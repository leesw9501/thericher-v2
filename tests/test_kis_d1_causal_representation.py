from __future__ import annotations

import ast
import hashlib
import json
from collections import OrderedDict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_d1_causal_representation as subject


def test_builds_development_only_windows_and_causal_terminal_mask() -> None:
    dataset = subject.build_kis_d1_causal_representation_dataset(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )

    assert dataset.training_windows.shape == (5808, 32, 5)
    assert dataset.diagnostic_windows.shape == (2676, 32, 5)
    inputs, targets = subject.mask_causal_representation_windows(dataset.training_windows[:2])

    assert inputs.shape == (2, 32, 6)
    assert targets.shape == (2, 4, 5)
    assert numpy.array_equal(inputs[:, -4:, :5], numpy.zeros((2, 4, 5), dtype=numpy.float32))
    assert numpy.array_equal(inputs[:, :-4, 5], numpy.zeros((2, 28), dtype=numpy.float32))
    assert numpy.array_equal(inputs[:, -4:, 5], numpy.ones((2, 4), dtype=numpy.float32))
    assert numpy.array_equal(targets, dataset.training_windows[:2, -4:, :])


def test_rejects_non_development_phase_and_source_identity() -> None:
    phase = _development_phase()
    phase.phase = "validation"

    with pytest.raises(ValueError, match="development phase"):
        subject.build_kis_d1_causal_representation_dataset(
            phase,
            input_id="kis.paper.private.daily.nas.sequence.input-v1",
        )

    invalid = _development_phase()
    invalid.parent_dataset_hash = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="development phase"):
        subject.build_kis_d1_causal_representation_dataset(
            invalid,
            input_id="kis.paper.private.daily.nas.sequence.input-v1",
        )


def test_freeze_is_external_immutable_and_contains_no_source_values(tmp_path: Path) -> None:
    dataset = subject.build_kis_d1_causal_representation_dataset(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    contract = subject.freeze_kis_d1_causal_representation_campaign(
        dataset,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-sha256",
    )
    same = subject.freeze_kis_d1_causal_representation_campaign(
        dataset,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-sha256",
    )
    payload = json.loads(contract.contract_path.read_text(encoding="utf-8"))

    assert contract.run_directory.is_relative_to(artifact_root)
    assert same.contract_sha256 == contract.contract_sha256
    assert payload["source"]["phase"] == "development_only"
    serialized = json.dumps(payload, sort_keys=True)
    assert "100.00" not in serialized
    assert "2020-" not in serialized
    assert '"predictions_persisted": false' in serialized
    assert '"pnl_or_profitability_claim": false' in serialized

    reattached = subject.freeze_kis_d1_causal_representation_campaign(
        dataset,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="different-code-revision",
    )
    assert reattached.contract_sha256 == contract.contract_sha256
    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.freeze_kis_d1_causal_representation_campaign(
            dataset,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
            code_revision="unit-code-sha256",
        )


def test_cuda_unavailable_writes_one_categorical_external_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset = subject.build_kis_d1_causal_representation_dataset(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    contract = subject.freeze_kis_d1_causal_representation_campaign(
        dataset,
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
        code_revision="unit-code-sha256",
    )
    _write_completed_cpu_smoke(contract)
    monkeypatch.setattr(
        subject,
        "_torch",
        lambda: SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    result = subject.run_kis_d1_causal_representation_cuda(contract)
    repeated = subject.run_kis_d1_causal_representation_cuda(contract)
    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert result.status == "runtime_unavailable"
    assert result.device == "unavailable"
    assert result.steps_completed == 0
    assert result.weights_path is None
    assert result.registry_outcome is not None
    assert repeated.summary_sha256 == result.summary_sha256
    assert repeated.registry_outcome is not None
    assert payload["weights_sha256"] if "weights_sha256" in payload else None is None
    assert "account" not in json.dumps(payload, sort_keys=True)
    assert "order" not in json.dumps(payload, sort_keys=True)


def test_safe_weight_serialization_uses_npz_without_pickle(tmp_path: Path) -> None:
    class Tensor:
        def __init__(self, value: numpy.ndarray) -> None:
            self.value = value

        def detach(self) -> Tensor:
            return self

        def cpu(self) -> Tensor:
            return self

        def contiguous(self) -> Tensor:
            return self

        def numpy(self) -> numpy.ndarray:
            return self.value

    class Model:
        def state_dict(self) -> dict[str, Tensor]:
            return {"weight": Tensor(numpy.asarray([[1.0, 2.0]], dtype=numpy.float32))}

    path = tmp_path / "weights.npz"
    digest = subject._write_or_verify_safe_weights(path=path, model=Model(), numpy=numpy)
    loaded = numpy.load(path, allow_pickle=False)

    assert digest == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.files == ["weight"]
    assert numpy.array_equal(loaded["weight"], numpy.asarray([[1.0, 2.0]], dtype=numpy.float32))


def test_orphaned_or_pickled_weight_archives_fail_closed(tmp_path: Path) -> None:
    class Tensor:
        def detach(self) -> Tensor:
            return self

        def cpu(self) -> Tensor:
            return self

        def contiguous(self) -> Tensor:
            return self

        def numpy(self) -> numpy.ndarray:
            return numpy.asarray([1.0], dtype=numpy.float32)

    class Model:
        def state_dict(self) -> dict[str, Tensor]:
            return {"weight": Tensor()}

    orphan = tmp_path / "orphan.npz"
    subject._write_or_verify_safe_weights(path=orphan, model=Model(), numpy=numpy)
    with pytest.raises(FileExistsError, match="orphaned"):
        subject._write_or_verify_safe_weights(path=orphan, model=Model(), numpy=numpy)

    pickled = tmp_path / "pickled.npz"
    with pickled.open("wb") as handle:
        numpy.savez_compressed(handle, weight=numpy.asarray([object()], dtype=object))
    with pytest.raises(ValueError, match="archive"):
        subject._verify_safe_weight_archive(pickled)


def test_existing_summary_must_bind_to_its_current_contract(tmp_path: Path) -> None:
    dataset = subject.build_kis_d1_causal_representation_dataset(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    contract = subject.freeze_kis_d1_causal_representation_campaign(
        dataset,
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
        code_revision="unit-code-sha256",
    )
    _write_completed_cpu_smoke(contract)
    foreign = replace(contract, contract_sha256="sha256:" + "b" * 64)

    with pytest.raises(ValueError, match="summary is malformed"):
        subject._load_existing_run(foreign, phase="cpu_smoke")


def test_leaf_source_keeps_torch_and_execution_as_run_time_boundaries() -> None:
    source = Path(subject.__file__).read_text(encoding="utf-8")
    module = ast.parse(source)
    top_level_imports = {
        alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "from thericher_v2.execution" not in source
    assert "torch" not in top_level_imports
    assert "from thericher_v2.data.kis_paper_daily_history_sequence_input import" in source
    assert "os.environ" not in source
    assert "requests" not in source
    assert "socket" not in source
    assert "KisPaperClient" not in source


def _write_completed_cpu_smoke(contract: subject.KisD1CausalRepresentationContract) -> None:
    weights_path = contract.run_directory / "cpu_smoke-weights.npz"
    with weights_path.open("wb") as handle:
        numpy.savez_compressed(handle, weight=numpy.asarray([1.0], dtype=numpy.float32))
    weights_hash = "sha256:" + hashlib.sha256(weights_path.read_bytes()).hexdigest()
    payload = subject._signed_payload(
        {
            "schema_version": 1,
            "campaign_id": subject.KIS_D1_CAUSAL_REPRESENTATION_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "phase": "cpu_smoke",
            "status": "completed",
            "device": "cpu",
            "steps_completed": subject.KIS_D1_CAUSAL_REPRESENTATION_CPU_STEPS,
            "training_loss_finite": True,
            "training_loss_decreased": False,
            "diagnostic_loss_finite": True,
            "weights_sha256": weights_hash,
            "scope": subject._non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    subject._write_or_verify_json(contract.run_directory / "cpu_smoke-summary.json", payload)


def _development_phase() -> SimpleNamespace:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    bars_by_symbol: OrderedDict[str, SimpleNamespace] = OrderedDict()
    sessions = tuple((start + timedelta(days=index)).date() for index in range(1510))
    for symbol_index, symbol in enumerate(subject.KIS_D1_CAUSAL_REPRESENTATION_SYMBOLS):
        bars: list[Bar] = []
        for index in range(1510):
            opening = Decimal("100") + Decimal(symbol_index) + Decimal(index) / Decimal("10")
            move = Decimal((index % 11) - 5) / Decimal("1000")
            close = opening * (Decimal("1") + move)
            high = max(opening, close) + Decimal("0.25") + Decimal(index % 3) / Decimal("100")
            low = min(opening, close) - Decimal("0.25") - Decimal(index % 5) / Decimal("100")
            bars.append(
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=start + timedelta(days=index),
                    open=opening,
                    high=high,
                    low=low,
                    close=close,
                    volume=Decimal("1000") + Decimal((index * 7 + symbol_index) % 19),
                    complete=True,
                )
            )
        bars_by_symbol[symbol] = SimpleNamespace(bars=tuple(bars))
    return SimpleNamespace(
        phase="development",
        parent_dataset_id=subject.KIS_D1_CAUSAL_REPRESENTATION_DATASET_ID,
        parent_dataset_hash=subject.KIS_D1_CAUSAL_REPRESENTATION_DATASET_HASH,
        index_hash="sha256:" + "a" * 64,
        bars_by_symbol=bars_by_symbol,
        common_sessions=sessions,
    )

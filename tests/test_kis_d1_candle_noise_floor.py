from __future__ import annotations

import ast
import importlib.util
import json
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_d1_candle_noise_floor as subject


def test_builds_fixed_candle_only_chronological_input() -> None:
    prepared = subject.build_kis_d1_candle_noise_floor_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )

    assert prepared.status == "ready"
    assert prepared.training_row_count == 5808
    assert prepared.validation_row_count == 2670
    assert prepared.validation_symbol_row_counts == (445, 445, 445, 445, 445, 445)
    assert prepared._training_features.shape == (5808, 96)
    assert prepared._validation_features.shape == (2670, 96)
    assert not prepared._training_features.flags.writeable
    assert prepared.safe_payload()["target_values_persisted"] is False
    assert prepared.safe_payload()["predictions_persisted"] is False

    bar = _bar(symbol="AAPL", index=10, upward=True, volume=Decimal("100"))
    changed_volume = _bar(symbol="AAPL", index=10, upward=True, volume=Decimal("900000"))
    assert subject._candle_feature_row(bar) == subject._candle_feature_row(changed_volume)


def test_invalid_candle_ratio_closes_input_before_fitting() -> None:
    phase = _development_phase()
    invalid = phase.bars_by_symbol["AAPL"].bars[0]
    object.__setattr__(invalid, "open", Decimal("0"))

    prepared = subject.build_kis_d1_candle_noise_floor_input(
        phase,
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )

    assert prepared.status == "input_unavailable"
    assert prepared.reason == "invalid_candle_ratio"
    assert prepared.training_row_count == 0
    assert prepared.validation_row_count == 0


def test_block_nulls_stay_inside_each_symbol_timeline() -> None:
    labels = numpy.asarray(
        [
            *([0] * 10),
            *([1] * 10),
            *([0] * 10),
            *([1] * 10),
            *([0] * 10),
            *([1] * 10),
        ],
        dtype=numpy.int8,
    )
    counts = (10, 10, 10, 10, 10, 10)

    permuted = subject._block_permute_validation_labels(
        labels,
        symbol_row_counts=counts,
        seed=1234,
    )

    cursor = 0
    for count in counts:
        assert numpy.array_equal(
            numpy.sort(permuted[cursor : cursor + count]),
            numpy.sort(labels[cursor : cursor + count]),
        )
        cursor += count


def test_frozen_external_run_uses_train_only_normalization_and_categorical_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prepared = subject.build_kis_d1_candle_noise_floor_input(
        _development_phase(),
        input_id="kis.paper.private.daily.nas.sequence.input-v1",
    )
    repo_root = tmp_path / "repository"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    captured_training: list[numpy.ndarray] = []

    class PredictiveModel:
        def predict_proba(self, values: numpy.ndarray) -> numpy.ndarray:
            probabilities = numpy.where(values[:, -1] < 0.0, 0.9, 0.1)
            return numpy.column_stack((1.0 - probabilities, probabilities))

    def fit(
        training_features: numpy.ndarray,
        _labels: numpy.ndarray,
        *,
        seed: int,
    ) -> PredictiveModel:
        assert seed in subject.KIS_D1_CANDLE_NOISE_FLOOR_SEEDS
        captured_training.append(training_features.copy())
        return PredictiveModel()

    monkeypatch.setattr(subject, "_fit_logistic", fit)
    contract = subject.freeze_kis_d1_candle_noise_floor_campaign(
        prepared,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="unit-code-revision",
    )
    same = subject.freeze_kis_d1_candle_noise_floor_campaign(
        prepared,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision="different-unit-code-revision",
    )
    result = subject.run_kis_d1_candle_noise_floor(contract)
    repeated = subject.run_kis_d1_candle_noise_floor(contract)
    contract_payload = json.loads(contract.contract_path.read_text(encoding="utf-8"))
    summary_payload = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert same.contract_sha256 == contract.contract_sha256
    assert result.status == "noise_floor_passed"
    assert repeated.summary_sha256 == result.summary_sha256
    assert result.registry_outcome.record_sha256 == repeated.registry_outcome.record_sha256
    assert contract.run_directory.is_relative_to(artifact_root)
    assert len(captured_training) == len(subject.KIS_D1_CANDLE_NOISE_FLOOR_SEEDS)
    for values in captured_training:
        assert numpy.allclose(values.mean(axis=0), 0.0)
        assert numpy.allclose(values.std(axis=0), 1.0)
    serialized = json.dumps(
        {"contract": contract_payload, "summary": summary_payload},
        sort_keys=True,
    )
    assert "100.00" not in serialized
    assert "2020-" not in serialized
    assert '"numeric_metrics_persisted": false' in serialized
    assert '"checkpoint_written": false' in serialized
    assert not list(contract.run_directory.glob("*.npz"))

    with pytest.raises(ValueError, match="outside the Git workspace"):
        subject.freeze_kis_d1_candle_noise_floor_campaign(
            prepared,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
            code_revision="unit-code-revision",
        )


def test_leaf_stays_outside_execution_network_and_gpu_surfaces() -> None:
    source = Path(subject.__file__).read_text(encoding="utf-8")
    module = ast.parse(source)
    top_level_imports = {
        alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "from thericher_v2.execution" not in source
    assert "torch" not in source
    assert "os.environ" not in source
    assert "requests" not in source
    assert "socket" not in source
    assert "sklearn" not in top_level_imports


def test_runner_only_wires_explicit_offline_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = Path(__file__).parents[1] / "scripts" / "run_kis_d1_candle_noise_floor.py"
    spec = importlib.util.spec_from_file_location("run_kis_d1_candle_noise_floor_test", path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    captured: dict[str, object] = {}
    prepared = SimpleNamespace()
    contract = SimpleNamespace(contract_sha256="sha256:" + "a" * 64)
    result = SimpleNamespace(
        status="noise_not_separable",
        reason="actual_label_signal_not_separable",
        summary_sha256="sha256:" + "b" * 64,
        registry_outcome=SimpleNamespace(record_sha256="sha256:" + "c" * 64),
    )

    def load(**kwargs: object) -> SimpleNamespace:
        captured["load"] = kwargs
        return prepared

    def freeze(value: object, **kwargs: object) -> SimpleNamespace:
        captured["freeze"] = {"value": value, **kwargs}
        return contract

    def run(value: object) -> SimpleNamespace:
        captured["run"] = value
        return result

    monkeypatch.setattr(runner, "load_kis_d1_candle_noise_floor_input", load)
    monkeypatch.setattr(runner, "freeze_kis_d1_candle_noise_floor_campaign", freeze)
    monkeypatch.setattr(runner, "run_kis_d1_candle_noise_floor", run)
    market_data_root = tmp_path / "market-data"
    artifact_root = tmp_path / "artifacts"
    runner.main(
        [
            "--market-data-root",
            str(market_data_root),
            "--artifact-root",
            str(artifact_root),
            "--repo-root",
            str(tmp_path),
            "--attempt-id",
            "unit-r1",
        ]
    )

    assert captured["freeze"]["value"] is prepared
    assert captured["freeze"]["artifact_root"] == artifact_root
    assert captured["freeze"]["attempt_id"] == "unit-r1"
    assert captured["run"] is contract
    runner_source = path.read_text(encoding="utf-8")
    for forbidden in (".env", "os.environ", "requests", "socket", "urllib", "torch"):
        assert forbidden not in runner_source


def _development_phase() -> SimpleNamespace:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(1510))
    bars_by_symbol: OrderedDict[str, SimpleNamespace] = OrderedDict()
    for symbol_index, symbol in enumerate(subject.KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS):
        bars_by_symbol[symbol] = SimpleNamespace(
            bars=tuple(
                _bar(
                    symbol=symbol,
                    index=index,
                    upward=index % 2 == 0,
                    volume=Decimal(1000 + symbol_index),
                )
                for index in range(1510)
            )
        )
    return SimpleNamespace(
        phase="development",
        parent_dataset_id=subject.KIS_D1_CANDLE_NOISE_FLOOR_DATASET_ID,
        parent_dataset_hash=subject.KIS_D1_CANDLE_NOISE_FLOOR_DATASET_HASH,
        index_hash="sha256:" + "a" * 64,
        bars_by_symbol=bars_by_symbol,
        common_sessions=sessions,
    )


def _bar(*, symbol: str, index: int, upward: bool, volume: Decimal) -> Bar:
    opening = Decimal("100") + Decimal(index) / Decimal("10")
    move = Decimal("0.01") if upward else Decimal("-0.01")
    close = opening * (Decimal("1") + move)
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index),
        open=opening,
        high=max(opening, close) + Decimal("0.25"),
        low=min(opening, close) - Decimal("0.25"),
        close=close,
        volume=volume,
        complete=True,
    )

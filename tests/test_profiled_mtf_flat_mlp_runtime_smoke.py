from __future__ import annotations

import hashlib
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.models.sequence_window import SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
from thericher_v2.research import profiled_mtf_flat_mlp_runtime_smoke as runtime_smoke
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from thericher_v2.research.profiled_mtf_flattened_control import (
    PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY,
    PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID,
    ProfiledMtfFlattenedBlock,
    ProfiledMtfFlattenedControl,
)


def test_runtime_batch_is_deterministic_and_uses_the_fixed_short_geometry() -> None:
    controls = (_control(1), _control(2))

    first = runtime_smoke.build_profiled_mtf_flat_mlp_runtime_batch(controls)
    second = runtime_smoke.build_profiled_mtf_flat_mlp_runtime_batch(controls)

    assert first == second
    assert first.control_count == 2
    assert first.feature_width == 50
    assert tuple(block.timeframe for block in first.layout) == SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    assert tuple(block.bar_count for block in first.layout) == (15, 3, 3, 2, 2)
    assert first.safe_payload()["batch_sha256"] == first.batch_sha256


def test_runtime_batch_rejects_duplicate_controls_and_noncanonical_layout() -> None:
    control = _control(1)

    with pytest.raises(ValueError, match="must not repeat"):
        runtime_smoke.build_profiled_mtf_flat_mlp_runtime_batch((control, control))

    noncanonical = _control(2, bar_counts=(14, 4, 3, 2, 2))
    with pytest.raises(ValueError, match="fixed canonical profile"):
        runtime_smoke.build_profiled_mtf_flat_mlp_runtime_batch(
            (noncanonical, _control(3, bar_counts=(14, 4, 3, 2, 2)))
        )


def test_contract_and_inventory_stay_outside_the_repository(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    artifact_root = tmp_path / "external-artifacts"
    repo_root.mkdir()
    contract = _freeze_contract(
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id="unit-contract",
    )

    inventory_path = runtime_smoke.write_profiled_mtf_flat_mlp_runtime_inventory(
        contract.inventory,
        artifact_root=artifact_root,
        repo_root=repo_root,
        attempt_id="unit-contract",
    )
    contract_text = contract.contract_path.read_text(encoding="utf-8")
    inventory_text = inventory_path.read_text(encoding="utf-8")

    assert contract.contract_path.is_relative_to(artifact_root.resolve())
    assert inventory_path.is_relative_to(artifact_root.resolve())
    assert not contract.contract_path.is_relative_to(repo_root.resolve())
    assert not inventory_path.is_relative_to(repo_root.resolve())
    assert '"feature_values_persisted":false' in contract_text
    assert '"weights_persisted":false' in contract_text
    assert '"predictive_target_ready_pair_count":0' in inventory_text
    assert "10100" not in contract_text
    assert "10100" not in inventory_text

    with pytest.raises(ValueError, match="outside the Git workspace"):
        _freeze_contract(
            artifact_root=repo_root / "model-artifacts",
            repo_root=repo_root,
            attempt_id="repo-artifact",
        )


def test_cuda_requires_cpu_then_records_a_scoped_unavailable_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _freeze_contract(
        artifact_root=tmp_path / "external-artifacts",
        repo_root=tmp_path / "repo",
        attempt_id="cuda-order",
    )

    with pytest.raises(ValueError, match="matching CPU runtime receipt"):
        runtime_smoke.run_profiled_mtf_flat_mlp_runtime_cuda(contract)

    runtime_smoke._write_run(
        contract,
        phase="cpu",
        status="completed",
        device="cpu",
        steps_completed=runtime_smoke.PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS,
        runtime_metrics={
            "control_count": contract.batch.control_count,
            "feature_width": contract.batch.feature_width,
            "structure_conclusion": "not_assessed_low_sample",
        },
    )
    monkeypatch.setattr(runtime_smoke, "_torch", lambda: _UnavailableTorch())

    first = runtime_smoke.run_profiled_mtf_flat_mlp_runtime_cuda(contract)
    second = runtime_smoke.run_profiled_mtf_flat_mlp_runtime_cuda(contract)

    assert first.status == "runtime_unavailable"
    assert first.device == "unavailable"
    assert first.steps_completed == 0
    assert first.runtime_metrics["reason"] == "cuda_runtime_unavailable"
    assert first.registry_outcome is not None
    assert first.registry_outcome.outcome_class == "non_promoting_failed"
    assert second.summary_sha256 == first.summary_sha256
    assert second.registry_outcome is not None


def test_existing_cuda_receipt_still_requires_its_matching_cpu_receipt(
    tmp_path: Path,
) -> None:
    contract = _freeze_contract(
        artifact_root=tmp_path / "external-artifacts",
        repo_root=tmp_path / "repo",
        attempt_id="cuda-reattach",
    )
    runtime_smoke._write_run(
        contract,
        phase="cpu",
        status="completed",
        device="cpu",
        steps_completed=runtime_smoke.PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS,
        runtime_metrics={"control_count": 2, "feature_width": 50},
    )
    runtime_smoke._write_run(
        contract,
        phase="cuda",
        status="completed",
        device="cuda",
        steps_completed=runtime_smoke.PROFILED_MTF_FLAT_MLP_RUNTIME_CUDA_STEPS,
        runtime_metrics={"control_count": 2, "feature_width": 50},
    )
    (contract.run_directory / "cpu-summary.json").unlink()

    with pytest.raises(ValueError, match="matching CPU runtime receipt"):
        runtime_smoke.run_profiled_mtf_flat_mlp_runtime_cuda(contract)


def test_runtime_run_rejects_impossible_phase_device_combinations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="phase/device combination"):
        runtime_smoke.ProfiledMtfFlatMlpRuntimeRun(
            contract_sha256=_digest("contract"),
            phase="cpu",
            status="completed",
            device="cuda",
            steps_completed=1,
            summary_path=tmp_path / "summary.json",
            summary_sha256=_digest("summary"),
            runtime_metrics={},
        )


def test_column_permutation_preserves_marginals_without_preserving_rows() -> None:
    matrix = (
        (1.0, 10.0, 100.0),
        (2.0, 20.0, 200.0),
        (3.0, 30.0, 300.0),
        (4.0, 40.0, 400.0),
    )

    permuted = runtime_smoke._column_permuted_matrix(matrix, seed=211)

    assert permuted != matrix
    for column in range(len(matrix[0])):
        assert sorted(row[column] for row in permuted) == sorted(
            row[column] for row in matrix
        )


def test_cpu_runtime_metrics_retain_the_fixed_contract_step_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = runtime_smoke.build_profiled_mtf_flat_mlp_runtime_batch((_control(1), _control(2)))
    calls: list[tuple[str, int]] = []

    def fake_metrics(
        _torch: object,
        _matrix: object,
        *,
        device_name: str,
        max_steps: int,
        max_seconds: float | None,
    ) -> dict[str, object]:
        calls.append((device_name, max_steps))
        assert max_seconds is None
        return {"steps_completed": max_steps, "initial_mse": 1.0, "final_mse": 1.0}

    monkeypatch.setattr(runtime_smoke, "_matrix_runtime_metrics", fake_metrics)

    metrics = runtime_smoke._cpu_runtime_metrics(object(), batch)

    assert metrics["steps_completed"] == runtime_smoke.PROFILED_MTF_FLAT_MLP_RUNTIME_CPU_STEPS
    assert calls == [("cpu", 8), ("cpu", 8)]


def test_inventory_on_a_missing_local_cache_never_uses_network_or_kis_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime inventory must not access a network provider")

    class EnvironmentWithoutKisSecrets(dict[str, str]):
        def get(self, key: str, default: object = None) -> object:
            if key.startswith("KIS_"):
                raise AssertionError("runtime inventory must not read KIS credentials")
            return super().get(key, default)

        def __getitem__(self, key: str) -> str:
            if key.startswith("KIS_"):
                raise AssertionError("runtime inventory must not read KIS credentials")
            return super().__getitem__(key)

    monkeypatch.setattr(socket, "socket", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "environ", EnvironmentWithoutKisSecrets(os.environ))

    with pytest.raises((FileNotFoundError, ValueError)):
        runtime_smoke.inspect_profiled_mtf_flat_mlp_runtime_inventory(
            cache_root=tmp_path / "empty-local-cache",
            repo_root=tmp_path / "repo",
            code_revision_sha256=_digest("code"),
        )


def _freeze_contract(
    *,
    artifact_root: Path,
    repo_root: Path,
    attempt_id: str,
) -> runtime_smoke.ProfiledMtfFlatMlpRuntimeContract:
    repo_root.mkdir(parents=True, exist_ok=True)
    batch = runtime_smoke.build_profiled_mtf_flat_mlp_runtime_batch((_control(1), _control(2)))
    inventory = runtime_smoke._build_inventory(
        status="runtime_input_ready",
        reason=None,
        source_contract_sha256=_digest("source-contract"),
        source_receipt_sha256=_digest("source-receipt"),
        feature_input_contract_sha256=_digest("feature-contract"),
        feature_input_receipt_sha256=_digest("feature-receipt"),
        eligible_session_count=1,
        batch=batch,
    )
    return runtime_smoke.freeze_profiled_mtf_flat_mlp_runtime_smoke(
        inventory,
        artifact_root=artifact_root,
        repo_root=repo_root,
        code_revision_sha256=_digest("code"),
        attempt_id=attempt_id,
    )


def _control(
    index: int,
    *,
    bar_counts: tuple[int, int, int, int, int] = (15, 3, 3, 2, 2),
) -> ProfiledMtfFlattenedControl:
    """Build caller-owned controls without reopening a source cache in this unit test."""

    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile("short")
    blocks: list[ProfiledMtfFlattenedBlock] = []
    values: list[Decimal] = []
    feature_offset = 0
    window_end = datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=index)
    for timeframe, bar_count in zip(
        SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES, bar_counts, strict=True
    ):
        blocks.append(
            ProfiledMtfFlattenedBlock(
                timeframe=timeframe,
                feature_offset=feature_offset,
                bar_count=bar_count,
                window_end=window_end,
                anchor_policy=PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY,
            )
        )
        values.extend(Decimal(10_000 + index * 100 + value) for value in range(bar_count * 2))
        feature_offset += bar_count * 2

    control = object.__new__(ProfiledMtfFlattenedControl)
    object.__setattr__(
        control,
        "projection",
        SimpleNamespace(
            source_contract_sha256=_digest("source-contract"),
            source_dataset_hash=_digest(f"dataset-{index % 2}"),
            catalog_sha256=profile.identity_sha256,
            profile_id="short",
        ),
    )
    object.__setattr__(control, "blocks", tuple(blocks))
    object.__setattr__(control, "flattened_values", tuple(values))
    object.__setattr__(control, "control_sha256", _digest(f"control-{index}-{bar_counts}"))
    object.__setattr__(control, "schema_id", PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID)
    object.__setattr__(control, "schema_version", SCHEMA_VERSION)
    return control


class _UnavailableTorch:
    class cuda:
        @staticmethod
        def is_available() -> bool:
            return False


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.models.sequence_window import SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
from thericher_v2.research import profiled_mtf_flat_mlp_runtime_smoke as flat_runtime
from thericher_v2.research import profiled_mtf_ragged_sequence_runtime as runtime
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from thericher_v2.research.profiled_mtf_flattened_control import (
    PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY,
    PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID,
    ProfiledMtfFlattenedBlock,
    ProfiledMtfFlattenedControl,
)


def test_ragged_batch_preserves_native_frame_lengths_and_explicit_masks() -> None:
    batch = runtime.build_profiled_mtf_ragged_sequence_batch(_source())

    assert tuple(frame.timeframe for frame in batch.frames) == SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    assert tuple(frame.sequence_length for frame in batch.frames) == (15, 3, 3, 2, 2)
    assert batch.token_count == 25
    assert batch.control_count == 2
    assert all(value for control in batch.validity_masks for frame in control for value in frame)
    payload = batch.safe_payload()
    assert payload["mask_policy"] == runtime.PROFILED_MTF_RAGGED_SEQUENCE_MASK_POLICY
    rendered = json.dumps(payload, sort_keys=True)
    for forbidden in ("QQQ", "SPY", "2026-", "10000"):
        assert forbidden not in rendered


def test_ragged_batch_rejects_post_cutoff_frames_and_false_masks() -> None:
    future_source = _source(window_end_delta=timedelta(minutes=1))
    with pytest.raises(ValueError, match="frame geometry"):
        runtime.build_profiled_mtf_ragged_sequence_batch(future_source)

    batch = runtime.build_profiled_mtf_ragged_sequence_batch(_source())
    invalid_masks = tuple(
        tuple(
            tuple(
                False if (control_index, frame_index, row_index) == (0, 0, 0) else value
                for row_index, value in enumerate(frame)
            )
            for frame_index, frame in enumerate(control)
        )
        for control_index, control in enumerate(batch.validity_masks)
    )
    with pytest.raises(ValueError, match="values or mask"):
        replace(batch, validity_masks=invalid_masks)


def test_runtime_requires_cpu_and_contains_unavailable_cuda(tmp_path: Path, monkeypatch) -> None:
    contract = _contract(tmp_path)

    with pytest.raises(ValueError, match="matching CPU runtime receipt"):
        runtime.run_profiled_mtf_ragged_sequence_runtime_cuda(contract)

    runtime._write_run(
        contract,
        phase="cpu",
        status="completed",
        device="cpu",
        steps_completed=runtime._total_steps(
            runtime.PROFILED_MTF_RAGGED_SEQUENCE_RUNTIME_CPU_STEPS_PER_FAMILY
        ),
        runtime_metrics={"steps_completed": runtime._total_steps(4)},
    )
    monkeypatch.setattr(runtime, "_torch", lambda: _UnavailableTorch())

    first = runtime.run_profiled_mtf_ragged_sequence_runtime_cuda(contract)
    second = runtime.run_profiled_mtf_ragged_sequence_runtime_cuda(contract)

    assert first.status == "runtime_unavailable"
    assert first.device == "unavailable"
    assert first.steps_completed == 0
    assert first.runtime_metrics["reason"] == "cuda_runtime_unavailable"
    assert first.registry_outcome is not None
    assert first.registry_outcome.outcome_class == "non_promoting_failed"
    assert second.summary_sha256 == first.summary_sha256


def test_contract_requires_external_artifacts_and_core_has_no_execution_route(
    tmp_path: Path,
) -> None:
    source = _source()
    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(ValueError, match="outside the Git workspace"):
        runtime.freeze_profiled_mtf_ragged_sequence_runtime(
            source,
            artifact_root=repository,
            repo_root=repository,
            code_revision_sha256=_digest("code"),
            attempt_id="unit",
        )

    script = """
import sys
import typing
import thericher_v2.research.profiled_mtf_ragged_sequence_runtime as runtime
typing.get_type_hints(runtime.freeze_profiled_mtf_ragged_sequence_runtime)
for name in sys.modules:
    if name.startswith('thericher_v2.execution'):
        raise SystemExit(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    source_text = Path(runtime.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("os.environ", "socket", "urllib", "requests", "local_paper", "kis_live"):
        assert forbidden not in source_text


def test_runner_keeps_the_runtime_local_only_and_uses_external_artifact_defaults() -> None:
    script = Path("scripts/run_profiled_mtf_ragged_sequence_runtime.py")
    source_text = script.read_text(encoding="utf-8").lower()

    assert 'path("/app/model_artifacts")' in source_text
    assert 'path("/app/market_data/' in source_text
    for forbidden in (
        "os.environ",
        ".env",
        "requests",
        "urllib",
        "socket",
        "thericher_v2.execution",
        "local_paper",
        "kis_live",
    ):
        assert forbidden not in source_text


def _contract(tmp_path: Path) -> runtime.ProfiledMtfRaggedSequenceRuntimeContract:
    repository = tmp_path / "repo"
    repository.mkdir()
    return runtime.freeze_profiled_mtf_ragged_sequence_runtime(
        _source(),
        artifact_root=tmp_path / "artifacts",
        repo_root=repository,
        code_revision_sha256=_digest("code"),
        attempt_id="unit",
    )


def _source(
    *,
    window_end_delta: timedelta = timedelta(),
) -> flat_runtime.ProfiledMtfFlatMlpRuntimeSource:
    controls = (_control(1, window_end_delta=window_end_delta), _control(2))
    batch = flat_runtime.build_profiled_mtf_flat_mlp_runtime_batch(controls)
    inventory = flat_runtime._build_inventory(
        status="runtime_input_ready",
        reason=None,
        source_contract_sha256=_digest("source-contract"),
        source_receipt_sha256=_digest("source-receipt"),
        feature_input_contract_sha256=_digest("feature-contract"),
        feature_input_receipt_sha256=_digest("feature-receipt"),
        eligible_session_count=1,
        batch=batch,
    )
    return flat_runtime.ProfiledMtfFlatMlpRuntimeSource(
        inventory=inventory,
        controls=controls,
    )


def _control(
    index: int,
    *,
    window_end_delta: timedelta = timedelta(),
) -> ProfiledMtfFlattenedControl:
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile("short")
    cutoff = datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=index)
    blocks: list[ProfiledMtfFlattenedBlock] = []
    values: list[Decimal] = []
    feature_offset = 0
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        bar_count = profile.lookbacks[timeframe]
        blocks.append(
            ProfiledMtfFlattenedBlock(
                timeframe=timeframe,
                feature_offset=feature_offset,
                bar_count=bar_count,
                window_end=cutoff + window_end_delta,
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
            source_dataset_hash=_digest(f"dataset-{index}"),
            catalog_sha256=profile.identity_sha256,
            profile_id="short",
            cutoff=cutoff,
        ),
    )
    object.__setattr__(control, "blocks", tuple(blocks))
    object.__setattr__(control, "flattened_values", tuple(values))
    object.__setattr__(control, "control_sha256", _digest(f"control-{index}"))
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

from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
import urllib.request
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

import thericher_v2.kis_daily_joint_event_d1_sequence_screen as screen
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KisDailyJointEventD1Materializer,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    build_kis_daily_joint_event_d1_target_cost_adapter,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    KisDailyJointEventFoldInput,
    KisDailyJointEventWindowSpec,
)


def test_sequence_input_preserves_causal_geometry_sparse_splits_and_tail() -> None:
    materializer, adapter = _materializer_and_adapter()

    prepared = screen.build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=materializer,
        target_adapter=adapter,
    )

    development_indices = materializer.eligible_decision_indices("development")
    validation_indices = materializer.eligible_decision_indices("validation")
    assert len(prepared.development_samples) == 2345
    assert len(prepared.validation_samples) == 146
    assert (
        tuple(sample.decision_index for sample in prepared.development_samples)
        == development_indices
    )
    assert (
        tuple(sample.decision_index for sample in prepared.validation_samples)
        == validation_indices
    )
    assert not set(development_indices).intersection(validation_indices)
    assert prepared.untouched_tail_session_count == 151
    assert all(
        sample.decision_index < materializer.fold_input.validation_end_index
        for sample in prepared.validation_samples
    )
    first = prepared.development_samples[0]
    assert first.predecessor_index == first.decision_index - 20
    assert first.feature_start_index == first.decision_index - 19
    assert first.feature_end_index == first.decision_index
    assert first.entry_index == first.decision_index + 1
    assert first.exit_index == first.decision_index + 2
    assert len(first.features) == 20
    assert all(
        row[2] == pytest.approx(row[0] - row[1], abs=1e-15)
        for row in first.features
    )


def test_future_open_changes_only_the_in_memory_target_not_features() -> None:
    baseline_materializer, baseline_adapter = _materializer_and_adapter()
    baseline = screen.build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=baseline_materializer,
        target_adapter=baseline_adapter,
    )
    target_sample = next(sample for sample in baseline.validation_samples if sample.target == 0)
    shifted_materializer, shifted_adapter = _materializer_and_adapter(
        qqq_open_overrides={target_sample.exit_index: Decimal("9999")},
    )
    shifted = screen.build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=shifted_materializer,
        target_adapter=shifted_adapter,
    )
    shifted_sample = _sample_for_decision(shifted.validation_samples, target_sample.decision_index)

    assert shifted_sample.features == target_sample.features
    assert target_sample.target == 0
    assert shifted_sample.target == 1


def test_standardizer_is_fit_only_on_development_values() -> None:
    baseline_materializer, baseline_adapter = _materializer_and_adapter()
    baseline = screen.build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=baseline_materializer,
        target_adapter=baseline_adapter,
    )
    validation_index = baseline.validation_samples[0].decision_index
    validation_changed_materializer, validation_changed_adapter = _materializer_and_adapter(
        qqq_close_overrides={validation_index: Decimal("999")},
    )
    validation_changed = screen.build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=validation_changed_materializer,
        target_adapter=validation_changed_adapter,
    )
    development_index = baseline.development_samples[0].decision_index
    development_changed_materializer, development_changed_adapter = _materializer_and_adapter(
        qqq_close_overrides={development_index: Decimal("999")},
    )
    development_changed = screen.build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=development_changed_materializer,
        target_adapter=development_changed_adapter,
    )

    assert (
        baseline.standardizer.normalization_identity
        == validation_changed.standardizer.normalization_identity
    )
    assert baseline.validation_samples != validation_changed.validation_samples
    assert (
        baseline.standardizer.normalization_identity
        != development_changed.standardizer.normalization_identity
    )
    assert (
        baseline.standardizer.transform(baseline.validation_samples[0].features)
        != development_changed.standardizer.transform(baseline.validation_samples[0].features)
    )


def test_candidate_only_run_is_external_source_safe_and_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    materializer, adapter = _materializer_and_adapter()
    artifact_root = tmp_path / "model-artifacts"

    first = screen.run_kis_daily_joint_event_d1_sequence_screen(
        materializer=materializer,
        target_adapter=adapter,
        artifact_root=artifact_root,
        run_label="cpu-a",
        mode="cpu-smoke",
        repo_root=tmp_path / "repo",
        trainer=_fake_trainer,
    )
    second = screen.run_kis_daily_joint_event_d1_sequence_screen(
        materializer=materializer,
        target_adapter=adapter,
        artifact_root=artifact_root,
        run_label="cpu-b",
        mode="cpu-smoke",
        repo_root=tmp_path / "repo",
        trainer=_fake_trainer,
    )

    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    serialized = first.summary_path.read_text(encoding="utf-8").lower()
    assert first.precommit_identity == second.precommit_identity
    assert first.result_identity == second.result_identity
    assert [result.spec.candidate_id for result in first.candidate_results] == [
        "linear",
        "compact_gru",
    ]
    assert summary["split"] == {
        "development_decision_count": 2345,
        "pre_validation_gap_consumed": False,
        "untouched_tail_session_count": 151,
        "validation_decision_count": 146,
    }
    assert summary["scope"] == {
        "candidate_only": True,
        "candidate_selection_eligible": False,
        "credentials_persisted": False,
        "ensemble_eligible": False,
        "feature_values_persisted": False,
        "model_execution_eligible": False,
        "offline_only": True,
        "paper_decision_eligible": False,
        "per_decision_outputs_persisted": False,
        "raw_market_data_persisted": False,
        "replay_materialized": False,
        "target_values_persisted": False,
    }
    assert all(result.metrics.evaluated_count == 146 for result in first.candidate_results)
    assert all(term not in serialized for term in ('"open"', '"close"', '"return"'))
    assert all(
        term not in serialized
        for term in ('"label"', '"prediction"', '"pnl"', '"order"', '"account"')
    )
    assert first.summary_path.is_relative_to(artifact_root)
    assert first.precommit_path.is_relative_to(artifact_root)
    with pytest.raises(ValueError, match="not source-safe"):
        screen._assert_source_safe({"label": 1})  # noqa: SLF001
    with pytest.raises(ValueError, match="outside the Git workspace"):
        screen.run_kis_daily_joint_event_d1_sequence_screen(
            materializer=materializer,
            target_adapter=adapter,
            artifact_root=tmp_path / "repo" / "model-artifacts",
            run_label="bad-root",
            mode="cpu-smoke",
            repo_root=tmp_path / "repo",
            trainer=_fake_trainer,
        )


def test_sequence_screen_import_and_script_help_stay_offline_and_route_free() -> None:
    module_code = """\
import importlib
import sys
importlib.import_module('thericher_v2.kis_daily_joint_event_d1_sequence_screen')
assert 'torch' not in sys.modules
assert not [name for name in sys.modules if name.startswith('thericher_v2.data')]
assert not [name for name in sys.modules if name.startswith('thericher_v2.execution')]
"""
    result = subprocess.run(
        [sys.executable, "-c", module_code],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "thericher_v2"
        / "kis_daily_joint_event_d1_sequence_screen.py"
    )
    imports = _imports(module_path)
    assert not any(
        term in imported
        for imported in imports
        for term in (
            "execution",
            "broker",
            "socket",
            "urllib",
            "http",
            "requests",
            "dotenv",
            "tiingo",
            "kis_paper",
            "replay",
            "order",
        )
    )

    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_daily_joint_event_d1_sequence_screen.py"
    )
    help_code = f"""\
import subprocess
import sys
result = subprocess.run([sys.executable, {str(script_path)!r}, '--help'], check=False)
assert result.returncode == 0
assert not [name for name in sys.modules if name.startswith('thericher_v2.data')]
assert not [name for name in sys.modules if name.startswith('thericher_v2.execution')]
"""
    help_result = subprocess.run(
        [sys.executable, "-c", help_code],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert help_result.returncode == 0, help_result.stderr


def _materializer_and_adapter(
    *,
    qqq_open_overrides: Mapping[int, Decimal] | None = None,
    qqq_close_overrides: Mapping[int, Decimal] | None = None,
) -> tuple[KisDailyJointEventD1Materializer, object]:
    sessions = _sessions()
    fold_input = _fold_input(sessions)
    opens = qqq_open_overrides or {}
    closes = qqq_close_overrides or {}
    materializer = KisDailyJointEventD1Materializer(
        fold_input=fold_input,
        fold_artifact_sha256=_sha256("fold-artifact"),
        catalog_dataset_hash=fold_input.catalog_dataset_hash,
        catalog_index_hash=fold_input.catalog_index_hash,
        common_sessions=sessions,
        bars_by_symbol=MappingProxyType(
            {
                "QQQ": _bars(
                    symbol="QQQ",
                    sessions=sessions,
                    open_overrides=opens,
                    close_overrides=closes,
                ),
                "SPY": _bars(symbol="SPY", sessions=sessions),
            }
        ),
    )
    adapter = build_kis_daily_joint_event_d1_target_cost_adapter(materializer=materializer)
    return materializer, adapter


def _sessions() -> tuple[date, ...]:
    start = date(2018, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(4756))


def _fold_input(sessions: tuple[date, ...]) -> KisDailyJointEventFoldInput:
    development_end = 2367
    gap_end = development_end + 22
    validation_end = gap_end + 252
    development_indices = tuple(range(20, 2365))
    validation_indices = tuple(range(gap_end + 20, gap_end + 20 + 146))
    return KisDailyJointEventFoldInput(
        source_artifact_sha256=_sha256("parent-artifact"),
        source_contract_identity=_sha256("parent-contract"),
        catalog_dataset_hash=_sha256("catalog-dataset"),
        catalog_index_hash=_sha256("catalog-index"),
        sidecar_dataset_hash=_sha256("sidecar-dataset"),
        sidecar_manifest_hash=_sha256("sidecar-manifest"),
        event_boundary_audit_sha256=_sha256("audit"),
        event_boundary_mask_identity=_sha256("mask"),
        event_boundary_partition_identity=_sha256("partition"),
        joint_event_identity=_sha256("joint"),
        fold_id="expanding-1",
        development_start_index=0,
        development_end_index=development_end,
        pre_validation_gap_start_index=development_end,
        pre_validation_gap_end_index=gap_end,
        validation_start_index=gap_end,
        validation_end_index=validation_end,
        development_start_session=sessions[0],
        development_end_session=sessions[development_end - 1],
        pre_validation_gap_start_session=sessions[development_end],
        pre_validation_gap_end_session=sessions[gap_end - 1],
        validation_start_session=sessions[gap_end],
        validation_end_session=sessions[validation_end - 1],
        development_eligible_decision_indices=development_indices,
        validation_eligible_decision_indices=validation_indices,
        development_eligible_decision_identity=_sha256("development-indices"),
        validation_eligible_decision_identity=_sha256("validation-indices"),
        spec=KisDailyJointEventWindowSpec(),
        model_execution_review=KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
        reattested_against_parent=True,
    )


def _bars(
    *,
    symbol: str,
    sessions: tuple[date, ...],
    open_overrides: Mapping[int, Decimal] | None = None,
    close_overrides: Mapping[int, Decimal] | None = None,
) -> tuple[Bar, ...]:
    opens = open_overrides or {}
    closes = close_overrides or {}
    base = Decimal("100") if symbol == "QQQ" else Decimal("200")
    bars: list[Bar] = []
    for index, session in enumerate(sessions):
        opening = opens.get(
            index,
            base + Decimal(index) / Decimal("100") + Decimal(index % 5) / Decimal("10"),
        )
        closing = closes.get(index, opening + Decimal((index % 3) - 1) / Decimal("100"))
        bars.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                open=opening,
                high=max(opening, closing) + Decimal("1"),
                low=min(opening, closing) - Decimal("1"),
                close=closing,
                volume=Decimal("1000"),
                complete=True,
            )
        )
    return tuple(bars)


def _fake_trainer(
    prepared: screen.KisDailyJointEventD1ScreenInput,
    spec: screen.KisDailyJointEventD1CandidateSpec,
    mode: screen.CandidateScreenMode,
) -> screen.KisDailyJointEventD1CandidateResult:
    observed_positive = sum(sample.target for sample in prepared.validation_samples)
    true_negative = len(prepared.validation_samples) - observed_positive
    metrics = screen.KisDailyJointEventD1ClassificationMetrics(
        evaluated_count=len(prepared.validation_samples),
        observed_positive_count=observed_positive,
        true_positive_count=0,
        true_negative_count=true_negative,
        false_positive_count=0,
        false_negative_count=observed_positive,
        accuracy=round(true_negative / len(prepared.validation_samples), 12),
        precision=0.0,
        recall=0.0,
        f1=0.0,
    )
    return screen.KisDailyJointEventD1CandidateResult(
        spec=spec,
        mode=mode,
        backend="unit",
        metrics=metrics,
    )


def _sample_for_decision(
    samples: tuple[screen.KisDailyJointEventD1SequenceSample, ...],
    decision_index: int,
) -> screen.KisDailyJointEventD1SequenceSample:
    return next(sample for sample in samples if sample.decision_index == decision_index)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate-only D1 screen must remain offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()

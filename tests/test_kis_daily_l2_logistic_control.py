from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research import kis_daily_l2_logistic_control as control


def test_control_reuses_the_frozen_qqq_spy_completed_bar_contract() -> None:
    prepared = control.build_kis_daily_l2_logistic_control_input(_catalog(count=180))

    assert prepared.campaign.campaign_id == control.KIS_DAILY_L2_LOGISTIC_CONTROL_ID
    assert tuple(prepared.sequence_input.catalog.bars_by_symbol) == ("QQQ", "SPY")
    assert prepared.campaign.naive_baselines == (
        "always_long",
        "previous_bar_direction",
        "flat",
    )
    assert prepared.sequence_input.split.purge_session_count == 22
    assert all(sample.label in {0, 1} for sample in prepared.sequence_input.development_samples)
    assert all(
        sample.label is None
        for samples in prepared.sequence_input.validation_samples_by_symbol.values()
        for sample in samples
    )
    with pytest.raises(ValueError, match="hyperparameters are frozen"):
        control.KisDailyL2LogisticControlSpec(steps=161)


def test_control_preserves_the_reviewer_target_4756_session_geometry() -> None:
    prepared = control.build_kis_daily_l2_logistic_control_input(_catalog(count=4756))

    assert prepared.sequence_input.split.development_session_count == 3783
    assert prepared.sequence_input.split.purge_session_count == 22
    assert prepared.sequence_input.split.validation_session_count == 951
    assert len(prepared.sequence_input.development_samples) == 7522
    assert {
        symbol: len(samples)
        for symbol, samples in prepared.sequence_input.validation_samples_by_symbol.items()
    } == {"QQQ": 465, "SPY": 465}


def test_validation_suffix_cannot_change_the_development_fit() -> None:
    baseline = control.build_kis_daily_l2_logistic_control_input(_catalog(count=180))
    shifted = control.build_kis_daily_l2_logistic_control_input(
        _catalog(count=180, qqq_price_shift_start=145, qqq_price_shift=Decimal("50"))
    )

    baseline_model = control.fit_kis_daily_l2_logistic_control(baseline)
    shifted_model = control.fit_kis_daily_l2_logistic_control(shifted)

    assert (
        baseline.sequence_input.development_input_hash
        == shifted.sequence_input.development_input_hash
    )
    assert baseline.sequence_input.standardizer.standardizer_hash == (
        shifted.sequence_input.standardizer.standardizer_hash
    )
    assert (
        baseline.sequence_input.validation_input_hash
        != shifted.sequence_input.validation_input_hash
    )
    assert baseline_model.parameter_hash == shifted_model.parameter_hash
    assert baseline_model.development_input_hash == baseline.sequence_input.development_input_hash


def test_control_is_deterministic_offline_local_paper_and_never_selects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    first = control.run_kis_daily_l2_logistic_control(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cpu-a",
        repo_root=repo_root,
    )
    second = control.run_kis_daily_l2_logistic_control(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="cpu-b",
        repo_root=repo_root,
    )

    summary = json.loads(first.summary_path.read_text(encoding="utf-8"))
    assert first.precommit_hash == second.precommit_hash
    assert first.model.parameter_hash == second.model.parameter_hash
    assert [cell.prediction_hash for cell in first.replay_cells] == [
        cell.prediction_hash for cell in second.replay_cells
    ]
    assert [cell.symbol for cell in first.replay_cells] == ["QQQ", "SPY"]
    assert len(first.baseline_cells) == 6
    assert {
        (cell.symbol, cell.baseline_id) for cell in first.baseline_cells
    } == {
        (symbol, baseline)
        for symbol in ("QQQ", "SPY")
        for baseline in ("flat", "always_long", "previous_bar_direction")
    }
    assert all(cell.replay.fill_source == LOCAL_PAPER_SOURCE for cell in first.replay_cells)
    assert all(
        cell.replay.replay_evidence.fill_source == LOCAL_PAPER_SOURCE
        for cell in first.replay_cells
    )
    assert all(cell.replay.fill_source == LOCAL_PAPER_SOURCE for cell in first.baseline_cells)
    assert all(
        cell.replay.replay_evidence.fill_source == LOCAL_PAPER_SOURCE
        for cell in first.baseline_cells
    )
    always_long_cells = [
        cell for cell in first.baseline_cells if cell.baseline_id == "always_long"
    ]
    assert len(always_long_cells) == 2
    assert all(cell.replay.result.trades for cell in always_long_cells)
    assert all(len(cell.replay.result.trades) % 2 == 0 for cell in always_long_cells)
    assert first.precommit_path.is_relative_to(artifact_root)
    assert first.model_path.is_relative_to(artifact_root)
    assert first.summary_path.is_relative_to(artifact_root)
    assert not first.summary_path.is_relative_to(repo_root)
    assert summary["mode"] == "offline_cpu_local_paper"
    assert summary["validation"]["labels_materialized_for_fit"] is False
    assert summary["reporting"] == {
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "sealed_holdout_materialized": False,
        "selection_allowed": False,
        "winner": None,
    }
    assert summary["artifact_policy"]["raw_market_data_written"] is False
    assert summary["model"]["spec"]["optimizer"] == "deterministic_full_batch_gradient_descent"
    assert summary["replay_sizing"] == {"starting_cash": "10000", "quantity": "1"}
    assert json.loads(first.precommit_path.read_text(encoding="utf-8"))["replay_sizing"] == {
        "starting_cash": "10000",
        "quantity": "1",
    }


def test_control_rejects_repository_artifacts(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        control.run_kis_daily_l2_logistic_control(
            _catalog(count=180),
            artifact_root=repo_root / "model-artifacts",
            run_label="bad-root",
            repo_root=repo_root,
        )


def test_control_rejects_artifact_root_inside_the_module_repository_when_repo_is_spoofed(
    tmp_path: Path,
) -> None:
    spoofed_repo_root = tmp_path / "unrelated-repo"
    spoofed_repo_root.mkdir()
    module_repo_root = Path(control.__file__).resolve().parents[3]

    with pytest.raises(ValueError, match="outside the Git workspace"):
        control.run_kis_daily_l2_logistic_control(
            _catalog(count=180),
            artifact_root=module_repo_root / "unit-artifacts",
            run_label="spoofed-root",
            repo_root=spoofed_repo_root,
        )


def test_control_checks_resolved_artifact_children_against_both_repository_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    checked: list[tuple[Path, Path]] = []
    original = control._reject_repo_path

    def record(path: Path, *, repo_root: Path) -> None:
        checked.append((Path(path), Path(repo_root)))
        original(path, repo_root=repo_root)

    monkeypatch.setattr(control, "_reject_repo_path", record)
    control.run_kis_daily_l2_logistic_control(
        _catalog(count=180),
        artifact_root=artifact_root,
        run_label="contained",
        repo_root=repo_root,
    )

    control_root = (artifact_root / control.KIS_DAILY_L2_LOGISTIC_CONTROL_ID).resolve()
    output_dir = (control_root / "contained").resolve()
    protected_roots = {repo_root.resolve(), control._MODULE_REPOSITORY_ROOT.resolve()}
    for protected_path in (control_root, output_dir):
        for protected_root in protected_roots:
            assert (protected_path, protected_root) in checked


@pytest.mark.parametrize("run_label", (".", "..", "../escape", "bad label", "x" * 81))
def test_control_rejects_unsafe_artifact_run_labels(tmp_path: Path, run_label: str) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"

    with pytest.raises(ValueError, match="run_label is invalid"):
        control.run_kis_daily_l2_logistic_control(
            _catalog(count=180),
            artifact_root=artifact_root,
            run_label=run_label,
            repo_root=repo_root,
        )

    assert not artifact_root.exists()


def test_control_rejects_non_validation_or_non_completed_prediction_windows() -> None:
    prepared = control.build_kis_daily_l2_logistic_control_input(_catalog(count=180))
    fitted = control.fit_kis_daily_l2_logistic_control(prepared)
    symbol = "QQQ"
    sample = prepared.sequence_input.validation_samples_by_symbol[symbol][0]
    decision_model = control._KisDailyL2LogisticDecisionModel(
        symbol=symbol,
        samples_by_decision_end={sample.decision_end: sample},
        probabilities_by_decision_end={sample.decision_end: 0.5},
        precommit_hash="sha256:" + "e" * 64,
        model_parameter_hash=fitted.parameter_hash,
    )
    bars = prepared.sequence_input.catalog.bars_by_symbol[symbol].bars
    validation_window = [
        bar
        for bar in bars
        if sample.history_start <= bar.start_ts <= sample.decision_start
    ]
    assert len(validation_window) == control.KIS_DAILY_SEQUENCE_LENGTH

    with pytest.raises(ValueError, match="future or cross-phase data"):
        decision_model.predict(
            [*validation_window[:-1], replace(validation_window[-1], complete=False)]
        )
    with pytest.raises(ValueError, match="future or cross-phase data"):
        decision_model.predict(
            [
                replace(
                    validation_window[0],
                    start_ts=validation_window[0].start_ts + timedelta(days=1),
                )
            ]
            + validation_window[1:]
        )
    with pytest.raises(ValueError, match="non-validation decision"):
        decision_model.predict(list(bars[: control.KIS_DAILY_SEQUENCE_LENGTH]))


def _catalog(
    *,
    count: int,
    qqq_price_shift_start: int | None = None,
    qqq_price_shift: Decimal = Decimal("0"),
) -> KisPaperPrivateDailyCatalog:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    sessions = tuple((start + timedelta(days=index)).date() for index in range(count))
    qqq_bars: list[Bar] = []
    spy_bars: list[Bar] = []
    for index in range(count):
        timestamp = start + timedelta(days=index)
        later_shift = (
            qqq_price_shift
            if qqq_price_shift_start is not None and index >= qqq_price_shift_start
            else Decimal("0")
        )
        qqq_open = Decimal("100") + Decimal(index) / Decimal("1000") + later_shift
        spy_open = Decimal("200") + Decimal(index) / Decimal("2000")
        qqq_bars.append(_bar(symbol="QQQ", start_ts=timestamp, opened=qqq_open))
        spy_bars.append(_bar(symbol="SPY", start_ts=timestamp, opened=spy_open))
    source_hash = "b" if qqq_price_shift_start is None else "c"
    dataset_hash = "sha256:" + source_hash * 64
    source_path = Path(f"C:/unit-market-data/kis-daily-l2-{source_hash}-index.json")
    return KisPaperPrivateDailyCatalog(
        dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "d" * 64,
        index_path=source_path,
        source_root=source_path.parent,
        adjustment_mode=KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(
            {
                "QQQ": _cataloged_bars_from_verified_loader(
                    dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
                    dataset_hash=dataset_hash,
                    source_path=source_path,
                    bars=tuple(qqq_bars),
                ),
                "SPY": _cataloged_bars_from_verified_loader(
                    dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
                    dataset_hash=dataset_hash,
                    source_path=source_path,
                    bars=tuple(spy_bars),
                ),
            }
        ),
        common_sessions=sessions,
        raw_price_limitations=(
            "MODP=0_unadjusted",
            "corporate_action_semantics_not_qualified",
        ),
    )


def _bar(*, symbol: str, start_ts: datetime, opened: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("1"),
        low=opened - Decimal("1"),
        close=opened,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "KIS daily L2 logistic control must remain offline and credential-free"
        )

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)

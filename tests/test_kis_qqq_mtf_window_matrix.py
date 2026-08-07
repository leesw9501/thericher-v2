from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_qqq_mtf_resampling_mechanics as mtf_mechanics
from thericher_v2.data import kis_qqq_mtf_window_feasibility as window_feasibility
from thericher_v2.data import kis_qqq_mtf_window_matrix as window_matrix
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session

_SESSION_DATES = (
    date(2026, 6, 22),
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
)
_LATER_SESSION_DATE = date(2026, 7, 21)
_EXPECTED_COUNTS = {
    "short": (300, 60, 60, 40, 40),
    "kis_baseline": (600, 120, 60, 40, 40),
    "one_hour": (1200, 240, 120, 40, 40),
    "medium": (1800, 360, 240, 40, 40),
    "long": (2400, 720, 240, 40, 40),
    "extended": (3600, 720, 360, 40, 40),
}


def test_window_matrix_is_external_aggregate_only_and_matches_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    mechanics_receipt, baseline_receipt = _parent_receipts(catalog, tmp_path, "r1")

    run = window_matrix.run_kis_qqq_mtf_window_matrix(
        catalog,
        mechanics_receipt=mechanics_receipt,
        baseline_receipt=baseline_receipt,
        artifact_root=tmp_path / "matrix-artifacts",
        run_label="matrix-r1",
    )

    assert run.status == "complete"
    assert run.eligible_session_count == 20
    assert run.input_unavailable_reason is None
    assert tuple(profile.profile_id for profile in run.profiles) == tuple(_EXPECTED_COUNTS)
    assert _counts_by_profile(run) == _EXPECTED_COUNTS
    assert all(
        item.terminal_partial_exclusion_count == 20
        for profile in run.profiles
        for item in profile.geometry
        if item.timeframe in (Timeframe.H1, Timeframe.H3)
    )
    assert all(
        item.terminal_partial_exclusion_count == 0
        for profile in run.profiles
        for item in profile.geometry
        if item.timeframe not in (Timeframe.H1, Timeframe.H3)
    )
    baseline = next(profile for profile in run.profiles if profile.profile_id == "kis_baseline")
    assert baseline.geometry == baseline_receipt.geometry

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_materialization"
    assert precommit["contract"]["parent_receipts"] == {
        "baseline_window": {
            "contract_hash": baseline_receipt.contract_hash,
            "feasibility_id": window_feasibility.KIS_QQQ_MTF_WINDOW_FEASIBILITY_ID,
        },
        "mechanics": {
            "contract_hash": mechanics_receipt.contract_hash,
            "mechanics_id": mtf_mechanics.KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
        },
    }
    ordered_profiles = precommit["contract"]["profile_catalog"]["ordered_profiles"]
    assert [item["profile_id"] for item in ordered_profiles] == list(_EXPECTED_COUNTS)
    assert summary["limits"]["predictive_campaign_allowed"] is False
    assert summary["limits"]["local_paper_input_allowed"] is False
    assert summary["artifact_policy"] == {
        "broker_called": False,
        "credential_read": False,
        "network_called": False,
        "raw_market_data_written": False,
        "raw_price_values_retained": False,
        "repo_storage_allowed": False,
        "root": str(tmp_path / "matrix-artifacts"),
    }
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert '"price"' not in serialized
    assert '"close"' not in serialized
    assert "KIS_PAPER_" not in serialized


def test_window_matrix_rejects_shifted_selected_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog(session_dates=(*_SESSION_DATES, _LATER_SESSION_DATE))
    mechanics_receipt, baseline_receipt = _parent_receipts(catalog, tmp_path, "shifted")
    missing_start = _session_window(_SESSION_DATES[0]).open_ts + timedelta(minutes=350)
    shifted = _catalog_from_bars(
        catalog,
        tuple(bar for bar in catalog.bars if bar.start_ts != missing_start),
    )

    run = window_matrix.run_kis_qqq_mtf_window_matrix(
        shifted,
        mechanics_receipt=mechanics_receipt,
        baseline_receipt=baseline_receipt,
        artifact_root=tmp_path / "matrix-artifacts",
        run_label="matrix-shifted",
    )

    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "mechanics_source_binding_mismatch"
    assert all(
        all(item.completed_window_bar_count == 0 for item in profile.geometry)
        for profile in run.profiles
    )


def test_window_matrix_ignores_post_cutoff_values_after_parent_rebinding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    changed_start = _session_window(_SESSION_DATES[4]).open_ts + timedelta(minutes=360)
    changed = _catalog_from_bars(
        catalog,
        tuple(
            replace(bar, close=Decimal("250"), high=Decimal("250"))
            if bar.start_ts == changed_start
            else bar
            for bar in catalog.bars
        ),
        dataset_hash="sha256:" + "b" * 64,
    )
    original_mechanics, original_baseline = _parent_receipts(catalog, tmp_path, "original")
    changed_mechanics, changed_baseline = _parent_receipts(changed, tmp_path, "changed")

    original = window_matrix.run_kis_qqq_mtf_window_matrix(
        catalog,
        mechanics_receipt=original_mechanics,
        baseline_receipt=original_baseline,
        artifact_root=tmp_path / "matrix-original",
        run_label="matrix-original",
    )
    changed_run = window_matrix.run_kis_qqq_mtf_window_matrix(
        changed,
        mechanics_receipt=changed_mechanics,
        baseline_receipt=changed_baseline,
        artifact_root=tmp_path / "matrix-changed",
        run_label="matrix-changed",
    )

    assert original.status == changed_run.status == "complete"
    assert original.contract_hash != changed_run.contract_hash
    assert original.baseline_contract_hash != changed_run.baseline_contract_hash
    assert original.profiles == changed_run.profiles


def test_window_matrix_rejects_a_mismatched_baseline_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    mechanics_receipt, baseline_receipt = _parent_receipts(catalog, tmp_path, "mismatch")
    other_catalog = _catalog(dataset_hash="sha256:" + "c" * 64)
    _, mismatched_baseline = _parent_receipts(other_catalog, tmp_path, "mismatch-other")

    run = window_matrix.run_kis_qqq_mtf_window_matrix(
        catalog,
        mechanics_receipt=mechanics_receipt,
        baseline_receipt=mismatched_baseline,
        artifact_root=tmp_path / "matrix-artifacts",
        run_label="matrix-mismatched-baseline",
    )

    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "baseline_source_binding_mismatch"


def test_window_matrix_rejects_a_forged_in_memory_parent_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    mechanics_receipt, baseline_receipt = _parent_receipts(catalog, tmp_path, "forged")
    forged_baseline = replace(baseline_receipt, source_input_hash="sha256:" + "d" * 64)

    with pytest.raises(ValueError, match="requires externally reattested parent receipts"):
        window_matrix.run_kis_qqq_mtf_window_matrix(
            catalog,
            mechanics_receipt=mechanics_receipt,
            baseline_receipt=forged_baseline,
            artifact_root=tmp_path / "matrix-artifacts",
            run_label="matrix-forged-parent",
        )

    assert not (tmp_path / "matrix-artifacts").exists()


def test_baseline_receipt_loader_rejects_a_tampered_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    mechanics_receipt = _mechanics_receipt(catalog, tmp_path, "tampered")
    baseline_run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        catalog,
        mechanics_receipt=mechanics_receipt,
        artifact_root=tmp_path / "baseline-artifacts",
        run_label="baseline-tampered",
    )
    precommit = json.loads(baseline_run.precommit_path.read_text(encoding="utf-8"))
    precommit["contract"]["unexpected"] = "tampered"
    baseline_run.precommit_path.write_text(
        json.dumps(precommit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="QQQ MTF window feasibility receipt is invalid"):
        window_feasibility.load_kis_qqq_mtf_window_feasibility_receipt(
            precommit_path=baseline_run.precommit_path,
            summary_path=baseline_run.summary_path,
        )


def test_baseline_receipt_loader_rejects_a_git_workspace_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    mechanics_receipt = _mechanics_receipt(catalog, tmp_path, "baseline-repo")
    baseline_run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        catalog,
        mechanics_receipt=mechanics_receipt,
        artifact_root=tmp_path / "baseline-artifacts",
        run_label="baseline-repo-path",
    )

    with pytest.raises(ValueError, match="must stay outside the Git workspace"):
        window_feasibility.load_kis_qqq_mtf_window_feasibility_receipt(
            precommit_path=baseline_run.precommit_path,
            summary_path=baseline_run.summary_path,
            repo_root=tmp_path,
        )


def test_window_matrix_rejects_a_repo_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    mechanics_receipt, baseline_receipt = _parent_receipts(catalog, tmp_path, "repo-root")

    with pytest.raises(ValueError, match="artifact_root must be outside the Git workspace"):
        window_matrix.run_kis_qqq_mtf_window_matrix(
            catalog,
            mechanics_receipt=mechanics_receipt,
            baseline_receipt=baseline_receipt,
            artifact_root=window_matrix._REPOSITORY_ROOT / "generated-matrix-artifacts",
            run_label="matrix-reject-root",
        )


def _counts_by_profile(
    run: window_matrix.KisQqqMtfWindowMatrixRun,
) -> dict[str, tuple[int, int, int, int, int]]:
    return {
        profile.profile_id: tuple(
            item.completed_window_bar_count for item in profile.geometry
        )
        for profile in run.profiles
    }


def _parent_receipts(
    catalog: CatalogedBars,
    tmp_path: Path,
    run_label: str,
) -> tuple[
    window_feasibility.KisQqqMtfMechanicsReceipt,
    window_feasibility.KisQqqMtfWindowFeasibilityReceipt,
]:
    mechanics_receipt = _mechanics_receipt(catalog, tmp_path, run_label)
    baseline_run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        catalog,
        mechanics_receipt=mechanics_receipt,
        artifact_root=tmp_path / "baseline-artifacts",
        run_label=f"baseline-{run_label}",
    )
    assert baseline_run.status == "complete"
    return mechanics_receipt, window_feasibility.load_kis_qqq_mtf_window_feasibility_receipt(
        precommit_path=baseline_run.precommit_path,
        summary_path=baseline_run.summary_path,
    )


def _mechanics_receipt(
    catalog: CatalogedBars,
    tmp_path: Path,
    run_label: str,
) -> window_feasibility.KisQqqMtfMechanicsReceipt:
    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        catalog,
        artifact_root=tmp_path / "mechanics-artifacts",
        run_label=f"mechanics-{run_label}",
    )
    assert run.status == "complete"
    return window_feasibility.load_kis_qqq_mtf_mechanics_receipt(
        precommit_path=run.precommit_path,
        summary_path=run.summary_path,
    )


def _catalog(
    *,
    session_dates: tuple[date, ...] = _SESSION_DATES,
    dataset_hash: str = "sha256:" + "a" * 64,
) -> CatalogedBars:
    bars = tuple(
        bar for session_date in session_dates for bar in _session_bars(session_date)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.matrix-unit-v1",
        dataset_hash=dataset_hash,
        source_path=Path("C:/external/kis-index.json"),
        bars=bars,
    )


def _catalog_from_bars(
    catalog: CatalogedBars,
    bars: tuple[Bar, ...],
    *,
    dataset_hash: str | None = None,
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash if dataset_hash is None else dataset_hash,
        source_path=catalog.source_path,
        bars=bars,
    )


def _session_bars(session_date: date) -> tuple[Bar, ...]:
    session = _session_window(session_date)
    return tuple(
        Bar(
            symbol="QQQ",
            market="US",
            timeframe=Timeframe.M1,
            start_ts=session.open_ts + timedelta(minutes=minute),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
        )
        for minute in range(390)
    )


def _session_window(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None
    return session.window


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(os, "getenv", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)

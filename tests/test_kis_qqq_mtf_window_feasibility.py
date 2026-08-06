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
from thericher_v2.data import (
    kis_qqq_mtf_resampling_mechanics as mtf_mechanics,
)
from thericher_v2.data import (
    kis_qqq_mtf_window_feasibility as window_feasibility,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

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


def test_window_feasibility_is_external_aggregate_only_and_causal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    receipt = _mechanics_receipt(catalog, tmp_path, "mechanics-r1")

    run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        catalog,
        mechanics_receipt=receipt,
        artifact_root=tmp_path / "window-artifacts",
        run_label="window-r1",
    )

    assert run.status == "complete"
    assert run.eligible_session_count == 20
    assert run.input_unavailable_reason is None
    geometry = {item.timeframe: item for item in run.geometry}
    assert _shape(geometry[Timeframe.M1]) == (30, 600, 0)
    assert _shape(geometry[Timeframe.M5]) == (6, 120, 0)
    assert _shape(geometry[Timeframe.M10]) == (3, 60, 0)
    assert _shape(geometry[Timeframe.H1]) == (2, 40, 20)
    assert _shape(geometry[Timeframe.H3]) == (2, 40, 20)
    assert all(item.causal_window_digest.startswith("sha256:") for item in geometry.values())
    assert (
        geometry[Timeframe.H1].causal_window_digest
        != geometry[Timeframe.H3].causal_window_digest
    )

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_materialization"
    assert precommit["contract"]["source_mechanics"] == {
        "contract_hash": receipt.contract_hash,
        "mechanics_id": mtf_mechanics.KIS_QQQ_MTF_RESAMPLING_MECHANICS_ID,
    }
    assert precommit["contract"]["profile"] == {
        "all_selected_window_ends_equal_cutoff": True,
        "catalog_sha256": summary["profile"]["catalog_sha256"],
        "cutoff": "15:30 America/New_York",
        "lookbacks": {"10m": 3, "1h": 2, "1m": 30, "3h": 2, "5m": 6},
        "profile_id": "kis_baseline",
    }
    assert summary["limits"]["predictive_campaign_allowed"] is False
    assert summary["limits"]["local_paper_input_allowed"] is False
    assert summary["artifact_policy"] == {
        "broker_called": False,
        "credential_read": False,
        "network_called": False,
        "raw_market_data_written": False,
        "raw_price_values_retained": False,
        "repo_storage_allowed": False,
        "root": str(tmp_path / "window-artifacts"),
    }
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert '"price"' not in serialized
    assert '"close"' not in serialized
    assert "KIS_PAPER_" not in serialized


def test_window_feasibility_rejects_an_incomplete_m1_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    receipt = _mechanics_receipt(catalog, tmp_path, "mechanics-r2")
    missing_start = _session_window(_SESSION_DATES[6]).open_ts + timedelta(minutes=340)
    incomplete = _catalog_from_bars(
        catalog,
        tuple(
            replace(bar, complete=False) if bar.start_ts == missing_start else bar
            for bar in catalog.bars
        ),
    )

    run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        incomplete,
        mechanics_receipt=receipt,
        artifact_root=tmp_path / "window-artifacts",
        run_label="window-incomplete",
    )

    assert run.status == "input_unavailable"
    assert run.eligible_session_count == 0
    assert run.input_unavailable_reason == "insufficient_complete_regular_sessions"
    assert all(_shape(item)[1:] == (0, 0) for item in run.geometry)


def test_window_feasibility_rejects_a_shifted_session_set_without_cross_session_carry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog(session_dates=(*_SESSION_DATES, _LATER_SESSION_DATE))
    receipt = _mechanics_receipt(catalog, tmp_path, "mechanics-r3")
    missing_start = _session_window(_SESSION_DATES[0]).open_ts + timedelta(minutes=350)
    shifted = _catalog_from_bars(
        catalog,
        tuple(bar for bar in catalog.bars if bar.start_ts != missing_start),
    )

    run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        shifted,
        mechanics_receipt=receipt,
        artifact_root=tmp_path / "window-artifacts",
        run_label="window-shifted",
    )

    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "mechanics_source_binding_mismatch"


def test_window_feasibility_ignores_post_cutoff_values_but_rebinds_parent_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    changed_start = _session_window(_SESSION_DATES[3]).open_ts + timedelta(minutes=360)
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
    original_receipt = _mechanics_receipt(catalog, tmp_path, "mechanics-r4-original")
    changed_receipt = _mechanics_receipt(changed, tmp_path, "mechanics-r4-changed")

    original = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        catalog,
        mechanics_receipt=original_receipt,
        artifact_root=tmp_path / "window-artifacts-original",
        run_label="window-original",
    )
    changed_run = window_feasibility.run_kis_qqq_mtf_window_feasibility(
        changed,
        mechanics_receipt=changed_receipt,
        artifact_root=tmp_path / "window-artifacts-changed",
        run_label="window-changed",
    )

    assert original.status == changed_run.status == "complete"
    assert original.contract_hash != changed_run.contract_hash
    assert original.mechanics_contract_hash != changed_run.mechanics_contract_hash
    assert original.geometry == changed_run.geometry


def test_window_cutoff_tracks_eastern_time_across_dst() -> None:
    summer = _session_window(date(2026, 7, 6))
    winter = _session_window(date(2026, 1, 5))

    summer_cutoff = window_feasibility._session_cutoff(summer.open_ts)
    winter_cutoff = window_feasibility._session_cutoff(winter.open_ts)

    assert summer_cutoff.astimezone(US_EQUITY_EASTERN).strftime("%H:%M") == "15:30"
    assert winter_cutoff.astimezone(US_EQUITY_EASTERN).strftime("%H:%M") == "15:30"
    assert summer_cutoff.hour == 19
    assert winter_cutoff.hour == 20


def test_window_feasibility_rejects_a_repo_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    receipt = _mechanics_receipt(catalog, tmp_path, "mechanics-r5")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="artifact_root must be outside the Git workspace"):
        window_feasibility.run_kis_qqq_mtf_window_feasibility(
            catalog,
            mechanics_receipt=receipt,
            artifact_root=window_feasibility._REPOSITORY_ROOT / "generated-window-artifacts",
            run_label="window-reject-root",
        )


def test_mechanics_receipt_rejects_a_tampered_frozen_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        catalog,
        artifact_root=tmp_path / "mechanics-artifacts",
        run_label="mechanics-tampered",
    )
    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    precommit["contract"]["unexpected"] = "tampered"
    run.precommit_path.write_text(
        json.dumps(precommit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="QQQ MTF mechanics receipt is invalid"):
        window_feasibility.load_kis_qqq_mtf_mechanics_receipt(
            precommit_path=run.precommit_path,
            summary_path=run.summary_path,
        )


def test_mechanics_receipt_rejects_a_git_workspace_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        catalog,
        artifact_root=tmp_path / "mechanics-artifacts",
        run_label="mechanics-repo-path",
    )

    with pytest.raises(ValueError, match="must stay outside the Git workspace"):
        window_feasibility.load_kis_qqq_mtf_mechanics_receipt(
            precommit_path=run.precommit_path,
            summary_path=run.summary_path,
            repo_root=tmp_path,
        )


def _shape(value: window_feasibility.QqqMtfWindowGeometry) -> tuple[int, int, int]:
    return (
        value.lookback,
        value.completed_window_bar_count,
        value.terminal_partial_exclusion_count,
    )


def _mechanics_receipt(
    catalog: CatalogedBars,
    tmp_path: Path,
    run_label: str,
) -> window_feasibility.KisQqqMtfMechanicsReceipt:
    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        catalog,
        artifact_root=tmp_path / "mechanics-artifacts",
        run_label=run_label,
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
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.window-unit-v1",
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

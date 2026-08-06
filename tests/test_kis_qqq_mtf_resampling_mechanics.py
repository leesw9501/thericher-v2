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
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session

_SESSION_DATES = (
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
    date(2026, 7, 21),
)
_LATER_SESSION_DATE = date(2026, 7, 22)


def test_mtf_mechanics_is_external_aggregate_only_and_session_aligned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)

    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        _catalog(),
        artifact_root=tmp_path / "model-artifacts",
        run_label="unit-r1",
    )

    assert run.status == "complete"
    assert run.session_count == 20
    assert run.input_unavailable_reason is None
    mechanics = {item.timeframe: item for item in run.timeframe_mechanics}
    assert _shape(mechanics[Timeframe.M1]) == (7800, 0, 0)
    assert _shape(mechanics[Timeframe.M5]) == (1560, 0, 0)
    assert _shape(mechanics[Timeframe.M10]) == (780, 0, 0)
    assert _shape(mechanics[Timeframe.H1]) == (120, 0, 20)
    assert _shape(mechanics[Timeframe.H3]) == (40, 0, 20)
    assert all(item.result_digest.startswith("sha256:") for item in mechanics.values())

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_materialization"
    assert precommit["contract"]["source"]["selection"] == (
        "first_20_complete_regular_sessions_ascending_within_2026_scope"
    )
    assert precommit["contract"]["source"]["calendar_scope"] == "2026"
    assert precommit["contract"]["source"]["causal_completed_m1_prefix_commitment"].startswith(
        "sha256:"
    )
    assert precommit["contract"]["resampling"] == {
        "bucket_anchor": "declared_regular_session_open",
        "cross_session_carry_allowed": False,
        "future_bars_used": False,
        "partial_bucket_policy": "explicitly_skip_terminal_partial_bucket",
        "source_timeframe": "1m",
        "target_timeframes": ["1m", "5m", "10m", "1h", "3h"],
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
        "root": str(tmp_path / "model-artifacts"),
    }
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert '"price"' not in serialized
    assert '"close"' not in serialized
    assert "KIS_PAPER_" not in serialized


def test_mtf_mechanics_rejects_an_incomplete_m1_session_before_resampling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    missing_start = _session_window(_SESSION_DATES[4]).open_ts + timedelta(minutes=100)
    incomplete = _catalog_from_bars(
        catalog,
        tuple(
            replace(bar, complete=False) if bar.start_ts == missing_start else bar
            for bar in catalog.bars
        ),
    )

    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        incomplete,
        artifact_root=tmp_path / "model-artifacts",
        run_label="unit-incomplete-m1",
    )

    assert run.status == "input_unavailable"
    assert run.session_count == 0
    assert run.input_unavailable_reason == "insufficient_complete_regular_sessions"
    assert all(_shape(item) == (0, 0, 0) for item in run.timeframe_mechanics)
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert summary["input_unavailable_reason"] == "insufficient_complete_regular_sessions"
    assert summary["artifact_policy"]["network_called"] is False


def test_mtf_mechanics_rejects_non_qqq_nas_kis_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)

    run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        _catalog(dataset_id="sample.qqq.us.m1.v1"),
        artifact_root=tmp_path / "model-artifacts",
        run_label="unit-wrong-source",
    )

    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "invalid_catalog"


def test_mtf_mechanics_preserves_selected_prefix_when_later_catalog_data_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog(session_dates=(*_SESSION_DATES, _LATER_SESSION_DATE))
    changed = _catalog_from_bars(
        catalog,
        tuple(
            replace(bar, close=Decimal("250"), high=Decimal("250"))
            if bar.start_ts == _session_window(_LATER_SESSION_DATE).open_ts
            else bar
            for bar in catalog.bars
        ),
        dataset_hash="sha256:" + "b" * 64,
    )

    original_run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        catalog,
        artifact_root=tmp_path / "model-artifacts-original",
        run_label="unit-original",
    )
    changed_run = mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
        changed,
        artifact_root=tmp_path / "model-artifacts-changed",
        run_label="unit-changed",
    )

    original_precommit = json.loads(original_run.precommit_path.read_text(encoding="utf-8"))
    changed_precommit = json.loads(changed_run.precommit_path.read_text(encoding="utf-8"))
    assert original_run.contract_hash != changed_run.contract_hash
    assert (
        original_precommit["contract"]["source"]["dataset_hash"]
        != changed_precommit["contract"]["source"]["dataset_hash"]
    )
    assert (
        original_precommit["contract"]["source"]["selected_session_dates_sha256"]
        == changed_precommit["contract"]["source"]["selected_session_dates_sha256"]
    )
    assert (
        original_precommit["contract"]["source"]["causal_completed_m1_prefix_commitment"]
        == changed_precommit["contract"]["source"]["causal_completed_m1_prefix_commitment"]
    )
    assert original_run.timeframe_mechanics == changed_run.timeframe_mechanics
    input_data = mtf_mechanics.prepare_kis_paper_intraday_feature_input(
        catalog,
        session_dates=_SESSION_DATES,
    )
    h3 = mtf_mechanics.resample_verified_kis_paper_private_intraday_catalog(
        input_data.catalog,
        timeframe=Timeframe.H3,
        session=input_data.session_windows[0],
    )
    assert len(h3.bars) == 2
    assert h3.skipped_bucket_starts == (
        input_data.session_windows[0].open_ts + timedelta(hours=6),
    )


def test_mtf_mechanics_rejects_a_repo_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="artifact_root must be outside the Git workspace"):
        mtf_mechanics.run_kis_qqq_mtf_resampling_mechanics(
            _catalog(),
            artifact_root=mtf_mechanics._REPOSITORY_ROOT / "generated-mtf-artifacts",
            run_label="unit-reject-root",
        )


def _shape(value: mtf_mechanics.QqqMtfTimeframeMechanics) -> tuple[int, int, int]:
    return (
        value.completed_bucket_count,
        value.incomplete_bucket_count,
        value.terminal_partial_bucket_count,
    )


def _catalog(
    *,
    session_dates: tuple[date, ...] = _SESSION_DATES,
    dataset_id: str = "kis.paper.private.intraday.qqq.nas.m1.unit-v1",
    dataset_hash: str = "sha256:" + "a" * 64,
) -> CatalogedBars:
    bars = tuple(
        bar for session_date in session_dates for bar in _session_bars(session_date)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
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

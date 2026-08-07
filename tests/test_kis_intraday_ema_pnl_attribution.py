from __future__ import annotations

import json
import os
import shutil
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution import replay_local_paper_realized_pnl
from thericher_v2.research import kis_intraday_ema_pnl_attribution as attribution
from thericher_v2.research import kis_intraday_ema_replay as ema_replay

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


def test_attribution_reattests_parent_and_writes_aggregate_local_paper_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "complete")

    run = attribution.run_source_local_ema_local_paper_pnl_attribution(
        catalog,
        parent_receipt=parent,
        artifact_root=tmp_path / "attribution-artifacts",
        run_label="attribution-r1",
    )

    assert run.status == "complete"
    assert run.session_count == 20
    assert run.input_unavailable_reason is None
    assert run.aggregate.local_paper_fill_count == parent.mechanics.local_paper_fill_count
    assert run.aggregate.open_quantity == 0
    assert run.aggregate.closed_segment_count > 0
    assert run.aggregate.gross_delta - run.aggregate.fee_total == run.aggregate.net_delta

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_attribution"
    assert precommit["contract"]["parent_replay"]["contract_hash"] == parent.contract_hash
    assert precommit["contract"]["aggregate_metric_schema"] == [
        "closed_segment_count",
        "closed_quantity",
        "gross_delta",
        "fee_total",
        "net_delta",
        "open_quantity",
        "local_paper_fill_count",
    ]
    assert summary["replay_consistency"] == {
        "all_fills_local_paper": True,
        "all_terminal_flat": True,
        "fee_aware_identity": True,
        "parent_mechanics_match": True,
        "replay_digest": parent.mechanics.replay_digest,
    }
    assert summary["aggregate"]["open_quantity"] == "0"
    assert summary["artifact_policy"] == {
        "broker_called": False,
        "credential_read": False,
        "network_called": False,
        "raw_fill_events_retained": False,
        "raw_market_data_written": False,
        "raw_price_values_retained": False,
        "repo_storage_allowed": False,
        "root": str(tmp_path / "attribution-artifacts"),
    }
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert '"price"' not in serialized
    assert "client_order_id" not in serialized
    assert "KIS_PAPER_" not in serialized


def test_attribution_rejects_tampered_or_forged_parent_before_writing_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "tampered")
    precommit = json.loads(parent.precommit_path.read_text(encoding="utf-8"))
    precommit["contract"]["execution"]["fee_bps"] = "2"
    parent.precommit_path.write_text(json.dumps(precommit, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="EMA replay precommit is invalid"):
        attribution.run_source_local_ema_local_paper_pnl_attribution(
            catalog,
            parent_receipt=parent,
            artifact_root=tmp_path / "tampered-child",
            run_label="tampered-child",
        )
    assert not (tmp_path / "tampered-child").exists()

    parent = _parent_receipt(parent_directory, tmp_path, "forged")
    forged = replace(parent, source_dataset_hash="sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="externally reattested"):
        attribution.run_source_local_ema_local_paper_pnl_attribution(
            catalog,
            parent_receipt=forged,
            artifact_root=tmp_path / "forged-child",
            run_label="forged-child",
        )
    assert not (tmp_path / "forged-child").exists()

    parent = _parent_receipt(parent_directory, tmp_path, "summary-tamper")
    summary = json.loads(parent.summary_path.read_text(encoding="utf-8"))
    summary["mechanics"]["decision_count"] += 1
    parent.summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="externally reattested"):
        attribution.run_source_local_ema_local_paper_pnl_attribution(
            catalog,
            parent_receipt=parent,
            artifact_root=tmp_path / "summary-tamper-child",
            run_label="summary-tamper-child",
        )
    assert not (tmp_path / "summary-tamper-child").exists()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        ema_replay.load_kis_intraday_ema_replay_receipt(
            precommit_path=Path(__file__),
            summary_path=Path(__file__),
        )


def test_attribution_closes_only_mismatched_catalog_input_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    _, parent_directory = parent_context
    original = _catalog("entry_exit", session_dates=(*_SESSION_DATES, _LATER_SESSION_DATE))
    parent = _parent_receipt(parent_directory, tmp_path, "shifted-parent")
    first_session_open = _session_window(_SESSION_DATES[0]).open_ts
    missing_start = first_session_open + timedelta(minutes=100)
    shifted = _catalog_from_bars(
        original,
        tuple(bar for bar in original.bars if bar.start_ts != missing_start),
    )

    run = attribution.run_source_local_ema_local_paper_pnl_attribution(
        shifted,
        parent_receipt=parent,
        artifact_root=tmp_path / "shifted-child",
        run_label="shifted-child",
    )

    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "parent_source_binding_mismatch"
    assert run.aggregate == attribution._empty_aggregate()
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert summary["replay_consistency"]["parent_mechanics_match"] is False
    assert summary["aggregate"]["local_paper_fill_count"] == 0


def test_later_bars_cannot_change_already_closed_prefix_pnl(
    monkeypatch: pytest.MonkeyPatch,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, _ = parent_context
    expected_contract_hash = _contract_hash(catalog)
    changed_start = _session_window(_SESSION_DATES[0]).open_ts + timedelta(minutes=200)
    changed = _catalog_from_bars(
        catalog,
        tuple(
            replace(bar, open=Decimal("250"), high=Decimal("250"), close=Decimal("250"))
            if bar.start_ts == changed_start
            else bar
            for bar in catalog.bars
        ),
    )

    original_replay = ema_replay.replay_kis_intraday_session_reset_ema_local_paper(
        catalog,
        expected_contract_hash=expected_contract_hash,
    )
    changed_replay = ema_replay.replay_kis_intraday_session_reset_ema_local_paper(
        changed,
        expected_contract_hash=expected_contract_hash,
    )
    cutoff = _session_window(_SESSION_DATES[0]).open_ts + timedelta(minutes=60)
    original_prefix = tuple(
        event
        for event in original_replay.session_replays[0].events
        if event.created_at < cutoff
    )
    changed_prefix = tuple(
        event
        for event in changed_replay.session_replays[0].events
        if event.created_at < cutoff
    )

    assert tuple(event.to_record() for event in changed_prefix) == tuple(
        event.to_record() for event in original_prefix
    )
    assert replay_local_paper_realized_pnl(changed_prefix) == replay_local_paper_realized_pnl(
        original_prefix
    )


def test_attribution_rejects_foreign_fill_before_fifo_accounting(
    monkeypatch: pytest.MonkeyPatch,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = ema_replay.load_kis_intraday_ema_replay_receipt(
        precommit_path=parent_directory / "precommit.json",
        summary_path=parent_directory / "summary.json",
    )
    replay = ema_replay.replay_kis_intraday_session_reset_ema_local_paper(
        catalog,
        expected_contract_hash=parent.contract_hash,
    )
    first_session = replay.session_replays[0]
    fill_index = next(
        index for index, event in enumerate(first_session.events) if event.event_type == "fill"
    )
    foreign_fill = replace(
        first_session.events[fill_index],
        payload={
            **first_session.events[fill_index].payload,
            "source": "foreign_test_fill",
        },
    )
    foreign_session = replace(
        first_session,
        events=(
            *first_session.events[:fill_index],
            foreign_fill,
            *first_session.events[fill_index + 1 :],
        ),
    )
    foreign_replay = replace(
        replay,
        session_replays=(foreign_session, *replay.session_replays[1:]),
    )

    with pytest.raises(attribution._InputUnavailable, match="non_local_fill_detected"):
        attribution._aggregate_local_paper_pnl(foreign_replay)


def test_attribution_rejects_git_resident_output_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "git-root")

    with pytest.raises(ValueError, match="outside the Git workspace"):
        attribution.run_source_local_ema_local_paper_pnl_attribution(
            catalog,
            parent_receipt=parent,
            artifact_root=Path(__file__).resolve().parents[1] / "generated-ema-pnl-artifacts",
            run_label="reject-git-root",
        )


@pytest.fixture(scope="module")
def parent_context(tmp_path_factory: pytest.TempPathFactory) -> tuple[CatalogedBars, Path]:
    catalog = _catalog("entry_exit")
    root = tmp_path_factory.mktemp("ema-pnl-parent")
    run = ema_replay.run_kis_intraday_session_reset_ema_replay(
        catalog,
        artifact_root=root / "artifacts",
        run_label="parent",
    )
    assert run.status == "complete"
    return catalog, run.precommit_path.parent


def _parent_receipt(parent_directory: Path, tmp_path: Path, label: str):
    copied_directory = tmp_path / f"parent-{label}"
    shutil.copytree(parent_directory, copied_directory)
    return ema_replay.load_kis_intraday_ema_replay_receipt(
        precommit_path=copied_directory / "precommit.json",
        summary_path=copied_directory / "summary.json",
    )


def _catalog(
    mode: str,
    *,
    session_dates: tuple[date, ...] = _SESSION_DATES,
    dataset_hash: str = "sha256:" + "a" * 64,
) -> CatalogedBars:
    return _catalog_from_bars(
        None,
        tuple(
            bar
            for session_date in session_dates
            for bar in _session_bars(session_date, mode)
        ),
        dataset_hash=dataset_hash,
    )


def _catalog_from_bars(
    catalog: CatalogedBars | None,
    bars: tuple[Bar, ...],
    *,
    dataset_hash: str | None = None,
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=(
            "kis.paper.private.intraday.qqq.nas.m1.test"
            if catalog is None
            else catalog.dataset_id
        ),
        dataset_hash=("sha256:" + "a" * 64) if dataset_hash is None else dataset_hash,
        source_path=Path("C:/external/kis-index.json") if catalog is None else catalog.source_path,
        bars=bars,
    )


def _session_bars(session_date: date, mode: str) -> tuple[Bar, ...]:
    open_ts = datetime(session_date.year, session_date.month, session_date.day, 13, 30, tzinfo=UTC)
    return tuple(_bar(open_ts, minute, mode) for minute in range(390))


def _session_window(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None
    return session.window


def _contract_hash(catalog: CatalogedBars) -> str:
    session_dates = ema_replay.select_first_complete_kis_intraday_regular_session_dates(catalog)
    plan = ema_replay.build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=session_dates,
        campaign_id=ema_replay.KIS_INTRADAY_EMA_REPLAY_ID,
    )
    return "sha256:" + ema_replay._sha256_json(ema_replay._contract_payload(plan))


def _bar(open_ts: datetime, minute: int, mode: str) -> Bar:
    close = Decimal("100")
    if mode == "entry_exit":
        if minute == 30:
            close = Decimal("102")
        elif minute >= 31:
            close = Decimal("90")
    opening = close
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=open_ts + timedelta(minutes=minute),
        open=opening,
        high=max(opening, close),
        low=min(opening, close),
        close=close,
        volume=Decimal("1"),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(os, "getenv", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)

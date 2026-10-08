from __future__ import annotations

import json
import os
import shutil
import socket
import urllib.request
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_intraday_donchian_pnl_attribution as attribution
from thericher_v2.research import kis_intraday_donchian_replay as donchian_replay

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


def test_attribution_reattests_parent_and_writes_aggregate_local_paper_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "complete")

    run = attribution.run_source_local_qqq_donchian_local_paper_pnl_attribution(
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

    with pytest.raises(ValueError, match="Donchian replay precommit is invalid"):
        attribution.run_source_local_qqq_donchian_local_paper_pnl_attribution(
            catalog,
            parent_receipt=parent,
            artifact_root=tmp_path / "tampered-child",
            run_label="tampered-child",
        )
    assert not (tmp_path / "tampered-child").exists()

    parent = _parent_receipt(parent_directory, tmp_path, "forged")
    forged = replace(parent, source_dataset_hash="sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="externally reattested"):
        attribution.run_source_local_qqq_donchian_local_paper_pnl_attribution(
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
        attribution.run_source_local_qqq_donchian_local_paper_pnl_attribution(
            catalog,
            parent_receipt=parent,
            artifact_root=tmp_path / "summary-tamper-child",
            run_label="summary-tamper-child",
        )
    assert not (tmp_path / "summary-tamper-child").exists()


def test_attribution_closes_only_mismatched_catalog_input_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "shifted-parent")
    missing_start = catalog.bars[100].start_ts
    shifted = _catalog_from_bars(
        catalog,
        tuple(bar for bar in catalog.bars if bar.start_ts != missing_start),
    )

    run = attribution.run_source_local_qqq_donchian_local_paper_pnl_attribution(
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


def test_replay_is_deterministic_and_fifo_rejects_foreign_fills(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
    baseline_replay: donchian_replay.DonchianLocalPaperReplay,
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "deterministic")

    original = baseline_replay
    session_calls = 0
    real_session = donchian_replay._run_donchian_local_paper_evidence

    def forward_session(*args, **kwargs):
        nonlocal session_calls
        session_calls += 1
        return real_session(*args, **kwargs)

    with pytest.MonkeyPatch.context() as tracking:
        tracking.setattr(donchian_replay, "_run_donchian_local_paper_evidence", forward_session)
        repeated = donchian_replay.replay_kis_intraday_session_reset_donchian_local_paper(
            catalog,
            expected_contract_hash=parent.contract_hash,
        )
    assert donchian_replay._run_donchian_local_paper_evidence is real_session
    assert session_calls == 20
    assert repeated == original

    first_session = original.session_replays[0]
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
        original,
        session_replays=(foreign_session, *original.session_replays[1:]),
    )
    with pytest.raises(attribution._InputUnavailable, match="non_local_fill_detected"):
        attribution._aggregate_local_paper_pnl(foreign_replay)

    non_flat_session = replace(
        first_session,
        mechanics=replace(first_session.mechanics, all_terminal_flat=False),
    )
    non_flat_replay = replace(
        original,
        session_replays=(non_flat_session, *original.session_replays[1:]),
    )
    with pytest.raises(attribution._InputUnavailable, match="terminal_flattening_mismatch"):
        attribution._aggregate_local_paper_pnl(non_flat_replay)

    wrong_cash_session = replace(
        first_session,
        terminal_account=replace(
            first_session.terminal_account,
            cash=first_session.terminal_account.cash + Decimal("1"),
        ),
    )
    wrong_cash_replay = replace(
        original,
        session_replays=(wrong_cash_session, *original.session_replays[1:]),
    )
    with pytest.raises(attribution._InputUnavailable, match="fifo_accounting_mismatch"):
        attribution._aggregate_local_paper_pnl(wrong_cash_replay)


def test_attribution_rejects_git_resident_output_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_context: tuple[CatalogedBars, Path],
) -> None:
    _deny_external_access(monkeypatch)
    catalog, parent_directory = parent_context
    parent = _parent_receipt(parent_directory, tmp_path, "git-root")

    with pytest.raises(ValueError, match="outside the Git workspace"):
        attribution.run_source_local_qqq_donchian_local_paper_pnl_attribution(
            catalog,
            parent_receipt=parent,
            artifact_root=Path(__file__).resolve().parents[1] / "generated-donchian-pnl-artifacts",
            run_label="reject-git-root",
        )


@pytest.fixture(scope="module")
def _parent_replay_context(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[CatalogedBars, Path, donchian_replay.DonchianLocalPaperReplay]]:
    catalog = _catalog()
    root = tmp_path_factory.mktemp("donchian-pnl-parent")
    sessions = []
    session_dates = []
    real_session = donchian_replay._run_donchian_local_paper_evidence

    def capture_session(*args, **kwargs):
        evidence = real_session(*args, **kwargs)
        sessions.append(deepcopy(evidence))
        session_dates.append(kwargs["session"].open_ts.date())
        return evidence

    with pytest.MonkeyPatch.context() as capturing:
        _deny_external_access(capturing)
        capturing.setattr(donchian_replay, "_run_donchian_local_paper_evidence", capture_session)
        run = donchian_replay.run_kis_intraday_session_reset_donchian_replay(
            catalog,
            artifact_root=root / "artifacts",
            run_label="parent",
        )
    assert donchian_replay._run_donchian_local_paper_evidence is real_session
    assert len(sessions) == run.session_count == 20
    assert tuple(session_dates) == _SESSION_DATES
    assert run.status == "complete"
    parent = donchian_replay.load_kis_intraday_donchian_replay_receipt(
        precommit_path=run.precommit_path, summary_path=run.summary_path
    )
    baseline = donchian_replay.DonchianLocalPaperReplay(
        mechanics=donchian_replay._sum_donchian(item.mechanics for item in sessions),
        session_replays=tuple(sessions),
    )
    assert baseline.mechanics == run.donchian == parent.mechanics
    assert baseline.mechanics.replay_digest == parent.mechanics.replay_digest
    assert all(
        donchian_replay._event_digest(item.events) == item.mechanics.replay_digest
        for item in sessions
    )
    protected_baseline = deepcopy(baseline)
    parent_bytes = {path: path.read_bytes() for path in (run.precommit_path, run.summary_path)}
    yield catalog, run.precommit_path.parent, baseline
    assert baseline == protected_baseline
    assert all(path.read_bytes() == content for path, content in parent_bytes.items())


@pytest.fixture(scope="module")
def parent_context(
    _parent_replay_context: tuple[CatalogedBars, Path, donchian_replay.DonchianLocalPaperReplay],
) -> tuple[CatalogedBars, Path]:
    return _parent_replay_context[:2]


@pytest.fixture
def baseline_replay(
    _parent_replay_context: tuple[CatalogedBars, Path, donchian_replay.DonchianLocalPaperReplay],
) -> donchian_replay.DonchianLocalPaperReplay:
    return deepcopy(_parent_replay_context[2])


def test_captured_baseline_has_independent_nested_event_payloads(
    baseline_replay: donchian_replay.DonchianLocalPaperReplay,
    _parent_replay_context: tuple[CatalogedBars, Path, donchian_replay.DonchianLocalPaperReplay],
) -> None:
    shared = _parent_replay_context[2]
    independent = deepcopy(shared)
    assert baseline_replay == independent == shared
    event = next(
        event
        for event in baseline_replay.session_replays[0].events
        if event.event_type == "local_paper_portfolio_snapshot" and event.payload["positions"]
    )
    event.payload["positions"][0]["quantity"] = "synthetic_mutation"
    assert baseline_replay != independent
    assert independent == shared


def _parent_receipt(parent_directory: Path, tmp_path: Path, label: str):
    copied_directory = tmp_path / f"parent-{label}"
    shutil.copytree(parent_directory, copied_directory)
    return donchian_replay.load_kis_intraday_donchian_replay_receipt(
        precommit_path=copied_directory / "precommit.json",
        summary_path=copied_directory / "summary.json",
    )


def _catalog() -> CatalogedBars:
    return _catalog_from_bars(
        None,
        tuple(
            bar
            for session_date in _SESSION_DATES
            for bar in _session_bars(session_date)
        ),
    )


def _catalog_from_bars(
    catalog: CatalogedBars | None,
    bars: tuple[Bar, ...],
) -> CatalogedBars:
    return _cataloged_bars_from_verified_loader(
        dataset_id=(
            "kis.paper.private.intraday.qqq.nas.m1.test"
            if catalog is None
            else catalog.dataset_id
        ),
        dataset_hash=("sha256:" + "a" * 64) if catalog is None else catalog.dataset_hash,
        source_path=Path("C:/external/kis-index.json") if catalog is None else catalog.source_path,
        bars=bars,
    )


def _session_bars(session_date: date) -> tuple[Bar, ...]:
    open_ts = datetime(session_date.year, session_date.month, session_date.day, 13, 30, tzinfo=UTC)
    return tuple(_bar(open_ts, minute) for minute in range(390))


def _bar(open_ts: datetime, minute: int) -> Bar:
    close = Decimal("100")
    high = Decimal("101")
    low = Decimal("99")
    if minute == 20:
        close = Decimal("102")
        high = Decimal("102")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=open_ts + timedelta(minutes=minute),
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(os, "environ", {})

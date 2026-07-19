from __future__ import annotations

import inspect
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution import (
    EmergencyStore,
    LocalPaperBroker,
    collect_fill_source_evidence,
    replay_local_paper_account,
    target_proposal_to_order_intent,
)
from thericher_v2.execution.fill_source import FillEventArtifact
from thericher_v2.research import kis_paper_baseline
from thericher_v2.research.kis_paper_baseline import (
    KIS_PAPER_BASELINE_SCHEMA_ID,
    evaluate_kis_paper_baseline,
)
from thericher_v2.state import EventStore


def test_fixed_baseline_builds_exact_90_1m_input_and_local_resamples() -> None:
    bars = _bars(92)

    result = evaluate_kis_paper_baseline(
        bars[:90],
        symbol="QQQ",
        market="US",
        as_of=bars[89].end_ts,
    )

    assert result.baseline_input is not None
    assert len(result.baseline_input.m1_bars) == 90
    assert len(result.baseline_input.m5_bars) == 18
    assert len(result.baseline_input.m10_bars) == 9
    assert result.proposal.action == "enter"
    assert result.proposal.target_exposure == Decimal("0.05")
    assert result.proposal.feature_schema_id == KIS_PAPER_BASELINE_SCHEMA_ID
    assert result.proposal.input_status == "ready"
    assert result.proposal.valid_until == bars[89].end_ts + timedelta(minutes=10)

    source = inspect.getsource(kis_paper_baseline)
    assert "orderintent" not in source.lower()


def test_baseline_abstains_for_unusable_input() -> None:
    complete = _bars(90)
    gapped = _bars(91)
    cases = (
        (_bars(89), _bars(89)[-1].end_ts, "missing"),
        (complete, complete[-1].end_ts + timedelta(minutes=3), "stale"),
        (gapped[:40] + gapped[41:], gapped[-1].end_ts, "non_contiguous"),
        (
            [*complete[:15], replace(complete[15], complete=False), *complete[16:]],
            complete[-1].end_ts,
            "incomplete",
        ),
        ([*complete, complete[12]], complete[-1].end_ts, "duplicate"),
    )

    for bars, as_of, expected_status in cases:
        result = evaluate_kis_paper_baseline(
            bars,
            symbol="QQQ",
            market="US",
            as_of=as_of,
        )

        assert result.baseline_input is None
        assert result.proposal.action == "abstain"
        assert result.proposal.target_exposure == 0
        assert result.proposal.input_status == expected_status


def test_execution_maps_ready_target_to_replayable_local_paper_fill(tmp_path: Path) -> None:
    bars = _bars(92)
    proposal = evaluate_kis_paper_baseline(
        bars[:90],
        symbol="QQQ",
        market="US",
        as_of=bars[89].end_ts,
    ).proposal
    order = target_proposal_to_order_intent(
        proposal,
        client_order_id="kis-paper-baseline-local-1",
        current_quantity=Decimal("0"),
        maximum_quantity=Decimal("20"),
    )

    assert order is not None
    assert order.side == "buy"
    assert order.quantity == Decimal("1.00")
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    execution = broker.submit_and_fill_next_bar(
        order,
        signal_bar=bars[89],
        execution_bar=bars[90],
    )

    assert execution.fill is not None
    evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=tmp_path / "events.jsonl",
                expected_fill_count=1,
                label="baseline",
            ),
        )
    )
    assert evidence.all_fills_local_paper
    assert replay_local_paper_account(store).quantity(market="US", symbol="QQQ") == Decimal("1.00")


def test_baseline_and_local_replay_are_network_and_credential_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bars = _bars(92)

    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("baseline and local paper must stay offline")

    original_open = Path.open

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.lower().startswith(".env"):
            raise AssertionError("baseline and local paper must not read credentials")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "open", guard_open)

    proposal = evaluate_kis_paper_baseline(
        bars[:90],
        symbol="QQQ",
        market="US",
        as_of=bars[89].end_ts,
    ).proposal
    order = target_proposal_to_order_intent(
        proposal,
        client_order_id="offline-local-paper",
        current_quantity=0,
        maximum_quantity=20,
    )
    assert order is not None
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    assert broker.submit_and_fill_next_bar(order, signal_bar=bars[89], execution_bar=bars[90]).fill


def _bars(count: int) -> list[Bar]:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result: list[Bar] = []
    for index in range(count):
        open_price = Decimal("100") + Decimal(index) / Decimal("100")
        close = open_price + Decimal("0.01")
        result.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start + timedelta(minutes=index),
                open=open_price,
                high=close + Decimal("0.01"),
                low=open_price - Decimal("0.01"),
                close=close,
                volume=Decimal("1000") + Decimal(index),
                complete=True,
            )
        )
    return result

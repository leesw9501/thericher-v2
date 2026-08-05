from __future__ import annotations

import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE, LocalPaperBroker
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    prepare_local_paper_intent,
)
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.session_reset_donchian import SessionResetDonchianRule
from thericher_v2.models.session_reset_donchian_target import (
    SessionResetDonchianTargetConfig,
    propose_session_reset_donchian_target,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.state import EventStore

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CONFIG = SessionResetDonchianTargetConfig(
    symbol="QQQ",
    market="US",
    timeframe=Timeframe.M1,
    target_exposure=Decimal("0.20"),
    confidence=Decimal("0.60"),
    decision_ttl=timedelta(minutes=2),
)
_REFERENCES = DecisionReceiptReferences(
    campaign_ref="ref:" + "1" * 64,
    model_ref="ref:" + "2" * 64,
    input_manifest_ref="sha256:" + "3" * 64,
    proposal_ref="ref:" + "4" * 64,
)
_EXIT_REFERENCES = DecisionReceiptReferences(
    campaign_ref="ref:" + "1" * 64,
    model_ref="ref:" + "2" * 64,
    input_manifest_ref="sha256:" + "3" * 64,
    proposal_ref="ref:" + "5" * 64,
)


def test_breakout_replays_once_through_the_existing_local_paper_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    history = _bars(20)
    history.append(_bar(20, close=Decimal("102"), high=Decimal("102")))
    signal_bar = history[-1]
    replay_bar = _bar(21)

    proposal = propose_session_reset_donchian_target(
        history,
        session=_SESSION,
        as_of=signal_bar.end_ts,
        model_position="flat",
        rule=SessionResetDonchianRule(),
        config=_CONFIG,
    )
    receipt = receipt_from_target_exposure_proposal(proposal, references=_REFERENCES)
    prepared = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_REFERENCES.proposal_ref,
            symbol="QQQ",
            target_exposure=proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=signal_bar.end_ts,
    )

    assert (proposal.action, proposal.input_status, receipt.decision_class) == (
        "enter",
        "ready",
        "enter",
    )
    assert prepared.status == "ready"
    assert prepared.local_paper_intent is not None

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    first = broker.submit_and_fill_next_bar(
        prepared.local_paper_intent,
        signal_bar=signal_bar,
        execution_bar=replay_bar,
    )
    retried_submission = broker.submit_and_fill_next_bar(
        prepared.local_paper_intent,
        signal_bar=signal_bar,
        execution_bar=replay_bar,
    )
    replayed = broker.fill_next_bar(
        prepared.local_paper_intent.client_order_id,
        signal_bar=signal_bar,
        execution_bar=replay_bar,
    )

    assert first.fill is not None
    assert first.fill.source == LOCAL_PAPER_SOURCE
    assert first.fill.filled_at == replay_bar.start_ts
    assert (retried_submission.order_result.status, retried_submission.order_result.reason) == (
        "rejected",
        "duplicate_client_order_id",
    )
    assert retried_submission.fill is None
    assert replayed.fill == first.fill
    fills = [event for event in store.iter_events() if event.event_type == "fill"]
    assert len(fills) == 1
    assert fills[0].payload["source"] == LOCAL_PAPER_SOURCE


def test_breakdown_exits_a_replayable_donchian_local_paper_position(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    entry_history = _bars(20)
    entry_history.append(_bar(20, close=Decimal("102"), high=Decimal("102")))
    entry_signal = entry_history[-1]
    entry_replay = _bar(21)
    entry_proposal = propose_session_reset_donchian_target(
        entry_history,
        session=_SESSION,
        as_of=entry_signal.end_ts,
        model_position="flat",
        rule=SessionResetDonchianRule(),
        config=_CONFIG,
    )
    entry_receipt = receipt_from_target_exposure_proposal(
        entry_proposal,
        references=_REFERENCES,
    )
    entry_prepared = prepare_local_paper_intent(
        entry_receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_REFERENCES.proposal_ref,
            symbol="QQQ",
            target_exposure=entry_proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=entry_signal.end_ts,
    )
    assert entry_prepared.local_paper_intent is not None

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    entry = broker.submit_and_fill_next_bar(
        entry_prepared.local_paper_intent,
        signal_bar=entry_signal,
        execution_bar=entry_replay,
    )
    assert entry.fill is not None
    current_quantity = broker.account().quantity(market="US", symbol="QQQ")
    assert current_quantity == entry.fill.quantity

    exit_history = [*entry_history, *(_bar(index) for index in range(21, 31))]
    exit_history.append(_bar(31, close=Decimal("98"), low=Decimal("98")))
    exit_signal = exit_history[-1]
    exit_replay = _bar(32)
    exit_proposal = propose_session_reset_donchian_target(
        exit_history,
        session=_SESSION,
        as_of=exit_signal.end_ts,
        model_position="long" if current_quantity > 0 else "flat",
        rule=SessionResetDonchianRule(),
        config=_CONFIG,
    )
    exit_receipt = receipt_from_target_exposure_proposal(
        exit_proposal,
        references=_EXIT_REFERENCES,
    )
    exit_prepared = prepare_local_paper_intent(
        exit_receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_EXIT_REFERENCES.proposal_ref,
            symbol="QQQ",
            target_exposure=exit_proposal.target_exposure,
            current_quantity=current_quantity,
            maximum_quantity=Decimal("5"),
        ),
        as_of=exit_signal.end_ts,
    )

    assert (exit_proposal.action, exit_receipt.decision_class, exit_prepared.status) == (
        "exit",
        "exit",
        "ready",
    )
    assert exit_prepared.local_paper_intent is not None
    assert exit_prepared.local_paper_intent.quantity == current_quantity
    exit = broker.submit_and_fill_next_bar(
        exit_prepared.local_paper_intent,
        signal_bar=exit_signal,
        execution_bar=exit_replay,
    )
    replayed = broker.fill_next_bar(
        exit_prepared.local_paper_intent.client_order_id,
        signal_bar=exit_signal,
        execution_bar=exit_replay,
    )

    assert exit.fill is not None
    assert exit.fill.source == LOCAL_PAPER_SOURCE
    assert exit.fill.filled_at == exit_replay.start_ts
    assert replayed.fill == exit.fill
    assert broker.account().positions == ()
    fills = [event for event in store.iter_events() if event.event_type == "fill"]
    assert len(fills) == 2
    assert all(event.payload["source"] == LOCAL_PAPER_SOURCE for event in fills)


def test_expired_donchian_local_paper_intent_is_rejected_without_a_fill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    history = _bars(20)
    history.append(_bar(20, close=Decimal("102"), high=Decimal("102")))
    signal_bar = history[-1]
    proposal = propose_session_reset_donchian_target(
        history,
        session=_SESSION,
        as_of=signal_bar.end_ts,
        model_position="flat",
        rule=SessionResetDonchianRule(),
        config=_CONFIG,
    )
    receipt = receipt_from_target_exposure_proposal(proposal, references=_REFERENCES)
    prepared = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_REFERENCES.proposal_ref,
            symbol="QQQ",
            target_exposure=proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=signal_bar.end_ts,
    )

    assert prepared.local_paper_intent is not None
    assert prepared.local_paper_intent.valid_until == _bar(23).start_ts

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    late_submission = broker.submit_order(
        replace(
            prepared.local_paper_intent,
            client_order_id=f"{prepared.local_paper_intent.client_order_id}-late",
        ),
        submitted_at=_bar(23).start_ts,
    )
    accepted = broker.submit_order(prepared.local_paper_intent)
    restarted = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    expired_fill = restarted.fill_next_bar(
        prepared.local_paper_intent.client_order_id,
        signal_bar=_bar(22),
        execution_bar=_bar(23),
    )

    assert (late_submission.status, late_submission.reason) == ("rejected", "intent_expired")
    assert accepted.status == "accepted"
    assert (expired_fill.order_result.status, expired_fill.order_result.reason) == (
        "rejected",
        "intent_expired",
    )
    assert expired_fill.fill is None
    assert restarted.account().positions == ()
    fills = [event for event in restarted.event_store.iter_events() if event.event_type == "fill"]
    assert fills == []


def test_insufficient_history_cannot_create_a_local_paper_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    history = _bars(20)
    proposal = propose_session_reset_donchian_target(
        history,
        session=_SESSION,
        as_of=history[-1].end_ts,
        model_position="flat",
        rule=SessionResetDonchianRule(),
        config=_CONFIG,
    )
    receipt = receipt_from_target_exposure_proposal(proposal, references=_REFERENCES)
    prepared = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_REFERENCES.proposal_ref,
            symbol="QQQ",
            target_exposure=proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=history[-1].end_ts,
    )

    assert (proposal.action, proposal.input_status, receipt.decision_class) == (
        "abstain",
        "missing",
        "abstain",
    )
    assert prepared.status == "no_intent"
    assert prepared.local_paper_intent is None


def _bars(count: int) -> list[Bar]:
    return [_bar(index) for index in range(count)]


def _bar(
    minute_offset: int,
    *,
    close: Decimal = Decimal("100"),
    high: Decimal = Decimal("101"),
    low: Decimal = Decimal("99"),
) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + timedelta(minutes=minute_offset),
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Donchian local-paper replay must stay offline")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

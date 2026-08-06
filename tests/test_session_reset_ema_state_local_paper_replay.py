from __future__ import annotations

import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE, LocalPaperBroker
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    PaperDecisionBridgeResult,
    prepare_local_paper_intent,
)
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.session_reset_ema_state import EmaStatePosition, SessionResetEmaStateRule
from thericher_v2.models.session_reset_ema_state_target import (
    SessionResetEmaStateTargetConfig,
    propose_session_reset_ema_state_target,
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
_RULE = SessionResetEmaStateRule(fast_period=2, slow_period=3, tolerance=Decimal("0"))
_CONFIG = SessionResetEmaStateTargetConfig(
    symbol="QQQ",
    market="US",
    timeframe=Timeframe.M1,
    target_exposure=Decimal("0.20"),
    confidence=Decimal("0.60"),
    decision_ttl=timedelta(minutes=2),
)
_ENTRY_REFERENCES = DecisionReceiptReferences(
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


def test_ema_entry_and_exit_replay_once_through_existing_local_paper_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    entry_history = _bars(["100", "100", "100", "110"])
    entry_signal = entry_history[-1]
    entry_execution = _bar(4, open_price=Decimal("91"), close=Decimal("90"))
    entry_proposal = _proposal(entry_history, model_position="flat")
    entry = _prepare(entry_proposal, _ENTRY_REFERENCES, current_quantity=Decimal("0"))

    assert (entry_proposal.action, entry_proposal.input_status, entry.status) == (
        "enter",
        "ready",
        "ready",
    )
    assert entry.local_paper_intent is not None
    assert entry.local_paper_intent.quantity == Decimal("1")

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    accepted_entry = broker.submit_order(entry.local_paper_intent)

    assert accepted_entry.status == "accepted"
    restarted_store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    restarted = LocalPaperBroker(
        event_store=restarted_store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    with pytest.raises(ValueError, match="execution_bar must start"):
        restarted.fill_next_bar(
            entry.local_paper_intent.client_order_id,
            signal_bar=entry_signal,
            execution_bar=_bar(5, close=Decimal("90")),
    )
    entered = restarted.fill_next_bar(
        entry.local_paper_intent.client_order_id,
        signal_bar=entry_signal,
        execution_bar=entry_execution,
    )

    assert entered.fill is not None
    assert entered.fill.source == LOCAL_PAPER_SOURCE
    assert entered.fill.filled_at == entry_execution.start_ts
    assert entered.fill.price == Decimal("91.0000")

    exit_history = [*entry_history, entry_execution]
    exit_signal = exit_history[-1]
    exit_execution = _bar(5, open_price=Decimal("89"), close=Decimal("90"))
    current_quantity = restarted.account().quantity(market="US", symbol="QQQ")
    exit_proposal = _proposal(exit_history, model_position="long")
    exit = _prepare(exit_proposal, _EXIT_REFERENCES, current_quantity=current_quantity)

    assert (exit_proposal.action, exit_proposal.input_status, exit.status) == (
        "exit",
        "ready",
        "ready",
    )
    assert exit.local_paper_intent is not None
    assert exit_proposal.target_exposure == Decimal("0")
    assert exit.local_paper_intent.quantity == current_quantity

    exited = restarted.submit_and_fill_next_bar(
        exit.local_paper_intent,
        signal_bar=exit_signal,
        execution_bar=exit_execution,
    )

    assert exited.fill is not None
    assert exited.fill.source == LOCAL_PAPER_SOURCE
    assert exited.fill.filled_at == exit_execution.start_ts
    assert exited.fill.price == Decimal("89.0000")
    assert restarted.account().positions == ()
    replayed_store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    replayed = LocalPaperBroker(
        event_store=replayed_store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    replayed_entry = replayed.fill_next_bar(
        entry.local_paper_intent.client_order_id,
        signal_bar=entry_signal,
        execution_bar=entry_execution,
    )
    replayed_exit = replayed.fill_next_bar(
        exit.local_paper_intent.client_order_id,
        signal_bar=exit_signal,
        execution_bar=exit_execution,
    )

    assert replayed_entry.fill == entered.fill
    assert replayed_exit.fill == exited.fill
    assert replayed.account().positions == ()
    fills = [event for event in replayed_store.iter_events() if event.event_type == "fill"]
    assert len(fills) == 2
    assert all(event.payload["source"] == LOCAL_PAPER_SOURCE for event in fills)


def test_default_ema_warmup_and_ready_hold_cannot_prepare_a_local_paper_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    default_rule = SessionResetEmaStateRule()
    warmup = _bars(["100"] * 29)

    proposal = _proposal(warmup, model_position="flat", rule=default_rule)
    prepared = _prepare(proposal, _ENTRY_REFERENCES, current_quantity=Decimal("0"))

    assert (proposal.action, proposal.input_status, proposal.target_exposure) == (
        "abstain",
        "missing",
        Decimal("0"),
    )
    assert prepared.status == "no_intent"
    assert prepared.local_paper_intent is None

    ready_hold = _proposal(
        _bars(["100"] * 30),
        model_position="flat",
        rule=default_rule,
    )
    hold_prepared = _prepare(
        ready_hold,
        _ENTRY_REFERENCES,
        current_quantity=Decimal("0"),
    )

    assert (ready_hold.action, ready_hold.input_status, ready_hold.target_exposure) == (
        "hold",
        "ready",
        Decimal("0"),
    )
    assert hold_prepared.status == "no_intent"
    assert hold_prepared.local_paper_intent is None


def test_ema_expired_local_paper_intent_is_rejected_without_a_fill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    history = _bars(["100", "100", "100", "110"])
    proposal = _proposal(history, model_position="flat")
    prepared = _prepare(proposal, _ENTRY_REFERENCES, current_quantity=Decimal("0"))

    assert prepared.local_paper_intent is not None
    assert prepared.local_paper_intent.valid_until == _bar(6, close=Decimal("90")).start_ts

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    late = broker.submit_order(
        replace(
            prepared.local_paper_intent,
            client_order_id=f"{prepared.local_paper_intent.client_order_id}-late",
        ),
        submitted_at=_bar(6, close=Decimal("90")).start_ts,
    )

    assert (late.status, late.reason) == ("rejected", "intent_expired")
    assert broker.account().positions == ()
    assert [event for event in store.iter_events() if event.event_type == "fill"] == []


def test_ema_local_paper_preparation_uses_only_the_causal_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    prefix = _bars(["100", "100", "100", "110"])
    with_future_bars = [*prefix, _bar(4, close=Decimal("90")), _bar(5, close=Decimal("90"))]
    as_of = prefix[-1].end_ts

    original = _proposal(prefix, model_position="flat", as_of=as_of)
    changed = _proposal(with_future_bars, model_position="flat", as_of=as_of)
    original_receipt = receipt_from_target_exposure_proposal(
        original,
        references=_ENTRY_REFERENCES,
    )
    changed_receipt = receipt_from_target_exposure_proposal(
        changed,
        references=_ENTRY_REFERENCES,
    )
    original_prepared = _prepare(original, _ENTRY_REFERENCES, current_quantity=Decimal("0"))
    changed_prepared = _prepare(changed, _ENTRY_REFERENCES, current_quantity=Decimal("0"))

    assert changed == original
    assert changed_receipt == original_receipt
    assert changed_prepared == original_prepared


def _proposal(
    bars: list[Bar],
    *,
    model_position: EmaStatePosition,
    rule: SessionResetEmaStateRule = _RULE,
    as_of: datetime | None = None,
) -> TargetExposureProposal:
    return propose_session_reset_ema_state_target(
        bars,
        session=_SESSION,
        as_of=as_of or bars[-1].end_ts,
        model_position=model_position,
        rule=rule,
        config=_CONFIG,
    )


def _prepare(
    proposal: TargetExposureProposal,
    references: DecisionReceiptReferences,
    *,
    current_quantity: Decimal,
) -> PaperDecisionBridgeResult:
    receipt = receipt_from_target_exposure_proposal(proposal, references=references)
    return prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=references.proposal_ref,
            symbol="QQQ",
            target_exposure=proposal.target_exposure,
            current_quantity=current_quantity,
            maximum_quantity=Decimal("5"),
        ),
        as_of=proposal.decided_at,
    )


def _bars(closes: list[str]) -> list[Bar]:
    return [_bar(index, close=Decimal(close)) for index, close in enumerate(closes)]


def _bar(
    minute_offset: int,
    *,
    close: Decimal,
    open_price: Decimal | None = None,
) -> Bar:
    opening = close if open_price is None else open_price
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=_SESSION.open_ts + timedelta(minutes=minute_offset),
        open=opening,
        high=max(opening, close),
        low=min(opening, close),
        close=close,
        volume=Decimal("1"),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("EMA local-paper replay must stay offline")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

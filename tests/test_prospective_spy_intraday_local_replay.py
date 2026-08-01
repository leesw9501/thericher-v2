from __future__ import annotations

import builtins
import hashlib
import io
import os
import socket
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.models.prospective_spy_intraday_observation import (
    observe_prospective_spy_intraday_baseline,
)
from thericher_v2.models.prospective_spy_intraday_session import (
    build_prospective_spy_intraday_session_record,
)

_SESSION = SessionWindow(
    open_ts=datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
    close_ts=datetime(2026, 8, 3, 20, 0, tzinfo=UTC),
)
_CUTOFF = datetime(2026, 8, 3, 19, 30, tzinfo=UTC)
_SOURCE_CONTRACT_HASH = "sha256:" + "a" * 64


def test_rising_proposal_replays_once_through_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    record, source_bars = _record(rising=True)
    observation = observe_prospective_spy_intraday_baseline(record)
    evaluation = observation.evaluation
    receipt, binding = _receipt_and_binding(evaluation.proposal, observation)

    from thericher_v2.execution.emergency import EmergencyStore
    from thericher_v2.execution.local_paper import (
        LOCAL_PAPER_SOURCE,
        LocalPaperBroker,
        replay_local_paper_account,
    )
    from thericher_v2.execution.paper_decision_bridge import prepare_local_paper_intent
    from thericher_v2.state import EventStore

    bridge = prepare_local_paper_intent(
        receipt,
        binding=binding,
        as_of=evaluation.proposal.decided_at,
    )

    assert evaluation.proposal.action == "enter"
    assert bridge.route == "local_paper"
    assert bridge.status == "ready"
    assert bridge.local_paper_intent is not None
    intent = bridge.local_paper_intent
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    first = broker.submit_and_fill_next_bar(
        intent,
        signal_bar=source_bars[-1],
        execution_bar=_next_replay_bar(),
    )

    assert first.order_result.status == "accepted"
    assert first.order_result.reason == "filled_at_next_bar_open"
    assert first.fill is not None
    assert first.fill.source == LOCAL_PAPER_SOURCE

    repeated_observation = observe_prospective_spy_intraday_baseline(record)
    repeated_evaluation = repeated_observation.evaluation
    repeated_receipt, repeated_binding = _receipt_and_binding(
        repeated_evaluation.proposal,
        repeated_observation,
    )
    repeated_bridge = prepare_local_paper_intent(
        repeated_receipt,
        binding=repeated_binding,
        as_of=repeated_evaluation.proposal.decided_at,
    )

    assert repeated_evaluation.proposal == evaluation.proposal
    assert repeated_observation.receipt == observation.receipt
    assert repeated_bridge.status == "ready"
    assert repeated_bridge.local_paper_intent == intent
    duplicate = broker.submit_and_fill_next_bar(
        intent,
        signal_bar=source_bars[-1],
        execution_bar=_next_replay_bar(),
    )
    replayed = broker.fill_next_bar(
        intent.client_order_id,
        signal_bar=source_bars[-1],
        execution_bar=_next_replay_bar(),
    )
    fill_events = [
        event
        for event in broker.event_store.iter_events()
        if event.event_type == "fill"
    ]

    assert duplicate.order_result.status == "rejected"
    assert duplicate.order_result.reason == "duplicate_client_order_id"
    assert duplicate.fill is None
    assert replayed.fill is not None
    assert replayed.fill.source == LOCAL_PAPER_SOURCE
    assert replayed.order_result.event_seq == first.order_result.event_seq
    assert len(fill_events) == 1
    assert {event.payload["source"] for event in fill_events} == {LOCAL_PAPER_SOURCE}
    assert replay_local_paper_account(broker.event_store) == first.account


def test_non_rising_proposal_creates_no_local_paper_intent_or_fill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    record, _ = _record(rising=False)
    observation = observe_prospective_spy_intraday_baseline(record)
    evaluation = observation.evaluation
    receipt, binding = _receipt_and_binding(evaluation.proposal, observation)

    from thericher_v2.execution.emergency import EmergencyStore
    from thericher_v2.execution.local_paper import LocalPaperBroker
    from thericher_v2.execution.paper_decision_bridge import prepare_local_paper_intent
    from thericher_v2.state import EventStore

    bridge = prepare_local_paper_intent(
        receipt,
        binding=binding,
        as_of=evaluation.proposal.decided_at,
    )
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )

    assert evaluation.proposal.action == "abstain"
    assert bridge.route == "local_paper"
    assert bridge.status == "no_intent"
    assert bridge.local_paper_intent is None
    assert [event for event in broker.event_store.iter_events() if event.event_type == "fill"] == []


def _receipt_and_binding(proposal, observation):
    from thericher_v2.execution.paper_decision_bridge import LocalPaperTargetBinding
    from thericher_v2.research.decision_receipt import (
        DecisionReceiptReferences,
        receipt_from_target_exposure_proposal,
    )

    references = DecisionReceiptReferences(
        campaign_ref="ref:" + "b" * 64,
        model_ref="ref:" + "c" * 64,
        input_manifest_ref=observation.receipt.record_contract_hash,
        proposal_ref="ref:" + hashlib.sha256(
            observation.receipt.receipt_id.encode("utf-8")
        ).hexdigest(),
    )
    return (
        receipt_from_target_exposure_proposal(proposal, references=references),
        LocalPaperTargetBinding(
            proposal_ref=references.proposal_ref,
            symbol=proposal.symbol,
            target_exposure=proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("50"),
        ),
    )


def _record(*, rising: bool) -> tuple[object, tuple[Bar, ...]]:
    source_bars = tuple(
        _bar(
            start=_SESSION.open_ts + Timeframe.M1.duration * index,
            close=(
                Decimal("100") + Decimal(index) / Decimal("1000")
                if rising
                else Decimal("101") - Decimal(index) / Decimal("1000")
            ),
        )
        for index in range(360)
    )
    return (
        build_prospective_spy_intraday_session_record(
            source_bars,
            session=_SESSION,
            cutoff=_CUTOFF,
            source_contract_hash=_SOURCE_CONTRACT_HASH,
        ),
        source_bars,
    )


def _next_replay_bar() -> Bar:
    return _bar(start=_CUTOFF, close=Decimal("101"))


def _bar(*, start: datetime, close: Decimal) -> Bar:
    return Bar(
        symbol="SPY",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start,
        open=close - Decimal("0.01"),
        high=close + Decimal("0.01"),
        low=close - Decimal("0.02"),
        close=close,
        volume=Decimal("1"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective local replay must not access external state")

    original_builtin_open = builtins.open
    original_io_open = io.open

    def guard_builtin_open(file: object, *args: object, **kwargs: object):
        _reject_dotenv_path(file)
        return original_builtin_open(file, *args, **kwargs)

    def guard_io_open(file: object, *args: object, **kwargs: object):
        _reject_dotenv_path(file)
        return original_io_open(file, *args, **kwargs)

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(socket.socket, "connect", fail_external)
    monkeypatch.setattr(builtins, "open", guard_builtin_open)
    monkeypatch.setattr(io, "open", guard_io_open)


def _reject_dotenv_path(file: object) -> None:
    try:
        path = Path(os.fspath(file))
    except TypeError:
        return
    if path.name.startswith(".env"):
        raise AssertionError("prospective local replay must not read credential files")

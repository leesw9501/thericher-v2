from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.execution import (
    BROKER_FAKE_SOURCE,
    LOCAL_PAPER_SOURCE,
    AccountSnapshot,
    BrokerFill,
    BrokerOrderRequest,
    BuyingPowerSnapshot,
    InMemoryBrokerTransport,
    OpenOrderSnapshot,
    create_kis_broker_adapter,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def test_contracts_are_immutable_and_require_utc_and_decimal_values() -> None:
    request = _request()

    with pytest.raises(FrozenInstanceError):
        request.quantity = Decimal("9")  # type: ignore[misc]
    with pytest.raises(ValueError, match="UTC"):
        replace(request, created_at=datetime(2026, 7, 18, 12, 0))
    with pytest.raises(ValueError, match="positive"):
        replace(request, quantity=Decimal("0"))


def test_submit_requires_persisted_intent_and_retry_is_idempotent(tmp_path) -> None:
    state_path = tmp_path / "broker-state.json"
    transport = InMemoryBrokerTransport(state_path=state_path)
    request = _request()

    rejected = transport.submit(request)
    assert rejected.accepted is False
    assert rejected.reason == "intent_not_recorded"
    with pytest.raises(KeyError):
        transport.order_status(request.client_order_id)

    assert transport.record_intent(request) == request
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    restored = InMemoryBrokerTransport.from_state(persisted, state_path=state_path)
    first = restored.submit(request, submitted_at=NOW + timedelta(seconds=1))
    retry = restored.submit(request, submitted_at=NOW + timedelta(minutes=1))

    assert first.accepted is True
    assert retry == first
    assert retry.acknowledged_at == first.acknowledged_at
    assert restored.order_status(request.client_order_id).status == "submitted"

    changed = replace(request, quantity=Decimal("8"))
    assert restored.submit(changed).reason == "recorded_intent_mismatch"
    with pytest.raises(ValueError, match="different intent"):
        restored.record_intent(changed)

    volatile = InMemoryBrokerTransport()
    volatile.record_intent(_request("volatile"))
    assert volatile.submit(_request("volatile")).reason == "intent_not_durable"


def test_fake_transport_progresses_deterministically_from_partial_to_full_fill(tmp_path) -> None:
    transport = _submitted_transport(tmp_path)

    first = transport.simulate_next_fill(
        "order-1",
        price=Decimal("10"),
        filled_at=NOW + timedelta(seconds=2),
    )
    partial = transport.order_status("order-1")
    second = transport.simulate_next_fill(
        "order-1",
        price=Decimal("12"),
        fee=Decimal("0.02"),
        filled_at=NOW + timedelta(seconds=3),
    )
    complete = transport.order_status("order-1")

    assert first.quantity == second.quantity == Decimal("2")
    assert first.source == second.source == BROKER_FAKE_SOURCE
    assert first.source != LOCAL_PAPER_SOURCE
    assert partial.status == "partially_filled"
    assert partial.remaining_quantity == Decimal("2")
    assert complete.status == "filled"
    assert complete.remaining_quantity == 0
    assert complete.average_fill_price == Decimal("11")
    with pytest.raises(ValueError, match="not open"):
        transport.simulate_next_fill(
            "order-1",
            price=Decimal("13"),
            filled_at=NOW + timedelta(seconds=4),
        )


def test_unknown_outcome_requires_authoritative_resolution_and_reconciliation(tmp_path) -> None:
    state_path = tmp_path / "broker-state.json"
    transport = _submitted_transport(tmp_path)
    cancelled = transport.cancel("order-1", cancelled_at=NOW + timedelta(seconds=2))

    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_quantity == Decimal("4")
    assert transport.order_status("order-1").status == "cancelled"
    assert transport.open_order_snapshot(captured_at=NOW + timedelta(seconds=3)).orders == ()

    unknown_request = _request("order-unknown")
    transport.record_intent(unknown_request)
    original_ack = transport.submit(
        unknown_request,
        submitted_at=NOW + timedelta(seconds=1),
    )
    unknown = transport.mark_outcome_unknown(
        unknown_request.client_order_id,
        observed_at=NOW + timedelta(seconds=2),
    )

    assert unknown.status == "outcome_unknown"
    assert (
        transport.submit(
            unknown_request,
            submitted_at=NOW + timedelta(seconds=3),
        ).reason
        == "outcome_unknown_requires_reconciliation"
    )
    assert (
        transport.cancel(
            unknown_request.client_order_id,
            cancelled_at=NOW + timedelta(seconds=3),
        ).status
        == "outcome_unknown"
    )
    result = transport.reconcile(
        account=_account(NOW + timedelta(seconds=3)),
        buying_power=_buying_power(NOW + timedelta(seconds=3)),
        open_orders=transport.open_order_snapshot(captured_at=NOW + timedelta(seconds=3)),
        fills=transport.fills,
        reconciled_at=NOW + timedelta(seconds=3),
    )
    assert result.safe_to_submit is False
    assert result.outcome_unknown_ids == ("order-unknown",)

    with pytest.raises(ValueError, match="stable ids"):
        transport.resolve_outcome_unknown(
            replace(
                unknown,
                broker_order_id="wrong",
                status="submitted",
                updated_at=NOW + timedelta(seconds=4),
                reason="authoritative_snapshot",
            )
        )
    resolved = transport.resolve_outcome_unknown(
        replace(
            unknown,
            status="submitted",
            updated_at=NOW + timedelta(seconds=4),
            reason="authoritative_snapshot",
        )
    )
    assert resolved.status == "submitted"

    restored = InMemoryBrokerTransport.from_state(
        json.loads(state_path.read_text(encoding="utf-8")),
        state_path=state_path,
    )
    clean_time = NOW + timedelta(seconds=5)
    clean = restored.reconcile(
        account=_account(clean_time),
        buying_power=_buying_power(clean_time),
        open_orders=restored.open_order_snapshot(captured_at=clean_time),
        fills=restored.fills,
        reconciled_at=clean_time,
    )
    assert clean.safe_to_submit is True
    assert restored.submit(unknown_request) == original_ack


def test_unknown_full_fill_requires_consistent_fill_evidence_and_persists(tmp_path) -> None:
    state_path = tmp_path / "broker-state.json"
    transport = _submitted_transport(tmp_path)
    request = _request()
    unknown = transport.mark_outcome_unknown(
        request.client_order_id,
        observed_at=NOW + timedelta(seconds=2),
    )
    assert unknown.broker_order_id is not None
    assert (
        transport.submit(
            request,
            submitted_at=NOW + timedelta(seconds=3),
        ).reason
        == "outcome_unknown_requires_reconciliation"
    )

    first_fill = BrokerFill(
        fill_id="authoritative-fill-1",
        client_order_id=request.client_order_id,
        broker_order_id=unknown.broker_order_id,
        quantity=Decimal("1.5"),
        price=Decimal("10"),
        fee=Decimal("0"),
        filled_at=NOW + timedelta(seconds=3),
    )
    second_fill = BrokerFill(
        fill_id="authoritative-fill-2",
        client_order_id=request.client_order_id,
        broker_order_id=unknown.broker_order_id,
        quantity=Decimal("2.5"),
        price=Decimal("12"),
        fee=Decimal("0"),
        filled_at=NOW + timedelta(seconds=4),
    )
    authoritative = replace(
        unknown,
        status="filled",
        filled_quantity=request.quantity,
        remaining_quantity=Decimal("0"),
        average_fill_price=Decimal("11.25"),
        updated_at=NOW + timedelta(seconds=5),
        reason="authoritative_filled_snapshot",
    )

    with pytest.raises(ValueError, match="fill evidence quantity"):
        transport.resolve_outcome_unknown(authoritative)
    with pytest.raises(ValueError, match="fill evidence quantity"):
        transport.resolve_outcome_unknown(
            authoritative,
            fills=(first_fill, replace(second_fill, quantity=Decimal("2"))),
        )
    with pytest.raises(ValueError, match="weighted price"):
        transport.resolve_outcome_unknown(
            replace(authoritative, average_fill_price=Decimal("11")),
            fills=(first_fill, second_fill),
        )
    with pytest.raises(ValueError, match="fill ids must be unique"):
        transport.resolve_outcome_unknown(
            authoritative,
            fills=(first_fill, first_fill, second_fill),
        )
    with pytest.raises(ValueError, match="cannot precede"):
        transport.resolve_outcome_unknown(
            authoritative,
            fills=(
                replace(first_fill, filled_at=NOW + timedelta(seconds=1)),
                second_fill,
            ),
        )

    resolved = transport.resolve_outcome_unknown(
        authoritative,
        fills=(first_fill, second_fill),
    )
    assert resolved.status == "filled"
    assert transport.fills == (first_fill, second_fill)

    restored = InMemoryBrokerTransport.from_state(
        json.loads(state_path.read_text(encoding="utf-8")),
        state_path=state_path,
    )
    assert restored.order_status(request.client_order_id) == authoritative
    assert restored.fills == (first_fill, second_fill)
    clean_time = NOW + timedelta(seconds=6)
    clean = restored.reconcile(
        account=_account(clean_time),
        buying_power=_buying_power(clean_time),
        open_orders=restored.open_order_snapshot(captured_at=clean_time),
        fills=restored.fills,
        reconciled_at=clean_time,
    )
    assert clean.safe_to_submit is True


def test_exported_json_state_reloads_for_idempotent_restart_recovery(tmp_path) -> None:
    state_path = tmp_path / "broker-state.json"
    transport = _submitted_transport(tmp_path)
    original_ack = transport.submit(_request(), submitted_at=NOW + timedelta(minutes=1))
    transport.simulate_next_fill(
        "order-1",
        price=Decimal("10"),
        filled_at=NOW + timedelta(seconds=2),
    )

    exported = json.loads(json.dumps(transport.export_state()))
    restored = InMemoryBrokerTransport.from_state(exported, state_path=state_path)

    assert restored.submit(_request()) == original_ack
    assert restored.order_status("order-1").status == "partially_filled"
    assert restored.fills == transport.fills
    restored.simulate_next_fill(
        "order-1",
        price=Decimal("12"),
        filled_at=NOW + timedelta(seconds=3),
    )
    assert restored.order_status("order-1").status == "filled"


def test_reconciliation_detects_duplicates_mismatches_and_stale_snapshots(tmp_path) -> None:
    transport = _submitted_transport(tmp_path)
    fill = transport.simulate_next_fill(
        "order-1",
        price=Decimal("10"),
        filled_at=NOW + timedelta(seconds=2),
    )
    current = transport.order_status("order-1")
    clean_time = NOW + timedelta(seconds=3)
    clean = transport.reconcile(
        account=_account(clean_time),
        buying_power=_buying_power(clean_time),
        open_orders=transport.open_order_snapshot(captured_at=clean_time),
        fills=transport.fills,
        reconciled_at=clean_time,
    )
    assert clean.safe_to_submit is True

    bad_snapshot = OpenOrderSnapshot(
        orders=(current, current, replace(current, broker_order_id="wrong")),
        captured_at=NOW - timedelta(minutes=10),
    )
    unsafe = transport.reconcile(
        account=_account(NOW - timedelta(minutes=10)),
        buying_power=replace(_buying_power(clean_time), currency="KRW"),
        open_orders=bad_snapshot,
        fills=(fill, fill),
        reconciled_at=clean_time,
    )

    assert unsafe.safe_to_submit is False
    assert "client:order-1" in unsafe.duplicates
    assert any(item.startswith("broker:") for item in unsafe.duplicates)
    assert f"fill:{fill.fill_id}" in unsafe.duplicates
    assert "open_order:order-1" in unsafe.mismatches
    assert "account_currency" in unsafe.mismatches
    assert set(unsafe.stale_snapshots) == {"account", "open_orders"}


def test_fake_and_disabled_transports_need_no_network_or_credentials(monkeypatch, tmp_path) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("broker readiness contracts must remain offline")

    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(os, "getenv", fail_io)

    transport = _submitted_transport(tmp_path)
    transport.simulate_next_fill(
        "order-1",
        price=Decimal("10"),
        filled_at=NOW + timedelta(seconds=2),
    )

    assert transport.fills[0].source == BROKER_FAKE_SOURCE
    assert (tmp_path / "broker-state.json").is_file()
    assert create_kis_broker_adapter().capabilities.can_submit is False


def _submitted_transport(tmp_path) -> InMemoryBrokerTransport:
    transport = InMemoryBrokerTransport(state_path=tmp_path / "broker-state.json")
    request = _request()
    transport.record_intent(request)
    assert transport.submit(request, submitted_at=NOW + timedelta(seconds=1)).accepted
    return transport


def _request(client_order_id: str = "order-1") -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id=client_order_id,
        symbol="aapl",
        market="us",
        side="buy",
        quantity=Decimal("4"),
        limit_price=None,
        decision_id="decision-1",
        created_at=NOW,
    )


def _account(captured_at: datetime) -> AccountSnapshot:
    return AccountSnapshot("USD", Decimal("1000"), Decimal("1000"), Decimal("0"), captured_at)


def _buying_power(captured_at: datetime) -> BuyingPowerSnapshot:
    return BuyingPowerSnapshot("USD", Decimal("1000"), Decimal("1000"), captured_at)

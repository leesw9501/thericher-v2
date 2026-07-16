from __future__ import annotations

import os
import socket
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, OrderIntent, Timeframe
from thericher_v2.execution import (
    BROKER_DISABLED_SOURCE,
    BROKER_EXECUTION_ENABLED,
    LOCAL_PAPER_SOURCE,
    BrokerCapabilities,
    CancelIntent,
    EmergencyStore,
    LocalPaperBroker,
    OrderStatusQuery,
    create_kis_broker_adapter,
)
from thericher_v2.state import EventStore


def test_disabled_kis_adapter_returns_unavailable_order_lifecycle_results() -> None:
    adapter = create_kis_broker_adapter()
    order = _order()
    cancel = CancelIntent(
        client_order_id=order.client_order_id,
        created_at=order.created_at,
        reason="unit_test_cancel",
    )
    status_query = OrderStatusQuery(
        client_order_id=order.client_order_id,
        created_at=order.created_at,
    )

    results = (
        adapter.submit_order(order),
        adapter.cancel_order(cancel),
        adapter.order_status(status_query),
    )

    assert BROKER_EXECUTION_ENABLED is False
    assert adapter.capabilities == BrokerCapabilities()
    assert adapter.capabilities.account_mode == "disabled"
    assert adapter.capabilities.can_submit is False
    assert adapter.capabilities.can_cancel is False
    assert adapter.capabilities.can_check_status is False
    assert {result.action for result in results} == {"submit", "cancel", "status"}
    for result in results:
        assert result.status == "unavailable"
        assert result.reason == "broker_execution_disabled"
        assert result.source == BROKER_DISABLED_SOURCE
        assert result.source != LOCAL_PAPER_SOURCE
        assert result.client_order_id == order.client_order_id
        assert _non_promotional(result.reason)


def test_disabled_kis_adapter_is_offline_and_does_not_read_credentials(monkeypatch) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("disabled broker boundary must not use network or secrets")

    original_open = Path.open
    original_read_text = Path.read_text

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.startswith(".env"):
            raise AssertionError("disabled broker boundary must not read credential files")
        return original_open(path, *args, **kwargs)

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("disabled broker boundary must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", fail_io)
    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(os, "getenv", fail_io)
    monkeypatch.setattr(Path, "open", guard_open)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    adapter = create_kis_broker_adapter()
    order = _order()

    assert adapter.submit_order(order).status == "unavailable"
    assert adapter.cancel_order(
        CancelIntent(client_order_id=order.client_order_id, created_at=order.created_at)
    ).status == "unavailable"
    assert adapter.order_status(
        OrderStatusQuery(client_order_id=order.client_order_id, created_at=order.created_at)
    ).status == "unavailable"


def test_explicit_broker_enable_request_fails_closed_without_io(monkeypatch) -> None:
    def fail_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("enabling disabled broker must not use network or secrets")

    monkeypatch.setattr(socket, "create_connection", fail_io)
    monkeypatch.setattr(urllib.request, "urlopen", fail_io)
    monkeypatch.setattr(os, "getenv", fail_io)

    with pytest.raises(NotImplementedError, match="KIS execution is not enabled"):
        create_kis_broker_adapter(enabled=True)


def test_disabled_broker_results_do_not_write_events_or_emit_local_paper_fills(tmp_path) -> None:
    event_store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    adapter = create_kis_broker_adapter()
    order = _order()

    result = adapter.submit_order(order)

    assert result.source == BROKER_DISABLED_SOURCE
    assert result.source != LOCAL_PAPER_SOURCE
    assert not hasattr(result, "fill")
    assert list(event_store.iter_events()) == []
    assert not event_store.jsonl_path.exists()


def test_local_paper_execution_remains_separate_from_disabled_broker(tmp_path) -> None:
    event_store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    local_paper = LocalPaperBroker(
        event_store=event_store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        starting_cash=Decimal("1000"),
    )
    disabled_broker = create_kis_broker_adapter()
    paper_order = _order("paper-1")

    local_result = local_paper.submit_and_fill_next_bar(
        paper_order,
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )
    event_types_before_broker = [event.event_type for event in event_store.iter_events()]
    disabled_result = disabled_broker.cancel_order(
        CancelIntent(client_order_id="disabled-cancel", created_at=paper_order.created_at)
    )

    assert local_result.fill is not None
    assert local_result.fill.source == LOCAL_PAPER_SOURCE
    assert disabled_result.source == BROKER_DISABLED_SOURCE
    assert [event.event_type for event in event_store.iter_events()] == event_types_before_broker


def test_disabled_broker_contracts_fail_closed_when_enabled_values_are_supplied() -> None:
    with pytest.raises(ValueError, match="cannot enable execution"):
        BrokerCapabilities(can_submit=True)
    with pytest.raises(ValueError, match="client_order_id"):
        CancelIntent(client_order_id="", created_at=datetime(2026, 1, 2, tzinfo=UTC))
    with pytest.raises(ValueError, match="client_order_id"):
        OrderStatusQuery(client_order_id="", created_at=datetime(2026, 1, 2, tzinfo=UTC))


def _order(client_order_id: str = "broker-boundary-1") -> OrderIntent:
    return OrderIntent(
        client_order_id=client_order_id,
        symbol="AAPL",
        market="US",
        side="buy",
        quantity=Decimal("2"),
        limit_price=None,
        decision_id="decision-1",
        created_at=datetime(2026, 1, 2, 14, 31, tzinfo=UTC),
    )


def _bar(index: int) -> Bar:
    open_price = Decimal("100") + Decimal(index)
    close = open_price + Decimal("0.25")
    return Bar(
        symbol="aapl",
        market="us",
        timeframe=Timeframe.M1,
        start_ts=datetime(2026, 1, 2, 14, 30 + index, tzinfo=UTC),
        open=open_price,
        high=close + Decimal("0.5"),
        low=open_price - Decimal("0.5"),
        close=close,
        volume=Decimal("1000"),
    )


def _non_promotional(value: str) -> bool:
    forbidden = ("best", "recommended", "passed", "promoted", "production")
    return not any(word in value.lower() for word in forbidden)

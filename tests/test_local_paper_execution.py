from __future__ import annotations

import socket
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, OrderIntent, Side, Timeframe
from thericher_v2.execution import EmergencyStore, LocalPaperBroker, replay_local_paper_account
from thericher_v2.state import EventStore


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


def _order(client_order_id: str = "paper-1", *, side: Side = "buy") -> OrderIntent:
    return OrderIntent(
        client_order_id=client_order_id,
        symbol="AAPL",
        market="US",
        side=side,
        quantity=Decimal("2"),
        limit_price=None,
        decision_id="decision-1",
        created_at=datetime(2026, 1, 2, 14, 31, tzinfo=UTC),
    )


def _broker(tmp_path, *, starting_cash: Decimal = Decimal("1000")) -> LocalPaperBroker:
    return LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        starting_cash=starting_cash,
        fee_bps=Decimal("1"),
    )


def test_local_paper_fill_is_offline_and_does_not_read_credentials(monkeypatch, tmp_path) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local paper execution must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("local paper execution must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    broker = _broker(tmp_path)
    result = broker.submit_and_fill_next_bar(
        _order(),
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )

    assert result.fill is not None
    assert result.fill.price == Decimal("101.0000")
    assert result.account.quantity(market="US", symbol="AAPL") == Decimal("2")


def test_duplicate_client_order_id_is_rejected(tmp_path) -> None:
    broker = _broker(tmp_path)
    order = _order("duplicate-id")

    first = broker.submit_order(order)
    duplicate = broker.submit_order(order)
    filled_original = broker.fill_next_bar(
        order.client_order_id,
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )

    assert first.status == "accepted"
    assert duplicate.status == "rejected"
    assert duplicate.reason == "duplicate_client_order_id"
    assert filled_original.fill is not None


def test_emergency_stop_blocks_new_local_paper_orders(tmp_path) -> None:
    emergency = EmergencyStore(tmp_path / "emergency.json")
    emergency.stop_new_orders("unit_test_stop")
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=emergency,
    )

    result = broker.submit_order(_order())

    assert result.status == "rejected"
    assert result.reason == "emergency_stop_active"
    assert list(broker.event_store.iter_events())[0].event_type == "local_paper_order_rejected"


def test_next_bar_fill_updates_cash_positions_and_replay(tmp_path) -> None:
    broker = _broker(tmp_path, starting_cash=Decimal("1000"))

    result = broker.submit_and_fill_next_bar(
        _order(),
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )
    replay = broker.event_store.replay()
    replayed_account = replay_local_paper_account(
        broker.event_store,
        starting_cash=Decimal("1000"),
    )

    assert result.fill is not None
    assert result.fill.source == "local_paper"
    assert result.fill.filled_at == _bar(1).start_ts
    assert result.account.cash == Decimal("797.9798")
    assert result.account.quantity(market="US", symbol="AAPL") == Decimal("2")
    assert replay.positions[("US", "AAPL")] == Decimal("2")
    assert replayed_account == result.account

    event_types = [event.event_type for event in broker.event_store.iter_events()]
    assert event_types == [
        "local_paper_order_accepted",
        "fill",
        "local_paper_portfolio_snapshot",
    ]


def test_sell_requires_local_position_and_updates_account(tmp_path) -> None:
    broker = _broker(tmp_path, starting_cash=Decimal("1000"))
    buy = broker.submit_and_fill_next_bar(
        _order("buy-1"),
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )
    sell = broker.submit_and_fill_next_bar(
        _order("sell-1", side="sell"),
        signal_bar=_bar(1),
        execution_bar=_bar(2),
    )

    assert buy.fill is not None
    assert sell.fill is not None
    assert sell.account.quantity(market="US", symbol="AAPL") == Decimal("0")
    assert sell.account.cash == Decimal("1001.9594")


def test_canceled_order_is_persisted_and_not_fillable(tmp_path) -> None:
    broker = _broker(tmp_path)
    order = _order("cancel-me")
    accepted = broker.submit_order(order)
    canceled = broker.cancel_order(
        order.client_order_id,
        canceled_at=datetime(2026, 1, 2, 14, 31, tzinfo=UTC),
        reason="unit_test_cancel",
    )

    assert accepted.status == "accepted"
    assert canceled.status == "canceled"
    assert canceled.reason == "unit_test_cancel"
    assert [event.event_type for event in broker.event_store.iter_events()] == [
        "local_paper_order_accepted",
        "local_paper_order_canceled",
    ]
    with pytest.raises(ValueError, match="no pending accepted"):
        broker.fill_next_bar(order.client_order_id, signal_bar=_bar(0), execution_bar=_bar(1))


def test_non_next_bar_execution_is_rejected_by_contract(tmp_path) -> None:
    broker = _broker(tmp_path)
    broker.submit_order(_order("bad-next-bar"))

    with pytest.raises(ValueError, match="execution_bar must start"):
        broker.fill_next_bar(
            "bad-next-bar",
            signal_bar=_bar(0),
            execution_bar=_bar(2),
        )

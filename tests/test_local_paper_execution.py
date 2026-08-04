from __future__ import annotations

import json
import socket
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, OrderIntent, Side, Timeframe
from thericher_v2.execution import (
    EmergencyStore,
    LocalPaperBroker,
    replay_local_paper_account,
    replay_local_paper_realized_pnl,
)
from thericher_v2.state import Event, EventStore


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


def _daily_bar(
    start_ts: datetime,
    *,
    open_price: Decimal = Decimal("100"),
    symbol: str = "AAPL",
    market: str = "US",
    timeframe: Timeframe = Timeframe.D1,
    complete: bool = True,
) -> Bar:
    close = open_price + Decimal("0.25")
    return Bar(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        start_ts=start_ts,
        open=open_price,
        high=close + Decimal("0.5"),
        low=open_price - Decimal("0.5"),
        close=close,
        volume=Decimal("1000"),
        complete=complete,
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


def _broker(
    tmp_path,
    *,
    starting_cash: Decimal = Decimal("1000"),
    fee_bps: Decimal = Decimal("1"),
) -> LocalPaperBroker:
    return LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        starting_cash=starting_cash,
        fee_bps=fee_bps,
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
    realized = replay_local_paper_realized_pnl(broker.event_store.iter_events())
    assert realized.realized_after_cost_pnl == Decimal("0")
    assert realized.closed_segment_count == 0
    assert realized.open_quantity == Decimal("2")


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


def test_malformed_emergency_state_blocks_new_local_paper_orders(tmp_path) -> None:
    emergency_path = tmp_path / "emergency.json"
    emergency_path.write_text('{"stop_new_orders": false}', encoding="utf-8")
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(emergency_path),
    )

    result = broker.submit_order(_order())

    assert result.status == "rejected"
    assert result.reason == "emergency_stop_active"
    assert list(broker.event_store.iter_events())[0].event_type == "local_paper_order_rejected"


def test_timezone_less_emergency_timestamp_blocks_new_local_paper_orders(tmp_path) -> None:
    emergency_path = tmp_path / "emergency.json"
    emergency_path.write_text(
        json.dumps(
            {
                "stop_new_orders": False,
                "cancel_open_orders_requested": False,
                "reason": "incorrectly_clear",
                "updated_at": "2026-01-02T14:30:00",
            }
        ),
        encoding="utf-8",
    )
    broker = LocalPaperBroker(
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(emergency_path),
    )

    result = broker.submit_order(_order())

    assert result.status == "rejected"
    assert result.reason == "emergency_stop_active"


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


def test_interrupted_fill_retries_existing_fill_without_duplicate(monkeypatch, tmp_path) -> None:
    broker = _broker(tmp_path, starting_cash=Decimal("1000"))
    order = _order("interrupted-fill")
    broker.submit_order(order)

    def fail_snapshot(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated snapshot interruption")

    monkeypatch.setattr(broker, "_record_portfolio_snapshot", fail_snapshot)
    with pytest.raises(OSError, match="snapshot interruption"):
        broker.fill_next_bar(
            order.client_order_id,
            signal_bar=_bar(0),
            execution_bar=_bar(1),
        )

    fill_event = next(
        event
        for event in broker.event_store.iter_events()
        if event.event_type == "fill"
        and event.payload.get("client_order_id") == order.client_order_id
    )
    recovered_broker = _broker(tmp_path, starting_cash=Decimal("1000"))
    recovered = recovered_broker.fill_next_bar(
        order.client_order_id,
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )
    replayed_account = replay_local_paper_account(
        recovered_broker.event_store,
        starting_cash=Decimal("1000"),
    )

    assert recovered.fill is not None
    assert recovered.fill.source == "local_paper"
    assert recovered.order_result.event_seq == fill_event.seq
    assert recovered.order_result.reason == "filled_at_next_bar_open"
    assert recovered.account == replayed_account
    assert [event.event_type for event in recovered_broker.event_store.iter_events()] == [
        "local_paper_order_accepted",
        "fill",
    ]
    assert recovered_broker.fill_next_bar(
        order.client_order_id,
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    ) == recovered


def test_interrupted_fill_recovery_rejects_revised_execution_bar(tmp_path, monkeypatch) -> None:
    broker = _broker(tmp_path)
    order = _order("interrupted-revised-bar")
    broker.submit_order(order)

    def fail_snapshot(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated snapshot interruption")

    monkeypatch.setattr(broker, "_record_portfolio_snapshot", fail_snapshot)
    with pytest.raises(OSError, match="snapshot interruption"):
        broker.fill_next_bar(
            order.client_order_id,
            signal_bar=_bar(0),
            execution_bar=_bar(1),
        )

    recovered_broker = _broker(tmp_path)
    with pytest.raises(ValueError, match="bar identity does not match"):
        recovered_broker.fill_next_bar(
            order.client_order_id,
            signal_bar=_bar(0),
            execution_bar=replace(_bar(1), volume=Decimal("999")),
        )
    with pytest.raises(ValueError, match="does not match requested execution"):
        _broker(tmp_path, fee_bps=Decimal("2")).fill_next_bar(
            order.client_order_id,
            signal_bar=_bar(0),
            execution_bar=_bar(1),
        )

    assert len(
        [
            event
            for event in recovered_broker.event_store.iter_events()
            if event.event_type == "fill"
            and event.payload.get("client_order_id") == order.client_order_id
        ]
    ) == 1


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


def test_realized_pnl_replay_is_fifo_fee_aware_and_excludes_open_lots(tmp_path) -> None:
    broker = _broker(tmp_path, starting_cash=Decimal("1000"))
    broker.submit_and_fill_next_bar(
        _order("pnl-buy-first"),
        signal_bar=_bar(0),
        execution_bar=_bar(1),
    )
    broker.submit_and_fill_next_bar(
        replace(_order("pnl-buy-second"), quantity=Decimal("1")),
        signal_bar=_bar(1),
        execution_bar=_bar(2),
    )
    broker.submit_and_fill_next_bar(
        replace(_order("pnl-sell", side="sell"), quantity=Decimal("2")),
        signal_bar=_bar(2),
        execution_bar=_bar(3),
    )

    realized = replay_local_paper_realized_pnl(broker.event_store.iter_events())

    assert realized.realized_after_cost_pnl == Decimal("3.9592")
    assert realized.closed_segment_count == 1
    assert realized.closed_quantity == Decimal("2")
    assert realized.open_quantity == Decimal("1")
    assert realized.local_paper_fill_count == 3
    assert broker.account().quantity(market="US", symbol="AAPL") == Decimal("1")


def test_realized_pnl_replay_fails_closed_for_an_oversold_local_history(tmp_path) -> None:
    event_store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    event_store.append(
        Event(
            event_type="fill",
            created_at=datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            payload={
                "source": "local_paper",
                "client_order_id": "oversold-local-paper",
                "market": "US",
                "symbol": "AAPL",
                "side": "sell",
                "quantity": "1",
                "price": "101",
                "fee": "0",
            },
        )
    )

    with pytest.raises(ValueError, match="exceeds available FIFO lots"):
        replay_local_paper_realized_pnl(event_store.iter_events())


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


@pytest.mark.parametrize(
    ("signal_start", "execution_start"),
    (
        (
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 5, tzinfo=UTC),
        ),
        (
            datetime(2025, 12, 24, tzinfo=UTC),
            datetime(2025, 12, 26, tzinfo=UTC),
        ),
    ),
    ids=("weekend-adjacent-observed-bars", "christmas-closure-adjacent-observed-bars"),
)
def test_daily_fill_accepts_adjacent_observed_bars_across_known_closures(
    tmp_path,
    signal_start: datetime,
    execution_start: datetime,
) -> None:
    broker = _broker(tmp_path)
    signal = _daily_bar(signal_start)
    execution = _daily_bar(execution_start, open_price=Decimal("101"))

    result = broker.submit_and_fill_next_bar(
        _order(f"daily-{execution_start.date().isoformat()}"),
        signal_bar=signal,
        execution_bar=execution,
    )

    assert result.fill is not None
    assert result.fill.filled_at == execution.start_ts
    assert result.fill.price == Decimal("101.0000")
    assert result.fill.source == "local_paper"


def test_daily_fill_rejects_reversed_same_date_and_mismatched_bars(tmp_path) -> None:
    broker = _broker(tmp_path)
    signal = _daily_bar(datetime(2026, 1, 2, tzinfo=UTC))
    valid_execution = _daily_bar(datetime(2026, 1, 5, tzinfo=UTC))
    cases = (
        (
            _daily_bar(datetime(2026, 1, 1, tzinfo=UTC)),
            "later observed UTC date",
        ),
        (
            _daily_bar(datetime(2026, 1, 2, 20, tzinfo=UTC)),
            "later observed UTC date",
        ),
        (replace(valid_execution, symbol="MSFT"), "match order"),
        (replace(valid_execution, market="CA"), "match order"),
        (replace(valid_execution, timeframe=Timeframe.H1), "same timeframe"),
        (replace(valid_execution, complete=False), "must be complete"),
    )

    for index, (execution, message) in enumerate(cases):
        order = _order(f"daily-invalid-{index}")
        broker.submit_order(order)
        with pytest.raises(ValueError, match=message):
            broker.fill_next_bar(
                order.client_order_id,
                signal_bar=signal,
                execution_bar=execution,
            )

    incomplete_signal_order = _order("daily-incomplete-signal")
    broker.submit_order(incomplete_signal_order)
    with pytest.raises(ValueError, match="must be complete"):
        broker.fill_next_bar(
            incomplete_signal_order.client_order_id,
            signal_bar=replace(signal, complete=False),
            execution_bar=valid_execution,
        )

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution import (
    BROKER_DISABLED_SOURCE,
    LOCAL_PAPER_SOURCE,
    replay_local_paper_decision_pnl,
    replay_local_paper_realized_pnl,
)
from thericher_v2.state import Event

START = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)


def _accepted(
    seq: int,
    client_order_id: str,
    decision_id: str,
    *,
    created_at: datetime,
    side: str = "buy",
    quantity: str = "1",
    market: str = "US",
    symbol: str = "AAPL",
) -> Event:
    return Event(
        event_type="local_paper_order_accepted",
        created_at=created_at,
        seq=seq,
        payload={
            "source": LOCAL_PAPER_SOURCE,
            "status": "accepted",
            "reason": "accepted_for_next_bar_open",
            "client_order_id": client_order_id,
            "market": market,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "decision_id": decision_id,
            "created_at": created_at.isoformat(),
        },
    )


def _fill(
    seq: int,
    client_order_id: str,
    *,
    created_at: datetime,
    side: str = "buy",
    quantity: str = "1",
    price: str = "100",
    fee: str = "0",
    source: str = LOCAL_PAPER_SOURCE,
    market: str = "US",
    symbol: str = "AAPL",
) -> Event:
    return Event(
        event_type="fill",
        created_at=created_at,
        seq=seq,
        payload={
            "source": source,
            "client_order_id": client_order_id,
            "market": market,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fee": fee,
        },
    )


def test_decision_pnl_replay_preserves_fifo_segments_and_both_decision_roles() -> None:
    events = (
        _accepted(1, "buy-a", "entry-a", created_at=START, quantity="2"),
        _fill(
            2,
            "buy-a",
            created_at=START + timedelta(minutes=1),
            quantity="2",
            price="101",
            fee="0.0202",
        ),
        _accepted(
            3,
            "buy-b",
            "entry-b",
            created_at=START + timedelta(minutes=2),
            quantity="2",
        ),
        _fill(
            4,
            "buy-b",
            created_at=START + timedelta(minutes=3),
            quantity="2",
            price="102",
            fee="0.0204",
        ),
        _accepted(
            5,
            "sell-a",
            "exit-a",
            created_at=START + timedelta(minutes=4),
            side="sell",
            quantity="3",
        ),
        _fill(
            6,
            "sell-a",
            created_at=START + timedelta(minutes=5),
            side="sell",
            quantity="3",
            price="103",
            fee="0.0309",
        ),
    )

    result = replay_local_paper_decision_pnl(events)

    assert result.aggregate == replay_local_paper_realized_pnl(events)
    assert result.aggregate.realized_after_cost_pnl == Decimal("4.9387")
    assert result.aggregate.closed_segment_count == 2
    assert result.aggregate.closed_quantity == Decimal("3")
    assert result.aggregate.open_quantity == Decimal("1")
    assert [
        (segment.entry_decision_id, segment.exit_decision_id, segment.quantity)
        for segment in result.closed_segments
    ] == [
        ("entry-a", "exit-a", Decimal("2")),
        ("entry-b", "exit-a", Decimal("1")),
    ]
    assert [total.decision_id for total in result.entry_decision_totals] == [
        "entry-a",
        "entry-b",
    ]
    assert [total.realized_after_cost_pnl for total in result.entry_decision_totals] == [
        Decimal("3.9592"),
        Decimal("0.9795"),
    ]
    assert result.exit_decision_totals[0].decision_id == "exit-a"
    assert result.exit_decision_totals[0].realized_after_cost_pnl == Decimal("4.9387")
    assert [
        (total.entry_decision_id, total.exit_decision_id, total.realized_after_cost_pnl)
        for total in result.decision_pair_totals
    ] == [
        ("entry-a", "exit-a", Decimal("3.9592")),
        ("entry-b", "exit-a", Decimal("0.9795")),
    ]


def test_decision_pnl_replay_fails_closed_for_missing_or_duplicate_acceptance() -> None:
    missing_acceptance = (
        _fill(1, "missing", created_at=START, price="101"),
    )
    duplicate_acceptance = (
        _accepted(1, "duplicate", "entry", created_at=START),
        _accepted(2, "duplicate", "entry", created_at=START + timedelta(minutes=1)),
    )

    with pytest.raises(ValueError, match="has no accepted"):
        replay_local_paper_decision_pnl(missing_acceptance)
    with pytest.raises(ValueError, match="multiple accepted"):
        replay_local_paper_decision_pnl(duplicate_acceptance)


def test_decision_pnl_replay_fails_closed_for_tampered_fill_identity_and_inactive_order() -> None:
    tampered_identity = (
        _accepted(1, "tampered", "entry", created_at=START),
        _fill(
            2,
            "tampered",
            created_at=START + timedelta(minutes=1),
            symbol="MSFT",
        ),
    )
    canceled_then_filled = (
        _accepted(1, "canceled", "entry", created_at=START),
        Event(
            event_type="local_paper_order_canceled",
            created_at=START + timedelta(minutes=1),
            seq=2,
            payload={
                "source": LOCAL_PAPER_SOURCE,
                "client_order_id": "canceled",
                "reason": "local_cancel",
            },
        ),
        _fill(3, "canceled", created_at=START + timedelta(minutes=2)),
    )

    with pytest.raises(ValueError, match="does not match accepted"):
        replay_local_paper_decision_pnl(tampered_identity)
    with pytest.raises(ValueError, match="follows an inactive"):
        replay_local_paper_decision_pnl(canceled_then_filled)


def test_decision_pnl_replay_rejects_timezone_less_accepted_order_timestamp() -> None:
    accepted = _accepted(1, "timezone-less", "entry", created_at=START)
    timezone_less_order = Event(
        event_type=accepted.event_type,
        created_at=accepted.created_at,
        seq=accepted.seq,
        payload={**accepted.payload, "created_at": "2026-01-02T14:30:00"},
    )

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        replay_local_paper_decision_pnl((timezone_less_order,))


def test_decision_pnl_replay_uses_append_order_not_date_label_timestamps() -> None:
    result = replay_local_paper_decision_pnl(
        (
            _accepted(
                1,
                "date-labeled",
                "entry",
                created_at=START + timedelta(hours=5),
            ),
            _fill(2, "date-labeled", created_at=START, price="100"),
        )
    )

    assert result.aggregate.local_paper_fill_count == 1
    assert result.closed_segments == ()
    assert result.aggregate.open_quantity == Decimal("1")


def test_decision_pnl_replay_ignores_other_routes() -> None:
    events = (
        _accepted(1, "buy", "entry", created_at=START),
        _fill(2, "buy", created_at=START + timedelta(minutes=1), price="100"),
        _accepted(
            3,
            "sell",
            "exit",
            created_at=START + timedelta(minutes=2),
            side="sell",
        ),
        _fill(
            4,
            "sell",
            created_at=START + timedelta(minutes=3),
            side="sell",
            price="101",
        ),
        _fill(
            5,
            "foreign",
            created_at=START + timedelta(minutes=4),
            side="sell",
            source=BROKER_DISABLED_SOURCE,
            price="1",
        ),
    )

    result = replay_local_paper_decision_pnl(events)

    assert result.aggregate == replay_local_paper_realized_pnl(events)
    assert result.aggregate.local_paper_fill_count == 2
    assert len(result.closed_segments) == 1
    assert result.closed_segments[0].realized_after_cost_pnl == Decimal("1")


def test_decision_pnl_replay_is_offline_and_does_not_read_credentials(monkeypatch) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("decision PnL replay must not open network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("decision PnL replay must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = replay_local_paper_decision_pnl(
        (
            _accepted(1, "buy", "entry", created_at=START),
            _fill(2, "buy", created_at=START + timedelta(minutes=1)),
        )
    )

    assert result.aggregate.local_paper_fill_count == 1
    assert result.aggregate.open_quantity == Decimal("1")

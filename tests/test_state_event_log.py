from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

from thericher_v2.state import Event, EventStore


def test_event_store_replays_positions_and_decisions(tmp_path) -> None:
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    store.append(
        Event(
            event_type="ensemble_decision",
            created_at=datetime(2026, 1, 2, 14, 35, tzinfo=UTC),
            payload={
                "market": "US",
                "symbol": "AAPL",
                "action": "buy",
                "confidence": "0.7",
            },
        )
    )
    store.append(
        Event(
            event_type="fill",
            created_at=datetime(2026, 1, 2, 14, 36, tzinfo=UTC),
            payload={
                "market": "US",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "2",
                "price": "100",
            },
        )
    )
    store.append(
        Event(
            event_type="fill",
            created_at=datetime(2026, 1, 2, 14, 37, tzinfo=UTC),
            payload={
                "market": "US",
                "symbol": "AAPL",
                "side": "sell",
                "quantity": "0.5",
                "price": "101",
            },
        )
    )

    replay = store.replay()

    assert replay.positions[("US", "AAPL")] == Decimal("1.5")
    assert replay.latest_decisions[("US", "AAPL")]["action"] == "buy"
    assert [event.seq for event in store.iter_events()] == [1, 2, 3]

    with sqlite3.connect(tmp_path / "state.sqlite") as conn:
        quantity = conn.execute(
            "select quantity from positions where market='US' and symbol='AAPL'"
        ).fetchone()[0]
    assert quantity == "1.5"

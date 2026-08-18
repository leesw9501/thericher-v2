from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal

import thericher_v2.state.event_log as event_log
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

    with closing(sqlite3.connect(tmp_path / "state.sqlite")) as conn:
        quantity = conn.execute(
            "select quantity from positions where market='US' and symbol='AAPL'"
        ).fetchone()[0]
    assert quantity == "1.5"


def test_event_store_can_defer_sqlite_rebuild_for_bounded_batch_work(tmp_path) -> None:
    store = EventStore(
        tmp_path / "state.sqlite",
        tmp_path / "events.jsonl",
        rebuild_sqlite_on_append=False,
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

    assert store.replay().positions[("US", "AAPL")] == Decimal("2")
    assert not (tmp_path / "state.sqlite").exists()

    store.rebuild_sqlite()

    with closing(sqlite3.connect(tmp_path / "state.sqlite")) as conn:
        quantity = conn.execute(
            "select quantity from positions where market='US' and symbol='AAPL'"
        ).fetchone()[0]
    assert quantity == "2"


def test_event_store_closes_each_sqlite_connection(monkeypatch, tmp_path) -> None:
    class TrackingConnection(sqlite3.Connection):
        was_closed = False

        def close(self) -> None:
            self.was_closed = True
            super().close()

    connections: list[TrackingConnection] = []
    original_connect = event_log.sqlite3.connect

    def tracking_connect(*args, **kwargs) -> TrackingConnection:
        kwargs["factory"] = TrackingConnection
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(event_log.sqlite3, "connect", tracking_connect)
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
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

    assert connections
    assert all(connection.was_closed for connection in connections)

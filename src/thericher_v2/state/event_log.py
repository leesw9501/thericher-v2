"""Append-only event log with rebuildable SQLite views."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.serialization import to_jsonable

_DECISION_EVENT_TYPES = frozenset(
    {"ensemble_decision", "daily_comparator_decision", "daily_relative_strength_decision"}
)


@dataclass(frozen=True)
class Event:
    event_type: str
    created_at: datetime
    payload: dict[str, Any]
    seq: int = 0
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        if not self.event_type:
            raise ValueError("event_type is required")
        if self.seq < 0:
            raise ValueError("seq must be non-negative")

    def with_seq(self, seq: int) -> Event:
        return Event(
            event_type=self.event_type,
            created_at=self.created_at,
            payload=self.payload,
            seq=seq,
            schema_version=self.schema_version,
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "seq": self.seq,
            "event_type": self.event_type,
            "created_at": self.created_at.isoformat(),
            "payload": to_jsonable(self.payload),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Event:
        created_at = datetime.fromisoformat(str(record["created_at"])).astimezone(UTC)
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")
        return cls(
            event_type=str(record["event_type"]),
            created_at=created_at,
            payload=payload,
            seq=int(record.get("seq", 0)),
            schema_version=int(record.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass(frozen=True)
class ReplayState:
    positions: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    latest_decisions: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)


class EventStore:
    def __init__(
        self,
        db_path: Path,
        jsonl_path: Path,
        *,
        rebuild_sqlite_on_append: bool = True,
    ) -> None:
        self.db_path = db_path
        self.jsonl_path = jsonl_path
        if not isinstance(rebuild_sqlite_on_append, bool):
            raise ValueError("rebuild_sqlite_on_append must be boolean")
        self.rebuild_sqlite_on_append = rebuild_sqlite_on_append

    def bootstrap(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("create table if not exists schema_version (version integer not null)")
            count = conn.execute("select count(*) from schema_version").fetchone()[0]
            if count == 0:
                conn.execute("insert into schema_version(version) values (?)", (SCHEMA_VERSION,))
            self._create_views(conn)

    def append(self, event: Event) -> Event:
        if self.rebuild_sqlite_on_append:
            self.bootstrap()
        else:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        seq = self.next_seq()
        event = event.with_seq(seq)
        with self.jsonl_path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(event.to_record(), sort_keys=True, separators=(",", ":")))
            file.write("\n")
        if self.rebuild_sqlite_on_append:
            self.rebuild_sqlite()
        return event

    def next_seq(self) -> int:
        max_seq = 0
        for event in self.iter_events():
            max_seq = max(max_seq, event.seq)
        return max_seq + 1

    def iter_events(self) -> Iterable[Event]:
        if not self.jsonl_path.exists():
            return []
        events: list[Event] = []
        with self.jsonl_path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
                events.append(Event.from_record(record))
        return events

    def replay(self) -> ReplayState:
        positions: dict[tuple[str, str], Decimal] = {}
        latest_decisions: dict[tuple[str, str], dict[str, Any]] = {}
        for event in sorted(self.iter_events(), key=lambda item: item.seq):
            payload = event.payload
            if event.event_type in _DECISION_EVENT_TYPES:
                market = payload.get("market")
                symbol = payload.get("symbol")
                if isinstance(market, str) and market and isinstance(symbol, str) and symbol:
                    key = (market.upper(), symbol.upper())
                    latest_decisions[key] = payload
            elif event.event_type == "fill":
                key = (str(payload["market"]).upper(), str(payload["symbol"]).upper())
                quantity = Decimal(str(payload["quantity"]))
                side = str(payload["side"])
                signed = quantity if side == "buy" else -quantity
                positions[key] = positions.get(key, Decimal("0")) + signed
        return ReplayState(positions=positions, latest_decisions=latest_decisions)

    def rebuild_sqlite(self) -> None:
        self.bootstrap()
        events = sorted(self.iter_events(), key=lambda item: item.seq)
        replay = self.replay()
        with sqlite3.connect(self.db_path) as conn:
            self._create_views(conn)
            conn.execute("delete from events")
            conn.execute("delete from positions")
            conn.execute("delete from latest_decisions")
            for event in events:
                conn.execute(
                    """
                    insert into events(seq, event_type, created_at, payload_json)
                    values (?, ?, ?, ?)
                    """,
                    (
                        event.seq,
                        event.event_type,
                        event.created_at.isoformat(),
                        json.dumps(event.payload, sort_keys=True),
                    ),
                )
            for (market, symbol), quantity in replay.positions.items():
                conn.execute(
                    "insert into positions(market, symbol, quantity) values (?, ?, ?)",
                    (market, symbol, str(quantity)),
                )
            for (market, symbol), decision in replay.latest_decisions.items():
                conn.execute(
                    """
                    insert into latest_decisions(market, symbol, action, confidence, payload_json)
                    values (?, ?, ?, ?, ?)
                    """,
                    (
                        market,
                        symbol,
                        str(decision.get("action", "")),
                        str(decision.get("confidence", "")),
                        json.dumps(decision, sort_keys=True),
                    ),
                )

    def _create_views(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            create table if not exists events (
              seq integer primary key,
              event_type text not null,
              created_at text not null,
              payload_json text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists positions (
              market text not null,
              symbol text not null,
              quantity text not null,
              primary key (market, symbol)
            )
            """
        )
        conn.execute(
            """
            create table if not exists latest_decisions (
              market text not null,
              symbol text not null,
              action text not null,
              confidence text not null,
              payload_json text not null,
              primary key (market, symbol)
            )
            """
        )

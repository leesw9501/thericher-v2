"""Read model for the interim local dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from thericher_v2.execution.emergency import EmergencyStore
from thericher_v2.serialization import to_jsonable
from thericher_v2.state.event_log import EventStore


@dataclass(frozen=True)
class DashboardSnapshot:
    mode: str
    heartbeat_utc: str
    status: str
    stop_new_orders: bool
    cancel_open_orders_requested: bool
    position_count: int
    latest_decision_count: int
    cash_by_currency: dict[str, str]
    message: str

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


def build_snapshot(
    event_store: EventStore,
    emergency_store: EmergencyStore,
    mode: str = "off",
) -> DashboardSnapshot:
    replay = event_store.replay()
    emergency = emergency_store.read()
    return DashboardSnapshot(
        mode=mode,
        heartbeat_utc=datetime.now(UTC).isoformat(),
        status="local_monitor_only",
        stop_new_orders=emergency.stop_new_orders,
        cancel_open_orders_requested=emergency.cancel_open_orders_requested,
        position_count=sum(1 for value in replay.positions.values() if value != Decimal("0")),
        latest_decision_count=len(replay.latest_decisions),
        cash_by_currency={},
        message="No broker adapter is active in the interim foundation.",
    )

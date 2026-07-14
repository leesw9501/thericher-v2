"""Local emergency-state persistence.

This module does not call a broker. It records operator intent so the future
execution adapter can block new orders or cancel open orders.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.contracts import EmergencyState
from thericher_v2.serialization import to_jsonable


class EmergencyStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> EmergencyState:
        if not self.path.exists():
            return EmergencyState(
                stop_new_orders=False,
                cancel_open_orders_requested=False,
                reason="default_clear",
                updated_at=datetime.now(UTC),
            )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return EmergencyState(
            stop_new_orders=bool(payload.get("stop_new_orders")),
            cancel_open_orders_requested=bool(payload.get("cancel_open_orders_requested")),
            reason=str(payload.get("reason", "")),
            updated_at=datetime.fromisoformat(str(payload["updated_at"])).astimezone(UTC),
        )

    def write(self, state: EmergencyState) -> EmergencyState:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(to_jsonable(state), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return state

    def stop_new_orders(self, reason: str) -> EmergencyState:
        current = self.read()
        return self.write(
            EmergencyState(
                stop_new_orders=True,
                cancel_open_orders_requested=current.cancel_open_orders_requested,
                reason=reason,
                updated_at=datetime.now(UTC),
            )
        )

    def request_cancel_open_orders(self, reason: str) -> EmergencyState:
        current = self.read()
        return self.write(
            EmergencyState(
                stop_new_orders=current.stop_new_orders,
                cancel_open_orders_requested=True,
                reason=reason,
                updated_at=datetime.now(UTC),
            )
        )

    def clear(self, reason: str) -> EmergencyState:
        return self.write(
            EmergencyState(
                stop_new_orders=False,
                cancel_open_orders_requested=False,
                reason=reason,
                updated_at=datetime.now(UTC),
            )
        )

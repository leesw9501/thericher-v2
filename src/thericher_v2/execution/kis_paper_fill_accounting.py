"""Private cumulative KIS Paper fills, distinct from local-paper simulations.

Amounts are gross executed consideration, not settled cash or after-fee PnL.
No broker identifiers, credentials, I/O, or submission capability live here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import require_utc


def fill_identity_ref(
    *,
    raw_order_id: str,
    order_at: datetime,
    symbol: str,
    exchange: str,
    side: str,
    quantity: Decimal,
) -> str:
    identity = [
        raw_order_id,
        require_utc(order_at).astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d"),
        symbol,
        exchange,
        side,
        str(quantity.normalize()),
        "USD",
    ]
    return "sha256:" + hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()


@dataclass(frozen=True, repr=False)
class KisPaperCumulativeFill:
    identity_ref: str
    requested_quantity: Decimal
    quantity: Decimal
    gross_amount: Decimal
    observed_at: datetime
    remaining_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"sha256:[0-9a-f]{64}", self.identity_ref) is None:
            raise ValueError("fill identity invalid")
        for value in (self.requested_quantity, self.quantity, self.gross_amount):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("fill numeric field invalid")
        if (
            self.requested_quantity <= 0
            or self.quantity > self.requested_quantity
            or self.requested_quantity != self.requested_quantity.to_integral_value()
            or self.quantity != self.quantity.to_integral_value()
            or (self.quantity == 0) != (self.gross_amount == 0)
        ):
            raise ValueError("fill quantities invalid")
        if self.remaining_quantity is not None and (
            not isinstance(self.remaining_quantity, Decimal)
            or not self.remaining_quantity.is_finite()
            or self.remaining_quantity < 0
            or self.remaining_quantity != self.remaining_quantity.to_integral_value()
            or self.quantity + self.remaining_quantity > self.requested_quantity
        ):
            raise ValueError("fill remaining quantity invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at))

    @property
    def status(self) -> str:
        if self.quantity == 0:
            return "unfilled"
        return "filled" if self.quantity == self.requested_quantity else "partial"

    def advance(self, previous: KisPaperCumulativeFill | None) -> KisPaperCumulativeFill:
        if previous is not None and (
            self.identity_ref != previous.identity_ref
            or self.requested_quantity != previous.requested_quantity
            or self.observed_at < previous.observed_at
            or self.quantity < previous.quantity
            or self.gross_amount < previous.gross_amount
            or (self.quantity == previous.quantity and self.gross_amount != previous.gross_amount)
            or (self.quantity > previous.quantity and self.gross_amount <= previous.gross_amount)
            or (
                self.remaining_quantity is not None
                and previous.remaining_quantity is not None
                and self.remaining_quantity > previous.remaining_quantity
            )
        ):
            raise ValueError("fill cumulative observation conflicts")
        # Store one cumulative total, never add a snapshot as another fill.
        return self

    def to_dict(self) -> dict[str, str]:
        payload = {
            "source": "kis_paper",
            "identity_ref": self.identity_ref,
            "requested_quantity": str(self.requested_quantity),
            "quantity": str(self.quantity),
            "gross_amount": str(self.gross_amount),
            "observed_at": self.observed_at.isoformat(),
        }
        if self.remaining_quantity is not None:
            payload["remaining_quantity"] = str(self.remaining_quantity)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> KisPaperCumulativeFill:
        required_keys = {
            "source",
            "identity_ref",
            "requested_quantity",
            "quantity",
            "gross_amount",
            "observed_at",
        }
        if (
            not isinstance(payload, Mapping)
            or set(payload) not in (required_keys, required_keys | {"remaining_quantity"})
            or payload["source"] != "kis_paper"
            or any(not isinstance(value, str) for value in payload.values())
        ):
            raise ValueError("fill payload invalid")
        return cls(
            identity_ref=payload["identity_ref"],
            requested_quantity=Decimal(payload["requested_quantity"]),
            quantity=Decimal(payload["quantity"]),
            gross_amount=Decimal(payload["gross_amount"]),
            observed_at=datetime.fromisoformat(payload["observed_at"]),
            remaining_quantity=(
                Decimal(payload["remaining_quantity"]) if "remaining_quantity" in payload else None
            ),
        )


@dataclass(frozen=True, repr=False)
class KisPaperExecutionObservation:
    row_count: int
    same_day_order_id_seen: bool
    status: str
    fill: KisPaperCumulativeFill | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            type(self.row_count) is not int
            or self.row_count < 0
            or type(self.same_day_order_id_seen) is not bool
            or self.status
            not in {
                "available",
                "absent",
                "ambiguous",
                "identity_mismatch",
                "fields_invalid",
                "unavailable",
            }
            or (self.status == "available") != (self.fill is not None)
            or (self.fill is not None and not self.same_day_order_id_seen)
        ):
            raise ValueError("execution observation invalid")
        if self.observed_at is not None:
            require_utc(self.observed_at)
            if self.fill is not None and self.fill.observed_at != self.observed_at:
                raise ValueError("execution observation time mismatch")

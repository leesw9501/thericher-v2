"""Broker-neutral deterministic buy decision for the first KIS Paper canary.

This is research-side evidence only.  Execution owns the later conversion into
an idempotent broker intent and every KIS transport detail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION, positive, require_utc

KIS_PAPER_CANARY_BUY_DECISION_SCHEMA_ID: Final = "kis-paper-canary-buy-decision-v1"
KIS_PAPER_CANARY_US_EXCHANGES: Final = frozenset({"NASD", "NYSE", "AMEX"})

_US_SYMBOL = re.compile(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*")


@dataclass(frozen=True)
class KisPaperCanaryBuyDecision:
    """A fixed-shape US limit-buy decision with no broker request fields.

    ``exchange`` is intentionally explicit and must not be inferred from a
    ticker.  The contract is useful to the paper-trading loop because it makes
    the narrow canary decision reproducible before Execution applies account,
    risk, persistence, reconciliation, and transport concerns.
    """

    decision_id: str
    symbol: str
    exchange: str
    quantity: Decimal
    limit_price: Decimal
    decision_as_of: datetime
    valid_until: datetime
    schema_id: str = KIS_PAPER_CANARY_BUY_DECISION_SCHEMA_ID
    market: Literal["US"] = "US"
    side: Literal["buy"] = "buy"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, str) or not self.decision_id.strip():
            raise ValueError("decision_id must be nonempty")
        if not isinstance(self.schema_id, str) or not self.schema_id.strip():
            raise ValueError("schema_id must be nonempty")
        if self.market != "US":
            raise ValueError("canary decision market must be US")
        if self.side != "buy":
            raise ValueError("canary decision side must be buy")
        _require_uppercase_symbol(self.symbol)
        _require_explicit_us_exchange(self.exchange)
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        object.__setattr__(self, "limit_price", positive(self.limit_price, "limit_price"))
        if self.quantity != self.quantity.to_integral_value():
            raise ValueError("canary decision quantity must be whole shares")
        object.__setattr__(
            self,
            "decision_as_of",
            require_utc(self.decision_as_of, "decision_as_of"),
        )
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until <= self.decision_as_of:
            raise ValueError("valid_until must follow decision_as_of")


def _require_uppercase_symbol(value: str) -> None:
    if not isinstance(value, str) or _US_SYMBOL.fullmatch(value) is None:
        raise ValueError("canary decision symbol must be an uppercase US ticker")


def _require_explicit_us_exchange(value: str) -> None:
    if not isinstance(value, str) or value not in KIS_PAPER_CANARY_US_EXCHANGES:
        raise ValueError("canary decision exchange must be an uppercase supported US exchange")

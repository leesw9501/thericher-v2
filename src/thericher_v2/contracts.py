"""Small immutable contracts shared by the v2 engine.

The contracts intentionally avoid broker-specific fields. Market adapters can
translate these objects into KIS, paper, or future broker payloads.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

SCHEMA_VERSION = 1
Side = Literal["buy", "sell"]
Action = Literal["buy", "sell", "hold"]
TargetAction = Literal["enter", "hold", "reduce", "exit", "abstain"]
TargetInputStatus = Literal[
    "ready",
    "missing",
    "stale",
    "incomplete",
    "duplicate",
    "non_contiguous",
    "misaligned",
    "future",
    "unqualified",
]


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M10 = "10m"
    H1 = "1h"
    H3 = "3h"
    D1 = "1d"

    @property
    def duration(self) -> timedelta:
        return {
            Timeframe.M1: timedelta(minutes=1),
            Timeframe.M5: timedelta(minutes=5),
            Timeframe.M10: timedelta(minutes=10),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.H3: timedelta(hours=3),
            Timeframe.D1: timedelta(days=1),
        }[self]


def require_utc(value: datetime, field_name: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    normalized = value.astimezone(UTC)
    if normalized.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be UTC")
    return normalized


def decimal_value(value: Decimal | int | str, field_name: str) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def non_negative(value: Decimal | int | str, field_name: str) -> Decimal:
    result = decimal_value(value, field_name)
    if result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def positive(value: Decimal | int | str, field_name: str) -> Decimal:
    result = decimal_value(value, field_name)
    if result <= 0:
        raise ValueError(f"{field_name} must be positive")
    return result


def decision_instrument_binding_ref(
    *,
    symbol: str,
    market: str,
    decision_class: str,
) -> str:
    """Return an opaque commitment to execution-critical instrument identity."""

    return _opaque_binding_ref(
        kind="decision_instrument_binding_v1",
        payload={
            "symbol": _binding_identity_text(symbol, "symbol"),
            "market": _binding_identity_text(market, "market"),
            "decision_class": _binding_decision_class(decision_class),
        },
    )


def decision_target_binding_ref(
    *,
    symbol: str,
    market: str,
    decision_class: str,
    target_exposure: Decimal | int | str,
) -> str:
    """Return an opaque commitment to one local target-exposure decision."""

    exposure = decimal_value(target_exposure, "target_exposure")
    if exposure < 0 or exposure > Decimal("1"):
        raise ValueError("target_exposure must be between 0 and 1")
    return _opaque_binding_ref(
        kind="decision_target_binding_v1",
        payload={
            "symbol": _binding_identity_text(symbol, "symbol"),
            "market": _binding_identity_text(market, "market"),
            "decision_class": _binding_decision_class(decision_class),
            "target_exposure": _decimal_marker(exposure),
        },
    )


def _opaque_binding_ref(*, kind: str, payload: dict[str, str]) -> str:
    encoded = json.dumps(
        {"kind": kind, **payload},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return "ref:" + hashlib.sha256(encoded).hexdigest()


def _binding_identity_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be nonempty")
    return value.upper()


def _binding_decision_class(value: str) -> str:
    if value not in {"enter", "exit", "abstain"}:
        raise ValueError("decision_class is invalid")
    return value


def _decimal_marker(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class Bar:
    symbol: str
    market: str
    timeframe: Timeframe
    start_ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    complete: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        object.__setattr__(self, "start_ts", require_utc(self.start_ts, "start_ts"))
        object.__setattr__(self, "open", positive(self.open, "open"))
        object.__setattr__(self, "high", positive(self.high, "high"))
        object.__setattr__(self, "low", positive(self.low, "low"))
        object.__setattr__(self, "close", positive(self.close, "close"))
        object.__setattr__(self, "volume", non_negative(self.volume, "volume"))
        if not isinstance(self.complete, bool):
            raise TypeError("complete must be bool")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("bar high/low must contain open and close")

    @property
    def end_ts(self) -> datetime:
        return self.start_ts + self.timeframe.duration


@dataclass(frozen=True)
class Signal:
    symbol: str
    market: str
    action: Action
    strength: Decimal
    reason: str
    timeframe: Timeframe
    generated_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "strength", non_negative(self.strength, "strength"))
        object.__setattr__(self, "generated_at", require_utc(self.generated_at, "generated_at"))
        if self.strength > Decimal("1"):
            raise ValueError("strength must be between 0 and 1")


@dataclass(frozen=True)
class ModelPrediction:
    model_id: str
    model_version: str
    symbol: str
    market: str
    signal: Signal
    confidence: Decimal
    expected_edge_bps: Decimal
    feature_window_end: datetime
    schema_version: int = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "confidence", non_negative(self.confidence, "confidence"))
        object.__setattr__(
            self,
            "expected_edge_bps",
            decimal_value(self.expected_edge_bps, "expected_edge_bps"),
        )
        object.__setattr__(
            self,
            "feature_window_end",
            require_utc(self.feature_window_end, "feature_window_end"),
        )
        if self.confidence > Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class EnsembleDecision:
    symbol: str
    market: str
    action: Action
    confidence: Decimal
    expected_edge_bps: Decimal
    risk_score: Decimal
    prediction_ids: tuple[str, ...]
    decided_at: datetime
    schema_version: int = SCHEMA_VERSION
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "confidence", non_negative(self.confidence, "confidence"))
        object.__setattr__(
            self,
            "expected_edge_bps",
            decimal_value(self.expected_edge_bps, "expected_edge_bps"),
        )
        object.__setattr__(self, "risk_score", non_negative(self.risk_score, "risk_score"))
        object.__setattr__(self, "decided_at", require_utc(self.decided_at, "decided_at"))
        if self.confidence > Decimal("1") or self.risk_score > Decimal("1"):
            raise ValueError("confidence and risk_score must be between 0 and 1")


@dataclass(frozen=True)
class TargetExposureProposal:
    """A model-side target state that Execution may map to an order delta."""

    proposal_id: str
    symbol: str
    market: str
    action: TargetAction
    target_exposure: Decimal
    confidence: Decimal
    feature_schema_id: str
    input_status: TargetInputStatus
    decided_at: datetime
    valid_until: datetime
    feature_window_end: datetime | None
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.feature_schema_id.strip():
            raise ValueError("target proposal identifiers must be nonempty")
        if not self.reason.strip():
            raise ValueError("target proposal reason must be nonempty")
        if self.action not in {"enter", "hold", "reduce", "exit", "abstain"}:
            raise ValueError("target proposal action is invalid")
        if self.input_status not in {
            "ready",
            "missing",
            "stale",
            "incomplete",
            "duplicate",
            "non_contiguous",
            "misaligned",
            "future",
            "unqualified",
        }:
            raise ValueError("target proposal input_status is invalid")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(
            self,
            "target_exposure",
            non_negative(self.target_exposure, "target_exposure"),
        )
        object.__setattr__(self, "confidence", non_negative(self.confidence, "confidence"))
        object.__setattr__(self, "decided_at", require_utc(self.decided_at, "decided_at"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.feature_window_end is not None:
            object.__setattr__(
                self,
                "feature_window_end",
                require_utc(self.feature_window_end, "feature_window_end"),
            )
        if self.target_exposure > Decimal("1") or self.confidence > Decimal("1"):
            raise ValueError("target exposure and confidence must be between 0 and 1")
        if self.valid_until < self.decided_at:
            raise ValueError("valid_until cannot precede decided_at")
        if self.feature_window_end is not None and self.feature_window_end > self.decided_at:
            raise ValueError("feature_window_end cannot follow decided_at")
        if self.input_status != "ready" and self.action != "abstain":
            raise ValueError("unready inputs must abstain")
        if self.action in {"abstain", "exit"} and self.target_exposure != 0:
            raise ValueError("abstain and exit proposals must target zero exposure")
        if self.action == "enter" and self.target_exposure == 0:
            raise ValueError("enter proposals must target positive exposure")


@dataclass(frozen=True)
class OrderIntent:
    client_order_id: str
    symbol: str
    market: str
    side: Side
    quantity: Decimal
    limit_price: Decimal | None
    decision_id: str
    created_at: datetime
    valid_until: datetime | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", positive(self.limit_price, "limit_price"))
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        if self.valid_until is not None:
            valid_until = require_utc(self.valid_until, "valid_until")
            if valid_until <= self.created_at:
                raise ValueError("valid_until must be after created_at")
            object.__setattr__(self, "valid_until", valid_until)


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    market: str
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())
        object.__setattr__(self, "quantity", decimal_value(self.quantity, "quantity"))
        object.__setattr__(self, "average_price", non_negative(self.average_price, "average_price"))
        object.__setattr__(self, "market_price", non_negative(self.market_price, "market_price"))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))

    @property
    def market_value(self) -> Decimal:
        return self.quantity * self.market_price


@dataclass(frozen=True)
class PortfolioSnapshot:
    base_currency: str
    cash: Decimal
    equity: Decimal
    positions: tuple[PositionSnapshot, ...]
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_currency", self.base_currency.upper())
        object.__setattr__(self, "cash", decimal_value(self.cash, "cash"))
        object.__setattr__(self, "equity", decimal_value(self.equity, "equity"))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class RiskLimits:
    max_position_notional: Decimal
    max_daily_loss: Decimal
    max_orders_per_day: int
    max_open_orders: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_position_notional",
            positive(self.max_position_notional, "max_position_notional"),
        )
        object.__setattr__(self, "max_daily_loss", positive(self.max_daily_loss, "max_daily_loss"))
        if self.max_orders_per_day <= 0:
            raise ValueError("max_orders_per_day must be positive")
        if self.max_open_orders < 0:
            raise ValueError("max_open_orders must be non-negative")


@dataclass(frozen=True)
class EmergencyState:
    stop_new_orders: bool
    cancel_open_orders_requested: bool
    reason: str
    updated_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "updated_at", require_utc(self.updated_at, "updated_at"))

    @property
    def blocks_new_orders(self) -> bool:
        return self.stop_new_orders

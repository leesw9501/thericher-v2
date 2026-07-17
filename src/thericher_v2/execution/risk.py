"""One deterministic, side-effect-free pre-submit risk decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    EmergencyState,
    PositionSnapshot,
    RiskLimits,
    decimal_value,
    non_negative,
    positive,
)

from .broker import (
    AccountSnapshot,
    BrokerOrderRequest,
    BuyingPowerSnapshot,
    InMemoryBrokerTransport,
    OpenOrderSnapshot,
    ReconciliationResult,
)

RiskReason = Literal[
    "intent_not_durable",
    "risk_limits_missing",
    "account_missing",
    "buying_power_missing",
    "open_orders_missing",
    "reconciliation_missing",
    "emergency_state_missing",
    "reference_price_missing",
    "position_missing",
    "realized_daily_pnl_missing",
    "orders_today_missing",
    "evidence_age_invalid",
    "evaluated_at_not_utc",
    "evidence_not_utc",
    "evidence_from_future",
    "evidence_stale",
    "reference_price_invalid",
    "position_invalid",
    "position_mismatch",
    "position_quantity_invalid",
    "position_price_invalid",
    "realized_daily_pnl_invalid",
    "orders_today_invalid",
    "currency_mismatch",
    "reconciliation_unsafe",
    "reconciliation_duplicate",
    "reconciliation_mismatch",
    "reconciliation_unknown",
    "reconciliation_stale",
    "emergency_stop_active",
    "open_orders_incomplete",
    "open_order_conflict",
    "max_orders_per_day_exceeded",
    "max_open_orders_exceeded",
    "sell_exceeds_long_position",
    "buying_power_exceeded",
    "max_position_notional_exceeded",
    "max_daily_loss_exceeded",
]


@dataclass(frozen=True)
class PreSubmitRiskDecision:
    allowed: bool
    reasons: tuple[RiskReason, ...]
    notional: Decimal | None
    projected_position_notional: Decimal | None
    evaluated_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.notional is not None:
            object.__setattr__(self, "notional", non_negative(self.notional, "notional"))
        if self.projected_position_notional is not None:
            object.__setattr__(
                self,
                "projected_position_notional",
                non_negative(self.projected_position_notional, "projected_position_notional"),
            )
        if self.allowed and (self.reasons or self.notional is None):
            raise ValueError("allowed decision requires notional and no reasons")
        if not self.allowed and not self.reasons:
            raise ValueError("disallowed decision requires at least one reason")


def evaluate_pre_submit_risk(
    *,
    request: BrokerOrderRequest,
    transport: InMemoryBrokerTransport,
    risk_limits: RiskLimits | None,
    account: AccountSnapshot | None,
    buying_power: BuyingPowerSnapshot | None,
    open_orders: OpenOrderSnapshot | None,
    reconciliation: ReconciliationResult | None,
    emergency_state: EmergencyState | None,
    reference_price: Decimal | None,
    position: PositionSnapshot | None,
    realized_daily_pnl: Decimal | None,
    orders_today: int | None,
    evaluated_at: datetime,
    max_evidence_age: timedelta | None,
) -> PreSubmitRiskDecision:
    reasons: list[RiskReason] = []
    if not transport.is_intent_durable(request):
        _add(reasons, "intent_not_durable")

    for evidence, reason in (
        (risk_limits, "risk_limits_missing"),
        (account, "account_missing"),
        (open_orders, "open_orders_missing"),
        (reconciliation, "reconciliation_missing"),
        (emergency_state, "emergency_state_missing"),
        (reference_price, "reference_price_missing"),
        (position, "position_missing"),
        (realized_daily_pnl, "realized_daily_pnl_missing"),
        (orders_today, "orders_today_missing"),
    ):
        if evidence is None:
            _add(reasons, reason)
    if request.side == "buy" and buying_power is None:
        _add(reasons, "buying_power_missing")

    age_is_valid = isinstance(max_evidence_age, timedelta) and max_evidence_age > timedelta(0)
    if not age_is_valid:
        _add(reasons, "evidence_age_invalid")
    evaluated_at_is_utc = _is_utc(evaluated_at)
    if not evaluated_at_is_utc:
        _add(reasons, "evaluated_at_not_utc")

    for timestamp in (
        None if account is None else account.captured_at,
        (None if request.side == "sell" or buying_power is None else buying_power.captured_at),
        None if open_orders is None else open_orders.captured_at,
        None if reconciliation is None else reconciliation.reconciled_at,
        None if emergency_state is None else emergency_state.updated_at,
    ):
        if timestamp is not None:
            _evidence_time_is_valid(
                timestamp,
                evaluated_at=evaluated_at,
                evaluated_at_is_utc=evaluated_at_is_utc,
                max_evidence_age=max_evidence_age,
                age_is_valid=age_is_valid,
                reasons=reasons,
            )

    reference_value: Decimal | None = None
    if reference_price is not None:
        try:
            reference_value = positive(reference_price, "reference_price")
        except (ValueError, ArithmeticError):
            _add(reasons, "reference_price_invalid")

    position_quantity: Decimal | None = None
    position_market_price: Decimal | None = None
    position_identity_valid = False
    position_values_valid = False
    position_time_valid = False
    if position is not None:
        if not isinstance(position, PositionSnapshot):
            _add(reasons, "position_invalid")
        else:
            position_identity_valid = (
                position.symbol == request.symbol and position.market == request.market
            )
            if not position_identity_valid:
                _add(reasons, "position_mismatch")
            try:
                position_quantity = decimal_value(position.quantity, "position.quantity")
                if position_quantity < 0:
                    position_quantity = None
                    _add(reasons, "position_quantity_invalid")
            except (ValueError, ArithmeticError):
                _add(reasons, "position_quantity_invalid")
            try:
                average_price = non_negative(position.average_price, "position.average_price")
                position_market_price = non_negative(
                    position.market_price,
                    "position.market_price",
                )
                if position_quantity is not None:
                    prices_match_quantity = (
                        position_quantity == 0 and average_price == 0 and position_market_price == 0
                    ) or (position_quantity > 0 and average_price > 0 and position_market_price > 0)
                    if not prices_match_quantity:
                        position_market_price = None
                        _add(reasons, "position_price_invalid")
            except (ValueError, ArithmeticError):
                _add(reasons, "position_price_invalid")
            position_values_valid = (
                position_quantity is not None and position_market_price is not None
            )
            position_time_valid = _evidence_time_is_valid(
                position.captured_at,
                evaluated_at=evaluated_at,
                evaluated_at_is_utc=evaluated_at_is_utc,
                max_evidence_age=max_evidence_age,
                age_is_valid=age_is_valid,
                reasons=reasons,
            )

    position_is_usable = position_identity_valid and position_values_valid and position_time_valid
    is_long_reduction = (
        request.side == "sell"
        and position_is_usable
        and position_quantity is not None
        and request.quantity <= position_quantity
    )
    if (
        request.side == "sell"
        and position_quantity is not None
        and request.quantity > position_quantity
    ):
        _add(reasons, "sell_exceeds_long_position")

    notional: Decimal | None = None
    projected_notional: Decimal | None = None
    if reference_value is not None:
        risk_price = reference_value
        if position_market_price is not None:
            risk_price = max(risk_price, position_market_price)
        if request.side == "buy":
            if request.limit_price is not None:
                risk_price = max(risk_price, request.limit_price)
            notional = request.quantity * risk_price
            if position_is_usable and position_quantity is not None:
                projected_notional = (position_quantity + request.quantity) * risk_price
        elif position_market_price is not None:
            notional = request.quantity * risk_price
            if is_long_reduction and position_quantity is not None:
                projected_notional = (position_quantity - request.quantity) * risk_price

    daily_pnl: Decimal | None = None
    if realized_daily_pnl is not None:
        try:
            daily_pnl = decimal_value(realized_daily_pnl, "realized_daily_pnl")
        except (ValueError, ArithmeticError):
            _add(reasons, "realized_daily_pnl_invalid")
    if orders_today is not None and (
        not isinstance(orders_today, int) or isinstance(orders_today, bool) or orders_today < 0
    ):
        _add(reasons, "orders_today_invalid")

    if request.side == "buy" and account is not None and buying_power is not None:
        if account.currency != buying_power.currency:
            _add(reasons, "currency_mismatch")
    if reconciliation is not None:
        if not reconciliation.safe_to_submit:
            _add(reasons, "reconciliation_unsafe")
        if reconciliation.duplicates:
            _add(reasons, "reconciliation_duplicate")
        if reconciliation.mismatches:
            _add(reasons, "reconciliation_mismatch")
        if reconciliation.outcome_unknown_ids:
            _add(reasons, "reconciliation_unknown")
        if reconciliation.stale_snapshots:
            _add(reasons, "reconciliation_stale")
    if emergency_state is not None and emergency_state.blocks_new_orders and not is_long_reduction:
        _add(reasons, "emergency_stop_active")
    if open_orders is not None:
        if not open_orders.complete:
            _add(reasons, "open_orders_incomplete")
        open_ids = tuple(order.client_order_id for order in open_orders.orders)
        if request.client_order_id in open_ids or len(open_ids) != len(set(open_ids)):
            _add(reasons, "open_order_conflict")

    if risk_limits is not None:
        if isinstance(orders_today, int) and not isinstance(orders_today, bool):
            if orders_today + 1 > risk_limits.max_orders_per_day and not is_long_reduction:
                _add(reasons, "max_orders_per_day_exceeded")
        if (
            open_orders is not None
            and len(open_orders.orders) + 1 > risk_limits.max_open_orders
            and not is_long_reduction
        ):
            _add(reasons, "max_open_orders_exceeded")
        if projected_notional is not None and not is_long_reduction:
            if projected_notional > risk_limits.max_position_notional:
                _add(reasons, "max_position_notional_exceeded")
        if (
            daily_pnl is not None
            and daily_pnl <= -risk_limits.max_daily_loss
            and not is_long_reduction
        ):
            _add(reasons, "max_daily_loss_exceeded")
    if request.side == "buy" and buying_power is not None and notional is not None:
        if notional > buying_power.available_cash or notional > buying_power.max_order_notional:
            _add(reasons, "buying_power_exceeded")

    return PreSubmitRiskDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        notional=notional,
        projected_position_notional=projected_notional,
        evaluated_at=evaluated_at,
    )


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _evidence_time_is_valid(
    value: datetime,
    *,
    evaluated_at: datetime,
    evaluated_at_is_utc: bool,
    max_evidence_age: timedelta | None,
    age_is_valid: bool,
    reasons: list[RiskReason],
) -> bool:
    if not isinstance(value, datetime) or not _is_utc(value):
        _add(reasons, "evidence_not_utc")
        return False
    if not evaluated_at_is_utc or not age_is_valid or max_evidence_age is None:
        return False
    if value > evaluated_at:
        _add(reasons, "evidence_from_future")
        return False
    if evaluated_at - value > max_evidence_age:
        _add(reasons, "evidence_stale")
        return False
    return True


def _add(reasons: list[RiskReason], reason: RiskReason) -> None:
    if reason not in reasons:
        reasons.append(reason)

"""Pure shared-cash, fractional-mark research ledger; no broker/fill parity claim."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, Underflow, localcontext
from fractions import Fraction
from functools import wraps

SYMBOLS = ("SPY", "QQQ", "IWM")
PRECISION = 50
SOLVER_STEPS = 192
_ZERO = Decimal(0)
_ONE = Decimal(1)
_ZEROS = (_ZERO, _ZERO, _ZERO)
_RELATIVE_ERROR = Decimal("1e-45")


class ThreeAssetNavError(ValueError):
    """Categorical invalid/unavailable input or numeric failure, without values."""


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ThreeAssetNavError(category)


def _amount(value: object, category: str, *, positive: bool = False) -> None:
    _require(
        type(value) is Decimal and value.is_finite() and (value > 0 if positive else value >= 0),
        category,
    )


def _vector(values: object, category: str, *, positive: bool = False) -> None:
    _require(type(values) is tuple and len(values) == 3, category)
    for value in values:
        _amount(value, category, positive=positive)


def _named(values: Mapping[str, Decimal], category: str) -> tuple[Decimal, Decimal, Decimal]:
    _require(isinstance(values, Mapping) and set(values) == set(SYMBOLS), category)
    return tuple(values[symbol] for symbol in SYMBOLS)


def _decimal(function):
    @wraps(function)
    def call(*args, **kwargs):
        with localcontext(Context(prec=PRECISION, rounding=ROUND_HALF_EVEN)) as context:
            context.traps[Underflow] = True
            try:
                return function(*args, **kwargs)
            except DecimalException:
                raise ThreeAssetNavError("numeric_range") from None

    return call


@dataclass(frozen=True)
class ThreeAssetPrices:
    values: tuple[Decimal, Decimal, Decimal] = field(repr=False)

    def __post_init__(self) -> None:
        _vector(self.values, "prices_invalid", positive=True)

    @classmethod
    def from_mapping(cls, prices: Mapping[str, Decimal]) -> ThreeAssetPrices:
        return cls(_named(prices, "price_symbols_invalid"))


@dataclass(frozen=True)
class ThreeAssetState:
    cash: Decimal = field(repr=False)
    quantities: tuple[Decimal, Decimal, Decimal] = field(default=_ZEROS, repr=False)

    def __post_init__(self) -> None:
        _amount(self.cash, "cash_invalid")
        _vector(self.quantities, "quantities_invalid")

    @classmethod
    def from_mapping(cls, cash: Decimal, quantities: Mapping[str, Decimal]) -> ThreeAssetState:
        return cls(cash, _named(quantities, "quantity_symbols_invalid"))


@dataclass(frozen=True)
class ThreeAssetTrade:
    state: ThreeAssetState = field(repr=False)
    pre_fee_nav: Decimal = field(repr=False)
    post_fee_nav: Decimal = field(repr=False)
    traded_notionals: tuple[Decimal, Decimal, Decimal] = field(repr=False)
    turnover: Decimal = field(repr=False)
    fees: Decimal = field(repr=False)


@dataclass(frozen=True)
class ThreeAssetMark:
    state: ThreeAssetState = field(repr=False)
    notionals: tuple[Decimal, Decimal, Decimal] = field(repr=False)
    nav: Decimal = field(repr=False)


def _weight_total(weights: tuple) -> Fraction:
    _vector(weights, "targets_invalid")
    _require(all(weight <= 1 for weight in weights), "targets_exceed_one")
    total = sum(map(Fraction, weights), Fraction(0))
    _require(total <= 1, "targets_exceed_one")
    return total


@dataclass(frozen=True)
class ThreeAssetDay:
    date: date
    adj_open3: tuple[Decimal, Decimal, Decimal] = field(repr=False)
    adj_close3: tuple[Decimal, Decimal, Decimal] = field(repr=False)

    def __post_init__(self) -> None:
        _require(type(self.date) is date, "date_invalid")
        _vector(self.adj_open3, "prices_invalid", positive=True)
        _vector(self.adj_close3, "prices_invalid", positive=True)


@dataclass(frozen=True)
class ThreeAssetTarget:
    weights3: tuple[Decimal, Decimal, Decimal] = field(repr=False)
    cash_weight: Decimal = field(repr=False)

    def __post_init__(self) -> None:
        total = _weight_total(self.weights3)
        _amount(self.cash_weight, "cash_weight_invalid")
        _require(total + Fraction(self.cash_weight) == 1, "cash_weight_mismatch")


@dataclass(frozen=True)
class ThreeAssetDaily:
    date: date
    nav: Decimal = field(repr=False)
    fees: Decimal = field(repr=False)
    traded_notional: Decimal = field(repr=False)
    cash: Decimal = field(repr=False)
    flat: bool = field(repr=False)
    simple_return: Decimal = field(repr=False)
    log_return: Decimal = field(repr=False)


@dataclass(frozen=True)
class ThreeAssetReplay:
    daily: tuple[ThreeAssetDaily, ...] = field(repr=False)
    final_state: ThreeAssetState = field(repr=False)
    total_fees: Decimal = field(repr=False)
    total_traded_notional: Decimal = field(repr=False)

    @property
    def navs(self) -> tuple[Decimal, ...]:
        return tuple(day.nav for day in self.daily)

    @property
    def simple_returns(self) -> tuple[Decimal, ...]:
        return tuple(day.simple_return for day in self.daily)

    @property
    def log_returns(self) -> tuple[Decimal, ...]:
        return tuple(day.log_return for day in self.daily)

    @property
    def final_nav(self) -> Decimal:
        return self.daily[-1].nav


def _inputs(state: ThreeAssetState, prices: ThreeAssetPrices) -> None:
    _require(type(state) is ThreeAssetState, "state_invalid")
    _require(type(prices) is ThreeAssetPrices, "prices_invalid")
    state.__post_init__()
    prices.__post_init__()


def _fee(cost_bps: Decimal) -> Decimal:
    _amount(cost_bps, "cost_bps_invalid")
    _require(cost_bps <= 100, "cost_bps_invalid")
    return cost_bps / 10000


def _post_fee_nav(nav: Decimal, holdings: tuple, weights: tuple, fee: Decimal) -> Decimal:
    # F(x) = x + f*sum(abs(w*x-h)) - V has slope >= 1-f*sum(w) >= .99.
    # Its unique root is in [0,V]; 192 steps cover the Decimal50 lattice.
    def residual(value):
        turnover = sum((abs(w * value - h) for w, h in zip(weights, holdings, strict=True)), _ZERO)
        return value + fee * turnover - nav

    if nav == 0 or residual(nav) == 0:
        return nav
    lower, upper = _ZERO, nav
    for _ in range(SOLVER_STEPS):
        middle = (lower + upper) / 2
        if middle == lower or middle == upper:
            return min((lower, upper), key=lambda value: abs(residual(value)))
        difference = residual(middle)
        if difference == 0:
            return middle
        if difference > 0:
            upper = middle
        else:
            lower = middle
    raise ThreeAssetNavError("solver_precision")


def _rebalance(
    state: ThreeAssetState,
    prices: ThreeAssetPrices,
    weights: tuple[Decimal, Decimal, Decimal],
    cash_weight: Decimal,
    fee: Decimal,
) -> ThreeAssetTrade:
    holdings = tuple(q * p for q, p in zip(state.quantities, prices.values, strict=True))
    nav = state.cash + sum(holdings, _ZERO)
    post_fee = _post_fee_nav(nav, holdings, weights, fee)
    quantities = tuple(w * post_fee / p for w, p in zip(weights, prices.values, strict=True))
    after = ThreeAssetState(cash_weight * post_fee, quantities)
    actual = tuple(q * p for q, p in zip(after.quantities, prices.values, strict=True))
    traded = tuple(a - h for a, h in zip(actual, holdings, strict=True))
    turnover = sum(map(abs, traded), _ZERO)
    fees = fee * turnover
    marked_nav = after.cash + sum(actual, _ZERO)
    _require(
        abs(marked_nav + fees - nav) <= nav * _RELATIVE_ERROR,
        "cashflow_precision",
    )
    return ThreeAssetTrade(after, nav, marked_nav, traded, turnover, fees)


@_decimal
def rebalance_open(
    state: ThreeAssetState,
    prices: ThreeAssetPrices,
    targets: Mapping[str, Decimal],
    cost_bps: Decimal,
) -> ThreeAssetTrade:
    """Simultaneous OPEN targets on post-fee NAV; residual weight stays in cash."""
    _inputs(state, prices)
    weights = _named(targets, "target_symbols_invalid")
    total = _weight_total(weights)
    # Validate the exact supplied sum; do not round excess weight into eligibility.
    residual = 1 - total
    cash_weight = Decimal(residual.numerator) / Decimal(residual.denominator)
    return _rebalance(state, prices, weights, cash_weight, _fee(cost_bps))


@_decimal
def mark_close(state: ThreeAssetState, prices: ThreeAssetPrices) -> ThreeAssetMark:
    """Mark CLOSE only; the same immutable cash and quantities carry overnight."""
    _inputs(state, prices)
    notionals = tuple(q * p for q, p in zip(state.quantities, prices.values, strict=True))
    return ThreeAssetMark(state, notionals, state.cash + sum(notionals, _ZERO))


@_decimal
def liquidate_close(
    state: ThreeAssetState, prices: ThreeAssetPrices, cost_bps: Decimal
) -> ThreeAssetTrade:
    """Final full liquidation at supplied CLOSE marks, charging all sale notional."""
    _inputs(state, prices)
    return _rebalance(state, prices, _ZEROS, _ONE, _fee(cost_bps))


@_decimal
def replay(
    days: Sequence[ThreeAssetDay],
    targets: Mapping[date, ThreeAssetTarget],
    cost_bps: Decimal,
) -> ThreeAssetReplay:
    """Initial NAV1; supplied OPEN actions, daily CLOSE marks, final CLOSE exit.

    The caller owns calendar alignment and causal target construction. Returns
    include initial entry and final exit: SIMPLE for matching, LOG for utility.
    No policy, matching calculation, broker semantics or price adjustment occurs.
    """
    _require(isinstance(days, Sequence) and len(days) > 0, "days_invalid")
    _require(isinstance(targets, Mapping), "target_dates_invalid")
    records, actions = tuple(days), dict(targets)
    for day in records:
        _require(type(day) is ThreeAssetDay, "day_invalid")
        day.__post_init__()
    _require(
        all(a.date < b.date for a, b in zip(records, records[1:], strict=False)),
        "day_order_invalid",
    )
    dates = {day.date for day in records}
    for key, target in actions.items():
        _require(type(key) is date and key in dates, "target_dates_invalid")
        _require(type(target) is ThreeAssetTarget, "target_invalid")
        target.__post_init__()
    fee = _fee(cost_bps)
    state, previous = ThreeAssetState(_ONE), _ONE
    daily = []
    total_fees = total_notional = _ZERO
    for index, day in enumerate(records):
        paid = traded = _ZERO
        if day.date in actions:
            target = actions[day.date]
            entry = _rebalance(
                state,
                ThreeAssetPrices(day.adj_open3),
                target.weights3,
                target.cash_weight,
                fee,
            )
            state, paid, traded = entry.state, entry.fees, entry.turnover
        close = ThreeAssetPrices(day.adj_close3)
        if index == len(records) - 1:
            exit_trade = _rebalance(state, close, _ZEROS, _ONE, fee)
            state = exit_trade.state
            paid, traded = paid + exit_trade.fees, traded + exit_trade.turnover
        marked = mark_close(state, close)
        _require(marked.nav > 0, "nonpositive_nav")
        growth = marked.nav / previous
        daily.append(
            ThreeAssetDaily(
                day.date,
                marked.nav,
                paid,
                traded,
                state.cash,
                all(quantity == 0 for quantity in state.quantities),
                growth - 1,
                growth.ln(),
            )
        )
        total_fees, total_notional = total_fees + paid, total_notional + traded
        previous = marked.nav
    return ThreeAssetReplay(tuple(daily), state, total_fees, total_notional)

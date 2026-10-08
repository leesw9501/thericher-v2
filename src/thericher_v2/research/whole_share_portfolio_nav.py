"""Pure whole-share, fixed-bank analytical cashflow; not broker replay parity.

SPY/TLT/GLD targets use gross marked NAV and exact supplied cent-lattice prices.
Synthetic fills are immediate, complete and SELL-before-BUY, with no latency,
slippage, interest or dividend adjustment. Explicit per-side fees apply to exact
notional without currency rounding. They reduce analytical cash, not gross target
NAV or entry cost. No native risk cap, source loading or policy is implemented.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Literal

SYMBOLS = ("SPY", "TLT", "GLD")
Prices3 = tuple[Decimal, Decimal, Decimal]
Weight = Decimal | Fraction
Weights3 = tuple[Weight, Weight, Weight]
Quantities3 = tuple[int, int, int]
Amounts3 = tuple[Fraction, Fraction, Fraction]
_ZERO = Fraction(0)
_ZEROS = (_ZERO, _ZERO, _ZERO)
_FLAT = (0, 0, 0)


class WholeShareNavError(ValueError):
    """Categorical invalid input, without prices or other numeric values."""


class WholeShareTradeReason(StrEnum):
    EXECUTED = "executed"
    NO_TARGET_DELTA = "no_target_delta"
    BANK_EXCEEDED = "bank_exceeded"
    ANALYTICAL_CASH_NEGATIVE = "analytical_cash_negative"


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise WholeShareNavError(category)


def _triple(values: object, category: str) -> None:
    _require(type(values) is tuple and len(values) == 3, category)


def _fraction(value: object, category: str) -> Fraction:
    _require(type(value) is Decimal and value.is_finite(), category)
    return Fraction(value)


def _prices(values: Prices3) -> Amounts3:
    _triple(values, "prices_invalid")
    result = tuple(_fraction(value, "prices_invalid") for value in values)
    _require(all(p > 0 and (p * 100).denominator == 1 for p in result), "prices_invalid")
    return result


def _weights(values: Weights3) -> Amounts3:
    _triple(values, "weights_invalid")
    result = tuple(
        value if type(value) is Fraction else _fraction(value, "weights_invalid")
        for value in values
    )
    _require(all(w >= 0 for w in result) and sum(result, _ZERO) <= 1, "weights_invalid")
    return result


def _fee(cost_bps: Decimal) -> Fraction:
    result = _fraction(cost_bps, "cost_bps_invalid")
    _require(result >= 0, "cost_bps_invalid")
    return result / 10000


@dataclass(frozen=True)
class WholeShareState:
    gross_cash: Fraction = field(default=Fraction(10000), repr=False)
    fees_paid: Fraction = field(default=_ZERO, repr=False)
    quantities3: Quantities3 = field(default=_FLAT, repr=False)
    entry_costs3: Amounts3 = field(default=_ZEROS, repr=False)
    basis_usd: Fraction = field(default=Fraction(100000), repr=False)
    allocated_usd: Fraction = field(default=Fraction(10000), repr=False)

    def __post_init__(self) -> None:
        _require(
            all(
                type(value) is Fraction and value >= 0
                for value in (self.gross_cash, self.fees_paid, self.basis_usd, self.allocated_usd)
            ),
            "state_amounts_invalid",
        )
        _require(
            self.basis_usd > 0 and 0 < self.allocated_usd <= self.basis_usd / 10,
            "state_bank_invalid",
        )
        _require(self.analytical_cash >= 0, "state_cash_negative")
        _triple(self.quantities3, "state_quantities_invalid")
        _require(
            all(type(q) is int and q >= 0 for q in self.quantities3),
            "state_quantities_invalid",
        )
        _triple(self.entry_costs3, "state_entry_costs_invalid")
        _require(
            all(type(c) is Fraction and c >= 0 for c in self.entry_costs3),
            "state_entry_costs_invalid",
        )
        _require(
            all(
                (q == 0) == (c == 0)
                for q, c in zip(self.quantities3, self.entry_costs3, strict=True)
            ),
            "state_entry_costs_invalid",
        )
        _require(sum(self.entry_costs3, _ZERO) <= self.allocated_usd, "state_bank_exceeded")

    @property
    def analytical_cash(self) -> Fraction:
        return self.gross_cash - self.fees_paid

    @property
    def gross_realized_pnl(self) -> Fraction:
        return self.gross_cash + sum(self.entry_costs3, _ZERO) - self.allocated_usd


def _state(state: WholeShareState) -> None:
    _require(type(state) is WholeShareState, "state_invalid")
    state.__post_init__()


@dataclass(frozen=True)
class WholeShareTrade:
    state: WholeShareState = field(repr=False)
    status: Literal["executed", "no_intent"]
    reason: WholeShareTradeReason
    target_quantities3: Quantities3 = field(repr=False)
    sold3: Quantities3 = field(default=_FLAT, repr=False)
    bought3: Quantities3 = field(default=_FLAT, repr=False)
    traded_notional: Fraction = field(default=_ZERO, repr=False)
    fees: Fraction = field(default=_ZERO, repr=False)


@dataclass(frozen=True)
class WholeShareMark:
    state: WholeShareState = field(repr=False)
    gross_nav: Fraction = field(repr=False)
    net_nav: Fraction = field(repr=False)


def _mark(state: WholeShareState, prices: Amounts3) -> WholeShareMark:
    gross = state.gross_cash + sum(
        (q * p for q, p in zip(state.quantities3, prices, strict=True)), _ZERO
    )
    return WholeShareMark(state, gross, gross - state.fees_paid)


def _trade(
    state: WholeShareState, prices: Amounts3, targets: Quantities3, fee: Fraction
) -> WholeShareTrade:
    sold = tuple(
        max(held - target, 0) for held, target in zip(state.quantities3, targets, strict=True)
    )
    bought = tuple(
        max(target - held, 0) for held, target in zip(state.quantities3, targets, strict=True)
    )
    if not any(sold) and not any(bought):
        return WholeShareTrade(state, "no_intent", WholeShareTradeReason.NO_TARGET_DELTA, targets)
    sale_notional = sum((q * p for q, p in zip(sold, prices, strict=True)), _ZERO)
    purchase_notional = sum((q * p for q, p in zip(bought, prices, strict=True)), _ZERO)
    # Release exact average entry cost before funding the complete BUY batch.
    costs = tuple(
        cost - (cost * sale / held if sale else _ZERO) + buy * price
        for cost, sale, held, buy, price in zip(
            state.entry_costs3, sold, state.quantities3, bought, prices, strict=True
        )
    )
    notional = sale_notional + purchase_notional
    paid = fee * notional
    cash = state.gross_cash + sale_notional - purchase_notional
    fees = state.fees_paid + paid
    if sum(costs, _ZERO) > state.allocated_usd:
        return WholeShareTrade(state, "no_intent", WholeShareTradeReason.BANK_EXCEEDED, targets)
    if cash - fees < 0:
        return WholeShareTrade(
            state, "no_intent", WholeShareTradeReason.ANALYTICAL_CASH_NEGATIVE, targets
        )
    after = replace(state, gross_cash=cash, fees_paid=fees, quantities3=targets, entry_costs3=costs)
    _require(_mark(after, prices).gross_nav == _mark(state, prices).gross_nav, "cashflow_invalid")
    return WholeShareTrade(
        after, "executed", WholeShareTradeReason.EXECUTED, targets, sold, bought, notional, paid
    )


def rebalance_open(
    state: WholeShareState, prices3: Prices3, weights3: Weights3, cost_bps: Decimal
) -> WholeShareTrade:
    """Floor gross-NAV targets, then atomically execute SELLs before BUYs.

    A rejected full batch returns the identical incumbent state, zero executed
    quantities and zero fees. No fee-aware target clipping or bank rebasing occurs.
    If both constraints fail, bank_exceeded is the deterministic first reason.
    """
    _state(state)
    prices, weights, fee = _prices(prices3), _weights(weights3), _fee(cost_bps)
    gross = _mark(state, prices).gross_nav
    targets = tuple(
        (weight * gross) // price for weight, price in zip(weights, prices, strict=True)
    )
    return _trade(state, prices, targets, fee)


def mark_close(state: WholeShareState, prices3: Prices3) -> WholeShareMark:
    """Mark supplied prices only; preserve quantities, entry costs and cash."""
    _state(state)
    return _mark(state, _prices(prices3))


def liquidate_close(state: WholeShareState, prices3: Prices3, cost_bps: Decimal) -> WholeShareTrade:
    """Attempt one complete CLOSE sale batch; rejection still preserves all state."""
    _state(state)
    return _trade(state, _prices(prices3), _FLAT, _fee(cost_bps))


@dataclass(frozen=True)
class WholeShareDay:
    date: date
    open3: Prices3 = field(repr=False)
    close3: Prices3 = field(repr=False)

    def __post_init__(self) -> None:
        _require(type(self.date) is date, "date_invalid")
        _prices(self.open3)
        _prices(self.close3)


@dataclass(frozen=True)
class WholeShareDaily:
    date: date
    mark: WholeShareMark = field(repr=False)
    open_trade: WholeShareTrade | None = field(repr=False)
    close_trade: WholeShareTrade | None = field(repr=False)

    @property
    def nav(self) -> Fraction:
        """Analytical net NAV, not the gross NAV used for target quantities."""
        return self.mark.net_nav

    @property
    def fees(self) -> Fraction:
        return sum((t.fees for t in (self.open_trade, self.close_trade) if t is not None), _ZERO)

    @property
    def traded_notional(self) -> Fraction:
        return sum(
            (t.traded_notional for t in (self.open_trade, self.close_trade) if t is not None),
            _ZERO,
        )


@dataclass(frozen=True)
class WholeShareReplay:
    daily: tuple[WholeShareDaily, ...] = field(repr=False)
    initial_mark: WholeShareMark = field(repr=False)
    final_state: WholeShareState = field(repr=False)

    @property
    def total_fees(self) -> Fraction:
        """Fees charged in this replay, excluding any carried historical fees."""
        return sum((day.fees for day in self.daily), _ZERO)

    @property
    def total_traded_notional(self) -> Fraction:
        return sum((day.traded_notional for day in self.daily), _ZERO)

    @property
    def final_gross_nav(self) -> Fraction:
        return self.daily[-1].mark.gross_nav

    @property
    def final_net_nav(self) -> Fraction:
        return self.daily[-1].mark.net_nav


def replay(
    days: Sequence[WholeShareDay],
    targets_by_date: Mapping[date, Weights3],
    cost_bps: Decimal,
    *,
    initial_state: WholeShareState,
    liquidate_last_close: bool,
) -> WholeShareReplay:
    """Supplied OPEN targets and CLOSE marks, with explicit terminal sale choice.

    The caller owns causal weights, risk scaling, cadence, calendar and source
    geometry. Missing actions carry state; no implicit fresh bank or episode reset
    occurs. Each failed batch carries its categorical no-intent result. Terminal
    liquidation is also an atomic attempt, never an assumed broker completion.
    """
    _state(initial_state)
    _fee(cost_bps)
    _require(type(liquidate_last_close) is bool, "liquidation_choice_invalid")
    _require(isinstance(days, Sequence) and len(days) > 0, "days_invalid")
    _require(isinstance(targets_by_date, Mapping), "target_dates_invalid")
    records, targets = tuple(days), dict(targets_by_date)
    for day in records:
        _require(type(day) is WholeShareDay, "day_invalid")
        day.__post_init__()
    _require(
        all(a.date < b.date for a, b in zip(records, records[1:], strict=False)),
        "day_order_invalid",
    )
    dates = {day.date for day in records}
    for key, weights in targets.items():
        _require(type(key) is date and key in dates, "target_dates_invalid")
        _weights(weights)
    state = initial_state
    initial_mark = _mark(state, _prices(records[0].open3))
    daily = []
    for index, day in enumerate(records):
        entry = exit_trade = None
        if day.date in targets:
            entry = rebalance_open(state, day.open3, targets[day.date], cost_bps)
            state = entry.state
        if liquidate_last_close and index == len(records) - 1:
            exit_trade = liquidate_close(state, day.close3, cost_bps)
            state = exit_trade.state
        daily.append(WholeShareDaily(day.date, mark_close(state, day.close3), entry, exit_trade))
    return WholeShareReplay(tuple(daily), initial_mark, state)

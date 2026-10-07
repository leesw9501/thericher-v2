"""Shared fractional OPEN/OPEN cashflow, not broker quantity or fill parity.

Targets are fractions of one post-entry-fee NAV, matching paired_allocation_utility.
Both purchases are planned before either fill. Quantities use a fixed 1e-40 unit
lattice, rounded down; actual notional fees are not currency-quantized. This is
an analytical injected local_paper fill projection, not LocalPaperBroker's
separate 0.0001 price/fee rounding. No source loading, policy or IO is performed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import (
    ROUND_DOWN,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DecimalException,
    Underflow,
    localcontext,
)
from fractions import Fraction
from functools import wraps

from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    replay_local_paper_account,
    replay_local_paper_realized_pnl,
)
from thericher_v2.research import three_asset_nav as ledger
from thericher_v2.state import Event

SYMBOLS = ("QQQ", "SPY")
PRECISION = 50
QUANTITY_QUANTUM = Decimal("1e-40")
QUANTITY_ROUNDING = ROUND_DOWN
RECONCILIATION_TOLERANCE = Decimal("1e-45")
_ZERO, _ONE = Decimal(0), Decimal(1)


class ClockPortfolioNavError(ValueError):
    """Categorical invalid/unavailable input or arithmetic failure, without values."""


def _require(condition, category):
    if not condition:
        raise ClockPortfolioNavError(category)


def _amount(value, category, *, positive=False):
    _require(
        type(value) is Decimal and value.is_finite() and (value > 0 if positive else value >= 0),
        category,
    )


def _pair(values, category, *, positive=False):
    _require(type(values) is tuple and len(values) == 2, category)
    for value in values:
        _amount(value, category, positive=positive)


def _named(values, category):
    _require(isinstance(values, Mapping) and set(values) == set(SYMBOLS), category)
    return tuple(values[symbol] for symbol in SYMBOLS)


def _decimal(function):
    @wraps(function)
    def call(*args, **kwargs):
        with localcontext(Context(prec=PRECISION, rounding=ROUND_HALF_EVEN)) as context:
            context.traps[Underflow] = True
            try:
                return function(*args, **kwargs)
            except (DecimalException, ledger.ThreeAssetNavError):
                raise ClockPortfolioNavError("numeric_range") from None

    return call


def _close(actual, expected, scale):
    _require(abs(actual - expected) <= scale * RECONCILIATION_TOLERANCE, "cashflow_reconciliation")


@dataclass(frozen=True)
class ClockOpportunity:
    session_date: date
    entry_at: datetime
    exit_at: datetime
    entry_open2: tuple[Decimal, Decimal] = field(repr=False)
    exit_open2: tuple[Decimal, Decimal] = field(repr=False)

    def __post_init__(self):
        _require(type(self.session_date) is date, "session_date_invalid")
        _require(
            all(
                type(t) is datetime and t.tzinfo is not None and t.utcoffset() == timedelta(0)
                for t in (self.entry_at, self.exit_at)
            ),
            "opportunity_time_invalid",
        )
        _require(
            self.entry_at.date() == self.exit_at.date() == self.session_date
            and self.exit_at - self.entry_at == timedelta(minutes=30)
            and not (self.entry_at.second or self.entry_at.microsecond),
            "opportunity_geometry_invalid",
        )
        _pair(self.entry_open2, "prices_invalid", positive=True)
        _pair(self.exit_open2, "prices_invalid", positive=True)

    @classmethod
    def from_mapping(cls, session_date, entry_at, exit_at, entry_open, exit_open):
        return cls(
            session_date,
            entry_at,
            exit_at,
            _named(entry_open, "price_symbols_invalid"),
            _named(exit_open, "price_symbols_invalid"),
        )


@dataclass(frozen=True)
class ClockTarget:
    weights2: tuple[Decimal, Decimal] = field(repr=False)

    def __post_init__(self):
        _pair(self.weights2, "targets_invalid")
        _require(all(w <= Decimal(".5") for w in self.weights2), "target_cap_exceeded")
        _require(sum(map(Fraction, self.weights2), Fraction(0)) <= 1, "target_sum_exceeded")

    @classmethod
    def from_mapping(cls, values):
        return cls(_named(values, "target_symbols_invalid"))


@dataclass(frozen=True)
class ClockFill:
    symbol: str
    side: str
    filled_at: datetime
    quantity: Decimal = field(repr=False)
    price: Decimal = field(repr=False)
    fee: Decimal = field(repr=False)
    source: str = LOCAL_PAPER_SOURCE

    @property
    @_decimal
    def notional(self):
        return self.quantity * self.price


@dataclass(frozen=True)
class ClockAssetCashflow:
    symbol: str
    gross_pnl: Decimal = field(repr=False)
    entry_fee: Decimal = field(repr=False)
    exit_fee: Decimal = field(repr=False)
    traded_notional: Decimal = field(repr=False)
    net_pnl: Decimal = field(repr=False)

    @property
    @_decimal
    def fees(self):
        return self.entry_fee + self.exit_fee


@dataclass(frozen=True)
class ClockSlotResult:
    entry_at: datetime
    exit_at: datetime
    pre_nav: Decimal = field(repr=False)
    entry_cash: Decimal = field(repr=False)
    final_nav: Decimal = field(repr=False)
    fills: tuple[ClockFill, ...] = field(repr=False)
    asset_cashflows: tuple[ClockAssetCashflow, ...] = field(repr=False)


@dataclass(frozen=True)
class ClockDaily:
    date: date
    nav: Decimal = field(repr=False)
    simple_return: Decimal = field(repr=False)
    log_return: Decimal = field(repr=False)
    fees: Decimal = field(repr=False)
    traded_notional: Decimal = field(repr=False)
    asset_cashflows: tuple[ClockAssetCashflow, ...] = field(repr=False)
    flat: bool = True


@dataclass(frozen=True)
class ClockPortfolioReplay:
    daily: tuple[ClockDaily, ...] = field(repr=False)
    slots: tuple[ClockSlotResult, ...] = field(repr=False)
    total_fees: Decimal = field(repr=False)
    total_traded_notional: Decimal = field(repr=False)
    asset_cashflows: tuple[ClockAssetCashflow, ...] = field(repr=False)

    @property
    def final_nav(self):
        return self.daily[-1].nav

    @property
    def navs(self):
        return tuple(day.nav for day in self.daily)

    @property
    def log_returns(self):
        return tuple(day.log_return for day in self.daily)

    @property
    def simple_returns(self):
        return tuple(day.simple_return for day in self.daily)


@dataclass(frozen=True)
class _EventView:
    events: tuple[Event, ...] = field(repr=False)

    def iter_events(self):
        return iter(self.events)


def _events(fills):
    return tuple(
        Event(
            event_type="fill",
            created_at=fill.filled_at,
            seq=i + 1,
            payload=dict(
                source=fill.source,
                client_order_id=f"clock:{fill.filled_at.isoformat()}:{fill.symbol}:{fill.side}",
                market="US",
                symbol=fill.symbol,
                side=fill.side,
                quantity=str(fill.quantity),
                price=str(fill.price),
                fee=str(fill.fee),
            ),
        )
        for i, fill in enumerate(fills)
    )


def _asset_flows(fills):
    result = []
    for symbol in SYMBOLS:
        own = tuple(f for f in fills if f.symbol == symbol)
        pnl = replay_local_paper_realized_pnl(_events(own))
        _require(pnl.open_quantity == 0, "position_not_flat")
        entry = sum((f.fee for f in own if f.side == "buy"), _ZERO)
        exit_ = sum((f.fee for f in own if f.side == "sell"), _ZERO)
        gross = sum((f.notional if f.side == "sell" else -f.notional for f in own), _ZERO)
        result.append(
            ClockAssetCashflow(
                symbol,
                gross,
                entry,
                exit_,
                sum((f.notional for f in own), _ZERO),
                pnl.realized_after_cost_pnl,
            )
        )
    return tuple(result)


def _aggregate(flows):
    names = ("gross_pnl", "entry_fee", "exit_fee", "traded_notional", "net_pnl")
    return tuple(
        ClockAssetCashflow(
            symbol,
            *(
                sum((getattr(f, name) for f in flows if f.symbol == symbol), _ZERO)
                for name in names
            ),
        )
        for symbol in SYMBOLS
    )


def _slot(opportunity, target, cash, cost_bps):
    # One existing simultaneous fee solve; neither leg sees later cash or exit prices.
    qqq, spy = opportunity.entry_open2
    entry = ledger.rebalance_open(
        ledger.ThreeAssetState(cash),
        ledger.ThreeAssetPrices((spy, qqq, _ONE)),
        {"SPY": target.weights2[1], "QQQ": target.weights2[0], "IWM": _ZERO},
        cost_bps,
    )
    quantities = tuple(
        q.quantize(QUANTITY_QUANTUM, rounding=QUANTITY_ROUNDING)
        for q in (entry.state.quantities[1], entry.state.quantities[0])
    )
    fee = cost_bps / 10000
    buys, sells = [], []
    for symbol, quantity, opened, exited in zip(
        SYMBOLS, quantities, opportunity.entry_open2, opportunity.exit_open2, strict=True
    ):
        if quantity > 0:
            buys.append(
                ClockFill(
                    symbol, "buy", opportunity.entry_at, quantity, opened, quantity * opened * fee
                )
            )
            sells.append(
                ClockFill(
                    symbol, "sell", opportunity.exit_at, quantity, exited, quantity * exited * fee
                )
            )
    fills = tuple(buys + sells)
    after_entry = replay_local_paper_account(_EventView(_events(buys)), starting_cash=cash)
    after_exit = replay_local_paper_account(_EventView(_events(fills)), starting_cash=cash)
    _require(after_entry.cash >= 0 and after_exit.cash > 0, "cash_invalid")
    _require(not after_exit.positions, "position_not_flat")
    flows = _asset_flows(fills)
    _close(after_exit.cash - cash, sum((f.net_pnl for f in flows), _ZERO), cash + after_exit.cash)
    return ClockSlotResult(
        opportunity.entry_at,
        opportunity.exit_at,
        cash,
        after_entry.cash,
        after_exit.cash,
        fills,
        flows,
    )


@_decimal
def replay(
    opportunities: Sequence[ClockOpportunity],
    targets_by_entry_at: Mapping[datetime, ClockTarget],
    cost_bps: Decimal,
    *,
    session_dates: Sequence[date],
    initial_cash: Decimal = _ONE,
) -> ClockPortfolioReplay:
    """Continuous shared account, flat after every slot and at every daily mark.

    Explicit session_dates retain zero-trade days. Targets must cover exactly the
    supplied opportunity keys; missing future marks are invalid even for cash.
    The caller owns causal eligibility, market-calendar geometry and source pins.
    initial_cash enables deterministic continuation at a flat slot/day boundary;
    it is normalized analytical capital, not a broker minimum or funded sleeve.
    """
    _require(isinstance(opportunities, Sequence), "opportunities_invalid")
    _require(isinstance(session_dates, Sequence) and len(session_dates) > 0, "dates_invalid")
    _require(isinstance(targets_by_entry_at, Mapping), "targets_invalid")
    records, dates, targets = tuple(opportunities), tuple(session_dates), dict(targets_by_entry_at)
    _require(all(type(day) is date for day in dates), "dates_invalid")
    _require(all(a < b for a, b in zip(dates, dates[1:], strict=False)), "dates_invalid")
    _amount(initial_cash, "initial_cash_invalid", positive=True)
    _amount(cost_bps, "cost_bps_invalid")
    _require(cost_bps <= 100, "cost_bps_invalid")
    for item in records:
        _require(type(item) is ClockOpportunity, "opportunity_invalid")
        item.__post_init__()
        _require(item.session_date in dates, "opportunity_date_invalid")
    _require(
        all(a.exit_at <= b.entry_at for a, b in zip(records, records[1:], strict=False)),
        "opportunity_order_invalid",
    )
    _require(
        all(type(key) is datetime for key in targets)
        and set(targets) == {item.entry_at for item in records},
        "target_keys_invalid",
    )
    for target in targets.values():
        _require(type(target) is ClockTarget, "target_invalid")
        target.__post_init__()
    cash, previous, slots, daily = initial_cash, initial_cash, [], []
    index = 0
    for day in dates:
        flows = []
        while index < len(records) and records[index].session_date == day:
            item = records[index]
            result = _slot(item, targets[item.entry_at], cash, cost_bps)
            slots.append(result)
            cash = result.final_nav
            flows.extend(result.asset_cashflows)
            index += 1
        assets = _aggregate(flows)
        fees = sum((f.fees for f in assets), _ZERO)
        turnover = sum((f.traded_notional for f in assets), _ZERO)
        _close(cash - previous, sum((f.net_pnl for f in assets), _ZERO), cash + previous)
        growth = cash / previous
        daily.append(ClockDaily(day, cash, growth - 1, growth.ln(), fees, turnover, assets))
        previous = cash
    totals = _aggregate([f for slot in slots for f in slot.asset_cashflows])
    _close(cash - initial_cash, sum((f.net_pnl for f in totals), _ZERO), cash + initial_cash)
    return ClockPortfolioReplay(
        tuple(daily),
        tuple(slots),
        sum((f.fees for f in totals), _ZERO),
        sum((f.traded_notional for f in totals), _ZERO),
        totals,
    )

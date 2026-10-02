"""Causal in-memory monthly inputs, separate from realized adjusted-mark payoffs.

Caller pins the calendar, source and requested months before inspecting outcomes.
No split selection, fitting, loading, persistence or execution qualification lives
here. Marks are revised/non-PIT fractional adjusted-price proxies; do not add
dividends/splits again. Cash interest is zero in the eventual analytical ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow

CONTEXT_RETURNS = 252
CONTEXT_CLOSES = CONTEXT_RETURNS + 1
SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _dates(values: tuple[date, ...]) -> bool:
    return (
        type(values) is tuple
        and bool(values)
        and all(type(d) is date for d in values)
        and all(a < b for a, b in zip(values, values[1:], strict=False))
    )


def _decimal(value: Decimal) -> bool:
    return type(value) is Decimal and value.is_finite()


def _bounds(value: tuple[int, int]) -> bool:
    return (
        type(value) is tuple
        and len(value) == 2
        and all(type(i) is int for i in value)
        and CONTEXT_CLOSES <= value[0] < value[1]
    )


@dataclass(frozen=True, slots=True)
class MonthlyModelInput:
    """Only completed past returns; no decision/target prices or future covariates."""

    context_dates: tuple[date, ...]
    close_returns_bps: tuple[Decimal, ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require(
            _dates(self.context_dates) and len(self.context_dates) == CONTEXT_CLOSES,
            "model_context_dates",
        )
        _require(
            type(self.close_returns_bps) is tuple
            and len(self.close_returns_bps) == CONTEXT_RETURNS
            and all(_decimal(v) and v > -10000 for v in self.close_returns_bps),
            "model_returns",
        )

    @property
    def source_date(self) -> date:
        return self.context_dates[-1]

    @property
    def return_dates(self) -> tuple[date, ...]:
        return self.context_dates[1:]


@dataclass(frozen=True, slots=True)
class MonthlyPayoffMarks:
    """Realized labels for carry/rebalance/daily marks, never model inputs."""

    target_dates: tuple[date, ...]
    open_over_previous_close: Decimal = field(repr=False)
    close_over_entry_open: tuple[Decimal, ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require(_dates(self.target_dates), "payoff_dates")
        _require(
            _decimal(self.open_over_previous_close) and self.open_over_previous_close > 0,
            "payoff_gap",
        )
        _require(
            type(self.close_over_entry_open) is tuple
            and len(self.close_over_entry_open) == len(self.target_dates)
            and all(_decimal(v) and v > 0 for v in self.close_over_entry_open),
            "payoff_growth",
        )

    @property
    def final_close_growth(self) -> Decimal:
        return self.close_over_entry_open[-1]


@dataclass(frozen=True, slots=True)
class MonthlyInputIdentity:
    """Date-only cohort identity; it is not a source or PIT availability attestation."""

    symbol: str
    decision_date: date
    source_date: date
    month_bounds: tuple[int, int]
    cohort_dates: tuple[date, ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require(
            type(self.symbol) is str
            and self.symbol in SYMBOLS
            and type(self.decision_date) is date
            and type(self.source_date) is date
            and self.source_date < self.decision_date,
            "input_identity",
        )
        _require(_bounds(self.month_bounds) and _dates(self.cohort_dates), "input_cohort")


@dataclass(frozen=True, slots=True)
class AdjustedMonthlyPolicyInputs:
    identity: MonthlyInputIdentity
    model: MonthlyModelInput
    payoff: MonthlyPayoffMarks

    def __post_init__(self) -> None:
        _require(
            type(self.identity) is MonthlyInputIdentity
            and type(self.model) is MonthlyModelInput
            and type(self.payoff) is MonthlyPayoffMarks,
            "input_record_types",
        )
        _require(
            self.identity.source_date == self.model.source_date
            and self.identity.decision_date == self.payoff.target_dates[0]
            and self.model.source_date < self.payoff.target_dates[0]
            and self.identity.cohort_dates == self.model.context_dates + self.payoff.target_dates
            and len(self.payoff.target_dates)
            == self.identity.month_bounds[1] - self.identity.month_bounds[0],
            "input_binding",
        )


def _valid_marks(row: AdjustedEtfRow) -> bool:
    values = tuple(
        getattr(row, name, None) for name in ("adj_open", "adj_high", "adj_low", "adj_close")
    )
    return all(_decimal(v) and v > 0 for v in values) and (
        row.adj_low
        <= min(row.adj_open, row.adj_close)
        <= max(row.adj_open, row.adj_close)
        <= row.adj_high
    )


def build_adjusted_monthly_policy_inputs(
    rows: tuple[AdjustedEtfRow, ...],
    *,
    symbol: str,
    calendar: tuple[date, ...],
    month_bounds: tuple[int, int],
) -> AdjustedMonthlyPolicyInputs:
    """Build one complete calendar month; bounds are half-open calendar indices.

    The calendar must bracket the requested month with prior/following month
    labels, including when the month is the last scored fold month. The next
    label proves completeness only: no next-month row/OPEN is required or read.
    Required source dates are exactly253 prior closes plus all target sessions.
    Source identity/order is checked throughout; numeric marks are checked only
    on that requested cohort, so unrelated future payoffs cannot affect it.
    """
    _require(type(symbol) is str and symbol in SYMBOLS, "symbol")
    _require(_dates(calendar), "calendar_dates")
    _require(_bounds(month_bounds), "month_bounds")
    start, stop = month_bounds
    _require(stop < len(calendar), "unbracketed_month")
    month = (calendar[start].year, calendar[start].month)
    target_dates = calendar[start:stop]
    _require(
        all((d.year, d.month) == month for d in target_dates)
        and (calendar[start - 1].year, calendar[start - 1].month) != month
        and (calendar[stop].year, calendar[stop].month) != month,
        "partial_calendar_month",
    )
    _require(type(rows) is tuple and bool(rows), "source_rows")
    _require(
        all(
            type(r) is AdjustedEtfRow
            and getattr(r, "symbol", None) == symbol
            and type(getattr(r, "session_date", None)) is date
            for r in rows
        ),
        "source_identity",
    )
    _require(
        all(a.session_date < b.session_date for a, b in zip(rows, rows[1:], strict=False)),
        "source_order",
    )
    context_dates = calendar[start - CONTEXT_CLOSES : start]
    required = context_dates + target_dates
    by_date = {r.session_date: r for r in rows}
    _require(all(d in by_date for d in required), "missing_required_session")
    _require(all(_valid_marks(by_date[d]) for d in required), "invalid_required_marks")
    history = [by_date[d].adj_close for d in context_dates]
    opening = by_date[target_dates[0]].adj_open
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        model = MonthlyModelInput(
            context_dates,
            tuple(10000 * (b / a - 1) for a, b in zip(history, history[1:], strict=False)),
        )
        payoff = MonthlyPayoffMarks(
            target_dates,
            opening / history[-1],
            tuple(by_date[d].adj_close / opening for d in target_dates),
        )
    identity = MonthlyInputIdentity(
        symbol, target_dates[0], context_dates[-1], month_bounds, required
    )
    return AdjustedMonthlyPolicyInputs(identity, model, payoff)

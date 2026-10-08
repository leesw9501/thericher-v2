"""Pure past-only raw-price features and a separate fixed monthly TRAIN target.

Frozen calendar completeness/availability are caller assumptions. Raw MODP0
prices have no split-unit, dividend, total-return or broker-fill correction.
There is no IO, model, fit, outcome selection or target lookup in feature prep.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, Underflow, localcontext

from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import (
    INSTRUMENT_ORDER,
    CrossAssetInputUnavailable,
    CrossAssetSession,
)
from thericher_v2.research.cross_asset_monthly_momentum import PRICE_BASIS, THIRD

CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
CONTEXT.traps[Underflow] = True
CHANNELS = tuple(f"{symbol}:{kind}" for symbol in INSTRUMENT_ORDER
                 for kind in ("close_to_close_log_return", "open_to_close_log_return"))
TARGET_COST_BPS = Decimal(5)


def _require(condition, code):
    if not condition:
        raise CrossAssetInputUnavailable(code)


def _vintage(value):
    _require(type(value) is str and bool(value) and value == value.strip(), "vintage_invalid")


def _positive(value):
    _require(type(value) is Decimal and value.is_finite() and value > 0, "required_price_invalid")


def _utc(value):
    _require(type(value) is datetime and value.utcoffset() == timedelta(0), "time_not_utc")


def _calendar(sessions):
    _require(type(sessions) is tuple and bool(sessions), "calendar_required")
    for session in sessions:
        _require(type(session) is CrossAssetSession, "calendar_type_invalid")
        session.__post_init__()
    _require(all(a.session_date < b.session_date and a.close_at < b.open_at
                 for a, b in zip(sessions, sessions[1:], strict=False)), "calendar_order_invalid")


@dataclass(frozen=True, slots=True)
class RawD1Price:
    symbol: str
    session_date: date
    vintage_ref: str = field(repr=False)
    open: Decimal | None = field(default=None, repr=False)
    close: Decimal | None = field(default=None, repr=False)
    price_basis: str = PRICE_BASIS

    def __post_init__(self):
        _require(type(self.symbol) is str and self.symbol in INSTRUMENT_ORDER, "row_symbol_invalid")
        _require(type(self.session_date) is date, "row_date_invalid")
        _vintage(self.vintage_ref)
        _require(type(self.price_basis) is str and self.price_basis == PRICE_BASIS,
                 "price_basis_invalid")
        _require(self.open is not None or self.close is not None, "row_prices_missing")
        for value in (self.open, self.close):
            if value is not None:
                _positive(value)


def _select(rows_by_symbol, required, vintage_ref):
    _vintage(vintage_ref)
    _require(isinstance(rows_by_symbol, Mapping) and set(rows_by_symbol) == set(INSTRUMENT_ORDER),
             "source_symbols_invalid")
    result = []
    for symbol in INSTRUMENT_ORDER:
        rows = rows_by_symbol[symbol]
        _require(isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)),
                 "source_sequence_invalid")
        selected = {}
        for row in rows:
            day = getattr(row, "session_date", None)
            if type(day) is not date or day not in required:
                continue
            _require(day not in selected, "required_session_duplicate")
            _require(type(row) is RawD1Price, "required_row_type_invalid")
            _require(row.symbol == symbol, "required_symbol_mismatch")
            _require(row.vintage_ref == vintage_ref, "required_vintage_mismatch")
            _require(type(row.price_basis) is str and row.price_basis == PRICE_BASIS,
                     "price_basis_invalid")
            selected[day] = {}
            for key in required[day]:
                value = getattr(row, key)
                _positive(value)
                selected[day][key] = value
        _require(set(selected) == set(required), "required_session_missing")
        result.append(selected)
    return tuple(result)


def _facts():
    return dict(status="ready", instrument_order=INSTRUMENT_ORDER, price_basis=PRICE_BASIS,
                splits_and_dividends="not_applied", publication_availability="not_observed",
                paper_input=False)


@dataclass(frozen=True, slots=True)
class HedgeFailureFeatures:
    decision_at: datetime
    entry_at: datetime
    observation_dates: tuple[date, ...] = field(repr=False)
    features: tuple[tuple[Decimal, ...], ...] = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _utc(self.decision_at)
        _utc(self.entry_at)
        _vintage(self.vintage_ref)
        dates = self.observation_dates
        _require(type(dates) is tuple and len(dates) == 63 and all(type(d) is date for d in dates)
                 and all(a < b for a, b in zip(dates, dates[1:], strict=False))
                 and dates[-1] == self.decision_at.date() and self.decision_at < self.entry_at
                 and self.entry_at.year * 12 + self.entry_at.month
                 == self.decision_at.year * 12 + self.decision_at.month + 1,
                 "feature_dates_invalid")
        _require(type(self.features) is tuple and len(self.features) == 6
                 and all(type(c) is tuple and len(c) == 63
                         and all(type(v) is Decimal and v.is_finite() for v in c)
                         for c in self.features), "feature_matrix_invalid")

    def safe_facts(self):
        return dict(_facts(), channels=CHANNELS, shape=(6, 63), required_closes=64,
                    required_opens=63, decision_at=self.decision_at.isoformat(),
                    entry_at=self.entry_at.isoformat())


def prepare_monthly_features(
    rows_by_symbol: Mapping[str, Sequence[RawD1Price]], *,
    scheduled_history: tuple[CrossAssetSession, ...], entry_session: CrossAssetSession,
    decision_at: datetime, vintage_ref: str,
) -> HedgeFailureFeatures:
    """Exactly64 scheduled past CLOSEs/63 OPENs; never reads target/forward prices."""
    _calendar(scheduled_history)
    _require(len(scheduled_history) == 64, "history_count_invalid")
    _require(type(entry_session) is CrossAssetSession, "entry_session_invalid")
    entry_session.__post_init__()
    _utc(decision_at)
    last = scheduled_history[-1]
    _require(decision_at == last.close_at and decision_at < entry_session.open_at
             and entry_session.session_date.year * 12 + entry_session.session_date.month
             == last.session_date.year * 12 + last.session_date.month + 1,
             "decision_not_previous_month_close")
    dates = tuple(s.session_date for s in scheduled_history)
    required = {day: ("close",) if i == 0 else ("open", "close")
                for i, day in enumerate(dates)}
    selected = _select(rows_by_symbol, required, vintage_ref)
    try:
        with localcontext(CONTEXT):
            channels = []
            for rows in selected:
                channels.append(tuple((rows[b]["close"] / rows[a]["close"]).ln()
                                      for a, b in zip(dates, dates[1:], strict=False)))
                channels.append(tuple((rows[d]["close"] / rows[d]["open"]).ln() for d in dates[1:]))
    except DecimalException:
        raise CrossAssetInputUnavailable("numeric_range") from None
    return HedgeFailureFeatures(decision_at, entry_session.open_at, dates[1:], tuple(channels),
                                vintage_ref)


@dataclass(frozen=True, slots=True)
class MonthlyRoundtripTarget:
    entry_at: datetime
    exit_at: datetime
    net_factor: Decimal = field(repr=False)
    loss_label: bool = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _utc(self.entry_at)
        _utc(self.exit_at)
        _vintage(self.vintage_ref)
        _require(self.entry_at < self.exit_at
                 and (self.entry_at.year, self.entry_at.month)
                 == (self.exit_at.year, self.exit_at.month), "target_window_invalid")
        _positive(self.net_factor)
        _require(type(self.loss_label) is bool and self.loss_label == (self.net_factor < 1),
                 "target_label_mismatch")

    def safe_facts(self):
        return dict(_facts(), entry_at=self.entry_at.isoformat(), exit_at=self.exit_at.isoformat(),
                    required_opens=3, required_closes=3, cost_bps_side=5,
                    daily_mark_support="not_checked",
                    target_arithmetic="three_asset_nav.replay; endpoints_only_not_daily_utility",
                    target_path="month_first_open_to_last_close; flat_after_exit")


def build_monthly_target(
    rows_by_symbol: Mapping[str, Sequence[RawD1Price]], *,
    scheduled_month: tuple[CrossAssetSession, ...], vintage_ref: str,
) -> MonthlyRoundtripTarget:
    """Caller freezes the complete month; cost5bps/side, identical finite thirds.

    Unit-factor uses canonical ledger rounding/costs, not a policy capital reset.
    Synthetic intermediate marks equal endpoint prices: only final NAV/label is
    used, never this replay's daily utility or a claim of adjusted source data.
    A future campaign carries capital and requires all daily valuation marks.
    """
    _calendar(scheduled_month)
    first, last = scheduled_month[0], scheduled_month[-1]
    _require(all((s.session_date.year, s.session_date.month)
                 == (first.session_date.year, first.session_date.month) for s in scheduled_month),
             "target_month_invalid")
    required = {first.session_date: ("open",), last.session_date: ("close",)}
    if first.session_date == last.session_date:
        required[first.session_date] = ("open", "close")
    selected = _select(rows_by_symbol, required, vintage_ref)
    try:
        with localcontext(CONTEXT):
            allocation = nav.ThreeAssetTarget((THIRD,) * 3, Decimal(1) - 3 * THIRD)
        opens = tuple(rows[first.session_date]["open"] for rows in selected)
        closes = tuple(rows[last.session_date]["close"] for rows in selected)
        days = ((nav.ThreeAssetDay(first.session_date, opens, closes),)
                if first.session_date == last.session_date else (
                    nav.ThreeAssetDay(first.session_date, opens, opens),
                    nav.ThreeAssetDay(last.session_date, closes, closes)))
        factor = nav.replay(days, {first.session_date: allocation}, TARGET_COST_BPS).final_nav
    except DecimalException:
        raise CrossAssetInputUnavailable("numeric_range") from None
    except nav.ThreeAssetNavError as error:
        code = "numeric_range" if str(error) == "numeric_range" else "target_ledger_unavailable"
        raise CrossAssetInputUnavailable(code) from None
    return MonthlyRoundtripTarget(first.open_at, last.close_at, factor, factor < 1, vintage_ref)

"""Pure raw-price sector momentum preparation, not a fitted or Paper policy.

Caller-frozen calendars/vintages bind rows, not publication or corporate-action
correctness. No provider, IO, payoff marks or legacy three-asset relabeling.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException, localcontext

from thericher_v2.research.cross_asset_etf_input import (
    CrossAssetInputUnavailable,
    CrossAssetSession,
)
from thericher_v2.research.cross_asset_monthly_momentum import (
    DECIMAL_CONTEXT,
    PRICE_BASIS,
    _calendar,
    _require,
    _vintage,
)

NAME = "kis-sector-relative-strength-preparation-v1"
SYMBOLS = ("SPY", "XLK", "XLF", "XLE")
LOOKBACK, REBALANCE = 126, 21


def configuration() -> dict[str, object]:
    return dict(
        name=NAME,
        preparation_only=True,
        symbols=list(SYMBOLS),
        lookback_return_intervals=LOOKBACK,
        required_completed_closes=LOOKBACK + 1,
        rebalance_scheduled_sessions=REBALANCE,
        decision="immediately previous frozen session CLOSE; execute following OPEN",
        momentum="Decimal50 (last CLOSE - first CLOSE) / first CLOSE",
        relative="sector momentum strictly greater than SPY momentum",
        selection="unique positive maximum: one sector or SPY, otherwise cash",
        ties="cash on any shared positive maximum, including SPY/sector ties",
        target="one selected risky weight 1, otherwise cash 1; no leverage",
        price_basis=PRICE_BASIS,
        source_cohort="caller-supplied future frozen cohort; no legacy trio binding",
        limits=[
            "calendar completeness is caller-owned",
            "non-PIT availability not observed",
            "splits/dividends not applied",
            "no payoff/cost/replay qualification",
        ],
        fits=0,
        gpu=False,
        paper_input=False,
    )


@dataclass(frozen=True, slots=True)
class SectorPriceClose:
    symbol: str
    session_date: date
    vintage_ref: str = field(repr=False)
    close: Decimal = field(repr=False)
    price_basis: str = PRICE_BASIS

    def __post_init__(self) -> None:
        _require(type(self.symbol) is str and self.symbol in SYMBOLS, "row_symbol_invalid")
        _require(type(self.session_date) is date, "row_date_invalid")
        _vintage(self.vintage_ref)
        _require(
            type(self.price_basis) is str and self.price_basis == PRICE_BASIS, "price_basis_invalid"
        )
        _require(
            type(self.close) is Decimal and self.close.is_finite() and self.close > 0,
            "price_close_invalid",
        )


@dataclass(frozen=True, slots=True)
class SectorAction:
    selected_symbol: str | None = field(repr=False)

    def __post_init__(self) -> None:
        _require(
            self.selected_symbol is None
            or (type(self.selected_symbol) is str and self.selected_symbol in SYMBOLS),
            "action_symbol_invalid",
        )

    @property
    def weights(self) -> tuple[Decimal, ...]:
        return tuple(Decimal(int(s == self.selected_symbol)) for s in SYMBOLS)

    @property
    def cash_weight(self) -> Decimal:
        return Decimal(int(self.selected_symbol is None))


def _selected_symbol(momentum: tuple[Decimal, ...]) -> str | None:
    maximum = max(momentum)
    if maximum <= 0 or momentum.count(maximum) != 1:
        return None
    return SYMBOLS[momentum.index(maximum)]


@dataclass(frozen=True, slots=True)
class SectorRelativeStrengthDecision:
    decision_at: datetime
    entry_at: datetime
    history_dates: tuple[date, ...] = field(repr=False)
    momentum: tuple[Decimal, ...] = field(repr=False)
    action: SectorAction = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self) -> None:
        _require(
            all(
                type(t) is datetime and t.utcoffset() == timedelta(0)
                for t in (self.decision_at, self.entry_at)
            ),
            "decision_not_utc",
        )
        _require(
            type(self.history_dates) is tuple
            and len(self.history_dates) == LOOKBACK + 1
            and all(type(d) is date for d in self.history_dates)
            and all(a < b for a, b in zip(self.history_dates, self.history_dates[1:], strict=False))
            and self.history_dates[-1] == self.decision_at.date()
            and self.decision_at < self.entry_at
            and self.decision_at.date() < self.entry_at.date(),
            "decision_geometry_invalid",
        )
        _vintage(self.vintage_ref)
        _require(
            type(self.momentum) is tuple
            and len(self.momentum) == len(SYMBOLS)
            and all(type(v) is Decimal and v.is_finite() for v in self.momentum),
            "momentum_invalid",
        )
        _require(type(self.action) is SectorAction, "action_type_invalid")
        self.action.__post_init__()
        _require(
            self.action.selected_symbol == _selected_symbol(self.momentum),
            "action_momentum_mismatch",
        )

    def safe_facts(self) -> dict[str, object]:
        return dict(
            status="ready",
            symbols=SYMBOLS,
            required_close_count_per_symbol=LOOKBACK + 1,
            lookback_return_intervals=LOOKBACK,
            rebalance_scheduled_sessions=REBALANCE,
            decision_at=self.decision_at.isoformat(),
            entry_at=self.entry_at.isoformat(),
            price_basis=PRICE_BASIS,
            availability="not_observed",
            paper_input=False,
        )


def rebalance_entry_dates(
    scheduled_sessions: tuple[CrossAssetSession, ...],
    *,
    first_entry_session_date: date,
) -> tuple[date, ...]:
    """Every21 declared sessions, anchored once; never infer dates from source rows.

    This supplies rebalance keys only, not a holding/exit or cost contract.
    Tail sessions and future marks cannot reset the phase or filter old keys.
    """
    _calendar(scheduled_sessions)
    dates = tuple(s.session_date for s in scheduled_sessions)
    _require(
        type(first_entry_session_date) is date and first_entry_session_date in dates,
        "first_entry_missing",
    )
    first = dates.index(first_entry_session_date)
    _require(first >= LOOKBACK + 1, "scheduled_history_missing")
    return dates[first::REBALANCE]


def build_sector_relative_strength(
    rows_by_symbol: Mapping[str, Sequence[SectorPriceClose]],
    *,
    scheduled_history: tuple[CrossAssetSession, ...],
    entry_session: CrossAssetSession,
    decision_at: datetime,
    vintage_ref: str,
) -> SectorRelativeStrengthDecision:
    """Unique positive winner beats SPY if it is a sector; every top tie stays cash.

    Exactly127 completed scheduled CLOSEs give126 return intervals. An interior
    gap is input_unavailable even though momentum uses endpoints. No stale-row
    fallback, forward support mask or future price validation is permitted.
    The caller freezes calendar completeness and immediate next-OPEN adjacency.
    """
    _calendar(scheduled_history)
    _require(len(scheduled_history) == LOOKBACK + 1, "scheduled_history_missing")
    _require(type(entry_session) is CrossAssetSession, "entry_session_invalid")
    entry_session.__post_init__()
    _require(
        type(decision_at) is datetime
        and decision_at.utcoffset() == timedelta(0)
        and decision_at == scheduled_history[-1].close_at
        and decision_at < entry_session.open_at
        and scheduled_history[-1].session_date < entry_session.session_date,
        "decision_not_previous_close",
    )
    _vintage(vintage_ref)
    _require(
        isinstance(rows_by_symbol, Mapping) and set(rows_by_symbol) == set(SYMBOLS),
        "source_symbols_invalid",
    )
    dates = tuple(s.session_date for s in scheduled_history)
    required = set(dates)
    momentum = []
    try:
        with localcontext(DECIMAL_CONTEXT):
            for symbol in SYMBOLS:
                source = rows_by_symbol[symbol]
                _require(
                    isinstance(source, Sequence) and not isinstance(source, (str, bytes)),
                    "source_sequence_invalid",
                )
                selected = {}
                for row in source:
                    day = getattr(row, "session_date", None)
                    if type(day) is date and day in required:
                        _require(day not in selected, "required_session_duplicate")
                        _require(type(row) is SectorPriceClose, "required_row_type_invalid")
                        row.__post_init__()
                        _require(row.symbol == symbol, "required_row_symbol_mismatch")
                        _require(row.vintage_ref == vintage_ref, "required_vintage_mismatch")
                        selected[day] = row.close
                _require(set(selected) == required, "required_session_missing")
                first, last = selected[dates[0]], selected[dates[-1]]
                momentum.append((last - first) / first)
    except DecimalException:
        raise CrossAssetInputUnavailable("numeric_range") from None
    values = tuple(momentum)
    return SectorRelativeStrengthDecision(
        decision_at,
        entry_session.open_at,
        dates,
        values,
        SectorAction(_selected_symbol(values)),
        vintage_ref,
    )

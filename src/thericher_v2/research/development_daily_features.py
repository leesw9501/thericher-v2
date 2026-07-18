"""Small, descriptive daily features for the bounded development-only universe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from thericher_v2.contracts import Bar
from thericher_v2.data.daily import (
    DevelopmentDailyUniverse,
    _reverify_broad_daily_development_feature_input,
)

FEATURE_NAMES = (
    "close_return_5_sessions",
    "close_return_1_session",
    "high_low_range",
    "volume_change_1_session",
)
FEATURE_AVAILABILITY = "after_completed_session_close"
RAW_CLOSE_LIMITATION = (
    "raw close return features can be distorted by unverified corporate actions"
)
_ONE = Decimal("1")
_MINIMUM_SESSIONS = 6


@dataclass(frozen=True)
class DevelopmentDailyFeatureRow:
    """One descriptive feature row available only after its session closes."""

    session: date
    symbol: str
    close_return_5_sessions: Decimal
    close_return_1_session: Decimal
    high_low_range: Decimal
    volume_change_1_session: Decimal


@dataclass(frozen=True)
class DevelopmentDailyFeatureResult:
    """In-memory, non-campaign feature materialization with source limitations."""

    source: DevelopmentDailyUniverse
    source_hash: str
    feature_names: tuple[str, ...]
    rows: tuple[DevelopmentDailyFeatureRow, ...]
    availability: str
    raw_close_limitation: str


def materialize_development_daily_features(
    universe: DevelopmentDailyUniverse,
) -> DevelopmentDailyFeatureResult:
    """Materialize fixed, no-lookahead features without labels or decisions."""

    if not isinstance(universe, DevelopmentDailyUniverse):
        raise TypeError("development daily features require DevelopmentDailyUniverse")
    streams = _reverify_broad_daily_development_feature_input(universe)
    if len(streams) != len(universe.reference.symbols):
        raise ValueError("development feature streams do not match fixed symbols")

    rows_by_symbol = {
        symbol: _materialize_symbol_features(symbol, bars)
        for symbol, bars in zip(universe.reference.symbols, streams, strict=True)
    }
    common_sessions = tuple(rows_by_symbol[universe.reference.symbols[0]])
    if any(
        tuple(rows_by_symbol[symbol]) != common_sessions
        for symbol in universe.reference.symbols[1:]
    ):
        raise ValueError("development feature streams must share identical sessions")
    rows = tuple(
        rows_by_symbol[symbol][session]
        for session in common_sessions
        for symbol in universe.reference.symbols
    )
    return DevelopmentDailyFeatureResult(
        source=universe,
        source_hash=universe.reference.dataset_hash,
        feature_names=FEATURE_NAMES,
        rows=rows,
        availability=FEATURE_AVAILABILITY,
        raw_close_limitation=RAW_CLOSE_LIMITATION,
    )


def _materialize_symbol_features(
    symbol: str,
    bars: tuple[Bar, ...],
) -> dict[date, DevelopmentDailyFeatureRow]:
    if len(bars) < _MINIMUM_SESSIONS:
        raise ValueError(
            f"development feature input for {symbol} needs at least {_MINIMUM_SESSIONS} sessions"
        )
    if any(bar.symbol != symbol or not bar.complete for bar in bars):
        raise ValueError("development feature input contains an invalid completed bar")
    rows: dict[date, DevelopmentDailyFeatureRow] = {}
    for index in range(5, len(bars)):
        current = bars[index]
        prior_one = bars[index - 1]
        prior_five = bars[index - 5]
        if current.start_ts <= prior_one.start_ts or prior_one.start_ts <= prior_five.start_ts:
            raise ValueError("development feature input must be strictly chronological")
        session = current.start_ts.date()
        rows[session] = DevelopmentDailyFeatureRow(
            session=session,
            symbol=symbol,
            close_return_5_sessions=current.close / prior_five.close - _ONE,
            close_return_1_session=current.close / prior_one.close - _ONE,
            high_low_range=current.high / current.low - _ONE,
            volume_change_1_session=(current.volume + _ONE) / (prior_one.volume + _ONE)
            - _ONE,
        )
    return rows

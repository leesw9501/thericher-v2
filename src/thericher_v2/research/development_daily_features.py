"""Small, descriptive daily features for the bounded development-only universe."""

from __future__ import annotations

import sys
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
OUTCOME_AVAILABILITY = "after_completed_next_observed_session_close"
RAW_NEXT_OBSERVED_CLOSE_OUTCOME_LIMITATION = (
    "raw next-observed-session close returns can be distorted by unverified "
    "corporate actions"
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


@dataclass(frozen=True)
class DevelopmentDailyFeatureOutcomeRow:
    """One future-only raw-close outcome paired with an immutable feature row."""

    feature: DevelopmentDailyFeatureRow
    outcome_session: date
    calendar_days_to_outcome: int
    raw_next_observed_close_return: Decimal


@dataclass(frozen=True)
class DevelopmentDailyFeatureOutcomeResult:
    """In-memory development outcomes that remain separate from decision inputs."""

    feature_result: DevelopmentDailyFeatureResult
    source_hash: str
    rows: tuple[DevelopmentDailyFeatureOutcomeRow, ...]
    outcome_availability: str
    raw_next_observed_close_outcome_limitation: str


def materialize_development_daily_features(
    universe: DevelopmentDailyUniverse,
) -> DevelopmentDailyFeatureResult:
    """Materialize fixed, no-lookahead features without labels or decisions."""

    if not isinstance(universe, DevelopmentDailyUniverse):
        raise TypeError("development daily features require DevelopmentDailyUniverse")
    streams = _reverify_broad_daily_development_feature_input(universe)
    return _materialize_development_daily_features_from_streams(universe, streams)


def materialize_development_daily_feature_outcomes(
    feature_result: DevelopmentDailyFeatureResult,
) -> DevelopmentDailyFeatureOutcomeResult:
    """Pair each feature row with one future raw-close outcome, never a decision."""

    if not isinstance(feature_result, DevelopmentDailyFeatureResult):
        raise TypeError(
            "development daily outcomes require DevelopmentDailyFeatureResult"
        )
    source = feature_result.source
    if not isinstance(source, DevelopmentDailyUniverse):
        raise TypeError(
            "development daily feature outcome source requires DevelopmentDailyUniverse"
        )
    if feature_result.source_hash != source.reference.dataset_hash:
        raise ValueError("development daily feature result source hash is inconsistent")
    streams = _reverify_broad_daily_development_feature_input(source)
    reattested_features = _materialize_development_daily_features_from_streams(
        source, streams
    )
    if reattested_features != feature_result:
        raise ValueError(
            "development daily feature result does not match re-attested source"
        )
    bars_by_symbol = dict(
        zip(source.reference.symbols, streams, strict=True)
    )
    index_by_symbol_and_session = {
        symbol: {bar.start_ts.date(): index for index, bar in enumerate(bars)}
        for symbol, bars in bars_by_symbol.items()
    }
    rows: list[DevelopmentDailyFeatureOutcomeRow] = []
    for feature in feature_result.rows:
        bars = bars_by_symbol.get(feature.symbol)
        feature_index = index_by_symbol_and_session.get(feature.symbol, {}).get(
            feature.session
        )
        if bars is None or feature_index is None:
            raise ValueError("development feature row is not present in re-attested bars")
        if feature_index + 1 >= len(bars):
            continue
        feature_bar = bars[feature_index]
        outcome_bar = bars[feature_index + 1]
        if outcome_bar.start_ts <= feature_bar.start_ts:
            raise ValueError("development outcome bars must be strictly chronological")
        outcome_session = outcome_bar.start_ts.date()
        calendar_days_to_outcome = (outcome_session - feature.session).days
        if calendar_days_to_outcome <= 0:
            raise ValueError("development outcome session must follow its feature session")
        rows.append(
            DevelopmentDailyFeatureOutcomeRow(
                feature=feature,
                outcome_session=outcome_session,
                calendar_days_to_outcome=calendar_days_to_outcome,
                raw_next_observed_close_return=outcome_bar.close / feature_bar.close
                - _ONE,
            )
        )
    return DevelopmentDailyFeatureOutcomeResult(
        feature_result=feature_result,
        source_hash=feature_result.source_hash,
        rows=tuple(rows),
        outcome_availability=OUTCOME_AVAILABILITY,
        raw_next_observed_close_outcome_limitation=(
            RAW_NEXT_OBSERVED_CLOSE_OUTCOME_LIMITATION
        ),
    )


def _materialize_development_daily_features_from_streams(
    universe: DevelopmentDailyUniverse,
    streams: tuple[tuple[Bar, ...], ...],
) -> DevelopmentDailyFeatureResult:
    caller_module = sys._getframe(1).f_globals.get("__name__")
    if caller_module != __name__:
        raise PermissionError(
            "development feature stream input is restricted to its materializer module"
        )
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

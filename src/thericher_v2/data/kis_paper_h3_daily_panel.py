"""Plan and qualify the native MODP1 OHLC60 input to the H3 proposal producer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas_market_calendars as mcal

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_MAX_ROWS,
    KisPaperDailyAdjustmentProbeQuery,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
    _parse_daily_raw_row,
)
from thericher_v2.execution.kis_paper_data_capture import CaptureQuery, CaptureResult

DEC3_AS_OF = date(2026, 12, 3)
# Ordered axis from the Nov6 NET25 producer's pinned PLAN, not a new universe.
NET25_H3_AXIS = (
    ("AAPL", "NAS"),
    ("AMD", "NAS"),
    ("AMZN", "NAS"),
    ("GOOGL", "NAS"),
    ("META", "NAS"),
    ("MSFT", "NAS"),
    ("NVDA", "NAS"),
    ("TSLA", "NAS"),
    ("JPM", "NYS"),
    ("JNJ", "NYS"),
    ("XOM", "NYS"),
    ("PG", "NYS"),
    ("KO", "NYS"),
    ("HD", "NYS"),
    ("V", "NYS"),
    ("DIS", "NYS"),
    ("UNH", "NYS"),
    ("SPY", "AMS"),
    ("QQQ", "NAS"),
)
_SESSION_COUNT = 60
_SYMBOL_COUNT = 19
_NATIVE_FIELDS = {"xymd", "open", "high", "low", "clos", "tvol"}


class H3DailyPanelError(ValueError):
    """Categorical refusal, without native values or private references."""


@dataclass(frozen=True)
class H3DailyPanelPlan:
    """One dated first-page query per ordered, caller-attested symbol/venue pair."""

    axis: tuple[tuple[str, str], ...]
    as_of: date = DEC3_AS_OF
    sessions: tuple[date, ...] = field(init=False)
    capture_sessions: tuple[date, ...] = field(init=False)
    as_of_close_utc: datetime = field(init=False)
    queries: tuple[CaptureQuery, ...] = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.axis) is not tuple
            or len(self.axis) != _SYMBOL_COUNT
            or any(
                type(pair) is not tuple
                or len(pair) != 2
                or any(type(value) is not str or value != value.strip().upper() for value in pair)
                for pair in self.axis
            )
            or len({symbol for symbol, _ in self.axis}) != _SYMBOL_COUNT
        ):
            raise H3DailyPanelError("h3_panel_axis_invalid")
        if type(self.as_of) is not date:
            raise H3DailyPanelError("h3_panel_as_of_invalid")
        calendar = mcal.get_calendar("NASDAQ")
        schedule = calendar.schedule(self.as_of - timedelta(days=200), self.as_of).tail(
            KIS_PAPER_DAILY_MAX_ROWS
        )
        capture_sessions = tuple(day.date() for day in schedule.index)
        if len(capture_sessions) != KIS_PAPER_DAILY_MAX_ROWS or capture_sessions[-1] != self.as_of:
            raise H3DailyPanelError("h3_panel_as_of_not_session")
        # BYMD has no lower bound on the wire: constrain a full page, then project OHLC60.
        first, last = (day.strftime("%Y%m%d") for day in (capture_sessions[0], self.as_of))
        # The capture session requires one identical allowlist on every daily query.
        scope = {symbol: frozenset({venue}) for symbol, venue in self.axis}
        try:
            queries = tuple(
                CaptureQuery(
                    KisPaperDailyAdjustmentProbeQuery(
                        symbol=symbol,
                        exchange=venue,
                        by_date=last,
                        adjustment_mode="1",
                        approved_symbol_exchanges=scope,
                    ),
                    first,
                    last,
                )
                for symbol, venue in self.axis
            )
        except ValueError:
            raise H3DailyPanelError("h3_panel_query_invalid") from None
        object.__setattr__(self, "capture_sessions", capture_sessions)
        object.__setattr__(self, "sessions", capture_sessions[-_SESSION_COUNT:])
        object.__setattr__(
            self, "as_of_close_utc", schedule["market_close"].iloc[-1].to_pydatetime()
        )
        object.__setattr__(self, "queries", queries)


@dataclass(frozen=True)
class H3DailyPanel:
    """Complete decimal-text native rows, chronological then in plan axis order."""

    plan: H3DailyPanelPlan
    rows: tuple[tuple[KisPaperDailyRawRow, ...], ...] = field(repr=False)


def qualify_h3_daily_panel(
    plan: H3DailyPanelPlan, captures: Iterable[tuple[CaptureResult, bytes]]
) -> H3DailyPanel:
    """Qualify trusted capture results and their already-read native JSON bytes.

    This is a data-only check. The caller owns custody and proof of post-close
    acquisition; neither a date key nor an accepted result proves finality.
    """
    keys = tuple(query.key for query in plan.queries)
    expected = {day.strftime("%Y%m%d") for day in plan.sessions}
    allowed = {day.strftime("%Y%m%d") for day in plan.capture_sessions}
    columns = {}
    for result, native in captures:
        if type(result) is not CaptureResult or result.query_key not in keys:
            raise H3DailyPanelError("h3_panel_query_mismatch")
        if result.query_key in columns:
            raise H3DailyPanelError("h3_panel_duplicate_query")
        if result.status != "ACCEPTED":
            raise H3DailyPanelError("h3_panel_capture_not_accepted")
        if (
            type(native) is not bytes
            or result.native is None
            or hashlib.sha256(native).hexdigest() != result.native.get("sha256")
        ):
            raise H3DailyPanelError("h3_panel_native_digest_mismatch")
        columns[result.query_key] = _qualify_column(native, result.row_count, expected, allowed)
    if set(columns) != set(keys):
        raise H3DailyPanelError("h3_panel_missing_query")
    return H3DailyPanel(
        plan,
        tuple(tuple(columns[key][day] for key in keys) for day in sorted(expected)),
    )


def _qualify_column(
    native: bytes, reported_count: int | None, expected: set[str], allowed: set[str]
) -> dict[str, KisPaperDailyRawRow]:
    try:
        documents = json.loads(native)
    except (ValueError, RecursionError):
        raise H3DailyPanelError("h3_panel_native_schema_invalid") from None
    if type(documents) is not list:
        raise H3DailyPanelError("h3_panel_native_schema_invalid")
    if type(reported_count) is not int or len(documents) != reported_count:
        raise H3DailyPanelError("h3_panel_native_count_mismatch")
    by_date = {}
    for document in documents:
        if type(document) is not dict or set(document) != _NATIVE_FIELDS:
            raise H3DailyPanelError("h3_panel_native_schema_invalid")
        try:
            row = _parse_daily_raw_row(document)
        except KisPaperMarketDataError:
            raise H3DailyPanelError("h3_panel_native_ohlcv_invalid") from None
        if row.xymd in by_date:
            raise H3DailyPanelError("h3_panel_duplicate_session")
        by_date[row.xymd] = row
    if not expected <= by_date.keys() <= allowed:
        raise H3DailyPanelError("h3_panel_session_coverage")
    return by_date

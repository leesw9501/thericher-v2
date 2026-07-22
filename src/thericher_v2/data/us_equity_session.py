"""Small source-backed US equity session windows for the active 2026 scope."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from .resample import SessionWindow

US_EQUITY_2026_NASDAQ_CALENDAR_URL = "https://www.nasdaqtrader.com/Trader.aspx?id=calendar"
US_EQUITY_2026_NYSE_CALENDAR_URL = "https://www.nyse.com/trade/hours-calendars?ecid=null"
US_EQUITY_2026_SESSION_SOURCES = (
    US_EQUITY_2026_NASDAQ_CALENDAR_URL,
    US_EQUITY_2026_NYSE_CALENDAR_URL,
)
US_EQUITY_EASTERN = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)
_CLOSED_DATES = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
    }
)
_EARLY_CLOSE_DATES = frozenset({date(2026, 11, 27), date(2026, 12, 24)})


@dataclass(frozen=True)
class UsEquity2026Session:
    """One 2026 NASDAQ/NYSE-Arca core session, expressed in UTC."""

    session_date: date
    kind: Literal["regular", "early_close"]
    window: SessionWindow
    sources: tuple[str, str] = US_EQUITY_2026_SESSION_SOURCES


def us_equity_2026_session(session_date: date) -> UsEquity2026Session | None:
    """Return the official 2026 core session or ``None`` for a closed date.

    This intentionally covers only the active 2026 KIS cache scope. It does
    not interpret a provider timestamp as an exchange bar-start/bar-end claim.
    """

    if type(session_date) is not date:
        raise ValueError("US equity session date is invalid")
    if session_date.year != 2026:
        raise ValueError("US equity session date is outside the 2026 source scope")
    if session_date.weekday() >= 5 or session_date in _CLOSED_DATES:
        return None
    kind: Literal["regular", "early_close"] = (
        "early_close" if session_date in _EARLY_CLOSE_DATES else "regular"
    )
    close = _EARLY_CLOSE if kind == "early_close" else _REGULAR_CLOSE
    open_utc = datetime.combine(session_date, _REGULAR_OPEN, US_EQUITY_EASTERN).astimezone(UTC)
    close_utc = datetime.combine(session_date, close, US_EQUITY_EASTERN).astimezone(UTC)
    return UsEquity2026Session(
        session_date=session_date,
        kind=kind,
        window=SessionWindow(open_ts=open_utc, close_ts=close_utc),
    )

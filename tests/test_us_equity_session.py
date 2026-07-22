from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session


def test_regular_2026_session_uses_eastern_core_hours_in_utc() -> None:
    session = us_equity_2026_session(date(2026, 7, 21))

    assert session is not None
    assert session.kind == "regular"
    assert session.window.open_ts == datetime(2026, 7, 21, 13, 30, tzinfo=UTC)
    assert session.window.close_ts == datetime(2026, 7, 21, 20, 0, tzinfo=UTC)


def test_closed_and_early_close_2026_dates_have_explicit_windows() -> None:
    assert us_equity_2026_session(date(2026, 7, 3)) is None
    early_close = us_equity_2026_session(date(2026, 11, 27))

    assert early_close is not None
    assert early_close.kind == "early_close"
    assert early_close.window.open_ts == datetime(2026, 11, 27, 14, 30, tzinfo=UTC)
    assert early_close.window.close_ts == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)


def test_session_calendar_refuses_dates_outside_its_sourced_2026_scope() -> None:
    with pytest.raises(ValueError, match="outside the 2026"):
        us_equity_2026_session(date(2027, 1, 4))

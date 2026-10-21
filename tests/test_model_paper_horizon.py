"""Pure canonical holding clocks for the future FUND20 ModelPaper consumer."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.model_paper_horizon import (
    MODEL_PAPER_20_SESSION_PROFILE,
    MODEL_PAPER_V1_PROFILE,
    model_paper_horizon_valid,
    validate_model_paper_horizon,
)


def window(day):
    return us_equity_2026_session(day).window


def test_twenty_official_sessions_include_veterans_day_and_cross_dst():
    first, last = window(date(2026, 10, 21)), window(date(2026, 11, 17))
    validate_model_paper_horizon(first, last, profile=MODEL_PAPER_20_SESSION_PROFILE)
    assert model_paper_horizon_valid(first, last, profile=MODEL_PAPER_20_SESSION_PROFILE)
    assert first.open_ts == datetime(2026, 10, 21, 13, 30, tzinfo=UTC)
    assert last.close_ts == datetime(2026, 11, 17, 21, tzinfo=UTC)
    assert us_equity_2026_session(date(2026, 11, 11)) is not None
    assert (
        sum(
            us_equity_2026_session(date(2026, 10, 21) + timedelta(days=i)) is not None
            for i in range(28)
        )
        == 20
    )


@pytest.mark.parametrize("last_day", [date(2026, 11, 16), date(2026, 11, 18)])
def test_nineteen_or_twenty_one_sessions_cannot_be_reinterpreted(last_day):
    with pytest.raises(ValueError, match="model_20session_horizon_invalid"):
        validate_model_paper_horizon(
            window(date(2026, 10, 21)), window(last_day), profile=MODEL_PAPER_20_SESSION_PROFILE
        )


@pytest.mark.parametrize("which", ["entry_open", "entry_close", "exit_open", "exit_close"])
def test_shifted_utc_clock_is_not_the_canonical_session(which):
    first, last = window(date(2026, 10, 21)), window(date(2026, 11, 17))
    if which.startswith("entry"):
        field = "open_ts" if which.endswith("open") else "close_ts"
        first = replace(first, **{field: getattr(first, field) + timedelta(hours=1)})
    else:
        field = "open_ts" if which.endswith("open") else "close_ts"
        last = replace(last, **{field: getattr(last, field) - timedelta(hours=1)})
    assert not model_paper_horizon_valid(first, last, profile=MODEL_PAPER_20_SESSION_PROFILE)


def test_weekend_start_is_not_silently_advanced_to_next_open():
    first = SessionWindow(
        datetime(2026, 10, 24, 13, 30, tzinfo=UTC), datetime(2026, 10, 24, 20, tzinfo=UTC)
    )
    assert not model_paper_horizon_valid(
        first, window(date(2026, 11, 20)), profile=MODEL_PAPER_20_SESSION_PROFILE
    )


@pytest.mark.parametrize("year", [2025, 2027])
def test_non_2026_calendar_is_unsupported_not_extrapolated(year):
    first = SessionWindow(
        datetime(year, 10, 21, 13, tzinfo=UTC), datetime(year, 10, 21, 20, tzinfo=UTC)
    )
    last = SessionWindow(
        datetime(year, 11, 17, 14, tzinfo=UTC), datetime(year, 11, 17, 21, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="model_20session_calendar_scope_invalid"):
        validate_model_paper_horizon(first, last, profile=MODEL_PAPER_20_SESSION_PROFILE)


def test_twenty_sessions_cannot_run_off_the_native_calendar_year():
    assert not model_paper_horizon_valid(
        window(date(2026, 12, 15)),
        window(date(2026, 12, 31)),
        profile=MODEL_PAPER_20_SESSION_PROFILE,
    )


def test_official_early_close_is_respected_instead_of_fixed_sixteen_hours():
    # Oct 30 .. Nov 27 is 20 sessions: Nov 26 is closed and Nov 27 closes early.
    first, last = window(date(2026, 10, 30)), window(date(2026, 11, 27))
    assert last.close_ts == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert model_paper_horizon_valid(first, last, profile=MODEL_PAPER_20_SESSION_PROFILE)
    assert not model_paper_horizon_valid(
        first,
        replace(last, close_ts=last.close_ts + timedelta(hours=3)),
        profile=MODEL_PAPER_20_SESSION_PROFILE,
    )


def test_v1_fourteen_calendar_day_boundary_is_not_relaxed():
    first = window(date(2026, 10, 21))
    boundary = first.open_ts + timedelta(days=14)
    last = SessionWindow(boundary - timedelta(hours=1), boundary)
    validate_model_paper_horizon(first, last, profile=MODEL_PAPER_V1_PROFILE)
    assert not model_paper_horizon_valid(
        first,
        replace(last, close_ts=boundary + timedelta(microseconds=1)),
        profile=MODEL_PAPER_V1_PROFILE,
    )
    assert not model_paper_horizon_valid(
        first, window(date(2026, 11, 17)), profile=MODEL_PAPER_V1_PROFILE
    )


@pytest.mark.parametrize("profile", ["unknown", "model-proposal-nas-20session-v0", None])
def test_unsupported_profile_never_defaults_to_v1(profile):
    assert not model_paper_horizon_valid(
        window(date(2026, 10, 21)), window(date(2026, 10, 27)), profile=profile
    )


@pytest.mark.parametrize("which", ["first", "last"])
def test_wrong_session_type_fails_closed(which):
    first, last = window(date(2026, 10, 21)), window(date(2026, 11, 17))
    assert not model_paper_horizon_valid(
        None if which == "first" else first,
        None if which == "last" else last,
        profile=MODEL_PAPER_20_SESSION_PROFILE,
    )

"""Scoped holding sessions for committed FUND20 proposals in native ModelPaper."""

from datetime import timedelta

from thericher_v2.data.us_equity_session import (
    US_EQUITY_EASTERN,
    us_equity_2026_session,
)
from thericher_v2.market.resample import SessionWindow

MODEL_PAPER_20_SESSION_PROFILE = "model-proposal-nas-20session-2026-v1"
MODEL_PAPER_V1_PROFILE = "model-proposal-nas-v1"
MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE = "model-proposal-nas-post-open-prior-session-v1"


def prior_official_session_close(first):
    """Exact prior close in the supported calendar, never a calendar-day approximation."""
    day = first.open_ts.astimezone(US_EQUITY_EASTERN).date()
    for offset in range(1, 15):
        previous = day - timedelta(days=offset)
        if previous.year != 2026:
            break
        session = us_equity_2026_session(previous)
        if session is not None:
            return session.window.close_ts
    raise ValueError("model_prior_session_calendar_scope_invalid")


def _validate_post_open_five_sessions(first, last):
    start = first.open_ts.astimezone(US_EQUITY_EASTERN).date()
    windows = []
    for offset in range(15):
        day = start + timedelta(days=offset)
        if day.year != 2026:
            raise ValueError("model_5session_calendar_scope_invalid")
        session = us_equity_2026_session(day)
        if session is not None:
            windows.append(session.window)
            if len(windows) == 5:
                break
    if len(windows) != 5 or windows[0] != first or windows[-1] != last:
        raise ValueError("model_5session_horizon_invalid")


def validate_model_paper_horizon(first, last, *, profile):
    if type(first) is not SessionWindow or type(last) is not SessionWindow:
        raise ValueError("model_sessions_invalid")
    if not first.open_ts < first.close_ts < last.open_ts < last.close_ts:
        raise ValueError("model_session_clocks_invalid")
    if profile == MODEL_PAPER_POST_OPEN_PRIOR_SESSION_PROFILE:
        _validate_post_open_five_sessions(first, last)
        return
    if profile == MODEL_PAPER_V1_PROFILE:
        if last.close_ts > first.open_ts + timedelta(days=14):
            raise ValueError("model_session_clocks_invalid")
        return
    if profile != MODEL_PAPER_20_SESSION_PROFILE:
        raise ValueError("model_profile_invalid")
    start = first.open_ts.astimezone(US_EQUITY_EASTERN).date()
    windows = []
    # Finite native-calendar scope, not a raised generic calendar-day ceiling.
    for offset in range(366):
        day = start + timedelta(days=offset)
        if day.year != 2026:
            raise ValueError("model_20session_calendar_scope_invalid")
        session = us_equity_2026_session(day)
        if session is not None:
            windows.append(session.window)
            if len(windows) == 20:
                break
    if len(windows) != 20 or windows[0] != first or windows[-1] != last:
        raise ValueError("model_20session_horizon_invalid")


def model_paper_horizon_valid(first, last, *, profile):
    try:
        validate_model_paper_horizon(first, last, profile=profile)
    except (ValueError, TypeError, AttributeError, OverflowError):
        return False
    return True

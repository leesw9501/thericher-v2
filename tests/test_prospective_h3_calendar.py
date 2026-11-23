from datetime import date, datetime

import pytest

from thericher_v2.research.prospective_h3_calendar import (
    H3Interval,
    select_prospective_h3_intervals,
)

SESSIONS = tuple(date(2026, 11, day) for day in (20, 23, 24, 25, 27, 30)) + tuple(
    date(2026, 12, day) for day in (1, 2, 3, 4)
)


@pytest.mark.parametrize("earliest_entry", [date(2026, 11, 22), date(2026, 11, 23)])
def test_selects_exact_count_by_session_offset_with_no_shared_boundary(earliest_entry):
    assert select_prospective_h3_intervals(SESSIONS, earliest_entry=earliest_entry, count=2) == (
        H3Interval(date(2026, 11, 23), date(2026, 11, 27)),
        H3Interval(date(2026, 11, 30), date(2026, 12, 3)),
    )


def test_exact_capacity_starts_at_first_session_when_cutoff_precedes_calendar():
    assert select_prospective_h3_intervals(
        list(SESSIONS[:4]), earliest_entry=date(2026, 11, 19), count=1
    ) == (H3Interval(SESSIONS[0], SESSIONS[3]),)


@pytest.mark.parametrize(
    ("sessions", "earliest_entry", "count"),
    [
        ((), SESSIONS[0], 1),
        (SESSIONS, date(2026, 12, 5), 1),
        (SESSIONS[:8], SESSIONS[1], 2),
    ],
)
def test_insufficient_sessions_rejects_entire_request(sessions, earliest_entry, count):
    with pytest.raises(ValueError, match="insufficient sessions"):
        select_prospective_h3_intervals(sessions, earliest_entry=earliest_entry, count=count)


@pytest.mark.parametrize("sessions", [SESSIONS + (SESSIONS[-1],), SESSIONS[::-1]])
def test_rejects_duplicate_or_out_of_order_sessions(sessions):
    with pytest.raises(ValueError, match="strictly chronological"):
        select_prospective_h3_intervals(sessions, earliest_entry=SESSIONS[0], count=1)


@pytest.mark.parametrize("count", [0, -1, True, 1.0])
def test_rejects_invalid_count(count):
    with pytest.raises(ValueError, match="positive integer"):
        select_prospective_h3_intervals(SESSIONS, earliest_entry=SESSIONS[0], count=count)


@pytest.mark.parametrize(
    ("sessions", "earliest_entry"),
    [(SESSIONS + ("2026-12-07",), SESSIONS[0]), (SESSIONS, datetime(2026, 11, 20))],
)
def test_requires_dates_not_strings_or_datetimes(sessions, earliest_entry):
    with pytest.raises(ValueError, match="must be dates"):
        select_prospective_h3_intervals(sessions, earliest_entry=earliest_entry, count=1)

"""Freeze session intervals for prospective H3 evaluation without outcome data."""

from bisect import bisect_left
from collections.abc import Sequence
from datetime import date
from itertools import pairwise
from typing import NamedTuple

_EXPIRY_OFFSET = 3
_ENTRY_STRIDE = _EXPIRY_OFFSET + 1


class H3Interval(NamedTuple):
    entry: date
    expiry: date


def select_prospective_h3_intervals(
    sessions: Sequence[date], *, earliest_entry: date, count: int
) -> tuple[H3Interval, ...]:
    """Select exactly ``count`` H3 intervals from caller-supplied sessions.

    The first entry is on or after ``earliest_entry``. Each expiry is three
    session positions after its entry, and the next entry is the session after
    expiry. Calendar completeness is the caller's responsibility.
    """
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    if type(earliest_entry) is not date or any(type(day) is not date for day in sessions):
        raise ValueError("sessions and earliest_entry must be dates")
    if any(left >= right for left, right in pairwise(sessions)):
        raise ValueError("sessions must be strictly chronological")

    first = bisect_left(sessions, earliest_entry)
    stop = first + count * _ENTRY_STRIDE
    if stop > len(sessions):
        raise ValueError("insufficient sessions for requested H3 intervals")
    return tuple(
        H3Interval(sessions[entry], sessions[entry + _EXPIRY_OFFSET])
        for entry in range(first, stop, _ENTRY_STRIDE)
    )

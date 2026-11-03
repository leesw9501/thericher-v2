"""Pure retention assessment for the next US19 raw historical-minute dataset.

The external collector owns bytes, networking and cursor persistence. These
objects never constitute engine Bars, qualified features or Paper input.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from enum import StrEnum
from typing import Literal


class CaptureIssue(StrEnum):
    EMPTY_PAGE = "empty_page"
    INVALID_REQUEST_KEY = "invalid_request_key"
    MALFORMED_EXCHANGE_CLOCK = "malformed_exchange_clock"
    AMBIGUOUS_EXCHANGE_CLOCK = "ambiguous_exchange_clock"
    NONEXISTENT_EXCHANGE_CLOCK = "nonexistent_exchange_clock"
    DUPLICATE_EXCHANGE_STAMP = "duplicate_exchange_stamp"
    NON_MONOTONIC_EXCHANGE_STAMPS = "non_monotonic_exchange_stamps"
    NEWER_THAN_REQUEST_KEY = "newer_than_request_key"
    MULTI_DATE_HEAD = "multi_date_head"
    KOREA_CLOCK_UNAVAILABLE = "korea_clock_unavailable"
    KOREA_CLOCK_MISMATCH = "korea_clock_mismatch"


@dataclass(frozen=True)
class RawMinuteClock:
    """Provider labels retained verbatim, including missing or malformed text."""

    exchange_date: str | None
    exchange_time: str | None
    korea_date: str | None
    korea_time: str | None


@dataclass(frozen=True)
class AssessedMinuteClock:
    raw: RawMinuteClock
    exchange_label_utc: datetime | None
    korea_label_utc: datetime | None
    korea_minus_exchange_seconds: int | None
    issues: frozenset[CaptureIssue]


class UnqualifiedHistoricalCaptureError(ValueError):
    """Raw retention is not a qualified model/Paper data handoff."""


@dataclass(frozen=True)
class HistoricalCaptureAssessment:
    rows: tuple[AssessedMinuteClock, ...]
    issues: frozenset[CaptureIssue]
    cursor_can_advance: bool
    next_exchange_key: str | None
    exchange_ascending: bool
    exchange_descending: bool
    exchange_duplicate_count: int
    max_exceeds_requested_key: bool

    @property
    def captured_count(self) -> int:
        return len(self.rows)

    @property
    def qualified_count(self) -> Literal[0]:
        return 0

    @property
    def training_eligible(self) -> Literal[False]:
        return False

    @property
    def clock_basis(self) -> Literal["exchange_local_label_proxy"]:
        return "exchange_local_label_proxy"

    @property
    def exchange_clock_asserted(self) -> Literal[True]:
        return True

    @property
    def cursor_action(self) -> Literal["advance", "close_exact_cursor"]:
        return "advance" if self.cursor_can_advance else "close_exact_cursor"

    @property
    def korea_mismatch_count(self) -> int:
        return sum(CaptureIssue.KOREA_CLOCK_MISMATCH in row.issues for row in self.rows)

    @property
    def korea_unavailable_count(self) -> int:
        return sum(CaptureIssue.KOREA_CLOCK_UNAVAILABLE in row.issues for row in self.rows)

    def require_qualified(self) -> None:
        raise UnqualifiedHistoricalCaptureError(
            "raw historical capture requires a separate qualified handoff"
        )


def _label(date: object, time: object) -> datetime | None:
    if (
        not isinstance(date, str)
        or not isinstance(time, str)
        or len(date) != 8
        or len(time) != 6
        or not date.isascii()
        or not time.isascii()
        or not date.isdigit()
        or not time.isdigit()
    ):
        return None
    try:
        return datetime.strptime(date + time, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _resolve(label: datetime, zone: tzinfo) -> tuple[datetime | None, str | None]:
    candidates = set()
    for fold in (0, 1):
        utc = label.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == label:
            candidates.add(utc)
    if not candidates:
        return None, "nonexistent"
    if len(candidates) != 1:
        return None, "ambiguous"
    return candidates.pop(), None


def assess_historical_capture(
    clocks: Sequence[RawMinuteClock],
    *,
    requested_key: str | None,
    exchange_timezone: tzinfo,
    korea_timezone: tzinfo,
) -> HistoricalCaptureAssessment:
    """Assess one page without repairing raw labels or granting qualification.

    Only exchange-label structure controls raw cursor advance. Korea labels
    remain independent diagnostics. UTC values are label proxies, not claims
    about provider bar boundaries, publication time, finality or PIT.
    """
    assessed = []
    stamps = []
    issues: set[CaptureIssue] = set()
    exchange_valid = True
    for raw in clocks:
        if not isinstance(raw, RawMinuteClock):
            raise TypeError("clock rows must be RawMinuteClock")
        row_issues = set()
        local = _label(raw.exchange_date, raw.exchange_time)
        exchange_utc = None
        if local is None:
            row_issues.add(CaptureIssue.MALFORMED_EXCHANGE_CLOCK)
        else:
            exchange_utc, error = _resolve(local, exchange_timezone)
            if error == "ambiguous":
                row_issues.add(CaptureIssue.AMBIGUOUS_EXCHANGE_CLOCK)
            elif error == "nonexistent":
                row_issues.add(CaptureIssue.NONEXISTENT_EXCHANGE_CLOCK)
            else:
                stamps.append(local.strftime("%Y%m%d%H%M%S"))
        exchange_valid &= exchange_utc is not None
        korea = _label(raw.korea_date, raw.korea_time)
        korea_utc = _resolve(korea, korea_timezone)[0] if korea is not None else None
        if korea_utc is None:
            row_issues.add(CaptureIssue.KOREA_CLOCK_UNAVAILABLE)
        delta = None
        if exchange_utc is not None and korea_utc is not None:
            delta = int((korea_utc - exchange_utc).total_seconds())
            if delta != 0:
                row_issues.add(CaptureIssue.KOREA_CLOCK_MISMATCH)
        assessed.append(AssessedMinuteClock(
            raw, exchange_utc, korea_utc, delta, frozenset(row_issues),
        ))
        issues.update(row_issues)

    key_label = None
    key_valid = requested_key is None
    if isinstance(requested_key, str) and len(requested_key) == 14:
        key_label = _label(requested_key[:8], requested_key[8:])
        key_valid = (
            key_label is not None and _resolve(key_label, exchange_timezone)[0] is not None
        )
    if not key_valid:
        issues.add(CaptureIssue.INVALID_REQUEST_KEY)
    if not assessed:
        issues.add(CaptureIssue.EMPTY_PAGE)
    duplicates = len(stamps) - len(set(stamps))
    ascending = exchange_valid and stamps == sorted(stamps)
    descending = exchange_valid and stamps == sorted(stamps, reverse=True)
    if duplicates:
        issues.add(CaptureIssue.DUPLICATE_EXCHANGE_STAMP)
    if exchange_valid and not (ascending or descending):
        issues.add(CaptureIssue.NON_MONOTONIC_EXCHANGE_STAMPS)
    newer = bool(stamps and key_valid and requested_key is not None and max(stamps) > requested_key)
    if newer:
        issues.add(CaptureIssue.NEWER_THAN_REQUEST_KEY)
    multiple_head_dates = requested_key is None and len({stamp[:8] for stamp in stamps}) > 1
    if multiple_head_dates:
        issues.add(CaptureIssue.MULTI_DATE_HEAD)
    advance = (
        bool(assessed) and exchange_valid and key_valid and not duplicates
        and (ascending or descending) and not newer and not multiple_head_dates
    )
    next_key = None
    if advance:
        oldest = datetime.strptime(min(stamps), "%Y%m%d%H%M%S")
        next_key = (oldest - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")
    return HistoricalCaptureAssessment(
        tuple(assessed), frozenset(issues), advance, next_key,
        ascending, descending, duplicates, newer,
    )

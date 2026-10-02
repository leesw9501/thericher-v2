"""Bounded, source-safe KIS Paper 1m pagination capability probe.

The probe uses the existing paper-only market-data client, keeps returned bars
only long enough to classify pagination behavior, and persists no raw market
data. It is intentionally a measurement tool rather than a cache collector.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MINUTE_CURRENT_HEAD_ONLY_TARGETS,
    KIS_PAPER_MINUTE_MAX_ROWS,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinuteContinuationSignal,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
)

KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET = ("QQQ", "NAS")
KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS = frozenset({"QQQ/NAS/1m", "SPY/AMS/1m"})
KIS_PAPER_MINUTE_CAPABILITY_PROBE_OBSERVED_TARGET_KEYS = frozenset({"SPY/NAS/1m"})
KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS = frozenset(
    f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_PAPER_MINUTE_CURRENT_HEAD_ONLY_TARGETS
)
KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET_KEYS = (
    KIS_PAPER_MINUTE_CAPABILITY_PROBE_NATIVE_TARGET_KEYS
    | KIS_PAPER_MINUTE_CAPABILITY_PROBE_OBSERVED_TARGET_KEYS
    | KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS
)
KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES = 3
KIS_PAPER_MINUTE_CAPABILITY_PROBE_ARTIFACT_DIRECTORY = "data/kis-paper-minute-capability-probe"
KIS_PAPER_MINUTE_CAPABILITY_PROBE_MIN_INTERVAL_SECONDS = 1.0
KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS = ("20260901120000", "20260803120000")

_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "minute_cursor_invalid",
        "minute_cursor_stalled",
        "minute_page_limit_exceeded",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "token_request_not_due",
        "transport_failure",
    }
)

_PageProgressCategory = Literal[
    "initial",
    "duplicate_within_page",
    "strictly_older_nonoverlapping",
    "overlap_or_not_older",
    "terminal_head_repeat",
]
_CursorProgressCategory = Literal[
    "not_observed",
    "single_page",
    "terminal_head_repeat",
    "strictly_backward_nonoverlapping",
    "duplicate_or_not_older",
]
_BodyMoreCategory = Literal["blank_or_absent", "zero", "one", "other_nonblank"]
_ExplicitOlderKeyCategory = Literal[
    "not_requested",
    "head_unavailable",
    "head_not_full",
    "header_continuation_present",
    "duplicate_keys",
    "older_keys_observed",
    "overlap_with_older_keys",
    "no_older_keys",
    "page2_rejected",
]


class KisPaperMinuteCapabilityProbeClient(Protocol):
    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts: ...

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage: ...


@dataclass(frozen=True)
class KisPaperMinuteCapabilityProbeOutcome:
    """Categorical evidence from one bounded allowlisted minute probe."""

    status: Literal["complete", "partial", "unavailable"]
    observed_at: datetime
    accepted_page_count: int
    accepted_page_size_category: Literal["none", "all_full", "some_partial"]
    continuation_category: Literal[
        "not_observed",
        "terminal",
        "continued",
        "available_at_probe_cap",
        "continuation_failed",
        "cursor_stalled",
        "duplicate_conflict",
    ]
    page_progress_categories: tuple[_PageProgressCategory, ...]
    cursor_progress_category: _CursorProgressCategory
    probe_pattern_category: Literal[
        "single_terminal_page",
        "terminal_head_repeat",
        "cursor_chain",
    ]
    historical_range_category: Literal[
        "not_observed",
        "single_exchange_date",
        "multiple_exchange_dates",
    ]
    minute_spacing_category: Literal[
        "not_observed",
        "single_minute",
        "contiguous_after_deduplication",
        "gap_observed",
    ]
    response_class: str
    token_reuse_category: Literal[
        "not_observed",
        "single_token_single_page",
        "single_token_reused",
        "multiple_token_attempts",
    ]
    request_start_category: Literal[
        "not_observed",
        "single_get",
        "at_or_below_existing_gate",
        "faster_than_existing_gate",
        "timestamps_incomplete",
    ]
    tested_request_interval_seconds: float
    token_request_count: int
    minute_page_request_count: int
    daily_page_request_count: int
    request_attempt_count: int
    categorical_limit_or_error_count: int
    elapsed_time_category: Literal[
        "under_5_seconds",
        "under_30_seconds",
        "30_seconds_or_more",
    ]
    calibration_fact: str
    pacing_recalibration_fact: str
    include_previous_day: bool = False
    target_key: str = "QQQ/NAS/1m"
    schema_version: int = SCHEMA_VERSION
    explicit_older_key_once: bool = False
    continuation_signal_categories: tuple[KisPaperMinuteContinuationSignal, ...] = ()
    body_more_categories: tuple[_BodyMoreCategory, ...] = ()
    explicit_older_key_category: _ExplicitOlderKeyCategory = "not_requested"
    new_older_key_count: int = 0
    overlap_key_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.accepted_page_count < 0:
            raise ValueError("capability probe accepted page count is invalid")
        if self.status == "unavailable" and self.accepted_page_count:
            raise ValueError("unavailable capability probe cannot accept pages")
        if (
            not _is_positive_finite(self.tested_request_interval_seconds)
            or min(
                self.token_request_count,
                self.minute_page_request_count,
                self.daily_page_request_count,
                self.request_attempt_count,
            )
            < 0
            or self.request_attempt_count
            != (
                self.token_request_count
                + self.minute_page_request_count
                + self.daily_page_request_count
            )
            or self.request_attempt_count < self.accepted_page_count
            or self.categorical_limit_or_error_count not in {0, 1}
            or not self.response_class
            or not self.calibration_fact
            or not self.pacing_recalibration_fact
            or type(self.include_previous_day) is not bool
            or self.target_key not in KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET_KEYS
        ):
            raise ValueError("capability probe observation is invalid")
        if len(self.page_progress_categories) != self.accepted_page_count:
            raise ValueError("capability probe page progress is invalid")
        if type(self.explicit_older_key_once) is not bool:
            raise ValueError("capability probe explicit older-key mode is invalid")
        if self.explicit_older_key_once:
            if (
                self.target_key != "QQQ/NAS/1m"
                or self.include_previous_day
                or self.minute_page_request_count > 2
                or self.accepted_page_count > 2
                or len(self.continuation_signal_categories) != self.accepted_page_count
                or len(self.body_more_categories) != self.accepted_page_count
                or any(
                    signal
                    not in {"recognized_continuation", "blank_or_absent", "unrecognized_nonblank"}
                    for signal in self.continuation_signal_categories
                )
                or any(
                    signal not in {"blank_or_absent", "zero", "one", "other_nonblank"}
                    for signal in self.body_more_categories
                )
                or self.explicit_older_key_category
                not in {
                    "head_unavailable",
                    "head_not_full",
                    "header_continuation_present",
                    "duplicate_keys",
                    "older_keys_observed",
                    "overlap_with_older_keys",
                    "no_older_keys",
                    "page2_rejected",
                }
                or any(
                    type(count) is not int or not 0 <= count <= KIS_PAPER_MINUTE_MAX_ROWS
                    for count in (self.new_older_key_count, self.overlap_key_count)
                )
            ):
                raise ValueError("capability probe explicit older-key facts are invalid")
        elif (
            self.continuation_signal_categories
            or self.body_more_categories
            or self.explicit_older_key_category != "not_requested"
            or self.new_older_key_count
            or self.overlap_key_count
        ):
            raise ValueError("capability probe explicit older-key facts require opt-in")
        if self.accepted_page_count == 0:
            if self.page_progress_categories or self.cursor_progress_category != "not_observed":
                raise ValueError("capability probe page progress is invalid")
            return
        if self.page_progress_categories[0] not in {"initial", "duplicate_within_page"}:
            raise ValueError("capability probe page progress is invalid")
        if any(category == "initial" for category in self.page_progress_categories[1:]):
            raise ValueError("capability probe page progress is invalid")
        if "duplicate_within_page" in self.page_progress_categories[:-1]:
            raise ValueError("capability probe page progress is invalid")
        expected_progress = _cursor_progress_category(self.page_progress_categories)
        if self.cursor_progress_category != expected_progress:
            raise ValueError("capability probe page progress is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return metadata-only evidence that cannot contain provider rows."""

        payload = {
            "schema_version": self.schema_version,
            "kind": "kis_paper_minute_capability_probe",
            "status": self.status,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": self.target_key,
            "request_scope": (
                "current_and_previous_day" if self.include_previous_day else "current_day_only"
            ),
            "observed_at": self.observed_at.isoformat(),
            "accepted_page_count": self.accepted_page_count,
            "accepted_page_size_category": self.accepted_page_size_category,
            "continuation_category": self.continuation_category,
            "page_progress_categories": list(self.page_progress_categories),
            "cursor_progress_category": self.cursor_progress_category,
            "probe_pattern_category": self.probe_pattern_category,
            "historical_range_category": self.historical_range_category,
            "minute_spacing_category": self.minute_spacing_category,
            "response_class": self.response_class,
            "token_reuse_category": self.token_reuse_category,
            "request_start_category": self.request_start_category,
            "tested_request_interval_seconds": self.tested_request_interval_seconds,
            "token_request_count": self.token_request_count,
            "minute_page_request_count": self.minute_page_request_count,
            "daily_page_request_count": self.daily_page_request_count,
            "request_attempt_count": self.request_attempt_count,
            "categorical_limit_or_error_count": self.categorical_limit_or_error_count,
            "elapsed_time_category": self.elapsed_time_category,
            "provider_request_start_ceiling": "bounded_candidate_only",
            "raw_market_data_retained": False,
            "calibration_fact": self.calibration_fact,
            "pacing_recalibration_fact": self.pacing_recalibration_fact,
        }
        if self.explicit_older_key_once:
            payload.pop("observed_at")
            payload.update(
                request_scope="current_head_then_explicit_older_key",
                explicit_older_key_once=True,
                continuation_signal_categories=list(self.continuation_signal_categories),
                body_more_categories=list(self.body_more_categories),
                explicit_older_key_category=self.explicit_older_key_category,
                new_older_key_count=self.new_older_key_count,
                overlap_key_count=self.overlap_key_count,
            )
        return payload


@dataclass(frozen=True)
class KisPaperMinuteCapabilityProbeResult:
    outcome: KisPaperMinuteCapabilityProbeOutcome | KisPaperMinuteFixedKeyProbeOutcome
    evidence_path: Path
    evidence_sha256: str | None = None


@dataclass(frozen=True)
class KisPaperMinuteFixedKeyPageFacts:
    requested_key: str
    category: Literal[
        "requested_date_observed", "earlier_only", "newer_than_key", "empty", "rejected", "invalid"
    ]
    row_count: int = 0
    unique_timestamp_count: int = 0
    oldest_exchange_key: str | None = None
    newest_exchange_key: str | None = None

    def __post_init__(self) -> None:
        if (
            self.requested_key not in KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS
            or self.category
            not in {
                "requested_date_observed",
                "earlier_only",
                "newer_than_key",
                "empty",
                "rejected",
                "invalid",
            }
            or type(self.row_count) is not int
            or type(self.unique_timestamp_count) is not int
            or not 0 <= self.unique_timestamp_count <= self.row_count <= KIS_PAPER_MINUTE_MAX_ROWS
            or (self.oldest_exchange_key is None) != (self.newest_exchange_key is None)
            or bool(self.row_count) != (self.oldest_exchange_key is not None)
        ):
            raise ValueError("fixed-key probe page facts are invalid")
        if self.row_count:
            for key in (self.oldest_exchange_key, self.newest_exchange_key):
                _validate_exchange_key(key)
            if self.oldest_exchange_key > self.newest_exchange_key:
                raise ValueError("fixed-key probe timestamp bounds are invalid")
        if self.category in {"requested_date_observed", "earlier_only", "newer_than_key"}:
            expected = (
                "newer_than_key"
                if self.newest_exchange_key is not None
                and self.newest_exchange_key > self.requested_key
                else "requested_date_observed"
                if self.newest_exchange_key is not None
                and self.newest_exchange_key[:8] == self.requested_key[:8]
                else "earlier_only"
            )
            if (
                not self.row_count
                or self.row_count != self.unique_timestamp_count
                or self.category != expected
            ):
                raise ValueError("fixed-key probe date classification is invalid")
        elif self.category != "invalid" and self.row_count:
            raise ValueError("fixed-key probe failure cannot retain page facts")


@dataclass(frozen=True)
class KisPaperMinuteFixedKeyProbeOutcome:
    observed_at: datetime
    pages: tuple[KisPaperMinuteFixedKeyPageFacts, ...]
    call_counts: KisPaperMarketDataCallCounts

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "pages", tuple(self.pages))
        if (
            not 1 <= len(self.pages) <= 2
            or any(type(page) is not KisPaperMinuteFixedKeyPageFacts for page in self.pages)
            or tuple(page.requested_key for page in self.pages)
            != KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS[: len(self.pages)]
            or self.call_counts.daily_page_attempts != 0
            or not 0 <= self.call_counts.minute_page_attempts <= 2
            or not 0 <= self.call_counts.token_attempts <= 1
        ):
            raise ValueError("fixed-key probe outcome is invalid")

    @property
    def status(self) -> Literal["complete", "partial", "unavailable"]:
        parsed = sum(
            page.category in {"requested_date_observed", "earlier_only", "newer_than_key"}
            for page in self.pages
        )
        return "complete" if parsed == 2 else "partial" if parsed else "unavailable"

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_minute_fixed_historical_key_probe",
            "status": self.status,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": "QQQ/NAS/1m",
            "observed_at": self.observed_at.isoformat(),
            "request_scope": "two_fixed_independent_historical_keys",
            "requested_keys": list(KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS),
            "max_minute_page_attempts": 2,
            "token_request_count": self.call_counts.token_attempts,
            "minute_page_request_count": self.call_counts.minute_page_attempts,
            "daily_page_request_count": self.call_counts.daily_page_attempts,
            "raw_market_data_retained": False,
            "exchange_timestamp_semantics": "observed_unqualified",
            "pages": [
                {
                    "requested_key": page.requested_key,
                    "category": page.category,
                    "row_count": page.row_count,
                    "unique_timestamp_count": page.unique_timestamp_count,
                    "oldest_exchange_key": page.oldest_exchange_key,
                    "newest_exchange_key": page.newest_exchange_key,
                }
                for page in self.pages
            ],
        }


def _validate_exchange_key(key: object) -> None:
    if not isinstance(key, str) or len(key) != 14 or not key.isascii() or not key.isdigit():
        raise ValueError("fixed-key probe exchange key is invalid")
    try:
        datetime.strptime(key, "%Y%m%d%H%M%S")
    except ValueError as error:
        raise ValueError("fixed-key probe exchange key is invalid") from error


def validate_kis_paper_minute_fixed_key_probe(
    keys: tuple[str, str] = KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS,
) -> None:
    if type(keys) is not tuple or len(keys) != 2 or keys != KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS:
        raise ValueError("fixed-key probe requires the predeclared two keys")
    for key in keys:
        _validate_exchange_key(key)
    if keys[0][:8] == keys[1][:8] or keys[0][8:] != keys[1][8:]:
        raise ValueError("fixed-key probe requires distinct dates at the same exchange clock")


def run_kis_paper_minute_fixed_key_probe(
    *,
    client: KisPaperMinuteCapabilityProbeClient,
    observed_at: datetime,
    keys: tuple[str, str] = KIS_PAPER_MINUTE_FIXED_HISTORICAL_KEYS,
) -> KisPaperMinuteFixedKeyProbeOutcome:
    """Measure fixed continuation keys, not a documented arbitrary-date start guarantee."""
    validate_kis_paper_minute_fixed_key_probe(keys)
    captured_at = require_utc(observed_at, "observed_at")
    if client.call_counts != KisPaperMarketDataCallCounts(0, 0, 0):
        raise ValueError("fixed-key probe requires an unused single client")
    pages = []
    for key in keys:
        query = KisPaperMinuteQuery(
            symbol="QQQ",
            exchange="NAS",
            include_previous_day=True,
            continuation_next="1",
            continuation_key=key,
        )
        try:
            page = client.fetch_minute_page(query)
            if page.query != query:
                raise KisPaperMarketDataError("minute_response_invalid")
            facts = _page_facts(page)
            category = (
                "invalid"
                if facts.has_duplicate_timestamps
                else "newer_than_key"
                if facts.newest.strftime("%Y%m%d%H%M%S") > key
                else "requested_date_observed"
                if facts.newest.strftime("%Y%m%d") == key[:8]
                else "earlier_only"
            )
            pages.append(
                KisPaperMinuteFixedKeyPageFacts(
                    requested_key=key,
                    category=category,
                    row_count=facts.row_count,
                    unique_timestamp_count=len(set(facts.timestamps)),
                    oldest_exchange_key=facts.oldest.strftime("%Y%m%d%H%M%S"),
                    newest_exchange_key=facts.newest.strftime("%Y%m%d%H%M%S"),
                )
            )
        except KisPaperMarketDataError as error:
            reason = str(error)
            category = (
                "empty"
                if reason == "minute_response_empty"
                else "invalid"
                if reason
                in {
                    "minute_response_invalid",
                    "minute_exchange_timestamp_invalid",
                    "minute_ohlc_invalid",
                    "minute_open_invalid",
                    "minute_high_invalid",
                    "minute_low_invalid",
                    "minute_last_invalid",
                    "minute_volume_invalid",
                }
                else "rejected"
            )
            pages.append(KisPaperMinuteFixedKeyPageFacts(key, category))
            # Only parsed market-page failures may continue with the already valid token.
            if category == "rejected" and reason != "minute_response_rejected":
                break
    return KisPaperMinuteFixedKeyProbeOutcome(captured_at, tuple(pages), client.call_counts)


def probe_and_write_kis_paper_minute_fixed_key_capability(
    *,
    client: KisPaperMinuteCapabilityProbeClient,
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime,
) -> KisPaperMinuteCapabilityProbeResult:
    outcome = run_kis_paper_minute_fixed_key_probe(client=client, observed_at=observed_at)
    path = write_kis_paper_minute_capability_probe_evidence(
        outcome,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    return KisPaperMinuteCapabilityProbeResult(
        outcome,
        path,
        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    )


@dataclass(frozen=True)
class _PageFacts:
    newest: datetime
    oldest: datetime
    timestamps: tuple[datetime, ...]
    has_duplicate_timestamps: bool
    continuation_available: bool
    row_count: int


def run_kis_paper_minute_capability_probe(
    *,
    client: KisPaperMinuteCapabilityProbeClient,
    request_start_times: Sequence[datetime],
    observed_at: datetime | None = None,
    max_pages: int = KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES,
    repeat_terminal_head_once: bool = True,
    explicit_older_key_once: bool = False,
    include_previous_day: bool = False,
    target: tuple[str, str] = KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET,
    tested_request_interval_seconds: float = KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    monotonic_clock: Callable[[], float],
) -> KisPaperMinuteCapabilityProbeOutcome:
    """Read bounded allowlisted pages and discard their raw contents.

    Opt-in QQQ/NAS uses at most two GETs: a current head (PINC=0), then only
    after a full head without recognized M/F, an explicit NEXT=1/PINC=1 request
    at oldest exchange timestamp minus one minute. This is not a collector.
    """

    if type(max_pages) is not int or not (
        1 <= max_pages <= KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES
    ):
        raise ValueError("capability probe page cap is invalid")
    if type(repeat_terminal_head_once) is not bool:
        raise TypeError("capability probe terminal head repeat must be a boolean")
    if type(include_previous_day) is not bool:
        raise TypeError("capability probe previous-day inclusion must be a boolean")
    if type(explicit_older_key_once) is not bool:
        raise TypeError("capability probe explicit older-key mode must be a boolean")
    if not _is_supported_tested_interval(tested_request_interval_seconds):
        raise ValueError("capability probe tested request interval is invalid")
    symbol, exchange = _normalize_probe_target(target)
    target_key = f"{symbol}/{exchange}/1m"
    if explicit_older_key_once:
        if target_key != "QQQ/NAS/1m" or include_previous_day or max_pages < 2:
            raise ValueError("explicit older-key probe requires QQQ/NAS current head and two pages")
        max_pages = 2
    if target_key in KIS_PAPER_MINUTE_CAPABILITY_PROBE_CANDIDATE_TARGET_KEYS and (
        max_pages != 1 or include_previous_day
    ):
        raise ValueError("candidate capability target requires one current-day page")
    captured_at = require_utc(observed_at or datetime.now(UTC), "observed_at")
    started = monotonic_clock()
    pages: list[_PageFacts] = []
    page_progress_categories: list[_PageProgressCategory] = []
    cursor_key: str | None = None
    failure: str | None = None
    cursor_stalled = False
    duplicate_or_not_older = False
    continuation_attempted = False
    terminal_head_repeat_count = 0
    header_signals: list[KisPaperMinuteContinuationSignal] = []
    body_signals: list[_BodyMoreCategory] = []
    explicit_attempted = False
    explicit_category: _ExplicitOlderKeyCategory = (
        "head_unavailable" if explicit_older_key_once else "not_requested"
    )
    new_older_key_count = 0
    overlap_key_count = 0

    try:
        for _page_number in range(max_pages):
            query = KisPaperMinuteQuery(
                exchange=exchange,
                symbol=symbol,
                include_previous_day=include_previous_day or explicit_attempted,
                continuation_next="1" if cursor_key is not None else None,
                continuation_key=cursor_key,
            )
            continuation_attempted = continuation_attempted or cursor_key is not None
            page = client.fetch_minute_page(query)
            facts = _page_facts(page)
            progress_category = (
                "terminal_head_repeat"
                if cursor_key is None and terminal_head_repeat_count
                else _page_progress_category(
                    prior=pages[-1] if pages else None,
                    candidate=facts,
                )
            )
            pages.append(facts)
            page_progress_categories.append(progress_category)
            if explicit_older_key_once:
                header_signals.append(page.continuation_signal)
                body_signals.append(_body_more_category(page.more))
                if explicit_attempted:
                    keys = set(facts.timestamps)
                    overlap_key_count = len(keys.intersection(pages[0].timestamps))
                    new_older_key_count = sum(stamp < pages[0].oldest for stamp in keys)
                    explicit_category = (
                        "duplicate_keys"
                        if facts.has_duplicate_timestamps
                        else "no_older_keys"
                        if not new_older_key_count
                        else "overlap_with_older_keys"
                        if overlap_key_count
                        else "older_keys_observed"
                    )
                    break
                if facts.has_duplicate_timestamps:
                    explicit_category = "duplicate_keys"
                    duplicate_or_not_older = True
                    break
                if facts.continuation_available or page.continuation_signal not in {
                    "blank_or_absent",
                    "unrecognized_nonblank",
                }:
                    explicit_category = "header_continuation_present"
                    break
                if facts.row_count != KIS_PAPER_MINUTE_MAX_ROWS:
                    explicit_category = "head_not_full"
                    break
                cursor_key = _cursor_key_for_next_page(page)
                explicit_attempted = True
                explicit_category = "page2_rejected"
                continue
            if progress_category in {"duplicate_within_page", "overlap_or_not_older"}:
                duplicate_or_not_older = True
                break
            if not facts.continuation_available:
                if (
                    cursor_key is None
                    and repeat_terminal_head_once
                    and terminal_head_repeat_count == 0
                    and len(pages) < max_pages
                ):
                    terminal_head_repeat_count += 1
                    continue
                break
            next_cursor_key = _cursor_key_for_next_page(page)
            if next_cursor_key == cursor_key:
                cursor_stalled = True
                break
            cursor_key = next_cursor_key
    except KisPaperMarketDataError as error:
        failure = _safe_failure_reason(error)

    elapsed_seconds = max(0.0, monotonic_clock() - started)
    call_counts = client.call_counts
    accepted_pages = len(pages)
    if failure is None:
        status: Literal["complete", "partial", "unavailable"] = "complete"
        response_class = "accepted"
    elif accepted_pages:
        status = "partial"
        response_class = failure
    else:
        status = "unavailable"
        response_class = failure
    continuation_category = _continuation_category(
        pages=pages,
        max_pages=max_pages,
        failure=failure,
        continuation_attempted=continuation_attempted,
        cursor_stalled=cursor_stalled,
        duplicate_or_not_older=duplicate_or_not_older
        or (
            explicit_older_key_once
            and len(pages) == 2
            and page_progress_categories[-1] in {"duplicate_within_page", "overlap_or_not_older"}
        ),
    )
    cursor_progress_category = _cursor_progress_category(page_progress_categories)
    probe_pattern_category = _probe_pattern_category(
        accepted_page_count=accepted_pages,
        continuation_attempted=continuation_attempted,
        terminal_head_repeat_count=terminal_head_repeat_count,
    )
    token_reuse_category = _token_reuse_category(
        call_counts=call_counts,
        accepted_page_count=accepted_pages,
    )
    request_start_category = _request_start_category(
        request_start_times=request_start_times,
        call_counts=call_counts,
    )
    tested_interval_observed = _request_starts_meet_tested_interval(
        request_start_times=request_start_times,
        call_counts=call_counts,
        tested_request_interval_seconds=float(tested_request_interval_seconds),
    )

    return KisPaperMinuteCapabilityProbeOutcome(
        status=status,
        observed_at=captured_at,
        accepted_page_count=accepted_pages,
        accepted_page_size_category=_page_size_category(pages),
        continuation_category=continuation_category,
        page_progress_categories=tuple(page_progress_categories),
        cursor_progress_category=cursor_progress_category,
        probe_pattern_category=probe_pattern_category,
        historical_range_category=_historical_range_category(pages),
        minute_spacing_category=_minute_spacing_category(pages),
        response_class=response_class,
        token_reuse_category=token_reuse_category,
        request_start_category=request_start_category,
        tested_request_interval_seconds=float(tested_request_interval_seconds),
        token_request_count=call_counts.token_attempts,
        minute_page_request_count=call_counts.minute_page_attempts,
        daily_page_request_count=call_counts.daily_page_attempts,
        request_attempt_count=(
            call_counts.token_attempts
            + call_counts.minute_page_attempts
            + call_counts.daily_page_attempts
        ),
        categorical_limit_or_error_count=int(failure is not None),
        elapsed_time_category=_elapsed_time_category(elapsed_seconds),
        calibration_fact="single_client_explicit_older_key_measurement_only"
        if explicit_older_key_once
        else _calibration_fact(
            status=status,
            accepted_page_count=accepted_pages,
            probe_pattern_category=probe_pattern_category,
            token_reuse_category=token_reuse_category,
            cursor_progress_category=cursor_progress_category,
        ),
        pacing_recalibration_fact=_pacing_recalibration_fact(
            status=status,
            response_class=response_class,
            accepted_page_count=accepted_pages,
            request_start_category=request_start_category,
            tested_request_interval_seconds=float(tested_request_interval_seconds),
            tested_interval_observed=tested_interval_observed,
        ),
        include_previous_day=include_previous_day,
        target_key=f"{symbol}/{exchange}/1m",
        explicit_older_key_once=explicit_older_key_once,
        continuation_signal_categories=tuple(header_signals),
        body_more_categories=tuple(body_signals),
        explicit_older_key_category=explicit_category,
        new_older_key_count=new_older_key_count,
        overlap_key_count=overlap_key_count,
    )


def write_kis_paper_minute_capability_probe_evidence(
    outcome: KisPaperMinuteCapabilityProbeOutcome | KisPaperMinuteFixedKeyProbeOutcome,
    *,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Atomically retain only the source-safe probe summary outside Git."""

    root = Path(artifact_root).resolve()
    repository = Path(repository_root).resolve()
    if root.is_relative_to(repository):
        raise ValueError("capability probe artifact root must stay outside Git")
    payload = json.dumps(outcome.safe_payload(), ensure_ascii=True, sort_keys=True) + "\n"
    encoded = payload.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    prefix = "fixed-key-pair-" if isinstance(outcome, KisPaperMinuteFixedKeyProbeOutcome) else ""
    destination = (
        root
        / KIS_PAPER_MINUTE_CAPABILITY_PROBE_ARTIFACT_DIRECTORY
        / f"{prefix}{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
    )
    _validate_artifact_destination(destination=destination, artifact_root=root)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("capability probe evidence conflicts")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    _validate_artifact_destination(destination=destination, artifact_root=root)
    staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def probe_and_write_kis_paper_minute_capability(
    *,
    client: KisPaperMinuteCapabilityProbeClient,
    request_start_times: Sequence[datetime],
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime | None = None,
    max_pages: int = KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES,
    repeat_terminal_head_once: bool = True,
    explicit_older_key_once: bool = False,
    include_previous_day: bool = False,
    target: tuple[str, str] = KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET,
    tested_request_interval_seconds: float = KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    monotonic_clock: Callable[[], float],
) -> KisPaperMinuteCapabilityProbeResult:
    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=observed_at,
        max_pages=max_pages,
        repeat_terminal_head_once=repeat_terminal_head_once,
        explicit_older_key_once=explicit_older_key_once,
        include_previous_day=include_previous_day,
        target=target,
        tested_request_interval_seconds=tested_request_interval_seconds,
        monotonic_clock=monotonic_clock,
    )
    return KisPaperMinuteCapabilityProbeResult(
        outcome=outcome,
        evidence_path=write_kis_paper_minute_capability_probe_evidence(
            outcome,
            artifact_root=artifact_root,
            repository_root=repository_root,
        ),
    )


def _page_facts(page: KisPaperMinutePage) -> _PageFacts:
    timestamps = tuple(
        sorted(_exchange_timestamp(row.exchange_date, row.exchange_time) for row in page.bars)
    )
    return _PageFacts(
        newest=timestamps[-1],
        oldest=timestamps[0],
        timestamps=timestamps,
        has_duplicate_timestamps=len(timestamps) != len(set(timestamps)),
        continuation_available=page.next_cursor is not None,
        row_count=len(page.bars),
    )


def _body_more_category(more: str) -> _BodyMoreCategory:
    if not more.strip():
        return "blank_or_absent"
    if more.strip() == "0":
        return "zero"
    return "one" if more.strip() == "1" else "other_nonblank"


def _normalize_probe_target(target: object) -> tuple[str, str]:
    if not isinstance(target, tuple) or len(target) != 2:
        raise ValueError("capability probe target is invalid")
    try:
        query = KisPaperMinuteQuery(exchange=str(target[1]), symbol=str(target[0]))
    except ValueError as error:
        raise ValueError("capability probe target is invalid") from error
    target_key = f"{query.symbol}/{query.exchange}/1m"
    if target_key not in KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET_KEYS:
        raise ValueError("capability probe target is invalid")
    return query.symbol, query.exchange


def _cursor_key_for_next_page(page: KisPaperMinutePage) -> str:
    oldest = min(page.bars, key=lambda row: (row.exchange_date, row.exchange_time))
    return (
        _exchange_timestamp(oldest.exchange_date, oldest.exchange_time) - timedelta(minutes=1)
    ).strftime("%Y%m%d%H%M%S")


def _exchange_timestamp(exchange_date: str, exchange_time: str) -> datetime:
    try:
        return datetime.strptime(f"{exchange_date}{exchange_time}", "%Y%m%d%H%M%S").replace(
            tzinfo=UTC
        )
    except ValueError as error:
        raise KisPaperMarketDataError("minute_exchange_timestamp_invalid") from error


def _page_size_category(pages: Sequence[_PageFacts]) -> Literal["none", "all_full", "some_partial"]:
    if not pages:
        return "none"
    if all(page.row_count == KIS_PAPER_MINUTE_MAX_ROWS for page in pages):
        return "all_full"
    return "some_partial"


def _continuation_category(
    *,
    pages: Sequence[_PageFacts],
    max_pages: int,
    failure: str | None,
    continuation_attempted: bool,
    cursor_stalled: bool,
    duplicate_or_not_older: bool,
) -> Literal[
    "not_observed",
    "terminal",
    "continued",
    "available_at_probe_cap",
    "continuation_failed",
    "cursor_stalled",
    "duplicate_conflict",
]:
    if duplicate_or_not_older:
        return "duplicate_conflict"
    if cursor_stalled:
        return "cursor_stalled"
    if not pages:
        return "not_observed"
    if failure is not None:
        return "continuation_failed" if continuation_attempted else "not_observed"
    if not pages[-1].continuation_available:
        return "terminal"
    if len(pages) >= max_pages:
        return "available_at_probe_cap"
    return "continued"


def _page_progress_category(
    *,
    prior: _PageFacts | None,
    candidate: _PageFacts,
) -> _PageProgressCategory:
    if prior is None:
        return "duplicate_within_page" if candidate.has_duplicate_timestamps else "initial"
    if candidate.has_duplicate_timestamps:
        return "duplicate_within_page"
    return (
        "strictly_older_nonoverlapping"
        if candidate.newest < prior.oldest
        else "overlap_or_not_older"
    )


def _cursor_progress_category(
    page_progress_categories: Sequence[_PageProgressCategory],
) -> _CursorProgressCategory:
    if not page_progress_categories:
        return "not_observed"
    if "duplicate_within_page" in page_progress_categories:
        return "duplicate_or_not_older"
    if len(page_progress_categories) == 1:
        return "single_page"
    if tuple(page_progress_categories) == ("initial", "terminal_head_repeat"):
        return "terminal_head_repeat"
    if all(
        category == "strictly_older_nonoverlapping" for category in page_progress_categories[1:]
    ):
        return "strictly_backward_nonoverlapping"
    return "duplicate_or_not_older"


def _historical_range_category(
    pages: Sequence[_PageFacts],
) -> Literal["not_observed", "single_exchange_date", "multiple_exchange_dates"]:
    days = {stamp.date() for page in pages for stamp in page.timestamps}
    if not days:
        return "not_observed"
    return "single_exchange_date" if len(days) == 1 else "multiple_exchange_dates"


def _probe_pattern_category(
    *,
    accepted_page_count: int,
    continuation_attempted: bool,
    terminal_head_repeat_count: int,
) -> Literal["single_terminal_page", "terminal_head_repeat", "cursor_chain"]:
    if terminal_head_repeat_count:
        return "terminal_head_repeat"
    if continuation_attempted:
        return "cursor_chain"
    if accepted_page_count:
        return "single_terminal_page"
    return "single_terminal_page"


def _minute_spacing_category(
    pages: Sequence[_PageFacts],
) -> Literal[
    "not_observed",
    "single_minute",
    "contiguous_after_deduplication",
    "gap_observed",
]:
    stamps = sorted({stamp for page in pages for stamp in page.timestamps})
    if not stamps:
        return "not_observed"
    if len(stamps) == 1:
        return "single_minute"
    if all(
        current - prior == timedelta(minutes=1)
        for prior, current in zip(stamps, stamps[1:], strict=False)
    ):
        return "contiguous_after_deduplication"
    return "gap_observed"


def _token_reuse_category(
    *,
    call_counts: KisPaperMarketDataCallCounts,
    accepted_page_count: int,
) -> Literal[
    "not_observed",
    "single_token_single_page",
    "single_token_reused",
    "multiple_token_attempts",
]:
    if not accepted_page_count:
        return "not_observed"
    if call_counts.token_attempts == 1:
        return "single_token_single_page" if accepted_page_count == 1 else "single_token_reused"
    return "multiple_token_attempts"


def _is_positive_finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def _is_supported_tested_interval(value: object) -> bool:
    return _is_positive_finite(value) and (
        KIS_PAPER_MINUTE_CAPABILITY_PROBE_MIN_INTERVAL_SECONDS
        <= float(value)
        <= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    )


def _pacing_recalibration_fact(
    *,
    status: Literal["complete", "partial", "unavailable"],
    response_class: str,
    accepted_page_count: int,
    request_start_category: str,
    tested_request_interval_seconds: float,
    tested_interval_observed: bool | None,
) -> str:
    if response_class == "rate_limited":
        return "rate_limit_observed_at_tested_interval"
    if tested_interval_observed is False:
        return "request_starts_faster_than_tested_interval"
    if (
        status == "complete"
        and accepted_page_count >= 2
        and request_start_category == "faster_than_existing_gate"
        and tested_interval_observed is True
    ):
        return "multi_page_single_client_candidate_interval_accepted"
    if request_start_category == "timestamps_incomplete":
        return "request_start_timestamps_incomplete"
    if tested_request_interval_seconds >= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS:
        return "existing_gate_measurement_only"
    return "insufficient_accepted_pages_for_candidate_interval"


def _request_start_category(
    *,
    request_start_times: Sequence[datetime],
    call_counts: KisPaperMarketDataCallCounts,
) -> Literal[
    "not_observed",
    "single_get",
    "at_or_below_existing_gate",
    "faster_than_existing_gate",
    "timestamps_incomplete",
]:
    minute_starts = _minute_request_start_times(
        request_start_times=request_start_times,
        call_counts=call_counts,
    )
    if minute_starts == ():
        return "not_observed"
    if minute_starts is None:
        return "timestamps_incomplete"
    if len(minute_starts) == 1:
        return "single_get"
    minimum_gap = _minimum_request_start_gap(minute_starts)
    return (
        "at_or_below_existing_gate"
        if minimum_gap >= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
        else "faster_than_existing_gate"
    )


def _request_starts_meet_tested_interval(
    *,
    request_start_times: Sequence[datetime],
    call_counts: KisPaperMarketDataCallCounts,
    tested_request_interval_seconds: float,
) -> bool | None:
    minute_starts = _minute_request_start_times(
        request_start_times=request_start_times,
        call_counts=call_counts,
    )
    if minute_starts is None or len(minute_starts) < 2:
        return None
    return _minimum_request_start_gap(minute_starts) >= tested_request_interval_seconds


def _minute_request_start_times(
    *,
    request_start_times: Sequence[datetime],
    call_counts: KisPaperMarketDataCallCounts,
) -> tuple[datetime, ...] | None:
    minute_requests = call_counts.minute_page_attempts
    if minute_requests == 0:
        return ()
    expected = call_counts.token_attempts + minute_requests + call_counts.daily_page_attempts
    starts = tuple(require_utc(value, "request_start_time") for value in request_start_times)
    if len(starts) != expected:
        return None
    return starts[-minute_requests:]


def _minimum_request_start_gap(starts: Sequence[datetime]) -> float:
    return min(
        (current - prior).total_seconds()
        for prior, current in zip(starts, starts[1:], strict=False)
    )


def _elapsed_time_category(
    elapsed_seconds: float,
) -> Literal["under_5_seconds", "under_30_seconds", "30_seconds_or_more"]:
    if elapsed_seconds < 5:
        return "under_5_seconds"
    if elapsed_seconds < 30:
        return "under_30_seconds"
    return "30_seconds_or_more"


def _calibration_fact(
    *,
    status: Literal["complete", "partial", "unavailable"],
    accepted_page_count: int,
    probe_pattern_category: str,
    token_reuse_category: str,
    cursor_progress_category: _CursorProgressCategory,
) -> str:
    if cursor_progress_category == "duplicate_or_not_older":
        return "single_client_duplicate_or_non_backward_page"
    if (
        status == "complete"
        and accepted_page_count > 1
        and probe_pattern_category == "cursor_chain"
        and token_reuse_category == "single_token_reused"
        and cursor_progress_category == "strictly_backward_nonoverlapping"
    ):
        return "single_client_cursor_chain_under_existing_gate"
    if (
        status == "complete"
        and probe_pattern_category == "terminal_head_repeat"
        and token_reuse_category == "single_token_reused"
    ):
        return "single_client_terminal_head_reuse_under_existing_gate"
    if accepted_page_count:
        return "single_client_retry_unfinished_cursor_on_next_owned_slot"
    return "retain_existing_gate_and_retry_on_next_owned_slot"


def _safe_failure_reason(error: KisPaperMarketDataError) -> str:
    reason = str(error)
    return reason if reason in _SAFE_FAILURE_REASONS else "market_data_probe_error"


def _validate_artifact_destination(*, destination: Path, artifact_root: Path) -> None:
    if destination.is_symlink():
        raise ValueError("capability probe artifact destination is invalid")
    try:
        destination.resolve().relative_to(artifact_root)
    except ValueError as error:
        raise ValueError("capability probe artifact destination is invalid") from error

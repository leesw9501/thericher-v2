"""Bounded, source-safe KIS Paper 1m pagination capability probe.

The probe uses the existing paper-only market-data client, keeps returned bars
only long enough to classify pagination behavior, and persists no raw market
data. It is intentionally a measurement tool rather than a cache collector.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_MINUTE_MAX_ROWS,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
)

KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET = ("QQQ", "NAS")
KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES = 3
KIS_PAPER_MINUTE_CAPABILITY_PROBE_ARTIFACT_DIRECTORY = "data/kis-paper-minute-capability-probe"

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
    """Categorical evidence from one bounded QQQ/NAS minute probe."""

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
    ]
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
    elapsed_time_category: Literal[
        "under_5_seconds",
        "under_30_seconds",
        "30_seconds_or_more",
    ]
    calibration_fact: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.accepted_page_count < 0:
            raise ValueError("capability probe accepted page count is invalid")
        if self.status == "unavailable" and self.accepted_page_count:
            raise ValueError("unavailable capability probe cannot accept pages")
        if not self.response_class or not self.calibration_fact:
            raise ValueError("capability probe observation is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return metadata-only evidence that cannot contain provider rows."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_minute_capability_probe",
            "status": self.status,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": "QQQ/NAS/1m",
            "observed_at": self.observed_at.isoformat(),
            "accepted_page_count": self.accepted_page_count,
            "accepted_page_size_category": self.accepted_page_size_category,
            "continuation_category": self.continuation_category,
            "probe_pattern_category": self.probe_pattern_category,
            "historical_range_category": self.historical_range_category,
            "minute_spacing_category": self.minute_spacing_category,
            "response_class": self.response_class,
            "token_reuse_category": self.token_reuse_category,
            "request_start_category": self.request_start_category,
            "elapsed_time_category": self.elapsed_time_category,
            "provider_request_start_ceiling": "not_tested_above_existing_gate",
            "raw_market_data_retained": False,
            "calibration_fact": self.calibration_fact,
        }


@dataclass(frozen=True)
class KisPaperMinuteCapabilityProbeResult:
    outcome: KisPaperMinuteCapabilityProbeOutcome
    evidence_path: Path


@dataclass(frozen=True)
class _PageFacts:
    newest: datetime
    oldest: datetime
    timestamps: tuple[datetime, ...]
    continuation_available: bool
    row_count: int


def run_kis_paper_minute_capability_probe(
    *,
    client: KisPaperMinuteCapabilityProbeClient,
    request_start_times: Sequence[datetime],
    observed_at: datetime | None = None,
    max_pages: int = KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES,
    repeat_terminal_head_once: bool = True,
    monotonic_clock: Callable[[], float],
) -> KisPaperMinuteCapabilityProbeOutcome:
    """Read at most three QQQ minute pages and discard their raw contents."""

    if type(max_pages) is not int or not (
        1 <= max_pages <= KIS_PAPER_MINUTE_CAPABILITY_PROBE_MAX_PAGES
    ):
        raise ValueError("capability probe page cap is invalid")
    if type(repeat_terminal_head_once) is not bool:
        raise TypeError("capability probe terminal head repeat must be a boolean")
    captured_at = require_utc(observed_at or datetime.now(UTC), "observed_at")
    started = monotonic_clock()
    pages: list[_PageFacts] = []
    cursor_key: str | None = None
    failure: str | None = None
    cursor_stalled = False
    continuation_attempted = False
    terminal_head_repeat_count = 0

    try:
        for _page_number in range(max_pages):
            query = KisPaperMinuteQuery(
                exchange=KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET[1],
                symbol=KIS_PAPER_MINUTE_CAPABILITY_PROBE_TARGET[0],
                continuation_next="1" if cursor_key is not None else None,
                continuation_key=cursor_key,
            )
            continuation_attempted = continuation_attempted or cursor_key is not None
            page = client.fetch_minute_page(query)
            facts = _page_facts(page)
            pages.append(facts)
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
    )
    probe_pattern_category = _probe_pattern_category(
        accepted_page_count=accepted_pages,
        continuation_attempted=continuation_attempted,
        terminal_head_repeat_count=terminal_head_repeat_count,
    )
    token_reuse_category = _token_reuse_category(
        call_counts=call_counts,
        accepted_page_count=accepted_pages,
    )

    return KisPaperMinuteCapabilityProbeOutcome(
        status=status,
        observed_at=captured_at,
        accepted_page_count=accepted_pages,
        accepted_page_size_category=_page_size_category(pages),
        continuation_category=continuation_category,
        probe_pattern_category=probe_pattern_category,
        historical_range_category=_historical_range_category(pages),
        minute_spacing_category=_minute_spacing_category(pages),
        response_class=response_class,
        token_reuse_category=token_reuse_category,
        request_start_category=_request_start_category(
            request_start_times=request_start_times,
            call_counts=call_counts,
        ),
        elapsed_time_category=_elapsed_time_category(elapsed_seconds),
        calibration_fact=_calibration_fact(
            status=status,
            accepted_page_count=accepted_pages,
            probe_pattern_category=probe_pattern_category,
            token_reuse_category=token_reuse_category,
        ),
    )


def write_kis_paper_minute_capability_probe_evidence(
    outcome: KisPaperMinuteCapabilityProbeOutcome,
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
    destination = (
        root
        / KIS_PAPER_MINUTE_CAPABILITY_PROBE_ARTIFACT_DIRECTORY
        / f"{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
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
    monotonic_clock: Callable[[], float],
) -> KisPaperMinuteCapabilityProbeResult:
    outcome = run_kis_paper_minute_capability_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=observed_at,
        max_pages=max_pages,
        repeat_terminal_head_once=repeat_terminal_head_once,
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
        continuation_available=page.next_cursor is not None,
        row_count=len(page.bars),
    )


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
) -> Literal[
    "not_observed",
    "terminal",
    "continued",
    "available_at_probe_cap",
    "continuation_failed",
    "cursor_stalled",
]:
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
    minute_requests = call_counts.minute_page_attempts
    if minute_requests == 0:
        return "not_observed"
    expected = call_counts.token_attempts + minute_requests + call_counts.daily_page_attempts
    starts = tuple(require_utc(value, "request_start_time") for value in request_start_times)
    if len(starts) != expected:
        return "timestamps_incomplete"
    minute_starts = starts[-minute_requests:]
    if len(minute_starts) == 1:
        return "single_get"
    minimum_gap = min(
        (current - prior).total_seconds()
        for prior, current in zip(minute_starts, minute_starts[1:], strict=False)
    )
    return (
        "at_or_below_existing_gate"
        if minimum_gap >= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
        else "faster_than_existing_gate"
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
) -> str:
    if (
        status == "complete"
        and accepted_page_count > 1
        and probe_pattern_category == "cursor_chain"
        and token_reuse_category == "single_token_reused"
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

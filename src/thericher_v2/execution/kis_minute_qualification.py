"""Bounded, sanitized qualification evidence for KIS paper raw 1-minute pages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_market_data import (
    KisPaperMinuteCallCounts,
    KisPaperMinuteClient,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)

KIS_PAPER_MINUTE_QUALIFICATION_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/execution/kis-paper-raw-minute-qualification"
)
KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT = Path("D:/thericher-v2/model-artifacts/_control")
KIS_PAPER_MINUTE_QUALIFICATION_VERSION = "kis-paper-raw-minute-qualification-v4"
KIS_PAPER_MINUTE_QUALIFICATION_OBJECTIVE_ID = "kis-paper-raw-minute-qualification-v4"
KIS_PAPER_MINUTE_QUALIFICATION_SESSION_DATE = date(2026, 7, 20)
KIS_PAPER_MINUTE_QUALIFICATION_SESSION_REFERENCE = (
    "https://www.nasdaqtrader.com/Trader.aspx?id=calendar"
)
KIS_PAPER_MINUTE_MAX_AGE = timedelta(minutes=2)
KIS_PAPER_MINUTE_MAX_PROBE_DURATION = timedelta(minutes=2)
KIS_PAPER_MINUTE_BASELINE_BARS = 90
_NEW_YORK = ZoneInfo("America/New_York")
_SEOUL = ZoneInfo("Asia/Seoul")
_REGULAR_SESSION_OPEN = time(9, 30)
_REGULAR_SESSION_CLOSE = time(16, 0)
_FIRST_SAFE_PROBE_TIME = time(13, 30)
_LAST_SAFE_PROBE_TIME = time(15, 40)
_SAFE_PROBE_SECONDS = range(10, 46)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "attempt_state_unresolved",
        "control_ledger_invalid",
        "control_ledger_write_failed",
        "config_missing",
        "continuation_contract_invalid",
        "kis_paper_minute_qualification_window_closed",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "paper_host_required",
        "qualification_attempt_already_reserved",
        "request_not_allowlisted",
        "redirect_rejected",
        "response_invalid",
        "reservation_marker_invalid",
        "reservation_state_write_failed",
        "summary_write_failed",
        "transport_failure",
        "window_recheck_closed",
    }
)


@dataclass(frozen=True)
class KisPaperMinuteQualificationFacts:
    """Predeclared runtime-consistency facts retained by the observed-only probe."""

    probe_window_valid: bool
    first_page_descends_one_minute: bool
    continuation_page_descends_one_minute: bool
    exchange_and_korea_map_to_same_utc: bool
    continuation_has_no_overlap: bool
    continuation_boundary_is_contiguous: bool
    conflicting_overlap_count: int
    current_minute_row_observed: bool
    current_minute_row_excluded: bool
    completed_bars_available: bool
    completed_window_fresh: bool
    baseline_boundary_aligned: bool
    schema_version: int = SCHEMA_VERSION

    @property
    def all_runtime_facts_passed(self) -> bool:
        return (
            self.probe_window_valid
            and self.first_page_descends_one_minute
            and self.continuation_page_descends_one_minute
            and self.exchange_and_korea_map_to_same_utc
            and self.continuation_has_no_overlap
            and self.continuation_boundary_is_contiguous
            and self.conflicting_overlap_count == 0
            and self.current_minute_row_observed
            and self.current_minute_row_excluded
            and self.completed_bars_available
            and self.completed_window_fresh
            and self.baseline_boundary_aligned
        )


@dataclass(frozen=True)
class KisPaperMinuteQualificationEvidence:
    """Metadata-only result from at most one token and two raw-minute reads."""

    observed_at_start: datetime
    observed_at_end: datetime
    exchange: str
    symbol: str
    call_counts: KisPaperMinuteCallCounts
    first_page_row_count: int
    continuation_page_row_count: int | None
    continuation_available: bool
    continuation_requested: bool
    first_exchange_newest: datetime
    first_exchange_oldest: datetime
    first_korea_newest: datetime
    first_korea_oldest: datetime
    continuation_exchange_newest: datetime | None
    continuation_exchange_oldest: datetime | None
    continuation_korea_newest: datetime | None
    continuation_korea_oldest: datetime | None
    exact_overlap_count: int
    excluded_current_or_future_row_count: int
    newest_completed_end: datetime | None
    facts: KisPaperMinuteQualificationFacts
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "observed_at_start",
            "observed_at_end",
            "first_exchange_newest",
            "first_exchange_oldest",
            "first_korea_newest",
            "first_korea_oldest",
        ):
            object.__setattr__(self, field_name, require_utc(getattr(self, field_name), field_name))
        if self.newest_completed_end is not None:
            object.__setattr__(
                self,
                "newest_completed_end",
                require_utc(self.newest_completed_end, "newest_completed_end"),
            )
        for field_name in (
            "continuation_exchange_newest",
            "continuation_exchange_oldest",
            "continuation_korea_newest",
            "continuation_korea_oldest",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_utc(value, field_name))
        if self.observed_at_end < self.observed_at_start:
            raise ValueError("qualification observation cannot end before it starts")
        if self.exchange != "NAS" or self.symbol != "QQQ":
            raise ValueError("qualification scope must be QQQ NAS")
        if self.call_counts.token_attempts != 1:
            raise ValueError("qualification must use exactly one paper token")
        if self.call_counts.minute_page_attempts not in {1, 2}:
            raise ValueError("qualification minute page count is not bounded")
        if self.first_page_row_count <= 0 or self.first_page_row_count > 120:
            raise ValueError("qualification needs a nonempty first page")
        if self.continuation_page_row_count is not None and not (
            0 < self.continuation_page_row_count <= 120
        ):
            raise ValueError("qualification continuation page must be nonempty")


@dataclass(frozen=True)
class KisPaperMinuteQualificationFailure:
    """Typed, sanitized failure input for the external one-shot summary writer."""

    observed_at: datetime
    call_counts: KisPaperMinuteCallCounts
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if not (0 <= self.call_counts.token_attempts <= 1):
            raise ValueError("qualification token count is not bounded")
        if not (0 <= self.call_counts.minute_page_attempts <= 2):
            raise ValueError("qualification minute page count is not bounded")
        object.__setattr__(
            self,
            "reason",
            sanitize_kis_paper_minute_failure_reason(self.reason),
        )


class _ContinuationRequestWindowClosed(Exception):
    """Stop a second page without discarding the completed first-page observation."""


def is_kis_paper_minute_qualification_window(value: datetime) -> bool:
    """Allow one regular-session observation only when two pages stay in-session."""

    observed_at = require_utc(value, "value").astimezone(_NEW_YORK)
    if (
        observed_at.date() != KIS_PAPER_MINUTE_QUALIFICATION_SESSION_DATE
        or observed_at.weekday() >= 5
        or observed_at.second not in _SAFE_PROBE_SECONDS
    ):
        return False
    local_time = observed_at.timetz().replace(second=0, microsecond=0, tzinfo=None)
    return (
        _FIRST_SAFE_PROBE_TIME <= local_time <= _LAST_SAFE_PROBE_TIME
        and observed_at.minute % 10 == 0
    )


def run_bounded_kis_paper_minute_qualification(
    client: KisPaperMinuteClient,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    observed_at_start: datetime | None = None,
) -> KisPaperMinuteQualificationEvidence:
    """Use one client, one token, one first page, and at most one continuation."""

    observation_started_at = require_utc(
        observed_at_start if observed_at_start is not None else clock(), "observed_at_start"
    )
    if not is_kis_paper_minute_qualification_window(observation_started_at):
        raise ValueError("kis_paper_minute_qualification_window_closed")

    # A suspended process must not use a once-valid timestamp to obtain a token.
    before_token = require_utc(clock(), "before_token")
    if (
        not is_kis_paper_minute_qualification_window(before_token)
        or not _qualification_observation_is_valid(observation_started_at, before_token)
    ):
        raise ValueError("window_recheck_closed")
    client.ensure_authenticated()

    first_page_started_at: datetime | None = None

    def require_first_page_window() -> None:
        nonlocal first_page_started_at
        value = require_utc(clock(), "before_first_page")
        if (
            not is_kis_paper_minute_qualification_window(value)
            or not _qualification_observation_is_valid(observation_started_at, value)
        ):
            raise ValueError("window_recheck_closed")
        first_page_started_at = value

    first_page = client.fetch_page(
        KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"),
        before_request=require_first_page_window,
    )
    if first_page_started_at is None:
        raise RuntimeError("first-page request gate was not called")
    continuation_page: KisPaperMinutePage | None = None
    observed_at_end: datetime
    if (
        first_page.next_cursor is not None
        and _page_descends_one_exchange_minute(first_page)
    ):
        before_continuation: datetime | None = None

        def require_continuation_window() -> None:
            nonlocal before_continuation
            value = require_utc(clock(), "before_continuation")
            before_continuation = value
            if not _qualification_observation_is_valid(observation_started_at, value):
                raise _ContinuationRequestWindowClosed

        last = first_page.bars[-1]
        try:
            continuation_page = client.fetch_page(
                KisPaperMinuteQuery(
                    exchange="NAS",
                    symbol="QQQ",
                    continuation_next=first_page.next_cursor,
                    continuation_key=_continuation_key_before(last),
                ),
                before_request=require_continuation_window,
            )
            observed_at_end = require_utc(clock(), "observed_at_end")
        except _ContinuationRequestWindowClosed:
            if before_continuation is None:
                raise RuntimeError("continuation request gate was not called") from None
            observed_at_end = before_continuation
    else:
        observed_at_end = require_utc(clock(), "observed_at_end")
    return assess_kis_paper_minute_qualification(
        first_page=first_page,
        continuation_page=continuation_page,
        observed_at_start=observation_started_at,
        observed_at_end=observed_at_end,
        call_counts=client.call_counts,
    )


def assess_kis_paper_minute_qualification(
    *,
    first_page: KisPaperMinutePage,
    continuation_page: KisPaperMinutePage | None,
    observed_at_start: datetime,
    observed_at_end: datetime,
    call_counts: KisPaperMinuteCallCounts,
) -> KisPaperMinuteQualificationEvidence:
    """Assess raw rows in memory and return only non-price qualification evidence."""

    start = require_utc(observed_at_start, "observed_at_start")
    end = require_utc(observed_at_end, "observed_at_end")
    if end < start:
        raise ValueError("qualification observation cannot end before it starts")
    if first_page.query.exchange != "NAS" or first_page.query.symbol != "QQQ":
        raise ValueError("qualification scope must be QQQ NAS")
    if continuation_page is not None and (
        continuation_page.query.exchange != "NAS" or continuation_page.query.symbol != "QQQ"
    ):
        raise ValueError("qualification continuation scope must be QQQ NAS")
    if continuation_page is not None and (
        first_page.next_cursor is None
        or continuation_page.query.continuation_next != first_page.next_cursor
        or continuation_page.query.continuation_key
        != _continuation_key_before(first_page.bars[-1])
    ):
        raise ValueError("continuation_contract_invalid")

    first_exchange = tuple(_exchange_utc(row) for row in first_page.bars)
    first_korea = tuple(_korea_utc(row) for row in first_page.bars)
    continuation_exchange = (
        tuple(_exchange_utc(row) for row in continuation_page.bars)
        if continuation_page is not None
        else ()
    )
    continuation_korea = (
        tuple(_korea_utc(row) for row in continuation_page.bars)
        if continuation_page is not None
        else ()
    )
    all_exchange = first_exchange + continuation_exchange
    all_korea = first_korea + continuation_korea
    overlap_count, conflicting_overlap_count = _overlap_facts(
        first_page,
        continuation_page,
    )
    exchange_minute = _minute_floor(end.astimezone(_NEW_YORK)).astimezone(UTC)
    current_rows = tuple(timestamp for timestamp in first_exchange if timestamp >= exchange_minute)
    completed = tuple(timestamp for timestamp in first_exchange if timestamp < exchange_minute)
    newest_completed_end = max(completed) + timedelta(minutes=1) if completed else None
    completed_age = end - newest_completed_end if newest_completed_end is not None else None
    current_minute_observed = (
        _minute_floor(start.astimezone(_NEW_YORK)).astimezone(UTC) == exchange_minute
        and max(first_exchange) == exchange_minute
    )
    facts = KisPaperMinuteQualificationFacts(
        probe_window_valid=_qualification_observation_is_valid(start, end),
        first_page_descends_one_minute=_page_descends_one_exchange_minute(first_page),
        continuation_page_descends_one_minute=(
            continuation_page is not None
            and _page_descends_one_exchange_minute(continuation_page)
        ),
        exchange_and_korea_map_to_same_utc=all(
            exchange_timestamp == korea_timestamp
            for exchange_timestamp, korea_timestamp in zip(all_exchange, all_korea, strict=True)
        ),
        continuation_has_no_overlap=(
            continuation_page is not None
            and overlap_count == 0
            and conflicting_overlap_count == 0
        ),
        continuation_boundary_is_contiguous=(
            continuation_page is not None
            and max(continuation_exchange) + timedelta(minutes=1) == min(first_exchange)
        ),
        conflicting_overlap_count=conflicting_overlap_count,
        current_minute_row_observed=current_minute_observed,
        current_minute_row_excluded=current_minute_observed and len(current_rows) == 1,
        completed_bars_available=len(completed) >= KIS_PAPER_MINUTE_BASELINE_BARS,
        completed_window_fresh=(
            completed_age is not None and timedelta(0) <= completed_age <= KIS_PAPER_MINUTE_MAX_AGE
        ),
        baseline_boundary_aligned=(
            newest_completed_end is not None
            and newest_completed_end.minute % 10 == 0
            and newest_completed_end.second == 0
            and newest_completed_end.microsecond == 0
        ),
    )
    return KisPaperMinuteQualificationEvidence(
        observed_at_start=start,
        observed_at_end=end,
        exchange=first_page.query.exchange,
        symbol=first_page.query.symbol,
        call_counts=call_counts,
        first_page_row_count=len(first_page.bars),
        continuation_page_row_count=len(continuation_page.bars) if continuation_page else None,
        continuation_available=first_page.next_cursor is not None,
        continuation_requested=continuation_page is not None,
        first_exchange_newest=max(first_exchange),
        first_exchange_oldest=min(first_exchange),
        first_korea_newest=max(first_korea),
        first_korea_oldest=min(first_korea),
        continuation_exchange_newest=max(continuation_exchange) if continuation_exchange else None,
        continuation_exchange_oldest=min(continuation_exchange) if continuation_exchange else None,
        continuation_korea_newest=max(continuation_korea) if continuation_korea else None,
        continuation_korea_oldest=min(continuation_korea) if continuation_korea else None,
        exact_overlap_count=overlap_count,
        excluded_current_or_future_row_count=len(current_rows),
        newest_completed_end=newest_completed_end,
        facts=facts,
    )


def sanitized_kis_paper_minute_qualification_summary(
    evidence: KisPaperMinuteQualificationEvidence,
) -> dict[str, object]:
    """Return an external artifact document without raw values, rows, or credentials."""

    _require_sanitizable_qualification_evidence(evidence)
    facts = evidence.facts
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_raw_minute_qualification",
        "probe_version": KIS_PAPER_MINUTE_QUALIFICATION_VERSION,
        "status": "observed",
        "promotion": "not_available_from_one_shot_probe",
        "scope": {
            "exchange": evidence.exchange,
            "symbol": evidence.symbol,
            "timeframe": "1m",
            "network_scope": "paper token plus one first page and at most one continuation",
            "order_or_account_endpoint_called": False,
        },
        "session_gate": {
            "exchange": "NASDAQ",
            "local_date": KIS_PAPER_MINUTE_QUALIFICATION_SESSION_DATE.isoformat(),
            "calendar_reference": KIS_PAPER_MINUTE_QUALIFICATION_SESSION_REFERENCE,
            "mode": "fixed_verified_full_session_date",
        },
        "observation": {
            "started_at_utc": _format_utc(evidence.observed_at_start),
            "ended_at_utc": _format_utc(evidence.observed_at_end),
            "first_page_row_count": evidence.first_page_row_count,
            "continuation_page_row_count": evidence.continuation_page_row_count,
            "continuation_available": evidence.continuation_available,
            "continuation_requested": evidence.continuation_requested,
            "call_counts": {
                "token_attempts": evidence.call_counts.token_attempts,
                "minute_page_attempts": evidence.call_counts.minute_page_attempts,
            },
            "exchange_timestamp_bounds_utc": {
                "newest": _format_utc(evidence.first_exchange_newest),
                "oldest": _format_utc(evidence.first_exchange_oldest),
            },
            "korea_timestamp_bounds_utc": {
                "newest": _format_utc(evidence.first_korea_newest),
                "oldest": _format_utc(evidence.first_korea_oldest),
            },
            "continuation_exchange_timestamp_bounds_utc": _optional_timestamp_bounds(
                evidence.continuation_exchange_newest,
                evidence.continuation_exchange_oldest,
            ),
            "continuation_korea_timestamp_bounds_utc": _optional_timestamp_bounds(
                evidence.continuation_korea_newest,
                evidence.continuation_korea_oldest,
            ),
            "exact_overlap_count": evidence.exact_overlap_count,
            "excluded_current_or_future_row_count": evidence.excluded_current_or_future_row_count,
            "newest_completed_end_utc": (
                _format_utc(evidence.newest_completed_end)
                if evidence.newest_completed_end is not None
                else None
            ),
        },
        "predeclared_facts": {
            "probe_window_valid": facts.probe_window_valid,
            "first_page_descends_one_minute": facts.first_page_descends_one_minute,
            "continuation_page_descends_one_minute": facts.continuation_page_descends_one_minute,
            "exchange_and_korea_map_to_same_utc": facts.exchange_and_korea_map_to_same_utc,
            "continuation_has_no_overlap": facts.continuation_has_no_overlap,
            "continuation_boundary_is_contiguous": facts.continuation_boundary_is_contiguous,
            "conflicting_overlap_count": facts.conflicting_overlap_count,
            "current_minute_row_observed": facts.current_minute_row_observed,
            "current_minute_row_excluded": facts.current_minute_row_excluded,
            "completed_bars_available": facts.completed_bars_available,
            "completed_window_fresh": facts.completed_window_fresh,
            "baseline_boundary_aligned": facts.baseline_boundary_aligned,
            "all_runtime_facts_passed": facts.all_runtime_facts_passed,
        },
        "storage": {
            "raw_market_data_retained": False,
            "in_memory_only": True,
            "persistent_cache_allowed": False,
        },
        "limitations": [
            "No raw prices, volume, rows, token, account identifier, or response body is retained.",
            "One raw-minute probe remains observed evidence and cannot qualify or promote a "
            "capability.",
        ],
    }


def sanitized_kis_paper_minute_failure_summary(
    *,
    observed_at: datetime,
    call_counts: KisPaperMinuteCallCounts,
    reason: str,
) -> dict[str, object]:
    """Record a bounded failure without retaining a response body or credentials."""

    if not (0 <= call_counts.token_attempts <= 1 and 0 <= call_counts.minute_page_attempts <= 2):
        raise ValueError("qualification call counts are not bounded")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_raw_minute_qualification",
        "probe_version": KIS_PAPER_MINUTE_QUALIFICATION_VERSION,
        "status": "rejected",
        "reason": sanitize_kis_paper_minute_failure_reason(reason),
        "observed_at_utc": _format_utc(require_utc(observed_at, "observed_at")),
        "call_counts": {
            "token_attempts": call_counts.token_attempts,
            "minute_page_attempts": call_counts.minute_page_attempts,
        },
        "storage": {"raw_market_data_retained": False, "in_memory_only": True},
    }


def sanitize_kis_paper_minute_failure_reason(value: BaseException | str) -> str:
    """Keep arbitrary transport or parser text out of external evidence."""

    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_probe_error"


def _require_sanitizable_qualification_evidence(
    evidence: KisPaperMinuteQualificationEvidence,
) -> None:
    if evidence.exchange != "NAS" or evidence.symbol != "QQQ":
        raise ValueError("qualification scope must be QQQ NAS")
    if (
        evidence.call_counts.token_attempts != 1
        or evidence.call_counts.minute_page_attempts not in {1, 2}
    ):
        raise ValueError("qualification call counts are not bounded")
    if not (0 < evidence.first_page_row_count <= 120):
        raise ValueError("qualification first page is not bounded")
    if evidence.continuation_page_row_count is not None and not (
        0 < evidence.continuation_page_row_count <= 120
    ):
        raise ValueError("qualification continuation page is not bounded")


def write_kis_paper_minute_qualification_summary(
    *,
    result: KisPaperMinuteQualificationEvidence | KisPaperMinuteQualificationFailure,
    artifact_root: Path,
    run_id: str,
    repo_root: Path,
) -> tuple[Path, str]:
    """Atomically persist one internally sanitized artifact outside the repository."""

    if not run_id or any(character not in "0123456789TZ-" for character in run_id):
        raise ValueError("qualification run_id is invalid")
    if isinstance(result, KisPaperMinuteQualificationEvidence):
        document = sanitized_kis_paper_minute_qualification_summary(result)
    elif isinstance(result, KisPaperMinuteQualificationFailure):
        document = sanitized_kis_paper_minute_failure_summary(
            observed_at=result.observed_at,
            call_counts=result.call_counts,
            reason=result.reason,
        )
    else:
        raise TypeError("qualification summary requires typed evidence or failure")
    resolved_root = _external_artifact_root(artifact_root=artifact_root, repo_root=repo_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    target = resolved_root / run_id
    if target.exists() or target.is_symlink():
        raise FileExistsError("qualification artifact destination already exists")
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    staging = resolved_root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        _write_bytes_and_sync(staging / "summary.json", payload)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target / "summary.json", "sha256:" + hashlib.sha256(payload).hexdigest()


def kis_paper_minute_qualification_attempt_is_reserved(
    *,
    control_root: Path,
    repo_root: Path,
) -> bool:
    """Check the externally durable one-shot marker without opening credentials."""

    return external_one_shot_attempt_is_reserved(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=KIS_PAPER_MINUTE_QUALIFICATION_OBJECTIVE_ID,
    )


def external_one_shot_attempt_is_reserved(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
) -> bool:
    """Return whether an external one-shot has any durable reservation evidence."""

    marker = _external_attempt_marker(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
    )
    phases = _external_attempt_ledger_phases(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
    )
    return marker.exists() or marker.is_symlink() or bool(phases)


def reserve_kis_paper_minute_qualification_attempt(
    *,
    control_root: Path,
    repo_root: Path,
    observed_at: datetime,
) -> Path:
    """Atomically reserve this objective before its first possible token request."""

    return reserve_external_one_shot_attempt(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=KIS_PAPER_MINUTE_QUALIFICATION_OBJECTIVE_ID,
        observed_at=observed_at,
    )


def reserve_external_one_shot_attempt(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
    observed_at: datetime,
) -> Path:
    """Create an exclusive marker, then record one reservation before any token."""

    marker = _external_attempt_marker(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
    )
    if external_one_shot_attempt_is_reserved(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
    ):
        raise ValueError("qualification_attempt_already_reserved")
    reserved_at = require_utc(observed_at, "observed_at")
    payload = _attempt_marker_payload(
        objective_id=objective_id,
        phase="reserved",
        reserved_at=reserved_at,
        updated_at=reserved_at,
    )
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as error:
        raise ValueError("qualification_attempt_already_reserved") from error
    except OSError as error:
        raise ValueError("reservation_state_write_failed") from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        # Keep an incomplete marker in place: a failed durability write must not permit retry.
        raise ValueError("reservation_state_write_failed") from error
    _append_external_attempt_ledger(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        phase="reserved",
        reserved_at=reserved_at,
        updated_at=reserved_at,
    )
    return marker


def mark_kis_paper_minute_qualification_network_started(
    *,
    control_root: Path,
    repo_root: Path,
    observed_at: datetime,
) -> Path:
    """Durably record the side-effect boundary before the token request."""

    return mark_external_one_shot_network_started(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=KIS_PAPER_MINUTE_QUALIFICATION_OBJECTIVE_ID,
        observed_at=observed_at,
    )


def mark_external_one_shot_network_started(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
    observed_at: datetime,
) -> Path:
    """Advance a reserved one-shot to its pre-network recovery boundary."""

    return _transition_external_one_shot_attempt(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        phase="network_started",
        allowed_predecessors=frozenset({"reserved"}),
        observed_at=observed_at,
    )


def mark_kis_paper_minute_qualification_summary_written(
    *,
    control_root: Path,
    repo_root: Path,
    observed_at: datetime,
    summary_hash: str,
    result_status: str,
) -> Path:
    """Link a completed one-shot attempt to its sanitized external summary."""

    if not summary_hash.startswith("sha256:") or result_status not in {"observed", "rejected"}:
        raise ValueError("reservation_state_write_failed")
    return mark_external_one_shot_summary_written(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=KIS_PAPER_MINUTE_QUALIFICATION_OBJECTIVE_ID,
        observed_at=observed_at,
        summary_hash=summary_hash,
        result_status=result_status,
    )


def mark_external_one_shot_summary_written(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
    observed_at: datetime,
    summary_hash: str,
    result_status: str,
) -> Path:
    """Link a completed or pre-network-rejected one-shot to its sanitized summary."""

    if not summary_hash.startswith("sha256:") or result_status not in {"observed", "rejected"}:
        raise ValueError("reservation_state_write_failed")
    return _transition_external_one_shot_attempt(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        phase="summary_written",
        allowed_predecessors=frozenset({"reserved", "network_started"}),
        observed_at=observed_at,
        summary_hash=summary_hash,
        result_status=result_status,
    )


def _exchange_utc(row: KisPaperMinuteRawBar) -> datetime:
    return _local_timestamp(row.exchange_date, row.exchange_time, _NEW_YORK)


def _korea_utc(row: KisPaperMinuteRawBar) -> datetime:
    return _local_timestamp(row.korea_date, row.korea_time, _SEOUL)


def _local_timestamp(date_text: str, time_text: str, zone: ZoneInfo) -> datetime:
    return datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M%S").replace(
        tzinfo=zone
    ).astimezone(UTC)


def _minute_floor(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _qualification_observation_is_valid(start: datetime, end: datetime) -> bool:
    """Allow completion seconds to vary while keeping the probe narrowly bounded."""

    if not is_kis_paper_minute_qualification_window(start):
        return False
    if end < start or end - start > KIS_PAPER_MINUTE_MAX_PROBE_DURATION:
        return False
    end_local = end.astimezone(_NEW_YORK)
    end_time = end_local.timetz().replace(tzinfo=None)
    return end_local.weekday() < 5 and _REGULAR_SESSION_OPEN <= end_time < _REGULAR_SESSION_CLOSE


def _strict_descending_one_minute(timestamps: tuple[datetime, ...]) -> bool:
    return len(timestamps) >= 2 and all(
        previous - current == timedelta(minutes=1)
        for previous, current in zip(timestamps, timestamps[1:], strict=False)
    )


def _page_descends_one_exchange_minute(page: KisPaperMinutePage) -> bool:
    return _strict_descending_one_minute(tuple(_exchange_utc(row) for row in page.bars))


def _continuation_key_before(row: KisPaperMinuteRawBar) -> str:
    """Use the documented exchange-local minute immediately before a page boundary."""

    exchange_local = datetime.strptime(
        f"{row.exchange_date}{row.exchange_time}", "%Y%m%d%H%M%S"
    ).replace(tzinfo=_NEW_YORK)
    return (exchange_local - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")


def _overlap_facts(
    first_page: KisPaperMinutePage,
    continuation_page: KisPaperMinutePage | None,
) -> tuple[int, int]:
    if continuation_page is None:
        return 0, 0
    first_by_timestamp = {
        _exchange_utc(row): row
        for row in first_page.bars
    }
    continuation_by_timestamp = {
        _exchange_utc(row): row
        for row in continuation_page.bars
    }
    overlap = set(first_by_timestamp).intersection(continuation_by_timestamp)
    conflicting = sum(
        first_by_timestamp[timestamp] != continuation_by_timestamp[timestamp]
        for timestamp in overlap
    )
    return len(overlap), conflicting


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")


def _optional_timestamp_bounds(
    newest: datetime | None,
    oldest: datetime | None,
) -> dict[str, str] | None:
    if newest is None and oldest is None:
        return None
    if newest is None or oldest is None:
        raise ValueError("timestamp bounds must be fully specified")
    return {"newest": _format_utc(newest), "oldest": _format_utc(oldest)}


def _write_bytes_and_sync(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _external_artifact_root(*, artifact_root: Path, repo_root: Path) -> Path:
    resolved_root = Path(artifact_root).resolve()
    if resolved_root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("qualification artifact root must stay outside Git")
    return resolved_root


def _external_attempt_marker(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
) -> Path:
    try:
        _validate_external_objective_id(objective_id)
        root = _external_control_root(control_root=control_root, repo_root=repo_root)
        reservations = _external_control_child(
            root=root,
            child_name="reservations",
            repo_root=repo_root,
        )
        return reservations / f"{objective_id}.json"
    except OSError as error:
        raise ValueError("reservation_marker_invalid") from error


def _external_control_root(*, control_root: Path, repo_root: Path) -> Path:
    root = _external_artifact_root(artifact_root=control_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    return _external_artifact_root(artifact_root=root, repo_root=repo_root)


def _external_control_child(*, root: Path, child_name: str, repo_root: Path) -> Path:
    child = root / child_name
    if child.is_symlink():
        raise ValueError("reservation_marker_invalid")
    child.mkdir(exist_ok=True)
    resolved_child = child.resolve()
    if (
        not resolved_child.is_relative_to(root)
        or resolved_child.is_relative_to(Path(repo_root).resolve())
    ):
        raise ValueError("reservation_marker_invalid")
    return resolved_child


def _validate_external_objective_id(objective_id: str) -> None:
    if (
        not objective_id
        or len(objective_id) > 128
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
            for character in objective_id
        )
    ):
        raise ValueError("reservation_marker_invalid")


def _external_attempt_ledger_directory(*, control_root: Path, repo_root: Path) -> Path:
    root = _external_control_root(control_root=control_root, repo_root=repo_root)
    return _external_control_child(root=root, child_name="ledger", repo_root=repo_root)


def _external_attempt_ledger_phases(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
) -> tuple[str, ...]:
    _validate_external_objective_id(objective_id)
    ledger = _external_attempt_ledger_directory(control_root=control_root, repo_root=repo_root)
    phases: list[str] = []
    for path in sorted(ledger.glob("*.jsonl")):
        if path.is_symlink():
            raise ValueError("control_ledger_invalid")
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                document = json.loads(line)
                if not isinstance(document, dict):
                    raise ValueError("control_ledger_invalid")
                if document.get("kind") != "external_one_shot_attempt":
                    continue
                if document.get("objective_id") != objective_id:
                    continue
                phase = document.get("phase")
                if phase not in {"reserved", "network_started", "summary_written"}:
                    raise ValueError("control_ledger_invalid")
                phases.append(phase)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            if isinstance(error, ValueError) and str(error) == "control_ledger_invalid":
                raise
            raise ValueError("control_ledger_invalid") from error
    return tuple(phases)


def _append_external_attempt_ledger(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
    phase: str,
    reserved_at: datetime,
    updated_at: datetime,
    summary_hash: str | None = None,
    result_status: str | None = None,
) -> None:
    _validate_external_objective_id(objective_id)
    if phase not in {"reserved", "network_started", "summary_written"}:
        raise ValueError("control_ledger_invalid")
    ledger = _external_attempt_ledger_directory(control_root=control_root, repo_root=repo_root)
    timestamp = require_utc(updated_at, "updated_at")
    path = ledger / f"{timestamp:%Y-%m}.jsonl"
    if path.is_symlink():
        raise ValueError("control_ledger_invalid")
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "external_one_shot_attempt",
        "objective_id": objective_id,
        "phase": phase,
        "reserved_at_utc": _format_utc(require_utc(reserved_at, "reserved_at")),
        "updated_at_utc": _format_utc(timestamp),
        "raw_market_data_retained": False,
    }
    if summary_hash is not None:
        document["summary_hash"] = summary_hash
    if result_status is not None:
        document["result_status"] = result_status
    payload = (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")
    try:
        with path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise ValueError("control_ledger_write_failed") from error


def _attempt_marker_payload(
    *,
    objective_id: str,
    phase: str,
    reserved_at: datetime,
    updated_at: datetime,
    summary_hash: str | None = None,
    result_status: str | None = None,
) -> bytes:
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "external_one_shot_attempt_marker",
        "objective_id": objective_id,
        "phase": phase,
        "reserved_at_utc": _format_utc(require_utc(reserved_at, "reserved_at")),
        "updated_at_utc": _format_utc(require_utc(updated_at, "updated_at")),
        "raw_market_data_retained": False,
    }
    if summary_hash is not None:
        document["summary_hash"] = summary_hash
    if result_status is not None:
        document["result_status"] = result_status
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _transition_external_one_shot_attempt(
    *,
    control_root: Path,
    repo_root: Path,
    objective_id: str,
    phase: str,
    allowed_predecessors: frozenset[str],
    observed_at: datetime,
    summary_hash: str | None = None,
    result_status: str | None = None,
) -> Path:
    marker = _external_attempt_marker(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
    )
    if marker.is_symlink():
        raise ValueError("reservation_marker_invalid")
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
        reserved_at = document["reserved_at_utc"]
        updated_at = document["updated_at_utc"]
        marker_phase = document["phase"]
        if (
            not isinstance(document, dict)
            or document.get("objective_id") != objective_id
            or marker_phase not in allowed_predecessors
            or not isinstance(reserved_at, str)
            or not isinstance(updated_at, str)
        ):
            raise ValueError("reservation_marker_invalid")
        reserved_at_value = require_utc(
            datetime.fromisoformat(reserved_at.replace("Z", "+00:00")),
            "reserved_at",
        )
        updated_at_value = require_utc(
            datetime.fromisoformat(updated_at.replace("Z", "+00:00")),
            "updated_at",
        )
        observed_at_value = require_utc(observed_at, "observed_at")
        if updated_at_value < reserved_at_value or observed_at_value < updated_at_value:
            raise ValueError("reservation_marker_invalid")
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, ValueError) and str(error) == "reservation_marker_invalid":
            raise
        raise ValueError("reservation_marker_invalid") from error
    phases = _external_attempt_ledger_phases(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
    )
    if not phases or phases[-1] not in allowed_predecessors:
        raise ValueError("reservation_marker_invalid")
    _append_external_attempt_ledger(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=objective_id,
        phase=phase,
        reserved_at=reserved_at_value,
        updated_at=observed_at_value,
        summary_hash=summary_hash,
        result_status=result_status,
    )
    payload = _attempt_marker_payload(
        objective_id=objective_id,
        phase=phase,
        reserved_at=reserved_at_value,
        updated_at=observed_at_value,
        summary_hash=summary_hash,
        result_status=result_status,
    )
    staging = marker.with_name(f".{marker.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_bytes_and_sync(staging, payload)
        os.replace(staging, marker)
        with marker.open("r+b") as handle:
            os.fsync(handle.fileno())
    except OSError as error:
        raise ValueError("reservation_state_write_failed") from error
    finally:
        if staging.exists():
            staging.unlink()
    return marker

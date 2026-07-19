"""Bounded, metadata-only KIS paper historical-data capability probe."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_market_data import (
    KIS_PAPER_DAILY_MAX_ROWS,
    KIS_PAPER_MINUTE_MAX_ROWS,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
)

KIS_PAPER_HISTORICAL_PROBE_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data-agent/kis-paper-historical-data-probe"
)
KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT = Path("D:/thericher-v2/model-artifacts/_control")
KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID = "kis-paper-historical-data-probe-v1"
KIS_PAPER_HISTORICAL_PROBE_VERSION = "kis-paper-historical-data-probe-v1"
KIS_PAPER_HISTORICAL_PROBE_SYMBOLS = ("QQQ", "SPY")
KIS_PAPER_HISTORICAL_MAX_DAILY_PAGES = 3
KIS_PAPER_HISTORICAL_MAX_MINUTE_PAGES = 3
_NEW_YORK = ZoneInfo("America/New_York")
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "control_ledger_invalid",
        "control_ledger_write_failed",
        "daily_response_invalid",
        "daily_response_rejected",
        "historical_probe_bounds_invalid",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "minute_timestamp_invalid",
        "paper_host_required",
        "qualification_attempt_already_reserved",
        "redirect_rejected",
        "request_not_allowlisted",
        "reservation_marker_invalid",
        "reservation_state_write_failed",
        "response_invalid",
        "transport_failure",
    }
)


class KisPaperHistoricalProbeError(RuntimeError):
    """A non-secret failure from the bounded historical capability probe."""


@dataclass(frozen=True)
class KisPaperHistoricalDailyObservation:
    """Sanitized daily-page metadata for one approved symbol."""

    symbol: str
    first_row_count: int
    first_newest_date: str | None
    first_oldest_date: str | None
    required_ohlcv_fields_present: bool
    continuation_available: bool
    continuation_requested: bool
    continuation_row_count: int | None
    continuation_newest_date: str | None
    continuation_oldest_date: str | None
    continuation_has_older_date: bool

    def __post_init__(self) -> None:
        if self.symbol not in KIS_PAPER_HISTORICAL_PROBE_SYMBOLS:
            raise ValueError("historical daily symbol is not approved")
        if not _is_bounded_int(self.first_row_count, lower=0, upper=KIS_PAPER_DAILY_MAX_ROWS):
            raise ValueError("historical daily page count is not bounded")
        if self.continuation_row_count is not None and not _is_bounded_int(
            self.continuation_row_count,
            lower=0,
            upper=KIS_PAPER_DAILY_MAX_ROWS,
        ):
            raise ValueError("historical daily continuation count is not bounded")
        if not all(
            isinstance(value, bool)
            for value in (
                self.required_ohlcv_fields_present,
                self.continuation_available,
                self.continuation_requested,
                self.continuation_has_older_date,
            )
        ):
            raise ValueError("historical daily facts must be boolean")
        if self.continuation_requested != (self.continuation_row_count is not None):
            raise ValueError("historical daily continuation facts are inconsistent")
        if self.continuation_requested != (
            self.continuation_newest_date is not None
            and self.continuation_oldest_date is not None
        ):
            raise ValueError("historical daily continuation bounds are inconsistent")
        for value in (
            self.first_newest_date,
            self.first_oldest_date,
            self.continuation_newest_date,
            self.continuation_oldest_date,
        ):
            if value is not None and (
                not isinstance(value, str) or len(value) != 8 or not value.isdigit()
            ):
                raise ValueError("historical daily date facts are invalid")
        if (
            self.first_newest_date is not None
            and self.first_oldest_date is not None
            and self.first_newest_date < self.first_oldest_date
        ):
            raise ValueError("historical daily first bounds are invalid")
        if (
            self.continuation_newest_date is not None
            and self.continuation_oldest_date is not None
            and self.continuation_newest_date < self.continuation_oldest_date
        ):
            raise ValueError("historical daily continuation bounds are invalid")


@dataclass(frozen=True)
class KisPaperHistoricalMinuteObservation:
    """Sanitized raw-minute metadata for one approved symbol."""

    symbol: str
    first_row_count: int
    first_newest_utc: datetime
    first_oldest_utc: datetime
    continuation_available: bool
    continuation_requested: bool
    continuation_row_count: int | None
    continuation_newest_utc: datetime | None
    continuation_oldest_utc: datetime | None
    exact_overlap_count: int
    continuation_boundary_contiguous: bool

    def __post_init__(self) -> None:
        if self.symbol not in KIS_PAPER_HISTORICAL_PROBE_SYMBOLS:
            raise ValueError("historical minute symbol is not approved")
        if not _is_bounded_int(self.first_row_count, lower=1, upper=KIS_PAPER_MINUTE_MAX_ROWS):
            raise ValueError("historical minute page count is not bounded")
        for field_name in ("first_newest_utc", "first_oldest_utc"):
            object.__setattr__(
                self,
                field_name,
                require_utc(getattr(self, field_name), field_name),
            )
        for field_name in ("continuation_newest_utc", "continuation_oldest_utc"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_utc(value, field_name))
        if self.continuation_row_count is not None and not _is_bounded_int(
            self.continuation_row_count,
            lower=1,
            upper=KIS_PAPER_MINUTE_MAX_ROWS,
        ):
            raise ValueError("historical minute continuation count is not bounded")
        if not all(
            isinstance(value, bool)
            for value in (
                self.continuation_available,
                self.continuation_requested,
                self.continuation_boundary_contiguous,
            )
        ):
            raise ValueError("historical minute facts must be boolean")
        if self.continuation_requested != (self.continuation_row_count is not None):
            raise ValueError("historical minute continuation facts are inconsistent")
        if self.continuation_requested != (
            self.continuation_newest_utc is not None and self.continuation_oldest_utc is not None
        ):
            raise ValueError("historical minute continuation bounds are inconsistent")
        if not _is_bounded_int(
            self.exact_overlap_count,
            lower=0,
            upper=min(
                self.first_row_count,
                self.continuation_row_count or 0,
            ),
        ):
            raise ValueError("historical minute overlap count is not bounded")
        if self.first_newest_utc < self.first_oldest_utc:
            raise ValueError("historical minute first bounds are invalid")
        if (
            self.continuation_newest_utc is not None
            and self.continuation_oldest_utc is not None
            and self.continuation_newest_utc < self.continuation_oldest_utc
        ):
            raise ValueError("historical minute continuation bounds are invalid")
        if self.continuation_row_count is None and (
            self.exact_overlap_count != 0 or self.continuation_boundary_contiguous
        ):
            raise ValueError("historical minute continuation facts are inconsistent")


@dataclass(frozen=True)
class KisPaperHistoricalProbeEvidence:
    """Typed metadata-only result of the fixed QQQ/SPY daily/minute probe."""

    observed_at: datetime
    requested_by_date: str
    call_counts: KisPaperMarketDataCallCounts
    daily: tuple[KisPaperHistoricalDailyObservation, ...]
    minute: tuple[KisPaperHistoricalMinuteObservation, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if (
            not isinstance(self.requested_by_date, str)
            or len(self.requested_by_date) != 8
            or not self.requested_by_date.isdigit()
        ):
            raise ValueError("historical probe date must be YYYYMMDD")
        object.__setattr__(self, "daily", tuple(self.daily))
        object.__setattr__(self, "minute", tuple(self.minute))
        if not all(isinstance(item, KisPaperHistoricalDailyObservation) for item in self.daily):
            raise ValueError("historical daily observations must be typed")
        if not all(isinstance(item, KisPaperHistoricalMinuteObservation) for item in self.minute):
            raise ValueError("historical minute observations must be typed")
        if tuple(item.symbol for item in self.daily) != KIS_PAPER_HISTORICAL_PROBE_SYMBOLS:
            raise ValueError("historical daily scope is not fixed")
        if tuple(item.symbol for item in self.minute) != KIS_PAPER_HISTORICAL_PROBE_SYMBOLS:
            raise ValueError("historical minute scope is not fixed")
        _require_bounded_call_counts(self.call_counts)


@dataclass(frozen=True)
class KisPaperHistoricalProbeFailure:
    """Typed sanitized failure input for the external historical probe artifact."""

    observed_at: datetime
    call_counts: KisPaperMarketDataCallCounts
    reason: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if not isinstance(self.call_counts, KisPaperMarketDataCallCounts):
            raise ValueError("historical failure call counts must be typed")
        if not _has_bounded_failure_call_counts(self.call_counts):
            raise ValueError("historical failure call counts are not bounded")
        object.__setattr__(
            self,
            "reason",
            sanitize_kis_paper_historical_probe_failure_reason(self.reason),
        )


def run_bounded_kis_paper_historical_probe(
    client: KisPaperMarketDataClient,
    *,
    observed_at: datetime | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperHistoricalProbeEvidence:
    """Read the predeclared QQQ/SPY page set without retaining any raw rows."""

    observed = require_utc(observed_at if observed_at is not None else clock(), "observed_at")
    requested_by_date = observed.astimezone(_NEW_YORK).strftime("%Y%m%d")

    qqq_daily_first = client.fetch_daily_page(
        KisPaperDailyQuery(symbol="QQQ", by_date=requested_by_date)
    )
    qqq_daily_continuation = _fetch_daily_continuation_if_available(client, qqq_daily_first)
    spy_daily_first = client.fetch_daily_page(
        KisPaperDailyQuery(symbol="SPY", by_date=requested_by_date)
    )

    qqq_minute_first = client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="QQQ"))
    qqq_minute_continuation = _fetch_minute_continuation_if_available(client, qqq_minute_first)
    spy_minute_first = client.fetch_minute_page(KisPaperMinuteQuery(exchange="NAS", symbol="SPY"))

    return KisPaperHistoricalProbeEvidence(
        observed_at=observed,
        requested_by_date=requested_by_date,
        call_counts=client.call_counts,
        daily=(
            _daily_observation(qqq_daily_first, qqq_daily_continuation),
            _daily_observation(spy_daily_first, None),
        ),
        minute=(
            _minute_observation(qqq_minute_first, qqq_minute_continuation),
            _minute_observation(spy_minute_first, None),
        ),
    )


def sanitized_kis_paper_historical_probe_summary(
    evidence: KisPaperHistoricalProbeEvidence,
) -> dict[str, object]:
    """Project fixed metadata only; price rows, cursors, and tokens are omitted."""

    evidence = _validated_historical_evidence(evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_historical_data_capability_probe",
        "probe_version": KIS_PAPER_HISTORICAL_PROBE_VERSION,
        "status": "observed",
        "scope": {
            "symbols": list(KIS_PAPER_HISTORICAL_PROBE_SYMBOLS),
            "exchange": "NAS",
            "endpoints": ["overseas_daily", "overseas_raw_1m"],
            "account_or_order_endpoint_called": False,
            "live_endpoint_called": False,
        },
        "observation": {
            "observed_at_utc": _format_utc(evidence.observed_at),
            "requested_by_date": evidence.requested_by_date,
            "call_counts": {
                "token_attempts": evidence.call_counts.token_attempts,
                "daily_page_attempts": evidence.call_counts.daily_page_attempts,
                "minute_page_attempts": evidence.call_counts.minute_page_attempts,
            },
            "daily": [_sanitized_daily_observation(item) for item in evidence.daily],
            "minute": [_sanitized_minute_observation(item) for item in evidence.minute],
        },
        "storage": {
            "raw_market_data_retained": False,
            "in_memory_only": True,
            "persistent_cache_allowed": False,
        },
        "limitations": [
            "This bounded response sample does not establish long-history retention "
            "or rate limits.",
            "It does not establish storage rights, point-in-time universe coverage, adjustments, "
            "or model fitness.",
        ],
    }


def sanitized_kis_paper_historical_probe_failure_summary(
    failure: KisPaperHistoricalProbeFailure,
) -> dict[str, object]:
    """Persist a non-secret bounded failure without response bodies or raw rows."""

    if not isinstance(failure.call_counts, KisPaperMarketDataCallCounts):
        raise ValueError("historical failure call counts must be typed")
    if not _has_bounded_failure_call_counts(failure.call_counts):
        raise ValueError("historical failure call counts are not bounded")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_historical_data_capability_probe",
        "probe_version": KIS_PAPER_HISTORICAL_PROBE_VERSION,
        "status": "rejected",
        "reason": failure.reason,
        "scope": {
            "symbols": list(KIS_PAPER_HISTORICAL_PROBE_SYMBOLS),
            "exchange": "NAS",
            "endpoints": ["overseas_daily", "overseas_raw_1m"],
            "account_or_order_endpoint_called": False,
            "live_endpoint_called": False,
        },
        "observed_at_utc": _format_utc(failure.observed_at),
        "call_counts": {
            "token_attempts": failure.call_counts.token_attempts,
            "daily_page_attempts": failure.call_counts.daily_page_attempts,
            "minute_page_attempts": failure.call_counts.minute_page_attempts,
        },
        "storage": {"raw_market_data_retained": False, "in_memory_only": True},
    }


def write_kis_paper_historical_probe_summary(
    *,
    result: KisPaperHistoricalProbeEvidence | KisPaperHistoricalProbeFailure,
    artifact_root: Path,
    run_id: str,
    repo_root: Path,
) -> tuple[Path, str]:
    """Atomically write one internally sanitized external evidence document."""

    if not run_id or any(character not in "0123456789TZ-" for character in run_id):
        raise ValueError("historical probe run id is invalid")
    if isinstance(result, KisPaperHistoricalProbeEvidence):
        document = sanitized_kis_paper_historical_probe_summary(result)
    elif isinstance(result, KisPaperHistoricalProbeFailure):
        document = sanitized_kis_paper_historical_probe_failure_summary(result)
    else:
        raise TypeError("historical probe summary requires typed evidence or failure")
    root = _external_artifact_root(artifact_root=artifact_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / run_id
    if target.exists() or target.is_symlink():
        raise FileExistsError("historical probe artifact destination already exists")
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    staging = root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        _write_bytes_and_sync(staging / "summary.json", payload)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target / "summary.json", "sha256:" + hashlib.sha256(payload).hexdigest()


def sanitize_kis_paper_historical_probe_failure_reason(value: BaseException | str) -> str:
    """Do not let transport or server text reach external evidence."""

    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_probe_error"


def _fetch_daily_continuation_if_available(
    client: KisPaperMarketDataClient,
    first: KisPaperDailyPage,
) -> KisPaperDailyPage | None:
    if not first.continuation_available:
        return None
    if first.oldest_date is None:
        raise KisPaperHistoricalProbeError("historical_probe_bounds_invalid")
    return client.fetch_daily_page(
        KisPaperDailyQuery(
            symbol=first.query.symbol,
            by_date=first.oldest_date,
            continuation="F",
        )
    )


def _fetch_minute_continuation_if_available(
    client: KisPaperMarketDataClient,
    first: KisPaperMinutePage,
) -> KisPaperMinutePage | None:
    if first.next_cursor is None:
        return None
    oldest = first.bars[-1]
    oldest_local = _minute_timestamp(
        oldest.exchange_date,
        oldest.exchange_time,
    ).astimezone(_NEW_YORK)
    return client.fetch_minute_page(
        KisPaperMinuteQuery(
            exchange=first.query.exchange,
            symbol=first.query.symbol,
            continuation_next=first.next_cursor,
            continuation_key=(oldest_local - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S"),
        )
    )


def _daily_observation(
    first: KisPaperDailyPage,
    continuation: KisPaperDailyPage | None,
) -> KisPaperHistoricalDailyObservation:
    continuation_has_older_date = (
        continuation is not None
        and first.oldest_date is not None
        and continuation.oldest_date is not None
        and continuation.oldest_date < first.oldest_date
    )
    return KisPaperHistoricalDailyObservation(
        symbol=first.query.symbol,
        first_row_count=first.row_count,
        first_newest_date=first.newest_date,
        first_oldest_date=first.oldest_date,
        required_ohlcv_fields_present=first.required_ohlcv_fields_present,
        continuation_available=first.continuation_available,
        continuation_requested=continuation is not None,
        continuation_row_count=continuation.row_count if continuation is not None else None,
        continuation_newest_date=continuation.newest_date if continuation is not None else None,
        continuation_oldest_date=continuation.oldest_date if continuation is not None else None,
        continuation_has_older_date=continuation_has_older_date,
    )


def _minute_observation(
    first: KisPaperMinutePage,
    continuation: KisPaperMinutePage | None,
) -> KisPaperHistoricalMinuteObservation:
    first_timestamps = tuple(
        _minute_timestamp(row.exchange_date, row.exchange_time) for row in first.bars
    )
    continuation_timestamps = (
        tuple(_minute_timestamp(row.exchange_date, row.exchange_time) for row in continuation.bars)
        if continuation is not None
        else ()
    )
    overlap = set(first_timestamps).intersection(continuation_timestamps)
    boundary_contiguous = bool(continuation_timestamps) and (
        max(continuation_timestamps) + timedelta(minutes=1) == min(first_timestamps)
    )
    return KisPaperHistoricalMinuteObservation(
        symbol=first.query.symbol,
        first_row_count=len(first.bars),
        first_newest_utc=max(first_timestamps),
        first_oldest_utc=min(first_timestamps),
        continuation_available=first.next_cursor is not None,
        continuation_requested=continuation is not None,
        continuation_row_count=len(continuation.bars) if continuation is not None else None,
        continuation_newest_utc=max(continuation_timestamps) if continuation_timestamps else None,
        continuation_oldest_utc=min(continuation_timestamps) if continuation_timestamps else None,
        exact_overlap_count=len(overlap),
        continuation_boundary_contiguous=boundary_contiguous,
    )


def _minute_timestamp(date_text: str, time_text: str) -> datetime:
    try:
        return datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M%S").replace(
            tzinfo=_NEW_YORK
        ).astimezone(UTC)
    except ValueError as error:
        raise KisPaperHistoricalProbeError("minute_timestamp_invalid") from error


def _require_bounded_call_counts(call_counts: KisPaperMarketDataCallCounts) -> None:
    if not isinstance(call_counts, KisPaperMarketDataCallCounts):
        raise ValueError("historical probe call counts must be typed")
    if (
        not _is_bounded_int(call_counts.token_attempts, lower=1, upper=1)
        or not _is_bounded_int(call_counts.daily_page_attempts, lower=2, upper=3)
        or not _is_bounded_int(call_counts.minute_page_attempts, lower=2, upper=3)
    ):
        raise ValueError("historical probe call counts are not bounded")


def _has_bounded_failure_call_counts(call_counts: KisPaperMarketDataCallCounts) -> bool:
    return (
        isinstance(call_counts, KisPaperMarketDataCallCounts)
        and _is_bounded_int(call_counts.token_attempts, lower=0, upper=1)
        and _is_bounded_int(
            call_counts.daily_page_attempts,
            lower=0,
            upper=KIS_PAPER_HISTORICAL_MAX_DAILY_PAGES,
        )
        and _is_bounded_int(
            call_counts.minute_page_attempts,
            lower=0,
            upper=KIS_PAPER_HISTORICAL_MAX_MINUTE_PAGES,
        )
    )


def _is_bounded_int(value: object, *, lower: int, upper: int) -> bool:
    return type(value) is int and lower <= value <= upper


def _validated_historical_evidence(
    evidence: KisPaperHistoricalProbeEvidence,
) -> KisPaperHistoricalProbeEvidence:
    """Rebuild typed metadata before it crosses the external artifact boundary."""

    if not isinstance(evidence, KisPaperHistoricalProbeEvidence):
        raise TypeError("historical probe summary requires typed evidence")
    if not isinstance(evidence.call_counts, KisPaperMarketDataCallCounts):
        raise ValueError("historical probe call counts must be typed")
    daily = tuple(
        KisPaperHistoricalDailyObservation(
            symbol=item.symbol,
            first_row_count=item.first_row_count,
            first_newest_date=item.first_newest_date,
            first_oldest_date=item.first_oldest_date,
            required_ohlcv_fields_present=item.required_ohlcv_fields_present,
            continuation_available=item.continuation_available,
            continuation_requested=item.continuation_requested,
            continuation_row_count=item.continuation_row_count,
            continuation_newest_date=item.continuation_newest_date,
            continuation_oldest_date=item.continuation_oldest_date,
            continuation_has_older_date=item.continuation_has_older_date,
        )
        for item in evidence.daily
    )
    minute = tuple(
        KisPaperHistoricalMinuteObservation(
            symbol=item.symbol,
            first_row_count=item.first_row_count,
            first_newest_utc=item.first_newest_utc,
            first_oldest_utc=item.first_oldest_utc,
            continuation_available=item.continuation_available,
            continuation_requested=item.continuation_requested,
            continuation_row_count=item.continuation_row_count,
            continuation_newest_utc=item.continuation_newest_utc,
            continuation_oldest_utc=item.continuation_oldest_utc,
            exact_overlap_count=item.exact_overlap_count,
            continuation_boundary_contiguous=item.continuation_boundary_contiguous,
        )
        for item in evidence.minute
    )
    return KisPaperHistoricalProbeEvidence(
        observed_at=evidence.observed_at,
        requested_by_date=evidence.requested_by_date,
        call_counts=evidence.call_counts,
        daily=daily,
        minute=minute,
        schema_version=evidence.schema_version,
    )


def _sanitized_daily_observation(item: KisPaperHistoricalDailyObservation) -> dict[str, object]:
    return {
        "symbol": item.symbol,
        "first_row_count": item.first_row_count,
        "first_date_bounds": {"newest": item.first_newest_date, "oldest": item.first_oldest_date},
        "required_ohlcv_fields_present": item.required_ohlcv_fields_present,
        "continuation_available": item.continuation_available,
        "continuation_requested": item.continuation_requested,
        "continuation_row_count": item.continuation_row_count,
        "continuation_date_bounds": {
            "newest": item.continuation_newest_date,
            "oldest": item.continuation_oldest_date,
        }
        if item.continuation_requested
        else None,
        "continuation_has_older_date": item.continuation_has_older_date,
    }


def _sanitized_minute_observation(item: KisPaperHistoricalMinuteObservation) -> dict[str, object]:
    return {
        "symbol": item.symbol,
        "first_row_count": item.first_row_count,
        "first_timestamp_bounds_utc": {
            "newest": _format_utc(item.first_newest_utc),
            "oldest": _format_utc(item.first_oldest_utc),
        },
        "continuation_available": item.continuation_available,
        "continuation_requested": item.continuation_requested,
        "continuation_row_count": item.continuation_row_count,
        "continuation_timestamp_bounds_utc": {
            "newest": _format_utc(item.continuation_newest_utc),
            "oldest": _format_utc(item.continuation_oldest_utc),
        }
        if item.continuation_requested
        and item.continuation_newest_utc is not None
        and item.continuation_oldest_utc is not None
        else None,
        "exact_overlap_count": item.exact_overlap_count,
        "continuation_boundary_contiguous": item.continuation_boundary_contiguous,
    }


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")


def _write_bytes_and_sync(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _external_artifact_root(*, artifact_root: Path, repo_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    if root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("historical probe artifact root must stay outside Git")
    return root

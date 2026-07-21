"""Bounded KIS paper historical-capacity observations.

The two tracks deliberately measure endpoint depth without becoming a data
archive. They keep OHLCV rows and continuation cursors in memory and persist
only sanitized page metadata outside the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_market_data import (
    KIS_PAPER_DAILY_MAX_ROWS,
    KIS_PAPER_MINUTE_MAX_ROWS,
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
)
from .kis_minute_qualification import write_external_one_shot_summary

KIS_PAPER_HISTORICAL_CAPACITY_MAP_VERSION = "kis-paper-historical-capacity-map-v1"
KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL = "QQQ"
KIS_PAPER_HISTORICAL_CAPACITY_MAP_EXCHANGE = "NAS"
KIS_PAPER_DAILY_CAPACITY_MAP_OBJECTIVE_ID = "kis-paper-daily-capacity-map-v1"
KIS_PAPER_MINUTE_CAPACITY_MAP_OBJECTIVE_ID = "kis-paper-raw-minute-capacity-map-v1"
KIS_PAPER_DAILY_CAPACITY_MAP_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data-agent/kis-paper-daily-capacity-map"
)
KIS_PAPER_MINUTE_CAPACITY_MAP_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data-agent/kis-paper-raw-minute-capacity-map"
)
KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT = Path("D:/thericher-v2/model-artifacts/_control")
KIS_PAPER_DAILY_CAPACITY_MAP_ANCHORS = ("20260717", "20250717")
KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGES_PER_ANCHOR = 2
KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS = (
    len(KIS_PAPER_DAILY_CAPACITY_MAP_ANCHORS) * KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGES_PER_ANCHOR
)
KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS = 8

_NEW_YORK = ZoneInfo("America/New_York")
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "daily_page_limit_exceeded",
        "daily_response_invalid",
        "daily_response_rejected",
        "minute_page_limit_exceeded",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "paper_host_required",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
    }
)


class KisPaperHistoricalCapacityMapError(RuntimeError):
    """A non-secret capacity-map result error."""


@dataclass(frozen=True)
class KisPaperDailyCapacityPage:
    """Sanitized facts for one daily page at a fixed depth anchor."""

    anchor_date: str
    page_number: int
    row_count: int
    newest_date: str | None
    oldest_date: str | None
    required_ohlcv_fields_present: bool
    continuation_available: bool
    progressed_older_than_previous: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.anchor_date not in KIS_PAPER_DAILY_CAPACITY_MAP_ANCHORS:
            raise ValueError("daily capacity anchor is invalid")
        if not (1 <= self.page_number <= KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGES_PER_ANCHOR):
            raise ValueError("daily capacity page number is invalid")
        if not (0 <= self.row_count <= KIS_PAPER_DAILY_MAX_ROWS):
            raise ValueError("daily capacity row count is invalid")
        if not isinstance(self.required_ohlcv_fields_present, bool):
            raise ValueError("daily capacity fields flag is invalid")
        if not isinstance(self.continuation_available, bool):
            raise ValueError("daily capacity continuation flag is invalid")
        if not isinstance(self.progressed_older_than_previous, bool):
            raise ValueError("daily capacity progression flag is invalid")
        if (self.newest_date is None) != (self.oldest_date is None):
            raise ValueError("daily capacity date bounds are incomplete")
        for value in (self.newest_date, self.oldest_date):
            if value is not None and (len(value) != 8 or not value.isdigit()):
                raise ValueError("daily capacity date bound is invalid")
        if (
            self.newest_date is not None
            and self.oldest_date is not None
            and self.newest_date < self.oldest_date
        ):
            raise ValueError("daily capacity date bounds are invalid")


@dataclass(frozen=True)
class KisPaperMinuteCapacityPage:
    """Sanitized facts for one raw-minute page, with no price or cursor data."""

    page_number: int
    row_count: int
    newest_utc: datetime
    oldest_utc: datetime
    required_ohlcv_fields_present: bool
    continuation_available: bool
    timestamps_strictly_descending: bool
    timestamps_one_minute_contiguous: bool
    overlap_with_previous_count: int
    boundary_contiguous_to_previous: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not (1 <= self.page_number <= KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS):
            raise ValueError("minute capacity page number is invalid")
        if not (1 <= self.row_count <= KIS_PAPER_MINUTE_MAX_ROWS):
            raise ValueError("minute capacity row count is invalid")
        object.__setattr__(self, "newest_utc", require_utc(self.newest_utc, "newest_utc"))
        object.__setattr__(self, "oldest_utc", require_utc(self.oldest_utc, "oldest_utc"))
        if self.newest_utc < self.oldest_utc:
            raise ValueError("minute capacity timestamp bounds are invalid")
        if not all(
            isinstance(value, bool)
            for value in (
                self.required_ohlcv_fields_present,
                self.continuation_available,
                self.timestamps_strictly_descending,
                self.timestamps_one_minute_contiguous,
                self.boundary_contiguous_to_previous,
            )
        ):
            raise ValueError("minute capacity flags are invalid")
        if not (0 <= self.overlap_with_previous_count <= self.row_count):
            raise ValueError("minute capacity overlap count is invalid")
        if self.page_number == 1 and (
            self.overlap_with_previous_count != 0 or self.boundary_contiguous_to_previous
        ):
            raise ValueError("first minute capacity page cannot have a previous boundary")


@dataclass(frozen=True)
class KisPaperDailyCapacityMapResult:
    """One independently terminal daily-capacity-map result."""

    observed_at: datetime
    call_counts: KisPaperMarketDataCallCounts
    pages: tuple[KisPaperDailyCapacityPage, ...]
    status: Literal["observed", "rejected"]
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "pages", tuple(self.pages))
        if not all(isinstance(page, KisPaperDailyCapacityPage) for page in self.pages):
            raise ValueError("daily capacity pages must be typed")
        _require_daily_call_counts(self.call_counts)
        _require_result_status(self.status, self.reason)
        if not _daily_pages_are_ordered(self.pages):
            raise ValueError("daily capacity pages must be ordered without gaps")
        if self.call_counts.daily_page_attempts < len(self.pages):
            raise ValueError("daily capacity calls cannot trail saved pages")


@dataclass(frozen=True)
class KisPaperMinuteCapacityMapResult:
    """One independently terminal raw-minute-capacity-map result."""

    observed_at: datetime
    call_counts: KisPaperMarketDataCallCounts
    pages: tuple[KisPaperMinuteCapacityPage, ...]
    status: Literal["observed", "rejected"]
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "pages", tuple(self.pages))
        if not all(isinstance(page, KisPaperMinuteCapacityPage) for page in self.pages):
            raise ValueError("minute capacity pages must be typed")
        _require_minute_call_counts(self.call_counts)
        _require_result_status(self.status, self.reason)
        if tuple(page.page_number for page in self.pages) != tuple(
            range(1, len(self.pages) + 1)
        ):
            raise ValueError("minute capacity pages must be ordered without gaps")
        if self.call_counts.minute_page_attempts < len(self.pages):
            raise ValueError("minute capacity calls cannot trail saved pages")


def run_bounded_kis_paper_daily_capacity_map(
    client: KisPaperMarketDataClient,
    *,
    observed_at: datetime | None = None,
) -> KisPaperDailyCapacityMapResult:
    """Measure two fixed daily anchors and stop the track at its first failure."""

    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    pages: list[KisPaperDailyCapacityPage] = []
    try:
        client.ensure_authenticated()
        for anchor_date in KIS_PAPER_DAILY_CAPACITY_MAP_ANCHORS:
            previous_oldest: str | None = None
            query = KisPaperDailyQuery(
                symbol=KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL,
                by_date=anchor_date,
            )
            for page_number in range(1, KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGES_PER_ANCHOR + 1):
                page = client.fetch_daily_page(query)
                pages.append(_daily_capacity_page(page, anchor_date, page_number, previous_oldest))
                if not page.continuation_available or page.oldest_date is None:
                    break
                previous_oldest = page.oldest_date
                query = KisPaperDailyQuery(
                    symbol=KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL,
                    by_date=page.oldest_date,
                    continuation="F",
                )
    except KisPaperMarketDataError as error:
        return KisPaperDailyCapacityMapResult(
            observed_at=observed,
            call_counts=client.call_counts,
            pages=tuple(pages),
            status="rejected",
            reason=sanitize_kis_paper_historical_capacity_map_failure_reason(error),
        )
    return KisPaperDailyCapacityMapResult(
        observed_at=observed,
        call_counts=client.call_counts,
        pages=tuple(pages),
        status="observed",
    )


def run_bounded_kis_paper_minute_capacity_map(
    client: KisPaperMarketDataClient,
    *,
    observed_at: datetime | None = None,
) -> KisPaperMinuteCapacityMapResult:
    """Measure up to eight raw-minute pages, stopping at the first rejection."""

    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    pages: list[KisPaperMinuteCapacityPage] = []
    previous_timestamps: tuple[datetime, ...] = ()
    query = KisPaperMinuteQuery(
        exchange=KIS_PAPER_HISTORICAL_CAPACITY_MAP_EXCHANGE,
        symbol=KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL,
    )
    try:
        client.ensure_authenticated()
        for page_number in range(1, KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS + 1):
            page = client.fetch_minute_page(query)
            timestamps = _minute_timestamps(page)
            pages.append(_minute_capacity_page(page, page_number, timestamps, previous_timestamps))
            if page.next_cursor is None:
                break
            previous_timestamps = timestamps
            query = KisPaperMinuteQuery(
                exchange=KIS_PAPER_HISTORICAL_CAPACITY_MAP_EXCHANGE,
                symbol=KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL,
                continuation_next=page.next_cursor,
                continuation_key=_continuation_key_before_oldest(timestamps),
            )
    except KisPaperMarketDataError as error:
        return KisPaperMinuteCapacityMapResult(
            observed_at=observed,
            call_counts=client.call_counts,
            pages=tuple(pages),
            status="rejected",
            reason=sanitize_kis_paper_historical_capacity_map_failure_reason(error),
        )
    return KisPaperMinuteCapacityMapResult(
        observed_at=observed,
        call_counts=client.call_counts,
        pages=tuple(pages),
        status="observed",
    )


def sanitized_kis_paper_daily_capacity_map_summary(
    result: KisPaperDailyCapacityMapResult,
) -> dict[str, object]:
    """Render a typed daily result without rows, cursor values, or credentials."""

    result = _validated_daily_result(result)
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_capacity_map",
        "capacity_map_version": KIS_PAPER_HISTORICAL_CAPACITY_MAP_VERSION,
        "status": result.status,
        "scope": _daily_scope(),
        "observation": {
            "observed_at_utc": _format_utc(result.observed_at),
            "anchors": list(KIS_PAPER_DAILY_CAPACITY_MAP_ANCHORS),
            "max_pages_per_anchor": KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGES_PER_ANCHOR,
            "call_counts": _call_counts_document(result.call_counts),
            "pages": [_daily_page_document(page) for page in result.pages],
        },
        "storage": {"raw_market_data_retained": False, "in_memory_only": True},
        "limitations": [
            "This bounded observation does not establish archive retention, rate limits, "
            "or storage rights.",
            "It does not create a market-data dataset, model input, or execution capability.",
        ],
    }
    if result.reason is not None:
        document["reason"] = result.reason
    return document


def sanitized_kis_paper_minute_capacity_map_summary(
    result: KisPaperMinuteCapacityMapResult,
) -> dict[str, object]:
    """Render a typed raw-minute result without rows, cursor values, or credentials."""

    result = _validated_minute_result(result)
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_raw_minute_capacity_map",
        "capacity_map_version": KIS_PAPER_HISTORICAL_CAPACITY_MAP_VERSION,
        "status": result.status,
        "scope": _minute_scope(),
        "observation": {
            "observed_at_utc": _format_utc(result.observed_at),
            "max_page_attempts": KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
            "call_counts": _call_counts_document(result.call_counts),
            "pages": [_minute_page_document(page) for page in result.pages],
        },
        "storage": {"raw_market_data_retained": False, "in_memory_only": True},
        "limitations": [
            "This bounded observation does not establish archive retention, rate limits, "
            "or storage rights.",
            "It does not create a market-data dataset, model input, or execution capability.",
        ],
    }
    if result.reason is not None:
        document["reason"] = result.reason
    return document


def write_kis_paper_daily_capacity_map_summary(
    *,
    result: KisPaperDailyCapacityMapResult,
    artifact_root: Path,
    run_id: str,
    repo_root: Path,
) -> tuple[Path, str]:
    return write_external_one_shot_summary(
        document=sanitized_kis_paper_daily_capacity_map_summary(result),
        artifact_root=artifact_root,
        run_id=run_id,
        repo_root=repo_root,
    )


def write_kis_paper_minute_capacity_map_summary(
    *,
    result: KisPaperMinuteCapacityMapResult,
    artifact_root: Path,
    run_id: str,
    repo_root: Path,
) -> tuple[Path, str]:
    return write_external_one_shot_summary(
        document=sanitized_kis_paper_minute_capacity_map_summary(result),
        artifact_root=artifact_root,
        run_id=run_id,
        repo_root=repo_root,
    )


def sanitize_kis_paper_historical_capacity_map_failure_reason(value: BaseException | str) -> str:
    """Keep server and transport text out of external artifacts."""

    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_capacity_map_error"


def _daily_capacity_page(
    page: KisPaperDailyPage,
    anchor_date: str,
    page_number: int,
    previous_oldest: str | None,
) -> KisPaperDailyCapacityPage:
    return KisPaperDailyCapacityPage(
        anchor_date=anchor_date,
        page_number=page_number,
        row_count=page.row_count,
        newest_date=page.newest_date,
        oldest_date=page.oldest_date,
        required_ohlcv_fields_present=page.required_ohlcv_fields_present,
        continuation_available=page.continuation_available,
        progressed_older_than_previous=(
            previous_oldest is not None
            and page.oldest_date is not None
            and page.oldest_date < previous_oldest
        ),
    )


def _minute_timestamps(page: KisPaperMinutePage) -> tuple[datetime, ...]:
    if not page.bars:
        raise KisPaperMarketDataError("minute_response_empty")
    return tuple(_exchange_utc(row.exchange_date, row.exchange_time) for row in page.bars)


def _minute_capacity_page(
    page: KisPaperMinutePage,
    page_number: int,
    timestamps: tuple[datetime, ...],
    previous_timestamps: tuple[datetime, ...],
) -> KisPaperMinuteCapacityPage:
    overlap = len(set(timestamps).intersection(previous_timestamps))
    return KisPaperMinuteCapacityPage(
        page_number=page_number,
        row_count=len(page.bars),
        newest_utc=max(timestamps),
        oldest_utc=min(timestamps),
        required_ohlcv_fields_present=bool(page.bars),
        continuation_available=page.next_cursor is not None,
        timestamps_strictly_descending=all(
            previous > current
            for previous, current in zip(timestamps, timestamps[1:], strict=False)
        ),
        timestamps_one_minute_contiguous=all(
            previous - current == timedelta(minutes=1)
            for previous, current in zip(timestamps, timestamps[1:], strict=False)
        ),
        overlap_with_previous_count=overlap,
        boundary_contiguous_to_previous=bool(previous_timestamps)
        and max(timestamps) + timedelta(minutes=1) == min(previous_timestamps),
    )


def _continuation_key_before_oldest(timestamps: tuple[datetime, ...]) -> str:
    oldest_local = min(timestamps).astimezone(_NEW_YORK)
    return (oldest_local - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")


def _exchange_utc(exchange_date: str, exchange_time: str) -> datetime:
    return datetime.strptime(f"{exchange_date}{exchange_time}", "%Y%m%d%H%M%S").replace(
        tzinfo=_NEW_YORK
    ).astimezone(UTC)


def _require_daily_call_counts(call_counts: KisPaperMarketDataCallCounts) -> None:
    if not isinstance(call_counts, KisPaperMarketDataCallCounts):
        raise ValueError("daily capacity call counts must be typed")
    if not (
        call_counts.token_attempts == 1
        and call_counts.minute_page_attempts == 0
        and 0 <= call_counts.daily_page_attempts <= KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS
    ):
        raise ValueError("daily capacity call counts are not bounded")


def _require_minute_call_counts(call_counts: KisPaperMarketDataCallCounts) -> None:
    if not isinstance(call_counts, KisPaperMarketDataCallCounts):
        raise ValueError("minute capacity call counts must be typed")
    if not (
        call_counts.token_attempts == 1
        and call_counts.daily_page_attempts == 0
        and 0 <= call_counts.minute_page_attempts
        <= KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS
    ):
        raise ValueError("minute capacity call counts are not bounded")


def _require_result_status(status: str, reason: str | None) -> None:
    if status not in {"observed", "rejected"}:
        raise ValueError("capacity map status is invalid")
    if status == "observed" and reason is not None:
        raise ValueError("observed capacity map cannot carry a failure reason")
    if status == "rejected" and reason not in _SAFE_FAILURE_REASONS | {
        "unexpected_capacity_map_error"
    }:
        raise ValueError("capacity map failure reason is invalid")


def _daily_pages_are_ordered(pages: tuple[KisPaperDailyCapacityPage, ...]) -> bool:
    anchor_index = -1
    previous_page_number = 0
    for page in pages:
        current_index = KIS_PAPER_DAILY_CAPACITY_MAP_ANCHORS.index(page.anchor_date)
        if current_index == anchor_index:
            if page.page_number != previous_page_number + 1:
                return False
        elif current_index == anchor_index + 1:
            if page.page_number != 1:
                return False
            anchor_index = current_index
        else:
            return False
        previous_page_number = page.page_number
    return True


def _validated_daily_result(
    result: KisPaperDailyCapacityMapResult,
) -> KisPaperDailyCapacityMapResult:
    if not isinstance(result, KisPaperDailyCapacityMapResult):
        raise TypeError("daily capacity map summary requires a typed result")
    return KisPaperDailyCapacityMapResult(
        observed_at=result.observed_at,
        call_counts=result.call_counts,
        pages=tuple(
            KisPaperDailyCapacityPage(
                anchor_date=page.anchor_date,
                page_number=page.page_number,
                row_count=page.row_count,
                newest_date=page.newest_date,
                oldest_date=page.oldest_date,
                required_ohlcv_fields_present=page.required_ohlcv_fields_present,
                continuation_available=page.continuation_available,
                progressed_older_than_previous=page.progressed_older_than_previous,
            )
            for page in result.pages
        ),
        status=result.status,
        reason=result.reason,
    )


def _validated_minute_result(
    result: KisPaperMinuteCapacityMapResult,
) -> KisPaperMinuteCapacityMapResult:
    if not isinstance(result, KisPaperMinuteCapacityMapResult):
        raise TypeError("minute capacity map summary requires a typed result")
    return KisPaperMinuteCapacityMapResult(
        observed_at=result.observed_at,
        call_counts=result.call_counts,
        pages=tuple(
            KisPaperMinuteCapacityPage(
                page_number=page.page_number,
                row_count=page.row_count,
                newest_utc=page.newest_utc,
                oldest_utc=page.oldest_utc,
                required_ohlcv_fields_present=page.required_ohlcv_fields_present,
                continuation_available=page.continuation_available,
                timestamps_strictly_descending=page.timestamps_strictly_descending,
                timestamps_one_minute_contiguous=page.timestamps_one_minute_contiguous,
                overlap_with_previous_count=page.overlap_with_previous_count,
                boundary_contiguous_to_previous=page.boundary_contiguous_to_previous,
            )
            for page in result.pages
        ),
        status=result.status,
        reason=result.reason,
    )


def _daily_scope() -> dict[str, object]:
    return {
        "symbol": KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL,
        "exchange": KIS_PAPER_HISTORICAL_CAPACITY_MAP_EXCHANGE,
        "endpoint": "overseas_daily",
        "account_or_order_endpoint_called": False,
        "live_endpoint_called": False,
    }


def _minute_scope() -> dict[str, object]:
    return {
        "symbol": KIS_PAPER_HISTORICAL_CAPACITY_MAP_SYMBOL,
        "exchange": KIS_PAPER_HISTORICAL_CAPACITY_MAP_EXCHANGE,
        "endpoint": "overseas_raw_1m",
        "account_or_order_endpoint_called": False,
        "live_endpoint_called": False,
    }


def _call_counts_document(call_counts: KisPaperMarketDataCallCounts) -> dict[str, int]:
    return {
        "token_attempts": call_counts.token_attempts,
        "daily_page_attempts": call_counts.daily_page_attempts,
        "minute_page_attempts": call_counts.minute_page_attempts,
    }


def _daily_page_document(page: KisPaperDailyCapacityPage) -> dict[str, object]:
    return {
        "anchor_date": page.anchor_date,
        "page_number": page.page_number,
        "row_count": page.row_count,
        "date_bounds": {"newest": page.newest_date, "oldest": page.oldest_date},
        "required_ohlcv_fields_present": page.required_ohlcv_fields_present,
        "continuation_available": page.continuation_available,
        "progressed_older_than_previous": page.progressed_older_than_previous,
    }


def _minute_page_document(page: KisPaperMinuteCapacityPage) -> dict[str, object]:
    return {
        "page_number": page.page_number,
        "row_count": page.row_count,
        "timestamp_bounds_utc": {
            "newest": _format_utc(page.newest_utc),
            "oldest": _format_utc(page.oldest_utc),
        },
        "required_ohlcv_fields_present": page.required_ohlcv_fields_present,
        "continuation_available": page.continuation_available,
        "timestamps_strictly_descending": page.timestamps_strictly_descending,
        "timestamps_one_minute_contiguous": page.timestamps_one_minute_contiguous,
        "overlap_with_previous_count": page.overlap_with_previous_count,
        "boundary_contiguous_to_previous": page.boundary_contiguous_to_previous,
    }


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")

"""Bounded private KIS Paper daily cache collection outside the repository."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_market_data import (
    KIS_PAPER_DAILY_MAX_ROWS,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
)
from .kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
)

KIS_PAPER_PRIVATE_DAILY_COLLECTOR_VERSION = "kis-paper-private-daily-collector-v1"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID = "kis-paper-private-daily-collector-v1"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL = "QQQ"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE = "NAS"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_ANCHOR_DATE = "20260717"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS = 2
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS = (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
)
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PROJECTED_BYTES = 1_048_576
KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT = Path("D:/market_data/us_equities/kis_paper_private/daily")

_RAW_DAILY_COLUMNS = (
    "symbol",
    "exchange",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "daily_duplicate_conflict",
        "daily_page_limit_exceeded",
        "daily_response_invalid",
        "daily_response_rejected",
        "pacing_delay_not_met",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
        KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
    }
)


class KisPaperPrivateDailyCollectorError(RuntimeError):
    """A non-secret failure from the private daily collector contract."""


@dataclass(frozen=True)
class KisPaperPrivateDailyCollectionTarget:
    """One bounded daily collection target, including its logical date cursor."""

    symbol: str
    exchange: str
    anchor_date: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "anchor_date", self.anchor_date.strip())
        try:
            KisPaperDailyQuery(
                symbol=self.symbol,
                exchange=self.exchange,
                by_date=self.anchor_date,
            )
        except ValueError as error:
            raise ValueError("private daily collection target is invalid") from error


KIS_PAPER_PRIVATE_DAILY_COLLECTOR_DEFAULT_TARGET = KisPaperPrivateDailyCollectionTarget(
    symbol=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL,
    exchange=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE,
    anchor_date=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_ANCHOR_DATE,
)


@dataclass(frozen=True)
class KisPaperPrivateDailyCollectorPage:
    """Safe page facts retained in a cache manifest."""

    page_number: int
    row_count: int
    newest_date: str | None
    oldest_date: str | None
    continuation_advertised: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not (1 <= self.page_number <= KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS):
            raise ValueError("private daily page number is invalid")
        if not (0 <= self.row_count <= KIS_PAPER_DAILY_MAX_ROWS):
            raise ValueError("private daily page row count is invalid")
        if (self.newest_date is None) != (self.oldest_date is None):
            raise ValueError("private daily page bounds are incomplete")
        for value in (self.newest_date, self.oldest_date):
            if value is not None and (len(value) != 8 or not value.isdigit()):
                raise ValueError("private daily page date is invalid")
        if (
            self.newest_date is not None
            and self.oldest_date is not None
            and self.newest_date < self.oldest_date
        ):
            raise ValueError("private daily page bounds are invalid")
        if not isinstance(self.continuation_advertised, bool):
            raise ValueError("private daily continuation flag is invalid")


@dataclass(frozen=True)
class KisPaperPrivateDailyCollectionResult:
    """One terminal collection attempt, with raw rows held only for D: persistence."""

    observed_at: datetime
    requested_anchor_date: str
    code_revision: str
    call_counts: KisPaperMarketDataCallCounts
    pages: tuple[KisPaperPrivateDailyCollectorPage, ...]
    rows: tuple[KisPaperDailyRawRow, ...]
    dedupe_count: int
    conflicting_duplicate_rows: int
    inter_page_delay_seconds: tuple[float, ...]
    status: Literal["observed", "partial", "rejected"]
    reason: str | None = None
    symbol: str = KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL
    exchange: str = KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "pages", tuple(self.pages))
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "inter_page_delay_seconds", tuple(self.inter_page_delay_seconds))
        try:
            target = KisPaperPrivateDailyCollectionTarget(
                symbol=self.symbol,
                exchange=self.exchange,
                anchor_date=self.requested_anchor_date,
            )
        except ValueError as error:
            raise ValueError("private daily result provenance is invalid") from error
        object.__setattr__(self, "symbol", target.symbol)
        object.__setattr__(self, "exchange", target.exchange)
        object.__setattr__(self, "requested_anchor_date", target.anchor_date)
        if not self.code_revision or "\n" in self.code_revision or len(self.code_revision) > 256:
            raise ValueError("private daily result provenance is invalid")
        if not isinstance(self.call_counts, KisPaperMarketDataCallCounts) or not (
            self.call_counts.token_attempts in {0, 1}
            and self.call_counts.minute_page_attempts == 0
            and 0 <= self.call_counts.daily_page_attempts
            <= KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS
        ):
            raise ValueError("private daily call counts are invalid")
        if not all(isinstance(page, KisPaperPrivateDailyCollectorPage) for page in self.pages):
            raise ValueError("private daily pages are invalid")
        if [page.page_number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("private daily pages are unordered")
        if self.call_counts.daily_page_attempts < len(self.pages):
            raise ValueError("private daily calls cannot trail accepted pages")
        if not all(isinstance(row, KisPaperDailyRawRow) for row in self.rows):
            raise ValueError("private daily rows are invalid")
        if len({row.xymd for row in self.rows}) != len(self.rows):
            raise ValueError("private daily rows are not deduplicated")
        if tuple(row.xymd for row in self.rows) != tuple(
            sorted(row.xymd for row in self.rows)
        ):
            raise ValueError("private daily rows are not chronological")
        if self.dedupe_count < 0 or self.conflicting_duplicate_rows < 0:
            raise ValueError("private daily duplicate facts are invalid")
        if len(self.inter_page_delay_seconds) > 1 or any(
            value < KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS
            for value in self.inter_page_delay_seconds
        ):
            raise ValueError("private daily pacing facts are invalid")
        if self.status not in {"observed", "partial", "rejected"}:
            raise ValueError("private daily result status is invalid")
        if self.status == "observed" and self.reason is not None:
            raise ValueError("observed private daily result cannot have a reason")
        if self.status in {"partial", "rejected"} and self.reason not in _SAFE_FAILURE_REASONS | {
            "unexpected_private_daily_collector_error"
        }:
            raise ValueError("private daily failure reason is invalid")
        if (
            self.call_counts.token_attempts == 0
            and self.call_counts.daily_page_attempts == 0
            and (
                self.status != "rejected"
                or self.reason != KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON
            )
        ):
            raise ValueError("private daily token spacing result is invalid")
        if self.status == "partial" and not _is_recoverable_partial_page(
            pages=self.pages,
            rows=self.rows,
        ):
            raise ValueError("private daily partial result is invalid")

    @property
    def input_row_count(self) -> int:
        return sum(page.row_count for page in self.pages)

    @property
    def stop_outcome(self) -> str:
        if self.status == "partial":
            assert self.reason is not None
            return f"partial_{self.reason}"
        if self.status == "rejected":
            assert self.reason is not None
            return self.reason
        if len(self.pages) == KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS:
            return "two_pages_completed"
        return "source_exhausted"


def run_bounded_kis_paper_private_daily_collection(
    client: KisPaperMarketDataClient,
    *,
    code_revision: str,
    target: KisPaperPrivateDailyCollectionTarget = KIS_PAPER_PRIVATE_DAILY_COLLECTOR_DEFAULT_TARGET,
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> KisPaperPrivateDailyCollectionResult:
    """Collect at most two raw daily pages, with a verified internal pace."""

    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    initial_call_counts = client.call_counts
    pages: list[KisPaperPrivateDailyCollectorPage] = []
    rows_by_date: dict[str, KisPaperDailyRawRow] = {}
    dedupe_count = 0
    conflicting_duplicate_rows = 0
    delays: list[float] = []
    target = KisPaperPrivateDailyCollectionTarget(
        symbol=target.symbol,
        exchange=target.exchange,
        anchor_date=target.anchor_date,
    )
    query = KisPaperDailyQuery(
        symbol=target.symbol,
        exchange=target.exchange,
        by_date=target.anchor_date,
    )
    try:
        client.ensure_authenticated()
        first_page = client.fetch_daily_raw_page(query)
        pages.append(_page_fact(first_page, page_number=1))
        rows_by_date, added_dedupe_count = _merge_daily_rows(rows_by_date, first_page.rows)
        dedupe_count += added_dedupe_count
        if first_page.page.continuation_available and first_page.page.oldest_date is not None:
            delay_started = monotonic_clock()
            sleeper(KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS)
            elapsed = monotonic_clock() - delay_started
            if elapsed < KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS:
                raise KisPaperPrivateDailyCollectorError("pacing_delay_not_met")
            delays.append(elapsed)
            second_page = client.fetch_daily_raw_page(
                KisPaperDailyQuery(
                    symbol=target.symbol,
                    exchange=target.exchange,
                    by_date=first_page.page.oldest_date,
                    continuation="F",
                )
            )
            pages.append(_page_fact(second_page, page_number=2))
            rows_by_date, added_dedupe_count = _merge_daily_rows(rows_by_date, second_page.rows)
            dedupe_count += added_dedupe_count
    except KisPaperPrivateDailyCollectorError as error:
        conflicting_duplicate_rows = 1 if str(error) == "daily_duplicate_conflict" else 0
        return _result(
            observed_at=observed,
            code_revision=code_revision,
            target=target,
            client=client,
            initial_call_counts=initial_call_counts,
            pages=pages,
            rows_by_date=rows_by_date,
            dedupe_count=dedupe_count,
            conflicting_duplicate_rows=conflicting_duplicate_rows,
            delays=delays,
            status=(
                "partial"
                if _is_recoverable_partial_page(pages=pages, rows=tuple(rows_by_date.values()))
                else "rejected"
            ),
            reason=sanitize_kis_paper_private_daily_collector_failure_reason(error),
        )
    except KisPaperMarketDataError as error:
        return _result(
            observed_at=observed,
            code_revision=code_revision,
            target=target,
            client=client,
            initial_call_counts=initial_call_counts,
            pages=pages,
            rows_by_date=rows_by_date,
            dedupe_count=dedupe_count,
            conflicting_duplicate_rows=conflicting_duplicate_rows,
            delays=delays,
            status=(
                "partial"
                if _is_recoverable_partial_page(pages=pages, rows=tuple(rows_by_date.values()))
                else "rejected"
            ),
            reason=sanitize_kis_paper_private_daily_collector_failure_reason(error),
        )
    return _result(
        observed_at=observed,
        code_revision=code_revision,
        target=target,
        client=client,
        initial_call_counts=initial_call_counts,
        pages=pages,
        rows_by_date=rows_by_date,
        dedupe_count=dedupe_count,
        conflicting_duplicate_rows=conflicting_duplicate_rows,
        delays=delays,
        status="observed",
    )


def write_kis_paper_private_daily_cache(
    *,
    result: KisPaperPrivateDailyCollectionResult,
    cache_root: Path,
    run_id: str,
    repo_root: Path,
    backfill_context: Mapping[str, object] | None = None,
) -> tuple[Path, str]:
    """Atomically publish a raw private cache and its manifest on the D: volume."""

    result = _validated_result(result)
    if not run_id or any(character not in "0123456789TZ-" for character in run_id):
        raise ValueError("private daily run_id is invalid")
    root = _external_cache_root(cache_root=cache_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    snapshot_name = (
        f"snapshot={run_id}-{result.symbol.lower()}-{result.exchange.lower()}-modp0-v1"
    )
    target = root / snapshot_name
    if target.exists() or target.is_symlink():
        raise FileExistsError("private daily cache destination already exists")
    staging = root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        raw_document: dict[str, object] | None = None
        if result.rows:
            raw_payload = _compressed_raw_daily_csv(
                result.rows,
                symbol=result.symbol,
                exchange=result.exchange,
            )
            _validate_compressed_raw_daily_csv(
                raw_payload,
                expected_rows=result.rows,
                symbol=result.symbol,
                exchange=result.exchange,
            )
            raw_directory = staging / "raw"
            raw_directory.mkdir()
            raw_path = raw_directory / "ohlcv_daily.csv.gz"
            _write_bytes_and_sync(raw_path, raw_payload)
            raw_document = {
                "path": "raw/ohlcv_daily.csv.gz",
                "sha256": "sha256:" + hashlib.sha256(raw_payload).hexdigest(),
                "size_bytes": len(raw_payload),
                "format": "csv.gz",
                "ordering": "session_date_ascending",
                "columns": list(_RAW_DAILY_COLUMNS),
            }
        manifest = private_daily_cache_manifest(
            result=result,
            snapshot_name=snapshot_name,
            raw_document=raw_document,
            backfill_context=backfill_context,
        )
        manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_bytes_and_sync(staging / "manifest.json", manifest_payload)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target / "manifest.json", "sha256:" + hashlib.sha256(manifest_payload).hexdigest()


def private_daily_cache_manifest(
    *,
    result: KisPaperPrivateDailyCollectionResult,
    snapshot_name: str,
    raw_document: Mapping[str, object] | None,
    backfill_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Render a provenance manifest that deliberately excludes requests and secrets."""

    result = _validated_result(result)
    if not snapshot_name.startswith("snapshot="):
        raise ValueError("private daily snapshot name is invalid")
    newest_date = result.rows[-1].xymd if result.rows else None
    oldest_date = result.rows[0].xymd if result.rows else None
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_daily_cache",
        "dataset_id": f"kis.paper.private.daily.{snapshot_name}",
        "immutable_snapshot": True,
        "collector_objective_id": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID,
        "collector_version": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_VERSION,
        "code_revision": result.code_revision,
        "collected_at_utc": _format_utc(result.observed_at),
        "status": {
            "observed": "completed",
            "partial": "partial",
            "rejected": "rejected",
        }[result.status],
        "completed": result.status == "observed",
        "stop_outcome": result.stop_outcome,
        "source": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "symbol": result.symbol,
            "exchange": result.exchange,
            "adjustment_mode": "MODP=0_unadjusted",
        },
        "requested_date_bounds": {
            "initial_anchor_bymd": result.requested_anchor_date,
            "continuation_cursor_persisted": False,
        },
        "returned_date_bounds": {
            "newest_session_date": _iso_date(newest_date) if newest_date else None,
            "oldest_session_date": _iso_date(oldest_date) if oldest_date else None,
        },
        "requests": {
            "token_attempts": result.call_counts.token_attempts,
            "max_pages": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS,
            "page_attempts": result.call_counts.daily_page_attempts,
            "accepted_pages": len(result.pages),
            "minimum_inter_page_delay_seconds": (
                KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS
            ),
            "observed_inter_page_delay_ms": [
                int(round(delay * 1000)) for delay in result.inter_page_delay_seconds
            ],
        },
        "pages": [_page_document(page) for page in result.pages],
        "deduplication": {
            "key": ["symbol", "exchange", "session_date"],
            "input_row_count": result.input_row_count,
            "unique_row_count": len(result.rows),
            "exact_duplicate_rows_removed": result.dedupe_count,
            "conflicting_duplicate_rows": result.conflicting_duplicate_rows,
            "conflict_policy": "reject_snapshot",
        },
        "files": {"raw_daily_rows": dict(raw_document) if raw_document is not None else None},
        "storage": {
            "root": "D:\\market_data",
            "private_local_only": True,
            "served": False,
            "redistributed": False,
        },
        "redaction": {
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "request_headers_persisted": False,
            "continuation_cursors_persisted": False,
            "response_bodies_persisted": False,
        },
    }
    if backfill_context is not None:
        manifest["backfill"] = _validated_backfill_context(backfill_context, result=result)
    return manifest


def private_daily_cache_would_cross_free_space_floor(
    *,
    cache_root: Path,
    repo_root: Path,
    projected_bytes: int = KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PROJECTED_BYTES,
) -> bool:
    """Keep a small collector from crossing the project-wide 15 percent D: floor."""

    if projected_bytes < 0:
        raise ValueError("private daily projected bytes are invalid")
    path = _external_cache_root(cache_root=cache_root, repo_root=repo_root)
    while not path.exists():
        parent = path.parent
        if parent == path:
            raise ValueError("private daily cache root is unavailable")
        path = parent
    usage = shutil.disk_usage(path)
    return usage.free - projected_bytes < usage.total * 0.15


def sanitize_kis_paper_private_daily_collector_failure_reason(value: BaseException | str) -> str:
    """Exclude server and transport details from manifests and control state."""

    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_private_daily_collector_error"


def _result(
    *,
    observed_at: datetime,
    code_revision: str,
    target: KisPaperPrivateDailyCollectionTarget,
    client: KisPaperMarketDataClient,
    initial_call_counts: KisPaperMarketDataCallCounts,
    pages: list[KisPaperPrivateDailyCollectorPage],
    rows_by_date: Mapping[str, KisPaperDailyRawRow],
    dedupe_count: int,
    conflicting_duplicate_rows: int,
    delays: list[float],
    status: Literal["observed", "partial", "rejected"],
    reason: str | None = None,
) -> KisPaperPrivateDailyCollectionResult:
    return KisPaperPrivateDailyCollectionResult(
        observed_at=observed_at,
        requested_anchor_date=target.anchor_date,
        code_revision=code_revision,
        call_counts=_call_count_delta(
            initial=initial_call_counts,
            final=client.call_counts,
        ),
        pages=tuple(pages),
        rows=tuple(rows_by_date[key] for key in sorted(rows_by_date)),
        dedupe_count=dedupe_count,
        conflicting_duplicate_rows=conflicting_duplicate_rows,
        inter_page_delay_seconds=tuple(delays),
        status=status,
        reason=reason,
        symbol=target.symbol,
        exchange=target.exchange,
    )


def _call_count_delta(
    *,
    initial: KisPaperMarketDataCallCounts,
    final: KisPaperMarketDataCallCounts,
) -> KisPaperMarketDataCallCounts:
    """Describe only calls made by this bounded collection on a reused client."""

    token_attempts = final.token_attempts - initial.token_attempts
    minute_page_attempts = final.minute_page_attempts - initial.minute_page_attempts
    daily_page_attempts = final.daily_page_attempts - initial.daily_page_attempts
    if min(token_attempts, minute_page_attempts, daily_page_attempts) < 0:
        raise ValueError("private daily client call counts regressed")
    return KisPaperMarketDataCallCounts(
        token_attempts=token_attempts,
        minute_page_attempts=minute_page_attempts,
        daily_page_attempts=daily_page_attempts,
    )


def _is_recoverable_partial_page(
    *,
    pages: tuple[KisPaperPrivateDailyCollectorPage, ...] | list[KisPaperPrivateDailyCollectorPage],
    rows: tuple[KisPaperDailyRawRow, ...],
) -> bool:
    """Keep one fully validated first page when only its continuation failed."""

    return (
        len(pages) == 1
        and pages[0].continuation_advertised
        and pages[0].row_count > 0
        and len(rows) == pages[0].row_count
    )


def _page_fact(
    raw_page: KisPaperDailyRawPage,
    *,
    page_number: int,
) -> KisPaperPrivateDailyCollectorPage:
    return KisPaperPrivateDailyCollectorPage(
        page_number=page_number,
        row_count=raw_page.page.row_count,
        newest_date=raw_page.page.newest_date,
        oldest_date=raw_page.page.oldest_date,
        continuation_advertised=raw_page.page.continuation_available,
    )


def _merge_daily_rows(
    existing: Mapping[str, KisPaperDailyRawRow],
    incoming: tuple[KisPaperDailyRawRow, ...],
) -> tuple[dict[str, KisPaperDailyRawRow], int]:
    merged = dict(existing)
    duplicate_count = 0
    for row in incoming:
        prior = merged.get(row.xymd)
        if prior is None:
            merged[row.xymd] = row
            continue
        if prior != row:
            raise KisPaperPrivateDailyCollectorError("daily_duplicate_conflict")
        duplicate_count += 1
    return merged, duplicate_count


def _validated_result(
    result: KisPaperPrivateDailyCollectionResult,
) -> KisPaperPrivateDailyCollectionResult:
    if not isinstance(result, KisPaperPrivateDailyCollectionResult):
        raise TypeError("private daily cache requires a typed result")
    return KisPaperPrivateDailyCollectionResult(
        observed_at=result.observed_at,
        requested_anchor_date=result.requested_anchor_date,
        code_revision=result.code_revision,
        call_counts=result.call_counts,
        pages=tuple(result.pages),
        rows=tuple(result.rows),
        dedupe_count=result.dedupe_count,
        conflicting_duplicate_rows=result.conflicting_duplicate_rows,
        inter_page_delay_seconds=tuple(result.inter_page_delay_seconds),
        status=result.status,
        reason=result.reason,
        symbol=result.symbol,
        exchange=result.exchange,
    )


def _compressed_raw_daily_csv(
    rows: tuple[KisPaperDailyRawRow, ...],
    *,
    symbol: str,
    exchange: str,
) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=_RAW_DAILY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "symbol": symbol,
                "exchange": exchange,
                "session_date": _iso_date(row.xymd),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.clos,
                "volume": row.tvol,
            }
        )
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as handle:
        handle.write(text.getvalue().encode("utf-8"))
    return compressed.getvalue()


def _validate_compressed_raw_daily_csv(
    payload: bytes,
    *,
    expected_rows: tuple[KisPaperDailyRawRow, ...],
    symbol: str,
    exchange: str,
) -> None:
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
        decoded = handle.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if tuple(reader.fieldnames or ()) != _RAW_DAILY_COLUMNS:
        raise ValueError("private daily raw schema is invalid")
    rows = list(reader)
    if len(rows) != len(expected_rows):
        raise ValueError("private daily raw row count is invalid")
    dates = [row["session_date"] for row in rows]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("private daily raw ordering is invalid")
    for document, expected in zip(rows, expected_rows, strict=True):
        if document != {
            "symbol": symbol,
            "exchange": exchange,
            "session_date": _iso_date(expected.xymd),
            "open": expected.open,
            "high": expected.high,
            "low": expected.low,
            "close": expected.clos,
            "volume": expected.tvol,
        }:
            raise ValueError("private daily raw contents are invalid")


def _validated_backfill_context(
    context: Mapping[str, object],
    *,
    result: KisPaperPrivateDailyCollectionResult,
) -> dict[str, object]:
    expected_keys = {
        "contract_version",
        "cursor_strategy",
        "input_cursor_date",
        "logical_cursor_persisted",
        "output_cursor_date",
        "target_key",
    }
    document = dict(context)
    if set(document) != expected_keys:
        raise ValueError("private daily backfill context is invalid")
    if (
        not isinstance(document["contract_version"], str)
        or not document["contract_version"]
        or document["target_key"] != f"{result.symbol}/{result.exchange}/MODP=0"
        or document["cursor_strategy"] != "oldest_session_date_with_exact_overlap"
        or document["input_cursor_date"] != result.requested_anchor_date
        or not isinstance(document["logical_cursor_persisted"], bool)
    ):
        raise ValueError("private daily backfill context is invalid")
    output_cursor = document["output_cursor_date"]
    if output_cursor is not None and (
        not isinstance(output_cursor, str) or len(output_cursor) != 8 or not output_cursor.isdigit()
    ):
        raise ValueError("private daily backfill context is invalid")
    expected_output_cursor = (
        result.rows[0].xymd if result.status in {"observed", "partial"} and result.rows else None
    )
    if output_cursor != expected_output_cursor:
        raise ValueError("private daily backfill context is invalid")
    return document


def _page_document(page: KisPaperPrivateDailyCollectorPage) -> dict[str, object]:
    return {
        "index": page.page_number,
        "outcome": "accepted",
        "row_count": page.row_count,
        "newest_session_date": _iso_date(page.newest_date) if page.newest_date else None,
        "oldest_session_date": _iso_date(page.oldest_date) if page.oldest_date else None,
        "continuation_advertised": page.continuation_advertised,
    }


def _external_cache_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = Path(cache_root).resolve()
    repository = Path(repo_root).resolve()
    mounted_root = repository / "market_data"
    mounted_market_data = mounted_root.is_mount() and root.is_relative_to(mounted_root)
    if root.is_relative_to(repository) and not mounted_market_data:
        raise ValueError("private daily cache root must stay outside Git")
    return root


def _write_bytes_and_sync(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")


def _iso_date(value: str) -> str:
    if len(value) != 8 or not value.isdigit():
        raise ValueError("private daily date is invalid")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"

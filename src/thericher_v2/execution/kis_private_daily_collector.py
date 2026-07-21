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

KIS_PAPER_PRIVATE_DAILY_COLLECTOR_VERSION = "kis-paper-private-daily-collector-v1"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID = "kis-paper-private-daily-collector-v1"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL = "QQQ"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE = "NAS"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_ANCHOR_DATE = "20260717"
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PAGE_ATTEMPTS = 2
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MIN_PAGE_INTERVAL_SECONDS = 2.0
KIS_PAPER_PRIVATE_DAILY_COLLECTOR_MAX_PROJECTED_BYTES = 1_048_576
KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT = Path("D:/market_data/us_equities/kis_paper_private/daily")
KIS_PAPER_PRIVATE_DAILY_CONTROL_ROOT = Path("D:/thericher-v2/model-artifacts/_control")

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
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
    }
)


class KisPaperPrivateDailyCollectorError(RuntimeError):
    """A non-secret failure from the private daily collector contract."""


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
    status: Literal["observed", "rejected"]
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "pages", tuple(self.pages))
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "inter_page_delay_seconds", tuple(self.inter_page_delay_seconds))
        if (
            self.requested_anchor_date != KIS_PAPER_PRIVATE_DAILY_COLLECTOR_ANCHOR_DATE
            or not self.code_revision
            or "\n" in self.code_revision
            or len(self.code_revision) > 256
        ):
            raise ValueError("private daily result provenance is invalid")
        if not isinstance(self.call_counts, KisPaperMarketDataCallCounts) or not (
            self.call_counts.token_attempts == 1
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
        if self.status not in {"observed", "rejected"}:
            raise ValueError("private daily result status is invalid")
        if self.status == "observed" and self.reason is not None:
            raise ValueError("observed private daily result cannot have a reason")
        if self.status == "rejected" and self.reason not in _SAFE_FAILURE_REASONS | {
            "unexpected_private_daily_collector_error"
        }:
            raise ValueError("private daily failure reason is invalid")

    @property
    def input_row_count(self) -> int:
        return sum(page.row_count for page in self.pages)

    @property
    def stop_outcome(self) -> str:
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
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> KisPaperPrivateDailyCollectionResult:
    """Collect at most two raw daily pages, with a verified internal pace."""

    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    pages: list[KisPaperPrivateDailyCollectorPage] = []
    rows_by_date: dict[str, KisPaperDailyRawRow] = {}
    dedupe_count = 0
    conflicting_duplicate_rows = 0
    delays: list[float] = []
    query = KisPaperDailyQuery(
        symbol=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL,
        by_date=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_ANCHOR_DATE,
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
                    symbol=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL,
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
            client=client,
            pages=pages,
            rows_by_date=rows_by_date,
            dedupe_count=dedupe_count,
            conflicting_duplicate_rows=conflicting_duplicate_rows,
            delays=delays,
            status="rejected",
            reason=sanitize_kis_paper_private_daily_collector_failure_reason(error),
        )
    except KisPaperMarketDataError as error:
        return _result(
            observed_at=observed,
            code_revision=code_revision,
            client=client,
            pages=pages,
            rows_by_date=rows_by_date,
            dedupe_count=dedupe_count,
            conflicting_duplicate_rows=conflicting_duplicate_rows,
            delays=delays,
            status="rejected",
            reason=sanitize_kis_paper_private_daily_collector_failure_reason(error),
        )
    return _result(
        observed_at=observed,
        code_revision=code_revision,
        client=client,
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
) -> tuple[Path, str]:
    """Atomically publish a raw private cache and its manifest on the D: volume."""

    result = _validated_result(result)
    if not run_id or any(character not in "0123456789TZ-" for character in run_id):
        raise ValueError("private daily run_id is invalid")
    root = _external_cache_root(cache_root=cache_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    snapshot_name = f"snapshot={run_id}-qqq-nas-modp0-v1"
    target = root / snapshot_name
    if target.exists() or target.is_symlink():
        raise FileExistsError("private daily cache destination already exists")
    staging = root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        raw_document: dict[str, object] | None = None
        if result.rows:
            raw_payload = _compressed_raw_daily_csv(result.rows)
            _validate_compressed_raw_daily_csv(raw_payload, expected_rows=result.rows)
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
) -> dict[str, object]:
    """Render a provenance manifest that deliberately excludes requests and secrets."""

    result = _validated_result(result)
    if not snapshot_name.startswith("snapshot="):
        raise ValueError("private daily snapshot name is invalid")
    newest_date = result.rows[-1].xymd if result.rows else None
    oldest_date = result.rows[0].xymd if result.rows else None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_daily_cache",
        "dataset_id": f"kis.paper.private.daily.{snapshot_name}",
        "immutable_snapshot": True,
        "collector_objective_id": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID,
        "collector_version": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_VERSION,
        "code_revision": result.code_revision,
        "collected_at_utc": _format_utc(result.observed_at),
        "status": "completed" if result.status == "observed" else "rejected",
        "completed": result.status == "observed",
        "stop_outcome": result.stop_outcome,
        "source": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "symbol": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL,
            "exchange": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE,
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


def private_daily_collector_recovery_state(
    *,
    control_root: Path,
    repo_root: Path,
) -> Literal["restart", "reconcile", "complete"]:
    """Classify a fresh, in-progress, or terminal collector without loading credentials."""

    marker = _private_daily_marker(control_root=control_root, repo_root=repo_root)
    ledger_events = _private_daily_ledger_events(control_root=control_root, repo_root=repo_root)
    if not marker.exists() and not ledger_events:
        return "restart"
    if marker.is_symlink():
        raise ValueError("private_daily_control_invalid")
    if not marker.exists():
        return "reconcile"
    document = _read_private_daily_marker(marker)
    if document.get("phase") == "completed":
        return "complete"
    if document.get("phase") in {"reserved", "network_started"}:
        return "reconcile"
    raise ValueError("private_daily_control_invalid")


def private_daily_collector_attempt_is_reserved(
    *,
    control_root: Path,
    repo_root: Path,
) -> bool:
    return private_daily_collector_recovery_state(
        control_root=control_root,
        repo_root=repo_root,
    ) != "restart"


def reserve_private_daily_collector_attempt(
    *,
    control_root: Path,
    repo_root: Path,
    observed_at: datetime,
) -> Path:
    """Durably reserve the raw-data collector before its token call."""

    if private_daily_collector_attempt_is_reserved(
        control_root=control_root,
        repo_root=repo_root,
    ):
        raise ValueError("private_daily_attempt_already_reserved")
    marker = _private_daily_marker(control_root=control_root, repo_root=repo_root)
    reserved_at = require_utc(observed_at, "observed_at")
    payload = _private_daily_control_payload(
        phase="reserved",
        reserved_at=reserved_at,
        updated_at=reserved_at,
        raw_market_data_retained=False,
        recovery="reconcile",
    )
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as error:
        raise ValueError("private_daily_attempt_already_reserved") from error
    except OSError as error:
        raise ValueError("private_daily_control_write_failed") from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise ValueError("private_daily_control_write_failed") from error
    _append_private_daily_ledger(
        control_root=control_root,
        repo_root=repo_root,
        phase="reserved",
        reserved_at=reserved_at,
        updated_at=reserved_at,
        raw_market_data_retained=False,
        recovery="reconcile",
    )
    return marker


def mark_private_daily_collector_network_started(
    *,
    control_root: Path,
    repo_root: Path,
    observed_at: datetime,
) -> Path:
    return _transition_private_daily_collector(
        control_root=control_root,
        repo_root=repo_root,
        phase="network_started",
        observed_at=observed_at,
        allowed_predecessors=frozenset({"reserved"}),
        raw_market_data_retained=False,
        recovery="reconcile",
    )


def mark_private_daily_collector_completed(
    *,
    control_root: Path,
    repo_root: Path,
    observed_at: datetime,
    manifest_hash: str,
    manifest_path: Path,
    result: KisPaperPrivateDailyCollectionResult,
) -> Path:
    if not manifest_hash.startswith("sha256:"):
        raise ValueError("private_daily_control_write_failed")
    result = _validated_result(result)
    return _transition_private_daily_collector(
        control_root=control_root,
        repo_root=repo_root,
        phase="completed",
        observed_at=observed_at,
        allowed_predecessors=frozenset({"network_started"}),
        raw_market_data_retained=bool(result.rows),
        recovery="complete",
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        result_status="completed" if result.status == "observed" else "rejected",
    )


def sanitize_kis_paper_private_daily_collector_failure_reason(value: BaseException | str) -> str:
    """Exclude server and transport details from manifests and control state."""

    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_private_daily_collector_error"


def _result(
    *,
    observed_at: datetime,
    code_revision: str,
    client: KisPaperMarketDataClient,
    pages: list[KisPaperPrivateDailyCollectorPage],
    rows_by_date: Mapping[str, KisPaperDailyRawRow],
    dedupe_count: int,
    conflicting_duplicate_rows: int,
    delays: list[float],
    status: Literal["observed", "rejected"],
    reason: str | None = None,
) -> KisPaperPrivateDailyCollectionResult:
    return KisPaperPrivateDailyCollectionResult(
        observed_at=observed_at,
        requested_anchor_date=KIS_PAPER_PRIVATE_DAILY_COLLECTOR_ANCHOR_DATE,
        code_revision=code_revision,
        call_counts=client.call_counts,
        pages=tuple(pages),
        rows=tuple(rows_by_date[key] for key in sorted(rows_by_date)),
        dedupe_count=dedupe_count,
        conflicting_duplicate_rows=conflicting_duplicate_rows,
        inter_page_delay_seconds=tuple(delays),
        status=status,
        reason=reason,
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
    )


def _compressed_raw_daily_csv(rows: tuple[KisPaperDailyRawRow, ...]) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=_RAW_DAILY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "symbol": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL,
                "exchange": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE,
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
            "symbol": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_SYMBOL,
            "exchange": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_EXCHANGE,
            "session_date": _iso_date(expected.xymd),
            "open": expected.open,
            "high": expected.high,
            "low": expected.low,
            "close": expected.clos,
            "volume": expected.tvol,
        }:
            raise ValueError("private daily raw contents are invalid")


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
    if root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("private daily cache root must stay outside Git")
    return root


def _private_daily_marker(*, control_root: Path, repo_root: Path) -> Path:
    root = _external_control_root(control_root=control_root, repo_root=repo_root)
    reservations = _external_control_child(
        root=root,
        child_name="reservations",
        repo_root=repo_root,
    )
    return reservations / f"{KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID}.json"


def _external_control_root(*, control_root: Path, repo_root: Path) -> Path:
    root = _external_cache_root(cache_root=control_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    return _external_cache_root(cache_root=root, repo_root=repo_root)


def _external_control_child(*, root: Path, child_name: str, repo_root: Path) -> Path:
    child = root / child_name
    if child.is_symlink():
        raise ValueError("private_daily_control_invalid")
    child.mkdir(exist_ok=True)
    resolved_child = child.resolve()
    if not (
        resolved_child.is_relative_to(root)
        and not resolved_child.is_relative_to(Path(repo_root).resolve())
    ):
        raise ValueError("private_daily_control_invalid")
    return resolved_child


def _private_daily_ledger_events(
    *,
    control_root: Path,
    repo_root: Path,
) -> tuple[dict[str, object], ...]:
    root = _external_control_root(control_root=control_root, repo_root=repo_root)
    ledger = _external_control_child(root=root, child_name="ledger", repo_root=repo_root)
    events: list[dict[str, object]] = []
    for path in sorted(ledger.glob("*.jsonl")):
        if path.is_symlink():
            raise ValueError("private_daily_control_invalid")
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                document = json.loads(line)
                if not isinstance(document, dict):
                    raise ValueError("private_daily_control_invalid")
                if (
                    document.get("kind") == "kis_paper_private_daily_collector_attempt"
                    and document.get("objective_id")
                    == KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID
                ):
                    events.append(document)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            if isinstance(error, ValueError) and str(error) == "private_daily_control_invalid":
                raise
            raise ValueError("private_daily_control_invalid") from error
    return tuple(events)


def _read_private_daily_marker(marker: Path) -> dict[str, object]:
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private_daily_control_invalid") from error
    if (
        not isinstance(document, dict)
        or document.get("kind") != "kis_paper_private_daily_collector_attempt_marker"
        or document.get("objective_id") != KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID
    ):
        raise ValueError("private_daily_control_invalid")
    return document


def _private_daily_control_payload(
    *,
    phase: Literal["reserved", "network_started", "completed"],
    reserved_at: datetime,
    updated_at: datetime,
    raw_market_data_retained: bool,
    recovery: Literal["reconcile", "complete"],
    manifest_hash: str | None = None,
    manifest_path: Path | None = None,
    result_status: Literal["completed", "rejected"] | None = None,
) -> bytes:
    document = _private_daily_control_document(
        phase=phase,
        reserved_at=reserved_at,
        updated_at=updated_at,
        raw_market_data_retained=raw_market_data_retained,
        recovery=recovery,
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        result_status=result_status,
    )
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _private_daily_control_document(
    *,
    phase: Literal["reserved", "network_started", "completed"],
    reserved_at: datetime,
    updated_at: datetime,
    raw_market_data_retained: bool,
    recovery: Literal["reconcile", "complete"],
    manifest_hash: str | None = None,
    manifest_path: Path | None = None,
    result_status: Literal["completed", "rejected"] | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_daily_collector_attempt_marker",
        "objective_id": KIS_PAPER_PRIVATE_DAILY_COLLECTOR_OBJECTIVE_ID,
        "phase": phase,
        "reserved_at_utc": _format_utc(require_utc(reserved_at, "reserved_at")),
        "updated_at_utc": _format_utc(require_utc(updated_at, "updated_at")),
        "raw_market_data_retained": raw_market_data_retained,
        "recovery": recovery,
    }
    if manifest_hash is not None:
        document["manifest_hash"] = manifest_hash
    if manifest_path is not None:
        document["manifest_path"] = str(manifest_path)
    if result_status is not None:
        document["result_status"] = result_status
    return document


def _append_private_daily_ledger(
    *,
    control_root: Path,
    repo_root: Path,
    phase: Literal["reserved", "network_started", "completed"],
    reserved_at: datetime,
    updated_at: datetime,
    raw_market_data_retained: bool,
    recovery: Literal["reconcile", "complete"],
    manifest_hash: str | None = None,
    manifest_path: Path | None = None,
    result_status: Literal["completed", "rejected"] | None = None,
) -> None:
    root = _external_control_root(control_root=control_root, repo_root=repo_root)
    ledger = _external_control_child(root=root, child_name="ledger", repo_root=repo_root)
    timestamp = require_utc(updated_at, "updated_at")
    path = ledger / f"{timestamp:%Y-%m}.jsonl"
    if path.is_symlink():
        raise ValueError("private_daily_control_invalid")
    document = _private_daily_control_document(
        phase=phase,
        reserved_at=reserved_at,
        updated_at=timestamp,
        raw_market_data_retained=raw_market_data_retained,
        recovery=recovery,
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        result_status=result_status,
    )
    document["kind"] = "kis_paper_private_daily_collector_attempt"
    payload = (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")
    try:
        with path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise ValueError("private_daily_control_write_failed") from error


def _transition_private_daily_collector(
    *,
    control_root: Path,
    repo_root: Path,
    phase: Literal["network_started", "completed"],
    observed_at: datetime,
    allowed_predecessors: frozenset[str],
    raw_market_data_retained: bool,
    recovery: Literal["reconcile", "complete"],
    manifest_hash: str | None = None,
    manifest_path: Path | None = None,
    result_status: Literal["completed", "rejected"] | None = None,
) -> Path:
    marker = _private_daily_marker(control_root=control_root, repo_root=repo_root)
    if marker.is_symlink():
        raise ValueError("private_daily_control_invalid")
    document = _read_private_daily_marker(marker)
    if document.get("phase") not in allowed_predecessors:
        raise ValueError("private_daily_control_invalid")
    try:
        reserved_at = require_utc(
            datetime.fromisoformat(str(document["reserved_at_utc"]).replace("Z", "+00:00")),
            "reserved_at",
        )
        prior_updated_at = require_utc(
            datetime.fromisoformat(str(document["updated_at_utc"]).replace("Z", "+00:00")),
            "updated_at",
        )
        updated_at = require_utc(observed_at, "observed_at")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("private_daily_control_invalid") from error
    if updated_at < prior_updated_at or prior_updated_at < reserved_at:
        raise ValueError("private_daily_control_invalid")
    payload = _private_daily_control_payload(
        phase=phase,
        reserved_at=reserved_at,
        updated_at=updated_at,
        raw_market_data_retained=raw_market_data_retained,
        recovery=recovery,
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        result_status=result_status,
    )
    staging = marker.with_name(f".{marker.name}.{uuid.uuid4().hex}.stage")
    try:
        _write_bytes_and_sync(staging, payload)
        os.replace(staging, marker)
    finally:
        if staging.exists():
            staging.unlink()
    _append_private_daily_ledger(
        control_root=control_root,
        repo_root=repo_root,
        phase=phase,
        reserved_at=reserved_at,
        updated_at=updated_at,
        raw_market_data_retained=raw_market_data_retained,
        recovery=recovery,
        manifest_hash=manifest_hash,
        manifest_path=manifest_path,
        result_status=result_status,
    )
    return marker


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

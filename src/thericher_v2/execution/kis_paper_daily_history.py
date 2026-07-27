"""Resumable KIS Paper daily-history collection for one fixed NAS basket.

The collector owns a new cache root and never reads the older capability probe,
frozen panel, or ETF catalog. Raw OHLCV stays in the cache; public run results
and external receipts carry only source-safe progress facts.
"""

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Literal
from urllib.parse import urlsplit

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.official_symbol_directory_nas_probe import (
    NAS_COMMON_STOCK_PROBE_SYMBOLS,
    NAS_EXCHANGE,
)

from .kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
)
from .kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from .kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectionTarget,
    KisPaperPrivateDailyCollectorError,
    KisPaperPrivateDailyCollectorPage,
    private_daily_cache_would_cross_free_space_floor,
    sanitize_kis_paper_private_daily_collector_failure_reason,
    write_kis_paper_private_daily_cache,
)

KIS_PAPER_DAILY_HISTORY_VERSION = "kis-paper-daily-nas-history-v1"
KIS_PAPER_DAILY_HISTORY_OBJECTIVE_ID = "kis-paper-daily-nas-history-v1"
KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE = "20260724"
KIS_PAPER_DAILY_HISTORY_TERMINAL_DATE = "19900101"
KIS_PAPER_DAILY_HISTORY_MAX_PAGES_PER_CHUNK = 2
KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_CHUNKS = 288
KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_RUNTIME = timedelta(minutes=30)
KIS_PAPER_DAILY_HISTORY_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-history/v1"
)
KIS_PAPER_DAILY_HISTORY_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-history-v1"
)
KIS_PAPER_DAILY_HISTORY_INDEX_FILENAME = "index.json"
KIS_PAPER_DAILY_HISTORY_LOCK_FILENAME = "worker.lock"

# These identities are the completed fixed six-symbol probe's source-safe
# provenance. They bind scope; they do not make this current listing a PIT set.
KIS_PAPER_DAILY_HISTORY_REGISTRY_VERSION = "official-symbol-directory-nas-probe-r1"
KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256 = (
    "sha256:58c894236425755cb18c60a576944e33f88f9c6221e75405d6de5b4a6fa27935"
)
KIS_PAPER_DAILY_HISTORY_SOURCE_MANIFEST_SHA256 = (
    "sha256:129e6aa02a27e8760139a901f13e2ee4e3fc9b5d4a3e615f9dcd431154aecea4"
)
KIS_PAPER_DAILY_HISTORY_SOURCE_FILE_SHA256 = (
    "sha256:cf9f42bbff4cdcec0335c5acf42c1ffe889039b5f1e48f60374120045513f6bb"
)

_TARGET_KEYS = tuple(f"{symbol}/{NAS_EXCHANGE}" for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS)
_DEFERRED_RECOVERY_TARGET_REASONS = {
    "MSFT/NAS": "daily_response_invalid",
    "NVDA/NAS": "transport_failure",
}
_DEFERRED_RECOVERY_TARGET_KEYS = tuple(_DEFERRED_RECOVERY_TARGET_REASONS)
KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES = {
    symbol: frozenset({NAS_EXCHANGE}) for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS
}
_TARGET_STATES = frozenset({"ready", "deferred", "source_limited", "complete"})
_RAW_COLUMNS = (
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
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
        "token_request_not_due",
        "unexpected_private_daily_collector_error",
        "no_cursor_progress",
        "cross_chunk_duplicate_conflict",
        "empty_daily_response",
    }
)


class KisPaperDailyHistoryError(RuntimeError):
    """A non-secret failure from the fixed-basket history collector."""


class UrllibKisPaperDailyHistoryTransport(UrllibKisPaperMarketDataTransport):
    """Allow only a virtual Paper token and fixed six-symbol NAS daily requests."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        request_gate: KisPaperMarketDataRateGate | None = None,
        token_start_gate: KisPaperMarketDataTokenStartGate | None = None,
    ) -> None:
        super().__init__(
            timeout_seconds=timeout_seconds,
            request_gate=request_gate,
            token_start_gate=token_start_gate,
        )
        self._daily_symbol_exchanges = KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        if request.method == "GET" and urlsplit(request.url).path != KIS_PAPER_DAILY_PATH:
            raise KisPaperMarketDataError("request_not_allowlisted")
        return self._request_with_daily_symbol_exchanges(
            request,
            daily_symbol_exchanges=self._daily_symbol_exchanges,
        )


@dataclass(frozen=True)
class KisPaperDailyHistoryTargetState:
    """Safe current projection for one fixed-symbol durable cursor."""

    target_key: str
    state: Literal["ready", "deferred", "source_limited", "complete"]
    cursor_date: str
    accepted_page_count: int
    categorical_failure_count: int
    coverage_bucket: str | None
    last_reason: str | None

    def __post_init__(self) -> None:
        if self.target_key not in _TARGET_KEYS or self.state not in _TARGET_STATES:
            raise ValueError("daily history target state is invalid")
        if not _is_date(self.cursor_date):
            raise ValueError("daily history cursor is invalid")
        if self.accepted_page_count < 0 or self.categorical_failure_count < 0:
            raise ValueError("daily history counters are invalid")
        if self.coverage_bucket is not None and not _is_coverage_bucket(self.coverage_bucket):
            raise ValueError("daily history coverage bucket is invalid")
        if self.last_reason is not None and self.last_reason not in _SAFE_FAILURE_REASONS:
            raise ValueError("daily history reason is invalid")

    def source_safe_document(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "state": self.state,
            "cursor_date": self.cursor_date,
            "coverage_bucket": self.coverage_bucket,
            "accepted_page_count": self.accepted_page_count,
            "categorical_failure_count": self.categorical_failure_count,
            "last_reason": self.last_reason,
        }


@dataclass(frozen=True)
class KisPaperDailyHistoryRun:
    """Source-safe outcome of one bounded worker cycle."""

    status: Literal[
        "collected",
        "complete",
        "deferred",
        "busy",
        "storage_floor_would_be_crossed",
    ]
    observed_at: datetime
    completed_at: datetime
    target_states: tuple[KisPaperDailyHistoryTargetState, ...]
    accepted_page_count: int
    categorical_failure_count: int
    chunk_attempt_count: int
    measured_accepted_pages_per_minute: float | None
    remaining_page_estimate: int | None
    eta_bucket: str
    next_due: datetime | None
    recovery: Literal["resume", "complete", "restart", "reconcile"]
    registry_sha256: str = KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256
    evidence_sha256: str | None = None
    recovery_target_keys: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "completed_at", require_utc(self.completed_at, "completed_at"))
        object.__setattr__(self, "target_states", tuple(self.target_states))
        object.__setattr__(self, "recovery_target_keys", tuple(self.recovery_target_keys))
        if (
            self.status
            not in {
                "collected",
                "complete",
                "deferred",
                "busy",
                "storage_floor_would_be_crossed",
            }
            or tuple(state.target_key for state in self.target_states) != _TARGET_KEYS
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
            or self.chunk_attempt_count < 0
            or self.remaining_page_estimate is not None
            or self.eta_bucket != "unknown"
            or self.recovery not in {"resume", "complete", "restart", "reconcile"}
            or self.registry_sha256 != KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256
            or self.recovery_target_keys not in ((), _DEFERRED_RECOVERY_TARGET_KEYS)
        ):
            raise ValueError("daily history run is invalid")
        if self.measured_accepted_pages_per_minute is not None and (
            self.measured_accepted_pages_per_minute < 0
        ):
            raise ValueError("daily history pace is invalid")
        if self.next_due is not None:
            object.__setattr__(self, "next_due", require_utc(self.next_due, "next_due"))
        if self.evidence_sha256 is not None and not _is_sha256(self.evidence_sha256):
            raise ValueError("daily history evidence hash is invalid")

    def source_safe_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_nas_history_receipt",
            "scope": {
                "provider": "KIS Open API virtual paper",
                "endpoint": "dailyprice",
                "mode": "off",
                "target_keys": list(_TARGET_KEYS),
                "recovery_target_keys": list(self.recovery_target_keys),
                "registry_version": KIS_PAPER_DAILY_HISTORY_REGISTRY_VERSION,
                "registry_sha256": self.registry_sha256,
                "source_manifest_sha256": KIS_PAPER_DAILY_HISTORY_SOURCE_MANIFEST_SHA256,
                "source_file_sha256": KIS_PAPER_DAILY_HISTORY_SOURCE_FILE_SHA256,
                "prospective_only": True,
                "historical_point_in_time_eligible": False,
            },
            "observed_at_utc": _format_utc(self.observed_at),
            "completed_at_utc": _format_utc(self.completed_at),
            "outcome": {
                "status": self.status,
                "recovery": self.recovery,
                "chunk_attempt_count": self.chunk_attempt_count,
                "accepted_page_count": self.accepted_page_count,
                "categorical_failure_count": self.categorical_failure_count,
                "measured_accepted_pages_per_minute": self.measured_accepted_pages_per_minute,
                "remaining_page_estimate": self.remaining_page_estimate,
                "eta_bucket": self.eta_bucket,
                "next_due_utc": None if self.next_due is None else _format_utc(self.next_due),
            },
            "targets": [state.source_safe_document() for state in self.target_states],
            "route_isolation": {
                "account_endpoints_used": False,
                "position_endpoints_used": False,
                "open_order_endpoints_used": False,
                "quote_endpoints_used": False,
                "order_endpoints_used": False,
                "live_endpoints_used": False,
                "tiingo_used": False,
            },
            "artifact_policy": {
                "raw_market_data_in_receipt": False,
                "credentials_in_receipt": False,
                "account_data_in_receipt": False,
                "request_headers_in_receipt": False,
                "broker_response_bodies_in_receipt": False,
                "repo_storage_allowed": False,
            },
        }


@dataclass(frozen=True)
class _Snapshot:
    target_key: str
    input_cursor_date: str
    output_cursor_date: str
    status: str
    stop_outcome: str
    manifest_path: Path
    manifest_relative_path: str
    manifest_hash: str
    raw_hash: str
    accepted_page_count: int
    row_fingerprints: Mapping[str, str]


def run_kis_paper_daily_history_collection(
    *,
    client_factory: Callable[[], KisPaperMarketDataClient],
    client: KisPaperMarketDataClient | None = None,
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    cache_root: Path = KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    evidence_root: Path = KIS_PAPER_DAILY_HISTORY_EVIDENCE_ROOT,
    repo_root: Path,
    code_revision: str,
    recover_deferred_targets: bool = False,
    max_chunks: int = KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_CHUNKS,
    max_runtime: timedelta = KIS_PAPER_DAILY_HISTORY_DEFAULT_MAX_RUNTIME,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> KisPaperDailyHistoryRun:
    """Advance independent fixed-symbol cursors without a foreground scheduler wait."""

    if (
        not isinstance(recover_deferred_targets, bool)
        or max_chunks <= 0
        or not isinstance(max_runtime, timedelta)
        or max_runtime <= timedelta(0)
    ):
        raise ValueError("daily history worker bounds are invalid")
    recovery_target_keys = _DEFERRED_RECOVERY_TARGET_KEYS if recover_deferred_targets else ()
    started_at = require_utc(clock(), "clock")
    root = _history_root(cache_root=cache_root, repo_root=repo_root)
    artifacts = _artifact_root(evidence_root=evidence_root, repo_root=repo_root)
    lock = _try_worker_lock(root / KIS_PAPER_DAILY_HISTORY_LOCK_FILENAME)
    if lock is None:
        return _build_run(
            status="busy",
            observed_at=started_at,
            completed_at=require_utc(clock(), "clock"),
            index=_load_or_initialize_index(root=root),
            accepted_page_count=0,
            categorical_failure_count=0,
            chunk_attempt_count=0,
            elapsed_seconds=0.0,
            next_due=None,
            recovery="resume",
            recovery_target_keys=recovery_target_keys,
        )
    try:
        index = _load_or_initialize_index(root=root)
        _reverify_index(index=index, root=root)
        recovered = _recover_orphan_snapshot(
            index=index,
            root=root,
            eligible_target_keys=recovery_target_keys or _TARGET_KEYS,
        )
        if recovered:
            _write_index(root=root, index=index)
        _validate_deferred_recovery_targets(
            index=index,
            recovery_target_keys=recovery_target_keys,
        )
        active_client = client
        accepted_pages = 0
        categorical_failures = 0
        chunk_attempts = 0
        next_due: datetime | None = _future_due(
            _next_due(
                request_gate,
                token_start_gate,
                token_required=active_client is None,
            ),
            now=started_at,
        )
        status: Literal["collected", "complete", "deferred", "storage_floor_would_be_crossed"] = (
            "deferred"
        )
        start_monotonic = monotonic_clock()
        attempted_deferred_recovery_targets: set[str] = set()

        while chunk_attempts < max_chunks:
            if monotonic_clock() - start_monotonic >= max_runtime.total_seconds():
                status = "collected" if accepted_pages else "deferred"
                break
            now = require_utc(clock(), "clock")
            next_due = _future_due(
                _next_due(
                    request_gate,
                    token_start_gate,
                    token_required=active_client is None,
                ),
                now=now,
            )
            if next_due is not None:
                status = "collected" if accepted_pages else "deferred"
                break
            target = _select_collectable_target(
                index=index,
                recovery_target_keys=recovery_target_keys,
                attempted_deferred_recovery_targets=attempted_deferred_recovery_targets,
            )
            if target is None:
                status = "complete" if _all_targets_terminal(index) else "deferred"
                break
            if str(target["target_key"]) in recovery_target_keys:
                attempted_deferred_recovery_targets.add(str(target["target_key"]))
            if private_daily_cache_would_cross_free_space_floor(
                cache_root=root,
                repo_root=repo_root,
            ):
                status = "storage_floor_would_be_crossed"
                break
            if active_client is None:
                active_client = client_factory()
            collection = _collect_two_pages_without_extra_delay(
                client=active_client,
                target=KisPaperPrivateDailyCollectionTarget(
                    symbol=str(target["symbol"]),
                    exchange=str(target["exchange"]),
                    anchor_date=str(target["next_anchor_date"]),
                    approved_symbol_exchanges=KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES,
                ),
                code_revision=code_revision,
                observed_at=require_utc(clock(), "clock"),
            )
            chunk_attempts += 1
            accepted_pages += len(collection.pages)
            if collection.status == "rejected" and not collection.rows:
                categorical_failures += 1
                _record_unretained_failure(
                    target=target,
                    reason=collection.reason or "unexpected_private_daily_collector_error",
                )
                _write_index(root=root, index=index)
                next_due = _future_due(
                    _next_due(
                        request_gate,
                        token_start_gate,
                        token_required=collection.reason == "token_request_not_due",
                    ),
                    now=require_utc(clock(), "clock"),
                )
                if next_due is not None or collection.reason == "token_request_not_due":
                    status = "collected" if accepted_pages else "deferred"
                    break
                continue
            if _is_terminal_empty_observation(collection):
                _record_source_limited(
                    target=target,
                    reason="empty_daily_response",
                    accepted_page_count=len(collection.pages),
                    categorical_failure=False,
                )
                _write_index(root=root, index=index)
                next_due = _future_due(
                    _next_due(
                        request_gate,
                        token_start_gate,
                        token_required=False,
                    ),
                    now=require_utc(clock(), "clock"),
                )
                if _all_targets_terminal(index):
                    status = "complete"
                    break
                status = "collected" if accepted_pages else "deferred"
                continue
            if _has_no_cursor_progress(collection):
                categorical_failures += _record_source_limited(
                    target=target,
                    reason="no_cursor_progress",
                    accepted_page_count=len(collection.pages),
                    categorical_failure=True,
                )
                _write_index(root=root, index=index)
                next_due = _future_due(
                    _next_due(
                        request_gate,
                        token_start_gate,
                        token_required=False,
                    ),
                    now=require_utc(clock(), "clock"),
                )
                if _all_targets_terminal(index):
                    status = "complete"
                    break
                status = "collected" if accepted_pages else "deferred"
                continue
            snapshot = _write_and_inspect_snapshot(
                root=root,
                repo_root=repo_root,
                index=index,
                result=collection,
            )
            commit_status, commit_failures, commit_next_due = _commit_snapshot(
                index=index,
                target=target,
                snapshot=snapshot,
                root=root,
                request_gate=request_gate,
                token_start_gate=token_start_gate,
            )
            categorical_failures += commit_failures
            _write_index(root=root, index=index)
            next_due = _future_due(
                commit_next_due,
                now=require_utc(clock(), "clock"),
            )
            if commit_status == "storage_floor_would_be_crossed":
                status = commit_status
                break
            if next_due is not None:
                status = "collected" if accepted_pages else "deferred"
                break
            if _all_targets_terminal(index):
                status = "complete"
                break
            status = "collected" if accepted_pages else "deferred"
        else:
            status = "collected" if accepted_pages else "deferred"

        completed_at = require_utc(clock(), "clock")
        run = _build_run(
            status=status,
            observed_at=started_at,
            completed_at=completed_at,
            index=index,
            accepted_page_count=accepted_pages,
            categorical_failure_count=categorical_failures,
            chunk_attempt_count=chunk_attempts,
            elapsed_seconds=max(0.0, monotonic_clock() - start_monotonic),
            next_due=_future_due(next_due, now=completed_at),
            recovery=(
                "complete"
                if status == "complete"
                else "reconcile"
                if any(target["state"] == "deferred" for target in _targets(index))
                else "resume"
            ),
            recovery_target_keys=recovery_target_keys,
        )
        evidence_hash = _write_source_safe_receipt(
            evidence_root=artifacts,
            repo_root=repo_root,
            run=run,
        )
        return KisPaperDailyHistoryRun(**{**run.__dict__, "evidence_sha256": evidence_hash})
    finally:
        _release_worker_lock(lock)


def _collect_two_pages_without_extra_delay(
    *,
    client: KisPaperMarketDataClient,
    target: KisPaperPrivateDailyCollectionTarget,
    code_revision: str,
    observed_at: datetime,
) -> KisPaperPrivateDailyCollectionResult:
    """Use transport-owned shared pacing; do not add a worker-local sleep."""

    initial_counts = client.call_counts
    pages: list[KisPaperPrivateDailyCollectorPage] = []
    rows_by_date: dict[str, KisPaperDailyRawRow] = {}
    dedupe_count = 0
    conflict_count = 0
    try:
        client.ensure_authenticated()
        first = client.fetch_daily_raw_page(
            KisPaperDailyQuery(
                symbol=target.symbol,
                exchange=target.exchange,
                by_date=target.anchor_date,
                approved_symbol_exchanges=KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES,
            )
        )
        pages.append(_page_fact(first, page_number=1))
        added, conflict = _merge_rows(rows_by_date, first.rows)
        dedupe_count += added
        conflict_count += conflict
        if conflict:
            raise KisPaperPrivateDailyCollectorError("daily_duplicate_conflict")
        if first.page.continuation_available and first.page.oldest_date is not None:
            second = client.fetch_daily_raw_page(
                KisPaperDailyQuery(
                    symbol=target.symbol,
                    exchange=target.exchange,
                    by_date=first.page.oldest_date,
                    continuation="F",
                    approved_symbol_exchanges=KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES,
                )
            )
            pages.append(_page_fact(second, page_number=2))
            added, conflict = _merge_rows(rows_by_date, second.rows)
            dedupe_count += added
            conflict_count += conflict
            if conflict:
                raise KisPaperPrivateDailyCollectorError("daily_duplicate_conflict")
    except (KisPaperMarketDataError, KisPaperPrivateDailyCollectorError) as error:
        reason = sanitize_kis_paper_private_daily_collector_failure_reason(error)
        return _collection_result(
            client=client,
            initial_counts=initial_counts,
            target=target,
            code_revision=code_revision,
            observed_at=observed_at,
            pages=pages,
            rows_by_date=rows_by_date,
            dedupe_count=dedupe_count,
            conflict_count=conflict_count,
            status="partial" if rows_by_date else "rejected",
            reason=reason,
        )
    return _collection_result(
        client=client,
        initial_counts=initial_counts,
        target=target,
        code_revision=code_revision,
        observed_at=observed_at,
        pages=pages,
        rows_by_date=rows_by_date,
        dedupe_count=dedupe_count,
        conflict_count=conflict_count,
        status="observed",
        reason=None,
    )


def _collection_result(
    *,
    client: KisPaperMarketDataClient,
    initial_counts: KisPaperMarketDataCallCounts,
    target: KisPaperPrivateDailyCollectionTarget,
    code_revision: str,
    observed_at: datetime,
    pages: Sequence[KisPaperPrivateDailyCollectorPage],
    rows_by_date: Mapping[str, KisPaperDailyRawRow],
    dedupe_count: int,
    conflict_count: int,
    status: Literal["observed", "partial", "rejected"],
    reason: str | None,
) -> KisPaperPrivateDailyCollectionResult:
    final = client.call_counts
    return KisPaperPrivateDailyCollectionResult(
        observed_at=observed_at,
        requested_anchor_date=target.anchor_date,
        code_revision=code_revision,
        call_counts=KisPaperMarketDataCallCounts(
            token_attempts=final.token_attempts - initial_counts.token_attempts,
            minute_page_attempts=final.minute_page_attempts - initial_counts.minute_page_attempts,
            daily_page_attempts=final.daily_page_attempts - initial_counts.daily_page_attempts,
        ),
        pages=tuple(pages),
        rows=tuple(rows_by_date[date] for date in sorted(rows_by_date)),
        dedupe_count=dedupe_count,
        conflicting_duplicate_rows=conflict_count,
        inter_page_delay_seconds=(),
        status=status,
        reason=reason,
        symbol=target.symbol,
        exchange=target.exchange,
        approved_symbol_exchanges=KIS_PAPER_DAILY_HISTORY_SYMBOL_EXCHANGES,
    )


def _page_fact(raw: KisPaperDailyRawPage, *, page_number: int) -> KisPaperPrivateDailyCollectorPage:
    page = raw.page
    return KisPaperPrivateDailyCollectorPage(
        page_number=page_number,
        row_count=page.row_count,
        newest_date=page.newest_date,
        oldest_date=page.oldest_date,
        continuation_advertised=page.continuation_available,
    )


def _merge_rows(
    rows_by_date: dict[str, KisPaperDailyRawRow],
    rows: Sequence[KisPaperDailyRawRow],
) -> tuple[int, int]:
    duplicates = 0
    conflicts = 0
    for row in rows:
        previous = rows_by_date.get(row.xymd)
        if previous is None:
            rows_by_date[row.xymd] = row
        elif previous == row:
            duplicates += 1
        else:
            conflicts += 1
    return duplicates, conflicts


def _write_and_inspect_snapshot(
    *,
    root: Path,
    repo_root: Path,
    index: Mapping[str, object],
    result: KisPaperPrivateDailyCollectionResult,
) -> _Snapshot:
    generation = int(index["generation"]) + 1
    run_id = f"{result.observed_at:%Y%m%dT%H%M%SZ}-{generation:06d}"
    output_cursor = result.rows[0].xymd if result.rows else None
    manifest_path, _ = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=root,
        run_id=run_id,
        repo_root=repo_root,
        collector_objective_id=KIS_PAPER_DAILY_HISTORY_OBJECTIVE_ID,
        collector_version=KIS_PAPER_DAILY_HISTORY_VERSION,
        backfill_context={
            "contract_version": KIS_PAPER_DAILY_HISTORY_VERSION,
            "cursor_strategy": "oldest_session_date_with_exact_overlap",
            "input_cursor_date": result.requested_anchor_date,
            "logical_cursor_persisted": True,
            "output_cursor_date": output_cursor,
            "target_key": f"{result.symbol}/{result.exchange}/MODP=0",
        },
    )
    return _inspect_snapshot(manifest_path=manifest_path, root=root)


def _is_terminal_empty_observation(result: KisPaperPrivateDailyCollectionResult) -> bool:
    """Recognize KIS's valid terminal no-row page without inventing a raw file."""

    return (
        result.status == "observed"
        and not result.rows
        and bool(result.pages)
        and all(page.row_count == 0 and not page.continuation_advertised for page in result.pages)
    )


def _has_no_cursor_progress(result: KisPaperPrivateDailyCollectionResult) -> bool:
    """Require each persisted chunk to move strictly toward older sessions."""

    return bool(result.rows) and result.rows[0].xymd >= result.requested_anchor_date


def _commit_snapshot(
    *,
    index: dict[str, object],
    target: dict[str, object],
    snapshot: _Snapshot,
    root: Path,
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
) -> tuple[Literal["collected", "storage_floor_would_be_crossed"], int, datetime | None]:
    if (
        snapshot.target_key != target["target_key"]
        or snapshot.input_cursor_date != target["next_anchor_date"]
    ):
        raise KisPaperDailyHistoryError("daily history snapshot cursor mismatch")
    if snapshot.output_cursor_date >= snapshot.input_cursor_date:
        # This only protects an orphan written by an older interrupted worker.
        # Normal collection checks the cursor before creating a snapshot.
        failures = _record_source_limited(
            target=target,
            reason="no_cursor_progress",
            accepted_page_count=snapshot.accepted_page_count,
            categorical_failure=True,
        )
        _append_chunk(
            target=target,
            snapshot=snapshot,
            root=root,
            outcome="source_limited",
            exact_overlap=0,
        )
        index["generation"] = int(index["generation"]) + 1
        return (
            "collected",
            failures,
            _next_due(
                request_gate,
                token_start_gate,
                token_required=False,
            ),
        )
    prior_fingerprints = {
        date: fingerprint
        for chunk in target["chunks"]
        if chunk["outcome"] in {"committed", "partial", "complete", "source_limited"}
        for date, fingerprint in chunk["row_fingerprints"].items()
    }
    conflicts = [
        date
        for date, fingerprint in snapshot.row_fingerprints.items()
        if date in prior_fingerprints and prior_fingerprints[date] != fingerprint
    ]
    exact_overlap = sum(
        prior_fingerprints.get(date) == fingerprint
        for date, fingerprint in snapshot.row_fingerprints.items()
    )
    if conflicts:
        target["state"] = "deferred"
        target["last_reason"] = "cross_chunk_duplicate_conflict"
        _append_chunk(
            target=target,
            snapshot=snapshot,
            root=root,
            outcome="conflict",
            exact_overlap=exact_overlap,
        )
        index["generation"] = int(index["generation"]) + 1
        return (
            "collected",
            1,
            _next_due(
                request_gate,
                token_start_gate,
                token_required=False,
            ),
        )

    target["accepted_page_count"] = (
        int(target["accepted_page_count"]) + snapshot.accepted_page_count
    )
    if snapshot.status == "partial":
        target["categorical_failure_count"] = int(target["categorical_failure_count"]) + 1
        target["last_reason"] = _partial_reason(snapshot.stop_outcome)
    else:
        target["last_reason"] = None
    terminal = (
        snapshot.stop_outcome == "source_exhausted"
        or snapshot.output_cursor_date <= KIS_PAPER_DAILY_HISTORY_TERMINAL_DATE
    )
    target["next_anchor_date"] = snapshot.output_cursor_date
    target["state"] = "complete" if terminal else "ready"
    _append_chunk(
        target=target,
        snapshot=snapshot,
        root=root,
        outcome="complete"
        if terminal
        else ("partial" if snapshot.status == "partial" else "committed"),
        exact_overlap=exact_overlap,
    )
    index["generation"] = int(index["generation"]) + 1
    next_due = _next_due(request_gate, token_start_gate, token_required=False)
    return "collected", 1 if snapshot.status == "partial" else 0, next_due


def _append_chunk(
    *,
    target: dict[str, object],
    snapshot: _Snapshot,
    root: Path,
    outcome: Literal["committed", "partial", "complete", "conflict", "source_limited"],
    exact_overlap: int,
) -> None:
    relative = snapshot.manifest_path.relative_to(root)
    target["chunks"].append(
        {
            "outcome": outcome,
            "input_cursor_date": snapshot.input_cursor_date,
            "output_cursor_date": snapshot.output_cursor_date,
            "manifest_path": str(relative),
            "manifest_sha256": snapshot.manifest_hash,
            "raw_sha256": snapshot.raw_hash,
            "row_count": len(snapshot.row_fingerprints),
            "accepted_page_count": snapshot.accepted_page_count,
            "exact_overlap_row_count": exact_overlap,
            "row_fingerprints": dict(snapshot.row_fingerprints),
            "stop_outcome": snapshot.stop_outcome,
        }
    )


def _record_unretained_failure(*, target: dict[str, object], reason: str) -> None:
    if reason not in _SAFE_FAILURE_REASONS:
        reason = "unexpected_private_daily_collector_error"
    repeated_structural_failure = (
        reason == "daily_response_invalid"
        and target["state"] == "deferred"
        and target["last_reason"] == "daily_response_invalid"
    )
    target["categorical_failure_count"] = int(target["categorical_failure_count"]) + 1
    target["last_reason"] = reason
    target["state"] = (
        "source_limited"
        if repeated_structural_failure
        else "ready"
        if reason in {"rate_limited", "token_request_not_due"}
        else "deferred"
    )


def _record_source_limited(
    *,
    target: dict[str, object],
    reason: Literal["empty_daily_response", "no_cursor_progress"],
    accepted_page_count: int,
    categorical_failure: bool,
) -> int:
    """Persist a terminal source fact without publishing a raw snapshot."""

    if accepted_page_count < 0:
        raise ValueError("daily history accepted page count is invalid")
    target["accepted_page_count"] = int(target["accepted_page_count"]) + accepted_page_count
    if categorical_failure:
        target["categorical_failure_count"] = int(target["categorical_failure_count"]) + 1
    target["last_reason"] = reason
    target["state"] = "source_limited"
    return 1 if categorical_failure else 0


def _validate_deferred_recovery_targets(
    *,
    index: Mapping[str, object],
    recovery_target_keys: tuple[str, ...],
) -> None:
    """Allow the explicit recovery mode to touch only its two known failures."""

    if not recovery_target_keys:
        return
    if recovery_target_keys != _DEFERRED_RECOVERY_TARGET_KEYS:
        raise KisPaperDailyHistoryError("daily history recovery targets are invalid")
    for target in _targets(index):
        target_key = str(target["target_key"])
        if target_key not in recovery_target_keys:
            continue
        state = str(target["state"])
        if state in {"complete", "source_limited"}:
            continue
        expected_reason = _DEFERRED_RECOVERY_TARGET_REASONS[target_key]
        last_reason = str(target.get("last_reason", ""))
        if state == "ready":
            continue
        if state != "deferred" or last_reason != expected_reason:
            raise KisPaperDailyHistoryError("daily history recovery target state mismatch")


def _select_collectable_target(
    *,
    index: Mapping[str, object],
    recovery_target_keys: tuple[str, ...],
    attempted_deferred_recovery_targets: set[str],
) -> dict[str, object] | None:
    if recovery_target_keys:
        candidates = [
            target
            for target in _targets(index)
            if target["target_key"] in recovery_target_keys
            and target["target_key"] not in attempted_deferred_recovery_targets
            and (
                target["state"] == "ready"
                or target["state"] == "deferred"
            )
        ]
    else:
        candidates = [target for target in _targets(index) if target["state"] == "ready"]
    if not candidates:
        return None
    positions = {target["target_key"]: position for position, target in enumerate(_targets(index))}
    return max(
        candidates,
        key=lambda target: (
            str(target["next_anchor_date"]),
            -int(target["accepted_page_count"]),
            -positions[str(target["target_key"])],
        ),
    )


def _all_targets_terminal(index: Mapping[str, object]) -> bool:
    return all(target["state"] in {"complete", "source_limited"} for target in _targets(index))


def _build_run(
    *,
    status: Literal["collected", "complete", "deferred", "busy", "storage_floor_would_be_crossed"],
    observed_at: datetime,
    completed_at: datetime,
    index: Mapping[str, object],
    accepted_page_count: int,
    categorical_failure_count: int,
    chunk_attempt_count: int,
    elapsed_seconds: float,
    next_due: datetime | None,
    recovery: Literal["resume", "complete", "restart", "reconcile"],
    recovery_target_keys: tuple[str, ...] = (),
) -> KisPaperDailyHistoryRun:
    target_states = tuple(
        KisPaperDailyHistoryTargetState(
            target_key=str(target["target_key"]),
            state=str(target["state"]),
            cursor_date=str(target["next_anchor_date"]),
            accepted_page_count=int(target["accepted_page_count"]),
            categorical_failure_count=int(target["categorical_failure_count"]),
            coverage_bucket=_coverage_bucket(str(target["next_anchor_date"])),
            last_reason=target["last_reason"],
        )
        for target in _targets(index)
    )
    pace = (
        None
        if accepted_page_count == 0
        else round(accepted_page_count / max(elapsed_seconds / 60, 0.001), 3)
    )
    return KisPaperDailyHistoryRun(
        status=status,
        observed_at=observed_at,
        completed_at=completed_at,
        target_states=target_states,
        accepted_page_count=accepted_page_count,
        categorical_failure_count=categorical_failure_count,
        chunk_attempt_count=chunk_attempt_count,
        measured_accepted_pages_per_minute=pace,
        remaining_page_estimate=None,
        eta_bucket="unknown",
        next_due=next_due,
        recovery=recovery,
        recovery_target_keys=recovery_target_keys,
    )


def _next_due(
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    *,
    token_required: bool,
) -> datetime | None:
    candidates = [request_gate.snapshot().retry_not_before_utc]
    if token_required:
        candidates.append(token_start_gate.snapshot().next_token_request_not_before_utc)
    due_values = [value for value in candidates if value is not None]
    return max(due_values, default=None)


def _future_due(value: datetime | None, *, now: datetime) -> datetime | None:
    """Expose a retry only while it remains an owned future wait."""

    current = require_utc(now, "clock")
    return value if value is not None and value > current else None


def _partial_reason(stop_outcome: str) -> str:
    reason = stop_outcome.removeprefix("partial_")
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_private_daily_collector_error"


def _load_or_initialize_index(*, root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / KIS_PAPER_DAILY_HISTORY_INDEX_FILENAME
    if not path.exists():
        index = _initial_index()
        _write_index(root=root, index=index)
        return index
    if path.is_symlink():
        raise KisPaperDailyHistoryError("daily history index is invalid")
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailyHistoryError("daily history index is invalid") from error
    if not isinstance(index, dict):
        raise KisPaperDailyHistoryError("daily history index is invalid")
    _validate_index(index)
    return index


def _initial_index() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_paper_daily_nas_history_index",
        "version": KIS_PAPER_DAILY_HISTORY_VERSION,
        "registry": {
            "version": KIS_PAPER_DAILY_HISTORY_REGISTRY_VERSION,
            "registry_sha256": KIS_PAPER_DAILY_HISTORY_REGISTRY_SHA256,
            "source_manifest_sha256": KIS_PAPER_DAILY_HISTORY_SOURCE_MANIFEST_SHA256,
            "source_file_sha256": KIS_PAPER_DAILY_HISTORY_SOURCE_FILE_SHA256,
            "target_keys": list(_TARGET_KEYS),
            "prospective_only": True,
            "historical_point_in_time_eligible": False,
        },
        "initial_anchor_date": KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE,
        "terminal_date": KIS_PAPER_DAILY_HISTORY_TERMINAL_DATE,
        "generation": 0,
        "targets": [
            {
                "target_key": key,
                "symbol": key.split("/", maxsplit=1)[0],
                "exchange": NAS_EXCHANGE,
                "next_anchor_date": KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE,
                "state": "ready",
                "accepted_page_count": 0,
                "categorical_failure_count": 0,
                "last_reason": None,
                "chunks": [],
            }
            for key in _TARGET_KEYS
        ],
        "storage": {"private_local_only": True, "served": False, "redistributed": False},
        "redaction": {
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "request_headers_persisted": False,
            "response_bodies_persisted": False,
            "raw_rows_in_index": False,
        },
    }


def _validate_index(index: Mapping[str, object]) -> None:
    if (
        index.get("schema_version") != 1
        or index.get("kind") != "kis_paper_daily_nas_history_index"
        or index.get("version") != KIS_PAPER_DAILY_HISTORY_VERSION
        or index.get("initial_anchor_date") != KIS_PAPER_DAILY_HISTORY_INITIAL_ANCHOR_DATE
        or index.get("terminal_date") != KIS_PAPER_DAILY_HISTORY_TERMINAL_DATE
        or not isinstance(index.get("generation"), int)
        or int(index["generation"]) < 0
    ):
        raise KisPaperDailyHistoryError("daily history index is invalid")
    registry = index.get("registry")
    if not isinstance(registry, Mapping) or registry != _initial_index()["registry"]:
        raise KisPaperDailyHistoryError("daily history registry is invalid")
    targets = index.get("targets")
    if (
        not isinstance(targets, list)
        or tuple(
            target.get("target_key") if isinstance(target, Mapping) else None for target in targets
        )
        != _TARGET_KEYS
    ):
        raise KisPaperDailyHistoryError("daily history targets are invalid")
    for target in targets:
        _validate_target(target)
    if (
        index.get("storage") != _initial_index()["storage"]
        or index.get("redaction") != _initial_index()["redaction"]
    ):
        raise KisPaperDailyHistoryError("daily history storage policy is invalid")


def _validate_target(value: object) -> None:
    if not isinstance(value, Mapping):
        raise KisPaperDailyHistoryError("daily history target is invalid")
    key = value.get("target_key")
    if (
        key not in _TARGET_KEYS
        or value.get("symbol") != str(key).split("/", maxsplit=1)[0]
        or value.get("exchange") != NAS_EXCHANGE
        or not _is_date(value.get("next_anchor_date"))
        or value.get("state") not in _TARGET_STATES
        or not isinstance(value.get("accepted_page_count"), int)
        or int(value["accepted_page_count"]) < 0
        or not isinstance(value.get("categorical_failure_count"), int)
        or int(value["categorical_failure_count"]) < 0
        or (
            value.get("last_reason") is not None
            and value.get("last_reason") not in _SAFE_FAILURE_REASONS
        )
        or not isinstance(value.get("chunks"), list)
    ):
        raise KisPaperDailyHistoryError("daily history target is invalid")
    for chunk in value["chunks"]:
        _validate_chunk(chunk)


def _validate_chunk(value: object) -> None:
    if not isinstance(value, Mapping):
        raise KisPaperDailyHistoryError("daily history chunk is invalid")
    fingerprints = value.get("row_fingerprints")
    if (
        value.get("outcome")
        not in {"committed", "partial", "complete", "conflict", "source_limited"}
        or not _is_date(value.get("input_cursor_date"))
        or not _is_date(value.get("output_cursor_date"))
        or not isinstance(value.get("manifest_path"), str)
        or not _is_sha256(value.get("manifest_sha256"))
        or not _is_sha256(value.get("raw_sha256"))
        or not isinstance(value.get("row_count"), int)
        or not isinstance(value.get("accepted_page_count"), int)
        or not isinstance(value.get("exact_overlap_row_count"), int)
        or not isinstance(fingerprints, Mapping)
        or not isinstance(value.get("stop_outcome"), str)
    ):
        raise KisPaperDailyHistoryError("daily history chunk is invalid")
    if int(value["row_count"]) <= 0 or len(fingerprints) != int(value["row_count"]):
        raise KisPaperDailyHistoryError("daily history chunk is invalid")
    for date, fingerprint in fingerprints.items():
        if not _is_iso_date(date) or not _is_sha256(fingerprint):
            raise KisPaperDailyHistoryError("daily history chunk is invalid")


def _write_index(*, root: Path, index: Mapping[str, object]) -> None:
    _validate_index(index)
    _write_json_atomically(root / KIS_PAPER_DAILY_HISTORY_INDEX_FILENAME, dict(index))


def _reverify_index(*, index: Mapping[str, object], root: Path) -> None:
    for target in _targets(index):
        for chunk in target["chunks"]:
            snapshot = _inspect_snapshot(
                manifest_path=root / str(chunk["manifest_path"]), root=root
            )
            expected = {
                "input_cursor_date": chunk["input_cursor_date"],
                "output_cursor_date": chunk["output_cursor_date"],
                "manifest_hash": chunk["manifest_sha256"],
                "raw_hash": chunk["raw_sha256"],
                "accepted_page_count": chunk["accepted_page_count"],
                "row_fingerprints": chunk["row_fingerprints"],
            }
            actual = {
                "input_cursor_date": snapshot.input_cursor_date,
                "output_cursor_date": snapshot.output_cursor_date,
                "manifest_hash": snapshot.manifest_hash,
                "raw_hash": snapshot.raw_hash,
                "accepted_page_count": snapshot.accepted_page_count,
                "row_fingerprints": dict(snapshot.row_fingerprints),
            }
            if snapshot.target_key != target["target_key"] or actual != expected:
                raise KisPaperDailyHistoryError("daily history committed snapshot drift")


def _recover_orphan_snapshot(
    *,
    index: dict[str, object],
    root: Path,
    eligible_target_keys: tuple[str, ...],
) -> bool:
    known_hashes = {
        chunk["manifest_sha256"] for target in _targets(index) for chunk in target["chunks"]
    }
    for manifest_path in sorted(root.glob("snapshot=*/manifest.json")):
        if manifest_path.is_symlink():
            raise KisPaperDailyHistoryError("daily history orphan path is invalid")
        try:
            snapshot = _inspect_snapshot(manifest_path=manifest_path, root=root)
        except KisPaperDailyHistoryError:
            continue
        if snapshot.manifest_hash in known_hashes:
            continue
        if snapshot.target_key not in eligible_target_keys:
            continue
        target = next(
            (
                candidate
                for candidate in _targets(index)
                if candidate["target_key"] == snapshot.target_key
                and candidate["next_anchor_date"] == snapshot.input_cursor_date
            ),
            None,
        )
        if target is None:
            continue
        _commit_snapshot(
            index=index,
            target=target,
            snapshot=snapshot,
            root=root,
            request_gate=_NoRetryGate(),
            token_start_gate=_NoTokenRetryGate(),
        )
        return True
    return False


def _inspect_snapshot(*, manifest_path: Path, root: Path) -> _Snapshot:
    path = _resolved_child(path=manifest_path, root=root)
    if path.name != "manifest.json":
        raise KisPaperDailyHistoryError("daily history manifest is invalid")
    try:
        payload = path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailyHistoryError("daily history manifest is invalid") from error
    if not isinstance(manifest, Mapping):
        raise KisPaperDailyHistoryError("daily history manifest is invalid")
    source = manifest.get("source")
    context = manifest.get("backfill")
    files = manifest.get("files")
    if (
        not isinstance(source, Mapping)
        or not isinstance(context, Mapping)
        or not isinstance(files, Mapping)
    ):
        raise KisPaperDailyHistoryError("daily history manifest is invalid")
    symbol = source.get("symbol")
    exchange = source.get("exchange")
    raw_document = files.get("raw_daily_rows")
    if (
        manifest.get("collector_objective_id") != KIS_PAPER_DAILY_HISTORY_OBJECTIVE_ID
        or manifest.get("collector_version") != KIS_PAPER_DAILY_HISTORY_VERSION
        or source.get("endpoint") != "dailyprice"
        or source.get("adjustment_mode") != "MODP=0_unadjusted"
        or not isinstance(symbol, str)
        or not isinstance(exchange, str)
        or f"{symbol}/{exchange}" not in _TARGET_KEYS
        or context.get("contract_version") != KIS_PAPER_DAILY_HISTORY_VERSION
        or context.get("target_key") != f"{symbol}/{exchange}/MODP=0"
        or context.get("cursor_strategy") != "oldest_session_date_with_exact_overlap"
        or context.get("logical_cursor_persisted") is not True
        or not _is_date(context.get("input_cursor_date"))
        or not _is_date(context.get("output_cursor_date"))
        or not isinstance(raw_document, Mapping)
    ):
        raise KisPaperDailyHistoryError("daily history manifest is invalid")
    raw_path = raw_document.get("path")
    raw_hash = raw_document.get("sha256")
    raw_size = raw_document.get("size_bytes")
    if not isinstance(raw_path, str) or not _is_sha256(raw_hash) or not isinstance(raw_size, int):
        raise KisPaperDailyHistoryError("daily history raw document is invalid")
    raw_payload = _resolved_child(path=path.parent / raw_path, root=path.parent).read_bytes()
    if len(raw_payload) != raw_size or _sha256(raw_payload) != raw_hash:
        raise KisPaperDailyHistoryError("daily history raw hash is invalid")
    fingerprints = _raw_row_fingerprints(raw_payload, symbol=symbol, exchange=exchange)
    output_cursor = str(context["output_cursor_date"])
    if not fingerprints or output_cursor != min(_compact_date(date) for date in fingerprints):
        raise KisPaperDailyHistoryError("daily history cursor is invalid")
    requests = manifest.get("requests")
    if not isinstance(requests, Mapping) or not isinstance(requests.get("accepted_pages"), int):
        raise KisPaperDailyHistoryError("daily history request facts are invalid")
    return _Snapshot(
        target_key=f"{symbol}/{exchange}",
        input_cursor_date=str(context["input_cursor_date"]),
        output_cursor_date=output_cursor,
        status=str(manifest.get("status")),
        stop_outcome=str(manifest.get("stop_outcome")),
        manifest_path=path,
        manifest_relative_path=str(path.relative_to(root)),
        manifest_hash=_sha256(payload),
        raw_hash=str(raw_hash),
        accepted_page_count=int(requests["accepted_pages"]),
        row_fingerprints=fingerprints,
    )


def _raw_row_fingerprints(payload: bytes, *, symbol: str, exchange: str) -> dict[str, str]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
            reader = csv.DictReader(io.StringIO(handle.read().decode("utf-8"), newline=""))
            if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                raise ValueError
            rows = list(reader)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise KisPaperDailyHistoryError("daily history raw contents are invalid") from error
    fingerprints: dict[str, str] = {}
    for row in rows:
        session = row.get("session_date")
        if (
            row.get("symbol") != symbol
            or row.get("exchange") != exchange
            or not _is_iso_date(session)
        ):
            raise KisPaperDailyHistoryError("daily history raw contents are invalid")
        if session in fingerprints:
            raise KisPaperDailyHistoryError("daily history raw contents are invalid")
        rendered = "\x1f".join(str(row.get(column, "")) for column in _RAW_COLUMNS)
        fingerprints[session] = _sha256(rendered.encode("utf-8"))
    if list(fingerprints) != sorted(fingerprints):
        raise KisPaperDailyHistoryError("daily history raw contents are invalid")
    return fingerprints


def _write_source_safe_receipt(
    *,
    evidence_root: Path,
    repo_root: Path,
    run: KisPaperDailyHistoryRun,
) -> str:
    root = _artifact_root(evidence_root=evidence_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"{run.completed_at:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:12]}"
    destination = root / f"run={run_id}"
    if destination.exists() or destination.is_symlink():
        raise KisPaperDailyHistoryError("daily history receipt destination is invalid")
    payload = (
        json.dumps(run.source_safe_document(), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    destination.mkdir()
    try:
        _write_bytes(destination / "receipt.json", payload)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return _sha256(payload)


def _history_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = Path(cache_root).resolve()
    repository = Path(repo_root).resolve()
    mounted_market_data = repository / "market_data"
    if root.is_relative_to(repository) and not (
        mounted_market_data.is_mount() and root.is_relative_to(mounted_market_data)
    ):
        raise KisPaperDailyHistoryError("daily history cache must stay outside Git")
    if root.is_symlink():
        raise KisPaperDailyHistoryError("daily history cache root is invalid")
    return root


def _artifact_root(*, evidence_root: Path, repo_root: Path) -> Path:
    root = Path(evidence_root).resolve()
    repository = Path(repo_root).resolve()
    if root.is_relative_to(repository) and not _is_external_mount(root, repository):
        raise KisPaperDailyHistoryError("daily history evidence must stay outside Git")
    if root.is_symlink():
        raise KisPaperDailyHistoryError("daily history evidence root is invalid")
    return root


def _is_external_mount(path: Path, repository: Path) -> bool:
    current = path
    while current != repository:
        if current.is_mount():
            return True
        current = current.parent
    return False


def _resolved_child(*, path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise KisPaperDailyHistoryError("daily history path is invalid")
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise KisPaperDailyHistoryError("daily history path is invalid")
    return resolved_path


def _targets(index: Mapping[str, object]) -> list[dict[str, object]]:
    values = index["targets"]
    assert isinstance(values, list)
    return [value for value in values if isinstance(value, dict)]


def _coverage_bucket(cursor: str) -> str | None:
    if not _is_date(cursor):
        return None
    quarter = (int(cursor[4:6]) - 1) // 3 + 1
    return f"{cursor[:4]}-Q{quarter}"


def _is_coverage_bucket(value: str) -> bool:
    return len(value) == 7 and value[:4].isdigit() and value[4:6] == "-Q" and value[6] in "1234"


def _is_date(value: object) -> bool:
    return isinstance(value, str) and len(value) == 8 and value.isdigit()


def _is_iso_date(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 10
        and value[4] == "-"
        and value[7] == "-"
        and value.replace("-", "").isdigit()
    )


def _compact_date(value: str) -> str:
    return value.replace("-", "")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")


def _write_json_atomically(path: Path, document: Mapping[str, object]) -> None:
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    staging = path.parent / f".{path.name}.{uuid.uuid4().hex}.stage"
    try:
        _write_bytes(staging, payload)
        os.replace(staging, path)
    finally:
        if staging.exists():
            staging.unlink()


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _try_worker_lock(path: Path) -> BinaryIO | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        _lock_nonblocking(handle)
    except OSError:
        handle.close()
        return None
    return handle


def _release_worker_lock(handle: BinaryIO | None) -> None:
    if handle is None:
        return
    try:
        _unlock(handle)
    finally:
        handle.close()


def _lock_nonblocking(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class _NoRetryGate:
    def snapshot(self) -> object:
        return type("Snapshot", (), {"retry_not_before_utc": None})()


class _NoTokenRetryGate:
    def snapshot(self) -> object:
        return type("Snapshot", (), {"next_token_request_not_before_utc": None})()

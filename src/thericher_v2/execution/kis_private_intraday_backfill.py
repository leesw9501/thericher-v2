"""Resumable private KIS Paper 1m cache collection for SPY and QQQ.

The module owns the credential-bearing transport boundary and writes only
provider-field rows, manifests, and cursor state below the external market-data
root. It deliberately does not make a session-calendar or strategy claim.
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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
)

KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday"
)
KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION = "v1"
KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME = "index.json"
KIS_PAPER_PRIVATE_INTRADAY_SNAPSHOT_DIRECTORY = "snapshots"
KIS_PAPER_PRIVATE_INTRADAY_LOCK_FILENAME = ".backfill.lock"
KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS = (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
)
KIS_PAPER_PRIVATE_INTRADAY_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
_RAW_MINUTE_COLUMNS = (
    "xymd",
    "xhms",
    "kymd",
    "khms",
    "open",
    "high",
    "low",
    "last",
    "evol",
)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "minute_cursor_invalid",
        "minute_cursor_stalled",
        "minute_duplicate_conflict",
        "minute_exchange_timestamp_invalid",
        "minute_korea_timestamp_invalid",
        "minute_ohlc_invalid",
        "minute_page_limit_exceeded",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "transport_failure",
        KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
    }
)
_ConflictOrigin = Literal["candidate_batch", "retained_cache"]
_CollectionScope = Literal["head", "historical"]


class _CandidateBatchDuplicateConflict(KisPaperMarketDataError):
    """Marks a conflicting minute fingerprint within the current candidate batch."""


class KisPaperPrivateIntradayClient(Protocol):
    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage: ...


@dataclass(frozen=True)
class KisPaperPrivateIntradayTarget:
    symbol: str
    exchange: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        KisPaperMinuteQuery(exchange=self.exchange, symbol=self.symbol)

    @property
    def target_key(self) -> str:
        return f"{self.symbol}/{self.exchange}/1m"


@dataclass(frozen=True)
class KisPaperPrivateIntradayCursor:
    """The narrow KIS minute continuation state needed for one next page."""

    next_value: str
    keyb: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "next_value", self.next_value.strip())
        object.__setattr__(self, "keyb", self.keyb.strip())
        if self.next_value != "1" or len(self.keyb) != 14 or not self.keyb.isdigit():
            raise ValueError("private intraday cursor is invalid")

    def as_document(self) -> dict[str, str]:
        return {"keyb": self.keyb, "next": self.next_value}

    @classmethod
    def from_document(cls, value: object) -> KisPaperPrivateIntradayCursor | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError("private intraday cursor is invalid")
        next_value = value.get("next")
        keyb = value.get("keyb")
        if not isinstance(next_value, str) or not isinstance(keyb, str):
            raise ValueError("private intraday cursor is invalid")
        return cls(next_value=next_value, keyb=keyb)


@dataclass(frozen=True)
class KisPaperPrivateIntradayBackfillRun:
    status: Literal[
        "collected",
        "partial",
        "rejected",
        "locked",
        "recovered",
        "source_exhausted",
    ]
    target_key: str
    row_count: int
    exact_overlap_rows: int
    manifest_path: Path | None = None
    manifest_hash: str | None = None
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {
            "collected",
            "partial",
            "rejected",
            "locked",
            "recovered",
            "source_exhausted",
        }:
            raise ValueError("private intraday backfill status is invalid")
        if not self.target_key.strip() or self.row_count < 0 or self.exact_overlap_rows < 0:
            raise ValueError("private intraday backfill result is invalid")
        if (self.manifest_path is None) != (self.manifest_hash is None):
            raise ValueError("private intraday backfill result is invalid")
        if self.manifest_hash is not None and not _is_sha256(self.manifest_hash):
            raise ValueError("private intraday backfill result is invalid")


@dataclass(frozen=True)
class _CollectedTarget:
    target: KisPaperPrivateIntradayTarget
    input_cursor: KisPaperPrivateIntradayCursor | None
    output_cursor: KisPaperPrivateIntradayCursor | None
    rows: tuple[KisPaperMinuteRawBar, ...]
    page_documents: tuple[dict[str, object], ...]
    exact_duplicate_rows: int
    status: Literal["collected", "partial", "rejected"]
    reason: str | None
    conflict_origin: _ConflictOrigin | None = None


@dataclass
class _WorkerLock:
    path: Path
    handle: io.BufferedRandom


@dataclass(frozen=True)
class _RecoveredSnapshot:
    target: KisPaperPrivateIntradayTarget
    manifest_path: Path
    manifest_hash: str
    chunk: Mapping[str, object]


def run_kis_paper_private_intraday_backfill_cycle(
    *,
    client: KisPaperPrivateIntradayClient,
    cache_root: Path,
    repo_root: Path,
    code_revision: str,
    pages_per_target: int = 2,
    resume_cursor: bool = True,
    quarantine_retained_head_conflicts: bool = False,
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
    """Collect bounded source pages with optional historical-cursor resumption.

    A head observation sets ``resume_cursor`` false: it starts from the latest
    source page and retains its snapshot without changing any persisted cursor.
    A failed attempt creates no data-bearing chunk, so it is recovery evidence
    for that call only and never a later collection latch.
    """

    if type(pages_per_target) is not int or pages_per_target <= 0:
        raise ValueError("pages_per_target must be a positive integer")
    if type(resume_cursor) is not bool:
        raise ValueError("resume_cursor must be a boolean")
    if type(quarantine_retained_head_conflicts) is not bool:
        raise ValueError("head conflict quarantine must be a boolean")
    if quarantine_retained_head_conflicts and resume_cursor:
        raise ValueError("head conflict quarantine requires head mode")
    if not code_revision.strip() or "\n" in code_revision:
        raise ValueError("private intraday code revision is invalid")
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    root = _backfill_root(cache_root=cache_root, repo_root=repo_root)
    lock = _acquire_worker_lock(root)
    if lock is None:
        return tuple(
            KisPaperPrivateIntradayBackfillRun(
                status="locked",
                target_key=KisPaperPrivateIntradayTarget(*target).target_key,
                row_count=0,
                exact_overlap_rows=0,
                reason="worker_locked",
            )
            for target in KIS_PAPER_PRIVATE_INTRADAY_TARGETS
        )
    try:
        index = _read_or_create_index(root, hydrate_source_exhaustion=resume_cursor)
        removed_candidate_chunks = _remove_candidate_batch_conflicted_chunks(
            index, resume_cursor=resume_cursor
        )
        _attest_committed_snapshots(root=root, index=index)
        recovered = _recover_orphan_snapshots(root=root, index=index)
        recovered_by_target: dict[str, list[_RecoveredSnapshot]] = {}
        for item in recovered:
            recovered_by_target.setdefault(item.target.target_key, []).append(item)
        if removed_candidate_chunks or recovered:
            _attest_committed_snapshots(root=root, index=index)
            _write_index(root=root, index=index)
        results: list[KisPaperPrivateIntradayBackfillRun] = []
        pacer = _RequestPacer(sleeper=sleeper, monotonic_clock=monotonic_clock)
        for symbol, exchange in KIS_PAPER_PRIVATE_INTRADAY_TARGETS:
            target = KisPaperPrivateIntradayTarget(symbol=symbol, exchange=exchange)
            recovered_snapshots = recovered_by_target.get(target.target_key)
            if recovered_snapshots:
                results.append(
                    _recovered_target_run(target=target, snapshots=recovered_snapshots)
                )
                continue
            target_state = _index_target(index=index, target=target)
            input_cursor = (
                KisPaperPrivateIntradayCursor.from_document(target_state.get("next_cursor"))
                if resume_cursor
                else None
            )
            if resume_cursor and _target_source_is_exhausted(target_state):
                results.append(
                    KisPaperPrivateIntradayBackfillRun(
                        status="source_exhausted",
                        target_key=target.target_key,
                        row_count=0,
                        exact_overlap_rows=0,
                        reason="source_exhausted",
                    )
                )
                continue
            collected = _collect_target(
                client=client,
                target=target,
                input_cursor=input_cursor,
                pages_per_target=pages_per_target,
                before_request=pacer.wait_before_request,
            )
            if not resume_cursor:
                collected = _CollectedTarget(
                    target=collected.target,
                    input_cursor=None,
                    output_cursor=None,
                    rows=collected.rows,
                    page_documents=collected.page_documents,
                    exact_duplicate_rows=collected.exact_duplicate_rows,
                    status=collected.status,
                    reason=collected.reason,
                    conflict_origin=collected.conflict_origin,
                )
            if collected.status == "rejected":
                _record_target_last_observation(
                    target_state=target_state,
                    reason=collected.reason,
                    conflict_origin=collected.conflict_origin,
                    observed_at_utc=_format_utc(observed),
                )
                _write_index(root=root, index=index)
                results.append(
                    KisPaperPrivateIntradayBackfillRun(
                        status="rejected",
                        target_key=target.target_key,
                        row_count=0,
                        exact_overlap_rows=0,
                        reason=collected.reason,
                    )
                )
                continue

            existing_fingerprints = _target_fingerprints(target_state)
            conflicting_chunk_keys = _conflicting_retained_chunk_keys(
                rows=collected.rows,
                target_state=target_state,
            )
            quarantined_retained_head_chunks = False
            if conflicting_chunk_keys and _can_quarantine_retained_head_conflicts(
                collected=collected,
                target_state=target_state,
                conflicting_chunk_keys=conflicting_chunk_keys,
                quarantine_retained_head_conflicts=quarantine_retained_head_conflicts,
            ):
                _quarantine_retained_head_chunks(
                    target_state=target_state,
                    conflicting_chunk_keys=conflicting_chunk_keys,
                )
                quarantined_retained_head_chunks = True
            if conflicting_chunk_keys:
                _record_target_last_observation(
                    target_state=target_state,
                    reason="minute_duplicate_conflict",
                    conflict_origin="retained_cache",
                    observed_at_utc=_format_utc(observed),
                )
                if quarantined_retained_head_chunks:
                    index["generation"] = int(index["generation"]) + 1
                _write_index(root=root, index=index)
                results.append(
                    KisPaperPrivateIntradayBackfillRun(
                        status="rejected",
                        target_key=target.target_key,
                        row_count=0,
                        exact_overlap_rows=0,
                        reason="minute_duplicate_conflict",
                    )
                )
                continue

            prior_exact_overlap = sum(
                1
                for row in collected.rows
                if _row_key(row) in existing_fingerprints
            )
            chunk = _chunk_document(
                target=target,
                collected=collected,
                observed_at=observed,
                prior_exact_overlap=prior_exact_overlap,
                collection_scope="historical" if resume_cursor else "head",
            )
            if _has_chunk(target_state=target_state, candidate=chunk):
                if resume_cursor:
                    target_state["next_cursor"] = (
                        collected.output_cursor.as_document()
                        if collected.output_cursor is not None
                        else None
                    )
                last_reason = (
                    "source_exhausted"
                    if _collected_target_source_is_exhausted(
                        collected=collected,
                        resume_cursor=resume_cursor,
                    )
                    else "already_cached"
                )
                _record_target_last_observation(
                    target_state=target_state,
                    reason=last_reason,
                    observed_at_utc=_format_utc(observed),
                )
                _write_index(root=root, index=index)
                results.append(
                    KisPaperPrivateIntradayBackfillRun(
                        status="recovered",
                        target_key=target.target_key,
                        row_count=len(collected.rows),
                        exact_overlap_rows=(
                            collected.exact_duplicate_rows + prior_exact_overlap
                        ),
                        reason="already_cached",
                    )
                )
                continue
            manifest_path, manifest_hash = _write_snapshot(
                root=root,
                target=target,
                collected=collected,
                chunk=chunk,
                code_revision=code_revision,
                observed_at=observed,
                run_id=_run_id(observed_at=observed, generation=int(index["generation"])),
            )
            chunk["manifest_path"] = str(manifest_path.relative_to(root)).replace("\\", "/")
            chunk["manifest_hash"] = manifest_hash
            target_state["chunks"].append(chunk)
            if resume_cursor:
                target_state["next_cursor"] = (
                    collected.output_cursor.as_document()
                    if collected.output_cursor is not None
                    else None
                )
            last_reason = (
                "source_exhausted"
                if _collected_target_source_is_exhausted(
                    collected=collected,
                    resume_cursor=resume_cursor,
                )
                else collected.reason
            )
            _record_target_last_observation(
                target_state=target_state,
                reason=last_reason,
                conflict_origin=(
                    collected.conflict_origin if last_reason == collected.reason else None
                ),
                observed_at_utc=_format_utc(observed),
            )
            index["generation"] = int(index["generation"]) + 1
            _write_index(root=root, index=index)
            results.append(
                KisPaperPrivateIntradayBackfillRun(
                    status=collected.status,
                    target_key=target.target_key,
                    row_count=len(collected.rows),
                    exact_overlap_rows=(
                        collected.exact_duplicate_rows + prior_exact_overlap
                    ),
                    manifest_path=manifest_path,
                    manifest_hash=manifest_hash,
                    reason=collected.reason,
                )
            )
        return tuple(results)
    finally:
        _release_worker_lock(lock)


def _recovered_target_run(
    *,
    target: KisPaperPrivateIntradayTarget,
    snapshots: list[_RecoveredSnapshot],
) -> KisPaperPrivateIntradayBackfillRun:
    latest = snapshots[-1]
    return KisPaperPrivateIntradayBackfillRun(
        status="recovered",
        target_key=target.target_key,
        row_count=sum(int(item.chunk["row_count"]) for item in snapshots),
        exact_overlap_rows=sum(int(item.chunk["exact_overlap_rows"]) for item in snapshots),
        manifest_path=latest.manifest_path,
        manifest_hash=latest.manifest_hash,
        reason=(
            str(latest.chunk["reason"])
            if latest.chunk["reason"] is not None
            else None
        ),
    )


def _collect_target(
    *,
    client: KisPaperPrivateIntradayClient,
    target: KisPaperPrivateIntradayTarget,
    input_cursor: KisPaperPrivateIntradayCursor | None,
    pages_per_target: int,
    before_request: Callable[[], None],
) -> _CollectedTarget:
    rows_by_key: dict[str, KisPaperMinuteRawBar] = {}
    pages: list[dict[str, object]] = []
    duplicate_rows = 0
    cursor = input_cursor
    try:
        for page_number in range(1, pages_per_target + 1):
            query = KisPaperMinuteQuery(
                exchange=target.exchange,
                symbol=target.symbol,
                continuation_next=cursor.next_value if cursor is not None else None,
                continuation_key=cursor.keyb if cursor is not None else None,
            )
            page = client.fetch_minute_page(query, before_request=before_request)
            if not page.bars:
                raise KisPaperMarketDataError("minute_response_empty")
            prospective_rows = dict(rows_by_key)
            prospective_duplicates = 0
            for row in page.bars:
                key = _row_key(row)
                prior = prospective_rows.get(key)
                if prior is None:
                    prospective_rows[key] = row
                elif _row_fingerprint(prior) == _row_fingerprint(row):
                    prospective_duplicates += 1
                else:
                    raise _CandidateBatchDuplicateConflict("minute_duplicate_conflict")
            next_cursor = _cursor_from_page(page)
            if next_cursor is not None and next_cursor == cursor:
                raise KisPaperMarketDataError("minute_cursor_stalled")
            # A page joins the durable candidate only after its cursor and all
            # same-page duplicates have been validated.
            rows_by_key = prospective_rows
            duplicate_rows += prospective_duplicates
            pages.append(_page_document(page=page, page_number=page_number))
            if next_cursor is None:
                cursor = None
                break
            cursor = next_cursor
    except KisPaperMarketDataError as error:
        reason = sanitize_kis_paper_private_intraday_failure_reason(error)
        conflict_origin: _ConflictOrigin | None = (
            "candidate_batch"
            if isinstance(error, _CandidateBatchDuplicateConflict)
            else None
        )
        # A conflicting candidate batch has no trustworthy prefix. Keeping an
        # earlier page would let an invalid batch later complete a session.
        if not rows_by_key or conflict_origin == "candidate_batch":
            return _CollectedTarget(
                target=target,
                input_cursor=input_cursor,
                output_cursor=input_cursor,
                rows=(),
                page_documents=tuple(pages),
                exact_duplicate_rows=duplicate_rows,
                status="rejected",
                reason=reason,
                conflict_origin=conflict_origin,
            )
        return _CollectedTarget(
            target=target,
            input_cursor=input_cursor,
            output_cursor=cursor,
            rows=tuple(rows_by_key[key] for key in sorted(rows_by_key)),
            page_documents=tuple(pages),
            exact_duplicate_rows=duplicate_rows,
            status="partial",
            reason=reason,
            conflict_origin=conflict_origin,
        )
    return _CollectedTarget(
        target=target,
        input_cursor=input_cursor,
        output_cursor=cursor,
        rows=tuple(rows_by_key[key] for key in sorted(rows_by_key)),
        page_documents=tuple(pages),
        exact_duplicate_rows=duplicate_rows,
        status="collected",
        reason=None,
    )


def sanitize_kis_paper_private_intraday_failure_reason(value: BaseException | str) -> str:
    reason = str(value)
    return reason if reason in _SAFE_FAILURE_REASONS else "private_intraday_collector_error"


def _record_target_last_observation(
    *,
    target_state: dict[str, object],
    reason: str | None,
    observed_at_utc: str,
    conflict_origin: _ConflictOrigin | None = None,
    origin_recorded: bool = True,
) -> None:
    if reason == "minute_duplicate_conflict":
        if not origin_recorded:
            if conflict_origin is not None:
                raise ValueError("private intraday conflict origin is invalid")
            target_state.pop("last_conflict_origin", None)
        elif conflict_origin not in {"candidate_batch", "retained_cache"}:
            raise ValueError("private intraday conflict origin is invalid")
        else:
            target_state["last_conflict_origin"] = conflict_origin
    elif conflict_origin is not None:
        raise ValueError("private intraday conflict origin is invalid")
    else:
        target_state["last_conflict_origin"] = None
    target_state["last_reason"] = reason
    target_state["last_observed_at_utc"] = observed_at_utc


def _cursor_from_page(page: KisPaperMinutePage) -> KisPaperPrivateIntradayCursor | None:
    if page.next_cursor is None:
        return None
    oldest = min(page.bars, key=_exchange_stamp)
    try:
        return KisPaperPrivateIntradayCursor(
            next_value=page.next_cursor,
            keyb=_one_exchange_minute_before(oldest),
        )
    except ValueError as error:
        raise KisPaperMarketDataError("minute_cursor_invalid") from error


def _one_exchange_minute_before(row: KisPaperMinuteRawBar) -> str:
    try:
        previous = datetime.strptime(
            f"{row.exchange_date}{row.exchange_time}", "%Y%m%d%H%M%S"
        ) - timedelta(minutes=1)
    except ValueError as error:
        raise KisPaperMarketDataError("minute_cursor_invalid") from error
    return previous.strftime("%Y%m%d%H%M%S")


def _page_document(*, page: KisPaperMinutePage, page_number: int) -> dict[str, object]:
    if page_number <= 0:
        raise ValueError("private intraday page number is invalid")
    exchange_stamps = [_exchange_stamp(row) for row in page.bars]
    korea_stamps = [_korea_stamp(row) for row in page.bars]
    return {
        "index": page_number,
        "row_count": len(page.bars),
        "newest_exchange_timestamp": max(exchange_stamps),
        "oldest_exchange_timestamp": min(exchange_stamps),
        "newest_korea_timestamp": max(korea_stamps),
        "oldest_korea_timestamp": min(korea_stamps),
        "continuation_available": page.next_cursor is not None,
        "more": page.more,
    }


def _chunk_document(
    *,
    target: KisPaperPrivateIntradayTarget,
    collected: _CollectedTarget,
    observed_at: datetime,
    prior_exact_overlap: int,
    collection_scope: _CollectionScope,
) -> dict[str, object]:
    input_cursor = (
        collected.input_cursor.as_document() if collected.input_cursor is not None else None
    )
    output_cursor = (
        collected.output_cursor.as_document() if collected.output_cursor is not None else None
    )
    rows = collected.rows
    fingerprints = {_row_key(row): _row_fingerprint(row) for row in rows}
    return {
        "chunk_key": _chunk_key(
            target=target,
            input_cursor=input_cursor,
            row_fingerprints=fingerprints,
        ),
        "outcome": "committed" if collected.status == "collected" else "partial",
        "input_cursor": input_cursor,
        "output_cursor": output_cursor,
        "manifest_path": None,
        "manifest_hash": None,
        "raw_sha256": None,
        "raw_market_data_retained": True,
        "row_count": len(rows),
        "row_fingerprints": fingerprints,
        "exact_overlap_rows": collected.exact_duplicate_rows + prior_exact_overlap,
        "conflicting_overlap_rows": 0,
        "collected_at_utc": _format_utc(observed_at),
        "reason": collected.reason,
        "conflict_origin": collected.conflict_origin,
        "collection_scope": collection_scope,
    }


def _write_snapshot(
    *,
    root: Path,
    target: KisPaperPrivateIntradayTarget,
    collected: _CollectedTarget,
    chunk: dict[str, object],
    code_revision: str,
    observed_at: datetime,
    run_id: str,
) -> tuple[Path, str]:
    snapshots_root = _snapshot_root(root)
    snapshot_name = f"snapshot={run_id}-{target.symbol.lower()}-{target.exchange.lower()}-m1-v1"
    target_root = snapshots_root / snapshot_name
    if target_root.exists() or target_root.is_symlink():
        raise FileExistsError("private intraday cache destination already exists")
    staging = snapshots_root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        raw_payload = _compressed_raw_minute_csv(collected.rows)
        raw_relative = "raw/ohlcv_1m.csv.gz"
        raw_path = staging / raw_relative
        raw_path.parent.mkdir()
        _write_bytes_and_sync(raw_path, raw_payload)
        raw_hash = "sha256:" + hashlib.sha256(raw_payload).hexdigest()
        chunk["raw_sha256"] = raw_hash
        chunk["manifest_path"] = (
            f"{KIS_PAPER_PRIVATE_INTRADAY_SNAPSHOT_DIRECTORY}/{snapshot_name}/manifest.json"
        )
        manifest = _snapshot_manifest(
            snapshot_name=snapshot_name,
            target=target,
            collected=collected,
            chunk=chunk,
            code_revision=code_revision,
            observed_at=observed_at,
            raw_document={
                "path": raw_relative,
                "sha256": raw_hash,
                "size_bytes": len(raw_payload),
                "format": "csv.gz",
                "ordering": "korea_timestamp_ascending",
                "columns": list(_RAW_MINUTE_COLUMNS),
            },
        )
        manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_bytes_and_sync(staging / "manifest.json", manifest_payload)
        os.replace(staging, target_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target_root / "manifest.json", "sha256:" + hashlib.sha256(manifest_payload).hexdigest()


def _snapshot_manifest(
    *,
    snapshot_name: str,
    target: KisPaperPrivateIntradayTarget,
    collected: _CollectedTarget,
    chunk: Mapping[str, object],
    code_revision: str,
    observed_at: datetime,
    raw_document: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_intraday_cache",
        "dataset_id": f"kis.paper.private.intraday.{snapshot_name}",
        "immutable_snapshot": True,
        "backfill_version": KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
        "code_revision": code_revision,
        "collected_at_utc": _format_utc(observed_at),
        "status": collected.status,
        "source": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "inquire-time-itemchartprice",
            "symbol": target.symbol,
            "exchange": target.exchange,
            "bar_interval": "1m",
        },
        "timestamp_contract": {
            "canonical_basis": "korea_timestamp",
            "timezone": "Asia/Seoul",
            "exchange_timestamp_semantics": "observed_unqualified",
            "canonical_start_policy": "korea_timestamp_projected_to_utc",
            "completed_bar_rule": (
                "source_timestamp_plus_1m_at_or_before_collection_minute"
            ),
        },
        "pages": list(collected.page_documents),
        "deduplication": {
            "key": ["kymd", "khms"],
            "input_row_count": sum(int(page["row_count"]) for page in collected.page_documents),
            "unique_row_count": len(collected.rows),
            "exact_duplicate_rows_removed": collected.exact_duplicate_rows,
            "conflict_policy": "reject_cursor_advance",
        },
        "files": {"raw_minute_rows": dict(raw_document)},
        "backfill": {"index_chunk": dict(chunk)},
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
            "response_bodies_persisted": False,
        },
    }


def _compressed_raw_minute_csv(rows: tuple[KisPaperMinuteRawBar, ...]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as gzip_handle:
        with io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="") as text_handle:
            writer = csv.DictWriter(
                text_handle,
                fieldnames=_RAW_MINUTE_COLUMNS,
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row.as_document())
    return buffer.getvalue()


def _read_or_create_index(
    root: Path,
    *,
    hydrate_source_exhaustion: bool,
) -> dict[str, object]:
    path = root / KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME
    if not path.exists():
        index: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_private_intraday_backfill",
            "backfill_version": KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
            "generation": 0,
            "targets": [
                {
                    "target_key": KisPaperPrivateIntradayTarget(*target).target_key,
                    "symbol": target[0],
                    "exchange": target[1],
                    "next_cursor": None,
                    "last_reason": None,
                    "last_conflict_origin": None,
                    "last_observed_at_utc": None,
                    "chunks": [],
                }
                for target in KIS_PAPER_PRIVATE_INTRADAY_TARGETS
            ],
        }
        _write_index(root=root, index=index)
        return index
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private intraday index is invalid") from error
    if not isinstance(loaded, dict):
        raise ValueError("private intraday index is invalid")
    _validate_index(loaded)
    if hydrate_source_exhaustion and _hydrate_source_exhaustion_state(loaded):
        _write_index(root=root, index=loaded)
    return loaded


def _validate_index(index: Mapping[str, object]) -> None:
    try:
        _validate_shared_index_metadata(
            index,
            expected_targets=KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
        )
    except ValueError as error:
        raise ValueError("private intraday index is invalid") from error


def _validate_chunk(*, chunk: object, target: KisPaperPrivateIntradayTarget) -> None:
    try:
        _validate_shared_index_metadata(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "kis_paper_private_intraday_backfill",
                "backfill_version": KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
                "generation": 0,
                "targets": [
                    {
                        "target_key": target.target_key,
                        "symbol": target.symbol,
                        "exchange": target.exchange,
                        "next_cursor": None,
                        "last_reason": None,
                        "last_conflict_origin": None,
                        "last_observed_at_utc": None,
                        "chunks": [chunk],
                    }
                ],
            },
            expected_targets=((target.symbol, target.exchange),),
        )
    except ValueError as error:
        raise ValueError("private intraday index is invalid") from error


def _validate_shared_index_metadata(
    index: Mapping[str, object],
    *,
    expected_targets: tuple[tuple[str, str], ...],
) -> None:
    """Defer the Data import until this execution module is fully initialized."""

    from thericher_v2.data.kis_paper_intraday_index_metadata import (
        validate_kis_paper_private_intraday_v1_index_metadata,
    )

    validate_kis_paper_private_intraday_v1_index_metadata(
        index,
        expected_targets=expected_targets,
    )


def _is_unretained_marker(chunk: object) -> bool:
    """Keep old non-data observations out of cache semantics."""

    from thericher_v2.data.kis_paper_intraday_index_metadata import (
        is_kis_paper_private_intraday_v1_unretained_marker,
    )

    return is_kis_paper_private_intraday_v1_unretained_marker(chunk)


def _is_candidate_batch_conflicted_chunk(chunk: object) -> bool:
    """Keep historical rows from a rejected candidate batch out of collection state."""

    return (
        isinstance(chunk, Mapping)
        and chunk.get("outcome") == "partial"
        and chunk.get("reason") == "minute_duplicate_conflict"
        and chunk.get("conflict_origin") == "candidate_batch"
    )


def _is_ignored_collection_chunk(chunk: object) -> bool:
    return _is_unretained_marker(chunk) or _is_candidate_batch_conflicted_chunk(chunk)


def _remove_candidate_batch_conflicted_chunks(
    index: dict[str, object], *, resume_cursor: bool
) -> bool:
    """Remove invalid legacy candidates from active state without deleting evidence files."""

    changed = False
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise ValueError("private intraday index is invalid")
    for target_state in targets:
        if not isinstance(target_state, dict):
            raise ValueError("private intraday index is invalid")
        chunks = target_state.get("chunks")
        if not isinstance(chunks, list):
            raise ValueError("private intraday index is invalid")
        active_chunks = [
            chunk for chunk in chunks if not _is_candidate_batch_conflicted_chunk(chunk)
        ]
        if len(active_chunks) == len(chunks):
            continue
        target_state["chunks"] = active_chunks
        if resume_cursor:
            target_state["next_cursor"] = _last_active_output_cursor(active_chunks)
        changed = True
    return changed


def _last_active_output_cursor(chunks: list[object]) -> dict[str, str] | None:
    for chunk in reversed(chunks):
        if _is_unretained_marker(chunk):
            continue
        if not isinstance(chunk, Mapping):
            raise ValueError("private intraday index is invalid")
        cursor = KisPaperPrivateIntradayCursor.from_document(chunk.get("output_cursor"))
        return cursor.as_document() if cursor is not None else None
    return None


def _index_target(
    *, index: Mapping[str, object], target: KisPaperPrivateIntradayTarget
) -> dict[str, object]:
    targets = index["targets"]
    assert isinstance(targets, list)
    for state in targets:
        if isinstance(state, dict) and state.get("target_key") == target.target_key:
            return state
    raise ValueError("private intraday index target is missing")


def _target_source_is_exhausted(target_state: Mapping[str, object]) -> bool:
    return (
        target_state.get("next_cursor") is None
        and target_state.get("last_reason") == "source_exhausted"
    )


def _collected_target_source_is_exhausted(
    *,
    collected: _CollectedTarget,
    resume_cursor: bool,
) -> bool:
    return (
        resume_cursor
        and collected.status == "collected"
        and collected.output_cursor is None
    )


def _hydrate_source_exhaustion_state(index: dict[str, object]) -> bool:
    """Upgrade old terminal cursor facts without issuing another source request."""

    changed = False
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise ValueError("private intraday index is invalid")
    for target_state in targets:
        if not isinstance(target_state, dict) or target_state.get("next_cursor") is not None:
            continue
        if target_state.get("last_reason") is not None:
            continue
        chunks = target_state.get("chunks")
        if not isinstance(chunks, list):
            raise ValueError("private intraday index is invalid")
        retained_chunks = [
            chunk for chunk in chunks if not _is_ignored_collection_chunk(chunk)
        ]
        if not retained_chunks:
            continue
        last_chunk = retained_chunks[-1]
        if (
            isinstance(last_chunk, Mapping)
            and last_chunk.get("outcome") == "committed"
            and last_chunk.get("output_cursor") is None
        ):
            target_state["last_reason"] = "source_exhausted"
            target_state["last_conflict_origin"] = None
            changed = True
    return changed


def _target_fingerprints(target_state: Mapping[str, object]) -> dict[str, str]:
    rows: dict[str, str] = {}
    chunks = target_state.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("private intraday index is invalid")
    for chunk in chunks:
        if _is_ignored_collection_chunk(chunk):
            continue
        if not isinstance(chunk, Mapping):
            raise ValueError("private intraday index is invalid")
        fingerprints = chunk.get("row_fingerprints")
        if not isinstance(fingerprints, Mapping):
            raise ValueError("private intraday index is invalid")
        for key, value in fingerprints.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("private intraday index is invalid")
            prior = rows.get(key)
            if prior is not None and prior != value:
                raise ValueError("private intraday index has conflicting retained rows")
            rows[key] = value
    return rows


def _has_chunk(*, target_state: Mapping[str, object], candidate: Mapping[str, object]) -> bool:
    chunks = target_state.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("private intraday index is invalid")
    candidate_key = candidate.get("chunk_key")
    candidate_rows = candidate.get("row_fingerprints")
    return any(
        isinstance(chunk, Mapping)
        and not _is_ignored_collection_chunk(chunk)
        and (
            chunk.get("chunk_key") == candidate_key
            or (
                chunk.get("input_cursor") == candidate.get("input_cursor")
                and chunk.get("row_fingerprints") == candidate_rows
            )
        )
        for chunk in chunks
    )


def _conflicting_retained_chunk_keys(
    *,
    rows: tuple[KisPaperMinuteRawBar, ...],
    target_state: Mapping[str, object],
) -> tuple[str, ...]:
    """Return active snapshots whose retained rows disagree with a candidate page."""

    candidate_fingerprints = {_row_key(row): _row_fingerprint(row) for row in rows}
    chunks = target_state.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("private intraday index is invalid")
    conflicts: list[str] = []
    for chunk in chunks:
        if _is_ignored_collection_chunk(chunk):
            continue
        if not isinstance(chunk, Mapping):
            raise ValueError("private intraday index is invalid")
        chunk_key = chunk.get("chunk_key")
        fingerprints = chunk.get("row_fingerprints")
        if not isinstance(chunk_key, str) or not isinstance(fingerprints, Mapping):
            raise ValueError("private intraday index is invalid")
        if any(
            candidate != fingerprints.get(row_key)
            for row_key, candidate in candidate_fingerprints.items()
            if row_key in fingerprints
        ):
            conflicts.append(chunk_key)
    return tuple(conflicts)


def _can_quarantine_retained_head_conflicts(
    *,
    collected: _CollectedTarget,
    target_state: Mapping[str, object],
    conflicting_chunk_keys: tuple[str, ...],
    quarantine_retained_head_conflicts: bool,
) -> bool:
    """Quarantine only complete fresh head pages, never cursor-backed history."""

    if (
        not quarantine_retained_head_conflicts
        or collected.status != "collected"
        or not conflicting_chunk_keys
    ):
        return False
    chunks = target_state.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("private intraday index is invalid")
    conflicts = set(conflicting_chunk_keys)
    matching_chunks = [
        chunk
        for chunk in chunks
        if (
            isinstance(chunk, Mapping)
            and not _is_ignored_collection_chunk(chunk)
            and chunk.get("chunk_key") in conflicts
        )
    ]
    if len(matching_chunks) != len(conflicts):
        raise ValueError("private intraday index is invalid")
    return all(_is_quarantinable_head_snapshot(chunk) for chunk in matching_chunks)


def _is_quarantinable_head_snapshot(chunk: Mapping[str, object]) -> bool:
    return (
        chunk.get("raw_market_data_retained") is True
        and chunk.get("collection_scope") == "head"
        and chunk.get("input_cursor") is None
        and chunk.get("output_cursor") is None
        and chunk.get("outcome") in {"committed", "partial"}
        and isinstance(chunk.get("chunk_key"), str)
        and _is_sha256(chunk.get("manifest_hash"))
        and _is_sha256(chunk.get("raw_sha256"))
    )


def _quarantine_retained_head_chunks(
    *, target_state: dict[str, object], conflicting_chunk_keys: tuple[str, ...]
) -> None:
    """Exclude conflicted head snapshots without deleting their immutable evidence."""

    from thericher_v2.data.kis_paper_intraday_index_metadata import (
        KIS_PAPER_PRIVATE_INTRADAY_QUARANTINED_HEAD_SNAPSHOT_NOTE,
    )

    chunks = target_state.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("private intraday index is invalid")
    conflicts = set(conflicting_chunk_keys)
    quarantined: list[object] = []
    for chunk in chunks:
        if (
            not isinstance(chunk, Mapping)
            or _is_ignored_collection_chunk(chunk)
            or chunk.get("chunk_key") not in conflicts
        ):
            quarantined.append(chunk)
            continue
        chunk_key = chunk.get("chunk_key")
        manifest_hash = chunk.get("manifest_hash")
        raw_hash = chunk.get("raw_sha256")
        if (
            not isinstance(chunk_key, str)
            or not _is_sha256(manifest_hash)
            or not _is_sha256(raw_hash)
        ):
            raise ValueError("private intraday index is invalid")
        quarantined.append(
            {
                "raw_market_data_retained": False,
                "historical_note": KIS_PAPER_PRIVATE_INTRADAY_QUARANTINED_HEAD_SNAPSHOT_NOTE,
                "quarantined_chunk_key": chunk_key,
                "quarantined_manifest_hash": manifest_hash,
                "quarantined_raw_sha256": raw_hash,
            }
        )
    target_state["chunks"] = quarantined


def _is_quarantined_head_snapshot_marker_for(
    marker: object,
    *,
    chunk_key: object,
    manifest_hash: str,
    raw_hash: object,
) -> bool:
    from thericher_v2.data.kis_paper_intraday_index_metadata import (
        KIS_PAPER_PRIVATE_INTRADAY_QUARANTINED_HEAD_SNAPSHOT_NOTE,
        is_kis_paper_private_intraday_v1_unretained_marker,
    )

    return (
        is_kis_paper_private_intraday_v1_unretained_marker(marker)
        and isinstance(marker, Mapping)
        and marker.get("historical_note")
        == KIS_PAPER_PRIVATE_INTRADAY_QUARANTINED_HEAD_SNAPSHOT_NOTE
        and marker.get("quarantined_chunk_key") == chunk_key
        and marker.get("quarantined_manifest_hash") == manifest_hash
        and marker.get("quarantined_raw_sha256") == raw_hash
    )


def _recover_orphan_snapshots(
    *, root: Path, index: dict[str, object]
) -> tuple[_RecoveredSnapshot, ...]:
    snapshots_root = _snapshot_root(root)
    recovered_snapshots: list[_RecoveredSnapshot] = []
    for manifest_path in sorted(snapshots_root.glob("snapshot=*/manifest.json")):
        if manifest_path.is_symlink():
            raise ValueError("private intraday snapshot path is invalid")
        manifest_hash = _sha256(manifest_path.read_bytes())
        manifest = _read_manifest(manifest_path)
        if manifest.get("kind") != "kis_paper_private_intraday_cache":
            continue
        source = manifest.get("source")
        backfill = manifest.get("backfill")
        if not isinstance(source, Mapping) or not isinstance(backfill, Mapping):
            raise ValueError("private intraday snapshot is invalid")
        target = KisPaperPrivateIntradayTarget(
            symbol=str(source.get("symbol", "")), exchange=str(source.get("exchange", ""))
        )
        chunk = backfill.get("index_chunk")
        if not isinstance(chunk, dict):
            raise ValueError("private intraday snapshot is invalid")
        if _is_candidate_batch_conflicted_chunk(chunk):
            continue
        state = _index_target(index=index, target=target)
        chunks = state["chunks"]
        assert isinstance(chunks, list)
        if any(
            _is_quarantined_head_snapshot_marker_for(
                existing,
                chunk_key=chunk.get("chunk_key"),
                manifest_hash=manifest_hash,
                raw_hash=chunk.get("raw_sha256"),
            )
            for existing in chunks
        ):
            continue
        if any(
            isinstance(existing, dict)
            and not _is_ignored_collection_chunk(existing)
            and existing.get("chunk_key") == chunk["chunk_key"]
            for existing in chunks
        ):
            continue
        raw_document = _manifest_raw_document(manifest)
        raw_path = _resolve_child(root=manifest_path.parent, relative=str(raw_document["path"]))
        raw_bytes = raw_path.read_bytes()
        if "sha256:" + hashlib.sha256(raw_bytes).hexdigest() != raw_document["sha256"]:
            raise ValueError("private intraday snapshot raw hash is invalid")
        if chunk.get("raw_sha256") != raw_document["sha256"]:
            raise ValueError("private intraday snapshot is invalid")
        recovered_chunk = dict(chunk)
        recovered_chunk["manifest_path"] = str(manifest_path.relative_to(root)).replace(
            "\\", "/"
        )
        recovered_chunk["manifest_hash"] = manifest_hash
        _validate_chunk(chunk=recovered_chunk, target=target)
        chunks.append(recovered_chunk)
        output_cursor = KisPaperPrivateIntradayCursor.from_document(
            recovered_chunk["output_cursor"]
        )
        state["next_cursor"] = output_cursor.as_document() if output_cursor is not None else None
        recovered_reason = recovered_chunk["reason"]
        if recovered_reason is not None and not isinstance(recovered_reason, str):
            raise ValueError("private intraday snapshot is invalid")
        recovered_origin = recovered_chunk.get("conflict_origin")
        _record_target_last_observation(
            target_state=state,
            reason=recovered_reason,
            conflict_origin=recovered_origin if isinstance(recovered_origin, str) else None,
            origin_recorded="conflict_origin" in recovered_chunk,
            observed_at_utc=str(recovered_chunk["collected_at_utc"]),
        )
        index["generation"] = int(index["generation"]) + 1
        recovered_snapshots.append(
            _RecoveredSnapshot(
                target=target,
                manifest_path=manifest_path,
                manifest_hash=str(recovered_chunk["manifest_hash"]),
                chunk=recovered_chunk,
            )
        )
    return tuple(recovered_snapshots)


def _attest_committed_snapshots(*, root: Path, index: Mapping[str, object]) -> None:
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise ValueError("private intraday index is invalid")
    for state in targets:
        if not isinstance(state, Mapping):
            raise ValueError("private intraday index is invalid")
        target = KisPaperPrivateIntradayTarget(
            symbol=str(state.get("symbol", "")),
            exchange=str(state.get("exchange", "")),
        )
        chunks = state.get("chunks")
        if not isinstance(chunks, list):
            raise ValueError("private intraday index is invalid")
        for chunk in chunks:
            if _is_ignored_collection_chunk(chunk):
                continue
            _attest_snapshot_chunk(root=root, target=target, chunk=chunk)


def _attest_snapshot_chunk(
    *,
    root: Path,
    target: KisPaperPrivateIntradayTarget,
    chunk: object,
) -> None:
    _validate_chunk(chunk=chunk, target=target)
    assert isinstance(chunk, Mapping)
    manifest_path = _resolve_child(root=root, relative=str(chunk["manifest_path"]))
    manifest_bytes = manifest_path.read_bytes()
    if _sha256(manifest_bytes) != chunk["manifest_hash"]:
        raise ValueError("private intraday manifest hash is invalid")
    manifest = _read_manifest(manifest_path)
    source = manifest.get("source")
    backfill = manifest.get("backfill")
    manifest_chunk = backfill.get("index_chunk") if isinstance(backfill, Mapping) else None
    if (
        not isinstance(source, Mapping)
        or source.get("symbol") != target.symbol
        or source.get("exchange") != target.exchange
        or not isinstance(manifest_chunk, Mapping)
        or manifest_chunk.get("chunk_key") != chunk["chunk_key"]
    ):
        raise ValueError("private intraday snapshot is invalid")
    raw_document = _manifest_raw_document(manifest)
    raw_path = _resolve_child(root=manifest_path.parent, relative=str(raw_document["path"]))
    raw_bytes = raw_path.read_bytes()
    raw_hash = _sha256(raw_bytes)
    if raw_hash != raw_document["sha256"] or raw_hash != chunk["raw_sha256"]:
        raise ValueError("private intraday snapshot raw hash is invalid")
    observed_rows = _decode_snapshot_rows(raw_bytes)
    expected_fingerprints = chunk["row_fingerprints"]
    if not isinstance(expected_fingerprints, Mapping):
        raise ValueError("private intraday snapshot is invalid")
    actual_fingerprints = {_row_key(row): _row_fingerprint(row) for row in observed_rows}
    if (
        len(observed_rows) != int(chunk["row_count"])
        or len(actual_fingerprints) != len(observed_rows)
        or dict(expected_fingerprints) != actual_fingerprints
    ):
        raise ValueError("private intraday snapshot row fingerprint is invalid")


def _decode_snapshot_rows(raw_bytes: bytes) -> tuple[KisPaperMinuteRawBar, ...]:
    try:
        with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _RAW_MINUTE_COLUMNS:
                raise ValueError("private intraday snapshot is invalid")
            rows = tuple(
                KisPaperMinuteRawBar(
                    exchange_date=str(record["xymd"]),
                    exchange_time=str(record["xhms"]),
                    korea_date=str(record["kymd"]),
                    korea_time=str(record["khms"]),
                    open=str(record["open"]),  # type: ignore[arg-type]
                    high=str(record["high"]),  # type: ignore[arg-type]
                    low=str(record["low"]),  # type: ignore[arg-type]
                    last=str(record["last"]),  # type: ignore[arg-type]
                    volume=str(record["evol"]),  # type: ignore[arg-type]
                )
                for record in reader
            )
    except (OSError, UnicodeDecodeError, csv.Error, KeyError, ValueError) as error:
        if isinstance(error, ValueError) and str(error) == "private intraday snapshot is invalid":
            raise
        raise ValueError("private intraday snapshot is invalid") from error
    if not rows:
        raise ValueError("private intraday snapshot is invalid")
    return rows


def _manifest_raw_document(manifest: Mapping[str, object]) -> dict[str, object]:
    files = manifest.get("files")
    document = files.get("raw_minute_rows") if isinstance(files, Mapping) else None
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("path"), str)
        or not _is_sha256(document.get("sha256"))
    ):
        raise ValueError("private intraday snapshot is invalid")
    return document


def _read_manifest(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private intraday snapshot is invalid") from error
    if not isinstance(loaded, dict):
        raise ValueError("private intraday snapshot is invalid")
    return loaded


def _write_index(*, root: Path, index: Mapping[str, object]) -> None:
    _validate_index(index)
    payload = (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8")
    target = root / KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME
    staging = root / f".{target.name}.{uuid.uuid4().hex}.stage"
    try:
        _write_bytes_and_sync(staging, payload)
        os.replace(staging, target)
    finally:
        if staging.exists():
            staging.unlink()


def _backfill_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = Path(cache_root).resolve()
    if root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("private intraday cache root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    backfill_root = root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    if backfill_root.is_symlink():
        raise ValueError("private intraday cache root is invalid")
    backfill_root.mkdir(exist_ok=True)
    return backfill_root.resolve()


def _snapshot_root(root: Path) -> Path:
    snapshots_root = root / KIS_PAPER_PRIVATE_INTRADAY_SNAPSHOT_DIRECTORY
    if snapshots_root.is_symlink():
        raise ValueError("private intraday snapshot path is invalid")
    try:
        snapshots_root.mkdir(exist_ok=True)
    except OSError as error:
        raise ValueError("private intraday snapshot path is invalid") from error
    if not snapshots_root.is_dir() or snapshots_root.is_symlink():
        raise ValueError("private intraday snapshot path is invalid")
    return _resolve_child(root=root, relative=KIS_PAPER_PRIVATE_INTRADAY_SNAPSHOT_DIRECTORY)


def _resolve_child(*, root: Path, relative: str) -> Path:
    candidate = root / relative
    if not relative or candidate.is_symlink():
        raise ValueError("private intraday snapshot path is invalid")
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("private intraday snapshot path is invalid")
    return resolved


def _acquire_worker_lock(root: Path) -> _WorkerLock | None:
    path = root / KIS_PAPER_PRIVATE_INTRADAY_LOCK_FILENAME
    if path.is_symlink():
        raise ValueError("private intraday worker lock is invalid")
    handle = path.open("a+b")
    if not _try_lock_handle(handle):
        handle.close()
        return None
    return _WorkerLock(path=path, handle=handle)


def _try_lock_handle(handle: io.BufferedRandom) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _release_worker_lock(lock: _WorkerLock | None) -> None:
    if lock is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            lock.handle.seek(0)
            msvcrt.locking(lock.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        lock.handle.close()


@dataclass
class _RequestPacer:
    sleeper: Callable[[float], None]
    monotonic_clock: Callable[[], float]
    last_request_started: float | None = None

    def wait_before_request(self) -> None:
        now = self.monotonic_clock()
        if self.last_request_started is not None:
            remaining = KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS - (
                now - self.last_request_started
            )
            if remaining > 0:
                self.sleeper(remaining)
        else:
            # The token POST happens immediately before the first minute GET.
            self.sleeper(KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS)
        self.last_request_started = self.monotonic_clock()


def _row_key(row: KisPaperMinuteRawBar) -> str:
    return _korea_stamp(row)


def _row_fingerprint(row: KisPaperMinuteRawBar) -> str:
    payload = json.dumps(row.as_document(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _exchange_stamp(row: KisPaperMinuteRawBar) -> str:
    return f"{row.exchange_date}T{row.exchange_time}"


def _korea_stamp(row: KisPaperMinuteRawBar) -> str:
    return f"{row.korea_date}T{row.korea_time}"


def _chunk_key(
    *,
    target: KisPaperPrivateIntradayTarget,
    input_cursor: object,
    row_fingerprints: Mapping[str, str],
) -> str:
    payload = json.dumps(
        {
            "backfill_version": KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
            "input_cursor": input_cursor,
            "row_fingerprints": dict(sorted(row_fingerprints.items())),
            "target_key": target.target_key,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _run_id(*, observed_at: datetime, generation: int) -> str:
    return f"{observed_at:%Y%m%dT%H%M%SZ}-{generation:06d}"


def _format_utc(value: datetime) -> str:
    return require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    prefix, separator, digest = value.partition(":")
    return (
        prefix == "sha256"
        and separator == ":"
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _write_bytes_and_sync(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

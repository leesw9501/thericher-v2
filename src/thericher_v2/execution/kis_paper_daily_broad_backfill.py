"""Resumable KIS Paper D1 backfill for a current-listing NAS registry.

The worker owns a new cache and index.  It never alters the terminal ETF or
fixed-NAS history contracts.  Registry construction stays offline in the Data
layer; this module only consumes a hash-attested registry and collects typed
unadjusted daily bars through the existing Paper market-data client.
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

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_daily_broad_registry import (
    KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
    KisPaperDailyBroadRegistry,
    load_kis_paper_daily_broad_registry,
    write_kis_paper_daily_broad_registry,
)

from .kis_market_data import KisPaperMarketDataClient
from .kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from .kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectionTarget,
    private_daily_cache_would_cross_free_space_floor,
    run_bounded_kis_paper_private_daily_collection,
    write_kis_paper_private_daily_cache,
)

KIS_PAPER_DAILY_BROAD_BACKFILL_VERSION = "kis-paper-daily-nas-broad-v1"
KIS_PAPER_DAILY_BROAD_BACKFILL_OBJECTIVE_ID = "kis-paper-daily-nas-broad-v1"
KIS_PAPER_DAILY_BROAD_BACKFILL_INITIAL_ANCHOR_DATE = "20260728"
KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_CHUNKS = 8
KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_RUNTIME = timedelta(minutes=15)
KIS_PAPER_DAILY_BROAD_BACKFILL_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-broad/v1"
)
KIS_PAPER_DAILY_BROAD_BACKFILL_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/kis-paper-daily-nas-broad-v1"
)
KIS_PAPER_DAILY_BROAD_BACKFILL_INDEX_FILENAME = "index.json"
KIS_PAPER_DAILY_BROAD_BACKFILL_LOCK_FILENAME = "worker.lock"
KIS_PAPER_DAILY_BROAD_BACKFILL_RETRY_DELAY = timedelta(minutes=2)

_TARGET_STATES = frozenset({"ready", "deferred", "source_limited", "complete"})
_TERMINAL_STATES = frozenset({"source_limited", "complete"})
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
_SOURCE_LIMIT_AFTER_REPEATS = frozenset({"daily_response_invalid", "no_cursor_progress"})
_SHARED_STOP_REASONS = frozenset(
    {"auth_rejected", "auth_response_invalid", "rate_limited", "token_request_not_due"}
)


class KisPaperDailyBroadBackfillError(RuntimeError):
    """A non-secret broad D1 backfill contract failure."""


@dataclass(frozen=True)
class KisPaperDailyBroadTargetState:
    """Source-safe current state for one registry target."""

    target_key: str
    state: Literal["ready", "deferred", "source_limited", "complete"]
    cursor_date: str
    accepted_page_count: int
    categorical_failure_count: int
    last_reason: str | None

    def __post_init__(self) -> None:
        if (
            not _is_target_key(self.target_key)
            or self.state not in _TARGET_STATES
            or not _is_date(self.cursor_date)
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
        ):
            raise ValueError("broad daily target state is invalid")

    def source_safe_document(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "state": self.state,
            "cursor_date": self.cursor_date,
            "accepted_page_count": self.accepted_page_count,
            "categorical_failure_count": self.categorical_failure_count,
            "last_reason": self.last_reason,
        }


@dataclass(frozen=True)
class KisPaperDailyBroadBackfillRun:
    """Source-safe outcome of one bounded broad collection worker."""

    status: Literal[
        "collected",
        "complete",
        "deferred",
        "busy",
        "storage_floor_would_be_crossed",
    ]
    observed_at: datetime
    completed_at: datetime
    registry_sha256: str
    target_states: tuple[KisPaperDailyBroadTargetState, ...]
    bootstrap_only: bool
    chunk_attempt_count: int
    accepted_page_count: int
    categorical_failure_count: int
    remaining_target_count: int
    next_due: datetime | None
    recovery: Literal["resume", "reconcile", "complete"]
    evidence_sha256: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "completed_at", require_utc(self.completed_at, "completed_at"))
        object.__setattr__(self, "target_states", tuple(self.target_states))
        if (
            self.status
            not in {
                "collected",
                "complete",
                "deferred",
                "busy",
                "storage_floor_would_be_crossed",
            }
            or not _is_sha256(self.registry_sha256)
            or not isinstance(self.bootstrap_only, bool)
            or self.chunk_attempt_count < 0
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
            or self.remaining_target_count < 0
            or self.recovery not in {"resume", "reconcile", "complete"}
        ):
            raise ValueError("broad daily backfill run is invalid")
        if self.next_due is not None:
            object.__setattr__(self, "next_due", require_utc(self.next_due, "next_due"))
        if self.evidence_sha256 is not None and not _is_sha256(self.evidence_sha256):
            raise ValueError("broad daily backfill evidence hash is invalid")

    def source_safe_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_broad_backfill_receipt",
            "scope": {
                "provider": "KIS Open API virtual paper",
                "endpoint": "dailyprice",
                "mode": "off",
                "registry_version": KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
                "registry_sha256": self.registry_sha256,
                "current_listing_only": True,
                "non_pit": True,
                "non_ranking": True,
                "provider_price_data": False,
            },
            "observed_at_utc": _format_utc(self.observed_at),
            "completed_at_utc": _format_utc(self.completed_at),
            "bootstrap_only": self.bootstrap_only,
            "outcome": {
                "status": self.status,
                "recovery": self.recovery,
                "chunk_attempt_count": self.chunk_attempt_count,
                "accepted_page_count": self.accepted_page_count,
                "categorical_failure_count": self.categorical_failure_count,
                "remaining_target_count": self.remaining_target_count,
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
            },
            "artifact_policy": {
                "raw_market_data_in_receipt": False,
                "credentials_in_receipt": False,
                "account_data_in_receipt": False,
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


@dataclass(frozen=True)
class _WorkerLock:
    handle: BinaryIO


def run_kis_paper_daily_broad_backfill(
    *,
    registry: KisPaperDailyBroadRegistry,
    client_factory: Callable[[], KisPaperMarketDataClient],
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    cache_root: Path = KIS_PAPER_DAILY_BROAD_BACKFILL_CACHE_ROOT,
    evidence_root: Path = KIS_PAPER_DAILY_BROAD_BACKFILL_EVIDENCE_ROOT,
    repo_root: Path,
    code_revision: str,
    bootstrap_only: bool = True,
    max_chunks: int = KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_CHUNKS,
    max_runtime: timedelta = KIS_PAPER_DAILY_BROAD_BACKFILL_DEFAULT_MAX_RUNTIME,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> KisPaperDailyBroadBackfillRun:
    """Advance independent current-listing D1 cursors with one reusable client."""

    if (
        type(bootstrap_only) is not bool
        or type(max_chunks) is not int
        or max_chunks <= 0
        or not isinstance(max_runtime, timedelta)
        or max_runtime <= timedelta(0)
    ):
        raise ValueError("broad daily backfill worker bounds are invalid")
    _validate_registry(registry)
    observed_at = require_utc(clock(), "clock")
    root = _cache_root(cache_root=cache_root, repo_root=repo_root)
    artifacts = _artifact_root(evidence_root=evidence_root, repo_root=repo_root)
    write_kis_paper_daily_broad_registry(registry=registry, output_root=root, repo_root=repo_root)
    if load_kis_paper_daily_broad_registry(output_root=root, repo_root=repo_root) != registry:
        raise KisPaperDailyBroadBackfillError("broad daily registry reattestation failed")
    lock = _try_worker_lock(root / KIS_PAPER_DAILY_BROAD_BACKFILL_LOCK_FILENAME)
    if lock is None:
        index = _load_or_initialize_index(root=root, registry=registry, persist=False)
        return _build_run(
            status="busy",
            observed_at=observed_at,
            completed_at=require_utc(clock(), "clock"),
            registry=registry,
            index=index,
            bootstrap_only=bootstrap_only,
            chunk_attempt_count=0,
            accepted_page_count=0,
            categorical_failure_count=0,
            next_due=None,
        )
    try:
        index = _load_or_initialize_index(root=root, registry=registry, persist=True)
        if _migrate_index(index):
            _write_index(root=root, index=index, registry=registry)
        allowed_keys = (
            registry.bootstrap_target_keys if bootstrap_only else registry.target_keys
        )
        active_client: KisPaperMarketDataClient | None = None
        attempted_keys: set[str] = set()
        accepted_page_count = 0
        categorical_failure_count = 0
        chunk_attempt_count = 0
        start_monotonic = monotonic_clock()
        next_due: datetime | None = None
        status: Literal["collected", "complete", "deferred", "storage_floor_would_be_crossed"] = (
            "deferred"
        )

        while chunk_attempt_count < max_chunks:
            if monotonic_clock() - start_monotonic >= max_runtime.total_seconds():
                status = "collected" if accepted_page_count else "deferred"
                break
            external_due = _external_retry_due(
                request_gate=request_gate,
                token_start_gate=token_start_gate,
                token_required=active_client is None,
            )
            if external_due is not None and external_due > require_utc(clock(), "clock"):
                next_due = external_due
                status = "collected" if accepted_page_count else "deferred"
                break
            target = _select_ready_target(
                index=index,
                allowed_keys=allowed_keys,
                attempted_keys=attempted_keys if bootstrap_only else frozenset(),
                observed_at=require_utc(clock(), "clock"),
            )
            if target is None:
                if _allowed_targets_terminal(index, allowed_keys):
                    status = "collected" if bootstrap_only else "complete"
                else:
                    status = "deferred"
                break
            target_key = str(target["target_key"])
            attempted_keys.add(target_key)
            _reverify_target(index=index, target=target, root=root)
            recovered = _recover_orphan_snapshot(
                index=index,
                target=target,
                root=root,
                observed_at=require_utc(clock(), "clock"),
            )
            if recovered:
                _write_index(root=root, index=index, registry=registry)
                continue
            if private_daily_cache_would_cross_free_space_floor(
                cache_root=root,
                repo_root=repo_root,
            ):
                status = "storage_floor_would_be_crossed"
                break
            if active_client is None:
                active_client = client_factory()
            result = run_bounded_kis_paper_private_daily_collection(
                active_client,
                code_revision=code_revision,
                target=KisPaperPrivateDailyCollectionTarget(
                    symbol=str(target["symbol"]),
                    exchange=str(target["exchange"]),
                    anchor_date=str(target["next_anchor_date"]),
                    approved_symbol_exchanges=_registry_symbol_exchanges(registry),
                ),
                observed_at=require_utc(clock(), "clock"),
                sleeper=sleeper,
                monotonic_clock=monotonic_clock,
            )
            chunk_attempt_count += 1
            accepted_page_count += len(result.pages)

            if result.status == "rejected":
                categorical_failure_count += _record_unretained_failure(
                    target=target,
                    reason=result.reason or "daily_response_invalid",
                    observed_at=require_utc(clock(), "clock"),
                )
                _write_index(root=root, index=index, registry=registry)
                if result.reason in _SHARED_STOP_REASONS:
                    next_due = _next_due(request_gate, token_start_gate, token_required=True)
                    status = "collected" if accepted_page_count else "deferred"
                    break
                continue
            if _is_terminal_empty_observation(result):
                _record_source_limited(
                    target=target,
                    reason="empty_daily_response",
                    accepted_pages=len(result.pages),
                )
                _write_index(root=root, index=index, registry=registry)
                continue

            snapshot = _write_and_inspect_snapshot(
                root=root,
                repo_root=repo_root,
                index=index,
                result=result,
            )
            categorical_failure_count += _commit_snapshot(
                index=index,
                target=target,
                snapshot=snapshot,
                root=root,
                observed_at=require_utc(clock(), "clock"),
            )
            _write_index(root=root, index=index, registry=registry)
            if result.reason in _SHARED_STOP_REASONS:
                next_due = _next_due(request_gate, token_start_gate, token_required=True)
                status = "collected" if accepted_page_count else "deferred"
                break
        else:
            status = "collected" if accepted_page_count else "deferred"

        completed_at = require_utc(clock(), "clock")
        run = _build_run(
            status=status,
            observed_at=observed_at,
            completed_at=completed_at,
            registry=registry,
            index=index,
            bootstrap_only=bootstrap_only,
            chunk_attempt_count=chunk_attempt_count,
            accepted_page_count=accepted_page_count,
            categorical_failure_count=categorical_failure_count,
            next_due=_future_due(
                next_due
                or _next_due(
                    request_gate,
                    token_start_gate,
                    token_required=active_client is None,
                ),
                now=completed_at,
            ),
        )
        evidence_hash = _write_source_safe_receipt(
            evidence_root=artifacts,
            repo_root=repo_root,
            run=run,
        )
        return KisPaperDailyBroadBackfillRun(**{**run.__dict__, "evidence_sha256": evidence_hash})
    finally:
        _release_worker_lock(lock)


def _validate_registry(registry: KisPaperDailyBroadRegistry) -> None:
    if (
        registry.version != KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION
        or registry.scope.current_listing_only is not True
        or registry.scope.non_pit is not True
        or registry.scope.non_ranking is not True
        or registry.scope.provider_price_data is not False
        or not registry.targets
        or not registry.bootstrap_targets
        or not _is_sha256(registry.registry_sha256)
        or tuple(sorted(registry.target_keys)) != registry.target_keys
        or not set(registry.bootstrap_target_keys).issubset(set(registry.target_keys))
    ):
        raise KisPaperDailyBroadBackfillError("broad daily registry is invalid")


def _registry_symbol_exchanges(
    registry: KisPaperDailyBroadRegistry,
) -> Mapping[str, frozenset[str]]:
    return {target.symbol: frozenset({target.exchange}) for target in registry.targets}


def _load_or_initialize_index(
    *,
    root: Path,
    registry: KisPaperDailyBroadRegistry,
    persist: bool,
) -> dict[str, object]:
    path = root / KIS_PAPER_DAILY_BROAD_BACKFILL_INDEX_FILENAME
    if not path.exists():
        index = _initial_index(registry)
        if persist:
            _write_index(root=root, index=index, registry=registry)
        return index
    if path.is_symlink():
        raise KisPaperDailyBroadBackfillError("broad daily index is invalid")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailyBroadBackfillError("broad daily index is invalid") from error
    if not isinstance(document, dict):
        raise KisPaperDailyBroadBackfillError("broad daily index is invalid")
    _validate_index(document, registry=registry)
    return document


def _initial_index(registry: KisPaperDailyBroadRegistry) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_broad_backfill_index",
        "version": KIS_PAPER_DAILY_BROAD_BACKFILL_VERSION,
        "initial_anchor_date": KIS_PAPER_DAILY_BROAD_BACKFILL_INITIAL_ANCHOR_DATE,
        "generation": 0,
        "registry": {
            "version": registry.version,
            "registry_sha256": registry.registry_sha256,
            "source_manifest_sha256": registry.source_manifest_sha256,
            "source_file_sha256": registry.source_file_sha256,
            "target_count": len(registry.targets),
            "bootstrap_target_count": len(registry.bootstrap_targets),
            "current_listing_only": True,
            "non_pit": True,
            "non_ranking": True,
        },
        "targets": [
            {
                "symbol": target.symbol,
                "exchange": target.exchange,
                "target_key": target.key,
                "initial_anchor_date": KIS_PAPER_DAILY_BROAD_BACKFILL_INITIAL_ANCHOR_DATE,
                "next_anchor_date": KIS_PAPER_DAILY_BROAD_BACKFILL_INITIAL_ANCHOR_DATE,
                "state": "ready",
                "retry_not_before_utc": None,
                "last_reason": None,
                "accepted_page_count": 0,
                "categorical_failure_count": 0,
                "consecutive_failure_reason": None,
                "consecutive_failure_count": 0,
                "chunks": [],
            }
            for target in registry.targets
        ],
        "storage": {"private_local_only": True, "served": False, "redistributed": False},
        "redaction": {"credentials_persisted": False, "account_facts_persisted": False},
    }


def _validate_index(index: Mapping[str, object], *, registry: KisPaperDailyBroadRegistry) -> None:
    expected = _initial_index(registry)
    if (
        index.get("schema_version") != SCHEMA_VERSION
        or index.get("kind") != expected["kind"]
        or index.get("version") != expected["version"]
        or index.get("initial_anchor_date") != expected["initial_anchor_date"]
        or not isinstance(index.get("generation"), int)
        or int(index["generation"]) < 0
        or index.get("registry") != expected["registry"]
        or index.get("storage") != expected["storage"]
        or index.get("redaction") != expected["redaction"]
        or not isinstance(index.get("targets"), list)
    ):
        raise KisPaperDailyBroadBackfillError("broad daily index is invalid")
    targets = index["targets"]
    expected_targets = expected["targets"]
    assert isinstance(expected_targets, list)
    if len(targets) != len(expected_targets):
        raise KisPaperDailyBroadBackfillError("broad daily index target count is invalid")
    for target, expected_target in zip(targets, expected_targets, strict=True):
        if not isinstance(target, dict):
            raise KisPaperDailyBroadBackfillError("broad daily index target is invalid")
        for key in ("symbol", "exchange", "target_key", "initial_anchor_date"):
            if target.get(key) != expected_target[key]:
                raise KisPaperDailyBroadBackfillError("broad daily index registry drift")
        if (
            target.get("state") not in _TARGET_STATES
            or not _is_date(target.get("next_anchor_date"))
            or not isinstance(target.get("accepted_page_count"), int)
            or int(target["accepted_page_count"]) < 0
            or not isinstance(target.get("categorical_failure_count"), int)
            or int(target["categorical_failure_count"]) < 0
            or not isinstance(target.get("chunks"), list)
        ):
            raise KisPaperDailyBroadBackfillError("broad daily index target is invalid")
        retry = target.get("retry_not_before_utc")
        if retry is not None:
            _parse_utc(str(retry))
        _validate_consecutive_failure(target)
        for chunk in target["chunks"]:
            _validate_chunk(chunk, target_key=str(target["target_key"]))


def _migrate_index(index: dict[str, object]) -> bool:
    """Add source-safe retry facts to an existing v1 index without altering data."""

    changed = False
    for target in _targets(index):
        reason_present = "consecutive_failure_reason" in target
        count_present = "consecutive_failure_count" in target
        if reason_present != count_present:
            raise KisPaperDailyBroadBackfillError("broad daily index is invalid")
        if not reason_present:
            target["consecutive_failure_reason"] = None
            target["consecutive_failure_count"] = 0
            changed = True
    return changed


def _validate_consecutive_failure(target: Mapping[str, object]) -> None:
    reason_present = "consecutive_failure_reason" in target
    count_present = "consecutive_failure_count" in target
    if reason_present != count_present:
        raise KisPaperDailyBroadBackfillError("broad daily index target is invalid")
    if not reason_present:
        return
    reason = target.get("consecutive_failure_reason")
    count = target.get("consecutive_failure_count")
    if (
        (reason is not None and not isinstance(reason, str))
        or not isinstance(count, int)
        or count < 0
        or (reason is None and count != 0)
        or (reason is not None and count == 0)
    ):
        raise KisPaperDailyBroadBackfillError("broad daily index target is invalid")


def _select_ready_target(
    *,
    index: Mapping[str, object],
    allowed_keys: Sequence[str],
    attempted_keys: Sequence[str],
    observed_at: datetime,
) -> dict[str, object] | None:
    target_by_key = {str(target["target_key"]): target for target in _targets(index)}
    candidates: list[tuple[int, dict[str, object]]] = []
    for position, target_key in enumerate(allowed_keys):
        target = target_by_key.get(target_key)
        if target is None or target_key in attempted_keys:
            continue
        retry = target.get("retry_not_before_utc")
        if target["state"] == "ready" or (
            target["state"] == "deferred"
            and retry is not None
            and _parse_utc(str(retry)) <= observed_at
        ):
            candidates.append((position, target))
    if not candidates:
        return None
    # Broaden useful coverage before repeatedly deepening one alphabetical target.
    return min(
        candidates,
        key=lambda candidate: (int(candidate[1]["accepted_page_count"]), candidate[0]),
    )[1]


def _allowed_targets_terminal(index: Mapping[str, object], allowed_keys: Sequence[str]) -> bool:
    target_by_key = {str(target["target_key"]): target for target in _targets(index)}
    return all(
        target_by_key.get(target_key, {}).get("state") in _TERMINAL_STATES
        for target_key in allowed_keys
    )


def _reverify_target(
    *,
    index: Mapping[str, object],
    target: Mapping[str, object],
    root: Path,
) -> None:
    for chunk in target["chunks"]:
        assert isinstance(chunk, Mapping)
        snapshot = _inspect_snapshot(
            manifest_path=root / str(chunk["manifest_path"]),
            root=root,
        )
        expected = {
            "target_key": target["target_key"],
            "input_cursor_date": chunk["input_cursor_date"],
            "output_cursor_date": chunk["output_cursor_date"],
            "manifest_hash": chunk["manifest_hash"],
            "raw_hash": chunk["raw_hash"],
            "row_fingerprints": chunk["row_fingerprints"],
        }
        if any(getattr(snapshot, key) != value for key, value in expected.items()):
            raise KisPaperDailyBroadBackfillError("broad daily committed snapshot drift")


def _recover_orphan_snapshot(
    *,
    index: dict[str, object],
    target: dict[str, object],
    root: Path,
    observed_at: datetime,
) -> bool:
    known = {
        str(chunk["manifest_hash"])
        for candidate in _targets(index)
        for chunk in candidate["chunks"]
    }
    pattern = (
        f"snapshot=*-{str(target['symbol']).lower()}-"
        f"{str(target['exchange']).lower()}-modp0-v1/manifest.json"
    )
    for manifest_path in sorted(root.glob(pattern)):
        snapshot = _inspect_snapshot(manifest_path=manifest_path, root=root)
        if snapshot.manifest_hash in known:
            continue
        if (
            snapshot.target_key != target["target_key"]
            or snapshot.input_cursor_date != target["next_anchor_date"]
        ):
            continue
        _commit_snapshot(
            index=index,
            target=target,
            snapshot=snapshot,
            root=root,
            observed_at=observed_at,
        )
        return True
    return False


def _record_unretained_failure(
    *,
    target: dict[str, object],
    reason: str,
    observed_at: datetime,
) -> int:
    target["categorical_failure_count"] = int(target["categorical_failure_count"]) + 1
    prior_reason = target.get("consecutive_failure_reason")
    prior_count = int(target.get("consecutive_failure_count", 0))
    repeats = prior_count + 1 if prior_reason == reason else 1
    target["consecutive_failure_reason"] = reason
    target["consecutive_failure_count"] = repeats
    target["last_reason"] = reason
    if reason in _SOURCE_LIMIT_AFTER_REPEATS and repeats >= 2:
        target["state"] = "source_limited"
        target["retry_not_before_utc"] = None
    else:
        target["state"] = "deferred"
        target["retry_not_before_utc"] = _format_utc(
            observed_at + KIS_PAPER_DAILY_BROAD_BACKFILL_RETRY_DELAY
        )
    return 1


def _record_source_limited(
    *,
    target: dict[str, object],
    reason: str,
    accepted_pages: int,
) -> None:
    target["state"] = "source_limited"
    target["retry_not_before_utc"] = None
    target["last_reason"] = reason
    target["consecutive_failure_reason"] = None
    target["consecutive_failure_count"] = 0
    target["accepted_page_count"] = int(target["accepted_page_count"]) + accepted_pages


def _is_terminal_empty_observation(result: KisPaperPrivateDailyCollectionResult) -> bool:
    return (
        result.status == "observed"
        and not result.rows
        and bool(result.pages)
        and all(page.row_count == 0 and not page.continuation_advertised for page in result.pages)
    )


def _write_and_inspect_snapshot(
    *,
    root: Path,
    repo_root: Path,
    index: Mapping[str, object],
    result: KisPaperPrivateDailyCollectionResult,
) -> _Snapshot:
    output_cursor = result.rows[0].xymd if result.rows else None
    manifest_path, _ = write_kis_paper_private_daily_cache(
        result=result,
        cache_root=root,
        run_id=(
            f"{result.observed_at:%Y%m%dT%H%M%S%fZ}-"
            f"{int(index['generation']) + 1:06d}"
        ),
        repo_root=repo_root,
        collector_objective_id=KIS_PAPER_DAILY_BROAD_BACKFILL_OBJECTIVE_ID,
        collector_version=KIS_PAPER_DAILY_BROAD_BACKFILL_VERSION,
        backfill_context={
            "contract_version": KIS_PAPER_DAILY_BROAD_BACKFILL_VERSION,
            "cursor_strategy": "oldest_session_date_with_exact_overlap",
            "input_cursor_date": result.requested_anchor_date,
            "logical_cursor_persisted": True,
            "output_cursor_date": output_cursor,
            "target_key": f"{result.symbol}/{result.exchange}/MODP=0",
        },
    )
    return _inspect_snapshot(manifest_path=manifest_path, root=root)


def _commit_snapshot(
    *,
    index: dict[str, object],
    target: dict[str, object],
    snapshot: _Snapshot,
    root: Path,
    observed_at: datetime,
) -> int:
    if (
        snapshot.target_key != target["target_key"]
        or snapshot.input_cursor_date != target["next_anchor_date"]
    ):
        raise KisPaperDailyBroadBackfillError("broad daily snapshot cursor mismatch")
    prior_fingerprints = {
        date: fingerprint
        for chunk in target["chunks"]
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
    failures = 0
    target["consecutive_failure_reason"] = None
    target["consecutive_failure_count"] = 0
    if conflicts:
        outcome = "conflict"
        reason = "cross_chunk_duplicate_conflict"
        target["state"] = "deferred"
        target["retry_not_before_utc"] = _format_utc(
            observed_at + KIS_PAPER_DAILY_BROAD_BACKFILL_RETRY_DELAY
        )
        target["last_reason"] = reason
        target["categorical_failure_count"] = int(target["categorical_failure_count"]) + 1
        failures = 1
    elif snapshot.output_cursor_date >= snapshot.input_cursor_date:
        outcome = "source_limited"
        reason = "no_cursor_progress"
        _record_source_limited(
            target=target,
            reason=reason,
            accepted_pages=snapshot.accepted_page_count,
        )
        target["categorical_failure_count"] = int(target["categorical_failure_count"]) + 1
        failures = 1
    elif snapshot.status == "partial":
        outcome = "partial"
        reason = snapshot.stop_outcome
        target["state"] = "ready"
        target["next_anchor_date"] = snapshot.output_cursor_date
        target["retry_not_before_utc"] = None
        target["last_reason"] = reason
        target["accepted_page_count"] = (
            int(target["accepted_page_count"]) + snapshot.accepted_page_count
        )
    elif snapshot.stop_outcome == "source_exhausted":
        outcome = "complete"
        reason = None
        target["state"] = "complete"
        target["next_anchor_date"] = snapshot.output_cursor_date
        target["retry_not_before_utc"] = None
        target["last_reason"] = None
        target["accepted_page_count"] = (
            int(target["accepted_page_count"]) + snapshot.accepted_page_count
        )
    else:
        outcome = "committed"
        reason = None
        target["state"] = "ready"
        target["next_anchor_date"] = snapshot.output_cursor_date
        target["retry_not_before_utc"] = None
        target["last_reason"] = None
        target["accepted_page_count"] = (
            int(target["accepted_page_count"]) + snapshot.accepted_page_count
        )
    target["chunks"].append(
        {
            "input_cursor_date": snapshot.input_cursor_date,
            "output_cursor_date": snapshot.output_cursor_date,
            "manifest_path": snapshot.manifest_relative_path,
            "manifest_hash": snapshot.manifest_hash,
            "raw_hash": snapshot.raw_hash,
            "accepted_page_count": snapshot.accepted_page_count,
            "row_fingerprints": dict(snapshot.row_fingerprints),
            "exact_overlap_rows": exact_overlap,
            "conflicting_overlap_rows": len(conflicts),
            "outcome": outcome,
            "reason": reason,
        }
    )
    index["generation"] = int(index["generation"]) + 1
    return failures


def _inspect_snapshot(*, manifest_path: Path, root: Path) -> _Snapshot:
    path = _resolved_child(path=manifest_path, root=root)
    if path.name != "manifest.json":
        raise KisPaperDailyBroadBackfillError("broad daily manifest is invalid")
    try:
        payload = path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailyBroadBackfillError("broad daily manifest is invalid") from error
    if not isinstance(manifest, Mapping):
        raise KisPaperDailyBroadBackfillError("broad daily manifest is invalid")
    source = manifest.get("source")
    context = manifest.get("backfill")
    files = manifest.get("files")
    raw_document = files.get("raw_daily_rows") if isinstance(files, Mapping) else None
    if (
        not isinstance(source, Mapping)
        or not isinstance(context, Mapping)
        or not isinstance(raw_document, Mapping)
    ):
        raise KisPaperDailyBroadBackfillError("broad daily manifest is invalid")
    symbol = source.get("symbol")
    exchange = source.get("exchange")
    target_key = context.get("target_key")
    input_cursor = context.get("input_cursor_date")
    output_cursor = context.get("output_cursor_date")
    if (
        manifest.get("collector_objective_id") != KIS_PAPER_DAILY_BROAD_BACKFILL_OBJECTIVE_ID
        or manifest.get("collector_version") != KIS_PAPER_DAILY_BROAD_BACKFILL_VERSION
        or source.get("endpoint") != "dailyprice"
        or source.get("adjustment_mode") != "MODP=0_unadjusted"
        or not isinstance(symbol, str)
        or not isinstance(exchange, str)
        or not _is_target_key(f"{symbol}/{exchange}")
        or target_key != f"{symbol}/{exchange}/MODP=0"
        or context.get("contract_version") != KIS_PAPER_DAILY_BROAD_BACKFILL_VERSION
        or context.get("cursor_strategy") != "oldest_session_date_with_exact_overlap"
        or context.get("logical_cursor_persisted") is not True
        or not _is_date(input_cursor)
        or not _is_date(output_cursor)
    ):
        raise KisPaperDailyBroadBackfillError("broad daily manifest is invalid")
    raw_relative = raw_document.get("path")
    raw_hash = raw_document.get("sha256")
    raw_size = raw_document.get("size_bytes")
    if (
        not isinstance(raw_relative, str)
        or not _is_sha256(raw_hash)
        or not isinstance(raw_size, int)
    ):
        raise KisPaperDailyBroadBackfillError("broad daily raw document is invalid")
    raw_payload = _resolved_child(path=path.parent / raw_relative, root=path.parent).read_bytes()
    if len(raw_payload) != raw_size or _sha256(raw_payload) != raw_hash:
        raise KisPaperDailyBroadBackfillError("broad daily raw hash is invalid")
    fingerprints = _raw_row_fingerprints(raw_payload, symbol=symbol, exchange=exchange)
    if not fingerprints or str(output_cursor) != min(_compact_date(date) for date in fingerprints):
        raise KisPaperDailyBroadBackfillError("broad daily cursor is invalid")
    requests = manifest.get("requests")
    if not isinstance(requests, Mapping) or not isinstance(requests.get("accepted_pages"), int):
        raise KisPaperDailyBroadBackfillError("broad daily request facts are invalid")
    return _Snapshot(
        target_key=f"{symbol}/{exchange}",
        input_cursor_date=str(input_cursor),
        output_cursor_date=str(output_cursor),
        status=str(manifest.get("status")),
        stop_outcome=str(manifest.get("stop_outcome")),
        manifest_path=path,
        manifest_relative_path=path.relative_to(root).as_posix(),
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
        raise KisPaperDailyBroadBackfillError("broad daily raw contents are invalid") from error
    fingerprints: dict[str, str] = {}
    for row in rows:
        session = row.get("session_date")
        if (
            row.get("symbol") != symbol
            or row.get("exchange") != exchange
            or not _is_iso_date(session)
            or session in fingerprints
        ):
            raise KisPaperDailyBroadBackfillError("broad daily raw contents are invalid")
        rendered = "\x1f".join(str(row.get(column, "")) for column in _RAW_COLUMNS)
        fingerprints[session] = _sha256(rendered.encode("utf-8"))
    if list(fingerprints) != sorted(fingerprints):
        raise KisPaperDailyBroadBackfillError("broad daily raw contents are invalid")
    return fingerprints


def _validate_chunk(chunk: object, *, target_key: str) -> None:
    if not isinstance(chunk, Mapping) or (
        not _is_date(chunk.get("input_cursor_date"))
        or not _is_date(chunk.get("output_cursor_date"))
        or not isinstance(chunk.get("manifest_path"), str)
        or not _is_sha256(chunk.get("manifest_hash"))
        or not _is_sha256(chunk.get("raw_hash"))
        or not isinstance(chunk.get("accepted_page_count"), int)
        or int(chunk["accepted_page_count"]) < 0
        or not isinstance(chunk.get("row_fingerprints"), Mapping)
        or not isinstance(chunk.get("exact_overlap_rows"), int)
        or not isinstance(chunk.get("conflicting_overlap_rows"), int)
        or chunk.get("outcome")
        not in {"committed", "partial", "complete", "source_limited", "conflict"}
    ):
        raise KisPaperDailyBroadBackfillError("broad daily index chunk is invalid")
    for session, fingerprint in chunk["row_fingerprints"].items():
        if not _is_iso_date(session) or not _is_sha256(fingerprint):
            raise KisPaperDailyBroadBackfillError("broad daily index chunk is invalid")
    if target_key != target_key.strip().upper():
        raise KisPaperDailyBroadBackfillError("broad daily index chunk is invalid")


def _write_index(
    *,
    root: Path,
    index: Mapping[str, object],
    registry: KisPaperDailyBroadRegistry,
) -> None:
    _validate_index(index, registry=registry)
    payload = (json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    target = root / KIS_PAPER_DAILY_BROAD_BACKFILL_INDEX_FILENAME
    staging = root / f".{target.name}.{uuid.uuid4().hex}.stage"
    try:
        _write_bytes(staging, payload)
        os.replace(staging, target)
    finally:
        if staging.exists():
            staging.unlink()


def _build_run(
    *,
    status: Literal[
        "collected", "complete", "deferred", "busy", "storage_floor_would_be_crossed"
    ],
    observed_at: datetime,
    completed_at: datetime,
    registry: KisPaperDailyBroadRegistry,
    index: Mapping[str, object],
    bootstrap_only: bool,
    chunk_attempt_count: int,
    accepted_page_count: int,
    categorical_failure_count: int,
    next_due: datetime | None,
) -> KisPaperDailyBroadBackfillRun:
    targets = tuple(
        KisPaperDailyBroadTargetState(
            target_key=str(target["target_key"]),
            state=str(target["state"]),
            cursor_date=str(target["next_anchor_date"]),
            accepted_page_count=int(target["accepted_page_count"]),
            categorical_failure_count=int(target["categorical_failure_count"]),
            last_reason=(None if target["last_reason"] is None else str(target["last_reason"])),
        )
        for target in _targets(index)
    )
    remaining = sum(state.state not in _TERMINAL_STATES for state in targets)
    return KisPaperDailyBroadBackfillRun(
        status=status,
        observed_at=observed_at,
        completed_at=completed_at,
        registry_sha256=registry.registry_sha256,
        target_states=targets,
        bootstrap_only=bootstrap_only,
        chunk_attempt_count=chunk_attempt_count,
        accepted_page_count=accepted_page_count,
        categorical_failure_count=categorical_failure_count,
        remaining_target_count=remaining,
        next_due=next_due,
        recovery="complete" if status == "complete" else "reconcile" if any(
            state.state == "deferred" for state in targets
        ) else "resume",
    )


def _write_source_safe_receipt(
    *,
    evidence_root: Path,
    repo_root: Path,
    run: KisPaperDailyBroadBackfillRun,
) -> str:
    root = _artifact_root(evidence_root=evidence_root, repo_root=repo_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"run={run.completed_at:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:12]}"
    if destination.exists() or destination.is_symlink():
        raise KisPaperDailyBroadBackfillError("broad daily receipt destination is invalid")
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


def _external_retry_due(
    *,
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    token_required: bool,
) -> datetime | None:
    """Yield a known cross-process retry instead of sleeping in this worker."""

    request_retry = request_gate.snapshot().retry_not_before_utc
    token_retry = (
        token_start_gate.snapshot().next_token_request_not_before_utc
        if token_required
        else None
    )
    candidates = [value for value in (request_retry, token_retry) if value is not None]
    return max(candidates) if candidates else None


def _next_due(
    request_gate: KisPaperMarketDataRateGate,
    token_start_gate: KisPaperMarketDataTokenStartGate,
    *,
    token_required: bool,
) -> datetime | None:
    request = request_gate.snapshot()
    candidates = [
        value
        for value in (
            request.retry_not_before_utc,
            (
                None
                if request.last_request_started_at_utc is None
                else request.last_request_started_at_utc
                + timedelta(seconds=KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS)
            ),
            (
                token_start_gate.snapshot().next_token_request_not_before_utc
                if token_required
                else None
            ),
        )
        if value is not None
    ]
    return max(candidates) if candidates else None


def _future_due(value: datetime | None, *, now: datetime) -> datetime | None:
    return value if value is not None and value > now else None


def _cache_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = Path(cache_root).resolve()
    repository = Path(repo_root).resolve()
    mounted_market_data = repository / "market_data"
    if root.is_relative_to(repository) and not (
        mounted_market_data.is_mount() and root.is_relative_to(mounted_market_data)
    ):
        raise KisPaperDailyBroadBackfillError("broad daily cache must stay outside Git")
    if root.is_symlink():
        raise KisPaperDailyBroadBackfillError("broad daily cache root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _artifact_root(*, evidence_root: Path, repo_root: Path) -> Path:
    root = Path(evidence_root).resolve()
    repository = Path(repo_root).resolve()
    if root.is_relative_to(repository) and not _is_external_mount(root, repository):
        raise KisPaperDailyBroadBackfillError("broad daily evidence must stay outside Git")
    if root.is_symlink():
        raise KisPaperDailyBroadBackfillError("broad daily evidence root is invalid")
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
        raise KisPaperDailyBroadBackfillError("broad daily path is invalid")
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise KisPaperDailyBroadBackfillError("broad daily path is invalid")
    return resolved_path


def _targets(index: Mapping[str, object]) -> list[dict[str, object]]:
    values = index["targets"]
    assert isinstance(values, list)
    return [value for value in values if isinstance(value, dict)]


def _try_worker_lock(path: Path) -> _WorkerLock | None:
    if path.is_symlink():
        raise KisPaperDailyBroadBackfillError("broad daily worker lock is invalid")
    handle = path.open("a+b")
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
        handle.close()
        return None
    return _WorkerLock(handle=handle)


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


def _is_target_key(value: object) -> bool:
    if not isinstance(value, str):
        return False
    symbol, separator, exchange = value.partition("/")
    return (
        separator == "/"
        and symbol.isascii()
        and symbol.isalnum()
        and 1 <= len(symbol) <= 5
        and exchange == "NAS"
    )


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
    return require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp")
    except ValueError as error:
        raise KisPaperDailyBroadBackfillError("broad daily timestamp is invalid") from error


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

"""Resumable, private KIS Paper daily-cache backfill outside the repository."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_market_data import KisPaperMarketDataClient
from .kis_private_daily_collector import (
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KisPaperPrivateDailyCollectionResult,
    KisPaperPrivateDailyCollectionTarget,
    private_daily_cache_would_cross_free_space_floor,
    run_bounded_kis_paper_private_daily_collection,
    write_kis_paper_private_daily_cache,
)

KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION = "kis-paper-private-daily-backfill-v1"
KIS_PAPER_PRIVATE_DAILY_BACKFILL_INITIAL_ANCHOR_DATE = "20260717"
KIS_PAPER_PRIVATE_DAILY_BACKFILL_RETRY_DELAY = timedelta(minutes=2)
KIS_PAPER_PRIVATE_DAILY_BACKFILL_MIN_CHUNK_INTERVAL = timedelta(minutes=2)
KIS_PAPER_PRIVATE_DAILY_BACKFILL_INDEX_DIRECTORY = "backfill-v1"
KIS_PAPER_PRIVATE_DAILY_BACKFILL_INDEX_FILENAME = "index.json"
KIS_PAPER_PRIVATE_DAILY_BACKFILL_LOCK_FILENAME = "worker.lock"

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
_TARGETS = (
    ("QQQ", "NAS", "verified_by_prior_private_snapshot"),
    ("SPY", "AMS", "pending_bounded_kis_response"),
    ("IWM", "AMS", "pending_bounded_kis_response"),
)
_TARGET_STATES = frozenset({"ready", "deferred", "source_limited", "complete"})
_USABLE_CHUNK_OUTCOMES = frozenset({"committed", "partial", "complete"})
_SOURCE_LIMITED_INVALID_CURSOR_REPEATS = 2
_SOURCE_LIMITED_INVALID_CURSOR_REASON = "daily_response_invalid"
_LEGACY_WINDOWS_DAILY_CACHE_COMPONENTS = (
    "market_data",
    "us_equities",
    "kis_paper_private",
    "daily",
)


@dataclass(frozen=True)
class KisPaperPrivateDailyBackfillRun:
    """Safe result of one worker invocation; it never contains raw rows or secrets."""

    status: Literal[
        "collected",
        "recovered",
        "deferred",
        "complete",
        "busy",
        "no_ready_target",
        "storage_floor_would_be_crossed",
    ]
    target_key: str | None = None
    manifest_path: Path | None = None
    manifest_hash: str | None = None
    row_count: int = 0
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.target_key is not None and not _is_target_key(self.target_key):
            raise ValueError("private daily backfill result target is invalid")
        if self.manifest_hash is not None and not self.manifest_hash.startswith("sha256:"):
            raise ValueError("private daily backfill result manifest hash is invalid")
        if self.row_count < 0:
            raise ValueError("private daily backfill result row count is invalid")


@dataclass(frozen=True)
class _WorkerLock:
    path: Path
    owner_id: str
    handle: BinaryIO


def run_kis_paper_private_daily_backfill_once(
    *,
    client_factory: Callable[[], KisPaperMarketDataClient],
    cache_root: Path = KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    repo_root: Path,
    code_revision: str,
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] | None = None,
    monotonic_clock: Callable[[], float] | None = None,
) -> KisPaperPrivateDailyBackfillRun:
    """Commit or recover one small chunk without a daemon or a one-shot marker."""

    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    root = _backfill_root(cache_root=cache_root, repo_root=repo_root)
    lock = _acquire_worker_lock(root=root, observed_at=observed)
    if lock is None:
        return KisPaperPrivateDailyBackfillRun(status="busy", reason="worker_lock_held")
    try:
        index = load_or_initialize_kis_paper_private_daily_backfill_index(
            cache_root=cache_root,
            repo_root=repo_root,
        )
        try:
            _reverify_committed_snapshots(
                index=index,
                cache_root=cache_root,
                repo_root=repo_root,
            )
        except ValueError:
            return KisPaperPrivateDailyBackfillRun(
                status="deferred",
                reason="committed_snapshot_reconcile_required",
            )
        recovered = _recover_orphan_snapshot(
            index=index,
            cache_root=cache_root,
            repo_root=repo_root,
            observed_at=observed,
        )
        if recovered is not None:
            _write_backfill_index(root=root, index=index)
            return recovered
        network_retry_not_before = index["network_retry_not_before_utc"]
        if (
            network_retry_not_before is not None
            and _parse_utc(str(network_retry_not_before)) > observed
        ):
            return KisPaperPrivateDailyBackfillRun(
                status="deferred",
                reason="shared_retry_not_before",
            )

        target = _select_ready_target(index=index, observed_at=observed)
        if target is None:
            return KisPaperPrivateDailyBackfillRun(status="no_ready_target")
        target_key = str(target["target_key"])
        if private_daily_cache_would_cross_free_space_floor(
            cache_root=cache_root,
            repo_root=repo_root,
        ):
            return KisPaperPrivateDailyBackfillRun(
                status="storage_floor_would_be_crossed",
                target_key=target_key,
            )

        collection_target = KisPaperPrivateDailyCollectionTarget(
            symbol=str(target["symbol"]),
            exchange=str(target["exchange"]),
            anchor_date=str(target["next_anchor_date"]),
        )
        collect_kwargs: dict[str, object] = {
            "code_revision": code_revision,
            "target": collection_target,
            "observed_at": observed,
        }
        if sleeper is not None:
            collect_kwargs["sleeper"] = sleeper
        if monotonic_clock is not None:
            collect_kwargs["monotonic_clock"] = monotonic_clock
        result = run_bounded_kis_paper_private_daily_collection(
            client_factory(),
            **collect_kwargs,  # type: ignore[arg-type]
        )
        output_cursor = _output_cursor_for_result(result)
        manifest_path, manifest_hash = write_kis_paper_private_daily_cache(
            result=result,
            cache_root=cache_root,
            run_id=_run_id(observed_at=observed, generation=int(index["generation"]) + 1),
            repo_root=repo_root,
            backfill_context={
                "contract_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
                "cursor_strategy": "oldest_session_date_with_exact_overlap",
                "input_cursor_date": result.requested_anchor_date,
                "logical_cursor_persisted": True,
                "output_cursor_date": output_cursor,
                "target_key": target_key,
            },
        )
        snapshot = inspect_kis_paper_private_daily_backfill_snapshot(
            manifest_path=manifest_path,
            cache_root=cache_root,
            repo_root=repo_root,
        )
        return _commit_snapshot(
            index=index,
            root=root,
            target=target,
            snapshot=snapshot,
            observed_at=observed,
            recovered=False,
        )
    finally:
        _release_worker_lock(lock)


def load_or_initialize_kis_paper_private_daily_backfill_index(
    *,
    cache_root: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Load the small logical index, creating an empty three-symbol lane once."""

    root = _backfill_root(cache_root=cache_root, repo_root=repo_root)
    path = root / KIS_PAPER_PRIVATE_DAILY_BACKFILL_INDEX_FILENAME
    if not path.exists():
        index = _initial_index()
        _write_backfill_index(root=root, index=index)
        return index
    return _read_backfill_index(path=path, cache_root=cache_root, repo_root=repo_root)


def inspect_kis_paper_private_daily_backfill_snapshot(
    *,
    manifest_path: Path,
    cache_root: Path,
    repo_root: Path,
) -> dict[str, object]:
    """Verify an immutable chunk from bytes, not a prior worker narrative."""

    root = _daily_cache_root(cache_root=cache_root, repo_root=repo_root)
    path = _resolve_external_child(path=Path(manifest_path), root=root)
    if path.name != "manifest.json":
        raise ValueError("private daily backfill manifest path is invalid")
    try:
        payload = path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private daily backfill manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise ValueError("private daily backfill manifest is invalid")
    source = manifest.get("source")
    context = manifest.get("backfill")
    if not isinstance(source, dict) or not isinstance(context, dict):
        raise ValueError("private daily backfill manifest is invalid")
    symbol = source.get("symbol")
    exchange = source.get("exchange")
    target_key = context.get("target_key")
    input_cursor = context.get("input_cursor_date")
    output_cursor = context.get("output_cursor_date")
    if (
        not isinstance(symbol, str)
        or not isinstance(exchange, str)
        or target_key != _target_key(symbol, exchange)
        or context.get("contract_version") != KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION
        or context.get("cursor_strategy") != "oldest_session_date_with_exact_overlap"
        or context.get("logical_cursor_persisted") is not True
        or not _is_date(input_cursor)
        or (output_cursor is not None and not _is_date(output_cursor))
        or manifest.get("status") not in {"completed", "partial", "rejected"}
    ):
        raise ValueError("private daily backfill manifest is invalid")
    row_fingerprints, raw_hash, raw_retained = _read_raw_snapshot_rows(
        manifest=manifest,
        manifest_path=path,
        symbol=symbol,
        exchange=exchange,
    )
    return {
        "target_key": target_key,
        "input_cursor_date": input_cursor,
        "output_cursor_date": output_cursor,
        "status": manifest["status"],
        "stop_outcome": manifest.get("stop_outcome"),
        "manifest_path": str(path),
        "manifest_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "raw_sha256": raw_hash,
        "raw_market_data_retained": raw_retained,
        "row_fingerprints": row_fingerprints,
        "row_count": len(row_fingerprints),
        "collected_at_utc": manifest.get("collected_at_utc"),
    }


def _reverify_committed_snapshots(
    *,
    index: Mapping[str, object],
    cache_root: Path,
    repo_root: Path,
) -> None:
    """Refuse cursor progress when a previously committed evidence file drifts."""

    for target in _targets(index):
        for chunk in target["chunks"]:
            if _is_unretained_marker(chunk):
                continue
            if chunk["outcome"] not in _USABLE_CHUNK_OUTCOMES:
                continue
            snapshot = inspect_kis_paper_private_daily_backfill_snapshot(
                manifest_path=Path(str(chunk["manifest_path"])),
                cache_root=cache_root,
                repo_root=repo_root,
            )
            expected = {
                "target_key": target["target_key"],
                "input_cursor_date": chunk["input_cursor_date"],
                "output_cursor_date": chunk["output_cursor_date"],
                "manifest_hash": chunk["manifest_hash"],
                "raw_sha256": chunk["raw_sha256"],
                "raw_market_data_retained": chunk["raw_market_data_retained"],
                "row_count": chunk["row_count"],
                "row_fingerprints": chunk["row_fingerprints"],
            }
            if any(snapshot[key] != value for key, value in expected.items()):
                raise ValueError("private daily backfill committed snapshot drift")


def _initial_index() -> dict[str, object]:
    targets: list[dict[str, object]] = []
    for symbol, exchange, venue_status in _TARGETS:
        targets.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "target_key": _target_key(symbol, exchange),
                "venue_status": venue_status,
                "initial_anchor_date": KIS_PAPER_PRIVATE_DAILY_BACKFILL_INITIAL_ANCHOR_DATE,
                "next_anchor_date": KIS_PAPER_PRIVATE_DAILY_BACKFILL_INITIAL_ANCHOR_DATE,
                "state": "ready",
                "retry_not_before_utc": None,
                "last_reason": None,
                "chunks": [],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_private_daily_backfill_index",
        "backfill_version": KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION,
        "generation": 0,
        "network_retry_not_before_utc": None,
        "last_shared_reason": None,
        "venue_attempts": [],
        "targets": targets,
        "storage": {"private_local_only": True, "served": False, "redistributed": False},
        "redaction": {"credentials_persisted": False, "account_facts_persisted": False},
    }


def _select_ready_target(
    *,
    index: Mapping[str, object],
    observed_at: datetime,
) -> dict[str, object] | None:
    ready: list[tuple[str, int, int, dict[str, object]]] = []
    for position, target in enumerate(_targets(index)):
        retry_not_before = target["retry_not_before_utc"]
        retry_is_ready = (
            retry_not_before is None
            or _parse_utc(str(retry_not_before)) <= observed_at
        )
        if target["state"] in {"ready", "deferred"} and retry_is_ready:
            # The newest cursor has the least historical coverage and limits the shared panel.
            retained_chunk_count = sum(
                not _is_unretained_marker(chunk) for chunk in target["chunks"]
            )
            ready.append((str(target["next_anchor_date"]), retained_chunk_count, position, target))
    return (
        max(ready, default=None, key=lambda item: (item[0], -item[1], -item[2]))[3]
        if ready
        else None
    )


def _recover_orphan_snapshot(
    *,
    index: dict[str, object],
    cache_root: Path,
    repo_root: Path,
    observed_at: datetime,
) -> KisPaperPrivateDailyBackfillRun | None:
    root = _daily_cache_root(cache_root=cache_root, repo_root=repo_root)
    committed_hashes = {
        chunk["manifest_hash"]
        for target in _targets(index)
        for chunk in target["chunks"]
        if not _is_unretained_marker(chunk)
    }
    for target in _targets(index):
        symbol = str(target["symbol"]).lower()
        exchange = str(target["exchange"]).lower()
        pattern = f"snapshot=*-{symbol}-{exchange}-modp0-v1/manifest.json"
        for manifest_path in sorted(root.glob(pattern)):
            if manifest_path.is_symlink():
                raise ValueError("private daily backfill manifest path is invalid")
            try:
                snapshot = inspect_kis_paper_private_daily_backfill_snapshot(
                    manifest_path=manifest_path,
                    cache_root=cache_root,
                    repo_root=repo_root,
                )
            except ValueError:
                continue
            if snapshot["manifest_hash"] in committed_hashes:
                continue
            if snapshot["target_key"] != target["target_key"]:
                continue
            return _commit_snapshot(
                index=index,
                root=_backfill_root(cache_root=cache_root, repo_root=repo_root),
                target=target,
                snapshot=snapshot,
                observed_at=observed_at,
                recovered=True,
            )
    return None


def _commit_snapshot(
    *,
    index: dict[str, object],
    root: Path,
    target: dict[str, object],
    snapshot: Mapping[str, object],
    observed_at: datetime,
    recovered: bool,
) -> KisPaperPrivateDailyBackfillRun:
    if snapshot["input_cursor_date"] != target["next_anchor_date"]:
        raise ValueError("private daily backfill orphan cursor does not match index")
    prior_fingerprints = {
        date: fingerprint
        for chunk in target["chunks"]
        if not _is_unretained_marker(chunk)
        if chunk["outcome"] in _USABLE_CHUNK_OUTCOMES
        for date, fingerprint in chunk["row_fingerprints"].items()
    }
    row_fingerprints = dict(snapshot["row_fingerprints"])
    conflicts = [
        session
        for session, fingerprint in row_fingerprints.items()
        if session in prior_fingerprints and prior_fingerprints[session] != fingerprint
    ]
    exact_overlap = sum(
        1
        for session, fingerprint in row_fingerprints.items()
        if prior_fingerprints.get(session) == fingerprint
    )
    result_status = str(snapshot["status"])
    output_cursor = snapshot["output_cursor_date"]
    outcome: Literal["committed", "partial", "deferred", "complete", "conflict"]
    status: Literal["collected", "recovered", "deferred", "complete"]
    reason: str | None = None
    if conflicts:
        outcome = "conflict"
        status = "deferred"
        reason = "cross_chunk_duplicate_conflict"
        target["state"] = "deferred"
        target["retry_not_before_utc"] = _deferred_until(observed_at)
        target["last_reason"] = reason
    elif result_status == "rejected":
        outcome = "deferred"
        status = "deferred"
        reason = str(snapshot["stop_outcome"])
        target["state"] = "deferred"
        target["retry_not_before_utc"] = _deferred_until(observed_at)
        target["last_reason"] = reason
        if reason == "auth_rejected":
            index["network_retry_not_before_utc"] = target["retry_not_before_utc"]
            index["last_shared_reason"] = reason
    elif snapshot["row_count"] == 0:
        outcome = "deferred"
        status = "deferred"
        reason = "empty_daily_response"
        target["state"] = "deferred"
        target["retry_not_before_utc"] = _deferred_until(observed_at)
        target["last_reason"] = reason
    elif snapshot["stop_outcome"] == "source_exhausted":
        outcome = "complete"
        status = "recovered" if recovered else "complete"
        target["state"] = "complete"
        target["retry_not_before_utc"] = None
        target["last_reason"] = None
        if output_cursor is not None:
            target["next_anchor_date"] = output_cursor
        target["venue_status"] = "verified_by_kis_response"
    elif output_cursor is None or str(output_cursor) >= str(target["next_anchor_date"]):
        outcome = "deferred"
        status = "deferred"
        reason = "no_cursor_progress"
        target["state"] = "deferred"
        target["retry_not_before_utc"] = _deferred_until(observed_at)
        target["last_reason"] = reason
    elif result_status == "partial":
        outcome = "partial"
        status = "recovered" if recovered else "collected"
        reason = str(snapshot["stop_outcome"])
        target["state"] = "ready"
        target["next_anchor_date"] = output_cursor
        target["retry_not_before_utc"] = None
        target["last_reason"] = reason
        target["venue_status"] = "verified_by_kis_response"
    else:
        outcome = "committed"
        status = "recovered" if recovered else "collected"
        target["state"] = "ready"
        target["next_anchor_date"] = output_cursor
        target["retry_not_before_utc"] = None
        target["last_reason"] = None
        target["venue_status"] = "verified_by_kis_response"

    if result_status in {"completed", "partial"} and not recovered:
        index["network_retry_not_before_utc"] = _format_utc(
            observed_at + KIS_PAPER_PRIVATE_DAILY_BACKFILL_MIN_CHUNK_INTERVAL
        )
        index["last_shared_reason"] = "inter_chunk_pace"

    manifest_path = _relative_index_path(
        path=Path(str(snapshot["manifest_path"])),
        root=root.parent,
    )
    target["chunks"].append(
        {
            "chunk_key": _chunk_key(
                target_key=str(target["target_key"]),
                input_cursor_date=str(snapshot["input_cursor_date"]),
            ),
            "outcome": outcome,
            "input_cursor_date": snapshot["input_cursor_date"],
            "output_cursor_date": output_cursor,
            "manifest_path": manifest_path,
            "manifest_hash": snapshot["manifest_hash"],
            "raw_sha256": snapshot["raw_sha256"],
            "raw_market_data_retained": snapshot["raw_market_data_retained"],
            "row_count": snapshot["row_count"],
            "row_fingerprints": row_fingerprints,
            "exact_overlap_rows": exact_overlap,
            "conflicting_overlap_rows": len(conflicts),
            "collected_at_utc": snapshot["collected_at_utc"],
            "reason": reason,
        }
    )
    index["generation"] = int(index["generation"]) + 1
    _write_backfill_index(root=root, index=index)
    return KisPaperPrivateDailyBackfillRun(
        status=status,
        target_key=str(target["target_key"]),
        manifest_path=Path(str(snapshot["manifest_path"])),
        manifest_hash=str(snapshot["manifest_hash"]),
        row_count=int(snapshot["row_count"]),
        reason=reason,
    )


def _output_cursor_for_result(result: KisPaperPrivateDailyCollectionResult) -> str | None:
    if result.status not in {"observed", "partial"} or not result.rows:
        return None
    return result.rows[0].xymd


def _read_raw_snapshot_rows(
    *,
    manifest: Mapping[str, object],
    manifest_path: Path,
    symbol: str,
    exchange: str,
) -> tuple[dict[str, str], str | None, bool]:
    files = manifest.get("files")
    raw_document = files.get("raw_daily_rows") if isinstance(files, dict) else None
    if raw_document is None:
        return {}, None, False
    if not isinstance(raw_document, dict):
        raise ValueError("private daily backfill raw document is invalid")
    raw_relative = raw_document.get("path")
    raw_hash = raw_document.get("sha256")
    raw_size = raw_document.get("size_bytes")
    if (
        not isinstance(raw_relative, str)
        or not isinstance(raw_hash, str)
        or not raw_hash.startswith("sha256:")
        or not isinstance(raw_size, int)
    ):
        raise ValueError("private daily backfill raw document is invalid")
    raw_path = _resolve_external_child(
        path=manifest_path.parent / raw_relative,
        root=manifest_path.parent,
    )
    try:
        payload = raw_path.read_bytes()
    except OSError as error:
        raise ValueError("private daily backfill raw path is invalid") from error
    if len(payload) != raw_size or "sha256:" + hashlib.sha256(payload).hexdigest() != raw_hash:
        raise ValueError("private daily backfill raw hash is invalid")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
            reader = csv.DictReader(io.StringIO(handle.read().decode("utf-8"), newline=""))
            if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                raise ValueError("private daily backfill raw schema is invalid")
            rows = list(reader)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("private daily backfill raw contents are invalid") from error
    fingerprints: dict[str, str] = {}
    for row in rows:
        session = row.get("session_date")
        if (
            row.get("symbol") != symbol
            or row.get("exchange") != exchange
            or not _is_iso_date(session)
        ):
            raise ValueError("private daily backfill raw contents are invalid")
        if session in fingerprints:
            raise ValueError("private daily backfill raw contents are invalid")
        fingerprint_input = "\x1f".join(str(row.get(field, "")) for field in _RAW_COLUMNS)
        fingerprints[session] = "sha256:" + hashlib.sha256(
            fingerprint_input.encode("utf-8")
        ).hexdigest()
    if list(fingerprints) != sorted(fingerprints):
        raise ValueError("private daily backfill raw contents are invalid")
    return fingerprints, raw_hash, True


def _read_backfill_index(
    *,
    path: Path,
    cache_root: Path,
    repo_root: Path,
) -> dict[str, object]:
    root = _backfill_root(cache_root=cache_root, repo_root=repo_root)
    if path.is_symlink() or path.resolve() != (root / path.name).resolve():
        raise ValueError("private daily backfill index is invalid")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private daily backfill index is invalid") from error
    if not isinstance(document, dict):
        raise ValueError("private daily backfill index is invalid")
    upgraded = _upgrade_index(document)
    upgraded = _normalize_index_manifest_paths(index=document, root=root.parent) or upgraded
    _validate_index(document)
    if upgraded:
        _write_backfill_index(root=root, index=document)
    return document


def _validate_index(index: Mapping[str, object]) -> None:
    if (
        index.get("kind") != "kis_paper_private_daily_backfill_index"
        or index.get("backfill_version") != KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION
        or not isinstance(index.get("generation"), int)
        or int(index["generation"]) < 0
        or not isinstance(index.get("targets"), list)
        or not isinstance(index.get("venue_attempts"), list)
    ):
        raise ValueError("private daily backfill index is invalid")
    network_retry_not_before = index.get("network_retry_not_before_utc")
    if network_retry_not_before is not None:
        _parse_utc(str(network_retry_not_before))
    if index.get("last_shared_reason") not in {None, "auth_rejected", "inter_chunk_pace"}:
        raise ValueError("private daily backfill index is invalid")
    targets = index["targets"]
    if len(targets) != len(_TARGETS):
        raise ValueError("private daily backfill index is invalid")
    for target, (symbol, exchange, _venue_status) in zip(targets, _TARGETS, strict=True):
        if not isinstance(target, dict):
            raise ValueError("private daily backfill index is invalid")
        if (
            target.get("symbol") != symbol
            or target.get("exchange") != exchange
            or target.get("target_key") != _target_key(symbol, exchange)
            or target.get("state") not in _TARGET_STATES
            or not _is_date(target.get("initial_anchor_date"))
            or not _is_date(target.get("next_anchor_date"))
            or not isinstance(target.get("chunks"), list)
        ):
            raise ValueError("private daily backfill index is invalid")
        retry_not_before = target.get("retry_not_before_utc")
        if retry_not_before is not None:
            _parse_utc(str(retry_not_before))
        for chunk in target["chunks"]:
            if _is_unretained_marker(chunk):
                continue
            _validate_chunk(chunk, target_key=_target_key(symbol, exchange))


def _upgrade_index(index: dict[str, object]) -> bool:
    """Apply local-only index revisions without dropping prior KIS evidence."""

    changed = False
    shared_retry: str | None = None
    targets = index.get("targets")
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, dict) or target.get("last_reason") != "auth_rejected":
                continue
            candidate = target.get("retry_not_before_utc")
            if candidate is None:
                continue
            candidate_text = str(candidate)
            if shared_retry is None or _parse_utc(candidate_text) > _parse_utc(shared_retry):
                shared_retry = candidate_text
    if "network_retry_not_before_utc" not in index:
        index["network_retry_not_before_utc"] = shared_retry
        changed = True
    if "last_shared_reason" not in index:
        index["last_shared_reason"] = "auth_rejected" if shared_retry else None
        changed = True
    if "venue_attempts" not in index:
        index["venue_attempts"] = []
        changed = True
    venue_attempts = index["venue_attempts"]
    if not isinstance(venue_attempts, list):
        raise ValueError("private daily backfill index is invalid")
    if not isinstance(targets, list) or len(targets) != len(_TARGETS):
        return changed
    for target, (symbol, exchange, venue_status) in zip(targets, _TARGETS, strict=True):
        if not isinstance(target, dict) or target.get("symbol") != symbol:
            return changed
        if target.get("exchange") == exchange:
            continue
        venue_attempts.append(
            {
                "target_key": target.get("target_key"),
                "exchange": target.get("exchange"),
                "chunks": target.get("chunks"),
                "last_reason": target.get("last_reason"),
                "prior_state": target.get("state"),
            }
        )
        target.update(
            {
                "exchange": exchange,
                "target_key": _target_key(symbol, exchange),
                "venue_status": venue_status,
                "initial_anchor_date": KIS_PAPER_PRIVATE_DAILY_BACKFILL_INITIAL_ANCHOR_DATE,
                "next_anchor_date": KIS_PAPER_PRIVATE_DAILY_BACKFILL_INITIAL_ANCHOR_DATE,
                "state": "ready",
                "retry_not_before_utc": None,
                "last_reason": None,
                "chunks": [],
            }
        )
        changed = True
    for target in targets:
        if not isinstance(target, dict) or not _has_persistently_invalid_source_cursor(target):
            continue
        target["state"] = "source_limited"
        target["retry_not_before_utc"] = None
        changed = True
    return changed


def _normalize_index_manifest_paths(*, index: dict[str, object], root: Path) -> bool:
    """Store local cache references relative to the shared daily cache root."""

    targets = index.get("targets")
    if not isinstance(targets, list):
        return False
    changed = False
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("chunks"), list):
            continue
        for chunk in target["chunks"]:
            if not isinstance(chunk, dict):
                continue
            manifest_path = chunk.get("manifest_path")
            if not isinstance(manifest_path, str):
                continue
            normalized = _relative_index_path(path=Path(manifest_path), root=root)
            if manifest_path != normalized:
                chunk["manifest_path"] = normalized
                changed = True
    return changed


def _validate_chunk(chunk: object, *, target_key: str) -> None:
    if not isinstance(chunk, dict):
        raise ValueError("private daily backfill index is invalid")
    if (
        chunk.get("chunk_key")
        != _chunk_key(target_key=target_key, input_cursor_date=str(chunk.get("input_cursor_date")))
        or chunk.get("outcome")
        not in _USABLE_CHUNK_OUTCOMES | {"deferred", "conflict"}
        or not _is_date(chunk.get("input_cursor_date"))
        or (
            chunk.get("output_cursor_date") is not None
            and not _is_date(chunk.get("output_cursor_date"))
        )
        or not isinstance(chunk.get("manifest_path"), str)
        or not isinstance(chunk.get("manifest_hash"), str)
        or not chunk["manifest_hash"].startswith("sha256:")
        or (
            chunk.get("raw_sha256") is not None
            and (
                not isinstance(chunk["raw_sha256"], str)
                or not chunk["raw_sha256"].startswith("sha256:")
            )
        )
        or not isinstance(chunk.get("raw_market_data_retained"), bool)
        or not isinstance(chunk.get("row_count"), int)
        or not isinstance(chunk.get("row_fingerprints"), dict)
        or not isinstance(chunk.get("exact_overlap_rows"), int)
        or not isinstance(chunk.get("conflicting_overlap_rows"), int)
    ):
        raise ValueError("private daily backfill index is invalid")
    fingerprints = chunk["row_fingerprints"]
    if len(fingerprints) != chunk["row_count"]:
        raise ValueError("private daily backfill index is invalid")
    for session, fingerprint in fingerprints.items():
        if (
            not _is_iso_date(session)
            or not isinstance(fingerprint, str)
            or not fingerprint.startswith("sha256:")
        ):
            raise ValueError("private daily backfill index is invalid")
    outcome = str(chunk["outcome"])
    output_cursor = chunk["output_cursor_date"]
    if outcome in _USABLE_CHUNK_OUTCOMES and (
        output_cursor is None
        or chunk["raw_market_data_retained"] is not True
        or chunk["row_count"] <= 0
    ):
        raise ValueError("private daily backfill usable chunk is invalid")
    if outcome in {"committed", "partial"} and output_cursor >= chunk["input_cursor_date"]:
        raise ValueError("private daily backfill usable chunk is invalid")
    if outcome == "complete" and output_cursor > chunk["input_cursor_date"]:
        raise ValueError("private daily backfill usable chunk is invalid")
    if outcome == "partial" and (
        not isinstance(chunk.get("reason"), str)
        or not str(chunk["reason"]).startswith("partial_")
    ):
        raise ValueError("private daily partial chunk is invalid")


def _is_unretained_marker(chunk: object) -> bool:
    """Ignore legacy non-data markers while preserving real deferred snapshots."""

    return (
        isinstance(chunk, Mapping)
        and chunk.get("raw_market_data_retained") is False
        and not isinstance(chunk.get("manifest_path"), str)
    )


def _has_persistently_invalid_source_cursor(target: Mapping[str, object]) -> bool:
    """Recognize a repeated, zero-row provider defect without starving other targets."""

    if target.get("state") != "deferred":
        return False
    cursor = target.get("next_anchor_date")
    chunks = target.get("chunks")
    if not isinstance(cursor, str) or not isinstance(chunks, list):
        return False
    invalid_count = 0
    for chunk in reversed(chunks):
        if _is_unretained_marker(chunk):
            continue
        if not isinstance(chunk, Mapping):
            return False
        if chunk.get("input_cursor_date") != cursor:
            break
        if (
            chunk.get("outcome") != "deferred"
            or chunk.get("reason") != _SOURCE_LIMITED_INVALID_CURSOR_REASON
            or chunk.get("row_count") != 0
            or chunk.get("raw_market_data_retained") is not False
            or chunk.get("output_cursor_date") is not None
        ):
            return False
        invalid_count += 1
    return invalid_count >= _SOURCE_LIMITED_INVALID_CURSOR_REPEATS


def _targets(index: Mapping[str, object]) -> list[dict[str, object]]:
    targets = index["targets"]
    assert isinstance(targets, list)
    return [target for target in targets if isinstance(target, dict)]


def _write_backfill_index(*, root: Path, index: Mapping[str, object]) -> None:
    _validate_index(index)
    payload = (json.dumps(index, indent=2, sort_keys=True) + "\n").encode("utf-8")
    target = root / KIS_PAPER_PRIVATE_DAILY_BACKFILL_INDEX_FILENAME
    staging = root / f".{target.name}.{uuid.uuid4().hex}.stage"
    try:
        _write_bytes_and_sync(staging, payload)
        os.replace(staging, target)
    finally:
        if staging.exists():
            staging.unlink()


def _daily_cache_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = Path(cache_root).resolve()
    repository = Path(repo_root).resolve()
    mounted_root = repository / "market_data"
    mounted_market_data = mounted_root.is_mount() and root.is_relative_to(mounted_root)
    if root.is_relative_to(repository) and not mounted_market_data:
        raise ValueError("private daily backfill cache root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_external_child(*, path: Path, root: Path) -> Path:
    """Reject symlinked files/directories before resolving their target path."""

    resolved_root = Path(root).resolve()
    candidate = _external_path_candidate(path=path, root=resolved_root)
    current = candidate
    while current != resolved_root:
        if not current.is_relative_to(resolved_root) or current.is_symlink():
            raise ValueError("private daily backfill path is invalid")
        parent = current.parent
        if parent == current:
            raise ValueError("private daily backfill path is invalid")
        current = parent
    if candidate.is_symlink():
        raise ValueError("private daily backfill path is invalid")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("private daily backfill path is invalid")
    return resolved


def _relative_index_path(*, path: Path, root: Path) -> str:
    resolved_root = Path(root).resolve()
    resolved = _resolve_external_child(path=path, root=resolved_root)
    return resolved.relative_to(resolved_root).as_posix()


def _external_path_candidate(*, path: Path, root: Path) -> Path:
    raw_path = str(path)
    native_path = Path(raw_path)
    if native_path.is_absolute():
        return Path(os.path.abspath(native_path))
    windows_path = PureWindowsPath(raw_path)
    if windows_path.is_absolute():
        return root.joinpath(*_legacy_windows_daily_cache_relative_parts(windows_path))
    return root / native_path


def _legacy_windows_daily_cache_relative_parts(path: PureWindowsPath) -> tuple[str, ...]:
    parts = path.parts[1:]
    prefix_length = len(_LEGACY_WINDOWS_DAILY_CACHE_COMPONENTS)
    if (
        len(parts) <= prefix_length
        or tuple(part.casefold() for part in parts[:prefix_length])
        != _LEGACY_WINDOWS_DAILY_CACHE_COMPONENTS
    ):
        raise ValueError("private daily backfill path is invalid")
    relative = tuple(parts[prefix_length:])
    if any(part in {"", ".", ".."} for part in relative):
        raise ValueError("private daily backfill path is invalid")
    return relative


def _backfill_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = _daily_cache_root(cache_root=cache_root, repo_root=repo_root)
    child = root / KIS_PAPER_PRIVATE_DAILY_BACKFILL_INDEX_DIRECTORY
    if child.is_symlink():
        raise ValueError("private daily backfill index is invalid")
    child.mkdir(exist_ok=True)
    resolved = child.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("private daily backfill index is invalid")
    return resolved


def _acquire_worker_lock(*, root: Path, observed_at: datetime) -> _WorkerLock | None:
    path = root / KIS_PAPER_PRIVATE_DAILY_BACKFILL_LOCK_FILENAME
    if path.is_symlink():
        raise ValueError("private daily backfill lock is invalid")
    handle = path.open("a+b")
    if not _try_lock_handle(handle):
        handle.close()
        return None
    owner_id = uuid.uuid4().hex
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {"created_at_utc": _format_utc(observed_at), "owner_id": owner_id},
                sort_keys=True,
            ).encode("utf-8")
        )
        handle.flush()
        os.fsync(handle.fileno())
    except OSError:
        _unlock_handle(handle)
        handle.close()
        raise
    return _WorkerLock(path=path, owner_id=owner_id, handle=handle)


def _try_lock_handle(handle: BinaryIO) -> bool:
    """Acquire a process-scoped nonblocking lock; OS release handles crashes."""

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


def _unlock_handle(handle: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        return


def _release_worker_lock(lock: _WorkerLock | None) -> None:
    if lock is None:
        return
    try:
        _unlock_handle(lock.handle)
    finally:
        lock.handle.close()


def _run_id(*, observed_at: datetime, generation: int) -> str:
    return f"{observed_at:%Y%m%dT%H%M%SZ}-{generation:06d}"


def _target_key(symbol: str, exchange: str) -> str:
    return f"{symbol.strip().upper()}/{exchange.strip().upper()}/MODP=0"


def _is_target_key(value: str) -> bool:
    return value in {_target_key(symbol, exchange) for symbol, exchange, _ in _TARGETS}


def _chunk_key(*, target_key: str, input_cursor_date: str) -> str:
    payload = f"{KIS_PAPER_PRIVATE_DAILY_BACKFILL_VERSION}|{target_key}|{input_cursor_date}"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def _deferred_until(observed_at: datetime) -> str:
    return _format_utc(observed_at + KIS_PAPER_PRIVATE_DAILY_BACKFILL_RETRY_DELAY)


def _format_utc(value: datetime) -> str:
    return require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp")
    except ValueError as error:
        raise ValueError("private daily backfill timestamp is invalid") from error


def _write_bytes_and_sync(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

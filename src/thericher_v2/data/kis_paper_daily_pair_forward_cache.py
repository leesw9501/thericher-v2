"""Private, forward-only QQQ/SPY D1 cache outside the Git workspace.

The cache is deliberately separate from the fixed QQQ/SPY history, the
six-symbol NAS forward stream, and the mutable broad current-listing cache.
It owns two exact KIS Paper daily targets and stores raw rows only under its
external cache root.  Every public payload is source-safe.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import BinaryIO, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_VERSION = "kis-paper-daily-qqq-spy-forward-v1"
KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ID = "kis.paper.private.daily.qqq-spy.forward-v1"
KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-qqq-spy-forward/v1"
)
KIS_PAPER_DAILY_PAIR_FORWARD_V2_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-qqq-spy-forward/v2"
)
KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY = date(2026, 7, 24)
KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_FAILURE_PHASES = (
    "cache_prepare",
    "snapshot_persist",
    "index_persist",
    "cache_reverify",
)
KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_PREPARE_SUBPHASES = (
    "cache_access",
    "cache_state_load",
    "incoming_merge",
)
KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON = (
    "daily_retained_revision_conflict"
)

_INDEX_FILENAME = "index.json"
_LOCK_FILENAME = "worker.lock"
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
_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}" for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
)
_TARGET_BY_KEY = dict(zip(_TARGET_KEYS, KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS, strict=True))
_TARGET_STATUSES = frozenset({"ready", "deferred", "input_unavailable"})
_SAFE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "daily_duplicate_conflict",
        "daily_page_limit_exceeded",
        KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON,
        "daily_response_invalid",
        "daily_response_rejected",
        "empty_daily_response",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "token_request_not_due",
        "transport_failure",
        "unexpected_private_daily_collector_error",
    }
)


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardCacheIdentity:
    """One allowlisted on-disk lineage for the fixed QQQ/SPY forward pair."""

    kind: str
    version: str

    def __post_init__(self) -> None:
        if (self.kind, self.version) not in {
            (
                "kis.paper.private.daily.qqq-spy.forward-v1",
                "kis-paper-daily-qqq-spy-forward-v1",
            ),
            (
                "kis.paper.private.daily.qqq-spy.forward-v2",
                "kis-paper-daily-qqq-spy-forward-v2",
            ),
        }:
            raise ValueError("pair forward cache identity is invalid")


KIS_PAPER_DAILY_PAIR_FORWARD_V1_IDENTITY = KisPaperDailyPairForwardCacheIdentity(
    kind=KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ID,
    version=KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_VERSION,
)
KIS_PAPER_DAILY_PAIR_FORWARD_V2_IDENTITY = KisPaperDailyPairForwardCacheIdentity(
    kind="kis.paper.private.daily.qqq-spy.forward-v2",
    version="kis-paper-daily-qqq-spy-forward-v2",
)


class KisPaperDailyPairForwardCacheError(RuntimeError):
    """A non-secret structural failure in the QQQ/SPY forward cache."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self._commit_failure_phase: str | None = None
        self._commit_failure_prepare_subphase: str | None = None


def get_kis_paper_daily_pair_forward_commit_failure_phase(
    error: BaseException,
) -> str | None:
    """Return an allowlisted commit phase attached by the bounded writer."""

    if not isinstance(error, KisPaperDailyPairForwardCacheError):
        return None
    phase = getattr(error, "_commit_failure_phase", None)
    return phase if phase in KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_FAILURE_PHASES else None


def get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(
    error: BaseException,
) -> str | None:
    """Return one fixed prepare region without exposing a causal claim."""

    if get_kis_paper_daily_pair_forward_commit_failure_phase(error) != "cache_prepare":
        return None
    subphase = getattr(error, "_commit_failure_prepare_subphase", None)
    return (
        subphase
        if subphase in KIS_PAPER_DAILY_PAIR_FORWARD_COMMIT_PREPARE_SUBPHASES
        else None
    )


def _attach_commit_failure_phase(
    error: KisPaperDailyPairForwardCacheError,
    phase: str,
) -> None:
    if get_kis_paper_daily_pair_forward_commit_failure_phase(error) is None:
        error._commit_failure_phase = phase


def _attach_commit_failure_prepare_subphase(
    error: KisPaperDailyPairForwardCacheError,
    subphase: str,
) -> None:
    """Attach only the static region where a prepare failure surfaced."""

    phase = get_kis_paper_daily_pair_forward_commit_failure_phase(error)
    if phase is None:
        _attach_commit_failure_phase(error, "cache_prepare")
    elif phase != "cache_prepare":
        return
    if get_kis_paper_daily_pair_forward_commit_failure_prepare_subphase(error) is None:
        error._commit_failure_prepare_subphase = subphase


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardRow:
    """One unadjusted D1 row retained only in the external pair cache."""

    symbol: str
    exchange: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        for name in ("open", "high", "low", "close", "volume"):
            try:
                value = Decimal(str(getattr(self, name)))
            except (InvalidOperation, ValueError) as error:
                raise ValueError("pair forward row is invalid") from error
            object.__setattr__(self, name, value)
        if (
            _target_key(self.symbol, self.exchange) not in _TARGET_KEYS
            or type(self.session_date) is not date
            or self.open <= 0
            or self.high <= 0
            or self.low <= 0
            or self.close <= 0
            or self.volume < 0
            or self.high < max(self.open, self.close)
            or self.low > min(self.open, self.close)
        ):
            raise ValueError("pair forward row is invalid")

    def raw_record(self) -> tuple[str, ...]:
        return (
            self.symbol,
            self.exchange,
            self.session_date.isoformat(),
            _decimal_text(self.open),
            _decimal_text(self.high),
            _decimal_text(self.low),
            _decimal_text(self.close),
            _decimal_text(self.volume),
        )


@dataclass(frozen=True, slots=True)
class _MergedRows:
    """One target merge with only a source-safe retained-conflict count."""

    rows: tuple[KisPaperDailyPairForwardRow, ...]
    retained_revision_conflict_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        if self.retained_revision_conflict_count < 0:
            raise ValueError("pair forward merge result is invalid")


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardTargetState:
    """Source-safe current state for one forward target."""

    target_key: str
    status: Literal["ready", "deferred", "input_unavailable"]
    accepted_page_count: int
    categorical_failure_count: int
    latest_session: date | None
    row_count: int
    rows_sha256: str | None
    last_reason: str | None

    def __post_init__(self) -> None:
        if (
            self.target_key not in _TARGET_KEYS
            or self.status not in _TARGET_STATUSES
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
            or self.row_count < 0
            or (self.latest_session is None) != (self.row_count == 0)
            or (self.rows_sha256 is None) != (self.row_count == 0)
            or (self.rows_sha256 is not None and not _is_sha256(self.rows_sha256))
            or self.last_reason not in _SAFE_REASONS | {None}
        ):
            raise ValueError("pair forward target state is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "status": self.status,
            "accepted_page_count": self.accepted_page_count,
            "categorical_failure_count": self.categorical_failure_count,
            "coverage_end_bucket": _coverage_bucket(self.latest_session),
            "row_count": self.row_count,
            "rows_sha256": self.rows_sha256,
            "last_reason": self.last_reason,
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardCache:
    """A verified external QQQ/SPY forward cache with no network surface."""

    root: Path
    index_path: Path
    index_hash: str
    cache_hash: str
    cache_identity: KisPaperDailyPairForwardCacheIdentity
    frozen_boundary: date
    rows_by_target: Mapping[str, tuple[KisPaperDailyPairForwardRow, ...]]
    targets_by_key: Mapping[str, KisPaperDailyPairForwardTargetState]
    common_sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        rows = MappingProxyType({key: tuple(value) for key, value in self.rows_by_target.items()})
        targets = MappingProxyType(dict(self.targets_by_key))
        common = tuple(self.common_sessions)
        if (
            tuple(rows) != _TARGET_KEYS
            or tuple(targets) != _TARGET_KEYS
            or not _is_sha256(self.index_hash)
            or not _is_sha256(self.cache_hash)
            or not isinstance(self.cache_identity, KisPaperDailyPairForwardCacheIdentity)
            or self.index_path.is_symlink()
            or self.root.is_symlink()
        ):
            raise ValueError("pair forward cache is invalid")
        for target_key, target_rows in rows.items():
            symbol, exchange = _TARGET_BY_KEY[target_key]
            target = targets[target_key]
            if (
                tuple(row.session_date for row in target_rows)
                != tuple(sorted(row.session_date for row in target_rows))
                or len({row.session_date for row in target_rows}) != len(target_rows)
                or any(
                    row.symbol != symbol
                    or row.exchange != exchange
                    or row.session_date <= self.frozen_boundary
                    for row in target_rows
                )
                or target.row_count != len(target_rows)
                or (target_rows and target.latest_session != target_rows[-1].session_date)
            ):
                raise ValueError("pair forward cache stream is invalid")
        expected_common = tuple(
            sorted(
                set.intersection(
                    *(set(row.session_date for row in target_rows) for target_rows in rows.values())
                )
            )
        )
        if common != expected_common:
            raise ValueError("pair forward cache common sessions are invalid")
        object.__setattr__(self, "root", self.root.resolve())
        object.__setattr__(self, "rows_by_target", rows)
        object.__setattr__(self, "targets_by_key", targets)
        object.__setattr__(self, "common_sessions", common)

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": self.cache_identity.kind,
            "version": self.cache_identity.version,
            "frozen_boundary": self.frozen_boundary.isoformat(),
            "index_sha256": self.index_hash,
            "cache_sha256": self.cache_hash,
            "forward_common_session_count": len(self.common_sessions),
            "forward_common_sessions_sha256": _dates_hash(self.common_sessions),
            "targets": [self.targets_by_key[key].safe_payload() for key in _TARGET_KEYS],
            "source": {
                "provider": "KIS Open API virtual paper",
                "endpoint": "dailyprice",
                "targets": [
                    {"symbol": symbol, "exchange": exchange}
                    for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
                ],
                "adjustment_mode": "MODP=0_unadjusted",
                "point_in_time_universe": False,
            },
            "raw_rows_persisted": True,
            "raw_rows_in_payload": False,
            "credentials_in_payload": False,
            "account_or_order_data_in_payload": False,
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardRun:
    """Source-safe result for one pair forward observation."""

    status: Literal["ready", "partial", "deferred", "input_unavailable", "unchanged"]
    observed_at: datetime
    cache: KisPaperDailyPairForwardCache
    accepted_page_count: int
    categorical_failure_count: int
    changed_target_count: int
    retained_revision_conflict_count: int
    revision_quarantined_target_count: int
    recovery: Literal["complete", "resume"]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if (
            self.status not in {"ready", "partial", "deferred", "input_unavailable", "unchanged"}
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
            or not 0 <= self.changed_target_count <= len(_TARGET_KEYS)
            or self.retained_revision_conflict_count < 0
            or not 0 <= self.revision_quarantined_target_count <= len(_TARGET_KEYS)
        ):
            raise ValueError("pair forward run is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "observed_at_bucket": self.observed_at.strftime("%Y-%m-%dT%H:00Z"),
            "accepted_page_count": self.accepted_page_count,
            "categorical_failure_count": self.categorical_failure_count,
            "changed_target_count": self.changed_target_count,
            "retained_revision_conflict_count": self.retained_revision_conflict_count,
            "revision_quarantined_target_count": self.revision_quarantined_target_count,
            "recovery": self.recovery,
            "cache": self.cache.safe_payload(),
            "route_isolation": {
                "daily_market_data_only": True,
                "account_endpoints_used": False,
                "order_endpoints_used": False,
                "live_endpoints_used": False,
            },
        }


def commit_kis_paper_daily_pair_forward_observation(
    *,
    rows_by_target: Mapping[str, Sequence[KisPaperDailyPairForwardRow]],
    failure_reasons_by_target: Mapping[str, str],
    cache_root: Path | str = KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    repo_root: Path | str | None = None,
    frozen_boundary: date = KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    cache_identity: KisPaperDailyPairForwardCacheIdentity = (
        KIS_PAPER_DAILY_PAIR_FORWARD_V1_IDENTITY
    ),
    observed_at: datetime | None = None,
) -> KisPaperDailyPairForwardRun:
    """Atomically retain one completed-session observation per successful target."""

    _validate_observation_inputs(
        rows_by_target=rows_by_target,
        failure_reasons_by_target=failure_reasons_by_target,
        frozen_boundary=frozen_boundary,
    )
    if not isinstance(cache_identity, KisPaperDailyPairForwardCacheIdentity):
        raise ValueError("pair forward cache identity is invalid")
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    repository = _repository_root(repo_root)
    try:
        try:
            root = _external_root(Path(cache_root), repository, create=True)
        except KisPaperDailyPairForwardCacheError as error:
            _attach_commit_failure_prepare_subphase(error, "cache_access")
            raise
        with _exclusive_lock(root / _LOCK_FILENAME):
            try:
                index_path = _safe_child(root / _INDEX_FILENAME, root)
                index_exists = index_path.exists()
            except KisPaperDailyPairForwardCacheError as error:
                _attach_commit_failure_prepare_subphase(error, "cache_access")
                raise
            try:
                index = _load_or_initialize_index(
                    root=root,
                    frozen_boundary=frozen_boundary,
                    cache_identity=cache_identity,
                )
                _validate_index(
                    index,
                    frozen_boundary=frozen_boundary,
                    cache_identity=cache_identity,
                )
                prior_by_target: dict[
                    str,
                    tuple[dict[str, object], tuple[KisPaperDailyPairForwardRow, ...]],
                ] = {}
                for target_key in _TARGET_KEYS:
                    target = _target_document(index, target_key)
                    existing = _load_target_rows(root=root, target=target, target_key=target_key)
                    prior_by_target[target_key] = (target, existing)
            except KisPaperDailyPairForwardCacheError as error:
                _attach_commit_failure_prepare_subphase(error, "cache_state_load")
                raise

            try:
                merged_by_target: dict[str, tuple[KisPaperDailyPairForwardRow, ...]] = {}
                retained_revision_conflicts_by_target: dict[str, int] = {}
                changed_targets: set[str] = set()
                pending_snapshots: dict[str, tuple[bytes, str, str]] = {}
                target_updates: dict[str, dict[str, object]] = {}

                for target_key in _TARGET_KEYS:
                    target, existing = prior_by_target[target_key]
                    if target_key in failure_reasons_by_target:
                        target_updates[target_key] = _failure_target_document(
                            target,
                            failure_reasons_by_target[target_key],
                        )
                        merged_by_target[target_key] = existing
                        retained_revision_conflicts_by_target[target_key] = 0
                        continue
                    incoming = tuple(
                        row
                        for row in rows_by_target[target_key]
                        if row.session_date > frozen_boundary
                    )
                    merge = _merge_rows(existing, incoming, target_key=target_key)
                    merged = merge.rows
                    merged_by_target[target_key] = merged
                    retained_revision_conflicts_by_target[target_key] = (
                        merge.retained_revision_conflict_count
                    )
                    if merged != existing:
                        raw_payload = _compressed_rows(merged)
                        pending_snapshots[target_key] = (
                            raw_payload,
                            _sha256(raw_payload),
                            _rows_sha256(merged),
                        )
                        changed_targets.add(target_key)
                        target_updates[target_key] = _success_target_document(
                            target,
                            rows=merged,
                            snapshot_path=None,
                            snapshot_sha256=None,
                            rows_sha256=pending_snapshots[target_key][2],
                            retained_revision_conflict_count=(
                                retained_revision_conflicts_by_target[target_key]
                            ),
                        )
                    else:
                        target_updates[target_key] = _success_target_document(
                            target,
                            rows=existing,
                            snapshot_path=None,
                            snapshot_sha256=None,
                            rows_sha256=_rows_sha256(existing) if existing else None,
                            retained_revision_conflict_count=(
                                retained_revision_conflicts_by_target[target_key]
                            ),
                        )
            except KisPaperDailyPairForwardCacheError as error:
                _attach_commit_failure_prepare_subphase(error, "incoming_merge")
                raise

            wrote_snapshot = False
            try:
                for target_key, snapshot in pending_snapshots.items():
                    payload, snapshot_sha256, rows_sha256 = snapshot
                    relative_path = _write_snapshot(
                        root=root,
                        target_key=target_key,
                        payload=payload,
                    )
                    target_updates[target_key] = _success_target_document(
                        _target_document(index, target_key),
                        rows=merged_by_target[target_key],
                        snapshot_path=relative_path,
                        snapshot_sha256=snapshot_sha256,
                        rows_sha256=rows_sha256,
                        retained_revision_conflict_count=(
                            retained_revision_conflicts_by_target[target_key]
                        ),
                    )
                    wrote_snapshot = True
            except KisPaperDailyPairForwardCacheError as error:
                _attach_commit_failure_phase(error, "snapshot_persist")
                raise

            try:
                updated_index = dict(index)
                updated_index["targets"] = [target_updates[key] for key in _TARGET_KEYS]
                if not index_exists or updated_index != index:
                    updated_index["generation"] = int(index["generation"]) + 1
                    _write_json_atomic(root / _INDEX_FILENAME, updated_index)
            except KisPaperDailyPairForwardCacheError as error:
                _attach_commit_failure_phase(error, "index_persist")
                raise

            try:
                cache = load_verified_kis_paper_daily_pair_forward_cache(
                    cache_root=root,
                    repo_root=repository,
                    cache_identity=cache_identity,
                )
            except KisPaperDailyPairForwardCacheError as error:
                _attach_commit_failure_phase(error, "cache_reverify")
                raise
    except KisPaperDailyPairForwardCacheError as error:
        _attach_commit_failure_phase(error, "cache_prepare")
        raise

    failure_count = len(failure_reasons_by_target)
    retained_revision_conflict_count = sum(retained_revision_conflicts_by_target.values())
    retained_revision_conflict_target_count = sum(
        count > 0 for count in retained_revision_conflicts_by_target.values()
    )
    revision_quarantined_target_count = sum(
        target.last_reason == KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON
        for target in cache.targets_by_key.values()
    )
    has_rows = any(cache.rows_by_target.values())
    status: Literal["ready", "partial", "deferred", "input_unavailable", "unchanged"]
    if failure_count == len(_TARGET_KEYS):
        status = "deferred"
    elif failure_count or revision_quarantined_target_count:
        status = "partial"
    elif not has_rows:
        status = "input_unavailable"
    elif not cache.common_sessions:
        status = "partial"
    elif not wrote_snapshot:
        status = "unchanged"
    else:
        status = "ready"
    return KisPaperDailyPairForwardRun(
        status=status,
        observed_at=observed,
        cache=cache,
        accepted_page_count=len(rows_by_target),
        categorical_failure_count=(
            failure_count + retained_revision_conflict_target_count
        ),
        changed_target_count=len(changed_targets),
        retained_revision_conflict_count=retained_revision_conflict_count,
        revision_quarantined_target_count=revision_quarantined_target_count,
        recovery=(
            "resume"
            if (
                failure_count
                or retained_revision_conflict_target_count
                or revision_quarantined_target_count
            )
            else "complete"
        ),
    )


def load_verified_kis_paper_daily_pair_forward_cache(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    repo_root: Path | str | None = None,
    cache_identity: KisPaperDailyPairForwardCacheIdentity = (
        KIS_PAPER_DAILY_PAIR_FORWARD_V1_IDENTITY
    ),
) -> KisPaperDailyPairForwardCache:
    """Reattest the pair cache without credentials, network, or KIS clients."""

    repository = _repository_root(repo_root)
    if not isinstance(cache_identity, KisPaperDailyPairForwardCacheIdentity):
        raise ValueError("pair forward cache identity is invalid")
    root = _external_root(Path(cache_root), repository, create=False)
    index_path = _safe_child(root / _INDEX_FILENAME, root)
    try:
        index_bytes = index_path.read_bytes()
    except OSError as error:
        raise KisPaperDailyPairForwardCacheError("pair forward index is unreadable") from error
    index = _json_mapping(index_bytes, "pair forward index")
    frozen_boundary = _date(index.get("frozen_boundary"), "pair forward boundary")
    _validate_index(
        index,
        frozen_boundary=frozen_boundary,
        cache_identity=cache_identity,
    )
    rows_by_target: dict[str, tuple[KisPaperDailyPairForwardRow, ...]] = {}
    targets: dict[str, KisPaperDailyPairForwardTargetState] = {}
    for target in index["targets"]:
        if not isinstance(target, Mapping):
            raise KisPaperDailyPairForwardCacheError("pair forward target is invalid")
        target_key = str(target["target_key"])
        rows = _load_target_rows(root=root, target=target, target_key=target_key)
        rows_by_target[target_key] = rows
        latest = rows[-1].session_date if rows else None
        targets[target_key] = KisPaperDailyPairForwardTargetState(
            target_key=target_key,
            status=str(target["status"]),  # type: ignore[arg-type]
            accepted_page_count=int(target["accepted_page_count"]),
            categorical_failure_count=int(target["categorical_failure_count"]),
            latest_session=latest,
            row_count=len(rows),
            rows_sha256=target.get("rows_sha256"),  # type: ignore[arg-type]
            last_reason=target.get("last_reason"),  # type: ignore[arg-type]
        )
    common_sessions = tuple(
        sorted(
            set.intersection(
                *(
                    set(row.session_date for row in target_rows)
                    for target_rows in rows_by_target.values()
                )
            )
        )
    )
    index_hash = _sha256(index_bytes)
    cache_hash = _sha256_json(
        {
            "index_sha256": index_hash,
            "frozen_boundary": frozen_boundary.isoformat(),
            "rows": {key: _rows_sha256(rows_by_target[key]) for key in _TARGET_KEYS},
            "common_sessions": [value.isoformat() for value in common_sessions],
        }
    )
    return KisPaperDailyPairForwardCache(
        root=root,
        index_path=index_path,
        index_hash=index_hash,
        cache_hash=cache_hash,
        cache_identity=cache_identity,
        frozen_boundary=frozen_boundary,
        rows_by_target=MappingProxyType(rows_by_target),
        targets_by_key=MappingProxyType(targets),
        common_sessions=common_sessions,
    )


def sanitize_kis_paper_daily_pair_forward_failure_reason(value: BaseException | str) -> str:
    """Reduce failures to the pair cache's source-safe recovery taxonomy."""

    reason = str(value).strip()
    return reason if reason in _SAFE_REASONS else "unexpected_private_daily_collector_error"


def _validate_observation_inputs(
    *,
    rows_by_target: Mapping[str, Sequence[KisPaperDailyPairForwardRow]],
    failure_reasons_by_target: Mapping[str, str],
    frozen_boundary: date,
) -> None:
    if type(frozen_boundary) is not date:
        raise ValueError("pair forward boundary is invalid")
    if (
        set(rows_by_target) | set(failure_reasons_by_target) != set(_TARGET_KEYS)
        or set(rows_by_target) & set(failure_reasons_by_target)
    ):
        raise ValueError("pair forward observation scope is invalid")
    for target_key, rows in rows_by_target.items():
        if target_key not in _TARGET_KEYS or not all(
            isinstance(row, KisPaperDailyPairForwardRow) for row in rows
        ):
            raise ValueError("pair forward observation rows are invalid")
        _merge_rows((), tuple(rows), target_key=target_key)
    for target_key, reason in failure_reasons_by_target.items():
        if target_key not in _TARGET_KEYS or reason not in _SAFE_REASONS:
            raise ValueError("pair forward observation failure is invalid")


def _load_or_initialize_index(
    *,
    root: Path,
    frozen_boundary: date,
    cache_identity: KisPaperDailyPairForwardCacheIdentity,
) -> dict[str, object]:
    path = _safe_child(root / _INDEX_FILENAME, root)
    if not path.exists():
        return _initial_index(frozen_boundary, cache_identity=cache_identity)
    index = _json_mapping(path.read_bytes(), "pair forward index")
    if _date(index.get("frozen_boundary"), "pair forward boundary") != frozen_boundary:
        raise KisPaperDailyPairForwardCacheError(
            "pair forward boundary conflicts with existing cache"
        )
    return index


def _initial_index(
    frozen_boundary: date,
    *,
    cache_identity: KisPaperDailyPairForwardCacheIdentity,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": cache_identity.kind,
        "version": cache_identity.version,
        "frozen_boundary": frozen_boundary.isoformat(),
        "generation": 0,
        "source": _source_document(),
        "targets": [_empty_target_document(None, target_key=key) for key in _TARGET_KEYS],
        "redaction": _redaction_document(),
    }


def _validate_index(
    index: Mapping[str, object],
    *,
    frozen_boundary: date,
    cache_identity: KisPaperDailyPairForwardCacheIdentity,
) -> None:
    expected = {
        "schema_version",
        "kind",
        "version",
        "frozen_boundary",
        "generation",
        "source",
        "targets",
        "redaction",
    }
    if (
        set(index) != expected
        or index.get("schema_version") != SCHEMA_VERSION
        or index.get("kind") != cache_identity.kind
        or index.get("version") != cache_identity.version
        or _date(index.get("frozen_boundary"), "pair forward boundary") != frozen_boundary
        or type(index.get("generation")) is not int
        or int(index["generation"]) < 0
        or index.get("source") != _source_document()
        or index.get("redaction") != _redaction_document()
        or not isinstance(index.get("targets"), list)
        or len(index["targets"]) != len(_TARGET_KEYS)
    ):
        raise KisPaperDailyPairForwardCacheError("pair forward index is invalid")
    targets = index["targets"]
    if (
        tuple(
            str(item.get("target_key", ""))
            for item in targets
            if isinstance(item, Mapping)
        )
        != _TARGET_KEYS
    ):
        raise KisPaperDailyPairForwardCacheError("pair forward target ordering is invalid")
    for target in targets:
        _validate_target(target, frozen_boundary=frozen_boundary)


def _validate_target(value: object, *, frozen_boundary: date) -> None:
    expected = {
        "target_key",
        "status",
        "accepted_page_count",
        "categorical_failure_count",
        "latest_session",
        "row_count",
        "snapshot_path",
        "snapshot_sha256",
        "rows_sha256",
        "last_reason",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise KisPaperDailyPairForwardCacheError("pair forward target is invalid")
    target_key = value.get("target_key")
    row_count = value.get("row_count")
    latest = value.get("latest_session")
    snapshot_path = value.get("snapshot_path")
    snapshot_sha256 = value.get("snapshot_sha256")
    rows_sha256 = value.get("rows_sha256")
    if (
        target_key not in _TARGET_KEYS
        or value.get("status") not in _TARGET_STATUSES
        or type(value.get("accepted_page_count")) is not int
        or int(value["accepted_page_count"]) < 0
        or type(value.get("categorical_failure_count")) is not int
        or int(value["categorical_failure_count"]) < 0
        or type(row_count) is not int
        or int(row_count) < 0
        or value.get("last_reason") not in _SAFE_REASONS | {None}
    ):
        raise KisPaperDailyPairForwardCacheError("pair forward target is invalid")
    if row_count == 0:
        if any(item is not None for item in (latest, snapshot_path, snapshot_sha256, rows_sha256)):
            raise KisPaperDailyPairForwardCacheError("empty pair forward target is invalid")
        return
    latest_date = _date(latest, "pair forward latest session")
    if (
        latest_date <= frozen_boundary
        or not isinstance(snapshot_path, str)
        or not snapshot_path
        or not _is_sha256(snapshot_sha256)
        or not _is_sha256(rows_sha256)
    ):
        raise KisPaperDailyPairForwardCacheError("pair forward target snapshot is invalid")


def _target_document(index: Mapping[str, object], target_key: str) -> dict[str, object]:
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise KisPaperDailyPairForwardCacheError("pair forward targets are invalid")
    for target in targets:
        if isinstance(target, Mapping) and target.get("target_key") == target_key:
            return dict(target)
    raise KisPaperDailyPairForwardCacheError("pair forward target is unavailable")


def _empty_target_document(
    prior: Mapping[str, object] | None,
    *,
    target_key: str | None = None,
) -> dict[str, object]:
    key = target_key or str(prior and prior.get("target_key"))
    if key not in _TARGET_KEYS:
        raise KisPaperDailyPairForwardCacheError("pair forward target key is invalid")
    return {
        "target_key": key,
        "status": "input_unavailable",
        "accepted_page_count": 0 if prior is None else int(prior["accepted_page_count"]),
        "categorical_failure_count": (
            0 if prior is None else int(prior["categorical_failure_count"])
        ),
        "latest_session": None,
        "row_count": 0,
        "snapshot_path": None,
        "snapshot_sha256": None,
        "rows_sha256": None,
        "last_reason": None,
    }


def _success_target_document(
    prior: Mapping[str, object],
    *,
    rows: tuple[KisPaperDailyPairForwardRow, ...],
    snapshot_path: str | None,
    snapshot_sha256: str | None,
    rows_sha256: str | None,
    retained_revision_conflict_count: int = 0,
) -> dict[str, object]:
    if retained_revision_conflict_count < 0:
        raise ValueError("pair forward retained revision conflict count is invalid")
    if not rows:
        return {
            "target_key": prior["target_key"],
            "status": "input_unavailable",
            "accepted_page_count": int(prior["accepted_page_count"]) + 1,
            "categorical_failure_count": int(prior["categorical_failure_count"]),
            "latest_session": None,
            "row_count": 0,
            "snapshot_path": None,
            "snapshot_sha256": None,
            "rows_sha256": None,
            "last_reason": None,
        }
    if rows_sha256 is None:
        raise ValueError("pair forward rows hash is unavailable")
    revision_quarantined = (
        retained_revision_conflict_count > 0 or _is_revision_quarantined(prior)
    )
    return {
        "target_key": prior["target_key"],
        "status": "input_unavailable" if revision_quarantined else "ready",
        "accepted_page_count": int(prior["accepted_page_count"]) + 1,
        "categorical_failure_count": int(prior["categorical_failure_count"])
        + (1 if retained_revision_conflict_count else 0),
        "latest_session": rows[-1].session_date.isoformat(),
        "row_count": len(rows),
        "snapshot_path": snapshot_path if snapshot_path is not None else prior.get("snapshot_path"),
        "snapshot_sha256": snapshot_sha256
        if snapshot_sha256 is not None
        else prior.get("snapshot_sha256"),
        "rows_sha256": rows_sha256,
        "last_reason": (
            KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON
            if revision_quarantined
            else None
        ),
    }


def _is_revision_quarantined(prior: Mapping[str, object]) -> bool:
    return (
        prior.get("last_reason")
        == KIS_PAPER_DAILY_PAIR_FORWARD_RETAINED_REVISION_CONFLICT_REASON
    )


def _failure_target_document(prior: Mapping[str, object], reason: str) -> dict[str, object]:
    if reason not in _SAFE_REASONS:
        raise ValueError("pair forward failure reason is invalid")
    result = dict(prior)
    if _is_revision_quarantined(prior):
        result["categorical_failure_count"] = int(prior["categorical_failure_count"]) + 1
        return result
    result["status"] = "deferred"
    result["categorical_failure_count"] = int(prior["categorical_failure_count"]) + 1
    result["last_reason"] = reason
    return result


def _load_target_rows(
    *,
    root: Path,
    target: Mapping[str, object],
    target_key: str,
) -> tuple[KisPaperDailyPairForwardRow, ...]:
    if int(target["row_count"]) == 0:
        return ()
    snapshot_path = _safe_child(root / str(target["snapshot_path"]), root)
    try:
        payload = snapshot_path.read_bytes()
    except OSError as error:
        raise KisPaperDailyPairForwardCacheError("pair forward snapshot is unreadable") from error
    if _sha256(payload) != target["snapshot_sha256"]:
        raise KisPaperDailyPairForwardCacheError("pair forward snapshot hash is invalid")
    rows = _parse_compressed_rows(payload, target_key=target_key)
    if (
        len(rows) != int(target["row_count"])
        or _rows_sha256(rows) != target["rows_sha256"]
        or rows[-1].session_date.isoformat() != target["latest_session"]
    ):
        raise KisPaperDailyPairForwardCacheError("pair forward snapshot contents are invalid")
    return rows


def _merge_rows(
    existing: Sequence[KisPaperDailyPairForwardRow],
    incoming: Sequence[KisPaperDailyPairForwardRow],
    *,
    target_key: str,
) -> _MergedRows:
    symbol, exchange = _TARGET_BY_KEY[target_key]
    by_session: dict[date, KisPaperDailyPairForwardRow] = {}
    retained_sessions: set[date] = set()
    for row in existing:
        if row.symbol != symbol or row.exchange != exchange:
            raise ValueError("pair forward row target is invalid")
        prior = by_session.get(row.session_date)
        if prior is not None and prior != row:
            raise KisPaperDailyPairForwardCacheError("pair forward duplicate conflict")
        by_session[row.session_date] = row
        retained_sessions.add(row.session_date)

    latest_retained_session = max(retained_sessions, default=None)
    retained_revision_conflict_count = 0
    for row in incoming:
        if row.symbol != symbol or row.exchange != exchange:
            raise ValueError("pair forward row target is invalid")
        prior = by_session.get(row.session_date)
        if prior is None:
            if (
                latest_retained_session is not None
                and row.session_date <= latest_retained_session
            ):
                raise KisPaperDailyPairForwardCacheError(
                    "pair forward non-forward append"
                )
            by_session[row.session_date] = row
        elif prior != row:
            if row.session_date not in retained_sessions:
                raise KisPaperDailyPairForwardCacheError("pair forward duplicate conflict")
            retained_revision_conflict_count += 1
    return _MergedRows(
        rows=tuple(by_session[session] for session in sorted(by_session)),
        retained_revision_conflict_count=retained_revision_conflict_count,
    )


def _write_snapshot(*, root: Path, target_key: str, payload: bytes) -> str:
    symbol, exchange = _TARGET_BY_KEY[target_key]
    directory = _safe_child(root / "snapshots" / f"{symbol.lower()}-{exchange.lower()}", root)
    directory.mkdir(parents=True, exist_ok=True)
    destination = _safe_child(directory / f"snapshot-{uuid.uuid4().hex}.csv.gz", root)
    _write_bytes_new(destination, payload)
    return destination.relative_to(root).as_posix()


def _compressed_rows(rows: Sequence[KisPaperDailyPairForwardRow]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_RAW_COLUMNS)
    for row in rows:
        writer.writerow(row.raw_record())
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as handle:
        handle.write(buffer.getvalue().encode("utf-8"))
    return compressed.getvalue()


def _parse_compressed_rows(
    payload: bytes,
    *,
    target_key: str,
) -> tuple[KisPaperDailyPairForwardRow, ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
            reader = csv.DictReader(io.StringIO(handle.read().decode("utf-8"), newline=""))
            if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                raise ValueError
            rows = tuple(
                KisPaperDailyPairForwardRow(
                    symbol=str(row["symbol"]),
                    exchange=str(row["exchange"]),
                    session_date=_date(row["session_date"], "pair forward session"),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                )
                for row in reader
            )
    except (KeyError, OSError, UnicodeDecodeError, InvalidOperation, ValueError) as error:
        raise KisPaperDailyPairForwardCacheError(
            "pair forward snapshot contents are invalid"
        ) from error
    return _merge_rows((), rows, target_key=target_key).rows


def _rows_sha256(rows: Sequence[KisPaperDailyPairForwardRow]) -> str:
    return _sha256("\n".join("\x1f".join(row.raw_record()) for row in rows).encode("utf-8"))


def _source_document() -> dict[str, object]:
    return {
        "provider": "KIS Open API virtual paper",
        "endpoint": "dailyprice",
        "targets": [
            {"symbol": symbol, "exchange": exchange}
            for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
        ],
        "adjustment_mode": "MODP=0_unadjusted",
        "point_in_time_universe": False,
    }


def _redaction_document() -> dict[str, bool]:
    return {
        "credentials_persisted": False,
        "account_facts_persisted": False,
        "request_headers_persisted": False,
        "response_bodies_persisted": False,
        "raw_rows_in_index": False,
    }


def _external_root(root: Path, repository: Path, *, create: bool) -> Path:
    if root.is_symlink():
        raise KisPaperDailyPairForwardCacheError("pair forward cache root is invalid")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise KisPaperDailyPairForwardCacheError("pair forward cache root is invalid")
    resolved = root.resolve(strict=True)
    mounted_market_data = repository / "market_data"
    if resolved.is_relative_to(repository) and not (
        mounted_market_data.is_mount() and resolved.is_relative_to(mounted_market_data)
    ):
        raise KisPaperDailyPairForwardCacheError("pair forward cache must stay outside Git")
    return resolved


def _repository_root(value: Path | str | None) -> Path:
    return Path(value or Path(__file__).resolve().parents[3]).resolve()


def _safe_child(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise KisPaperDailyPairForwardCacheError("pair forward cache path is invalid")
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(root.resolve()):
        raise KisPaperDailyPairForwardCacheError("pair forward cache path escapes root")
    return resolved


def _write_json_atomic(path: Path, value: Mapping[str, object]) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.stage")
    try:
        _write_bytes_new(temporary, payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_bytes_new(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise KisPaperDailyPairForwardCacheError("pair forward cache destination exists")
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _json_mapping(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailyPairForwardCacheError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise KisPaperDailyPairForwardCacheError(f"{label} is invalid")
    return value


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    try:
        if path.is_symlink():
            raise KisPaperDailyPairForwardCacheError("pair forward lock is invalid")
    except KisPaperDailyPairForwardCacheError as error:
        _attach_commit_failure_prepare_subphase(error, "cache_access")
        raise
    with path.open("a+b") as handle:
        _lock(handle)
        try:
            yield
        finally:
            _unlock(handle)


def _lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _target_key(symbol: str, exchange: str) -> str:
    return f"{symbol}/{exchange}"


def _date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} is invalid") from error


def _coverage_bucket(value: date | None) -> str | None:
    if value is None:
        return None
    return f"{value.year}-Q{((value.month - 1) // 3) + 1}"


def _dates_hash(values: Sequence[date]) -> str:
    return _sha256("\n".join(value.isoformat() for value in values).encode("utf-8"))


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_json(value: Mapping[str, object]) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value.removeprefix("sha256:"))
    )

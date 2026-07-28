"""Private, forward-only NAS D1 cache and read-only historical overlay.

The cache stores only KIS Paper daily rows outside Git.  It never calls KIS,
loads credentials, or changes the frozen daily-history panel.  A narrow
execution wrapper owns the credentialed page fetch and passes typed rows here.
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

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
)
from thericher_v2.data.official_symbol_directory_nas_probe import NAS_EXCHANGE

KIS_PAPER_DAILY_NAS_FORWARD_CACHE_VERSION = "kis-paper-daily-nas-forward-v1"
KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ID = "kis.paper.private.daily.nas.forward-v1"
KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-nas-forward/v1"
)
KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY = date(2026, 7, 24)
KIS_PAPER_DAILY_NAS_FORWARD_CONTEXT_BARS = 29
KIS_PAPER_DAILY_NAS_FORWARD_TARGET_SLOT_SESSIONS = 3

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
_TARGET_KEYS = tuple(f"{symbol}/{NAS_EXCHANGE}" for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
_TARGET_STATUSES = frozenset({"ready", "deferred", "input_unavailable", "source_limited"})
_SAFE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "daily_duplicate_conflict",
        "daily_page_limit_exceeded",
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


class KisPaperDailyNasForwardCacheError(RuntimeError):
    """A non-secret structural failure in the private forward cache."""


@dataclass(frozen=True, slots=True)
class KisPaperDailyNasForwardRow:
    """One complete unadjusted daily bar held only in the private cache."""

    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.upper().strip())
        for name in ("open", "high", "low", "close", "volume"):
            try:
                value = Decimal(str(getattr(self, name)))
            except (InvalidOperation, ValueError) as error:
                raise ValueError("NAS forward row is invalid") from error
            object.__setattr__(self, name, value)
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or type(self.session_date) is not date
            or self.open <= 0
            or self.high <= 0
            or self.low <= 0
            or self.close <= 0
            or self.volume < 0
            or self.high < max(self.open, self.close)
            or self.low > min(self.open, self.close)
        ):
            raise ValueError("NAS forward row is invalid")

    def to_bar(self) -> Bar:
        return Bar(
            symbol=self.symbol,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime(
                self.session_date.year,
                self.session_date.month,
                self.session_date.day,
                tzinfo=UTC,
            ),
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            complete=True,
        )

    def raw_record(self) -> tuple[str, ...]:
        return (
            self.symbol,
            NAS_EXCHANGE,
            self.session_date.isoformat(),
            _decimal_text(self.open),
            _decimal_text(self.high),
            _decimal_text(self.low),
            _decimal_text(self.close),
            _decimal_text(self.volume),
        )


@dataclass(frozen=True, slots=True)
class KisPaperDailyNasForwardTargetState:
    """Source-safe current state for one independent forward stream."""

    target_key: str
    status: Literal["ready", "deferred", "input_unavailable", "source_limited"]
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
            raise ValueError("NAS forward target state is invalid")

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
class KisPaperDailyNasForwardCache:
    """Verified six-stream forward cache loaded from a private external root."""

    root: Path
    index_path: Path
    index_hash: str
    cache_hash: str
    frozen_boundary: date
    rows_by_symbol: Mapping[str, tuple[KisPaperDailyNasForwardRow, ...]]
    targets_by_key: Mapping[str, KisPaperDailyNasForwardTargetState]
    common_sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        streams = MappingProxyType(
            {key: tuple(value) for key, value in self.rows_by_symbol.items()}
        )
        targets = MappingProxyType(dict(self.targets_by_key))
        common = tuple(self.common_sessions)
        if (
            tuple(streams) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or tuple(targets) != _TARGET_KEYS
            or not _is_sha256(self.index_hash)
            or not _is_sha256(self.cache_hash)
            or self.index_path.is_symlink()
            or self.root.is_symlink()
        ):
            raise ValueError("NAS forward cache is invalid")
        for symbol, rows in streams.items():
            target = targets[f"{symbol}/{NAS_EXCHANGE}"]
            if (
                tuple(row.session_date for row in rows)
                != tuple(sorted(row.session_date for row in rows))
                or len({row.session_date for row in rows}) != len(rows)
                or any(
                    row.symbol != symbol or row.session_date <= self.frozen_boundary for row in rows
                )
                or target.row_count != len(rows)
                or (rows and target.latest_session != rows[-1].session_date)
            ):
                raise ValueError("NAS forward cache stream is invalid")
        expected_common = tuple(
            sorted(
                set.intersection(
                    *(set(row.session_date for row in rows) for rows in streams.values())
                )
            )
        )
        if common != expected_common:
            raise ValueError("NAS forward cache common sessions are invalid")
        object.__setattr__(self, "root", self.root.resolve())
        object.__setattr__(self, "rows_by_symbol", streams)
        object.__setattr__(self, "targets_by_key", targets)
        object.__setattr__(self, "common_sessions", common)

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ID,
            "version": KIS_PAPER_DAILY_NAS_FORWARD_CACHE_VERSION,
            "frozen_boundary": self.frozen_boundary.isoformat(),
            "index_sha256": self.index_hash,
            "cache_sha256": self.cache_hash,
            "forward_common_session_count": len(self.common_sessions),
            "forward_common_sessions_sha256": _dates_hash(self.common_sessions),
            "targets": [
                self.targets_by_key[target_key].safe_payload() for target_key in _TARGET_KEYS
            ],
            "source": {
                "provider": "KIS Open API virtual paper",
                "endpoint": "dailyprice",
                "exchange": NAS_EXCHANGE,
                "adjustment_mode": KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
                "fixed_current_listing_basket": True,
                "point_in_time_universe": False,
            },
            "raw_rows_persisted": True,
            "raw_rows_in_payload": False,
            "credentials_in_payload": False,
            "account_or_order_data_in_payload": False,
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyNasForwardRun:
    """Source-safe outcome of one six-symbol forward cache observation."""

    status: Literal[
        "ready", "partial", "deferred", "input_unavailable", "source_limited", "unchanged"
    ]
    observed_at: datetime
    cache: KisPaperDailyNasForwardCache
    accepted_page_count: int
    categorical_failure_count: int
    changed_target_count: int
    prospective_input_status: Literal["ready", "input_unavailable"]
    recovery: Literal["complete", "resume", "reconcile"]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if (
            self.status
            not in {
                "ready",
                "partial",
                "deferred",
                "input_unavailable",
                "source_limited",
                "unchanged",
            }
            or self.accepted_page_count < 0
            or self.categorical_failure_count < 0
            or not 0 <= self.changed_target_count <= len(_TARGET_KEYS)
            or self.prospective_input_status not in {"ready", "input_unavailable"}
        ):
            raise ValueError("NAS forward run is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "observed_at_bucket": self.observed_at.strftime("%Y-%m-%dT%H:00Z"),
            "accepted_page_count": self.accepted_page_count,
            "categorical_failure_count": self.categorical_failure_count,
            "changed_target_count": self.changed_target_count,
            "prospective_consumer": {
                "required_common_session_count": KIS_PAPER_DAILY_NAS_FORWARD_TARGET_SLOT_SESSIONS,
                "status": self.prospective_input_status,
            },
            "recovery": self.recovery,
            "cache": self.cache.safe_payload(),
            "route_isolation": {
                "daily_market_data_only": True,
                "account_endpoints_used": False,
                "order_endpoints_used": False,
                "live_endpoints_used": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisPaperDailyNasHistoricalForwardProjection:
    """In-memory, read-only frozen-context plus forward-row consumer view."""

    frozen_panel_hash: str
    forward_cache_hash: str
    frozen_boundary: date
    context_by_symbol: Mapping[str, tuple[Bar, ...]]
    forward_by_symbol: Mapping[str, tuple[Bar, ...]]
    forward_common_sessions: tuple[date, ...]
    eligible_target_slot_count: int
    status: Literal["ready", "input_unavailable"]

    def __post_init__(self) -> None:
        context = MappingProxyType(
            {key: tuple(value) for key, value in self.context_by_symbol.items()}
        )
        forward = MappingProxyType(
            {key: tuple(value) for key, value in self.forward_by_symbol.items()}
        )
        sessions = tuple(self.forward_common_sessions)
        if (
            not _is_sha256(self.frozen_panel_hash)
            or not _is_sha256(self.forward_cache_hash)
            or tuple(context) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or tuple(forward) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or self.status not in {"ready", "input_unavailable"}
            or self.eligible_target_slot_count < 0
            or self.eligible_target_slot_count
            != len(sessions) // KIS_PAPER_DAILY_NAS_FORWARD_TARGET_SLOT_SESSIONS
            or (self.status == "ready") != (self.eligible_target_slot_count > 0)
            or any(
                len(value) != KIS_PAPER_DAILY_NAS_FORWARD_CONTEXT_BARS for value in context.values()
            )
            or any(
                bar.start_ts.date() <= self.frozen_boundary
                or not bar.complete
                or bar.timeframe is not Timeframe.D1
                for values in forward.values()
                for bar in values
            )
        ):
            raise ValueError("NAS historical-forward projection is invalid")
        expected_common = tuple(
            sorted(
                set.intersection(
                    *(set(bar.start_ts.date() for bar in values) for values in forward.values())
                )
            )
        )
        if sessions != expected_common:
            raise ValueError("NAS historical-forward projection common sessions are invalid")
        object.__setattr__(self, "context_by_symbol", context)
        object.__setattr__(self, "forward_by_symbol", forward)
        object.__setattr__(self, "forward_common_sessions", sessions)

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "kis.paper.private.daily.nas.historical-forward-projection-v1",
            "frozen_panel_sha256": self.frozen_panel_hash,
            "forward_cache_sha256": self.forward_cache_hash,
            "frozen_boundary": self.frozen_boundary.isoformat(),
            "context_completed_d1_bars_per_symbol": KIS_PAPER_DAILY_NAS_FORWARD_CONTEXT_BARS,
            "forward_common_session_count": len(self.forward_common_sessions),
            "forward_common_sessions_sha256": _dates_hash(self.forward_common_sessions),
            "eligible_target_slot_count": self.eligible_target_slot_count,
            "status": self.status,
            "merged_rows_persisted": False,
            "point_in_time_universe": False,
            "paper_trading_eligible": False,
        }


def commit_kis_paper_daily_nas_forward_observation(
    *,
    rows_by_symbol: Mapping[str, Sequence[KisPaperDailyNasForwardRow]],
    failure_reasons_by_symbol: Mapping[str, str],
    cache_root: Path | str = KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ROOT,
    repo_root: Path | str | None = None,
    frozen_boundary: date = KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY,
    observed_at: datetime | None = None,
) -> KisPaperDailyNasForwardRun:
    """Atomically retain one source-local forward observation per successful target."""

    _validate_observation_inputs(
        rows_by_symbol=rows_by_symbol,
        failure_reasons_by_symbol=failure_reasons_by_symbol,
        frozen_boundary=frozen_boundary,
    )
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    repository = _repository_root(repo_root)
    root = _external_root(Path(cache_root), repository, create=True)
    with _exclusive_lock(root / _LOCK_FILENAME):
        index_path = _safe_child(root / _INDEX_FILENAME, root)
        index_exists = index_path.exists()
        index = _load_or_initialize_index(root=root, frozen_boundary=frozen_boundary)
        _validate_index(index, frozen_boundary=frozen_boundary)
        merged_by_symbol: dict[str, tuple[KisPaperDailyNasForwardRow, ...]] = {}
        changed_symbols: set[str] = set()
        pending_snapshots: dict[str, tuple[bytes, str, str, int]] = {}
        target_updates: dict[str, dict[str, object]] = {}

        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
            target_key = f"{symbol}/{NAS_EXCHANGE}"
            target = _target_document(index, target_key)
            existing = _load_target_rows(root=root, target=target, symbol=symbol)
            if symbol in failure_reasons_by_symbol:
                target_updates[target_key] = _failure_target_document(
                    target,
                    failure_reasons_by_symbol[symbol],
                )
                merged_by_symbol[symbol] = existing
                continue
            incoming = tuple(
                row for row in rows_by_symbol[symbol] if row.session_date > frozen_boundary
            )
            merged = _merge_rows(existing, incoming, symbol=symbol)
            merged_by_symbol[symbol] = merged
            if merged != existing:
                raw_payload = _compressed_rows(merged)
                pending_snapshots[symbol] = (
                    raw_payload,
                    _sha256(raw_payload),
                    _rows_sha256(merged),
                    len(merged),
                )
                changed_symbols.add(symbol)
                target_updates[target_key] = _success_target_document(
                    target,
                    rows=merged,
                    snapshot_path=None,
                    snapshot_sha256=None,
                    rows_sha256=pending_snapshots[symbol][2],
                )
            else:
                target_updates[target_key] = _success_target_document(
                    target,
                    rows=existing,
                    snapshot_path=None,
                    snapshot_sha256=None,
                    rows_sha256=_rows_sha256(existing) if existing else None,
                )

        wrote_snapshot = False
        for symbol, (
            payload,
            snapshot_sha256,
            rows_sha256,
            _row_count,
        ) in pending_snapshots.items():
            relative_path = _write_snapshot(root=root, symbol=symbol, payload=payload)
            target_key = f"{symbol}/{NAS_EXCHANGE}"
            target_updates[target_key] = _success_target_document(
                _target_document(index, target_key),
                rows=merged_by_symbol[symbol],
                snapshot_path=relative_path,
                snapshot_sha256=snapshot_sha256,
                rows_sha256=rows_sha256,
            )
            wrote_snapshot = True

        updated_index = dict(index)
        updated_index["targets"] = [target_updates[target_key] for target_key in _TARGET_KEYS]
        index_changed = not index_exists or updated_index != index
        if index_changed:
            updated_index["generation"] = int(index["generation"]) + 1
            _write_json_atomic(root / _INDEX_FILENAME, updated_index)
        cache = load_verified_kis_paper_daily_nas_forward_cache(
            cache_root=root,
            repo_root=repository,
        )

    failures = len(failure_reasons_by_symbol)
    has_rows = any(cache.rows_by_symbol.values())
    status: Literal[
        "ready", "partial", "deferred", "input_unavailable", "source_limited", "unchanged"
    ]
    if failures == len(_TARGET_KEYS):
        status = "deferred"
    elif failures:
        status = "partial"
    elif not has_rows:
        status = "input_unavailable"
    elif not all(cache.rows_by_symbol.values()) or not cache.common_sessions:
        status = "partial"
    elif not wrote_snapshot:
        status = "unchanged"
    else:
        status = "ready"
    return KisPaperDailyNasForwardRun(
        status=status,
        observed_at=observed,
        cache=cache,
        accepted_page_count=len(rows_by_symbol),
        categorical_failure_count=failures,
        changed_target_count=len(changed_symbols),
        prospective_input_status=(
            "ready"
            if len(cache.common_sessions) >= KIS_PAPER_DAILY_NAS_FORWARD_TARGET_SLOT_SESSIONS
            else "input_unavailable"
        ),
        recovery="resume" if failures else "complete",
    )


def load_verified_kis_paper_daily_nas_forward_cache(
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyNasForwardCache:
    """Re-attest private forward snapshots without a network or credential surface."""

    repository = _repository_root(repo_root)
    root = _external_root(Path(cache_root), repository, create=False)
    index_path = _safe_child(root / _INDEX_FILENAME, root)
    try:
        index_bytes = index_path.read_bytes()
    except OSError as error:
        raise KisPaperDailyNasForwardCacheError("forward index is unreadable") from error
    index = _json_mapping(index_bytes, "forward index")
    frozen_boundary = _date(index.get("frozen_boundary"), "forward boundary")
    _validate_index(index, frozen_boundary=frozen_boundary)
    rows_by_symbol: dict[str, tuple[KisPaperDailyNasForwardRow, ...]] = {}
    targets: dict[str, KisPaperDailyNasForwardTargetState] = {}
    for target in index["targets"]:
        if not isinstance(target, Mapping):
            raise KisPaperDailyNasForwardCacheError("forward target is invalid")
        target_key = str(target["target_key"])
        symbol, _exchange = target_key.split("/", maxsplit=1)
        rows = _load_target_rows(root=root, target=target, symbol=symbol)
        rows_by_symbol[symbol] = rows
        latest = rows[-1].session_date if rows else None
        targets[target_key] = KisPaperDailyNasForwardTargetState(
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
                *(set(row.session_date for row in rows) for rows in rows_by_symbol.values())
            )
        )
    )
    index_hash = _sha256(index_bytes)
    cache_hash = _sha256_json(
        {
            "index_sha256": index_hash,
            "frozen_boundary": frozen_boundary.isoformat(),
            "rows": {
                symbol: _rows_sha256(rows_by_symbol[symbol])
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
            "common_sessions": [value.isoformat() for value in common_sessions],
        }
    )
    return KisPaperDailyNasForwardCache(
        root=root,
        index_path=index_path,
        index_hash=index_hash,
        cache_hash=cache_hash,
        frozen_boundary=frozen_boundary,
        rows_by_symbol=MappingProxyType(rows_by_symbol),
        targets_by_key=MappingProxyType(targets),
        common_sessions=common_sessions,
    )


def build_kis_paper_daily_nas_historical_forward_projection(
    *,
    frozen_panel: KisPaperDailyHistoryPanel,
    forward_cache: KisPaperDailyNasForwardCache,
    frozen_boundary: date | None = None,
) -> KisPaperDailyNasHistoricalForwardProjection:
    """Join immutable historical context with later verified forward rows in memory only."""

    boundary = frozen_boundary or forward_cache.frozen_boundary
    if (
        boundary != forward_cache.frozen_boundary
        or not frozen_panel.common_sessions
        or frozen_panel.common_sessions[-1] != boundary
    ):
        raise ValueError("historical-forward boundary is invalid")
    context_by_symbol: dict[str, tuple[Bar, ...]] = {}
    forward_by_symbol: dict[str, tuple[Bar, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        historical = tuple(
            bar
            for bar in frozen_panel.bars_by_symbol[symbol].bars
            if bar.start_ts.date() <= boundary
        )
        context = historical[-KIS_PAPER_DAILY_NAS_FORWARD_CONTEXT_BARS:]
        if len(context) != KIS_PAPER_DAILY_NAS_FORWARD_CONTEXT_BARS:
            raise ValueError("historical-forward context is unavailable")
        forward = tuple(row.to_bar() for row in forward_cache.rows_by_symbol[symbol])
        if any(bar.start_ts.date() <= boundary for bar in forward):
            raise ValueError("historical-forward overlap is invalid")
        context_by_symbol[symbol] = context
        forward_by_symbol[symbol] = forward
    common = forward_cache.common_sessions
    eligible_slots = len(common) // KIS_PAPER_DAILY_NAS_FORWARD_TARGET_SLOT_SESSIONS
    return KisPaperDailyNasHistoricalForwardProjection(
        frozen_panel_hash=frozen_panel.dataset_hash,
        forward_cache_hash=forward_cache.cache_hash,
        frozen_boundary=boundary,
        context_by_symbol=MappingProxyType(context_by_symbol),
        forward_by_symbol=MappingProxyType(forward_by_symbol),
        forward_common_sessions=common,
        eligible_target_slot_count=eligible_slots,
        status="ready" if eligible_slots else "input_unavailable",
    )


def sanitize_kis_paper_daily_nas_forward_failure_reason(value: BaseException | str) -> str:
    """Reduce a transport/parser failure to the cache's source-safe taxonomy."""

    reason = str(value).strip()
    return reason if reason in _SAFE_REASONS else "unexpected_private_daily_collector_error"


def _validate_observation_inputs(
    *,
    rows_by_symbol: Mapping[str, Sequence[KisPaperDailyNasForwardRow]],
    failure_reasons_by_symbol: Mapping[str, str],
    frozen_boundary: date,
) -> None:
    if type(frozen_boundary) is not date:
        raise ValueError("forward boundary is invalid")
    expected = set(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS)
    if set(rows_by_symbol) | set(failure_reasons_by_symbol) != expected or set(
        rows_by_symbol
    ) & set(failure_reasons_by_symbol):
        raise ValueError("forward observation scope is invalid")
    for symbol, rows in rows_by_symbol.items():
        if symbol not in expected or not all(
            isinstance(row, KisPaperDailyNasForwardRow) for row in rows
        ):
            raise ValueError("forward observation rows are invalid")
        if any(row.symbol != symbol for row in rows):
            raise ValueError("forward observation symbol is invalid")
        _merge_rows((), tuple(rows), symbol=symbol)
    for symbol, reason in failure_reasons_by_symbol.items():
        if symbol not in expected or reason not in _SAFE_REASONS:
            raise ValueError("forward observation failure is invalid")


def _load_or_initialize_index(*, root: Path, frozen_boundary: date) -> dict[str, object]:
    path = _safe_child(root / _INDEX_FILENAME, root)
    if not path.exists():
        return _initial_index(frozen_boundary)
    index = _json_mapping(path.read_bytes(), "forward index")
    if _date(index.get("frozen_boundary"), "forward boundary") != frozen_boundary:
        raise KisPaperDailyNasForwardCacheError("forward boundary conflicts with existing cache")
    return index


def _initial_index(frozen_boundary: date) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ID,
        "version": KIS_PAPER_DAILY_NAS_FORWARD_CACHE_VERSION,
        "frozen_boundary": frozen_boundary.isoformat(),
        "generation": 0,
        "source": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "exchange": NAS_EXCHANGE,
            "adjustment_mode": KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
            "fixed_current_listing_basket": True,
            "point_in_time_universe": False,
        },
        "targets": [
            _empty_target_document(None, target_key=target_key) for target_key in _TARGET_KEYS
        ],
        "redaction": {
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "request_headers_persisted": False,
            "response_bodies_persisted": False,
            "raw_rows_in_index": False,
        },
    }


def _validate_index(index: Mapping[str, object], *, frozen_boundary: date) -> None:
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
        or index.get("kind") != KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ID
        or index.get("version") != KIS_PAPER_DAILY_NAS_FORWARD_CACHE_VERSION
        or _date(index.get("frozen_boundary"), "forward boundary") != frozen_boundary
        or type(index.get("generation")) is not int
        or int(index["generation"]) < 0
        or not isinstance(index.get("source"), Mapping)
        or not isinstance(index.get("redaction"), Mapping)
        or not isinstance(index.get("targets"), list)
        or len(index["targets"]) != len(_TARGET_KEYS)
    ):
        raise KisPaperDailyNasForwardCacheError("forward index is invalid")
    source = index["source"]
    if source != {
        "provider": "KIS Open API virtual paper",
        "endpoint": "dailyprice",
        "exchange": NAS_EXCHANGE,
        "adjustment_mode": KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        "fixed_current_listing_basket": True,
        "point_in_time_universe": False,
    }:
        raise KisPaperDailyNasForwardCacheError("forward source is invalid")
    redaction = index["redaction"]
    if redaction != {
        "credentials_persisted": False,
        "account_facts_persisted": False,
        "request_headers_persisted": False,
        "response_bodies_persisted": False,
        "raw_rows_in_index": False,
    }:
        raise KisPaperDailyNasForwardCacheError("forward redaction is invalid")
    if (
        tuple(
            str(item.get("target_key", ""))
            for item in index["targets"]
            if isinstance(item, Mapping)
        )
        != _TARGET_KEYS
    ):
        raise KisPaperDailyNasForwardCacheError("forward target ordering is invalid")
    for target in index["targets"]:
        _validate_target(target, frozen_boundary=frozen_boundary)


def _validate_target(value: object, *, frozen_boundary: date) -> None:
    if not isinstance(value, Mapping) or set(value) != {
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
    }:
        raise KisPaperDailyNasForwardCacheError("forward target is invalid")
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
        raise KisPaperDailyNasForwardCacheError("forward target is invalid")
    if row_count == 0:
        if any(item is not None for item in (latest, snapshot_path, snapshot_sha256, rows_sha256)):
            raise KisPaperDailyNasForwardCacheError("empty forward target is invalid")
        return
    latest_date = _date(latest, "forward latest session")
    if (
        latest_date <= frozen_boundary
        or not isinstance(snapshot_path, str)
        or not snapshot_path
        or not _is_sha256(snapshot_sha256)
        or not _is_sha256(rows_sha256)
    ):
        raise KisPaperDailyNasForwardCacheError("forward target snapshot is invalid")


def _target_document(index: Mapping[str, object], target_key: str) -> dict[str, object]:
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise KisPaperDailyNasForwardCacheError("forward targets are invalid")
    for target in targets:
        if isinstance(target, Mapping) and target.get("target_key") == target_key:
            return dict(target)
    raise KisPaperDailyNasForwardCacheError("forward target is unavailable")


def _empty_target_document(
    prior: Mapping[str, object] | None,
    *,
    target_key: str | None = None,
) -> dict[str, object]:
    key = target_key or str(prior and prior.get("target_key"))
    if key not in _TARGET_KEYS:
        raise KisPaperDailyNasForwardCacheError("forward target key is invalid")
    return {
        "target_key": key,
        "status": "input_unavailable",
        "accepted_page_count": 0 if prior is None else int(prior["accepted_page_count"]),
        "categorical_failure_count": 0
        if prior is None
        else int(prior["categorical_failure_count"]),
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
    rows: tuple[KisPaperDailyNasForwardRow, ...],
    snapshot_path: str | None,
    snapshot_sha256: str | None,
    rows_sha256: str | None,
) -> dict[str, object]:
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
        raise ValueError("forward rows hash is unavailable")
    return {
        "target_key": prior["target_key"],
        "status": "ready",
        "accepted_page_count": int(prior["accepted_page_count"]) + 1,
        "categorical_failure_count": int(prior["categorical_failure_count"]),
        "latest_session": rows[-1].session_date.isoformat(),
        "row_count": len(rows),
        "snapshot_path": snapshot_path if snapshot_path is not None else prior.get("snapshot_path"),
        "snapshot_sha256": snapshot_sha256
        if snapshot_sha256 is not None
        else prior.get("snapshot_sha256"),
        "rows_sha256": rows_sha256,
        "last_reason": None,
    }


def _failure_target_document(prior: Mapping[str, object], reason: str) -> dict[str, object]:
    if reason not in _SAFE_REASONS:
        raise ValueError("forward failure reason is invalid")
    result = dict(prior)
    result["status"] = "deferred"
    result["categorical_failure_count"] = int(prior["categorical_failure_count"]) + 1
    result["last_reason"] = reason
    return result


def _load_target_rows(
    *,
    root: Path,
    target: Mapping[str, object],
    symbol: str,
) -> tuple[KisPaperDailyNasForwardRow, ...]:
    if int(target["row_count"]) == 0:
        return ()
    snapshot_path = _safe_child(root / str(target["snapshot_path"]), root)
    try:
        payload = snapshot_path.read_bytes()
    except OSError as error:
        raise KisPaperDailyNasForwardCacheError("forward snapshot is unreadable") from error
    if _sha256(payload) != target["snapshot_sha256"]:
        raise KisPaperDailyNasForwardCacheError("forward snapshot hash is invalid")
    rows = _parse_compressed_rows(payload, symbol=symbol)
    if (
        len(rows) != int(target["row_count"])
        or _rows_sha256(rows) != target["rows_sha256"]
        or rows[-1].session_date.isoformat() != target["latest_session"]
    ):
        raise KisPaperDailyNasForwardCacheError("forward snapshot contents are invalid")
    return rows


def _merge_rows(
    existing: Sequence[KisPaperDailyNasForwardRow],
    incoming: Sequence[KisPaperDailyNasForwardRow],
    *,
    symbol: str,
) -> tuple[KisPaperDailyNasForwardRow, ...]:
    by_session: dict[date, KisPaperDailyNasForwardRow] = {}
    for row in (*existing, *incoming):
        if row.symbol != symbol:
            raise ValueError("forward row symbol is invalid")
        prior = by_session.get(row.session_date)
        if prior is not None and prior != row:
            raise KisPaperDailyNasForwardCacheError("forward duplicate conflict")
        by_session[row.session_date] = row
    return tuple(by_session[session] for session in sorted(by_session))


def _write_snapshot(*, root: Path, symbol: str, payload: bytes) -> str:
    directory = _safe_child(root / "snapshots" / symbol, root)
    directory.mkdir(parents=True, exist_ok=True)
    destination = _safe_child(directory / f"snapshot-{uuid.uuid4().hex}.csv.gz", root)
    _write_bytes_new(destination, payload)
    return destination.relative_to(root).as_posix()


def _compressed_rows(rows: Sequence[KisPaperDailyNasForwardRow]) -> bytes:
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
    payload: bytes, *, symbol: str
) -> tuple[KisPaperDailyNasForwardRow, ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
            reader = csv.DictReader(io.StringIO(handle.read().decode("utf-8"), newline=""))
            if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                raise ValueError
            rows = tuple(
                KisPaperDailyNasForwardRow(
                    symbol=str(row["symbol"]),
                    session_date=_date(row["session_date"], "forward session"),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                )
                for row in reader
            )
    except (KeyError, OSError, UnicodeDecodeError, InvalidOperation, ValueError) as error:
        raise KisPaperDailyNasForwardCacheError("forward snapshot contents are invalid") from error
    return _merge_rows((), rows, symbol=symbol)


def _rows_sha256(rows: Sequence[KisPaperDailyNasForwardRow]) -> str:
    return _sha256("\n".join("\x1f".join(row.raw_record()) for row in rows).encode("utf-8"))


def _external_root(root: Path, repository: Path, *, create: bool) -> Path:
    if root.is_symlink():
        raise KisPaperDailyNasForwardCacheError("forward cache root is invalid")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir() or root.is_symlink():
        raise KisPaperDailyNasForwardCacheError("forward cache root is invalid")
    resolved = root.resolve(strict=True)
    mounted_market_data = repository / "market_data"
    if resolved.is_relative_to(repository) and not (
        mounted_market_data.is_mount() and resolved.is_relative_to(mounted_market_data)
    ):
        raise KisPaperDailyNasForwardCacheError("forward cache must stay outside Git")
    return resolved


def _repository_root(value: Path | str | None) -> Path:
    return Path(value or Path(__file__).resolve().parents[3]).resolve()


def _safe_child(path: Path, root: Path) -> Path:
    if path.is_symlink():
        raise KisPaperDailyNasForwardCacheError("forward cache path is invalid")
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(root.resolve()):
        raise KisPaperDailyNasForwardCacheError("forward cache path escapes root")
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
        raise KisPaperDailyNasForwardCacheError("forward cache destination exists")
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _json_mapping(payload: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperDailyNasForwardCacheError(f"{label} is invalid") from error
    if not isinstance(value, dict):
        raise KisPaperDailyNasForwardCacheError(f"{label} is invalid")
    return value


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    if path.is_symlink():
        raise KisPaperDailyNasForwardCacheError("forward lock is invalid")
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

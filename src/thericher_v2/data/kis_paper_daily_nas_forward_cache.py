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
    has_complete_us_equity_session_coverage,
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
        "daily_retained_revision_conflict",
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
_FAILURE_STAGES = frozenset(
    {
        "observation_input",
        "cache_access",
        "cache_commit",
        "verified_base_load",
        "target_fetch",
        "overlap_reconciliation",
        "cache_publish",
        "published_cache_load",
    }
)


class KisPaperDailyNasForwardCacheError(RuntimeError):
    """A non-secret structural failure in the private forward cache."""

    def __init__(self, *args: object, category: str = "cache_contract") -> None:
        super().__init__(*args)
        self._nas_forward_failure_category = category


def get_kis_paper_daily_nas_forward_failure_details(error: BaseException) -> dict[str, str]:
    """Project only closed diagnostic values, never exception text or chained errors."""

    category = "collector_error"
    if isinstance(error, KisPaperDailyNasForwardCacheError):
        category = "cache_contract"
        if getattr(error, "_nas_forward_failure_category", None) == "duplicate_conflict":
            category = "duplicate_conflict"
    elif isinstance(error, OSError):
        category = "io_error"
    elif isinstance(error, ValueError):
        category = "value_error"
    stage = getattr(error, "_nas_forward_failure_stage", None)
    details = {
        "failure_stage": stage if type(stage) is str and stage in _FAILURE_STAGES else "unknown",
        "failure_category": category,
    }
    symbol = getattr(error, "_nas_forward_failure_symbol", None)
    if (
        details["failure_stage"] != "unknown"
        and type(symbol) is str
        and symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        details["failure_symbol"] = symbol
    return details


@contextmanager
def kis_paper_daily_nas_forward_failure_context(
    stage: str, *, symbol: str | None = None
) -> Iterator[None]:
    """Annotate an existing exception without changing its type or handling."""

    if stage not in _FAILURE_STAGES or (
        symbol is not None and symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS forward failure context is invalid")
    try:
        yield
    except (RuntimeError, OSError, ValueError) as error:
        if get_kis_paper_daily_nas_forward_failure_details(error)["failure_stage"] == "unknown":
            error._nas_forward_failure_stage = stage
            error._nas_forward_failure_symbol = symbol
        raise


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
    retained_revision_snapshot_count: int = 0

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
            or type(self.retained_revision_snapshot_count) is not int
            or self.retained_revision_snapshot_count < 0
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
        expected_common = _common_forward_sessions(streams)
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
            "retained_revision_snapshot_count": self.retained_revision_snapshot_count,
            "canonical_revision_policy": "first_retained_not_point_in_time",
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
    # The persisted reason is shared with fetch failures; the stage belongs to this run.
    overlap_conflict_symbols: tuple[str, ...] = ()

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
            or len(set(self.overlap_conflict_symbols)) != len(self.overlap_conflict_symbols)
            or len(self.overlap_conflict_symbols) > self.categorical_failure_count
            or any(
                symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
                or self.cache.targets_by_key[f"{symbol}/{NAS_EXCHANGE}"].last_reason
                not in {"daily_duplicate_conflict", "daily_retained_revision_conflict"}
                for symbol in self.overlap_conflict_symbols
            )
        ):
            raise ValueError("NAS forward run is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
        if self.categorical_failure_count:
            payload["target_failures"] = [
                {
                    "failure_stage": (
                        "overlap_reconciliation"
                        if target_key.split("/", maxsplit=1)[0] in self.overlap_conflict_symbols
                        else "target_fetch"
                    ),
                    "failure_category": (
                        "duplicate_conflict"
                        if target_key.split("/", maxsplit=1)[0] in self.overlap_conflict_symbols
                        else target.last_reason
                    ),
                    "failure_symbol": target_key.split("/", maxsplit=1)[0],
                }
                for target_key, target in self.cache.targets_by_key.items()
                if target.last_reason is not None
                and (
                    target.last_reason != "daily_retained_revision_conflict"
                    or target_key.split("/", maxsplit=1)[0] in self.overlap_conflict_symbols
                )
            ]
        return payload


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
    retain_revisions: bool = False,
) -> KisPaperDailyNasForwardRun:
    """Atomically retain one source-local forward observation per successful target."""

    with kis_paper_daily_nas_forward_failure_context("observation_input"):
        if type(retain_revisions) is not bool:
            raise ValueError("NAS revision retention mode is invalid")
        _validate_observation_inputs(
            rows_by_symbol=rows_by_symbol,
            failure_reasons_by_symbol=failure_reasons_by_symbol,
            frozen_boundary=frozen_boundary,
        )
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    repository = _repository_root(repo_root)
    effective_failures = dict(failure_reasons_by_symbol)
    overlap_conflict_symbols: list[str] = []
    with kis_paper_daily_nas_forward_failure_context("cache_access"):
        root = _external_root(Path(cache_root), repository, create=True)
    with (
        kis_paper_daily_nas_forward_failure_context("cache_commit"),
        _exclusive_lock(root / _LOCK_FILENAME),
    ):
        with kis_paper_daily_nas_forward_failure_context("verified_base_load"):
            index_path = _safe_child(root / _INDEX_FILENAME, root)
            index_exists = index_path.exists()
            index = _load_or_initialize_index(root=root, frozen_boundary=frozen_boundary)
            _validate_index(index, frozen_boundary=frozen_boundary)
            _validate_retained_revisions(root, index)
        revisions = list(index.get("retained_revisions", []))
        merged_by_symbol: dict[str, tuple[KisPaperDailyNasForwardRow, ...]] = {}
        changed_symbols: set[str] = set()
        pending_snapshots: dict[str, tuple[bytes, str, str, int]] = {}
        target_updates: dict[str, dict[str, object]] = {}

        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
            target_key = f"{symbol}/{NAS_EXCHANGE}"
            with kis_paper_daily_nas_forward_failure_context("verified_base_load", symbol=symbol):
                target = _target_document(index, target_key)
                existing = _load_target_rows(root=root, target=target, symbol=symbol)
            if symbol in effective_failures:
                target_updates[target_key] = _failure_target_document(
                    target,
                    effective_failures[symbol],
                )
                merged_by_symbol[symbol] = existing
                continue
            incoming = _merge_rows(
                (),
                tuple(row for row in rows_by_symbol[symbol] if row.session_date > frozen_boundary),
                symbol=symbol,
            )
            try:
                with kis_paper_daily_nas_forward_failure_context(
                    "overlap_reconciliation", symbol=symbol
                ):
                    merged = _merge_rows(existing, incoming, symbol=symbol)
            except KisPaperDailyNasForwardCacheError as error:
                if get_kis_paper_daily_nas_forward_failure_details(error) != {
                    "failure_stage": "overlap_reconciliation",
                    "failure_category": "duplicate_conflict",
                    "failure_symbol": symbol,
                }:
                    raise
                effective_failures[symbol] = "daily_duplicate_conflict"
                overlap_conflict_symbols.append(symbol)
                if not retain_revisions:
                    target_updates[target_key] = _failure_target_document(
                        target, effective_failures[symbol]
                    )
                    merged_by_symbol[symbol] = existing
                    continue
                with kis_paper_daily_nas_forward_failure_context("cache_publish", symbol=symbol):
                    _retain_revision(root, revisions, target, incoming, observed, symbol)
                effective_failures[symbol] = "daily_retained_revision_conflict"
                existing_dates = {row.session_date for row in existing}
                merged = _merge_rows(
                    existing,
                    tuple(row for row in incoming if row.session_date not in existing_dates),
                    symbol=symbol,
                )
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
            with kis_paper_daily_nas_forward_failure_context("cache_publish", symbol=symbol):
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

        # Retention resolves acquisition, not the contradictory values for a predictive consumer.
        for symbol in overlap_conflict_symbols:
            if retain_revisions:
                key = f"{symbol}/{NAS_EXCHANGE}"
                target_updates[key] = _failure_target_document(
                    target_updates[key], "daily_retained_revision_conflict"
                )
        for record in revisions:
            target = target_updates[f"{record['symbol']}/{NAS_EXCHANGE}"]
            if target["status"] == "ready":
                target["status"] = "deferred"
                target["last_reason"] = "daily_retained_revision_conflict"
        updated_index = dict(index)
        if revisions:
            updated_index["retained_revisions"] = revisions
        updated_index["targets"] = [target_updates[target_key] for target_key in _TARGET_KEYS]
        index_changed = not index_exists or updated_index != index
        if index_changed:
            updated_index["generation"] = int(index["generation"]) + 1
            with kis_paper_daily_nas_forward_failure_context("cache_publish"):
                _write_json_atomic(root / _INDEX_FILENAME, updated_index)
        common_sessions = _common_forward_sessions(merged_by_symbol)
        targets_ready = all(target["status"] == "ready" for target in target_updates.values())
        prospective_input_ready = targets_ready and _is_forward_projection_ready(
            common_sessions,
            frozen_boundary=frozen_boundary,
        )
        with kis_paper_daily_nas_forward_failure_context("published_cache_load"):
            cache = load_verified_kis_paper_daily_nas_forward_cache(
                cache_root=root,
                repo_root=repository,
            )

    failures = len(effective_failures)
    has_rows = any(cache.rows_by_symbol.values())
    status: Literal[
        "ready", "partial", "deferred", "input_unavailable", "source_limited", "unchanged"
    ]
    if failures == len(_TARGET_KEYS):
        status = "deferred"
    elif failures or not targets_ready and has_rows:
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
        accepted_page_count=len(rows_by_symbol) - (
            0 if retain_revisions else len(overlap_conflict_symbols)
        ),
        categorical_failure_count=failures,
        changed_target_count=len(changed_symbols),
        prospective_input_status="ready" if prospective_input_ready else "input_unavailable",
        recovery="resume" if failures or not targets_ready and has_rows else "complete",
        overlap_conflict_symbols=tuple(overlap_conflict_symbols),
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
    _validate_retained_revisions(root, index)
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
    common_sessions = _common_forward_sessions(rows_by_symbol)
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
        retained_revision_snapshot_count=len(index.get("retained_revisions", [])),
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
    if any(target.status == "deferred" for target in forward_cache.targets_by_key.values()):
        raise ValueError("NAS historical-forward projection has deferred targets")
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
    if not _has_complete_forward_session_coverage(
        common,
        frozen_boundary=boundary,
    ):
        raise ValueError("NAS historical-forward projection has a normal US session gap")
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


def load_kis_paper_daily_nas_revision_as_of(
    *,
    cache_root: Path | str,
    repo_root: Path | str,
    symbol: str,
    snapshot_sha256: str,
    as_of: datetime,
) -> tuple[KisPaperDailyNasForwardRow, ...]:
    """Read one exact retained whole-page vintage, never a mixed or latest-row view.

    Local recording time is only a conservative availability bound. This proves
    neither original historical availability nor source finality/correctness.
    """
    as_of = require_utc(as_of, "as_of")
    root = _external_root(Path(cache_root), _repository_root(repo_root), create=False)
    index = _json_mapping(_safe_child(root / _INDEX_FILENAME, root).read_bytes(), "forward index")
    _validate_index(index, frozen_boundary=_date(index.get("frozen_boundary"), "boundary"))
    _validate_retained_revisions(root, index)
    matches = [
        record for record in index.get("retained_revisions", [])
        if record["symbol"] == symbol and record["snapshot_sha256"] == snapshot_sha256
    ]
    if len(matches) != 1 or datetime.fromisoformat(matches[0]["recorded_at"]) > as_of:
        raise KisPaperDailyNasForwardCacheError("revision unavailable at requested time")
    payload = _safe_child(root / matches[0]["snapshot_path"], root).read_bytes()
    if _sha256(payload) != snapshot_sha256:
        raise KisPaperDailyNasForwardCacheError("retained revision hash is invalid")
    return _parse_compressed_rows(payload, symbol=symbol)


def sanitize_kis_paper_daily_nas_forward_failure_reason(value: BaseException | str) -> str:
    """Reduce a transport/parser failure to the cache's source-safe taxonomy."""

    reason = str(value).strip()
    return reason if reason in _SAFE_REASONS else "unexpected_private_daily_collector_error"


def _common_forward_sessions(
    rows_by_symbol: Mapping[str, Sequence[KisPaperDailyNasForwardRow]],
) -> tuple[date, ...]:
    if not rows_by_symbol:
        return ()
    return tuple(
        sorted(
            set.intersection(
                *(set(row.session_date for row in rows) for rows in rows_by_symbol.values())
            )
        )
    )


def _has_complete_forward_session_coverage(
    sessions: tuple[date, ...],
    *,
    frozen_boundary: date,
) -> bool:
    return bool(sessions) and has_complete_us_equity_session_coverage(
        (frozen_boundary, *sessions)
    )


def _is_forward_projection_ready(
    sessions: tuple[date, ...],
    *,
    frozen_boundary: date,
) -> bool:
    if len(sessions) < KIS_PAPER_DAILY_NAS_FORWARD_TARGET_SLOT_SESSIONS:
        return False
    try:
        return _has_complete_forward_session_coverage(
            sessions,
            frozen_boundary=frozen_boundary,
        )
    except ValueError:
        return False


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
        set(index) not in (expected, expected | {"retained_revisions"})
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
        "status": (
            "deferred"
            if prior.get("last_reason") == "daily_retained_revision_conflict" else "ready"
        ),
        "accepted_page_count": int(prior["accepted_page_count"]) + 1,
        "categorical_failure_count": int(prior["categorical_failure_count"]),
        "latest_session": rows[-1].session_date.isoformat(),
        "row_count": len(rows),
        "snapshot_path": snapshot_path if snapshot_path is not None else prior.get("snapshot_path"),
        "snapshot_sha256": snapshot_sha256
        if snapshot_sha256 is not None
        else prior.get("snapshot_sha256"),
        "rows_sha256": rows_sha256,
        "last_reason": (
            "daily_retained_revision_conflict"
            if prior.get("last_reason") == "daily_retained_revision_conflict" else None
        ),
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
            raise KisPaperDailyNasForwardCacheError(
                "forward duplicate conflict", category="duplicate_conflict"
            )
        by_session[row.session_date] = row
    return tuple(by_session[session] for session in sorted(by_session))


def _write_snapshot(*, root: Path, symbol: str, payload: bytes) -> str:
    directory = _safe_child(root / "snapshots" / symbol, root)
    directory.mkdir(parents=True, exist_ok=True)
    destination = _safe_child(directory / f"snapshot-{uuid.uuid4().hex}.csv.gz", root)
    _write_bytes_new(destination, payload)
    return destination.relative_to(root).as_posix()


def _retain_revision(
    root: Path,
    records: list[dict[str, object]],
    prior: Mapping[str, object],
    incoming: tuple[KisPaperDailyNasForwardRow, ...],
    observed: datetime,
    symbol: str,
) -> None:
    rows_hash = _rows_sha256(incoming)
    # Identical pages need no second copy or a fabricated new first-observation time.
    if any(item["symbol"] == symbol and item["rows_sha256"] == rows_hash for item in records):
        return
    payload = _compressed_rows(incoming)
    prior_rows = _load_target_rows(root=root, target=prior, symbol=symbol)
    by_date = {row.session_date: row for row in prior_rows}
    changed = sum(
        row.session_date in by_date and by_date[row.session_date] != row for row in incoming
    )
    records.append({
        "symbol": symbol,
        "recorded_at": max(datetime.now(UTC), observed).isoformat(),
        "snapshot_path": _write_snapshot(root=root, symbol=symbol, payload=payload),
        "snapshot_sha256": _sha256(payload),
        "rows_sha256": rows_hash,
        "row_count": len(incoming),
        "revised_row_count": changed,
        "prior_target": dict(prior),
    })


def _validate_retained_revisions(root: Path, index: Mapping[str, object]) -> None:
    records = index.get("retained_revisions", [])
    if not isinstance(records, list):
        raise KisPaperDailyNasForwardCacheError("retained revisions are invalid")
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "symbol", "recorded_at", "snapshot_path", "snapshot_sha256", "rows_sha256",
            "row_count", "revised_row_count", "prior_target",
        }:
            raise KisPaperDailyNasForwardCacheError("retained revision is invalid")
        symbol = record["symbol"]
        if (
            symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or type(record["row_count"]) is not int or record["row_count"] <= 0
            or type(record["revised_row_count"]) is not int
            or not 0 < record["revised_row_count"] <= record["row_count"]
            or not isinstance(record["snapshot_path"], str)
            or not _is_sha256(record["snapshot_sha256"])
            or not _is_sha256(record["rows_sha256"])
            or (symbol, record["rows_sha256"]) in seen
        ):
            raise KisPaperDailyNasForwardCacheError("retained revision metadata is invalid")
        try:
            require_utc(datetime.fromisoformat(record["recorded_at"]), "recorded_at")
        except (TypeError, ValueError) as error:
            raise KisPaperDailyNasForwardCacheError("retained revision time is invalid") from error
        seen.add((symbol, record["rows_sha256"]))
        boundary = _date(index["frozen_boundary"], "forward boundary")
        prior = record["prior_target"]
        _validate_target(prior, frozen_boundary=boundary)
        if prior["target_key"] != f"{symbol}/{NAS_EXCHANGE}":
            raise KisPaperDailyNasForwardCacheError("retained revision target is invalid")
        prior_rows = _load_target_rows(root=root, target=prior, symbol=symbol)
        try:
            payload = _safe_child(root / record["snapshot_path"], root).read_bytes()
        except OSError as error:
            raise KisPaperDailyNasForwardCacheError("retained revision is unreadable") from error
        if _sha256(payload) != record["snapshot_sha256"]:
            raise KisPaperDailyNasForwardCacheError("retained revision hash is invalid")
        rows = _parse_compressed_rows(payload, symbol=symbol)
        by_date = {row.session_date: row for row in prior_rows}
        if (
            len(rows) != record["row_count"] or _rows_sha256(rows) != record["rows_sha256"]
            or any(row.session_date <= boundary for row in rows)
            or sum(row.session_date in by_date and by_date[row.session_date] != row for row in rows)
            != record["revised_row_count"]
        ):
            raise KisPaperDailyNasForwardCacheError("retained revision contents are invalid")
    revised_symbols = {symbol for symbol, _ in seen}
    for target in index["targets"]:
        symbol = target["target_key"].split("/")[0]
        if (
            symbol in revised_symbols and target["status"] != "deferred"
            or target["last_reason"] == "daily_retained_revision_conflict"
            and symbol not in revised_symbols
        ):
            raise KisPaperDailyNasForwardCacheError("retained revision state is invalid")


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
            records = tuple(reader)
            if any(row["exchange"] != NAS_EXCHANGE for row in records):
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
                for row in records
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

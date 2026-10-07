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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
    validate_kis_paper_minute_failure_diagnostic,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    KIS_PAPER_MARKET_DATA_TOKEN_REQUEST_NOT_DUE_REASON,
)

KIS_PAPER_MARKET_DATA_ROOT = Path(r"D:\market_data")
KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT = (
    KIS_PAPER_MARKET_DATA_ROOT / "us_equities" / "kis_paper_private" / "intraday"
)
KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT = (
    KIS_PAPER_MARKET_DATA_ROOT / "us_equities" / "kis_paper_private" / "iwm_current_head"
)
KIS_PAPER_IWM_M1_CURRENT_HEAD_REPLAY_CACHE_ROOT = (
    KIS_PAPER_MARKET_DATA_ROOT / "us_equities" / "kis_paper_private" / "iwm_m1_current_head"
)
KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION = "v1"
KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME = "index.json"
KIS_PAPER_PRIVATE_INTRADAY_SNAPSHOT_DIRECTORY = "snapshots"
KIS_PAPER_PRIVATE_INTRADAY_LOCK_FILENAME = ".backfill.lock"
KIS_PAPER_PRIVATE_INTRADAY_MIN_REQUEST_INTERVAL_SECONDS = (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
)
KIS_PAPER_PRIVATE_INTRADAY_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
KIS_PAPER_QQQ_DATED_SESSION = date(2026, 9, 1)
KIS_PAPER_QQQ_DATED_INITIAL_KEY = "20260901155900"
KIS_PAPER_QQQ_DATED_CACHE_ROOT = (
    KIS_PAPER_MARKET_DATA_ROOT / "us_equities/kis_paper_private/intraday-dated/qqq-20260901"
)
KIS_PAPER_IWM_CURRENT_HEAD_TARGET = ("IWM", "AMS")
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
KIS_PAPER_PRIVATE_INTRADAY_CONFLICT_ORIGINS = frozenset({"candidate_batch", "retained_cache"})
KIS_PAPER_PRIVATE_INTRADAY_RETAINED_HEAD_CONFLICT_DISPOSITIONS = frozenset(
    {"not_applicable", "preserved", "quarantined"}
)


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
    conflict_origin: _ConflictOrigin | None = None
    retained_head_conflict_disposition: Literal["not_applicable", "preserved", "quarantined"] = (
        "not_applicable"
    )
    schema_version: int = SCHEMA_VERSION

    failure_phase: str | None = None
    failure_code: str | None = None
    failure_page_ordinal: int | None = None
    requested_pages_per_target: int | None = None

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
        validate_kis_paper_minute_failure_diagnostic(
            reason=self.reason,
            phase=self.failure_phase,
            code=self.failure_code,
            page_ordinal=self.failure_page_ordinal,
            requested_pages_per_target=self.requested_pages_per_target,
        )
        if self.failure_phase is not None and self.status not in {"partial", "rejected"}:
            raise ValueError("private intraday failure diagnostic is invalid")
        if self.conflict_origin not in KIS_PAPER_PRIVATE_INTRADAY_CONFLICT_ORIGINS | {None}:
            raise ValueError("private intraday conflict origin is invalid")
        if (
            self.retained_head_conflict_disposition
            not in KIS_PAPER_PRIVATE_INTRADAY_RETAINED_HEAD_CONFLICT_DISPOSITIONS
        ):
            raise ValueError("private intraday conflict disposition is invalid")
        if self.conflict_origin is None:
            if self.retained_head_conflict_disposition != "not_applicable":
                raise ValueError("private intraday conflict disposition is invalid")
            if self.reason == "minute_duplicate_conflict":
                raise ValueError("private intraday conflict provenance is invalid")
            return
        if self.status != "rejected" or self.reason != "minute_duplicate_conflict":
            raise ValueError("private intraday conflict provenance is invalid")
        if self.conflict_origin == "candidate_batch":
            if self.retained_head_conflict_disposition != "not_applicable":
                raise ValueError("private intraday conflict disposition is invalid")
            return
        if self.retained_head_conflict_disposition not in {"preserved", "quarantined"}:
            raise ValueError("private intraday conflict disposition is invalid")


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
    failure_phase: str | None = None
    failure_code: str | None = None
    failure_page_ordinal: int | None = None
    requested_pages_per_target: int | None = None


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
    explicit_qqq_head_continuation: bool = False,
    explicit_pair_head_continuation: bool = False,
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
    """Collect QQQ/SPY with separate QQQ-only or paired bounded head opt-ins.

    Both options require head mode and at most eight pages per target. The
    QQQ-only option leaves SPY unchanged; neither changes historical cursors
    or attests source availability.
    """

    return _run_kis_paper_private_intraday_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision=code_revision,
        targets=KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
        pages_per_target=pages_per_target,
        resume_cursor=resume_cursor,
        quarantine_retained_head_conflicts=quarantine_retained_head_conflicts,
        explicit_qqq_head_continuation=explicit_qqq_head_continuation,
        explicit_pair_head_continuation=explicit_pair_head_continuation,
        observed_at=observed_at,
        sleeper=sleeper,
        monotonic_clock=monotonic_clock,
    )


def run_kis_paper_iwm_current_head_cycle(
    *,
    client: KisPaperPrivateIntradayClient,
    cache_root: Path,
    repo_root: Path,
    code_revision: str,
    target: tuple[str, str] = KIS_PAPER_IWM_CURRENT_HEAD_TARGET,
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> KisPaperPrivateIntradayBackfillRun:
    """Collect exactly one isolated IWM current-head page with no cursor path."""

    validate_kis_paper_iwm_current_head_request(
        target=target,
        cache_root=cache_root,
        repo_root=repo_root,
    )
    targets = (KIS_PAPER_IWM_CURRENT_HEAD_TARGET,)
    results = _run_kis_paper_private_intraday_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision=code_revision,
        targets=targets,
        pages_per_target=1,
        resume_cursor=False,
        quarantine_retained_head_conflicts=False,
        observed_at=observed_at,
        sleeper=sleeper,
        monotonic_clock=monotonic_clock,
    )
    if len(results) != 1 or results[0].target_key != "IWM/AMS/1m":
        raise ValueError("IWM current-head result is invalid")
    return results[0]


def validate_kis_paper_iwm_current_head_request(
    *,
    target: tuple[str, str],
    cache_root: Path,
    repo_root: Path,
    market_data_root: Path | None = None,
    protected_cache_roots: tuple[Path, ...] = (
        KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
        KIS_PAPER_IWM_M1_CURRENT_HEAD_REPLAY_CACHE_ROOT,
    ),
) -> Path:
    """Reject an unsafe IWM head request before a client can issue a call."""

    targets = _normalize_private_intraday_targets((target,))
    if targets != (KIS_PAPER_IWM_CURRENT_HEAD_TARGET,):
        raise ValueError("IWM current-head target is invalid")
    return _validate_iwm_current_head_cache_root(
        cache_root=cache_root,
        repo_root=repo_root,
        market_data_root=market_data_root or KIS_PAPER_MARKET_DATA_ROOT,
        protected_cache_roots=protected_cache_roots,
    )


def validate_kis_paper_qqq_dated_session_request(
    *,
    cache_root: Path,
    repo_root: Path,
    session_date: date,
    pages: int,
    inspect_paths: bool = True,
    observed_at: datetime | None = None,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> Path:
    """Bind this finite request before credentials; preview performs no filesystem IO."""
    target = _dated_session_target(target)
    _dated_qqq_keys(session_date, observed_at=observed_at)
    root = Path(cache_root)
    if (
        type(session_date) is not date
        or type(pages) is not int
        or not 1 <= pages <= 4
        or type(inspect_paths) is not bool
        or not root.is_absolute()
        or root != kis_paper_qqq_dated_session_cache_root(session_date, target=target)
        or root.is_relative_to(Path(repo_root))
    ):
        raise ValueError("QQQ dated-session request is invalid")
    if inspect_paths:
        # Reject junctions as well as symlinks, including retained descendants.
        candidates = [root, *root.parents]
        while candidates:
            candidate = candidates.pop()
            try:
                info = candidate.lstat()
            except FileNotFoundError:
                continue
            if getattr(info, "st_file_attributes", 0) & 0x400 or candidate.is_symlink():
                raise ValueError("QQQ dated-session path is invalid")
            if candidate.is_relative_to(root) and candidate.is_dir():
                candidates.extend(candidate.iterdir())
        if root.resolve().is_relative_to(Path(repo_root).resolve()):
            raise ValueError("QQQ dated-session path is invalid")
    return root


def _dated_session_target(target: tuple[str, str]) -> tuple[str, str]:
    if (
        type(target) is not tuple
        or any(type(value) is not str for value in target)
        or target not in KIS_PAPER_PRIVATE_INTRADAY_TARGETS
    ):
        raise ValueError("dated-session target must be QQQ/NAS or SPY/AMS")
    return target


def kis_paper_qqq_dated_session_cache_root(
    session_date: date,
    *,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> Path:
    """Use exactly one independent external v1 parent per explicit date."""
    target = _dated_session_target(target)
    if type(session_date) is not date or session_date.year != 2026:
        raise ValueError("QQQ dated-session date is invalid")
    return KIS_PAPER_QQQ_DATED_CACHE_ROOT.parent / f"{target[0].lower()}-{session_date:%Y%m%d}"


def _dated_qqq_keys(
    session_date: date,
    *,
    observed_at: datetime | None = None,
) -> tuple[str, str]:
    from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

    session = us_equity_2026_session(session_date)
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    if session is None or session.kind != "regular" or session.window.close_ts > observed:
        raise ValueError("QQQ dated-session must be a closed 2026 regular session")
    return (
        session.window.open_ts.astimezone(US_EQUITY_EASTERN).strftime("%Y%m%d%H%M%S"),
        (session.window.close_ts - timedelta(minutes=1))
        .astimezone(US_EQUITY_EASTERN)
        .strftime("%Y%m%d%H%M%S"),
    )


def kis_paper_qqq_dated_session_initial_key(
    session_date: date,
    *,
    observed_at: datetime | None = None,
) -> str:
    """Calendar close minus one minute; temporal reach remains measured, not promised."""
    return _dated_qqq_keys(session_date, observed_at=observed_at)[1]


def kis_paper_qqq_dated_session_complete(
    *,
    cache_root: Path,
    repo_root: Path,
    session_date: date = KIS_PAPER_QQQ_DATED_SESSION,
    observed_at: datetime | None = None,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> bool:
    """Only the verified canonical reader can establish the regular-minute cohort."""
    validate_kis_paper_qqq_dated_session_request(
        cache_root=cache_root,
        repo_root=repo_root,
        session_date=session_date,
        pages=4,
        observed_at=observed_at,
        target=target,
    )
    from thericher_v2.data.kis_paper_intraday import (
        load_verified_kis_paper_private_intraday_catalog,
        require_complete_kis_paper_private_intraday_session,
    )
    from thericher_v2.data.us_equity_session import us_equity_2026_session

    session = us_equity_2026_session(session_date)
    assert session is not None
    try:
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=cache_root,
            repo_root=repo_root,
            symbol=target[0],
            exchange=target[1],
        )
        require_complete_kis_paper_private_intraday_session(catalog, session=session.window)
    except ValueError as error:
        if str(error) not in {
            "private intraday session is incomplete",
            "private intraday session has no source bars",
            "private intraday cache has no retained bars",
        }:
            raise
        return False
    return True


def run_kis_paper_qqq_dated_session_cycle(
    *,
    client: KisPaperPrivateIntradayClient,
    cache_root: Path,
    repo_root: Path,
    code_revision: str,
    session_date: date = KIS_PAPER_QQQ_DATED_SESSION,
    pages: int = 4,
    observed_at: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic_clock: Callable[[], float] = time.monotonic,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> KisPaperPrivateIntradayBackfillRun:
    """One explicit native closed-date invocation; never borrow or reseed another cursor."""
    validate_kis_paper_qqq_dated_session_request(
        cache_root=cache_root,
        repo_root=repo_root,
        session_date=session_date,
        pages=pages,
        observed_at=observed_at,
        target=target,
    )
    return _run_kis_paper_private_intraday_cycle(
        client=client,
        cache_root=cache_root,
        repo_root=repo_root,
        code_revision=code_revision,
        targets=(target,),
        pages_per_target=pages,
        resume_cursor=True,
        quarantine_retained_head_conflicts=False,
        observed_at=observed_at,
        sleeper=sleeper,
        monotonic_clock=monotonic_clock,
        dated_qqq_session=session_date,
    )[0]


def _run_kis_paper_private_intraday_cycle(
    *,
    client: KisPaperPrivateIntradayClient,
    cache_root: Path,
    repo_root: Path,
    code_revision: str,
    targets: tuple[tuple[str, str], ...],
    pages_per_target: int,
    resume_cursor: bool,
    quarantine_retained_head_conflicts: bool,
    observed_at: datetime | None,
    sleeper: Callable[[float], None],
    monotonic_clock: Callable[[], float],
    explicit_qqq_head_continuation: bool = False,
    explicit_pair_head_continuation: bool = False,
    dated_qqq_session: date | None = None,
) -> tuple[KisPaperPrivateIntradayBackfillRun, ...]:
    """Collect bounded source pages with optional historical-cursor resumption.

    A head observation sets ``resume_cursor`` false: it starts from the latest
    source page and retains its snapshot without changing any persisted cursor.
    A failed attempt creates no data-bearing chunk, so it is recovery evidence
    for that call only and never a later collection latch.
    """

    targets = _normalize_private_intraday_targets(targets)
    if dated_qqq_session:
        if len(targets) != 1:
            raise ValueError("dated-session target scope is invalid")
        _dated_session_target(targets[0])
    if type(pages_per_target) is not int or pages_per_target <= 0:
        raise ValueError("pages_per_target must be a positive integer")
    if type(resume_cursor) is not bool:
        raise ValueError("resume_cursor must be a boolean")
    if type(quarantine_retained_head_conflicts) is not bool:
        raise ValueError("head conflict quarantine must be a boolean")
    if quarantine_retained_head_conflicts and resume_cursor:
        raise ValueError("head conflict quarantine requires head mode")
    if type(explicit_qqq_head_continuation) is not bool:
        raise ValueError("explicit QQQ head continuation must be a boolean")
    if type(explicit_pair_head_continuation) is not bool:
        raise ValueError("explicit paired head continuation must be a boolean")
    if explicit_qqq_head_continuation and explicit_pair_head_continuation:
        raise ValueError("head continuation options are mutually exclusive")
    if explicit_qqq_head_continuation and (
        resume_cursor or pages_per_target > 8 or targets != KIS_PAPER_PRIVATE_INTRADAY_TARGETS
    ):
        raise ValueError(
            "explicit QQQ head continuation requires QQQ/SPY head mode, at most eight pages"
        )
    if explicit_pair_head_continuation and (
        resume_cursor
        or pages_per_target > 8
        or targets != KIS_PAPER_PRIVATE_INTRADAY_TARGETS
        or dated_qqq_session is not None
    ):
        raise ValueError(
            "explicit paired head continuation requires QQQ/SPY head mode, at most eight pages"
        )
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
            for target in targets
        )
    try:
        index = _read_or_create_index(
            root,
            hydrate_source_exhaustion=resume_cursor and not dated_qqq_session,
            expected_targets=targets,
            initial_cursor=(
                KisPaperPrivateIntradayCursor(
                    "1",
                    kis_paper_qqq_dated_session_initial_key(
                        dated_qqq_session, observed_at=observed
                    ),
                )
                if dated_qqq_session
                else None
            ),
        )
        removed_candidate_chunks = _remove_candidate_batch_conflicted_chunks(
            index, resume_cursor=resume_cursor
        )
        if dated_qqq_session:
            _validate_dated_qqq_state(
                index,
                session_date=dated_qqq_session,
                observed_at=observed,
                target=targets[0],
            )
        _attest_committed_snapshots(root=root, index=index)
        recovered = _recover_orphan_snapshots(root=root, index=index)
        recovered_by_target: dict[str, list[_RecoveredSnapshot]] = {}
        for item in recovered:
            recovered_by_target.setdefault(item.target.target_key, []).append(item)
        if dated_qqq_session:
            _validate_dated_qqq_state(
                index,
                session_date=dated_qqq_session,
                observed_at=observed,
                target=targets[0],
            )
        if removed_candidate_chunks or recovered:
            _attest_committed_snapshots(root=root, index=index)
            _write_index(root=root, index=index, expected_targets=targets)
        results: list[KisPaperPrivateIntradayBackfillRun] = []
        pacer = _RequestPacer(sleeper=sleeper, monotonic_clock=monotonic_clock)
        for symbol, exchange in targets:
            target = KisPaperPrivateIntradayTarget(symbol=symbol, exchange=exchange)
            recovered_snapshots = recovered_by_target.get(target.target_key)
            if recovered_snapshots:
                results.append(_recovered_target_run(target=target, snapshots=recovered_snapshots))
                continue
            target_state = _index_target(index=index, target=target)
            input_cursor = (
                KisPaperPrivateIntradayCursor.from_document(target_state.get("next_cursor"))
                if resume_cursor
                else None
            )
            if dated_qqq_session and target_state["chunks"]:
                complete = kis_paper_qqq_dated_session_complete(
                    cache_root=cache_root,
                    repo_root=repo_root,
                    session_date=dated_qqq_session,
                    observed_at=observed,
                    target=(symbol, exchange),
                )
                if (
                    complete
                    or input_cursor.keyb
                    < _dated_qqq_keys(
                        dated_qqq_session,
                        observed_at=observed,
                    )[0]
                ):
                    results.append(
                        KisPaperPrivateIntradayBackfillRun(
                            status="recovered",
                            target_key=target.target_key,
                            row_count=0,
                            exact_overlap_rows=0,
                            reason="dated_session_complete"
                            if complete
                            else "dated_session_incomplete",
                        )
                    )
                    continue
            if (
                resume_cursor
                and not dated_qqq_session
                and _target_source_is_exhausted(target_state)
            ):
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
                explicit_qqq_head_continuation=(
                    explicit_qqq_head_continuation and target.target_key == "QQQ/NAS/1m"
                ),
                explicit_pair_head_continuation=explicit_pair_head_continuation,
                dated_qqq_session=dated_qqq_session,
                observed_at=observed,
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
                    failure_phase=collected.failure_phase,
                    failure_code=collected.failure_code,
                    failure_page_ordinal=collected.failure_page_ordinal,
                    requested_pages_per_target=collected.requested_pages_per_target,
                )
            if collected.status == "rejected":
                _record_target_last_observation(
                    target_state=target_state,
                    reason=collected.reason,
                    conflict_origin=collected.conflict_origin,
                    observed_at_utc=_format_utc(observed),
                )
                _write_index(root=root, index=index, expected_targets=targets)
                results.append(
                    KisPaperPrivateIntradayBackfillRun(
                        status="rejected",
                        target_key=target.target_key,
                        row_count=0,
                        exact_overlap_rows=0,
                        reason=collected.reason,
                        conflict_origin=collected.conflict_origin,
                        failure_phase=collected.failure_phase,
                        failure_code=collected.failure_code,
                        failure_page_ordinal=collected.failure_page_ordinal,
                        requested_pages_per_target=collected.requested_pages_per_target,
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
                _write_index(root=root, index=index, expected_targets=targets)
                if quarantined_retained_head_chunks:
                    # Durable markers must precede a replacement's orphan-recoverable snapshot.
                    existing_fingerprints = _target_fingerprints(target_state)
                    conflicting_chunk_keys = _conflicting_retained_chunk_keys(
                        rows=collected.rows,
                        target_state=target_state,
                    )
                if conflicting_chunk_keys:
                    results.append(
                        KisPaperPrivateIntradayBackfillRun(
                            status="rejected",
                            target_key=target.target_key,
                            row_count=0,
                            exact_overlap_rows=0,
                            reason="minute_duplicate_conflict",
                            conflict_origin="retained_cache",
                            retained_head_conflict_disposition=(
                                "quarantined" if quarantined_retained_head_chunks else "preserved"
                            ),
                        )
                    )
                    continue

            prior_exact_overlap = sum(
                1 for row in collected.rows if _row_key(row) in existing_fingerprints
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
                    collected.reason
                    if collected.status == "partial"
                    else (
                        "source_exhausted"
                        if _collected_target_source_is_exhausted(
                            collected=collected,
                            resume_cursor=resume_cursor and not dated_qqq_session,
                        )
                        else "already_cached"
                    )
                )
                _record_target_last_observation(
                    target_state=target_state,
                    reason=last_reason,
                    observed_at_utc=_format_utc(observed),
                )
                _write_index(root=root, index=index, expected_targets=targets)
                results.append(
                    KisPaperPrivateIntradayBackfillRun(
                        status="partial" if collected.status == "partial" else "recovered",
                        target_key=target.target_key,
                        row_count=len(collected.rows),
                        exact_overlap_rows=(collected.exact_duplicate_rows + prior_exact_overlap),
                        reason=collected.reason
                        if collected.status == "partial"
                        else "already_cached",
                        failure_phase=collected.failure_phase,
                        failure_code=collected.failure_code,
                        failure_page_ordinal=collected.failure_page_ordinal,
                        requested_pages_per_target=collected.requested_pages_per_target,
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
                    resume_cursor=resume_cursor and not dated_qqq_session,
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
            _write_index(root=root, index=index, expected_targets=targets)
            results.append(
                KisPaperPrivateIntradayBackfillRun(
                    status=collected.status,
                    target_key=target.target_key,
                    row_count=len(collected.rows),
                    exact_overlap_rows=(collected.exact_duplicate_rows + prior_exact_overlap),
                    manifest_path=manifest_path,
                    manifest_hash=manifest_hash,
                    reason=collected.reason,
                    failure_phase=collected.failure_phase,
                    failure_code=collected.failure_code,
                    failure_page_ordinal=collected.failure_page_ordinal,
                    requested_pages_per_target=collected.requested_pages_per_target,
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
        reason=(str(latest.chunk["reason"]) if latest.chunk["reason"] is not None else None),
    )


def _collect_target(
    *,
    client: KisPaperPrivateIntradayClient,
    target: KisPaperPrivateIntradayTarget,
    input_cursor: KisPaperPrivateIntradayCursor | None,
    pages_per_target: int,
    before_request: Callable[[], None],
    explicit_qqq_head_continuation: bool = False,
    explicit_pair_head_continuation: bool = False,
    dated_qqq_session: date | None = None,
    observed_at: datetime | None = None,
) -> _CollectedTarget:
    rows_by_key: dict[str, KisPaperMinuteRawBar] = {}
    pages: list[dict[str, object]] = []
    duplicate_rows = 0
    cursor = input_cursor
    explicit_head_continuation = explicit_qqq_head_continuation or explicit_pair_head_continuation
    try:
        for page_number in range(1, pages_per_target + 1):
            query = KisPaperMinuteQuery(
                exchange=target.exchange,
                symbol=target.symbol,
                include_previous_day=(explicit_head_continuation or dated_qqq_session is not None)
                and cursor is not None,
                continuation_next=cursor.next_value if cursor is not None else None,
                continuation_key=cursor.keyb if cursor is not None else None,
            )
            page = client.fetch_minute_page(query, before_request=before_request)
            if not page.bars:
                raise KisPaperMarketDataError("minute_response_empty")
            if explicit_pair_head_continuation:
                _validate_explicit_head_page(
                    page=page, target=target, cursor=cursor, retained_rows=rows_by_key
                )
            if dated_qqq_session:
                _validate_dated_qqq_page(
                    page=page,
                    cursor=cursor,
                    retained_rows=rows_by_key,
                    session_date=dated_qqq_session,
                    target=(target.symbol, target.exchange),
                )
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
            if explicit_qqq_head_continuation:
                _validate_explicit_qqq_head_page(
                    page=page, cursor=cursor, retained_rows=rows_by_key
                )
            next_cursor = _cursor_from_page(page)
            if dated_qqq_session:
                # Retain a resumable frontier even on the last budgeted/short page.
                next_cursor = KisPaperPrivateIntradayCursor(
                    "1",
                    _one_exchange_minute_before(min(page.bars, key=_exchange_stamp)),
                )
            if (
                explicit_head_continuation
                and next_cursor is None
                and page.continuation_signal in {"blank_or_absent", "unrecognized_nonblank"}
                and len(page.bars) == 120
                and page_number < pages_per_target
            ):
                # This is a caller-derived request, not a provider continuation signal.
                try:
                    next_cursor = KisPaperPrivateIntradayCursor(
                        next_value="1",
                        keyb=_one_exchange_minute_before(min(page.bars, key=_exchange_stamp)),
                    )
                except (ValueError, OverflowError) as error:
                    raise KisPaperMarketDataError("minute_cursor_invalid") from error
            if (
                explicit_head_continuation
                and next_cursor is not None
                and next_cursor.keyb[:8] != page.bars[0].exchange_date
            ):
                next_cursor = None
            if explicit_pair_head_continuation and len(page.bars) < 120:
                next_cursor = None
            if (
                explicit_pair_head_continuation
                and next_cursor is not None
                and (
                    next_cursor.keyb
                    >= min(_exchange_stamp(row) for row in page.bars).replace("T", "")
                    or (cursor is not None and next_cursor.keyb >= cursor.keyb)
                )
            ):
                raise KisPaperMarketDataError("minute_cursor_stalled")
            if next_cursor is not None and next_cursor == cursor:
                raise KisPaperMarketDataError("minute_cursor_stalled")
            # A page joins the durable candidate only after its cursor and all
            # same-page duplicates have been validated.
            rows_by_key = prospective_rows
            duplicate_rows += prospective_duplicates
            pages.append(_page_document(page=page, page_number=page_number))
            if dated_qqq_session and (
                len(page.bars) < 120
                or next_cursor.keyb
                < _dated_qqq_keys(
                    dated_qqq_session,
                    observed_at=observed_at,
                )[0]
            ):
                cursor = next_cursor
                break
            if next_cursor is None:
                cursor = None
                break
            cursor = next_cursor
    except KisPaperMarketDataError as error:
        reason = sanitize_kis_paper_private_intraday_failure_reason(error)
        failure_phase, failure_code = error.failure_phase, error.failure_code
        failure_page_ordinal = page_number if failure_phase is not None else None
        requested_pages_per_target = pages_per_target if failure_phase is not None else None
        try:
            validate_kis_paper_minute_failure_diagnostic(
                reason=reason,
                phase=failure_phase,
                code=failure_code,
                page_ordinal=failure_page_ordinal,
                requested_pages_per_target=requested_pages_per_target,
            )
        except ValueError:
            failure_phase = failure_code = failure_page_ordinal = None
            requested_pages_per_target = None
        conflict_origin: _ConflictOrigin | None = (
            "candidate_batch" if isinstance(error, _CandidateBatchDuplicateConflict) else None
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
                failure_phase=failure_phase,
                failure_code=failure_code,
                failure_page_ordinal=failure_page_ordinal,
                requested_pages_per_target=requested_pages_per_target,
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
            failure_phase=failure_phase,
            failure_code=failure_code,
            failure_page_ordinal=failure_page_ordinal,
            requested_pages_per_target=requested_pages_per_target,
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


def _validate_dated_qqq_state(
    index: Mapping[str, object],
    *,
    session_date: date,
    observed_at: datetime,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> None:
    initial_key = kis_paper_qqq_dated_session_initial_key(session_date, observed_at=observed_at)
    floor_key = f"{session_date:%Y%m%d}000000"
    state = _index_target(index=index, target=KisPaperPrivateIntradayTarget(*target))
    cursor = KisPaperPrivateIntradayCursor.from_document(state["next_cursor"])
    if cursor is None or not floor_key <= cursor.keyb <= initial_key:
        raise ValueError("QQQ dated-session cursor is invalid")
    _validate_dated_cursor_time(cursor)
    expected = KisPaperPrivateIntradayCursor("1", initial_key).as_document()
    for chunk in state["chunks"]:
        if chunk["collection_scope"] != "historical" or chunk["input_cursor"] != expected:
            raise ValueError("QQQ dated-session custody is invalid")
        following = KisPaperPrivateIntradayCursor.from_document(chunk["output_cursor"])
        if following is None or not floor_key <= following.keyb < expected["keyb"]:
            raise ValueError("QQQ dated-session custody is invalid")
        _validate_dated_cursor_time(following)
        expected = following.as_document()
    if cursor.as_document() != expected:
        raise ValueError("QQQ dated-session custody is invalid")


def _validate_dated_cursor_time(cursor: KisPaperPrivateIntradayCursor) -> None:
    try:
        parsed = datetime.strptime(cursor.keyb, "%Y%m%d%H%M%S")
    except ValueError as error:
        raise ValueError("QQQ dated-session cursor is invalid") from error
    if parsed.second != 0:
        raise ValueError("QQQ dated-session cursor is invalid")


def _validate_dated_qqq_page(
    *,
    page: KisPaperMinutePage,
    cursor: KisPaperPrivateIntradayCursor | None,
    retained_rows: Mapping[str, KisPaperMinuteRawBar],
    session_date: date,
    target: tuple[str, str] = ("QQQ", "NAS"),
) -> None:
    stamps = [_exchange_stamp(row).replace("T", "") for row in page.bars]
    korea = [_korea_stamp(row) for row in page.bars]
    if (
        cursor is None
        or (page.query.symbol, page.query.exchange) != target
        or page.query.continuation_key != cursor.keyb
        or page.query.continuation_next != cursor.next_value
        or page.query.include_previous_day is not True
        or not 1 <= len(stamps) <= 120
        or len(set(stamps)) != len(stamps)
        or len(set(korea)) != len(korea)
        or any(stamp[:8] != f"{session_date:%Y%m%d}" or stamp[-2:] != "00" for stamp in stamps)
        or max(stamps) > cursor.keyb
        or min(stamps) <= f"{session_date:%Y%m%d}000000"
        or (retained_rows and max(korea) >= min(retained_rows))
    ):
        raise KisPaperMarketDataError("minute_response_invalid")


def _validate_explicit_qqq_head_page(
    *,
    page: KisPaperMinutePage,
    cursor: KisPaperPrivateIntradayCursor | None,
    retained_rows: Mapping[str, KisPaperMinuteRawBar],
) -> None:
    if (page.query.symbol, page.query.exchange) != ("QQQ", "NAS"):
        raise KisPaperMarketDataError("minute_response_invalid")
    exchange_stamps = [_exchange_stamp(row) for row in page.bars]
    korea_stamps = [_korea_stamp(row) for row in page.bars]
    if len(set(exchange_stamps)) != len(page.bars) or len(set(korea_stamps)) != len(page.bars):
        raise KisPaperMarketDataError("minute_response_invalid")
    if len({row.exchange_date for row in page.bars}) != 1:
        raise KisPaperMarketDataError("minute_response_invalid")
    if cursor is not None:
        requested_stamp = f"{cursor.keyb[:8]}T{cursor.keyb[8:]}"
        if (
            page.bars[0].exchange_date != next(iter(retained_rows.values())).exchange_date
            or max(exchange_stamps) > requested_stamp
            or max(korea_stamps) >= min(retained_rows)
        ):
            raise KisPaperMarketDataError("minute_cursor_stalled")


def _validate_explicit_head_page(
    *,
    page: KisPaperMinutePage,
    target: KisPaperPrivateIntradayTarget,
    cursor: KisPaperPrivateIntradayCursor | None,
    retained_rows: Mapping[str, KisPaperMinuteRawBar],
) -> None:
    if (target.symbol, target.exchange) not in KIS_PAPER_PRIVATE_INTRADAY_TARGETS or (
        page.query.symbol,
        page.query.exchange,
    ) != (target.symbol, target.exchange):
        raise KisPaperMarketDataError(
            "minute_response_invalid",
            failure_phase="head_contract",
            failure_code="response_identity_mismatch",
        )
    exchange_stamps = [_exchange_stamp(row) for row in page.bars]
    korea_stamps = [_korea_stamp(row) for row in page.bars]
    failure_code = None
    if len(set(exchange_stamps)) != len(page.bars):
        failure_code = "duplicate_exchange_timestamp"
    elif len(set(korea_stamps)) != len(page.bars):
        failure_code = "duplicate_korea_timestamp"
    elif len({row.exchange_date for row in page.bars}) != 1:
        failure_code = "mixed_exchange_dates"
    elif not any(
        exchange_stamps == sorted(exchange_stamps, reverse=reverse)
        and korea_stamps == sorted(korea_stamps, reverse=reverse)
        for reverse in (False, True)
    ):
        failure_code = "timestamp_order_invalid"
    if failure_code is not None:
        raise KisPaperMarketDataError(
            "minute_response_invalid", failure_phase="head_contract", failure_code=failure_code
        )
    if cursor is not None:
        requested_stamp = f"{cursor.keyb[:8]}T{cursor.keyb[8:]}"
        if (
            not retained_rows
            or page.bars[0].exchange_date != cursor.keyb[:8]
            or any(row.exchange_date != cursor.keyb[:8] for row in retained_rows.values())
            or max(exchange_stamps) > requested_stamp
            or max(exchange_stamps) >= min(_exchange_stamp(row) for row in retained_rows.values())
            or max(korea_stamps) >= min(_korea_stamp(row) for row in retained_rows.values())
        ):
            raise KisPaperMarketDataError("minute_cursor_stalled")


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
            "completed_bar_rule": ("source_timestamp_plus_1m_at_or_before_collection_minute"),
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


def _normalize_private_intraday_targets(
    targets: object,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(targets, tuple) or not targets:
        raise ValueError("private intraday target scope is invalid")
    normalized: list[tuple[str, str]] = []
    target_keys: set[str] = set()
    for item in targets:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
        ):
            raise ValueError("private intraday target scope is invalid")
        target = KisPaperPrivateIntradayTarget(symbol=item[0], exchange=item[1])
        if target.target_key in target_keys:
            raise ValueError("private intraday target scope is invalid")
        target_keys.add(target.target_key)
        normalized.append((target.symbol, target.exchange))
    return tuple(normalized)


def _validate_iwm_current_head_cache_root(
    *,
    cache_root: Path,
    repo_root: Path,
    market_data_root: Path,
    protected_cache_roots: tuple[Path, ...],
) -> Path:
    supplied = Path(cache_root)
    supplied_market_data_root = Path(market_data_root)
    if (
        not supplied.is_absolute()
        or supplied.is_symlink()
        or not supplied_market_data_root.is_absolute()
        or supplied_market_data_root.is_symlink()
    ):
        raise ValueError("IWM current-head cache root is invalid")
    root = supplied.resolve(strict=False)
    market_data = supplied_market_data_root.resolve(strict=False)
    repository = Path(repo_root).resolve(strict=False)
    if (
        root.is_relative_to(repository)
        or root == market_data
        or not root.is_relative_to(market_data)
    ):
        raise ValueError("IWM current-head cache root is invalid")
    for protected_root in protected_cache_roots:
        protected = Path(protected_root).resolve(strict=False)
        if root == protected or root.is_relative_to(protected) or protected.is_relative_to(root):
            raise ValueError("IWM current-head cache root is invalid")
    return root


def _read_or_create_index(
    root: Path,
    *,
    hydrate_source_exhaustion: bool,
    expected_targets: tuple[tuple[str, str], ...] = KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
    initial_cursor: KisPaperPrivateIntradayCursor | None = None,
) -> dict[str, object]:
    expected_targets = _normalize_private_intraday_targets(expected_targets)
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
                    "next_cursor": initial_cursor.as_document() if initial_cursor else None,
                    "last_reason": None,
                    "last_conflict_origin": None,
                    "last_observed_at_utc": None,
                    "chunks": [],
                }
                for target in expected_targets
            ],
        }
        _write_index(root=root, index=index, expected_targets=expected_targets)
        return index
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private intraday index is invalid") from error
    if not isinstance(loaded, dict):
        raise ValueError("private intraday index is invalid")
    _validate_index(loaded, expected_targets=expected_targets)
    if hydrate_source_exhaustion and _hydrate_source_exhaustion_state(loaded):
        _write_index(root=root, index=loaded, expected_targets=expected_targets)
    return loaded


def _validate_index(
    index: Mapping[str, object],
    *,
    expected_targets: tuple[tuple[str, str], ...] = KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
) -> None:
    try:
        _validate_shared_index_metadata(
            index,
            expected_targets=_normalize_private_intraday_targets(expected_targets),
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
    return resume_cursor and collected.status == "collected" and collected.output_cursor is None


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
        retained_chunks = [chunk for chunk in chunks if not _is_ignored_collection_chunk(chunk)]
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
        and chunk.get("outcome") == "committed"
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
        recovered_chunk["manifest_path"] = str(manifest_path.relative_to(root)).replace("\\", "/")
        recovered_chunk["manifest_hash"] = manifest_hash
        _validate_chunk(chunk=recovered_chunk, target=target)
        chunks.append(recovered_chunk)
        if recovered_chunk.get("collection_scope") == "historical":
            output_cursor = KisPaperPrivateIntradayCursor.from_document(
                recovered_chunk["output_cursor"]
            )
            state["next_cursor"] = (
                output_cursor.as_document() if output_cursor is not None else None
            )
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


def _write_index(
    *,
    root: Path,
    index: Mapping[str, object],
    expected_targets: tuple[tuple[str, str], ...] = KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
) -> None:
    _validate_index(index, expected_targets=expected_targets)
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

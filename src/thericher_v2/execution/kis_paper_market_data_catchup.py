"""Finite, rate-gated private KIS Paper daily-history catch-up orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_private_daily_backfill import KisPaperPrivateDailyBackfillRun

KIS_PAPER_MARKET_DATA_CATCHUP_MAX_CHUNKS = 48
KIS_PAPER_MARKET_DATA_CATCHUP_MAX_RUNTIME = timedelta(hours=6)
CatchupStatus = Literal[
    "drained",
    "budget_exhausted",
    "rate_limited_cooldown",
    "storage_floor",
    "recovery_required",
    "busy",
]


@dataclass(frozen=True)
class KisPaperMarketDataCatchupResult:
    """Sanitized bounded outcome for one data-only catch-up worker."""

    status: CatchupStatus
    chunk_attempt_count: int
    retained_chunk_count: int
    completed_target_count: int
    last_reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.chunk_attempt_count < 0 or self.retained_chunk_count < 0:
            raise ValueError("market-data catch-up counts are invalid")
        if self.completed_target_count < 0:
            raise ValueError("market-data catch-up counts are invalid")


def run_kis_paper_market_data_catchup(
    *,
    run_daily_chunk: Callable[[], KisPaperPrivateDailyBackfillRun],
    max_chunks: int = KIS_PAPER_MARKET_DATA_CATCHUP_MAX_CHUNKS,
    max_runtime: timedelta = KIS_PAPER_MARKET_DATA_CATCHUP_MAX_RUNTIME,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperMarketDataCatchupResult:
    """Drain finite ready daily cursors without interpreting market values."""

    if type(max_chunks) is not int or max_chunks <= 0:
        raise ValueError("market-data catch-up max chunks must be positive")
    if not isinstance(max_runtime, timedelta) or max_runtime <= timedelta(0):
        raise ValueError("market-data catch-up max runtime must be positive")
    started_at = require_utc(clock(), "clock")
    attempted = 0
    retained = 0
    completed = 0

    while attempted < max_chunks:
        if require_utc(clock(), "clock") - started_at >= max_runtime:
            return _result(
                status="budget_exhausted",
                attempted=attempted,
                retained=retained,
                completed=completed,
                reason="runtime_budget_exhausted",
            )
        result = run_daily_chunk()
        if result.status in {"collected", "recovered", "complete"}:
            attempted += 1
            retained += int(result.manifest_path is not None)
            completed += int(result.status == "complete")
            continue
        if result.status == "no_ready_target":
            return _result(
                status="drained",
                attempted=attempted,
                retained=retained,
                completed=completed,
            )
        if result.status == "storage_floor_would_be_crossed":
            return _result(
                status="storage_floor",
                attempted=attempted,
                retained=retained,
                completed=completed,
                reason=result.reason,
            )
        if result.status == "busy":
            return _result(
                status="busy",
                attempted=attempted,
                retained=retained,
                completed=completed,
                reason=result.reason,
            )
        if result.status == "deferred":
            return _result(
                status=(
                    "rate_limited_cooldown"
                    if result.reason in {"rate_limited", "shared_retry_not_before"}
                    else "recovery_required"
                ),
                attempted=attempted,
                retained=retained,
                completed=completed,
                reason=result.reason,
            )
        raise ValueError("market-data catch-up received an invalid daily result")

    return _result(
        status="budget_exhausted",
        attempted=attempted,
        retained=retained,
        completed=completed,
        reason="chunk_budget_exhausted",
    )


def _result(
    *,
    status: CatchupStatus,
    attempted: int,
    retained: int,
    completed: int,
    reason: str | None = None,
) -> KisPaperMarketDataCatchupResult:
    return KisPaperMarketDataCatchupResult(
        status=status,
        chunk_attempt_count=attempted,
        retained_chunk_count=retained,
        completed_target_count=completed,
        last_reason=reason,
    )

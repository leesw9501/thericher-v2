from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from thericher_v2.execution.kis_paper_market_data_catchup import (
    run_kis_paper_market_data_catchup,
)
from thericher_v2.execution.kis_private_daily_backfill import KisPaperPrivateDailyBackfillRun


def test_catchup_drains_ready_daily_targets_without_an_unbounded_loop() -> None:
    results = iter(
        (
            _daily_result("collected", manifest=True),
            _daily_result("complete", manifest=True),
            _daily_result("no_ready_target"),
        )
    )

    result = run_kis_paper_market_data_catchup(
        run_daily_chunk=lambda: next(results),
        max_chunks=4,
        max_runtime=timedelta(minutes=5),
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    assert result.status == "drained"
    assert result.chunk_attempt_count == 2
    assert result.retained_chunk_count == 2
    assert result.completed_target_count == 1
    assert result.last_reason is None


def test_catchup_stops_at_the_shared_rate_cooldown_without_another_chunk() -> None:
    calls = 0

    def run_daily_chunk() -> KisPaperPrivateDailyBackfillRun:
        nonlocal calls
        calls += 1
        return _daily_result("deferred", reason="shared_retry_not_before")

    result = run_kis_paper_market_data_catchup(
        run_daily_chunk=run_daily_chunk,
        max_chunks=4,
        max_runtime=timedelta(minutes=5),
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    assert result.status == "rate_limited_cooldown"
    assert result.chunk_attempt_count == 0
    assert result.last_reason == "shared_retry_not_before"
    assert calls == 1


def test_catchup_has_a_finite_chunk_budget() -> None:
    result = run_kis_paper_market_data_catchup(
        run_daily_chunk=lambda: _daily_result("collected", manifest=True),
        max_chunks=2,
        max_runtime=timedelta(minutes=5),
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    assert result.status == "budget_exhausted"
    assert result.chunk_attempt_count == 2
    assert result.last_reason == "chunk_budget_exhausted"


def _daily_result(
    status: str,
    *,
    manifest: bool = False,
    reason: str | None = None,
) -> KisPaperPrivateDailyBackfillRun:
    return KisPaperPrivateDailyBackfillRun(
        status=status,  # type: ignore[arg-type]
        target_key="QQQ/NAS/MODP=0" if status != "no_ready_target" else None,
        manifest_path=Path("D:/market_data/manifest.json") if manifest else None,
        manifest_hash="sha256:test" if manifest else None,
        row_count=1 if manifest else 0,
        reason=reason,
    )

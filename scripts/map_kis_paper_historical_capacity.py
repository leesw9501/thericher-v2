"""Run one independently durable KIS paper historical-capacity map track."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.execution.kis_historical_capacity_map import (
    KIS_PAPER_DAILY_CAPACITY_MAP_ARTIFACT_ROOT,
    KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    KIS_PAPER_DAILY_CAPACITY_MAP_OBJECTIVE_ID,
    KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT,
    KIS_PAPER_MINUTE_CAPACITY_MAP_ARTIFACT_ROOT,
    KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    KIS_PAPER_MINUTE_CAPACITY_MAP_OBJECTIVE_ID,
    KisPaperDailyCapacityMapResult,
    KisPaperMinuteCapacityMapResult,
    run_bounded_kis_paper_daily_capacity_map,
    run_bounded_kis_paper_minute_capacity_map,
    sanitize_kis_paper_historical_capacity_map_failure_reason,
    write_kis_paper_daily_capacity_map_summary,
    write_kis_paper_minute_capacity_map_summary,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_minute_qualification import (
    external_one_shot_attempt_is_reserved,
    mark_external_one_shot_network_started,
    mark_external_one_shot_summary_written,
    reserve_external_one_shot_attempt,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_Track = Literal["daily", "minute"]


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPO_ROOT / ".env",
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", choices=("daily", "minute"), required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    track: _Track = args.track

    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return

    objective_id = _objective_id(track)
    try:
        if external_one_shot_attempt_is_reserved(
            control_root=KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=objective_id,
        ):
            _print_already_reserved(track)
            return
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "reservation_marker_invalid"}))
        return

    try:
        config = load_kis_paper_market_data_config(dotenv_path)
    except KisPaperMarketDataError as error:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": sanitize_kis_paper_historical_capacity_map_failure_reason(error),
                }
            )
        )
        return

    reserved_at = clock()
    try:
        reserve_external_one_shot_attempt(
            control_root=KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=objective_id,
            observed_at=reserved_at,
            raw_market_data_retained=False,
        )
        network_started_at = clock()
        mark_external_one_shot_network_started(
            control_root=KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=objective_id,
            observed_at=network_started_at,
        )
    except ValueError:
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return

    client = _client_for_track(track, config)
    try:
        result = _run_track(track, client, observed_at=network_started_at)
    except (KisPaperMarketDataError, ValueError) as error:
        result = _failed_track_result(
            track,
            observed_at=network_started_at,
            call_counts=client.call_counts,
            error=error,
        )
    run_id = reserved_at.strftime("%Y%m%dT%H%M%SZ")
    try:
        summary_path, summary_hash = _write_track_summary(
            track,
            result=result,
            run_id=run_id,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "summary_write_failed"}))
        return
    try:
        mark_external_one_shot_summary_written(
            control_root=KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=objective_id,
            observed_at=result.observed_at,
            summary_hash=summary_hash,
            result_status=result.status,
        )
    except ValueError:
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return
    print(
        json.dumps(
            {
                "status": result.status,
                "summary_path": str(summary_path),
                "summary_hash": summary_hash,
                "track": track,
            },
            sort_keys=True,
        )
    )


def _client_for_track(
    track: _Track,
    config: KisPaperMarketDataConfig,
) -> KisPaperMarketDataClient:
    if track == "daily":
        return KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(),
            max_daily_page_attempts=KIS_PAPER_DAILY_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
        )
    return KisPaperMarketDataClient(
        config=config,
        transport=UrllibKisPaperMarketDataTransport(),
        max_minute_page_attempts=KIS_PAPER_MINUTE_CAPACITY_MAP_MAX_PAGE_ATTEMPTS,
    )


def _run_track(
    track: _Track,
    client: KisPaperMarketDataClient,
    *,
    observed_at: datetime,
) -> KisPaperDailyCapacityMapResult | KisPaperMinuteCapacityMapResult:
    if track == "daily":
        return run_bounded_kis_paper_daily_capacity_map(client, observed_at=observed_at)
    return run_bounded_kis_paper_minute_capacity_map(client, observed_at=observed_at)


def _failed_track_result(
    track: _Track,
    *,
    observed_at: datetime,
    call_counts: KisPaperMarketDataCallCounts,
    error: BaseException,
) -> KisPaperDailyCapacityMapResult | KisPaperMinuteCapacityMapResult:
    reason = sanitize_kis_paper_historical_capacity_map_failure_reason(error)
    if track == "daily":
        return KisPaperDailyCapacityMapResult(
            observed_at=observed_at,
            call_counts=call_counts,
            pages=(),
            status="rejected",
            reason=reason,
        )
    return KisPaperMinuteCapacityMapResult(
        observed_at=observed_at,
        call_counts=call_counts,
        pages=(),
        status="rejected",
        reason=reason,
    )


def _write_track_summary(
    track: _Track,
    *,
    result: KisPaperDailyCapacityMapResult | KisPaperMinuteCapacityMapResult,
    run_id: str,
) -> tuple[Path, str]:
    if track == "daily":
        if not isinstance(result, KisPaperDailyCapacityMapResult):
            raise ValueError("daily capacity result is invalid")
        return write_kis_paper_daily_capacity_map_summary(
            result=result,
            artifact_root=KIS_PAPER_DAILY_CAPACITY_MAP_ARTIFACT_ROOT,
            run_id=run_id,
            repo_root=_REPO_ROOT,
        )
    if not isinstance(result, KisPaperMinuteCapacityMapResult):
        raise ValueError("minute capacity result is invalid")
    return write_kis_paper_minute_capacity_map_summary(
        result=result,
        artifact_root=KIS_PAPER_MINUTE_CAPACITY_MAP_ARTIFACT_ROOT,
        run_id=run_id,
        repo_root=_REPO_ROOT,
    )


def _objective_id(track: _Track) -> str:
    return (
        KIS_PAPER_DAILY_CAPACITY_MAP_OBJECTIVE_ID
        if track == "daily"
        else KIS_PAPER_MINUTE_CAPACITY_MAP_OBJECTIVE_ID
    )


def _print_already_reserved(track: _Track) -> None:
    print(
        json.dumps(
            {
                "status": "not_executed",
                "reason": "capacity_map_attempt_already_reserved",
                "track": track,
            }
        )
    )


if __name__ == "__main__":
    main()

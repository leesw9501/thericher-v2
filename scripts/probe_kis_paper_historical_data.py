"""Run the operator-approved bounded KIS paper historical-data capability probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution.kis_historical_probe import (
    KIS_PAPER_HISTORICAL_PROBE_ARTIFACT_ROOT,
    KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT,
    KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID,
    KisPaperHistoricalProbeError,
    KisPaperHistoricalProbeEvidence,
    KisPaperHistoricalProbeFailure,
    run_bounded_kis_paper_historical_probe,
    sanitize_kis_paper_historical_probe_failure_reason,
    write_kis_paper_historical_probe_summary,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataClient,
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


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    dotenv_path: Path = _REPO_ROOT / ".env",
) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return

    observed_at = clock()
    try:
        attempt_reserved = external_one_shot_attempt_is_reserved(
            control_root=KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID,
        )
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "reservation_marker_invalid"}))
        return
    if attempt_reserved:
        print(
            json.dumps(
                {"status": "not_executed", "reason": "historical_attempt_already_reserved"}
            )
        )
        return

    try:
        config = load_kis_paper_market_data_config(dotenv_path)
    except KisPaperMarketDataError as error:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": sanitize_kis_paper_historical_probe_failure_reason(error),
                }
            )
        )
        return

    client: KisPaperMarketDataClient | None = None
    attempt_created = False
    result: KisPaperHistoricalProbeEvidence | KisPaperHistoricalProbeFailure
    try:
        reserved_at = clock()
        reserve_external_one_shot_attempt(
            control_root=KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID,
            observed_at=reserved_at,
        )
        attempt_created = True
        network_started_at = clock()
        mark_external_one_shot_network_started(
            control_root=KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID,
            observed_at=network_started_at,
        )
        client = KisPaperMarketDataClient(
            config=config,
            transport=UrllibKisPaperMarketDataTransport(),
        )
        result = run_bounded_kis_paper_historical_probe(
            client,
            observed_at=network_started_at,
            clock=clock,
        )
    except (KisPaperHistoricalProbeError, KisPaperMarketDataError, ValueError) as error:
        if not attempt_created:
            print(
                json.dumps(
                    {
                        "status": "not_executed",
                        "reason": sanitize_kis_paper_historical_probe_failure_reason(error),
                    }
                )
            )
            return
        result = KisPaperHistoricalProbeFailure(
            observed_at=clock(),
            call_counts=(
                client.call_counts
                if client is not None
                else KisPaperMarketDataCallCounts(0, 0, 0)
            ),
            reason=sanitize_kis_paper_historical_probe_failure_reason(error),
        )

    run_id = observed_at.strftime("%Y%m%dT%H%M%SZ")
    try:
        summary_path, summary_hash = write_kis_paper_historical_probe_summary(
            result=result,
            artifact_root=KIS_PAPER_HISTORICAL_PROBE_ARTIFACT_ROOT,
            run_id=run_id,
            repo_root=_REPO_ROOT,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "summary_write_failed"}))
        return
    try:
        mark_external_one_shot_summary_written(
            control_root=KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID,
            observed_at=result.observed_at,
            summary_hash=summary_hash,
            result_status=(
                "rejected" if isinstance(result, KisPaperHistoricalProbeFailure) else "observed"
            ),
        )
    except ValueError:
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return
    print(
        json.dumps(
            {
                "status": (
                    "rejected" if isinstance(result, KisPaperHistoricalProbeFailure) else "observed"
                ),
                "summary_path": str(summary_path),
                "summary_hash": summary_hash,
            },
            sort_keys=True,
        )
    )
if __name__ == "__main__":
    main()

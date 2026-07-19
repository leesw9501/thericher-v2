"""Run the one bounded KIS paper raw-minute qualification probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinuteCallCounts,
    KisPaperMinuteClient,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_minute_qualification import (
    KIS_PAPER_MINUTE_QUALIFICATION_ARTIFACT_ROOT,
    KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT,
    KisPaperMinuteQualificationEvidence,
    KisPaperMinuteQualificationFailure,
    is_kis_paper_minute_qualification_window,
    kis_paper_minute_qualification_attempt_is_reserved,
    mark_kis_paper_minute_qualification_network_started,
    mark_kis_paper_minute_qualification_summary_written,
    reserve_kis_paper_minute_qualification_attempt,
    run_bounded_kis_paper_minute_qualification,
    sanitize_kis_paper_minute_failure_reason,
    write_kis_paper_minute_qualification_summary,
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
    parser.add_argument("--confirm-no-exception", action="store_true")
    args = parser.parse_args(argv)

    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return

    observed_at = clock()
    if not is_kis_paper_minute_qualification_window(observed_at):
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": "regular_session_qualification_window_closed",
                    "observed_at_utc": observed_at.isoformat().replace("+00:00", "Z"),
                }
            )
        )
        return
    if not args.confirm_no_exception:
        print(
            json.dumps(
                {"status": "not_executed", "reason": "session_exception_confirmation_required"}
            )
        )
        return

    try:
        attempt_reserved = kis_paper_minute_qualification_attempt_is_reserved(
            control_root=KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
        )
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "reservation_marker_invalid"}))
        return
    if attempt_reserved:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": "qualification_attempt_already_reserved",
                }
            )
        )
        return

    client: KisPaperMinuteClient | None = None
    result: KisPaperMinuteQualificationEvidence | KisPaperMinuteQualificationFailure
    try:
        config = load_kis_paper_market_data_config(dotenv_path)
        reserved_at = clock()
        if not is_kis_paper_minute_qualification_window(reserved_at):
            print(
                json.dumps(
                    {
                        "status": "not_executed",
                        "reason": "regular_session_qualification_window_closed",
                        "observed_at_utc": reserved_at.isoformat().replace("+00:00", "Z"),
                    }
                )
            )
            return
        reserve_kis_paper_minute_qualification_attempt(
            control_root=KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            observed_at=reserved_at,
        )
        network_started_at = clock()
        if not is_kis_paper_minute_qualification_window(network_started_at):
            result = KisPaperMinuteQualificationFailure(
                observed_at=network_started_at,
                call_counts=KisPaperMinuteCallCounts(0, 0),
                reason="window_recheck_closed",
            )
        else:
            mark_kis_paper_minute_qualification_network_started(
                control_root=KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT,
                repo_root=_REPO_ROOT,
                observed_at=network_started_at,
            )
            client = KisPaperMinuteClient(
                config=config,
                transport=UrllibKisPaperMarketDataTransport(),
            )
            result = run_bounded_kis_paper_minute_qualification(
                client,
                clock=clock,
                observed_at_start=network_started_at,
            )
    except (KisPaperMarketDataError, ValueError) as error:
        if str(error) == "qualification_attempt_already_reserved":
            print(json.dumps({"status": "not_executed", "reason": str(error)}))
            return
        result = KisPaperMinuteQualificationFailure(
            observed_at=observed_at,
            call_counts=(
                client.call_counts if client is not None else KisPaperMinuteCallCounts(0, 0)
            ),
            reason=sanitize_kis_paper_minute_failure_reason(error),
        )

    run_id = observed_at.strftime("%Y%m%dT%H%M%SZ")
    try:
        summary_path, summary_hash = write_kis_paper_minute_qualification_summary(
            result=result,
            artifact_root=KIS_PAPER_MINUTE_QUALIFICATION_ARTIFACT_ROOT,
            run_id=run_id,
            repo_root=_REPO_ROOT,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "summary_write_failed"}))
        return
    try:
        mark_kis_paper_minute_qualification_summary_written(
            control_root=KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            observed_at=(
                result.observed_at_end
                if isinstance(result, KisPaperMinuteQualificationEvidence)
                else result.observed_at
            ),
            summary_hash=summary_hash,
            result_status=(
                "observed"
                if isinstance(result, KisPaperMinuteQualificationEvidence)
                else "rejected"
            ),
        )
    except ValueError:
        # The durable network_started state and written summary still prevent a retry.
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return
    print(
        json.dumps(
            {
                "summary_path": str(summary_path),
                "summary_hash": summary_hash,
                "status": "observed"
                if isinstance(result, KisPaperMinuteQualificationEvidence)
                else "rejected",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

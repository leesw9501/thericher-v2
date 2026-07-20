"""Prepare one separately bounded KIS paper raw-minute observation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinuteCallCounts,
    KisPaperMinuteClient,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_minute_qualification import (
    external_one_shot_attempt_is_reserved,
    mark_external_one_shot_network_started,
    mark_external_one_shot_summary_written,
    reserve_external_one_shot_attempt,
)
from thericher_v2.execution.kis_raw_minute_observation import (
    KIS_PAPER_RAW_MINUTE_OBSERVATION_ARTIFACT_ROOT,
    KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT,
    KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID,
    KisPaperRawMinuteObservation,
    KisPaperRawMinuteObservationError,
    KisPaperRawMinuteObservationFailure,
    is_kis_paper_raw_minute_observation_window,
    run_bounded_kis_paper_raw_minute_observation,
    sanitize_kis_paper_raw_minute_failure_reason,
    write_kis_paper_raw_minute_observation_summary,
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
    parser.add_argument("--confirm-regular-nasdaq-session", action="store_true")
    parser.add_argument("--session-date", type=_session_date)
    args = parser.parse_args(argv)

    if not args.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return
    if args.session_date is None:
        print(json.dumps({"status": "not_executed", "reason": "session_date_required"}))
        return

    observed_at = clock()
    if not is_kis_paper_raw_minute_observation_window(
        observed_at,
        session_date=args.session_date,
    ):
        _print_window_closed(observed_at, session_date=args.session_date)
        return
    if not args.confirm_regular_nasdaq_session:
        print(
            json.dumps(
                {
                    "status": "not_executed",
                    "reason": "regular_nasdaq_session_confirmation_required",
                }
            )
        )
        return

    try:
        if external_one_shot_attempt_is_reserved(
            control_root=KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID,
        ):
            _print_already_reserved()
            return
    except ValueError:
        print(json.dumps({"status": "not_executed", "reason": "reservation_marker_invalid"}))
        return

    try:
        # Configuration preflight has no network side effect and consumes no reservation.
        config = load_kis_paper_market_data_config(dotenv_path)
    except (KisPaperMarketDataError, ValueError):
        print(json.dumps({"status": "not_executed", "reason": "configuration_preflight_failed"}))
        return

    reserved_at = clock()
    if not is_kis_paper_raw_minute_observation_window(
        reserved_at,
        session_date=args.session_date,
    ):
        _print_window_closed(reserved_at, session_date=args.session_date)
        return
    try:
        if external_one_shot_attempt_is_reserved(
            control_root=KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID,
        ):
            _print_already_reserved()
            return
        reserve_external_one_shot_attempt(
            control_root=KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID,
            observed_at=reserved_at,
        )
    except ValueError as error:
        if str(error) == "qualification_attempt_already_reserved":
            _print_already_reserved()
            return
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return

    network_started_at = clock()
    failure_observed_at = network_started_at
    if not is_kis_paper_raw_minute_observation_window(
        network_started_at,
        session_date=args.session_date,
    ):
        result: KisPaperRawMinuteObservation | KisPaperRawMinuteObservationFailure = (
            KisPaperRawMinuteObservationFailure(
                observed_at=network_started_at,
                call_counts=KisPaperMinuteCallCounts(0, 0),
                reason="observation_window_closed",
            )
        )
    else:
        try:
            mark_external_one_shot_network_started(
                control_root=KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT,
                repo_root=_REPO_ROOT,
                objective_id=KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID,
                observed_at=network_started_at,
            )
        except ValueError:
            print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
            return

        client: KisPaperMinuteClient | None = None
        try:
            client = KisPaperMinuteClient(
                config=config,
                transport=UrllibKisPaperMarketDataTransport(),
            )
            result = run_bounded_kis_paper_raw_minute_observation(
                client,
                session_date=args.session_date,
                clock=clock,
                observed_at_start=network_started_at,
            )
        except (KisPaperMarketDataError, KisPaperRawMinuteObservationError, ValueError) as error:
            result = KisPaperRawMinuteObservationFailure(
                observed_at=failure_observed_at,
                call_counts=(
                    client.call_counts if client is not None else KisPaperMinuteCallCounts(0, 0)
                ),
                reason=sanitize_kis_paper_raw_minute_failure_reason(error),
            )

    run_id = observed_at.strftime("%Y%m%dT%H%M%SZ")
    try:
        summary_path, summary_hash = write_kis_paper_raw_minute_observation_summary(
            result=result,
            artifact_root=KIS_PAPER_RAW_MINUTE_OBSERVATION_ARTIFACT_ROOT,
            run_id=run_id,
            repo_root=_REPO_ROOT,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "indeterminate", "reason": "summary_write_failed"}))
        return
    try:
        mark_external_one_shot_summary_written(
            control_root=KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT,
            repo_root=_REPO_ROOT,
            objective_id=KIS_PAPER_RAW_MINUTE_OBSERVATION_OBJECTIVE_ID,
            observed_at=(
                result.observed_at_end
                if isinstance(result, KisPaperRawMinuteObservation)
                else result.observed_at
            ),
            summary_hash=summary_hash,
            result_status=(
                "observed" if isinstance(result, KisPaperRawMinuteObservation) else "rejected"
            ),
        )
    except ValueError:
        print(json.dumps({"status": "indeterminate", "reason": "attempt_state_unresolved"}))
        return
    print(
        json.dumps(
            {
                "summary_path": str(summary_path),
                "summary_hash": summary_hash,
                "status": (
                    "observed" if isinstance(result, KisPaperRawMinuteObservation) else "rejected"
                ),
            },
            sort_keys=True,
        )
    )


def _session_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("session date must be YYYY-MM-DD") from error


def _print_window_closed(observed_at: datetime, *, session_date: date) -> None:
    print(
        json.dumps(
            {
                "status": "not_executed",
                "reason": "regular_session_window_closed",
                "session_date": session_date.isoformat(),
                "observed_at_utc": observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
    )


def _print_already_reserved() -> None:
    print(
        json.dumps(
            {
                "status": "not_executed",
                "reason": "observation_attempt_already_reserved",
            }
        )
    )


if __name__ == "__main__":
    main()

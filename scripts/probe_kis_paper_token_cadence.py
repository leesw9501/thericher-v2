"""Run one bounded KIS Paper token-only cadence capability probe."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_token_cadence_probe import (
    KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS,
    KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
    KisPaperTokenCadenceProbeAttempt,
    run_kis_paper_token_cadence_probe,
    write_kis_paper_token_cadence_probe,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic_clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS,
    )
    arguments = parser.parse_args(argv)
    if not 30.0 <= arguments.interval_seconds <= 300.0:
        parser.error("--interval-seconds must be between 30 and 300")
    if not arguments.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0

    control_root = (
        KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )
    try:
        current_token_gate = KisPaperMarketDataTokenStartGate(control_root=control_root)
        if not current_token_gate.token_request_is_due():
            print(
                json.dumps(
                    {
                        "kind": KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
                        "status": "unavailable",
                        "paper_only": True,
                        "reason": "token_request_not_due",
                        "token_value_retained": False,
                    },
                    sort_keys=True,
                )
            )
            return 2
        config = load_kis_paper_market_data_config(_REPO_ROOT / ".env")
        if not current_token_gate.claim_token_request_start():
            print(
                json.dumps(
                    {
                        "kind": KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
                        "status": "unavailable",
                        "paper_only": True,
                        "reason": "token_request_not_due",
                        "token_value_retained": False,
                    },
                    sort_keys=True,
                )
            )
            return 2
        request_starts: list[KisPaperTokenCadenceProbeAttempt] = []

        def record_request_start(started_at: datetime) -> None:
            request_starts.append(
                KisPaperTokenCadenceProbeAttempt(
                    request_started_at=started_at,
                    monotonic_started_seconds=monotonic_clock(),
                )
            )

        request_gate = KisPaperMarketDataRateGate(
            control_root=control_root,
            on_request_started=record_request_start,
        )
        first_transport = UrllibKisPaperMarketDataTransport(request_gate=request_gate)
        second_transport = UrllibKisPaperMarketDataTransport(
            request_gate=request_gate,
            token_start_gate=KisPaperMarketDataTokenStartGate(
                control_root=control_root,
                minimum_request_interval_seconds=arguments.interval_seconds,
            ),
        )
        transports = iter((first_transport, second_transport))

        def authenticate_once() -> KisPaperTokenCadenceProbeAttempt:
            before = len(request_starts)
            transport = next(transports)
            KisPaperMarketDataClient(config=config, transport=transport).ensure_authenticated()
            starts = request_starts[before:]
            if len(starts) != 1:
                raise KisPaperMarketDataError("transport_failure")
            return starts[0]

        outcome = run_kis_paper_token_cadence_probe(
            authenticate_once=authenticate_once,
            requested_interval_seconds=arguments.interval_seconds,
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
        )
        observed_at = clock()
        run = write_kis_paper_token_cadence_probe(
            outcome,
            artifact_root=arguments.artifact_root,
            repo_root=_REPO_ROOT,
            run_label=f"token-cadence-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}",
            observed_at=observed_at,
        )
    except (KisPaperMarketDataError, OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
                    "status": "unavailable",
                    "paper_only": True,
                    "token_value_retained": False,
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {**outcome.safe_payload(), "summary_path": str(run.summary_path)},
            sort_keys=True,
        )
    )
    return 0 if outcome.status == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())

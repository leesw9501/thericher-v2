"""Run one isolated IWM/AMS head-plus-optional-continuation KIS Paper probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from time import monotonic

from thericher_v2.data.kis_paper_iwm_temporal_reach_probe import (
    KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_KIND,
    run_and_write_kis_paper_iwm_temporal_reach_probe,
    validate_kis_paper_iwm_temporal_reach_probe_artifact_root,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataConfig,
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

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(
    argv: Sequence[str] | None = None,
    *,
    config_loader: Callable[[Path], KisPaperMarketDataConfig] = load_kis_paper_market_data_config,
    monotonic_clock: Callable[[], float] = monotonic,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--dotenv-path", type=Path, default=_REPOSITORY_ROOT / ".env")
    args = parser.parse_args(argv)
    if not args.execute:
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_KIND,
                    "status": "not_executed",
                    "reason": "execute_flag_required",
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        artifact_root = validate_kis_paper_iwm_temporal_reach_probe_artifact_root(
            artifact_root=args.artifact_root,
            repo_root=args.repository_root,
        )
        control_root = (
            KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT.parent / KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
        )
        client = KisPaperMarketDataClient(
            config=config_loader(args.dotenv_path),
            transport=UrllibKisPaperMarketDataTransport(
                request_gate=KisPaperMarketDataRateGate(control_root=control_root),
                token_start_gate=KisPaperMarketDataTokenStartGate(control_root=control_root),
            ),
            max_minute_page_attempts=2,
            minute_route="iwm_temporal_reach_probe",
        )
        receipt = run_and_write_kis_paper_iwm_temporal_reach_probe(
            client=client,
            artifact_root=artifact_root,
            repo_root=args.repository_root,
            monotonic_clock=monotonic_clock,
        )
    except (KisPaperMarketDataError, OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_IWM_TEMPORAL_REACH_PROBE_KIND,
                    "status": "input_unavailable",
                    "paper_only": True,
                    "route_class": "kis_paper_market_data",
                    "model_input_eligibility": False,
                },
                sort_keys=True,
            )
        )
        return 2
    payload = receipt.outcome.safe_payload() | {"evidence_sha256": receipt.evidence_sha256}
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

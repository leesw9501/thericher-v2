"""Run one bounded KIS Paper daily-representation capability probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_broad_d1_adjustment_semantics_probe import (
    KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ARTIFACT_ROOT,
    KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ID,
    load_kis_broad_d1_adjustment_semantics_probe_plan,
    run_kis_broad_d1_adjustment_semantics_probe,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperDailyAdjustmentProbeTransport,
    load_kis_paper_market_data_config,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY,
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if _REPOSITORY_ROOT == Path("/app"):
    _DEFAULT_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/daily-nas-broad/v1")
    _DEFAULT_PANEL_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/daily-nas-broad-panel/v1"
    )
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
    _DEFAULT_CONTROL_ROOT = Path("/app/market_data/us_equities/kis_paper_private") / (
        KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )
else:
    _DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily-nas-broad\v1")
    _DEFAULT_PANEL_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1"
    )
    _DEFAULT_ARTIFACT_ROOT = KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ARTIFACT_ROOT
    _DEFAULT_CONTROL_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private") / (
        KIS_PAPER_MARKET_DATA_CONTROL_DIRECTORY
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--materialization-receipt-path", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=_DEFAULT_PANEL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--control-root", type=Path, default=_DEFAULT_CONTROL_ROOT)
    parser.add_argument("--run-label", required=True)
    args = parser.parse_args(argv)
    try:
        plan = load_kis_broad_d1_adjustment_semantics_probe_plan(
            manifest_path=args.manifest_path,
            materialization_receipt_path=args.materialization_receipt_path,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            repo_root=_REPOSITORY_ROOT,
        )
        if not args.execute and plan.witnesses:
            print(
                json.dumps(
                    {
                        "kind": KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ID,
                        "status": "not_executed",
                        "reason": "execute_flag_required",
                    },
                    sort_keys=True,
                )
            )
            return 0
        client = None
        if plan.witnesses:
            config = load_kis_paper_market_data_config(_REPOSITORY_ROOT / ".env")
            request_gate = KisPaperMarketDataRateGate(control_root=args.control_root)
            token_start_gate = KisPaperMarketDataTokenStartGate(control_root=args.control_root)
            client = KisPaperMarketDataClient(
                config=config,
                transport=UrllibKisPaperDailyAdjustmentProbeTransport(
                    daily_symbol_exchanges=plan.daily_symbol_exchanges,
                    request_gate=request_gate,
                    token_start_gate=token_start_gate,
                ),
                max_daily_page_attempts=3 * len(plan.witnesses),
            )
        result = run_kis_broad_d1_adjustment_semantics_probe(
            plan=plan,
            client=client,
            artifact_root=args.artifact_root,
            run_label=args.run_label,
            repo_root=_REPOSITORY_ROOT,
        )
    except (KisPaperMarketDataError, OSError, RuntimeError, ValueError):
        print(
            json.dumps(
                {
                    "kind": KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ID,
                    "status": "input_or_runtime_unavailable",
                },
                sort_keys=True,
            )
        )
        return 20
    print(
        json.dumps(
            {
                "kind": KIS_BROAD_D1_ADJUSTMENT_SEMANTICS_PROBE_ID,
                "status": result.outcome.status,
                "reason": result.outcome.reason,
                "receipt_sha256": result.receipt_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the frozen FirstRate SPY/QQQ 5m technical trend rule offline."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.firstrate_m5_trend_rule_after_cost_control import (
    FIRSTRATE_M5_TREND_RULE_CONTROL_ID,
    run_firstrate_m5_trend_rule_after_cost_control,
    validate_firstrate_m5_trend_rule_after_cost_control,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)
    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

    run = run_firstrate_m5_trend_rule_after_cost_control(
        run_label=run_label,
        market_data_root=Path(args.market_data_root),
        artifact_root=Path(args.artifact_root),
        repo_root=_REPO_ROOT,
    )
    if run.status == "input_unavailable":
        print(
            json.dumps(
                {
                    "control_id": FIRSTRATE_M5_TREND_RULE_CONTROL_ID,
                    "status": run.status,
                    "training_started": False,
                    "gpu_used": False,
                    "paper_or_broker_called": False,
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return
    receipt = validate_firstrate_m5_trend_rule_after_cost_control(
        run_label=run_label,
        market_data_root=Path(args.market_data_root),
        artifact_root=Path(args.artifact_root),
        repo_root=_REPO_ROOT,
    )
    print(
        json.dumps(
            {
                "control_id": FIRSTRATE_M5_TREND_RULE_CONTROL_ID,
                "status": run.status,
                "classification": receipt.classification,
                "source_reattached": receipt.source_reattached,
                "training_started": False,
                "gpu_used": False,
                "paper_or_broker_called": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

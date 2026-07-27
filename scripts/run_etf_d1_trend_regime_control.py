"""Run the fixed source-local ETF D1 trend-regime control offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.research.etf_d1_trend_regime import (
    run_current_etf_d1_trend_regime_control,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    args = parser.parse_args()
    result = run_current_etf_d1_trend_regime_control(
        run_label=args.run_label,
        repository_root=Path(__file__).resolve().parents[1],
    )
    print(
        json.dumps(
            {
                "precommit_hash": result.precommit_hash,
                "summary_path": str(result.summary_path),
                "falsified": result.falsified,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

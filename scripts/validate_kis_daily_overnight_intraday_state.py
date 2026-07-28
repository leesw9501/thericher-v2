"""Independently reattest one bounded KIS QQQ/SPY D1 state CPU smoke."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_daily_overnight_intraday_state import (
    DEFAULT_KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ARTIFACT_ROOT,
)
from thericher_v2.research.kis_daily_overnight_intraday_state_validation import (
    validate_current_kis_daily_overnight_intraday_state_cpu_smoke,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--precommit-path", required=True, type=Path)
    parser.add_argument("--summary-path", required=True, type=Path)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ARTIFACT_ROOT,
    )
    args = parser.parse_args(argv)
    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

    precommit_hash, summary_hash, receipt_path = (
        validate_current_kis_daily_overnight_intraday_state_cpu_smoke(
            cache_root=Path(args.cache_root),
            artifact_root=Path(args.artifact_root),
            precommit_path=Path(args.precommit_path),
            summary_path=Path(args.summary_path),
            run_label=run_label,
            repository_root=_REPOSITORY_ROOT,
        )
    )
    print(
        "\n".join(
            (
                "status=attested",
                f"precommit_hash={precommit_hash}",
                f"summary_hash={summary_hash}",
                f"receipt_path={receipt_path}",
            )
        )
    )


if __name__ == "__main__":
    main()

"""Run the bounded, offline-only KIS QQQ/SPY D1 state CPU smoke."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_daily_overnight_intraday_state import (
    DEFAULT_KIS_DAILY_OVERNIGHT_INTRADAY_STATE_ARTIFACT_ROOT,
    load_current_kis_daily_overnight_intraday_state_input,
    run_kis_daily_overnight_intraday_state_cpu_smoke,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", default="cpu-smoke")
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

    state_input = load_current_kis_daily_overnight_intraday_state_input(
        cache_root=Path(args.cache_root),
        repository_root=_REPOSITORY_ROOT,
    )
    run = run_kis_daily_overnight_intraday_state_cpu_smoke(
        state_input,
        artifact_root=Path(args.artifact_root),
        run_label=run_label,
        repository_root=_REPOSITORY_ROOT,
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    print(
        "\n".join(
            (
                f"status={summary['status']}",
                f"outcome={summary['outcome']}",
                f"precommit_hash={run.precommit_hash}",
                f"artifact_dir={run.summary_path.parent}",
            )
        )
    )


if __name__ == "__main__":
    main()

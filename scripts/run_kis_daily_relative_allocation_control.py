"""Run the frozen offline QQQ/SPY D1 relative-allocation CPU control."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_daily_relative_allocation_control import (
    run_kis_daily_relative_allocation_control,
)
from thericher_v2.research.kis_daily_relative_regime_control import (
    DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT,
    load_current_kis_daily_relative_regime_input,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--mode", required=True, choices=("cpu-smoke", "cpu-full"))
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT,
    )
    args = parser.parse_args(argv)
    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

    control_input = load_current_kis_daily_relative_regime_input(
        cache_root=Path(args.cache_root),
        repository_root=_REPOSITORY_ROOT,
    )
    run = run_kis_daily_relative_allocation_control(
        control_input,
        mode=args.mode,
        artifact_root=Path(args.artifact_root),
        run_label=run_label,
        repository_root=_REPOSITORY_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

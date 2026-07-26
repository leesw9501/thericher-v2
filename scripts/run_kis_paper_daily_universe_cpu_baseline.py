"""Run the frozen offline six-symbol daily local-paper baseline."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_paper_daily_universe_cpu_baseline import (
    KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
    run_kis_paper_daily_universe_cpu_baseline,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")
    artifact_root = Path(args.artifact_root)
    output_dir = artifact_root / KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID / run_label
    if output_dir.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    run = run_kis_paper_daily_universe_cpu_baseline(
        artifact_root=artifact_root,
        run_label=run_label,
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

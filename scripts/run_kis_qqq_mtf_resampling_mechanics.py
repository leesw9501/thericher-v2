"""Run the source-local QQQ/NAS multi-timeframe resampling mechanics check."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.data.kis_qqq_mtf_resampling_mechanics import (
    run_kis_qqq_mtf_resampling_mechanics,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(arguments.cache_root),
        repo_root=_REPO_ROOT,
        symbol="QQQ",
        exchange="NAS",
    )
    run = run_kis_qqq_mtf_resampling_mechanics(
        catalog,
        artifact_root=Path(arguments.artifact_root),
        run_label=str(arguments.run_label),
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()

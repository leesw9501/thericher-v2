"""Run the fixed offline SPY first-30m/final-30m momentum falsification."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.research.spy_first30_final30_momentum import (
    run_spy_first30_final30_momentum,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DATASET_ID = "kis.paper.private.intraday.spy.ams.m1.v1"
_DATASET_HASH = "sha256:64f149f5ff1c9002107f001a44f78c54c8944e9c030d6153898b1229d9c742e6"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=arguments.cache_root,
        repo_root=_REPOSITORY_ROOT,
        symbol="SPY",
        exchange="AMS",
    )
    if catalog.dataset_id != _DATASET_ID or catalog.dataset_hash != _DATASET_HASH:
        raise ValueError(
            "SPY first-30m/final-30m source identity does not match the frozen contract"
        )
    run = run_spy_first30_final30_momentum(
        catalog,
        artifact_root=arguments.artifact_root,
        run_label=arguments.run_label,
        repo_root=_REPOSITORY_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()

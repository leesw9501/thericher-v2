"""Run one aggregate-only source-local Donchian local-paper PnL attribution."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.research.kis_intraday_donchian_pnl_attribution import (
    run_source_local_qqq_donchian_local_paper_pnl_attribution,
)
from thericher_v2.research.kis_intraday_donchian_replay import (
    load_kis_intraday_donchian_replay_receipt,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_DEFAULT_PARENT_RUN_DIRECTORY = (
    _DEFAULT_ARTIFACT_ROOT
    / "research"
    / "kis-intraday-session-reset-donchian-mechanics-v1"
    / "m1-donchian-mechanics-20260806-r1"
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--parent-precommit",
        type=Path,
        default=_DEFAULT_PARENT_RUN_DIRECTORY / "precommit.json",
    )
    parser.add_argument(
        "--parent-summary",
        type=Path,
        default=_DEFAULT_PARENT_RUN_DIRECTORY / "summary.json",
    )
    arguments = parser.parse_args(argv)
    catalog = load_verified_kis_paper_private_intraday_catalog(
        cache_root=Path(arguments.cache_root),
        repo_root=_REPO_ROOT,
        symbol="QQQ",
        exchange="NAS",
    )
    parent_receipt = load_kis_intraday_donchian_replay_receipt(
        precommit_path=Path(arguments.parent_precommit),
        summary_path=Path(arguments.parent_summary),
        repo_root=_REPO_ROOT,
    )
    run = run_source_local_qqq_donchian_local_paper_pnl_attribution(
        catalog,
        parent_receipt=parent_receipt,
        artifact_root=Path(arguments.artifact_root),
        run_label=str(arguments.run_label),
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()

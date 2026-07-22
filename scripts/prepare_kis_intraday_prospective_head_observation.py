"""Prepare the bounded prospective KIS intraday head observation from index metadata."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_intraday_prospective_head_observation import (
    prepare_kis_intraday_prospective_head_observation,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_HEAD_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday-head"
)
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--head-cache-root", type=Path, default=_DEFAULT_HEAD_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    result = prepare_kis_intraday_prospective_head_observation(
        head_cache_root=Path(args.head_cache_root),
        artifact_root=Path(args.artifact_root),
        run_label=str(args.run_label),
        repo_root=_REPO_ROOT,
    )
    print(json.dumps(result.to_payload(), sort_keys=True))


if __name__ == "__main__":
    main()

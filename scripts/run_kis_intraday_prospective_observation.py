"""Run the first pair-bound KIS prospective observation entirely offline."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_intraday_prospective_observation import (
    load_kis_intraday_prospective_observation_input,
)
from thericher_v2.research.kis_intraday_prospective_observation_runner import (
    run_kis_intraday_prospective_observation,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_HISTORICAL_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday"
    )
    _DEFAULT_HEAD_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday-head"
    )
    _DEFAULT_PREPARATION_DIR = Path(
        "/app/model_artifacts/kis-intraday-prospective-head-observation/scheduled-head-v1"
    )
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_HISTORICAL_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday"
    )
    _DEFAULT_HEAD_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday-head"
    )
    _DEFAULT_PREPARATION_DIR = Path(
        r"D:\thericher-v2\model-artifacts\kis-intraday-prospective-head-observation\scheduled-head-v1"
    )
    _DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

_PAIR_FILENAMES = ("precommit.json", "planning-receipt.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--historical-cache-root",
        type=Path,
        default=_DEFAULT_HISTORICAL_CACHE_ROOT,
    )
    parser.add_argument("--head-cache-root", type=Path, default=_DEFAULT_HEAD_CACHE_ROOT)
    parser.add_argument("--preparation-dir", type=Path, default=_DEFAULT_PREPARATION_DIR)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    pair_status = _preparation_pair_status(args.preparation_dir)
    if pair_status is not None:
        print(json.dumps(pair_status, sort_keys=True))
        return 0
    try:
        observation_input = load_kis_intraday_prospective_observation_input(
            historical_cache_root=args.historical_cache_root,
            head_cache_root=args.head_cache_root,
            preparation_dir=args.preparation_dir,
            repo_root=_REPO_ROOT,
        )
    except ValueError:
        print(
            json.dumps(
                {
                    "kind": "kis_intraday_prospective_observation",
                    "status": "unavailable",
                    "reason": "verified_input_unavailable",
                },
                sort_keys=True,
            )
        )
        return 0
    run = run_kis_intraday_prospective_observation(
        observation_input,
        artifact_root=args.artifact_root,
        repo_root=_REPO_ROOT,
    )
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "kind": "kis_intraday_prospective_observation",
                "status": "complete",
                "summary": summary,
            },
            sort_keys=True,
        )
    )
    return 0


def _preparation_pair_status(preparation_dir: Path) -> dict[str, str] | None:
    paths = tuple(preparation_dir / filename for filename in _PAIR_FILENAMES)
    existing = tuple(path.exists() and not path.is_symlink() for path in paths)
    if not any(existing):
        return {
            "kind": "kis_intraday_prospective_observation",
            "status": "pending",
            "reason": "preparation_pair_missing",
        }
    if not all(existing):
        return {
            "kind": "kis_intraday_prospective_observation",
            "status": "unavailable",
            "reason": "preparation_pair_incomplete",
        }
    return None


if __name__ == "__main__":
    raise SystemExit(main())

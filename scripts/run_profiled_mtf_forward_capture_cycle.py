"""Run one local-cache profiled-MTF forward capture-cycle invocation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_intraday_mtf_availability import (
    load_kis_intraday_mtf_availability_catalogs,
)
from thericher_v2.data.profiled_mtf_forward_capture_cycle import (
    PROFILED_MTF_FORWARD_CAPTURE_CYCLE_ID,
    run_profiled_mtf_forward_capture_cycle,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_HISTORICAL_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday"
    )
    _DEFAULT_HEAD_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday-head"
    )
    _DEFAULT_MARKET_DATA_ROOT = Path("/app/market_data")
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_HISTORICAL_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday"
    )
    _DEFAULT_HEAD_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday-head"
    )
    _DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
    _DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

_RECOVERY_EXIT_CODE = 20


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--historical-cache-root",
        type=Path,
        default=_DEFAULT_HISTORICAL_CACHE_ROOT,
    )
    parser.add_argument("--head-cache-root", type=Path, default=_DEFAULT_HEAD_CACHE_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--observed-at", type=_parse_utc)
    parser.add_argument("--code-revision-sha256")
    args = parser.parse_args(argv)
    try:
        result = run_profiled_mtf_forward_capture_cycle(
            historical_cache_root=args.historical_cache_root,
            head_cache_root=args.head_cache_root,
            market_data_root=args.market_data_root,
            artifact_root=args.artifact_root,
            repo_root=_REPO_ROOT,
            code_revision=args.code_revision_sha256 or _code_revision(_REPO_ROOT),
            observed_at=args.observed_at or datetime.now(UTC),
            catalog_loader=load_kis_intraday_mtf_availability_catalogs,
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": PROFILED_MTF_FORWARD_CAPTURE_CYCLE_ID,
                    "action": "recovery",
                    "status": "input_unavailable",
                },
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE
    print(json.dumps(result.safe_payload(), sort_keys=True))
    if result.source_result is not None and result.source_result.outcome == "busy":
        return _RECOVERY_EXIT_CODE
    return 0


def _code_revision(repo_root: Path) -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = "git-unavailable"
    return "sha256:" + hashlib.sha256(revision.encode("ascii")).hexdigest()


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("observed_at must be UTC") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("observed_at must be UTC")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())

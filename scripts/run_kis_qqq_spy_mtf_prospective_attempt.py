"""Materialize one credential-free QQQ/SPY prospective attempt from local caches."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_qqq_spy_mtf_prospective_observation import (
    KisQqqSpyMtfProspectiveObservationError,
    prospective_observation_window,
    run_kis_qqq_spy_mtf_prospective_attempt,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_HISTORICAL_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday"
    )
    _DEFAULT_HEAD_CACHE_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/intraday-head"
    )
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_HISTORICAL_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday"
    )
    _DEFAULT_HEAD_CACHE_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\intraday-head"
    )
    _DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

_DEFAULT_AVAILABILITY_SUMMARY = (
    _DEFAULT_ARTIFACT_ROOT
    / "data"
    / "kis-intraday-mtf-availability-receipt-v1"
    / "local-cache-20260802-r2"
    / "summary.json"
)
_RECOVERY_EXIT_CODE = 20


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--historical-cache-root",
        type=Path,
        default=_DEFAULT_HISTORICAL_CACHE_ROOT,
    )
    parser.add_argument("--head-cache-root", type=Path, default=_DEFAULT_HEAD_CACHE_ROOT)
    parser.add_argument(
        "--availability-summary",
        type=Path,
        default=_DEFAULT_AVAILABILITY_SUMMARY,
    )
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--observed-at", type=_parse_utc)
    args = parser.parse_args(argv)
    observed_at = args.observed_at or datetime.now(UTC)
    if prospective_observation_window(observed_at) is None:
        print(
            json.dumps(
                {
                    "kind": "kis_qqq_spy_mtf_prospective_observation",
                    "status": "pending",
                    "reason": "outside_eligible_observation_window",
                },
                sort_keys=True,
            )
        )
        return 0
    try:
        result = run_kis_qqq_spy_mtf_prospective_attempt(
            availability_summary_path=args.availability_summary,
            historical_cache_root=args.historical_cache_root,
            head_cache_root=args.head_cache_root,
            artifact_root=args.artifact_root,
            repo_root=_REPO_ROOT,
            code_revision=_code_revision(_REPO_ROOT),
            observed_at=observed_at,
        )
    except (KisQqqSpyMtfProspectiveObservationError, OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": "kis_qqq_spy_mtf_prospective_observation",
                    "status": "unavailable",
                    "reason": "verified_input_unavailable",
                },
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE
    if result is None:
        raise RuntimeError("eligible prospective observation unexpectedly returned no result")
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return _RECOVERY_EXIT_CODE if result.outcome == "busy" else 0


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

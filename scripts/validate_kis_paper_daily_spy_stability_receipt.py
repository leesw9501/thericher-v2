"""Validate one stored D1 stability receipt without credentials or network access."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_spy_stability_observer import (
    KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_ROOT,
    KisPaperDailySpyStabilityObserverError,
    validate_kis_paper_daily_spy_stability_receipt,
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-path", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=KIS_PAPER_DAILY_SPY_STABILITY_OBSERVER_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        observation = validate_kis_paper_daily_spy_stability_receipt(
            args.receipt_path,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
        )
    except (KisPaperDailySpyStabilityObserverError, OSError, ValueError):
        print(
            json.dumps(
                {"status": "unavailable", "reason": "receipt_unavailable"},
                sort_keys=True,
            )
        )
        return
    print(json.dumps(observation.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()

"""Run the bounded offline QQQ/SPY D1 local-paper naive validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.research.kis_daily_masked_naive_validation import (
    DEFAULT_KIS_DAILY_MASKED_NAIVE_ARTIFACT_ROOT,
    run_pinned_kis_daily_masked_naive_validation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_DAILY_MASKED_NAIVE_ARTIFACT_ROOT,
    )
    args = parser.parse_args()
    result = run_pinned_kis_daily_masked_naive_validation(
        artifact_root=args.artifact_root,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "artifact_path": str(result.artifact_path),
                "artifact_sha256": result.artifact_sha256,
                "common_session_count": result.common_session_count,
                "control_count": len(result.control_results),
                "local_paper_fill_count": sum(
                    item.fill_count for item in result.control_results
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

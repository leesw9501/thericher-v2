"""Write the bounded local-only replacement-data inventory artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.local_replacement_inventory import (
    build_local_replacement_inventory,
)
from thericher_v2.data.norgate_broad_development_artifact import DEFAULT_MODEL_ARTIFACT_ROOT
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = build_local_replacement_inventory(
        market_data_root=args.market_data_root,
        artifact_root=args.artifact_root,
        repo_root=args.repo_root,
    )
    print(
        json.dumps(
            {
                "artifact_dir": str(result.artifact_dir),
                "summary_path": str(result.summary_path),
                "summary_sha256": result.summary_sha256,
                "conclusion": result.conclusion,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Write the single sanitized qualification receipt for the frozen Norgate panel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.norgate_development_qualification import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    qualify_frozen_norgate_trial_development_panel,
)
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    args = parser.parse_args()
    result = qualify_frozen_norgate_trial_development_panel(
        artifact_root=args.artifact_root,
        market_data_root=args.market_data_root,
        repo_root=_REPOSITORY_ROOT,
    )
    print(
        json.dumps(
            {
                "receipt_path": str(result.receipt_path),
                "receipt_hash": result.receipt_hash,
                "status": result.status,
                "source_dataset_hash": result.source_dataset_hash,
                "source_manifest_hash": result.source_manifest_hash,
                "selected_symbol_count": result.selected_symbol_count,
                "common_session_count": result.common_session_count,
                "scope": dict(result.scope),
                "development_interface": dict(result.development_interface),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

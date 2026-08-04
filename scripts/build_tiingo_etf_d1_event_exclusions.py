"""Build one immutable Tiingo ETF D1 source-marker exclusion sidecar."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import DEFAULT_MARKET_DATA_ROOT
from thericher_v2.data.tiingo_etf_event_exclusions import (
    TiingoEtfEventExclusionError,
    build_tiingo_etf_d1_event_exclusion_snapshot,
    default_tiingo_etf_d1_event_exclusion_snapshot_dir,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    arguments = parser.parse_args(argv)
    retrieved_at = datetime.now(UTC)
    destination = arguments.destination or default_tiingo_etf_d1_event_exclusion_snapshot_dir(
        retrieved_at
    )
    try:
        result = build_tiingo_etf_d1_event_exclusion_snapshot(
            destination=destination,
            parent_snapshot=arguments.parent,
            retrieved_at_utc=retrieved_at,
            market_data_root=arguments.market_data_root,
            repo_root=_REPOSITORY_ROOT,
        )
    except (OSError, TiingoEtfEventExclusionError, ValueError) as error:
        print(
            json.dumps(
                {
                    "kind": "tiingo_etf_d1_event_marker_exclusions",
                    "status": "categorical_failure",
                    "failure_class": type(error).__name__,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "kind": "tiingo_etf_d1_event_marker_exclusions",
                "status": "created",
                "snapshot_dir": str(result.snapshot_dir),
                "parent_snapshot_dir": str(result.parent_snapshot_dir),
                "parent_dataset_hash": result.parent_dataset_hash,
                "parent_manifest_hash": result.parent_manifest_hash,
                "manifest_hash": result.manifest_hash,
                "marker_count": result.marker_count,
                "excluded_session_count": result.excluded_session_count,
                "session_counts": dict(result.session_counts),
                "free_percent": result.free_percent,
                "point_in_time_eligible": False,
                "paper_input_eligible": False,
                "ranking_eligible": False,
                "sealed_holdout_eligible": False,
                "event_semantics_verified": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

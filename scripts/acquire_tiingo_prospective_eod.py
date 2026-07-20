"""Acquire the one bounded prospective Tiingo Standard EOD snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.tiingo_prospective_eod import (
    PROSPECTIVE_EOD_REQUESTED_START,
    acquire_tiingo_prospective_eod_snapshot,
    clamp_source_as_of,
    latest_source_complete_date,
)


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-as-of", type=_date_argument)
    args = parser.parse_args()

    retrieved_at = datetime.now(UTC)
    requested_source_as_of = args.source_as_of or latest_source_complete_date(retrieved_at)
    source_as_of = clamp_source_as_of(requested_source_as_of, retrieved_at_utc=retrieved_at)
    snapshot = acquire_tiingo_prospective_eod_snapshot(
        env_path=Path(".env"),
        requested_start=PROSPECTIVE_EOD_REQUESTED_START,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "snapshot_dir": str(snapshot.snapshot_dir),
                "dataset_hash": snapshot.dataset_hash,
                "manifest_hash": snapshot.manifest_hash,
                "retrieved_at_utc": snapshot.retrieved_at_utc.isoformat(),
                "source_as_of": snapshot.source_as_of.isoformat(),
                "row_count": snapshot.row_count,
                "request_count": len(snapshot.raw_files),
                "prospective_lineage_only": snapshot.prospective_lineage_only,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

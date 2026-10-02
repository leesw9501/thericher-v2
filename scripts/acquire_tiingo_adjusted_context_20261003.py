"""Plan one new-vintage ETF context snapshot; acquire only with --acquire.

Raw responses retain provider fields, but canonical rows remain unadjusted.
This does not qualify adjusted fields, historical availability or a consumer.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import (
    DEFAULT_MARKET_DATA_ROOT,
    TIINGO_ETF_D1_SYMBOLS,
    acquire_tiingo_etf_d1_snapshot,
    default_tiingo_etf_d1_snapshot_dir,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_REQUESTED_START = date(2025, 7, 1)
_REQUESTED_END = date(2026, 9, 30)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--acquire", action="store_true")
    arguments = parser.parse_args(argv)
    retrieved_at = datetime.now(UTC)
    destination = default_tiingo_etf_d1_snapshot_dir(retrieved_at)
    payload: dict[str, object] = {
        "status": "plan_only",
        "snapshot_dir": str(destination),
        "retrieved_at_utc": retrieved_at.isoformat(),
        "request_range": {
            "start": _REQUESTED_START.isoformat(),
            "end": _REQUESTED_END.isoformat(),
        },
        "symbols": list(TIINGO_ETF_D1_SYMBOLS),
        "planned_request_count": len(TIINGO_ETF_D1_SYMBOLS),
    }
    if not arguments.acquire:
        print(json.dumps(payload, sort_keys=True))
        return 0

    try:
        # The existing acquisition path reads only the approved TIINGO_API_TOKEN.
        snapshot = acquire_tiingo_etf_d1_snapshot(
            env_path=_REPOSITORY_ROOT / ".env",
            destination=destination,
            requested_start=_REQUESTED_START,
            requested_end=_REQUESTED_END,
            retrieved_at_utc=retrieved_at,
            market_data_root=DEFAULT_MARKET_DATA_ROOT,
            repo_root=_REPOSITORY_ROOT,
        )
    except FileExistsError:
        payload["status"] = "destination_exists"
    except Exception:
        # Do not expose provider bodies, exception text or credential failures.
        payload["status"] = "acquisition_unavailable"
    else:
        payload.update(
            {
                "status": "acquired",
                "snapshot_dir": str(snapshot.snapshot_dir),
                "dataset_id": snapshot.dataset_id,
                "dataset_hash": snapshot.dataset_hash,
                "manifest_hash": snapshot.manifest_hash,
                "raw_hashes": dict(snapshot.raw_hashes),
                "session_counts": dict(snapshot.session_counts),
                "row_count": snapshot.row_count,
                "completed_request_count": len(TIINGO_ETF_D1_SYMBOLS),
            }
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    print(json.dumps(payload, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

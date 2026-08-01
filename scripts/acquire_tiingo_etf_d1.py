"""Collect one immutable raw-D1 Tiingo snapshot for SPY, QQQ, and IWM."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.tiingo_etf_daily import (
    DEFAULT_MARKET_DATA_ROOT,
    DEFAULT_TIINGO_ETF_D1_RECEIPT_ROOT,
    TiingoEtfDailyError,
    acquire_tiingo_etf_d1_snapshot,
    default_tiingo_etf_d1_snapshot_dir,
    write_tiingo_etf_d1_receipt,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_START = date(1990, 1, 1)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=_parse_date, default=_DEFAULT_START)
    parser.add_argument("--end", type=_parse_date, default=datetime.now(UTC).date())
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_TIINGO_ETF_D1_RECEIPT_ROOT)
    arguments = parser.parse_args(argv)
    retrieved_at = datetime.now(UTC)
    destination = arguments.destination or default_tiingo_etf_d1_snapshot_dir(retrieved_at)
    try:
        snapshot = acquire_tiingo_etf_d1_snapshot(
            env_path=_REPOSITORY_ROOT / ".env",
            destination=destination,
            requested_start=arguments.start,
            requested_end=arguments.end,
            retrieved_at_utc=retrieved_at,
            market_data_root=arguments.market_data_root,
            repo_root=_REPOSITORY_ROOT,
        )
        receipt_path = write_tiingo_etf_d1_receipt(
            snapshot,
            artifact_root=arguments.artifact_root,
            repo_root=_REPOSITORY_ROOT,
        )
    except (OSError, TiingoEtfDailyError, ValueError) as error:
        print(
            json.dumps(
                {
                    "kind": "tiingo_etf_raw_d1_collection_receipt",
                    "status": "categorical_failure",
                    "failure_class": type(error).__name__,
                    "symbols": ["SPY", "QQQ", "IWM"],
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from None
    print(
        json.dumps(
            {
                "kind": "tiingo_etf_raw_d1_collection_receipt",
                "status": "collected",
                "snapshot_dir": str(snapshot.snapshot_dir),
                "receipt_path": str(receipt_path),
                "dataset_id": snapshot.dataset_id,
                "dataset_hash": snapshot.dataset_hash,
                "manifest_hash": snapshot.manifest_hash,
                "session_counts": dict(snapshot.session_counts),
                "event_session_counts": dict(snapshot.event_session_counts),
                "free_percent": snapshot.free_percent,
            },
            sort_keys=True,
        )
    )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


if __name__ == "__main__":
    main()

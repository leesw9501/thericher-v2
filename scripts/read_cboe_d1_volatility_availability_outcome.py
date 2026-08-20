"""Read one Cboe D1 availability outcome without network or raw-data output."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from thericher_v2.data.cboe_d1_volatility_availability import (
    _CBOE_DAILY_PRICE_URLS,
    CboeD1VolatilityAvailabilityError,
    read_cboe_d1_volatility_availability_outcome,
)


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from error


def _utc_datetime_argument(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a UTC ISO-8601 timestamp") from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise argparse.ArgumentTypeError("expected a UTC ISO-8601 timestamp")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read one Cboe D1 availability outcome")
    parser.add_argument("--series", required=True, choices=sorted(_CBOE_DAILY_PRICE_URLS))
    parser.add_argument("--session-label", required=True, type=_date_argument)
    parser.add_argument("--session-close", required=True, type=_utc_datetime_argument)
    parser.add_argument("--next-market-open", required=True, type=_utc_datetime_argument)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        outcome = read_cboe_d1_volatility_availability_outcome(
            series_symbol=args.series,
            session_label=args.session_label,
            session_close=args.session_close,
            next_market_open=args.next_market_open,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
        )
        payload = {
            "status": outcome.status,
            "series_symbol": outcome.series_symbol,
            "session_label": outcome.session_label,
            "receipt_sha256": outcome.receipt_sha256,
            "observed_at_utc": outcome.observed_at_utc,
            "receipt_path": str(outcome.receipt_path) if outcome.receipt_path is not None else None,
        }
    except CboeD1VolatilityAvailabilityError:
        payload = {
            "status": "unavailable",
            "series_symbol": args.series,
            "session_label": args.session_label.isoformat(),
            "receipt_sha256": None,
            "observed_at_utc": None,
            "receipt_path": None,
        }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()

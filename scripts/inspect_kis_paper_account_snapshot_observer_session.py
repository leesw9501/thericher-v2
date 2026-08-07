"""Classify an explicit UTC time against the 2026 US equity session calendar."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from thericher_v2.data.us_equity_session import (
    US_EQUITY_EASTERN,
    us_equity_2026_session,
)

SessionStatus = Literal[
    "eligible", "outside_regular_session", "session_unavailable"
]
_KIND = "kis_paper_snapshot_observer_session"


def inspect_session(observed_at: datetime) -> dict[str, str]:
    """Return the observer's source-safe session classification for one UTC time."""

    if type(observed_at) is not datetime or observed_at.tzinfo is not UTC:
        raise ValueError("observed_at must be an explicit UTC datetime")

    session_date = observed_at.astimezone(US_EQUITY_EASTERN).date()
    try:
        session = us_equity_2026_session(session_date)
    except ValueError:
        status: SessionStatus = "session_unavailable"
    else:
        if session is None:
            status = "session_unavailable"
        elif session.window.open_ts <= observed_at < session.window.close_ts:
            status = "eligible"
        else:
            status = "outside_regular_session"

    return {
        "kind": _KIND,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "status": status,
    }


def _parse_observed_at(value: str) -> datetime:
    if not (value.endswith("Z") or value.endswith("+00:00")):
        raise argparse.ArgumentTypeError("observed_at must use an explicit UTC offset")

    try:
        observed_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("observed_at must be an ISO-8601 datetime") from error

    if observed_at.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("observed_at must use an explicit UTC offset")
    return observed_at


def main(argv: Sequence[str] | None = None) -> None:
    """Print one source-safe classification object."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-at", required=True, type=_parse_observed_at)
    args = parser.parse_args(argv)
    print(json.dumps(inspect_session(args.observed_at), sort_keys=True))


if __name__ == "__main__":
    main()

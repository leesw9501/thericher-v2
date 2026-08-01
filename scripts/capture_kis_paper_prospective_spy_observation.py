"""Materialize one fresh SPY prospective receipt from the local KIS Paper cache."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_prospective_spy_capture import (
    capture_kis_paper_prospective_spy_observation,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/intraday")
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
    _DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", type=_parse_date, required=True)
    parser.add_argument("--observed-at", type=_parse_datetime, default=datetime.now(UTC))
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    result = capture_kis_paper_prospective_spy_observation(
        cache_root=args.cache_root,
        artifact_root=args.artifact_root,
        repo_root=_REPO_ROOT,
        session_date=args.session_date,
        observed_at=args.observed_at,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("--session-date must use YYYY-MM-DD") from error


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("--observed-at must be ISO-8601 UTC") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--observed-at must include a UTC offset")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())

"""Write a source-safe readiness receipt from one completed KIS head collection."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_qqq_intraday_head_readiness import (
    KIS_QQQ_INTRADAY_HEAD_READINESS_KIND,
    observe_kis_paper_qqq_intraday_head_readiness,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday-head")
_DEFAULT_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts\data\kis-qqq-intraday-head-readiness-v1"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Observe a metadata-only QQQ readiness window")
    parser.add_argument("--collection-started-at", type=_parse_utc, required=True)
    parser.add_argument("--collector-returned-at", type=_parse_utc, required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    args = parser.parse_args(argv)
    try:
        result = observe_kis_paper_qqq_intraday_head_readiness(
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            collection_started_at=args.collection_started_at,
            collector_returned_at=args.collector_returned_at,
        )
        payload = result.safe_payload()
    except (OSError, TypeError, ValueError):
        payload = {
            "kind": KIS_QQQ_INTRADAY_HEAD_READINESS_KIND,
            "status": "input_unavailable",
            "reason": "metadata_unavailable",
        }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("collection timestamps must be UTC") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("collection timestamps must be UTC")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())

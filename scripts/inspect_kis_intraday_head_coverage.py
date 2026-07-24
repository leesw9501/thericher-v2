"""Print a safe prospective-head coverage summary without opening raw minute data."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_intraday_head_coverage import (
    inspect_kis_paper_private_intraday_head_coverage,
)
from thericher_v2.research.kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_HEAD_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday-head"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head-cache-root", type=Path, default=_DEFAULT_HEAD_CACHE_ROOT)
    arguments = parser.parse_args(argv)

    coverage = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=arguments.head_cache_root,
        repo_root=_REPO_ROOT,
        after_session_date=KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1],
        required_complete_session_count=KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
    )
    print(json.dumps(coverage.to_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

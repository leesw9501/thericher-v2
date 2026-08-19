"""Reattach the isolated IWM current-head cache without provider access."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_iwm_current_head_cache_mechanics import (
    KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_KIND,
    inspect_and_write_kis_paper_iwm_current_head_cache_mechanics,
)
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT,
    KIS_PAPER_MARKET_DATA_ROOT,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_IWM_CURRENT_HEAD_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=KIS_PAPER_MARKET_DATA_ROOT)
    args = parser.parse_args(argv)
    try:
        receipt = inspect_and_write_kis_paper_iwm_current_head_cache_mechanics(
            cache_root=args.cache_root,
            artifact_root=args.artifact_root,
            repo_root=args.repository_root,
            market_data_root=args.market_data_root,
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_IWM_CURRENT_HEAD_CACHE_MECHANICS_KIND,
                    "status": "unavailable",
                    "reason": "cache_verification_failed",
                    "network_access": False,
                    "credentials_read": False,
                    "paper_execution": False,
                },
                sort_keys=True,
            )
        )
        return 2
    payload = receipt.mechanics.safe_payload()
    payload["evidence_sha256"] = receipt.evidence_sha256
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run one offline causal-qualification check for the QQQ/SPY D1 forward cache."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.kis_paper_daily_forward_causal_qualification import (
    qualify_current_kis_paper_daily_pair_forward_cache,
    write_kis_daily_forward_causal_qualification_receipt,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\daily-qqq-spy-forward\v1"
)
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--parent-receipt", required=True, type=Path)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    args = parser.parse_args(argv)

    result = qualify_current_kis_paper_daily_pair_forward_cache(
        cache_root=args.cache_root,
        parent_receipt_path=args.parent_receipt,
        artifact_root=args.artifact_root,
        repository_root=_REPOSITORY_ROOT,
    )
    receipt = write_kis_daily_forward_causal_qualification_receipt(
        result=result,
        artifact_root=args.artifact_root,
        repository_root=_REPOSITORY_ROOT,
        run_label=str(args.run_label),
    )
    artifact_root = Path(args.artifact_root).resolve(strict=True)
    print(
        json.dumps(
            {
                "status": result.status,
                "missing_condition_ids": list(result.missing_condition_ids),
                "receipt_sha256": receipt.receipt_sha256,
                "receipt_path_relative_to_artifact_root": receipt.receipt_path.relative_to(
                    artifact_root
                ).as_posix(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Print one offline, sanitized current KIS intraday-head schedule fact."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from thericher_v2.ops.kis_paper_intraday_head_schedule_receipt import (
    DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    KisPaperIntradayHeadScheduleReceiptError,
    read_kis_paper_intraday_head_schedule_fact_from_artifact_root,
)


def default_artifact_root() -> Path:
    """Use the host artifact mount without loading project configuration files."""

    return Path(
        os.environ.get(
            "THERICHER_HOST_MODEL_ARTIFACT_ROOT",
            DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
        )
    )


def default_capture_cache_root() -> Path:
    """Use only the external intraday-head cache mount for bound receipts."""

    return Path(os.environ.get("THERICHER_HOST_MARKET_DATA_ROOT", r"D:\market_data")) / (
        "us_equities/kis_paper_private/intraday-head"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project the current task-owned KIS intraday-head terminal schedule receipt"
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=default_artifact_root(),
    )
    parser.add_argument(
        "--capture-cache-root",
        type=Path,
        default=default_capture_cache_root(),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        fact = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            arguments.artifact_root,
            capture_cache_root=arguments.capture_cache_root,
        )
    except (KisPaperIntradayHeadScheduleReceiptError, ValueError):
        print(json.dumps({"status": "unavailable"}, sort_keys=True))
        return 2
    print(json.dumps(fact.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

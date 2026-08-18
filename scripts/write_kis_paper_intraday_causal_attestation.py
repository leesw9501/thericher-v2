"""Write one future-only KIS Paper intraday causal-attestation artifact."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.ops.kis_paper_intraday_causal_attestation_writer import (
    DEFAULT_KIS_PAPER_INTRADAY_HEAD_CAPTURE_CACHE_ROOT,
    write_current_kis_paper_intraday_causal_attestation,
)
from thericher_v2.ops.kis_paper_intraday_head_schedule_receipt import (
    DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    )
    parser.add_argument(
        "--capture-cache-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_CAPTURE_CACHE_ROOT,
    )
    arguments = parser.parse_args(argv)
    if not arguments.execute:
        print(json.dumps({"status": "not_executed", "reason": "execute_flag_required"}))
        return 0
    result = write_current_kis_paper_intraday_causal_attestation(
        artifact_root=arguments.artifact_root,
        repository_root=_REPOSITORY_ROOT,
        capture_cache_root=arguments.capture_cache_root,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

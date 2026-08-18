"""Print the validated current source-safe intraday-head invocation pointer."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.ops.kis_paper_intraday_head_invocation_receipt import (
    DEFAULT_KIS_PAPER_INTRADAY_HEAD_INVOCATION_ARTIFACT_ROOT,
    KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND,
    read_current_kis_paper_intraday_head_invocation_runtime_fact,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_INVOCATION_ARTIFACT_ROOT,
    )
    arguments = parser.parse_args(argv)
    try:
        fact = read_current_kis_paper_intraday_head_invocation_runtime_fact(
            artifact_root=arguments.artifact_root,
            repository_root=_REPOSITORY_ROOT,
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": KIS_PAPER_INTRADAY_HEAD_INVOCATION_RUNTIME_KIND,
                    "status": "unavailable",
                },
                sort_keys=True,
            )
        )
        return 0
    payload = fact.safe_payload()
    payload["status"] = "complete"
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

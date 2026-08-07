"""Reattest one explicit KIS Paper snapshot-observer receipt offline."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.execution.kis_paper_console_bridge import (
    read_kis_paper_snapshot_observer_evidence,
)
from thericher_v2.execution.kis_readonly import DEFAULT_KIS_PAPER_ARTIFACT_ROOT

_KIND = "kis_paper_snapshot_observer_reattachment"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reattest one explicit KIS Paper snapshot observer receipt"
    )
    parser.add_argument("--evidence-path", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_ARTIFACT_ROOT,
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        fact = read_kis_paper_snapshot_observer_evidence(
            evidence_path=arguments.evidence_path,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "kind": _KIND,
                    "status": "unavailable",
                    "reason_code": "observer_evidence_unavailable",
                    "scope": "read_only",
                    "submit_capability": False,
                },
                sort_keys=True,
            )
        )
        return 2

    payload = {"kind": _KIND, **fact}
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

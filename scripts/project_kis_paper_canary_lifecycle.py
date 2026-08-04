"""Print one read-only sanitized KIS Paper canary lifecycle or session fact."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from thericher_v2.execution.paper_canary_lifecycle import (
    PaperCanaryLifecycleError,
    read_paper_canary_lifecycle_fact_from_artifact_root,
    read_paper_canary_session_fact_from_artifact_root,
)

DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def default_artifact_root() -> Path:
    """Use the host mount setting; the container path is not valid on Windows."""

    return Path(os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT", DEFAULT_ARTIFACT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project one sanitized KIS Paper canary lifecycle or scheduled session"
    )
    selected_receipt = parser.add_mutually_exclusive_group(required=True)
    selected_receipt.add_argument("--run-id")
    selected_receipt.add_argument("--session-id")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=default_artifact_root(),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.run_id is not None:
            fact = read_paper_canary_lifecycle_fact_from_artifact_root(
                arguments.artifact_root,
                arguments.run_id,
            )
        else:
            fact = read_paper_canary_session_fact_from_artifact_root(
                arguments.artifact_root,
                arguments.session_id,
            )
    except (PaperCanaryLifecycleError, ValueError):
        print(json.dumps({"status": "unavailable", "paper_only": True}, sort_keys=True))
        return 2
    print(json.dumps(fact.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

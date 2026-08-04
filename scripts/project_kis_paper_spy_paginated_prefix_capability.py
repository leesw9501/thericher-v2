"""Print one offline, sanitized SPY paginated-prefix capability fact."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from thericher_v2.data.kis_spy_paginated_prefix_capability import (
    read_spy_paginated_prefix_capability_fact_from_artifact_root,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")


def _default_artifact_root() -> Path:
    return Path(os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT", _DEFAULT_ARTIFACT_ROOT))


def _parse_session_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("session date must be YYYY-MM-DD") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project one exact task-owned SPY paginated-prefix receipt pair"
    )
    parser.add_argument("--session-date", type=_parse_session_date, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--artifact-root", type=Path, default=_default_artifact_root())
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        fact = read_spy_paginated_prefix_capability_fact_from_artifact_root(
            artifact_root=arguments.artifact_root,
            repository_root=_REPOSITORY_ROOT,
            session_date=arguments.session_date,
            run_id=arguments.run_id,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "unavailable"}, sort_keys=True))
        return 2
    print(json.dumps(fact.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

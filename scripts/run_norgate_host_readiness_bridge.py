"""Run the raw-data-free Norgate readiness bridge in the isolated host runtime."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from thericher_v2.data.norgate_host_readiness_bridge import (  # noqa: E402
    DEFAULT_CANDIDATE_ROOTS,
    DEFAULT_RECEIPT_ROOT,
    assess_norgate_host_readiness,
    build_norgate_host_readiness_receipt,
    default_norgate_host_readiness_receipt_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    arguments = parser.parse_args()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        readiness = assess_norgate_host_readiness(
            client_loader=lambda: importlib.import_module("norgatedata"),
            candidate_roots=DEFAULT_CANDIDATE_ROOTS,
        )
    receipt = build_norgate_host_readiness_receipt(
        destination=arguments.artifact_root
        / default_norgate_host_readiness_receipt_path(arguments.run_label).name,
        readiness=readiness,
        retrieved_at_utc=datetime.now(UTC),
        artifact_root=arguments.artifact_root,
        repo_root=REPOSITORY_ROOT,
    )
    print(json.dumps(receipt.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

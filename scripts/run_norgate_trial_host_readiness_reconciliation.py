"""Run one source-safe Norgate trial host readiness reconciliation locally."""

from __future__ import annotations

import argparse
import contextlib
import csv
import importlib
import io
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from thericher_v2.data.norgate_host_readiness_bridge import (  # noqa: E402
    DEFAULT_CANDIDATE_ROOTS,
    DEFAULT_RECEIPT_ROOT,
)
from thericher_v2.data.norgate_trial_host_readiness_reconciliation import (  # noqa: E402
    DEFAULT_RECONCILIATION_ROOT,
    default_updater_installation_marker_status,
    run_norgate_trial_host_readiness_reconciliation,
    validate_norgate_trial_host_readiness_reconciliation,
)

DEFAULT_PRIOR_RECEIPT = (
    DEFAULT_RECEIPT_ROOT / "bridge-norgate-host-readiness-20260818T230439Z.json"
)
_UPDATER_IMAGE_NAMES = frozenset({"ndu.exe", "norgatedataupdater.exe"})
_RECOVERY_EXIT_CODE = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_RECONCILIATION_ROOT)
    parser.add_argument("--prior-receipt", type=Path, default=DEFAULT_PRIOR_RECEIPT)
    parser.add_argument("--prior-receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()

    if arguments.verify_only:
        receipt = validate_norgate_trial_host_readiness_reconciliation(
            run_label=arguments.run_label,
            artifact_root=arguments.artifact_root,
            repo_root=REPOSITORY_ROOT,
        )
        print(
            json.dumps(
                {
                    "status": receipt.status,
                    "summary_sha256": receipt.summary_sha256,
                    "prior_receipt_sha256": receipt.prior_receipt_sha256,
                },
                sort_keys=True,
            )
        )
        return 0

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            receipt = run_norgate_trial_host_readiness_reconciliation(
                run_label=arguments.run_label,
                retrieved_at_utc=datetime.now(UTC),
                prior_receipt_source=arguments.prior_receipt,
                prior_receipt_root=arguments.prior_receipt_root,
                artifact_root=arguments.artifact_root,
                client_loader=lambda: importlib.import_module("norgatedata"),
                updater_installation_marker_probe=default_updater_installation_marker_status,
                updater_process_probe=_updater_process_status,
                candidate_roots=DEFAULT_CANDIDATE_ROOTS,
                repo_root=REPOSITORY_ROOT,
            )
    except Exception:
        print(
            json.dumps(
                {
                    "status": "input_unavailable",
                    "reason": "diagnosis_unavailable",
                    "recovery": "restore_local_norgate_api_readiness",
                },
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE

    print(json.dumps(receipt.safe_payload(), sort_keys=True))
    return 0


def _updater_process_status(
    *,
    process_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Inspect image names in memory and return only a categorical marker."""

    try:
        completed = process_runner(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            check=False,
            errors="replace",
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if completed.returncode != 0:
        return "unavailable"
    try:
        rows = csv.reader(io.StringIO(completed.stdout))
        observed = any(
            row and row[0].strip().casefold() in _UPDATER_IMAGE_NAMES for row in rows
        )
    except (csv.Error, TypeError):
        return "unavailable"
    return "observed" if observed else "not_observed"


if __name__ == "__main__":
    raise SystemExit(main())

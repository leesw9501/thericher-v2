"""Reconcile one persisted ambiguous KIS Paper canary without a new order."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from thericher_v2.execution.emergency import DEFAULT_PAPER_EXECUTION_CONTROL_STATE
from thericher_v2.execution.kis_paper_canary import (
    DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    KisPaperCanaryError,
    reconcile_kis_paper_canary_unknown_run,
)
from thericher_v2.execution.kis_readonly import KisPaperReadOnlyError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile one ambiguous KIS virtual-paper canary without submitting an order"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_KIS_PAPER_CANARY_STATE_ROOT)
    parser.add_argument(
        "--runtime-projection",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    )
    parser.add_argument(
        "--paper-account-snapshot",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    )
    parser.add_argument(
        "--emergency-state",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    )
    parser.add_argument(
        "--execution-control",
        type=Path,
        default=DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(
            os.environ.get(
                "THERICHER_MODEL_ARTIFACT_ROOT",
                DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
            )
        ),
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def _safe_failure_reason(error: Exception) -> str:
    if isinstance(error, KisPaperCanaryError) and error.code in {
        "recovery_state_missing",
        "recovery_run_id_mismatch",
        "recovery_phase_not_reconcilable",
        "state_invalid",
    }:
        return error.code
    return "reconciliation_unavailable"


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        outcome = reconcile_kis_paper_canary_unknown_run(
            run_id=arguments.run_id,
            environment=os.environ,
            state_path=arguments.state_root / f"{arguments.run_id}.json",
            runtime_projection_path=arguments.runtime_projection,
            paper_account_snapshot_path=arguments.paper_account_snapshot,
            emergency_state_path=arguments.emergency_state,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
            execution_control_path=arguments.execution_control,
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": _safe_failure_reason(error),
                    "paper_only": True,
                }
            )
        )
        return 2
    print(json.dumps(outcome.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

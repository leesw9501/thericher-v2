"""Write one source-safe D1 target/cost receipt without model execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_kis_daily_joint_event_d1_materializer import (
    load_pinned_kis_daily_joint_event_d1_materializer,
)

from thericher_v2.kis_daily_joint_event_d1_materializer import (
    KIS_DAILY_JOINT_EVENT_D1_SUPPORTED_FOLD_IDS,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    build_kis_daily_joint_event_d1_target_cost_adapter,
    write_kis_daily_joint_event_d1_target_cost_receipt,
)
from thericher_v2.kis_daily_joint_event_window_contract import DEFAULT_MODEL_ARTIFACT_ROOT

_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument(
        "--fold-id",
        choices=KIS_DAILY_JOINT_EVENT_D1_SUPPORTED_FOLD_IDS,
        default="expanding-1",
    )
    parser.add_argument("--parent-artifact", type=Path)
    parser.add_argument("--fold-artifact", type=Path)
    parser.add_argument("--phase", choices=("development", "validation"), default="validation")
    parser.add_argument("--decision-index", type=int)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root)
    materializer = load_pinned_kis_daily_joint_event_d1_materializer(
        artifact_root=artifact_root,
        fold_id=args.fold_id,
        parent_artifact=Path(args.parent_artifact) if args.parent_artifact else None,
        fold_artifact=Path(args.fold_artifact) if args.fold_artifact else None,
        market_data_root=Path(args.market_data_root),
    )
    adapter = build_kis_daily_joint_event_d1_target_cost_adapter(materializer=materializer)
    phase = args.phase
    eligible = materializer.eligible_decision_indices(phase)
    decision_index = args.decision_index if args.decision_index is not None else eligible[0]
    destination = args.destination or (
        artifact_root
        / "research-contracts"
        / (
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            f"d1-target-cost-{args.fold_id}-{phase}-first-v2.json"
        )
    )
    receipt = write_kis_daily_joint_event_d1_target_cost_receipt(
        destination=Path(destination),
        adapter=adapter,
        phase=phase,
        decision_index=decision_index,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parents[1],
    )
    target = adapter.derive(phase=phase, decision_index=decision_index)
    print(
        json.dumps(
            {
                "status": "candidate",
                "materializer_identity": materializer.materializer_identity,
                "target_cost_identity": adapter.target_cost_identity,
                "receipt_sha256": receipt.content_hash,
                "phase": target.phase,
                "decision_index": target.decision_index,
                "feature_start_index": target.feature_start_index,
                "feature_end_index": target.feature_end_index,
                "entry_index": target.entry_index,
                "exit_index": target.exit_index,
                "model_execution_review": materializer.fold_input.model_execution_review,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

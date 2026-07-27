"""Run one candidate-only QQQ/SPY D1 classification screen offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from prepare_kis_daily_joint_event_d1_materializer import (
    load_pinned_kis_daily_joint_event_d1_materializer,
)

from thericher_v2.kis_daily_joint_event_d1_sequence_screen import (
    KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_FOLD_IDS,
    KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID,
    run_kis_daily_joint_event_d1_sequence_screen,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    build_kis_daily_joint_event_d1_target_cost_adapter,
)
from thericher_v2.kis_daily_joint_event_window_contract import DEFAULT_MODEL_ARTIFACT_ROOT

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_PARENT_ARTIFACT_NAME = (
    "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json"
)
_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")


@dataclass(frozen=True, slots=True)
class _ScreenFoldPin:
    fold_artifact_name: str
    target_cost_artifact_name: str
    target_cost_receipt_sha256: str
    target_cost_identity: str


_SCREEN_FOLD_PINS = {
    "expanding-1": _ScreenFoldPin(
        fold_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-1-v1.json"
        ),
        target_cost_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-1-validation-first-v2.json"
        ),
        target_cost_receipt_sha256=(
            "sha256:90beea4c501a946dd5502a2b0eb4a06b10a0ef36ed5f70f29c595a17dd6d7486"
        ),
        target_cost_identity=(
            "sha256:2c0ecbb889b8f1660929e87458e4a90d01f2390e41b25ed47e7201ab8a94b842"
        ),
    ),
    "expanding-2": _ScreenFoldPin(
        fold_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-2-v1.json"
        ),
        target_cost_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-2-validation-first-v2.json"
        ),
        target_cost_receipt_sha256=(
            "sha256:4de77ac80db46b1378c5728473e2f31c04b5c5343ffde8ddf507b9afb16941da"
        ),
        target_cost_identity=(
            "sha256:cd58b52816a7d0a744f8fce42a384091ce8ea9290c73316b699579a1a16291a0"
        ),
    ),
    "expanding-3": _ScreenFoldPin(
        fold_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "joint-event-window-fold-input-expanding-3-v1.json"
        ),
        target_cost_artifact_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-3-validation-first-v2.json"
        ),
        target_cost_receipt_sha256=(
            "sha256:4c389d437ed5c6ad35908dd98e1639e8ab17d41db889a7e5d1d6437c78961560"
        ),
        target_cost_identity=(
            "sha256:5511c3f072e81debe81c39792d6ca4b9500773ebf0d4029b9c7d501286176cc3"
        ),
    ),
}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cpu-smoke", "cuda-screen"), required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--fold-id", choices=KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_FOLD_IDS,
                        default="expanding-1")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--parent-artifact", type=Path)
    parser.add_argument("--fold-artifact", type=Path)
    parser.add_argument("--target-cost-receipt", type=Path)
    args = parser.parse_args(argv)

    run_label = str(args.run_label)
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        parser.error("--run-label must use 1-80 ASCII letters, digits, '.', '_' or '-'")
    artifact_root = Path(args.artifact_root)
    fold_id = str(args.fold_id)
    fold_pin = _screen_fold_pin(fold_id)
    contract_root = artifact_root / "research-contracts"
    parent_artifact = (
        Path(args.parent_artifact)
        if args.parent_artifact
        else contract_root / _PARENT_ARTIFACT_NAME
    )
    fold_artifact = (
        Path(args.fold_artifact)
        if args.fold_artifact
        else contract_root / fold_pin.fold_artifact_name
    )
    target_cost_receipt = (
        Path(args.target_cost_receipt)
        if args.target_cost_receipt
        else contract_root / fold_pin.target_cost_artifact_name
    )
    output_dir = artifact_root / KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID / run_label
    if output_dir.exists():
        parser.error("--run-label already has external evidence; choose a new attempt label")

    materializer = load_pinned_kis_daily_joint_event_d1_materializer(
        artifact_root=artifact_root,
        fold_id=fold_id,
        parent_artifact=parent_artifact,
        fold_artifact=fold_artifact,
        market_data_root=Path(args.market_data_root),
    )
    target_adapter = build_kis_daily_joint_event_d1_target_cost_adapter(
        materializer=materializer,
    )
    _attest_target_cost_receipt(
        path=target_cost_receipt,
        artifact_root=artifact_root,
        materializer_identity=materializer.materializer_identity,
        fold_input_identity=materializer.fold_input.fold_input_identity,
        target_cost_identity=target_adapter.target_cost_identity,
        expected_target_cost_receipt_sha256=fold_pin.target_cost_receipt_sha256,
        expected_target_cost_identity=fold_pin.target_cost_identity,
    )
    run = run_kis_daily_joint_event_d1_sequence_screen(
        materializer=materializer,
        target_adapter=target_adapter,
        artifact_root=artifact_root,
        run_label=run_label,
        mode=args.mode,
        repo_root=_REPO_ROOT,
    )
    print(run.summary_path.read_text(encoding="utf-8"))


def _attest_target_cost_receipt(
    *,
    path: Path,
    artifact_root: Path,
    materializer_identity: str,
    fold_input_identity: str,
    target_cost_identity: str,
    expected_target_cost_receipt_sha256: str,
    expected_target_cost_identity: str,
) -> None:
    """Verify the fixed v2 source-safe receipt without exposing its contents."""

    resolved_root = artifact_root.resolve()
    resolved_path = path.resolve(strict=True)
    if (
        path.is_symlink()
        or not resolved_path.is_file()
        or not resolved_path.is_relative_to(resolved_root)
    ):
        raise ValueError("target/cost receipt must stay under the external artifact root")
    encoded = resolved_path.read_bytes()
    if (
        "sha256:" + hashlib.sha256(encoded).hexdigest()
        != expected_target_cost_receipt_sha256
    ):
        raise ValueError("target/cost receipt hash does not match the pinned v2 artifact")
    try:
        document = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("target/cost receipt is invalid") from error
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    if encoded != canonical.encode("utf-8") or not isinstance(document, Mapping):
        raise ValueError("target/cost receipt is not canonical")
    source_fold = document.get("source_fold_input")
    source_materializer = document.get("source_materializer")
    scope = document.get("scope")
    if (
        document.get("target_cost_identity") != expected_target_cost_identity
        or target_cost_identity != expected_target_cost_identity
        or not isinstance(source_fold, Mapping)
        or source_fold.get("fold_input_identity") != fold_input_identity
        or not isinstance(source_materializer, Mapping)
        or source_materializer.get("materializer_identity") != materializer_identity
        or not isinstance(scope, Mapping)
        or scope.get("offline_only") is not True
        or scope.get("target_values_persisted") is not False
        or scope.get("paper_decision_eligible") is not False
    ):
        raise ValueError("target/cost receipt lineage or scope is incompatible")


def _screen_fold_pin(fold_id: str) -> _ScreenFoldPin:
    if not isinstance(fold_id, str):
        raise ValueError("joint D1 sequence screen fold id is invalid")
    try:
        return _SCREEN_FOLD_PINS[fold_id]
    except KeyError as error:
        raise ValueError("joint D1 sequence screen fold id is invalid") from error


if __name__ == "__main__":
    main()

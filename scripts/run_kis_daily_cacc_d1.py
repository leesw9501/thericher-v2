"""Run the fixed CACC-D1 CPU candidate from pinned local research inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from prepare_kis_daily_joint_event_d1_materializer import (
    load_pinned_kis_daily_joint_event_d1_materializer,
)

from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    build_kis_daily_joint_event_d1_target_cost_adapter,
)
from thericher_v2.kis_daily_joint_event_window_contract import DEFAULT_MODEL_ARTIFACT_ROOT
from thericher_v2.research.kis_daily_cacc_d1 import (
    KIS_DAILY_CACC_D1_FOLD_IDS,
    KisDailyCaccD1FoldBinding,
    run_kis_daily_cacc_d1,
)

_DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
_RESEARCH_CONTRACTS_DIRECTORY = "research-contracts"


@dataclass(frozen=True, slots=True)
class _TargetCostPin:
    receipt_name: str
    receipt_sha256: str
    target_cost_identity: str


_TARGET_COST_PINS = {
    "expanding-1": _TargetCostPin(
        receipt_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-1-validation-first-v2.json"
        ),
        receipt_sha256=(
            "sha256:90beea4c501a946dd5502a2b0eb4a06b10a0ef36ed5f70f29c595a17dd6d7486"
        ),
        target_cost_identity=(
            "sha256:2c0ecbb889b8f1660929e87458e4a90d01f2390e41b25ed47e7201ab8a94b842"
        ),
    ),
    "expanding-2": _TargetCostPin(
        receipt_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-2-validation-first-v2.json"
        ),
        receipt_sha256=(
            "sha256:4de77ac80db46b1378c5728473e2f31c04b5c5343ffde8ddf507b9afb16941da"
        ),
        target_cost_identity=(
            "sha256:cd58b52816a7d0a744f8fce42a384091ce8ea9290c73316b699579a1a16291a0"
        ),
    ),
    "expanding-3": _TargetCostPin(
        receipt_name=(
            "snapshot=2026-07-24-qqq-spy-tiingo-events-v1-"
            "d1-target-cost-expanding-3-validation-first-v2.json"
        ),
        receipt_sha256=(
            "sha256:4c389d437ed5c6ad35908dd98e1639e8ab17d41db889a7e5d1d6437c78961560"
        ),
        target_cost_identity=(
            "sha256:5511c3f072e81debe81c39792d6ca4b9500773ebf0d4029b9c7d501286176cc3"
        ),
    ),
}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    args = parser.parse_args(argv)

    artifact_root = Path(args.artifact_root)
    bindings = tuple(
        _load_pinned_fold_binding(
            artifact_root=artifact_root,
            market_data_root=Path(args.market_data_root),
            fold_id=fold_id,
        )
        for fold_id in KIS_DAILY_CACC_D1_FOLD_IDS
    )
    run = run_kis_daily_cacc_d1(
        bindings=bindings,
        artifact_root=artifact_root,
        run_label=str(args.run_label),
        repo_root=Path(__file__).resolve().parents[1],
    )
    print(run.summary_path.read_text(encoding="utf-8"))


def _load_pinned_fold_binding(
    *,
    artifact_root: Path,
    market_data_root: Path,
    fold_id: str,
) -> KisDailyCaccD1FoldBinding:
    pin = _target_cost_pin(fold_id)
    materializer = load_pinned_kis_daily_joint_event_d1_materializer(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        fold_id=fold_id,
    )
    target_adapter = build_kis_daily_joint_event_d1_target_cost_adapter(
        materializer=materializer,
    )
    _attest_target_cost_receipt(
        path=(artifact_root / _RESEARCH_CONTRACTS_DIRECTORY / pin.receipt_name),
        artifact_root=artifact_root,
        materializer_identity=materializer.materializer_identity,
        fold_input_identity=materializer.fold_input.fold_input_identity,
        target_cost_identity=target_adapter.target_cost_identity,
        expected_receipt_sha256=pin.receipt_sha256,
        expected_target_cost_identity=pin.target_cost_identity,
    )
    return KisDailyCaccD1FoldBinding(
        materializer=materializer,
        target_adapter=target_adapter,
    )


def _attest_target_cost_receipt(
    *,
    path: Path,
    artifact_root: Path,
    materializer_identity: str,
    fold_input_identity: str,
    target_cost_identity: str,
    expected_receipt_sha256: str,
    expected_target_cost_identity: str,
) -> None:
    """Verify the pre-existing source-safe v2 receipt without exposing values."""

    resolved_root = Path(artifact_root).resolve()
    resolved_path = Path(path).resolve(strict=True)
    if (
        path.is_symlink()
        or not resolved_path.is_file()
        or not resolved_path.is_relative_to(resolved_root)
    ):
        raise ValueError("CACC-D1 target/cost receipt must stay under the artifact root")
    encoded = resolved_path.read_bytes()
    if "sha256:" + hashlib.sha256(encoded).hexdigest() != expected_receipt_sha256:
        raise ValueError("CACC-D1 target/cost receipt hash does not match the pinned v2 artifact")
    try:
        document = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("CACC-D1 target/cost receipt is invalid") from error
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    source_fold = document.get("source_fold_input") if isinstance(document, Mapping) else None
    source_materializer = (
        document.get("source_materializer") if isinstance(document, Mapping) else None
    )
    scope = document.get("scope") if isinstance(document, Mapping) else None
    if (
        encoded != canonical.encode("utf-8")
        or document.get("target_cost_identity") != expected_target_cost_identity
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
        raise ValueError("CACC-D1 target/cost receipt lineage or scope is incompatible")


def _target_cost_pin(fold_id: str) -> _TargetCostPin:
    try:
        return _TARGET_COST_PINS[fold_id]
    except KeyError as error:
        raise ValueError("CACC-D1 fold id is invalid") from error


if __name__ == "__main__":
    main()

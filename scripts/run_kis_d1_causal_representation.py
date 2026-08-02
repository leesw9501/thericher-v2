"""Run the fixed KIS D1 causal-representation feasibility campaign offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_d1_causal_representation import (
    KIS_D1_CAUSAL_REPRESENTATION_DEFAULT_ATTEMPT_ID,
    KIS_D1_CAUSAL_REPRESENTATION_ID,
    freeze_kis_d1_causal_representation_campaign,
    load_kis_d1_causal_representation_dataset,
    run_kis_d1_causal_representation_cpu_smoke,
    run_kis_d1_causal_representation_cuda,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MARKET_DATA_ROOT = (
    Path("/app/market_data") if Path("/app/market_data").is_dir() else Path(r"D:\market_data")
)
_DEFAULT_ARTIFACT_ROOT = (
    Path("/app/model_artifacts")
    if Path("/app/model_artifacts").is_dir()
    else Path(r"D:\thericher-v2\model-artifacts")
)
_PANEL_NAME = "panel=7e8d6fe54dd5252fc4b9"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cpu-smoke", "cuda"), required=True)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPOSITORY_ROOT)
    parser.add_argument("--attempt-id", default=KIS_D1_CAUSAL_REPRESENTATION_DEFAULT_ATTEMPT_ID)
    args = parser.parse_args(argv)

    market_data_root = Path(args.market_data_root)
    cache_root = market_data_root / "us_equities" / "kis_paper_private" / "daily-nas-history" / "v1"
    panel_root = (
        market_data_root
        / "us_equities"
        / "kis_paper_private"
        / "daily-nas-history-panel"
        / "v1"
    )
    dataset = load_kis_d1_causal_representation_dataset(
        manifest_path=panel_root / _PANEL_NAME / "manifest.json",
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=Path(args.repo_root),
    )
    contract = freeze_kis_d1_causal_representation_campaign(
        dataset,
        artifact_root=Path(args.artifact_root),
        repo_root=Path(args.repo_root),
        code_revision=_code_revision(),
        attempt_id=str(args.attempt_id),
    )
    if args.mode == "cpu-smoke":
        result = run_kis_d1_causal_representation_cpu_smoke(contract)
    else:
        result = run_kis_d1_causal_representation_cuda(contract)
    print(
        json.dumps(
            {
                "campaign_id": KIS_D1_CAUSAL_REPRESENTATION_ID,
                "contract_sha256": contract.contract_sha256,
                "phase": result.phase,
                "status": result.status,
                "device": result.device,
                "steps_completed": result.steps_completed,
                "training_loss_finite": result.training_loss_finite,
                "training_loss_decreased": result.training_loss_decreased,
                "diagnostic_loss_finite": result.diagnostic_loss_finite,
                "summary_sha256": result.summary_sha256,
                "weights_sha256": result.weights_sha256,
                "registry_outcome_sha256": (
                    None
                    if result.registry_outcome is None
                    else result.registry_outcome.record_sha256
                ),
            },
            sort_keys=True,
        )
    )


def _code_revision() -> str:
    module = (
        _REPOSITORY_ROOT
        / "src"
        / "thericher_v2"
        / "research"
        / "kis_d1_causal_representation.py"
    )
    return "sha256:" + hashlib.sha256(module.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()

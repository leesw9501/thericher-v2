"""Run the fixed CPU or CUDA engineering-only Norgate validation target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.norgate_broad_development_artifact import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    default_norgate_broad_development_feature_artifact_dir,
)
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT
from thericher_v2.research.norgate_broad_development_validation import (
    CUDA_JOB_SPECS,
    VALIDATION_VERSION,
    run_norgate_broad_development_cpu_baseline_from_artifact,
    run_norgate_broad_development_cuda_job_from_artifact,
)

DEFAULT_PANEL_SNAPSHOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "norgate_trial_broad_development_panel"
    / "canonical"
    / "ohlcv_1d"
    / "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cpu", "cuda", "cuda-batch"), required=True)
    parser.add_argument("--feature-artifact", type=Path)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--run-id", default=VALIDATION_VERSION)
    parser.add_argument("--job", choices=tuple(item.job_id for item in CUDA_JOB_SPECS))
    parser.add_argument("--code-revision", default="unrecorded")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.mode == "cuda" and args.job is None:
        parser.error("--job is required with --mode cuda")
    if args.mode != "cuda" and args.job is not None:
        parser.error("--job is only valid with --mode cuda")
    feature_artifact = args.feature_artifact or (
        default_norgate_broad_development_feature_artifact_dir(
            DEFAULT_PANEL_SNAPSHOT,
            artifact_root=args.artifact_root,
        )
    )
    common = {
        "artifact_root": args.artifact_root,
        "market_data_root": args.market_data_root,
        "run_id": args.run_id,
        "repo_root": args.repo_root,
        "code_revision": args.code_revision,
    }
    if args.mode == "cpu":
        result = run_norgate_broad_development_cpu_baseline_from_artifact(
            feature_artifact,
            **common,
        )
        print(_cpu_payload(result))
        return
    job_ids = (args.job,) if args.mode == "cuda" else tuple(item.job_id for item in CUDA_JOB_SPECS)
    results = [
        run_norgate_broad_development_cuda_job_from_artifact(
            feature_artifact,
            job_id=job_id,
            **common,
        )
        for job_id in job_ids
    ]
    print(
        json.dumps(
            {"mode": args.mode, "jobs": [_cuda_payload(result) for result in results]},
            sort_keys=True,
        )
    )


def _cpu_payload(result: object) -> str:
    return json.dumps(
        {
            "mode": "cpu",
            "summary_path": str(result.summary_path),
            "summary_sha256": result.summary_sha256,
            "artifact_hash": result.artifact_hash,
            "contract_hash": result.contract_hash,
        },
        sort_keys=True,
    )


def _cuda_payload(result: object) -> dict[str, object]:
    return {
        "job_id": result.job_id,
        "summary_path": str(result.summary_path),
        "summary_sha256": result.summary_sha256,
        "checkpoint_path": str(result.checkpoint_path),
        "checkpoint_sha256": result.checkpoint_sha256,
        "prediction_path": str(result.prediction_path),
        "prediction_sha256": result.prediction_sha256,
        "review_required": result.review_required,
    }


if __name__ == "__main__":
    main()

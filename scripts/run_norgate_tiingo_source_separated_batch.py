"""Run the one fixed offline CPU or CUDA source-separated engineering batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from thericher_v2.data.norgate_broad_development_artifact import DEFAULT_MODEL_ARTIFACT_ROOT
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT
from thericher_v2.research.norgate_tiingo_source_separated_batch import (
    CUDA_JOB_SPECS,
    DEFAULT_COHORT_ARTIFACT_DIR,
    DEFAULT_CONTRACT_ARTIFACT_DIR,
    DEFAULT_FEATURE_ARTIFACT_DIR,
    load_verified_norgate_tiingo_source_separated_batch_dataset,
    run_norgate_tiingo_source_separated_cpu_baseline,
    run_norgate_tiingo_source_separated_cuda_job,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--job", choices=tuple(item.job_id for item in CUDA_JOB_SPECS))
    parser.add_argument("--contract-artifact", type=Path, default=DEFAULT_CONTRACT_ARTIFACT_DIR)
    parser.add_argument("--cohort-artifact", type=Path, default=DEFAULT_COHORT_ARTIFACT_DIR)
    parser.add_argument("--feature-artifact", type=Path, default=DEFAULT_FEATURE_ARTIFACT_DIR)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    if args.mode == "cuda" and args.job is None:
        parser.error("--job is required with --mode cuda")
    if args.mode == "cpu" and args.job is not None:
        parser.error("--job is only valid with --mode cuda")

    dataset = load_verified_norgate_tiingo_source_separated_batch_dataset(
        contract_artifact_dir=args.contract_artifact,
        cohort_artifact_dir=args.cohort_artifact,
        feature_artifact_dir=args.feature_artifact,
        artifact_root=args.artifact_root,
        market_data_root=args.market_data_root,
        repo_root=args.repo_root,
    )
    common = {
        "artifact_root": args.artifact_root,
        "repo_root": args.repo_root,
        "code_revision": args.code_revision,
    }
    if args.mode == "cpu":
        result = run_norgate_tiingo_source_separated_cpu_baseline(dataset, **common)
        print(
            json.dumps(
                {
                    "mode": "cpu",
                    "summary_path": str(result.summary_path),
                    "summary_sha256": result.summary_sha256,
                    "contract_hash": result.contract_hash,
                },
                sort_keys=True,
            )
        )
        return

    result = run_norgate_tiingo_source_separated_cuda_job(
        dataset,
        job_id=args.job,
        **common,
    )
    print(
        json.dumps(
            {
                "mode": "cuda",
                "job_id": result.job_id,
                "summary_path": str(result.summary_path),
                "summary_sha256": result.summary_sha256,
                "checkpoint_path": str(result.checkpoint_path),
                "checkpoint_sha256": result.checkpoint_sha256,
                "prediction_path": str(result.prediction_path),
                "prediction_sha256": result.prediction_sha256,
                "review_required": result.review_required,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Freeze and run one offline, non-promoting Norgate D1 development campaign."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.data.norgate_broad_development_artifact import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    default_norgate_broad_development_feature_artifact_dir,
)
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT
from thericher_v2.research.norgate_broad_development_validation import (
    NORGATE_BROAD_OPPORTUNITY_DEVELOPMENT_CAMPAIGN,
    NORGATE_BROAD_OPPORTUNITY_DEVELOPMENT_VERSION,
    OPPORTUNITY_CUDA_JOB_SPECS,
    freeze_norgate_broad_development_campaign_from_artifact,
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


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("freeze", "cpu", "cuda"), required=True)
    parser.add_argument("--feature-artifact", type=Path)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_MODEL_ARTIFACT_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--run-id", default=NORGATE_BROAD_OPPORTUNITY_DEVELOPMENT_VERSION)
    parser.add_argument("--job", choices=tuple(item.job_id for item in OPPORTUNITY_CUDA_JOB_SPECS))
    parser.add_argument("--code-revision", default="unrecorded")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if args.mode == "cuda" and args.job is None:
        parser.error("--job is required with --mode cuda")
    if args.mode != "cuda" and args.job is not None:
        parser.error("--job is only valid with --mode cuda")

    feature_artifact = args.feature_artifact
    if feature_artifact is None:
        feature_artifact = default_norgate_broad_development_feature_artifact_dir(
            DEFAULT_PANEL_SNAPSHOT,
            artifact_root=args.artifact_root,
        )
    common = {
        "artifact_root": args.artifact_root,
        "market_data_root": args.market_data_root,
        "run_id": args.run_id,
        "campaign_id": NORGATE_BROAD_OPPORTUNITY_DEVELOPMENT_CAMPAIGN.campaign_id,
        "repo_root": args.repo_root,
        "code_revision": args.code_revision,
    }
    if args.mode == "freeze":
        result = freeze_norgate_broad_development_campaign_from_artifact(
            feature_artifact,
            **common,
        )
        print(
            json.dumps(
                {
                    "mode": "freeze",
                    "campaign_id": result.campaign_id,
                    "contract_path": str(result.contract_path),
                    "contract_sha256": result.contract_sha256,
                    "artifact_hash": result.artifact_hash,
                    "derived_contract_hash": result.derived_contract_hash,
                },
                sort_keys=True,
            )
        )
        return
    if args.mode == "cpu":
        result = run_norgate_broad_development_cpu_baseline_from_artifact(
            feature_artifact,
            **common,
        )
        print(
            json.dumps(
                {
                    "mode": "cpu",
                    "summary_path": str(result.summary_path),
                    "summary_sha256": result.summary_sha256,
                    "artifact_hash": result.artifact_hash,
                    "contract_hash": result.contract_hash,
                },
                sort_keys=True,
            )
        )
        return

    result = run_norgate_broad_development_cuda_job_from_artifact(
        feature_artifact,
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

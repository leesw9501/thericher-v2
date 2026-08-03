"""Run the fixed native-ragged CPU campaign from local immutable receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from thericher_v2.data import (
    kis_mtf_profiled_prospective_observer as forward_outcome_observer,
)
from thericher_v2.data.kis_intraday_mtf_availability import (
    load_kis_intraday_mtf_availability_catalogs,
)
from thericher_v2.research import (
    profiled_mtf_forward_campaign_readiness as readiness,
)
from thericher_v2.research import (
    profiled_mtf_forward_ragged_sequence_cpu_campaign as ragged_campaign,
)
from thericher_v2.research import (
    profiled_mtf_forward_supervised_dataset as supervised_dataset,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/intraday")
    _DEFAULT_MARKET_DATA_ROOT = Path("/app/market_data")
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
    _DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
    _DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

_DEFAULT_DATASET_ATTEMPT_ID = "local-cache-r3"
_DEFAULT_READINESS_ATTEMPT_ID = "local-cache-r3"
_DEFAULT_CAMPAIGN_ATTEMPT_ID = "local-cache-r1"
_RECOVERY_EXIT_CODE = 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--dataset-attempt-id", default=_DEFAULT_DATASET_ATTEMPT_ID)
    parser.add_argument("--readiness-attempt-id", default=_DEFAULT_READINESS_ATTEMPT_ID)
    parser.add_argument("--attempt-id", default=_DEFAULT_CAMPAIGN_ATTEMPT_ID)
    parser.add_argument("--code-revision-sha256")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    readiness_receipt_path = (
        args.artifact_root
        / "research"
        / readiness.PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID
        / args.readiness_attempt_id
        / "readiness-receipt.json"
    )
    dataset_receipt_path = (
        args.artifact_root
        / "research"
        / supervised_dataset.PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID
        / args.dataset_attempt_id
        / "dataset-receipt.json"
    )
    try:
        readiness_receipt = readiness.load_profiled_mtf_forward_campaign_readiness_receipt(
            readiness_receipt_path,
            repo_root=args.repo_root,
        )
        catalogs = load_kis_intraday_mtf_availability_catalogs(
            cache_root=args.cache_root,
            repo_root=args.repo_root,
        )
        observer_contract = (
            forward_outcome_observer.freeze_kis_mtf_profiled_prospective_observer_contract(
                historical_catalogs=catalogs,
                code_revision=readiness_receipt.policy.code_revision_sha256,
            )
        )
        outcome_contract = (
            forward_outcome_observer.freeze_kis_mtf_profiled_forward_outcome_contract(
                observer_contract
            )
        )
        catalog = forward_outcome_observer.load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
            artifact_root=args.artifact_root,
            market_data_root=args.market_data_root,
            repo_root=args.repo_root,
            contract=outcome_contract,
        )
        dataset_receipt = supervised_dataset.load_profiled_mtf_forward_supervised_dataset_receipt(
            dataset_receipt_path,
            market_data_root=args.market_data_root,
            repo_root=args.repo_root,
        )
        if dataset_receipt.policy.readiness_receipt_sha256 != readiness_receipt.receipt_sha256:
            raise ValueError("supervised dataset readiness receipt changed")
        materialization = (
            supervised_dataset.load_profiled_mtf_forward_supervised_dataset_materialization(
                dataset_receipt,
                catalog=catalog,
                repo_root=args.repo_root,
            )
        )
        policy = ragged_campaign.freeze_profiled_mtf_forward_ragged_sequence_cpu_campaign_policy(
            dataset_receipt,
            code_revision_sha256=args.code_revision_sha256 or _campaign_code_revision_sha256(),
        )
        result = ragged_campaign.run_profiled_mtf_forward_ragged_sequence_cpu_campaign(
            policy,
            dataset_receipt=dataset_receipt,
            materialization=materialization,
        )
        receipt = ragged_campaign.write_profiled_mtf_forward_ragged_sequence_cpu_campaign_receipt(
            result,
            policy=policy,
            artifact_root=args.artifact_root,
            repo_root=args.repo_root,
            attempt_id=args.attempt_id,
        )
    except (OSError, ValueError):
        print(
            json.dumps(
                {
                    "campaign_id": (
                        ragged_campaign.PROFILED_MTF_FORWARD_RAGGED_SEQUENCE_CPU_CAMPAIGN_ID
                    ),
                    "status": "input_unavailable",
                    "scope": {"source_safe_only": True},
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE
    print(
        json.dumps(
            {**result.safe_payload(), "receipt_sha256": receipt.receipt_sha256},
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


def _campaign_code_revision_sha256() -> str:
    source = b"".join(
        path.read_bytes()
        for path in (
            Path(ragged_campaign.__file__),
            Path(supervised_dataset.__file__),
            Path(readiness.__file__),
            Path(forward_outcome_observer.__file__),
        )
    )
    return "sha256:" + hashlib.sha256(source).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

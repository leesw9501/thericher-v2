"""Reattest and materialize the first profiled-MTF supervised target contract."""

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

_DEFAULT_READINESS_ATTEMPT_ID = "local-cache-r3"
_DEFAULT_DATASET_ATTEMPT_ID = "local-cache-r1"
_RECOVERY_EXIT_CODE = 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--readiness-attempt-id", default=_DEFAULT_READINESS_ATTEMPT_ID)
    parser.add_argument("--attempt-id", default=_DEFAULT_DATASET_ATTEMPT_ID)
    parser.add_argument("--code-revision-sha256")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    dataset_code_revision_sha256 = args.code_revision_sha256 or _dataset_code_revision_sha256()
    readiness_path = (
        args.artifact_root
        / "research"
        / readiness.PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID
        / args.readiness_attempt_id
        / "readiness-receipt.json"
    )
    try:
        catalogs = load_kis_intraday_mtf_availability_catalogs(
            cache_root=args.cache_root,
            repo_root=args.repo_root,
        )
        observer_contract = (
            forward_outcome_observer.freeze_kis_mtf_profiled_prospective_observer_contract(
                historical_catalogs=catalogs,
                code_revision=_readiness_code_revision_sha256(),
            )
        )
        outcome_contract = (
            forward_outcome_observer.freeze_kis_mtf_profiled_forward_outcome_contract(
                observer_contract
            )
        )
        readiness_receipt = readiness.load_profiled_mtf_forward_campaign_readiness_receipt(
            readiness_path,
            repo_root=args.repo_root,
        )
        catalog = forward_outcome_observer.load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
            artifact_root=args.artifact_root,
            market_data_root=args.market_data_root,
            repo_root=args.repo_root,
            contract=outcome_contract,
        )
        policy = supervised_dataset.freeze_profiled_mtf_forward_supervised_dataset_policy(
            readiness_receipt,
            code_revision_sha256=dataset_code_revision_sha256,
        )
        result = supervised_dataset.materialize_profiled_mtf_forward_supervised_dataset(
            policy,
            receipt=readiness_receipt,
            catalog=catalog,
            market_data_root=args.market_data_root,
            repo_root=args.repo_root,
        )
        receipt = supervised_dataset.write_profiled_mtf_forward_supervised_dataset_receipt(
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
                    "dataset_id": supervised_dataset.PROFILED_MTF_FORWARD_SUPERVISED_DATASET_ID,
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
            {
                **result.safe_payload(),
                "receipt_sha256": receipt.receipt_sha256,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


def _readiness_code_revision_sha256() -> str:
    source = b"".join(
        path.read_bytes()
        for path in (
            _REPO_ROOT / "scripts" / "run_profiled_mtf_forward_campaign_readiness.py",
            Path(readiness.__file__),
            Path(forward_outcome_observer.__file__),
        )
    )
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _dataset_code_revision_sha256() -> str:
    source = b"".join(
        path.read_bytes()
        for path in (
            Path(__file__),
            Path(readiness.__file__),
            Path(supervised_dataset.__file__),
            Path(forward_outcome_observer.__file__),
        )
    )
    return "sha256:" + hashlib.sha256(source).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

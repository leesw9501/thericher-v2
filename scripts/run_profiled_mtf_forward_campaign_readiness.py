"""Reattest the local forward-outcome inventory into a source-safe readiness receipt."""

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
from thericher_v2.research import profiled_mtf_forward_campaign_readiness as readiness

_REPO_ROOT = Path(__file__).resolve().parents[1]
if _REPO_ROOT == Path("/app"):
    _DEFAULT_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/intraday")
    _DEFAULT_MARKET_DATA_ROOT = Path("/app/market_data")
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday")
    _DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
    _DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

_RECOVERY_EXIT_CODE = 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--market-data-root", type=Path, default=_DEFAULT_MARKET_DATA_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--attempt-id", default="local-cache-r1")
    parser.add_argument("--code-revision-sha256")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    code_revision_sha256 = args.code_revision_sha256 or _code_revision_sha256()
    try:
        catalogs = load_kis_intraday_mtf_availability_catalogs(
            cache_root=args.cache_root,
            repo_root=args.repo_root,
        )
        observer_contract = (
            forward_outcome_observer.freeze_kis_mtf_profiled_prospective_observer_contract(
                historical_catalogs=catalogs,
                code_revision=code_revision_sha256,
            )
        )
        outcome_contract = (
            forward_outcome_observer.freeze_kis_mtf_profiled_forward_outcome_contract(
                observer_contract
            )
        )
        inventory = forward_outcome_observer.inspect_kis_mtf_profiled_forward_outcome_inventory(
            artifact_root=args.artifact_root,
            market_data_root=args.market_data_root,
            repo_root=args.repo_root,
            contract=outcome_contract,
        )
        policy = readiness.freeze_profiled_mtf_forward_campaign_readiness_policy(
            forward_outcome_contract_sha256=outcome_contract.contract_sha256,
            code_revision_sha256=code_revision_sha256,
        )
        result = readiness.evaluate_profiled_mtf_forward_campaign_readiness(policy, inventory)
        receipt = readiness.write_profiled_mtf_forward_campaign_readiness_receipt(
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
                    "campaign_id": readiness.PROFILED_MTF_FORWARD_CAMPAIGN_READINESS_ID,
                    "status": "input_unavailable",
                    "scope": {"source_safe_inventory_only": True},
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return _RECOVERY_EXIT_CODE
    payload = {
        **result.safe_payload(),
        "receipt_sha256": receipt.receipt_sha256,
    }
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


def _code_revision_sha256() -> str:
    source = (
        Path(__file__).read_bytes()
        + Path(readiness.__file__).read_bytes()
        + Path(forward_outcome_observer.__file__).read_bytes()
    )
    return "sha256:" + hashlib.sha256(source).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

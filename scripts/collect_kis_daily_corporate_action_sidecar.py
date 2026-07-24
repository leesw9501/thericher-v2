"""Collect a bounded, price-free Tiingo event sidecar for the KIS QQQ/SPY panel."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_daily_corporate_actions import (
    DEFAULT_MARKET_DATA_ROOT,
    build_kis_daily_corporate_action_snapshot,
    default_kis_daily_corporate_action_snapshot_dir,
    fetch_kis_daily_tiingo_corporate_action_responses,
)
from thericher_v2.data.kis_paper_daily import load_kis_paper_private_daily_catalog
from thericher_v2.research.kis_daily_event_mask_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    build_kis_daily_event_mask_contract,
    write_kis_daily_event_mask_contract,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--contract-destination", type=Path)
    args = parser.parse_args()

    catalog = load_kis_paper_private_daily_catalog(
        target_keys=("QQQ/NAS/MODP=0", "SPY/AMS/MODP=0"),
        repo_root=Path.cwd(),
    )
    sessions = catalog.common_sessions
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "planned_no_network",
                    "symbols": ["QQQ", "SPY"],
                    "start_session": sessions[0].isoformat(),
                    "end_session": sessions[-1].isoformat(),
                    "session_count": len(sessions),
                },
                sort_keys=True,
            )
        )
        return

    retrieved_at = datetime.now(UTC)
    destination = args.destination or default_kis_daily_corporate_action_snapshot_dir(
        retrieved_at.date()
    )
    responses = fetch_kis_daily_tiingo_corporate_action_responses(
        env_path=Path(".env"),
        start_session=sessions[0],
        end_session=sessions[-1],
    )
    sidecar = build_kis_daily_corporate_action_snapshot(
        destination=destination,
        raw_responses=responses,
        catalog=catalog,
        retrieved_at_utc=retrieved_at,
        market_data_root=DEFAULT_MARKET_DATA_ROOT,
        repo_root=Path.cwd(),
    )
    contract = build_kis_daily_event_mask_contract(catalog=catalog, sidecar=sidecar)
    contract_destination = args.contract_destination or (
        DEFAULT_MODEL_ARTIFACT_ROOT
        / "research-contracts"
        / f"{sidecar.snapshot_dir.name}-event-mask.json"
    )
    receipt = write_kis_daily_event_mask_contract(
        destination=contract_destination,
        contract=contract,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "status": "qualified_retrospective_price_return_only",
                "snapshot_dir": str(sidecar.snapshot_dir),
                "dataset_hash": sidecar.dataset_hash,
                "manifest_hash": sidecar.manifest_hash,
                "event_counts": sidecar.event_counts,
                "contract_path": str(receipt.path),
                "contract_hash": receipt.content_hash,
            },
            default=dict,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

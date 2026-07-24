"""Freeze the offline QQQ/SPY KIS daily event-boundary audit contract."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_daily_corporate_actions import load_kis_daily_corporate_action_snapshot
from thericher_v2.data.kis_paper_daily import load_kis_paper_private_daily_catalog
from thericher_v2.research.kis_daily_event_mask_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    build_kis_daily_event_boundary_audit,
    write_kis_daily_event_boundary_audit,
)

_SIDECAR_DIR = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-corporate-actions/"
    "snapshot=2026-07-24-qqq-spy-tiingo-events-v1"
)
_SIDECAR_DATASET_HASH = "sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3"
_SIDECAR_MANIFEST_HASH = "sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    catalog = load_kis_paper_private_daily_catalog(
        target_keys=("QQQ/NAS/MODP=0", "SPY/AMS/MODP=0"),
        repo_root=Path.cwd(),
    )
    sidecar = load_kis_daily_corporate_action_snapshot(
        _SIDECAR_DIR,
        catalog=catalog,
        expected_dataset_hash=_SIDECAR_DATASET_HASH,
        expected_manifest_hash=_SIDECAR_MANIFEST_HASH,
        repo_root=Path.cwd(),
    )
    audit = build_kis_daily_event_boundary_audit(
        catalog=catalog,
        sidecar=sidecar,
        created_at_utc=datetime.now(UTC),
    )
    destination = args.destination or (
        DEFAULT_MODEL_ARTIFACT_ROOT
        / "research-contracts"
        / f"{sidecar.snapshot_dir.name}-event-boundary-audit.json"
    )
    artifact = write_kis_daily_event_boundary_audit(
        destination=destination,
        audit=audit,
        repo_root=Path.cwd(),
    )
    print(
        json.dumps(
            {
                "status": audit.status,
                "unqualified_reasons": audit.unqualified_reasons,
                "mask_identity": audit.mask_identity(),
                "partition_identity": audit.partition_identity(),
                "audit_counts": audit.audit_counts,
                "artifact_path": str(artifact.path),
                "artifact_hash": artifact.content_hash,
            },
            default=dict,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Run one source-local KIS broad-D1 event-censored CPU preflight."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.kis_broad_d1_event_censored_cpu_preflight import (
    KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ARTIFACT_ROOT,
    KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
    run_kis_broad_d1_event_censored_cpu_preflight,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if _REPOSITORY_ROOT == Path("/app"):
    _DEFAULT_CACHE_ROOT = Path("/app/market_data/us_equities/kis_paper_private/daily-nas-broad/v1")
    _DEFAULT_PANEL_ROOT = Path(
        "/app/market_data/us_equities/kis_paper_private/daily-nas-broad-panel/v1"
    )
    _DEFAULT_ARTIFACT_ROOT = Path("/app/model_artifacts")
else:
    _DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\daily-nas-broad\v1")
    _DEFAULT_PANEL_ROOT = Path(
        r"D:\market_data\us_equities\kis_paper_private\daily-nas-broad-panel\v1"
    )
    _DEFAULT_ARTIFACT_ROOT = KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ARTIFACT_ROOT


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--materialization-receipt-path", type=Path, required=True)
    parser.add_argument("--geometry-audit-receipt-path", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=_DEFAULT_CACHE_ROOT)
    parser.add_argument("--panel-root", type=Path, default=_DEFAULT_PANEL_ROOT)
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-label", required=True)
    parser.add_argument(
        "--review-status",
        choices=("uncertain", "supported-with-limits", "review_unavailable"),
        required=True,
    )
    args = parser.parse_args(argv)
    try:
        result = run_kis_broad_d1_event_censored_cpu_preflight(
            manifest_path=args.manifest_path,
            materialization_receipt_path=args.materialization_receipt_path,
            geometry_audit_receipt_path=args.geometry_audit_receipt_path,
            cache_root=args.cache_root,
            panel_root=args.panel_root,
            artifact_root=args.artifact_root,
            run_label=args.run_label,
            review_status=args.review_status,
            repo_root=_REPOSITORY_ROOT,
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        print(
            json.dumps(
                {
                    "kind": KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
                    "status": "input_or_runtime_unavailable",
                },
                sort_keys=True,
            )
        )
        return 20
    print(
        json.dumps(
            {
                "kind": KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
                "status": result.status,
                "receipt_sha256": result.receipt_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

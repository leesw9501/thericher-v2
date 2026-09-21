"""Metadata-only freeze or explicitly dispatched offline DEVELOPMENT comparison."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from thericher_v2.research.firstrate_m5_open_open_dev_20260921 import FAMILY, freeze, run_frozen


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--market-data-root", type=Path, default=Path(r"D:\market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path(r"D:\thericher-v2\model-artifacts")
    )
    args = parser.parse_args(argv)
    if args.run and not args.contract_sha256:
        parser.error("--run requires --contract-sha256 from the reviewed freeze")
    if args.freeze and args.contract_sha256:
        parser.error("--contract-sha256 is used only with --run")
    try:
        if args.freeze:
            digest = freeze(artifact_root=args.artifact_root, run_label=args.run_label)
            result = {"family": FAMILY, "status": "frozen_metadata_only", "contract_sha256": digest}
        else:
            summary = run_frozen(
                market_data_root=args.market_data_root,
                artifact_root=args.artifact_root,
                run_label=args.run_label,
                contract_sha256=args.contract_sha256,
            )
            result = {
                "family": FAMILY,
                "status": summary["status"],
                "evidence_grade": "DEVELOPMENT_ONLY_ALREADY_SEEN",
                "promotion": False,
            }
    except (OSError, ValueError):
        result = {"family": FAMILY, "status": "offline_contract_or_namespace_unavailable"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"frozen_metadata_only", "development_complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

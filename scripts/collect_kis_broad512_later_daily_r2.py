"""Inert by default; exact-plan isolated fixed512 later collection command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thericher_v2.data import kis_broad512_later_refresh_r2 as r  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--plan", type=Path, default=r.PREPARATION / "plan.json")
    parser.add_argument("--pin")
    parser.add_argument("--epoch", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--receipt", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        r.require(args.plan.absolute() == (r.PREPARATION / "plan.json").absolute(), "plan_path")
        if args.prepare:
            plan = r.prepare_plan()
            r.save(args.plan, plan)
            result = {
                "status": "source_prepared_no_acquisition",
                "plan_sha256": r.attest(args.plan),
                "target_count": 512,
                "calendar_count": 71,
                "context_sessions": 21,
                "score_sessions": 50,
                "actual_acquisition": False,
            }
        elif args.execute or args._worker:
            r.require(args.pin is not None, "explicit_plan_pin_required")
            r.attest(args.plan, args.pin)
            plan = r.document(r.read(args.plan))
            if args._worker:
                r.require(args.epoch is not None and args.receipt is not None, "worker_control")
                r.plain(args.receipt, r.PREPARATION)
                return r.worker(plan, args.pin, args.epoch, args.receipt)
            result = r.execute(plan, args.pin)
        else:
            result = {"status": "inert", "actual_acquisition": False}
    except Exception:
        result = {"status": "command_rejected", "category": "invalid_source_or_control"}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return (
        0
        if result["status"]
        in {"inert", "source_prepared_no_acquisition", "fresh_later_numeric_view_serialized"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

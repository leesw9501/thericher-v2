"""Freeze or run the single CPU-only retained-model nominal-hurdle comparison."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import tempfile
from pathlib import Path

from thericher_v2.research import firstrate_h30_fixed_hurdle as s
from thericher_v2.research.campaign_registry import register_campaign_outcome


def interrupt(*_):
    raise KeyboardInterrupt


def dispatch(args):
    s.verify(args.artifact_root, args.contract_sha256)
    output = s.h30.run_directory(args.artifact_root, s.NAME)
    supervise = runpy.run_path(
        str(s.h30.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
    )["supervise"]
    with (output / "started.json").open("xb") as handle:
        handle.write(
            s.h30.encode(
                {
                    "name": s.NAME,
                    "contract_sha256": args.contract_sha256,
                    "parent_pid": os.getpid(),
                    "hard_timeout_seconds": s.SECONDS,
                }
            )
        )
    result, job = s.failure(args.contract_sha256, "worker_failed_or_timed_out"), None
    with tempfile.TemporaryDirectory(prefix="cpu-job-", dir=output) as temporary:
        path = Path(temporary) / "result.json"
        try:
            job = supervise(
                s.worker,
                (args.artifact_root, args.market_data_root, args.contract_sha256, path),
                seconds=s.SECONDS,
                name=s.NAME,
            )
            if not job["timed_out"] and job["exit_code"] == 0 and path.is_file():
                candidate = json.loads(path.read_bytes())
                if candidate.get("status") == "complete":
                    s.validate_result(candidate, args.contract_sha256)
                    result = candidate
                elif candidate == s.failure(args.contract_sha256, candidate.get("reason")):
                    result = candidate
        except KeyboardInterrupt:
            result = s.failure(args.contract_sha256, "execution_preempted")
        except Exception:
            result = s.failure(args.contract_sha256, "worker_result_invalid")
    result["job"] = job
    raw = s.h30.encode(result)
    with (output / "summary.json").open("xb") as handle:
        handle.write(raw)
    register_campaign_outcome(
        contract_hash=args.contract_sha256,
        outcome_class="non_promoting_completed"
        if result["status"] == "complete"
        else "non_promoting_failed",
        outcome_reference_sha256=s.h30.digest(raw),
        artifact_root=args.artifact_root,
        repo_root=s.h30.REPO,
    )
    return {
        "status": result["status"],
        "reason": result.get("reason"),
        "contract_sha256": args.contract_sha256,
        "summary_sha256": s.h30.digest(raw),
        "cells": len(result["cells"]),
        "models": len(result["models"]),
        "job": job,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--contract-sha256")
    parser.add_argument("--artifact-root", type=Path, default=Path("/app/model_artifacts"))
    parser.add_argument("--market-data-root", type=Path, default=Path("/app/market_data"))
    args = parser.parse_args(argv)
    if bool(args.run) != bool(args.contract_sha256):
        parser.error("--contract-sha256 is required only for --run")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        result = (
            {"status": "frozen_metadata_only", "contract_sha256": s.freeze(args.artifact_root)}
            if args.freeze
            else dispatch(args)
        )
    except (Exception, KeyboardInterrupt):
        result = {"status": "dispatch_unavailable", "raw_error_suppressed": True}
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("complete", "frozen_metadata_only") else 1


if __name__ == "__main__":
    raise SystemExit(main())

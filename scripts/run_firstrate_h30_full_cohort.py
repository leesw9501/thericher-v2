"""Freeze or supervise one fixed H30 full-cohort DEVELOPMENT phase."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import tempfile
from contextlib import nullcontext
from pathlib import Path

from thericher_v2.research import firstrate_h30_full_cohort as s
from thericher_v2.research.campaign_registry import register_campaign_outcome
from thericher_v2.research.engine_research_agent import GpuFileLock, resolve_agent_root


def interrupt(*_):
    raise KeyboardInterrupt


def dispatch(args):
    output, *_ = s.verify(args.artifact_root, args.contract_sha256)
    supervise = runpy.run_path(
        str(s.h30.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
    )["supervise"]
    lock = (
        GpuFileLock(resolve_agent_root(args.artifact_root) / "locks/gpu.lock")
        if args.phase == "cuda"
        else nullcontext()
    )
    with lock:
        with (output / f"{args.phase}-started.json").open("xb") as handle:
            handle.write(
                s.h30.encode(
                    {
                        "name": s.NAME,
                        "parent_pid": os.getpid(),
                        "contract_sha256": args.contract_sha256,
                        "hard_timeout_seconds": s.SECONDS[args.phase],
                    }
                )
            )
        with tempfile.TemporaryDirectory(prefix=f"{args.phase}-job-", dir=output) as temporary:
            path = Path(temporary) / "result.json"
            result = s.failure(args.phase, args.contract_sha256, "worker_failed_or_timed_out")
            job = None
            try:
                job = supervise(
                    s.worker,
                    (
                        args.artifact_root,
                        args.market_data_root,
                        args.contract_sha256,
                        args.phase,
                        args.cpu_summary_sha256,
                        path,
                    ),
                    seconds=s.SECONDS[args.phase],
                    name=s.NAME,
                )
                if not job["timed_out"] and job["exit_code"] == 0 and path.is_file():
                    candidate = json.loads(path.read_bytes())
                    s.validate_result(candidate, args.phase, args.contract_sha256)
                    if args.phase == "cuda":
                        refs = candidate.get("models", [])
                        s.require(
                            [tuple(r[k] for k in s.d.IDENTITY) for r in refs] == list(s.KEYS),
                            "model_matrix",
                        )
                        for ref in refs:
                            s.load_model(Path(temporary) / "models", ref, args.contract_sha256)
                        s.require(not (output / "models").exists(), "model_namespace_used")
                        (Path(temporary) / "models").rename(output / "models")
                    result = candidate
            except KeyboardInterrupt:
                result = s.failure(args.phase, args.contract_sha256, "execution_preempted")
            except Exception:
                result = s.failure(args.phase, args.contract_sha256, "worker_result_invalid")
            result["job"] = job
            raw = s.h30.encode(result)
            with (output / f"{args.phase}-summary.json").open("xb") as handle:
                handle.write(raw)
    if args.phase == "cuda" or result["status"] != "complete":
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
        "phase": args.phase,
        "contract_sha256": args.contract_sha256,
        "summary_sha256": s.h30.digest(raw),
        "cells": len(result["cells"]),
        "models": len(result.get("models", [])),
        "job": job,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--phase", choices=("cpu", "cuda"))
    parser.add_argument("--contract-sha256")
    parser.add_argument("--cpu-summary-sha256")
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    if bool(args.phase) != bool(args.contract_sha256):
        parser.error("--contract-sha256 is required only for a phase")
    if (args.phase == "cuda") != bool(args.cpu_summary_sha256):
        parser.error("--cpu-summary-sha256 is required only for CUDA")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
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

"""Supervise the fixed TRAIN-only learnability diagnostic, never an evaluation."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import tempfile
from pathlib import Path

from thericher_v2.research import firstrate_h30_train_learnability as study
from thericher_v2.research.engine_research_agent import GpuFileLock, resolve_agent_root


def interrupt(*_):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--contract-sha256")
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    h30 = study.h30
    scope = study.contract()
    scope_hash = h30.digest(h30.encode(scope))
    if args.describe:
        print(json.dumps({"contract": scope, "sha256": scope_hash}, sort_keys=True))
        return 0
    old_signal = signal.signal(signal.SIGTERM, interrupt)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    try:
        study.require(scope_hash == args.contract_sha256, "contract_changed")
        output = h30.run_directory(args.artifact_root, study.NAME)
        supervise = runpy.run_path(
            str(h30.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
        )["supervise"]
        with GpuFileLock(resolve_agent_root(args.artifact_root) / "locks/gpu.lock"):
            output.mkdir(parents=True, exist_ok=False)
            with tempfile.TemporaryDirectory(prefix="job-", dir=output) as temporary:
                path = Path(temporary) / "result.json"
                result = study.failure(scope_hash, "worker_failed_or_timed_out")
                try:
                    job = supervise(
                        study.worker,
                        (args.artifact_root, args.market_data_root, scope_hash, path),
                        seconds=study.SECONDS,
                        name=study.NAME,
                    )
                    if not job["timed_out"] and job["exit_code"] == 0 and path.is_file():
                        candidate = json.loads(path.read_bytes())
                        keys = [(f["arm"], f["seed"]) for f in candidate.get("fits", [])]
                        valid = (
                            candidate.get("status") == "complete"
                            and keys == list(study.KEYS)
                            and all(f["updates"] == study.UPDATES for f in candidate["fits"])
                        )
                        if candidate.get("contract_sha256") == scope_hash and valid:
                            result = candidate
                        elif (
                            candidate.get("contract_sha256") == scope_hash
                            and candidate.get("status") == "failed_all4"
                            and not keys
                        ):
                            result = study.failure(scope_hash, candidate["reason"])
                except KeyboardInterrupt:
                    result = study.failure(scope_hash, "execution_preempted")
                if result["status"] == "complete":
                    path.rename(output / "summary.json")  # Report construction was supervised too.
                else:
                    with (output / "summary.json").open("xb") as handle:
                        handle.write(h30.encode(result))
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "fit_count": len(result["fits"]),
                    "contract_sha256": scope_hash,
                },
                sort_keys=True,
            )
        )
        return 0 if result["status"] == "complete" else 1
    except (Exception, KeyboardInterrupt):
        print(json.dumps({"status": "dispatch_unavailable", "raw_error_suppressed": True}))
        return 1
    finally:
        signal.signal(signal.SIGTERM, old_signal)


if __name__ == "__main__":
    raise SystemExit(main())

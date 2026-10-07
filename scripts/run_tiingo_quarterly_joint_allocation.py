"""Static plan, bounded CPU run, read-only replay, or pinned registry-only recovery."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import time
from pathlib import Path

from thericher_v2.research import tiingo_quarterly_joint_allocation as study
from thericher_v2.research.campaign_registry import register_campaign_outcome


def supervise(target, arguments, *, seconds):
    existing = runpy.run_path(str(study.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    return existing["supervise"](target, arguments, seconds=seconds, name=study.NAME)


def dispatch(artifact_root, market_data_root, pin):
    deadline = time.monotonic() + study.SECONDS
    output, contract = study.verify(artifact_root, market_data_root, pin)
    study.require(
        {p.name for p in output.iterdir()} == {"precommit.json"}, "attempt_already_exists"
    )
    study.register_contract(artifact_root, contract, pin)
    study.atomic_new(output / "started.json", {"contract_sha256": pin})
    result = study.failure(contract, pin, "worker_failed")
    try:
        path = output / "worker-result.json"
        job = supervise(
            study.worker_entry,
            (artifact_root, market_data_root, pin, path, deadline),
            seconds=max(0, deadline - time.monotonic()),
        )
        if job["timed_out"]:
            result = study.failure(contract, pin, "hard_timeout")
        elif type(job["exit_code"]) is int and job["exit_code"] == 0:
            candidate = json.loads(study._read(path))
            study.validate_result(candidate, contract, pin)
            study.verify(artifact_root, market_data_root, pin)
            result = candidate
    except KeyboardInterrupt:
        result = study.failure(contract, pin, "execution_preempted")
    except Exception:
        result = study.failure(contract, pin, "worker_result_invalid")
    study.atomic_new(output / "summary.json", result)
    register_campaign_outcome(
        contract_hash=pin,
        outcome_class="non_promoting_failed"
        if result["status"] == "failed"
        else "non_promoting_completed",
        outcome_reference_sha256=study.digest(study.encode(result)),
        artifact_root=artifact_root,
        repo_root=study.REPO,
    )
    return study.safe_result(result)


def _interrupt(*_):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--recover-registry", action="store_true")
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    if bool(args.contract_sha256) != bool(args.run or args.verify or args.recover_registry):
        parser.error("--contract-sha256 is required for --run, --verify or --recover-registry")
    if bool(args.result_sha256) != bool(args.verify or args.recover_registry):
        parser.error("--result-sha256 is required only for --verify or --recover-registry")
    if not (args.freeze or args.run or args.verify or args.recover_registry):
        print(json.dumps(dict(status="static_plan", config=study.configuration()), sort_keys=True))
        return 0
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "1"
    previous = signal.signal(signal.SIGTERM, _interrupt)
    try:
        if args.freeze:
            result = dict(
                status="frozen_metadata_only",
                contract_sha256=study.freeze(args.artifact_root, args.market_data_root),
            )
        elif args.verify or args.recover_registry:
            operation = study.recover_registry if args.recover_registry else study.readback
            result = operation(
                args.artifact_root,
                args.market_data_root,
                args.contract_sha256,
                result_sha256=args.result_sha256,
                deadline=time.monotonic() + study.SECONDS,
            )
        else:
            result = dispatch(args.artifact_root, args.market_data_root, args.contract_sha256)
    except (Exception, KeyboardInterrupt):
        result = dict(status="dispatch_unavailable", raw_error_suppressed=True)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"frozen_metadata_only", "complete", "input_unavailable"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

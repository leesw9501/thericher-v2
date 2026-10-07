"""Static plan, CPU smoke, explicit CPU repair dispatch, or zero-fit readback."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import time
from pathlib import Path

from thericher_v2.research import tiingo_joint_d1_policy as study
from thericher_v2.research.campaign_registry import register_campaign_outcome


def supervise(target, arguments, *, seconds):
    existing = runpy.run_path(str(study.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    return existing["supervise"](target, arguments, seconds=seconds, name=study.NAME)


def dispatch(artifact_root, market_data_root, pin):
    from thericher_v2.research.engine_research_agent import GpuFileLock

    output, contract = study.verify(artifact_root, market_data_root, pin)
    study.require(
        {p.name for p in output.iterdir()} == {"precommit.json"}, "attempt_already_exists"
    )
    # Reuse the file-lease primitive on this CPU attempt, never the shared GPU path.
    with GpuFileLock(output / "cpu-attempt.lock"):
        deadline = time.monotonic() + study.SECONDS
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
                candidate = json.loads(study.prior._read(path))
                study.validate_result(candidate, contract, pin)
                study.verify(artifact_root, market_data_root, pin)
                result = candidate
        except KeyboardInterrupt:
            result = study.failure(contract, pin, "execution_preempted")
        except Exception:
            result = study.failure(contract, pin, "worker_result_invalid")
        study.atomic_new(output / "summary.json", result)
        # A failure here is recoverable from the immutable original summary, without another run.
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
    for flag in (
        "plan",
        "smoke",
        "freeze",
        "run",
        "verify",
        "recover-registry",
        "recover-terminal",
    ):
        mode.add_argument("--" + flag, action="store_true")
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    parser.add_argument("--smoke-receipt", type=Path)
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    if (
        args.run or args.verify or args.recover_registry or args.recover_terminal
    ) and not args.contract_sha256:
        parser.error("--contract-sha256 is required for run/readback/recovery")
    if args.contract_sha256 and not (
        args.smoke or args.run or args.verify or args.recover_registry or args.recover_terminal
    ):
        parser.error("--contract-sha256 applies only to smoke/run/readback/recovery")
    if bool(args.result_sha256) != bool(
        args.verify or args.recover_registry or args.recover_terminal
    ):
        parser.error("--result-sha256 applies only to readback/recovery")
    if args.smoke_receipt and not args.smoke:
        parser.error("--smoke-receipt applies only to smoke")
    if not (
        args.smoke
        or args.freeze
        or args.run
        or args.verify
        or args.recover_registry
        or args.recover_terminal
    ):
        print(json.dumps(dict(status="static_plan", config=study.configuration()), sort_keys=True))
        return 0
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[name] = "2"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    previous = signal.signal(signal.SIGTERM, _interrupt)
    try:
        if args.smoke:
            contract = None
            if args.contract_sha256:
                # A smoke may read only the code-bound precommit, never market metadata or registry.
                raw = study.prior._read(study._output(args.artifact_root) / "precommit.json")
                study.require(study.digest(raw) == args.contract_sha256, "smoke_contract_binding")
                contract = json.loads(raw)
            result = study.smoke(contract=contract, pin=args.contract_sha256)
            if args.smoke_receipt:
                parent = study.prior.base.ensure_external_artifact_directory(
                    args.smoke_receipt.parent, study.REPO
                )
                study.atomic_new(parent / args.smoke_receipt.name, result)
        elif args.freeze:
            result = dict(
                status="frozen_metadata_only",
                contract_sha256=study.freeze(args.artifact_root, args.market_data_root),
            )
        elif args.verify or args.recover_registry or args.recover_terminal:
            operation = (
                study.recover_terminal
                if args.recover_terminal
                else study.recover_registry
                if args.recover_registry
                else study.readback
            )
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
    return (
        0
        if result["status"]
        in {"synthetic_cpu_passed", "frozen_metadata_only", "complete", "input_unavailable"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

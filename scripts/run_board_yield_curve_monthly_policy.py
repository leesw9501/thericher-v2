"""One fixed CPU campaign, bounded ALL-RO replay and registry-only recovery."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import runpy
import time
from pathlib import Path

from thericher_v2.research import board_yield_curve_monthly_policy as study


def supervise(target, arguments, *, seconds):
    return runpy.run_path(str(study.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))[
        "supervise"
    ](target, arguments, seconds=seconds, name=study.NAME)


def dispatch(root, market, pin):
    deadline = time.monotonic() + study.SECONDS
    output, contract = study.verify(root, market, pin)
    study.require({p.name for p in output.iterdir()} == {"precommit.json"},
                  "attempt_already_exists")
    study.register_contract(root, contract, pin)
    study.atomic_new(output / "started.json", {"contract_sha256": pin})
    result = study.failure(pin, "dispatch", "worker_failed")
    try:
        job = supervise(study.worker_entry, (root, market, pin, deadline),
                        seconds=max(0, deadline - time.monotonic()))
        if job["timed_out"]:
            result = study.failure(pin, "dispatch", "hard_timeout")
        elif job["exit_code"] == 0:
            worker_raw = study._read(output / "worker-result.json")
            candidate = json.loads(worker_raw)
            study.require(worker_raw == study.encode(candidate), "worker_result_encoding")
            study.validate_result(candidate, contract, pin)
            study.require(candidate["status"] != "failed" or candidate["phase"] != "dispatch",
                          "worker_result_origin")
            study.verify(root, market, pin)
            result = candidate
    except KeyboardInterrupt:
        result = study.failure(pin, "dispatch", "execution_preempted")
    except Exception:
        result = study.failure(pin, "dispatch", "worker_result_invalid")
    if result["status"] == "failed" and result["phase"] == "dispatch":
        # supervise() has joined/terminated/killed the child before this snapshot.
        result["dispatch_worker_binding"] = study.dispatch_worker_binding(output)
    study.validate_result(result, contract, pin)
    study.atomic_new(output / "summary.json", result)
    study.append_outcome(root, pin, result)
    return study.safe_result(result)


def bounded_readback(operation, root, market, pin, result_pin):
    receiving, sending = multiprocessing.get_context("spawn").Pipe(duplex=False)
    try:
        deadline = time.monotonic() + study.SECONDS
        job = supervise(study.readback_entry,
                        (operation, root, market, pin, result_pin, deadline, sending),
                        seconds=study.SECONDS)
        if job["timed_out"] or job["exit_code"] != 0 or not receiving.poll():
            return dict(status="readback_unavailable", raw_error_suppressed=True)
        return receiving.recv()
    finally:
        receiving.close()
        sending.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ("plan", "smoke", "freeze", "run", "verify", "recover-registry"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--artifact-root", type=Path,
                        default=Path("D:/thericher-v2/model-artifacts"))
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    args = parser.parse_args(argv)
    bound = bool(args.run or args.verify or args.recover_registry)
    if bool(args.contract_sha256) != bound or bool(args.result_sha256) != bool(
        args.verify or args.recover_registry
    ):
        parser.error("run/replay/recovery require exact contract/result pins")
    try:
        if args.smoke:
            result = study.synthetic_smoke()
        elif args.freeze:
            result = dict(status="frozen_metadata_only",
                          contract_sha256=study.freeze(args.artifact_root, args.market_data_root))
        elif args.run:
            result = dispatch(args.artifact_root, args.market_data_root, args.contract_sha256)
        elif args.verify or args.recover_registry:
            result = bounded_readback("verify" if args.verify else "recover-registry",
                                      args.artifact_root, args.market_data_root,
                                      args.contract_sha256, args.result_sha256)
        else:
            result = dict(status="static_plan", config=study.configuration())
    except (Exception, KeyboardInterrupt):
        result = dict(status="dispatch_unavailable", raw_error_suppressed=True)
    print(json.dumps(result, sort_keys=True))
    verified_failure = (result["status"] == "failed"
                        and result.get("replay") == "failure_binding_only")
    return 0 if verified_failure or result["status"] in {
        "static_plan", "synthetic_smoke_passed", "frozen_metadata_only", "complete",
        "input_unavailable",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())

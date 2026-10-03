"""One metadata-frozen offline study; parent owns pinned Docker dispatch and mounts."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import sys
import time
from contextlib import nullcontext
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from thericher_v2.research import tiingo_causal_expert_mixture_development as study  # noqa: E402
from thericher_v2.research.campaign_registry import register_campaign_outcome  # noqa: E402
from thericher_v2.research.engine_research_agent import (  # noqa: E402
    GpuFileLock,
    resolve_agent_root,
)


def supervise(target, arguments, *, seconds):
    runner = runpy.run_path(str(study.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))
    return runner["supervise"](target, arguments, seconds=seconds, name=study.NAME)


def dispatch(artifacts, market, pin, phase):
    study.require(phase in {"cuda", "cpu-smoke"}, "dispatch_phase")
    study.runtime_constraints()
    root, contract = study.verify(artifacts, market, pin)
    study.require(not (root / "cuda-started.json").exists(), "attempt_already_exists")
    result = study.result_base(pin, phase)
    lock = (
        GpuFileLock(resolve_agent_root(artifacts) / "locks/gpu.lock")
        if phase == "cuda"
        else nullcontext()
    )
    with lock:
        study.atomic_new(root / f"{phase}-started.json", {"contract_sha256": pin})
        deadline = time.monotonic() + (120 if phase == "cpu-smoke" else study.SECONDS)
        path = root / f"{phase}-result.json"
        try:
            job = supervise(
                study.worker,
                (artifacts, market, pin, path, deadline, phase),
                seconds=max(0, deadline - time.monotonic()),
            )
            if not job["timed_out"] and type(job["exit_code"]) is int and job["exit_code"] == 0:
                candidate, _ = study.read_json(path)
                study.validate_result(candidate, contract, pin)
                study.require(candidate["phase"] == phase, "result_phase_binding")
                result = study.result_base(
                    pin,
                    phase,
                    counts={k: candidate[k] for k in ("fits_started", "fits_completed")},
                    failure_stage="validate",
                )
                study.verify_weights(root, candidate)
                study.verify(artifacts, market, pin)
                result = candidate
            elif path.exists():
                candidate, _ = study.read_json(path)
                study.validate_result(candidate, contract, pin)
                study.require(candidate["phase"] == phase, "result_phase_binding")
                result = study.result_base(
                    pin,
                    phase,
                    counts={k: candidate[k] for k in ("fits_started", "fits_completed")},
                    failure_stage=candidate["failure_stage"],
                )
        except (Exception, KeyboardInterrupt):
            pass
        study.atomic_new(root / f"{phase}-summary.json", result)
        if phase == "cuda":
            register_campaign_outcome(
                contract_hash=pin,
                outcome_class="non_promoting_completed"
                if result["status"] in {"complete", "input_unavailable"}
                else "non_promoting_failed",
                outcome_reference_sha256=study.digest(study.encode(result)),
                artifact_root=artifacts,
                repo_root=study.REPO,
            )
    return dict(
        status=result["status"],
        fits_started=result["fits_started"],
        fits_completed=result["fits_completed"],
        cells=len(result["cells"]),
        failure_stage=result["failure_stage"],
        summary_sha256=study.digest(study.encode(result)),
        contract_sha256=pin,
    )


def _interrupt(*_):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--phase", choices=("cpu-smoke", "cuda"), default="cuda")
    parser.add_argument("--contract-sha256")
    parser.add_argument("--summary-sha256")
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    if not (args.freeze or args.run or args.verify):
        print(
            json.dumps(
                dict(
                    status="preview",
                    fits=0,
                    cells=144,
                    operational_io=False,
                    config=study.configuration(),
                ),
                sort_keys=True,
            )
        )
        return 0
    if (args.run or args.verify) and not args.contract_sha256:
        parser.error("--contract-sha256 required")
    if args.verify and not args.summary_sha256:
        parser.error("--summary-sha256 required")
    if args.freeze and (args.contract_sha256 or args.summary_sha256):
        parser.error("freeze cannot supply result pins")
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
        if args.freeze:
            result = dict(
                status="frozen_metadata_only",
                contract_sha256=study.freeze(args.artifact_root, args.market_data_root),
            )
        elif args.run:
            result = dispatch(
                args.artifact_root, args.market_data_root, args.contract_sha256, args.phase
            )
        else:
            _, contract = study.verify(
                args.artifact_root, args.market_data_root, args.contract_sha256
            )
            root = study.base.ensure_external_artifact_directory(
                args.artifact_root, study.REPO, "research", study.NAME
            )
            value, pin = study.read_json(root / f"{args.phase}-summary.json", args.summary_sha256)
            study.validate_result(value, contract, args.contract_sha256)
            study.require(value["phase"] == args.phase, "result_phase_binding")
            study.verify_weights(root, value)
            result = dict(
                status="verified",
                result_status=value["status"],
                summary_sha256=pin,
                cells=len(value["cells"]),
            )
    except (Exception, KeyboardInterrupt):
        result = dict(
            status="dispatch_unavailable",
            fits_started=None,
            fits_completed=None,
            failure_stage=None,
        )
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True))
    return (
        0
        if result["status"]
        in {"frozen_metadata_only", "complete", "cpu_smoke_complete", "verified"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

"""Supervise one named, hard-time-limited offline development phase."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path

from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as study
from thericher_v2.research.engine_research_agent import GpuFileLock, resolve_agent_root


def supervise(target, arguments, *, seconds, name):
    """The parent, not the training function, owns and reaps the timed process."""
    process = multiprocessing.get_context("spawn").Process(
        target=target, args=arguments, name=name, daemon=False
    )
    started = time.monotonic()
    process.start()
    timed_out = False
    try:
        process.join(max(0, seconds - (time.monotonic() - started)))
        timed_out = process.is_alive()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(2)
        if process.is_alive():
            process.kill()
            process.join()
    result = {
        "name": name,
        "pid": process.pid,
        "hard_timeout_seconds": seconds,
        "timed_out": timed_out,
        "exit_code": process.exitcode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    process.close()
    return result


def dispatch(args):
    output, _ = study.verify_contract(args.artifact_root, args.run_label, args.contract_sha256)
    if args.phase == "cuda":
        raw = (output / "cpu-summary.json").read_bytes()
        if study.digest(raw) != args.cpu_summary_sha256:
            raise study.StudyFailure("cpu_summary_hash_mismatch")
        study.bind_cpu_summary(json.loads(raw), args.contract_sha256)
    lock = (
        GpuFileLock(resolve_agent_root(args.artifact_root) / "locks" / "gpu.lock")
        if args.phase == "cuda"
        else nullcontext()
    )
    name = f"{study.FAMILY}-{args.run_label}-{args.phase}"
    with lock:
        with (output / f"{args.phase}-started.json").open("xb") as handle:
            handle.write(
                study.encode(
                    {
                        "name": name,
                        "parent_pid": os.getpid(),
                        "contract_sha256": args.contract_sha256,
                        "hard_timeout_seconds": study.TIMEOUTS[args.phase],
                    }
                )
            )
        with tempfile.TemporaryDirectory(prefix=f"{args.phase}-job-", dir=output) as temporary:
            worker_result = Path(temporary) / "result.json"
            job = supervise(
                study.worker_entry,
                (
                    args.market_data_root,
                    args.artifact_root,
                    args.run_label,
                    args.contract_sha256,
                    args.phase,
                    args.cpu_summary_sha256,
                    worker_result,
                ),
                seconds=study.TIMEOUTS[args.phase],
                name=name,
            )
            result = study.result_base(args.phase)
            if job["timed_out"] or job["exit_code"] != 0 or not worker_result.is_file():
                study.invalidate(result, "hard_timeout" if job["timed_out"] else "worker_failed")
            else:
                result = json.loads(worker_result.read_bytes())
                expected = study.expected_cells(args.phase)
                if (
                    result.get("contract_sha256") != args.contract_sha256
                    or len(result.get("cells", [])) != len(expected)
                    or {study.cell_key(c) for c in result["cells"]}
                    != {study.cell_key(c) for c in expected}
                ):
                    result = study.invalidate(
                        study.result_base(args.phase), "worker_matrix_invalid"
                    )
            if result.get("status") == "complete" and args.phase == "cuda":
                references = result.get("models", [])
                if len(references) != 16:
                    study.invalidate(result, "final_model_matrix_incomplete")
                else:
                    for reference in references:
                        study.load_model_arrays(
                            Path(temporary) / "models", reference, args.contract_sha256
                        )
                    if (output / "models").exists():
                        raise study.StudyFailure("model_namespace_used")
                    (Path(temporary) / "models").rename(output / "models")
            result.update(
                {
                    "contract_sha256": args.contract_sha256,
                    "cpu_summary_sha256": args.cpu_summary_sha256,
                    "job": job,
                }
            )
            with (output / f"{args.phase}-summary.json").open("xb") as handle:
                handle.write(study.encode(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--phase", choices=("cpu", "cuda"))
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--cpu-summary-sha256")
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    args = parser.parse_args(argv)
    if args.phase and not args.contract_sha256:
        parser.error("a reviewed --contract-sha256 is required")
    if (args.phase == "cuda") != (args.cpu_summary_sha256 is not None):
        parser.error("--cpu-summary-sha256 is required only for CUDA")
    if args.freeze and args.contract_sha256:
        parser.error("freeze does not accept --contract-sha256")
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    try:
        if args.freeze:
            report = {
                "status": "frozen_metadata_only",
                "contract_sha256": study.freeze(args.artifact_root, args.run_label),
            }
        else:
            result = dispatch(args)
            report = {
                "status": result["status"],
                "phase": args.phase,
                "cell_count": len(result["cells"]),
                "model_count": len(result.get("models", [])),
                "job": result["job"],
            }
    except Exception:
        report = {"status": "dispatch_unavailable", "raw_error_suppressed": True}
    print(json.dumps({"family": study.FAMILY, **report}, sort_keys=True))
    return 0 if report["status"] in {"complete", "frozen_metadata_only"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

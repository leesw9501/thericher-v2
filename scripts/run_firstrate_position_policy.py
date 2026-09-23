"""Freeze metadata or run one CPU-only, no-fit DEVELOPMENT position-policy comparison."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import tempfile
from pathlib import Path

from thericher_v2.research import firstrate_position_policy as study
from thericher_v2.research.campaign_registry import register_campaign_outcome


def interrupt(*_):
    raise KeyboardInterrupt


def dispatch(args):
    output = study.verify(args.artifact_root, args.contract_sha256)
    summary = output / "summary.json"
    if summary.exists() or summary.is_symlink():
        raise FileExistsError("summary_exists")
    with (output / "started.json").open("xb") as handle:
        handle.write(
            study.h30.encode(
                dict(
                    name=study.NAME,
                    parent_pid=os.getpid(),
                    contract_sha256=args.contract_sha256,
                    hard_timeout_seconds=study.SECONDS,
                )
            )
        )
    result = study.failure(args.contract_sha256, "worker_failed_or_timed_out")
    job = None
    try:
        supervise = runpy.run_path(
            str(study.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
        )["supervise"]
        with tempfile.TemporaryDirectory(prefix="cpu-job-", dir=output) as temporary:
            path = Path(temporary) / "result.json"
            job = supervise(
                study.worker,
                (args.artifact_root, args.market_data_root, args.contract_sha256, path),
                seconds=study.SECONDS,
                name=study.NAME,
            )
            if (
                job["timed_out"] is False
                and type(job["exit_code"]) is int
                and job["exit_code"] == 0
            ):
                if not path.is_file() or path.is_symlink():
                    raise ValueError("worker_result_missing")
                candidate = json.loads(path.read_bytes())
                if candidate.get("status") == "failed_all_cells":
                    reason = candidate.get("reason")
                    if reason not in (
                        "common_outcome_support_shortfall",
                        "runtime_or_invariant_failure",
                    ):
                        raise ValueError("worker_result_invalid")
                    expected = study.failure(args.contract_sha256, reason)
                    support = candidate.get("support")
                    if support is not None:
                        if (
                            not isinstance(support, dict)
                            or set(support) != {"eligible", "observed", "censored", "blocks"}
                            or any(
                                type(v) is not int or not 0 <= v <= 1000000
                                for v in support.values()
                            )
                            or support["observed"] + support["censored"] != support["eligible"]
                            or support["blocks"] > support["observed"]
                        ):
                            raise ValueError("worker_result_invalid")
                        expected["support"] = support
                    if candidate != expected:
                        raise ValueError("worker_result_invalid")
                else:
                    study.validate_result(candidate, args.contract_sha256)
                study.verify(args.artifact_root, args.contract_sha256)
                result = candidate
    except KeyboardInterrupt:
        result = study.failure(args.contract_sha256, "execution_preempted")
    except Exception:
        result = study.failure(args.contract_sha256, "worker_result_invalid")
    result["job"] = job
    raw = study.h30.encode(result)
    with summary.open("xb") as handle:
        handle.write(raw)
    register_campaign_outcome(
        contract_hash=args.contract_sha256,
        outcome_class="non_promoting_completed"
        if result["status"] == "complete"
        else "non_promoting_failed",
        outcome_reference_sha256=study.h30.digest(raw),
        artifact_root=args.artifact_root,
        repo_root=study.REPO,
    )
    return dict(
        status=result["status"],
        contract_sha256=args.contract_sha256,
        summary_sha256=study.h30.digest(raw),
        paired_cells=len(result["cells"]),
        job=job,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--contract-sha256")
    parser.add_argument(
        "--artifact-root", type=Path, default=Path("D:/thericher-v2/model-artifacts")
    )
    parser.add_argument("--market-data-root", type=Path, default=Path("D:/market_data"))
    args = parser.parse_args(argv)
    if args.run != bool(args.contract_sha256) or (args.freeze and args.contract_sha256 is not None):
        parser.error("--contract-sha256 is required only for --run")
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        result = (
            {"status": "frozen_metadata_only", "contract_sha256": study.freeze(args.artifact_root)}
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

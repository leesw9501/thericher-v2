"""Freeze or supervise one bounded DEVELOPMENT model-family comparison phase."""

from __future__ import annotations

import argparse
import json
import os
import runpy
import signal
import tempfile
from contextlib import nullcontext
from pathlib import Path

from thericher_v2.research import firstrate_family_comparison as s
from thericher_v2.research.artifact_paths import reject_repo_artifact_path
from thericher_v2.research.campaign_registry import register_campaign_outcome
from thericher_v2.research.engine_research_agent import GpuFileLock, resolve_agent_root

MODEL_COUNTS = {"cpu": 4, "cuda": 16}
SAFE_FAILURES = frozenset(
    {
        "calendar_version",
        "contract_changed",
        "lineage_changed",
        "cpu_summary_hash",
        "training_support_shortfall",
        "evaluation_support_shortfall",
        "evaluation_outcome_support_shortfall",
        "source_hash",
        "source_changed",
        "source_order",
        "train_label_crosses_eval_history",
        "cpu_cuda_cohort_changed",
        "target_fee_replay_parity",
        "budget_exhausted",
        "nonfinite_loss",
        "nonfinite_gradient",
        "nonfinite_fit",
        "model_reload",
        "cell_matrix",
        "fit_matrix",
        "training_passes",
        "result_accounting",
        "runtime_or_invariant_failure",
        "study_invariant_failed",
        "parent_control_mismatch",
        "lightgbm_version",
    }
)


def interrupt(*_):
    raise KeyboardInterrupt


class WorkerFailure(ValueError):
    """An identity-bound categorical failure, never arbitrary exception text."""

    def __init__(self, reason, support=None):
        super().__init__(reason)
        self.support = support


def check_worker_failure(candidate, phase, scope_hash):
    if (
        candidate.get("status") == "failed_all_phase_cells"
        and candidate.get("name") == s.NAME
        and candidate.get("phase") == phase
        and candidate.get("contract_sha256") == scope_hash
        and isinstance(candidate.get("reason"), str)
        and candidate["reason"] in SAFE_FAILURES
    ):
        support = candidate.get("support")
        if support is not None:
            if (
                not isinstance(support, dict)
                or set(support) != {"eligible", "observed", "censored", "blocks"}
                or any(type(v) is not int or not 0 <= v <= 1000000 for v in support.values())
                or support["observed"] + support["censored"] != support["eligible"]
                or support["blocks"] > support["observed"]
            ):
                raise ValueError("invalid_support")
        raise WorkerFailure(candidate["reason"], support)


def validate_complete(result, phase, scope_hash):
    s.validate_result(result, phase, scope_hash)
    if (
        result.get("status") != "complete"
        or result.get("name") != s.NAME
        or result.get("phase") != phase
        or result.get("contract_sha256") != scope_hash
        or not isinstance(result.get("models"), list)
        or len(result["models"]) != MODEL_COUNTS[phase]
    ):
        raise ValueError("result_identity_or_model_matrix")


def bind_cpu_summary(output, scope_hash, cpu_hash):
    path = output / "cpu-summary.json"
    if path.is_symlink():
        raise WorkerFailure("cpu_summary_hash")
    raw = path.read_bytes()
    if s.h30.digest(raw) != cpu_hash:
        raise WorkerFailure("cpu_summary_hash")
    validate_complete(json.loads(raw), "cpu", scope_hash)


def dispatch(args):
    reject_repo_artifact_path(args.artifact_root, s.REPO)
    output, *_ = s.verify(args.artifact_root, args.contract_sha256)
    reject_repo_artifact_path(output, s.REPO)
    if not output.resolve().is_relative_to(args.artifact_root.resolve()):
        raise ValueError("output_root_mismatch")
    lock = (
        GpuFileLock(resolve_agent_root(args.artifact_root) / "locks/gpu.lock")
        if args.phase == "cuda"
        else nullcontext()
    )
    summary = output / f"{args.phase}-summary.json"
    destination = output / f"{args.phase}-models"
    with lock:
        if summary.exists() or summary.is_symlink():
            raise FileExistsError("phase_summary_exists")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("model_namespace_used")
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
        result = s.failure(args.phase, args.contract_sha256, "worker_failed_or_timed_out")
        job = None
        try:
            if args.phase == "cuda":
                bind_cpu_summary(output, args.contract_sha256, args.cpu_summary_sha256)
            supervise = runpy.run_path(
                str(s.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py")
            )["supervise"]
            with tempfile.TemporaryDirectory(prefix=f"{args.phase}-job-", dir=output) as temporary:
                path = Path(temporary) / "result.json"
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
                if (
                    job["timed_out"] is False
                    and type(job["exit_code"]) is int
                    and job["exit_code"] == 0
                ):
                    if not path.is_file() or path.is_symlink():
                        raise ValueError("worker_result_missing")
                    candidate = json.loads(path.read_bytes())
                    check_worker_failure(candidate, args.phase, args.contract_sha256)
                    validate_complete(candidate, args.phase, args.contract_sha256)
                    if (
                        args.phase == "cuda"
                        and candidate.get("cpu_summary_sha256") != args.cpu_summary_sha256
                    ):
                        raise WorkerFailure("cpu_summary_hash")
                    models = Path(temporary) / "models"
                    if not models.is_dir() or models.is_symlink():
                        raise WorkerFailure("model_reload")
                    try:
                        s.verify_models(models, candidate, args.contract_sha256)
                    except Exception as error:
                        raise WorkerFailure("model_reload") from error
                    candidate["job"] = job
                    s.h30.encode(candidate)
                    if destination.exists() or destination.is_symlink():
                        raise FileExistsError("model_namespace_used")
                    models.rename(destination)
                    result = candidate
        except WorkerFailure as error:
            result = s.failure(args.phase, args.contract_sha256, str(error))
            if error.support is not None:
                result["support"] = error.support
        except KeyboardInterrupt:
            result = s.failure(args.phase, args.contract_sha256, "execution_preempted")
        except Exception:
            result = s.failure(args.phase, args.contract_sha256, "worker_result_invalid")
        result["job"] = job
        raw = s.h30.encode(result)
        with summary.open("xb") as handle:
            handle.write(raw)
    if args.phase == "cuda" or result["status"] != "complete":
        register_campaign_outcome(
            contract_hash=args.contract_sha256,
            outcome_class="non_promoting_completed"
            if result["status"] == "complete"
            else "non_promoting_failed",
            outcome_reference_sha256=s.h30.digest(raw),
            artifact_root=args.artifact_root,
            repo_root=s.REPO,
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
    if (args.phase is not None) != (args.contract_sha256 is not None) or args.contract_sha256 == "":
        parser.error("--contract-sha256 is required only for a phase")
    if (args.phase == "cuda") != (
        args.cpu_summary_sha256 is not None
    ) or args.cpu_summary_sha256 == "":
        parser.error("--cpu-summary-sha256 is required only for CUDA")
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        reject_repo_artifact_path(args.artifact_root, s.REPO)
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

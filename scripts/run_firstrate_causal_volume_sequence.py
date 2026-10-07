"""Bounded offline volume study. The parent owns actual freeze/CUDA dispatch."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import run_firstrate_forward_variance_baseline as baseline
import run_firstrate_forward_variance_smoke as smoke

from thericher_v2.research import causal_volume_sequence as volume
from thericher_v2.research.campaign_registry import (
    register_campaign_outcome,
    register_frozen_campaign,
)

STUDY = "firstrate-causal-volume-sequence-development-20261008-v1"
FAMILY = "firstrate-causal-volume-sequence-development-v1"
IMAGE = "sha256:d6b43213ee3877653e3c1e79c7238fb5caa71241abf238838fa0c3332cf4f039"
REPO = Path(__file__).resolve().parents[1]
CODE = (
    *baseline.CODE,
    "src/thericher_v2/research/causal_volume_sequence.py",
    "src/thericher_v2/research/sequence_architecture_models.py",
    "src/thericher_v2/research/engine_research_agent.py",
    "scripts/run_firstrate_causal_volume_sequence.py",
)
load_source_cases = baseline.load_source_cases

# Only the pinned leaves come from snapshots; other dependencies remain in the
# existing image. Namespace packages bypass its lazy compatibility imports.
FROZEN_REPLAY_BOOTSTRAP = """\
import runpy
import sys
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

code = Path(sys.argv[1])
sys.path.insert(0, str(code / "scripts"))
for name in ("thericher_v2", "thericher_v2.research", "thericher_v2.data", "thericher_v2.market"):
    relative = Path(*name.split("."))
    package = types.ModuleType(name)
    package.__package__ = name
    package.__path__ = [str(code / "src" / relative), str(Path("/app/src") / relative)]
    package.__spec__ = ModuleSpec(name, loader=None, is_package=True)
    sys.modules[name] = package
    if "." in name:
        parent, child = name.rsplit(".", 1)
        setattr(sys.modules[parent], child, package)
program = runpy.run_path(str(code / "scripts/run_firstrate_causal_volume_sequence.py"))

def forbidden(*args, **kwargs):
    raise RuntimeError("recovery_fit_or_GPU_forbidden")

for name in ("fit_models", "fit_gru", "fit_ridge"):
    setattr(program["volume"], name, forbidden)
import torch
torch.optim.AdamW = forbidden
torch.cuda.is_available = forbidden
sys.argv = sys.argv[2:]
raise SystemExit(program["main"]())
"""


def contract(pins, vram_bytes=2 * 1024**3):
    volume.require(type(vram_bytes) is int and 0 < vram_bytes <= 4 * 1024**3, "VRAM_contract")
    return {
        "study": STUDY,
        "family": FAMILY,
        "grade": "revised_seen_activity_development_only",
        "lineage_precommit_sha256": smoke.PARENT_HASH,
        "normalization_sha256": smoke.NORMALIZATION_HASH,
        "source_sha256": smoke.SOURCES,
        "scheduled_date_set_sha256": smoke.DATE_HASH,
        "scheduled_dates": 251,
        "split": {
            "TRAIN": 160,
            "embargo": 1,
            "comparison": 90,
            "halves": [45, 45],
            "rule": "shared scheduled chronological dates BEFORE any exclusion",
        },
        "decisions": list(volume.SLOTS),
        "decision_rule": "open+slot minutes; never clip early closes",
        "input": "own/peer24 completed M5 volumes from M1 starts C-120..C-1; END<=C",
        "features": list(volume.FEATURES),
        "ridge_summaries": list(volume.SUMMARIES),
        "target": "sum volume of30 exact complete M1 starts C+1..C+30; available C+31",
        "zero_missing": "zero valid/log1p; no target floor/imputation; missing target only censors "
        "its common ETF/slot cohort, never input eligibility",
        "transforms": "feature and summary population mean/std from all input-eligible TRAIN; "
        "log1p target mean/std from input+target-eligible TRAIN; constant std=>1",
        "model": {
            "architecture": "pooled_gru32",
            "seed": 101,
            "epochs": 128,
            "batch": 128,
            "optimizer": "AdamW",
            "lr": 0.001,
            "weight_decay": 0.01,
            "dtype": "float64",
            "selection": "final_epoch_only",
            "shuffle": False,
            "fits": {"CUDA_GRU": 1, "CPU_Ridge": 1},
        },
        "controls": {
            "train_slot_mean": "arithmetic target TRAIN mean per ETF/slot",
            "persistence": "own trailing30 total volume",
            "seasonality": "targetTRAINmean/past30TRAINmean*currentpast30 per ETF/slot; "
            "zero denominator or absent TRAIN group=>scoped unknown",
            "ridge": "pooled weighted L2=1 fixed log-volume summaries; unpenalized intercept",
        },
        "loss": "squared normalized log1p target error; mean common slots within ETFday, "
        "then mean shared dates; TRAIN row weight N/(days*ETFs_on_day*slots_on_ETFday)",
        "kill": "GRU>=5%better than EVERY control for EACH ETF/all90/first45/last45 AND "
        "every shared-date deletion within each group without refit; zero control "
        "loss/empty cohort fails; no ETF/window/seed rescue",
        "matrix": {
            "cells": 1,
            "horizon_minutes": 30,
            "context_minutes": 120,
            "effective_samples": "shared dates, never IID slots or ETF observations",
        },
        "compute": {
            "seconds": 600,
            "cpu": 2,
            "memory_bytes": 6 * 1024**3,
            "vram_bytes": vram_bytes,
            "vram_headroom_bytes": 1024**3,
            "network": "none",
            "source": "read_only",
            "image": IMAGE,
            "stop": "deadline/VRAM/fault ends exact attempt; no restart/tuning",
        },
        "runtime": {
            "python": "3.12.14",
            "torch": "2.7.0+cu128",
            "numpy": "2.5.1",
            "pandas-market-calendars": "5.4.0",
        },
        "artifact_root": "D:/thericher-v2/model-artifacts/research/" + STUDY,
        "retention": "numeric JSON model state and exact code snapshots outside Git; "
        "anchored contract/result/model hashes; CPU inference/loss replay no fit",
        "prior_seen_history": [
            "firstrate-forward-risk-baseline-development-20261007-v1",
            "firstrate-paired-allocation-development-20261005-v2",
            "firstrate-first30-closing29-development-20261005-v1",
        ],
        "costs": "not_applicable_activity_target_no_trades",
        "holdout": "none",
        "paper_input": False,
        "broker_calls": 0,
        "limitations": [
            "revised/seen source, not independent replication or sealed evaluation",
            "timestamps/actions/finality/historical availability unqualified",
            "physical parsing not target-isolated; conditional complete-case scores",
            "activity target is not return/PnL/capacity/impact/fillability",
            "critical code pins, not a fully locked transitive dependency bundle",
        ],
        "code_sha256": pins,
    }


def check_runtime(plan):
    import torch

    volume.require(platform.python_version() == plan["runtime"]["python"], "python_version")
    volume.require(torch.__version__ == plan["runtime"]["torch"], "torch_version")
    for name in ("numpy", "pandas-market-calendars"):
        volume.require(importlib.metadata.version(name) == plan["runtime"][name], name + "_version")


def check_pins(plan, market, lineage, normalization):
    volume.require(
        plan == contract(plan["code_sha256"], plan["compute"]["vram_bytes"])
        and set(plan["code_sha256"]) == set(CODE),
        "contract_changed",
    )
    specs = smoke.check_metadata(lineage, normalization)
    volume.require(
        {spec.symbol for spec in specs} == set(volume.SYMBOLS) and len(specs) == 2,
        "source_symbol_cardinality",
    )
    for relative, pin in plan["code_sha256"].items():
        volume.require(smoke.file_hash(REPO / relative) == pin, "code_changed")
    for spec in specs:
        source = market / spec.canonical_market_data_relative_path
        volume.require(source.stat().st_size <= 134217728, "source_size_limit")
        volume.require(smoke.file_hash(source) == smoke.SOURCES[spec.symbol], "source_changed")
    return specs


def register(plan, root, artifact_base):
    return register_frozen_campaign(
        contract_hash=smoke.file_hash(root / "contract.json"),
        dataset_hash=smoke.digest(smoke.encode(plan["source_sha256"])),
        split_hash=smoke.digest(smoke.encode([smoke.DATE_HASH, plan["split"], plan["decisions"]])),
        cost_model_hash=smoke.digest(smoke.encode(plan["costs"])),
        trial_family=FAMILY,
        holdout_access="none",
        artifact_root=artifact_base,
        repo_root=REPO,
    )


def freeze(root, market, lineage, normalization, artifact_base, vram_bytes=2 * 1024**3):
    plan = contract({relative: smoke.file_hash(REPO / relative) for relative in CODE}, vram_bytes)
    check_runtime(plan)
    check_pins(plan, market, lineage, normalization)
    if root.exists():
        volume.require(
            (root / "contract.json").read_bytes() == smoke.encode(plan) + b"\n",
            "existing_contract_mismatch",
        )
    else:
        root.mkdir(parents=True, exist_ok=False)
        smoke.write_once(root / "contract.json", plan)
    for relative, pin in plan["code_sha256"].items():
        destination = root / "code" / relative
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write((REPO / relative).read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
        volume.require(smoke.file_hash(destination) == pin, "frozen_code_changed")
    registered = register(plan, root, artifact_base)
    return {
        "status": "frozen_before_source_value_parse",
        "actual_fits": 0,
        "contract_sha256": smoke.file_hash(root / "contract.json"),
        "registry_sha256": registered.record_sha256,
    }


def jsonable(value):
    return json.loads(json.dumps(value, default=lambda item: item.isoformat(), allow_nan=False))


def input_projection(rows):
    # Forward support counts belong to target evidence, never input evidence.
    return tuple(
        replace(
            row,
            target=None,
            target_status="not_inspected",
            target_available_at=None,
            target_m1_count=0,
        )
        for row in rows
    )


def compute(plan, market, lineage, normalization, deadline, models=None):
    check_runtime(plan)
    specs = check_pins(plan, market, lineage, normalization)
    sessions, grouped = load_source_cases(specs, market, deadline)
    dates = tuple(session.open_ts.date() for session in sessions)
    rows, checks = [], Counter()
    for session in sessions:
        volume.require(time.monotonic() < deadline, "compute_stop")
        pair = tuple(tuple(grouped[symbol][session.open_ts.date()]) for symbol in volume.SYMBOLS)
        original = volume.records_from_pair(pair, session)
        for slot in volume.SLOTS:
            at = session.open_ts + slot * volume.MINUTE
            expected = input_projection([row for row in original if row.slot == slot])
            prefix = tuple(tuple(bar for bar in bars if bar.start_ts < at) for bars in pair)
            changed = volume.records_from_pair(prefix, session)
            volume.require(
                expected == input_projection([row for row in changed if row.slot == slot]),
                "future_dependent_input",
            )
            checks["prefix_future_removal"] += 1
            for support in (False, True):
                edited = tuple(
                    tuple(
                        replace(bar, complete=False)
                        if support and bar.start_ts >= at
                        else replace(bar, volume=bar.volume * 7)
                        if not support and bar.start_ts >= at
                        else bar
                        for bar in bars
                    )
                    for bars in pair
                )
                changed = volume.records_from_pair(edited, session)
                volume.require(
                    expected == input_projection([row for row in changed if row.slot == slot]),
                    "future_mutation_changed_input",
                )
                checks["future_support" if support else "future_value"] += 1
        rows.extend(original)
    train, later = volume.split_records(rows, dates)
    if models is None:
        models = volume.fit_models(
            train, deadline=deadline, vram_bytes=plan["compute"]["vram_bytes"]
        )
    volume.attest_train(models, train)
    forecasts = volume.predict(models, later, deadline=deadline)
    volume.require(
        forecasts == volume.predict(models, input_projection(later), deadline=deadline),
        "target_dependent_forecast",
    )
    checks["target_blind_forecast"] += len(later)
    report = volume.evaluate(later, forecasts, models["statistics"], dates[161:])
    check_pins(plan, market, lineage, normalization)
    volume.require(time.monotonic() < deadline, "compute_stop")
    result = {
        "status": "non_promoting_completed",
        "study": STUDY,
        "grade": plan["grade"],
        "scheduled": {"TRAIN": 160, "embargo": 1, "comparison": 90, "keys": len(rows)},
        "TRAIN": models["statistics"]["fit_rows"],
        "comparison": report,
        "outcomes": [
            {
                "date": row.session_date.isoformat(),
                "symbol": row.symbol,
                "slot": row.slot,
                "input": row.input_status,
                "target": row.target_status,
                "input_m1": row.input_m1_count,
                "target_m1": row.target_m1_count,
            }
            for row in rows
        ],
        "mutation_checks": dict(checks),
        "model_sha256": smoke.digest(smoke.encode(models)),
        "commitments": {
            "TRAIN": smoke.digest(smoke.encode(jsonable([asdict(row) for row in train]))),
            "inputs": smoke.digest(
                smoke.encode(jsonable([asdict(row) for row in input_projection(rows)]))
            ),
            "targets": smoke.digest(
                smoke.encode(
                    jsonable(
                        [
                            [
                                row.session_date,
                                row.symbol,
                                row.slot,
                                row.target_status,
                                row.target,
                                row.target_available_at,
                                row.target_m1_count,
                            ]
                            for row in rows
                        ]
                    )
                )
            ),
            "forecasts": smoke.digest(
                smoke.encode(
                    jsonable(
                        [
                            [row.session_date, row.symbol, row.slot, forecasts[row.key]]
                            for row in later
                        ]
                    )
                )
            ),
        },
        "recipe_actual_fits": {"CUDA_GRU": 1, "CPU_Ridge": 1},
        "holdout": False,
        "paper_input": False,
        "broker_calls": 0,
        "raw_market_rows_retained": False,
    }
    return result, models


def read_replay(root, result_pin):
    volume.require(
        (root / "result.json").stat().st_size <= 8 * 1024**2
        and (root / "models.json").stat().st_size <= 8 * 1024**2,
        "replay_size_limit",
    )
    raw = (root / "result.json").read_bytes()
    volume.require(smoke.digest(raw) == result_pin, "exact_result_pin_required")
    result = json.loads(raw)
    models = json.loads((root / "models.json").read_bytes())
    volume.require(smoke.digest(smoke.encode(models)) == result["model_sha256"], "model_changed")
    return models, result


def recovery_path(path):
    volume.require(path.is_absolute(), "recovery_absolute_paths_required")
    for parent in (path, *path.parents):
        volume.require(
            not parent.is_symlink() and not getattr(parent, "is_junction", lambda: False)(),
            "recovery_linked_path",
        )
    return path


def recovery_evidence(root, contract_pin, result_pin):
    paths = (
        root / "contract.json",
        root / "result.json",
        root / "models.json",
        root / "attempt.json",
    )
    for path in paths:
        recovery_path(path)
        volume.require(path.is_file() and path.stat().st_size <= 8 * 1024**2, "recovery_size_limit")
    raw = paths[0].read_bytes()
    volume.require(smoke.digest(raw) == contract_pin, "exact_contract_pin_required")
    plan = json.loads(raw)
    volume.require(
        plan == contract(plan["code_sha256"], plan["compute"]["vram_bytes"])
        and set(plan["code_sha256"]) == set(CODE),
        "contract_changed",
    )
    _, result = read_replay(root, result_pin)
    volume.require(
        result["contract_sha256"] == contract_pin
        and result["study"] == STUDY
        and result["grade"] == plan["grade"]
        and result["status"] == "non_promoting_completed"
        and result["recipe_actual_fits"] == plan["model"]["fits"]
        and result["holdout"] is False
        and result["paper_input"] is False
        and result["broker_calls"] == 0,
        "recovery_result_binding",
    )
    volume.require(
        json.loads(paths[3].read_bytes())["contract_sha256"] == contract_pin,
        "recovery_attempt_binding",
    )
    hashes = {str(path): smoke.file_hash(path) for path in paths}
    for relative, pin in plan["code_sha256"].items():
        path = recovery_path(root / "code" / relative)
        volume.require(
            path.is_file() and path.stat().st_size <= 1024**2, "recovery_code_size_limit"
        )
        hashes[str(path)] = smoke.file_hash(path)
        volume.require(hashes[str(path)] == pin, "frozen_code_changed")
    return plan, result, hashes


def recovery_runtime(plan, inputs):
    volume.require(os.name == "posix" and Path("/.dockerenv").is_file(), "recovery_Docker_required")
    check_runtime(plan)
    volume.require({name for _, name in socket.if_nameindex()} == {"lo"}, "recovery_network_none")
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
    volume.require(
        quota != "max" and 0 < int(quota) <= plan["compute"]["cpu"] * int(period),
        "recovery_CPU_bound",
    )
    volume.require(
        memory != "max" and 0 < int(memory) <= plan["compute"]["memory_bytes"],
        "recovery_memory_bound",
    )
    for path in inputs:
        volume.require(
            os.statvfs(recovery_path(path)).f_flag & os.ST_RDONLY, "recovery_inputs_read_only"
        )


def replay_frozen(root, market, lineage, normalization, contract_pin, result_pin, deadline):
    timeout = deadline - time.monotonic()
    volume.require(0 < timeout <= 600, "compute_stop")
    command = [
        str(Path(sys.executable).resolve()),
        "-I",
        "-B",
        "-c",
        FROZEN_REPLAY_BOOTSTRAP,
        str(root / "code"),
        str(root / "code/scripts/run_firstrate_causal_volume_sequence.py"),
        "verify",
        "--artifact-root",
        str(root),
        "--artifact-base",
        "/app/model_artifacts",
        "--market-root",
        str(market),
        "--lineage",
        str(lineage),
        "--normalization",
        str(normalization),
        "--contract-sha256",
        contract_pin,
        "--result-sha256",
        result_pin,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root / "code",
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={
                "CUDA_VISIBLE_DEVICES": "",
                "OMP_NUM_THREADS": "2",
                "MKL_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "2",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONHASHSEED": "0",
            },
        )
    except subprocess.TimeoutExpired:
        raise volume.VolumeFault("recovery_replay_timeout") from None
    except OSError:
        raise volume.VolumeFault("recovery_replay_launch_failed") from None
    volume.require(completed.returncode == 0, "recovery_replay_failed")
    volume.require(len(completed.stdout) <= 4096, "recovery_replay_output_limit")
    try:
        return json.loads(completed.stdout)
    except (ValueError, UnicodeError):
        raise volume.VolumeFault("recovery_replay_output_invalid") from None


def recover(root, market, lineage, normalization, base, contract_pin, result_pin, deadline):
    for path in (root, market, lineage, normalization, base):
        recovery_path(path)
    plan, result, before = recovery_evidence(root, contract_pin, result_pin)
    recovery_runtime(plan, (root, market, lineage, normalization))
    replay = replay_frozen(root, market, lineage, normalization, contract_pin, result_pin, deadline)
    volume.require(
        replay
        == {
            "status": "verified_all_ro_no_refit",
            "verification_fits": 0,
            "model_sha256": result["model_sha256"],
        },
        "recovery_replay_binding",
    )
    _, _, after = recovery_evidence(root, contract_pin, result_pin)
    volume.require(before == after, "recovery_evidence_changed")
    volume.require(time.monotonic() < deadline, "compute_stop")
    entry = register_campaign_outcome(
        contract_hash=contract_pin,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=result_pin,
        artifact_root=base,
        repo_root=REPO,
    )
    return {
        "status": "recovered_exact_outcome",
        "verification_fits": 0,
        "contract_sha256": contract_pin,
        "result_sha256": result_pin,
        "registry_sha256": entry.record_sha256,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", nargs="?", choices=("plan", "freeze", "run", "verify", "recover"), default="plan"
    )
    for flag in ("artifact-root", "artifact-base", "market-root", "lineage", "normalization"):
        parser.add_argument("--" + flag, type=Path)
    parser.add_argument("--contract-sha256")
    parser.add_argument("--result-sha256")
    parser.add_argument("--vram-bytes", type=int, default=2 * 1024**3)
    args = parser.parse_args()
    deadline = time.monotonic() + 600
    try:
        if args.mode == "plan":
            print(
                json.dumps({"status": "plan", "study": STUDY, "actual_fits": 0, "broker_calls": 0})
            )
            return 0
        volume.require(
            all(
                (
                    args.artifact_root,
                    args.artifact_base,
                    args.market_root,
                    args.lineage,
                    args.normalization,
                )
            ),
            "explicit_paths_required",
        )
        root, base = args.artifact_root.resolve(), args.artifact_base.resolve()
        allowed = Path("D:/thericher-v2/model-artifacts").resolve()
        volume.require(
            base == (allowed if os.name == "nt" else Path("/app/model_artifacts")),
            "artifact_base_outside_scope",
        )
        volume.require(
            root in (base / "research" / STUDY, *((Path("/study"),) if os.name != "nt" else ())),
            "artifact_root_outside_scope",
        )
        if args.mode == "recover":
            result = recover(
                args.artifact_root,
                args.market_root,
                args.lineage,
                args.normalization,
                args.artifact_base,
                args.contract_sha256,
                args.result_sha256,
                deadline,
            )
        elif args.mode == "freeze":
            result = freeze(
                root, args.market_root, args.lineage, args.normalization, base, args.vram_bytes
            )
        else:
            raw = (root / "contract.json").read_bytes()
            volume.require(smoke.digest(raw) == args.contract_sha256, "exact_contract_pin_required")
            plan = json.loads(raw)
            models = None
            if args.mode == "verify":
                models, expected = read_replay(root, args.result_sha256)
                result, _ = compute(
                    plan, args.market_root, args.lineage, args.normalization, deadline, models
                )
                result["contract_sha256"] = args.contract_sha256
                volume.require(result == expected, "readback_mismatch")
                result = {
                    "status": "verified_all_ro_no_refit",
                    "verification_fits": 0,
                    "model_sha256": result["model_sha256"],
                }
            else:
                from thericher_v2.research.engine_research_agent import (
                    GpuFileLock,
                    resolve_agent_root,
                )

                check_runtime(plan)
                check_pins(plan, args.market_root, args.lineage, args.normalization)
                volume.require(
                    os.environ.get("CUBLAS_WORKSPACE_CONFIG") in (":4096:8", ":16:8"),
                    "deterministic_CUBLAS_config_required",
                )
                with GpuFileLock(resolve_agent_root(base) / "locks/gpu.lock"):
                    register(plan, root, base)
                    smoke.write_once(
                        root / "attempt.json",
                        {
                            "contract_sha256": args.contract_sha256,
                            "started_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    result, models = compute(
                        plan, args.market_root, args.lineage, args.normalization, deadline
                    )
                    result["contract_sha256"] = args.contract_sha256
                    smoke.write_once(root / "models.json", models)
                    smoke.write_once(root / "result.json", result)
                register_campaign_outcome(
                    contract_hash=args.contract_sha256,
                    outcome_class="non_promoting_completed",
                    outcome_reference_sha256=smoke.file_hash(root / "result.json"),
                    artifact_root=base,
                    repo_root=REPO,
                )
                result = {
                    "status": result["status"],
                    "kill": result["comparison"]["status"],
                    "model_sha256": result["model_sha256"],
                    "result_sha256": smoke.file_hash(root / "result.json"),
                }
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        reason = (
            str(error)
            if isinstance(error, (volume.VolumeFault, smoke.SmokeFault))
            else "reader_or_runtime_fault"
        )
        print(
            json.dumps(
                {"status": "input_unavailable", "reason": reason, "raw_error_suppressed": True}
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

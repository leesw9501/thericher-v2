"""Finite offline pooled study; parent alone owns Docker mounts and actual dispatch."""

from __future__ import annotations

import json
import runpy
import signal
import sys
import time
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from thericher_v2.research import kis_pooled_patch_return_development as r  # noqa: E402
from thericher_v2.research.engine_research_agent import (  # noqa: E402
    GpuFileLock,
    resolve_agent_root,
)

q = SimpleNamespace(
    **runpy.run_path(str(REPO / "scripts/run_kis_qqq_dated_downside_development.py"))
)
e = SimpleNamespace(
    **runpy.run_path(str(REPO / "scripts/run_kis_equal_minute_resolution_development.py"))
)
h = q.h
NAME, SECONDS, INDEX_LIMIT = r.NAME, 300, q.INDEX_LIMIT
STAGES = ("cpu_smoke", "load", "prepare", "fit", "inference", "evaluate", "validate", "dispatch")
encode, digest, require, atomic = q.encode, q.digest, q.require, q.atomic
runtime = e.runtime
CODE = tuple(
    dict.fromkeys(
        (
            *q.CODE,
            *e.CODE,
            "scripts/run_kis_pooled_patch_return_development.py",
            "src/thericher_v2/research/kis_pooled_patch_return_development.py",
            "src/thericher_v2/research/sequence_architecture_models.py",
            "src/thericher_v2/research/engine_research_agent.py",
        )
    )
)


def configuration():
    return dict(
        r.configuration(),
        image=h.IMAGE,
        index_metadata_max_bytes=INDEX_LIMIT,
        runtime_resources="pinned Torch2.7+cu128; CPU2/6GiB/swap0/networknone; 300s",
        reconstruction="exact cohort/action/fee/cell replay; NOT learned inference",
    )


def paths(artifacts, inputs):
    for root in (artifacts, inputs):
        h._unlinked_path(root)
        require(root.is_dir() and not root.resolve().is_relative_to(REPO), "external_root")
    require(
        not artifacts.resolve().is_relative_to(inputs.resolve())
        and not inputs.resolve().is_relative_to(artifacts.resolve()),
        "root_overlap",
    )
    output = artifacts / "research" / NAME
    h._unlinked_path(output.parent)
    require(output.parent.is_dir(), "research_root")
    if output.exists() or output.is_symlink():
        h._unlinked_path(output)
    return output


def proposed(inputs, pins):
    require(type(pins) is dict and set(pins) == {t[0] for t in r.TARGETS}, "symbol_index_pins")
    versions = runtime()
    sources = []
    for target in r.TARGETS:
        sources.extend(
            dict(s, symbol=target[0], exchange=target[1])
            for s in q.source_metadata(inputs, pins[target[0]], target=target)
        )
    return dict(
        name=NAME,
        config=configuration(),
        runtime=versions,
        sources=sources,
        code_sha256={p: digest(h._read(REPO / p)) for p in CODE},
    )


def freeze(artifacts, inputs, pins):
    output, contract = paths(artifacts, inputs), proposed(inputs, pins)
    output.mkdir()
    h._unlinked_path(output)
    atomic(output / "precommit.json", contract)
    pin = digest(encode(contract))
    q.register_frozen_campaign(
        contract_hash=pin,
        dataset_hash=digest(encode(contract["sources"])),
        split_hash=digest(encode(configuration())),
        cost_model_hash=digest(encode(r.COSTS)),
        trial_family=NAME,
        holdout_access="none",
        artifact_root=artifacts,
        repo_root=REPO,
    )
    return pin


def verify_contract(artifacts, inputs, pin):
    require(h._hash(pin), "contract_pin")
    output = paths(artifacts, inputs)
    contract = h._json(output / "precommit.json", pin)
    h._fields(contract, ("name", "config", "runtime", "sources", "code_sha256"))
    sources = contract["sources"]
    require(type(sources) is list and len(sources) == 40, "source_count")
    pins = {t[0]: {} for t in r.TARGETS}
    for source, (target, day) in zip(sources, r.product(r.TARGETS, r.DATES), strict=True):
        h._fields(
            source,
            (
                "date",
                "root",
                "index_sha256",
                "dataset_id",
                "dataset_sha256",
                "manifests",
                "symbol",
                "exchange",
            ),
        )
        require(
            (source["symbol"], source["exchange"], source["date"]) == (*target, str(day)),
            "source_order",
        )
        pins[target[0]][str(day)] = source["index_sha256"]
    require(encode(contract) == encode(proposed(inputs, pins)), "contract_changed")
    return output, contract


def load_panel(inputs, contract):
    windows, catalogs = (), {}
    for source in contract["sources"]:
        day = date.fromisoformat(source["date"])
        catalog = q.data.load_verified_kis_paper_private_intraday_catalog(
            cache_root=inputs / source["root"],
            repo_root=REPO,
            symbol=source["symbol"],
            exchange=source["exchange"],
            expected_index_metadata_sha256=source["index_sha256"],
        )
        require(
            (catalog.dataset_id, catalog.dataset_hash)
            == (source["dataset_id"], source["dataset_sha256"]),
            "dataset_changed",
        )
        prepared = q.data.prepare_kis_paper_intraday_feature_input(catalog, session_dates=(day,))
        windows += r.build_windows(prepared)
        catalogs[source["symbol"], day] = prepared.catalog
    r.check_cohort(windows)
    return windows, catalogs


def cohort_hash(windows):
    return q.cohort_hash(windows)


def failure(pin, phase, stage, counts="unobserved"):
    return dict(
        name=NAME,
        contract_sha256=pin,
        phase=phase,
        status="failed",
        failure_stage=stage,
        fits_started=counts,
    )


def validate_result(value, pin, phase):
    complete = value.get("status") == "complete"
    extra = ("smoke",) if phase == "cpu-smoke" else ("cohort_sha256", "evaluation")
    h._fields(
        value,
        (
            "name",
            "contract_sha256",
            "phase",
            "status",
            "fits_started",
            *(extra if complete else ("failure_stage",)),
        ),
    )
    require(
        value["name"] == NAME
        and value["contract_sha256"] == pin
        and value["phase"] == phase
        and phase in ("cpu-smoke", "cuda")
        and value["status"] in ("complete", "failed"),
        "result_binding",
    )
    counts = value["fits_started"]
    if not complete:
        require(
            type(value["failure_stage"]) is str and value["failure_stage"] in STAGES,
            "failure_stage",
        )
        if counts == "unobserved":
            return
    h._fields(counts, r.MODELS)
    require(all(type(v) is int and 0 <= v <= 1 for v in counts.values()), "fit_counts")
    require(phase != "cpu-smoke" or counts == dict.fromkeys(r.MODELS, 0), "smoke_actual_fits")
    if not complete:
        return
    if phase == "cpu-smoke":
        require(
            counts == dict.fromkeys(r.MODELS, 0)
            and encode(value["smoke"])
            == encode(
                dict(
                    synthetic_windows=r.WINDOW_COUNT,
                    synthetic_fits=6,
                    actual_fits=0,
                    cells=42,
                    verified=True,
                )
            ),
            "smoke_shape",
        )
    else:
        require(
            counts == dict.fromkeys(r.MODELS, 1) and h._hash(value["cohort_sha256"]),
            "complete_fits",
        )
        v = value["evaluation"]
        h._fields(v, ("commit_sha256", "daily", "cells", "descriptive"))
        require(
            h._hash(v["commit_sha256"])
            and type(v["daily"]) is list
            and len(v["daily"]) == 18
            and type(v["cells"]) is list
            and len(v["cells"]) == 42,
            "cell_count",
        )
        kills = v["descriptive"]["kill_categories"]
        require(
            type(kills) is list
            and all(type(k) is str and k in r.KILLS for k in kills)
            and len(set(kills)) == len(kills),
            "kill_categories",
        )


def verify_replay(value, inputs, contract):
    windows, catalogs = load_panel(inputs, contract)
    require(value["cohort_sha256"] == cohort_hash(windows), "cohort_binding")
    r.verify_evaluation(
        windows,
        r.payoffs(windows, catalogs, r.TRAIN),
        r.payoffs(windows, catalogs, r.COMPARISON),
        value["evaluation"],
    )


def readback(artifacts, inputs, pin, summary_pin):
    require(h._hash(summary_pin), "summary_pin")
    output, contract = verify_contract(artifacts, inputs, pin)
    value = h._json(output / "cuda-summary.json", summary_pin)
    validate_result(value, pin, "cuda")
    require(
        {p.name for p in output.iterdir()} - {"cuda-worker.json"}
        == {
            "precommit.json",
            "cpu-smoke-started.json",
            "cpu-smoke-worker.json",
            "cpu-smoke-summary.json",
            "cuda-started.json",
            "cuda-summary.json",
        },
        "output_changed",
    )
    smoke_receipt(output, pin)
    require(h._json(output / "cuda-started.json") == dict(contract_sha256=pin), "attempt")
    if value["status"] == "complete":
        require(encode(h._json(output / "cuda-worker.json")) == encode(value), "worker_binding")
        verify_replay(value, inputs, contract)
        verify_contract(artifacts, inputs, pin)
    elif value["fits_started"] != "unobserved":
        candidate = h._json(output / "cuda-worker.json")
        validate_result(candidate, pin, "cuda")
        require(candidate["fits_started"] == value["fits_started"], "worker_binding")
    return dict(
        status="verified_" + value["status"],
        contract_sha256=pin,
        summary_sha256=summary_pin,
        cells=42 if value["status"] == "complete" else 0,
        learned_inference_reconstructed=False,
    )


def smoke_receipt(output, pin, summary_pin=None):
    smoke = h._json(output / "cpu-smoke-summary.json", summary_pin)
    validate_result(smoke, pin, "cpu-smoke")
    require(
        smoke["status"] == "complete"
        and h._json(output / "cpu-smoke-started.json") == dict(contract_sha256=pin)
        and encode(h._json(output / "cpu-smoke-worker.json")) == encode(smoke),
        "smoke_incomplete",
    )


def worker(artifacts, inputs, pin, phase, deadline):
    output = None
    counts, progress = (
        dict.fromkeys(r.MODELS, 0),
        dict(stage="cpu_smoke" if phase == "cpu-smoke" else "load"),
    )
    try:
        output = paths(artifacts, inputs)
        verify_contract(artifacts, inputs, pin)
        require(h._json(output / (phase + "-started.json")) == dict(contract_sha256=pin), "attempt")
        if phase == "cpu-smoke":
            result = dict(smoke=r.cpu_smoke(deadline))
        else:
            import torch

            progress["stage"] = "load"
            require(torch.cuda.is_available(), "CUDA_unavailable")
            _, contract = verify_contract(artifacts, inputs, pin)
            windows, catalogs = load_panel(inputs, contract)
            progress["stage"] = "prepare"
            train = r.payoffs(windows, catalogs, r.TRAIN)
            actions = r.fit_actions(
                windows, train, counts, deadline, device="cuda", progress=progress
            )
            # Seal every policy's inference before asking for any comparison payoff.
            commit = r.commitment(actions)
            progress["stage"] = "evaluate"
            gross = r.payoffs(windows, catalogs, r.COMPARISON)
            evaluation = r.aggregate(windows, gross, actions)
            require(evaluation["commit_sha256"] == commit, "inference_commit_changed")
            r.verify_evaluation(windows, train, gross, evaluation)
            result = dict(cohort_sha256=cohort_hash(windows), evaluation=evaluation)
        progress["stage"] = "validate"
        result.update(
            name=NAME, contract_sha256=pin, phase=phase, status="complete", fits_started=counts
        )
        validate_result(result, pin, phase)
        verify_contract(artifacts, inputs, pin)
        require(time.monotonic() < deadline, "hard_timeout")
    except (Exception, KeyboardInterrupt):
        result = failure(pin, phase, progress["stage"], counts)
    if output is not None:
        try:
            atomic(output / (phase + "-worker.json"), result)
        except Exception:
            pass


def dispatch(artifacts, inputs, pin, phase, smoke_pin=None):
    deadline = time.monotonic() + SECONDS
    output, _ = verify_contract(artifacts, inputs, pin)
    allowed = {"precommit.json"}
    if phase == "cuda":
        require(h._hash(smoke_pin), "smoke_pin")
        smoke_receipt(output, pin, smoke_pin)
        allowed |= {"cpu-smoke-started.json", "cpu-smoke-worker.json", "cpu-smoke-summary.json"}
    require(
        phase in ("cpu-smoke", "cuda") and {p.name for p in output.iterdir()} == allowed,
        "single_attempt",
    )
    supervisor = runpy.run_path(str(REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))[
        "supervise"
    ]
    lock = nullcontext()
    if phase == "cuda":
        lock_path = resolve_agent_root(artifacts) / "locks/gpu.lock"
        for directory in (lock_path.parent.parent, lock_path.parent):
            h._unlinked_path(directory.parent)
            if not directory.exists() and not directory.is_symlink():
                directory.mkdir()
            h._unlinked_path(directory)
        if lock_path.exists() or lock_path.is_symlink():
            h._unlinked_path(lock_path)
        lock = GpuFileLock(lock_path)
    atomic(output / (phase + "-started.json"), dict(contract_sha256=pin))
    result = failure(pin, phase, "dispatch")
    try:
        with lock:
            require(time.monotonic() < deadline, "hard_timeout")
            job = supervisor(
                worker,
                (artifacts, inputs, pin, phase, deadline),
                seconds=deadline - time.monotonic(),
                name=NAME + "-" + phase,
            )
            candidate = h._json(output / (phase + "-worker.json"))
            validate_result(candidate, pin, phase)
            result["fits_started"] = candidate["fits_started"]
            require(
                job["timed_out"] is False
                and type(job["exit_code"]) is int
                and job["exit_code"] == 0,
                "worker_failed",
            )
            _, contract = verify_contract(artifacts, inputs, pin)
            if phase == "cuda" and candidate["status"] == "complete":
                verify_replay(candidate, inputs, contract)
                verify_contract(artifacts, inputs, pin)
            require(
                {p.name for p in output.iterdir()}
                == allowed | {phase + "-started.json", phase + "-worker.json"}
                and time.monotonic() < deadline,
                "output_changed",
            )
            result = candidate
    except (Exception, KeyboardInterrupt):
        pass
    validate_result(result, pin, phase)
    atomic(output / (phase + "-summary.json"), result)
    if phase == "cuda":
        q.register_campaign_outcome(
            contract_hash=pin,
            outcome_class="non_promoting_completed"
            if result["status"] == "complete"
            else "non_promoting_failed",
            outcome_reference_sha256=digest(encode(result)),
            artifact_root=artifacts,
            repo_root=REPO,
        )
    return dict(
        status=result["status"],
        phase=phase,
        contract_sha256=pin,
        summary_sha256=digest(encode(result)),
        fits_started=result["fits_started"],
        cells=42 if phase == "cuda" and result["status"] == "complete" else 0,
    )


def main(argv=None):
    try:
        parser = h._Parser(description=__doc__, allow_abbrev=False)
        mode = parser.add_mutually_exclusive_group()
        for flag in ("freeze", "cpu-smoke", "cuda", "verify"):
            mode.add_argument("--" + flag, action="store_true")
        parser.add_argument("--artifact-root", type=Path, default=Path("/artifacts"))
        parser.add_argument("--input-root", type=Path, default=Path("/input"))
        for flag in ("qqq-index-pins", "spy-index-pins"):
            parser.add_argument("--" + flag, type=Path)
        for flag in ("contract-sha256", "smoke-summary-sha256", "summary-sha256"):
            parser.add_argument("--" + flag)
        args = parser.parse_args(argv)
        if not any((args.freeze, args.cpu_smoke, args.cuda, args.verify)):
            result = dict(
                status="preview",
                cells=42,
                actual_fits=3,
                synthetic_smoke_fits=6,
                image=h.IMAGE,
                wall_seconds=300,
                cpu_threads=2,
                memory_bytes=6 * 1024**3,
                network="none",
                weights_retained=False,
            )
        else:
            require(
                (
                    args.freeze
                    and args.qqq_index_pins is not None
                    and args.spy_index_pins is not None
                    and args.contract_sha256 is None
                )
                or (
                    not args.freeze
                    and args.qqq_index_pins is None
                    and args.spy_index_pins is None
                    and h._hash(args.contract_sha256)
                ),
                "mode_arguments",
            )
            require(
                (args.cuda and h._hash(args.smoke_summary_sha256))
                or (not args.cuda and args.smoke_summary_sha256 is None),
                "smoke_arguments",
            )
            require(
                (args.verify and h._hash(args.summary_sha256))
                or (not args.verify and args.summary_sha256 is None),
                "summary_arguments",
            )
            if args.freeze:
                result = dict(
                    status="frozen_metadata_only",
                    contract_sha256=freeze(
                        args.artifact_root,
                        args.input_root,
                        dict(QQQ=h._json(args.qqq_index_pins), SPY=h._json(args.spy_index_pins)),
                    ),
                )
            elif args.verify:
                result = readback(
                    args.artifact_root, args.input_root, args.contract_sha256, args.summary_sha256
                )
            else:
                previous = signal.signal(signal.SIGTERM, h._interrupt)
                try:
                    result = dispatch(
                        args.artifact_root,
                        args.input_root,
                        args.contract_sha256,
                        "cpu-smoke" if args.cpu_smoke else "cuda",
                        args.smoke_summary_sha256,
                    )
                finally:
                    signal.signal(signal.SIGTERM, previous)
    except (Exception, KeyboardInterrupt):
        result = dict(status="unavailable", raw_error_suppressed=True)
    print(json.dumps(result, sort_keys=True), flush=True)
    return (
        0
        if result["status"] in ("preview", "frozen_metadata_only", "complete", "verified_complete")
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

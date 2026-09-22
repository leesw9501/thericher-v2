"""Synthetic parent custody tests: no market data, model runtimes, or child jobs."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import runpy
import signal
import socket
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from thericher_v2 import research
from thericher_v2.research import firstrate_family_comparison as real_study

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts/run_firstrate_family_comparison.py"
SUPERVISOR = REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"
HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
COUNTS = {"cpu": 4, "cuda": 16}


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@pytest.fixture(autouse=True)
def block_external_surfaces(monkeypatch):
    original_import, original_open = builtins.__import__, Path.open

    def checked_import(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "lightgbm"} and not getattr(
            sys.modules.get(name), "_runner_test_double", False
        ):
            pytest.fail(f"forbidden actual model runtime import: {name}")
        if any(part in name.lower() for part in ("broker", "credential", "dotenv", "kis_")):
            pytest.fail(f"forbidden runtime or broker import: {name}")
        return original_import(name, *args, **kwargs)

    def checked_open(path, *args, **kwargs):
        normalized = str(path).replace("\\", "/").lower()
        if normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts")) or any(
            part in path.parts for part in ("market-source-blocked", ".env", ".env.local")
        ):
            pytest.fail("source or private-state read attempted")
        return original_open(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("network, subprocess, or actual runtime attempted")

    monkeypatch.setattr(builtins, "__import__", checked_import)
    monkeypatch.setattr(Path, "open", checked_open)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    for name in THREAD_ENV:
        monkeypatch.setenv(name, "7")
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":16:8")


@pytest.fixture
def harness(tmp_path, monkeypatch):
    output = tmp_path / "research/fake-family/family-comparison-v1"
    output.mkdir(parents=True)
    state = SimpleNamespace(
        output=output,
        root=tmp_path,
        market=tmp_path / "market-source-blocked",
        mode="complete",
        calls=[],
        outcomes=[],
        events=[],
        loaded=[],
        cpu_hash=None,
    )
    study = ModuleType("thericher_v2.research.firstrate_family_comparison")
    study.NAME, study.FAMILY, study.REPO = "family-comparison-v1", "fake-family", REPO
    study.SECONDS = {"cpu": 600, "cuda": 900}
    study.h30 = SimpleNamespace(encode=encode, digest=digest)

    def freeze(root):
        assert root == tmp_path
        state.events.append("freeze")
        return HASH

    def verify(root, scope_hash):
        assert root == tmp_path and scope_hash == HASH
        state.events.append("verify")
        return output, b"synthetic-receipt", {"name": study.NAME}

    def failure(phase, scope_hash, reason):
        return dict(
            name=study.NAME,
            status="failed_all_phase_cells",
            phase=phase,
            contract_sha256=scope_hash,
            reason=reason,
            cells=[],
            folds=[],
            fits=[],
            models=[],
            promotion=False,
            holdout_access=False,
        )

    def complete(phase):
        result = failure(phase, HASH, "unused")
        result.update(
            status="complete",
            cells=[{"cell": 1}, {"cell": 2}],
            fits=list(range(COUNTS[phase])),
            models=[
                {
                    "weights_file": f"model-{i}.{'text' if phase == 'cpu' else 'npz'}",
                    "config_file": f"model-{i}.json",
                }
                for i in range(COUNTS[phase])
            ],
            cpu_summary_sha256=state.cpu_hash if phase == "cuda" else None,
        )
        return result

    def validate_result(result, phase, scope_hash):
        state.events.append(f"validate-{phase}")
        if (
            result["name"] != study.NAME
            or result["status"] != "complete"
            or result["phase"] != phase
            or result["contract_sha256"] != scope_hash
            or result["cells"] != [{"cell": 1}, {"cell": 2}]
            or result["fits"] != list(range(COUNTS[phase]))
        ):
            raise ValueError("PRIVATE invalid result details")

    def verify_models(root, result, scope_hash):
        phase = result["phase"]
        assert scope_hash == HASH and root.name == "models"
        assert root.parent.parent == output
        assert state.lock.is_file() == (phase == "cuda")
        assert not (output / f"{phase}-models").exists()
        state.events.append(f"reload-{phase}")
        for ref in result["models"]:
            if (root / ref["weights_file"]).read_bytes() != b"synthetic model":
                raise ValueError("PRIVATE model bytes invalid")
            if json.loads((root / ref["config_file"]).read_bytes()) != {"contract_sha256": HASH}:
                raise ValueError("PRIVATE model metadata invalid")
            state.loaded.append((phase, ref["weights_file"]))

    def worker(*args):
        pytest.fail("actual worker must not run")

    for function in (freeze, verify, failure, validate_result, verify_models, worker):
        setattr(study, function.__name__, function)
    monkeypatch.setitem(sys.modules, study.__name__, study)
    monkeypatch.setattr(research, "firstrate_family_comparison", study, raising=False)
    cli = runpy.run_path(str(RUNNER))
    ns = cli["dispatch"].__globals__
    state.cli, state.ns, state.study, state.complete = cli, ns, study, complete
    state.lock = ns["resolve_agent_root"](tmp_path) / "locks/gpu.lock"
    original_lock = ns["GpuFileLock"]

    def lock_factory(path):
        state.events.append("lock")
        assert path == state.lock
        return original_lock(path)

    monkeypatch.setitem(ns, "GpuFileLock", lock_factory)

    def supervise(target, args, *, seconds, name):
        state.events.append("supervise")
        state.calls.append((target, args, seconds, name))
        root, market, scope_hash, phase, cpu_hash, path = args
        assert target is worker
        assert (root, market, scope_hash) == (tmp_path, state.market, HASH)
        assert cpu_hash == (state.cpu_hash if phase == "cuda" else None)
        assert seconds == study.SECONDS[phase] and name == study.NAME
        assert path.parent.parent == output and not path.is_relative_to(REPO)
        assert json.loads((output / f"{phase}-started.json").read_bytes()) == {
            "name": study.NAME,
            "parent_pid": os.getpid(),
            "contract_sha256": HASH,
            "hard_timeout_seconds": seconds,
        }
        if phase == "cuda":
            assert json.loads(state.lock.read_bytes())["pid"] == os.getpid()
            assert "validate-cpu" in state.events[:-1]
        assert all(os.environ[name] == "1" for name in THREAD_ENV)
        assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"
        result = complete(phase)
        models = path.parent / "models"
        models.mkdir()
        for ref in result["models"]:
            (models / ref["weights_file"]).write_bytes(b"synthetic model")
            (models / ref["config_file"]).write_bytes(encode({"contract_sha256": HASH}))
        if state.mode == "preempt":
            raise KeyboardInterrupt
        if state.mode == "sigterm":
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        if state.mode == "supervisor_error":
            raise RuntimeError("PRIVATE worker error")
        if state.mode == "identity":
            result["contract_sha256"] = OTHER_HASH
        if state.mode in {"cells", "fits", "partial_models"}:
            result["models" if state.mode == "partial_models" else state.mode].pop()
        if state.mode == "empty_models":
            result["models"] = []
        if state.mode == "model_corrupt":
            (models / result["models"][-1]["weights_file"]).write_bytes(b"PRIVATE corrupt")
        if state.mode == "model_missing":
            (models / result["models"][-1]["weights_file"]).unlink()
        if state.mode == "metadata_corrupt":
            (models / result["models"][-1]["config_file"]).write_bytes(b"PRIVATE metadata")
        if state.mode == "failed_result":
            result = failure(phase, HASH, "PRIVATE untrusted reason")
        if state.mode == "safe_failure":
            result = failure(phase, HASH, state.reason)
            result["cells"] = [{"PRIVATE": "discard even on a trusted failure reason"}]
            result["private_extra"] = "PRIVATE"
            if hasattr(state, "support"):
                result["support"] = state.support
        if state.mode == "not_mapping":
            result = ["PRIVATE"]
        if state.mode != "missing":
            path.write_bytes(
                b"PRIVATE malformed JSON" if state.mode == "malformed" else encode(result)
            )
        return {"timed_out": state.mode == "timeout", "exit_code": 5 if state.mode == "exit" else 0}

    def load_supervisor(path):
        assert Path(path) == SUPERVISOR
        state.events.append("load_supervisor")
        return {"supervise": supervise}

    def register(**kwargs):
        state.events.append("register")
        assert not state.lock.exists()
        state.outcomes.append(kwargs)

    monkeypatch.setattr(ns["runpy"], "run_path", load_supervisor)
    monkeypatch.setitem(ns, "register_campaign_outcome", register)
    return state


def seed_cpu(harness):
    raw = encode(harness.complete("cpu"))
    (harness.output / "cpu-summary.json").write_bytes(raw)
    harness.cpu_hash = digest(raw)


def arguments(harness, phase="cpu"):
    args = [
        "--phase",
        phase,
        "--contract-sha256",
        HASH,
        "--artifact-root",
        str(harness.root),
        "--market-data-root",
        str(harness.market),
    ]
    if phase == "cuda":
        args += ["--cpu-summary-sha256", harness.cpu_hash or OTHER_HASH]
    return args


def invoke(harness, capsys, phase="cpu"):
    previous = signal.getsignal(signal.SIGTERM)
    code = harness.cli["main"](arguments(harness, phase))
    assert signal.getsignal(signal.SIGTERM) == previous
    captured = capsys.readouterr()
    assert not captured.err and "PRIVATE" not in captured.out
    return code, json.loads(captured.out)


def assert_outcome(harness, phase, completed):
    raw = (harness.output / f"{phase}-summary.json").read_bytes()
    assert "PRIVATE" not in raw.decode()
    assert harness.outcomes == [
        {
            "contract_hash": HASH,
            "outcome_class": "non_promoting_completed" if completed else "non_promoting_failed",
            "outcome_reference_sha256": digest(raw),
            "artifact_root": harness.root,
            "repo_root": REPO,
        }
    ]
    assert harness.events[-1] == "register"


def test_freeze_only_metadata_no_lock_supervisor_or_outcome(harness, capsys):
    previous = signal.getsignal(signal.SIGTERM)
    assert harness.cli["main"](["--freeze", "--artifact-root", str(harness.root)]) == 0
    assert signal.getsignal(signal.SIGTERM) == previous
    assert json.loads(capsys.readouterr().out) == {
        "status": "frozen_metadata_only",
        "contract_sha256": HASH,
    }
    assert harness.events == ["freeze"] and not harness.outcomes
    assert not list(harness.output.iterdir())


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--freeze", "--phase", "cpu"],
        ["--phase", "cpu"],
        ["--freeze", "--contract-sha256", HASH],
        ["--freeze", "--contract-sha256", ""],
        ["--freeze", "--cpu-summary-sha256", OTHER_HASH],
        ["--freeze", "--cpu-summary-sha256", ""],
        ["--phase", "cuda", "--contract-sha256", HASH],
        ["--phase", "cpu", "--contract-sha256", HASH, "--cpu-summary-sha256", OTHER_HASH],
        ["--phase", "cpu", "--contract-sha256", HASH, "--cpu-summary-sha256", ""],
        ["--phase", "cpu", "--contract-sha256", ""],
        ["--phase", "cuda", "--contract-sha256", HASH, "--cpu-summary-sha256", ""],
    ],
)
def test_invalid_cli_rejected_before_io(harness, args):
    with pytest.raises(SystemExit) as error:
        harness.cli["main"](args)
    assert error.value.code == 2 and not harness.events


def test_cli_external_defaults_and_fixed_environment(harness, monkeypatch, capsys):
    captured = []

    def dispatch(args):
        captured.append(args)
        assert all(os.environ[name] == "1" for name in THREAD_ENV)
        assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"
        return {"status": "complete"}

    monkeypatch.setitem(harness.ns, "dispatch", dispatch)
    assert harness.cli["main"](["--phase", "cpu", "--contract-sha256", HASH]) == 0
    assert captured[0].artifact_root == Path("D:/thericher-v2/model-artifacts")
    assert captured[0].market_data_root == Path("D:/market_data")
    assert captured[0].cpu_summary_sha256 is None
    assert json.loads(capsys.readouterr().out) == {"status": "complete"}
    assert not harness.events


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
def test_complete_phase_retains_all_models_once_after_parent_reload(harness, capsys, phase):
    if phase == "cuda":
        seed_cpu(harness)
    code, report = invoke(harness, capsys, phase)
    assert code == 0 and report["status"] == "complete"
    assert report["cells"] == 2 and report["models"] == COUNTS[phase]
    assert len(harness.calls) == 1 and len(harness.loaded) == COUNTS[phase]
    assert not harness.lock.exists() and not list(harness.output.glob("*-job-*"))
    models = harness.output / f"{phase}-models"
    assert len(list(models.iterdir())) == 2 * COUNTS[phase]
    assert not (harness.output / "models").exists()
    assert harness.events.index(f"validate-{phase}") < harness.events.index(f"reload-{phase}")
    if phase == "cuda":
        assert harness.events.index("validate-cpu") < harness.events.index("load_supervisor")
        assert_outcome(harness, phase, True)
    else:
        assert "lock" not in harness.events and not harness.outcomes
    summary = harness.output / f"{phase}-summary.json"
    raw = summary.read_bytes()
    assert report["summary_sha256"] == digest(raw)
    outcomes = list(harness.outcomes)
    assert invoke(harness, capsys, phase)[0] == 1
    assert summary.read_bytes() == raw and len(harness.calls) == 1
    assert harness.outcomes == outcomes and not harness.lock.exists()


def test_cpu_then_cuda_preserves_both_phase_model_namespaces(harness, capsys):
    assert invoke(harness, capsys)[0] == 0
    raw = (harness.output / "cpu-summary.json").read_bytes()
    harness.cpu_hash = digest(raw)
    models = harness.output / "cpu-models"
    before = {path.name: path.read_bytes() for path in models.iterdir()}
    assert invoke(harness, capsys, "cuda")[0] == 0
    assert (harness.output / "cpu-summary.json").read_bytes() == raw
    assert {path.name: path.read_bytes() for path in models.iterdir()} == before
    assert len(list((harness.output / "cuda-models").iterdir())) == 32
    assert len(harness.calls) == 2
    assert_outcome(harness, "cuda", True)


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
def test_failed_atomic_model_move_leaves_empty_failure_and_cleans_temporary(
    harness, monkeypatch, capsys, phase
):
    if phase == "cuda":
        seed_cpu(harness)
    original_rename = Path.rename

    def rename(path, destination):
        if path.name == "models":
            assert len(harness.loaded) == COUNTS[phase]
            assert destination == harness.output / f"{phase}-models"
            raise OSError("PRIVATE rename error")
        return original_rename(path, destination)

    monkeypatch.setattr(Path, "rename", rename)
    code, report = invoke(harness, capsys, phase)
    assert code == 1 and report["cells"] == report["models"] == 0
    assert not (harness.output / f"{phase}-models").exists()
    assert not list(harness.output.glob("*-job-*")) and not harness.lock.exists()
    assert_outcome(harness, phase, False)


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
@pytest.mark.parametrize(
    "mode",
    [
        "timeout",
        "exit",
        "missing",
        "malformed",
        "not_mapping",
        "identity",
        "cells",
        "fits",
        "failed_result",
        "preempt",
        "sigterm",
        "supervisor_error",
        "empty_models",
        "partial_models",
        "model_corrupt",
        "model_missing",
        "metadata_corrupt",
    ],
)
def test_failed_phase_is_empty_and_never_moves_models(harness, capsys, phase, mode):
    if phase == "cuda":
        seed_cpu(harness)
    harness.mode = mode
    code, report = invoke(harness, capsys, phase)
    assert code == 1 and report["status"] == "failed_all_phase_cells"
    assert report["cells"] == report["models"] == 0 and len(harness.calls) == 1
    assert not harness.lock.exists() and not list(harness.output.glob("*-job-*"))
    assert not (harness.output / f"{phase}-models").exists()
    summary = json.loads((harness.output / f"{phase}-summary.json").read_bytes())
    assert summary["cells"] == summary["folds"] == summary["fits"] == summary["models"] == []
    if mode in {"preempt", "sigterm"}:
        assert summary["reason"] == "execution_preempted"
    if mode in {"model_corrupt", "model_missing", "metadata_corrupt"}:
        assert len(harness.loaded) == COUNTS[phase] - 1 and summary["reason"] == "model_reload"
    else:
        assert not harness.loaded
    assert_outcome(harness, phase, False)


@pytest.mark.parametrize("reason", ["parent_control_mismatch", "model_reload", "lightgbm_version"])
def test_identity_bound_failure_preserves_only_allowlisted_reason(harness, capsys, reason):
    harness.mode, harness.reason = "safe_failure", reason
    assert invoke(harness, capsys)[0] == 1
    summary = json.loads((harness.output / "cpu-summary.json").read_bytes())
    assert summary["reason"] == reason and summary["cells"] == []
    assert "private_extra" not in summary
    assert_outcome(harness, "cpu", False)


def test_safe_support_counters_preserved_without_partial_cells(harness, capsys):
    harness.mode, harness.reason = "safe_failure", "evaluation_outcome_support_shortfall"
    harness.support = dict(eligible=100, observed=0, censored=100, blocks=0)
    assert invoke(harness, capsys)[0] == 1
    summary = json.loads((harness.output / "cpu-summary.json").read_bytes())
    assert summary["support"] == harness.support and summary["cells"] == []
    assert_outcome(harness, "cpu", False)


@pytest.mark.parametrize(
    "support",
    [
        "PRIVATE",
        {},
        dict(eligible=True, observed=0, censored=1, blocks=0),
        dict(eligible=10, observed=5, censored=4, blocks=1),
        dict(eligible=10, observed=5, censored=5, blocks=6),
        dict(eligible=-1, observed=0, censored=-1, blocks=0),
        dict(eligible=1000001, observed=0, censored=1000001, blocks=0),
    ],
)
def test_bad_failure_support_becomes_generic_empty_result(harness, capsys, support):
    harness.mode, harness.reason, harness.support = "safe_failure", "source_hash", support
    assert invoke(harness, capsys)[0] == 1
    summary = json.loads((harness.output / "cpu-summary.json").read_bytes())
    assert summary["reason"] == "worker_result_invalid" and "support" not in summary
    assert_outcome(harness, "cpu", False)


@pytest.mark.parametrize(
    "mode", ["missing", "hash", "identity", "failed", "cells", "models", "json"]
)
def test_cuda_rejects_unmatched_or_incomplete_cpu_before_child_dispatch(harness, capsys, mode):
    if mode != "missing":
        cpu = harness.complete("cpu")
        if mode == "identity":
            cpu["contract_sha256"] = OTHER_HASH
        if mode == "failed":
            cpu["status"] = "failed_all_phase_cells"
        if mode in {"cells", "models"}:
            cpu[mode].pop()
        raw = b"PRIVATE invalid JSON" if mode == "json" else encode(cpu)
        (harness.output / "cpu-summary.json").write_bytes(raw)
        harness.cpu_hash = OTHER_HASH if mode == "hash" else digest(raw)
    code, report = invoke(harness, capsys, "cuda")
    assert code == 1 and report["cells"] == report["models"] == 0
    assert not harness.calls and "load_supervisor" not in harness.events
    assert not harness.lock.exists() and not list(harness.output.glob("*-job-*"))
    assert_outcome(harness, "cuda", False)


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
@pytest.mark.parametrize("artifact", ["started", "summary", "models"])
def test_existing_phase_evidence_is_immutable(harness, capsys, phase, artifact):
    if phase == "cuda":
        seed_cpu(harness)
    path = harness.output / f"{phase}-{artifact}{'' if artifact == 'models' else '.json'}"
    if artifact == "models":
        path.mkdir()
        path = path / "prior-model"
    path.write_bytes(b"immutable evidence")
    assert invoke(harness, capsys, phase)[0] == 1
    assert path.read_bytes() == b"immutable evidence"
    assert not harness.calls and not harness.outcomes and not harness.lock.exists()


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
def test_cpu_does_not_observe_gpu_ownership(harness, capsys, phase):
    if phase == "cuda":
        seed_cpu(harness)
    harness.lock.parent.mkdir(parents=True)
    harness.lock.write_text("other owner", encoding="ascii")
    if phase == "cpu":
        # This assertion concerns the runner lock, not the unrelated owner's lock.
        harness.study.verify_models = lambda *args: None
    assert invoke(harness, capsys, phase)[0] == (1 if phase == "cuda" else 0)
    assert harness.lock.read_text(encoding="ascii") == "other owner"
    assert len(harness.calls) == (0 if phase == "cuda" else 1)
    assert not harness.outcomes


@pytest.mark.parametrize("boundary", ["freeze", "verify", "register"])
def test_outer_failure_suppresses_exception_and_restores_signal(
    harness, monkeypatch, capsys, boundary
):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE exception detail")

    seed_cpu(harness)
    if boundary == "register":
        monkeypatch.setitem(harness.ns, "register_campaign_outcome", fail)
    else:
        monkeypatch.setattr(harness.study, boundary, fail)
    previous = signal.getsignal(signal.SIGTERM)
    argv = (
        ["--freeze", "--artifact-root", str(harness.root)]
        if boundary == "freeze"
        else arguments(harness, "cuda")
    )
    assert harness.cli["main"](argv) == 1
    assert signal.getsignal(signal.SIGTERM) == previous
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    assert json.loads(captured.out) == {
        "status": "dispatch_unavailable",
        "raw_error_suppressed": True,
    }
    assert not harness.lock.exists()
    if boundary == "register":
        assert (harness.output / "cuda-summary.json").is_file()
    else:
        assert not harness.calls


@pytest.mark.parametrize("mode", ["freeze", "cpu"])
def test_git_artifact_root_rejected_before_study_io(harness, capsys, mode):
    harness.root = REPO / "must-not-create-family-artifacts"
    argv = (
        ["--freeze", "--artifact-root", str(harness.root)]
        if mode == "freeze"
        else arguments(harness)
    )
    assert harness.cli["main"](argv) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "dispatch_unavailable"
    assert not harness.events and not harness.root.exists()


@pytest.mark.parametrize("mode", ["timeout", "sigint", "sigterm"])
def test_reused_spawn_supervisor_reaps_before_parent_lock_release(tmp_path, monkeypatch, mode):
    stub = ModuleType("thericher_v2.research.firstrate_family_comparison")
    monkeypatch.setitem(sys.modules, stub.__name__, stub)
    monkeypatch.setattr(research, "firstrate_family_comparison", stub, raising=False)
    cli = runpy.run_path(str(RUNNER))
    parent = ModuleType("thericher_v2.research.firstrate_m5_h30_lstm_dev_20260921")
    monkeypatch.setitem(sys.modules, parent.__name__, parent)
    monkeypatch.setattr(research, "firstrate_m5_h30_lstm_dev_20260921", parent, raising=False)
    supervisor = runpy.run_path(str(SUPERVISOR))["supervise"]
    lock = tmp_path / "gpu.lock"
    events = []

    class Process:
        pid, exitcode = 123, -9
        alive = True

        def start(self):
            assert lock.is_file()
            events.append("start")

        def join(self, seconds=None):
            assert lock.is_file()
            events.append(("join", seconds))
            if len(events) == 2:
                if mode == "sigint":
                    raise KeyboardInterrupt
                if mode == "sigterm":
                    cli["interrupt"](signal.SIGTERM, None)

        def is_alive(self):
            return self.alive

        def terminate(self):
            assert lock.is_file()
            events.append("terminate")

        def kill(self):
            assert lock.is_file()
            events.append("kill")
            self.alive = False

        def close(self):
            events.append("close")

    def context(method):
        assert method == "spawn"

        def create(**kwargs):
            assert kwargs == {"target": None, "args": (), "name": "fake-phase", "daemon": False}
            return Process()

        return SimpleNamespace(Process=create)

    monkeypatch.setattr(supervisor.__globals__["multiprocessing"], "get_context", context)
    with cli["GpuFileLock"](lock):
        if mode == "timeout":
            result = supervisor(None, (), seconds=0, name="fake-phase")
            assert result["timed_out"] is True and result["exit_code"] == -9
        else:
            with pytest.raises(KeyboardInterrupt):
                supervisor(None, (), seconds=0, name="fake-phase")
    assert not lock.exists()
    assert events[:6] == ["start", ("join", 0), "terminate", ("join", 2), "kill", ("join", None)]


def real_complete(phase, scope_hash):
    result = real_study.failure(phase, scope_hash, None)
    result.pop("reason")
    result.update(status="complete", parent_controls_reproduced=84 if phase == "cpu" else 0)
    for symbol in real_study.h30.SYMBOLS:
        for number in (1, 2):
            result["folds"].append(
                dict(
                    symbol=symbol,
                    fold=number,
                    horizon_minutes=30,
                    cohort_sha256=HASH,
                    normalizer_sha256=real_study.h30.digest(
                        np.zeros(4).tobytes()
                        + np.ones(4).tobytes()
                        + real_study.h30.encode([0.0, 1.0])
                    ),
                )
            )
            for cost in real_study.h30.COSTS:
                for identity in real_study.identities(phase):
                    if identity["symbol"] == symbol and identity["fold"] == number:
                        result["cells"].append(
                            dict(
                                **identity,
                                cost_bps_per_side=cost,
                                gross_dollars="1.25",
                                fees_dollars="0.25",
                                net_dollars="1.00",
                                local_paper_replay_parity=True,
                            )
                        )
    for identity in real_study.identities(phase, fitted=True):
        result["fits"].append(
            dict(
                **identity,
                initial_train_mse=1.0,
                final_train_mse=0.75,
                train_mean_baseline_mse=1.0,
                train_rows=129,
                epochs=8,
                updates=16,
            )
        )
    return result


@pytest.fixture
def real_harness(tmp_path, monkeypatch):
    """Real contract/worker/serialization; synthetic lineage, models, and compute."""
    state = SimpleNamespace(
        root=tmp_path,
        market=tmp_path / "market-source-blocked",
        mode="complete",
        calls=[],
        events=[],
        outcomes=[],
        freezes=[],
    )
    cli = runpy.run_path(str(RUNNER))
    ns = cli["dispatch"].__globals__
    assert ns["s"] is real_study
    state.cli, state.ns = cli, ns
    state.lock = ns["resolve_agent_root"](tmp_path) / "locks/gpu.lock"
    receipt = tmp_path / real_study.h30.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b"synthetic normalization receipt")
    monkeypatch.setattr(real_study, "lineage", lambda root: (root / "synthetic-parent", {}))
    monkeypatch.setattr(
        real_study.sessions, "contract", lambda receipt: {"source_pins": {"synthetic": HASH}}
    )
    monkeypatch.setattr(
        real_study.h30, "register_frozen_campaign", lambda **kwargs: state.freezes.append(kwargs)
    )
    state.scope_hash = real_study.freeze(tmp_path)
    state.output, _, _ = real_study.verify(tmp_path, state.scope_hash)

    torch = ModuleType("torch")
    torch._runner_test_double = True
    torch.set_num_threads = lambda count: state.events.append(("threads", count))
    torch.use_deterministic_algorithms = lambda value: state.events.append(("deterministic", value))
    torch.from_numpy = lambda value: value.copy()

    class Sequence:
        def state_dict(self):
            return {"weight": np.zeros(1, dtype=np.float32)}

        def load_state_dict(self, values, *, strict):
            assert strict and set(values) == {"weight"}
            state.events.append("sequence-reload")

    class Booster:
        def __init__(self, *, model_file):
            assert Path(model_file).read_text(encoding="utf-8") == "synthetic booster text"
            state.events.append("tree-reload")

        def num_feature(self):
            return 144

        def num_trees(self):
            return 64

        def predict(self, values):
            return np.zeros(len(values))

    lightgbm = ModuleType("lightgbm")
    lightgbm._runner_test_double, lightgbm.__version__, lightgbm.Booster = True, "4.6.0", Booster
    pools = ModuleType("threadpoolctl")
    pools.threadpool_limits = lambda *, limits: nullcontext()
    for name, module in (("torch", torch), ("lightgbm", lightgbm), ("threadpoolctl", pools)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(real_study.models, "build_sequence", lambda *args: Sequence())
    monkeypatch.setattr(
        real_study,
        "sequence_predict",
        lambda torch, model, values, device="cpu": np.zeros(len(values)),
    )
    original_version = real_study.h30.importlib.metadata.version
    monkeypatch.setattr(
        real_study.h30.importlib.metadata,
        "version",
        lambda name: "5.4.0" if name == "pandas-market-calendars" else original_version(name),
    )
    monkeypatch.setattr(real_study.h30, "runtime_identity", lambda: {"synthetic": True})
    monkeypatch.setattr(real_study.h30, "EmergencyStore", lambda path: None)

    def streams(market, receipt, deadline):
        assert market == state.market
        state.events.append("synthetic-streams")
        return ()

    def configure_cuda():
        assert state.lock.is_file()
        state.events.append("synthetic-cuda")
        return torch, {"backend": "synthetic-cuda"}

    monkeypatch.setattr(real_study.h30, "load_streams", streams)
    monkeypatch.setattr(real_study.h30, "configure_cuda", configure_cuda)

    def compare(
        streams,
        phase,
        emergency,
        deadline,
        torch,
        root,
        scope_hash,
        parent_root,
        prior,
        reference=None,
    ):
        assert streams == () and scope_hash == state.scope_hash
        assert root.name == "models" and root.parent.parent == state.output
        assert state.lock.is_file() == (phase == "cuda")
        if phase == "cuda":
            real_study.validate_result(reference, "cpu", scope_hash)
        result = real_complete(phase, scope_hash)
        fold = SimpleNamespace(
            channel_mean=np.zeros(4),
            channel_scale=np.ones(4),
            y_mean=0.0,
            y_scale=1.0,
            facts=dict(
                cohort_sha256=HASH,
                normalizer_sha256=result["folds"][0]["normalizer_sha256"],
            ),
            eval_x=np.zeros((2, 36, 4), dtype=np.float32),
        )
        for identity in real_study.identities(phase, fitted=True):
            weights = (
                "synthetic booster text"
                if phase == "cpu"
                else {"state.weight": np.zeros(1, dtype=np.float32)}
            )
            result["models"].append(
                real_study.save_model(root, fold, identity, weights, np.zeros(2), scope_hash, torch)
            )
        if state.mode == "worker_failure":
            raise real_study.h30.StudyFailure("parent_control_mismatch")
        if state.mode == "support_shortfall":
            raise real_study.sessions.OutcomeSupportShortfall(100, 20, 4)
        if state.mode == "unexpected":
            raise RuntimeError("PRIVATE synthetic failure")
        return result

    monkeypatch.setattr(real_study, "compare", compare)
    original_verify_models = real_study.verify_models

    def verify_models(root, result, scope_hash):
        state.events.append(f"verify-models-{result['phase']}")
        return original_verify_models(root, result, scope_hash)

    monkeypatch.setattr(real_study, "verify_models", verify_models)

    def supervise(target, args, *, seconds, name):
        assert target is real_study.worker and name == real_study.NAME
        assert seconds == real_study.SECONDS[args[3]]
        state.calls.append(args[3])
        target(*args)
        path = args[-1]
        result = json.loads(path.read_bytes())
        if state.mode == "corrupt_model":
            ref = result["models"][-1]
            (path.parent / "models" / ref["weights_file"]).write_bytes(b"PRIVATE corrupt model")
        if state.mode == "corrupt_accounting":
            result["cells"][0]["net_dollars"] = "999"
            path.write_bytes(real_study.h30.encode(result))
        if state.mode == "corrupt_cpu_binding":
            if state.returned_cpu_hash is None:
                result.pop("cpu_summary_sha256")
            else:
                result["cpu_summary_sha256"] = state.returned_cpu_hash
            path.write_bytes(real_study.h30.encode(result))
        return {"timed_out": False, "exit_code": 0}

    monkeypatch.setattr(ns["runpy"], "run_path", lambda path: {"supervise": supervise})
    monkeypatch.setitem(
        ns, "register_campaign_outcome", lambda **kwargs: state.outcomes.append(kwargs)
    )
    return state


def invoke_real(harness, capsys, phase):
    args = [
        "--phase",
        phase,
        "--contract-sha256",
        harness.scope_hash,
        "--artifact-root",
        str(harness.root),
        "--market-data-root",
        str(harness.market),
    ]
    if phase == "cuda":
        raw = (harness.output / "cpu-summary.json").read_bytes()
        args.extend(["--cpu-summary-sha256", real_study.h30.digest(raw)])
    previous = signal.getsignal(signal.SIGTERM)
    code = harness.cli["main"](args)
    assert signal.getsignal(signal.SIGTERM) == previous
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    return code, json.loads(captured.out)


def test_real_import_and_spawn_target_identity_without_runtime():
    cli = runpy.run_path(str(RUNNER))
    assert cli["s"] is real_study
    assert sys.modules[real_study.worker.__module__].worker is real_study.worker
    assert cli["MODEL_COUNTS"] == {
        phase: len(real_study.identities(phase, fitted=True)) for phase in ("cpu", "cuda")
    }
    assert real_study.SECONDS == {"cpu": 600, "cuda": 900}


def test_real_worker_runner_both_phases_with_numeric_and_text_serialization(real_harness, capsys):
    h = real_harness
    assert len(h.freezes) == 1 and h.freezes[0]["contract_hash"] == h.scope_hash
    before = None
    for phase, cells, files in (("cpu", 96, 12), ("cuda", 48, 32)):
        code, report = invoke_real(h, capsys, phase)
        assert code == 0, (
            report,
            h.events,
            (h.output / f"{phase}-summary.json").read_text(encoding="utf-8"),
        )
        assert report["cells"] == cells and report["models"] == COUNTS[phase]
        raw = (h.output / f"{phase}-summary.json").read_bytes()
        result = json.loads(raw)
        real_study.validate_result(result, phase, h.scope_hash)
        assert report["summary_sha256"] == real_study.h30.digest(raw)
        retained = h.output / f"{phase}-models"
        assert len(list(retained.iterdir())) == files
        assert h.events.count(f"verify-models-{phase}") == 2
        real_study.verify_models(retained, result, h.scope_hash)
        assert not h.lock.exists() and not list(h.output.glob("*-job-*"))
        if phase == "cpu":
            before = {p.name: p.read_bytes() for p in retained.iterdir()}
            assert not h.outcomes
        else:
            assert result["cpu_summary_sha256"] == real_study.h30.digest(
                (h.output / "cpu-summary.json").read_bytes()
            )
            assert h.outcomes[0]["outcome_reference_sha256"] == report["summary_sha256"]
            assert h.outcomes[0]["outcome_class"] == "non_promoting_completed"
    assert {p.name: p.read_bytes() for p in (h.output / "cpu-models").iterdir()} == before
    assert h.calls == ["cpu", "cuda"]
    assert ("threads", 1) in h.events and ("deterministic", True) in h.events


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
@pytest.mark.parametrize(
    "mode,reason",
    [
        ("worker_failure", "parent_control_mismatch"),
        ("support_shortfall", "evaluation_outcome_support_shortfall"),
        ("unexpected", "runtime_or_invariant_failure"),
        ("corrupt_model", "model_reload"),
        ("corrupt_accounting", "worker_result_invalid"),
    ],
)
def test_real_worker_parent_failures_are_empty(real_harness, capsys, phase, mode, reason):
    h = real_harness
    if phase == "cuda":
        assert invoke_real(h, capsys, "cpu")[0] == 0
    h.mode = mode
    code, report = invoke_real(h, capsys, phase)
    assert code == 1 and report["cells"] == report["models"] == 0
    raw = (h.output / f"{phase}-summary.json").read_bytes()
    result = json.loads(raw)
    assert result["reason"] == reason and "PRIVATE" not in raw.decode()
    assert all(result[key] == [] for key in ("cells", "fits", "folds", "models"))
    if mode == "support_shortfall":
        assert result["support"] == dict(eligible=100, observed=20, censored=80, blocks=4)
    assert not (h.output / f"{phase}-models").exists()
    assert not h.lock.exists() and not list(h.output.glob("*-job-*"))
    assert len(h.outcomes) == 1 and h.outcomes[0]["outcome_class"] == "non_promoting_failed"


def test_real_cpu_accounting_checked_before_cuda_dispatch(real_harness, capsys):
    h = real_harness
    assert invoke_real(h, capsys, "cpu")[0] == 0
    path = h.output / "cpu-summary.json"
    result = json.loads(path.read_bytes())
    result["cells"][0]["net_dollars"] = "999"
    path.write_bytes(real_study.h30.encode(result))
    assert invoke_real(h, capsys, "cuda")[0] == 1
    assert h.calls == ["cpu"] and "synthetic-cuda" not in h.events
    assert h.outcomes[0]["outcome_class"] == "non_promoting_failed"


@pytest.mark.parametrize("returned_cpu_hash", [OTHER_HASH, None], ids=["mismatch", "missing"])
def test_returned_cuda_cpu_binding_checked_before_parent_reload_or_retention(
    real_harness, capsys, returned_cpu_hash
):
    h = real_harness
    assert invoke_real(h, capsys, "cpu")[0] == 0
    cpu_summary = (h.output / "cpu-summary.json").read_bytes()
    cpu_models = {p.name: p.read_bytes() for p in (h.output / "cpu-models").iterdir()}
    h.mode, h.returned_cpu_hash = "corrupt_cpu_binding", returned_cpu_hash
    code, report = invoke_real(h, capsys, "cuda")
    assert code == 1 and report["cells"] == report["models"] == 0
    raw = (h.output / "cuda-summary.json").read_bytes()
    result = json.loads(raw)
    assert result["reason"] == "cpu_summary_hash"
    assert all(result[key] == [] for key in ("cells", "fits", "folds", "models"))
    assert h.events.count("verify-models-cuda") == 1  # Worker reload only.
    assert not (h.output / "cuda-models").exists()
    assert not h.lock.exists() and not list(h.output.glob("*-job-*"))
    assert (h.output / "cpu-summary.json").read_bytes() == cpu_summary
    assert {p.name: p.read_bytes() for p in (h.output / "cpu-models").iterdir()} == cpu_models
    assert len(h.outcomes) == 1 and h.outcomes[0]["outcome_class"] == "non_promoting_failed"
    assert h.outcomes[0]["outcome_reference_sha256"] == real_study.h30.digest(raw)

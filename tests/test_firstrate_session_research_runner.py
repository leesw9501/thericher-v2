"""Synthetic runner custody checks; never read source data or start a runtime."""

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
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from thericher_v2 import research

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts/run_firstrate_session_research.py"
SUPERVISOR = REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"
HASH = "sha256:" + "a" * 64
CPU_HASH = "sha256:" + "b" * 64
THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode("utf-8")


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@pytest.fixture(autouse=True)
def block_external_surfaces(monkeypatch):
    original_import, original_open = builtins.__import__, Path.open

    def checked_import(name, *args, **kwargs):
        if (
            name == "torch"
            or name.startswith("torch.")
            or any(part in name.lower() for part in ("broker", "credential", "dotenv", "kis_"))
        ):
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
        pytest.fail("network, subprocess, or real runtime attempted")

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
    output = tmp_path / "research/fake-family/regular-session-cost-matrix-v1"
    output.mkdir(parents=True)
    market = tmp_path / "market-source-blocked"
    state = SimpleNamespace(
        output=output,
        root=tmp_path,
        market=market,
        mode="complete",
        calls=[],
        outcomes=[],
        events=[],
        loaded=[],
    )
    study = ModuleType("thericher_v2.research.firstrate_session_research")
    study.NAME = "regular-session-cost-matrix-v1"
    study.FAMILY = "fake-family"
    study.REPO = REPO
    study.SECONDS = {"cpu": 1200, "cuda": 1800}
    study.h30 = SimpleNamespace(REPO=REPO, encode=encode, digest=digest)

    def freeze(root):
        assert root == tmp_path
        state.events.append("freeze")
        return HASH

    def verify(root, scope_hash):
        assert root == tmp_path and scope_hash == HASH
        state.events.append("verify")
        return output, b"synthetic-receipt", {"name": study.NAME}

    def failure(phase, scope_hash, reason):
        return {
            "name": study.NAME,
            "status": "failed_all_phase_cells",
            "phase": phase,
            "contract_sha256": scope_hash,
            "reason": reason,
            "cells": [],
            "fits": [],
            "models": [],
            "retained_weights": False,
            "promotion": False,
        }

    def validate_result(result, phase, scope_hash):
        state.events.append("validate")
        if (
            result["name"] != study.NAME
            or result["status"] != "complete"
            or result["phase"] != phase
            or result["contract_sha256"] != scope_hash
            or result["cells"] != [{"cell": 1}, {"cell": 2}]
            or result["fits"] != (list(range(48)) if phase == "cuda" else [])
        ):
            raise ValueError("PRIVATE invalid result details")

    def verify_models(root, result, scope_hash):
        assert scope_hash == HASH and root.name == "models"
        assert root.parent.parent == output and state.lock.is_file()
        state.events.append("reload")
        for ref in result["models"]:
            raw = (root / ref["weights_file"]).read_bytes()
            if raw != b"synthetic numeric model":
                raise ValueError("PRIVATE model bytes invalid")
            state.loaded.append(ref["weights_file"])

    def worker(*args):
        pytest.fail("real worker must not run")

    for function in (freeze, verify, failure, validate_result, verify_models, worker):
        setattr(study, function.__name__, function)
    monkeypatch.setitem(sys.modules, study.__name__, study)
    monkeypatch.setattr(research, "firstrate_session_research", study, raising=False)
    cli = runpy.run_path(str(RUNNER))
    ns = cli["dispatch"].__globals__
    state.cli, state.ns, state.study = cli, ns, study
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
        root, source, scope_hash, phase, cpu_hash, path = args
        assert target is worker
        assert (root, source, scope_hash) == (tmp_path, market, HASH)
        assert cpu_hash == (CPU_HASH if phase == "cuda" else None)
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
        assert all(os.environ[name] == "1" for name in THREAD_ENV)
        assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"
        result = failure(phase, HASH, "unused")
        result.update(
            status="complete",
            cells=[{"cell": 1}, {"cell": 2}],
            fits=list(range(48)) if phase == "cuda" else [],
            models=[{"weights_file": f"model-{i}.npz"} for i in range(48)]
            if phase == "cuda"
            else [],
            retained_weights=phase == "cuda",
        )
        models = path.parent / "models"
        if phase == "cuda":
            models.mkdir()
            for ref in result["models"]:
                (models / ref["weights_file"]).write_bytes(b"synthetic numeric model")
        if state.mode == "preempt":
            raise KeyboardInterrupt
        if state.mode == "sigterm":
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        if state.mode == "supervisor_error":
            raise RuntimeError("PRIVATE worker error")
        if state.mode == "identity":
            result["contract_sha256"] = CPU_HASH
        if state.mode == "cells":
            result["cells"].pop()
        if state.mode == "fits":
            result["fits"].pop()
        if state.mode == "empty_models":
            result["models"] = []
        if state.mode == "partial_models":
            result["models"].pop()
        if state.mode == "model_corrupt":
            (models / result["models"][-1]["weights_file"]).write_bytes(b"PRIVATE corrupt")
        if state.mode == "model_missing":
            (models / result["models"][-1]["weights_file"]).unlink()
        if state.mode == "failed_result":
            result = failure(phase, HASH, "PRIVATE untrusted reason")
        if state.mode == "safe_failure":
            result = failure(phase, HASH, "training_support_shortfall")
        if state.mode == "scoring_shortfall":
            result = failure(phase, HASH, "evaluation_outcome_support_shortfall")
            result["support"] = dict(eligible=100, observed=0, censored=100, blocks=0)
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
        args += ["--cpu-summary-sha256", CPU_HASH]
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


def test_bound_worker_failure_preserves_only_safe_reason(harness):
    harness.mode = "safe_failure"
    assert harness.cli["main"](arguments(harness)) == 1
    summary = json.loads((harness.output / "cpu-summary.json").read_bytes())
    assert summary["reason"] == "training_support_shortfall"
    assert summary["cells"] == [] and len(harness.outcomes) == 1


def test_scoring_shortfall_preserves_counts_not_fake_zero_returns(harness):
    harness.mode = "scoring_shortfall"
    assert harness.cli["main"](arguments(harness)) == 1
    summary = json.loads((harness.output / "cpu-summary.json").read_bytes())
    assert summary["reason"] == "evaluation_outcome_support_shortfall"
    assert summary["support"] == dict(eligible=100, observed=0, censored=100, blocks=0)
    assert summary["cells"] == []


def test_freeze_only_metadata_no_supervisor_lock_or_outcome(harness, capsys):
    previous = signal.getsignal(signal.SIGTERM)
    assert harness.cli["main"](["--freeze", "--artifact-root", str(harness.root)]) == 0
    assert signal.getsignal(signal.SIGTERM) == previous
    assert json.loads(capsys.readouterr().out) == {
        "status": "frozen_metadata_only",
        "contract_sha256": HASH,
    }
    assert harness.events == ["freeze"] and harness.outcomes == []
    assert not list(harness.output.iterdir())


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--freeze", "--phase", "cpu"],
        ["--phase", "cpu"],
        ["--freeze", "--contract-sha256", HASH],
        ["--freeze", "--cpu-summary-sha256", CPU_HASH],
        ["--phase", "cuda", "--contract-sha256", HASH],
        ["--phase", "cpu", "--contract-sha256", HASH, "--cpu-summary-sha256", CPU_HASH],
        ["--phase", "cpu", "--contract-sha256", ""],
        ["--phase", "cuda", "--contract-sha256", HASH, "--cpu-summary-sha256", ""],
    ],
)
def test_invalid_cli_rejected_before_io(harness, args):
    with pytest.raises(SystemExit) as error:
        harness.cli["main"](args)
    assert error.value.code == 2 and not harness.events


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
def test_success_once_immutable_summary_and_external_temp_cleanup(harness, capsys, phase):
    code, report = invoke(harness, capsys, phase)
    assert code == 0 and report["status"] == "complete"
    assert report["cells"] == 2 and report["models"] == (48 if phase == "cuda" else 0)
    assert len(harness.calls) == 1
    assert not harness.lock.exists() and not list(harness.output.glob("*-job-*"))
    summary = harness.output / f"{phase}-summary.json"
    raw = summary.read_bytes()
    assert report["summary_sha256"] == digest(raw)
    if phase == "cuda":
        assert harness.events.index("validate") < harness.events.index("reload")
        assert len(harness.loaded) == len(list((harness.output / "models").iterdir())) == 48
        assert_outcome(harness, phase, True)
    else:
        assert "lock" not in harness.events and "reload" not in harness.events
        assert not harness.outcomes and not (harness.output / "models").exists()
    outcomes = list(harness.outcomes)
    assert invoke(harness, capsys, phase)[0] == 1
    assert summary.read_bytes() == raw and len(harness.calls) == 1
    assert harness.outcomes == outcomes and not harness.lock.exists()


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
@pytest.mark.parametrize(
    "mode",
    [
        "timeout",
        "exit",
        "missing",
        "malformed",
        "identity",
        "cells",
        "failed_result",
        "preempt",
        "sigterm",
        "supervisor_error",
    ],
)
def test_failed_phase_discards_result_and_registers_once(harness, capsys, phase, mode):
    harness.mode = mode
    code, report = invoke(harness, capsys, phase)
    assert code == 1 and report["status"] == "failed_all_phase_cells"
    assert report["cells"] == report["models"] == 0 and len(harness.calls) == 1
    assert not harness.lock.exists() and not list(harness.output.glob("*-job-*"))
    assert not (harness.output / "models").exists() and not harness.loaded
    summary = json.loads((harness.output / f"{phase}-summary.json").read_bytes())
    assert summary["cells"] == summary["fits"] == summary["models"] == []
    assert summary["retained_weights"] is False
    if mode in ("preempt", "sigterm"):
        assert summary["reason"] == "execution_preempted"
    assert_outcome(harness, phase, False)


@pytest.mark.parametrize(
    "mode",
    [
        "fits",
        "empty_models",
        "partial_models",
        "model_corrupt",
        "model_missing",
    ],
)
def test_cuda_requires_whole_matrix_and_every_reload_before_move(harness, capsys, mode):
    harness.mode = mode
    assert invoke(harness, capsys, "cuda")[0] == 1
    assert len(harness.calls) == 1 and not harness.lock.exists()
    assert not (harness.output / "models").exists()
    assert not list(harness.output.glob("*-job-*"))
    if mode in ("model_corrupt", "model_missing"):
        assert len(harness.loaded) == 47
    else:
        assert not harness.loaded
    assert_outcome(harness, "cuda", False)


def test_existing_model_namespace_never_replaced(harness, capsys):
    models = harness.output / "models"
    models.mkdir()
    original = models / "prior-model"
    original.write_bytes(b"immutable")
    assert invoke(harness, capsys, "cuda")[0] == 1
    assert original.read_bytes() == b"immutable" and list(models.iterdir()) == [original]
    assert not list(harness.output.glob("*-job-*"))
    assert_outcome(harness, "cuda", False)


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
@pytest.mark.parametrize("artifact", ["started", "summary"])
def test_preexisting_phase_evidence_prevents_dispatch(harness, capsys, phase, artifact):
    path = harness.output / f"{phase}-{artifact}.json"
    path.write_bytes(b"immutable evidence")
    assert invoke(harness, capsys, phase)[0] == 1
    assert path.read_bytes() == b"immutable evidence"
    assert not harness.calls and not harness.outcomes and not harness.lock.exists()
    assert not list(harness.output.glob("*-job-*"))


@pytest.mark.parametrize("phase", ["cpu", "cuda"])
def test_only_cuda_observes_parent_gpu_lock(harness, capsys, phase):
    harness.lock.parent.mkdir(parents=True)
    harness.lock.write_text("other owner", encoding="ascii")
    assert invoke(harness, capsys, phase)[0] == (1 if phase == "cuda" else 0)
    assert harness.lock.read_text(encoding="ascii") == "other owner"
    assert len(harness.calls) == (0 if phase == "cuda" else 1)
    assert not harness.outcomes


@pytest.mark.parametrize("boundary", ["freeze", "verify", "register"])
def test_outer_failures_suppress_raw_errors_and_restore_signal(
    harness, monkeypatch, capsys, boundary
):
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE exception detail")

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


@pytest.mark.parametrize("mode", ["timeout", "sigint", "sigterm"])
def test_reused_supervisor_reaps_before_parent_lock_release(tmp_path, monkeypatch, mode):
    stub = ModuleType("thericher_v2.research.firstrate_session_research")
    monkeypatch.setitem(sys.modules, stub.__name__, stub)
    monkeypatch.setattr(research, "firstrate_session_research", stub, raising=False)
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

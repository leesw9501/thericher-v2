"""Mocked CPU supervisor/immutable output tests; no actual process or market panel."""

import json
import os
import runpy
from types import SimpleNamespace

import pytest

from thericher_v2.research import firstrate_position_policy as s

HASH = "sha256:" + "a" * 64
RUNNER = s.REPO / "scripts/run_firstrate_position_policy.py"


@pytest.fixture
def runner(tmp_path, monkeypatch):
    cli = runpy.run_path(str(RUNNER))
    ns = cli["dispatch"].__globals__
    state = SimpleNamespace(
        calls=[],
        outcomes=[],
        mode="complete",
        output=tmp_path,
        result={**s.failure(HASH, None), "status": "complete", "cells": []},
    )
    state.result.pop("reason")
    args = SimpleNamespace(
        artifact_root=tmp_path, market_data_root=tmp_path / "unread-source", contract_sha256=HASH
    )

    def verify(root, pin):
        assert root == tmp_path and pin == HASH
        state.calls.append("verify")
        return tmp_path

    def validate(result, pin):
        assert pin == HASH and result == state.result
        state.calls.append("validate")

    def supervise(target, arguments, *, seconds, name):
        assert target is s.worker and seconds == 600 and name == s.NAME
        root, market, pin, path = arguments
        assert (root, market, pin) == (args.artifact_root, args.market_data_root, HASH)
        assert path.parent.parent == tmp_path
        assert not path.is_relative_to(s.REPO)
        state.calls.append("supervise")
        if state.mode == "interrupt":
            raise KeyboardInterrupt
        if state.mode == "error":
            raise RuntimeError("PRIVATE error must never escape")
        if state.mode not in ("missing", "timeout"):
            path.write_bytes(s.h30.encode(state.result))
        return dict(timed_out=state.mode == "timeout", exit_code=0, elapsed_seconds=0.1)

    monkeypatch.setattr(s, "verify", verify)
    monkeypatch.setattr(s, "validate_result", validate)
    monkeypatch.setattr(s, "worker", lambda *_: pytest.fail("actual worker forbidden"))
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: pytest.fail("data read forbidden"))
    monkeypatch.setitem(ns, "runpy", SimpleNamespace(run_path=lambda _: {"supervise": supervise}))
    monkeypatch.setitem(
        ns, "register_campaign_outcome", lambda **kwargs: state.outcomes.append(kwargs)
    )
    state.cli, state.args = cli, args
    return state


def test_cpu_only_dispatch_reaps_temporary_files_and_returns_safe_summary(runner):
    result = runner.cli["dispatch"](runner.args)
    assert result["status"] == "complete"
    assert runner.calls == ["verify", "supervise", "validate", "verify"]
    assert not list(runner.output.glob("cpu-job-*"))
    assert set(p.name for p in runner.output.iterdir()) == {"started.json", "summary.json"}
    assert runner.outcomes[0]["outcome_class"] == "non_promoting_completed"
    assert not (runner.output / "models").exists()
    assert not (runner.output / "locks/gpu.lock").exists()


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("timeout", "worker_failed_or_timed_out"),
        ("missing", "worker_result_invalid"),
        ("error", "worker_result_invalid"),
        ("interrupt", "execution_preempted"),
    ],
)
def test_failed_run_never_returns_partial_cells_or_private_errors(runner, mode, reason):
    runner.mode = mode
    result = runner.cli["dispatch"](runner.args)
    assert result["status"] == "failed_all_cells"
    saved = json.loads((runner.output / "summary.json").read_bytes())
    assert saved["reason"] == reason and saved["cells"] == []
    assert "PRIVATE" not in json.dumps(saved)
    assert not list(runner.output.glob("cpu-job-*"))
    assert runner.outcomes[0]["outcome_class"] == "non_promoting_failed"


@pytest.mark.parametrize("existing", ("started.json", "summary.json"))
def test_existing_attempt_is_never_overwritten_or_retried(runner, existing):
    path = runner.output / existing
    path.write_text("immutable", encoding="ascii")
    with pytest.raises(FileExistsError):
        runner.cli["dispatch"](runner.args)
    assert path.read_text(encoding="ascii") == "immutable"
    assert "supervise" not in runner.calls


@pytest.mark.parametrize("mutation", (None, "identity", "private", "count", "extra", "cells"))
def test_worker_shortfall_is_identity_bound_and_safe(runner, mutation):
    result = s.failure(HASH, "common_outcome_support_shortfall")
    result["support"] = {"eligible": 36, "observed": 30, "censored": 6, "blocks": 5}
    if mutation == "identity":
        result["contract_sha256"] = "wrong"
    elif mutation == "private":
        result["reason"] = "PRIVATE body"
    elif mutation == "count":
        result["support"]["observed"] = -1
    elif mutation == "extra":
        result["support"]["raw"] = "PRIVATE body"
    elif mutation == "cells":
        result["cells"] = [{"net_dollars": "1"}]
    runner.result = result
    runner.cli["dispatch"](runner.args)
    saved = json.loads((runner.output / "summary.json").read_bytes())
    assert saved["cells"] == [] and "PRIVATE" not in json.dumps(saved)
    assert saved["reason"] == (
        "common_outcome_support_shortfall" if mutation is None else "worker_result_invalid"
    )


@pytest.mark.parametrize(
    "argv",
    (
        [],
        ["--run"],
        ["--run", "--contract-sha256", ""],
        ["--freeze", "--contract-sha256", HASH],
        ["--phase", "cuda"],
    ),
)
def test_cli_requires_explicit_freeze_or_bound_cpu_run(runner, argv):
    with pytest.raises(SystemExit) as caught:
        runner.cli["main"](argv)
    assert caught.value.code == 2
    assert runner.calls == []


def test_freeze_mode_does_not_spawn_or_read_panel(runner, monkeypatch, capsys):
    monkeypatch.setattr(s, "freeze", lambda root: HASH)
    for name in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "CUDA_VISIBLE_DEVICES",
    ):
        monkeypatch.setenv(name, "7")
    assert runner.cli["main"](["--freeze", "--artifact-root", str(runner.output)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "frozen_metadata_only"
    assert os.environ["CUDA_VISIBLE_DEVICES"] == ""
    assert os.environ["OMP_NUM_THREADS"] == "1"
    assert runner.calls == []

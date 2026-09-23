"""Synthetic CLI/supervisor protocol tests; no source reads or shared registry writes."""

import copy
import json
import runpy
from types import SimpleNamespace

import pytest

import test_firstrate_opening_range as orb_tests
from test_firstrate_opening_range import HASH, run
from thericher_v2.research import firstrate_opening_range as s

source = orb_tests.source


@pytest.fixture
def runner(tmp_path, monkeypatch, source):
    shared = runpy.run_path(str(s.REPO / "scripts/run_firstrate_position_policy.py"))
    own = runpy.run_path(str(s.REPO / "scripts/run_firstrate_opening_range.py"))
    state = SimpleNamespace(
        output=tmp_path,
        mode="complete",
        result=run(source),
        calls=[],
        outcomes=[],
        shared=shared,
        own=own,
    )
    ns = shared["main"].__globals__
    monkeypatch.setitem(
        own["main"].__globals__, "runpy", SimpleNamespace(run_path=lambda _: shared)
    )

    def verify(root, pin):
        assert root == tmp_path and pin == HASH
        state.calls.append("verify")
        return tmp_path

    def supervise(target, arguments, *, seconds, name):
        assert target is s.worker and seconds == 600 and name == s.NAME
        root, market, pin, path = arguments
        assert root == tmp_path and pin == HASH
        assert path.parent.parent == tmp_path
        state.calls.append("supervise")
        if state.mode == "interrupt":
            raise KeyboardInterrupt
        if state.mode == "error":
            raise ValueError("PRIVATE")
        if state.mode != "missing":
            path.write_bytes(s.h30.encode(state.result))
        return dict(timed_out=state.mode == "timeout", exit_code=0, elapsed_seconds=0.1)

    monkeypatch.setattr(s, "verify", verify)
    monkeypatch.setattr(s, "worker", lambda *_: pytest.fail("actual worker forbidden"))
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: pytest.fail("panel read forbidden"))
    monkeypatch.setitem(ns, "runpy", SimpleNamespace(run_path=lambda _: {"supervise": supervise}))
    monkeypatch.setitem(ns, "register_campaign_outcome", lambda **kw: state.outcomes.append(kw))
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "CUDA_VISIBLE_DEVICES",
    ):
        monkeypatch.setenv(name, "1")
    state.argv = [
        "--run",
        "--contract-sha256",
        HASH,
        "--artifact-root",
        str(tmp_path),
        "--market-data-root",
        str(tmp_path / "unread-market"),
    ]
    return state


def test_cli_binds_orb_to_existing_cpu_supervisor(runner, capsys):
    assert runner.own["main"](runner.argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "complete" and result["paired_cells"] == 12
    saved = json.loads((runner.output / "summary.json").read_bytes())
    assert saved["name"] == s.NAME
    assert runner.calls == ["verify", "supervise", "verify"]
    assert runner.outcomes[0]["outcome_class"] == "non_promoting_completed"
    assert set(p.name for p in runner.output.iterdir()) == {"started.json", "summary.json"}


@pytest.mark.parametrize("mode", ("timeout", "missing", "interrupt", "error"))
def test_failed_runner_never_emits_partial_pnl_or_private_errors(runner, mode, capsys):
    runner.mode = mode
    assert runner.own["main"](runner.argv) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed_all_cells"
    raw = (runner.output / "summary.json").read_text()
    assert "PRIVATE" not in raw and json.loads(raw)["cells"] == []
    assert not list(runner.output.glob("cpu-job-*"))
    assert runner.outcomes[0]["outcome_class"] == "non_promoting_failed"


@pytest.mark.parametrize("mutation", ("identity", "extra", "reason", "partial"))
def test_failed_payload_is_exactly_bound_to_orb(runner, mutation, capsys):
    payload = s.failure(HASH, "runtime_or_invariant_failure")
    if mutation == "identity":
        payload["name"] = "wrong"
    elif mutation == "extra":
        payload["raw"] = "PRIVATE"
    elif mutation == "reason":
        payload["reason"] = "PRIVATE"
    elif mutation == "partial":
        payload["cells"] = copy.deepcopy(runner.result["cells"])
    runner.result = payload
    assert runner.own["main"](runner.argv) == 1
    capsys.readouterr()
    saved = json.loads((runner.output / "summary.json").read_bytes())
    assert saved["reason"] == "worker_result_invalid" and saved["cells"] == []
    assert "PRIVATE" not in json.dumps(saved)


@pytest.mark.parametrize("existing", ("started.json", "summary.json"))
def test_existing_attempt_is_not_retried(runner, existing, capsys):
    path = runner.output / existing
    path.write_text("immutable")
    assert runner.own["main"](runner.argv) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "dispatch_unavailable"
    assert path.read_text() == "immutable"
    assert "supervise" not in runner.calls


def test_freeze_mode_only_calls_orb_metadata_freeze(runner, monkeypatch, capsys):
    calls = []

    def freeze(root):
        calls.append(root)
        return HASH

    monkeypatch.setattr(s, "freeze", freeze)
    assert runner.own["main"](["--freeze", "--artifact-root", str(runner.output)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "frozen_metadata_only"
    assert calls == [runner.output] and runner.calls == []
    assert runner.outcomes == []


@pytest.mark.parametrize(
    "argv", ([], ["--run"], ["--freeze", "--contract-sha256", HASH], ["--phase", "cuda"])
)
def test_cli_refuses_unbound_or_gpu_run(runner, argv):
    with pytest.raises(SystemExit) as caught:
        runner.own["main"](argv)
    assert caught.value.code == 2
    assert runner.calls == []

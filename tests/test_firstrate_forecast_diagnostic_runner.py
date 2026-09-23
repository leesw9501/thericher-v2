"""Synthetic supervisor tests; no child process, real artifact, or source access."""

import json
import os
import runpy
from types import SimpleNamespace

import pytest

from test_firstrate_forecast_diagnostic import (  # noqa: F401
    HASH,
    OTHER,
    compare,
    matrix,
    no_external_io,
    source,
)
from thericher_v2.research import firstrate_forecast_diagnostic as s


@pytest.fixture
def runner(tmp_path, monkeypatch, matrix):  # noqa: F811
    cli = runpy.run_path(str(s.REPO / "scripts/run_firstrate_forecast_diagnostic.py"))
    ns = cli["dispatch"].__globals__
    output = tmp_path / "dispatch"
    output.mkdir()
    state = SimpleNamespace(
        cli=cli,
        calls=[],
        outcomes=[],
        output=output,
        mode="complete",
        result=compare(matrix),
        job=dict(timed_out=False, exit_code=0, elapsed_seconds=0.1),
        args=SimpleNamespace(
            artifact_root=tmp_path,
            market_data_root=tmp_path / "never-read",
            contract_sha256=HASH,
        ),
    )

    def verify(root, pin):
        assert root == tmp_path and pin == HASH
        state.calls.append("verify")
        if state.mode == "changed" and state.calls.count("verify") == 2:
            raise ValueError("PRIVATE synthetic contract changed")
        return output

    def supervise(target, arguments, *, seconds, name):
        assert target is s.worker and seconds == 600 and name == s.NAME
        root, market, pin, path = arguments
        assert (root, market, pin) == (tmp_path, state.args.market_data_root, HASH)
        assert path.parent.parent == output and not path.is_relative_to(s.REPO)
        state.calls.append("supervise")
        if state.mode == "interrupt":
            raise KeyboardInterrupt
        if state.mode == "error":
            raise RuntimeError("PRIVATE synthetic error")
        if state.mode != "missing":
            path.write_bytes(s.h30.encode(state.result))
        return state.job

    monkeypatch.setattr(s, "verify", verify)
    monkeypatch.setattr(s, "worker", lambda *_: pytest.fail("actual worker forbidden"))
    monkeypatch.setitem(ns, "runpy", SimpleNamespace(run_path=lambda _: {"supervise": supervise}))
    monkeypatch.setitem(ns, "register_campaign_outcome", lambda **kw: state.outcomes.append(kw))
    return state


def saved(runner):
    return json.loads((runner.output / "summary.json").read_bytes())


def test_complete_dispatch_binds_result_and_receipt_without_model_or_gpu_artifacts(runner):
    result = runner.cli["dispatch"](runner.args)
    assert result["status"] == "complete" and result["cells"] == 28
    assert runner.calls == ["verify", "supervise", "verify"]
    assert set(p.name for p in runner.output.iterdir()) == {"started.json", "summary.json"}
    receipt = runner.outcomes[0]
    assert receipt["outcome_class"] == "non_promoting_completed"
    assert receipt["contract_hash"] == HASH
    assert receipt["outcome_reference_sha256"] == result["summary_sha256"]
    assert result["summary_sha256"] == s.h30.digest((runner.output / "summary.json").read_bytes())
    assert saved(runner)["parent_controls_reproduced"] == 84


@pytest.mark.parametrize(
    "case", ("timeout", "nonzero", "bool_exit", "missing", "error", "interrupt", "changed")
)
def test_failed_supervision_never_consumes_even_a_complete_worker_result(runner, case):
    runner.mode = case
    if case == "timeout":
        runner.job["timed_out"] = True
    elif case == "nonzero":
        runner.job["exit_code"] = 1
    elif case == "bool_exit":
        runner.job["exit_code"] = False
    result = runner.cli["dispatch"](runner.args)
    assert result["status"] == "failed_all_cells" and result["cells"] == 0
    value = saved(runner)
    assert value["cells"] == value["folds"] == [] and value["parent_controls_reproduced"] == 0
    assert "PRIVATE" not in json.dumps(value)
    expected = "worker_result_invalid"
    if case in ("timeout", "nonzero", "bool_exit"):
        expected = "worker_failed_or_timed_out"
    elif case == "interrupt":
        expected = "execution_preempted"
    assert value["reason"] == expected
    assert not list(runner.output.glob("cpu-job-*"))
    assert runner.outcomes[0]["outcome_class"] == "non_promoting_failed"


@pytest.mark.parametrize("mutation", (None, "identity", "raw_reason", "partial_cells"))
def test_worker_failure_is_exactly_identity_bound_and_source_safe(runner, mutation):
    runner.result = s.failure(HASH, "runtime_or_invariant_failure")
    if mutation == "identity":
        runner.result["contract_sha256"] = OTHER
    elif mutation == "raw_reason":
        runner.result["reason"] = "PRIVATE synthetic payload"
    elif mutation == "partial_cells":
        runner.result["cells"] = [{"prediction": "PRIVATE"}]
    runner.cli["dispatch"](runner.args)
    value = saved(runner)
    assert value["contract_sha256"] == HASH and value["cells"] == []
    assert value["reason"] == (
        "runtime_or_invariant_failure" if mutation is None else "worker_result_invalid"
    )
    assert "PRIVATE" not in json.dumps(value)


@pytest.mark.parametrize("mutation", ("identity", "partial", "raw", "raw_fold"))
def test_success_result_cannot_bypass_binding_or_leak_raw_fields(runner, mutation):
    if mutation == "identity":
        runner.result["contract_sha256"] = OTHER
    elif mutation == "partial":
        runner.result["cells"].pop()
    elif mutation == "raw_fold":
        runner.result["folds"][0]["raw_predictions"] = ["PRIVATE synthetic row"]
    else:
        runner.result["cells"][0]["metrics"]["raw_predictions"] = ["PRIVATE synthetic row"]
    runner.cli["dispatch"](runner.args)
    value = saved(runner)
    assert value["status"] == "failed_all_cells" and value["cells"] == []
    assert "PRIVATE" not in json.dumps(value)


@pytest.mark.parametrize("existing", ("started.json", "summary.json"))
def test_existing_attempt_and_summary_are_never_overwritten(runner, existing):
    path = runner.output / existing
    path.write_bytes(b"immutable prior synthetic attempt")
    with pytest.raises(FileExistsError):
        runner.cli["dispatch"](runner.args)
    assert path.read_bytes() == b"immutable prior synthetic attempt"
    assert "supervise" not in runner.calls and runner.outcomes == []


def test_freeze_cli_sets_cpu_environment_without_inference(runner, monkeypatch, capsys):
    monkeypatch.setattr(s, "freeze", lambda root: HASH)
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "CUDA_VISIBLE_DEVICES",
    ):
        monkeypatch.setenv(key, "7")
    code = runner.cli["main"](["--freeze", "--artifact-root", str(runner.args.artifact_root)])
    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "frozen_metadata_only"
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "" and os.environ["OMP_NUM_THREADS"] == "1"
    assert runner.calls == []


@pytest.mark.parametrize(
    "argv",
    (
        ["--run"],
        ["--run", "--contract-sha256", ""],
        ["--freeze", "--contract-sha256", ""],
    ),
)
def test_cli_rejects_missing_or_empty_hash_without_reading_artifacts(monkeypatch, argv):
    cli = runpy.run_path(str(s.REPO / "scripts/run_firstrate_forecast_diagnostic.py"))
    monkeypatch.setattr(s, "verify", lambda *_: pytest.fail("no artifact reads"))
    monkeypatch.setattr(s, "freeze", lambda *_: pytest.fail("no artifact writes"))
    with pytest.raises(SystemExit) as caught:
        cli["main"](argv)
    assert caught.value.code == 2

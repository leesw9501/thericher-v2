"""Isolated synthetic CPU fixtures only; no retained data or CUDA invocation."""

from __future__ import annotations

import builtins
import json
import runpy
import signal
import time

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import make_bars
from thericher_v2.research import firstrate_h30_train_learnability as s

h30, d = s.h30, s.d


@pytest.fixture(scope="module")
def source():
    bars = make_bars()
    plan = h30.plans(bars)[0]
    fold = h30.prepare_fold("SPY", 1, {b.start_ts: b for b in bars}, (plan[0], (), plan[2]))
    return bars, plan, fold


@pytest.fixture
def cpu_torch(monkeypatch):
    import torch

    threads, dtype, state = (
        torch.get_num_threads(),
        torch.get_default_dtype(),
        torch.get_rng_state(),
    )
    initialized = torch.cuda.is_initialized()
    torch.set_num_threads(1)
    torch.set_default_dtype(torch.float32)
    monkeypatch.setattr(torch.cuda, "manual_seed_all", lambda *a: pytest.fail("CUDA seed access"))
    monkeypatch.setattr(torch.cuda, "_lazy_init", lambda *a: pytest.fail("CUDA access"))
    yield torch
    assert torch.cuda.is_initialized() == initialized
    torch.set_rng_state(state)
    torch.set_num_threads(threads)
    torch.set_default_dtype(dtype)


def cli():
    return runpy.run_path(str(h30.REPO / s.OWN_FILES[1]))


def test_describe_only_hashes_source_no_torch_or_artifact_access(monkeypatch, capsys):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split(".")[0] != "torch"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(d, "bindings", lambda *a: pytest.fail("artifact read"))
    assert cli()["main"](["--describe"]) == 0
    described = json.loads(capsys.readouterr().out)
    contract = described["contract"]
    assert h30.digest(h30.encode(contract)) == described["sha256"]
    assert s.KEYS == (
        ("synthetic64", 101),
        ("synthetic64", 103),
        ("spy_train16", 101),
        ("spy_train16", 103),
    )
    assert contract["total_updates"] == 4 * s.UPDATES == 1024
    assert contract["budget_seconds"] == 180 and s.CHECKPOINTS == (0, 1, 16, 64, 256)
    assert all(
        contract[k] is False
        for k in (
            "evaluation_access",
            "payoff",
            "weights_retained",
            "promotion",
            "generalization_claim",
        )
    )


def test_subset_uses_original_train_order_no_eval_or_second_csv(source, monkeypatch):
    bars, plan, expected = source
    observe, outcomes = h30.observe, h30.outcomes
    calls = []

    def guarded_observe(index, times):
        assert all(b.end_ts <= plan[2] for b in index.values())
        assert all(t + h30.HOLD < plan[2] for t in times)
        calls.append(len(times))
        return observe(index, times)

    def guarded_outcomes(index, observations):
        assert all(o.at + h30.HOLD < plan[2] for o in observations)
        return outcomes(index, observations)

    def streams():
        yield "SPY", bars
        pytest.fail("second CSV consumed")

    monkeypatch.setattr(h30, "observe", guarded_observe)
    monkeypatch.setattr(h30, "outcomes", guarded_outcomes)
    monkeypatch.setattr(h30, "score", lambda *a: pytest.fail("payoff"))
    data, facts = s.batches(streams(), {"folds": [expected.facts]})
    assert calls == [len(plan[0]), 0]
    assert np.array_equal(data[1][0], expected.train_x[:16, -12:])
    assert np.array_equal(data[1][1], expected.train_y[:16])
    assert facts["normalizer_sha256"] == expected.facts["normalizer_sha256"]
    assert facts["train_only_cohort_sha256"] == expected.facts["cohort_sha256"]
    assert data[0][0].shape == (64, 12, 4) and data[1][0].shape == (16, 12, 4)
    x = np.random.default_rng(0).normal(size=(64, 12, 4))
    y = x[:, -1, 0]
    assert np.array_equal(data[0][0], x.astype(np.float32))
    assert np.array_equal(data[0][1], ((y - y.mean()) / y.std()).astype(np.float32))


def test_normalizer_drift_rejected_before_subset(source):
    bars, _, fold = source
    with pytest.raises(h30.StudyFailure, match="train_binding"):
        s.batches(iter([("SPY", bars)]), {"folds": [{**fold.facts, "normalizer_sha256": "bad"}]})


def test_ordered_hash_duplicate_conflict_and_literal_baseline():
    x = np.zeros((16, 12, 4), dtype=np.float32)
    y = np.arange(16, dtype=np.float32)
    facts = s.batch_facts(x, y)
    assert facts["duplicate_input_pairs"] == facts["conflicting_target_pairs"] == 120
    assert facts["mean_baseline_mse"] == 21.25
    assert facts["ordered_batch_sha256"] != s.batch_facts(x, y[::-1])["ordered_batch_sha256"]
    h30.encode(facts)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("constant", "constant_batch_target"),
        ("nan", "batch_nonfinite"),
        ("short", "batch_geometry"),
    ],
)
def test_bad_batch_no_backfill(mutation, reason):
    x, y = np.zeros((16, 12, 4), np.float32), np.arange(16, dtype=np.float32)
    if mutation == "constant":
        y[:] = 1
    elif mutation == "nan":
        x[0, 0, 0] = np.nan
    else:
        x, y = x[:15], y[:15]
    with pytest.raises(h30.StudyFailure, match=reason):
        s.batch_facts(x, y)


def test_checkpoint_fresh_forward_independent_numpy_mse_and_parity(cpu_torch, monkeypatch):
    torch = cpu_torch

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.calls = []

        def forward(self, x):
            self.calls.append((self.training, torch.is_grad_enabled()))
            return x[:, -1, :1]

    model = Model()
    x, y = torch.ones(16, 12, 4), torch.arange(16, dtype=torch.float32)
    metrics = s.checkpoint(torch, model, x, y, 21.25)
    assert metrics["mse"] == sum((1 - i) ** 2 for i in range(16)) / 16
    assert model.calls == [(False, False), (True, False)]
    monkeypatch.setattr(torch.nn.functional, "mse_loss", lambda *a: torch.tensor(999.0))
    with pytest.raises(h30.StudyFailure, match="loss_parity"):
        s.checkpoint(torch, model, x, y, 21.25)


def test_actual_model_fixed_updates_and_source_safe_metrics(cpu_torch, monkeypatch):
    torch = cpu_torch
    x = np.random.default_rng(0).normal(size=(16, 12, 4)).astype(np.float32)
    y = np.arange(16, dtype=np.float32) / 16
    original, calls = torch.optim.AdamW.step, []

    def step(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(torch.optim.AdamW, "step", step)
    facts = s.batch_facts(x, y)
    result = s.fit(
        torch,
        torch.tensor(x),
        torch.tensor(y),
        "spy_train16",
        101,
        facts["mean_baseline_mse"],
        time.monotonic() + 30,
    )
    assert len(calls) == result["updates"] == 256
    assert [m["update"] for m in result["checkpoints"]] == list(s.CHECKPOINTS)
    assert all(m["movement_rms"] > 0 for m in result["checkpoints"][1:])
    assert result["classification"] == "train_capacity_measurement_only"
    text = h30.encode(result).decode()
    assert not any(k in text for k in ("prediction", "state.", "scaler", "target_values"))


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("gradient", "nonfinite_gradient"),
        ("parameter", "nonfinite_parameter"),
        ("zero_step", "no_first_update"),
    ],
)
def test_nonfinite_or_zero_first_update_discards_fit(cpu_torch, monkeypatch, fault, reason):
    torch = cpu_torch
    factory = h30.build_torch_sequence_model

    def model(**kwargs):
        result = factory(**kwargs)
        if fault == "gradient":
            next(result.parameters()).register_hook(lambda g: g * float("nan"))
        return result

    def step(self, *a, **kw):
        if fault == "parameter":
            with torch.no_grad():
                self.param_groups[0]["params"][0].fill_(float("inf"))

    monkeypatch.setattr(h30, "build_torch_sequence_model", model)
    if fault != "gradient":
        monkeypatch.setattr(torch.optim.AdamW, "step", step)
    with pytest.raises(h30.StudyFailure, match=reason):
        s.fit(
            torch,
            torch.ones(16, 12, 4),
            torch.arange(16, dtype=torch.float32),
            "synthetic64",
            101,
            21.25,
            time.monotonic() + 30,
        )


def test_synthetic_miss_is_not_code_failure_and_no_early_stopping(cpu_torch, monkeypatch):
    torch = cpu_torch
    monkeypatch.setattr(s, "checkpoint", lambda *a: {"mse": 100.0, "mean_baseline_ratio": 100.0})
    result = s.fit(
        torch,
        torch.ones(16, 12, 4),
        torch.arange(16, dtype=torch.float32),
        "synthetic64",
        103,
        21.25,
        time.monotonic() + 30,
    )
    assert result["classification"] == "learnability_not_demonstrated"
    assert result["updates"] == 256


def test_deadline_checked_in_loop(cpu_torch):
    torch = cpu_torch
    with pytest.raises(h30.StudyFailure, match="budget_exhausted"):
        s.fit(
            torch,
            torch.ones(16, 12, 4),
            torch.arange(16, dtype=torch.float32),
            "synthetic64",
            101,
            21.25,
            time.monotonic() - 1,
        )


def test_worker_hash_failure_before_source_or_cuda(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "bindings", lambda *a: pytest.fail("artifact read"))
    monkeypatch.setattr(h30, "configure_cuda", lambda: pytest.fail("GPU"))
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path, "wrong", path)
    result = json.loads(path.read_bytes())
    assert result["status"] == "failed_all4" and result["fits"] == []
    assert result["reason"] == "contract_changed"


@pytest.mark.parametrize(
    "mode", ["success", "timeout", "partial", "preempt", "failure", "foreign_failure", "raw_reason"]
)
def test_cli_supervised_prep_report_lock_and_immutable_sibling(tmp_path, monkeypatch, mode):
    module = cli()
    main_globals = module["main"].__globals__
    scope_hash = h30.digest(h30.encode(s.contract()))
    output = h30.run_directory(tmp_path, s.NAME)
    lock = main_globals["resolve_agent_root"](tmp_path) / "locks/gpu.lock"
    monkeypatch.setattr(d, "bindings", lambda *a: pytest.fail("prep escaped supervisor"))

    def supervise(target, arguments, *, seconds, name):
        assert target is s.worker and seconds == 180 and name == s.NAME
        assert lock.is_file()
        assert arguments[:3] == (tmp_path, tmp_path / "market", scope_hash)
        assert main_globals["os"].environ["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8"
        if mode == "preempt":
            raise KeyboardInterrupt
        result = {
            "status": "complete",
            "contract_sha256": scope_hash,
            "fits": [{"arm": a, "seed": seed, "updates": 256} for a, seed in s.KEYS],
        }
        if mode == "partial":
            result["fits"].pop()
        if mode in ("failure", "foreign_failure", "raw_reason"):
            result = s.failure(scope_hash, "nonfinite_gradient")
        if mode == "foreign_failure":
            result["contract_sha256"] = "wrong"
        if mode == "raw_reason":
            result["reason"] = "private raw exception must not escape"
        arguments[-1].write_bytes(h30.encode(result))
        return {"timed_out": mode == "timeout", "exit_code": 0}

    monkeypatch.setattr(main_globals["runpy"], "run_path", lambda *a: {"supervise": supervise})
    args = [
        "--contract-sha256",
        scope_hash,
        "--artifact-root",
        str(tmp_path),
        "--market-data-root",
        str(tmp_path / "market"),
    ]
    previous_handler = signal.getsignal(signal.SIGTERM)
    assert module["main"](args) == (0 if mode == "success" else 1)
    assert signal.getsignal(signal.SIGTERM) == previous_handler
    assert not lock.exists()
    assert output.parent == h30.run_directory(tmp_path, d.RUN).parent
    result = json.loads((output / "summary.json").read_bytes())
    assert len(result["fits"]) == (4 if mode == "success" else 0)
    if mode == "foreign_failure":
        assert result["reason"] == "worker_failed_or_timed_out"
    if mode == "raw_reason":
        assert result["reason"] == "runtime_or_binding_failure"
    assert not list(output.glob("job-*"))
    original = (output / "summary.json").read_bytes()
    assert module["main"](args) == 1
    assert (output / "summary.json").read_bytes() == original


def test_held_existing_gpu_lock_prevents_dispatch(tmp_path, monkeypatch):
    module = cli()
    namespace = module["main"].__globals__
    monkeypatch.setattr(namespace["runpy"], "run_path", lambda *a: {"supervise": None})
    lock = namespace["resolve_agent_root"](tmp_path) / "locks/gpu.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("owned elsewhere", encoding="ascii")
    assert (
        module["main"](
            [
                "--contract-sha256",
                h30.digest(h30.encode(s.contract())),
                "--artifact-root",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert lock.read_text(encoding="ascii") == "owned elsewhere"
    assert not h30.run_directory(tmp_path, s.NAME).exists()


def test_artifact_guard_still_rejects_git_root():
    with pytest.raises(ValueError):
        h30.run_directory(h30.REPO, s.NAME)

"""Synthetic CPU inference only; no retained inputs, optimizer, or CUDA execution."""

from __future__ import annotations

import builtins
import json
import runpy
import sys
import time
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import make_bars
from thericher_v2.research import firstrate_h30_train_diagnostic as d

h30 = d.h30


@pytest.fixture(scope="module")
def sources():
    spy = make_bars()
    return {"SPY": spy, "QQQ": [replace(b, symbol="QQQ") for b in spy]}


@pytest.fixture
def package(sources, tmp_path):
    folds = []
    for symbol, bars in sources.items():
        for number, plan in enumerate(h30.plans(bars), 1):
            folds.append(h30.prepare_fold(symbol, number, {b.start_ts: b for b in bars}, plan))
    states = {
        k: np.full(shape, 0.125, dtype=np.float32)
        for k, shape in h30.STATE_SHAPES.items()
        if k.startswith("state.")
    }
    retained = [(f, c, s, states) for f in folds for c in h30.CONTEXTS for s in h30.SEEDS]
    refs = h30.save_final_models(
        tmp_path / "models", retained, d.H30_HASH, [], {}, time.monotonic() + 30
    )
    payload = {"source_pins": [], "normalization_sha256": "sha256:" + "a" * 64}
    cpu = {
        "status": "complete",
        "contract_sha256": d.H30_HASH,
        "runtime": {"environment": {}},
        "folds": [f.facts for f in folds],
        "cells": [{"net_dollars": "must_not_consume"}],
    }
    cuda = {**cpu, "cpu_summary_sha256": d.SUMMARY_HASHES["cpu"], "models": refs}
    return tmp_path, payload, cpu, cuda, folds


@pytest.fixture
def cpu_torch(monkeypatch):
    import torch

    def forbidden(*args, **kwargs):
        raise AssertionError("optimizer or GPU access forbidden")

    threads, dtype = torch.get_num_threads(), torch.get_default_dtype()
    state, initialized = torch.get_rng_state(), torch.cuda.is_initialized()
    torch.set_num_threads(1)
    torch.set_default_dtype(torch.float32)
    monkeypatch.setattr(torch, "optim", SimpleNamespace(AdamW=forbidden, SGD=forbidden))
    monkeypatch.setattr(torch.cuda, "manual_seed_all", forbidden)
    monkeypatch.setattr(torch.cuda, "_lazy_init", forbidden)
    yield torch
    assert torch.cuda.is_initialized() == initialized
    torch.set_rng_state(state)
    torch.set_num_threads(threads)
    torch.set_default_dtype(dtype)


def test_fixed_scope_is_all16_no_optimizer_no_eval_no_selection():
    assert len(d.fit_keys()) == 16 and d.SECONDS == 600
    scope = d.contract()
    assert scope["optimizer_steps"] == 0 and scope["gpu"] is False
    assert scope["evaluation_predictions"] is scope["payoff"] is scope["promotion"] is False
    assert len(scope["code_sha256"]) == 2 and scope["summary_sha256"] == d.SUMMARY_HASHES


def test_train_preparation_never_observes_eval_or_constructs_eval_targets(
    sources, package, monkeypatch
):
    _, _, cpu, _, _ = package
    observe, outcomes = h30.observe, h30.outcomes
    calls = []
    cutoff = None

    def guarded_observe(index, times):
        assert all(b.end_ts <= cutoff for b in index.values())
        assert all(t + h30.HOLD < cutoff for t in times)
        calls.append(("observe", len(times)))
        return observe(index, times)

    def guarded_outcomes(index, observations):
        assert observations and all(x.at + h30.HOLD < cutoff for x in observations)
        calls.append(("outcomes", len(observations)))
        return outcomes(index, observations)

    monkeypatch.setattr(h30, "observe", guarded_observe)
    monkeypatch.setattr(h30, "outcomes", guarded_outcomes)
    for expected in cpu["folds"]:
        bars = sources[expected["symbol"]]
        plan = h30.plans(bars)[expected["fold"] - 1]
        cutoff = plan[2]
        fold = d.prepare_train(expected["symbol"], expected["fold"], bars, plan, expected)
        assert len(fold.evaluation) == len(fold.eval_x) == 0
        assert fold.facts["evaluation_outcomes"] is None
        assert fold.facts["cohort_sha256"] != expected["cohort_sha256"]  # deliberately not compared
    assert sum(kind == "outcomes" for kind, _ in calls) == 4
    assert sum(kind == "observe" and count == 0 for kind, count in calls) == 4


@pytest.mark.parametrize("field", ["normalizer_sha256", "training_outcomes", "train_blocks_36"])
def test_train_binding_drift_rejected(sources, package, field):
    expected = {**package[2]["folds"][0], field: "changed"}
    with pytest.raises(h30.StudyFailure, match="train_binding"):
        d.prepare_train("SPY", 1, sources["SPY"], h30.plans(sources["SPY"])[0], expected)


def test_all16_saved_fits_cpu_inference_no_optimizer_or_evaluation(
    sources, package, cpu_torch, monkeypatch
):
    root, payload, cpu, cuda, _ = package
    original = h30.prepare_fold

    def guard(symbol, number, index, plan):
        assert plan[1] == ()
        return original(symbol, number, index, plan)

    monkeypatch.setattr(h30, "prepare_fold", guard)
    monkeypatch.setattr(h30, "score", lambda *a: pytest.fail("no payoff path"))
    monkeypatch.setattr(h30, "cuda_predictor_factory", lambda *a: pytest.fail("no training path"))
    facts, rows = d.diagnose(
        sources.items(), root, payload, cpu, cuda, cpu_torch, time.monotonic() + 30
    )
    assert len(facts) == 4 and [tuple(r[k] for k in d.IDENTITY) for r in rows] == d.fit_keys()
    for row in rows:
        assert row["parameter_count"] == 1425 and row["train_count"] >= 128
        assert set(row["train_mse_standardized"]) == {"initial", "final", "train_mean"}
        assert (row["oldest24_mask"] is None) == (row["context"] == 12)
    encoded = h30.encode({"folds": facts, "fits": rows}).decode()
    for forbidden in (
        "channel_mean",
        "channel_scale",
        "target_mean",
        "target_scale",
        "net_dollars",
        "state.encoder",
        "evaluation_outcomes",
        "evaluation_inputs",
    ):
        assert forbidden not in encoded


def test_literal_metrics_and_oldest24_mask_leave_last12_unchanged(cpu_torch, monkeypatch):
    torch = cpu_torch

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.bias = torch.nn.Parameter(torch.tensor([1.0]))

        def forward(self, x):
            return (x[:, 0, 0] * self.bias + x[:, -1, 0]).unsqueeze(1)

    monkeypatch.setattr(h30, "build_torch_sequence_model", lambda **kw: Model())
    values = np.ones((4, 36, 4), dtype=np.float32)
    values[:, -12:] = 2
    tensor = torch.tensor(values)
    fold = SimpleNamespace(train_y=np.zeros(4, dtype=np.float32), y_scale=3.0, y_mean=-1.0)
    result = d.measure(
        torch,
        fold,
        tensor,
        {"state.bias": np.asarray([2.0], dtype=np.float32)},
        36,
        101,
        time.monotonic() + 30,
    )
    assert result["train_mse_standardized"] == {"initial": 9.0, "final": 16.0, "train_mean": 0.0}
    assert result["parameter_movement_rms"] == 1.0
    assert result["oldest24_mask"]["initial"]["rms_change_bps"] == 3.0
    assert result["oldest24_mask"]["final"]["rms_change_bps"] == 6.0
    assert result["prediction_distribution"]["final"]["std_bps"] == 0.0
    assert result["prediction_distribution"]["final"]["positive_fraction"] == 1.0
    np.testing.assert_array_equal(tensor.numpy(), values)


def test_saved_scaler_mismatch_rejected(package):
    root, payload, _, cuda, folds = package
    config, arrays = h30.load_model_arrays(root / "models", cuda["models"][0], d.H30_HASH)
    arrays["target_scale"] *= 2
    with pytest.raises(h30.StudyFailure, match="model_scaler_binding"):
        d.bind_model(config, arrays, folds[0], payload)


def test_summary_hashes_checked_and_payoff_fields_not_returned(package, monkeypatch):
    root, payload, cpu, cuda, _ = package
    (root / "contract.json").write_bytes(h30.encode(payload))
    hashes = {}
    for phase, summary in (("cpu", cpu), ("cuda", cuda)):
        raw = h30.encode(summary)
        (root / f"{phase}-summary.json").write_bytes(raw)
        hashes[phase] = h30.digest(raw)
    monkeypatch.setattr(h30, "verify_contract", lambda *a: (root, b"fixture"))
    monkeypatch.setattr(d, "SUMMARY_HASHES", hashes)
    # The CUDA summary's CPU binding is itself inside its hash-bound bytes.
    cuda["cpu_summary_sha256"] = hashes["cpu"]
    raw = h30.encode(cuda)
    (root / "cuda-summary.json").write_bytes(raw)
    hashes["cuda"] = h30.digest(raw)
    bound = d.bindings(root)
    assert "cells" not in bound[3] and "cells" not in bound[4]
    (root / "cuda-summary.json").write_bytes(raw + b" ")
    with pytest.raises(h30.StudyFailure, match="summary_identity"):
        d.bindings(root)


def test_worker_rejects_binding_before_source_or_torch(tmp_path, monkeypatch):
    scope_hash = h30.digest(h30.encode(d.contract()))
    monkeypatch.setattr(
        d, "bindings", lambda *a: (_ for _ in ()).throw(h30.StudyFailure("summary_identity"))
    )
    original = builtins.__import__

    def guard(name, *args, **kwargs):
        assert name != "torch" and not name.startswith("torch.")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    monkeypatch.setattr(h30, "load_streams", lambda *a: pytest.fail("no source read"))
    target = tmp_path / "result.json"
    d.worker(tmp_path, tmp_path, scope_hash, target)
    result = json.loads(target.read_bytes())
    assert result["status"] == "failed_all16" and result["fits"] == []
    assert result["reason"] == "summary_identity"


@pytest.mark.parametrize(
    "error", [h30.StudyFailure("budget_exhausted"), ValueError("private detail")]
)
def test_worker_failure_keeps_no_partial_metrics(tmp_path, monkeypatch, error):
    scope_hash = h30.digest(h30.encode(d.contract()))
    runtime = {"runtime": {"environment": {}}}
    monkeypatch.setattr(d, "bindings", lambda *a: (tmp_path, b"fixture", {}, runtime, runtime))
    monkeypatch.setattr(h30, "runtime_identity", lambda: {})
    monkeypatch.setattr(h30, "load_streams", lambda *a: iter(()))
    fake = SimpleNamespace(
        set_num_threads=lambda n: None,
        set_num_interop_threads=lambda n: None,
        use_deterministic_algorithms=lambda b: None,
        cuda=SimpleNamespace(is_initialized=lambda: False),
    )
    monkeypatch.setitem(sys.modules, "torch", fake)

    def fail(*args):
        raise error

    monkeypatch.setattr(d, "diagnose", fail)
    target = tmp_path / "failure.json"
    d.worker(tmp_path, tmp_path, scope_hash, target)
    result = json.loads(target.read_bytes())
    assert result["status"] == "failed_all16" and result["fits"] == []
    assert result["unavailable_fits"] == 16 and "private detail" not in target.read_text()


@pytest.mark.parametrize("mode", ["timeout", "partial", "complete"])
def test_cli_uses_existing_watchdog_and_immutable_appendix(tmp_path, monkeypatch, capsys, mode):
    namespace = runpy.run_path(str(h30.REPO / d.OWN_FILES[1]))
    scope_hash = h30.digest(h30.encode(d.contract()))
    monkeypatch.setattr(d, "bindings", lambda *a: (tmp_path, b"fixture", {}, {}, {}))

    def supervised(target, arguments, *, seconds, name):
        assert target is d.worker and seconds == 600 and name == "h30-train-diagnostic-v1"
        assert arguments[:3] == (tmp_path, tmp_path, scope_hash)
        rows = [dict(zip(d.IDENTITY, k, strict=True)) for k in d.fit_keys()]
        if mode == "partial":
            rows.pop()
        arguments[-1].write_bytes(
            h30.encode(
                {"status": "complete", "fits": rows, "diagnostic_contract_sha256": scope_hash}
            )
        )
        return {"timed_out": mode == "timeout", "exit_code": 0}

    monkeypatch.setattr(runpy, "run_path", lambda path: {"supervise": supervised})
    args = [
        "--diagnostic-contract-sha256",
        scope_hash,
        "--artifact-root",
        str(tmp_path),
        "--market-data-root",
        str(tmp_path),
    ]
    assert namespace["main"](args) == (0 if mode == "complete" else 1)
    target = tmp_path / d.NAME / "summary.json"
    raw = target.read_bytes()
    result = json.loads(raw)
    assert len(result["fits"]) == (16 if mode == "complete" else 0)
    assert namespace["main"](args) == 1 and target.read_bytes() == raw
    assert "dispatch_unavailable" in capsys.readouterr().out

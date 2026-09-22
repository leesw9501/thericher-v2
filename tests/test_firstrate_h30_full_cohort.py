"""Synthetic, CPU-only successor checks; no retained source, Docker or CUDA calls."""

from __future__ import annotations

import json
import runpy
import signal
import time
from dataclasses import replace

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff, make_bars, synthetic_receipt
from thericher_v2.research import firstrate_h30_full_cohort as s

h30 = s.h30
HASH = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def source():
    return make_bars()


@pytest.fixture
def reference(source, monkeypatch):
    monkeypatch.setattr(h30, "roundtrip", fast_payoff)
    return h30.compare(
        ((symbol, source) for symbol in h30.SYMBOLS),
        "cpu",
        None,
        time.monotonic() + 30,
        ridge_predictor=lambda f, c: np.zeros(len(f.evaluation)),
    )


@pytest.fixture
def torch_cpu(monkeypatch):
    import torch

    threads, rng = torch.get_num_threads(), torch.get_rng_state()
    torch.set_num_threads(1)
    monkeypatch.setattr(torch.cuda, "manual_seed_all", lambda *a: pytest.fail("CUDA RNG"))
    monkeypatch.setattr(torch.cuda, "_lazy_init", lambda *a: pytest.fail("CUDA init"))
    yield torch
    torch.set_rng_state(rng)
    torch.set_num_threads(threads)


def test_contract_changes_only_declared_training_axis_and_keeps_lineage(tmp_path):
    receipt = synthetic_receipt(tmp_path / "market")
    parent, contract = h30.contract_payload(receipt), s.contract(receipt)
    for key in (
        "source_pins",
        "scalers",
        "purge",
        "split",
        "eligibility",
        "censoring",
        "sampling",
        "minimums",
        "cost_bps_per_side",
        "linear",
        "naives",
        "runtime",
    ):
        assert parent[key] == contract[key]
    assert contract["contexts"] == [12] and contract["seeds"] == [101, 103]
    assert contract["parent_contract_sha256"] == s.d.H30_HASH
    assert contract["learnability_contract_sha256"] == s.LEARN_HASH
    assert "epochs" not in contract["training"]
    assert contract["training"]["updates_per_fit"] == 256
    assert contract["training"]["batch_size"] == 128
    assert contract["budget"]["shared_max_optimizer_updates"] == 2048
    assert contract["budget"]["gpu_fits"] == len(s.KEYS) == 8
    assert contract["budget"]["phase_seconds"] == {"cpu": 600, "cuda": 180}
    assert len(s.expected_cells("cpu")) == 48 and len(s.expected_cells("cuda")) == 24
    assert all(
        contract[k] is False
        for k in (
            "promotion",
            "generalization_claim",
            "ranking",
            "holdout_access",
            "early_stopping",
            "retries",
        )
    )
    assert not list(tmp_path.rglob("contract.json"))


@pytest.mark.parametrize("count", [128, 230, 241, 256, 1024])
def test_exact_minibatch_order_short_tail_and_256_updates(count):
    batches = s.batch_slices(count)
    assert len(batches) == 256
    per_pass = (count + 127) // 128
    assert [i for b in batches[:per_pass] for i in range(b.start, b.stop)] == list(range(count))
    assert all(b.stop - b.start <= 128 for b in batches)
    assert batches[per_pass] == batches[0]


def run_compare(source, reference, phase="cpu", **kwargs):
    return s.compare(
        ((symbol, source) for symbol in h30.SYMBOLS),
        phase,
        reference,
        None,
        time.monotonic() + 30,
        ridge=lambda f, c: np.zeros(len(f.evaluation)),
        **kwargs,
    )


def test_matched_cpu_controls_and_all_eight_fixed_fits(source, reference):
    cpu, retained = run_compare(source, reference)
    assert retained == [] and cpu["fits"] == []
    assert {h30.cell_key(c): c for c in cpu["cells"]} == {
        h30.cell_key(c): c for c in reference["cells"] if c["context"] in (12, None)
    }
    calls = []

    def trainer(torch, fold, seed, deadline):
        calls.append((fold.symbol, fold.fold, 12, seed))
        return (
            np.zeros(len(fold.evaluation)),
            {},
            dict(
                zip(s.d.IDENTITY, calls[-1], strict=True),
                updates=256,
            ),
        )

    cuda, retained = run_compare(source, cpu, "cuda", trainer=trainer)
    cuda["contract_sha256"] = HASH
    s.validate_result(cuda, "cuda", HASH)
    assert calls == list(s.KEYS) and len(retained) == 8
    assert all(
        set(c["matched_baseline_delta_net_dollars"]) == {*h30.NAIVES, "ridge"}
        for c in cuda["cells"]
    )
    assert h30.CONTEXTS == (12, 36) and h30.EPOCHS == 8


@pytest.mark.parametrize("key", ["cohort_sha256", "normalizer_sha256", "evaluation_inputs"])
def test_parent_drift_prevents_fitting(source, reference, key):
    reference["folds"][0][key] = "changed"
    with pytest.raises(h30.StudyFailure, match="parent_cohort"):
        run_compare(source, reference, "cuda", trainer=lambda *a: pytest.fail("fit after drift"))


def test_same_max36_eligibility_purge_and_future_invariant_scalers(source):
    index = {b.start_ts: b for b in source}
    plan = h30.plans(source)[0]
    original = h30.prepare_fold("SPY", 1, index, plan)
    at = original.evaluation[1].at
    changed = dict(index)
    del changed[at - 30 * h30.STEP]
    observed, counts = h30.observe(changed, (at,))
    assert not observed and counts["past_missing"] == 1
    for at, bar in tuple(index.items()):
        if at >= plan[1][0]:
            index[at] = replace(bar, high=bar.high * 2, close=bar.close * 2, volume=bar.volume * 5)
    altered = h30.prepare_fold("SPY", 1, index, plan)
    assert original.facts["normalizer_sha256"] == altered.facts["normalizer_sha256"]
    assert np.array_equal(original.train_y, altered.train_y)
    assert max(plan[0]) + h30.HOLD < plan[2]


def test_actual_cpu_model_exact_updates_full_train_loss_and_final_only(
    source, torch_cpu, monkeypatch
):
    torch = torch_cpu
    fold = h30.prepare_fold("SPY", 1, {b.start_ts: b for b in source}, h30.plans(source)[0])
    step, updates = torch.optim.AdamW.step, []

    def counted(self, *a, **kw):
        updates.append(1)
        return step(self, *a, **kw)

    monkeypatch.setattr(torch.optim.AdamW, "step", counted)
    predicted, state, facts = s.fit(torch, fold, 101, time.monotonic() + 30, device="cpu")
    assert len(updates) == facts["updates"] == 256
    assert facts["train_rows"] == len(fold.train_y)
    assert facts["parameter_movement_rms"] > 0
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    )
    model.load_state_dict({k.removeprefix("state."): torch.from_numpy(v) for k, v in state.items()})
    model.eval()
    with torch.inference_mode():
        train = model(torch.tensor(fold.train_x[:, -12:])).flatten().numpy().astype(np.float64)
        actual = model(torch.tensor(fold.eval_x[:, -12:])).flatten().numpy()
    assert facts["final"]["mse"] == pytest.approx(np.mean((train - fold.train_y) ** 2))
    assert np.array_equal(predicted, actual)
    with pytest.raises(h30.StudyFailure, match="budget_exhausted"):
        s.fit(torch, fold, 101, time.monotonic() - 1, device="cpu")


def test_numeric_final_models_roundtrip_restoration_and_tamper(source, torch_cpu, tmp_path):
    torch = torch_cpu
    fold = h30.prepare_fold("SPY", 1, {b.start_ts: b for b in source}, h30.plans(source)[0])
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    )
    state = {"state." + k: v.detach().numpy().copy() for k, v in model.state_dict().items()}
    retained = [
        (replace(fold, symbol=symbol, fold=number), seed, state)
        for symbol, number, _, seed in s.KEYS
    ]
    root = tmp_path / "models"
    refs = s.save_models(root, retained, HASH, [], {}, torch, time.monotonic() + 30)
    assert len(refs) == 8 and len(list(root.glob("*.npz"))) == 8
    config, arrays = s.load_model(root, refs[0], HASH)
    assert config["final_update"] == 256 and "final_epoch" not in config
    assert config["name"] == s.NAME and np.array_equal(arrays["channel_mean"], fold.channel_mean)
    with (root / refs[0]["weights_file"]).open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(h30.StudyFailure, match="model_hash"):
        s.load_model(root, refs[0], HASH)


def test_worker_binding_failure_discards_all_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(
        s, "verify", lambda *a: (_ for _ in ()).throw(h30.StudyFailure("budget_exhausted"))
    )
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path, HASH, "cuda", HASH, path)
    result = json.loads(path.read_bytes())
    assert result["reason"] == "budget_exhausted" and not result["retained_weights"]
    assert result["cells"] == result["fits"] == result["models"] == []
    assert result["unavailable_cells"] == 24


def test_duplicate_stream_rejected_before_excess_fits(source, reference):
    calls = []

    def trainer(torch, fold, seed, deadline):
        calls.append((fold.symbol, fold.fold, seed))
        return np.zeros(len(fold.evaluation)), {}, {}

    with pytest.raises(h30.StudyFailure, match="fold_matrix"):
        s.compare(
            ((symbol, source) for symbol in ("SPY", "SPY")),
            "cuda",
            reference,
            None,
            time.monotonic() + 30,
            trainer=trainer,
        )
    assert len(calls) == 4


@pytest.mark.parametrize("mode", ["complete", "timeout", "preempt", "partial", "model_failure"])
def test_parent_lock_reaping_contract_no_retry(tmp_path, monkeypatch, mode):
    cli = runpy.run_path(str(h30.REPO / s.OWN_FILES[1]))
    ns = cli["dispatch"].__globals__
    output = h30.run_directory(tmp_path, s.NAME)
    output.mkdir(parents=True)
    lock = ns["resolve_agent_root"](tmp_path) / "locks/gpu.lock"
    monkeypatch.setattr(s, "verify", lambda *a: (output,))
    monkeypatch.setitem(ns, "register_campaign_outcome", lambda **kw: None)
    monkeypatch.setattr(s, "load_model", lambda *a: None)

    def supervise(target, args, *, seconds, name):
        assert target is s.worker and lock.is_file() and seconds == 180 and name == s.NAME
        if mode == "preempt":
            raise KeyboardInterrupt
        models = args[-1].parent / "models"
        models.mkdir()
        refs = [dict(zip(s.d.IDENTITY, key, strict=True)) for key in s.KEYS]
        result = {
            **h30.result_base("cuda"),
            "name": s.NAME,
            "status": "complete",
            "contract_sha256": HASH,
            "cells": [
                {**c, "status": "complete", "parity_verified": True}
                for c in s.expected_cells("cuda")
            ],
            "fits": [{**ref, "updates": 256} for ref in refs],
            "models": refs,
            "retained_weights": True,
        }
        if mode == "partial":
            result["fits"].pop()
        if mode == "model_failure":
            result["models"] = []
        args[-1].write_bytes(h30.encode(result))
        return {"timed_out": mode == "timeout", "exit_code": 0}

    monkeypatch.setattr(ns["runpy"], "run_path", lambda *a: {"supervise": supervise})
    args = [
        "--phase",
        "cuda",
        "--contract-sha256",
        HASH,
        "--cpu-summary-sha256",
        HASH,
        "--artifact-root",
        str(tmp_path),
    ]
    old_handler = signal.getsignal(signal.SIGTERM)
    assert cli["main"](args) == (0 if mode == "complete" else 1)
    assert signal.getsignal(signal.SIGTERM) == old_handler
    assert not lock.exists() and not list(output.glob("cuda-job-*"))
    assert (output / "models").exists() == (mode == "complete")
    raw = (output / "cuda-summary.json").read_bytes()
    assert cli["main"](args) == 1
    assert (output / "cuda-summary.json").read_bytes() == raw and not lock.exists()


def test_existing_lock_and_repo_artifact_boundary(tmp_path, monkeypatch):
    cli = runpy.run_path(str(h30.REPO / s.OWN_FILES[1]))
    ns = cli["dispatch"].__globals__
    monkeypatch.setattr(s, "verify", lambda *a: (tmp_path,))
    monkeypatch.setattr(
        ns["runpy"], "run_path", lambda *a: {"supervise": lambda *a, **kw: pytest.fail("owned GPU")}
    )
    lock = ns["resolve_agent_root"](tmp_path) / "locks/gpu.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("other owner", encoding="ascii")
    assert (
        cli["main"](
            [
                "--phase",
                "cuda",
                "--contract-sha256",
                HASH,
                "--cpu-summary-sha256",
                HASH,
                "--artifact-root",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert lock.read_text(encoding="ascii") == "other owner"
    with pytest.raises(ValueError):
        h30.run_directory(h30.REPO, s.NAME)

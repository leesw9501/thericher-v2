"""Synthetic-only tests; no retained data, training, broker network or GPU."""

from __future__ import annotations

import json
import multiprocessing
import runpy
import time
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff, make_bars, synthetic_receipt
from thericher_v2.research import firstrate_h30_fixed_hurdle as s

h30 = s.h30
HASH = "sha256:" + "a" * 64


def test_contract_single_nominal_threshold_no_new_training_or_selection(tmp_path):
    payload = s.parent.contract(synthetic_receipt(tmp_path / "market"))
    scope = s.contract(payload, [])
    assert all(scope[k] == payload[k] for k in s.INHERITED)
    assert scope["parent_contract_sha256"] == s.PARENT_HASH
    assert scope["decision"]["hurdle_bps"] == 6
    assert not scope["decision"]["exact_breakeven_claim"]
    assert scope["budget"] == {"cpu_seconds": 300, "parent_wall_seconds": 300, "cpu_threads": 1}
    assert scope["cost_bps_per_side"] == [1, 3, 5]
    assert len(set(s.expected_keys())) == 84
    assert all(
        scope[k] is False
        for k in (
            "gpu",
            "model_selection",
            "threshold_search",
            "holdout_access",
            "promotion",
            "generalization_claim",
            "retries",
            "fallback",
            "retained_new_weights",
        )
    )
    assert scope["optimizer_steps"] == 0 and not list(tmp_path.rglob("contract.json"))


def test_hurdle_in_raw_bps_after_inverse_scaling_strict_equality_flat():
    sign, hurdle = s.decisions(np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), 6, 3, 5)
    assert sign == (False, True, True, True, True)
    assert hurdle == (False, False, False, True, True)
    assert all(not h or a for a, h in zip(sign, hurdle, strict=True))
    sign, hurdle = s.decisions([0.0006, 6.0, np.nextafter(6.0, np.inf)], 0, 1, 3)
    assert sign == (True, True, True) and hurdle == (False, False, True)


@pytest.mark.parametrize(
    "values,mean,scale,count",
    [([np.nan], 0, 1, 1), ([1], 0, 0, 1), ([1], np.inf, 1, 1), ([1], 0, -1, 1), ([1], 0, 1, 2)],
)
def test_nonfinite_or_wrong_unit_geometry_fails(values, mean, scale, count):
    with pytest.raises(h30.StudyFailure):
        s.decisions(values, mean, scale, count)


@pytest.fixture(scope="module")
def source():
    return make_bars()


@pytest.fixture
def bound(source, monkeypatch):
    monkeypatch.setattr(h30, "roundtrip", fast_payoff)
    def streams():
        return ((symbol, source) for symbol in h30.SYMBOLS)

    def prediction(fold):
        return np.full(len(fold.evaluation), 0.1)
    cpu = h30.compare(
        streams(), "cpu", None, time.monotonic() + 30, ridge_predictor=lambda f, c: prediction(f)
    )
    cuda = h30.compare(
        streams(),
        "cuda",
        None,
        time.monotonic() + 30,
        cpu_summary=cpu,
        cuda_factory=lambda fold, deadline: lambda c, seed: prediction(fold),
    )
    cuda["models"] = [dict(zip(s.d.IDENTITY, key, strict=True)) for key in s.parent.KEYS]
    prepared = {
        (symbol, number): h30.prepare_fold(symbol, number, {b.start_ts: b for b in source}, plan)
        for symbol in h30.SYMBOLS
        for number, plan in enumerate(h30.plans(source), 1)
    }
    calls = []

    def load(root, ref, scope_hash):
        calls.append(tuple(ref[k] for k in s.d.IDENTITY))
        fold = prepared[(ref["symbol"], ref["fold"])]
        return {
            "source_pins": [],
            "normalizer_sha256": fold.facts["normalizer_sha256"],
            "cohort_sha256": fold.facts["cohort_sha256"],
        }, {
            "channel_mean": fold.channel_mean,
            "channel_scale": fold.channel_scale,
            "target_mean": np.array([fold.y_mean]),
            "target_scale": np.array([fold.y_scale]),
        }

    monkeypatch.setattr(s.parent, "load_model", load)
    monkeypatch.setattr(s, "predict", lambda torch, arrays, x: np.full(len(x), 0.1))
    monkeypatch.setattr(h30, "ridge_predict", lambda *a: pytest.fail("refit"))
    monkeypatch.setattr(s.parent, "fit", lambda *a: pytest.fail("training"))
    return cpu, cuda, calls


def compare(source, bound, tmp_path):
    cpu, cuda, _ = bound
    return s.compare(
        ((symbol, source) for symbol in h30.SYMBOLS),
        tmp_path,
        {"source_pins": []},
        cpu,
        cuda,
        None,
        None,
        time.monotonic() + 30,
    )


def test_all_models_all_cells_reproduction_and_fixed_cost_activity(source, bound, tmp_path):
    result = compare(source, bound, tmp_path)
    result["contract_sha256"] = HASH
    s.validate_result(result, HASH)
    assert bound[2] == list(s.parent.KEYS)
    assert result["prior_replay_cells_reproduced"] == 60
    assert len(result["folds"]) == 4
    for symbol, fold, _, seed in s.parent.KEYS:
        cells = [
            c
            for c in result["cells"]
            if (c["symbol"], c["fold"], c["seed"]) == (symbol, fold, seed)
            and c["candidate"] == "lstm_hurdle"
        ]
        assert len(cells) == 3 and len({c["long_intents"] for c in cells}) == 1
        assert all(set(c["matched_delta_net_dollars"]) == {*h30.NAIVES, "lstm_sign"} for c in cells)
    result["cells"].pop()
    with pytest.raises(h30.StudyFailure, match="cell_matrix"):
        s.validate_result(result, HASH)


@pytest.mark.parametrize(
    "key", ["normalizer_sha256", "cohort_sha256", "evaluation_inputs", "outcome_mask_sha256"]
)
def test_parent_fold_drift_rejected(source, bound, tmp_path, key):
    bound[1]["folds"][0][key] = "changed"
    with pytest.raises(h30.StudyFailure, match="changed"):
        compare(source, bound, tmp_path)


def test_cpu_sign_or_control_difference_rejects_all(source, bound, tmp_path):
    for cell in bound[1]["cells"]:
        cell["net_dollars"] = "999999"
    with pytest.raises(h30.StudyFailure, match="prior_replay_changed"):
        compare(source, bound, tmp_path)


def test_every_signal_fixed_before_future_censor_and_no_backfill(source, tmp_path):
    index = {b.start_ts: b for b in source}
    fold = h30.prepare_fold("SPY", 1, index, h30.plans(source)[0])
    sign, hurdle = s.decisions(np.full(len(fold.evaluation), 7.0), 0, 1, len(fold.evaluation))
    at = fold.evaluation[0].at
    del index[at + h30.HOLD]
    facts, cells = h30.score(
        fold,
        index,
        {("lstm_sign", 12, 101): sign, ("lstm_hurdle", 12, 101): hurdle},
        h30.EmergencyStore(tmp_path / "emergency.json"),
        time.monotonic() + 30,
    )
    assert facts["evaluation_outcomes"]["observed"] == len(sign) - 1
    assert all(
        c["long_intents"] == len(sign) and c["long_censored"] == 1 and c["trades"] == len(sign) - 1
        for c in cells
    )


def test_six_bps_is_not_exact_rounded_fee_breakeven(source, tmp_path):
    path = tuple(
        replace(b, open=p, close=p, high=p, low=p)
        for i, b in enumerate(source[36:43])
        for p in [Decimal("1000.6") if i == 6 else Decimal("1000")]
    )
    outcome = h30.Outcome(path)
    assert outcome.target_bps == 6
    obs = h30.Observation(path[0].start_ts, (), source[35])
    gross, fees = h30.roundtrip(obs, outcome, 3, h30.EmergencyStore(tmp_path / "emergency.json"))
    assert gross - fees == Decimal("-0.0002")


def test_actual_cpu_restore_finite_inference_no_optimizer_or_cuda(monkeypatch):
    import torch

    monkeypatch.setattr(torch.cuda, "_lazy_init", lambda *a: pytest.fail("CUDA"))
    monkeypatch.setattr(torch.optim.AdamW, "step", lambda *a: pytest.fail("optimizer"))
    model = h30.build_torch_sequence_model(
        torch=torch,
        architecture_id="lstm",
        feature_count=4,
        hidden_size=16,
        attention_heads=1,
        tcn_kernel_size=3,
    )
    arrays = {"state." + k: v.detach().numpy().copy() for k, v in model.state_dict().items()}
    x = np.zeros((3, 36, 4), dtype=np.float32)
    got = s.predict(torch, arrays, x)
    model.eval()
    with torch.inference_mode():
        expected = model(torch.tensor(x[:, -12:])).numpy().reshape(-1)
    assert np.array_equal(got, expected) and np.isfinite(got).all()


def test_worker_failure_discards_all_partial_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "cpu_limit", lambda: None)
    monkeypatch.setattr(
        s, "verify", lambda *a: (_ for _ in ()).throw(h30.StudyFailure("parent_summary_changed"))
    )
    path = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path, HASH, path)
    result = json.loads(path.read_bytes())
    assert result == s.failure(HASH, "parent_summary_changed")
    assert result["cells"] == result["folds"] == result["models"] == []


def test_existing_supervisor_timeout_reaps_child():
    supervise = runpy.run_path(str(h30.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))[
        "supervise"
    ]
    job = supervise(time.sleep, (5,), seconds=0.1, name="synthetic-hurdle-timeout")
    assert job["timed_out"] and job["exit_code"] is not None
    assert job["pid"] not in {p.pid for p in multiprocessing.active_children()}

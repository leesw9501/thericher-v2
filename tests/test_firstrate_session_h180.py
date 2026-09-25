"""Synthetic H180 contracts; no retained market data, CUDA, or external services."""

from __future__ import annotations

import copy
import json
import runpy
import socket
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff, synthetic_receipt
from test_firstrate_session_research import source as session_source
from thericher_v2.execution import EmergencyStore
from thericher_v2.research import firstrate_session_h180 as s

HASH = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
H180 = timedelta(minutes=180)
source = session_source


def forbidden(*args, **kwargs):
    raise AssertionError("unexpected external data, network, CUDA, or custody access")


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(s.h30, "load_streams", forbidden)
    monkeypatch.setattr(s, "configure_cuda", forbidden)
    monkeypatch.setattr(s, "GpuFileLock", forbidden, raising=False)
    monkeypatch.setattr(s.base, "register_frozen_campaign", forbidden)


@pytest.fixture(scope="module")
def cohort(source):
    schedule, bars = source
    index = {b.start_ts: b for b in bars}
    folds = tuple(
        s.sessions.prepare_fold("SPY", number, index, plan, 180)
        for number, plan in enumerate(s.plans(schedule), 1)
    )
    return schedule, index, folds


@pytest.fixture
def prepared(source, monkeypatch):
    schedule, bars = source
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
    monkeypatch.setattr(s.h30, "ridge_predict", lambda fold, context: np.zeros(len(fold.eval_x)))
    streams = tuple(
        (symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.h30.SYMBOLS
    )
    return s.prepare(streams)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    root, market = tmp_path / "artifacts", tmp_path / "market"
    receipt = synthetic_receipt(market)
    path = root / s.h30.RECEIPT
    path.parent.mkdir(parents=True)
    path.write_bytes(receipt)
    monkeypatch.setattr(s.importlib.metadata, "version", lambda _: "synthetic")
    registrations = []
    monkeypatch.setattr(s.base, "register_frozen_campaign", lambda **kw: registrations.append(kw))
    pin = s.freeze(root, market)
    output, contract = s.verify(root, market, pin)
    return SimpleNamespace(
        root=root,
        market=market,
        output=output,
        contract=contract,
        pin=pin,
        registrations=registrations,
    )


@pytest.fixture
def fake_sequence(monkeypatch):
    def restore(torch, architecture, arrays):
        assert architecture in s.family.models.ARCHITECTURES
        return arrays["state.forecast"]

    def predict(torch, model, values, device):
        assert device == "cuda" and model.shape == (len(values),)
        return model.copy()

    monkeypatch.setattr(s.family, "restore_sequence", restore)
    monkeypatch.setattr(s.family, "sequence_predict", predict)


def fake_trainer(torch, fold, architecture, seed, deadline):
    assert fold.facts["evaluation_outcomes"] is None
    assert not hasattr(fold, "eval_y")
    assert len(fold.train_y) == len(fold.train_x)
    assert not fold.train_y.flags.writeable
    level = (-3.0, -1.0, 1.0, 7.0)[s.MEMBERS.index((architecture, seed))]
    predicted = np.full(len(fold.eval_x), level)
    facts = dict(
        epochs=32,
        updates=32 * ((len(fold.train_y) + 127) // 128),
        train_rows=len(fold.train_y),
        initial_train_mse=1.0,
        final_train_mse=0.5,
        train_mean_baseline_mse=1.0,
        parameter_count=1,
        peak_cuda_memory_bytes=0,
    )
    return predicted, {"state.forecast": predicted.copy()}, facts


def test_plans_six_train_starts_and_one_eval_per_full_session(source):
    schedule, _ = source
    for fold, (train, evaluation, cutoff, count) in enumerate(s.plans(schedule)):
        left, right = ((80, 120), (120, 160))[fold]
        assert len(train) == left * 6
        assert len(evaluation) == count == 40
        assert evaluation == tuple(o + H180 for o, _ in schedule[left:right])
        assert train[:6] == tuple(schedule[0][0] + H180 + i * s.h30.STEP for i in range(6))
        assert train[5] + H180 == schedule[0][1] - s.h30.STEP
        assert cutoff == evaluation[0] - H180
        assert all(t + H180 < cutoff for t in train)


def test_early_close_exclusions_are_calendar_only_and_preserve_split(source):
    schedule = list(source[0])
    for i in (0, 80, 120):
        opening, _ = schedule[i]
        schedule[i] = opening, opening + timedelta(minutes=210)
    first, second = s.plans(schedule)
    assert first[3] == second[3] == 40
    assert len(first[0]) == 79 * 6
    assert len(second[0]) == 118 * 6
    assert len(first[1]) == len(second[1]) == 39
    assert first[1][0] == schedule[81][0] + H180
    assert second[1][0] == schedule[121][0] + H180


def test_purge_excludes_exact_cutoff_equality(source):
    schedule = list(source[0])
    cutoff = schedule[80][0]
    opening = cutoff - 2 * H180
    schedule[79] = opening, opening + timedelta(minutes=390)
    train, evaluation, actual_cutoff, _ = s.plans(schedule)[0]
    assert actual_cutoff == cutoff == evaluation[0] - H180
    assert opening + H180 not in train
    assert all(t + H180 < cutoff for t in train)


def test_short_or_all_early_close_schedule_is_unavailable(source):
    with pytest.raises(ValueError, match="session_support"):
        s.plans(source[0][:3])
    early = tuple((o, o + timedelta(minutes=210)) for o, _ in source[0])
    with pytest.raises(ValueError, match="evaluation_support"):
        s.plans(early)


def test_prepare_fold_train_only_scalers_survive_eval_mutation(cohort):
    schedule, index, (fold, _) = cohort
    plan = s.plans(schedule)[0]
    changed = {
        at: replace(
            bar,
            open=bar.open * 2,
            high=bar.high * 2,
            low=bar.low * 2,
            close=bar.close * 2,
            volume=bar.volume * 100,
        )
        if at >= plan[2]
        else bar
        for at, bar in index.items()
    }
    other = s.sessions.prepare_fold("SPY", 1, changed, plan, 180)
    for field in ("train_x", "train_y", "channel_mean", "channel_scale"):
        np.testing.assert_array_equal(getattr(fold, field), getattr(other, field))
    assert (fold.y_mean, fold.y_scale) == (other.y_mean, other.y_scale)
    assert fold.facts["normalizer_sha256"] == other.facts["normalizer_sha256"]


def test_prepare_never_reads_eval_outcomes_and_missing_future_preserves_inputs(cohort, monkeypatch):
    schedule, index, (fold, _) = cohort
    plan = s.plans(schedule)[0]
    changed = dict(index)
    for at in plan[1]:
        del changed[at + H180]
    original = s.sessions.outcomes
    calls = []

    def training_only(rows, observations, horizon):
        assert all(o.at + H180 < plan[2] for o in observations)
        calls.append(len(observations))
        return original(rows, observations, horizon)

    monkeypatch.setattr(s.sessions, "outcomes", training_only)
    other = s.sessions.prepare_fold("SPY", 1, changed, plan, 180)
    assert calls == [480]
    assert other.facts["evaluation_outcomes"] is None
    assert other.facts["evaluation_inputs"] == fold.facts["evaluation_inputs"]
    assert other.facts["cohort_sha256"] == fold.facts["cohort_sha256"]
    for field in ("train_x", "train_y", "eval_x"):
        np.testing.assert_array_equal(getattr(fold, field), getattr(other, field))
        assert not getattr(other, field).flags.writeable


def test_prepare_missing_past_drops_only_that_session_without_backfill(cohort):
    schedule, index, (fold, _) = cohort
    plan = s.plans(schedule)[0]
    changed = dict(index)
    del changed[plan[1][0] - s.h30.STEP]
    other = s.sessions.prepare_fold("SPY", 1, changed, plan, 180)
    assert other.evaluation == fold.evaluation[1:]
    assert other.facts["evaluation_inputs"]["past_missing"] == 1
    assert other.facts["normalizer_sha256"] == fold.facts["normalizer_sha256"]


def test_prepare_keeps_four_per_symbol_folds_and_no_eval_targets(prepared):
    assert [(f.symbol, f.fold) for f, *_ in prepared] == [
        (symbol, number) for symbol in ("SPY", "QQQ") for number in (1, 2)
    ]
    for fold, _, selected, forecast in prepared:
        assert len(fold.train_y) == (480 if fold.fold == 1 else 720)
        assert len(fold.eval_x) == fold.facts["eval_blocks_36"] == 40
        assert fold.train_x.shape[1:] == (36, 4)
        assert fold.facts["evaluation_outcomes"] is None
        assert tuple(selected) == s.CPU and set(forecast) == {"ridge", "train_mean"}


def test_prepare_rejects_duplicate_source_timestamp(source, monkeypatch):
    schedule, bars = source
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
    with pytest.raises(ValueError, match="source_order"):
        s.prepare((("SPY", (*bars, bars[0])),))


def test_cpu_fixed_strict_six_bps_threshold_and_readonly_decisions(cohort, monkeypatch):
    _, index, (original, _) = cohort
    fold = replace(original, y_mean=2.0, y_scale=4.0)
    normalized = np.resize(np.array([1.0, 1.0 + 1e-7, 0.0]), len(fold.eval_x))
    monkeypatch.setattr(s.h30, "ridge_predict", lambda f, context: normalized)
    selected, forecasts = s.cpu_predictions(fold, index)
    assert selected["ridge"][:3].tolist() == [False, True, False]
    assert selected["always_long"].all() and not selected["cash"].any()
    assert not selected["train_mean"].any()
    assert all(not flags.flags.writeable for flags in selected.values())
    np.testing.assert_array_equal(forecasts["ridge"], normalized * 4 + 2)


@pytest.mark.parametrize("cost", s.COSTS)
def test_h180_payoff_exact_local_paper_parity(cohort, tmp_path, cost):
    _, index, (fold, _) = cohort
    obs = fold.evaluation[0]
    observed, _ = s.sessions.outcomes(index, (obs,), 180)
    outcome = observed[0]
    assert outcome.bars[-1].start_ts == obs.at + H180
    assert s.sessions.payoff(
        obs, outcome, cost, EmergencyStore(tmp_path / "emergency.json")
    ) == fast_payoff(obs, outcome, cost, None)
    assert outcome.target_bps == float(10000 * (outcome.exit / outcome.entry - 1))


def test_score_real_local_paper_accounting_and_cost_invariant_actions(cohort, tmp_path):
    _, index, (fold, _) = cohort
    observed, _ = s.sessions.outcomes(index, fold.evaluation, 180)
    flags = np.arange(len(observed)) % 2 == 0
    flags.setflags(write=False)
    before = flags.tobytes()
    cells, _ = s.score(
        fold,
        {"synthetic": flags},
        {},
        observed,
        EmergencyStore(tmp_path / "emergency.json"),
        time.monotonic() + 60,
    )
    assert flags.tobytes() == before
    assert len({c["decision_sha256"] for c in cells}) == 1
    assert len({c["gross"] for c in cells}) == 1
    for cell in cells:
        payoffs = [
            fast_payoff(obs, outcome, cell["cost"], None)
            for obs, outcome, active in zip(fold.evaluation, observed, flags, strict=True)
            if active
        ]
        gross = sum((p[0] for p in payoffs), Decimal(0))
        fees = sum((p[1] for p in payoffs), Decimal(0))
        assert tuple(Decimal(cell[k]) for k in ("gross", "fees", "net")) == (
            gross,
            fees,
            gross - fees,
        )
        assert cell["selected"] == cell["roundtrips"] == 20
        assert cell["exposure_minutes"] == 3600 and cell["local_paper"] is True


def test_score_censors_after_decisions_and_rejects_insufficient_outcomes(cohort, monkeypatch):
    _, index, (fold, _) = cohort
    observed, _ = s.sessions.outcomes(index, fold.evaluation, 180)
    flags = np.ones(len(observed), dtype=bool)
    monkeypatch.setattr(s.sessions, "payoff", fast_payoff)
    cells, _ = s.score(
        fold,
        {"synthetic": flags},
        {},
        (None, *observed[1:]),
        None,
        time.monotonic() + 30,
    )
    assert all(c["selected"] == 40 and c["censored"] == 1 and c["roundtrips"] == 39 for c in cells)
    with pytest.raises(ValueError, match="evaluation_outcome_support"):
        s.score(
            fold, {"synthetic": flags}, {}, (None,) * 9 + observed[9:], None, time.monotonic() + 30
        )


def test_whole_family_cpu_then_fake_gpu_uniform_four_excludes_ridge(
    prepared,
    frozen,
    fake_sequence,
    monkeypatch,
):
    monkeypatch.setattr(s.sessions, "payoff", fast_payoff)
    deadline = time.monotonic() + 60
    cpu = s.cpu_compare(prepared, None, deadline)
    assert len(cpu["cells"]) == 60 and len(cpu["folds"]) == 4
    captured, trained = [], []
    original_score = s.score

    def trainer(torch, fold, architecture, seed, until):
        assert len(cpu["cells"]) == 60
        trained.append((fold.symbol, fold.fold, architecture, seed))
        return fake_trainer(torch, fold, architecture, seed, until)

    def score(fold, selected, forecasts, *args):
        assert "ridge" not in forecasts and tuple(selected) == s.GPU
        expected = np.mean([forecasts[f"{a}_{seed}"] for a, seed in s.MEMBERS], axis=0)
        np.testing.assert_allclose(forecasts["uniform_four"], expected)
        captured.append(fold.symbol)
        return original_score(fold, selected, forecasts, *args)

    monkeypatch.setattr(s, "score", score)
    gpu = s.gpu_compare(
        prepared,
        frozen.output / "models",
        frozen.pin,
        cpu,
        None,
        None,
        deadline,
        trainer=trainer,
    )
    assert len(trained) == len(set(trained)) == len(gpu["models"]) == 16
    assert len(gpu["cells"]) == 60 and len(captured) == 4
    assert s.MEMBERS == (
        ("dilated_tcn", 101),
        ("dilated_tcn", 103),
        ("compact_attention", 101),
        ("compact_attention", 103),
    )
    result = dict(
        **s.header(frozen.contract, frozen.pin),
        status="complete",
        criterion="descriptive_no_selection",
        cells=cpu["cells"] + gpu.pop("cells"),
        folds=cpu["folds"],
        runtime=dict(
            torch="synthetic",
            cuda="synthetic",
            cudnn=0,
            device="synthetic",
            cross_runtime_bitwise_claim=False,
            cublas_workspace_config=":4096:8",
            memory_budget_bytes=1024,
            inherited_four_gib_cap=False,
        ),
        **gpu,
    )
    s.validate_result(result, frozen.contract, frozen.pin)
    s.verify_models(frozen.output, result, frozen.pin)
    wrong_budget = copy.deepcopy(result)
    wrong_budget["fits"][0]["updates"] -= 1
    with pytest.raises(ValueError, match="training_budget"):
        s.validate_result(wrong_budget, frozen.contract, frozen.pin)
    wrong_path = copy.deepcopy(result)
    wrong_path["cells"][len(s.CPU)]["decision_sha256"] = OTHER
    with pytest.raises(ValueError, match="cost_changes_path"):
        s.validate_result(wrong_path, frozen.contract, frozen.pin)


def test_gpu_refuses_changed_cpu_cohort(prepared, tmp_path, fake_sequence, monkeypatch):
    monkeypatch.setattr(s.sessions, "payoff", fast_payoff)
    deadline = time.monotonic() + 30
    cpu = s.cpu_compare(prepared, None, deadline)
    cpu["folds"][0]["cohort_sha256"] = OTHER
    with pytest.raises(ValueError, match="cpu_gpu_cohort"):
        s.gpu_compare(
            prepared,
            tmp_path / "models",
            HASH,
            cpu,
            None,
            None,
            deadline,
            trainer=fake_trainer,
        )


def test_retention_numeric_reload_hashes_and_no_overwrite(cohort, tmp_path, fake_sequence):
    fold = cohort[2][0]
    predicted = np.ones(len(fold.eval_x))
    root = tmp_path / "models"
    ref, reloaded = s.retain_model(
        root,
        fold,
        *s.MEMBERS[0],
        {"state.forecast": predicted},
        predicted,
        HASH,
        None,
    )
    cfg = json.loads((root / ref["file"]).read_bytes())
    np.testing.assert_array_equal(reloaded, predicted)
    assert s.digest((root / ref["file"]).read_bytes()) == ref["sha256"]
    assert s.digest((root / ref["weights_file"]).read_bytes()) == cfg["weights_sha256"]
    assert cfg["horizon_minutes"] == 180 and cfg["epochs"] == 32
    assert cfg["numeric_only"] is cfg["reload_parity"] is True
    arrays = s.family.read_arrays(root / ref["weights_file"])
    s.family.check_scalers(arrays, fold)
    assert all(a.dtype != object for a in arrays.values())
    with pytest.raises(FileExistsError):
        s.retain_model(root, fold, *s.MEMBERS[0], {}, predicted, HASH, None)
    s.verify_models(tmp_path, {"models": [ref]}, HASH)
    weights = root / ref["weights_file"]
    original = weights.read_bytes()
    weights.write_bytes(original + b"changed")
    with pytest.raises(ValueError, match="model_weights_hash"):
        s.verify_models(tmp_path, {"models": [ref]}, HASH)
    weights.write_bytes(original)
    (root / ref["file"]).write_bytes(b"{}")
    with pytest.raises(ValueError, match="model_config_hash"):
        s.verify_models(tmp_path, {"models": [ref]}, HASH)


@pytest.mark.parametrize("restored", (1.1, 1.0 + 1e-7))
def test_retention_rejects_prediction_or_decision_flip(cohort, tmp_path, fake_sequence, restored):
    fold = replace(cohort[2][0], y_mean=2.0, y_scale=4.0)
    predicted = np.ones(len(fold.eval_x))
    with pytest.raises(ValueError, match="model_reload"):
        s.retain_model(
            tmp_path / "models",
            fold,
            *s.MEMBERS[0],
            {"state.forecast": np.full(len(predicted), restored)},
            predicted,
            HASH,
            None,
        )


def test_float32_near_point_one_requires_float64_reload_decision_parity(
    cohort,
    tmp_path,
    fake_sequence,
):
    fold = replace(cohort[2][0], y_mean=5.0, y_scale=10.0)
    upper = np.float32(0.1)
    lower = np.nextafter(upper, np.float32(-np.inf))
    pair = np.array([lower, upper], dtype=np.float32)
    assert (pair * 10 + 5 > 6).tolist() == [False, False]
    converted = s.to_bps(fold, pair)
    assert converted.dtype == np.float64
    assert (converted > 6).tolist() == [False, True]
    predicted = np.full(len(fold.eval_x), upper, dtype=np.float32)
    again = np.full(len(fold.eval_x), lower, dtype=np.float32)
    assert np.allclose(predicted, again, rtol=1e-5, atol=1e-6)
    with pytest.raises(ValueError, match="model_reload"):
        s.retain_model(
            tmp_path / "models",
            fold,
            *s.MEMBERS[0],
            {"state.forecast": again},
            predicted,
            HASH,
            None,
        )


def test_uniform_reload_rejects_blend_flip_when_each_member_keeps_decision(
    cohort,
    tmp_path,
    fake_sequence,
    monkeypatch,
):
    fold = replace(cohort[2][0], y_mean=5.0, y_scale=10.0)
    middle = np.float32(0.1)
    lower = np.nextafter(middle, np.float32(-np.inf))
    upper = np.nextafter(middle, np.float32(np.inf))
    original = np.array([lower, lower, upper, upper], dtype=np.float32)
    restored = np.array([lower, lower, middle, middle], dtype=np.float32)
    np.testing.assert_array_equal(s.to_bps(fold, original) > 6, s.to_bps(fold, restored) > 6)
    assert s.to_bps(fold, original.astype(np.float64).mean()) > 6
    assert s.to_bps(fold, restored.astype(np.float64).mean()) < 6
    calls = []

    def trainer(torch, trained, architecture, seed, deadline):
        i = s.MEMBERS.index((architecture, seed))
        calls.append((architecture, seed))
        return (
            np.full(len(fold.eval_x), original[i], dtype=np.float32),
            {"state.forecast": np.full(len(fold.eval_x), restored[i], dtype=np.float32)},
            {},
        )

    monkeypatch.setattr(s.sessions, "outcomes", forbidden)
    with pytest.raises(ValueError, match="ensemble_reload"):
        s.gpu_compare(
            ((fold, cohort[1], {}, {}),),
            tmp_path / "models",
            HASH,
            {},
            None,
            None,
            time.monotonic() + 30,
            trainer=trainer,
        )
    assert calls == list(s.MEMBERS)


def test_retention_rejects_object_arrays(cohort, tmp_path, fake_sequence):
    fold = cohort[2][0]
    with pytest.raises(ValueError, match="Object arrays"):
        s.retain_model(
            tmp_path / "models",
            fold,
            *s.MEMBERS[0],
            {"state.forecast": np.array([{"unsafe": True}], dtype=object)},
            np.zeros(len(fold.eval_x)),
            HASH,
            None,
        )


def test_freeze_verify_external_single_attempt_and_fixed_contract(frozen):
    assert frozen.output.is_relative_to(frozen.root)
    assert len(frozen.registrations) == 1
    assert frozen.registrations[0]["holdout_access"] == "none"
    cfg = frozen.contract["config"]
    assert cfg["context"] == 36 and cfg["horizon_minutes"] == 180
    assert cfg["fits"] == {"ridge": 4, "cuda": 16}
    assert cfg["budget"]["epochs"] == 32 and cfg["budget"]["passes"] == 1
    assert all(cfg[k] is False for k in ("holdout", "promotion", "selection", "broker_input"))
    with pytest.raises(FileExistsError):
        s.freeze(frozen.root, frozen.market)
    with pytest.raises(ValueError, match="binding"):
        s.verify(frozen.root, frozen.market, OTHER)


def test_freeze_rejects_repository_source_and_artifact_roots(frozen):
    with pytest.raises(ValueError, match="source_root"):
        s.freeze(frozen.root, s.REPO)
    with pytest.raises(ValueError, match="source_root"):
        s.verify(frozen.root, s.REPO, frozen.pin)
    with pytest.raises(ValueError, match="outside"):
        s.base.ensure_external_artifact_directory(s.REPO, s.REPO, "research")


def test_verify_rejects_changed_receipt_and_config(frozen, monkeypatch):
    receipt = frozen.root / s.h30.RECEIPT
    original = receipt.read_bytes()
    receipt.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="binding"):
        s.verify(frozen.root, frozen.market, frozen.pin)
    receipt.write_bytes(original)
    old_configuration = s.configuration
    monkeypatch.setattr(s, "configuration", lambda: {**old_configuration(), "context": 12})
    with pytest.raises(ValueError, match="binding"):
        s.verify(frozen.root, frozen.market, frozen.pin)


@pytest.mark.parametrize("case", ("wrong_path", "prior_result", "prior_summary", "wrong_marker"))
def test_worker_rejects_attempt_boundaries_before_loading(frozen, case):
    path = frozen.output / "worker-result.json"
    s.atomic_new(
        frozen.output / "started.json",
        {"contract_sha256": OTHER if case == "wrong_marker" else frozen.pin},
    )
    if case == "wrong_path":
        path = frozen.output / "wrong.json"
    elif case == "prior_result":
        path.write_bytes(b"{}")
    elif case == "prior_summary":
        (frozen.output / "summary.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="attempt|worker_path"):
        s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 30)


def test_worker_cpu_failure_never_enters_cuda_and_emits_closed_failure(frozen, monkeypatch):
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    monkeypatch.setattr(s.h30, "load_streams", lambda *args: ())
    monkeypatch.setattr(s, "prepare", lambda streams: ())
    monkeypatch.setattr(s.h30, "EmergencyStore", lambda path: None)
    monkeypatch.setattr(s, "cpu_compare", forbidden)
    path = frozen.output / "worker-result.json"
    s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 30)
    result = json.loads(path.read_bytes())
    assert result == s.failure(frozen.contract, frozen.pin, "runtime_or_invariant_failure")
    assert not (frozen.output / "cpu-baseline.json").exists()


def test_worker_persists_cpu_before_cuda_and_verifies_after_work(frozen, monkeypatch):
    s.atomic_new(frozen.output / "started.json", {"contract_sha256": frozen.pin})
    events = []
    cpu = dict(cells=[], folds=[])
    monkeypatch.setattr(s.h30, "load_streams", lambda *args: ())
    monkeypatch.setattr(s, "prepare", lambda streams: ())
    monkeypatch.setattr(s.h30, "EmergencyStore", lambda path: None)

    def compare(*args):
        events.append("cpu")
        return cpu

    def cuda():
        assert json.loads((frozen.output / "cpu-baseline.json").read_bytes())["cells"] == []
        events.append("cuda")
        return None, {}

    def gpu(*args):
        assert args[3] is cpu
        events.append("gpu")
        return dict(cells=[], fits=[], models=[], diagnostics=[])

    original_verify = s.verify

    def verify(*args):
        events.append("verify")
        return original_verify(*args)

    monkeypatch.setattr(s, "cpu_compare", compare)
    monkeypatch.setattr(s, "configure_cuda", cuda)
    monkeypatch.setattr(s, "gpu_compare", gpu)
    monkeypatch.setattr(s, "validate_result", lambda *args: events.append("validate"))
    monkeypatch.setattr(s, "verify", verify)
    path = frozen.output / "worker-result.json"
    s.run_worker(frozen.root, frozen.market, frozen.pin, path, time.monotonic() + 30)
    assert json.loads(path.read_bytes())["status"] == "complete"
    assert events == ["verify", "cpu", "cuda", "gpu", "validate", "verify"]


def test_dispatch_timeout_is_single_attempt_without_real_supervisor(frozen, monkeypatch):
    runner = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    dispatch = runner["dispatch"]
    namespace = dispatch.__globals__
    calls, recorded = [], []

    def supervise(*args, **kwargs):
        calls.append(kwargs)
        assert 0 < kwargs["seconds"] <= s.SECONDS
        return dict(timed_out=True, exit_code=None)

    monkeypatch.setitem(namespace, "study", s)
    monkeypatch.setitem(namespace, "worker", s.worker_entry)
    monkeypatch.setitem(namespace, "supervise", supervise)
    monkeypatch.setitem(namespace, "register_campaign_outcome", lambda **kw: recorded.append(kw))
    result = dispatch(frozen.root, frozen.market, frozen.pin)
    assert result["criterion"] == "hard_timeout" and len(calls) == len(recorded) == 1
    with pytest.raises(ValueError, match="attempt_already_exists"):
        dispatch(frozen.root, frozen.market, frozen.pin)
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ("timeout", "raise"))
def test_parent_runner_releases_fake_gpu_lock_after_timeout_or_dispatch_raise(
    frozen,
    monkeypatch,
    mode,
):
    parent = runpy.run_path(str(s.REPO / "scripts/run_tiingo_month_start_development.py"))
    launcher = runpy.run_path(str(s.REPO / "scripts/run_firstrate_session_h180.py"))
    namespace = parent["dispatch"].__globals__
    events = []

    @contextmanager
    def fake_lock(path):
        assert path == frozen.root / "agent" / "locks/gpu.lock"
        events.append("acquire")
        try:
            yield
        finally:
            events.append("release")

    def supervise(*args, **kwargs):
        assert events == ["acquire"]
        events.append("timeout")
        return dict(timed_out=True, exit_code=None)

    def dispatch_error(*args):
        assert events == ["acquire"]
        events.append("raise")
        raise RuntimeError("synthetic dispatch failure")

    class ParentMain:
        __globals__ = namespace

        def __call__(self, argv):
            return namespace["dispatch"](frozen.root, frozen.market, frozen.pin)

    if mode == "raise":
        monkeypatch.setitem(namespace, "dispatch", dispatch_error)
    monkeypatch.setitem(namespace, "supervise", supervise)
    monkeypatch.setitem(namespace, "register_campaign_outcome", lambda **kwargs: None)
    entry = launcher["main"]
    monkeypatch.setitem(entry.__globals__, "os", SimpleNamespace(environ={}))
    monkeypatch.setitem(
        entry.__globals__,
        "runpy",
        SimpleNamespace(run_path=lambda path: {"main": ParentMain()}),
    )
    monkeypatch.setitem(entry.__globals__, "GpuFileLock", fake_lock)
    monkeypatch.setitem(entry.__globals__, "resolve_agent_root", lambda root: frozen.root / "agent")
    if mode == "raise":
        with pytest.raises(RuntimeError, match="synthetic dispatch failure"):
            entry([])
    else:
        assert entry([])["criterion"] == "hard_timeout"
    assert events == ["acquire", mode, "release"]


def test_worker_entry_suppresses_exception_body(monkeypatch):
    def fail(*args):
        raise RuntimeError("synthetic detail must not escape")

    monkeypatch.setattr(s, "run_worker", fail)
    with pytest.raises(SystemExit) as caught:
        s.worker_entry()
    assert caught.value.code == 1 and caught.value.__suppress_context__


def test_failure_validator_rejects_attached_partial_results(frozen):
    result = s.failure(frozen.contract, frozen.pin, "runtime_or_invariant_failure")
    s.validate_result(result, frozen.contract, frozen.pin)
    changed = copy.deepcopy(result)
    changed["cells"] = [{"partial": True}]
    with pytest.raises(ValueError, match="failure_shape"):
        s.validate_result(changed, frozen.contract, frozen.pin)

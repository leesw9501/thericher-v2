"""Synthetic inputs and stub trainers only: no actual model fitting or CUDA."""

from __future__ import annotations

import builtins
import csv
import json
import multiprocessing
import runpy
import sys
import time
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CSV_FIELDS, bar_to_record
from thericher_v2.execution import EmergencyStore
from thericher_v2.research import firstrate_m5_h30_lstm_dev_20260921 as study

START = datetime(2026, 1, 1, tzinfo=UTC)
HASH = "sha256:" + "a" * 64


def make_bars(count=16 * 288, *, timeframe=Timeframe.M5, symbol="SPY"):
    result = []
    for i in range(count):
        price = Decimal(100) + Decimal((i * 17) % 113) / 100
        close = price + (Decimal(".02") if i % 2 else Decimal("-.01"))
        result.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=timeframe,
                start_ts=START + i * timeframe.duration,
                open=price,
                high=max(price, close) + Decimal(".1"),
                low=min(price, close) - Decimal(".1"),
                close=close,
                volume=Decimal(100 + i % 19),
                complete=True,
            )
        )
    return result


@pytest.fixture(scope="module")
def source():
    return tuple(make_bars())


def prepared(source, *, symbol="SPY", number=1):
    index = {b.start_ts: b for b in source}
    return study.prepare_fold(symbol, number, index, study.plans(source)[number - 1])


def fast_payoff(obs, outcome, cost, emergency):
    gross = outcome.exit - outcome.entry
    fees = sum(
        ((p * cost / 10000).quantize(Decimal(".0001")) for p in (outcome.entry, outcome.exit)),
        Decimal(0),
    )
    return gross, fees


def run_stubbed(source, tmp_path, monkeypatch, *, phase="cpu", cpu=None, ridge=None, factory=None):
    monkeypatch.setattr(study, "roundtrip", fast_payoff)
    return study.compare(
        ((s, source) for s in study.SYMBOLS),
        phase,
        EmergencyStore(tmp_path / "emergency.json"),
        time.monotonic() + 30,
        cpu_summary=cpu,
        ridge_predictor=ridge or (lambda f, c: np.zeros(len(f.evaluation))),
        cuda_factory=factory,
    )


def synthetic_receipt(root):
    root.mkdir()
    entries = []
    for symbol in study.SYMBOLS:
        bars = make_bars(1003, timeframe=Timeframe.M1, symbol=symbol)
        path = root / f"{symbol}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(bar_to_record(bar) for bar in bars)
        entries.append(
            {
                "symbol": symbol,
                "market": "US",
                "timeframe": "1m",
                "canonical_market_data_relative_path": path.name,
                "canonical_sha256": study.digest(path.read_bytes()),
                "bar_count": len(bars),
                "timestamp_set_equal": True,
                "emitted_timestamp_set_sha256": study.digest(
                    "".join(f"{b.start_ts.isoformat()}\n" for b in bars).encode()
                ),
            }
        )
    return study.encode(
        {
            "schema_version": "firstrate-free-intraday-normalization-receipt-v1",
            "status": "completed",
            "normalizations": entries,
            "permitted_interpretation": "source_isolated_retrospective_mechanics_only",
        }
    )


def test_full_contract_is_in_memory_only_and_budget_is_shared(tmp_path):
    receipt = synthetic_receipt(tmp_path / "market")
    payload = study.contract_payload(receipt)
    assert payload["contexts"] == [12, 36] and payload["seeds"] == [101, 103]
    assert payload["budget"]["gpu_fits"] == 16
    assert payload["budget"]["ridge_fits"] == 8
    assert payload["budget"]["cost_cells"] == 108
    assert payload["budget"]["phase_seconds"] == {"cpu": 600, "cuda": 1200}
    assert payload["retained_weights"].startswith("all16_final_epoch8")
    assert payload["runtime"]["cublas_workspace_config"] == ":4096:8"
    assert "TRAIN exit" in payload["strongest_kill_test"]
    assert "1/3/5bps" in payload["strongest_kill_test"]
    for key in (
        "promotion",
        "generalization_claim",
        "holdout_access",
        "ranking",
        "retries",
        "early_stopping",
        "oom_fallback",
    ):
        assert payload[key] is False
    assert len(study.expected_cells("cpu")) + len(study.expected_cells("cuda")) == 108
    assert not list(tmp_path.rglob("contract.json"))


@pytest.mark.parametrize(
    "root,repo,allowed",
    [
        (PurePosixPath("/app/market_data"), PurePosixPath("/app"), True),
        (PurePosixPath("/app/market_data/elsewhere"), PurePosixPath("/app"), False),
        (PurePosixPath("/app/src"), PurePosixPath("/app"), False),
        (PurePosixPath("/app/model_artifacts"), PurePosixPath("/app"), False),
        (PureWindowsPath("D:/market_data"), PureWindowsPath("C:/repo"), True),
        (PureWindowsPath("C:/repo/data"), PureWindowsPath("C:/repo"), False),
    ],
)
def test_docker_source_root_is_separate_from_artifact_guard(root, repo, allowed):
    assert study.source_root_allowed(root, repo) is allowed


def test_artifact_guard_stays_strict_and_source_parse_once_per_symbol(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="outside"):
        study.run_directory(study.REPO / "research-output", "fixture")
    market = tmp_path / "market"
    receipt = synthetic_receipt(market)
    original = study.LocalCsvBarProvider.get_bars
    calls = []

    def record(provider, query):
        calls.append(query.symbol)
        return original(provider, query)

    monkeypatch.setattr(study.LocalCsvBarProvider, "get_bars", record)
    loaded = list(study.load_streams(market, receipt, time.monotonic() + 20))
    assert calls == ["SPY", "QQQ"]
    assert [len(b) for _, b in loaded] == [200, 200]  # final three M1 rows dropped
    assert all(b.complete for _, rows in loaded for b in rows)


def test_hourly_schedule_common_context_purge_and_eval_dependence(source):
    index = {b.start_ts: b for b in source}
    for train_times, eval_times, cutoff in study.plans(source):
        train, _ = study.observe(index, train_times)
        evaluation, _ = study.observe(index, eval_times)
        targets, _ = study.outcomes(index, train)
        assert max(y.bars[-1].start_ts for y in targets if y) < cutoff
        assert cutoff <= evaluation[0].at - 36 * study.STEP
        assert all(
            b - a >= study.CADENCE for a, b in zip(eval_times[:-1], eval_times[1:], strict=True)
        )
        assert evaluation[0].at + study.HOLD < evaluation[1].at
        assert evaluation[0].at + study.HOLD > evaluation[1].at - 36 * study.STEP
        assert study.blocks(evaluation) < len(evaluation)  # legitimate dependent eval histories
        assert len(train_times) <= 1024 and len(eval_times) <= 256
    timestamp = START + timedelta(hours=4)
    changed = dict(index)
    del changed[timestamp - 30 * study.STEP]
    assert all(timestamp - i * study.STEP in changed for i in range(1, 13))
    obs, counts = study.observe(changed, (timestamp,))
    assert not obs and counts["past_missing"] == 1  # no short-context backfill


def test_future_data_never_enters_observation_or_fold_scalers(source):
    index = {b.start_ts: b for b in source}
    fold = prepared(source)
    cutoff = study.plans(source)[0][1][0]
    changed = dict(index)
    for at, bar in tuple(changed.items()):
        if at >= cutoff:
            changed[at] = replace(
                bar, close=bar.close * 2, high=bar.high * 2, volume=bar.volume * 9
            )
    second = study.prepare_fold("SPY", 1, changed, study.plans(source)[0])
    assert second.facts["normalizer_sha256"] == fold.facts["normalizer_sha256"]
    np.testing.assert_array_equal(second.train_x, fold.train_x)
    np.testing.assert_array_equal(second.train_y, fold.train_y)
    assert not np.array_equal(second.eval_x, fold.eval_x)
    at = fold.evaluation[3].at
    past = {t: b for t, b in index.items() if t < at}
    a = study.observe(index, (at,))[0]
    b = study.observe(past, (at,))[0]
    assert a == b
    assert study.outcomes(past, b)[1]["future_entry"] == 1
    assert prepared(source, number=2).facts["normalizer_sha256"] != fold.facts["normalizer_sha256"]


@pytest.mark.parametrize("relaxed_cutoff", [False, True])
def test_exact_train_exit_equal_eval_history_start_is_rejected(source, relaxed_cutoff):
    index = {b.start_ts: b for b in source}
    train, evaluation, cutoff = study.plans(source)[0]
    boundary_train = (*train, cutoff - study.HOLD)
    declared_cutoff = cutoff + study.STEP if relaxed_cutoff else cutoff
    with pytest.raises(study.StudyFailure, match="train_label_crosses_eval_history"):
        study.prepare_fold("SPY", 1, index, (boundary_train, evaluation, declared_cutoff))


@pytest.mark.parametrize("cost", [1, 3, 5])
def test_30minute_target_and_literal_fee_accounting_match_broker(tmp_path, cost):
    rows = make_bars(100)
    at = START + timedelta(hours=4)
    obs = study.observe({b.start_ts: b for b in rows}, (at,))[0][0]
    holding = list(rows[48:55])
    holding[0] = replace(
        holding[0],
        open=Decimal("101.123456"),
        high=Decimal(200),
        low=Decimal(1),
        close=Decimal(100),
    )
    holding[-1] = replace(
        holding[-1], open=Decimal("102.765432"), high=Decimal(200), low=Decimal(1), close=Decimal(1)
    )
    outcome = study.Outcome(tuple(holding))
    assert outcome.target_bps == float((Decimal("102.7654") / Decimal("101.1235") - 1) * 10000)
    expected_fee = sum(
        (
            (p * cost / 10000).quantize(Decimal(".0001"))
            for p in (Decimal("101.1235"), Decimal("102.7654"))
        ),
        Decimal(0),
    )
    gross, fees = study.roundtrip(obs, outcome, cost, EmergencyStore(tmp_path / "emergency.json"))
    assert gross == Decimal("1.6419") and fees == expected_fee
    assert not list(tmp_path.rglob("*.sqlite")) and not list(tmp_path.rglob("*.jsonl"))


def test_censoring_missing_holding_path_does_not_change_earlier_intent(source):
    index = {b.start_ts: b for b in source}
    at = START + timedelta(hours=4)
    obs = study.observe(index, (at,))[0]
    del index[at + 3 * study.STEP]
    same = study.observe(index, (at,))[0]
    assert same == obs
    attached, counts = study.outcomes(index, obs)
    assert attached == (None,) and counts["future_holding_path"] == 1


def test_cpu_and_cuda_matrix_match_cohorts_without_training(source, tmp_path, monkeypatch):
    calls = []
    original_import = builtins.__import__

    def import_without_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("stubbed matrix must not import Torch")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_torch)

    def ridge(fold, context):
        calls.append((fold.symbol, fold.fold, context, id(fold.train_x), id(fold.eval_x)))
        return np.zeros(len(fold.evaluation))

    cpu = run_stubbed(source, tmp_path, monkeypatch, ridge=ridge)
    assert cpu["status"] == "complete" and len(cpu["cells"]) == 60
    assert len(calls) == 8
    assert len({c[3] for c in calls}) == len({c[4] for c in calls}) == 4
    assert all(f["train_blocks_36"] >= 16 and f["eval_blocks_36"] >= 8 for f in cpu["folds"])
    assert all(
        c["trades"] == c["scored_decisions"]
        for c in cpu["cells"]
        if c["candidate"] == "always_long"
    )
    assert all(c["trades"] == 0 for c in cpu["cells"] if c["candidate"] == "always_flat")
    cpu["contract_sha256"] = HASH
    assert study.bind_cpu_summary(cpu, HASH) is cpu
    gpu_calls, materializations = [], []

    def factory(fold, deadline):
        materializations.append((fold.symbol, fold.fold))

        def predict(context, seed):
            gpu_calls.append((fold.symbol, fold.fold, context, seed))
            return np.zeros(len(fold.evaluation))

        return predict

    gpu = run_stubbed(source, tmp_path, monkeypatch, phase="cuda", cpu=cpu, factory=factory)
    assert gpu["status"] == "complete" and len(gpu["cells"]) == 48
    assert len(materializations) == 4 and len(gpu_calls) == 16
    assert gpu_calls == [
        (s, f, c, seed)
        for s in study.SYMBOLS
        for f in (1, 2)
        for c in study.CONTEXTS
        for seed in study.SEEDS
    ]
    for cell in gpu["cells"]:
        assert set(cell["matched_baseline_delta_net_dollars"]) == {*study.NAIVES, "ridge"}
        assert Decimal(cell["matched_baseline_delta_net_dollars"]["ridge"]) == 0
        assert cell["eligible_decisions"] == cell["scored_decisions"] + cell["future_censored"]


def test_no_performance_gate_and_no_shortfall_backfill(source, tmp_path, monkeypatch):
    cpu = {
        **study.result_base("cpu"),
        "status": "complete",
        "contract_sha256": HASH,
        "cells": [
            {**c, "status": "complete", "net_dollars": "-999999"}
            for c in study.expected_cells("cpu")
        ],
    }
    assert study.bind_cpu_summary(cpu, HASH) is cpu
    scheduled = study.plans(source)
    removed = {t - study.STEP for train, evaluation, _ in scheduled for t in (*train, *evaluation)}
    gapped = tuple(b for b in source if b.start_ts not in removed)
    assert study.plans(gapped) == scheduled

    def forbid(*args):
        raise AssertionError("no fit on insufficient predeclared support")

    result = run_stubbed(gapped, tmp_path, monkeypatch, ridge=forbid)
    assert result["status"] == "input_unavailable"
    assert len(result["cells"]) == 60
    assert all(c["status"] == "unavailable" and "net_dollars" not in c for c in result["cells"])
    assert all(c["eligible_decisions"] == c["scored_decisions"] == 0 for c in result["cells"])
    assert all(f["eval_blocks_36"] == 0 for f in result["folds"])


@pytest.mark.parametrize("reason", ["budget_exhausted", "nonfinite_loss", "oom_no_fallback"])
def test_failure_discards_every_partial_phase_metric(source, tmp_path, monkeypatch, reason):
    count = 0

    def fail_later(fold, context):
        nonlocal count
        count += 1
        if count == 3:
            raise study.StudyFailure(reason)
        return np.zeros(len(fold.evaluation))

    result = run_stubbed(source, tmp_path, monkeypatch, ridge=fail_later)
    assert result["status"] == "failed_all_phase_cells" and result["reason"] == reason
    assert count == 3  # no retry or adaptive epoch/seed recovery
    assert len(result["cells"]) == 60 and result["retained_weights"] is False
    assert all(c["status"] == "unavailable" and "net_dollars" not in c for c in result["cells"])
    known = [c for c in result["cells"] if c["symbol"] == "SPY" and c["fold"] == 1]
    unknown = [c for c in result["cells"] if c["symbol"] == "SPY" and c["fold"] == 2]
    assert all(c["scored_decisions"] > 0 and c["future_censored"] == 0 for c in known)
    assert all(c["eligible_decisions"] > 0 and c["scored_decisions"] is None for c in unknown)


def fake_states():
    return {
        k: np.full(shape, 0.125, dtype=np.float32)
        for k, shape in study.STATE_SHAPES.items()
        if k.startswith("state.")
    }


@pytest.fixture
def bundles(source, tmp_path):
    retained = [
        (prepared(source, symbol=s, number=f), c, seed, fake_states())
        for s in study.SYMBOLS
        for f in (1, 2)
        for c in study.CONTEXTS
        for seed in study.SEEDS
    ]
    root = tmp_path / "models"
    references = study.save_final_models(
        root, retained, HASH, [], {"fixture": True}, time.monotonic() + 30
    )
    return root, references, retained


def test_all16_final_states_numeric_save_load_no_scalers_in_manifest(bundles):
    root, references, retained = bundles
    assert len(references) == 16 and len(list(root.iterdir())) == 32
    for reference, (fold, context, seed, original) in zip(references, retained, strict=True):
        config, arrays = study.load_model_arrays(root, reference, HASH)
        assert (
            config["final_epoch"] == 8 and config["context"] == context and config["seed"] == seed
        )
        assert config["private_development_inference_only"] is True
        assert config["promotion"] is False
        for name in original:
            np.testing.assert_array_equal(arrays[name], original[name])
        np.testing.assert_array_equal(arrays["channel_mean"], fold.channel_mean)
        assert arrays["target_mean"][0] == fold.y_mean
        assert "channel_mean" not in config and "target_mean" not in config
        assert all(a.dtype.kind == "f" for a in arrays.values())


@pytest.mark.parametrize(
    "key,value", [("symbol", "QQQ"), ("fold", 2), ("context", 36), ("seed", 103)]
)
def test_swapped_reference_rejected_even_when_enum_valid(bundles, key, value):
    root, references, _ = bundles
    with pytest.raises(study.StudyFailure, match="model_config_identity"):
        study.load_model_arrays(root, {**references[0], key: value}, HASH)


def test_unsafe_arrays_and_tampering_rejected_before_inference(bundles):
    root, references, _ = bundles
    _, arrays = study.load_model_arrays(root, references[0], HASH)
    arrays["target_mean"] = np.asarray([object()], dtype=object)
    with pytest.raises(study.StudyFailure, match="geometry"):
        study.validate_model_arrays(arrays)
    path = root / references[0]["weights_file"]
    with path.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(study.StudyFailure, match="weights_hash"):
        study.load_model_arrays(root, references[0], HASH)


def test_restore_wires_identical_numeric_state_and_scalers_without_torch_training(
    bundles, monkeypatch
):
    root, references, retained = bundles

    class Tensor:
        def __init__(self, array):
            self.array = np.asarray(array)

        def flatten(self):
            return Tensor(self.array.flatten())

        def numpy(self):
            return self.array

    class Model:
        def load_state_dict(self, state, strict):
            assert strict and len(state) == 6
            self.state = state

        def eval(self):
            return self

        def __call__(self, tensor):
            return Tensor(tensor.array[:, -1, 0] + self.state["head.bias"].array[0])

    calls = []

    def build(**kwargs):
        calls.append(kwargs)
        return Model()

    monkeypatch.setattr(study, "build_torch_sequence_model", build)
    torch = SimpleNamespace(from_numpy=Tensor, no_grad=nullcontext)
    predictor = study.restore_predictor(root, references[0], HASH, torch)
    fold = retained[0][0]
    values = np.arange(2 * 12 * 4, dtype=np.float64).reshape(2, 12, 4) / 100
    scaled = ((values - fold.channel_mean) / fold.channel_scale).astype("float32")
    expected = (scaled[:, -1, 0] + 0.125) * fold.y_scale + fold.y_mean
    np.testing.assert_allclose(predictor(values), expected)
    assert calls[0]["architecture_id"] == "lstm" and calls[0]["hidden_size"] == 16


def test_cuda_environment_rejected_before_torch_import(monkeypatch):
    monkeypatch.delenv("CUBLAS_WORKSPACE_CONFIG", raising=False)
    with pytest.raises(study.StudyFailure, match="cublas_workspace_config_mismatch"):
        study.configure_cuda()


def test_categorical_cuda_preflight_uses_fake_runtime_only(monkeypatch):
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    calls = []
    torch = SimpleNamespace(
        __fixture_only__=True,
        __version__="2.7.0+cu128",
        version=SimpleNamespace(cuda="12.8"),
        set_num_threads=lambda n: calls.append(("threads", n)),
        use_deterministic_algorithms=lambda b: calls.append(("deterministic", b)),
        backends=SimpleNamespace(
            cudnn=SimpleNamespace(version=lambda: 123),
            cuda=SimpleNamespace(matmul=SimpleNamespace()),
        ),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            get_device_properties=lambda n: SimpleNamespace(total_memory=24 * 1024**3),
            set_per_process_memory_fraction=lambda f, n: calls.append(("memory", f)),
            get_device_name=lambda n: "synthetic-device",
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    actual, metadata = study.configure_cuda()
    assert actual is torch and metadata["cross_runtime_bitwise_claim"] is False
    assert ("memory", 1 / 6) in calls
    torch.__version__ = "unexpected"
    with pytest.raises(study.StudyFailure, match="runtime_version_mismatch"):
        study.configure_cuda()


def cli_namespace():
    return runpy.run_path(str(study.REPO / "scripts/run_firstrate_m5_h30_lstm_dev_20260921.py"))


def test_named_parent_watchdog_kills_and_reaps_without_training():
    job = cli_namespace()["supervise"](time.sleep, (30,), seconds=0.15, name="fixture-h30-watchdog")
    assert job["timed_out"] is True and job["name"] == "fixture-h30-watchdog"
    assert job["exit_code"] is not None and job["elapsed_seconds"] < 5
    assert all(p.pid != job["pid"] for p in multiprocessing.active_children())


def test_worker_rejects_cross_runtime_cpu_binding_before_source_or_cuda(tmp_path, monkeypatch):
    cpu = {
        **study.result_base("cpu"),
        "status": "complete",
        "contract_sha256": HASH,
        "runtime": {"environment": {"python": "other"}},
        "cells": [{**c, "status": "complete"} for c in study.expected_cells("cpu")],
    }
    raw = study.encode(cpu)
    (tmp_path / "cpu-summary.json").write_bytes(raw)
    monkeypatch.setattr(study, "verify_contract", lambda *args: (tmp_path, b"fixture"))
    monkeypatch.setattr(study, "runtime_identity", lambda: {"python": "fixture"})

    def forbid(*args):
        raise AssertionError("must reject before source or GPU")

    monkeypatch.setattr(study, "configure_cuda", forbid)
    monkeypatch.setattr(study, "load_streams", forbid)
    output = tmp_path / "worker.json"
    study.worker_entry(tmp_path, tmp_path, "fixture", HASH, "cuda", study.digest(raw), output)
    result = json.loads(output.read_bytes())
    assert result["reason"] == "cpu_cuda_runtime_mismatch" and len(result["cells"]) == 48
    assert result["retained_weights"] is False


def test_cli_requires_freeze_identity_and_suppresses_private_errors(tmp_path, capsys):
    main = cli_namespace()["main"]
    with pytest.raises(SystemExit):
        main(["--phase", "cpu", "--run-label", "fixture"])
    with pytest.raises(SystemExit):
        main(["--phase", "cuda", "--run-label", "fixture", "--contract-sha256", HASH])
    assert (
        main(
            [
                "--phase",
                "cpu",
                "--run-label",
                "fixture",
                "--contract-sha256",
                HASH,
                "--artifact-root",
                str(tmp_path),
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "dispatch_unavailable" and str(tmp_path) not in json.dumps(payload)

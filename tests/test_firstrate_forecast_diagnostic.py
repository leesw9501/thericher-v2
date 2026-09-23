"""Synthetic retained-model integration checks; never read real research artifacts."""

import copy
import json
import socket
import sys
import time
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff
from test_firstrate_session_research import source  # noqa: F401
from thericher_v2.research import firstrate_forecast_diagnostic as s

HASH, OTHER = "sha256:" + "a" * 64, "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    original = Path.open

    def safe_open(path, *args, **kwargs):
        normalized = str(path).replace("\\", "/").lower()
        assert not normalized.startswith(("d:/market_data", "d:/thericher-v2/model-artifacts"))
        assert not path.name.startswith(".env")
        return original(path, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        pytest.fail("actual data, fitting, GPU, broker, or network access forbidden")

    monkeypatch.setattr(Path, "open", safe_open)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    for name in ("load_streams", "configure_cuda", "LocalPaperBroker"):
        monkeypatch.setattr(s.h30, name, forbidden)
    for name in ("fit_lightgbm", "fit_sequence"):
        monkeypatch.setattr(s.family.models, name, forbidden)


def identity(symbol, number, name, seed):
    return dict(zip(s.family.IDENTITY, (symbol, number, 30, name, 36, seed), strict=True))


@pytest.fixture
def matrix(source, tmp_path, monkeypatch):  # noqa: F811
    schedule, bars = source
    schedule = schedule[:40]
    bars = tuple(b for b in bars if b.start_ts < schedule[-1][1])
    streams = tuple(
        (symbol, tuple(replace(b, symbol=symbol) for b in bars)) for symbol in s.h30.SYMBOLS
    )
    monkeypatch.setattr(s.sessions, "regular_sessions", lambda _: schedule)
    original_outcomes, original_score = s.sessions.outcomes, s.family.score

    def outcomes(index, observations, horizon):
        observed, counts = original_outcomes(index, observations, horizon)
        if len(observations) == 60:
            observed = list(observed)
            observed[1] = None
            counts.update(observed=59, future_missing=1)
        return tuple(observed), counts

    monkeypatch.setattr(s.sessions, "outcomes", outcomes)
    monkeypatch.setattr(s.family, "score", lambda *a: original_score(*a, replay=fast_payoff))
    state = SimpleNamespace(
        streams=streams,
        results={phase: dict(cells=[], folds=[], models=[]) for phase in ("cpu", "cuda")},
        folds={},
        calls=[],
        configs=[],
        arrays={},
        root=tmp_path,
    )
    for phase in state.results:
        (tmp_path / f"{phase}-models").mkdir()
    for symbol, values in streams:
        index = {b.start_ts: b for b in values}
        for number, plan in enumerate(s.sessions.plans(schedule, 30), 1):
            fold = s.sessions.prepare_fold(symbol, number, index, plan, 30)
            state.folds[symbol, number] = fold
            predictions = np.resize(np.array([-8.0, 7.0, 6.0, 0.0, 12.0]), len(fold.evaluation))
            selected = []
            for name, seed in s.CANDIDATES:
                ident = identity(symbol, number, name, seed)
                selected.append((ident, predictions > 6))
                if name == "lstm":
                    continue
                phase = "cpu" if name == "lightgbm" else "cuda"
                path = tmp_path / f"{phase}-models" / f"{symbol}-{number}-{name}-{seed}.json"
                path.write_bytes(s.h30.encode(dict(cohort_sha256=fold.facts["cohort_sha256"])))
                state.results[phase]["models"].append({**ident, "config_file": path.name})
                state.configs.append(path)
            cells = s.family.score(fold, selected, index, None, time.monotonic() + 60)
            for phase in state.results:
                state.results[phase]["folds"].append(copy.deepcopy(fold.facts))
                state.results[phase]["cells"].extend(
                    c for c in cells if (c["candidate"] in ("lstm", "lightgbm")) == (phase == "cpu")
                )
            state.arrays[symbol, number] = s.family.scaler_arrays(fold)

    def predict(fold, name, seed):
        state.calls.append((fold.symbol, fold.fold, name, seed))
        values = np.resize(np.array([-8.0, 7.0, 6.0, 0.0, 12.0]), len(fold.evaluation))
        return (values - fold.y_mean) / fold.y_scale

    def load_model(root, ref, scope_hash, torch):
        assert scope_hash == s.FAMILY_CONTRACT and torch is None
        phase = "cpu" if ref["candidate"] == "lightgbm" else "cuda"
        assert root == tmp_path / f"{phase}-models"
        fold = state.folds[ref["symbol"], ref["fold"]]

        def tree(values, *, num_threads):
            assert num_threads == 1 and values.shape == (60, 144)
            return predict(fold, ref["candidate"], ref["seed"])

        return SimpleNamespace(predict=tree, fold=fold, ref=ref), state.arrays[
            fold.symbol, fold.fold
        ]

    monkeypatch.setattr(s.family, "load_model", load_model)
    monkeypatch.setattr(
        s.family, "parent_prediction", lambda torch, fold, seed, *_: predict(fold, "lstm", seed)
    )
    monkeypatch.setattr(
        s.family,
        "sequence_predict",
        lambda torch, model, values: predict(model.fold, model.ref["candidate"], model.ref["seed"]),
    )
    return state


def compare(matrix):
    return s.compare(
        matrix.streams,
        None,
        None,
        {},
        matrix.root,
        matrix.results,
        None,
        time.monotonic() + 60,
        HASH,
    )


def test_fixed28_inference_parent84_replay_and_common_censoring(matrix, monkeypatch):
    original = s.summarize_forecast
    seen = []

    def summarize(prediction, target, keys, *, train_mean_bps):
        if keys != ["synthetic"]:
            assert len(prediction) == len(target) == len(keys) == 59
            np.testing.assert_allclose(prediction[:4], [-8, 6, 0, 12], atol=1e-12)
            seen.append(train_mean_bps)
        return original(prediction, target, keys, train_mean_bps=train_mean_bps)

    monkeypatch.setattr(s, "summarize_forecast", summarize)
    result = compare(matrix)
    s.validate_result(result, HASH)
    assert len(result["cells"]) == len(matrix.calls) == 28
    assert len(result["folds"]) == 4 and result["parent_controls_reproduced"] == 84
    assert seen == [fold.y_mean for fold in matrix.folds.values() for _ in s.CANDIDATES]
    assert all(result[k] is False for k in s.FLAGS)
    assert all(
        (c["eligible_decisions"], c["future_censored"], c["selected_censored"]) == (60, 1, 1)
        for c in result["cells"]
    )
    assert matrix.calls == [
        (symbol, number, name, seed)
        for symbol in s.h30.SYMBOLS
        for number in (1, 2)
        for name, seed in s.CANDIDATES
    ]


def test_all_seven_predictions_are_frozen_before_any_eval_outcome(matrix, monkeypatch):
    original = s.sessions.outcomes

    def outcomes(index, observations, horizon):
        if len(observations) == 60:
            assert [(name, seed) for _, _, name, seed in matrix.calls] == list(s.CANDIDATES)
            raise RuntimeError("synthetic stop before evaluation outcomes")
        return original(index, observations, horizon)

    original_forecasts = s.forecasts

    def forecasts(*args):
        result = original_forecasts(*args)
        assert all(not values.flags.writeable and len(values) == 60 for _, values in result)
        return result

    monkeypatch.setattr(s.sessions, "outcomes", outcomes)
    monkeypatch.setattr(s, "forecasts", forecasts)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        compare(matrix)


@pytest.mark.parametrize("case", ("replay", "fold", "scaler", "config_cohort"))
def test_parent_replay_cohort_and_scaler_mismatch_kill_whole_comparison(matrix, case):
    if case == "replay":
        matrix.results["cuda"]["cells"][-1]["selected_decisions"] += 1
    elif case == "fold":
        matrix.results["cpu"]["folds"][-1]["normalizer_sha256"] = OTHER
    elif case == "scaler":
        matrix.arrays[s.h30.SYMBOLS[0], 1]["target_mean"] += 1
    else:
        matrix.configs[0].write_bytes(s.h30.encode(dict(cohort_sha256=OTHER)))
    with pytest.raises(s.h30.StudyFailure, match="parent_control_mismatch"):
        compare(matrix)


@pytest.mark.parametrize("case", ("identity", "count", "partial", "holdout"))
def test_result_identity_and_complete_matrix_are_bound(matrix, case):
    result = compare(matrix)
    if case == "identity":
        result["contract_sha256"] = OTHER
    elif case == "count":
        result["parent_controls_reproduced"] -= 1
    elif case == "partial":
        result["cells"].pop()
    else:
        result["holdout_access"] = True
    with pytest.raises(s.h30.StudyFailure):
        s.validate_result(result, HASH)


@pytest.mark.parametrize("case", ("missing_metrics", "raw_predictions", "raw_fold", "censor_count"))
def test_success_payload_rejects_incomplete_or_raw_evidence(matrix, case):
    result = compare(matrix)
    if case == "missing_metrics":
        del result["cells"][0]["metrics"]
    elif case == "raw_predictions":
        result["cells"][0]["metrics"]["raw_predictions"] = ["PRIVATE synthetic row"]
    elif case == "raw_fold":
        result["folds"][0]["raw_predictions"] = ["PRIVATE synthetic row"]
    else:
        result["cells"][0]["future_censored"] = 61
    with pytest.raises((s.h30.StudyFailure, ValueError, KeyError)):
        s.validate_result(result, HASH)


def test_freeze_pins_28_existing_models_code_and_no_new_holdout(tmp_path, monkeypatch):
    refs = [{"weights_sha256": HASH, "synthetic_id": i} for i in range(28)]
    results = {"cpu": {"models": refs[8:12]}, "cuda": {"models": refs[12:]}}
    monkeypatch.setattr(
        s, "lineage", lambda root: (root, b"synthetic receipt", {}, root, results, refs[:8])
    )
    monkeypatch.setattr(s.sessions, "contract", lambda _: {"source_pins": [{"sha256": OTHER}]})
    calls = []
    monkeypatch.setattr(s.h30, "register_frozen_campaign", lambda **kw: calls.append(kw))
    pin = s.freeze(tmp_path)
    output = s.verify(tmp_path, pin)
    cfg = json.loads((output / "contract.json").read_bytes())
    assert cfg["parent_models"] == refs and cfg["parent_summaries"] == s.SUMMARIES
    assert cfg["parent_contract_sha256"] == s.FAMILY_CONTRACT
    assert set(cfg["code_sha256"]) == set(s.CODE)
    assert len(cfg["candidates"]) == 7 and all(cfg[k] is False for k in s.FLAGS)
    assert calls[0]["holdout_access"] == "none" and calls[0]["contract_hash"] == pin
    monkeypatch.setattr(s, "SECONDS", s.SECONDS + 1)
    with pytest.raises(s.h30.StudyFailure, match="contract_changed"):
        s.verify(tmp_path, pin)
    with pytest.raises(FileExistsError):
        s.freeze(tmp_path)


def test_repo_artifact_root_rejected_before_lineage_read(monkeypatch):
    monkeypatch.setattr(s, "lineage", lambda *_: pytest.fail("path must fail before reads"))
    with pytest.raises(ValueError):
        s.freeze(s.REPO / "generated-forecast-artifacts")


@pytest.mark.parametrize("changed", (None, "summary", "config", "weights", "scalers"))
def test_lineage_binds_retained_family_bytes_without_loading_models(tmp_path, monkeypatch, changed):
    refs, pins, validations = [], {}, []
    for phase in ("cpu", "cuda"):
        directory = tmp_path / f"{phase}-models"
        directory.mkdir()
        ref = {}
        for field in ("config", "weights", "scalers"):
            path = directory / f"synthetic-{field}.bin"
            path.write_bytes(f"synthetic {phase} {field}".encode())
            ref[field + "_file"] = path.name
            ref[field + "_sha256"] = s.h30.digest(path.read_bytes())
        refs.append(ref)
        raw = s.h30.encode({"models": [ref]})
        (tmp_path / f"{phase}-summary.json").write_bytes(raw)
        pins[phase] = s.h30.digest(raw)
    monkeypatch.setattr(s, "SUMMARIES", pins)
    monkeypatch.setattr(s.position, "lineage", lambda root: (root, b"synthetic", {}, []))
    monkeypatch.setattr(s.family, "verify", lambda root, pin: (root, None, None))
    monkeypatch.setattr(s.family, "validate_result", lambda *args: validations.append(args[1:]))
    monkeypatch.setattr(s.family, "load_model", lambda *_: pytest.fail("metadata only"))
    if changed is not None:
        path = (
            tmp_path / "cuda-summary.json"
            if changed == "summary"
            else tmp_path / "cuda-models" / refs[-1][changed + "_file"]
        )
        path.write_bytes(path.read_bytes() + b"changed")
        with pytest.raises(s.h30.StudyFailure, match="lineage_changed|model_reload"):
            s.lineage(tmp_path)
    else:
        result = s.lineage(tmp_path)
        assert result[:4] == (tmp_path, b"synthetic", {}, tmp_path)
        assert validations == [(phase, s.FAMILY_CONTRACT) for phase in ("cpu", "cuda")]


@pytest.mark.parametrize("stage", ("compare", "reverify", "deadline"))
def test_worker_failure_discards_all_partial_cells_and_private_errors(tmp_path, monkeypatch, stage):
    calls = []
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "7")
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            set_num_threads=lambda n: calls.append(("threads", n)),
            use_deterministic_algorithms=lambda yes: calls.append(("deterministic", yes)),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "threadpoolctl",
        SimpleNamespace(
            threadpool_limits=lambda **kw: nullcontext(),
        ),
    )
    monkeypatch.setattr(
        s.h30.importlib.metadata,
        "version",
        lambda name: {"pandas-market-calendars": "5.4.0", "lightgbm": "4.6.0"}[name],
    )
    verifies = []

    def verify(*_):
        verifies.append(True)
        if stage == "reverify" and len(verifies) == 2:
            raise ValueError("PRIVATE synthetic source changed")

    def calculation(*_):
        if stage == "compare":
            raise ValueError("PRIVATE synthetic partial predictions")
        return {**s.failure(HASH, None), "status": "complete", "cells": [{"raw": "PRIVATE"}]}

    def deadline(*_):
        if stage == "deadline":
            raise s.h30.StudyFailure("budget_exhausted")

    monkeypatch.setattr(s, "verify", verify)
    monkeypatch.setattr(s, "lineage", lambda root: (root, b"synthetic", {}, root, {}, []))
    monkeypatch.setattr(s.h30, "load_streams", lambda *_: ())
    monkeypatch.setattr(s.h30, "EmergencyStore", lambda *_: None)
    monkeypatch.setattr(s, "compare", calculation)
    monkeypatch.setattr(s.h30, "check_time", deadline)
    output = tmp_path / "result.json"
    s.worker(tmp_path, tmp_path / "never-read", HASH, output)
    assert json.loads(output.read_bytes()) == s.failure(HASH, "runtime_or_invariant_failure")
    assert calls == [("threads", 1), ("deterministic", True)]
    with pytest.raises(FileExistsError):
        s.worker(tmp_path, tmp_path / "never-read", HASH, output)

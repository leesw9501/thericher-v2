"""Independent synthetic comparison checks; no market files, network, or brokers."""

from __future__ import annotations

import copy
import json
import socket
import sys
import time
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest

from test_firstrate_m5_h30_lstm_dev_20260921 import fast_payoff
from test_firstrate_session_research import source  # noqa: F401
from thericher_v2.research import firstrate_family_comparison as s

h30, sessions = s.h30, s.sessions
HASH, OTHER = "sha256:" + "a" * 64, "sha256:" + "b" * 64


@pytest.fixture(autouse=True)
def no_external_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected broker, actual-data, or network access")

    for name in ("LocalPaperBroker", "EmergencyStore", "load_streams"):
        monkeypatch.setattr(h30, name, forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def normalizer_digest(arrays):
    return h30.digest(
        arrays["channel_mean"].tobytes()
        + arrays["channel_scale"].tobytes()
        + h30.encode([float(arrays["target_mean"][0]), float(arrays["target_scale"][0])])
    )


def prepared():
    fold = h30.PreparedFold(
        "SPY",
        1,
        np.zeros((129, 36, 4), np.float32),
        np.zeros((3, 36, 4), np.float32),
        np.linspace(-1, 1, 129, dtype=np.float32),
        2.0,
        4.0,
        np.arange(4, dtype=np.float64),
        np.arange(1, 5, dtype=np.float64),
        (),
        {"cohort_sha256": HASH},
    )
    fold.facts["normalizer_sha256"] = normalizer_digest(s.scaler_arrays(fold))
    return fold


def identity(candidate="lightgbm", seed=101):
    return dict(zip(s.IDENTITY, ("SPY", 1, 30, candidate, 36, seed), strict=True))


@pytest.fixture
def booster(monkeypatch):
    model = SimpleNamespace(
        num_feature=lambda: 144,
        num_trees=lambda: 64,
        predict=lambda x: np.full(len(x), 1.0),
    )
    monkeypatch.setitem(sys.modules, "lightgbm", SimpleNamespace(Booster=lambda **kw: model))
    return model


@pytest.fixture
def saved_tree(tmp_path, booster):
    root, fold = tmp_path / "models", prepared()
    ref = s.save_model(root, fold, identity(), "synthetic booster", np.ones(3), HASH, None)
    return root, fold, ref


def rehash_config(root, ref, cfg):
    raw = h30.encode(cfg)
    (root / ref["config_file"]).write_bytes(raw)
    ref["config_sha256"] = h30.digest(raw)


def rewrite_arrays(root, ref, arrays):
    path = root / ref["scalers_file"]
    with path.open("wb") as handle:
        np.savez(handle, **arrays)
    cfg = json.loads((root / ref["config_file"]).read_bytes())
    for key in ("scalers", "weights"):
        if ref[key + "_file"] == path.name:
            cfg[key + "_sha256"] = ref[key + "_sha256"] = h30.digest(path.read_bytes())
    rehash_config(root, ref, cfg)


def test_tree_numeric_roundtrip_threshold_and_no_overwrite(saved_tree, booster):
    root, fold, ref = saved_tree
    model, arrays = s.load_model(root, ref, HASH, None)
    assert model is booster and set(arrays) == s.SCALERS
    s.check_scalers(arrays, fold)
    np.testing.assert_array_equal(model.predict(fold.eval_x.reshape(3, -1)), np.ones(3))
    with pytest.raises(FileExistsError):
        s.save_model(root, fold, identity(), "replacement", np.ones(3), HASH, None)


@pytest.mark.parametrize("field", ("config_file", "weights_file", "scalers_file"))
def test_model_file_hash_tampering_is_rejected(saved_tree, field):
    root, _, ref = saved_tree
    path = root / ref[field]
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.load_model(root, ref, HASH, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "wrong"),
        ("contract_sha256", OTHER),
        ("private_development_only", False),
        ("symbol", "QQQ"),
        ("fold", 2),
        ("horizon_minutes", 60),
        ("context", 12),
        ("seed", 103),
        ("candidate", "lstm"),
        ("weights_file", "wrong.txt"),
        ("weights_sha256", OTHER),
        ("scalers_file", "wrong.npz"),
        ("scalers_sha256", OTHER),
    ],
)
def test_rehashed_config_identity_and_binding_tampering_is_rejected(saved_tree, field, value):
    root, _, ref = saved_tree
    cfg = json.loads((root / ref["config_file"]).read_bytes())
    cfg[field] = value
    rehash_config(root, ref, cfg)
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.load_model(root, ref, HASH, None)


@pytest.mark.parametrize("case", ("missing", "dtype", "shape", "nan", "zero", "negative", "extra"))
def test_scaler_schema_and_values_rejected_even_when_hashes_match(saved_tree, case):
    root, _, ref = saved_tree
    arrays = s.read_arrays(root / ref["scalers_file"])
    if case == "missing":
        del arrays["target_scale"]
    elif case == "dtype":
        arrays["channel_mean"] = arrays["channel_mean"].astype(np.float32)
    elif case == "shape":
        arrays["target_mean"] = np.zeros(2)
    elif case == "extra":
        arrays["unrecognized"] = np.zeros(1)
    else:
        arrays["target_scale"][0] = {"nan": np.nan, "zero": 0, "negative": -1}[case]
    rewrite_arrays(root, ref, arrays)
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.load_model(root, ref, HASH, None)


def test_rehashed_positive_scaler_tampering_must_match_normalizer_digest(saved_tree):
    root, _, ref = saved_tree
    arrays = s.read_arrays(root / ref["scalers_file"])
    arrays["channel_mean"][0] += 100
    rewrite_arrays(root, ref, arrays)
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.load_model(root, ref, HASH, None)


def test_rehashed_normalizer_config_tampering_must_be_rejected(saved_tree):
    root, _, ref = saved_tree
    cfg = json.loads((root / ref["config_file"]).read_bytes())
    cfg["normalizer_sha256"] = OTHER
    rehash_config(root, ref, cfg)
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.load_model(root, ref, HASH, None)


@pytest.mark.parametrize("field", ("cohort_sha256", "normalizer_sha256"))
def test_verify_models_binds_config_to_result_fold(tmp_path, monkeypatch, booster, field):
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    root = tmp_path / "models"
    result = {"phase": "cpu", "models": [], "folds": []}
    for ident in s.identities("cpu", fitted=True):
        fold = replace(prepared(), symbol=ident["symbol"], fold=ident["fold"])
        result["models"].append(
            s.save_model(root, fold, ident, "synthetic booster", np.ones(3), HASH, None)
        )
        result["folds"].append(
            {**{k: ident[k] for k in ("symbol", "fold", "horizon_minutes")}, **fold.facts}
        )
    s.verify_models(root, result, HASH)
    result["folds"][0][field] = OTHER
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.verify_models(root, result, HASH)


def test_save_model_rejects_decision_flip_inside_allclose_tolerance(tmp_path, booster):
    fold = prepared()
    # 1.0 * 4 + 2 == 6; a tiny normalized change crosses the strict decision threshold.
    assert np.allclose(np.ones(3), np.full(3, 1 + 1e-7), rtol=1e-5, atol=1e-6)
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.save_model(
            tmp_path / "models", fold, identity(), "booster", np.full(3, 1 + 1e-7), HASH, None
        )


@pytest.mark.parametrize("case", ("object", "oversize"))
def test_numeric_reader_rejects_pickle_or_oversized_archives(tmp_path, case):
    path = tmp_path / "weights.npz"
    if case == "object":
        np.savez(path, unsafe=np.array([{"not": "numeric"}], dtype=object))
        with pytest.raises(ValueError, match="Object arrays"):
            s.read_arrays(path)
    else:
        path.write_bytes(b"0" * (2 * 1024**2))
        with pytest.raises(h30.StudyFailure, match="model_reload"):
            s.read_arrays(path)


@pytest.fixture
def parent_archive(tmp_path, monkeypatch):
    root, fold = tmp_path / sessions.NAME, prepared()
    directory = root / "models"
    directory.mkdir(parents=True)
    arrays = {
        key: np.zeros(shape, dtype=np.float32)
        for key, shape in h30.STATE_SHAPES.items()
        if key.startswith("state.")
    }
    arrays.update(s.scaler_arrays(fold))
    path = directory / "SPY-1-30-36-101.npz"
    np.savez(path, **arrays)
    ident = {key: value for key, value in identity().items() if key != "candidate"}
    cfg = {
        **ident,
        "name": sessions.NAME,
        "contract_sha256": s.PARENT_CONTRACT,
        "cohort_sha256": fold.facts["cohort_sha256"],
        "architecture": "lstm",
        "epochs": 8,
        "hidden_size": 16,
        "feature_count": 4,
        "weights_file": path.name,
        "weights_sha256": h30.digest(path.read_bytes()),
        "private_development_only": True,
    }
    ref = {
        **ident,
        "config_file": "SPY-1-30-36-101.json",
        "weights_file": path.name,
        "weights_sha256": cfg["weights_sha256"],
    }
    rehash_config(directory, ref, cfg)
    restored = object()
    calls = []

    def restore(torch, name, values):
        assert name == "lstm"
        h30.validate_model_arrays(values)
        return restored

    def predict(torch, model, values, device="cpu"):
        assert model is restored and device == "cpu"
        assert values is fold.eval_x
        calls.append("prediction")
        return np.full(len(values), 0.25)

    monkeypatch.setattr(s, "restore_sequence", restore)
    monkeypatch.setattr(s, "sequence_predict", predict)
    return root, fold, ref, {"cuda": {"models": [ref]}}, calls


def test_parent_reload_uses_retained_models_directory_and_normalized_input(parent_archive):
    root, fold, _, prior, calls = parent_archive
    prediction = s.parent_prediction(None, fold, 101, root, prior)
    np.testing.assert_array_equal(prediction, np.full(3, 0.25))
    assert calls == ["prediction"]


@pytest.mark.parametrize("case", ("config_hash", "weights_hash", "cohort", "contract", "scalers"))
def test_parent_reload_rejects_hash_cohort_or_scaler_mismatch(parent_archive, case):
    root, fold, ref, prior, calls = parent_archive
    directory = root / "models"
    if case.endswith("hash"):
        key = "config_file" if case == "config_hash" else "weights_file"
        path = directory / ref[key]
        path.write_bytes(path.read_bytes() + b"tampered")
    elif case == "scalers":
        fold.channel_mean[0] += 100
    else:
        cfg = json.loads((directory / ref["config_file"]).read_bytes())
        cfg["cohort_sha256" if case == "cohort" else "contract_sha256"] = OTHER
        rehash_config(directory, ref, cfg)
    with pytest.raises(h30.StudyFailure, match="parent_control_mismatch"):
        s.parent_prediction(None, fold, 101, root, prior)
    assert not calls


@pytest.fixture
def matrix(monkeypatch, source):  # noqa: F811 - imported pytest fixture
    schedules, all_bars = source
    schedules = schedules[:40]
    bars = tuple(b for b in all_bars if b.start_ts < schedules[-1][1])
    streams = tuple(
        (symbol, tuple(replace(bar, symbol=symbol) for bar in bars)) for symbol in h30.SYMBOLS
    )
    monkeypatch.setattr(sessions, "HORIZONS", (30,))
    monkeypatch.setattr(sessions, "regular_sessions", lambda _bars: schedules)

    def predictions(fold, context=36):
        assert context == 36 or context == 12
        return np.full(len(fold.evaluation), 0.25)

    def trainer(torch, fold, context, seed, deadline):
        return (
            predictions(fold, context),
            {},
            dict(
                epochs=8,
                updates=8 * ((len(fold.train_y) + 127) // 128),
                train_rows=len(fold.train_y),
                initial_train_mse=1.0,
                final_train_mse=0.5,
                train_mean_baseline_mse=1.0,
                parameter_count=3361,
            ),
        )

    kwargs = dict(schedules=schedules, replay=fast_payoff, ridge=predictions)
    cpu, _ = sessions.compare(streams, "cpu", None, time.monotonic() + 60, **kwargs)
    cuda, _ = sessions.compare(
        streams, "cuda", None, time.monotonic() + 60, reference=cpu, trainer=trainer, **kwargs
    )
    prior = {"cpu": cpu, "cuda": cuda}
    actual_score = s.score
    monkeypatch.setattr(s, "score", lambda *args: actual_score(*args, replay=fast_payoff))
    monkeypatch.setattr(h30, "ridge_predict", predictions)
    monkeypatch.setattr(s, "parent_prediction", lambda torch, fold, *args: predictions(fold))
    monkeypatch.setattr(s.models, "fit_lightgbm", lambda f: trainer(None, f, 36, 101, 0))
    monkeypatch.setattr(
        s.models,
        "fit_sequence",
        lambda torch, f, name, seed, deadline: trainer(torch, f, 36, seed, deadline),
    )
    monkeypatch.setattr(s, "save_model", lambda root, f, ident, *args: dict(ident))
    return SimpleNamespace(streams=streams, prior=prior, schedules=schedules, score=actual_score)


def run_comparison(matrix, phase="cpu", reference=None):
    return s.compare(
        matrix.streams,
        phase,
        None,
        time.monotonic() + 60,
        None,
        None,
        HASH,
        None,
        matrix.prior,
        reference,
    )


def test_exact_cell_and_fit_matrix_matches_independent_parent_controls(matrix):
    cpu = run_comparison(matrix)
    s.validate_result(cpu, "cpu", HASH)
    cuda = run_comparison(matrix, "cuda", cpu)
    s.validate_result(cuda, "cuda", HASH)
    assert len(cpu["cells"]) == 96 and len(cuda["cells"]) == 48
    assert len(cpu["fits"]) == len(cpu["models"]) == 4
    assert len(cuda["fits"]) == len(cuda["models"]) == 16
    assert cpu["parent_controls_reproduced"] == 84
    assert cuda["parent_controls_reproduced"] == 0 and cuda["folds"] == cpu["folds"]
    assert set(c["context"] for c in cpu["cells"] if c["candidate"] == "ridge") == {36}
    assert all(c["horizon_minutes"] == 30 for c in cpu["cells"] + cuda["cells"])


@pytest.mark.parametrize(
    "case",
    (
        "missing_cell",
        "duplicate_cell",
        "wrong_cost",
        "missing_fit",
        "wrong_model",
        "accounting",
        "parity_flag",
    ),
)
def test_result_matrix_and_accounting_mutations_rejected(matrix, case):
    result = run_comparison(matrix)
    if case == "missing_cell":
        result["cells"].pop()
    elif case == "duplicate_cell":
        result["cells"][-1] = copy.deepcopy(result["cells"][0])
    elif case == "wrong_cost":
        result["cells"][0]["cost_bps_per_side"] = 7
    elif case == "missing_fit":
        result["fits"].pop()
    elif case == "wrong_model":
        result["models"][0]["seed"] = 103
    elif case == "accounting":
        result["cells"][0]["net_dollars"] = "123"
    else:
        result["cells"][0]["local_paper_replay_parity"] = False
    with pytest.raises(h30.StudyFailure):
        s.validate_result(result, "cpu", HASH)


@pytest.mark.parametrize("case", ("cohort", "normalizer", "censor", "control", "missing"))
def test_parent_control_parity_mismatches_rejected(matrix, case):
    result = run_comparison(matrix)
    if case in ("cohort", "normalizer"):
        result["folds"][0][case + "_sha256"] = OTHER
    elif case == "censor":
        result["folds"][0]["evaluation_outcomes"]["future_missing"] += 1
    elif case == "missing":
        result["cells"] = [c for c in result["cells"] if c["candidate"] != "always_flat"]
    else:
        result["cells"][0]["selected_decisions"] += 1
    with pytest.raises(h30.StudyFailure, match="parent_control_mismatch"):
        s.parent_parity(result, matrix.prior)


def test_duplicate_fold_facts_cannot_satisfy_result_or_parent_parity(matrix):
    result = run_comparison(matrix)
    result["folds"][-1] = copy.deepcopy(result["folds"][0])
    with pytest.raises(h30.StudyFailure):
        s.validate_result(result, "cpu", HASH)
        s.parent_parity(result, matrix.prior)


def test_cpu_cuda_normalizer_mismatch_rejected(matrix):
    cpu = run_comparison(matrix)
    cpu["folds"][0]["normalizer_sha256"] = OTHER
    with pytest.raises(h30.StudyFailure, match="cpu_cuda_cohort_changed"):
        run_comparison(matrix, "cuda", cpu)


def test_future_censoring_happens_after_all_model_decisions(matrix, monkeypatch):
    first_eval = sessions.plans(matrix.schedules, 30)[0][1][0]
    outcomes, parent_prediction, fit = sessions.outcomes, s.parent_prediction, s.models.fit_lightgbm
    calls = []

    def train(fold):
        calls.append("lightgbm")
        return fit(fold)

    def parent(torch, fold, seed, *args):
        calls.append(seed)
        return parent_prediction(torch, fold, seed, *args)

    def unavailable(index, observations, horizon):
        if observations and observations[0].at >= first_eval:
            assert calls == ["lightgbm", 101, 103]
            return (None,) * len(observations), dict(
                eligible=len(observations), observed=0, future_missing=len(observations)
            )
        return outcomes(index, observations, horizon)

    monkeypatch.setattr(s.models, "fit_lightgbm", train)
    monkeypatch.setattr(s, "parent_prediction", parent)
    monkeypatch.setattr(sessions, "outcomes", unavailable)
    with pytest.raises(sessions.OutcomeSupportShortfall) as caught:
        run_comparison(matrix)
    assert caught.value.support == {"eligible": 60, "observed": 0, "censored": 60, "blocks": 0}


def test_selected_missing_outcome_remains_a_decision_without_pnl(matrix):
    symbol, bars = matrix.streams[0]
    index = {bar.start_ts: bar for bar in bars}
    plan = sessions.plans(matrix.schedules, 30)[0]
    fold = sessions.prepare_fold(symbol, 1, index, plan, 30)
    selected = np.zeros(len(fold.evaluation), dtype=bool)
    selected[-1] = True
    snapshots = (fold.eval_x.copy(), fold.train_x.copy(), fold.train_y.copy())
    # The last scheduled exit is future-only to every scored decision in this fold.
    del index[fold.evaluation[-1].at + h30.HOLD]
    calls = []

    def replay(obs, outcome, cost, emergency):
        calls.append((obs.at, cost))
        return fast_payoff(obs, outcome, cost, emergency)

    cells = matrix.score(
        fold, [(identity(), selected)], index, None, time.monotonic() + 30, replay=replay
    )
    assert len(cells) == 3 and len(calls) == 59 * 3
    assert all(
        c["eligible_decisions"] == 60
        and c["selected_decisions"] == 1
        and c["future_censored"] == 1
        and c["selected_censored"] == 1
        and c["roundtrips"] == 0
        and Decimal(c["net_dollars"]) == 0
        for c in cells
    )
    for actual, expected in zip((fold.eval_x, fold.train_x, fold.train_y), snapshots, strict=True):
        np.testing.assert_array_equal(actual, expected)


def test_evaluation_changes_do_not_fit_normalizers(matrix):
    symbol, bars = matrix.streams[0]
    index = {bar.start_ts: bar for bar in bars}
    plan = sessions.plans(matrix.schedules, 30)[0]
    fold = sessions.prepare_fold(symbol, 1, index, plan, 30)
    changed = {
        at: replace(bar, volume=bar.volume * 1000) if at >= plan[2] else bar
        for at, bar in index.items()
    }
    other = sessions.prepare_fold(symbol, 1, changed, plan, 30)
    for name in ("train_x", "train_y", "channel_mean", "channel_scale"):
        np.testing.assert_array_equal(getattr(fold, name), getattr(other, name))
    assert fold.facts["normalizer_sha256"] == other.facts["normalizer_sha256"]
    assert fold.y_mean == other.y_mean and fold.y_scale == other.y_scale
    assert not np.array_equal(fold.eval_x, other.eval_x)


@pytest.fixture
def torch_cpu():
    torch = pytest.importorskip("torch", reason="optional local synthetic reload check")
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield torch
    torch.set_num_threads(previous)


@pytest.mark.parametrize("architecture", s.models.ARCHITECTURES)
def test_trained_sequence_state_numeric_save_and_reload(
    tmp_path, monkeypatch, torch_cpu, architecture
):
    torch = torch_cpu
    torch.manual_seed(101)
    fold = prepared()
    model = s.models.build_sequence(torch, architecture)
    before = {k: value.detach().clone() for k, value in model.state_dict().items()}
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    model.train()
    loss = torch.nn.functional.mse_loss(
        model(torch.tensor(fold.train_x)).flatten(), torch.tensor(fold.train_y)
    )
    loss.backward()
    optimizer.step()
    state = {"state." + k: value.detach().numpy().copy() for k, value in model.state_dict().items()}
    assert any(not torch.equal(before[k], value) for k, value in model.state_dict().items())
    actual_predict = s.sequence_predict
    prediction = actual_predict(torch, model, fold.eval_x)
    devices = []

    def cpu_reload(runtime, model, values, device="cpu"):
        devices.append(device)
        return actual_predict(runtime, model, values, "cpu")

    monkeypatch.setattr(s, "sequence_predict", cpu_reload)
    root = tmp_path / "models"
    ref = s.save_model(root, fold, identity(architecture), state, prediction, HASH, torch)
    assert devices == ["cuda"]
    restored, arrays = s.load_model(root, ref, HASH, torch)
    s.check_scalers(arrays, fold)
    np.testing.assert_allclose(
        actual_predict(torch, restored, fold.eval_x), prediction, rtol=1e-5, atol=1e-6
    )
    for key, value in state.items():
        np.testing.assert_array_equal(arrays[key], value)
    assert ref["weights_file"] == ref["scalers_file"]
    arrays["state.head.weight"] = arrays["state.head.weight"].reshape(-1)
    rewrite_arrays(root, ref, arrays)
    with pytest.raises(h30.StudyFailure, match="model_reload"):
        s.load_model(root, ref, HASH, torch)

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from thericher_v2.research import five_session_tree as tree
from thericher_v2.research.five_session_cohort import FiveSessionFrame

CohortError = tree.TreeError

IDENTITIES = tuple(f"S{i:04d}/NAS" for i in range(512))
IDENTITY = hashlib.sha256(json.dumps(list(IDENTITIES), separators=(",", ":")).encode()).hexdigest()
RAW = b"synthetic-owned-hash-fixture-not-a-pickle"
MEAN = np.arange(5, dtype=np.float64)
SCALE = np.arange(1, 6, dtype=np.float64)


def frame(**changes):
    opening = datetime(2026, 7, 28, 13, 30, tzinfo=UTC)
    opens = tuple(opening + timedelta(days=i) for i in range(5))
    values = dict(
        index=21,
        identities=IDENTITIES,
        decision=opening - timedelta(hours=1),
        prior_closes=tuple(opening - timedelta(days=i) for i in range(21, 0, -1)),
        session_opens=opens,
        session_closes=tuple(at + timedelta(hours=6, minutes=30) for at in opens),
        tokens=np.arange(512 * 100, dtype=np.float64).reshape(512, 20, 5) / 1000,
        eligible=np.ones(512, dtype=bool),
        momentum=np.full(512, 0.1),
        volatility=np.linspace(0.1, 0.8, 512),
        feature_stamp="1" * 64,
    )
    return FiveSessionFrame(**(values | changes))


def metadata(raw=RAW):
    return {
        "kind": "self_generated_frozen_HGBR_and_scaler_export_v1",
        "format": "private_own_pickle_protocol5",
        "artifact": "teacher.pkl",
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "model_class": "sklearn.ensemble.HistGradientBoostingRegressor",
        "scaler_mean_shape": [5],
        "scaler_scale_shape": [5],
        "scaler_dtype": "float64",
        "complete_training_dates": 675,
        "training_entries": [20, 695],
        "training_last_exit_index": 699,
        "training_last_exit_ts": tree.TRAINING_CUTOFF.isoformat(),
        "identity_sha256": "sha256:" + IDENTITY,
        "sklearn_version": "1.9.1",
        "numpy_version": "2.5.1",
        "seed": 101,
        "availability": "assumed_not_observed",
        "promotion_eligible": False,
        "broker_input": False,
        "roundtrip_verified": True,
        "prediction_bit_equal": True,
        "source_pins": {"/model/ranking.py": "sha256:" + tree.FEATURE_SHA256},
        "model_parameters": tree.MODEL_PARAMETERS
        | {"implementation": "sklearn.ensemble.HistGradientBoostingRegressor"},
    }


@pytest.fixture
def owned_fixture(tmp_path, monkeypatch):
    calls = []
    model, meta = tmp_path / "teacher.pkl", tmp_path / "teacher-metadata.json"
    model.write_bytes(RAW)
    monkeypatch.setattr(tree, "TEACHER_SHA256", hashlib.sha256(RAW).hexdigest())
    monkeypatch.setattr(tree, "IDENTITY_SHA256", IDENTITY)
    monkeypatch.setattr(np, "__version__", "2.5.1")
    monkeypatch.setattr(tree, "version", lambda name: "1.9.1")

    def bind(doc):
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        meta.write_bytes(raw)
        monkeypatch.setattr(tree, "METADATA_SHA256", hashlib.sha256(raw).hexdigest())

    def deserialize(raw):
        assert raw == RAW  # No arbitrary or actual pickle is deserialized on the host.
        calls.append("deserialize")

        def predict(x):
            calls.append(x.copy())
            return np.ones(len(x))

        return predict, MEAN.copy(), SCALE.copy()

    bind(metadata())
    monkeypatch.setattr(tree, "_deserialize", deserialize)
    return model, meta, calls, bind


def test_lazy_module_has_no_default_model_or_heavy_imports():
    code = (
        "import sys; from thericher_v2.research import five_session_tree as t; "
        "assert not any(k=='pickle' or k.startswith(('numpy','sklearn','torch',"
        "'thericher_v2.execution','thericher_v2.broker')) for k in sys.modules); "
        "assert 'fit' not in vars(t._TreeInference); "
        "assert list(__import__('inspect').signature(t.load_goal80_teacher).parameters)"
        "==['model_path','metadata_path']"
    )
    result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert tree.TEACHER_SHA256 == "ca6b36d1686365fe4f6680589bb0927e7e2e143e1b69a7ab13dd88339d2ae5a0"
    assert (
        tree.METADATA_SHA256 == "2ce286eeec36093f412eb9b27966a6ab6869c9856cc24f7b5b06adc87b3eeb35"
    )


@pytest.mark.parametrize("which", [0, 1])
def test_wrong_bytes_never_reach_deserialization(owned_fixture, which):
    model, meta, calls, _ = owned_fixture
    (model, meta)[which].write_bytes(b"wrong")
    with pytest.raises(CohortError, match="teacher_hash_binding"):
        tree.load_goal80_teacher(model, meta)
    assert not calls


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("complete_training_dates", 674),
        ("training_entries", [20, 795]),
        ("training_last_exit_index", 799),
        ("training_last_exit_ts", "2026-03-04T21:00:00+00:00"),
        ("identity_sha256", "sha256:" + "0" * 64),
        ("availability", "observed"),
        ("model_parameters", {}),
        ("source_pins", {}),
    ],
)
def test_metadata_schema_recipe_cutoff_before_deserialization(owned_fixture, key, bad):
    model, meta, calls, bind = owned_fixture
    bind(metadata() | {key: bad})
    with pytest.raises(CohortError, match="teacher_metadata_binding|teacher_recipe_binding"):
        tree.load_goal80_teacher(model, meta)
    assert not calls


@pytest.mark.parametrize("library", ["numpy", "sklearn"])
def test_wrong_runtime_before_deserialization(owned_fixture, monkeypatch, library):
    model, meta, calls, _ = owned_fixture
    if library == "numpy":
        monkeypatch.setattr(np, "__version__", "2.0.0")
    else:
        monkeypatch.setattr(tree, "version", lambda name: "1.8.0")
    with pytest.raises(CohortError, match="tree_runtime_binding"):
        tree.load_goal80_teacher(model, meta)
    assert not calls


def test_duplicate_metadata_rejected_before_runtime_or_deserialization(owned_fixture, monkeypatch):
    model, meta, calls, _ = owned_fixture
    raw = b'{"seed":101,"seed":101}'
    meta.write_bytes(raw)
    monkeypatch.setattr(tree, "METADATA_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(CohortError, match="teacher_duplicate_metadata"):
        tree.load_goal80_teacher(model, meta)
    assert not calls


def test_exact_scaler_eligible_geometry_ties_and_immutable_decision(owned_fixture):
    model, meta, calls, _ = owned_fixture
    teacher = tree.load_goal80_teacher(model, meta)
    mask = np.ones(512, dtype=bool)
    mask[[0, 8, 511]] = False
    current = frame(eligible=mask)
    decision = teacher(current)
    assert decision.status == "ready"
    assert decision.original_slots == tuple(i for i in range(12) if i not in (0, 8))
    np.testing.assert_array_equal(
        calls[1], ((current.tokens - MEAN) / SCALE)[mask].reshape(-1, 100)
    )
    assert calls[1].shape == (509, 100) and len(calls) == 2
    assert not decision.scores[~mask].any() and not decision.weights[~mask].any()
    assert decision.frame_stamp == current.stamp
    assert decision.availability == "assumed_not_observed"
    assert not hasattr(teacher, "fit") and not hasattr(teacher, "model")
    for array in (decision.scores, decision.weights, teacher._mean, teacher._scale):
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        decision.reason = "changed"


@pytest.mark.parametrize("mask", [np.zeros(512, dtype=bool), np.arange(512) < 128])
def test_unsupported_zero_scoped_allocation_without_prediction(owned_fixture, mask):
    model, meta, calls, _ = owned_fixture
    result = tree.load_goal80_teacher(model, meta)(frame(eligible=mask))
    assert result.status == "input_unavailable" and result.reason == "prior_causal_support"
    assert not result.weights.any() and not result.scores.any() and result.original_slots == ()
    assert calls == ["deserialize"]


def test_identity_and_training_cutoff_not_local_calendar_index(owned_fixture):
    model, meta, _, _ = owned_fixture
    teacher = tree.load_goal80_teacher(model, meta)
    wrong = replace(frame(), identities=IDENTITIES[::-1])
    with pytest.raises(CohortError, match="tree_identity_binding"):
        teacher(wrong)
    old = frame()
    shift = timedelta(days=(old.decision.date() - tree.TRAINING_CUTOFF.date()).days)
    stale = replace(
        old,
        decision=old.decision - shift,
        prior_closes=tuple(t - shift for t in old.prior_closes),
        session_opens=tuple(t - shift for t in old.session_opens),
        session_closes=tuple(t - shift for t in old.session_closes),
    )
    with pytest.raises(CohortError, match="tree_causal_feature_binding"):
        teacher(stale)
    assert teacher(frame()).status == "ready"  # Local later index21 is legitimate.


@pytest.mark.parametrize(
    "bad", [np.full(5, 0.0), np.full(5, np.nan), np.ones(4), np.ones(5, dtype=int)]
)
def test_scaler_bad_values_shapes_and_dtype(owned_fixture, monkeypatch, bad):
    model, meta, _, _ = owned_fixture
    monkeypatch.setattr(tree, "_deserialize", lambda raw: (lambda x: np.zeros(len(x)), MEAN, bad))
    with pytest.raises(CohortError, match="tree_scaler_binding"):
        tree.load_goal80_teacher(model, meta)


@pytest.mark.parametrize("bad", [np.zeros((512, 1)), np.full(512, np.nan), np.zeros(513)])
def test_prediction_shape_and_finite_scores(owned_fixture, monkeypatch, bad):
    model, meta, _, _ = owned_fixture
    monkeypatch.setattr(tree, "_deserialize", lambda raw: (lambda x: bad, MEAN, SCALE))
    teacher = tree.load_goal80_teacher(model, meta)
    with pytest.raises(CohortError, match="tree_scores_binding"):
        teacher(frame())


@pytest.mark.parametrize("sigma", [0.1, 0.8, 4.0])
def test_frozen_goal80_seal_parity_caps_and_slot_veto(owned_fixture, sigma):
    model, meta, _, _ = owned_fixture
    momentum = np.full(512, 0.10)
    momentum[[0, 5]] = 0
    current = frame(momentum=momentum, volatility=np.full(512, sigma))
    result = tree.load_goal80_teacher(model, meta)(current)
    # Exact frozen Goal80 seal_policies tree branch, independent of adapter code.
    selected = sorted(
        np.flatnonzero(current.eligible).tolist(), key=lambda i: (-result.scores[i], i)
    )[:10]
    vol = current.volatility[selected]
    original = np.minimum(0.10, 0.50 * (1 / vol) / (1 / vol).sum())
    original *= min(1.0, 0.08 / float(np.dot(original, vol)))
    proxy = np.expm1(0.25 * np.log1p(current.momentum[selected]))
    expected = np.zeros(512)
    expected[selected] = original * (proxy > 0.003)
    np.testing.assert_array_equal(result.weights, expected)
    assert result.original_slots == tuple(range(10))
    assert result.weights[0] == result.weights[5] == result.weights[10] == 0
    assert result.weights.max() <= 0.10 and result.weights.sum() <= 0.50
    assert np.dot(result.weights, current.volatility) <= 0.08 + 1e-12


def test_descending_scores_ties_name_cap_and_no_redistribution(owned_fixture, monkeypatch):
    model, meta, _, _ = owned_fixture
    scores = np.arange(512, dtype=float)
    scores[[2, 3]] = 1000
    monkeypatch.setattr(tree, "_deserialize", lambda raw: (lambda x: scores, MEAN, SCALE))
    sigma = np.full(512, 0.8)
    sigma[2] = 0.1
    momentum = np.full(512, 0.1)
    momentum[3] = 0
    current = frame(volatility=sigma, momentum=momentum)
    decision = tree.load_goal80_teacher(model, meta)(current)
    assert decision.original_slots == (2, 3, 511, 510, 509, 508, 507, 506, 505, 504)
    inverse = 1 / sigma[list(decision.original_slots)]
    original = np.minimum(0.10, 0.50 * inverse / inverse.sum())
    original *= min(1.0, 0.08 / float(np.dot(original, sigma[list(decision.original_slots)])))
    assert decision.weights[2] == original[0]
    assert decision.weights[3] == 0 and decision.weights[503] == 0
    np.testing.assert_array_equal(decision.weights[list(decision.original_slots)[2:]], original[2:])


@pytest.mark.parametrize("kind", ["shape", "mask", "nan", "momentum", "support", "stamp"])
def test_defensive_typed_input_geometry_mask_finite_and_stamp(owned_fixture, kind):
    model, meta, _, _ = owned_fixture
    teacher = tree.load_goal80_teacher(model, meta)
    current = frame()
    key, value = {
        "shape": ("tokens", np.zeros((512, 19, 5))),
        "mask": ("eligible", np.ones(512, dtype=int)),
        "nan": ("tokens", np.full((512, 20, 5), np.nan)),
        "momentum": ("momentum", np.full(512, -1.0)),
        "support": ("supported", False),
        "stamp": ("feature_stamp", "not-canonical"),
    }[kind]
    object.__setattr__(current, key, value)
    with pytest.raises(CohortError):
        teacher(current)


def test_only_loader_calls_private_deserializer_no_fit_or_torch_source():
    parsed = ast.parse(inspect.getsource(tree))
    callers = [
        node.name
        for node in parsed.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_deserialize"
            for n in ast.walk(node)
        )
    ]
    assert callers == ["load_goal80_teacher"]
    assert ".fit(" not in inspect.getsource(tree) and "import torch" not in inspect.getsource(tree)

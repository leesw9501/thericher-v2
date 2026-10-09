"""Manufactured numeric bytes and nominal clocks only; no actual weights or data."""

import hashlib
import io
import zipfile
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_relative_features as feature
from thericher_v2.research import kis_stock_ridge_inference as ridge

KEYS = tuple(f"opaque-{i:03}" for i in range(128))
DATES = tuple(date(2030, 1, 1) + timedelta(days=i) for i in range(113))
OPEN = tuple(
    datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=13, minutes=30)
    for day in DATES
)
CLOSE = tuple(
    datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=20) for day in DATES
)
PLAN = feature.FeaturePlan(DATES, KEYS, OPEN, CLOSE)


def payload():
    return dict(
        scaler_mean=np.asarray([0.1, -0.2, 0.3, 0.4], dtype=np.float64),
        scaler_scale=np.asarray([1.0, 2.0, 0.5, 3.0], dtype=np.float64),
        coefficients=np.asarray([0.3, -0.6, 0.9, 0.2], dtype=np.float64),
        intercept=np.asarray(0.07, dtype=np.float64),
        alpha=np.asarray(1.0, dtype=np.float64),
        target_open_cutoff=np.asarray(799, dtype=np.int64),
        training_row_count=np.asarray(40, dtype=np.int64),
        training_date_count=np.asarray(4, dtype=np.int64),
        seed=np.asarray(101, dtype=np.int64),
    )


def npz(values=None, *, compressed=False):
    stream = io.BytesIO()
    (np.savez_compressed if compressed else np.savez)(
        stream, **(payload() if values is None else values)
    )
    return stream.getvalue()


def pin(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def decode(raw=None, **kwargs):
    raw = npz() if raw is None else raw
    return ridge.decode_ridge_npz(
        raw,
        expected_sha256=kwargs.pop("expected_sha256", pin(raw)),
        expected_training_rows=kwargs.pop("expected_training_rows", 40),
        expected_training_dates=kwargs.pop("expected_training_dates", 4),
        **kwargs,
    )


def seal(entry=112, eligible=KEYS):
    rows = tuple(
        feature.StockRow(key, f"SYN{i:03}", "SYN", (float(i) / 100, -0.2, 0.4, 0.02))
        for i, key in enumerate(eligible)
    )
    return feature.FeatureSeal(PLAN, entry, rows, tuple(key for key in KEYS if key not in eligible))


def snapshot(features):
    return core.EligibilitySnapshot(
        features.entry_index,
        DATES[features.entry_index - 1],
        features.entry_session,
        tuple(
            core.FeatureRow(row.key, ((0.0,) * 20,) * 2, (0.0,) * 3, 0.0) for row in features.rows
        ),
        features.unavailable_keys,
        features.decision_at,
        features.entry_open_at,
        CLOSE[features.entry_index],
    )


def clocks():
    return dict(
        cache_observed_at=CLOSE[111] + timedelta(minutes=10),
        as_of=OPEN[112] - timedelta(minutes=10),
        inference_started_at=OPEN[112] - timedelta(minutes=9),
        inference_completed_at=OPEN[112] - timedelta(minutes=8),
    )


def prospective(state=None, features=None, snap=None, prediction=None, **kwargs):
    state = decode() if state is None else state
    features = seal() if features is None else features
    prediction = ridge.predict_feature_seal(state, features) if prediction is None else prediction
    return ridge.seal_prospective_ridge(
        state,
        prediction,
        snapshot(features) if snap is None else snap,
        expected_keys=kwargs.pop("expected_keys", KEYS),
        **(clocks() | kwargs),
    )


def rewrite(raw, change, *, compression=zipfile.ZIP_STORED, extra=None):
    result = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw)) as original,
        zipfile.ZipFile(result, "w", compression=compression) as output,
    ):
        for name in original.namelist():
            output.writestr(name, change(name, original.read(name)))
        if extra is not None:
            output.writestr(*extra)
    return result.getvalue()


def test_exact_schema_and_float64_prediction_original_formula():
    values, state = payload(), decode()
    x = np.asarray([[0.12, 0.9, 1.2, 0.33], [0.2, -0.7, 2.0, 0.18]], dtype=np.float64)
    expected = ((x.astype(np.float64) - values["scaler_mean"]) / values["scaler_scale"]) @ values[
        "coefficients"
    ] + values["intercept"]
    actual = ridge.predict_ridge(state, x)
    assert np.array_equal(actual, expected) and actual.dtype == np.float64
    assert (state.target_open_cutoff, state.seed, state.alpha) == (799, 101, 1.0)
    assert (state.training_row_count, state.training_date_count) == (40, 4)


def test_state_copy_is_frozen_and_cannot_reenable_writeable_buffers():
    state = decode()
    for array in (state.scaler_mean, state.scaler_scale, state.coefficients):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array[0] = 999.0
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        state.intercept = 0.0
    original = payload()["coefficients"]
    copied = replace(state, coefficients=original)
    original[0] = 999.0
    assert copied.coefficients[0] == state.coefficients[0]


@pytest.mark.parametrize("wrong", ["", "a" * 64, "sha256:" + "f" * 64, "sha256:" + "A" * 64, None])
def test_explicit_trusted_hash_required_and_checked_before_numpy(monkeypatch, wrong):
    monkeypatch.setattr(np, "load", lambda *a, **k: pytest.fail("numpy before hash verification"))
    with pytest.raises(ValueError):
        decode(expected_sha256=wrong)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "missing",
        "wrong_shape",
        "f32",
        "complex",
        "object",
        "bool",
        "big_endian",
        "nan",
        "inf",
        "scale0",
        "scale_negative",
        "cutoff",
        "seed",
        "alpha",
        "rows",
        "dates",
        "int32",
    ],
)
def test_numeric_schema_rejects_bad_state_and_metadata(mutation):
    values = payload()
    if mutation == "extra":
        values["code"] = np.asarray(1)
    elif mutation == "missing":
        del values["seed"]
    elif mutation == "wrong_shape":
        values["coefficients"] = np.zeros((1, 4))
    elif mutation in {"f32", "complex", "object", "bool", "big_endian"}:
        dtype = {
            "f32": np.float32,
            "complex": np.complex128,
            "object": object,
            "bool": bool,
            "big_endian": ">f8",
        }[mutation]
        values["coefficients"] = np.asarray([1, 2, 3, 4], dtype=dtype)
    elif mutation in {"nan", "inf"}:
        values["intercept"] = np.asarray(float(mutation))
    elif mutation.startswith("scale"):
        values["scaler_scale"][0] = 0.0 if mutation == "scale0" else -1.0
    elif mutation in {"cutoff", "seed", "rows", "dates", "alpha"}:
        name = {
            "cutoff": "target_open_cutoff",
            "rows": "training_row_count",
            "dates": "training_date_count",
        }.get(mutation, mutation)
        values[name] = values[name] + 1
    else:
        values["seed"] = np.asarray(101, dtype=np.int32)
    with pytest.raises(ValueError):
        decode(npz(values))


@pytest.mark.parametrize("counts", [(True, 4), (40, True), (0, 0), (1, 2), (129, 1), (1000, 735)])
def test_expected_training_counts_are_explicit_bounded_integers(counts):
    with pytest.raises(ValueError, match="counts"):
        decode(expected_training_rows=counts[0], expected_training_dates=counts[1])


@pytest.mark.parametrize(
    "mutation",
    [
        "truncate",
        "not_zip",
        "compressed",
        "extra_member",
        "duplicate",
        "member_size",
        "huge_shape",
        "trailing_npy",
    ],
)
def test_archive_and_allocation_budget_rejects_malformed_before_numpy(monkeypatch, mutation):
    raw = npz()
    if mutation == "truncate":
        raw = raw[:-5]
    elif mutation == "not_zip":
        raw = b"synthetic nonzip bytes"
    elif mutation == "compressed":
        raw = npz(compressed=True)
    elif mutation == "extra_member":
        raw = rewrite(
            raw, lambda name, body: body, extra=("arbitrary.py", b"synthetic nonexecuted code")
        )
    elif mutation == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate"):
            raw = rewrite(raw, lambda name, body: body, extra=("seed.npy", b"duplicate"))
    elif mutation == "member_size":
        raw = rewrite(raw, lambda name, body: b"x" * 2048 if name == "seed.npy" else body)
    elif mutation == "huge_shape":
        stream = io.BytesIO()
        np.lib.format.write_array_header_1_0(
            stream, dict(descr="<f8", fortran_order=False, shape=(10**12, 4))
        )
        raw = rewrite(
            raw, lambda name, body: stream.getvalue() if name == "coefficients.npy" else body
        )
    else:
        raw = rewrite(raw, lambda name, body: body + b"unused" if name == "seed.npy" else body)
    monkeypatch.setattr(np, "load", lambda *a, **k: pytest.fail("numpy allocated malformed schema"))
    with pytest.raises(ValueError):
        decode(raw)


def test_np_load_never_allows_pickle_and_object_header_never_reaches_it(monkeypatch):
    original = np.load
    calls = []

    def inspected(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["allow_pickle"] is False
        return original(*args, **kwargs)

    monkeypatch.setattr(np, "load", inspected)
    decode()
    assert len(calls) == 1
    values = payload()
    values["coefficients"] = np.asarray([{}, {}, {}, {}], dtype=object)
    with pytest.raises(ValueError):
        decode(npz(values))
    assert len(calls) == 1


def test_supplied_bytes_cap_and_no_mutable_bytearray_input():
    with pytest.raises(ValueError, match="byte_budget"):
        decode(b"x" * (ridge.MAX_NPZ_BYTES + 1))
    with pytest.raises(ValueError, match="byte_budget"):
        decode(bytearray(npz()))


@pytest.mark.parametrize(
    "bad",
    [
        np.zeros((0, 4)),
        np.zeros((1, 3)),
        np.zeros((1, 20, 2)),
        np.ones((1, 4), dtype=bool),
        np.ones((1, 4), dtype=np.int64),
        np.ones((1, 4), dtype=complex),
        np.ones((1, 4), dtype=object),
        np.full((1, 4), np.nan),
        np.full((1, 4), np.inf),
    ],
)
def test_predict_rejects_nonreal_nonfinite_or_wrong_geometry(bad):
    with pytest.raises(ValueError):
        ridge.predict_ridge(decode(), bad)


def test_prediction_overflow_unavailable_not_clipped_and_input_not_mutated():
    state = decode()
    x = np.asarray([[0.2, -0.3, 0.7, 0.02]], dtype=np.float64)
    before = x.copy()
    ridge.predict_ridge(state, x)
    assert np.array_equal(x, before)
    tiny = replace(state, scaler_scale=np.full(4, 1e-300, dtype=np.float64))
    with pytest.raises(ValueError, match="nonfinite"):
        ridge.predict_ridge(tiny, np.full((1, 4), 1e300))


def test_current52_one_batched_call_exact_original_flatten_and_sparse_keys(monkeypatch):
    state = decode()
    groups = tuple(
        seal(i, KEYS[:0] if i == 66 else KEYS[:10] if i == 67 else KEYS) for i in range(61, 113)
    )
    original_predict = ridge.predict_ridge
    calls = []

    def predicted(state, features):
        calls.append(features.copy())
        return original_predict(state, features)

    monkeypatch.setattr(ridge, "predict_ridge", predicted)
    output = ridge.predict_current52(state, groups, expected_keys=KEYS)
    assert len(output) == 52 and len(calls) == 1
    x = np.asarray([row.values for group in groups for row in group.rows], dtype=np.float64)
    expected = original_predict(state, x)
    assert np.array_equal(calls[0], x)
    flat = np.asarray([value for group in output for _, value in group.scores])
    assert np.array_equal(flat, expected)
    assert output[5].scores == () and tuple(key for key, _ in output[6].scores) == KEYS[:10]
    assert all(group.features is supplied for group, supplied in zip(output, groups, strict=True))


@pytest.mark.parametrize("mutation", ["reverse", "missing_date", "different_plan", "keys"])
def test_current_batch_join_order_and_peer_binding_fail_before_prediction(monkeypatch, mutation):
    state = decode()
    groups = tuple(seal(i) for i in range(61, 113))
    keys = KEYS
    if mutation == "reverse":
        groups = groups[::-1]
    elif mutation == "missing_date":
        groups = groups[:-1]
    elif mutation == "different_plan":
        plan = replace(PLAN, open_clocks=tuple(t + timedelta(minutes=1) for t in OPEN))
        groups = (*groups[:-1], replace(groups[-1], plan=plan))
    else:
        keys = KEYS[:-1] + ("wrong-identity",)
    monkeypatch.setattr(
        ridge, "predict_ridge", lambda *args: pytest.fail("invalid peers predicted")
    )
    with pytest.raises(ValueError):
        ridge.predict_current52(state, groups, expected_keys=keys)


def test_prospective_uses_actual_completion_not_nominal_close_and_never_reinfers(monkeypatch):
    state, features = decode(), seal()
    predicted = ridge.predict_feature_seal(state, features)
    monkeypatch.setattr(
        ridge, "predict_ridge", lambda *args: pytest.fail("inferred after completion clock")
    )
    result = prospective(state, features, prediction=predicted)
    assert result.score_seal.snapshot.decision_at == clocks()["inference_completed_at"]
    assert result.nominal_prior_close_at == features.decision_at
    assert result.score_seal.snapshot.decision_at != features.decision_at
    assert result.score_seal.scores == predicted.scores
    assert result.model_sha256 == state.source_sha256
    assert not result.paper_input and not result.historical_availability_attested


@pytest.mark.parametrize(
    "change", ["late", "at_open", "before_cache", "before_close", "naive", "time_reverse"]
)
def test_prospective_clock_bindings_never_late_or_backdated(change):
    times = clocks()
    if change in {"late", "at_open"}:
        times["inference_completed_at"] = OPEN[112] + timedelta(seconds=change == "late")
    elif change == "before_cache":
        times["as_of"] = times["cache_observed_at"] - timedelta(seconds=1)
    elif change == "before_close":
        times["cache_observed_at"] = CLOSE[111] - timedelta(seconds=1)
    elif change == "naive":
        times["as_of"] = times["as_of"].replace(tzinfo=None)
    else:
        times["inference_completed_at"] = times["inference_started_at"] - timedelta(seconds=1)
    with pytest.raises(ValueError):
        prospective(**times)


@pytest.mark.parametrize("change", ["eligible", "clock", "entry", "model", "foreign_scores"])
def test_prospective_exact_feature_snapshot_model_score_join(change):
    state, features = decode(), seal()
    snap, prediction = snapshot(features), ridge.predict_feature_seal(state, features)
    if change == "eligible":
        snap = snapshot(seal(eligible=KEYS[:-1]))
    elif change == "clock":
        snap = replace(snap, entry_open_at=snap.entry_open_at + timedelta(minutes=1))
    elif change == "entry":
        features = seal(111)
        snap, prediction = snapshot(features), ridge.predict_feature_seal(state, features)
    elif change == "model":
        prediction = replace(prediction, model_sha256="sha256:" + "f" * 64)
    else:
        with pytest.raises(ValueError, match="peers"):
            replace(prediction, scores=prediction.scores[:-1])
        return
    with pytest.raises(ValueError):
        prospective(state, features, snap, prediction)


@pytest.mark.parametrize("count", [0, 1, 9])
def test_sparse_prospective_does_not_replace_peers_or_fabricate_top10(count):
    result = prospective(features=seal(eligible=KEYS[:count]))
    assert result.score_seal.weights is None
    assert tuple(key for key, _ in result.score_seal.scores) == KEYS[:count]
    assert result.score_seal.snapshot.unavailable_keys == KEYS[count:]


def test_loader_predict_and_seal_have_no_file_io_refits_or_output(monkeypatch, capsys):
    raw, features = npz(), seal()
    monkeypatch.setattr(
        "builtins.open", lambda *args, **kwargs: pytest.fail("adapter opened a file")
    )
    state = decode(raw)
    predicted = ridge.predict_feature_seal(state, features)
    result = prospective(state, features, prediction=predicted)
    assert result.score_seal.arm == "ridge"
    assert capsys.readouterr().out == ""

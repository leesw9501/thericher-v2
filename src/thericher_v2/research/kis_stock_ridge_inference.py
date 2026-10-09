"""Supplied-byte final Ridge reload and pure prospective research scoring.

Only the frozen cutoff799 numeric NPZ schema is accepted, never model code or
pickle. Expected hash/counts and actual observation clocks are caller-owned.
Clocks are checked for consistency, not independently attested. A score seal
is not an OrderIntent, Paper input, profitability or native parity claim.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType

import numpy as np

from thericher_v2.contracts import require_utc
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_relative_features as feature
from thericher_v2.research import kis_stock_score_replay as score

CUTOFF, SEED, ALPHA = 799, 101, 1.0
MAX_TRAIN_DATES = 734
MAX_NPZ_BYTES = 32768
MAX_MEMBER_BYTES = 1024
MAX_PREDICTION_ROWS = 52 * 128
_PIN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCHEMA = MappingProxyType(
    {
        "scaler_mean": ((4,), np.dtype("<f8")),
        "scaler_scale": ((4,), np.dtype("<f8")),
        "coefficients": ((4,), np.dtype("<f8")),
        "intercept": ((), np.dtype("<f8")),
        "alpha": ((), np.dtype("<f8")),
        "target_open_cutoff": ((), np.dtype("<i8")),
        "training_row_count": ((), np.dtype("<i8")),
        "training_date_count": ((), np.dtype("<i8")),
        "seed": ((), np.dtype("<i8")),
    }
)


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _counts(rows: int, dates: int) -> None:
    _require(
        type(rows) is int
        and type(dates) is int
        and 1 <= dates <= MAX_TRAIN_DATES
        and dates <= rows <= 128 * dates,
        "ridge_training_counts",
    )


def _frozen_float64(value: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    _require(
        type(value) is np.ndarray
        and value.shape == shape
        and value.dtype == np.dtype("<f8")
        and np.isfinite(value).all(),
        "ridge_state_shape_dtype_finite",
    )
    # Immutable bytes own a copy; setflags(write=True) cannot reopen this buffer.
    return np.frombuffer(value.tobytes(order="C"), dtype=np.float64).reshape(shape)


@dataclass(frozen=True, slots=True, eq=False)
class RidgeState:
    source_sha256: str
    scaler_mean: np.ndarray = field(repr=False)
    scaler_scale: np.ndarray = field(repr=False)
    coefficients: np.ndarray = field(repr=False)
    intercept: float = field(repr=False)
    training_row_count: int
    training_date_count: int
    target_open_cutoff: int = CUTOFF
    seed: int = SEED
    alpha: float = ALPHA

    def __post_init__(self) -> None:
        _require(
            type(self.source_sha256) is str and _PIN.fullmatch(self.source_sha256), "ridge_pin"
        )
        _counts(self.training_row_count, self.training_date_count)
        _require(
            type(self.target_open_cutoff) is int
            and self.target_open_cutoff == CUTOFF
            and type(self.seed) is int
            and self.seed == SEED
            and type(self.alpha) is float
            and self.alpha == ALPHA,
            "ridge_fixed_metadata",
        )
        _require(type(self.intercept) is float and np.isfinite(self.intercept), "ridge_intercept")
        for name in ("scaler_mean", "scaler_scale", "coefficients"):
            object.__setattr__(self, name, _frozen_float64(getattr(self, name), (4,)))
        _require(np.all(self.scaler_scale > 0), "ridge_positive_scale")


def _inspect_npz(raw: bytes) -> None:
    """Validate bounded NPY headers before numpy can allocate any claimed shape."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        names = {name + ".npy" for name in _SCHEMA}
        _require(
            len(members) == len(names)
            and {member.filename for member in members} == names
            and not archive.comment,
            "ridge_npz_keyset",
        )
        for member in members:
            # The frozen producer uses np.savez, not savez_compressed. This also
            # rejects compression bombs without trusting declared ratio alone.
            _require(
                member.compress_type == zipfile.ZIP_STORED
                and member.compress_size == member.file_size
                and 0 < member.file_size <= MAX_MEMBER_BYTES
                and not member.flag_bits & 1,
                "ridge_npz_member_budget",
            )
            body = archive.read(member)
            stream = io.BytesIO(body)
            _require(np.lib.format.read_magic(stream) == (1, 0), "ridge_npy_version")
            shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                stream, max_header_size=MAX_MEMBER_BYTES
            )
            expected_shape, expected_dtype = _SCHEMA[member.filename[:-4]]
            _require(
                shape == expected_shape and dtype == expected_dtype and fortran is False,
                "ridge_npy_shape_dtype",
            )
            size = (4 if shape else 1) * dtype.itemsize
            _require(stream.tell() + size == len(body), "ridge_npy_payload_length")


def decode_ridge_npz(
    raw: bytes,
    *,
    expected_sha256: str,
    expected_training_rows: int,
    expected_training_dates: int,
) -> RidgeState:
    """Decode only supplied immutable bytes; exact counts come from frozen custody.

    The hash identifies trusted bytes, not independent proof of training labels,
    peer universe, source data or scaler values. No external model is imported.
    """
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_NPZ_BYTES, "ridge_npz_byte_budget")
    _require(type(expected_sha256) is str and _PIN.fullmatch(expected_sha256), "ridge_pin")
    _counts(expected_training_rows, expected_training_dates)
    _require("sha256:" + hashlib.sha256(raw).hexdigest() == expected_sha256, "ridge_hash_mismatch")
    try:
        _inspect_npz(raw)
        with np.load(
            io.BytesIO(raw), allow_pickle=False, max_header_size=MAX_MEMBER_BYTES
        ) as values:
            _require(set(values.files) == set(_SCHEMA), "ridge_npz_keyset")
            arrays = {name: values[name] for name in _SCHEMA}
    except (ValueError, TypeError, OSError, EOFError, RuntimeError, OverflowError) as exc:
        raise ValueError("ridge_npz_invalid") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("ridge_npz_invalid") from exc
    for name, (shape, dtype) in _SCHEMA.items():
        value = arrays[name]
        _require(
            type(value) is np.ndarray
            and value.shape == shape
            and value.dtype == dtype
            and np.isfinite(value).all(),
            "ridge_numeric_schema",
        )
    _require(
        int(arrays["target_open_cutoff"]) == CUTOFF
        and int(arrays["seed"]) == SEED
        and float(arrays["alpha"]) == ALPHA
        and int(arrays["training_row_count"]) == expected_training_rows
        and int(arrays["training_date_count"]) == expected_training_dates,
        "ridge_fixed_metadata",
    )
    return RidgeState(
        expected_sha256,
        arrays["scaler_mean"],
        arrays["scaler_scale"],
        arrays["coefficients"],
        float(arrays["intercept"]),
        expected_training_rows,
        expected_training_dates,
    )


def predict_ridge(state: RidgeState, features: np.ndarray) -> np.ndarray:
    """Original float64 transform, then matrix @ coefficients + intercept."""
    _require(type(state) is RidgeState, "ridge_state_required")
    _require(
        type(features) is np.ndarray
        and features.ndim == 2
        and features.shape[1:] == (4,)
        and 0 < len(features) <= MAX_PREDICTION_ROWS
        and features.dtype.kind == "f"
        and np.isfinite(features).all(),
        "ridge_features_shape_dtype_finite",
    )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            transformed = (features.astype(np.float64) - state.scaler_mean) / state.scaler_scale
            prediction = transformed @ state.coefficients + state.intercept
    except FloatingPointError as exc:
        raise ValueError("ridge_prediction_nonfinite") from exc
    _require(
        prediction.shape == (len(features),)
        and prediction.dtype == np.float64
        and np.isfinite(prediction).all(),
        "ridge_prediction_nonfinite",
    )
    return prediction


@dataclass(frozen=True, slots=True)
class RidgeScores:
    features: feature.FeatureSeal = field(repr=False)
    model_sha256: str
    scores: tuple[tuple[str, float], ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require(isinstance(self.features, feature.FeatureSeal), "feature_seal_required")
        _require(type(self.model_sha256) is str and _PIN.fullmatch(self.model_sha256), "ridge_pin")
        _require(
            type(self.scores) is tuple
            and all(type(pair) is tuple and len(pair) == 2 for pair in self.scores)
            and tuple(key for key, _ in self.scores) == self.features.eligible_keys
            and all(type(value) is float and np.isfinite(value) for _, value in self.scores),
            "ridge_exact_feature_score_peers",
        )

    @property
    def entry_index(self) -> int:
        return self.features.entry_index


def predict_feature_seal(state: RidgeState, seal: feature.FeatureSeal) -> RidgeScores:
    """Pure single-group inference; caller records completion AFTER this returns."""
    _require(type(state) is RidgeState, "ridge_state_required")
    _require(
        isinstance(seal, feature.FeatureSeal) and not seal.include_sequence,
        "four_feature_seal_required",
    )
    prediction = (
        predict_ridge(state, np.asarray(seal.features, dtype=np.float64))
        if seal.rows
        else np.empty(0, dtype=np.float64)
    )
    return RidgeScores(
        seal,
        state.source_sha256,
        tuple(zip(seal.eligible_keys, map(float, prediction), strict=True)),
    )


def _keys(keys: tuple[str, ...]) -> None:
    _require(
        type(keys) is tuple
        and len(keys) == 128
        and all(type(key) is str and key for key in keys)
        and keys == tuple(sorted(set(keys))),
        "exact128_sorted_peer_keys",
    )


def predict_current52(
    state: RidgeState,
    seals: tuple[feature.FeatureSeal, ...],
    *,
    expected_keys: tuple[str, ...],
) -> tuple[RidgeScores, ...]:
    """Flatten all52 known CURRENT feature groups exactly like the original worker.

    Feature assembly stays caller-owned. Empty/sparse groups remain, with no
    target callback, future completeness filter or replacement of a key/date.
    """
    _require(type(state) is RidgeState, "ridge_state_required")
    _keys(expected_keys)
    _require(
        type(seals) is tuple
        and len(seals) == 52
        and all(isinstance(seal, feature.FeatureSeal) for seal in seals)
        and tuple(seal.entry_index for seal in seals) == tuple(range(61, 113)),
        "exact52_ordered_current_feature_groups",
    )
    plan = seals[0].plan
    _require(
        len(plan.sessions) == 113
        and plan.keys == expected_keys
        and all(seal.plan == plan and seal.include_sequence is False for seal in seals),
        "current_plan_peer_binding",
    )
    rows = [row.values for seal in seals for row in seal.rows]
    predictions = (
        predict_ridge(state, np.asarray(rows, dtype=np.float64))
        if rows
        else np.empty(0, dtype=np.float64)
    )
    offset, result = 0, []
    for seal in seals:
        count = len(seal.rows)
        values = predictions[offset : offset + count]
        result.append(
            RidgeScores(
                seal,
                state.source_sha256,
                tuple(zip(seal.eligible_keys, map(float, values), strict=True)),
            )
        )
        offset += count
    _require(offset == len(predictions), "ridge_prediction_row_binding")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ProspectiveRidgeSeal:
    score_seal: score.ScoreSeal
    model_sha256: str
    cache_observed_at: datetime
    as_of: datetime
    inference_started_at: datetime
    inference_completed_at: datetime
    nominal_prior_close_at: datetime
    paper_input: bool = False
    historical_availability_attested: bool = False


def seal_prospective_ridge(
    state: RidgeState,
    prediction: RidgeScores,
    snapshot: core.EligibilitySnapshot,
    *,
    expected_keys: tuple[str, ...],
    cache_observed_at: datetime,
    as_of: datetime,
    inference_started_at: datetime,
    inference_completed_at: datetime,
    owned_keys: tuple[str, ...] = (),
) -> ProspectiveRidgeSeal:
    """Bind caller-attested actual clocks to the last rolled113 pre-OPEN decision.

    This function does not predict again, obtain clocks or read bars/targets. Completed prior61
    eligibility comes from the supplied pure feature/snapshot kernels and frozen
    source custody. The returned ScoreSeal uses actual completion, not a
    backdated nominal prior CLOSE, for its decision_at.
    """
    _require(type(state) is RidgeState, "ridge_state_required")
    _require(
        type(prediction) is RidgeScores and prediction.model_sha256 == state.source_sha256,
        "ridge_prediction_model_binding",
    )
    features = prediction.features
    _keys(expected_keys)
    _require(
        isinstance(features, feature.FeatureSeal)
        and isinstance(snapshot, core.EligibilitySnapshot)
        and len(features.plan.sessions) == 113
        and features.entry_index == 112
        and features.plan.keys == expected_keys
        and features.include_sequence is False
        and snapshot.entry_index == features.entry_index
        and snapshot.entry_session == features.entry_session
        and snapshot.decision_session == features.plan.sessions[111]
        and snapshot.decision_at == features.decision_at
        and snapshot.entry_open_at == features.entry_open_at
        and snapshot.target_close_at == features.plan.close_clocks[112]
        and snapshot.eligible_keys == features.eligible_keys
        and snapshot.unavailable_keys == features.unavailable_keys,
        "prospective_feature_snapshot_peer_binding",
    )
    times = (cache_observed_at, as_of, inference_started_at, inference_completed_at)
    _require(all(isinstance(value, datetime) for value in times), "actual_clock_required")
    observed, cutoff, started, completed = (
        require_utc(value, "actual_inference_clock") for value in times
    )
    _require(
        features.decision_at <= observed <= cutoff <= started <= completed < features.entry_open_at,
        "prospective_observation_time_binding",
    )
    scores = dict(prediction.scores)
    actual_snapshot = replace(snapshot, decision_at=completed)
    seal = score.seal_scores(actual_snapshot, owned_keys, scores, arm="ridge")
    return ProspectiveRidgeSeal(
        seal,
        state.source_sha256,
        observed,
        cutoff,
        started,
        completed,
        features.decision_at,
    )

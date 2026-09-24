"""Pure fixed expert/fusion learner. Caller owns source, payoff, replay and custody."""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.tree import DecisionTreeRegressor

TARGET_KEYS = (
    "trend",
    "reversion",
    "ridge",
    "majority",
    "gate",
    "without_trend",
    "without_reversion",
    "without_ridge",
    "always_flat",
    "always_long",
)
GATE_FEATURES = (
    "trend_vote",
    "reversion_vote",
    "ridge_vote",
    "sma3_to_sma12_minus_one",
    "last_to_mean12_minus_one",
    "body_std12",
)
HISTORY = timedelta(minutes=180)
HOLD = timedelta(minutes=30)
MIN_INNER_TRAIN = MIN_OOF = 128
DECISION_COST_BPS_PER_SIDE = 3
NY = ZoneInfo("America/New_York")


class GraphInputUnavailable(ValueError):
    """Closed support failure; no partial fitted graph is returned."""

    status = "input_unavailable"

    def __init__(self, reason: str, count: int):
        super().__init__(reason)
        self.reason = reason
        self.count = count


@dataclass(frozen=True)
class GraphPrediction:
    targets: Mapping[str, np.ndarray] = field(repr=False)
    gate_choice: np.ndarray = field(repr=False)
    diagnostics: dict[str, object]


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _deadline(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("graph_deadline_exceeded")


def _array(value, shape, name):
    _require(
        isinstance(value, np.ndarray) and value.dtype == np.dtype("float64"),
        f"{name}_float64_required",
    )
    _require(value.shape == shape, f"{name}_shape")
    _require(np.isfinite(value).all(), f"{name}_nonfinite")


def _times(values: Sequence[datetime], count: int, name: str):
    values = tuple(values)
    _require(len(values) == count, f"{name}_shape")
    _require(
        all(
            isinstance(t, datetime) and t.tzinfo is not None and t.utcoffset() == timedelta(0)
            for t in values
        ),
        f"{name}_utc_required",
    )
    result = tuple(t.astimezone(UTC) for t in values)
    _require(all(a < b for a, b in zip(result, result[1:], strict=False)), f"{name}_order")
    return result


def _hash(*arrays):
    digest = hashlib.sha256()
    for array in arrays:
        value = np.ascontiguousarray(array)
        digest.update(str((value.dtype.str, value.shape)).encode("ascii"))
        digest.update(value.tobytes())
    return "sha256:" + digest.hexdigest()


def _time_hash(times):
    return "sha256:" + hashlib.sha256("\n".join(t.isoformat() for t in times).encode()).hexdigest()


def _rule_context(x, closes):
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            last12 = closes[:, -12:]
            mean12 = last12.mean(axis=1)
            mean3 = closes[:, -3:].mean(axis=1)
            std12 = last12.std(axis=1, ddof=0)
            trend = mean3 > mean12
            reversion = (std12 > 0) & (closes[:, -1] < mean12 - std12)
            context = np.column_stack(
                (mean3 / mean12 - 1, closes[:, -1] / mean12 - 1, x[:, -12:, 0].std(axis=1, ddof=0))
            )
        except FloatingPointError:
            raise ValueError("nonfinite_rule_context") from None
    _require(np.isfinite(context).all(), "nonfinite_rule_context")
    return trend, reversion, context


def _ridge_predict(train_x, train_y, eval_x, deadline):
    _deadline(deadline)
    mean = train_x.mean(axis=(0, 1))
    scale = train_x.std(axis=(0, 1), ddof=0)
    scale = np.where(scale == 0, 1.0, scale)
    train = ((train_x - mean) / scale).reshape(len(train_x), -1)
    evaluation = ((eval_x - mean) / scale).reshape(len(eval_x), -1)
    _require(np.isfinite(train).all() and np.isfinite(evaluation).all(), "nonfinite_scaler")
    model = Ridge(alpha=1.0, solver="svd", fit_intercept=True)
    model.fit(train, train_y)
    _deadline(deadline)
    predictions = model.predict(evaluation)
    _require(np.isfinite(predictions).all(), "nonfinite_ridge")
    return predictions, dict(
        scaler_sha256=_hash(mean, scale),
        model_sha256=_hash(model.coef_, np.asarray(model.intercept_)),
    )


def _expert_votes(trend, reversion, predictions):
    return np.column_stack((trend, reversion, predictions > 6.0))


def _gate_decision(votes, utilities):
    _require(utilities.shape == votes.shape and np.isfinite(utilities).all(), "gate_output")
    winner = np.argmax(utilities, axis=1)  # Fixed tie order: trend, reversion, Ridge.
    positive = utilities[np.arange(len(votes)), winner] > 0
    choice = np.where(positive, winner + 1, 0).astype("int64")
    return choice, positive & votes[np.arange(len(votes)), winner]


def _inner_splits(times):
    dates = tuple(t.astimezone(NY).date() for t in times)
    unique = sorted(set(dates))
    if len(unique) < 4:
        raise GraphInputUnavailable("insufficient_training_dates", len(unique))
    date_index = {d: i for i, d in enumerate(unique)}
    day = np.asarray([date_index[d] for d in dates])
    cuts = (len(unique) // 4, len(unique) // 2, 3 * len(unique) // 4, len(unique))
    splits = []
    for left, right in zip(cuts, cuts[1:], strict=False):
        validation = np.flatnonzero((day >= left) & (day < right))
        cutoff = times[int(validation[0])] - HISTORY
        training = np.asarray(
            [i for i, t in enumerate(times) if day[i] < left and t + HOLD < cutoff], dtype="int64"
        )
        if len(training) < MIN_INNER_TRAIN:
            raise GraphInputUnavailable("insufficient_inner_train", len(training))
        splits.append((training, validation, cutoff))
    count = sum(len(validation) for _, validation, _ in splits)
    if count < MIN_OOF:
        raise GraphInputUnavailable("insufficient_pooled_oof", count)
    return splits


def fit_predict_graph(
    *,
    train_x,
    eval_x,
    train_closes,
    eval_closes,
    train_times,
    eval_times,
    train_y,
    train_net_y,
    deadline,
) -> GraphPrediction:
    """Fit three chronological OOF Ridges, a fixed utility gate and final Ridge.

    Times are decision instants: histories cover [t-180m,t), and labels end
    at t+30m. The caller attests source/session coverage and supplies exact
    3bps/side net labels; this function never reconstructs costs or positions.
    Decisions are frozen at that standalone basis. External 1/3/5/10bps-side
    replay is accounting sensitivity, not refitting or independent evidence.
    """
    _require(type(deadline) in (int, float) and math.isfinite(deadline), "deadline_finite_required")
    _deadline(deadline)
    _require(isinstance(train_x, np.ndarray) and train_x.ndim == 3, "train_x_shape")
    _require(isinstance(eval_x, np.ndarray) and eval_x.ndim == 3, "eval_x_shape")
    n, m = len(train_x), len(eval_x)
    _require(n > 0 and m > 0, "empty_input")
    for value, shape, name in (
        (train_x, (n, 36, 4), "train_x"),
        (eval_x, (m, 36, 4), "eval_x"),
        (train_closes, (n, 36), "train_closes"),
        (eval_closes, (m, 36), "eval_closes"),
        (train_y, (n,), "train_y"),
        (train_net_y, (n,), "train_net_y"),
    ):
        _array(value, shape, name)
    _require((train_closes > 0).all() and (eval_closes > 0).all(), "closes_positive_required")
    training_times = _times(train_times, n, "train_times")
    evaluation_times = _times(eval_times, m, "eval_times")
    _require(training_times[-1] + HOLD < evaluation_times[0] - HISTORY, "outer_purge")
    splits = _inner_splits(training_times)  # Preflight every support minimum before fitting.
    train_trend, train_reversion, train_context = _rule_context(train_x, train_closes)
    eval_trend, eval_reversion, eval_context = _rule_context(eval_x, eval_closes)
    contexts, utilities, oof_indices, inner = [], [], [], []
    for training, validation, cutoff in splits:
        forecasts, identity = _ridge_predict(
            train_x[training], train_y[training], train_x[validation], deadline
        )
        votes = _expert_votes(train_trend[validation], train_reversion[validation], forecasts)
        contexts.append(np.column_stack((votes, train_context[validation])))
        utilities.append(votes * train_net_y[validation, None])
        oof_indices.extend(validation.tolist())
        inner.append(
            dict(
                train_count=len(training),
                validation_count=len(validation),
                train_last=training_times[int(training[-1])].isoformat(),
                train_label_end=(training_times[int(training[-1])] + HOLD).isoformat(),
                validation_first=training_times[int(validation[0])].isoformat(),
                validation_last=training_times[int(validation[-1])].isoformat(),
                validation_history_start=cutoff.isoformat(),
                train_times_sha256=_time_hash([training_times[i] for i in training]),
                validation_times_sha256=_time_hash([training_times[i] for i in validation]),
                **identity,
            )
        )
    meta_x, meta_y = np.concatenate(contexts), np.concatenate(utilities)
    _require(np.isfinite(meta_x).all() and np.isfinite(meta_y).all(), "nonfinite_oof")
    _deadline(deadline)
    gate = DecisionTreeRegressor(max_depth=2, min_samples_leaf=64, random_state=811)
    gate.fit(meta_x, meta_y)
    _deadline(deadline)
    forecasts, final = _ridge_predict(train_x, train_y, eval_x, deadline)
    votes = _expert_votes(eval_trend, eval_reversion, forecasts)
    expected = gate.predict(np.column_stack((votes, eval_context)))
    choice, gated = _gate_decision(votes, expected)
    targets = dict(
        trend=votes[:, 0],
        reversion=votes[:, 1],
        ridge=votes[:, 2],
        majority=votes.sum(axis=1) >= 2,
        gate=gated,
        without_trend=votes[:, 1] & votes[:, 2],
        without_reversion=votes[:, 0] & votes[:, 2],
        without_ridge=votes[:, 0] & votes[:, 1],
        always_flat=np.zeros(m, dtype=bool),
        always_long=np.ones(m, dtype=bool),
    )
    targets = {key: np.array(targets[key], dtype=bool, copy=True) for key in TARGET_KEYS}
    for value in (*targets.values(), choice):
        value.setflags(write=False)
    tree = gate.tree_
    leaves = np.flatnonzero(tree.children_left == -1)
    leaf_use = gate.apply(np.column_stack((votes, eval_context)))
    chosen_utility = np.where(choice > 0, expected.max(axis=1), 0.0)
    diagnostics = dict(
        train_count=n,
        eval_count=m,
        oof_count=len(meta_x),
        ridge_fits=4,
        tree_fits=1,
        decision_cost_bps_per_side=DECISION_COST_BPS_PER_SIDE,
        gate_depth=int(gate.get_depth()),
        gate_leaves=int(gate.get_n_leaves()),
        train_last=training_times[-1].isoformat(),
        eval_first=evaluation_times[0].isoformat(),
        outer_label_end=(training_times[-1] + HOLD).isoformat(),
        outer_history_start=(evaluation_times[0] - HISTORY).isoformat(),
        inner=inner,
        final=final,
        oof_sha256=_hash(np.asarray(oof_indices), meta_x, meta_y),
        gate_sha256=_hash(
            tree.children_left,
            tree.children_right,
            tree.feature,
            tree.threshold,
            tree.value,
            tree.n_node_samples,
        ),
        gate_choice_counts=np.bincount(choice, minlength=4).tolist(),
        gate_leaf_ids=leaves.tolist(),
        gate_leaf_train_counts=tree.n_node_samples[leaves].tolist(),
        gate_leaf_eval_counts=[int(np.count_nonzero(leaf_use == leaf)) for leaf in leaves],
        mean_chosen_gate_utility_bps=float(chosen_utility.mean()),
        target_sha256={k: _hash(v) for k, v in targets.items()},
    )
    _deadline(deadline)
    return GraphPrediction(MappingProxyType(targets), choice, diagnostics)

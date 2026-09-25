"""Fixed TRAIN-only shallow boosting on the unchanged causal Ridge features."""

from __future__ import annotations

import math
import time

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from thericher_v2.research.causal_feature_ridge import FEATURES as FEATURES
from thericher_v2.research.causal_feature_ridge import feature_matrix
from thericher_v2.research.policy_graph_models import _array, _hash, _require

PARAMETERS = dict(
    loss="squared_error",
    learning_rate=0.05,
    n_estimators=64,
    subsample=1.0,
    criterion="friedman_mse",
    min_samples_split=2,
    min_samples_leaf=64,
    max_depth=2,
    max_features=None,
    random_state=911,
    n_iter_no_change=None,
)


def _deadline(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("causal_feature_boosting_deadline_exceeded")


def _model_sha256(model):
    _require(
        model.n_estimators_ == 64 and model.estimators_.shape == (64, 1),
        "boosting_estimator_count",
    )
    arrays = [model.init_.constant_]
    for estimator in model.estimators_[:, 0]:
        tree = estimator.tree_
        arrays.extend(
            (
                np.asarray(tree.node_count, dtype="int64"),
                tree.children_left,
                tree.children_right,
                tree.feature,
                tree.threshold,
                tree.value,
                tree.n_node_samples,
                tree.weighted_n_node_samples,
                tree.impurity,
            )
        )
    _require(all(np.isfinite(array).all() for array in arrays), "nonfinite_boosting")
    return _hash(*arrays)


def fit_predict(
    *, train_x, train_closes, train_y, eval_x, eval_closes, deadline
) -> tuple[np.ndarray, dict[str, str]]:
    """Fit once on all TRAIN rows, without scaling, tuning or an internal split.

    The caller owns completed-bar availability and temporal purging. Deadline
    is absolute time.monotonic(); checks surround fit/predict, while the worker
    supervisor owns the hard cap. Only predictions and two hashes leave here.
    """
    _require(
        type(deadline) in (int, float) and -math.inf < deadline < math.inf,
        "deadline_finite_required",
    )
    _deadline(deadline)
    train_features = feature_matrix(train_x, train_closes)
    eval_features = feature_matrix(eval_x, eval_closes)
    _array(train_y, (len(train_features),), "train_y")
    _deadline(deadline)
    model = GradientBoostingRegressor(**PARAMETERS)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            model.fit(train_features, train_y)
        except (FloatingPointError, OverflowError, ValueError, np.linalg.LinAlgError):
            raise ValueError("boosting_numerical_failure") from None
    _deadline(deadline)
    identity = dict(
        model_sha256=_model_sha256(model),
        training_features_sha256=_hash(train_features),
    )
    _deadline(deadline)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            forecast = model.predict(eval_features)
        except (FloatingPointError, OverflowError, ValueError, np.linalg.LinAlgError):
            raise ValueError("boosting_numerical_failure") from None
    _deadline(deadline)
    _array(forecast, (len(eval_features),), "forecast")
    forecast.setflags(write=False)
    return forecast, identity

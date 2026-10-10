"""Explicit owned Goal80 inference; research allocation, never broker RiskLimits."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from thericher_v2.research.five_session_cohort import FiveSessionFrame

TEACHER_SHA256 = "ca6b36d1686365fe4f6680589bb0927e7e2e143e1b69a7ab13dd88339d2ae5a0"
METADATA_SHA256 = "2ce286eeec36093f412eb9b27966a6ab6869c9856cc24f7b5b06adc87b3eeb35"
IDENTITY_SHA256 = "533d35e49da24aa81255e7e540d7ddae216e5b7177a45cf3f7cd01252f4bfe09"
FEATURE_SHA256 = "04df85bc83e18cba01718be9398bf7eaad1f716d399510fd1ec28e45c9c77709"
TRAINING_CUTOFF = datetime(2026, 3, 3, 21, tzinfo=UTC)
MODEL_PARAMETERS = {
    "categorical_features": None,
    "early_stopping": False,
    "l2_regularization": 0.1,
    "learning_rate": 0.05,
    "loss": "squared_error",
    "max_bins": 63,
    "max_depth": 4,
    "max_iter": 128,
    "max_leaf_nodes": 15,
    "min_samples_leaf": 64,
    "random_state": 101,
}


class TreeError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise TreeError(reason)


def _checked_bytes(path: Path, expected: str, maximum: int) -> bytes:
    path = Path(path)
    require(not any(p.is_symlink() for p in (path, *path.parents)), "teacher_linked_path")
    require(path.is_file() and path.stat().st_size <= maximum, "teacher_file_bound")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(
        len(raw) <= maximum and hashlib.sha256(raw).hexdigest() == expected,
        "teacher_hash_binding",
    )
    return raw


def _document(raw: bytes) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "teacher_duplicate_metadata")
            out[key] = value
        return out

    doc = json.loads(raw, object_pairs_hook=pairs)
    require(type(doc) is dict, "teacher_metadata_schema")
    return doc


def _validate_metadata(doc: dict, size: int) -> None:
    expected = {
        "kind": "self_generated_frozen_HGBR_and_scaler_export_v1",
        "format": "private_own_pickle_protocol5",
        "artifact": "teacher.pkl",
        "sha256": "sha256:" + TEACHER_SHA256,
        "size_bytes": size,
        "model_class": "sklearn.ensemble.HistGradientBoostingRegressor",
        "scaler_mean_shape": [5],
        "scaler_scale_shape": [5],
        "scaler_dtype": "float64",
        "complete_training_dates": 675,
        "training_entries": [20, 695],
        "training_last_exit_index": 699,
        "training_last_exit_ts": TRAINING_CUTOFF.isoformat(),
        "identity_sha256": "sha256:" + IDENTITY_SHA256,
        "sklearn_version": "1.9.1",
        "numpy_version": "2.5.1",
        "seed": 101,
        "availability": "assumed_not_observed",
        "promotion_eligible": False,
        "broker_input": False,
        "roundtrip_verified": True,
        "prediction_bit_equal": True,
    }
    require(all(doc.get(k) == v for k, v in expected.items()), "teacher_metadata_binding")
    require(
        type(doc.get("source_pins")) is dict
        and doc["source_pins"].get("/model/ranking.py") == "sha256:" + FEATURE_SHA256
        and doc.get("model_parameters")
        == MODEL_PARAMETERS | {"implementation": expected["model_class"]},
        "teacher_recipe_binding",
    )


def _deserialize(raw: bytes):
    # Reachable only after both immutable owned byte hashes and runtime checks.
    import pickle

    from sklearn.ensemble import HistGradientBoostingRegressor
    from threadpoolctl import threadpool_limits

    bundle = pickle.loads(raw)
    require(
        type(bundle) is dict and set(bundle) == {"model", "scaler_mean", "scaler_scale"},
        "teacher_bundle_schema",
    )
    model = bundle["model"]
    require(
        type(model) is HistGradientBoostingRegressor
        and model.n_features_in_ == 100
        and model.n_iter_ == 128
        and all(model.get_params()[k] == v for k, v in MODEL_PARAMETERS.items()),
        "teacher_model_binding",
    )

    def predict(x):
        with threadpool_limits(limits=2):
            return model.predict(x)

    return predict, bundle["scaler_mean"], bundle["scaler_scale"]


@dataclass(frozen=True, eq=False)
class TreeDecision:
    status: Literal["ready", "input_unavailable"]
    reason: str
    scores: NDArray[np.float64] = field(repr=False)
    weights: NDArray[np.float64] = field(repr=False)
    original_slots: tuple[int, ...]
    frame_stamp: str
    teacher_sha256: str = field(default_factory=lambda: TEACHER_SHA256)
    availability: str = "assumed_not_observed"

    def __post_init__(self) -> None:
        import numpy as np

        from thericher_v2.research.five_session_cohort import frozen

        scores, weights = frozen(self.scores), frozen(self.weights)
        slots = tuple(self.original_slots)
        require(
            scores.shape == weights.shape == (512,)
            and np.isfinite(scores).all()
            and np.isfinite(weights).all()
            and (weights >= 0).all()
            and (weights <= 0.10 + 1e-12).all()
            and weights.sum() <= 0.50 + 1e-12
            and len(slots) in (0, 10)
            and len(set(slots)) == len(slots)
            and all(type(i) is int and 0 <= i < 512 for i in slots)
            and set(np.flatnonzero(weights)) <= set(slots),
            "tree_decision_geometry_caps",
        )
        require(
            self.status in ("ready", "input_unavailable")
            and (self.status == "ready" or (not slots and not weights.any()))
            and self.teacher_sha256 == TEACHER_SHA256
            and self.availability == "assumed_not_observed"
            and bool(self.frame_stamp),
            "tree_decision_binding",
        )
        for key, value in (("scores", scores), ("weights", weights), ("original_slots", slots)):
            object.__setattr__(self, key, value)


@dataclass(frozen=True, eq=False)
class _TreeInference:
    _predict: Callable = field(repr=False)
    _mean: NDArray[np.float64] = field(repr=False)
    _scale: NDArray[np.float64] = field(repr=False)

    def __call__(self, frame: FiveSessionFrame) -> TreeDecision:
        import numpy as np

        from thericher_v2.research.five_session_cohort import FiveSessionFrame

        require(isinstance(frame, FiveSessionFrame), "typed_tree_frame")
        identity = json.dumps(list(frame.identities), separators=(",", ":")).encode()
        require(hashlib.sha256(identity).hexdigest() == IDENTITY_SHA256, "tree_identity_binding")
        require(
            frame.decision > TRAINING_CUTOFF
            and frame.prior_closes[-1] < frame.decision < frame.target_open
            and frame.availability == "assumed_not_observed"
            and len(frame.feature_stamp) == 64
            and all(k in "0123456789abcdef" for k in frame.feature_stamp),
            "tree_causal_feature_binding",
        )
        require(
            frame.tokens.shape == (512, 20, 5)
            and frame.eligible.shape == frame.momentum.shape == frame.volatility.shape == (512,)
            and frame.eligible.dtype == np.bool_
            and np.isfinite(frame.tokens).all()
            and np.isfinite(frame.momentum).all()
            and np.isfinite(frame.volatility).all()
            and (frame.volatility >= 0.10).all()
            and (frame.momentum[frame.eligible] > -1).all(),
            "tree_feature_values",
        )
        supported = bool(frame.eligible.sum() >= 128 and frame.eligible[128:].sum() >= 64)
        require(frame.supported == supported, "tree_support_binding")
        scores, weights = np.zeros(512), np.zeros(512)
        if not supported:
            return TreeDecision(
                "input_unavailable", "prior_causal_support", scores, weights, (), frame.stamp
            )
        scaled = (frame.tokens - self._mean) / self._scale
        scaled[~frame.eligible] = 0
        require(np.isfinite(scaled).all(), "tree_scaled_finite")
        predicted = np.asarray(self._predict(scaled[frame.eligible].reshape(-1, 100)))
        require(
            predicted.shape == (int(frame.eligible.sum()),) and np.isfinite(predicted).all(),
            "tree_scores_binding",
        )
        scores[frame.eligible] = predicted
        slots = tuple(
            sorted(np.flatnonzero(frame.eligible).tolist(), key=lambda i: (-scores[i], i))[:10]
        )
        sigma = frame.volatility[list(slots)]
        original = np.minimum(0.10, 0.50 * (1 / sigma) / (1 / sigma).sum())
        original *= min(1.0, 0.08 / float(np.dot(original, sigma)))
        proxy = np.expm1(0.25 * np.log1p(frame.momentum[list(slots)]))
        weights[list(slots)] = original * (proxy > 0.003)
        require(np.dot(weights, frame.volatility) <= 0.08 + 1e-12, "tree_triangle_risk")
        return TreeDecision("ready", "frozen_goal80_tree", scores, weights, slots, frame.stamp)


def load_goal80_teacher(model_path: Path, metadata_path: Path) -> _TreeInference:
    """Load only the exact owned artifact; no hash argument, fit API or default path.

    Call in the isolated pinned CPU runtime. Frame producers attest canonical
    04df features and calendar completeness; a stamp alone cannot prove provenance.
    """
    metadata = _checked_bytes(metadata_path, METADATA_SHA256, 64 * 1024)
    raw = _checked_bytes(model_path, TEACHER_SHA256, 16 * 1024**2)
    _validate_metadata(_document(metadata), len(raw))

    import numpy as np

    from thericher_v2.research.five_session_cohort import frozen

    require(
        np.__version__ == "2.5.1" and version("scikit-learn") == "1.9.1", "tree_runtime_binding"
    )
    predict, mean, scale = _deserialize(raw)
    require(
        callable(predict)
        and all(
            type(x) is np.ndarray and x.dtype == np.float64 and x.shape == (5,)
            for x in (mean, scale)
        )
        and np.isfinite(mean).all()
        and np.isfinite(scale).all()
        and (scale > 0).all(),
        "tree_scaler_binding",
    )
    return _TreeInference(predict, frozen(mean), frozen(scale))

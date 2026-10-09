"""Pure decision-time expert geometry, date-balanced Ridge and named seals.

The caller binds source/registry/calendar identities and supplies already
qualified labels. No target is read here, and labels never define eligibility.
Entry indices identify dates in the caller's pinned training calendar; a later
snapshot has its own calendar, not a merged price window. All evidence is seen
development, not historical availability, independent replication or Paper input.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np

from thericher_v2.research import kis_pooled_equity_components as core

EXPERTS = ("component", "momentum5", "momentum20", "momentum60")
VIEW_WIDTHS = MappingProxyType({"expert_rank": 4, "component_flat": 40})
RIDGE_ALPHA = 1.0
ROUND_TRIP_BPS = core.ROUND_TRIP_BPS
UNIFORM_POLICY = "uniform_rank_blend"
LEARNED_POLICIES = ("expert_rank_ridge", "component_flat_ridge", "contextual_gate")
OOF_FOLDS = (
    core.PrefixFold(427, range(429, 611)),
    core.PrefixFold(609, range(611, 800)),
)
FINAL_FIT_ENTRIES = range(61, 800)
RowKey = tuple[int, str]


def normalized_midranks(scores: Sequence[core.Score]) -> tuple[float, ...]:
    """Ascending finite midranks/(N-1)-.5; empty/singleton geometry is zero."""
    values = tuple(core._score(value) for value in scores)
    if len(values) < 2:
        return (0.0,) * len(values)
    return tuple(rank / (len(values) - 1) - 0.5 for rank in core._midranks(values))


@dataclass(frozen=True, slots=True)
class FusionInputs:
    snapshot: core.EligibilitySnapshot
    component_flat: tuple[tuple[float, ...], ...] = field(init=False)
    expert_ranks: tuple[tuple[float, ...], ...] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, core.EligibilitySnapshot):
            raise ValueError("bound_eligibility_snapshot_required")
        experts = core.controls(self.snapshot)
        ranks = tuple(
            normalized_midranks(tuple(score for _, score in experts[name].scores))
            for name in EXPERTS
        )
        object.__setattr__(
            self, "component_flat", tuple(row.flattened for row in self.snapshot.rows)
        )
        object.__setattr__(self, "expert_ranks", tuple(zip(*ranks, strict=True)))

    @property
    def eligible_keys(self) -> tuple[str, ...]:
        return self.snapshot.eligible_keys

    @property
    def unavailable_keys(self) -> tuple[str, ...]:
        return self.snapshot.unavailable_keys

    def features(self, view: str) -> tuple[tuple[float, ...], ...]:
        _width(view)
        return self.expert_ranks if view == "expert_rank" else self.component_flat


def snapshot(
    plan: core.ComponentPlan, entry_index: int, past_source: core.PastSource
) -> FusionInputs:
    """Delegate the exact prior-61 scheduled-bar reads to the causal core."""
    return FusionInputs(core.snapshot(plan, entry_index, past_source))


def uniform_rank_blend(inputs: FusionInputs) -> core.PredictionSeal:
    weights = ((0.25,) * len(EXPERTS),) * len(inputs.eligible_keys)
    return core.seal(inputs.snapshot, weighted_rank_scores(inputs, weights))


def weighted_rank_scores(inputs: FusionInputs, expert_weights: object) -> tuple[float, ...]:
    """Blend the SAME centered ranks using caller's per-instrument softmax weights.

    Torch computes the gate externally. N x 4 weights use the eligible-key and
    EXPERTS order, never a global four-weight vector. Sum tolerance1e-6 permits
    float32 softmax roundoff; supplied weights are not silently renormalized.
    """
    weights = _matrix(expert_weights, len(EXPERTS))
    if len(weights) != len(inputs.eligible_keys):
        raise ValueError("weights_must_cover_entire_eligible_snapshot")
    if not ((weights >= 0) & (weights <= 1)).all() or any(
        not math.isclose(math.fsum(row), 1.0, rel_tol=0, abs_tol=1e-6) for row in weights
    ):
        raise ValueError("per_instrument_softmax_weights_required")
    return tuple(
        math.fsum(rank * weight for rank, weight in zip(ranks, row, strict=True))
        for ranks, row in zip(inputs.expert_ranks, weights, strict=True)
    )


def training_labels(inputs: FusionInputs, labels: core.RankLabels) -> tuple[float, ...]:
    """Bind supplied complete-date ranks, without reading targets or dropping peers."""
    if not isinstance(labels, core.RankLabels) or labels.snapshot != inputs.snapshot:
        raise ValueError("labels_must_match_decision_snapshot")
    if labels.labels is None or labels.missing_keys:
        raise ValueError("complete_date_rank_labels_required")
    if tuple(key for key, _ in labels.labels) != inputs.eligible_keys:
        raise ValueError("labels_must_cover_entire_eligible_snapshot")
    return tuple(
        float(value)
        for value in _vector(
            tuple(value for _, value in labels.labels), len(inputs.eligible_keys), "labels"
        )
    )


def seal_predictions(
    inputs: FusionInputs,
    predictions: Mapping[str, Mapping[str, core.Score] | Sequence[core.Score]] | None = None,
) -> Mapping[str, core.PredictionSeal]:
    """Seal complete named score vectors; caller may replay each via core.replay_day.

    Contextual-gate scores use weighted_rank_scores with caller's softmax weights;
    no Torch model is loaded here. Metrics and conditional-value tests are external.
    No candidate is renamed to tcn/ridge or passed through core.evaluate_day.
    """
    supplied = {} if predictions is None else dict(predictions)
    if set(supplied) - set(LEARNED_POLICIES):
        raise ValueError("unknown_fusion_policy_name")
    result = dict(core.controls(inputs.snapshot))
    result[UNIFORM_POLICY] = uniform_rank_blend(inputs)
    for name in LEARNED_POLICIES:
        if name in supplied:
            result[name] = core.seal(inputs.snapshot, supplied[name])
    return MappingProxyType(result)


def validate_fold(plan: core.ComponentPlan, fold: core.PrefixFold) -> None:
    """Validate only the two fixed prefix folds, with a full nominal-clock gap."""
    if not isinstance(plan, core.ComponentPlan) or fold not in OOF_FOLDS:
        raise ValueError("fixed_fusion_prefix_fold_required")
    if plan.close_clocks[fold.fit_target_cutoff] >= plan.close_clocks[fold.score_entries.start - 1]:
        raise ValueError("fit_target_must_precede_first_decision")


def _width(view: str) -> int:
    if view not in VIEW_WIDTHS:
        raise ValueError("fixed_ridge_view_required")
    return VIEW_WIDTHS[view]


def _real_array(value: object, name: str) -> np.ndarray:
    try:
        if not isinstance(value, np.ndarray) and any(
            isinstance(item, (bool, np.bool_)) for item in np.asarray(value, dtype=object).flat
        ):
            raise ValueError
        raw = np.asarray(value)
        if raw.dtype.kind not in "iuf":
            raise ValueError
        array = raw.astype(np.float64, copy=True)
        if not np.isfinite(array).all():
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name}_must_be_finite_real") from None
    return array


def _matrix(value: object, width: int) -> np.ndarray:
    array = _real_array(value, "features")
    if array.shape == (0,):
        array = array.reshape(0, width)
    if array.ndim != 2 or array.shape[1] != width:
        raise ValueError("fixed_feature_geometry_required")
    return array


def _vector(value: object, size: int, name: str) -> np.ndarray:
    array = _real_array(value, name)
    if array.shape != (size,):
        raise ValueError(f"{name}_geometry_required")
    return array


def _row_keys(value: Sequence[RowKey]) -> tuple[RowKey, ...]:
    try:
        keys = tuple(tuple(pair) for pair in value)
    except TypeError:
        raise ValueError("training_date_key_identity_required") from None
    if not keys or any(
        len(pair) != 2
        or type(pair[0]) is not int
        or not 61 <= pair[0] < core.SESSION_COUNT
        or not isinstance(pair[1], str)
        or not pair[1]
        for pair in keys
    ):
        raise ValueError("training_date_key_identity_required")
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_training_date_key")
    return keys


def date_balanced_weights(row_keys: Sequence[RowKey]) -> tuple[float, ...]:
    """Each date has equal total weight; normalize total weight to row count.

    Caller supplies training_labels-bound rows, not an outcome-filtered decision
    universe. This function neither removes missing rows nor invents labels.
    """
    keys = _row_keys(row_keys)
    counts = Counter(index for index, _ in keys)
    weights = np.asarray([1.0 / counts[index] for index, _ in keys], dtype=np.float64)
    weights *= len(keys) / weights.sum()
    return tuple(float(value) for value in weights)


def weighted_scaler(
    features: object, weights: object
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Weighted population mean/std of supplied prefix only; zero std -> one."""
    x = _real_array(features, "features")
    if x.ndim != 2 or len(x) == 0 or x.shape[1] not in VIEW_WIDTHS.values():
        raise ValueError("fixed_nonempty_feature_geometry_required")
    w = _vector(weights, len(x), "weights")
    if not (w > 0).all():
        raise ValueError("strictly_positive_weights_required")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            mean = (x * w[:, None]).sum(axis=0) / w.sum()
            mean = np.where(np.all(x == x[0], axis=0), x[0], mean)
            variance = ((x - mean) ** 2 * w[:, None]).sum(axis=0) / w.sum()
            scale = np.sqrt(variance)
            scale = np.where(scale == 0, 1.0, scale)
    except FloatingPointError:
        raise ValueError("nonfinite_weighted_scaler") from None
    if not np.isfinite(mean).all() or not np.isfinite(scale).all():
        raise ValueError("nonfinite_weighted_scaler")
    return tuple(float(value) for value in mean), tuple(float(value) for value in scale)


def _cutoff(value: int) -> int:
    if type(value) is not int or not 61 <= value < core.SESSION_COUNT:
        raise ValueError("training_prefix_cutoff_required")
    return value


@dataclass(frozen=True, slots=True)
class RidgeModel:
    view: str
    fit_target_cutoff: int
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    training_row_count: int
    training_date_count: int

    def __post_init__(self) -> None:
        width = _width(self.view)
        _cutoff(self.fit_target_cutoff)
        for name in ("mean", "scale", "coefficients"):
            array = _vector(getattr(self, name), width, name)
            if name == "scale" and not (array > 0).all():
                raise ValueError("strictly_positive_scale_required")
            object.__setattr__(self, name, tuple(float(value) for value in array))
        object.__setattr__(self, "intercept", float(_vector([self.intercept], 1, "intercept")[0]))
        if (
            type(self.training_row_count) is not int
            or type(self.training_date_count) is not int
            or not 1 <= self.training_date_count <= self.training_row_count
        ):
            raise ValueError("training_counts_required")

    def predict(self, features: object) -> tuple[float, ...]:
        """Apply frozen scaling; caller binds chronology across different calendars."""
        x = _matrix(features, _width(self.view))
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                scores = ((x - self.mean) / self.scale) @ self.coefficients + self.intercept
        except FloatingPointError:
            raise ValueError("nonfinite_ridge_prediction") from None
        if not np.isfinite(scores).all():
            raise ValueError("nonfinite_ridge_prediction")
        return tuple(float(value) for value in scores)


def fit_ridge(
    features: object,
    labels: object,
    *,
    row_keys: Sequence[RowKey],
    fit_target_cutoff: int,
    view: str,
) -> RidgeModel:
    """Fit sum(w*error^2) + alpha1*||coef||^2, with an unpenalized intercept.

    Date-balanced weights sum to N, not one: the penalty's scale is explicit.
    Future rows reject rather than silently enter or get filtered from a fit.
    Numpy's augmented least-squares solver avoids custom optimization and normal
    equations. No evaluation features/labels enter scaling or model selection.
    The caller uses training_labels to reject peer-incomplete dates as a whole.
    """
    cutoff = _cutoff(fit_target_cutoff)
    width = _width(view)
    keys = _row_keys(row_keys)
    if any(index > cutoff for index, _ in keys):
        raise ValueError("training_row_after_prefix_cutoff")
    x = _matrix(features, width)
    if len(x) != len(keys):
        raise ValueError("training_rows_must_match_identities")
    y = _vector(labels, len(keys), "labels")
    order = sorted(range(len(keys)), key=keys.__getitem__)
    x, y = x[order], y[order]
    keys = tuple(keys[index] for index in order)
    weights = np.asarray(date_balanced_weights(keys))
    mean, scale = weighted_scaler(x, weights)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
            root_weights = np.sqrt(weights)
            penalty = np.diag([0.0, *([math.sqrt(RIDGE_ALPHA)] * width)])
            augmented = np.vstack((design * root_weights[:, None], penalty))
            targets = np.concatenate((y * root_weights, np.zeros(width + 1)))
            solution, _, rank, _ = np.linalg.lstsq(augmented, targets, rcond=None)
    except (FloatingPointError, np.linalg.LinAlgError):
        raise ValueError("ridge_numerical_failure") from None
    if rank != width + 1 or not np.isfinite(solution).all():
        raise ValueError("ridge_numerical_failure")
    return RidgeModel(
        view,
        cutoff,
        mean,
        scale,
        tuple(float(value) for value in solution[1:]),
        float(solution[0]),
        len(keys),
        len({index for index, _ in keys}),
    )

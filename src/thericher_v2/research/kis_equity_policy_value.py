"""Pure participation/value prototype; callbacks and identity bindings are caller-owned.

Only completed prior-61 bars determine eligibility. Their last20 log ON/ID
components supply a shared cohort context. Targets are logical future reads
after every fixed basket is sealed; no loading, persistence or broker access.
Nominal clocks do not establish historical observation/finality or Paper parity.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np

from thericher_v2.research import kis_equity_rule_fusion as fusion
from thericher_v2.research import kis_pooled_equity_components as core

EXPERTS = (*fusion.EXPERTS, fusion.UNIFORM_POLICY)
ACTIONS = (*EXPERTS, "cash")
CHANNELS = ("log_overnight", "log_intraday")
CONTEXT_STEPS = 20
PRIMARY_BPS = 10
ROUND_TRIP_BPS = core.ROUND_TRIP_BPS
RIDGE_ALPHA = 1.0
FIT_CUTOFFS = (427, 609, 799)
OOF_FOLDS = fusion.OOF_FOLDS
FINAL_FIT_ENTRIES = fusion.FINAL_FIT_ENTRIES
CURRENT_ENTRIES = tuple(range(761, 800))
MODES = ("joint", "participation_only")
Context = tuple[tuple[float, float], ...]


def cohort_context(state: core.EligibilitySnapshot) -> Context | None:
    """Equal-weight log ON/ID means over the SAME decision-eligible keys at every step."""
    if not isinstance(state, core.EligibilitySnapshot):
        raise ValueError("bound_eligibility_snapshot_required")
    if not state.rows:
        return None
    count = len(state.rows)
    return tuple(
        tuple(
            math.fsum(row.components[channel][step] / count for row in state.rows)
            for channel in range(len(CHANNELS))
        )
        for step in range(CONTEXT_STEPS)
    )


def seal_experts(state: core.EligibilitySnapshot) -> Mapping[str, core.PredictionSeal]:
    """Freeze exactly five fixed top10 baskets without a target callback."""
    inputs = fusion.FusionInputs(state)
    policies = fusion.seal_predictions(inputs)
    return MappingProxyType({name: policies[name] for name in EXPERTS})


@dataclass(frozen=True, slots=True)
class ParticipationInputs:
    snapshot: core.EligibilitySnapshot
    context: Context | None = field(init=False)
    seals: Mapping[str, core.PredictionSeal] = field(init=False)
    cash_seal: core.PredictionSeal = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", cohort_context(self.snapshot))
        object.__setattr__(self, "seals", seal_experts(self.snapshot))
        object.__setattr__(
            self,
            "cash_seal",
            core.seal(self.snapshot, [0.0] * len(self.snapshot.rows), allocation="cash"),
        )

    @property
    def eligible_keys(self) -> tuple[str, ...]:
        return self.snapshot.eligible_keys

    @property
    def unavailable_keys(self) -> tuple[str, ...]:
        return self.snapshot.unavailable_keys


def snapshot(
    plan: core.ComponentPlan, entry_index: int, past_source: core.PastSource
) -> ParticipationInputs:
    return ParticipationInputs(core.snapshot(plan, entry_index, past_source))


@dataclass(frozen=True, slots=True)
class JointLabels:
    inputs: ParticipationInputs
    replays: tuple[core.DayReplay, ...]
    values: tuple[float, ...] | None = field(init=False)
    missing_selected: tuple[str, ...] = field(init=False)

    def __post_init__(self) -> None:
        replays = tuple(self.replays)
        if len(replays) != len(EXPERTS) or any(
            not isinstance(day, core.DayReplay)
            or day.seal != self.inputs.seals[name]
            or day.round_trip_bps != PRIMARY_BPS
            for name, day in zip(EXPERTS, replays, strict=True)
        ):
            raise ValueError("five_primary_basket_labels_required")
        values = None
        if all(day.complete for day in replays):
            values = tuple(
                float(value)
                for value in _vector([day.net_return for day in replays], len(EXPERTS), "labels")
            )
        object.__setattr__(self, "replays", replays)
        object.__setattr__(self, "values", values)
        object.__setattr__(
            self,
            "missing_selected",
            tuple(sorted({key for day in replays for key in day.missing_selected})),
        )

    @property
    def complete(self) -> bool:
        return self.values is not None

    @property
    def available_at(self):
        return self.inputs.snapshot.target_close_at


def joint_labels(inputs: ParticipationInputs, target_source: core.TargetSource) -> JointLabels:
    """Read the selected-key union once, AFTER all five baskets have been sealed.

    A missing/invalid selected payoff invalidates the whole five-output date.
    Unselected peers never determine labels or retroactively change eligibility.
    Fewer10 produces five analytical-flat zero labels without target reads;
    an empty cohort has no context and cannot supply a model training row.
    """
    selected = tuple(sorted({key for name in EXPERTS for key in inputs.seals[name].selected_keys}))
    session = inputs.snapshot.entry_session
    targets = {key: target_source(key, session) for key in selected}

    def cached(key, day):
        if day != session or key not in targets:
            raise ValueError("sealed_target_binding")
        return targets[key]

    return JointLabels(
        inputs,
        tuple(
            core.replay_day(inputs.seals[name], cached, round_trip_bps=PRIMARY_BPS)
            for name in EXPERTS
        ),
    )


def _vector(value: object, size: int, name: str) -> np.ndarray:
    array = fusion._real_array(value, name)
    if array.shape != (size,):
        raise ValueError(f"{name}_geometry_required")
    return array


def _contexts(value: object) -> np.ndarray:
    array = fusion._real_array(value, "contexts")
    if array.shape == (0,):
        array = array.reshape(0, CONTEXT_STEPS, len(CHANNELS))
    if array.ndim != 3 or array.shape[1:] != (CONTEXT_STEPS, len(CHANNELS)):
        raise ValueError("context_geometry_N20x2_required")
    return array


def _labels(value: object, count: int) -> np.ndarray:
    array = fusion._real_array(value, "labels")
    if array.shape != (count, len(EXPERTS)):
        raise ValueError("joint_labels_geometry_Nx5_required")
    return array


def _entries(value: Sequence[int]) -> tuple[int, ...]:
    entries = tuple(value)
    if not entries or any(type(i) is not int or not 61 <= i < 800 for i in entries):
        raise ValueError("training_date_identity_required")
    if len(set(entries)) != len(entries):
        raise ValueError("one_row_per_training_date_required")
    return entries


def _prefix(contexts, entry_indices, fit_target_cutoff):
    if type(fit_target_cutoff) is not int or fit_target_cutoff not in FIT_CUTOFFS:
        raise ValueError("fixed_prefix_cutoff_required")
    entries = _entries(entry_indices)
    if any(index > fit_target_cutoff for index in entries):
        raise ValueError("training_date_after_prefix_cutoff")
    x = _contexts(contexts)
    if len(x) != len(entries):
        raise ValueError("contexts_must_match_training_dates")
    order = sorted(range(len(entries)), key=entries.__getitem__)
    return x[order], tuple(entries[i] for i in order), order


@dataclass(frozen=True, slots=True)
class PrefixScaler:
    fit_target_cutoff: int
    entry_indices: tuple[int, ...]
    mean: tuple[float, float]
    scale: tuple[float, float]

    def __post_init__(self) -> None:
        entries = _entries(self.entry_indices)
        if (
            type(self.fit_target_cutoff) is not int
            or self.fit_target_cutoff not in FIT_CUTOFFS
            or entries != tuple(sorted(entries))
            or entries[-1] > self.fit_target_cutoff
        ):
            raise ValueError("scaler_prefix_binding")
        object.__setattr__(self, "entry_indices", entries)
        for name in ("mean", "scale"):
            array = _vector(getattr(self, name), len(CHANNELS), name)
            if name == "scale" and not (array > 0).all():
                raise ValueError("positive_channel_scale_required")
            object.__setattr__(self, name, tuple(float(value) for value in array))

    @property
    def training_date_count(self) -> int:
        return len(self.entry_indices)

    def transform(self, contexts: object) -> np.ndarray:
        """Fresh N20x2 array; channel statistics are shared across all20 steps."""
        x = _contexts(contexts)
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                result = (x - self.mean) / self.scale
        except FloatingPointError:
            raise ValueError("nonfinite_scaled_context") from None
        if not np.isfinite(result).all():
            raise ValueError("nonfinite_scaled_context")
        return result


def prefix_scaler(
    contexts: object, *, entry_indices: Sequence[int], fit_target_cutoff: int
) -> PrefixScaler:
    """One row/date, uniform date weight1 (sum=N), population channel std over N*20."""
    x, entries, _ = _prefix(contexts, entry_indices, fit_target_cutoff)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            values = x.reshape(-1, len(CHANNELS))
            mean = values.mean(axis=0)
            # Exact constants avoid a roundoff-only variance for nonbinary floats.
            mean = np.where(np.all(values == values[0], axis=0), values[0], mean)
            scale = np.sqrt(((values - mean) ** 2).mean(axis=0))
            scale = np.where(scale == 0, 1.0, scale)
    except FloatingPointError:
        raise ValueError("nonfinite_prefix_scaler") from None
    return PrefixScaler(fit_target_cutoff, entries, tuple(mean), tuple(scale))


@dataclass(frozen=True, slots=True)
class RidgeModel:
    scaler: PrefixScaler
    coefficients: tuple[tuple[float, ...], ...]
    intercept: tuple[float, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scaler, PrefixScaler):
            raise ValueError("prefix_scaler_required")
        coefficients = _labels(self.coefficients, CONTEXT_STEPS * len(CHANNELS))
        object.__setattr__(
            self,
            "coefficients",
            tuple(tuple(float(value) for value in row) for row in coefficients),
        )
        object.__setattr__(
            self,
            "intercept",
            tuple(float(value) for value in _vector(self.intercept, len(EXPERTS), "intercept")),
        )

    @property
    def fit_target_cutoff(self) -> int:
        return self.scaler.fit_target_cutoff

    @property
    def training_date_count(self) -> int:
        return self.scaler.training_date_count

    @property
    def training_row_count(self) -> int:
        return self.training_date_count

    @property
    def mean(self) -> tuple[float, float]:
        return self.scaler.mean

    @property
    def scale(self) -> tuple[float, float]:
        return self.scaler.scale

    def predict(self, contexts: object) -> tuple[tuple[float, ...], ...]:
        """N20x2 or interleaved N40; both apply the exact same two-channel scaler."""
        raw = fusion._real_array(contexts, "contexts")
        if raw.ndim == 2 and raw.shape[1] == CONTEXT_STEPS * len(CHANNELS):
            raw = raw.reshape(len(raw), CONTEXT_STEPS, len(CHANNELS))
        scaled = self.scaler.transform(raw)
        x = scaled.reshape(len(scaled), CONTEXT_STEPS * len(CHANNELS))
        try:
            with np.errstate(over="raise", invalid="raise"):
                values = x @ self.coefficients + self.intercept
        except FloatingPointError:
            raise ValueError("nonfinite_ridge_prediction") from None
        if not np.isfinite(values).all():
            raise ValueError("nonfinite_ridge_prediction")
        return tuple(tuple(float(value) for value in row) for row in values)


def fit_ridge(
    contexts: object,
    labels: object,
    *,
    entry_indices: Sequence[int],
    fit_target_cutoff: int,
) -> RidgeModel:
    """ONE five-output lstsq fit: sum(date errors^2) + alpha1*sum(coef^2).

    Intercepts are unpenalized. Flattening is chronological step-major ON,ID.
    Caller supplies complete JointLabels.values rows and may reuse model.scaler
    unchanged for the external GRU; no evaluation window enters these stats.
    """
    x, entries, order = _prefix(contexts, entry_indices, fit_target_cutoff)
    y = _labels(labels, len(entries))[order]
    scaler = prefix_scaler(x, entry_indices=entries, fit_target_cutoff=fit_target_cutoff)
    width = CONTEXT_STEPS * len(CHANNELS)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            design = np.column_stack((np.ones(len(x)), scaler.transform(x).reshape(len(x), width)))
            penalty = np.diag([0.0, *([math.sqrt(RIDGE_ALPHA)] * width)])
            augmented = np.vstack((design, penalty))
            targets = np.vstack((y, np.zeros((width + 1, len(EXPERTS)))))
            solution, _, rank, _ = np.linalg.lstsq(augmented, targets, rcond=None)
    except (FloatingPointError, np.linalg.LinAlgError):
        raise ValueError("ridge_numerical_failure") from None
    if rank != width + 1 or not np.isfinite(solution).all():
        raise ValueError("ridge_numerical_failure")
    return RidgeModel(scaler, tuple(map(tuple, solution[1:])), tuple(solution[0]))


@dataclass(frozen=True, slots=True)
class ActionSeal:
    inputs: ParticipationInputs
    predicted_net: tuple[float, ...]
    mode: str
    action: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, ParticipationInputs) or self.mode not in MODES:
            raise ValueError("bound_participation_action_required")
        predictions = tuple(
            float(value) for value in _vector(self.predicted_net, len(EXPERTS), "predicted_net")
        )
        action = "cash"
        if len(self.inputs.eligible_keys) >= core.TOP_K:
            if self.mode == "participation_only":
                if predictions[-1] > 0:
                    action = fusion.UNIFORM_POLICY
            else:
                best = min(range(len(EXPERTS)), key=lambda i: (-predictions[i], EXPERTS[i]))
                if predictions[best] > 0:
                    action = EXPERTS[best]
        object.__setattr__(self, "predicted_net", predictions)
        object.__setattr__(self, "action", action)

    @property
    def seal(self) -> core.PredictionSeal:
        return self.inputs.cash_seal if self.action == "cash" else self.inputs.seals[self.action]


def seal_actions(
    inputs: Sequence[ParticipationInputs],
    predicted_net: object,
    *,
    expected_entries: Sequence[int] = CURRENT_ENTRIES,
) -> Mapping[str, tuple[ActionSeal, ...]]:
    """Freeze BOTH action paths for EVERY expected date before caller replays any.

    Default is all39 current entries, including empty/unavailable cohorts. Pass
    an explicit chronological OOF range for a different scoring segment.
    """
    states, expected = tuple(inputs), _entries(expected_entries)
    if (
        expected != tuple(sorted(expected))
        or any(not isinstance(state, ParticipationInputs) for state in states)
        or tuple(state.snapshot.entry_index for state in states) != expected
    ):
        raise ValueError("all_expected_action_dates_required")
    predictions = _labels(predicted_net, len(states))
    return MappingProxyType(
        {
            mode: tuple(
                ActionSeal(state, tuple(row), mode)
                for state, row in zip(states, predictions, strict=True)
            )
            for mode in MODES
        }
    )


def replay_action(
    action: ActionSeal, target_source: core.TargetSource, *, round_trip_bps: int = PRIMARY_BPS
) -> core.DayReplay:
    """Replay the frozen basket, never replace a missing payoff or rethreshold at stress cost."""
    if not isinstance(action, ActionSeal):
        raise ValueError("sealed_participation_action_required")
    return core.replay_day(action.seal, target_source, round_trip_bps=round_trip_bps)

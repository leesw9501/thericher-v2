"""Fixed supplied-expert conjunction on original TCN slots; no execution or fitting."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_score_replay as score


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _snapshot(snapshot: core.EligibilitySnapshot) -> core.EligibilitySnapshot:
    _require(type(snapshot) is core.EligibilitySnapshot, "eligibility_snapshot_required")
    return core.EligibilitySnapshot(
        snapshot.entry_index,
        snapshot.decision_session,
        snapshot.entry_session,
        tuple(
            core.FeatureRow(row.key, row.components, row.momentum, row.component_score)
            for row in snapshot.rows
        ),
        snapshot.unavailable_keys,
        snapshot.decision_at,
        snapshot.entry_open_at,
        snapshot.target_close_at,
    )


@dataclass(frozen=True, slots=True, repr=False)
class ExpertValuesSeal:
    snapshot: core.EligibilitySnapshot
    kind: str
    values: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot", _snapshot(self.snapshot))
        _require(type(self.kind) is str and self.kind in ("binary60", "signed60"), "expert_kind")
        _require(
            type(self.values) is tuple
            and all(type(pair) is tuple and len(pair) == 2 for pair in self.values)
            and tuple(key for key, _ in self.values) == self.snapshot.eligible_keys,
            "expert_exact_ordered_peers_required",
        )
        _require(
            all(type(value) is float and math.isfinite(value) for _, value in self.values),
            "finite_float_expert_values_required",
        )
        _require(
            self.kind != "binary60" or all(0 <= value <= 1 for _, value in self.values),
            "binary_probability_range",
        )


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ConjunctionMask:
    baseline: score.ScoreSeal
    weights: tuple[tuple[str, Fraction], ...] | None

    def __init__(
        self,
        baseline: score.ScoreSeal,
        binary: ExpertValuesSeal,
        signed: ExpertValuesSeal,
    ) -> None:
        _require(
            type(baseline) is score.ScoreSeal and baseline.arm == "tcn20",
            "original_tcn20_seal_required",
        )
        owned = score.ScoreSeal(
            _snapshot(baseline.snapshot),
            baseline.arm,
            baseline.owned_keys,
            baseline.scores,
            baseline.ranked_keys,
            baseline.weights,
        )
        _require(
            type(binary) is ExpertValuesSeal and type(signed) is ExpertValuesSeal,
            "bound_expert_seals_required",
        )
        binary = ExpertValuesSeal(binary.snapshot, binary.kind, binary.values)
        signed = ExpertValuesSeal(signed.snapshot, signed.kind, signed.values)
        _require(binary.kind == "binary60" and signed.kind == "signed60", "expert_kind_binding")
        _require(
            binary.snapshot == signed.snapshot == owned.snapshot,
            "expert_snapshot_binding",
        )
        probabilities, payoffs = dict(binary.values), dict(signed.values)
        weights = (
            None
            if owned.weights is None
            else tuple(
                (key, weight)
                for key, weight in owned.weights
                if probabilities[key] > 0.5 and payoffs[key] > 0
            )
        )
        object.__setattr__(self, "baseline", owned)
        object.__setattr__(self, "weights", weights)

    def safe_facts(self) -> dict[str, str | int | bool | None]:
        return {
            "status": "input_unavailable" if self.weights is None else "complete",
            "reason": (
                self.baseline.reason if self.weights is None else "fixed_expert_conjunction"
            ),
            "eligible_count": len(self.baseline.snapshot.eligible_keys),
            "original_slot_count": len(self.baseline.weights or ()),
            "accepted_slot_count": None if self.weights is None else len(self.weights),
            "all_cash": None if self.weights is None else not self.weights,
            "reranked": False,
            "redistributed": False,
            "resized": False,
        }


def conjoin_experts(
    baseline: score.ScoreSeal,
    binary: ExpertValuesSeal,
    signed: ExpertValuesSeal,
) -> ConjunctionMask:
    """Keep an original slot iff binary>0.5 AND signed>0; None remains KEEP.

    Weights remain in the ScoreSeal's original units. Exposure scaling and
    original-quantity-or-zero accounting are caller-owned, never recomputed here.
    """
    return ConjunctionMask(baseline, binary, signed)

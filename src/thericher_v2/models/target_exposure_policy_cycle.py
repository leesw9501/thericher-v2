"""Pure same-cycle composition of target policy and portfolio allocation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from thericher_v2.contracts import (
    ModelPrediction,
    TargetExposureProposal,
    decimal_value,
    require_utc,
)
from thericher_v2.models.sequence_window import CausalMultiTimeframeSequenceWindow
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
)
from thericher_v2.models.target_exposure_cycle_allocator import (
    TargetExposureAllocationCycleEntry,
    allocate_target_exposure_cycle,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    propose_target_exposure,
)


@dataclass(frozen=True)
class TargetExposurePolicyCycleEntry:
    """Caller-owned inputs for one symbol in a shared decision cycle."""

    eligibility: OpportunityEligibility
    predictions: Sequence[ModelPrediction]
    current_exposure: Decimal | int | str
    allocation: TargetExposureAllocationInput
    causal_window: CausalMultiTimeframeSequenceWindow | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.eligibility, OpportunityEligibility):
            raise TypeError("eligibility must be an OpportunityEligibility")
        if not isinstance(self.allocation, TargetExposureAllocationInput):
            raise TypeError("allocation must be a TargetExposureAllocationInput")
        if self.causal_window is not None and not isinstance(
            self.causal_window, CausalMultiTimeframeSequenceWindow
        ):
            raise TypeError("causal_window must be a CausalMultiTimeframeSequenceWindow")

        predictions = tuple(self.predictions)
        if any(not isinstance(prediction, ModelPrediction) for prediction in predictions):
            raise TypeError("predictions must contain ModelPrediction values")
        current_exposure = decimal_value(self.current_exposure, "current_exposure")
        if not Decimal("0") <= current_exposure <= Decimal("1"):
            raise ValueError("current_exposure must be between 0 and 1")
        if current_exposure != self.allocation.current_symbol_exposure:
            raise ValueError("current_exposure must match allocation current_symbol_exposure")

        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "current_exposure", current_exposure)


@dataclass(frozen=True)
class TargetExposurePolicyCycleOutcome:
    """The pre-allocation policy state and its final allocation state."""

    policy_proposal: TargetExposureProposal
    allocated_proposal: TargetExposureProposal

    def __post_init__(self) -> None:
        if not isinstance(self.policy_proposal, TargetExposureProposal):
            raise TypeError("policy_proposal must be a TargetExposureProposal")
        if not isinstance(self.allocated_proposal, TargetExposureProposal):
            raise TypeError("allocated_proposal must be a TargetExposureProposal")
        if (
            self.policy_proposal.symbol != self.allocated_proposal.symbol
            or self.policy_proposal.market != self.allocated_proposal.market
            or self.policy_proposal.feature_schema_id != self.allocated_proposal.feature_schema_id
            or self.policy_proposal.decided_at != self.allocated_proposal.decided_at
        ):
            raise ValueError("policy and allocation proposals must share one identity")


def evaluate_target_exposure_policy_cycle(
    entries: Sequence[TargetExposurePolicyCycleEntry],
    *,
    policy_config: TargetPositionPolicyConfig,
    allocation_config: TargetExposureAllocationConfig,
    as_of: datetime,
) -> tuple[TargetExposurePolicyCycleOutcome, ...]:
    """Evaluate caller order through existing policy and allocation contracts.

    The helper neither ranks symbols nor reserves capital. It keeps each
    policy-level proposal alongside the serially allocated target so later
    attribution can distinguish a trade-policy decision from a capacity cap.
    """

    if not isinstance(entries, Sequence):
        raise TypeError("entries must be a sequence")
    if not isinstance(policy_config, TargetPositionPolicyConfig):
        raise TypeError("policy_config must be a TargetPositionPolicyConfig")
    if not isinstance(allocation_config, TargetExposureAllocationConfig):
        raise TypeError("allocation_config must be a TargetExposureAllocationConfig")
    now = require_utc(as_of, "as_of")
    cycle_entries = tuple(entries)
    if any(not isinstance(entry, TargetExposurePolicyCycleEntry) for entry in cycle_entries):
        raise TypeError("entries must contain TargetExposurePolicyCycleEntry values")

    policy_proposals = tuple(
        propose_target_exposure(
            entry.eligibility,
            entry.predictions,
            current_exposure=entry.current_exposure,
            config=policy_config,
            as_of=now,
            causal_window=entry.causal_window,
        )
        for entry in cycle_entries
    )
    allocated_proposals = allocate_target_exposure_cycle(
        tuple(
            TargetExposureAllocationCycleEntry(
                proposal=proposal,
                allocation=entry.allocation,
            )
            for proposal, entry in zip(policy_proposals, cycle_entries, strict=True)
        ),
        config=allocation_config,
        as_of=now,
    )
    return tuple(
        TargetExposurePolicyCycleOutcome(
            policy_proposal=policy_proposal,
            allocated_proposal=allocated_proposal,
        )
        for policy_proposal, allocated_proposal in zip(
            policy_proposals,
            allocated_proposals,
            strict=True,
        )
    )

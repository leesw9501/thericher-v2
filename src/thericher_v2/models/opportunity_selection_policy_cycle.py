"""Pure composition of source-attested selection, policy, and allocation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from thericher_v2.contracts import ModelPrediction, decimal_value
from thericher_v2.models.opportunity_selection import (
    OpportunitySelectionConfig,
    OpportunitySelectionContext,
    OpportunitySelectionEntry,
    OpportunitySelectionOutcome,
    select_source_attested_opportunities,
)
from thericher_v2.models.sequence_window import CausalMultiTimeframeSequenceWindow
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
)
from thericher_v2.models.target_exposure_policy_cycle import (
    TargetExposurePolicyCycleEntry,
    TargetExposurePolicyCycleOutcome,
    evaluate_target_exposure_policy_cycle,
)
from thericher_v2.models.target_position_policy import TargetPositionPolicyConfig


@dataclass(frozen=True)
class OpportunitySelectionPolicyCycleEntry:
    """One candidate's selection evidence plus downstream policy inputs."""

    selection_entry: OpportunitySelectionEntry
    predictions: Sequence[ModelPrediction]
    current_exposure: Decimal | int | str
    allocation: TargetExposureAllocationInput
    causal_window: CausalMultiTimeframeSequenceWindow | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.selection_entry, OpportunitySelectionEntry):
            raise TypeError("selection_entry must be an OpportunitySelectionEntry")
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
            raise ValueError("current_exposure must be between zero and one")
        if current_exposure != self.allocation.current_symbol_exposure:
            raise ValueError("current_exposure must match allocation current_symbol_exposure")
        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "current_exposure", current_exposure)

    @property
    def identity(self) -> tuple[str, str]:
        return self.selection_entry.identity


@dataclass(frozen=True)
class OpportunitySelectionPolicyCycleOutcome:
    """Preserve selection, per-symbol policy, and capacity results separately."""

    selection_outcome: OpportunitySelectionOutcome
    policy_cycle_outcome: TargetExposurePolicyCycleOutcome | None

    def __post_init__(self) -> None:
        if not isinstance(self.selection_outcome, OpportunitySelectionOutcome):
            raise TypeError("selection_outcome must be an OpportunitySelectionOutcome")
        if self.selection_outcome.selected != (self.policy_cycle_outcome is not None):
            raise ValueError("only selected outcomes can have a policy cycle outcome")
        if self.policy_cycle_outcome is not None:
            if not isinstance(self.policy_cycle_outcome, TargetExposurePolicyCycleOutcome):
                raise TypeError("policy_cycle_outcome must be a TargetExposurePolicyCycleOutcome")
            market, symbol = self.selection_outcome.entry.identity
            if (
                self.policy_cycle_outcome.policy_proposal.market != market
                or self.policy_cycle_outcome.policy_proposal.symbol != symbol
            ):
                raise ValueError("selection and policy cycle outcomes must share one identity")


def evaluate_opportunity_selection_policy_cycle(
    entries: Sequence[OpportunitySelectionPolicyCycleEntry],
    *,
    selection_config: OpportunitySelectionConfig,
    selection_context: OpportunitySelectionContext,
    policy_config: TargetPositionPolicyConfig,
    allocation_config: TargetExposureAllocationConfig,
) -> tuple[OpportunitySelectionPolicyCycleOutcome, ...]:
    """Run a frozen ranking before per-symbol policy and capacity allocation.

    The returned tuple retains one selection result for every input.  Only the
    selected subset enters the existing target-policy/allocation cycle, in
    deterministic selection-rank order.  This makes selection exclusion,
    policy abstention, and allocation capacity effects independently visible.
    """

    if not isinstance(entries, Sequence):
        raise TypeError("entries must be a sequence")
    if not isinstance(selection_config, OpportunitySelectionConfig):
        raise TypeError("selection_config must be an OpportunitySelectionConfig")
    if not isinstance(selection_context, OpportunitySelectionContext):
        raise TypeError("selection_context must be an OpportunitySelectionContext")
    if not isinstance(policy_config, TargetPositionPolicyConfig):
        raise TypeError("policy_config must be a TargetPositionPolicyConfig")
    if not isinstance(allocation_config, TargetExposureAllocationConfig):
        raise TypeError("allocation_config must be a TargetExposureAllocationConfig")
    cycle_entries = tuple(entries)
    if any(not isinstance(entry, OpportunitySelectionPolicyCycleEntry) for entry in cycle_entries):
        raise TypeError("entries must contain OpportunitySelectionPolicyCycleEntry values")

    selection_outcomes = select_source_attested_opportunities(
        tuple(entry.selection_entry for entry in cycle_entries),
        config=selection_config,
        context=selection_context,
    )
    entries_by_identity = {entry.identity: entry for entry in cycle_entries}
    selected_outcomes = tuple(
        sorted(
            (outcome for outcome in selection_outcomes if outcome.selected),
            key=lambda outcome: outcome.selection_rank,
        )
    )
    policy_outcomes = evaluate_target_exposure_policy_cycle(
        tuple(
            TargetExposurePolicyCycleEntry(
                source_eligibility=entries_by_identity[outcome.entry.identity]
                .selection_entry.source_eligibility,
                predictions=entries_by_identity[outcome.entry.identity].predictions,
                current_exposure=entries_by_identity[outcome.entry.identity].current_exposure,
                allocation=entries_by_identity[outcome.entry.identity].allocation,
                causal_window=entries_by_identity[outcome.entry.identity].causal_window,
            )
            for outcome in selected_outcomes
        ),
        policy_config=policy_config,
        allocation_config=allocation_config,
        as_of=selection_context.as_of,
    )
    policy_by_identity = {
        (outcome.policy_proposal.market, outcome.policy_proposal.symbol): outcome
        for outcome in policy_outcomes
    }
    return tuple(
        OpportunitySelectionPolicyCycleOutcome(
            selection_outcome=outcome,
            policy_cycle_outcome=policy_by_identity.get(outcome.entry.identity),
        )
        for outcome in selection_outcomes
    )

"""Pure cohort-level lineage for selected policy and allocation outcomes.

The lineage reference is deliberately not an execution binding.  It lets a
caller preserve the complete source-attested selection cohort when forwarding
one selected target proposal to the existing immutable decision-receipt path.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from thericher_v2.models.opportunity_selection import (
    OpportunitySelectionConfig,
    OpportunitySelectionContext,
    select_source_attested_opportunities,
)
from thericher_v2.models.opportunity_selection_policy_cycle import (
    OpportunitySelectionPolicyCycleOutcome,
)

SELECTION_POLICY_LINEAGE_SCHEMA_ID = "selection-policy-lineage-v1"
_OPAQUE_REFERENCE: Final = re.compile(r"ref:[0-9a-f]{32,128}", re.ASCII)


@dataclass(frozen=True)
class SelectionPolicyProposalLineage:
    """Safe lineage references for one selected target proposal."""

    cohort_ref: str
    proposal_ref: str
    selection_ref: str
    selection_rank: int
    symbol: str
    market: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.cohort_ref, "cohort_ref"),
            (self.proposal_ref, "proposal_ref"),
            (self.selection_ref, "selection_ref"),
        ):
            if _OPAQUE_REFERENCE.fullmatch(value) is None:
                raise ValueError(f"{name} must be an opaque reference")
        if type(self.selection_rank) is not int or self.selection_rank <= 0:
            raise ValueError("selection_rank must be a positive integer")
        if not self.symbol.strip() or not self.market.strip():
            raise ValueError("lineage symbol and market must be nonempty")
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "market", self.market.upper())


def build_selected_selection_policy_proposal_lineage(
    outcomes: Sequence[OpportunitySelectionPolicyCycleOutcome],
    *,
    selection_config: OpportunitySelectionConfig,
    selection_context: OpportunitySelectionContext,
    symbol: str,
    market: str,
) -> SelectionPolicyProposalLineage:
    """Build a selected proposal reference after replaying the full cohort.

    This proves only the exact candidate field supplied by the caller.  It
    cannot prove that field was the whole historical universe or that scores
    are predictive.  The full selection result is recomputed first, which
    binds the selector, score schema, thresholds, common source context, and
    peer ordering rather than trusting a one-row rank assertion.
    """

    if not isinstance(outcomes, Sequence):
        raise TypeError("outcomes must be a sequence")
    if not isinstance(selection_config, OpportunitySelectionConfig):
        raise TypeError("selection_config must be an OpportunitySelectionConfig")
    if not isinstance(selection_context, OpportunitySelectionContext):
        raise TypeError("selection_context must be an OpportunitySelectionContext")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be nonempty")
    if not isinstance(market, str) or not market.strip():
        raise ValueError("market must be nonempty")
    cycle_outcomes = tuple(outcomes)
    if any(
        not isinstance(outcome, OpportunitySelectionPolicyCycleOutcome)
        for outcome in cycle_outcomes
    ):
        raise TypeError("outcomes must contain OpportunitySelectionPolicyCycleOutcome values")

    selection_outcomes = tuple(outcome.selection_outcome for outcome in cycle_outcomes)
    expected_selection = select_source_attested_opportunities(
        tuple(outcome.entry for outcome in selection_outcomes),
        config=selection_config,
        context=selection_context,
    )
    if selection_outcomes != expected_selection:
        raise ValueError("selection outcomes must match deterministic cohort recomputation")

    target_identity = market.upper(), symbol.upper()
    matching = tuple(
        outcome
        for outcome in cycle_outcomes
        if outcome.selection_outcome.entry.identity == target_identity
    )
    if len(matching) != 1:
        raise ValueError("selected identity must occur exactly once in the cohort")
    selected = matching[0]
    if not selected.selection_outcome.selected:
        raise ValueError("lineage is available only for a selected outcome")
    if selected.policy_cycle_outcome is None:
        raise ValueError("selected outcome must retain a policy cycle outcome")

    cohort_ref = _cohort_ref(
        cycle_outcomes,
        selection_config=selection_config,
        selection_context=selection_context,
    )
    policy_outcome = selected.policy_cycle_outcome
    proposal_ref = _opaque_reference(
        kind="selection_policy_proposal_lineage_v1",
        payload={
            "cohort_ref": cohort_ref,
            "selection_ref": selected.selection_outcome.entry.selection_ref,
            "selection_rank": selected.selection_outcome.selection_rank,
            "policy_proposal_id": policy_outcome.policy_proposal.proposal_id,
            "allocated_proposal_id": policy_outcome.allocated_proposal.proposal_id,
            "symbol": target_identity[1],
            "market": target_identity[0],
        },
    )
    return SelectionPolicyProposalLineage(
        cohort_ref=cohort_ref,
        proposal_ref=proposal_ref,
        selection_ref=selected.selection_outcome.entry.selection_ref,
        selection_rank=selected.selection_outcome.selection_rank,
        symbol=target_identity[1],
        market=target_identity[0],
    )


def _cohort_ref(
    outcomes: tuple[OpportunitySelectionPolicyCycleOutcome, ...],
    *,
    selection_config: OpportunitySelectionConfig,
    selection_context: OpportunitySelectionContext,
) -> str:
    return _opaque_reference(
        kind="selection_policy_cohort_lineage_v1",
        payload={
            "schema_id": SELECTION_POLICY_LINEAGE_SCHEMA_ID,
            "selector_id": selection_config.selector_id,
            "score_schema_id": selection_config.score_schema_id,
            "maximum_selected": selection_config.maximum_selected,
            "minimum_score": str(selection_config.minimum_score),
            "snapshot_id": selection_context.snapshot_id,
            "as_of": selection_context.as_of.isoformat(),
            "source_semantics_id": selection_context.source_semantics_id,
            "availability_grade": selection_context.availability_grade,
            "candidates": [_candidate_payload(outcome) for outcome in outcomes],
        },
    )


def _candidate_payload(outcome: OpportunitySelectionPolicyCycleOutcome) -> dict[str, object]:
    selection = outcome.selection_outcome
    entry = selection.entry
    source = entry.source_eligibility
    policy = outcome.policy_cycle_outcome
    return {
        "market": entry.identity[0],
        "symbol": entry.identity[1],
        "selection_ref": entry.selection_ref,
        "selection_score": str(entry.selection_score),
        "score_observed_at": entry.score_observed_at.isoformat(),
        "score_valid_until": entry.score_valid_until.isoformat(),
        "source_contract_id": source.expected_contract.contract_id,
        "source_contract_hash": source.expected_contract.contract_hash,
        "selected": selection.selected,
        "selection_rank": selection.selection_rank,
        "reason": selection.reason,
        "policy_proposal_id": policy.policy_proposal.proposal_id if policy is not None else None,
        "allocated_proposal_id": policy.allocated_proposal.proposal_id
        if policy is not None
        else None,
    }


def _opaque_reference(*, kind: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        {"kind": kind, **payload},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return "ref:" + hashlib.sha256(encoded).hexdigest()

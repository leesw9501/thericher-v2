"""Pure source-attested cross-sectional opportunity selection.

This module is the first model-side stage of the decision graph.  It consumes
only caller-owned scores and already source-attested opportunities, then emits
a complete selected/not-selected result for the frozen candidate set.  It has
no data, training, broker, portfolio-reservation, or execution authority.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from thericher_v2.contracts import decimal_value, require_utc
from thericher_v2.models.current_source_opportunity_eligibility import (
    CurrentSourceOpportunityEligibility,
)

_COMPACT_IDENTIFIER: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", re.ASCII)
_SELECTION_REFERENCE: Final = re.compile(r"ref:[0-9a-f]{32,128}", re.ASCII)


class OpportunitySelectionInputError(ValueError):
    """A whole ranked set is unsafe to compare at its declared snapshot."""


@dataclass(frozen=True)
class OpportunitySelectionConfig:
    """Frozen top-K geometry for one caller-owned score schema."""

    selector_id: str
    score_schema_id: str
    maximum_selected: int
    minimum_score: Decimal | int | str

    def __post_init__(self) -> None:
        if (
            _COMPACT_IDENTIFIER.fullmatch(self.selector_id) is None
            or _COMPACT_IDENTIFIER.fullmatch(self.score_schema_id) is None
        ):
            raise ValueError("selection identifiers must be compact stable identifiers")
        if type(self.maximum_selected) is not int or self.maximum_selected <= 0:
            raise ValueError("maximum_selected must be a positive integer")
        minimum_score = decimal_value(self.minimum_score, "minimum_score")
        if not Decimal("0") <= minimum_score <= Decimal("1"):
            raise ValueError("minimum_score must be between zero and one")
        object.__setattr__(self, "minimum_score", minimum_score)


@dataclass(frozen=True)
class OpportunitySelectionContext:
    """The common source semantics required before scores can be compared."""

    snapshot_id: str
    as_of: datetime
    source_semantics_id: str
    availability_grade: str

    def __post_init__(self) -> None:
        for value in (
            self.snapshot_id,
            self.source_semantics_id,
            self.availability_grade,
        ):
            if _COMPACT_IDENTIFIER.fullmatch(value) is None:
                raise ValueError("selection context identifiers must be compact stable identifiers")
        object.__setattr__(self, "as_of", require_utc(self.as_of, "selection as_of"))


@dataclass(frozen=True)
class OpportunitySelectionEntry:
    """One caller-scored opportunity bound to a source-attested snapshot."""

    source_eligibility: CurrentSourceOpportunityEligibility
    selection_ref: str
    selection_score: Decimal | int | str
    score_schema_id: str
    snapshot_id: str
    source_semantics_id: str
    availability_grade: str
    score_observed_at: datetime
    score_valid_until: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.source_eligibility, CurrentSourceOpportunityEligibility):
            raise TypeError("source_eligibility must be a CurrentSourceOpportunityEligibility")
        if _SELECTION_REFERENCE.fullmatch(self.selection_ref) is None:
            raise ValueError("selection_ref must be an opaque reference")
        for value in (
            self.score_schema_id,
            self.snapshot_id,
            self.source_semantics_id,
            self.availability_grade,
        ):
            if _COMPACT_IDENTIFIER.fullmatch(value) is None:
                raise ValueError("selection entry identifiers must be compact stable identifiers")
        selection_score = decimal_value(self.selection_score, "selection_score")
        if not Decimal("0") <= selection_score <= Decimal("1"):
            raise ValueError("selection_score must be between zero and one")
        observed_at = require_utc(self.score_observed_at, "score_observed_at")
        valid_until = require_utc(self.score_valid_until, "score_valid_until")
        if valid_until < observed_at:
            raise ValueError("selection score validity is invalid")
        object.__setattr__(self, "selection_score", selection_score)
        object.__setattr__(self, "score_observed_at", observed_at)
        object.__setattr__(self, "score_valid_until", valid_until)

    @property
    def identity(self) -> tuple[str, str]:
        eligibility = self.source_eligibility.eligibility
        return eligibility.market, eligibility.symbol


@dataclass(frozen=True)
class OpportunitySelectionOutcome:
    """One auditable result, including candidates excluded before policy."""

    entry: OpportunitySelectionEntry
    selected: bool
    selection_rank: int | None
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.entry, OpportunitySelectionEntry):
            raise TypeError("entry must be an OpportunitySelectionEntry")
        if not isinstance(self.selected, bool):
            raise TypeError("selected must be boolean")
        if self.selected:
            if type(self.selection_rank) is not int or self.selection_rank <= 0:
                raise ValueError("selected outcomes require a positive selection rank")
            if self.reason != "selected":
                raise ValueError("selected outcomes must have the selected reason")
        elif self.selection_rank is not None:
            raise ValueError("not-selected outcomes cannot carry a selection rank")
        if not self.reason:
            raise ValueError("selection outcome reason must be nonempty")


def select_source_attested_opportunities(
    entries: Sequence[OpportunitySelectionEntry],
    *,
    config: OpportunitySelectionConfig,
    context: OpportunitySelectionContext,
) -> tuple[OpportunitySelectionOutcome, ...]:
    """Select a deterministic top-K set from one aligned candidate snapshot.

    A stale, duplicate, unqualified, or mixed-context input rejects the whole
    selection cycle.  Silently dropping such a row would let the selected set
    depend on data availability.  A source-attested but upstream-ineligible
    candidate is instead retained as a normal, per-candidate not-selected
    outcome because it is comparable evidence about that candidate.
    """

    if not isinstance(entries, Sequence):
        raise TypeError("entries must be a sequence")
    if not isinstance(config, OpportunitySelectionConfig):
        raise TypeError("config must be an OpportunitySelectionConfig")
    if not isinstance(context, OpportunitySelectionContext):
        raise TypeError("context must be an OpportunitySelectionContext")
    cycle_entries = tuple(entries)
    if any(not isinstance(entry, OpportunitySelectionEntry) for entry in cycle_entries):
        raise TypeError("entries must contain OpportunitySelectionEntry values")

    _validate_cycle_inputs(cycle_entries, config=config, context=context)
    candidates = tuple(
        entry
        for entry in cycle_entries
        if entry.source_eligibility.eligible and entry.selection_score >= config.minimum_score
    )
    ranked = tuple(sorted(candidates, key=_ranking_key))
    selected_by_identity = {
        entry.identity: rank
        for rank, entry in enumerate(ranked[: config.maximum_selected], start=1)
    }
    outcomes_by_identity: dict[tuple[str, str], OpportunitySelectionOutcome] = {}
    for entry in cycle_entries:
        rank = selected_by_identity.get(entry.identity)
        if rank is not None:
            outcome = OpportunitySelectionOutcome(
                entry=entry,
                selected=True,
                selection_rank=rank,
                reason="selected",
            )
        elif not entry.source_eligibility.eligible:
            outcome = OpportunitySelectionOutcome(
                entry=entry,
                selected=False,
                selection_rank=None,
                reason=f"source_{entry.source_eligibility.reason}",
            )
        elif entry.selection_score < config.minimum_score:
            outcome = OpportunitySelectionOutcome(
                entry=entry,
                selected=False,
                selection_rank=None,
                reason="score_below_threshold",
            )
        else:
            outcome = OpportunitySelectionOutcome(
                entry=entry,
                selected=False,
                selection_rank=None,
                reason="selection_capacity_exhausted",
            )
        outcomes_by_identity[entry.identity] = outcome
    return tuple(outcomes_by_identity[identity] for identity in sorted(outcomes_by_identity))


def _validate_cycle_inputs(
    entries: tuple[OpportunitySelectionEntry, ...],
    *,
    config: OpportunitySelectionConfig,
    context: OpportunitySelectionContext,
) -> None:
    identities: set[tuple[str, str]] = set()
    for entry in entries:
        identity = entry.identity
        if identity in identities:
            raise OpportunitySelectionInputError("selection_duplicate_identity")
        identities.add(identity)
        if entry.score_schema_id != config.score_schema_id:
            raise OpportunitySelectionInputError("selection_score_schema_misaligned")
        if (
            entry.snapshot_id != context.snapshot_id
            or entry.source_semantics_id != context.source_semantics_id
            or entry.availability_grade != context.availability_grade
            or entry.source_eligibility.as_of != context.as_of
        ):
            raise OpportunitySelectionInputError("selection_context_misaligned")
        source = entry.source_eligibility.eligibility
        if entry.source_eligibility.input_status != "ready":
            raise OpportunitySelectionInputError(
                f"selection_source_{entry.source_eligibility.input_status}"
            )
        if source.observed_at > context.as_of:
            raise OpportunitySelectionInputError("selection_source_future")
        if source.valid_until < context.as_of:
            raise OpportunitySelectionInputError("selection_source_stale")
        if entry.score_observed_at > context.as_of:
            raise OpportunitySelectionInputError("selection_score_future")
        if entry.score_valid_until < context.as_of:
            raise OpportunitySelectionInputError("selection_score_stale")


def _ranking_key(entry: OpportunitySelectionEntry) -> tuple[Decimal, str, str]:
    market, symbol = entry.identity
    return -entry.selection_score, market, symbol

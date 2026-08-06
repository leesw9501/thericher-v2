"""Pure caller-ordered same-cycle target-exposure allocation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from thericher_v2.contracts import TargetExposureProposal, require_utc
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
    allocate_target_exposure,
)


@dataclass(frozen=True)
class TargetExposureAllocationCycleEntry:
    """One caller-ordered proposal and its per-symbol allocation facts."""

    proposal: TargetExposureProposal
    allocation: TargetExposureAllocationInput

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, TargetExposureProposal):
            raise TypeError("proposal must be a TargetExposureProposal")
        if not isinstance(self.allocation, TargetExposureAllocationInput):
            raise TypeError("allocation must be a TargetExposureAllocationInput")


def allocate_target_exposure_cycle(
    entries: Sequence[TargetExposureAllocationCycleEntry],
    *,
    config: TargetExposureAllocationConfig,
    as_of: datetime,
) -> tuple[TargetExposureProposal, ...]:
    """Allocate caller-provided proposals in order against one capacity snapshot.

    This helper deliberately has no symbol-selection or reservation authority.
    It only refreshes an in-memory capacity view after an accepted target
    increase. Reductions and exits do not release capacity because Execution
    has not yet confirmed an actual position change.
    """

    if not isinstance(entries, Sequence):
        raise TypeError("entries must be a sequence")
    if not isinstance(config, TargetExposureAllocationConfig):
        raise TypeError("config must be a TargetExposureAllocationConfig")
    now = require_utc(as_of, "as_of")
    cycle_entries = tuple(entries)
    if not cycle_entries:
        return ()
    if any(not isinstance(entry, TargetExposureAllocationCycleEntry) for entry in cycle_entries):
        raise TypeError("entries must contain TargetExposureAllocationCycleEntry values")

    _require_unique_identities(cycle_entries)
    _require_shared_portfolio_snapshot(cycle_entries)

    portfolio_exposure = cycle_entries[0].allocation.current_portfolio_exposure
    available_capacity = cycle_entries[0].allocation.available_portfolio_capacity
    allocated: list[TargetExposureProposal] = []
    for entry in cycle_entries:
        refreshed_allocation = replace(
            entry.allocation,
            current_portfolio_exposure=portfolio_exposure,
            available_portfolio_capacity=available_capacity,
        )
        result = allocate_target_exposure(
            entry.proposal,
            refreshed_allocation,
            config=config,
            as_of=now,
        )
        allocated.append(result)

        accepted_increase = (
            max(
                Decimal("0"),
                result.target_exposure - entry.allocation.current_symbol_exposure,
            )
            if result.action == "enter"
            else Decimal("0")
        )
        portfolio_exposure += accepted_increase
        available_capacity -= accepted_increase

    return tuple(allocated)


def _require_unique_identities(entries: Sequence[TargetExposureAllocationCycleEntry]) -> None:
    identities: set[tuple[str, str]] = set()
    for entry in entries:
        identity = (entry.proposal.market, entry.proposal.symbol)
        if identity in identities:
            raise ValueError("cycle proposals must have unique market/symbol identities")
        identities.add(identity)


def _require_shared_portfolio_snapshot(
    entries: Sequence[TargetExposureAllocationCycleEntry],
) -> None:
    expected = _portfolio_snapshot(entries[0].allocation)
    if any(_portfolio_snapshot(entry.allocation) != expected for entry in entries[1:]):
        raise ValueError("cycle allocations must share one portfolio snapshot")


def _portfolio_snapshot(
    allocation: TargetExposureAllocationInput,
) -> tuple[Decimal, Decimal, Decimal, str, datetime, datetime]:
    return (
        allocation.current_portfolio_exposure,
        allocation.available_portfolio_capacity,
        allocation.portfolio_exposure_cap,
        allocation.input_status,
        allocation.observed_at,
        allocation.valid_until,
    )

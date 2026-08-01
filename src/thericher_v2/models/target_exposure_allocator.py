"""Pure caller-owned long-only target-exposure allocation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from thericher_v2.contracts import (
    TargetExposureProposal,
    TargetInputStatus,
    decimal_value,
    require_utc,
)

_ALLOCATOR_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", re.ASCII)
_INPUT_STATUSES = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "incomplete",
        "duplicate",
        "non_contiguous",
        "misaligned",
        "future",
        "unqualified",
    }
)


@dataclass(frozen=True)
class TargetExposureAllocationConfig:
    """Stable identity for a pure allocation rule with no default target."""

    allocator_id: str

    def __post_init__(self) -> None:
        if _ALLOCATOR_ID.fullmatch(self.allocator_id) is None:
            raise ValueError("allocator_id must be a compact stable identifier")


@dataclass(frozen=True)
class TargetExposureAllocationInput:
    """Caller-declared capacity facts for one long-only target calculation.

    This is intentionally a snapshot, not a portfolio reservation or state
    authority. A caller that allocates multiple symbols in one decision cycle
    must serialize them and refresh this input after each accepted increase.
    """

    current_symbol_exposure: Decimal
    current_portfolio_exposure: Decimal
    available_portfolio_capacity: Decimal
    portfolio_exposure_cap: Decimal
    per_symbol_exposure_cap: Decimal
    confidence_multiplier: Decimal
    risk_multiplier: Decimal
    input_status: TargetInputStatus
    observed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        normalized = {
            "current_symbol_exposure": decimal_value(
                self.current_symbol_exposure,
                "current_symbol_exposure",
            ),
            "current_portfolio_exposure": decimal_value(
                self.current_portfolio_exposure,
                "current_portfolio_exposure",
            ),
            "available_portfolio_capacity": decimal_value(
                self.available_portfolio_capacity,
                "available_portfolio_capacity",
            ),
            "portfolio_exposure_cap": decimal_value(
                self.portfolio_exposure_cap,
                "portfolio_exposure_cap",
            ),
            "per_symbol_exposure_cap": decimal_value(
                self.per_symbol_exposure_cap,
                "per_symbol_exposure_cap",
            ),
            "confidence_multiplier": decimal_value(
                self.confidence_multiplier,
                "confidence_multiplier",
            ),
            "risk_multiplier": decimal_value(self.risk_multiplier, "risk_multiplier"),
        }
        if any(value < 0 or value > 1 for value in normalized.values()):
            raise ValueError("allocation exposures and multipliers must be between 0 and 1")
        if self.input_status not in _INPUT_STATUSES:
            raise ValueError("allocation input_status is invalid")
        observed_at = require_utc(self.observed_at, "observed_at")
        valid_until = require_utc(self.valid_until, "valid_until")
        if valid_until < observed_at:
            raise ValueError("allocation validity is invalid")
        for name, value in normalized.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "valid_until", valid_until)


def allocate_target_exposure(
    proposal: TargetExposureProposal,
    allocation: TargetExposureAllocationInput,
    *,
    config: TargetExposureAllocationConfig,
    as_of: datetime,
) -> TargetExposureProposal:
    """Scale then cap an entry target using only caller-owned capacity facts.

    The allocator has no portfolio reservation authority. It returns a target
    proposal only; Execution remains responsible for its own position, cash,
    quantization, and order-boundary checks.
    """

    if not isinstance(proposal, TargetExposureProposal):
        raise TypeError("proposal must be a TargetExposureProposal")
    if not isinstance(allocation, TargetExposureAllocationInput):
        raise TypeError("allocation must be a TargetExposureAllocationInput")
    if not isinstance(config, TargetExposureAllocationConfig):
        raise TypeError("config must be a TargetExposureAllocationConfig")
    now = require_utc(as_of, "as_of")
    proposal_status = _proposal_input_status(proposal, now)
    if proposal.action in {"reduce", "exit"}:
        if proposal_status == "ready":
            return proposal
        return _abstain(
            proposal,
            allocation=allocation,
            config=config,
            as_of=now,
            input_status=proposal_status,
            reason=f"proposal_{proposal_status}",
        )
    if proposal.action in {"abstain", "hold"}:
        return proposal
    if proposal_status != "ready":
        return _abstain(
            proposal,
            allocation=allocation,
            config=config,
            as_of=now,
            input_status=proposal_status,
            reason=f"proposal_{proposal_status}",
        )
    allocation_status = _allocation_input_status(allocation, now)
    if allocation_status != "ready":
        return _abstain(
            proposal,
            allocation=allocation,
            config=config,
            as_of=now,
            input_status=allocation_status,
            reason=f"allocation_{allocation_status}",
        )
    if _capacity_is_inconsistent(allocation):
        return _abstain(
            proposal,
            allocation=allocation,
            config=config,
            as_of=now,
            input_status="unqualified",
            reason="allocation_capacity_inconsistent",
        )

    # The contract fixes multiplier application before concentration/capacity caps.
    scaled_target = (
        proposal.target_exposure
        * allocation.confidence_multiplier
        * allocation.risk_multiplier
    )
    requested_increase = max(Decimal("0"), scaled_target - allocation.current_symbol_exposure)
    symbol_headroom = max(
        Decimal("0"),
        allocation.per_symbol_exposure_cap - allocation.current_symbol_exposure,
    )
    portfolio_headroom = max(
        Decimal("0"),
        allocation.portfolio_exposure_cap - allocation.current_portfolio_exposure,
    )
    permitted_increase = min(
        requested_increase,
        symbol_headroom,
        portfolio_headroom,
        allocation.available_portfolio_capacity,
    )
    valid_until = min(proposal.valid_until, allocation.valid_until)
    if permitted_increase <= 0:
        reason = (
            "allocation_no_increase_after_scaling"
            if requested_increase <= 0
            else "allocation_capacity_exhausted"
        )
        return _hold(
            proposal,
            allocation=allocation,
            config=config,
            as_of=now,
            target_exposure=allocation.current_symbol_exposure,
            valid_until=valid_until,
            reason=reason,
        )
    return _proposal(
        proposal,
        allocation=allocation,
        config=config,
        as_of=now,
        action="enter",
        target_exposure=allocation.current_symbol_exposure + permitted_increase,
        confidence=proposal.confidence,
        input_status="ready",
        valid_until=valid_until,
        reason="allocation_scaled_then_capped_entry",
    )


def _proposal_input_status(
    proposal: TargetExposureProposal,
    as_of: datetime,
) -> TargetInputStatus:
    if proposal.input_status != "ready":
        return proposal.input_status
    if as_of < proposal.decided_at:
        return "future"
    if as_of > proposal.valid_until:
        return "stale"
    return "ready"


def _allocation_input_status(
    allocation: TargetExposureAllocationInput,
    as_of: datetime,
) -> TargetInputStatus:
    if allocation.input_status != "ready":
        return allocation.input_status
    if as_of < allocation.observed_at:
        return "future"
    if as_of > allocation.valid_until:
        return "stale"
    return "ready"


def _capacity_is_inconsistent(allocation: TargetExposureAllocationInput) -> bool:
    return (
        allocation.current_symbol_exposure > allocation.current_portfolio_exposure
        or allocation.current_symbol_exposure > allocation.per_symbol_exposure_cap
        or allocation.current_portfolio_exposure > allocation.portfolio_exposure_cap
        or allocation.current_portfolio_exposure + allocation.available_portfolio_capacity
        > allocation.portfolio_exposure_cap
    )


def _hold(
    proposal: TargetExposureProposal,
    *,
    allocation: TargetExposureAllocationInput,
    config: TargetExposureAllocationConfig,
    as_of: datetime,
    target_exposure: Decimal,
    valid_until: datetime,
    reason: str,
) -> TargetExposureProposal:
    return _proposal(
        proposal,
        allocation=allocation,
        config=config,
        as_of=as_of,
        action="hold",
        target_exposure=target_exposure,
        confidence=proposal.confidence,
        input_status="ready",
        valid_until=valid_until,
        reason=reason,
    )


def _abstain(
    proposal: TargetExposureProposal,
    *,
    allocation: TargetExposureAllocationInput,
    config: TargetExposureAllocationConfig,
    as_of: datetime,
    input_status: TargetInputStatus,
    reason: str,
) -> TargetExposureProposal:
    return _proposal(
        proposal,
        allocation=allocation,
        config=config,
        as_of=as_of,
        action="abstain",
        target_exposure=Decimal("0"),
        confidence=Decimal("0"),
        input_status=input_status,
        valid_until=as_of,
        reason=reason,
    )


def _proposal(
    source: TargetExposureProposal,
    *,
    allocation: TargetExposureAllocationInput,
    config: TargetExposureAllocationConfig,
    as_of: datetime,
    action: str,
    target_exposure: Decimal,
    confidence: Decimal,
    input_status: TargetInputStatus,
    valid_until: datetime,
    reason: str,
) -> TargetExposureProposal:
    feature_window_end = source.feature_window_end
    if feature_window_end is not None and feature_window_end > as_of:
        feature_window_end = None
    return TargetExposureProposal(
        proposal_id=_proposal_id(
            source=source,
            allocation=allocation,
            config=config,
            as_of=as_of,
            action=action,
            target_exposure=target_exposure,
            confidence=confidence,
            input_status=input_status,
            valid_until=valid_until,
            reason=reason,
        ),
        symbol=source.symbol,
        market=source.market,
        action=action,
        target_exposure=target_exposure,
        confidence=confidence,
        feature_schema_id=source.feature_schema_id,
        input_status=input_status,
        decided_at=as_of,
        valid_until=valid_until,
        feature_window_end=feature_window_end,
        reason=reason,
    )


def _proposal_id(
    *,
    source: TargetExposureProposal,
    allocation: TargetExposureAllocationInput,
    config: TargetExposureAllocationConfig,
    as_of: datetime,
    action: str,
    target_exposure: Decimal,
    confidence: Decimal,
    input_status: TargetInputStatus,
    valid_until: datetime,
    reason: str,
) -> str:
    payload = {
        "allocator_id": config.allocator_id,
        "source_proposal_id": source.proposal_id,
        "allocation": {
            "current_symbol_exposure": str(allocation.current_symbol_exposure),
            "current_portfolio_exposure": str(allocation.current_portfolio_exposure),
            "available_portfolio_capacity": str(allocation.available_portfolio_capacity),
            "portfolio_exposure_cap": str(allocation.portfolio_exposure_cap),
            "per_symbol_exposure_cap": str(allocation.per_symbol_exposure_cap),
            "confidence_multiplier": str(allocation.confidence_multiplier),
            "risk_multiplier": str(allocation.risk_multiplier),
            "input_status": allocation.input_status,
            "observed_at": allocation.observed_at.isoformat(),
            "valid_until": allocation.valid_until.isoformat(),
        },
        "as_of": as_of.isoformat(),
        "action": action,
        "target_exposure": str(target_exposure),
        "confidence": str(confidence),
        "input_status": input_status,
        "valid_until": valid_until.isoformat(),
        "reason": reason,
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return "allocation:" + hashlib.sha256(encoded).hexdigest()

from __future__ import annotations

import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    prepare_local_paper_intent,
)
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
    allocate_target_exposure,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

_NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_entry_is_scaled_before_capacity_and_concentration_caps() -> None:
    allocated = allocate_target_exposure(
        _proposal(target_exposure="0.80"),
        _allocation(
            current_symbol_exposure="0.10",
            current_portfolio_exposure="0.40",
            available_portfolio_capacity="0.50",
            portfolio_exposure_cap="0.90",
            per_symbol_exposure_cap="0.70",
            confidence_multiplier="0.50",
            risk_multiplier="0.50",
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert (allocated.action, allocated.target_exposure, allocated.reason) == (
        "enter",
        Decimal("0.20"),
        "allocation_scaled_then_capped_entry",
    )


def test_entry_is_capped_by_current_capacity_and_per_symbol_limit() -> None:
    allocated = allocate_target_exposure(
        _proposal(target_exposure="0.90"),
        _allocation(
            current_symbol_exposure="0.10",
            current_portfolio_exposure="0.70",
            available_portfolio_capacity="0.12",
            portfolio_exposure_cap="0.82",
            per_symbol_exposure_cap="0.30",
            confidence_multiplier="1",
            risk_multiplier="1",
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert (allocated.action, allocated.target_exposure) == ("enter", Decimal("0.22"))


def test_capacity_exhaustion_or_scaled_target_below_current_never_reduces() -> None:
    exhausted = allocate_target_exposure(
        _proposal(target_exposure="0.70"),
        _allocation(
            current_symbol_exposure="0.20",
            current_portfolio_exposure="0.80",
            available_portfolio_capacity="0",
            portfolio_exposure_cap="0.80",
            per_symbol_exposure_cap="0.50",
        ),
        config=_config(),
        as_of=_NOW,
    )
    scaled_below_current = allocate_target_exposure(
        _proposal(target_exposure="0.20"),
        _allocation(
            current_symbol_exposure="0.20",
            current_portfolio_exposure="0.40",
            available_portfolio_capacity="0.40",
            portfolio_exposure_cap="0.80",
            per_symbol_exposure_cap="0.50",
            confidence_multiplier="0.50",
            risk_multiplier="0.50",
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert (exhausted.action, exhausted.target_exposure, exhausted.reason) == (
        "hold",
        Decimal("0.20"),
        "allocation_capacity_exhausted",
    )
    assert (scaled_below_current.action, scaled_below_current.target_exposure) == (
        "hold",
        Decimal("0.20"),
    )
    assert scaled_below_current.reason == "allocation_no_increase_after_scaling"


def test_unqualified_stale_or_inconsistent_capacity_becomes_an_abstain() -> None:
    unqualified = allocate_target_exposure(
        _proposal(),
        _allocation(input_status="unqualified"),
        config=_config(),
        as_of=_NOW,
    )
    stale = allocate_target_exposure(
        _proposal(),
        _allocation(valid_until=_NOW - timedelta(seconds=1)),
        config=_config(),
        as_of=_NOW,
    )
    inconsistent = allocate_target_exposure(
        _proposal(),
        _allocation(
            current_portfolio_exposure="0.70",
            available_portfolio_capacity="0.20",
            portfolio_exposure_cap="0.80",
        ),
        config=_config(),
        as_of=_NOW,
    )

    assert (unqualified.action, unqualified.input_status, unqualified.reason) == (
        "abstain",
        "unqualified",
        "allocation_unqualified",
    )
    assert (stale.action, stale.input_status, stale.reason) == (
        "abstain",
        "stale",
        "allocation_stale",
    )
    assert (inconsistent.action, inconsistent.input_status, inconsistent.reason) == (
        "abstain",
        "unqualified",
        "allocation_capacity_inconsistent",
    )


def test_valid_reduction_or_exit_passes_through_bad_capacity_but_stale_exit_does_not() -> None:
    exit_proposal = _proposal(action="exit", target_exposure="0")
    reduced = _proposal(action="reduce", target_exposure="0.10")
    bad_capacity = _allocation(input_status="unqualified")

    assert allocate_target_exposure(
        exit_proposal,
        bad_capacity,
        config=_config(),
        as_of=_NOW,
    ) is exit_proposal
    assert allocate_target_exposure(
        reduced,
        bad_capacity,
        config=_config(),
        as_of=_NOW,
    ) is reduced

    stale_exit = allocate_target_exposure(
        _proposal(
            action="exit",
            target_exposure="0",
            decided_at=_NOW - timedelta(minutes=2),
            valid_until=_NOW - timedelta(seconds=1),
        ),
        bad_capacity,
        config=_config(),
        as_of=_NOW,
    )
    assert (stale_exit.action, stale_exit.input_status, stale_exit.reason) == (
        "abstain",
        "stale",
        "proposal_stale",
    )


def test_allocation_identity_is_deterministic_and_input_sensitive() -> None:
    source = _proposal()
    inputs = _allocation()

    first = allocate_target_exposure(source, inputs, config=_config(), as_of=_NOW)
    second = allocate_target_exposure(source, inputs, config=_config(), as_of=_NOW)
    changed = allocate_target_exposure(
        source,
        _allocation(per_symbol_exposure_cap="0.30"),
        config=_config(),
        as_of=_NOW,
    )

    assert first.proposal_id == second.proposal_id
    assert first.proposal_id != changed.proposal_id


def test_allocated_target_composes_only_with_the_local_paper_preparation_bridge() -> None:
    allocated = allocate_target_exposure(
        _proposal(),
        _allocation(current_symbol_exposure="0"),
        config=_config(),
        as_of=_NOW,
    )
    receipt = receipt_from_target_exposure_proposal(allocated, references=_references())

    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref="ref:" + "4" * 64,
            symbol="QQQ",
            target_exposure=allocated.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=_NOW,
    )

    assert bridge.route == "local_paper"
    assert bridge.status == "ready"
    assert bridge.kis_paper_decision is None
    assert bridge.local_paper_intent is not None


def test_allocator_is_pure_and_needs_no_external_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _deny_external_access(monkeypatch)

    allocated = allocate_target_exposure(
        _proposal(),
        _allocation(),
        config=_config(),
        as_of=_NOW,
    )

    assert allocated.action == "enter"


def _proposal(
    *,
    action: str = "enter",
    target_exposure: str = "0.40",
    decided_at: datetime = _NOW,
    valid_until: datetime | None = None,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id="source-proposal-v1",
        symbol="QQQ",
        market="US",
        action=action,
        target_exposure=Decimal(target_exposure),
        confidence=Decimal("0.80"),
        feature_schema_id="target-policy-features-v1",
        input_status="ready",
        decided_at=decided_at,
        valid_until=valid_until or decided_at + timedelta(minutes=2),
        feature_window_end=decided_at - timedelta(minutes=1),
        reason="source_target",
    )


def _allocation(
    *,
    current_symbol_exposure: str = "0.10",
    current_portfolio_exposure: str = "0.40",
    available_portfolio_capacity: str = "0.40",
    portfolio_exposure_cap: str = "0.80",
    per_symbol_exposure_cap: str = "0.50",
    confidence_multiplier: str = "1",
    risk_multiplier: str = "1",
    input_status: str = "ready",
    valid_until: datetime | None = None,
) -> TargetExposureAllocationInput:
    return TargetExposureAllocationInput(
        current_symbol_exposure=Decimal(current_symbol_exposure),
        current_portfolio_exposure=Decimal(current_portfolio_exposure),
        available_portfolio_capacity=Decimal(available_portfolio_capacity),
        portfolio_exposure_cap=Decimal(portfolio_exposure_cap),
        per_symbol_exposure_cap=Decimal(per_symbol_exposure_cap),
        confidence_multiplier=Decimal(confidence_multiplier),
        risk_multiplier=Decimal(risk_multiplier),
        input_status=input_status,
        observed_at=_NOW - timedelta(seconds=1),
        valid_until=valid_until or _NOW + timedelta(minutes=1),
    )


def _config() -> TargetExposureAllocationConfig:
    return TargetExposureAllocationConfig(allocator_id="target-exposure-allocation-v1")


def _references() -> DecisionReceiptReferences:
    return DecisionReceiptReferences(
        campaign_ref="ref:" + "1" * 64,
        model_ref="ref:" + "2" * 64,
        input_manifest_ref="sha256:" + "3" * 64,
        proposal_ref="ref:" + "4" * 64,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("target exposure allocation must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

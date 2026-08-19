from __future__ import annotations

import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import ModelPrediction, Signal, Timeframe
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    prepare_local_paper_intent,
)
from thericher_v2.models.current_source_opportunity_eligibility import (
    CurrentSourceContract,
    CurrentSourceMetadata,
    adapt_current_source_opportunity_eligibility,
)
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
)
from thericher_v2.models.target_exposure_policy_cycle import (
    TargetExposurePolicyCycleEntry,
    evaluate_target_exposure_policy_cycle,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

_NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
_TIMEFRAMES = (Timeframe.M1, Timeframe.M5)


def test_cycle_preserves_policy_and_allocation_outcomes_in_caller_order() -> None:
    outcomes = evaluate_target_exposure_policy_cycle(
        (_entry("QQQ"), _entry("SPY")),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        as_of=_NOW,
    )

    assert [
        (
            item.policy_proposal.symbol,
            item.policy_proposal.action,
            item.allocated_proposal.action,
            item.allocated_proposal.target_exposure,
        )
        for item in outcomes
    ] == [
        ("QQQ", "enter", "enter", Decimal("0.30")),
        ("SPY", "enter", "hold", Decimal("0")),
    ]
    assert outcomes[1].allocated_proposal.reason == "allocation_capacity_exhausted"


def test_unready_source_attestation_abstains_without_consuming_next_symbol_capacity() -> None:
    outcomes = evaluate_target_exposure_policy_cycle(
        (
            _entry("QQQ", source_status="unqualified"),
            _entry("SPY"),
        ),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        as_of=_NOW,
    )

    assert (
        outcomes[0].policy_proposal.action,
        outcomes[0].allocated_proposal.action,
        outcomes[0].allocated_proposal.reason,
    ) == ("abstain", "abstain", "opportunity_unqualified")
    assert (
        outcomes[1].allocated_proposal.action,
        outcomes[1].allocated_proposal.target_exposure,
    ) == ("enter", Decimal("0.30"))


def test_valid_exit_does_not_release_unexecuted_capacity_for_a_later_entry() -> None:
    outcomes = evaluate_target_exposure_policy_cycle(
        (
            _entry(
                "QQQ",
                action="sell",
                expected_edge_bps="-4",
                current_symbol_exposure="0.30",
                current_portfolio_exposure="0.80",
                available_portfolio_capacity="0",
                portfolio_exposure_cap="0.80",
            ),
            _entry(
                "SPY",
                current_portfolio_exposure="0.80",
                available_portfolio_capacity="0",
                portfolio_exposure_cap="0.80",
            ),
        ),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        as_of=_NOW,
    )

    assert (outcomes[0].policy_proposal.action, outcomes[0].allocated_proposal.action) == (
        "exit",
        "exit",
    )
    assert (outcomes[1].allocated_proposal.action, outcomes[1].allocated_proposal.reason) == (
        "hold",
        "allocation_capacity_exhausted",
    )


def test_current_exposure_must_match_the_allocation_snapshot() -> None:
    with pytest.raises(ValueError, match="match allocation current_symbol_exposure"):
        TargetExposurePolicyCycleEntry(
            source_eligibility=_source_eligibility("QQQ"),
            predictions=_predictions("QQQ"),
            current_exposure=Decimal("0.10"),
            allocation=_allocation(current_symbol_exposure="0"),
        )


def test_cycle_requires_a_monotone_current_source_attestation() -> None:
    with pytest.raises(TypeError, match="source_eligibility"):
        TargetExposurePolicyCycleEntry(
            source_eligibility=_eligibility("QQQ"),
            predictions=_predictions("QQQ"),
            current_exposure=Decimal("0"),
            allocation=_allocation(),
        )


def test_allocated_target_composes_only_with_the_local_paper_bridge() -> None:
    outcome = evaluate_target_exposure_policy_cycle(
        (_entry("QQQ"),),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        as_of=_NOW,
    )[0]
    receipt = receipt_from_target_exposure_proposal(
        outcome.allocated_proposal,
        references=_references(),
    )

    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref="ref:" + "4" * 64,
            symbol="QQQ",
            target_exposure=outcome.allocated_proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=_NOW,
    )

    assert bridge.route == "local_paper"
    assert bridge.status == "ready"
    assert bridge.kis_paper_decision is None
    assert bridge.local_paper_intent is not None
    assert bridge.local_paper_intent.quantity == Decimal("3.00")


def test_cycle_is_pure_and_needs_no_external_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)

    outcomes = evaluate_target_exposure_policy_cycle(
        (_entry("QQQ"), _entry("SPY")),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        as_of=_NOW,
    )

    assert len(outcomes) == 2


def _entry(
    symbol: str,
    *,
    action: str = "buy",
    expected_edge_bps: str = "4",
    source_status: str = "ready",
    current_symbol_exposure: str = "0",
    current_portfolio_exposure: str = "0.40",
    available_portfolio_capacity: str = "0.30",
    portfolio_exposure_cap: str = "0.70",
) -> TargetExposurePolicyCycleEntry:
    return TargetExposurePolicyCycleEntry(
        source_eligibility=_source_eligibility(symbol, status=source_status),
        predictions=_predictions(symbol, action=action, expected_edge_bps=expected_edge_bps),
        current_exposure=Decimal(current_symbol_exposure),
        allocation=_allocation(
            current_symbol_exposure=current_symbol_exposure,
            current_portfolio_exposure=current_portfolio_exposure,
            available_portfolio_capacity=available_portfolio_capacity,
            portfolio_exposure_cap=portfolio_exposure_cap,
        ),
    )


def _eligibility(symbol: str) -> OpportunityEligibility:
    return OpportunityEligibility(
        opportunity_ref="ref:" + symbol.lower().encode().hex().ljust(64, "0"),
        symbol=symbol,
        market="US",
        eligible=True,
        input_status="ready",
        observed_at=_NOW - timedelta(minutes=1),
        valid_until=_NOW + timedelta(minutes=3),
    )


def _source_eligibility(
    symbol: str,
    *,
    status: str = "ready",
):
    contract = CurrentSourceContract(
        contract_id=f"current-source-{symbol.lower()}-us-v1",
        contract_hash="sha256:" + ("a" if symbol == "QQQ" else "b") * 64,
    )
    return adapt_current_source_opportunity_eligibility(
        _eligibility(symbol),
        CurrentSourceMetadata(
            contract=contract,
            symbol=symbol,
            market="US",
            input_status=status,
            complete=True,
            observed_at=_NOW - timedelta(minutes=1),
            valid_until=_NOW + timedelta(minutes=2),
        ),
        expected_contract=contract,
        as_of=_NOW,
    )


def _predictions(
    symbol: str,
    *,
    action: str = "buy",
    expected_edge_bps: str = "4",
) -> tuple[ModelPrediction, ...]:
    return tuple(
        ModelPrediction(
            model_id=f"{symbol.lower()}-{timeframe.value}-expert",
            model_version="test-v1",
            symbol=symbol,
            market="US",
            signal=Signal(
                symbol=symbol,
                market="US",
                action=action,
                strength=Decimal("0.80"),
                reason="policy_cycle_test",
                timeframe=timeframe,
                generated_at=_NOW,
            ),
            confidence=Decimal("0.80"),
            expected_edge_bps=Decimal(expected_edge_bps),
            feature_window_end=_NOW - timedelta(minutes=1),
        )
        for timeframe in _TIMEFRAMES
    )


def _allocation(
    *,
    current_symbol_exposure: str = "0",
    current_portfolio_exposure: str = "0.40",
    available_portfolio_capacity: str = "0.30",
    portfolio_exposure_cap: str = "0.70",
) -> TargetExposureAllocationInput:
    return TargetExposureAllocationInput(
        current_symbol_exposure=Decimal(current_symbol_exposure),
        current_portfolio_exposure=Decimal(current_portfolio_exposure),
        available_portfolio_capacity=Decimal(available_portfolio_capacity),
        portfolio_exposure_cap=Decimal(portfolio_exposure_cap),
        per_symbol_exposure_cap=Decimal("0.50"),
        confidence_multiplier=Decimal("1"),
        risk_multiplier=Decimal("1"),
        input_status="ready",
        observed_at=_NOW - timedelta(seconds=1),
        valid_until=_NOW + timedelta(minutes=1),
    )


def _policy_config() -> TargetPositionPolicyConfig:
    return TargetPositionPolicyConfig(
        policy_id="target-policy-cycle-test-v1",
        feature_schema_id="target-policy-cycle-features-v1",
        required_timeframes=_TIMEFRAMES,
        maximum_evidence_age={
            Timeframe.M1: timedelta(minutes=2),
            Timeframe.M5: timedelta(minutes=10),
        },
        minimum_confidence=Decimal("0.60"),
        minimum_absolute_edge_bps=Decimal("2"),
        entry_target_exposure=Decimal("0.50"),
        decision_ttl=timedelta(minutes=2),
    )


def _allocation_config() -> TargetExposureAllocationConfig:
    return TargetExposureAllocationConfig(allocator_id="target-policy-cycle-test-v1")


def _references() -> DecisionReceiptReferences:
    return DecisionReceiptReferences(
        campaign_ref="ref:" + "1" * 64,
        model_ref="ref:" + "2" * 64,
        input_manifest_ref="sha256:" + "3" * 64,
        proposal_ref="ref:" + "4" * 64,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("target policy cycle must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

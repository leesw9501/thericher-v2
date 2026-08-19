from __future__ import annotations

import os
import socket
import urllib.request
from dataclasses import replace
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
from thericher_v2.models.opportunity_selection import (
    OpportunitySelectionConfig,
    OpportunitySelectionContext,
    OpportunitySelectionEntry,
    OpportunitySelectionInputError,
)
from thericher_v2.models.opportunity_selection_policy_cycle import (
    OpportunitySelectionPolicyCycleEntry,
    evaluate_opportunity_selection_policy_cycle,
)
from thericher_v2.models.target_exposure_allocator import (
    TargetExposureAllocationConfig,
    TargetExposureAllocationInput,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.selection_policy_provenance import (
    build_selected_selection_policy_proposal_lineage,
)

_NOW = datetime(2026, 8, 3, 15, 0, tzinfo=UTC)
_TIMEFRAMES = (Timeframe.M1, Timeframe.M5)


def test_cycle_separates_selection_policy_and_capacity_outcomes() -> None:
    outcomes = evaluate_opportunity_selection_policy_cycle(
        (
            _entry("DIA", "0.70", actions=("buy", "buy")),
            _entry("IWM", "0.80", actions=("buy", "buy")),
            _entry("SPY", "0.90", actions=("buy", "sell")),
            _entry("QQQ", "0.99", actions=("buy", "buy")),
        ),
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
    )
    by_symbol = {
        item.selection_outcome.entry.source_eligibility.eligibility.symbol: item
        for item in outcomes
    }

    assert (
        by_symbol["DIA"].selection_outcome.selected,
        by_symbol["DIA"].selection_outcome.reason,
        by_symbol["DIA"].policy_cycle_outcome,
    ) == (False, "selection_capacity_exhausted", None)
    assert by_symbol["QQQ"].selection_outcome.selection_rank == 1
    assert by_symbol["QQQ"].policy_cycle_outcome is not None
    assert (
        by_symbol["QQQ"].policy_cycle_outcome.policy_proposal.action,
        by_symbol["QQQ"].policy_cycle_outcome.allocated_proposal.action,
        by_symbol["QQQ"].policy_cycle_outcome.allocated_proposal.target_exposure,
    ) == ("enter", "enter", Decimal("0.30"))
    assert by_symbol["SPY"].selection_outcome.selection_rank == 2
    assert by_symbol["SPY"].policy_cycle_outcome is not None
    assert (
        by_symbol["SPY"].policy_cycle_outcome.policy_proposal.action,
        by_symbol["SPY"].policy_cycle_outcome.allocated_proposal.action,
        by_symbol["SPY"].policy_cycle_outcome.policy_proposal.reason,
    ) == ("abstain", "abstain", "expert_conflict")
    assert by_symbol["IWM"].selection_outcome.selection_rank == 3
    assert by_symbol["IWM"].policy_cycle_outcome is not None
    assert (
        by_symbol["IWM"].policy_cycle_outcome.policy_proposal.action,
        by_symbol["IWM"].policy_cycle_outcome.allocated_proposal.action,
        by_symbol["IWM"].policy_cycle_outcome.allocated_proposal.reason,
    ) == ("enter", "hold", "allocation_capacity_exhausted")


def test_cycle_selection_order_is_not_caller_order() -> None:
    entries = (
        _entry("SPY", "0.90", actions=("buy", "buy")),
        _entry("QQQ", "0.99", actions=("buy", "buy")),
        _entry("IWM", "0.80", actions=("buy", "buy")),
    )

    first = evaluate_opportunity_selection_policy_cycle(
        entries,
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
    )
    second = evaluate_opportunity_selection_policy_cycle(
        tuple(reversed(entries)),
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
    )

    assert _cycle_summary(first) == _cycle_summary(second)


def test_selected_lineage_replays_the_full_cohort_then_binds_a_local_paper_receipt() -> None:
    entries, outcomes = _cycle()
    lineage = build_selected_selection_policy_proposal_lineage(
        outcomes,
        entries=entries,
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        symbol="QQQ",
        market="US",
    )
    qqq = _outcome_for(outcomes, "QQQ")
    assert qqq.policy_cycle_outcome is not None

    receipt = receipt_from_target_exposure_proposal(
        qqq.policy_cycle_outcome.allocated_proposal,
        references=DecisionReceiptReferences(
            campaign_ref="ref:" + "a" * 64,
            model_ref="ref:" + "b" * 64,
            input_manifest_ref="sha256:" + "c" * 64,
            proposal_ref=lineage.proposal_ref,
        ),
    )
    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=lineage.proposal_ref,
            symbol="QQQ",
            target_exposure=qqq.policy_cycle_outcome.allocated_proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=_NOW,
    )

    assert lineage.selection_rank == 1
    assert lineage.symbol == "QQQ"
    assert lineage.proposal_ref.startswith("ref:")
    assert bridge.route == "local_paper"
    assert bridge.status == "ready"
    assert bridge.kis_paper_decision is None


def test_lineage_rejects_a_nonselected_or_tampered_selection_cohort() -> None:
    entries, outcomes = _cycle()
    with pytest.raises(ValueError, match="only for a selected outcome"):
        build_selected_selection_policy_proposal_lineage(
            outcomes,
            entries=entries,
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=_allocation_config(),
            symbol="DIA",
            market="US",
        )

    qqq = _outcome_for(outcomes, "QQQ")
    tampered_selection = replace(
        qqq.selection_outcome,
        entry=replace(qqq.selection_outcome.entry, selection_score=Decimal("0.10")),
    )
    tampered = tuple(
        replace(outcome, selection_outcome=tampered_selection)
        if outcome is qqq
        else outcome
        for outcome in outcomes
    )
    with pytest.raises(ValueError, match="deterministic cohort replay"):
        build_selected_selection_policy_proposal_lineage(
            tampered,
            entries=entries,
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=_allocation_config(),
            symbol="QQQ",
            market="US",
        )
    with pytest.raises(ValueError, match="deterministic cohort replay"):
        build_selected_selection_policy_proposal_lineage(
            outcomes,
            entries=entries,
            selection_config=replace(_selection_config(), maximum_selected=1),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=_allocation_config(),
            symbol="QQQ",
            market="US",
        )


def test_lineage_rejects_tampered_downstream_allocation_outcome() -> None:
    entries, outcomes = _cycle()
    qqq = _outcome_for(outcomes, "QQQ")
    assert qqq.policy_cycle_outcome is not None
    forged_allocation = replace(
        qqq.policy_cycle_outcome.allocated_proposal,
        target_exposure=Decimal("0.10"),
    )
    forged_outcome = replace(
        qqq,
        policy_cycle_outcome=replace(
            qqq.policy_cycle_outcome,
            allocated_proposal=forged_allocation,
        ),
    )
    forged_cohort = tuple(
        forged_outcome if outcome is qqq else outcome for outcome in outcomes
    )

    with pytest.raises(ValueError, match="deterministic cohort replay"):
        build_selected_selection_policy_proposal_lineage(
            forged_cohort,
            entries=entries,
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=_allocation_config(),
            symbol="QQQ",
            market="US",
        )


def test_lineage_requires_the_exact_frozen_policy_and_allocation_configs() -> None:
    entries, outcomes = _cycle()

    with pytest.raises(ValueError, match="deterministic cohort replay"):
        build_selected_selection_policy_proposal_lineage(
            outcomes,
            entries=entries,
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=replace(
                _policy_config(),
                entry_target_exposure=Decimal("0.40"),
            ),
            allocation_config=_allocation_config(),
            symbol="QQQ",
            market="US",
        )
    with pytest.raises(ValueError, match="deterministic cohort replay"):
        build_selected_selection_policy_proposal_lineage(
            outcomes,
            entries=entries,
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=TargetExposureAllocationConfig(
                allocator_id="other-selection-policy-cycle-test-v1"
            ),
            symbol="QQQ",
            market="US",
        )


def test_invalid_selection_input_fails_before_the_policy_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import thericher_v2.models.opportunity_selection_policy_cycle as cycle_module

    def policy_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("policy cycle must not run after selection rejection")

    monkeypatch.setattr(cycle_module, "evaluate_target_exposure_policy_cycle", policy_must_not_run)
    with pytest.raises(OpportunitySelectionInputError, match="score_stale"):
        evaluate_opportunity_selection_policy_cycle(
            (
                _entry(
                    "QQQ",
                    "0.90",
                    actions=("buy", "buy"),
                    score_valid_until=_NOW - timedelta(seconds=1),
                ),
            ),
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=_allocation_config(),
        )


def test_duplicate_selection_reference_fails_before_the_policy_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import thericher_v2.models.opportunity_selection_policy_cycle as cycle_module

    def policy_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("policy cycle must not run after selection rejection")

    entries = (
        _entry("QQQ", "0.90", actions=("buy", "buy")),
        _entry("SPY", "0.80", actions=("buy", "buy")),
    )
    duplicate_reference_entries = (
        entries[0],
        replace(
            entries[1],
            selection_entry=replace(
                entries[1].selection_entry,
                selection_ref=entries[0].selection_entry.selection_ref,
            ),
        ),
    )
    monkeypatch.setattr(cycle_module, "evaluate_target_exposure_policy_cycle", policy_must_not_run)

    with pytest.raises(OpportunitySelectionInputError, match="duplicate_reference"):
        evaluate_opportunity_selection_policy_cycle(
            duplicate_reference_entries,
            selection_config=_selection_config(),
            selection_context=_selection_context(),
            policy_config=_policy_config(),
            allocation_config=_allocation_config(),
        )


def test_cycle_is_pure_without_data_network_broker_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("selection policy cycle must not access external state")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    entries = (_entry("QQQ", "0.90", actions=("buy", "buy")),)
    outcomes = evaluate_opportunity_selection_policy_cycle(
        entries,
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
    )

    assert outcomes[0].selection_outcome.selected is True
    assert outcomes[0].policy_cycle_outcome is not None
    lineage = build_selected_selection_policy_proposal_lineage(
        outcomes,
        entries=entries,
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
        symbol="QQQ",
        market="US",
    )
    assert lineage.selection_rank == 1


def _cycle_summary(
    outcomes: tuple[object, ...],
) -> tuple[tuple[str, bool, int | None, str, str | None, str | None], ...]:
    summary = []
    for outcome in outcomes:
        selection = outcome.selection_outcome
        policy = outcome.policy_cycle_outcome
        summary.append(
            (
                selection.entry.source_eligibility.eligibility.symbol,
                selection.selected,
                selection.selection_rank,
                selection.reason,
                policy.policy_proposal.action if policy is not None else None,
                policy.allocated_proposal.action if policy is not None else None,
            )
        )
    return tuple(summary)


def _cycle() -> tuple[
    tuple[OpportunitySelectionPolicyCycleEntry, ...],
    tuple[object, ...],
]:
    entries = (
        _entry("DIA", "0.70", actions=("buy", "buy")),
        _entry("IWM", "0.80", actions=("buy", "buy")),
        _entry("SPY", "0.90", actions=("buy", "sell")),
        _entry("QQQ", "0.99", actions=("buy", "buy")),
    )
    return entries, _outcomes(entries)


def _outcomes(
    entries: tuple[OpportunitySelectionPolicyCycleEntry, ...],
) -> tuple[object, ...]:
    return evaluate_opportunity_selection_policy_cycle(
        entries,
        selection_config=_selection_config(),
        selection_context=_selection_context(),
        policy_config=_policy_config(),
        allocation_config=_allocation_config(),
    )


def _outcome_for(outcomes: tuple[object, ...], symbol: str) -> object:
    return next(
        outcome
        for outcome in outcomes
        if outcome.selection_outcome.entry.source_eligibility.eligibility.symbol == symbol
    )


def _entry(
    symbol: str,
    score: str,
    *,
    actions: tuple[str, str],
    score_valid_until: datetime = _NOW + timedelta(minutes=1),
) -> OpportunitySelectionPolicyCycleEntry:
    contract = CurrentSourceContract(
        contract_id=f"source-{symbol.lower()}-v1",
        contract_hash="sha256:" + symbol.lower().encode().hex().ljust(64, "0"),
    )
    source_eligibility = adapt_current_source_opportunity_eligibility(
        OpportunityEligibility(
            opportunity_ref="ref:" + symbol.lower().encode().hex().ljust(64, "0"),
            symbol=symbol,
            market="US",
            eligible=True,
            input_status="ready",
            observed_at=_NOW - timedelta(minutes=1),
            valid_until=_NOW + timedelta(minutes=2),
        ),
        CurrentSourceMetadata(
            contract=contract,
            symbol=symbol,
            market="US",
            input_status="ready",
            complete=True,
            observed_at=_NOW - timedelta(seconds=30),
            valid_until=_NOW + timedelta(minutes=1),
        ),
        expected_contract=contract,
        as_of=_NOW,
    )
    selection_entry = OpportunitySelectionEntry(
        source_eligibility=source_eligibility,
        selection_ref="ref:" + (symbol.lower().encode().hex() + "f" * 64)[:64],
        selection_score=Decimal(score),
        selector_id="selection-policy-cycle-test-v1",
        score_schema_id="cross-sectional-score-v1",
        snapshot_id="selection-policy-snapshot-v1",
        source_semantics_id="completed-bar-source-v1",
        availability_grade="causal-current-v1",
        score_observed_at=_NOW - timedelta(seconds=1),
        score_valid_until=score_valid_until,
    )
    return OpportunitySelectionPolicyCycleEntry(
        selection_entry=selection_entry,
        predictions=tuple(
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
                    reason="selection-policy-cycle-test",
                    timeframe=timeframe,
                    generated_at=_NOW,
                ),
                confidence=Decimal("0.80"),
                expected_edge_bps=Decimal("4"),
                feature_window_end=_NOW - timedelta(minutes=1),
            )
            for timeframe, action in zip(_TIMEFRAMES, actions, strict=True)
        ),
        current_exposure=Decimal("0"),
        allocation=TargetExposureAllocationInput(
            current_symbol_exposure=Decimal("0"),
            current_portfolio_exposure=Decimal("0.40"),
            available_portfolio_capacity=Decimal("0.30"),
            portfolio_exposure_cap=Decimal("0.70"),
            per_symbol_exposure_cap=Decimal("0.50"),
            confidence_multiplier=Decimal("1"),
            risk_multiplier=Decimal("1"),
            input_status="ready",
            observed_at=_NOW - timedelta(seconds=1),
            valid_until=_NOW + timedelta(minutes=1),
        ),
    )


def _selection_config() -> OpportunitySelectionConfig:
    return OpportunitySelectionConfig(
        selector_id="selection-policy-cycle-test-v1",
        score_schema_id="cross-sectional-score-v1",
        maximum_selected=3,
        minimum_score=Decimal("0.50"),
    )


def _selection_context() -> OpportunitySelectionContext:
    return OpportunitySelectionContext(
        snapshot_id="selection-policy-snapshot-v1",
        as_of=_NOW,
        source_semantics_id="completed-bar-source-v1",
        availability_grade="causal-current-v1",
    )


def _policy_config() -> TargetPositionPolicyConfig:
    return TargetPositionPolicyConfig(
        policy_id="selection-policy-cycle-test-v1",
        feature_schema_id="selection-policy-cycle-features-v1",
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
    return TargetExposureAllocationConfig(allocator_id="selection-policy-cycle-test-v1")

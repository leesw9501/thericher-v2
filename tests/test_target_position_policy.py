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
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    propose_target_exposure,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

_NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
_TIMEFRAMES = (Timeframe.M1, Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)


def test_full_multitimeframe_entry_flows_only_to_local_paper_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)

    proposal = propose_target_exposure(
        _eligibility(),
        _predictions(),
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
    )

    assert proposal.action == "enter"
    assert proposal.target_exposure == Decimal("0.20")
    assert proposal.input_status == "ready"
    assert proposal.reason == "unanimous_entry"
    receipt = receipt_from_target_exposure_proposal(proposal, references=_references())
    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_references().proposal_ref,
            symbol="QQQ",
            target_exposure=proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=_NOW,
    )

    assert bridge.route == "local_paper"
    assert bridge.status == "ready"
    assert bridge.local_paper_intent is not None
    assert bridge.kis_paper_decision is None


def test_conflicting_experts_abstain_without_an_execution_object() -> None:
    predictions = list(_predictions())
    predictions[1] = _prediction(Timeframe.M5, action="sell", expected_edge_bps=Decimal("-4"))

    proposal = propose_target_exposure(
        _eligibility(),
        predictions,
        current_exposure=Decimal("0.20"),
        config=_config(),
        as_of=_NOW,
    )

    assert proposal.action == "abstain"
    assert proposal.target_exposure == Decimal("0")
    assert proposal.input_status == "ready"
    assert proposal.reason == "expert_conflict"
    receipt = receipt_from_target_exposure_proposal(proposal, references=_references())
    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=_references().proposal_ref,
            symbol="QQQ",
            target_exposure=Decimal("0"),
            current_quantity=Decimal("1"),
            maximum_quantity=Decimal("5"),
        ),
        as_of=_NOW,
    )

    assert bridge.status == "no_intent"
    assert bridge.local_paper_intent is None


def test_stale_or_duplicate_evidence_becomes_a_categorical_abstain() -> None:
    stale = list(_predictions())
    stale[0] = _prediction(Timeframe.M1, feature_window_end=_NOW - timedelta(minutes=4))
    stale_proposal = propose_target_exposure(
        _eligibility(),
        stale,
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
    )
    duplicate_proposal = propose_target_exposure(
        _eligibility(),
        [*_predictions(), _prediction(Timeframe.M1)],
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
    )

    assert (stale_proposal.action, stale_proposal.input_status, stale_proposal.reason) == (
        "abstain",
        "stale",
        "evidence_stale",
    )
    assert (
        duplicate_proposal.action,
        duplicate_proposal.input_status,
        duplicate_proposal.reason,
    ) == ("abstain", "duplicate", "evidence_duplicate")


def test_ineligible_or_misaligned_inputs_never_create_a_target_action() -> None:
    ineligible = OpportunityEligibility(
        opportunity_ref="ref:" + "2" * 64,
        symbol="QQQ",
        market="US",
        eligible=False,
        input_status="ready",
        observed_at=_NOW - timedelta(minutes=1),
        valid_until=_NOW + timedelta(minutes=3),
    )
    misaligned = list(_predictions())
    misaligned[0] = _prediction(Timeframe.M1, symbol="SPY")

    ineligible_proposal = propose_target_exposure(
        ineligible,
        _predictions(),
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
    )
    misaligned_proposal = propose_target_exposure(
        _eligibility(),
        misaligned,
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
    )

    assert (ineligible_proposal.action, ineligible_proposal.reason) == (
        "abstain",
        "opportunity_ineligible",
    )
    assert (misaligned_proposal.action, misaligned_proposal.input_status) == (
        "abstain",
        "misaligned",
    )


def test_unanimous_sell_exits_only_when_an_exposure_exists() -> None:
    sells = [
        _prediction(timeframe, action="sell", expected_edge_bps=Decimal("-4"))
        for timeframe in _TIMEFRAMES
    ]

    holding = propose_target_exposure(
        _eligibility(),
        sells,
        current_exposure=Decimal("0.20"),
        config=_config(),
        as_of=_NOW,
    )
    flat = propose_target_exposure(
        _eligibility(),
        sells,
        current_exposure=Decimal("0"),
        config=_config(),
        as_of=_NOW,
    )

    assert (holding.action, holding.target_exposure, holding.reason) == (
        "exit",
        Decimal("0"),
        "unanimous_exit",
    )
    assert (flat.action, flat.target_exposure, flat.reason) == (
        "hold",
        Decimal("0"),
        "flat_exit_consensus",
    )


def _eligibility() -> OpportunityEligibility:
    return OpportunityEligibility(
        opportunity_ref="ref:" + "1" * 64,
        symbol="QQQ",
        market="US",
        eligible=True,
        input_status="ready",
        observed_at=_NOW - timedelta(minutes=1),
        valid_until=_NOW + timedelta(minutes=3),
    )


def _config() -> TargetPositionPolicyConfig:
    return TargetPositionPolicyConfig(
        policy_id="target-position-policy-test-v1",
        feature_schema_id="target-position-policy-features-v1",
        required_timeframes=_TIMEFRAMES,
        maximum_evidence_age={
            timeframe: timeframe.duration + timedelta(minutes=2) for timeframe in _TIMEFRAMES
        },
        minimum_confidence=Decimal("0.60"),
        minimum_absolute_edge_bps=Decimal("2"),
        entry_target_exposure=Decimal("0.20"),
        decision_ttl=timedelta(minutes=2),
    )


def _predictions() -> tuple[ModelPrediction, ...]:
    return tuple(_prediction(timeframe) for timeframe in _TIMEFRAMES)


def _prediction(
    timeframe: Timeframe,
    *,
    symbol: str = "QQQ",
    action: str = "buy",
    expected_edge_bps: Decimal = Decimal("4"),
    feature_window_end: datetime | None = None,
) -> ModelPrediction:
    window_end = feature_window_end or _NOW - timeframe.duration
    return ModelPrediction(
        model_id=f"expert-{timeframe.value}",
        model_version="test-v1",
        symbol=symbol,
        market="US",
        signal=Signal(
            symbol=symbol,
            market="US",
            action=action,
            strength=Decimal("0.80"),
            reason="test_evidence",
            timeframe=timeframe,
            generated_at=_NOW,
        ),
        confidence=Decimal("0.80"),
        expected_edge_bps=expected_edge_bps,
        feature_window_end=window_end,
    )


def _references() -> DecisionReceiptReferences:
    return DecisionReceiptReferences(
        campaign_ref="ref:" + "3" * 64,
        model_ref="ref:" + "4" * 64,
        input_manifest_ref="sha256:" + "5" * 64,
        proposal_ref="ref:" + "6" * 64,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("target-position policy must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

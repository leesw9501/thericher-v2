from __future__ import annotations

import inspect
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.execution import EmergencyStore, LocalPaperBroker, paper_decision_bridge
from thericher_v2.execution.paper_decision_bridge import (
    KisPaperLimitProof,
    LocalPaperTargetBinding,
    PaperDecisionExecutionBinding,
    prepare_kis_paper_decision,
    prepare_local_paper_intent,
    receipt_attribution_ref,
)
from thericher_v2.research import decision_receipt
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.state import EventStore

NOW = datetime(2026, 7, 22, 14, 31, tzinfo=UTC)


def test_eligible_receipt_replays_through_local_paper_with_its_exact_identity(
    tmp_path: Path,
) -> None:
    receipt = _receipt()
    prepared = prepare_local_paper_intent(
        receipt,
        binding=_local_target_binding(
            receipt,
            target_exposure=Decimal("0.5"),
            current_quantity=Decimal("1"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=NOW,
    )

    assert prepared.status == "ready"
    assert prepared.reason == "eligible"
    assert prepared.local_paper_intent is not None
    order = prepared.local_paper_intent
    assert order.decision_id == receipt.decision_id
    assert prepared.receipt_ref == receipt_attribution_ref(receipt)
    assert order.client_order_id == f"local-receipt-{receipt_attribution_ref(receipt)[7:]}"
    assert order.quantity == Decimal("4")

    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")
    broker = LocalPaperBroker(
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
    )
    execution = broker.submit_and_fill_next_bar(
        order,
        signal_bar=_bar(NOW - timedelta(minutes=1)),
        execution_bar=_bar(NOW),
    )

    assert execution.fill is not None
    events = tuple(store.iter_events())
    accepted = next(event for event in events if event.event_type == "local_paper_order_accepted")
    fill = next(event for event in events if event.event_type == "fill")
    assert accepted.payload["decision_id"] == receipt.decision_id
    assert fill.payload["source"] == "local_paper"
    replay = broker.fill_next_bar(
        order.client_order_id,
        signal_bar=_bar(NOW - timedelta(minutes=1)),
        execution_bar=_bar(NOW),
    )
    assert replay.fill == execution.fill
    assert len([event for event in store.iter_events() if event.event_type == "fill"]) == 1
    safe = prepared.safe_payload()
    assert set(safe) == {
        "schema_version",
        "kind",
        "route",
        "receipt_ref",
        "status",
        "reason",
        "price_contract_ref",
    }
    assert safe["price_contract_ref"] is None
    assert not {"symbol", "exchange", "quantity", "limit_price"}.intersection(safe)


def test_abstain_future_and_binding_mismatch_never_rehydrate_to_local_paper_intent() -> None:
    abstain = _receipt(action="abstain")
    unavailable = _receipt(action="abstain", input_status="unqualified")
    mismatched = PaperDecisionExecutionBinding(
        proposal_ref=_ref("e"),
        symbol="QQQ",
        exchange="NASD",
        quantity=Decimal("2"),
    )

    for receipt, binding, as_of, reason in (
        (abstain, _binding(abstain), NOW, "receipt_not_eligible"),
        (unavailable, _binding(unavailable), NOW, "receipt_not_eligible"),
        (abstain, _binding(abstain), NOW - timedelta(seconds=1), "receipt_not_eligible"),
        (_receipt(), _binding(_receipt()), NOW - timedelta(seconds=1), "receipt_not_current"),
        (_receipt(), _binding(_receipt()), NOW + timedelta(minutes=3), "receipt_not_current"),
        (_receipt(), mismatched, NOW, "binding_mismatch"),
    ):
        prepared = prepare_local_paper_intent(receipt, binding=binding, as_of=as_of)

        assert prepared.status == "no_intent"
        assert prepared.reason == reason
        assert prepared.local_paper_intent is None


def test_eligible_receipt_can_prepare_but_not_submit_a_tick_valid_kis_paper_decision() -> None:
    receipt = _receipt()
    binding = _binding(receipt)
    prepared = prepare_kis_paper_decision(
        receipt,
        binding=binding,
        limit_proof=_limit_proof(receipt),
        as_of=NOW,
    )

    assert prepared.status == "ready"
    assert prepared.kis_paper_decision is not None
    decision = prepared.kis_paper_decision
    assert decision.decision_id == f"receipt-{receipt_attribution_ref(receipt)[7:]}"
    assert decision.quantity == Decimal("2")
    assert prepared.safe_payload() == {
        "schema_version": 1,
        "kind": "paper_decision_bridge_result",
        "route": "kis_paper",
        "receipt_ref": receipt_attribution_ref(receipt),
        "status": "ready",
        "reason": "eligible",
        "price_contract_ref": f"sha256:{'e' * 64}",
    }

    mismatched_proof = _limit_proof(receipt, receipt_id=f"decision:sha256:{'f' * 64}")
    blocked = prepare_kis_paper_decision(
        receipt,
        binding=binding,
        limit_proof=mismatched_proof,
        as_of=NOW,
    )
    assert blocked.status == "no_intent"
    assert blocked.reason == "price_proof_receipt_mismatch"
    assert blocked.kis_paper_decision is None


def test_eligible_exit_receipt_keeps_sell_identity_on_both_paper_routes() -> None:
    receipt = _receipt(action="exit")
    binding = _binding(receipt)

    local = prepare_local_paper_intent(
        receipt,
        binding=_local_target_binding(
            receipt,
            target_exposure=Decimal("0"),
            current_quantity=Decimal("5"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=NOW,
    )
    paper = prepare_kis_paper_decision(
        receipt,
        binding=binding,
        limit_proof=_limit_proof(receipt),
        as_of=NOW,
    )

    assert local.status == paper.status == "ready"
    assert local.local_paper_intent is not None
    assert local.local_paper_intent.side == "sell"
    assert local.local_paper_intent.quantity == Decimal("5")
    assert paper.kis_paper_decision is not None
    assert paper.kis_paper_decision.side == "sell"


def test_local_target_already_satisfied_remains_a_scoped_no_intent() -> None:
    receipt = _receipt()

    prepared = prepare_local_paper_intent(
        receipt,
        binding=_local_target_binding(
            receipt,
            target_exposure=Decimal("0.5"),
            current_quantity=Decimal("5"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=NOW,
    )

    assert prepared.status == "no_intent"
    assert prepared.reason == "target_already_satisfied"
    assert prepared.local_paper_intent is None


def test_entry_receipt_rejects_a_nonpositive_execution_target() -> None:
    receipt = _receipt()

    prepared = prepare_local_paper_intent(
        receipt,
        binding=_local_target_binding(
            receipt,
            target_exposure=Decimal("0"),
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=NOW,
    )

    assert prepared.status == "no_intent"
    assert prepared.reason == "target_binding_mismatch"
    assert prepared.local_paper_intent is None


def test_local_target_binding_requires_the_receipt_committed_symbol_and_exposure() -> None:
    receipt = _receipt(target_exposure=Decimal("0.20"))
    for binding, reason in (
        (
            LocalPaperTargetBinding(
                proposal_ref=receipt.proposal_ref,
                symbol="SPY",
                target_exposure=Decimal("1"),
                current_quantity=Decimal("0"),
                maximum_quantity=Decimal("10"),
            ),
            "binding_mismatch",
        ),
        (
            LocalPaperTargetBinding(
                proposal_ref=receipt.proposal_ref,
                symbol="QQQ",
                target_exposure=Decimal("1"),
                current_quantity=Decimal("0"),
                maximum_quantity=Decimal("10"),
            ),
            "target_binding_mismatch",
        ),
    ):
        prepared = prepare_local_paper_intent(receipt, binding=binding, as_of=NOW)

        assert prepared.status == "no_intent"
        assert prepared.reason == reason
        assert prepared.local_paper_intent is None
        assert prepared.kis_paper_decision is None


def test_kis_paper_binding_requires_the_receipt_committed_instrument() -> None:
    receipt = _receipt()
    mismatched = PaperDecisionExecutionBinding(
        proposal_ref=receipt.proposal_ref,
        symbol="SPY",
        exchange="AMEX",
        quantity=Decimal("1"),
    )

    prepared = prepare_kis_paper_decision(
        receipt,
        binding=mismatched,
        limit_proof=_limit_proof(receipt),
        as_of=NOW,
    )

    assert prepared.status == "no_intent"
    assert prepared.reason == "binding_mismatch"
    assert prepared.kis_paper_decision is None


def test_legacy_receipt_without_binding_commitments_fails_closed_for_execution() -> None:
    receipt = _receipt()
    legacy = ResearchDecisionReceipt(
        campaign_ref=receipt.campaign_ref,
        model_ref=receipt.model_ref,
        input_manifest_ref=receipt.input_manifest_ref,
        proposal_ref=receipt.proposal_ref,
        decision_id=decision_receipt._derive_decision_id(
            campaign_ref=receipt.campaign_ref,
            model_ref=receipt.model_ref,
            input_manifest_ref=receipt.input_manifest_ref,
            proposal_ref=receipt.proposal_ref,
            instrument_binding_ref=None,
            target_binding_ref=None,
            decision_class=receipt.decision_class,
            input_status=receipt.input_status,
            decided_at=receipt.decided_at,
            valid_until=receipt.valid_until,
            reason_class=receipt.reason_class,
            schema_version=receipt.schema_version,
        ),
        decision_class=receipt.decision_class,
        input_status=receipt.input_status,
        decided_at=receipt.decided_at,
        valid_until=receipt.valid_until,
        reason_class=receipt.reason_class,
    )

    prepared = prepare_local_paper_intent(
        legacy,
        binding=_local_target_binding(
            legacy,
            target_exposure=Decimal("0.5"),
            current_quantity=Decimal("0"),
            maximum_quantity=Decimal("10"),
        ),
        as_of=NOW,
    )

    assert legacy.instrument_binding_ref is None
    assert legacy.target_binding_ref is None
    assert prepared.status == "no_intent"
    assert prepared.reason == "binding_mismatch"
    assert prepared.local_paper_intent is None

    paper = prepare_kis_paper_decision(
        legacy,
        binding=_binding(legacy),
        limit_proof=_limit_proof(legacy),
        as_of=NOW,
    )

    assert paper.status == "no_intent"
    assert paper.reason == "binding_mismatch"
    assert paper.kis_paper_decision is None


def test_local_target_binding_cannot_prepare_a_kis_paper_decision() -> None:
    receipt = _receipt()

    with pytest.raises(TypeError, match="paper execution binding"):
        prepare_kis_paper_decision(
            receipt,
            binding=_local_target_binding(
                receipt,
                target_exposure=Decimal("0.5"),
                current_quantity=Decimal("1"),
                maximum_quantity=Decimal("10"),
            ),  # type: ignore[arg-type]
            limit_proof=_limit_proof(receipt),
            as_of=NOW,
        )


def test_bridge_is_offline_and_does_not_read_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("receipt bridge must remain offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    receipt = _receipt()
    local_binding = _local_target_binding(
        receipt,
        target_exposure=Decimal("0.5"),
        current_quantity=Decimal("1"),
        maximum_quantity=Decimal("10"),
    )

    local = prepare_local_paper_intent(receipt, binding=local_binding, as_of=NOW)
    paper = prepare_kis_paper_decision(
        receipt,
        binding=_binding(receipt),
        limit_proof=_limit_proof(receipt),
        as_of=NOW,
    )

    assert local.status == "ready"
    assert paper.status == "ready"
    source = inspect.getsource(paper_decision_bridge).lower()
    for forbidden in (
        "kis_readonly",
        "kis_market_data",
        "socket",
        "urllib",
        "dotenv",
        "kis_live",
        ".env",
    ):
        assert forbidden not in source


def _receipt(
    *,
    action: str = "enter",
    input_status: str = "ready",
    target_exposure: Decimal | None = None,
) -> ResearchDecisionReceipt:
    resolved_target_exposure = (
        Decimal("0.5") if action == "enter" else Decimal("0")
    ) if target_exposure is None else target_exposure
    proposal = TargetExposureProposal(
        proposal_id="source-proposal-not-exported",
        symbol="QQQ",
        market="US",
        action=action,  # type: ignore[arg-type]
        target_exposure=resolved_target_exposure,
        confidence=Decimal("0.55") if input_status == "ready" else Decimal("0"),
        feature_schema_id="unit-feature-schema",
        input_status=input_status,  # type: ignore[arg-type]
        decided_at=NOW,
        valid_until=NOW + timedelta(minutes=2),
        feature_window_end=NOW,
        reason="not-exported-to-receipt",
    )
    return receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_ref("a"),
            model_ref=_ref("b"),
            input_manifest_ref=f"sha256:{'c' * 64}",
            proposal_ref=_ref("d"),
        ),
    )


def _binding(receipt: ResearchDecisionReceipt) -> PaperDecisionExecutionBinding:
    return PaperDecisionExecutionBinding(
        proposal_ref=receipt.proposal_ref,
        symbol="QQQ",
        exchange="NASD",
        quantity=Decimal("2"),
    )


def _local_target_binding(
    receipt: ResearchDecisionReceipt,
    *,
    target_exposure: Decimal,
    current_quantity: Decimal,
    maximum_quantity: Decimal,
) -> LocalPaperTargetBinding:
    return LocalPaperTargetBinding(
        proposal_ref=receipt.proposal_ref,
        symbol="QQQ",
        target_exposure=target_exposure,
        current_quantity=current_quantity,
        maximum_quantity=maximum_quantity,
    )


def _limit_proof(
    receipt: ResearchDecisionReceipt,
    *,
    receipt_id: str | None = None,
) -> KisPaperLimitProof:
    return KisPaperLimitProof(
        receipt_id=receipt.decision_id if receipt_id is None else receipt_id,
        price_contract_ref=f"sha256:{'e' * 64}",
        symbol="QQQ",
        exchange="NASD",
        limit_price=Decimal("101.25"),
        observed_at=NOW - timedelta(seconds=30),
        valid_until=NOW + timedelta(minutes=1),
        final_limit_tick_valid=True,
    )


def _bar(start: datetime) -> Bar:
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start,
        open=Decimal("101"),
        high=Decimal("102"),
        low=Decimal("100"),
        close=Decimal("101.50"),
        volume=Decimal("1000"),
        complete=True,
    )


def _ref(value: str) -> str:
    return f"ref:{value * 32}"

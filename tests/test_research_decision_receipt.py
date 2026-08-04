from __future__ import annotations

import inspect
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from thericher_v2.contracts import Bar, TargetExposureProposal, Timeframe
from thericher_v2.data.kis_capability import (
    KisCapabilityQualification,
    KisCapabilityState,
    KisMarketDataCapability,
    KisStorageRightsStatus,
)
from thericher_v2.research import decision_receipt
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
    receipt_projection_for_target_action,
)
from thericher_v2.research.kis_paper_baseline import evaluate_kis_paper_baseline


def test_ready_baseline_proposal_projects_to_a_safe_deterministic_enter_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = _baseline_proposal(monkeypatch)
    references = _references()

    first = receipt_from_target_exposure_proposal(proposal, references=references)
    replay = receipt_from_target_exposure_proposal(proposal, references=references)

    assert first == replay
    assert first.canonical_json() == replay.canonical_json()
    assert first.decision_class == "enter"
    assert first.reason_class == "eligible_enter"
    assert first.input_status == "ready"
    assert first.decided_at.tzinfo is UTC
    assert first.valid_until.tzinfo is UTC
    assert set(first.to_payload()) == {
        "campaign_ref",
        "decision_class",
        "decision_id",
        "decided_at",
        "input_manifest_ref",
        "input_status",
        "instrument_binding_ref",
        "model_ref",
        "proposal_ref",
        "reason_class",
        "schema_version",
        "target_binding_ref",
        "valid_until",
    }
    assert first.instrument_binding_ref is not None
    assert first.target_binding_ref is not None
    assert first.instrument_binding_ref.startswith("ref:")
    assert first.target_binding_ref.startswith("ref:")
    serialized = first.canonical_json()
    for forbidden in (
        proposal.symbol,
        proposal.market,
        str(proposal.target_exposure),
        str(proposal.confidence),
        proposal.feature_schema_id,
        proposal.reason,
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize("status", ("future", "missing", "stale", "unqualified"))
def test_unready_proposal_is_an_explicit_unavailable_abstain(status: str) -> None:
    proposal = _proposal(
        action="abstain",
        input_status=status,
        reason="raw-context-is-not-exported",
    )

    receipt = receipt_from_target_exposure_proposal(proposal, references=_references())

    assert receipt.decision_class == "abstain"
    assert receipt.input_status == status
    assert receipt.reason_class == "input_unavailable"
    assert proposal.reason not in receipt.canonical_json()


def test_changed_capability_contract_projects_to_an_unavailable_abstain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    changed_capability = replace(capability, paging_facts="changed provider capability contract")
    bars = _bars(90)

    result = evaluate_kis_paper_baseline(
        bars,
        capability=changed_capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )
    receipt = receipt_from_target_exposure_proposal(result.proposal, references=_references())

    assert result.proposal.input_status == "unqualified"
    assert receipt.decision_class == "abstain"
    assert receipt.reason_class == "input_unavailable"


@pytest.mark.parametrize(
    ("action", "reason_class"),
    (
        ("hold", "non_entry_proposal"),
        ("reduce", "non_entry_proposal"),
        ("abstain", "model_abstain"),
    ),
)
def test_ready_non_enter_proposals_remain_abstentions(
    action: str,
    reason_class: str,
) -> None:
    receipt = receipt_from_target_exposure_proposal(
        _proposal(action=action, input_status="ready", reason="do-not-export-hold-detail"),
        references=_references(),
    )

    assert receipt.decision_class == "abstain"
    assert receipt.reason_class == reason_class


def test_receipt_projection_rejects_unknown_action_before_unavailable_input() -> None:
    with pytest.raises(ValueError, match="target action is invalid"):
        receipt_projection_for_target_action("future_action", input_status="missing")


def test_ready_exit_proposal_projects_to_an_explicit_exit_receipt() -> None:
    receipt = receipt_from_target_exposure_proposal(
        _proposal(action="exit", input_status="ready", reason="target-flat"),
        references=_references(),
    )

    assert receipt.decision_class == "exit"
    assert receipt.reason_class == "eligible_exit"


def test_exact_input_manifest_reference_and_derived_identity_are_required() -> None:
    proposal = _proposal(action="enter", input_status="ready", reason="not-exported")

    with pytest.raises(ValueError, match="exact sha256"):
        DecisionReceiptReferences(
            campaign_ref=_ref("a"),
            model_ref=_ref("b"),
            input_manifest_ref="sha256:abc123",
            proposal_ref=_ref("d"),
        )

    receipt = receipt_from_target_exposure_proposal(proposal, references=_references())
    changed_manifest_receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_ref("a"),
            model_ref=_ref("b"),
            input_manifest_ref=f"sha256:{'e' * 64}",
            proposal_ref=_ref("d"),
        ),
    )
    assert changed_manifest_receipt.decision_id != receipt.decision_id
    with pytest.raises(ValueError, match="immutable receipt payload"):
        ResearchDecisionReceipt(
            **{**receipt.__dict__, "decision_id": f"decision:sha256:{'0' * 64}"},
        )


def test_receipt_module_has_no_direct_external_or_execution_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("decision receipt must remain local and pure")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    receipt = receipt_from_target_exposure_proposal(
        _proposal(action="enter", input_status="ready", reason="not-exported"),
        references=_references(),
    )

    assert receipt.decision_class == "enter"
    source = inspect.getsource(decision_receipt).lower()
    for forbidden_import in (
        "thericher_v2.execution",
        "thericher_v2.data.kis",
        "requests",
        "urllib",
        "socket",
        "dotenv",
    ):
        assert forbidden_import not in source


def _baseline_proposal(monkeypatch: pytest.MonkeyPatch) -> TargetExposureProposal:
    capability = _qualified_capability()
    _trust_for_test(monkeypatch, capability)
    bars = _bars(90)
    result = evaluate_kis_paper_baseline(
        bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=bars[-1].end_ts,
    )
    assert result.proposal.action == "enter"
    return result.proposal


def _proposal(*, action: str, input_status: str, reason: str) -> TargetExposureProposal:
    decided_at = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)
    return TargetExposureProposal(
        proposal_id="proposal-contains-no-receipt-fields",
        symbol="QQQ",
        market="US",
        action=action,  # type: ignore[arg-type]
        target_exposure=Decimal("0.05") if action in {"enter", "hold"} else Decimal("0"),
        confidence=Decimal("0.55") if input_status == "ready" else Decimal("0"),
        feature_schema_id="test-feature-schema",
        input_status=input_status,  # type: ignore[arg-type]
        decided_at=decided_at,
        valid_until=decided_at + timedelta(minutes=10),
        feature_window_end=decided_at,
        reason=reason,
    )


def _references() -> DecisionReceiptReferences:
    return DecisionReceiptReferences(
        campaign_ref=_ref("a"),
        model_ref=_ref("b"),
        input_manifest_ref=f"sha256:{'c' * 64}",
        proposal_ref=_ref("d"),
    )


def _ref(value: str) -> str:
    return f"ref:{value * 32}"


def _bars(count: int) -> list[Bar]:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    result: list[Bar] = []
    for index in range(count):
        open_price = Decimal("100") + Decimal(index) / Decimal("100")
        close = open_price + Decimal("0.01")
        result.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start + timedelta(minutes=index),
                open=open_price,
                high=close + Decimal("0.01"),
                low=open_price - Decimal("0.01"),
                close=close,
                volume=Decimal("1000") + Decimal(index),
                complete=True,
            )
        )
    return result


def _qualified_capability() -> KisMarketDataCapability:
    return KisMarketDataCapability(
        capability_id="unit.kis.paper.raw-1m",
        state=KisCapabilityState.QUALIFIED,
        endpoint_category="overseas_stock_intraday",
        exchange_scope=("NAS",),
        symbol_scope=("QQQ",),
        raw_fields=("open", "high", "low", "last", "evol"),
        timeframe=Timeframe.M1,
        time_semantics="unit bar-open timestamp evidence",
        completed_bar_rule="unit current-minute exclusion",
        freshness_budget=timedelta(minutes=2),
        paging_facts="unit contiguous continuation",
        storage_rights=KisStorageRightsStatus.UNVERIFIED,
        evidence_reference="unit-capability-evidence",
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _trust_for_test(monkeypatch: pytest.MonkeyPatch, capability: KisMarketDataCapability) -> None:
    from thericher_v2.research import kis_paper_baseline

    monkeypatch.setattr(
        kis_paper_baseline,
        "trusted_kis_paper_baseline_qualifications",
        lambda: (
            KisCapabilityQualification(
                qualification_id=f"unit.qualification.{capability.capability_id}",
                capability_id=capability.capability_id,
                capability_contract_sha256=capability.contract_sha256,
                evidence_reference="unit-qualification-evidence",
                reviewed_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        ),
    )

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.execution.kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID,
    KIS_PAPER_US_CCNCL_TR_ID,
    KisPaperCanaryClient,
    KisPaperCanaryStateStore,
)
from thericher_v2.execution.kis_paper_quote import KisPaperSpyLimitInput
from thericher_v2.execution.kis_paper_receipt_canary import (
    prepare_kis_paper_spy_receipt_decision,
    receipt_canary_run_id,
    run_kis_paper_receipt_canary,
)
from thericher_v2.execution.kis_readonly import (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_BASE_URL,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperConfig,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

NOW = datetime(2026, 7, 22, 14, 30, tzinfo=UTC)


@dataclass
class FakePaperTransport:
    requests: list[KisHttpRequest] = field(default_factory=list)
    order_open: bool = False

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        self.requests.append(request)
        tr_id = request.headers.get("tr_id", "")
        if request.method == "POST" and request.url.endswith("/oauth2/tokenP"):
            return KisHttpResponse.from_payload({"access_token": "test-access-token"})
        if tr_id == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            self.order_open = True
            return KisHttpResponse.from_payload(
                {"rt_cd": "0", "output": {"ODNO": "ORD-123456789"}}
            )
        if tr_id == KIS_PAPER_US_CCNCL_TR_ID:
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_OPEN_ORDERS_ENDPOINT.tr_id:
            if self.order_open and request.query.get("OVRS_EXCG_CD") == "AMEX":
                return KisHttpResponse.from_payload(
                    {"rt_cd": "0", "output": [_matching_spy_open_order()]}
                )
            return KisHttpResponse.from_payload({"rt_cd": "0", "output": []})
        if tr_id == KIS_PAPER_BALANCE_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload({"rt_cd": "0", "output1": []})
        if tr_id == KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT.tr_id:
            return KisHttpResponse.from_payload(
                {
                    "rt_cd": "0",
                    "output": {
                        "tr_crcy_cd": "USD",
                        "ord_psbl_frcr_amt": "1200.50",
                        "ovrs_ord_psbl_amt": "1199.75",
                    },
                }
            )
        raise AssertionError(f"unexpected paper request: {request!r}")


class NoCredentialEnvironment(Mapping[str, str]):
    """Fails if receipt replay tries to consult credentials or a dotenv mapping."""

    def __getitem__(self, key: str) -> str:
        raise AssertionError(f"unexpected environment access: {key}")

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def test_receipt_reuses_first_paper_intent_without_credential_read_or_resubmit(
    tmp_path: Path,
) -> None:
    transport = FakePaperTransport()
    client = KisPaperCanaryClient(config=_config(), transport=transport)
    receipt = _eligible_receipt()
    first = _prepared(receipt, last=Decimal("500.25"), quoted_at=NOW)
    paths = _paths(tmp_path)

    first_outcome = run_kis_paper_receipt_canary(
        first,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        execute=True,
        cancel_after_submit=False,
        client=client,
        now=NOW,
        submit_permitted=lambda _now: True,
        **paths,
    )
    changed_price = _prepared(
        receipt,
        last=Decimal("600.25"),
        quoted_at=NOW + timedelta(seconds=30),
    )
    second_outcome = run_kis_paper_receipt_canary(
        changed_price,
        environment=NoCredentialEnvironment(),
        state_root=tmp_path / "private",
        execute=True,
        cancel_after_submit=False,
        client=client,
        now=NOW + timedelta(seconds=30),
        submit_permitted=lambda _now: True,
        **paths,
    )

    assert _submission_count(transport) == 1
    assert first_outcome.run_id == second_outcome.run_id == receipt_canary_run_id(first.receipt_ref)
    state = KisPaperCanaryStateStore(
        tmp_path / "private" / f"{first_outcome.run_id}.json"
    ).read()
    assert state is not None
    assert state.intent.price_contract_ref == first.price_contract_ref
    assert state.intent.price_contract_ref != changed_price.price_contract_ref
    assert all(request.url.startswith(KIS_PAPER_BASE_URL) for request in transport.requests)

    safe_evidence = first_outcome.evidence_path.read_text(encoding="utf-8")
    for forbidden in ("paper-app-secret", "12345678", "500.25", "600.25"):
        assert forbidden not in safe_evidence


def test_receipt_preparation_is_pure_and_rejects_an_ineligible_receipt() -> None:
    receipt = _eligible_receipt()
    prepared = _prepared(receipt, last=Decimal("500.25"), quoted_at=NOW)

    assert prepared.status == "ready"
    assert prepared.route == "kis_paper"
    assert prepared.price_contract_ref is not None
    assert receipt_canary_run_id(prepared.receipt_ref).startswith("receipt-")

    unavailable = TargetExposureProposal(
        proposal_id="daily-spy-unavailable",
        symbol="SPY",
        market="US",
        action="abstain",
        target_exposure=Decimal("0"),
        confidence=Decimal("0"),
        feature_schema_id="test.daily.spy",
        input_status="missing",
        decided_at=NOW,
        valid_until=NOW,
        feature_window_end=None,
        reason="input_missing",
    )
    unavailable_receipt = receipt_from_target_exposure_proposal(
        unavailable,
        references=_references("c"),
    )
    rejected = _prepared(unavailable_receipt, last=Decimal("500.25"), quoted_at=NOW)

    assert rejected.status == "no_intent"
    assert rejected.reason == "receipt_not_eligible"
    assert rejected.kis_paper_decision is None


def _prepared(
    receipt: ResearchDecisionReceipt,
    *,
    last: Decimal,
    quoted_at: datetime,
):
    return prepare_kis_paper_spy_receipt_decision(
        receipt,
        limit_input=KisPaperSpyLimitInput(
            last=last,
            decimal_places=2,
            tick_size=Decimal("0.01"),
            quoted_at=quoted_at,
        ),
        as_of=quoted_at,
    )


def _eligible_receipt() -> ResearchDecisionReceipt:
    proposal = TargetExposureProposal(
        proposal_id="daily-spy-enter",
        symbol="SPY",
        market="US",
        action="enter",
        target_exposure=Decimal("0.05"),
        confidence=Decimal("0.55"),
        feature_schema_id="test.daily.spy",
        input_status="ready",
        decided_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=5),
        feature_window_end=NOW - timedelta(minutes=1),
        reason="two_close_momentum_enter",
    )
    return receipt_from_target_exposure_proposal(proposal, references=_references("a"))


def _references(character: str) -> DecisionReceiptReferences:
    return DecisionReceiptReferences(
        campaign_ref=f"ref:{character * 64}",
        model_ref=f"ref:{character * 63}b",
        input_manifest_ref="sha256:" + character * 64,
        proposal_ref=f"ref:{character * 62}cc",
    )


def _config() -> KisPaperConfig:
    return KisPaperConfig(
        app_key="paper-app-key",
        app_secret="paper-app-secret",
        account_number="12345678",
        account_product_code="01",
    )


def _paths(tmp_path: Path) -> dict[str, Path]:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    return {
        "runtime_projection_path": tmp_path / "runtime" / "canary.json",
        "paper_account_snapshot_path": tmp_path / "runtime" / "account.json",
        "emergency_state_path": tmp_path / "emergency" / "state.json",
        "artifact_root": tmp_path / "artifacts",
        "repository_root": repository_root,
    }


def _matching_spy_open_order() -> dict[str, str]:
    return {
        "odno": "ORD-123456789",
        "pdno": "SPY",
        "ovrs_excg_cd": "AMEX",
        "tr_crcy_cd": "USD",
        "sll_buy_dvsn_cd": "02",
        "ft_ord_qty": "1",
        "ft_ccld_qty": "0",
        "nccs_qty": "1",
        "ft_ord_unpr3": "500.00",
    }


def _submission_count(transport: FakePaperTransport) -> int:
    return sum(
        request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        for request in transport.requests
    )

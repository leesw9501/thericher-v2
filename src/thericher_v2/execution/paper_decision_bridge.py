"""Pure preparation from a research receipt to private paper decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final, Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    OrderIntent,
    TargetExposureProposal,
    decimal_value,
    decision_instrument_binding_ref,
    decision_target_binding_ref,
    positive,
    require_utc,
)

from .target_position import target_proposal_to_order_intent

if TYPE_CHECKING:
    from thericher_v2.research.decision_receipt import ResearchDecisionReceipt
    from thericher_v2.research.kis_paper_canary_intent import KisPaperCanaryOrderDecision

_OPAQUE_REFERENCE: Final = re.compile(r"ref:[0-9a-f]{32,128}")
_SHA256_REFERENCE: Final = re.compile(r"sha256:[0-9a-f]{64}")
_RECEIPT_DECISION_ID: Final = re.compile(r"decision:sha256:([0-9a-f]{64})")
_US_SYMBOL: Final = re.compile(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*")
_US_EXCHANGES: Final = frozenset({"NASD", "NYSE", "AMEX"})

BridgeRoute = Literal["local_paper", "kis_paper"]
BridgeStatus = Literal["ready", "no_intent"]
BridgeReason = Literal[
    "eligible",
    "receipt_not_eligible",
    "receipt_not_current",
    "binding_mismatch",
    "target_binding_mismatch",
    "target_already_satisfied",
    "price_proof_receipt_mismatch",
    "price_proof_binding_mismatch",
    "price_proof_not_current",
    "price_proof_tick_invalid",
]


@dataclass(frozen=True)
class PaperDecisionExecutionBinding:
    """Execution-owned symbol, venue, and whole-share binding for one receipt."""

    proposal_ref: str
    symbol: str
    exchange: str
    quantity: Decimal
    market: Literal["US"] = "US"

    def __post_init__(self) -> None:
        if _OPAQUE_REFERENCE.fullmatch(self.proposal_ref) is None:
            raise ValueError("proposal_ref must be an opaque reference")
        _require_us_symbol(self.symbol)
        if self.exchange not in _US_EXCHANGES:
            raise ValueError("exchange must be a supported US exchange")
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        if self.quantity != self.quantity.to_integral_value():
            raise ValueError("quantity must be whole shares")
        if self.market != "US":
            raise ValueError("market must be US")


@dataclass(frozen=True)
class LocalPaperTargetBinding:
    """Execution-owned target weight and position snapshot for one local receipt."""

    proposal_ref: str
    symbol: str
    target_exposure: Decimal
    current_quantity: Decimal
    maximum_quantity: Decimal
    market: Literal["US"] = "US"

    def __post_init__(self) -> None:
        if _OPAQUE_REFERENCE.fullmatch(self.proposal_ref) is None:
            raise ValueError("proposal_ref must be an opaque reference")
        _require_us_symbol(self.symbol)
        target_exposure = decimal_value(self.target_exposure, "target_exposure")
        current_quantity = decimal_value(self.current_quantity, "current_quantity")
        maximum_quantity = decimal_value(self.maximum_quantity, "maximum_quantity")
        if target_exposure < 0 or target_exposure > Decimal("1"):
            raise ValueError("target_exposure must be between 0 and 1")
        if current_quantity < 0:
            raise ValueError("current_quantity must be non-negative")
        if maximum_quantity <= 0:
            raise ValueError("maximum_quantity must be positive")
        object.__setattr__(self, "target_exposure", target_exposure)
        object.__setattr__(self, "current_quantity", current_quantity)
        object.__setattr__(self, "maximum_quantity", maximum_quantity)
        if self.market != "US":
            raise ValueError("market must be US")


@dataclass(frozen=True)
class KisPaperLimitProof:
    """Private execution proof for a final tick-valid virtual-paper limit."""

    receipt_id: str
    price_contract_ref: str
    symbol: str
    exchange: str
    limit_price: Decimal
    observed_at: datetime
    valid_until: datetime
    final_limit_tick_valid: bool

    def __post_init__(self) -> None:
        _receipt_digest(self.receipt_id)
        if _SHA256_REFERENCE.fullmatch(self.price_contract_ref) is None:
            raise ValueError("price_contract_ref must be an exact sha256 reference")
        _require_us_symbol(self.symbol)
        if self.exchange not in _US_EXCHANGES:
            raise ValueError("exchange must be a supported US exchange")
        object.__setattr__(self, "limit_price", positive(self.limit_price, "limit_price"))
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until <= self.observed_at:
            raise ValueError("limit proof validity is invalid")
        if not isinstance(self.final_limit_tick_valid, bool):
            raise ValueError("final_limit_tick_valid must be boolean")


@dataclass(frozen=True)
class PaperDecisionBridgeResult:
    """A safe no-intent fact or a private order/decision prepared for one route."""

    route: BridgeRoute
    receipt_ref: str
    status: BridgeStatus
    reason: BridgeReason
    local_paper_intent: OrderIntent | None = None
    kis_paper_decision: KisPaperCanaryOrderDecision | None = None
    price_contract_ref: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.route not in {"local_paper", "kis_paper"}:
            raise ValueError("route is invalid")
        _require_sha256_reference(self.receipt_ref, "receipt_ref")
        if self.status not in {"ready", "no_intent"}:
            raise ValueError("status is invalid")
        if self.reason not in {
            "eligible",
            "receipt_not_eligible",
            "receipt_not_current",
            "binding_mismatch",
            "target_binding_mismatch",
            "target_already_satisfied",
            "price_proof_receipt_mismatch",
            "price_proof_binding_mismatch",
            "price_proof_not_current",
            "price_proof_tick_invalid",
        }:
            raise ValueError("reason is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported bridge schema_version")
        ready_local = self.status == "ready" and self.route == "local_paper"
        ready_kis = self.status == "ready" and self.route == "kis_paper"
        if ready_local != (self.local_paper_intent is not None):
            raise ValueError("local paper intent does not match bridge status")
        if ready_kis != (self.kis_paper_decision is not None):
            raise ValueError("KIS paper decision does not match bridge status")
        if self.status == "ready" and self.reason != "eligible":
            raise ValueError("ready bridge result must be eligible")
        if self.status == "no_intent" and (
            self.local_paper_intent is not None or self.kis_paper_decision is not None
        ):
            raise ValueError("no-intent bridge result cannot contain an execution object")
        if ready_kis:
            _require_sha256_reference(self.price_contract_ref, "price_contract_ref")
        elif self.price_contract_ref is not None:
            raise ValueError("only a ready KIS result can carry a price contract reference")

    def safe_payload(self) -> dict[str, object]:
        """Expose only route, receipt identity, and categorical preparation state."""

        return {
            "schema_version": self.schema_version,
            "kind": "paper_decision_bridge_result",
            "route": self.route,
            "receipt_ref": self.receipt_ref,
            "status": self.status,
            "reason": self.reason,
            "price_contract_ref": self.price_contract_ref,
        }


def prepare_local_paper_intent(
    receipt: ResearchDecisionReceipt,
    *,
    binding: PaperDecisionExecutionBinding | LocalPaperTargetBinding,
    as_of: datetime,
) -> PaperDecisionBridgeResult:
    """Prepare a deterministic local-paper target delta without external access."""

    if not isinstance(binding, (PaperDecisionExecutionBinding, LocalPaperTargetBinding)):
        raise TypeError("local paper requires a supported execution binding")
    now = require_utc(as_of, "as_of")
    reason = _eligibility_reason(receipt=receipt, binding=binding, as_of=now)
    receipt_ref = receipt_attribution_ref(receipt)
    if reason is not None:
        return _no_intent(route="local_paper", receipt_ref=receipt_ref, reason=reason)
    digest = _receipt_digest(receipt.decision_id)
    target_binding = (
        binding
        if isinstance(binding, LocalPaperTargetBinding)
        else _legacy_local_target_binding(receipt=receipt, binding=binding)
    )
    if not _matches_target_binding(receipt=receipt, binding=target_binding):
        return _no_intent(
            route="local_paper",
            receipt_ref=receipt_ref,
            reason="target_binding_mismatch",
        )
    proposal = _local_target_proposal(receipt=receipt, binding=target_binding)
    if proposal is None:
        return _no_intent(
            route="local_paper",
            receipt_ref=receipt_ref,
            reason="target_binding_mismatch",
        )
    intent = target_proposal_to_order_intent(
        proposal,
        client_order_id=f"local-receipt-{digest}",
        current_quantity=target_binding.current_quantity,
        maximum_quantity=target_binding.maximum_quantity,
        as_of=now,
    )
    if intent is None:
        return _no_intent(
            route="local_paper",
            receipt_ref=receipt_ref,
            reason="target_already_satisfied",
        )
    return PaperDecisionBridgeResult(
        route="local_paper",
        receipt_ref=receipt_ref,
        status="ready",
        reason="eligible",
        local_paper_intent=intent,
    )


def prepare_kis_paper_decision(
    receipt: ResearchDecisionReceipt,
    *,
    binding: PaperDecisionExecutionBinding,
    limit_proof: KisPaperLimitProof,
    as_of: datetime,
) -> PaperDecisionBridgeResult:
    """Prepare an existing virtual-paper entry or exit decision without submitting it."""

    from thericher_v2.research.kis_paper_canary_intent import (
        KisPaperCanaryBuyDecision,
        KisPaperCanarySellDecision,
    )

    if not isinstance(binding, PaperDecisionExecutionBinding):
        raise TypeError("KIS paper requires a paper execution binding")
    now = require_utc(as_of, "as_of")
    receipt_ref = receipt_attribution_ref(receipt)
    reason = _eligibility_reason(receipt=receipt, binding=binding, as_of=now)
    if reason is not None:
        return _no_intent(route="kis_paper", receipt_ref=receipt_ref, reason=reason)
    if limit_proof.receipt_id != receipt.decision_id:
        return _no_intent(
            route="kis_paper",
            receipt_ref=receipt_ref,
            reason="price_proof_receipt_mismatch",
        )
    if limit_proof.symbol != binding.symbol or limit_proof.exchange != binding.exchange:
        return _no_intent(
            route="kis_paper",
            receipt_ref=receipt_ref,
            reason="price_proof_binding_mismatch",
        )
    if now < limit_proof.observed_at or now >= limit_proof.valid_until:
        return _no_intent(
            route="kis_paper",
            receipt_ref=receipt_ref,
            reason="price_proof_not_current",
        )
    if not limit_proof.final_limit_tick_valid:
        return _no_intent(
            route="kis_paper",
            receipt_ref=receipt_ref,
            reason="price_proof_tick_invalid",
        )
    digest = _receipt_digest(receipt.decision_id)
    decision: KisPaperCanaryOrderDecision
    if receipt.decision_class == "enter":
        decision = KisPaperCanaryBuyDecision(
            decision_id=f"receipt-{digest}",
            symbol=binding.symbol,
            exchange=binding.exchange,
            quantity=binding.quantity,
            limit_price=limit_proof.limit_price,
            decision_as_of=now,
            valid_until=min(receipt.valid_until, limit_proof.valid_until),
        )
    else:
        decision = KisPaperCanarySellDecision(
            decision_id=f"receipt-{digest}",
            symbol=binding.symbol,
            exchange=binding.exchange,
            quantity=binding.quantity,
            limit_price=limit_proof.limit_price,
            decision_as_of=now,
            valid_until=min(receipt.valid_until, limit_proof.valid_until),
        )
    return PaperDecisionBridgeResult(
        route="kis_paper",
        receipt_ref=receipt_ref,
        status="ready",
        reason="eligible",
        kis_paper_decision=decision,
        price_contract_ref=limit_proof.price_contract_ref,
    )


def receipt_attribution_ref(receipt: ResearchDecisionReceipt) -> str:
    """Return the full opaque receipt digest used for cross-route attribution."""

    return "sha256:" + _receipt_digest(receipt.decision_id)


def _eligibility_reason(
    *,
    receipt: ResearchDecisionReceipt,
    binding: PaperDecisionExecutionBinding | LocalPaperTargetBinding,
    as_of: datetime,
) -> BridgeReason | None:
    if binding.proposal_ref != receipt.proposal_ref:
        return "binding_mismatch"
    if not _matches_instrument_binding(receipt=receipt, binding=binding):
        return "binding_mismatch"
    eligible_shape = (
        receipt.decision_class == "enter" and receipt.reason_class == "eligible_enter"
    ) or (receipt.decision_class == "exit" and receipt.reason_class == "eligible_exit")
    if not eligible_shape or receipt.input_status != "ready":
        return "receipt_not_eligible"
    if as_of < receipt.decided_at or as_of >= receipt.valid_until:
        return "receipt_not_current"
    return None


def _matches_instrument_binding(
    *,
    receipt: ResearchDecisionReceipt,
    binding: PaperDecisionExecutionBinding | LocalPaperTargetBinding,
) -> bool:
    if receipt.instrument_binding_ref is None:
        return False
    return receipt.instrument_binding_ref == decision_instrument_binding_ref(
        symbol=binding.symbol,
        market=binding.market,
        decision_class=receipt.decision_class,
    )


def _matches_target_binding(
    *,
    receipt: ResearchDecisionReceipt,
    binding: LocalPaperTargetBinding,
) -> bool:
    if receipt.target_binding_ref is None:
        return False
    return receipt.target_binding_ref == decision_target_binding_ref(
        symbol=binding.symbol,
        market=binding.market,
        decision_class=receipt.decision_class,
        target_exposure=binding.target_exposure,
    )


def _legacy_local_target_binding(
    *,
    receipt: ResearchDecisionReceipt,
    binding: PaperDecisionExecutionBinding,
) -> LocalPaperTargetBinding:
    """Preserve fixed-lot local callers while routing them through target sizing."""

    if receipt.decision_class == "enter":
        target_exposure = Decimal("1")
        current_quantity = Decimal("0")
    elif receipt.decision_class == "exit":
        target_exposure = Decimal("0")
        current_quantity = binding.quantity
    else:  # pragma: no cover - eligibility filters non-actionable receipts.
        raise ValueError("eligible local receipt must be enter or exit")
    return LocalPaperTargetBinding(
        proposal_ref=binding.proposal_ref,
        symbol=binding.symbol,
        market=binding.market,
        target_exposure=target_exposure,
        current_quantity=current_quantity,
        maximum_quantity=binding.quantity,
    )


def _local_target_proposal(
    *,
    receipt: ResearchDecisionReceipt,
    binding: LocalPaperTargetBinding,
) -> TargetExposureProposal | None:
    if receipt.decision_class == "enter":
        if binding.target_exposure <= 0:
            return None
        action: Literal["enter", "exit"] = "enter"
    elif receipt.decision_class == "exit":
        if binding.target_exposure != 0:
            return None
        action = "exit"
    else:  # pragma: no cover - eligibility filters non-actionable receipts.
        raise ValueError("eligible local receipt must be enter or exit")
    return TargetExposureProposal(
        proposal_id=receipt.decision_id,
        symbol=binding.symbol,
        market=binding.market,
        action=action,
        target_exposure=binding.target_exposure,
        confidence=Decimal("1"),
        feature_schema_id="execution-target-bridge-v1",
        input_status="ready",
        decided_at=receipt.decided_at,
        valid_until=receipt.valid_until,
        feature_window_end=receipt.decided_at,
        reason="receipt_bound_execution_target",
    )


def _no_intent(
    *,
    route: BridgeRoute,
    receipt_ref: str,
    reason: BridgeReason,
) -> PaperDecisionBridgeResult:
    return PaperDecisionBridgeResult(
        route=route,
        receipt_ref=receipt_ref,
        status="no_intent",
        reason=reason,
    )


def _receipt_digest(value: str) -> str:
    match = _RECEIPT_DECISION_ID.fullmatch(value)
    if match is None:
        raise ValueError("receipt decision_id must be a canonical digest identity")
    return match.group(1)


def _require_sha256_reference(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_REFERENCE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact sha256 reference")


def _require_us_symbol(value: str) -> None:
    if not isinstance(value, str) or _US_SYMBOL.fullmatch(value) is None:
        raise ValueError("symbol must be an uppercase US ticker")

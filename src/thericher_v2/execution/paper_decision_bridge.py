"""Pure preparation from a research receipt to private paper decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION, OrderIntent, positive, require_utc
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt
from thericher_v2.research.kis_paper_canary_intent import (
    KisPaperCanaryBuyDecision,
    KisPaperCanaryOrderDecision,
    KisPaperCanarySellDecision,
)

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
    binding: PaperDecisionExecutionBinding,
    as_of: datetime,
) -> PaperDecisionBridgeResult:
    """Prepare a deterministic local-paper entry or exit without external access."""

    now = require_utc(as_of, "as_of")
    reason = _eligibility_reason(receipt=receipt, binding=binding, as_of=now)
    receipt_ref = receipt_attribution_ref(receipt)
    if reason is not None:
        return _no_intent(route="local_paper", receipt_ref=receipt_ref, reason=reason)
    digest = _receipt_digest(receipt.decision_id)
    return PaperDecisionBridgeResult(
        route="local_paper",
        receipt_ref=receipt_ref,
        status="ready",
        reason="eligible",
        local_paper_intent=OrderIntent(
            client_order_id=f"local-receipt-{digest}",
            symbol=binding.symbol,
            market=binding.market,
            side="buy" if receipt.decision_class == "enter" else "sell",
            quantity=binding.quantity,
            limit_price=None,
            decision_id=receipt.decision_id,
            created_at=now,
        ),
    )


def prepare_kis_paper_decision(
    receipt: ResearchDecisionReceipt,
    *,
    binding: PaperDecisionExecutionBinding,
    limit_proof: KisPaperLimitProof,
    as_of: datetime,
) -> PaperDecisionBridgeResult:
    """Prepare an existing virtual-paper entry or exit decision without submitting it."""

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
    if (
        limit_proof.symbol != binding.symbol
        or limit_proof.exchange != binding.exchange
    ):
        return _no_intent(
            route="kis_paper",
            receipt_ref=receipt_ref,
            reason="price_proof_binding_mismatch",
        )
    if now < limit_proof.observed_at or now > limit_proof.valid_until:
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
    binding: PaperDecisionExecutionBinding,
    as_of: datetime,
) -> BridgeReason | None:
    if binding.proposal_ref != receipt.proposal_ref:
        return "binding_mismatch"
    eligible_shape = (
        (receipt.decision_class == "enter" and receipt.reason_class == "eligible_enter")
        or (receipt.decision_class == "exit" and receipt.reason_class == "eligible_exit")
    )
    if not eligible_shape or receipt.input_status != "ready":
        return "receipt_not_eligible"
    if as_of < receipt.decided_at or as_of > receipt.valid_until:
        return "receipt_not_current"
    return None


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

"""Fail-closed receipt lineage for already replayed local-paper PnL.

This leaf joins immutable research decision receipts to the existing FIFO
local-paper accounting projection.  It is deliberately not a model evaluation
or broker-PnL surface: callers receive accounting provenance only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, decision_instrument_binding_ref
from thericher_v2.execution.local_paper import (
    LocalPaperDecisionPnl,
    LocalPaperDecisionPnlSegment,
)
from thericher_v2.execution.paper_decision_bridge import receipt_attribution_ref
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt


@dataclass(frozen=True)
class LocalPaperReceiptLineage:
    """Opaque immutable receipt references for one local-paper decision."""

    decision_id: str
    receipt_ref: str
    campaign_ref: str
    model_ref: str
    input_manifest_ref: str
    proposal_ref: str
    decision_class: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not self.decision_id.startswith("decision:sha256:")
            or not self.receipt_ref.startswith("sha256:")
            or not self.campaign_ref.startswith("ref:")
            or not self.model_ref.startswith("ref:")
            or not self.input_manifest_ref.startswith("sha256:")
            or not self.proposal_ref.startswith("ref:")
            or self.decision_class not in {"enter", "exit"}
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("local-paper receipt lineage is invalid")


@dataclass(frozen=True)
class LocalPaperReceiptPnlSegment:
    """One existing closed FIFO segment joined to immutable decision receipts."""

    accounting: LocalPaperDecisionPnlSegment
    entry_receipt: LocalPaperReceiptLineage
    exit_receipt: LocalPaperReceiptLineage
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accounting, LocalPaperDecisionPnlSegment)
            or self.accounting.entry_decision_id != self.entry_receipt.decision_id
            or self.accounting.exit_decision_id != self.exit_receipt.decision_id
            or self.entry_receipt.decision_class != "enter"
            or self.exit_receipt.decision_class != "exit"
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("local-paper receipt PnL segment is invalid")


@dataclass(frozen=True)
class LocalPaperReceiptPnlAttribution:
    """Accounting provenance joining a verified local-paper projection to receipts.

    The result does not establish causal decision credit, model performance,
    broker PnL, or a Paper-trading outcome.
    """

    accounting: LocalPaperDecisionPnl
    closed_segments: tuple[LocalPaperReceiptPnlSegment, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.accounting, LocalPaperDecisionPnl)
            or tuple(segment.accounting for segment in self.closed_segments)
            != self.accounting.closed_segments
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("local-paper receipt PnL attribution is invalid")


def attribute_local_paper_decision_pnl_to_receipts(
    accounting: LocalPaperDecisionPnl,
    receipts: Sequence[ResearchDecisionReceipt],
) -> LocalPaperReceiptPnlAttribution:
    """Join verified local-paper FIFO segments to supplied canonical receipts.

    Missing, duplicate, role-incompatible, or instrument-incompatible receipts
    fail closed.  This function intentionally does not compare receipt and fill
    timestamps because a valid date-labeled local replay can preserve sequence
    order while using a source session label as its fill timestamp.
    """

    if not isinstance(accounting, LocalPaperDecisionPnl):
        raise TypeError("accounting must be LocalPaperDecisionPnl")
    receipt_index = _build_receipt_index(receipts)
    segments = tuple(
        _attribute_segment(segment, receipt_index)
        for segment in accounting.closed_segments
    )
    return LocalPaperReceiptPnlAttribution(accounting=accounting, closed_segments=segments)


def _build_receipt_index(
    receipts: Sequence[ResearchDecisionReceipt],
) -> dict[str, ResearchDecisionReceipt]:
    index: dict[str, ResearchDecisionReceipt] = {}
    for receipt in receipts:
        if not isinstance(receipt, ResearchDecisionReceipt):
            raise TypeError("receipts must contain ResearchDecisionReceipt values")
        if receipt.decision_id in index:
            raise ValueError("duplicate decision receipt identity")
        index[receipt.decision_id] = receipt
    return index


def _attribute_segment(
    segment: LocalPaperDecisionPnlSegment,
    receipt_index: dict[str, ResearchDecisionReceipt],
) -> LocalPaperReceiptPnlSegment:
    entry_receipt = receipt_index.get(segment.entry_decision_id)
    if entry_receipt is None:
        raise ValueError("entry decision receipt is missing")
    exit_receipt = receipt_index.get(segment.exit_decision_id)
    if exit_receipt is None:
        raise ValueError("exit decision receipt is missing")
    _verify_receipt_role(entry_receipt, segment=segment, role="entry")
    _verify_receipt_role(exit_receipt, segment=segment, role="exit")
    return LocalPaperReceiptPnlSegment(
        accounting=segment,
        entry_receipt=_lineage(entry_receipt),
        exit_receipt=_lineage(exit_receipt),
    )


def _verify_receipt_role(
    receipt: ResearchDecisionReceipt,
    *,
    segment: LocalPaperDecisionPnlSegment,
    role: Literal["entry", "exit"],
) -> None:
    expected_class = "enter" if role == "entry" else "exit"
    expected_reason = "eligible_enter" if role == "entry" else "eligible_exit"
    if (
        receipt.decision_class != expected_class
        or receipt.reason_class != expected_reason
        or receipt.input_status != "ready"
        or receipt.instrument_binding_ref is None
        or receipt.target_binding_ref is None
    ):
        raise ValueError(f"{role} decision receipt is not execution-eligible")
    expected_instrument_ref = decision_instrument_binding_ref(
        symbol=segment.symbol,
        market=segment.market,
        decision_class=expected_class,
    )
    if receipt.instrument_binding_ref != expected_instrument_ref:
        raise ValueError(f"{role} decision receipt does not match local-paper instrument")


def _lineage(receipt: ResearchDecisionReceipt) -> LocalPaperReceiptLineage:
    return LocalPaperReceiptLineage(
        decision_id=receipt.decision_id,
        receipt_ref=receipt_attribution_ref(receipt),
        campaign_ref=receipt.campaign_ref,
        model_ref=receipt.model_ref,
        input_manifest_ref=receipt.input_manifest_ref,
        proposal_ref=receipt.proposal_ref,
        decision_class=receipt.decision_class,
    )

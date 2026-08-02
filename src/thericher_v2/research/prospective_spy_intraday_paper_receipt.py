"""Pure receipt bridge for the frozen prospective SPY intraday baseline.

This module translates only the source-safe immutable observation receipt into
the generic research receipt consumed by the already bounded SPY Paper canary.
It has no data, credential, network, local-fill, or execution behavior.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from thericher_v2.contracts import TargetExposureProposal
from thericher_v2.models.prospective_spy_intraday_baseline import (
    PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
    PROSPECTIVE_SPY_INTRADAY_BASELINE_ID,
    PROSPECTIVE_SPY_INTRADAY_BASELINE_TARGET_EXPOSURE,
)
from thericher_v2.models.prospective_spy_intraday_observation import (
    ProspectiveSpyIntradayObservationReceipt,
)

from .decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

KIS_PAPER_PROSPECTIVE_SPY_INTRADAY_CAMPAIGN_ID = "prospective-spy-intraday-paper-v1"


def prospective_spy_intraday_input_manifest_ref(
    receipt: ProspectiveSpyIntradayObservationReceipt,
) -> str:
    """Derive the exact source-safe manifest identity consumed by this bridge."""

    _require_receipt(receipt)
    payload = {
        "kind": "prospective-spy-intraday-paper-input-manifest-v1",
        "receipt_id": receipt.receipt_id,
        "source_contract_hash": receipt.source_contract_hash,
        "record_contract_hash": receipt.record_contract_hash,
        "bar_content_commitment_sha256": receipt.bar_content_commitment_sha256,
        "cutoff": _utc_marker(receipt.cutoff),
    }
    return "sha256:" + _sha256_json(payload)


def research_receipt_from_prospective_spy_intraday_observation(
    receipt: ProspectiveSpyIntradayObservationReceipt,
) -> ResearchDecisionReceipt:
    """Narrow one frozen observation into a paper-eligible research receipt."""

    _require_receipt(receipt)
    input_manifest_ref = prospective_spy_intraday_input_manifest_ref(receipt)
    action = receipt.decision_class
    proposal = TargetExposureProposal(
        proposal_id=(
            f"{KIS_PAPER_PROSPECTIVE_SPY_INTRADAY_CAMPAIGN_ID}:sha256:"
            f"{_sha256_json({'receipt_id': receipt.receipt_id, 'action': action})}"
        ),
        symbol="SPY",
        market="US",
        action=action,
        target_exposure=(
            PROSPECTIVE_SPY_INTRADAY_BASELINE_TARGET_EXPOSURE
            if action == "enter"
            else Decimal("0")
        ),
        confidence=Decimal("0.50") if action == "enter" else Decimal("0"),
        feature_schema_id=PROSPECTIVE_SPY_INTRADAY_BASELINE_FEATURE_SCHEMA_ID,
        input_status="ready",
        decided_at=receipt.decided_at,
        valid_until=receipt.valid_until,
        feature_window_end=receipt.cutoff,
        reason=(
            "unanimous_trailing_return_enter"
            if action == "enter"
            else "trailing_return_not_unanimous_abstain"
        ),
    )
    return receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_opaque_ref("campaign", KIS_PAPER_PROSPECTIVE_SPY_INTRADAY_CAMPAIGN_ID),
            model_ref=_opaque_ref("model", PROSPECTIVE_SPY_INTRADAY_BASELINE_ID),
            input_manifest_ref=input_manifest_ref,
            proposal_ref=_opaque_ref("proposal", receipt.receipt_id, input_manifest_ref),
        ),
    )


def _require_receipt(value: object) -> ProspectiveSpyIntradayObservationReceipt:
    if not isinstance(value, ProspectiveSpyIntradayObservationReceipt):
        raise TypeError("receipt must be a ProspectiveSpyIntradayObservationReceipt")
    return value


def _opaque_ref(*parts: str) -> str:
    return "ref:" + _sha256_json({"parts": list(parts)})


def _sha256_json(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _utc_marker(value) -> str:
    return value.isoformat().replace("+00:00", "Z")

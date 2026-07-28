"""Immutable, safe projections of research target-state proposals."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    TargetExposureProposal,
    TargetInputStatus,
    require_utc,
)

DecisionClass = Literal["enter", "exit", "abstain"]
DecisionReasonClass = Literal[
    "eligible_enter",
    "eligible_exit",
    "input_unavailable",
    "model_abstain",
    "non_entry_proposal",
]

_INPUT_STATUSES: Final = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "incomplete",
        "duplicate",
        "non_contiguous",
        "misaligned",
        "future",
        "unqualified",
    }
)
_OPAQUE_REFERENCE = re.compile(r"ref:[0-9a-f]{32,128}")
_INPUT_MANIFEST_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}")
_DECISION_ID = re.compile(r"decision:sha256:[0-9a-f]{64}")


def decision_class_for_target_action(action: str) -> DecisionClass:
    """Return the narrowed receipt class for one target-exposure action."""

    if action == "enter":
        return "enter"
    if action == "exit":
        return "exit"
    if action in {"hold", "reduce", "abstain"}:
        return "abstain"
    raise ValueError("target action is invalid")


def receipt_projection_for_target_action(
    action: str,
    *,
    input_status: TargetInputStatus,
) -> tuple[DecisionClass, DecisionReasonClass]:
    """Return the decision receipt projection for one target-exposure action."""

    decision_class = decision_class_for_target_action(action)
    if input_status not in _INPUT_STATUSES:
        raise ValueError("input_status is invalid")
    if input_status != "ready":
        return "abstain", "input_unavailable"
    if decision_class == "enter":
        return "enter", "eligible_enter"
    if decision_class == "exit":
        return "exit", "eligible_exit"
    if action == "abstain":
        return "abstain", "model_abstain"
    return "abstain", "non_entry_proposal"


@dataclass(frozen=True)
class DecisionReceiptReferences:
    """Caller-supplied opaque identities for a frozen research observation.

    ``input_manifest_ref`` is the exact digest of the input manifest, never a
    truncated display value. The manifest must bind the input's provider and
    capability contract before a caller supplies it here.
    """

    campaign_ref: str
    model_ref: str
    input_manifest_ref: str
    proposal_ref: str

    def __post_init__(self) -> None:
        _require_opaque_reference(self.campaign_ref, "campaign_ref")
        _require_opaque_reference(self.model_ref, "model_ref")
        _require_input_manifest_reference(self.input_manifest_ref)
        _require_opaque_reference(self.proposal_ref, "proposal_ref")


@dataclass(frozen=True)
class ResearchDecisionReceipt:
    """Replayable, narrowed evidence for an entry, exit, or abstain decision."""

    campaign_ref: str
    model_ref: str
    input_manifest_ref: str
    proposal_ref: str
    decision_id: str
    decision_class: DecisionClass
    input_status: TargetInputStatus
    decided_at: datetime
    valid_until: datetime
    reason_class: DecisionReasonClass
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        DecisionReceiptReferences(
            campaign_ref=self.campaign_ref,
            model_ref=self.model_ref,
            input_manifest_ref=self.input_manifest_ref,
            proposal_ref=self.proposal_ref,
        )
        if self.decision_class not in {"enter", "exit", "abstain"}:
            raise ValueError("decision_class must be enter, exit, or abstain")
        if self.input_status not in _INPUT_STATUSES:
            raise ValueError("input_status is invalid")
        if self.reason_class not in {
            "eligible_enter",
            "eligible_exit",
            "input_unavailable",
            "model_abstain",
            "non_entry_proposal",
        }:
            raise ValueError("reason_class is invalid")
        object.__setattr__(self, "decided_at", require_utc(self.decided_at, "decided_at"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until < self.decided_at:
            raise ValueError("valid_until cannot precede decided_at")
        _require_decision_shape(
            decision_class=self.decision_class,
            input_status=self.input_status,
            reason_class=self.reason_class,
        )
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported receipt schema_version")
        if _DECISION_ID.fullmatch(self.decision_id) is None:
            raise ValueError("decision_id must be a canonical digest identity")
        if self.decision_id != _derive_decision_id(
            campaign_ref=self.campaign_ref,
            model_ref=self.model_ref,
            input_manifest_ref=self.input_manifest_ref,
            proposal_ref=self.proposal_ref,
            decision_class=self.decision_class,
            input_status=self.input_status,
            decided_at=self.decided_at,
            valid_until=self.valid_until,
            reason_class=self.reason_class,
            schema_version=self.schema_version,
        ):
            raise ValueError("decision_id must match the immutable receipt payload")

    def to_payload(self) -> dict[str, object]:
        """Return the complete safe payload in a deterministic field set."""

        payload = _identity_payload(
            campaign_ref=self.campaign_ref,
            model_ref=self.model_ref,
            input_manifest_ref=self.input_manifest_ref,
            proposal_ref=self.proposal_ref,
            decision_class=self.decision_class,
            input_status=self.input_status,
            decided_at=self.decided_at,
            valid_until=self.valid_until,
            reason_class=self.reason_class,
            schema_version=self.schema_version,
        )
        return {"decision_id": self.decision_id, **payload}

    def canonical_json(self) -> str:
        """Serialize the receipt for byte-stable replay evidence."""

        return json.dumps(
            self.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def receipt_from_target_exposure_proposal(
    proposal: TargetExposureProposal,
    *,
    references: DecisionReceiptReferences,
) -> ResearchDecisionReceipt:
    """Narrow a target-state proposal without copying its raw decision inputs."""

    decision_class, reason_class = _classify_proposal(proposal)
    decision_id = _derive_decision_id(
        campaign_ref=references.campaign_ref,
        model_ref=references.model_ref,
        input_manifest_ref=references.input_manifest_ref,
        proposal_ref=references.proposal_ref,
        decision_class=decision_class,
        input_status=proposal.input_status,
        decided_at=proposal.decided_at,
        valid_until=proposal.valid_until,
        reason_class=reason_class,
        schema_version=SCHEMA_VERSION,
    )
    return ResearchDecisionReceipt(
        campaign_ref=references.campaign_ref,
        model_ref=references.model_ref,
        input_manifest_ref=references.input_manifest_ref,
        proposal_ref=references.proposal_ref,
        decision_id=decision_id,
        decision_class=decision_class,
        input_status=proposal.input_status,
        decided_at=proposal.decided_at,
        valid_until=proposal.valid_until,
        reason_class=reason_class,
    )


def _classify_proposal(
    proposal: TargetExposureProposal,
) -> tuple[DecisionClass, DecisionReasonClass]:
    return receipt_projection_for_target_action(
        proposal.action,
        input_status=proposal.input_status,
    )


def _require_opaque_reference(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _OPAQUE_REFERENCE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an opaque reference")


def _require_input_manifest_reference(value: str) -> None:
    if not isinstance(value, str) or _INPUT_MANIFEST_REFERENCE.fullmatch(value) is None:
        raise ValueError("input_manifest_ref must be an exact sha256 digest")


def _require_decision_shape(
    *,
    decision_class: DecisionClass,
    input_status: TargetInputStatus,
    reason_class: DecisionReasonClass,
) -> None:
    if input_status != "ready":
        if decision_class != "abstain" or reason_class != "input_unavailable":
            raise ValueError("unavailable inputs must produce an unavailable abstain receipt")
        return
    if decision_class == "enter" and reason_class == "eligible_enter":
        return
    if decision_class == "exit" and reason_class == "eligible_exit":
        return
    if decision_class == "abstain" and reason_class in {
        "model_abstain",
        "non_entry_proposal",
    }:
        return
    raise ValueError("receipt decision shape is invalid")


def _derive_decision_id(
    *,
    campaign_ref: str,
    model_ref: str,
    input_manifest_ref: str,
    proposal_ref: str,
    decision_class: DecisionClass,
    input_status: TargetInputStatus,
    decided_at: datetime,
    valid_until: datetime,
    reason_class: DecisionReasonClass,
    schema_version: int,
) -> str:
    payload = _identity_payload(
        campaign_ref=campaign_ref,
        model_ref=model_ref,
        input_manifest_ref=input_manifest_ref,
        proposal_ref=proposal_ref,
        decision_class=decision_class,
        input_status=input_status,
        decided_at=decided_at,
        valid_until=valid_until,
        reason_class=reason_class,
        schema_version=schema_version,
    )
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return f"decision:sha256:{hashlib.sha256(encoded).hexdigest()}"


def _identity_payload(
    *,
    campaign_ref: str,
    model_ref: str,
    input_manifest_ref: str,
    proposal_ref: str,
    decision_class: DecisionClass,
    input_status: TargetInputStatus,
    decided_at: datetime,
    valid_until: datetime,
    reason_class: DecisionReasonClass,
    schema_version: int,
) -> dict[str, object]:
    return {
        "campaign_ref": campaign_ref,
        "model_ref": model_ref,
        "input_manifest_ref": input_manifest_ref,
        "proposal_ref": proposal_ref,
        "decision_class": decision_class,
        "input_status": input_status,
        "decided_at": _utc_marker(decided_at),
        "valid_until": _utc_marker(valid_until),
        "reason_class": reason_class,
        "schema_version": schema_version,
    }


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")

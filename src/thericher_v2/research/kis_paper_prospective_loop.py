"""One broker-free prospective QQQ decision and local-paper replay loop."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, TargetExposureProposal
from thericher_v2.data.kis_capability import (
    KisCapabilityState,
    KisMarketDataCapability,
    KisStorageRightsStatus,
)
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE,
    KisPaperIntradayRuntimeWindow,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.research.kis_paper_baseline import (
    KIS_PAPER_BASELINE_SCHEMA_ID,
    KisPaperBaselineAuthorization,
    evaluate_kis_paper_baseline,
)
from thericher_v2.research.kis_paper_prospective_local_replay import (
    KisPaperProspectiveLocalReplay,
    replay_kis_paper_prospective_local_paper,
)

KIS_PAPER_PROSPECTIVE_LOOP_KIND = "kis_paper_prospective_loop"
KIS_PAPER_PROSPECTIVE_LOOP_CAMPAIGN_ID = "prospective-qqq-1m-baseline-v1"
KIS_PAPER_PROSPECTIVE_LOOP_MODEL_ID = "fixed-10m-5m-target-state-v1"
_RUNTIME_CAPABILITY_ID_PREFIX = "kis.paper.us.qqq.nas.runtime-1m"

ProspectiveLoopAuthorization = Literal[
    "qualified",
    "provisional",
    "unqualified",
    "not_evaluated",
]
ProspectiveInputEvidenceGradeKind = Literal["observed_provisional", "input_unavailable"]


@dataclass(frozen=True)
class KisPaperProspectiveInputEvidenceGrade:
    """Interpretation limits that travel with one prospective QQQ input."""

    input_evidence_grade: ProspectiveInputEvidenceGradeKind
    capability_authorization: Literal["provisional", "not_evaluated"]
    provider_decision_time_availability: Literal["not_observed"] = "not_observed"
    provider_finality: Literal["not_observed"] = "not_observed"
    terminal_state_support: Literal["unqualified"] = "unqualified"
    pnl_status: Literal["not_observed"] = "not_observed"
    promotion_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        expected_grade: ProspectiveInputEvidenceGradeKind = (
            "observed_provisional"
            if self.capability_authorization == "provisional"
            else "input_unavailable"
        )
        if self.input_evidence_grade != expected_grade:
            raise ValueError("prospective input evidence grade is inconsistent")
        if (
            self.provider_decision_time_availability != "not_observed"
            or self.provider_finality != "not_observed"
            or self.terminal_state_support != "unqualified"
            or self.pnl_status != "not_observed"
            or self.promotion_eligible is not False
        ):
            raise ValueError("prospective input evidence limits are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "input_evidence_grade": self.input_evidence_grade,
            "capability_authorization": self.capability_authorization,
            "provider_decision_time_availability": self.provider_decision_time_availability,
            "provider_finality": self.provider_finality,
            "terminal_state_support": self.terminal_state_support,
            "pnl_status": self.pnl_status,
            "promotion_eligible": self.promotion_eligible,
        }


@dataclass(frozen=True)
class KisPaperProspectiveLoopResult:
    """One source-safe decision-to-local-paper outcome for a selected window."""

    window: KisPaperIntradayRuntimeWindow
    proposal: TargetExposureProposal
    receipt: ResearchDecisionReceipt
    capability_authorization: ProspectiveLoopAuthorization
    local_paper_replay: KisPaperProspectiveLocalReplay | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.capability_authorization not in {
            "qualified",
            "provisional",
            "unqualified",
            "not_evaluated",
        }:
            raise ValueError("prospective loop capability authorization is invalid")
        if self.window.status == "ready":
            if self.proposal.input_status != "ready":
                raise ValueError("ready runtime input must retain a ready proposal")
            if self.local_paper_replay is None:
                raise ValueError("ready runtime input requires a local-paper replay result")
        elif self.proposal.input_status != self.window.status:
            raise ValueError("unready runtime input must retain its exact status")
        elif self.local_paper_replay is not None:
            raise ValueError("unready runtime input cannot create a local-paper replay")
        prospective_input_evidence_grade(
            window=self.window,
            capability_authorization=self.capability_authorization,
        )

    @property
    def input_evidence_grade(self) -> KisPaperProspectiveInputEvidenceGrade:
        return prospective_input_evidence_grade(
            window=self.window,
            capability_authorization=self.capability_authorization,
        )

    def safe_payload(self) -> dict[str, object]:
        """Return safe evidence that binds data, decision, and replay identities."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_LOOP_KIND,
            "mode": "offline_local_paper",
            "window": self.window.safe_payload(),
            "baseline": {
                "schema_id": KIS_PAPER_BASELINE_SCHEMA_ID,
                "capability_authorization": self.capability_authorization,
                "action": self.proposal.action,
                "input_status": self.proposal.input_status,
                "reason": self.proposal.reason,
                "decided_at": _utc_marker(self.proposal.decided_at),
                "valid_until": _utc_marker(self.proposal.valid_until),
                "feature_window_end": (
                    None
                    if self.proposal.feature_window_end is None
                    else _utc_marker(self.proposal.feature_window_end)
                ),
            },
            "input_evidence_grade": self.input_evidence_grade.safe_payload(),
            "receipt": self.receipt.to_payload(),
            "local_paper_replay": (
                None if self.local_paper_replay is None else self.local_paper_replay.safe_payload()
            ),
            "claim": (
                "bounded provisional Paper observation; local replay only; "
                "not a model promotion or profitability claim"
            ),
        }


def prospective_input_evidence_grade(
    *,
    window: KisPaperIntradayRuntimeWindow,
    capability_authorization: ProspectiveLoopAuthorization,
) -> KisPaperProspectiveInputEvidenceGrade:
    """Return the fixed non-promoting interpretation for this runtime loop."""

    expected_authorization: Literal["provisional", "not_evaluated"] = (
        "provisional" if window.status == "ready" else "not_evaluated"
    )
    if capability_authorization != expected_authorization:
        raise ValueError("runtime loop capability authorization is inconsistent")
    return KisPaperProspectiveInputEvidenceGrade(
        input_evidence_grade=(
            "observed_provisional"
            if expected_authorization == "provisional"
            else "input_unavailable"
        ),
        capability_authorization=expected_authorization,
    )


def run_kis_paper_prospective_loop(
    window: KisPaperIntradayRuntimeWindow,
    *,
    local_paper_state_root: Path,
    repo_root: Path,
) -> KisPaperProspectiveLoopResult:
    """Create one deterministic decision receipt and local-paper replay.

    This function owns no credential, network, KIS quote, account, or order
    behavior. A later Execution-owned receipt canary may consume its narrowed
    receipt only when a separately fresh QQQ limit proof is available.
    """

    if not isinstance(window, KisPaperIntradayRuntimeWindow):
        raise TypeError("prospective loop requires a runtime window")
    if window.status != "ready":
        proposal = _unavailable_proposal(window)
        receipt = _receipt_for(window=window, proposal=proposal)
        return KisPaperProspectiveLoopResult(
            window=window,
            proposal=proposal,
            receipt=receipt,
            capability_authorization="not_evaluated",
            local_paper_replay=None,
        )

    capability = _runtime_observed_capability(window)
    authorization = KisPaperBaselineAuthorization(
        capability_id=capability.capability_id,
        capability_contract_sha256=capability.contract_sha256,
        evidence_reference=capability.evidence_reference,
    )
    evaluation = evaluate_kis_paper_baseline(
        window.decision_bars,
        capability=capability,
        symbol="QQQ",
        market="US",
        as_of=window.as_of,
        max_age=KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE,
        provisional_authorization=authorization,
    )
    receipt = _receipt_for(window=window, proposal=evaluation.proposal)
    local_replay = replay_kis_paper_prospective_local_paper(
        evaluation.proposal,
        signal_bar=window.decision_bars[-1],
        replay_bar=window.replay_bar,
        state_root=local_paper_state_root,
        repo_root=repo_root,
    )
    return KisPaperProspectiveLoopResult(
        window=window,
        proposal=evaluation.proposal,
        receipt=receipt,
        capability_authorization=evaluation.capability_authorization,
        local_paper_replay=local_replay,
    )


def _runtime_observed_capability(
    window: KisPaperIntradayRuntimeWindow,
) -> KisMarketDataCapability:
    if window.status != "ready":
        raise ValueError("runtime capability requires a ready window")
    if window.max_age > KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE:
        raise ValueError("runtime window exceeds the fixed baseline freshness budget")
    return KisMarketDataCapability(
        capability_id=(
            f"{_RUNTIME_CAPABILITY_ID_PREFIX}.{window.input_manifest_ref.removeprefix('sha256:')[:16]}"
        ),
        state=KisCapabilityState.OBSERVED,
        endpoint_category="overseas_stock_intraday",
        exchange_scope=("NAS",),
        symbol_scope=("QQQ",),
        raw_fields=("open", "high", "low", "last", "evol"),
        timeframe=window.decision_bars[0].timeframe,
        time_semantics="runtime 2026 regular-session completed-bar observation; provisional",
        completed_bar_rule="verified cached minute ends at or before runtime as_of",
        freshness_budget=window.max_age,
        paging_facts="runtime window selected from a verified local KIS head catalog",
        storage_rights=KisStorageRightsStatus.UNVERIFIED,
        evidence_reference=window.input_manifest_ref,
        observed_at=window.as_of,
    )


def _unavailable_proposal(window: KisPaperIntradayRuntimeWindow) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=(
            f"{KIS_PAPER_BASELINE_SCHEMA_ID}:US:QQQ:{window.status}:"
            f"runtime-{window.input_manifest_ref.removeprefix('sha256:')}"
        ),
        symbol="QQQ",
        market="US",
        action="abstain",
        target_exposure=Decimal("0"),
        confidence=Decimal("0"),
        feature_schema_id=KIS_PAPER_BASELINE_SCHEMA_ID,
        input_status=window.status,
        decided_at=window.as_of,
        valid_until=window.as_of + timedelta(minutes=1),
        feature_window_end=window.window_end,
        reason=f"runtime_window_{window.status}",
    )


def _receipt_for(
    *,
    window: KisPaperIntradayRuntimeWindow,
    proposal: TargetExposureProposal,
) -> ResearchDecisionReceipt:
    return receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_opaque_ref(KIS_PAPER_PROSPECTIVE_LOOP_CAMPAIGN_ID),
            model_ref=_opaque_ref(KIS_PAPER_PROSPECTIVE_LOOP_MODEL_ID),
            input_manifest_ref=window.input_manifest_ref,
            proposal_ref=_opaque_ref(window.input_manifest_ref, proposal.proposal_id),
        ),
    )


def _opaque_ref(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return "ref:" + hashlib.sha256(payload).hexdigest()


def _utc_marker(value) -> str:
    return value.isoformat().replace("+00:00", "Z")

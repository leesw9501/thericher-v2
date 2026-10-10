"""One frozen tree slot exchanged for Paper preparation, never order sizing.

Caller-attested current manifest, canonical features and official clocks remain
input provenance, not PIT/finality proof. The pilot is not full top-ten replay.
Model availability stays assumed; completion time is an actual caller observation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Context, Decimal, localcontext
from fractions import Fraction
from typing import TYPE_CHECKING, Literal

from thericher_v2.contracts import TargetExposureProposal, decision_instrument_binding_ref
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

if TYPE_CHECKING:
    from thericher_v2.research.five_session_cohort import FiveSessionFrame
    from thericher_v2.research.five_session_tree import TreeDecision

INFERENCE_SOURCE_SHA256 = "sha256:2f64a23813f1c617667d7632a9a1575f9532eeff36450d0f8dfa09fe823e91f5"
FEATURE_SCHEMA_ID = "kis_stock_five_session_tree_prior20_pilot_v1"
CONFIDENCE_MARKER = Decimal("1")  # Engineering marker, not a calibrated probability.
_CONTEXT = Context(prec=64, rounding=ROUND_FLOOR)
_QUANTUM = Decimal("1e-24")


class PaperDecisionError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise PaperDecisionError(reason)


def _utc(value: datetime) -> None:
    _require(type(value) is datetime and value.utcoffset() == timedelta(0), "clock_invalid")


def _ref(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "ref:" + hashlib.sha256(raw).hexdigest()


def _pin(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True)
class FiveSessionPaperDecision:
    """Lightweight metadata only; no arrays, model callable or capital amounts.

    A no-intent observation never cancels an already owned entry/EXIT lifecycle.
    Entry expiry is not holding duration; the fifth clock remains separate.
    """

    status: Literal["prepared", "no_intent"]
    reason: str
    cohort_ref: str
    selected_slot: int | None
    instrument_key: str | None
    instrument_binding_ref: str | None
    frame_ref: str
    feature_ref: str
    allocation_ref: str
    source_pins: tuple[tuple[str, str], ...]
    input_manifest_ref: str
    model_ref: str
    proposal_ref: str | None
    nominal_decision_at: datetime
    prior_close_at: datetime
    session_opens: tuple[datetime, ...]
    session_closes: tuple[datetime, ...]
    entry_valid_until: datetime
    inference_completed_at: datetime
    as_of: datetime
    proposal: TargetExposureProposal | None
    receipt: ResearchDecisionReceipt | None
    availability: str = "assumed_not_observed"

    def __post_init__(self) -> None:
        _require(self.status in ("prepared", "no_intent") and bool(self.reason), "dto_status")
        _require(
            type(self.session_opens) is type(self.session_closes) is tuple
            and len(self.session_opens) == len(self.session_closes) == 5
            and type(self.source_pins) is tuple
            and all(
                type(row) is tuple and len(row) == 2 and type(row[0]) is str
                for row in self.source_pins
            ),
            "dto_geometry",
        )
        for at in (
            self.nominal_decision_at,
            self.prior_close_at,
            self.entry_valid_until,
            self.inference_completed_at,
            self.as_of,
            *self.session_opens,
            *self.session_closes,
        ):
            _utc(at)
        _require(
            self.prior_close_at < self.nominal_decision_at < self.first_open
            and self.prior_close_at <= self.inference_completed_at <= self.as_of
            and self.as_of < self.entry_valid_until
            and self.first_open < self.entry_valid_until <= self.session_closes[0]
            and all(
                o < c and o.date() == c.date()
                for o, c in zip(self.session_opens, self.session_closes, strict=True)
            )
            and all(
                a < b for a, b in zip(self.session_closes[:-1], self.session_opens[1:], strict=True)
            ),
            "dto_clocks",
        )
        _require(
            all(_pin(ref) for ref in (self.frame_ref, self.feature_ref, self.input_manifest_ref))
            and all(_pin(pin) for _, pin in self.source_pins)
            and all(
                re.fullmatch(r"ref:[0-9a-f]{64}", ref) is not None
                for ref in (self.cohort_ref, self.allocation_ref, self.model_ref)
            )
            and self.availability == "assumed_not_observed",
            "dto_references",
        )
        _require(
            (
                self.selected_slot is None
                and self.instrument_key is None
                and self.instrument_binding_ref is None
            )
            or (
                type(self.selected_slot) is int
                and 0 <= self.selected_slot < 512
                and isinstance(self.instrument_key, str)
                and re.fullmatch(r"ref:[0-9a-f]{64}", self.instrument_binding_ref or "")
            ),
            "dto_instrument",
        )
        if self.status == "no_intent":
            _require(self.proposal is self.receipt is self.proposal_ref is None, "dto_no_intent")
            return
        _require(
            type(self.proposal) is TargetExposureProposal
            and type(self.receipt) is ResearchDecisionReceipt
            and self.selected_slot is not None,
            "dto_prepared",
        )
        p, r = self.proposal, self.receipt
        _require(
            p.action == "enter"
            and p.input_status == "ready"
            and p.confidence == CONFIDENCE_MARKER
            and 0 < p.target_exposure <= Decimal(".01")
            and p.decided_at == self.inference_completed_at
            and p.valid_until == self.entry_valid_until
            and p.feature_window_end == self.prior_close_at
            and p.feature_schema_id == FEATURE_SCHEMA_ID
            and p.proposal_id == self.proposal_ref
            and self.instrument_key == p.symbol + "/NAS"
            and p.market == "US"
            and r.proposal_ref == self.proposal_ref
            and r.model_ref == self.model_ref
            and r.input_manifest_ref == self.input_manifest_ref
            and r.instrument_binding_ref == self.instrument_binding_ref,
            "dto_proposal_binding",
        )
        with localcontext(_CONTEXT):
            cohort = _ref(
                dict(
                    campaign=r.campaign_ref,
                    frame=self.frame_ref[7:],
                    input=self.input_manifest_ref,
                    model=self.model_ref,
                    sources=self.source_pins,
                    allocation=self.allocation_ref,
                    slot=self.selected_slot,
                    instrument=self.instrument_binding_ref,
                )
            )
            proposal = _ref(
                dict(
                    cohort=cohort,
                    completed=self.inference_completed_at.isoformat(),
                    valid_until=self.entry_valid_until.isoformat(),
                    target=format(p.target_exposure, "f"),
                )
            )
            _require(
                self.cohort_ref == cohort and self.proposal_ref == proposal, "dto_identity_binding"
            )
            expected = receipt_from_target_exposure_proposal(
                p,
                references=DecisionReceiptReferences(
                    r.campaign_ref, self.model_ref, self.input_manifest_ref, self.proposal_ref
                ),
            )
        _require(r == expected, "dto_receipt_binding")

    @property
    def first_open(self) -> datetime:
        return self.session_opens[0]

    @property
    def fifth_close(self) -> datetime:
        return self.session_closes[4]


def prepare_five_session_paper_decision(
    frame: FiveSessionFrame,
    decision: TreeDecision,
    *,
    campaign_ref: str,
    input_manifest_sha256: str,
    expected_input_manifest_sha256: str,
    feature_source_sha256: str,
    inference_source_sha256: str,
    instrument_bindings: Mapping[str, str],
    inference_completed_at: datetime,
    as_of: datetime,
    entry_valid_until: datetime,
) -> FiveSessionPaperDecision:
    """Bind one actual inference; no reranking, replacement or account access.

    Pins are prefixed sha256 references. Instrument bindings map frozen identity
    keys to existing US/enter refs. ORIGINAL means the original ranked ten slots,
    including added identities, not a new restriction to the original128 prefix.
    Actual completion can precede the nominal preopen clock, but not prior data.
    C/B=.10; N/B=.10/(1+.0005*sum(all weights)). Decimal shortest float values
    are summed exactly, then exposure rounds DOWN at 24 decimal places. Execution
    owns whole-share floor, available capacity and exclusive-instrument checks.
    """
    # Model/numeric types are needed only on the preparation side, never DTO import.
    from thericher_v2.research.five_session_cohort import CohortError, FiveSessionFrame
    from thericher_v2.research.five_session_tree import (
        FEATURE_SHA256,
        IDENTITY_SHA256,
        METADATA_SHA256,
        TEACHER_SHA256,
        TRAINING_CUTOFF,
        TreeDecision,
        TreeError,
    )

    _require(type(frame) is FiveSessionFrame and type(decision) is TreeDecision, "typed_input")
    _require(decision.teacher_sha256 == TEACHER_SHA256, "teacher_binding")
    try:
        checked = replace(frame)
        replace(decision)
    except (CohortError, TreeError) as exc:
        raise PaperDecisionError("typed_input_invalid") from exc
    _require(
        checked.stamp == frame.stamp == decision.frame_stamp
        and checked.supported == frame.supported,
        "frame_binding",
    )
    identity = json.dumps(list(frame.identities), separators=(",", ":")).encode()
    _require(hashlib.sha256(identity).hexdigest() == IDENTITY_SHA256, "identity_binding")
    _require(
        feature_source_sha256 == "sha256:" + FEATURE_SHA256
        and inference_source_sha256 == INFERENCE_SOURCE_SHA256,
        "source_binding",
    )
    _require(
        _pin(input_manifest_sha256)
        and _pin(expected_input_manifest_sha256)
        and input_manifest_sha256 == expected_input_manifest_sha256,
        "manifest_binding",
    )
    _require(
        frame.decision > TRAINING_CUTOFF
        and isinstance(frame.feature_stamp, str)
        and _pin("sha256:" + frame.feature_stamp)
        and frame.availability == decision.availability == "assumed_not_observed",
        "feature_binding",
    )
    _require(isinstance(instrument_bindings, Mapping), "instrument_map")
    for at in (inference_completed_at, as_of, entry_valid_until):
        _utc(at)
    _require(frame.prior_closes[-1] <= inference_completed_at, "inference_before_prior")
    _require(inference_completed_at <= as_of, "future_inference")
    _require(as_of < entry_valid_until, "entry_window_closed")
    _require(
        frame.target_open < entry_valid_until <= frame.session_closes[0], "entry_window_invalid"
    )
    model_ref = "ref:" + TEACHER_SHA256
    DecisionReceiptReferences(campaign_ref, model_ref, input_manifest_sha256, "ref:" + "0" * 64)
    _require(
        decision.reason
        == ("frozen_goal80_tree" if decision.status == "ready" else "prior_causal_support"),
        "decision_reason_binding",
    )
    _require(
        decision.status != "ready"
        or (
            frame.supported
            and len(decision.original_slots) == 10
            and all(frame.eligible[i] for i in decision.original_slots)
        ),
        "decision_support_binding",
    )
    slot = next((i for i in decision.original_slots if decision.weights[i] > 0), None)
    key = frame.identities[slot] if slot is not None else None
    binding = None
    if key is not None:
        _require(re.fullmatch(r"[A-Z][A-Z0-9.]{0,15}/NAS", key) is not None, "instrument_key")
        binding = decision_instrument_binding_ref(
            symbol=key[:-4], market="US", decision_class="enter"
        )
    source_pins = (
        ("feature", feature_source_sha256),
        ("inference", inference_source_sha256),
        ("teacher_metadata", "sha256:" + METADATA_SHA256),
    )
    allocation_ref = (
        "ref:"
        + hashlib.sha256(
            decision.scores.tobytes()
            + decision.weights.tobytes()
            + repr(decision.original_slots).encode()
            + decision.status.encode()
        ).hexdigest()
    )
    cohort_ref = _ref(
        dict(
            campaign=campaign_ref,
            frame=frame.stamp,
            input=input_manifest_sha256,
            model=model_ref,
            sources=source_pins,
            allocation=allocation_ref,
            slot=slot,
            instrument=binding,
        )
    )
    base = dict(
        cohort_ref=cohort_ref,
        selected_slot=slot,
        instrument_key=key,
        instrument_binding_ref=binding,
        frame_ref="sha256:" + frame.stamp,
        feature_ref="sha256:" + frame.feature_stamp,
        allocation_ref=allocation_ref,
        source_pins=source_pins,
        input_manifest_ref=input_manifest_sha256,
        model_ref=model_ref,
        nominal_decision_at=frame.decision,
        prior_close_at=frame.prior_closes[-1],
        session_opens=frame.session_opens,
        session_closes=frame.session_closes,
        entry_valid_until=entry_valid_until,
        inference_completed_at=inference_completed_at,
        as_of=as_of,
    )
    reason = None
    if decision.status == "input_unavailable":
        reason = "prior_causal_support"
    elif slot is None:
        reason = "model_cash_veto"
    elif key not in instrument_bindings:
        reason = "selected_instrument_unavailable"
    elif instrument_bindings[key] != binding:
        reason = "selected_instrument_mismatch"
    if reason is not None:
        return FiveSessionPaperDecision(
            status="no_intent",
            reason=reason,
            proposal_ref=None,
            proposal=None,
            receipt=None,
            **base,
        )
    gross = sum((Fraction(Decimal(str(float(w)))) for w in decision.weights), Fraction())
    exposure = (
        Fraction(1, 10)
        * Fraction(Decimal(str(float(decision.weights[slot]))))
        / (1 + Fraction(1, 2000) * gross)
    )
    with localcontext(_CONTEXT):
        target = (Decimal(exposure.numerator) / Decimal(exposure.denominator)).quantize(_QUANTUM)
        if target == 0:
            return FiveSessionPaperDecision(
                status="no_intent",
                reason="exposure_underflow",
                proposal_ref=None,
                proposal=None,
                receipt=None,
                **base,
            )
        proposal_ref = _ref(
            dict(
                cohort=cohort_ref,
                completed=inference_completed_at.isoformat(),
                valid_until=entry_valid_until.isoformat(),
                target=format(target, "f"),
            )
        )
        proposal = TargetExposureProposal(
            proposal_id=proposal_ref,
            symbol=key[:-4],
            market="US",
            action="enter",
            target_exposure=target,
            confidence=CONFIDENCE_MARKER,
            feature_schema_id=FEATURE_SCHEMA_ID,
            input_status="ready",
            decided_at=inference_completed_at,
            valid_until=entry_valid_until,
            feature_window_end=frame.prior_closes[-1],
            reason="frozen_tree_single_slot_engineering_marker_not_probability",
        )
        receipt = receipt_from_target_exposure_proposal(
            proposal,
            references=DecisionReceiptReferences(
                campaign_ref, model_ref, input_manifest_sha256, proposal_ref
            ),
        )
    return FiveSessionPaperDecision(
        status="prepared",
        reason="frozen_first_surviving_slot",
        proposal_ref=proposal_ref,
        proposal=proposal,
        receipt=receipt,
        **base,
    )

"""A transparent, point-in-time SPY D1 baseline for virtual-paper decisions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import SCHEMA_VERSION, TargetExposureProposal, require_utc
from thericher_v2.data.kis_paper_daily_spy_input import KisPaperDailySpyInput
from thericher_v2.data.us_equity_session import UsEquity2026Session, us_equity_2026_session

from .decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)

KIS_PAPER_DAILY_SPY_BASELINE_SCHEMA_ID = "kis-paper-daily-spy-baseline-v1"
KIS_PAPER_DAILY_SPY_BASELINE_TARGET_EXPOSURE = Decimal("0.05")


@dataclass(frozen=True)
class KisPaperDailySpyBaselineEvaluation:
    """A daily input, target-state proposal, and immutable narrowed receipt."""

    input: KisPaperDailySpyInput
    proposal: TargetExposureProposal
    receipt: ResearchDecisionReceipt
    execution_session: UsEquity2026Session | None
    schema_version: int = SCHEMA_VERSION


def evaluate_kis_paper_daily_spy_baseline(
    input: KisPaperDailySpyInput,
    *,
    as_of: datetime,
) -> KisPaperDailySpyBaselineEvaluation:
    """Evaluate a two-close momentum reference without a broker dependency.

    The decision identity is fixed to the first verified local availability of
    its input, rather than to each worker invocation.  This makes a retry of
    the same daily source reconstitute the same receipt.
    """

    observed_at = require_utc(as_of, "as_of")
    execution_session = _next_session_after(input.last_consumed_session)
    status, reason = _input_status(
        input=input,
        execution_session=execution_session,
        observed_at=observed_at,
    )
    if status != "ready":
        proposal = _abstain(
            input=input,
            status=status,
            reason=reason,
            decided_at=observed_at,
            valid_until=observed_at,
        )
    else:
        assert execution_session is not None
        trend_up = input.bars[-1].close > input.bars[-2].close
        proposal = TargetExposureProposal(
            proposal_id=_proposal_ref(input, suffix="trend"),
            symbol="SPY",
            market="US",
            action="enter" if trend_up else "abstain",
            target_exposure=(
                KIS_PAPER_DAILY_SPY_BASELINE_TARGET_EXPOSURE if trend_up else Decimal("0")
            ),
            confidence=Decimal("0.55") if trend_up else Decimal("0"),
            feature_schema_id=KIS_PAPER_DAILY_SPY_BASELINE_SCHEMA_ID,
            input_status="ready",
            decided_at=input.first_available_at,
            valid_until=execution_session.window.close_ts,
            feature_window_end=input.first_available_at,
            reason="two_close_momentum_enter" if trend_up else "two_close_momentum_abstain",
        )
    receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_opaque_ref("campaign", input.input_manifest_ref),
            model_ref=_opaque_ref("model", KIS_PAPER_DAILY_SPY_BASELINE_SCHEMA_ID),
            input_manifest_ref=input.input_manifest_ref,
            proposal_ref=_proposal_ref(input, suffix=proposal.reason),
        ),
    )
    return KisPaperDailySpyBaselineEvaluation(
        input=input,
        proposal=proposal,
        receipt=receipt,
        execution_session=execution_session,
    )


def _input_status(
    *,
    input: KisPaperDailySpyInput,
    execution_session: UsEquity2026Session | None,
    observed_at: datetime,
) -> tuple[str, str]:
    if execution_session is None:
        return "unqualified", "daily_execution_session_unavailable"
    if input.first_available_at >= execution_session.window.close_ts:
        return "stale", "daily_input_available_after_execution_session"
    if observed_at <= input.first_available_at:
        return "future", "daily_input_not_yet_available"
    if observed_at > execution_session.window.close_ts:
        return "stale", "daily_input_execution_window_expired"
    if not _are_consecutive_sessions(input.bars[0].start_ts.date(), input.last_consumed_session):
        return "non_contiguous", "daily_input_sessions_non_contiguous"
    return "ready", "daily_input_ready"


def _abstain(
    *,
    input: KisPaperDailySpyInput,
    status: str,
    reason: str,
    decided_at: datetime,
    valid_until: datetime,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=_proposal_ref(input, suffix=reason),
        symbol="SPY",
        market="US",
        action="abstain",
        target_exposure=Decimal("0"),
        confidence=Decimal("0"),
        feature_schema_id=KIS_PAPER_DAILY_SPY_BASELINE_SCHEMA_ID,
        input_status=status,  # type: ignore[arg-type]
        decided_at=decided_at,
        valid_until=valid_until,
        feature_window_end=None,
        reason=reason,
    )


def _next_session_after(session_date: date) -> UsEquity2026Session | None:
    for offset in range(1, 8):
        try:
            candidate = us_equity_2026_session(session_date + timedelta(days=offset))
        except ValueError:
            return None
        if candidate is not None:
            return candidate
    return None


def _are_consecutive_sessions(previous: date, current: date) -> bool:
    next_session = _next_session_after(previous)
    return next_session is not None and next_session.session_date == current


def _opaque_ref(label: str, value: str) -> str:
    digest = hashlib.sha256(f"{label}|{value}".encode()).hexdigest()
    return f"ref:{digest}"


def _proposal_ref(input: KisPaperDailySpyInput, *, suffix: str) -> str:
    return _opaque_ref(
        "proposal",
        "|".join(
            (
                input.input_manifest_ref,
                input.last_consumed_session.isoformat(),
                suffix,
            )
        ),
    )

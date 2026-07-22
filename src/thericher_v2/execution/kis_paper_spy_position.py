"""Pure current-account target resolution for the bounded KIS Paper SPY loop.

This module consumes an already-complete KIS Paper read-only snapshot. It does
not create requests, persist raw account facts, infer fills, or calculate PnL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt

from .kis_readonly import KisPaperReadOnlySnapshot

KIS_PAPER_SPY_POSITION_SYMBOL = "SPY"
KIS_PAPER_SPY_POSITION_EXCHANGE = "AMEX"
KIS_PAPER_SPY_ACCOUNT_FACT_MAX_AGE = timedelta(seconds=120)

PositionAction = Literal["buy", "sell", "none"]
PositionReason = Literal[
    "receipt_not_eligible",
    "receipt_not_current",
    "account_unavailable",
    "account_snapshot_not_current",
    "position_out_of_scope",
    "open_order_conflict",
    "target_already_satisfied",
    "target_buy_one_share",
    "target_sell_one_share",
]
PositionState = Literal["not_observed", "flat", "one_share", "out_of_scope"]


@dataclass(frozen=True)
class KisPaperSpyPositionResolution:
    """Categorical result of reconciling one receipt with current Paper facts."""

    decision_class: Literal["enter", "exit", "abstain"]
    action: PositionAction
    reason_code: PositionReason
    account_fact_status: Literal["current", "unavailable"]
    position_state: PositionState
    open_order_state: Literal["clear", "conflict", "not_observed"]
    observed_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.decision_class not in {"enter", "exit", "abstain"}:
            raise ValueError("SPY position decision class is invalid")
        if self.action not in {"buy", "sell", "none"}:
            raise ValueError("SPY position action is invalid")
        if self.reason_code not in {
            "receipt_not_eligible",
            "receipt_not_current",
            "account_unavailable",
            "account_snapshot_not_current",
            "position_out_of_scope",
            "open_order_conflict",
            "target_already_satisfied",
            "target_buy_one_share",
            "target_sell_one_share",
        }:
            raise ValueError("SPY position reason is invalid")
        if self.account_fact_status not in {"current", "unavailable"}:
            raise ValueError("SPY account fact status is invalid")
        if self.position_state not in {"not_observed", "flat", "one_share", "out_of_scope"}:
            raise ValueError("SPY position state is invalid")
        if self.open_order_state not in {"clear", "conflict", "not_observed"}:
            raise ValueError("SPY open-order state is invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        _validate_resolution_shape(self)

    def safe_payload(self) -> dict[str, object]:
        """Expose replayable categorical attribution only, never account values."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_spy_position_resolution",
            "paper_only": True,
            "decision_class": self.decision_class,
            "action": self.action,
            "reason_code": self.reason_code,
            "account_fact_status": self.account_fact_status,
            "position_state": self.position_state,
            "open_order_state": self.open_order_state,
            "observed_at": self.observed_at.isoformat(),
            "pnl_status": "not_observed",
        }


def resolve_kis_paper_spy_position_target(
    receipt: ResearchDecisionReceipt,
    *,
    snapshot: KisPaperReadOnlySnapshot | None,
    as_of: datetime,
    max_account_fact_age: timedelta = KIS_PAPER_SPY_ACCOUNT_FACT_MAX_AGE,
) -> KisPaperSpyPositionResolution:
    """Return the one eligible Paper side from a fresh, complete account fact.

    A decision receipt never implies an inventory change. Only a fresh complete
    KIS Paper snapshot may establish the flat/one-share state used here.
    """

    observed_at = require_utc(as_of, "as_of")
    if max_account_fact_age <= timedelta(0):
        raise ValueError("maximum account fact age must be positive")
    if not _eligible_receipt(receipt, observed_at=observed_at):
        return _resolution(
            receipt,
            action="none",
            reason_code=(
                "receipt_not_current"
                if receipt.input_status == "ready"
                and receipt.decision_class in {"enter", "exit"}
                else "receipt_not_eligible"
            ),
            account_fact_status="unavailable",
            position_state="not_observed",
            open_order_state="not_observed",
            observed_at=observed_at,
        )
    if snapshot is None:
        return _resolution(
            receipt,
            action="none",
            reason_code="account_unavailable",
            account_fact_status="unavailable",
            position_state="not_observed",
            open_order_state="not_observed",
            observed_at=observed_at,
        )
    if not _snapshot_is_current(snapshot, observed_at=observed_at, max_age=max_account_fact_age):
        return _resolution(
            receipt,
            action="none",
            reason_code="account_snapshot_not_current",
            account_fact_status="unavailable",
            position_state="not_observed",
            open_order_state="not_observed",
            observed_at=observed_at,
        )

    position_state = _spy_position_state(snapshot)
    open_order_state: Literal["clear", "conflict"] = (
        "conflict"
        if any(
            order.symbol == KIS_PAPER_SPY_POSITION_SYMBOL
            for order in snapshot.open_orders.orders
        )
        else "clear"
    )
    if position_state == "out_of_scope":
        return _resolution(
            receipt,
            action="none",
            reason_code="position_out_of_scope",
            account_fact_status="current",
            position_state=position_state,
            open_order_state=open_order_state,
            observed_at=observed_at,
        )
    if open_order_state == "conflict":
        return _resolution(
            receipt,
            action="none",
            reason_code="open_order_conflict",
            account_fact_status="current",
            position_state=position_state,
            open_order_state=open_order_state,
            observed_at=observed_at,
        )
    if receipt.decision_class == "enter" and position_state == "flat":
        return _resolution(
            receipt,
            action="buy",
            reason_code="target_buy_one_share",
            account_fact_status="current",
            position_state=position_state,
            open_order_state=open_order_state,
            observed_at=observed_at,
        )
    if receipt.decision_class == "exit" and position_state == "one_share":
        return _resolution(
            receipt,
            action="sell",
            reason_code="target_sell_one_share",
            account_fact_status="current",
            position_state=position_state,
            open_order_state=open_order_state,
            observed_at=observed_at,
        )
    return _resolution(
        receipt,
        action="none",
        reason_code="target_already_satisfied",
        account_fact_status="current",
        position_state=position_state,
        open_order_state=open_order_state,
        observed_at=observed_at,
    )


def _eligible_receipt(receipt: ResearchDecisionReceipt, *, observed_at: datetime) -> bool:
    expected_reason = (
        "eligible_enter" if receipt.decision_class == "enter" else "eligible_exit"
    )
    return (
        receipt.decision_class in {"enter", "exit"}
        and receipt.reason_class == expected_reason
        and receipt.input_status == "ready"
        and receipt.decided_at <= observed_at <= receipt.valid_until
    )


def _snapshot_is_current(
    snapshot: KisPaperReadOnlySnapshot,
    *,
    observed_at: datetime,
    max_age: timedelta,
) -> bool:
    captured_at = snapshot.captured_at
    return captured_at <= observed_at and observed_at - captured_at <= max_age


def _spy_position_state(snapshot: KisPaperReadOnlySnapshot) -> PositionState:
    spy_positions = [
        position
        for position in snapshot.positions
        if position.symbol == KIS_PAPER_SPY_POSITION_SYMBOL
    ]
    if not spy_positions:
        return "flat"
    if (
        len(spy_positions) == 1
        and spy_positions[0].exchange == KIS_PAPER_SPY_POSITION_EXCHANGE
        and spy_positions[0].quantity == 1
    ):
        return "one_share"
    return "out_of_scope"


def _resolution(
    receipt: ResearchDecisionReceipt,
    *,
    action: PositionAction,
    reason_code: PositionReason,
    account_fact_status: Literal["current", "unavailable"],
    position_state: PositionState,
    open_order_state: Literal["clear", "conflict", "not_observed"],
    observed_at: datetime,
) -> KisPaperSpyPositionResolution:
    return KisPaperSpyPositionResolution(
        decision_class=receipt.decision_class,
        action=action,
        reason_code=reason_code,
        account_fact_status=account_fact_status,
        position_state=position_state,
        open_order_state=open_order_state,
        observed_at=observed_at,
    )


def _validate_resolution_shape(resolution: KisPaperSpyPositionResolution) -> None:
    if resolution.action == "buy":
        if (
            resolution.decision_class != "enter"
            or resolution.reason_code != "target_buy_one_share"
            or resolution.account_fact_status != "current"
            or resolution.position_state != "flat"
            or resolution.open_order_state != "clear"
        ):
            raise ValueError("SPY buy resolution is invalid")
        return
    if resolution.action == "sell":
        if (
            resolution.decision_class != "exit"
            or resolution.reason_code != "target_sell_one_share"
            or resolution.account_fact_status != "current"
            or resolution.position_state != "one_share"
            or resolution.open_order_state != "clear"
        ):
            raise ValueError("SPY sell resolution is invalid")
        return
    if resolution.reason_code in {"target_buy_one_share", "target_sell_one_share"}:
        raise ValueError("SPY no-action resolution cannot carry a target action reason")

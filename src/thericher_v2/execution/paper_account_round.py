"""Public, finite selection for one source-owned serial Paper account round.

The adapter owns bank exclusion, scheduled-owner proof, credentials, original
per-cohort debits, native risk, pre-wire deadlines and positive closure. This
module never reads custody or turns a callback return into submit/fill evidence.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite


class PaperRoundContractError(ValueError):
    pass


def _need(value: bool) -> None:
    if not value:
        raise PaperRoundContractError("paper_round_contract_invalid")


def _utc(value: datetime) -> datetime:
    _need(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class PaperRoundSlot:
    slot: str
    phase: str
    starts_at: datetime
    ends_at: datetime
    input_ref: str
    policy_ref: str

    def validate(self) -> None:
        _need(
            type(self.slot) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", self.slot) is not None
        )
        _need(type(self.phase) is str and self.phase in {"entry", "exit"})
        start, end = _utc(self.starts_at), _utc(self.ends_at)
        _need(start < end <= start + timedelta(hours=8))
        _need(
            all(
                type(ref) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", ref) is not None
                for ref in (self.input_ref, self.policy_ref)
            )
        )


@dataclass(frozen=True)
class PaperCohortProgress:
    """Native adapter assertion, not independent broker or ownership evidence.

    The adapter must derive this from the original persisted target sequence
    under its existing account ownership and risk checks. A cursor counts
    traversed targets, never shares, fills, money or released reservations.
    """

    slot: PaperRoundSlot
    adapter_ref: str
    before: int
    after: int
    state: str
    reconciled: bool
    unknown_pending: bool


def _tick(value: float) -> float:
    _need(type(value) in (int, float) and isfinite(value) and value >= 0)
    return value


def run_cohort_progress(
    slot: PaperRoundSlot,
    *,
    adapter_ref: str,
    work_units: int,
    completed: int,
    clock: Callable[[], datetime],
    monotonic: Callable[[], float],
    invoke_original_target: Callable[[PaperRoundSlot, int, datetime], PaperCohortProgress],
    max_visits: int,
    wall_seconds: int,
) -> dict:
    """Advance reconciled original targets, stopping on any unknown effect.

    This opt-in helper does not change ``run_serial_round`` or installed tasks.
    An admitted native adapter supplies the persisted starting cursor and must
    enforce the narrowed pre-wire deadline, pending reconciliation and its own
    per-target debits. This loop cannot interrupt a callback or attest its
    claims. Physical account/process closure remains the adapter's obligation.
    """
    _need(type(slot) is PaperRoundSlot)
    slot.validate()
    _need(type(adapter_ref) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", adapter_ref))
    _need(type(work_units) is int and 1 <= work_units <= 512)
    _need(type(completed) is int and 0 <= completed <= work_units)
    _need(type(max_visits) is int and 1 <= max_visits <= 32)
    _need(type(wall_seconds) is int and 1 <= wall_seconds <= 900)
    _need(callable(clock) and callable(monotonic) and callable(invoke_original_target))
    started, first_tick = _utc(clock()), _tick(monotonic())
    deadline = min(_utc(slot.ends_at), started + timedelta(seconds=wall_seconds))
    last_at, last_tick = started, first_tick
    cursor, visits = completed, []
    status = "traversal_complete_not_fill_evidence" if cursor == work_units else "no_ready_slot"
    while cursor < work_units:
        at, tick = _utc(clock()), _tick(monotonic())
        _need(at >= last_at and tick >= last_tick)
        last_at, last_tick = at, tick
        remaining = wall_seconds - (tick - first_tick)
        if at >= deadline or remaining <= 0:
            status = "cohort_deadline"
            break
        if not _utc(slot.starts_at) <= at < _utc(slot.ends_at):
            break
        if len(visits) >= max_visits:
            status = "cohort_visit_limit"
            break
        # Never widen a previously issued deadline, even if UTC stalls.
        deadline = min(deadline, at + timedelta(seconds=remaining))
        row = {"cursor": cursor, "deadline_utc": deadline.isoformat()}
        visits.append(row)
        try:
            feedback = invoke_original_target(slot, cursor, deadline)
        except Exception as error:
            row.update(status="technical_failure_unknown_effects", category=_category(error))
            status = "stopped_for_adapter_recovery"
            break
        valid = (
            type(feedback) is PaperCohortProgress
            and type(feedback.slot) is PaperRoundSlot
            and feedback.slot == slot
            and type(feedback.adapter_ref) is str
            and feedback.adapter_ref == adapter_ref
            and type(feedback.before) is int
            and feedback.before == cursor
            and type(feedback.after) is int
            and cursor <= feedback.after <= work_units
            and type(feedback.state) is str
            and feedback.state in {"advanced", "no_intent", "complete", "pending", "unavailable"}
            and type(feedback.reconciled) is bool
            and type(feedback.unknown_pending) is bool
        )
        if not valid:
            row["status"] = "invalid_native_progress_unknown_effects"
            status = "stopped_for_adapter_recovery"
            break
        if feedback.unknown_pending or not feedback.reconciled or feedback.state == "pending":
            row["status"] = "pending_or_unreconciled"
            status = "stopped_for_exact_reconciliation"
            break
        if feedback.state == "unavailable":
            row["status"] = "native_input_unavailable"
            status = "stopped_for_adapter_recovery"
            break
        if feedback.after != cursor + 1 or (
            feedback.state == "complete" and feedback.after != work_units
        ):
            row["status"] = "non_sequential_native_progress"
            status = "stopped_for_adapter_recovery"
            break
        cursor = feedback.after
        row["status"] = "native_cursor_advanced_not_fill_evidence"
        status = (
            "traversal_complete_not_fill_evidence" if cursor == work_units else "cohort_progress"
        )
    return {
        "status": status,
        "slot": slot.slot,
        "phase": slot.phase,
        "input_ref": slot.input_ref,
        "policy_ref": slot.policy_ref,
        "adapter_ref": adapter_ref,
        "completed_before": completed,
        "completed_after": cursor,
        "work_units": work_units,
        "invocations": len(visits),
        "steps": visits,
        "outer_debits": 0,
        "waits": 0,
        "broker_acceptance_fill_inventory_PnL_proved": False,
        "native_risk_and_exact_pending_reconciliation_required": True,
    }


def _category(error: Exception) -> str:
    for kind in (TimeoutError, OSError, ValueError, RuntimeError):
        if isinstance(error, kind):
            return kind.__name__
    return "unclassified_exception"


def run_serial_round(
    slots: Sequence[PaperRoundSlot],
    *,
    clock: Callable[[], datetime],
    invoke_original_leg: Callable[[PaperRoundSlot, datetime], object],
    max_legs: int,
    wall_seconds: int,
) -> dict:
    """Attempt each due slot at most once, without waiting or writing a debit.

    This must run within the adapter's one physical-bank ownership scope. The
    supplied deadline only narrows an original window; the native pre-wire
    guard, not this selection loop, enforces it during an HTTP operation.
    Recovery of an exact pending intent remains inside the original leg; this
    function does not invent a recovery slot or infer reservations are released.
    """
    _need(type(max_legs) is int and 1 <= max_legs <= 32)
    _need(type(wall_seconds) is int and 1 <= wall_seconds <= 900)
    _need(callable(clock) and callable(invoke_original_leg))
    _need(type(slots) in (list, tuple) and len(slots) <= 32)
    items = tuple(slots)
    _need(all(type(slot) is PaperRoundSlot for slot in items))
    for slot in items:
        slot.validate()
    keys = [(slot.slot, slot.phase) for slot in items]
    _need(len(set(keys)) == len(keys))
    routes = [(slot.input_ref, slot.policy_ref, slot.phase) for slot in items]
    _need(len(set(routes)) == len(routes))
    # One policy's entry and exit cannot be routed as simultaneous alternatives.
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if left.slot == right.slot:
                _need(left.input_ref == right.input_ref and left.policy_ref == right.policy_ref)
                _need(
                    max(_utc(left.starts_at), _utc(right.starts_at))
                    >= min(_utc(left.ends_at), _utc(right.ends_at))
                )
    started = _utc(clock())
    deadline = started + timedelta(seconds=wall_seconds)
    last_at = started
    visits: list[dict] = []
    status = "no_ready_slot"
    ordered = sorted(items, key=lambda item: (_utc(item.starts_at), item.slot, item.phase))
    for slot in ordered:
        at = _utc(clock())
        _need(at >= last_at)
        last_at = at
        if at >= deadline:
            status = "round_deadline"
            break
        if len(visits) >= max_legs:
            status = "round_leg_limit"
            break
        if not _utc(slot.starts_at) <= at < _utc(slot.ends_at):
            continue
        bounded = min(deadline, _utc(slot.ends_at))
        row = {
            "slot": slot.slot,
            "phase": slot.phase,
            "input_ref": slot.input_ref,
            "policy_ref": slot.policy_ref,
            "deadline_utc": bounded.isoformat(),
            "status": "invocation_started_not_submit_evidence",
        }
        visits.append(row)
        try:
            # The original implementation debits. A second outer debit is forbidden.
            invoke_original_leg(slot, bounded)
        except Exception as error:
            row.update(status="technical_failure_unknown_effects", category=_category(error))
            status = "stopped_for_adapter_recovery"
            break
        row["status"] = "callback_returned_not_fill_evidence"
        status = "serial_round_returned"
    return {
        "status": status,
        "steps": visits,
        "invocations": len(visits),
        "round_started_utc": started.isoformat(),
        "round_deadline_utc": deadline.isoformat(),
        "outer_debits": 0,
        "waits": 0,
        "broker_acceptance_fill_inventory_PnL_proved": False,
        "native_risk_and_exact_pending_reconciliation_required": True,
    }

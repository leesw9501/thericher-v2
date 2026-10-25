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

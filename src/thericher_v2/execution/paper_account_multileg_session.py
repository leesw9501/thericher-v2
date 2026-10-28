"""Opt-in finite entry guest for an already admitted single Paper account owner.

The dated unified host supplies account exclusion, pinned source/policy/cap,
and ONE authenticated client factory with a shared finite native wire budget.
That budget must enforce the supplied guard/deadline immediately before every
wire, including after pacing; this traversal cannot establish OS ownership or
interrupt a callback. Existing one-effect sessions and budgets are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path
from re import fullmatch

from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution.kis_readonly import require_utc
from thericher_v2.execution.paper_account_session import (
    PaperAccountCohort,
    _same_skip_active,
    _snapshot,
)

MAX_TARGETS = 100


class PaperAccountMultilegSessionError(ValueError):
    """Categorical contract failure without private native state."""


def _need(ok: bool, category: str) -> None:
    if not ok:
        raise PaperAccountMultilegSessionError(category)


def _plan_count(record: dict | None) -> int:
    return 0 if record is None else sum(len(owner["plans"]) for owner in record["owners"].values())


def run_native_account_multileg_session(
    *,
    cohort: PaperAccountCohort,
    paths: Mapping[str, Path],
    expected_account_ref: str,
    target_loader: Callable[[], core.ModelPaperWeightsInput],
    client_factory: Callable,
    guard: Callable[[], object],
    deadline: datetime,
    clock: Callable[[], datetime],
    monotonic: Callable[[], float],
    max_effects: int = 17,
    max_native_calls: int = 17,
    first_failure_sink: Callable | None = None,
) -> dict[str, object]:
    """Traverse reconciled entries only, using original journals and no debit.

    ``max_effects`` is the caller's frozen cumulative cap, not a fresh allowance
    on restart. Every retained owner plan counts conservatively, including
    reserved/unknown requests. The host must bind this cap and ``source_ref``
    with the original policy in ``guard``; they are not new financial state.
    Initial pending recovery visits that exact BUY once and always yields,
    even if resolved. Fresh pending/accepted partial also stops immediately.
    Never use this recovery-capable API as a custody reader.
    """
    _need(type(cohort) is PaperAccountCohort, "multileg_cohort_invalid")
    cohort.validate()
    _need(
        cohort.mode == "entry"
        and cohort.profile
        in {
            core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5,
            core.StockCycleProfile.MODEL_WEIGHTS_US_H5,
        },
        "multileg_entry_profile_required",
    )
    _need(type(max_effects) is int and 1 <= max_effects <= 17, "multileg_limit_invalid")
    _need(type(max_native_calls) is int and 1 <= max_native_calls <= 17, "multileg_limit_invalid")
    _need(
        all(callable(f) for f in (target_loader, client_factory, guard, clock, monotonic)),
        "multileg_callback_invalid",
    )
    _need(
        type(expected_account_ref) is str and fullmatch(r"[0-9a-f]{64}", expected_account_ref),
        "multileg_account_ref_invalid",
    )
    deadline = require_utc(deadline)
    _need(deadline <= cohort.slot.ends_at, "multileg_deadline_widened")
    paths = dict(paths)
    started = require_utc(clock())
    last_at, last_tick = started, monotonic()
    _need(type(last_tick) in (int, float) and isfinite(last_tick), "multileg_clock_invalid")
    deadline = min(deadline, started + timedelta(seconds=280))
    tick_end = last_tick + (deadline - started).total_seconds()

    def check() -> None:
        nonlocal last_at, last_tick
        for after_guard in (False, True):
            if after_guard:
                _need(guard() is not False, "multileg_admission_denied")
            at, tick = require_utc(clock()), monotonic()
            _need(
                type(tick) in (int, float)
                and isfinite(tick)
                and at >= last_at
                and tick >= last_tick,
                "multileg_clock_invalid",
            )
            _need(
                cohort.slot.starts_at <= at < deadline and tick < tick_end,
                "multileg_deadline_closed",
            )
            last_at, last_tick = at, tick

    check()
    before = _snapshot(paths, expected_account_ref, cohort)
    book, record, value, prefix = before
    pending = record is not None and record["pending"] is not None
    initial_pending = pending
    native_calls = skipped = 0
    cursor = len(prefix)
    plans = _plan_count(record)
    outcome = None

    def result(stop: str) -> dict[str, object]:
        return {
            "kind": "paper_account_multileg_session_v1",
            "stop": stop,
            "native": None if outcome is None else outcome.safe_payload(),
            "native_calls": native_calls,
            "skipped": skipped,
            "cursor": cursor,
            "pending": pending,
            "persisted_plans": plans,
            "max_effects": max_effects,
            "outer_debits": 0,
            "limitation": "native_progress_not_current_inventory_or_fees_settlement_net_pnl",
        }

    def forbidden():
        raise PaperAccountMultilegSessionError("multileg_retained_input_must_not_reload")

    if record is not None and value is None:
        return result("retained_inactive_no_new_cohort")
    if initial_pending:
        _need(record["pending"]["side"] == "buy", "multileg_entry_pending_required")
    if value is None:
        check()
        value = target_loader()
    _need(
        type(value) is core.ModelPaperWeightsInput
        and value.input_ref == cohort.slot.input_ref
        and value.policy_ref == cohort.slot.policy_ref
        and value.profile == cohort.profile.value,
        "multileg_input_changed",
    )
    core._validate_input(value, value.entry_session.open_ts, cohort.profile)
    _need(
        len(value.metadata.rows) <= MAX_TARGETS and len(value.targets) <= MAX_TARGETS,
        "multileg_target_limit",
    )
    if not initial_pending:
        if not value.entry_session.open_ts <= require_utc(clock()) < value.entry_session.close_ts:
            return result("outside_original_entry_session")
        if not value.targets:
            return result("empty_original_basket")

    def fresh_loader():
        return value

    loader = fresh_loader if record is None else forbidden

    def client(instrument):
        check()
        bound = client_factory(instrument)
        check()
        return bound

    for _ in range(1 if initial_pending else max_native_calls):
        check()
        if not initial_pending and cursor == len(value.targets):
            return result("original_entry_prefix_exhausted")
        if not initial_pending and plans >= max_effects:
            return result("persisted_effect_cap")
        oldbook, oldrecord, _, oldprefix = before
        native_calls += 1
        outcome = core.run_kis_paper_current_stock_cycle(
            **paths,
            expected_account_ref=expected_account_ref,
            expected_input_ref=cohort.slot.input_ref,
            expected_policy_ref=cohort.slot.policy_ref,
            profile=cohort.profile,
            target_loader=loader,
            client_factory=client,
            clock=clock,
            execute=True,
            first_failure_sink=first_failure_sink,
        )
        check()
        after = _snapshot(paths, expected_account_ref, cohort)
        newbook, newrecord, newvalue, newprefix = after
        pending = newrecord is not None and newrecord["pending"] is not None
        plans = _plan_count(newrecord)
        cursor = len(newprefix)
        if initial_pending:
            return result("initial_pending_recovery_once")
        if pending:
            return result("pending_preserved")
        if outcome.status == "complete" and outcome.reason == "policy_no_order_complete":
            _need(
                newrecord is not None
                and newvalue is None
                and outcome.leg_count == 0
                and value.input_ref in newrecord["completed"]
                and newbook == oldbook,
                "multileg_no_order_completion_changed",
            )
            cursor = len(value.targets)
            skipped += 1
            return result("native_no_order_complete")
        if outcome.status not in {"advanced", "no_intent"}:
            return result("native_non_progress_stop")
        _need(
            newrecord is not None
            and newvalue == value
            and newprefix == oldprefix + (value.targets[len(oldprefix)].proposal.symbol,),
            "multileg_nonprefix_progress",
        )
        if outcome.leg_count:
            _need(
                outcome.status == "advanced" and outcome.reason == "native_leg_closed",
                "multileg_unreconciled_progress",
            )
        else:
            _need(outcome.status == "no_intent" and newbook == oldbook, "multileg_skip_changed")
            if oldrecord is not None:
                _need(
                    {k: v for k, v in newrecord.items() if k not in {"ref", "active"}}
                    == {k: v for k, v in oldrecord.items() if k not in {"ref", "active"}}
                    and _same_skip_active(
                        oldrecord["active"],
                        newrecord["active"],
                        cohort.profile,
                        value.targets[len(oldprefix)].proposal.symbol,
                    ),
                    "multileg_skip_changed",
                )
            skipped += 1
        before, loader = after, forbidden
    return result(
        "initial_pending_recovery_once"
        if initial_pending
        else (
            "original_entry_prefix_exhausted"
            if cursor == len(value.targets)
            else "native_call_limit"
        )
    )

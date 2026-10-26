"""One finite native visit inside an already admitted account owner.

The actual SingleOwnerContext/BankLeg/NativeBridge caller retains exclusion,
original logical debits, wire admission and OS/container closure. This adapter
neither establishes those facts nor creates an account or releases reservations.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from math import ceil
from pathlib import Path

from thericher_v2.execution import kis_paper_current_stock_cycle as core
from thericher_v2.execution.kis_readonly import require_utc
from thericher_v2.execution.paper_account_round import (
    PaperCohortProgress,
    PaperRoundSlot,
    run_cohort_progress,
)


class PaperAccountSessionError(ValueError):
    """Categorical failure; never attach private native state."""


def _need(ok: bool, category: str) -> None:
    if not ok:
        raise PaperAccountSessionError(category)


@dataclass(frozen=True, repr=False)
class PaperAccountCohort:
    slot: PaperRoundSlot
    source_ref: str
    basis_ref: str
    profile: core.StockCycleProfile
    mode: str = "entry"

    def validate(self) -> None:
        _need(type(self.slot) is PaperRoundSlot, "account_session_slot_invalid")
        self.slot.validate()
        core._pin(self.source_ref)
        core._pin(self.basis_ref)
        _need(
            type(self.profile) is core.StockCycleProfile
            and self.profile in {
                core.StockCycleProfile.MODEL_WEIGHTS_NAS,
                core.StockCycleProfile.MODEL_WEIGHTS_NAS_H5,
                core.StockCycleProfile.MODEL_WEIGHTS_NAS_H20_EARLY_EXIT,
            }
            and type(self.mode) is str
            and self.mode in {"entry", "exit", "recovery"}
            and self.slot.phase == ("entry" if self.mode == "entry" else "exit"),
            "account_session_profile_invalid",
        )


def _snapshot(paths, account, cohort):
    root = Path(paths["state_root"])
    book = core._book(root, account, cohort.basis_ref)
    record = core.budget._read_json(root / core.model_paper_pointer(cohort.slot.policy_ref))
    if record is None:
        return book, None, None, ()
    _need(
        record.get("ref") == "sha256:" + core.budget._digest(
            {k: v for k, v in record.items() if k != "ref"}
        )
        and record.get("paths") == {k: str(Path(v).resolve()) for k, v in paths.items()}
        and record.get("account_ref") == account
        and record.get("basis_ref") == cohort.basis_ref
        and record.get("policy_ref") == cohort.slot.policy_ref
        and record.get("profile") == cohort.profile.value,
        "account_session_binding_changed",
    )
    core._model_record_input(record, cohort.slot.input_ref, cohort.slot.policy_ref, cohort.profile)
    core._owned_registry(record, book)
    if record["active"] is None:
        return book, record, None, ()
    value = core._unpack(record["active"]["model_input"])
    targets = tuple(t.proposal.symbol for t in value.targets)
    done = record["active"]["entries_done"]
    _need(
        type(done) is list and all(type(s) is str for s in done)
        and len(targets) == len(set(targets))
        and len(done) <= len(targets) and tuple(done) == targets[:len(done)],
        "account_session_nonprefix_cursor",
    )
    return book, record, value, tuple(done)


def run_native_account_session(
    *,
    cohort: PaperAccountCohort,
    paths: Mapping[str, Path],
    expected_account_ref: str,
    target_loader: Callable,
    client_factory: Callable,
    configure_early_exit: Callable,
    admit: Callable,
    deadline: datetime,
    clock: Callable,
    monotonic: Callable,
    first_failure_sink: Callable | None = None,
    max_native_calls: int = 32,
) -> dict:
    """Skip only exact unreserved native prefix steps, then yield first leg.

    Client/budget construction is lazy in the worker, once for this entire
    call. Recovery never reloads a proposal or renews a request. ``admit``
    must be the real source/owner guard; this is not an offline reader API.
    """
    _need(type(cohort) is PaperAccountCohort, "account_session_cohort_invalid")
    cohort.validate()
    _need(type(max_native_calls) is int and 1 <= max_native_calls <= 32,
          "account_session_limit_invalid")
    deadline = require_utc(deadline)
    _need(deadline <= cohort.slot.ends_at, "account_session_deadline_widened")
    _need(all(callable(f) for f in (target_loader, client_factory, configure_early_exit,
                                    admit, clock, monotonic)), "account_session_callback_invalid")
    native_calls = skipped = cursor = 0
    pending = False
    outcome = None

    def result(stop):
        return {
            "kind": "paper_account_session_v1", "stop": stop,
            "native": None if outcome is None else outcome.safe_payload(),
            "native_calls": native_calls, "skipped": skipped, "cursor": cursor,
            "pending": pending, "outer_debits": 0,
            "limitation": "not_basket_completion_or_fill_or_current_inventory_or_pnl",
        }

    def guard():
        _need(cohort.slot.starts_at <= require_utc(clock()) < deadline,
              "account_session_deadline_closed")
        _need(admit() is not False, "account_session_admission_denied")
        _need(cohort.slot.starts_at <= require_utc(clock()) < deadline,
              "account_session_deadline_closed")

    guard()
    before = _snapshot(paths, expected_account_ref, cohort)
    initial_pending = before[1] is not None and before[1]["pending"] is not None
    value = before[2]

    def forbidden():
        raise PaperAccountSessionError("account_session_retained_input_must_not_reload")

    if initial_pending:
        loader = forbidden
    elif cohort.mode == "recovery":
        return result("no_retained_pending")
    elif before[1] is not None:
        if value is None:
            return result("retained_inactive_no_new_cohort")
        loader = forbidden
    elif cohort.mode != "entry":
        return result("no_retained_owned_cycle")
    else:
        guard()
        value = target_loader()
        _need(
            type(value) is core.ModelPaperWeightsInput
            and value.input_ref == cohort.slot.input_ref
            and value.policy_ref == cohort.slot.policy_ref
            and value.profile == cohort.profile.value,
            "account_session_input_changed",
        )
        def loader():
            return value
    if not initial_pending and cohort.mode == "entry":
        _need(value is not None, "account_session_retained_input_missing")
        if not value.entry_session.open_ts <= clock() < value.entry_session.close_ts:
            return result("outside_original_entry_session")
        if not value.targets:
            return result("empty_original_basket")
    if not initial_pending and cohort.mode == "exit" and clock() < value.metadata.exit_not_before:
        return result("await_declared_exit")

    for _ in range(1 if initial_pending or cohort.mode != "entry" else max_native_calls):
        guard()
        oldbook, oldrecord, _, oldprefix = before
        cursor = len(oldprefix)
        if value is not None and cohort.mode == "entry" and cursor == len(value.targets):
            return result("original_entry_prefix_exhausted")
        native_calls += 1
        outcome = core.run_kis_paper_current_stock_cycle(
            **paths, expected_account_ref=expected_account_ref,
            expected_input_ref=cohort.slot.input_ref, expected_policy_ref=cohort.slot.policy_ref,
            profile=cohort.profile, target_loader=loader, client_factory=client_factory,
            clock=clock, execute=True, first_failure_sink=first_failure_sink,
            **({"configure_early_exit": configure_early_exit}
               if cohort.profile is core.StockCycleProfile.MODEL_WEIGHTS_NAS_H20_EARLY_EXIT
               else {}),
        )
        guard()
        after = _snapshot(paths, expected_account_ref, cohort)
        newbook, newrecord, newvalue, newprefix = after
        cursor = len(newprefix)
        pending = newrecord is not None and newrecord["pending"] is not None
        if initial_pending:
            return result("initial_pending_recovery_once")
        if outcome.leg_count != 0:
            return result("yield_after_first_native_leg")
        if pending:
            return result("pending_preserved")
        if cohort.mode != "entry" or outcome.status != "no_intent":
            return result("native_non_skip_stop")
        _need(
            newrecord is not None and newvalue == value and newbook == oldbook
            and cursor == len(oldprefix) + 1 and newprefix[:-1] == oldprefix,
            "account_session_skip_changed",
        )
        if oldrecord is not None:
            _need(
                newrecord["owners"] == oldrecord["owners"]
                and {k: v for k, v in newrecord["active"].items() if k != "entries_done"}
                == {k: v for k, v in oldrecord["active"].items() if k != "entries_done"},
                "account_session_skip_changed",
            )
        # Reuse c7's cursor contract only for the completed, unreserved skip.
        # It never chooses another effectful leg or mislabels an effect as pending.
        progress = run_cohort_progress(
            cohort.slot, adapter_ref=cohort.source_ref, work_units=len(value.targets),
            completed=len(oldprefix), clock=clock, monotonic=monotonic,
            invoke_original_target=lambda slot, start, end, after=cursor: PaperCohortProgress(
                slot, cohort.source_ref, start, after, "no_intent", True, False
            ),
            max_visits=1, wall_seconds=min(280, max(1, ceil((deadline - clock()).total_seconds()))),
        )
        if progress["completed_after"] != cursor:
            return result("skip_progress_deadline_yield")
        skipped += 1
        before, loader = after, forbidden
    return result("native_call_limit")

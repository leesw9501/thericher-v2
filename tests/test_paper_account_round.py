from datetime import UTC, datetime, timedelta, timezone

import pytest

from thericher_v2.execution.paper_account_round import (
    PaperCohortProgress,
    PaperRoundContractError,
    PaperRoundSlot,
    run_cohort_progress,
    run_serial_round,
)

NOW = datetime(2026, 10, 30, 19, 45, tzinfo=UTC)


def slot(name="GRU", phase="exit", starts_at=NOW, ends_at=NOW + timedelta(minutes=15)):
    from hashlib import sha256

    return PaperRoundSlot(
        name,
        phase,
        starts_at,
        ends_at,
        "sha256:" + sha256(name.encode()).hexdigest(),
        "sha256:" + "2" * 64,
    )


def run(items, clock=lambda: NOW, invoke=lambda *_: None, **kwargs):
    return run_serial_round(
        items,
        clock=clock,
        invoke_original_leg=invoke,
        max_legs=kwargs.get("max_legs", 4),
        wall_seconds=kwargs.get("wall", 300),
    )


def test_due_original_legs_are_serial_with_no_outer_debit_or_fill_inference():
    calls, busy = [], False

    def invoke(item, deadline):
        nonlocal busy
        assert not busy
        busy = True
        assert deadline <= item.ends_at
        calls.append((item.slot, item.input_ref, item.policy_ref))
        busy = False
        return {"status": "filled"}  # A return value alone is not linked-fill evidence.

    result = run([slot("TimesFM"), slot("GRU"), slot("L")], invoke=invoke)
    assert [item[0] for item in calls] == ["GRU", "L", "TimesFM"]
    assert len(calls) == result["invocations"] == 3
    assert result["outer_debits"] == result["waits"] == 0
    assert result["broker_acceptance_fill_inventory_PnL_proved"] is False
    assert all(row["status"] == "callback_returned_not_fill_evidence" for row in result["steps"])


@pytest.mark.parametrize("offset", [-1, 900, 901])
def test_no_call_outside_original_half_open_window(offset):
    calls = []
    result = run(
        [slot()],
        clock=lambda: NOW + timedelta(seconds=offset),
        invoke=lambda *_: calls.append(True),
    )
    assert calls == [] and result["status"] == "no_ready_slot"


def test_future_slot_does_not_wait_or_preempt_a_ready_slot():
    calls = []
    future = slot("future", starts_at=NOW + timedelta(hours=1), ends_at=NOW + timedelta(hours=2))
    result = run([future, slot()], invoke=lambda item, _: calls.append(item.slot))
    assert calls == ["GRU"] and result["waits"] == 0


def test_deadline_is_narrowed_and_no_new_callback_starts_after_elapsed_round():
    at, calls = NOW, []

    def clock():
        return at

    def invoke(item, deadline):
        nonlocal at
        assert deadline == NOW + timedelta(seconds=30)
        calls.append(item.slot)
        at += timedelta(seconds=30)

    result = run([slot("A"), slot("B")], clock=clock, invoke=invoke, wall=30)
    assert calls == ["A"] and result["status"] == "round_deadline"


def test_clock_rechecked_between_legs_uses_each_original_window():
    times = iter([NOW, NOW, NOW + timedelta(minutes=1)])
    calls = []
    ending = slot("B", ends_at=NOW + timedelta(minutes=1))
    result = run(
        [slot("A"), ending],
        clock=lambda: next(times),
        invoke=lambda item, _: calls.append(item.slot),
    )
    assert calls == ["A"] and result["invocations"] == 1


def test_exception_stops_other_private_work_and_never_retains_raw_exception():
    def fail(*_):
        raise RuntimeError("private-sensitive-error-not-for-output")

    result = run([slot("A"), slot("B")], invoke=fail)
    assert result["status"] == "stopped_for_adapter_recovery" and result["invocations"] == 1
    assert result["steps"][0]["category"] == "RuntimeError"
    assert "private-sensitive" not in str(result)


def test_keyboard_interrupt_preserves_outer_owner_recovery_instead_of_being_swallowed():
    def fail(*_):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run([slot()], invoke=fail)


def test_finite_leg_limit_without_extra_calls():
    calls = []
    result = run([slot("A"), slot("B")], max_legs=1, invoke=lambda item, _: calls.append(item.slot))
    assert calls == ["A"] and result["status"] == "round_leg_limit"


def test_duplicate_or_overlapping_policy_slots_rejected_before_callback():
    for items in ([slot(), slot()], [slot(phase="entry"), slot(phase="exit")]):
        with pytest.raises(PaperRoundContractError):
            run(items)


def test_same_slot_input_or_policy_cannot_be_swapped_between_phases():
    later = PaperRoundSlot(
        "GRU",
        "entry",
        NOW - timedelta(days=1),
        NOW - timedelta(days=1) + timedelta(minutes=1),
        "sha256:" + "3" * 64,
        "sha256:" + "2" * 64,
    )
    with pytest.raises(PaperRoundContractError):
        run([later, slot()])


@pytest.mark.parametrize("value", [0, -1, 901, True])
def test_unbounded_or_invalid_round_wall_rejected(value):
    with pytest.raises(PaperRoundContractError):
        run([slot()], wall=value)


def test_naive_and_backward_clocks_rejected():
    with pytest.raises(PaperRoundContractError):
        run([slot()], clock=lambda: NOW.replace(tzinfo=None))
    times = iter([NOW, NOW - timedelta(seconds=1)])
    with pytest.raises(PaperRoundContractError):
        run([slot()], clock=lambda: next(times))


def test_utc_offsets_are_explicitly_normalized():
    korea = NOW.astimezone(timezone(timedelta(hours=9)))
    assert run([slot()], clock=lambda: korea)["invocations"] == 1


def test_empty_round_is_no_ready_and_no_side_effect():
    assert run([])["invocations"] == 0


def test_unbounded_input_iterator_and_alias_of_same_policy_route_are_rejected():
    with pytest.raises(PaperRoundContractError):
        run(iter([slot()]))
    first = slot()
    alias = PaperRoundSlot(
        "ALIAS", first.phase, first.starts_at, first.ends_at, first.input_ref, first.policy_ref
    )
    with pytest.raises(PaperRoundContractError):
        run([first, alias])


ADAPTER = "sha256:" + "a" * 64


def progress(item, before, *, state="advanced", **changes):
    fields = dict(
        slot=item, adapter_ref=ADAPTER, before=before, after=before + 1,
        state=state, reconciled=True, unknown_pending=False,
    )
    fields.update(changes)
    return PaperCohortProgress(**fields)


def cohort(invoke=None, **changes):
    fields = dict(
        adapter_ref=ADAPTER, work_units=3, completed=0, clock=lambda: NOW,
        monotonic=lambda: 0.0,
        invoke_original_target=invoke or (lambda item, cursor, _: progress(item, cursor)),
        max_visits=4, wall_seconds=300,
    )
    fields.update(changes)
    return run_cohort_progress(slot(), **fields)


def test_cohort_advances_skipped_original_target_then_remaining_without_outer_debits():
    calls = []

    def invoke(item, cursor, deadline):
        assert deadline == NOW + timedelta(seconds=300)
        calls.append(cursor)
        return progress(item, cursor, state="no_intent" if cursor == 0 else "advanced")

    result = cohort(invoke)
    assert calls == [0, 1, 2]
    assert result["status"] == "traversal_complete_not_fill_evidence"
    assert result["completed_after"] == 3
    assert result["outer_debits"] == result["waits"] == 0
    assert not result["broker_acceptance_fill_inventory_PnL_proved"]


def test_cohort_resumes_exact_persisted_cursor_and_does_not_repeat_completed_work():
    calls = []
    result = cohort(
        lambda item, cursor, _: (calls.append(cursor) or progress(item, cursor)), completed=2
    )
    assert calls == [2] and result["completed_before"] == 2
    assert cohort(completed=3)["invocations"] == 0


@pytest.mark.parametrize("changes", [
    {"unknown_pending": True}, {"reconciled": False}, {"state": "pending"},
])
def test_cohort_never_continues_or_consumes_cursor_with_unknown_effects(changes):
    result = cohort(lambda item, cursor, _: progress(item, cursor, **changes))
    assert result["status"] == "stopped_for_exact_reconciliation"
    assert result["completed_after"] == 0 and result["invocations"] == 1


@pytest.mark.parametrize("changes", [
    {"before": 1}, {"after": 0}, {"after": 2}, {"after": True},
    {"before": False}, {"after": 4}, {"state": "filled"}, {"reconciled": 1},
    {"unknown_pending": 0}, {"slot": slot("other")}, {"slot": slot(phase="entry")},
    {"adapter_ref": "sha256:" + "b" * 64}, {"state": "complete"},
])
def test_cohort_invalid_or_non_sequential_feedback_stops_without_replacement(changes):
    result = cohort(lambda item, cursor, _: progress(item, cursor, **changes))
    assert result["status"] == "stopped_for_adapter_recovery"
    assert result["invocations"] == 1 and result["completed_after"] == 0


def test_cohort_rejects_callback_dict_claiming_fill_and_never_echoes_payload():
    result = cohort(lambda *_: {"status": "filled", "private": "do-not-echo"})
    assert result["invocations"] == 1 and "do-not-echo" not in str(result)


def test_cohort_complete_assertion_is_traversal_only_and_unavailable_stops():
    result = cohort(lambda item, cursor, _: progress(item, cursor, state="complete"), completed=2)
    assert result["completed_after"] == 3
    assert not result["broker_acceptance_fill_inventory_PnL_proved"]
    result = cohort(lambda item, cursor, _: progress(item, cursor, state="unavailable"))
    assert result["completed_after"] == 0 and result["invocations"] == 1


def test_cohort_discontinuous_second_feedback_keeps_only_prior_reconciled_progress():
    result = cohort(lambda item, cursor, _: progress(item, 0))
    assert result["invocations"] == 2 and result["completed_after"] == 1


@pytest.mark.parametrize("offset", [-1, 900, 901])
def test_cohort_does_not_wait_or_invoke_outside_original_window(offset):
    result = cohort(clock=lambda: NOW + timedelta(seconds=offset))
    assert result["invocations"] == result["waits"] == 0


def test_cohort_monotonic_budget_expires_even_if_utc_does_not_advance():
    ticks = iter([0, 0, 300])
    result = cohort(monotonic=lambda: next(ticks))
    assert result["invocations"] == 1 and result["status"] == "cohort_deadline"


def test_cohort_monotonic_elapsed_narrows_deadline_and_never_widens():
    ticks = iter([0, 20, 40, 60])
    deadlines = []
    result = cohort(
        lambda item, cursor, end: (deadlines.append(end) or progress(item, cursor)),
        monotonic=lambda: next(ticks),
    )
    assert deadlines == [NOW + timedelta(seconds=s) for s in (280, 260, 240)]
    assert result["invocations"] == 3


def test_cohort_original_end_is_not_widened_and_visit_limit_is_finite():
    result = cohort(wall_seconds=900, max_visits=1)
    assert result["steps"][0]["deadline_utc"] == slot().ends_at.isoformat()
    assert result["invocations"] == 1 and result["status"] == "cohort_visit_limit"


@pytest.mark.parametrize("values", [[1, 0], [0, float("nan")], [0, float("inf")], [0, True]])
def test_cohort_invalid_monotonic_clock_never_calls_adapter(values):
    ticks, calls = iter(values), []
    with pytest.raises(PaperRoundContractError):
        cohort(lambda *_: calls.append(True), monotonic=lambda: next(ticks))
    assert not calls


@pytest.mark.parametrize("changes", [
    {"completed": -1}, {"completed": 4}, {"completed": True},
    {"work_units": 0}, {"work_units": 513}, {"max_visits": 33},
    {"max_visits": True}, {"wall_seconds": 901}, {"adapter_ref": "unbound"},
])
def test_cohort_bad_contract_rejected_before_effects(changes):
    calls = []
    with pytest.raises(PaperRoundContractError):
        cohort(lambda *_: calls.append(True), **changes)
    assert not calls


def test_cohort_callback_exception_stops_and_redacts_private_error():
    def fail(*_):
        raise OSError("private-do-not-retain")

    result = cohort(fail)
    assert result["invocations"] == 1 and result["completed_after"] == 0
    assert result["steps"][0]["category"] == "OSError"
    assert "private-do-not-retain" not in str(result)


def test_cohort_process_interrupt_is_not_swallowed():
    def fail(*_):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        cohort(fail)

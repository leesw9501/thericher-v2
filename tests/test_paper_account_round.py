from datetime import UTC, datetime, timedelta, timezone

import pytest

from thericher_v2.execution.paper_account_round import (
    PaperRoundContractError,
    PaperRoundSlot,
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

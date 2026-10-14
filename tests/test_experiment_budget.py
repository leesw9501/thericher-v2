"""Synthetic clocks only; the Engine sidecar owns the actual pinned-loader SYN."""

import ast
import hashlib
import io
import json
import socket
from itertools import chain, repeat
from pathlib import Path

import pytest

from thericher_v2.research import experiment_budget as module
from thericher_v2.research.experiment_budget import BudgetExceeded, BudgetProtocol, DualClockBudget


class Clock:
    def __init__(self):
        self.w, self.m = 1000.0, 100.0

    def wall(self):
        return self.w

    def mono(self):
        return self.m

    def advance(self, seconds):
        self.w += seconds
        self.m += seconds


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("network_forbidden")

    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture
def clock():
    return Clock()


def budget(clock, **changes):
    fields = dict(appointment_epoch=clock.w, active_cap=10, end_cap=30,
                  active_charged=2, reserve=1, wall=clock.wall, mono=clock.mono)
    return DualClockBudget(**(fields | changes))


def test_strict_finite_nonnegative_parameters(clock):
    for field in ("appointment_epoch", "active_cap", "end_cap", "active_charged",
                  "elapsed_charged", "reserve"):
        for value in (True, False, "1", None, -1, float("inf"), float("nan"), 10**1000):
            with pytest.raises(ValueError, match="budget_number_invalid"):
                budget(clock, **{field: value})


def test_positive_caps_reserve_and_frozen_appointment(clock):
    for changes in (dict(active_cap=0), dict(end_cap=0), dict(reserve=10),
                    dict(appointment_epoch=clock.w + 1), dict(wall=1), dict(mono=None)):
        with pytest.raises(ValueError):
            budget(clock, **changes)
    current = budget(clock, appointment_epoch=clock.w - 5)
    clock.advance(3)
    assert current.snapshot()["appointment_epoch"] == 995
    assert current.elapsed == 8 and current.charged == 2
    clock.w = clock.m = 1e308
    current = budget(clock, appointment_epoch=0, active_cap=1e308, end_cap=1.7e308)
    current.check()
    assert current.elapsed == 1e308


def test_queue_time_is_elapsed_not_active_debit(clock):
    current = budget(clock)
    clock.advance(5)
    current.check()
    assert current.active == 2 and current.elapsed == 5
    with current.owned_worker():
        clock.advance(3)
    assert current.charged == 5 and current.elapsed == 8


def test_repeated_checks_and_snapshots_never_double_debit(clock):
    current = budget(clock)
    with current.owned_worker():
        clock.advance(3)
        for _ in range(10):
            current.check()
            assert current.active == 5 and current.charged == 2
            assert current.snapshot()["active_owned_seconds"] == 5
    for _ in range(10):
        current.check()
    assert current.charged == 5


def test_failure_and_cleanup_charged_once_original_error_preserved(clock):
    current = budget(clock)
    error = RuntimeError("synthetic_failure")
    with pytest.raises(RuntimeError) as caught:
        with current.owned_worker():
            try:
                clock.advance(3)
                raise error
            finally:
                clock.advance(2)
    assert caught.value is error and current.charged == 7
    with current.owned_worker():
        clock.advance(1)
    assert current.charged == 8


def test_carried_charge_is_not_refunded_even_if_already_exhausted(clock):
    current = budget(clock, active_charged=12)
    with pytest.raises(BudgetExceeded, match="active_owned_worker_cap"):
        with current.owned_worker():
            pytest.fail("exhausted_worker_entered")
    with pytest.raises(AttributeError):
        current.charged = 0
    assert current.snapshot()["active_owned_seconds"] == 12


def test_nested_scope_denied_outer_cleanup_still_charged(clock):
    current = budget(clock)
    with current.owned_worker():
        clock.advance(2)
        with pytest.raises(ValueError, match="nested_owner_scope"):
            with current.owned_worker():
                pytest.fail("nested_worker_entered")
        clock.advance(1)
    assert current.charged == 5


def test_publication_type_is_exact_bool_without_clock_calls(clock):
    current = budget(clock)
    current._mono = lambda: pytest.fail("invalid_publication_sampled_clock")
    for value in (1, 0, None, "true", [], object()):
        with pytest.raises(TypeError, match="publication_boolean"):
            current.check(publication=value)
        with pytest.raises(TypeError, match="publication_boolean"):
            with current.owned_worker(publication=value):
                pytest.fail("invalid_publication_entered")


def test_publication_uses_reserve_but_cannot_bypass_active_cap(clock):
    current = budget(clock, active_charged=9)
    with pytest.raises(BudgetExceeded):
        current.check()
    current.check(publication=True)
    with pytest.raises(BudgetExceeded, match="active_owned_worker_cap"):
        with current.owned_worker(publication=True):
            clock.advance(1)
    assert current.charged == 10
    with pytest.raises(BudgetExceeded):
        current.check(publication=True)


def test_publication_never_bypasses_either_end_clock(clock):
    for jump in ("wall", "mono"):
        local = Clock()
        current = budget(local)
        local.advance(29)
        with pytest.raises(BudgetExceeded, match="end_to_end_cap"):
            current.check()
        current.check(publication=True)
        if jump == "wall":
            local.w += 1
        else:
            local.m += 1
        with pytest.raises(BudgetExceeded, match="end_to_end_cap"):
            current.check(publication=True)
        assert current.charged == 2


def test_wall_rollback_never_rewinds_elapsed_or_restores_capacity(clock):
    current = budget(clock)
    clock.w += 29
    assert current.elapsed == 29
    clock.w -= 100
    clock.m += 2
    assert current.elapsed == 29
    with pytest.raises(BudgetExceeded, match="end_to_end_cap"):
        current.check()
    clock.m += 28
    with pytest.raises(BudgetExceeded):
        current.check(publication=True)


def test_monotonic_rollback_latches_failure_without_refunding_known_charge(clock):
    current = budget(clock)
    with pytest.raises(ValueError, match="budget_clock_invalid"):
        with current.owned_worker():
            clock.advance(3)
            current.check()
            clock.m -= 2
    assert current.charged == 5
    clock.m += 10
    with pytest.raises(ValueError, match="budget_clock_invalid"):
        current.check(publication=True)


def test_invalid_clock_readings_deny_and_charge_valid_monotonic_progress(clock):
    for field in ("w", "m"):
        for value in (-1, float("nan"), float("inf"), True):
            local = Clock()
            current = budget(local)
            with pytest.raises(ValueError, match="budget_clock_invalid"):
                with current.owned_worker():
                    local.advance(2)
                    current.check()
                    local.advance(1)
                    setattr(local, field, value)
            assert current.charged == (5 if field == "w" else 4)


def test_success_exit_checks_caps_and_failed_exit_preserves_original_error(clock):
    current = budget(clock)
    with pytest.raises(BudgetExceeded, match="end_to_end_cap"):
        with current.owned_worker():
            clock.w += 30
            clock.m += 1
    assert current.charged == 3
    current = budget(clock)
    error = RuntimeError("synthetic_failure")
    with pytest.raises(RuntimeError) as caught:
        with current.owned_worker():
            clock.advance(12)
            raise error
    assert caught.value is error and current.charged == 14
    with pytest.raises(BudgetExceeded):
        current.check(publication=True)


def test_native_sha_signature_contract_accepts_publication_keyword_without_io(clock):
    def sha(path, guard: BudgetProtocol):
        guard.check(publication=True)
        return hashlib.sha256(path.read()).hexdigest()

    current = budget(clock, active_charged=9)
    data = b"invented SYN bytes only"
    assert sha(io.BytesIO(data), current) == hashlib.sha256(data).hexdigest()
    clock.advance(30)
    with pytest.raises(BudgetExceeded):
        sha(io.BytesIO(data), current)


def test_snapshot_numeric_only_and_module_has_no_io_or_authority_dependencies(clock):
    current = budget(clock)
    snapshot = current.snapshot()
    assert set(snapshot) == {"appointment_epoch", "active_owned_seconds", "end_to_end_seconds",
                             "active_cap", "end_cap", "clock_failed"}
    assert snapshot["clock_failed"] is False
    assert all(type(value) is float for key, value in snapshot.items() if key != "clock_failed")
    json.dumps(snapshot, allow_nan=False)
    tree = ast.parse(Path(module.__file__).read_text())
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
    assert imported == {"math", "time", "contextlib", "typing"}
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)}
    assert not calls & {"open", "print", "getenv", "exec", "eval"}


def test_restart_carries_elapsed_high_water_after_wall_rollback(clock):
    original = budget(clock)
    clock.advance(30)
    with pytest.raises(BudgetExceeded):
        original.check(publication=True)
    retained = original.snapshot()
    clock.w = 1001
    restarted = budget(clock, appointment_epoch=retained["appointment_epoch"],
                       active_charged=retained["active_owned_seconds"],
                       elapsed_charged=retained["end_to_end_seconds"],
                       clock_failed=retained["clock_failed"])
    with pytest.raises(BudgetExceeded, match="end_to_end_cap"):
        restarted.check(publication=True)


def test_clock_failure_inside_body_charges_later_monotonic_cleanup(clock):
    current = budget(clock)
    with pytest.raises(ValueError, match="budget_clock_invalid"):
        with current.owned_worker():
            try:
                clock.advance(2)
                clock.w = float("nan")
                current.check()
            finally:
                clock.m += 5
    assert current.charged == 9
    assert current.snapshot()["clock_failed"] is True
    assert current.snapshot()["end_to_end_seconds"] == 7


def test_fault_state_survives_restart_even_after_clock_recovers(clock):
    current = budget(clock)
    clock.w = float("nan")
    with pytest.raises(ValueError, match="budget_clock_invalid"):
        current.check()
    retained = current.snapshot()
    clock.w = 1001
    recovered = budget(clock, elapsed_charged=retained["end_to_end_seconds"],
                       clock_failed=retained["clock_failed"])
    with pytest.raises(ValueError, match="budget_clock_invalid"):
        recovered.check(publication=True)


def test_clock_fault_flag_requires_boolean(clock):
    for value in (1, 0, None, "false"):
        with pytest.raises(ValueError, match="budget_clock_state_invalid"):
            budget(clock, clock_failed=value)


@pytest.mark.parametrize("last", [99, 110])
def test_final_cleanup_sample_cannot_silently_fault_or_exhaust(last):
    readings = chain([100, 100, last], repeat(last))
    current = DualClockBudget(appointment_epoch=1000, active_cap=10, end_cap=30,
                              wall=lambda: 1000, mono=lambda: next(readings))
    with pytest.raises((ValueError, BudgetExceeded)):
        with current.owned_worker():
            pass
    assert current.snapshot()["clock_failed"] is (last == 99)

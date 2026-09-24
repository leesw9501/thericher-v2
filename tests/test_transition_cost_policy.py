"""Synthetic-only tests of the pure transition-cost target policy."""

from __future__ import annotations

import ast
import builtins
import json
import socket
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.research import transition_cost_policy as s

OPEN = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
FIRST = OPEN + timedelta(hours=3)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def inputs(forecasts, *, terminal=None, offsets=None, keys=None, **kwargs):
    n = len(forecasts)
    return dict(
        forecasts=np.array(forecasts, dtype=np.float64),
        times=tuple(FIRST + s.HOLD * i for i in range(n))
        if offsets is None
        else tuple(FIRST + timedelta(minutes=i) for i in offsets),
        session_keys=(OPEN,) * n if keys is None else tuple(keys),
        terminal=np.zeros(n, dtype=bool) if terminal is None else np.array(terminal, dtype=bool),
        **kwargs,
    )


@pytest.mark.parametrize("cost", [0.0, 3.0])
@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("side", [-1, 0, 1])
def test_threshold_ties_and_adjacent_floats(cost, held, terminal, side):
    threshold = (0.0 if terminal else -cost) if held else cost * (1 + terminal)
    forecast = threshold if side == 0 else np.nextafter(threshold, np.inf * side)
    forecasts = [100.0, forecast] if held else [forecast]
    flags = [False, terminal] if held else [terminal]
    result = s.target_positions(**inputs(forecasts, terminal=flags, cost_bps=cost))
    assert bool(result.targets[-1]) == (side > 0)


def test_held_negative_forecast_continues_then_exits_at_tie():
    result = s.target_positions(**inputs([4, -2, -3, 3, 4, -4]))
    assert result.targets.tolist() == [True, True, False, False, True, False]
    assert result.counts == dict(enter=2, hold=1, exit=2, flat=1, expiry_exit=0)


def test_stateless_decision_uses_cash_but_bookkeeping_uses_actual_position():
    args = inputs([4, 4, -2, 4])
    stateful = s.target_positions(**args)
    stateless = s.target_positions(**args, stateful=False)
    assert stateful.targets.tolist() == [True, True, True, True]
    assert stateful.counts == dict(enter=1, hold=3, exit=0, flat=0, expiry_exit=1)
    assert stateless.targets.tolist() == [True, True, False, True]
    assert stateless.counts == dict(enter=2, hold=1, exit=1, flat=0, expiry_exit=1)


def test_gap_expires_previous_lease_and_resets_decision_state():
    result = s.target_positions(**inputs([4, -2, 4, -2], offsets=[0, 60, 90, 150]))
    assert result.targets.tolist() == [True, False, True, False]
    assert result.counts == dict(enter=2, hold=0, exit=0, flat=2, expiry_exit=2)


def test_gap_one_microsecond_beyond_lease_does_not_carry():
    args = inputs([4, -2])
    args["times"] = (FIRST, FIRST + s.HOLD + timedelta(microseconds=1))
    result = s.target_positions(**args)
    assert result.targets.tolist() == [True, False]
    assert result.counts["expiry_exit"] == 1


def test_new_session_even_at_contiguous_time_resets_state():
    next_open = FIRST + timedelta(minutes=15)
    result = s.target_positions(**inputs([4, -2], keys=[OPEN, next_open]))
    assert result.targets.tolist() == [True, False]
    assert result.counts == dict(enter=1, hold=0, exit=0, flat=1, expiry_exit=1)


def test_terminal_held_policy_pays_exit_cost_and_next_session_starts_flat():
    result = s.target_positions(
        **inputs(
            [4, 0.01, -2],
            terminal=[False, True, False],
            offsets=[0, 30, 1440],
            keys=[OPEN, OPEN, OPEN + timedelta(days=1)],
        )
    )
    assert result.targets.tolist() == [True, True, False]
    assert result.counts == dict(enter=1, hold=1, exit=0, flat=1, expiry_exit=1)


def test_terminal_flag_is_not_inferred_from_missing_next_row():
    nonterminal = s.target_positions(**inputs([4]))
    terminal = s.target_positions(**inputs([4], terminal=[True]))
    assert nonterminal.targets.tolist() == [True]
    assert terminal.targets.tolist() == [False]
    assert nonterminal.counts["expiry_exit"] == 1
    assert terminal.counts["expiry_exit"] == 0


@pytest.mark.parametrize("stateful", [False, True])
def test_every_prefix_and_changed_future_leave_earlier_targets_unchanged(stateful):
    args = inputs([4, -2, -3, 7, 0, 8, -2], terminal=[False] * 6 + [True], stateful=stateful)
    full = s.target_positions(**args)
    for stop in range(1, len(args["times"]) + 1):
        prefix = {k: v[:stop] if isinstance(v, (tuple, np.ndarray)) else v for k, v in args.items()}
        np.testing.assert_array_equal(s.target_positions(**prefix).targets, full.targets[:stop])
    changed = dict(args)
    changed["forecasts"] = args["forecasts"].copy()
    changed["forecasts"][3:] = -999
    changed["terminal"] = np.zeros(7, dtype=bool)
    changed["times"] = args["times"][:3] + tuple(
        FIRST + timedelta(days=1) + s.HOLD * i for i in range(4)
    )
    changed["session_keys"] = (OPEN,) * 3 + (OPEN + timedelta(days=1),) * 4
    np.testing.assert_array_equal(s.target_positions(**changed).targets[:3], full.targets[:3])


@pytest.mark.parametrize("stateful", [False, True])
@pytest.mark.parametrize("cost", [0.0, 3.0])
def test_matches_literal_utility_and_lease_bookkeeping(stateful, cost):
    rng = np.random.default_rng(811)
    forecasts = rng.integers(-10, 11, size=60).astype(np.float64)
    times, keys, flags = [], [], []
    for day in range(10):
        times.extend(FIRST + timedelta(days=day, minutes=30 * i) for i in (0, 1, 2, 4, 5, 6))
        keys.extend([OPEN + timedelta(days=day)] * 6)
        flags.extend([False] * 5 + [True])
    result = s.target_positions(
        forecasts=forecasts,
        times=tuple(times),
        session_keys=tuple(keys),
        terminal=np.array(flags),
        cost_bps=cost,
        stateful=stateful,
    )
    previous = False
    expected = []
    counts = dict.fromkeys(s.COUNT_KEYS, 0)
    for i, forecast in enumerate(forecasts):
        contiguous = i > 0 and times[i] - times[i - 1] == s.HOLD and keys[i] == keys[i - 1]
        if previous and not contiguous:
            counts["expiry_exit"] += 1
        actual = previous and contiguous
        q = int(actual) if stateful else 0
        utility = [x * forecast - cost * abs(x - q) - cost * x * flags[i] for x in (0, 1)]
        selected = utility[1] > utility[0]
        counts[
            ("hold" if selected else "exit") if actual else ("enter" if selected else "flat")
        ] += 1
        expected.append(selected)
        previous = selected
    counts["expiry_exit"] += int(previous)
    assert result.targets.tolist() == expected
    assert result.counts == counts
    assert counts["enter"] == counts["exit"] + counts["expiry_exit"]
    assert sum(counts[k] for k in s.COUNT_KEYS[:4]) == len(forecasts)


def test_frozen_readonly_closed_json_counts_and_no_input_mutation():
    args = inputs([4, -2, 0], terminal=[False, False, True])
    before = {k: v.copy() for k, v in args.items() if isinstance(v, np.ndarray)}
    result = s.target_positions(**args)
    assert result.targets.shape == (3,) and result.targets.dtype == np.bool_
    assert not result.targets.flags.writeable
    assert tuple(result.counts) == s.COUNT_KEYS
    assert all(type(value) is int and value >= 0 for value in result.counts.values())
    json.dumps(result.counts, allow_nan=False)
    assert "array(" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.counts = {}
    with pytest.raises(ValueError):
        result.targets[0] = False
    for key, value in before.items():
        np.testing.assert_array_equal(args[key], value)


def test_empty_input_is_empty_with_zero_counts():
    result = s.target_positions(**inputs([]))
    assert result.targets.shape == (0,) and not result.targets.flags.writeable
    assert result.counts == dict.fromkeys(s.COUNT_KEYS, 0)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("forecasts", [4.0], "forecasts_float64_vector_required"),
        ("forecasts", np.array([4], dtype=np.float32), "forecasts_float64_vector_required"),
        ("forecasts", np.array([[4.0]]), "forecasts_float64_vector_required"),
        ("forecasts", np.array([True]), "forecasts_float64_vector_required"),
        ("forecasts", np.array([np.nan]), "forecasts_nonfinite"),
        ("forecasts", np.array([np.inf]), "forecasts_nonfinite"),
        ("forecasts", np.array([-np.inf]), "forecasts_nonfinite"),
        ("terminal", [False], "terminal_bool_vector_required"),
        ("terminal", np.array([0]), "terminal_bool_vector_required"),
        ("terminal", np.array([[False]]), "terminal_bool_vector_required"),
        ("terminal", np.array([], dtype=bool), "terminal_bool_vector_required"),
        ("stateful", 1, "stateful_bool_required"),
        ("stateful", np.bool_(True), "stateful_bool_required"),
        ("cost_bps", True, "cost_nonnegative_finite_required"),
        ("cost_bps", "3", "cost_nonnegative_finite_required"),
        ("cost_bps", -1.0, "cost_nonnegative_finite_required"),
        ("cost_bps", np.nan, "cost_nonnegative_finite_required"),
        ("cost_bps", np.inf, "cost_nonnegative_finite_required"),
        ("cost_bps", None, "cost_nonnegative_finite_required"),
        ("cost_bps", 10**400, "cost_nonnegative_finite_required"),
    ],
)
def test_invalid_array_scalar_inputs_have_closed_errors(field, value, reason):
    args = inputs([4])
    args[field] = value
    with pytest.raises(ValueError, match=f"^{reason}$"):
        s.target_positions(**args)


@pytest.mark.parametrize("field", ["times", "session_keys"])
@pytest.mark.parametrize("case", ["list", "length", "naive", "offset", "text"])
def test_invalid_time_containers_and_utc_values(field, case):
    args = inputs([4])
    value = args[field][0]
    args[field] = {
        "list": [value],
        "length": (),
        "naive": (value.replace(tzinfo=None),),
        "offset": (value.astimezone(timezone(timedelta(hours=1))),),
        "text": ("private-input-must-not-appear",),
    }[case]
    reason = f"{field}_shape" if case in ("list", "length") else f"{field}_utc_required"
    with pytest.raises(ValueError, match=f"^{reason}$"):
        s.target_positions(**args)


@pytest.mark.parametrize(
    "offsets,reason",
    [([0, 0], "times_order"), ([30, 0], "times_order"), ([0, 29], "decision_overlap")],
)
def test_invalid_order_or_overlapping_leases(offsets, reason):
    with pytest.raises(ValueError, match=f"^{reason}$"):
        s.target_positions(**inputs([4, 4], offsets=offsets))


@pytest.mark.parametrize("gap", [30, 60])
@pytest.mark.parametrize("previous_target", [-10, 10])
def test_observed_terminal_prohibits_later_same_session(gap, previous_target):
    with pytest.raises(ValueError, match="^decision_after_terminal$"):
        s.target_positions(**inputs([previous_target, 4], terminal=[True, False], offsets=[0, gap]))


@pytest.mark.parametrize(
    "case,reason",
    [
        ("future", "session_open_after_decision"),
        ("decreasing", "session_keys_order"),
        ("reentry", "session_keys_order"),
        ("retroactive", "session_open_inconsistent"),
    ],
)
def test_inconsistent_session_keys(case, reason):
    args = inputs([4, 4, 4], offsets=[0, 1440, 2880])
    args["session_keys"] = {
        "future": (FIRST + timedelta(seconds=1), OPEN, OPEN),
        "decreasing": (OPEN, OPEN - timedelta(days=1), OPEN),
        "reentry": (OPEN, OPEN + timedelta(days=1), OPEN),
        "retroactive": (OPEN, OPEN + timedelta(minutes=30), OPEN + timedelta(minutes=30)),
    }[case]
    with pytest.raises(ValueError, match=f"^{reason}$"):
        s.target_positions(**args)


def test_noncontiguous_readonly_arrays_and_finite_extremes():
    forecasts = np.array([np.finfo(np.float64).max, 0, -np.finfo(np.float64).max, 0])[::2]
    forecasts.setflags(write=False)
    args = inputs([4, 4])
    args["forecasts"] = forecasts
    result = s.target_positions(**args)
    assert result.targets.tolist() == [True, False]
    args["cost_bps"] = np.finfo(np.float64).max
    args["terminal"][-1] = True
    assert not s.target_positions(**args).targets.any()


def test_no_io_or_outcomes_and_only_pure_imports(monkeypatch):
    source = Path(s.__file__).read_text(encoding="utf-8")
    imports = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module.split(".")[0])
    assert imports <= {"__future__", "math", "dataclasses", "datetime", "numpy"}

    def forbidden(*args, **kwargs):
        pytest.fail("IO forbidden")

    args = inputs([4, -2])
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(np, "load", forbidden)
        patch.setattr(np, "save", forbidden)
        assert s.target_positions(**args).targets.tolist() == [True, True]
        with pytest.raises(TypeError):
            s.target_positions(**args, outcomes=np.array([10.0, -10.0]))

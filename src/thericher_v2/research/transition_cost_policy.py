"""Pure one-step transition-cost heuristic; not a multi-step optimal policy."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

HOLD = timedelta(minutes=30)
COUNT_KEYS = ("enter", "hold", "exit", "flat", "expiry_exit")


@dataclass(frozen=True)
class TransitionTargets:
    targets: np.ndarray = field(repr=False)
    counts: dict[str, int]


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _utc_tuple(value, count, name):
    _require(type(value) is tuple and len(value) == count, f"{name}_shape")
    _require(
        all(
            isinstance(t, datetime) and t.tzinfo is not None and t.utcoffset() == timedelta(0)
            for t in value
        ),
        f"{name}_utc_required",
    )


def target_positions(
    *,
    forecasts: np.ndarray,
    times: tuple[datetime, ...],
    session_keys: tuple[datetime, ...],
    terminal: np.ndarray,
    cost_bps: float = 3.0,
    stateful: bool = True,
) -> TransitionTargets:
    """Choose x in {0,1} by x*f - c*abs(x-q) - c*x*terminal, ties to cash.

    Forecasts are gross H30 bps; c is the per-side decision cost. Each target
    leases [t,t+30m), extending only at a contiguous same-session decision.
    The caller supplies known-calendar terminal flags, never outcome masks.
    Stateless decisions use q=0, but bookkeeping uses actual prior targets.

    The first four counts partition decision rows. expiry_exit separately
    counts forced exits across gaps/sessions and at the final lease expiry.
    End-of-input expiry affects counts only, never the earlier chosen target.
    Empty input returns empty targets and zero counts. Errors are closed codes.
    """
    _require(
        isinstance(forecasts, np.ndarray)
        and forecasts.dtype == np.dtype("float64")
        and forecasts.ndim == 1,
        "forecasts_float64_vector_required",
    )
    _require(np.isfinite(forecasts).all(), "forecasts_nonfinite")
    n = len(forecasts)
    _require(
        isinstance(terminal, np.ndarray)
        and terminal.dtype == np.dtype("bool")
        and terminal.shape == (n,),
        "terminal_bool_vector_required",
    )
    _require(type(stateful) is bool, "stateful_bool_required")
    _require(type(cost_bps) in (int, float, np.float64), "cost_nonnegative_finite_required")
    try:
        cost = float(cost_bps)
    except OverflowError:
        raise ValueError("cost_nonnegative_finite_required") from None
    _require(math.isfinite(cost) and cost >= 0, "cost_nonnegative_finite_required")
    _utc_tuple(times, n, "times")
    _utc_tuple(session_keys, n, "session_keys")
    counts = dict.fromkeys(COUNT_KEYS, 0)
    targets = np.empty(n, dtype=bool)
    previous = False
    for i, (forecast, at, key, is_terminal) in enumerate(
        zip(forecasts, times, session_keys, terminal, strict=True)
    ):
        _require(key <= at, "session_open_after_decision")
        contiguous = False
        if i:
            gap = at - times[i - 1]
            _require(gap > timedelta(0), "times_order")
            _require(gap >= HOLD, "decision_overlap")
            same_session = key == session_keys[i - 1]
            if same_session:
                _require(not terminal[i - 1], "decision_after_terminal")
            else:
                _require(key > session_keys[i - 1], "session_keys_order")
                _require(key > times[i - 1], "session_open_inconsistent")
            contiguous = same_session and gap == HOLD
        if previous and not contiguous:
            counts["expiry_exit"] += 1
        actual = previous and contiguous
        q = actual and stateful
        # Algebraic thresholds avoid cancellation in long-utility minus flat-utility.
        threshold = (0.0 if is_terminal else -cost) if q else cost + cost * int(is_terminal)
        selected = bool(forecast > threshold)
        action = ("hold" if selected else "exit") if actual else ("enter" if selected else "flat")
        counts[action] += 1
        targets[i] = selected
        previous = selected
    counts["expiry_exit"] += int(previous)
    targets.setflags(write=False)
    return TransitionTargets(targets, counts)

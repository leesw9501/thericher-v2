"""Synthetic transition-cost decisions against the existing local-paper replay."""

import time
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import numpy as np
import pytest

from test_firstrate_position_policy import day as day
from test_firstrate_position_policy import no_external_io as no_external_io
from test_firstrate_session_research import source as source
from thericher_v2.research import policy_graph_replay as replay
from thericher_v2.research.transition_cost_policy import target_positions


@pytest.fixture
def emergency(tmp_path):
    return replay.h30.EmergencyStore(tmp_path / "emergency.json")


def choose(day, forecasts, *, stateful=True, terminal=None):
    return target_positions(
        forecasts=np.asarray(forecasts, dtype=np.float64),
        times=tuple(o.at for o in day.obs),
        session_keys=tuple(day.keys),
        terminal=np.asarray(
            [False] * (len(day.obs) - 1) + [True] if terminal is None else terminal, dtype=np.bool_
        ),
        cost_bps=3,
        stateful=stateful,
    )


def compare(day, emergency, targets, cost=3, cached=None):
    return replay.compare_policy(
        ident={},
        observations=day.obs,
        outcomes=day.outcomes,
        selected=targets,
        keys=day.keys,
        keep=(True,) * len(day.obs),
        cost=cost,
        emergency=emergency,
        deadline=time.monotonic() + 30,
        replay=cached,
    )


@pytest.mark.parametrize(
    "lead,last,expected",
    [(0, 6, False), (0, 7, True), (4, 0, False), (4, 0.1, True), (4, -0.1, False)],
)
def test_terminal_thresholds_and_terminal_flat_replay(day, emergency, lead, last, expected):
    decision = choose(day, [-100] * 4 + [lead, last])
    assert decision.targets[-1] == expected
    assert decision.targets.dtype == np.bool_ and not decision.targets.flags.writeable
    assert isinstance(decision.counts, dict)
    result = compare(day, emergency, decision.targets)
    assert all(result[name]["terminal_flat"] for name in ("repeated", "persistent"))
    assert result["persistent"]["exposure_minutes"] == 30 * (int(lead > 3) + int(expected))


def test_nonterminal_ties_flat_and_stateful_hold_can_change_policy_exposure(day, emergency):
    forecasts = [3, 4, -2, -3, 4, 0]
    stateful = choose(day, forecasts)
    stateless = choose(day, forecasts, stateful=False)
    assert stateful.targets.tolist() == [False, True, True, False, True, False]
    assert stateless.targets.tolist() == [False, True, False, False, True, False]
    a, b = [compare(day, emergency, d.targets) for d in (stateful, stateless)]
    assert a["persistent"]["exposure_minutes"] == 90
    assert b["persistent"]["exposure_minutes"] == 60
    for cell in (a, b):
        assert cell["repeated"]["gross_dollars"] == cell["persistent"]["gross_dollars"]
        assert cell["repeated"]["exposure_sha256"] == cell["persistent"]["exposure_sha256"]


@pytest.mark.parametrize("stateful", [True, False])
def test_fixed_targets_cost_only_at_boundaries_with_independent_rounded_fees(
    day, emergency, stateful
):
    decision = choose(day, [4] * 5 + [7], stateful=stateful)
    assert decision.counts == {"enter": 1, "hold": 5, "exit": 0, "flat": 0, "expiry_exit": 1}
    before = decision.targets.tobytes()
    plans = replay.positions.plan_positions(day.obs, decision.targets, day.keys)
    cached = replay.make_cached_payoff()
    hashes = set()
    for cost in (1, 3, 5, 10):
        cell = compare(day, emergency, decision.targets, cost, cached)
        hashes.add(cell["decision_sha256"])
        for name, spans in zip(("repeated", "persistent"), plans, strict=True):
            fees = sum(
                (bar.open.quantize(Decimal(".0001")) * Decimal(cost) / 10000).quantize(
                    Decimal(".0001")
                )
                for first, last in spans
                for bar in (day.outcomes[first].bars[0], day.outcomes[last].bars[-1])
            )
            assert Decimal(cell[name]["fees_dollars"]) == fees
            assert cell[name]["fills"] == 2 * len(spans)
            assert cell[name]["terminal_flat"] and cell[name]["local_paper_replay_parity"]
        assert cell["repeated"]["fills"] == 12 and cell["persistent"]["fills"] == 2
        assert cell["persistent"]["exposure_minutes"] == 180
        assert Decimal(cell["persistent"]["net_dollars"]) - Decimal(
            cell["repeated"]["net_dollars"]
        ) == Decimal(cell["saved_fees_dollars"])
    assert len(hashes) == 1 and decision.targets.tobytes() == before


@pytest.mark.parametrize("boundary", ["gap", "session"])
def test_position_lease_expires_and_hold_threshold_resets(day, emergency, boundary):
    if boundary == "gap":
        day.obs, day.outcomes, day.keys = (
            values[:2] + values[3:] for values in (day.obs, day.outcomes, day.keys)
        )
    else:
        shift = timedelta(days=1)
        day.obs = day.obs[:2] + tuple(
            replace(
                o, at=o.at + shift, signal=replace(o.signal, start_ts=o.signal.start_ts + shift)
            )
            for o in day.obs[2:]
        )
        day.outcomes = day.outcomes[:2] + tuple(
            replay.h30.Outcome(tuple(replace(b, start_ts=b.start_ts + shift) for b in out.bars))
            for out in day.outcomes[2:]
        )
        day.keys = day.keys[:2] + tuple(k + shift for k in day.keys[2:])
    terminal = [False] * len(day.obs)
    terminal[-1] = True
    if boundary == "session":
        terminal[1] = True
    decision = choose(day, [4, 4] + [-1] * (len(day.obs) - 2), terminal=terminal)
    assert decision.targets.tolist() == [True, True] + [False] * (len(day.obs) - 2)
    assert decision.counts["expiry_exit"] == 1
    cell = compare(day, emergency, decision.targets)
    assert cell["persistent"]["roundtrips"] == 1
    assert cell["risk"]["persistent"]["max_holding_minutes"] == 60
    assert cell["persistent"]["terminal_flat"]


def test_calendar_terminal_is_not_last_available_observation(day, emergency):
    calendar_terminal = day.obs[-1].at
    day.obs, day.outcomes, day.keys = (values[:-1] for values in (day.obs, day.outcomes, day.keys))
    flags = [o.at == calendar_terminal for o in day.obs]
    assert not any(flags)
    decision = choose(day, [-100] * 4 + [4], terminal=flags)
    assert decision.targets.tolist() == [False] * 4 + [True]
    assert decision.counts["expiry_exit"] == 1
    cell = compare(day, emergency, decision.targets)
    assert cell["persistent"]["exposure_minutes"] == 30
    assert cell["persistent"]["terminal_flat"]

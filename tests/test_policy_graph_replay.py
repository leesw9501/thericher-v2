"""Synthetic local-paper replay only; no source data, model, or network access."""

import time
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from test_firstrate_position_policy import day as day
from test_firstrate_position_policy import no_external_io as no_external_io
from test_firstrate_session_research import source as source
from thericher_v2.research import policy_graph_replay as s


@pytest.fixture
def emergency(tmp_path):
    return s.h30.EmergencyStore(tmp_path / "emergency.json")


def compare(day, emergency, selected=None, *, cost=3, replay=None, keep=None):
    return s.compare_policy(
        ident={"candidate": "synthetic"},
        observations=day.obs,
        outcomes=day.outcomes,
        selected=np.ones(len(day.obs), dtype=bool) if selected is None else selected,
        keys=day.keys,
        keep=(True,) * len(day.obs) if keep is None else keep,
        cost=cost,
        emergency=emergency,
        deadline=time.monotonic() + 30,
        replay=replay,
    )


@pytest.mark.parametrize("cost", [1, 3, 5])
def test_real_payoff_preserves_all_pair_fields_and_fee_identity(day, emergency, cost):
    selected = np.ones(len(day.obs), dtype=bool)
    expected = s.positions.paired_cell(
        {"candidate": "synthetic"},
        day.obs,
        day.outcomes,
        selected,
        s.positions.plan_positions(day.obs, selected, day.keys),
        (True,) * len(day.obs),
        cost,
        emergency,
        time.monotonic() + 30,
    )
    result = compare(day, emergency, cost=cost)
    assert {k: v for k, v in result.items() if k != "risk"} == expected
    assert result["risk"]["repeated"]["max_holding_minutes"] == 30
    assert result["risk"]["persistent"]["max_holding_minutes"] == 180
    assert result["risk"]["persistent"]["mean_holding_minutes"] == 180
    assert Decimal(result["persistent"]["net_dollars"]) - Decimal(
        result["repeated"]["net_dollars"]
    ) == Decimal(result["saved_fees_dollars"])


@pytest.mark.parametrize(
    "case,maximum,mean",
    [
        ("gap", 90, 75),
        ("session", 90, 90),
        ("unselected", 90, 75),
    ],
)
def test_no_merge_across_gap_session_or_unselected(day, emergency, case, maximum, mean):
    selected = np.ones(len(day.obs), dtype=bool)
    if case == "gap":
        day.obs = day.obs[:2] + day.obs[3:]
        day.outcomes = day.outcomes[:2] + day.outcomes[3:]
        day.keys = day.keys[:2] + day.keys[3:]
        selected = np.ones(len(day.obs), dtype=bool)
    elif case == "session":
        day.keys = day.keys[:3] + (day.keys[0] + s.h30.HOLD,) * 3
    else:
        selected[2] = False
    result = compare(day, emergency, selected)
    assert result["persistent"]["roundtrips"] == 2
    assert result["risk"]["persistent"]["max_holding_minutes"] == maximum
    assert result["risk"]["persistent"]["mean_holding_minutes"] == mean


def test_all_flat_starts_at_zero_without_payoff(day, emergency):
    def forbidden(*args):
        pytest.fail("flat policy cannot execute a trade")

    result = compare(day, emergency, np.zeros(len(day.obs), dtype=bool), replay=forbidden)
    for name in ("repeated", "persistent"):
        assert result[name]["fills"] == 0
        assert result["risk"][name] == {
            "max_mark_to_market_drawdown_dollars": "0",
            "max_holding_minutes": 0,
            "mean_holding_minutes": 0.0,
        }


def set_opens(day, prices):
    day.obs, day.keys = day.obs[:1], day.keys[:1]
    bars = tuple(
        replace(bar, open=Decimal(price), high=Decimal(1000), low=Decimal(1), close=Decimal(100))
        for bar, price in zip(day.outcomes[0].bars, prices, strict=True)
    )
    day.outcomes = (s.h30.Outcome(bars),)


def test_drawdown_sees_intratrade_opens_and_fee_instants_not_only_closed_trades(day, emergency):
    set_opens(day, [100, 110, 80, 100, 100, 100, 110])
    result = compare(day, emergency, cost=3)
    assert Decimal(result["persistent"]["net_dollars"]) == Decimal("9.9370")
    assert Decimal(result["risk"]["persistent"]["max_mark_to_market_drawdown_dollars"]) == 30
    # A monotone rising trade still draws down by its exit fee from the pre-fee exit peak.
    set_opens(day, [100, 100, 100, 100, 100, 100, 110])
    result = compare(day, emergency, cost=3)
    assert Decimal(result["risk"]["persistent"]["max_mark_to_market_drawdown_dollars"]) == (
        Decimal("0.0330")
    )


def test_quantization_and_initial_zero_capture_entry_and_exit_fees(day, emergency):
    set_opens(day, ["100.123456"] * 7)
    result = compare(day, emergency)
    fee = (Decimal("100.1235") * 3 / 10000).quantize(Decimal("0.0001"))
    assert Decimal(result["risk"]["repeated"]["max_mark_to_market_drawdown_dollars"]) == 2 * fee
    assert Decimal(result["repeated"]["net_dollars"]) == -2 * fee


def test_drawdown_accumulates_prior_closed_net_across_trades(day, emergency):
    day.outcomes = tuple(
        s.h30.Outcome(
            tuple(
                replace(
                    b, open=Decimal(100), high=Decimal(101), low=Decimal(99), close=Decimal(100)
                )
                for b in outcome.bars
            )
        )
        for outcome in day.outcomes
    )
    result = compare(day, emergency)
    assert Decimal(result["risk"]["repeated"]["max_mark_to_market_drawdown_dollars"]) == (
        Decimal("0.36")
    )
    assert Decimal(result["risk"]["persistent"]["max_mark_to_market_drawdown_dollars"]) == (
        Decimal("0.06")
    )


def test_final_mark_net_must_match_replay_net(day, emergency):
    set_opens(day, [100, 100, 100, 100, 100, 100, 110])
    with pytest.raises(s.h30.StudyFailure, match="mark_to_market_net_parity"):
        compare(day, emergency, replay=lambda *_: (Decimal(0), Decimal(0)))


def test_future_high_low_close_do_not_change_risk(day, emergency):
    original = compare(day, emergency)
    day.outcomes = tuple(
        s.h30.Outcome(
            tuple(
                replace(b, high=Decimal(1000), low=Decimal(1), close=Decimal(500))
                for b in outcome.bars
            )
        )
        for outcome in day.outcomes
    )
    assert compare(day, emergency) == original


def test_cache_runs_real_local_paper_on_miss_and_reuses_across_policies(
    day, emergency, monkeypatch
):
    calls = []
    original = s.sessions.payoff

    def observed(*args):
        calls.append(args[:3])
        return original(*args)

    monkeypatch.setattr(s.sessions, "payoff", observed)
    replay = s.make_cached_payoff()
    first = compare(day, emergency, replay=replay)
    assert len(calls) == 7
    assert compare(day, emergency, replay=replay) == first
    assert len(calls) == 7
    compare(day, emergency, np.array([True, False, True, False, True, False]), replay=replay)
    assert len(calls) == 7
    compare(day, emergency, cost=5, replay=replay)
    assert len(calls) == 14


@pytest.mark.parametrize("change", ["signal", "interior", "exit", "symbol", "time"])
def test_cache_full_signal_path_and_time_prevent_collisions(day, emergency, monkeypatch, change):
    calls = []
    original = s.sessions.payoff

    def observed(*args):
        calls.append(None)
        return original(*args)

    monkeypatch.setattr(s.sessions, "payoff", observed)
    replay = s.make_cached_payoff()
    obs, outcome = day.obs[0], day.outcomes[0]
    replay(obs, outcome, 3, emergency)
    if change == "signal":
        obs = replace(obs, signal=replace(obs.signal, close=obs.signal.open - Decimal("0.01")))
    elif change in {"interior", "exit"}:
        bars = list(outcome.bars)
        index = 2 if change == "interior" else -1
        bars[index] = replace(bars[index], high=bars[index].high + 1)
        outcome = s.h30.Outcome(tuple(bars))
    elif change == "symbol":
        obs = replace(obs, signal=replace(obs.signal, symbol="QQQ"))
        outcome = s.h30.Outcome(tuple(replace(b, symbol="QQQ") for b in outcome.bars))
    else:
        obs = replace(obs, at=obs.at + s.h30.STEP)
    if change == "time":
        with pytest.raises(s.h30.StudyFailure, match="target_fee_replay_parity"):
            replay(obs, outcome, 3, emergency)
    else:
        replay(obs, outcome, 3, emergency)
    assert len(calls) == 2


def test_cache_does_not_bypass_existing_emergency_or_cross_store_scope(day, emergency, tmp_path):
    replay = s.make_cached_payoff()
    replay(day.obs[0], day.outcomes[0], 3, emergency)
    emergency.stop_new_orders("synthetic")
    with pytest.raises(s.h30.StudyFailure, match="roundtrip_rejected"):
        replay(day.obs[0], day.outcomes[0], 3, emergency)
    with pytest.raises(s.h30.StudyFailure, match="payoff_cache_emergency_scope"):
        replay(day.obs[0], day.outcomes[0], 3, s.h30.EmergencyStore(tmp_path / "other.json"))


def test_common_future_censoring_preserves_planned_decisions_and_only_scores_kept_sessions(
    source, emergency
):
    schedule, bars = source
    index = {b.start_ts: b for b in bars}
    obs, _ = s.h30.observe(index, s.sessions.session_grid(schedule[:12], 30, training=False))
    outcomes, _ = s.sessions.outcomes(index, obs, 30)
    keys = s.positions.session_keys(obs, schedule)
    args = dict(
        ident={},
        observations=obs,
        outcomes=outcomes,
        selected=np.ones(len(obs), dtype=bool),
        keys=keys,
        cost=3,
        emergency=emergency,
        deadline=time.monotonic() + 30,
        replay=s.make_cached_payoff(),
    )
    keep, _ = s.positions.common_support(obs, outcomes, keys)
    before = s.compare_policy(**args, keep=keep)
    changed = list(outcomes)
    changed[2] = None
    keep, _ = s.positions.common_support(obs, changed, keys)
    after = s.compare_policy(**{**args, "outcomes": changed}, keep=keep)
    assert before["decision_sha256"] == after["decision_sha256"]
    assert before["selected_decisions"] == after["selected_decisions"] == 72
    assert after["selected_censored"] == 6
    assert after["repeated"]["roundtrips"] == 66
    assert after["persistent"]["roundtrips"] == 11
    assert after["risk"]["persistent"]["mean_holding_minutes"] == 180


def test_deadline_and_partial_session_mask_are_rejected(day, emergency):
    with pytest.raises(s.h30.StudyFailure, match="common_support_mask"):
        compare(day, emergency, keep=(False, True, True, True, True, True))
    with pytest.raises(s.h30.StudyFailure, match="budget_exhausted"):
        s.compare_policy(
            ident={},
            observations=day.obs,
            outcomes=day.outcomes,
            selected=np.zeros(len(day.obs), dtype=bool),
            keys=day.keys,
            keep=(True,) * len(day.obs),
            cost=3,
            emergency=emergency,
            deadline=0,
        )

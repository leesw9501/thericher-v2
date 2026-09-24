"""Same-session, fixed-one-share policy replay; marked PnL is not portfolio NAV."""

from datetime import timedelta
from decimal import Decimal

from thericher_v2.research import firstrate_position_policy as positions

sessions, h30 = positions.sessions, positions.h30
_TICK = Decimal("0.0001")


def make_cached_payoff():
    """Return a payoff cache owned by one caller fold and one emergency store.

    Only successful scalar results are cached. Full immutable bars, including
    the signal bar, distinguish paths even when endpoints or timestamps match.
    """
    cache = {}
    unbound = object()
    owner = unbound

    def payoff(obs, outcome, cost, emergency):
        nonlocal owner
        if owner is unbound:
            owner = emergency
        sessions.require(emergency is owner, "payoff_cache_emergency_scope")
        key = (obs.at, obs.signal, tuple(outcome.bars), cost)
        if key not in cache or emergency.read().blocks_new_orders:
            cache[key] = sessions.payoff(obs, outcome, cost, emergency)
        return cache[key]

    return payoff


def compare_policy(
    *, ident, observations, outcomes, selected, keys, keep, cost, emergency, deadline, replay=None
):
    """Add open-mark risk to the existing paired cell using caller common_support.

    ``keep`` is the fold-wide mask from positions.common_support, shared by all
    policies. Plans and decision hashes retain the pre-censor decisions. Risk
    dollars are strings; maximum/mean holding minutes are integer/float values.
    """
    h30.check_time(deadline)
    plans = positions.plan_positions(observations, selected, keys)
    sessions.require(len(outcomes) == len(keep) == len(observations), "replay_shape")
    session_keep = {}
    for key, retained, outcome in zip(keys, keep, outcomes, strict=True):
        sessions.require(
            type(retained) is bool
            and session_keep.setdefault(key, retained) == retained
            and (not retained or outcome is not None),
            "common_support_mask",
        )
    cell = positions.paired_cell(
        ident,
        observations,
        outcomes,
        selected,
        plans,
        keep,
        cost,
        emergency,
        deadline,
        sessions.payoff if replay is None else replay,
    )
    cell["risk"] = {
        name: _marked_risk(outcomes, spans, keep, cost, cell[name]["net_dollars"], deadline)
        for name, spans in zip(("repeated", "persistent"), plans, strict=True)
    }
    return cell


def _marked_risk(outcomes, spans, keep, cost, expected_net, deadline):
    closed = peak = drawdown = Decimal(0)
    holding = []

    def mark(value):
        nonlocal peak, drawdown
        peak = max(peak, value)
        drawdown = max(drawdown, peak - value)

    for first, last in spans:
        h30.check_time(deadline)
        if not keep[first]:
            continue
        entry, exit_price = outcomes[first].entry, outcomes[last].exit
        entry_fee = (entry * cost / 10000).quantize(_TICK)
        exit_fee = (exit_price * cost / 10000).quantize(_TICK)
        mark(closed - entry_fee)
        # Shared H30 boundary bars are marked once while the share stays held.
        for index in range(first, last + 1):
            h30.check_time(deadline)
            bars = outcomes[index].bars
            for bar in bars if index == first else bars[1:]:
                mark(closed + bar.open.quantize(_TICK) - entry - entry_fee)
        closed += exit_price - entry - entry_fee - exit_fee
        mark(closed)
        holding.append(
            (outcomes[last].bars[-1].start_ts - outcomes[first].bars[0].start_ts)
            // timedelta(minutes=1)
        )
    sessions.require(closed == Decimal(expected_net), "mark_to_market_net_parity")
    return {
        "max_mark_to_market_drawdown_dollars": str(drawdown),
        "max_holding_minutes": max(holding, default=0),
        "mean_holding_minutes": sum(holding) / len(holding) if holding else 0.0,
    }

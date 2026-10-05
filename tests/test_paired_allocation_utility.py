"""Synthetic joint-cash accounting, causal geometry and CPU autograd parity."""

import socket
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research import paired_allocation_utility as s
from thericher_v2.research.adjusted_monthly_net_utility import (
    numpy_net_utility,
    torch_net_utility,
)
from thericher_v2.research.paired_completed_context import build_paired_completed_context


def arrays(weights=((0.4, 0.3, 0.3), (0.2, 0.6, 0.2), (0, 0, 1))):
    return np.asarray(weights, dtype=np.float64), np.asarray(
        ((1.12, 0.87), (0.91, 1.08), (2.0, 0.5)), dtype=np.float64
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic computation must not access a network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def torch():
    module = pytest.importorskip("torch")
    previous = module.get_num_threads()
    module.set_num_threads(1)
    try:
        yield module
    finally:
        module.set_num_threads(previous)


@pytest.mark.parametrize("cost", (0, 3, 4.5, 6, 100, Decimal("9999")))
@pytest.mark.parametrize(
    "weights",
    (
        ((0, 0, 1),) * 3,
        ((1, 0, 0),) * 3,
        ((0, 1, 0),) * 3,
        ((0.5, 0.5, 0),) * 3,
        ((0.4, 0.3, 0.3), (0.2, 0.6, 0.2), (0, 0, 1)),
    ),
)
def test_numpy_matches_shared_decimal_replay(weights, cost):
    weights, growth = arrays(weights)
    actual = s.numpy_daily_flat_nav(weights, growth, cost_bps=cost)
    expected = s.decimal_daily_flat_nav(weights, growth, cost_bps=cost)
    assert len(actual) == 3
    assert np.allclose(actual, [float(v) for v in expected], rtol=3e-12, atol=1e-14)
    assert not actual.flags.writeable


@pytest.mark.parametrize("cost", (0, 3, 4.5, 6, 100))
def test_torch_matches_numpy_decimal_and_existing_utility(torch, cost):
    weights, growth = arrays()
    tensor = torch.tensor(weights, dtype=torch.float64, requires_grad=True)
    actual = s.torch_daily_flat_nav(torch, tensor, growth, cost_bps=cost)
    expected = s.numpy_daily_flat_nav(weights, growth, cost_bps=cost)
    assert actual.shape == (3,)
    assert np.allclose(actual.detach().numpy(), expected, rtol=1e-13, atol=1e-13)
    utility = torch_net_utility(torch, actual)
    assert float(utility.detach()) == pytest.approx(numpy_net_utility(expected), rel=1e-12)
    utility.backward()
    assert tensor.grad is not None and bool(torch.isfinite(tensor.grad).all())


def test_exact_entry_solve_and_marked_exit_cost_not_nominal_roundtrip():
    weights = np.asarray(((0.3, 0.2, 0.5),), dtype=np.float64)
    growth = np.asarray(((2, 0.5),), dtype=np.float64)
    fee, risk, marked = 0.01, 0.5, 0.3 * 2 + 0.2 * 0.5
    expected = (0.5 + (1 - fee) * marked) / (1 + fee * risk)
    actual = s.numpy_daily_flat_nav(weights, growth, cost_bps=100)[0]
    assert actual == pytest.approx(expected, rel=1e-14)
    assert actual != pytest.approx(0.5 + marked - 2 * fee * risk, abs=1e-8)


def test_core_fee_solver_called_once_for_shared_entry_and_once_for_shared_exit(monkeypatch):
    calls, original = [], s.rebalance

    def traced(stock, nav, weight, fee):
        result = original(stock, nav, weight, fee)
        calls.append((stock, nav, weight, fee, result))
        return result

    monkeypatch.setattr(s, "rebalance", traced)
    weights, growth = arrays()
    nav = s.decimal_daily_flat_nav(weights, growth, cost_bps=6)
    assert len(calls) == 6
    for i in range(3):
        entry, exit_ = calls[2 * i : 2 * i + 2]
        assert entry[0] == 0
        assert entry[1] == (Decimal(1) if i == 0 else nav[i - 1])
        assert exit_[2] == 0 and exit_[4][0] == 0
        assert exit_[4][1] == nav[i]
        with localcontext() as context:
            context.prec = 50
            for stock, initial, _, fee, result in (entry, exit_):
                new_stock, cash, paid, traded = result
                assert paid == fee * traded
                assert traded == abs(new_stock - stock)
                assert abs(new_stock + cash + paid - initial) < Decimal("1e-40")


def test_one_shared_nav_compounds_without_resets_or_two_independent_sleeves():
    weights = np.asarray(((0.5, 0.5, 0),) * 2, dtype=np.float64)
    growth = np.asarray(((2, 0.5), (0.5, 2)), dtype=np.float64)
    result = s.numpy_daily_flat_nav(weights, growth, cost_bps=0)
    assert np.array_equal(result, (1.25, 1.5625))
    independent_sleeves = 0.5 * np.cumprod(growth[:, 0]) + 0.5 * np.cumprod(growth[:, 1])
    assert not np.array_equal(result, independent_sleeves)


def test_columns_are_qqq_spy_cash_and_cash_has_no_return_or_fee():
    growth = np.asarray(((1.2, 0.8),), dtype=np.float64)
    for weights, expected in (((1, 0, 0), 1.2), ((0, 1, 0), 0.8), ((0, 0, 1), 1)):
        assert (
            s.numpy_daily_flat_nav(np.asarray((weights,), dtype=np.float64), growth, cost_bps=0)[0]
            == expected
        )
    weights, growth = arrays(((0, 0, 1),) * 3)
    assert np.array_equal(s.numpy_daily_flat_nav(weights, growth, cost_bps=9999), np.ones(3))


def test_inputs_are_unchanged_and_later_outcome_cannot_change_earlier_nav():
    weights, growth = arrays()
    original_weights, original_growth = weights.copy(), growth.copy()
    first = s.numpy_daily_flat_nav(weights, growth)
    changed = growth.copy()
    changed[1:] *= 17
    later = s.numpy_daily_flat_nav(weights, changed)
    assert first[0] == later[0]
    assert np.array_equal(weights, original_weights)
    assert np.array_equal(growth, original_growth)


def test_only_small_simplex_roundoff_is_normalized_without_mutating_weights(torch):
    weights, growth = arrays()
    weights[0, 2] += 1e-13
    original = weights.copy()
    normalized = weights / weights.sum(axis=1, keepdims=True)
    expected = s.numpy_daily_flat_nav(normalized, growth)
    assert np.array_equal(s.numpy_daily_flat_nav(weights, growth), expected)
    actual = s.torch_daily_flat_nav(torch, torch.tensor(weights), growth)
    assert np.allclose(actual.numpy(), expected, rtol=1e-13, atol=1e-13)
    assert np.array_equal(weights, original)


@pytest.mark.parametrize("cost", (True, "3", -1, 10000, float("nan"), float("inf")))
def test_torch_rejects_invalid_cost(torch, cost):
    weights, growth = arrays()
    with pytest.raises(ValueError, match="daily_flat_cost"):
        s.torch_daily_flat_nav(torch, torch.tensor(weights), growth, cost_bps=cost)


@pytest.mark.parametrize("invalid", ("float32", "nan", "short", "negative", "sum", "bool"))
def test_torch_rejects_malformed_weights(torch, invalid):
    weights, growth = arrays()
    value = torch.tensor(weights)
    if invalid == "float32":
        value = value.float()
    elif invalid == "nan":
        value[0, 0] = float("nan")
    elif invalid == "short":
        value = value[:-1]
    elif invalid == "negative":
        value[0] = torch.tensor((-0.1, 0.6, 0.5))
    elif invalid == "sum":
        value[0, 0] += 0.1
    else:
        value = value.bool()
    with pytest.raises(ValueError, match="daily_flat_(weights|simplex)"):
        s.torch_daily_flat_nav(torch, value, growth)


@pytest.mark.parametrize("cost", (True, "3", None, -1, 10000, float("nan"), float("inf")))
def test_invalid_cost_is_rejected_in_both_references(cost):
    weights, growth = arrays()
    for function in (s.numpy_daily_flat_nav, s.decimal_daily_flat_nav):
        with pytest.raises(ValueError, match="daily_flat_cost"):
            function(weights, growth, cost_bps=cost)


@pytest.mark.parametrize(
    "weights",
    (
        np.ones((3, 2)),
        np.ones((2, 3)),
        np.full((3, 3), np.nan),
        np.asarray(((-0.1, 0.6, 0.5),) * 3),
        np.asarray(((0.3, 0.3, 0.3),) * 3),
        np.asarray(((1.1, 0, -0.1),) * 3),
        np.ones((3, 3), dtype=bool),
        np.ones((3, 3), dtype=np.float32),
    ),
)
def test_invalid_weights_are_not_silently_sized(weights):
    _, growth = arrays()
    for function in (s.numpy_daily_flat_nav, s.decimal_daily_flat_nav):
        with pytest.raises(ValueError, match="daily_flat_(weights|simplex)"):
            function(weights, growth)


@pytest.mark.parametrize(
    "growth",
    (
        np.ones((3, 3)),
        np.ones((0, 2)),
        np.ones((3, 2), dtype=np.float32),
        np.zeros((3, 2)),
        np.full((3, 2), -1.0),
        np.full((3, 2), np.nan),
        np.full((3, 2), np.inf),
    ),
)
def test_missing_invalid_or_empty_growth_is_not_a_flat_success(growth):
    weights, _ = arrays()
    for function in (s.numpy_daily_flat_nav, s.decimal_daily_flat_nav):
        with pytest.raises(ValueError, match="daily_flat_growth"):
            function(weights, growth)


@pytest.mark.parametrize("growth_value", (1e-300, 1e300))
def test_numpy_and_torch_reject_underflow_or_overflow_nav(torch, growth_value):
    weights = np.asarray(((1, 0, 0),) * 3, dtype=np.float64)
    growth = np.full((3, 2), growth_value, dtype=np.float64)
    with pytest.raises(ValueError, match="daily_flat_nav"):
        s.numpy_daily_flat_nav(weights, growth)
    with pytest.raises(ValueError, match="daily_flat_nav"):
        s.torch_daily_flat_nav(torch, torch.tensor(weights), growth)


def test_torch_autograd_agrees_with_finite_difference_on_logits(torch):
    _, growth = arrays()
    logits = torch.tensor(((0.3, -0.2, 0.1),) * 3, dtype=torch.float64, requires_grad=True)
    nav = s.torch_daily_flat_nav(torch, torch.softmax(logits, dim=1), growth, cost_bps=6)
    torch.log(nav[-1]).backward()
    original, epsilon = logits.detach().numpy(), 1e-6
    for index in np.ndindex(original.shape):
        values = []
        for direction in (-1, 1):
            changed = original.copy()
            changed[index] += direction * epsilon
            exp = np.exp(changed - changed.max(axis=1, keepdims=True))
            weights = exp / exp.sum(axis=1, keepdims=True)
            values.append(np.log(s.numpy_daily_flat_nav(weights, growth, cost_bps=6)[-1]))
        assert logits.grad[index].item() == pytest.approx(
            (values[1] - values[0]) / (2 * epsilon), abs=1e-9
        )


@pytest.mark.parametrize("minutes,holding", ((390, 238), (210, 58)))
def test_fixed_150_minute_cutoff_next_open_and_known_early_close(minutes, holding):
    opening = datetime(2023, 7, 3, 13, 30, tzinfo=UTC)
    session = SessionWindow(opening, opening + timedelta(minutes=minutes))
    entry, exit_ = s.daily_flat_execution_times(
        session, observed_at=opening + timedelta(minutes=150)
    )
    assert entry == opening + timedelta(minutes=151)
    assert exit_ == session.close_ts - timedelta(minutes=1)
    assert (exit_ - entry) == timedelta(minutes=holding)


@pytest.mark.parametrize("offset", (-1, 150.5, 388, 389, 390))
def test_invalid_geometry_has_no_synthetic_holding_interval(offset):
    opening = datetime(2023, 7, 3, 13, 30, tzinfo=UTC)
    session = SessionWindow(opening, opening + timedelta(minutes=390))
    with pytest.raises(ValueError, match="daily_flat_(session_geometry|holding_interval)"):
        s.daily_flat_execution_times(session, observed_at=opening + timedelta(minutes=offset))


def test_naive_cutoff_and_non_minute_or_multi_day_session_are_rejected():
    opening = datetime(2023, 7, 3, 13, 30, tzinfo=UTC)
    session = SessionWindow(opening, opening + timedelta(minutes=390))
    with pytest.raises(ValueError, match="timezone-aware"):
        s.daily_flat_execution_times(session, observed_at=opening.replace(tzinfo=None))
    for invalid in (
        SessionWindow(opening, session.close_ts + timedelta(seconds=1)),
        SessionWindow(opening + timedelta(seconds=1), session.close_ts + timedelta(seconds=1)),
        SessionWindow(opening, opening + timedelta(days=1)),
    ):
        with pytest.raises(ValueError, match="daily_flat_session_geometry"):
            s.daily_flat_execution_times(
                invalid, observed_at=invalid.open_ts + timedelta(minutes=150)
            )


@pytest.mark.parametrize("window", (30, 120))
def test_causal_context_can_be_sealed_without_outcomes_or_whole_session_mask(window):
    opening = datetime(2023, 6, 5, 13, 30, tzinfo=UTC)
    session = SessionWindow(opening, opening + timedelta(minutes=390))
    cutoff = opening + timedelta(minutes=150)

    def source(symbol):
        return tuple(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.M1,
                start_ts=opening + timedelta(minutes=i),
                open=Decimal(100),
                high=Decimal(101),
                low=Decimal(99),
                close=Decimal(100),
                volume=Decimal(10),
            )
            for i in range(390)
            if i != 300
        )

    qqq, spy = source("QQQ"), source("SPY")
    arguments = dict(
        own_symbol="QQQ",
        peer_symbol="SPY",
        session=session,
        observed_at=cutoff,
        timeframe=Timeframe.M1,
        context_bars=window,
    )
    first = build_paired_completed_context(qqq, spy, **arguments)
    changed = tuple(
        replace(bar, open=Decimal(200), high=Decimal(201), low=Decimal(199), close=Decimal(200))
        if bar.start_ts >= cutoff
        else bar
        for bar in qqq
    )
    assert first == build_paired_completed_context(changed, spy, **arguments)
    prefix = tuple(bar for bar in qqq if bar.start_ts < cutoff)
    peer_prefix = tuple(bar for bar in spy if bar.start_ts < cutoff)
    assert first == build_paired_completed_context(prefix, peer_prefix, **arguments)
    entry, exit_ = s.daily_flat_execution_times(session, observed_at=first.observed_at)
    assert first.completed_through == cutoff < entry < exit_

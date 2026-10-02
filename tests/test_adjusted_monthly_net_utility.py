"""Synthetic calendar/feature separation, Decimal NAV oracle and optional Torch."""

import socket
import time
from dataclasses import replace
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal, localcontext
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.data.tiingo_adjusted_etf_daily import AdjustedEtfRow
from thericher_v2.research import adjusted_monthly_net_utility as s
from thericher_v2.research import tiingo_monthly_holding_development as oracle
from thericher_v2.research.adjusted_monthly_policy_inputs import (
    build_adjusted_monthly_policy_inputs,
)


@pytest.fixture(autouse=True)
def no_network_or_actual_data(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("synthetic only")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(oracle, "load_adjusted", forbidden)


@pytest.fixture
def sample():
    dates, rows = [], []
    day, previous = date(2000, 11, 1), Decimal(100)
    while day <= date(2002, 4, 1):
        if day.weekday() < 5:
            i = len(dates)
            opening = previous * (1 + Decimal(i % 5 - 2) / 1000)
            closing = opening * (1 + Decimal(i % 9 - 4) / 100)
            dates.append(day)
            rows.append(
                AdjustedEtfRow(
                    "SPY",
                    day,
                    opening,
                    max(opening, closing) * Decimal("1.01"),
                    min(opening, closing) * Decimal(".99"),
                    closing,
                )
            )
            previous = closing
        day += timedelta(days=1)
    dates, rows = tuple(dates), tuple(rows)
    bounds = []
    for month in (1, 2, 3):
        indices = [i for i, d in enumerate(dates) if (d.year, d.month) == (2002, month)]
        bounds.append((indices[0], indices[-1] + 1))
    records = tuple(
        build_adjusted_monthly_policy_inputs(
            rows,
            symbol="SPY",
            calendar=dates,
            month_bounds=b,
        )
        for b in bounds
    )
    return SimpleNamespace(
        dates=dates,
        rows=rows,
        bounds=bounds,
        records=records,
        data=s.prepare_monthly_utility_arrays(records),
    )


@pytest.fixture
def torch():
    module = pytest.importorskip("torch")
    previous = module.get_num_threads()
    with module.random.fork_rng(devices=[]):
        module.set_num_threads(1)
        try:
            yield module
        finally:
            module.set_num_threads(previous)


def exact_nav(sample, weights, cost):
    actions = {b[0]: Decimal(str(w)) for b, w in zip(sample.bounds, weights, strict=True)}
    result = oracle.replay(
        {r.session_date.isoformat(): r for r in sample.rows},
        [d.isoformat() for d in sample.dates],
        (sample.bounds[0][0], sample.bounds[-1][1]),
        actions,
        str(cost),
        deadline=time.monotonic() + 30,
    )
    return np.asarray([float(v) for v in result["navs"]])


@pytest.mark.parametrize(
    "weights", [(0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5), (0.1, 0.8, 0.2), (0.8, 0, 1)]
)
@pytest.mark.parametrize("cost", [0, 2.5, 10, 100])
def test_numpy_matches_independent_decimal_ledger_every_daily_mark(sample, weights, cost):
    nav = s.numpy_monthly_nav(weights, sample.data, cost_bps=cost)
    assert np.allclose(nav, exact_nav(sample, weights, cost), rtol=2e-13, atol=2e-13)
    assert len(nav) == sum(len(r.payoff.target_dates) for r in sample.records)


def test_first_gap_not_earned_and_final_fee_on_last_actual_session(sample):
    gaps = sample.data.open_gaps.copy()
    gaps[0] = 100
    changed = replace(sample.data, open_gaps=gaps)
    a = s.numpy_monthly_nav((1, 1, 1), sample.data, cost_bps=10)
    assert np.array_equal(a, s.numpy_monthly_nav((1, 1, 1), changed, cost_bps=10))
    growth = float(
        sample.rows[sample.bounds[-1][1] - 1].adj_close / sample.rows[sample.bounds[0][0]].adj_open
    )
    assert a[-1] == pytest.approx(growth * 0.999 / 1.001, rel=2e-13)


def test_interior_gap_earned_by_owned_stock_not_cash(sample):
    changed = sample.data.open_gaps.copy()
    changed[1] *= 1.2
    changed = replace(sample.data, open_gaps=changed)
    a = s.numpy_monthly_nav((1, 1, 1), sample.data, cost_bps=0)
    b = s.numpy_monthly_nav((1, 1, 1), changed, cost_bps=0)
    n = len(sample.records[0].payoff.target_dates)
    assert np.array_equal(a[:n], b[:n])
    assert np.allclose(b[n:], a[n:] * 1.2)
    assert np.array_equal(
        s.numpy_monthly_nav((0, 0, 0), sample.data), s.numpy_monthly_nav((0, 0, 0), changed)
    )


def test_padded_marks_are_not_observations_or_final_growth(sample):
    growth = sample.data.close_growth.copy()
    growth[~sample.data.valid_days] = 99
    changed = replace(sample.data, close_growth=growth)
    assert np.array_equal(
        s.numpy_monthly_nav((0.5, 0.7, 0.9), sample.data),
        s.numpy_monthly_nav((0.5, 0.7, 0.9), changed),
    )


def test_features_fixed_scale_clip_readonly_and_exclude_payoffs(sample):
    assert sample.data.features.shape == (3, 252, 1)
    assert sample.data.features.dtype == np.float32
    assert np.allclose(
        sample.data.features[0, :, 0],
        [float(x / 100) for x in sample.records[0].model.close_returns_bps],
    )
    for array in (
        sample.data.features,
        sample.data.open_gaps,
        sample.data.close_growth,
        sample.data.valid_days,
    ):
        assert not array.flags.writeable
    assert "array(" not in repr(sample.data)
    assert all(
        a < b for a, b in zip(sample.data.source_dates, sample.data.decision_dates, strict=True)
    )
    record = sample.records[-1]
    changed = replace(
        record,
        payoff=replace(
            record.payoff,
            open_over_previous_close=record.payoff.open_over_previous_close * 2,
            close_over_entry_open=tuple(v * 3 for v in record.payoff.close_over_entry_open),
        ),
    )
    data = s.prepare_monthly_utility_arrays(sample.records[:-1] + (changed,))
    assert np.array_equal(data.features, sample.data.features)
    assert not np.array_equal(data.close_growth, sample.data.close_growth)


@pytest.mark.parametrize("precision", [2, 6, 28, 70])
def test_immutable_feature_scaling_ignores_ambient_decimal_context(sample, precision):
    with localcontext() as context:
        context.prec, context.rounding = precision, ROUND_DOWN
        data = s.prepare_monthly_utility_arrays(sample.records)
    for field in ("features", "open_gaps", "close_growth", "valid_days"):
        assert np.array_equal(getattr(data, field), getattr(sample.data, field))


@pytest.mark.parametrize(
    "case", ["empty", "list", "reverse", "duplicate", "gap", "mixed", "binding"]
)
def test_bad_month_cohorts_are_rejected(sample, case):
    records = sample.records
    if case == "empty":
        records = ()
    elif case == "list":
        records = list(records)
    elif case == "reverse":
        records = records[::-1]
    elif case == "duplicate":
        records = records[:1] * 2
    elif case == "gap":
        records = records[::2]
    elif case == "mixed":
        other = replace(records[-1], identity=replace(records[-1].identity, symbol="QQQ"))
        records = records[:-1] + (other,)
    else:
        other = replace(
            records[-1],
            identity=replace(
                records[-1].identity,
                month_bounds=tuple(i + 1 for i in records[-1].identity.month_bounds),
            ),
        )
        records = records[:-1] + (other,)
    with pytest.raises(ValueError):
        s.prepare_monthly_utility_arrays(records)


@pytest.mark.parametrize(
    "weights",
    [(1, 0), (1, 0, 2), (1, -0.01, 0), (1, float("nan"), 0), (1, float("inf"), 0), [[1], [0], [1]]],
)
def test_invalid_weights_rejected(sample, weights):
    with pytest.raises(ValueError):
        s.numpy_monthly_nav(weights, sample.data)


@pytest.mark.parametrize("cost", [True, -1, 10000, float("nan"), float("inf"), "10"])
def test_invalid_cost_rejected(sample, cost):
    with pytest.raises(ValueError):
        s.numpy_monthly_nav((0.5, 0.5, 0.5), sample.data, cost_bps=cost)


@pytest.mark.parametrize("nav", [[], [0], [-1], [float("nan")], [float("inf")], [[1]]])
def test_invalid_utility_nav_rejected(nav):
    with pytest.raises(ValueError):
        s.numpy_net_utility(nav)


def test_objective_cash_initial_fee_and_population_variance():
    assert s.numpy_net_utility(np.ones(6)) == 0
    nav = np.asarray([0.99, 1.1, 0.95])
    logs = np.log(nav / np.asarray([1, 0.99, 1.1]))
    assert s.numpy_net_utility(nav) == pytest.approx(252 * (logs.mean() - logs.var(ddof=0)))


@pytest.mark.parametrize("architecture", ["linear", "lstm"])
def test_optional_torch_model_is_finite_and_context_bounded(sample, architecture, torch):
    torch.manual_seed(101)
    model = s.build_torch_monthly_policy(torch, architecture)
    x = torch.tensor(sample.data.features.copy())
    weights = model(x)
    assert weights.shape == (3,) and bool(((weights > 0) & (weights < 1)).all())
    changed = x.clone()
    changed[-1] *= 2
    assert torch.equal(weights[:2], model(changed)[:2])
    with pytest.raises(ValueError, match="monthly_feature_shape"):
        model(x[:, :-1])
    assert not any(isinstance(m, torch.nn.Dropout) for m in model.modules())


def test_optional_torch_nav_and_gradient_match_numpy_and_finite_difference(sample, torch):
    values = np.asarray([0.1, 0.8, 0.2])
    weights = torch.tensor(values, dtype=torch.float64, requires_grad=True)
    nav = s.torch_monthly_nav(torch, weights, sample.data, cost_bps=10)
    assert np.allclose(nav.detach().numpy(), exact_nav(sample, values, 10), rtol=2e-13, atol=2e-13)
    score = s.torch_net_utility(torch, nav)
    assert float(score.detach()) == pytest.approx(
        s.numpy_net_utility(nav.detach().numpy()), rel=1e-12
    )
    score.backward()
    grad = weights.grad.detach().numpy()
    for i in range(3):
        a, b = values.copy(), values.copy()
        a[i] += 1e-6
        b[i] -= 1e-6
        expected = (
            s.numpy_net_utility(s.numpy_monthly_nav(a, sample.data))
            - s.numpy_net_utility(s.numpy_monthly_nav(b, sample.data))
        ) / 2e-6
        assert grad[i] == pytest.approx(expected, rel=1e-5, abs=1e-7)


@pytest.mark.parametrize("architecture", ["linear", "lstm"])
def test_optional_cpu_optimizer_updates_and_numeric_state_reconstructs(sample, architecture, torch):
    torch.manual_seed(101)
    model = s.build_torch_monthly_policy(torch, architecture)
    x = torch.tensor(sample.data.features.copy())
    before = {k: v.detach().numpy().copy() for k, v in model.state_dict().items()}
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003, weight_decay=0.001)
    optimizer.zero_grad()
    loss = -s.torch_net_utility(torch, s.torch_monthly_nav(torch, model(x), sample.data))
    loss.backward()
    assert all(
        p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in model.parameters()
    )
    optimizer.step()
    after = {k: v.detach().numpy().copy() for k, v in model.state_dict().items()}
    assert any(not np.array_equal(before[k], after[k]) for k in before)
    restored = s.build_torch_monthly_policy(torch, architecture)
    restored.load_state_dict({k: torch.tensor(v) for k, v in after.items()}, strict=True)
    with torch.no_grad():
        assert torch.equal(model(x), restored(x))

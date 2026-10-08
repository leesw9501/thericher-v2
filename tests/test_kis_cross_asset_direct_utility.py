from __future__ import annotations

import builtins
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, localcontext

import numpy as np
import pytest

from thericher_v2.research import kis_cross_asset_direct_utility as study
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_daily_risk_input import RawD1Price
from thericher_v2.research.cross_asset_etf_input import (
    CrossAssetInputUnavailable,
    CrossAssetSession,
)

D = Decimal
VINTAGE = "synthetic-direct-only-hidden-vintage"


def session(day):
    return CrossAssetSession(
        day, datetime.combine(day, time(14, 30), UTC), datetime.combine(day, time(21), UTC)
    )


def source_fixture():
    schedule = tuple(session(date(2024, 1, 1) + timedelta(days=i)) for i in range(64))
    rows = {s: [] for s in study.SYMBOLS}
    with localcontext(study.CONTEXT):
        for asset, symbol in enumerate(study.SYMBOLS):
            price = D(100 + asset * 40)
            for i, s in enumerate(schedule):
                change = D(((i * (asset + 1)) % 9) - 4) / 1000
                price *= 1 + change
                rows[symbol].append(
                    RawD1Price(
                        symbol,
                        s.session_date,
                        VINTAGE,
                        open=None if i == 0 else price / D("1.002"),
                        close=price,
                    )
                )
    return schedule, {s: tuple(v) for s, v in rows.items()}


def context(rows=None, schedule=None, **kwargs):
    original, source = source_fixture()
    schedule = original if schedule is None else schedule
    return study.prepare_context(
        source if rows is None else rows,
        scheduled_history=schedule,
        entry_session=session(schedule[-1].session_date + timedelta(days=1)),
        decision_at=kwargs.get("decision_at", schedule[-1].close_at),
        vintage_ref=kwargs.get("vintage_ref", VINTAGE),
    )


@pytest.fixture
def torch():
    return pytest.importorskip("torch")


def target(weights):
    risky = tuple(D(str(x)) for x in weights[:3])
    with localcontext(study.CONTEXT) as ctx:
        ctx.prec = 100
        cash = 1 - sum(risky, D(0))
    return nav.ThreeAssetTarget(risky, cash)


def group_fixture(count=3):
    groups = []
    for g in range(count):
        opened = tuple(D(100 + 37 * asset) * (1 + D(g) / 5) for asset in range(3))
        days = []
        for j in range(21):
            closed = tuple(
                v * (1 + D((asset + 1) * (j + 1) - 12 * g) / 1000) for asset, v in enumerate(opened)
            )
            intermediate = opened if j == 0 else tuple(v * D("1.017") for v in closed)
            days.append(
                nav.ThreeAssetDay(
                    date(2024, 1, 1) + timedelta(days=g * 21 + j), intermediate, closed
                )
            )
        groups.append(tuple(days))
    return tuple(groups)


def tensors(torch, groups, weights=None):
    weights = ((0.2, 0.3, 0.1, 0.4),) * len(groups) if weights is None else weights
    return (
        torch.tensor([[float(v) for v in g[0].adj_open3] for g in groups], dtype=torch.float64),
        torch.tensor(
            [[[float(v) for v in d.adj_close3] for d in g] for g in groups], dtype=torch.float64
        ),
        torch.tensor(weights, dtype=torch.float64),
    )


def test_fixed_metadata_no_runtime_or_permission_platform():
    cfg = study.configuration()
    assert cfg["cells"] == len(study.POLICIES) * 3 * 2 == 42
    assert cfg["gru"]["hidden_size"] == 16 and cfg["fits"] == 2
    assert cfg["context"] == [6, 63] and cfg["family_seconds"] == 300
    assert cfg["actual_fits"] == 0 and cfg["source_io"] is cfg["paper_input"] is False
    assert "joint-d1-direct-utility-development-v1" in cfg["lineage"]


def test_exact_population_63_not_252_or_sample_covariance():
    schedule, rows = source_fixture()
    actual = context(rows, schedule)
    with localcontext(study.CONTEXT):
        returns = np.array(
            [
                [(b.close - a.close) / a.close for a, b in zip(rows[s], rows[s][1:], strict=False)]
                for s in study.SYMBOLS
            ],
            dtype=np.float64,
        ).T
    np.testing.assert_allclose(actual.covariance, np.cov(returns.T, ddof=0), atol=1e-20)
    assert actual.features.observation_dates == tuple(s.session_date for s in schedule[1:])
    assert actual.safe_facts()["covariance_returns"] == 63
    assert VINTAGE not in repr(actual) and "Decimal" not in repr(actual)
    with pytest.raises(FrozenInstanceError):
        actual.covariance = ()


@pytest.mark.parametrize("kind", ["absent", "extreme", "duplicate", "bad_support"])
def test_all_current_future_support_ignored(kind):
    schedule, rows = source_fixture()
    modified = dict(rows)
    for s in study.SYMBOLS:
        if kind == "absent":
            continue
        future = RawD1Price(
            s,
            schedule[-1].session_date + timedelta(days=1),
            VINTAGE,
            open=D("1e30"),
            close=D("1e-20"),
        )
        extra = (future, future) if kind == "duplicate" else (future,)
        if kind == "bad_support":

            class Future:
                session_date = schedule[-1].session_date + timedelta(days=2)

                @property
                def close(self):
                    raise AssertionError("future_value_read")

            extra += (Future(),)
        modified[s] += extra
    assert context(modified, schedule) == context(rows, schedule)


@pytest.mark.parametrize("symbol", study.SYMBOLS)
def test_missing_past_local_unavailable_not_old_fallback(symbol):
    schedule, rows = source_fixture()
    rows[symbol] = rows[symbol][:20] + rows[symbol][21:]
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        context(rows, schedule)


def test_cutoff_vintage_and_degenerate_covariance():
    schedule, rows = source_fixture()
    with pytest.raises(CrossAssetInputUnavailable):
        context(rows, schedule, decision_at=schedule[-1].open_at)
    with pytest.raises(CrossAssetInputUnavailable, match="vintage"):
        context(rows, schedule, vintage_ref="other")
    flat = {s: tuple(replace(r, open=D(100), close=D(100)) for r in rows[s]) for s in study.SYMBOLS}
    with pytest.raises(study.DirectUtilityError, match="covariance_values"):
        context(flat, schedule)


def test_no_io_or_credentials_in_adapter_and_control_allocations(monkeypatch):
    schedule, rows = source_fixture()

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden_io")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    prepared = context(rows, schedule)
    targets = study.fixed_controls(prepared)
    assert set(targets) == {"erc", "minvar", "inverse_volatility", "equal_thirds", "cash"}
    assert targets["cash"].cash_weight == 1
    c = np.asarray(prepared.covariance)
    shrunk = 0.75 * c + 0.25 * np.diag(np.diag(c))
    for t in targets.values():
        w = np.array(t.weights3, dtype=np.float64)
        assert np.sqrt(252 * w @ shrunk @ w) <= 0.10 + 1e-12


@pytest.mark.parametrize("cost", [0, 2.5, 5, 10])
@pytest.mark.parametrize("tail", [0, 14])
def test_decimal_complete_path_fees_cash_utility_and_capital_parity(torch, cost, tail):
    groups = group_fixture()
    inputs = tensors(torch, groups)
    result = study.replay_closed_groups(*inputs, cost, tail_days=tail)
    last = groups[-1][-1]
    tail_marks = tuple(replace(last, date=last.date + timedelta(days=i + 1)) for i in range(tail))
    expected = study.decimal_reference(
        groups, (target((0.2, 0.3, 0.1, 0.4)),) * 3, cost_bps=D(str(cost)), tail=tail_marks
    )
    for key in ("nav", "fees", "traded_notional", "cash", "log_returns"):
        values = [
            float(getattr(d, "log_return" if key == "log_returns" else key)) for d in expected.daily
        ]
        np.testing.assert_allclose(
            getattr(result, key).numpy(), values, rtol=study.PARITY_TOLERANCE, atol=1e-12
        )
    with localcontext(study.CONTEXT):
        logs = tuple(d.log_return for d in expected.daily)
        mean = sum(logs) / len(logs)
        utility = 252 * (mean - 5 * sum((v - mean) ** 2 for v in logs) / len(logs))
    assert float(study.net_utility(result)) == pytest.approx(float(utility), abs=1e-11)
    assert "tensor" not in repr(result)
    assert expected.final_state.quantities == (D(0),) * 3


def test_unchanged_daily_target_is_not_a_rebalance(torch):
    groups = group_fixture(1)
    inputs = tensors(torch, groups, ((1.0, 0.0, 0.0, 0.0),))
    result = study.replay_closed_groups(*inputs, 10)
    assert (result.traded_notional[1:20] == 0).all()
    reference = study.decimal_reference(groups, (target((1, 0, 0, 0)),), cost_bps=D(10))
    mutated = tuple(
        replace(d, adj_open3=tuple(v * 99 for v in d.adj_open3)) if i else d
        for i, d in enumerate(groups[0])
    )
    other = study.decimal_reference((mutated,), (target((1, 0, 0, 0)),), cost_bps=D(10))
    assert reference == other


def test_global_initial_capital_and_cross_group_denominator(torch):
    groups = group_fixture(2)
    opened, closed, weights = tensors(torch, groups)
    actual = study.replay_closed_groups(opened, closed, weights, 10)
    scaled = study.replay_closed_groups(opened, closed, weights, 10, initial_nav=17.0)
    torch.testing.assert_close(scaled.nav, 17 * actual.nav)
    torch.testing.assert_close(scaled.entry_quantities, 17 * actual.entry_quantities)
    torch.testing.assert_close(scaled.log_returns, actual.log_returns)
    alone = study.replay_closed_groups(opened[1:], closed[1:], weights[1:], 10)
    torch.testing.assert_close(actual.nav[21:], actual.nav[20] * alone.nav)
    assert actual.log_returns[21] == pytest.approx(float(alone.log_returns[0]))
    assert not torch.equal(actual.nav[21:], alone.nav)


def test_constant_price_exact_actual_roundtrip_not_weight_distance(torch):
    opened = torch.tensor([[100.0, 100.0, 100.0]], dtype=torch.float64)
    closed = opened[:, None, :].expand(-1, 21, -1)
    weights = torch.tensor([[0.2, 0.3, 0.1, 0.4]], dtype=torch.float64)
    result = study.replay_closed_groups(opened, closed, weights, 10)
    a, c = 0.6, 0.001
    assert float(result.nav[-1]) == pytest.approx((1 - c * a) / (1 + c * a))
    assert float(result.fees.sum()) == pytest.approx(2 * c * a / (1 + c * a))


def test_risk_cap_single_shrink_and_gradient(torch):
    c = torch.tensor(
        [[[0.0004, 0.00005, -0.00002], [0.00005, 0.0002, 0.00001], [-0.00002, 0.00001, 0.0001]]],
        dtype=torch.float64,
    )
    logits = torch.tensor([[0.2, -0.3, 0.1, 0.8]], dtype=torch.float64, requires_grad=True)
    weights = study.risk_capped_weights(logits, c)
    mix = logits[:, :3].softmax(-1)
    shrunk = 0.75 * c + 0.25 * torch.diag_embed(c.diagonal(dim1=-2, dim2=-1))
    vol = torch.sqrt(252 * torch.einsum("bi,bij,bj->b", mix, shrunk, mix))
    expected = (
        mix * (logits[:, 3].sigmoid() * torch.minimum(torch.ones_like(vol), 0.10 / vol))[:, None]
    )
    torch.testing.assert_close(weights[:, :3], expected)
    assert bool((weights >= 0).all()) and bool((weights.sum(-1) - 1).abs().max() < 1e-14)
    attained = torch.sqrt(
        252 * torch.einsum("bi,bij,bj->b", weights[:, :3], shrunk, weights[:, :3])
    )
    assert float(attained.detach().max()) <= 0.10
    assert torch.autograd.gradcheck(lambda x: study.risk_capped_weights(x, c), (logits,))


def test_global_utility_backward_matches_finite_difference_no_detach(torch):
    groups = group_fixture(2)
    opened, closed, _ = tensors(torch, groups)
    c = torch.eye(3, dtype=torch.float64)[None].expand(2, -1, -1) * 0.0002
    logits = torch.tensor(
        [[0.2, -0.3, 0.1, 0.8], [-0.1, 0.1, 0.5, -0.4]], dtype=torch.float64, requires_grad=True
    )

    def objective(x):
        weights = study.risk_capped_weights(x, c)
        return study.net_utility(study.replay_closed_groups(opened, closed, weights, 10))

    assert torch.autograd.gradcheck(objective, (logits,), eps=1e-6, atol=1e-6)
    grad = torch.autograd.grad(objective(logits), logits)[0]
    assert bool(torch.isfinite(grad).all()) and bool((grad.abs().sum(-1) > 0).all())


def test_payoff_mutations_cannot_change_weights_or_prior_group(torch):
    opened, closed, _ = tensors(torch, group_fixture(2))
    c = torch.eye(3, dtype=torch.float64)[None].expand(2, -1, -1) * 0.0001
    logits = torch.zeros((2, 4), dtype=torch.float64)
    before = study.risk_capped_weights(logits, c)
    actual = study.replay_closed_groups(opened, closed, before, 10)
    changed = closed.clone()
    changed[1] *= 17
    again = study.replay_closed_groups(opened, changed, before, 10)
    assert torch.equal(before, study.risk_capped_weights(logits, c))
    assert torch.equal(actual.nav[:21], again.nav[:21])
    changed[1, 3, 0] = float("nan")
    with pytest.raises(study.DirectUtilityError, match="close_values"):
        study.replay_closed_groups(opened, changed, before, 10)


@pytest.mark.parametrize("scale", [1e-6, 1e6])
def test_per_asset_price_scale_invariance(torch, scale):
    opened, closed, weights = tensors(torch, group_fixture(2))
    original = study.replay_closed_groups(opened, closed, weights, 10)
    units = torch.tensor([scale, 3.0, 1 / scale], dtype=torch.float64)
    scaled = study.replay_closed_groups(opened * units, closed * units, weights, 10)
    torch.testing.assert_close(scaled.nav, original.nav)
    torch.testing.assert_close(scaled.fees, original.fees)


def test_near_break_even_and_hostile_decimal_context(torch):
    groups = group_fixture(1)
    factor = D("1.001") / D("0.999")
    days = tuple(
        replace(d, adj_close3=tuple(v * factor for v in groups[0][0].adj_open3)) for d in groups[0]
    )
    opened, closed, weights = tensors(torch, (days,), ((1.0, 0.0, 0.0, 0.0),))
    with localcontext() as ctx:
        ctx.prec = 6
        expected = study.decimal_reference((days,), (target((1, 0, 0, 0)),), cost_bps=D(10))
    actual = study.replay_closed_groups(opened, closed, weights, 10)
    assert float(actual.nav[-1]) == pytest.approx(float(expected.final_nav), abs=1e-12)


@pytest.mark.parametrize("fault", ["weight_sum", "negative", "float32", "shape", "cost", "tail"])
def test_invalid_numeric_domain_never_repaired(torch, fault):
    opened, closed, weights = tensors(torch, group_fixture(1))
    kwargs, cost = {}, 10
    if fault == "weight_sum":
        weights[0, 0] = 2
    elif fault == "negative":
        weights[0, 0] = -0.1
    elif fault == "float32":
        opened = opened.float()
    elif fault == "shape":
        closed = closed[:, :-1]
    elif fault == "cost":
        cost = float("nan")
    else:
        kwargs["tail_days"] = 21
    with pytest.raises(study.DirectUtilityError):
        study.replay_closed_groups(opened, closed, weights, cost, **kwargs)


def test_cash_path_and_tail_never_trade(torch):
    opened, closed, _ = tensors(torch, group_fixture(2))
    weights = torch.tensor([[0.0, 0.0, 0.0, 1.0]] * 2, dtype=torch.float64)
    result = study.replay_closed_groups(opened, closed, weights, 10, tail_days=14)
    assert result.nav.shape == (56,) and (result.nav == 1).all()
    assert (result.log_returns == 0).all() and (result.fees == 0).all()
    assert float(study.net_utility(result)) == 0

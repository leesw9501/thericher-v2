from __future__ import annotations

import builtins
import importlib.util
import os
import random
import socket
import sys
import urllib.request
from dataclasses import FrozenInstanceError, fields
from datetime import date, timedelta
from decimal import Decimal
from itertools import permutations, product
from pathlib import Path

import pytest

from thericher_v2.research import differentiable_three_asset_nav as nav
from thericher_v2.research import three_asset_nav as decimal_nav

PARITY_TOLERANCE = 1e-10
OUTPUTS = ("nav", "log_returns", "fees", "traded_notional", "cash")


@pytest.fixture
def torch(monkeypatch):
    torch = pytest.importorskip("torch")

    def prohibited(*args, **kwargs):
        raise AssertionError("GPU access is outside this CPU test package")

    for name in ("is_available", "device_count", "current_device", "init", "synchronize"):
        monkeypatch.setattr(torch.cuda, name, prohibited)
    return torch


@pytest.fixture
def sample(torch):
    opens = torch.tensor([[2, 4, 5], [5, 3, 9], [4, 7, 6]], dtype=torch.float64)
    closes = torch.tensor([[3, 4, 6], [4, 2, 8], [6, 8, 3]], dtype=torch.float64)
    weights = torch.tensor(
        [[0.2, 0.3, 0.4, 0.1], [0.6, 0.1, 0.2, 0.1], [0.1, 0.4, 0.2, 0.3]],
        dtype=torch.float64,
    )
    return opens, closes, weights


def decimal_replay(opens, closes, weights, cost):
    days, targets = [], {}
    for index, (opening, closing, target) in enumerate(zip(opens, closes, weights, strict=True)):
        key = date(2000, 1, 1) + timedelta(days=index)
        days.append(
            decimal_nav.ThreeAssetDay(
                key, tuple(map(Decimal, map(str, opening))), tuple(map(Decimal, map(str, closing)))
            )
        )
        values = tuple(map(Decimal, map(str, target)))
        targets[key] = decimal_nav.ThreeAssetTarget(values[:3], values[3])
    return decimal_nav.replay(days, targets, Decimal(str(cost)))


def assert_decimal_parity(torch, opens, closes, weights, cost):
    expected = decimal_replay(opens, closes, weights, cost)
    actual = nav.replay_torch(
        torch.tensor(opens, dtype=torch.float64),
        torch.tensor(closes, dtype=torch.float64),
        torch.tensor(weights, dtype=torch.float64),
        cost,
    )
    for name in OUTPUTS:
        decimal_name = "log_return" if name == "log_returns" else name
        reference = torch.tensor(
            [float(getattr(day, decimal_name)) for day in expected.daily], dtype=torch.float64
        )
        torch.testing.assert_close(
            getattr(actual, name), reference, rtol=PARITY_TOLERANCE, atol=1e-14
        )
    assert actual.nav.shape == (len(opens),)
    assert actual.cash[-1] == actual.nav[-1]
    torch.testing.assert_close(actual.fees, actual.traded_notional * cost / 10000)
    torch.testing.assert_close(actual.log_returns.sum(), actual.nav[-1].log())
    return actual


@pytest.mark.parametrize("cost", (0, 2.5, 5, 10, 100))
@pytest.mark.parametrize(
    "weights",
    (
        [[0.2, 0.3, 0.4, 0.1]],
        [[0.8, 0.1, 0.1, 0], [0, 0, 0, 1]],
        [[0.8, 0.1, 0.1, 0], [0.1, 0.4, 0.5, 0]],
        [[0.2, 0.3, 0.4, 0.1], [0.6, 0.1, 0.2, 0.1], [0.1, 0.4, 0.2, 0.3]],
    ),
    ids=("all-buy-final-exit", "all-sell", "shared-cash-mixed", "overnight-drift"),
)
def test_decimal_actual_cashflow_parity(torch, cost, weights):
    opens = [[2, 4, 5], [5, 3, 9], [4, 7, 6]][: len(weights)]
    closes = [[3, 4, 6], [4, 2, 8], [6, 8, 3]][: len(weights)]
    assert_decimal_parity(torch, opens, closes, weights, cost)


@pytest.mark.parametrize("cost", (0, 2.5, 5, 10, 100))
def test_single_day_scalar_entry_and_final_exit_in_one_log_return(torch, cost):
    prices = torch.ones((1, 3), dtype=torch.float64)
    weights = torch.tensor([[1, 0, 0, 0]], dtype=torch.float64)
    result = nav.replay_torch(prices, prices, weights, cost)
    fee = cost / 10000
    post_open = 1 / (1 + fee)
    expected = (1 - fee) * post_open
    torch.testing.assert_close(result.nav, prices.new_tensor([expected]))
    torch.testing.assert_close(result.traded_notional, prices.new_tensor([2 * post_open]))
    torch.testing.assert_close(result.fees, prices.new_tensor([2 * fee * post_open]))
    torch.testing.assert_close(result.log_returns, prices.new_tensor([expected]).log())


@pytest.mark.parametrize("cost", (0, 2.5, 5, 10, 100))
def test_all_cash_has_no_artificial_trade_or_exit(torch, sample, cost):
    opens, closes, weights = sample
    weights = weights.new_tensor([[0, 0, 0, 1]]).expand(3, 4)
    result = nav.replay_torch(opens, closes, weights, cost)
    for name in OUTPUTS:
        target = torch.ones(3) if name in {"nav", "cash"} else torch.zeros(3)
        torch.testing.assert_close(getattr(result, name), target.to(dtype=torch.float64))


def test_unchanged_target_trades_drift_and_never_resets_capital(torch):
    opens = [[2, 4, 5], [5, 3, 9], [4, 7, 6]]
    closes = [[3, 4, 6], [4, 2, 8], [6, 8, 3]]
    weights = [[0.2, 0.3, 0.4, 0.1]] * 3
    result = assert_decimal_parity(torch, opens, closes, weights, 5)
    assert result.traded_notional[1] > 0
    independent = nav.replay_torch(
        torch.tensor(opens[1:], dtype=torch.float64),
        torch.tensor(closes[1:], dtype=torch.float64),
        torch.tensor(weights[1:], dtype=torch.float64),
        5,
    )
    assert result.nav[-1] != independent.nav[-1]


@pytest.mark.parametrize("cost", (0, 2.5, 5, 10, 100))
def test_long_synthetic_path_decimal_parity(torch, cost):
    generator = random.Random(101)
    opens, closes, weights = [], [], []
    for _ in range(256):
        opening = [generator.randrange(50, 151) for _ in range(3)]
        closing = [value + generator.randrange(-5, 6) for value in opening]
        cuts = sorted((0, 1000, *(generator.randrange(1001) for _ in range(3))))
        target = [(upper - lower) / 1000 for lower, upper in zip(cuts, cuts[1:], strict=False)]
        opens.append(opening)
        closes.append(closing)
        weights.append(target)
    assert_decimal_parity(torch, opens, closes, weights, cost)


@pytest.mark.parametrize("face", tuple(product((-1, 1), repeat=3)))
def test_all_eight_sign_faces_solve_original_equation(torch, face):
    weights = torch.tensor([[0.1, 0.1, 0.1]], dtype=torch.float64, requires_grad=True)
    alpha = weights.new_tensor([[0.2 if sign < 0 else 0.01 for sign in face]])
    alpha.requires_grad_()
    fee = weights.new_tensor(0.01, requires_grad=True)
    fraction, turnover = nav._fraction(torch, weights, alpha, fee)
    signs = weights.new_tensor([face])
    expected = (1 + fee * (signs * alpha).sum()) / (1 + fee * (signs * weights).sum())
    torch.testing.assert_close(fraction[0], expected)
    delta = weights * fraction[:, None] - alpha
    assert (delta * signs > 0).all()
    torch.testing.assert_close(turnover, delta.abs().sum(dim=1))
    torch.testing.assert_close(fraction + fee * turnover, fraction.new_ones(1))
    dw, da, df = torch.autograd.grad(fraction.sum(), (weights, alpha, fee))
    denominator = 1 + fee * (signs * weights).sum()
    torch.testing.assert_close(dw, -fee * signs * fraction / denominator)
    torch.testing.assert_close(da, fee * signs / denominator)
    torch.testing.assert_close(df, -turnover[0] / denominator)


def test_exact_fee_tie_lex_face_one_sided_not_central(torch):
    weights = torch.tensor([[0.2, 0.3, 0.4]], dtype=torch.float64, requires_grad=True)
    alpha = weights.detach().clone()
    fee = weights.new_tensor(0.01)
    fraction, turnover = nav._fraction(torch, weights, alpha, fee)
    assert fraction[0] == 1 and turnover[0] == 0
    gradient = torch.autograd.grad(fraction.sum() + turnover.sum(), weights, retain_graph=True)[0]
    direction = weights.new_tensor([[-0.01, -0.02, -0.03]])
    step = 1e-6
    shifted = nav._fraction(torch, weights.detach() + step * direction, alpha, fee)
    difference = ((shifted[0] + shifted[1]) - (fraction + turnover).detach()) / step
    torch.testing.assert_close((gradient * direction).sum(), difference[0], rtol=1e-6, atol=1e-9)
    assert (torch.autograd.grad(fraction.sum(), weights, retain_graph=True)[0] > 0).all()


def test_tiny_true_trade_not_clipped_or_treated_as_tie(torch):
    prices = torch.ones((1, 3), dtype=torch.float64)
    weights = torch.tensor([[1e-42, 0, 0, 1]], dtype=torch.float64, requires_grad=True)
    result = nav.replay_torch(prices, prices, weights, 10)
    assert result.traded_notional[0] > 0 and result.fees[0] > 0
    torch.testing.assert_close(
        result.traded_notional, prices.new_tensor([2e-42]), rtol=1e-12, atol=0
    )
    gradient = torch.autograd.grad(result.fees.sum(), weights)[0]
    assert gradient[0, 0] > 0 and torch.isfinite(gradient).all()


@pytest.mark.parametrize("order", tuple(permutations(range(3))))
def test_asset_permutation_requires_corresponding_price_and_weight_columns(torch, sample, order):
    opens, closes, weights = sample
    original = nav.replay_torch(opens, closes, weights, 10)
    reordered = nav.replay_torch(opens[:, order], closes[:, order], weights[:, (*order, 3)], 10)
    for name in OUTPUTS:
        torch.testing.assert_close(getattr(original, name), getattr(reordered, name))
    if order != (0, 1, 2):
        mismatched = nav.replay_torch(opens[:, order], closes[:, order], weights, 10)
        assert not torch.allclose(original.nav, mismatched.nav)


def test_price_units_invariant_and_noncontiguous_tensors_supported(torch, sample):
    opens, closes, weights = sample
    original = nav.replay_torch(opens, closes, weights, 5)
    scale = opens.new_tensor([0.5, 2, 10])
    scaled = nav.replay_torch(opens * scale, closes * scale, weights, 5)
    strided = tuple(tensor.T.contiguous().T for tensor in sample)
    assert all(not value.is_contiguous() for value in strided)
    noncontiguous = nav.replay_torch(*strided, 5)
    for name in OUTPUTS:
        torch.testing.assert_close(getattr(original, name), getattr(scaled, name))
        torch.testing.assert_close(getattr(original, name), getattr(noncontiguous, name))


@pytest.mark.parametrize("cost", (-1, 101, float("nan"), float("inf"), True, "5", 10**1000))
def test_invalid_scalar_cost_is_categorical(torch, sample, cost):
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match="^cost_bps_invalid$"):
        nav.replay_torch(*sample, cost)


@pytest.mark.parametrize("kind", ("vector", "float32", "meta", "nan", "negative", "excess"))
def test_invalid_tensor_cost_is_categorical(torch, sample, kind):
    cost = {
        "vector": lambda: torch.tensor([5], dtype=torch.float64),
        "float32": lambda: torch.tensor(5, dtype=torch.float32),
        "meta": lambda: torch.empty((), dtype=torch.float64, device="meta"),
        "nan": lambda: torch.tensor(float("nan"), dtype=torch.float64),
        "negative": lambda: torch.tensor(-1, dtype=torch.float64),
        "excess": lambda: torch.tensor(101, dtype=torch.float64),
    }[kind]()
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match="^cost_bps_invalid$"):
        nav.replay_torch(*sample, cost)


@pytest.mark.parametrize(
    "kind,category",
    (
        ("object", "input_tensor"),
        ("float32", "input_dtype"),
        ("integer", "input_dtype"),
        ("sparse", "input_dtype"),
        ("empty", "input_shape"),
        ("two-assets", "input_shape"),
        ("four-assets", "input_shape"),
        ("unaligned-close", "input_shape"),
        ("missing-cash", "input_shape"),
        ("extra-weight", "input_shape"),
        ("flat-price", "input_shape"),
        ("meta", "input_device"),
    ),
)
def test_input_shape_dtype_and_device_not_repaired(torch, sample, kind, category):
    opens, closes, weights = sample
    changes = {
        "object": lambda: (opens.tolist(), closes, weights),
        "float32": lambda: (opens.float(), closes, weights),
        "integer": lambda: (opens.long(), closes, weights),
        "sparse": lambda: (opens.to_sparse(), closes, weights),
        "empty": lambda: (opens[:0], closes[:0], weights[:0]),
        "two-assets": lambda: (opens[:, :2], closes[:, :2], weights),
        "four-assets": lambda: (weights, weights, weights),
        "unaligned-close": lambda: (opens, closes[:2], weights),
        "missing-cash": lambda: (opens, closes, weights[:, :3]),
        "extra-weight": lambda: (opens, closes, torch.cat((weights, weights[:, :1]), dim=1)),
        "flat-price": lambda: (opens[0], closes[0], weights),
        "meta": lambda: (opens.to("meta"), closes.to("meta"), weights.to("meta")),
    }
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match=f"^{category}$"):
        nav.replay_torch(*changes[kind](), 5)


@pytest.mark.parametrize("value", (0, -1, float("inf"), float("nan")))
@pytest.mark.parametrize("column", (0, 1))
def test_invalid_open_or_close_price_unavailable(torch, sample, value, column):
    values = list(sample)
    values[column] = values[column].clone()
    values[column][1, 2] = value
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match="^price_domain$"):
        nav.replay_torch(*values, 5)


@pytest.mark.parametrize("kind", ("negative", "excess", "nan", "inf", "sum-low", "sum-high"))
def test_invalid_weights_not_clipped_or_normalized(torch, sample, kind):
    opens, closes, weights = sample
    weights = weights.clone()
    weights[1, 0] = {
        "negative": -0.1,
        "excess": 1.1,
        "nan": float("nan"),
        "inf": float("inf"),
        "sum-low": 0.59,
        "sum-high": 0.61,
    }[kind]
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match="^weight_domain$"):
        nav.replay_torch(opens, closes, weights, 5)


def test_declared_weight_tolerance_does_not_normalize(torch):
    prices = torch.ones((1, 3), dtype=torch.float64)
    weights = prices.new_tensor([[0.2, 0.3, 0.4, 0.1 + nav.WEIGHT_SUM_TOLERANCE / 2]])
    before = weights.clone()
    result = nav.replay_torch(prices, prices, weights, 0)
    torch.testing.assert_close(result.nav[0], weights.sum(), rtol=0, atol=0)
    assert torch.equal(weights, before)
    weights[0, 3] += 2e-12
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match="^weight_domain$"):
        nav.replay_torch(prices, prices, weights, 0)
    assert nav.WEIGHT_SUM_TOLERANCE == 64 * 2.0**-52
    assert nav.CASHFLOW_TOLERANCE == PARITY_TOLERANCE


@pytest.mark.parametrize("kind", ("ratio-overflow", "ratio-underflow", "nav-overflow", "nav-zero"))
def test_unrepresentable_numeric_ranges_rejected(torch, kind):
    prices = torch.ones((3, 3), dtype=torch.float64)
    closes = prices.clone()
    weights = prices.new_tensor([[1, 0, 0, 0]]).expand(3, 4)
    if kind == "ratio-overflow":
        prices[0, 0], prices[1, 0] = 1e-300, 1e300
    elif kind == "ratio-underflow":
        prices[0, 0], closes[0, 0] = 1e300, 1e-300
    elif kind == "nav-overflow":
        prices[:, 0] = prices.new_tensor([1e-200, 1, 1e200])
        closes[:, 0] = prices[:, 0]
    else:
        prices[:, 0] = prices.new_tensor([1e200, 1, 1e-200])
        closes[:, 0] = prices[:, 0]
    with pytest.raises(nav.DifferentiableThreeAssetNavError, match="^numeric_range$"):
        nav.replay_torch(prices, closes, weights, 5)


def test_smooth_gradcheck_prices_logits_and_cost_with_previous_weight_paths(torch, sample):
    opens, closes, weights = sample
    opens, closes = opens.requires_grad_(), closes.requires_grad_()
    logits = weights.log().requires_grad_()
    cost = weights.new_tensor(5, requires_grad=True)

    def outputs(opening, closing, scores, bps):
        result = nav.replay_torch(opening, closing, scores.softmax(dim=1), bps)
        return tuple(getattr(result, name) for name in OUTPUTS)

    assert torch.autograd.gradcheck(
        outputs, (opens, closes, logits, cost), eps=1e-6, atol=1e-7, rtol=2e-5
    )
    result = nav.replay_torch(opens, closes, logits.softmax(dim=1), cost)
    previous_gradient = torch.autograd.grad(result.fees[1], logits, retain_graph=True)[0]
    assert previous_gradient[0].abs().sum() > 0
    overnight_gradient = torch.autograd.grad(result.nav[-1], opens)[0]
    assert overnight_gradient[0].abs().sum() > 0


def test_replay_tie_one_sided_feasible_weight_direction(torch):
    prices = torch.ones((3, 3), dtype=torch.float64)
    weights = prices.new_tensor([[0.2, 0.3, 0.4, 0.1]]).expand(3, 4).clone().requires_grad_()
    result = nav.replay_torch(prices, prices, weights, 100)
    direction = torch.zeros_like(weights)
    direction[1] = weights.new_tensor([-0.01, -0.02, -0.03, 0.06])
    step = 1e-6
    shifted = nav.replay_torch(prices, prices, weights.detach() + step * direction, 100)
    for name in OUTPUTS:
        value = getattr(result, name)
        gradient = torch.autograd.grad(value[1], weights, retain_graph=True)[0]
        derivative = (getattr(shifted, name)[1] - value[1].detach()) / step
        torch.testing.assert_close((gradient * direction).sum(), derivative, rtol=2e-5, atol=2e-9)


def test_synthetic_cpu_log_utility_backward_and_update(torch, sample):
    opens, closes, weights = sample
    logits = weights.log().requires_grad_()
    result = nav.replay_torch(opens, closes, logits.softmax(dim=1), 5)
    utility = 252 * (result.log_returns.mean() - 5 * result.log_returns.var(unbiased=False))
    utility.backward()
    assert torch.isfinite(logits.grad).all() and logits.grad.abs().sum() > 0
    before = logits.detach().clone()
    with torch.no_grad():
        logits += 0.001 * logits.grad
    assert not torch.equal(logits, before)
    updated = nav.replay_torch(opens, closes, logits.softmax(dim=1), 5)
    assert torch.isfinite(updated.log_returns).all()


def test_output_frozen_hidden_inputs_unchanged_and_repeated_deterministic(torch, sample):
    before = tuple(value.clone() for value in sample)
    first, second = nav.replay_torch(*sample, 5), nav.replay_torch(*sample, 5)
    assert nav.ASSET_ORDER == ("SPY", "QQQ", "IWM", "cash")
    assert repr(first) == "DifferentiableThreeAssetReplay()"
    assert all(not item.repr for item in fields(first))
    with pytest.raises(FrozenInstanceError):
        first.nav = None
    for name in OUTPUTS:
        value = getattr(first, name)
        assert value.dtype == torch.float64 and value.device.type == "cpu"
        assert torch.equal(value, getattr(second, name))
    assert all(torch.equal(value, original) for value, original in zip(sample, before, strict=True))


def test_import_does_not_load_torch(monkeypatch):
    original = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("Torch must be imported only on replay")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)
    spec = importlib.util.spec_from_file_location("_lazy_nav_test", nav.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert callable(module.replay_torch)


def test_replay_performs_no_io_environment_network_or_broker_access(torch, sample, monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError("pure replay cannot access external state")

    with monkeypatch.context() as isolated:
        for target, name in (
            (builtins, "open"),
            (Path, "open"),
            (Path, "read_bytes"),
            (Path, "read_text"),
            (os, "getenv"),
            (socket, "create_connection"),
            (urllib.request, "urlopen"),
        ):
            isolated.setattr(target, name, prohibited)
        result = nav.replay_torch(*sample, 5)
    assert result.nav.shape == (3,)

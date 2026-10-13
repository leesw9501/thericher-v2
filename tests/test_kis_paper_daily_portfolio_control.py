"""Synthetic arithmetic and independent covariance tests; no market or broker."""

from decimal import Decimal, localcontext
from fractions import Fraction

import numpy as np
import pytest

from thericher_v2.research.kis_paper_daily_portfolio_control import (
    SYMBOLS,
    build_capped_thirds_control,
)


def columns(*, volatile=False):
    if volatile:
        return {
            symbol: tuple(Decimal(100 + (i % 2) * (80 - 10 * j)) for i in range(253))
            for j, symbol in enumerate(SYMBOLS)
        }
    return {
        symbol: tuple(Decimal(10000 + i + (i % (3 + j))) for i in range(253))
        for j, symbol in enumerate(SYMBOLS)
    }


def independent_covariance(data):
    with localcontext() as context:
        context.prec = 50
        returns = np.asarray([
            [(b - a) / a for a, b in zip(data[s], data[s][1:], strict=False)]
            for s in SYMBOLS
        ], dtype=float)
    covariance = np.cov(returns, bias=True)
    return 0.9 * covariance + 0.1 * np.diag(np.diag(covariance))


def test_constant_repeated_prices_are_valid_and_exactly_unlevered():
    data = {symbol: (Decimal(100),) * 253 for symbol in SYMBOLS}
    weights, covariance = build_capped_thirds_control(data)
    assert sum(map(Fraction, weights.values())) == 1
    assert all(value == 0 for row in covariance.values() for value in row.values())
    assert abs(weights["SPY"] - weights["GLD"]) < Decimal("1e-49")


@pytest.mark.parametrize("volatile", [False, True])
def test_population_shrinkage_risk_cap_and_inputs_unchanged(volatile):
    data = columns(volatile=volatile)
    original = dict(data)
    weights, matrix = build_capped_thirds_control(data)
    actual = np.asarray([[matrix[s][t] for t in SYMBOLS] for s in SYMBOLS], dtype=float)
    expected = independent_covariance(data)
    np.testing.assert_allclose(actual, expected, rtol=2e-14, atol=1e-25)
    vector = np.asarray([weights[s] for s in SYMBOLS], dtype=float)
    volatility = np.sqrt(252 * float(vector @ actual @ vector))
    assert volatility <= 0.10 + 1e-14
    total = sum(map(Fraction, weights.values()))
    assert 0 < total <= 1
    assert (total < 1) is volatile
    assert data == original
    assert build_capped_thirds_control(dict(reversed(list(data.items())))) == (weights, matrix)


def test_decimal_context_does_not_change_control():
    data = columns(volatile=True)
    expected = build_capped_thirds_control(data)
    with localcontext() as context:
        context.prec = 6
        assert build_capped_thirds_control(data) == expected


@pytest.mark.parametrize("count", [0, 252, 254])
def test_wrong_window_is_rejected(count):
    data = {symbol: (Decimal(100),) * count for symbol in SYMBOLS}
    with pytest.raises(ValueError, match="control_close_input"):
        build_capped_thirds_control(data)


@pytest.mark.parametrize(
    "bad", [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity"), 1, True, "1"]
)
def test_invalid_close_is_rejected(bad):
    data = columns()
    data["SPY"] = (bad,) + data["SPY"][1:]
    with pytest.raises(ValueError, match="control_close_input"):
        build_capped_thirds_control(data)


@pytest.mark.parametrize("symbol", ["QQQ", "IWM"])
def test_other_instrument_is_not_silently_adopted(symbol):
    data = columns()
    data[symbol] = data.pop("GLD")
    with pytest.raises(ValueError, match="control_instrument_scope"):
        build_capped_thirds_control(data)


def test_nonzero_decimal_return_underflow_is_not_flattened():
    data = {symbol: (Decimal(1),) * 253 for symbol in SYMBOLS}
    data["SPY"] = (Decimal("1." + "0" * 399 + "1"),) + data["SPY"][1:]
    with pytest.raises(ValueError, match="control_return_representation"):
        build_capped_thirds_control(data)


def test_extreme_returns_are_not_converted_to_infinity():
    data = columns()
    data["SPY"] = (Decimal("1e400"), Decimal("1e-400")) + data["SPY"][2:]
    with pytest.raises(ValueError):
        build_capped_thirds_control(data)


def test_nearly_singular_small_returns_keep_finite_covariance():
    data = {
        symbol: tuple(Decimal(1) + Decimal("1e-12") * (i % 5) for i in range(253))
        for symbol in SYMBOLS
    }
    weights, covariance = build_capped_thirds_control(data)
    assert sum(map(Fraction, weights.values())) == 1
    assert all(value.is_finite() for row in covariance.values() for value in row.values())
    assert all(covariance[s][s] > 0 for s in SYMBOLS)

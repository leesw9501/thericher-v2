from __future__ import annotations

import builtins
import os
import socket
import subprocess
import urllib.request
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Context,
    Decimal,
    localcontext,
)
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2.research.whole_share_quote_projection import (
    WholeShareQuoteProjectionError,
    project_quote,
)

D = Decimal
F = Fraction


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", "1.00"),
        ("1.00", "1.00"),
        ("1.00000", "1.00"),
        ("1.004999999999999999999", "1.00"),
        ("1.005", "1.00"),
        ("1.005000000000000000001", "1.01"),
        ("1.014999999999999999999", "1.01"),
        ("1.015", "1.02"),
        ("1.015000000000000000001", "1.02"),
        ("1.025", "1.02"),
        ("1.035", "1.04"),
        ("123.455", "123.46"),
        ("123.465", "123.46"),
        ("0.01", "0.01"),
        ("0.005000000000000000001", "0.01"),
        ("0.014999999999999999999", "0.01"),
        ("0.015", "0.02"),
        ("0.025", "0.02"),
        ("999.995", "1000.00"),
        ("12345678901234567890.123456789", "12345678901234567890.12"),
    ],
)
def test_nearest_cent_and_half_cent_parity_are_exact(raw, expected):
    value = D(raw)
    before = value.as_tuple()
    result = project_quote(value)
    assert type(result) is Decimal and result == D(expected)
    assert result.as_tuple().exponent == -2
    assert (F(result) * 100).denominator == 1
    assert abs(F(result) - F(value)) <= F(1, 200)
    assert value.as_tuple() == before


@pytest.mark.parametrize("floor_cents", [0, 1, 2, 3, 99, 100, 101, 102, 12345, 12346])
def test_tie_always_selects_even_cent_and_never_directional_bias(floor_cents):
    midpoint = D((0, D(10 * floor_cents + 5).as_tuple().digits, -3))
    expected = floor_cents + floor_cents % 2
    if expected == 0:
        with pytest.raises(WholeShareQuoteProjectionError, match="^projected_quote_nonpositive$"):
            project_quote(midpoint)
        return
    result = project_quote(midpoint)
    assert F(result) == F(expected, 100)
    assert (F(result) * 100).numerator % 2 == 0
    assert abs(F(result) - F(midpoint)) == F(1, 200)


@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_UP])
def test_ambient_precision_exponents_rounding_and_traps_cannot_change_projection(rounding):
    values = tuple(map(D, ("1.005", "1.015", "999.995", "1e300", "0.005000000001")))
    expected = tuple(map(project_quote, values))
    context = Context(prec=1, Emin=-1, Emax=1, clamp=1, rounding=rounding)
    for signal in context.traps:
        context.traps[signal] = True
    with localcontext(context) as active:
        before = dict(active.flags)
        assert tuple(map(project_quote, values)) == expected
        assert active.flags == before


@pytest.mark.parametrize("value", [D("1e300"), D("123456789012345678901234567890.005")])
def test_bounded_large_values_remain_exact_and_cent_aligned(value):
    result = project_quote(value)
    assert result.is_finite() and F(result) > 0
    assert (F(result) * 100).denominator == 1
    assert abs(F(result) - F(value)) <= F(1, 200)
    assert project_quote(result) == result


@pytest.mark.parametrize("raw", ["1e-300", "0.000001", "0.004999999999999999999", "0.005"])
def test_tiny_positive_values_that_round_to_zero_are_not_clipped(raw):
    value = D(raw)
    before = value.as_tuple()
    with pytest.raises(WholeShareQuoteProjectionError, match="^projected_quote_nonpositive$"):
        project_quote(value)
    assert value.as_tuple() == before


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        1,
        1.005,
        "1.005",
        F(201, 200),
        D(0),
        D("-0"),
        D("-1"),
        D("NaN"),
        D("sNaN"),
        D("Infinity"),
        D("-Infinity"),
    ],
)
def test_invalid_types_nonpositive_and_nonfinite_inputs_are_categorical(value):
    with pytest.raises(WholeShareQuoteProjectionError, match="^quote_invalid$"):
        project_quote(value)


def test_no_filesystem_environment_network_or_process_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("pure quote projection attempted an external effect")

    values = tuple(map(D, ("1.005", "1.015", "123.455")))
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", deny)
        patch.setattr(Path, "read_bytes", deny)
        patch.setattr(Path, "read_text", deny)
        patch.setattr(Path, "write_bytes", deny)
        patch.setattr(Path, "write_text", deny)
        patch.setattr(os, "getenv", deny)
        patch.setattr(type(os.environ), "__getitem__", deny)
        patch.setattr(socket, "create_connection", deny)
        patch.setattr(urllib.request, "urlopen", deny)
        patch.setattr(subprocess, "run", deny)
        assert tuple(map(project_quote, values)) == (D("1.00"), D("1.02"), D("123.46"))

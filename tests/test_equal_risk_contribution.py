"""Synthetic covariance only; no source values, fitting, broker or runtime probes."""

from __future__ import annotations

import itertools
import socket
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.research import equal_risk_contribution as erc


def covariance():
    vol = np.array([0.2, 0.1, 0.15])
    correlation = np.array([[1, 0.8, -0.2], [0.8, 1, 0.1], [-0.2, 0.1, 1]])
    return correlation * np.outer(vol, vol)


def independent_risk(c, weights):
    w = np.array([float(v) for v in weights])
    variance = sum(w[i] * c[i, j] * w[j] for i in range(3) for j in range(3))
    return tuple(w[i] * sum(c[i, j] * w[j] for j in range(3)) / variance for i in range(3))


def test_cross_covariance_equalizes_component_risk_and_conserves_exact_mass():
    c = covariance()
    answer = erc.equal_risk_contribution(c)
    assert sum(map(Fraction, answer.weights)) == 1
    assert all(0 < v < 1 for v in answer.weights)
    assert independent_risk(c, answer.weights) == pytest.approx((1 / 3,) * 3, abs=1e-12)
    assert answer.normalized_risk_contributions == pytest.approx(
        independent_risk(c, answer.weights), abs=1e-14
    )
    assert 1 <= answer.sweeps <= 1024
    assert erc.equal_risk_contribution_weights(c) == answer.weights


@pytest.mark.parametrize("diagonal", [(1, 4, 9), (0.04, 0.01, 0.09), (1, 1, 1)])
def test_diagonal_covariance_is_inverse_volatility(diagonal):
    expected = 1 / np.sqrt(diagonal)
    expected /= expected.sum()
    answer = erc.equal_risk_contribution(np.diag(diagonal))
    assert [float(v) for v in answer.weights] == pytest.approx(expected, abs=2e-12)


def test_nonuniform_off_diagonal_changes_weights_without_changing_marginal_volatility():
    c = covariance()
    full = erc.equal_risk_contribution_weights(c)
    diagonal = erc.equal_risk_contribution_weights(np.diag(np.diag(c)))
    assert max(abs(float(a - b)) for a, b in zip(full, diagonal, strict=True)) > 0.02
    assert max(abs(v - 1 / 3) for v in independent_risk(c, diagonal)) > 0.02


def test_equal_correlation_structure_collapses_to_inverse_volatility():
    vol = np.array([1.0, 2.0, 3.0])
    corr = np.full((3, 3), 0.4)
    np.fill_diagonal(corr, 1)
    result = erc.equal_risk_contribution_weights(corr * np.outer(vol, vol))
    expected = (1 / vol) / (1 / vol).sum()
    assert list(map(float, result)) == pytest.approx(expected, abs=2e-12)


@pytest.mark.parametrize("order", list(itertools.permutations(range(3))))
def test_column_permutation_preserves_the_corresponding_allocation(order):
    c = covariance()
    original = erc.equal_risk_contribution_weights(c)
    permuted = erc.equal_risk_contribution_weights(c[np.ix_(order, order)])
    assert list(map(float, permuted)) == pytest.approx(
        [float(original[i]) for i in order], abs=3e-12
    )


@pytest.mark.parametrize("scale", [1e-250, 1e-20, 1, 1e20, 1e250])
def test_whole_covariance_scale_does_not_change_weights(scale):
    c = covariance()
    expected = erc.equal_risk_contribution_weights(c)
    actual = erc.equal_risk_contribution_weights(c * scale)
    assert list(map(float, actual)) == pytest.approx(list(map(float, expected)), abs=3e-12)


@pytest.mark.parametrize(
    "values,reason",
    [
        (None, "covariance_values"),
        ([], "covariance_shape"),
        (np.eye(2), "covariance_shape"),
        ([[1, 0], [0, 1], [0, 0]], "covariance_shape"),
        ([[1, "0", 0], [0, 1, 0], [0, 0, 1]], "covariance_values"),
        (np.eye(3, dtype=bool), "covariance_values"),
        (np.eye(3, dtype=complex), "covariance_values"),
        (np.diag([1, np.nan, 1]), "covariance_values"),
        (np.diag([1, np.inf, 1]), "covariance_values"),
        ([[1, 0.2, 0], [0.1, 1, 0], [0, 0, 1]], "covariance_values"),
        (np.zeros((3, 3)), "covariance_not_positive_definite"),
        (np.diag([1, 0, 1]), "covariance_not_positive_definite"),
        (np.diag([1, -1, 1]), "covariance_not_positive_definite"),
        (np.ones((3, 3)), "covariance_not_positive_definite"),
        ([[1, 1, 0], [1, 1, 0], [0, 0, 1]], "covariance_not_positive_definite"),
        ([[1, 2, 0], [2, 1, 0], [0, 0, 1]], "covariance_not_positive_definite"),
    ],
)
def test_invalid_singular_or_indefinite_covariance_has_no_fallback(values, reason):
    with pytest.raises(erc.EqualRiskContributionUnavailable, match=f"^{reason}$") as error:
        erc.equal_risk_contribution(values)
    assert error.value.safe_facts() == {"status": "input_unavailable", "reason_code": reason}


def test_numerically_singular_positive_definite_matrix_is_not_repaired():
    c = np.full((3, 3), 1 - 1e-15)
    np.fill_diagonal(c, 1.0)
    with pytest.raises(erc.EqualRiskContributionUnavailable, match="positive_definite"):
        erc.equal_risk_contribution(c)


def test_bounded_nonconvergence_does_not_publish_partial_weights(monkeypatch):
    monkeypatch.setattr(erc, "MAX_SWEEPS", 1)
    with pytest.raises(erc.EqualRiskContributionUnavailable, match="allocation_not_converged"):
        erc.equal_risk_contribution(covariance())


def test_ambient_decimal_precision_does_not_change_normalization():
    expected = erc.equal_risk_contribution_weights(covariance())
    with localcontext() as context:
        context.prec = 3
        actual = erc.equal_risk_contribution_weights(covariance())
    assert actual == expected and sum(map(Fraction, actual)) == 1


def test_result_is_immutable_and_safe_projection_hides_numeric_values():
    answer = erc.equal_risk_contribution(covariance())
    assert "Decimal" not in repr(answer) and "weights=" not in repr(answer)
    assert answer.safe_facts() == {"status": "ready", "asset_count": 3, "sweeps": answer.sweeps}
    with pytest.raises(FrozenInstanceError):
        answer.sweeps = 999


def test_solver_does_not_mutate_or_retain_input_array():
    c = covariance()
    original = c.copy()
    answer = erc.equal_risk_contribution(c)
    np.testing.assert_array_equal(c, original)
    c[:] = 0
    assert answer.weights == erc.equal_risk_contribution_weights(original)


def test_solver_is_source_and_io_free(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Pure ERC attempted IO")

    monkeypatch.setattr(Path, "read_bytes", denied)
    monkeypatch.setattr(Path, "write_bytes", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr("builtins.open", denied)
    assert erc.equal_risk_contribution(covariance()).safe_facts()["status"] == "ready"


def test_fixed_solver_recipe_and_method_attribution():
    config = erc.configuration()
    assert config["max_sweeps"] == 1024 and config["risk_tolerance"] == 1e-12
    assert config["asset_count"] == 3 and config["method_url"].endswith("1311.4057v1")
    assert "no internal shrinkage" in config["covariance"]
    assert "fallback" in config["failure"]
    assert erc.WEIGHT_QUANTUM == Decimal("1e-45")

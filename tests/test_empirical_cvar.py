from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import empirical_cvar as cvar


def manufactured():
    return np.random.default_rng(101).normal(0.0002, 0.01, (252, 3))


def test_simplex_primal_and_epigraph_constraints():
    returns = manufactured()
    result = cvar.solve_cvar95(returns)
    weights = np.asarray(result.weights)
    losses = -returns @ weights
    assert np.all(weights >= 0) and np.all(weights <= 1)
    assert sum(result.weights) == pytest.approx(1, abs=1e-10)
    assert np.min(result.excess_losses) >= -1e-10
    assert np.all(np.asarray(result.excess_losses) >= losses - result.threshold - 1e-10)
    objective = result.threshold + (20 / 252) * sum(result.excess_losses)
    assert objective == pytest.approx(result.cvar, abs=1e-10)


def test_known_disjoint_tail_diversification_optimum():
    returns = np.zeros((252, 3))
    for i in range(3):
        returns[15 * i : 15 * (i + 1), i] = -0.03
    result = cvar.solve_cvar95(returns)
    assert result.weights == pytest.approx((1 / 3,) * 3, abs=1e-9)
    assert result.cvar == pytest.approx(0.01, abs=1e-10)


def test_exact_fractional_tail_mass_not_top13_average():
    losses = np.arange(1, 253, dtype=np.float64) / 1000
    expected = float(
        (sum(Fraction(i, 1000) for i in range(241, 253)) + Fraction(3, 5) * Fraction(240, 1000))
        / Fraction(63, 5)
    )
    result = cvar.solve_cvar95(-np.repeat(losses[:, None], 3, axis=1))
    assert result.cvar == pytest.approx(expected, abs=1e-10)
    assert cvar.empirical_cvar95(losses) == pytest.approx(expected, abs=1e-15)
    assert abs(result.cvar - np.mean(losses[-13:])) > 1e-6
    assert result.threshold == pytest.approx(0.24, abs=1e-10)
    gains = cvar.solve_cvar95(np.full((252, 3), 0.01))
    assert gains.cvar == pytest.approx(-0.01, abs=1e-10)


def test_dual_tail_marginals_and_asset_stationarity():
    returns = manufactured()
    result = cvar.solve_cvar95(returns)
    q = np.asarray(result.tail_marginals)
    losses = -returns @ np.asarray(result.weights)
    assert q.min() >= -1e-10 and q.max() <= 20 / 252 + 1e-10
    assert q.sum() == pytest.approx(1, abs=1e-10)
    assert q @ losses == pytest.approx(result.cvar, abs=1e-10)
    risks = -returns.T @ q
    for weight, risk in zip(result.weights, risks, strict=True):
        assert risk >= result.cvar - 1e-10
        if weight > 1e-8:
            assert risk == pytest.approx(result.cvar, abs=1e-10)


def test_short_wrong_shape_and_nonreal_reject_before_solver(monkeypatch):
    monkeypatch.setattr(cvar, "linprog", lambda *a, **k: pytest.fail("solver should not run"))
    for value in (
        np.zeros((251, 3)),
        np.zeros((253, 3)),
        np.zeros((252, 2)),
        np.zeros((3, 252)),
        np.zeros((252, 3), dtype=bool),
        np.zeros((252, 3), dtype=complex),
        np.full((252, 3), "0.1"),
    ):
        with pytest.raises(ValueError, match="finite_real_exact_geometry_required"):
            cvar.solve_cvar95(value)


def test_nonfinite_never_calls_solver(monkeypatch):
    monkeypatch.setattr(cvar, "linprog", lambda *a, **k: pytest.fail("solver should not run"))
    for invalid in (np.nan, np.inf, -np.inf):
        returns = manufactured()
        returns[0, 0] = invalid
        with pytest.raises(ValueError, match="finite_real_exact_geometry_required"):
            cvar.solve_cvar95(returns)


def test_solver_failure_and_corrupt_primal_dual_never_fallback(monkeypatch):
    original = cvar.linprog
    retained = []

    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        retained.append(result)
        return result

    monkeypatch.setattr(cvar, "linprog", capture)
    cvar.solve_cvar95(manufactured())
    result = retained[0]
    variants = [SimpleNamespace(success=False, status=2), SimpleNamespace(success=True, status=0)]
    for category in ("negative_weight", "simplex", "epigraph", "dual", "objective"):
        value = deepcopy(result)
        if category == "negative_weight":
            value.x[0] = -1e-12
        elif category == "simplex":
            value.x[:3] = 0
        elif category == "epigraph":
            value.x[4:] += 1
        elif category == "dual":
            value.ineqlin.marginals[:] = 0
        else:
            value.fun += 1
        variants.append(value)
    for value in variants:
        monkeypatch.setattr(cvar, "linprog", lambda *a, value=value, **k: value)
        with pytest.raises(cvar.CVaRUnavailable):
            cvar.solve_cvar95(manufactured())

    def failed_call(*args, **kwargs):
        raise RuntimeError("manufactured_private_exception_text")

    monkeypatch.setattr(cvar, "linprog", failed_call)
    with pytest.raises(cvar.CVaRUnavailable, match="^solver_call_failed$"):
        cvar.solve_cvar95(manufactured())


def test_same_order_same_runtime_determinism_no_mutation_or_risk_cap():
    returns = manufactured()
    before = returns.tobytes()
    first, second = cvar.solve_cvar95(returns), cvar.solve_cvar95(returns)
    assert first == second
    assert returns.tobytes() == before
    tied = np.zeros((252, 3))
    assert cvar.solve_cvar95(tied) == cvar.solve_cvar95(tied)
    assert first.safe_facts()["solver_calls"] == 1
    assert first.safe_facts()["risk_cap_or_execution_claim"] is False
    assert first.safe_facts()["fallback"] is False
    assert "weights" not in repr(first)
    with pytest.raises(FrozenInstanceError):
        first.weights = (1.0, 0.0, 0.0)

"""Fixed empirical95% CVaR LP on supplied252x3 returns; no IO or execution.

Minimize t + (20/252) sum(u), with u >= -R w - t, u >= 0,
w >= 0 and sum(w)=1. Equal scenario probabilities; fixed supplied column/row
order. HiGHS chooses one optimum: no secondary objective or cross-version tie
guarantee. No clipping, renormalization, fallback, mean target or risk cap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

SCENARIOS, ASSETS = 252, 3
CONFIDENCE = "0.95"
TAIL_MASS = 63 / 5
TAIL_COEFFICIENT = 20 / SCENARIOS
TOLERANCE = 1e-8
OPTIONS = {
    "presolve": True,
    "primal_feasibility_tolerance": 1e-9,
    "dual_feasibility_tolerance": 1e-9,
}


class CVaRUnavailable(ValueError):
    """Closed numerical/solver failure category; no allocation fallback."""


def _provided(value, shape):
    try:
        raw = np.asarray(value)
        if raw.shape != shape or raw.dtype.kind not in "iuf":
            raise ValueError
        result = np.array(raw, dtype=np.float64, copy=True)
        if not np.isfinite(result).all():
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ValueError("finite_real_exact_geometry_required") from None
    return result


def empirical_cvar95(losses):
    """Worst12 observations plus0.6 of the13th; NOT a rounded top13 mean."""
    values = np.sort(_provided(losses, (SCENARIOS,)))[::-1]
    try:
        result = (
            math.fsum([*(float(v) for v in values[:12]), float(values[12]) * 3 / 5]) / TAIL_MASS
        )
    except (OverflowError, ValueError):
        raise CVaRUnavailable("numerical_invalid") from None
    if not math.isfinite(result):
        raise CVaRUnavailable("numerical_invalid")
    return result


@dataclass(frozen=True, slots=True, repr=False)
class CVaRSolution:
    weights: tuple[float, float, float]
    threshold: float
    cvar: float
    excess_losses: tuple[float, ...]
    tail_marginals: tuple[float, ...]

    def safe_facts(self):
        return {
            "status": "optimal_numerically_attested",
            "scenarios": SCENARIOS,
            "assets": ASSETS,
            "confidence": CONFIDENCE,
            "solver_calls": 1,
            "tail_mass_observations": "12.6",
            "mean_target": False,
            "secondary_tie_objective": False,
            "fallback": False,
            "risk_cap_or_execution_claim": False,
        }


def solve_cvar95(returns) -> CVaRSolution:
    """One HiGHS solve and independent primal/dual/fractional-tail audit.

    Comparisons use fixed1e-8 absolute tolerance, scaled by max(1,loss and
    objective magnitude) for loss-unit comparisons only. Simplex and dual-mass
    checks are unscaled. Returned weights are original solver values, never
    clipped or normalized; any negative weight fails even within tolerance.
    """
    values = _provided(returns, (SCENARIOS, ASSETS))
    objective = np.r_[np.zeros(ASSETS), 1.0, np.full(SCENARIOS, TAIL_COEFFICIENT)]
    constraints = np.c_[-values, -np.ones(SCENARIOS), -np.eye(SCENARIOS)]
    equality = np.r_[np.ones(ASSETS), np.zeros(SCENARIOS + 1)][None, :]
    bounds = [(0, 1)] * ASSETS + [(None, None)] + [(0, None)] * SCENARIOS
    try:
        result = linprog(
            objective,
            A_ub=constraints,
            b_ub=np.zeros(SCENARIOS),
            A_eq=equality,
            b_eq=np.ones(1),
            bounds=bounds,
            method="highs",
            options=dict(OPTIONS),
        )
    except Exception:
        raise CVaRUnavailable("solver_call_failed") from None
    if not getattr(result, "success", False) or getattr(result, "status", None) != 0:
        raise CVaRUnavailable("solver_failed")
    try:
        x = _provided(result.x, (SCENARIOS + ASSETS + 1,))
        q = -_provided(result.ineqlin.marginals, (SCENARIOS,))
        reported = float(result.fun)
        if not math.isfinite(reported):
            raise ValueError
        w, threshold, u = x[:ASSETS], float(x[ASSETS]), x[ASSETS + 1 :]
        with np.errstate(over="raise", invalid="raise"):
            losses = -values @ w
            risks = -values.T @ q
            lp = float(objective @ x)
            hinge = threshold + TAIL_COEFFICIENT * math.fsum(np.maximum(losses - threshold, 0))
            tail = empirical_cvar95(losses)
            dual = float(q @ losses)
        scale = max(1.0, abs(threshold), abs(reported), float(np.max(np.abs(losses))))
        tolerance = TOLERANCE * scale
        valid = (
            np.isfinite(risks).all()
            and all(math.isfinite(v) for v in (lp, hinge, tail, dual))
            and np.all(w >= 0)
            and np.all(w <= 1)
            and abs(math.fsum(w) - 1) <= TOLERANCE
            and np.all(u >= -tolerance)
            and np.all(u >= losses - threshold - tolerance)
            and np.all(q >= -TOLERANCE)
            and np.all(q <= TAIL_COEFFICIENT + TOLERANCE)
            and abs(math.fsum(q) - 1) <= TOLERANCE
            and all(abs(v - reported) <= tolerance for v in (lp, hinge, tail, dual))
            and np.all(risks >= reported - tolerance)
            and np.all(np.abs(risks[w > TOLERANCE] - reported) <= tolerance)
        )
        if not valid:
            raise ValueError
    except (ValueError, TypeError, AttributeError, ArithmeticError):
        raise CVaRUnavailable("numerical_attestation_failed") from None
    return CVaRSolution(
        tuple(map(float, w)), threshold, reported, tuple(map(float, u)), tuple(map(float, q))
    )

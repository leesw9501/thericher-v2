"""Pure three-asset covariance ERC; no IO, estimator, clocks, or cash overlay.

Method: Griveau-Billion, Richard and Roncalli (2013), arXiv:1311.4057v1,
sections 1-2 and appendix A.3.2: equal risk budgets and cyclic coordinate
minimization of a quadratic with a logarithmic barrier. This is original
implementation of the equations, not copied repository or paper code.

The caller supplies identically ordered, causal covariance columns. Population
covariance, source grade, adjustment, shrinkage, availability, cadence and cost
accounting remain caller responsibilities. No implicit shrinkage or fallback.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from fractions import Fraction
from math import fsum, hypot, isfinite, sqrt
from numbers import Real

import numpy as np

ASSET_COUNT = 3
MAX_SWEEPS = 1024
RISK_TOLERANCE = 1e-12
MIN_CORRELATION_EIGENVALUE = 64 * np.finfo(np.float64).eps
WEIGHT_QUANTUM = Decimal("1e-45")
CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
METHOD_URL = "https://arxiv.org/pdf/1311.4057v1"


class EqualRiskContributionUnavailable(ValueError):
    """Scoped numerical failure, never a substitute allocation."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def safe_facts(self) -> dict[str, str]:
        return {"status": "input_unavailable", "reason_code": self.reason_code}


@dataclass(frozen=True, slots=True, repr=False)
class EqualRiskContribution:
    weights: tuple[Decimal, Decimal, Decimal]
    normalized_risk_contributions: tuple[float, float, float]
    sweeps: int

    def safe_facts(self) -> dict[str, str | int]:
        return {"status": "ready", "asset_count": ASSET_COUNT, "sweeps": self.sweeps}


def configuration() -> dict[str, str | int | float]:
    return {
        "algorithm": "cyclic_coordinate_descent_quadratic_log_barrier",
        "asset_count": ASSET_COUNT,
        "risk_budgets": "equal thirds",
        "coordinate_order": "caller column order",
        "initialization": "three copies of sqrt(1/3) in correlation space",
        "max_sweeps": MAX_SWEEPS,
        "risk_tolerance": RISK_TOLERANCE,
        "minimum_correlation_eigenvalue": MIN_CORRELATION_EIGENVALUE,
        "numeric": "float64; Decimal50 HALF_EVEN 45dp/last-column residual",
        "covariance": "exact symmetric positive definite; no internal shrinkage",
        "failure": "no clipping, inverse-volatility fallback, or partial allocation",
        "method_url": METHOD_URL,
    }


def _require(value: bool, reason: str) -> None:
    if not value:
        raise EqualRiskContributionUnavailable(reason)


def _covariance(values: Sequence[Sequence[float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        rows = tuple(tuple(row) for row in values)
        _require(
            len(rows) == ASSET_COUNT and all(len(row) == ASSET_COUNT for row in rows),
            "covariance_shape",
        )
        _require(
            all(
                isinstance(v, Real) and not isinstance(v, (bool, np.bool_))
                for row in rows
                for v in row
            ),
            "covariance_values",
        )
        c = np.asarray(rows, dtype=np.float64)
    except (TypeError, OverflowError):
        raise EqualRiskContributionUnavailable("covariance_values") from None
    _require(bool(np.isfinite(c).all()) and np.array_equal(c, c.T), "covariance_values")
    scale = float(np.abs(c).max())
    _require(scale > 0 and bool((np.diag(c) > 0).all()), "covariance_not_positive_definite")
    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        c = c / scale
        _require(bool((np.diag(c) > 0).all()), "covariance_not_representable")
        vol = np.sqrt(np.diag(c))
        # Sequential divisions avoid underflow of the volatility outer product.
        correlation = (c / vol[:, None]) / vol[None, :]
        correlation = correlation * 0.5 + correlation.T * 0.5
    _require(bool(np.isfinite(correlation).all()), "covariance_not_representable")
    _require(
        float(np.linalg.eigvalsh(correlation)[0]) > MIN_CORRELATION_EIGENVALUE,
        "covariance_not_positive_definite",
    )
    return c, correlation, vol


def _contributions(c: np.ndarray, weights: Sequence[float]) -> tuple[float, float, float]:
    w = np.asarray(weights, dtype=np.float64)
    gradient = c @ w
    variance = float(w @ gradient)
    _require(isfinite(variance) and variance > 0, "allocation_not_representable")
    values = tuple(float(v) for v in w * gradient / variance)
    _require(all(isfinite(v) for v in values), "allocation_not_representable")
    return values


def _decimal_weights(values: Sequence[float]) -> tuple[Decimal, Decimal, Decimal]:
    _require(all(isfinite(v) and v > 0 for v in values), "allocation_not_representable")
    with localcontext(CONTEXT):
        numbers = tuple(Decimal.from_float(v) for v in values)
        total = sum(numbers, Decimal(0))
        result = [(v / total).quantize(WEIGHT_QUANTUM) for v in numbers]
        result[-1] = 1 - sum(result[:-1], Decimal(0))
    _require(
        all(0 < v < 1 for v in result) and sum(map(Fraction, result)) == 1,
        "allocation_not_representable",
    )
    return tuple(result)


def equal_risk_contribution(covariance: Sequence[Sequence[float]]) -> EqualRiskContribution:
    """Solve positive three-asset ERC with fixed bounds, returning hidden numeric fields.

    Input is finite, exactly symmetric covariance in caller column order. An
    eigenvalue <=64 binary64 eps in correlation space is numerically singular
    and rejected, even if mathematically positive definite. Scalars multiplying
    the whole matrix do not change the economic allocation. Stop only when
    normalized component-risk residuals and the final Decimal weights meet
    1e-12. No expected return, target, tuning parameter or source read is used.
    """
    try:
        c, correlation, vol = _covariance(covariance)
        budget = 1 / ASSET_COUNT
        y = [sqrt(budget)] * ASSET_COUNT
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            for sweep in range(1, MAX_SWEEPS + 1):
                for i in range(ASSET_COUNT):
                    a = float(correlation[i, i])
                    cross = fsum(
                        float(correlation[i, j]) * y[j] for j in range(ASSET_COUNT) if j != i
                    )
                    root = hypot(cross, 2 * sqrt(a * budget))
                    # Positive quadratic root without cancellation for cross>=0.
                    y[i] = 2 * budget / (root + cross) if cross >= 0 else (root - cross) / (2 * a)
                    _require(isfinite(y[i]) and y[i] > 0, "allocation_not_representable")
                residual = max(abs(v - budget) for v in _contributions(correlation, y))
                if residual <= RISK_TOLERANCE:
                    weights = _decimal_weights(
                        tuple(float(v / s) for v, s in zip(y, vol, strict=True))
                    )
                    risk = _contributions(c, tuple(float(w) for w in weights))
                    _require(
                        max(abs(v - budget) for v in risk) <= RISK_TOLERANCE,
                        "allocation_not_representable",
                    )
                    return EqualRiskContribution(weights, risk, sweep)
    except (FloatingPointError, np.linalg.LinAlgError, ArithmeticError):
        raise EqualRiskContributionUnavailable("allocation_not_representable") from None
    raise EqualRiskContributionUnavailable("allocation_not_converged")


def equal_risk_contribution_weights(
    covariance: Sequence[Sequence[float]],
) -> tuple[Decimal, Decimal, Decimal]:
    """Weight-only adapter compatible with existing three-asset NAV consumers."""
    return equal_risk_contribution(covariance).weights

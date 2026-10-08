"""Pure three-asset ANTICOR transfers; no clocks, IO, fitting, or execution.

Reference: Borodin, El-Yaniv and Gogan (2004), DOI 10.1613/jair.1336,
https://arxiv.org/pdf/1107.0036v1, equations (2)-(3) and Figure 1.
Figure 1's inclusive mean comparison is used, rather than the prose's strict
comparison. Its all-pairs claims include diagonal claims: self-transfers use
the same donor denominator but cancel in the portfolio update.

The caller supplies two consecutive, completed past log-return windows with
identically ordered asset columns and already drifted weights. Causal source
availability, price basis, calendars, cadence, costs, and any cash overlay
remain caller responsibilities. This primitive establishes none of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from math import fsum, isclose, isfinite, sqrt, ulp
from numbers import Real

ASSET_COUNT = 3
WEIGHT_SUM_TOLERANCE = 32 * ulp(1.0)
Weights = tuple[float, float, float]
Window = tuple[Weights, ...]


def _finite_real(value: object, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(reason)
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(reason) from error
    if not isfinite(result):
        raise ValueError(reason)
    return result


def _window(values: Sequence[Sequence[float]]) -> Window:
    try:
        rows = tuple(tuple(row) for row in values)
    except TypeError as error:
        raise ValueError("window_shape") from error
    if len(rows) < 2 or any(len(row) != ASSET_COUNT for row in rows):
        raise ValueError("window_shape")
    return tuple(tuple(_finite_real(value, "window_value") for value in row) for row in rows)


def _weights(values: Sequence[float]) -> tuple[Fraction, Fraction, Fraction]:
    try:
        numbers = tuple(_finite_real(value, "weight_value") for value in values)
    except TypeError as error:
        raise ValueError("weight_shape") from error
    if len(numbers) != ASSET_COUNT:
        raise ValueError("weight_shape")
    if any(value < 0 or value > 1 for value in numbers):
        raise ValueError("weight_domain")
    if not isclose(fsum(numbers), 1.0, rel_tol=0.0, abs_tol=WEIGHT_SUM_TOLERANCE):
        raise ValueError("weight_sum")
    fractions = tuple(Fraction(value) for value in numbers)
    total = sum(fractions)
    # Normalize only accepted binary rounding, without assigning one asset a residual.
    return tuple(value / total for value in fractions)


def _column_statistics(window: Window) -> tuple[tuple[Fraction, ...], tuple[tuple, ...]]:
    means = []
    vectors = []
    for column in zip(*window, strict=True):
        exact = tuple(Fraction(value) for value in column)
        mean = sum(exact) / len(exact)
        centered = tuple(value - mean for value in exact)
        scale = max(abs(value) for value in centered)
        means.append(mean)
        if scale == 0:
            vectors.append(())
            continue
        # Scaling before conversion avoids overflow and preserves subnormal variation.
        scaled = tuple(float(value / scale) for value in centered)
        norm = sqrt(fsum(value * value for value in scaled))
        vectors.append(tuple(value / norm for value in scaled))
    return tuple(means), tuple(vectors)


def _cross_correlations(previous: Window, recent: Window) -> tuple[tuple[float, ...], ...]:
    _, earlier_vectors = _column_statistics(previous)
    _, recent_vectors = _column_statistics(recent)
    result = []
    for earlier in earlier_vectors:
        row = []
        for later in recent_vectors:
            value = fsum(a * b for a, b in zip(earlier, later, strict=True)) if (
                earlier and later
            ) else 0.0
            # Cauchy's bound; clipping here addresses dot-product rounding only.
            row.append(min(1.0, max(-1.0, value)))
        result.append(tuple(row))
    return tuple(result)


def anticor_allocation(
    previous_log_returns: Sequence[Sequence[float]],
    recent_log_returns: Sequence[Sequence[float]],
    drifted_weights: Sequence[float],
) -> Weights:
    """Return long-only weights from equal time-major ``(w, 3)`` windows, w>=2.

    All numbers must be finite real scalars. Weights must already be in [0, 1]
    and sum to one within 32 binary64 ulps. Exact rational transfer accounting
    conserves the normalized input mass; output conversion rounds to binary64.
    Zero-variance correlations are zero, with no epsilon variance threshold.
    No damping, window search, cash gate, payoff, or second drift is applied.
    """
    previous, recent = _window(previous_log_returns), _window(recent_log_returns)
    if len(previous) != len(recent):
        raise ValueError("window_length")
    original = _weights(drifted_weights)
    recent_means, _ = _column_statistics(recent)
    correlations = _cross_correlations(previous, recent)
    reversal = tuple(max(0.0, -correlations[i][i]) for i in range(ASSET_COUNT))
    balances = [Fraction(0) for _ in original]
    for donor in range(ASSET_COUNT):
        claims = tuple(
            Fraction(correlations[donor][recipient] + reversal[donor] + reversal[recipient])
            if recent_means[donor] >= recent_means[recipient]
            and correlations[donor][recipient] > 0.0
            else Fraction(0)
            for recipient in range(ASSET_COUNT)
        )
        total = sum(claims)
        if total == 0:
            balances[donor] += original[donor]
        else:
            for recipient, claim in enumerate(claims):
                balances[recipient] += original[donor] * claim / total
    if sum(balances) != 1 or any(value < 0 or value > 1 for value in balances):
        raise ArithmeticError("transfer_invariant")
    return tuple(float(value) for value in balances)

"""Original three-ETF engineering control, independent of one-shot artifacts.

This is arithmetic only, not a profitable strategy or a cash allocation. The
caller owns session alignment, source/availability and native execution risk.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from fractions import Fraction

SYMBOLS = ("SPY", "TLT", "GLD")
CONTEXT_CLOSES = 253
ANNUAL_VOLATILITY_CAP = 0.10
_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)


def build_capped_thirds_control(
    closes_by_symbol: Mapping[str, Sequence[Decimal]],
) -> tuple[dict[str, Decimal], dict[str, dict[str, Decimal]]]:
    """Return original weights and daily shrunk population covariance.

    Equal thirds are only reduced when annualized risk exceeds ten percent.
    This number does not replace the executor's shared initial-cash tenth.
    Repeated price values and zero variance are valid; no date is inferred.
    """
    import numpy as np

    from thericher_v2.research.joint_portfolio_covariance import _population_covariance

    if not isinstance(closes_by_symbol, Mapping) or set(closes_by_symbol) != set(SYMBOLS):
        raise ValueError("control_instrument_scope")
    columns = tuple(closes_by_symbol[symbol] for symbol in SYMBOLS)
    if any(
        not isinstance(column, Sequence)
        or len(column) != CONTEXT_CLOSES
        or any(
            type(value) is not Decimal or not value.is_finite() or value <= 0
            for value in column
        )
        for column in columns
    ):
        raise ValueError("control_close_input")
    try:
        with localcontext(_CONTEXT):
            returns = tuple(
                tuple((b - a) / a for a, b in zip(column, column[1:], strict=False))
                for column in columns
            )
            weights = [Decimal(1) / 3] * 2
            weights.append(1 - sum(weights))
        values = np.asarray(returns, dtype=np.float64).T
        if not np.isfinite(values).all() or not (values > -1).all() or any(
            value != 0 and converted == 0
            for column, converted_column in zip(returns, values.T, strict=True)
            for value, converted in zip(column, converted_column, strict=True)
        ):
            raise ValueError("control_return_representation")
        covariance = _population_covariance(values)
        shrunk = 0.9 * covariance + 0.1 * np.diag(np.diag(covariance))
        if not np.array_equal(shrunk, shrunk.T):
            raise ValueError("control_covariance_symmetry")
        vector = np.asarray(weights, dtype=np.float64)
        volatility = math.sqrt(252 * float(vector @ shrunk @ vector))
        if not math.isfinite(volatility):
            raise ValueError("control_risk_representation")
        exposure = (
            Decimal(1) if volatility <= ANNUAL_VOLATILITY_CAP
            else Decimal.from_float(ANNUAL_VOLATILITY_CAP / volatility)
        )
        with localcontext(_CONTEXT):
            scaled = tuple(weight * exposure for weight in weights)
        with localcontext(_CONTEXT) as context:
            context.prec = max(100, max(-value.as_tuple().exponent for value in scaled) + 2)
            cash = 1 - sum(scaled, Decimal(0))
        if sum(map(Fraction, scaled), Fraction(cash)) != 1:
            raise ValueError("control_weight_representation")
        matrix = {
            symbol: {
                other: Decimal.from_float(float(shrunk[i, j]))
                for j, other in enumerate(SYMBOLS)
            }
            for i, symbol in enumerate(SYMBOLS)
        }
        return dict(zip(SYMBOLS, scaled, strict=True)), matrix
    except ArithmeticError:
        raise ValueError("control_numeric_unavailable") from None

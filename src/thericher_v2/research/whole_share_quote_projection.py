"""Synthetic analytical nearest-cent quotes, not observed broker quotes.

This projection does not establish adjusted prices, total returns or historical
quote availability. Callers retain raw feature/covariance inputs separately.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction


class WholeShareQuoteProjectionError(ValueError):
    """Categorical invalid/unavailable quote, without its numeric value."""


def project_quote(value: Decimal) -> Decimal:
    """Project a positive finite Decimal to .01, nearest with exact ties-to-even.

    No directional choice, minimum-cent clipping or ambient Decimal rounding is
    used. A value that projects to zero is unavailable, not repaired to one cent.
    """
    if type(value) is not Decimal or not value.is_finite():
        raise WholeShareQuoteProjectionError("quote_invalid")
    exact = Fraction(value)
    if exact <= 0:
        raise WholeShareQuoteProjectionError("quote_invalid")
    cents = exact * 100
    whole, remainder = divmod(cents.numerator, cents.denominator)
    twice = 2 * remainder
    if twice > cents.denominator or (twice == cents.denominator and whole % 2):
        whole += 1
    if whole <= 0:
        raise WholeShareQuoteProjectionError("projected_quote_nonpositive")
    # Integer and tuple Decimal construction are exact even under hostile contexts.
    return Decimal((0, Decimal(whole).as_tuple().digits, -2))

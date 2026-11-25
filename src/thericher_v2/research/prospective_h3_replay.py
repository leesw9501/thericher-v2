"""Pure single-cohort replay for the frozen fixed-half H3 study."""

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import ProspectiveH3Marks

_SYMBOLS = tuple("AAPL AMD AMZN GOOGL META MSFT NVDA TSLA JPM JNJ XOM PG KO HD V DIS UNH".split())
_SESSIONS = tuple(
    tuple(date.fromisoformat(day) for day in row.split())
    for row in (
        "2026-11-30 2026-12-01 2026-12-02 2026-12-03",
        "2026-12-04 2026-12-07 2026-12-08 2026-12-09",
        "2026-12-10 2026-12-11 2026-12-14 2026-12-15",
        "2026-12-16 2026-12-17 2026-12-18 2026-12-21",
        "2026-12-22 2026-12-23 2026-12-24 2026-12-28",
    )
)
_COUNT = len(_SYMBOLS)
_FEE = Fraction(1, 400)
_ZERO = Fraction(0)
_ONE = Fraction(1)


@dataclass(frozen=True)
class H3Book:
    """All notionals and fees are in units of original NAV (one)."""

    entry_notional: Fraction
    exit_notional: Fraction
    nav: tuple[Fraction, ...] = field(repr=False)
    drawdown: Fraction
    mean_sampled_gross: Fraction
    peak_sampled_gross: Fraction
    peak_issuer_nav_share: Fraction

    @property
    def growth(self) -> Fraction:
        return self.nav[-1] - _ONE

    @property
    def turnover(self) -> Fraction:
        return self.entry_notional + self.exit_notional

    @property
    def fees(self) -> Fraction:
        return self.turnover * _FEE


@dataclass(frozen=True)
class ProspectiveH3Replay:
    interval: H3Interval
    status: Literal["no_signal", "scored"]
    model: H3Book
    matched_gross_ew: H3Book
    cash: H3Book


def replay_prospective_h3_cohort(
    interval: H3Interval,
    marks: ProspectiveH3Marks,
    *,
    forecast_symbols: tuple[str, ...],
    blend_scores: tuple[float | Decimal, ...],
) -> ProspectiveH3Replay:
    """Score an already admitted forecast and target pair, without opening any files.

    The caller verifies seal timing, 50:50 composition, score-to-interval binding,
    target provenance/basis and block-end admission. Invalid inputs raise rather
    than producing a flat result. Each cohort starts from unit NAV independently.
    """
    if (
        type(interval) is not H3Interval
        or type(marks) is not ProspectiveH3Marks
        or marks.sessions not in _SESSIONS
        or interval != H3Interval(marks.sessions[0], marks.sessions[-1])
    ):
        raise ValueError("h3_replay_interval_invalid")
    if marks.symbols != _SYMBOLS or forecast_symbols != _SYMBOLS:
        raise ValueError("h3_replay_axis_invalid")
    if (
        type(blend_scores) is not tuple
        or len(blend_scores) != _COUNT
        or not all(_finite_score(score) for score in blend_scores)
    ):
        raise ValueError("h3_replay_scores_invalid")
    opens = _exact_marks(marks.opens, 4)
    closes = _exact_marks(marks.closes, 3)
    positive = tuple(score > 0 for score in blend_scores)
    requested_gross = Fraction(sum(positive), 2 * _COUNT)
    slot_notional = Fraction(1, 2 * _COUNT) / (1 + _FEE * requested_gross)
    model = _replay(tuple(slot_notional if take else _ZERO for take in positive), opens, closes)
    # Unit starting cash and the same native cap make the model's funded gross
    # feasible for EW by construction; only its allocation across names changes.
    ew = _replay((model.entry_notional / _COUNT,) * _COUNT, opens, closes)
    cash = H3Book(_ZERO, _ZERO, (_ONE,) * len(model.nav), _ZERO, _ZERO, _ZERO, _ZERO)
    status = "scored" if requested_gross else "no_signal"
    return ProspectiveH3Replay(interval, status, model, ew, cash)


def _finite_score(score: object) -> bool:
    if isinstance(score, Decimal):
        return score.is_finite()
    return type(score) is float and math.isfinite(score)


def _exact_marks(
    grid: tuple[tuple[Decimal, ...], ...], rows: int
) -> tuple[tuple[Fraction, ...], ...]:
    if (
        type(grid) is not tuple
        or len(grid) != rows
        or any(
            type(row) is not tuple
            or len(row) != _COUNT
            or any(
                type(value) is not Decimal or not value.is_finite() or value <= 0 for value in row
            )
            for row in grid
        )
    ):
        raise ValueError("h3_replay_marks_invalid")
    return tuple(tuple(Fraction(value) for value in row) for row in grid)


def _replay(
    allocations: tuple[Fraction, ...],
    opens: tuple[tuple[Fraction, ...], ...],
    closes: tuple[tuple[Fraction, ...], ...],
) -> H3Book:
    buy = sum(allocations, _ZERO)
    remaining = _ONE - buy * (1 + _FEE)
    quantities = tuple(amount / price for amount, price in zip(allocations, opens[0], strict=True))
    nav, exposure = [_ONE], [_ZERO]
    peak_issuer = _ZERO
    # Original sf_book grid, including the unchanged pre/post intermediate
    # opens and the pre-liquidation expiry open.
    for prices in (
        opens[0],
        closes[0],
        opens[1],
        opens[1],
        closes[1],
        opens[2],
        opens[2],
        closes[2],
        opens[3],
    ):
        values = tuple(q * p for q, p in zip(quantities, prices, strict=True))
        gross = sum(values, _ZERO)
        value = remaining + gross
        nav.append(value)
        exposure.append(gross / value)
        peak_issuer = max(peak_issuer, max(values) / value)
    sell = gross
    nav.append(remaining + sell * (1 - _FEE))
    exposure.append(_ZERO)
    peak, dd = _ONE, _ZERO
    for value in nav:
        peak = max(peak, value)
        dd = max(dd, 1 - value / peak)
    return H3Book(
        buy, sell, tuple(nav), dd, sum(exposure, _ZERO) / len(exposure), max(exposure), peak_issuer
    )

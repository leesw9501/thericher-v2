"""Pure past-only, same-vintage D1 inputs for one three-ETF covariance study.

Callers bind adjusted values, vintage provenance, the exact scheduled dates and
decision-time availability. Bar's UTC day end is representation completeness,
not an exchange close or proof of historical availability. No provider, calendar
inference, target, allocation, fitting, cost model or trading path lives here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import MAX_EMAX, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal, localcontext

import numpy as np

from thericher_v2.contracts import Bar, Timeframe, require_utc

SYMBOLS = ("SPY", "QQQ", "IWM")
CONTEXT_RETURNS = 252
CONTEXT_CLOSES = CONTEXT_RETURNS + 1


class JointPortfolioInputUnavailable(ValueError):
    """A categorical failure of only this requested input window."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def safe_facts(self) -> dict[str, str]:
        return {"status": "input_unavailable", "reason_code": self.reason_code}


@dataclass(frozen=True, slots=True, repr=False)
class JointPortfolioCovarianceInput:
    symbols: tuple[str, ...]
    scheduled_dates: tuple[date, ...]
    decision_at: datetime
    completed_through: datetime
    source_vintage_ref: str
    # Rows follow scheduled_dates[1:]; columns are always SPY, QQQ, IWM.
    returns: tuple[tuple[float, ...], ...]
    covariance: tuple[tuple[float, ...], ...]

    def safe_facts(self) -> dict[str, str | int]:
        return {
            "status": "ready",
            "symbol_count": len(self.symbols),
            "close_count_per_symbol": len(self.scheduled_dates),
            "return_count": len(self.returns),
            "covariance_rows": len(self.covariance),
            "covariance_columns": len(self.symbols),
            "history_start": self.scheduled_dates[0].isoformat(),
            "history_last_session": self.scheduled_dates[-1].isoformat(),
            "completed_through": self.completed_through.isoformat(),
            "decision_at": self.decision_at.isoformat(),
        }


def _contract(condition: bool, reason_code: str) -> None:
    if not condition:
        raise ValueError(reason_code)


def _required_bars(
    bars: Sequence[Bar], *, symbol: str, dates: tuple[date, ...], decision_at: datetime
) -> tuple[Bar, ...]:
    _contract(isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)), "source_sequence")
    date_set = frozenset(dates)
    required = []
    # Select by past session keys before consulting values or completeness.
    # Unrelated current/future support is never an input-availability mask.
    for bar in bars:
        start = getattr(bar, "start_ts", None)
        if (
            isinstance(start, datetime)
            and start.tzinfo is not None
            and start.utcoffset() is not None
            and start.astimezone(UTC).date() in date_set
        ):
            required.append(bar)
    starts = [bar.start_ts for bar in required]
    if len(set(starts)) != len(starts):
        raise JointPortfolioInputUnavailable("required_session_duplicate")
    if len(required) != CONTEXT_CLOSES:
        raise JointPortfolioInputUnavailable("required_session_missing")
    expected = tuple(datetime.combine(day, time(), UTC) for day in dates)
    if tuple(starts) != expected:
        raise JointPortfolioInputUnavailable("required_session_alignment_or_order")
    for bar in required:
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or bar.start_ts.utcoffset() != timedelta(0)
        ):
            raise JointPortfolioInputUnavailable("required_bar_identity")
        if bar.complete is not True or bar.end_ts > decision_at:
            raise JointPortfolioInputUnavailable("required_bar_incomplete")
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if any(type(value) is not Decimal or not value.is_finite() for value in values):
            raise JointPortfolioInputUnavailable("required_bar_values_invalid")
        try:
            replace(bar)
        except (ValueError, TypeError, ArithmeticError):
            raise JointPortfolioInputUnavailable("required_bar_values_invalid") from None
    return tuple(required)


def _simple_returns(bars: tuple[Bar, ...]) -> tuple[float, ...]:
    # Fixed Decimal arithmetic avoids float-price overflow and ambient precision.
    try:
        with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)):
            values = tuple(
                (right.close - left.close) / left.close
                for left, right in zip(bars, bars[1:], strict=False)
            )
        result = tuple(float(value) for value in values)
    except (ValueError, OverflowError, ArithmeticError):
        raise JointPortfolioInputUnavailable("returns_not_representable") from None
    if any(
        not np.isfinite(converted) or converted <= -1 or (original != 0 and converted == 0)
        for original, converted in zip(values, result, strict=True)
    ):
        raise JointPortfolioInputUnavailable("returns_not_representable")
    return result


def _population_covariance(returns: np.ndarray) -> np.ndarray:
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            relative = returns - returns[0]
            centered = relative - relative.mean(axis=0)
            covariance = centered.T @ centered / CONTEXT_RETURNS
            # Enforce exact symmetric storage without clipping eigenvalues.
            covariance = covariance * 0.5 + covariance.T * 0.5
        if not np.isfinite(covariance).all():
            raise JointPortfolioInputUnavailable("covariance_not_representable")
        if np.any(np.any(centered != 0, axis=0) & (np.diag(covariance) == 0)):
            raise JointPortfolioInputUnavailable("covariance_not_representable")
        scale = float(np.abs(covariance).max())
        if scale and np.linalg.eigvalsh(covariance / scale)[0] < -64 * np.finfo(np.float64).eps:
            raise JointPortfolioInputUnavailable("covariance_not_psd")
    except (FloatingPointError, np.linalg.LinAlgError):
        raise JointPortfolioInputUnavailable("covariance_not_representable") from None
    return covariance


def build_joint_portfolio_covariance(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    *,
    vintage_ref_by_symbol: Mapping[str, str],
    scheduled_dates: tuple[date, ...],
    decision_at: datetime,
) -> JointPortfolioCovarianceInput:
    """Build 252 fractional simple returns and population covariance (ddof=0).

    Exactly 253 caller-scheduled past UTC session dates are required. Dates are
    not inferred from weekdays, source intersection, full future coverage or a
    frequency guess. Each selected D1 start must be UTC midnight, with end at
    or before the common cutoff. Rows retain caller date order; columns always
    follow SYMBOLS regardless of mapping order. Zero volume/variance are valid.

    Vintage refs must match, but equality is a caller binding, not source-byte
    verification or a guarantee that Bar carries adjusted values. The returned
    immutable numeric tuples are private. Float64 Gram covariance is PSD up to
    roundoff; overflow/underflow failures are scoped, never clipped or repaired.
    """
    _contract(isinstance(bars_by_symbol, Mapping), "source_columns")
    sources = dict(bars_by_symbol)
    _contract(set(sources) == set(SYMBOLS), "source_columns")
    _contract(isinstance(vintage_ref_by_symbol, Mapping), "source_vintage_columns")
    vintages = dict(vintage_ref_by_symbol)
    _contract(set(vintages) == set(SYMBOLS), "source_vintage_columns")
    _contract(
        all(isinstance(value, str) and bool(value.strip()) for value in vintages.values()),
        "source_vintage_ref",
    )
    if len(set(vintages.values())) != 1:
        raise JointPortfolioInputUnavailable("source_vintage_mismatch")
    _contract(
        type(scheduled_dates) is tuple
        and len(scheduled_dates) == CONTEXT_CLOSES
        and all(type(day) is date for day in scheduled_dates)
        and all(
            left < right for left, right in zip(scheduled_dates, scheduled_dates[1:], strict=False)
        ),
        "scheduled_dates",
    )
    _contract(isinstance(decision_at, datetime), "decision_at")
    decision_at = require_utc(decision_at, "decision_at")
    _contract(scheduled_dates[-1] < decision_at.date(), "scheduled_dates_not_past")
    selected = tuple(
        _required_bars(
            sources[symbol], symbol=symbol, dates=scheduled_dates, decision_at=decision_at
        )
        for symbol in SYMBOLS
    )
    returns = np.asarray(tuple(_simple_returns(bars) for bars in selected), dtype=np.float64).T
    covariance = _population_covariance(returns)
    return JointPortfolioCovarianceInput(
        symbols=SYMBOLS,
        scheduled_dates=scheduled_dates,
        decision_at=decision_at,
        completed_through=selected[0][-1].end_ts,
        source_vintage_ref=vintages[SYMBOLS[0]],
        returns=tuple(tuple(float(value) for value in row) for row in returns),
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
    )

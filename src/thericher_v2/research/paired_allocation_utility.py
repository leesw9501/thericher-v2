"""Joint two-ETF/cash NAV with one entry and full liquidation each session.

Columns are (QQQ, SPY, cash) for weights and (QQQ, SPY) for gross growth.
Weights specify fractions of post-entry-fee NAV, not pre-fee cash. One shared
cash balance compounds across sessions; no stock earns an overnight return.
Fractional notionals, one common proportional fee rate, and exact endpoint
fills are analytical assumptions, not local-paper or broker fill parity.

Callers build causal contexts with build_paired_completed_context and freeze
every comparison weight before inspecting entry/exit outcomes. These array
functions cannot attest source identity, timestamps, availability or that
ordering. They perform no loading, fitting, persistence or broker IO.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

import numpy as np

from thericher_v2.contracts import Timeframe, require_utc
from thericher_v2.market.resample import SessionWindow
from thericher_v2.research.tiingo_monthly_holding_development import rebalance

_SIMPLEX_TOLERANCE = 1e-12


def daily_flat_execution_times(
    session: SessionWindow, *, observed_at: datetime
) -> tuple[datetime, datetime]:
    """Next M1 OPEN entry and last session M1 OPEN exit; no calendar inference."""
    if not isinstance(session, SessionWindow) or not isinstance(observed_at, datetime):
        raise ValueError("daily_flat_session_type")
    observed_at = require_utc(observed_at, "observed_at")
    minute = Timeframe.M1.duration
    if (
        (observed_at - session.open_ts) % minute
        or session.duration % minute
        or session.open_ts.second
        or session.open_ts.microsecond
        or session.duration >= timedelta(days=1)
        or not session.open_ts <= observed_at < session.close_ts
    ):
        raise ValueError("daily_flat_session_geometry")
    entry, exit_ = observed_at + minute, session.close_ts - minute
    if entry >= exit_:
        raise ValueError("daily_flat_holding_interval")
    return entry, exit_


def _fee(cost_bps: float | Decimal) -> float:
    if type(cost_bps) not in (int, float, Decimal):
        raise ValueError("daily_flat_cost")
    if not Decimal(str(cost_bps)).is_finite() or not 0 <= cost_bps < 10000:
        raise ValueError("daily_flat_cost")
    return float(cost_bps) / 10000


def _growth(growth: np.ndarray) -> np.ndarray:
    if (
        not isinstance(growth, np.ndarray)
        or growth.dtype != np.float64
        or growth.ndim != 2
        or growth.shape[1] != 2
        or growth.shape[0] == 0
        or not np.isfinite(growth).all()
        or not (growth > 0).all()
    ):
        raise ValueError("daily_flat_growth")
    return growth


def _weights(weights: np.ndarray, rows: int) -> np.ndarray:
    if (
        not isinstance(weights, np.ndarray)
        or weights.dtype != np.float64
        or weights.shape != (rows, 3)
        or not np.isfinite(weights).all()
        or not ((weights >= 0) & (weights <= 1)).all()
    ):
        raise ValueError("daily_flat_weights")
    totals = weights.sum(axis=1)
    if not (np.abs(totals - 1) <= _SIMPLEX_TOLERANCE).all():
        raise ValueError("daily_flat_simplex")
    # Only floating-point simplex dust is normalized, never a sizing violation.
    return weights / totals[:, None]


def numpy_daily_flat_nav(weights, growth, *, cost_bps=3) -> np.ndarray:
    """Daily liquidation NAV from initial cash1; weights/growth are float64 arrays."""
    factors = _growth(growth)
    allocation = _weights(weights, len(factors))
    fee = _fee(cost_bps)
    risk = allocation[:, :2].sum(axis=1)
    marked_stock = (allocation[:, :2] * factors).sum(axis=1)
    # Entry solves S = risk*(cash - fee*S); liquidation charges marked stock.
    daily = (allocation[:, 2] + (1 - fee) * marked_stock) / (1 + fee * risk)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        nav = np.cumprod(daily)
    if not np.isfinite(nav).all() or not (nav > 0).all():
        raise ValueError("daily_flat_nav")
    nav.setflags(write=False)
    return nav


def torch_daily_flat_nav(torch, weights, growth, *, cost_bps=3):
    """Autograd-safe identical NAV; weights are a float64 tensor, growth is fixed."""
    factors = _growth(growth)
    fee = _fee(cost_bps)
    if (
        not isinstance(weights, torch.Tensor)
        or weights.dtype != torch.float64
        or tuple(weights.shape) != (len(factors), 3)
        or not bool(torch.isfinite(weights).all())
        or not bool(((weights >= 0) & (weights <= 1)).all())
    ):
        raise ValueError("daily_flat_weights")
    totals = weights.sum(dim=1)
    if not bool((torch.abs(totals - 1) <= _SIMPLEX_TOLERANCE).all()):
        raise ValueError("daily_flat_simplex")
    allocation = weights / totals[:, None]
    fixed_growth = torch.tensor(factors.copy(), dtype=torch.float64, device=weights.device)
    risk = allocation[:, :2].sum(dim=1)
    marked_stock = (allocation[:, :2] * fixed_growth).sum(dim=1)
    daily = (allocation[:, 2] + (1 - fee) * marked_stock) / (1 + fee * risk)
    nav = torch.cumprod(daily, dim=0)
    if not bool(torch.isfinite(nav).all()) or not bool((nav > 0).all()):
        raise ValueError("daily_flat_nav")
    return nav


def decimal_daily_flat_nav(weights, growth, *, cost_bps=3) -> tuple[Decimal, ...]:
    """Decimal50 replay of one shared cash balance using the existing fee solver.

    No monthly marks/carry or independently funded sleeves are imported. Floating
    inputs are converted through their decimal text; this is a numerical reference,
    not an assertion of additional price precision.
    """
    factors = _growth(growth)
    allocation = _weights(weights, len(factors))
    _fee(cost_bps)
    navs = []
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        fee, cash = Decimal(str(cost_bps)) / 10000, Decimal(1)
        for row, gains in zip(allocation, factors, strict=True):
            values = tuple(Decimal(str(value)) for value in row)
            total = sum(values, Decimal(0))
            qqq, spy, _ = (value / total for value in values)
            risk = qqq + spy
            stock, remaining_cash, _, _ = rebalance(Decimal(0), cash, risk, fee)
            qqq_notional = stock * qqq / risk if risk else Decimal(0)
            spy_notional = stock - qqq_notional
            exit_stock = qqq_notional * Decimal(str(gains[0])) + spy_notional * Decimal(
                str(gains[1])
            )
            final_stock, cash, _, _ = rebalance(
                exit_stock, remaining_cash + exit_stock, Decimal(0), fee
            )
            if final_stock != 0 or cash <= 0 or not cash.is_finite():
                raise ValueError("daily_flat_nav")
            navs.append(cash)
    return tuple(navs)

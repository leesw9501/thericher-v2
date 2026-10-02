"""Small research-only policies and a differentiable adjusted-mark NAV proxy.

Inputs are already source/calendar-bound by the caller. Outcomes are separate
from model features; no loading, fitting, artifact writing or broker IO occurs.
This mirrors the monthly Decimal ledger, not actual shares, fills or PnL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, localcontext

import numpy as np

from .adjusted_monthly_policy_inputs import AdjustedMonthlyPolicyInputs


@dataclass(frozen=True, repr=False)
class MonthlyUtilityArrays:
    symbol: str
    decision_dates: tuple[date, ...]
    source_dates: tuple[date, ...]
    features: np.ndarray
    open_gaps: np.ndarray
    close_growth: np.ndarray
    valid_days: np.ndarray


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ValueError(category)


def prepare_monthly_utility_arrays(
    records: tuple[AdjustedMonthlyPolicyInputs, ...],
) -> MonthlyUtilityArrays:
    """One ordered continuous sleeve; no missing month/day or mixed instrument.

    The first OPEN starts NAV1, so its preceding overnight gap is not earned.
    Each later OPEN carries the preceding owned stock through its overnight gap.
    Padded daily marks are masked out, never treated as zero-return observations.
    """
    _require(type(records) is tuple and bool(records), "monthly_records")
    _require(all(type(r) is AdjustedMonthlyPolicyInputs for r in records), "monthly_record_type")
    for record in records:
        record.__post_init__()
        record.identity.__post_init__()
        record.model.__post_init__()
        record.payoff.__post_init__()
    symbol = records[0].identity.symbol
    _require(all(r.identity.symbol == symbol for r in records), "monthly_symbol")
    for previous, current in zip(records, records[1:], strict=False):
        a, b = previous.identity.decision_date, current.identity.decision_date
        _require(b.year * 12 + b.month == a.year * 12 + a.month + 1, "monthly_gap")
        _require(
            previous.payoff.target_dates[-1] == current.model.source_date
            and previous.identity.month_bounds[1] == current.identity.month_bounds[0]
            and previous.payoff.target_dates[-1] < current.payoff.target_dates[0],
            "monthly_carry_binding",
        )
    with localcontext() as context:
        context.prec, context.rounding = 50, ROUND_HALF_EVEN
        features = np.asarray(
            [[float(v / 100) for v in r.model.close_returns_bps] for r in records],
            dtype=np.float32,
        )
    gaps = np.asarray([float(r.payoff.open_over_previous_close) for r in records], dtype=np.float64)
    lengths = [len(r.payoff.target_dates) for r in records]
    growth = np.ones((len(records), max(lengths)), dtype=np.float64)
    valid = np.zeros(growth.shape, dtype=np.bool_)
    for i, record in enumerate(records):
        growth[i, : lengths[i]] = [float(v) for v in record.payoff.close_over_entry_open]
        valid[i, : lengths[i]] = True
    _require(
        np.isfinite(features).all()
        and np.isfinite(gaps).all()
        and (gaps > 0).all()
        and np.isfinite(growth).all()
        and (growth > 0).all(),
        "monthly_numeric_range",
    )
    features = np.clip(features, -20, 20)[..., None]
    for array in (features, gaps, growth, valid):
        array.setflags(write=False)
    return MonthlyUtilityArrays(
        symbol,
        tuple(r.identity.decision_date for r in records),
        tuple(r.model.source_date for r in records),
        features,
        gaps,
        growth,
        valid,
    )


def build_torch_monthly_policy(torch, architecture: str):
    """A fixed architecture, no pretrained code, symbol feature or position state."""
    _require(architecture in {"linear", "lstm"}, "monthly_architecture")

    class Policy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = (
                torch.nn.LSTM(1, 16, num_layers=1, batch_first=True, dropout=0)
                if architecture == "lstm"
                else None
            )
            self.head = torch.nn.Linear(16 if self.encoder is not None else 252, 1)

        def forward(self, features):
            if features.ndim != 3 or tuple(features.shape[1:]) != (252, 1):
                raise ValueError("monthly_feature_shape")
            encoded = features[:, :, 0]
            if self.encoder is not None:
                _, (hidden, _) = self.encoder(features)
                encoded = hidden[-1]
            return torch.sigmoid(self.head(encoded)).squeeze(-1)

    return Policy()


def _array_shapes(data: MonthlyUtilityArrays) -> None:
    _require(type(data) is MonthlyUtilityArrays, "monthly_array_type")
    n = len(data.decision_dates)
    _require(
        n > 0
        and len(data.source_dates) == n
        and data.features.shape == (n, 252, 1)
        and data.open_gaps.shape == (n,)
        and data.close_growth.ndim == 2
        and data.close_growth.shape[0] == n
        and data.valid_days.shape == data.close_growth.shape
        and data.valid_days.dtype == np.bool_,
        "monthly_array_shape",
    )
    lengths = data.valid_days.sum(axis=1)
    _require(
        (lengths > 0).all()
        and np.array_equal(
            data.valid_days, np.arange(data.close_growth.shape[1])[None, :] < lengths[:, None]
        )
        and np.isfinite(data.open_gaps).all()
        and (data.open_gaps > 0).all()
        and np.isfinite(data.close_growth).all()
        and (data.close_growth > 0).all(),
        "monthly_array_numeric",
    )


def torch_monthly_nav(torch, weights, data: MonthlyUtilityArrays, *, cost_bps: float = 10.0):
    """Daily CLOSE NAV including initial fee and final liquidation, autograd-safe.

    Inference calls need the same frozen payoff marks, not future model inputs.
    Piecewise target solving sets stock / post-fee NAV to w exactly. Costs use
    traded notional, not |w_t-w_{t-1}| or a daily round-trip approximation.
    """
    _array_shapes(data)
    _require(
        type(cost_bps) in (int, float) and np.isfinite(cost_bps) and 0 <= cost_bps < 10000,
        "monthly_cost",
    )
    _require(
        weights.ndim == 1 and weights.shape[0] == len(data.decision_dates), "monthly_weights_shape"
    )
    _require(
        bool(torch.isfinite(weights).all()) and bool(((weights >= 0) & (weights <= 1)).all()),
        "monthly_weights_domain",
    )
    weights = weights.to(dtype=torch.float64)
    gaps = torch.tensor(data.open_gaps.copy(), dtype=torch.float64, device=weights.device)
    growth = torch.tensor(data.close_growth.copy(), dtype=torch.float64, device=weights.device)
    lengths = data.valid_days.sum(axis=1).tolist()
    fee = cost_bps / 10000
    cash, stock = weights.new_tensor(1), weights.new_tensor(0)
    days = []
    for i, length in enumerate(lengths):
        if i:
            stock = stock * growth[i - 1, lengths[i - 1] - 1] * gaps[i]
        nav = cash + stock
        w = weights[i]
        bought = w * (nav + fee * stock) / (1 + fee * w)
        sold = w * (nav - fee * stock) / (1 - fee * w)
        target = torch.where(w * nav >= stock, bought, sold)
        cash = nav - target - fee * torch.abs(target - stock)
        stock = target
        marked = cash + stock * growth[i, :length]
        if i == len(lengths) - 1:
            # Replace only final CLOSE: there is no extra synthetic trading day.
            marked = torch.cat(
                (marked[:-1], (marked[-1] - fee * stock * growth[i, length - 1])[None])
            )
        days.append(marked)
    result = torch.cat(days)
    _require(bool(torch.isfinite(result).all()) and bool((result > 0).all()), "monthly_NAV_domain")
    return result


def numpy_monthly_nav(weights, data: MonthlyUtilityArrays, *, cost_bps: float = 10.0):
    """CPU numerical reference; fitted parameters or future feature reads absent."""
    _array_shapes(data)
    _require(
        type(cost_bps) in (int, float) and np.isfinite(cost_bps) and 0 <= cost_bps < 10000,
        "monthly_cost",
    )
    values = np.asarray(weights, dtype=np.float64)
    _require(
        values.shape == (len(data.decision_dates),)
        and np.isfinite(values).all()
        and ((values >= 0) & (values <= 1)).all(),
        "monthly_weights_domain",
    )
    fee, cash, stock = cost_bps / 10000, 1.0, 0.0
    lengths = data.valid_days.sum(axis=1).tolist()
    days = []
    for i, length in enumerate(lengths):
        if i:
            stock *= data.close_growth[i - 1, lengths[i - 1] - 1] * data.open_gaps[i]
        nav, weight = cash + stock, values[i]
        if weight * nav >= stock:
            target = weight * (nav + fee * stock) / (1 + fee * weight)
        else:
            target = weight * (nav - fee * stock) / (1 - fee * weight)
        cash, stock = nav - target - fee * abs(target - stock), target
        marked = cash + stock * data.close_growth[i, :length]
        if i == len(lengths) - 1:
            marked[-1] -= fee * stock * data.close_growth[i, length - 1]
        days.extend(marked.tolist())
    result = np.asarray(days, dtype=np.float64)
    _require(np.isfinite(result).all() and (result > 0).all(), "monthly_NAV_domain")
    return result


def numpy_net_utility(nav) -> float:
    """Same fixed objective without Torch for isolated CPU parity tests."""
    values = np.asarray(nav, dtype=np.float64)
    _require(
        values.ndim == 1 and values.size > 0 and np.isfinite(values).all() and (values > 0).all(),
        "monthly_NAV_domain",
    )
    logs = np.log(values / np.concatenate(([1.0], values[:-1])))
    return float(252 * (logs.mean() - logs.var()))


def torch_net_utility(torch, nav):
    """Fixed daily log-growth minus population log-risk, annualized with252.

    This is our simple objective, NOT DeePM Sharpe/SoftMin replication. Initial
    and final fees participate in the same observed-day return sequence.
    """
    _require(
        nav.ndim == 1
        and nav.numel() > 0
        and bool(torch.isfinite(nav).all())
        and bool((nav > 0).all()),
        "monthly_NAV_domain",
    )
    logs = torch.log(nav / torch.cat((nav.new_ones(1), nav[:-1])))
    return 252 * (logs.mean() - logs.var(unbiased=False))

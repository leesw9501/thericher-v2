"""Float64 shared-cash adjusted-mark replay, not broker or fill-parity evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import product

ASSET_ORDER = ("SPY", "QQQ", "IWM", "cash")
WEIGHT_SUM_TOLERANCE = 64 * 2.0**-52
FACE_TOLERANCE = 32 * 2.0**-52
RESIDUAL_TOLERANCE = 256 * 2.0**-52
CASHFLOW_TOLERANCE = 1e-10
_FACES = tuple(product((-1.0, 1.0), repeat=3))


class DifferentiableThreeAssetNavError(ValueError):
    """Categorical input/numeric error; never includes supplied financial values."""


@dataclass(frozen=True, eq=False)
class DifferentiableThreeAssetReplay:
    nav: object = field(repr=False)
    log_returns: object = field(repr=False)
    fees: object = field(repr=False)
    traded_notional: object = field(repr=False)
    cash: object = field(repr=False)


def _require(condition, category):
    if not bool(condition):
        raise DifferentiableThreeAssetNavError(category)


def _fraction(torch, weights, alpha, fee):
    signs = weights.new_tensor(_FACES)
    numerator = 1 + fee * (alpha[:, None, :] * signs).sum(dim=2)
    denominator = 1 + fee * (weights[:, None, :] * signs).sum(dim=2)
    candidates = numerator / denominator
    delta = weights[:, None, :] * candidates[:, :, None] - alpha[:, None, :]
    oriented = signs * delta
    bounded = (candidates > 0) & (candidates <= 1 + RESIDUAL_TOLERANCE)
    strict = (oriented >= 0).all(dim=2) & bounded
    scale = 1 + alpha[:, None, :].abs() + (weights[:, None, :] * candidates[:, :, None]).abs()
    rounded = (oriented >= -FACE_TOLERANCE * scale).all(dim=2) & bounded
    # Prefer exact signs, including arbitrarily small real trades, over roundoff ties.
    valid = torch.where(strict.any(dim=1, keepdim=True), strict, rounded)
    _require(torch.isfinite(candidates).all() & valid.any(dim=1).all(), "fee_face_unavailable")
    index = valid.to(dtype=torch.int64).argmax(dim=1)
    fraction = candidates.gather(1, index[:, None]).squeeze(1)
    differences = torch.where(valid, (candidates - fraction[:, None]).abs(), 0)
    _require((differences <= RESIDUAL_TOLERANCE).all(), "fee_faces_disagree")
    delta = weights * fraction[:, None] - alpha
    # At exact zero, use the selected face's one-sided derivative, not abs'(0)=0.
    absolute = torch.where(delta == 0, signs[index] * delta, delta.abs())
    turnover = absolute.sum(dim=1)
    residual = fraction + fee * turnover - 1
    _require((residual.abs() <= RESIDUAL_TOLERANCE).all(), "fee_residual")
    return fraction, turnover


def replay_torch(open_prices, close_prices, weights, cost_bps) -> DifferentiableThreeAssetReplay:
    """Replay daily OPEN targets from NAV1; final row includes CLOSE liquidation.

    Inputs are float64 strided tensors [N,3], [N,3], [N,4] on one CPU/CUDA
    device, in ASSET_ORDER. Outputs are [N]. Cost is a Python int/float or a
    float64 scalar tensor on that device, in [0,100] bps. No dtype conversion,
    normalization, model, calendar, IO or CUDA availability query is performed.

    Float row sums admit WEIGHT_SUM_TOLERANCE without changing their values.
    Face consistency admits FACE_TOLERANCE relative roundoff only if no strict
    face exists; the first valid (-1,+1) lexicographic face is selected. Root
    agreement/residuals admit RESIDUAL_TOLERANCE. Kink gradients follow that
    face, not a unique derivative across it or every boundary-feasible direction.
    Relative normalized cashflow admits CASHFLOW_TOLERANCE (1e-10).
    The caller owns causal input construction and aligned scheduled-day marks.
    """
    import torch

    for value in (open_prices, close_prices, weights):
        _require(isinstance(value, torch.Tensor), "input_tensor")
        _require(value.dtype == torch.float64 and value.layout == torch.strided, "input_dtype")
    _require(
        open_prices.ndim == 2
        and open_prices.shape[0] > 0
        and open_prices.shape[1] == 3
        and close_prices.shape == open_prices.shape
        and weights.shape == (open_prices.shape[0], 4),
        "input_shape",
    )
    _require(
        weights.device.type in {"cpu", "cuda"}
        and open_prices.device == close_prices.device == weights.device,
        "input_device",
    )
    _require(
        torch.isfinite(open_prices).all()
        & torch.isfinite(close_prices).all()
        & (open_prices > 0).all()
        & (close_prices > 0).all(),
        "price_domain",
    )
    _require(
        torch.isfinite(weights).all()
        & ((weights >= 0) & (weights <= 1)).all()
        & ((weights.sum(dim=1) - 1).abs() <= WEIGHT_SUM_TOLERANCE).all(),
        "weight_domain",
    )
    if isinstance(cost_bps, torch.Tensor):
        _require(
            cost_bps.ndim == 0
            and cost_bps.dtype == torch.float64
            and cost_bps.layout == torch.strided
            and cost_bps.device == weights.device,
            "cost_bps_invalid",
        )
        _require(torch.isfinite(cost_bps) & (cost_bps >= 0) & (cost_bps <= 100), "cost_bps_invalid")
        fee = cost_bps / 10000
    else:
        _require(
            type(cost_bps) in (int, float) and 0 <= cost_bps <= 100 and math.isfinite(cost_bps),
            "cost_bps_invalid",
        )
        fee = weights.new_tensor(cost_bps / 10000)

    stock, target_cash = weights[:, :3], weights[:, 3]
    previous = torch.cat((weights.new_tensor([[0, 0, 0, 1]]), weights[:-1]), dim=0)
    # Previous post-OPEN quantities persist; CLOSE marking does not reset them.
    drift = torch.cat((open_prices.new_ones((1, 3)), open_prices[1:] / open_prices[:-1]), dim=0)
    close_growth = close_prices / open_prices
    holdings = previous[:, :3] * drift
    drift_nav = previous[:, 3] + holdings.sum(dim=1)
    _require(
        torch.isfinite(drift).all()
        & torch.isfinite(close_growth).all()
        & torch.isfinite(drift_nav).all()
        & (drift_nav > 0).all()
        & (close_growth > 0).all(),
        "numeric_range",
    )
    alpha = holdings / drift_nav[:, None]
    fraction, turnover_fraction = _fraction(torch, stock, alpha, fee)
    post_open_nav = torch.cumprod(drift_nav * fraction, dim=0)
    previous_post_open = torch.cat((weights.new_ones(1), post_open_nav[:-1]))
    pre_open_nav = previous_post_open * drift_nav
    stock_close = (stock * close_growth).sum(dim=1)
    mark = target_cash + stock_close
    close_nav = post_open_nav * mark
    exit_notional = post_open_nav[-1] * stock_close[-1]
    exit_fee = fee * exit_notional
    nav = torch.cat((close_nav[:-1], (close_nav[-1] - exit_fee)[None]))
    liquidation = torch.cat((weights.new_zeros(weights.shape[0] - 1), exit_notional[None]))
    traded_notional = pre_open_nav * turnover_fraction + liquidation
    fees = fee * traded_notional
    cash = torch.cat((target_cash[:-1] * post_open_nav[:-1], nav[-1:]))
    log_returns = torch.log(nav) - torch.log(torch.cat((weights.new_ones(1), nav[:-1])))
    balance = fraction * weights.sum(dim=1) + fee * turnover_fraction - 1
    _require((balance.abs() <= CASHFLOW_TOLERANCE).all(), "cashflow_residual")
    _require(
        torch.isfinite(nav).all()
        & (nav > 0).all()
        & torch.isfinite(log_returns).all()
        & torch.isfinite(fees).all()
        & torch.isfinite(traded_notional).all()
        & torch.isfinite(cash).all()
        & (fees >= 0).all()
        & (traded_notional >= 0).all()
        & (cash >= 0).all(),
        "numeric_range",
    )
    return DifferentiableThreeAssetReplay(nav, log_returns, fees, traded_notional, cash)

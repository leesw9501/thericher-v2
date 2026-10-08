"""Pure causal risk inputs and differentiable closed21-group cash accounting.

No source IO, fit, dispatch, broker or promotion. Caller freezes the complete
calendar/vintage and seals actions before supplying forward marks. Raw KIS
prices are not relabeled as adjusted. Torch is optional and imported on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext

import numpy as np

from thericher_v2.research import kis_cross_asset_erc_development as controls
from thericher_v2.research import kis_cross_asset_relative_allocation as allocation
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_daily_risk_input import (
    DailyRiskFeatures,
    prepare_daily_features,
)
from thericher_v2.research.cross_asset_hedge_failure_input import CONTEXT, _select

NAME = "kis-cross-asset-direct-risk-capped-utility-development-v1"
SYMBOLS = allocation.SYMBOLS
HORIZON, UPDATES, SEED, SECONDS = 21, 512, 101, 300
POLICIES = ("gru", "constant", "erc", "minvar", "inverse_volatility", "equal_thirds", "cash")
PARITY_TOLERANCE = 1e-10


class DirectUtilityError(ValueError):
    """Source-safe categorical failure, without numeric or private values."""


def require(condition, code):
    if not condition:
        raise DirectUtilityError(code)


def configuration():
    return dict(
        name=NAME,
        symbols=list(SYMBOLS),
        policies=list(POLICIES),
        cells=42,
        context=[6, 63],
        required_closes=64,
        horizon=HORIZON,
        covariance="63 simple past returns; population;25% diagonal shrink ONCE",
        risk="sigmoid intensity*min(1,.10/sqrt(252*w'C_shrunk*w));no leverage",
        gru=dict(
            input_size=6,
            hidden_size=16,
            layers=1,
            output_size=4,
            dropout=0,
            seed=SEED,
            updates=UPDATES,
            dtype="float32",
        ),
        constant=dict(logits=4, initial_logits="zero", updates=UPDATES, device="cpu"),
        optimizer=dict(name="AdamW", lr=0.001, weight_decay=0.01),
        path_dtype="float64",
        train_cost_bps_side="10",
        costs_bps_side=["2.5", "5", "10"],
        accounting="continuous NAV1;entry OPEN/21st CLOSE exit;actual notional fees;cash tail",
        objective="252*(mean all daily log returns-5*population variance)",
        kill="both views10bps growth>0;GRU utility>all six controls by>1e-10",
        family_seconds=SECONDS,
        fits=2,
        actual_fits=0,
        source_io=False,
        paper_input=False,
        lineage=["joint-d1-direct-utility-development-v1", allocation.NAME],
    )


def _covariance(values):
    c = np.asarray(values, dtype=np.float64)
    require(
        c.shape == (3, 3) and np.isfinite(c).all() and np.array_equal(c, c.T), "covariance_values"
    )
    scale = float(np.abs(c).max())
    require(
        scale > 0
        and (np.diag(c) > 0).all()
        and np.linalg.eigvalsh(c / scale)[0] >= -64 * np.finfo(float).eps,
        "covariance_values",
    )
    return c


@dataclass(frozen=True, slots=True)
class CausalRiskContext:
    features: object = field(repr=False)
    covariance: tuple[tuple[float, ...], ...] = field(repr=False)

    def __post_init__(self):
        require(type(self.features) is DailyRiskFeatures, "feature_type")
        self.features.__post_init__()
        require(
            type(self.covariance) is tuple and all(type(row) is tuple for row in self.covariance),
            "covariance_type",
        )
        _covariance(self.covariance)

    def safe_facts(self):
        return dict(
            self.features.safe_facts(),
            covariance_shape=(3, 3),
            covariance_returns=63,
            covariance_shrinkage="not_applied_until_allocation",
            paper_input=False,
        )


def prepare_context(rows_by_symbol, *, scheduled_history, entry_session, decision_at, vintage_ref):
    features = prepare_daily_features(
        rows_by_symbol,
        scheduled_history=scheduled_history,
        entry_session=entry_session,
        decision_at=decision_at,
        vintage_ref=vintage_ref,
    )
    dates = tuple(s.session_date for s in scheduled_history)
    rows = _select(rows_by_symbol, dict.fromkeys(dates, ("close",)), vintage_ref)
    with localcontext(CONTEXT):
        values = tuple(
            tuple(
                (r[b]["close"] - r[a]["close"]) / r[a]["close"]
                for a, b in zip(dates, dates[1:], strict=False)
            )
            for r in rows
        )
    returns = np.asarray(values, dtype=np.float64).T
    require(
        np.isfinite(returns).all()
        and (returns > -1).all()
        and all(
            v == 0 or x != 0
            for col, converted in zip(values, returns.T, strict=True)
            for v, x in zip(col, converted, strict=True)
        ),
        "returns_not_representable",
    )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            relative = returns - returns[0]
            centered = relative - relative.mean(axis=0)
            c = centered.T @ centered / 63
            c = _covariance(0.5 * c + 0.5 * c.T)
    except (FloatingPointError, np.linalg.LinAlgError):
        raise DirectUtilityError("covariance_numeric") from None
    return CausalRiskContext(features, tuple(tuple(float(x) for x in row) for row in c))


def fixed_controls(context):
    """Fresh63-return allocations; no prior controls/actions/results are read."""
    require(type(context) is CausalRiskContext, "context_type")
    context.__post_init__()
    targets, _ = controls.risk_allocations(context.covariance)
    return {"erc": targets["candidate"], **{p: targets[p] for p in POLICIES[3:]}}


def _tensor(torch, value, shape, code):
    require(
        isinstance(value, torch.Tensor)
        and value.dtype == torch.float64
        and value.layout == torch.strided
        and tuple(value.shape) == shape
        and bool(torch.isfinite(value).all()),
        code,
    )


def risk_capped_weights(logits, raw_covariance):
    """Differentiable simplex mix and cash intensity, same declared covariance cap.

    Takes ONLY previously prepared past covariance, never payoff/forward marks.
    Model fp32 outputs must be explicitly cast to float64 by the caller.
    """
    import torch

    require(isinstance(logits, torch.Tensor) and logits.ndim == 2, "logit_shape")
    count = logits.shape[0]
    require(count > 0, "logit_shape")
    _tensor(torch, logits, (count, 4), "logit_values")
    _tensor(torch, raw_covariance, (count, 3, 3), "covariance_values")
    require(raw_covariance.device == logits.device, "input_device")
    diagonal = raw_covariance.diagonal(dim1=-2, dim2=-1)
    scale = raw_covariance.abs().amax(dim=(-2, -1))
    require(
        bool((diagonal > 0).all())
        and bool((raw_covariance == raw_covariance.transpose(-1, -2)).all())
        and bool(
            (
                torch.linalg.eigvalsh(raw_covariance / scale[:, None, None])[:, 0]
                >= -64 * torch.finfo(torch.float64).eps
            ).all()
        ),
        "covariance_values",
    )
    shrunk = 0.75 * raw_covariance + 0.25 * torch.diag_embed(diagonal)
    mix = logits[:, :3].softmax(-1)
    variance = torch.einsum("bi,bij,bj->b", mix, shrunk, mix)
    require(bool(torch.isfinite(variance).all()) and bool((variance > 0).all()), "risk_numeric")
    cap = torch.minimum(torch.ones_like(variance), 0.10 / torch.sqrt(252 * variance))
    risky = mix * (logits[:, 3].sigmoid() * cap)[:, None]
    cash = 1 - risky.sum(-1, keepdim=True)
    require(bool((cash >= 0).all()), "weight_numeric")
    return torch.cat((risky, cash), -1)


@dataclass(frozen=True, slots=True)
class ClosedGroupReplay:
    nav: object = field(repr=False)
    log_returns: object = field(repr=False)
    fees: object = field(repr=False)
    traded_notional: object = field(repr=False)
    cash: object = field(repr=False)
    entry_quantities: object = field(repr=False)


def replay_closed_groups(
    entry_open, daily_close, weights, cost_bps, *, tail_days=0, initial_nav=1.0
):
    """Vectorized21-day flat-to-flat groups; unchanged shares, continuous capital.

    Shape [G,3] entry OPENs, [G,21,3] CLOSEs, [G,4] post-fee target weights.
    No intermediate OPENs or daily target repeats. Caller owns all scheduled
    mark support; missing/nonfinite values fail, never delete a day/group.
    Float64 ideal quantities omit only the Decimal ledger's1e-40 unit rounding.
    """
    import torch

    require(isinstance(entry_open, torch.Tensor) and entry_open.ndim == 2, "open_shape")
    groups = entry_open.shape[0]
    require(groups > 0, "open_shape")
    _tensor(torch, entry_open, (groups, 3), "open_values")
    _tensor(torch, daily_close, (groups, HORIZON, 3), "close_values")
    _tensor(torch, weights, (groups, 4), "weight_values")
    require(entry_open.device == daily_close.device == weights.device, "input_device")
    require(bool((entry_open > 0).all()) and bool((daily_close > 0).all()), "price_domain")
    require(
        bool(((weights >= 0) & (weights <= 1)).all())
        and bool(((weights.sum(-1) - 1).abs() <= 64 * torch.finfo(torch.float64).eps).all()),
        "weight_domain",
    )
    require(type(tail_days) is int and 0 <= tail_days < HORIZON, "tail_days")
    require(
        type(initial_nav) in (int, float) and np.isfinite(initial_nav) and initial_nav > 0,
        "initial_nav",
    )
    require(
        type(cost_bps) in (int, float) and np.isfinite(cost_bps) and 0 <= cost_bps <= 100,
        "cost_bps",
    )
    fee = cost_bps / 10000
    invested = weights[:, :3].sum(-1)
    post_fraction = 1 / (1 + fee * invested)
    units = weights[:, :3] * post_fraction[:, None] / entry_open
    risky_marks = (units[:, None, :] * daily_close).sum(-1)
    cash = weights[:, 3] * post_fraction
    marks = cash[:, None] + risky_marks
    terminal = marks[:, -1] - fee * risky_marks[:, -1]
    factors = torch.cat((marks[:, :-1], terminal[:, None]), 1)
    require(bool(torch.isfinite(factors).all()) and bool((factors > 0).all()), "nav_numeric")
    entering = initial_nav * torch.cumprod(torch.cat((terminal.new_ones(1), terminal[:-1])), 0)
    navs = entering[:, None] * factors
    entry_notional = entering * post_fraction * invested
    exit_notional = entering * risky_marks[:, -1]
    zero = navs.new_zeros((groups, HORIZON - 2))
    notional = torch.cat((entry_notional[:, None], zero, exit_notional[:, None]), 1)
    cashes = torch.cat(((entering * cash)[:, None].expand(-1, HORIZON - 1), navs[:, -1:]), 1)
    path = torch.cat((navs.flatten(), navs[-1, -1].expand(tail_days)))
    traded = torch.cat((notional.flatten(), path.new_zeros(tail_days)))
    cash_path = torch.cat((cashes.flatten(), path[-1].expand(tail_days)))
    logs = path.log() - torch.cat((path.new_tensor([initial_nav]), path[:-1])).log()
    require(
        bool(torch.isfinite(path).all())
        and bool((path > 0).all())
        and bool(torch.isfinite(logs).all())
        and bool(torch.isfinite(traded).all())
        and bool(torch.isfinite(cash_path).all()),
        "nav_numeric",
    )
    return ClosedGroupReplay(path, logs, fee * traded, traded, cash_path, units * entering[:, None])


def net_utility(replay):
    require(type(replay) is ClosedGroupReplay, "replay_type")
    logs = replay.log_returns
    return 252 * (logs.mean() - 5 * ((logs - logs.mean()) ** 2).mean())


@nav._decimal
def decimal_reference(groups, targets, *, cost_bps, tail=(), initial_nav=Decimal(1)):
    """Canonical low-level ledger, NEVER restarting at unit NAV per group."""
    require(
        type(groups) is tuple
        and bool(groups)
        and type(targets) is tuple
        and len(targets) == len(groups)
        and all(type(g) is tuple and len(g) == HORIZON for g in groups),
        "group_geometry",
    )
    require(type(tail) is tuple and len(tail) < HORIZON, "tail_days")
    days = tuple(d for g in groups for d in g) + tail
    require(
        all(type(d) is nav.ThreeAssetDay for d in days)
        and all(a.date < b.date for a, b in zip(days, days[1:], strict=False)),
        "mark_calendar",
    )
    for day in days:
        day.__post_init__()
    for target in targets:
        require(type(target) is nav.ThreeAssetTarget, "target_type")
        target.__post_init__()
    state, previous = nav.ThreeAssetState(initial_nav), initial_nav
    fee, trace, fees, notionals = nav._fee(cost_bps), [], Decimal(0), Decimal(0)
    entries = {g[0].date: t for g, t in zip(groups, targets, strict=True)}
    exits = {g[-1].date for g in groups}
    for day in days:
        paid = traded = Decimal(0)
        if day.date in entries:
            target = entries[day.date]
            require(all(q == 0 for q in state.quantities), "entry_not_flat")
            trade = nav._rebalance(
                state, nav.ThreeAssetPrices(day.adj_open3), target.weights3, target.cash_weight, fee
            )
            state, paid, traded = trade.state, trade.fees, trade.turnover
        prices = nav.ThreeAssetPrices(day.adj_close3)
        if day.date in exits:
            trade = nav.liquidate_close(state, prices, cost_bps)
            state, paid, traded = trade.state, paid + trade.fees, traded + trade.turnover
        marked = nav.mark_close(state, prices)
        factor = marked.nav / previous
        trace.append(
            nav.ThreeAssetDaily(
                day.date,
                marked.nav,
                paid,
                traded,
                state.cash,
                all(q == 0 for q in state.quantities),
                factor - 1,
                factor.ln(),
            )
        )
        state, previous = marked.state, marked.nav
        fees, notionals = fees + paid, notionals + traded
    require(all(q == 0 for q in state.quantities), "final_not_flat")
    return nav.ThreeAssetReplay(tuple(trace), state, fees, notionals)

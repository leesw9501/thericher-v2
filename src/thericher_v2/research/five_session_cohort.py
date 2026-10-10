"""Pure NumPy five-session research policy and fixed-quantity accounting.

Used Goal78 source SHA256:
c9fb42dd66afe92cebb31c1f4d1d20d04f31e3db99137375747f2aa2207314e1
Research caps are not broker RiskLimits. Availability is assumed, not observed.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol

import numpy as np
from numpy.typing import ArrayLike, NDArray

COSTS = (5, 10, 20)
POLICIES = ("candidate", "cash", "momentum", "ridge")
Policy = Literal["candidate", "cash", "momentum", "ridge"]
ReplayStatus = Literal["complete", "input_unavailable"]


class FirstSessionFeatures(Protocol):
    """Causal feature boundary; no dependency on a particular model or loader."""

    identities: tuple[str, ...]
    decision: datetime
    tokens: NDArray[np.float64]
    eligible: NDArray[np.bool_]
    momentum: NDArray[np.float64]
    stamp: str

    @property
    def target_open(self) -> datetime: ...

    @property
    def target_close(self) -> datetime: ...


class CohortError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise CohortError(reason)


def frozen(value: ArrayLike, dtype=np.float64) -> np.ndarray:
    a = np.asarray(value, dtype=dtype)
    return np.frombuffer(a.tobytes(), dtype=dtype).reshape(a.shape)


def utc(value: datetime) -> datetime:
    require(
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0),
        "utc_clock",
    )
    return value


@dataclass(frozen=True, eq=False)
class FiveSessionFrame:
    """Original128-first 512-identity feature frame, with 21 strictly prior closes.

    Support requires 128 eligible identities including 64 beyond the original
    prefix. The caller owns any study-specific upper index and calendar scope.
    The session clocks establish order, not calendar completeness or PIT truth.
    """

    index: int
    identities: tuple[str, ...]
    decision: datetime
    prior_closes: tuple[datetime, ...]
    session_opens: tuple[datetime, ...]
    session_closes: tuple[datetime, ...]
    tokens: NDArray[np.float64] = field(repr=False)
    eligible: NDArray[np.bool_] = field(repr=False)
    momentum: NDArray[np.float64] = field(repr=False)
    volatility: NDArray[np.float64] = field(repr=False)
    feature_stamp: str
    availability: str = "assumed_not_observed"
    stamp: str = field(init=False)
    supported: bool = field(init=False)

    def __post_init__(self) -> None:
        require(type(self.index) is int and self.index >= 20, "cohort_outside_history")
        keys = tuple(self.identities)
        prior, opens, closes = (
            tuple(getattr(self, name))
            for name in ("prior_closes", "session_opens", "session_closes")
        )
        require(
            len(keys) == 512 and len(set(keys)) == 512 and all(type(k) is str and k for k in keys),
            "identity512",
        )
        require(len(prior) == 21 and len(opens) == len(closes) == 5, "five_session_geometry")
        for clock in (self.decision, *prior, *opens, *closes):
            utc(clock)
        require(
            all(a < b for a, b in zip(prior, prior[1:], strict=False))
            and prior[-1] < self.decision < opens[0],
            "causal_prior_clocks",
        )
        require(
            all(o < x and o.date() == x.date() for o, x in zip(opens, closes, strict=True))
            and all(a < b for a, b in zip(closes[:-1], opens[1:], strict=True)),
            "five_actual_session_clocks",
        )
        require(
            self.availability == "assumed_not_observed" and bool(self.feature_stamp),
            "availability_binding",
        )
        tokens, mask, momentum, vol = (
            frozen(self.tokens),
            frozen(self.eligible, np.bool_),
            frozen(self.momentum),
            frozen(self.volatility),
        )
        require(
            tokens.shape == (512, 20, 5) and mask.shape == momentum.shape == vol.shape == (512,),
            "feature_geometry",
        )
        require(
            np.isfinite(tokens).all()
            and np.isfinite(momentum).all()
            and np.isfinite(vol).all()
            and (vol >= 0.10).all(),
            "feature_values",
        )
        for name, value in (
            ("identities", keys),
            ("prior_closes", prior),
            ("session_opens", opens),
            ("session_closes", closes),
            ("tokens", tokens),
            ("eligible", mask),
            ("momentum", momentum),
            ("volatility", vol),
        ):
            object.__setattr__(self, name, value)
        header = repr(
            (
                self.index,
                keys,
                self.decision,
                prior,
                opens,
                closes,
                self.feature_stamp,
                self.availability,
            )
        ).encode()
        object.__setattr__(
            self,
            "stamp",
            hashlib.sha256(
                header + tokens.tobytes() + mask.tobytes() + momentum.tobytes() + vol.tobytes()
            ).hexdigest(),
        )
        object.__setattr__(self, "supported", bool(mask.sum() >= 128 and mask[128:].sum() >= 64))

    @property
    def target_open(self) -> datetime:
        return self.session_opens[0]

    @property
    def target_close(self) -> datetime:
        return self.session_closes[-1]


def make_five_session_frame(
    *,
    index: int,
    feature_frame: FirstSessionFeatures,
    prior_closes: tuple[datetime, ...],
    prior_close_prices: ArrayLike,
    session_opens: tuple[datetime, ...],
    session_closes: tuple[datetime, ...],
) -> FiveSessionFrame:
    """Copy prior features without relabeling the source's first-session clock."""
    prices = np.asarray(prior_close_prices, dtype=np.float64)
    require(prices.shape == (21, 512), "prior_close_prices")
    require(
        feature_frame.target_open == session_opens[0]
        and feature_frame.target_close == session_closes[0],
        "first_session_feature_binding",
    )
    mask = feature_frame.eligible
    require(
        np.isfinite(prices[:, mask]).all() and (prices[:, mask] > 0).all(), "eligible_prior_prices"
    )
    vol = np.full(512, 0.10)
    if mask.any():
        log_returns = np.diff(np.log(prices[:, mask]), axis=0)
        vol[mask] = np.maximum(0.10, log_returns.std(axis=0, ddof=0) * math.sqrt(252))
        require(
            np.allclose(
                prices[-1, mask] / prices[0, mask] - 1,
                feature_frame.momentum[mask],
                rtol=1e-12,
                atol=1e-12,
            ),
            "momentum_prior_binding",
        )
    return FiveSessionFrame(
        index,
        feature_frame.identities,
        feature_frame.decision,
        tuple(prior_closes),
        tuple(session_opens),
        tuple(session_closes),
        feature_frame.tokens,
        mask,
        feature_frame.momentum,
        vol,
        feature_frame.stamp,
    )


@dataclass(frozen=True, eq=False)
class CohortPlan:
    stamp: str
    policy: Policy
    original_selected: tuple[int, ...]
    weights: NDArray[np.float64] = field(repr=False)
    supported: bool

    def __post_init__(self) -> None:
        require(self.policy in POLICIES, "policy")
        w = frozen(self.weights)
        require(
            w.shape == (512,)
            and np.isfinite(w).all()
            and (w >= 0).all()
            and (w <= 0.10 + 1e-12).all()
            and w.sum() <= 0.50 + 1e-12,
            "entry_caps",
        )
        selected = tuple(self.original_selected)
        require(
            len(selected) in (0, 10)
            and len(set(selected)) == len(selected)
            and all(type(k) is int and 0 <= k < 512 for k in selected)
            and set(np.flatnonzero(w)) <= set(selected),
            "original_slots_only",
        )
        object.__setattr__(self, "weights", w)
        object.__setattr__(self, "original_selected", selected)


def seal_policy(
    frame: FiveSessionFrame, *, policy: Policy, ridge_scores: ArrayLike | None = None
) -> CohortPlan:
    require(isinstance(frame, FiveSessionFrame) and policy in POLICIES, "typed_policy_frame")
    w = np.zeros(512)
    if not frame.supported or policy == "cash":
        return CohortPlan(frame.stamp, policy, (), w, frame.supported)
    scores = frame.momentum if policy != "ridge" else np.asarray(ridge_scores, dtype=np.float64)
    require(scores.shape == (512,) and np.isfinite(scores[frame.eligible]).all(), "score_binding")
    selected = tuple(
        sorted(np.flatnonzero(frame.eligible).tolist(), key=lambda k: (-scores[k], k))[:10]
    )
    if policy != "candidate":
        w[list(selected)] = 0.05
    else:
        sigma = frame.volatility[list(selected)]
        inverse = 1 / sigma
        original = np.minimum(0.10, 0.50 * inverse / inverse.sum())
        original *= min(1.0, 0.08 / float(np.dot(original, sigma)))
        proxy = np.expm1(0.25 * np.log1p(frame.momentum[list(selected)]))
        w[list(selected)] = original * (proxy > 0.003)
        require(float(np.dot(w, frame.volatility)) <= 0.08 + 1e-12, "triangle_risk_cap")
    return CohortPlan(frame.stamp, policy, selected, w, True)


@dataclass(frozen=True, eq=False)
class FiveSessionLabels:
    stamp: str
    exit_at: datetime
    values: NDArray[np.float64] = field(repr=False)
    complete: bool

    def __post_init__(self) -> None:
        utc(self.exit_at)
        values = frozen(self.values)
        require(values.shape == (512,) and np.isfinite(values).all(), "label_values")
        object.__setattr__(self, "values", values)


def make_labels(
    frame: FiveSessionFrame,
    *,
    open_prices: ArrayLike,
    close_prices: ArrayLike,
    observed_at: datetime,
) -> FiveSessionLabels:
    require(
        isinstance(frame, FiveSessionFrame) and utc(observed_at) >= frame.target_close,
        "five_session_labels_not_completed",
    )
    o, x = np.asarray(open_prices, dtype=np.float64), np.asarray(close_prices, dtype=np.float64)
    require(o.shape == (512,) and x.shape == (5, 512), "five_session_label_shapes")
    valid = np.isfinite(o) & (o > 0) & np.isfinite(x).all(axis=0) & (x > 0).all(axis=0)
    complete = frame.supported and bool(valid[frame.eligible].all())
    values = np.zeros(512)
    if complete:
        values[frame.eligible] = (
            x[-1, frame.eligible] * (1 - 0.0005) / (o[frame.eligible] * (1 + 0.0005)) - 1
        )
    return FiveSessionLabels(frame.stamp, frame.target_close, values, complete)


@dataclass(frozen=True)
class CohortReplay:
    status: ReplayStatus
    reason: str
    daily_nav: tuple[float | None, ...]
    cash: tuple[float | None, ...]
    quantities: tuple[float, ...] | None
    daily_quantities: tuple[tuple[float, ...] | None, ...]
    entry_reference_nav: float | None
    entry_fee: float | None
    exit_fee: float | None
    fees: tuple[float | None, ...]
    turnover: float | None
    daily_turnover: tuple[float | None, ...]
    daily_exposure: tuple[float | None, ...]
    missing_entries: int
    missing_marks: tuple[int, ...]


def replay_cohort(
    open_prices: ArrayLike,
    close_prices: ArrayLike,
    weights: ArrayLike,
    roundtrip_bps: int,
    initial_cash: float = 1.0,
) -> CohortReplay:
    """Weights on post-entry-fee NAV; real five close marks and fixed fractional lots.

    Unselected prices are ignored. Missing required input never replaces a slot,
    fills a mark, liquidates for free or removes a scheduled date.
    Turnover is traded notional / initial_cash; fees and NAV are absolute.
    The caller supplies five actual consecutive session marks and owns calendar
    validation. No order, fill-timing or historical-availability claim is made.
    """
    o, closes, w = (np.asarray(v, dtype=np.float64) for v in (open_prices, close_prices, weights))
    require(
        o.ndim == w.ndim == 1
        and 1 <= len(w) <= 512
        and o.shape == w.shape
        and closes.shape == (5, len(w)),
        "replay_shapes",
    )
    require(roundtrip_bps in COSTS and type(roundtrip_bps) is int, "fixed_cost_band")
    require(math.isfinite(initial_cash) and initial_cash > 0, "initial_cash")
    require(
        np.isfinite(w).all()
        and (w >= 0).all()
        and (w <= 0.10 + 1e-12).all()
        and w.sum() <= 0.50 + 1e-12,
        "entry_caps",
    )
    held = w > 0
    missing_open = int((held & (~np.isfinite(o) | (o <= 0))).sum())
    missing = tuple(int((held & (~np.isfinite(x) | (x <= 0))).sum()) for x in closes)
    if missing_open:
        unknown = (None,) * 5
        return CohortReplay(
            "input_unavailable",
            "selected_entry_missing",
            unknown,
            unknown,
            None,
            unknown,
            None,
            None,
            None,
            unknown,
            None,
            unknown,
            unknown,
            missing_open,
            missing,
        )
    c = roundtrip_bps / 20000
    reference = initial_cash / (1 + c * float(w.sum()))
    notional = reference * w
    q = np.zeros(len(w))
    q[held] = notional[held] / o[held]
    entry_notional = float(notional.sum())
    entry_fee = c * entry_notional
    entry_cash = initial_cash - entry_notional - entry_fee
    require(np.isfinite(q).all() and math.isfinite(entry_cash) and entry_cash >= 0, "cash_quantity")
    quantities, zero = tuple(float(x) for x in q), (0.0,) * len(w)
    nav, cash, qs, fees, turns, exposure = [], [], [], [], [], []
    exit_fee = exit_notional = None
    for day in range(5):
        value = None if missing[day] else float(np.dot(q[held], closes[day, held]))
        require(value is None or (math.isfinite(value) and value >= 0), "marked_value")
        if day == 4 and value is not None:
            exit_notional, exit_fee = value, c * value
            final_cash = entry_cash + value - exit_fee
            require(math.isfinite(final_cash) and final_cash > 0, "exit_cash")
            nav.append(final_cash)
            cash.append(final_cash)
            qs.append(zero)
            exposure.append(0.0)
        else:
            marked = None if value is None else entry_cash + value
            nav.append(marked)
            cash.append(entry_cash)
            qs.append(quantities)
            exposure.append(None if marked is None else value / marked)
        fees.append(entry_fee if day == 0 else exit_fee if day == 4 else 0.0)
        turns.append(
            entry_notional / initial_cash
            if day == 0
            else None
            if day == 4 and exit_notional is None
            else exit_notional / initial_cash
            if day == 4
            else 0.0
        )
    return CohortReplay(
        "input_unavailable" if any(missing) else "complete",
        "held_mark_or_exit_missing" if any(missing) else "complete",
        tuple(nav),
        tuple(cash),
        quantities,
        tuple(qs),
        reference,
        entry_fee,
        exit_fee,
        tuple(fees),
        None if exit_notional is None else (entry_notional + exit_notional) / initial_cash,
        tuple(turns),
        tuple(exposure),
        missing_open,
        missing,
    )

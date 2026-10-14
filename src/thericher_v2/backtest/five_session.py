"""Analytical entry-open to fifth-close replay, not broker or local-paper fills."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Literal

import numpy as np

from thericher_v2.contracts import require_utc


@dataclass(frozen=True)
class ReplaySession:
    ordinal: int
    open_ts: datetime
    close_ts: datetime

    def __post_init__(self):
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("session_ordinal_invalid")
        require_utc(self.open_ts)
        require_utc(self.close_ts)
        if self.open_ts >= self.close_ts:
            raise ValueError("session_window_invalid")


@dataclass(frozen=True)
class FiveSessionReplay:
    status: Literal["complete", "input_unavailable"]
    nav: tuple[Fraction, ...] = ()
    exposure: tuple[Fraction, ...] = ()
    fees: Fraction | None = None
    changed_notional: Fraction | None = None
    legs: int | None = None
    missing_basket: int | None = None
    reason: str | None = None
    starting_cash: Fraction = Fraction(1)

    def summary(self) -> dict[str, object]:
        if self.status != "complete":
            return dict(status=self.status, reason=self.reason, missing_basket=self.missing_basket)
        starting_cash = self.starting_cash
        if starting_cash <= 0:
            raise ValueError("starting_cash_invalid")
        values = (starting_cash, *self.nav)
        peak = starting_cash
        drawdown = Fraction(0)
        for value in self.nav:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        return dict(
            status="complete",
            growth=float(values[-1] / starting_cash - 1),
            mean_log_return=sum(
                math.log(float(b / a)) for a, b in zip(values, values[1:], strict=False)
            )
            / max(1, len(self.nav)),
            drawdown=float(drawdown),
            fees=float(self.fees),
            turnover=float(self.changed_notional / starting_cash),
            mean_exposure=float(sum(self.exposure, Fraction(0)) / max(1, len(self.exposure))),
            close_marks=len(self.nav),
            legs=self.legs,
        )


def _matrix(value, *, boolean=False):
    result = np.asarray(value)
    if result.dtype.kind not in ("fiub" if boolean else "fiu"):
        raise ValueError("numeric_matrix_required")
    return result.astype(float, copy=False)


def _fraction(value):
    return Fraction(str(float(value)))


def replay_five_session(
    *,
    calendar: Sequence[ReplaySession],
    entries: Sequence[int],
    decisions: Sequence[datetime],
    weights,
    actions,
    opens,
    closes,
    per_side_fee_bps: int = 10,
    quantity_basis_fee_bps: int = 10,
    starting_cash: Fraction = Fraction(1),
) -> FiveSessionReplay:
    """Fixed ORIGINAL-capital quantities across recosts, five real close marks.

    Calendar includes nonholding gaps. Zero quantity never depends on a price;
    a missing positive-position entry/mark makes only this replay unavailable.
    Caller freezes identities, policy, source and availability before this API.
    """
    for bps in (per_side_fee_bps, quantity_basis_fee_bps):
        if type(bps) is not int or not 0 <= bps < 10000:
            raise ValueError("per_side_cost_invalid")
    if type(starting_cash) is not Fraction or starting_cash <= 0:
        raise ValueError("starting_cash_invalid")
    if not calendar or any(type(s) is not ReplaySession for s in calendar):
        raise ValueError("calendar_required")
    for prior, current in zip(calendar, calendar[1:], strict=False):
        if current.ordinal != prior.ordinal + 1 or prior.close_ts >= current.open_ts:
            raise ValueError("calendar_sequence_invalid")
    if len(entries) != len(decisions) or any(type(e) is not int for e in entries):
        raise ValueError("entry_binding_invalid")
    if any(b < a + 5 for a, b in zip(entries, entries[1:], strict=False)):
        raise ValueError("overlapping_or_reordered_baskets")
    w, a, op, cl = (
        _matrix(weights),
        _matrix(actions, boolean=True),
        _matrix(opens),
        _matrix(closes),
    )
    if (
        w.ndim != 2
        or len(w) != len(entries)
        or a.shape != w.shape
        or op.shape != w.shape
        or cl.shape != (len(entries), 5, w.shape[1])
    ):
        raise ValueError("five_session_shape_invalid")
    if (
        not np.isfinite(w).all()
        or (w < 0).any()
        or (w > 0.1 + 1e-12).any()
        or (w.sum(axis=1) > 0.5 + 1e-12).any()
        or not np.isfinite(a).all()
        or (a < 0).any()
        or (a > 1).any()
    ):
        raise ValueError("frozen_sizing_invalid")
    sessions = {s.ordinal: s for s in calendar}
    for e, decision in zip(entries, decisions, strict=True):
        at = require_utc(decision)
        if (
            e not in sessions
            or e + 4 not in sessions
            or at >= sessions[e].open_ts
            or e - 1 in sessions
            and at != sessions[e - 1].close_ts
        ):
            raise ValueError("causal_five_session_binding_invalid")
    cash, fees, changed, legs = starting_cash, Fraction(0), Fraction(0), 0
    marks, exposures = {}, {}
    rate = Fraction(per_side_fee_bps, 10000)
    basis = 1 + Fraction(quantity_basis_fee_bps, 10000)
    for row, entry in enumerate(entries):
        held = np.flatnonzero((w[row] > 0) & (a[row] > 0))
        if (
            not np.isfinite(op[row, held]).all()
            or (op[row, held] <= 0).any()
            or not np.isfinite(cl[row, :, held]).all()
            or (cl[row, :, held] <= 0).any()
        ):
            return FiveSessionReplay(
                "input_unavailable",
                missing_basket=row,
                reason="positive_quantity_missing_five_session_quote",
            )
        quantities = [
            starting_cash
            * _fraction(w[row, col])
            * _fraction(a[row, col])
            / (_fraction(op[row, col]) * basis)
            for col in held
        ]
        buy = sum(
            (q * _fraction(op[row, col]) for q, col in zip(quantities, held, strict=True)),
            Fraction(0),
        )
        if buy * (1 + rate) > cash:
            return FiveSessionReplay(
                "input_unavailable", missing_basket=row, reason="fixed_quantity_exceeds_actual_cash"
            )
        cash -= buy * (1 + rate)
        fees += buy * rate
        changed += buy
        legs += len(held)
        for day in range(5):
            value = sum(
                (q * _fraction(cl[row, day, col]) for q, col in zip(quantities, held, strict=True)),
                Fraction(0),
            )
            if day == 4:
                cash += value * (1 - rate)
                fees += value * rate
                changed += value
                legs += len(held)
                value = Fraction(0)
            nav = cash + value
            if cash < 0 or nav <= 0:
                raise ValueError("self_financing_invalid")
            marks[entry + day], exposures[entry + day] = nav, value / nav
    nav, exposure, last = [], [], starting_cash
    for session in calendar:
        last = marks.get(session.ordinal, last)
        nav.append(last)
        exposure.append(exposures.get(session.ordinal, Fraction(0)))
    return FiveSessionReplay(
        "complete", tuple(nav), tuple(exposure), fees, changed, legs, starting_cash=starting_cash
    )

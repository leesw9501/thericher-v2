"""Pure daily raw-OC contexts and a separate five-session TRAIN loss proxy.

The caller attests exactly64 prior and exactly5 forward scheduled NYSE sessions.
Raw vintages do not establish publication availability, corporate actions,
total returns or broker fills. No IO, policy, fitting or label lookup occurs
in feature preparation; existing monthly eligibility remains unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, Underflow, localcontext
from functools import lru_cache

from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import (
    INSTRUMENT_ORDER,
    CrossAssetInputUnavailable,
    CrossAssetSession,
)
from thericher_v2.research.cross_asset_hedge_failure_input import (
    CHANNELS,
    TARGET_COST_BPS,
    RawD1Price,
    _calendar,
    _facts,
    _positive,
    _require,
    _select,
    _utc,
    _vintage,
)
from thericher_v2.research.cross_asset_monthly_momentum import THIRD

CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN)
CONTEXT.traps[Underflow] = True
__all__ = (
    "INSTRUMENT_ORDER",
    "CHANNELS",
    "CrossAssetSession",
    "RawD1Price",
    "DailyRiskFeatures",
    "FiveSessionTarget",
    "prepare_daily_features",
    "build_five_session_target",
)


@lru_cache(maxsize=16384)
def _log(value: Decimal) -> Decimal:
    with localcontext(CONTEXT):
        return value.ln()


@dataclass(frozen=True, slots=True)
class DailyRiskFeatures:
    decision_at: datetime
    entry_at: datetime
    observation_dates: tuple[date, ...] = field(repr=False)
    features: tuple[tuple[Decimal, ...], ...] = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _utc(self.decision_at)
        _utc(self.entry_at)
        _vintage(self.vintage_ref)
        dates = self.observation_dates
        _require(
            type(dates) is tuple
            and len(dates) == 63
            and all(type(d) is date for d in dates)
            and all(a < b for a, b in zip(dates, dates[1:], strict=False))
            and dates[-1] == self.decision_at.date()
            and self.decision_at.date() < self.entry_at.date()
            and self.decision_at < self.entry_at,
            "feature_dates_invalid",
        )
        _require(
            type(self.features) is tuple
            and len(self.features) == 6
            and all(
                type(channel) is tuple
                and len(channel) == 63
                and all(type(v) is Decimal and v.is_finite() for v in channel)
                for channel in self.features
            ),
            "feature_matrix_invalid",
        )

    def safe_facts(self):
        return dict(
            _facts(),
            channels=CHANNELS,
            shape=(6, 63),
            required_closes=64,
            required_opens=63,
            decision_at=self.decision_at.isoformat(),
            entry_at=self.entry_at.isoformat(),
            calendar_attestation_owned_by="caller",
        )


def prepare_daily_features(
    rows_by_symbol: Mapping[str, Sequence[RawD1Price]],
    *,
    scheduled_history: tuple[CrossAssetSession, ...],
    entry_session: CrossAssetSession,
    decision_at: datetime,
    vintage_ref: str,
) -> DailyRiskFeatures:
    """Consume exact scheduled past keys first, never current/future support."""
    _calendar(scheduled_history)
    _require(len(scheduled_history) == 64, "history_count_invalid")
    _require(type(entry_session) is CrossAssetSession, "entry_session_invalid")
    entry_session.__post_init__()
    _utc(decision_at)
    last = scheduled_history[-1]
    _require(
        decision_at == last.close_at
        and last.session_date < entry_session.session_date
        and decision_at < entry_session.open_at,
        "decision_not_previous_close",
    )
    dates = tuple(s.session_date for s in scheduled_history)
    required = {day: ("close",) if i == 0 else ("open", "close") for i, day in enumerate(dates)}
    selected = _select(rows_by_symbol, required, vintage_ref)
    try:
        with localcontext(CONTEXT):
            channels = []
            for rows in selected:
                closes = tuple(_log(rows[day]["close"]) for day in dates)
                channels.append(tuple(b - a for a, b in zip(closes, closes[1:], strict=False)))
                channels.append(
                    tuple(closes[i] - _log(rows[day]["open"]) for i, day in enumerate(dates[1:], 1))
                )
    except DecimalException:
        raise CrossAssetInputUnavailable("numeric_range") from None
    return DailyRiskFeatures(
        decision_at, entry_session.open_at, dates[1:], tuple(channels), vintage_ref
    )


@dataclass(frozen=True, slots=True)
class FiveSessionTarget:
    entry_at: datetime
    exit_at: datetime
    net_factor: Decimal = field(repr=False)
    loss_label: bool = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _utc(self.entry_at)
        _utc(self.exit_at)
        _vintage(self.vintage_ref)
        _require(
            self.entry_at.date() < self.exit_at.date() and self.entry_at < self.exit_at,
            "target_window_invalid",
        )
        _positive(self.net_factor)
        _require(
            type(self.loss_label) is bool and self.loss_label == (self.net_factor < 1),
            "target_label_mismatch",
        )

    def safe_facts(self):
        return dict(
            _facts(),
            entry_at=self.entry_at.isoformat(),
            exit_at=self.exit_at.isoformat(),
            scheduled_session_count=5,
            required_opens=3,
            required_closes=3,
            cost_bps_side=5,
            daily_mark_support="not_checked",
            target_arithmetic="three_asset_nav.replay; endpoints_only_not_daily_utility",
            target_path="first_open_to_fifth_close; flat_after_exit",
            calendar_attestation_owned_by="caller",
        )


def build_five_session_target(
    rows_by_symbol: Mapping[str, Sequence[RawD1Price]],
    *,
    scheduled_forward: tuple[CrossAssetSession, ...],
    vintage_ref: str,
) -> FiveSessionTarget:
    """Fixed finite-thirds endpoint ledger proxy, never a daily utility target."""
    _calendar(scheduled_forward)
    _require(len(scheduled_forward) == 5, "forward_count_invalid")
    first, last = scheduled_forward[0], scheduled_forward[-1]
    selected = _select(
        rows_by_symbol, {first.session_date: ("open",), last.session_date: ("close",)}, vintage_ref
    )
    try:
        with localcontext(CONTEXT):
            allocation = nav.ThreeAssetTarget((THIRD,) * 3, Decimal(1) - 3 * THIRD)
        opens = tuple(rows[first.session_date]["open"] for rows in selected)
        closes = tuple(rows[last.session_date]["close"] for rows in selected)
        days = (
            nav.ThreeAssetDay(first.session_date, opens, opens),
            nav.ThreeAssetDay(last.session_date, closes, closes),
        )
        factor = nav.replay(days, {first.session_date: allocation}, TARGET_COST_BPS).final_nav
    except DecimalException:
        raise CrossAssetInputUnavailable("numeric_range") from None
    except nav.ThreeAssetNavError as error:
        code = "numeric_range" if str(error) == "numeric_range" else "target_ledger_unavailable"
        raise CrossAssetInputUnavailable(code) from None
    return FiveSessionTarget(first.open_at, last.close_at, factor, factor < 1, vintage_ref)

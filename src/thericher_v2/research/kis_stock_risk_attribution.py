"""Fixed cash-backed exposure and exact stock/day accounting; no fits or I/O.

Rank seals remain unchanged in the returned CarryReplay for reference parity.
ScaledSeal records the actual sizing instruction separately, before quotes.
Cash earns zero; missing marks do not become zero contributions. Source clocks,
raw-price diagnostics, persistence and research comparisons are caller-owned.
This analytical book is not broker accounting or a Paper input.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from thericher_v2.research import kis_equity_rank_buffer_carry as book
from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_score_replay as score

EXPOSURES = (Fraction(1), Fraction(1, 10), Fraction(1, 4))
RankSeal = score.ScoreSeal | book.TargetSeal
ScoreSource = Callable[[int], Mapping[str, float]]
ZERO = Fraction(0)


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


@dataclass(frozen=True, slots=True)
class ScaledSeal:
    original: RankSeal
    exposure: Fraction

    def __post_init__(self) -> None:
        _require(
            isinstance(self.original, (score.ScoreSeal, book.TargetSeal)), "rank_seal_required"
        )
        _require(
            type(self.exposure) is Fraction and self.exposure in EXPOSURES,
            "fixed_exposure_required",
        )

    @property
    def weights(self) -> tuple[tuple[str, Fraction], ...] | None:
        weights = self.original.weights
        return None if weights is None else tuple((key, w * self.exposure) for key, w in weights)

    @property
    def cash_weight(self) -> Fraction | None:
        weights = self.weights
        return None if weights is None else 1 - sum((w for _, w in weights), ZERO)


def scale_seal(seal: RankSeal, exposure: Fraction) -> ScaledSeal:
    """Scale only weights, not rank, peers, KEEP semantics or whole-share floors."""
    return ScaledSeal(seal, exposure)


def rebalance_scaled(
    state: book.Ledger,
    seal: ScaledSeal,
    prices: Mapping[str, Decimal | None],
    *,
    round_trip_bps: int,
) -> book.Trade:
    _require(isinstance(state, book.Ledger) and isinstance(seal, ScaledSeal), "book_seal_required")
    original = seal.original
    _require(
        state.owned_keys == original.owned_keys
        and set(state.keys)
        == set(original.snapshot.eligible_keys) | set(original.snapshot.unavailable_keys),
        "book_seal_binding",
    )
    book._fee(round_trip_bps)
    if seal.weights is None:
        return book.Trade(state, original.reason)
    return book._execute(state, seal.weights, prices, round_trip_bps)


@dataclass(frozen=True, slots=True)
class StockDay:
    key: str
    prior_marked_value: Fraction | None
    marked_value: Fraction | None
    # Buys positive, sells negative; both OPEN and terminal CLOSE fills included.
    signed_fill_cash: Fraction
    fees: Fraction
    traded_notional: Fraction
    net_contribution: Fraction | None


@dataclass(frozen=True, slots=True)
class DayAttribution:
    entry_index: int
    session: date
    stocks: tuple[StockDay, ...]
    nav_delta: Fraction | None
    net_contribution: Fraction | None
    fees: Fraction
    traded_notional: Fraction
    unavailable_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AssetAttribution:
    key: str
    net_contribution: Fraction | None
    fees: Fraction
    traded_notional: Fraction


@dataclass(frozen=True, slots=True)
class RiskReplay:
    replay: book.CarryReplay
    exposure: Fraction
    seals: tuple[ScaledSeal, ...]
    days: tuple[DayAttribution, ...]
    assets: tuple[AssetAttribution, ...]
    net_gain: Fraction | None
    fees: Fraction
    traded_notional: Fraction

    @property
    def attribution_complete(self) -> bool:
        return self.net_gain is not None


def attribute_day(
    before: book.Ledger,
    day: book.Daily,
    previous_closes: Mapping[str, Decimal | None],
    closes: Mapping[str, Decimal | None],
    *,
    previous_nav: Fraction | None,
) -> DayAttribution:
    """Exact q_end*C - prior_q*C_prior - signed_fill_cash - fees per opaque key.

    A zero holding needs no quote. Adjacent unavailable NAVs cannot support a
    complete daily equality even if some stock contributions are computable.
    """
    _require(
        isinstance(before, book.Ledger)
        and isinstance(day, book.Daily)
        and before.keys == day.state.keys == day.trade.state.keys,
        "attribution_book_binding",
    )
    _require(previous_nav is None or type(previous_nav) is Fraction, "previous_nav_invalid")
    _require(
        day.state == (day.terminal_trade.state if day.terminal_trade else day.trade.state),
        "attribution_final_state_binding",
    )
    fills = day.trade.fills + (day.terminal_trade.fills if day.terminal_trade else ())
    signed = dict.fromkeys(before.keys, ZERO)
    fees = dict.fromkeys(before.keys, ZERO)
    notional = dict.fromkeys(before.keys, ZERO)
    delta = dict.fromkeys(before.keys, ZERO)
    for fill in fills:
        _require(
            fill.key in signed
            and fill.side in ("buy", "sell")
            and type(fill.quantity) is Fraction
            and fill.quantity > 0
            and type(fill.price) is Fraction
            and fill.price > 0
            and type(fill.fee) is Fraction
            and fill.fee >= 0,
            "attribution_fill_invalid",
        )
        sign = 1 if fill.side == "buy" else -1
        amount = fill.quantity * fill.price
        signed[fill.key] += sign * amount
        delta[fill.key] += sign * fill.quantity
        fees[fill.key] += fill.fee
        notional[fill.key] += amount
    total_fees = sum(fees.values(), ZERO)
    _require(
        before.gross_cash - sum(signed.values(), ZERO) == day.state.gross_cash
        and before.fees_paid + total_fees == day.state.fees_paid
        and all(
            q + delta[key] == after
            for key, q, after in zip(
                before.keys, before.quantities, day.state.quantities, strict=True
            )
        ),
        "attribution_fill_cash_conservation",
    )
    prior_prices, prior_missing = book._prices(previous_closes, before.owned_keys)
    prices, missing = book._prices(closes, day.state.owned_keys)
    if previous_nav is not None:
        _require(previous_nav == book.mark(before, previous_closes), "prior_nav_mark_binding")
    if day.net_nav is not None:
        _require(day.net_nav == book.mark(day.state, closes), "nav_mark_binding")
    stocks = []
    for key, prior_q, q in zip(before.keys, before.quantities, day.state.quantities, strict=True):
        prior_value = (
            ZERO if not prior_q else (prior_q * prior_prices[key] if key in prior_prices else None)
        )
        value = ZERO if not q else (q * prices[key] if key in prices else None)
        contribution = (
            value - prior_value - signed[key] - fees[key]
            if value is not None and prior_value is not None
            else None
        )
        stocks.append(
            StockDay(key, prior_value, value, signed[key], fees[key], notional[key], contribution)
        )
    nav_delta = (
        day.net_nav - previous_nav if day.net_nav is not None and previous_nav is not None else None
    )
    contribution = (
        sum((stock.net_contribution for stock in stocks), ZERO)
        if nav_delta is not None and not prior_missing and not missing
        else None
    )
    _require(contribution is None or contribution == nav_delta, "daily_attribution_conservation")
    return DayAttribution(
        day.entry_index,
        day.session,
        tuple(stocks),
        nav_delta,
        contribution,
        total_fees,
        sum(notional.values(), ZERO),
        tuple(sorted(set(prior_missing) | set(missing) | set(day.unavailable_keys))),
    )


def replay_risk(
    plan: book.CarryPlan,
    snapshot_source: book.SnapshotSource,
    price_source: book.PriceSource,
    *,
    exposure: Fraction,
    round_trip_bps: int,
    liquidate_last_close: bool,
    mode: str = "whole",
    arm: str | None = None,
    score_source: ScoreSource | None = None,
    policy: str | None = None,
    on_seal: Callable[[ScaledSeal], None] | None = None,
) -> RiskReplay:
    """One fixed BANK, all 52 marks; same scores, costs and cadence at each exposure.

    Controls seal against this replay's own actual inventory, including floors.
    No current quote is requested until on_seal returns successfully. The book
    retains original ranking seals; RiskReplay.seals holds executed sizing seals.
    """
    _require(isinstance(plan, book.CarryPlan), "plan_required")
    _require(type(exposure) is Fraction and exposure in EXPOSURES, "fixed_exposure_required")
    _require(type(liquidate_last_close) is bool, "explicit_terminal_choice_required")
    model_arm = arm in score.ARMS and policy is None and callable(score_source)
    control_arm = policy in book.POLICIES and arm is None and score_source is None
    _require(model_arm or control_arm, "exactly_one_model_or_control_required")
    book._fee(round_trip_bps)
    state = book.Ledger.initial(plan.keys, mode=mode)
    previous_closes, previous_nav = {}, book.BANK
    days, attributions, seals, trades = [], [], [], []
    started = False
    for entry in plan.mark_entries:
        before, session, seal = state, plan.sessions[entry], None
        trade = book.Trade(state, "scheduled_carry")
        if (entry - book.WARMUP) % book.CADENCE == 0:
            snapshot = snapshot_source(entry)
            _require(
                isinstance(snapshot, core.EligibilitySnapshot)
                and snapshot.entry_index == entry
                and snapshot.entry_session == session
                and snapshot.decision_session == plan.sessions[entry - 1]
                and set(snapshot.eligible_keys) | set(snapshot.unavailable_keys) == set(plan.keys),
                "snapshot_calendar_universe_binding",
            )
            seal = (
                score.seal_scores(snapshot, state.owned_keys, score_source(entry), arm=arm)
                if model_arm
                else book.seal_target(
                    snapshot, state.owned_keys, policy=policy, buy_once_started=started
                )
            )
            scaled = scale_seal(seal, exposure)
            seals.append(scaled)
            if on_seal is not None:
                on_seal(scaled)
            needed = tuple(sorted(set(state.owned_keys) | {key for key, _ in scaled.weights or ()}))
            opening = (
                {key: price_source(key, session, "open") for key in needed}
                if scaled.weights is not None
                else {}
            )
            trade = rebalance_scaled(state, scaled, opening, round_trip_bps=round_trip_bps)
            if policy == "buy_once_momentum20" and scaled.weights:
                started = True
        state = trade.state
        closing = {key: price_source(key, session, "close") for key in state.owned_keys}
        _, close_missing = book._prices(closing, state.owned_keys)
        terminal = None
        if entry == book.SESSION_COUNT - 1 and liquidate_last_close:
            terminal = book.liquidate_final(state, closing, round_trip_bps=round_trip_bps)
            state = terminal.state
        missing = tuple(sorted(set(trade.unavailable_keys) | set(close_missing)))
        nav = None if missing else book.mark(state, closing)
        day = book.Daily(entry, session, seal, trade, terminal, state, nav, missing)
        days.append(day)
        attributions.append(
            attribute_day(before, day, previous_closes, closing, previous_nav=previous_nav)
        )
        previous_closes, previous_nav = closing, nav
        trades.append(trade)
        if terminal is not None:
            trades.append(terminal)
    unavailable = tuple(day.entry_index for day in days if day.net_nav is None)
    fills = tuple(fill for trade in trades for fill in trade.fills)
    fees = sum((fill.fee for fill in fills), ZERO)
    notional = sum((fill.quantity * fill.price for fill in fills), ZERO)
    public = book.PublicAggregate(
        len(days),
        len(seals),
        len(fills),
        unavailable,
        None if unavailable else days[-1].net_nav / book.BANK - 1,
        notional / book.BANK,
        fees / book.BANK,
        state.mode,
        liquidate_last_close,
        len(state.owned_keys),
    )
    complete = all(day.net_contribution is not None for day in attributions)
    net_gain = sum((day.net_contribution for day in attributions), ZERO) if complete else None
    assets = tuple(
        AssetAttribution(
            key,
            sum((day.stocks[i].net_contribution for day in attributions), ZERO)
            if complete
            else None,
            sum((day.stocks[i].fees for day in attributions), ZERO),
            sum((day.stocks[i].traded_notional for day in attributions), ZERO),
        )
        for i, key in enumerate(plan.keys)
    )
    _require(
        fees == state.fees_paid
        and fees == sum((asset.fees for asset in assets), ZERO)
        and notional == sum((asset.traded_notional for asset in assets), ZERO),
        "cumulative_fee_notional_conservation",
    )
    if complete:
        _require(
            net_gain == days[-1].net_nav - book.BANK
            and net_gain == sum((asset.net_contribution for asset in assets), ZERO),
            "cumulative_attribution_conservation",
        )
    return RiskReplay(
        book.CarryReplay(tuple(days), state, public),
        exposure,
        tuple(seals),
        tuple(attributions),
        assets,
        net_gain,
        fees,
        notional,
    )

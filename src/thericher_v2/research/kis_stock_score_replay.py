"""Fixed supplied-score baskets using the reviewed carry accounting unchanged.

This is analytical development only. Predictions, data clocks and persistence
are caller-owned; this module never fits a model or calls a broker.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from thericher_v2.research import kis_equity_rank_buffer_carry as book
from thericher_v2.research import kis_pooled_equity_components as core

ARMS = ("ridge", "hgb", "gru", "equal_fixed_mean_blend")
SUPPORTED_ARMS = (
    *ARMS,
    "tcn10",
    "tcn20",
    "chronos2_stock_isolated",
    "chronos2_stock_group",
)


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


@dataclass(frozen=True, slots=True)
class ScoreSeal:
    snapshot: core.EligibilitySnapshot
    arm: str
    owned_keys: tuple[str, ...]
    scores: tuple[tuple[str, float], ...]
    ranked_keys: tuple[str, ...]
    weights: tuple[tuple[str, Fraction], ...] | None

    def __post_init__(self) -> None:
        _require(isinstance(self.snapshot, core.EligibilitySnapshot), "snapshot_required")
        _require(self.arm in SUPPORTED_ARMS, "arm_invalid")
        universe = set(self.snapshot.eligible_keys) | set(self.snapshot.unavailable_keys)
        _require(
            type(self.owned_keys) is tuple
            and self.owned_keys == tuple(sorted(set(self.owned_keys)))
            and set(self.owned_keys) <= universe,
            "owned_keys_invalid",
        )
        _require(
            type(self.scores) is tuple
            and all(type(pair) is tuple and len(pair) == 2 for pair in self.scores),
            "scores_invalid",
        )
        names = tuple(key for key, _ in self.scores)
        _require(
            names == self.snapshot.eligible_keys
            and all(type(v) is float and math.isfinite(v) for _, v in self.scores),
            "scores_exact_eligible_peers_required",
        )
        ranked = tuple(key for key, _ in sorted(self.scores, key=lambda pair: (-pair[1], pair[0])))
        _require(type(self.ranked_keys) is tuple and self.ranked_keys == ranked, "rank_binding")
        expected = (
            tuple((key, Fraction(1, book.TOP_K)) for key in sorted(ranked[: book.TOP_K]))
            if len(ranked) >= book.TOP_K
            else None
        )
        _require(self.weights == expected, "fixed_top10_weights_required")

    @property
    def reason(self) -> str:
        return "fewer_than_10_keep_inventory" if self.weights is None else "fixed_model_basket"


def seal_scores(
    snapshot: core.EligibilitySnapshot,
    owned_keys: tuple[str, ...],
    scores: Mapping[str, float],
    *,
    arm: str,
) -> ScoreSeal:
    _require(isinstance(snapshot, core.EligibilitySnapshot), "snapshot_required")
    _require(isinstance(scores, Mapping), "scores_required")
    _require(set(scores) == set(snapshot.eligible_keys), "scores_exact_eligible_peers_required")
    frozen = tuple((key, scores[key]) for key in snapshot.eligible_keys)
    _require(
        all(type(v) is float and math.isfinite(v) for _, v in frozen), "finite_scores_required"
    )
    ranked = tuple(key for key, _ in sorted(frozen, key=lambda pair: (-pair[1], pair[0])))
    weights = (
        tuple((key, Fraction(1, book.TOP_K)) for key in sorted(ranked[: book.TOP_K]))
        if len(ranked) >= book.TOP_K
        else None
    )
    return ScoreSeal(snapshot, arm, owned_keys, frozen, ranked, weights)


def rebalance_scores(
    state: book.Ledger,
    seal: ScoreSeal,
    prices: Mapping[str, Decimal | None],
    *,
    round_trip_bps: int,
) -> book.Trade:
    _require(isinstance(state, book.Ledger) and isinstance(seal, ScoreSeal), "book_seal_required")
    _require(
        state.owned_keys == seal.owned_keys
        and set(state.keys)
        == set(seal.snapshot.eligible_keys) | set(seal.snapshot.unavailable_keys),
        "book_seal_binding",
    )
    _require(type(round_trip_bps) is int and round_trip_bps in book.ROUND_TRIP_BPS, "cost_invalid")
    if seal.weights is None:
        return book.Trade(state, seal.reason)
    # Reuse the exact fee-aware primitive; no momentum-policy relabeling.
    return book._execute(state, seal.weights, prices, round_trip_bps)


def replay_scores(
    plan: book.CarryPlan,
    snapshot_source: book.SnapshotSource,
    score_source: Callable[[int], Mapping[str, float]],
    price_source: book.PriceSource,
    *,
    arm: str,
    round_trip_bps: int,
    liquidate_last_close: bool,
    initial_state: book.Ledger | None = None,
    on_seal: Callable[[ScoreSeal], None] | None = None,
) -> book.CarryReplay:
    _require(isinstance(plan, book.CarryPlan) and arm in SUPPORTED_ARMS, "replay_contract_invalid")
    _require(type(liquidate_last_close) is bool, "explicit_terminal_choice_required")
    _require(type(round_trip_bps) is int and round_trip_bps in book.ROUND_TRIP_BPS, "cost_invalid")
    state = initial_state if initial_state is not None else book.Ledger.initial(plan.keys)
    _require(state.keys == plan.keys, "initial_keys_mismatch")
    days, trades = [], []
    for entry in plan.mark_entries:
        session, seal = plan.sessions[entry], None
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
            seal = seal_scores(snapshot, state.owned_keys, score_source(entry), arm=arm)
            if on_seal is not None:
                on_seal(seal)
            needed = tuple(sorted(set(state.owned_keys) | {key for key, _ in seal.weights or ()}))
            opening = (
                {key: price_source(key, session, "open") for key in needed}
                if seal.weights is not None
                else {}
            )
            trade = rebalance_scores(state, seal, opening, round_trip_bps=round_trip_bps)
        state = trade.state
        closing = {key: price_source(key, session, "close") for key in state.owned_keys}
        _, close_missing = book._prices(closing, state.owned_keys)
        terminal = None
        if entry == book.SESSION_COUNT - 1 and liquidate_last_close:
            terminal = book.liquidate_final(state, closing, round_trip_bps=round_trip_bps)
            state = terminal.state
        missing = tuple(sorted(set(trade.unavailable_keys) | set(close_missing)))
        nav = None if missing else book.mark(state, closing)
        days.append(book.Daily(entry, session, seal, trade, terminal, state, nav, missing))
        trades.append(trade)
        if terminal is not None:
            trades.append(terminal)
    unavailable = tuple(day.entry_index for day in days if day.net_nav is None)
    fills = tuple(fill for trade in trades for fill in trade.fills)
    public = book.PublicAggregate(
        len(days),
        sum(day.seal is not None for day in days),
        len(fills),
        unavailable,
        None if unavailable else days[-1].net_nav / book.BANK - 1,
        sum((fill.quantity * fill.price for fill in fills), book.ZERO) / book.BANK,
        sum((fill.fee for fill in fills), book.ZERO) / book.BANK,
        state.mode,
        liquidate_last_close,
        len(state.owned_keys),
    )
    return book.CarryReplay(tuple(days), state, public)

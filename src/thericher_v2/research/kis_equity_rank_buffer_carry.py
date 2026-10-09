"""Zero-fit carry preparation; pure synthetic accounting, not a Paper input.

Both books size on the same post-fee net NAV; only whole quantities are floored.
Cash, fee and average-cost bookkeeping mirrors whole_share_portfolio_nav, not
its gross-NAV sizing or fixed entry-basis cap. BANK is initial funding only;
profits can compound. Neither models broker fills or settlement.
Callbacks, source identity, event persistence and actual observation clocks are
caller-owned. Calendar clocks in supplied snapshots are nominal only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research.whole_share_quote_projection import project_quote

SESSION_COUNT = 113
WARMUP = 61
MARK_COUNT = 52
KEY_COUNT = 128
TOP_K = 10
BUFFER_RANK = 20
CADENCE = 5
REVIEW_POSITIONS = tuple(range(0, MARK_COUNT, CADENCE))
FULL_OPEN_INTERVAL_COUNT = 10
PARTIAL_TAIL_MARK_COUNT = 2
FIT_COUNT = 0
FAMILY_CPU_SECONDS = 300
BANK = Fraction(10000)
ROUND_TRIP_BPS = (5, 10, 20)
POLICIES = ("rank_buffer_momentum20", "full_top10_momentum20", "buy_once_momentum20", "cash")
ZERO = Fraction(0)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _keys(values: tuple[str, ...]) -> None:
    _require(
        isinstance(values, tuple)
        and 1 <= len(values) <= KEY_COUNT
        and all(isinstance(key, str) and key for key in values)
        and values == tuple(sorted(set(values))),
        "opaque_sorted_unique_keys_required",
    )


def _amount(value: Fraction) -> bool:
    return isinstance(value, Fraction) and value >= 0


@dataclass(frozen=True, slots=True)
class CarryPlan:
    sessions: tuple[date, ...]
    keys: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sessions", tuple(self.sessions))
        object.__setattr__(self, "keys", tuple(self.keys))
        _keys(self.keys)
        _require(len(self.keys) == KEY_COUNT, "exact_128_keys_required")
        _require(
            len(self.sessions) == SESSION_COUNT
            and all(type(day) is date for day in self.sessions)
            and all(a < b for a, b in zip(self.sessions, self.sessions[1:], strict=False)),
            "exact_113_ordered_official_sessions_required",
        )

    @property
    def mark_entries(self) -> range:
        return range(WARMUP, SESSION_COUNT)


@dataclass(frozen=True, slots=True)
class TargetSeal:
    snapshot: core.EligibilitySnapshot
    policy: str
    owned_keys: tuple[str, ...]
    ranked_keys: tuple[str, ...]
    # None means KEEP, not cash or a newly selected empty basket.
    weights: tuple[tuple[str, Fraction], ...] | None
    reason: str

    def __post_init__(self) -> None:
        _require(isinstance(self.snapshot, core.EligibilitySnapshot), "snapshot_required")
        object.__setattr__(self, "owned_keys", tuple(self.owned_keys))
        object.__setattr__(self, "ranked_keys", tuple(self.ranked_keys))
        if self.weights is not None:
            object.__setattr__(self, "weights", tuple((key, w) for key, w in self.weights))
        universe = set(self.snapshot.eligible_keys) | set(self.snapshot.unavailable_keys)
        _require(self.policy in POLICIES, "policy_invalid")
        _require(
            self.owned_keys == tuple(sorted(set(self.owned_keys)))
            and set(self.owned_keys) <= universe
            and len(self.ranked_keys) == len(self.snapshot.rows)
            and set(self.ranked_keys) == set(self.snapshot.eligible_keys),
            "seal_key_binding",
        )
        if self.weights is not None:
            names = tuple(key for key, _ in self.weights)
            _require(
                names == tuple(sorted(set(names)))
                and set(names) <= set(self.snapshot.eligible_keys)
                and (
                    (self.policy == "cash" and not names)
                    or (
                        self.policy != "cash"
                        and len(names) == TOP_K
                        and all(
                            isinstance(weight, Fraction) and weight == Fraction(1, TOP_K)
                            for _, weight in self.weights
                        )
                    )
                ),
                "fixed_top10_weights_required",
            )


def seal_target(
    snapshot: core.EligibilitySnapshot,
    owned_keys: tuple[str, ...],
    *,
    policy: str = "rank_buffer_momentum20",
    buy_once_started: bool = False,
) -> TargetSeal:
    """Rank all decision-eligible peers before any execution-price lookup."""
    _require(isinstance(snapshot, core.EligibilitySnapshot), "snapshot_required")
    _require(policy in POLICIES and type(buy_once_started) is bool, "policy_invalid")
    owned = tuple(owned_keys)
    scores = dict(core.controls(snapshot)["momentum20"].scores)
    ranked = tuple(sorted(scores, key=lambda key: (-Fraction(scores[key]), key)))
    if policy == "cash":
        weights, reason = (), "cash"
    elif len(ranked) < TOP_K:
        weights, reason = None, "fewer_than_10_keep_inventory"
    elif policy == "buy_once_momentum20" and buy_once_started:
        weights, reason = None, "buy_once_keep_inventory"
    else:
        selected = []
        if policy == "rank_buffer_momentum20":
            selected = [key for key in owned if key in ranked[:BUFFER_RANK]]
            _require(len(selected) <= TOP_K, "owned_buffer_exceeds_top10")
        for key in ranked:
            if len(selected) == TOP_K:
                break
            if key not in selected:
                selected.append(key)
        weights = tuple((key, Fraction(1, TOP_K)) for key in sorted(selected))
        reason = "fixed_basket"
    return TargetSeal(snapshot, policy, owned, ranked, weights, reason)


@dataclass(frozen=True, slots=True)
class Ledger:
    keys: tuple[str, ...]
    quantities: tuple[Fraction, ...]
    entry_costs: tuple[Fraction, ...]
    gross_cash: Fraction = BANK
    fees_paid: Fraction = ZERO
    mode: str = "whole"

    def __post_init__(self) -> None:
        _keys(self.keys)
        _require(self.mode in ("whole", "fractional_reference"), "ledger_mode_invalid")
        _require(
            isinstance(self.quantities, tuple)
            and isinstance(self.entry_costs, tuple)
            and len(self.quantities) == len(self.entry_costs) == len(self.keys)
            and _amount(self.gross_cash)
            and _amount(self.fees_paid)
            and self.cash >= 0
            and all(_amount(q) for q in self.quantities)
            and all(_amount(cost) for cost in self.entry_costs)
            and all(
                (q == 0) == (cost == 0)
                for q, cost in zip(self.quantities, self.entry_costs, strict=True)
            )
            and (self.mode != "whole" or all(q.denominator == 1 for q in self.quantities)),
            "ledger_invalid",
        )

    @classmethod
    def initial(cls, keys: tuple[str, ...], *, mode: str = "whole") -> Ledger:
        return cls(keys, (ZERO,) * len(keys), (ZERO,) * len(keys), mode=mode)

    @property
    def cash(self) -> Fraction:
        return self.gross_cash - self.fees_paid

    @property
    def owned_keys(self) -> tuple[str, ...]:
        return tuple(key for key, q in zip(self.keys, self.quantities, strict=True) if q)


@dataclass(frozen=True, slots=True)
class Fill:
    key: str
    side: str
    quantity: Fraction
    price: Fraction
    fee: Fraction


@dataclass(frozen=True, slots=True)
class Trade:
    state: Ledger
    reason: str
    fills: tuple[Fill, ...] = ()
    unavailable_keys: tuple[str, ...] = ()

    @property
    def traded_notional(self) -> Fraction:
        return sum((fill.quantity * fill.price for fill in self.fills), ZERO)


def _prices(
    raw: Mapping[str, Decimal | None], needed: tuple[str, ...]
) -> tuple[dict[str, Fraction], tuple[str, ...]]:
    prices, missing = {}, []
    for key in needed:
        try:
            prices[key] = Fraction(project_quote(raw.get(key)))
        except (ValueError, ArithmeticError):
            missing.append(key)
    return prices, tuple(missing)


def _fee(round_trip_bps: int) -> Fraction:
    _require(type(round_trip_bps) is int and round_trip_bps in ROUND_TRIP_BPS, "cost_invalid")
    return Fraction(round_trip_bps, 20000)


def _reference_nav(nav: Fraction, holdings: tuple, weights: tuple, fee: Fraction) -> Fraction:
    # Exact finite piecewise-linear counterpart of three_asset_nav's post-fee
    # equation. At most N+1 intervals; no iterative optimizer or tolerance.
    bounds = sorted(
        {
            ZERO,
            nav,
            *(h / w for h, w in zip(holdings, weights, strict=True) if w and 0 < h / w < nav),
        }
    )
    if nav == 0:
        return ZERO
    for lower, upper in zip(bounds, bounds[1:], strict=False):
        middle = (lower + upper) / 2
        signs = tuple(1 if w * middle >= h else -1 for h, w in zip(holdings, weights, strict=True))
        numerator = nav + fee * sum((s * h for s, h in zip(signs, holdings, strict=True)), ZERO)
        denominator = 1 + fee * sum((s * w for s, w in zip(signs, weights, strict=True)), ZERO)
        root = numerator / denominator
        if lower <= root <= upper:
            return root
    raise ValueError("fractional_reference_equation_invalid")


def _execute(
    state: Ledger,
    weights: tuple[tuple[str, Fraction], ...],
    raw_prices: Mapping[str, Decimal | None],
    round_trip_bps: int,
) -> Trade:
    fee = _fee(round_trip_bps)
    names = tuple(key for key, _ in weights)
    _require(
        names == tuple(sorted(set(names)))
        and set(names) <= set(state.keys)
        and all(_amount(w) for _, w in weights)
        and sum((w for _, w in weights), ZERO) <= 1,
        "target_invalid",
    )
    needed = tuple(sorted(set(state.owned_keys) | set(names)))
    prices, missing = _prices(raw_prices, needed)
    if missing:
        return Trade(state, "price_unavailable", unavailable_keys=missing)
    weights_by_key = dict(weights)
    vector = tuple(weights_by_key.get(key, ZERO) for key in state.keys)
    holdings = tuple(
        q * prices[key] if q else ZERO for key, q in zip(state.keys, state.quantities, strict=True)
    )
    # Solve V' + f*sum(abs(w*V' - held_notional)) = current NET NAV.
    # Shared sizing funds the complete delta batch before any fill. Flooring
    # only lowers purchases/increases sale proceeds by more than its fee change.
    nav = _reference_nav(state.cash + sum(holdings, ZERO), holdings, vector, fee)
    target = tuple(
        w * nav / prices[key] if w else ZERO for key, w in zip(state.keys, vector, strict=True)
    )
    if state.mode == "whole":
        target = tuple(Fraction(q.numerator // q.denominator) for q in target)
    sold = tuple(max(q - t, ZERO) for q, t in zip(state.quantities, target, strict=True))
    bought = tuple(max(t - q, ZERO) for q, t in zip(state.quantities, target, strict=True))
    fills = tuple(
        Fill(key, side, q, prices[key], q * prices[key] * fee)
        for side, amounts in (("sell", sold), ("buy", bought))
        for key, q in zip(state.keys, amounts, strict=True)
        if q
    )
    if not fills:
        return Trade(state, "no_delta")
    sale = sum((fill.quantity * fill.price for fill in fills if fill.side == "sell"), ZERO)
    purchase = sum((fill.quantity * fill.price for fill in fills if fill.side == "buy"), ZERO)
    fees = state.fees_paid + sum((fill.fee for fill in fills), ZERO)
    cash = state.gross_cash + sale - purchase
    costs = tuple(
        cost - cost * s / q + b * prices[key] if q else b * prices.get(key, ZERO)
        for key, q, cost, s, b in zip(
            state.keys, state.quantities, state.entry_costs, sold, bought, strict=True
        )
    )
    if cash - fees < 0:
        return Trade(state, "analytical_cash_negative")
    after = Ledger(state.keys, target, costs, cash, fees, state.mode)
    return Trade(after, "executed", fills)


def rebalance(
    state: Ledger,
    seal: TargetSeal,
    prices: Mapping[str, Decimal | None],
    *,
    round_trip_bps: int,
) -> Trade:
    _fee(round_trip_bps)
    _require(
        seal.owned_keys == state.owned_keys
        and set(state.keys)
        == set(seal.snapshot.eligible_keys) | set(seal.snapshot.unavailable_keys),
        "ledger_seal_binding",
    )
    if seal.weights is None:
        return Trade(state, seal.reason)
    return _execute(state, seal.weights, prices, round_trip_bps)


def liquidate_final(
    state: Ledger,
    prices: Mapping[str, Decimal | None],
    *,
    round_trip_bps: int,
) -> Trade:
    """Explicit terminal CLOSE only; replay never calls this at ordinary marks."""
    return _execute(state, (), prices, round_trip_bps)


def mark(state: Ledger, prices: Mapping[str, Decimal | None]) -> Fraction | None:
    projected, missing = _prices(prices, state.owned_keys)
    if missing:
        return None
    return state.cash + sum(
        (q * projected[key] for key, q in zip(state.keys, state.quantities, strict=True) if q), ZERO
    )


@dataclass(frozen=True, slots=True)
class Daily:
    entry_index: int
    session: date
    seal: TargetSeal | None
    trade: Trade
    terminal_trade: Trade | None
    state: Ledger
    net_nav: Fraction | None
    unavailable_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublicAggregate:
    mark_count: int
    decision_count: int
    fill_count: int
    unavailable_entries: tuple[int, ...]
    net_growth: Fraction | None
    traded_notional_over_bank: Fraction
    fees_over_bank: Fraction
    mode: str
    final_liquidation_requested: bool
    final_inventory_count: int
    development_only: bool = True
    historical_decision_time_availability: str = "not_observed"
    broker_fill_parity_claimed: bool = False
    full_open_interval_count: int = FULL_OPEN_INTERVAL_COUNT
    partial_tail_mark_count: int = PARTIAL_TAIL_MARK_COUNT
    independent_sample_count_claimed: bool = False


@dataclass(frozen=True, slots=True)
class CarryReplay:
    days: tuple[Daily, ...]
    final_state: Ledger
    public: PublicAggregate


PriceSource = Callable[[str, date, str], Decimal | None]
SnapshotSource = Callable[[int], core.EligibilitySnapshot]


def replay(
    plan: CarryPlan,
    snapshot_source: SnapshotSource,
    price_source: PriceSource,
    *,
    policy: str,
    round_trip_bps: int,
    liquidate_last_close: bool,
    initial_state: Ledger | None = None,
    on_seal: Callable[[TargetSeal], None] | None = None,
) -> CarryReplay:
    """All 52 consecutive marks, one book; callbacks perform no kernel-owned I/O.

    A buy-once control latches its first nonempty basket even if funding rejects;
    it never turns a failed basket into outcome-dependent retries.
    """
    _require(isinstance(plan, CarryPlan) and policy in POLICIES, "replay_contract_invalid")
    _require(type(liquidate_last_close) is bool, "explicit_terminal_choice_required")
    _fee(round_trip_bps)
    state = initial_state if initial_state is not None else Ledger.initial(plan.keys)
    _require(state.keys == plan.keys, "initial_keys_mismatch")
    days, trades, started = [], [], bool(state.owned_keys)
    for entry in plan.mark_entries:
        session, seal = plan.sessions[entry], None
        trade = Trade(state, "scheduled_carry")
        if (entry - WARMUP) % CADENCE == 0:
            snapshot = snapshot_source(entry)
            _require(
                isinstance(snapshot, core.EligibilitySnapshot)
                and snapshot.entry_index == entry
                and snapshot.entry_session == session
                and snapshot.decision_session == plan.sessions[entry - 1]
                and set(snapshot.eligible_keys) | set(snapshot.unavailable_keys) == set(plan.keys),
                "snapshot_calendar_universe_binding",
            )
            seal = seal_target(snapshot, state.owned_keys, policy=policy, buy_once_started=started)
            if on_seal is not None:
                on_seal(seal)
            if seal.weights is not None:
                needed = tuple(sorted(set(state.owned_keys) | {key for key, _ in seal.weights}))
                opening = {key: price_source(key, session, "open") for key in needed}
                trade = rebalance(state, seal, opening, round_trip_bps=round_trip_bps)
                if policy == "buy_once_momentum20" and seal.weights:
                    started = True
            else:
                trade = rebalance(state, seal, {}, round_trip_bps=round_trip_bps)
        state = trade.state
        closing = {key: price_source(key, session, "close") for key in state.owned_keys}
        _, close_missing = _prices(closing, state.owned_keys)
        terminal = None
        if entry == SESSION_COUNT - 1 and liquidate_last_close:
            terminal = liquidate_final(state, closing, round_trip_bps=round_trip_bps)
            state = terminal.state
        missing = tuple(sorted(set(trade.unavailable_keys) | set(close_missing)))
        nav = None if missing else mark(state, closing)
        days.append(Daily(entry, session, seal, trade, terminal, state, nav, missing))
        trades.append(trade)
        if terminal is not None:
            trades.append(terminal)
    unavailable = tuple(day.entry_index for day in days if day.net_nav is None)
    fills = tuple(fill for trade in trades for fill in trade.fills)
    public = PublicAggregate(
        len(days),
        sum(day.seal is not None for day in days),
        len(fills),
        unavailable,
        None if unavailable else days[-1].net_nav / BANK - 1,
        sum((fill.quantity * fill.price for fill in fills), ZERO) / BANK,
        sum((fill.fee for fill in fills), ZERO) / BANK,
        state.mode,
        liquidate_last_close,
        len(state.owned_keys),
    )
    return CarryReplay(tuple(days), state, public)

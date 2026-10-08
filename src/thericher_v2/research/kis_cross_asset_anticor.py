"""Source-free fixed ANTICOR preparation and continuous raw-price NAV replay.

No loader, IO, provider, fit, model dispatch or Paper input. The caller freezes
source/calendar/custody before an actual study. Legacy NAV positional fields
do not assert adjustment: input grade remains raw MODP0 throughout.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal, localcontext
from fractions import Fraction
from math import isfinite
from time import monotonic
from types import MappingProxyType

from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.anticor_allocation import _weights, _window, anticor_allocation
from thericher_v2.research.cross_asset_hedge_failure_input import (
    CONTEXT,
    INSTRUMENT_ORDER,
    CrossAssetSession,
    _calendar,
    _require,
    _select,
    _utc,
    _vintage,
)
from thericher_v2.research.cross_asset_monthly_momentum import PRICE_BASIS, THIRD

NAME = "kis-cross-asset-anticor-development-v1"
SYMBOLS = INSTRUMENT_ORDER
WINDOW, CADENCE, SECONDS = 20, 5, 60
CANDIDATES = ("candidate",)
CONTROLS = ("balanced", "momentum63", "spy", "cash")
POLICIES = CANDIDATES + CONTROLS
COSTS = (Decimal("2.5"), Decimal(5), Decimal(10))
TOLERANCE = Decimal("1e-10")
QUANTUM = Decimal("1e-45")
DEV_START, VIEW_END, DEV_END = date(2021, 1, 4), date(2023, 12, 29), date(2026, 9, 30)
FIRST_DECISION = date(2020, 12, 31)
INPUT_SHA256 = "4a25284d8ae8538105c798cbc0337ef3ca9615977829eb2d3d951797cbc5dc64"
COMMITMENT_ID = "02b27fdd7b181a1af9598b30db69cc9b9108e746ca7d74c2e5623e2ed0345c10"


def configuration():
    return dict(
        name=NAME, preparation_only=True, symbols=list(SYMBOLS), price_basis=PRICE_BASIS,
        input_sha256=INPUT_SHA256, commitment_id=COMMITMENT_ID,
        source=dict(doi="10.1613/jair.1336", url="https://arxiv.org/pdf/1107.0036v1",
                    equations="2,3; Figure1 inclusive ties and all-pairs/self claims",
                    primitive_preparation_sha256=
                    "8c16fc5b2b93558ba41272fd86fbfc53f3dc18538bf71d0d4d4e9a60266142dd",
                    source_results_adopted=False, primary_source_code_copied=False),
        windows=dict(w=WINDOW, past_returns=40, past_closes=41, shared_past_closes=64,
                     return_formula="Decimal50 ln(CLOSE[t])-ln(CLOSE[t-1]); binary64 windows"),
        cadence="every5 frozen NYSE sessions from2021-01-04; previous CLOSE decision; next OPEN",
        drift="continuous zero-fee signal inventory; prior executed OPEN and decision CLOSE only; "
              "normalize risky notionals; seed equal thirds; not a scored or broker inventory",
        target="Figure1 simultaneous original-donor transfers; no damping, blend or cash gate; "
               "exact rational normalization of float rounding, each weight ROUND_DOWN45dp; "
               "exact residual cash; no target recomputation at execution OPEN",
        momentum="63 scheduled CLOSE log differences; absolute argmax>0 elsecash; ties SPY/TLT/GLD",
        policies=list(POLICIES), costs_bps_side=[str(c) for c in COSTS], cells=30,
        dev_views=[["2021-01-04", "2023-12-29"], ["2024-01-02", "2026-09-30"]],
        geometry=dict(marks=1442, views=[753, 689], entries=289, tail="held until final CLOSE"),
        accounting="one NAV1 per policy/cost; simultaneous post-fee OPEN allocation; "
                   "actual incumbent notional fees; daily CLOSE marks; final CLOSE exit only",
        utility="252*(mean daily log return-5*population variance)",
        kill="10bps BOTH views candidate growth>0; growth AND utility improvements "
             ">1e-10 vs balanced/momentum63/spy/cash; turnover cannot rescue failure",
        fits=0, gpu=False, seconds=SECONDS, selection="none; one fixed window/cadence",
        lineage="seen raw 2016 cohort; related closed momentum/21D-selection/allocation studies; "
                "new pairwise reversal mechanism, not model or failed-study rescue",
        grade="RELATED_SEEN_RAW_PRICE_ONLY_DEVELOPMENT", paper_input=False, holdout="none",
        limitations=["non-PIT", "splits/dividends not applied",
                     "availability/finality not observed", "ideal fractional fills",
                     "overlapping windows; observations not independent"],
    )


@dataclass(frozen=True, slots=True)
class AnticorPlan:
    sessions: tuple[CrossAssetSession, ...] = field(repr=False)
    dev_indices: tuple[int, ...] = field(repr=False)
    block_cut: int

    def __post_init__(self):
        _calendar(self.sessions)
        indices = self.dev_indices
        _require(type(indices) is tuple and bool(indices), "dev_calendar")
        _require(all(type(i) is int and 64 <= i < len(self.sessions) for i in indices),
                 "plan_indices")
        _require(indices == tuple(range(indices[0], indices[-1] + 1)), "plan_indices")
        _require(type(self.block_cut) is int and 0 < self.block_cut < len(indices), "view_calendar")

    @property
    def dates(self):
        return tuple(self.sessions[i].session_date for i in self.dev_indices)

    @property
    def entry_indices(self):
        return self.dev_indices[::CADENCE]

    @property
    def entries(self):
        return tuple(self.sessions[i].session_date for i in self.entry_indices)

    def record(self):
        return dict(dates=[d.isoformat() for d in self.dates],
                    entries=[d.isoformat() for d in self.entries], block_cut=self.block_cut,
                    decisions=[self.sessions[i - 1].close_at.isoformat()
                               for i in self.entry_indices],
                    opens=[self.sessions[i].open_at.isoformat() for i in self.entry_indices],
                    independent_sample_count="not_claimed")


def build_plan(sessions):
    """Fixed study calendar; pure lower-level plan objects also permit synthetic fixtures."""
    _calendar(sessions)
    indices = tuple(i for i, s in enumerate(sessions) if DEV_START <= s.session_date <= DEV_END)
    cut = sum(sessions[i].session_date <= VIEW_END for i in indices)
    plan = AnticorPlan(sessions, indices, cut)
    _require(plan.dates[0] == DEV_START and plan.dates[-1] == DEV_END
             and sessions[indices[0] - 1].session_date == FIRST_DECISION
             and plan.dates[cut - 1] == VIEW_END and plan.dates[cut] == date(2024, 1, 2)
             and (len(indices), cut, len(plan.entries)) == (1442, 753, 289), "study_calendar")
    return plan


@dataclass(frozen=True, slots=True)
class AnticorContext:
    decision_at: datetime
    entry_at: datetime
    history_dates: tuple[date, ...] = field(repr=False)
    previous: tuple[tuple[float, ...], ...] = field(repr=False)
    recent: tuple[tuple[float, ...], ...] = field(repr=False)
    momentum: tuple[Decimal, ...] = field(repr=False)
    last_closes: tuple[Decimal, ...] = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _utc(self.decision_at)
        _utc(self.entry_at)
        _vintage(self.vintage_ref)
        _require(type(self.history_dates) is tuple and len(self.history_dates) == 64
                 and all(type(d) is date for d in self.history_dates)
                 and all(a < b for a, b in zip(self.history_dates, self.history_dates[1:],
                                              strict=False))
                 and self.history_dates[-1] == self.decision_at.date()
                 and self.decision_at < self.entry_at, "context_dates")
        _require(type(self.previous) is tuple and type(self.recent) is tuple
                 and len(self.previous) == len(self.recent) == WINDOW, "context_shape")
        object.__setattr__(self, "previous", _window(self.previous))
        object.__setattr__(self, "recent", _window(self.recent))
        _require(type(self.momentum) is tuple and len(self.momentum) == 3
                 and all(type(x) is Decimal and x.is_finite() for x in self.momentum),
                 "context_momentum")
        nav.ThreeAssetPrices(self.last_closes)

    def safe_facts(self):
        return dict(status="ready", symbols=SYMBOLS, window=WINDOW, past_returns=40,
                    momentum_sessions=63, decision_at=self.decision_at.isoformat(),
                    entry_at=self.entry_at.isoformat(), price_basis=PRICE_BASIS, paper_input=False)


def prepare_context(rows_by_symbol, *, scheduled_history, entry_session, decision_at, vintage_ref):
    _calendar(scheduled_history)
    _require(len(scheduled_history) == 64 and type(entry_session) is CrossAssetSession,
             "context_calendar")
    entry_session.__post_init__()
    _utc(decision_at)
    _require(decision_at == scheduled_history[-1].close_at
             and decision_at < entry_session.open_at, "context_cutoff")
    dates = tuple(s.session_date for s in scheduled_history)
    selected = _select(rows_by_symbol, dict.fromkeys(dates, ("close",)), vintage_ref)
    with localcontext(CONTEXT):
        logs = tuple(tuple(rows[d]["close"].ln() for d in dates) for rows in selected)
        returns = tuple(tuple(float(column[j] - column[j - 1]) for column in logs)
                        for j in range(24, 64))
        _require(all(isfinite(v) for row in returns for v in row), "context_numeric")
        momentum = tuple(column[-1] - column[0] for column in logs)
    closes = tuple(rows[dates[-1]]["close"] for rows in selected)
    return AnticorContext(decision_at, entry_session.open_at, dates, returns[:20], returns[20:],
                          momentum, closes, vintage_ref)


def canonical_target(weights):
    """No arbitrary weight repair: only primitive-accepted binary rounding is normalized."""
    exact = _weights(weights)
    with localcontext(CONTEXT):
        values = tuple((Decimal(v.numerator) / Decimal(v.denominator)).quantize(
            QUANTUM, rounding=ROUND_DOWN) for v in exact)
        cash = Decimal(1) - sum(values)
    return nav.ThreeAssetTarget(values, cash)


def _fixed_target(index=None):
    return nav.ThreeAssetTarget(tuple(Decimal(int(i == index)) for i in range(3)),
                                Decimal(int(index is None)))


def _balanced():
    with localcontext(CONTEXT):
        return nav.ThreeAssetTarget((THIRD,) * 3, Decimal(1) - 3 * THIRD)


def decision_target(context, drifted_weights):
    _require(type(context) is AnticorContext, "context_type")
    context.__post_init__()
    return canonical_target(anticor_allocation(context.previous, context.recent, drifted_weights))


@dataclass(frozen=True, slots=True)
class AnticorActions:
    plan: AnticorPlan = field(repr=False)
    vintage_ref: str = field(repr=False)
    targets: Mapping = field(repr=False)

    def __post_init__(self):
        _require(type(self.plan) is AnticorPlan, "plan_type")
        self.plan.__post_init__()
        _vintage(self.vintage_ref)
        _require(isinstance(self.targets, Mapping) and set(self.targets) == set(POLICIES),
                 "action_policies")
        copied = {}
        fixed = dict(balanced=_balanced(), spy=_fixed_target(0), cash=_fixed_target())
        for policy in POLICIES:
            actions = self.targets[policy]
            _require(isinstance(actions, Mapping) and set(actions) == set(self.plan.entries),
                     "action_keys")
            checked = {}
            for day in self.plan.entries:
                target = actions[day]
                _require(type(target) is nav.ThreeAssetTarget, "action_type")
                target.__post_init__()
                if policy in fixed:
                    _require(target == fixed[policy], "fixed_action_mismatch")
                if policy == "momentum63":
                    _require(target in tuple(_fixed_target(i) for i in (None, 0, 1, 2)),
                             "momentum_action")
                if policy == "candidate":
                    _require(target.cash_weight <= 3 * QUANTUM
                             and all((Fraction(w) / Fraction(QUANTUM)).denominator == 1
                                     for w in target.weights3),
                             "candidate_action")
                checked[day] = nav.ThreeAssetTarget(target.weights3, target.cash_weight)
            copied[policy] = MappingProxyType(checked)
        object.__setattr__(self, "targets", MappingProxyType(copied))

    def record(self):
        return dict(plan=self.plan.record(), vintage_ref=self.vintage_ref,
                    targets={p: [[d.isoformat(), *map(str, t.weights3), str(t.cash_weight)]
                                 for d, t in rows.items()] for p, rows in self.targets.items()})


def _stop(deadline):
    if deadline is not None:
        _require(monotonic() < deadline, "compute_stop")


def prepare_actions(rows_by_symbol, plan, vintage_ref, *, deadline=None):
    _require(type(plan) is AnticorPlan, "plan_type")
    plan.__post_init__()
    _vintage(vintage_ref)
    targets = {p: {} for p in POLICIES}
    signal = nav.ThreeAssetState(Decimal(1))
    previous_entry = previous_target = None
    for index in plan.entry_indices:
        _stop(deadline)
        entry = plan.sessions[index]
        history = plan.sessions[index - 64:index]
        context = prepare_context(rows_by_symbol, scheduled_history=history,
                                  entry_session=entry, decision_at=history[-1].close_at,
                                  vintage_ref=vintage_ref)
        drifted = (1 / 3,) * 3
        if previous_entry is not None:
            # The prior execution OPEN is now past. Never inspect the pending current OPEN.
            rows = _select(rows_by_symbol, {previous_entry: ("open",)}, vintage_ref)
            prices = nav.ThreeAssetPrices(tuple(r[previous_entry]["open"] for r in rows))
            with localcontext(CONTEXT):
                signal = nav._rebalance(signal, prices, previous_target.weights3,
                                        previous_target.cash_weight, Decimal(0)).state
                marked = nav.mark_close(signal, nav.ThreeAssetPrices(context.last_closes))
                risky = sum(marked.notionals)
                _require(risky > 0, "signal_risky_empty")
                drifted = tuple(float(v / risky) for v in marked.notionals)
        target = decision_target(context, drifted)
        targets["candidate"][entry.session_date] = target
        targets["balanced"][entry.session_date] = _balanced()
        best = max(range(3), key=lambda i: context.momentum[i])
        targets["momentum63"][entry.session_date] = _fixed_target(
            best if context.momentum[best] > 0 else None)
        targets["spy"][entry.session_date] = _fixed_target(0)
        targets["cash"][entry.session_date] = _fixed_target()
        previous_entry, previous_target = entry.session_date, target
    return AnticorActions(plan, vintage_ref, targets)


def prepare_marks(rows_by_symbol, plan, vintage_ref):
    _require(type(plan) is AnticorPlan, "plan_type")
    plan.__post_init__()
    selected = _select(rows_by_symbol, dict.fromkeys(plan.dates, ("open", "close")), vintage_ref)
    return tuple(nav.ThreeAssetDay(day, tuple(r[day]["open"] for r in selected),
                                   tuple(r[day]["close"] for r in selected)) for day in plan.dates)


@dataclass(frozen=True, slots=True)
class AnticorCell:
    block: int
    policy: str
    cost_bps: Decimal
    observations: int
    entries: int
    growth: Decimal = field(repr=False)
    utility: Decimal = field(repr=False)
    turnover: Decimal = field(repr=False)
    fees: Decimal = field(repr=False)

    def record(self):
        metrics = {k: str(getattr(self, k)) for k in ("growth", "utility", "turnover", "fees")}
        return dict(block=self.block, policy=self.policy, cost_bps=str(self.cost_bps),
                    observations=self.observations, entries=self.entries, status="complete",
                    metrics=metrics)


def evaluate(days, actions, *, deadline=None):
    _require(type(actions) is AnticorActions, "actions_type")
    actions.__post_init__()
    plan = actions.plan
    _require(tuple(d.date for d in days) == plan.dates, "forward_mark_gap")
    cells = []
    for cost in COSTS:
        for policy in POLICIES:
            _stop(deadline)
            ledger = nav.replay(days, actions.targets[policy], cost)
            cut = plan.block_cut
            for block, records, entering in ((0, ledger.daily[:cut], Decimal(1)),
                                             (1, ledger.daily[cut:], ledger.daily[cut - 1].nav)):
                with localcontext(CONTEXT):
                    logs = tuple(d.log_return for d in records)
                    mean = sum(logs) / len(logs)
                    variance = sum((v - mean) ** 2 for v in logs) / len(logs)
                    turnover, previous = Decimal(0), entering
                    for record in records:
                        turnover += record.traded_notional / previous
                        previous = record.nav
                    cells.append(AnticorCell(
                        block, policy, cost, len(records),
                        sum(d.date in actions.targets[policy] for d in records),
                        records[-1].nav / entering - 1, 252 * (mean - 5 * variance),
                        turnover, sum(d.fees for d in records)))
            _stop(deadline)
    return tuple(cells)


def criterion(cells):
    expected = {(b, p, c) for b in (0, 1) for p in POLICIES for c in COSTS}
    _require(type(cells) is tuple and len(cells) == 30
             and all(type(c) is AnticorCell for c in cells), "cell_matrix")
    _require({(c.block, c.policy, c.cost_bps) for c in cells} == expected, "cell_matrix")
    _require(all(type(c.block) is int and type(c.policy) is str
                 and type(c.cost_bps) is Decimal and type(c.observations) is int
                 and c.observations > 0 and type(c.entries) is int
                 and 0 <= c.entries <= c.observations for c in cells), "cell_metadata")
    _require(all(type(v) is Decimal and v.is_finite() for c in cells
                 for v in (c.growth, c.utility, c.turnover, c.fees)), "cell_numeric")
    _require(all(c.growth > -1 and c.turnover >= 0 and c.fees >= 0 for c in cells), "cell_domain")
    for block in (0, 1):
        group = {c.policy: c for c in cells if c.block == block and c.cost_bps == Decimal(10)}
        own = group["candidate"]
        with localcontext(CONTEXT):
            if own.growth <= 0 or any(
                own.growth - group[p].growth <= TOLERANCE
                or own.utility - group[p].utility <= TOLERANCE for p in CONTROLS
            ):
                return dict(candidate="rejected")
    return dict(candidate="development_survivor")

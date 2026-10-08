"""Pure conditional-hedge utility preparation; no IO, fitting or dispatch.

Four heads estimate normalized 21-session episode utilities, not single-asset
log net factors. Cash has a fixed zero score. Episode label normalization never
resets the scored policy capital; whole-period utility is recomputed, not a sum
of episode utilities. Raw-price, seen-development limitations remain unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from thericher_v2.research import kis_cross_asset_relative_allocation as base
from thericher_v2.research import three_asset_nav as nav

NAME = "kis-cross-asset-conditional-hedge-utility-development-v1"
SYMBOLS, HORIZON = base.SYMBOLS, base.HORIZON
CANDIDATES = ("ridge", "gru")
HEADS = ("spy", "spy_tlt", "spy_gld", "balanced")
CONTROLS = HEADS + ("cash",)
POLICIES = CANDIDATES + CONTROLS
TIE_ORDER = ("cash",) + HEADS
COSTS, TARGET_COST, TOLERANCE = base.COSTS, Decimal(5), base.TOLERANCE
INPUT_SHA256 = "4a25284d8ae8538105c798cbc0337ef3ca9615977829eb2d3d951797cbc5dc64"
COMMITMENT_ID = "02b27fdd7b181a1af9598b30db69cc9b9108e746ca7d74c2e5623e2ed0345c10"
AllocationPlan, CrossAssetSession = base.AllocationPlan, base.CrossAssetSession
build_plan, prepare_features = base.build_plan, base.prepare_features
prepare_entry_features, standardize = base.prepare_entry_features, base.standardize
replay_groups = base.replay_groups


def configuration():
    return dict(
        name=NAME, preparation_only=True, symbols=list(SYMBOLS),
        dataset=dict(sha256=INPUT_SHA256, commitment_id=COMMITMENT_ID,
                     scope="2016-02-02..2026-10-07 raw KIS OC; parent binds source archive"),
        features="unchanged asset-major6x63 ln(CLOSE) differences/ln(CLOSE)-ln(OPEN); "
                 "64 prior CLOSEs/63 OPENs; previous scheduled CLOSE decision",
        target="four absolute 21-session first OPEN->terminal CLOSE episode utilities; "
               "252*(mean daily log NAV return-5*population variance), actual5bps/side",
        target_path="normalized initial NAV1 per TRAIN episode; 21 daily CLOSE marks, "
                    "first-return entry fee/final-return liquidation fee; no intermediate trades",
        score_semantics="expected episode utility estimate, not calibrated return/confidence; "
                        "cash exact0, no learned cash head; target utilities unscaled",
        train="unchanged AllocationPlan; label exit<=2020-12-30 CLOSE; "
              "first DEV decision2020-12-31 CLOSE; no same-CLOSE maturity",
        dev_views=[["2021-01-04", "2023-12-29"], ["2024-01-02", "2026-09-30"]],
        geometry=dict(train_entries=1154, dev_groups=68, dev_marks=1442, view_marks=[753, 689],
                      tail_cash_days=14, source="parent-frozen 2016 cohort/calendar metadata"),
        groups="partition all DEV once into21-session groups; tail cash; cross-view carry",
        heads=list(HEADS), tie_order=list(TIE_ORDER),
        actions={name: dict(weights=[str(v) for v in t.weights3], cash=str(t.cash_weight))
                 for name, t in action_table().items()},
        standardization="unchanged TRAIN-only population channel scaler; zero std divisor1; "
                        "no target scaling or DEV fitting",
        ridge=dict(alpha=1, fit_intercept=True, solver="svd", inputs="flattened6x63",
                   output_size=4),
        gru=dict(input_size=6, hidden_size=64, layers=1, output_size=4, dropout=0,
                 seed=101, updates=1024, optimizer="AdamW", lr=0.001, weight_decay=0.01,
                 loss="mean squared four absolute episode utility errors", batch="full",
                 dtype="float32", tf32=False, deterministic=True),
        policies=list(POLICIES), costs_bps_side=[str(c) for c in COSTS], cells=42,
        accounting="one continuous NAV1 per policy/cost, not per episode/view; "
                   "unchanged Decimal50 shared-cash actual-notional fees/group CLOSE exit; "
                   "whole-view utility recomputed, not additive episode scores",
        kill="10bps BOTH views growth>0 AND utility improvement>1e-10 over "
             "ALL five fixed actions; GRU additionally over Ridge; no fallback or rescue",
        relative_growth="descriptive control-relative growth only, not a dominance condition",
        fits=2, seconds=300, selection="one final fit/member; no grid/refit/early stop",
        lineage=[base.NAME, "kis-cross-asset-daily-risk-development-v1",
                 "joint-d1-direct-utility-development-v1-cpu-r2"],
        semantic_identity="conditional multi-asset hedge episode utility; not absolute "
                          "single-asset return argmax, variance forecasting or learned fusion",
        grade="RELATED_SEEN_RAW_PRICE_ONLY_DEVELOPMENT", paper_input=False, holdout="none",
        limitations=["non-PIT", "corporate actions/dividends not applied",
                     "provider availability/finality not observed", "ideal fractional fills",
                     "overlapping TRAIN labels/contexts, not independent samples",
                     "episode utility regression is not whole-period utility optimization"],
    )


def action_table():
    """Named SPY/TLT/GLD positions; never use the legacy ledger SYMBOLS mapping."""
    half, zero = Decimal("0.5"), Decimal(0)
    return MappingProxyType(dict(
        spy=base.unit_target(0),
        spy_tlt=nav.ThreeAssetTarget((half, half, zero), zero),
        spy_gld=nav.ThreeAssetTarget((half, zero, half), zero),
        balanced=base.balanced_target(), cash=base.unit_target(),
    ))


def select_action(scores):
    base._require(type(scores) is tuple and len(scores) == 4, "prediction_shape")
    base._require(all(type(v) is Decimal and v.is_finite() for v in scores),
                  "prediction_nonfinite")
    best = max(range(4), key=lambda i: scores[i])
    return action_table()[HEADS[best] if scores[best] > 0 else "cash"]


@dataclass(frozen=True, slots=True)
class Utility21Target:
    entry_at: datetime
    exit_at: datetime
    utilities: tuple[Decimal, ...] = field(repr=False)
    net_factors: tuple[Decimal, ...] = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        base._utc(self.entry_at)
        base._utc(self.exit_at)
        base._vintage(self.vintage_ref)
        base._require(self.entry_at < self.exit_at, "target_time")
        base._require(type(self.utilities) is tuple and len(self.utilities) == 4
                      and all(type(v) is Decimal and v.is_finite() for v in self.utilities),
                      "target_utility_shape")
        base._require(type(self.net_factors) is tuple and len(self.net_factors) == 4,
                      "target_factor_shape")
        for factor in self.net_factors:
            base._positive(factor)

    @property
    def cash_utility(self):
        return Decimal(0)

    def safe_facts(self):
        return dict(kind="conditional_hedge_utility21_target", heads=HEADS, sessions=21,
                    cost_bps_side=5, cash_head="fixed_zero_not_learned",
                    entry_at=self.entry_at.isoformat(), exit_at=self.exit_at.isoformat(),
                    normalized_episode="label_only_not_policy_capital_reset", paper_input=False)


@nav._decimal
def build_utility_target(rows_by_symbol, *, scheduled_forward, vintage_ref):
    """TRAIN-only caller scope; all 21 CLOSEs are mandatory, unlike endpoint returns."""
    base._calendar(scheduled_forward)
    base._require(len(scheduled_forward) == HORIZON, "target_calendar")
    first, last = scheduled_forward[0], scheduled_forward[-1]
    required = {s.session_date: ("close",) for s in scheduled_forward}
    required[first.session_date] = ("open", "close")
    rows = base._select(rows_by_symbol, required, vintage_ref)
    days = []
    for i, session in enumerate(scheduled_forward):
        closes = tuple(r[session.session_date]["close"] for r in rows)
        # Only first OPEN is executable; later OPEN slots are unused ledger placeholders.
        opens = tuple(r[session.session_date]["open"] for r in rows) if i == 0 else closes
        days.append(nav.ThreeAssetDay(session.session_date, opens, closes))
    utilities, factors = [], []
    for name in HEADS:
        trace = nav.replay(days, {first.session_date: action_table()[name]}, TARGET_COST)
        utilities.append(Decimal(base._metrics(trace.daily, Decimal(1))["utility"]))
        factors.append(trace.final_nav)
    return Utility21Target(first.open_at, last.close_at, tuple(utilities), tuple(factors),
                           vintage_ref)


def prepare_train_target(rows_by_symbol, *, plan, entry_index, vintage_ref):
    plan.__post_init__()
    base._require(entry_index in plan.train_indices, "target_not_train")
    return build_utility_target(rows_by_symbol,
                                scheduled_forward=plan.sessions[entry_index:entry_index + HORIZON],
                                vintage_ref=vintage_ref)


@dataclass(frozen=True, slots=True)
class HedgeActionSeal:
    plan: AllocationPlan = field(repr=False)
    vintage_ref: str = field(repr=False)
    actions: Mapping = field(repr=False)

    def __post_init__(self):
        base._require(type(self.plan) is AllocationPlan, "plan_type")
        self.plan.__post_init__()
        base._vintage(self.vintage_ref)
        base._require(isinstance(self.actions, Mapping) and set(self.actions) == set(POLICIES),
                      "action_policies")
        entries, table, copied = tuple(g[0] for g in self.plan.groups), action_table(), {}
        for policy in POLICIES:
            actions = self.actions[policy]
            base._require(isinstance(actions, Mapping) and set(actions) == set(entries),
                          "action_keys")
            targets = {}
            for day in entries:
                target = actions[day]
                base._require(type(target) is nav.ThreeAssetTarget, "action_type")
                target.__post_init__()
                base._require(target == table[policy] if policy in CONTROLS
                              else target in table.values(), "policy_allocation")
                targets[day] = nav.ThreeAssetTarget(target.weights3, target.cash_weight)
            copied[policy] = MappingProxyType(targets)
        object.__setattr__(self, "actions", MappingProxyType(copied))

    def record(self):
        return dict(semantic_identity=NAME, plan=self.plan.record(), vintage_ref=self.vintage_ref,
                    targets={p: [[d.isoformat(), *map(str, t.weights3), str(t.cash_weight)]
                                 for d, t in rows.items()] for p, rows in self.actions.items()})


def prepare_actions(predictions, dev_features, *, plan, vintage_ref):
    """No forward rows or costs: seal every candidate/control action before payoff access."""
    plan.__post_init__()
    entries = tuple(g[0] for g in plan.groups)
    base._require(isinstance(predictions, Mapping) and set(predictions) == set(CANDIDATES)
                  and all(isinstance(p, Mapping) and set(p) == set(entries)
                          for p in predictions.values()), "prediction_keys")
    base._require(isinstance(dev_features, Mapping) and set(dev_features) == set(entries),
                  "feature_keys")
    table, actions = action_table(), {p: {} for p in POLICIES}
    for day, i in zip(entries, plan.group_indices, strict=True):
        features = dev_features[day]
        features.__post_init__()
        base._require(features.vintage_ref == vintage_ref
                      and features.entry_at == plan.sessions[i].open_at
                      and features.decision_at == plan.sessions[i - 1].close_at
                      and features.observation_dates
                      == tuple(s.session_date for s in plan.sessions[i - 63:i]), "feature_binding")
        for candidate in CANDIDATES:
            actions[candidate][day] = select_action(predictions[candidate][day])
        for control in CONTROLS:
            actions[control][day] = table[control]
    return HedgeActionSeal(plan, vintage_ref, actions)


def prepare_marks(rows_by_symbol, *, plan, vintage_ref):
    plan.__post_init__()
    rows = base._select(rows_by_symbol, dict.fromkeys(plan.dates, ("open", "close")), vintage_ref)
    return tuple(nav.ThreeAssetDay(day, tuple(r[day]["open"] for r in rows),
                                    tuple(r[day]["close"] for r in rows)) for day in plan.dates)


@nav._decimal
def evaluate(days, seal):
    base._require(type(seal) is HedgeActionSeal, "action_seal")
    seal = HedgeActionSeal(seal.plan, seal.vintage_ref, seal.actions)
    records = tuple(days)
    base._require(tuple(d.date for d in records) == seal.plan.dates, "forward_mark_gap")
    cells, cut = [], seal.plan.block_cut
    for cost in COSTS:
        for policy in POLICIES:
            trace = replay_groups(records, seal.actions[policy], plan=seal.plan, cost_bps=cost)
            for block, subset, entering in (
                (0, trace.daily[:cut], Decimal(1)),
                (1, trace.daily[cut:], trace.daily[cut - 1].nav),
            ):
                cells.append(dict(policy=policy, cost_bps=str(cost), block=block,
                                  metrics=base._metrics(subset, entering)))
    by_key = {(c["block"], c["policy"], c["cost_bps"]): c["metrics"] for c in cells}
    for cell in cells:
        candidate = cell["policy"]
        if candidate in CANDIDATES:
            controls = CONTROLS + (("ridge",) if candidate == "gru" else ())
            cell["control_relative_growth"] = {
                p: str(Decimal(cell["metrics"]["growth"])
                       - Decimal(by_key[cell["block"], p, cell["cost_bps"]]["growth"]))
                for p in controls}
    return cells


@nav._decimal
def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    base._require(len(cells) == 42
                  and {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == expected,
                  "cell_matrix")
    base._require(all(type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
                      for c in cells for k in ("growth", "utility")), "cell_metrics")
    verdicts = {}
    for candidate in CANDIDATES:
        controls, passed = CONTROLS + (("ridge",) if candidate == "gru" else ()), True
        for block in (0, 1):
            group = {c["policy"]: c["metrics"] for c in cells
                     if c["block"] == block and c["cost_bps"] == "10"}
            own = group[candidate]
            passed &= Decimal(own["growth"]) > 0 and all(
                Decimal(own["utility"]) - Decimal(group[p]["utility"]) > TOLERANCE
                for p in controls)
        verdicts[candidate] = "development_survivor" if passed else "rejected"
    return verdicts

"""Pure paired campaign preparation; no IO, models, fits or broker effects.

TRAIN labels are nominal-flat episode values, not state-conditioned continuous
DEV counterfactuals. Revised raw prices/rates remain seen, non-PIT and non-TR.
Accounting and curve selection delegate to the released pure role APIs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from types import MappingProxyType

from thericher_v2.data.h15_curve_state import H15CurveState, select_h15_curve_state
from thericher_v2.research import kis_cross_asset_relative_allocation as base
from thericher_v2.research import whole_share_portfolio_nav as whole
from thericher_v2.research.cross_asset_daily_risk_input import DailyRiskFeatures
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable
from thericher_v2.research.cross_asset_hedge_failure_input import CONTEXT
from thericher_v2.research.joint_portfolio_covariance import _population_covariance
from thericher_v2.research.whole_share_quote_projection import project_quote

NAME = "kis-lagged-rate-whole-share-policy-development-v1"
SYMBOLS, HORIZON = base.SYMBOLS, 21
HEADS = ("spy", "spy_tlt", "spy_gld", "balanced")
CONTROLS = HEADS + ("cash",)
CANDIDATES = ("ridge_price", "ridge_rates", "gru_price", "gru_rates")
POLICIES = CANDIDATES + CONTROLS
COSTS = (Decimal("2.5"), Decimal(5), Decimal(10))
TARGET_COST, BANK, BASIS = Decimal(5), Fraction(10000), Fraction(100000)
FITS = 4
COHORT_START = date(2016, 2, 2)
TOLERANCE = Decimal("1e-10")
_require = base._require


def configuration():
    return dict(
        name=NAME,
        preparation_only=True,
        symbols=list(SYMBOLS),
        input_sha256="4a25284d8ae8538105c798cbc0337ef3ca9615977829eb2d3d951797cbc5dc64",
        rates_sha256="d7bd515cfa34d957cb9af62377052e51e24c899c637dc4a5e95c752416ba3d5c",
        features="asset-major6x63 log CLOSE differences/log CLOSE minus log OPEN; "
        "253 prior CLOSE covariance support; final three rate factors only",
        rates="same-date3M/2Y/10Y: mean,10Y-3M,2*2Y-3M-10Y; percentage points; "
        "decision ET date minus30 calendar days; age<=7; no individual carry",
        covariance="252 simple returns/population/.9C+.1diag(C); risk cap.10 annual",
        actions=list(CONTROLS),
        tie_order=["cash", *HEADS],
        target="four5bps 21-session nominal-flat whole-share episode utilities; "
        "252*(mean daily log NAV return-5*population variance)",
        target_limitation="state-omitted nominal-flat labels are not exact counterfactuals "
        "for evolving DEV balances; integer replay is not scale invariant",
        train="253-session warmup; all label exits<=2020-12-30",
        dev_views=[["2021-01-04", "2023-12-29"], ["2024-01-02", "2026-09-30"]],
        groups="partition entire DEV once into21; group CLOSE liquidation; tail cash; "
        "retain capital across groups and view boundary",
        accounting="basis100000/bank10000 once; analytical fees separate from gross cash; "
        "synthetic projected OPEN/CLOSE fills and marks, not exact raw or broker quotes; "
        "immediate terminal fills; "
        "SELL before BUY; fee-unaffordable exact action no-intent/no clipping",
        quote_grid=".01 nearest-cent ties-even synthetic fill/mark projection only; "
        "raw information preserved in price features and covariance",
        scaler="shared TRAIN population price channel scaler; final3 rate scaler; "
        "zero std divisor1; no target scaling; price-only rate slots zero",
        ridge=dict(alpha=1, solver="svd", fit_intercept=True, inputs=381, heads=4),
        gru=dict(
            input_size=6,
            hidden_size=64,
            layers=1,
            output_size=4,
            head_inputs=67,
            updates=512,
            seed=101,
            optimizer="AdamW",
            lr=0.001,
            weight_decay=0.01,
            dropout=0,
            batch="full",
            loss="unscaled four-head MSE",
            dtype="float32",
            initialization="clone identical seed101 state; independent fresh optimizers",
            deterministic=True,
            tf32=False,
        ),
        cells=54,
        fits=4,
        seconds=600,
        costs_bps_side=[str(c) for c in COSTS],
        kill="10bps BOTH views: each rates member growth>0 and utility improvement>1e-10 "
        "over matched price member AND all5 fixed controls",
        holdout="none",
        paper_input=False,
        interest=0,
        latency=0,
        slippage=0,
        limitations=[
            "seen revised non-PIT/non-TR prices and rates",
            "no broker parity",
            "publication/finality not observed",
            "overlapping TRAIN labels not ESS",
            "state-omitted nominal-flat target approximation",
        ],
        lineage=[
            "kis-cross-asset-conditional-hedge-utility-development-v1",
            "kis-learned-stateful-rebalance-development-v1",
            "kis-whole-share-fixed-bank-replay-parity-v1",
        ],
    )


@dataclass(frozen=True, slots=True)
class CampaignPlan:
    sessions: tuple = field(repr=False)
    train_indices: tuple[int, ...] = field(repr=False)
    dev_indices: tuple[int, ...] = field(repr=False)
    block_cut: int

    def __post_init__(self):
        original = base.build_plan(self.sessions)
        expected = tuple(
            i
            for i in original.train_indices
            if i >= 253 and original.sessions[i - 253].session_date >= COHORT_START
        )
        _require(bool(expected) and self.train_indices == expected, "train_warmup")
        _require(
            self.dev_indices == original.dev_indices and self.block_cut == original.block_cut,
            "plan_geometry",
        )

    @property
    def dates(self):
        return tuple(self.sessions[i].session_date for i in self.dev_indices)

    @property
    def group_indices(self):
        n = len(self.dev_indices) - len(self.dev_indices) % HORIZON
        return self.dev_indices[:n:HORIZON]

    @property
    def groups(self):
        return tuple(
            tuple(s.session_date for s in self.sessions[i : i + HORIZON])
            for i in self.group_indices
        )

    def record(self):
        self.__post_init__()
        return dict(
            train_entries=[self.sessions[i].session_date.isoformat() for i in self.train_indices],
            train_exits=[
                self.sessions[i + 20].session_date.isoformat() for i in self.train_indices
            ],
            dates=[d.isoformat() for d in self.dates],
            groups=[[d.isoformat() for d in g] for g in self.groups],
            block_cut=self.block_cut,
            tail_cash_days=len(self.dates) % HORIZON,
            independent_sample_count="not_claimed",
            calendar_attestation="caller",
        )


def build_plan(sessions):
    old = base.build_plan(sessions)
    return CampaignPlan(
        sessions,
        tuple(
            i
            for i in old.train_indices
            if i >= 253 and old.sessions[i - 253].session_date >= COHORT_START
        ),
        old.dev_indices,
        old.block_cut,
    )


def action_table():
    z, o, half, third = Fraction(0), Fraction(1), Fraction(1, 2), Fraction(1, 3)
    return MappingProxyType(
        dict(
            spy=(o, z, z),
            spy_tlt=(half, half, z),
            spy_gld=(half, z, half),
            balanced=(third,) * 3,
            cash=(z,) * 3,
        )
    )


def _selected(rows, required, vintage):
    return base._select(rows, required, vintage)


def _scaled_actions(covariance):
    result = {}
    with localcontext(CONTEXT):
        for name, weights in action_table().items():
            variance = 252 * sum(
                (weights[i] * covariance[i][j] * weights[j] for i in range(3) for j in range(3)),
                Fraction(0),
            )
            _require(variance >= 0, "covariance_invalid")
            vol = (Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()
            scale = min(Decimal(1), Decimal(".1") / vol) if vol else Decimal(1)
            while variance * Fraction(scale) ** 2 > Fraction(1, 100):
                scale = scale.next_minus()
            result[name] = tuple(w * Fraction(scale) for w in weights)
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class PreparedEntry:
    price: DailyRiskFeatures = field(repr=False)
    rates3: tuple[Decimal, ...] = field(repr=False)
    actions: Mapping = field(repr=False)
    covariance3: tuple = field(repr=False)
    curve: H15CurveState = field(repr=False)

    def __post_init__(self):
        _require(type(self.price) is DailyRiskFeatures, "feature_type")
        self.price.__post_init__()
        _require(type(self.curve) is H15CurveState, "rate_state_invalid")
        self.curve.__post_init__()
        _require(
            self.curve.status == "available" and self.curve.decision_at == self.price.decision_at,
            "rate_state_unavailable",
        )
        with localcontext(CONTEXT):
            expected_rates = tuple(
                Decimal(v.numerator) / Decimal(v.denominator) for v in self.curve.factors_percent
            )
        _require(
            type(self.rates3) is tuple
            and len(self.rates3) == 3
            and all(type(v) is Decimal and v.is_finite() for v in self.rates3),
            "rate_shape",
        )
        _require(self.rates3 == expected_rates, "rate_binding")
        _require(
            type(self.covariance3) is tuple
            and len(self.covariance3) == 3
            and all(
                type(r) is tuple and len(r) == 3 and all(type(v) is Fraction for v in r)
                for r in self.covariance3
            ),
            "covariance_shape",
        )
        _require(
            all(
                self.covariance3[i][j] == self.covariance3[j][i] for i in range(3) for j in range(3)
            ),
            "covariance_symmetry",
        )
        c = self.covariance3
        determinant = (
            c[0][0] * (c[1][1] * c[2][2] - c[1][2] ** 2)
            - c[0][1] * (c[0][1] * c[2][2] - c[1][2] * c[0][2])
            + c[0][2] * (c[0][1] * c[1][2] - c[1][1] * c[0][2])
        )
        _require(
            all(c[i][i] >= 0 for i in range(3))
            and determinant >= 0
            and all(
                c[i][i] * c[j][j] - c[i][j] ** 2 >= 0 for i in range(3) for j in range(i + 1, 3)
            ),
            "covariance_not_psd",
        )
        expected = _scaled_actions(self.covariance3)
        _require(
            isinstance(self.actions, Mapping) and dict(self.actions) == dict(expected),
            "action_scaling",
        )
        object.__setattr__(self, "actions", MappingProxyType(dict(expected)))

    def safe_facts(self):
        return dict(
            kind="lagged_rates_integer_entry",
            price_shape=(6, 63),
            rates=3,
            covariance_closes=253,
            decision_at=self.price.decision_at.isoformat(),
            entry_at=self.price.entry_at.isoformat(),
            paper_input=False,
        )


def prepare_entry(rows_by_symbol, *, plan, entry_index, vintage_ref, curve_snapshot):
    """Select only required past keys; rates never affect covariance or action scaling."""
    import numpy as np

    plan.__post_init__()
    _require(entry_index in plan.train_indices + plan.group_indices, "entry_scope")
    history = plan.sessions[entry_index - 253 : entry_index]
    required = {s.session_date: ("close",) for s in history}
    for s in history[-63:]:
        required[s.session_date] = ("open", "close")
    selected = _selected(rows_by_symbol, required, vintage_ref)
    price = base.prepare_features(
        rows_by_symbol,
        scheduled_history=history[-64:],
        entry_session=plan.sessions[entry_index],
        decision_at=history[-1].close_at,
        vintage_ref=vintage_ref,
    )
    try:
        exact_returns = tuple(
            tuple(
                Fraction(col[b.session_date]["close"]) / Fraction(col[a.session_date]["close"]) - 1
                for col in selected
            )
            for a, b in zip(history, history[1:], strict=False)
        )
        returns = np.asarray(exact_returns, dtype=np.float64)
        _require(np.isfinite(returns).all() and (returns > -1).all(), "return_numeric")
        _require(
            all(
                original == 0 or converted != 0
                for row, values in zip(exact_returns, returns, strict=True)
                for original, converted in zip(row, values, strict=True)
            ),
            "return_numeric",
        )
        covariance = _population_covariance(returns)
        covariance = 0.9 * covariance + 0.1 * np.diag(np.diag(covariance))
        _require(np.isfinite(covariance).all(), "covariance_numeric")
    except (ArithmeticError, ValueError) as error:
        if isinstance(error, CrossAssetInputUnavailable):
            raise
        raise CrossAssetInputUnavailable("covariance_numeric") from None
    exact = tuple(tuple(Fraction(float(v)) for v in r) for r in covariance)
    curve = select_h15_curve_state(curve_snapshot, decision_at=price.decision_at)
    _require(curve.status == "available", "rate_state_unavailable")
    with localcontext(CONTEXT):
        rates = tuple(Decimal(v.numerator) / Decimal(v.denominator) for v in curve.factors_percent)
    return PreparedEntry(price, rates, _scaled_actions(exact), exact, curve)


@dataclass(frozen=True, slots=True, repr=False)
class PairedScaledInputs:
    train_price: object
    dev_price: object
    train_rates: object
    dev_rates: object
    price_mean: object
    price_divisor: object
    rate_mean: object
    rate_divisor: object

    def ridge_inputs(self, *, augmented):
        import numpy as np

        _require(type(augmented) is bool, "arm_invalid")
        return tuple(
            np.concatenate((p.reshape(len(p), 378), r if augmented else np.zeros_like(r)), axis=1)
            for p, r in ((self.train_price, self.train_rates), (self.dev_price, self.dev_rates))
        )


def standardize(train_entries, dev_entries):
    import numpy as np

    for entries in (train_entries, dev_entries):
        _require(type(entries) is tuple and bool(entries), "scaler_rows")
        for entry in entries:
            _require(type(entry) is PreparedEntry, "feature_type")
            entry.__post_init__()
    price = base.standardize(
        [e.price.features for e in train_entries], [e.price.features for e in dev_entries]
    )
    train = np.asarray([e.rates3 for e in train_entries], dtype=np.float64)
    dev = np.asarray([e.rates3 for e in dev_entries], dtype=np.float64)
    _require(np.isfinite(train).all() and np.isfinite(dev).all(), "rate_numeric")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            mean, std = train.mean(axis=0), train.std(axis=0, ddof=0)
            divisor = np.where(std == 0, 1.0, std)
            a, b = (train - mean) / divisor, (dev - mean) / divisor
        except FloatingPointError:
            raise CrossAssetInputUnavailable("rate_scaler_numeric") from None
    _require(all(np.isfinite(v).all() for v in (mean, divisor, a, b)), "rate_scaler_numeric")
    for v in (mean, divisor, a, b):
        v.flags.writeable = False
    return PairedScaledInputs(
        price.train, price.dev, a, b, price.mean, price.divisor, mean, divisor
    )


def select_action(scores):
    _require(
        type(scores) is tuple
        and len(scores) == 4
        and all(type(v) is Decimal and v.is_finite() for v in scores),
        "prediction_invalid",
    )
    best = max(range(4), key=lambda i: scores[i])
    return HEADS[best] if scores[best] > 0 else "cash"


@dataclass(frozen=True, slots=True)
class ActionSeal:
    plan: CampaignPlan = field(repr=False)
    vintage_ref: str = field(repr=False)
    actions: Mapping = field(repr=False)
    entries: Mapping = field(repr=False)
    predictions: Mapping = field(repr=False)

    def __post_init__(self):
        _require(type(self.plan) is CampaignPlan, "plan_type")
        self.plan.__post_init__()
        base._vintage(self.vintage_ref)
        entries = {g[0] for g in self.plan.groups}
        _require(isinstance(self.entries, Mapping) and set(self.entries) == entries, "feature_keys")
        _require(
            isinstance(self.predictions, Mapping)
            and set(self.predictions) == set(CANDIDATES)
            and all(
                isinstance(v, Mapping) and set(v) == entries for v in self.predictions.values()
            ),
            "prediction_keys",
        )
        for i in self.plan.group_indices:
            entry = self.entries[self.plan.sessions[i].session_date]
            _require(type(entry) is PreparedEntry, "feature_type")
            entry.__post_init__()
            _require(
                entry.price.vintage_ref == self.vintage_ref
                and entry.price.entry_at == self.plan.sessions[i].open_at
                and entry.price.decision_at == self.plan.sessions[i - 1].close_at
                and entry.price.observation_dates
                == tuple(s.session_date for s in self.plan.sessions[i - 63 : i]),
                "feature_binding",
            )
        _require(
            isinstance(self.actions, Mapping) and set(self.actions) == set(POLICIES), "policy_keys"
        )
        frozen = {}
        for name, actions in self.actions.items():
            _require(isinstance(actions, Mapping) and set(actions) == entries, "action_keys")
            copied = {}
            for day, weights in actions.items():
                _require(
                    type(weights) is tuple
                    and len(weights) == 3
                    and all(type(v) is Fraction and v >= 0 for v in weights)
                    and sum(weights) <= 1,
                    "action_weights",
                )
                choice = select_action(self.predictions[name][day]) if name in CANDIDATES else name
                _require(weights == self.entries[day].actions[choice], "action_binding")
                copied[day] = weights
            frozen[name] = MappingProxyType(copied)
        object.__setattr__(self, "actions", MappingProxyType(frozen))
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))
        object.__setattr__(
            self,
            "predictions",
            MappingProxyType({p: MappingProxyType(dict(v)) for p, v in self.predictions.items()}),
        )


def seal_actions(predictions, entries, *, plan, vintage_ref):
    plan.__post_init__()
    keys = {g[0] for g in plan.groups}
    _require(isinstance(entries, Mapping) and set(entries) == keys, "feature_keys")
    _require(
        isinstance(predictions, Mapping)
        and set(predictions) == set(CANDIDATES)
        and all(isinstance(v, Mapping) and set(v) == keys for v in predictions.values()),
        "prediction_keys",
    )
    actions = {p: {} for p in POLICIES}
    for i in plan.group_indices:
        day, entry = plan.sessions[i].session_date, entries[plan.sessions[i].session_date]
        _require(type(entry) is PreparedEntry, "feature_type")
        entry.__post_init__()
        _require(
            entry.price.vintage_ref == vintage_ref
            and entry.price.decision_at == plan.sessions[i - 1].close_at
            and entry.price.entry_at == plan.sessions[i].open_at
            and entry.price.observation_dates
            == tuple(s.session_date for s in plan.sessions[i - 63 : i]),
            "feature_binding",
        )
        for policy in POLICIES:
            choice = select_action(predictions[policy][day]) if policy in CANDIDATES else policy
            actions[policy][day] = entry.actions[choice]
    return ActionSeal(plan, vintage_ref, actions, entries, predictions)


def prepare_marks(rows_by_symbol, *, plan, vintage_ref, ledger=whole):
    plan.__post_init__()
    rows = _selected(rows_by_symbol, dict.fromkeys(plan.dates, ("open", "close")), vintage_ref)
    return tuple(
        ledger.WholeShareDay(
            d,
            tuple(project_quote(r[d]["open"]) for r in rows),
            tuple(project_quote(r[d]["close"]) for r in rows),
        )
        for d in plan.dates
    )


def _initial(ledger):
    return ledger.WholeShareState(
        BANK, Fraction(0), (0, 0, 0), (Fraction(0),) * 3, basis_usd=BASIS, allocated_usd=BANK
    )


def _metrics(navs, entering):
    _require(bool(navs) and entering > 0 and all(v > 0 for v in navs), "nav_invalid")
    with localcontext(CONTEXT):
        previous, logs = entering, []
        for value in navs:
            factor = Fraction(value) / Fraction(previous)
            logs.append((Decimal(factor.numerator) / Decimal(factor.denominator)).ln())
            previous = value
        mean = sum(logs, Decimal(0)) / len(logs)
        variance = sum(((v - mean) ** 2 for v in logs), Decimal(0)) / len(logs)
        growth = Fraction(navs[-1]) / Fraction(entering) - 1
        return dict(
            growth=str(Decimal(growth.numerator) / Decimal(growth.denominator)),
            utility=str(252 * (mean - 5 * variance)),
            days=len(navs),
        )


@dataclass(frozen=True, slots=True)
class EpisodeTarget:
    entry_date: date
    exit_date: date
    utilities: tuple[Decimal, ...] = field(repr=False)

    def __post_init__(self):
        _require(
            type(self.entry_date) is date
            and type(self.exit_date) is date
            and self.entry_date < self.exit_date,
            "target_dates",
        )
        _require(
            type(self.utilities) is tuple
            and len(self.utilities) == 4
            and all(type(v) is Decimal and v.is_finite() for v in self.utilities),
            "target_shape",
        )

    @property
    def cash_utility(self):
        """Only this label's initial-flat, zero-interest, no-trade cash episode."""
        return Decimal(0)

    def safe_facts(self):
        return dict(
            kind="nominal_flat_integer_utility21",
            heads=4,
            sessions=21,
            cost_bps=5,
            entry_date=self.entry_date.isoformat(),
            exit_date=self.exit_date.isoformat(),
            state_omitted=True,
            paper_input=False,
        )


def prepare_train_targets(rows_by_symbol, *, plan, entry_index, vintage_ref, entry, ledger=whole):
    """Real ledger dependency; no fractional predecessor labels or capital rescaling."""
    plan.__post_init__()
    _require(entry_index in plan.train_indices and type(entry) is PreparedEntry, "target_scope")
    entry.__post_init__()
    _require(
        entry.price.entry_at == plan.sessions[entry_index].open_at
        and entry.price.decision_at == plan.sessions[entry_index - 1].close_at
        and entry.price.vintage_ref == vintage_ref,
        "target_binding",
    )
    forward = plan.sessions[entry_index : entry_index + HORIZON]
    required = {s.session_date: ("close",) for s in forward}
    required[forward[0].session_date] = ("open", "close")
    rows = _selected(rows_by_symbol, required, vintage_ref)
    days = tuple(
        ledger.WholeShareDay(
            s.session_date,
            tuple(project_quote(r[s.session_date]["open" if i == 0 else "close"]) for r in rows),
            tuple(project_quote(r[s.session_date]["close"]) for r in rows),
        )
        for i, s in enumerate(forward)
    )
    utilities = []
    for action in HEADS:
        trace = ledger.replay(
            days,
            {days[0].date: entry.actions[action]},
            TARGET_COST,
            initial_state=_initial(ledger),
            liquidate_last_close=True,
        )
        utilities.append(
            Decimal(_metrics(tuple(d.mark.net_nav for d in trace.daily), BANK)["utility"])
        )
    return EpisodeTarget(forward[0].session_date, forward[-1].session_date, tuple(utilities))


def evaluate(days, seal, *, ledger=whole):
    _require(type(seal) is ActionSeal, "seal_type")
    seal = ActionSeal(seal.plan, seal.vintage_ref, seal.actions, seal.entries, seal.predictions)
    records = tuple(days)
    _require(tuple(d.date for d in records) == seal.plan.dates, "forward_mark_gap")
    cells = []
    for cost in COSTS:
        for policy in POLICIES:
            state, navs = _initial(ledger), []
            n = len(records) - len(records) % HORIZON
            for start in range(0, n, HORIZON):
                block = records[start : start + HORIZON]
                _require(state.quantities3 == (0, 0, 0), "group_entry_not_flat")
                trace = ledger.replay(
                    block,
                    {block[0].date: seal.actions[policy][block[0].date]},
                    cost,
                    initial_state=state,
                    liquidate_last_close=True,
                )
                state = trace.final_state
                navs.extend(d.mark.net_nav for d in trace.daily)
            if n < len(records):
                trace = ledger.replay(
                    records[n:], {}, cost, initial_state=state, liquidate_last_close=True
                )
                state = trace.final_state
                navs.extend(d.mark.net_nav for d in trace.daily)
            _require(
                state.quantities3 == (0, 0, 0)
                and state.allocated_usd == BANK
                and state.basis_usd == BASIS,
                "terminal_bank_or_inventory",
            )
            cut = seal.plan.block_cut
            for view, values, entering in ((0, navs[:cut], BANK), (1, navs[cut:], navs[cut - 1])):
                cells.append(
                    dict(
                        policy=policy,
                        cost_bps=str(cost),
                        view=view,
                        metrics=_metrics(tuple(values), entering),
                    )
                )
    return cells


def criterion(cells):
    expected = {(p, str(c), v) for p in POLICIES for c in COSTS for v in (0, 1)}
    _require(
        len(cells) == 54 and {(c["policy"], c["cost_bps"], c["view"]) for c in cells} == expected,
        "cell_matrix",
    )
    lookup = {}
    for cell in cells:
        metrics = cell["metrics"]
        _require(
            all(
                type(metrics[k]) is str and Decimal(metrics[k]).is_finite()
                for k in ("growth", "utility")
            ),
            "cell_metrics",
        )
        lookup[cell["policy"], cell["cost_bps"], cell["view"]] = metrics
    verdicts = {}
    for rates, price in (("ridge_rates", "ridge_price"), ("gru_rates", "gru_price")):
        passed = True
        with localcontext(CONTEXT):
            for view in (0, 1):
                own = lookup[rates, "10", view]
                passed &= Decimal(own["growth"]) > 0
                passed &= all(
                    Decimal(own["utility"]) - Decimal(lookup[p, "10", view]["utility"]) > TOLERANCE
                    for p in (price,) + CONTROLS
                )
        verdicts[rates] = "survived_development" if passed else "rejected"
    return verdicts

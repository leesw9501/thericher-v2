"""Pure causal whole-share HOLD/rebalance preparation and sequential replay.

No fitting, IO or broker effects. TRAIN behaviour states are not candidate-policy
states; 21-CLOSE counterfactuals omit subsequent decisions and terminal sales.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from types import MappingProxyType

from thericher_v2.research import kis_cross_asset_relative_allocation as base
from thericher_v2.research import kis_lagged_rate_whole_share_policy_development as prior
from thericher_v2.research import whole_share_portfolio_nav as whole
from thericher_v2.research.cross_asset_daily_risk_input import DailyRiskFeatures
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable
from thericher_v2.research.cross_asset_hedge_failure_input import CONTEXT, RawD1Price
from thericher_v2.research.joint_portfolio_covariance import _population_covariance
from thericher_v2.research.whole_share_quote_projection import project_quote

SYMBOLS, HORIZON, BANK, BASIS = prior.SYMBOLS, prior.HORIZON, prior.BANK, prior.BASIS
COSTS, TOLERANCE = prior.COSTS, prior.TOLERANCE
TRAIN_COST = Decimal(10)
BEHAVIOURS = ("always", "buyonce")
POLICIES = ("state", "price", "always", "buyonce", "cash")
HOLD, REBALANCE = "hold", "rebalance"
_require = base._require


@dataclass(frozen=True, slots=True)
class CampaignPlan(prior.CampaignPlan):
    def record(self):
        record = prior.CampaignPlan.record(self)
        record["tail_hold_days"] = record.pop("tail_cash_days")
        return record


def build_plan(sessions):
    plan = prior.build_plan(sessions)
    return CampaignPlan(plan.sessions, plan.train_indices, plan.dev_indices, plan.block_cut)


def configuration():
    return dict(
        name="kis-whole-share-hold-rebalance-payoff-alignment-v1",
        preparation_only=True,
        input_sha256=prior.configuration()["input_sha256"],
        price_features="raw6x63;253 prior CLOSEs/252 population returns/.9C+.1diag(C)",
        action="HOLD or next OPEN balanced thirds scaled to .10 desired annual risk",
        state="quantities3,entrycosts3/BANK,grosscash/BANK,fees/BANK,projected priorCLOSE3/BANK",
        train="two causal behaviours; every eligible prior CLOSE; 10bps; paired rows",
        behaviour="always every21 scheduled sessions; buyonce first attempt only; no resets",
        target="21 CLOSE utility difference from identical prior-CLOSE netNAV; "
        "one action then HOLD; no horizon liquidation",
        structural_stop="no paired-state preferred-action difference; delta>0 rebalance else HOLD",
        scaler="shared paired TRAIN population price-channel/state-column scalers; "
        "zero std divisor1; price-only state slots zero; targets unscaled",
        ridge=dict(alpha=1, solver="svd", fit_intercept=True, inputs=389, outputs=1),
        policies=list(POLICIES),
        dev="continuous across both views;68 complete21 groups;tail14 HOLD; "
        "final study CLOSE liquidation only; per-decision seal before execution quote access",
        accounting="basis100000/bank10000 once; SELL before BUY; whole floors; "
        "atomic infeasibility preserves state; fees separate from gross cash",
        quotes="nearest-cent ties-even synthetic fills/marks only; raw information unchanged",
        costs_bps_side=[str(c) for c in COSTS],
        cells=30,
        fits=2,
        seconds=300,
        cpu_only=True,
        gpu=False,
        holdout="none",
        paper_input=False,
        kill="BOTH10bps views state growth>0 and utility improvements>1e-10 "
        "over price/always/buyonce/cash",
        mechanism_inspiration=["NBER w15205", "arXiv:1203.5957"],
        optimality_replica=False,
        lineage=["kis-learned-stateful-rebalance-development-v1", prior.NAME],
        limitations=[
            "related outcome-informed seen raw non-PIT/non-TR development",
            "publication/finality not observed; synthetic quotes are not broker parity",
            "behaviour coverage mismatch and myopic counterfactual continuation",
            "overlapping paired labels; nonoverlap geometry is not ESS",
            "held risk may exceed desired target cap",
            "tail HOLD and final liquidation differ from TRAIN horizon marks",
            "closed predecessor rejections unchanged",
        ],
    )


def plan_record(plan):
    plan.__post_init__()
    record = plan.record()
    n = len(plan.train_indices)
    return dict(
        **record,
        paired_train_rows=2 * n,
        disjoint_label_geometry=(n + HORIZON - 1) // HORIZON,
        train_marks=n + HORIZON - 1,
        always_train_attempts=(n + 2 * (HORIZON - 1)) // HORIZON,
        buyonce_train_attempts=1,
    )


@dataclass(frozen=True, slots=True)
class TypedRowSource:
    """Date metadata and pure fetch(required_date_fields) -> typed row mapping.

    The caller owns byte/schema/source pins. Fetch must return only requested
    dates and fields; unrequested OPEN/CLOSE fields must be None. No IO occurs
    here except whatever the caller explicitly supplies in its callback.
    """

    dates_by_symbol: Mapping = field(repr=False)
    fetch: object = field(repr=False)

    def __post_init__(self):
        _require(
            isinstance(self.dates_by_symbol, Mapping)
            and set(self.dates_by_symbol) == set(SYMBOLS)
            and callable(self.fetch),
            "source_scope",
        )
        _require(
            all(
                type(ds) is tuple and all(type(d) is date for d in ds)
                for ds in self.dates_by_symbol.values()
            ),
            "source_date_metadata",
        )
        object.__setattr__(self, "dates_by_symbol", MappingProxyType(dict(self.dates_by_symbol)))


class _Source:
    """Index date metadata only; validate prices/identity only at selected keys."""

    def __init__(self, rows):
        if type(rows) is TypedRowSource:
            rows.__post_init__()
            self.fetch = rows.fetch
            self.index = {}
            for symbol, dates in rows.dates_by_symbol.items():
                index = {}
                for day in dates:
                    index.setdefault(day, []).append(None)
                self.index[symbol] = index
            return
        _require(isinstance(rows, Mapping) and set(rows) == set(SYMBOLS), "source_symbols_invalid")
        self.fetch = None
        self.index = {}
        for symbol in SYMBOLS:
            column = rows[symbol]
            _require(
                isinstance(column, Sequence) and not isinstance(column, (str, bytes)),
                "source_sequence_invalid",
            )
            index = {}
            for row in column:
                day = getattr(row, "session_date", None)
                if type(day) is date:
                    index.setdefault(day, []).append(row)
            self.index[symbol] = index

    def rows(self, required):
        if self.fetch is None:
            return {
                s: tuple(r for d in required for r in self.index[s].get(d, ())) for s in SYMBOLS
            }
        for s in SYMBOLS:
            for day in required:
                found = self.index[s].get(day, ())
                _require(bool(found), "required_session_missing")
                _require(len(found) == 1, "required_session_duplicate")
        result = self.fetch(MappingProxyType(dict(required)))
        _require(
            isinstance(result, Mapping) and set(result) == set(SYMBOLS), "source_symbols_invalid"
        )
        for column in result.values():
            _require(
                isinstance(column, Sequence) and not isinstance(column, (str, bytes)),
                "source_sequence_invalid",
            )
            for row in column:
                _require(type(row) is RawD1Price and row.session_date in required, "fetch_scope")
                _require(
                    all(
                        getattr(row, key) is None
                        for key in ("open", "close")
                        if key not in required[row.session_date]
                    ),
                    "fetch_extra_numeric_field",
                )
        return result

    def select(self, required, vintage):
        return base._select(self.rows(required), required, vintage)


def _source(rows):
    return rows if type(rows) is _Source else _Source(rows)


def _covariance(selected, history):
    import numpy as np

    try:
        exact_returns = tuple(
            tuple(
                Fraction(c[b.session_date]["close"]) / Fraction(c[a.session_date]["close"]) - 1
                for c in selected
            )
            for a, b in zip(history, history[1:], strict=False)
        )
        returns = np.asarray(exact_returns, dtype=np.float64)
        _require(np.isfinite(returns).all() and (returns > -1).all(), "return_numeric")
        _require(
            all(
                exact == 0 or converted != 0
                for row, values in zip(exact_returns, returns, strict=True)
                for exact, converted in zip(row, values, strict=True)
            ),
            "return_numeric",
        )
        raw = _population_covariance(returns)
        covariance = 0.9 * raw + 0.1 * np.diag(np.diag(raw))
        _require(np.isfinite(covariance).all(), "covariance_numeric")
        return tuple(tuple(Fraction(float(v)) for v in r) for r in covariance)
    except (ArithmeticError, ValueError) as error:
        if isinstance(error, CrossAssetInputUnavailable):
            raise
        raise CrossAssetInputUnavailable("covariance_numeric") from None


@dataclass(frozen=True, slots=True)
class PriceEntry:
    price: DailyRiskFeatures = field(repr=False)
    balanced3: tuple[Fraction, ...] = field(repr=False)
    covariance3: tuple = field(repr=False)
    prior_close3: tuple[Decimal, ...] = field(repr=False)

    def __post_init__(self):
        _require(type(self.price) is DailyRiskFeatures, "feature_type")
        self.price.__post_init__()
        c = self.covariance3
        _require(
            type(c) is tuple
            and len(c) == 3
            and all(
                type(r) is tuple and len(r) == 3 and all(type(v) is Fraction for v in r) for r in c
            ),
            "covariance_shape",
        )
        _require(all(c[i][j] == c[j][i] for i in range(3) for j in range(3)), "covariance_symmetry")
        determinant = (
            c[0][0] * (c[1][1] * c[2][2] - c[1][2] ** 2)
            - c[0][1] * (c[0][1] * c[2][2] - c[1][2] * c[0][2])
            + c[0][2] * (c[0][1] * c[1][2] - c[1][1] * c[0][2])
        )
        _require(
            all(c[i][i] >= 0 for i in range(3))
            and determinant >= 0
            and all(c[i][i] * c[j][j] >= c[i][j] ** 2 for i in range(3) for j in range(i + 1, 3)),
            "covariance_not_psd",
        )
        _require(
            type(self.balanced3) is tuple
            and len(self.balanced3) == 3
            and all(type(w) is Fraction for w in self.balanced3)
            and self.balanced3 == prior._scaled_actions(c)["balanced"],
            "action_scaling",
        )
        whole._prices(self.prior_close3)

    def safe_facts(self):
        return dict(
            kind="whole_share_price_entry",
            price_shape=(6, 63),
            covariance_closes=253,
            decision_at=self.price.decision_at.isoformat(),
            entry_at=self.price.entry_at.isoformat(),
            paper_input=False,
        )


def prepare_price_entry(rows_by_symbol, *, plan, entry_index, vintage_ref):
    plan.__post_init__()
    _require(
        type(entry_index) is int
        and (
            plan.train_indices[0] <= entry_index < plan.train_indices[-1] + HORIZON
            or entry_index in plan.group_indices
        ),
        "entry_scope",
    )
    source = _source(rows_by_symbol)
    history = plan.sessions[entry_index - 253 : entry_index]
    selected = source.select({s.session_date: ("close",) for s in history}, vintage_ref)
    feature_required = {
        s.session_date: ("close",) if i == 0 else ("open", "close")
        for i, s in enumerate(history[-64:])
    }
    price = base.prepare_features(
        source.rows(feature_required),
        scheduled_history=history[-64:],
        entry_session=plan.sessions[entry_index],
        decision_at=history[-1].close_at,
        vintage_ref=vintage_ref,
    )
    covariance = _covariance(selected, history)
    return PriceEntry(
        price,
        prior._scaled_actions(covariance)["balanced"],
        covariance,
        tuple(project_quote(c[history[-1].session_date]["close"]) for c in selected),
    )


def state_vector(state, entry):
    _require(
        type(state) is whole.WholeShareState and type(entry) is PriceEntry, "state_feature_type"
    )
    state.__post_init__()
    entry.__post_init__()
    _require(state.basis_usd == BASIS and state.allocated_usd == BANK, "original_bank")
    return (
        tuple(Fraction(q) for q in state.quantities3)
        + tuple(c / BANK for c in state.entry_costs3)
        + (state.gross_cash / BANK, state.fees_paid / BANK)
        + tuple(Fraction(p) / BANK for p in entry.prior_close3)
    )


@dataclass(frozen=True, slots=True)
class DecisionInput:
    entry: PriceEntry = field(repr=False)
    state: whole.WholeShareState = field(repr=False)
    state11: tuple[Fraction, ...] = field(repr=False)

    def __post_init__(self):
        _require(
            type(self.state11) is tuple and self.state11 == state_vector(self.state, self.entry),
            "state_feature_binding",
        )


def _input(entry, state):
    return DecisionInput(entry, state, state_vector(state, entry))


def preferred_action(delta):
    _require(type(delta) is Decimal and delta.is_finite(), "prediction_invalid")
    return REBALANCE if delta > 0 else HOLD


@dataclass(frozen=True, slots=True)
class CounterfactualTarget:
    decision_at: datetime
    entry_at: datetime
    exit_at: datetime
    hold_utility: Decimal = field(repr=False)
    rebalance_utility: Decimal = field(repr=False)
    delta: Decimal = field(repr=False)
    rebalance_reason: str

    def __post_init__(self):
        for t in (self.decision_at, self.entry_at, self.exit_at):
            base._utc(t)
        _require(self.decision_at < self.entry_at < self.exit_at, "target_time")
        _require(
            all(
                type(v) is Decimal and v.is_finite()
                for v in (self.hold_utility, self.rebalance_utility, self.delta)
            ),
            "target_numeric",
        )
        with localcontext(CONTEXT):
            _require(self.delta == self.rebalance_utility - self.hold_utility, "target_delta")
        _require(
            self.rebalance_reason in {r.value for r in whole.WholeShareTradeReason},
            "target_trade_reason",
        )

    @property
    def preferred(self):
        return preferred_action(self.delta)


def _forward_days(source, forward, vintage):
    required = {s.session_date: ("close",) for s in forward}
    required[forward[0].session_date] = ("open", "close")
    rows = source.select(required, vintage)
    return tuple(
        whole.WholeShareDay(
            s.session_date,
            tuple(project_quote(c[s.session_date]["open" if i == 0 else "close"]) for c in rows),
            tuple(project_quote(c[s.session_date]["close"]) for c in rows),
        )
        for i, s in enumerate(forward)
    )


def _counterfactual(decision, days, exit_at):
    decision.__post_init__()
    origin = whole.mark_close(decision.state, decision.entry.prior_close3).net_nav
    utilities, reason = [], None
    for rebalance in (False, True):
        trace = whole.replay(
            days,
            {days[0].date: decision.entry.balanced3} if rebalance else {},
            TRAIN_COST,
            initial_state=decision.state,
            liquidate_last_close=False,
        )
        utilities.append(
            Decimal(prior._metrics(tuple(d.mark.net_nav for d in trace.daily), origin)["utility"])
        )
        if rebalance:
            reason = trace.daily[0].open_trade.reason.value
    with localcontext(CONTEXT):
        delta = utilities[1] - utilities[0]
    if reason != "executed":
        _require(delta == 0, "infeasible_branch_changed_state")
    return CounterfactualTarget(
        decision.entry.price.decision_at,
        decision.entry.price.entry_at,
        exit_at,
        utilities[0],
        utilities[1],
        delta,
        reason,
    )


def counterfactual_target(rows_by_symbol, *, plan, entry_index, vintage_ref, decision):
    plan.__post_init__()
    _require(
        entry_index in plan.train_indices and type(decision) is DecisionInput, "target_not_train"
    )
    _binding(decision.entry, plan, entry_index, vintage_ref)
    forward = plan.sessions[entry_index : entry_index + HORIZON]
    return _counterfactual(
        decision, _forward_days(_source(rows_by_symbol), forward, vintage_ref), forward[-1].close_at
    )


def _binding(entry, plan, index, vintage):
    entry.__post_init__()
    _require(
        entry.price.entry_at == plan.sessions[index].open_at
        and entry.price.decision_at == plan.sessions[index - 1].close_at
        and entry.price.vintage_ref == vintage,
        "feature_binding",
    )


def _quotes(source, day, kind, vintage):
    return tuple(project_quote(c[day][kind]) for c in source.select({day: (kind,)}, vintage))


def _advance(source, index, plan, vintage, state, weights=None, *, cost=TRAIN_COST, final=False):
    day = plan.sessions[index].session_date
    opening = (
        whole.rebalance_open(state, _quotes(source, day, "open", vintage), weights, cost)
        if weights is not None
        else None
    )
    state = opening.state if opening else state
    close = _quotes(source, day, "close", vintage)
    sale = whole.liquidate_close(state, close, cost) if final else None
    state = sale.state if sale else state
    return whole.WholeShareDaily(day, whole.mark_close(state, close), opening, sale)


@dataclass(frozen=True, slots=True)
class TrainingRow:
    entry_index: int
    behaviour: str
    decision: DecisionInput = field(repr=False)
    target: CounterfactualTarget = field(repr=False)

    def __post_init__(self):
        _require(type(self.entry_index) is int and self.behaviour in BEHAVIOURS, "training_row")
        self.decision.__post_init__()
        self.target.__post_init__()
        _require(
            self.target.decision_at == self.decision.entry.price.decision_at
            and self.target.entry_at == self.decision.entry.price.entry_at,
            "target_binding",
        )


@dataclass(frozen=True, slots=True)
class TrainingSet:
    plan: CampaignPlan = field(repr=False)
    vintage_ref: str = field(repr=False)
    rows: tuple[TrainingRow, ...] = field(repr=False)
    behaviour_replays: Mapping = field(repr=False)

    def __post_init__(self):
        self.plan.__post_init__()
        base._vintage(self.vintage_ref)
        _require(
            type(self.rows) is tuple and len(self.rows) == 2 * len(self.plan.train_indices),
            "training_pairs",
        )
        for row, expected in zip(
            self.rows, ((i, b) for i in self.plan.train_indices for b in BEHAVIOURS), strict=True
        ):
            _require(
                type(row) is TrainingRow and (row.entry_index, row.behaviour) == expected,
                "training_pairs",
            )
            row.__post_init__()
            _binding(row.decision.entry, self.plan, row.entry_index, self.vintage_ref)
            _require(
                row.target.exit_at == self.plan.sessions[row.entry_index + 20].close_at,
                "target_binding",
            )
        _require(
            isinstance(self.behaviour_replays, Mapping)
            and set(self.behaviour_replays) == set(BEHAVIOURS),
            "behaviour_keys",
        )
        dates = tuple(
            s.session_date
            for s in self.plan.sessions[
                self.plan.train_indices[0] : self.plan.train_indices[-1] + HORIZON
            ]
        )
        for replay in self.behaviour_replays.values():
            _require(
                type(replay) is tuple and tuple(d.date for d in replay) == dates, "behaviour_marks"
            )
        object.__setattr__(
            self, "behaviour_replays", MappingProxyType(dict(self.behaviour_replays))
        )

    @property
    def ordering_changes(self):
        return sum(
            a.target.preferred != b.target.preferred
            for a, b in zip(self.rows[::2], self.rows[1::2], strict=True)
        )

    def safe_facts(self):
        return dict(
            kind="paired_whole_share_training",
            pairs=len(self.rows) // 2,
            rows=len(self.rows),
            ordering_changes=self.ordering_changes,
            structural_pass=self.ordering_changes > 0,
            disjoint_label_geometry=plan_record(self.plan)["disjoint_label_geometry"],
            independent_sample_count="not_claimed",
            fits=0,
            paper_input=False,
        )


def prepare_training(rows_by_symbol, *, plan, vintage_ref):
    plan.__post_init__()
    source = _source(rows_by_symbol)
    first, stop = plan.train_indices[0], plan.train_indices[-1] + HORIZON
    states = {b: prior._initial(whole) for b in BEHAVIOURS}
    replays, rows = {b: [] for b in BEHAVIOURS}, []
    eligible = set(plan.train_indices)
    for index in range(first, stop):
        due = (index - first) % HORIZON == 0
        entry = (
            prepare_price_entry(source, plan=plan, entry_index=index, vintage_ref=vintage_ref)
            if index in eligible or due
            else None
        )
        if index in eligible:
            snapshots = {b: _input(entry, states[b]) for b in BEHAVIOURS}
            forward = plan.sessions[index : index + HORIZON]
            days = _forward_days(source, forward, vintage_ref)
            rows.extend(
                TrainingRow(
                    index,
                    b,
                    snapshots[b],
                    _counterfactual(snapshots[b], days, forward[-1].close_at),
                )
                for b in BEHAVIOURS
            )
        for b in BEHAVIOURS:
            trade = due if b == "always" else index == first
            daily = _advance(
                source, index, plan, vintage_ref, states[b], entry.balanced3 if trade else None
            )
            states[b] = daily.mark.state
            replays[b].append(daily)
    return TrainingSet(plan, vintage_ref, tuple(rows), {b: tuple(v) for b, v in replays.items()})


@dataclass(frozen=True, slots=True, repr=False)
class RidgeScaler:
    price_mean: object
    price_divisor: object
    state_mean: object
    state_divisor: object

    def __post_init__(self):
        import numpy as np

        for name, size in (
            ("price_mean", 6),
            ("price_divisor", 6),
            ("state_mean", 11),
            ("state_divisor", 11),
        ):
            value = np.array(getattr(self, name), dtype=np.float64, copy=True)
            _require(value.shape == (size,) and np.isfinite(value).all(), "scaler_numeric")
            _require(not name.endswith("divisor") or (value > 0).all(), "scaler_numeric")
            value.flags.writeable = False
            object.__setattr__(self, name, value)

    def transform(self, decision, *, augmented):
        import numpy as np

        _require(type(decision) is DecisionInput and type(augmented) is bool, "scaler_input")
        decision.__post_init__()
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                price = (
                    np.asarray(decision.entry.price.features, dtype=np.float64)
                    - self.price_mean[:, None]
                ) / self.price_divisor[:, None]
                state = (
                    (np.asarray(decision.state11, dtype=np.float64) - self.state_mean)
                    / self.state_divisor
                    if augmented
                    else np.zeros(11)
                )
                result = np.concatenate((price.reshape(378), state))
        except (ArithmeticError, ValueError):
            raise CrossAssetInputUnavailable("scaler_numeric") from None
        _require(np.isfinite(result).all(), "scaler_numeric")
        result.flags.writeable = False
        return result

    def training_inputs(self, training, *, augmented):
        import numpy as np

        training.__post_init__()
        result = np.stack([self.transform(r.decision, augmented=augmented) for r in training.rows])
        result.flags.writeable = False
        return result


def fit_scaler(training):
    """Fit numeric scalers on paired TRAIN rows only; no model is fitted here."""
    import numpy as np

    _require(type(training) is TrainingSet, "training_type")
    training.__post_init__()
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            price = np.asarray(
                [r.decision.entry.price.features for r in training.rows], dtype=np.float64
            )
            state = np.asarray([r.decision.state11 for r in training.rows], dtype=np.float64)
            _require(np.isfinite(price).all() and np.isfinite(state).all(), "scaler_numeric")
            pm, ps = price.mean(axis=(0, 2)), price.std(axis=(0, 2), ddof=0)
            sm, ss = state.mean(axis=0), state.std(axis=0, ddof=0)
    except (ArithmeticError, ValueError) as error:
        if isinstance(error, CrossAssetInputUnavailable):
            raise
        raise CrossAssetInputUnavailable("scaler_numeric") from None
    return RidgeScaler(pm, np.where(ps == 0, 1.0, ps), sm, np.where(ss == 0, 1.0, ss))


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    policy: str
    cost_bps: Decimal
    action: str
    decision: DecisionInput = field(repr=False)
    prediction: Decimal | None = field(repr=False)

    def __post_init__(self):
        _require(
            self.policy in POLICIES and type(self.cost_bps) is Decimal and self.cost_bps in COSTS,
            "decision_scope",
        )
        self.decision.__post_init__()
        _require(self.action in (HOLD, REBALANCE), "decision_action")
        if self.policy in ("state", "price"):
            _require(self.action == preferred_action(self.prediction), "decision_binding")
        else:
            _require(self.prediction is None, "decision_binding")

    def safe_facts(self):
        return dict(
            policy=self.policy,
            action=self.action,
            cost_bps=str(self.cost_bps),
            decision_at=self.decision.entry.price.decision_at.isoformat(),
            entry_at=self.decision.entry.price.entry_at.isoformat(),
            sealed_before_execution=True,
        )


@dataclass(frozen=True, slots=True)
class PolicyReplay:
    policy: str
    cost_bps: Decimal
    daily: tuple = field(repr=False)
    decisions: tuple[DecisionRecord, ...] = field(repr=False)

    @property
    def final_state(self):
        return self.daily[-1].mark.state


@dataclass(frozen=True, slots=True)
class Evaluation:
    cells: tuple = field(repr=False)
    replays: tuple[PolicyReplay, ...] = field(repr=False)


def evaluate(rows_by_symbol, *, plan, vintage_ref, predictor, on_seal=None):
    """Per-decision logical seal before selected current OPEN/CLOSE numeric access.

    predictor(policy, DecisionInput) returns one finite Decimal advantage. The
    optional on_seal(DecisionRecord) callback must return before execution access.
    It is not given the source or forward marks. Caller owns callback effects.
    """
    plan.__post_init__()
    base._vintage(vintage_ref)
    _require(callable(predictor) and (on_seal is None or callable(on_seal)), "predictor_invalid")
    source, replays, cells = _source(rows_by_symbol), [], []
    opportunities = set(plan.group_indices)
    for cost in COSTS:
        for policy in POLICIES:
            state, daily, decisions = prior._initial(whole), [], []
            for index in plan.dev_indices:
                weights = None
                if index in opportunities:
                    entry = prepare_price_entry(
                        source, plan=plan, entry_index=index, vintage_ref=vintage_ref
                    )
                    decision = _input(entry, state)
                    prediction = (
                        predictor(policy, decision) if policy in ("state", "price") else None
                    )
                    action = (
                        preferred_action(prediction)
                        if prediction is not None
                        else (
                            REBALANCE
                            if policy == "always"
                            or policy == "buyonce"
                            and index == plan.dev_indices[0]
                            else HOLD
                        )
                    )
                    record = DecisionRecord(policy, cost, action, decision, prediction)
                    if on_seal is not None:
                        on_seal(record)
                    record.__post_init__()
                    _binding(entry, plan, index, vintage_ref)
                    _require(
                        record.decision is decision
                        and record.decision.state == state
                        and record.action == action
                        and record.policy == policy
                        and record.cost_bps == cost
                        and record.prediction == prediction,
                        "seal_changed",
                    )
                    decisions.append(record)
                    weights = entry.balanced3 if action == REBALANCE else None
                day = _advance(
                    source,
                    index,
                    plan,
                    vintage_ref,
                    state,
                    weights,
                    cost=cost,
                    final=index == plan.dev_indices[-1],
                )
                state = day.mark.state
                daily.append(day)
            _require(state.basis_usd == BASIS and state.allocated_usd == BANK, "original_bank")
            replay = PolicyReplay(policy, cost, tuple(daily), tuple(decisions))
            replays.append(replay)
            navs, cut = tuple(d.mark.net_nav for d in daily), plan.block_cut
            for view, values, origin in ((0, navs[:cut], BANK), (1, navs[cut:], navs[cut - 1])):
                cells.append(
                    dict(
                        policy=policy,
                        cost_bps=str(cost),
                        view=view,
                        metrics=prior._metrics(values, origin),
                    )
                )
    return Evaluation(tuple(cells), tuple(replays))


def criterion(cells):
    expected = {(p, str(c), v) for p in POLICIES for c in COSTS for v in (0, 1)}
    _require(
        len(cells) == 30 and {(c["policy"], c["cost_bps"], c["view"]) for c in cells} == expected,
        "cell_matrix",
    )
    table = {}
    for cell in cells:
        metrics = cell["metrics"]
        _require(
            all(
                type(metrics[k]) is str and Decimal(metrics[k]).is_finite()
                for k in ("growth", "utility")
            ),
            "cell_metrics",
        )
        table[cell["policy"], cell["cost_bps"], cell["view"]] = metrics
    with localcontext(CONTEXT):
        passed = all(
            Decimal(table["state", "10", view]["growth"]) > 0
            and all(
                Decimal(table["state", "10", view]["utility"])
                - Decimal(table[p, "10", view]["utility"])
                > TOLERANCE
                for p in ("price", "always", "buyonce", "cash")
            )
            for view in (0, 1)
        )
    return {"state": "survived_development" if passed else "rejected"}

"""Source-free preparation for a new KIS 2016+ relative-allocation study.

Predictions are absolute unit-capital log net factors, not centered ranks or
confidence estimates. The caller freezes a NEW dataset/calendar before actual
use; this module has no loader, artifact lifecycle, broker or dispatch path.
Positional NAV arithmetic never relabels raw KIS prices as adjusted data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
from types import MappingProxyType

from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_daily_risk_input import prepare_daily_features
from thericher_v2.research.cross_asset_hedge_failure_input import (
    CONTEXT,
    INSTRUMENT_ORDER,
    CrossAssetSession,
    _calendar,
    _positive,
    _require,
    _select,
    _utc,
    _vintage,
)
from thericher_v2.research.cross_asset_monthly_momentum import THIRD

NAME = "kis-cross-asset-21-session-relative-allocation-development-v1"
SYMBOLS = INSTRUMENT_ORDER
HORIZON, SEED, UPDATES, SECONDS = 21, 101, 1024, 300
CANDIDATES = ("ridge", "gru")
CONTROLS = ("cash", "group_balanced", "momentum63", "group_spy")
REFERENCE = "spy_buyhold"
POLICIES = CANDIDATES + CONTROLS + (REFERENCE,)
COSTS = (Decimal("2.5"), Decimal(5), Decimal(10))
TARGET_COST = Decimal(5)
TOLERANCE = Decimal("1e-10")
DEV_START, VIEW_END, DEV_END = date(2021, 1, 4), date(2023, 12, 29), date(2026, 9, 30)
FIRST_DECISION, MATURITY_DAY = date(2020, 12, 31), date(2020, 12, 30)


def configuration():
    return dict(
        name=NAME,
        preparation_only=True,
        symbols=list(SYMBOLS),
        dataset=dict(
            identity=None,
            sha256=None,
            state="pending_new_2016_cohort",
            legacy_02dcc_input_allowed=False,
        ),
        features="asset-major 6x63 ln(CLOSE) differences / ln(CLOSE)-ln(OPEN); "
        "64 exact prior CLOSEs/63 OPENs, previous scheduled CLOSE decision",
        target="three absolute 21-session unit NAV log net factors; "
        "first OPEN->21st CLOSE canonical ledger 5bps/side; no centering",
        train="2016+ warmup; each label exit<=2020-12-30 CLOSE, one scheduled "
        "session before first DEV decision 2020-12-31 CLOSE",
        dev_views=[["2021-01-04", "2023-12-29"], ["2024-01-02", "2026-09-30"]],
        groups="partition all DEV once into21 sessions, no view reset; tail cash; "
        "unchanged quantities until group-last CLOSE liquidation",
        standardization="TRAIN-only float64 population channel mean/std over samples/time; "
        "zero std divisor1; GRU float32, Ridge float64; targets unscaled",
        ridge=dict(alpha=1, fit_intercept=True, solver="svd", inputs="flattened6x63"),
        gru=dict(
            input_size=6,
            hidden_size=64,
            layers=1,
            output_size=3,
            dropout=0,
            seed=SEED,
            updates=UPDATES,
            optimizer="AdamW",
            lr=0.001,
            weight_decay=0.01,
            loss="mean squared absolute log-factor error",
            batch="full",
            dtype="float32",
            tf32=False,
            deterministic=True,
        ),
        action="absolute argmax strictly>0 else cash; ties SPY/TLT/GLD; no confidence gate",
        momentum="sum63 past close-to-close log returns; same strict>0 selection/ties",
        policies=list(POLICIES),
        reference_only=REFERENCE,
        costs_bps_side=[str(c) for c in COSTS],
        cells=42,
        accounting="one continuous NAV1 per policy/cost; Decimal50 actual-notional fees; "
        "all daily marks, cross-view inventory and denominators retained",
        utility="252*(mean daily log return-5*population variance)",
        kill="10bps BOTH views growth>0 and utility improvements>1e-10; "
        "Ridge vs four matched controls; GRU vs those controls+Ridge; "
        "uninterrupted SPY reference excluded; no wealth-dominance requirement",
        fits=2,
        seconds=SECONDS,
        selection="one final fit/member; no grid/early stop/refit",
        runtime_assumption="parent pins runtime and proves synthetic throughput before values",
        cublas_workspace_config=":4096:8",
        parent_gpu_lease=True,
        lineage="closed NAS/trio sequence, momentum, allocation, five-session risk and "
        "variance families retained; new21D asset-selection mechanism, not rescue",
        grade="RELATED_SEEN_RAW_PRICE_ONLY_DEVELOPMENT",
        paper_input=False,
        holdout="none",
        limitations=[
            "non-PIT",
            "corporate actions/dividends not applied",
            "provider availability/finality not observed",
            "ideal fractional fills",
            "overlapping TRAIN targets/contexts; counts not independent samples",
        ],
    )


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    sessions: tuple[CrossAssetSession, ...] = field(repr=False)
    train_indices: tuple[int, ...] = field(repr=False)
    dev_indices: tuple[int, ...] = field(repr=False)
    block_cut: int

    def __post_init__(self):
        _calendar(self.sessions)
        _require(type(self.train_indices) is tuple and bool(self.train_indices), "train_calendar")
        _require(type(self.dev_indices) is tuple and bool(self.dev_indices), "dev_calendar")
        for indices in (self.train_indices, self.dev_indices):
            _require(
                all(type(i) is int and 64 <= i < len(self.sessions) for i in indices)
                and all(a < b for a, b in zip(indices, indices[1:], strict=False)),
                "plan_indices",
            )
        _require(
            self.dev_indices == tuple(range(self.dev_indices[0], self.dev_indices[-1] + 1))
            and type(self.block_cut) is int
            and 0 < self.block_cut < len(self.dev_indices),
            "view_calendar",
        )
        first = self.dev_indices[0]
        _require(
            self.sessions[first].session_date == DEV_START
            and self.sessions[first - 1].session_date == FIRST_DECISION
            and self.sessions[first - 2].session_date == MATURITY_DAY
            and self.dates[-1] == DEV_END
            and self.dates[self.block_cut - 1] == VIEW_END
            and self.dates[self.block_cut] == date(2024, 1, 2),
            "study_calendar",
        )
        expected = tuple(
            i
            for i in range(64, first - 1)
            if self.sessions[i - 64].session_date >= date(2016, 1, 1)
            and i + HORIZON - 1 <= first - 2
        )
        _require(self.train_indices == expected, "train_maturity")

    @property
    def dates(self):
        return tuple(self.sessions[i].session_date for i in self.dev_indices)

    @property
    def group_indices(self):
        return self.dev_indices[: len(self.dev_indices) - len(self.dev_indices) % HORIZON : HORIZON]

    @property
    def groups(self):
        return tuple(
            tuple(s.session_date for s in self.sessions[i : i + HORIZON])
            for i in self.group_indices
        )

    def record(self):
        return dict(
            train_entries=[self.sessions[i].session_date.isoformat() for i in self.train_indices],
            train_exits=[self.sessions[i + 20].close_at.isoformat() for i in self.train_indices],
            maturity_cutoff=self.sessions[self.dev_indices[0] - 2].close_at.isoformat(),
            first_dev_decision=self.sessions[self.dev_indices[0] - 1].close_at.isoformat(),
            dates=[d.isoformat() for d in self.dates],
            groups=[[d.isoformat() for d in g] for g in self.groups],
            block_cut=self.block_cut,
            tail_cash_days=len(self.dates) % HORIZON,
            independent_sample_count="not_claimed",
        )


def build_plan(sessions):
    """Caller supplies a complete frozen calendar, never dates selected from prices."""
    _calendar(sessions)
    dev = tuple(i for i, s in enumerate(sessions) if DEV_START <= s.session_date <= DEV_END)
    _require(bool(dev) and dev[0] >= 66, "dev_calendar")
    train = tuple(
        i
        for i in range(64, dev[0] - 1)
        if sessions[i - 64].session_date >= date(2016, 1, 1) and i + 20 <= dev[0] - 2
    )
    cut = sum(sessions[i].session_date <= VIEW_END for i in dev)
    return AllocationPlan(sessions, train, dev, cut)


def prepare_features(rows_by_symbol, *, scheduled_history, entry_session, decision_at, vintage_ref):
    return prepare_daily_features(
        rows_by_symbol,
        scheduled_history=scheduled_history,
        entry_session=entry_session,
        decision_at=decision_at,
        vintage_ref=vintage_ref,
    )


@dataclass(frozen=True, slots=True)
class Absolute21Target:
    entry_at: datetime
    exit_at: datetime
    net_factors: tuple[Decimal, ...] = field(repr=False)
    log_net_factors: tuple[Decimal, ...] = field(repr=False)
    vintage_ref: str = field(repr=False)

    def __post_init__(self):
        _utc(self.entry_at)
        _utc(self.exit_at)
        _vintage(self.vintage_ref)
        _require(self.entry_at < self.exit_at, "target_time")
        _require(
            type(self.net_factors) is tuple
            and len(self.net_factors) == 3
            and type(self.log_net_factors) is tuple
            and len(self.log_net_factors) == 3,
            "target_shape",
        )
        with localcontext(CONTEXT):
            for factor, log in zip(self.net_factors, self.log_net_factors, strict=True):
                _positive(factor)
                _require(
                    type(log) is Decimal and log.is_finite() and log == factor.ln(),
                    "target_log_mismatch",
                )

    def safe_facts(self):
        return dict(
            kind="absolute21_target",
            symbols=SYMBOLS,
            sessions=21,
            cost_bps_side=5,
            target="absolute_log_net_factor_not_centered",
            entry_at=self.entry_at.isoformat(),
            exit_at=self.exit_at.isoformat(),
            daily_utility="not_supplied",
            paper_input=False,
        )


def unit_target(index=None):
    _require(index is None or type(index) is int and 0 <= index < 3, "allocation_index")
    weights = tuple(Decimal(int(i == index)) for i in range(3))
    return nav.ThreeAssetTarget(weights, Decimal(int(index is None)))


@nav._decimal
def balanced_target():
    return nav.ThreeAssetTarget((THIRD,) * 3, Decimal(1) - 3 * THIRD)


@nav._decimal
def build_absolute_target(rows_by_symbol, *, scheduled_forward, vintage_ref):
    """Separate TRAIN endpoint lookup; no features or DEV marks are consumed here."""
    _calendar(scheduled_forward)
    _require(len(scheduled_forward) == HORIZON, "target_calendar")
    first, last = scheduled_forward[0], scheduled_forward[-1]
    rows = _select(
        rows_by_symbol, {first.session_date: ("open",), last.session_date: ("close",)}, vintage_ref
    )
    opens = tuple(r[first.session_date]["open"] for r in rows)
    closes = tuple(r[last.session_date]["close"] for r in rows)
    days = (
        nav.ThreeAssetDay(first.session_date, opens, opens),
        nav.ThreeAssetDay(last.session_date, closes, closes),
    )
    factors = tuple(
        nav.replay(days, {first.session_date: unit_target(i)}, TARGET_COST).final_nav
        for i in range(3)
    )
    return Absolute21Target(
        first.open_at, last.close_at, factors, tuple(f.ln() for f in factors), vintage_ref
    )


def prepare_entry_features(rows_by_symbol, *, plan, entry_index, vintage_ref):
    plan.__post_init__()
    _require(entry_index in plan.train_indices + plan.group_indices, "feature_entry_scope")
    history = plan.sessions[entry_index - 64 : entry_index]
    return prepare_features(
        rows_by_symbol,
        scheduled_history=history,
        entry_session=plan.sessions[entry_index],
        decision_at=history[-1].close_at,
        vintage_ref=vintage_ref,
    )


def prepare_train_target(rows_by_symbol, *, plan, entry_index, vintage_ref):
    plan.__post_init__()
    _require(entry_index in plan.train_indices, "target_not_train")
    return build_absolute_target(
        rows_by_symbol,
        scheduled_forward=plan.sessions[entry_index : entry_index + 21],
        vintage_ref=vintage_ref,
    )


@dataclass(frozen=True, slots=True)
class StandardizedInputs:
    train: object = field(repr=False)
    dev: object = field(repr=False)
    mean: object = field(repr=False)
    divisor: object = field(repr=False)


def standardize(train_features, dev_features):
    """Numeric conversion only; callers keep TRAIN targets in a separate interface."""
    import numpy as np

    train = np.array(train_features, dtype=np.float64, copy=True)
    dev = np.array(dev_features, dtype=np.float64, copy=True)
    _require(
        train.ndim == dev.ndim == 3
        and train.shape[1:] == dev.shape[1:] == (6, 63)
        and train.shape[0] > 0
        and np.isfinite(train).all()
        and np.isfinite(dev).all(),
        "feature_matrix",
    )
    mean, std = train.mean(axis=(0, 2)), train.std(axis=(0, 2), ddof=0)
    divisor = np.where(std == 0, 1.0, std)
    _require(np.isfinite(mean).all() and np.isfinite(divisor).all(), "scaler_numeric")
    a = (train - mean[None, :, None]) / divisor[None, :, None]
    b = (dev - mean[None, :, None]) / divisor[None, :, None]
    _require(np.isfinite(a).all() and np.isfinite(b).all(), "feature_numeric")
    for array in (a, b, mean, divisor):
        array.flags.writeable = False
    return StandardizedInputs(a, b, mean, divisor)


def _scores(scores):
    _require(type(scores) is tuple and len(scores) == 3, "prediction_shape")
    for value in scores:
        _require(type(value) is Decimal and value.is_finite(), "prediction_nonfinite")


def absolute_action(scores):
    _scores(scores)
    best = max(range(3), key=lambda i: scores[i])
    return unit_target(best if scores[best] > 0 else None)


@dataclass(frozen=True, slots=True)
class ActionSeal:
    plan: AllocationPlan = field(repr=False)
    vintage_ref: str = field(repr=False)
    actions: Mapping = field(repr=False)

    def __post_init__(self):
        _require(type(self.plan) is AllocationPlan, "plan_type")
        self.plan.__post_init__()
        _vintage(self.vintage_ref)
        _require(
            isinstance(self.actions, Mapping) and set(self.actions) == set(POLICIES),
            "action_policies",
        )
        entries = tuple(g[0] for g in self.plan.groups)
        copied = {}
        for policy in POLICIES:
            actions = self.actions[policy]
            expected = entries[:1] if policy == REFERENCE else entries
            _require(isinstance(actions, Mapping) and set(actions) == set(expected), "action_keys")
            targets = {}
            for day in expected:
                target = actions[day]
                _require(type(target) is nav.ThreeAssetTarget, "action_type")
                target.__post_init__()
                fixed = {
                    "cash": unit_target(),
                    "group_balanced": balanced_target(),
                    "group_spy": unit_target(0),
                    REFERENCE: unit_target(0),
                }
                _require(
                    target == fixed[policy]
                    if policy in fixed
                    else target in tuple(unit_target(i) for i in (None, 0, 1, 2)),
                    "policy_allocation",
                )
                targets[day] = nav.ThreeAssetTarget(target.weights3, target.cash_weight)
            copied[policy] = MappingProxyType(targets)
        object.__setattr__(self, "actions", MappingProxyType(copied))


@nav._decimal
def prepare_actions(predictions, dev_features, *, plan, vintage_ref):
    """No forward rows argument: every policy action is sealed before payoff lookup."""
    plan.__post_init__()
    entries = tuple(g[0] for g in plan.groups)
    _require(
        isinstance(predictions, Mapping)
        and set(predictions) == set(CANDIDATES)
        and all(set(p) == set(entries) for p in predictions.values()),
        "prediction_keys",
    )
    _require(
        isinstance(dev_features, Mapping) and set(dev_features) == set(entries), "feature_keys"
    )
    actions = {p: {} for p in POLICIES}
    for j, (day, i) in enumerate(zip(entries, plan.group_indices, strict=True)):
        features = dev_features[day]
        features.__post_init__()
        _require(
            features.vintage_ref == vintage_ref
            and features.entry_at == plan.sessions[i].open_at
            and features.decision_at == plan.sessions[i - 1].close_at
            and features.observation_dates
            == tuple(s.session_date for s in plan.sessions[i - 63 : i]),
            "feature_binding",
        )
        for candidate in CANDIDATES:
            actions[candidate][day] = absolute_action(predictions[candidate][day])
        momentum = tuple(sum(features.features[2 * k], Decimal(0)) for k in range(3))
        actions["momentum63"][day] = absolute_action(momentum)
        actions["cash"][day] = unit_target()
        actions["group_balanced"][day] = balanced_target()
        actions["group_spy"][day] = unit_target(0)
        if j == 0:
            actions[REFERENCE][day] = unit_target(0)
    return ActionSeal(plan, vintage_ref, actions)


@nav._decimal
def replay_groups(days, targets, *, plan, cost_bps):
    plan.__post_init__()
    records = tuple(days)
    _require(tuple(d.date for d in records) == plan.dates, "forward_mark_gap")
    entries, exits = {g[0] for g in plan.groups}, {g[-1] for g in plan.groups}
    _require(set(targets) == entries, "action_keys")
    for d in records:
        _require(type(d) is nav.ThreeAssetDay, "mark_type")
        d.__post_init__()
    for t in targets.values():
        _require(type(t) is nav.ThreeAssetTarget, "action_type")
        t.__post_init__()
    fee = nav._fee(cost_bps)
    state, previous = nav.ThreeAssetState(Decimal(1)), Decimal(1)
    total_fees = total_notional = Decimal(0)
    trace = []
    for d in records:
        paid = traded = Decimal(0)
        if d.date in entries:
            _require(all(q == 0 for q in state.quantities), "entry_not_flat")
            t = targets[d.date]
            trade = nav._rebalance(
                state, nav.ThreeAssetPrices(d.adj_open3), t.weights3, t.cash_weight, fee
            )
            state, paid, traded = trade.state, trade.fees, trade.turnover
        close = nav.ThreeAssetPrices(d.adj_close3)
        if d.date in exits:
            trade = nav.liquidate_close(state, close, cost_bps)
            state, paid, traded = trade.state, paid + trade.fees, traded + trade.turnover
        marked = nav.mark_close(state, close)
        _positive(marked.nav)
        factor = marked.nav / previous
        trace.append(
            nav.ThreeAssetDaily(
                d.date,
                marked.nav,
                paid,
                traded,
                state.cash,
                all(q == 0 for q in state.quantities),
                factor - 1,
                factor.ln(),
            )
        )
        total_fees, total_notional = total_fees + paid, total_notional + traded
        previous = marked.nav
    _require(trace[-1].flat, "final_not_flat")
    return nav.ThreeAssetReplay(tuple(trace), state, total_fees, total_notional)


@nav._decimal
def _metrics(records, entering):
    logs = tuple(d.log_return for d in records)
    mean = sum(logs, Decimal(0)) / len(logs)
    variance = sum(((v - mean) ** 2 for v in logs), Decimal(0)) / len(logs)
    return dict(
        growth=str(records[-1].nav / entering - 1),
        utility=str(252 * (mean - 5 * variance)),
        days=len(records),
    )


def evaluate(days, seal):
    _require(type(seal) is ActionSeal, "action_seal")
    seal = ActionSeal(seal.plan, seal.vintage_ref, seal.actions)
    records = tuple(days)
    _require(tuple(d.date for d in records) == seal.plan.dates, "forward_mark_gap")
    cells = []
    for cost in COSTS:
        for policy in POLICIES:
            actions = seal.actions[policy]
            replay = (
                nav.replay(records, actions, cost)
                if policy == REFERENCE
                else replay_groups(records, actions, plan=seal.plan, cost_bps=cost)
            )
            cut = seal.plan.block_cut
            for block, subset, entering in (
                (0, replay.daily[:cut], Decimal(1)),
                (1, replay.daily[cut:], replay.daily[cut - 1].nav),
            ):
                cells.append(
                    dict(
                        policy=policy,
                        cost_bps=str(cost),
                        block=block,
                        metrics=_metrics(subset, entering),
                    )
                )
    return cells


@nav._decimal
def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    _require(
        len(cells) == 42 and {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == expected,
        "cell_matrix",
    )
    _require(
        all(
            type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
            for c in cells
            for k in ("growth", "utility")
        ),
        "cell_metrics",
    )
    verdicts = {}
    for candidate in CANDIDATES:
        controls = CONTROLS + (("ridge",) if candidate == "gru" else ())
        passed = True
        for block in (0, 1):
            group = {
                c["policy"]: c["metrics"]
                for c in cells
                if c["block"] == block and c["cost_bps"] == "10"
            }
            own = group[candidate]
            passed &= Decimal(own["growth"]) > 0 and all(
                Decimal(own["utility"]) - Decimal(group[p]["utility"]) > TOLERANCE for p in controls
            )
        verdicts[candidate] = "development_survivor" if passed else "rejected"
    return verdicts


def make_gru():
    import torch

    class JointGRU(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = torch.nn.GRU(
                6, 64, 1, batch_first=True, dropout=0, device="cpu", dtype=torch.float32
            )
            self.output = torch.nn.Linear(64, 3, device="cpu", dtype=torch.float32)

        def forward(self, x):
            hidden, _ = self.encoder(x.transpose(1, 2))
            return self.output(hidden[:, -1])

    return JointGRU()


def _fit_inputs(train_x, train_y, dev_x):
    import numpy as np

    _require(
        train_x.ndim == dev_x.ndim == 3
        and train_x.shape[1:] == dev_x.shape[1:] == (6, 63)
        and train_x.shape[0] > 0
        and train_y.shape == (len(train_x), 3)
        and all(np.isfinite(a).all() for a in (train_x, train_y, dev_x)),
        "fit_inputs",
    )


def fit_ridge(train_x, train_y, dev_x, *, progress):
    """Future caller-owned fit primitive; completion precedes postfit predictions."""
    import numpy as np
    from sklearn.linear_model import Ridge

    _fit_inputs(train_x, train_y, dev_x)
    model = Ridge(alpha=1, fit_intercept=True, solver="svd")
    progress("ridge", "started", 0)
    model.fit(
        np.asarray(train_x, dtype=np.float64).reshape(len(train_x), -1),
        np.asarray(train_y, dtype=np.float64),
    )
    progress("ridge", "completed", 1)
    predictions = model.predict(np.asarray(dev_x, dtype=np.float64).reshape(len(dev_x), -1))
    _validate_predictions(predictions, len(dev_x))
    return model, predictions


def _validate_predictions(values, count):
    import numpy as np

    _require(values.shape == (count, 3) and np.isfinite(values).all(), "prediction_nonfinite")


def fit_gru(train_x, train_y, dev_x, *, progress):
    """No lease/dispatch here: future frozen supervisor owns budget and CUDA scope."""
    import numpy as np
    import torch

    _fit_inputs(train_x, train_y, dev_x)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    x = torch.tensor(np.array(train_x, dtype=np.float32, copy=True), device="cuda")
    y = torch.tensor(np.array(train_y, dtype=np.float32, copy=True), device="cuda")
    model = make_gru().to("cuda")
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    progress("gru", "started", 0)
    model.train()
    for n in range(1, UPDATES + 1):
        optimizer.zero_grad(set_to_none=True)
        loss = ((model(x) - y) ** 2).mean()
        _require(bool(torch.isfinite(loss).item()), "training_nonfinite")
        loss.backward()
        optimizer.step()
        if n % 256 == 0:
            torch.cuda.synchronize()
            progress("gru", "updates", n)
    torch.cuda.synchronize()
    progress("gru", "completed", UPDATES)
    model.eval()
    with torch.no_grad():
        predictions = (
            model(torch.tensor(np.array(dev_x, dtype=np.float32, copy=True), device="cuda"))
            .cpu()
            .numpy()
        )
    _validate_predictions(predictions, len(dev_x))
    return model, predictions

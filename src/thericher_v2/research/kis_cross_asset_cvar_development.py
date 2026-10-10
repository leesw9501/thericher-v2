"""Pure 4a252-bound CVaR preparation/replay; no input IO, worker or fitting.

Only in-memory geometry/price selection/covariance/target/metrics helpers are
reused. Their historical source loaders and worker contracts are never called.
Parent owns exact source attestation, action publication and the shared budget.
"""

from __future__ import annotations

import math
import time
from datetime import date
from decimal import Decimal, localcontext

import numpy as np

from thericher_v2.research import empirical_cvar as cvar
from thericher_v2.research import kis_cross_asset_erc_development as erc_study

NAME = "kis-cross-asset-cvar-development-v1"
INPUT_PIN, COMMITMENT_ID = erc_study.INPUT_PIN, erc_study.COMMITMENT_ID
INPUT_RELATIVE = erc_study.INPUT_RELATIVE
CANDIDATES = ("cvar",)
CONTROLS = ("erc", "minvar", "equal_thirds")
RISK_POLICIES = CANDIDATES + CONTROLS
POLICIES = RISK_POLICIES + ("cash",)
COSTS = (Decimal(5), Decimal(10), Decimal(20))
SECONDS, WORK_SECONDS, CLEANUP_SECONDS = 300, 270, 30
TOLERANCE = Decimal("1e-10")
prior, base, nav, solver = erc_study.prior, erc_study.base, erc_study.nav, erc_study.solver
require, encode, digest = prior.require, prior.encode, prior.digest
StudyPlan, required_past_dates = prior.StudyPlan, prior.required_past_dates
RUNTIME = dict(erc_study.RUNTIME)
CODE = erc_study.CODE + (
    "src/thericher_v2/research/empirical_cvar.py",
    "src/thericher_v2/research/kis_cross_asset_cvar_development.py",
)


def configuration():
    return dict(
        name=NAME,
        symbols=list(base.INSTRUMENT_ORDER),
        policies=list(POLICIES),
        cells=30,
        costs_bps_side=[str(c) for c in COSTS],
        input_commitment_sha256=INPUT_PIN,
        commitment_id=COMMITMENT_ID,
        input_relative=INPUT_RELATIVE,
        calendar_sha256=base.CALENDAR_PIN,
        image=base.IMAGE,
        runtime=dict(RUNTIME),
        scipy_runtime="parent must attest existing native distribution; no install",
        geometry=dict(monthly_entries=33, valuation_days=689, view_days=[252, 437]),
        dev_views=[["2024-01-02", "2024-12-31"], ["2025-01-02", "2026-09-30"]],
        scenarios="253 strictly prior raw CLOSEs/252 simple returns;Decimal50 HALF_EVEN "
        "then float64;no raw rounding",
        cvar="fixed95% empirical LP on RAW scenarios;equal probabilities;12.6 tail mass; "
        "one HiGHS solve/month;no mean target/secondary objective/fallback",
        covariance="population ddof0;common0.75*C+0.25*diag(C) for controls/risk cap",
        minvar="existing internal10% shrink compensated by input(5/6)*C+(1/6)*diag(C)",
        target_numeric="existing45dp normalized simplex from attested solver weights; "
        "Decimal50 scaling/exact residual cash;no negative clipping",
        cap="ALL four risky policies min(1,.10/sqrt(252*w'C_shrunk*w));no leverage; "
        "same ceiling not identical risk;NOT Paper10%-of-original-basis budget",
        timing="33 first scheduled month OPENs;previous scheduled CLOSE decisions; "
        "seal all actions before forward marks;no future-support filter",
        accounting="three_asset_nav.replay;fractional NAV1 once/policy/cost;continuous "
        "cash/inventory/views;monthly OPEN drift rebalance;final CLOSE liquidation only; "
        "Decimal50 actual-notional fees EACH SIDE;cash earns0",
        utility="252*(mean daily log return-5*population variance)",
        diagnostics="daily ES95 of negative SIMPLE net returns/exact fractional tail mass; "
        "running-peak DD across views;sum actual traded notional/previous CLOSE NAV",
        kill="10bps EACH SIDE BOTH views cvar growth>0 and>cash;utility exceeds "
        "erc/minvar/equal_thirds by>1e-10;ES/DD/turnover descriptive only",
        seconds=SECONDS,
        work_seconds=WORK_SECONDS,
        cleanup_seconds=CLEANUP_SECONDS,
        cpu=2,
        memory_bytes=2 * 1024**3,
        network="none",
        actual_fits=0,
        gpu=False,
        source_io=False,
        holdout_access="none",
        paper_input=False,
        grade="RAW_PRICE_ONLY_SEEN_SOURCE_DEVELOPMENT",
        lineage=[erc_study.NAME],
        limitations=[
            "MODP0 raw;CA/splits/dividends/TR not applied;chunk vintages differ",
            "PIT/finality/decision-time availability not observed",
            "ideal fractional fills;overlapping monthly contexts not independent",
            "about13 empirical tail observations;weak tail estimation",
            "solver ties runtime/order-dependent;no cross-runtime equivalence",
            "seen DEV;no fresh holdout/independent alpha/Paper qualification",
        ],
    )


def build_plan(sessions):
    return erc_study.build_plan(sessions)


def _due(deadline, clock):
    observed = clock()
    require(
        type(observed) in (int, float) and math.isfinite(observed) and observed < deadline,
        "compute_stop",
    )


def returns_from_closes(columns):
    require(len(columns) == 3 and all(len(c) == 253 for c in columns), "close_geometry")
    require(
        all(type(v) is Decimal and v.is_finite() and v > 0 for c in columns for v in c),
        "required_price",
    )
    with localcontext(base.CONTEXT):
        values = tuple(tuple((b - a) / a for a, b in zip(c, c[1:], strict=False)) for c in columns)
    returns = np.asarray(values, dtype=np.float64).T
    require(
        returns.shape == (252, 3)
        and np.isfinite(returns).all()
        and (returns > -1).all()
        and all(
            v == 0 or f != 0
            for column, floats in zip(values, returns.T, strict=True)
            for v, f in zip(column, floats, strict=True)
        ),
        "returns_not_representable",
    )
    returns.setflags(write=False)
    return returns


def risk_allocations(columns):
    """CVaR uses raw scenarios; control allocation/caps share fixed25% covariance."""
    returns = returns_from_closes(columns)
    covariance = prior.covariance_from_closes(columns)
    solution = cvar.solve_cvar95(returns)
    diagonal = np.diag(np.diag(covariance))
    shrunk = 0.75 * covariance + 0.25 * diagonal
    weights = (
        solver._normalized(tuple(Decimal.from_float(v) for v in solution.weights)),
        erc_study.erc.equal_risk_contribution_weights(shrunk),
        solver.minimum_variance_weights((5 / 6) * covariance + (1 / 6) * diagonal),
        solver._normalized((Decimal(1),) * 3),
    )
    targets, facts = {}, {}
    for policy, w in zip(RISK_POLICIES, weights, strict=True):
        floats = np.asarray(w, dtype=np.float64)
        variance = float(floats @ shrunk @ floats)
        require(math.isfinite(variance) and variance >= 0, "risk_not_representable")
        volatility = math.sqrt(252 * variance)
        require(math.isfinite(volatility), "risk_not_representable")
        exposure = Decimal(1) if volatility <= 0.10 else Decimal.from_float(0.10 / volatility)
        target = prior.scaled_target(w, exposure)
        attained = np.asarray(target.weights3, dtype=np.float64)
        attained_vol = math.sqrt(252 * float(attained @ shrunk @ attained))
        require(math.isfinite(attained_vol), "risk_not_representable")
        targets[policy] = target
        facts[policy] = dict(
            forecast_volatility=volatility,
            exposure=str(exposure),
            attained_forecast_volatility=attained_vol,
        )
    facts["cvar"].update(solution.safe_facts(), empirical_cvar95=str(solution.cvar))
    targets["cash"] = nav.ThreeAssetTarget((Decimal(0),) * 3, Decimal(1))
    return targets, facts


def prepare_actions(
    rows_by_symbol,
    plan,
    vintage_ref,
    *,
    input_commitment_sha256,
    deadline=float("inf"),
    clock=time.monotonic,
):
    require(input_commitment_sha256 == INPUT_PIN and vintage_ref == COMMITMENT_ID, "input_binding")
    require(build_plan(plan.sessions) == plan, "plan_changed")
    actions, diagnostics, past = {p: [] for p in POLICIES}, [], []
    for index in plan.entry_indices:
        _due(deadline, clock)
        dates = tuple(s.session_date for s in plan.sessions[index - 253 : index])
        columns = prior._selected_closes(rows_by_symbol, dates, vintage_ref)
        targets, facts = risk_allocations(columns)
        _due(deadline, clock)
        day = plan.sessions[index].session_date.isoformat()
        past.append(digest(encode([[str(v) for v in c] for c in columns])))
        diagnostics.append(dict(entry_date=day, policies=facts))
        for policy, target in targets.items():
            actions[policy].append([day, *map(str, target.weights3), str(target.cash_weight)])
    _due(deadline, clock)
    return dict(
        plan=plan.record(),
        vintage_ref=vintage_ref,
        input_commitment_sha256=INPUT_PIN,
        past_input_sha256=digest(encode(past)),
        actions=actions,
        diagnostics=diagnostics,
    )


def _diagnostics(daily, entering):
    with localcontext(base.CONTEXT):
        losses = sorted((-d.simple_return for d in daily), reverse=True)
        whole, remainder = divmod(len(losses), 20)
        tail = sum(losses[:whole], Decimal(0))
        if remainder:
            tail += losses[whole] * Decimal(remainder) / 20
        es = tail / (Decimal(len(losses)) / 20)
        turnover, previous = Decimal(0), entering
        for day in daily:
            turnover += day.traded_notional / previous
            previous = day.nav
    return dict(daily_es95=str(es), turnover_previous_close_nav=str(turnover))


def evaluate(days, actions, plan, *, deadline=float("inf"), clock=time.monotonic):
    """15 continuous fractional ledgers, split into30 views; never boundary reset."""
    require(build_plan(plan.sessions) == plan, "plan_changed")
    require(
        actions["plan"] == plan.record()
        and set(actions["actions"]) == set(POLICIES)
        and actions["vintage_ref"] == COMMITMENT_ID
        and actions["input_commitment_sha256"] == INPUT_PIN,
        "action_binding",
    )
    require(tuple(d.date for d in days) == plan.dates, "forward_mark_gap")
    sealed, cells = digest(encode(actions)), []
    keys = [plan.sessions[i].session_date.isoformat() for i in plan.entry_indices]
    for cost in COSTS:
        for policy in POLICIES:
            _due(deadline, clock)
            rows = actions["actions"][policy]
            require(
                all(type(r) is list and len(r) == 5 for r in rows) and [r[0] for r in rows] == keys,
                "action_keys",
            )
            targets = {
                date.fromisoformat(r[0]): nav.ThreeAssetTarget(
                    tuple(Decimal(w) for w in r[1:4]), Decimal(r[4])
                )
                for r in rows
            }
            ledger = nav.replay(days, targets, cost)
            _due(deadline, clock)
            cut, peak = plan.block_cut, Decimal(1)
            for block, subset, entering in (
                (0, ledger.daily[:cut], Decimal(1)),
                (1, ledger.daily[cut:], ledger.daily[cut - 1].nav),
            ):
                metrics, peak = prior._metrics(
                    subset, entering, peak, sum(d.date in targets for d in subset)
                )
                metrics.update(_diagnostics(subset, entering))
                cells.append(
                    dict(
                        block=block,
                        policy=policy,
                        cost_bps=str(cost),
                        status="complete",
                        metrics=metrics,
                    )
                )
    require(digest(encode(actions)) == sealed, "action_changed")
    _due(deadline, clock)
    return cells


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    require(
        len(cells) == 30
        and {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == expected
        and all(c["status"] == "complete" for c in cells),
        "cell_matrix",
    )
    require(
        all(
            type(c["metrics"][k]) is str and Decimal(c["metrics"][k]).is_finite()
            for c in cells
            for k in ("growth", "utility")
        ),
        "cell_metrics",
    )
    with localcontext(base.CONTEXT):
        for block in (0, 1):
            group = {
                c["policy"]: c["metrics"]
                for c in cells
                if c["block"] == block and c["cost_bps"] == "10"
            }
            own = group["cvar"]
            if (
                Decimal(own["growth"]) <= 0
                or Decimal(own["growth"]) <= Decimal(group["cash"]["growth"])
                or any(
                    Decimal(own["utility"]) - Decimal(group[p]["utility"]) <= TOLERANCE
                    for p in CONTROLS
                )
            ):
                return {"cvar": "rejected"}
    return {"cvar": "development_survivor"}

"""Pure, source-bound ERC preparation; no worker, source IO, or promotion.

Parent supplies hash-attested 4a252 raw OC rows/calendar. Reused legacy helpers
perform only in-memory past selection, covariance and NAV arithmetic; their
02dcc IO/contract/run paths are never called. This is seen-data development.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, localcontext

import numpy as np

from thericher_v2.research import equal_risk_contribution as erc
from thericher_v2.research import kis_causal_risk_allocation as prior

NAME = "kis-cross-asset-erc-development-v1"
INPUT_PIN = "sha256:4a25284d8ae8538105c798cbc0337ef3ca9615977829eb2d3d951797cbc5dc64"
COMMITMENT_ID = "02b27fdd7b181a1af9598b30db69cc9b9108e746ca7d74c2e5623e2ed0345c10"
INPUT_RELATIVE = (
    "research/kis-cross-asset-oc-cohort-v1/input/"
    "cross-asset-oc-cohort-20261008-v1/input-commitment.json"
)
CANDIDATES = ("candidate",)
RISK_POLICIES = ("candidate", "minvar", "inverse_volatility", "equal_thirds", "SPY")
POLICIES = RISK_POLICIES + ("cash",)
CONTROLS = ("inverse_volatility", "minvar", "equal_thirds")
COSTS, RUNTIME = prior.COSTS, dict(prior.RUNTIME)
TOLERANCE = Decimal("1e-10")
base, nav, solver = prior.base, prior.nav, prior.solver
require, encode, digest = prior.require, prior.encode, prior.digest
StudyPlan, required_past_dates = prior.StudyPlan, prior.required_past_dates
CODE = prior.CODE + (
    "src/thericher_v2/research/equal_risk_contribution.py",
    "src/thericher_v2/research/kis_cross_asset_erc_development.py",
)


def configuration():
    return dict(
        name=NAME,
        symbols=list(base.INSTRUMENT_ORDER),
        policies=list(POLICIES),
        cells=36,
        input_commitment_sha256=INPUT_PIN,
        commitment_id=COMMITMENT_ID,
        input_relative=INPUT_RELATIVE,
        calendar_sha256=base.CALENDAR_PIN,
        image=base.IMAGE,
        runtime=dict(RUNTIME),
        geometry=dict(monthly_entries=33, valuation_days=689, view_days=[252, 437]),
        covariance="253 required past CLOSEs;252 simple returns;Decimal50 then float64;ddof0",
        shrinkage="NEW fixed25%:0.75*C+0.25*diag(C), once, all risky policies/caps",
        minvar="existing seven-face solver internally shrinks10%; input(5/6)*C+(1/6)*diag(C) "
        "makes its final matrix the fixed25% matrix, within float64 roundoff",
        erc=erc.configuration(),
        inverse_volatility="inverse sqrt diagonal; no zero fallback",
        cap="ALL five risky policies min(1,.10/sqrt(252*w'C_shrunk*w)); no leverage; "
        "same ceiling NOT identical attained risk",
        timing="33 first scheduled month OPENs; previous scheduled CLOSE decision; "
        "actions sealed before forward marks; no future-coverage mask",
        accounting="three_asset_nav.replay;NAV1 once/policy/cost;continuous inventory/views; "
        "monthly OPEN drift rebalance;final CLOSE exit only;Decimal50 actual "
        "notional fees;cash earns0;SPY same cap/cadence, descriptive only",
        target_numeric="45dp risky simplex;Decimal50 scaling;exact residual cash",
        costs_bps_side=[str(c) for c in COSTS],
        utility="252*(mean daily log-5*pop variance)",
        kill="10bps BOTH views candidate growth>0 and>cash; utility exceeds "
        "inverse_volatility/minvar/equal_thirds by>1e-10;SPY descriptive only",
        missing="required past/mark gap or ERC numerical failure is scoped unavailable; "
        "no older substitution, fallback or date deletion",
        lineage=[prior.NAME],
        grade="RAW_PRICE_ONLY_SEEN_SOURCE_DEVELOPMENT",
        limitations=[
            "MODP0 raw;CA/splits/dividends/TR not applied",
            "chunk vintages differ",
            "PIT/finality/decision-time availability not observed",
            "ideal fractional fills;overlapping histories not independent",
            "no fresh holdout, Paper or deployment claim",
        ],
        actual_fits=0,
        gpu=False,
        source_io=False,
        predictive=False,
        paper_input=False,
    )


def build_plan(sessions):
    """Reuse geometry only; caller provides the exact frozen calendar explicitly."""
    return prior.build_plan(sessions)


def risk_allocations(covariance):
    c = np.asarray(covariance, dtype=np.float64)
    require(
        c.shape == (3, 3) and np.isfinite(c).all() and np.array_equal(c, c.T), "covariance_values"
    )
    scale = float(np.abs(c).max())
    require(
        scale > 0
        and (np.diag(c) > 0).all()
        and np.linalg.eigvalsh(c / scale)[0] >= -64 * np.finfo(float).eps,
        "covariance_values",
    )
    diagonal = np.diag(np.diag(c))
    shrunk = 0.75 * c + 0.25 * diagonal
    # Compensate the reused solver's built-in 10%, not a second 25% shrink.
    solver_input = (5 / 6) * c + (1 / 6) * diagonal
    weights = (
        erc.equal_risk_contribution_weights(shrunk),
        solver.minimum_variance_weights(solver_input),
        solver._normalized(tuple(Decimal.from_float(1 / math.sqrt(v)) for v in np.diag(c))),
        solver._normalized((Decimal(1),) * 3),
        (Decimal(1), Decimal(0), Decimal(0)),
    )
    targets, facts = {}, {}
    for policy, w in zip(RISK_POLICIES, weights, strict=True):
        values = np.asarray(w, dtype=np.float64)
        variance = float(values @ shrunk @ values)
        require(math.isfinite(variance) and variance > 0, "risk_not_representable")
        vol = math.sqrt(252 * variance)
        require(math.isfinite(vol), "risk_not_representable")
        exposure = Decimal(1) if vol <= 0.10 else Decimal.from_float(0.10 / vol)
        target = prior.scaled_target(w, exposure)
        attained = np.asarray(target.weights3, dtype=np.float64)
        targets[policy] = target
        facts[policy] = dict(
            forecast_volatility=vol,
            exposure=str(exposure),
            attained_forecast_volatility=math.sqrt(252 * float(attained @ shrunk @ attained)),
        )
    targets["cash"] = nav.ThreeAssetTarget((Decimal(0),) * 3, Decimal(1))
    return targets, facts


def prepare_actions(rows_by_symbol, plan, vintage_ref, *, input_commitment_sha256):
    """Private in-memory seal; identity checks do not replace parent source hash attestation."""
    require(input_commitment_sha256 == INPUT_PIN and vintage_ref == COMMITMENT_ID, "input_binding")
    require(build_plan(plan.sessions) == plan, "plan_changed")
    actions, diagnostics, past = {p: [] for p in POLICIES}, [], []
    for index in plan.entry_indices:
        dates = tuple(s.session_date for s in plan.sessions[index - 253 : index])
        columns = prior._selected_closes(rows_by_symbol, dates, vintage_ref)
        targets, facts = risk_allocations(prior.covariance_from_closes(columns))
        day = plan.sessions[index].session_date.isoformat()
        past.append(digest(encode([[str(v) for v in c] for c in columns])))
        diagnostics.append(dict(entry_date=day, policies=facts))
        for policy, target in targets.items():
            actions[policy].append([day, *map(str, target.weights3), str(target.cash_weight)])
    return dict(
        plan=plan.record(),
        vintage_ref=vintage_ref,
        input_commitment_sha256=INPUT_PIN,
        past_input_sha256=digest(encode(past)),
        actions=actions,
        diagnostics=diagnostics,
    )


def evaluate(days, actions, plan):
    """One continuous shared-cash ledger per policy/cost; two views, never two resets."""
    require(build_plan(plan.sessions) == plan, "plan_changed")
    require(
        actions["plan"] == plan.record()
        and set(actions["actions"]) == set(POLICIES)
        and actions["vintage_ref"] == COMMITMENT_ID
        and actions["input_commitment_sha256"] == INPUT_PIN,
        "action_binding",
    )
    require(tuple(d.date for d in days) == plan.dates, "forward_mark_gap")
    seal, cells = digest(encode(actions)), []
    keys = [plan.sessions[i].session_date.isoformat() for i in plan.entry_indices]
    for cost in COSTS:
        for policy in POLICIES:
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
            cut, peak = plan.block_cut, Decimal(1)
            for block, subset, entering in (
                (0, ledger.daily[:cut], Decimal(1)),
                (1, ledger.daily[cut:], ledger.daily[cut - 1].nav),
            ):
                metrics, peak = prior._metrics(
                    subset, entering, peak, sum(d.date in targets for d in subset)
                )
                cells.append(
                    dict(
                        block=block,
                        policy=policy,
                        cost_bps=str(cost),
                        status="complete",
                        metrics=metrics,
                    )
                )
    require(digest(encode(actions)) == seal, "action_changed")
    return cells


def criterion(cells):
    expected = {(b, p, str(c)) for b in (0, 1) for p in POLICIES for c in COSTS}
    require(
        len(cells) == 36
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
            own = group["candidate"]
            if (
                Decimal(own["growth"]) <= 0
                or Decimal(own["growth"]) <= Decimal(group["cash"]["growth"])
                or any(
                    Decimal(own["utility"]) - Decimal(group[p]["utility"]) <= TOLERANCE
                    for p in CONTROLS
                )
            ):
                return {"candidate": "rejected"}
    return {"candidate": "development_survivor"}

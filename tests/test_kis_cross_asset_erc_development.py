"""Synthetic ERC comparison preparation; no private source or worker execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Context, Decimal, localcontext
from fractions import Fraction

import numpy as np
import pytest

from thericher_v2.research import kis_cross_asset_erc_development as study

D = Decimal
COV = np.array(
    [[0.0004, 0.00012, -0.00003], [0.00012, 0.0009, 0.00008], [-0.00003, 0.00008, 0.000225]]
)


@pytest.fixture(scope="module")
def plan():
    return study.build_plan(study.base.calendar_sessions())


@pytest.fixture(scope="module")
def closes(plan):
    dates = sorted(study.required_past_dates(plan))
    return {
        symbol: tuple(
            study.base.PriceClose(
                symbol, day, study.COMMITMENT_ID, D(100 + ((i * (j + 3)) % (11 + j)))
            )
            for i, day in enumerate(dates)
        )
        for j, symbol in enumerate(study.base.INSTRUMENT_ORDER)
    }


def prepare(rows, plan, **kwargs):
    return study.prepare_actions(
        rows, plan, study.COMMITMENT_ID, input_commitment_sha256=study.INPUT_PIN, **kwargs
    )


def sealed_actions(plan):
    targets, _ = study.risk_allocations(COV)
    keys = [plan.sessions[i].session_date.isoformat() for i in plan.entry_indices]
    return dict(
        plan=plan.record(),
        vintage_ref=study.COMMITMENT_ID,
        input_commitment_sha256=study.INPUT_PIN,
        actions={
            p: [[key, *map(str, t.weights3), str(t.cash_weight)] for key in keys]
            for p, t in targets.items()
        },
    )


def synthetic_cells():
    return [
        dict(
            block=b,
            policy=p,
            cost_bps=str(c),
            status="complete",
            metrics=dict(
                growth=".01" if p == "candidate" else "0",
                utility=".02" if p == "candidate" else "0",
            ),
        )
        for c in study.COSTS
        for p in study.POLICIES
        for b in (0, 1)
    ]


def cell(cells, block, policy, cost="10"):
    return next(
        c for c in cells if (c["block"], c["policy"], c["cost_bps"]) == (block, policy, cost)
    )


def test_configuration_is_fixed_new_contract_not_legacy_io():
    config = study.configuration()
    assert config["cells"] == 36 and config["actual_fits"] == 0
    assert config["input_commitment_sha256"] == study.INPUT_PIN != study.base.INPUT_PIN
    assert config["commitment_id"] == study.COMMITMENT_ID
    assert config["policies"] == list(study.POLICIES)
    assert config["costs_bps_side"] == ["2.5", "5", "10"]
    assert "25%" in config["shrinkage"] and "10%" in config["minvar"]
    assert config["lineage"] == [study.prior.NAME]
    assert not any(config[k] for k in ("gpu", "source_io", "predictive", "paper_input"))
    assert study.configuration() == config


def test_exact_geometry_and_explicit_calendar(plan):
    assert (len(plan.entry_indices), len(plan.dates), plan.block_cut) == (33, 689, 252)
    assert plan.dates[0] == date(2024, 1, 2) and plan.dates[-1] == date(2026, 9, 30)
    assert all(len(r["history_dates"]) == 253 for r in plan.record()["entries"])
    with pytest.raises(TypeError):
        study.build_plan()
    with pytest.raises(study.base.StudyFault):
        study.build_plan(plan.sessions[:-100])


def test_minvar_internal_shrink_compensated_not_double(monkeypatch):
    original = study.solver.minimum_variance_weights
    captured = []

    def solver(c):
        captured.append(c.copy())
        return original(c)

    monkeypatch.setattr(study.solver, "minimum_variance_weights", solver)
    study.risk_allocations(COV)
    actual = 0.9 * captured[0] + 0.1 * np.diag(np.diag(captured[0]))
    expected = 0.75 * COV + 0.25 * np.diag(np.diag(COV))
    assert np.allclose(actual, expected, atol=1e-19, rtol=2e-15)
    assert not np.allclose(actual, 0.9 * expected + 0.1 * np.diag(np.diag(expected)), atol=1e-12)


def test_erc_contributions_and_all_risky_policies_use_same_cap():
    targets, facts = study.risk_allocations(COV)
    shrunk = 0.75 * COV + 0.25 * np.diag(np.diag(COV))
    target = targets["candidate"]
    w = np.array(target.weights3, dtype=float)
    rc = w * (shrunk @ w) / (w @ shrunk @ w)
    assert np.max(abs(rc - 1 / 3)) < 2e-12
    for policy in study.RISK_POLICIES:
        t, f = targets[policy], facts[policy]
        assert sum(map(Fraction, (*t.weights3, t.cash_weight))) == 1
        assert f["attained_forecast_volatility"] <= 0.10 + 1e-15
        assert 0 < D(f["exposure"]) <= 1
        assert all(v >= 0 for v in (*t.weights3, t.cash_weight))
    assert targets["SPY"].weights3[1:] == (D(0), D(0))
    assert targets["cash"].weights3 == (D(0),) * 3
    assert targets["cash"].cash_weight == 1


def test_diagonal_erc_matches_inversevol_and_lowvol_no_leverage():
    targets, facts = study.risk_allocations(np.diag([1e-7, 4e-7, 9e-7]))
    assert np.allclose(
        np.array(targets["candidate"].weights3, dtype=float),
        np.array(targets["inverse_volatility"].weights3, dtype=float),
        atol=1e-12,
    )
    assert all(D(f["exposure"]) == 1 for f in facts.values())


def test_covariance_correlation_changes_erc_not_inversevol():
    a, _ = study.risk_allocations(COV)
    b, _ = study.risk_allocations(np.diag(np.diag(COV)))
    w = lambda t: np.array(t.weights3, dtype=float) / sum(map(float, t.weights3))  # noqa: E731
    assert not np.allclose(w(a["candidate"]), w(b["candidate"]), atol=1e-6)
    assert np.allclose(w(a["inverse_volatility"]), w(b["inverse_volatility"]), atol=1e-14)


@pytest.mark.parametrize(
    "c",
    [
        np.zeros((3, 3)),
        np.eye(2),
        np.eye(3) * np.nan,
        [[1, 0.1, 0], [0, 1, 0], [0, 0, 1]],
        np.diag([1.0, 0.0, 1.0]),
        [[1, 2, 0], [2, 1, 0], [0, 0, 1]],
    ],
)
def test_invalid_covariance_no_fallback(c):
    with pytest.raises((study.base.StudyFault, study.erc.EqualRiskContributionUnavailable)):
        study.risk_allocations(c)


@pytest.mark.parametrize("precision", [7, 28])
def test_numeric_context_independence(precision):
    expected = study.risk_allocations(COV)
    with localcontext(Context(prec=precision)):
        assert study.risk_allocations(COV) == expected


@pytest.mark.parametrize("mutation", ["add", "price", "remove", "wrong_vintage"])
def test_after_last_decision_future_support_irrelevant(plan, closes, mutation):
    expected = prepare(closes, plan)
    future = study.base.PriceClose("SPY", plan.dates[-1], study.COMMITMENT_ID, D(99))
    rows = dict(closes, SPY=closes["SPY"] + (future,))
    if mutation == "price":
        rows["SPY"] = rows["SPY"][:-1] + (replace(future, close=D("1e40")),)
    elif mutation == "wrong_vintage":
        rows["SPY"] = rows["SPY"][:-1] + (replace(future, vintage_ref="future"),)
    elif mutation == "remove":
        rows = closes
    assert prepare(rows, plan) == expected


def test_current_and_future_rows_cannot_change_first_decision(plan, closes):
    expected = prepare(closes, plan)
    entry = plan.sessions[plan.entry_indices[0]].session_date
    rows = {
        s: tuple(replace(r, close=r.close * 2) if r.session_date >= entry else r for r in values)
        for s, values in closes.items()
    }
    actual = prepare(rows, plan)
    for p in study.POLICIES:
        assert actual["actions"][p][0] == expected["actions"][p][0]
    assert actual["diagnostics"][0] == expected["diagnostics"][0]


@pytest.mark.parametrize("symbol", study.base.INSTRUMENT_ORDER)
def test_one_required_past_gap_is_unavailable_not_cash(plan, closes, symbol):
    rows = dict(closes, **{symbol: closes[symbol][1:]})
    with pytest.raises(study.base.StudyFault, match="required_session_missing"):
        prepare(rows, plan)


@pytest.mark.parametrize("mutation", ["duplicate", "vintage"])
def test_required_rows_strict_binding(plan, closes, mutation):
    rows = dict(closes)
    first = rows["SPY"][0]
    rows["SPY"] = (
        (first,) + rows["SPY"]
        if mutation == "duplicate"
        else (replace(first, vintage_ref="other"),) + rows["SPY"][1:]
    )
    with pytest.raises(study.base.StudyFault):
        prepare(rows, plan)


@pytest.mark.parametrize(
    "pin,vintage", [(study.base.INPUT_PIN, study.COMMITMENT_ID), (study.INPUT_PIN, "unbound")]
)
def test_legacy_input_identity_rejected(plan, closes, pin, vintage):
    with pytest.raises(study.base.StudyFault, match="input_binding"):
        study.prepare_actions(closes, plan, vintage, input_commitment_sha256=pin)


def test_continuous_ledger_36cells_actions_unchanged_and_restart_exact(plan):
    actions = sealed_actions(plan)
    before = study.encode(actions)
    days = tuple(
        study.nav.ThreeAssetDay(d, (D(100 + i),) * 3, (D(101 + i),) * 3)
        for i, d in enumerate(plan.dates)
    )
    cells = study.evaluate(days, actions, plan)
    assert len(cells) == 36 and study.encode(actions) == before
    assert study.evaluate(days, deepcopy(actions), plan) == cells
    expected = {(b, p, str(c)) for c in study.COSTS for p in study.POLICIES for b in (0, 1)}
    assert {(c["block"], c["policy"], c["cost_bps"]) for c in cells} == expected
    for policy in study.POLICIES:
        for cost in study.COSTS:
            a, b = [cell(cells, block, policy, str(cost))["metrics"] for block in (0, 1)]
            assert b["entering_nav"] == a["nav"]
            assert b["running_peak_entry"] == a["running_peak_exit"]
            assert (a["entries"], b["entries"], a["days"], b["days"]) == (12, 21, 252, 437)
    assert D(cell(cells, 0, "SPY")["metrics"]["entering_nav"]) == 1
    assert D(cell(cells, 1, "SPY")["metrics"]["entering_nav"]) != 1
    assert D(cell(cells, 1, "cash")["metrics"]["fees"]) == 0


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "action", "pin"])
def test_forward_mark_and_seal_faults_never_drop_days(plan, mutation):
    days = tuple(study.nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in plan.dates)
    actions = sealed_actions(plan)
    if mutation == "gap":
        days = days[:252] + days[253:]
    elif mutation == "duplicate":
        days = days[:252] + (days[251],) + days[253:]
    elif mutation == "action":
        actions["actions"]["candidate"].pop()
    else:
        actions["input_commitment_sha256"] = study.base.INPUT_PIN
    with pytest.raises(study.base.StudyFault):
        study.evaluate(days, actions, plan)


def test_new_kill_positive_utility_can_survive_lower_spy_wealth():
    cells = synthetic_cells()
    for b in (0, 1):
        cell(cells, b, "SPY")["metrics"].update(growth="1", utility="1")
    assert study.criterion(cells) == {"candidate": "development_survivor"}


@pytest.mark.parametrize("value", ["0", "-.01", "1e-40"])
def test_growth_floor_exact_not_epsilon(value):
    cells = synthetic_cells()
    cell(cells, 1, "candidate")["metrics"]["growth"] = value
    assert study.criterion(cells) == {
        "candidate": ("development_survivor" if D(value) > 0 else "rejected")
    }


@pytest.mark.parametrize("control", study.CONTROLS)
def test_positive_growth_utility_not_better_than_each_control_rejects(control):
    cells = synthetic_cells()
    cell(cells, 1, control)["metrics"]["utility"] = ".03"
    assert study.criterion(cells) == {"candidate": "rejected"}


def test_exact_utility_epsilon_rejects_hostile_decimal_context():
    cells = synthetic_cells()
    cell(cells, 1, "candidate")["metrics"]["utility"] = ".0000000001"
    with localcontext(Context(prec=7)):
        assert study.criterion(cells) == {"candidate": "rejected"}
    cell(cells, 1, "candidate")["metrics"]["utility"] = ".00000000010000000001"
    assert study.criterion(cells) == {"candidate": "development_survivor"}


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "incomplete", "nonfinite"])
def test_kill_requires_complete_finite_fixed_matrix(mutation):
    cells = synthetic_cells()
    if mutation == "missing":
        cells.pop()
    elif mutation == "duplicate":
        cells[-1] = cells[0]
    elif mutation == "incomplete":
        cells[0]["status"] = "input_unavailable"
    else:
        cells[0]["metrics"]["utility"] = "NaN"
    with pytest.raises(study.base.StudyFault):
        study.criterion(cells)


def test_pure_functions_never_use_legacy_io_or_current_calendar(plan, closes, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("IO/worker/implicit calendar forbidden")

    for obj, name in (
        (study.base, "_read"),
        (study.base, "_json"),
        (study.base, "calendar_sessions"),
        (study.prior, "run"),
        (study.prior, "read_contract"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    actions = prepare(closes, plan)
    days = tuple(study.nav.ThreeAssetDay(d, (D(100),) * 3, (D(100),) * 3) for d in plan.dates)
    assert len(study.evaluate(days, actions, plan)) == 36

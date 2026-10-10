"""Manufactured price-only campaign tests; no provider, private rows or worker."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from thericher_v2.research import kis_cross_asset_cvar_development as study

D = Decimal


@pytest.fixture(scope="module")
def plan():
    return study.build_plan(study.base.calendar_sessions())


@pytest.fixture(scope="module")
def closes(plan):
    dates = sorted(study.required_past_dates(plan))
    return {
        symbol: tuple(
            study.base.PriceClose(
                symbol, day, study.COMMITMENT_ID, D(100 + (i * (j + 3)) % (11 + j))
            )
            for i, day in enumerate(dates)
        )
        for j, symbol in enumerate(study.base.INSTRUMENT_ORDER)
    }


def columns(plan, closes):
    index = plan.entry_indices[0]
    dates = tuple(s.session_date for s in plan.sessions[index - 253 : index])
    return study.prior._selected_closes(closes, dates, study.COMMITMENT_ID)


def prepare(closes, plan, **kwargs):
    return study.prepare_actions(
        closes, plan, study.COMMITMENT_ID, input_commitment_sha256=study.INPUT_PIN, **kwargs
    )


@pytest.fixture(scope="module")
def prepared(plan, closes):
    return prepare(closes, plan)


def sealed_actions(plan):
    keys = [plan.sessions[i].session_date.isoformat() for i in plan.entry_indices]
    risky = (".25", ".25", ".25", ".25")
    cash = ("0", "0", "0", "1")
    return dict(
        plan=plan.record(),
        vintage_ref=study.COMMITMENT_ID,
        input_commitment_sha256=study.INPUT_PIN,
        actions={p: [[k, *(cash if p == "cash" else risky)] for k in keys] for p in study.POLICIES},
    )


@pytest.fixture(scope="module")
def marks(plan):
    return tuple(
        study.nav.ThreeAssetDay(d, (D(100 + i),) * 3, (D(101 + i),) * 3)
        for i, d in enumerate(plan.dates)
    )


@pytest.fixture(scope="module")
def evaluated(plan, marks):
    return study.evaluate(marks, sealed_actions(plan), plan)


def synthetic_cells():
    return [
        dict(
            block=b,
            policy=p,
            cost_bps=str(c),
            status="complete",
            metrics=dict(
                growth=".01" if p == "cvar" else "0", utility=".02" if p == "cvar" else "0"
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


def test_fixed_configuration_new_costs_and_no_legacy_io():
    config = study.configuration()
    assert config["cells"] == 30 and config["actual_fits"] == 0
    assert config["policies"] == ["cvar", "erc", "minvar", "equal_thirds", "cash"]
    assert config["costs_bps_side"] == ["5", "10", "20"]
    assert config["input_commitment_sha256"] == study.INPUT_PIN != study.base.INPUT_PIN
    assert config["commitment_id"] == study.COMMITMENT_ID
    assert "Paper10%" in config["cap"] and "EACH SIDE" in config["accounting"]
    assert (config["seconds"], config["work_seconds"], config["cleanup_seconds"]) == (300, 270, 30)
    assert all(config[k] is False for k in ("gpu", "source_io", "paper_input"))
    assert study.configuration() == config


def test_explicit_calendar_exact_monthly_geometry(plan):
    assert (len(plan.entry_indices), len(plan.dates), plan.block_cut) == (33, 689, 252)
    assert plan.dates[0] == date(2024, 1, 2) and plan.dates[-1] == date(2026, 9, 30)
    assert all(len(r["history_dates"]) == 253 for r in plan.record()["entries"])
    assert all(r["history_dates"][-1] < r["entry_date"] for r in plan.record()["entries"])
    with pytest.raises(TypeError):
        study.build_plan()
    with pytest.raises(study.base.StudyFault):
        study.build_plan(plan.sessions[:-100])


def test_decimal50_raw_returns_no_cent_rounding_and_hostile_context(plan, closes):
    raw = columns(plan, closes)
    raw = tuple((D("100.00013"),) + c[1:] for c in raw)
    result = study.returns_from_closes(raw)
    with localcontext(study.base.CONTEXT):
        expected = np.array(
            [[(b - a) / a for a, b in zip(c, c[1:], strict=False)] for c in raw], dtype=np.float64
        ).T
    assert result.shape == (252, 3) and result.dtype == np.float64
    assert np.array_equal(result, expected) and not result.flags.writeable
    for precision in (7, 28):
        with localcontext(Context(prec=precision)):
            assert np.array_equal(study.returns_from_closes(raw), result)
    assert result[0, 0] != float((raw[0][1] - D(100)) / D(100))


def test_cvar_raw_scenarios_controls25pct_and_common_cap(plan, closes, monkeypatch):
    raw = columns(plan, closes)
    captured_returns, captured_covariances = [], []
    solve, minvar = study.cvar.solve_cvar95, study.solver.minimum_variance_weights

    def capture_returns(values):
        captured_returns.append(values.copy())
        return solve(values)

    def capture_covariance(values):
        captured_covariances.append(values.copy())
        return minvar(values)

    monkeypatch.setattr(study.cvar, "solve_cvar95", capture_returns)
    monkeypatch.setattr(study.solver, "minimum_variance_weights", capture_covariance)
    targets, facts = study.risk_allocations(raw)
    covariance = study.prior.covariance_from_closes(raw)
    shrunk = 0.75 * covariance + 0.25 * np.diag(np.diag(covariance))
    assert np.array_equal(captured_returns[0], study.returns_from_closes(raw))
    compensated = captured_covariances[0]
    assert np.allclose(
        0.9 * compensated + 0.1 * np.diag(np.diag(compensated)), shrunk, atol=1e-19, rtol=2e-15
    )
    existing, _ = study.erc_study.risk_allocations(covariance)
    assert targets["erc"] == existing["candidate"]
    assert targets["minvar"] == existing["minvar"]
    assert targets["equal_thirds"] == existing["equal_thirds"]
    for policy in study.RISK_POLICIES:
        target = targets[policy]
        assert sum(map(Fraction, (*target.weights3, target.cash_weight))) == 1
        assert all(v >= 0 for v in (*target.weights3, target.cash_weight))
        assert 0 < D(facts[policy]["exposure"]) <= 1
        assert facts[policy]["attained_forecast_volatility"] <= 0.1 + 1e-15
    assert facts["cvar"]["tail_mass_observations"] == "12.6"


def test_low_vol_no_leverage_and_invalid_closes_fail_without_fallback():
    raw = tuple(
        tuple(D(100) + D((i * (j + 3)) % (11 + j)) / 1000 for i in range(253)) for j in range(3)
    )
    targets, facts = study.risk_allocations(raw)
    assert all(D(f["exposure"]) == 1 for f in facts.values())
    assert targets["cash"].cash_weight == 1 and targets["cash"].weights3 == (D(0),) * 3
    for malformed in (
        raw[:2],
        (raw[0][:-1], *raw[1:]),
        ((D(0), *raw[0][1:]), *raw[1:]),
        ((D("NaN"), *raw[0][1:]), *raw[1:]),
    ):
        with pytest.raises(study.base.StudyFault):
            study.risk_allocations(malformed)


def test_future_mutation_cannot_change_first_action_but_past_can(plan, closes, prepared):
    entry = plan.sessions[plan.entry_indices[0]].session_date
    rows = {
        s: tuple(replace(r, close=r.close * 2) if r.session_date >= entry else r for r in values)
        for s, values in closes.items()
    }
    actual = prepare(rows, plan)
    for policy in study.POLICIES:
        assert actual["actions"][policy][0] == prepared["actions"][policy][0]
    assert actual["diagnostics"][0] == prepared["diagnostics"][0]
    rows = dict(closes, SPY=(replace(closes["SPY"][0], close=D(200)), *closes["SPY"][1:]))
    altered = prepare(rows, plan)
    assert altered["past_input_sha256"] != prepared["past_input_sha256"]
    assert any(altered["actions"][p][0] != prepared["actions"][p][0] for p in study.RISK_POLICIES)


def test_future_support_irrelevant_and_legacy_io_forbidden(plan, closes, prepared, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("legacy IO/worker/current calendar forbidden")

    for obj, name in (
        (study.base, "_read"),
        (study.base, "_json"),
        (study.base, "calendar_sessions"),
        (study.prior, "run"),
        (study.prior, "read_contract"),
    ):
        monkeypatch.setattr(obj, name, forbidden)
    future = study.base.PriceClose("SPY", plan.dates[-1], "foreign_future", D("1e40"))
    assert prepare(dict(closes, SPY=closes["SPY"] + (future,)), plan) == prepared


def test_required_gap_duplicate_identity_and_old_pin_never_cash(plan, closes):
    first = closes["SPY"][0]
    for bad in (
        closes["SPY"][1:],
        (first, *closes["SPY"]),
        (replace(first, vintage_ref="foreign"), *closes["SPY"][1:]),
    ):
        with pytest.raises(study.base.StudyFault):
            prepare(dict(closes, SPY=bad), plan)
    for pin, vintage in ((study.base.INPUT_PIN, study.COMMITMENT_ID), (study.INPUT_PIN, "foreign")):
        with pytest.raises(study.base.StudyFault, match="input_binding"):
            study.prepare_actions(closes, plan, vintage, input_commitment_sha256=pin)


def test_one_ledger_per_policy_cost_actual_fees_and_no_view_reset(plan, marks, evaluated):
    assert len(evaluated) == 30
    actions = sealed_actions(plan)
    targets = {
        date.fromisoformat(r[0]): study.nav.ThreeAssetTarget(tuple(D(v) for v in r[1:4]), D(r[4]))
        for r in actions["actions"]["cvar"]
    }
    ledger = study.nav.replay(marks, targets, D(10))
    a, b = [cell(evaluated, i, "cvar")["metrics"] for i in (0, 1)]
    assert b["entering_nav"] == a["nav"] != "1"
    assert b["running_peak_entry"] == a["running_peak_exit"]
    assert (a["entries"], b["entries"], a["days"], b["days"]) == (12, 21, 252, 437)
    assert (
        a["trace_sha256"]
        == study.prior._metrics(ledger.daily[:252], D(1), D(1), 12)[0]["trace_sha256"]
    )
    assert D(a["fees"]) + D(b["fees"]) == pytest.approx(ledger.total_fees, rel=D("1e-27"))
    with localcontext(study.base.CONTEXT):
        assert abs(ledger.total_fees - ledger.total_traded_notional * D(".001")) < D("1e-45")
    assert ledger.final_state.quantities == (D(0),) * 3
    assert ledger.daily[251].flat is False and ledger.daily[-1].flat is True
    for block in (0, 1):
        cash = cell(evaluated, block, "cash")["metrics"]
        assert D(cash["fees"]) == D(cash["daily_es95"]) == 0
    assert study.evaluate(marks, deepcopy(actions), plan) == evaluated


def test_daily_es_exact_fractional_tail_in_both_views():
    for n in (252, 437):
        days = tuple(
            SimpleNamespace(simple_return=-D(i) / 10000, traded_notional=D(0), nav=D(1))
            for i in range(1, n + 1)
        )
        count, fraction = divmod(n, 20)
        expected = (
            sum(Fraction(i, 10000) for i in range(n - count + 1, n + 1))
            + Fraction(fraction, 20) * Fraction(n - count, 10000)
        ) / Fraction(n, 20)
        with localcontext(study.base.CONTEXT):
            exact = D(expected.numerator) / D(expected.denominator)
        for precision in (7, 28):
            with localcontext(Context(prec=precision)):
                assert D(study._diagnostics(days, D(1))["daily_es95"]) == exact


def test_main_kill_both_views_positive_cash_and_controls_diagnostics_not_selection():
    original = synthetic_cells()
    assert study.criterion(original) == {"cvar": "development_survivor"}
    for block in (0, 1):
        for policy in study.CONTROLS:
            cells = deepcopy(original)
            cell(cells, block, policy)["metrics"]["utility"] = ".03"
            assert study.criterion(cells) == {"cvar": "rejected"}
        for growth in ("0", "-.01"):
            cells = deepcopy(original)
            cell(cells, block, "cvar")["metrics"]["growth"] = growth
            assert study.criterion(cells) == {"cvar": "rejected"}
        cells = deepcopy(original)
        cell(cells, block, "cash")["metrics"]["growth"] = ".02"
        assert study.criterion(cells) == {"cvar": "rejected"}
    for c in original:
        c["metrics"].update(daily_es95="999", maximum_drawdown="999", turnover="999")
    assert study.criterion(original) == {"cvar": "development_survivor"}


def test_utility_epsilon_exact_under_hostile_decimal_context():
    cells = synthetic_cells()
    cell(cells, 1, "cvar")["metrics"]["utility"] = ".0000000001"
    with localcontext(Context(prec=7)):
        assert study.criterion(cells) == {"cvar": "rejected"}
    cell(cells, 1, "cvar")["metrics"]["utility"] = ".00000000010000000001"
    assert study.criterion(cells) == {"cvar": "development_survivor"}


def test_kill_requires_complete_exact_finite_matrix():
    for mutation in ("missing", "duplicate", "incomplete", "nonfinite"):
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


def test_forward_gaps_and_substituted_seals_reject_without_date_deletion(plan, marks):
    for mutation in ("gap", "duplicate", "action", "pin"):
        days, actions = marks, sealed_actions(plan)
        if mutation == "gap":
            days = days[:252] + days[253:]
        elif mutation == "duplicate":
            days = days[:252] + (days[251],) + days[253:]
        elif mutation == "action":
            actions["actions"]["cvar"].pop()
        else:
            actions["input_commitment_sha256"] = study.base.INPUT_PIN
        with pytest.raises(study.base.StudyFault):
            study.evaluate(days, actions, plan)


def test_deadline_after_solve_replay_and_final_checks_never_ready(plan, closes, marks, monkeypatch):
    targets = {p: study.nav.ThreeAssetTarget((D(0),) * 3, D(1)) for p in study.POLICIES}
    monkeypatch.setattr(study, "risk_allocations", lambda c: (targets, {}))
    ticks = iter((0, 11))
    with pytest.raises(study.base.StudyFault, match="compute_stop"):
        prepare(closes, plan, deadline=10, clock=lambda: next(ticks))
    ticks = iter([0] * 66 + [11])
    with pytest.raises(study.base.StudyFault, match="compute_stop"):
        prepare(closes, plan, deadline=10, clock=lambda: next(ticks))
    ticks = iter((0, 11))
    with pytest.raises(study.base.StudyFault, match="compute_stop"):
        study.evaluate(marks, sealed_actions(plan), plan, deadline=10, clock=lambda: next(ticks))
    ticks = iter([0] * 30 + [11])
    with pytest.raises(study.base.StudyFault, match="compute_stop"):
        study.evaluate(marks, sealed_actions(plan), plan, deadline=10, clock=lambda: next(ticks))


def test_hostile_context_replay_and_actions_costs_are_not_mutated(plan, marks, evaluated):
    actions = sealed_actions(plan)
    before = study.encode(actions)
    old_costs = (study.prior.COSTS, study.erc_study.COSTS, study.base.COSTS)
    with localcontext(Context(prec=7)):
        assert study.evaluate(marks, actions, plan) == evaluated
    assert study.encode(actions) == before
    assert old_costs == (study.prior.COSTS, study.erc_study.COSTS, study.base.COSTS)
    assert study.base.COSTS == (D("2.5"), D(5), D(10))

from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2.research import anticor_allocation as primitive
from thericher_v2.research import kis_cross_asset_anticor as study
from thericher_v2.research import three_asset_nav as nav
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable
from thericher_v2.research.cross_asset_hedge_failure_input import RawD1Price


def sessions(count=81):
    result = []
    day = date(2024, 1, 2)
    while len(result) < count:
        if day.weekday() < 5:
            hour = 14 if day < date(2024, 3, 11) else 13
            opened = datetime.combine(day, time(hour, 30), UTC)
            closed = datetime.combine(day, time(hour + 7), UTC)
            result.append(study.CrossAssetSession(day, opened, closed))
        day += timedelta(days=1)
    return tuple(result)


@pytest.fixture
def plan():
    return study.AnticorPlan(sessions(), tuple(range(64, 81)), 8)


def rows(plan, *, constant=False):
    return {
        symbol: tuple(RawD1Price(symbol, s.session_date, "synthetic-v1",
                                open=Decimal(100) if constant else Decimal(100 + 3 * asset + i),
                                close=Decimal(100) if constant else Decimal(101 + 3 * asset + i))
                      for i, s in enumerate(plan.sessions))
        for asset, symbol in enumerate(study.SYMBOLS)
    }


def alter(source, symbol, day, **changes):
    return {key: tuple(replace(r, **changes) if key == symbol and r.session_date == day else r
                       for r in values) for key, values in source.items()}


def context(plan, source, index=64):
    history = plan.sessions[index - 64:index]
    return study.prepare_context(source, scheduled_history=history,
                                 entry_session=plan.sessions[index],
                                 decision_at=history[-1].close_at, vintage_ref="synthetic-v1")


def test_released_primitive_bytes_are_identical():
    assert hashlib.sha256(Path(primitive.__file__).read_bytes()).hexdigest() == (
        "8c16fc5b2b93558ba41272fd86fbfc53f3dc18538bf71d0d4d4e9a60266142dd")


def test_frozen_recipe_and_provenance_no_model_or_paper():
    config = study.configuration()
    assert config["windows"] == dict(w=20, past_returns=40, past_closes=41,
                                    shared_past_closes=64,
                                    return_formula="Decimal50 ln(CLOSE[t])-ln(CLOSE[t-1]); "
                                                   "binary64 windows")
    assert config["seconds"] == 60 and config["cells"] == 30 and config["fits"] == 0
    assert not config["gpu"] and not config["paper_input"] and config["holdout"] == "none"
    assert config["input_sha256"] == study.INPUT_SHA256
    assert config["source"]["doi"] == "10.1613/jair.1336"
    assert config["policies"] == ["candidate", "balanced", "momentum63", "spy", "cash"]
    config["windows"]["w"] = 99
    assert study.configuration()["windows"]["w"] == 20


def test_default_real_calendar_geometry_without_market_data():
    import pandas_market_calendars as calendars

    schedule = calendars.get_calendar("NYSE").schedule("2016-02-02", "2026-10-07")
    frozen = tuple(study.CrossAssetSession(day.date(), row.market_open.to_pydatetime(),
                                         row.market_close.to_pydatetime())
                   for day, row in schedule.iterrows())
    plan = study.build_plan(frozen)
    assert len(plan.dates) == 1442 and plan.block_cut == 753 and len(plan.entries) == 289
    assert plan.entry_indices == plan.dev_indices[::5]
    assert plan.dates[plan.block_cut] not in plan.entries
    assert plan.record()["decisions"][0] == "2020-12-31T21:00:00+00:00"


def test_default_builder_rejects_synthetic_extent(plan):
    with pytest.raises(CrossAssetInputUnavailable):
        study.build_plan(plan.sessions)


def test_exact_40_returns_recent_mean_formula_and_no_open_dependency(plan):
    source = rows(plan)
    actual = context(plan, source)
    with localcontext(study.CONTEXT):
        column = [r.close.ln() for r in source["SPY"][:64]]
        expected = tuple(float(column[j] - column[j - 1]) for j in range(24, 64))
        assert actual.momentum[0] == column[-1] - column[0]
    assert tuple(r[0] for r in actual.previous + actual.recent) == expected
    assert actual.history_dates[-41] == plan.sessions[23].session_date
    changed = {key: tuple(replace(r, open=None) for r in values) for key, values in source.items()}
    assert context(plan, changed) == actual


def test_current_future_price_and_support_mutations_do_not_change_context(plan):
    source = rows(plan)
    actual = context(plan, source)
    changed = {key: tuple(replace(r, open=Decimal("1e20"), close=Decimal("1e-20"),
                                 vintage_ref="different-future") if i >= 64 else r
                          for i, r in enumerate(values)) for key, values in source.items()}
    missing = {key: values[:64] for key, values in source.items()}
    assert context(plan, changed) == context(plan, missing) == actual


@pytest.mark.parametrize("symbol", study.SYMBOLS)
def test_required_past_gap_cannot_fall_back_to_older_observation(plan, symbol):
    source = rows(plan)
    source[symbol] = source[symbol][:24] + source[symbol][25:]
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        context(plan, source)


@pytest.mark.parametrize("changes,reason", [
    (dict(vintage_ref="other"), "required_vintage_mismatch"),
    (dict(close=None), "required_price_invalid"),
])
def test_past_vintage_and_close_requirements(plan, changes, reason):
    source = alter(rows(plan), "TLT", plan.sessions[30].session_date, **changes)
    with pytest.raises(CrossAssetInputUnavailable, match=reason):
        context(plan, source)


def test_past_duplicate_rejected_future_duplicate_ignored(plan):
    source = rows(plan)
    source["GLD"] += (source["GLD"][-1],)
    context(plan, source)
    source["GLD"] += (source["GLD"][30],)
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_duplicate"):
        context(plan, source)


def test_cutoff_early_close_and_dst(plan):
    source = rows(plan)
    history = list(plan.sessions[:64])
    history[-1] = replace(history[-1], close_at=history[-1].close_at - timedelta(hours=3))
    actual = study.prepare_context(source, scheduled_history=tuple(history),
                                   entry_session=plan.sessions[64],
                                   decision_at=history[-1].close_at, vintage_ref="synthetic-v1")
    assert actual.decision_at == history[-1].close_at
    with pytest.raises(CrossAssetInputUnavailable, match="context_cutoff"):
        study.prepare_context(source, scheduled_history=tuple(history),
                              entry_session=plan.sessions[64],
                              decision_at=plan.sessions[63].close_at, vintage_ref="synthetic-v1")
    assert plan.sessions[0].open_at.hour != plan.sessions[64].open_at.hour


def test_context_private_values_and_direct_constructor_validation(plan):
    actual = context(plan, rows(plan))
    assert "last_closes" not in repr(actual) and "momentum=" not in repr(actual)
    with pytest.raises(CrossAssetInputUnavailable, match="context_dates"):
        replace(actual, history_dates=actual.history_dates[:-1] + (actual.history_dates[-2],))
    with pytest.raises(CrossAssetInputUnavailable, match="context_shape"):
        replace(actual, recent=actual.recent[:-1])
    copied = replace(actual, previous=tuple(list(row) for row in actual.previous))
    assert all(type(row) is tuple for row in copied.previous)


@pytest.mark.parametrize("weights", [(1 / 3,) * 3, (0.1, 0.2, 0.7), (1.0, 0.0, 0.0)])
def test_canonical_decimal_weights_conserve_exact_fraction_and_residual_cash(weights):
    with localcontext(Context(prec=7)):
        target = study.canonical_target(weights)
    assert sum(map(Fraction, target.weights3)) + Fraction(target.cash_weight) == 1
    assert 0 <= target.cash_weight <= 3 * study.QUANTUM
    assert all((Fraction(w) / Fraction(study.QUANTUM)).denominator == 1 for w in target.weights3)
    if weights == (1 / 3,) * 3:
        assert target.weights3 == (study.THIRD,) * 3


def test_target_rejects_arbitrary_invalid_weight_normalization():
    with pytest.raises(ValueError, match="weight_sum"):
        study.canonical_target((0.2, 0.2, 0.2))


def test_causal_signal_drift_prior_open_and_previous_close_not_current_open(plan, monkeypatch):
    monkeypatch.setattr(study, "anticor_allocation", lambda earlier, recent, drifted: drifted)
    source = rows(plan, constant=True)
    prior_close = plan.sessions[68].session_date
    source = alter(source, "SPY", prior_close, close=Decimal(200))
    base = study.prepare_actions(source, plan, "synthetic-v1")
    second_day = plan.sessions[69].session_date
    assert base.targets["candidate"][second_day] == study.canonical_target((0.5, 0.25, 0.25))
    changed = alter(source, "SPY", second_day, open=Decimal(1000))
    changed_actions = study.prepare_actions(changed, plan, "synthetic-v1")
    assert changed_actions.targets["candidate"][second_day] == base.targets["candidate"][second_day]
    third_day = plan.sessions[74].session_date
    assert changed_actions.targets["candidate"][third_day] != base.targets["candidate"][third_day]
    first_open = alter(source, "SPY", plan.entries[0], open=Decimal(200))
    first_actions = study.prepare_actions(first_open, plan, "synthetic-v1")
    assert (first_actions.targets["candidate"][plan.entries[0]]
            == base.targets["candidate"][plan.entries[0]])
    assert first_actions.targets["candidate"][second_day] == study._balanced()


def test_missing_last_execution_open_or_future_close_not_action_eligibility_mask(plan):
    source = rows(plan)
    actual = study.prepare_actions(source, plan, "synthetic-v1")
    missing_open = alter(source, "GLD", plan.entries[-1], open=None)
    assert study.prepare_actions(missing_open, plan, "synthetic-v1").record() == actual.record()
    with pytest.raises(CrossAssetInputUnavailable, match="required_price_invalid"):
        study.prepare_marks(missing_open, plan, "synthetic-v1")
    missing_close = alter(source, "GLD", plan.dates[-1], close=None)
    assert study.prepare_actions(missing_close, plan, "synthetic-v1").record() == actual.record()
    with pytest.raises(CrossAssetInputUnavailable, match="required_price_invalid"):
        study.prepare_marks(missing_close, plan, "synthetic-v1")


def test_momentum_ties_cash_and_fixed_controls(plan):
    source = rows(plan, constant=True)
    actions = study.prepare_actions(source, plan, "synthetic-v1")
    assert all(t == study._fixed_target() for t in actions.targets["momentum63"].values())
    rising = {symbol: tuple(replace(r, close=Decimal(100 + i)) for i, r in enumerate(values))
              for symbol, values in source.items()}
    actions = study.prepare_actions(rising, plan, "synthetic-v1")
    assert all(t == study._fixed_target(0) for t in actions.targets["momentum63"].values())
    assert set(actions.targets) == set(study.POLICIES)
    assert all(tuple(values) == plan.entries for values in actions.targets.values())


def test_action_seal_copies_inputs_and_rejects_forged_fixed_cash_candidate(plan):
    actions = study.prepare_actions(rows(plan), plan, "synthetic-v1")
    original = actions.record()
    copied = {p: dict(v) for p, v in actions.targets.items()}
    seal = study.AnticorActions(plan, "synthetic-v1", copied)
    copied["spy"].clear()
    assert seal.record() == original
    with pytest.raises(TypeError):
        seal.targets["spy"][plan.entries[0]] = study._fixed_target()
    for policy in ("spy", "candidate"):
        copied = {p: dict(v) for p, v in actions.targets.items()}
        copied[policy][plan.entries[0]] = study._fixed_target()
        with pytest.raises(CrossAssetInputUnavailable):
            study.AnticorActions(plan, "synthetic-v1", copied)


def test_all_marks_required_no_drop_or_zero_pnl(plan):
    source = rows(plan)
    actions = study.prepare_actions(source, plan, "synthetic-v1")
    marks = study.prepare_marks(source, plan, "synthetic-v1")
    with pytest.raises(CrossAssetInputUnavailable, match="forward_mark_gap"):
        study.evaluate(marks[:9] + marks[10:], actions)
    with pytest.raises(CrossAssetInputUnavailable, match="forward_mark_gap"):
        study.evaluate(marks + (marks[-1],), actions)


def test_shared_capital_both_views_fees_and_short_final_holding(plan):
    source = rows(plan, constant=True)
    actions = study.prepare_actions(source, plan, "synthetic-v1")
    marks = study.prepare_marks(source, plan, "synthetic-v1")
    before = actions.record()
    cells = study.evaluate(marks, actions)
    assert actions.record() == before and len(cells) == 30
    first, second = tuple(c for c in cells if c.policy == "balanced" and c.cost_bps == 10)
    with localcontext(study.CONTEXT):
        exposure = 3 * study.THIRD
        f = Decimal(".001")
        expected = (1 - f * exposure) / (1 + f * exposure)
        combined = (1 + first.growth) * (1 + second.growth)
        assert abs(combined - expected) < Decimal("1e-43")
        assert first.fees > 0 and second.fees > 0
    ledger = nav.replay(marks, actions.targets["balanced"], Decimal(10))
    with localcontext(study.CONTEXT):
        assert first.growth == ledger.daily[plan.block_cut - 1].nav - 1
        assert second.growth == ledger.final_nav / ledger.daily[plan.block_cut - 1].nav - 1
    assert plan.dates[plan.block_cut] not in plan.entries
    assert ledger.daily[plan.block_cut].fees < Decimal("1e-43")
    assert len(plan.dates) % 5 == 2 and plan.entries[-1] == plan.dates[-2]
    assert not ledger.daily[-2].flat and ledger.daily[-1].flat
    assert first.observations == 8 and second.observations == 9
    assert study.criterion(cells) == dict(candidate="rejected")
    assert "growth=" not in repr(first) and "fees=" not in repr(second)


def test_nonconstant_paths_match_one_full_existing_ledger_with_cost_invariant_actions(plan):
    source = rows(plan)
    actions = study.prepare_actions(source, plan, "synthetic-v1")
    marks = study.prepare_marks(source, plan, "synthetic-v1")
    cells = study.evaluate(marks, actions)
    for cost in study.COSTS:
        ledger = nav.replay(marks, actions.targets["candidate"], cost)
        own = [c for c in cells if c.policy == "candidate" and c.cost_bps == cost]
        with localcontext(study.CONTEXT):
            combined = (1 + own[0].growth) * (1 + own[1].growth)
            assert abs(combined - ledger.final_nav) < Decimal("1e-45")
    assert all(c.entries == 2 for c in cells)


def test_per_asset_price_scale_does_not_change_context_or_accounting(plan):
    source = rows(plan)
    scaled = {key: tuple(replace(r, open=r.open * scale, close=r.close * scale) for r in values)
              for (key, values), scale in zip(source.items(), (Decimal(10), Decimal(5), Decimal(2)),
                                              strict=True)}
    a = study.prepare_actions(source, plan, "synthetic-v1")
    b = study.prepare_actions(scaled, plan, "synthetic-v1")
    assert a.record() == b.record()
    x = study.evaluate(study.prepare_marks(source, plan, "synthetic-v1"), a)
    y = study.evaluate(study.prepare_marks(scaled, plan, "synthetic-v1"), b)
    for original, changed in zip(x, y, strict=True):
        assert abs(original.growth - changed.growth) < Decimal("1e-43")
        assert abs(original.utility - changed.utility) < Decimal("1e-43")


def passing_cells():
    return tuple(study.AnticorCell(b, p, c, 10, 2,
                                  Decimal(".2") if p == "candidate" else Decimal(".1"),
                                  Decimal(".3") if p == "candidate" else Decimal(".2"),
                                  Decimal(1), Decimal(".001"))
                 for b in (0, 1) for p in study.POLICIES for c in study.COSTS)


def test_original_both_view_growth_and_utility_kill_not_turnover_selection():
    cells = passing_cells()
    assert study.criterion(cells) == dict(candidate="development_survivor")
    for field in ("growth", "utility"):
        changed = tuple(replace(c, **{field: Decimal(".1") if field == "growth" else Decimal(".2")})
                        if c.block == 1 and c.policy == "candidate" and c.cost_bps == 10 else c
                        for c in cells)
        assert study.criterion(changed) == dict(candidate="rejected")
    improved_other_costs = tuple(
        replace(c, growth=Decimal(".9"), utility=Decimal(".9"))
        if c.policy == "candidate" and c.cost_bps != 10 else c for c in changed)
    assert study.criterion(improved_other_costs) == dict(candidate="rejected")


@pytest.mark.parametrize("policy", study.CONTROLS)
def test_each_control_cannot_be_omitted_from_kill(policy):
    cells = tuple(replace(c, growth=Decimal(".21")) if c.policy == policy
                  and c.block == 0 and c.cost_bps == 10 else c for c in passing_cells())
    assert study.criterion(cells) == dict(candidate="rejected")


def test_exact_improvement_boundary_and_hostile_decimal_context():
    cells = tuple(replace(c, growth=Decimal(".1000000001"))
                  if c.policy == "candidate" and c.cost_bps == 10 else c for c in passing_cells())
    with localcontext(Context(prec=7)):
        assert study.criterion(cells) == dict(candidate="rejected")
        cells = tuple(replace(c, growth=Decimal(".10000000010000001"))
                      if c.policy == "candidate" and c.cost_bps == 10 else c for c in cells)
        assert study.criterion(cells) == dict(candidate="development_survivor")


def test_matrix_and_nonfinite_cell_guard_no_partial_success():
    cells = passing_cells()
    for invalid in (cells[:-1], cells[:-1] + (cells[0],)):
        with pytest.raises(CrossAssetInputUnavailable, match="cell_matrix"):
            study.criterion(invalid)
    invalid = (replace(cells[0], utility=Decimal("NaN")),) + cells[1:]
    with pytest.raises(CrossAssetInputUnavailable, match="cell_numeric"):
        study.criterion(invalid)


def test_bound_deadline_stops_pure_prep_and_replay(plan, monkeypatch):
    source = rows(plan)
    actions = study.prepare_actions(source, plan, "synthetic-v1")
    marks = study.prepare_marks(source, plan, "synthetic-v1")
    monkeypatch.setattr(study, "monotonic", lambda: 60.0)
    for call in (lambda: study.prepare_actions(source, plan, "synthetic-v1", deadline=60.0),
                 lambda: study.evaluate(marks, actions, deadline=60.0)):
        with pytest.raises(CrossAssetInputUnavailable, match="compute_stop"):
            call()


def test_source_is_pure_no_loader_fileio_model_broker_or_dispatch():
    tree = ast.parse(Path(study.__file__).read_text(encoding="utf-8"))
    banned = {"os", "pathlib", "torch", "sklearn", "requests", "socket", "subprocess"}
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not any(name.split(".")[0] in banned for name in imports)
    assert not any("tiingo" in name or "execution" in name for name in imports)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "print", "eval", "exec"} for n in ast.walk(tree))

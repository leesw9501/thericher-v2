"""Public synthetic fixtures; real pure price, quote and whole-share APIs."""

from __future__ import annotations

import builtins
import socket
import urllib.request
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from test_kis_lagged_rate_whole_share_policy_development import rows_for, session, weekdays
from thericher_v2.research import kis_whole_share_hold_rebalance as study
from thericher_v2.research import whole_share_portfolio_nav as whole
from thericher_v2.research.cross_asset_etf_input import CrossAssetInputUnavailable

D = Decimal
VINTAGE = "synthetic-raw-OC"


@pytest.fixture(scope="module")
def plan():
    past = weekdays(date(2016, 2, 2), 300) + [date(2020, 12, 30), date(2020, 12, 31)]
    dev = weekdays(date(2021, 1, 4), 42) + [date(2023, 12, 29)]
    dev += weekdays(date(2024, 1, 2), 42) + [date(2026, 9, 30)]
    return study.build_plan(tuple(map(session, past + dev)))


def boundary_rows(plan):
    first = plan.train_indices[0]
    return {
        s: tuple(
            replace(
                r,
                open=D("3333.33") if i < first + 21 else D(3330),
                close=D("3333.33") if i < first + 21 else D(3340),
            )
            for i, r in enumerate(c)
        )
        for s, c in rows_for(plan.sessions).items()
    }


@pytest.fixture(scope="module")
def training(plan):
    return study.prepare_training(boundary_rows(plan), plan=plan, vintage_ref=VINTAGE)


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("pure preparation must not access IO/network/provider or models")

    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)


def entry_for(plan, rows=None, index=None):
    return study.prepare_price_entry(
        rows_for(plan.sessions) if rows is None else rows,
        plan=plan,
        entry_index=plan.train_indices[0] if index is None else index,
        vintage_ref=VINTAGE,
    )


def decision_for(entry, state=None):
    state = study.prior._initial(whole) if state is None else state
    return study.DecisionInput(entry, state, study.state_vector(state, entry))


def test_fixed_recipe_and_same_calendar_but_tail_hold(plan):
    config = study.configuration()
    assert config["name"] == "kis-whole-share-hold-rebalance-payoff-alignment-v1"
    assert (config["fits"], config["cells"], config["seconds"]) == (2, 30, 300)
    assert config["cpu_only"] and not config["gpu"] and not config["paper_input"]
    assert config["ridge"] == dict(alpha=1, solver="svd", fit_intercept=True, inputs=389, outputs=1)
    assert config["holdout"] == "none" and not config["optimality_replica"]
    assert "raw" in config["price_features"] and "no resets" in config["behaviour"]
    old = study.prior.build_plan(plan.sessions)
    assert (plan.train_indices, plan.dev_indices, plan.block_cut) == (
        old.train_indices,
        old.dev_indices,
        old.block_cut,
    )
    assert "tail_cash_days" not in plan.record() and plan.record()["tail_hold_days"] == 2
    record = study.plan_record(plan)
    assert record["paired_train_rows"] == 2 * len(plan.train_indices)
    assert record["train_marks"] == len(plan.train_indices) + 20
    assert record["disjoint_label_geometry"] == 2 and record["always_train_attempts"] == 3
    assert record["independent_sample_count"] == "not_claimed"


def test_raw_subcent_price_features_covariance_and_only_prior_quote_projection(plan):
    rows = {
        s: tuple(replace(r, close=D(100) + D(i % (j + 3)) / 1000) for i, r in enumerate(c))
        for j, (s, c) in enumerate(rows_for(plan.sessions).items())
    }
    entry = entry_for(plan, rows)
    with localcontext(study.CONTEXT):
        assert (
            entry.price.features[0][0] == rows["SPY"][190].close.ln() - rows["SPY"][189].close.ln()
        )
    assert any(entry.covariance3[i][i] > 0 for i in range(3))
    assert entry.prior_close3 == (D(100),) * 3
    assert "prior_close3=" not in repr(entry) and entry.safe_facts()["price_shape"] == (6, 63)
    annual = 252 * sum(
        entry.balanced3[i] * entry.covariance3[i][j] * entry.balanced3[j]
        for i in range(3)
        for j in range(3)
    )
    assert annual <= Fraction(1, 100)


def test_future_invalid_values_presence_and_identity_are_not_feature_masks(plan):
    rows = rows_for(plan.sessions, D("103.005"))
    expected = entry_for(plan, rows)
    used = {s.session_date for s in plan.sessions[:253]}
    changed = {
        s: tuple(
            r
            if r.session_date in used
            else SimpleNamespace(
                session_date=r.session_date, open="poison", close="poison", symbol="unknown"
            )
            for r in c
        )
        for s, c in rows.items()
    }
    assert entry_for(plan, changed) == expected
    assert (
        entry_for(plan, {s: tuple(r for r in c if r.session_date in used) for s, c in rows.items()})
        == expected
    )


@pytest.mark.parametrize("fault", ["gap", "duplicate", "vintage", "symbol", "scope"])
def test_required_past_faults_cannot_be_grafted_or_dropped(plan, fault):
    rows = {s: list(c) for s, c in rows_for(plan.sessions).items()}
    if fault == "gap":
        rows["TLT"].pop(0)
    elif fault == "duplicate":
        rows["TLT"].append(rows["TLT"][0])
    elif fault == "vintage":
        rows["TLT"][0] = replace(rows["TLT"][0], vintage_ref="other")
    elif fault == "symbol":
        rows["TLT"][0] = replace(rows["TLT"][0], symbol="SPY")
    else:
        rows["QQQ"] = rows.pop("TLT")
    with pytest.raises(CrossAssetInputUnavailable):
        entry_for(plan, rows)


def test_exact_state_vector_and_original_bank_no_reset(plan):
    entry = entry_for(plan)
    state = whole.WholeShareState(
        Fraction(9000), Fraction(3), (2, 0, 0), (Fraction(206), Fraction(0), Fraction(0))
    )
    vector = study.state_vector(state, entry)
    assert vector == (
        Fraction(2),
        Fraction(0),
        Fraction(0),
        Fraction(206, 10000),
        Fraction(0),
        Fraction(0),
        Fraction(9, 10),
        Fraction(3, 10000),
        *(Fraction(103, 10000),) * 3,
    )
    assert len(vector) == 11 and all(type(v) is Fraction for v in vector)
    with pytest.raises(CrossAssetInputUnavailable, match="original_bank"):
        study.state_vector(replace(state, basis_usd=Fraction(200000)), entry)
    with pytest.raises(CrossAssetInputUnavailable, match="state_feature_binding"):
        replace(decision_for(entry, state), state11=(Fraction(0),) * 11)


def test_causal_train_snapshots_first_failed_attempt_buyonce_never_retries(plan, training):
    assert len(training.rows) == 2 * len(plan.train_indices)
    for b in study.BEHAVIOURS:
        replay = training.behaviour_replays[b]
        assert replay[0].open_trade.reason == "analytical_cash_negative"
        assert replay[0].mark.state == study.prior._initial(whole)
        assert all(d.close_trade is None for d in replay)
    always, buy = (training.behaviour_replays[b] for b in study.BEHAVIOURS)
    assert always[21].open_trade.status == "executed" and always[21].mark.state.quantities3 == (
        1,
        1,
        1,
    )
    assert all(d.open_trade is None for d in buy[1:])
    first = plan.train_indices[0]
    for row in training.rows:
        replay = training.behaviour_replays[row.behaviour]
        expected = (
            study.prior._initial(whole)
            if row.entry_index == first
            else replay[row.entry_index - first - 1].mark.state
        )
        assert row.decision.state == expected
        assert row.decision.entry.price.decision_at == plan.sessions[row.entry_index - 1].close_at
        assert row.target.exit_at <= plan.sessions[plan.dev_indices[0] - 2].close_at
    assert training.ordering_changes > 0 and training.safe_facts()["structural_pass"]
    assert training.rows[0].target.delta == training.rows[1].target.delta == 0


def test_counterfactuals_use_same_prior_net_nav_no_liquidation_and_no_future_rebalances(
    plan, training
):
    rows = boundary_rows(plan)
    row = next(
        r
        for r in training.rows
        if r.entry_index == plan.train_indices[0] + 22 and r.behaviour == "always"
    )
    i, initial = row.entry_index, row.decision.state
    days = tuple(
        whole.WholeShareDay(s.session_date, (D(3330),) * 3, (D(3340),) * 3)
        for s in plan.sessions[i : i + 21]
    )
    origin = whole.mark_close(initial, row.decision.entry.prior_close3).net_nav
    for do_trade, expected in (
        (False, row.target.hold_utility),
        (True, row.target.rebalance_utility),
    ):
        result = whole.replay(
            days,
            {days[0].date: row.decision.entry.balanced3} if do_trade else {},
            D(10),
            initial_state=initial,
            liquidate_last_close=False,
        )
        assert result.final_state.quantities3 == (1, 1, 1)
        assert all(d.open_trade is None and d.close_trade is None for d in result.daily[1:])
        assert (
            D(study.prior._metrics(tuple(d.mark.net_nav for d in result.daily), origin)["utility"])
            == expected
        )
    actual = study.counterfactual_target(
        rows, plan=plan, entry_index=i, vintage_ref=VINTAGE, decision=row.decision
    )
    assert actual == row.target and row.target.preferred == study.HOLD


def test_infeasible_rows_preserved_and_magnitude_only_does_not_pass_structural_stop(plan, training):
    assert training.rows[0].target.rebalance_reason == "analytical_cash_negative"
    assert training.rows[0].target.hold_utility == training.rows[0].target.rebalance_utility
    changed = []
    for i, row in enumerate(training.rows):
        delta = D(1) if i % 2 == 0 else D(2)
        changed.append(
            replace(
                row,
                target=replace(row.target, hold_utility=D(0), rebalance_utility=delta, delta=delta),
            )
        )
    same_order = replace(training, rows=tuple(changed))
    assert same_order.ordering_changes == 0 and not same_order.safe_facts()["structural_pass"]
    flat = study.prepare_training(rows_for(plan.sessions), plan=plan, vintage_ref=VINTAGE)
    assert flat.ordering_changes == 0


def test_train_only_future_dev_poison_does_not_change_states_labels_or_scalers(plan, training):
    cutoff = plan.sessions[plan.dev_indices[0] - 2].session_date
    rows = {
        s: tuple(
            r
            if r.session_date <= cutoff
            else SimpleNamespace(session_date=r.session_date, open="invalid", close="invalid")
            for r in c
        )
        for s, c in boundary_rows(plan).items()
    }
    rebuilt = study.prepare_training(rows, plan=plan, vintage_ref=VINTAGE)
    assert rebuilt.rows == training.rows and rebuilt.behaviour_replays == training.behaviour_replays
    left, right = study.fit_scaler(training), study.fit_scaler(rebuilt)
    for name in ("price_mean", "price_divisor", "state_mean", "state_divisor"):
        np.testing.assert_array_equal(getattr(left, name), getattr(right, name))


def test_paired_shared_train_scalers_389_and_zero_price_state_slots(training):
    scaler = study.fit_scaler(training)
    price = scaler.training_inputs(training, augmented=False)
    state = scaler.training_inputs(training, augmented=True)
    assert price.shape == state.shape == (len(training.rows), 389)
    np.testing.assert_array_equal(price[:, :378], state[:, :378])
    assert not price[:, 378:].any() and state[:, 378:].any()
    for array in (price, state, scaler.price_mean, scaler.state_mean):
        assert not array.flags.writeable
    np.testing.assert_array_equal(
        scaler.state_mean,
        np.array([r.decision.state11 for r in training.rows], dtype=float).mean(axis=0),
    )
    with pytest.raises(FrozenInstanceError):
        training.rows[0].decision.state = training.rows[1].decision.state


def test_required_forward_gap_no_deletion_or_dev_target(plan, training):
    row = training.rows[0]
    missing = plan.sessions[row.entry_index + 10].session_date
    rows = {
        s: tuple(r for r in c if r.session_date != missing) for s, c in boundary_rows(plan).items()
    }
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_missing"):
        study.counterfactual_target(
            rows, plan=plan, entry_index=row.entry_index, vintage_ref=VINTAGE, decision=row.decision
        )
    with pytest.raises(CrossAssetInputUnavailable, match="target_not_train"):
        study.counterfactual_target(
            rows_for(plan.sessions),
            plan=plan,
            entry_index=plan.group_indices[0],
            vintage_ref=VINTAGE,
            decision=row.decision,
        )


@pytest.mark.parametrize(
    "delta,expected", [(D(0), "hold"), (D(-1), "hold"), (D("1e-40"), "rebalance")]
)
def test_ties_hold_no_adaptive_threshold(delta, expected):
    assert study.preferred_action(delta) == expected


@pytest.mark.parametrize("bad", [None, 1.0, D("NaN"), D("Infinity")])
def test_bad_prediction_fails_before_quote_selection(plan, monkeypatch, bad):
    def deny_quotes(*args):
        pytest.fail("invalid predictor output must fail before execution quotes")

    monkeypatch.setattr(study, "_quotes", deny_quotes)
    with pytest.raises(CrossAssetInputUnavailable, match="prediction_invalid"):
        study.evaluate(
            rows_for(plan.sessions), plan=plan, vintage_ref=VINTAGE, predictor=lambda *_: bad
        )


def test_real_sequential_prediction_and_seal_before_current_open_and_close(plan, monkeypatch):
    source, advance, quote = study.prepare_price_entry, study._advance, study._quotes
    events, sealed = [], []

    def predicted(policy, decision):
        events.append(("predict", policy, decision.entry.price.entry_at.date()))
        return D(1)

    def on_seal(record):
        events.append(("seal", record.policy, record.decision.entry.price.entry_at.date()))
        sealed.append(record)

    def selected_quotes(book, day, kind, vintage):
        assert sealed
        if day in {g[0] for g in plan.groups}:
            assert sealed[-1].decision.entry.price.entry_at.date() == day
        events.append((kind, sealed[-1].policy, day))
        return quote(book, day, kind, vintage)

    def advance_checked(book, index, actual_plan, vintage, state, weights=None, **kwargs):
        if index in plan.group_indices:
            assert events[-1][0] == "seal"
            assert sealed[-1].decision.state == state
        return advance(book, index, actual_plan, vintage, state, weights, **kwargs)

    monkeypatch.setattr(study, "_quotes", selected_quotes)
    monkeypatch.setattr(study, "_advance", advance_checked)
    result = study.evaluate(
        rows_for(plan.sessions),
        plan=plan,
        vintage_ref=VINTAGE,
        predictor=predicted,
        on_seal=on_seal,
    )
    assert study.prepare_price_entry is source
    assert len(result.cells) == 30 and len(result.replays) == 15
    assert len(sealed) == 15 * len(plan.groups)
    for replay in result.replays:
        assert replay.daily[-1].close_trade is not None
        assert all(d.close_trade is None for d in replay.daily[:-1])
        assert all(d.open_trade is None for d in replay.daily[84:])
        assert (
            replay.final_state.basis_usd == study.BASIS
            and replay.final_state.allocated_usd == study.BANK
        )
    assert not any(kind == "open" and day in set(plan.dates[84:]) for kind, _, day in events)


def test_continuous_views_tail_hold_final_liquidation_and_exact_notional_fees(plan):
    result = study.evaluate(
        rows_for(plan.sessions), plan=plan, vintage_ref=VINTAGE, predictor=lambda *_: D(1)
    )
    replay = next(r for r in result.replays if r.policy == "state" and r.cost_bps == D(10))
    assert replay.daily[83].mark.state.quantities3 != (0, 0, 0)
    assert replay.daily[84].mark.state.quantities3 == replay.daily[83].mark.state.quantities3
    assert replay.daily[85].mark.state.quantities3 == (0, 0, 0)
    assert replay.daily[43].open_trade is None
    fees = sum((d.fees for d in replay.daily), Fraction(0))
    notional = sum((d.traded_notional for d in replay.daily), Fraction(0))
    assert fees == notional * Fraction(10, 10000) == replay.final_state.fees_paid
    navs = tuple(d.mark.net_nav for d in replay.daily)
    later = next(
        c for c in result.cells if (c["policy"], c["cost_bps"], c["view"]) == ("state", "10", 1)
    )
    assert later["metrics"] == study.prior._metrics(navs[43:], navs[42])
    assert study.criterion(result.cells) == {"state": "rejected"}


def test_buyonce_dev_first_failure_not_retried(plan):
    result = study.evaluate(
        rows_for(plan.sessions, D("3333.33")),
        plan=plan,
        vintage_ref=VINTAGE,
        predictor=lambda *_: D(0),
    )
    for replay in (r for r in result.replays if r.policy == "buyonce"):
        assert replay.daily[0].open_trade.reason == "analytical_cash_negative"
        assert all(d.open_trade is None for d in replay.daily[1:])
        assert all(d.mark.state.quantities3 == (0, 0, 0) for d in replay.daily)


def test_future_perturbation_cannot_change_dev_decisions_or_execution_prefix(plan):
    rows = rows_for(plan.sessions)
    mutation = plan.dev_indices[30]
    changed = {
        s: tuple(
            replace(r, open=D(150), close=D(151)) if i >= mutation else r for i, r in enumerate(c)
        )
        for s, c in rows.items()
    }
    left = study.evaluate(rows, plan=plan, vintage_ref=VINTAGE, predictor=lambda *_: D(1))
    right = study.evaluate(changed, plan=plan, vintage_ref=VINTAGE, predictor=lambda *_: D(1))
    for a, b in zip(left.replays, right.replays, strict=True):
        assert a.daily[:30] == b.daily[:30]
        assert a.decisions[:2] == b.decisions[:2]


def test_seal_tampering_is_rejected_before_execution(plan, monkeypatch):
    def tamper(record):
        object.__setattr__(record, "cost_bps", D(5))

    def deny_quotes(*args):
        pytest.fail("changed seal must not execute")

    monkeypatch.setattr(study, "_quotes", deny_quotes)
    with pytest.raises(CrossAssetInputUnavailable, match="seal_changed"):
        study.evaluate(
            rows_for(plan.sessions),
            plan=plan,
            vintage_ref=VINTAGE,
            predictor=lambda *_: D(1),
            on_seal=tamper,
        )


def deferred_source(rows, fetch):
    return study.TypedRowSource(
        {s: tuple(r.session_date for r in c) for s, c in rows.items()}, fetch
    )


def test_lazy_typed_fetch_only_requested_numeric_fields_and_current_open_after_seal(plan):
    rows = rows_for(plan.sessions)
    by_date = {s: {r.session_date: r for r in c} for s, c in rows.items()}
    sealed, requests = [], []

    def fetch(required):
        requests.append(dict(required))
        if len(required) == 1:
            day, fields = next(iter(required.items()))
            if day in set(plan.dates):
                assert sealed
                if "open" in fields:
                    assert sealed[-1].decision.entry.price.entry_at.date() == day
        return {
            s: tuple(
                replace(
                    by_date[s][d],
                    open=by_date[s][d].open if "open" in fields else None,
                    close=by_date[s][d].close if "close" in fields else None,
                )
                for d, fields in required.items()
            )
            for s in study.SYMBOLS
        }

    lazy = deferred_source(rows, fetch)
    result = study.evaluate(
        lazy, plan=plan, vintage_ref=VINTAGE, predictor=lambda *_: D(1), on_seal=sealed.append
    )
    ordinary = study.evaluate(rows, plan=plan, vintage_ref=VINTAGE, predictor=lambda *_: D(1))
    assert result.cells == ordinary.cells and result.replays == ordinary.replays
    assert all(len(r) == 1 or len(r) in (64, 253) for r in requests)
    assert requests[0] == {
        s.session_date: ("close",)
        for s in plan.sessions[plan.dev_indices[0] - 253 : plan.dev_indices[0]]
    }


def test_lazy_source_cannot_return_unrequested_numeric_fields_or_hide_required_duplicate(plan):
    rows = rows_for(plan.sessions)

    def overfetch(required):
        return {s: tuple(r for r in c if r.session_date in required) for s, c in rows.items()}

    with pytest.raises(CrossAssetInputUnavailable, match="fetch_extra_numeric_field"):
        entry_for(plan, deferred_source(rows, overfetch))
    dates = {s: tuple(r.session_date for r in c) for s, c in rows.items()}
    dates["TLT"] += (plan.sessions[0].session_date,)
    with pytest.raises(CrossAssetInputUnavailable, match="required_session_duplicate"):
        entry_for(plan, study.TypedRowSource(dates, overfetch))


def test_lazy_source_future_presence_does_not_mask_past_and_training_stays_train(plan, training):
    rows = boundary_rows(plan)
    by_date = {s: {r.session_date: r for r in c} for s, c in rows.items()}
    cutoff = plan.sessions[plan.dev_indices[0] - 2].session_date

    def fetch(required):
        assert all(d <= cutoff for d in required)
        return {
            s: tuple(
                replace(
                    by_date[s][d],
                    open=by_date[s][d].open if "open" in fields else None,
                    close=by_date[s][d].close if "close" in fields else None,
                )
                for d, fields in required.items()
            )
            for s in study.SYMBOLS
        }

    dates = {
        s: tuple(d for d in c if d <= cutoff)
        for s, c in {s: tuple(r.session_date for r in c) for s, c in rows.items()}.items()
    }
    result = study.prepare_training(
        study.TypedRowSource(dates, fetch), plan=plan, vintage_ref=VINTAGE
    )
    assert result.rows == training.rows


def cells():
    return [
        dict(
            policy=p,
            cost_bps=str(c),
            view=v,
            metrics=dict(growth=".1", utility="1" if p == "state" else "0"),
        )
        for p in study.POLICIES
        for c in study.COSTS
        for v in (0, 1)
    ]


@pytest.mark.parametrize("failure", ["growth", "price", "always", "buyonce", "cash", "tolerance"])
def test_original_two_view_kill_kept(failure):
    records = cells()
    assert study.criterion(records) == {"state": "survived_development"}
    target = next(
        c for c in records if (c["policy"], c["cost_bps"], c["view"]) == ("state", "10", 1)
    )
    if failure == "growth":
        target["metrics"]["growth"] = "0"
    elif failure == "tolerance":
        target["metrics"]["utility"] = "1e-10"
    else:
        next(c for c in records if (c["policy"], c["cost_bps"], c["view"]) == (failure, "10", 1))[
            "metrics"
        ]["utility"] = "1"
    with localcontext() as context:
        context.prec = 2
        assert study.criterion(records) == {"state": "rejected"}


def test_duplicate_or_missing_cells_do_not_pass():
    records = cells()
    with pytest.raises(CrossAssetInputUnavailable, match="cell_matrix"):
        study.criterion(records[:-1] + [records[0]])

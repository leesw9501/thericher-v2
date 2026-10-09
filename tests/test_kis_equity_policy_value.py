import builtins
import socket
import subprocess
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_equity_policy_value as k
from thericher_v2.research import kis_equity_rule_fusion as fusion
from thericher_v2.research import kis_pooled_equity_components as core


@pytest.fixture
def plan():
    sessions = tuple(date(2020, 1, 1) + timedelta(days=i) for i in range(800))
    return core.ComponentPlan(
        sessions,
        tuple(f"opaque:{i:03}" for i in range(12)),
        tuple(datetime.combine(day, time(14, 30), UTC) for day in sessions),
        tuple(datetime.combine(day, time(21), UTC) for day in sessions),
    )


def state(plan, index=100, count=12, tied=False):
    return core.EligibilitySnapshot(
        index,
        plan.sessions[index - 1],
        plan.sessions[index],
        tuple(
            core.FeatureRow(
                key,
                (
                    tuple((i + j) / 1000 for j in range(20)),
                    tuple((i - j) / 1000 for j in range(20)),
                ),
                (float(i // 2), float(-i), 0.0),
                0.0 if tied else float(i // 2),
            )
            for i, key in enumerate(plan.keys[:count])
        ),
        plan.keys[count:],
        plan.close_clocks[index - 1],
        plan.open_clocks[index],
        plan.close_clocks[index],
    )


@pytest.fixture
def past(plan):
    indices = {day: i for i, day in enumerate(plan.sessions)}
    assets = {key: i for i, key in enumerate(plan.keys)}

    def source(key, day):
        opening = Decimal(100 + assets[key]) + Decimal(indices[day]) / 10
        closing = opening * (1 + Decimal(assets[key] + 1) / 1000)
        return Bar(
            symbol=key,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=datetime.combine(day, time(), UTC),
            open=opening,
            high=closing * Decimal("1.01"),
            low=opening * Decimal("0.99"),
            close=closing,
            volume=Decimal(1000),
        )

    return source


def forbidden(*_args, **_kwargs):
    pytest.fail("unexpected I/O, future target or evaluator access")


def training():
    entries = (61, 62, 63, 64, 65, 66)
    x = np.arange(len(entries) * 40, dtype=float).reshape(len(entries), 20, 2) / 1000
    y = np.arange(len(entries) * 5, dtype=float).reshape(len(entries), 5) / 100
    return x, y, entries


def fit(x, y, entries, cutoff=427):
    return k.fit_ridge(x, y, entry_indices=entries, fit_target_cutoff=cutoff)


def test_frozen_contract_and_folds(plan):
    assert k.EXPERTS == ("component", "momentum5", "momentum20", "momentum60", "uniform_rank_blend")
    assert k.ACTIONS == (*k.EXPERTS, "cash")
    assert k.CHANNELS == ("log_overnight", "log_intraday")
    assert k.FIT_CUTOFFS == (427, 609, 799)
    assert k.PRIMARY_BPS == 10 and k.ROUND_TRIP_BPS == (5, 10, 20)
    assert k.RIDGE_ALPHA == 1
    assert k.FINAL_FIT_ENTRIES == range(61, 800)
    assert k.CURRENT_ENTRIES == tuple(range(761, 800))
    assert [(f.fit_target_cutoff, f.score_entries) for f in k.OOF_FOLDS] == [
        (427, range(429, 611)),
        (609, range(611, 800)),
    ]
    for fold in k.OOF_FOLDS:
        fusion.validate_fold(plan, fold)


def test_snapshot_exact_prior61_and_same_eligible_cohort_context(plan, past, monkeypatch):
    monkeypatch.setattr(core, "target_labels", forbidden)
    monkeypatch.setattr(core, "evaluate_day", forbidden)
    calls, bars = [], {}
    index, missing = 100, plan.keys[0]

    def source(key, day):
        assert day in plan.sessions[index - 61 : index]
        calls.append((key, day))
        bar = past(key, day)
        bars[key, day] = bar
        return None if key == missing and day == plan.sessions[index - 61] else bar

    inputs = k.snapshot(plan, index, source)
    assert calls == [(key, day) for key in plan.keys for day in plan.sessions[index - 61 : index]]
    assert inputs.eligible_keys == plan.keys[1:]
    assert inputs.unavailable_keys == (missing,)
    for step, day in enumerate(plan.sessions[index - 20 : index]):
        previous = plan.sessions[index - 21 + step]
        expected_on = np.mean(
            [
                np.log(float(bars[key, day].open)) - np.log(float(bars[key, previous].close))
                for key in inputs.eligible_keys
            ]
        )
        expected_id = np.mean(
            [
                np.log(float(bars[key, day].close)) - np.log(float(bars[key, day].open))
                for key in inputs.eligible_keys
            ]
        )
        assert inputs.context[step] == pytest.approx((expected_on, expected_id))
    assert isinstance(bars[plan.keys[1], plan.sessions[99]].close, Decimal)


def test_context_has_chronological_steps_channel_order_and_no_key_weighting(plan):
    inputs = k.ParticipationInputs(state(plan, count=10))
    np.testing.assert_allclose(
        inputs.context, tuple(((4.5 + j) / 1000, (4.5 - j) / 1000) for j in range(20))
    )
    assert len(inputs.context) == 20 and all(len(row) == 2 for row in inputs.context)
    assert tuple(inputs.seals) == k.EXPERTS
    assert inputs.cash_seal.allocation == "cash"
    assert "tcn" not in inputs.seals and "equal_weight" not in inputs.seals
    assert inputs.seals["uniform_rank_blend"] == fusion.uniform_rank_blend(
        fusion.FusionInputs(inputs.snapshot)
    )
    with pytest.raises(FrozenInstanceError):
        inputs.context = ()
    with pytest.raises(TypeError):
        inputs.seals["component"] = inputs.cash_seal


def test_joint_labels_all_five_sealed_before_first_target_and_read_union_once(plan, monkeypatch):
    inputs = k.ParticipationInputs(state(plan))
    original, sealed, calls = core.seal, [], []

    def spy(*args, **kwargs):
        result = original(*args, **kwargs)
        sealed.append(result)
        return result

    monkeypatch.setattr(core, "seal", spy)
    fresh = k.ParticipationInputs(inputs.snapshot)
    selected = tuple(sorted({key for name in k.EXPERTS for key in fresh.seals[name].selected_keys}))

    def target(key, day):
        assert all(fresh.seals[name] in sealed for name in k.EXPERTS)
        assert day == fresh.snapshot.entry_session and key in selected
        calls.append(key)
        return core.OpenClose(100, 101 + int(key[-3:]) / 10)

    labels = k.joint_labels(fresh, target)
    assert calls == list(selected)
    assert labels.complete and len(labels.values) == 5
    for i, name in enumerate(k.EXPERTS):
        expected = (
            np.mean([0.01 + int(key[-3:]) / 1000 for key in fresh.seals[name].selected_keys])
            - 0.001
        )
        assert labels.values[i] == pytest.approx(expected)
    assert labels.available_at == fresh.snapshot.target_close_at
    assert labels.missing_selected == ()
    assert fresh == inputs


@pytest.mark.parametrize("bad", [None, core.OpenClose(0, 1), core.OpenClose(100, float("nan"))])
def test_any_selected_missing_or_invalid_invalidates_whole_joint_date(plan, bad):
    inputs = k.ParticipationInputs(state(plan))
    missing = inputs.seals["component"].selected_keys[0]
    labels = k.joint_labels(
        inputs, lambda key, day: bad if key == missing else core.OpenClose(100, 101)
    )
    assert not labels.complete and labels.values is None
    assert labels.missing_selected == (missing,)
    assert inputs.eligible_keys == plan.keys
    assert labels.inputs is inputs and len(labels.replays) == 5


def test_missing_peer_selected_only_by_other_expert_still_rejects_joint_date(plan):
    inputs = k.ParticipationInputs(state(plan))
    missing = next(
        key
        for key in inputs.seals["momentum20"].selected_keys
        if key not in inputs.seals["component"].selected_keys
    )
    labels = k.joint_labels(
        inputs, lambda key, _: None if key == missing else core.OpenClose(100, 101)
    )
    assert labels.replays[0].complete
    assert labels.values is None and labels.missing_selected == (missing,)


def test_unselected_peers_are_not_read_and_cannot_censor_joint_labels(plan):
    base = state(plan, tied=True)
    rows = tuple(replace(row, momentum=(0, 0, 0)) for row in base.rows)
    inputs = k.ParticipationInputs(replace(base, rows=rows))
    assert all(inputs.seals[name].selected_keys == plan.keys[:10] for name in k.EXPERTS)

    def target(key, _):
        assert key not in plan.keys[10:]
        return core.OpenClose(100, 102)

    labels = k.joint_labels(inputs, target)
    assert labels.values == pytest.approx((0.019,) * 5)
    assert inputs.eligible_keys == plan.keys


@pytest.mark.parametrize("count", [0, 1, 9])
def test_under10_all_experts_actions_flat_no_targets_and_no_global_block(plan, count):
    inputs = k.ParticipationInputs(state(plan, count=count))
    assert (inputs.context is None) == (count == 0)
    assert all(not seal.selected_keys for seal in inputs.seals.values())
    assert k.joint_labels(inputs, forbidden).values == (0.0,) * 5
    for mode in k.MODES:
        action = k.ActionSeal(inputs, (100.0,) * 5, mode)
        assert action.action == "cash"
        assert k.replay_action(action, forbidden).net_return == 0
    eligible = k.ParticipationInputs(state(plan, count=10))
    assert k.ActionSeal(eligible, (1.0,) * 5, "joint").action == "component"


@pytest.mark.parametrize(
    "values,joint,participation",
    [
        ((0, 0, 0, 0, 0), "cash", "cash"),
        ((-1, -2, -3, -4, -5), "cash", "cash"),
        ((1, 1, 1, 1, 1), "component", "uniform_rank_blend"),
        ((-1, 2, 2, -1, 0), "momentum20", "cash"),
        ((0, 0, 0, 0, 0.1), "uniform_rank_blend", "uniform_rank_blend"),
        ((0.2, 0, 0, 0, -0.1), "component", "cash"),
    ],
)
def test_positive_only_cash_zero_and_lexical_expert_ties(plan, values, joint, participation):
    inputs = k.ParticipationInputs(state(plan))
    assert k.ActionSeal(inputs, values, "joint").action == joint
    assert k.ActionSeal(inputs, values, "participation_only").action == participation


def test_all39_both_action_paths_frozen_before_any_current_payoff(plan):
    inputs = tuple(
        k.ParticipationInputs(state(plan, index=i, count=0 if i == 770 else 12))
        for i in k.CURRENT_ENTRIES
    )
    predicted = np.full((39, 5), 0.01)
    actions = k.seal_actions(inputs, predicted)
    predicted[:] = -1
    assert tuple(actions) == k.MODES
    assert all(len(path) == 39 for path in actions.values())
    assert actions["joint"][9].action == "cash"

    def target(key, day):
        assert all(
            tuple(a.inputs.snapshot.entry_index for a in path) == k.CURRENT_ENTRIES
            for path in actions.values()
        )
        return None if day == plan.sessions[775] else core.OpenClose(100, 101)

    for path in actions.values():
        days = tuple(k.replay_action(action, target) for action in path)
        assert len(days) == 39
        metrics = core.portfolio_metrics(days, expected_entries=k.CURRENT_ENTRIES)
        assert metrics.session_count == 39 and metrics.missing_entries == (775,)
        assert metrics.growth is None
    with pytest.raises(TypeError):
        actions["other"] = ()


@pytest.mark.parametrize("fault", ["missing", "duplicate", "order", "scores"])
def test_current_batch_rejects_dropped_dates_or_misaligned_predictions(plan, fault):
    inputs = [k.ParticipationInputs(state(plan, index=i)) for i in k.CURRENT_ENTRIES]
    scores = np.zeros((39, 5))
    if fault == "missing":
        inputs.pop()
    elif fault == "duplicate":
        inputs[-1] = inputs[0]
    elif fault == "order":
        inputs.reverse()
    else:
        scores = scores[:, :4]
    with pytest.raises(ValueError):
        k.seal_actions(inputs, scores)


def test_frozen_action_replay_costs_are_roundtrip_not_each_side_and_no_rethreshold(plan):
    inputs = k.ParticipationInputs(state(plan))
    action = k.ActionSeal(inputs, (0.0001, -1, -1, -1, -1), "joint")
    original = replace(action)
    for cost in k.ROUND_TRIP_BPS:
        replay = k.replay_action(action, lambda *_: core.OpenClose(100, 101), round_trip_bps=cost)
        assert replay.net_return == pytest.approx(0.01 - cost / 10000)
        assert replay.entry_turnover == replay.exit_turnover == 1
        assert action == original and action.action == "component"
    with pytest.raises(ValueError):
        k.replay_action(action, forbidden, round_trip_bps=30)


def test_selected_payoff_missing_stays_unavailable_not_cash_or_replacement(plan):
    inputs = k.ParticipationInputs(state(plan))
    action = k.ActionSeal(inputs, (1, 0, 0, 0, 0), "joint")
    selected = action.seal.selected_keys
    day = k.replay_action(
        action, lambda key, _: None if key == selected[0] else core.OpenClose(100, 101)
    )
    assert day.net_return is None and not day.complete
    assert day.reason == "selected_target_missing" and day.missing_selected == (selected[0],)
    assert action.action == "component" and action.seal.selected_keys == selected


def test_prefix_scaler_shared_across20_steps_and_equal_date_weights():
    x, _, entries = training()
    scaler = k.prefix_scaler(x, entry_indices=entries, fit_target_cutoff=427)
    assert scaler.mean == pytest.approx(x.mean(axis=(0, 1)))
    assert scaler.scale == pytest.approx(x.std(axis=(0, 1)))
    assert scaler.training_date_count == 6 and scaler.entry_indices == entries
    np.testing.assert_allclose(scaler.transform(x), (x - scaler.mean) / scaler.scale)
    assert not np.allclose(x.mean(axis=0)[0], scaler.mean)


@pytest.mark.parametrize("channel", [0, 1])
@pytest.mark.parametrize("constant", [0.1, -0.0017, 7.1])
def test_canonical_flat_channel_formula_exact_constants_and_shuffled_dates(channel, constant):
    x, _, entries = training()
    x[:, :, channel] = constant
    values = x.reshape(-1, 2)
    mean = values.mean(axis=0)
    mean = np.where(np.all(values == values[0], axis=0), values[0], mean)
    scale = np.sqrt(((values - mean) ** 2).mean(axis=0))
    scale = np.where(scale == 0, 1.0, scale)
    scaler = k.prefix_scaler(x, entry_indices=entries, fit_target_cutoff=427)
    assert scaler.mean == tuple(mean) and scaler.scale == tuple(scale)
    assert scaler.mean[channel] == constant and scaler.scale[channel] == 1.0
    assert np.array_equal(scaler.transform(x)[:, :, channel], np.zeros((6, 20)))
    order = [5, 1, 3, 0, 4, 2]
    shuffled = k.prefix_scaler(
        x[order], entry_indices=tuple(entries[i] for i in order), fit_target_cutoff=427
    )
    assert shuffled == scaler


def test_both_nonbinary_constant_channels_preserve_exact_means():
    x = np.tile([0.1, -0.0017], (6, 20, 1))
    scaler = k.prefix_scaler(x, entry_indices=(61, 62, 63, 64, 65, 66), fit_target_cutoff=427)
    assert scaler.mean == (0.1, -0.0017) and scaler.scale == (1.0, 1.0)
    assert np.array_equal(scaler.transform(x), np.zeros_like(x))


def test_multioutput_ridge_is_one_lstsq_and_matches_independent_normal_equations(monkeypatch):
    x, y, entries = training()
    original, calls = np.linalg.lstsq, []

    def spy(a, b, **kwargs):
        calls.append((a.shape, b.shape))
        return original(a, b, **kwargs)

    monkeypatch.setattr(np.linalg, "lstsq", spy)
    model = fit(x, y, entries)
    assert calls == [((6 + 41, 41), (6 + 41, 5))]
    z = ((x - x.mean(axis=(0, 1))) / x.std(axis=(0, 1))).reshape(6, 40)
    design = np.column_stack((np.ones(6), z))
    expected = np.linalg.solve(design.T @ design + np.diag([0, *([1] * 40)]), design.T @ y)
    np.testing.assert_allclose(model.coefficients, expected[1:], atol=1e-12)
    np.testing.assert_allclose(model.intercept, expected[0], atol=1e-12)
    np.testing.assert_allclose(model.predict(x), design @ expected, atol=1e-12)
    assert model.fit_target_cutoff == 427 and model.training_date_count == 6
    assert model.training_row_count == model.training_date_count
    assert model.mean == model.scaler.mean and model.scale == model.scaler.scale
    assert len(model.coefficients) == 40 and len(model.intercept) == 5
    assert model.predict(x.reshape(6, 40)) == model.predict(x)
    assert model.predict(np.empty((0, 40))) == ()


@pytest.mark.parametrize("constant", [0.1, -0.0017, 7.1])
def test_zero_variance_scale_one_and_unpenalized_five_intercepts(constant):
    _, y, entries = training()
    x = np.full((6, 20, 2), constant)
    model = fit(x, y, entries)
    assert model.scaler.mean == (constant,) * 2
    assert model.scaler.scale == (1.0,) * 2
    np.testing.assert_allclose(model.coefficients, 0, atol=1e-14)
    assert model.intercept == pytest.approx(y.mean(axis=0))
    np.testing.assert_allclose(model.predict(x), np.tile(y.mean(axis=0), (6, 1)))
    assert model.predict([]) == ()


def test_single_date_and_empty_prediction_are_supported():
    x, y, entries = training()
    model = fit(x[:1], y[:1], entries[:1])
    np.testing.assert_allclose(model.predict(x[:1]), y[:1], atol=1e-14)
    assert model.predict(np.empty((0, 20, 2))) == ()


def test_prefix_stats_isolated_prediction_and_input_mutations_cannot_change_model():
    x, y, entries = training()
    old_x, old_y = x.copy(), y.copy()
    model = fit(x, y, entries)
    before = replace(model)
    model.predict(np.full((39, 20, 2), 1000.0))
    assert model == before
    x[:] = -100
    y[:] = 10
    assert model == fit(old_x, old_y, entries)
    with pytest.raises(FrozenInstanceError):
        model.scaler.mean = (0, 0)
    with pytest.raises(TypeError):
        model.coefficients[0][0] = 0
    with pytest.raises(ValueError, match="training_date_after_prefix_cutoff"):
        fit(np.vstack((old_x, old_x[:1])), np.vstack((old_y, old_y[:1])), (*entries, 428))


def test_fit_deterministic_row_order_no_input_modification():
    x, y, entries = training()
    original_x, original_y = x.copy(), y.copy()
    order = [5, 1, 3, 0, 4, 2]
    assert fit(x, y, entries) == fit(x[order], y[order], tuple(entries[i] for i in order))
    assert np.array_equal(x, original_x) and np.array_equal(y, original_y)


@pytest.mark.parametrize("fault", ["duplicate", "future", "early", "bool", "empty"])
def test_one_row_date_identity_and_prefix_rejections(fault):
    x, y, entries = training()
    if fault == "duplicate":
        entries = (*entries[:-1], entries[0])
    elif fault == "future":
        entries = (428, *entries[1:])
    elif fault == "early":
        entries = (60, *entries[1:])
    elif fault == "bool":
        entries = (True, *entries[1:])
    else:
        x, y, entries = [], [], ()
    with pytest.raises(ValueError):
        fit(x, y, entries)
    with pytest.raises(ValueError):
        k.prefix_scaler(x, entry_indices=entries, fit_target_cutoff=427)


@pytest.mark.parametrize("cutoff", [426, 610, 800, True, 427.0])
def test_only_frozen_fit_cutoffs(cutoff):
    x, y, entries = training()
    with pytest.raises(ValueError, match="fixed_prefix_cutoff_required"):
        fit(x, y, entries, cutoff)


@pytest.mark.parametrize("fault", ["flat", "steps", "channels", "rows", "labels", "labelrows"])
def test_fixed_geometry_rejections(fault):
    x, y, entries = training()
    if fault == "flat":
        x = x.reshape(6, 40)
    elif fault == "steps":
        x = x[:, :19]
    elif fault == "channels":
        x = x[:, :, :1]
    elif fault == "rows":
        x = x[:-1]
    elif fault == "labels":
        y = y[:, :4]
    else:
        y = y[:-1]
    with pytest.raises(ValueError):
        fit(x, y, entries)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), complex(1, 0), True, "1"])
@pytest.mark.parametrize("field", ["contexts", "labels", "predictions"])
def test_nonfinite_complex_bool_string_inputs_fail(plan, bad, field):
    x, y, entries = training()
    if field == "contexts":
        values = x.tolist()
        values[0][0][0] = bad
        with pytest.raises(ValueError):
            fit(values, y, entries)
    elif field == "labels":
        values = y.tolist()
        values[0][0] = bad
        with pytest.raises(ValueError):
            fit(x, values, entries)
    else:
        with pytest.raises(ValueError):
            k.ActionSeal(k.ParticipationInputs(state(plan)), (bad, 0, 0, 0, 0), "joint")


def test_model_scaler_and_label_binding_reject_forged_geometry(plan):
    x, y, entries = training()
    model = fit(x, y, entries)
    with pytest.raises(ValueError):
        replace(model.scaler, scale=(0, 1))
    with pytest.raises(ValueError):
        replace(model.scaler, mean=(1 + 0j, 1))
    with pytest.raises(ValueError):
        replace(model, intercept=(float("nan"),) * 5)
    with pytest.raises(ValueError):
        replace(model, coefficients=((0,) * 4,) * 40)
    with pytest.raises(ValueError):
        model.predict(np.zeros((1, 19, 2)))
    inputs = k.ParticipationInputs(state(plan))
    labels = k.joint_labels(inputs, lambda *_: core.OpenClose(100, 101))
    with pytest.raises(ValueError, match="five_primary_basket_labels_required"):
        replace(labels, inputs=k.ParticipationInputs(state(plan, index=101)))
    with pytest.raises(ValueError):
        k.ActionSeal(inputs, (0,) * 4, "joint")
    with pytest.raises(ValueError):
        k.ActionSeal(inputs, (0,) * 5, "tcn")


def test_numerical_failures_rejected(monkeypatch):
    x, y, entries = training()
    with pytest.raises(ValueError):
        fit(np.full_like(x, 1e308), y, entries)
    model = fit(x, y, entries)
    exploding = replace(model, coefficients=((1e308,) * 5,) * 40)
    with pytest.raises(ValueError, match="nonfinite_ridge_prediction"):
        exploding.predict(np.full((1, 20, 2), 1e200))

    def broken(*_args, **_kwargs):
        raise np.linalg.LinAlgError("synthetic")

    monkeypatch.setattr(np.linalg, "lstsq", broken)
    with pytest.raises(ValueError, match="ridge_numerical_failure"):
        fit(x, y, entries)


def test_pure_apis_do_no_file_network_subprocess_or_target_io(plan, monkeypatch):
    inputs = k.ParticipationInputs(state(plan))
    x, y, entries = training()
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(core, "target_labels", forbidden)
    monkeypatch.setattr(core, "evaluate_day", forbidden)
    model = fit(x, y, entries)
    predictions = model.predict([inputs.context])
    paths = k.seal_actions([inputs], predictions, expected_entries=(100,))
    for path in paths.values():
        cash = k.ActionSeal(inputs, (-1,) * 5, path[0].mode)
        assert k.replay_action(cash, forbidden).net_return == 0

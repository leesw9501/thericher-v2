from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import numpy as np
import pytest

from thericher_v2.contracts import Bar, Timeframe
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


def state(plan, index=100, count=12):
    return core.EligibilitySnapshot(
        index,
        plan.sessions[index - 1],
        plan.sessions[index],
        tuple(
            core.FeatureRow(
                key,
                (tuple(float(i + j) for j in range(20)), tuple(float(i - j) for j in range(20))),
                (float(i // 2), float(-i), 0.0),
                float(i // 2),
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


def forbidden(*_args):
    pytest.fail("unexpected target/evaluator access")


def training(width=4):
    keys = ((61, "a"), (61, "b"), (62, "a"), (63, "a"), (63, "b"), (63, "c"))
    x = np.arange(len(keys) * width, dtype=float).reshape(len(keys), width) / 10
    y = np.asarray([0.1, -0.2, 0.4, 0.3, -0.1, 0.2])
    return x, y, keys


def fit(x, y, keys, view="expert_rank", cutoff=63):
    return fusion.fit_ridge(x, y, row_keys=keys, fit_target_cutoff=cutoff, view=view)


def test_fixed_folds_have_prefix_gap_and_full_seen_final_fit(plan):
    first, second = fusion.OOF_FOLDS
    assert first.fit_target_cutoff == 427 and first.score_entries == range(429, 611)
    assert second.fit_target_cutoff == 609 and second.score_entries == range(611, 800)
    assert first.fit_entries == range(61, 428)
    assert second.fit_entries == range(61, 610)
    assert fusion.FINAL_FIT_ENTRIES == range(61, 800)
    assert core.TRAIN_ENTRIES == range(61, 520)
    for fold in fusion.OOF_FOLDS:
        fusion.validate_fold(plan, fold)
        assert (
            plan.close_clocks[fold.fit_target_cutoff]
            < plan.close_clocks[fold.score_entries.start - 1]
        )


@pytest.mark.parametrize(
    "fold", [core.PrefixFold(427, range(428, 611)), core.PrefixFold(610, range(611, 800))]
)
def test_no_arbitrary_fold_or_outcome_selected_cutoff(plan, fold):
    with pytest.raises(ValueError, match="fixed_fusion_prefix_fold_required"):
        fusion.validate_fold(plan, fold)


def test_exact_causal_geometry_preserves_opaque_keys_and_unavailable(plan, past, monkeypatch):
    monkeypatch.setattr(core, "target_labels", forbidden)
    monkeypatch.setattr(core, "evaluate_day", forbidden)
    calls = []
    index = 100
    missing = plan.keys[0]

    def source(key, day):
        assert day in plan.sessions[index - 61 : index]
        calls.append((key, day))
        return None if key == missing and day == plan.sessions[index - 61] else past(key, day)

    result = fusion.snapshot(plan, index, source)
    assert calls == [(key, day) for key in plan.keys for day in plan.sessions[index - 61 : index]]
    assert result.eligible_keys == plan.keys[1:]
    assert result.unavailable_keys == (missing,)
    assert result.component_flat == tuple(row.flattened for row in result.snapshot.rows)
    assert all(len(row) == 40 for row in result.component_flat)
    assert all(len(row) == 4 for row in result.expert_ranks)
    assert result.features("expert_rank") == result.expert_ranks
    assert result.features("component_flat") == result.component_flat
    assert result.snapshot.decision_at == plan.close_clocks[index - 1]


@pytest.mark.parametrize("count", [0, 1, 9, 10, 12])
def test_ranks_cover_entire_decision_cross_section_with_stable_ties(plan, count):
    result = fusion.FusionInputs(state(plan, count=count))
    n = len(result.eligible_keys)
    assert result.eligible_keys == plan.keys[:count]
    assert len(result.component_flat) == len(result.expert_ranks) == count
    if n > 1:
        tied = tuple(
            (2 * (i // 2) + (0.5 if 2 * (i // 2) + 1 < n else 0)) / (n - 1) - 0.5 for i in range(n)
        )
        assert tuple(row[0] for row in result.expert_ranks) == tied
        assert tuple(row[1] for row in result.expert_ranks) == tied
        assert tuple(row[2] for row in result.expert_ranks) == tuple(
            (n - 1 - i) / (n - 1) - 0.5 for i in range(n)
        )
        assert tuple(row[3] for row in result.expert_ranks) == (0.0,) * n
    elif n:
        assert result.expert_ranks == ((0.0, 0.0, 0.0, 0.0),)


def test_finite_decimal_midranks_do_not_collapse_close_scores_or_ties():
    tiny = Decimal("1.00000000000000000000000000000000001")
    assert fusion.normalized_midranks([1, tiny, 1, 0]) == (0.0, 0.5, 0.0, -0.5)
    assert fusion.normalized_midranks([2, 2, 2]) == (0.0, 0.0, 0.0)
    assert fusion.normalized_midranks([]) == ()
    assert fusion.normalized_midranks([2]) == (0.0,)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), complex(1, 0), True, "NaN"])
def test_rank_input_rejects_nonfinite_complex_or_boolean(value):
    with pytest.raises(ValueError):
        fusion.normalized_midranks([0, value])


def test_geometry_and_seals_are_deeply_immutable_and_keep_genuine_names(plan, monkeypatch):
    inputs = fusion.FusionInputs(state(plan))
    supplied = {name: [0.0] * 12 for name in fusion.LEARNED_POLICIES}
    monkeypatch.setattr(core, "evaluate_day", forbidden)
    policies = fusion.seal_predictions(inputs, supplied)
    assert tuple(policies) == (
        *fusion.EXPERTS,
        "equal_weight",
        "cash",
        "uniform_rank_blend",
        *fusion.LEARNED_POLICIES,
    )
    assert "tcn" not in policies and "ridge" not in policies
    for policy in policies.values():
        assert policy.snapshot is inputs.snapshot
        assert tuple(key for key, _ in policy.scores) == inputs.eligible_keys
    supplied["contextual_gate"][0] = 100
    assert policies["contextual_gate"].scores[0][1] == 0
    with pytest.raises(TypeError):
        policies["tcn"] = policies["contextual_gate"]
    with pytest.raises(FrozenInstanceError):
        inputs.expert_ranks = ()
    with pytest.raises(TypeError):
        inputs.component_flat[0][0] = 99


@pytest.mark.parametrize("name", ["tcn", "ridge", "component", "unknown"])
def test_no_aliasing_or_overwriting_fixed_experts(plan, name):
    with pytest.raises(ValueError, match="unknown_fusion_policy_name"):
        fusion.seal_predictions(fusion.FusionInputs(state(plan)), {name: [0.0] * 12})


@pytest.mark.parametrize("fault", ["missing", "extra", "nan", "complex"])
def test_learned_scores_must_cover_all_eligible_peers(plan, fault):
    inputs = fusion.FusionInputs(state(plan))
    scores = dict.fromkeys(inputs.eligible_keys, 0.0)
    if fault == "missing":
        del scores[inputs.eligible_keys[-1]]
    elif fault == "extra":
        scores["foreign"] = 0
    else:
        scores[inputs.eligible_keys[0]] = float("nan") if fault == "nan" else 1 + 0j
    with pytest.raises(ValueError):
        fusion.seal_predictions(inputs, {"contextual_gate": scores})


def test_uniform_blend_is_mean_of_four_rank_features_sealed_before_targets(plan):
    inputs = fusion.FusionInputs(state(plan))
    prediction = fusion.uniform_rank_blend(inputs)
    expected = [sum(row) / 4 for row in inputs.expert_ranks]
    assert tuple(float(score) for _, score in prediction.scores) == pytest.approx(expected)
    assert prediction == core.seal(inputs.snapshot, expected)


def test_gate_uses_same_centered_ranks_and_per_instrument_weights_without_mutation(plan):
    inputs = fusion.FusionInputs(state(plan))
    weights = np.zeros((12, 4))
    for i in range(12):
        weights[i, i % 4] = 1
    before = weights.copy()
    scores = fusion.weighted_rank_scores(inputs, weights)
    assert scores == tuple(row[i % 4] for i, row in enumerate(inputs.expert_ranks))
    uniform = fusion.weighted_rank_scores(inputs, np.full((12, 4), 0.25))
    assert core.seal(inputs.snapshot, uniform) == fusion.uniform_rank_blend(inputs)
    assert np.array_equal(weights, before)


@pytest.mark.parametrize("fault", ["global", "missing", "negative", "sum", "nan", "complex"])
def test_gate_weight_geometry_and_softmax_domain(plan, fault):
    inputs = fusion.FusionInputs(state(plan))
    weights = np.full((12, 4), 0.25)
    if fault == "global":
        weights = weights[0]
    elif fault == "missing":
        weights = weights[:-1]
    elif fault == "negative":
        weights[0] = [-0.1, 0.3, 0.4, 0.4]
    elif fault == "sum":
        weights[0] = [0.25, 0.25, 0.25, 0.2]
    elif fault == "nan":
        weights[0, 0] = float("nan")
    else:
        weights = weights.astype(complex)
    with pytest.raises(ValueError):
        fusion.weighted_rank_scores(inputs, weights)


def test_float32_softmax_roundoff_is_explicit_and_not_renormalized(plan):
    inputs = fusion.FusionInputs(state(plan))
    weights = np.tile(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32), (12, 1))
    scores = fusion.weighted_rank_scores(inputs, weights)
    expected = tuple(
        sum(rank * float(weight) for rank, weight in zip(row, weights[0], strict=True))
        for row in inputs.expert_ranks
    )
    assert scores == pytest.approx(expected)


@pytest.mark.parametrize("count", [0, 1, 9])
def test_gate_blend_preserves_flat_cross_sections(plan, count):
    inputs = fusion.FusionInputs(state(plan, count=count))
    scores = fusion.weighted_rank_scores(inputs, ((0.25,) * 4,) * count)
    policy = fusion.seal_predictions(inputs, {"contextual_gate": scores})["contextual_gate"]
    assert policy.selected_keys == ()
    assert core.replay_day(policy, forbidden).complete


@pytest.mark.parametrize("count", [0, 1, 9])
def test_under_ten_is_flat_for_all_named_policies_without_target_reads(plan, count):
    inputs = fusion.FusionInputs(state(plan, count=count))
    predictions = {name: [0.0] * count for name in fusion.LEARNED_POLICIES}
    for policy in fusion.seal_predictions(inputs, predictions).values():
        assert policy.selected_keys == ()
        assert policy.snapshot.unavailable_keys == plan.keys[count:]
        replay = core.replay_day(policy, forbidden)
        assert replay.complete and replay.gross_return == replay.net_return == 0


def test_missing_unselected_target_does_not_change_geometry_or_sealed_winners(plan):
    inputs = fusion.FusionInputs(state(plan))
    scores = dict.fromkeys(inputs.eligible_keys, 0.0)
    prediction = fusion.seal_predictions(inputs, {"contextual_gate": scores})["contextual_gate"]
    missing = plan.keys[-1]

    def target(key, day):
        assert day == inputs.snapshot.entry_session
        return None if key == missing else core.OpenClose(100, 101)

    labels = core.target_labels(inputs.snapshot, target)
    assert labels.labels is None and labels.missing_keys == (missing,)
    with pytest.raises(ValueError, match="complete_date_rank_labels_required"):
        fusion.training_labels(inputs, labels)
    assert inputs.eligible_keys == plan.keys
    assert prediction.selected_keys == plan.keys[:10]
    assert core.replay_day(prediction, target).complete
    assert inputs == fusion.FusionInputs(inputs.snapshot)


def test_missing_selected_outcome_is_unavailable_not_zero_or_replaced(plan):
    inputs = fusion.FusionInputs(state(plan))
    prediction = fusion.seal_predictions(inputs, {"contextual_gate": [0.0] * 12})["contextual_gate"]
    omitted = prediction.selected_keys[0]

    def target(key, _day):
        return None if key == omitted else core.OpenClose(100, 101)

    day = core.replay_day(prediction, target)
    assert day.missing_selected == (omitted,)
    assert not day.complete and day.net_return is day.gross_return is None
    assert day.reason == "selected_target_missing"
    assert prediction.selected_keys == plan.keys[:10]


def test_training_labels_require_exact_complete_decision_snapshot(plan):
    inputs = fusion.FusionInputs(state(plan))
    labels = core.target_labels(
        inputs.snapshot, lambda key, _day: core.OpenClose(100, 100 + int(key[-3:]))
    )
    assert fusion.training_labels(inputs, labels) == tuple(value for _, value in labels.labels)
    wrong_date = fusion.FusionInputs(state(plan, index=101))
    with pytest.raises(ValueError, match="labels_must_match_decision_snapshot"):
        fusion.training_labels(wrong_date, labels)
    with pytest.raises(ValueError, match="labels_must_match_decision_snapshot"):
        fusion.training_labels(inputs, [0] * 12)


def test_date_weights_equalize_whole_dates_with_explicit_alpha_scale():
    _, _, keys = training()
    weights = fusion.date_balanced_weights(keys)
    assert weights == pytest.approx((1, 1, 2, 2 / 3, 2 / 3, 2 / 3))
    assert sum(weights) == pytest.approx(len(keys))
    for index in (61, 62, 63):
        total = sum(weight for (day, _), weight in zip(keys, weights, strict=True) if day == index)
        assert total == pytest.approx(2)
    assert fusion.RIDGE_ALPHA == 1.0
    assert fusion.ROUND_TRIP_BPS == (5, 10, 20)


@pytest.mark.parametrize("view,width", [("expert_rank", 4), ("component_flat", 40)])
def test_ridge_matches_independent_weighted_normal_equations_and_scaler(view, width):
    x, y, keys = training(width)
    model = fit(x, y, keys, view)
    weights = np.array([1, 1, 2, 2 / 3, 2 / 3, 2 / 3])
    mean = np.average(x, axis=0, weights=weights)
    scale = np.sqrt(np.average((x - mean) ** 2, axis=0, weights=weights))
    design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    regularizer = np.diag([0, *([1] * width)])
    expected = np.linalg.solve(
        design.T @ (weights[:, None] * design) + regularizer,
        design.T @ (weights * y),
    )
    assert model.mean == pytest.approx(mean)
    assert model.scale == pytest.approx(scale)
    assert model.intercept == pytest.approx(expected[0])
    assert model.coefficients == pytest.approx(expected[1:])
    assert model.predict(x) == pytest.approx(design @ expected)
    assert model.training_row_count == 6 and model.training_date_count == 3


def test_scaler_is_date_balanced_not_row_count_balanced():
    keys = ((61, "a"), (62, "a"), (62, "b"), (62, "c"))
    x = np.asarray([[0.0] * 4, *([[10.0] * 4] * 3)])
    model = fit(x, [0, 1, 1, 1], keys, cutoff=62)
    assert model.mean == (5.0,) * 4
    assert model.scale == (5.0,) * 4


def test_zero_variance_is_scale_one_with_unpenalized_date_balanced_intercept():
    keys = ((61, "a"), (62, "a"), (62, "b"), (62, "c"))
    model = fit([[7.0] * 4] * 4, [0, 10, 10, 10], keys, cutoff=62)
    assert model.mean == (7.0,) * 4
    assert model.scale == (1.0,) * 4
    assert model.coefficients == pytest.approx((0.0,) * 4, abs=1e-14)
    assert model.intercept == pytest.approx(5)
    assert model.predict([[7.0] * 4]) == pytest.approx((5,))
    assert model.predict([]) == ()


@pytest.mark.parametrize("constant", [0.1, 7.1, 1e-12, -0.0017])
def test_exact_constant_columns_stay_zero_variance_despite_weighted_roundoff(constant):
    _, y, keys = training()
    model = fit([[constant] * 4] * len(keys), y, keys)
    assert model.mean == (constant,) * 4
    assert model.scale == (1.0,) * 4
    assert model.coefficients == pytest.approx((0.0,) * 4, abs=1e-14)


def test_single_training_row_is_finite_intercept_only():
    model = fit([[1, 2, 3, 4]], [0.25], ((61, "opaque"),), cutoff=61)
    assert model.scale == (1.0,) * 4
    assert model.coefficients == pytest.approx((0.0,) * 4)
    assert model.predict([[1, 2, 3, 4]]) == pytest.approx((0.25,))


def test_scaler_prefix_only_and_prediction_never_updates_model():
    x, y, keys = training()
    model = fit(x, y, keys)
    before = replace(model)
    evaluation = np.full((3, 4), 1000000.0)
    model.predict(evaluation)
    evaluation[:] = -1000000.0
    model.predict(evaluation)
    assert model == before
    assert model == fit(x, y, keys)
    with pytest.raises(ValueError, match="training_row_after_prefix_cutoff"):
        fit(
            np.vstack((x, evaluation)),
            np.append(y, [0, 0, 0]),
            (*keys, (64, "a"), (64, "b"), (64, "c")),
        )


def test_fit_canonicalizes_row_order_and_does_not_mutate_inputs():
    x, y, keys = training()
    old_x, old_y = x.copy(), y.copy()
    model = fit(x, y, keys)
    order = [5, 1, 3, 0, 4, 2]
    assert fit(x[order], y[order], tuple(keys[i] for i in order)) == model
    assert np.array_equal(x, old_x) and np.array_equal(y, old_y)
    x[:] = 999
    y[:] = 999
    assert fit(old_x, old_y, keys) == model
    with pytest.raises(FrozenInstanceError):
        model.intercept = 0


@pytest.mark.parametrize("fault", ["duplicate", "empty", "early", "future", "bool", "blank_key"])
def test_training_date_key_identity_and_prefix_validation(fault):
    x, y, keys = training()
    if fault == "duplicate":
        keys = (*keys[:-1], keys[0])
    elif fault == "empty":
        x, y, keys = [], [], ()
    elif fault == "early":
        keys = ((60, "a"), *keys[1:])
    elif fault == "future":
        keys = ((64, "a"), *keys[1:])
    elif fault == "bool":
        keys = ((True, "a"), *keys[1:])
    else:
        keys = ((61, ""), *keys[1:])
    with pytest.raises(ValueError):
        fit(x, y, keys)


@pytest.mark.parametrize("cutoff", [60, 800, True, 63.0])
def test_invalid_prefix_cutoff(cutoff):
    x, y, keys = training()
    with pytest.raises(ValueError, match="training_prefix_cutoff_required"):
        fit(x, y, keys, cutoff=cutoff)


@pytest.mark.parametrize("field", ["features", "labels", "weights"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), complex(1, 0), True, "1"])
def test_nonfinite_complex_boolean_string_rows_labels_weights_rejected(field, bad):
    x, y, keys = training()
    if field == "features":
        values = x.tolist()
        values[0][0] = bad
        with pytest.raises(ValueError):
            fit(values, y, keys)
    elif field == "labels":
        values = y.tolist()
        values[0] = bad
        with pytest.raises(ValueError):
            fit(x, values, keys)
    else:
        values = list(fusion.date_balanced_weights(keys))
        values[0] = bad
        with pytest.raises(ValueError):
            fusion.weighted_scaler(x, values)


@pytest.mark.parametrize("bad", [0, -1])
def test_zero_or_negative_scaler_weights_rejected(bad):
    x, _, keys = training()
    weights = list(fusion.date_balanced_weights(keys))
    weights[0] = bad
    with pytest.raises(ValueError, match="strictly_positive_weights_required"):
        fusion.weighted_scaler(x, weights)


@pytest.mark.parametrize("fault", ["width", "row_count", "label_count", "weight_count", "view"])
def test_fixed_fit_geometry(fault):
    x, y, keys = training()
    with pytest.raises(ValueError):
        if fault == "width":
            fit(x[:, :3], y, keys)
        elif fault == "row_count":
            fit(x[:-1], y, keys)
        elif fault == "label_count":
            fit(x, y[:-1], keys)
        elif fault == "weight_count":
            fusion.weighted_scaler(x, [1] * 5)
        else:
            fit(x, y, keys, view="tcn")


@pytest.mark.parametrize("field", ["mean", "scale", "coefficients", "intercept"])
@pytest.mark.parametrize("bad", [float("nan"), complex(1, 0)])
def test_model_rejects_nonfinite_or_complex_scaler_and_weights(field, bad):
    x, y, keys = training()
    model = fit(x, y, keys)
    value = bad if field == "intercept" else (bad, *getattr(model, field)[1:])
    with pytest.raises(ValueError):
        replace(model, **{field: value})


def test_model_rejects_nonpositive_scale_and_invalid_prediction_geometry():
    x, y, keys = training()
    model = fit(x, y, keys)
    with pytest.raises(ValueError, match="strictly_positive_scale_required"):
        replace(model, scale=(0, *model.scale[1:]))
    with pytest.raises(ValueError):
        model.predict([[0, 1, 2]])
    with pytest.raises(ValueError):
        model.predict([[1 + 0j] * 4])


def test_overflow_in_scaling_prediction_or_solver_fails_closed(monkeypatch):
    x, y, keys = training()
    with pytest.raises(ValueError, match="nonfinite_weighted_scaler"):
        fit([[1e308] * 4] * 6, y, keys)
    model = fit(x, y, keys)
    exploding = replace(model, coefficients=(1e308,) * 4)
    with pytest.raises(ValueError, match="nonfinite_ridge_prediction"):
        exploding.predict([[1e308] * 4])

    def broken_solver(*_args, **_kwargs):
        raise np.linalg.LinAlgError("synthetic failure")

    monkeypatch.setattr(np.linalg, "lstsq", broken_solver)
    with pytest.raises(ValueError, match="ridge_numerical_failure"):
        fit(x, y, keys)


def test_two_fitted_views_seal_as_their_true_names_without_target_access(plan, monkeypatch):
    inputs = fusion.FusionInputs(state(plan))
    x_rank, y, keys = training(4)
    x_flat, _, _ = training(40)
    rank_model, flat_model = fit(x_rank, y, keys), fit(x_flat, y, keys, "component_flat")
    monkeypatch.setattr(core, "evaluate_day", forbidden)
    monkeypatch.setattr(core, "target_labels", forbidden)
    policies = fusion.seal_predictions(
        inputs,
        {
            "component_flat_ridge": flat_model.predict(inputs.component_flat),
            "expert_rank_ridge": rank_model.predict(inputs.expert_ranks),
        },
    )
    assert tuple(policies)[-2:] == ("expert_rank_ridge", "component_flat_ridge")
    assert "tcn" not in policies
    assert all(len(policies[name].scores) == 12 for name in tuple(policies)[-2:])

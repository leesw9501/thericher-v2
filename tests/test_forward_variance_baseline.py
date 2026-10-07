"""Synthetic-only CPU controls: no data, model runtime, broker or external state."""

from __future__ import annotations

import socket
import subprocess
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from math import exp, log, sqrt
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.research.forward_variance_baseline import (
    FORECAST_CEILING,
    FORECAST_FLOOR,
    SCALE_FLOOR,
    ForwardVarianceBaselineConfig,
    ForwardVarianceRecord,
    compare_forward_variance_baseline,
    fit_forward_variance_baseline,
    predict_forward_variance_baseline,
    qlike,
)
from thericher_v2.research.intraday_variance_targets import IntradayVarianceTarget

MINUTE = timedelta(minutes=1)
CONFIG = ForwardVarianceBaselineConfig(
    "QQQ", ("own", "constant"), date(2023, 1, 3), date(2023, 1, 5), 60, 120
)


def record(day, *, features=None, target=1.0, past=4.0):
    at = datetime(2023, 1, day, 16, tzinfo=UTC)
    return ForwardVarianceRecord(
        at.date(),
        "QQQ",
        at,
        at,
        (float(day), 9.0) if features is None else features,
        past,
        IntradayVarianceTarget(
            "QQQ", at, 60, at + MINUTE, at + 61 * MINUTE, at + 62 * MINUTE, target
        ),
    )


def train():
    return tuple(record(day, target=exp(day)) for day in (1, 2, 3))


def fit(rows=None):
    return fit_forward_variance_baseline(train() if rows is None else rows, config=CONFIG)


def no_input(row, status="required_past_m1_shortfall"):
    return replace(
        row,
        features=None,
        features_available_at=None,
        past_realized_variance=None,
        input_status=status,
    )


def test_train_only_population_scaling_and_fixed_ridge_exact_solution():
    model = fit((*train(), record(5, features=(1e8, -1e8), target=1e200)))
    assert model.feature_mean == (2.0, 9.0)
    assert model.feature_scale == pytest.approx((sqrt(2 / 3), SCALE_FLOOR))
    assert model.intercept == pytest.approx(2.0)
    assert model.coefficients == pytest.approx((sqrt(2 / 3) * 3 / 4, 0.0))
    assert model.train_mean_variance == pytest.approx(sum(exp(day) for day in (1, 2, 3)) / 3)
    assert model.train_available_through == train()[-1].target.available_at
    prediction = predict_forward_variance_baseline(model, (record(5),))[0]
    assert prediction.log_ridge == pytest.approx(exp(2 + 3 * 3 / 4))
    assert model.scope == "non_promoting_forward_risk"
    with pytest.raises(FrozenInstanceError):
        model.intercept = 0


def test_chronological_cut_is_before_exclusion_and_embargo_is_unread():
    rows = (
        no_input(train()[0]),
        *train()[1:],
        record(4, features=(float("nan"),), target=-1),
        record(5),
    )
    model = fit(rows)
    assert tuple(day for day, _ in model.training_rows) == tuple(
        row.session_date for row in train()
    )
    assert model.training_rows[0][1] == ("input:required_past_m1_shortfall",)
    assert model.feature_mean == (2.5, 9.0)
    with pytest.raises(ValueError, match="comparison must follow"):
        predict_forward_variance_baseline(model, (rows[-2],))


@pytest.mark.parametrize(
    "rows",
    [
        (record(2), record(1)),
        (record(1), record(1)),
        (record(1), replace(record(2), decision_at=record(1).decision_at)),
    ],
)
def test_unordered_duplicate_sessions_and_decisions_reject(rows):
    with pytest.raises(ValueError, match="chronological"):
        fit(rows)


def test_same_scheduled_date_is_not_counted_as_two_independent_rows():
    with pytest.raises(ValueError, match="chronological"):
        fit((record(1), replace(record(1), decision_at=record(1).decision_at + MINUTE)))


@pytest.mark.parametrize(
    "mutation",
    [
        {"symbol": "SPY"},
        {"session_date": datetime(2023, 1, 1)},
        {"decision_at": datetime(2023, 1, 1, 16)},
        {"decision_at": datetime(2023, 1, 1, 16, 0, 1, tzinfo=UTC)},
    ],
)
def test_metadata_validation(mutation):
    with pytest.raises(ValueError):
        fit((replace(record(1), **mutation), *train()[1:]))


@pytest.mark.parametrize(
    "mutation",
    [
        {"symbol": "qqq"},
        {"feature_names": ()},
        {"feature_names": ("x", "x")},
        {"train_through": CONFIG.comparison_from},
        {"comparison_from": CONFIG.train_through},
        {"horizon_minutes": 0},
        {"past_return_count": True},
        {"past_return_count": 0},
    ],
)
def test_frozen_config_validation(mutation):
    with pytest.raises(ValueError):
        replace(CONFIG, **mutation)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True, "1"])
@pytest.mark.parametrize("field", ["feature", "past", "target"])
def test_nonfinite_and_nonnumeric_values_are_not_dropped(bad, field):
    row = record(1)
    row = (
        replace(row, features=(bad, 9.0))
        if field == "feature"
        else replace(row, past_realized_variance=bad)
        if field == "past"
        else replace(row, target=replace(row.target, realized_variance=bad))
    )
    with pytest.raises(ValueError, match="finite numeric"):
        fit((row, *train()[1:]))


def test_negative_target_is_invalid_even_when_input_is_missing():
    with pytest.raises(ValueError, match="nonnegative"):
        fit((no_input(record(1, target=-1)), *train()[1:]))
    with pytest.raises(ValueError, match="nonnegative"):
        compare_forward_variance_baseline(fit(), (no_input(record(5, target=-1)),))


def test_zero_train_targets_and_independent_missingness_are_visible():
    rows = (no_input(record(1, target=0)), *train()[1:])
    model = fit(rows)
    assert model.training_rows[0][1] == (
        "input:required_past_m1_shortfall",
        "target:zero_log_domain",
    )
    assert model.train_mean_variance == pytest.approx((exp(2) + exp(3)) / 2)
    with pytest.raises(ValueError, match="two complete positive-target"):
        fit((record(1, target=0), record(2, target=0), record(3)))


def test_comparison_keeps_zero_missing_and_input_exclusions_and_one_common_cohort():
    model = fit()
    missing_target = replace(record(7), target=None, target_status="session_horizon_shortfall")
    missing_both = replace(
        no_input(record(8)), target=None, target_status="required_forward_m1_shortfall"
    )
    rows = (record(5, target=2), record(6, target=0), missing_target, missing_both)
    result = compare_forward_variance_baseline(model, rows)
    assert len(result.rows) == 4
    assert result.scored_count == 1
    assert result.rows[1].exclusions == ("target:zero_log_domain",)
    assert result.rows[1].prediction.log_ridge > 0
    assert result.rows[2].exclusions == ("target:session_horizon_shortfall",)
    assert result.rows[2].prediction.log_ridge > 0
    assert result.rows[3].exclusions == (
        "input:required_past_m1_shortfall",
        "target:required_forward_m1_shortfall",
    )
    assert all(row.qlike is None for row in result.rows[1:])
    assert result.mean_qlike == result.rows[0].qlike
    assert result.scope == model.scope
    empty = compare_forward_variance_baseline(model, (record(5, target=0),))
    assert empty.scored_count == 0 and empty.mean_qlike is None
    assert compare_forward_variance_baseline(model, ()).rows == ()


def test_baseline_horizon_scaling_floor_and_qlike_formula():
    model = fit()
    rows = (record(5, target=2, past=4), record(6, target=3, past=0))
    predictions = predict_forward_variance_baseline(model, rows)
    assert predictions[0].past_variance == 2
    assert not predictions[0].past_floored
    assert predictions[1].past_variance == FORECAST_FLOOR
    assert predictions[1].past_floored
    assert all(prediction.train_mean == model.train_mean_variance for prediction in predictions)
    result = compare_forward_variance_baseline(model, rows)
    assert result.rows[0].qlike[1] == 0
    assert qlike(2, 4) == pytest.approx(0.5 - log(0.5) - 1)
    assert result.mean_qlike == pytest.approx(
        tuple((result.rows[0].qlike[index] + result.rows[1].qlike[index]) / 2 for index in range(3))
    )
    assert qlike(1e-300, 1e300) > 0
    assert qlike(1.0, 1.0 + 1e-10) > 0


@pytest.mark.parametrize(
    "target,forecast",
    [(0, 1), (-1, 1), (1, 0), (1, -1), (float("nan"), 1), (1, float("inf")), (1e300, 1e-300)],
)
def test_qlike_rejects_undefined_or_nonfinite_loss(target, forecast):
    with pytest.raises(ValueError):
        qlike(target, forecast)


@pytest.mark.parametrize(
    "field,value",
    [
        ("features", None),
        ("features", (1.0,)),
        ("features", [1.0, 2.0]),
        ("features_available_at", None),
        ("features_available_at", datetime(2023, 1, 1, 17, tzinfo=UTC)),
        ("past_realized_variance", None),
        ("past_realized_variance", -1),
        ("input_status", ""),
        ("input_status", "missing"),
        ("target", None),
        ("target_status", "missing"),
    ],
)
def test_missing_values_need_consistent_explicit_status(field, value):
    with pytest.raises(ValueError):
        fit((replace(record(1), **{field: value}), *train()[1:]))


@pytest.mark.parametrize(
    "mutation",
    [
        {"symbol": "SPY"},
        {"horizon_minutes": 59},
        {"available_at": datetime(2023, 1, 1, 17, 1, tzinfo=UTC)},
        {"target_start": datetime(2023, 1, 1, 16, tzinfo=UTC)},
        {"decision_at": datetime(2023, 1, 1, 16, 1, tzinfo=UTC)},
    ],
)
def test_target_geometry_must_match_existing_helper(mutation):
    row = record(1)
    with pytest.raises(ValueError, match="geometry"):
        fit((replace(row, target=replace(row.target, **mutation)), *train()[1:]))


def test_comparison_cannot_precede_training_label_availability():
    model = fit()
    row = replace(
        record(5),
        decision_at=model.train_available_through,
        features_available_at=model.train_available_through,
    )
    with pytest.raises(ValueError, match="TRAIN target availability"):
        predict_forward_variance_baseline(model, (row,))


def test_future_features_targets_and_missingness_never_change_fit():
    initial = (*train(), record(5), record(6))
    reference = fit(initial)
    mutations = (
        replace(record(5), features=(1e6, -1e6), past_realized_variance=1e8),
        replace(record(5), target=replace(record(5).target, realized_variance=1e200)),
        replace(record(5), target=None, target_status="required_forward_m1_shortfall"),
        no_input(record(5)),
        replace(record(5), features=(float("nan"),), target=object(), target_status=None),
    )
    for mutated in mutations:
        assert fit((*train(), mutated, initial[-1])) == reference
    predictions = predict_forward_variance_baseline(reference, initial[-2:])
    for mutated in mutations[1:3]:
        assert predict_forward_variance_baseline(reference, (mutated, initial[-1])) == predictions
    poison = mutations[-1]
    target_poison_only = replace(
        record(5), target=poison.target, target_status=poison.target_status
    )
    assert (
        predict_forward_variance_baseline(reference, (target_poison_only, initial[-1]))
        == predictions
    )
    changed_target = compare_forward_variance_baseline(reference, (mutations[1], initial[-1]))
    original = compare_forward_variance_baseline(reference, initial[-2:])
    assert changed_target.rows[0].qlike != original.rows[0].qlike
    assert changed_target.rows[1] == original.rows[1]
    changed_input = predict_forward_variance_baseline(reference, (mutations[0], initial[-1]))
    assert changed_input[1] == predictions[1]
    assert reference == fit(initial)


def test_extreme_future_inputs_get_positive_fixed_bounds_or_explicit_failure():
    model = fit()
    forecasts = predict_forward_variance_baseline(
        model, (record(5, features=(1e6, 9.0)), record(6, features=(-1e6, 9.0)))
    )
    assert forecasts[0].log_ridge == FORECAST_CEILING
    assert forecasts[1].log_ridge == FORECAST_FLOOR
    assert all(prediction.ridge_clipped for prediction in forecasts)
    with pytest.raises(ValueError, match="numerical transform"):
        predict_forward_variance_baseline(model, (record(5, features=(1.0, 1e308)),))
    with pytest.raises(ValueError, match="TRAIN numerical"):
        fit(
            tuple(record(day, features=(1e308 * (-1 if day == 1 else 1), 9.0)) for day in (1, 2, 3))
        )


def test_constant_features_fit_unpenalized_log_mean_not_arithmetic_mean():
    rows = tuple(
        record(day, features=(7.0, 9.0), target=value)
        for day, value in zip((1, 2, 3), (1.0, 4.0, 16.0), strict=True)
    )
    model = fit(rows)
    assert model.coefficients == (0.0, 0.0)
    prediction = predict_forward_variance_baseline(model, (record(5, features=(7.0, 9.0)),))[0]
    assert prediction.log_ridge == pytest.approx(4.0)
    assert prediction.train_mean == pytest.approx(7.0)


def test_comparison_invalid_targets_reject_without_changing_model():
    model = fit()
    for value in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            compare_forward_variance_baseline(model, (record(5, target=value),))
    assert model == fit()


def test_only_one_numpy_solve_and_no_comparison_refit(monkeypatch):
    calls = []
    solve = np.linalg.solve

    def counted(*args):
        calls.append(1)
        return solve(*args)

    monkeypatch.setattr(np.linalg, "solve", counted)
    model = fit()
    compare_forward_variance_baseline(model, (record(5), record(6)))
    predict_forward_variance_baseline(model, (record(7),))
    assert calls == [1]


def test_missing_train_target_is_audited_and_does_not_shift_cut():
    rows = (
        replace(record(1), target=None, target_status="required_forward_m1_shortfall"),
        *train()[1:],
        record(5, target=1e200),
    )
    model = fit(rows)
    assert model.training_rows[0][1] == ("target:required_forward_m1_shortfall",)
    assert model.feature_mean == (2.5, 9.0)
    assert model.train_mean_variance == pytest.approx((exp(2) + exp(3)) / 2)


def test_future_record_addition_removal_cannot_change_fit_or_earlier_prediction():
    model = fit((*train(), record(5)))
    assert fit((*train(), record(5), record(6, target=1e100))) == model == fit()
    alone = predict_forward_variance_baseline(model, (record(5),))
    together = predict_forward_variance_baseline(model, (record(5), record(6)))
    assert alone[0] == together[0]


def test_comparison_features_and_past_variance_are_validated_without_target_mask():
    model = fit()
    for field in ("features", "past_realized_variance"):
        invalid = (float("nan"), 9.0) if field == "features" else float("inf")
        row = replace(record(5), **{field: invalid}, target=None, target_status="missing")
        with pytest.raises(ValueError, match="finite numeric"):
            compare_forward_variance_baseline(model, (row,))


def test_helpers_do_not_open_files_or_use_external_surfaces(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pure baseline attempted an external side effect")

    with monkeypatch.context() as local:
        local.setattr(Path, "open", forbidden)
        local.setattr(socket, "create_connection", forbidden)
        local.setattr(socket.socket, "connect", forbidden)
        local.setattr(subprocess, "Popen", forbidden)
        model = fit()
        result = compare_forward_variance_baseline(model, (record(5),))
        assert result.scored_count == 1

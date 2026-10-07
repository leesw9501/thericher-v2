"""Frozen synthetic losses only; no fit, source, broker or external state."""

from __future__ import annotations

import builtins
import json
import socket
import subprocess
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from math import fsum
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.research import forward_variance_baseline as baseline
from thericher_v2.research.forward_variance_baseline import (
    VarianceComparison,
    VariancePrediction,
    VarianceScore,
)
from thericher_v2.research.forward_variance_evaluation import evaluate_variance_baselines

DATES = tuple(date(2023, 1, 1) + timedelta(days=index) for index in range(90))


def score(day, losses=(1.0, 2.0, 3.0), *, exclusions=()):
    inputs = tuple(reason for reason in exclusions if reason.startswith("input:"))
    return VarianceScore(
        VariancePrediction(
            day,
            datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=16),
            inputs,
            None if inputs else 1.0,
            None if inputs else 1.0,
            None if inputs else 1.0,
        ),
        exclusions,
        None if exclusions else losses,
    )


def comparison(rows=None):
    rows = tuple(score(day) for day in DATES) if rows is None else tuple(rows)
    losses = [row.qlike for row in rows if row.qlike is not None]
    means = (
        tuple(fsum(loss[index] / len(losses) for loss in losses) for index in range(3))
        if losses
        else None
    )
    return VarianceComparison(rows, len(losses), means)


def evaluate(qqq=None, spy=None, *, dates=DATES):
    return evaluate_variance_baselines(
        {"QQQ": comparison() if qqq is None else qqq, "SPY": comparison() if spy is None else spy},
        comparison_dates=dates,
    )


def mutate_row(result, index, **fields):
    rows = list(result.rows)
    rows[index] = replace(rows[index], **fields)
    return replace(result, rows=tuple(rows))


def test_fixed_groups_deterministic_source_safe_aggregates_and_strict_success():
    result = evaluate()
    assert result["status"] == "supported-development-premise"
    assert result["scope"] == "non_promoting_forward_risk"
    assert result["model_order"] == ("log_ridge", "past_variance", "train_mean")
    assert result["paired_difference_order"] == (
        "ridge_minus_past_variance",
        "ridge_minus_train_mean",
    )
    assert result["group_order"] == ("all90", "first45", "last45")
    for groups in result["etfs"].values():
        for name, group in groups.items():
            count = 90 if name == "all90" else 45
            assert (group["scheduled_count"], group["eligible_count"], group["excluded_count"]) == (
                count,
                count,
                0,
            )
            assert group["mean_qlike"] == (1.0, 2.0, 3.0)
            assert group["paired_differences"] == (-1.0, -2.0)
            assert group["exclusion_reasons"] == {}
            deletion = group["leave_one_shared_date_out"]
            assert deletion["checked_date_count"] == 90
            assert deletion["undefined_count"] == deletion["failed_date_count"] == 0
            assert deletion["worst_paired_differences"] == (-1.0, -2.0)
            assert deletion["incremental_premise"]
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    assert all(term not in encoded for term in ("coefficients", "decision_at", "forecasts"))
    assert result == evaluate_variance_baselines(
        {"SPY": comparison(), "QQQ": comparison()}, comparison_dates=DATES
    )


def test_scheduled_half_does_not_move_after_missingness_and_zero_exclusions():
    rows = tuple(
        score(day, exclusions=("input:required_past_m1_shortfall",))
        if index < 44
        else score(day, (1.0, 4.0, 5.0))
        if index == 44
        else score(day, exclusions=("target:zero_log_domain",))
        if index == 45
        else score(day, (2.0, 3.0, 6.0))
        for index, day in enumerate(DATES)
    )
    result = evaluate(comparison(rows))
    groups = result["etfs"]["QQQ"]
    assert groups["first45"]["scheduled_count"] == groups["last45"]["scheduled_count"] == 45
    assert groups["first45"]["eligible_count"] == 1
    assert groups["first45"]["mean_qlike"] == (1.0, 4.0, 5.0)
    assert groups["last45"]["eligible_count"] == 44
    assert groups["last45"]["mean_qlike"] == (2.0, 3.0, 6.0)
    assert groups["all90"]["excluded_count"] == 45
    assert groups["all90"]["exclusion_reasons"] == {
        "input:required_past_m1_shortfall": 44,
        "target:zero_log_domain": 1,
    }
    assert groups["first45"]["leave_one_shared_date_out"]["undefined_count"] == 1
    assert result["status"] == "rejected"


def test_multiple_reasons_count_excluded_rows_once_and_preserve_forecast_flags():
    rows = list(comparison().rows)
    rows[0] = score(DATES[0], exclusions=("input:missing", "target:zero_log_domain"))
    rows[1] = score(DATES[1], exclusions=("target:session_horizon_shortfall",))
    rows[1] = replace(
        rows[1], prediction=replace(rows[1].prediction, ridge_clipped=True, past_floored=True)
    )
    group = evaluate(comparison(rows))["etfs"]["QQQ"]["first45"]
    assert group["eligible_count"] == 43 and group["excluded_count"] == 2
    assert sum(group["exclusion_reasons"].values()) == 3
    assert group["scheduled_ridge_clipped_count"] == group["scheduled_past_floored_count"] == 1


def test_paired_loss_means_use_same_dates_not_etf_pool_or_difference_of_rounded_means():
    rows = tuple(
        score(day, (float(index), float(index + 2), float(index + 4)))
        for index, day in enumerate(DATES)
    )
    result = evaluate(comparison(rows))
    qqq = result["etfs"]["QQQ"]
    assert qqq["all90"]["mean_qlike"] == (44.5, 46.5, 48.5)
    assert qqq["first45"]["mean_qlike"] == (22.0, 24.0, 26.0)
    assert qqq["last45"]["mean_qlike"] == (67.0, 69.0, 71.0)
    assert qqq["all90"]["paired_differences"] == (-2.0, -4.0)
    assert result["etfs"]["SPY"]["all90"]["paired_differences"] == (-1.0, -2.0)


def test_one_fragile_day_fails_deletion_without_any_fit_or_reweighting():
    rows = tuple(
        score(day, (0.0, 100.0, 200.0))
        if index == 0
        else score(day, (2.0, 1.0, 1.0))
        if index < 45
        else score(day, (0.0, 3.0, 4.0))
        for index, day in enumerate(DATES)
    )
    result = evaluate(comparison(rows))
    groups = result["etfs"]["QQQ"]
    assert all(group["incremental_premise"] for group in groups.values())
    assert groups["all90"]["leave_one_shared_date_out"]["incremental_premise"]
    group = groups["first45"]
    assert group["leave_one_shared_date_out"]["failed_date_count"] == 1
    assert group["leave_one_shared_date_out"]["worst_paired_differences"] == (1.0, 1.0)
    assert result["status"] == "rejected"


@pytest.mark.parametrize("losses", [(1.0, 1.0, 2.0), (1.0, 2.0, 1.0), (0.0, 0.0, 0.0)])
def test_equality_with_either_control_fails(losses):
    result = evaluate(comparison(tuple(score(day, losses) for day in DATES)))
    assert result["status"] == "rejected"
    assert not result["etfs"]["QQQ"]["all90"]["incremental_premise"]


def test_failed_half_or_etf_cannot_be_rescued_by_pooled_all90_score():
    rows = tuple(
        score(day, (0.0, 10.0, 20.0)) if index < 45 else score(day, (2.0, 1.0, 1.0))
        for index, day in enumerate(DATES)
    )
    result = evaluate(spy=comparison(rows))
    assert result["etfs"]["SPY"]["all90"]["incremental_premise"]
    assert result["etfs"]["QQQ"]["last45"]["incremental_premise"]
    assert not result["etfs"]["SPY"]["last45"]["incremental_premise"]
    assert result["status"] == "rejected"


def test_empty_common_cohort_is_valid_explicit_rejection_not_hidden_date_filter():
    rows = tuple(score(day, exclusions=("target:zero_log_domain",)) for day in DATES)
    result = evaluate(comparison(rows))
    for group in result["etfs"]["QQQ"].values():
        assert group["eligible_count"] == 0
        assert group["excluded_count"] == group["scheduled_count"]
        assert group["mean_qlike"] is group["paired_differences"] is None
        deletion = group["leave_one_shared_date_out"]
        assert deletion["undefined_count"] == deletion["failed_date_count"] == 90
        assert deletion["worst_paired_differences"] is None
    assert result["status"] == "rejected"


@pytest.mark.parametrize(
    "dates",
    [
        (),
        DATES[:-1],
        (*DATES, DATES[-1] + timedelta(days=1)),
        list(DATES),
        (DATES[0], *DATES[:-1]),
        tuple(reversed(DATES)),
        (datetime(2023, 1, 1, tzinfo=UTC), *DATES[1:]),
    ],
)
def test_exact_90_ordered_unique_date_contract(dates):
    with pytest.raises(ValueError, match="90 ordered unique"):
        evaluate(dates=dates)


@pytest.mark.parametrize("symbols", [{}, {"QQQ"}, {"QQQ", "SPY", "IWM"}, {"qqq", "SPY"}])
def test_exact_symbol_scope(symbols):
    with pytest.raises(ValueError, match="exactly QQQ and SPY"):
        evaluate_variance_baselines(
            {symbol: comparison() for symbol in symbols}, comparison_dates=DATES
        )


@pytest.mark.parametrize("rows", [(), comparison().rows[:-1], list(comparison().rows)])
def test_missing_rows_and_mutable_rows_do_not_silently_filter(rows):
    with pytest.raises(ValueError, match="scheduled rows"):
        evaluate(replace(comparison(), rows=rows))


@pytest.mark.parametrize(
    "prediction",
    [
        replace(comparison().rows[0].prediction, session_date=DATES[1]),
        replace(comparison().rows[0].prediction, session_date=datetime(2023, 1, 1)),
        replace(comparison().rows[0].prediction, decision_at=datetime(2023, 1, 1, 16)),
        replace(
            comparison().rows[0].prediction, decision_at=datetime(2023, 1, 1, 16, 0, 1, tzinfo=UTC)
        ),
    ],
)
def test_duplicate_misaligned_dates_or_invalid_decision_clocks(prediction):
    with pytest.raises(ValueError, match="scheduled dates"):
        evaluate(mutate_row(comparison(), 0, prediction=prediction))


def test_etf_shared_date_decisions_and_chronological_clocks_must_align():
    original = comparison()
    shifted = replace(
        original.rows[0].prediction,
        decision_at=original.rows[0].prediction.decision_at + timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="align"):
        evaluate(mutate_row(original, 0, prediction=shifted))
    duplicate = replace(
        original.rows[1].prediction, decision_at=original.rows[0].prediction.decision_at
    )
    with pytest.raises(ValueError, match="scheduled dates"):
        evaluate(mutate_row(original, 1, prediction=duplicate))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), -1.0, True, "1", None])
@pytest.mark.parametrize("index", [0, 1, 2])
def test_invalid_or_negative_losses_are_invalid_not_excluded(bad, index):
    values = [1.0, 2.0, 3.0]
    values[index] = bad
    with pytest.raises(ValueError, match="finite nonnegative"):
        evaluate(mutate_row(comparison(), 0, qlike=tuple(values)))


@pytest.mark.parametrize("values", [None, (), (1.0, 2.0), (1.0, 2.0, 3.0, 4.0), [1.0, 2.0, 3.0]])
def test_common_score_triple_is_mandatory(values):
    with pytest.raises(ValueError, match="common three-model tuple"):
        evaluate(mutate_row(comparison(), 0, qlike=values))


@pytest.mark.parametrize(
    "reasons",
    [
        ("",),
        (" target:missing",),
        ("target:",),
        ("target:missing", "target:missing"),
        ("private/path",),
        ["target:missing"],
    ],
)
def test_empty_duplicate_or_unsafe_exclusion_categories_reject(reasons):
    with pytest.raises(ValueError, match="source-safe"):
        evaluate(mutate_row(comparison(), 0, exclusions=reasons, qlike=None))


def test_excluded_scores_must_be_absent_and_input_reasons_cannot_disappear():
    with pytest.raises(ValueError, match="excluded scores must be absent"):
        evaluate(mutate_row(comparison(), 0, exclusions=("target:zero_log_domain",)))
    rows = list(comparison().rows)
    rows[0] = score(DATES[0], exclusions=("input:missing",))
    rows[0] = replace(rows[0], exclusions=("target:missing",))
    with pytest.raises(ValueError, match="preserve input"):
        evaluate(replace(comparison(), rows=tuple(rows)))


@pytest.mark.parametrize(
    "mutation",
    [
        {"scored_count": 89},
        {"scored_count": True},
        {"mean_qlike": (0.0, 0.0, 0.0)},
        {"mean_qlike": None},
        {"mean_qlike": (1.0, float("inf"), 3.0)},
    ],
)
def test_stale_count_or_mean_metadata_rejects(mutation):
    with pytest.raises(ValueError):
        evaluate(replace(comparison(), **mutation))


def test_empty_cohort_cannot_carry_mean_metadata():
    result = comparison(tuple(score(day, exclusions=("target:missing",)) for day in DATES))
    with pytest.raises(ValueError, match="empty cohort"):
        evaluate(replace(result, mean_qlike=(0.0, 0.0, 0.0)))


@pytest.mark.parametrize(
    "mutation",
    [
        {"log_ridge": None},
        {"past_variance": 0.0},
        {"train_mean": float("inf")},
        {"ridge_clipped": 1},
        {"past_floored": "false"},
    ],
)
def test_prediction_cohort_must_have_finite_positive_forecasts_and_boolean_flags(mutation):
    original = comparison()
    with pytest.raises(ValueError):
        evaluate(
            mutate_row(original, 0, prediction=replace(original.rows[0].prediction, **mutation))
        )


def test_input_exclusion_cannot_retain_forecast_or_clip_flag():
    original = comparison()
    missing = score(DATES[0], exclusions=("input:missing",))
    for mutation in ({"log_ridge": 1.0}, {"ridge_clipped": True}):
        malformed = replace(missing, prediction=replace(missing.prediction, **mutation))
        with pytest.raises(ValueError, match="no forecasts or flags"):
            evaluate(replace(original, rows=(malformed, *original.rows[1:])))


def test_finite_extreme_losses_do_not_overflow_and_no_incremental_epsilon():
    result = evaluate(comparison(tuple(score(day, (0.0, 1e308, 1e308)) for day in DATES)))
    assert result["status"] == "supported-development-premise"
    assert result["etfs"]["QQQ"]["all90"]["mean_qlike"] == (0.0, 1e308, 1e308)
    tiny = evaluate(comparison(tuple(score(day, (0.0, 1e-300, 1e-300)) for day in DATES)))
    assert tiny["status"] == "supported-development-premise"


def test_no_refits_files_network_processes_or_input_mutation(monkeypatch):
    original = {"QQQ": comparison(), "SPY": comparison()}
    snapshot = dict(original)

    def forbidden(*args, **kwargs):
        pytest.fail("pure evaluation attempted a fit or external side effect")

    with monkeypatch.context() as local:
        local.setattr(baseline, "fit_forward_variance_baseline", forbidden)
        local.setattr(baseline, "predict_forward_variance_baseline", forbidden)
        local.setattr(baseline, "compare_forward_variance_baseline", forbidden)
        local.setattr(np.linalg, "solve", forbidden)
        local.setattr(builtins, "open", forbidden)
        local.setattr(Path, "open", forbidden)
        local.setattr(socket, "create_connection", forbidden)
        local.setattr(socket.socket, "connect", forbidden)
        local.setattr(subprocess, "Popen", forbidden)
        result = evaluate_variance_baselines(original, comparison_dates=DATES)
    assert result["status"] == "supported-development-premise"
    assert original == snapshot

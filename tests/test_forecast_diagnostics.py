from __future__ import annotations

import json
import math

import numpy as np
import pytest

from thericher_v2.research.forecast_diagnostics import summarize_forecast


def test_aggregate_metrics_and_fixed_train_baseline() -> None:
    result = summarize_forecast([-2, 0, 4], [-1, 2, 5], ["a", "a", "a"], train_mean_bps=10)

    assert result["n"] == 3
    assert result["session_count"] == 1
    assert result["predicted_mean_bps"] == pytest.approx(2 / 3)
    assert result["predicted_std_bps"] == pytest.approx(math.sqrt(56 / 9))
    assert result["actual_mean_bps"] == 2
    assert result["actual_std_bps"] == pytest.approx(math.sqrt(6))
    assert result["mae_bps"] == pytest.approx(4 / 3)
    assert result["mse_bps2"] == 2
    assert result["zero_forecast_mse_bps2"] == 10
    assert result["train_mean_forecast_mse_bps2"] == 70
    assert result["mse_skill_vs_zero"] == pytest.approx(0.8)
    assert result["mse_skill_vs_train_mean"] == pytest.approx(1 - 2 / 70)
    assert result["pearson"] == pytest.approx(9 / math.sqrt(84))
    assert result["spearman"] == pytest.approx(1)
    assert result["directional_accuracy"] == pytest.approx(2 / 3)
    assert result["calibration_slope"] == pytest.approx(27 / 28)
    assert result["calibration_intercept_bps"] == pytest.approx(19 / 14)


def test_fixed_bin_boundaries_and_strict_selected_subset() -> None:
    result = summarize_forecast(
        [-7, -6, -1, 0, 6, 7], [2, -2, 4, 0, -4, 6], ["s"] * 6, train_mean_bps=0
    )

    assert result["predicted_bins"] == {
        "[-inf,-6)": {
            "n": 1,
            "pred_mean": -7.0,
            "actual_mean": 2.0,
            "positive_actual_fraction": 1.0,
        },
        "[-6,0)": {"n": 2, "pred_mean": -3.5, "actual_mean": 1.0, "positive_actual_fraction": 0.5},
        "[0,6]": {"n": 2, "pred_mean": 3.0, "actual_mean": -2.0, "positive_actual_fraction": 0.0},
        "(6,inf)": {"n": 1, "pred_mean": 7.0, "actual_mean": 6.0, "positive_actual_fraction": 1.0},
    }
    assert sum(item["n"] for item in result["predicted_bins"].values()) == result["n"]
    assert result["selected_gt_6bps"] == {"n": 1, "share": 1 / 6, "actual_mean_bps": 6.0}


def test_spearman_uses_average_tied_ranks_and_is_order_invariant() -> None:
    predicted = np.array([3, 1, 1, 2], dtype=float)
    actual = np.array([2, 4, 2, 1], dtype=float)
    result = summarize_forecast(predicted, actual, ["s"] * 4, train_mean_bps=0)
    # Ranks: predicted [4, 1.5, 1.5, 3]; actual [2.5, 4, 2.5, 1].
    assert result["spearman"] == pytest.approx(-0.5)
    assert result["pearson"] != pytest.approx(-0.5)
    order = [2, 0, 3, 1]
    reordered = summarize_forecast(predicted[order], actual[order], ["s"] * 4, train_mean_bps=0)
    for field in result:
        if isinstance(result[field], float):
            assert reordered[field] == pytest.approx(result[field])
        else:
            assert reordered[field] == result[field]


@pytest.mark.parametrize("predicted,actual", [([1, 1, 1], [1, 2, 3]), ([1, 2, 3], [0, 0, 0])])
def test_constant_vectors_have_undefined_correlations(predicted, actual) -> None:
    result = summarize_forecast(predicted, actual, ["s"] * 3, train_mean_bps=0)
    assert result["pearson"] is None
    assert result["spearman"] is None
    assert result["mean_session_pearson"] is None
    assert result["valid_session_count"] == 0
    if predicted[0] == predicted[-1]:
        assert result["calibration_slope"] is None
        assert result["calibration_intercept_bps"] is None
    else:
        assert result["calibration_slope"] == 0
        assert result["calibration_intercept_bps"] == 0


def test_single_row_empty_bins_and_absent_selection() -> None:
    result = summarize_forecast([6], [-2], ["only"], train_mean_bps=3)
    assert result["n"] == result["session_count"] == 1
    assert result["predicted_std_bps"] == result["actual_std_bps"] == 0
    assert result["pearson"] is result["spearman"] is None
    assert result["calibration_slope"] is result["calibration_intercept_bps"] is None
    assert result["mean_session_pearson"] is None
    assert result["valid_session_count"] == 0
    assert result["selected_gt_6bps"] == {"n": 0, "share": 0.0, "actual_mean_bps": None}
    for label in ("[-inf,-6)", "[-6,0)", "(6,inf)"):
        assert result["predicted_bins"][label] == {
            "n": 0,
            "pred_mean": None,
            "actual_mean": None,
            "positive_actual_fraction": None,
        }


def test_session_mean_is_unweighted_and_omits_only_undefined_sessions() -> None:
    result = summarize_forecast(
        [1, 1, 2, 2, 3, 4, 8, 9, 9, 10, 11],
        [1, 4, 2, 3, 2, 1, 7, 1, 2, 0, 0],
        ["short", "long", "short", "long", "long", "long", "single", "x", "x", "y", "y"],
        train_mean_bps=0,
    )
    assert result["session_count"] == 5
    assert result["valid_session_count"] == 2
    assert result["mean_session_pearson"] == pytest.approx(0, abs=1e-15)


def test_all_singleton_sessions_have_no_valid_session_pearson() -> None:
    result = summarize_forecast([1, 2], [2, 4], ["a", "b"], train_mean_bps=0)
    assert result["pearson"] == pytest.approx(1)
    assert result["session_count"] == 2
    assert result["valid_session_count"] == 0
    assert result["mean_session_pearson"] is None


def test_directional_accuracy_excludes_actual_zero_not_predicted_zero() -> None:
    result = summarize_forecast([0, -1, 1, 0, 7], [1, -2, 3, 0, 0], ["s"] * 5, train_mean_bps=0)
    assert result["directional_accuracy"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("actual,train_mean", [(0.0, 0.0), (0.0, 2.0), (2.0, 2.0)])
def test_baseline_degeneracy(actual: float, train_mean: float) -> None:
    result = summarize_forecast([1, 3], [actual] * 2, ["s"] * 2, train_mean_bps=train_mean)
    if actual == 0:
        assert result["zero_forecast_mse_bps2"] == 0
        assert result["mse_skill_vs_zero"] is None
        assert result["directional_accuracy"] is None
    if actual == train_mean:
        assert result["train_mean_forecast_mse_bps2"] == 0
        assert result["mse_skill_vs_train_mean"] is None


def test_perfect_forecast_and_negative_skill_are_not_clipped() -> None:
    perfect = summarize_forecast([-2, 2], [-2, 2], ["s"] * 2, train_mean_bps=0)
    assert perfect["mse_bps2"] == perfect["mae_bps"] == 0
    assert perfect["mse_skill_vs_zero"] == perfect["mse_skill_vs_train_mean"] == 1
    bad = summarize_forecast([10, -10], [-1, 1], ["s"] * 2, train_mean_bps=0)
    assert bad["mse_skill_vs_zero"] == bad["mse_skill_vs_train_mean"] == -120


@pytest.mark.parametrize("scale,shift", [(3.0, 0.0), (1.0, 20.0), (-2.0, 5.0)])
def test_common_affine_transformation_of_errors_and_calibration(scale, shift) -> None:
    predicted = np.array([-3.0, 1.0, 2.0, 7.0])
    actual = 2 * predicted + 3
    baseline = summarize_forecast(predicted, actual, ["s"] * 4, train_mean_bps=4)
    result = summarize_forecast(
        scale * predicted + shift,
        scale * actual + shift,
        ["s"] * 4,
        train_mean_bps=scale * 4 + shift,
    )
    assert result["pearson"] == pytest.approx(baseline["pearson"])
    assert result["spearman"] == pytest.approx(baseline["spearman"])
    assert result["mse_bps2"] == pytest.approx(scale**2 * baseline["mse_bps2"])
    assert result["mae_bps"] == pytest.approx(abs(scale) * baseline["mae_bps"])
    assert result["predicted_std_bps"] == pytest.approx(abs(scale) * baseline["predicted_std_bps"])
    assert result["mse_skill_vs_train_mean"] == pytest.approx(baseline["mse_skill_vs_train_mean"])
    assert result["calibration_slope"] == pytest.approx(2)
    assert result["calibration_intercept_bps"] == pytest.approx(3 * scale - shift)


@pytest.mark.parametrize("scale", [1e-100, 1e100])
def test_correlations_and_calibration_survive_large_scale_changes(scale: float) -> None:
    predicted = np.array([-2.0, -1.0, 1.0, 2.0]) * scale
    result = summarize_forecast(predicted, -3 * predicted, ["s"] * 4, train_mean_bps=0)
    assert result["pearson"] == pytest.approx(-1)
    assert result["spearman"] == pytest.approx(-1)
    assert result["calibration_slope"] == pytest.approx(-3)


@pytest.mark.parametrize("field", ["predicted_bps", "actual_bps"])
@pytest.mark.parametrize(
    "value,message",
    [
        ([], "forecast_empty"),
        ([1], "forecast_length_mismatch"),
        (1.0, "forecast_shape_invalid"),
        ([[1, 2]], "forecast_shape_invalid"),
        ([[1], [2]], "forecast_shape_invalid"),
        ([[1], [2, 3]], "forecast_values_invalid"),
        ([float("nan"), 1], "forecast_nonfinite"),
        ([float("inf"), 1], "forecast_nonfinite"),
        ([float("-inf"), 1], "forecast_nonfinite"),
        (["private-value", "2"], "forecast_values_invalid"),
        ([1 + 1j, 2], "forecast_values_invalid"),
        ([True, False], "forecast_values_invalid"),
        (None, "forecast_values_invalid"),
    ],
)
def test_invalid_forecasts_raise_fixed_categories(field, value, message) -> None:
    arguments = {"predicted_bps": [1, 2], "actual_bps": [2, 3], "session_keys": ["s", "s"]}
    arguments[field] = value
    with pytest.raises(ValueError, match=f"^{message}$"):
        summarize_forecast(**arguments, train_mean_bps=0)


@pytest.mark.parametrize(
    "keys", [None, "ss", [["a", "b"]], ["a", 1], ["a", None], ["a", ""], ["a", "  "], [b"a", b"b"]]
)
def test_invalid_session_keys_are_not_coerced(keys) -> None:
    with pytest.raises(ValueError, match="^session_keys_invalid$"):
        summarize_forecast([1, 2], [2, 3], keys, train_mean_bps=0)


@pytest.mark.parametrize("keys", [[], ["s"], ["a", "b", "c"]])
def test_session_length_mismatch(keys) -> None:
    with pytest.raises(ValueError, match="^forecast_length_mismatch$"):
        summarize_forecast([1, 2], [2, 3], keys, train_mean_bps=0)


@pytest.mark.parametrize(
    "train_mean", [None, True, "2", [2.0], complex(2, 1), float("nan"), float("inf"), float("-inf")]
)
def test_invalid_train_mean_raises_fixed_category(train_mean) -> None:
    with pytest.raises(ValueError, match="^train_mean_invalid$"):
        summarize_forecast([1, 2], [2, 3], ["s"] * 2, train_mean_bps=train_mean)


def test_numeric_overflow_cannot_escape_as_nonfinite_json() -> None:
    with pytest.raises(ValueError, match="^forecast_numeric_overflow$"):
        summarize_forecast([1e200, -1e200], [0, 1], ["s"] * 2, train_mean_bps=0)


@pytest.mark.parametrize("predicted,actual", [([0, 0], [0, 0]), ([-8, 0, 6, 8], [-4, 1, 2, 9])])
def test_results_are_finite_native_json_and_inputs_are_unchanged(predicted, actual) -> None:
    predicted = np.array(predicted, dtype=np.float64)
    actual = np.array(actual, dtype=np.float64)
    keys = np.array(["s"] * len(actual))
    snapshots = [array.copy() for array in (predicted, actual, keys)]
    for array in (predicted, actual, keys):
        array.flags.writeable = False
    result = summarize_forecast(predicted, actual, keys, train_mean_bps=np.float64(0))
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert type(result["n"]) is int
    assert type(result["mse_bps2"]) is float
    for array, before in zip((predicted, actual, keys), snapshots, strict=True):
        np.testing.assert_array_equal(array, before)

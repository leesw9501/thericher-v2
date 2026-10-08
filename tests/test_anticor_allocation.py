from __future__ import annotations

import ast
import itertools
import math
import random
from pathlib import Path

import pytest

from thericher_v2.research import anticor_allocation as study

SOURCE = Path(study.__file__)
allocate = study.anticor_allocation


def permute(window, order):
    return tuple(tuple(row[index] for index in order) for row in window)


def test_constant_windows_retain_original_weights():
    previous = ((0.1, -0.2, 0.3),) * 3
    recent = ((0.5, 0.4, -0.1),) * 3
    weights = (0.2, 0.3, 0.5)
    assert allocate(previous, recent, weights) == weights
    assert study._cross_correlations(previous, recent) == ((0.0,) * 3,) * 3


def test_no_positive_claims_retain_weights():
    previous = ((-1.0,) * 3, (1.0,) * 3)
    recent = ((1.0,) * 3, (-1.0,) * 3)
    assert allocate(previous, recent, (0.6, 0.3, 0.1)) == (0.6, 0.3, 0.1)


def test_inclusive_ties_and_self_claims_match_figure_one():
    window = ((-1.0,) * 3, (1.0,) * 3)
    # All nine claims are equal, including the diagonal. Strict ties would do nothing.
    assert allocate(window, window, (0.8, 0.1, 0.1)) == pytest.approx((1 / 3,) * 3)


def test_original_donor_flow_hand_calculation():
    previous = ((-1.0,) * 3, (1.0,) * 3)
    recent = ((1.0, 0.0, -1.0), (3.0, 2.0, 1.0))
    # Claim rows [1,1,1], [0,1,1], [0,0,1]. No incoming wealth is reused.
    result = allocate(previous, recent, (0.6, 0.3, 0.1))
    assert result == pytest.approx((0.2, 0.35, 0.45), abs=1e-15)


def test_negative_self_correlations_increase_off_diagonal_claim():
    previous = ((-1.0, 1.0, 4.0), (1.0, -1.0, 4.0))
    recent = ((2.0, -1.0, 4.0), (0.0, 1.0, 4.0))
    expected = ((-1.0, 1.0, 0.0), (1.0, -1.0, 0.0), (0.0, 0.0, 0.0))
    for actual, row in zip(study._cross_correlations(previous, recent), expected, strict=True):
        assert actual == pytest.approx(row)
    assert allocate(previous, recent, (0.6, 0.3, 0.1)) == pytest.approx((0.0, 0.9, 0.1))


def test_reversal_bonus_changes_two_recipient_flow_ratio():
    previous = ((-1.0, 1.0, -1.0), (1.0, -1.0, 1.0))
    recent = ((4.0, 1.0, 0.0), (2.0, 3.0, 2.0))
    # Donor zero: self-correlation -1; recipient one -1, recipient two +1.
    # Claims are 3 and 2, giving original 0.5 wealth to recipients as 0.3/0.2.
    assert allocate(previous, recent, (0.5, 0.25, 0.25)) == pytest.approx((0.0, 0.55, 0.45))


def test_mean_uses_every_observation_not_last_return():
    previous = ((-2.0,) * 3, (0.0,) * 3, (2.0,) * 3)
    recent = ((4.0, 0.0, 2.0), (3.0, 1.0, 2.0), (-1.0, 2.0, 2.0))
    # Asset zero has higher mean than asset one, despite a lower last return.
    assert allocate(previous, recent, (1.0, 0.0, 0.0)) == (0.0, 1.0, 0.0)


def test_direct_normalized_cross_lag_dot_products():
    previous = ((-2.0, 3.0, 1.0), (0.0, 0.0, 1.0), (2.0, -1.0, 1.0))
    recent = ((1.0, -2.0, 9.0), (2.0, 0.0, 9.0), (4.0, 2.0, 9.0))
    matrix = study._cross_correlations(previous, recent)
    for i, j in itertools.product(range(3), repeat=2):
        x = [row[i] for row in previous]
        y = [row[j] for row in recent]
        dx = [value - math.fsum(x) / 3 for value in x]
        dy = [value - math.fsum(y) / 3 for value in y]
        norm = math.sqrt(math.fsum(a * a for a in dx) * math.fsum(b * b for b in dy))
        expected = math.fsum(a * b for a, b in zip(dx, dy, strict=True)) / norm if norm else 0
        assert matrix[i][j] == pytest.approx(expected, abs=2e-15)


@pytest.mark.parametrize("order", tuple(itertools.permutations(range(3))))
def test_symbol_permutation_is_exact(order):
    previous = ((-1.0, 2.0, 0.0), (2.0, 0.0, 1.0), (0.0, -1.0, -2.0))
    recent = ((3.0, 0.0, -1.0), (0.0, 1.0, 2.0), (-1.0, 2.0, 0.0))
    weights = (0.6, 0.25, 0.15)
    expected = allocate(previous, recent, weights)
    assert allocate(permute(previous, order), permute(recent, order),
                    tuple(weights[i] for i in order)) == tuple(expected[i] for i in order)


def test_constant_column_has_zero_correlations_not_division_failure():
    window = ((-1.0, 0.4, -2.0), (1.0, 0.4, 2.0))
    correlations = study._cross_correlations(window, window)
    assert correlations[1] == (0.0,) * 3
    assert tuple(row[1] for row in correlations) == (0.0,) * 3
    assert allocate(window, window, (0.0, 1.0, 0.0)) == (0.0, 1.0, 0.0)


@pytest.mark.parametrize("scale", [1e-310, 1.0, 1e308])
def test_finite_extremes_do_not_overflow_or_erase_variation(scale):
    window = ((-scale,) * 3, (scale,) * 3)
    assert allocate(window, window, (1.0, 0.0, 0.0)) == pytest.approx((1 / 3,) * 3)


def test_recent_window_changes_the_transfer():
    previous = ((-1.0,) * 3, (1.0,) * 3)
    aligned = previous
    reversed_window = tuple(reversed(previous))
    assert allocate(previous, aligned, (1.0, 0.0, 0.0)) != allocate(
        previous, reversed_window, (1.0, 0.0, 0.0)
    )


def test_caller_slices_past_windows_future_append_cannot_change_input():
    past = [(-1.0,) * 3, (1.0,) * 3, (0.0,) * 3, (2.0,) * 3]
    before = allocate(past[:2], past[2:4], (0.6, 0.3, 0.1))
    for future in [(1e200, -1e200, 0.0), (math.nan,) * 3]:
        assert allocate(past[:2], (past + [future])[2:4], (0.6, 0.3, 0.1)) == before


def test_inputs_not_mutated_and_output_is_immutable():
    earlier = [[-1.0] * 3, [1.0] * 3]
    recent = [[1.0, 0.0, -1.0], [3.0, 2.0, 1.0]]
    weights = [0.6, 0.3, 0.1]
    originals = ([row[:] for row in earlier], [row[:] for row in recent], weights[:])
    result = allocate(earlier, recent, weights)
    assert (earlier, recent, weights) == originals
    assert isinstance(result, tuple)


def test_random_synthetic_long_only_mass_conservation():
    rng = random.Random(101)
    for _ in range(100):
        earlier = tuple(tuple(rng.uniform(-2, 2) for _ in range(3)) for _ in range(5))
        recent = tuple(tuple(rng.uniform(-2, 2) for _ in range(3)) for _ in range(5))
        raw = [rng.random() for _ in range(3)]
        weights = tuple(value / math.fsum(raw) for value in raw)
        output = allocate(earlier, recent, weights)
        assert all(math.isfinite(value) and 0 <= value <= 1 for value in output)
        assert math.fsum(output) == pytest.approx(1.0, abs=2 * math.ulp(1.0))


@pytest.mark.parametrize("bad", [[], [(0.0,) * 3], [(0.0, 0.0)] * 2,
                                  [(0.0,) * 3, (0.0,)], [None, None]])
def test_invalid_window_shape_rejected(bad):
    with pytest.raises(ValueError, match="window_shape"):
        allocate(bad, ((0.0,) * 3,) * 2, (1.0, 0.0, 0.0))


def test_different_window_lengths_rejected():
    with pytest.raises(ValueError, match="window_length"):
        allocate(((0.0,) * 3,) * 2, ((0.0,) * 3,) * 3, (1.0, 0.0, 0.0))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, True, "1"])
def test_nonfinite_or_nonreal_window_values_rejected(bad):
    with pytest.raises(ValueError, match="window_value"):
        allocate(((bad, 0.0, 0.0), (0.0,) * 3), ((0.0,) * 3,) * 2, (1.0, 0.0, 0.0))


@pytest.mark.parametrize("weights,reason", [
    ((2.0, 0.0, 0.0), "weight_domain"), ((-0.1, 0.5, 0.6), "weight_domain"),
    ((0.0, 0.0, 0.0), "weight_sum"), ((0.4, 0.3, 0.2), "weight_sum"),
    ((1.0, 0.0), "weight_shape"), ((math.nan, 0.0, 0.0), "weight_value"),
    ((True, 0.0, 0.0), "weight_value"), ((math.inf, 0.0, 0.0), "weight_value"),
])
def test_invalid_weights_rejected_without_repair(weights, reason):
    with pytest.raises(ValueError, match=reason):
        allocate(((0.0,) * 3,) * 2, ((0.0,) * 3,) * 2, weights)


def test_source_has_no_io_runtime_or_model_dependencies():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports <= {"__future__", "collections.abc", "fractions", "math", "numbers"}
    assert not any(isinstance(node, ast.Import) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {"open", "print", "eval", "exec"}
                   for node in ast.walk(tree))

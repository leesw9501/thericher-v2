"""Synthetic causal mixture tests; no experts, market data, runtime or ledger."""

import ast
import socket
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from thericher_v2.research import causal_expert_mixture as s

DECISION = datetime(2024, 3, 1, 14, 30, tzinfo=UTC)
FEEDBACK = DECISION - timedelta(days=1)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def update(losses, weights=None, **kwargs):
    arguments = dict(
        rate=0.1,
        completed_loss_available_at=FEEDBACK,
        decision_at=DECISION,
        last_feedback_at=None,
    )
    arguments.update(kwargs)
    return s.update_weights(losses, weights, **arguments)


def test_uniform_and_explicit_projection_does_not_mutate_inputs():
    targets = np.array([0.0, 0.2, 1.0])
    weights = np.array([0.2, 0.3, 0.5])
    before = targets.copy(), weights.copy()
    assert s.project_target(targets) == pytest.approx(0.4)
    assert s.project_target(targets, weights) == pytest.approx(0.56)
    np.testing.assert_array_equal(targets, before[0])
    np.testing.assert_array_equal(weights, before[1])


@pytest.mark.parametrize("target", [0.0, 0.5, 1.0])
def test_identical_experts_project_identically_before_and_after_update(target):
    targets = np.full(3, target)
    assert s.project_target(targets) == pytest.approx(target)
    assert s.project_target(targets, update(np.array([-4.0, 2.0, 9.0]))) == pytest.approx(target)


def test_update_matches_exponential_loss_formula_and_keeps_inputs_readonly():
    weights, losses = np.array([0.2, 0.3, 0.5]), np.array([-2.0, 0.0, 3.0])
    before = weights.copy(), losses.copy()
    weights.setflags(write=False)
    losses.setflags(write=False)
    actual = update(losses, weights)
    expected = weights * np.exp(-0.1 * losses)
    expected /= expected.sum()
    np.testing.assert_allclose(actual, expected, rtol=1e-15, atol=0)
    np.testing.assert_array_equal(weights, before[0])
    np.testing.assert_array_equal(losses, before[1])
    assert not actual.flags.writeable and not np.shares_memory(actual, weights)


@pytest.mark.parametrize("loss", [0.0, 5.0, -5.0])
def test_equal_losses_leave_coefficients_unchanged(loss):
    weights = np.array([0.2, 0.3, 0.5])
    actual = update(np.full(3, loss), weights)
    np.testing.assert_array_equal(actual, weights)
    assert not actual.flags.writeable and not np.shares_memory(actual, weights)


def test_zero_prior_mass_remains_zero_even_for_best_loss():
    actual = update(np.array([-1e308, 3.0, 0.0]), np.array([0.0, 0.5, 0.5]))
    assert actual[0] == 0 and actual[2] > actual[1] > 0


@pytest.mark.parametrize("rate", [0.1, 1.0, 1e308, np.nextafter(0.0, 1.0).item()])
def test_extreme_finite_losses_are_stable(rate):
    largest = np.finfo(np.float64).max
    weights = np.array([0.2, 0.3, 0.5])
    with np.errstate(all="raise"):
        actual = update(np.array([-largest, 0.0, largest]), weights, rate=rate)
    assert np.isfinite(actual).all() and (actual >= 0).all() and (actual <= 1).all()
    assert actual.sum() == pytest.approx(1.0)
    if rate >= 0.1:
        np.testing.assert_array_equal(actual, np.array([1.0, 0.0, 0.0]))
    else:
        expected = weights * np.exp(-rate * np.array([-largest, 0.0, largest]))
        expected /= expected.sum()
        np.testing.assert_allclose(actual, expected, rtol=1e-15, atol=0)


def test_large_rate_preserves_small_loss_contrasts_with_extreme_outlier():
    actual = update(np.array([0.0, 1e-300, 1e308]), rate=1e300)
    expected = np.array([1.0, np.exp(-1.0), 0.0])
    expected /= expected.sum()
    np.testing.assert_allclose(actual, expected, rtol=1e-15, atol=0)


def test_future_loss_mutation_does_not_change_earlier_actions_or_coefficients():
    def trajectory(losses):
        weights, last, actions, coefficients = None, None, [], []
        for i in range(4):
            decision = DECISION + timedelta(days=31 * i)
            if i:
                available = decision - timedelta(days=1)
                weights = update(
                    losses[i - 1],
                    weights,
                    decision_at=decision,
                    completed_loss_available_at=available,
                    last_feedback_at=last,
                )
                last = available
            actions.append(s.project_target(np.array([0.1, 0.9]), weights))
            coefficients.append(None if weights is None else weights.copy())
        return actions, coefficients

    losses = np.array([[0.0, 1.0], [2.0, 0.0], [1.0, -1.0]])
    changed = losses.copy()
    changed[-1] = [100.0, -100.0]
    before, after = trajectory(losses), trajectory(changed)
    assert before[0][:3] == after[0][:3] and before[0][-1] != after[0][-1]
    for i in (1, 2):
        np.testing.assert_array_equal(before[1][i], after[1][i])


@pytest.mark.parametrize(
    "available,last,reason",
    [
        (DECISION, None, "feedback_not_prior"),
        (DECISION + timedelta(seconds=1), None, "feedback_not_prior"),
        (FEEDBACK, FEEDBACK, "feedback_stale"),
        (FEEDBACK, FEEDBACK + timedelta(seconds=1), "feedback_stale"),
    ],
)
def test_rejected_feedback_does_not_mutate_or_block_next_valid_update(available, last, reason):
    weights, losses = np.array([0.4, 0.6]), np.array([1.0, 0.0])
    before = weights.copy(), losses.copy()
    with pytest.raises(ValueError, match=reason):
        update(losses, weights, completed_loss_available_at=available, last_feedback_at=last)
    np.testing.assert_array_equal(weights, before[0])
    np.testing.assert_array_equal(losses, before[1])
    next_available = DECISION + timedelta(days=1)
    actual = update(
        losses,
        weights,
        completed_loss_available_at=next_available,
        decision_at=next_available + timedelta(seconds=1),
        last_feedback_at=FEEDBACK,
    )
    assert actual[1] > weights[1]


def test_successive_update_requires_new_feedback_and_explicit_watermark():
    losses = np.array([0.0, 1.0])
    first = update(losses)
    with pytest.raises(ValueError, match="feedback_stale"):
        update(losses, first, last_feedback_at=FEEDBACK)
    second = update(
        losses,
        first,
        completed_loss_available_at=FEEDBACK + timedelta(seconds=1),
        last_feedback_at=FEEDBACK,
    )
    assert second[0] > first[0]
    with pytest.raises(TypeError):
        s.update_weights(
            losses, rate=0.1, completed_loss_available_at=FEEDBACK, decision_at=DECISION
        )


@pytest.mark.parametrize(
    "field", ["completed_loss_available_at", "decision_at", "last_feedback_at"]
)
@pytest.mark.parametrize(
    "bad",
    [
        DECISION.replace(tzinfo=None),
        DECISION.astimezone(timezone(timedelta(hours=9))),
        "2024-03-01",
        0,
    ],
)
def test_timestamps_require_aware_utc(field, bad):
    with pytest.raises(ValueError, match="_utc"):
        update(np.array([0.0, 1.0]), **{field: bad})


@pytest.mark.parametrize("kind", ["targets", "losses", "weights"])
@pytest.mark.parametrize(
    "bad",
    [
        [],
        [0.0, 1.0],
        np.array([], dtype="float64"),
        np.array([[0.0, 1.0]]),
        np.array([0, 1]),
        np.array([False, True]),
        np.array([0.0, 1.0], dtype="float32"),
        np.array([0.0, 1.0], dtype=object),
        np.array([0.0, np.nan]),
        np.array([0.0, np.inf]),
    ],
)
def test_vectors_reject_invalid_shapes_types_and_nonfinite_values(kind, bad):
    with pytest.raises(ValueError):
        if kind == "targets":
            s.project_target(bad)
        elif kind == "losses":
            update(bad)
        else:
            s.project_target(np.array([0.0, 1.0]), bad)


@pytest.mark.parametrize("bad", [np.array([-0.01, 1.01]), np.array([0.0, 1.01])])
def test_projection_rejects_out_of_range_targets(bad):
    with pytest.raises(ValueError, match="targets_domain"):
        s.project_target(bad)


@pytest.mark.parametrize(
    "bad",
    [
        np.array([1.0]),
        np.array([0.0, 0.0]),
        np.array([0.2, 0.2]),
        np.array([-0.1, 1.1]),
        np.array([0.5, 0.50000001]),
    ],
)
@pytest.mark.parametrize("operation", ["project", "update"])
def test_weights_require_matching_simplex(bad, operation):
    with pytest.raises(ValueError, match="weights_simplex"):
        if operation == "project":
            s.project_target(np.array([0.0, 1.0]), bad)
        else:
            update(np.array([0.0, 1.0]), bad)


@pytest.mark.parametrize(
    "bad", [0.0, -0.1, float("nan"), float("inf"), True, 1, ".1", np.float64(0.1)]
)
def test_rate_must_be_explicit_positive_finite_float(bad):
    with pytest.raises(ValueError, match="rate_finite_positive"):
        update(np.array([0.0, 1.0]), rate=bad)


def test_module_imports_only_datetime_and_numpy_without_io_or_models():
    tree = ast.parse(Path(s.__file__).read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imports == {"__future__", "datetime", "numpy"}

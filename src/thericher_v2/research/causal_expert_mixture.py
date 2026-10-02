"""Pure exponential-loss/Hedge-style adaptation, not BOA reproduction or NAV accounting."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _vector(value, name):
    _require(
        isinstance(value, np.ndarray)
        and value.dtype == np.dtype("float64")
        and value.ndim == 1
        and value.size > 0,
        name + "_float64_vector",
    )
    _require(np.isfinite(value).all(), name + "_nonfinite")
    return value


def _simplex(weights, count):
    values = np.full(count, 1.0 / count) if weights is None else _vector(weights, "weights")
    _require(
        values.shape == (count,)
        and ((values >= 0) & (values <= 1)).all()
        and abs(float(values.sum()) - 1.0) <= 1e-12,
        "weights_simplex",
    )
    return values / values.sum()


def _utc(value, name):
    _require(
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0),
        name + "_utc",
    )


def project_target(expert_targets, weights=None):
    """Convex target only; finite float64 vectors, default uniform coefficients."""
    targets = _vector(expert_targets, "targets")
    _require(((targets >= 0) & (targets <= 1)).all(), "targets_domain")
    return float(np.clip(np.dot(_simplex(weights, len(targets)), targets), 0.0, 1.0))


def update_weights(
    completed_losses,
    weights=None,
    *,
    rate,
    completed_loss_available_at,
    decision_at,
    last_feedback_at,
):
    """Apply w*exp(-rate*loss) using strictly prior, newly available feedback.

    Caller declares one positive finite float rate (e.g. 0.1), attests completion,
    and advances its watermark to completed_loss_available_at only after success.
    Inputs are unchanged; returned coefficients are read-only. No cost/NAV inference.
    """
    losses = _vector(completed_losses, "losses")
    prior = _simplex(weights, len(losses))
    _require(type(rate) is float and np.isfinite(rate) and rate > 0, "rate_finite_positive")
    _utc(completed_loss_available_at, "feedback")
    _utc(decision_at, "decision")
    _require(completed_loss_available_at < decision_at, "feedback_not_prior")
    if last_feedback_at is not None:
        _utc(last_feedback_at, "watermark")
        _require(last_feedback_at < completed_loss_available_at, "feedback_stale")
    active = prior > 0
    supported_losses = losses[active]
    minimum = supported_losses.min()
    if (supported_losses == minimum).all():
        prior.setflags(write=False)
        return prior
    with np.errstate(over="ignore", under="ignore", invalid="raise"):
        difference = supported_losses - minimum
        penalty = rate * difference
        # Opposite-sign extremes can overflow the difference even with a tiny rate.
        wide = np.isinf(difference)
        penalty[wide] = rate * supported_losses[wide] - rate * minimum
        logits = np.log(prior[active]) - penalty
        logits -= logits.max()
        result = np.zeros(len(losses), dtype=np.float64)
        result[active] = np.exp(logits)
        result /= result.sum()
    result.setflags(write=False)
    return result

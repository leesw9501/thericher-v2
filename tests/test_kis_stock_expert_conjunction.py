"""Manufactured seals only: no market, model, callback or broker access."""

import math
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.research import kis_pooled_equity_components as core
from thericher_v2.research import kis_stock_expert_conjunction as conjunction
from thericher_v2.research import kis_stock_score_replay as score

KEYS = tuple(f"opaque-{i:03}" for i in range(12))


def snapshot(count=12):
    return core.EligibilitySnapshot(
        61,
        date(2030, 1, 1),
        date(2030, 1, 2),
        tuple(core.FeatureRow(key, ((0.0,) * 20,) * 2, (0.0,) * 3, 0.0) for key in KEYS[:count]),
        KEYS[count:],
        datetime(2030, 1, 1, 20, tzinfo=UTC),
        datetime(2030, 1, 2, 14, tzinfo=UTC),
        datetime(2030, 1, 2, 20, tzinfo=UTC),
    )


def inputs(count=12):
    snap = snapshot(count)
    baseline = score.seal_scores(
        snap, (), {key: float(i) for i, key in enumerate(snap.eligible_keys)}, arm="tcn20"
    )
    binary = conjunction.ExpertValuesSeal(
        snap, "binary60", tuple((key, 0.75) for key in snap.eligible_keys)
    )
    signed = conjunction.ExpertValuesSeal(
        snap, "signed60", tuple((key, 0.25) for key in snap.eligible_keys)
    )
    return baseline, binary, signed


def value_at(seal, key, value):
    return replace(seal, values=tuple((k, value if k == key else v) for k, v in seal.values))


def test_all_pass_keeps_exact_original_weights_and_ranking():
    baseline, binary, signed = inputs()
    result = conjunction.conjoin_experts(baseline, binary, signed)
    assert result.baseline == baseline
    assert result.weights == baseline.weights
    assert result.baseline.ranked_keys == tuple(reversed(KEYS))
    assert all(weight == Fraction(1, 10) for _, weight in result.weights)
    assert not hasattr(result, "binary") and not hasattr(result, "signed")


@pytest.mark.parametrize(
    ("probability", "payoff", "passes"),
    [
        (0.5, 1.0, False),
        (math.nextafter(0.5, 1.0), math.nextafter(0.0, 1.0), True),
        (math.nextafter(0.5, 0.0), 1.0, False),
        (1.0, 0.0, False),
        (1.0, -0.0, False),
        (1.0, -2.0, False),
        (0.0, 1.0, False),
        (1.0, 1e300, True),
    ],
)
def test_strict_thresholds_no_clipping_or_implied_price(probability, payoff, passes):
    baseline, binary, signed = inputs()
    key = KEYS[-1]
    result = conjunction.conjoin_experts(
        baseline, value_at(binary, key, probability), value_at(signed, key, payoff)
    )
    assert (key in dict(result.weights)) is passes
    assert result.weights == tuple(pair for pair in baseline.weights if pair[0] != key or passes)


def test_rejected_slots_never_replaced_by_unranked_passing_peers():
    baseline, binary, signed = inputs()
    binary = replace(binary, values=tuple((key, 1.0 if key == KEYS[0] else 0.0) for key in KEYS))
    result = conjunction.conjoin_experts(baseline, binary, signed)
    assert result.weights == ()
    assert result.safe_facts()["all_cash"] is True
    assert result.baseline.weights == baseline.weights


@pytest.mark.parametrize("count", [0, 1, 9])
def test_insufficient_original_peers_keep_none_not_empty_cash(count):
    result = conjunction.conjoin_experts(*inputs(count))
    assert result.weights is None
    assert result.safe_facts()["accepted_slot_count"] is None
    assert result.safe_facts()["all_cash"] is None
    assert result.safe_facts()["reason"] == "fewer_than_10_keep_inventory"


@pytest.mark.parametrize("kind", ["binary60", "signed60"])
@pytest.mark.parametrize(
    "value", [True, 1, Decimal("0.5"), float("nan"), float("inf"), -float("inf")]
)
def test_exact_finite_float_values_required(kind, value):
    snap = snapshot()
    values = tuple((key, value if i == 0 else 0.75) for i, key in enumerate(KEYS))
    with pytest.raises(ValueError, match="finite_float_expert_values_required"):
        conjunction.ExpertValuesSeal(snap, kind, values)


@pytest.mark.parametrize("value", [-0.001, 1.001])
def test_binary_probability_range(value):
    _, binary, _ = inputs()
    with pytest.raises(ValueError, match="binary_probability_range"):
        value_at(binary, KEYS[0], value)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "duplicate", "reversed", "list", "pair_list"]
)
def test_full_ordered_peers_required_even_outside_top_ten(mutation):
    _, binary, _ = inputs()
    values = binary.values
    altered = {
        "missing": values[1:],
        "extra": (*values, ("foreign", 0.75)),
        "duplicate": (values[0], *values[:-1]),
        "reversed": tuple(reversed(values)),
        "list": list(values),
        "pair_list": (list(values[0]), *values[1:]),
    }[mutation]
    with pytest.raises(ValueError, match="expert_exact_ordered_peers_required"):
        replace(binary, values=altered)


@pytest.mark.parametrize(
    "field",
    [
        "entry_index",
        "decision_session",
        "entry_session",
        "decision_at",
        "entry_open_at",
        "target_close_at",
        "rows",
    ],
)
def test_same_keys_do_not_authorize_foreign_calendar_clock_or_features(field):
    baseline, binary, signed = inputs()
    snap = binary.snapshot
    changes = {
        "entry_index": 62,
        "decision_session": snap.decision_session - timedelta(days=1),
        "entry_session": snap.entry_session + timedelta(days=1),
        "decision_at": snap.decision_at - timedelta(seconds=1),
        "entry_open_at": snap.entry_open_at + timedelta(seconds=1),
        "target_close_at": snap.target_close_at + timedelta(seconds=1),
        "rows": (replace(snap.rows[0], component_score=0.1), *snap.rows[1:]),
    }
    foreign = replace(binary, snapshot=replace(snap, **{field: changes[field]}))
    with pytest.raises(ValueError, match="expert_snapshot_binding"):
        conjunction.conjoin_experts(baseline, foreign, signed)


def test_kinds_cannot_swap_or_alias_and_other_score_arms_rejected():
    baseline, binary, signed = inputs()
    with pytest.raises(ValueError, match="expert_kind_binding"):
        conjunction.conjoin_experts(baseline, signed, binary)
    with pytest.raises(ValueError, match="expert_kind"):
        replace(binary, kind="binary20")
    with pytest.raises(ValueError, match="original_tcn20_seal_required"):
        conjunction.conjoin_experts(replace(baseline, arm="tcn10"), binary, signed)
    with pytest.raises(ValueError, match="bound_expert_seals_required"):
        conjunction.conjoin_experts(baseline, binary.values, signed)


def test_immutable_owned_seals_and_result_hide_private_floats():
    baseline, binary, signed = inputs()
    result = conjunction.conjoin_experts(baseline, binary, signed)
    assert result.baseline is not baseline
    assert result.baseline.snapshot is not baseline.snapshot
    assert binary.snapshot is not baseline.snapshot
    for obj, name, value in ((binary, "values", ()), (result, "weights", ())):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, name, value)
    assert "0.75" not in repr(binary) and "scores" not in repr(result)
    assert all(type(v) is not float for v in result.safe_facts().values())


def test_all_score_ties_keep_original_lexical_basket():
    baseline, binary, signed = inputs()
    baseline = score.seal_scores(baseline.snapshot, (), dict.fromkeys(KEYS, 1.0), arm="tcn20")
    result = conjunction.conjoin_experts(baseline, binary, signed)
    assert result.weights == tuple((key, Fraction(1, 10)) for key in KEYS[:10])


def test_forged_baseline_revalidated_and_errors_are_categorical():
    baseline, binary, signed = inputs()
    object.__setattr__(baseline, "weights", ((KEYS[-1], Fraction(1)),))
    with pytest.raises(ValueError, match="^fixed_top10_weights_required$"):
        conjunction.conjoin_experts(baseline, binary, signed)


def test_forged_expert_revalidated_before_keep_result():
    baseline, binary, signed = inputs(9)
    object.__setattr__(binary, "values", ())
    with pytest.raises(ValueError, match="expert_exact_ordered_peers_required"):
        conjunction.conjoin_experts(baseline, binary, signed)

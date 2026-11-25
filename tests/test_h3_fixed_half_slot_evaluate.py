from dataclasses import asdict, replace
from datetime import date
from fractions import Fraction

import pytest

from test_h3_dec4_fixed_half_reader import case, setup_owner  # noqa: F401
from test_prospective_h3_marks import _panel
from thericher_v2.ops.h3_fixed_half_slot_evaluate import evaluate_dec4_fixed_half_slot
from thericher_v2.research.prospective_h3_block import reduce_prospective_h3_block
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import project_prospective_h3_marks

_DEC4 = H3Interval(date(2026, 12, 4), date(2026, 12, 9))
_NOV30 = H3Interval(date(2026, 11, 30), date(2026, 12, 3))


def _marks(interval):
    return project_prospective_h3_marks(_panel(interval.expiry), interval)


@pytest.fixture
def inputs(case):  # noqa: F811
    scores = [1.0] + [0.0] * 16
    case.publish(SELF=scores, OLD60=scores, BLEND=scores)
    return case.read(), _marks(_DEC4)


def test_native_synthetic_replay_feeds_block_reducer(inputs):
    replay = evaluate_dec4_fixed_half_slot(*inputs)
    buy = Fraction(400, 13601)
    sell = buy * Fraction(159, 156)
    fees = (buy + sell) / 400
    assert replay.model.entry_notional == replay.matched_gross_ew.entry_notional == buy
    assert replay.model.exit_notional == sell
    assert replay.model.fees == fees
    assert replay.model.growth == sell - buy - fees
    assert replay.matched_gross_ew.fees == (buy + replay.matched_gross_ew.exit_notional) / 400
    assert replay.cash.growth == replay.cash.fees == 0

    block = reduce_prospective_h3_block([replay])
    assert block.admitted_count == 1 and block.comparison is None
    assert tuple(slot.status for slot in block.slots) == (
        "absent",
        "scored",
        "absent",
        "absent",
        "absent",
    )
    assert block.slots[1].interval == _DEC4 and block.slots[1].replay is replay


def test_native_no_signal_is_not_an_absent_slot(inputs):
    forecast, marks = inputs
    replay = evaluate_dec4_fixed_half_slot(replace(forecast, blend_scores=(0.0,) * 17), marks)
    slot = reduce_prospective_h3_block([replay]).slots[1]
    assert slot.status == "no_signal"
    assert replay.model == replay.matched_gross_ew == replay.cash


def test_rejects_other_cohort_even_if_pair_matches(inputs):
    forecast, _ = inputs
    marks = _marks(_NOV30)
    with pytest.raises(ValueError, match="h3_replay_interval_invalid"):
        evaluate_dec4_fixed_half_slot(forecast, marks)
    with pytest.raises(ValueError, match="h3_fixed_half_slot_interval"):
        evaluate_dec4_fixed_half_slot(replace(forecast, interval=_NOV30), marks)


def test_rejects_wrong_inner_session_with_exact_endpoints(inputs):
    forecast, marks = inputs
    wrong = replace(marks, sessions=(marks.sessions[0], date(2026, 12, 5), *marks.sessions[2:]))
    with pytest.raises(ValueError, match="h3_replay_interval_invalid"):
        evaluate_dec4_fixed_half_slot(forecast, wrong)


@pytest.mark.parametrize("reorder", ["forecast", "marks", "both"])
def test_rejects_noncanonical_symbol_order(inputs, reorder):
    forecast, marks = inputs
    if reorder in ("forecast", "both"):
        forecast = replace(forecast, forecast_symbols=forecast.forecast_symbols[::-1])
    if reorder in ("marks", "both"):
        marks = replace(marks, symbols=marks.symbols[::-1])
    with pytest.raises(ValueError, match="h3_replay_axis_invalid"):
        evaluate_dec4_fixed_half_slot(forecast, marks)


def test_requires_typed_inputs_and_exact_marks(inputs):
    forecast, marks = inputs
    with pytest.raises(ValueError, match="h3_fixed_half_slot_input_type"):
        evaluate_dec4_fixed_half_slot(asdict(forecast), marks)
    with pytest.raises(ValueError, match="h3_fixed_half_slot_input_type"):
        evaluate_dec4_fixed_half_slot(forecast, asdict(marks))
    with pytest.raises(ValueError, match="h3_replay_marks_invalid"):
        evaluate_dec4_fixed_half_slot(forecast, replace(marks, closes=marks.closes[:-1]))

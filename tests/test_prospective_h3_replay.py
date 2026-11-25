from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS, H3DailyPanel, H3DailyPanelPlan
from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import (
    ProspectiveH3Marks,
    project_prospective_h3_marks,
)
from thericher_v2.research.prospective_h3_replay import replay_prospective_h3_cohort

SYMBOLS = tuple(symbol for symbol, _ in NET25_H3_AXIS[:17])
SESSIONS = (date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 2), date(2026, 12, 3))
INTERVAL = H3Interval(SESSIONS[0], SESSIONS[-1])
SIGNAL = (0.125, 0.0) + (-0.125,) * 15


def _row(first, other):
    return (Decimal(first),) + (Decimal(other),) * 16


@pytest.fixture
def marks():
    entry = _row(100, 200)
    return ProspectiveH3Marks(
        SESSIONS, SYMBOLS, (entry, _row(50, 200), entry, _row(150, 180)), (entry,) * 3
    )


def _replay(marks, scores=SIGNAL, symbols=SYMBOLS, interval=INTERVAL):
    return replay_prospective_h3_cohort(
        interval, marks, forecast_symbols=symbols, blend_scores=scores
    )


def test_funded_ew_matches_entry_but_exits_its_own_quantities(marks):
    result = _replay(marks)
    assert result.status == "scored"
    buy = Fraction(400, 13601)  # (1/34) / (1 + 1/(400*34))
    for book, sell in (
        (result.model, buy * Fraction(3, 2)),
        (result.matched_gross_ew, buy * Fraction(159, 170)),
    ):
        assert book.entry_notional == buy
        assert book.exit_notional == sell
        assert book.turnover == buy + sell
        assert book.fees == (buy + sell) / 400
        assert book.growth == sell - buy - book.fees
    assert result.model.turnover != result.matched_gross_ew.turnover
    assert result.cash.nav == (1,) * 11
    assert result.cash.growth == result.cash.fees == result.cash.turnover == 0
    assert result.cash.drawdown == 0


def test_sampled_nav_preserves_gaps_and_pre_post_sale_fee(marks):
    book = _replay(marks).model
    buy, sell = book.entry_notional, book.exit_notional
    cash = 1 - buy * Fraction(401, 400)
    at_entry, trough, before_sale = cash + buy, cash + buy / 2, cash + sell
    assert book.nav == (
        1,
        at_entry,
        at_entry,
        trough,
        trough,
        at_entry,
        at_entry,
        at_entry,
        at_entry,
        before_sale,
        before_sale - sell / 400,
    )
    assert book.drawdown == 1 - trough
    assert book.peak_sampled_gross == book.peak_issuer_nav_share == sell / before_sale
    assert book.mean_sampled_gross == (6 * buy / at_entry + buy / trough + sell / before_sale) / 11


def test_all_positive_at_cap_is_already_equal_weight(marks):
    result = _replay(marks, (0.5,) * 17)
    assert result.model == result.matched_gross_ew
    assert result.model.entry_notional == Fraction(400, 801)


def test_valid_no_signal_is_distinct_from_missing(marks):
    scores = (Decimal("-0"), 0.0) + (-1.0,) * 15
    result = _replay(marks, scores)
    assert result.status == "no_signal"
    assert result.model == result.matched_gross_ew == result.cash
    invalid = replace(marks, closes=(marks.closes[0][:-1], *marks.closes[1:]))
    with pytest.raises(ValueError, match="h3_replay_marks_invalid"):
        _replay(invalid, scores)


@pytest.mark.parametrize("value", [Decimal(0), Decimal("NaN"), Decimal("Infinity"), None])
def test_invalid_mark_on_unselected_name_withholds_pair(marks, value):
    invalid = replace(marks, opens=(*marks.opens[:3], (*marks.opens[3][:-1], value)))
    with pytest.raises(ValueError, match="h3_replay_marks_invalid"):
        _replay(invalid)


@pytest.mark.parametrize("scores", [SIGNAL[:-1], (float("nan"), *SIGNAL[1:]), (True, *SIGNAL[1:])])
def test_incomplete_or_nonfinite_scores_are_not_no_signal(marks, scores):
    with pytest.raises(ValueError, match="h3_replay_scores_invalid"):
        _replay(marks, scores)


def test_rejects_wrong_session_or_symbol_alignment(marks):
    with pytest.raises(ValueError, match="h3_replay_interval_invalid"):
        _replay(marks, interval=H3Interval(date(2026, 12, 4), date(2026, 12, 9)))
    with pytest.raises(ValueError, match="h3_replay_interval_invalid"):
        _replay(replace(marks, sessions=(SESSIONS[0], SESSIONS[2], SESSIONS[1], SESSIONS[3])))
    with pytest.raises(ValueError, match="h3_replay_axis_invalid"):
        _replay(marks, symbols=SYMBOLS[::-1])
    with pytest.raises(ValueError, match="h3_replay_axis_invalid"):
        _replay(replace(marks, symbols=SYMBOLS[::-1]))


@pytest.mark.parametrize(("entry", "expiry"), [(30, 3), (4, 9), (10, 15), (16, 21), (22, 28)])
def test_real_projector_handoff_on_each_frozen_cohort(entry, expiry):
    interval = H3Interval(date(2026, 11 if entry == 30 else 12, entry), date(2026, 12, expiry))
    plan = H3DailyPanelPlan(NET25_H3_AXIS, interval.expiry)
    rows = tuple(
        (KisPaperDailyRawRow(day.strftime("%Y%m%d"), "100", "101", "99", "100", "1"),)
        * len(plan.axis)
        for day in plan.sessions
    )
    marks = project_prospective_h3_marks(H3DailyPanel(plan, rows), interval)
    result = _replay(marks, interval=interval)
    assert result.model.entry_notional == result.matched_gross_ew.entry_notional
    assert result.model.growth == result.matched_gross_ew.growth == -result.model.fees < 0

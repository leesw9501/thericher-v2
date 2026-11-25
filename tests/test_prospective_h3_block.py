from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest

from thericher_v2.research.prospective_h3_block import reduce_prospective_h3_block
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import ProspectiveH3Marks
from thericher_v2.research.prospective_h3_replay import replay_prospective_h3_cohort

_SESSIONS = (
    (date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 2), date(2026, 12, 3)),
    (date(2026, 12, 4), date(2026, 12, 7), date(2026, 12, 8), date(2026, 12, 9)),
    (date(2026, 12, 10), date(2026, 12, 11), date(2026, 12, 14), date(2026, 12, 15)),
    (date(2026, 12, 16), date(2026, 12, 17), date(2026, 12, 18), date(2026, 12, 21)),
    (date(2026, 12, 22), date(2026, 12, 23), date(2026, 12, 24), date(2026, 12, 28)),
)
_SYMBOLS = tuple("AAPL AMD AMZN GOOGL META MSFT NVDA TSLA JPM JNJ XOM PG KO HD V DIS UNH".split())


@pytest.fixture
def replays():
    entry = (Decimal(100),) * 17
    return tuple(
        replay_prospective_h3_cohort(
            H3Interval(days[0], days[-1]),
            ProspectiveH3Marks(
                days, _SYMBOLS, (entry,) * 3 + ((Decimal(exit_), *entry[1:]),), (entry,) * 3
            ),
            forecast_symbols=_SYMBOLS,
            blend_scores=(signal,) + (0.0,) * 16,
        )
        for days, exit_, signal in zip(
            _SESSIONS, (150, 25, 60, 120, 100), (1.0, 0.0, 1.0, 1.0, 1.0), strict=True
        )
    )


def test_missing_slots_do_not_become_flat_cohorts(replays):
    empty = reduce_prospective_h3_block(())
    assert empty.admitted_count == 0
    assert empty.comparison is None
    assert [slot.status for slot in empty.slots] == ["absent"] * 5

    partial = reduce_prospective_h3_block(reversed(replays[:3]))
    assert tuple(slot.interval for slot in partial.slots) == tuple(r.interval for r in replays)
    assert [slot.status for slot in partial.slots] == [
        "scored",
        "no_signal",
        "scored",
        "absent",
        "absent",
    ]
    assert partial.slots[1].replay is replays[1]
    assert partial.slots[1].replay.model.growth == 0
    assert partial.slots[-1].replay is None
    assert partial.admitted_count == 3
    assert partial.comparison is None


@pytest.mark.parametrize("count", [4, 5])
def test_descriptive_comparison_is_paired_net_growth_per_admitted_date(replays, count):
    block = reduce_prospective_h3_block(reversed(replays[:count]))
    assert block.admitted_count == count
    assert block.comparison is not None

    # One funded name: model captures its full move; EW captures 1/17.
    buy = Fraction(400, 13601)
    total_move = Fraction(1, 2) - Fraction(2, 5) + Fraction(1, 5)
    total_model_sell = buy * (count - 1 + total_move)
    assert block.comparison.mean_model_minus_matched_gross_ew == (
        buy * total_move * Fraction(16, 17) * Fraction(399, 400) / count
    )
    assert (
        block.comparison.mean_model_minus_cash
        == (buy * total_move - (buy * (count - 1) + total_model_sell) / 400) / count
    )
    assert all(slot.replay is r for slot, r in zip(block.slots[:count], replays, strict=False))


@pytest.mark.parametrize(
    "interval",
    [
        H3Interval(date(2026, 11, 9), date(2026, 11, 12)),
        H3Interval(date(2026, 12, 4), date(2026, 12, 10)),
        H3Interval(datetime(2026, 12, 4), date(2026, 12, 9)),
        (date(2026, 12, 4), date(2026, 12, 9)),
    ],
)
def test_rejects_off_block_or_non_exact_intervals(replays, interval):
    with pytest.raises(ValueError, match="h3_block_interval_invalid"):
        reduce_prospective_h3_block([replace(replays[0], interval=interval)])


def test_rejects_duplicate_and_invalid_replays(replays):
    with pytest.raises(ValueError, match="h3_block_interval_duplicate"):
        reduce_prospective_h3_block([replays[1], replays[1]])
    with pytest.raises(ValueError, match="h3_block_replay_invalid"):
        reduce_prospective_h3_block([replace(replays[1], status="absent")])

from dataclasses import asdict, replace
from datetime import date, datetime

import pytest

from test_prospective_h3_block import replays  # noqa: F401
from thericher_v2.ops.h3_fixed_half_block_evaluate import evaluate_h3_fixed_half_block
from thericher_v2.research.prospective_h3_block import H3BlockSlot, reduce_prospective_h3_block
from thericher_v2.research.prospective_h3_calendar import H3Interval


@pytest.fixture
def slots(replays):  # noqa: F811
    return tuple(H3BlockSlot(replay.interval, replay) for replay in replays)


@pytest.mark.parametrize("missing", [(0, 1, 2, 3, 4), (2, 4), (2,), ()])
def test_preserves_frozen_slots_and_native_descriptive_result(slots, missing):
    handoff = tuple(
        replace(slot, replay=None) if index in missing else slot for index, slot in enumerate(slots)
    )
    result = evaluate_h3_fixed_half_block(handoff)

    assert result.block == reduce_prospective_h3_block(
        slot.replay for slot in handoff if slot.replay is not None
    )
    assert result.block.slots == handoff
    assert result.unmeasured_intervals == tuple(slots[index].interval for index in missing)
    assert result.block.admitted_count == 5 - len(missing)
    assert (result.block.comparison is not None) == (len(missing) <= 1)
    assert result.block.slots[1].status == ("absent" if 1 in missing else "no_signal")
    assert all(
        left.replay is right.replay for left, right in zip(result.block.slots, handoff, strict=True)
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda slots: slots[1:],
        lambda slots: (*slots, slots[-1]),
        lambda slots: slots[::-1],
        lambda slots: (slots[1], *slots[1:]),
        lambda slots: (asdict(slots[0]), *slots[1:]),
        lambda slots: (replace(slots[0], interval=tuple(slots[0].interval)), *slots[1:]),
        lambda slots: (
            replace(
                slots[0],
                interval=H3Interval(date(2026, 11, 9), date(2026, 11, 12)),
                replay=None,
            ),
            *slots[1:],
        ),
        list,
    ],
)
def test_rejects_inexact_schedule(slots, change):
    with pytest.raises(ValueError, match="h3_fixed_half_block_schedule"):
        evaluate_h3_fixed_half_block(change(slots))


def test_rejects_misrouted_replay_even_when_its_own_slot_is_unmeasured(slots):
    first, second, *rest = slots
    with pytest.raises(ValueError, match="h3_fixed_half_block_binding"):
        evaluate_h3_fixed_half_block(
            (replace(first, replay=second.replay), replace(second, replay=None), *rest)
        )


@pytest.mark.parametrize(
    "change",
    [
        asdict,
        lambda replay: replace(replay, interval=tuple(replay.interval)),
        lambda replay: replace(
            replay, interval=H3Interval(datetime(2026, 11, 30), replay.interval.expiry)
        ),
    ],
)
def test_rejects_untyped_replay_or_interval(slots, change):
    bad = replace(slots[0], replay=change(slots[0].replay))
    with pytest.raises(ValueError, match="h3_fixed_half_block_binding"):
        evaluate_h3_fixed_half_block((bad, *slots[1:]))


def test_invalid_native_status_is_not_absence(slots):
    bad = replace(slots[0], replay=replace(slots[0].replay, status="absent"))
    with pytest.raises(ValueError, match="h3_block_replay_invalid"):
        evaluate_h3_fixed_half_block((bad, *slots[1:]))

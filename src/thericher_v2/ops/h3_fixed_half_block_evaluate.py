"""Bind the fixed-half block-end caller's ordered handoff to the native reducer."""

from dataclasses import dataclass
from datetime import date

from thericher_v2.research.prospective_h3_block import (
    H3BlockSlot,
    ProspectiveH3Block,
    reduce_prospective_h3_block,
)
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_replay import ProspectiveH3Replay

_FROZEN_SLOTS = reduce_prospective_h3_block(()).slots


@dataclass(frozen=True)
class H3FixedHalfBlockEvaluation:
    """Native per-date books and optional descriptive comparison, not promotion evidence."""

    block: ProspectiveH3Block

    @property
    def unmeasured_intervals(self) -> tuple[H3Interval, ...]:
        return tuple(slot.interval for slot in self.block.slots if slot.replay is None)


def evaluate_h3_fixed_half_block(
    slots: tuple[H3BlockSlot, ...],
) -> H3FixedHalfBlockEvaluation:
    """Require the entire frozen schedule, with explicit None for an unadmitted slot.

    The caller owns block-end timing and independent provenance/admission. This
    pure join does not read outcomes or turn an invalid handoff into a missing date.
    """
    if type(slots) is not tuple or len(slots) != len(_FROZEN_SLOTS):
        raise ValueError("h3_fixed_half_block_schedule")

    admitted: list[ProspectiveH3Replay] = []
    for slot, frozen in zip(slots, _FROZEN_SLOTS, strict=True):
        if type(slot) is not H3BlockSlot or not _matches(slot.interval, frozen.interval):
            raise ValueError("h3_fixed_half_block_schedule")
        replay = slot.replay
        if replay is None:
            continue
        if type(replay) is not ProspectiveH3Replay or not _matches(
            replay.interval, frozen.interval
        ):
            raise ValueError("h3_fixed_half_block_binding")
        admitted.append(replay)

    return H3FixedHalfBlockEvaluation(reduce_prospective_h3_block(admitted))


def _matches(interval: H3Interval, frozen: H3Interval) -> bool:
    return (
        type(interval) is H3Interval
        and type(interval.entry) is date
        and type(interval.expiry) is date
        and interval == frozen
    )

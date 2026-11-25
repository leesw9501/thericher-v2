"""Block-end readout of already admitted frozen fixed-half H3 replays."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Literal

from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_replay import ProspectiveH3Replay

_FROZEN_INTERVALS = tuple(
    H3Interval(date.fromisoformat(entry), date.fromisoformat(expiry))
    for entry, expiry in (
        ("2026-11-30", "2026-12-03"),
        ("2026-12-04", "2026-12-09"),
        ("2026-12-10", "2026-12-15"),
        ("2026-12-16", "2026-12-21"),
        ("2026-12-22", "2026-12-28"),
    )
)


@dataclass(frozen=True)
class H3BlockSlot:
    interval: H3Interval
    replay: ProspectiveH3Replay | None

    @property
    def status(self) -> Literal["absent", "no_signal", "scored"]:
        return "absent" if self.replay is None else self.replay.status


@dataclass(frozen=True)
class H3DescriptiveComparison:
    """Equal-date means of paired net growth differences, not block returns."""

    mean_model_minus_matched_gross_ew: Fraction
    mean_model_minus_cash: Fraction


@dataclass(frozen=True)
class ProspectiveH3Block:
    slots: tuple[H3BlockSlot, ...]
    comparison: H3DescriptiveComparison | None

    @property
    def admitted_count(self) -> int:
        return sum(slot.replay is not None for slot in self.slots)


def reduce_prospective_h3_block(replays: Iterable[ProspectiveH3Replay]) -> ProspectiveH3Block:
    """Lay out the five frozen slots and, with >=4 admitted, compare paired net growth.

    The caller owns one-shot block-end timing, seal/target provenance and admission.
    Pass native replay results only; omit unadmitted slots. A valid no-signal
    counts as an admitted date. Original books retain per-date fees, drawdown,
    exposure and turnover. No NAV is carried between dates, and the comparison
    makes no claim of sample independence, alpha or promotion eligibility.
    """
    by_interval: dict[H3Interval, ProspectiveH3Replay] = {}
    for replay in replays:
        if type(replay) is not ProspectiveH3Replay or replay.status not in ("no_signal", "scored"):
            raise ValueError("h3_block_replay_invalid")
        interval = replay.interval
        if (
            type(interval) is not H3Interval
            or type(interval.entry) is not date
            or type(interval.expiry) is not date
            or interval not in _FROZEN_INTERVALS
        ):
            raise ValueError("h3_block_interval_invalid")
        if interval in by_interval:
            raise ValueError("h3_block_interval_duplicate")
        by_interval[interval] = replay

    slots = tuple(
        H3BlockSlot(interval, by_interval.get(interval)) for interval in _FROZEN_INTERVALS
    )
    count = len(by_interval)
    if count < 4:
        return ProspectiveH3Block(slots, None)

    comparison = H3DescriptiveComparison(
        sum(
            (r.model.growth - r.matched_gross_ew.growth for r in by_interval.values()),
            Fraction(0),
        )
        / count,
        sum((r.model.growth - r.cash.growth for r in by_interval.values()), Fraction(0)) / count,
    )
    return ProspectiveH3Block(slots, comparison)

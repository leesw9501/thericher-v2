"""Open the frozen H3 block for Engine Research's descriptive paired replay."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.ops.h3_fixed_half_block_evaluate import (
    H3FixedHalfBlockEvaluation,
    evaluate_h3_fixed_half_block,
)
from thericher_v2.research.prospective_h3_block import _FROZEN_INTERVALS, H3BlockSlot
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_replay import ProspectiveH3Replay


class H3SlotReadiness(Enum):
    READY = "ready"
    UNMEASURED = "unmeasured"
    UNOPENED = "unopened"
    LIVE = "live"
    ERROR = "error"


@dataclass(frozen=True)
class H3SlotReaderBinding:
    interval: H3Interval
    source_sha256: str
    read: Callable[[Callable[[], bool]], ProspectiveH3Replay]


def _block_release_at() -> datetime:
    expiry = max(interval.expiry for interval in _FROZEN_INTERVALS)
    session = us_equity_2026_session(expiry)
    if session is None:
        raise ValueError("h3_block_readout_calendar")
    return session.window.close_ts


# The frozen readers use this close as their earliest release, not as proof
# that the final target edition is available. Custody still gates each slot.
BLOCK_RELEASE_AT = _block_release_at()


class H3BlockReadoutError(ValueError):
    """Categorical readout failure; no reader exception text or partial book."""


def read_h3_fixed_half_block(
    bindings: tuple[H3SlotReaderBinding, ...],
    *,
    attest: Callable[[H3SlotReaderBinding], H3SlotReadiness],
    clock: Callable[[], datetime],
) -> H3FixedHalfBlockEvaluation:
    """Read each admitted slot once in order, then delegate the typed block join.

    An independent launcher prebinds the ordered sources and owns the durable
    one-shot claim. Its outcome-free attestation checks that the callable uses
    the pinned source, that one-shot authority and RO isolation still hold, and
    that the exact forecast/target owners are closed. UNMEASURED requires
    positive terminal evidence for this slot, not missing files or a failed
    reader. READY readers keep their native custody checks and call the supplied
    readiness probe at their read boundaries. Nothing here opens files itself.
    """
    if type(bindings) is not tuple or len(bindings) != len(_FROZEN_INTERVALS):
        raise H3BlockReadoutError("h3_block_readout_schedule")
    for binding, interval in zip(bindings, _FROZEN_INTERVALS, strict=True):
        if (
            type(binding) is not H3SlotReaderBinding
            or type(binding.interval) is not H3Interval
            or any(type(day) is not date for day in binding.interval)
            or binding.interval != interval
        ):
            raise H3BlockReadoutError("h3_block_readout_schedule")
        if (
            type(binding.source_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", binding.source_sha256) is None
            or not callable(binding.read)
        ):
            raise H3BlockReadoutError("h3_block_readout_source")

    last = BLOCK_RELEASE_AT

    def check_clock() -> None:
        nonlocal last
        try:
            now = clock()
            valid = type(now) is datetime and now.utcoffset() == UTC.utcoffset(None) and now >= last
        except Exception:
            raise H3BlockReadoutError("h3_block_readout_clock") from None
        if not valid:
            raise H3BlockReadoutError("h3_block_readout_clock")
        last = now

    def readiness(binding: H3SlotReaderBinding) -> H3SlotReadiness:
        check_clock()
        try:
            state = attest(binding)
        except Exception:
            raise H3BlockReadoutError("h3_block_readout_attest_error") from None
        check_clock()
        if type(state) is not H3SlotReadiness:
            raise H3BlockReadoutError("h3_block_readout_attestation")
        if state not in (H3SlotReadiness.READY, H3SlotReadiness.UNMEASURED):
            raise H3BlockReadoutError(f"h3_block_readout_{state.value}")
        return state

    def read_slot(binding: H3SlotReaderBinding, state: H3SlotReadiness) -> H3BlockSlot:
        def reader_ready() -> bool:
            if readiness(binding) is not state:
                raise H3BlockReadoutError("h3_block_readout_readiness_changed")
            return True

        reader_ready()
        if state is H3SlotReadiness.UNMEASURED:
            return H3BlockSlot(binding.interval, None)
        try:
            replay = binding.read(reader_ready)
        except H3BlockReadoutError:
            raise
        except Exception:
            raise H3BlockReadoutError("h3_block_readout_reader_error") from None
        reader_ready()
        if replay is None:
            raise H3BlockReadoutError("h3_block_readout_reader_result")
        return H3BlockSlot(binding.interval, replay)

    states = tuple(readiness(binding) for binding in bindings)
    slots = tuple(
        read_slot(binding, state) for binding, state in zip(bindings, states, strict=True)
    )
    for binding, state in zip(bindings, states, strict=True):
        if readiness(binding) is not state:
            raise H3BlockReadoutError("h3_block_readout_readiness_changed")
    return evaluate_h3_fixed_half_block(slots)

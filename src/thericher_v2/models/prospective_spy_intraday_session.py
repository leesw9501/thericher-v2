"""Pure prospective SPY regular-session input contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.market.resample import SessionWindow, resample_session_bars

from .sequence_window import (
    CausalMultiTimeframeSequenceWindow,
    SequenceWindowInputError,
    build_causal_multitimeframe_sequence_window,
)

PROSPECTIVE_SPY_INTRADAY_SESSION_RECORD_ID = "prospective-spy-intraday-session-record-v1"

_EASTERN = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_DECISION_CUTOFF = time(15, 30)
_REGULAR_CLOSE = time(16, 0)
_SOURCE_TIMEFRAME = Timeframe.M1
_LOOKBACKS = {
    Timeframe.M1: 30,
    Timeframe.M5: 6,
    Timeframe.M10: 3,
    Timeframe.H1: 2,
    Timeframe.H3: 2,
}
_TIMEFRAMES = tuple(_LOOKBACKS)
_SHA256_PREFIX = "sha256:"


class ProspectiveSpyIntradaySessionInputError(ValueError):
    """A categorical structural failure in one prospective SPY session."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        super().__init__(f"{status}: {message}")


@dataclass(frozen=True, slots=True)
class ProspectiveSpyIntradaySessionRecord:
    """One in-memory, regular-session SPY input with no provider behavior."""

    source_contract_hash: str
    contract_hash: str
    cutoff: datetime
    session: SessionWindow
    sequence_window: CausalMultiTimeframeSequenceWindow = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.session, SessionWindow):
            raise TypeError("session must be a SessionWindow")
        if not isinstance(self.sequence_window, CausalMultiTimeframeSequenceWindow):
            raise TypeError("sequence_window must be a CausalMultiTimeframeSequenceWindow")
        normalized_cutoff = _validate_regular_session_geometry(self.session, self.cutoff)
        object.__setattr__(self, "cutoff", normalized_cutoff)
        _require_sha256(self.source_contract_hash, "source_contract_hash")
        _require_sha256(self.contract_hash, "contract_hash")
        sequence_window = _revalidate_sequence_window(
            self.sequence_window,
            cutoff=normalized_cutoff,
        )
        object.__setattr__(self, "sequence_window", sequence_window)
        if sequence_window.symbol != "SPY":
            raise ValueError("prospective session sequence window must be SPY")
        if sequence_window.cutoff != normalized_cutoff:
            raise ValueError("prospective session sequence window cutoff is invalid")
        if tuple(sequence_window.windows) != _TIMEFRAMES:
            raise ValueError("prospective session sequence window timeframes are invalid")
        if {
            timeframe: len(window.bars)
            for timeframe, window in sequence_window.windows.items()
        } != _LOOKBACKS:
            raise ValueError("prospective session sequence window lookbacks are invalid")
        expected_hash = _record_contract_hash(
            source_contract_hash=self.source_contract_hash,
            session=self.session,
            cutoff=normalized_cutoff,
            sequence_window=sequence_window,
        )
        if self.contract_hash != expected_hash:
            raise ValueError("prospective session contract hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return structural input metadata without observed bar values."""

        return {
            "record_id": PROSPECTIVE_SPY_INTRADAY_SESSION_RECORD_ID,
            "source_contract_hash": self.source_contract_hash,
            "contract_hash": self.contract_hash,
            "symbol": self.sequence_window.symbol,
            "market": self.sequence_window.market,
            "timeframes": [timeframe.value for timeframe in _TIMEFRAMES],
            "session": {
                "open_ts": self.session.open_ts.isoformat(),
                "close_ts": self.session.close_ts.isoformat(),
            },
            "cutoff": self.cutoff.isoformat(),
            "sequence_window": self.sequence_window.structural_metadata(),
        }


def build_prospective_spy_intraday_session_record(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    cutoff: datetime,
    source_contract_hash: str,
) -> ProspectiveSpyIntradaySessionRecord:
    """Build the fixed 09:30-15:30 ET SPY sequence input from completed 1m bars."""

    normalized_cutoff = _validate_regular_session_geometry(session, cutoff)
    _require_sha256(source_contract_hash, "source_contract_hash")
    source_bars = _validate_source_bars(
        bars,
        session=session,
        cutoff=normalized_cutoff,
    )
    bars_by_timeframe: dict[Timeframe, tuple[Bar, ...]] = {}
    for timeframe in _TIMEFRAMES:
        resampled = resample_session_bars(source_bars, timeframe, session=session)
        if any(
            bucket_start < normalized_cutoff
            for bucket_start in resampled.skipped_bucket_starts
        ):
            raise ProspectiveSpyIntradaySessionInputError(
                "non_contiguous",
                f"{timeframe.value} has an incomplete bucket before cutoff",
            )
        bars_by_timeframe[timeframe] = resampled.bars
    try:
        sequence_window = build_causal_multitimeframe_sequence_window(
            bars_by_timeframe,
            lookbacks=_LOOKBACKS,
            cutoff=normalized_cutoff,
        )
    except SequenceWindowInputError as error:
        raise ProspectiveSpyIntradaySessionInputError(error.status, str(error)) from error
    contract_hash = _record_contract_hash(
        source_contract_hash=source_contract_hash,
        session=session,
        cutoff=normalized_cutoff,
        sequence_window=sequence_window,
    )
    return ProspectiveSpyIntradaySessionRecord(
        source_contract_hash=source_contract_hash,
        contract_hash=contract_hash,
        cutoff=normalized_cutoff,
        session=session,
        sequence_window=sequence_window,
    )


def _validate_regular_session_geometry(session: SessionWindow, cutoff: datetime) -> datetime:
    if not isinstance(session, SessionWindow):
        raise TypeError("session must be a SessionWindow")
    normalized_cutoff = require_utc(cutoff, "cutoff")
    local_open = session.open_ts.astimezone(_EASTERN)
    local_close = session.close_ts.astimezone(_EASTERN)
    if (
        local_open.weekday() >= 5
        or local_open.date() != local_close.date()
        or local_open.time() != _REGULAR_OPEN
        or local_close.time() != _REGULAR_CLOSE
        or session.duration != timedelta(hours=6, minutes=30)
    ):
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "session must be one weekday 09:30-16:00 America/New_York regular session",
        )
    expected_cutoff = datetime.combine(
        local_open.date(),
        _DECISION_CUTOFF,
        _EASTERN,
    ).astimezone(UTC)
    if normalized_cutoff != expected_cutoff:
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "cutoff must be the fixed 15:30 America/New_York decision boundary",
        )
    return normalized_cutoff


def _validate_source_bars(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    cutoff: datetime,
) -> tuple[Bar, ...]:
    source = tuple(bars)
    if not source:
        raise ProspectiveSpyIntradaySessionInputError("missing", "no 1m source bars supplied")
    if any(not isinstance(bar, Bar) for bar in source):
        raise TypeError("bars must contain Bar objects")
    if any(bar.timeframe != _SOURCE_TIMEFRAME for bar in source):
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "source bars must use the 1m timeframe",
        )
    if any(bar.symbol != "SPY" for bar in source):
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "source bars must use the SPY symbol",
        )
    markets = {bar.market for bar in source}
    if len(markets) != 1 or not next(iter(markets)).strip():
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "source bars must share one nonempty market identity",
        )
    starts = tuple(bar.start_ts for bar in source)
    if len(set(starts)) != len(starts):
        raise ProspectiveSpyIntradaySessionInputError("duplicate", "duplicate 1m bar start")
    if any(not bar.complete for bar in source):
        raise ProspectiveSpyIntradaySessionInputError(
            "incomplete",
            "source bars must all be complete",
        )
    if any(bar.start_ts >= cutoff or bar.end_ts > cutoff for bar in source):
        raise ProspectiveSpyIntradaySessionInputError(
            "future",
            "a caller may not supply a bar at or after cutoff",
        )
    if any(bar.start_ts < session.open_ts for bar in source):
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "source bars must start no earlier than the session open",
        )
    if any((bar.start_ts - session.open_ts) % _SOURCE_TIMEFRAME.duration for bar in source):
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            "source bars must align to whole minutes from the session open",
        )

    expected_starts = frozenset(
        session.open_ts + _SOURCE_TIMEFRAME.duration * offset
        for offset in range((cutoff - session.open_ts) // _SOURCE_TIMEFRAME.duration)
    )
    observed_starts = frozenset(starts)
    if unexpected_starts := observed_starts - expected_starts:
        raise ProspectiveSpyIntradaySessionInputError(
            "misaligned",
            f"source bars include {len(unexpected_starts)} unexpected session timestamps",
        )
    missing_starts = expected_starts - observed_starts
    if missing_starts:
        boundary_starts = {session.open_ts, cutoff - _SOURCE_TIMEFRAME.duration}
        status = "missing" if missing_starts & boundary_starts else "non_contiguous"
        raise ProspectiveSpyIntradaySessionInputError(
            status,
            f"source bars omit {len(missing_starts)} required 1m timestamps",
        )
    return tuple(sorted(source, key=lambda bar: bar.start_ts))


def _revalidate_sequence_window(
    sequence_window: CausalMultiTimeframeSequenceWindow,
    *,
    cutoff: datetime,
) -> CausalMultiTimeframeSequenceWindow:
    """Rebuild selected tails so a mutated record cannot bypass causal checks."""

    try:
        return build_causal_multitimeframe_sequence_window(
            {
                timeframe: window.bars
                for timeframe, window in sequence_window.windows.items()
            },
            lookbacks=_LOOKBACKS,
            cutoff=cutoff,
        )
    except (AttributeError, SequenceWindowInputError, TypeError, ValueError) as error:
        raise ValueError("prospective session sequence window is invalid") from error


def _record_contract_hash(
    *,
    source_contract_hash: str,
    session: SessionWindow,
    cutoff: datetime,
    sequence_window: CausalMultiTimeframeSequenceWindow,
) -> str:
    payload = {
        "record_id": PROSPECTIVE_SPY_INTRADAY_SESSION_RECORD_ID,
        "source_contract_hash": source_contract_hash,
        "session": {
            "open": session.open_ts.isoformat(),
            "close": session.close_ts.isoformat(),
        },
        "cutoff": cutoff.isoformat(),
        "sequence_window": sequence_window.structural_metadata(),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != len(_SHA256_PREFIX) + 64
        or not value.startswith(_SHA256_PREFIX)
        or any(character not in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")

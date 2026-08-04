"""Broker-free selection of the bounded QQQ KIS Paper runtime input window."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, TargetInputStatus, Timeframe, require_utc
from thericher_v2.data.kis_paper_intraday import (
    KisPaperPrivateIntradayLocalRetention,
    inspect_kis_paper_private_intraday_local_retention,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.us_equity_session import UsEquity2026Session, us_equity_2026_session

KIS_PAPER_INTRADAY_RUNTIME_WINDOW_SCHEMA_ID = "kis-paper-intraday-runtime-window-v1"
KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS = 90
KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M5_BARS = 18
KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M10_BARS = 9
# This deadline governs only the current QQQ runtime/Paper route.
KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE = timedelta(minutes=2)

_KIS_PAPER_QQQ_NAS_M1_CATALOG_PREFIX = "kis.paper.private.intraday.qqq.nas.m1."
_RUNTIME_WINDOW_STATUSES = frozenset(
    {
        "ready",
        "missing",
        "stale",
        "incomplete",
        "non_contiguous",
        "future",
        "misaligned",
    }
)
_RuntimeWindowStatus = Literal[
    "ready",
    "missing",
    "stale",
    "incomplete",
    "non_contiguous",
    "future",
    "misaligned",
]
_FreshnessCategory = Literal[
    "candidate_unavailable",
    "future",
    "within_budget",
    "at_budget",
    "over_budget",
]


@dataclass(frozen=True, slots=True)
class KisPaperIntradayRuntimeFreshness:
    """Source-safe freshness fact for one completed runtime-window candidate."""

    completed_window_end: datetime | None
    observed_at: datetime
    max_age: timedelta = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc_datetime(self.observed_at, "observed_at"))
        if self.completed_window_end is not None:
            object.__setattr__(
                self,
                "completed_window_end",
                _utc_datetime(self.completed_window_end, "completed_window_end"),
            )
        _require_positive_age(self.max_age)

    @property
    def lag(self) -> timedelta | None:
        if self.completed_window_end is None or self.completed_window_end > self.observed_at:
            return None
        return self.observed_at - self.completed_window_end

    @property
    def category(self) -> _FreshnessCategory:
        if self.completed_window_end is None:
            return "candidate_unavailable"
        if self.completed_window_end > self.observed_at:
            return "future"
        assert self.lag is not None
        if self.lag < self.max_age:
            return "within_budget"
        if self.lag == self.max_age:
            return "at_budget"
        return "over_budget"

    @property
    def current(self) -> bool:
        return self.category in {"within_budget", "at_budget"}

    def safe_payload(self) -> dict[str, object]:
        return {
            "completed_window_end": _optional_utc_marker(self.completed_window_end),
            "route_observed_at": _utc_marker(self.observed_at),
            "lag_microseconds": None if self.lag is None else _timedelta_microseconds(self.lag),
            "lag_category": self.category,
            "selected_budget_microseconds": _timedelta_microseconds(self.max_age),
        }


@dataclass(frozen=True, slots=True)
class KisPaperIntradayRuntimeWindow:
    """One source-safe outcome for the 90-bar QQQ local-paper decision input.

    ``decision_bars`` and ``replay_bar`` remain in-memory only. They are
    excluded from ``repr`` and ``safe_payload`` so receipt-oriented callers do
    not accidentally serialize OHLCV values or a source path.
    """

    status: TargetInputStatus
    decision_bars: tuple[Bar, ...] = field(repr=False)
    replay_bar: Bar | None = field(repr=False)
    source_catalog_hash: str
    input_manifest_ref: str
    as_of: datetime
    max_age: timedelta = field(repr=False)
    window_start: datetime | None
    window_end: datetime | None
    source_bar_count: int
    regular_bar_count: int
    candidate_bar_count: int
    schema_id: str = KIS_PAPER_INTRADAY_RUNTIME_WINDOW_SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_bars", tuple(self.decision_bars))
        object.__setattr__(self, "as_of", _utc_datetime(self.as_of, "as_of"))
        if self.window_start is not None:
            object.__setattr__(
                self,
                "window_start",
                _utc_datetime(self.window_start, "window_start"),
            )
        if self.window_end is not None:
            object.__setattr__(self, "window_end", _utc_datetime(self.window_end, "window_end"))
        if self.status not in _RUNTIME_WINDOW_STATUSES:
            raise ValueError("runtime window status is invalid")
        if not isinstance(self.max_age, timedelta) or self.max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        _require_sha256(self.source_catalog_hash, "source_catalog_hash")
        _require_sha256(self.input_manifest_ref, "input_manifest_ref")
        if self.schema_id != KIS_PAPER_INTRADAY_RUNTIME_WINDOW_SCHEMA_ID:
            raise ValueError("runtime window schema is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("runtime window schema version is invalid")
        if any(
            type(value) is not int or value < 0
            for value in (
                self.source_bar_count,
                self.regular_bar_count,
                self.candidate_bar_count,
            )
        ):
            raise ValueError("runtime window counts are invalid")
        if self.regular_bar_count > self.source_bar_count:
            raise ValueError("regular bar count exceeds source bar count")

        has_window = self.window_start is not None or self.window_end is not None
        if has_window != (self.candidate_bar_count == KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS):
            raise ValueError("runtime window candidate metadata is invalid")
        if has_window:
            assert self.window_start is not None
            assert self.window_end is not None
            if (
                self.window_end - self.window_start
                != Timeframe.M1.duration * KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS
                or not _ends_on_ten_minute_boundary(self.window_end)
            ):
                raise ValueError("runtime window timing is invalid")

        if self.status == "ready":
            _validate_ready_window(self)
        elif self.decision_bars or self.replay_bar is not None:
            raise ValueError("unready runtime window must not expose bars")
        elif self.status == "stale":
            if not has_window or self.freshness.category != "over_budget":
                raise ValueError("stale runtime window requires an over-budget candidate")
        elif self.status != "stale" and has_window:
            raise ValueError("only ready or stale runtime windows may retain candidate timing")

        expected_manifest_ref = _input_manifest_ref(
            status=self.status,
            source_catalog_hash=self.source_catalog_hash,
            as_of=self.as_of,
            max_age=self.max_age,
            window_start=self.window_start,
            window_end=self.window_end,
            source_bar_count=self.source_bar_count,
            regular_bar_count=self.regular_bar_count,
            candidate_bar_count=self.candidate_bar_count,
            decision_bar_count=len(self.decision_bars),
            replay_bar=self.replay_bar,
        )
        if self.input_manifest_ref != expected_manifest_ref:
            raise ValueError("runtime window input manifest reference is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return categorical, count, time, and hash facts only."""

        return {
            "kind": "kis_paper_intraday_runtime_window",
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "status": self.status,
            "source_bar_count": self.source_bar_count,
            "regular_bar_count": self.regular_bar_count,
            "candidate_bar_count": self.candidate_bar_count,
            "decision_bar_count": len(self.decision_bars),
            "replay_bar_count": int(self.replay_bar is not None),
            "as_of": _utc_marker(self.as_of),
            "window_start": _optional_utc_marker(self.window_start),
            "window_end": _optional_utc_marker(self.window_end),
            "replay_bar_start": (
                None if self.replay_bar is None else _utc_marker(self.replay_bar.start_ts)
            ),
            "replay_bar_end": (
                None if self.replay_bar is None else _utc_marker(self.replay_bar.end_ts)
            ),
            "freshness": self.freshness.safe_payload(),
            "source_catalog_hash": self.source_catalog_hash,
            "input_manifest_ref": self.input_manifest_ref,
        }

    @property
    def freshness(self) -> KisPaperIntradayRuntimeFreshness:
        return self.freshness_at(as_of=self.as_of)

    def freshness_at(self, *, as_of: datetime) -> KisPaperIntradayRuntimeFreshness:
        return KisPaperIntradayRuntimeFreshness(
            completed_window_end=self.window_end,
            observed_at=as_of,
            max_age=self.max_age,
        )


@dataclass(frozen=True, slots=True)
class KisPaperIntradayRuntimeWindowLocalAvailability:
    """Source-safe local-retention fact for one selected runtime input window.

    ``local_input_available_by_decision`` means only that every selected bar
    was already retained in this local cache by ``decided_at``. It deliberately
    says nothing about provider publication, finality, or another run's input.
    """

    input_manifest_ref: str
    source_catalog_hash: str
    index_metadata_sha256: str
    selected_bar_count: int
    latest_local_retained_at: datetime
    decided_at: datetime
    local_input_available_by_decision: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_sha256(self.input_manifest_ref, "input_manifest_ref")
        _require_sha256(self.source_catalog_hash, "source_catalog_hash")
        _require_sha256(self.index_metadata_sha256, "index_metadata_sha256")
        if type(self.selected_bar_count) is not int or self.selected_bar_count <= 0:
            raise ValueError("runtime local availability selected bar count is invalid")
        object.__setattr__(
            self,
            "latest_local_retained_at",
            _utc_datetime(self.latest_local_retained_at, "latest_local_retained_at"),
        )
        object.__setattr__(self, "decided_at", _utc_datetime(self.decided_at, "decided_at"))
        if type(self.local_input_available_by_decision) is not bool:
            raise ValueError("runtime local availability decision flag is invalid")
        if self.local_input_available_by_decision != (
            self.latest_local_retained_at <= self.decided_at
        ):
            raise ValueError("runtime local availability decision flag is inconsistent")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("runtime local availability schema version is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return only lineage, timing, count, and local-availability facts."""

        return {
            "kind": "kis_paper_intraday_runtime_window_local_availability",
            "schema_version": self.schema_version,
            "input_manifest_ref": self.input_manifest_ref,
            "source_catalog_hash": self.source_catalog_hash,
            "index_metadata_sha256": self.index_metadata_sha256,
            "selected_bar_count": self.selected_bar_count,
            "latest_local_retained_at": _utc_marker(self.latest_local_retained_at),
            "decided_at": _utc_marker(self.decided_at),
            "local_input_available_by_decision": self.local_input_available_by_decision,
            "limitations": {
                "local_cache_retention_only": True,
                "provider_decision_time_availability": "not_observed",
                "provider_finality": "not_observed",
            },
        }


def attest_kis_paper_intraday_runtime_window_local_availability(
    catalog: CatalogedBars,
    *,
    runtime_window: KisPaperIntradayRuntimeWindow,
    cache_root: Path,
    repo_root: Path,
    decided_at: datetime,
) -> KisPaperIntradayRuntimeWindowLocalAvailability:
    """Bind one ready QQQ runtime window to its earliest local retention facts.

    The caller keeps freshness and execution checks separate. This helper opens
    only the already persisted local index metadata through the verified loader
    contract; it never reads credentials or calls a provider or broker.
    """

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("runtime local availability requires CatalogedBars")
    if not isinstance(runtime_window, KisPaperIntradayRuntimeWindow):
        raise TypeError("runtime local availability requires a runtime window")
    resolved_decided_at = _utc_datetime(decided_at, "decided_at")
    if runtime_window.status != "ready":
        raise ValueError("runtime local availability requires a ready window")
    if runtime_window.source_catalog_hash != catalog.dataset_hash:
        raise ValueError("runtime window catalog lineage is invalid")
    if resolved_decided_at < runtime_window.as_of:
        raise ValueError("decided_at must not precede runtime window as_of")

    retention: KisPaperPrivateIntradayLocalRetention = (
        inspect_kis_paper_private_intraday_local_retention(
            catalog,
            cache_root=cache_root,
            repo_root=repo_root,
            symbol="QQQ",
            exchange="NAS",
            selected_bars=runtime_window.decision_bars,
        )
    )
    if retention.source_catalog_hash != runtime_window.source_catalog_hash:
        raise ValueError("runtime local availability retention lineage is invalid")

    return KisPaperIntradayRuntimeWindowLocalAvailability(
        input_manifest_ref=runtime_window.input_manifest_ref,
        source_catalog_hash=runtime_window.source_catalog_hash,
        index_metadata_sha256=retention.index_metadata_sha256,
        selected_bar_count=retention.selected_bar_count,
        latest_local_retained_at=retention.latest_local_retained_at,
        decided_at=resolved_decided_at,
        local_input_available_by_decision=(
            retention.latest_local_retained_at <= resolved_decided_at
        ),
    )


def select_kis_paper_intraday_runtime_window(
    catalog: CatalogedBars,
    *,
    as_of: datetime,
    max_age: timedelta,
) -> KisPaperIntradayRuntimeWindow:
    """Select the newest qualified QQQ 90-bar window without opening any source.

    The source is a pre-verified in-memory ``CatalogedBars`` stream. This
    function never loads a cache, reads credentials, or calls a broker. A
    complete 390-minute session is deliberately not required.
    """

    observed_at = _utc_datetime(as_of, "as_of")
    _require_positive_age(max_age)
    if not isinstance(catalog, CatalogedBars):
        raise TypeError("runtime window selection requires CatalogedBars")

    source_bar_count = len(catalog.bars)
    if not _is_qualified_catalog(catalog):
        return _result(
            status="misaligned",
            catalog=catalog,
            as_of=observed_at,
            max_age=max_age,
            source_bar_count=source_bar_count,
            regular_bar_count=0,
        )
    regular_by_session = _regular_bars_by_session(catalog.bars)
    regular_bar_count = sum(len(bars) for bars in regular_by_session.values())
    if _contains_future_bar(catalog.bars, as_of=observed_at):
        return _result(
            status="future",
            catalog=catalog,
            as_of=observed_at,
            max_age=max_age,
            source_bar_count=source_bar_count,
            regular_bar_count=regular_bar_count,
        )

    candidate = _newest_candidate(regular_by_session)
    if candidate is not None:
        candidate_bars, session = candidate
        freshness = KisPaperIntradayRuntimeFreshness(
            completed_window_end=candidate_bars[-1].end_ts,
            observed_at=observed_at,
            max_age=max_age,
        )
        if not freshness.current:
            return _result(
                status="stale",
                catalog=catalog,
                as_of=observed_at,
                max_age=max_age,
                source_bar_count=source_bar_count,
                regular_bar_count=regular_bar_count,
                candidate_bars=candidate_bars,
            )
        return _result(
            status="ready",
            catalog=catalog,
            as_of=observed_at,
            max_age=max_age,
            source_bar_count=source_bar_count,
            regular_bar_count=regular_bar_count,
            candidate_bars=candidate_bars,
            replay_bar=_immediate_replay_bar(
                candidate_bars=candidate_bars,
                session=session,
                session_bars=regular_by_session[session.session_date],
                as_of=observed_at,
            ),
        )

    return _result(
        status=_unavailable_status(regular_by_session),
        catalog=catalog,
        as_of=observed_at,
        max_age=max_age,
        source_bar_count=source_bar_count,
        regular_bar_count=regular_bar_count,
    )


def _result(
    *,
    status: _RuntimeWindowStatus,
    catalog: CatalogedBars,
    as_of: datetime,
    max_age: timedelta,
    source_bar_count: int,
    regular_bar_count: int,
    candidate_bars: tuple[Bar, ...] = (),
    replay_bar: Bar | None = None,
) -> KisPaperIntradayRuntimeWindow:
    candidate = tuple(candidate_bars)
    is_ready = status == "ready"
    decision_bars = candidate if is_ready else ()
    selected_replay_bar = replay_bar if is_ready else None
    window_start = candidate[0].start_ts if candidate else None
    window_end = candidate[-1].end_ts if candidate else None
    manifest_ref = _input_manifest_ref(
        status=status,
        source_catalog_hash=catalog.dataset_hash,
        as_of=as_of,
        max_age=max_age,
        window_start=window_start,
        window_end=window_end,
        source_bar_count=source_bar_count,
        regular_bar_count=regular_bar_count,
        candidate_bar_count=len(candidate),
        decision_bar_count=len(decision_bars),
        replay_bar=selected_replay_bar,
    )
    return KisPaperIntradayRuntimeWindow(
        status=status,
        decision_bars=decision_bars,
        replay_bar=selected_replay_bar,
        source_catalog_hash=catalog.dataset_hash,
        input_manifest_ref=manifest_ref,
        as_of=as_of,
        max_age=max_age,
        window_start=window_start,
        window_end=window_end,
        source_bar_count=source_bar_count,
        regular_bar_count=regular_bar_count,
        candidate_bar_count=len(candidate),
    )


def _is_qualified_catalog(catalog: CatalogedBars) -> bool:
    return (
        catalog.dataset_id.startswith(_KIS_PAPER_QQQ_NAS_M1_CATALOG_PREFIX)
        and all(
            bar.symbol == "QQQ"
            and bar.market == "US"
            and bar.timeframe is Timeframe.M1
            for bar in catalog.bars
        )
    )


def _contains_future_bar(bars: tuple[Bar, ...], *, as_of: datetime) -> bool:
    return any(
        bar.start_ts >= as_of or (bar.complete and bar.end_ts > as_of)
        for bar in bars
    )


def _regular_bars_by_session(
    bars: tuple[Bar, ...],
) -> dict[date, tuple[Bar, ...]]:
    grouped: defaultdict[date, list[Bar]] = defaultdict(list)
    for bar in bars:
        session = _regular_session_for(bar)
        if session is not None:
            grouped[session.session_date].append(bar)
    return {
        session_date: tuple(sorted(session_bars, key=lambda bar: bar.start_ts))
        for session_date, session_bars in grouped.items()
    }


def _regular_session_for(bar: Bar) -> UsEquity2026Session | None:
    session_date = bar.start_ts.date()
    if session_date.year != 2026:
        return None
    session = us_equity_2026_session(session_date)
    if (
        session is None
        or session.kind != "regular"
        or bar.start_ts < session.window.open_ts
        or bar.end_ts > session.window.close_ts
    ):
        return None
    return session


def _newest_candidate(
    regular_by_session: dict[date, tuple[Bar, ...]],
) -> tuple[tuple[Bar, ...], UsEquity2026Session] | None:
    candidates: list[tuple[tuple[Bar, ...], UsEquity2026Session]] = []
    for session_date, bars in regular_by_session.items():
        session = us_equity_2026_session(session_date)
        assert session is not None
        for end_index in range(KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS - 1, len(bars)):
            candidate = bars[
                end_index + 1 - KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS : end_index + 1
            ]
            if _is_qualified_candidate(candidate, session=session):
                candidates.append((candidate, session))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0][-1].end_ts)


def _is_qualified_candidate(
    bars: tuple[Bar, ...],
    *,
    session: UsEquity2026Session,
) -> bool:
    if len(bars) != KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS:
        return False
    if any(
        not bar.complete
        or not _is_minute_aligned(bar.start_ts)
        or bar.start_ts < session.window.open_ts
        or bar.end_ts > session.window.close_ts
        for bar in bars
    ):
        return False
    if any(
        current.start_ts != prior.end_ts
        for prior, current in zip(bars, bars[1:], strict=False)
    ):
        return False
    return _ends_on_ten_minute_boundary(bars[-1].end_ts)


def _immediate_replay_bar(
    *,
    candidate_bars: tuple[Bar, ...],
    session: UsEquity2026Session,
    session_bars: tuple[Bar, ...],
    as_of: datetime,
) -> Bar | None:
    expected_start = candidate_bars[-1].end_ts
    matches = tuple(bar for bar in session_bars if bar.start_ts == expected_start)
    if len(matches) != 1:
        return None
    replay_bar = matches[0]
    if (
        not replay_bar.complete
        or replay_bar.end_ts > as_of
        or replay_bar.start_ts < session.window.open_ts
        or replay_bar.end_ts > session.window.close_ts
    ):
        return None
    return replay_bar


def _unavailable_status(
    regular_by_session: dict[date, tuple[Bar, ...]],
) -> _RuntimeWindowStatus:
    regular_bars = tuple(bar for bars in regular_by_session.values() for bar in bars)
    if not regular_bars or all(
        len(bars) < KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS
        for bars in regular_by_session.values()
    ):
        return "missing"
    if any(not _is_minute_aligned(bar.start_ts) for bar in regular_bars):
        return "misaligned"
    if any(_has_gap_or_duplicate(bars) for bars in regular_by_session.values()):
        return "non_contiguous"
    if any(not bar.complete for bar in regular_bars):
        return "incomplete"
    return "misaligned"


def _has_gap_or_duplicate(bars: tuple[Bar, ...]) -> bool:
    return any(
        current.start_ts != prior.end_ts
        for prior, current in zip(bars, bars[1:], strict=False)
    )


def _validate_ready_window(window: KisPaperIntradayRuntimeWindow) -> None:
    bars = window.decision_bars
    if len(bars) != KIS_PAPER_INTRADAY_RUNTIME_WINDOW_M1_BARS:
        raise ValueError("ready runtime window requires exactly 90 decision bars")
    if window.candidate_bar_count != len(bars):
        raise ValueError("ready runtime window candidate count is invalid")
    assert window.window_start is not None
    assert window.window_end is not None
    if bars[0].start_ts != window.window_start or bars[-1].end_ts != window.window_end:
        raise ValueError("ready runtime window timing does not match decision bars")
    session = _regular_session_for(bars[0])
    if session is None or not _is_qualified_candidate(bars, session=session):
        raise ValueError("ready runtime window decision bars are invalid")
    if not window.freshness.current:
        raise ValueError("ready runtime window freshness is invalid")
    if window.replay_bar is not None:
        replay = window.replay_bar
        if (
            replay.symbol != "QQQ"
            or replay.market != "US"
            or replay.timeframe is not Timeframe.M1
            or not replay.complete
            or replay.start_ts != window.window_end
            or replay.end_ts > window.as_of
            or _regular_session_for(replay) != session
        ):
            raise ValueError("ready runtime window replay bar is invalid")


def _input_manifest_ref(
    *,
    status: TargetInputStatus,
    source_catalog_hash: str,
    as_of: datetime,
    max_age: timedelta,
    window_start: datetime | None,
    window_end: datetime | None,
    source_bar_count: int,
    regular_bar_count: int,
    candidate_bar_count: int,
    decision_bar_count: int,
    replay_bar: Bar | None,
) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "schema_id": KIS_PAPER_INTRADAY_RUNTIME_WINDOW_SCHEMA_ID,
        "status": status,
        "source_catalog_hash": source_catalog_hash,
        "as_of": _utc_marker(as_of),
        "max_age_microseconds": _timedelta_microseconds(max_age),
        "window_start": _optional_utc_marker(window_start),
        "window_end": _optional_utc_marker(window_end),
        "source_bar_count": source_bar_count,
        "regular_bar_count": regular_bar_count,
        "candidate_bar_count": candidate_bar_count,
        "decision_bar_count": decision_bar_count,
        "replay_bar_start": None if replay_bar is None else _utc_marker(replay_bar.start_ts),
        "replay_bar_end": None if replay_bar is None else _utc_marker(replay_bar.end_ts),
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    return require_utc(value, field_name)


def _require_positive_age(value: timedelta) -> None:
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise ValueError("max_age must be positive")


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _is_minute_aligned(timestamp: datetime) -> bool:
    return timestamp.second == 0 and timestamp.microsecond == 0


def _ends_on_ten_minute_boundary(timestamp: datetime) -> bool:
    return _is_minute_aligned(timestamp) and timestamp.minute % 10 == 0


def _timedelta_microseconds(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")


def _optional_utc_marker(value: datetime | None) -> str | None:
    return None if value is None else _utc_marker(value)

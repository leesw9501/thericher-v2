"""Metadata-only topology audit for the scheduled KIS Paper intraday head.

The audit intentionally opens only the retained index and manifest metadata. It
never opens raw minute snapshots, credentials, broker data, or a scheduler API.
The caller supplies source-safe static Task Scheduler facts.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import require_utc

from .kis_intraday_head_coverage import (
    KIS_INTRADAY_HEAD_CACHE_VERSION,
    KIS_INTRADAY_HEAD_EXPECTED_TARGETS,
    KIS_INTRADAY_HEAD_INDEX_FILENAME,
    KIS_INTRADAY_HEAD_QQQ_TARGET_KEY,
    KisIntradayHeadCoverage,
    inspect_kis_paper_private_intraday_head_coverage,
)
from .kis_paper_intraday import raw_bar_end_is_complete
from .kis_paper_intraday_index_metadata import (
    KisPaperPrivateIntradayV1RetainedChunkMetadata,
    validate_kis_paper_private_intraday_v1_index_metadata,
)
from .us_equity_session import us_equity_2026_session

KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_KIND = "kis_paper_intraday_capture_topology"
KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_TASK_NAME = "thericher-kis-paper-intraday-head"
KIS_PAPER_INTRADAY_CAPTURE_SLOT_TOLERANCE = timedelta(minutes=10)

_KOREA_TZ = ZoneInfo("Asia/Seoul")
_EASTERN_TZ = ZoneInfo("America/New_York")
_SAFE_TASK_STATE = re.compile(r"[A-Za-z_]{1,40}", re.ASCII)
_TASK_LOG_STATES = frozenset({"enabled", "disabled", "unavailable"})


@dataclass(frozen=True, slots=True)
class KisPaperIntradayCaptureTaskFacts:
    """Static, source-safe facts from the one existing Task Scheduler entry."""

    task_name: str
    state: str
    enabled: bool
    action_count: int
    trigger_start_boundaries: tuple[datetime, ...]
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_task_result: int
    missed_run_count: int
    operational_log_state: Literal["enabled", "disabled", "unavailable"]

    def __post_init__(self) -> None:
        if self.task_name != KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_TASK_NAME:
            raise ValueError("capture topology task name is invalid")
        if _SAFE_TASK_STATE.fullmatch(self.state) is None:
            raise ValueError("capture topology task state is invalid")
        if type(self.enabled) is not bool or type(self.action_count) is not int:
            raise ValueError("capture topology task facts are invalid")
        if self.action_count < 0 or type(self.last_task_result) is not int:
            raise ValueError("capture topology task facts are invalid")
        if type(self.missed_run_count) is not int or self.missed_run_count < 0:
            raise ValueError("capture topology task facts are invalid")
        boundaries = tuple(self.trigger_start_boundaries)
        if not boundaries:
            raise ValueError("capture topology task triggers are invalid")
        normalized_boundaries = tuple(
            require_utc(boundary, "capture topology trigger") for boundary in boundaries
        )
        if len(set(normalized_boundaries)) != len(normalized_boundaries):
            raise ValueError("capture topology task triggers are invalid")
        object.__setattr__(self, "trigger_start_boundaries", normalized_boundaries)
        if self.last_run_at is not None:
            object.__setattr__(self, "last_run_at", require_utc(self.last_run_at, "last run"))
        if self.next_run_at is not None:
            object.__setattr__(self, "next_run_at", require_utc(self.next_run_at, "next run"))
        if self.operational_log_state not in _TASK_LOG_STATES:
            raise ValueError("capture topology task log state is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "task_name": self.task_name,
            "state": self.state,
            "enabled": self.enabled,
            "action_count": self.action_count,
            "trigger_count": len(self.trigger_start_boundaries),
            "trigger_start_boundaries": [
                _utc_marker(value) for value in self.trigger_start_boundaries
            ],
            "last_run_at": None if self.last_run_at is None else _utc_marker(self.last_run_at),
            "next_run_at": None if self.next_run_at is None else _utc_marker(self.next_run_at),
            "last_task_result": self.last_task_result,
            "missed_run_count": self.missed_run_count,
            "operational_log_state": self.operational_log_state,
        }


@dataclass(frozen=True, slots=True)
class KisPaperIntradayCaptureTopology:
    """One source-safe audit result; no missing chunk is treated as a missed task."""

    task_facts: KisPaperIntradayCaptureTaskFacts
    coverage: KisIntradayHeadCoverage
    retained_slot_counts: tuple[tuple[str, int], ...]
    sessions: tuple[dict[str, object], ...]
    evidence_status: Literal["not_created", "topology_observed", "run_or_persistence_unresolved"]
    recommendation: str

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_PAPER_INTRADAY_CAPTURE_TOPOLOGY_KIND,
            "task_scheduler": self.task_facts.to_payload(),
            "coverage": self.coverage.to_payload(),
            "retained_slot_counts": [
                {"slot_et": slot, "retained_chunk_count": count}
                for slot, count in self.retained_slot_counts
            ],
            "sessions": list(self.sessions),
            "evidence_status": self.evidence_status,
            "recommendation": self.recommendation,
            "limitations": {
                "metadata_only": True,
                "raw_market_data_read": False,
                "credentials_read": False,
                "broker_or_kis_call": False,
                "missing_retained_chunk_proves_scheduler_miss": False,
                "task_scheduler_operational_log": self.task_facts.operational_log_state,
            },
        }


def inspect_kis_paper_intraday_capture_topology(
    *,
    cache_root: Path | str,
    repository_root: Path | str,
    task_facts: KisPaperIntradayCaptureTaskFacts,
    after_session_date: date,
    required_complete_session_count: int,
) -> KisPaperIntradayCaptureTopology:
    """Audit retained M1 topology plus caller-provided static task facts.

    A missing retained chunk can arise from an ignored trigger, failed dispatcher,
    collector lock, provider response, or de-duplication. The audit reports that
    uncertainty explicitly and recommends observability before changing timing.
    """

    coverage = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=repository_root,
        after_session_date=after_session_date,
        required_complete_session_count=required_complete_session_count,
    )
    if coverage.status == "not_created":
        return KisPaperIntradayCaptureTopology(
            task_facts=task_facts,
            coverage=coverage,
            retained_slot_counts=(),
            sessions=(),
            evidence_status="not_created",
            recommendation="collect one task-owned session before changing the task contract",
        )

    chunks = _read_qqq_head_chunks(cache_root=cache_root, repository_root=repository_root)
    session_chunks = _session_chunks(chunks=chunks, task_facts=task_facts)
    sessions = tuple(
        _session_payload(
            session_date=session_date,
            chunks=items,
            coverage=coverage,
            task_facts=task_facts,
        )
        for session_date, items in sorted(session_chunks.items())
        if session_date > after_session_date
    )
    slot_counts = Counter(
        chunk.slot_et
        for values in session_chunks.values()
        for chunk in values
        if chunk.slot_et is not None
    )
    retained_slot_counts = tuple(sorted(slot_counts.items()))
    has_short_with_absent_slot = any(
        item["coverage_status"] == "short" and item["unretained_or_unstarted_slots"]
        for item in sessions
    )
    return KisPaperIntradayCaptureTopology(
        task_facts=task_facts,
        coverage=coverage,
        retained_slot_counts=retained_slot_counts,
        sessions=sessions,
        evidence_status=(
            "run_or_persistence_unresolved" if has_short_with_absent_slot else "topology_observed"
        ),
        recommendation=(
            "add source-safe start and terminal slot receipts to the existing dispatcher before "
            "changing triggers, paging, or downstream scheduling"
            if has_short_with_absent_slot
            else "retain the existing one-task contract and reattach the next task-owned result"
        ),
    )


@dataclass(frozen=True, slots=True)
class _ChunkSlot:
    session_date: date
    slot_et: str | None
    min_offset: int
    max_offset: int
    complete_minute_count: int
    row_count: int
    terminal_page: bool


def _read_qqq_head_chunks(
    *, cache_root: Path | str, repository_root: Path | str
) -> tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...]:
    root = Path(cache_root)
    if root.is_symlink():
        raise ValueError("capture topology cache root is invalid")
    resolved_root = root.resolve()
    if resolved_root.is_relative_to(Path(repository_root).resolve()):
        raise ValueError("capture topology cache root must stay outside the Git workspace")
    version_root = resolved_root / KIS_INTRADAY_HEAD_CACHE_VERSION
    index_path = version_root / KIS_INTRADAY_HEAD_INDEX_FILENAME
    if not index_path.exists():
        return ()
    if index_path.is_symlink():
        raise ValueError("capture topology index is invalid")
    try:
        index_bytes = index_path.read_bytes()
        index = json.loads(index_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("capture topology index is invalid") from error
    if not isinstance(index, dict):
        raise ValueError("capture topology index is invalid")
    try:
        metadata = validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=KIS_INTRADAY_HEAD_EXPECTED_TARGETS,
        )
    except ValueError as error:
        raise ValueError("capture topology index is invalid") from error
    target = next(
        (item for item in metadata.targets if item.target_key == KIS_INTRADAY_HEAD_QQQ_TARGET_KEY),
        None,
    )
    if target is None:
        raise ValueError("capture topology target is invalid")
    return tuple(chunk for chunk in target.retained_chunks if chunk.collection_scope == "head")


def _session_chunks(
    *,
    chunks: tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...],
    task_facts: KisPaperIntradayCaptureTaskFacts,
) -> dict[date, list[_ChunkSlot]]:
    result: dict[date, list[_ChunkSlot]] = defaultdict(list)
    for chunk in chunks:
        offsets_by_date: dict[date, list[tuple[int, bool]]] = defaultdict(list)
        for row_key, _fingerprint in chunk.rows:
            row_start = _korea_timestamp_to_utc(row_key)
            session = us_equity_2026_session(row_start.date())
            if (
                session is None
                or session.kind != "regular"
                or not session.window.open_ts <= row_start < session.window.close_ts
            ):
                continue
            offsets_by_date[row_start.date()].append(
                (
                    int((row_start - session.window.open_ts) / timedelta(minutes=1)),
                    raw_bar_end_is_complete(start_ts=row_start, collected_at=chunk.collected_at),
                )
            )
        for session_date, values in offsets_by_date.items():
            offsets = [offset for offset, _complete in values]
            result[session_date].append(
                _ChunkSlot(
                    session_date=session_date,
                    slot_et=_matched_slot_et(
                        collected_at=chunk.collected_at,
                        session_date=session_date,
                        task_facts=task_facts,
                    ),
                    min_offset=min(offsets),
                    max_offset=max(offsets),
                    complete_minute_count=sum(1 for _offset, complete in values if complete),
                    row_count=len(values),
                    terminal_page=chunk.output_cursor is None,
                )
            )
    return result


def _session_payload(
    *,
    session_date: date,
    chunks: list[_ChunkSlot],
    coverage: KisIntradayHeadCoverage,
    task_facts: KisPaperIntradayCaptureTaskFacts,
) -> dict[str, object]:
    coverage_item = next(
        (item for item in coverage.session_coverage if item.session_date == session_date),
        None,
    )
    all_slots = _slot_labels_for_session(
        session_date=session_date,
        trigger_start_boundaries=task_facts.trigger_start_boundaries,
    )
    retained_slots = sorted({chunk.slot_et for chunk in chunks if chunk.slot_et is not None})
    if coverage_item is None:
        coverage_status: Literal["complete", "short"] = "short"
        complete_minute_count = sum(chunk.complete_minute_count for chunk in chunks)
        missing_minute_count = None
    else:
        coverage_status = coverage_item.status
        complete_minute_count = coverage_item.complete_minute_count
        missing_minute_count = coverage_item.expected_minute_count - complete_minute_count
    return {
        "session_date": session_date.isoformat(),
        "coverage_status": coverage_status,
        "complete_minute_count": complete_minute_count,
        "missing_minute_count": missing_minute_count,
        "retained_chunks": [
            {
                "slot_et": chunk.slot_et,
                "row_count": chunk.row_count,
                "complete_minute_count": chunk.complete_minute_count,
                "min_offset": chunk.min_offset,
                "max_offset": chunk.max_offset,
                "terminal_page": chunk.terminal_page,
            }
            for chunk in sorted(chunks, key=lambda item: (item.slot_et or "", item.min_offset))
        ],
        "retained_slots": retained_slots,
        "unretained_or_unstarted_slots": [
            slot for slot in all_slots if slot not in retained_slots
        ],
    }


def _matched_slot_et(
    *,
    collected_at: datetime,
    session_date: date,
    task_facts: KisPaperIntradayCaptureTaskFacts,
) -> str | None:
    candidates = _slot_datetimes_for_session(
        session_date=session_date,
        trigger_start_boundaries=task_facts.trigger_start_boundaries,
    )
    matches = [
        (
            abs(collected_at - scheduled_at),
            scheduled_at.astimezone(_EASTERN_TZ).strftime("%H:%M"),
        )
        for scheduled_at in candidates
        if abs(collected_at - scheduled_at) <= KIS_PAPER_INTRADAY_CAPTURE_SLOT_TOLERANCE
    ]
    if len(matches) != 1:
        return None
    return matches[0][1]


def _slot_labels_for_session(
    *, session_date: date, trigger_start_boundaries: tuple[datetime, ...]
) -> tuple[str, ...]:
    return tuple(
        value.astimezone(_EASTERN_TZ).strftime("%H:%M")
        for value in _slot_datetimes_for_session(
            session_date=session_date,
            trigger_start_boundaries=trigger_start_boundaries,
        )
    )


def _slot_datetimes_for_session(
    *, session_date: date, trigger_start_boundaries: tuple[datetime, ...]
) -> tuple[datetime, ...]:
    values = []
    for boundary in trigger_start_boundaries:
        kst_time = boundary.astimezone(_KOREA_TZ).timetz().replace(tzinfo=None)
        scheduled = datetime.combine(
            session_date + timedelta(days=1),
            time(hour=kst_time.hour, minute=kst_time.minute, second=kst_time.second),
            tzinfo=_KOREA_TZ,
        ).astimezone(UTC)
        values.append(scheduled)
    return tuple(sorted(values))


def _korea_timestamp_to_utc(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError as error:
        raise ValueError("capture topology row timestamp is invalid") from error
    return parsed.replace(tzinfo=_KOREA_TZ).astimezone(UTC)


def _utc_marker(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

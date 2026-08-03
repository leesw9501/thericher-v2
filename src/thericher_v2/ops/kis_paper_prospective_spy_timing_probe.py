"""Data-only timing evidence for the prospective SPY completed-bar seam."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_prospective_spy_capture import (
    capture_kis_paper_prospective_spy_observation,
)
from thericher_v2.data.us_equity_session import us_equity_2026_session

KIS_PAPER_PROSPECTIVE_SPY_TIMING_PROBE_KIND = "kis_paper_prospective_spy_timing_probe"
KIS_PAPER_PROSPECTIVE_SPY_TIMING_PROBE_ARTIFACT_DIRECTORY = (
    "data/kis-paper-prospective-spy-timing-probe-v1"
)
KIS_PAPER_PROSPECTIVE_SPY_TIMING_PROBE_TARGET = "SPY/AMS/1m"
_EASTERN = ZoneInfo("America/New_York")
_DECISION_TIME = time(15, 30)
_VALIDITY_SECONDS = 60
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}", re.ASCII)
_DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE_ROOT = Path(r"D:\market_data\us_equities\kis_paper_private\intraday-head")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_COLLECTION_STATUSES = frozenset(
    {"collected", "partial", "rejected", "locked", "recovered", "source_exhausted", "unavailable"}
)
_CAPTURE_STATUSES = frozenset({"captured", "not_yet_observed", "not_run"})
_SCHEDULE_RELATIONS = frozenset(
    {
        "calendar_unavailable",
        "not_regular_session",
        "before_decision_cutoff",
        "inside_execution_validity",
        "at_or_after_execution_expiry",
    }
)
_CLOCK_ORDERS = frozenset({"ordered", "non_monotonic"})

ScheduleRelation = Literal[
    "calendar_unavailable",
    "not_regular_session",
    "before_decision_cutoff",
    "inside_execution_validity",
    "at_or_after_execution_expiry",
]
CaptureStatus = Literal["captured", "not_yet_observed", "not_run"]


@dataclass(frozen=True, slots=True)
class KisPaperProspectiveSpyTimingProbeOutcome:
    """One external, post-collection observation with no execution surface."""

    probe_id: str
    session_date: date
    scheduler_started_at: datetime
    collector_returned_at: datetime
    probe_started_at: datetime
    probe_finished_at: datetime
    schedule_relation: ScheduleRelation
    collector_clock_order: Literal["ordered", "non_monotonic"]
    collector_wall_duration_ms: int | None
    collection_exit_code: int
    spy_collection_status: str
    spy_row_count: int
    spy_exact_overlap_rows: int
    spy_reason: str | None
    capture_status: CaptureStatus
    capture_reason: str | None
    post_collection_prefix_availability: Literal[
        "present_after_collection", "unavailable_after_collection"
    ]
    evidence_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.probe_id) is None or self.probe_id in {".", ".."}:
            raise ValueError("prospective SPY timing probe id is invalid")
        if type(self.session_date) is not date:
            raise ValueError("prospective SPY timing probe session date is invalid")
        for name in (
            "scheduler_started_at",
            "collector_returned_at",
            "probe_started_at",
            "probe_finished_at",
        ):
            object.__setattr__(self, name, require_utc(getattr(self, name), name))
        if self.schedule_relation not in _SCHEDULE_RELATIONS:
            raise ValueError("prospective SPY timing schedule relation is invalid")
        if self.collector_clock_order not in _CLOCK_ORDERS:
            raise ValueError("prospective SPY timing clock order is invalid")
        if self.collector_wall_duration_ms is not None and self.collector_wall_duration_ms < 0:
            raise ValueError("prospective SPY timing duration is invalid")
        if self.collection_exit_code < 0:
            raise ValueError("prospective SPY timing collector exit code is invalid")
        if self.spy_collection_status not in _COLLECTION_STATUSES:
            raise ValueError("prospective SPY timing collector status is invalid")
        if self.spy_row_count < 0 or self.spy_exact_overlap_rows < 0:
            raise ValueError("prospective SPY timing collector counts are invalid")
        if self.spy_reason is not None and _SAFE_REASON.fullmatch(self.spy_reason) is None:
            raise ValueError("prospective SPY timing collector reason is invalid")
        if self.capture_status not in _CAPTURE_STATUSES:
            raise ValueError("prospective SPY timing capture status is invalid")
        if self.capture_reason is not None and _SAFE_REASON.fullmatch(self.capture_reason) is None:
            raise ValueError("prospective SPY timing capture reason is invalid")
        expected_availability = (
            "present_after_collection"
            if self.capture_status == "captured"
            else "unavailable_after_collection"
        )
        if self.post_collection_prefix_availability != expected_availability:
            raise ValueError("prospective SPY timing prefix availability is invalid")
        if not isinstance(self.evidence_path, Path) or self.evidence_path.name != "evidence.json":
            raise ValueError("prospective SPY timing evidence path is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Expose timing and collection categories without rows or broker state."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_SPY_TIMING_PROBE_KIND,
            "probe_id": self.probe_id,
            "target": KIS_PAPER_PROSPECTIVE_SPY_TIMING_PROBE_TARGET,
            "session_date": self.session_date.isoformat(),
            "route_class": "kis_paper_market_data_post_collection",
            "timing": {
                "timezone": "America/New_York",
                "scheduler_started_at": _time_payload(self.scheduler_started_at),
                "collector_returned_at": _time_payload(self.collector_returned_at),
                "probe_started_at": _time_payload(self.probe_started_at),
                "probe_finished_at": _time_payload(self.probe_finished_at),
                "collector_clock_order": self.collector_clock_order,
                "collector_wall_duration_ms": self.collector_wall_duration_ms,
                "collector_wall_duration_includes_container_lifecycle": True,
            },
            "schedule_relation": self.schedule_relation,
            "collector": {
                "exit_code": self.collection_exit_code,
                "spy_status": self.spy_collection_status,
                "spy_row_count": self.spy_row_count,
                "spy_exact_overlap_rows": self.spy_exact_overlap_rows,
                "spy_reason": self.spy_reason,
            },
            "post_collection_prefix": {
                "availability": self.post_collection_prefix_availability,
                "capture_status": self.capture_status,
                "capture_reason": self.capture_reason,
                "decision_time_availability": "not_observed",
            },
        }


def run_kis_paper_prospective_spy_timing_probe(
    *,
    scheduler_started_at: datetime,
    collector_returned_at: datetime,
    collection_exit_code: int,
    spy_collection_status: str,
    spy_row_count: int,
    spy_exact_overlap_rows: int,
    spy_reason: str | None,
    cache_root: Path = _DEFAULT_CACHE_ROOT,
    artifact_root: Path = _DEFAULT_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    probe_started_at: datetime | None = None,
    probe_finished_at: datetime | None = None,
    probe_id: str | None = None,
) -> KisPaperProspectiveSpyTimingProbeOutcome:
    """Record a cache observation after one existing collector invocation.

    This does not open a KIS client or any Execution path. ``captured`` means
    only that the prefix existed after the collector returned; it is explicitly
    not a claim about decision-time availability.
    """

    scheduler_started = require_utc(scheduler_started_at, "scheduler_started_at")
    collector_returned = require_utc(collector_returned_at, "collector_returned_at")
    probe_started = require_utc(probe_started_at or datetime.now(UTC), "probe_started_at")
    resolved_probe_id = probe_id or _probe_id(probe_started)
    _require_safe_id(resolved_probe_id)
    _require_collection_inputs(
        collection_exit_code=collection_exit_code,
        spy_collection_status=spy_collection_status,
        spy_row_count=spy_row_count,
        spy_exact_overlap_rows=spy_exact_overlap_rows,
        spy_reason=spy_reason,
    )
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    session_date = probe_started.astimezone(_EASTERN).date()
    capture_status, capture_reason = _capture_post_collection_prefix(
        collection_exit_code=collection_exit_code,
        spy_collection_status=spy_collection_status,
        cache_root=cache_root,
        artifact_root=root,
        repository_root=repository_root,
        session_date=session_date,
        probe_started_at=probe_started,
    )
    probe_finished = require_utc(probe_finished_at or datetime.now(UTC), "probe_finished_at")
    clock_order, duration_ms = _collector_timing(
        scheduler_started_at=scheduler_started,
        collector_returned_at=collector_returned,
    )
    outcome = KisPaperProspectiveSpyTimingProbeOutcome(
        probe_id=resolved_probe_id,
        session_date=session_date,
        scheduler_started_at=scheduler_started,
        collector_returned_at=collector_returned,
        probe_started_at=probe_started,
        probe_finished_at=probe_finished,
        schedule_relation=_schedule_relation(scheduler_started),
        collector_clock_order=clock_order,
        collector_wall_duration_ms=duration_ms,
        collection_exit_code=collection_exit_code,
        spy_collection_status=spy_collection_status,
        spy_row_count=spy_row_count,
        spy_exact_overlap_rows=spy_exact_overlap_rows,
        spy_reason=_safe_reason(spy_reason),
        capture_status=capture_status,
        capture_reason=capture_reason,
        post_collection_prefix_availability=(
            "present_after_collection"
            if capture_status == "captured"
            else "unavailable_after_collection"
        ),
        evidence_path=_evidence_path(artifact_root=root, probe_id=resolved_probe_id),
    )
    _write_or_verify(outcome.evidence_path, outcome.safe_payload(), artifact_root=root)
    return outcome


def _capture_post_collection_prefix(
    *,
    collection_exit_code: int,
    spy_collection_status: str,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
    session_date: date,
    probe_started_at: datetime,
) -> tuple[CaptureStatus, str | None]:
    if collection_exit_code != 0 or spy_collection_status == "unavailable":
        return "not_run", "collector_payload_unavailable"
    try:
        result = capture_kis_paper_prospective_spy_observation(
            cache_root=cache_root,
            artifact_root=artifact_root,
            repo_root=repository_root,
            session_date=session_date,
            observed_at=probe_started_at,
        )
    except (OSError, TypeError, ValueError):
        return "not_run", "capture_unavailable"
    if result.status == "captured":
        return "captured", None
    return "not_yet_observed", _safe_reason(result.reason) or "capture_unavailable"


def _schedule_relation(value: datetime) -> ScheduleRelation:
    session_date = value.astimezone(_EASTERN).date()
    try:
        session = us_equity_2026_session(session_date)
    except ValueError:
        return "calendar_unavailable"
    if session is None or session.kind != "regular":
        return "not_regular_session"
    cutoff = datetime.combine(session_date, _DECISION_TIME, _EASTERN).astimezone(UTC)
    valid_until = cutoff + timedelta(seconds=_VALIDITY_SECONDS)
    if value < cutoff:
        return "before_decision_cutoff"
    if value < valid_until:
        return "inside_execution_validity"
    return "at_or_after_execution_expiry"


def _collector_timing(
    *, scheduler_started_at: datetime, collector_returned_at: datetime
) -> tuple[Literal["ordered", "non_monotonic"], int | None]:
    if collector_returned_at < scheduler_started_at:
        return "non_monotonic", None
    elapsed = collector_returned_at - scheduler_started_at
    return "ordered", int(round(elapsed.total_seconds() * 1000))


def _require_collection_inputs(
    *,
    collection_exit_code: int,
    spy_collection_status: str,
    spy_row_count: int,
    spy_exact_overlap_rows: int,
    spy_reason: str | None,
) -> None:
    if collection_exit_code < 0:
        raise ValueError("prospective SPY timing collector exit code is invalid")
    if spy_collection_status not in _COLLECTION_STATUSES:
        raise ValueError("prospective SPY timing collector status is invalid")
    if spy_row_count < 0 or spy_exact_overlap_rows < 0:
        raise ValueError("prospective SPY timing collector counts are invalid")
    _safe_reason(spy_reason)


def _safe_reason(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _SAFE_REASON.fullmatch(value) is None:
        return "unavailable"
    return value


def _probe_id(value: datetime) -> str:
    return f"prospective-spy-timing-{value.strftime('%Y%m%dT%H%M%S%fZ')}"


def _require_safe_id(value: str) -> None:
    if _SAFE_ID.fullmatch(value) is None or value in {".", ".."}:
        raise ValueError("prospective SPY timing probe id is invalid")


def _time_payload(value: datetime) -> dict[str, object]:
    utc_value = require_utc(value, "timing value")
    eastern = utc_value.astimezone(_EASTERN)
    return {
        "utc": _utc_marker(utc_value),
        "eastern": eastern.isoformat(),
        "eastern_utc_offset": eastern.strftime("%z"),
        "eastern_dst": bool(eastern.dst()),
    }


def _evidence_path(*, artifact_root: Path, probe_id: str) -> Path:
    directory = artifact_root / KIS_PAPER_PROSPECTIVE_SPY_TIMING_PROBE_ARTIFACT_DIRECTORY / probe_id
    _ensure_real_descendant(root=artifact_root, directory=directory)
    path = directory / "evidence.json"
    if path.exists() and path.is_symlink():
        raise ValueError("prospective SPY timing evidence path is invalid")
    if not path.resolve(strict=False).is_relative_to(artifact_root):
        raise ValueError("prospective SPY timing evidence path is invalid")
    return path


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve(strict=False)
    repository = Path(repository_root).resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    mounted_artifacts = repository == docker_repository and root.is_relative_to(docker_artifacts)
    if root.is_relative_to(repository) and not mounted_artifacts:
        raise ValueError("prospective SPY timing artifact root must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("prospective SPY timing artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _ensure_real_descendant(*, root: Path, directory: Path) -> None:
    try:
        parts = directory.relative_to(root).parts
    except ValueError as error:
        raise ValueError("prospective SPY timing evidence path is invalid") from error
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.exists():
            if cursor.is_symlink() or not cursor.is_dir():
                raise ValueError("prospective SPY timing evidence path is invalid")
        else:
            cursor.mkdir()
        if not cursor.resolve(strict=True).is_relative_to(root):
            raise ValueError("prospective SPY timing evidence path is invalid")


def _write_or_verify(
    path: Path,
    payload: Mapping[str, object],
    *,
    artifact_root: Path,
) -> None:
    _ensure_real_descendant(root=artifact_root, directory=path.parent)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.is_symlink() or path.read_text(encoding="ascii") != rendered:
            raise ValueError("prospective SPY timing evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != rendered:
                raise ValueError("prospective SPY timing evidence identity conflicts")
            return
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "timing value").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("timing values must be UTC") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("timing values must be UTC")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a Data-only prospective SPY timing receipt")
    parser.add_argument("--scheduler-started-at", type=_parse_utc, required=True)
    parser.add_argument("--collector-returned-at", type=_parse_utc, required=True)
    parser.add_argument("--collection-exit-code", type=int, required=True)
    parser.add_argument(
        "--spy-collection-status",
        choices=sorted(_COLLECTION_STATUSES),
        required=True,
    )
    parser.add_argument("--spy-row-count", type=int, required=True)
    parser.add_argument("--spy-exact-overlap-rows", type=int, required=True)
    parser.add_argument("--spy-reason")
    parser.add_argument("--probe-started-at", type=_parse_utc)
    parser.add_argument("--probe-finished-at", type=_parse_utc)
    parser.add_argument("--probe-id")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=_DEFAULT_CACHE_ROOT,
    )
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repository-root", type=Path, default=_DEFAULT_REPOSITORY_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    outcome = run_kis_paper_prospective_spy_timing_probe(
        scheduler_started_at=args.scheduler_started_at,
        collector_returned_at=args.collector_returned_at,
        collection_exit_code=args.collection_exit_code,
        spy_collection_status=args.spy_collection_status,
        spy_row_count=args.spy_row_count,
        spy_exact_overlap_rows=args.spy_exact_overlap_rows,
        spy_reason=args.spy_reason,
        cache_root=args.cache_root,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        probe_started_at=args.probe_started_at,
        probe_finished_at=args.probe_finished_at,
        probe_id=args.probe_id,
    )
    print(json.dumps(outcome.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()

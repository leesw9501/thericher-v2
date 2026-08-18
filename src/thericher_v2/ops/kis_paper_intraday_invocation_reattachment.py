"""Offline, source-safe binding of one intraday invocation to its terminal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.data.kis_paper_intraday_capture_topology import (
    KisPaperIntradayCaptureTaskFacts,
    KisPaperIntradayCaptureTopology,
    inspect_kis_paper_intraday_capture_topology,
)

from .kis_paper_intraday_head_invocation_receipt import (
    KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY,
    KisPaperIntradayHeadInvocationRuntimeFact,
    KisPaperIntradayHeadInvocationTerminalFact,
    read_current_kis_paper_intraday_head_invocation_runtime_fact,
    read_current_kis_paper_intraday_head_invocation_terminal_fact,
)
from .kis_paper_intraday_head_schedule_receipt import (
    KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY,
    KisPaperIntradayHeadScheduleFact,
    KisPaperIntradayHeadScheduleReceiptError,
    read_kis_paper_intraday_head_schedule_fact_from_artifact_root,
)

KIS_PAPER_INTRADAY_INVOCATION_REATTACHMENT_KIND = (
    "kis_paper_intraday_invocation_reattachment"
)
_EASTERN_TZ = ZoneInfo("America/New_York")

_ReattachmentStatus = Literal[
    "marker_unavailable",
    "start_only",
    "terminal_unavailable",
    "marker_not_later",
    "collector_nonzero",
    "retained_partial",
    "complete_session",
]
_TopologyRelation = Literal[
    "not_observed",
    "current_metadata_consistent",
    "current_metadata_diverged",
]


@dataclass(frozen=True, slots=True)
class KisPaperIntradayInvocationReattachment:
    """One bounded diagnosis without raw rows, paths, or external side effects."""

    status: _ReattachmentStatus
    reason: str
    invocation_phase: Literal["unavailable", "started", "terminal"]
    run_id: str | None
    started_at: datetime | None
    schedule_observed_at: datetime | None
    completed_at: datetime | None
    invocation_receipt_sha256: str | None
    schedule_receipt_sha256: str | None
    invocation_receipt_pointer: str | None
    schedule_receipt_pointer: str | None
    topology_relation: _TopologyRelation
    topology_session_date: date | None
    collection_failure_category: Literal[
        "reason_unavailable", "dispatcher_config", "collector_provider"
    ] = "reason_unavailable"

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_PAPER_INTRADAY_INVOCATION_REATTACHMENT_KIND,
            "status": self.status,
            "reason": self.reason,
            "invocation": {
                "phase": self.invocation_phase,
                "run_id": self.run_id,
                "started_at": _utc_marker(self.started_at),
                "schedule_observed_at": _utc_marker(self.schedule_observed_at),
                "completed_at": _utc_marker(self.completed_at),
                "receipt_sha256": self.invocation_receipt_sha256,
                "collection_failure_category": self.collection_failure_category,
            },
            "schedule_terminal_receipt_sha256": self.schedule_receipt_sha256,
            "external_evidence": {
                "relative_to_artifact_root": True,
                "invocation_receipt": self.invocation_receipt_pointer,
                "schedule_terminal": self.schedule_receipt_pointer,
            },
            "topology": {
                "relation": self.topology_relation,
                "session_date": (
                    None
                    if self.topology_session_date is None
                    else self.topology_session_date.isoformat()
                ),
            },
            "limitations": {
                "raw_market_data_read": False,
                "credentials_read": False,
                "broker_or_kis_call": False,
                "marker_proves_scheduler_origin": False,
                "topology_is_exact_run_binding": False,
            },
        }


def reattach_kis_paper_intraday_invocation_from_artifact_root(
    *,
    artifact_root: Path,
    capture_cache_root: Path,
    repository_root: Path,
    task_facts: KisPaperIntradayCaptureTaskFacts,
    after_session_date: date,
    required_complete_session_count: int,
    baseline_run_id: str | None = None,
    baseline_completed_at: datetime | None = None,
) -> KisPaperIntradayInvocationReattachment:
    """Read only validated source-safe pointers and metadata for the current run."""

    _validate_baseline(
        baseline_run_id=baseline_run_id,
        baseline_completed_at=baseline_completed_at,
    )

    try:
        runtime = read_current_kis_paper_intraday_head_invocation_runtime_fact(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
    except (OSError, ValueError):
        return _marker_unavailable()
    if runtime.phase == "started":
        return _start_only(runtime)
    try:
        terminal = read_current_kis_paper_intraday_head_invocation_terminal_fact(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
        schedule = read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
            artifact_root,
            repository_root=repository_root,
            capture_cache_root=capture_cache_root,
            observation_artifact_root=artifact_root,
        )
    except (KisPaperIntradayHeadScheduleReceiptError, OSError, ValueError):
        return _terminal_unavailable(runtime, reason="schedule_terminal_unavailable")
    try:
        topology = inspect_kis_paper_intraday_capture_topology(
            cache_root=capture_cache_root,
            repository_root=repository_root,
            task_facts=task_facts,
            after_session_date=after_session_date,
            required_complete_session_count=required_complete_session_count,
        )
    except (OSError, ValueError):
        topology = None
    return classify_kis_paper_intraday_invocation_reattachment(
        runtime=runtime,
        terminal=terminal,
        schedule=schedule,
        topology=topology,
        baseline_run_id=baseline_run_id,
        baseline_completed_at=baseline_completed_at,
    )


def classify_kis_paper_intraday_invocation_reattachment(
    *,
    runtime: KisPaperIntradayHeadInvocationRuntimeFact | None,
    terminal: KisPaperIntradayHeadInvocationTerminalFact | None,
    schedule: KisPaperIntradayHeadScheduleFact | None,
    topology: KisPaperIntradayCaptureTopology | None,
    baseline_run_id: str | None = None,
    baseline_completed_at: datetime | None = None,
) -> KisPaperIntradayInvocationReattachment:
    """Classify only evidence that is bound to the current invocation marker."""

    _validate_baseline(
        baseline_run_id=baseline_run_id,
        baseline_completed_at=baseline_completed_at,
    )

    if runtime is None:
        return _marker_unavailable()
    if runtime.phase == "started":
        return _start_only(runtime)
    if terminal is None or schedule is None:
        return _terminal_unavailable(runtime, reason="schedule_terminal_unavailable")
    if terminal.run_id != runtime.run_id or schedule.run_id != terminal.run_id:
        return _terminal_unavailable(runtime, reason="schedule_run_mismatch")
    if schedule.observed_at != terminal.schedule_observed_at:
        return _terminal_unavailable(runtime, reason="schedule_timestamp_mismatch")
    if schedule.terminal_status != terminal.schedule_receipt_outcome:
        return _terminal_unavailable(runtime, reason="schedule_outcome_mismatch")
    expected_terminal_outcome = "succeeded" if schedule.scheduler_exit_code == 0 else "nonzero"
    if terminal.terminal_outcome != expected_terminal_outcome:
        return _terminal_unavailable(runtime, reason="terminal_outcome_mismatch")
    if terminal.collection_outcome == "nonzero":
        if (
            schedule.terminal_status != "recovery"
            or schedule.recovery_class != "collection_exit_nonzero"
        ):
            return _terminal_unavailable(runtime, reason="collection_outcome_mismatch")
        return _require_later_marker(
            _terminal_result(
                status="collector_nonzero",
                reason="collection_exit_nonzero",
                terminal=terminal,
                schedule=schedule,
                topology=topology,
            ),
            baseline_run_id=baseline_run_id,
            baseline_completed_at=baseline_completed_at,
        )
    if terminal.terminal_outcome != "succeeded" or schedule.terminal_status != "complete":
        return _terminal_unavailable(runtime, reason="dispatch_terminal_not_complete")
    if (
        schedule.coverage_binding_status != "verified"
        or schedule.current_session_cumulative_coverage_category is None
    ):
        return _terminal_unavailable(runtime, reason="capture_binding_unavailable")
    if schedule.current_session_cumulative_coverage_category == "complete":
        return _require_later_marker(
            _terminal_result(
                status="complete_session",
                reason="current_session_complete",
                terminal=terminal,
                schedule=schedule,
                topology=topology,
            ),
            baseline_run_id=baseline_run_id,
            baseline_completed_at=baseline_completed_at,
        )
    return _require_later_marker(
        _terminal_result(
            status="retained_partial",
            reason="current_session_not_complete",
            terminal=terminal,
            schedule=schedule,
            topology=topology,
        ),
        baseline_run_id=baseline_run_id,
        baseline_completed_at=baseline_completed_at,
    )


def _validate_baseline(
    *,
    baseline_run_id: str | None,
    baseline_completed_at: datetime | None,
) -> None:
    if baseline_run_id is None and baseline_completed_at is None:
        return
    if baseline_run_id is None or baseline_completed_at is None:
        raise ValueError("baseline run ID and completion timestamp must be supplied together")
    if baseline_completed_at.tzinfo is None:
        raise ValueError("baseline completion timestamp must be timezone-aware")


def _require_later_marker(
    result: KisPaperIntradayInvocationReattachment,
    *,
    baseline_run_id: str | None,
    baseline_completed_at: datetime | None,
) -> KisPaperIntradayInvocationReattachment:
    if baseline_run_id is None or baseline_completed_at is None:
        return result
    if result.run_id != baseline_run_id and result.completed_at is not None:
        if result.completed_at > baseline_completed_at:
            return result
    return KisPaperIntradayInvocationReattachment(
        status="marker_not_later",
        reason="current_marker_is_not_later_than_baseline",
        invocation_phase=result.invocation_phase,
        run_id=result.run_id,
        started_at=result.started_at,
        schedule_observed_at=result.schedule_observed_at,
        completed_at=result.completed_at,
        invocation_receipt_sha256=result.invocation_receipt_sha256,
        schedule_receipt_sha256=result.schedule_receipt_sha256,
        invocation_receipt_pointer=result.invocation_receipt_pointer,
        schedule_receipt_pointer=result.schedule_receipt_pointer,
        topology_relation=result.topology_relation,
        topology_session_date=result.topology_session_date,
        collection_failure_category=result.collection_failure_category,
    )


def _marker_unavailable() -> KisPaperIntradayInvocationReattachment:
    return KisPaperIntradayInvocationReattachment(
        status="marker_unavailable",
        reason="current_marker_unavailable",
        invocation_phase="unavailable",
        run_id=None,
        started_at=None,
        schedule_observed_at=None,
        completed_at=None,
        invocation_receipt_sha256=None,
        schedule_receipt_sha256=None,
        invocation_receipt_pointer=None,
        schedule_receipt_pointer=None,
        topology_relation="not_observed",
        topology_session_date=None,
    )


def _start_only(
    runtime: KisPaperIntradayHeadInvocationRuntimeFact,
) -> KisPaperIntradayInvocationReattachment:
    return KisPaperIntradayInvocationReattachment(
        status="start_only",
        reason="terminal_marker_not_recorded",
        invocation_phase="started",
        run_id=runtime.run_id,
        started_at=runtime.observed_at,
        schedule_observed_at=None,
        completed_at=None,
        invocation_receipt_sha256=runtime.receipt_sha256,
        schedule_receipt_sha256=None,
        invocation_receipt_pointer=_invocation_receipt_pointer(
            run_id=runtime.run_id,
            phase="started",
        ),
        schedule_receipt_pointer=None,
        topology_relation="not_observed",
        topology_session_date=None,
    )


def _terminal_unavailable(
    runtime: KisPaperIntradayHeadInvocationRuntimeFact,
    *,
    reason: str,
) -> KisPaperIntradayInvocationReattachment:
    return KisPaperIntradayInvocationReattachment(
        status="terminal_unavailable",
        reason=reason,
        invocation_phase="terminal",
        run_id=runtime.run_id,
        started_at=None,
        schedule_observed_at=None,
        completed_at=runtime.observed_at,
        invocation_receipt_sha256=runtime.receipt_sha256,
        schedule_receipt_sha256=None,
        invocation_receipt_pointer=_invocation_receipt_pointer(
            run_id=runtime.run_id,
            phase="terminal",
        ),
        schedule_receipt_pointer=None,
        topology_relation="not_observed",
        topology_session_date=None,
    )


def _terminal_result(
    *,
    status: Literal["collector_nonzero", "retained_partial", "complete_session"],
    reason: str,
    terminal: KisPaperIntradayHeadInvocationTerminalFact,
    schedule: KisPaperIntradayHeadScheduleFact,
    topology: KisPaperIntradayCaptureTopology | None,
) -> KisPaperIntradayInvocationReattachment:
    session_date = terminal.schedule_observed_at.astimezone(_EASTERN_TZ).date()
    relation = _topology_relation(
        topology=topology,
        session_date=session_date,
        expected_complete=status == "complete_session",
    )
    return KisPaperIntradayInvocationReattachment(
        status=status,
        reason=reason,
        invocation_phase="terminal",
        run_id=terminal.run_id,
        started_at=terminal.started_at,
        schedule_observed_at=terminal.schedule_observed_at,
        completed_at=terminal.completed_at,
        invocation_receipt_sha256=terminal.receipt_sha256,
        schedule_receipt_sha256=schedule.receipt_sha256,
        invocation_receipt_pointer=_invocation_receipt_pointer(
            run_id=terminal.run_id,
            phase="terminal",
        ),
        schedule_receipt_pointer=(
            f"{KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY}/"
            f"{schedule.run_id}.json"
        ),
        topology_relation=relation,
        topology_session_date=session_date if topology is not None else None,
        collection_failure_category=terminal.collection_failure_category,
    )


def _topology_relation(
    *,
    topology: KisPaperIntradayCaptureTopology | None,
    session_date: date,
    expected_complete: bool,
) -> _TopologyRelation:
    if topology is None:
        return "not_observed"
    item = next(
        (
            candidate
            for candidate in topology.sessions
            if candidate.get("session_date") == session_date.isoformat()
        ),
        None,
    )
    if item is None:
        return "not_observed"
    expected_status = "complete" if expected_complete else "short"
    return (
        "current_metadata_consistent"
        if item.get("coverage_status") == expected_status
        else "current_metadata_diverged"
    )


def _utc_marker(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def _invocation_receipt_pointer(*, run_id: str, phase: Literal["started", "terminal"]) -> str:
    return f"{KIS_PAPER_INTRADAY_HEAD_INVOCATION_RECEIPT_DIRECTORY}/{run_id}/{phase}.json"

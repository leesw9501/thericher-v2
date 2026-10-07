"""Source-safe evidence for one bounded KIS Paper intraday capture attempt.

The existing private-intraday collector owns credentials, request pacing, the
single worker lock, source rows, and cache mutation. This module adds no KIS
calls. It projects one completed collector attempt into a D:-resident receipt
and exact regular-session coverage so downstream work can distinguish partial
head data from a complete 390-minute session.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import validate_kis_paper_minute_failure_diagnostic
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    KIS_PAPER_PRIVATE_INTRADAY_CONFLICT_ORIGINS,
    KIS_PAPER_PRIVATE_INTRADAY_RETAINED_HEAD_CONFLICT_DISPOSITIONS,
    KIS_PAPER_PRIVATE_INTRADAY_TARGETS,
    KisPaperPrivateIntradayBackfillRun,
    sanitize_kis_paper_private_intraday_failure_reason,
)

from .kis_intraday_head_coverage import (
    KisIntradayHeadCoverage,
    inspect_kis_paper_private_intraday_head_coverage,
)

KIS_PAPER_INTRADAY_SESSION_CAPTURE_KIND = "kis_paper_intraday_session_capture"
KIS_PAPER_INTRADAY_SESSION_CAPTURE_DIRECTORY = "session-capture"
KIS_PAPER_INTRADAY_SESSION_CAPTURE_AFTER_SESSION_DATE = date(2026, 1, 1)
KIS_PAPER_INTRADAY_SESSION_CAPTURE_REQUIRED_COMPLETE_SESSIONS = 1

_CAPTURE_SUCCEEDED_STATUSES = frozenset({"collected", "recovered", "source_exhausted"})
_CAPTURE_RUN_STATUSES = frozenset(
    {"collected", "partial", "rejected", "locked", "recovered", "source_exhausted"}
)
_EXPECTED_TARGET_KEYS = frozenset(
    f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_PAPER_PRIVATE_INTRADAY_TARGETS
)
_CAPTURE_TARGET_KEY = "QQQ/NAS/1m"
_EASTERN_TZ = ZoneInfo("America/New_York")
_SCHEDULE_RUN_ID_PATTERN = re.compile(r"\Aintraday-head-[0-9]{8}T[0-9]{6}(?:[0-9]{1,7})?Z\Z")
KIS_PAPER_INTRADAY_SESSION_CAPTURE_COVERAGE_CATEGORIES = frozenset({"complete", "incomplete"})


@dataclass(frozen=True)
class KisPaperIntradaySessionCaptureTarget:
    """An allowlisted, non-data-bearing summary of one target collection."""

    target_key: str
    status: Literal["collected", "partial", "rejected", "locked", "recovered", "source_exhausted"]
    row_count: int
    exact_overlap_rows: int
    reason: str | None
    conflict_origin: Literal["candidate_batch", "retained_cache"] | None = None
    retained_head_conflict_disposition: Literal["not_applicable", "preserved", "quarantined"] = (
        "not_applicable"
    )
    failure_phase: str | None = None
    failure_code: str | None = None
    failure_page_ordinal: int | None = None
    requested_pages_per_target: int | None = None

    def __post_init__(self) -> None:
        if self.target_key not in _EXPECTED_TARGET_KEYS:
            raise ValueError("session capture target is invalid")
        if self.status not in _CAPTURE_RUN_STATUSES:
            raise ValueError("session capture target status is invalid")
        if self.row_count < 0 or self.exact_overlap_rows < 0:
            raise ValueError("session capture target counts are invalid")
        validate_kis_paper_minute_failure_diagnostic(
            reason=self.reason,
            phase=self.failure_phase,
            code=self.failure_code,
            page_ordinal=self.failure_page_ordinal,
            requested_pages_per_target=self.requested_pages_per_target,
        )
        if self.failure_phase is not None and self.status not in {"partial", "rejected"}:
            raise ValueError("session capture failure diagnostic is invalid")
        if self.reason is not None:
            object.__setattr__(
                self,
                "reason",
                sanitize_kis_paper_private_intraday_failure_reason(self.reason),
            )
        if self.conflict_origin not in KIS_PAPER_PRIVATE_INTRADAY_CONFLICT_ORIGINS | {None}:
            raise ValueError("session capture target conflict origin is invalid")
        if (
            self.retained_head_conflict_disposition
            not in KIS_PAPER_PRIVATE_INTRADAY_RETAINED_HEAD_CONFLICT_DISPOSITIONS
        ):
            raise ValueError("session capture target conflict disposition is invalid")
        if self.conflict_origin is None:
            if self.retained_head_conflict_disposition != "not_applicable":
                raise ValueError("session capture target conflict disposition is invalid")
            return
        if self.status != "rejected" or self.reason != "minute_duplicate_conflict":
            raise ValueError("session capture target conflict provenance is invalid")
        if self.conflict_origin == "candidate_batch":
            if self.retained_head_conflict_disposition != "not_applicable":
                raise ValueError("session capture target conflict disposition is invalid")
            return
        if self.retained_head_conflict_disposition not in {"preserved", "quarantined"}:
            raise ValueError("session capture target conflict disposition is invalid")

    def to_payload(self) -> dict[str, object]:
        payload = {
            "target_key": self.target_key,
            "status": self.status,
            "row_count": self.row_count,
            "exact_overlap_rows": self.exact_overlap_rows,
            "reason": self.reason,
            "conflict_origin": self.conflict_origin,
            "retained_head_conflict_disposition": self.retained_head_conflict_disposition,
        }
        if self.failure_phase is not None:
            payload.update(
                failure_phase=self.failure_phase,
                failure_code=self.failure_code,
                failure_page_ordinal=self.failure_page_ordinal,
                requested_pages_per_target=self.requested_pages_per_target,
            )
        return payload


@dataclass(frozen=True)
class KisPaperIntradaySessionCaptureOutcome:
    """Metadata-only result of a bounded, one-client collector invocation."""

    status: Literal["complete", "incomplete"]
    observed_at: datetime
    targets: tuple[KisPaperIntradaySessionCaptureTarget, ...]
    coverage: KisIntradayHeadCoverage
    current_session_cumulative_coverage: KisIntradayHeadCoverage
    schedule_run_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        targets = tuple(self.targets)
        object.__setattr__(self, "targets", targets)
        if (
            len(targets) != len(_EXPECTED_TARGET_KEYS)
            or {item.target_key for item in targets} != _EXPECTED_TARGET_KEYS
        ):
            raise ValueError("session capture targets are incomplete")
        capture_target = next(item for item in targets if item.target_key == _CAPTURE_TARGET_KEY)
        expected_status = (
            "complete" if capture_target.status in _CAPTURE_SUCCEEDED_STATUSES else "incomplete"
        )
        if self.status != expected_status:
            raise ValueError("session capture aggregate status is invalid")
        if not isinstance(self.coverage, KisIntradayHeadCoverage):
            raise TypeError("session capture coverage is invalid")
        if not isinstance(self.current_session_cumulative_coverage, KisIntradayHeadCoverage):
            raise TypeError("session capture cumulative coverage is invalid")
        object.__setattr__(self, "schedule_run_id", validate_schedule_run_id(self.schedule_run_id))
        if self.schedule_run_id is not None:
            for target in targets:
                if target.failure_phase is not None and target.requested_pages_per_target != (
                    kis_paper_intraday_head_requested_page_budget(self.schedule_run_id)
                ):
                    raise ValueError("session capture requested page budget is invalid")

    @property
    def current_session_cumulative_coverage_digest(self) -> str:
        """Return the digest of the coverage payload and nothing else."""

        return (
            "sha256:"
            + hashlib.sha256(
                _canonical_json_bytes(self.current_session_cumulative_coverage.to_payload())
            ).hexdigest()
        )

    @property
    def current_session_cumulative_coverage_category(self) -> Literal["complete", "incomplete"]:
        """Classify only the ET session containing this capture observation."""

        current_session_date = self.observed_at.astimezone(_EASTERN_TZ).date()
        status = next(
            (
                item.status
                for item in self.current_session_cumulative_coverage.session_coverage
                if item.session_date == current_session_date
            ),
            None,
        )
        return "complete" if status == "complete" else "incomplete"

    def safe_payload(self) -> dict[str, object]:
        """Return the receipt body without provider rows, paths, or credentials."""

        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_INTRADAY_SESSION_CAPTURE_KIND,
            "status": self.status,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "collection_mode": "session_capture",
            "capture_target_key": _CAPTURE_TARGET_KEY,
            "observed_at": self.observed_at.isoformat(),
            "storage": "external_market_data_only",
            "targets": [item.to_payload() for item in self.targets],
            "coverage": self.coverage.to_payload(),
            "current_session_cumulative_coverage": (
                self.current_session_cumulative_coverage.to_payload()
            ),
        }
        if self.schedule_run_id is not None:
            payload["schedule_run_id"] = self.schedule_run_id
            payload["current_session_cumulative_coverage_digest"] = (
                self.current_session_cumulative_coverage_digest
            )
            payload["current_session_cumulative_coverage_category"] = (
                self.current_session_cumulative_coverage_category
            )
        return payload


@dataclass(frozen=True)
class KisPaperIntradaySessionCaptureResult:
    outcome: KisPaperIntradaySessionCaptureOutcome
    evidence_path: Path
    evidence_sha256: str = ""

    def terminal_receipt_binding(self) -> dict[str, str] | None:
        """Return the all-or-none terminal binding without an evidence path."""

        if self.outcome.schedule_run_id is None:
            return None
        return {
            "schedule_run_id": self.outcome.schedule_run_id,
            "observed_at": self.outcome.observed_at.isoformat(),
            "receipt_sha256": self.evidence_sha256,
            "current_session_cumulative_coverage_digest": (
                self.outcome.current_session_cumulative_coverage_digest
            ),
            "current_session_cumulative_coverage_category": (
                self.outcome.current_session_cumulative_coverage_category
            ),
        }

    def safe_output_payload(self) -> dict[str, object]:
        """Return source-safe output and, when bound, terminal receipt input."""

        payload = self.outcome.safe_payload()
        binding = self.terminal_receipt_binding()
        if binding is not None:
            payload["terminal_receipt_binding"] = binding
        return payload


def build_kis_paper_intraday_session_capture_outcome(
    *,
    runs: Sequence[KisPaperPrivateIntradayBackfillRun],
    cache_root: Path,
    repository_root: Path,
    observed_at: datetime,
    schedule_run_id: str | None = None,
    coverage_after_session_date: date = KIS_PAPER_INTRADAY_SESSION_CAPTURE_AFTER_SESSION_DATE,
    required_complete_session_count: int = (
        KIS_PAPER_INTRADAY_SESSION_CAPTURE_REQUIRED_COMPLETE_SESSIONS
    ),
) -> KisPaperIntradaySessionCaptureOutcome:
    """Classify one capture and its current ET session without opening raw rows."""

    if type(coverage_after_session_date) is not date:
        raise ValueError("session capture coverage date is invalid")
    if type(required_complete_session_count) is not int or required_complete_session_count <= 0:
        raise ValueError("session capture complete-session count is invalid")
    observed_at = require_utc(observed_at, "observed_at")
    schedule_run_id = validate_schedule_run_id(schedule_run_id)
    targets = _capture_targets(runs)
    capture_manifest_hashes = frozenset(
        run.manifest_hash
        for run in runs
        if run.target_key == _CAPTURE_TARGET_KEY and run.manifest_hash is not None
    )
    coverage = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=repository_root,
        after_session_date=coverage_after_session_date,
        required_complete_session_count=required_complete_session_count,
        manifest_hashes=capture_manifest_hashes,
    )
    current_session_date = observed_at.astimezone(_EASTERN_TZ).date()
    current_session_cumulative_coverage = inspect_kis_paper_private_intraday_head_coverage(
        cache_root=cache_root,
        repo_root=repository_root,
        after_session_date=current_session_date - timedelta(days=1),
        required_complete_session_count=1,
        through_session_date=current_session_date,
    )
    capture_target = next(item for item in targets if item.target_key == _CAPTURE_TARGET_KEY)
    status: Literal["complete", "incomplete"] = (
        "complete" if capture_target.status in _CAPTURE_SUCCEEDED_STATUSES else "incomplete"
    )
    return KisPaperIntradaySessionCaptureOutcome(
        status=status,
        observed_at=observed_at,
        targets=targets,
        coverage=coverage,
        current_session_cumulative_coverage=current_session_cumulative_coverage,
        schedule_run_id=schedule_run_id,
    )


def write_kis_paper_intraday_session_capture_evidence(
    outcome: KisPaperIntradaySessionCaptureOutcome,
    *,
    cache_root: Path,
    repository_root: Path,
) -> Path:
    """Write immutable source-safe capture evidence below the external cache root."""

    root = _capture_evidence_root(cache_root=cache_root, repository_root=repository_root)
    encoded = _evidence_bytes(outcome)
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    destination = root / f"{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
    _validate_capture_evidence_destination(root=root, destination=destination)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("session capture evidence conflicts")
        return destination
    root.mkdir(parents=True, exist_ok=True)
    _validate_capture_evidence_destination(root=root, destination=destination)
    staging = root / f".{digest}.{uuid.uuid4().hex[:8]}.stage"
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def build_and_write_kis_paper_intraday_session_capture(
    *,
    runs: Sequence[KisPaperPrivateIntradayBackfillRun],
    cache_root: Path,
    repository_root: Path,
    observed_at: datetime,
    schedule_run_id: str | None = None,
) -> KisPaperIntradaySessionCaptureResult:
    """Produce D:-resident coverage evidence after the existing collector releases its lock."""

    outcome = build_kis_paper_intraday_session_capture_outcome(
        runs=runs,
        cache_root=cache_root,
        repository_root=repository_root,
        observed_at=observed_at,
        schedule_run_id=schedule_run_id,
    )
    evidence_sha256 = _evidence_sha256(outcome)
    return KisPaperIntradaySessionCaptureResult(
        outcome=outcome,
        evidence_path=write_kis_paper_intraday_session_capture_evidence(
            outcome,
            cache_root=cache_root,
            repository_root=repository_root,
        ),
        evidence_sha256=evidence_sha256,
    )


def validate_schedule_run_id(value: str | None) -> str | None:
    """Accept an unbound capture or the scheduler's canonical safe run identifier."""

    if value is None:
        return None
    if type(value) is not str or _SCHEDULE_RUN_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("schedule run ID is invalid")
    return value


def kis_paper_intraday_head_requested_page_budget(schedule_run_id: str) -> int:
    """Match the existing launcher's 4/8-page contract at its frozen run start."""

    if validate_schedule_run_id(schedule_run_id) is None:
        raise ValueError("schedule run ID is invalid")
    stamp = schedule_run_id.removeprefix("intraday-head-")
    started_at = datetime.strptime(stamp[:15], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    eastern = started_at.astimezone(_EASTERN_TZ)
    if eastern.weekday() < 5 and time(16, 20) <= eastern.time() < time(20):
        return 8
    return 4


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _evidence_bytes(outcome: KisPaperIntradaySessionCaptureOutcome) -> bytes:
    return _canonical_json_bytes(outcome.safe_payload()) + b"\n"


def _evidence_sha256(outcome: KisPaperIntradaySessionCaptureOutcome) -> str:
    return "sha256:" + hashlib.sha256(_evidence_bytes(outcome)).hexdigest()


def _capture_targets(
    runs: Sequence[KisPaperPrivateIntradayBackfillRun],
) -> tuple[KisPaperIntradaySessionCaptureTarget, ...]:
    values = tuple(runs)
    if (
        len(values) != len(_EXPECTED_TARGET_KEYS)
        or {run.target_key for run in values} != _EXPECTED_TARGET_KEYS
    ):
        raise ValueError("session capture collector results are incomplete")
    if any(
        run.reason == "minute_duplicate_conflict" and run.conflict_origin is None for run in values
    ):
        raise ValueError("session capture conflict provenance is invalid")
    return tuple(
        KisPaperIntradaySessionCaptureTarget(
            target_key=run.target_key,
            status=run.status,
            row_count=run.row_count,
            exact_overlap_rows=run.exact_overlap_rows,
            reason=run.reason,
            conflict_origin=run.conflict_origin,
            retained_head_conflict_disposition=run.retained_head_conflict_disposition,
            failure_phase=run.failure_phase,
            failure_code=run.failure_code,
            failure_page_ordinal=run.failure_page_ordinal,
            requested_pages_per_target=run.requested_pages_per_target,
        )
        for run in values
    )


def _capture_evidence_root(*, cache_root: Path, repository_root: Path) -> Path:
    supplied_root = Path(cache_root)
    if supplied_root.is_symlink():
        raise ValueError("session capture cache root is invalid")
    resolved_cache = supplied_root.resolve()
    resolved_repository = Path(repository_root).resolve()
    if resolved_cache.is_relative_to(resolved_repository):
        raise ValueError("session capture cache root must stay outside the Git workspace")
    version_root = resolved_cache / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    if version_root.is_symlink():
        raise ValueError("session capture cache root is invalid")
    return version_root / KIS_PAPER_INTRADAY_SESSION_CAPTURE_DIRECTORY


def _validate_capture_evidence_destination(*, root: Path, destination: Path) -> None:
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("session capture evidence root is invalid")
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("session capture evidence destination is invalid")
    if not destination.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValueError("session capture evidence destination is invalid")

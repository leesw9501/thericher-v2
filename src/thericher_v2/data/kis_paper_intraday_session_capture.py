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
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
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


@dataclass(frozen=True)
class KisPaperIntradaySessionCaptureTarget:
    """An allowlisted, non-data-bearing summary of one target collection."""

    target_key: str
    status: Literal["collected", "partial", "rejected", "locked", "recovered", "source_exhausted"]
    row_count: int
    exact_overlap_rows: int
    reason: str | None

    def __post_init__(self) -> None:
        if self.target_key not in _EXPECTED_TARGET_KEYS:
            raise ValueError("session capture target is invalid")
        if self.status not in _CAPTURE_RUN_STATUSES:
            raise ValueError("session capture target status is invalid")
        if self.row_count < 0 or self.exact_overlap_rows < 0:
            raise ValueError("session capture target counts are invalid")
        if self.reason is not None:
            object.__setattr__(
                self,
                "reason",
                sanitize_kis_paper_private_intraday_failure_reason(self.reason),
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "status": self.status,
            "row_count": self.row_count,
            "exact_overlap_rows": self.exact_overlap_rows,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class KisPaperIntradaySessionCaptureOutcome:
    """Metadata-only result of a bounded, one-client collector invocation."""

    status: Literal["complete", "incomplete"]
    observed_at: datetime
    targets: tuple[KisPaperIntradaySessionCaptureTarget, ...]
    coverage: KisIntradayHeadCoverage
    current_session_cumulative_coverage: KisIntradayHeadCoverage
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

    def safe_payload(self) -> dict[str, object]:
        """Return the receipt body without provider rows, paths, or credentials."""

        return {
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


@dataclass(frozen=True)
class KisPaperIntradaySessionCaptureResult:
    outcome: KisPaperIntradaySessionCaptureOutcome
    evidence_path: Path


def build_kis_paper_intraday_session_capture_outcome(
    *,
    runs: Sequence[KisPaperPrivateIntradayBackfillRun],
    cache_root: Path,
    repository_root: Path,
    observed_at: datetime,
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
    current_session_cumulative_coverage = (
        inspect_kis_paper_private_intraday_head_coverage(
            cache_root=cache_root,
            repo_root=repository_root,
            after_session_date=current_session_date - timedelta(days=1),
            required_complete_session_count=1,
            through_session_date=current_session_date,
        )
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
    )


def write_kis_paper_intraday_session_capture_evidence(
    outcome: KisPaperIntradaySessionCaptureOutcome,
    *,
    cache_root: Path,
    repository_root: Path,
) -> Path:
    """Write immutable source-safe capture evidence below the external cache root."""

    root = _capture_evidence_root(cache_root=cache_root, repository_root=repository_root)
    payload = json.dumps(outcome.safe_payload(), ensure_ascii=True, sort_keys=True) + "\n"
    encoded = payload.encode("utf-8")
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
) -> KisPaperIntradaySessionCaptureResult:
    """Produce D:-resident coverage evidence after the existing collector releases its lock."""

    outcome = build_kis_paper_intraday_session_capture_outcome(
        runs=runs,
        cache_root=cache_root,
        repository_root=repository_root,
        observed_at=observed_at,
    )
    return KisPaperIntradaySessionCaptureResult(
        outcome=outcome,
        evidence_path=write_kis_paper_intraday_session_capture_evidence(
            outcome,
            cache_root=cache_root,
            repository_root=repository_root,
        ),
    )


def _capture_targets(
    runs: Sequence[KisPaperPrivateIntradayBackfillRun],
) -> tuple[KisPaperIntradaySessionCaptureTarget, ...]:
    values = tuple(runs)
    if (
        len(values) != len(_EXPECTED_TARGET_KEYS)
        or {run.target_key for run in values} != _EXPECTED_TARGET_KEYS
    ):
        raise ValueError("session capture collector results are incomplete")
    return tuple(
        KisPaperIntradaySessionCaptureTarget(
            target_key=run.target_key,
            status=run.status,
            row_count=run.row_count,
            exact_overlap_rows=run.exact_overlap_rows,
            reason=run.reason,
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

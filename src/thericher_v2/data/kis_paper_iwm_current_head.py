"""Source-safe evidence for one isolated KIS Paper IWM current-head cache run."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import KisPaperMarketDataCallCounts
from thericher_v2.execution.kis_private_intraday_backfill import (
    KisPaperPrivateIntradayBackfillRun,
    sanitize_kis_paper_private_intraday_failure_reason,
)

KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_KIND = "kis_paper_iwm_m1_current_head_ingestion"
KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_ARTIFACT_DIRECTORY = (
    "data/kis-paper-iwm-m1-current-head-ingestion"
)
KIS_PAPER_IWM_CURRENT_HEAD_TARGET_KEY = "IWM/AMS/1m"

_SAFE_LOCK_REASON = "worker_locked"


@dataclass(frozen=True, slots=True)
class KisPaperIwmCurrentHeadIngestionOutcome:
    """A metadata-only result for one current-day IWM page attempt."""

    status: Literal["accepted", "recovered", "unavailable", "locked"]
    observed_at: datetime
    response_category: Literal["accepted", "already_cached", "error", "worker_locked"]
    accepted_page_count: int
    minute_page_request_count: int
    token_request_count: int
    pace_bucket: Literal["not_started", "shared_gate_observed", "shared_gate_evidence_incomplete"]
    next_recovery_fact: Literal[
        "current_head_only_reobservation",
        "fresh_one_page_invocation_required",
        "isolated_worker_lock_release_required",
    ]
    reason: str | None
    raw_market_data_retained: bool
    target_key: str = KIS_PAPER_IWM_CURRENT_HEAD_TARGET_KEY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if (
            self.target_key != KIS_PAPER_IWM_CURRENT_HEAD_TARGET_KEY
            or self.schema_version != SCHEMA_VERSION
            or self.accepted_page_count not in {0, 1}
            or self.minute_page_request_count not in {0, 1}
            or self.token_request_count not in {0, 1}
        ):
            raise ValueError("IWM current-head ingestion outcome is invalid")
        if self.status == "accepted":
            if (
                self.response_category != "accepted"
                or self.accepted_page_count != 1
                or self.minute_page_request_count != 1
                or self.reason is not None
                or not self.raw_market_data_retained
                or self.next_recovery_fact != "current_head_only_reobservation"
            ):
                raise ValueError("IWM current-head ingestion outcome is invalid")
        elif self.status == "recovered":
            if (
                self.response_category != "already_cached"
                or self.accepted_page_count != 1
                or self.minute_page_request_count != 1
                or self.reason not in {None, "already_cached"}
                or self.raw_market_data_retained
                or self.next_recovery_fact != "current_head_only_reobservation"
            ):
                raise ValueError("IWM current-head ingestion outcome is invalid")
        elif self.status == "unavailable":
            if (
                self.response_category != "error"
                or self.accepted_page_count != 0
                or self.raw_market_data_retained
                or not self.reason
                or self.next_recovery_fact != "fresh_one_page_invocation_required"
            ):
                raise ValueError("IWM current-head ingestion outcome is invalid")
        elif self.status == "locked":
            if (
                self.response_category != "worker_locked"
                or self.accepted_page_count != 0
                or self.minute_page_request_count != 0
                or self.token_request_count != 0
                or self.raw_market_data_retained
                or self.reason != _SAFE_LOCK_REASON
                or self.next_recovery_fact != "isolated_worker_lock_release_required"
            ):
                raise ValueError("IWM current-head ingestion outcome is invalid")
        else:
            raise ValueError("IWM current-head ingestion outcome is invalid")
        if self.pace_bucket == "not_started" and (
            self.minute_page_request_count or self.token_request_count
        ):
            raise ValueError("IWM current-head ingestion pace bucket is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return only categorical execution facts, never rows, prices, or paths."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_KIND,
            "status": self.status,
            "response_category": self.response_category,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": self.target_key,
            "request_scope": "one_current_day_page_no_previous_day_no_continuation",
            "observed_at": self.observed_at.isoformat(),
            "accepted_page_count": self.accepted_page_count,
            "minute_page_request_count": self.minute_page_request_count,
            "token_request_count": self.token_request_count,
            "pace_bucket": self.pace_bucket,
            "next_recovery_fact": self.next_recovery_fact,
            "reason": self.reason,
            "raw_market_data_retained": self.raw_market_data_retained,
            "storage": "external_market_data_only",
            "does_not_establish": [
                "historical_intraday_reach",
                "session_finality",
                "decision_time_availability",
                "dataset_qualification",
                "model_or_paper_input_eligibility",
            ],
        }


@dataclass(frozen=True, slots=True)
class KisPaperIwmCurrentHeadIngestionResult:
    outcome: KisPaperIwmCurrentHeadIngestionOutcome
    evidence_path: Path = field(repr=False)


def build_kis_paper_iwm_current_head_ingestion_outcome(
    *,
    run: KisPaperPrivateIntradayBackfillRun,
    call_counts: KisPaperMarketDataCallCounts,
    request_start_count: int,
    observed_at: datetime,
) -> KisPaperIwmCurrentHeadIngestionOutcome:
    """Project one collector result without exposing its cache or source rows."""

    if (
        run.target_key != KIS_PAPER_IWM_CURRENT_HEAD_TARGET_KEY
        or call_counts.daily_page_attempts != 0
        or call_counts.minute_page_attempts not in {0, 1}
        or call_counts.token_attempts not in {0, 1}
        or type(request_start_count) is not int
        or request_start_count < 0
    ):
        raise ValueError("IWM current-head ingestion inputs are invalid")
    pace_bucket = _pace_bucket(
        token_request_count=call_counts.token_attempts,
        minute_page_request_count=call_counts.minute_page_attempts,
        request_start_count=request_start_count,
    )
    if run.status == "collected":
        return KisPaperIwmCurrentHeadIngestionOutcome(
            status="accepted",
            observed_at=observed_at,
            response_category="accepted",
            accepted_page_count=1,
            minute_page_request_count=call_counts.minute_page_attempts,
            token_request_count=call_counts.token_attempts,
            pace_bucket=pace_bucket,
            next_recovery_fact="current_head_only_reobservation",
            reason=None,
            raw_market_data_retained=run.manifest_hash is not None,
        )
    if run.status == "recovered":
        return KisPaperIwmCurrentHeadIngestionOutcome(
            status="recovered",
            observed_at=observed_at,
            response_category="already_cached",
            accepted_page_count=int(call_counts.minute_page_attempts == 1),
            minute_page_request_count=call_counts.minute_page_attempts,
            token_request_count=call_counts.token_attempts,
            pace_bucket=pace_bucket,
            next_recovery_fact="current_head_only_reobservation",
            reason=run.reason,
            raw_market_data_retained=False,
        )
    if run.status == "locked":
        return KisPaperIwmCurrentHeadIngestionOutcome(
            status="locked",
            observed_at=observed_at,
            response_category="worker_locked",
            accepted_page_count=0,
            minute_page_request_count=0,
            token_request_count=0,
            pace_bucket="not_started",
            next_recovery_fact="isolated_worker_lock_release_required",
            reason=_SAFE_LOCK_REASON,
            raw_market_data_retained=False,
        )
    if run.status == "rejected":
        return KisPaperIwmCurrentHeadIngestionOutcome(
            status="unavailable",
            observed_at=observed_at,
            response_category="error",
            accepted_page_count=0,
            minute_page_request_count=call_counts.minute_page_attempts,
            token_request_count=call_counts.token_attempts,
            pace_bucket=pace_bucket,
            next_recovery_fact="fresh_one_page_invocation_required",
            reason=sanitize_kis_paper_private_intraday_failure_reason(run.reason or ""),
            raw_market_data_retained=False,
        )
    raise ValueError("IWM current-head ingestion result is invalid")


def write_kis_paper_iwm_current_head_ingestion_evidence(
    outcome: KisPaperIwmCurrentHeadIngestionOutcome,
    *,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Write one canonical source-safe receipt outside the Git workspace."""

    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    payload = json.dumps(outcome.safe_payload(), ensure_ascii=True, sort_keys=True) + "\n"
    encoded = payload.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    destination_root = root / KIS_PAPER_IWM_CURRENT_HEAD_INGESTION_ARTIFACT_DIRECTORY
    _ensure_real_directory(destination_root)
    filename = f"{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
    destination = destination_root / filename
    _validate_destination(root=root, destination=destination)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("IWM current-head ingestion evidence conflicts")
        return destination
    staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def build_and_write_kis_paper_iwm_current_head_ingestion(
    *,
    run: KisPaperPrivateIntradayBackfillRun,
    call_counts: KisPaperMarketDataCallCounts,
    request_start_count: int,
    observed_at: datetime,
    artifact_root: Path,
    repository_root: Path,
) -> KisPaperIwmCurrentHeadIngestionResult:
    outcome = build_kis_paper_iwm_current_head_ingestion_outcome(
        run=run,
        call_counts=call_counts,
        request_start_count=request_start_count,
        observed_at=observed_at,
    )
    return KisPaperIwmCurrentHeadIngestionResult(
        outcome=outcome,
        evidence_path=write_kis_paper_iwm_current_head_ingestion_evidence(
            outcome,
            artifact_root=artifact_root,
            repository_root=repository_root,
        ),
    )


def _pace_bucket(
    *,
    token_request_count: int,
    minute_page_request_count: int,
    request_start_count: int,
) -> Literal["not_started", "shared_gate_observed", "shared_gate_evidence_incomplete"]:
    request_count = token_request_count + minute_page_request_count
    if request_count == 0:
        return "not_started"
    return (
        "shared_gate_observed"
        if request_start_count == request_count
        else "shared_gate_evidence_incomplete"
    )


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = validate_kis_paper_iwm_current_head_ingestion_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    _ensure_real_directory(root)
    return root


def validate_kis_paper_iwm_current_head_ingestion_artifact_root(
    *,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Validate the external evidence destination without creating it."""

    supplied = Path(artifact_root)
    if supplied.is_symlink():
        raise ValueError("IWM current-head ingestion artifact root is invalid")
    root = supplied.resolve(strict=False)
    repository = Path(repository_root).resolve(strict=False)
    if root.is_relative_to(repository):
        raise ValueError("IWM current-head ingestion artifact root must stay outside Git")
    if root.exists() and not root.is_dir():
        raise ValueError("IWM current-head ingestion artifact root is invalid")
    return root


def _ensure_real_directory(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("IWM current-head ingestion artifact destination is invalid")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("IWM current-head ingestion artifact destination is invalid")


def _validate_destination(*, root: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("IWM current-head ingestion evidence destination is invalid")
    if not destination.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValueError("IWM current-head ingestion evidence destination is invalid")

"""Isolated SPY 1m paginated-prefix capability contracts.

The credential-bearing collector supplies raw KIS minute pages to this module,
which stores them only under the external market-data root.  The observer uses
the same module without importing an Execution path or reading environment
state: it validates one exact fresh run and writes only a source-safe receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.us_equity_session import us_equity_2026_session

KIS_SPY_PAGINATED_PREFIX_CAPABILITY_KIND = "kis_spy_paginated_prefix_capability"
KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND = "kis_spy_paginated_prefix_collection"
KIS_SPY_PAGINATED_PREFIX_RAW_KIND = "kis_spy_paginated_prefix_raw_pages"
KIS_SPY_PAGINATED_PREFIX_FACT_KIND = "kis_spy_paginated_prefix_capability_fact"
KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID = "kis-spy-paginated-prefix-capability-v1"
KIS_SPY_PAGINATED_PREFIX_TARGET = "SPY/AMS/1m"
KIS_SPY_PAGINATED_PREFIX_MAX_PAGES = 4
KIS_SPY_PAGINATED_PREFIX_MAX_ROWS_PER_PAGE = 120
KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES = 360
KIS_SPY_PAGINATED_PREFIX_CACHE_DIRECTORY = "spy-paginated-prefix-capability-v1"
KIS_SPY_PAGINATED_PREFIX_ARTIFACT_DIRECTORY = "data/kis-spy-paginated-prefix-capability-v1"

_EASTERN = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_DECISION_CUTOFF = time(15, 30)
_NEGATIVE_CONTROL_START = time(15, 29, 30)
_VALIDITY = timedelta(minutes=1)
_RAW_COLUMNS = frozenset({"xymd", "xhms", "kymd", "khms", "open", "high", "low", "last", "evol"})
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}", re.ASCII)
_DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\spy-paginated-prefix-capability"
)
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

CollectionStatus = Literal["collected", "partial"]
ControlStatus = Literal["negative_control_clean", "negative_control_violation"]
PreflightStatus = Literal[
    "ready", "outside_stage_window", "control_unavailable", "control_not_clean"
]
ObservationStatus = Literal[
    "availability_within_validity_after_collection",
    "outside_stage_window",
    "control_unavailable",
    "control_not_clean",
    "collection_unavailable",
    "fresh_run_invalid",
    "page_seam_invalid",
    "incomplete_prefix",
    "capture_expired",
]
FactResultClass = Literal[
    "post_collection_completed_prefix",
    "measurement_incomplete_or_invalid",
    "no_capability_measurement",
]
ContinuationSignal = Literal[
    "recognized_continuation",
    "blank_or_absent",
    "unrecognized_nonblank",
    "not_recorded_legacy",
]


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixPage:
    """One retained raw page with enough metadata to validate its seam later."""

    index: int
    rows: tuple[dict[str, str], ...]
    continuation_advertised: bool
    continuation_signal: ContinuationSignal | None = None

    def __post_init__(self) -> None:
        if (
            self.index <= 0
            or not self.rows
            or len(self.rows) > KIS_SPY_PAGINATED_PREFIX_MAX_ROWS_PER_PAGE
        ):
            raise ValueError("SPY paginated prefix page is invalid")
        object.__setattr__(self, "rows", tuple(_normalize_raw_row(row) for row in self.rows))
        if type(self.continuation_advertised) is not bool:
            raise ValueError("SPY paginated prefix page continuation is invalid")
        signal = self.continuation_signal
        if signal is None:
            signal = (
                "recognized_continuation"
                if self.continuation_advertised
                else "blank_or_absent"
            )
        if not isinstance(signal, str) or signal not in {
            "recognized_continuation",
            "blank_or_absent",
            "unrecognized_nonblank",
            "not_recorded_legacy",
        }:
            raise ValueError("SPY paginated prefix page continuation signal is invalid")
        if signal != "not_recorded_legacy" and (
            self.continuation_advertised != (signal == "recognized_continuation")
        ):
            raise ValueError("SPY paginated prefix page continuation signal is invalid")
        object.__setattr__(self, "continuation_signal", signal)


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixCollection:
    """One bounded same-client result before external-cache persistence."""

    status: CollectionStatus
    reason: str | None
    pages: tuple[KisSpyPaginatedPrefixPage, ...]

    def __post_init__(self) -> None:
        if self.status not in {"collected", "partial"}:
            raise ValueError("SPY paginated prefix collection status is invalid")
        object.__setattr__(self, "pages", tuple(self.pages))
        if len(self.pages) > KIS_SPY_PAGINATED_PREFIX_MAX_PAGES:
            raise ValueError("SPY paginated prefix collection pages are invalid")
        if self.status == "collected" and not self.pages:
            raise ValueError("SPY paginated prefix collected pages are invalid")
        if self.status == "partial" and self.reason is None:
            raise ValueError("SPY paginated prefix partial reason is invalid")
        if tuple(page.index for page in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise ValueError("SPY paginated prefix page indices are invalid")
        if self.reason is not None and _SAFE_REASON.fullmatch(self.reason) is None:
            raise ValueError("SPY paginated prefix collection reason is invalid")


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixCollectionRun:
    """External raw-cache run.  ``safe_payload`` deliberately contains no rows."""

    run_id: str
    session_date: date
    collection_started_at: datetime
    collection: KisSpyPaginatedPrefixCollection
    token_attempts: int
    minute_page_attempts: int
    raw_content_sha256: str
    manifest_path: Path = field(repr=False)

    def __post_init__(self) -> None:
        _require_safe_id(self.run_id)
        if type(self.session_date) is not date:
            raise ValueError("SPY paginated prefix session date is invalid")
        object.__setattr__(
            self,
            "collection_started_at",
            require_utc(self.collection_started_at, "collection_started_at"),
        )
        if not isinstance(self.collection, KisSpyPaginatedPrefixCollection):
            raise ValueError("SPY paginated prefix collection run is invalid")
        if not 0 <= self.token_attempts <= 1:
            raise ValueError("SPY paginated prefix token attempts are invalid")
        if not 0 <= self.minute_page_attempts <= KIS_SPY_PAGINATED_PREFIX_MAX_PAGES:
            raise ValueError("SPY paginated prefix page attempts are invalid")
        if self.minute_page_attempts < len(self.collection.pages):
            raise ValueError("SPY paginated prefix page attempts are invalid")
        if not _is_sha256(self.raw_content_sha256):
            raise ValueError("SPY paginated prefix raw hash is invalid")
        if not isinstance(self.manifest_path, Path) or self.manifest_path.name != "manifest.json":
            raise ValueError("SPY paginated prefix manifest path is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
            "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
            "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
            "run_id": self.run_id,
            "session_date": self.session_date.isoformat(),
            "collection_started_at": _time_payload(self.collection_started_at),
            "collection": {
                "status": self.collection.status,
                "reason": self.collection.reason,
                "page_count": len(self.collection.pages),
                "continuation_advertised_on_final_page": (
                    None
                    if not self.collection.pages
                    else self.collection.pages[-1].continuation_advertised
                ),
                "terminal_continuation_signal": (
                    None
                    if not self.collection.pages
                    else self.collection.pages[-1].continuation_signal
                ),
            },
            "client": {
                "single_in_memory_client": True,
                "token_attempts": self.token_attempts,
                "minute_page_attempts": self.minute_page_attempts,
                "maximum_minute_page_attempts": KIS_SPY_PAGINATED_PREFIX_MAX_PAGES,
            },
            "raw_content_sha256": self.raw_content_sha256,
        }


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixControl:
    """A cache-presence negative control recorded before the 15:30 boundary."""

    status: ControlStatus
    session_date: date
    run_id: str
    observed_at: datetime
    artifact_path: Path = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"negative_control_clean", "negative_control_violation"}:
            raise ValueError("SPY paginated prefix control status is invalid")
        if type(self.session_date) is not date:
            raise ValueError("SPY paginated prefix control session date is invalid")
        _require_safe_id(self.run_id)
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if (
            not isinstance(self.artifact_path, Path)
            or self.artifact_path.name != "negative-control.json"
        ):
            raise ValueError("SPY paginated prefix control path is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("SPY paginated prefix control schema version is invalid")

    @property
    def valid_for_collection(self) -> bool:
        return self.status == "negative_control_clean"

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_SPY_PAGINATED_PREFIX_CAPABILITY_KIND,
            "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
            "phase": "negative_control",
            "status": self.status,
            "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
            "session_date": self.session_date.isoformat(),
            "run_id": self.run_id,
            "timing": {"observed_at": _time_payload(self.observed_at)},
            "control": {
                "scope": "dedicated_fresh_run_namespace_absence",
                "fresh_run_absent_before_cutoff": self.valid_for_collection,
                "source_availability": "not_observed",
                "completed_minute_predicate": "exchange_timestamp_plus_1m_at_or_before_1530_et",
                "positive_collection_permitted": self.valid_for_collection,
            },
            "decision_time_availability": "not_observed",
        }


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixPreflight:
    status: PreflightStatus
    session_date: date
    run_id: str
    observed_at: datetime
    control: KisSpyPaginatedPrefixControl | None = field(repr=False)

    def __post_init__(self) -> None:
        if self.status not in {
            "ready",
            "outside_stage_window",
            "control_unavailable",
            "control_not_clean",
        }:
            raise ValueError("SPY paginated prefix preflight status is invalid")
        if type(self.session_date) is not date:
            raise ValueError("SPY paginated prefix preflight session date is invalid")
        _require_safe_id(self.run_id)
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.status == "ready" and (
            self.control is None or not self.control.valid_for_collection
        ):
            raise ValueError("SPY paginated prefix ready preflight is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_SPY_PAGINATED_PREFIX_CAPABILITY_KIND,
            "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
            "phase": "positive_preflight",
            "status": self.status,
            "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
            "session_date": self.session_date.isoformat(),
            "run_id": self.run_id,
            "timing": {"observed_at": _time_payload(self.observed_at)},
            "negative_control_status": None if self.control is None else self.control.status,
            "decision_time_availability": "not_observed",
        }


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixObservation:
    """A source-safe outcome from one exact collection run."""

    status: ObservationStatus
    session_date: date
    run_id: str
    collection_started_at: datetime
    collector_returned_at: datetime
    observer_started_at: datetime
    observer_finished_at: datetime
    collection_exit_code: int
    control_status: str | None
    collection_status: str | None
    page_count: int | None
    terminal_continuation_signal: ContinuationSignal | None
    complete_minute_count: int | None
    missing_minute_count: int | None
    page_seam_status: str | None
    raw_content_sha256: str | None
    artifact_path: Path = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {
            "availability_within_validity_after_collection",
            "outside_stage_window",
            "control_unavailable",
            "control_not_clean",
            "collection_unavailable",
            "fresh_run_invalid",
            "page_seam_invalid",
            "incomplete_prefix",
            "capture_expired",
        }:
            raise ValueError("SPY paginated prefix observation status is invalid")
        if type(self.session_date) is not date:
            raise ValueError("SPY paginated prefix observation session date is invalid")
        _require_safe_id(self.run_id)
        for name in (
            "collection_started_at",
            "collector_returned_at",
            "observer_started_at",
            "observer_finished_at",
        ):
            object.__setattr__(self, name, require_utc(getattr(self, name), name))
        if self.collection_exit_code < 0:
            raise ValueError("SPY paginated prefix collection exit code is invalid")
        for value in (self.page_count, self.complete_minute_count, self.missing_minute_count):
            if value is not None and value < 0:
                raise ValueError("SPY paginated prefix observation counts are invalid")
        if self.page_count is not None and self.page_count > KIS_SPY_PAGINATED_PREFIX_MAX_PAGES:
            raise ValueError("SPY paginated prefix observation page count is invalid")
        if self.terminal_continuation_signal is not None and (
            not isinstance(self.terminal_continuation_signal, str)
            or self.terminal_continuation_signal
            not in {
                "recognized_continuation",
                "blank_or_absent",
                "unrecognized_nonblank",
                "not_recorded_legacy",
            }
        ):
            raise ValueError("SPY paginated prefix observation continuation signal is invalid")
        if self.raw_content_sha256 is not None and not _is_sha256(self.raw_content_sha256):
            raise ValueError("SPY paginated prefix observation raw hash is invalid")
        if not isinstance(self.artifact_path, Path) or self.artifact_path.name != "evidence.json":
            raise ValueError("SPY paginated prefix observation artifact path is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("SPY paginated prefix observation schema version is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_SPY_PAGINATED_PREFIX_CAPABILITY_KIND,
            "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
            "phase": "positive_observation",
            "status": self.status,
            "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
            "session_date": self.session_date.isoformat(),
            "run_id": self.run_id,
            "timing": {
                "collection_started_at": _time_payload(self.collection_started_at),
                "collector_returned_at": _time_payload(self.collector_returned_at),
                "observer_started_at": _time_payload(self.observer_started_at),
                "observer_finished_at": _time_payload(self.observer_finished_at),
                "validity_rule": "1530_et_inclusive_to_1531_et_exclusive",
            },
            "negative_control_status": self.control_status,
            "collection": {
                "exit_code": self.collection_exit_code,
                "status": self.collection_status,
                "page_count": self.page_count,
                "terminal_continuation_signal": self.terminal_continuation_signal,
                "raw_content_sha256": self.raw_content_sha256,
            },
            "coverage": {
                "completed_minute_rule": "exchange_timestamp_plus_1m_at_or_before_1530_et",
                "expected_minute_count": KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES,
                "complete_minute_count": self.complete_minute_count,
                "missing_minute_count": self.missing_minute_count,
                "page_seam_status": self.page_seam_status,
            },
            "decision_time_availability": "not_observed",
        }


@dataclass(frozen=True, slots=True)
class KisSpyPaginatedPrefixCapabilityFact:
    """Offline projection of one exact task-owned prefix receipt pair."""

    session_date: date
    run_id: str
    result_class: FactResultClass
    control_status: ControlStatus
    control_observed_at: datetime
    observation_status: ObservationStatus
    observation_control_status: ControlStatus | None
    collection_started_at: datetime
    collector_returned_at: datetime
    observer_started_at: datetime
    observer_finished_at: datetime
    collection_exit_code: int
    collection_status: CollectionStatus | None
    page_count: int | None
    terminal_continuation_signal: ContinuationSignal | None
    complete_minute_count: int | None
    missing_minute_count: int | None
    page_seam_status: Literal["continuous", "invalid"] | None
    raw_content_sha256: str | None
    control_receipt_sha256: str
    observation_receipt_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.session_date) is not date:
            raise ValueError("SPY paginated prefix fact session date is invalid")
        _require_safe_id(self.run_id)
        if self.result_class not in {
            "post_collection_completed_prefix",
            "measurement_incomplete_or_invalid",
            "no_capability_measurement",
        }:
            raise ValueError("SPY paginated prefix fact result class is invalid")
        if self.control_status not in {"negative_control_clean", "negative_control_violation"}:
            raise ValueError("SPY paginated prefix fact control status is invalid")
        if self.observation_status not in {
            "availability_within_validity_after_collection",
            "outside_stage_window",
            "control_unavailable",
            "control_not_clean",
            "collection_unavailable",
            "fresh_run_invalid",
            "page_seam_invalid",
            "incomplete_prefix",
            "capture_expired",
        }:
            raise ValueError("SPY paginated prefix fact observation status is invalid")
        if self.observation_control_status not in {
            None,
            "negative_control_clean",
            "negative_control_violation",
        }:
            raise ValueError("SPY paginated prefix fact observation control status is invalid")
        for name in (
            "control_observed_at",
            "collection_started_at",
            "collector_returned_at",
            "observer_started_at",
            "observer_finished_at",
        ):
            object.__setattr__(self, name, require_utc(getattr(self, name), name))
        if self.collection_exit_code < 0:
            raise ValueError("SPY paginated prefix fact collection exit code is invalid")
        if self.collection_status not in {None, "collected", "partial"}:
            raise ValueError("SPY paginated prefix fact collection status is invalid")
        if (
            self.page_count is not None
            and not 0 <= self.page_count <= KIS_SPY_PAGINATED_PREFIX_MAX_PAGES
        ):
            raise ValueError("SPY paginated prefix fact page count is invalid")
        if self.terminal_continuation_signal is not None and (
            not isinstance(self.terminal_continuation_signal, str)
            or self.terminal_continuation_signal
            not in {
                "recognized_continuation",
                "blank_or_absent",
                "unrecognized_nonblank",
                "not_recorded_legacy",
            }
        ):
            raise ValueError("SPY paginated prefix fact continuation signal is invalid")
        for value in (self.complete_minute_count, self.missing_minute_count):
            if value is not None and not 0 <= value <= KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES:
                raise ValueError("SPY paginated prefix fact coverage is invalid")
        if (
            self.complete_minute_count is not None
            and self.missing_minute_count is not None
            and self.complete_minute_count + self.missing_minute_count
            != KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES
        ):
            raise ValueError("SPY paginated prefix fact coverage is invalid")
        if self.page_seam_status not in {None, "continuous", "invalid"}:
            raise ValueError("SPY paginated prefix fact seam status is invalid")
        for value in (
            self.raw_content_sha256,
            self.control_receipt_sha256,
            self.observation_receipt_sha256,
        ):
            if value is not None and not _is_sha256(value):
                raise ValueError("SPY paginated prefix fact hash is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("SPY paginated prefix fact schema version is invalid")
        if self.result_class == "post_collection_completed_prefix":
            if not (
                self.control_status == "negative_control_clean"
                and self.observation_status == "availability_within_validity_after_collection"
                and self.observation_control_status == "negative_control_clean"
                and self.collection_exit_code == 0
                and self.collection_status == "collected"
                and self.page_count is not None
                and self.complete_minute_count == KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES
                and self.missing_minute_count == 0
                and self.page_seam_status == "continuous"
                and self.raw_content_sha256 is not None
                and _capture_timing_is_valid(
                    session_date=self.session_date,
                    collection_started_at=self.collection_started_at,
                    collector_returned_at=self.collector_returned_at,
                    observer_started_at=self.observer_started_at,
                    observer_finished_at=self.observer_finished_at,
                )
            ):
                raise ValueError("SPY paginated prefix completed fact is invalid")
        elif self.result_class == "measurement_incomplete_or_invalid":
            if self.observation_status not in {
                "fresh_run_invalid",
                "page_seam_invalid",
                "incomplete_prefix",
                "capture_expired",
            }:
                raise ValueError("SPY paginated prefix diagnostic fact is invalid")
        elif self.observation_status not in {
            "outside_stage_window",
            "control_unavailable",
            "control_not_clean",
            "collection_unavailable",
        }:
            raise ValueError("SPY paginated prefix no-measurement fact is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_SPY_PAGINATED_PREFIX_FACT_KIND,
            "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
            "source": "task_owned_immutable_receipts",
            "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
            "session_date": self.session_date.isoformat(),
            "run_id": self.run_id,
            "result_class": self.result_class,
            "control": {
                "status": self.control_status,
                "observed_at": _time_payload(self.control_observed_at),
                "receipt_sha256": self.control_receipt_sha256,
            },
            "observation": {
                "status": self.observation_status,
                "negative_control_status": self.observation_control_status,
                "timing": {
                    "collection_started_at": _time_payload(self.collection_started_at),
                    "collector_returned_at": _time_payload(self.collector_returned_at),
                    "observer_started_at": _time_payload(self.observer_started_at),
                    "observer_finished_at": _time_payload(self.observer_finished_at),
                    "validity_rule": "1530_et_inclusive_to_1531_et_exclusive",
                },
                "receipt_sha256": self.observation_receipt_sha256,
            },
            "collection": {
                "exit_code": self.collection_exit_code,
                "status": self.collection_status,
                "page_count": self.page_count,
                "terminal_continuation_signal": self.terminal_continuation_signal,
                "raw_content_sha256": self.raw_content_sha256,
            },
            "coverage": {
                "completed_minute_rule": "exchange_timestamp_plus_1m_at_or_before_1530_et",
                "expected_minute_count": KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES,
                "complete_minute_count": self.complete_minute_count,
                "missing_minute_count": self.missing_minute_count,
                "page_seam_status": self.page_seam_status,
            },
            "decision_time_availability": "not_observed",
        }


def run_id_for_session(session_date: date) -> str:
    """Return the only allowed fresh-run namespace for one scheduled session."""

    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix session date is invalid")
    return f"spy-prefix-{session_date.strftime('%Y%m%d')}-v1"


def read_spy_paginated_prefix_capability_fact_from_artifact_root(
    *,
    artifact_root: Path | str,
    repository_root: Path | str,
    session_date: date,
    run_id: str | None = None,
) -> KisSpyPaginatedPrefixCapabilityFact:
    """Read only one exact control/observation receipt pair without raw pages."""

    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix fact session date is invalid")
    expected_run_id = run_id_for_session(session_date)
    resolved_run_id = expected_run_id if run_id is None else run_id
    _require_safe_id(resolved_run_id)
    if resolved_run_id != expected_run_id:
        raise ValueError("SPY paginated prefix fact run id is invalid")
    root = _external_artifact_root(
        artifact_root=Path(artifact_root), repository_root=Path(repository_root), create=False
    )
    control_relative = (
        Path(KIS_SPY_PAGINATED_PREFIX_ARTIFACT_DIRECTORY)
        / "controls"
        / session_date.isoformat()
        / "negative-control.json"
    )
    control_bytes = _read_existing_artifact_bytes(
        root=root,
        relative_path=control_relative,
        error_message="SPY paginated prefix control receipt is unavailable",
    )
    control = _parse_negative_control_payload(
        payload=_decode_object(
            control_bytes,
            "SPY paginated prefix control receipt is invalid",
        ),
        artifact_path=root / control_relative,
        session_date=session_date,
        run_id=resolved_run_id,
    )
    observation_relative = (
        Path(KIS_SPY_PAGINATED_PREFIX_ARTIFACT_DIRECTORY)
        / "runs"
        / resolved_run_id
        / "evidence.json"
    )
    observation_bytes = _read_existing_artifact_bytes(
        root=root,
        relative_path=observation_relative,
        error_message="SPY paginated prefix observation receipt is unavailable",
    )
    observation_path = root / observation_relative
    payload = _decode_object(
        observation_bytes,
        "SPY paginated prefix observation receipt is invalid",
    )
    if set(payload) != {
        "schema_version",
        "kind",
        "schema_id",
        "phase",
        "status",
        "target",
        "session_date",
        "run_id",
        "timing",
        "negative_control_status",
        "collection",
        "coverage",
        "decision_time_availability",
    }:
        raise ValueError("SPY paginated prefix observation receipt is invalid")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_SPY_PAGINATED_PREFIX_CAPABILITY_KIND
        or payload.get("schema_id") != KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID
        or payload.get("phase") != "positive_observation"
        or payload.get("target") != KIS_SPY_PAGINATED_PREFIX_TARGET
        or payload.get("session_date") != session_date.isoformat()
        or payload.get("run_id") != resolved_run_id
        or payload.get("decision_time_availability") != "not_observed"
    ):
        raise ValueError("SPY paginated prefix observation receipt is invalid")
    timing = payload.get("timing")
    collection_payload = payload.get("collection")
    coverage_payload = payload.get("coverage")
    if (
        not isinstance(timing, Mapping)
        or set(timing)
        != {
            "collection_started_at",
            "collector_returned_at",
            "observer_started_at",
            "observer_finished_at",
            "validity_rule",
        }
        or timing.get("validity_rule") != "1530_et_inclusive_to_1531_et_exclusive"
        or not isinstance(collection_payload, Mapping)
        or set(collection_payload)
        not in (
            {"exit_code", "status", "page_count", "raw_content_sha256"},
            {
                "exit_code",
                "status",
                "page_count",
                "terminal_continuation_signal",
                "raw_content_sha256",
            },
        )
        or not isinstance(coverage_payload, Mapping)
        or set(coverage_payload)
        != {
            "completed_minute_rule",
            "expected_minute_count",
            "complete_minute_count",
            "missing_minute_count",
            "page_seam_status",
        }
        or coverage_payload.get("completed_minute_rule")
        != "exchange_timestamp_plus_1m_at_or_before_1530_et"
        or coverage_payload.get("expected_minute_count")
        != KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES
    ):
        raise ValueError("SPY paginated prefix observation receipt is invalid")
    observation_status = payload.get("status")
    observation_control_status = payload.get("negative_control_status")
    collection_exit_code = collection_payload.get("exit_code")
    collection_status = collection_payload.get("status")
    page_count = collection_payload.get("page_count")
    terminal_continuation_signal = collection_payload.get(
        "terminal_continuation_signal",
        None if page_count is None or page_count == 0 else "not_recorded_legacy",
    )
    raw_content_sha256 = collection_payload.get("raw_content_sha256")
    complete_minute_count = coverage_payload.get("complete_minute_count")
    missing_minute_count = coverage_payload.get("missing_minute_count")
    page_seam_status = coverage_payload.get("page_seam_status")
    if (
        observation_status
        not in {
            "availability_within_validity_after_collection",
            "outside_stage_window",
            "control_unavailable",
            "control_not_clean",
            "collection_unavailable",
            "fresh_run_invalid",
            "page_seam_invalid",
            "incomplete_prefix",
            "capture_expired",
        }
        or observation_control_status
        not in {None, "negative_control_clean", "negative_control_violation"}
        or type(collection_exit_code) is not int
        or collection_status not in {None, "collected", "partial"}
        or (page_count is not None and type(page_count) is not int)
        or (
            terminal_continuation_signal is not None
            and (
                not isinstance(terminal_continuation_signal, str)
                or terminal_continuation_signal
                not in {
                    "recognized_continuation",
                    "blank_or_absent",
                    "unrecognized_nonblank",
                    "not_recorded_legacy",
                }
            )
        )
        or (raw_content_sha256 is not None and not isinstance(raw_content_sha256, str))
        or (complete_minute_count is not None and type(complete_minute_count) is not int)
        or (missing_minute_count is not None and type(missing_minute_count) is not int)
        or page_seam_status not in {None, "continuous", "invalid"}
    ):
        raise ValueError("SPY paginated prefix observation receipt is invalid")
    observation = KisSpyPaginatedPrefixObservation(
        status=observation_status,
        session_date=session_date,
        run_id=resolved_run_id,
        collection_started_at=_parse_time_payload(timing.get("collection_started_at")),
        collector_returned_at=_parse_time_payload(timing.get("collector_returned_at")),
        observer_started_at=_parse_time_payload(timing.get("observer_started_at")),
        observer_finished_at=_parse_time_payload(timing.get("observer_finished_at")),
        collection_exit_code=collection_exit_code,
        control_status=observation_control_status,
        collection_status=collection_status,
        page_count=page_count,
        terminal_continuation_signal=terminal_continuation_signal,
        complete_minute_count=complete_minute_count,
        missing_minute_count=missing_minute_count,
        page_seam_status=page_seam_status,
        raw_content_sha256=raw_content_sha256,
        artifact_path=observation_path,
    )
    if observation.status == "availability_within_validity_after_collection":
        result_class: FactResultClass = "post_collection_completed_prefix"
    elif observation.status in {
        "fresh_run_invalid",
        "page_seam_invalid",
        "incomplete_prefix",
        "capture_expired",
    }:
        result_class = "measurement_incomplete_or_invalid"
    else:
        result_class = "no_capability_measurement"
    if (
        _read_existing_artifact_bytes(
            root=root,
            relative_path=control_relative,
            error_message="SPY paginated prefix receipt changed during projection",
        )
        != control_bytes
        or _read_existing_artifact_bytes(
            root=root,
            relative_path=observation_relative,
            error_message="SPY paginated prefix receipt changed during projection",
        )
        != observation_bytes
    ):
        raise ValueError("SPY paginated prefix receipt changed during projection")
    return KisSpyPaginatedPrefixCapabilityFact(
        session_date=session_date,
        run_id=resolved_run_id,
        result_class=result_class,
        control_status=control.status,
        control_observed_at=control.observed_at,
        observation_status=observation.status,
        observation_control_status=observation.control_status,
        collection_started_at=observation.collection_started_at,
        collector_returned_at=observation.collector_returned_at,
        observer_started_at=observation.observer_started_at,
        observer_finished_at=observation.observer_finished_at,
        collection_exit_code=observation.collection_exit_code,
        collection_status=observation.collection_status,
        page_count=observation.page_count,
        terminal_continuation_signal=observation.terminal_continuation_signal,
        complete_minute_count=observation.complete_minute_count,
        missing_minute_count=observation.missing_minute_count,
        page_seam_status=observation.page_seam_status,
        raw_content_sha256=observation.raw_content_sha256,
        control_receipt_sha256="sha256:" + _sha256(control_bytes),
        observation_receipt_sha256="sha256:" + _sha256(observation_bytes),
    )


def is_spy_paginated_prefix_positive_window(
    *, session_date: date, observed_at: datetime
) -> bool:
    """Return whether an observer's own UTC reading is inside the positive slot."""

    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix session date is invalid")
    return _inside_positive_window(
        session_date=session_date,
        value=require_utc(observed_at, "observed_at"),
    )


def collect_spy_paginated_prefix_pages(
    *,
    fetch_page: Callable[[str | None, str | None], object],
) -> KisSpyPaginatedPrefixCollection:
    """Collect at most four pages through the caller-owned single client.

    The function has no provider, credential, or environment dependency.  A
    caller supplies the one client's fetch callback; continuation is derived
    only from the oldest exchange timestamp of the preceding page.
    """

    pages: list[KisSpyPaginatedPrefixPage] = []
    fingerprints_by_timestamp: dict[datetime, str] = {}
    cursor_next: str | None = None
    cursor_key: str | None = None
    try:
        for index in range(1, KIS_SPY_PAGINATED_PREFIX_MAX_PAGES + 1):
            page = fetch_page(cursor_next, cursor_key)
            rows = tuple(_row_document(row) for row in _page_rows(page))
            if not rows:
                return KisSpyPaginatedPrefixCollection(
                    status="partial", reason="minute_response_empty", pages=tuple(pages)
                )
            stamps = tuple(_exchange_timestamp(row) for row in rows)
            if len(set(stamps)) != len(stamps):
                return KisSpyPaginatedPrefixCollection(
                    status="partial",
                    reason="minute_duplicate_conflict",
                    pages=tuple(pages)
                    + (
                        KisSpyPaginatedPrefixPage(
                            index=index,
                            rows=rows,
                            continuation_advertised=_page_continuation(page),
                            continuation_signal=_page_continuation_signal(page),
                        ),
                    ),
                )
            for stamp, row in zip(stamps, rows, strict=True):
                fingerprint = _raw_row_fingerprint(row)
                prior = fingerprints_by_timestamp.get(stamp)
                if prior is not None:
                    return KisSpyPaginatedPrefixCollection(
                        status="partial",
                        reason="minute_duplicate_conflict",
                        pages=tuple(pages)
                        + (
                        KisSpyPaginatedPrefixPage(
                            index=index,
                            rows=rows,
                            continuation_advertised=_page_continuation(page),
                            continuation_signal=_page_continuation_signal(page),
                        ),
                        ),
                    )
                fingerprints_by_timestamp[stamp] = fingerprint
            continuation_advertised = _page_continuation(page)
            pages.append(
                KisSpyPaginatedPrefixPage(
                    index=index,
                    rows=rows,
                    continuation_advertised=continuation_advertised,
                    continuation_signal=_page_continuation_signal(page),
                )
            )
            if not continuation_advertised:
                return KisSpyPaginatedPrefixCollection(
                    status="collected", reason=None, pages=tuple(pages)
                )
            next_cursor = _page_next_cursor(page)
            next_key = _one_minute_before(min(stamps))
            if (next_cursor, next_key) == (cursor_next, cursor_key):
                return KisSpyPaginatedPrefixCollection(
                    status="partial", reason="minute_cursor_stalled", pages=tuple(pages)
                )
            cursor_next, cursor_key = next_cursor, next_key
    except Exception as error:  # The safe category is the only retained failure detail.
        if pages:
            return KisSpyPaginatedPrefixCollection(
                status="partial", reason=_safe_collection_reason(error), pages=tuple(pages)
            )
        return KisSpyPaginatedPrefixCollection(
            status="partial", reason=_safe_collection_reason(error), pages=()
        )
    return KisSpyPaginatedPrefixCollection(
        status="collected", reason="page_limit_reached", pages=tuple(pages)
    )


def write_spy_paginated_prefix_collection_run(
    *,
    collection: KisSpyPaginatedPrefixCollection,
    cache_root: Path | str,
    repository_root: Path | str,
    run_id: str,
    session_date: date,
    collection_started_at: datetime,
    token_attempts: int,
    minute_page_attempts: int,
) -> KisSpyPaginatedPrefixCollectionRun:
    """Persist one immutable raw collection under the dedicated external cache."""

    _require_safe_id(run_id)
    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix session date is invalid")
    started = require_utc(collection_started_at, "collection_started_at")
    _require_positive_window(session_date=session_date, value=started)
    if not isinstance(collection, KisSpyPaginatedPrefixCollection):
        raise ValueError("SPY paginated prefix collection is invalid")
    if not 0 <= token_attempts <= 1:
        raise ValueError("SPY paginated prefix token attempts are invalid")
    if not 0 <= minute_page_attempts <= KIS_SPY_PAGINATED_PREFIX_MAX_PAGES:
        raise ValueError("SPY paginated prefix minute page attempts are invalid")
    if minute_page_attempts < len(collection.pages):
        raise ValueError("SPY paginated prefix minute page attempts are invalid")
    root = _external_cache_root(
        cache_root=Path(cache_root), repository_root=Path(repository_root), create=True
    )
    runs_root = _ensure_real_directory(root / "runs", root=root)
    destination = runs_root / run_id
    if destination.exists():
        raise ValueError("SPY paginated prefix fresh run already exists")
    raw_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_SPY_PAGINATED_PREFIX_RAW_KIND,
        "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
        "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
        "run_id": run_id,
        "session_date": session_date.isoformat(),
        "pages": [
            {
                "index": page.index,
                "continuation_advertised": page.continuation_advertised,
                "continuation_signal": page.continuation_signal,
                "rows": list(page.rows),
            }
            for page in collection.pages
        ],
    }
    raw_bytes = _canonical_bytes(raw_payload)
    raw_hash = "sha256:" + _sha256(raw_bytes)
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND,
        "schema_id": KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID,
        "target": KIS_SPY_PAGINATED_PREFIX_TARGET,
        "run_id": run_id,
        "session_date": session_date.isoformat(),
        "collection_started_at": _utc_marker(started),
        "collection": {
            "status": collection.status,
            "reason": collection.reason,
            "page_count": len(collection.pages),
            "continuation_advertised_on_final_page": (
                None if not collection.pages else collection.pages[-1].continuation_advertised
            ),
            "terminal_continuation_signal": (
                None if not collection.pages else collection.pages[-1].continuation_signal
            ),
        },
        "client": {
            "single_in_memory_client": True,
            "token_attempts": token_attempts,
            "minute_page_attempts": minute_page_attempts,
            "maximum_minute_page_attempts": KIS_SPY_PAGINATED_PREFIX_MAX_PAGES,
        },
        "raw_file": "raw-pages.json",
        "raw_content_sha256": raw_hash,
    }
    manifest_bytes = _canonical_bytes(manifest_payload)
    staging = runs_root / f".{run_id}.{os.getpid()}.{uuid.uuid4().hex}.stage"
    try:
        _ensure_real_directory(staging, root=root)
        (staging / "raw-pages.json").write_bytes(raw_bytes)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        if destination.exists():
            raise ValueError("SPY paginated prefix fresh run already exists")
        os.replace(staging, destination)
    finally:
        if staging.exists():
            _remove_empty_or_owned_staging(staging, root=root)
    return KisSpyPaginatedPrefixCollectionRun(
        run_id=run_id,
        session_date=session_date,
        collection_started_at=started,
        collection=collection,
        token_attempts=token_attempts,
        minute_page_attempts=minute_page_attempts,
        raw_content_sha256=raw_hash,
        manifest_path=destination / "manifest.json",
    )


def record_spy_paginated_prefix_negative_control(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    repository_root: Path | str,
    session_date: date,
    run_id: str,
    observed_at: datetime,
) -> KisSpyPaginatedPrefixControl:
    """Record the dedicated fresh-run absence control before collection.

    This control deliberately observes only the planned external run namespace;
    it does not infer source availability.  The caller must provide the
    observer's actual clock reading, not a scheduler dispatch marker.
    """

    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix session date is invalid")
    _require_safe_id(run_id)
    observed = require_utc(observed_at, "observed_at")
    _require_negative_control_window(session_date=session_date, value=observed)
    cache = _external_cache_root(
        cache_root=Path(cache_root), repository_root=Path(repository_root), create=False
    )
    run_path = _cache_run_path(root=cache, run_id=run_id)
    root = _external_artifact_root(
        artifact_root=Path(artifact_root), repository_root=Path(repository_root)
    )
    destination = _control_artifact_path(root=root, session_date=session_date)
    status: ControlStatus = (
        "negative_control_violation" if run_path.exists() else "negative_control_clean"
    )
    outcome = KisSpyPaginatedPrefixControl(
        status=status,
        session_date=session_date,
        run_id=run_id,
        observed_at=observed,
        artifact_path=destination,
    )
    _write_or_verify(destination, outcome.safe_payload(), root=root)
    return outcome


def preflight_spy_paginated_prefix_positive(
    *,
    artifact_root: Path | str,
    repository_root: Path | str,
    session_date: date,
    run_id: str,
    observed_at: datetime,
) -> KisSpyPaginatedPrefixPreflight:
    """Require the same-session clean negative control before any KIS call."""

    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix session date is invalid")
    _require_safe_id(run_id)
    observed = require_utc(observed_at, "observed_at")
    if not _inside_positive_window(session_date=session_date, value=observed):
        return KisSpyPaginatedPrefixPreflight(
            status="outside_stage_window",
            session_date=session_date,
            run_id=run_id,
            observed_at=observed,
            control=None,
        )
    try:
        root = _external_artifact_root(
            artifact_root=Path(artifact_root), repository_root=Path(repository_root), create=False
        )
    except (OSError, ValueError):
        return KisSpyPaginatedPrefixPreflight(
            status="control_unavailable",
            session_date=session_date,
            run_id=run_id,
            observed_at=observed,
            control=None,
        )
    try:
        control = _load_negative_control(
            artifact_root=root, session_date=session_date, run_id=run_id
        )
    except (OSError, ValueError):
        return KisSpyPaginatedPrefixPreflight(
            status="control_unavailable",
            session_date=session_date,
            run_id=run_id,
            observed_at=observed,
            control=None,
        )
    return KisSpyPaginatedPrefixPreflight(
        status="ready" if control.valid_for_collection else "control_not_clean",
        session_date=session_date,
        run_id=run_id,
        observed_at=observed,
        control=control,
    )


def observe_spy_paginated_prefix_positive(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    repository_root: Path | str,
    session_date: date,
    run_id: str,
    collection_started_at: datetime,
    collector_returned_at: datetime,
    collection_exit_code: int,
    observer_started_at: datetime | None = None,
    observer_finished_at: datetime | None = None,
) -> KisSpyPaginatedPrefixObservation:
    """Verify one exact raw run in a network- and credential-free observer."""

    if type(session_date) is not date:
        raise ValueError("SPY paginated prefix session date is invalid")
    _require_safe_id(run_id)
    collection_started = require_utc(collection_started_at, "collection_started_at")
    collector_returned = require_utc(collector_returned_at, "collector_returned_at")
    observer_started = require_utc(observer_started_at or datetime.now(UTC), "observer_started_at")
    observer_finished = require_utc(
        observer_finished_at or datetime.now(UTC), "observer_finished_at"
    )
    if collection_exit_code < 0:
        raise ValueError("SPY paginated prefix collection exit code is invalid")
    root = _external_artifact_root(
        artifact_root=Path(artifact_root), repository_root=Path(repository_root)
    )
    destination = _observation_artifact_path(root=root, run_id=run_id)
    preflight = preflight_spy_paginated_prefix_positive(
        artifact_root=root,
        repository_root=repository_root,
        session_date=session_date,
        run_id=run_id,
        observed_at=observer_started,
    )
    control_status = None if preflight.control is None else preflight.control.status
    if preflight.status != "ready":
        status: ObservationStatus = (
            "outside_stage_window"
            if preflight.status == "outside_stage_window"
            else "control_unavailable"
            if preflight.status == "control_unavailable"
            else "control_not_clean"
        )
        return _write_observation(
            status=status,
            session_date=session_date,
            run_id=run_id,
            collection_started_at=collection_started,
            collector_returned_at=collector_returned,
            observer_started_at=observer_started,
            observer_finished_at=observer_finished,
            collection_exit_code=collection_exit_code,
            control_status=control_status,
            collection_status=None,
            page_count=None,
            terminal_continuation_signal=None,
            complete_minute_count=None,
            missing_minute_count=None,
            page_seam_status=None,
            raw_content_sha256=None,
            artifact_path=destination,
            artifact_root=root,
        )
    if collection_exit_code != 0:
        return _write_observation(
            status="collection_unavailable",
            session_date=session_date,
            run_id=run_id,
            collection_started_at=collection_started,
            collector_returned_at=collector_returned,
            observer_started_at=observer_started,
            observer_finished_at=observer_finished,
            collection_exit_code=collection_exit_code,
            control_status=control_status,
            collection_status=None,
            page_count=None,
            terminal_continuation_signal=None,
            complete_minute_count=None,
            missing_minute_count=None,
            page_seam_status=None,
            raw_content_sha256=None,
            artifact_path=destination,
            artifact_root=root,
        )
    try:
        loaded = _load_collection_run(
            cache_root=Path(cache_root),
            repository_root=Path(repository_root),
            run_id=run_id,
        )
        coverage = _evaluate_collection_coverage(
            loaded=loaded,
            session_date=session_date,
            collection_started_at=collection_started,
        )
    except (OSError, ValueError):
        return _write_observation(
            status="fresh_run_invalid",
            session_date=session_date,
            run_id=run_id,
            collection_started_at=collection_started,
            collector_returned_at=collector_returned,
            observer_started_at=observer_started,
            observer_finished_at=observer_finished,
            collection_exit_code=collection_exit_code,
            control_status=control_status,
            collection_status=None,
            page_count=None,
            terminal_continuation_signal=None,
            complete_minute_count=None,
            missing_minute_count=None,
            page_seam_status=None,
            raw_content_sha256=None,
            artifact_path=destination,
            artifact_root=root,
        )
    timing_valid = _capture_timing_is_valid(
        session_date=session_date,
        collection_started_at=collection_started,
        collector_returned_at=collector_returned,
        observer_started_at=observer_started,
        observer_finished_at=observer_finished,
    )
    if not timing_valid:
        status = "capture_expired"
    elif coverage.page_seam_status != "continuous":
        status = "page_seam_invalid"
    elif not coverage.complete:
        status = "incomplete_prefix"
    else:
        status = "availability_within_validity_after_collection"
    return _write_observation(
        status=status,
        session_date=session_date,
        run_id=run_id,
        collection_started_at=collection_started,
        collector_returned_at=collector_returned,
        observer_started_at=observer_started,
        observer_finished_at=observer_finished,
        collection_exit_code=collection_exit_code,
        control_status=control_status,
        collection_status=loaded.collection_status,
        page_count=loaded.page_count,
        terminal_continuation_signal=loaded.terminal_continuation_signal,
        complete_minute_count=coverage.complete_minute_count,
        missing_minute_count=coverage.missing_minute_count,
        page_seam_status=coverage.page_seam_status,
        raw_content_sha256=loaded.raw_content_sha256,
        artifact_path=destination,
        artifact_root=root,
    )


@dataclass(frozen=True, slots=True)
class _LoadedCollectionRun:
    run_id: str
    session_date: date
    collection_started_at: datetime
    collection_status: str
    page_count: int
    terminal_continuation_signal: ContinuationSignal | None
    token_attempts: int
    minute_page_attempts: int
    raw_content_sha256: str
    pages: tuple[KisSpyPaginatedPrefixPage, ...]


@dataclass(frozen=True, slots=True)
class _CoverageEvaluation:
    complete: bool
    complete_minute_count: int
    missing_minute_count: int
    page_seam_status: Literal["continuous", "invalid"]


def _write_observation(
    *,
    status: ObservationStatus,
    session_date: date,
    run_id: str,
    collection_started_at: datetime,
    collector_returned_at: datetime,
    observer_started_at: datetime,
    observer_finished_at: datetime,
    collection_exit_code: int,
    control_status: str | None,
    collection_status: str | None,
    page_count: int | None,
    terminal_continuation_signal: ContinuationSignal | None,
    complete_minute_count: int | None,
    missing_minute_count: int | None,
    page_seam_status: str | None,
    raw_content_sha256: str | None,
    artifact_path: Path,
    artifact_root: Path,
) -> KisSpyPaginatedPrefixObservation:
    outcome = KisSpyPaginatedPrefixObservation(
        status=status,
        session_date=session_date,
        run_id=run_id,
        collection_started_at=collection_started_at,
        collector_returned_at=collector_returned_at,
        observer_started_at=observer_started_at,
        observer_finished_at=observer_finished_at,
        collection_exit_code=collection_exit_code,
        control_status=control_status,
        collection_status=collection_status,
        page_count=page_count,
        terminal_continuation_signal=terminal_continuation_signal,
        complete_minute_count=complete_minute_count,
        missing_minute_count=missing_minute_count,
        page_seam_status=page_seam_status,
        raw_content_sha256=raw_content_sha256,
        artifact_path=artifact_path,
    )
    _write_or_verify(artifact_path, outcome.safe_payload(), root=artifact_root)
    return outcome


def _load_collection_run(
    *, cache_root: Path, repository_root: Path, run_id: str
) -> _LoadedCollectionRun:
    root = _external_cache_root(
        cache_root=cache_root, repository_root=repository_root, create=False
    )
    run_root = _cache_run_path(root=root, run_id=run_id)
    if not run_root.is_dir() or run_root.is_symlink():
        raise ValueError("SPY paginated prefix fresh run is unavailable")
    manifest_path = run_root / "manifest.json"
    raw_path = run_root / "raw-pages.json"
    if any(not path.is_file() or path.is_symlink() for path in (manifest_path, raw_path)):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    if not manifest_path.resolve(strict=True).is_relative_to(root) or not raw_path.resolve(
        strict=True
    ).is_relative_to(root):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    manifest = _decode_object(
        manifest_path.read_bytes(), "SPY paginated prefix manifest is invalid"
    )
    raw_bytes = raw_path.read_bytes()
    raw = _decode_object(raw_bytes, "SPY paginated prefix raw pages are invalid")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != KIS_SPY_PAGINATED_PREFIX_COLLECTION_KIND
        or manifest.get("schema_id") != KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID
        or manifest.get("target") != KIS_SPY_PAGINATED_PREFIX_TARGET
        or manifest.get("run_id") != run_id
        or manifest.get("raw_file") != "raw-pages.json"
        or raw.get("schema_version") != SCHEMA_VERSION
        or raw.get("kind") != KIS_SPY_PAGINATED_PREFIX_RAW_KIND
        or raw.get("schema_id") != KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID
        or raw.get("target") != KIS_SPY_PAGINATED_PREFIX_TARGET
        or raw.get("run_id") != run_id
    ):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    session_date = _parse_session_date(manifest.get("session_date"))
    if raw.get("session_date") != session_date.isoformat():
        raise ValueError("SPY paginated prefix fresh run is invalid")
    collection_started = _parse_utc_marker(manifest.get("collection_started_at"))
    collection = manifest.get("collection")
    client = manifest.get("client")
    raw_hash = manifest.get("raw_content_sha256")
    if (
        not isinstance(collection, Mapping)
        or not isinstance(client, Mapping)
        or not isinstance(raw_hash, str)
    ):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    if not _is_sha256(raw_hash) or raw_hash != "sha256:" + _sha256(raw_bytes):
        raise ValueError("SPY paginated prefix raw hash is invalid")
    collection_status = collection.get("status")
    collection_reason = collection.get("reason")
    page_count = collection.get("page_count")
    token_attempts = client.get("token_attempts")
    minute_page_attempts = client.get("minute_page_attempts")
    if (
        collection_status not in {"collected", "partial"}
        or (collection_reason is not None and not isinstance(collection_reason, str))
        or type(page_count) is not int
        or type(token_attempts) is not int
        or type(minute_page_attempts) is not int
        or client.get("single_in_memory_client") is not True
        or client.get("maximum_minute_page_attempts") != KIS_SPY_PAGINATED_PREFIX_MAX_PAGES
        or not 0 <= token_attempts <= 1
        or not 0 <= minute_page_attempts <= KIS_SPY_PAGINATED_PREFIX_MAX_PAGES
    ):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    raw_pages = raw.get("pages")
    if not isinstance(raw_pages, list) or len(raw_pages) != page_count:
        raise ValueError("SPY paginated prefix raw pages are invalid")
    pages = tuple(_page_from_document(value) for value in raw_pages)
    if tuple(page.index for page in pages) != tuple(range(1, len(pages) + 1)):
        raise ValueError("SPY paginated prefix raw pages are invalid")
    if minute_page_attempts < len(pages):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    terminal_continuation_signal = collection.get(
        "terminal_continuation_signal",
        None if not pages else "not_recorded_legacy",
    )
    if (
        terminal_continuation_signal is not None
        and (
            not isinstance(terminal_continuation_signal, str)
            or terminal_continuation_signal
            not in {
                "recognized_continuation",
                "blank_or_absent",
                "unrecognized_nonblank",
                "not_recorded_legacy",
            }
        )
    ) or (
        pages and terminal_continuation_signal != pages[-1].continuation_signal
    ):
        raise ValueError("SPY paginated prefix fresh run is invalid")
    return _LoadedCollectionRun(
        run_id=run_id,
        session_date=session_date,
        collection_started_at=collection_started,
        collection_status=collection_status,
        page_count=page_count,
        terminal_continuation_signal=terminal_continuation_signal,
        token_attempts=token_attempts,
        minute_page_attempts=minute_page_attempts,
        raw_content_sha256=raw_hash,
        pages=pages,
    )


def _evaluate_collection_coverage(
    *,
    loaded: _LoadedCollectionRun,
    session_date: date,
    collection_started_at: datetime,
) -> _CoverageEvaluation:
    if loaded.session_date != session_date or loaded.collection_started_at != collection_started_at:
        raise ValueError("SPY paginated prefix fresh run binding is invalid")
    if loaded.collection_status != "collected" or not loaded.pages:
        return _CoverageEvaluation(
            complete=False,
            complete_minute_count=0,
            missing_minute_count=KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES,
            page_seam_status="invalid",
        )
    all_stamps: set[datetime] = set()
    seam_valid = True
    previous_oldest: datetime | None = None
    for page in loaded.pages:
        stamps = tuple(_exchange_timestamp(row) for row in page.rows)
        if len(set(stamps)) != len(stamps) or not _timestamps_are_continuous(stamps):
            seam_valid = False
        if previous_oldest is not None and max(stamps) + timedelta(minutes=1) != previous_oldest:
            seam_valid = False
        if all_stamps.intersection(stamps):
            seam_valid = False
        all_stamps.update(stamps)
        previous_oldest = min(stamps)
    if len(loaded.pages) > 1 and any(
        not page.continuation_advertised for page in loaded.pages[:-1]
    ):
        seam_valid = False
    expected = _expected_prefix_stamps(session_date)
    if all_stamps - expected:
        seam_valid = False
    complete_count = len(all_stamps.intersection(expected))
    missing_count = len(expected - all_stamps)
    return _CoverageEvaluation(
        complete=seam_valid and missing_count == 0,
        complete_minute_count=complete_count,
        missing_minute_count=missing_count,
        page_seam_status="continuous" if seam_valid else "invalid",
    )


def _load_negative_control(
    *, artifact_root: Path, session_date: date, run_id: str
) -> KisSpyPaginatedPrefixControl:
    path = _control_artifact_path(root=artifact_root, session_date=session_date, create=False)
    if not path.is_file() or path.is_symlink():
        raise ValueError("SPY paginated prefix negative control is unavailable")
    if not path.resolve(strict=True).is_relative_to(artifact_root):
        raise ValueError("SPY paginated prefix negative control is invalid")
    return _parse_negative_control_payload(
        payload=_decode_object(
            path.read_bytes(),
            "SPY paginated prefix negative control is invalid",
        ),
        artifact_path=path,
        session_date=session_date,
        run_id=run_id,
    )


def _parse_negative_control_payload(
    *,
    payload: Mapping[str, object],
    artifact_path: Path,
    session_date: date,
    run_id: str,
) -> KisSpyPaginatedPrefixControl:
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_SPY_PAGINATED_PREFIX_CAPABILITY_KIND
        or payload.get("schema_id") != KIS_SPY_PAGINATED_PREFIX_SCHEMA_ID
        or payload.get("phase") != "negative_control"
        or payload.get("target") != KIS_SPY_PAGINATED_PREFIX_TARGET
        or payload.get("session_date") != session_date.isoformat()
        or payload.get("run_id") != run_id
    ):
        raise ValueError("SPY paginated prefix negative control is invalid")
    timing = payload.get("timing")
    control = payload.get("control")
    if not isinstance(timing, Mapping) or not isinstance(control, Mapping):
        raise ValueError("SPY paginated prefix negative control is invalid")
    observed = _parse_time_payload(timing.get("observed_at"))
    _require_negative_control_window(session_date=session_date, value=observed)
    status = payload.get("status")
    if status not in {"negative_control_clean", "negative_control_violation"}:
        raise ValueError("SPY paginated prefix negative control is invalid")
    if (
        control.get("completed_minute_predicate")
        != "exchange_timestamp_plus_1m_at_or_before_1530_et"
        or control.get("fresh_run_absent_before_cutoff") != (status == "negative_control_clean")
        or control.get("positive_collection_permitted") != (status == "negative_control_clean")
    ):
        raise ValueError("SPY paginated prefix negative control is invalid")
    return KisSpyPaginatedPrefixControl(
        status=status,
        session_date=session_date,
        run_id=run_id,
        observed_at=observed,
        artifact_path=artifact_path,
    )


def _page_rows(page: object) -> Sequence[object]:
    rows = getattr(page, "bars", None)
    if not isinstance(rows, Sequence):
        raise ValueError("minute_response_invalid")
    return rows


def _row_document(row: object) -> dict[str, str]:
    serializer = getattr(row, "as_document", None)
    if not callable(serializer):
        raise ValueError("minute_response_invalid")
    return _normalize_raw_row(serializer())


def _page_continuation(page: object) -> bool:
    cursor = getattr(page, "next_cursor", None)
    if cursor is None:
        return False
    if cursor != "1":
        raise ValueError("minute_cursor_invalid")
    return True


def _page_continuation_signal(page: object) -> ContinuationSignal:
    advertised = _page_continuation(page)
    signal = getattr(page, "continuation_signal", None)
    if signal is None:
        return "recognized_continuation" if advertised else "blank_or_absent"
    if not isinstance(signal, str) or signal not in {
        "recognized_continuation",
        "blank_or_absent",
        "unrecognized_nonblank",
    }:
        raise ValueError("minute_continuation_signal_invalid")
    if advertised != (signal == "recognized_continuation"):
        raise ValueError("minute_continuation_signal_invalid")
    return signal


def _page_next_cursor(page: object) -> str:
    if not _page_continuation(page):
        raise ValueError("minute_cursor_invalid")
    return "1"


def _normalize_raw_row(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _RAW_COLUMNS:
        raise ValueError("minute_response_invalid")
    normalized: dict[str, str] = {}
    for key in sorted(_RAW_COLUMNS):
        raw = value.get(key)
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("minute_response_invalid")
        normalized[key] = raw.strip()
    _exchange_timestamp(normalized)
    return normalized


def _page_from_document(value: object) -> KisSpyPaginatedPrefixPage:
    if not isinstance(value, Mapping):
        raise ValueError("SPY paginated prefix raw page is invalid")
    index = value.get("index")
    continuation = value.get("continuation_advertised")
    signal = value.get("continuation_signal", "not_recorded_legacy")
    rows = value.get("rows")
    if (
        type(index) is not int
        or type(continuation) is not bool
        or not isinstance(signal, str)
        or signal
        not in {
            "recognized_continuation",
            "blank_or_absent",
            "unrecognized_nonblank",
            "not_recorded_legacy",
        }
        or not isinstance(rows, list)
    ):
        raise ValueError("SPY paginated prefix raw page is invalid")
    return KisSpyPaginatedPrefixPage(
        index=index,
        continuation_advertised=continuation,
        continuation_signal=signal,
        rows=tuple(_normalize_raw_row(row) for row in rows),
    )


def _exchange_timestamp(row: Mapping[str, str]) -> datetime:
    try:
        local = datetime.strptime(f"{row['xymd']}{row['xhms']}", "%Y%m%d%H%M%S")
    except (KeyError, ValueError) as error:
        raise ValueError("minute_exchange_timestamp_invalid") from error
    if local.second != 0:
        raise ValueError("minute_exchange_timestamp_invalid")
    return local.replace(tzinfo=_EASTERN).astimezone(UTC)


def _one_minute_before(value: datetime) -> str:
    return (value.astimezone(_EASTERN) - timedelta(minutes=1)).strftime("%Y%m%d%H%M%S")


def _raw_row_fingerprint(row: Mapping[str, str]) -> str:
    return _sha256(_canonical_bytes(dict(row)))


def _timestamps_are_continuous(values: Sequence[datetime]) -> bool:
    ordered = tuple(sorted(values))
    return all(
        current == previous + timedelta(minutes=1)
        for previous, current in zip(ordered, ordered[1:], strict=False)
    )


def _expected_prefix_stamps(session_date: date) -> set[datetime]:
    open_at, cutoff = _session_boundaries(session_date)
    return {
        open_at + timedelta(minutes=index)
        for index in range(KIS_SPY_PAGINATED_PREFIX_EXPECTED_MINUTES)
        if open_at + timedelta(minutes=index) < cutoff
    }


def _capture_timing_is_valid(
    *,
    session_date: date,
    collection_started_at: datetime,
    collector_returned_at: datetime,
    observer_started_at: datetime,
    observer_finished_at: datetime,
) -> bool:
    cutoff = _session_boundaries(session_date)[1]
    valid_until = cutoff + _VALIDITY
    return (
        cutoff
        <= collection_started_at
        <= collector_returned_at
        <= observer_started_at
        <= observer_finished_at
        and observer_finished_at < valid_until
    )


def _inside_positive_window(*, session_date: date, value: datetime) -> bool:
    try:
        _, cutoff = _session_boundaries(session_date)
    except ValueError:
        return False
    return cutoff <= value < cutoff + _VALIDITY


def _require_positive_window(*, session_date: date, value: datetime) -> None:
    if not _inside_positive_window(session_date=session_date, value=value):
        raise ValueError(
            "SPY paginated prefix collection must start inside the 15:30 validity window"
        )


def _require_negative_control_window(*, session_date: date, value: datetime) -> None:
    open_at, cutoff = _session_boundaries(session_date)
    del open_at
    negative_start = cutoff - timedelta(seconds=30)
    if not negative_start <= value < cutoff:
        raise ValueError("SPY paginated prefix negative control must run at 15:29:30 ET")


def _session_boundaries(session_date: date) -> tuple[datetime, datetime]:
    try:
        session = us_equity_2026_session(session_date)
    except ValueError as error:
        raise ValueError("SPY paginated prefix calendar is unavailable") from error
    if session is None or session.kind != "regular":
        raise ValueError("SPY paginated prefix requires a regular session")
    open_at = datetime.combine(session_date, _REGULAR_OPEN, _EASTERN).astimezone(UTC)
    cutoff = datetime.combine(session_date, _DECISION_CUTOFF, _EASTERN).astimezone(UTC)
    if session.window.open_ts != open_at:
        raise ValueError("SPY paginated prefix session geometry is invalid")
    return open_at, cutoff


def _safe_collection_reason(error: BaseException) -> str:
    candidate = str(error)
    return candidate if _SAFE_REASON.fullmatch(candidate) is not None else "collector_error"


def _require_safe_id(value: str) -> None:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None or value in {".", ".."}:
        raise ValueError("SPY paginated prefix run id is invalid")


def _parse_session_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("SPY paginated prefix session date is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("SPY paginated prefix session date is invalid") from error


def _parse_utc_marker(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("SPY paginated prefix UTC marker is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("SPY paginated prefix UTC marker is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("SPY paginated prefix UTC marker is invalid")
    return parsed.astimezone(UTC)


def _time_payload(value: datetime) -> dict[str, object]:
    utc_value = require_utc(value, "timing value")
    eastern = utc_value.astimezone(_EASTERN)
    return {
        "utc": _utc_marker(utc_value),
        "eastern": eastern.isoformat(),
        "eastern_utc_offset": eastern.strftime("%z"),
        "eastern_dst": bool(eastern.dst()),
    }


def _parse_time_payload(value: object) -> datetime:
    if not isinstance(value, Mapping):
        raise ValueError("SPY paginated prefix timing payload is invalid")
    utc_value = _parse_utc_marker(value.get("utc"))
    eastern = utc_value.astimezone(_EASTERN)
    if value != _time_payload(utc_value):
        raise ValueError("SPY paginated prefix timing payload is invalid")
    if eastern.tzinfo is None:
        raise ValueError("SPY paginated prefix timing payload is invalid")
    return utc_value


def _external_cache_root(*, cache_root: Path, repository_root: Path, create: bool) -> Path:
    root = cache_root.resolve(strict=False)
    repository = repository_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_market_data = (docker_repository / "market_data").resolve(strict=False)
    mounted_market_data = repository == docker_repository and root.is_relative_to(
        docker_market_data
    )
    if root.is_relative_to(repository) and not mounted_market_data:
        raise ValueError("SPY paginated prefix cache root must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("SPY paginated prefix cache root is invalid")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _external_artifact_root(
    *, artifact_root: Path, repository_root: Path, create: bool = True
) -> Path:
    root = artifact_root.resolve(strict=False)
    repository = repository_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    mounted_artifacts = repository == docker_repository and root.is_relative_to(docker_artifacts)
    if root.is_relative_to(repository) and not mounted_artifacts:
        raise ValueError("SPY paginated prefix artifact root must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("SPY paginated prefix artifact root is invalid")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        raise ValueError("SPY paginated prefix artifact root is unavailable")
    return root


def _read_existing_artifact_bytes(
    *, root: Path, relative_path: Path, error_message: str
) -> bytes:
    if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
        raise ValueError(error_message)
    cursor = root
    for part in relative_path.parts:
        cursor = cursor / part
        if not cursor.exists() or cursor.is_symlink():
            raise ValueError(error_message)
    if not cursor.is_file() or not cursor.resolve(strict=True).is_relative_to(root):
        raise ValueError(error_message)
    return cursor.read_bytes()


def _cache_run_path(*, root: Path, run_id: str) -> Path:
    _require_safe_id(run_id)
    path = root / "runs" / run_id
    if path.exists() and path.is_symlink():
        raise ValueError("SPY paginated prefix cache run path is invalid")
    if not path.resolve(strict=False).is_relative_to(root):
        raise ValueError("SPY paginated prefix cache run path is invalid")
    return path


def _control_artifact_path(*, root: Path, session_date: date, create: bool = True) -> Path:
    directory = (
        root / KIS_SPY_PAGINATED_PREFIX_ARTIFACT_DIRECTORY / "controls" / session_date.isoformat()
    )
    if create:
        _ensure_real_directory(directory, root=root)
    elif directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise ValueError("SPY paginated prefix control artifact path is invalid")
    path = directory / "negative-control.json"
    if path.exists() and path.is_symlink():
        raise ValueError("SPY paginated prefix control artifact path is invalid")
    if not path.resolve(strict=False).is_relative_to(root):
        raise ValueError("SPY paginated prefix control artifact path is invalid")
    return path


def _observation_artifact_path(*, root: Path, run_id: str) -> Path:
    _require_safe_id(run_id)
    directory = root / KIS_SPY_PAGINATED_PREFIX_ARTIFACT_DIRECTORY / "runs" / run_id
    _ensure_real_directory(directory, root=root)
    path = directory / "evidence.json"
    if path.exists() and path.is_symlink():
        raise ValueError("SPY paginated prefix observation artifact path is invalid")
    if not path.resolve(strict=False).is_relative_to(root):
        raise ValueError("SPY paginated prefix observation artifact path is invalid")
    return path


def _ensure_real_directory(path: Path, *, root: Path) -> Path:
    try:
        parts = path.relative_to(root).parts
    except ValueError as error:
        raise ValueError("SPY paginated prefix directory is invalid") from error
    cursor = root
    if cursor.exists() and (cursor.is_symlink() or not cursor.is_dir()):
        raise ValueError("SPY paginated prefix directory is invalid")
    for part in parts:
        cursor = cursor / part
        if cursor.exists():
            if cursor.is_symlink() or not cursor.is_dir():
                raise ValueError("SPY paginated prefix directory is invalid")
        else:
            cursor.mkdir()
        if not cursor.resolve(strict=True).is_relative_to(root):
            raise ValueError("SPY paginated prefix directory is invalid")
    return path


def _remove_empty_or_owned_staging(path: Path, *, root: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError("SPY paginated prefix staging path is invalid")
    for child in path.iterdir():
        if child.is_symlink() or not child.is_file():
            raise ValueError("SPY paginated prefix staging path is invalid")
        child.unlink()
    path.rmdir()


def _write_or_verify(path: Path, payload: Mapping[str, object], *, root: Path) -> None:
    _ensure_real_directory(path.parent, root=root)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.is_symlink() or path.read_text(encoding="ascii") != rendered:
            raise ValueError("SPY paginated prefix evidence identity conflicts")
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
            if path.is_symlink() or path.read_text(encoding="ascii") != rendered:
                raise ValueError("SPY paginated prefix evidence identity conflicts")
            return
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _decode_object(encoded: bytes, error_message: str) -> dict[str, object]:
    try:
        value = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(error_message) from error
    if not isinstance(value, dict):
        raise ValueError(error_message)
    return value


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value, flags=re.ASCII))


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")

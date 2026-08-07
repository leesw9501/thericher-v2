"""Small two-target adapter around the existing KIS Paper minute probe."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_minute_capability_probe import (
    KisPaperMinuteCapabilityProbeOutcome,
    run_kis_paper_minute_capability_probe,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
)
from thericher_v2.execution.kis_market_data_rate_gate import (
    KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
)

KIS_PAPER_M1_HISTORICAL_REACH_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
KIS_PAPER_M1_HISTORICAL_REACH_MAX_PAGES_PER_TARGET = 2
KIS_PAPER_M1_HISTORICAL_REACH_ARTIFACT_DIRECTORY = "data/kis-paper-m1-historical-reach-probe-v1"
KIS_PAPER_M1_HISTORICAL_REACH_MIN_INTERVAL_SECONDS = 1.0


class KisPaperM1HistoricalReachProbeClient(Protocol):
    """Read-only client surface shared by the fixed two-target run."""

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts: ...

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage: ...


@dataclass(frozen=True)
class KisPaperM1HistoricalReachTargetOutcome:
    """Source-safe result for one fixed target within a shared-client probe."""

    target_key: str
    request_scope: Literal["current_day_only", "current_and_previous_day"]
    status: Literal["complete", "partial", "unavailable", "skipped"]
    accepted_page_count: int
    continuation_category: str
    cursor_progress_category: str
    historical_range_category: str
    minute_spacing_category: str
    response_class: str
    token_context_category: Literal[
        "not_observed",
        "issued_for_shared_client",
        "reused_shared_client_token",
        "multiple_token_attempts",
    ]
    request_start_category: str
    tested_request_interval_seconds: float
    token_request_count: int
    minute_page_request_count: int
    request_attempt_count: int
    categorical_limit_or_error_count: int
    elapsed_time_category: str
    next_due: Literal["provider_rate_limit_backoff", "token_start_guard"] | None
    observed_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if (
            self.target_key not in _target_keys()
            or self.request_scope not in {"current_day_only", "current_and_previous_day"}
            or not 0
            <= self.accepted_page_count
            <= KIS_PAPER_M1_HISTORICAL_REACH_MAX_PAGES_PER_TARGET
            or min(
                self.token_request_count,
                self.minute_page_request_count,
                self.request_attempt_count,
            )
            < 0
            or self.request_attempt_count
            != self.token_request_count + self.minute_page_request_count
            or self.categorical_limit_or_error_count not in {0, 1}
            or not self.response_class
            or not _is_supported_interval(self.tested_request_interval_seconds)
        ):
            raise ValueError("historical reach target outcome is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": "kis_paper_m1_historical_reach_target_probe",
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": self.target_key,
            "request_scope": self.request_scope,
            "status": self.status,
            "observed_at": self.observed_at.isoformat(),
            "accepted_page_count": self.accepted_page_count,
            "page_budget": KIS_PAPER_M1_HISTORICAL_REACH_MAX_PAGES_PER_TARGET,
            "continuation_category": self.continuation_category,
            "cursor_progress_category": self.cursor_progress_category,
            "historical_range_category": self.historical_range_category,
            "minute_spacing_category": self.minute_spacing_category,
            "response_class": self.response_class,
            "token_context_category": self.token_context_category,
            "request_start_category": self.request_start_category,
            "tested_request_interval_seconds": self.tested_request_interval_seconds,
            "token_request_count": self.token_request_count,
            "minute_page_request_count": self.minute_page_request_count,
            "request_attempt_count": self.request_attempt_count,
            "categorical_limit_or_error_count": self.categorical_limit_or_error_count,
            "elapsed_time_category": self.elapsed_time_category,
            "raw_market_data_retained": False,
        }
        if self.next_due is not None:
            payload["next_due"] = self.next_due
        return payload


@dataclass(frozen=True)
class KisPaperM1HistoricalReachProbeResult:
    outcomes: tuple[KisPaperM1HistoricalReachTargetOutcome, ...]
    evidence_paths: tuple[Path, ...]

    @property
    def status(self) -> Literal["complete", "partial", "unavailable"]:
        statuses = {outcome.status for outcome in self.outcomes}
        if statuses == {"complete"}:
            return "complete"
        if statuses <= {"unavailable", "skipped"}:
            return "unavailable"
        return "partial"

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_m1_historical_reach_probe",
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "status": self.status,
            "target_count": len(self.outcomes),
            "raw_market_data_retained": False,
            "targets": [outcome.safe_payload() for outcome in self.outcomes],
        }


def run_kis_paper_m1_historical_reach_probe(
    *,
    client: KisPaperM1HistoricalReachProbeClient,
    request_start_times: list[datetime],
    observed_at: datetime | None = None,
    tested_request_interval_seconds: float = KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    include_previous_day: bool = False,
    monotonic_clock: Callable[[], float],
) -> tuple[KisPaperM1HistoricalReachTargetOutcome, ...]:
    """Run one at-most-two-page probe per fixed target with a shared client."""

    if not _is_supported_interval(tested_request_interval_seconds):
        raise ValueError("historical reach tested request interval is invalid")
    if type(include_previous_day) is not bool:
        raise ValueError("historical reach previous-day scope is invalid")
    captured_at = require_utc(observed_at or datetime.now(UTC), "observed_at")
    scope: Literal["current_day_only", "current_and_previous_day"] = (
        "current_and_previous_day" if include_previous_day else "current_day_only"
    )
    outcomes: list[KisPaperM1HistoricalReachTargetOutcome] = []
    shared_next_due: Literal["provider_rate_limit_backoff", "token_start_guard"] | None = None
    for symbol, exchange in KIS_PAPER_M1_HISTORICAL_REACH_TARGETS:
        target_key = _target_key(symbol, exchange)
        if shared_next_due is not None:
            outcomes.append(
                _skipped_outcome(
                    target_key=target_key,
                    request_scope=scope,
                    observed_at=captured_at,
                    tested_request_interval_seconds=tested_request_interval_seconds,
                    next_due=shared_next_due,
                )
            )
            continue
        request_start_offset = len(request_start_times)
        scoped_client = _TargetScopedClient(
            delegate=client,
            start_counts=client.call_counts,
        )
        outcome = run_kis_paper_minute_capability_probe(
            client=scoped_client,
            request_start_times=_RequestStartSlice(
                values=request_start_times,
                offset=request_start_offset,
            ),
            observed_at=captured_at,
            max_pages=KIS_PAPER_M1_HISTORICAL_REACH_MAX_PAGES_PER_TARGET,
            repeat_terminal_head_once=False,
            include_previous_day=include_previous_day,
            target=(symbol, exchange),
            tested_request_interval_seconds=tested_request_interval_seconds,
            monotonic_clock=monotonic_clock,
        )
        normalized = _normalize_outcome(
            probe_outcome=outcome,
            target_key=target_key,
            request_scope=scope,
            contract_violation=scoped_client.contract_violation,
        )
        outcomes.append(normalized)
        shared_next_due = normalized.next_due
    return tuple(outcomes)


def probe_and_write_kis_paper_m1_historical_reach(
    *,
    client: KisPaperM1HistoricalReachProbeClient,
    request_start_times: list[datetime],
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime | None = None,
    tested_request_interval_seconds: float = KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS,
    include_previous_day: bool = False,
    monotonic_clock: Callable[[], float],
) -> KisPaperM1HistoricalReachProbeResult:
    outcomes = run_kis_paper_m1_historical_reach_probe(
        client=client,
        request_start_times=request_start_times,
        observed_at=observed_at,
        tested_request_interval_seconds=tested_request_interval_seconds,
        include_previous_day=include_previous_day,
        monotonic_clock=monotonic_clock,
    )
    return KisPaperM1HistoricalReachProbeResult(
        outcomes=outcomes,
        evidence_paths=write_kis_paper_m1_historical_reach_evidence(
            outcomes,
            artifact_root=artifact_root,
            repository_root=repository_root,
        ),
    )


def validate_kis_paper_m1_historical_reach_artifact_root(
    *, artifact_root: Path, repository_root: Path
) -> Path:
    """Reject unsafe receipt roots before a credential-bearing client is built."""

    root = Path(artifact_root)
    repository = Path(repository_root).resolve()
    if root.resolve().is_relative_to(repository):
        raise ValueError("historical reach artifact root must stay outside Git")
    _reject_links(root)
    return root


def write_kis_paper_m1_historical_reach_evidence(
    outcomes: Sequence[KisPaperM1HistoricalReachTargetOutcome],
    *,
    artifact_root: Path,
    repository_root: Path,
) -> tuple[Path, ...]:
    """Write one immutable metadata-only receipt below each target's external root."""

    if tuple(outcome.target_key for outcome in outcomes) != _target_keys():
        raise ValueError("historical reach outcomes must cover each fixed target once")
    root = validate_kis_paper_m1_historical_reach_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    paths: list[Path] = []
    for outcome in outcomes:
        encoded = (
            json.dumps(outcome.safe_payload(), ensure_ascii=True, sort_keys=True) + "\n"
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()[:16]
        destination = (
            root
            / KIS_PAPER_M1_HISTORICAL_REACH_ARTIFACT_DIRECTORY
            / f"target={outcome.target_key.removesuffix('/1m').replace('/', '-')}"
            / f"{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
        )
        _validate_destination(destination=destination, artifact_root=root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _validate_destination(destination=destination, artifact_root=root)
        if destination.exists():
            if destination.read_bytes() != encoded:
                raise ValueError("historical reach evidence conflicts")
            paths.append(destination)
            continue
        staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
        try:
            staging.write_bytes(encoded)
            os.replace(staging, destination)
        finally:
            staging.unlink(missing_ok=True)
        paths.append(destination)
    return tuple(paths)


@dataclass
class _TargetScopedClient:
    delegate: KisPaperM1HistoricalReachProbeClient
    start_counts: KisPaperMarketDataCallCounts
    contract_violation: str | None = None

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        end = self.delegate.call_counts
        values = (
            end.token_attempts - self.start_counts.token_attempts,
            end.minute_page_attempts - self.start_counts.minute_page_attempts,
            end.daily_page_attempts - self.start_counts.daily_page_attempts,
        )
        if min(values) < 0 or values[2]:
            raise ValueError("historical reach client count delta is invalid")
        return KisPaperMarketDataCallCounts(*values)

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage:
        if before_request is None:
            page = self.delegate.fetch_minute_page(query)
        else:
            page = self.delegate.fetch_minute_page(query, before_request=before_request)
        if page.query.symbol != query.symbol or page.query.exchange != query.exchange:
            self.contract_violation = "minute_target_mismatch"
        elif not page.bars:
            self.contract_violation = "minute_response_empty"
        elif page.continuation_signal == "unrecognized_nonblank":
            self.contract_violation = "unrecognized_continuation"
        if self.contract_violation is not None:
            raise KisPaperMarketDataError(self.contract_violation)
        return page


@dataclass(frozen=True)
class _RequestStartSlice(Sequence[datetime]):
    """A live per-target view while the shared transport appends start times."""

    values: list[datetime]
    offset: int

    def __len__(self) -> int:
        return len(self.values) - self.offset

    def __getitem__(self, index: int | slice) -> datetime | list[datetime]:
        return self.values[self.offset :][index]


def _normalize_outcome(
    *,
    probe_outcome: KisPaperMinuteCapabilityProbeOutcome,
    target_key: str,
    request_scope: Literal["current_day_only", "current_and_previous_day"],
    contract_violation: str | None,
) -> KisPaperM1HistoricalReachTargetOutcome:
    invalid_pagination = probe_outcome.continuation_category in {
        "duplicate_conflict",
        "cursor_stalled",
    }
    status: Literal["complete", "partial", "unavailable"] = probe_outcome.status
    response_class = probe_outcome.response_class
    if contract_violation is not None:
        response_class = contract_violation
    if (invalid_pagination or contract_violation is not None) and status == "complete":
        status = "partial"
        response_class = contract_violation or probe_outcome.continuation_category
    next_due = _next_due_for_response(response_class)
    return KisPaperM1HistoricalReachTargetOutcome(
        target_key=target_key,
        request_scope=request_scope,
        status=status,
        accepted_page_count=probe_outcome.accepted_page_count,
        continuation_category=(
            "unrecognized_continuation"
            if contract_violation == "unrecognized_continuation"
            else probe_outcome.continuation_category
        ),
        cursor_progress_category=probe_outcome.cursor_progress_category,
        historical_range_category=probe_outcome.historical_range_category,
        minute_spacing_category=probe_outcome.minute_spacing_category,
        response_class=response_class,
        token_context_category=_token_context_category(
            probe_outcome=probe_outcome,
        ),
        request_start_category=probe_outcome.request_start_category,
        tested_request_interval_seconds=probe_outcome.tested_request_interval_seconds,
        token_request_count=probe_outcome.token_request_count,
        minute_page_request_count=probe_outcome.minute_page_request_count,
        request_attempt_count=probe_outcome.request_attempt_count,
        categorical_limit_or_error_count=int(
            bool(
                probe_outcome.categorical_limit_or_error_count
                or invalid_pagination
                or contract_violation
            )
        ),
        elapsed_time_category=probe_outcome.elapsed_time_category,
        next_due=next_due,
        observed_at=probe_outcome.observed_at,
    )


def _skipped_outcome(
    *,
    target_key: str,
    request_scope: Literal["current_day_only", "current_and_previous_day"],
    observed_at: datetime,
    tested_request_interval_seconds: float,
    next_due: Literal["provider_rate_limit_backoff", "token_start_guard"],
) -> KisPaperM1HistoricalReachTargetOutcome:
    return KisPaperM1HistoricalReachTargetOutcome(
        target_key=target_key,
        request_scope=request_scope,
        status="skipped",
        accepted_page_count=0,
        continuation_category="skipped",
        cursor_progress_category="skipped",
        historical_range_category="not_observed",
        minute_spacing_category="not_observed",
        response_class="shared_cooldown",
        token_context_category="not_observed",
        request_start_category="not_observed",
        tested_request_interval_seconds=tested_request_interval_seconds,
        token_request_count=0,
        minute_page_request_count=0,
        request_attempt_count=0,
        categorical_limit_or_error_count=0,
        elapsed_time_category="under_5_seconds",
        next_due=next_due,
        observed_at=observed_at,
    )


def _token_context_category(
    *, probe_outcome: KisPaperMinuteCapabilityProbeOutcome
) -> Literal[
    "not_observed",
    "issued_for_shared_client",
    "reused_shared_client_token",
    "multiple_token_attempts",
]:
    if probe_outcome.minute_page_request_count == 0 and probe_outcome.token_request_count == 0:
        return "not_observed"
    if probe_outcome.token_request_count == 0:
        return "reused_shared_client_token"
    if probe_outcome.token_request_count == 1:
        return "issued_for_shared_client"
    return "multiple_token_attempts"


def _next_due_for_response(
    response_class: str,
) -> Literal["provider_rate_limit_backoff", "token_start_guard"] | None:
    if response_class == "rate_limited":
        return "provider_rate_limit_backoff"
    if response_class == "token_request_not_due":
        return "token_start_guard"
    return None


def _target_keys() -> tuple[str, ...]:
    return tuple(
        _target_key(symbol, exchange) for symbol, exchange in KIS_PAPER_M1_HISTORICAL_REACH_TARGETS
    )


def _target_key(symbol: str, exchange: str) -> str:
    return f"{symbol}/{exchange}/1m"


def _is_supported_interval(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and KIS_PAPER_M1_HISTORICAL_REACH_MIN_INTERVAL_SECONDS
        <= float(value)
        <= KIS_PAPER_MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS
    )


def _validate_destination(*, destination: Path, artifact_root: Path) -> None:
    if not destination.is_relative_to(artifact_root):
        raise ValueError("historical reach evidence destination is invalid")
    _reject_links(destination.parent)
    if not destination.parent.resolve().is_relative_to(artifact_root.resolve()):
        raise ValueError("historical reach evidence destination is invalid")


def _reject_links(path: Path) -> None:
    current = path
    while True:
        if current.exists() and _is_link_or_reparse_point(current):
            raise ValueError("historical reach artifact path must not contain links")
        if current == current.parent:
            return
        current = current.parent


def _is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))

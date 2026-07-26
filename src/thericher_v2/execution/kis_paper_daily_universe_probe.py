"""Bounded NAS-only KIS Paper daily capability probe.

This module advances the data-collection loop by testing whether a fixed,
prospective six-symbol NASDAQ registry can be read through the already
authorized KIS Paper daily endpoint.  It does not read configuration, issue
orders, inspect accounts, or make a network client itself.  Callers supply a
preconfigured daily-only client and may persist raw rows only to an external
private cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol
from urllib.parse import urlsplit

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.official_symbol_directory_nas_probe import (
    NAS_COMMON_STOCK_PROBE_SYMBOLS,
    NAS_COMMON_STOCK_PROBE_TARGET_COUNT,
    NAS_EXCHANGE,
    OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256,
    NasProbeTarget,
    OfficialSymbolDirectoryNasProbeRegistry,
)

from .kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
)
from .kis_private_daily_collector import (
    _compressed_raw_daily_csv,
    _external_cache_root,
    _validate_compressed_raw_daily_csv,
    _write_bytes_and_sync,
)

KIS_PAPER_DAILY_UNIVERSE_PROBE_VERSION = "kis-paper-daily-universe-probe-v1"
KIS_PAPER_DAILY_UNIVERSE_PROBE_OBJECTIVE_ID = "kis-paper-daily-universe-probe-v1"
KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT = NAS_COMMON_STOCK_PROBE_TARGET_COUNT
KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET = 2
KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT = Path(
    "D:/market_data/us_equities/kis_paper_private/daily-universe-probe/v1"
)
KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT = Path(
    "D:/thericher-v2/model-artifacts/kis-paper-daily-universe-probe-v1"
)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_SAFE_UNSUPPORTED_REASONS = frozenset({"daily_response_rejected"})
_SAFE_RESUMABLE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "paper_host_required",
        "pacing_delay_not_met",
        "rate_limited",
        "transport_failure",
    }
)
_SAFE_FAILURE_REASONS = _SAFE_UNSUPPORTED_REASONS | _SAFE_RESUMABLE_REASONS | {
    "daily_duplicate_conflict",
    "daily_response_invalid",
    "daily_scope_mismatch",
    "daily_cursor_not_progressed",
    "empty_daily_response",
    "request_not_allowlisted",
    "unexpected_daily_probe_error",
}


class KisPaperDailyUniverseProbeError(RuntimeError):
    """A source-safe failure in the isolated daily-universe probe."""


class KisPaperDailyUniverseProbeClient(Protocol):
    """The only client surface the probe needs from a supplied Paper client."""

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts: ...

    def ensure_authenticated(self) -> None: ...

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage: ...


class UrllibKisPaperDailyUniverseProbeTransport(UrllibKisPaperMarketDataTransport):
    """Paper transport restricted to one registry's daily GET pairs plus tokens.

    The base transport retains its ordinary global scope.  This subclass is
    created only for the short-lived capability probe and refuses minute or
    other GET routes before delegating the daily allowlist validation to the
    base transport's shared direct-only request path.
    """

    def __init__(
        self,
        *,
        registry: OfficialSymbolDirectoryNasProbeRegistry,
        timeout_seconds: float = 15.0,
        request_gate: object | None = None,
        token_start_gate: object | None = None,
    ) -> None:
        super().__init__(
            timeout_seconds=timeout_seconds,
            request_gate=request_gate,  # type: ignore[arg-type]
            token_start_gate=token_start_gate,  # type: ignore[arg-type]
        )
        self._daily_symbol_exchanges = _registry_daily_symbol_exchanges(registry)

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        if request.method == "GET" and urlsplit(request.url).path != KIS_PAPER_DAILY_PATH:
            raise KisPaperMarketDataError("request_not_allowlisted")
        return self._request_with_daily_symbol_exchanges(
            request,
            daily_symbol_exchanges=self._daily_symbol_exchanges,
        )


@dataclass(frozen=True)
class KisPaperDailyUniverseProbePage:
    """Source-safe facts from one accepted raw daily response page."""

    page_number: int
    row_count: int
    newest_date: str | None
    oldest_date: str | None
    continuation_advertised: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not (1 <= self.page_number <= KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET):
            raise ValueError("daily universe probe page number is invalid")
        if self.row_count < 0:
            raise ValueError("daily universe probe page row count is invalid")
        if (self.newest_date is None) != (self.oldest_date is None):
            raise ValueError("daily universe probe page bounds are incomplete")
        for value in (self.newest_date, self.oldest_date):
            if value is not None and (len(value) != 8 or not value.isdigit()):
                raise ValueError("daily universe probe page date is invalid")
        if (
            self.newest_date is not None
            and self.oldest_date is not None
            and self.newest_date < self.oldest_date
        ):
            raise ValueError("daily universe probe page bounds are invalid")
        if not isinstance(self.continuation_advertised, bool):
            raise ValueError("daily universe probe continuation is invalid")


@dataclass(frozen=True)
class KisPaperDailyUniverseProbeTargetResult:
    """One registry target's bounded, replayable capability observation."""

    symbol: str
    exchange: str
    classification: Literal["accepted", "source_limited", "unsupported", "invalid"]
    recovery: Literal["complete", "resume", "restart"]
    reason: str | None
    pages: tuple[KisPaperDailyUniverseProbePage, ...]
    daily_page_attempts: int
    duplicate_rows_removed: int
    rows: tuple[KisPaperDailyRawRow, ...] = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "pages", tuple(self.pages))
        object.__setattr__(self, "rows", tuple(self.rows))
        if not self.symbol.isascii() or not self.symbol.isalnum() or self.exchange != NAS_EXCHANGE:
            raise ValueError("daily universe probe target result is invalid")
        if self.classification not in {"accepted", "source_limited", "unsupported", "invalid"}:
            raise ValueError("daily universe probe classification is invalid")
        if self.recovery not in {"complete", "resume", "restart"}:
            raise ValueError("daily universe probe recovery is invalid")
        if self.reason is not None and self.reason not in _SAFE_FAILURE_REASONS:
            raise ValueError("daily universe probe reason is invalid")
        if not all(isinstance(page, KisPaperDailyUniverseProbePage) for page in self.pages):
            raise ValueError("daily universe probe pages are invalid")
        if [page.page_number for page in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("daily universe probe pages are unordered")
        if len(self.pages) > KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET:
            raise ValueError("daily universe probe page limit is invalid")
        if not (
            0
            <= self.daily_page_attempts
            <= KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET
        ):
            raise ValueError("daily universe probe request count is invalid")
        if self.daily_page_attempts < len(self.pages) or self.duplicate_rows_removed < 0:
            raise ValueError("daily universe probe request facts are invalid")
        if not all(isinstance(row, KisPaperDailyRawRow) for row in self.rows):
            raise ValueError("daily universe probe raw rows are invalid")
        if tuple(row.xymd for row in self.rows) != tuple(sorted(row.xymd for row in self.rows)):
            raise ValueError("daily universe probe raw rows are unordered")
        if len({row.xymd for row in self.rows}) != len(self.rows):
            raise ValueError("daily universe probe raw rows are duplicated")
        if self.classification == "accepted":
            if not self.rows or self.reason is not None or self.recovery != "complete":
                raise ValueError("accepted daily universe probe result is invalid")
        elif self.rows:
            raise ValueError("non-accepted daily universe probe result cannot retain raw rows")
        if self.classification == "source_limited" and (
            self.reason != "empty_daily_response" or self.recovery != "complete"
        ):
            raise ValueError("source-limited daily universe probe result is invalid")
        if self.classification == "unsupported" and (
            self.reason not in _SAFE_UNSUPPORTED_REASONS or self.recovery != "complete"
        ):
            raise ValueError("unsupported daily universe probe result is invalid")
        if self.classification == "invalid" and (
            self.reason is None or self.recovery not in {"resume", "restart"}
        ):
            raise ValueError("invalid daily universe probe result is invalid")

    @property
    def target_key(self) -> str:
        return f"{self.symbol}/{self.exchange}"

    @property
    def input_row_count(self) -> int:
        return sum(page.row_count for page in self.pages)

    @property
    def stop_outcome(self) -> str:
        if self.classification == "accepted":
            return "two_pages_completed" if len(self.pages) == 2 else "source_exhausted"
        assert self.reason is not None
        return self.reason

    def source_safe_document(self) -> dict[str, object]:
        """Return only metadata that can safely appear in a cache manifest."""

        return {
            "target_key": self.target_key,
            "classification": self.classification,
            "recovery": self.recovery,
            "reason": self.reason,
            "stop_outcome": self.stop_outcome,
            "requests": {
                "max_pages": KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET,
                "page_attempts": self.daily_page_attempts,
                "accepted_pages": len(self.pages),
                "continuation_cursors_persisted": False,
            },
            "pages": [
                {
                    "index": page.page_number,
                    "row_count": page.row_count,
                    "newest_session_date": _iso_date(page.newest_date),
                    "oldest_session_date": _iso_date(page.oldest_date),
                    "continuation_advertised": page.continuation_advertised,
                }
                for page in self.pages
            ],
            "deduplication": {
                "key": ["symbol", "exchange", "session_date"],
                "input_row_count": self.input_row_count,
                "unique_row_count": len(self.rows),
                "exact_duplicate_rows_removed": self.duplicate_rows_removed,
                "conflict_policy": "invalidate_target",
            },
        }


@dataclass(frozen=True)
class KisPaperDailyUniverseProbeResult:
    """One complete six-target capability probe with no account or order facts."""

    observed_at: datetime
    anchor_date: str
    code_revision: str
    registry: OfficialSymbolDirectoryNasProbeRegistry
    target_results: tuple[KisPaperDailyUniverseProbeTargetResult, ...]
    call_counts: KisPaperMarketDataCallCounts
    recovery: Literal["complete", "resume", "restart"]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "anchor_date", self.anchor_date.strip())
        object.__setattr__(self, "target_results", tuple(self.target_results))
        _registry_daily_symbol_exchanges(self.registry)
        if len(self.anchor_date) != 8 or not self.anchor_date.isdigit():
            raise ValueError("daily universe probe anchor date is invalid")
        if not self.code_revision or "\n" in self.code_revision or len(self.code_revision) > 256:
            raise ValueError("daily universe probe code revision is invalid")
        if not isinstance(self.call_counts, KisPaperMarketDataCallCounts) or (
            self.call_counts.token_attempts < 0
            or self.call_counts.minute_page_attempts != 0
            or not (
                0
                <= self.call_counts.daily_page_attempts
                <= KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT
                * KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET
            )
        ):
            raise ValueError("daily universe probe call counts are invalid")
        expected_keys = tuple(
            f"{target.symbol}/{target.exchange}" for target in self.registry.targets
        )
        actual_keys = tuple(result.target_key for result in self.target_results)
        if actual_keys != expected_keys:
            raise ValueError("daily universe probe target results do not match registry")
        if self.recovery not in {"complete", "resume", "restart"}:
            raise ValueError("daily universe probe recovery is invalid")
        if self.recovery == "complete" and any(
            target.recovery != "complete" for target in self.target_results
        ):
            raise ValueError("daily universe probe recovery does not match targets")

    @property
    def accepted_target_count(self) -> int:
        return sum(target.classification == "accepted" for target in self.target_results)


@dataclass(frozen=True)
class KisPaperDailyUniverseProbeTargetState:
    """A raw-row-free target state returned by the public one-shot runner."""

    target_key: str
    classification: Literal["accepted", "source_limited", "unsupported", "invalid"]
    recovery: Literal["complete", "resume", "restart"]
    reason: str | None
    stop_outcome: str
    daily_page_attempts: int
    accepted_pages: int
    input_row_count: int
    unique_row_count: int
    duplicate_rows_removed: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.target_key.endswith(f"/{NAS_EXCHANGE}") or self.target_key.count("/") != 1:
            raise ValueError("daily universe probe target state is invalid")
        if self.classification not in {"accepted", "source_limited", "unsupported", "invalid"}:
            raise ValueError("daily universe probe target state is invalid")
        if self.recovery not in {"complete", "resume", "restart"}:
            raise ValueError("daily universe probe target state is invalid")
        if self.reason is not None and self.reason not in _SAFE_FAILURE_REASONS:
            raise ValueError("daily universe probe target state is invalid")
        if self.stop_outcome not in _SAFE_FAILURE_REASONS | {
            "source_exhausted",
            "two_pages_completed",
        }:
            raise ValueError("daily universe probe target state is invalid")
        if not (
            0 <= self.daily_page_attempts <= KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET
            and 0 <= self.accepted_pages <= self.daily_page_attempts
            and self.input_row_count >= 0
            and self.unique_row_count >= 0
            and self.duplicate_rows_removed >= 0
        ):
            raise ValueError("daily universe probe target state is invalid")


@dataclass(frozen=True)
class KisPaperDailyUniverseProbeRun:
    """Source-safe state from one persisted six-target capability probe."""

    observed_at: datetime
    anchor_date: str
    code_revision: str
    registry_version: str
    registry_sha256: str
    source_manifest_sha256: str
    source_file_sha256: str
    registry_target_keys: tuple[str, ...]
    target_states: tuple[KisPaperDailyUniverseProbeTargetState, ...]
    call_counts: KisPaperMarketDataCallCounts
    recovery: Literal["complete", "resume", "restart"]
    manifest_path: Path
    manifest_sha256: str
    evidence_path: Path
    evidence_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "anchor_date", _valid_anchor_date(self.anchor_date))
        object.__setattr__(self, "registry_target_keys", tuple(self.registry_target_keys))
        object.__setattr__(self, "target_states", tuple(self.target_states))
        object.__setattr__(self, "manifest_path", Path(self.manifest_path))
        object.__setattr__(self, "evidence_path", Path(self.evidence_path))
        if (
            not self.code_revision
            or not self.registry_version
            or not _is_sha256(self.registry_sha256)
            or not _is_sha256(self.source_manifest_sha256)
            or not _is_sha256(self.source_file_sha256)
            or len(self.registry_target_keys) != KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT
            or len(set(self.registry_target_keys)) != KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT
            or tuple(state.target_key for state in self.target_states) != self.registry_target_keys
            or not isinstance(self.call_counts, KisPaperMarketDataCallCounts)
            or self.call_counts.minute_page_attempts != 0
            or self.recovery not in {"complete", "resume", "restart"}
            or not self.manifest_path.name == "manifest.json"
            or not _is_sha256(self.manifest_sha256)
            or not self.evidence_path.name == "evidence.json"
            or not _is_sha256(self.evidence_sha256)
        ):
            raise ValueError("daily universe probe run is invalid")


@dataclass(frozen=True)
class _PersistedProbeSnapshot:
    """Validated source-safe facts needed to repair an interrupted evidence write."""

    observed_at: datetime
    anchor_date: str
    code_revision: str
    registry: OfficialSymbolDirectoryNasProbeRegistry
    target_states: tuple[KisPaperDailyUniverseProbeTargetState, ...]
    call_counts: KisPaperMarketDataCallCounts
    recovery: Literal["complete", "resume", "restart"]
    manifest_path: Path
    manifest_sha256: str
    manifest: Mapping[str, object]


def _collect_kis_paper_daily_universe_probe(
    client: KisPaperDailyUniverseProbeClient,
    *,
    registry: OfficialSymbolDirectoryNasProbeRegistry,
    anchor_date: str,
    code_revision: str,
    observed_at: datetime | None = None,
) -> KisPaperDailyUniverseProbeResult:
    """Probe exactly six registry targets through one supplied read-only client."""

    scope = _registry_daily_symbol_exchanges(registry)
    normalized_anchor_date = _valid_anchor_date(anchor_date)
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    initial_counts = _validated_call_counts(client.call_counts)
    authentication_error: BaseException | None = None
    try:
        client.ensure_authenticated()
    except (KisPaperMarketDataError, ValueError) as error:
        authentication_error = error

    target_results: list[KisPaperDailyUniverseProbeTargetResult] = []
    for target in registry.targets:
        if authentication_error is not None:
            target_results.append(
                _failure_result(
                    target=target,
                    daily_page_attempts=0,
                    error=authentication_error,
                )
            )
            continue
        target_results.append(
            _probe_target(
                client=client,
                target=target,
                anchor_date=normalized_anchor_date,
                daily_symbol_exchanges=scope,
            )
        )

    final_counts = _validated_call_counts(client.call_counts)
    delta = _call_count_delta(initial=initial_counts, final=final_counts)
    recovery = _combined_recovery(target_results)
    return KisPaperDailyUniverseProbeResult(
        observed_at=observed,
        anchor_date=normalized_anchor_date,
        code_revision=code_revision,
        registry=registry,
        target_results=tuple(target_results),
        call_counts=delta,
        recovery=recovery,
    )


def run_kis_paper_daily_universe_probe(
    client: KisPaperDailyUniverseProbeClient,
    *,
    registry: OfficialSymbolDirectoryNasProbeRegistry,
    cache_root: Path = KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    artifact_root: Path = KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT,
    code_revision: str,
    observed_at: datetime,
    anchor_date: str | None = None,
    run_id: str | None = None,
) -> KisPaperDailyUniverseProbeRun:
    """Collect, persist, and return source-safe state for one fixed registry.

    ``client`` must already be a KIS Paper daily-only client configured with
    :class:`UrllibKisPaperDailyUniverseProbeTransport` (or an equivalent
    registry-pinned transport).  The function neither loads credentials nor
    constructs a network client.
    """

    observed = require_utc(observed_at, "observed_at")
    normalized_run_id = run_id or observed.strftime("%Y%m%dT%H%M%SZ")
    _valid_run_id(normalized_run_id)
    resolved_cache_root, resolved_artifact_root = _validated_storage_roots(
        cache_root=cache_root,
        artifact_root=artifact_root,
    )
    snapshot_directory = _snapshot_directory(
        cache_root=resolved_cache_root,
        run_id=normalized_run_id,
    )
    manifest_path = snapshot_directory / "manifest.json"
    evidence_path = _evidence_directory(
        artifact_root=resolved_artifact_root,
        run_id=normalized_run_id,
    ) / "evidence.json"
    if snapshot_directory.exists() or snapshot_directory.is_symlink():
        if not manifest_path.is_file() or manifest_path.is_symlink():
            raise ValueError("daily universe probe cache recovery requires reconcile")
        return _finalize_persisted_probe_run(
            manifest_path=manifest_path,
            registry=registry,
            artifact_root=resolved_artifact_root,
            run_id=normalized_run_id,
        )
    if evidence_path.exists() or evidence_path.is_symlink():
        raise ValueError("daily universe probe evidence recovery requires reconcile")
    collection = _collect_kis_paper_daily_universe_probe(
        client,
        registry=registry,
        anchor_date=anchor_date or observed.strftime("%Y%m%d"),
        code_revision=code_revision,
        observed_at=observed,
    )
    manifest_path, _ = write_kis_paper_daily_universe_probe_cache(
        result=collection,
        cache_root=resolved_cache_root,
        run_id=normalized_run_id,
    )
    return _finalize_persisted_probe_run(
        manifest_path=manifest_path,
        registry=registry,
        artifact_root=resolved_artifact_root,
        run_id=normalized_run_id,
    )


def run_kis_paper_daily_universe_probe_once(
    client: KisPaperDailyUniverseProbeClient,
    *,
    registry: OfficialSymbolDirectoryNasProbeRegistry,
    cache_root: Path = KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    artifact_root: Path = KIS_PAPER_DAILY_UNIVERSE_PROBE_EVIDENCE_ROOT,
    code_revision: str,
    observed_at: datetime,
    anchor_date: str | None = None,
    run_id: str | None = None,
) -> KisPaperDailyUniverseProbeRun:
    """Compatibility spelling for the source-safe public one-shot runner."""

    return run_kis_paper_daily_universe_probe(
        client,
        registry=registry,
        cache_root=cache_root,
        artifact_root=artifact_root,
        code_revision=code_revision,
        observed_at=observed_at,
        anchor_date=anchor_date,
        run_id=run_id,
    )


def write_kis_paper_daily_universe_probe_cache(
    *,
    result: KisPaperDailyUniverseProbeResult,
    cache_root: Path = KIS_PAPER_DAILY_UNIVERSE_PROBE_CACHE_ROOT,
    run_id: str,
) -> tuple[Path, str]:
    """Atomically persist accepted raw rows and a source-safe probe manifest.

    Raw CSV compression, validation, and durable writes reuse the existing
    private daily cache helpers.  This module only owns the multi-target
    manifest that binds those raw files to the official-registry identity.
    """

    result = _validated_result(result)
    _valid_run_id(run_id)
    root = _probe_cache_root(cache_root=cache_root)
    root.mkdir(parents=True, exist_ok=True)
    snapshot_name = f"snapshot={run_id}-daily-universe-probe-v1"
    target = root / snapshot_name
    if target.exists() or target.is_symlink():
        raise FileExistsError("daily universe probe cache destination already exists")
    staging = root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        raw_documents = _write_accepted_raw_rows(staging=staging, result=result)
        manifest = daily_universe_probe_cache_manifest(
            result=result,
            snapshot_name=snapshot_name,
            raw_documents=raw_documents,
        )
        manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_bytes_and_sync(staging / "manifest.json", manifest_payload)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target / "manifest.json", "sha256:" + hashlib.sha256(manifest_payload).hexdigest()


def daily_universe_probe_cache_manifest(
    *,
    result: KisPaperDailyUniverseProbeResult,
    snapshot_name: str,
    raw_documents: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Build a source-safe manifest without raw rows, headers, or credentials."""

    result = _validated_result(result)
    if not snapshot_name.startswith("snapshot="):
        raise ValueError("daily universe probe snapshot name is invalid")
    expected_raw_keys = {
        target.target_key for target in result.target_results if target.classification == "accepted"
    }
    if set(raw_documents) != expected_raw_keys:
        raise ValueError("daily universe probe raw document keys are invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_daily_universe_capability_probe",
        "dataset_id": f"kis.paper.private.daily.universe.{snapshot_name}",
        "immutable_snapshot": True,
        "probe": {
            "objective_id": KIS_PAPER_DAILY_UNIVERSE_PROBE_OBJECTIVE_ID,
            "version": KIS_PAPER_DAILY_UNIVERSE_PROBE_VERSION,
            "target_count": KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT,
            "max_pages_per_target": KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET,
            "initial_anchor_bymd": result.anchor_date,
        },
        "collected_at_utc": _format_utc(result.observed_at),
        "code_revision": result.code_revision,
        "recovery": result.recovery,
        "registry": {
            "version": result.registry.version,
            "registry_sha256": result.registry.registry_sha256,
            "source_manifest_sha256": result.registry.source_manifest_sha256,
            "source_file_sha256": result.registry.source_file_sha256,
            "source_file_size_bytes": result.registry.source_file_size_bytes,
            "prospective_only": result.registry.prospective_only,
            "historical_point_in_time_eligible": result.registry.historical_point_in_time_eligible,
            "target_keys": list(result.registry.target_keys),
        },
        "source": {
            "provider": "KIS Open API virtual paper",
            "endpoint": "dailyprice",
            "adjustment_mode": "MODP=0_unadjusted",
            "account_or_order_endpoints_used": False,
        },
        "requests": {
            "token_attempts": result.call_counts.token_attempts,
            "minute_page_attempts": result.call_counts.minute_page_attempts,
            "daily_page_attempts": result.call_counts.daily_page_attempts,
        },
        "targets": [target.source_safe_document() for target in result.target_results],
        "files": {
            "raw_daily_rows": {
                key: dict(raw_documents[key]) for key in sorted(raw_documents)
            }
        },
        "storage": {
            "root": "D:\\market_data",
            "private_local_only": True,
            "served": False,
            "redistributed": False,
        },
        "redaction": {
            "credentials_persisted": False,
            "account_facts_persisted": False,
            "order_facts_persisted": False,
            "request_headers_persisted": False,
            "continuation_cursors_persisted": False,
            "response_bodies_persisted": False,
            "raw_rows_in_manifest": False,
        },
    }


def _finalize_persisted_probe_run(
    *,
    manifest_path: Path,
    registry: OfficialSymbolDirectoryNasProbeRegistry,
    artifact_root: Path,
    run_id: str,
) -> KisPaperDailyUniverseProbeRun:
    snapshot = _read_persisted_probe_snapshot(
        manifest_path=manifest_path,
        registry=registry,
    )
    evidence_path = (
        _evidence_directory(artifact_root=artifact_root, run_id=run_id) / "evidence.json"
    )
    if evidence_path.exists() or evidence_path.is_symlink():
        evidence_sha256 = _verify_source_safe_probe_evidence(
            evidence_path=evidence_path,
            manifest_path=snapshot.manifest_path,
            manifest_sha256=snapshot.manifest_sha256,
        )
    else:
        evidence_path, evidence_sha256 = _write_source_safe_probe_evidence(
            snapshot=snapshot,
            artifact_root=artifact_root,
            run_id=run_id,
        )
    return KisPaperDailyUniverseProbeRun(
        observed_at=snapshot.observed_at,
        anchor_date=snapshot.anchor_date,
        code_revision=snapshot.code_revision,
        registry_version=snapshot.registry.version,
        registry_sha256=snapshot.registry.registry_sha256,
        source_manifest_sha256=snapshot.registry.source_manifest_sha256,
        source_file_sha256=snapshot.registry.source_file_sha256,
        registry_target_keys=snapshot.registry.target_keys,
        target_states=snapshot.target_states,
        call_counts=snapshot.call_counts,
        recovery=snapshot.recovery,
        manifest_path=snapshot.manifest_path,
        manifest_sha256=snapshot.manifest_sha256,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
    )


def _write_source_safe_probe_evidence(
    *,
    snapshot: _PersistedProbeSnapshot,
    artifact_root: Path,
    run_id: str,
) -> tuple[Path, str]:
    """Write a raw-row-free evidence pointer from an already durable cache."""

    _valid_run_id(run_id)
    root = _evidence_root(artifact_root=artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"run={run_id}"
    if target.exists() or target.is_symlink():
        raise FileExistsError("daily universe probe evidence destination already exists")
    staging = root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        evidence = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_daily_universe_capability_probe_evidence",
            "run_id": run_id,
            "collected_at_utc": _format_utc(snapshot.observed_at),
            "code_revision": snapshot.code_revision,
            "cache_manifest": {
                "path": str(snapshot.manifest_path),
                "sha256": snapshot.manifest_sha256,
            },
            "registry": {
                "version": snapshot.registry.version,
                "registry_sha256": snapshot.registry.registry_sha256,
                "source_manifest_sha256": snapshot.registry.source_manifest_sha256,
                "source_file_sha256": snapshot.registry.source_file_sha256,
                "target_keys": list(snapshot.registry.target_keys),
            },
            "requests": {
                "token_attempts": snapshot.call_counts.token_attempts,
                "minute_page_attempts": snapshot.call_counts.minute_page_attempts,
                "daily_page_attempts": snapshot.call_counts.daily_page_attempts,
            },
            "recovery": snapshot.recovery,
            "targets": list(snapshot.manifest["targets"]),
            "redaction": {
                "raw_rows_persisted": False,
                "credentials_persisted": False,
                "account_facts_persisted": False,
                "order_facts_persisted": False,
                "request_headers_persisted": False,
                "response_bodies_persisted": False,
            },
        }
        payload = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _write_bytes_and_sync(staging / "evidence.json", payload)
        os.rename(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target / "evidence.json", "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_persisted_probe_snapshot(
    *,
    manifest_path: Path,
    registry: OfficialSymbolDirectoryNasProbeRegistry,
) -> _PersistedProbeSnapshot:
    """Reattest a committed cache before repairing or trusting its evidence."""

    if manifest_path.name != "manifest.json" or manifest_path.is_symlink():
        raise ValueError("daily universe probe persisted manifest is invalid")
    try:
        payload = manifest_path.read_bytes()
        manifest = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("daily universe probe persisted manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise ValueError("daily universe probe persisted manifest is invalid")
    manifest_sha256 = "sha256:" + hashlib.sha256(payload).hexdigest()
    _registry_daily_symbol_exchanges(registry)
    probe = _required_mapping(manifest, "probe")
    registry_document = _required_mapping(manifest, "registry")
    source = _required_mapping(manifest, "source")
    requests = _required_mapping(manifest, "requests")
    files = _required_mapping(manifest, "files")
    if (
        manifest.get("kind") != "kis_paper_daily_universe_capability_probe"
        or manifest.get("immutable_snapshot") is not True
        or probe.get("objective_id") != KIS_PAPER_DAILY_UNIVERSE_PROBE_OBJECTIVE_ID
        or probe.get("version") != KIS_PAPER_DAILY_UNIVERSE_PROBE_VERSION
        or probe.get("target_count") != KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT
        or probe.get("max_pages_per_target") != KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET
        or registry_document.get("version") != registry.version
        or registry_document.get("registry_sha256") != registry.registry_sha256
        or registry_document.get("source_manifest_sha256") != registry.source_manifest_sha256
        or registry_document.get("source_file_sha256") != registry.source_file_sha256
        or registry_document.get("target_keys") != list(registry.target_keys)
        or registry_document.get("prospective_only") is not True
        or registry_document.get("historical_point_in_time_eligible") is not False
        or source.get("provider") != "KIS Open API virtual paper"
        or source.get("endpoint") != "dailyprice"
        or source.get("adjustment_mode") != "MODP=0_unadjusted"
        or source.get("account_or_order_endpoints_used") is not False
    ):
        raise ValueError("daily universe probe persisted manifest is invalid")
    anchor_date = _valid_anchor_date(_required_str(probe, "initial_anchor_bymd"))
    observed_at = _parse_utc(_required_str(manifest, "collected_at_utc"))
    code_revision = _required_str(manifest, "code_revision")
    recovery = manifest.get("recovery")
    if recovery not in {"complete", "resume", "restart"}:
        raise ValueError("daily universe probe persisted manifest is invalid")
    call_counts = KisPaperMarketDataCallCounts(
        token_attempts=_required_nonnegative_int(requests, "token_attempts"),
        minute_page_attempts=_required_nonnegative_int(requests, "minute_page_attempts"),
        daily_page_attempts=_required_nonnegative_int(requests, "daily_page_attempts"),
    )
    if (
        call_counts.minute_page_attempts != 0
        or call_counts.daily_page_attempts
        > KIS_PAPER_DAILY_UNIVERSE_PROBE_TARGET_COUNT
        * KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET
    ):
        raise ValueError("daily universe probe persisted manifest is invalid")
    target_documents = manifest.get("targets")
    if not isinstance(target_documents, list):
        raise ValueError("daily universe probe persisted manifest is invalid")
    target_states = tuple(_target_state_from_document(document) for document in target_documents)
    if tuple(state.target_key for state in target_states) != registry.target_keys:
        raise ValueError("daily universe probe persisted manifest is invalid")
    raw_documents = files.get("raw_daily_rows")
    if not isinstance(raw_documents, Mapping):
        raise ValueError("daily universe probe persisted manifest is invalid")
    _validate_persisted_raw_documents(
        snapshot_root=manifest_path.parent,
        raw_documents=raw_documents,
        target_states=target_states,
    )
    return _PersistedProbeSnapshot(
        observed_at=observed_at,
        anchor_date=anchor_date,
        code_revision=code_revision,
        registry=registry,
        target_states=target_states,
        call_counts=call_counts,
        recovery=recovery,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
    )


def _verify_source_safe_probe_evidence(
    *,
    evidence_path: Path,
    manifest_path: Path,
    manifest_sha256: str,
) -> str:
    if evidence_path.name != "evidence.json" or evidence_path.is_symlink():
        raise ValueError("daily universe probe evidence is invalid")
    try:
        payload = evidence_path.read_bytes()
        evidence = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("daily universe probe evidence is invalid") from error
    if not isinstance(evidence, Mapping):
        raise ValueError("daily universe probe evidence is invalid")
    cache_manifest = evidence.get("cache_manifest")
    redaction = evidence.get("redaction")
    if (
        evidence.get("kind") != "kis_paper_daily_universe_capability_probe_evidence"
        or not isinstance(cache_manifest, Mapping)
        or cache_manifest.get("path") != str(manifest_path)
        or cache_manifest.get("sha256") != manifest_sha256
        or not isinstance(redaction, Mapping)
        or redaction.get("raw_rows_persisted") is not False
    ):
        raise ValueError("daily universe probe evidence is invalid")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _target_state_from_document(value: object) -> KisPaperDailyUniverseProbeTargetState:
    if not isinstance(value, Mapping):
        raise ValueError("daily universe probe persisted target is invalid")
    requests = _required_mapping(value, "requests")
    deduplication = _required_mapping(value, "deduplication")
    pages = value.get("pages")
    if not isinstance(pages, list) or any(not isinstance(page, Mapping) for page in pages):
        raise ValueError("daily universe probe persisted target is invalid")
    if requests.get("max_pages") != KIS_PAPER_DAILY_UNIVERSE_PROBE_MAX_PAGES_PER_TARGET:
        raise ValueError("daily universe probe persisted target is invalid")
    reason_value = value.get("reason")
    reason = None if reason_value is None else _required_str(value, "reason")
    state = KisPaperDailyUniverseProbeTargetState(
        target_key=_required_str(value, "target_key"),
        classification=_required_str(value, "classification"),
        recovery=_required_str(value, "recovery"),
        reason=reason,
        stop_outcome=_required_str(value, "stop_outcome"),
        daily_page_attempts=_required_nonnegative_int(requests, "page_attempts"),
        accepted_pages=_required_nonnegative_int(requests, "accepted_pages"),
        input_row_count=_required_nonnegative_int(deduplication, "input_row_count"),
        unique_row_count=_required_nonnegative_int(deduplication, "unique_row_count"),
        duplicate_rows_removed=_required_nonnegative_int(
            deduplication,
            "exact_duplicate_rows_removed",
        ),
    )
    if len(pages) != state.accepted_pages or value.get("stop_outcome") != state.stop_outcome:
        raise ValueError("daily universe probe persisted target is invalid")
    return state


def _validate_persisted_raw_documents(
    *,
    snapshot_root: Path,
    raw_documents: Mapping[object, object],
    target_states: tuple[KisPaperDailyUniverseProbeTargetState, ...],
) -> None:
    expected_keys = {
        state.target_key for state in target_states if state.classification == "accepted"
    }
    if set(raw_documents) != expected_keys:
        raise ValueError("daily universe probe persisted raw documents are invalid")
    resolved_snapshot_root = snapshot_root.resolve()
    for target_key in expected_keys:
        document = raw_documents[target_key]
        if not isinstance(document, Mapping):
            raise ValueError("daily universe probe persisted raw documents are invalid")
        relative_path = _required_str(document, "path")
        path_parts = Path(relative_path).parts
        if (
            Path(relative_path).is_absolute()
            or len(path_parts) != 2
            or path_parts[0] != "raw"
            or any(part in {"", ".", ".."} for part in path_parts)
        ):
            raise ValueError("daily universe probe persisted raw documents are invalid")
        raw_path = (snapshot_root / Path(relative_path)).resolve()
        try:
            raw_path.relative_to(resolved_snapshot_root)
        except ValueError as error:
            raise ValueError("daily universe probe persisted raw documents are invalid") from error
        if raw_path.is_symlink() or not raw_path.is_file():
            raise ValueError("daily universe probe persisted raw documents are invalid")
        try:
            raw_payload = raw_path.read_bytes()
        except OSError as error:
            raise ValueError("daily universe probe persisted raw documents are invalid") from error
        if (
            document.get("sha256") != "sha256:" + hashlib.sha256(raw_payload).hexdigest()
            or document.get("size_bytes") != len(raw_payload)
            or document.get("format") != "csv.gz"
        ):
            raise ValueError("daily universe probe persisted raw documents are invalid")


def _required_mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise ValueError("daily universe probe persisted document is invalid")
    return result


def _required_str(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError("daily universe probe persisted document is invalid")
    return result


def _required_nonnegative_int(value: Mapping[str, object], key: str) -> int:
    result = value.get(key)
    if type(result) is not int or result < 0:
        raise ValueError("daily universe probe persisted document is invalid")
    return result


def _parse_utc(value: str) -> datetime:
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "value")
    except ValueError as error:
        raise ValueError("daily universe probe persisted document is invalid") from error


def _probe_target(
    *,
    client: KisPaperDailyUniverseProbeClient,
    target: NasProbeTarget,
    anchor_date: str,
    daily_symbol_exchanges: Mapping[str, frozenset[str]],
) -> KisPaperDailyUniverseProbeTargetResult:
    initial_counts = _validated_call_counts(client.call_counts)
    try:
        first_query = KisPaperDailyQuery(
            symbol=target.symbol,
            exchange=target.exchange,
            by_date=anchor_date,
            approved_symbol_exchanges=daily_symbol_exchanges,
        )
        first_page = client.fetch_daily_raw_page(first_query)
        _validate_page(raw_page=first_page, expected_query=first_query)
        pages = [_page_fact(first_page, page_number=1)]
        if not first_page.rows:
            return _source_limited_result(
                target=target,
                pages=pages,
                daily_page_attempts=_call_count_delta(
                    initial=initial_counts,
                    final=_validated_call_counts(client.call_counts),
                ).daily_page_attempts,
            )
        rows_by_date, duplicate_rows_removed = _merge_daily_rows({}, first_page.rows)
        if first_page.page.continuation_available:
            assert first_page.page.oldest_date is not None
            continuation_query = KisPaperDailyQuery(
                symbol=target.symbol,
                exchange=target.exchange,
                by_date=first_page.page.oldest_date,
                continuation="F",
                approved_symbol_exchanges=daily_symbol_exchanges,
            )
            second_page = client.fetch_daily_raw_page(continuation_query)
            _validate_page(raw_page=second_page, expected_query=continuation_query)
            pages.append(_page_fact(second_page, page_number=2))
            if not second_page.rows or not any(
                row.xymd < first_page.page.oldest_date for row in second_page.rows
            ):
                raise KisPaperDailyUniverseProbeError("daily_cursor_not_progressed")
            rows_by_date, additional_duplicates = _merge_daily_rows(rows_by_date, second_page.rows)
            duplicate_rows_removed += additional_duplicates
    except (KisPaperMarketDataError, KisPaperDailyUniverseProbeError, ValueError) as error:
        final_counts = _validated_call_counts(client.call_counts)
        return _failure_result(
            target=target,
            daily_page_attempts=_call_count_delta(
                initial=initial_counts,
                final=final_counts,
            ).daily_page_attempts,
            error=error,
        )
    final_counts = _validated_call_counts(client.call_counts)
    return KisPaperDailyUniverseProbeTargetResult(
        symbol=target.symbol,
        exchange=target.exchange,
        classification="accepted",
        recovery="complete",
        reason=None,
        pages=tuple(pages),
        daily_page_attempts=_call_count_delta(
            initial=initial_counts,
            final=final_counts,
        ).daily_page_attempts,
        duplicate_rows_removed=duplicate_rows_removed,
        rows=tuple(rows_by_date[date] for date in sorted(rows_by_date)),
    )


def _target_state(
    target: KisPaperDailyUniverseProbeTargetResult,
) -> KisPaperDailyUniverseProbeTargetState:
    return KisPaperDailyUniverseProbeTargetState(
        target_key=target.target_key,
        classification=target.classification,
        recovery=target.recovery,
        reason=target.reason,
        stop_outcome=target.stop_outcome,
        daily_page_attempts=target.daily_page_attempts,
        accepted_pages=len(target.pages),
        input_row_count=target.input_row_count,
        unique_row_count=len(target.rows),
        duplicate_rows_removed=target.duplicate_rows_removed,
    )


def _source_limited_result(
    *,
    target: NasProbeTarget,
    pages: list[KisPaperDailyUniverseProbePage],
    daily_page_attempts: int,
) -> KisPaperDailyUniverseProbeTargetResult:
    return KisPaperDailyUniverseProbeTargetResult(
        symbol=target.symbol,
        exchange=target.exchange,
        classification="source_limited",
        recovery="complete",
        reason="empty_daily_response",
        pages=tuple(pages),
        daily_page_attempts=daily_page_attempts,
        duplicate_rows_removed=0,
        rows=(),
    )


def _failure_result(
    *,
    target: NasProbeTarget,
    daily_page_attempts: int,
    error: BaseException,
) -> KisPaperDailyUniverseProbeTargetResult:
    reason = _safe_failure_reason(error)
    classification: Literal["unsupported", "invalid"]
    recovery: Literal["complete", "resume", "restart"]
    if reason in _SAFE_UNSUPPORTED_REASONS:
        classification = "unsupported"
        recovery = "complete"
    else:
        classification = "invalid"
        recovery = "resume" if reason in _SAFE_RESUMABLE_REASONS else "restart"
    return KisPaperDailyUniverseProbeTargetResult(
        symbol=target.symbol,
        exchange=target.exchange,
        classification=classification,
        recovery=recovery,
        reason=reason,
        pages=(),
        daily_page_attempts=daily_page_attempts,
        duplicate_rows_removed=0,
        rows=(),
    )


def _validate_page(*, raw_page: KisPaperDailyRawPage, expected_query: KisPaperDailyQuery) -> None:
    if (
        raw_page.page.query != expected_query
        or dict(raw_page.page.query.approved_symbol_exchanges)
        != dict(expected_query.approved_symbol_exchanges)
    ):
        raise KisPaperDailyUniverseProbeError("daily_scope_mismatch")
    if raw_page.page.continuation_available != (raw_page.page.continuation_value == "F"):
        raise KisPaperDailyUniverseProbeError("daily_response_invalid")
    dates = tuple(row.xymd for row in raw_page.rows)
    if not dates:
        if (
            raw_page.page.newest_date is not None
            or raw_page.page.oldest_date is not None
            or raw_page.page.required_ohlcv_fields_present
        ):
            raise KisPaperDailyUniverseProbeError("daily_response_invalid")
        return
    if (
        raw_page.page.newest_date != max(dates)
        or raw_page.page.oldest_date != min(dates)
        or not raw_page.page.required_ohlcv_fields_present
    ):
        raise KisPaperDailyUniverseProbeError("daily_response_invalid")
    if raw_page.page.continuation_available and raw_page.page.oldest_date is None:
        raise KisPaperDailyUniverseProbeError("daily_response_invalid")


def _page_fact(
    raw_page: KisPaperDailyRawPage,
    *,
    page_number: int,
) -> KisPaperDailyUniverseProbePage:
    return KisPaperDailyUniverseProbePage(
        page_number=page_number,
        row_count=raw_page.page.row_count,
        newest_date=raw_page.page.newest_date,
        oldest_date=raw_page.page.oldest_date,
        continuation_advertised=raw_page.page.continuation_available,
    )


def _merge_daily_rows(
    existing: Mapping[str, KisPaperDailyRawRow],
    incoming: tuple[KisPaperDailyRawRow, ...],
) -> tuple[dict[str, KisPaperDailyRawRow], int]:
    merged = dict(existing)
    duplicate_rows_removed = 0
    for row in incoming:
        prior = merged.get(row.xymd)
        if prior is None:
            merged[row.xymd] = row
        elif prior == row:
            duplicate_rows_removed += 1
        else:
            raise KisPaperDailyUniverseProbeError("daily_duplicate_conflict")
    return merged, duplicate_rows_removed


def _write_accepted_raw_rows(
    *,
    staging: Path,
    result: KisPaperDailyUniverseProbeResult,
) -> dict[str, dict[str, object]]:
    raw_directory = staging / "raw"
    documents: dict[str, dict[str, object]] = {}
    for target in result.target_results:
        if target.classification != "accepted":
            continue
        raw_directory.mkdir(exist_ok=True)
        file_name = f"{target.symbol.lower()}-{target.exchange.lower()}-ohlcv-daily.csv.gz"
        raw_path = raw_directory / file_name
        raw_payload = _compressed_raw_daily_csv(
            target.rows,
            symbol=target.symbol,
            exchange=target.exchange,
        )
        _validate_compressed_raw_daily_csv(
            raw_payload,
            expected_rows=target.rows,
            symbol=target.symbol,
            exchange=target.exchange,
        )
        _write_bytes_and_sync(raw_path, raw_payload)
        documents[target.target_key] = {
            "path": f"raw/{file_name}",
            "sha256": "sha256:" + hashlib.sha256(raw_payload).hexdigest(),
            "size_bytes": len(raw_payload),
            "format": "csv.gz",
            "ordering": "session_date_ascending",
            "columns": [
                "symbol",
                "exchange",
                "session_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        }
    return documents


def _registry_daily_symbol_exchanges(
    registry: OfficialSymbolDirectoryNasProbeRegistry,
) -> Mapping[str, frozenset[str]]:
    if not isinstance(registry, OfficialSymbolDirectoryNasProbeRegistry):
        raise TypeError("daily universe probe requires an official NAS registry")
    if (
        registry.prospective_only is not True
        or registry.historical_point_in_time_eligible is not False
        or registry.source_manifest_sha256
        != OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256
        or tuple(target.symbol for target in registry.targets) != NAS_COMMON_STOCK_PROBE_SYMBOLS
        or registry.target_keys
        != tuple(f"{symbol}/{NAS_EXCHANGE}" for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS)
        or not registry.registry_payload
        or not _is_sha256(registry.registry_sha256)
        or not _is_sha256(registry.source_manifest_sha256)
        or not _is_sha256(registry.source_file_sha256)
        or registry.source_file_size_bytes < 1
    ):
        raise ValueError("daily universe probe registry is invalid")
    scope: dict[str, frozenset[str]] = {}
    for target in registry.targets:
        if (
            not isinstance(target, NasProbeTarget)
            or target.exchange != NAS_EXCHANGE
            or not target.symbol.isascii()
            or not target.symbol.isalnum()
            or target.symbol != target.symbol.upper()
            or target.symbol in scope
        ):
            raise ValueError("daily universe probe registry targets are invalid")
        scope[target.symbol] = frozenset({target.exchange})
    return MappingProxyType(scope)


def _validated_result(result: KisPaperDailyUniverseProbeResult) -> KisPaperDailyUniverseProbeResult:
    if not isinstance(result, KisPaperDailyUniverseProbeResult):
        raise TypeError("daily universe probe cache requires a typed result")
    return KisPaperDailyUniverseProbeResult(
        observed_at=result.observed_at,
        anchor_date=result.anchor_date,
        code_revision=result.code_revision,
        registry=result.registry,
        target_results=result.target_results,
        call_counts=result.call_counts,
        recovery=result.recovery,
    )


def _validated_call_counts(value: KisPaperMarketDataCallCounts) -> KisPaperMarketDataCallCounts:
    if (
        not isinstance(value, KisPaperMarketDataCallCounts)
        or value.token_attempts < 0
        or value.minute_page_attempts < 0
        or value.daily_page_attempts < 0
    ):
        raise ValueError("daily universe probe client call counts are invalid")
    return value


def _call_count_delta(
    *,
    initial: KisPaperMarketDataCallCounts,
    final: KisPaperMarketDataCallCounts,
) -> KisPaperMarketDataCallCounts:
    delta = KisPaperMarketDataCallCounts(
        token_attempts=final.token_attempts - initial.token_attempts,
        minute_page_attempts=final.minute_page_attempts - initial.minute_page_attempts,
        daily_page_attempts=final.daily_page_attempts - initial.daily_page_attempts,
    )
    return _validated_call_counts(delta)


def _combined_recovery(
    targets: list[KisPaperDailyUniverseProbeTargetResult],
) -> Literal["complete", "resume", "restart"]:
    if any(target.recovery == "resume" for target in targets):
        return "resume"
    if any(target.recovery == "restart" for target in targets):
        return "restart"
    return "complete"


def _safe_failure_reason(error: BaseException) -> str:
    reason = str(error)
    return reason if reason in _SAFE_FAILURE_REASONS else "unexpected_daily_probe_error"


def _valid_anchor_date(value: str) -> str:
    normalized = value.strip()
    if len(normalized) != 8 or not normalized.isdigit():
        raise ValueError("daily universe probe anchor date is invalid")
    return normalized


def _valid_run_id(value: str) -> None:
    if not value or any(character not in "0123456789TZ-" for character in value):
        raise ValueError("daily universe probe run id is invalid")


def _validated_storage_roots(*, cache_root: Path, artifact_root: Path) -> tuple[Path, Path]:
    cache = _probe_cache_root(cache_root=cache_root)
    artifact = _evidence_root(artifact_root=artifact_root)
    if _path_contains(cache, artifact) or _path_contains(artifact, cache):
        raise ValueError("daily universe probe raw cache and evidence roots must be separate")
    return cache, artifact


def _probe_cache_root(*, cache_root: Path) -> Path:
    return _external_cache_root(cache_root=Path(cache_root), repo_root=_REPOSITORY_ROOT)


def _evidence_root(*, artifact_root: Path) -> Path:
    return _external_cache_root(cache_root=Path(artifact_root), repo_root=_REPOSITORY_ROOT)


def _snapshot_directory(*, cache_root: Path, run_id: str) -> Path:
    _valid_run_id(run_id)
    return cache_root / f"snapshot={run_id}-daily-universe-probe-v1"


def _evidence_directory(*, artifact_root: Path, run_id: str) -> Path:
    _valid_run_id(run_id)
    return artifact_root / f"run={run_id}"


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _format_utc(value: datetime) -> str:
    return require_utc(value, "value").isoformat().replace("+00:00", "Z")


def _iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) != 8 or not value.isdigit():
        raise ValueError("daily universe probe date is invalid")
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"

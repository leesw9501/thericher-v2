"""Source-safe readiness evidence for a future Norgate broad-panel holdout.

The local Norgate client is used only to collect completed D1 session dates in
memory. Raw rows and prices never enter the receipt. A short calendar tail is a
fast, terminal input limitation for the *next* broad campaign, not a hold on
other Data, Research, or Execution work.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.norgate_trial_development_panel import (
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_COMMON_SESSION_COUNT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_END,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SELECTED_SYMBOL_COUNT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_START,
)

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_NORGATE_TRIAL_TAIL_READINESS_ROOT = (
    DEFAULT_MODEL_ARTIFACT_ROOT / "data" / "norgate-trial-tail-readiness-v1"
)
DEFAULT_NORGATE_ACTIVE_DATABASE_ROOT_CANDIDATES = (
    Path("D:/market_data/us_equities/norgate_us_platinum_trial"),
    Path(r"C:\ProgramData\Norgate Data"),
)
NORGATE_TRIAL_TAIL_READINESS_ID = "norgate-trial-tail-readiness-v1"
NORGATE_US_DATABASE_NAME = "US Equities"
NORGATE_TAIL_REFERENCE_SYMBOLS = ("SPY", "QQQ", "IWM")
NORGATE_TAIL_REQUESTED_START = FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_END + timedelta(days=1)
NORGATE_TAIL_MINIMUM_COMMON_SESSIONS = 126
NORGATE_ACTIVE_DATABASE_ROOT_TOLERANCE_SECONDS = 300
_ACTIVE_DATABASE_CORE_FILE = "core_us.ngdb"
_PRECOMMIT_FILE = "precommit.json"
_SUMMARY_FILE = "summary.json"
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_VALID_STATUSES = {"ready", "input_unavailable"}


class NorgateTrialTailReadinessError(ValueError):
    """Raised when the bounded source-safe readiness contract is invalid."""


class NorgateLocalDatabaseConfigurationError(NorgateTrialTailReadinessError):
    """Raised when the local Norgate API has no usable US database catalog entry."""

    _VALID_REASONS = {
        "no_configured_databases",
        "us_equities_database_not_configured",
    }

    def __init__(self, reason: str) -> None:
        if reason not in self._VALID_REASONS:
            raise ValueError("Norgate database configuration reason is invalid")
        self.reason = reason
        super().__init__("Norgate local US database configuration is unavailable")


@dataclass(frozen=True, slots=True)
class NorgateTailReferenceObservation:
    """In-memory D1 calendar evidence from the official local client."""

    package_version: str
    source_update_at_utc: datetime
    requested_start: date
    requested_end: date
    sessions_by_symbol: Mapping[str, Sequence[date]] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.package_version, str) or not self.package_version:
            raise NorgateTrialTailReadinessError("Norgate package version is invalid")
        if self.requested_end < self.requested_start:
            raise NorgateTrialTailReadinessError("Norgate tail window is invalid")
        object.__setattr__(self, "source_update_at_utc", _utc_datetime(self.source_update_at_utc))
        normalized: dict[str, tuple[date, ...]] = {}
        if set(self.sessions_by_symbol) != set(NORGATE_TAIL_REFERENCE_SYMBOLS):
            raise NorgateTrialTailReadinessError("Norgate tail reference symbols are invalid")
        for symbol in NORGATE_TAIL_REFERENCE_SYMBOLS:
            raw_sessions = self.sessions_by_symbol[symbol]
            sessions = tuple(raw_sessions)
            previous: date | None = None
            for session in sessions:
                if (
                    not isinstance(session, date)
                    or isinstance(session, datetime)
                    or session < self.requested_start
                    or session > self.requested_end
                    or (previous is not None and session <= previous)
                ):
                    raise NorgateTrialTailReadinessError("Norgate tail sessions are invalid")
                previous = session
            normalized[symbol] = sessions
        object.__setattr__(self, "sessions_by_symbol", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class NorgateTrialTailReadinessResult:
    """Verified aggregate-only readiness receipt."""

    receipt_dir: Path
    receipt_hash: str
    precommit_hash: str
    status: str
    reason: str
    active_database_root: Path
    database_build_metadata_sha256: str
    source_update_at_utc: datetime
    requested_start: date
    requested_end: date
    calendar_day_upper_bound: int
    common_session_count: int
    per_symbol_session_counts: Mapping[str, int]

    def safe_payload(self) -> dict[str, object]:
        """Return the source-safe result suitable for logs and stateboards."""

        return {
            "receipt_dir": str(self.receipt_dir),
            "receipt_hash": self.receipt_hash,
            "precommit_hash": self.precommit_hash,
            "status": self.status,
            "reason": self.reason,
            "active_database_root": str(self.active_database_root),
            "database_build_metadata_sha256": self.database_build_metadata_sha256,
            "source_update_at_utc": _format_utc(self.source_update_at_utc),
            "requested_window": {
                "start": self.requested_start.isoformat(),
                "end": self.requested_end.isoformat(),
            },
            "calendar_day_upper_bound": self.calendar_day_upper_bound,
            "minimum_common_sessions": NORGATE_TAIL_MINIMUM_COMMON_SESSIONS,
            "common_session_count": self.common_session_count,
            "per_symbol_session_counts": dict(self.per_symbol_session_counts),
        }


ClientLoader = Callable[[], Any]


def default_norgate_trial_tail_readiness_dir(run_label: str) -> Path:
    """Return the immutable external receipt directory for one bounded run."""

    label = _safe_run_label(run_label)
    return DEFAULT_NORGATE_TRIAL_TAIL_READINESS_ROOT / f"tail-{label}"


def collect_norgate_tail_reference_observation(
    *,
    requested_end: date,
    client_loader: ClientLoader | None = None,
    requested_start: date = NORGATE_TAIL_REQUESTED_START,
) -> NorgateTailReferenceObservation:
    """Read only D1 session dates from the local Norgate interface in memory."""

    if requested_end < requested_start:
        raise NorgateTrialTailReadinessError("Norgate tail window is invalid")
    client = _load_client(client_loader)
    _assert_norgate_us_database_is_configured(client)
    try:
        source_update = client.last_database_update_time(NORGATE_US_DATABASE_NAME)
    except Exception as exc:
        raise NorgateTrialTailReadinessError("Norgate update metadata is unavailable") from exc
    sessions_by_symbol: dict[str, tuple[date, ...]] = {}
    for symbol in NORGATE_TAIL_REFERENCE_SYMBOLS:
        try:
            response = client.price_timeseries(
                symbol,
                stock_price_adjustment_setting=client.StockPriceAdjustmentType.NONE,
                padding_setting=client.PaddingType.NONE,
                start_date=requested_start.isoformat(),
                end_date=requested_end.isoformat(),
                limit=-1,
                timeseriesformat="numpy-recarray",
                interval="D",
            )
        except Exception as exc:
            raise NorgateTrialTailReadinessError("Norgate tail source call is unavailable") from exc
        sessions_by_symbol[symbol] = _session_dates(
            response,
            requested_start=requested_start,
            requested_end=requested_end,
        )
    return NorgateTailReferenceObservation(
        package_version=_package_version(client),
        source_update_at_utc=_utc_datetime(source_update),
        requested_start=requested_start,
        requested_end=requested_end,
        sessions_by_symbol=sessions_by_symbol,
    )


def resolve_active_norgate_us_database_root(
    source_update_at_utc: datetime,
    *,
    candidates: Sequence[Path] = DEFAULT_NORGATE_ACTIVE_DATABASE_ROOT_CANDIDATES,
    tolerance_seconds: int = NORGATE_ACTIVE_DATABASE_ROOT_TOLERANCE_SECONDS,
) -> Path:
    """Resolve one local database root whose US core timestamp matches the service."""

    source_update = _utc_datetime(source_update_at_utc)
    if tolerance_seconds < 0:
        raise ValueError("Norgate root timestamp tolerance is invalid")
    matches: list[Path] = []
    for candidate in candidates:
        root = Path(candidate)
        core = root / _ACTIVE_DATABASE_CORE_FILE
        if root.is_symlink() or core.is_symlink() or not root.is_dir() or not core.is_file():
            continue
        try:
            resolved_root = root.resolve(strict=True)
            core_timestamp = datetime.fromtimestamp(core.stat().st_mtime, UTC)
        except OSError:
            continue
        if abs((core_timestamp - source_update).total_seconds()) <= tolerance_seconds:
            matches.append(resolved_root)
    if len(matches) != 1:
        raise NorgateTrialTailReadinessError("active Norgate US database root is unresolved")
    return matches[0]


def build_norgate_trial_tail_readiness_receipt(
    *,
    destination: Path,
    observation: NorgateTailReferenceObservation,
    active_database_root: Path,
    database_build_metadata_sha256: str,
    retrieved_at_utc: datetime,
    artifact_root: Path = DEFAULT_NORGATE_TRIAL_TAIL_READINESS_ROOT,
    repo_root: Path | None = None,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTrialTailReadinessResult:
    """Persist one source-safe tail readiness receipt outside the repository."""

    target, root = _validate_destination(
        destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    _validate_storage(root, disk_usage=disk_usage)
    active_root = _validate_active_database_root(active_database_root)
    database_hash = _sha256_value(database_build_metadata_sha256, "database build metadata hash")
    retrieved_at = _utc_datetime(retrieved_at_utc)
    common_sessions = _common_sessions(observation.sessions_by_symbol)
    calendar_day_upper_bound = (observation.requested_end - observation.requested_start).days + 1
    status, reason = _classify_tail(
        calendar_day_upper_bound=calendar_day_upper_bound,
        common_session_count=len(common_sessions),
    )
    precommit = _precommit_document(
        target=target,
        observation=observation,
        active_database_root=active_root,
        database_build_metadata_sha256=database_hash,
        retrieved_at=retrieved_at,
    )
    precommit_bytes = _json_bytes(precommit)
    summary = _summary_document(
        precommit_hash=_sha256(precommit_bytes),
        observation=observation,
        calendar_day_upper_bound=calendar_day_upper_bound,
        common_sessions=common_sessions,
        status=status,
        reason=reason,
    )
    staging = root / f".{target.name}.staging-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        (staging / _PRECOMMIT_FILE).write_bytes(precommit_bytes)
        (staging / _SUMMARY_FILE).write_bytes(_json_bytes(summary))
        os.rename(staging, target)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return verify_norgate_trial_tail_readiness_receipt(
        target,
        artifact_root=root,
        repo_root=repo_root,
    )


def verify_norgate_trial_tail_readiness_receipt(
    receipt_dir: Path,
    *,
    artifact_root: Path = DEFAULT_NORGATE_TRIAL_TAIL_READINESS_ROOT,
    repo_root: Path | None = None,
) -> NorgateTrialTailReadinessResult:
    """Reattach one receipt without importing Norgate or reading raw rows."""

    directory, _root = _validate_existing_receipt_dir(
        receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    if {entry.name for entry in directory.iterdir()} != {_PRECOMMIT_FILE, _SUMMARY_FILE}:
        raise NorgateTrialTailReadinessError("Norgate tail receipt files are invalid")
    precommit_bytes = _read_regular_file(directory / _PRECOMMIT_FILE)
    summary_bytes = _read_regular_file(directory / _SUMMARY_FILE)
    precommit = _json_object(precommit_bytes, "precommit")
    summary = _json_object(summary_bytes, "summary")
    return _result_from_documents(
        directory,
        precommit=precommit,
        precommit_hash=_sha256(precommit_bytes),
        summary=summary,
        receipt_hash=_sha256(summary_bytes),
    )


def _load_client(client_loader: ClientLoader | None) -> Any:
    try:
        if client_loader is None:
            import importlib

            client = importlib.import_module("norgatedata")
        else:
            client = client_loader()
        _ = client.PaddingType.NONE
        _ = client.StockPriceAdjustmentType.NONE
        _ = client.databases
        _ = client.last_database_update_time
        _ = client.price_timeseries
    except Exception as exc:
        raise NorgateTrialTailReadinessError("Norgate local client is unavailable") from exc
    return client


def _assert_norgate_us_database_is_configured(client: Any) -> None:
    """Reject an empty or mismatched local catalog before reading date metadata."""

    try:
        configured = tuple(client.databases())
    except Exception as exc:
        raise NorgateTrialTailReadinessError("Norgate database catalog is unavailable") from exc
    if not all(isinstance(name, str) and name for name in configured):
        raise NorgateTrialTailReadinessError("Norgate database catalog is invalid")
    if not configured:
        raise NorgateLocalDatabaseConfigurationError("no_configured_databases")
    if NORGATE_US_DATABASE_NAME not in configured:
        raise NorgateLocalDatabaseConfigurationError("us_equities_database_not_configured")


def _session_dates(
    response: Any,
    *,
    requested_start: date,
    requested_end: date,
) -> tuple[date, ...]:
    fields = tuple(getattr(getattr(response, "dtype", None), "names", ()) or ())
    if "Date" not in fields:
        raise NorgateTrialTailReadinessError("Norgate tail date field is unavailable")
    try:
        rows = tuple(response)
    except TypeError as exc:
        raise NorgateTrialTailReadinessError("Norgate tail source series is unreadable") from exc
    sessions: list[date] = []
    previous: date | None = None
    for row in rows:
        session = _session_date(_row_value(row, "Date"))
        if (
            session < requested_start
            or session > requested_end
            or (previous is not None and session <= previous)
        ):
            raise NorgateTrialTailReadinessError("Norgate tail source sessions are invalid")
        sessions.append(session)
        previous = session
    return tuple(sessions)


def _common_sessions(sessions_by_symbol: Mapping[str, Sequence[date]]) -> tuple[date, ...]:
    common: set[date] | None = None
    for symbol in NORGATE_TAIL_REFERENCE_SYMBOLS:
        symbol_sessions = set(sessions_by_symbol[symbol])
        common = symbol_sessions if common is None else common & symbol_sessions
    return tuple(sorted(common or ()))


def _classify_tail(*, calendar_day_upper_bound: int, common_session_count: int) -> tuple[str, str]:
    if calendar_day_upper_bound < NORGATE_TAIL_MINIMUM_COMMON_SESSIONS:
        return "input_unavailable", "calendar_interval_below_predeclared_minimum"
    if common_session_count < NORGATE_TAIL_MINIMUM_COMMON_SESSIONS:
        return "input_unavailable", "source_reference_tail_below_predeclared_minimum"
    return "ready", "tail_minimum_attested"


def _precommit_document(
    *,
    target: Path,
    observation: NorgateTailReferenceObservation,
    active_database_root: Path,
    database_build_metadata_sha256: str,
    retrieved_at: datetime,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": NORGATE_TRIAL_TAIL_READINESS_ID,
        "receipt_dir": str(target),
        "retrieved_at_utc": _format_utc(retrieved_at),
        "active_database": {
            "provider": "norgatedata",
            "access": "local_windows_host_only",
            "root": str(active_database_root),
            "database_name": NORGATE_US_DATABASE_NAME,
            "database_build_metadata_sha256": database_build_metadata_sha256,
            "source_update_at_utc": _format_utc(observation.source_update_at_utc),
            "package_version": observation.package_version,
        },
        "frozen_panel": {
            "dataset_hash": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
            "selected_symbol_count": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SELECTED_SYMBOL_COUNT,
            "common_session_count": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_COMMON_SESSION_COUNT,
            "start": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_START.isoformat(),
            "end": FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_END.isoformat(),
        },
        "tail_contract": {
            "reference_symbols": list(NORGATE_TAIL_REFERENCE_SYMBOLS),
            "requested_start": observation.requested_start.isoformat(),
            "requested_end": observation.requested_end.isoformat(),
            "minimum_common_sessions": NORGATE_TAIL_MINIMUM_COMMON_SESSIONS,
            "calendar_maximum_is_kill_test": True,
            "raw_rows_retained": False,
            "model_training_allowed": False,
        },
    }


def _summary_document(
    *,
    precommit_hash: str,
    observation: NorgateTailReferenceObservation,
    calendar_day_upper_bound: int,
    common_sessions: tuple[date, ...],
    status: str,
    reason: str,
) -> dict[str, object]:
    per_symbol_counts = {
        symbol: len(observation.sessions_by_symbol[symbol])
        for symbol in NORGATE_TAIL_REFERENCE_SYMBOLS
    }
    return {
        "receipt_id": NORGATE_TRIAL_TAIL_READINESS_ID,
        "precommit_sha256": precommit_hash,
        "status": status,
        "reason": reason,
        "reference_tail": {
            "per_symbol_session_counts": per_symbol_counts,
            "common_session_count": len(common_sessions),
            "common_start": common_sessions[0].isoformat() if common_sessions else None,
            "common_end": common_sessions[-1].isoformat() if common_sessions else None,
            "calendar_day_upper_bound": calendar_day_upper_bound,
            "minimum_common_sessions": NORGATE_TAIL_MINIMUM_COMMON_SESSIONS,
            "shortfall_sessions": max(
                0, NORGATE_TAIL_MINIMUM_COMMON_SESSIONS - len(common_sessions)
            ),
        },
        "rebuild_performed": False,
        "membership_verification_performed": False,
        "per_symbol_tail_availability_performed": False,
        "model_training_allowed": False,
        "gpu_appointment_allowed": False,
        "paper_input_allowed": False,
        "next_recovery": _next_recovery(status),
    }


def _next_recovery(status: str) -> str:
    if status == "ready":
        return "perform the separately predeclared panel reattestation before any campaign"
    return (
        "wait for a later completed local Norgate tail or use a distinct source contract; "
        "do not retune or reopen consumed broad-panel evaluation windows"
    )


def _result_from_documents(
    directory: Path,
    *,
    precommit: Mapping[str, object],
    precommit_hash: str,
    summary: Mapping[str, object],
    receipt_hash: str,
) -> NorgateTrialTailReadinessResult:
    if precommit.get("receipt_id") != NORGATE_TRIAL_TAIL_READINESS_ID:
        raise NorgateTrialTailReadinessError("Norgate tail precommit identity is invalid")
    if summary.get("receipt_id") != NORGATE_TRIAL_TAIL_READINESS_ID:
        raise NorgateTrialTailReadinessError("Norgate tail summary identity is invalid")
    if summary.get("precommit_sha256") != precommit_hash:
        raise NorgateTrialTailReadinessError("Norgate tail receipt lineage is invalid")
    active_database = _mapping(precommit.get("active_database"), "active database")
    tail_contract = _mapping(precommit.get("tail_contract"), "tail contract")
    reference_tail = _mapping(summary.get("reference_tail"), "reference tail")
    status = summary.get("status")
    reason = summary.get("reason")
    if status not in _VALID_STATUSES or not isinstance(reason, str) or not reason:
        raise NorgateTrialTailReadinessError("Norgate tail receipt status is invalid")
    if tail_contract.get("minimum_common_sessions") != NORGATE_TAIL_MINIMUM_COMMON_SESSIONS:
        raise NorgateTrialTailReadinessError("Norgate tail minimum is invalid")
    if tail_contract.get("reference_symbols") != list(NORGATE_TAIL_REFERENCE_SYMBOLS):
        raise NorgateTrialTailReadinessError("Norgate tail reference scope is invalid")
    requested_start = _date_value(tail_contract.get("requested_start"), "requested start")
    requested_end = _date_value(tail_contract.get("requested_end"), "requested end")
    if requested_start != NORGATE_TAIL_REQUESTED_START or requested_end < requested_start:
        raise NorgateTrialTailReadinessError("Norgate tail window is invalid")
    per_symbol_counts = _integer_mapping(
        reference_tail.get("per_symbol_session_counts"), "per-symbol session counts"
    )
    if set(per_symbol_counts) != set(NORGATE_TAIL_REFERENCE_SYMBOLS):
        raise NorgateTrialTailReadinessError("Norgate tail symbol counts are invalid")
    common_session_count = _nonnegative_integer(
        reference_tail.get("common_session_count"), "common session count"
    )
    calendar_day_upper_bound = _nonnegative_integer(
        reference_tail.get("calendar_day_upper_bound"), "calendar day upper bound"
    )
    if calendar_day_upper_bound != (requested_end - requested_start).days + 1:
        raise NorgateTrialTailReadinessError("Norgate tail calendar upper bound is invalid")
    expected_status, expected_reason = _classify_tail(
        calendar_day_upper_bound=calendar_day_upper_bound,
        common_session_count=common_session_count,
    )
    if (status, reason) != (expected_status, expected_reason):
        raise NorgateTrialTailReadinessError("Norgate tail classification is invalid")
    active_root = Path(_nonempty_text(active_database.get("root"), "active database root"))
    build_hash = _sha256_value(
        active_database.get("database_build_metadata_sha256"), "database build metadata hash"
    )
    source_update = _datetime_value(
        active_database.get("source_update_at_utc"), "source update timestamp"
    )
    return NorgateTrialTailReadinessResult(
        receipt_dir=directory,
        receipt_hash=receipt_hash,
        precommit_hash=precommit_hash,
        status=status,
        reason=reason,
        active_database_root=active_root,
        database_build_metadata_sha256=build_hash,
        source_update_at_utc=source_update,
        requested_start=requested_start,
        requested_end=requested_end,
        calendar_day_upper_bound=calendar_day_upper_bound,
        common_session_count=common_session_count,
        per_symbol_session_counts=MappingProxyType(dict(per_symbol_counts)),
    )


def _validate_destination(
    destination: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    resolved_root = _ensure_artifact_root(artifact_root, repo_root=repo_root)
    target = Path(destination).resolve(strict=False)
    if target.parent != resolved_root or target.name != _safe_run_label(target.name):
        raise NorgateTrialTailReadinessError("Norgate tail receipt destination is invalid")
    _validate_external_root(resolved_root, repo_root=repo_root)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Norgate tail receipt destination already exists")
    return target, resolved_root


def _validate_existing_receipt_dir(
    receipt_dir: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(artifact_root)
    if root.is_symlink() or not root.is_dir():
        raise NorgateTrialTailReadinessError("Norgate tail artifact root is unavailable")
    resolved_root = root.resolve(strict=True)
    directory = Path(receipt_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise NorgateTrialTailReadinessError("Norgate tail receipt is unavailable")
    resolved_directory = directory.resolve(strict=True)
    if resolved_directory.parent != resolved_root:
        raise NorgateTrialTailReadinessError("Norgate tail receipt must stay under artifact root")
    _validate_external_root(resolved_root, repo_root=repo_root)
    return resolved_directory, resolved_root


def _ensure_artifact_root(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise NorgateTrialTailReadinessError("Norgate tail artifact root is unavailable")
    proposed_root = root.resolve(strict=False)
    _validate_external_root(proposed_root, repo_root=repo_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise NorgateTrialTailReadinessError("Norgate tail artifact root is unavailable") from exc
    if root.is_symlink() or not resolved_root.is_dir():
        raise NorgateTrialTailReadinessError("Norgate tail artifact root is unavailable")
    return resolved_root


def _validate_external_root(root: Path, *, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    repository = Path(repo_root).resolve(strict=True)
    if (
        root == repository or root.is_relative_to(repository)
    ) and not _is_container_external_artifact_root(root, repository):
        raise NorgateTrialTailReadinessError(
            "Norgate tail receipt must stay outside the Git workspace"
        )


def _is_container_external_artifact_root(root: Path, repository: Path) -> bool:
    container_repository = Path("/app").resolve()
    return repository == container_repository and (
        root == container_repository / "model_artifacts"
        or root.is_relative_to(container_repository / "model_artifacts")
    )


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> None:
    usage = disk_usage(root)
    total = getattr(usage, "total", 0)
    free = getattr(usage, "free", 0)
    if (
        not isinstance(total, int)
        or not isinstance(free, int)
        or total <= 0
        or free * 100 < total * 15
    ):
        raise NorgateTrialTailReadinessError("Norgate tail artifact storage is unavailable")


def _validate_active_database_root(root: Path) -> Path:
    candidate = Path(root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise NorgateTrialTailReadinessError("active Norgate database root is unavailable")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise NorgateTrialTailReadinessError("active Norgate database root is unavailable") from exc


def _package_version(client: Any) -> str:
    value = getattr(client, "__version__", None)
    if not isinstance(value, str) or not value:
        raise NorgateTrialTailReadinessError("Norgate package version is unavailable")
    return value


def _row_value(row: Any, field: str) -> Any:
    try:
        return row[field]
    except (KeyError, TypeError, IndexError) as exc:
        raise NorgateTrialTailReadinessError("Norgate tail source row is invalid") from exc


def _session_date(value: Any) -> date:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise NorgateTrialTailReadinessError("Norgate tail source date is invalid") from exc
    raise NorgateTrialTailReadinessError("Norgate tail source date is invalid")


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise NorgateTrialTailReadinessError("Norgate tail receipt file is invalid")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise NorgateTrialTailReadinessError("Norgate tail receipt file is unavailable") from exc


def _json_object(value: bytes, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid") from exc
    if not isinstance(parsed, dict):
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    return parsed


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    return value


def _integer_mapping(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    result: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
        result[key] = _nonnegative_integer(item, label)
    return result


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    return value


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid") from exc


def _datetime_value(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid") from exc
    return _utc_datetime(parsed)


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise NorgateTrialTailReadinessError("Norgate timestamp is invalid")
    return value.astimezone(UTC)


def _sha256_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise NorgateTrialTailReadinessError(f"Norgate {label} is invalid")
    return value


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NorgateTrialTailReadinessError(f"Norgate tail {label} is invalid")
    return value


def _safe_run_label(value: str) -> str:
    if not isinstance(value, str) or _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise NorgateTrialTailReadinessError("Norgate tail run label is invalid")
    return value


def _format_utc(value: datetime) -> str:
    return _utc_datetime(value).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Mapping[str, object]) -> bytes:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return (serialized + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

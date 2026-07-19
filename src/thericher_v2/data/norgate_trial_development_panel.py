"""Bounded host-only Norgate raw-D1 development-panel evidence."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import uuid
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_membership import (
    NorgateMembershipSnapshotResult,
    load_verified_norgate_sp500_membership_scope,
)
from thericher_v2.data.norgate_trial_raw_d1 import (
    NorgateTrialRawD1Result,
    load_verified_norgate_trial_raw_d1_session_scope,
)

DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_NORGATE_TRIAL_DEVELOPMENT_PANEL_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "norgate_trial_broad_development_panel"
    / "canonical"
    / "ohlcv_1d"
)
NORGATE_TRIAL_DEVELOPMENT_PANEL_VERSION = "norgate-trial-broad-d1-panel-r1"
DEFAULT_MINIMUM_SELECTED_SYMBOLS = 100
_SNAPSHOT_SUFFIX = "-norgate-trial-broad-d1-panel-r1"
_DATA_FILE = "panel_ohlcv_1d.csv.gz"
_AVAILABILITY_FILE = "candidate_availability.csv"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_DATA_COLUMNS = ("candidate_rank", "symbol", "date", "open", "high", "low", "close", "volume")
_AVAILABILITY_COLUMNS = ("candidate_rank", "symbol", "status", "returned_row_count")
_STATUSES = ("selected", "session_mismatch", "invalid", "unavailable")
_LIMITATIONS = (
    "The candidate union is date-less and is used only to bound retrieval scope.",
    "Sparse membership rows are not used as positive or negative selection evidence.",
    "Static full-session selection is survivorship and availability selection.",
    "NONE is a requested query setting, not proof of adjustment semantics.",
    "This panel is not PIT, ranking, holdout, paper, source preference, or profit evidence.",
)


class NorgateTrialDevelopmentPanelError(RuntimeError):
    """Raised when a bounded development-panel snapshot cannot be retained."""


@dataclass(frozen=True, slots=True)
class NorgateTrialDevelopmentPanelResult:
    """Non-secret aggregate result for one retained panel snapshot."""

    snapshot_dir: Path
    membership_snapshot_dir: Path
    calendar_snapshot_dir: Path
    dataset_hash: str
    manifest_hash: str
    candidate_count: int
    selected_symbol_count: int
    unavailable_count: int
    session_mismatch_count: int
    invalid_count: int
    common_session_count: int
    actual_start: date
    actual_end: date
    development_training_eligible: bool
    norgate_package_version: str
    free_percent: float


@dataclass(frozen=True, slots=True)
class _CandidateAvailability:
    candidate_rank: int
    symbol: str
    status: str
    returned_row_count: int


BarLoader = Callable[[str, date, date], Sequence[Bar]]


def default_norgate_trial_development_panel_snapshot_dir(retrieval_date: date) -> Path:
    """Return the external immutable destination for one panel snapshot."""

    if isinstance(retrieval_date, datetime):
        raise ValueError("Norgate development-panel retrieval date must not include a time")
    return DEFAULT_NORGATE_TRIAL_DEVELOPMENT_PANEL_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def build_norgate_trial_development_panel_snapshot(
    *,
    destination: Path,
    membership_snapshot: Path,
    calendar_snapshot: Path,
    retrieved_at_utc: datetime,
    load_bars: BarLoader,
    norgate_package_version: str,
    minimum_selected_symbols: int = DEFAULT_MINIMUM_SELECTED_SYMBOLS,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTrialDevelopmentPanelResult:
    """Retain exact-session raw bars while recording all candidate outcomes."""

    if platform_name != "win32":
        raise NorgateTrialDevelopmentPanelError("Norgate development panel requires Windows")
    retrieved_at = _utc_datetime(retrieved_at_utc, "Norgate development-panel retrieval time")
    minimum = _positive_int(minimum_selected_symbols, "minimum selected symbols")
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    package_version = _nonempty_text(norgate_package_version, "Norgate package version")
    membership, candidates = load_verified_norgate_sp500_membership_scope(
        membership_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    calendar, common_sessions = load_verified_norgate_trial_raw_d1_session_scope(
        calendar_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    availability, selected_rows = _collect_panel_rows(
        candidates,
        common_sessions=common_sessions,
        load_bars=load_bars,
    )
    selected_count = sum(item.status == "selected" for item in availability)
    eligible = selected_count >= minimum
    data_bytes = _gzip_bytes(_data_csv_bytes(selected_rows, candidates=candidates))
    availability_bytes = _availability_csv_bytes(availability)
    retention_bytes = _retention_marker_bytes()
    manifest = _manifest(
        destination=target,
        market_data_root=root,
        membership=membership,
        calendar=calendar,
        common_sessions=common_sessions,
        availability=availability,
        data_hash=_sha256(data_bytes),
        data_size=len(data_bytes),
        availability_hash=_sha256(availability_bytes),
        availability_size=len(availability_bytes),
        retention_hash=_sha256(retention_bytes),
        retention_size=len(retention_bytes),
        minimum_selected_symbols=minimum,
        development_training_eligible=eligible,
        retrieved_at_utc=retrieved_at,
        norgate_package_version=package_version,
        free_percent=free_percent,
    )
    manifest_bytes = _json_bytes(manifest)
    staging = _create_staging_directory(target)
    try:
        (staging / _DATA_FILE).write_bytes(data_bytes)
        (staging / _AVAILABILITY_FILE).write_bytes(availability_bytes)
        (staging / _RETENTION_FILE).write_bytes(retention_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        _validate_snapshot_contents(
            staging,
            manifest,
            membership=membership,
            candidates=candidates,
            calendar=calendar,
            common_sessions=common_sessions,
            market_data_root=market_data_root,
        )
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    try:
        return verify_norgate_trial_development_panel_snapshot(
            target,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
    except Exception as exc:
        _quarantine_failed_snapshot(target)
        raise NorgateTrialDevelopmentPanelError(
            "Norgate development-panel verification failed; external evidence was retained"
        ) from exc


def verify_norgate_trial_development_panel_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateTrialDevelopmentPanelResult:
    """Re-attest a panel snapshot without Norgate, network, or token access."""

    snapshot = _validate_existing_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    manifest_bytes = _read_file(snapshot, _MANIFEST_FILE, "manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate development-panel manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Norgate development-panel manifest is invalid")
    _validate_manifest_header(manifest, snapshot=snapshot)
    membership_document = _mapping(manifest.get("membership_parent"), "membership parent")
    calendar_document = _mapping(manifest.get("calendar_parent"), "calendar parent")
    membership, candidates = load_verified_norgate_sp500_membership_scope(
        _rebase_market_data_snapshot(
            membership_document.get("snapshot_dir"),
            market_data_root=market_data_root,
            label="membership snapshot",
        ),
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    calendar, common_sessions = load_verified_norgate_trial_raw_d1_session_scope(
        _rebase_market_data_snapshot(
            calendar_document.get("snapshot_dir"),
            market_data_root=market_data_root,
            label="calendar snapshot",
        ),
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    details = _validate_snapshot_contents(
        snapshot,
        manifest,
        membership=membership,
        candidates=candidates,
        calendar=calendar,
        common_sessions=common_sessions,
        market_data_root=market_data_root,
    )
    return NorgateTrialDevelopmentPanelResult(
        snapshot_dir=snapshot,
        membership_snapshot_dir=membership.snapshot_dir,
        calendar_snapshot_dir=calendar.snapshot_dir,
        dataset_hash=details["dataset_hash"],
        manifest_hash=_sha256(manifest_bytes),
        candidate_count=len(candidates),
        selected_symbol_count=details["selected_symbol_count"],
        unavailable_count=details["unavailable_count"],
        session_mismatch_count=details["session_mismatch_count"],
        invalid_count=details["invalid_count"],
        common_session_count=len(common_sessions),
        actual_start=common_sessions[0],
        actual_end=common_sessions[-1],
        development_training_eligible=details["development_training_eligible"],
        norgate_package_version=details["norgate_package_version"],
        free_percent=details["free_percent"],
    )


def _collect_panel_rows(
    candidates: tuple[str, ...],
    *,
    common_sessions: tuple[date, ...],
    load_bars: BarLoader,
) -> tuple[tuple[_CandidateAvailability, ...], tuple[Bar, ...]]:
    availability: list[_CandidateAvailability] = []
    selected_rows: list[Bar] = []
    for candidate_rank, symbol in enumerate(candidates, start=1):
        try:
            source_bars = tuple(load_bars(symbol, common_sessions[0], common_sessions[-1]))
        except Exception:
            availability.append(
                _CandidateAvailability(candidate_rank, symbol, "unavailable", 0)
            )
            continue
        try:
            bars = _validated_candidate_bars(source_bars, symbol=symbol)
        except Exception:
            availability.append(
                _CandidateAvailability(candidate_rank, symbol, "invalid", len(source_bars))
            )
            continue
        if tuple(bar.start_ts.date() for bar in bars) != common_sessions:
            availability.append(
                _CandidateAvailability(candidate_rank, symbol, "session_mismatch", len(bars))
            )
            continue
        availability.append(_CandidateAvailability(candidate_rank, symbol, "selected", len(bars)))
        selected_rows.extend(bars)
    return tuple(availability), tuple(selected_rows)


def _validated_candidate_bars(bars: Sequence[Bar], *, symbol: str) -> tuple[Bar, ...]:
    validated: list[Bar] = []
    previous: date | None = None
    for bar in bars:
        if (
            bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe != Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo != UTC
            or any(
                (
                    bar.start_ts.hour,
                    bar.start_ts.minute,
                    bar.start_ts.second,
                    bar.start_ts.microsecond,
                )
            )
        ):
            raise ValueError("Norgate development-panel bar contract is invalid")
        session_date = bar.start_ts.date()
        if previous is not None and session_date <= previous:
            raise ValueError("Norgate development-panel response must be strictly ordered")
        validated.append(bar)
        previous = session_date
    return tuple(validated)


def _manifest(
    *,
    destination: Path,
    market_data_root: Path,
    membership: NorgateMembershipSnapshotResult,
    calendar: NorgateTrialRawD1Result,
    common_sessions: tuple[date, ...],
    availability: tuple[_CandidateAvailability, ...],
    data_hash: str,
    data_size: int,
    availability_hash: str,
    availability_size: int,
    retention_hash: str,
    retention_size: int,
    minimum_selected_symbols: int,
    development_training_eligible: bool,
    retrieved_at_utc: datetime,
    norgate_package_version: str,
    free_percent: float,
) -> dict[str, Any]:
    counts = _availability_counts(availability)
    return {
        "schema_version": 1,
        "kind": "norgate_trial_broad_development_panel",
        "snapshot_version": NORGATE_TRIAL_DEVELOPMENT_PANEL_VERSION,
        "dataset_id": _dataset_id(destination),
        "dataset_hash": data_hash,
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "membership_parent": _membership_document(membership),
        "calendar_parent": _calendar_document(calendar, common_sessions=common_sessions),
        "norgate_source_contract": {
            "provider": "Norgate Data",
            "query_method": "price_timeseries",
            "interval": "D",
            "requested_stock_price_adjustment_setting": "NONE",
            "adjustment_semantics_verified": False,
            "padding_setting": "NONE",
            "timeseriesformat": "numpy-recarray",
            "fields": ["Date", "Open", "High", "Low", "Close", "Volume"],
        },
        "norgate_package": {"name": "norgatedata", "version": norgate_package_version},
        "static_panel_contract": {
            "selection_rule": "exact_parent_common_session_sequence_only",
            "minimum_selected_symbols": minimum_selected_symbols,
            "threshold_is_not_coverage_or_quality_proof": True,
            "candidate_union_scope_only": True,
            "membership_values_used_for_selection": False,
            "candidate_count": len(availability),
            "selected_symbol_count": counts["selected"],
            "unavailable_count": counts["unavailable"],
            "session_mismatch_count": counts["session_mismatch"],
            "invalid_count": counts["invalid"],
            "common_session_count": len(common_sessions),
            "actual_common_window": {
                "start": common_sessions[0].isoformat(),
                "end": common_sessions[-1].isoformat(),
            },
        },
        "files": {
            "panel_ohlcv": {
                "path": _DATA_FILE,
                "sha256": data_hash,
                "size_bytes": data_size,
                "format": "csv.gz",
                "columns": list(_DATA_COLUMNS),
            },
            "candidate_availability": {
                "path": _AVAILABILITY_FILE,
                "sha256": availability_hash,
                "size_bytes": availability_size,
                "format": "csv",
                "columns": list(_AVAILABILITY_COLUMNS),
            },
            "retention_marker": {
                "path": _RETENTION_FILE,
                "sha256": retention_hash,
                "size_bytes": retention_size,
            },
        },
        "storage": {
            "root": str(market_data_root),
            "free_percent": free_percent,
            "warning_floor_percent": 20,
            "hard_floor_percent": 15,
        },
        "retention": {
            "norgate_origin_data": True,
            "operator_action_required_on_lapse": True,
            "automated_deletion": False,
            "marker_file": _RETENTION_FILE,
        },
        "scope": _scope(development_training_eligible),
        "limitations": list(_LIMITATIONS),
    }


def _membership_document(value: NorgateMembershipSnapshotResult) -> dict[str, Any]:
    return {
        "snapshot_dir": str(value.snapshot_dir),
        "dataset_id": value.dataset_id,
        "dataset_hash": value.dataset_hash,
        "manifest_hash": value.manifest_hash,
        "candidate_count": value.candidate_count,
        "membership_row_count": value.membership_row_count,
    }


def _calendar_document(
    value: NorgateTrialRawD1Result,
    *,
    common_sessions: tuple[date, ...],
) -> dict[str, Any]:
    return {
        "snapshot_dir": str(value.snapshot_dir),
        "dataset_id": value.dataset_id,
        "dataset_hash": value.dataset_hash,
        "manifest_hash": value.manifest_hash,
        "common_session_count": len(common_sessions),
        "actual_common_window": {
            "start": common_sessions[0].isoformat(),
            "end": common_sessions[-1].isoformat(),
        },
    }


def _scope(development_training_eligible: bool) -> dict[str, bool]:
    return {
        "development_panel_attested": True,
        "development_training_eligible": development_training_eligible,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
        "campaign_eligible": False,
        "model_eligible": False,
        "gpu_eligible": False,
        "paper_trading_eligible": False,
    }


def _validate_manifest_header(manifest: dict[str, Any], *, snapshot: Path) -> None:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "norgate_trial_broad_development_panel"
        or manifest.get("snapshot_version") != NORGATE_TRIAL_DEVELOPMENT_PANEL_VERSION
        or manifest.get("dataset_id") != _dataset_id(snapshot)
        or manifest.get("immutable_snapshot") is not True
    ):
        raise ValueError("Norgate development-panel manifest identity is invalid")
    if manifest.get("norgate_source_contract") != {
        "provider": "Norgate Data",
        "query_method": "price_timeseries",
        "interval": "D",
        "requested_stock_price_adjustment_setting": "NONE",
        "adjustment_semantics_verified": False,
        "padding_setting": "NONE",
        "timeseriesformat": "numpy-recarray",
        "fields": ["Date", "Open", "High", "Low", "Close", "Volume"],
    }:
        raise ValueError("Norgate development-panel source contract is invalid")
    _utc_datetime(_datetime_value(manifest.get("retrieved_at_utc")), "retrieved_at_utc")
    package = _mapping(manifest.get("norgate_package"), "package")
    if package.get("name") != "norgatedata":
        raise ValueError("Norgate development-panel package identity is invalid")
    _nonempty_text(package.get("version"), "Norgate package version")
    _validate_storage_document(manifest.get("storage"))
    _validate_retention_document(manifest.get("retention"))


def _validate_snapshot_contents(
    snapshot: Path,
    manifest: dict[str, Any],
    *,
    membership: NorgateMembershipSnapshotResult,
    candidates: tuple[str, ...],
    calendar: NorgateTrialRawD1Result,
    common_sessions: tuple[date, ...],
    market_data_root: Path,
) -> dict[str, Any]:
    _validate_parent_documents(
        manifest,
        membership=membership,
        calendar=calendar,
        common_sessions=common_sessions,
        market_data_root=market_data_root,
    )
    files = _mapping(manifest.get("files"), "files")
    data_document = _mapping(files.get("panel_ohlcv"), "panel data metadata")
    data = _read_verified_file(
        snapshot,
        data_document,
        expected_name=_DATA_FILE,
        label="panel data",
    )
    dataset_hash = _required_sha256(data_document.get("sha256"), "panel data hash")
    if manifest.get("dataset_hash") != dataset_hash:
        raise ValueError("Norgate development-panel dataset hash is inconsistent")
    availability_data = _read_verified_file(
        snapshot,
        files.get("candidate_availability"),
        expected_name=_AVAILABILITY_FILE,
        label="candidate availability",
    )
    retention_data = _read_verified_file(
        snapshot,
        files.get("retention_marker"),
        expected_name=_RETENTION_FILE,
        label="retention marker",
    )
    if retention_data != _retention_marker_bytes():
        raise ValueError("Norgate development-panel retention marker is invalid")
    availability = _parse_availability_rows(availability_data)
    _validate_availability_rows(availability, candidates=candidates)
    selected_rows = _parse_data_rows(data)
    selected_count = _validate_selected_rows(
        selected_rows,
        availability=availability,
        candidates=candidates,
        common_sessions=common_sessions,
    )
    counts = _availability_counts(availability)
    contract = _mapping(manifest.get("static_panel_contract"), "static panel contract")
    minimum = _positive_int(contract.get("minimum_selected_symbols"), "minimum selected symbols")
    eligible = selected_count >= minimum
    if contract != {
        "selection_rule": "exact_parent_common_session_sequence_only",
        "minimum_selected_symbols": minimum,
        "threshold_is_not_coverage_or_quality_proof": True,
        "candidate_union_scope_only": True,
        "membership_values_used_for_selection": False,
        "candidate_count": len(candidates),
        "selected_symbol_count": counts["selected"],
        "unavailable_count": counts["unavailable"],
        "session_mismatch_count": counts["session_mismatch"],
        "invalid_count": counts["invalid"],
        "common_session_count": len(common_sessions),
        "actual_common_window": {
            "start": common_sessions[0].isoformat(),
            "end": common_sessions[-1].isoformat(),
        },
    }:
        raise ValueError("Norgate development-panel static contract is invalid")
    if manifest.get("scope") != _scope(eligible):
        raise ValueError("Norgate development-panel scope is invalid")
    if manifest.get("limitations") != list(_LIMITATIONS):
        raise ValueError("Norgate development-panel limitations are invalid")
    package = _mapping(manifest.get("norgate_package"), "package")
    storage = _mapping(manifest.get("storage"), "storage")
    return {
        "dataset_hash": dataset_hash,
        "selected_symbol_count": selected_count,
        "unavailable_count": counts["unavailable"],
        "session_mismatch_count": counts["session_mismatch"],
        "invalid_count": counts["invalid"],
        "development_training_eligible": eligible,
        "norgate_package_version": _nonempty_text(package.get("version"), "package version"),
        "free_percent": _nonnegative_float(storage.get("free_percent"), "free percent"),
    }


def _validate_parent_documents(
    manifest: dict[str, Any],
    *,
    membership: NorgateMembershipSnapshotResult,
    calendar: NorgateTrialRawD1Result,
    common_sessions: tuple[date, ...],
    market_data_root: Path,
) -> None:
    membership_document = _mapping(manifest.get("membership_parent"), "membership parent")
    calendar_document = _mapping(manifest.get("calendar_parent"), "calendar parent")
    if not _parent_document_matches(
        membership_document,
        _membership_document(membership),
        market_data_root=market_data_root,
        label="membership snapshot",
    ):
        raise ValueError("Norgate development-panel membership parent is invalid")
    if not _parent_document_matches(
        calendar_document,
        _calendar_document(calendar, common_sessions=common_sessions),
        market_data_root=market_data_root,
        label="calendar snapshot",
    ):
        raise ValueError("Norgate development-panel calendar parent is invalid")


def _parent_document_matches(
    declared: dict[str, Any],
    expected: dict[str, Any],
    *,
    market_data_root: Path,
    label: str,
) -> bool:
    declared_copy = dict(declared)
    expected_copy = dict(expected)
    declared_path = declared_copy.pop("snapshot_dir", None)
    expected_path = expected_copy.pop("snapshot_dir", None)
    if declared_copy != expected_copy or not isinstance(expected_path, str):
        return False
    try:
        rebased = _rebase_market_data_snapshot(
            declared_path,
            market_data_root=market_data_root,
            label=label,
        )
    except ValueError:
        return False
    return rebased == Path(expected_path).resolve()


def _rebase_market_data_snapshot(
    value: object,
    *,
    market_data_root: Path,
    label: str,
) -> Path:
    raw = _nonempty_text(value, label)
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate development-panel market-data root is invalid")
    root = root.resolve()
    declared = Path(raw)
    if declared.is_dir() and not declared.is_symlink():
        resolved = declared.resolve()
        if resolved != root and root in resolved.parents:
            return resolved

    parts = tuple(part for part in raw.replace("\\", "/").split("/") if part)
    root_name = root.name.casefold()
    anchors = [index for index, part in enumerate(parts) if part.casefold() == root_name]
    if not anchors:
        raise ValueError("Norgate development-panel parent snapshot root is invalid")
    relative_parts = parts[anchors[-1] + 1 :]
    if (
        not relative_parts
        or any(
            part in {".", ".."} or any(character in part for character in ("\\", ":"))
            for part in relative_parts
        )
    ):
        raise ValueError("Norgate development-panel parent snapshot path is invalid")
    rebased = root.joinpath(*relative_parts).resolve()
    if rebased == root or root not in rebased.parents:
        raise ValueError("Norgate development-panel parent snapshot escapes market data")
    return rebased


def _availability_counts(availability: Sequence[_CandidateAvailability]) -> dict[str, int]:
    return {status: sum(item.status == status for item in availability) for status in _STATUSES}


def _data_csv_bytes(rows: tuple[Bar, ...], *, candidates: tuple[str, ...]) -> bytes:
    ranks = {symbol: index for index, symbol in enumerate(candidates, start=1)}
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_DATA_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for bar in rows:
        writer.writerow(
            {
                "candidate_rank": ranks[bar.symbol],
                "symbol": bar.symbol,
                "date": bar.start_ts.date().isoformat(),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _availability_csv_bytes(availability: tuple[_CandidateAvailability, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_AVAILABILITY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in availability:
        writer.writerow(
            {
                "candidate_rank": item.candidate_rank,
                "symbol": item.symbol,
                "status": item.status,
                "returned_row_count": item.returned_row_count,
            }
        )
    return buffer.getvalue().encode("utf-8")


def _retention_marker_bytes() -> bytes:
    return (
        "This directory contains Norgate-origin trial raw-D1 panel data.\n"
        "If the trial or subscription ends and the Norgate EULA requires deletion,\n"
        "the operator must delete this snapshot directory and derived copies.\n"
        "This static panel is survivorship and availability selected. It is not a\n"
        "PIT universe, ranking, holdout, paper-trading, source-preference, or\n"
        "profitability input. NONE is a requested query parameter, not verified\n"
        "adjustment semantics. This marker records scope only and does not perform\n"
        "or prove deletion. It does not authorize deletion of C:\\ProgramData\\Norgate Data.\n"
    ).encode("ascii")


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _parse_availability_rows(data: bytes) -> tuple[_CandidateAvailability, ...]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
        fieldnames = tuple(reader.fieldnames or ())
        source_rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate development-panel availability CSV is invalid") from exc
    if fieldnames != _AVAILABILITY_COLUMNS:
        raise ValueError("Norgate development-panel availability CSV schema is invalid")
    rows: list[_CandidateAvailability] = []
    for source_row in source_rows:
        rows.append(
            _CandidateAvailability(
                candidate_rank=_positive_int(source_row.get("candidate_rank"), "candidate rank"),
                symbol=_symbol(source_row.get("symbol")),
                status=_status(source_row.get("status")),
                returned_row_count=_nonnegative_int(
                    source_row.get("returned_row_count"), "returned row count"
                ),
            )
        )
    return tuple(rows)


def _parse_data_rows(data: bytes) -> tuple[tuple[int, Bar], ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as compressed:
            reader = csv.DictReader(io.TextIOWrapper(compressed, encoding="utf-8", newline=""))
            fieldnames = tuple(reader.fieldnames or ())
            source_rows = tuple(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate development-panel data is invalid") from exc
    if fieldnames != _DATA_COLUMNS:
        raise ValueError("Norgate development-panel data CSV schema is invalid")
    rows: list[tuple[int, Bar]] = []
    previous_rank = 0
    previous_date: date | None = None
    for source_row in source_rows:
        rank = _positive_int(source_row.get("candidate_rank"), "candidate rank")
        symbol = _symbol(source_row.get("symbol"))
        session_date = _date_value(source_row.get("date"), "session date")
        if rank < previous_rank or (
            rank == previous_rank and previous_date is not None and session_date <= previous_date
        ):
            raise ValueError("Norgate development-panel data CSV ordering is invalid")
        if rank != previous_rank:
            previous_date = None
        rows.append(
            (
                rank,
                Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=datetime.combine(session_date, datetime.min.time(), UTC),
                    open=_decimal(source_row.get("open"), "open"),
                    high=_decimal(source_row.get("high"), "high"),
                    low=_decimal(source_row.get("low"), "low"),
                    close=_decimal(source_row.get("close"), "close"),
                    volume=_decimal(source_row.get("volume"), "volume"),
                ),
            )
        )
        previous_rank = rank
        previous_date = session_date
    return tuple(rows)


def _validate_availability_rows(
    availability: tuple[_CandidateAvailability, ...],
    *,
    candidates: tuple[str, ...],
) -> None:
    if len(availability) != len(candidates):
        raise ValueError("Norgate development-panel availability count is invalid")
    pairs = zip(availability, candidates, strict=True)
    for expected_rank, (item, symbol) in enumerate(pairs, start=1):
        if item.candidate_rank != expected_rank or item.symbol != symbol:
            raise ValueError("Norgate development-panel availability ordering is invalid")
        if item.status == "selected" and item.returned_row_count <= 0:
            raise ValueError("Norgate development-panel selected count is invalid")
        if item.status == "unavailable" and item.returned_row_count != 0:
            raise ValueError("Norgate development-panel unavailable count is invalid")


def _validate_selected_rows(
    rows: tuple[tuple[int, Bar], ...],
    *,
    availability: tuple[_CandidateAvailability, ...],
    candidates: tuple[str, ...],
    common_sessions: tuple[date, ...],
) -> int:
    by_rank: dict[int, list[Bar]] = {}
    for rank, bar in rows:
        by_rank.setdefault(rank, []).append(bar)
    selected = [item for item in availability if item.status == "selected"]
    if set(by_rank) != {item.candidate_rank for item in selected}:
        raise ValueError("Norgate development-panel selected symbols are inconsistent")
    for item in selected:
        bars = tuple(by_rank[item.candidate_rank])
        if (
            item.symbol != candidates[item.candidate_rank - 1]
            or any(bar.symbol != item.symbol for bar in bars)
            or len(bars) != item.returned_row_count
            or tuple(bar.start_ts.date() for bar in bars) != common_sessions
        ):
            raise ValueError("Norgate development-panel selected rows are inconsistent")
    if len(rows) != len(selected) * len(common_sessions):
        raise ValueError("Norgate development-panel row count is inconsistent")
    return len(selected)


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate development-panel market-data root must exist")
    root = root.resolve()
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate development-panel market-data root must stay outside Git")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Norgate development-panel destination already exists")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Norgate development-panel destination must stay under market data")
    if repo_root is not None and target.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate development-panel destination must stay outside Git")
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Norgate development-panel destination name is invalid")
    if target.parent.is_dir() and any(target.parent.glob(".stage-*")):
        raise FileExistsError("Norgate development-panel staging residue requires recovery")
    return target, root


def _validate_existing_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> Path:
    root = Path(market_data_root).resolve()
    snapshot = Path(snapshot_dir)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("Norgate development-panel snapshot must be a directory")
    snapshot = snapshot.resolve()
    if not snapshot.is_relative_to(root):
        raise ValueError("Norgate development-panel snapshot must stay under market data")
    if (
        repo_root is not None
        and snapshot.is_relative_to(Path(repo_root).resolve())
        and not root.is_mount()
    ):
        raise ValueError("Norgate development-panel snapshot must stay outside Git")
    if not snapshot.name.startswith("snapshot=") or not snapshot.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Norgate development-panel snapshot name is invalid")
    return snapshot


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Norgate development-panel storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Norgate development-panel storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn("Norgate development-panel storage is below the warning floor", stacklevel=2)
    return free_percent


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".stage-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _quarantine_failed_snapshot(destination: Path) -> Path:
    quarantined = destination.parent / f".rejected-{destination.name}-{uuid.uuid4().hex}"
    try:
        os.rename(destination, quarantined)
    except OSError:
        return destination
    return quarantined


def _read_file(snapshot: Path, filename: str, label: str) -> bytes:
    path = snapshot / filename
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(snapshot):
        raise ValueError(f"Norgate development-panel {label} path is invalid")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Norgate development-panel {label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"Norgate development-panel {label} must be a regular file")
    return resolved.read_bytes()


def _read_verified_file(
    snapshot: Path,
    metadata: object,
    *,
    expected_name: str,
    label: str,
) -> bytes:
    if not isinstance(metadata, dict) or metadata.get("path") != expected_name:
        raise ValueError(f"Norgate development-panel {label} metadata is invalid")
    data = _read_file(snapshot, expected_name, label)
    if _sha256(data) != _required_sha256(metadata.get("sha256"), f"{label} hash"):
        raise ValueError(f"Norgate development-panel {label} hash mismatch")
    if metadata.get("size_bytes") != len(data):
        raise ValueError(f"Norgate development-panel {label} size is inconsistent")
    return data


def _validate_storage_document(value: object) -> None:
    storage = _mapping(value, "storage")
    if (
        _nonnegative_float(storage.get("free_percent"), "free percent") < 15
        or storage.get("warning_floor_percent") != 20
        or storage.get("hard_floor_percent") != 15
        or not isinstance(storage.get("root"), str)
    ):
        raise ValueError("Norgate development-panel storage evidence is invalid")


def _validate_retention_document(value: object) -> None:
    if value != {
        "norgate_origin_data": True,
        "operator_action_required_on_lapse": True,
        "automated_deletion": False,
        "marker_file": _RETENTION_FILE,
    }:
        raise ValueError("Norgate development-panel retention evidence is invalid")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Norgate development-panel {label} is invalid")
    return value


def _status(value: object) -> str:
    result = _nonempty_text(value, "candidate status")
    if result not in _STATUSES:
        raise ValueError("Norgate development-panel candidate status is invalid")
    return result


def _symbol(value: object) -> str:
    result = _nonempty_text(value, "symbol").upper()
    if result != result.strip():
        raise ValueError("Norgate development-panel symbol is invalid")
    return result


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Norgate development-panel {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Norgate development-panel {label} is invalid") from exc


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Norgate development-panel {label} is invalid") from exc
    if not result.is_finite():
        raise ValueError(f"Norgate development-panel {label} is invalid")
    return result


def _positive_int(value: object, label: str) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Norgate development-panel {label} is invalid") from exc
    if isinstance(value, bool) or result <= 0 or str(result) != str(value):
        raise ValueError(f"Norgate development-panel {label} is invalid")
    return result


def _nonnegative_int(value: object, label: str) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Norgate development-panel {label} is invalid") from exc
    if isinstance(value, bool) or result < 0 or str(result) != str(value):
        raise ValueError(f"Norgate development-panel {label} is invalid")
    return result


def _nonnegative_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Norgate development-panel {label} is invalid")
    return float(value)


def _nonempty_text(value: object, label: str) -> str:
    result = str(value or "")
    if not result or result != result.strip():
        raise ValueError(f"Norgate development-panel {label} is required")
    return result


def _datetime_value(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Norgate development-panel datetime is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Norgate development-panel datetime is invalid") from exc


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"Norgate development-panel {label} must be UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _required_sha256(value: object, label: str) -> str:
    result = _nonempty_text(value, label)
    if len(result) != 71 or not result.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in result[7:]
    ):
        raise ValueError(f"Norgate development-panel {label} is invalid")
    return result


def _dataset_id(snapshot_dir: Path) -> str:
    return f"us_equities.norgate_trial_broad_development_panel.1d.{Path(snapshot_dir).name}"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

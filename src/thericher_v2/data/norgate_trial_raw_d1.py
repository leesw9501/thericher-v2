"""Immutable, host-only Norgate trial raw-D1 evidence for fixed ETFs."""

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

FIXED_NORGATE_TRIAL_SYMBOLS = ("SPY", "QQQ", "IWM")
DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_NORGATE_TRIAL_RAW_D1_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_daily"
    / "canonical"
    / "norgate_trial_raw_d1"
)
NORGATE_TRIAL_RAW_D1_VERSION = "norgate-trial-raw-d1-r2"
_SNAPSHOT_SUFFIX = "-norgate-trial-raw-d1-r2"
DEFAULT_NORGATE_TRIAL_DIVIDEND_EXCLUSION_ROOT = (
    DEFAULT_NORGATE_TRIAL_RAW_D1_ROOT / "dividend_marker_exclusions"
)
NORGATE_TRIAL_DIVIDEND_EXCLUSION_VERSION = "norgate-trial-raw-d1-r3-dividend-exclusions-r1"
_DIVIDEND_SNAPSHOT_SUFFIX = "-norgate-trial-raw-d1-r3-dividend-exclusions-r1"
_DATA_FILE = "norgate_ohlcv_1d.csv.gz"
_EVENT_FILE = "capital_event_exclusions.csv"
_DIVIDEND_FILE = "dividend_marker_exclusions.csv"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_DATA_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")
_EVENT_COLUMNS = ("symbol", "event_marker_date", "excluded_session_date")
_DIVIDEND_COLUMNS = ("symbol", "source_marker_date", "excluded_session_date")
_SOURCE_FIELDS = ("Date", "Open", "High", "Low", "Close", "Volume")
_SCOPE = {
    "development_source_attested": True,
    "development_training_eligible": False,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "model_eligible": False,
    "gpu_eligible": False,
    "paper_trading_eligible": False,
}
_DIVIDEND_SCOPE = {
    "parent_raw_d1_attested": True,
    "development_training_eligible": False,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "model_eligible": False,
    "gpu_eligible": False,
    "paper_trading_eligible": False,
}


class NorgateTrialRawD1Error(RuntimeError):
    """Raised when one bounded Norgate trial snapshot cannot be retained."""


class NorgateCapitalEventUnavailableError(NorgateTrialRawD1Error):
    """Raised when the local Norgate capital-event evidence cannot be read."""


@dataclass(frozen=True, slots=True)
class NorgateCapitalEventEvidence:
    """Aggregate event-query facts plus in-window nonzero marker dates."""

    returned_row_count: int
    returned_start: date | None
    returned_end: date | None
    clipped_session_count: int
    marker_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class NorgateDividendMarkerEvidence:
    """Source-returned marker dates without dividend-value retention."""

    returned_row_count: int
    session_dates: tuple[date, ...]
    marker_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class NorgateTrialRawD1Result:
    """Non-secret result from a completed fixed-ETF Norgate trial snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    row_count: int
    common_session_count: int
    event_marker_count: int
    excluded_session_count: int
    actual_start: date
    actual_end: date
    norgate_package_version: str
    free_percent: float


@dataclass(frozen=True, slots=True)
class NorgateTrialDividendExclusionResult:
    """Non-secret result from a retained exclusion-only source sidecar."""

    snapshot_dir: Path
    parent_snapshot_dir: Path
    parent_dataset_hash: str
    parent_manifest_hash: str
    manifest_hash: str
    marker_count: int
    excluded_session_count: int
    common_session_count: int
    actual_start: date
    actual_end: date
    norgate_package_version: str
    free_percent: float


@dataclass(frozen=True, slots=True)
class _EventExclusion:
    symbol: str
    event_marker_date: date
    excluded_session_date: date


@dataclass(frozen=True, slots=True)
class _DividendExclusion:
    symbol: str
    source_marker_date: date
    excluded_session_date: date


BarLoader = Callable[[str, date, date], Sequence[Bar]]
EventLoader = Callable[[str, date, date], NorgateCapitalEventEvidence]
DividendLoader = Callable[[str, date, date], NorgateDividendMarkerEvidence]
ClientLoader = Callable[[], Any]


def default_norgate_trial_raw_d1_snapshot_dir(retrieval_date: date) -> Path:
    """Return the external immutable destination for this snapshot revision."""

    if isinstance(retrieval_date, datetime):
        raise ValueError("Norgate trial raw-D1 retrieval date must not include a time")
    return DEFAULT_NORGATE_TRIAL_RAW_D1_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def default_norgate_trial_dividend_exclusion_snapshot_dir(retrieval_date: date) -> Path:
    """Return the external immutable destination for the exclusion sidecar."""

    if isinstance(retrieval_date, datetime):
        raise ValueError("Norgate dividend exclusion retrieval date must not include a time")
    return DEFAULT_NORGATE_TRIAL_DIVIDEND_EXCLUSION_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_DIVIDEND_SNAPSHOT_SUFFIX}"
    )


def load_norgate_capital_event_evidence(
    symbol: str,
    requested_start: date,
    requested_end: date,
    *,
    client_loader: ClientLoader | None = None,
) -> NorgateCapitalEventEvidence:
    """Read one local event series and explicitly clip any padded response."""

    _validate_window(requested_start, requested_end)
    client = _load_norgatedata(client_loader)
    normalized_symbol = _symbol(symbol)
    try:
        response = client.capital_event_timeseries(
            normalized_symbol,
            start_date=requested_start.isoformat(),
            end_date=requested_end.isoformat(),
            limit=-1,
            timeseriesformat="numpy-recarray",
        )
    except Exception as exc:
        raise NorgateCapitalEventUnavailableError(
            "Norgate capital-event data is unavailable"
        ) from exc
    fields = tuple(getattr(getattr(response, "dtype", None), "names", ()) or ())
    if "Date" not in fields or "Capital Event" not in fields:
        raise ValueError("Norgate capital-event response is missing required fields")
    returned_dates: list[date] = []
    marker_dates: list[date] = []
    previous: date | None = None
    for row in response:
        session_date = _session_date(_row_value(row, "Date"))
        if previous is not None and session_date <= previous:
            raise ValueError("Norgate capital-event response must be strictly ordered")
        returned_dates.append(session_date)
        if requested_start <= session_date <= requested_end and _event_flag(
            _row_value(row, "Capital Event")
        ):
            marker_dates.append(session_date)
        previous = session_date
    if not returned_dates:
        raise ValueError("Norgate capital-event response is empty")
    return NorgateCapitalEventEvidence(
        returned_row_count=len(returned_dates),
        returned_start=returned_dates[0],
        returned_end=returned_dates[-1],
        clipped_session_count=sum(
            requested_start <= session_date <= requested_end for session_date in returned_dates
        ),
        marker_dates=tuple(marker_dates),
    )


def load_norgate_dividend_marker_evidence(
    symbol: str,
    requested_start: date,
    requested_end: date,
    *,
    client_loader: ClientLoader | None = None,
) -> NorgateDividendMarkerEvidence:
    """Read source markers without retaining dividend amounts or raw price rows."""

    _validate_window(requested_start, requested_end)
    client = _load_norgatedata(client_loader)
    normalized_symbol = _symbol(symbol)
    try:
        response = client.price_timeseries(
            normalized_symbol,
            stock_price_adjustment_setting=client.StockPriceAdjustmentType.NONE,
            padding_setting=client.PaddingType.NONE,
            start_date=requested_start.isoformat(),
            end_date=requested_end.isoformat(),
            timeseriesformat="numpy-recarray",
            interval="D",
        )
    except Exception as exc:
        raise NorgateTrialRawD1Error("Norgate dividend-marker data is unavailable") from exc
    fields = tuple(getattr(getattr(response, "dtype", None), "names", ()) or ())
    if "Date" not in fields or "Dividend" not in fields:
        raise ValueError("Norgate dividend-marker response is missing required fields")
    session_dates: list[date] = []
    marker_dates: list[date] = []
    previous: date | None = None
    for row in response:
        session_date = _session_date(_row_value(row, "Date"))
        if previous is not None and session_date <= previous:
            raise ValueError("Norgate dividend-marker response must be strictly ordered")
        session_dates.append(session_date)
        if _event_flag(_row_value(row, "Dividend")):
            marker_dates.append(session_date)
        previous = session_date
    if not session_dates:
        raise ValueError("Norgate dividend-marker response is empty")
    return NorgateDividendMarkerEvidence(
        returned_row_count=len(session_dates),
        session_dates=tuple(session_dates),
        marker_dates=tuple(marker_dates),
    )


def build_norgate_trial_raw_d1_snapshot(
    *,
    destination: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    norgate_bars: BarLoader,
    capital_event_evidence: EventLoader,
    norgate_package_version: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTrialRawD1Result:
    """Retain one verified, raw/no-adjustment fixed-ETF trial snapshot."""

    _validate_window(requested_start, requested_end)
    if platform_name != "win32":
        raise NorgateTrialRawD1Error("Norgate trial raw-D1 snapshot requires Windows")
    if Path(destination).exists() or Path(destination).is_symlink():
        return verify_norgate_trial_raw_d1_snapshot(
            destination,
            market_data_root=market_data_root,
            repo_root=repo_root,
            expected_requested_start=requested_start,
            expected_requested_end=requested_end,
        )
    retrieved_at = _utc_datetime(retrieved_at_utc, "Norgate trial raw-D1 retrieval time")
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    package_version = _nonempty_text(norgate_package_version, "Norgate package version")
    rows, common_sessions, event_evidence, exclusions = _collect_snapshot_evidence(
        requested_start=requested_start,
        requested_end=requested_end,
        norgate_bars=norgate_bars,
        capital_event_evidence=capital_event_evidence,
    )
    data_bytes = _gzip_bytes(_data_csv_bytes(rows))
    event_bytes = _event_csv_bytes(exclusions)
    marker_bytes = _retention_marker_bytes()
    manifest = _manifest(
        destination=target,
        market_data_root=root,
        data_hash=_sha256(data_bytes),
        data_size=len(data_bytes),
        event_hash=_sha256(event_bytes),
        event_size=len(event_bytes),
        marker_hash=_sha256(marker_bytes),
        marker_size=len(marker_bytes),
        row_count=len(rows),
        common_sessions=common_sessions,
        event_evidence=event_evidence,
        exclusions=exclusions,
        requested_start=requested_start,
        requested_end=requested_end,
        retrieved_at_utc=retrieved_at,
        norgate_package_version=package_version,
        free_percent=free_percent,
    )
    manifest_bytes = _json_bytes(manifest)
    staging = _create_staging_directory(target)
    try:
        (staging / _DATA_FILE).write_bytes(data_bytes)
        (staging / _EVENT_FILE).write_bytes(event_bytes)
        (staging / _RETENTION_FILE).write_bytes(marker_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        _validate_written_snapshot(staging, manifest)
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    try:
        return verify_norgate_trial_raw_d1_snapshot(
            target,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
    except Exception as exc:
        _quarantine_failed_snapshot(target)
        raise NorgateTrialRawD1Error(
            "Norgate trial raw-D1 verification failed; external evidence was retained"
        ) from exc


def verify_norgate_trial_raw_d1_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    expected_requested_start: date | None = None,
    expected_requested_end: date | None = None,
) -> NorgateTrialRawD1Result:
    """Re-attest one retained snapshot without client, network, or token access."""

    snapshot = _validate_existing_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
        require_snapshot_name=True,
    )
    manifest_bytes = _read_file(snapshot, _MANIFEST_FILE, "manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate trial raw-D1 manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Norgate trial raw-D1 manifest is invalid")
    _validate_manifest_header(
        manifest,
        snapshot=snapshot,
        expected_requested_start=expected_requested_start,
        expected_requested_end=expected_requested_end,
    )
    details = _validate_written_snapshot(snapshot, manifest)
    return NorgateTrialRawD1Result(
        snapshot_dir=snapshot,
        dataset_id=_dataset_id(snapshot),
        dataset_hash=details["dataset_hash"],
        manifest_hash=_sha256(manifest_bytes),
        row_count=details["row_count"],
        common_session_count=details["common_session_count"],
        event_marker_count=details["event_marker_count"],
        excluded_session_count=details["excluded_session_count"],
        actual_start=details["actual_start"],
        actual_end=details["actual_end"],
        norgate_package_version=details["norgate_package_version"],
        free_percent=details["free_percent"],
    )


def load_verified_norgate_trial_raw_d1_session_scope(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> tuple[NorgateTrialRawD1Result, tuple[date, ...]]:
    """Return a verified raw-D1 parent and its exact common-session calendar."""

    return _verified_parent_session_evidence(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def load_verified_norgate_trial_raw_d1_common_sessions(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> tuple[date, ...]:
    """Load the hash-attested common session calendar without returning prices."""

    _parent, common_sessions = load_verified_norgate_trial_raw_d1_session_scope(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return common_sessions


def build_norgate_trial_dividend_exclusion_snapshot(
    *,
    destination: Path,
    parent_snapshot: Path,
    retrieved_at_utc: datetime,
    dividend_evidence: DividendLoader,
    norgate_package_version: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTrialDividendExclusionResult:
    """Retain one exclusion-only sidecar for the verified raw-D1 parent."""

    if platform_name != "win32":
        raise NorgateTrialRawD1Error("Norgate dividend exclusion snapshot requires Windows")
    retrieved_at = _utc_datetime(retrieved_at_utc, "Norgate dividend exclusion retrieval time")
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
        snapshot_suffix=_DIVIDEND_SNAPSHOT_SUFFIX,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    package_version = _nonempty_text(norgate_package_version, "Norgate package version")
    parent, common_sessions = _verified_parent_session_evidence(
        parent_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    evidence_by_symbol = _collect_dividend_marker_evidence(
        dividend_evidence,
        common_sessions=common_sessions,
    )
    exclusions = tuple(
        exclusion
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
        for exclusion in _dividend_exclusions(
            symbol,
            marker_dates=evidence_by_symbol[symbol].marker_dates,
            common_sessions=common_sessions,
        )
    )
    exclusion_bytes = _dividend_csv_bytes(exclusions)
    marker_bytes = _dividend_retention_marker_bytes()
    manifest = _dividend_manifest(
        destination=target,
        market_data_root=root,
        parent=parent,
        common_sessions=common_sessions,
        evidence_by_symbol=evidence_by_symbol,
        exclusions=exclusions,
        exclusion_hash=_sha256(exclusion_bytes),
        exclusion_size=len(exclusion_bytes),
        marker_hash=_sha256(marker_bytes),
        marker_size=len(marker_bytes),
        retrieved_at_utc=retrieved_at,
        norgate_package_version=package_version,
        free_percent=free_percent,
    )
    manifest_bytes = _json_bytes(manifest)
    staging = _create_staging_directory(target)
    try:
        (staging / _DIVIDEND_FILE).write_bytes(exclusion_bytes)
        (staging / _RETENTION_FILE).write_bytes(marker_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        _validate_written_dividend_exclusion_snapshot(
            staging,
            manifest,
            parent=parent,
            common_sessions=common_sessions,
        )
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    try:
        return verify_norgate_trial_dividend_exclusion_snapshot(
            target,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
    except Exception as exc:
        _quarantine_failed_snapshot(target)
        raise NorgateTrialRawD1Error(
            "Norgate dividend exclusion verification failed; external evidence was retained"
        ) from exc


def verify_norgate_trial_dividend_exclusion_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateTrialDividendExclusionResult:
    """Re-attest one exclusion sidecar without client, network, or token access."""

    snapshot = _validate_existing_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
        require_snapshot_name=True,
        snapshot_suffix=_DIVIDEND_SNAPSHOT_SUFFIX,
    )
    manifest_bytes = _read_file(snapshot, _MANIFEST_FILE, "dividend exclusion manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate dividend exclusion manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Norgate dividend exclusion manifest is invalid")
    _validate_dividend_manifest_header(manifest, snapshot=snapshot)
    parent_document = _mapping(manifest.get("parent_raw_d1"), "dividend parent")
    parent_path = Path(_nonempty_text(parent_document.get("snapshot_dir"), "parent snapshot"))
    parent, common_sessions = _verified_parent_session_evidence(
        parent_path,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_dividend_parent_document(
        parent_document,
        parent=parent,
        common_sessions=common_sessions,
    )
    details = _validate_written_dividend_exclusion_snapshot(
        snapshot,
        manifest,
        parent=parent,
        common_sessions=common_sessions,
    )
    return NorgateTrialDividendExclusionResult(
        snapshot_dir=snapshot,
        parent_snapshot_dir=parent.snapshot_dir,
        parent_dataset_hash=parent.dataset_hash,
        parent_manifest_hash=parent.manifest_hash,
        manifest_hash=_sha256(manifest_bytes),
        marker_count=details["marker_count"],
        excluded_session_count=details["excluded_session_count"],
        common_session_count=len(common_sessions),
        actual_start=common_sessions[0],
        actual_end=common_sessions[-1],
        norgate_package_version=details["norgate_package_version"],
        free_percent=details["free_percent"],
    )


def _verified_parent_session_evidence(
    parent_snapshot: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[NorgateTrialRawD1Result, tuple[date, ...]]:
    parent = verify_norgate_trial_raw_d1_snapshot(
        parent_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    manifest_bytes = _read_file(parent.snapshot_dir, _MANIFEST_FILE, "parent raw-D1 manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate dividend exclusion parent manifest is invalid") from exc
    files = _mapping(_mapping(manifest, "parent manifest").get("files"), "parent files")
    data = _read_verified_file(
        parent.snapshot_dir,
        files.get("norgate_ohlcv"),
        expected_name=_DATA_FILE,
        label="parent raw-D1 data",
    )
    common_sessions = _validate_data_rows(_parse_data_rows(data), manifest)
    if (
        len(common_sessions) != parent.common_session_count
        or common_sessions[0] != parent.actual_start
        or common_sessions[-1] != parent.actual_end
    ):
        raise ValueError("Norgate dividend exclusion parent session evidence is inconsistent")
    return parent, common_sessions


def _collect_dividend_marker_evidence(
    loader: DividendLoader,
    *,
    common_sessions: tuple[date, ...],
) -> dict[str, NorgateDividendMarkerEvidence]:
    evidence: dict[str, NorgateDividendMarkerEvidence] = {}
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        evidence[symbol] = _validated_dividend_marker_evidence(
            loader(symbol, common_sessions[0], common_sessions[-1]),
            symbol=symbol,
            common_sessions=common_sessions,
        )
    return evidence


def _validated_dividend_marker_evidence(
    value: NorgateDividendMarkerEvidence,
    *,
    symbol: str,
    common_sessions: tuple[date, ...],
) -> NorgateDividendMarkerEvidence:
    if not isinstance(value, NorgateDividendMarkerEvidence):
        raise ValueError("Norgate dividend-marker evidence is invalid")
    if (
        value.returned_row_count != len(value.session_dates)
        or value.session_dates != common_sessions
        or not value.session_dates
    ):
        raise ValueError("Norgate dividend-marker sessions do not match the raw-D1 parent")
    if (
        value.marker_dates != tuple(sorted(set(value.marker_dates)))
        or any(
            not isinstance(marker, date)
            or isinstance(marker, datetime)
            or marker not in common_sessions
            for marker in value.marker_dates
        )
    ):
        raise ValueError(f"Norgate dividend markers are invalid for {symbol}")
    if not value.marker_dates:
        raise ValueError(f"Norgate dividend markers require nonzero evidence for {symbol}")
    return value


def _dividend_exclusions(
    symbol: str,
    *,
    marker_dates: tuple[date, ...],
    common_sessions: tuple[date, ...],
) -> tuple[_DividendExclusion, ...]:
    positions = {session_date: index for index, session_date in enumerate(common_sessions)}
    exclusions: list[_DividendExclusion] = []
    for marker_date in marker_dates:
        index = positions.get(marker_date)
        if index is None:
            raise ValueError("Norgate dividend marker is not a fixed-ETF session")
        for excluded_index in range(max(0, index - 1), min(len(common_sessions), index + 2)):
            exclusions.append(
                _DividendExclusion(
                    symbol=symbol,
                    source_marker_date=marker_date,
                    excluded_session_date=common_sessions[excluded_index],
                )
            )
    return tuple(exclusions)


def _dividend_manifest(
    *,
    destination: Path,
    market_data_root: Path,
    parent: NorgateTrialRawD1Result,
    common_sessions: tuple[date, ...],
    evidence_by_symbol: dict[str, NorgateDividendMarkerEvidence],
    exclusions: tuple[_DividendExclusion, ...],
    exclusion_hash: str,
    exclusion_size: int,
    marker_hash: str,
    marker_size: int,
    retrieved_at_utc: datetime,
    norgate_package_version: str,
    free_percent: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "fixed_etf_norgate_trial_raw_d1_dividend_exclusions",
        "snapshot_version": NORGATE_TRIAL_DIVIDEND_EXCLUSION_VERSION,
        "dataset_id": _dividend_dataset_id(destination),
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "symbols": list(FIXED_NORGATE_TRIAL_SYMBOLS),
        "symbol_order": list(FIXED_NORGATE_TRIAL_SYMBOLS),
        "parent_raw_d1": _dividend_parent_document(parent, common_sessions=common_sessions),
        "norgate_source_contract": {
            "provider": "Norgate Data",
            "query_method": "price_timeseries",
            "interval": "D",
            "requested_stock_price_adjustment_setting": "NONE",
            "adjustment_semantics_verified": False,
            "padding_setting": "NONE",
            "timeseriesformat": "numpy-recarray",
            "fields": ["Date", "Dividend"],
            "marker_semantics_verified": False,
        },
        "norgate_package": {"name": "norgatedata", "version": norgate_package_version},
        "source_marker_evidence": {
            "source_field": "Dividend",
            "response_exactly_matches_parent_sessions": True,
            "marker_exclusion_rule": "marker_session_plus_adjacent_observed_sessions",
            "source_marker_dates_are_not_timestamps_or_actionable_events": True,
            "all_symbols_have_nonzero_marker": True,
            "per_symbol": {
                symbol: _dividend_marker_document(evidence_by_symbol[symbol])
                for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
            },
            "observed_nonzero_marker_count": sum(
                len(value.marker_dates) for value in evidence_by_symbol.values()
            ),
            "exclusion_row_count": len(exclusions),
        },
        "files": {
            "dividend_marker_exclusions": {
                "path": _DIVIDEND_FILE,
                "sha256": exclusion_hash,
                "size_bytes": exclusion_size,
                "format": "csv",
                "columns": list(_DIVIDEND_COLUMNS),
            },
            "retention_marker": {
                "path": _RETENTION_FILE,
                "sha256": marker_hash,
                "size_bytes": marker_size,
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
        "scope": _DIVIDEND_SCOPE,
        "limitations": [
            "The source marker is exclusion evidence, not a timestamp or event classification.",
            "NONE is a recorded query setting, not a proof of adjustment semantics.",
            "The parent trial coverage is bounded and not a broad historical universe.",
            "This sidecar does not establish campaign, model, GPU, paper, or source preference.",
        ],
    }


def _dividend_parent_document(
    parent: NorgateTrialRawD1Result,
    *,
    common_sessions: tuple[date, ...],
) -> dict[str, Any]:
    return {
        "snapshot_dir": str(parent.snapshot_dir),
        "dataset_id": parent.dataset_id,
        "dataset_hash": parent.dataset_hash,
        "manifest_hash": parent.manifest_hash,
        "actual_common_window": {
            "start": common_sessions[0].isoformat(),
            "end": common_sessions[-1].isoformat(),
            "common_session_count": len(common_sessions),
        },
    }


def _dividend_marker_document(value: NorgateDividendMarkerEvidence) -> dict[str, Any]:
    return {
        "returned_row_count": value.returned_row_count,
        "nonzero_marker_count": len(value.marker_dates),
        "response_matches_parent_sessions": True,
    }


def _collect_snapshot_evidence(
    *,
    requested_start: date,
    requested_end: date,
    norgate_bars: BarLoader,
    capital_event_evidence: EventLoader,
) -> tuple[
    tuple[Bar, ...],
    tuple[date, ...],
    dict[str, NorgateCapitalEventEvidence],
    tuple[_EventExclusion, ...],
]:
    bars_by_symbol: dict[str, tuple[Bar, ...]] = {}
    dates_by_symbol: dict[str, tuple[date, ...]] = {}
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        bars = _validated_bars(
            norgate_bars(symbol, requested_start, requested_end),
            symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
        )
        if not bars:
            raise ValueError("Norgate trial raw-D1 source returned no bars")
        dates = tuple(bar.start_ts.date() for bar in bars)
        bars_by_symbol[symbol] = bars
        dates_by_symbol[symbol] = dates
    common_sessions = dates_by_symbol[FIXED_NORGATE_TRIAL_SYMBOLS[0]]
    if any(
        dates_by_symbol[symbol] != common_sessions
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS[1:]
    ):
        raise ValueError("Norgate trial raw-D1 source has uneven fixed-ETF sessions")
    evidence_by_symbol: dict[str, NorgateCapitalEventEvidence] = {}
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        evidence_by_symbol[symbol] = _validated_event_evidence(
            capital_event_evidence(symbol, requested_start, requested_end),
            symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
            expected_session_count=len(common_sessions),
        )
    rows = tuple(bar for symbol in FIXED_NORGATE_TRIAL_SYMBOLS for bar in bars_by_symbol[symbol])
    exclusions = tuple(
        exclusion
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
        for exclusion in _event_exclusions(
            symbol,
            marker_dates=evidence_by_symbol[symbol].marker_dates,
            common_sessions=common_sessions,
        )
    )
    return rows, common_sessions, evidence_by_symbol, exclusions


def _validated_bars(
    bars: Sequence[Bar],
    *,
    symbol: str,
    requested_start: date,
    requested_end: date,
) -> tuple[Bar, ...]:
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
            raise ValueError("Norgate trial raw-D1 bar contract is invalid")
        session_date = bar.start_ts.date()
        if session_date < requested_start or session_date > requested_end:
            raise ValueError("Norgate trial raw-D1 response is outside the requested window")
        if previous is not None and session_date <= previous:
            raise ValueError("Norgate trial raw-D1 response must be strictly ordered")
        validated.append(bar)
        previous = session_date
    return tuple(validated)


def _validated_event_evidence(
    value: NorgateCapitalEventEvidence,
    *,
    symbol: str,
    requested_start: date,
    requested_end: date,
    expected_session_count: int,
) -> NorgateCapitalEventEvidence:
    if not isinstance(value, NorgateCapitalEventEvidence):
        raise ValueError("Norgate capital-event evidence is invalid")
    if value.returned_row_count < value.clipped_session_count or value.returned_row_count <= 0:
        raise ValueError("Norgate capital-event returned row count is invalid")
    if (
        value.returned_start is None
        or value.returned_end is None
        or value.returned_end < value.returned_start
    ):
        raise ValueError("Norgate capital-event returned range is invalid")
    if value.clipped_session_count != expected_session_count:
        raise ValueError("Norgate capital-event coverage does not match raw-D1 sessions")
    if (
        value.marker_dates != tuple(sorted(set(value.marker_dates)))
        or any(
            not isinstance(marker, date)
            or isinstance(marker, datetime)
            or marker < requested_start
            or marker > requested_end
            for marker in value.marker_dates
        )
    ):
        raise ValueError(f"Norgate capital-event markers are invalid for {symbol}")
    return value


def _event_exclusions(
    symbol: str,
    *,
    marker_dates: tuple[date, ...],
    common_sessions: tuple[date, ...],
) -> tuple[_EventExclusion, ...]:
    positions = {session_date: index for index, session_date in enumerate(common_sessions)}
    exclusions: list[_EventExclusion] = []
    for marker_date in marker_dates:
        index = positions.get(marker_date)
        if index is None:
            raise ValueError("Norgate capital-event marker is not a fixed-ETF session")
        for excluded_index in range(max(0, index - 1), min(len(common_sessions), index + 2)):
            exclusions.append(
                _EventExclusion(
                    symbol=symbol,
                    event_marker_date=marker_date,
                    excluded_session_date=common_sessions[excluded_index],
                )
            )
    return tuple(exclusions)


def _manifest(
    *,
    destination: Path,
    market_data_root: Path,
    data_hash: str,
    data_size: int,
    event_hash: str,
    event_size: int,
    marker_hash: str,
    marker_size: int,
    row_count: int,
    common_sessions: tuple[date, ...],
    event_evidence: dict[str, NorgateCapitalEventEvidence],
    exclusions: tuple[_EventExclusion, ...],
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    norgate_package_version: str,
    free_percent: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "fixed_etf_norgate_trial_raw_d1",
        "snapshot_version": NORGATE_TRIAL_RAW_D1_VERSION,
        "dataset_id": _dataset_id(destination),
        "dataset_hash": data_hash,
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "symbols": list(FIXED_NORGATE_TRIAL_SYMBOLS),
        "symbol_order": list(FIXED_NORGATE_TRIAL_SYMBOLS),
        "row_count": row_count,
        "requested_window": {
            "start": requested_start.isoformat(),
            "end": requested_end.isoformat(),
            "end_semantics": "inclusive source-session date",
        },
        "actual_common_window": {
            "start": common_sessions[0].isoformat(),
            "end": common_sessions[-1].isoformat(),
            "common_session_count": len(common_sessions),
            "per_symbol_row_count": len(common_sessions),
        },
        "norgate_source_contract": {
            "provider": "Norgate Data",
            "query_method": "price_timeseries",
            "interval": "D",
            "requested_stock_price_adjustment_setting": "NONE",
            "adjustment_semantics_verified": False,
            "padding_setting": "NONE",
            "timeseriesformat": "numpy-recarray",
            "fields": list(_SOURCE_FIELDS),
        },
        "norgate_package": {"name": "norgatedata", "version": norgate_package_version},
        "capital_event_evidence": {
            "query_method": "capital_event_timeseries",
            "query_window_clipped_explicitly": True,
            "response_can_be_range_padded": True,
            "marker_exclusion_rule": "marker_session_plus_adjacent_observed_sessions",
            "marker_dates_are_not_timestamps_or_actionable_events": True,
            "per_symbol": {
                symbol: _event_document(event_evidence[symbol])
                for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
            },
            "observed_nonzero_marker_count": sum(
                len(value.marker_dates) for value in event_evidence.values()
            ),
            "observed_marker_count_interpretation": (
                "not_established_from_clipped_or_padded_query"
            ),
            "exclusion_row_count": len(exclusions),
        },
        "files": {
            "norgate_ohlcv": {
                "path": _DATA_FILE,
                "sha256": data_hash,
                "size_bytes": data_size,
                "format": "csv.gz",
                "columns": list(_DATA_COLUMNS),
            },
            "capital_event_exclusions": {
                "path": _EVENT_FILE,
                "sha256": event_hash,
                "size_bytes": event_size,
                "format": "csv",
                "columns": list(_EVENT_COLUMNS),
            },
            "retention_marker": {
                "path": _RETENTION_FILE,
                "sha256": marker_hash,
                "size_bytes": marker_size,
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
        "scope": _SCOPE,
        "limitations": [
            "The trial coverage is bounded and not a broad historical universe.",
            "NONE is a recorded query setting, not a proof of adjustment semantics.",
            "Capital-event markers are conservative exclusion evidence, not timestamps.",
            "This source is separate from Tiingo and does not establish source preference.",
        ],
    }


def _event_document(value: NorgateCapitalEventEvidence) -> dict[str, Any]:
    return {
        "returned_row_count": value.returned_row_count,
        "returned_start": value.returned_start.isoformat() if value.returned_start else None,
        "returned_end": value.returned_end.isoformat() if value.returned_end else None,
        "clipped_session_count": value.clipped_session_count,
        "observed_marker_count": len(value.marker_dates),
        "observed_marker_count_interpretation": "not_established_from_clipped_or_padded_query",
        "response_was_range_padded": value.returned_row_count != value.clipped_session_count,
    }


def _validate_manifest_header(
    manifest: dict[str, Any],
    *,
    snapshot: Path,
    expected_requested_start: date | None = None,
    expected_requested_end: date | None = None,
) -> None:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "fixed_etf_norgate_trial_raw_d1"
        or manifest.get("snapshot_version") != NORGATE_TRIAL_RAW_D1_VERSION
        or manifest.get("dataset_id") != _dataset_id(snapshot)
        or manifest.get("immutable_snapshot") is not True
        or manifest.get("symbols") != list(FIXED_NORGATE_TRIAL_SYMBOLS)
        or manifest.get("symbol_order") != list(FIXED_NORGATE_TRIAL_SYMBOLS)
    ):
        raise ValueError("Norgate trial raw-D1 manifest identity is invalid")
    if manifest.get("scope") != _SCOPE:
        raise ValueError("Norgate trial raw-D1 scope is invalid")
    if manifest.get("norgate_source_contract") != {
        "provider": "Norgate Data",
        "query_method": "price_timeseries",
        "interval": "D",
        "requested_stock_price_adjustment_setting": "NONE",
        "adjustment_semantics_verified": False,
        "padding_setting": "NONE",
        "timeseriesformat": "numpy-recarray",
        "fields": list(_SOURCE_FIELDS),
    }:
        raise ValueError("Norgate trial raw-D1 source contract is invalid")
    _utc_datetime(_datetime_value(manifest.get("retrieved_at_utc")), "retrieved_at_utc")
    _required_sha256(manifest.get("dataset_hash"), "dataset hash")
    package = _mapping(manifest.get("norgate_package"), "package")
    if package.get("name") != "norgatedata":
        raise ValueError("Norgate trial raw-D1 package identity is invalid")
    _nonempty_text(package.get("version"), "package version")
    requested = _mapping(manifest.get("requested_window"), "requested window")
    requested_start = _date_value(requested.get("start"), "requested start")
    requested_end = _date_value(requested.get("end"), "requested end")
    if (
        requested_end < requested_start
        or requested.get("end_semantics") != "inclusive source-session date"
    ):
        raise ValueError("Norgate trial raw-D1 requested window is invalid")
    if (expected_requested_start is not None and requested_start != expected_requested_start) or (
        expected_requested_end is not None and requested_end != expected_requested_end
    ):
        raise ValueError("Norgate trial raw-D1 snapshot request does not match existing evidence")
    _validate_storage_document(manifest.get("storage"))
    _validate_retention_document(manifest.get("retention"))


def _validate_dividend_manifest_header(manifest: dict[str, Any], *, snapshot: Path) -> None:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "fixed_etf_norgate_trial_raw_d1_dividend_exclusions"
        or manifest.get("snapshot_version") != NORGATE_TRIAL_DIVIDEND_EXCLUSION_VERSION
        or manifest.get("dataset_id") != _dividend_dataset_id(snapshot)
        or manifest.get("immutable_snapshot") is not True
        or manifest.get("symbols") != list(FIXED_NORGATE_TRIAL_SYMBOLS)
        or manifest.get("symbol_order") != list(FIXED_NORGATE_TRIAL_SYMBOLS)
    ):
        raise ValueError("Norgate dividend exclusion manifest identity is invalid")
    if manifest.get("scope") != _DIVIDEND_SCOPE:
        raise ValueError("Norgate dividend exclusion scope is invalid")
    if manifest.get("norgate_source_contract") != {
        "provider": "Norgate Data",
        "query_method": "price_timeseries",
        "interval": "D",
        "requested_stock_price_adjustment_setting": "NONE",
        "adjustment_semantics_verified": False,
        "padding_setting": "NONE",
        "timeseriesformat": "numpy-recarray",
        "fields": ["Date", "Dividend"],
        "marker_semantics_verified": False,
    }:
        raise ValueError("Norgate dividend exclusion source contract is invalid")
    _utc_datetime(_datetime_value(manifest.get("retrieved_at_utc")), "retrieved_at_utc")
    package = _mapping(manifest.get("norgate_package"), "dividend package")
    if package.get("name") != "norgatedata":
        raise ValueError("Norgate dividend exclusion package identity is invalid")
    _nonempty_text(package.get("version"), "Norgate dividend package version")
    _validate_storage_document(manifest.get("storage"))
    _validate_retention_document(manifest.get("retention"))


def _validate_dividend_parent_document(
    document: dict[str, Any],
    *,
    parent: NorgateTrialRawD1Result,
    common_sessions: tuple[date, ...],
) -> None:
    if document != _dividend_parent_document(parent, common_sessions=common_sessions):
        raise ValueError("Norgate dividend exclusion parent evidence is invalid")


def _validate_written_dividend_exclusion_snapshot(
    snapshot: Path,
    manifest: dict[str, Any],
    *,
    parent: NorgateTrialRawD1Result,
    common_sessions: tuple[date, ...],
) -> dict[str, Any]:
    files = _mapping(manifest.get("files"), "dividend exclusion files")
    exclusion_data = _read_verified_file(
        snapshot,
        files.get("dividend_marker_exclusions"),
        expected_name=_DIVIDEND_FILE,
        label="dividend marker exclusions",
    )
    marker_data = _read_verified_file(
        snapshot,
        files.get("retention_marker"),
        expected_name=_RETENTION_FILE,
        label="dividend retention marker",
    )
    if marker_data != _dividend_retention_marker_bytes():
        raise ValueError("Norgate dividend exclusion retention marker is invalid")
    _validate_dividend_parent_document(
        _mapping(manifest.get("parent_raw_d1"), "dividend parent"),
        parent=parent,
        common_sessions=common_sessions,
    )
    exclusions = _parse_dividend_exclusion_rows(exclusion_data)
    marker_count = _validate_dividend_exclusion_rows(
        exclusions,
        common_sessions=common_sessions,
        manifest=manifest,
    )
    package = _mapping(manifest.get("norgate_package"), "dividend package")
    storage = _mapping(manifest.get("storage"), "dividend storage")
    return {
        "marker_count": marker_count,
        "excluded_session_count": len(exclusions),
        "norgate_package_version": _nonempty_text(
            package.get("version"), "Norgate dividend package version"
        ),
        "free_percent": _nonnegative_float(storage.get("free_percent"), "free percent"),
    }


def _validate_dividend_exclusion_rows(
    exclusions: tuple[_DividendExclusion, ...],
    *,
    common_sessions: tuple[date, ...],
    manifest: dict[str, Any],
) -> int:
    evidence = _mapping(manifest.get("source_marker_evidence"), "dividend marker evidence")
    if (
        evidence.get("source_field") != "Dividend"
        or evidence.get("response_exactly_matches_parent_sessions") is not True
        or evidence.get("marker_exclusion_rule")
        != "marker_session_plus_adjacent_observed_sessions"
        or evidence.get("source_marker_dates_are_not_timestamps_or_actionable_events") is not True
        or evidence.get("all_symbols_have_nonzero_marker") is not True
    ):
        raise ValueError("Norgate dividend exclusion marker contract is invalid")
    per_symbol = _mapping(evidence.get("per_symbol"), "dividend marker symbols")
    if set(per_symbol) != set(FIXED_NORGATE_TRIAL_SYMBOLS):
        raise ValueError("Norgate dividend exclusion symbols are invalid")
    markers_by_symbol = {
        symbol: tuple(
            sorted(
                {
                    exclusion.source_marker_date
                    for exclusion in exclusions
                    if exclusion.symbol == symbol
                }
            )
        )
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
    }
    if any(not markers for markers in markers_by_symbol.values()):
        raise ValueError("Norgate dividend exclusion requires nonzero markers for every symbol")
    expected = tuple(
        exclusion
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
        for exclusion in _dividend_exclusions(
            symbol,
            marker_dates=markers_by_symbol[symbol],
            common_sessions=common_sessions,
        )
    )
    if exclusions != expected:
        raise ValueError("Norgate dividend exclusions are inconsistent")
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        expected_document = {
            "returned_row_count": len(common_sessions),
            "nonzero_marker_count": len(markers_by_symbol[symbol]),
            "response_matches_parent_sessions": True,
        }
        if per_symbol.get(symbol) != expected_document:
            raise ValueError("Norgate dividend exclusion per-symbol evidence is invalid")
    marker_count = _dividend_marker_count(exclusions)
    if (
        evidence.get("observed_nonzero_marker_count") != marker_count
        or evidence.get("exclusion_row_count") != len(exclusions)
    ):
        raise ValueError("Norgate dividend exclusion aggregate evidence is invalid")
    return marker_count


def _validate_written_snapshot(
    snapshot: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Norgate trial raw-D1 file evidence is invalid")
    data = _read_verified_file(
        snapshot,
        files.get("norgate_ohlcv"),
        expected_name=_DATA_FILE,
        label="raw-D1 data",
    )
    event_data = _read_verified_file(
        snapshot,
        files.get("capital_event_exclusions"),
        expected_name=_EVENT_FILE,
        label="capital-event exclusions",
    )
    _read_verified_file(
        snapshot,
        files.get("retention_marker"),
        expected_name=_RETENTION_FILE,
        label="retention marker",
    )
    rows = _parse_data_rows(data)
    common_sessions = _validate_data_rows(rows, manifest)
    exclusions = _parse_event_rows(event_data)
    _validate_event_rows(exclusions, common_sessions=common_sessions, manifest=manifest)
    actual_window = _mapping(manifest.get("actual_common_window"), "actual common window")
    package = _mapping(manifest.get("norgate_package"), "package")
    return {
        "dataset_hash": _required_sha256(manifest.get("dataset_hash"), "dataset hash"),
        "row_count": len(rows),
        "common_session_count": len(common_sessions),
        "event_marker_count": _event_marker_count(exclusions),
        "excluded_session_count": len(exclusions),
        "actual_start": _date_value(actual_window.get("start"), "actual common start"),
        "actual_end": _date_value(actual_window.get("end"), "actual common end"),
        "norgate_package_version": _nonempty_text(package.get("version"), "package version"),
        "free_percent": _nonnegative_float(
            _mapping(manifest.get("storage"), "storage").get("free_percent"), "free percent"
        ),
    }


def _validate_data_rows(rows: tuple[Bar, ...], manifest: dict[str, Any]) -> tuple[date, ...]:
    expected_rows = _positive_int(manifest.get("row_count"), "row count")
    if len(rows) != expected_rows:
        raise ValueError("Norgate trial raw-D1 row count is inconsistent")
    rows_by_symbol = {
        symbol: tuple(row for row in rows if row.symbol == symbol)
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
    }
    if any(len(rows_by_symbol[symbol]) == 0 for symbol in FIXED_NORGATE_TRIAL_SYMBOLS):
        raise ValueError("Norgate trial raw-D1 symbols are incomplete")
    common_sessions = tuple(
        row.start_ts.date() for row in rows_by_symbol[FIXED_NORGATE_TRIAL_SYMBOLS[0]]
    )
    if any(
        tuple(row.start_ts.date() for row in rows_by_symbol[symbol]) != common_sessions
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS[1:]
    ):
        raise ValueError("Norgate trial raw-D1 sessions are uneven")
    actual = _mapping(manifest.get("actual_common_window"), "actual common window")
    if actual != {
        "start": common_sessions[0].isoformat(),
        "end": common_sessions[-1].isoformat(),
        "common_session_count": len(common_sessions),
        "per_symbol_row_count": len(common_sessions),
    }:
        raise ValueError("Norgate trial raw-D1 common window is inconsistent")
    if manifest.get("dataset_hash") != _mapping(
        _mapping(manifest.get("files"), "files").get("norgate_ohlcv"), "raw-D1 file"
    ).get("sha256"):
        raise ValueError("Norgate trial raw-D1 dataset hash is inconsistent")
    return common_sessions


def _validate_event_rows(
    exclusions: tuple[_EventExclusion, ...],
    *,
    common_sessions: tuple[date, ...],
    manifest: dict[str, Any],
) -> None:
    event_document = _mapping(manifest.get("capital_event_evidence"), "capital-event evidence")
    if (
        event_document.get("query_method") != "capital_event_timeseries"
        or event_document.get("query_window_clipped_explicitly") is not True
        or event_document.get("response_can_be_range_padded") is not True
        or event_document.get("marker_exclusion_rule")
        != "marker_session_plus_adjacent_observed_sessions"
        or event_document.get("marker_dates_are_not_timestamps_or_actionable_events") is not True
    ):
        raise ValueError("Norgate trial raw-D1 capital-event contract is invalid")
    per_symbol = _mapping(event_document.get("per_symbol"), "capital-event per-symbol evidence")
    if set(per_symbol) != set(FIXED_NORGATE_TRIAL_SYMBOLS):
        raise ValueError("Norgate trial raw-D1 event symbols are invalid")
    markers_by_symbol = {
        symbol: tuple(
            sorted(
                {
                    exclusion.event_marker_date
                    for exclusion in exclusions
                    if exclusion.symbol == symbol
                }
            )
        )
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
    }
    expected = tuple(
        exclusion
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
        for exclusion in _event_exclusions(
            symbol,
            marker_dates=markers_by_symbol[symbol],
            common_sessions=common_sessions,
        )
    )
    if exclusions != expected:
        raise ValueError("Norgate trial raw-D1 event exclusions are inconsistent")
    if event_document.get("observed_nonzero_marker_count") != sum(
        len(markers) for markers in markers_by_symbol.values()
    ):
        raise ValueError("Norgate trial raw-D1 event marker count is inconsistent")
    if (
        event_document.get("observed_marker_count_interpretation")
        != "not_established_from_clipped_or_padded_query"
    ):
        raise ValueError("Norgate trial raw-D1 event marker interpretation is invalid")
    if event_document.get("exclusion_row_count") != len(exclusions):
        raise ValueError("Norgate trial raw-D1 event exclusion count is inconsistent")
    for symbol in FIXED_NORGATE_TRIAL_SYMBOLS:
        document = _mapping(per_symbol.get(symbol), "capital-event symbol evidence")
        if (
            _positive_int(document.get("returned_row_count"), "event returned row count")
            < _positive_int(document.get("clipped_session_count"), "event clipped session count")
            or document.get("clipped_session_count") != len(common_sessions)
            or document.get("observed_marker_count") != len(markers_by_symbol[symbol])
            or document.get("observed_marker_count_interpretation")
            != "not_established_from_clipped_or_padded_query"
            or document.get("response_was_range_padded")
            != (document.get("returned_row_count") != document.get("clipped_session_count"))
        ):
            raise ValueError("Norgate trial raw-D1 event coverage is inconsistent")
        _date_value(document.get("returned_start"), "event returned start")
        _date_value(document.get("returned_end"), "event returned end")


def _event_marker_count(exclusions: tuple[_EventExclusion, ...]) -> int:
    return sum(
        len({exclusion.event_marker_date for exclusion in exclusions if exclusion.symbol == symbol})
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
    )


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    snapshot_suffix: str = _SNAPSHOT_SUFFIX,
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate trial raw-D1 market-data root must exist")
    root = root.resolve()
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate trial raw-D1 market-data root must stay outside Git")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Norgate trial raw-D1 destination already exists")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Norgate trial raw-D1 destination must stay under market data")
    if repo_root is not None and target.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate trial raw-D1 destination must stay outside Git")
    if not target.name.startswith("snapshot=") or not target.name.endswith(snapshot_suffix):
        raise ValueError("Norgate trial raw-D1 destination name is invalid")
    if target.parent.is_dir() and any(target.parent.glob(".stage-*")):
        raise FileExistsError("Norgate trial raw-D1 staging residue requires recovery")
    return target, root


def _validate_existing_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    require_snapshot_name: bool,
    snapshot_suffix: str = _SNAPSHOT_SUFFIX,
) -> Path:
    root = Path(market_data_root).resolve()
    snapshot = Path(snapshot_dir)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("Norgate trial raw-D1 snapshot must be a directory")
    snapshot = snapshot.resolve()
    if not snapshot.is_relative_to(root):
        raise ValueError("Norgate trial raw-D1 snapshot must stay under market data")
    if (
        repo_root is not None
        and snapshot.is_relative_to(Path(repo_root).resolve())
        and not root.is_mount()
    ):
        raise ValueError("Norgate trial raw-D1 snapshot must stay outside Git")
    if require_snapshot_name and (
        not snapshot.name.startswith("snapshot=") or not snapshot.name.endswith(snapshot_suffix)
    ):
        raise ValueError("Norgate trial raw-D1 snapshot name is invalid")
    return snapshot


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Norgate trial raw-D1 storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Norgate trial raw-D1 storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn("Norgate trial raw-D1 storage is below the warning floor", stacklevel=2)
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


def _data_csv_bytes(rows: tuple[Bar, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_DATA_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for bar in rows:
        writer.writerow(
            {
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


def _event_csv_bytes(exclusions: tuple[_EventExclusion, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_EVENT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for exclusion in exclusions:
        writer.writerow(
            {
                "symbol": exclusion.symbol,
                "event_marker_date": exclusion.event_marker_date.isoformat(),
                "excluded_session_date": exclusion.excluded_session_date.isoformat(),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _dividend_csv_bytes(exclusions: tuple[_DividendExclusion, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_DIVIDEND_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for exclusion in exclusions:
        writer.writerow(
            {
                "symbol": exclusion.symbol,
                "source_marker_date": exclusion.source_marker_date.isoformat(),
                "excluded_session_date": exclusion.excluded_session_date.isoformat(),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _retention_marker_bytes() -> bytes:
    return (
        "This directory contains Norgate-origin trial raw-D1 data.\n"
        "If the trial or subscription ends and the Norgate EULA requires deletion,\n"
        "the operator must delete this snapshot directory and derived copies.\n"
        "Do not use this snapshot as a PIT universe, campaign, model, GPU, or\n"
        "paper-trading input. It records development-source evidence only.\n"
        "Capital-event markers are conservative exclusions, not timestamps.\n"
        "A zero observed marker count does not establish that no events occurred.\n"
        "NONE is a requested query parameter, not verified adjustment semantics.\n"
        "This marker records scope only; it does not perform or prove deletion.\n"
        "It does not authorize deletion of C:\\ProgramData\\Norgate Data.\n"
    ).encode("ascii")


def _dividend_retention_marker_bytes() -> bytes:
    return (
        "This directory contains Norgate-origin trial marker metadata derived from a\n"
        "separate retained raw-D1 parent snapshot. If the trial or subscription ends\n"
        "and the Norgate EULA requires deletion, the operator must delete this\n"
        "directory and the referenced parent/derived copies. Do not use these source\n"
        "markers as event timestamps, adjustment semantics, a PIT universe, campaign,\n"
        "model, GPU, paper-trading, or source-preference input.\n"
    ).encode("ascii")


def _read_file(snapshot: Path, filename: str, label: str) -> bytes:
    path = snapshot / filename
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(snapshot):
        raise ValueError(f"Norgate trial raw-D1 {label} path is invalid")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Norgate trial raw-D1 {label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"Norgate trial raw-D1 {label} must be a regular file")
    return resolved.read_bytes()


def _read_verified_file(
    snapshot: Path,
    metadata: object,
    *,
    expected_name: str,
    label: str,
) -> bytes:
    if not isinstance(metadata, dict) or metadata.get("path") != expected_name:
        raise ValueError(f"Norgate trial raw-D1 {label} metadata is invalid")
    data = _read_file(snapshot, expected_name, label)
    if _sha256(data) != _required_sha256(metadata.get("sha256"), f"{label} hash"):
        raise ValueError(f"Norgate trial raw-D1 {label} hash mismatch")
    if metadata.get("size_bytes") != len(data):
        raise ValueError(f"Norgate trial raw-D1 {label} size is inconsistent")
    return data


def _parse_data_rows(data: bytes) -> tuple[Bar, ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as compressed:
            reader = csv.DictReader(io.TextIOWrapper(compressed, encoding="utf-8", newline=""))
            fieldnames = tuple(reader.fieldnames or ())
            source_rows = tuple(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate trial raw-D1 data is invalid") from exc
    if fieldnames != _DATA_COLUMNS:
        raise ValueError("Norgate trial raw-D1 CSV schema is invalid")
    bars: list[Bar] = []
    previous_symbol_index = -1
    previous_date: date | None = None
    for source_row in source_rows:
        symbol = _symbol(source_row.get("symbol"))
        try:
            symbol_index = FIXED_NORGATE_TRIAL_SYMBOLS.index(symbol)
        except ValueError as exc:
            raise ValueError("Norgate trial raw-D1 CSV symbol is invalid") from exc
        session_date = _date_value(source_row.get("date"), "CSV session date")
        if symbol_index < previous_symbol_index or (
            symbol_index == previous_symbol_index
            and previous_date is not None
            and session_date <= previous_date
        ):
            raise ValueError("Norgate trial raw-D1 CSV ordering is invalid")
        if symbol_index != previous_symbol_index:
            previous_date = None
        bars.append(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(session_date, datetime.min.time(), UTC),
                open=_decimal(source_row.get("open"), "CSV open"),
                high=_decimal(source_row.get("high"), "CSV high"),
                low=_decimal(source_row.get("low"), "CSV low"),
                close=_decimal(source_row.get("close"), "CSV close"),
                volume=_decimal(source_row.get("volume"), "CSV volume"),
            )
        )
        previous_symbol_index = symbol_index
        previous_date = session_date
    if not bars:
        raise ValueError("Norgate trial raw-D1 CSV has no rows")
    return tuple(bars)


def _parse_event_rows(data: bytes) -> tuple[_EventExclusion, ...]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
        fieldnames = tuple(reader.fieldnames or ())
        source_rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate trial raw-D1 event CSV is invalid") from exc
    if fieldnames != _EVENT_COLUMNS:
        raise ValueError("Norgate trial raw-D1 event CSV schema is invalid")
    exclusions: list[_EventExclusion] = []
    for source_row in source_rows:
        exclusions.append(
            _EventExclusion(
                symbol=_symbol(source_row.get("symbol")),
                event_marker_date=_date_value(
                    source_row.get("event_marker_date"), "event marker date"
                ),
                excluded_session_date=_date_value(
                    source_row.get("excluded_session_date"), "excluded session date"
                ),
            )
        )
    if tuple(sorted(exclusions, key=_event_sort_key)) != tuple(exclusions):
        raise ValueError("Norgate trial raw-D1 event CSV ordering is invalid")
    return tuple(exclusions)


def _event_sort_key(value: _EventExclusion) -> tuple[int, date, date]:
    return (
        FIXED_NORGATE_TRIAL_SYMBOLS.index(value.symbol),
        value.event_marker_date,
        value.excluded_session_date,
    )


def _parse_dividend_exclusion_rows(data: bytes) -> tuple[_DividendExclusion, ...]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
        fieldnames = tuple(reader.fieldnames or ())
        source_rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate dividend exclusion CSV is invalid") from exc
    if fieldnames != _DIVIDEND_COLUMNS:
        raise ValueError("Norgate dividend exclusion CSV schema is invalid")
    exclusions: list[_DividendExclusion] = []
    for source_row in source_rows:
        exclusions.append(
            _DividendExclusion(
                symbol=_symbol(source_row.get("symbol")),
                source_marker_date=_date_value(
                    source_row.get("source_marker_date"), "source marker date"
                ),
                excluded_session_date=_date_value(
                    source_row.get("excluded_session_date"), "excluded session date"
                ),
            )
        )
    if tuple(sorted(exclusions, key=_dividend_sort_key)) != tuple(exclusions):
        raise ValueError("Norgate dividend exclusion CSV ordering is invalid")
    return tuple(exclusions)


def _dividend_sort_key(value: _DividendExclusion) -> tuple[int, date, date]:
    return (
        FIXED_NORGATE_TRIAL_SYMBOLS.index(value.symbol),
        value.source_marker_date,
        value.excluded_session_date,
    )


def _dividend_marker_count(exclusions: tuple[_DividendExclusion, ...]) -> int:
    return sum(
        len(
            {
                exclusion.source_marker_date
                for exclusion in exclusions
                if exclusion.symbol == symbol
            }
        )
        for symbol in FIXED_NORGATE_TRIAL_SYMBOLS
    )


def _load_norgatedata(loader: ClientLoader | None) -> Any:
    try:
        if loader is not None:
            return loader()
        import importlib

        return importlib.import_module("norgatedata")
    except Exception as exc:
        raise NorgateCapitalEventUnavailableError(
            "Norgate capital-event client is unavailable"
        ) from exc


def _validate_storage_document(value: object) -> None:
    storage = _mapping(value, "storage")
    if (
        _nonnegative_float(storage.get("free_percent"), "free percent") < 15
        or storage.get("warning_floor_percent") != 20
        or storage.get("hard_floor_percent") != 15
        or not isinstance(storage.get("root"), str)
    ):
        raise ValueError("Norgate trial raw-D1 storage evidence is invalid")


def _validate_retention_document(value: object) -> None:
    if value != {
        "norgate_origin_data": True,
        "operator_action_required_on_lapse": True,
        "automated_deletion": False,
        "marker_file": _RETENTION_FILE,
    }:
        raise ValueError("Norgate trial raw-D1 retention evidence is invalid")


def _validate_window(requested_start: date, requested_end: date) -> None:
    if isinstance(requested_start, datetime) or isinstance(requested_end, datetime):
        raise ValueError("Norgate trial raw-D1 dates must not include a time")
    if requested_end < requested_start:
        raise ValueError("Norgate trial raw-D1 end date must not precede start date")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid")
    return value


def _row_value(row: object, name: str) -> object:
    try:
        return row[name]  # type: ignore[index]
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("Norgate capital-event row is invalid") from exc


def _event_flag(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    normalized = str(value).strip().lower()
    return normalized not in {"", "0", "0.0", "false", "none", "nan", "nat"}


def _symbol(value: object) -> str:
    result = str(value or "").strip().upper()
    if result not in FIXED_NORGATE_TRIAL_SYMBOLS:
        raise ValueError("Norgate trial raw-D1 symbol is invalid")
    return result


def _session_date(value: object) -> date:
    return _date_value(str(value)[:10], "capital-event date")


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid") from exc


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid") from exc
    if not result.is_finite():
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid")
    return result


def _datetime_value(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Norgate trial raw-D1 datetime is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Norgate trial raw-D1 datetime is invalid") from exc


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"Norgate trial raw-D1 {label} must be UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid")
    return value


def _nonnegative_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid")
    return float(value)


def _nonempty_text(value: object, label: str) -> str:
    result = str(value or "")
    if not result or result != result.strip():
        raise ValueError(f"Norgate trial raw-D1 {label} is required")
    return result


def _required_sha256(value: object, label: str) -> str:
    result = _nonempty_text(value, label)
    if len(result) != 71 or not result.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in result[7:]
    ):
        raise ValueError(f"Norgate trial raw-D1 {label} is invalid")
    return result


def _dataset_id(snapshot_dir: Path) -> str:
    return f"us_equities.fixed_etf_norgate_trial_raw_d1.{Path(snapshot_dir).name}"


def _dividend_dataset_id(snapshot_dir: Path) -> str:
    return (
        "us_equities.fixed_etf_norgate_trial_raw_d1_dividend_exclusions."
        f"{Path(snapshot_dir).name}"
    )


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

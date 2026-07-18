"""Bounded, host-only raw-D1 source-alignment evidence for three fixed ETFs."""

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
from pathlib import Path
from typing import Any

from thericher_v2.contracts import Bar, Timeframe

FIXED_ALIGNMENT_SYMBOLS = ("SPY", "QQQ", "IWM")
DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
DEFAULT_NORGATE_RAW_ALIGNMENT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_daily"
    / "canonical"
    / "norgate_raw_d1_alignment"
)
_SNAPSHOT_SUFFIX = "-norgate-raw-d1-alignment-r1"
_DATA_FILE = "norgate_ohlcv_1d.csv.gz"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_DATA_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")
_OHLCV_FIELDS = ("open", "high", "low", "close", "volume")


class NorgateRawAlignmentError(RuntimeError):
    """Raised when the bounded host-only Norgate alignment cannot be built."""


@dataclass(frozen=True, slots=True)
class TiingoRawD1Reference:
    """Pinned external Tiingo raw-D1 input identity for comparison only."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str


@dataclass(frozen=True, slots=True)
class NorgateRawAlignmentResult:
    """Non-secret summary of one immutable source-alignment snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    row_count: int
    comparison_status: str
    requested_start: date
    requested_end: date
    norgate_package_version: str
    free_percent: float


BarLoader = Callable[[str, date, date], Sequence[Bar]]


def default_norgate_raw_alignment_snapshot_dir(retrieval_date: date) -> Path:
    """Return the external immutable destination for one bounded comparison."""

    return DEFAULT_NORGATE_RAW_ALIGNMENT_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def build_norgate_raw_d1_alignment_snapshot(
    *,
    destination: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    tiingo_reference: TiingoRawD1Reference,
    norgate_bars: BarLoader,
    tiingo_bars: BarLoader,
    norgate_package_version: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateRawAlignmentResult:
    """Write one external Norgate raw-D1 snapshot and comparison counts.

    The loaders are deliberately injected: Norgate stays host-only at the caller
    boundary, and the already-attested Tiingo loader remains the only Tiingo
    source reader. No loader receives credentials or performs source selection.
    """

    _validate_window(requested_start, requested_end)
    if platform_name != "win32":
        raise NorgateRawAlignmentError("Norgate raw-D1 alignment requires Windows")
    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    destination_path, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    reference = _validate_tiingo_reference(
        tiingo_reference,
        market_data_root=root,
        repo_root=repo_root,
    )
    package_version = _nonempty_text(norgate_package_version, "Norgate package version")
    rows, comparison = _collect_alignment(
        requested_start=requested_start,
        requested_end=requested_end,
        norgate_bars=norgate_bars,
        tiingo_bars=tiingo_bars,
    )

    data_bytes = _gzip_bytes(_data_csv_bytes(rows))
    data_hash = _sha256(data_bytes)
    marker_bytes = _retention_marker_bytes()
    marker_hash = _sha256(marker_bytes)
    manifest = _manifest(
        destination=destination_path,
        market_data_root=root,
        reference=reference,
        data_hash=data_hash,
        data_size=len(data_bytes),
        marker_hash=marker_hash,
        marker_size=len(marker_bytes),
        row_count=len(rows),
        requested_start=requested_start,
        requested_end=requested_end,
        retrieved_at_utc=retrieved_at,
        norgate_package_version=package_version,
        comparison=comparison,
        free_percent=free_percent,
    )
    manifest_bytes = _json_bytes(manifest)

    staging = _create_staging_directory(destination_path)
    try:
        (staging / _DATA_FILE).write_bytes(data_bytes)
        (staging / _RETENTION_FILE).write_bytes(marker_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        _validate_written_snapshot(staging, manifest)
        os.rename(staging, destination_path)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return verify_norgate_raw_d1_alignment_snapshot(
        destination_path,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def verify_norgate_raw_d1_alignment_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateRawAlignmentResult:
    """Reattest one published alignment snapshot without calling either source."""

    snapshot = _validate_existing_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    try:
        manifest_bytes = (snapshot / _MANIFEST_FILE).read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate raw-D1 alignment manifest is unavailable") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Norgate raw-D1 alignment manifest is invalid")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "fixed_etf_norgate_raw_d1_alignment"
        or manifest.get("dataset_id") != _dataset_id(snapshot)
    ):
        raise ValueError("Norgate raw-D1 alignment manifest identity is invalid")
    _validate_scope(manifest.get("scope"))
    _validate_written_snapshot(snapshot, manifest)

    requested = manifest.get("requested_window")
    if not isinstance(requested, dict):
        raise ValueError("Norgate raw-D1 requested window is unavailable")
    comparison = manifest.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError("Norgate raw-D1 comparison summary is unavailable")
    status = comparison.get("status")
    if status not in {"literal_raw_ohlcv_match", "literal_raw_ohlcv_difference"}:
        raise ValueError("Norgate raw-D1 comparison status is invalid")
    storage = manifest.get("storage")
    package = manifest.get("norgate_package")
    if not isinstance(storage, dict) or not isinstance(package, dict):
        raise ValueError("Norgate raw-D1 manifest metadata is unavailable")
    return NorgateRawAlignmentResult(
        snapshot_dir=snapshot,
        dataset_id=_dataset_id(snapshot),
        dataset_hash=_required_sha256(manifest.get("dataset_hash"), "dataset hash"),
        manifest_hash=_sha256(manifest_bytes),
        row_count=_positive_int(manifest.get("row_count"), "row count"),
        comparison_status=status,
        requested_start=_date_value(requested.get("start"), "requested start"),
        requested_end=_date_value(requested.get("end"), "requested end"),
        norgate_package_version=_nonempty_text(package.get("version"), "package version"),
        free_percent=_nonnegative_float(storage.get("free_percent"), "free percent"),
    )


def _collect_alignment(
    *,
    requested_start: date,
    requested_end: date,
    norgate_bars: BarLoader,
    tiingo_bars: BarLoader,
) -> tuple[tuple[Bar, ...], dict[str, Any]]:
    rows: list[Bar] = []
    summaries: dict[str, dict[str, Any]] = {}
    complete_match = True
    for symbol in FIXED_ALIGNMENT_SYMBOLS:
        norgate = _validated_bars(
            norgate_bars(symbol, requested_start, requested_end),
            symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
            source="Norgate",
        )
        tiingo = _validated_bars(
            tiingo_bars(symbol, requested_start, requested_end),
            symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
            source="Tiingo",
        )
        if not norgate or not tiingo:
            raise ValueError("Norgate raw-D1 alignment source returned no bars")
        rows.extend(norgate.values())
        summary = _comparison_summary(norgate, tiingo)
        summaries[symbol] = summary
        complete_match = complete_match and summary["complete_literal_match"]
    return tuple(rows), {
        "status": "literal_raw_ohlcv_match"
        if complete_match
        else "literal_raw_ohlcv_difference",
        "symbols": summaries,
        "comparison_rule": "decimal equality on raw OHLCV fields for exact common dates",
        "source_preference": "not evaluated",
    }


def _validated_bars(
    bars: Sequence[Bar],
    *,
    symbol: str,
    requested_start: date,
    requested_end: date,
    source: str,
) -> dict[date, Bar]:
    result: dict[date, Bar] = {}
    previous_date: date | None = None
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
            raise ValueError(f"{source} raw-D1 bar contract is invalid")
        session_date = bar.start_ts.date()
        if session_date < requested_start or session_date > requested_end:
            raise ValueError(f"{source} raw-D1 response is outside the requested window")
        if previous_date is not None and session_date <= previous_date:
            raise ValueError(f"{source} raw-D1 response must be strictly ordered")
        result[session_date] = bar
        previous_date = session_date
    return result


def _comparison_summary(norgate: dict[date, Bar], tiingo: dict[date, Bar]) -> dict[str, Any]:
    norgate_dates = set(norgate)
    tiingo_dates = set(tiingo)
    common_dates = tuple(sorted(norgate_dates & tiingo_dates))
    field_equal_counts = {
        field: sum(
            getattr(norgate[session_date], field) == getattr(tiingo[session_date], field)
            for session_date in common_dates
        )
        for field in _OHLCV_FIELDS
    }
    all_fields_equal = sum(
        all(
            getattr(norgate[session_date], field) == getattr(tiingo[session_date], field)
            for field in _OHLCV_FIELDS
        )
        for session_date in common_dates
    )
    return {
        "norgate_session_count": len(norgate_dates),
        "tiingo_session_count": len(tiingo_dates),
        "common_session_count": len(common_dates),
        "norgate_only_session_count": len(norgate_dates - tiingo_dates),
        "tiingo_only_session_count": len(tiingo_dates - norgate_dates),
        "field_equal_counts": field_equal_counts,
        "all_ohlcv_equal_session_count": all_fields_equal,
        "complete_literal_match": (
            len(norgate_dates) == len(tiingo_dates) == len(common_dates) == all_fields_equal
        ),
    }


def _validate_window(requested_start: date, requested_end: date) -> None:
    if isinstance(requested_start, datetime) or isinstance(requested_end, datetime):
        raise ValueError("Norgate raw-D1 dates must not include a time")
    if requested_end < requested_start:
        raise ValueError("Norgate raw-D1 end date must not precede start date")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root).resolve()
    if not root.is_dir():
        raise ValueError("Norgate raw-D1 market-data root must exist")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Norgate raw-D1 destination already exists")
    target = target.resolve()
    _validate_external_path(target, market_data_root=root, repo_root=repo_root)
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Norgate raw-D1 destination must use the required snapshot name")
    return target, root


def _validate_existing_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> Path:
    snapshot = Path(snapshot_dir)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("Norgate raw-D1 snapshot must be a directory")
    snapshot = snapshot.resolve()
    _validate_external_path(
        snapshot,
        market_data_root=Path(market_data_root).resolve(),
        repo_root=repo_root,
    )
    if not snapshot.name.startswith("snapshot=") or not snapshot.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Norgate raw-D1 snapshot must use the required snapshot name")
    return snapshot


def _validate_external_path(path: Path, *, market_data_root: Path, repo_root: Path | None) -> None:
    if not path.is_relative_to(market_data_root):
        raise ValueError("Norgate raw-D1 paths must stay under market data")
    if repo_root is not None and path.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate raw-D1 paths must stay outside Git")


def _validate_tiingo_reference(
    reference: TiingoRawD1Reference,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> TiingoRawD1Reference:
    snapshot = Path(reference.snapshot_dir)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("Tiingo raw-D1 reference snapshot is unavailable")
    snapshot = snapshot.resolve()
    _validate_external_path(snapshot, market_data_root=market_data_root, repo_root=repo_root)
    return TiingoRawD1Reference(
        snapshot_dir=snapshot,
        dataset_id=_nonempty_text(reference.dataset_id, "Tiingo dataset id"),
        dataset_hash=_required_sha256(reference.dataset_hash, "Tiingo dataset hash"),
        manifest_hash=_required_sha256(reference.manifest_hash, "Tiingo manifest hash"),
    )


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Norgate raw-D1 storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Norgate raw-D1 storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn(
            "Norgate raw-D1 storage is below the warning free-space floor",
            stacklevel=2,
        )
    return free_percent


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".stage-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _data_csv_bytes(rows: Sequence[Bar]) -> bytes:
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


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _retention_marker_bytes() -> bytes:
    return (
        "This directory contains Norgate-origin raw-D1 data.\n"
        "If the trial or subscription ends and the Norgate EULA requires deletion,\n"
        "the operator must delete this snapshot directory and derived copies.\n"
        "Do not use this snapshot to choose a source or as a campaign, model, or\n"
        "paper-trading input. It records bounded alignment evidence only.\n"
        "This marker records scope only; it does not perform or prove deletion.\n"
        "It does not authorize deletion of C:\\ProgramData\\Norgate Data.\n"
    ).encode("ascii")


def _manifest(
    *,
    destination: Path,
    market_data_root: Path,
    reference: TiingoRawD1Reference,
    data_hash: str,
    data_size: int,
    marker_hash: str,
    marker_size: int,
    row_count: int,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    norgate_package_version: str,
    comparison: dict[str, Any],
    free_percent: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "fixed_etf_norgate_raw_d1_alignment",
        "dataset_id": _dataset_id(destination),
        "dataset_hash": data_hash,
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "symbols": list(FIXED_ALIGNMENT_SYMBOLS),
        "symbol_order": list(FIXED_ALIGNMENT_SYMBOLS),
        "row_count": row_count,
        "requested_window": {
            "start": requested_start.isoformat(),
            "end": requested_end.isoformat(),
            "end_semantics": "inclusive source-session date",
        },
        "norgate_source_contract": {
            "provider": "Norgate Data",
            "query_method": "price_timeseries",
            "interval": "D",
            "stock_price_adjustment_setting": "NONE",
            "padding_setting": "NONE",
            "timeseriesformat": "numpy-recarray",
            "fields": ["Date", "Open", "High", "Low", "Close", "Volume"],
        },
        "norgate_package": {"name": "norgatedata", "version": norgate_package_version},
        "tiingo_reference": {
            "snapshot_dir": str(reference.snapshot_dir),
            "dataset_id": reference.dataset_id,
            "dataset_hash": reference.dataset_hash,
            "manifest_hash": reference.manifest_hash,
            "raw_price_policy": "copy_raw_ohlcv_without_price_rescaling",
        },
        "comparison": comparison,
        "files": {
            "norgate_ohlcv": {
                "path": _DATA_FILE,
                "sha256": data_hash,
                "size_bytes": data_size,
                "format": "csv.gz",
                "columns": list(_DATA_COLUMNS),
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
        "scope": {
            "data_alignment_only": True,
            "source_preference_eligible": False,
            "point_in_time_eligible": False,
            "campaign_eligible": False,
            "model_eligible": False,
            "paper_trading_eligible": False,
        },
        "limitations": [
            "Raw equality or inequality does not establish adjustment semantics.",
            "The comparison does not establish publication-time, PIT, delisting, or eligibility"
            " facts.",
            "An inequality cannot identify which provider is correct.",
        ],
    }


def _validate_scope(value: object) -> None:
    if not isinstance(value, dict) or value != {
        "data_alignment_only": True,
        "source_preference_eligible": False,
        "point_in_time_eligible": False,
        "campaign_eligible": False,
        "model_eligible": False,
        "paper_trading_eligible": False,
    }:
        raise ValueError("Norgate raw-D1 scope must remain alignment-only")


def _validate_written_snapshot(snapshot: Path, manifest: dict[str, Any]) -> None:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Norgate raw-D1 manifest is missing file evidence")
    data = _read_verified_file(
        snapshot,
        files.get("norgate_ohlcv"),
        expected_name=_DATA_FILE,
        label="raw-D1 data",
    )
    _read_verified_file(
        snapshot,
        files.get("retention_marker"),
        expected_name=_RETENTION_FILE,
        label="retention marker",
    )
    try:
        rows = _csv_row_count(gzip.decompress(data))
    except OSError as exc:
        raise ValueError("Norgate raw-D1 data compression is invalid") from exc
    if rows != manifest.get("row_count"):
        raise ValueError("Norgate raw-D1 row count is inconsistent")
    if manifest.get("dataset_hash") != files["norgate_ohlcv"].get("sha256"):
        raise ValueError("Norgate raw-D1 dataset hash is inconsistent")


def _read_verified_file(
    snapshot: Path,
    metadata: object,
    *,
    expected_name: str,
    label: str,
) -> bytes:
    if not isinstance(metadata, dict) or metadata.get("path") != expected_name:
        raise ValueError(f"Norgate raw-D1 {label} metadata is invalid")
    path = snapshot / expected_name
    if path.is_symlink() or not path.resolve().is_relative_to(snapshot):
        raise ValueError(f"Norgate raw-D1 {label} path is invalid")
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"Norgate raw-D1 {label} is missing") from exc
    if _sha256(data) != _required_sha256(metadata.get("sha256"), f"{label} hash"):
        raise ValueError(f"Norgate raw-D1 {label} hash mismatch")
    if metadata.get("size_bytes") != len(data):
        raise ValueError(f"Norgate raw-D1 {label} size is inconsistent")
    return data


def _csv_row_count(data: bytes) -> int:
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""))
        header = tuple(next(reader))
    except (StopIteration, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate raw-D1 CSV is invalid") from exc
    if header != _DATA_COLUMNS:
        raise ValueError("Norgate raw-D1 CSV schema is invalid")
    return sum(1 for _row in reader)


def _dataset_id(snapshot_dir: Path) -> str:
    return f"us_equities.fixed_etf_norgate_raw_d1_alignment.{Path(snapshot_dir).name}"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _required_sha256(value: object, label: str) -> str:
    text = _nonempty_text(value, label)
    if len(text) != 71 or not text.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in text[7:]
    ):
        raise ValueError(f"Norgate raw-D1 {label} is invalid")
    return text


def _nonempty_text(value: object, label: str) -> str:
    text = str(value or "")
    if not text or text != text.strip():
        raise ValueError(f"Norgate raw-D1 {label} is required")
    return text


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Norgate raw-D1 {label} is invalid")
    return value


def _nonnegative_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Norgate raw-D1 {label} is invalid")
    return float(value)


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Norgate raw-D1 {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Norgate raw-D1 {label} is invalid") from exc


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

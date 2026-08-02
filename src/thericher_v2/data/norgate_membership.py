"""Host-only, external Norgate membership-matrix snapshot construction.

The snapshot keeps a date-less candidate union separate from sparse per-symbol
membership rows. It is not a direct historical-universe list or a research
input.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib
import io
import json
import os
import shutil
import sys
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
DEFAULT_NORGATE_MEMBERSHIP_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "norgate_membership"
    / "canonical"
    / "sp500_current_past"
)
NORGATE_WATCHLIST_NAME = "S&P 500 Current & Past"
NORGATE_INDEX_NAME = "S&P 500"
EXPECTED_CANDIDATE_COUNT = 541
_SNAPSHOT_SUFFIX = "-norgate-sp500-membership-r1"
_CANDIDATE_FILE = "candidate_union.csv"
_MATRIX_FILE = "membership_matrix.csv.gz"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_CANDIDATE_COLUMNS = ("candidate_rank", "symbol")
_MATRIX_COLUMNS = ("candidate_rank", "symbol", "date", "index_constituent")


class NorgateMembershipSnapshotError(ValueError):
    """A masked, fail-closed host-only Norgate membership failure."""


@dataclass(frozen=True, slots=True)
class NorgateMembershipSnapshotResult:
    """Non-secret facts from one immutable Norgate membership snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    candidate_count: int
    membership_row_count: int
    actual_start: date
    actual_end: date
    package_version: str
    free_percent: float


@dataclass(frozen=True, slots=True)
class _MembershipRow:
    candidate_rank: int
    symbol: str
    session_date: date
    index_constituent: bool


def default_norgate_sp500_membership_snapshot_dir(retrieval_date: date) -> Path:
    """Return a dated external destination; callers still get overwrite protection."""

    return DEFAULT_NORGATE_MEMBERSHIP_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def build_norgate_sp500_membership_snapshot(
    *,
    destination: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    expected_candidate_count: int = EXPECTED_CANDIDATE_COUNT,
    client_loader: Callable[[], Any] | None = None,
    platform_name: str = sys.platform,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateMembershipSnapshotResult:
    """Build one sparse external snapshot after validating every source series.

    ``requested_end`` is passed through to the official package as its explicit
    end-date argument. The manifest distinguishes this request from the sparse
    actual coverage returned for the candidate union.
    """

    _validate_window(requested_start, requested_end)
    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    destination_path, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    if platform_name != "win32":
        raise NorgateMembershipSnapshotError("Norgate membership snapshot requires Windows")
    if expected_candidate_count <= 0:
        raise ValueError("expected_candidate_count must be positive")

    loader = client_loader or _load_norgatedata
    client = _load_client(loader)
    candidates = _load_candidates(client, expected_candidate_count=expected_candidate_count)
    rows, coverage = _load_membership_rows(
        client,
        candidates=candidates,
        requested_start=requested_start,
        requested_end=requested_end,
    )
    package_version = _package_version(client)

    candidate_bytes = _candidate_csv_bytes(candidates)
    matrix_bytes = _gzip_bytes(_matrix_csv_bytes(rows))
    candidate_hash = _sha256(candidate_bytes)
    dataset_hash = _sha256(matrix_bytes)
    retention_bytes = _retention_marker_bytes()
    retention_hash = _sha256(retention_bytes)
    manifest = _manifest(
        destination=destination_path,
        market_data_root=root,
        candidate_hash=candidate_hash,
        candidate_size=len(candidate_bytes),
        dataset_hash=dataset_hash,
        matrix_size=len(matrix_bytes),
        retention_hash=retention_hash,
        retention_size=len(retention_bytes),
        candidate_count=len(candidates),
        membership_row_count=len(rows),
        requested_start=requested_start,
        requested_end=requested_end,
        retrieved_at_utc=retrieved_at,
        package_version=package_version,
        coverage=coverage,
        free_percent=free_percent,
        expected_candidate_count=expected_candidate_count,
    )
    manifest_bytes = _json_bytes(manifest)
    manifest_hash = _sha256(manifest_bytes)

    staging = _create_staging_directory(destination_path)
    try:
        (staging / _CANDIDATE_FILE).write_bytes(candidate_bytes)
        (staging / _MATRIX_FILE).write_bytes(matrix_bytes)
        (staging / _RETENTION_FILE).write_bytes(retention_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        staged = _verify_snapshot(
            staging,
            market_data_root=market_data_root,
            repo_root=repo_root,
            expected_dataset_id=_dataset_id(destination_path),
            require_snapshot_name=False,
        )
        if (
            staged.dataset_hash != dataset_hash
            or staged.manifest_hash != manifest_hash
            or staged.candidate_count != len(candidates)
            or staged.membership_row_count != len(rows)
        ):
            raise ValueError("Norgate membership staged snapshot is inconsistent")
        os.rename(staging, destination_path)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return verify_norgate_sp500_membership_snapshot(
        destination_path,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def verify_norgate_sp500_membership_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateMembershipSnapshotResult:
    """Reattest one external snapshot without loading Norgate or network data."""

    return _verify_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
        expected_dataset_id=None,
        require_snapshot_name=True,
    )


def load_verified_norgate_sp500_membership_scope(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> tuple[NorgateMembershipSnapshotResult, tuple[str, ...]]:
    """Return one verified snapshot together with its ordered candidate scope."""

    result = verify_norgate_sp500_membership_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return result, _load_candidate_union_from_verified_snapshot(result)


def load_verified_norgate_sp500_candidate_union(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> tuple[str, ...]:
    """Load only the hash-attested candidate scope from a verified snapshot."""

    _result, candidates = load_verified_norgate_sp500_membership_scope(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return candidates


def _load_candidate_union_from_verified_snapshot(
    result: NorgateMembershipSnapshotResult,
) -> tuple[str, ...]:
    try:
        manifest = json.loads((result.snapshot_dir / _MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate membership candidate manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Norgate membership candidate manifest is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Norgate membership candidate files are invalid")
    candidate_bytes = _validate_file(
        result.snapshot_dir,
        files.get("candidate_union"),
        expected_name=_CANDIDATE_FILE,
        label="candidate union",
    )
    try:
        reader = csv.DictReader(io.StringIO(candidate_bytes.decode("utf-8"), newline=""))
        fieldnames = tuple(reader.fieldnames or ())
        rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate membership candidate union is invalid") from exc
    if fieldnames != _CANDIDATE_COLUMNS or len(rows) != result.candidate_count:
        raise ValueError("Norgate membership candidate union is invalid")
    candidates: list[str] = []
    for expected_rank, row in enumerate(rows, start=1):
        try:
            rank = int(row.get("candidate_rank", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError("Norgate membership candidate rank is invalid") from exc
        if rank != expected_rank:
            raise ValueError("Norgate membership candidate rank is invalid")
        candidates.append(_candidate_symbol(row.get("symbol")))
    if len(set(candidates)) != len(candidates):
        raise ValueError("Norgate membership candidate union has duplicates")
    return tuple(candidates)


def _verify_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    expected_dataset_id: str | None,
    require_snapshot_name: bool,
) -> NorgateMembershipSnapshotResult:
    snapshot, _root = _validate_existing_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
        require_snapshot_name=require_snapshot_name,
    )
    try:
        manifest_bytes = (snapshot / _MANIFEST_FILE).read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Norgate membership manifest is missing") from exc
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate membership manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Norgate membership manifest must be an object")
    if (manifest.get("schema_version"), manifest.get("kind")) != (
        1,
        "norgate_sp500_current_past_membership_matrix",
    ):
        raise ValueError("Norgate membership manifest schema is invalid")
    dataset_id = expected_dataset_id or _dataset_id(snapshot)
    if manifest.get("dataset_id") != dataset_id:
        raise ValueError("Norgate membership dataset identity is inconsistent")
    scope = manifest.get("scope")
    if not isinstance(scope, dict) or any(
        scope.get(key) is not False
        for key in (
            "direct_historical_universe_list",
            "publication_time_proven",
            "pit_eligible",
            "campaign_eligible",
            "model_eligible",
            "ranking_eligible",
            "sealed_holdout_eligible",
        )
    ):
        raise ValueError("Norgate membership scope must stay ineligible")

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Norgate membership manifest is missing file lineage")
    candidate_bytes = _validate_file(
        snapshot,
        files.get("candidate_union"),
        expected_name=_CANDIDATE_FILE,
        label="candidate union",
    )
    matrix_bytes = _validate_file(
        snapshot,
        files.get("membership_matrix"),
        expected_name=_MATRIX_FILE,
        label="membership matrix",
    )
    _validate_file(
        snapshot,
        files.get("retention_marker"),
        expected_name=_RETENTION_FILE,
        label="retention marker",
    )
    candidate_count = _csv_row_count(candidate_bytes, _CANDIDATE_COLUMNS)
    membership_count = _gzip_csv_row_count(matrix_bytes, _MATRIX_COLUMNS)
    if candidate_count != manifest.get("candidate_count"):
        raise ValueError("Norgate membership candidate count is inconsistent")
    if membership_count != manifest.get("membership_row_count"):
        raise ValueError("Norgate membership row count is inconsistent")

    actual_window = manifest.get("actual_sparse_date_window")
    if not isinstance(actual_window, dict):
        raise ValueError("Norgate membership actual window is missing")
    actual_start = _date_value(actual_window.get("start"), "actual start")
    actual_end = _date_value(actual_window.get("end"), "actual end")
    if actual_end < actual_start:
        raise ValueError("Norgate membership actual window is invalid")
    package = manifest.get("package")
    if not isinstance(package, dict):
        raise ValueError("Norgate membership package metadata is missing")
    package_version = _text(package.get("version"), "package version")
    storage = manifest.get("storage")
    if not isinstance(storage, dict) or not isinstance(storage.get("free_percent"), (int, float)):
        raise ValueError("Norgate membership storage metadata is missing")
    return NorgateMembershipSnapshotResult(
        snapshot_dir=snapshot,
        dataset_id=dataset_id,
        dataset_hash=_required_sha256(manifest.get("dataset_hash"), "dataset hash"),
        manifest_hash=_sha256(manifest_bytes),
        candidate_count=candidate_count,
        membership_row_count=membership_count,
        actual_start=actual_start,
        actual_end=actual_end,
        package_version=package_version,
        free_percent=float(storage["free_percent"]),
    )


def _load_norgatedata() -> Any:
    return importlib.import_module("norgatedata")


def _load_client(loader: Callable[[], Any]) -> Any:
    try:
        client = loader()
        _ = client.PaddingType.NONE
        _ = client.watchlist_symbols
        _ = client.index_constituent_timeseries
    except Exception as exc:
        raise NorgateMembershipSnapshotError("Norgate membership data is unavailable") from exc
    return client


def _load_candidates(client: Any, *, expected_candidate_count: int) -> tuple[str, ...]:
    try:
        raw_candidates = client.watchlist_symbols(NORGATE_WATCHLIST_NAME)
    except Exception as exc:
        raise NorgateMembershipSnapshotError("Norgate candidate union is unavailable") from exc
    if not isinstance(raw_candidates, (list, tuple)):
        raise ValueError("Norgate candidate union must be a list")
    candidates = tuple(sorted(_candidate_symbol(value) for value in raw_candidates))
    if len(candidates) != expected_candidate_count:
        raise ValueError("Norgate candidate count differs from the observed tripwire")
    if len(set(candidates)) != len(candidates):
        raise ValueError("Norgate candidate union has duplicates")
    return candidates


def _load_membership_rows(
    client: Any,
    *,
    candidates: tuple[str, ...],
    requested_start: date,
    requested_end: date,
) -> tuple[tuple[_MembershipRow, ...], dict[str, int | str | bool]]:
    rows: list[_MembershipRow] = []
    per_symbol_counts: list[int] = []
    actual_start: date | None = None
    actual_end: date | None = None
    for candidate_rank, symbol in enumerate(candidates, start=1):
        try:
            response = client.index_constituent_timeseries(
                symbol,
                NORGATE_INDEX_NAME,
                padding_setting=client.PaddingType.NONE,
                start_date=requested_start.isoformat(),
                end_date=requested_end.isoformat(),
                limit=-1,
                timeseriesformat="numpy-recarray",
            )
        except Exception as exc:
            raise NorgateMembershipSnapshotError(
                "Norgate membership series is unavailable"
            ) from exc
        series = _parse_membership_series(
            response,
            candidate_rank=candidate_rank,
            symbol=symbol,
            requested_start=requested_start,
            requested_end=requested_end,
        )
        if not series:
            raise ValueError("Norgate membership series is empty")
        per_symbol_counts.append(len(series))
        rows.extend(series)
        series_start = series[0].session_date
        series_end = series[-1].session_date
        actual_start = min(actual_start, series_start) if actual_start else series_start
        actual_end = max(actual_end, series_end) if actual_end else series_end
    if actual_start is None or actual_end is None:
        raise ValueError("Norgate membership matrix has no rows")
    return tuple(rows), {
        "start": actual_start.isoformat(),
        "end": actual_end.isoformat(),
        "per_symbol_row_count_min": min(per_symbol_counts),
        "per_symbol_row_count_max": max(per_symbol_counts),
        "uneven_per_symbol_coverage_observed": len(set(per_symbol_counts)) > 1,
    }


def _parse_membership_series(
    response: Any,
    *,
    candidate_rank: int,
    symbol: str,
    requested_start: date,
    requested_end: date,
) -> tuple[_MembershipRow, ...]:
    fields = tuple(getattr(getattr(response, "dtype", None), "names", ()) or ())
    if "Date" not in fields or "Index Constituent" not in fields:
        raise ValueError("Norgate membership response has required fields missing")
    rows: list[_MembershipRow] = []
    previous_date: date | None = None
    for source_row in response:
        session_date = _session_date(_row_value(source_row, "Date"))
        if session_date < requested_start or session_date > requested_end:
            raise ValueError("Norgate membership response is outside the requested window")
        if previous_date is not None and session_date <= previous_date:
            raise ValueError("Norgate membership response must be strictly ordered")
        rows.append(
            _MembershipRow(
                candidate_rank=candidate_rank,
                symbol=symbol,
                session_date=session_date,
                index_constituent=_membership_flag(_row_value(source_row, "Index Constituent")),
            )
        )
        previous_date = session_date
    return tuple(rows)


def _validate_window(requested_start: date, requested_end: date) -> None:
    if isinstance(requested_start, datetime) or isinstance(requested_end, datetime):
        raise ValueError("Norgate membership dates must not include a time")
    if requested_end < requested_start:
        raise ValueError("Norgate membership end date must not precede start date")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root).resolve()
    if not root.is_dir():
        raise ValueError("Norgate market-data root must exist")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Norgate membership destination already exists")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Norgate membership destination must stay under market data")
    if repo_root is not None and target.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Norgate membership destination must stay outside Git")
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Norgate membership destination must use the required snapshot name")
    return target, root


def _validate_existing_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    require_snapshot_name: bool,
) -> tuple[Path, Path]:
    root = Path(market_data_root).resolve()
    snapshot = Path(snapshot_dir)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("Norgate membership snapshot must be a directory")
    snapshot = snapshot.resolve()
    if not snapshot.is_relative_to(root):
        raise ValueError("Norgate membership snapshot must stay under market data")
    if (
        repo_root is not None
        and snapshot.is_relative_to(Path(repo_root).resolve())
        and not root.is_mount()
    ):
        raise ValueError("Norgate membership snapshot must stay outside Git")
    if require_snapshot_name and (
        not snapshot.name.startswith("snapshot=") or not snapshot.name.endswith(_SNAPSHOT_SUFFIX)
    ):
        raise ValueError("Norgate membership snapshot must use the required snapshot name")
    return snapshot, root


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Norgate membership storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Norgate membership storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn(
            "Norgate membership storage is below the warning free-space floor",
            stacklevel=2,
        )
    return free_percent


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".staging-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _candidate_symbol(value: Any) -> str:
    candidate = str(value).strip().upper()
    if not candidate:
        raise ValueError("Norgate candidate union has an empty symbol")
    return candidate


def _row_value(row: Any, field_name: str) -> Any:
    try:
        return row[field_name]
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("Norgate membership response has an unreadable field") from exc


def _session_date(value: Any) -> date:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, bytes):
        value = value.decode("ascii")
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValueError("Norgate membership response has an invalid date") from exc
    raise ValueError("Norgate membership response has an invalid date")


def _membership_flag(value: Any) -> bool:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and value in (0.0, 1.0):
        return bool(value)
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        return value.strip() == "1"
    raise ValueError("Norgate membership response must use binary membership values")


def _candidate_csv_bytes(candidates: tuple[str, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_CANDIDATE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for candidate_rank, symbol in enumerate(candidates, start=1):
        writer.writerow({"candidate_rank": candidate_rank, "symbol": symbol})
    return buffer.getvalue().encode("utf-8")


def _matrix_csv_bytes(rows: tuple[_MembershipRow, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_MATRIX_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "candidate_rank": row.candidate_rank,
                "symbol": row.symbol,
                "date": row.session_date.isoformat(),
                "index_constituent": int(row.index_constituent),
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
        "This directory contains Norgate-origin data.\n"
        "If the trial or subscription ends and the Norgate EULA requires deletion,\n"
        "the operator must delete this snapshot directory and its derived copies.\n"
        "This marker records scope only; it does not perform or prove deletion.\n"
        "It does not authorize deletion of C:\\ProgramData\\Norgate Data.\n"
    ).encode("ascii")


def _manifest(
    *,
    destination: Path,
    market_data_root: Path,
    candidate_hash: str,
    candidate_size: int,
    dataset_hash: str,
    matrix_size: int,
    retention_hash: str,
    retention_size: int,
    candidate_count: int,
    membership_row_count: int,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    package_version: str,
    coverage: dict[str, int | str | bool],
    free_percent: float,
    expected_candidate_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "norgate_sp500_current_past_membership_matrix",
        "dataset_id": _dataset_id(destination),
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "candidate_count": candidate_count,
        "membership_row_count": membership_row_count,
        "candidate_count_tripwire": {
            "expected_from_capability_audit": expected_candidate_count,
            "matched": candidate_count == expected_candidate_count,
            "stability_proof": False,
        },
        "source_contract": {
            "provider": "Norgate Data",
            "watchlist_name": NORGATE_WATCHLIST_NAME,
            "index_name": NORGATE_INDEX_NAME,
            "candidate_method": "watchlist_symbols",
            "membership_method": "index_constituent_timeseries",
            "padding_setting": "NONE",
            "timeseriesformat": "numpy-recarray",
            "requested_window": {
                "start": requested_start.isoformat(),
                "end": requested_end.isoformat(),
                "end_semantics": "passed through as the official client end_date argument",
            },
            "actual_sparse_date_window": coverage,
        },
        "actual_sparse_date_window": {"start": coverage["start"], "end": coverage["end"]},
        "package": {"name": "norgatedata", "version": package_version},
        "files": {
            "candidate_union": {
                "path": _CANDIDATE_FILE,
                "sha256": candidate_hash,
                "size_bytes": candidate_size,
                "columns": list(_CANDIDATE_COLUMNS),
                "format": "csv",
            },
            "membership_matrix": {
                "path": _MATRIX_FILE,
                "sha256": dataset_hash,
                "size_bytes": matrix_size,
                "columns": list(_MATRIX_COLUMNS),
                "format": "csv.gz",
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
            "scope": "this snapshot directory and derived copies only",
        },
        "scope": {
            "direct_historical_universe_list": False,
            "publication_time_proven": False,
            "pit_eligible": False,
            "campaign_eligible": False,
            "model_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "limitations": [
            "The candidate union has no as-of date.",
            "Sparse membership rows do not imply zero membership on missing dates.",
            "Membership values do not establish source publication or decision-time availability.",
            "The snapshot does not prove candidate-union completeness or delisting coverage.",
        ],
    }


def _validate_file(
    snapshot: Path,
    metadata: object,
    *,
    expected_name: str,
    label: str,
) -> bytes:
    if not isinstance(metadata, dict) or metadata.get("path") != expected_name:
        raise ValueError(f"Norgate membership {label} lineage is invalid")
    expected_hash = _required_sha256(metadata.get("sha256"), f"{label} hash")
    path = snapshot / expected_name
    if path.is_symlink() or not path.resolve().is_relative_to(snapshot):
        raise ValueError(f"Norgate membership {label} path is invalid")
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"Norgate membership {label} is missing") from exc
    if _sha256(data) != expected_hash:
        raise ValueError(f"Norgate membership {label} hash mismatch")
    if metadata.get("size_bytes") != len(data):
        raise ValueError(f"Norgate membership {label} size is inconsistent")
    return data


def _csv_row_count(data: bytes, expected_columns: tuple[str, ...]) -> int:
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""))
        header = tuple(next(reader))
    except (StopIteration, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate membership CSV is invalid") from exc
    if header != expected_columns:
        raise ValueError("Norgate membership CSV schema is invalid")
    return sum(1 for _row in reader)


def _gzip_csv_row_count(data: bytes, expected_columns: tuple[str, ...]) -> int:
    try:
        return _csv_row_count(gzip.decompress(data), expected_columns)
    except OSError as exc:
        raise ValueError("Norgate membership matrix compression is invalid") from exc


def _dataset_id(snapshot_dir: Path) -> str:
    return f"us_equities.norgate_sp500_current_past_membership.1d.{Path(snapshot_dir).name}"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _required_sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 71 or not text.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in text[7:]
    ):
        raise ValueError(f"Norgate membership {label} is invalid")
    return text


def _text(value: object, label: str) -> str:
    text = str(value or "")
    if not text or text != text.strip():
        raise ValueError(f"Norgate membership {label} is required")
    return text


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Norgate membership {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Norgate membership {label} is invalid") from exc


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _package_version(client: Any) -> str:
    return str(getattr(client, "__version__", "unknown")).strip() or "unknown"

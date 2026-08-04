"""Build and verify source-marker exclusion sidecars for Tiingo ETF D1 snapshots."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import uuid
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .tiingo_etf_daily import (
    DEFAULT_MARKET_DATA_ROOT,
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailySnapshot,
    load_verified_tiingo_etf_d1_snapshot,
)

DEFAULT_TIINGO_ETF_D1_EVENT_EXCLUSION_ROOT = (
    DEFAULT_MARKET_DATA_ROOT / "us_equities" / "tiingo_etf_daily" / "event_marker_exclusions"
)
TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION = "tiingo-etf-d1-event-exclusions-r1"

_EXCLUSION_FILE = "event_marker_exclusions.csv"
_MANIFEST_FILE = "manifest.json"
_SNAPSHOT_SUFFIX = f"-{TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION}"
_EXCLUSION_COLUMNS = (
    "symbol",
    "source_marker_date",
    "excluded_session_date",
    "reason",
)
_EXCLUSION_REASON = "source_marker_or_adjacent_observed_session"
_LIMITATIONS = (
    "Source markers are exclusion evidence, not verified event timestamps or classifications.",
    "This sidecar does not establish point-in-time, ranking, paper, or sealed-holdout eligibility.",
    "The source-marker mask is retrospective data hygiene and must not become a trading signal.",
)
_SCOPE = {
    "retrospective_research_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "paper_input_eligible": False,
    "sealed_holdout_eligible": False,
    "event_semantics_verified": False,
}
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class TiingoEtfEventExclusionError(RuntimeError):
    """A masked failure while producing a Tiingo marker-exclusion sidecar."""


@dataclass(frozen=True, slots=True)
class TiingoEtfEventExclusion:
    """One source-marker hygiene exclusion without any raw financial values."""

    symbol: str
    source_marker_date: date
    excluded_session_date: date
    reason: str = _EXCLUSION_REASON

    def __post_init__(self) -> None:
        if self.symbol not in TIINGO_ETF_D1_SYMBOLS:
            raise ValueError("Tiingo ETF event exclusion symbol is invalid")
        if (
            type(self.source_marker_date) is not date
            or type(self.excluded_session_date) is not date
        ):
            raise ValueError("Tiingo ETF event exclusion date is invalid")
        if self.reason != _EXCLUSION_REASON:
            raise ValueError("Tiingo ETF event exclusion reason is invalid")


@dataclass(frozen=True, slots=True)
class TiingoEtfEventExclusionResult:
    """Source-safe identity and aggregate facts for one immutable sidecar."""

    snapshot_dir: Path
    parent_snapshot_dir: Path
    parent_dataset_id: str
    parent_dataset_hash: str
    parent_manifest_hash: str
    parent_raw_hashes: Mapping[str, str]
    manifest_hash: str
    marker_count: int
    excluded_session_count: int
    session_counts: Mapping[str, int]
    free_percent: float

    def __post_init__(self) -> None:
        for label, value in (
            ("parent_dataset_hash", self.parent_dataset_hash),
            ("parent_manifest_hash", self.parent_manifest_hash),
            ("manifest_hash", self.manifest_hash),
        ):
            _require_sha256(value, label)
        if not self.parent_dataset_id:
            raise ValueError("Tiingo ETF event exclusion parent dataset id is invalid")
        if self.marker_count < 0 or self.excluded_session_count < 0:
            raise ValueError("Tiingo ETF event exclusion counts are invalid")
        if set(self.parent_raw_hashes) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("Tiingo ETF event exclusion raw hashes are incomplete")
        if set(self.session_counts) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("Tiingo ETF event exclusion session counts are incomplete")
        for source_hash in self.parent_raw_hashes.values():
            _require_sha256(source_hash, "parent raw hash")
        if any(not isinstance(value, int) or value < 1 for value in self.session_counts.values()):
            raise ValueError("Tiingo ETF event exclusion session counts are invalid")
        if not isinstance(self.free_percent, (int, float)) or self.free_percent < 15:
            raise ValueError("Tiingo ETF event exclusion storage fact is invalid")
        object.__setattr__(
            self, "parent_raw_hashes", MappingProxyType(dict(self.parent_raw_hashes))
        )
        object.__setattr__(self, "session_counts", MappingProxyType(dict(self.session_counts)))


def default_tiingo_etf_d1_event_exclusion_snapshot_dir(retrieved_at_utc: datetime) -> Path:
    """Return a unique external destination for one immutable exclusion sidecar."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    label = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_TIINGO_ETF_D1_EVENT_EXCLUSION_ROOT / f"snapshot={label}{_SNAPSHOT_SUFFIX}"


def build_tiingo_etf_d1_event_exclusion_snapshot(
    *,
    destination: Path,
    parent_snapshot: Path,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoEtfEventExclusionResult:
    """Create an external-only sidecar after reattesting the immutable parent."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    loaded = _reattest_parent_snapshot(
        parent_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    exclusions = _derive_exclusions(loaded)
    exclusion_bytes = _exclusion_csv_bytes(exclusions)
    manifest = _manifest(
        destination=target,
        market_data_root=root,
        loaded=loaded,
        exclusions=exclusions,
        exclusion_hash=_sha256(exclusion_bytes),
        exclusion_size=len(exclusion_bytes),
        retrieved_at=retrieved_at,
        free_percent=free_percent,
    )
    manifest_bytes = _json_bytes(manifest)
    staging = _create_staging_directory(target)
    renamed = False
    try:
        (staging / _EXCLUSION_FILE).write_bytes(exclusion_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        _validate_written_sidecar(
            staging,
            manifest,
            loaded=loaded,
            exclusions=exclusions,
            identity_snapshot=target,
        )
        os.replace(staging, target)
        renamed = True
        return verify_tiingo_etf_d1_event_exclusion_snapshot(
            target,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
    except Exception:
        if renamed:
            _remove_failed_destination(target)
        elif staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_tiingo_etf_d1_event_exclusion_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoEtfEventExclusionResult:
    """Recompute and reattest one sidecar without credentials or network access."""

    snapshot, _root = _validate_existing_sidecar(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_sidecar_contents(snapshot)
    manifest_bytes = _read_file(snapshot, _MANIFEST_FILE, "manifest")
    manifest = _json_mapping(manifest_bytes, "manifest")
    _validate_manifest_header(manifest, snapshot=snapshot)
    parent_document = _mapping(manifest.get("parent_snapshot"), "parent snapshot")
    parent_path = Path(_required_text(parent_document.get("snapshot_dir"), "parent snapshot path"))
    loaded = _reattest_parent_snapshot(
        parent_path,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    exclusions = _derive_exclusions(loaded)
    details = _validate_written_sidecar(
        snapshot,
        manifest,
        loaded=loaded,
        exclusions=exclusions,
    )
    parent = loaded.snapshot
    return TiingoEtfEventExclusionResult(
        snapshot_dir=snapshot,
        parent_snapshot_dir=parent.snapshot_dir,
        parent_dataset_id=parent.dataset_id,
        parent_dataset_hash=parent.dataset_hash,
        parent_manifest_hash=parent.manifest_hash,
        parent_raw_hashes=parent.raw_hashes,
        manifest_hash=_sha256(manifest_bytes),
        marker_count=details["marker_count"],
        excluded_session_count=details["excluded_session_count"],
        session_counts=parent.session_counts,
        free_percent=details["free_percent"],
    )


def _reattest_parent_snapshot(
    parent_snapshot: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> LoadedTiingoEtfDailySnapshot:
    parent, _root = _validate_existing_parent(
        parent_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    manifest = _json_mapping(
        _read_file(parent, _MANIFEST_FILE, "parent manifest"), "parent manifest"
    )
    dataset_id = _required_text(manifest.get("dataset_id"), "parent dataset id")
    dataset_hash = _required_sha256(manifest.get("dataset_hash"), "parent dataset hash")
    manifest_hash = _sha256(_read_file(parent, _MANIFEST_FILE, "parent manifest"))
    loaded = load_verified_tiingo_etf_d1_snapshot(
        parent,
        dataset_id=dataset_id,
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=manifest_hash,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    if (
        loaded.snapshot.dataset_id != dataset_id
        or loaded.snapshot.dataset_hash != dataset_hash
        or loaded.snapshot.manifest_hash != manifest_hash
    ):
        raise ValueError("Tiingo ETF event exclusion parent identity is inconsistent")
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        marker_count = sum(
            row.div_cash != 0 or row.split_factor != 1 for row in loaded.rows_by_symbol[symbol]
        )
        if marker_count != loaded.snapshot.event_session_counts[symbol]:
            raise ValueError("Tiingo ETF event exclusion parent marker count is inconsistent")
    return loaded


def _derive_exclusions(
    loaded: LoadedTiingoEtfDailySnapshot,
) -> tuple[TiingoEtfEventExclusion, ...]:
    exclusions: list[TiingoEtfEventExclusion] = []
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = loaded.rows_by_symbol[symbol]
        positions = {row.session_date: index for index, row in enumerate(rows)}
        marker_dates = tuple(
            row.session_date for row in rows if row.div_cash != 0 or row.split_factor != 1
        )
        if marker_dates != tuple(sorted(set(marker_dates))):
            raise ValueError("Tiingo ETF event exclusion parent marker dates are invalid")
        for marker_date in marker_dates:
            marker_index = positions.get(marker_date)
            if marker_index is None:
                raise ValueError("Tiingo ETF event exclusion marker is not an observed session")
            for excluded_index in range(max(0, marker_index - 1), min(len(rows), marker_index + 2)):
                exclusions.append(
                    TiingoEtfEventExclusion(
                        symbol=symbol,
                        source_marker_date=marker_date,
                        excluded_session_date=rows[excluded_index].session_date,
                    )
                )
    result = tuple(exclusions)
    if result != tuple(sorted(result, key=_exclusion_sort_key)):
        raise ValueError("Tiingo ETF event exclusions are not deterministic")
    return result


def _manifest(
    *,
    destination: Path,
    market_data_root: Path,
    loaded: LoadedTiingoEtfDailySnapshot,
    exclusions: tuple[TiingoEtfEventExclusion, ...],
    exclusion_hash: str,
    exclusion_size: int,
    retrieved_at: datetime,
    free_percent: float,
) -> dict[str, object]:
    parent = loaded.snapshot
    marker_counts = _marker_counts(exclusions)
    exclusion_counts = _exclusion_counts(exclusions)
    return {
        "schema_version": 1,
        "kind": "tiingo_etf_d1_event_marker_exclusions",
        "version": TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION,
        "dataset_id": _dataset_id(destination),
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at),
        "symbols": list(TIINGO_ETF_D1_SYMBOLS),
        "parent_snapshot": _parent_document(parent),
        "source_marker_evidence": {
            "source_fields": ["div_cash", "split_factor"],
            "marker_rule": "div_cash_nonzero_or_split_factor_not_one",
            "marker_exclusion_rule": "marker_session_plus_adjacent_observed_sessions",
            "event_semantics_verified": False,
            "per_symbol": {
                symbol: {
                    "source_marker_count": marker_counts[symbol],
                    "excluded_session_count": exclusion_counts[symbol],
                }
                for symbol in TIINGO_ETF_D1_SYMBOLS
            },
            "observed_source_marker_count": sum(marker_counts.values()),
            "exclusion_row_count": len(exclusions),
        },
        "files": {
            "event_marker_exclusions": {
                "path": _EXCLUSION_FILE,
                "sha256": exclusion_hash,
                "size_bytes": exclusion_size,
                "format": "csv",
                "columns": list(_EXCLUSION_COLUMNS),
            }
        },
        "storage": {
            "root": str(market_data_root),
            "free_percent_before_write": free_percent,
            "warning_floor_percent": 20,
            "hard_floor_percent": 15,
        },
        "scope": _SCOPE,
        "limitations": list(_LIMITATIONS),
    }


def _parent_document(parent: TiingoEtfDailySnapshot) -> dict[str, object]:
    return {
        "snapshot_dir": str(parent.snapshot_dir),
        "dataset_id": parent.dataset_id,
        "canonical_dataset_hash": parent.dataset_hash,
        "manifest_hash": parent.manifest_hash,
        "raw_hashes": dict(parent.raw_hashes),
        "canonical_raw_normalized_equivalence_reattested": True,
        "session_counts": dict(parent.session_counts),
    }


def _validate_manifest_header(manifest: Mapping[str, object], *, snapshot: Path) -> None:
    if (
        set(manifest)
        != {
            "schema_version",
            "kind",
            "version",
            "dataset_id",
            "immutable_snapshot",
            "retrieved_at_utc",
            "symbols",
            "parent_snapshot",
            "source_marker_evidence",
            "files",
            "storage",
            "scope",
            "limitations",
        }
        or (
            manifest.get("schema_version") != 1
            or manifest.get("kind") != "tiingo_etf_d1_event_marker_exclusions"
            or manifest.get("version") != TIINGO_ETF_D1_EVENT_EXCLUSION_VERSION
            or manifest.get("dataset_id") != _dataset_id(snapshot)
            or manifest.get("immutable_snapshot") is not True
            or manifest.get("symbols") != list(TIINGO_ETF_D1_SYMBOLS)
            or manifest.get("scope") != _SCOPE
        )
    ):
        raise ValueError("Tiingo ETF event exclusion manifest identity is invalid")
    _utc_datetime(_datetime_value(manifest.get("retrieved_at_utc")), "retrieved_at_utc")
    limitations = manifest.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(value, str) for value in limitations
    ):
        raise ValueError("Tiingo ETF event exclusion limitations are invalid")
    if limitations != list(_LIMITATIONS):
        raise ValueError("Tiingo ETF event exclusion limitations are invalid")
    _validate_storage_document(manifest.get("storage"))


def _validate_written_sidecar(
    snapshot: Path,
    manifest: Mapping[str, object],
    *,
    loaded: LoadedTiingoEtfDailySnapshot,
    exclusions: tuple[TiingoEtfEventExclusion, ...],
    identity_snapshot: Path | None = None,
) -> dict[str, int | float]:
    _validate_sidecar_contents(snapshot)
    _validate_manifest_header(manifest, snapshot=identity_snapshot or snapshot)
    parent = _mapping(manifest.get("parent_snapshot"), "parent snapshot")
    if parent != _parent_document(loaded.snapshot):
        raise ValueError("Tiingo ETF event exclusion parent evidence is invalid")
    evidence = _mapping(manifest.get("source_marker_evidence"), "source marker evidence")
    expected_evidence = _source_marker_evidence(exclusions)
    if evidence != expected_evidence:
        raise ValueError("Tiingo ETF event exclusion source marker evidence is invalid")
    files = _mapping(manifest.get("files"), "files")
    expected_file = _mapping(files.get("event_marker_exclusions"), "event marker exclusions")
    if (
        set(files) != {"event_marker_exclusions"}
        or expected_file.get("path") != _EXCLUSION_FILE
        or expected_file.get("format") != "csv"
        or expected_file.get("columns") != list(_EXCLUSION_COLUMNS)
    ):
        raise ValueError("Tiingo ETF event exclusion file contract is invalid")
    exclusion_bytes = _read_file(snapshot, _EXCLUSION_FILE, "event marker exclusions")
    if (
        _required_sha256(expected_file.get("sha256"), "event marker exclusion hash")
        != _sha256(exclusion_bytes)
        or expected_file.get("size_bytes") != len(exclusion_bytes)
    ):
        raise ValueError("Tiingo ETF event exclusion hash mismatch")
    parsed = _parse_exclusions(exclusion_bytes)
    if parsed != exclusions:
        raise ValueError("Tiingo ETF event exclusions are inconsistent with the parent")
    storage = _mapping(manifest.get("storage"), "storage")
    return {
        "marker_count": int(evidence["observed_source_marker_count"]),
        "excluded_session_count": len(parsed),
        "free_percent": float(storage["free_percent_before_write"]),
    }


def _source_marker_evidence(
    exclusions: tuple[TiingoEtfEventExclusion, ...],
) -> dict[str, object]:
    marker_counts = _marker_counts(exclusions)
    exclusion_counts = _exclusion_counts(exclusions)
    return {
        "source_fields": ["div_cash", "split_factor"],
        "marker_rule": "div_cash_nonzero_or_split_factor_not_one",
        "marker_exclusion_rule": "marker_session_plus_adjacent_observed_sessions",
        "event_semantics_verified": False,
        "per_symbol": {
            symbol: {
                "source_marker_count": marker_counts[symbol],
                "excluded_session_count": exclusion_counts[symbol],
            }
            for symbol in TIINGO_ETF_D1_SYMBOLS
        },
        "observed_source_marker_count": sum(marker_counts.values()),
        "exclusion_row_count": len(exclusions),
    }


def _marker_counts(exclusions: tuple[TiingoEtfEventExclusion, ...]) -> dict[str, int]:
    return {
        symbol: len(
            {
                exclusion.source_marker_date
                for exclusion in exclusions
                if exclusion.symbol == symbol
            }
        )
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }


def _exclusion_counts(exclusions: tuple[TiingoEtfEventExclusion, ...]) -> dict[str, int]:
    return {
        symbol: sum(exclusion.symbol == symbol for exclusion in exclusions)
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }


def _parse_exclusions(data: bytes) -> tuple[TiingoEtfEventExclusion, ...]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
        fields = tuple(reader.fieldnames or ())
        rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Tiingo ETF event exclusion CSV is invalid") from exc
    if fields != _EXCLUSION_COLUMNS:
        raise ValueError("Tiingo ETF event exclusion CSV schema is invalid")
    exclusions = tuple(
        TiingoEtfEventExclusion(
            symbol=_symbol(row.get("symbol")),
            source_marker_date=_date_value(row.get("source_marker_date"), "source marker date"),
            excluded_session_date=_date_value(
                row.get("excluded_session_date"), "excluded session date"
            ),
            reason=_required_text(row.get("reason"), "exclusion reason"),
        )
        for row in rows
    )
    if exclusions != tuple(sorted(exclusions, key=_exclusion_sort_key)):
        raise ValueError("Tiingo ETF event exclusion CSV ordering is invalid")
    return exclusions


def _exclusion_csv_bytes(exclusions: tuple[TiingoEtfEventExclusion, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_EXCLUSION_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for exclusion in exclusions:
        writer.writerow(
            {
                "symbol": exclusion.symbol,
                "source_marker_date": exclusion.source_marker_date.isoformat(),
                "excluded_session_date": exclusion.excluded_session_date.isoformat(),
                "reason": exclusion.reason,
            }
        )
    return buffer.getvalue().encode("utf-8")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = _validated_market_data_root(market_data_root, repo_root=repo_root)
    target = Path(destination).resolve(strict=False)
    if not target.is_relative_to(root):
        raise ValueError("Tiingo ETF event exclusion destination must remain under market_data")
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Tiingo ETF event exclusion destination name is invalid")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Tiingo ETF event exclusion destination already exists")
    return target, root


def _validate_existing_parent(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = _validated_market_data_root(market_data_root, repo_root=repo_root)
    snapshot = Path(snapshot_dir)
    if snapshot.is_symlink():
        raise ValueError("Tiingo ETF event exclusion parent cannot be a symlink")
    resolved = snapshot.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise ValueError("Tiingo ETF event exclusion parent must remain under market_data")
    if not resolved.name.startswith("snapshot="):
        raise ValueError("Tiingo ETF event exclusion parent name is invalid")
    return resolved, root


def _validate_existing_sidecar(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = _validated_market_data_root(market_data_root, repo_root=repo_root)
    snapshot = Path(snapshot_dir)
    if snapshot.is_symlink():
        raise ValueError("Tiingo ETF event exclusion snapshot cannot be a symlink")
    resolved = snapshot.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(root):
        raise ValueError("Tiingo ETF event exclusion snapshot must remain under market_data")
    if not resolved.name.startswith("snapshot=") or not resolved.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Tiingo ETF event exclusion snapshot name is invalid")
    return resolved, root


def _validated_market_data_root(market_data_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(market_data_root).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Tiingo ETF event exclusion market-data root is invalid")
    if repo_root is not None:
        resolved_repo = Path(repo_root).resolve(strict=True)
        if root.is_relative_to(resolved_repo) and not _is_container_external_mount(
            root, resolved_repo, mount_name="market_data"
        ):
            raise ValueError("Tiingo ETF event exclusion data must stay outside the Git workspace")
    return root


def _validate_sidecar_contents(snapshot: Path) -> None:
    expected = {_MANIFEST_FILE, _EXCLUSION_FILE}
    try:
        entries = tuple(snapshot.iterdir())
    except OSError as exc:
        raise ValueError("Tiingo ETF event exclusion snapshot is unavailable") from exc
    if {entry.name for entry in entries} != expected or any(
        not entry.is_file() or entry.is_symlink() for entry in entries
    ):
        raise ValueError("Tiingo ETF event exclusion snapshot contents are invalid")


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = getattr(usage, "total", 0)
    free = getattr(usage, "free", -1)
    if not isinstance(total, int) or total <= 0 or not isinstance(free, int) or free < 0:
        raise ValueError("Tiingo ETF event exclusion disk usage is invalid")
    free_percent = free * 100 / total
    if free_percent < 15:
        raise TiingoEtfEventExclusionError("Tiingo ETF event exclusion storage floor reached")
    if free_percent < 20:
        warnings.warn(
            "Tiingo ETF event exclusion storage is below the warning threshold", stacklevel=2
        )
    return free_percent


def _validate_storage_document(value: object) -> None:
    storage = _mapping(value, "storage")
    if (
        set(storage)
        != {
            "root",
            "free_percent_before_write",
            "warning_floor_percent",
            "hard_floor_percent",
        }
        or not isinstance(storage.get("root"), str)
        or _nonnegative_float(storage.get("free_percent_before_write")) < 15
        or storage.get("warning_floor_percent") != 20
        or storage.get("hard_floor_percent") != 15
    ):
        raise ValueError("Tiingo ETF event exclusion storage evidence is invalid")


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".stage-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _remove_failed_destination(destination: Path) -> None:
    if destination.is_dir() and not destination.is_symlink():
        rejected = destination.parent / f".rejected-{destination.name}-{uuid.uuid4().hex}"
        try:
            os.replace(destination, rejected)
        except OSError:
            shutil.rmtree(destination, ignore_errors=True)


def _read_file(snapshot: Path, name: str, label: str) -> bytes:
    path = snapshot / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Tiingo ETF event exclusion {label} is unavailable")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(snapshot):
        raise ValueError(f"Tiingo ETF event exclusion {label} path is invalid")
    try:
        return resolved.read_bytes()
    except OSError as exc:
        raise ValueError(f"Tiingo ETF event exclusion {label} is unavailable") from exc


def _json_mapping(data: bytes, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid") from exc
    return _mapping(value, label)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid")
    return value


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid")
    return value


def _required_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid")
    _require_sha256(value, label)
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 71 or not value.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in value[7:]
    ):
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid")


def _datetime_value(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Tiingo ETF event exclusion retrieval time is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Tiingo ETF event exclusion retrieval time is invalid") from exc
    return parsed


def _utc_datetime(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"Tiingo ETF event exclusion {label} must be UTC")
    return value.astimezone(UTC)


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Tiingo ETF event exclusion {label} is invalid") from exc


def _symbol(value: object) -> str:
    result = str(value or "").upper()
    if result not in TIINGO_ETF_D1_SYMBOLS:
        raise ValueError("Tiingo ETF event exclusion symbol is invalid")
    return result


def _nonnegative_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("Tiingo ETF event exclusion storage fact is invalid")
    return float(value)


def _exclusion_sort_key(value: TiingoEtfEventExclusion) -> tuple[int, date, date, str]:
    return (
        TIINGO_ETF_D1_SYMBOLS.index(value.symbol),
        value.source_marker_date,
        value.excluded_session_date,
        value.reason,
    )


def _dataset_id(destination: Path) -> str:
    return f"us_equities.tiingo_etf_daily.{destination.name}"


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_container_external_mount(path: Path, repo_root: Path, *, mount_name: str) -> bool:
    container_repo = Path("/app").resolve()
    if repo_root != container_repo:
        return False
    mount_root = container_repo / mount_name
    return path == mount_root or path.is_relative_to(mount_root)

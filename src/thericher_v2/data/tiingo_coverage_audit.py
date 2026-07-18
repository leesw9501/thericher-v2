"""Offline, aggregate-only coverage audit for two Tiingo daily snapshots."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .norgate_candidate_union import DEFAULT_MARKET_DATA_ROOT
from .tiingo_daily_pilot import (
    TiingoDailyPilotResult,
    verify_tiingo_daily_pilot_snapshot,
    verify_tiingo_daily_shard_snapshot,
)

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_TIINGO_COVERAGE_AUDIT_ROOT = (
    DEFAULT_MODEL_ARTIFACT_ROOT / "data-agent" / "tiingo-daily-coverage-audit"
)
TIINGO_COVERAGE_AUDIT_VERSION = "tiingo-daily-coverage-audit-r1"
_SUMMARY_FILE = "summary.json"
_CANONICAL_FILE = "ohlcv_1d.csv.gz"
_SNAPSHOT_SUFFIX = "-tiingo-daily-coverage-audit-r1"
_SCOPE = {
    "private_internal_use_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "model_eligible": False,
    "gpu_eligible": False,
    "paper_trading_eligible": False,
}


@dataclass(frozen=True, slots=True)
class TiingoDailyCoverageAuditInputs:
    """Hash-pinned external inputs for one offline aggregate audit."""

    r1_snapshot_dir: Path
    r1_dataset_hash: str
    r1_manifest_hash: str
    r2_snapshot_dir: Path
    r2_dataset_hash: str
    r2_manifest_hash: str
    candidate_union_hash: str


@dataclass(frozen=True, slots=True)
class TiingoDailyCoverageAuditResult:
    """Non-sensitive facts from one immutable external coverage summary."""

    summary_path: Path
    summary_hash: str
    r1_common_session_count: int
    r2_common_session_count: int
    combined_common_session_count: int
    existing_reference_window_candidate_count: int
    free_percent: float


@dataclass(frozen=True, slots=True)
class _SnapshotCoverage:
    result: TiingoDailyPilotResult
    rank_dates: dict[int, frozenset[date]]
    source_size_bytes: int

    @property
    def common_dates(self) -> frozenset[date]:
        return frozenset(set.intersection(*(set(dates) for dates in self.rank_dates.values())))

    @property
    def row_counts(self) -> tuple[int, ...]:
        return tuple(len(dates) for dates in self.rank_dates.values())


def default_tiingo_daily_coverage_audit_dir(audit_date: date) -> Path:
    """Return the immutable external summary path for this audit revision."""

    if isinstance(audit_date, datetime):
        raise ValueError("Tiingo coverage audit date must not include a time")
    return DEFAULT_TIINGO_COVERAGE_AUDIT_ROOT / (
        f"snapshot={audit_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def run_tiingo_daily_coverage_audit(
    *,
    inputs: TiingoDailyCoverageAuditInputs,
    destination: Path,
    audited_at_utc: datetime,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoDailyCoverageAuditResult:
    """Re-attest external evidence and publish one symbol-private summary."""

    audited_at = _utc_datetime(audited_at_utc, "Tiingo coverage audit time")
    r1_result = verify_tiingo_daily_pilot_snapshot(
        inputs.r1_snapshot_dir,
        expected_dataset_hash=inputs.r1_dataset_hash,
        expected_manifest_hash=inputs.r1_manifest_hash,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    r2_result = verify_tiingo_daily_shard_snapshot(
        inputs.r2_snapshot_dir,
        expected_dataset_hash=inputs.r2_dataset_hash,
        expected_manifest_hash=inputs.r2_manifest_hash,
        predecessor_snapshot_dir=inputs.r1_snapshot_dir,
        expected_predecessor_dataset_hash=inputs.r1_dataset_hash,
        expected_predecessor_manifest_hash=inputs.r1_manifest_hash,
        expected_candidate_union_hash=inputs.candidate_union_hash,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    r1 = _load_coverage(r1_result)
    r2 = _load_coverage(r2_result)
    summary = _summary(inputs=inputs, r1=r1, r2=r2, audited_at=audited_at)
    target, root = _validate_destination(
        destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    summary["artifact_storage"] = {
        "root": str(root),
        "free_percent": free_percent,
        "warning_floor_percent": 20,
        "hard_floor_percent": 15,
    }
    summary_bytes = _json_bytes(summary)
    staging = target.parent / f".stage-{uuid.uuid4().hex}"
    target.parent.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    try:
        (staging / _SUMMARY_FILE).write_bytes(summary_bytes)
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    stored = (target / _SUMMARY_FILE).read_bytes()
    if stored != summary_bytes:
        raise RuntimeError("Tiingo coverage audit summary publication is inconsistent")
    return TiingoDailyCoverageAuditResult(
        summary_path=target / _SUMMARY_FILE,
        summary_hash=_sha256(stored),
        r1_common_session_count=len(r1.common_dates),
        r2_common_session_count=len(r2.common_dates),
        combined_common_session_count=summary["combined"]["common_session_count"],
        existing_reference_window_candidate_count=summary["existing_window_filter"][
            "candidate_count_covering_r2_window"
        ],
        free_percent=free_percent,
    )


def _load_coverage(result: TiingoDailyPilotResult) -> _SnapshotCoverage:
    canonical_bytes = _read_attested_snapshot_file(
        result.snapshot_dir,
        _CANONICAL_FILE,
        expected_hash=result.dataset_hash,
        label="Tiingo coverage audit canonical data",
    )
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(canonical_bytes), mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                fieldnames = tuple(reader.fieldnames or ())
                rows = tuple(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Tiingo coverage audit canonical data is invalid") from exc
    required = {"candidate_rank", "candidate_symbol", "date"}
    if not required.issubset(fieldnames):
        raise ValueError("Tiingo coverage audit canonical columns are invalid")
    rank_dates: dict[int, set[date]] = {}
    for row in rows:
        rank = _rank(row.get("candidate_rank"))
        session = _session_date(row.get("date"))
        dates = rank_dates.setdefault(rank, set())
        if session in dates:
            raise ValueError("Tiingo coverage audit canonical dates are invalid")
        dates.add(session)
    if len(rows) != result.row_count or len(rank_dates) != result.available_count:
        raise ValueError("Tiingo coverage audit canonical counts are inconsistent")
    if not rank_dates:
        raise ValueError("Tiingo coverage audit requires available source rows")
    source_size_bytes = _source_snapshot_size(result.snapshot_dir)
    return _SnapshotCoverage(
        result=result,
        rank_dates={rank: frozenset(dates) for rank, dates in rank_dates.items()},
        source_size_bytes=source_size_bytes,
    )


def _read_attested_snapshot_file(
    snapshot: Path,
    relative_path: str,
    *,
    expected_hash: str,
    label: str,
) -> bytes:
    path = snapshot / relative_path
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(snapshot):
        raise ValueError(f"{label} path is invalid")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"{label} must be a regular file inside the snapshot")
    contents = resolved.read_bytes()
    if _sha256(contents) != expected_hash:
        raise ValueError(f"{label} changed after re-attestation")
    return contents


def _source_snapshot_size(snapshot: Path) -> int:
    """Measure verified-source storage without including file names or values in output."""

    size_bytes = 0
    for entry in snapshot.rglob("*"):
        if entry.is_symlink():
            raise ValueError("Tiingo coverage audit source snapshot contains a symbolic link")
        if not entry.is_file():
            continue
        try:
            resolved = entry.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(
                "Tiingo coverage audit source snapshot changed during inspection"
            ) from exc
        if not resolved.is_relative_to(snapshot):
            raise ValueError("Tiingo coverage audit source snapshot file path is invalid")
        size_bytes += resolved.stat().st_size
    return size_bytes


def _summary(
    *,
    inputs: TiingoDailyCoverageAuditInputs,
    r1: _SnapshotCoverage,
    r2: _SnapshotCoverage,
    audited_at: datetime,
) -> dict[str, Any]:
    r1_document = _snapshot_document(r1)
    r2_document = _snapshot_document(r2)
    r1_ranks = set(r1.rank_dates)
    r2_ranks = set(r2.rank_dates)
    overlap_count = len(r1_ranks & r2_ranks)
    if overlap_count:
        raise ValueError("Tiingo coverage audit input ranks overlap")
    combined_dates = frozenset(
        set.intersection(
            *(set(dates) for dates in (*r1.rank_dates.values(), *r2.rank_dates.values()))
        )
    )
    r2_window = r2.common_dates
    candidate_count_covering_window = sum(
        r2_window.issubset(dates)
        for dates in (*r1.rank_dates.values(), *r2.rank_dates.values())
    )
    combined_count = len(r1.rank_dates) + len(r2.rank_dates)
    recommendation = _recommendation(
        r1=r1,
        r2=r2,
        combined_common_dates=combined_dates,
        candidate_count_covering_window=candidate_count_covering_window,
    )
    return {
        "schema_version": 1,
        "kind": "tiingo_daily_coverage_audit",
        "audit_version": TIINGO_COVERAGE_AUDIT_VERSION,
        "audited_at_utc": _format_utc(audited_at),
        "inputs": {
            "r1": {
                "snapshot_dir": str(inputs.r1_snapshot_dir),
                "dataset_hash": inputs.r1_dataset_hash,
                "manifest_hash": inputs.r1_manifest_hash,
            },
            "r2": {
                "snapshot_dir": str(inputs.r2_snapshot_dir),
                "dataset_hash": inputs.r2_dataset_hash,
                "manifest_hash": inputs.r2_manifest_hash,
            },
            "candidate_union_hash": inputs.candidate_union_hash,
        },
        "snapshots": {"r1": r1_document, "r2": r2_document},
        "combined": {
            "available_candidate_count": combined_count,
            "rank_overlap_count": overlap_count,
            "common_session_count": len(combined_dates),
            "common_session_range": _date_range(combined_dates),
            "intersection_is_monotone": True,
            "r1_is_binding_common_window": combined_dates == r1.common_dates,
        },
        "existing_window_filter": {
            "reference": "r2_common_returned_session_window",
            "reference_session_count": len(r2_window),
            "reference_session_range": _date_range(r2_window),
            "candidate_count_covering_r2_window": candidate_count_covering_window,
            "candidate_identifiers_persisted": False,
            "eligibility": "descriptive_only_not_pit_or_model",
        },
        "recommendation": recommendation,
        "scope": _SCOPE,
        "limitations": [
            "The candidate union has no publication-time proof or "
            "historical tradable-universe claim.",
            "R2 common sessions are a returned-source cohort fact, not "
            "point-in-time eligibility.",
            "Adding symbols cannot increase an existing intersection; a third shard "
            "cannot raise the R1/R2 combined common-session floor.",
            "Candidate filtering remains a private descriptive alternative until "
            "a separate bounded objective defines its use.",
        ],
    }


def _snapshot_document(coverage: _SnapshotCoverage) -> dict[str, Any]:
    counts = coverage.row_counts
    return {
        "dataset_hash": coverage.result.dataset_hash,
        "manifest_hash": coverage.result.manifest_hash,
        "request_count": coverage.result.request_count,
        "available_candidate_count": len(coverage.rank_dates),
        "unavailable_count": coverage.result.unavailable_count,
        "row_count": coverage.result.row_count,
        "per_candidate_rows_min": min(counts),
        "per_candidate_rows_max": max(counts),
        "common_session_count": len(coverage.common_dates),
        "common_session_range": _date_range(coverage.common_dates),
        "source_snapshot_size_bytes": coverage.source_size_bytes,
    }


def _recommendation(
    *,
    r1: _SnapshotCoverage,
    r2: _SnapshotCoverage,
    combined_common_dates: frozenset[date],
    candidate_count_covering_window: int,
) -> dict[str, Any]:
    return {
        "decision": "defer_third_shard_for_existing_window_filter_analysis",
        "primary_next_action": (
            "Evaluate a private descriptive fixed-window cohort from existing "
            "bytes before another acquisition."
        ),
        "third_shard_expected_value": (
            "Independent-cohort discovery only; it cannot improve the R1/R2 "
            "combined common-session floor."
        ),
        "unique_symbol_budget": {
            "requested_so_far": r1.result.request_count + r2.result.request_count,
            "additional_for_one_future_shard": 30,
            "public_monthly_reference": 500,
        },
        "storage_effect": {
            "current_source_snapshot_bytes": r1.source_size_bytes + r2.source_size_bytes,
            "projected_upper_bound_from_larger_existing_shard": max(
                r1.source_size_bytes, r2.source_size_bytes
            ),
        },
        "existing_filter_alternative": {
            "candidate_count_covering_r2_window": candidate_count_covering_window,
            "r2_window_session_count": len(r2.common_dates),
        },
        "stop_rule": (
            "Do not acquire a third shard merely to increase the combined "
            "common-session count."
        ),
        "reversal_fact": (
            "A later explicit independent-cohort contract shows the existing-window "
            "filter cannot satisfy its stated coverage need."
        ),
        "combined_common_session_count": len(combined_common_dates),
    }


def _validate_destination(
    destination: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(artifact_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Tiingo coverage audit artifact root must exist")
    root = root.resolve()
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo coverage audit artifact root must stay outside Git")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Tiingo coverage audit destination already exists")
    target = target.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Tiingo coverage audit destination must stay under the artifact root")
    if repo_root is not None and target.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo coverage audit destination must stay outside Git")
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Tiingo coverage audit destination name is invalid")
    if target.parent.is_dir() and any(target.parent.glob(".stage-*")):
        raise FileExistsError("Tiingo coverage audit staging residue requires recovery")
    return target, root


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Tiingo coverage audit storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Tiingo coverage audit storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn("Tiingo coverage audit storage is below the warning floor", stacklevel=2)
    return free_percent


def _rank(value: object) -> int:
    if not isinstance(value, str) or not value.isdigit() or int(value) <= 0:
        raise ValueError("Tiingo coverage audit candidate rank is invalid")
    return int(value)


def _session_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Tiingo coverage audit session date is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Tiingo coverage audit session date is invalid") from exc


def _date_range(dates: frozenset[date]) -> dict[str, str] | None:
    if not dates:
        return None
    return {"first": min(dates).isoformat(), "last": max(dates).isoformat()}


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

"""Compact, offline Tiingo/Norgate cross-source cohort evidence.

The existing Tiingo and Norgate parent verifiers own source correctness.  This
module reuses them, derives only rank/session/action-marker metadata, and never
exposes bars, features, labels, or a research training path.
"""

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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from .norgate_trial_development_panel import (
    DEFAULT_MARKET_DATA_ROOT,
    verify_norgate_trial_development_panel_snapshot,
)
from .tiingo_daily_pilot import verify_tiingo_daily_shard_snapshot

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
_DOCKER_MODEL_ARTIFACT_ROOT = Path("/app/model_artifacts")
_DOCKER_MARKET_DATA_ROOT = Path("/app/market_data")
COHORT_DIRECTORY = "tiingo-norgate-cross-source-cohort"
COHORT_VERSION = "tiingo-norgate-cross-source-cohort-r1"
_MANIFEST_FILE = "manifest.json"
_TIINGO_FILE = "ohlcv_1d.csv.gz"
_NORGATE_PANEL_FILE = "panel_ohlcv_1d.csv.gz"
_NORGATE_AVAILABILITY_FILE = "candidate_availability.csv"
_MAX_ARTIFACT_BYTES = 1_000_000
_FEATURE_LOOKBACK = 20
_OUTCOME_HORIZON = 2
_TIINGO_COLUMNS = (
    "candidate_rank",
    "candidate_symbol",
    "request_identifier",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "div_cash",
    "split_factor",
)
_NORGATE_PANEL_COLUMNS = (
    "candidate_rank",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_NORGATE_AVAILABILITY_COLUMNS = (
    "candidate_rank",
    "symbol",
    "status",
    "returned_row_count",
)

_TIINGO_SNAPSHOT_RELATIVE = Path(
    "us_equities/tiingo_standard_eod_pilot/canonical/"
    "snapshot=2026-07-18-tiingo-standard-eod-pilot-r2"
)
_NORGATE_SNAPSHOT_RELATIVE = Path(
    "us_equities/norgate_trial_broad_development_panel/canonical/ohlcv_1d/"
    "snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1"
)
DEFAULT_TIINGO_SNAPSHOT = DEFAULT_MARKET_DATA_ROOT / _TIINGO_SNAPSHOT_RELATIVE
DEFAULT_NORGATE_SNAPSHOT = DEFAULT_MARKET_DATA_ROOT / _NORGATE_SNAPSHOT_RELATIVE


@dataclass(frozen=True, slots=True)
class CrossSourceCohortExpectation:
    """Pinned parent identity and observed geometry for one bounded cohort."""

    tiingo_dataset_hash: str
    tiingo_manifest_hash: str
    norgate_dataset_hash: str
    norgate_manifest_hash: str
    tiingo_available_rank_count: int
    tiingo_session_count: int
    norgate_selected_rank_count: int
    norgate_session_count: int
    forward_only_session_count: int


DEFAULT_COHORT_EXPECTATION = CrossSourceCohortExpectation(
    tiingo_dataset_hash=("sha256:6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1"),
    tiingo_manifest_hash=(
        "sha256:76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e"
    ),
    norgate_dataset_hash=(
        "sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d"
    ),
    norgate_manifest_hash=(
        "sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e"
    ),
    tiingo_available_rank_count=29,
    tiingo_session_count=501,
    norgate_selected_rank_count=523,
    norgate_session_count=483,
    forward_only_session_count=18,
)


@dataclass(frozen=True, slots=True)
class TiingoNorgateCrossSourceCohort:
    """Read-only metadata for cross-source engineering falsification only."""

    artifact_dir: Path
    manifest_hash: str
    tiingo_dataset_hash: str
    tiingo_manifest_hash: str
    norgate_dataset_hash: str
    norgate_manifest_hash: str
    rank_count: int
    overlap_session_count: int
    forward_only_session_count: int
    marker_count: int
    excluded_decision_count: int
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _Series:
    candidate_rank: int
    symbol: str
    sessions: tuple[date, ...]
    marker_indices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Parent:
    snapshot_dir: Path
    snapshot_relative: PurePosixPath
    dataset_hash: str
    manifest_hash: str
    dataset_id: str
    series: tuple[_Series, ...]


def default_tiingo_norgate_cross_source_cohort_dir(
    *, artifact_root: Path | None = None
) -> Path:
    """Return the immutable external destination for this cohort revision."""

    return _artifact_root_or_default(artifact_root) / COHORT_DIRECTORY / COHORT_VERSION


def build_tiingo_norgate_cross_source_cohort(
    *,
    tiingo_snapshot: Path | None = None,
    norgate_snapshot: Path | None = None,
    artifact_root: Path | None = None,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
    expectation: CrossSourceCohortExpectation = DEFAULT_COHORT_EXPECTATION,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoNorgateCrossSourceCohort:
    """Write one compact external manifest after offline parent re-attestation."""

    root = _validate_artifact_root(_artifact_root_or_default(artifact_root), repo_root=repo_root)
    market_root = _market_data_root_or_default(market_data_root)
    _validate_expectation(expectation)
    tiingo = _load_tiingo(
        _snapshot_or_default(tiingo_snapshot, market_root, _TIINGO_SNAPSHOT_RELATIVE),
        market_data_root=market_root,
        repo_root=repo_root,
        expectation=expectation,
    )
    norgate = _load_norgate(
        _snapshot_or_default(norgate_snapshot, market_root, _NORGATE_SNAPSHOT_RELATIVE),
        market_data_root=market_root,
        repo_root=repo_root,
        expectation=expectation,
    )
    target = default_tiingo_norgate_cross_source_cohort_dir(artifact_root=root)
    _validate_artifact_target(target, root=root)
    if target.exists():
        return verify_tiingo_norgate_cross_source_cohort(
            target,
            artifact_root=root,
            market_data_root=market_root,
            repo_root=repo_root,
            expectation=expectation,
        )
    payload = _manifest(target, tiingo=tiingo, norgate=norgate, expectation=expectation)
    data = _json_bytes(payload)
    if len(data) > _MAX_ARTIFACT_BYTES:
        raise ValueError("cross-source cohort manifest exceeds the compact artifact limit")
    _validate_storage(root, required_bytes=len(data), disk_usage=disk_usage)
    staging = _create_staging_directory(target)
    try:
        (staging / _MANIFEST_FILE).write_bytes(data)
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return verify_tiingo_norgate_cross_source_cohort(
        target,
        artifact_root=root,
        market_data_root=market_root,
        repo_root=repo_root,
        expectation=expectation,
    )


def verify_tiingo_norgate_cross_source_cohort(
    artifact_dir: Path,
    *,
    artifact_root: Path | None = None,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
    expectation: CrossSourceCohortExpectation = DEFAULT_COHORT_EXPECTATION,
) -> TiingoNorgateCrossSourceCohort:
    """Recompute the manifest from verified local parents without credentials."""

    root = _validate_artifact_root(_artifact_root_or_default(artifact_root), repo_root=repo_root)
    market_root = _market_data_root_or_default(market_data_root)
    _validate_expectation(expectation)
    artifact = _validate_existing_artifact(artifact_dir, root=root)
    data = _read_regular_file(artifact, _MANIFEST_FILE, "cross-source cohort manifest")
    if len(data) > _MAX_ARTIFACT_BYTES:
        raise ValueError("cross-source cohort manifest exceeds the compact artifact limit")
    manifest = _json_object(data, "cross-source cohort manifest")
    tiingo_path, norgate_path = _contract_parent_paths(manifest, market_data_root=market_root)
    tiingo = _load_tiingo(
        tiingo_path,
        market_data_root=market_root,
        repo_root=repo_root,
        expectation=expectation,
    )
    norgate = _load_norgate(
        norgate_path,
        market_data_root=market_root,
        repo_root=repo_root,
        expectation=expectation,
    )
    if manifest != _manifest(artifact, tiingo=tiingo, norgate=norgate, expectation=expectation):
        raise ValueError("cross-source cohort manifest is inconsistent")
    return _cohort_result(artifact=artifact, manifest_hash=_sha256(data), manifest=manifest)


def load_verified_tiingo_norgate_cross_source_cohort(
    artifact_dir: Path,
    *,
    artifact_root: Path | None = None,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
    expectation: CrossSourceCohortExpectation = DEFAULT_COHORT_EXPECTATION,
) -> TiingoNorgateCrossSourceCohort:
    """Return metadata only after full parent and manifest re-attestation."""

    return verify_tiingo_norgate_cross_source_cohort(
        artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
        expectation=expectation,
    )


def _artifact_root_or_default(value: Path | None) -> Path:
    if value is not None:
        return Path(value)
    if _is_docker_runtime():
        return _DOCKER_MODEL_ARTIFACT_ROOT
    return DEFAULT_MODEL_ARTIFACT_ROOT


def _is_docker_runtime() -> bool:
    return os.name != "nt" and Path("/app").is_dir()


def _market_data_root_or_default(value: Path | None) -> Path:
    if value is not None:
        return Path(value)
    if _is_docker_runtime():
        return _DOCKER_MARKET_DATA_ROOT
    return DEFAULT_MARKET_DATA_ROOT


def _snapshot_or_default(value: Path | None, root: Path, relative: Path) -> Path:
    return Path(value) if value is not None else root / relative


def _load_tiingo(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    expectation: CrossSourceCohortExpectation,
) -> _Parent:
    root = _validate_market_root(market_data_root)
    snapshot = _validate_market_snapshot(snapshot_dir, root=root, label="Tiingo snapshot")
    manifest_data = _read_regular_file(snapshot, _MANIFEST_FILE, "Tiingo manifest")
    if _sha256(manifest_data) != expectation.tiingo_manifest_hash:
        raise ValueError("Tiingo cohort parent manifest hash mismatch")
    manifest = _json_object(manifest_data, "Tiingo manifest")
    predecessor = _mapping(manifest.get("predecessor"), "Tiingo predecessor")
    verify_tiingo_daily_shard_snapshot(
        snapshot,
        expected_dataset_hash=expectation.tiingo_dataset_hash,
        expected_manifest_hash=expectation.tiingo_manifest_hash,
        predecessor_snapshot_dir=_rebase_market_snapshot(
            predecessor.get("snapshot_dir"), market_data_root=root, label="Tiingo predecessor"
        ),
        expected_predecessor_dataset_hash=_required_sha256(
            predecessor.get("dataset_hash"), "Tiingo predecessor dataset hash"
        ),
        expected_predecessor_manifest_hash=_required_sha256(
            predecessor.get("manifest_hash"), "Tiingo predecessor manifest hash"
        ),
        expected_candidate_union_hash=_required_sha256(
            predecessor.get("candidate_union_hash"), "Tiingo predecessor candidate union hash"
        ),
        market_data_root=root,
        repo_root=repo_root,
    )
    canonical = _read_regular_file(snapshot, _TIINGO_FILE, "Tiingo canonical data")
    if _sha256(canonical) != expectation.tiingo_dataset_hash:
        raise ValueError("Tiingo cohort parent canonical data hash mismatch")
    series = _parse_tiingo(canonical)
    sessions = _common_sessions(series, label="Tiingo")
    if (
        len(series) != expectation.tiingo_available_rank_count
        or len(sessions) != expectation.tiingo_session_count
    ):
        raise ValueError("Tiingo cohort parent geometry is invalid")
    return _Parent(
        snapshot_dir=snapshot,
        snapshot_relative=_market_relative(snapshot, market_data_root=root),
        dataset_hash=expectation.tiingo_dataset_hash,
        manifest_hash=expectation.tiingo_manifest_hash,
        dataset_id=_nonempty_text(manifest.get("dataset_id"), "Tiingo dataset id"),
        series=series,
    )


def _load_norgate(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    expectation: CrossSourceCohortExpectation,
) -> _Parent:
    root = _validate_market_root(market_data_root)
    snapshot = _validate_market_snapshot(snapshot_dir, root=root, label="Norgate snapshot")
    result = verify_norgate_trial_development_panel_snapshot(
        snapshot, market_data_root=root, repo_root=repo_root
    )
    if (
        result.dataset_hash != expectation.norgate_dataset_hash
        or result.manifest_hash != expectation.norgate_manifest_hash
        or result.selected_symbol_count != expectation.norgate_selected_rank_count
        or result.common_session_count != expectation.norgate_session_count
        or not result.development_training_eligible
    ):
        raise ValueError("Norgate cohort parent facts are invalid")
    manifest_data = _read_regular_file(snapshot, _MANIFEST_FILE, "Norgate manifest")
    if _sha256(manifest_data) != expectation.norgate_manifest_hash:
        raise ValueError("Norgate cohort parent manifest hash mismatch")
    manifest = _json_object(manifest_data, "Norgate manifest")
    panel = _read_regular_file(snapshot, _NORGATE_PANEL_FILE, "Norgate panel data")
    if _sha256(panel) != expectation.norgate_dataset_hash:
        raise ValueError("Norgate cohort parent panel hash mismatch")
    availability = _read_regular_file(
        snapshot, _NORGATE_AVAILABILITY_FILE, "Norgate availability data"
    )
    series = _parse_norgate(panel, availability=availability)
    if (
        len(series) != expectation.norgate_selected_rank_count
        or len(_common_sessions(series, label="Norgate")) != expectation.norgate_session_count
    ):
        raise ValueError("Norgate cohort parent geometry is invalid")
    return _Parent(
        snapshot_dir=snapshot,
        snapshot_relative=_market_relative(snapshot, market_data_root=root),
        dataset_hash=expectation.norgate_dataset_hash,
        manifest_hash=expectation.norgate_manifest_hash,
        dataset_id=_nonempty_text(manifest.get("dataset_id"), "Norgate dataset id"),
        series=series,
    )


def _parse_tiingo(data: bytes) -> tuple[_Series, ...]:
    rows = _gzip_csv_rows(data, expected_columns=_TIINGO_COLUMNS, label="Tiingo canonical")
    grouped: dict[int, list[tuple[str, date, bool]]] = {}
    for row in rows:
        rank = _positive_int(row.get("candidate_rank"), "Tiingo candidate rank")
        symbol = _symbol(row.get("candidate_symbol"), "Tiingo symbol")
        if row.get("request_identifier") != symbol:
            raise ValueError("Tiingo canonical rank linkage is invalid")
        marker = (
            _decimal(row.get("div_cash"), "Tiingo dividend") != 0
            or _decimal(row.get("split_factor"), "Tiingo split factor") != 1
        )
        grouped.setdefault(rank, []).append(
            (symbol, _date_value(row.get("date"), "Tiingo session"), marker)
        )
    return _series_from_grouped(grouped, marker=True, label="Tiingo")


def _parse_norgate(data: bytes, *, availability: bytes) -> tuple[_Series, ...]:
    available = _availability_map(availability)
    rows = _gzip_csv_rows(data, expected_columns=_NORGATE_PANEL_COLUMNS, label="Norgate panel")
    grouped: dict[int, list[tuple[str, date, bool]]] = {}
    for row in rows:
        rank = _positive_int(row.get("candidate_rank"), "Norgate candidate rank")
        symbol = _symbol(row.get("symbol"), "Norgate symbol")
        if available.get(rank) != (symbol, "selected"):
            raise ValueError("Norgate panel availability linkage is invalid")
        grouped.setdefault(rank, []).append(
            (symbol, _date_value(row.get("date"), "Norgate session"), False)
        )
    if set(grouped) != {
        rank for rank, (_symbol_value, status) in available.items() if status == "selected"
    }:
        raise ValueError("Norgate selected rank set is invalid")
    return _series_from_grouped(grouped, marker=False, label="Norgate")


def _gzip_csv_rows(
    data: bytes, *, expected_columns: tuple[str, ...], label: str
) -> tuple[dict[str, str], ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as compressed:
            reader = csv.DictReader(io.TextIOWrapper(compressed, encoding="utf-8", newline=""))
            fieldnames = tuple(reader.fieldnames or ())
            rows = tuple(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if fieldnames != expected_columns or not rows:
        raise ValueError(f"{label} schema is invalid")
    return rows


def _availability_map(data: bytes) -> dict[int, tuple[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        if tuple(reader.fieldnames or ()) != _NORGATE_AVAILABILITY_COLUMNS:
            raise ValueError("Norgate availability schema is invalid")
        rows = tuple(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate availability data is invalid") from exc
    result: dict[int, tuple[str, str]] = {}
    for row in rows:
        rank = _positive_int(row.get("candidate_rank"), "Norgate availability rank")
        symbol = _symbol(row.get("symbol"), "Norgate availability symbol")
        status = _nonempty_text(row.get("status"), "Norgate availability status")
        if (
            status not in {"selected", "session_mismatch", "unavailable", "invalid"}
            or rank in result
        ):
            raise ValueError("Norgate availability is invalid")
        result[rank] = (symbol, status)
    if not result:
        raise ValueError("Norgate availability is empty")
    return result


def _series_from_grouped(
    grouped: Mapping[int, list[tuple[str, date, bool]]], *, marker: bool, label: str
) -> tuple[_Series, ...]:
    result: list[_Series] = []
    for rank in sorted(grouped):
        entries = grouped[rank]
        symbols = {item[0] for item in entries}
        sessions = tuple(item[1] for item in entries)
        if len(symbols) != 1 or any(
            later <= earlier for earlier, later in zip(sessions, sessions[1:], strict=False)
        ):
            raise ValueError(f"{label} rows are not canonical")
        result.append(
            _Series(
                candidate_rank=rank,
                symbol=next(iter(symbols)),
                sessions=sessions,
                marker_indices=tuple(
                    index for index, item in enumerate(entries) if marker and item[2]
                ),
            )
        )
    if not result:
        raise ValueError(f"{label} has no series")
    return tuple(result)


def _manifest(
    artifact: Path,
    *,
    tiingo: _Parent,
    norgate: _Parent,
    expectation: CrossSourceCohortExpectation,
) -> dict[str, Any]:
    tiingo_sessions = _common_sessions(tiingo.series, label="Tiingo")
    norgate_sessions = _common_sessions(norgate.series, label="Norgate")
    if tiingo_sessions[: len(norgate_sessions)] != norgate_sessions:
        raise ValueError("cross-source overlap session sequence is invalid")
    forward_only = tiingo_sessions[len(norgate_sessions) :]
    if (
        len(forward_only) != expectation.forward_only_session_count
        or forward_only[0] <= norgate_sessions[-1]
    ):
        raise ValueError("cross-source forward-only boundary is invalid")
    norgate_by_rank = {item.candidate_rank: item.symbol for item in norgate.series}
    linkage = [
        {"candidate_rank": item.candidate_rank, "symbol": item.symbol} for item in tiingo.series
    ]
    if len({item["symbol"] for item in linkage}) != len(linkage) or any(
        norgate_by_rank.get(item["candidate_rank"]) != item["symbol"] for item in linkage
    ):
        raise ValueError("cross-source rank and symbol linkage is invalid")
    decision_start = _FEATURE_LOOKBACK
    decision_end = len(norgate_sessions) - _OUTCOME_HORIZON - 1
    if decision_end < decision_start:
        raise ValueError("cross-source reference window is invalid")
    masks: list[dict[str, Any]] = []
    marker_count = overlap_count = forward_count = excluded_count = 0
    for source in tiingo.series:
        overlap = tuple(index for index in source.marker_indices if index < len(norgate_sessions))
        forward = tuple(index for index in source.marker_indices if index >= len(norgate_sessions))
        excluded = _excluded_indices(
            overlap, decision_start=decision_start, decision_end=decision_end
        )
        marker_count += len(source.marker_indices)
        overlap_count += len(overlap)
        forward_count += len(forward)
        excluded_count += len(excluded)
        masks.append(
            {
                "candidate_rank": source.candidate_rank,
                "overlap_marker_session_indices": list(overlap),
                "overlap_marker_dates": [tiingo_sessions[index].isoformat() for index in overlap],
                "forward_only_marker_session_indices": list(forward),
                "forward_only_marker_dates": [
                    tiingo_sessions[index].isoformat() for index in forward
                ],
                "excluded_decision_indices": list(excluded),
            }
        )
    if marker_count == 0:
        raise ValueError("cross-source cohort has no Tiingo action markers")
    overlap_dates = [item.isoformat() for item in norgate_sessions]
    forward_dates = [item.isoformat() for item in forward_only]
    return {
        "schema_version": 1,
        "kind": "tiingo_norgate_cross_source_cohort",
        "cohort_version": COHORT_VERSION,
        "artifact_dir_name": artifact.name,
        "immutable": True,
        "scope": {
            "cross_source_engineering_evidence_only": True,
            "point_in_time_eligible": False,
            "model_eligible": False,
            "training_eligible": False,
            "ranking_eligible": False,
            "ensemble_eligible": False,
            "campaign_eligible": False,
            "paper_trading_eligible": False,
            "pnl_eligible": False,
            "profitability_eligible": False,
        },
        "access_boundary": {
            "network_access": False,
            "credential_access": False,
            "broker_access": False,
            "local_paper_access": False,
            "model_access": False,
            "raw_bar_export": False,
            "feature_or_label_export": False,
        },
        "parents": {
            "tiingo": {
                "snapshot_relative_to_market_data_root": tiingo.snapshot_relative.as_posix(),
                "dataset_id": tiingo.dataset_id,
                "dataset_hash": tiingo.dataset_hash,
                "manifest_hash": tiingo.manifest_hash,
                "raw_fields": list(_TIINGO_COLUMNS),
            },
            "norgate": {
                "snapshot_relative_to_market_data_root": norgate.snapshot_relative.as_posix(),
                "dataset_id": norgate.dataset_id,
                "dataset_hash": norgate.dataset_hash,
                "manifest_hash": norgate.manifest_hash,
                "raw_fields": list(_NORGATE_PANEL_COLUMNS),
            },
        },
        "rank_linkage": {
            "available_rank_count": len(linkage),
            "pairs": linkage,
            "pairs_sha256": _sha256(_json_bytes(linkage)),
            "matching_rule": "candidate_rank_and_exact_symbol",
        },
        "session_contract": {
            "tiingo_common_session_count": len(tiingo_sessions),
            "norgate_overlap_session_count": len(norgate_sessions),
            "overlap_session_dates": overlap_dates,
            "overlap_session_dates_sha256": _sha256(_json_bytes(overlap_dates)),
            "forward_only_session_count": len(forward_only),
            "forward_only_session_dates": forward_dates,
            "forward_only_session_dates_sha256": _sha256(_json_bytes(forward_dates)),
            "forward_only_price_source": "tiingo_only",
            "norgate_fields_in_forward_only_slice": False,
        },
        "conservative_marker_mask": {
            "marker_definition": {
                "cash_distribution": "div_cash != 0",
                "split": "split_factor != 1",
                "source": "Tiingo canonical raw fields",
            },
            "reference_window": {
                "feature_source_index_range": "t-20..t",
                "entry_index": "t+1",
                "outcome_exit_index": "t+2",
                "inclusive_dependency_index_range": "t-20..t+2",
                "reference_only_not_a_training_contract": True,
                "candidate_decision_index_range": f"{decision_start}..{decision_end}",
            },
            "edge_censored_decision_indices": [
                *range(decision_start),
                len(norgate_sessions) - 2,
                len(norgate_sessions) - 1,
            ],
            "total_marker_count": marker_count,
            "overlap_marker_count": overlap_count,
            "forward_only_marker_count": forward_count,
            "per_rank": masks,
            "per_rank_sha256": _sha256(_json_bytes(masks)),
            "excluded_rank_decision_pair_count": excluded_count,
        },
        "limitations": [
            "The rank/symbol linkage is static survivor and availability evidence, not PIT "
            "membership.",
            "Norgate raw adjustment and corporate-action semantics remain unverified.",
            "Tiingo marker dates prove only provider-returned date attachment, not action timing.",
            "Session edges outside this snapshot are censored or unobservable, not clean evidence.",
            "Forward-only Tiingo sessions are source-separated engineering evidence, not a "
            "performance holdout.",
            "No provider price fields are mixed, compared, ranked, or exported by this cohort.",
        ],
    }


def _excluded_indices(
    markers: tuple[int, ...], *, decision_start: int, decision_end: int
) -> tuple[int, ...]:
    excluded: set[int] = set()
    for marker in markers:
        excluded.update(
            range(
                max(decision_start, marker - _OUTCOME_HORIZON),
                min(decision_end, marker + _FEATURE_LOOKBACK) + 1,
            )
        )
    return tuple(sorted(excluded))


def _cohort_result(
    *, artifact: Path, manifest_hash: str, manifest: Mapping[str, Any]
) -> TiingoNorgateCrossSourceCohort:
    parents = _mapping(manifest.get("parents"), "cross-source parents")
    tiingo = _mapping(parents.get("tiingo"), "cross-source Tiingo parent")
    norgate = _mapping(parents.get("norgate"), "cross-source Norgate parent")
    linkage = _mapping(manifest.get("rank_linkage"), "cross-source rank linkage")
    sessions = _mapping(manifest.get("session_contract"), "cross-source session contract")
    mask = _mapping(manifest.get("conservative_marker_mask"), "cross-source marker mask")
    return TiingoNorgateCrossSourceCohort(
        artifact_dir=artifact,
        manifest_hash=manifest_hash,
        tiingo_dataset_hash=_required_sha256(tiingo.get("dataset_hash"), "Tiingo dataset hash"),
        tiingo_manifest_hash=_required_sha256(tiingo.get("manifest_hash"), "Tiingo manifest hash"),
        norgate_dataset_hash=_required_sha256(norgate.get("dataset_hash"), "Norgate dataset hash"),
        norgate_manifest_hash=_required_sha256(
            norgate.get("manifest_hash"), "Norgate manifest hash"
        ),
        rank_count=_positive_int(linkage.get("available_rank_count"), "cross-source rank count"),
        overlap_session_count=_positive_int(
            sessions.get("norgate_overlap_session_count"), "cross-source overlap session count"
        ),
        forward_only_session_count=_nonnegative_int(
            sessions.get("forward_only_session_count"), "cross-source forward session count"
        ),
        marker_count=_positive_int(mask.get("total_marker_count"), "cross-source marker count"),
        excluded_decision_count=_nonnegative_int(
            mask.get("excluded_rank_decision_pair_count"), "cross-source exclusion count"
        ),
        metadata=MappingProxyType(dict(manifest)),
    )


def _contract_parent_paths(
    manifest: Mapping[str, Any], *, market_data_root: Path
) -> tuple[Path, Path]:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "tiingo_norgate_cross_source_cohort"
        or manifest.get("cohort_version") != COHORT_VERSION
        or manifest.get("immutable") is not True
    ):
        raise ValueError("cross-source cohort manifest identity is invalid")
    parents = _mapping(manifest.get("parents"), "cross-source parents")
    return (
        _relative_market_snapshot(
            _mapping(parents.get("tiingo"), "cross-source Tiingo parent").get(
                "snapshot_relative_to_market_data_root"
            ),
            market_data_root=market_data_root,
            label="Tiingo parent",
        ),
        _relative_market_snapshot(
            _mapping(parents.get("norgate"), "cross-source Norgate parent").get(
                "snapshot_relative_to_market_data_root"
            ),
            market_data_root=market_data_root,
            label="Norgate parent",
        ),
    )


def _common_sessions(series: tuple[_Series, ...], *, label: str) -> tuple[date, ...]:
    if (
        not series
        or not series[0].sessions
        or any(item.sessions != series[0].sessions for item in series[1:])
    ):
        raise ValueError(f"{label} series session sequences are invalid")
    return series[0].sessions


def _validate_expectation(expectation: CrossSourceCohortExpectation) -> None:
    for value, label in (
        (expectation.tiingo_dataset_hash, "expected Tiingo dataset hash"),
        (expectation.tiingo_manifest_hash, "expected Tiingo manifest hash"),
        (expectation.norgate_dataset_hash, "expected Norgate dataset hash"),
        (expectation.norgate_manifest_hash, "expected Norgate manifest hash"),
    ):
        _required_sha256(value, label)
    if (
        expectation.tiingo_available_rank_count <= 0
        or expectation.norgate_selected_rank_count <= 0
        or expectation.norgate_session_count <= 0
        or expectation.forward_only_session_count <= 0
        or expectation.tiingo_session_count
        != expectation.norgate_session_count + expectation.forward_only_session_count
    ):
        raise ValueError("cross-source cohort expectation is invalid")


def _validate_market_root(value: Path) -> Path:
    root = Path(value)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("cross-source market-data root is invalid")
    return root.resolve()


def _validate_market_snapshot(value: Path, *, root: Path, label: str) -> Path:
    snapshot = Path(value)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError(f"{label} is invalid")
    snapshot = snapshot.resolve()
    if snapshot == root or not snapshot.is_relative_to(root):
        raise ValueError(f"{label} must stay under market data")
    return snapshot


def _market_relative(snapshot: Path, *, market_data_root: Path) -> PurePosixPath:
    root = _validate_market_root(market_data_root)
    return _portable_relative_path(
        snapshot.resolve().relative_to(root).as_posix(), "parent snapshot"
    )


def _relative_market_snapshot(value: object, *, market_data_root: Path, label: str) -> Path:
    root = _validate_market_root(market_data_root)
    relative = _portable_relative_path(value, label)
    return _validate_market_snapshot(root.joinpath(*relative.parts), root=root, label=label)


def _rebase_market_snapshot(value: object, *, market_data_root: Path, label: str) -> Path:
    root = _validate_market_root(market_data_root)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} is invalid")
    declared = Path(value)
    if declared.is_dir() and not declared.is_symlink() and declared.resolve().is_relative_to(root):
        return declared.resolve()
    parts = tuple(part for part in value.replace("\\", "/").split("/") if part)
    anchors = [index for index, part in enumerate(parts) if part.casefold() == root.name.casefold()]
    if not anchors:
        raise ValueError(f"{label} root is invalid")
    return _relative_market_snapshot(
        "/".join(parts[anchors[-1] + 1 :]), market_data_root=root, label=label
    )


def _portable_relative_path(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(
            part in {".", ".."} or any(char in part for char in ("\\", ":")) for part in path.parts
        )
    ):
        raise ValueError(f"{label} is invalid")
    return path


def _validate_artifact_root(value: Path, *, repo_root: Path | None) -> Path:
    root = Path(value)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("cross-source artifact root must be an existing directory")
    root = root.resolve()
    repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repo.is_dir() or repo.is_symlink():
        raise ValueError("cross-source repository root is invalid")
    repo = repo.resolve()
    docker_root = Path("/app/model_artifacts").resolve()
    docker_mount = (
        os.name != "nt" and repo == Path("/app").resolve() and root.is_relative_to(docker_root)
    )
    if root.is_relative_to(repo) and not docker_mount:
        raise ValueError("cross-source artifacts must stay outside the Git workspace")
    return root


def _validate_artifact_target(target: Path, *, root: Path) -> None:
    if Path(target) != default_tiingo_norgate_cross_source_cohort_dir(artifact_root=root):
        raise ValueError("cross-source artifact destination is invalid")
    if target.parent.exists() and target.parent.is_symlink():
        raise ValueError("cross-source artifact parent path is invalid")
    if target.parent.is_dir() and any(target.parent.glob(".stage-*")):
        raise FileExistsError("cross-source artifact staging residue requires recovery")


def _validate_existing_artifact(value: Path, *, root: Path) -> Path:
    artifact = Path(value)
    if not artifact.is_dir() or artifact.is_symlink():
        raise ValueError("cross-source cohort artifact must be a directory")
    artifact = artifact.resolve()
    if artifact != default_tiingo_norgate_cross_source_cohort_dir(artifact_root=root):
        raise ValueError("cross-source cohort artifact must stay under the artifact root")
    entries = tuple(artifact.iterdir())
    if {entry.name for entry in entries} != {_MANIFEST_FILE} or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ValueError("cross-source cohort artifact files are invalid")
    return artifact


def _validate_storage(
    root: Path, *, required_bytes: int, disk_usage: Callable[[str | Path], Any]
) -> None:
    usage = disk_usage(root)
    total = int(usage.total)
    free_after = int(usage.free) - required_bytes
    if total <= 0 or free_after < 0:
        raise ValueError("cross-source artifact storage is invalid")
    free_percent = 100 * free_after / total
    if free_percent < 15:
        raise ValueError("cross-source artifact storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn("cross-source artifact storage is below the warning floor", stacklevel=2)


def _create_staging_directory(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".stage-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _read_regular_file(root: Path, filename: str, label: str) -> bytes:
    path = root / filename
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(root):
        raise ValueError(f"{label} path is invalid")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError(f"{label} must be a regular file")
    return resolved.read_bytes()


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        return _mapping(json.loads(data.decode("utf-8")), label)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is invalid")
    return value


def _positive_int(value: object, label: str) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if isinstance(value, bool) or result <= 0 or str(result) != str(value):
        raise ValueError(f"{label} is invalid")
    return result


def _nonnegative_int(value: object, label: str) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if isinstance(value, bool) or result < 0 or str(result) != str(value):
        raise ValueError(f"{label} is invalid")
    return result


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} is invalid")
    return value


def _symbol(value: object, label: str) -> str:
    return _nonempty_text(value, label).upper()


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} is invalid")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} is invalid")
    return result


def _required_sha256(value: object, label: str) -> str:
    result = _nonempty_text(value, label)
    if (
        len(result) != 71
        or not result.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in result[7:])
    ):
        raise ValueError(f"{label} is invalid")
    return result


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

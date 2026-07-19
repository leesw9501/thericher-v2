"""External engineering-only features derived from an attested Norgate panel."""

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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from thericher_v2.data.norgate_trial_development_panel import (
    DEFAULT_MARKET_DATA_ROOT,
    NorgateTrialDevelopmentPanelResult,
    verify_norgate_trial_development_panel_snapshot,
)

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
NORGATE_BROAD_DEVELOPMENT_FEATURE_ARTIFACT_VERSION = "norgate-broad-development-feature-r2"

_ARTIFACT_DIRECTORY = "norgate-broad-development-features"
_FEATURE_FILE = "features.npz"
_CONTRACT_FILE = "contract.json"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "DELETE_ON_PARENT_EXPIRY.txt"
_PARENT_DATA_FILE = "panel_ohlcv_1d.csv.gz"
_PARENT_MANIFEST_FILE = "manifest.json"
_PARENT_RETENTION_FILE = "DELETE_NORGATE_DATA_ON_EXPIRY.txt"
_PARENT_DATA_COLUMNS = (
    "candidate_rank",
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_ARRAY_NAMES = (
    "feature_array",
    "label_array",
    "symbol_ranks",
    "decision_indices",
    "decision_dates",
    "decision_timestamps_ns",
    "source_start_indices",
    "source_end_indices",
    "source_start_timestamps_ns",
    "source_end_timestamps_ns",
    "entry_indices",
    "exit_indices",
    "split_ids",
)
_FIRST_DECISION_INDEX = 20
_LAST_DECISION_INDEX = 480
_FEATURE_RETURN_COUNT = 20
_DEVELOPMENT_START = 20
_DEVELOPMENT_END = 319
_PURGE_START = 320
_PURGE_END = 321
_VALIDATION_START = 322
_VALIDATION_END = 480
_DISCONTINUITY_THRESHOLD = Decimal("0.20")
_SESSION_COUNT = 483
_NANOSECONDS_PER_DAY = 86_400_000_000_000
_UNIX_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()
_SPLIT_CODES = {"development": 0, "purge": 1, "validation": 2}
_DERIVED_SCOPE = {
    "engineering_cuda_exploration_eligible": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "model_eligible": False,
    "model_promotion_eligible": False,
    "gpu_eligible": False,
    "paper_trading_eligible": False,
    "pnl_eligible": False,
    "profitability_eligible": False,
}


@dataclass(frozen=True, slots=True)
class NorgateBroadDevelopmentFeatureArtifact:
    """Verified arrays and immutable metadata for bounded engineering exploration."""

    artifact_dir: Path
    panel_snapshot_dir: Path
    artifact_hash: str
    contract_hash: str
    manifest_hash: str
    parent_dataset_hash: str
    parent_manifest_hash: str
    contract: Mapping[str, Any]
    metadata: Mapping[str, Any]
    feature_array: Any
    label_array: Any
    symbol_ranks: Any
    decision_indices: Any
    decision_dates: Any
    decision_timestamps_ns: Any
    source_start_indices: Any
    source_end_indices: Any
    source_start_timestamps_ns: Any
    source_end_timestamps_ns: Any
    entry_indices: Any
    exit_indices: Any
    split_ids: Any


@dataclass(frozen=True, slots=True)
class _PanelSeries:
    candidate_rank: int
    symbol: str
    sessions: tuple[date, ...]
    opens: tuple[Decimal, ...]
    closes: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class _AttestedPanel:
    result: NorgateTrialDevelopmentPanelResult
    snapshot_relative_to_market_data_root: PurePosixPath
    parent_retention_hash: str
    series: tuple[_PanelSeries, ...]


@dataclass(frozen=True, slots=True)
class _FeaturePayload:
    arrays: dict[str, Any]
    row_counts: dict[str, int]
    selected_symbols: tuple[tuple[int, str], ...]


def default_norgate_broad_development_feature_artifact_dir(
    panel_snapshot: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
) -> Path:
    """Return the deterministic external destination for one parent panel."""

    name = Path(panel_snapshot).name
    if not name.startswith("snapshot="):
        raise ValueError("Norgate broad development panel snapshot name is invalid")
    identity = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return Path(artifact_root) / _ARTIFACT_DIRECTORY / f"r2-{identity}"


def build_norgate_broad_development_feature_artifact(
    panel_snapshot: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateBroadDevelopmentFeatureArtifact:
    """Build one immutable external feature artifact from an attested raw panel.

    This is deliberately a data-quality transform, not a model, campaign, ranking,
    PnL, profitability, paper-trading, or generic GPU authorization surface.
    """

    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    parent = _load_attested_panel(
        panel_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    target = default_norgate_broad_development_feature_artifact_dir(
        parent.result.snapshot_dir,
        artifact_root=root,
    )
    _validate_artifact_target(target, root=root, parent=parent)
    if target.exists():
        return load_verified_norgate_broad_development_feature_artifact(
            target,
            artifact_root=root,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )

    payload = _build_feature_payload(parent)
    contract = _contract(target, parent=parent, payload=payload)
    contract_bytes = _json_bytes(contract)
    feature_bytes = _npz_bytes(payload.arrays)
    retention_bytes = _retention_marker_bytes(parent)
    required_bytes = len(contract_bytes) + len(feature_bytes) + len(retention_bytes)
    _validate_storage(root, required_bytes=required_bytes)
    manifest = _manifest(
        target,
        parent=parent,
        contract_bytes=contract_bytes,
        feature_bytes=feature_bytes,
        retention_bytes=retention_bytes,
    )
    manifest_bytes = _json_bytes(manifest)

    staging = _create_staging_directory(target)
    try:
        (staging / _CONTRACT_FILE).write_bytes(contract_bytes)
        (staging / _FEATURE_FILE).write_bytes(feature_bytes)
        (staging / _RETENTION_FILE).write_bytes(retention_bytes)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return load_verified_norgate_broad_development_feature_artifact(
        target,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def verify_norgate_broad_development_feature_artifact(
    artifact_dir: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateBroadDevelopmentFeatureArtifact:
    """Re-attest derived bytes, transform math, and the raw panel lineage offline."""

    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    artifact = _validate_existing_artifact(artifact_dir, root=root)
    manifest_bytes = _read_regular_file(artifact, _MANIFEST_FILE, "feature artifact manifest")
    manifest = _json_object(manifest_bytes, "feature artifact manifest")
    files = _mapping(manifest.get("files"), "feature artifact files")
    contract_bytes = _read_verified_file(
        artifact,
        files.get("contract"),
        expected_name=_CONTRACT_FILE,
        label="feature artifact contract",
    )
    contract = _json_object(contract_bytes, "feature artifact contract")
    parent_snapshot = _contract_parent_snapshot(
        contract,
        artifact=artifact,
        market_data_root=market_data_root,
    )
    parent = _load_attested_panel(
        parent_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    payload = _build_feature_payload(parent)
    expected_contract = _contract(artifact, parent=parent, payload=payload)
    if contract != expected_contract:
        raise ValueError("Norgate broad development feature contract is inconsistent")

    feature_bytes = _read_verified_file(
        artifact,
        files.get("features"),
        expected_name=_FEATURE_FILE,
        label="feature artifact features",
    )
    retention_bytes = _read_verified_file(
        artifact,
        files.get("retention_marker"),
        expected_name=_RETENTION_FILE,
        label="feature artifact retention marker",
    )
    if retention_bytes != _retention_marker_bytes(parent):
        raise ValueError("Norgate broad development feature retention marker is invalid")

    expected_manifest = _manifest(
        artifact,
        parent=parent,
        contract_bytes=contract_bytes,
        feature_bytes=feature_bytes,
        retention_bytes=retention_bytes,
    )
    if manifest != expected_manifest:
        raise ValueError("Norgate broad development feature manifest is inconsistent")

    arrays = _load_npz_arrays(feature_bytes)
    _validate_arrays(arrays, expected=payload.arrays)
    return _artifact_result(
        artifact=artifact,
        parent=parent,
        contract=contract,
        manifest=manifest,
        arrays=arrays,
        contract_hash=_sha256(contract_bytes),
        artifact_hash=_sha256(feature_bytes),
        manifest_hash=_sha256(manifest_bytes),
    )


def load_verified_norgate_broad_development_feature_artifact(
    artifact_dir: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateBroadDevelopmentFeatureArtifact:
    """Load arrays only after a full offline re-attestation of their parent panel."""

    return verify_norgate_broad_development_feature_artifact(
        artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def _load_attested_panel(
    panel_snapshot: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> _AttestedPanel:
    result = verify_norgate_trial_development_panel_snapshot(
        panel_snapshot,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    if not result.development_training_eligible:
        raise ValueError("Norgate broad development parent is not development-training eligible")
    if result.common_session_count != _SESSION_COUNT:
        raise ValueError("Norgate broad development parent session count is invalid")
    snapshot_relative = _market_data_relative_path(
        result.snapshot_dir,
        market_data_root=market_data_root,
    )

    manifest_bytes = _read_regular_file(
        result.snapshot_dir,
        _PARENT_MANIFEST_FILE,
        "Norgate broad development parent manifest",
    )
    if _sha256(manifest_bytes) != result.manifest_hash:
        raise ValueError("Norgate broad development parent manifest hash mismatch")
    manifest = _json_object(manifest_bytes, "Norgate broad development parent manifest")
    scope = _mapping(manifest.get("scope"), "Norgate broad development parent scope")
    if scope.get("model_eligible") is not False or scope.get("gpu_eligible") is not False:
        raise ValueError("Norgate broad development parent model or GPU scope is invalid")

    files = _mapping(manifest.get("files"), "Norgate broad development parent files")
    data = _read_verified_file(
        result.snapshot_dir,
        files.get("panel_ohlcv"),
        expected_name=_PARENT_DATA_FILE,
        label="Norgate broad development parent data",
    )
    if _sha256(data) != result.dataset_hash:
        raise ValueError("Norgate broad development parent data hash mismatch")
    retention = _read_verified_file(
        result.snapshot_dir,
        files.get("retention_marker"),
        expected_name=_PARENT_RETENTION_FILE,
        label="Norgate broad development parent retention marker",
    )
    series = _parse_panel_series(data, result=result)
    return _AttestedPanel(
        result=result,
        snapshot_relative_to_market_data_root=snapshot_relative,
        parent_retention_hash=_sha256(retention),
        series=series,
    )


def _parse_panel_series(
    data: bytes,
    *,
    result: NorgateTrialDevelopmentPanelResult,
) -> tuple[_PanelSeries, ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as compressed:
            reader = csv.DictReader(io.TextIOWrapper(compressed, encoding="utf-8", newline=""))
            fieldnames = tuple(reader.fieldnames or ())
            source_rows = tuple(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Norgate broad development parent data is invalid") from exc
    if fieldnames != _PARENT_DATA_COLUMNS:
        raise ValueError("Norgate broad development parent data schema is invalid")

    grouped: dict[int, list[tuple[str, date, Decimal, Decimal]]] = {}
    previous_rank = 0
    previous_date: date | None = None
    for row in source_rows:
        rank = _positive_int(row.get("candidate_rank"), "candidate rank")
        symbol = _symbol(row.get("symbol"))
        session = _date_value(row.get("date"), "session date")
        if rank < previous_rank or (
            rank == previous_rank and previous_date is not None and session <= previous_date
        ):
            raise ValueError("Norgate broad development parent data ordering is invalid")
        if rank != previous_rank:
            previous_date = None
        grouped.setdefault(rank, []).append(
            (
                symbol,
                session,
                _positive_decimal(row.get("open"), "open"),
                _positive_decimal(row.get("close"), "close"),
            )
        )
        previous_rank = rank
        previous_date = session

    if len(grouped) != result.selected_symbol_count:
        raise ValueError("Norgate broad development selected symbol count is invalid")
    series: list[_PanelSeries] = []
    common_sessions: tuple[date, ...] | None = None
    for rank in sorted(grouped):
        values = grouped[rank]
        symbols = {value[0] for value in values}
        sessions = tuple(value[1] for value in values)
        if len(symbols) != 1 or len(sessions) != _SESSION_COUNT:
            raise ValueError("Norgate broad development parent series is invalid")
        if common_sessions is None:
            common_sessions = sessions
        elif sessions != common_sessions:
            raise ValueError("Norgate broad development parent sessions are uneven")
        series.append(
            _PanelSeries(
                candidate_rank=rank,
                symbol=next(iter(symbols)),
                sessions=sessions,
                opens=tuple(value[2] for value in values),
                closes=tuple(value[3] for value in values),
            )
        )
    if common_sessions is None or (
        common_sessions[0] != result.actual_start or common_sessions[-1] != result.actual_end
    ):
        raise ValueError("Norgate broad development parent session range is invalid")
    return tuple(series)


def _build_feature_payload(parent: _AttestedPanel) -> _FeaturePayload:
    np = _numpy()
    feature_rows: list[list[float]] = []
    labels: list[int] = []
    symbol_ranks: list[int] = []
    decision_indices: list[int] = []
    decision_dates: list[str] = []
    decision_timestamps: list[int] = []
    source_start_indices: list[int] = []
    source_end_indices: list[int] = []
    feature_start_timestamps: list[int] = []
    feature_end_timestamps: list[int] = []
    entry_indices: list[int] = []
    exit_indices: list[int] = []
    split_ids: list[int] = []

    ordered_sources = tuple(sorted(parent.series, key=lambda item: item.candidate_rank))
    discontinuities = {
        source.candidate_rank: _raw_discontinuities(source) for source in ordered_sources
    }
    for decision_index in range(_FIRST_DECISION_INDEX, _LAST_DECISION_INDEX + 1):
        split_name = _split_name(decision_index)
        split_code = _SPLIT_CODES[split_name]
        for source in ordered_sources:
            if any(
                discontinuities[source.candidate_rank][
                    _discontinuity_start(decision_index) : decision_index + 3
                ]
            ):
                continue
            feature_start = decision_index - _FEATURE_RETURN_COUNT
            feature_values = [
                float(source.closes[index] / source.closes[index - 1] - 1)
                for index in range(feature_start + 1, decision_index + 1)
            ]
            if len(feature_values) != _FEATURE_RETURN_COUNT:
                raise ValueError("Norgate broad development feature count is invalid")
            outcome = source.opens[decision_index + 2] / source.opens[decision_index + 1] - 1
            feature_rows.append(feature_values)
            labels.append(_binary_direction(outcome))
            symbol_ranks.append(source.candidate_rank)
            decision_indices.append(decision_index)
            decision_dates.append(source.sessions[decision_index].isoformat())
            decision_timestamps.append(_timestamp_ns(source.sessions[decision_index]))
            source_start_indices.append(feature_start)
            source_end_indices.append(decision_index)
            feature_start_timestamps.append(_timestamp_ns(source.sessions[feature_start]))
            feature_end_timestamps.append(_timestamp_ns(source.sessions[decision_index]))
            entry_indices.append(decision_index + 1)
            exit_indices.append(decision_index + 2)
            split_ids.append(split_code)

    arrays = {
        "feature_array": np.asarray(feature_rows, dtype=np.float32).reshape(
            len(feature_rows), _FEATURE_RETURN_COUNT
        ),
        "label_array": np.asarray(labels, dtype=np.int8),
        "symbol_ranks": np.asarray(symbol_ranks, dtype=np.int32),
        "decision_indices": np.asarray(decision_indices, dtype=np.int16),
        "decision_dates": np.asarray(decision_dates, dtype="U10"),
        "decision_timestamps_ns": np.asarray(decision_timestamps, dtype=np.int64),
        "source_start_indices": np.asarray(source_start_indices, dtype=np.int16),
        "source_end_indices": np.asarray(source_end_indices, dtype=np.int16),
        "source_start_timestamps_ns": np.asarray(feature_start_timestamps, dtype=np.int64),
        "source_end_timestamps_ns": np.asarray(feature_end_timestamps, dtype=np.int64),
        "entry_indices": np.asarray(entry_indices, dtype=np.int16),
        "exit_indices": np.asarray(exit_indices, dtype=np.int16),
        "split_ids": np.asarray(split_ids, dtype=np.int8),
    }
    _validate_payload_geometry(arrays)
    return _FeaturePayload(
        arrays=arrays,
        row_counts={
            name: int((arrays["split_ids"] == code).sum())
            for name, code in _SPLIT_CODES.items()
        },
        selected_symbols=tuple(
            (item.candidate_rank, item.symbol)
            for item in sorted(parent.series, key=lambda item: item.candidate_rank)
        ),
    )


def _raw_discontinuities(source: _PanelSeries) -> tuple[bool, ...]:
    flags = [False]
    for index in range(1, len(source.sessions)):
        previous_close = source.closes[index - 1]
        open_gap = abs(source.opens[index] / previous_close - 1)
        close_gap = abs(source.closes[index] / previous_close - 1)
        flags.append(open_gap >= _DISCONTINUITY_THRESHOLD or close_gap >= _DISCONTINUITY_THRESHOLD)
    return tuple(flags)


def _discontinuity_start(decision_index: int) -> int:
    return decision_index - _FEATURE_RETURN_COUNT


def _split_name(decision_index: int) -> str:
    if _DEVELOPMENT_START <= decision_index <= _DEVELOPMENT_END:
        return "development"
    if _PURGE_START <= decision_index <= _PURGE_END:
        return "purge"
    if _VALIDATION_START <= decision_index <= _VALIDATION_END:
        return "validation"
    raise ValueError("Norgate broad development decision index is outside the frozen split")


def _contract(
    artifact: Path,
    *,
    parent: _AttestedPanel,
    payload: _FeaturePayload,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "norgate_broad_development_feature_artifact",
        "artifact_version": NORGATE_BROAD_DEVELOPMENT_FEATURE_ARTIFACT_VERSION,
        "artifact_dir_name": artifact.name,
        "parent_panel": {
            "snapshot_relative_to_market_data_root": str(
                parent.snapshot_relative_to_market_data_root
            ),
            "dataset_hash": parent.result.dataset_hash,
            "manifest_hash": parent.result.manifest_hash,
            "selected_symbol_count": parent.result.selected_symbol_count,
            "common_session_count": parent.result.common_session_count,
            "actual_common_window": {
                "start": parent.result.actual_start.isoformat(),
                "end": parent.result.actual_end.isoformat(),
            },
            "development_training_eligible": True,
            "raw_scope": {"model_eligible": False, "gpu_eligible": False},
            "retention_marker": {
                "path": _PARENT_RETENTION_FILE,
                "sha256": parent.parent_retention_hash,
            },
        },
        "scope": dict(_DERIVED_SCOPE),
        "transform": {
            "feature_kind": "raw_close_to_close_returns",
            "feature_return_count": _FEATURE_RETURN_COUNT,
            "feature_return_end_index_range": "t-19..t",
            "feature_source_index_range": "t-20..t",
            "max_feature_source_index": "t",
            "entry_index": "t+1",
            "exit_index": "t+2",
            "label": "1 if open[t+2]/open[t+1]-1 > 0 else 0",
            "label_values": {"non_positive": 0, "positive": 1},
        },
        "discontinuity_conditioning": {
            "purpose": "raw_data_quality_conditioning_only",
            "does_not_assert_corporate_action": True,
            "threshold_absolute_return": float(_DISCONTINUITY_THRESHOLD),
            "condition": (
                "abs(open[i]/close[i-1]-1)>=0.20 or "
                "abs(close[i]/close[i-1]-1)>=0.20"
            ),
            "checked_index_range": "t-20..t+2",
            "index_zero_policy": "not_computable_without_prior_panel_close",
            "exclusion_rule": "exclude sample when any checked raw discontinuity is true",
        },
        "temporal_groups": {
            "development": {
                "decision_index_start": _DEVELOPMENT_START,
                "decision_index_end": _DEVELOPMENT_END,
                "decision_date_count": _DEVELOPMENT_END - _DEVELOPMENT_START + 1,
                "split_code": _SPLIT_CODES["development"],
            },
            "purge": {
                "decision_index_start": _PURGE_START,
                "decision_index_end": _PURGE_END,
                "decision_date_count": _PURGE_END - _PURGE_START + 1,
                "split_code": _SPLIT_CODES["purge"],
            },
            "validation": {
                "decision_index_start": _VALIDATION_START,
                "decision_index_end": _VALIDATION_END,
                "decision_date_count": _VALIDATION_END - _VALIDATION_START + 1,
                "split_code": _SPLIT_CODES["validation"],
            },
            "row_order": "decision_index_then_candidate_rank",
        },
        "timestamp_encoding": "utc_epoch_nanoseconds",
        "selected_symbols": [
            {"candidate_rank": rank, "symbol": symbol}
            for rank, symbol in payload.selected_symbols
        ],
        "row_counts": payload.row_counts,
        "arrays": {
            name: {"dtype": str(value.dtype), "shape": list(value.shape)}
            for name, value in payload.arrays.items()
        },
        "retention": {
            "norgate_origin_data": True,
            "parent_deletion_requires_derived_deletion": True,
            "automated_deletion": False,
            "marker_file": _RETENTION_FILE,
        },
        "inherited_boundary_limitations": {
            "raw_discontinuity_index_zero": "not_computable_without_prior_panel_close",
        },
        "limitations": [
            "This artifact is derived from a static complete-history survivor panel.",
            "Raw adjustment semantics remain unverified.",
            "Raw discontinuity conditioning is not a corporate-action assertion.",
            "Raw discontinuity index 0 cannot be computed because no prior panel close exists.",
            "This artifact is engineering-only CUDA exploration evidence, not model promotion,"
            " ranking, holdout, campaign, paper, PnL, or profitability evidence.",
        ],
    }


def _manifest(
    artifact: Path,
    *,
    parent: _AttestedPanel,
    contract_bytes: bytes,
    feature_bytes: bytes,
    retention_bytes: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "norgate_broad_development_feature_artifact",
        "artifact_version": NORGATE_BROAD_DEVELOPMENT_FEATURE_ARTIFACT_VERSION,
        "artifact_dir_name": artifact.name,
        "immutable_artifact": True,
        "parent_dataset_hash": parent.result.dataset_hash,
        "parent_manifest_hash": parent.result.manifest_hash,
        "files": {
            "contract": _file_document(_CONTRACT_FILE, contract_bytes, "json"),
            "features": _file_document(_FEATURE_FILE, feature_bytes, "npz"),
            "retention_marker": _file_document(_RETENTION_FILE, retention_bytes, "text"),
        },
    }


def _file_document(path: str, data: bytes, file_format: str) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": _sha256(data),
        "size_bytes": len(data),
        "format": file_format,
    }


def _retention_marker_bytes(parent: _AttestedPanel) -> bytes:
    return (
        "This directory contains a derived feature artifact from Norgate-origin data.\n"
        "If the parent Norgate trial or subscription requires deletion under the EULA,\n"
        "the operator must delete this derived directory with the parent snapshot.\n"
        "Parent snapshot relative to market-data root: "
        f"{parent.snapshot_relative_to_market_data_root}\n"
        f"Parent dataset hash: {parent.result.dataset_hash}\n"
        f"Parent manifest hash: {parent.result.manifest_hash}\n"
        f"Parent retention marker hash: {parent.parent_retention_hash}\n"
        "This marker records linkage only. It does not perform deletion or authorize\n"
        "deletion of C:\\ProgramData\\Norgate Data.\n"
    ).encode("ascii")


def _validate_payload_geometry(arrays: Mapping[str, Any]) -> None:
    np = _numpy()
    feature_array = arrays["feature_array"]
    row_count = feature_array.shape[0]
    if feature_array.ndim != 2 or feature_array.shape[1] != _FEATURE_RETURN_COUNT:
        raise ValueError("Norgate broad development feature shape is invalid")
    if not np.isfinite(feature_array).all():
        raise ValueError("Norgate broad development feature values are invalid")
    if any(
        value.shape != (row_count,)
        for name, value in arrays.items()
        if name != "feature_array"
    ):
        raise ValueError("Norgate broad development feature row alignment is invalid")
    decision = arrays["decision_indices"]
    starts = arrays["source_start_indices"]
    ends = arrays["source_end_indices"]
    entries = arrays["entry_indices"]
    exits = arrays["exit_indices"]
    if (
        not ((decision >= _FIRST_DECISION_INDEX) & (decision <= _LAST_DECISION_INDEX)).all()
        or not (starts == decision - _FEATURE_RETURN_COUNT).all()
        or not (ends == decision).all()
        or not (entries == decision + 1).all()
        or not (exits == decision + 2).all()
        or not (ends <= decision).all()
    ):
        raise ValueError("Norgate broad development no-lookahead geometry is invalid")
    expected_codes = np.asarray([_SPLIT_CODES[_split_name(int(value))] for value in decision])
    if not np.array_equal(arrays["split_ids"], expected_codes):
        raise ValueError("Norgate broad development split codes are invalid")
    if not set(int(value) for value in arrays["label_array"]).issubset({0, 1}):
        raise ValueError("Norgate broad development labels are invalid")
    if not (arrays["source_end_timestamps_ns"] == arrays["decision_timestamps_ns"]).all():
        raise ValueError("Norgate broad development source end timestamps are invalid")
    if not (arrays["source_start_timestamps_ns"] <= arrays["source_end_timestamps_ns"]).all():
        raise ValueError("Norgate broad development source timestamps are invalid")
    canonical_order = np.lexsort((arrays["symbol_ranks"], decision))
    if not np.array_equal(canonical_order, np.arange(row_count)):
        raise ValueError("Norgate broad development row order is invalid")


def _validate_arrays(arrays: Mapping[str, Any], *, expected: Mapping[str, Any]) -> None:
    if tuple(arrays) != _ARRAY_NAMES:
        raise ValueError("Norgate broad development feature arrays are invalid")
    for name in _ARRAY_NAMES:
        actual = arrays[name]
        expected_value = expected[name]
        if actual.dtype != expected_value.dtype or actual.shape != expected_value.shape:
            raise ValueError("Norgate broad development feature array schema is invalid")
        if not _numpy().array_equal(actual, expected_value):
            raise ValueError("Norgate broad development feature array content is invalid")
    _validate_payload_geometry(arrays)


def _load_npz_arrays(data: bytes) -> dict[str, Any]:
    np = _numpy()
    try:
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            if tuple(archive.files) != _ARRAY_NAMES:
                raise ValueError("Norgate broad development feature array names are invalid")
            arrays = {name: archive[name] for name in _ARRAY_NAMES}
    except (OSError, ValueError) as exc:
        raise ValueError("Norgate broad development feature archive is invalid") from exc
    if any(value.dtype.hasobject for value in arrays.values()):
        raise ValueError("Norgate broad development feature archive contains object arrays")
    return arrays


def _npz_bytes(arrays: Mapping[str, Any]) -> bytes:
    np = _numpy()
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **{name: arrays[name] for name in _ARRAY_NAMES})
    return buffer.getvalue()


def _artifact_result(
    *,
    artifact: Path,
    parent: _AttestedPanel,
    contract: dict[str, Any],
    manifest: dict[str, Any],
    arrays: Mapping[str, Any],
    contract_hash: str,
    artifact_hash: str,
    manifest_hash: str,
) -> NorgateBroadDevelopmentFeatureArtifact:
    return NorgateBroadDevelopmentFeatureArtifact(
        artifact_dir=artifact,
        panel_snapshot_dir=parent.result.snapshot_dir,
        artifact_hash=artifact_hash,
        contract_hash=contract_hash,
        manifest_hash=manifest_hash,
        parent_dataset_hash=parent.result.dataset_hash,
        parent_manifest_hash=parent.result.manifest_hash,
        contract=MappingProxyType(contract),
        metadata=MappingProxyType(manifest),
        feature_array=arrays["feature_array"],
        label_array=arrays["label_array"],
        symbol_ranks=arrays["symbol_ranks"],
        decision_indices=arrays["decision_indices"],
        decision_dates=arrays["decision_dates"],
        decision_timestamps_ns=arrays["decision_timestamps_ns"],
        source_start_indices=arrays["source_start_indices"],
        source_end_indices=arrays["source_end_indices"],
        source_start_timestamps_ns=arrays["source_start_timestamps_ns"],
        source_end_timestamps_ns=arrays["source_end_timestamps_ns"],
        entry_indices=arrays["entry_indices"],
        exit_indices=arrays["exit_indices"],
        split_ids=arrays["split_ids"],
    )


def _market_data_relative_path(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
) -> PurePosixPath:
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate broad development market-data root is invalid")
    root = root.resolve()
    snapshot = Path(snapshot_dir).resolve()
    if snapshot == root or root not in snapshot.parents:
        raise ValueError("Norgate broad development parent snapshot is outside market data")
    return _portable_relative_path(
        snapshot.relative_to(root).as_posix(),
        "parent panel snapshot",
    )


def _portable_relative_path(value: object, label: str) -> PurePosixPath:
    raw = _nonempty_text(value, label)
    candidate = PurePosixPath(raw)
    if (
        candidate.is_absolute()
        or not candidate.parts
        or any(
            part in {".", ".."} or any(character in part for character in ("\\", ":"))
            for part in candidate.parts
        )
    ):
        raise ValueError(f"Norgate broad development {label} is invalid")
    return candidate


def _contract_parent_snapshot(
    contract: dict[str, Any],
    *,
    artifact: Path,
    market_data_root: Path,
) -> Path:
    if (
        contract.get("schema_version") != 1
        or contract.get("kind") != "norgate_broad_development_feature_artifact"
        or contract.get("artifact_version") != NORGATE_BROAD_DEVELOPMENT_FEATURE_ARTIFACT_VERSION
        or contract.get("artifact_dir_name") != artifact.name
    ):
        raise ValueError("Norgate broad development feature contract identity is invalid")
    parent = _mapping(contract.get("parent_panel"), "Norgate broad development parent panel")
    relative = _portable_relative_path(
        parent.get("snapshot_relative_to_market_data_root"),
        "parent panel snapshot",
    )
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate broad development market-data root is invalid")
    root = root.resolve()
    snapshot = (root / Path(*relative.parts)).resolve()
    if snapshot == root or root not in snapshot.parents:
        raise ValueError("Norgate broad development parent snapshot escapes market data")
    return snapshot


def _validate_artifact_root(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(artifact_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Norgate broad development artifact root must be an existing directory")
    root = root.resolve()
    repository = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repository.is_dir() or repository.is_symlink():
        raise ValueError("Norgate broad development repository root is invalid")
    repository = repository.resolve()
    docker_artifact_root = Path("/app/model_artifacts").resolve()
    docker_mount = (
        os.name != "nt"
        and repository == Path("/app").resolve()
        and (root == docker_artifact_root or root.is_relative_to(docker_artifact_root))
    )
    if (root == repository or root.is_relative_to(repository)) and not docker_mount:
        raise ValueError("Norgate broad development artifact root must stay outside Git workspace")
    return root


def _validate_artifact_target(target: Path, *, root: Path, parent: _AttestedPanel) -> None:
    expected = default_norgate_broad_development_feature_artifact_dir(
        parent.result.snapshot_dir,
        artifact_root=root,
    )
    if Path(target) != expected:
        raise ValueError("Norgate broad development artifact destination is invalid")
    container = expected.parent
    if container.exists() and container.is_symlink():
        raise ValueError("Norgate broad development artifact parent path is invalid")
    if container.is_dir() and any(container.glob(".stage-*")):
        raise FileExistsError(
            "Norgate broad development artifact staging residue requires recovery"
        )


def _validate_existing_artifact(artifact_dir: Path, *, root: Path) -> Path:
    artifact = Path(artifact_dir)
    if not artifact.is_dir() or artifact.is_symlink():
        raise ValueError("Norgate broad development feature artifact must be a directory")
    artifact = artifact.resolve()
    expected_parent = (root / _ARTIFACT_DIRECTORY).resolve()
    if artifact.parent != expected_parent or not artifact.is_relative_to(root):
        raise ValueError("Norgate broad development feature artifact must stay under artifact root")
    _validate_artifact_files(artifact)
    return artifact


def _validate_artifact_files(artifact: Path) -> None:
    expected = {_FEATURE_FILE, _CONTRACT_FILE, _MANIFEST_FILE, _RETENTION_FILE}
    try:
        entries = tuple(artifact.iterdir())
    except OSError as exc:
        raise ValueError("Norgate broad development feature artifact is unreadable") from exc
    if {entry.name for entry in entries} != expected or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ValueError("Norgate broad development feature artifact files are invalid")


def _validate_storage(root: Path, *, required_bytes: int) -> None:
    if required_bytes < 0:
        raise ValueError("Norgate broad development artifact size is invalid")
    usage = shutil.disk_usage(root)
    total = int(usage.total)
    free_after = int(usage.free) - required_bytes
    if total <= 0 or free_after < 0:
        raise ValueError("Norgate broad development artifact storage is invalid")
    free_percent = 100 * free_after / total
    if free_percent < 15:
        raise ValueError(
            "Norgate broad development artifact storage is below the hard free-space floor"
        )
    if free_percent < 20:
        warnings.warn(
            "Norgate broad development artifact storage is below the warning floor",
            stacklevel=2,
        )


def _create_staging_directory(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("Norgate broad development artifact parent path is invalid")
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


def _read_verified_file(
    root: Path,
    metadata: object,
    *,
    expected_name: str,
    label: str,
) -> bytes:
    document = _mapping(metadata, f"{label} metadata")
    if document.get("path") != expected_name:
        raise ValueError(f"{label} metadata is invalid")
    data = _read_regular_file(root, expected_name, label)
    if _sha256(data) != _required_sha256(document.get("sha256"), f"{label} hash"):
        raise ValueError(f"{label} hash mismatch")
    if document.get("size_bytes") != len(data):
        raise ValueError(f"{label} size is inconsistent")
    return data


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    return _mapping(value, label)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is invalid")
    return value


def _positive_int(value: object, label: str) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Norgate broad development {label} is invalid") from exc
    if isinstance(value, bool) or result <= 0 or str(result) != str(value):
        raise ValueError(f"Norgate broad development {label} is invalid")
    return result


def _nonempty_text(value: object, label: str) -> str:
    result = str(value or "")
    if not result or result != result.strip():
        raise ValueError(f"Norgate broad development {label} is required")
    return result


def _symbol(value: object) -> str:
    result = _nonempty_text(value, "symbol").upper()
    if result != result.strip():
        raise ValueError("Norgate broad development symbol is invalid")
    return result


def _date_value(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Norgate broad development {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Norgate broad development {label} is invalid") from exc


def _positive_decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Norgate broad development {label} is invalid") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"Norgate broad development {label} is invalid")
    return result


def _binary_direction(value: Decimal) -> int:
    return 1 if value > 0 else 0


def _timestamp_ns(value: date) -> int:
    return (value.toordinal() - _UNIX_EPOCH_ORDINAL) * _NANOSECONDS_PER_DAY


def _required_sha256(value: object, label: str) -> str:
    result = _nonempty_text(value, label)
    if len(result) != 71 or not result.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in result[7:]
    ):
        raise ValueError(f"Norgate broad development {label} is invalid")
    return result


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Norgate broad development features require the research NumPy extra"
        ) from exc
    return np

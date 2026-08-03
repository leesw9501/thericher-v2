"""Read-only geometry audit for one bounded KIS broad-D1 selected panel.

The audit consumes raw bars only in memory.  Its external receipt deliberately
contains aggregate counts, hashes, and fixed availability semantics rather than
symbols, rows, prices, targets, model outputs, or execution state.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, Bar
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KisPaperDailyBroadPanelSelection,
    load_materialized_kis_paper_daily_broad_panel_selection,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_BROAD_D1_GEOMETRY_AUDIT_ID = "kis-broad-d1-geometry-audit-v1"
KIS_BROAD_D1_GEOMETRY_AUDIT_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
KIS_BROAD_D1_GEOMETRY_AUDIT_DIRECTORY = "data/kis-broad-d1-geometry-audit-v1"
KIS_BROAD_D1_GEOMETRY_AUDIT_RATIO_BINS = (2.0, 3.0, 5.0, 10.0)
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


class KisBroadD1GeometryAuditUnavailable(ValueError):
    """The fixed source coverage cannot satisfy this audit contract."""

    def __init__(self, code: str) -> None:
        if not code or not code.replace("_", "").isalnum():
            raise ValueError("KIS broad D1 geometry audit unavailable code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KisBroadD1GeometryAuditSpec:
    """Fixed selection, event, and chronological availability geometry."""

    cohort_target_count: int = 128
    history_session_count: int = 800
    terminal_buffer_sessions: int = 1
    feature_lookback_sessions: int = 20
    development_session_count: int = 520
    purge_session_count: int = 20
    validation_session_count: int = 260
    minimum_validation_available_target_count: int = 96
    maximum_within_bar_range_ratio: float = 2.0
    raw_byte_attestation_limit: int = 512
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.cohort_target_count < 2
            or self.history_session_count < 8
            or self.terminal_buffer_sessions != 1
            or self.feature_lookback_sessions != 20
            or self.development_session_count < 4
            or self.purge_session_count < 1
            or self.validation_session_count < 4
            or self.development_session_count
            + self.purge_session_count
            + self.validation_session_count
            != self.history_session_count
            or self.feature_lookback_sessions >= self.development_session_count - 1
            or self.feature_lookback_sessions >= self.validation_session_count - 1
            or not math.isfinite(self.maximum_within_bar_range_ratio)
            or self.maximum_within_bar_range_ratio != 2.0
            or not 1 <= self.minimum_validation_available_target_count <= self.cohort_target_count
            or self.raw_byte_attestation_limit < self.cohort_target_count
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS broad D1 geometry audit spec is invalid")

    @property
    def development_decision_count(self) -> int:
        return self.development_session_count - self.feature_lookback_sessions - 1

    @property
    def validation_decision_count(self) -> int:
        return self.validation_session_count - self.feature_lookback_sessions - 1

    def payload(self) -> dict[str, object]:
        return {
            "cohort_target_count": self.cohort_target_count,
            "cohort_selection": "lexicographic_first_coverage_eligible_no_score_or_rank",
            "history_session_count": self.history_session_count,
            "terminal_buffer_sessions": self.terminal_buffer_sessions,
            "feature_lookback_sessions": self.feature_lookback_sessions,
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "maximum_within_bar_range_ratio": self.maximum_within_bar_range_ratio,
            "ratio_bin_thresholds": list(KIS_BROAD_D1_GEOMETRY_AUDIT_RATIO_BINS),
            "minimum_validation_available_target_count": (
                self.minimum_validation_available_target_count
            ),
            "raw_byte_attestation_limit": self.raw_byte_attestation_limit,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1GeometryAuditSource:
    """Source-safe identity of the exact selected-panel audit input."""

    dataset_hash: str
    manifest_sha256: str
    materialization_receipt_sha256: str
    source_index_hash: str
    selected_target_key_set_hash: str
    full_target_count: int
    coverage_eligible_target_count: int
    selected_target_count: int
    raw_byte_attested_target_count: int
    common_session_count: int
    common_session_grid_sha256: str

    def __post_init__(self) -> None:
        if (
            any(
                not _is_sha256(value)
                for value in (
                    self.dataset_hash,
                    self.manifest_sha256,
                    self.materialization_receipt_sha256,
                    self.source_index_hash,
                    self.selected_target_key_set_hash,
                    self.common_session_grid_sha256,
                )
            )
            or self.full_target_count < self.coverage_eligible_target_count
            or self.coverage_eligible_target_count < self.selected_target_count
            or self.selected_target_count < 1
            or self.raw_byte_attested_target_count < self.selected_target_count
            or self.raw_byte_attested_target_count > self.coverage_eligible_target_count
            or self.common_session_count < 1
        ):
            raise ValueError("KIS broad D1 geometry audit source is invalid")

    @property
    def excluded_target_count(self) -> int:
        return self.full_target_count - self.selected_target_count

    def payload(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "manifest_sha256": self.manifest_sha256,
            "materialization_receipt_sha256": self.materialization_receipt_sha256,
            "source_index_hash": self.source_index_hash,
            "selected_target_key_set_hash": self.selected_target_key_set_hash,
            "full_target_count": self.full_target_count,
            "coverage_eligible_target_count": self.coverage_eligible_target_count,
            "selected_target_count": self.selected_target_count,
            "raw_byte_attested_target_count": self.raw_byte_attested_target_count,
            "excluded_target_count": self.excluded_target_count,
            "common_session_count": self.common_session_count,
            "common_session_grid_sha256": self.common_session_grid_sha256,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1GeometryRatioBin:
    """Aggregate event counts for one frozen high/low-ratio threshold."""

    threshold: float
    affected_bar_count: int
    affected_target_count: int
    affected_session_count: int

    def __post_init__(self) -> None:
        if (
            self.threshold not in KIS_BROAD_D1_GEOMETRY_AUDIT_RATIO_BINS
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.affected_bar_count,
                    self.affected_target_count,
                    self.affected_session_count,
                )
            )
        ):
            raise ValueError("KIS broad D1 geometry ratio bin is invalid")

    def payload(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "affected_bar_count": self.affected_bar_count,
            "affected_target_count": self.affected_target_count,
            "affected_session_count": self.affected_session_count,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1GeometryAudit:
    """Aggregate-only geometry and causal feature-window availability evidence."""

    source: KisBroadD1GeometryAuditSource
    spec: KisBroadD1GeometryAuditSpec
    ratio_bins: tuple[KisBroadD1GeometryRatioBin, ...]
    feature_event_mask_sha256: str
    feature_event_count: int
    feature_event_target_count: int
    feature_event_session_count: int
    development_available_pair_count: int
    development_available_per_target_min: int
    development_available_per_target_max: int
    validation_available_pair_count: int
    validation_available_per_target_min: int
    validation_available_per_target_max: int
    validation_available_per_session_min: int
    validation_available_per_session_max: int
    validation_sessions_below_minimum_count: int
    contract_sha256: str

    def __post_init__(self) -> None:
        expected_thresholds = KIS_BROAD_D1_GEOMETRY_AUDIT_RATIO_BINS
        if (
            not isinstance(self.source, KisBroadD1GeometryAuditSource)
            or not isinstance(self.spec, KisBroadD1GeometryAuditSpec)
            or tuple(item.threshold for item in self.ratio_bins) != expected_thresholds
            or any(not isinstance(item, KisBroadD1GeometryRatioBin) for item in self.ratio_bins)
            or not _is_sha256(self.feature_event_mask_sha256)
            or not _is_sha256(self.contract_sha256)
            or self.feature_event_count != self.ratio_bins[0].affected_bar_count
            or self.feature_event_target_count != self.ratio_bins[0].affected_target_count
            or self.feature_event_session_count != self.ratio_bins[0].affected_session_count
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.feature_event_count,
                    self.feature_event_target_count,
                    self.feature_event_session_count,
                    self.development_available_pair_count,
                    self.development_available_per_target_min,
                    self.development_available_per_target_max,
                    self.validation_available_pair_count,
                    self.validation_available_per_target_min,
                    self.validation_available_per_target_max,
                    self.validation_available_per_session_min,
                    self.validation_available_per_session_max,
                    self.validation_sessions_below_minimum_count,
                )
            )
            or self.development_available_per_target_min
            > self.development_available_per_target_max
            or self.validation_available_per_target_min
            > self.validation_available_per_target_max
            or self.validation_available_per_session_min
            > self.validation_available_per_session_max
            or self.validation_available_per_session_max > self.source.selected_target_count
            or self.validation_sessions_below_minimum_count
            > self.spec.validation_decision_count
            or self.contract_sha256 != _sha256_payload(_contract_payload(self.source, self.spec))
        ):
            raise ValueError("KIS broad D1 geometry audit is invalid")

    @property
    def event_censored_candidate_input_eligible(self) -> bool:
        return (
            self.validation_sessions_below_minimum_count == 0
            and self.development_available_pair_count > 0
            and self.validation_available_pair_count > 0
        )

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_BROAD_D1_GEOMETRY_AUDIT_ID,
            "status": "completed",
            "contract_sha256": self.contract_sha256,
            "source": self.source.payload(),
            "spec": self.spec.payload(),
            "ratio_bins": [item.payload() for item in self.ratio_bins],
            "feature_event_censoring": {
                "event_definition": "high_low_ratio_gt_fixed_2",
                "feature_window": "t_minus_19_through_t_completed_bars_only",
                "target_event_censoring": False,
                "feature_event_mask_sha256": self.feature_event_mask_sha256,
                "feature_event_count": self.feature_event_count,
                "feature_event_target_count": self.feature_event_target_count,
                "feature_event_session_count": self.feature_event_session_count,
                "development_available_pair_count": self.development_available_pair_count,
                "development_available_per_target_min": self.development_available_per_target_min,
                "development_available_per_target_max": self.development_available_per_target_max,
                "validation_available_pair_count": self.validation_available_pair_count,
                "validation_available_per_target_min": self.validation_available_per_target_min,
                "validation_available_per_target_max": self.validation_available_per_target_max,
                "validation_available_per_session_min": self.validation_available_per_session_min,
                "validation_available_per_session_max": self.validation_available_per_session_max,
                "validation_sessions_below_minimum_count": (
                    self.validation_sessions_below_minimum_count
                ),
                "event_censored_candidate_input_eligible": (
                    self.event_censored_candidate_input_eligible
                ),
            },
            "scope": {
                "source_local_development_input_only": True,
                "current_listing_only": True,
                "non_pit": True,
                "adjustment_mode": "MODP=0_unadjusted",
                "corporate_action_qualified": False,
                "session_finality_attested": False,
                "model_training_eligible": False,
                "ranking_allowed": False,
                "pnl_or_profitability_claim_allowed": False,
                "paper_input_allowed": False,
                "live_allowed": False,
            },
            "artifact_policy": _artifact_policy(),
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1GeometryAuditRun:
    """One immutable external audit result or scoped unavailable receipt."""

    status: str
    run_directory: Path
    receipt_path: Path
    receipt_sha256: str
    audit: KisBroadD1GeometryAudit | None

    def __post_init__(self) -> None:
        if (
            self.status not in {"completed", "input_unavailable"}
            or not self.run_directory.is_dir()
            or not self.receipt_path.is_file()
            or not _is_sha256(self.receipt_sha256)
            or _sha256_file(self.receipt_path) != self.receipt_sha256
            or (self.status == "completed") != (self.audit is not None)
        ):
            raise ValueError("KIS broad D1 geometry audit run is invalid")


def build_kis_broad_d1_geometry_audit(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str,
    cache_root: Path | str,
    panel_root: Path | str,
    repo_root: Path | str | None = None,
    spec: KisBroadD1GeometryAuditSpec | None = None,
) -> KisBroadD1GeometryAudit:
    """Reattach one selected panel and calculate aggregate-only geometry facts."""

    resolved_spec = spec or KisBroadD1GeometryAuditSpec()
    try:
        selection = load_materialized_kis_paper_daily_broad_panel_selection(
            manifest_path,
            materialization_receipt_path=materialization_receipt_path,
            cohort_target_count=resolved_spec.cohort_target_count,
            minimum_bar_count=(
                resolved_spec.history_session_count + resolved_spec.terminal_buffer_sessions
            ),
            common_session_count=resolved_spec.history_session_count,
            terminal_buffer_sessions=resolved_spec.terminal_buffer_sessions,
            raw_byte_attestation_limit=resolved_spec.raw_byte_attestation_limit,
            cache_root=cache_root,
            panel_root=panel_root,
            repo_root=repo_root,
        )
    except ValueError as error:
        reason = {
            "broad daily panel selection coverage is insufficient": (
                "insufficient_coverage_eligible_targets"
            ),
            "broad daily panel selection exact coverage is insufficient": (
                "insufficient_exact_common_session_coverage"
            ),
        }.get(str(error))
        if reason is None:
            raise
        raise KisBroadD1GeometryAuditUnavailable(reason) from error
    return build_kis_broad_d1_geometry_audit_from_selection(selection, spec=resolved_spec)


def build_kis_broad_d1_geometry_audit_from_selection(
    selection: KisPaperDailyBroadPanelSelection,
    *,
    spec: KisBroadD1GeometryAuditSpec | None = None,
) -> KisBroadD1GeometryAudit:
    """Build the fixed audit from a Data-owned selected-panel type."""

    if not isinstance(selection, KisPaperDailyBroadPanelSelection):
        raise TypeError("KIS broad D1 geometry audit requires a selected panel")
    resolved_spec = spec or KisBroadD1GeometryAuditSpec()
    if (
        len(selection.selected_target_keys) != resolved_spec.cohort_target_count
        or selection.minimum_bar_count
        != resolved_spec.history_session_count + resolved_spec.terminal_buffer_sessions
        or selection.common_session_count != resolved_spec.history_session_count
        or selection.terminal_buffer_sessions != resolved_spec.terminal_buffer_sessions
        or selection.raw_byte_attested_target_count < resolved_spec.cohort_target_count
    ):
        raise ValueError("KIS broad D1 geometry audit selection contract is invalid")

    grid = _common_grid(selection, resolved_spec)
    records_by_target: dict[str, tuple[Bar, ...]] = {}
    event_rows: list[list[bool]] = []
    for target_key in selection.selected_target_keys:
        records = _records_on_grid(selection.bars_by_target[target_key].bars, grid)
        records_by_target[target_key] = records
        event_rows.append(_event_flags(records, resolved_spec))

    ratio_bins = tuple(
        KisBroadD1GeometryRatioBin(
            threshold=threshold,
            affected_bar_count=sum(
                _ratio_exceeds(record, threshold)
                for records in records_by_target.values()
                for record in records
            ),
            affected_target_count=sum(
                any(_ratio_exceeds(record, threshold) for record in records)
                for records in records_by_target.values()
            ),
            affected_session_count=sum(
                any(
                    _ratio_exceeds(records[session_index], threshold)
                    for records in records_by_target.values()
                )
                for session_index in range(len(grid))
            ),
        )
        for threshold in KIS_BROAD_D1_GEOMETRY_AUDIT_RATIO_BINS
    )
    availability_rows = [_feature_availability(row, resolved_spec) for row in event_rows]
    development_indices = range(
        resolved_spec.feature_lookback_sessions,
        resolved_spec.development_session_count - 1,
    )
    validation_start = (
        resolved_spec.development_session_count + resolved_spec.purge_session_count
    )
    validation_indices = range(
        validation_start + resolved_spec.feature_lookback_sessions,
        resolved_spec.history_session_count - 1,
    )
    development_counts = [
        sum(row[index] for index in development_indices) for row in availability_rows
    ]
    validation_counts = [
        sum(row[index] for index in validation_indices) for row in availability_rows
    ]
    validation_session_counts = [
        sum(row[index] for row in availability_rows) for index in validation_indices
    ]
    source = KisBroadD1GeometryAuditSource(
        dataset_hash=selection.dataset_hash,
        manifest_sha256=selection.manifest_sha256,
        materialization_receipt_sha256=selection.materialization_receipt_sha256,
        source_index_hash=selection.index_sha256,
        selected_target_key_set_hash=selection.selected_target_key_set_hash,
        full_target_count=selection.full_target_count,
        coverage_eligible_target_count=selection.coverage_eligible_target_count,
        selected_target_count=len(selection.selected_target_keys),
        raw_byte_attested_target_count=selection.raw_byte_attested_target_count,
        common_session_count=len(grid),
        common_session_grid_sha256=_sha256_payload(
            {"session_starts": [item.isoformat() for item in grid]}
        ),
    )
    return KisBroadD1GeometryAudit(
        source=source,
        spec=resolved_spec,
        ratio_bins=ratio_bins,
        feature_event_mask_sha256=_sha256_bool_matrix(event_rows),
        feature_event_count=sum(sum(row) for row in event_rows),
        feature_event_target_count=sum(any(row) for row in event_rows),
        feature_event_session_count=sum(
            any(row[index] for row in event_rows) for index in range(len(grid))
        ),
        development_available_pair_count=sum(development_counts),
        development_available_per_target_min=min(development_counts),
        development_available_per_target_max=max(development_counts),
        validation_available_pair_count=sum(validation_counts),
        validation_available_per_target_min=min(validation_counts),
        validation_available_per_target_max=max(validation_counts),
        validation_available_per_session_min=min(validation_session_counts),
        validation_available_per_session_max=max(validation_session_counts),
        validation_sessions_below_minimum_count=sum(
            count < resolved_spec.minimum_validation_available_target_count
            for count in validation_session_counts
        ),
        contract_sha256=_sha256_payload(_contract_payload(source, resolved_spec)),
    )


def run_kis_broad_d1_geometry_audit(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str,
    cache_root: Path | str,
    panel_root: Path | str,
    artifact_root: Path | str = KIS_BROAD_D1_GEOMETRY_AUDIT_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
    spec: KisBroadD1GeometryAuditSpec | None = None,
) -> KisBroadD1GeometryAuditRun:
    """Write one immutable external receipt for the fixed source-local audit."""

    if not _RUN_LABEL.fullmatch(run_label):
        raise ValueError("KIS broad D1 geometry audit run label is invalid")
    repository = Path(repo_root or Path.cwd()).resolve()
    root = ensure_external_artifact_directory(
        Path(artifact_root),
        repository,
        *KIS_BROAD_D1_GEOMETRY_AUDIT_DIRECTORY.split("/"),
    )
    output_directory = root / run_label
    if output_directory.exists() or output_directory.is_symlink():
        raise FileExistsError("KIS broad D1 geometry audit artifact is immutable")
    output_directory.mkdir()
    if output_directory.is_symlink() or output_directory.resolve(strict=True) != output_directory:
        raise ValueError("KIS broad D1 geometry audit artifact path is invalid")
    try:
        audit = build_kis_broad_d1_geometry_audit(
            manifest_path=manifest_path,
            materialization_receipt_path=materialization_receipt_path,
            cache_root=cache_root,
            panel_root=panel_root,
            repo_root=repository,
            spec=spec,
        )
    except KisBroadD1GeometryAuditUnavailable as error:
        receipt_path = output_directory / "input-unavailable.json"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_BROAD_D1_GEOMETRY_AUDIT_ID,
            "status": "input_unavailable",
            "reason": error.code,
            "artifact_policy": _artifact_policy(),
        }
        receipt_sha256 = _write_json_new(receipt_path, payload)
        return KisBroadD1GeometryAuditRun(
            status="input_unavailable",
            run_directory=output_directory,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
            audit=None,
        )
    receipt_path = output_directory / "summary.json"
    receipt_sha256 = _write_json_new(receipt_path, audit.payload())
    return KisBroadD1GeometryAuditRun(
        status="completed",
        run_directory=output_directory,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        audit=audit,
    )


def _common_grid(
    selection: KisPaperDailyBroadPanelSelection,
    spec: KisBroadD1GeometryAuditSpec,
) -> tuple[datetime, ...]:
    records = selection.bars_by_target[selection.selected_target_keys[0]].bars
    grid_start = -(spec.history_session_count + spec.terminal_buffer_sessions)
    grid_end = -spec.terminal_buffer_sessions
    grid = tuple(item.start_ts for item in records[grid_start:grid_end])
    if len(grid) != spec.history_session_count or tuple(sorted(grid)) != grid:
        raise KisBroadD1GeometryAuditUnavailable("invalid_common_session_grid")
    for target_key in selection.selected_target_keys:
        sessions = {item.start_ts for item in selection.bars_by_target[target_key].bars}
        if not all(session in sessions for session in grid):
            raise KisBroadD1GeometryAuditUnavailable("common_session_grid_drift")
    return grid


def _records_on_grid(records: tuple[Bar, ...], grid: tuple[datetime, ...]) -> tuple[Bar, ...]:
    by_session = {item.start_ts: item for item in records}
    try:
        selected = tuple(by_session[session] for session in grid)
    except KeyError as error:
        raise KisBroadD1GeometryAuditUnavailable("common_session_grid_drift") from error
    if any(not item.complete for item in selected):
        raise KisBroadD1GeometryAuditUnavailable("incomplete_bar")
    return selected


def _event_flags(records: tuple[Bar, ...], spec: KisBroadD1GeometryAuditSpec) -> list[bool]:
    flags: list[bool] = []
    for record in records:
        open_value = float(record.open)
        high_value = float(record.high)
        low_value = float(record.low)
        close_value = float(record.close)
        if (
            not all(
                math.isfinite(value) and value > 0.0
                for value in (open_value, high_value, low_value, close_value)
            )
            or high_value < max(open_value, close_value)
            or low_value > min(open_value, close_value)
        ):
            raise KisBroadD1GeometryAuditUnavailable("malformed_within_bar_geometry")
        flags.append(high_value / low_value > spec.maximum_within_bar_range_ratio)
    return flags


def _ratio_exceeds(record: Bar, threshold: float) -> bool:
    return float(record.high) / float(record.low) > threshold


def _feature_availability(
    events: list[bool], spec: KisBroadD1GeometryAuditSpec
) -> list[bool]:
    availability = [False] * len(events)
    for index in range(spec.feature_lookback_sessions, len(events) - 1):
        availability[index] = not any(
            events[index - spec.feature_lookback_sessions + 1 : index + 1]
        )
    return availability


def _contract_payload(
    source: KisBroadD1GeometryAuditSource,
    spec: KisBroadD1GeometryAuditSpec,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_GEOMETRY_AUDIT_ID,
        "source": source.payload(),
        "spec": spec.payload(),
        "target_event_censoring": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "external_artifact_only": True,
        "raw_market_data_persisted": False,
        "raw_rows_persisted": False,
        "prices_persisted": False,
        "volumes_persisted": False,
        "targets_persisted": False,
        "predictions_persisted": False,
        "model_weights_persisted": False,
        "credentials_read": False,
        "network_access": False,
        "kis_accessed": False,
        "broker_access": False,
        "gpu_used": False,
    }


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            str(path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FileExistsError("KIS broad D1 geometry audit receipt is immutable") from error
    try:
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("KIS broad D1 geometry audit receipt write failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _sha256_bytes(encoded)


def _sha256_bool_matrix(values: list[list[bool]]) -> str:
    encoded = bytes(value for row in values for value in row)
    return _sha256_bytes(encoded)


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True

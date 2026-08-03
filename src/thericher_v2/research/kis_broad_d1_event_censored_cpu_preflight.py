"""One source-local event-censored CPU preflight for the KIS broad-D1 panel.

The first broad-D1 CPU preflight rejected every within-bar range event.  This
separate candidate preserves that fixed 2.0 definition but censors only a
decision whose completed-bar feature window contains such an event.  It is an
aggregate classification diagnostic, never a pricing, selection, PnL, Paper,
or promotion result.
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
from types import MappingProxyType
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_broad_d1_geometry_audit import (
    KIS_BROAD_D1_GEOMETRY_AUDIT_ID,
    KisBroadD1GeometryAudit,
    KisBroadD1GeometryAuditSpec,
    KisBroadD1GeometryAuditUnavailable,
    build_kis_broad_d1_geometry_audit_from_selection,
)
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanelSelection,
    load_materialized_kis_paper_daily_broad_panel_selection,
)

from .artifact_paths import ensure_external_artifact_directory, reject_repo_artifact_path
from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)

KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID = "kis-broad-d1-event-censored-cpu-preflight-v1"
KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts"
)
KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_TRIAL_FAMILY = "kis-broad-d1-event-censored-cpu"
KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_FEATURE_NAMES = (
    "within_bar_log_return",
    "within_bar_log_range",
    "within_bar_close_location",
    "trailing_5_session_within_bar_log_return_mean",
    "trailing_20_session_within_bar_log_return_mean",
)
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_ALLOWED_REVIEW_STATUSES = frozenset({"uncertain", "supported-with-limits", "review_unavailable"})


class KisBroadD1EventCensoredCpuInputUnavailable(ValueError):
    """A fixed input, causal availability, or class condition is unavailable."""

    def __init__(self, code: str) -> None:
        if not code or not code.replace("_", "").isalnum():
            raise ValueError("event-censored preflight unavailable code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KisBroadD1EventCensoredCpuPreflightSpec:
    """Frozen source geometry, event policy, model, and falsification budget."""

    cohort_target_count: int = 128
    history_session_count: int = 800
    terminal_buffer_sessions: int = 1
    feature_lookback_sessions: int = 20
    development_session_count: int = 520
    purge_session_count: int = 20
    validation_session_count: int = 260
    minimum_validation_available_target_count: int = 96
    maximum_within_bar_range_ratio: float = 2.0
    l2_inverse_strength: float = 0.1
    logistic_max_iterations: int = 300
    random_seed: int = 20_260_803
    selection_raw_byte_attestation_limit: int = 512
    session_bootstrap_draw_count: int = 2_000
    session_block_permutation_draw_count: int = 2_000
    per_target_permutation_draw_count: int = 2_000
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
            or not 1 <= self.minimum_validation_available_target_count <= self.cohort_target_count
            or not math.isfinite(self.maximum_within_bar_range_ratio)
            or self.maximum_within_bar_range_ratio != 2.0
            or not math.isfinite(self.l2_inverse_strength)
            or self.l2_inverse_strength <= 0.0
            or self.logistic_max_iterations < 1
            or self.random_seed < 0
            or self.selection_raw_byte_attestation_limit < self.cohort_target_count
            or self.session_bootstrap_draw_count < 2_000
            or self.session_block_permutation_draw_count < 2_000
            or self.per_target_permutation_draw_count < 2_000
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("event-censored CPU preflight spec is invalid")

    @property
    def development_decision_count(self) -> int:
        return self.development_session_count - self.feature_lookback_sessions - 1

    @property
    def validation_decision_count(self) -> int:
        return self.validation_session_count - self.feature_lookback_sessions - 1

    def geometry_audit_spec(self) -> KisBroadD1GeometryAuditSpec:
        return KisBroadD1GeometryAuditSpec(
            cohort_target_count=self.cohort_target_count,
            history_session_count=self.history_session_count,
            terminal_buffer_sessions=self.terminal_buffer_sessions,
            feature_lookback_sessions=self.feature_lookback_sessions,
            development_session_count=self.development_session_count,
            purge_session_count=self.purge_session_count,
            validation_session_count=self.validation_session_count,
            minimum_validation_available_target_count=(
                self.minimum_validation_available_target_count
            ),
            maximum_within_bar_range_ratio=self.maximum_within_bar_range_ratio,
            raw_byte_attestation_limit=self.selection_raw_byte_attestation_limit,
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "cohort_target_count": self.cohort_target_count,
            "cohort_selection": "lexicographic_first_coverage_eligible_no_score_or_rank",
            "history_session_count": self.history_session_count,
            "terminal_buffer_sessions": self.terminal_buffer_sessions,
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "feature_lookback_sessions": self.feature_lookback_sessions,
            "feature_names": list(KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_FEATURE_NAMES),
            "target": "next_completed_bar_within_bar_direction_tie_is_zero",
            "event_definition": "high_low_ratio_gt_fixed_2",
            "feature_event_censoring": "t_minus_19_through_t_completed_bars_only",
            "target_event_censoring": False,
            "minimum_validation_available_target_count": (
                self.minimum_validation_available_target_count
            ),
            "model": {
                "family": "pooled_l2_logistic",
                "l2_inverse_strength": self.l2_inverse_strength,
                "maximum_iterations": self.logistic_max_iterations,
                "gpu_used": False,
                "weights_persisted": False,
            },
            "falsification": {
                "baselines": [
                    "flat_zero_direction",
                    "per_target_development_majority_direction",
                    "current_session_cross_sectional_direction_majority",
                    "same_target_prior_within_bar_direction",
                ],
                "session_bootstrap_draw_count": self.session_bootstrap_draw_count,
                "session_block_permutation_draw_count": self.session_block_permutation_draw_count,
                "per_target_permutation_draw_count": self.per_target_permutation_draw_count,
                "acceptance_rule": (
                    "true_balanced_accuracy_above_both_95th_null_quantiles_and_"
                    "both_5th_percentile_session_bootstrap_advantages_above_zero"
                ),
            },
            "random_seed": self.random_seed,
            "selection_raw_byte_attestation_limit": self.selection_raw_byte_attestation_limit,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1EventCensoredCpuPreflightInput:
    """Reattested in-memory inputs with an explicit causal availability mask."""

    dataset_hash: str
    source_index_hash: str
    materialization_receipt_sha256: str
    target_key_set_hash: str
    geometry_audit_receipt_sha256: str
    geometry_audit_contract_sha256: str
    full_target_count: int
    coverage_eligible_target_count: int
    target_count: int
    raw_byte_attested_target_count: int
    common_session_start: datetime
    common_session_end: datetime
    spec: KisBroadD1EventCensoredCpuPreflightSpec
    development_features: Any
    development_labels: Any
    validation_features: Any
    validation_labels: Any
    validation_available: Any
    validation_baselines: Mapping[str, Any]
    development_feature_hash: str
    development_label_hash: str
    validation_feature_hash: str
    validation_label_hash: str
    validation_availability_hash: str
    feature_event_mask_sha256: str
    feature_event_count: int
    zero_target_count: int
    zero_range_feature_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        numpy = _numpy()
        baselines = MappingProxyType(dict(self.validation_baselines))
        development_features = numpy.asarray(self.development_features, dtype=numpy.float64)
        development_labels = numpy.asarray(self.development_labels, dtype=numpy.int8)
        validation_features = numpy.asarray(self.validation_features, dtype=numpy.float64)
        validation_labels = numpy.asarray(self.validation_labels, dtype=numpy.int8)
        validation_available = numpy.asarray(self.validation_available, dtype=numpy.bool_)
        expected_validation_shape = (self.target_count, self.spec.validation_decision_count)
        if (
            any(
                not _is_sha256(value)
                for value in (
                    self.dataset_hash,
                    self.source_index_hash,
                    self.materialization_receipt_sha256,
                    self.target_key_set_hash,
                    self.geometry_audit_receipt_sha256,
                    self.geometry_audit_contract_sha256,
                    self.development_feature_hash,
                    self.development_label_hash,
                    self.validation_feature_hash,
                    self.validation_label_hash,
                    self.validation_availability_hash,
                    self.feature_event_mask_sha256,
                )
            )
            or self.full_target_count < self.coverage_eligible_target_count
            or self.coverage_eligible_target_count < self.target_count
            or self.target_count != self.spec.cohort_target_count
            or self.raw_byte_attested_target_count < self.target_count
            or self.raw_byte_attested_target_count > self.coverage_eligible_target_count
            or self.common_session_end <= self.common_session_start
            or development_features.ndim != 2
            or development_features.shape[1]
            != len(KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_FEATURE_NAMES)
            or development_features.shape[0] != development_labels.size
            or development_features.shape[0] < 2
            or validation_features.shape
            != (
                self.target_count,
                self.spec.validation_decision_count,
                len(KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_FEATURE_NAMES),
            )
            or validation_labels.shape != expected_validation_shape
            or validation_available.shape != expected_validation_shape
            or set(baselines)
            != {
                "flat_zero_direction",
                "per_target_development_majority_direction",
                "current_session_cross_sectional_direction_majority",
                "same_target_prior_within_bar_direction",
            }
            or any(
                numpy.asarray(values, dtype=numpy.int8).shape != expected_validation_shape
                for values in baselines.values()
            )
            or not numpy.isfinite(development_features).all()
            or not numpy.isfinite(validation_features).all()
            or not set(numpy.unique(development_labels)).issubset({0, 1})
            or not set(numpy.unique(validation_labels)).issubset({0, 1})
            or any(
                not set(numpy.unique(numpy.asarray(values, dtype=numpy.int8))).issubset({0, 1})
                for values in baselines.values()
            )
            or len(numpy.unique(development_labels)) != 2
            or len(numpy.unique(validation_labels[validation_available])) != 2
            or int(validation_available.sum()) < self.spec.minimum_validation_available_target_count
            or self.development_feature_hash != _sha256_array(development_features)
            or self.development_label_hash != _sha256_array(development_labels)
            or self.validation_feature_hash != _sha256_array(validation_features)
            or self.validation_label_hash != _sha256_array(validation_labels)
            or self.validation_availability_hash != _sha256_array(validation_available)
            or self.feature_event_count < 0
            or self.zero_target_count < 0
            or self.zero_range_feature_count < 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("event-censored CPU preflight input is invalid")
        object.__setattr__(self, "development_features", development_features)
        object.__setattr__(self, "development_labels", development_labels)
        object.__setattr__(self, "validation_features", validation_features)
        object.__setattr__(self, "validation_labels", validation_labels)
        object.__setattr__(self, "validation_available", validation_available)
        object.__setattr__(self, "validation_baselines", baselines)

    @property
    def development_pair_count(self) -> int:
        return int(self.development_labels.size)

    @property
    def validation_pair_count(self) -> int:
        return int(self.validation_available.sum())

    @property
    def split_hash(self) -> str:
        return _sha256_payload(
            {
                "common_session_start": self.common_session_start.isoformat(),
                "common_session_end": self.common_session_end.isoformat(),
                "history_session_count": self.spec.history_session_count,
                "terminal_buffer_sessions": self.spec.terminal_buffer_sessions,
                "development_session_count": self.spec.development_session_count,
                "purge_session_count": self.spec.purge_session_count,
                "validation_session_count": self.spec.validation_session_count,
                "feature_lookback_sessions": self.spec.feature_lookback_sessions,
            }
        )

    @property
    def cost_model_hash(self) -> str:
        return _sha256_payload({"kind": "no_execution_or_cost_model"})


@dataclass(frozen=True, slots=True)
class KisBroadD1EventCensoredCpuPreflightRun:
    """Immutable external evidence for one candidate invocation."""

    status: Literal["completed", "input_unavailable"]
    run_directory: Path
    receipt_path: Path
    receipt_sha256: str
    contract_sha256: str | None
    frozen_campaign: FrozenCampaignRegistryEntry | None
    outcome: CampaignOutcomeRegistryEntry | None

    def __post_init__(self) -> None:
        if (
            self.status not in {"completed", "input_unavailable"}
            or not self.run_directory.is_dir()
            or not self.receipt_path.is_file()
            or not _is_sha256(self.receipt_sha256)
            or _sha256_file(self.receipt_path) != self.receipt_sha256
            or (self.status == "completed") != (self.contract_sha256 is not None)
            or (self.status == "completed") != (self.frozen_campaign is not None)
            or (self.status == "completed") != (self.outcome is not None)
        ):
            raise ValueError("event-censored CPU preflight run is invalid")


def build_kis_broad_d1_event_censored_cpu_preflight_input(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str,
    geometry_audit_receipt_path: Path | str,
    cache_root: Path | str,
    panel_root: Path | str,
    repo_root: Path | str | None = None,
    spec: KisBroadD1EventCensoredCpuPreflightSpec | None = None,
) -> KisBroadD1EventCensoredCpuPreflightInput:
    """Reattach the frozen subset and exact audit before deriving any model input."""

    resolved_spec = spec or KisBroadD1EventCensoredCpuPreflightSpec()
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
            raw_byte_attestation_limit=resolved_spec.selection_raw_byte_attestation_limit,
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
        raise KisBroadD1EventCensoredCpuInputUnavailable(reason) from error
    try:
        audit = build_kis_broad_d1_geometry_audit_from_selection(
            selection,
            spec=resolved_spec.geometry_audit_spec(),
        )
    except KisBroadD1GeometryAuditUnavailable as error:
        raise KisBroadD1EventCensoredCpuInputUnavailable(
            f"geometry_audit_{error.code}"
        ) from error
    receipt_sha256 = _reattest_geometry_audit_receipt(
        geometry_audit_receipt_path,
        expected=audit,
        repo_root=_repository_root(repo_root),
    )
    return build_kis_broad_d1_event_censored_cpu_preflight_input_from_selection(
        selection,
        geometry_audit=audit,
        geometry_audit_receipt_sha256=receipt_sha256,
        spec=resolved_spec,
    )


def build_kis_broad_d1_event_censored_cpu_preflight_input_from_selection(
    selection: KisPaperDailyBroadPanelSelection,
    *,
    geometry_audit: KisBroadD1GeometryAudit,
    geometry_audit_receipt_sha256: str,
    spec: KisBroadD1EventCensoredCpuPreflightSpec | None = None,
) -> KisBroadD1EventCensoredCpuPreflightInput:
    """Derive one fixed causal input from an already reattested selected subset."""

    if not isinstance(selection, KisPaperDailyBroadPanelSelection):
        raise TypeError("event-censored CPU preflight requires a selected broad panel")
    resolved_spec = spec or KisBroadD1EventCensoredCpuPreflightSpec()
    if (
        not isinstance(geometry_audit, KisBroadD1GeometryAudit)
        or not _is_sha256(geometry_audit_receipt_sha256)
        or selection.dataset_id != KIS_PAPER_DAILY_BROAD_PANEL_ID
        or len(selection.selected_target_keys) != resolved_spec.cohort_target_count
        or selection.minimum_bar_count
        != resolved_spec.history_session_count + resolved_spec.terminal_buffer_sessions
        or selection.common_session_count != resolved_spec.history_session_count
        or selection.terminal_buffer_sessions != resolved_spec.terminal_buffer_sessions
        or selection.coverage_eligible_target_count < resolved_spec.cohort_target_count
        or selection.raw_byte_attested_target_count < resolved_spec.cohort_target_count
        or geometry_audit.spec != resolved_spec.geometry_audit_spec()
        or geometry_audit.source.dataset_hash != selection.dataset_hash
        or geometry_audit.source.manifest_sha256 != selection.manifest_sha256
        or geometry_audit.source.materialization_receipt_sha256
        != selection.materialization_receipt_sha256
        or geometry_audit.source.source_index_hash != selection.index_sha256
        or geometry_audit.source.selected_target_key_set_hash
        != selection.selected_target_key_set_hash
        or not geometry_audit.event_censored_candidate_input_eligible
    ):
        raise KisBroadD1EventCensoredCpuInputUnavailable("geometry_audit_contract_mismatch")

    numpy = _numpy()
    grid = _common_grid(selection, resolved_spec)
    development_indices = range(
        resolved_spec.feature_lookback_sessions,
        resolved_spec.development_session_count - 1,
    )
    validation_start = resolved_spec.development_session_count + resolved_spec.purge_session_count
    validation_indices = range(
        validation_start + resolved_spec.feature_lookback_sessions,
        resolved_spec.history_session_count - 1,
    )
    development_features: list[Any] = []
    development_labels: list[Any] = []
    validation_features: list[Any] = []
    validation_labels: list[Any] = []
    validation_available: list[Any] = []
    validation_current_directions: list[Any] = []
    event_rows: list[list[bool]] = []
    zero_target_count = 0
    zero_range_feature_count = 0

    for target_key in selection.selected_target_keys:
        records = _records_on_grid(selection.bars_by_target[target_key].bars, grid)
        geometry, directions, events, target_zeros, range_zeros = _geometry(records, resolved_spec)
        availability = _feature_availability(events, resolved_spec)
        event_rows.append(events)
        zero_target_count += target_zeros
        zero_range_feature_count += range_zeros
        development_mask = numpy.asarray(
            [availability[index] for index in development_indices], dtype=numpy.bool_
        )
        validation_mask = numpy.asarray(
            [availability[index] for index in validation_indices], dtype=numpy.bool_
        )
        development_rows = _feature_rows(geometry, development_indices, resolved_spec, numpy)
        validation_rows = _feature_rows(geometry, validation_indices, resolved_spec, numpy)
        development_target_labels = directions[[index + 1 for index in development_indices]]
        validation_target_labels = directions[[index + 1 for index in validation_indices]]
        development_features.append(development_rows[development_mask])
        development_labels.append(development_target_labels[development_mask])
        validation_features.append(validation_rows)
        validation_labels.append(validation_target_labels)
        validation_available.append(validation_mask)
        validation_current_directions.append(geometry[list(validation_indices), 0] > 0.0)

    event_mask_sha256 = _sha256_bool_matrix(event_rows)
    if (
        event_mask_sha256 != geometry_audit.feature_event_mask_sha256
        or sum(sum(row) for row in event_rows) != geometry_audit.feature_event_count
        or sum(any(row) for row in event_rows) != geometry_audit.feature_event_target_count
        or sum(any(row[index] for row in event_rows) for index in range(len(grid)))
        != geometry_audit.feature_event_session_count
    ):
        raise KisBroadD1EventCensoredCpuInputUnavailable("geometry_audit_event_mask_mismatch")

    development_feature_matrix = numpy.concatenate(development_features, axis=0)
    development_label_vector = numpy.concatenate(development_labels, axis=0).astype(numpy.int8)
    validation_feature_matrix = numpy.stack(validation_features, axis=0)
    validation_label_matrix = numpy.stack(validation_labels, axis=0).astype(numpy.int8)
    validation_mask_matrix = numpy.stack(validation_available, axis=0).astype(numpy.bool_)
    validation_current_matrix = numpy.stack(validation_current_directions, axis=0).astype(
        numpy.int8
    )
    if any(
        count < resolved_spec.minimum_validation_available_target_count
        for count in validation_mask_matrix.sum(axis=0)
    ):
        raise KisBroadD1EventCensoredCpuInputUnavailable(
            "validation_event_censoring_coverage_short"
        )
    if len(numpy.unique(development_label_vector)) != 2:
        raise KisBroadD1EventCensoredCpuInputUnavailable("development_class_variation_missing")
    if len(numpy.unique(validation_label_matrix[validation_mask_matrix])) != 2:
        raise KisBroadD1EventCensoredCpuInputUnavailable("validation_class_variation_missing")

    development_majority = numpy.asarray(
        [int(labels.mean() > 0.5) for labels in development_labels], dtype=numpy.int8
    )
    cross_sectional_majority = numpy.empty(
        (resolved_spec.validation_decision_count,), dtype=numpy.int8
    )
    for index in range(resolved_spec.validation_decision_count):
        current = validation_current_matrix[:, index]
        available = validation_mask_matrix[:, index]
        cross_sectional_majority[index] = int(current[available].mean() > 0.5)
    baselines = {
        "flat_zero_direction": numpy.zeros_like(validation_label_matrix, dtype=numpy.int8),
        "per_target_development_majority_direction": numpy.repeat(
            development_majority[:, None],
            resolved_spec.validation_decision_count,
            axis=1,
        ),
        "current_session_cross_sectional_direction_majority": numpy.repeat(
            cross_sectional_majority[None, :],
            len(selection.selected_target_keys),
            axis=0,
        ),
        "same_target_prior_within_bar_direction": validation_current_matrix,
    }
    return KisBroadD1EventCensoredCpuPreflightInput(
        dataset_hash=selection.dataset_hash,
        source_index_hash=selection.index_sha256,
        materialization_receipt_sha256=selection.materialization_receipt_sha256,
        target_key_set_hash=selection.selected_target_key_set_hash,
        geometry_audit_receipt_sha256=geometry_audit_receipt_sha256,
        geometry_audit_contract_sha256=geometry_audit.contract_sha256,
        full_target_count=selection.full_target_count,
        coverage_eligible_target_count=selection.coverage_eligible_target_count,
        target_count=len(selection.selected_target_keys),
        raw_byte_attested_target_count=selection.raw_byte_attested_target_count,
        common_session_start=grid[0],
        common_session_end=grid[-1],
        spec=resolved_spec,
        development_features=development_feature_matrix,
        development_labels=development_label_vector,
        validation_features=validation_feature_matrix,
        validation_labels=validation_label_matrix,
        validation_available=validation_mask_matrix,
        validation_baselines=baselines,
        development_feature_hash=_sha256_array(development_feature_matrix),
        development_label_hash=_sha256_array(development_label_vector),
        validation_feature_hash=_sha256_array(validation_feature_matrix),
        validation_label_hash=_sha256_array(validation_label_matrix),
        validation_availability_hash=_sha256_array(validation_mask_matrix),
        feature_event_mask_sha256=event_mask_sha256,
        feature_event_count=geometry_audit.feature_event_count,
        zero_target_count=zero_target_count,
        zero_range_feature_count=zero_range_feature_count,
    )


def run_kis_broad_d1_event_censored_cpu_preflight(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str,
    geometry_audit_receipt_path: Path | str,
    cache_root: Path | str,
    panel_root: Path | str,
    artifact_root: Path | str = KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ARTIFACT_ROOT,
    run_label: str,
    review_status: str,
    repo_root: Path | str | None = None,
    spec: KisBroadD1EventCensoredCpuPreflightSpec | None = None,
) -> KisBroadD1EventCensoredCpuPreflightRun:
    """Freeze and run one source-local CPU candidate, or contain its input failure."""

    if not _RUN_LABEL.fullmatch(run_label):
        raise ValueError("event-censored CPU preflight run label is invalid")
    if review_status not in _ALLOWED_REVIEW_STATUSES:
        raise ValueError("event-censored CPU preflight review status is invalid")
    repository = _repository_root(repo_root)
    resolved_spec = spec or KisBroadD1EventCensoredCpuPreflightSpec()
    output_directory = _prepare_output_directory(
        artifact_root=Path(artifact_root),
        repo_root=repository,
        run_label=run_label,
    )
    try:
        preflight_input = build_kis_broad_d1_event_censored_cpu_preflight_input(
            manifest_path=manifest_path,
            materialization_receipt_path=materialization_receipt_path,
            geometry_audit_receipt_path=geometry_audit_receipt_path,
            cache_root=cache_root,
            panel_root=panel_root,
            repo_root=repository,
            spec=resolved_spec,
        )
    except KisBroadD1EventCensoredCpuInputUnavailable as error:
        receipt_path = output_directory / "input-unavailable.json"
        receipt_sha256 = _write_json_new(
            receipt_path,
            _input_unavailable_payload(
                spec=resolved_spec,
                review_status=review_status,
                reason=error.code,
            ),
        )
        return KisBroadD1EventCensoredCpuPreflightRun(
            status="input_unavailable",
            run_directory=output_directory,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
            contract_sha256=None,
            frozen_campaign=None,
            outcome=None,
        )

    precommit = _precommit_payload(preflight_input, review_status=review_status)
    contract_sha256 = _sha256_payload(precommit)
    frozen_campaign = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=preflight_input.dataset_hash,
        split_hash=preflight_input.split_hash,
        cost_model_hash=preflight_input.cost_model_hash,
        trial_family=KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_TRIAL_FAMILY,
        holdout_access="none",
        artifact_root=Path(artifact_root),
        repo_root=repository,
    )
    _write_json_new(
        output_directory / "precommit.json",
        {
            **precommit,
            "campaign_contract_hash": contract_sha256,
            "campaign_registry_record_sha256": frozen_campaign.record_sha256,
        },
    )
    metrics = _fit_and_evaluate(preflight_input)
    receipt_path = output_directory / "summary.json"
    receipt_sha256 = _write_json_new(
        receipt_path,
        _summary_payload(
            preflight_input,
            contract_sha256=contract_sha256,
            review_status=review_status,
            metrics=metrics,
        ),
    )
    outcome = register_campaign_outcome(
        contract_hash=contract_sha256,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=receipt_sha256,
        artifact_root=Path(artifact_root),
        repo_root=repository,
    )
    return KisBroadD1EventCensoredCpuPreflightRun(
        status="completed",
        run_directory=output_directory,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        contract_sha256=contract_sha256,
        frozen_campaign=frozen_campaign,
        outcome=outcome,
    )


def _common_grid(
    selection: KisPaperDailyBroadPanelSelection,
    spec: KisBroadD1EventCensoredCpuPreflightSpec,
) -> tuple[datetime, ...]:
    records = selection.bars_by_target[selection.selected_target_keys[0]].bars
    start = -(spec.history_session_count + spec.terminal_buffer_sessions)
    grid = tuple(item.start_ts for item in records[start : -spec.terminal_buffer_sessions])
    if len(grid) != spec.history_session_count or tuple(sorted(grid)) != grid:
        raise KisBroadD1EventCensoredCpuInputUnavailable("invalid_common_session_grid")
    return grid


def _records_on_grid(records: tuple[Bar, ...], grid: tuple[datetime, ...]) -> tuple[Bar, ...]:
    by_session = {record.start_ts: record for record in records}
    try:
        selected = tuple(by_session[session] for session in grid)
    except KeyError as error:
        raise KisBroadD1EventCensoredCpuInputUnavailable("common_session_grid_drift") from error
    if any(
        record.timeframe is not Timeframe.D1
        or record.market != "US"
        or not record.complete
        or record.start_ts != session
        for record, session in zip(selected, grid, strict=True)
    ):
        raise KisBroadD1EventCensoredCpuInputUnavailable("incomplete_or_misaligned_bar")
    return selected


def _geometry(
    records: tuple[Bar, ...],
    spec: KisBroadD1EventCensoredCpuPreflightSpec,
) -> tuple[Any, Any, list[bool], int, int]:
    numpy = _numpy()
    geometry = numpy.empty((len(records), 3), dtype=numpy.float64)
    directions = numpy.empty((len(records),), dtype=numpy.int8)
    events: list[bool] = []
    zero_target_count = 0
    zero_range_feature_count = 0
    for index, record in enumerate(records):
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
            raise KisBroadD1EventCensoredCpuInputUnavailable("malformed_within_bar_geometry")
        within_bar_return = math.log(close_value / open_value)
        within_bar_range = math.log(high_value / low_value)
        if high_value == low_value:
            close_location = 0.0
            zero_range_feature_count += 1
        else:
            close_location = (close_value - low_value) / (high_value - low_value) - 0.5
        if not all(
            math.isfinite(value)
            for value in (within_bar_return, within_bar_range, close_location)
        ):
            raise KisBroadD1EventCensoredCpuInputUnavailable("non_finite_within_bar_geometry")
        geometry[index] = (within_bar_return, within_bar_range, close_location)
        directions[index] = int(within_bar_return > 0.0)
        events.append(high_value / low_value > spec.maximum_within_bar_range_ratio)
        if within_bar_return == 0.0:
            zero_target_count += 1
    return geometry, directions, events, zero_target_count, zero_range_feature_count


def _feature_availability(
    events: list[bool], spec: KisBroadD1EventCensoredCpuPreflightSpec
) -> list[bool]:
    available = [False] * len(events)
    for index in range(spec.feature_lookback_sessions, len(events) - 1):
        available[index] = not any(events[index - spec.feature_lookback_sessions + 1 : index + 1])
    return available


def _feature_rows(
    geometry: Any,
    indices: range,
    spec: KisBroadD1EventCensoredCpuPreflightSpec,
    numpy: Any,
) -> Any:
    values = numpy.asarray(geometry, dtype=numpy.float64)
    rows = numpy.empty(
        (len(indices), len(KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_FEATURE_NAMES)),
        dtype=numpy.float64,
    )
    for row_index, session_index in enumerate(indices):
        if session_index < spec.feature_lookback_sessions:
            raise KisBroadD1EventCensoredCpuInputUnavailable(
                "feature_window_crosses_split_boundary"
            )
        current = values[session_index]
        rows[row_index] = (
            current[0],
            current[1],
            current[2],
            float(values[session_index - 4 : session_index + 1, 0].mean()),
            float(
                values[
                    session_index - spec.feature_lookback_sessions + 1 : session_index + 1,
                    0,
                ].mean()
            ),
        )
    if not numpy.isfinite(rows).all():
        raise KisBroadD1EventCensoredCpuInputUnavailable("non_finite_feature_matrix")
    return rows


def _fit_and_evaluate(
    preflight_input: KisBroadD1EventCensoredCpuPreflightInput,
) -> dict[str, object]:
    numpy = _numpy()
    LogisticRegression = _logistic_regression()
    feature_means = preflight_input.development_features.mean(axis=0)
    feature_scales = preflight_input.development_features.std(axis=0)
    if not numpy.isfinite(feature_means).all() or not numpy.isfinite(feature_scales).all():
        raise KisBroadD1EventCensoredCpuInputUnavailable("development_standardization_failure")
    constant_feature_count = int((feature_scales <= 1e-12).sum())
    feature_scales = numpy.where(feature_scales <= 1e-12, 1.0, feature_scales)
    model = LogisticRegression(
        C=preflight_input.spec.l2_inverse_strength,
        solver="lbfgs",
        max_iter=preflight_input.spec.logistic_max_iterations,
        random_state=preflight_input.spec.random_seed,
    )
    model.fit(
        (preflight_input.development_features - feature_means) / feature_scales,
        preflight_input.development_labels,
    )
    flat_validation = preflight_input.validation_features.reshape(
        -1,
        len(KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_FEATURE_NAMES),
    )
    probabilities = model.predict_proba((flat_validation - feature_means) / feature_scales)[:, 1]
    probabilities = probabilities.reshape(
        preflight_input.target_count,
        preflight_input.spec.validation_decision_count,
    )
    if (
        not numpy.isfinite(probabilities).all()
        or numpy.any(probabilities < 0.0)
        or numpy.any(probabilities > 1.0)
    ):
        raise KisBroadD1EventCensoredCpuInputUnavailable("invalid_model_probabilities")
    predictions = (probabilities >= 0.5).astype(numpy.int8)
    labels = preflight_input.validation_labels
    available = preflight_input.validation_available
    baseline_scores = {
        name: _masked_balanced_accuracy(labels, values, available, numpy)
        for name, values in preflight_input.validation_baselines.items()
    }
    model_score = _masked_balanced_accuracy(labels, predictions, available, numpy)
    bootstrap = _session_bootstrap_advantages(
        labels=labels,
        probabilities=probabilities,
        predictions=predictions,
        baselines=preflight_input.validation_baselines,
        available=available,
        draw_count=preflight_input.spec.session_bootstrap_draw_count,
        seed=preflight_input.spec.random_seed + 1,
        numpy=numpy,
    )
    session_block_null = _session_block_permutation_quantile(
        labels=labels,
        predictions=predictions,
        available=available,
        draw_count=preflight_input.spec.session_block_permutation_draw_count,
        seed=preflight_input.spec.random_seed + 2,
        numpy=numpy,
    )
    per_target_null = _per_target_permutation_quantile(
        labels=labels,
        predictions=predictions,
        available=available,
        draw_count=preflight_input.spec.per_target_permutation_draw_count,
        seed=preflight_input.spec.random_seed + 3,
        numpy=numpy,
    )
    falsifiers_passed = (
        model_score > session_block_null
        and model_score > per_target_null
        and bootstrap["balanced_accuracy_advantage_lower_5th_percentile"] > 0.0
        and bootstrap["cross_sectional_residual_advantage_lower_5th_percentile"] > 0.0
    )
    return {
        "model_balanced_accuracy": model_score,
        "development_constant_feature_count": constant_feature_count,
        "baseline_balanced_accuracy": dict(sorted(baseline_scores.items())),
        "session_block_permutation_null_95th_percentile": session_block_null,
        "per_target_temporal_permutation_null_95th_percentile": per_target_null,
        **bootstrap,
        "causal_falsifiers_passed": falsifiers_passed,
        "model_weights_persisted": False,
        "prediction_rows_persisted": False,
    }


def _masked_balanced_accuracy(labels: Any, predictions: Any, available: Any, numpy: Any) -> float:
    selected_labels = numpy.asarray(labels, dtype=numpy.int8)[available]
    selected_predictions = numpy.asarray(predictions, dtype=numpy.int8)[available]
    positive = selected_labels == 1
    negative = selected_labels == 0
    if not positive.any() or not negative.any():
        raise KisBroadD1EventCensoredCpuInputUnavailable("validation_class_variation_missing")
    return float(
        (
            (selected_predictions[positive] == 1).mean()
            + (selected_predictions[negative] == 0).mean()
        )
        / 2.0
    )


def _session_bootstrap_advantages(
    *,
    labels: Any,
    probabilities: Any,
    predictions: Any,
    baselines: Mapping[str, Any],
    available: Any,
    draw_count: int,
    seed: int,
    numpy: Any,
) -> dict[str, float]:
    generator = numpy.random.default_rng(seed)
    session_count = labels.shape[1]
    balanced_advantages = numpy.empty((draw_count,), dtype=numpy.float64)
    residual_advantages = numpy.empty((draw_count,), dtype=numpy.float64)
    for draw in range(draw_count):
        sessions = generator.integers(0, session_count, size=session_count)
        sampled_labels = labels[:, sessions]
        sampled_available = available[:, sessions]
        model_score = _masked_balanced_accuracy(
            sampled_labels, predictions[:, sessions], sampled_available, numpy
        )
        baseline_score = max(
            _masked_balanced_accuracy(sampled_labels, values[:, sessions], sampled_available, numpy)
            for values in baselines.values()
        )
        balanced_advantages[draw] = model_score - baseline_score
        model_error = _masked_cross_sectional_residual_error(
            sampled_labels,
            probabilities[:, sessions],
            sampled_available,
            numpy,
        )
        baseline_error = min(
            _masked_cross_sectional_residual_error(
                sampled_labels, values[:, sessions], sampled_available, numpy
            )
            for values in baselines.values()
        )
        residual_advantages[draw] = baseline_error - model_error
    return {
        "balanced_accuracy_advantage_lower_5th_percentile": float(
            numpy.quantile(balanced_advantages, 0.05)
        ),
        "cross_sectional_residual_advantage_lower_5th_percentile": float(
            numpy.quantile(residual_advantages, 0.05)
        ),
    }


def _masked_cross_sectional_residual_error(
    labels: Any, values: Any, available: Any, numpy: Any
) -> float:
    errors: list[Any] = []
    for index in range(labels.shape[1]):
        mask = available[:, index]
        if int(mask.sum()) < 2:
            continue
        selected_labels = labels[:, index][mask]
        selected_values = values[:, index][mask]
        errors.append(
            (
                selected_values
                - selected_values.mean()
                - (selected_labels - selected_labels.mean())
            )
            ** 2
        )
    if not errors:
        raise KisBroadD1EventCensoredCpuInputUnavailable("cross_sectional_coverage_short")
    return float(numpy.concatenate(errors).mean())


def _session_block_permutation_quantile(
    *,
    labels: Any,
    predictions: Any,
    available: Any,
    draw_count: int,
    seed: int,
    numpy: Any,
) -> float:
    generator = numpy.random.default_rng(seed)
    session_count = labels.shape[1]
    scores = numpy.empty((draw_count,), dtype=numpy.float64)
    for draw in range(draw_count):
        scores[draw] = _masked_balanced_accuracy(
            labels[:, generator.permutation(session_count)], predictions, available, numpy
        )
    return float(numpy.quantile(scores, 0.95))


def _per_target_permutation_quantile(
    *,
    labels: Any,
    predictions: Any,
    available: Any,
    draw_count: int,
    seed: int,
    numpy: Any,
) -> float:
    generator = numpy.random.default_rng(seed)
    scores = numpy.empty((draw_count,), dtype=numpy.float64)
    for draw in range(draw_count):
        permuted = numpy.empty_like(labels)
        for target_index in range(labels.shape[0]):
            permuted[target_index] = labels[target_index, generator.permutation(labels.shape[1])]
        scores[draw] = _masked_balanced_accuracy(permuted, predictions, available, numpy)
    return float(numpy.quantile(scores, 0.95))


def _reattest_geometry_audit_receipt(
    path: Path | str,
    *,
    expected: KisBroadD1GeometryAudit,
    repo_root: Path,
) -> str:
    receipt_path = Path(path)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise KisBroadD1EventCensoredCpuInputUnavailable("geometry_audit_receipt_unavailable")
    _reject_symlink_components(receipt_path)
    resolved = receipt_path.resolve(strict=True)
    reject_repo_artifact_path(resolved, repo_root)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisBroadD1EventCensoredCpuInputUnavailable(
            "geometry_audit_receipt_unreadable"
        ) from error
    if not isinstance(payload, dict) or payload != expected.payload():
        raise KisBroadD1EventCensoredCpuInputUnavailable("geometry_audit_receipt_mismatch")
    return _sha256_file(resolved)


def _contract_payload(
    preflight_input: KisBroadD1EventCensoredCpuPreflightInput,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
        "dataset": {
            "dataset_id": KIS_PAPER_DAILY_BROAD_PANEL_ID,
            "dataset_hash": preflight_input.dataset_hash,
            "source_index_hash": preflight_input.source_index_hash,
            "materialization_receipt_sha256": preflight_input.materialization_receipt_sha256,
            "target_key_set_hash": preflight_input.target_key_set_hash,
            "full_target_count": preflight_input.full_target_count,
            "coverage_eligible_target_count": preflight_input.coverage_eligible_target_count,
            "cohort_target_count": preflight_input.target_count,
            "raw_byte_attested_target_count": preflight_input.raw_byte_attested_target_count,
            "timeframe": Timeframe.D1.value,
            "common_session_start": preflight_input.common_session_start.isoformat(),
            "common_session_end": preflight_input.common_session_end.isoformat(),
        },
        "geometry_audit": {
            "kind": KIS_BROAD_D1_GEOMETRY_AUDIT_ID,
            "receipt_sha256": preflight_input.geometry_audit_receipt_sha256,
            "contract_sha256": preflight_input.geometry_audit_contract_sha256,
            "feature_event_mask_sha256": preflight_input.feature_event_mask_sha256,
            "feature_event_count": preflight_input.feature_event_count,
        },
        "input_hashes": {
            "development_features": preflight_input.development_feature_hash,
            "development_labels": preflight_input.development_label_hash,
            "validation_features": preflight_input.validation_feature_hash,
            "validation_labels": preflight_input.validation_label_hash,
            "validation_availability": preflight_input.validation_availability_hash,
        },
        "spec": preflight_input.spec.safe_payload(),
        "cost_model": {"kind": "no_execution_or_cost_model"},
    }


def _precommit_payload(
    preflight_input: KisBroadD1EventCensoredCpuPreflightInput, *, review_status: str
) -> dict[str, object]:
    return {
        **_contract_payload(preflight_input),
        "status": "precommitted",
        "claim": (
            "one source-local event-censored causal CPU preflight on completed KIS D1 bars; "
            "aggregate classification diagnostics only, never a profitability, selection, ranking, "
            "ensemble, Paper, or live claim"
        ),
        "availability": {
            "features_use_completed_bar_t_or_earlier": True,
            "target_uses_next_completed_bar": True,
            "terminal_panel_session_excluded": True,
            "target_tie_rule": "zero_direction",
            "event_definition": "high_low_ratio_gt_fixed_2",
            "feature_window_censoring": "t_minus_19_through_t_completed_bars_only",
            "target_event_censoring": False,
            "all_baselines_bootstraps_and_nulls_use_same_availability_mask": True,
        },
        "sample_counts": {
            "development_available_pairs": preflight_input.development_pair_count,
            "validation_available_pairs": preflight_input.validation_pair_count,
            "validation_available_per_session_min": int(
                preflight_input.validation_available.sum(axis=0).min()
            ),
            "validation_available_per_session_max": int(
                preflight_input.validation_available.sum(axis=0).max()
            ),
        },
        "source_limitations": [
            "current_listing_only_not_point_in_time_universe",
            "non_pit_registry_scope",
            "MODP_0_unadjusted",
            "corporate_action_semantics_not_qualified",
            "session_finality_unattested",
            "development_coverage_only_not_research_ready",
            "range_event_censoring_is_hygiene_not_performance_evidence",
        ],
        "review": {
            "reviewer": "claude_cli_falsification_first",
            "status": review_status,
            "resolution": (
                "fixed_2_range_event_censoring, same-mask controls, session-block and "
                "per-target temporal nulls, and non-promoting scope frozen"
            ),
        },
        "permissions": _permission_payload(),
        "promotion": _promotion_payload(),
    }


def _input_unavailable_payload(
    *,
    spec: KisBroadD1EventCensoredCpuPreflightSpec,
    review_status: str,
    reason: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
        "status": "input_unavailable",
        "reason": reason,
        "spec": spec.safe_payload(),
        "review_status": review_status,
        "permissions": _permission_payload(),
        "promotion": _promotion_payload(),
    }


def _summary_payload(
    preflight_input: KisBroadD1EventCensoredCpuPreflightInput,
    *,
    contract_sha256: str,
    review_status: str,
    metrics: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
        "status": "completed",
        "campaign_contract_hash": contract_sha256,
        "review_status": review_status,
        "source": {
            "dataset_id": KIS_PAPER_DAILY_BROAD_PANEL_ID,
            "dataset_hash": preflight_input.dataset_hash,
            "source_index_hash": preflight_input.source_index_hash,
            "materialization_receipt_sha256": preflight_input.materialization_receipt_sha256,
            "target_key_set_hash": preflight_input.target_key_set_hash,
            "full_target_count": preflight_input.full_target_count,
            "coverage_eligible_target_count": preflight_input.coverage_eligible_target_count,
            "cohort_target_count": preflight_input.target_count,
            "raw_byte_attested_target_count": preflight_input.raw_byte_attested_target_count,
            "current_listing_only": True,
            "non_pit": True,
            "adjustment_mode": "MODP=0_unadjusted",
            "corporate_action_qualified": False,
            "session_finality_attested": False,
        },
        "geometry_audit": {
            "receipt_sha256": preflight_input.geometry_audit_receipt_sha256,
            "contract_sha256": preflight_input.geometry_audit_contract_sha256,
            "feature_event_mask_sha256": preflight_input.feature_event_mask_sha256,
            "feature_event_count": preflight_input.feature_event_count,
        },
        "sample_counts": {
            "development_available_pairs": preflight_input.development_pair_count,
            "validation_available_pairs": preflight_input.validation_pair_count,
            "validation_available_per_session_min": int(
                preflight_input.validation_available.sum(axis=0).min()
            ),
            "validation_available_per_session_max": int(
                preflight_input.validation_available.sum(axis=0).max()
            ),
            "zero_target_count": preflight_input.zero_target_count,
            "zero_range_feature_count": preflight_input.zero_range_feature_count,
        },
        "metrics": dict(metrics),
        "result": {
            "causal_falsifiers_passed": metrics["causal_falsifiers_passed"],
            "interpretation": "source_local_non_promoting_event_censored_cpu_preflight_only",
            **_promotion_payload(),
        },
        "artifact_policy": _artifact_policy(),
    }


def _permission_payload() -> dict[str, bool]:
    return {
        "network_access": False,
        "credentials_read": False,
        "kis_accessed": False,
        "broker_access": False,
        "order_access": False,
        "gpu_used": False,
        "weights_persisted": False,
        "raw_market_data_persisted": False,
    }


def _promotion_payload() -> dict[str, bool]:
    return {
        "profitability_claim_allowed": False,
        "ranking_allowed": False,
        "selection_allowed": False,
        "ensemble_allowed": False,
        "paper_input_allowed": False,
        "live_allowed": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "external_artifact_only": True,
        "raw_market_data_persisted": False,
        "prices_persisted": False,
        "volumes_persisted": False,
        "targets_persisted": False,
        "prediction_rows_persisted": False,
        "model_weights_persisted": False,
        "credentials_read": False,
        "network_access": False,
        "broker_access": False,
        "gpu_used": False,
    }


def _prepare_output_directory(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    root = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        KIS_BROAD_D1_EVENT_CENSORED_CPU_PREFLIGHT_ID,
    )
    output_directory = root / run_label
    if output_directory.exists() or output_directory.is_symlink():
        raise FileExistsError("event-censored CPU preflight artifact already exists")
    output_directory.mkdir()
    if output_directory.is_symlink() or output_directory.resolve(strict=True) != output_directory:
        raise ValueError("event-censored CPU preflight artifact path is invalid")
    return output_directory


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        descriptor = os.open(
            str(path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FileExistsError("event-censored CPU preflight artifact is immutable") from error
    try:
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("event-censored CPU preflight artifact write failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _sha256_bytes(encoded)


def _repository_root(value: Path | str | None) -> Path:
    return Path(value or Path.cwd()).resolve()


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise KisBroadD1EventCensoredCpuInputUnavailable("geometry_audit_receipt_path_invalid")


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as error:
        raise RuntimeError("event-censored CPU preflight requires numpy") from error
    return numpy


def _logistic_regression() -> Any:
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError as error:
        raise RuntimeError("event-censored CPU preflight requires scikit-learn") from error
    return LogisticRegression


def _sha256_array(values: Any) -> str:
    array = _numpy().ascontiguousarray(values)
    return _sha256_bytes(
        array.dtype.str.encode("ascii") + repr(array.shape).encode("ascii") + array.tobytes()
    )


def _sha256_bool_matrix(values: list[list[bool]]) -> str:
    return _sha256_bytes(bytes(value for row in values for value in row))


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

"""One read-only, non-promoting causal CPU preflight for the broad KIS D1 panel.

This is deliberately a narrow research instrument.  It reattests an immutable
Data panel, derives only completed-bar inputs, and writes source-safe aggregate
receipts outside the repository.  It has no provider, credential, broker,
order, local-paper, PnL, ranking, ensemble, or model-weight persistence path.
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
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanel,
    KisPaperDailyBroadPanelSelection,
    load_materialized_kis_paper_daily_broad_panel,
    load_materialized_kis_paper_daily_broad_panel_selection,
)

from .artifact_paths import ensure_external_artifact_directory
from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)

KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ID = "kis-broad-d1-causal-cpu-preflight-v1"
KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_TRIAL_FAMILY = "kis-broad-d1-causal-cpu"
KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_FEATURE_NAMES = (
    "within_bar_log_return",
    "within_bar_log_range",
    "within_bar_close_location",
    "trailing_5_session_within_bar_log_return_mean",
    "trailing_20_session_within_bar_log_return_mean",
)
_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_ALLOWED_REVIEW_STATUSES = frozenset({"uncertain", "supported-with-limits", "review_unavailable"})
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class KisBroadD1CausalCpuInputUnavailable(ValueError):
    """A predeclared data-coverage or causal-input condition is not met."""

    def __init__(self, code: str) -> None:
        if not code or not code.replace("_", "").isalnum():
            raise ValueError("KIS broad D1 preflight unavailable code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KisBroadD1CausalCpuPreflightSpec:
    """The fixed data geometry, controls, and falsification budget."""

    cohort_target_count: int = 128
    history_session_count: int = 800
    terminal_buffer_sessions: int = 1
    development_session_count: int = 520
    purge_session_count: int = 20
    validation_session_count: int = 260
    feature_lookback_sessions: int = 20
    maximum_within_bar_range_ratio: float = 2.0
    l2_inverse_strength: float = 0.1
    logistic_max_iterations: int = 300
    random_seed: int = 20_260_803
    selection_raw_byte_attestation_limit: int = 512
    session_permutation_draw_count: int = 2_000
    session_bootstrap_draw_count: int = 2_000
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.cohort_target_count < 2
            or self.history_session_count < 8
            or self.terminal_buffer_sessions != 1
            or self.development_session_count < 4
            or self.purge_session_count < 1
            or self.validation_session_count < 4
            or self.feature_lookback_sessions != 20
            or self.development_session_count + self.purge_session_count
            + self.validation_session_count
            != self.history_session_count
            or self.feature_lookback_sessions >= self.development_session_count - 1
            or self.feature_lookback_sessions >= self.validation_session_count - 1
            or not math.isfinite(self.maximum_within_bar_range_ratio)
            or self.maximum_within_bar_range_ratio <= 1.0
            or not math.isfinite(self.l2_inverse_strength)
            or self.l2_inverse_strength <= 0.0
            or self.logistic_max_iterations < 1
            or self.random_seed < 0
            or self.selection_raw_byte_attestation_limit < self.cohort_target_count
            or self.session_permutation_draw_count < 2_000
            or self.session_bootstrap_draw_count < 2_000
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS broad D1 causal CPU preflight spec is invalid")

    @property
    def development_sample_count_per_target(self) -> int:
        return self.development_session_count - self.feature_lookback_sessions - 1

    @property
    def validation_sample_count_per_target(self) -> int:
        return self.validation_session_count - self.feature_lookback_sessions - 1

    def safe_payload(self) -> dict[str, object]:
        return {
            "cohort_target_count": self.cohort_target_count,
            "cohort_selection": "lexicographic_first_coverage_eligible_no_score_or_rank",
            "history_session_count": self.history_session_count,
            "terminal_buffer_sessions": self.terminal_buffer_sessions,
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "validation_in_partition_warmup_sessions": self.feature_lookback_sessions,
            "feature_lookback_sessions": self.feature_lookback_sessions,
            "feature_names": list(KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_FEATURE_NAMES),
            "target": "next_completed_bar_within_bar_direction_tie_is_zero",
            "maximum_within_bar_range_ratio": self.maximum_within_bar_range_ratio,
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
                "session_permutation_draw_count": self.session_permutation_draw_count,
                "session_bootstrap_draw_count": self.session_bootstrap_draw_count,
                "acceptance_rule": (
                    "true_balanced_accuracy_above_95th_session_permutation_quantile_and_"
                    "5th_percentile_session_bootstrap_advantages_above_zero"
                ),
            },
            "random_seed": self.random_seed,
            "selection_raw_byte_attestation_limit": self.selection_raw_byte_attestation_limit,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1CausalCpuPreflightInput:
    """In-memory, reattested input with opaque lineage and no persisted rows."""

    dataset_hash: str
    source_index_hash: str
    materialization_receipt_sha256: str | None
    target_key_set_hash: str
    full_target_count: int
    coverage_eligible_target_count: int
    target_count: int
    raw_byte_attested_target_count: int
    common_session_start: datetime
    common_session_end: datetime
    spec: KisBroadD1CausalCpuPreflightSpec
    development_features: Any
    development_labels: Any
    validation_features: Any
    validation_labels: Any
    validation_baselines: Mapping[str, Any]
    development_feature_hash: str
    development_label_hash: str
    validation_feature_hash: str
    validation_label_hash: str
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
        expected_development_rows = (
            self.target_count * self.spec.development_sample_count_per_target
        )
        expected_validation_shape = (
            self.target_count,
            self.spec.validation_sample_count_per_target,
        )
        if (
            not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.source_index_hash)
            or (
                self.materialization_receipt_sha256 is not None
                and not _is_sha256(self.materialization_receipt_sha256)
            )
            or not _is_sha256(self.target_key_set_hash)
            or self.full_target_count < self.target_count
            or self.coverage_eligible_target_count < self.target_count
            or self.coverage_eligible_target_count > self.full_target_count
            or self.target_count != self.spec.cohort_target_count
            or self.raw_byte_attested_target_count < self.target_count
            or self.raw_byte_attested_target_count > self.full_target_count
            or self.common_session_end <= self.common_session_start
            or development_features.shape
            != (expected_development_rows, len(KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_FEATURE_NAMES))
            or development_labels.shape != (expected_development_rows,)
            or validation_features.shape
            != (
                self.target_count * self.spec.validation_sample_count_per_target,
                len(KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_FEATURE_NAMES),
            )
            or validation_labels.shape != expected_validation_shape
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
            or len(numpy.unique(validation_labels)) != 2
            or any(
                not _is_sha256(value)
                for value in (
                    self.development_feature_hash,
                    self.development_label_hash,
                    self.validation_feature_hash,
                    self.validation_label_hash,
                )
            )
            or self.development_feature_hash != _sha256_array(development_features)
            or self.development_label_hash != _sha256_array(development_labels)
            or self.validation_feature_hash != _sha256_array(validation_features)
            or self.validation_label_hash != _sha256_array(validation_labels)
            or self.zero_target_count < 0
            or self.zero_range_feature_count < 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS broad D1 causal CPU preflight input is invalid")
        object.__setattr__(self, "development_features", development_features)
        object.__setattr__(self, "development_labels", development_labels)
        object.__setattr__(self, "validation_features", validation_features)
        object.__setattr__(self, "validation_labels", validation_labels)
        object.__setattr__(self, "validation_baselines", baselines)

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
                "validation_in_partition_warmup_sessions": self.spec.feature_lookback_sessions,
            }
        )

    @property
    def cost_model_hash(self) -> str:
        return _sha256_payload({"kind": "no_execution_or_cost_model"})

    @property
    def contract_hash(self) -> str:
        return _sha256_payload(_contract_payload(self))


@dataclass(frozen=True, slots=True)
class KisBroadD1CausalCpuPreflightRun:
    """External evidence for the one CPU preflight invocation."""

    status: Literal["completed", "input_unavailable"]
    run_directory: Path
    receipt_path: Path
    receipt_hash: str
    contract_hash: str | None
    frozen_campaign: FrozenCampaignRegistryEntry | None
    outcome: CampaignOutcomeRegistryEntry | None

    def __post_init__(self) -> None:
        if (
            self.status not in {"completed", "input_unavailable"}
            or not self.run_directory.is_dir()
            or not self.receipt_path.is_file()
            or not _is_sha256(self.receipt_hash)
            or _sha256_file(self.receipt_path) != self.receipt_hash
            or (self.status == "completed") != (self.contract_hash is not None)
            or (self.status == "completed") != (self.frozen_campaign is not None)
            or (self.status == "completed") != (self.outcome is not None)
        ):
            raise ValueError("KIS broad D1 causal CPU preflight run is invalid")


def build_kis_broad_d1_causal_cpu_preflight_input(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str | None = None,
    cache_root: Path | str,
    panel_root: Path | str,
    repo_root: Path | str | None = None,
    spec: KisBroadD1CausalCpuPreflightSpec | None = None,
) -> KisBroadD1CausalCpuPreflightInput:
    """Reattach one immutable Data input before opening any CPU model input."""

    resolved_spec = spec or KisBroadD1CausalCpuPreflightSpec()
    if materialization_receipt_path is not None:
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
            unavailable_reasons = {
                "broad daily panel selection coverage is insufficient": (
                    "insufficient_coverage_eligible_targets"
                ),
                "broad daily panel selection exact coverage is insufficient": (
                    "insufficient_exact_common_session_coverage"
                ),
            }
            if str(error) not in unavailable_reasons:
                raise
            raise KisBroadD1CausalCpuInputUnavailable(
                unavailable_reasons[str(error)]
            ) from error
        return build_kis_broad_d1_causal_cpu_preflight_input_from_selection(
            selection,
            spec=resolved_spec,
        )
    panel = load_materialized_kis_paper_daily_broad_panel(
        manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return build_kis_broad_d1_causal_cpu_preflight_input_from_panel(panel, spec=resolved_spec)


def build_kis_broad_d1_causal_cpu_preflight_input_from_panel(
    panel: KisPaperDailyBroadPanel,
    *,
    spec: KisBroadD1CausalCpuPreflightSpec | None = None,
) -> KisBroadD1CausalCpuPreflightInput:
    """Build the fixed CPU input from an already reattested broad Data panel."""

    if not isinstance(panel, KisPaperDailyBroadPanel):
        raise TypeError("KIS broad D1 causal CPU preflight requires a broad panel")
    resolved_spec = spec or KisBroadD1CausalCpuPreflightSpec()
    if panel.dataset_id != KIS_PAPER_DAILY_BROAD_PANEL_ID:
        raise ValueError("KIS broad D1 causal CPU preflight panel identity is invalid")

    selected_keys, grid = _select_target_cohort(panel, resolved_spec)
    return _build_kis_broad_d1_causal_cpu_preflight_input(
        dataset_hash=panel.dataset_hash,
        source_index_hash=panel.index_sha256,
        materialization_receipt_sha256=None,
        full_target_count=len(panel.target_keys),
        coverage_eligible_target_count=_coverage_eligible_target_count(panel, resolved_spec),
        raw_byte_attested_target_count=len(panel.bars_by_target),
        selected_keys=selected_keys,
        grid=grid,
        bars_by_target=panel.bars_by_target,
        spec=resolved_spec,
    )


def build_kis_broad_d1_causal_cpu_preflight_input_from_selection(
    selection: KisPaperDailyBroadPanelSelection,
    *,
    spec: KisBroadD1CausalCpuPreflightSpec | None = None,
) -> KisBroadD1CausalCpuPreflightInput:
    """Build the CPU input from the distinct Data-owned selected-panel type."""

    if not isinstance(selection, KisPaperDailyBroadPanelSelection):
        raise TypeError("KIS broad D1 causal CPU preflight requires a panel selection")
    resolved_spec = spec or KisBroadD1CausalCpuPreflightSpec()
    required_bar_count = (
        resolved_spec.history_session_count + resolved_spec.terminal_buffer_sessions
    )
    if (
        selection.dataset_id != KIS_PAPER_DAILY_BROAD_PANEL_ID
        or len(selection.selected_target_keys) != resolved_spec.cohort_target_count
        or selection.minimum_bar_count != required_bar_count
        or selection.common_session_count != resolved_spec.history_session_count
        or selection.terminal_buffer_sessions != resolved_spec.terminal_buffer_sessions
        or selection.coverage_eligible_target_count < resolved_spec.cohort_target_count
        or selection.coverage_eligible_target_count > selection.full_target_count
        or selection.raw_byte_attested_target_count < resolved_spec.cohort_target_count
        or selection.raw_byte_attested_target_count > selection.full_target_count
    ):
        raise ValueError("KIS broad D1 causal CPU preflight panel selection is invalid")
    grid = _common_grid_from_selected_selection(selection, resolved_spec)
    return _build_kis_broad_d1_causal_cpu_preflight_input(
        dataset_hash=selection.dataset_hash,
        source_index_hash=selection.index_sha256,
        materialization_receipt_sha256=selection.materialization_receipt_sha256,
        full_target_count=selection.full_target_count,
        coverage_eligible_target_count=selection.coverage_eligible_target_count,
        raw_byte_attested_target_count=selection.raw_byte_attested_target_count,
        selected_keys=selection.selected_target_keys,
        grid=grid,
        bars_by_target=selection.bars_by_target,
        spec=resolved_spec,
    )


def _build_kis_broad_d1_causal_cpu_preflight_input(
    *,
    dataset_hash: str,
    source_index_hash: str,
    materialization_receipt_sha256: str | None,
    full_target_count: int,
    coverage_eligible_target_count: int,
    raw_byte_attested_target_count: int,
    selected_keys: tuple[str, ...],
    grid: tuple[datetime, ...],
    bars_by_target: Mapping[str, Any],
    spec: KisBroadD1CausalCpuPreflightSpec,
) -> KisBroadD1CausalCpuPreflightInput:
    """Derive causal matrices from the exact selected streams and fixed grid."""

    numpy = _numpy()
    development_features_by_target: list[Any] = []
    development_labels_by_target: list[Any] = []
    validation_features_by_target: list[Any] = []
    validation_labels_by_target: list[Any] = []
    validation_current_directions: list[Any] = []
    zero_target_count = 0
    zero_range_feature_count = 0

    for target_key in selected_keys:
        records = _records_on_grid(bars_by_target[target_key].bars, grid)
        geometry, target_directions, target_zero_count, range_zero_count = _geometry(
            records,
            spec,
        )
        development_indices = range(
            spec.feature_lookback_sessions,
            spec.development_session_count - 1,
        )
        validation_start = (
            spec.development_session_count + spec.purge_session_count
        )
        validation_indices = range(
            validation_start + spec.feature_lookback_sessions,
            spec.history_session_count - 1,
        )
        development_features_by_target.append(
            _feature_rows(geometry, development_indices, spec, numpy)
        )
        development_labels_by_target.append(
            target_directions[[index + 1 for index in development_indices]]
        )
        validation_features_by_target.append(
            _feature_rows(geometry, validation_indices, spec, numpy)
        )
        validation_labels_by_target.append(
            target_directions[[index + 1 for index in validation_indices]]
        )
        validation_current_directions.append(geometry[list(validation_indices), 0] > 0.0)
        zero_target_count += target_zero_count
        zero_range_feature_count += range_zero_count

    development_features = numpy.concatenate(development_features_by_target, axis=0)
    development_labels_matrix = numpy.stack(development_labels_by_target, axis=0)
    validation_features_matrix = numpy.stack(validation_features_by_target, axis=0)
    validation_labels = numpy.stack(validation_labels_by_target, axis=0).astype(numpy.int8)
    validation_current_directions_matrix = numpy.stack(
        validation_current_directions,
        axis=0,
    ).astype(numpy.int8)
    per_target_majority = (
        development_labels_matrix.mean(axis=1, keepdims=True) > 0.5
    ).astype(numpy.int8)
    validation_sample_count = spec.validation_sample_count_per_target
    baselines = {
        "flat_zero_direction": numpy.zeros_like(validation_labels, dtype=numpy.int8),
        "per_target_development_majority_direction": numpy.repeat(
            per_target_majority,
            validation_sample_count,
            axis=1,
        ),
        "current_session_cross_sectional_direction_majority": numpy.repeat(
            (
                validation_current_directions_matrix.mean(axis=0, keepdims=True) > 0.5
            ).astype(numpy.int8),
            len(selected_keys),
            axis=0,
        ),
        "same_target_prior_within_bar_direction": validation_current_directions_matrix,
    }
    development_labels = development_labels_matrix.reshape(-1).astype(numpy.int8)
    validation_features = validation_features_matrix.reshape(
        -1,
        len(KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_FEATURE_NAMES),
    )
    target_key_set_hash = _selected_target_key_set_hash(selected_keys)
    return KisBroadD1CausalCpuPreflightInput(
        dataset_hash=dataset_hash,
        source_index_hash=source_index_hash,
        materialization_receipt_sha256=materialization_receipt_sha256,
        target_key_set_hash=target_key_set_hash,
        full_target_count=full_target_count,
        coverage_eligible_target_count=coverage_eligible_target_count,
        target_count=len(selected_keys),
        raw_byte_attested_target_count=raw_byte_attested_target_count,
        common_session_start=grid[0],
        common_session_end=grid[-1],
        spec=spec,
        development_features=development_features,
        development_labels=development_labels,
        validation_features=validation_features,
        validation_labels=validation_labels,
        validation_baselines=baselines,
        development_feature_hash=_sha256_array(development_features),
        development_label_hash=_sha256_array(development_labels),
        validation_feature_hash=_sha256_array(validation_features),
        validation_label_hash=_sha256_array(validation_labels),
        zero_target_count=zero_target_count,
        zero_range_feature_count=zero_range_feature_count,
    )


def run_kis_broad_d1_causal_cpu_preflight(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str | None = None,
    cache_root: Path | str,
    panel_root: Path | str,
    artifact_root: Path | str = KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ARTIFACT_ROOT,
    run_label: str,
    review_status: str,
    repo_root: Path | str | None = None,
    spec: KisBroadD1CausalCpuPreflightSpec | None = None,
) -> KisBroadD1CausalCpuPreflightRun:
    """Run the frozen CPU study, or write one scoped input-unavailable receipt."""

    _validate_run_label(run_label)
    if review_status not in _ALLOWED_REVIEW_STATUSES:
        raise ValueError("KIS broad D1 causal CPU preflight review status is invalid")
    repository = _repository_root(repo_root)
    resolved_spec = spec or KisBroadD1CausalCpuPreflightSpec()
    output_directory = _prepare_output_directory(
        artifact_root=Path(artifact_root),
        repo_root=repository,
        run_label=run_label,
    )
    try:
        preflight_input = build_kis_broad_d1_causal_cpu_preflight_input(
            manifest_path=manifest_path,
            materialization_receipt_path=materialization_receipt_path,
            cache_root=cache_root,
            panel_root=panel_root,
            repo_root=repository,
            spec=resolved_spec,
        )
    except KisBroadD1CausalCpuInputUnavailable as error:
        receipt_path = output_directory / "input-unavailable.json"
        payload = _input_unavailable_payload(
            spec=resolved_spec,
            review_status=review_status,
            reason=error.code,
        )
        receipt_hash = _write_json_new(receipt_path, payload)
        return KisBroadD1CausalCpuPreflightRun(
            status="input_unavailable",
            run_directory=output_directory,
            receipt_path=receipt_path,
            receipt_hash=receipt_hash,
            contract_hash=None,
            frozen_campaign=None,
            outcome=None,
        )

    precommit_payload = _precommit_payload(preflight_input, review_status=review_status)
    contract_hash = _sha256_payload(precommit_payload)
    frozen_campaign = register_frozen_campaign(
        contract_hash=contract_hash,
        dataset_hash=preflight_input.dataset_hash,
        split_hash=preflight_input.split_hash,
        cost_model_hash=preflight_input.cost_model_hash,
        trial_family=KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_TRIAL_FAMILY,
        holdout_access="none",
        artifact_root=Path(artifact_root),
        repo_root=repository,
    )
    precommit_path = output_directory / "precommit.json"
    _write_json_new(
        precommit_path,
        {
            **precommit_payload,
            "campaign_contract_hash": contract_hash,
            "campaign_registry_record_sha256": frozen_campaign.record_sha256,
        },
    )
    metrics = _fit_and_evaluate(preflight_input)
    receipt_path = output_directory / "summary.json"
    receipt_payload = _summary_payload(
        preflight_input,
        contract_hash=contract_hash,
        review_status=review_status,
        metrics=metrics,
    )
    receipt_hash = _write_json_new(receipt_path, receipt_payload)
    outcome = register_campaign_outcome(
        contract_hash=contract_hash,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=receipt_hash,
        artifact_root=Path(artifact_root),
        repo_root=repository,
    )
    return KisBroadD1CausalCpuPreflightRun(
        status="completed",
        run_directory=output_directory,
        receipt_path=receipt_path,
        receipt_hash=receipt_hash,
        contract_hash=contract_hash,
        frozen_campaign=frozen_campaign,
        outcome=outcome,
    )


def _select_target_cohort(
    panel: KisPaperDailyBroadPanel,
    spec: KisBroadD1CausalCpuPreflightSpec,
) -> tuple[tuple[str, ...], tuple[datetime, ...]]:
    eligible_keys = tuple(
        target_key
        for target_key in panel.target_keys
        if len(panel.bars_by_target[target_key].bars)
        >= spec.history_session_count + spec.terminal_buffer_sessions
    )
    if len(eligible_keys) < spec.cohort_target_count:
        raise KisBroadD1CausalCpuInputUnavailable("insufficient_coverage_eligible_targets")
    reference_bars = panel.bars_by_target[eligible_keys[0]].bars
    buffer_start = -spec.terminal_buffer_sessions
    grid_bars = reference_bars[
        -(spec.history_session_count + spec.terminal_buffer_sessions) : buffer_start
    ]
    grid = tuple(bar.start_ts for bar in grid_bars)
    if len(grid) != spec.history_session_count or tuple(sorted(grid)) != grid:
        raise KisBroadD1CausalCpuInputUnavailable("invalid_reference_session_grid")
    selected: list[str] = []
    for target_key in eligible_keys:
        sessions = {bar.start_ts for bar in panel.bars_by_target[target_key].bars}
        if all(session in sessions for session in grid):
            selected.append(target_key)
        if len(selected) == spec.cohort_target_count:
            return tuple(selected), grid
    raise KisBroadD1CausalCpuInputUnavailable("insufficient_exact_common_session_coverage")


def _common_grid_from_selected_selection(
    selection: KisPaperDailyBroadPanelSelection,
    spec: KisBroadD1CausalCpuPreflightSpec,
) -> tuple[datetime, ...]:
    """Derive a fixed common grid without replacing the frozen selection."""

    reference_bars = selection.bars_by_target[selection.selected_target_keys[0]].bars
    grid_start = -(spec.history_session_count + spec.terminal_buffer_sessions)
    grid_end = -spec.terminal_buffer_sessions
    grid_bars = reference_bars[grid_start:grid_end]
    grid = tuple(bar.start_ts for bar in grid_bars)
    if len(grid) != spec.history_session_count or tuple(sorted(grid)) != grid:
        raise KisBroadD1CausalCpuInputUnavailable("invalid_reference_session_grid")
    for target_key in selection.selected_target_keys:
        sessions = {bar.start_ts for bar in selection.bars_by_target[target_key].bars}
        if not all(session in sessions for session in grid):
            raise KisBroadD1CausalCpuInputUnavailable("insufficient_exact_common_session_coverage")
    return grid


def _coverage_eligible_target_count(
    panel: KisPaperDailyBroadPanel,
    spec: KisBroadD1CausalCpuPreflightSpec,
) -> int:
    return sum(
        len(catalog.bars) >= spec.history_session_count + spec.terminal_buffer_sessions
        for catalog in panel.bars_by_target.values()
    )


def _records_on_grid(records: tuple[Bar, ...], grid: tuple[datetime, ...]) -> tuple[Bar, ...]:
    by_session = {bar.start_ts: bar for bar in records}
    try:
        selected = tuple(by_session[session] for session in grid)
    except KeyError as error:
        raise KisBroadD1CausalCpuInputUnavailable("common_session_grid_drift") from error
    if (
        len(selected) != len(grid)
        or any(
            bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.market != "US"
            or bar.start_ts != session
            for bar, session in zip(selected, grid, strict=True)
        )
    ):
        raise KisBroadD1CausalCpuInputUnavailable("incomplete_or_misaligned_bar")
    return selected


def _geometry(
    records: tuple[Bar, ...],
    spec: KisBroadD1CausalCpuPreflightSpec,
) -> tuple[Any, Any, int, int]:
    numpy = _numpy()
    geometry = numpy.empty((len(records), 3), dtype=numpy.float64)
    target_directions = numpy.empty((len(records),), dtype=numpy.int8)
    zero_target_count = 0
    zero_range_feature_count = 0
    for index, bar in enumerate(records):
        open_value = float(bar.open)
        high_value = float(bar.high)
        low_value = float(bar.low)
        close_value = float(bar.close)
        if (
            not all(
                math.isfinite(value) and value > 0.0
                for value in (open_value, high_value, low_value, close_value)
            )
            or high_value < max(open_value, close_value)
            or low_value > min(open_value, close_value)
            or high_value / low_value > spec.maximum_within_bar_range_ratio
        ):
            raise KisBroadD1CausalCpuInputUnavailable("within_bar_geometry_integrity_failure")
        within_bar_log_return = math.log(close_value / open_value)
        within_bar_log_range = math.log(high_value / low_value)
        if high_value == low_value:
            close_location = 0.0
            zero_range_feature_count += 1
        else:
            close_location = (close_value - low_value) / (high_value - low_value) - 0.5
        if not all(
            math.isfinite(value)
            for value in (within_bar_log_return, within_bar_log_range, close_location)
        ):
            raise KisBroadD1CausalCpuInputUnavailable("non_finite_within_bar_geometry")
        geometry[index] = (within_bar_log_return, within_bar_log_range, close_location)
        target_directions[index] = 1 if within_bar_log_return > 0.0 else 0
        if within_bar_log_return == 0.0:
            zero_target_count += 1
    return geometry, target_directions, zero_target_count, zero_range_feature_count


def _feature_rows(
    geometry: Any,
    indices: range,
    spec: KisBroadD1CausalCpuPreflightSpec,
    numpy: Any,
) -> Any:
    values = numpy.asarray(geometry, dtype=numpy.float64)
    rows = numpy.empty(
        (len(indices), len(KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_FEATURE_NAMES)),
        dtype=numpy.float64,
    )
    for row_index, session_index in enumerate(indices):
        if session_index < spec.feature_lookback_sessions:
            raise KisBroadD1CausalCpuInputUnavailable("feature_window_crosses_split_boundary")
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
        raise KisBroadD1CausalCpuInputUnavailable("non_finite_feature_matrix")
    return rows


def _fit_and_evaluate(preflight_input: KisBroadD1CausalCpuPreflightInput) -> dict[str, object]:
    numpy = _numpy()
    LogisticRegression = _logistic_regression()
    development_features = preflight_input.development_features
    development_labels = preflight_input.development_labels
    feature_means = development_features.mean(axis=0)
    feature_scales = development_features.std(axis=0)
    if not numpy.isfinite(feature_means).all() or not numpy.isfinite(feature_scales).all():
        raise KisBroadD1CausalCpuInputUnavailable("development_standardization_failure")
    constant_feature_count = int((feature_scales <= 1e-12).sum())
    feature_scales = numpy.where(feature_scales <= 1e-12, 1.0, feature_scales)
    standardized_development = (development_features - feature_means) / feature_scales
    standardized_validation = (preflight_input.validation_features - feature_means) / feature_scales
    model = LogisticRegression(
        C=preflight_input.spec.l2_inverse_strength,
        solver="lbfgs",
        max_iter=preflight_input.spec.logistic_max_iterations,
        random_state=preflight_input.spec.random_seed,
    )
    model.fit(standardized_development, development_labels)
    probabilities = model.predict_proba(standardized_validation)[:, 1].reshape(
        preflight_input.target_count,
        preflight_input.spec.validation_sample_count_per_target,
    )
    if (
        not numpy.isfinite(probabilities).all()
        or numpy.any(probabilities < 0.0)
        or numpy.any(probabilities > 1.0)
    ):
        raise ValueError("KIS broad D1 causal CPU preflight probabilities are invalid")
    predictions = (probabilities >= 0.5).astype(numpy.int8)
    labels = preflight_input.validation_labels
    baseline_scores = {
        name: _balanced_accuracy(labels, values, numpy)
        for name, values in preflight_input.validation_baselines.items()
    }
    model_score = _balanced_accuracy(labels, predictions, numpy)
    bootstrap = _bootstrap_advantages(
        labels=labels,
        probabilities=probabilities,
        predictions=predictions,
        baselines=preflight_input.validation_baselines,
        draw_count=preflight_input.spec.session_bootstrap_draw_count,
        seed=preflight_input.spec.random_seed + 1,
        numpy=numpy,
    )
    permutation_quantile = _session_permutation_quantile(
        labels=labels,
        predictions=predictions,
        draw_count=preflight_input.spec.session_permutation_draw_count,
        seed=preflight_input.spec.random_seed + 2,
        numpy=numpy,
    )
    falsifiers_passed = (
        model_score > permutation_quantile
        and bootstrap["balanced_accuracy_advantage_lower_5th_percentile"] > 0.0
        and bootstrap["cross_sectional_residual_advantage_lower_5th_percentile"] > 0.0
    )
    return {
        "model_balanced_accuracy": model_score,
        "development_constant_feature_count": constant_feature_count,
        "baseline_balanced_accuracy": dict(sorted(baseline_scores.items())),
        "permutation_null_95th_percentile": permutation_quantile,
        **bootstrap,
        "causal_falsifiers_passed": falsifiers_passed,
        "model_weights_persisted": False,
        "prediction_rows_persisted": False,
    }


def _balanced_accuracy(labels: Any, predictions: Any, numpy: Any) -> float:
    flattened_labels = numpy.asarray(labels, dtype=numpy.int8).reshape(-1)
    flattened_predictions = numpy.asarray(predictions, dtype=numpy.int8).reshape(-1)
    positives = flattened_labels == 1
    negatives = flattened_labels == 0
    if not positives.any() or not negatives.any():
        raise KisBroadD1CausalCpuInputUnavailable("validation_class_variation_missing")
    positive_recall = float((flattened_predictions[positives] == 1).mean())
    negative_recall = float((flattened_predictions[negatives] == 0).mean())
    return (positive_recall + negative_recall) / 2.0


def _bootstrap_advantages(
    *,
    labels: Any,
    probabilities: Any,
    predictions: Any,
    baselines: Mapping[str, Any],
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
        model_score = _balanced_accuracy(sampled_labels, predictions[:, sessions], numpy)
        baseline_score = max(
            _balanced_accuracy(sampled_labels, values[:, sessions], numpy)
            for values in baselines.values()
        )
        balanced_advantages[draw] = model_score - baseline_score
        target_residual = sampled_labels - sampled_labels.mean(axis=0, keepdims=True)
        model_residual = probabilities[:, sessions] - probabilities[:, sessions].mean(
            axis=0,
            keepdims=True,
        )
        model_error = float(numpy.mean((model_residual - target_residual) ** 2))
        baseline_error = min(
            float(
                numpy.mean(
                    (
                        values[:, sessions]
                        - values[:, sessions].mean(axis=0, keepdims=True)
                        - target_residual
                    )
                    ** 2
                )
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


def _session_permutation_quantile(
    *,
    labels: Any,
    predictions: Any,
    draw_count: int,
    seed: int,
    numpy: Any,
) -> float:
    generator = numpy.random.default_rng(seed)
    session_count = labels.shape[1]
    scores = numpy.empty((draw_count,), dtype=numpy.float64)
    for draw in range(draw_count):
        scores[draw] = _balanced_accuracy(
            labels[:, generator.permutation(session_count)],
            predictions,
            numpy,
        )
    return float(numpy.quantile(scores, 0.95))


def _contract_payload(
    preflight_input: KisBroadD1CausalCpuPreflightInput) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ID,
        "dataset": {
            "dataset_id": KIS_PAPER_DAILY_BROAD_PANEL_ID,
            "dataset_hash": preflight_input.dataset_hash,
            "source_index_hash": preflight_input.source_index_hash,
            "materialization_receipt_sha256": preflight_input.materialization_receipt_sha256,
            "target_key_set_hash": preflight_input.target_key_set_hash,
            "full_target_count": preflight_input.full_target_count,
            "coverage_eligible_target_count": preflight_input.coverage_eligible_target_count,
            "target_count": preflight_input.target_count,
            "raw_byte_attested_target_count": preflight_input.raw_byte_attested_target_count,
            "full_panel_raw_byte_attested_this_run": (
                preflight_input.raw_byte_attested_target_count == preflight_input.full_target_count
            ),
            "timeframe": Timeframe.D1.value,
            "common_session_start": preflight_input.common_session_start.isoformat(),
            "common_session_end": preflight_input.common_session_end.isoformat(),
        },
        "input_hashes": {
            "development_features": preflight_input.development_feature_hash,
            "development_labels": preflight_input.development_label_hash,
            "validation_features": preflight_input.validation_feature_hash,
            "validation_labels": preflight_input.validation_label_hash,
        },
        "spec": preflight_input.spec.safe_payload(),
        "cost_model": {"kind": "no_execution_or_cost_model"},
    }


def _precommit_payload(
    preflight_input: KisBroadD1CausalCpuPreflightInput,
    *,
    review_status: str,
) -> dict[str, object]:
    return {
        **_contract_payload(preflight_input),
        "status": "precommitted",
        "claim": (
            "one source-local causal CPU preflight on completed KIS D1 bar geometry; "
            "aggregate classification diagnostics only, never a profitability, selection, "
            "ranking, ensemble, Paper, or live claim"
        ),
        "source_reattestation": {
            "raw_byte_attested_target_count": preflight_input.raw_byte_attested_target_count,
            "full_target_count": preflight_input.full_target_count,
            "excluded_target_count": (
                preflight_input.full_target_count - preflight_input.target_count
            ),
            "full_panel_raw_byte_attested_this_run": (
                preflight_input.raw_byte_attested_target_count == preflight_input.full_target_count
            ),
            "selection_scope": (
                "full_panel" if preflight_input.raw_byte_attested_target_count
                == preflight_input.full_target_count else "frozen_selected_cohort_only"
            ),
        },
        "source_limitations": [
            "current_listing_only_not_point_in_time_universe",
            "non_pit_registry_scope",
            "MODP_0_unadjusted",
            "corporate_action_semantics_not_qualified",
            "session_finality_unattested",
            "development_coverage_only_not_research_ready",
        ],
        "availability": {
            "features_use_completed_bar_t_or_earlier": True,
            "target_uses_next_completed_bar": True,
            "terminal_panel_session_excluded": True,
            "target_tie_rule": "zero_direction",
            "zero_range_feature_rule": "neutral_close_location",
            "within_bar_mixed_adjustment_screen": "reject_if_high_low_ratio_exceeds_fixed_limit",
        },
        "review": {
            "reviewer": "claude_cli_falsification_first",
            "status": review_status,
            "resolution": (
                "session-block null/bootstrap, factor baselines, residual check, "
                "and geometry screen frozen"
            ),
        },
        "permissions": {
            "network_access": False,
            "credentials_read": False,
            "kis_accessed": False,
            "broker_access": False,
            "order_access": False,
            "gpu_used": False,
            "weights_persisted": False,
            "raw_market_data_persisted": False,
        },
        "promotion": {
            "ranking_allowed": False,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
            "live_allowed": False,
            "profitability_claim_allowed": False,
        },
    }


def _input_unavailable_payload(
    *,
    spec: KisBroadD1CausalCpuPreflightSpec,
    review_status: str,
    reason: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ID,
        "status": "input_unavailable",
        "reason": reason,
        "spec": spec.safe_payload(),
        "review_status": review_status,
        "raw_market_data_persisted": False,
        "network_access": False,
        "credentials_read": False,
        "broker_access": False,
        "gpu_used": False,
        "selection_allowed": False,
        "paper_input_allowed": False,
    }


def _summary_payload(
    preflight_input: KisBroadD1CausalCpuPreflightInput,
    *,
    contract_hash: str,
    review_status: str,
    metrics: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ID,
        "status": "completed",
        "campaign_contract_hash": contract_hash,
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
            "excluded_target_count": (
                preflight_input.full_target_count - preflight_input.target_count
            ),
            "full_panel_raw_byte_attested_this_run": (
                preflight_input.raw_byte_attested_target_count == preflight_input.full_target_count
            ),
            "common_session_start": preflight_input.common_session_start.isoformat(),
            "common_session_end": preflight_input.common_session_end.isoformat(),
            "terminal_buffer_sessions": preflight_input.spec.terminal_buffer_sessions,
            "current_listing_only": True,
            "non_pit": True,
            "adjustment_mode": "MODP=0_unadjusted",
            "corporate_action_qualified": False,
            "session_finality_attested": False,
        },
        "sample_counts": {
            "development": int(preflight_input.development_labels.shape[0]),
            "validation": int(preflight_input.validation_labels.size),
            "validation_window_session_count": preflight_input.spec.validation_session_count,
            "validation_decision_session_count": (
                preflight_input.spec.validation_sample_count_per_target
            ),
            "zero_target_count": preflight_input.zero_target_count,
            "zero_range_feature_count": preflight_input.zero_range_feature_count,
        },
        "metrics": dict(metrics),
        "result": {
            "causal_falsifiers_passed": metrics["causal_falsifiers_passed"],
            "interpretation": "source_local_non_promoting_cpu_preflight_only",
            "profitability_claim_allowed": False,
            "ranking_allowed": False,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
            "live_allowed": False,
        },
        "artifact_policy": {
            "external_artifact_only": True,
            "raw_market_data_persisted": False,
            "prices_persisted": False,
            "volumes_persisted": False,
            "prediction_rows_persisted": False,
            "model_weights_persisted": False,
            "credentials_read": False,
            "network_access": False,
            "broker_access": False,
            "gpu_used": False,
        },
    }


def _prepare_output_directory(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    root = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        KIS_BROAD_D1_CAUSAL_CPU_PREFLIGHT_ID,
    )
    output_directory = root / run_label
    if output_directory.exists():
        raise FileExistsError("KIS broad D1 causal CPU preflight artifact already exists")
    output_directory.mkdir()
    if output_directory.is_symlink() or output_directory.resolve(strict=True) != output_directory:
        raise ValueError("KIS broad D1 causal CPU preflight artifact path is invalid")
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
        raise FileExistsError("KIS broad D1 causal CPU preflight artifact is immutable") from error
    try:
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("KIS broad D1 causal CPU preflight artifact write failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _sha256_bytes(encoded)


def _repository_root(value: Path | str | None) -> Path:
    return Path(value or Path.cwd()).resolve()


def _validate_run_label(value: str) -> None:
    if not _RUN_LABEL.fullmatch(value):
        raise ValueError("KIS broad D1 causal CPU preflight run label is invalid")


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as error:  # pragma: no cover - dependency is required by the dev extra.
        raise RuntimeError("numpy is required for KIS broad D1 causal CPU preflight") from error
    return numpy


def _logistic_regression() -> Any:
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError as error:  # pragma: no cover - dependency is required by the dev extra.
        raise RuntimeError(
            "scikit-learn is required for KIS broad D1 causal CPU preflight"
        ) from error
    return LogisticRegression


def _sha256_array(values: Any) -> str:
    array = _numpy().ascontiguousarray(values)
    return _sha256_bytes(array.tobytes())


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _selected_target_key_set_hash(target_keys: tuple[str, ...]) -> str:
    """Match the Data-owned selected-panel identity encoding exactly."""

    payload = json.dumps(
        {"target_keys": list(target_keys)},
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    return _sha256_bytes((payload + "\n").encode("utf-8"))


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

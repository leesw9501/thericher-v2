"""Fixed CPU-only controls for the first profiled MTF forward dataset.

This module is intentionally a narrow, non-promoting campaign.  It consumes
the already frozen first-30-pair contract, builds features from the causal
input prefixes only, and compares a no-trade baseline with two predeclared
classical controls.  It does not calculate PnL, select a winner, persist a
model, allocate GPU, or touch broker/data-provider routes.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

from .artifact_paths import ensure_external_artifact_directory
from .causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from .kis_mtf_profiled_feature_input_preflight import (
    build_target_free_mtf_feature_projection,
    resample_completed_causal_prefix,
)
from .profiled_mtf_flattened_control import build_profiled_mtf_flattened_control
from .profiled_mtf_forward_supervised_dataset import (
    PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT,
    PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT,
    ProfiledMtfForwardSupervisedDatasetMaterialization,
    ProfiledMtfForwardSupervisedDatasetReceipt,
)

PROFILED_MTF_FORWARD_CPU_CAMPAIGN_ID: Final = "profiled-mtf-forward-cpu-campaign-executor-v1"
PROFILED_MTF_FORWARD_CPU_CAMPAIGN_PROFILE_ID: Final = "short"
PROFILED_MTF_FORWARD_CPU_CAMPAIGN_FEATURE_WIDTH: Final = 50
PROFILED_MTF_FORWARD_CPU_CAMPAIGN_CANDIDATE_IDS: Final = (
    "no_trade_zero",
    "ridge_alpha_10",
    "hist_gradient_depth_limited",
)
PROFILED_MTF_FORWARD_CPU_CAMPAIGN_METRIC_NAMES: Final = (
    "validation_mae",
    "validation_directional_hit_rate",
    "permuted_validation_mae",
    "permuted_validation_directional_hit_rate",
)
_ATTEMPT_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{1,80}$", re.ASCII)

CampaignStatus = Literal["input_unavailable", "cpu_evaluated_not_promoting"]


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCpuCampaignPolicy:
    """One fixed feature/control/split contract before any target is consumed."""

    dataset_receipt_sha256: str
    dataset_policy_sha256: str
    dataset_result_sha256: str
    dataset_contract_sha256: str | None
    code_revision_sha256: str
    policy_sha256: str

    def __post_init__(self) -> None:
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.dataset_receipt_sha256,
                    self.dataset_policy_sha256,
                    self.dataset_result_sha256,
                    self.code_revision_sha256,
                    self.policy_sha256,
                )
            )
            or (
                self.dataset_contract_sha256 is not None
                and not _is_sha256(self.dataset_contract_sha256)
            )
            or self.policy_sha256 != _sha256_json(_policy_unsigned_payload(self))
        ):
            raise ValueError("profiled MTF CPU campaign policy is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {**_policy_unsigned_payload(self), "policy_sha256": self.policy_sha256}


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCpuFeatureMatrix:
    """In-memory causal control rows; values never appear in a source-safe receipt."""

    dataset_contract_sha256: str
    row_keys: tuple[tuple[int, int, str, str], ...]
    values: tuple[tuple[Decimal, ...], ...] = field(repr=False)
    control_sha256s: tuple[str, ...]
    feature_matrix_sha256: str

    def __post_init__(self) -> None:
        values = tuple(tuple(row) for row in self.values)
        keys = tuple(self.row_keys)
        if (
            not _is_sha256(self.dataset_contract_sha256)
            or len(keys) != PROFILED_MTF_FORWARD_SUPERVISED_DATASET_PAIR_COUNT * 2
            or len(values) != len(keys)
            or len(self.control_sha256s) != len(keys)
            or any(
                len(row) != PROFILED_MTF_FORWARD_CPU_CAMPAIGN_FEATURE_WIDTH
                or any(not value.is_finite() for value in row)
                for row in values
            )
            or any(not _is_sha256(value) for value in self.control_sha256s)
            or self.feature_matrix_sha256 != _feature_matrix_sha256(
                dataset_contract_sha256=self.dataset_contract_sha256,
                row_keys=keys,
                values=values,
                control_sha256s=self.control_sha256s,
            )
        ):
            raise ValueError("profiled MTF CPU feature matrix is invalid")
        object.__setattr__(self, "row_keys", keys)
        object.__setattr__(self, "values", values)


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCpuCandidateMetric:
    """In-memory numerical evidence for one fixed candidate; never a promotion."""

    candidate_id: str
    validation_mae: float = field(repr=False)
    validation_directional_hit_rate: float = field(repr=False)
    permuted_validation_mae: float = field(repr=False)
    permuted_validation_directional_hit_rate: float = field(repr=False)
    evidence_sha256: str

    def __post_init__(self) -> None:
        values = (
            self.validation_mae,
            self.validation_directional_hit_rate,
            self.permuted_validation_mae,
            self.permuted_validation_directional_hit_rate,
        )
        if (
            self.candidate_id not in PROFILED_MTF_FORWARD_CPU_CAMPAIGN_CANDIDATE_IDS
            or any(not math.isfinite(value) for value in values)
            or not 0 <= self.validation_directional_hit_rate <= 1
            or not 0 <= self.permuted_validation_directional_hit_rate <= 1
            or self.validation_mae < 0
            or self.permuted_validation_mae < 0
            or self.evidence_sha256 != _candidate_evidence_sha256(self)
        ):
            raise ValueError("profiled MTF CPU candidate metric is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "metric_names": list(PROFILED_MTF_FORWARD_CPU_CAMPAIGN_METRIC_NAMES),
            "metric_evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCpuCampaignResult:
    """Source-safe non-promoting campaign result with metrics held in memory only."""

    policy_sha256: str
    dataset_receipt_sha256: str
    dataset_result_sha256: str
    status: CampaignStatus
    feature_matrix_sha256: str | None
    train_row_count: int
    purge_row_count: int
    validation_row_count: int
    candidate_metrics: tuple[ProfiledMtfForwardCpuCandidateMetric, ...] = field(repr=False)
    result_sha256: str = ""

    def __post_init__(self) -> None:
        metrics = tuple(self.candidate_metrics)
        evaluated = self.status == "cpu_evaluated_not_promoting"
        expected_counts = (40, 4, 16) if evaluated else (0, 0, 0)
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.policy_sha256,
                    self.dataset_receipt_sha256,
                    self.dataset_result_sha256,
                    self.result_sha256,
                )
            )
            or (self.feature_matrix_sha256 is not None) != evaluated
            or (
                self.feature_matrix_sha256 is not None
                and not _is_sha256(self.feature_matrix_sha256)
            )
            or (self.train_row_count, self.purge_row_count, self.validation_row_count)
            != expected_counts
            or (
                tuple(metric.candidate_id for metric in metrics)
                != PROFILED_MTF_FORWARD_CPU_CAMPAIGN_CANDIDATE_IDS
                if evaluated
                else metrics != ()
            )
            or self.status not in {"input_unavailable", "cpu_evaluated_not_promoting"}
            or self.result_sha256 != _result_sha256(self)
        ):
            raise ValueError("profiled MTF CPU campaign result is invalid")
        object.__setattr__(self, "candidate_metrics", metrics)

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": PROFILED_MTF_FORWARD_CPU_CAMPAIGN_ID,
            "policy_sha256": self.policy_sha256,
            "dataset_receipt_sha256": self.dataset_receipt_sha256,
            "dataset_result_sha256": self.dataset_result_sha256,
            "status": self.status,
            "feature_matrix_sha256": self.feature_matrix_sha256,
            "pair_split": {
                "train_row_count": self.train_row_count,
                "purge_row_count": self.purge_row_count,
                "validation_row_count": self.validation_row_count,
            },
            "candidate_metrics": [metric.safe_payload() for metric in self.candidate_metrics],
            "scope": _result_scope(cpu_trained=self.status == "cpu_evaluated_not_promoting"),
            "result_sha256": self.result_sha256,
        }


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCpuCampaignReceipt:
    """External receipt that intentionally excludes values, predictions, and models."""

    policy: ProfiledMtfForwardCpuCampaignPolicy = field(repr=False)
    result: ProfiledMtfForwardCpuCampaignResult = field(repr=False)
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            self.receipt_path.name != "campaign-receipt.json"
            or self.receipt_path.is_symlink()
            or not _is_sha256(self.receipt_sha256)
            or self.result.policy_sha256 != self.policy.policy_sha256
        ):
            raise ValueError("profiled MTF CPU campaign receipt is invalid")


def freeze_profiled_mtf_forward_cpu_campaign_policy(
    dataset_receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    *,
    code_revision_sha256: str,
) -> ProfiledMtfForwardCpuCampaignPolicy:
    """Predeclare one CPU-only control family against the immutable dataset receipt."""

    _require_sha256(code_revision_sha256, "code_revision_sha256")
    result = dataset_receipt.result
    return ProfiledMtfForwardCpuCampaignPolicy(
        dataset_receipt_sha256=dataset_receipt.receipt_sha256,
        dataset_policy_sha256=dataset_receipt.policy.policy_sha256,
        dataset_result_sha256=result.result_sha256,
        dataset_contract_sha256=result.dataset_contract_sha256,
        code_revision_sha256=code_revision_sha256,
        policy_sha256=_sha256_json(
            _policy_unsigned_payload_from_fields(
                dataset_receipt_sha256=dataset_receipt.receipt_sha256,
                dataset_policy_sha256=dataset_receipt.policy.policy_sha256,
                dataset_result_sha256=result.result_sha256,
                dataset_contract_sha256=result.dataset_contract_sha256,
                code_revision_sha256=code_revision_sha256,
            )
        ),
    )


def build_profiled_mtf_forward_cpu_feature_matrix(
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization,
) -> ProfiledMtfForwardCpuFeatureMatrix:
    """Build fixed short-profile controls from input prefixes only, never outcomes."""

    result = materialization.receipt.result
    if result.dataset_contract_sha256 is None:
        raise ValueError("CPU campaign dataset contract is unavailable")
    values: list[tuple[Decimal, ...]] = []
    row_keys: list[tuple[int, int, str, str]] = []
    control_sha256s: list[str] = []
    for row in materialization.rows:
        snapshot = materialization.snapshots[row.pair_index]
        minute_bars = snapshot.input_prefixes[row.leg_index]
        cutoff = row.input_end
        session = _regular_session_for_cutoff(cutoff)
        projection = build_target_free_mtf_feature_projection(
            source_contract_sha256=result.dataset_contract_sha256,
            source_dataset_hash=row.raw_snapshot_sha256,
            catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
            profile_id=PROFILED_MTF_FORWARD_CPU_CAMPAIGN_PROFILE_ID,
            minute_bars=minute_bars,
            bars_by_timeframe=resample_completed_causal_prefix(
                minute_bars,
                session=session.window,
                cutoff=cutoff,
            ),
            cutoff=cutoff,
        )
        control = build_profiled_mtf_flattened_control(projection)
        if control.feature_width != PROFILED_MTF_FORWARD_CPU_CAMPAIGN_FEATURE_WIDTH:
            raise ValueError("CPU campaign feature width changed")
        row_keys.append(
            (row.pair_index, row.leg_index, row.split, row.raw_snapshot_sha256)
        )
        values.append(control.flattened_values)
        control_sha256s.append(control.control_sha256)
    value_tuple = tuple(values)
    key_tuple = tuple(row_keys)
    control_tuple = tuple(control_sha256s)
    return ProfiledMtfForwardCpuFeatureMatrix(
        dataset_contract_sha256=result.dataset_contract_sha256,
        row_keys=key_tuple,
        values=value_tuple,
        control_sha256s=control_tuple,
        feature_matrix_sha256=_feature_matrix_sha256(
            dataset_contract_sha256=result.dataset_contract_sha256,
            row_keys=key_tuple,
            values=value_tuple,
            control_sha256s=control_tuple,
        ),
    )


def run_profiled_mtf_forward_cpu_campaign(
    policy: ProfiledMtfForwardCpuCampaignPolicy,
    *,
    dataset_receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization | None,
) -> ProfiledMtfForwardCpuCampaignResult:
    """Run fixed controls in memory, excluding purge rows and never promoting a result."""

    _reattest_policy(
        policy=policy,
        dataset_receipt=dataset_receipt,
        materialization=materialization,
    )
    if materialization is None:
        return _input_unavailable_result(policy=policy)
    feature_matrix = build_profiled_mtf_forward_cpu_feature_matrix(materialization)
    metrics = _evaluate_fixed_controls(feature_matrix, materialization)
    return _evaluated_result(policy=policy, feature_matrix=feature_matrix, metrics=metrics)


def write_profiled_mtf_forward_cpu_campaign_receipt(
    result: ProfiledMtfForwardCpuCampaignResult,
    *,
    policy: ProfiledMtfForwardCpuCampaignPolicy,
    artifact_root: Path | str,
    repo_root: Path | str,
    attempt_id: str,
) -> ProfiledMtfForwardCpuCampaignReceipt:
    """Write source-safe campaign evidence without values, predictions, or model state."""

    _require_attempt_id(attempt_id)
    if result.policy_sha256 != policy.policy_sha256:
        raise ValueError("CPU campaign result policy changed")
    directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "research",
        PROFILED_MTF_FORWARD_CPU_CAMPAIGN_ID,
        attempt_id,
    )
    unsigned_payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": PROFILED_MTF_FORWARD_CPU_CAMPAIGN_ID,
        "attempt_id": attempt_id,
        "policy": policy.safe_payload(),
        "result": result.safe_payload(),
        "artifact_policy": _artifact_policy(),
    }
    payload = {**unsigned_payload, "receipt_sha256": _sha256_json(unsigned_payload)}
    receipt_path = directory / "campaign-receipt.json"
    _write_or_verify_json(receipt_path, payload)
    return ProfiledMtfForwardCpuCampaignReceipt(
        policy=policy,
        result=result,
        receipt_path=receipt_path,
        receipt_sha256=payload["receipt_sha256"],
    )


def _regular_session_for_cutoff(cutoff: datetime):
    eastern_date = cutoff.astimezone(US_EQUITY_EASTERN).date()
    session = us_equity_2026_session(eastern_date)
    if (
        session is None
        or session.kind != "regular"
        or cutoff.astimezone(US_EQUITY_EASTERN).time().replace(tzinfo=None) != time(15, 30)
    ):
        raise ValueError("CPU campaign causal session is invalid")
    return session


def _evaluate_fixed_controls(
    feature_matrix: ProfiledMtfForwardCpuFeatureMatrix,
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization,
) -> tuple[ProfiledMtfForwardCpuCandidateMetric, ...]:
    from numpy import asarray, mean
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rows = materialization.rows
    expected_keys = tuple(
        (row.pair_index, row.leg_index, row.split, row.raw_snapshot_sha256) for row in rows
    )
    if feature_matrix.row_keys != expected_keys:
        raise ValueError("CPU campaign feature/target rows diverged")
    features = asarray(feature_matrix.values, dtype=float)
    targets = asarray([float(row.target_log_return) for row in rows], dtype=float)
    splits = [row.split for row in rows]
    train_indices = [index for index, split in enumerate(splits) if split == "train"]
    purge_indices = [index for index, split in enumerate(splits) if split == "purge"]
    validation_indices = [index for index, split in enumerate(splits) if split == "validation"]
    if (len(train_indices), len(purge_indices), len(validation_indices)) != (40, 4, 16):
        raise ValueError("CPU campaign pair split changed")
    train_features = features[train_indices]
    validation_features = features[validation_indices]
    train_targets = targets[train_indices]
    validation_targets = targets[validation_indices]
    permuted_train_targets = train_targets.reshape(20, 2)[::-1].reshape(-1)
    factories = {
        "ridge_alpha_10": lambda: make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "hist_gradient_depth_limited": lambda: HistGradientBoostingRegressor(
            learning_rate=0.1,
            l2_regularization=1.0,
            max_iter=30,
            max_leaf_nodes=3,
            min_samples_leaf=10,
            random_state=0,
        ),
    }
    metrics: list[ProfiledMtfForwardCpuCandidateMetric] = []
    for candidate_id in PROFILED_MTF_FORWARD_CPU_CAMPAIGN_CANDIDATE_IDS:
        if candidate_id == "no_trade_zero":
            predictions = validation_targets * 0.0
            permuted_predictions = validation_targets * 0.0
        else:
            original_model = factories[candidate_id]()
            original_model.fit(train_features, train_targets)
            predictions = original_model.predict(validation_features)
            permuted_model = factories[candidate_id]()
            permuted_model.fit(train_features, permuted_train_targets)
            permuted_predictions = permuted_model.predict(validation_features)
        metric_fields = {
            "candidate_id": candidate_id,
            "validation_mae": float(mean(abs(validation_targets - predictions))),
            "validation_directional_hit_rate": float(
                mean((predictions > 0.0) == (validation_targets > 0.0))
            ),
            "permuted_validation_mae": float(
                mean(abs(validation_targets - permuted_predictions))
            ),
            "permuted_validation_directional_hit_rate": float(
                mean((permuted_predictions > 0.0) == (validation_targets > 0.0))
            ),
        }
        metrics.append(
            ProfiledMtfForwardCpuCandidateMetric(
                **metric_fields,
                evidence_sha256=_candidate_evidence_sha256_fields(metric_fields),
            )
        )
    return tuple(metrics)


def _reattest_policy(
    *,
    policy: ProfiledMtfForwardCpuCampaignPolicy,
    dataset_receipt: ProfiledMtfForwardSupervisedDatasetReceipt,
    materialization: ProfiledMtfForwardSupervisedDatasetMaterialization | None,
) -> None:
    result = dataset_receipt.result
    if (
        policy.dataset_receipt_sha256 != dataset_receipt.receipt_sha256
        or policy.dataset_policy_sha256 != dataset_receipt.policy.policy_sha256
        or policy.dataset_result_sha256 != result.result_sha256
        or policy.dataset_contract_sha256 != result.dataset_contract_sha256
    ):
        raise ValueError("CPU campaign dataset receipt is stale or mismatched")
    if materialization is not None and materialization.receipt != dataset_receipt:
        raise ValueError("CPU campaign dataset materialization is stale or mismatched")
    if (materialization is not None) != (result.status == "materialized"):
        raise ValueError("CPU campaign dataset availability is inconsistent")


def _input_unavailable_result(
    *,
    policy: ProfiledMtfForwardCpuCampaignPolicy,
) -> ProfiledMtfForwardCpuCampaignResult:
    fields = {
        "policy_sha256": policy.policy_sha256,
        "dataset_receipt_sha256": policy.dataset_receipt_sha256,
        "dataset_result_sha256": policy.dataset_result_sha256,
        "status": "input_unavailable",
        "feature_matrix_sha256": None,
        "train_row_count": 0,
        "purge_row_count": 0,
        "validation_row_count": 0,
        "candidate_metrics": (),
    }
    return ProfiledMtfForwardCpuCampaignResult(
        **fields,
        result_sha256=_result_sha256_fields(fields),
    )


def _evaluated_result(
    *,
    policy: ProfiledMtfForwardCpuCampaignPolicy,
    feature_matrix: ProfiledMtfForwardCpuFeatureMatrix,
    metrics: tuple[ProfiledMtfForwardCpuCandidateMetric, ...],
) -> ProfiledMtfForwardCpuCampaignResult:
    fields = {
        "policy_sha256": policy.policy_sha256,
        "dataset_receipt_sha256": policy.dataset_receipt_sha256,
        "dataset_result_sha256": policy.dataset_result_sha256,
        "status": "cpu_evaluated_not_promoting",
        "feature_matrix_sha256": feature_matrix.feature_matrix_sha256,
        "train_row_count": 40,
        "purge_row_count": 4,
        "validation_row_count": 16,
        "candidate_metrics": metrics,
    }
    return ProfiledMtfForwardCpuCampaignResult(
        **fields,
        result_sha256=_result_sha256_fields(fields),
    )


def _policy_unsigned_payload(policy: ProfiledMtfForwardCpuCampaignPolicy) -> dict[str, object]:
    return _policy_unsigned_payload_from_fields(
        dataset_receipt_sha256=policy.dataset_receipt_sha256,
        dataset_policy_sha256=policy.dataset_policy_sha256,
        dataset_result_sha256=policy.dataset_result_sha256,
        dataset_contract_sha256=policy.dataset_contract_sha256,
        code_revision_sha256=policy.code_revision_sha256,
    )


def _policy_unsigned_payload_from_fields(
    *,
    dataset_receipt_sha256: str,
    dataset_policy_sha256: str,
    dataset_result_sha256: str,
    dataset_contract_sha256: str | None,
    code_revision_sha256: str,
) -> dict[str, object]:
    return {
        "campaign_id": PROFILED_MTF_FORWARD_CPU_CAMPAIGN_ID,
        "dataset_receipt_sha256": dataset_receipt_sha256,
        "dataset_policy_sha256": dataset_policy_sha256,
        "dataset_result_sha256": dataset_result_sha256,
        "dataset_contract_sha256": dataset_contract_sha256,
        "code_revision_sha256": code_revision_sha256,
        "feature_representation": {
            "profile_id": PROFILED_MTF_FORWARD_CPU_CAMPAIGN_PROFILE_ID,
            "timeframes": ["1m", "5m", "10m", "1h", "3h"],
            "ragged_window_lengths": [15, 3, 3, 2, 2],
            "per_bar_features": [
                "close_relative_to_first_completed_bar",
                "volume_relative_to_first_completed_bar_or_one",
            ],
            "flattened_feature_width": PROFILED_MTF_FORWARD_CPU_CAMPAIGN_FEATURE_WIDTH,
            "input_cutoff": "15:30 America/New_York",
            "outcome_rows_used_as_features": False,
            "cross_timeframe_row_alignment": False,
        },
        "pair_level_temporal_split": {
            "train_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[0],
            "purge_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[1],
            "validation_pair_count": PROFILED_MTF_FORWARD_SUPERVISED_DATASET_TEMPORAL_SPLIT[2],
        },
        "baseline": "no_trade_zero_return",
        "fixed_classical_controls": [
            "ridge_alpha_10",
            "hist_gradient_depth_limited",
        ],
        "metrics": list(PROFILED_MTF_FORWARD_CPU_CAMPAIGN_METRIC_NAMES),
        "strongest_kill_test": "train_pair_block_target_reversal",
        "stop_rule": "no_tuning_or_promotion_after_single_fixed_validation_pass",
        "compute": "cpu_only",
    }


def _feature_matrix_sha256(
    *,
    dataset_contract_sha256: str,
    row_keys: tuple[tuple[int, int, str, str], ...],
    values: tuple[tuple[Decimal, ...], ...],
    control_sha256s: tuple[str, ...],
) -> str:
    return _sha256_json(
        {
            "dataset_contract_sha256": dataset_contract_sha256,
            "rows": [
                {
                    "row_key": list(row_key),
                    "control_sha256": control_sha256,
                    "values": [str(value) for value in row],
                }
                for row_key, row, control_sha256 in zip(
                    row_keys, values, control_sha256s, strict=True
                )
            ],
        }
    )


def _candidate_evidence_sha256(metric: ProfiledMtfForwardCpuCandidateMetric) -> str:
    return _candidate_evidence_sha256_fields(
        {
            "candidate_id": metric.candidate_id,
            "validation_mae": metric.validation_mae,
            "validation_directional_hit_rate": metric.validation_directional_hit_rate,
            "permuted_validation_mae": metric.permuted_validation_mae,
            "permuted_validation_directional_hit_rate": (
                metric.permuted_validation_directional_hit_rate
            ),
        }
    )


def _candidate_evidence_sha256_fields(fields: dict[str, object]) -> str:
    return _sha256_json(fields)


def _result_sha256(result: ProfiledMtfForwardCpuCampaignResult) -> str:
    return _result_sha256_fields(
        {
            "policy_sha256": result.policy_sha256,
            "dataset_receipt_sha256": result.dataset_receipt_sha256,
            "dataset_result_sha256": result.dataset_result_sha256,
            "status": result.status,
            "feature_matrix_sha256": result.feature_matrix_sha256,
            "train_row_count": result.train_row_count,
            "purge_row_count": result.purge_row_count,
            "validation_row_count": result.validation_row_count,
            "candidate_metrics": result.candidate_metrics,
        }
    )


def _result_sha256_fields(fields: dict[str, object]) -> str:
    metrics = fields["candidate_metrics"]
    return _sha256_json(
        {
            **{key: value for key, value in fields.items() if key != "candidate_metrics"},
            "candidate_metrics": [
                metric.safe_payload() for metric in metrics
            ],
        }
    )


def _result_scope(*, cpu_trained: bool) -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "predictions_persisted": False,
        "model_weights_persisted": False,
        "model_trained_cpu_only_in_memory": cpu_trained,
        "gpu_allocated": False,
        "pnl_calculated": False,
        "paper_or_broker_action": False,
        "network_or_credentials_used": False,
        "promotion_or_winner_selected": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "raw_rows_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "predictions_persisted": False,
        "weights_persisted": False,
    }


def _write_or_verify_json(path: Path, payload: dict[str, object]) -> None:
    if path.is_symlink():
        raise ValueError("CPU campaign receipt path must not be a symlink")
    encoded = _canonical_json(payload)
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise ValueError("CPU campaign receipt is unavailable") from error
        if existing != encoded:
            raise ValueError("CPU campaign receipt conflicts")
        return
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded.decode("utf-8"))
    except FileExistsError:
        _write_or_verify_json(path, payload)


def _canonical_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_json(payload: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _require_sha256(value: object, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must be a SHA-256 identity")


def _require_attempt_id(value: str) -> None:
    if _ATTEMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("CPU campaign attempt_id is invalid")

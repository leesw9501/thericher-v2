"""Engineering-only validation for one hash-attested Norgate broad panel.

This module deliberately stops before campaign construction, paper execution,
model selection, ensembles, or PnL.  Its input is a Data-owned, verified,
derived feature artifact; callers must reattest that artifact before building
this ``NorgateBroadDevelopmentDataset``.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from thericher_v2.data.norgate_broad_development_artifact import (
    NorgateBroadDevelopmentFeatureArtifact,
    load_verified_norgate_broad_development_feature_artifact,
)
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
VALIDATION_VERSION = "norgate-broad-development-validation-r1"
FEATURE_WIDTH = 20
DEVELOPMENT_START_INDEX = 20
DEVELOPMENT_END_INDEX = 319
PURGE_START_INDEX = 320
PURGE_END_INDEX = 321
VALIDATION_START_INDEX = 322
VALIDATION_END_INDEX = 480
CPU_LINEAR_STEPS = 160
CPU_LINEAR_LEARNING_RATE = 0.08
CPU_LINEAR_L2 = 0.0001
STRONG_RESULT_ACCURACY = 0.56
FIXED_PARENT_DATASET_HASH = (
    "sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d"
)
FIXED_PARENT_MANIFEST_HASH = (
    "sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e"
)
FIXED_PARENT_ROW_COUNTS = {
    "development": 154249,
    "purge": 1036,
    "validation": 82040,
}

_RESULT_SCOPE = {
    "engineering_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "model_promotion_eligible": False,
    "ensemble_eligible": False,
    "paper_trading_eligible": False,
    "pnl_or_profitability_claim": False,
}
_LIMITATIONS = (
    "Complete-history selected symbols are survivorship and availability conditioned.",
    "Raw price adjustment and corporate-action semantics remain unverified.",
    "The discontinuity mask is a future-aware data-quality condition, not a live rule.",
    "Flat raw open-to-open outcomes are labeled non-positive (class 0).",
    "Date-clustered observations are not independent cross-sectional samples.",
    "Validation feature windows overlap late development bars despite the decision-date purge.",
)


@dataclass(frozen=True, slots=True)
class NorgateBroadDevelopmentDataset:
    """Verified, canonical arrays supplied by the Data-owned feature artifact."""

    artifact_dir: Path
    artifact_hash: str
    contract_hash: str
    parent_dataset_hash: str
    parent_manifest_hash: str
    features: Any
    labels: Any
    decision_indices: Any
    decision_dates: Any
    source_start_indices: Any
    source_end_indices: Any
    entry_indices: Any
    exit_indices: Any
    symbol_ranks: Any
    split_ids: Any
    discontinuity_excluded_count: int
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NorgateCudaJobSpec:
    """One fixed non-selectable CUDA architecture/seed combination."""

    job_id: str
    model_family: Literal["mlp", "temporal_conv"]
    seed: int
    epochs: int = 32
    batch_size: int = 8192
    learning_rate: float = 0.0005
    weight_decay: float = 0.001


CUDA_JOB_SPECS = (
    NorgateCudaJobSpec(
        "mlp-seed-71",
        "mlp",
        71,
        epochs=24,
        batch_size=4096,
        learning_rate=0.001,
        weight_decay=0.0001,
    ),
    NorgateCudaJobSpec(
        "mlp-seed-113",
        "mlp",
        113,
        epochs=24,
        batch_size=4096,
        learning_rate=0.001,
        weight_decay=0.0001,
    ),
    NorgateCudaJobSpec(
        "temporal-conv-seed-71",
        "temporal_conv",
        71,
        epochs=24,
        batch_size=4096,
        learning_rate=0.0005,
        weight_decay=0.0001,
    ),
    NorgateCudaJobSpec(
        "temporal-conv-seed-113",
        "temporal_conv",
        113,
        epochs=24,
        batch_size=4096,
        learning_rate=0.0005,
        weight_decay=0.0001,
    ),
)


@dataclass(frozen=True, slots=True)
class NorgateCpuBaselineResult:
    """Persisted CPU baseline evidence for one frozen derived feature artifact."""

    summary_path: Path
    summary_sha256: str
    artifact_hash: str
    contract_hash: str


@dataclass(frozen=True, slots=True)
class NorgateCudaJobResult:
    """Persisted evidence for one fixed CUDA exploration job."""

    job_id: str
    summary_path: Path
    summary_sha256: str
    checkpoint_path: Path
    checkpoint_sha256: str
    prediction_path: Path
    prediction_sha256: str
    review_required: bool


CudaTrainer = Callable[
    [NorgateCudaJobSpec, Any, Any, Any, Path], tuple[Any, Mapping[str, Any]]
]


def load_verified_norgate_broad_development_dataset(
    feature_artifact_dir: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateBroadDevelopmentDataset:
    """Re-attest the Data-owned artifact before every CPU or CUDA invocation."""

    artifact = load_verified_norgate_broad_development_feature_artifact(
        feature_artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return _dataset_from_verified_feature_artifact(artifact)


def run_norgate_broad_development_cpu_baseline_from_artifact(
    feature_artifact_dir: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    run_id: str = VALIDATION_VERSION,
    repo_root: Path | None = None,
    code_revision: str = "unrecorded",
) -> NorgateCpuBaselineResult:
    """Re-attest the raw lineage, then write the CPU evidence outside Git."""

    dataset = load_verified_norgate_broad_development_dataset(
        feature_artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return run_norgate_broad_development_cpu_baseline(
        dataset,
        artifact_root=artifact_root,
        run_id=run_id,
        repo_root=repo_root,
        code_revision=code_revision,
    )


def run_norgate_broad_development_cuda_job_from_artifact(
    feature_artifact_dir: Path,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    run_id: str = VALIDATION_VERSION,
    job_id: str,
    repo_root: Path | None = None,
    code_revision: str = "unrecorded",
) -> NorgateCudaJobResult:
    """Re-attest raw and derived hashes immediately before one CUDA job starts."""

    dataset = load_verified_norgate_broad_development_dataset(
        feature_artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return run_norgate_broad_development_cuda_job(
        dataset,
        artifact_root=artifact_root,
        run_id=run_id,
        job_id=job_id,
        repo_root=repo_root,
        code_revision=code_revision,
    )


def run_norgate_broad_development_cpu_baseline(
    dataset: NorgateBroadDevelopmentDataset,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    run_id: str = VALIDATION_VERSION,
    repo_root: Path | None = None,
    code_revision: str = "unrecorded",
) -> NorgateCpuBaselineResult:
    """Write deterministic CPU baselines after fail-closed dataset checks."""

    arrays = _validated_arrays(dataset)
    output_dir = _validation_output_dir(
        artifact_root,
        run_id=run_id,
        repo_root=repo_root or Path.cwd(),
    )
    summary_path = output_dir / "cpu-baseline.json"
    if summary_path.exists():
        raise FileExistsError(f"CPU baseline already exists: {summary_path}")

    numpy = _numpy()
    development = arrays["split_ids"] == "development"
    validation = arrays["split_ids"] == "validation"
    means, scales = _fit_standardization(arrays["features"][development])
    standardized = (arrays["features"] - means) / scales
    linear_weights, linear_bias = _fit_regularized_linear(
        standardized[development],
        arrays["labels"][development],
    )
    always_up_probabilities = numpy.ones(int(validation.sum()), dtype=numpy.float64)
    linear_probabilities = _sigmoid(
        standardized[validation] @ linear_weights + linear_bias
    )
    payload = _base_payload(
        dataset,
        arrays,
        code_revision=code_revision,
        phase="cpu_baseline",
    )
    payload["cpu_baselines"] = {
        "development_preprocessing": {
            "kind": "feature_standardization_v1",
            "fit_split": "development",
            "means": [float(value) for value in means],
            "scales": [float(value) for value in scales],
            "sha256": _sha256_json(
                {
                    "means": [float(value) for value in means],
                    "scales": [float(value) for value in scales],
                }
            ),
        },
        "always_up": _date_clustered_metrics(
            arrays["labels"][validation],
            always_up_probabilities,
            arrays["decision_dates"][validation],
        ),
        "regularized_linear": {
            "hyperparameters": {
                "steps": CPU_LINEAR_STEPS,
                "learning_rate": CPU_LINEAR_LEARNING_RATE,
                "l2": CPU_LINEAR_L2,
                "fit_split": "development",
                "row_shuffle": False,
            },
            "weights_sha256": _sha256_array(linear_weights),
            "bias": float(linear_bias),
            "validation": _date_clustered_metrics(
                arrays["labels"][validation],
                linear_probabilities,
                arrays["decision_dates"][validation],
            ),
        },
    }
    payload["cpu_baselines"]["strong_result_review_required"] = any(
        item["date_mean_accuracy"] >= STRONG_RESULT_ACCURACY
        for item in (
            payload["cpu_baselines"]["always_up"],
            payload["cpu_baselines"]["regularized_linear"]["validation"],
        )
    )
    _write_json_new(summary_path, payload)
    return NorgateCpuBaselineResult(
        summary_path=summary_path,
        summary_sha256=_sha256_file(summary_path),
        artifact_hash=dataset.artifact_hash,
        contract_hash=dataset.contract_hash,
    )


def run_norgate_broad_development_cuda_job(
    dataset: NorgateBroadDevelopmentDataset,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    run_id: str = VALIDATION_VERSION,
    job_id: str,
    repo_root: Path | None = None,
    code_revision: str = "unrecorded",
    trainer: CudaTrainer | None = None,
) -> NorgateCudaJobResult:
    """Run exactly one fixed CUDA job after verified CPU baseline evidence."""

    arrays = _validated_arrays(dataset)
    spec = _cuda_job_spec(job_id)
    output_dir = _validation_output_dir(
        artifact_root,
        run_id=run_id,
        repo_root=repo_root or Path.cwd(),
    )
    cpu_summary = _read_verified_cpu_summary(output_dir / "cpu-baseline.json", dataset)
    job_dir = output_dir / "cuda" / spec.job_id
    checkpoint_path = job_dir / "checkpoint.pt"
    prediction_path = job_dir / "validation-predictions.npz"
    summary_path = job_dir / "summary.json"
    if checkpoint_path.exists() or prediction_path.exists() or summary_path.exists():
        raise FileExistsError(f"CUDA job already exists: {spec.job_id}")

    development = arrays["split_ids"] == "development"
    validation = arrays["split_ids"] == "validation"
    means, scales = _fit_standardization(arrays["features"][development])
    expected_standardization_hash = cpu_summary["cpu_baselines"]["development_preprocessing"][
        "sha256"
    ]
    observed_standardization_hash = _sha256_json(
        {
            "means": [float(value) for value in means],
            "scales": [float(value) for value in scales],
        }
    )
    if observed_standardization_hash != expected_standardization_hash:
        raise ValueError("CUDA standardization does not match the verified CPU baseline")
    standardized = (arrays["features"] - means) / scales
    job_dir.mkdir(parents=True, exist_ok=False)
    selected_trainer = trainer or _train_torch_cuda
    try:
        probabilities, trainer_evidence = selected_trainer(
            spec,
            standardized[development],
            arrays["labels"][development],
            standardized[validation],
            checkpoint_path,
        )
        if trainer_evidence.get("safe_weights_only_reload") is not True:
            raise ValueError("CUDA trainer did not prove a safe weights-only checkpoint reload")
        metrics = _date_clustered_metrics(
            arrays["labels"][validation],
            probabilities,
            arrays["decision_dates"][validation],
        )
        checkpoint_hash = _sha256_file(checkpoint_path)
        prediction_hash = _write_validation_predictions(
            prediction_path,
            arrays,
            validation=validation,
            probabilities=probabilities,
        )
        payload = _base_payload(
            dataset,
            arrays,
            code_revision=code_revision,
            phase="cuda_exploration",
        )
        review_required = (
            metrics["date_mean_accuracy"] >= STRONG_RESULT_ACCURACY
            or metrics["date_mean_balanced_accuracy"] >= STRONG_RESULT_ACCURACY
        )
        payload["cuda_job"] = {
            "job_id": spec.job_id,
            "model_family": spec.model_family,
            "seed": spec.seed,
            "fixed_batch": True,
            "selection_eligible": False,
            "ensemble_eligible": False,
            "hyperparameters": {
                "epochs": spec.epochs,
                "batch_size": spec.batch_size,
                "learning_rate": spec.learning_rate,
                "weight_decay": spec.weight_decay,
                "row_shuffle": False,
            },
            "validation": metrics,
            "checkpoint": {
                "path": str(checkpoint_path.resolve()),
                "sha256": checkpoint_hash,
                "safe_weights_only_reload": trainer_evidence["safe_weights_only_reload"],
            },
            "validation_predictions": {
                "path": str(prediction_path.resolve()),
                "sha256": prediction_hash,
                "alignment": "decision_index_then_candidate_rank",
                "future_ensemble_use": False,
            },
            "trainer": dict(trainer_evidence),
            "review_required_before_any_follow_up": review_required,
            "stop_rule": (
                "No tuning, seed expansion, model selection, ensemble, or reuse beyond "
                "the four fixed jobs without a new contract."
            ),
        }
        _write_json_new(summary_path, payload)
    except Exception:
        if not summary_path.exists():
            for path in (checkpoint_path, prediction_path):
                if path.exists():
                    path.unlink()
        if job_dir.exists() and not any(job_dir.iterdir()):
            job_dir.rmdir()
        raise
    return NorgateCudaJobResult(
        job_id=spec.job_id,
        summary_path=summary_path,
        summary_sha256=_sha256_file(summary_path),
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=_sha256_file(checkpoint_path),
        prediction_path=prediction_path,
        prediction_sha256=_sha256_file(prediction_path),
        review_required=review_required,
    )


def _dataset_from_verified_feature_artifact(
    artifact: NorgateBroadDevelopmentFeatureArtifact,
) -> NorgateBroadDevelopmentDataset:
    contract = artifact.contract
    if not isinstance(contract, Mapping):
        raise ValueError("verified Norgate feature artifact contract is invalid")
    scope = contract.get("scope")
    parent = contract.get("parent_panel")
    transform = contract.get("transform")
    conditioning = contract.get("discontinuity_conditioning")
    if not all(
        isinstance(value, Mapping)
        for value in (scope, parent, transform, conditioning)
    ):
        raise ValueError("verified Norgate feature artifact contract is incomplete")
    required_scope = {
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
    if any(scope.get(key) is not value for key, value in required_scope.items()):
        raise ValueError("verified Norgate feature artifact scope is invalid")
    if parent.get("raw_scope") != {"model_eligible": False, "gpu_eligible": False}:
        raise ValueError("verified Norgate feature artifact parent scope is invalid")
    if (
        parent.get("dataset_hash") != artifact.parent_dataset_hash
        or parent.get("manifest_hash") != artifact.parent_manifest_hash
    ):
        raise ValueError("verified Norgate feature artifact parent hashes are inconsistent")
    if (
        transform.get("feature_return_count") != FEATURE_WIDTH
        or transform.get("feature_source_index_range") != "t-20..t"
        or transform.get("max_feature_source_index") != "t"
        or transform.get("entry_index") != "t+1"
        or transform.get("exit_index") != "t+2"
        or conditioning.get("checked_index_range") != "t-20..t+2"
    ):
        raise ValueError("verified Norgate feature artifact timing contract is invalid")
    numpy = _numpy()
    source_labels = numpy.asarray(artifact.label_array, dtype=numpy.int8)
    if not numpy.isin(source_labels, (0, 1)).all():
        raise ValueError("verified Norgate feature artifact binary labels are invalid")
    source_splits = numpy.asarray(artifact.split_ids, dtype=numpy.int8)
    split_names = numpy.asarray(("development", "purge", "validation"))
    if not numpy.isin(source_splits, (0, 1, 2)).all():
        raise ValueError("verified Norgate feature artifact split codes are invalid")
    observed_counts = {
        name: int((source_splits == code).sum())
        for code, name in enumerate(("development", "purge", "validation"))
    }
    if contract.get("row_counts") != observed_counts:
        raise ValueError("verified Norgate feature artifact row counts are inconsistent")
    fixed_parent_component_matches = (
        artifact.parent_dataset_hash == FIXED_PARENT_DATASET_HASH
        or artifact.parent_manifest_hash == FIXED_PARENT_MANIFEST_HASH
    )
    if fixed_parent_component_matches and (
        artifact.parent_dataset_hash != FIXED_PARENT_DATASET_HASH
        or artifact.parent_manifest_hash != FIXED_PARENT_MANIFEST_HASH
        or observed_counts != FIXED_PARENT_ROW_COUNTS
    ):
        raise ValueError("fixed Norgate parent row counts or lineage are inconsistent")
    selected_symbols = parent.get("selected_symbol_count")
    if not isinstance(selected_symbols, int) or selected_symbols <= 0:
        raise ValueError("verified Norgate feature artifact symbol count is invalid")
    potential_rows = (VALIDATION_END_INDEX - DEVELOPMENT_START_INDEX + 1) * selected_symbols
    excluded_count = potential_rows - len(source_labels)
    if excluded_count < 0:
        raise ValueError("verified Norgate feature artifact row count is invalid")
    limitations = contract.get("limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(value, str) and value for value in limitations
    ):
        raise ValueError("verified Norgate feature artifact limitations are invalid")
    return NorgateBroadDevelopmentDataset(
        artifact_dir=artifact.artifact_dir,
        artifact_hash=artifact.artifact_hash,
        contract_hash=artifact.contract_hash,
        parent_dataset_hash=artifact.parent_dataset_hash,
        parent_manifest_hash=artifact.parent_manifest_hash,
        features=artifact.feature_array,
        labels=source_labels,
        decision_indices=artifact.decision_indices,
        decision_dates=artifact.decision_dates,
        source_start_indices=artifact.source_start_indices,
        source_end_indices=artifact.source_end_indices,
        entry_indices=artifact.entry_indices,
        exit_indices=artifact.exit_indices,
        symbol_ranks=artifact.symbol_ranks,
        split_ids=split_names[source_splits],
        discontinuity_excluded_count=excluded_count,
        limitations=tuple(limitations),
    )


def _validated_arrays(dataset: NorgateBroadDevelopmentDataset) -> dict[str, Any]:
    if not isinstance(dataset, NorgateBroadDevelopmentDataset):
        raise TypeError("Norgate broad validation requires a verified Data-owned dataset")
    _require_sha256(dataset.artifact_hash, "artifact_hash")
    _require_sha256(dataset.contract_hash, "contract_hash")
    _require_sha256(dataset.parent_dataset_hash, "parent_dataset_hash")
    _require_sha256(dataset.parent_manifest_hash, "parent_manifest_hash")
    if dataset.discontinuity_excluded_count < 0:
        raise ValueError("discontinuity_excluded_count must be non-negative")
    numpy = _numpy()
    arrays = {
        "features": numpy.asarray(dataset.features, dtype=numpy.float64),
        "labels": numpy.asarray(dataset.labels, dtype=numpy.int8),
        "decision_indices": numpy.asarray(dataset.decision_indices, dtype=numpy.int64),
        "decision_dates": numpy.asarray(dataset.decision_dates).astype("datetime64[D]"),
        "source_start_indices": numpy.asarray(dataset.source_start_indices, dtype=numpy.int64),
        "source_end_indices": numpy.asarray(dataset.source_end_indices, dtype=numpy.int64),
        "entry_indices": numpy.asarray(dataset.entry_indices, dtype=numpy.int64),
        "exit_indices": numpy.asarray(dataset.exit_indices, dtype=numpy.int64),
        "symbol_ranks": numpy.asarray(dataset.symbol_ranks, dtype=numpy.int64),
        "split_ids": numpy.asarray(dataset.split_ids).astype("U16"),
    }
    count = len(arrays["labels"])
    if (
        count == 0
        or arrays["features"].shape != (count, FEATURE_WIDTH)
        or any(len(value) != count for key, value in arrays.items() if key != "features")
    ):
        raise ValueError("Norgate broad feature array shapes are invalid")
    if not numpy.isfinite(arrays["features"]).all() or not numpy.isin(
        arrays["labels"], (0, 1)
    ).all():
        raise ValueError("Norgate broad feature values or labels are invalid")
    if (arrays["symbol_ranks"] <= 0).any():
        raise ValueError("Norgate broad symbol ranks are invalid")
    if not (
        (arrays["source_start_indices"] == arrays["decision_indices"] - FEATURE_WIDTH)
        & (arrays["source_end_indices"] == arrays["decision_indices"])
        & (arrays["entry_indices"] == arrays["decision_indices"] + 1)
        & (arrays["exit_indices"] == arrays["decision_indices"] + 2)
    ).all():
        raise ValueError("Norgate broad source and label index contract is invalid")
    if not (arrays["source_end_indices"] < arrays["entry_indices"]).all():
        raise ValueError("Norgate broad features include a future entry bar")
    if not (arrays["entry_indices"] < arrays["exit_indices"]).all():
        raise ValueError("Norgate broad label order is invalid")
    expected_order = numpy.lexsort((arrays["symbol_ranks"], arrays["decision_indices"]))
    if not numpy.array_equal(expected_order, numpy.arange(count)):
        raise ValueError("Norgate broad feature rows must use canonical date/rank order")
    if not numpy.all(arrays["decision_dates"][1:] >= arrays["decision_dates"][:-1]):
        raise ValueError("Norgate broad decision dates must be chronological")
    _validate_split_contract(arrays)
    return arrays


def _validate_split_contract(arrays: Mapping[str, Any]) -> None:
    numpy = _numpy()
    expected = {
        "development": numpy.arange(DEVELOPMENT_START_INDEX, DEVELOPMENT_END_INDEX + 1),
        "purge": numpy.arange(PURGE_START_INDEX, PURGE_END_INDEX + 1),
        "validation": numpy.arange(VALIDATION_START_INDEX, VALIDATION_END_INDEX + 1),
    }
    if set(arrays["split_ids"]) != set(expected):
        raise ValueError("Norgate broad split names are invalid")
    for split_id, expected_indices in expected.items():
        observed_indices = numpy.unique(
            arrays["decision_indices"][arrays["split_ids"] == split_id]
        )
        if not numpy.array_equal(observed_indices, expected_indices):
            raise ValueError("Norgate broad temporal split is invalid")
    if int((arrays["split_ids"] == "development").sum()) <= 0:
        raise ValueError("Norgate broad development split is empty")
    if int((arrays["split_ids"] == "validation").sum()) <= 0:
        raise ValueError("Norgate broad validation split is empty")


def _fit_standardization(features: Any) -> tuple[Any, Any]:
    numpy = _numpy()
    means = features.mean(axis=0)
    scales = features.std(axis=0)
    scales = numpy.where(scales > 1e-12, scales, 1.0)
    if not numpy.isfinite(means).all() or not numpy.isfinite(scales).all():
        raise ValueError("development-only standardization is invalid")
    return means, scales


def _fit_regularized_linear(features: Any, labels: Any) -> tuple[Any, float]:
    numpy = _numpy()
    weights = numpy.zeros(FEATURE_WIDTH, dtype=numpy.float64)
    bias = 0.0
    target = labels.astype(numpy.float64)
    for _ in range(CPU_LINEAR_STEPS):
        probabilities = _sigmoid(features @ weights + bias)
        residual = probabilities - target
        gradient = features.T @ residual / len(target) + CPU_LINEAR_L2 * weights
        bias_gradient = float(residual.mean())
        weights -= CPU_LINEAR_LEARNING_RATE * gradient
        bias -= CPU_LINEAR_LEARNING_RATE * bias_gradient
    if not numpy.isfinite(weights).all() or not math.isfinite(bias):
        raise ValueError("regularized linear training diverged")
    return weights, bias


def _date_clustered_metrics(labels: Any, probabilities: Any, decision_dates: Any) -> dict[str, Any]:
    numpy = _numpy()
    labels = numpy.asarray(labels, dtype=numpy.int8)
    probabilities = numpy.asarray(probabilities, dtype=numpy.float64)
    decision_dates = numpy.asarray(decision_dates).astype("datetime64[D]")
    if len(labels) == 0 or len(probabilities) != len(labels):
        raise ValueError("validation metrics require matching nonempty arrays")
    if not numpy.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("validation probabilities are invalid")
    predictions = (probabilities >= 0.5).astype(numpy.int8)
    unique_dates, inverse = numpy.unique(decision_dates, return_inverse=True)
    date_accuracy = numpy.empty(len(unique_dates), dtype=numpy.float64)
    date_balanced_accuracy = numpy.empty(len(unique_dates), dtype=numpy.float64)
    date_brier = numpy.empty(len(unique_dates), dtype=numpy.float64)
    date_log_loss = numpy.empty(len(unique_dates), dtype=numpy.float64)
    for index in range(len(unique_dates)):
        selected = inverse == index
        date_accuracy[index] = float((predictions[selected] == labels[selected]).mean())
        positives = labels[selected] == 1
        negatives = ~positives
        recalls = []
        if positives.any():
            recalls.append(float((predictions[selected][positives] == 1).mean()))
        if negatives.any():
            recalls.append(float((predictions[selected][negatives] == 0).mean()))
        date_balanced_accuracy[index] = float(sum(recalls) / len(recalls))
        date_brier[index] = float(((probabilities[selected] - labels[selected]) ** 2).mean())
        clipped = numpy.clip(probabilities[selected], 1e-7, 1 - 1e-7)
        date_log_loss[index] = float(
            -(labels[selected] * numpy.log(clipped)
              + (1 - labels[selected]) * numpy.log(1 - clipped)).mean()
        )
    blocks = []
    for block_index, positions in enumerate(
        numpy.array_split(numpy.arange(len(unique_dates)), min(5, len(unique_dates))),
        start=1,
    ):
        if len(positions) == 0:
            continue
        mask = numpy.isin(inverse, positions)
        blocks.append(
            {
                "block": block_index,
                "start_date": str(unique_dates[positions[0]]),
                "end_date": str(unique_dates[positions[-1]]),
                "date_groups": int(len(positions)),
                "accuracy": float((predictions[mask] == labels[mask]).mean()),
            }
        )
    return {
        "row_count_descriptive_only": int(len(labels)),
        "date_group_count": int(len(unique_dates)),
        "date_mean_accuracy": float(date_accuracy.mean()),
        "date_median_accuracy": float(numpy.median(date_accuracy)),
        "date_min_accuracy": float(date_accuracy.min()),
        "date_max_accuracy": float(date_accuracy.max()),
        "date_mean_balanced_accuracy": float(date_balanced_accuracy.mean()),
        "date_mean_brier": float(date_brier.mean()),
        "date_mean_log_loss": float(date_log_loss.mean()),
        "positive_label_rate": float(labels.mean()),
        "mean_predicted_probability": float(probabilities.mean()),
        "contiguous_date_blocks": blocks,
        "iid_claim": False,
    }


def _train_torch_cuda(
    spec: NorgateCudaJobSpec,
    development_features: Any,
    development_labels: Any,
    validation_features: Any,
    checkpoint_path: Path,
) -> tuple[Any, Mapping[str, Any]]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is not available")
    torch.manual_seed(spec.seed)
    torch.cuda.manual_seed_all(spec.seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    device = torch.device("cuda")
    torch.cuda.reset_peak_memory_stats(device)
    train_x = torch.tensor(development_features, dtype=torch.float32, device=device)
    train_y = torch.tensor(development_labels, dtype=torch.float32, device=device).view(-1, 1)
    validation_x = torch.tensor(validation_features, dtype=torch.float32, device=device)
    model = _build_torch_model(spec, torch).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=spec.learning_rate,
        weight_decay=spec.weight_decay,
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    last_loss = 0.0
    for _ in range(spec.epochs):
        for start in range(0, len(train_x), spec.batch_size):
            end = min(start + spec.batch_size, len(train_x))
            logits = model(train_x[start:end])
            loss = loss_fn(logits, train_y[start:end])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            last_loss = float(loss.item())
    torch.cuda.synchronize(device)
    with torch.no_grad():
        probabilities = torch.sigmoid(model(validation_x)).view(-1).cpu().numpy()
    payload = {
        "schema_version": 1,
        "kind": "norgate_broad_development_cuda_checkpoint",
        "job_id": spec.job_id,
        "model_family": spec.model_family,
        "seed": spec.seed,
        "state_dict": model.state_dict(),
    }
    with checkpoint_path.open("xb") as handle:
        torch.save(payload, handle)
    _verify_torch_checkpoint(spec, checkpoint_path, torch)
    return probabilities, {
        "backend": "torch_cuda",
        "device": torch.cuda.get_device_name(device),
        "torch_version": torch.__version__,
        "epochs": spec.epochs,
        "examples": int(len(train_x)),
        "final_batch_loss": f"{last_loss:.8f}",
        "cuda_peak_memory_bytes": int(torch.cuda.max_memory_allocated(device)),
        "safe_weights_only_reload": True,
    }


def _build_torch_model(spec: NorgateCudaJobSpec, torch: Any) -> Any:
    if spec.model_family == "mlp":
        return torch.nn.Sequential(
            torch.nn.Linear(FEATURE_WIDTH, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, 16),
            torch.nn.ReLU(),
            torch.nn.Linear(16, 1),
        )
    if spec.model_family == "temporal_conv":
        return _causal_temporal_conv_model(torch)
    raise ValueError("unsupported fixed CUDA model family")


def _causal_temporal_conv_model(torch: Any) -> Any:
    class CausalTemporalConv(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.first = torch.nn.Conv1d(1, 16, kernel_size=3)
            self.second = torch.nn.Conv1d(16, 16, kernel_size=3, dilation=2)
            self.output = torch.nn.Linear(16, 1)

        def forward(self, features: Any) -> Any:
            values = features.unsqueeze(1)
            values = torch.nn.functional.pad(values, (2, 0))
            values = torch.nn.functional.relu(self.first(values))
            values = torch.nn.functional.pad(values, (4, 0))
            values = torch.nn.functional.relu(self.second(values))
            return self.output(values[:, :, -1])

    return CausalTemporalConv()


def _verify_torch_checkpoint(spec: NorgateCudaJobSpec, checkpoint_path: Path, torch: Any) -> None:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - torch-specific failure path.
        raise ValueError("CUDA checkpoint cannot be safely reloaded") from exc
    if not isinstance(payload, dict) or (
        payload.get("kind") != "norgate_broad_development_cuda_checkpoint"
        or payload.get("job_id") != spec.job_id
        or payload.get("model_family") != spec.model_family
        or payload.get("seed") != spec.seed
    ):
        raise ValueError("CUDA checkpoint contract is invalid")
    model = _build_torch_model(spec, torch)
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("CUDA checkpoint state is incompatible") from exc


def _write_validation_predictions(
    path: Path,
    arrays: Mapping[str, Any],
    *,
    validation: Any,
    probabilities: Any,
) -> str:
    numpy = _numpy()
    values = numpy.asarray(probabilities, dtype=numpy.float32)
    expected_count = int(validation.sum())
    if values.shape != (expected_count,) or not numpy.isfinite(values).all():
        raise ValueError("CUDA validation probabilities are invalid")
    payload = {
        "decision_indices": arrays["decision_indices"][validation],
        "decision_dates": arrays["decision_dates"][validation],
        "symbol_ranks": arrays["symbol_ranks"][validation],
        "labels": arrays["labels"][validation],
        "probabilities": values,
    }
    buffer = io.BytesIO()
    numpy.savez_compressed(buffer, **payload)
    data = buffer.getvalue()
    try:
        with numpy.load(io.BytesIO(data), allow_pickle=False) as archive:
            if tuple(archive.files) != tuple(payload):
                raise ValueError("CUDA validation prediction array names are invalid")
            for name, expected in payload.items():
                if not numpy.array_equal(archive[name], expected):
                    raise ValueError("CUDA validation prediction data is invalid")
    except (OSError, ValueError) as exc:
        raise ValueError("CUDA validation predictions cannot be safely reloaded") from exc
    with path.open("xb") as handle:
        handle.write(data)
    return _sha256_file(path)


def _base_payload(
    dataset: NorgateBroadDevelopmentDataset,
    arrays: Mapping[str, Any],
    *,
    code_revision: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "norgate_broad_development_engineering_validation",
        "validation_version": VALIDATION_VERSION,
        "phase": phase,
        "code_revision": _nonempty_text(code_revision, "code_revision"),
        "scope": dict(_RESULT_SCOPE),
        "lineage": {
            "derived_artifact_dir": str(dataset.artifact_dir.resolve()),
            "derived_artifact_hash": dataset.artifact_hash,
            "derived_contract_hash": dataset.contract_hash,
            "raw_parent_dataset_hash": dataset.parent_dataset_hash,
            "raw_parent_manifest_hash": dataset.parent_manifest_hash,
        },
        "feature_contract": {
            "feature_count": FEATURE_WIDTH,
            "feature_source_indices": "t-20 through t inclusive, as 20 close-to-close returns",
            "label": "raw open[t+2] / raw open[t+1] - 1 and sign",
            "decision_bar_complete": True,
            "maximum_feature_source_index_equals_decision_index": True,
            "entry_index_offset": 1,
            "exit_index_offset": 2,
            "no_lookahead_verified": True,
        },
        "temporal_split": {
            "development_decision_indices": [DEVELOPMENT_START_INDEX, DEVELOPMENT_END_INDEX],
            "purge_decision_indices": [PURGE_START_INDEX, PURGE_END_INDEX],
            "validation_decision_indices": [VALIDATION_START_INDEX, VALIDATION_END_INDEX],
            "development_date_groups": 300,
            "purge_date_groups": 2,
            "validation_date_groups": 159,
            "development_label_validation_feature_overlap": True,
        },
        "data_quality_conditioning": {
            "raw_discontinuity_threshold": 0.2,
            "rule": (
                "exclude any t-20 through t+2 window touching abs(raw overnight or "
                "close-to-close return) >= 0.20"
            ),
            "excluded_samples": dataset.discontinuity_excluded_count,
            "is_live_rule": False,
            "is_corporate_action_claim": False,
        },
        "sample_counts": {
            split_id: int((arrays["split_ids"] == split_id).sum())
            for split_id in ("development", "purge", "validation")
        },
        "limitations": list(dict.fromkeys((*_LIMITATIONS, *dataset.limitations))),
        "attestations": {
            "offline": True,
            "network_access": False,
            "credential_access": False,
            "broker_access": False,
            "local_paper_execution": False,
        },
    }


def _read_verified_cpu_summary(
    path: Path,
    dataset: NorgateBroadDevelopmentDataset,
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("verified CPU baseline is required before a CUDA job")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("CPU baseline summary is malformed") from exc
    if not isinstance(payload, dict) or (
        payload.get("phase") != "cpu_baseline"
        or payload.get("scope") != _RESULT_SCOPE
        or payload.get("lineage", {}).get("derived_artifact_hash") != dataset.artifact_hash
        or payload.get("lineage", {}).get("derived_contract_hash") != dataset.contract_hash
        or not isinstance(payload.get("cpu_baselines"), dict)
    ):
        raise ValueError("CPU baseline does not match the verified derived artifact")
    standardization = payload["cpu_baselines"].get("development_preprocessing")
    if not isinstance(standardization, dict) or not isinstance(standardization.get("sha256"), str):
        raise ValueError("CPU baseline preprocessing evidence is invalid")
    return payload


def _validation_output_dir(artifact_root: Path, *, run_id: str, repo_root: Path) -> Path:
    _safe_path_component(run_id, "run_id")
    root = Path(artifact_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("model artifact root must be an existing non-symlink directory")
    resolved_root = root.resolve()
    resolved_repo = Path(repo_root).resolve()
    docker_artifact_root = Path("/app/model_artifacts").resolve()
    docker_mount = (
        os.name != "nt"
        and resolved_repo == Path("/app").resolve()
        and (
            resolved_root == docker_artifact_root
            or docker_artifact_root in resolved_root.parents
        )
    )
    inside_repository = (
        resolved_root == resolved_repo or resolved_repo in resolved_root.parents
    )
    if inside_repository and not docker_mount:
        raise ValueError("model artifacts must stay outside the Git workspace")
    output = resolved_root / "norgate-broad-development-validation" / run_id
    if output.is_symlink() or not output.is_relative_to(resolved_root):
        raise ValueError("validation artifact path escapes the artifact root")
    return output


def _cuda_job_spec(job_id: str) -> NorgateCudaJobSpec:
    for spec in CUDA_JOB_SPECS:
        if spec.job_id == job_id:
            return spec
    raise ValueError("CUDA job_id is not in the fixed exploration batch")


def _write_json_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _sigmoid(values: Any) -> Any:
    numpy = _numpy()
    return 1.0 / (1.0 + numpy.exp(-numpy.clip(values, -40.0, 40.0)))


def _numpy() -> Any:
    import numpy

    return numpy


def _sha256_array(value: Any) -> str:
    return "sha256:" + hashlib.sha256(value.tobytes()).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _safe_path_component(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or any(character in value for character in ("/", "\\", ":"))
    ):
        raise ValueError(f"{field_name} must be one safe path component")


def _nonempty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()

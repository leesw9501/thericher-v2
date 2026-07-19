"""Finite Norgate-only engineering batch bound to one verified contract.

The batch is deliberately narrow: it materializes a static, source-separated
slice, runs two deterministic CPU baselines, and permits two separately invoked
CUDA MLP jobs. It never opens a provider, a broker, local paper execution, or a
candidate-selection path.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import signal
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from thericher_v2.data.norgate_broad_development_artifact import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    NorgateBroadDevelopmentFeatureArtifact,
    load_verified_norgate_broad_development_feature_artifact,
)
from thericher_v2.data.norgate_trial_development_panel import DEFAULT_MARKET_DATA_ROOT

from .norgate_tiingo_source_separated_contract import (
    CONTRACT_DIRECTORY,
    CONTRACT_VERSION,
    NorgateTiingoSourceSeparatedContract,
    load_verified_norgate_tiingo_source_separated_contract,
)
from .tiingo_norgate_cross_source_intake import (
    TiingoNorgateSourceSeparationContractInput,
    load_verified_tiingo_norgate_source_separation_contract_input,
)

BATCH_DIRECTORY = "norgate-tii-source-separated-batch"
BATCH_VERSION = "norgate-tii-source-separated-batch-r1"
FEATURE_WIDTH = 20
CPU_LINEAR_STEPS = 160
CPU_LINEAR_LEARNING_RATE = 0.08
CPU_LINEAR_L2 = 0.0001
STRONG_RESULT_ACCURACY = 0.56
CUDA_WALL_CLOCK_CAP_SECONDS = 180
CUDA_VRAM_CAP_MIB = 4096
CUDA_CUBLAS_WORKSPACE_CONFIG = ":4096:8"

DEFAULT_CONTRACT_ARTIFACT_DIR = (
    DEFAULT_MODEL_ARTIFACT_ROOT / CONTRACT_DIRECTORY / CONTRACT_VERSION
)
DEFAULT_COHORT_ARTIFACT_DIR = (
    DEFAULT_MODEL_ARTIFACT_ROOT
    / "tiingo-norgate-cross-source-cohort"
    / "tiingo-norgate-cross-source-cohort-r1"
)
DEFAULT_FEATURE_ARTIFACT_DIR = (
    DEFAULT_MODEL_ARTIFACT_ROOT
    / "norgate-broad-development-features"
    / "r2-3c1b21bde92e4623"
)

_DEVELOPMENT = range(20, 320)
_PURGE = range(320, 322)
_VALIDATION = range(322, 481)
_RESULT_SCOPE = {
    "engineering_only": True,
    "retrospective_static_mask_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "ensemble_eligible": False,
    "paper_trading_eligible": False,
    "pnl_eligible": False,
    "model_promotion_eligible": False,
    "profitability_eligible": False,
}
_CONTRACT_SCOPE = {
    "engineering_only": True,
    "future_bounded_batch_prepared": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "ensemble_eligible": False,
    "paper_trading_eligible": False,
    "pnl_eligible": False,
    "model_promotion_eligible": False,
    "profitability_eligible": False,
}
_LIMITATIONS = (
    "Rank linkage is static survivor and availability evidence, not point-in-time membership.",
    "Tiingo marker metadata is retrospective returned-session evidence, not event timing.",
    "Norgate raw-discontinuity conditioning uses t+2 and is not point-in-time safe.",
    "Raw adjustment and corporate-action semantics remain unverified.",
    "Validation is a fixed engineering observation, not a sealed holdout or selection input.",
)


@dataclass(frozen=True, slots=True)
class SourceSeparatedCudaJobSpec:
    """One code-pinned MLP configuration from the immutable contract roster."""

    job_id: str
    hidden_width: int
    seed: int
    epochs: int = 12
    batch_size: int = 1024
    learning_rate: float = 0.001
    weight_decay: float = 0.0001


CUDA_JOB_SPECS = (
    SourceSeparatedCudaJobSpec("mlp-hidden-32-seed-71", hidden_width=32, seed=71),
    SourceSeparatedCudaJobSpec("mlp-hidden-64-seed-113", hidden_width=64, seed=113),
)


@dataclass(frozen=True, slots=True)
class NorgateTiingoSourceSeparatedBatchDataset:
    """Only Norgate arrays selected through verified static mask metadata."""

    contract_dir: Path
    contract_hash: str
    cohort_manifest_hash: str
    feature_artifact_hash: str
    feature_contract_hash: str
    selected_slice_sha256: str
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
    rank_symbols: tuple[tuple[int, str], ...]
    sample_counts: Mapping[str, int]
    norgate_retention: Mapping[str, Any]
    contract: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SourceSeparatedCpuBaselineResult:
    """Immutable CPU evidence for the one permitted batch."""

    summary_path: Path
    summary_sha256: str
    contract_hash: str


@dataclass(frozen=True, slots=True)
class SourceSeparatedCudaJobResult:
    """Immutable successful CUDA evidence for one permitted MLP job."""

    job_id: str
    summary_path: Path
    summary_sha256: str
    checkpoint_path: Path
    checkpoint_sha256: str
    prediction_path: Path
    prediction_sha256: str
    review_required: bool


class SourceSeparatedCudaJobStopped(RuntimeError):
    """A bounded CUDA job stopped and wrote failure evidence."""

    def __init__(
        self,
        reason: str,
        *,
        elapsed_seconds: float | None = None,
        peak_memory_bytes: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.elapsed_seconds = elapsed_seconds
        self.peak_memory_bytes = peak_memory_bytes


class SourceSeparatedGpuLockHeldError(RuntimeError):
    """Raised when another bounded source-separated CUDA job owns the GPU."""


class SourceSeparatedGpuFileLock:
    """A deliberately narrow cross-process lock for this fixed CUDA batch."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._fd: int | None = None

    def __enter__(self) -> SourceSeparatedGpuFileLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(
                str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
        except FileExistsError as exc:
            raise SourceSeparatedGpuLockHeldError(
                f"source-separated GPU lock already exists: {self.lock_path}"
            ) from exc
        payload = {
            "schema_version": 1,
            "batch_version": BATCH_VERSION,
            "pid": os.getpid(),
            "created_at": datetime.now(UTC).isoformat(),
            "manual_recovery": (
                "remove this lock only after verifying no bounded CUDA job is running"
            ),
        }
        os.write(self._fd, json.dumps(payload, sort_keys=True).encode("utf-8"))
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


CudaTrainer = Callable[
    [SourceSeparatedCudaJobSpec, Any, Any, Any, Path, Callable[[], float]],
    tuple[Any, Mapping[str, Any]],
]


def default_norgate_tiingo_source_separated_batch_dir(
    *, artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT
) -> Path:
    """Return the single external output location for this fixed batch."""

    return Path(artifact_root) / BATCH_DIRECTORY / BATCH_VERSION


def load_verified_norgate_tiingo_source_separated_batch_dataset(
    *,
    contract_artifact_dir: Path = DEFAULT_CONTRACT_ARTIFACT_DIR,
    cohort_artifact_dir: Path = DEFAULT_COHORT_ARTIFACT_DIR,
    feature_artifact_dir: Path = DEFAULT_FEATURE_ARTIFACT_DIR,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateTiingoSourceSeparatedBatchDataset:
    """Reattest every parent before materializing the Norgate-only rows."""

    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    contract = load_verified_norgate_tiingo_source_separated_contract(
        contract_artifact_dir,
        cohort_artifact_dir=cohort_artifact_dir,
        feature_artifact_dir=feature_artifact_dir,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    cohort = load_verified_tiingo_norgate_source_separation_contract_input(
        cohort_artifact_dir,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    feature = load_verified_norgate_broad_development_feature_artifact(
        feature_artifact_dir,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_batch_lineage(contract, cohort, feature)
    return _dataset_from_verified_parents(contract, cohort, feature)


def run_norgate_tiingo_source_separated_cpu_baseline(
    dataset: NorgateTiingoSourceSeparatedBatchDataset,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path | None = None,
    code_revision: str,
) -> SourceSeparatedCpuBaselineResult:
    """Write the two fixed CPU baselines exactly once."""

    arrays = _validated_arrays(dataset)
    output_dir = _batch_output_dir(artifact_root, repo_root=repo_root)
    summary_path = output_dir / "cpu-baseline.json"
    if summary_path.exists():
        raise FileExistsError(f"source-separated CPU baseline already exists: {summary_path}")

    numpy = _numpy()
    development = arrays["split_ids"] == "development"
    validation = arrays["split_ids"] == "validation"
    means, scales = _fit_standardization(arrays["features"][development])
    standardized = (arrays["features"] - means) / scales
    weights, bias = _fit_regularized_linear(
        standardized[development], arrays["labels"][development]
    )
    baseline_dev = numpy.ones(int(development.sum()), dtype=numpy.float64)
    baseline_validation = numpy.ones(int(validation.sum()), dtype=numpy.float64)
    linear_dev = _sigmoid(standardized[development] @ weights + bias)
    linear_validation = _sigmoid(standardized[validation] @ weights + bias)

    payload = _base_payload(dataset, arrays, code_revision=code_revision, phase="cpu_baseline")
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
        "naive_always_long": {
            "development_diagnostic_only": _date_clustered_metrics(
                arrays["labels"][development],
                baseline_dev,
                arrays["decision_dates"][development],
            ),
            "validation_once": _date_clustered_metrics(
                arrays["labels"][validation],
                baseline_validation,
                arrays["decision_dates"][validation],
            ),
        },
        "regularized_linear": {
            "hyperparameters": {
                "steps": CPU_LINEAR_STEPS,
                "learning_rate": CPU_LINEAR_LEARNING_RATE,
                "l2": CPU_LINEAR_L2,
                "fit_split": "development",
                "row_shuffle": False,
            },
            "weights_sha256": _sha256_array(weights),
            "bias": float(bias),
            "development_diagnostic_only": _date_clustered_metrics(
                arrays["labels"][development],
                linear_dev,
                arrays["decision_dates"][development],
            ),
            "validation_once": _date_clustered_metrics(
                arrays["labels"][validation],
                linear_validation,
                arrays["decision_dates"][validation],
            ),
        },
    }
    validation_metrics = (
        payload["cpu_baselines"]["naive_always_long"]["validation_once"],
        payload["cpu_baselines"]["regularized_linear"]["validation_once"],
    )
    payload["evaluation_policy"] = {
        "validation_evaluation_count_per_predeclared_candidate": 1,
        "validation_replay_or_retune_permitted": False,
        "candidate_selection_eligible": False,
        "validation_metrics_are_engineering_only": True,
    }
    payload["review_required_before_interpretation"] = any(
        item["date_mean_accuracy"] >= STRONG_RESULT_ACCURACY for item in validation_metrics
    )
    _write_json_new(summary_path, payload)
    return SourceSeparatedCpuBaselineResult(
        summary_path=summary_path,
        summary_sha256=_sha256_file(summary_path),
        contract_hash=dataset.contract_hash,
    )


def run_norgate_tiingo_source_separated_cuda_job(
    dataset: NorgateTiingoSourceSeparatedBatchDataset,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    job_id: str,
    repo_root: Path | None = None,
    code_revision: str,
    trainer: CudaTrainer | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> SourceSeparatedCudaJobResult:
    """Run one contract-pinned CUDA MLP job after the immutable CPU baseline."""

    arrays = _validated_arrays(dataset)
    spec = _cuda_job_spec(job_id)
    _validate_contract_cuda_spec(dataset.contract, spec)
    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    output_dir = default_norgate_tiingo_source_separated_batch_dir(artifact_root=root)
    if output_dir.is_symlink() or not output_dir.is_relative_to(root):
        raise ValueError("source-separated CUDA artifact path escapes its root")
    cpu_summary = _read_verified_cpu_summary(output_dir / "cpu-baseline.json", dataset)
    development = arrays["split_ids"] == "development"
    validation = arrays["split_ids"] == "validation"
    means, scales = _fit_standardization(arrays["features"][development])
    expected_standardization_hash = cpu_summary["cpu_baselines"]["development_preprocessing"][
        "sha256"
    ]
    if _sha256_json(
        {
            "means": [float(value) for value in means],
            "scales": [float(value) for value in scales],
        }
    ) != expected_standardization_hash:
        raise ValueError("source-separated CUDA standardization differs from CPU evidence")

    standardized = (arrays["features"] - means) / scales
    selected_trainer = trainer or _train_torch_cuda
    with SourceSeparatedGpuFileLock(_source_separated_cuda_lock_path(root)):
        job_dir = output_dir / "cuda" / spec.job_id
        if job_dir.exists():
            raise FileExistsError(
                f"source-separated CUDA job already has evidence: {spec.job_id}"
            )
        job_dir.mkdir(parents=True, exist_ok=False)
        checkpoint_path = job_dir / "checkpoint.pt"
        prediction_path = job_dir / "validation-predictions.npz"
        summary_path = job_dir / "summary.json"
        failure_path = job_dir / "failure.json"
        try:
            probabilities, trainer_evidence = selected_trainer(
                spec,
                standardized[development],
                arrays["labels"][development],
                standardized[validation],
                checkpoint_path,
                monotonic,
            )
            _validate_cuda_trainer_evidence(trainer_evidence)
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
            review_required = (
                metrics["date_mean_accuracy"] >= STRONG_RESULT_ACCURACY
                or metrics["date_mean_balanced_accuracy"] >= STRONG_RESULT_ACCURACY
            )
            payload = _base_payload(
                dataset, arrays, code_revision=code_revision, phase="cuda_mlp"
            )
            payload["cuda_job"] = {
                "job_id": spec.job_id,
                "model_family": "mlp",
                "hidden_width": spec.hidden_width,
                "seed": spec.seed,
                "contract_pinned": True,
                "selection_eligible": False,
                "ensemble_eligible": False,
                "hyperparameters": {
                    "epochs": spec.epochs,
                    "batch_size": spec.batch_size,
                    "learning_rate": spec.learning_rate,
                    "weight_decay": spec.weight_decay,
                    "row_shuffle": False,
                    "optimizer": "adamw",
                    "deterministic_algorithms": True,
                    "tf32_enabled": False,
                },
                "validation_once": metrics,
                "checkpoint": {
                    "path": str(checkpoint_path.resolve()),
                    "sha256": checkpoint_hash,
                    "safe_weights_only_reload": True,
                },
                "validation_predictions": {
                    "path": str(prediction_path.resolve()),
                    "sha256": prediction_hash,
                    "alignment": "decision_index_then_candidate_rank",
                    "future_ensemble_use": False,
                },
                "trainer": dict(trainer_evidence),
                "review_required_before_interpretation": review_required,
                "stop_rule": (
                    "No retry, tuning, seed expansion, model selection, ensemble, or reuse "
                    "without a new contract."
                ),
            }
            _write_json_new(summary_path, payload)
        except SourceSeparatedCudaJobStopped as exc:
            _remove_if_exists(checkpoint_path)
            _remove_if_exists(prediction_path)
            _write_cuda_failure(
                failure_path,
                dataset=dataset,
                arrays=arrays,
                code_revision=code_revision,
                spec=spec,
                reason=exc.reason,
                elapsed_seconds=exc.elapsed_seconds,
                peak_memory_bytes=exc.peak_memory_bytes,
            )
            raise
        except Exception as exc:
            _remove_if_exists(checkpoint_path)
            _remove_if_exists(prediction_path)
            _write_cuda_failure(
                failure_path,
                dataset=dataset,
                arrays=arrays,
                code_revision=code_revision,
                spec=spec,
                reason=f"unexpected_{type(exc).__name__}",
                elapsed_seconds=None,
                peak_memory_bytes=None,
            )
            raise
        return SourceSeparatedCudaJobResult(
            job_id=spec.job_id,
            summary_path=summary_path,
            summary_sha256=_sha256_file(summary_path),
            checkpoint_path=checkpoint_path,
            checkpoint_sha256=_sha256_file(checkpoint_path),
            prediction_path=prediction_path,
            prediction_sha256=_sha256_file(prediction_path),
            review_required=review_required,
        )


def _validate_batch_lineage(
    contract: NorgateTiingoSourceSeparatedContract,
    cohort: TiingoNorgateSourceSeparationContractInput,
    feature: NorgateBroadDevelopmentFeatureArtifact,
) -> None:
    payload = _mapping(contract.contract, "source-separated batch contract")
    if contract.cohort_manifest_hash != cohort.manifest_hash:
        raise ValueError("source-separated batch cohort manifest is inconsistent")
    if (
        contract.feature_artifact_hash != feature.artifact_hash
        or contract.feature_contract_hash != feature.contract_hash
    ):
        raise ValueError("source-separated batch feature artifact is inconsistent")
    parents = _mapping(payload.get("parents"), "source-separated batch parents")
    cohort_parent = _mapping(parents.get("cohort"), "source-separated batch cohort parent")
    feature_parent = _mapping(
        parents.get("norgate_feature_artifact"), "source-separated batch feature parent"
    )
    if (
        cohort_parent.get("manifest_hash") != cohort.manifest_hash
        or cohort_parent.get("norgate_dataset_hash") != cohort.norgate_dataset_hash
        or cohort_parent.get("norgate_manifest_hash") != cohort.norgate_manifest_hash
        or feature_parent.get("artifact_hash") != feature.artifact_hash
        or feature_parent.get("contract_hash") != feature.contract_hash
        or feature.parent_dataset_hash != cohort.norgate_dataset_hash
        or feature.parent_manifest_hash != cohort.norgate_manifest_hash
    ):
        raise ValueError("source-separated batch parent lineage is inconsistent")
    if payload.get("source_roles") != {
        "norgate": "sole_price_feature_label_source",
        "tiingo": "rank_session_and_returned_marker_mask_only",
        "source_price_mixing": False,
        "forward_only_tiingo_session_use": False,
    }:
        raise ValueError("source-separated batch source roles are invalid")
    if payload.get("scope") != _CONTRACT_SCOPE:
        raise ValueError("source-separated batch contract scope is invalid")
    temporal = _mapping(
        payload.get("temporal_geometry"), "source-separated batch temporal geometry"
    )
    if temporal != {
        "feature_source_index_range": "t-20..t",
        "entry_index": "t+1",
        "exit_index": "t+2",
        "maximum_used_dependency_index": 482,
        "first_forward_only_tiingo_index": 483,
        "forward_only_sessions_used": False,
        "development_decision_index_range": [20, 319],
        "purge_decision_index_range": [320, 321],
        "validation_decision_index_range": [322, 480],
        "purge_observed_sessions": 2,
        "embargo_observed_sessions_for_any_later_fold_or_refit": 2,
        "post_validation_embargo_consumed": False,
    }:
        raise ValueError("source-separated batch temporal geometry is invalid")
    _validate_contract_rank_and_mask(payload, cohort)
    _validate_contract_counts(payload, contract)


def _validate_contract_rank_and_mask(
    payload: Mapping[str, Any], cohort: TiingoNorgateSourceSeparationContractInput
) -> None:
    selection = _mapping(payload.get("rank_selection"), "source-separated batch rank selection")
    pairs = [{"candidate_rank": rank, "symbol": symbol} for rank, symbol in cohort.rank_symbols]
    if (
        selection.get("rule") != "exact_cohort_candidate_rank_and_symbol_pairs"
        or selection.get("rank_count") != len(pairs)
        or selection.get("pairs") != pairs
        or selection.get("pairs_sha256") != _sha256_json(pairs)
    ):
        raise ValueError("source-separated batch rank selection is invalid")
    rows = [
        {
            "candidate_rank": rank,
            "overlap_marker_indices": list(cohort.overlap_marker_indices_by_rank[rank]),
            "forward_only_marker_indices": list(
                cohort.forward_only_marker_indices_by_rank[rank]
            ),
            "excluded_decision_indices": list(cohort.excluded_decision_indices_by_rank[rank]),
        }
        for rank, _symbol in cohort.rank_symbols
    ]
    marker_mask = _mapping(
        payload.get("conservative_marker_mask"), "source-separated batch marker mask"
    )
    if (
        marker_mask.get("per_rank_sha256") != _sha256_json(rows)
        or marker_mask.get("cohort_excluded_pair_count")
        != sum(len(values) for values in cohort.excluded_decision_indices_by_rank.values())
        or marker_mask.get("forward_only_marker_pair_effect") != "none"
    ):
        raise ValueError("source-separated batch marker mask is invalid")


def _validate_contract_counts(
    payload: Mapping[str, Any], contract: NorgateTiingoSourceSeparatedContract
) -> None:
    counts = _mapping(payload.get("sample_counts"), "source-separated batch sample counts")
    expected = {
        "potential_rank_decision_pairs": 13_369,
        "after_tiingo_marker_mask": 10_053,
        "after_existing_norgate_feature_conditioning": 9_904,
        "development": 6_434,
        "purge": 50,
        "validation": 3_420,
    }
    if counts != expected or (
        contract.rank_count,
        contract.retained_feature_row_count,
        contract.development_row_count,
        contract.purge_row_count,
        contract.validation_row_count,
    ) != (29, 9_904, 6_434, 50, 3_420):
        raise ValueError("source-separated batch sample counts are invalid")
    conditioning = _mapping(
        payload.get("norgate_feature_conditioning"), "source-separated batch conditioning"
    )
    if conditioning.get("rows_removed_after_tiingo_marker_mask") != 149:
        raise ValueError("source-separated batch conditioning count is invalid")


def _dataset_from_verified_parents(
    contract: NorgateTiingoSourceSeparatedContract,
    cohort: TiingoNorgateSourceSeparationContractInput,
    feature: NorgateBroadDevelopmentFeatureArtifact,
) -> NorgateTiingoSourceSeparatedBatchDataset:
    numpy = _numpy()
    feature_values = numpy.asarray(feature.feature_array, dtype=numpy.float64)
    labels = numpy.asarray(feature.label_array, dtype=numpy.int8)
    ranks = numpy.asarray(feature.symbol_ranks, dtype=numpy.int64)
    decisions = numpy.asarray(feature.decision_indices, dtype=numpy.int64)
    dates = numpy.asarray(feature.decision_dates).astype("U10")
    source_start = numpy.asarray(feature.source_start_indices, dtype=numpy.int64)
    source_end = numpy.asarray(feature.source_end_indices, dtype=numpy.int64)
    entry = numpy.asarray(feature.entry_indices, dtype=numpy.int64)
    exit = numpy.asarray(feature.exit_indices, dtype=numpy.int64)
    parent_splits = numpy.asarray(feature.split_ids, dtype=numpy.int8)
    if feature_values.shape != (len(labels), FEATURE_WIDTH) or any(
        len(value) != len(labels)
        for value in (ranks, decisions, dates, source_start, source_end, entry, exit, parent_splits)
    ):
        raise ValueError("source-separated feature arrays are misaligned")
    selected_ranks = numpy.asarray([rank for rank, _symbol in cohort.rank_symbols])
    selected = numpy.isin(ranks, selected_ranks)
    for rank, _symbol in cohort.rank_symbols:
        excluded = numpy.asarray(cohort.excluded_decision_indices_by_rank[rank])
        selected &= ~((ranks == rank) & numpy.isin(decisions, excluded))
    if not selected.any():
        raise ValueError("source-separated contract selected no Norgate feature rows")
    arrays = {
        "features": feature_values[selected],
        "labels": labels[selected],
        "decision_indices": decisions[selected],
        "decision_dates": dates[selected],
        "source_start_indices": source_start[selected],
        "source_end_indices": source_end[selected],
        "entry_indices": entry[selected],
        "exit_indices": exit[selected],
        "symbol_ranks": ranks[selected],
        "parent_splits": parent_splits[selected],
    }
    split_ids = numpy.empty(len(arrays["labels"]), dtype="U16")
    split_ids[numpy.isin(arrays["decision_indices"], tuple(_DEVELOPMENT))] = "development"
    split_ids[numpy.isin(arrays["decision_indices"], tuple(_PURGE))] = "purge"
    split_ids[numpy.isin(arrays["decision_indices"], tuple(_VALIDATION))] = "validation"
    arrays["split_ids"] = split_ids
    _validate_selected_arrays(arrays, cohort, contract.contract)
    selected_slice = [
        {
            "candidate_rank": int(rank),
            "decision_date": str(decision_date),
            "decision_index": int(decision_index),
        }
        for rank, decision_date, decision_index in zip(
            arrays["symbol_ranks"],
            arrays["decision_dates"],
            arrays["decision_indices"],
            strict=True,
        )
    ]
    retention = _norgate_retention(feature)
    counts = _mapping(contract.contract["sample_counts"], "source-separated batch counts")
    return NorgateTiingoSourceSeparatedBatchDataset(
        contract_dir=contract.artifact_dir,
        contract_hash=contract.contract_hash,
        cohort_manifest_hash=contract.cohort_manifest_hash,
        feature_artifact_hash=contract.feature_artifact_hash,
        feature_contract_hash=contract.feature_contract_hash,
        selected_slice_sha256=_sha256_json(selected_slice),
        features=arrays["features"],
        labels=arrays["labels"],
        decision_indices=arrays["decision_indices"],
        decision_dates=arrays["decision_dates"],
        source_start_indices=arrays["source_start_indices"],
        source_end_indices=arrays["source_end_indices"],
        entry_indices=arrays["entry_indices"],
        exit_indices=arrays["exit_indices"],
        symbol_ranks=arrays["symbol_ranks"],
        split_ids=arrays["split_ids"],
        rank_symbols=cohort.rank_symbols,
        sample_counts=MappingProxyType(
            {key: int(value) for key, value in counts.items()}
        ),
        norgate_retention=MappingProxyType(retention),
        contract=MappingProxyType(dict(contract.contract)),
    )


def _norgate_retention(feature: NorgateBroadDevelopmentFeatureArtifact) -> dict[str, Any]:
    retention = _mapping(feature.contract.get("retention"), "Norgate feature retention")
    if (
        retention.get("norgate_origin_data") is not True
        or retention.get("parent_deletion_requires_derived_deletion") is not True
        or retention.get("automated_deletion") is not False
        or not isinstance(retention.get("marker_file"), str)
        or not retention["marker_file"]
    ):
        raise ValueError("Norgate feature retention is invalid")
    return dict(retention)


def _validate_selected_arrays(
    arrays: Mapping[str, Any],
    cohort: TiingoNorgateSourceSeparationContractInput,
    contract: Mapping[str, Any],
) -> None:
    numpy = _numpy()
    count = len(arrays["labels"])
    if (
        count != 9_904
        or arrays["features"].shape != (count, FEATURE_WIDTH)
        or any(len(value) != count for key, value in arrays.items() if key != "features")
        or not numpy.isfinite(arrays["features"]).all()
        or not numpy.isin(arrays["labels"], (0, 1)).all()
    ):
        raise ValueError("source-separated selected arrays are invalid")
    if not (
        (arrays["source_start_indices"] == arrays["decision_indices"] - FEATURE_WIDTH)
        & (arrays["source_end_indices"] == arrays["decision_indices"])
        & (arrays["entry_indices"] == arrays["decision_indices"] + 1)
        & (arrays["exit_indices"] == arrays["decision_indices"] + 2)
    ).all():
        raise ValueError("source-separated selected timing is invalid")
    if (
        (arrays["decision_indices"] < 20).any()
        or (arrays["decision_indices"] > 480).any()
        or int(arrays["exit_indices"].max()) != 482
        or int(arrays["exit_indices"].max()) >= len(cohort.overlap_session_dates)
    ):
        raise ValueError("source-separated selected rows use a forward-only session")
    expected_dates = numpy.asarray(cohort.overlap_session_dates, dtype="U10")[
        arrays["decision_indices"]
    ]
    if not numpy.array_equal(arrays["decision_dates"], expected_dates):
        raise ValueError("source-separated selected decision dates are inconsistent")
    expected_order = numpy.lexsort((arrays["symbol_ranks"], arrays["decision_indices"]))
    if not numpy.array_equal(expected_order, numpy.arange(count)):
        raise ValueError("source-separated selected rows are not canonical")
    expected_splits = numpy.select(
        [
            numpy.isin(arrays["decision_indices"], tuple(_DEVELOPMENT)),
            numpy.isin(arrays["decision_indices"], tuple(_PURGE)),
            numpy.isin(arrays["decision_indices"], tuple(_VALIDATION)),
        ],
        ["development", "purge", "validation"],
        default="invalid",
    )
    if not numpy.array_equal(arrays["split_ids"], expected_splits):
        raise ValueError("source-separated selected split is invalid")
    expected_parent_codes = numpy.select(
        [arrays["split_ids"] == "development", arrays["split_ids"] == "purge"],
        [0, 1],
        default=2,
    )
    if not numpy.array_equal(arrays["parent_splits"], expected_parent_codes):
        raise ValueError("source-separated selected parent split is invalid")
    observed_counts = {
        split: int((arrays["split_ids"] == split).sum())
        for split in ("development", "purge", "validation")
    }
    if observed_counts != {
        "development": 6_434,
        "purge": 50,
        "validation": 3_420,
    }:
        raise ValueError("source-separated selected split counts are invalid")
    for rank, _symbol in cohort.rank_symbols:
        selected_decisions = arrays["decision_indices"][arrays["symbol_ranks"] == rank]
        if len(selected_decisions) == 0 or numpy.isin(
            selected_decisions,
            numpy.asarray(cohort.excluded_decision_indices_by_rank[rank]),
        ).any():
            raise ValueError("source-separated marker mask was not preserved")
    if _mapping(contract.get("sample_counts"), "counts") != {
        "potential_rank_decision_pairs": 13_369,
        "after_tiingo_marker_mask": 10_053,
        "after_existing_norgate_feature_conditioning": 9_904,
        "development": 6_434,
        "purge": 50,
        "validation": 3_420,
    }:
        raise ValueError("source-separated contract counts changed")


def _validated_arrays(dataset: NorgateTiingoSourceSeparatedBatchDataset) -> dict[str, Any]:
    if not isinstance(dataset, NorgateTiingoSourceSeparatedBatchDataset):
        raise TypeError("source-separated batch requires a verified Norgate-only dataset")
    for value, label in (
        (dataset.contract_hash, "contract hash"),
        (dataset.cohort_manifest_hash, "cohort manifest hash"),
        (dataset.feature_artifact_hash, "feature artifact hash"),
        (dataset.feature_contract_hash, "feature contract hash"),
        (dataset.selected_slice_sha256, "selected slice hash"),
    ):
        _require_sha256(value, label)
    _validate_dataset_contract(dataset)
    numpy = _numpy()
    arrays = {
        "features": numpy.asarray(dataset.features, dtype=numpy.float64),
        "labels": numpy.asarray(dataset.labels, dtype=numpy.int8),
        "decision_indices": numpy.asarray(dataset.decision_indices, dtype=numpy.int64),
        "decision_dates": numpy.asarray(dataset.decision_dates).astype("U10"),
        "source_start_indices": numpy.asarray(dataset.source_start_indices, dtype=numpy.int64),
        "source_end_indices": numpy.asarray(dataset.source_end_indices, dtype=numpy.int64),
        "entry_indices": numpy.asarray(dataset.entry_indices, dtype=numpy.int64),
        "exit_indices": numpy.asarray(dataset.exit_indices, dtype=numpy.int64),
        "symbol_ranks": numpy.asarray(dataset.symbol_ranks, dtype=numpy.int64),
        "split_ids": numpy.asarray(dataset.split_ids).astype("U16"),
    }
    _validate_dataset_arrays(arrays, rank_symbols=dataset.rank_symbols)
    return arrays


def _validate_dataset_contract(dataset: NorgateTiingoSourceSeparatedBatchDataset) -> None:
    contract = _mapping(dataset.contract, "source-separated batch dataset contract")
    expected_counts = {
        "potential_rank_decision_pairs": 13_369,
        "after_tiingo_marker_mask": 10_053,
        "after_existing_norgate_feature_conditioning": 9_904,
        "development": 6_434,
        "purge": 50,
        "validation": 3_420,
    }
    pairs = [
        {"candidate_rank": int(rank), "symbol": str(symbol)}
        for rank, symbol in dataset.rank_symbols
    ]
    if (
        len(pairs) != 29
        or len({item["candidate_rank"] for item in pairs}) != 29
        or any(not item["symbol"] for item in pairs)
        or contract.get("scope") != _CONTRACT_SCOPE
        or contract.get("source_roles")
        != {
            "norgate": "sole_price_feature_label_source",
            "tiingo": "rank_session_and_returned_marker_mask_only",
            "source_price_mixing": False,
            "forward_only_tiingo_session_use": False,
        }
        or _mapping(contract.get("sample_counts"), "source-separated dataset counts")
        != expected_counts
        or dict(dataset.sample_counts) != expected_counts
    ):
        raise ValueError("source-separated batch dataset contract is invalid")
    selection = _mapping(contract.get("rank_selection"), "source-separated dataset ranks")
    if (
        selection.get("rule") != "exact_cohort_candidate_rank_and_symbol_pairs"
        or selection.get("rank_count") != len(pairs)
        or selection.get("pairs") != pairs
        or selection.get("pairs_sha256") != _sha256_json(pairs)
    ):
        raise ValueError("source-separated batch dataset roster is invalid")
    temporal = _mapping(contract.get("temporal_geometry"), "source-separated dataset timing")
    if temporal != {
        "feature_source_index_range": "t-20..t",
        "entry_index": "t+1",
        "exit_index": "t+2",
        "maximum_used_dependency_index": 482,
        "first_forward_only_tiingo_index": 483,
        "forward_only_sessions_used": False,
        "development_decision_index_range": [20, 319],
        "purge_decision_index_range": [320, 321],
        "validation_decision_index_range": [322, 480],
        "purge_observed_sessions": 2,
        "embargo_observed_sessions_for_any_later_fold_or_refit": 2,
        "post_validation_embargo_consumed": False,
    }:
        raise ValueError("source-separated batch dataset timing is invalid")
    _validate_contract_cuda_spec(contract, CUDA_JOB_SPECS[0])
    _validate_contract_cuda_spec(contract, CUDA_JOB_SPECS[1])


def _validate_dataset_arrays(
    arrays: Mapping[str, Any], *, rank_symbols: tuple[tuple[int, str], ...]
) -> None:
    numpy = _numpy()
    count = len(arrays["labels"])
    if (
        count != 9_904
        or arrays["features"].shape != (count, FEATURE_WIDTH)
        or any(len(value) != count for key, value in arrays.items() if key != "features")
        or not numpy.isfinite(arrays["features"]).all()
        or not numpy.isin(arrays["labels"], (0, 1)).all()
    ):
        raise ValueError("source-separated batch arrays are invalid")
    if not (
        (arrays["source_start_indices"] == arrays["decision_indices"] - FEATURE_WIDTH)
        & (arrays["source_end_indices"] == arrays["decision_indices"])
        & (arrays["entry_indices"] == arrays["decision_indices"] + 1)
        & (arrays["exit_indices"] == arrays["decision_indices"] + 2)
    ).all():
        raise ValueError("source-separated batch timing is invalid")
    split_counts = {
        split: int((arrays["split_ids"] == split).sum())
        for split in ("development", "purge", "validation")
    }
    if split_counts != {"development": 6_434, "purge": 50, "validation": 3_420}:
        raise ValueError("source-separated batch split counts are invalid")
    if (arrays["split_ids"] == "purge").sum() != 50:
        raise ValueError("source-separated batch purge must remain visible")
    expected_splits = numpy.select(
        [
            numpy.isin(arrays["decision_indices"], tuple(_DEVELOPMENT)),
            numpy.isin(arrays["decision_indices"], tuple(_PURGE)),
            numpy.isin(arrays["decision_indices"], tuple(_VALIDATION)),
        ],
        ["development", "purge", "validation"],
        default="invalid",
    )
    if not numpy.array_equal(arrays["split_ids"], expected_splits):
        raise ValueError("source-separated batch split timing is invalid")
    if (
        (arrays["decision_indices"] < 20).any()
        or (arrays["decision_indices"] > 480).any()
        or int(arrays["exit_indices"].max()) != 482
        or (arrays["exit_indices"] >= 483).any()
    ):
        raise ValueError("source-separated batch uses a forward-only session")
    expected_ranks = {int(rank) for rank, _symbol in rank_symbols}
    if set(int(value) for value in arrays["symbol_ranks"]) != expected_ranks:
        raise ValueError("source-separated batch rank roster is invalid")
    pairs = numpy.column_stack((arrays["decision_indices"], arrays["symbol_ranks"]))
    if len(numpy.unique(pairs, axis=0)) != count:
        raise ValueError("source-separated batch has duplicate rank/decision rows")
    expected_order = numpy.lexsort((arrays["symbol_ranks"], arrays["decision_indices"]))
    if not numpy.array_equal(expected_order, numpy.arange(count)):
        raise ValueError("source-separated batch rows are not canonical")


def _validate_contract_cuda_spec(
    contract: Mapping[str, Any], spec: SourceSeparatedCudaJobSpec
) -> None:
    future_batch = _mapping(contract.get("future_batch"), "source-separated future batch")
    if (
        future_batch.get("cpu_baselines") != ["naive_always_long", "regularized_linear"]
        or future_batch.get("cuda_max_concurrent_jobs") != 1
        or future_batch.get("cuda_per_job_wall_clock_cap_seconds") != CUDA_WALL_CLOCK_CAP_SECONDS
        or future_batch.get("cuda_per_job_vram_cap_mib") != CUDA_VRAM_CAP_MIB
        or future_batch.get("no_candidate_ranking_or_promotion") is not True
    ):
        raise ValueError("source-separated CUDA budget is invalid")
    candidates = future_batch.get("cuda_candidates")
    if not isinstance(candidates, list):
        raise ValueError("source-separated CUDA candidates are invalid")
    expected = {
        "id": spec.job_id,
        "family": "mlp",
        "hidden_width": spec.hidden_width,
        "seed": spec.seed,
        "epochs": spec.epochs,
        "batch_size": spec.batch_size,
    }
    if candidates.count(expected) != 1:
        raise ValueError("source-separated CUDA job is not contract-pinned")


def _cuda_job_spec(job_id: str) -> SourceSeparatedCudaJobSpec:
    for spec in CUDA_JOB_SPECS:
        if spec.job_id == job_id:
            return spec
    raise ValueError("source-separated CUDA job is not in the fixed batch")


def _train_torch_cuda(
    spec: SourceSeparatedCudaJobSpec,
    development_features: Any,
    development_labels: Any,
    validation_features: Any,
    checkpoint_path: Path,
    monotonic: Callable[[], float],
) -> tuple[Any, Mapping[str, Any]]:
    workspace_config = _require_cuda_determinism_workspace()
    import torch

    if not torch.cuda.is_available():
        raise SourceSeparatedCudaJobStopped("cuda_unavailable")
    device = torch.device("cuda:0")
    properties = torch.cuda.get_device_properties(device)
    cap_bytes = CUDA_VRAM_CAP_MIB * 1024 * 1024
    if cap_bytes > properties.total_memory:
        raise SourceSeparatedCudaJobStopped("vram_cap_exceeds_device_memory")
    start = monotonic()
    torch.manual_seed(spec.seed)
    torch.cuda.manual_seed_all(spec.seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.cuda.set_per_process_memory_fraction(cap_bytes / properties.total_memory, device)
    torch.cuda.reset_peak_memory_stats(device)
    try:
        with _cuda_wall_clock_alarm(torch, device, start, monotonic) as hard_timer_enforced:
            train_x = torch.tensor(development_features, dtype=torch.float32, device=device)
            train_y = torch.tensor(
                development_labels, dtype=torch.float32, device=device
            ).view(-1, 1)
            validation_x = torch.tensor(validation_features, dtype=torch.float32, device=device)
            model = _build_torch_model(spec, torch).to(device)
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=spec.learning_rate, weight_decay=spec.weight_decay
            )
            loss_fn = torch.nn.BCEWithLogitsLoss()
            last_loss: Any | None = None
            for _epoch in range(spec.epochs):
                for start_index in range(0, len(train_x), spec.batch_size):
                    end_index = min(start_index + spec.batch_size, len(train_x))
                    logits = model(train_x[start_index:end_index])
                    loss = loss_fn(logits, train_y[start_index:end_index])
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                    last_loss = loss.detach()
                    _enforce_cuda_caps(torch, device, start, monotonic, cap_bytes)
            if last_loss is None:
                raise ValueError("source-separated CUDA training received no development batches")
            model.eval()
            with torch.no_grad():
                probabilities = torch.sigmoid(model(validation_x)).view(-1).cpu().numpy()
            elapsed, peak = _enforce_cuda_caps(torch, device, start, monotonic, cap_bytes)
            payload = {
                "schema_version": 1,
                "kind": "norgate_tiingo_source_separated_cuda_checkpoint",
                "job_id": spec.job_id,
                "hidden_width": spec.hidden_width,
                "seed": spec.seed,
                "state_dict": model.state_dict(),
            }
            with checkpoint_path.open("xb") as handle:
                torch.save(payload, handle)
            _verify_torch_checkpoint(spec, checkpoint_path, torch)
            elapsed, peak = _enforce_cuda_caps(torch, device, start, monotonic, cap_bytes)
    except torch.cuda.OutOfMemoryError as exc:
        elapsed, peak = _cuda_usage(torch, device, start, monotonic)
        raise SourceSeparatedCudaJobStopped(
            "cuda_out_of_memory", elapsed_seconds=elapsed, peak_memory_bytes=peak
        ) from exc
    return probabilities, {
        "backend": "torch_cuda",
        "device": torch.cuda.get_device_name(device),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "epochs": spec.epochs,
        "examples": int(len(train_x)),
        "final_batch_loss": f"{float(last_loss.item()):.8f}",
        "elapsed_seconds": elapsed,
        "peak_memory_bytes": peak,
        "vram_cap_bytes": cap_bytes,
        "vram_cap_enforcement": "torch_allocator_fraction_and_peak_accounting",
        "vram_cap_is_physical_partition": False,
        "wall_clock_cap_seconds": CUDA_WALL_CLOCK_CAP_SECONDS,
        "wall_clock_hard_timer_enforced": hard_timer_enforced,
        "wall_clock_enforcement": "unix_itimer_plus_monotonic_batch_checks",
        "cublas_workspace_config": workspace_config,
        "safe_weights_only_reload": True,
    }


def _build_torch_model(spec: SourceSeparatedCudaJobSpec, torch: Any) -> Any:
    return torch.nn.Sequential(
        torch.nn.Linear(FEATURE_WIDTH, spec.hidden_width),
        torch.nn.ReLU(),
        torch.nn.Linear(spec.hidden_width, 1),
    )


def _require_cuda_determinism_workspace() -> str:
    configured = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if configured != CUDA_CUBLAS_WORKSPACE_CONFIG:
        raise SourceSeparatedCudaJobStopped("cuda_determinism_workspace_unconfigured")
    return configured


def _enforce_cuda_caps(
    torch: Any,
    device: Any,
    start: float,
    monotonic: Callable[[], float],
    cap_bytes: int,
) -> tuple[float, int]:
    torch.cuda.synchronize(device)
    elapsed, peak = _cuda_usage(torch, device, start, monotonic)
    if elapsed > CUDA_WALL_CLOCK_CAP_SECONDS:
        raise SourceSeparatedCudaJobStopped(
            "wall_clock_cap_exceeded", elapsed_seconds=elapsed, peak_memory_bytes=peak
        )
    if peak > cap_bytes:
        raise SourceSeparatedCudaJobStopped(
            "vram_cap_exceeded", elapsed_seconds=elapsed, peak_memory_bytes=peak
        )
    return elapsed, peak


@contextmanager
def _cuda_wall_clock_alarm(
    torch: Any, device: Any, start: float, monotonic: Callable[[], float]
) -> Iterator[bool]:
    """Apply a Docker/Linux hard wall-clock interrupt in addition to batch checks."""

    if os.name == "nt" or not hasattr(signal, "SIGALRM") or not hasattr(signal, "setitimer"):
        yield False
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0.0)

    def _timeout(_signal_number: int, _frame: object) -> None:
        elapsed, peak = _cuda_usage(torch, device, start, monotonic)
        raise SourceSeparatedCudaJobStopped(
            "wall_clock_cap_exceeded", elapsed_seconds=elapsed, peak_memory_bytes=peak
        )

    signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, CUDA_WALL_CLOCK_CAP_SECONDS)
    try:
        yield True
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _cuda_usage(
    torch: Any, device: Any, start: float, monotonic: Callable[[], float]
) -> tuple[float, int]:
    elapsed = max(0.0, float(monotonic() - start))
    peak = max(
        int(torch.cuda.max_memory_allocated(device)),
        int(torch.cuda.max_memory_reserved(device)),
    )
    return elapsed, peak


def _verify_torch_checkpoint(
    spec: SourceSeparatedCudaJobSpec, checkpoint_path: Path, torch: Any
) -> None:
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover - torch-specific failure path.
        raise ValueError("source-separated CUDA checkpoint cannot be safely reloaded") from exc
    if not isinstance(payload, dict) or (
        payload.get("kind") != "norgate_tiingo_source_separated_cuda_checkpoint"
        or payload.get("job_id") != spec.job_id
        or payload.get("hidden_width") != spec.hidden_width
        or payload.get("seed") != spec.seed
    ):
        raise ValueError("source-separated CUDA checkpoint contract is invalid")
    model = _build_torch_model(spec, torch)
    try:
        model.load_state_dict(payload["state_dict"], strict=True)
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("source-separated CUDA checkpoint state is incompatible") from exc


def _validate_cuda_trainer_evidence(evidence: Mapping[str, Any]) -> None:
    if (
        evidence.get("backend") != "torch_cuda"
        or evidence.get("safe_weights_only_reload") is not True
        or not isinstance(evidence.get("elapsed_seconds"), (int, float))
        or evidence["elapsed_seconds"] < 0
        or evidence["elapsed_seconds"] > CUDA_WALL_CLOCK_CAP_SECONDS
        or not isinstance(evidence.get("peak_memory_bytes"), int)
        or evidence["peak_memory_bytes"] < 0
        or evidence["peak_memory_bytes"] > CUDA_VRAM_CAP_MIB * 1024 * 1024
        or evidence.get("vram_cap_bytes") != CUDA_VRAM_CAP_MIB * 1024 * 1024
        or evidence.get("vram_cap_enforcement")
        != "torch_allocator_fraction_and_peak_accounting"
        or evidence.get("vram_cap_is_physical_partition") is not False
        or evidence.get("wall_clock_cap_seconds") != CUDA_WALL_CLOCK_CAP_SECONDS
        or evidence.get("wall_clock_hard_timer_enforced") is not True
        or evidence.get("wall_clock_enforcement")
        != "unix_itimer_plus_monotonic_batch_checks"
        or evidence.get("cublas_workspace_config") != CUDA_CUBLAS_WORKSPACE_CONFIG
    ):
        raise ValueError("source-separated CUDA trainer evidence is invalid")


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
        raise ValueError("source-separated CUDA validation probabilities are invalid")
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
                raise ValueError("source-separated CUDA prediction arrays are invalid")
            for name, expected in payload.items():
                if not numpy.array_equal(archive[name], expected):
                    raise ValueError("source-separated CUDA prediction data is invalid")
    except (OSError, ValueError) as exc:
        raise ValueError("source-separated CUDA predictions cannot be safely reloaded") from exc
    with path.open("xb") as handle:
        handle.write(data)
    return _sha256_file(path)


def _base_payload(
    dataset: NorgateTiingoSourceSeparatedBatchDataset,
    arrays: Mapping[str, Any],
    *,
    code_revision: str,
    phase: Literal["cpu_baseline", "cuda_mlp", "cuda_failure"],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "norgate_tiingo_source_separated_engineering_batch",
        "batch_version": BATCH_VERSION,
        "phase": phase,
        "code_revision": _nonempty_text(code_revision, "code_revision"),
        "scope": dict(_RESULT_SCOPE),
        "lineage": {
            "contract_dir": str(dataset.contract_dir.resolve()),
            "contract_hash": dataset.contract_hash,
            "cohort_manifest_hash": dataset.cohort_manifest_hash,
            "feature_artifact_hash": dataset.feature_artifact_hash,
            "feature_contract_hash": dataset.feature_contract_hash,
            "selected_slice_sha256": dataset.selected_slice_sha256,
            "norgate_is_sole_price_feature_label_source": True,
            "tiingo_raw_data_loaded": False,
            "tiingo_forward_only_sessions_used": False,
        },
        "feature_and_target_timing": {
            "feature_source_index_range": "t-20..t",
            "entry_index": "t+1",
            "label_exit_index": "t+2",
            "combined_static_conditioning_window": "t-20..t+2",
            "maximum_used_dependency_index": 482,
            "first_forward_only_tiingo_index": 483,
        },
        "temporal_split": {
            "fit_decision_indices": [20, 319],
            "purge_decision_indices": [320, 321],
            "purge_used_for_fit": False,
            "purge_used_for_evaluation": False,
            "validation_decision_indices": [322, 480],
            "validation_used_for_fixed_engineering_evaluation_only": True,
            "development_label_exit_max_index": 321,
            "validation_decision_start_index": 322,
        },
        "sample_counts": {
            split: int((arrays["split_ids"] == split).sum())
            for split in ("development", "purge", "validation")
        },
        "attestations": {
            "offline": True,
            "network_access": False,
            "credential_access": False,
            "broker_access": False,
            "local_paper_execution": False,
            "artifact_outside_git": True,
        },
        "retention": dict(dataset.norgate_retention),
        "limitations": list(_LIMITATIONS),
    }


def _write_cuda_failure(
    path: Path,
    *,
    dataset: NorgateTiingoSourceSeparatedBatchDataset,
    arrays: Mapping[str, Any],
    code_revision: str,
    spec: SourceSeparatedCudaJobSpec,
    reason: str,
    elapsed_seconds: float | None,
    peak_memory_bytes: int | None,
) -> None:
    payload = _base_payload(dataset, arrays, code_revision=code_revision, phase="cuda_failure")
    payload["cuda_failure"] = {
        "job_id": spec.job_id,
        "reason": _nonempty_text(reason, "CUDA failure reason"),
        "automatic_retry_permitted": False,
        "wall_clock_cap_seconds": CUDA_WALL_CLOCK_CAP_SECONDS,
        "vram_cap_bytes": CUDA_VRAM_CAP_MIB * 1024 * 1024,
        "elapsed_seconds": elapsed_seconds,
        "peak_memory_bytes": peak_memory_bytes,
    }
    _write_json_new(path, payload)


def _read_verified_cpu_summary(
    path: Path, dataset: NorgateTiingoSourceSeparatedBatchDataset
) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("source-separated CUDA requires the immutable CPU baseline")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("source-separated CPU baseline is malformed") from exc
    if not isinstance(payload, dict) or (
        payload.get("batch_version") != BATCH_VERSION
        or payload.get("phase") != "cpu_baseline"
        or payload.get("scope") != _RESULT_SCOPE
        or payload.get("lineage", {}).get("contract_hash") != dataset.contract_hash
        or payload.get("lineage", {}).get("feature_artifact_hash") != dataset.feature_artifact_hash
        or payload.get("evaluation_policy", {}).get("candidate_selection_eligible") is not False
        or payload.get("evaluation_policy", {}).get("validation_replay_or_retune_permitted")
        is not False
        or not isinstance(payload.get("cpu_baselines"), dict)
    ):
        raise ValueError("source-separated CPU baseline does not match the fixed batch")
    standardization = payload["cpu_baselines"].get("development_preprocessing")
    if not isinstance(standardization, dict) or not isinstance(standardization.get("sha256"), str):
        raise ValueError("source-separated CPU preprocessing evidence is invalid")
    return payload


def _fit_standardization(features: Any) -> tuple[Any, Any]:
    numpy = _numpy()
    means = features.mean(axis=0)
    scales = features.std(axis=0)
    scales = numpy.where(scales > 1e-12, scales, 1.0)
    if not numpy.isfinite(means).all() or not numpy.isfinite(scales).all():
        raise ValueError("source-separated development standardization is invalid")
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
        raise ValueError("source-separated regularized linear training diverged")
    return weights, bias


def _date_clustered_metrics(labels: Any, probabilities: Any, decision_dates: Any) -> dict[str, Any]:
    numpy = _numpy()
    labels = numpy.asarray(labels, dtype=numpy.int8)
    probabilities = numpy.asarray(probabilities, dtype=numpy.float64)
    dates = numpy.asarray(decision_dates).astype("U10")
    if len(labels) == 0 or len(probabilities) != len(labels):
        raise ValueError("source-separated metrics require matching nonempty arrays")
    if not numpy.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("source-separated probabilities are invalid")
    predictions = (probabilities >= 0.5).astype(numpy.int8)
    unique_dates, inverse = numpy.unique(dates, return_inverse=True)
    date_accuracy = numpy.empty(len(unique_dates), dtype=numpy.float64)
    date_balanced_accuracy = numpy.empty(len(unique_dates), dtype=numpy.float64)
    date_brier = numpy.empty(len(unique_dates), dtype=numpy.float64)
    date_log_loss = numpy.empty(len(unique_dates), dtype=numpy.float64)
    for index in range(len(unique_dates)):
        selected = inverse == index
        labels_for_date = labels[selected]
        predictions_for_date = predictions[selected]
        probabilities_for_date = probabilities[selected]
        date_accuracy[index] = float((predictions_for_date == labels_for_date).mean())
        recalls: list[float] = []
        positives = labels_for_date == 1
        negatives = ~positives
        if positives.any():
            recalls.append(float((predictions_for_date[positives] == 1).mean()))
        if negatives.any():
            recalls.append(float((predictions_for_date[negatives] == 0).mean()))
        date_balanced_accuracy[index] = float(sum(recalls) / len(recalls))
        date_brier[index] = float(((probabilities_for_date - labels_for_date) ** 2).mean())
        clipped = numpy.clip(probabilities_for_date, 1e-7, 1 - 1e-7)
        date_log_loss[index] = float(
            -(
                labels_for_date * numpy.log(clipped)
                + (1 - labels_for_date) * numpy.log(1 - clipped)
            ).mean()
        )
    return {
        "row_count_descriptive_only": int(len(labels)),
        "date_group_count": int(len(unique_dates)),
        "date_mean_accuracy": float(date_accuracy.mean()),
        "date_mean_balanced_accuracy": float(date_balanced_accuracy.mean()),
        "date_mean_brier": float(date_brier.mean()),
        "date_mean_log_loss": float(date_log_loss.mean()),
        "positive_label_rate": float(labels.mean()),
        "mean_predicted_probability": float(probabilities.mean()),
        "iid_claim": False,
    }


def _batch_output_dir(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    output = default_norgate_tiingo_source_separated_batch_dir(artifact_root=root)
    if output.is_symlink() or not output.is_relative_to(root):
        raise ValueError("source-separated batch artifact path escapes its root")
    return output


def _source_separated_cuda_lock_path(artifact_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    path = root / "_control" / "locks" / "norgate-tii-source-separated-cuda.lock"
    if not path.is_relative_to(root):
        raise ValueError("source-separated CUDA lock path escapes its artifact root")
    return path


def _validate_artifact_root(value: Path, *, repo_root: Path | None) -> Path:
    root = Path(value)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("source-separated batch artifact root must be an existing directory")
    root = root.resolve()
    repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repo.is_dir() or repo.is_symlink():
        raise ValueError("source-separated batch repository root is invalid")
    repo = repo.resolve()
    docker_mount = (
        os.name != "nt"
        and repo == Path("/app").resolve()
        and root.is_relative_to(Path("/app/model_artifacts").resolve())
    )
    if root.is_relative_to(repo) and not docker_mount:
        raise ValueError("source-separated batch artifacts must stay outside the Git workspace")
    return root


def _write_json_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} is invalid")
    return value


def _require_sha256(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} is invalid")


def _nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is invalid")
    return value.strip()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_array(value: Any) -> str:
    return "sha256:" + hashlib.sha256(value.tobytes()).hexdigest()


def _sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()


def _sigmoid(values: Any) -> Any:
    numpy = _numpy()
    return 1.0 / (1.0 + numpy.exp(-numpy.clip(values, -40.0, 40.0)))


def _numpy() -> Any:
    import numpy

    return numpy

"""Candidate-only QQQ/SPY D1 classification screen for one reattested fold.

This module deliberately stops before replay, selection, or any execution
surface.  It receives already-verified in-memory materialization adapters,
keeps rows and targets in process memory, and writes only source-safe aggregate
classification evidence under the external model-artifact root.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from thericher_v2.kis_daily_joint_event_d1_materializer import KisDailyJointEventD1Materializer
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KisDailyJointEventD1TargetCostAdapter,
)
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    is_container_external_mount,
)

KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_SCHEMA_VERSION = 1
KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID = "kis-daily-joint-event-d1-sequence-screen-v1"
KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_KIND = "kis_daily_joint_event_d1_sequence_screen"
KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_FEATURE_NAMES = (
    "qqq_completed_close_return",
    "spy_completed_close_return",
    "qqq_minus_spy_completed_close_return",
)
KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH = 20
KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT = 3
KIS_DAILY_JOINT_EVENT_D1_TOTAL_SESSION_COUNT = 4756
KIS_DAILY_JOINT_EVENT_D1_UNTOUCHED_TAIL_SESSION_COUNT = 151
KIS_DAILY_JOINT_EVENT_D1_SCORE_THRESHOLD = 0.5
KIS_DAILY_JOINT_EVENT_D1_CPU_EPOCHS = 2
KIS_DAILY_JOINT_EVENT_D1_CUDA_EPOCHS = 12
KIS_DAILY_JOINT_EVENT_D1_CPU_MAX_SECONDS = 90
KIS_DAILY_JOINT_EVENT_D1_CUDA_MAX_SECONDS = 180

CandidateScreenMode = Literal["cpu-smoke", "cuda-screen"]
CandidateModelId = Literal["linear", "compact_gru"]
MaterializationPhase = Literal["development", "validation"]
ScreenFoldId = Literal["expanding-1", "expanding-2", "expanding-3"]
SequenceRow = tuple[float, float, float]
SequenceFeatures = tuple[SequenceRow, ...]

KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_FOLD_IDS: tuple[ScreenFoldId, ...] = (
    "expanding-1",
    "expanding-2",
    "expanding-3",
)


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1SequenceScreenFoldSpec:
    """One explicit, independent sparse-fold contract for this screen."""

    fold_id: ScreenFoldId
    development_decision_count: int
    validation_decision_count: int

    def __post_init__(self) -> None:
        if (
            self.fold_id not in KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_FOLD_IDS
            or type(self.development_decision_count) is not int
            or type(self.validation_decision_count) is not int
            or self.development_decision_count <= 0
            or self.validation_decision_count <= 0
        ):
            raise ValueError("joint D1 sequence screen fold spec is invalid")


KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_FOLD_SPECS = {
    "expanding-1": KisDailyJointEventD1SequenceScreenFoldSpec(
        fold_id="expanding-1",
        development_decision_count=2345,
        validation_decision_count=146,
    ),
    "expanding-2": KisDailyJointEventD1SequenceScreenFoldSpec(
        fold_id="expanding-2",
        development_decision_count=2511,
        validation_decision_count=128,
    ),
    "expanding-3": KisDailyJointEventD1SequenceScreenFoldSpec(
        fold_id="expanding-3",
        development_decision_count=2671,
        validation_decision_count=145,
    ),
}

_ALLOWED_ARTIFACT_KEYS = frozenset(
    {
        "accuracy",
        "artifact_policy",
        "backend",
        "candidate_id",
        "candidate_only",
        "candidate_selection_eligible",
        "candidates",
        "classification",
        "classification_only",
        "column_count",
        "credentials_persisted",
        "development_decision_count",
        "device",
        "ensemble_eligible",
        "epochs",
        "evaluated_count",
        "false_negative_count",
        "false_positive_count",
        "family",
        "feature_values_persisted",
        "failure_class",
        "fit_scope",
        "fold_id",
        "fold_input_identity",
        "f1",
        "hidden_size",
        "immutable_write_only",
        "kind",
        "materializer_identity",
        "metrics",
        "mode",
        "model_execution_eligible",
        "normalization",
        "normalization_identity",
        "observed_positive_count",
        "offline_only",
        "paper_decision_eligible",
        "per_decision_outputs_persisted",
        "precision",
        "pre_validation_gap_consumed",
        "precommit",
        "precommit_identity",
        "raw_market_data_persisted",
        "recall",
        "replay_materialized",
        "repo_storage_allowed",
        "result_identity",
        "schema_version",
        "score_threshold",
        "screen_id",
        "seed",
        "sequence_length",
        "shape",
        "scope",
        "source",
        "split",
        "status",
        "target_cost_identity",
        "target_values_persisted",
        "true_negative_count",
        "true_positive_count",
        "untouched_tail_session_count",
        "validation_decision_count",
    }
)


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1SequenceSample:
    """One transient, causal 20-by-3 input and its in-memory binary target."""

    phase: MaterializationPhase
    decision_index: int
    predecessor_index: int
    feature_start_index: int
    feature_end_index: int
    entry_index: int
    exit_index: int
    features: SequenceFeatures
    target: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(tuple(row) for row in self.features))
        if (
            self.phase not in {"development", "validation"}
            or type(self.decision_index) is not int
            or type(self.predecessor_index) is not int
            or type(self.feature_start_index) is not int
            or type(self.feature_end_index) is not int
            or type(self.entry_index) is not int
            or type(self.exit_index) is not int
            or self.predecessor_index != self.feature_start_index - 1
            or self.feature_end_index != self.decision_index
            or self.entry_index != self.decision_index + 1
            or self.exit_index != self.decision_index + 2
            or len(self.features) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH
            or any(
                len(row) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT
                or any(not math.isfinite(value) for value in row)
                for row in self.features
            )
            or type(self.target) is not int
            or self.target not in {0, 1}
        ):
            raise ValueError("joint D1 sequence sample is invalid")
        for qqq_value, spy_value, spread_value in self.features:
            if not math.isclose(
                qqq_value - spy_value,
                spread_value,
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise ValueError("joint D1 sequence sample spread is invalid")


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1Standardizer:
    """A development-fitted standardizer that stays in memory with its screen."""

    means: SequenceRow
    scales: SequenceRow

    def __post_init__(self) -> None:
        object.__setattr__(self, "means", tuple(self.means))
        object.__setattr__(self, "scales", tuple(self.scales))
        if (
            len(self.means) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT
            or len(self.scales) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT
            or any(not math.isfinite(value) for value in (*self.means, *self.scales))
            or any(value <= 0 for value in self.scales)
        ):
            raise ValueError("joint D1 sequence standardizer is invalid")

    @property
    def normalization_identity(self) -> str:
        return _sha256_json(
            {
                "sequence_length": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH,
                "column_count": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT,
                "means": [format(value, ".17g") for value in self.means],
                "scales": [format(value, ".17g") for value in self.scales],
            }
        )

    def transform(self, features: SequenceFeatures) -> SequenceFeatures:
        if (
            len(features) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH
            or any(len(row) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT for row in features)
        ):
            raise ValueError("joint D1 sequence standardizer feature shape is invalid")
        transformed = tuple(
            tuple(
                (value - self.means[column]) / self.scales[column]
                for column, value in enumerate(row)
            )
            for row in features
        )
        if any(not math.isfinite(value) for row in transformed for value in row):
            raise ValueError("joint D1 sequence standardizer output is invalid")
        return transformed  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CandidateSpec:
    """One fixed, non-tunable candidate in the first classification screen."""

    candidate_id: CandidateModelId
    seed: int
    hidden_size: int
    learning_rate: float

    def __post_init__(self) -> None:
        if (
            self.candidate_id not in {"linear", "compact_gru"}
            or type(self.seed) is not int
            or self.seed < 0
            or not math.isfinite(self.learning_rate)
            or self.learning_rate <= 0
            or (self.candidate_id == "linear" and self.hidden_size != 0)
            or (self.candidate_id == "compact_gru" and self.hidden_size != 16)
        ):
            raise ValueError("joint D1 candidate spec is invalid")

    def epochs_for(self, mode: CandidateScreenMode) -> int:
        if mode == "cpu-smoke":
            return KIS_DAILY_JOINT_EVENT_D1_CPU_EPOCHS
        if mode == "cuda-screen":
            return KIS_DAILY_JOINT_EVENT_D1_CUDA_EPOCHS
        raise ValueError("joint D1 candidate mode is invalid")

    def document(self, *, mode: CandidateScreenMode) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "family": "linear" if self.candidate_id == "linear" else "compact_sequence_gru",
            "seed": self.seed,
            "hidden_size": self.hidden_size,
            "epochs": self.epochs_for(mode),
        }


KIS_DAILY_JOINT_EVENT_D1_CANDIDATE_SPECS = (
    KisDailyJointEventD1CandidateSpec(
        candidate_id="linear",
        seed=2026072701,
        hidden_size=0,
        learning_rate=0.01,
    ),
    KisDailyJointEventD1CandidateSpec(
        candidate_id="compact_gru",
        seed=2026072702,
        hidden_size=16,
        learning_rate=0.003,
    ),
)


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1ScreenInput:
    """The exact in-memory fold-local input for one candidate-only screen."""

    materializer: KisDailyJointEventD1Materializer
    target_adapter: KisDailyJointEventD1TargetCostAdapter
    development_samples: tuple[KisDailyJointEventD1SequenceSample, ...]
    validation_samples: tuple[KisDailyJointEventD1SequenceSample, ...]
    standardizer: KisDailyJointEventD1Standardizer
    untouched_tail_session_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "development_samples", tuple(self.development_samples))
        object.__setattr__(self, "validation_samples", tuple(self.validation_samples))
        if (
            not isinstance(self.materializer, KisDailyJointEventD1Materializer)
            or not isinstance(self.target_adapter, KisDailyJointEventD1TargetCostAdapter)
            or self.target_adapter.materializer.materializer_identity
            != self.materializer.materializer_identity
        ):
            raise ValueError("joint D1 sequence screen input is invalid")
        fold_spec = _screen_fold_spec(self.materializer.fold_input.fold_id)
        if (
            len(self.development_samples) != fold_spec.development_decision_count
            or len(self.validation_samples) != fold_spec.validation_decision_count
            or self.untouched_tail_session_count
            != KIS_DAILY_JOINT_EVENT_D1_UNTOUCHED_TAIL_SESSION_COUNT
        ):
            raise ValueError("joint D1 sequence screen input is invalid")
        development_indices = tuple(sample.decision_index for sample in self.development_samples)
        validation_indices = tuple(sample.decision_index for sample in self.validation_samples)
        if (
            development_indices
            != self.materializer.eligible_decision_indices("development")
            or validation_indices != self.materializer.eligible_decision_indices("validation")
            or set(development_indices).intersection(validation_indices)
            or any(sample.phase != "development" for sample in self.development_samples)
            or any(sample.phase != "validation" for sample in self.validation_samples)
        ):
            raise ValueError("joint D1 sequence screen split is invalid")

    @property
    def source_identity(self) -> str:
        return _sha256_json(
            {
                "fold_id": self.materializer.fold_input.fold_id,
                "fold_input_identity": self.materializer.fold_input.fold_input_identity,
                "materializer_identity": self.materializer.materializer_identity,
                "target_cost_identity": self.target_adapter.target_cost_identity,
                "catalog_dataset_hash": self.materializer.catalog_dataset_hash,
                "catalog_index_hash": self.materializer.catalog_index_hash,
                "development_decision_count": len(self.development_samples),
                "validation_decision_count": len(self.validation_samples),
                "untouched_tail_session_count": self.untouched_tail_session_count,
                "normalization_identity": self.standardizer.normalization_identity,
            }
        )


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1ClassificationMetrics:
    """Aggregate validation classification counts only; no per-decision output."""

    evaluated_count: int
    observed_positive_count: int
    true_positive_count: int
    true_negative_count: int
    false_positive_count: int
    false_negative_count: int
    accuracy: float
    precision: float
    recall: float
    f1: float

    def __post_init__(self) -> None:
        counts = (
            self.evaluated_count,
            self.observed_positive_count,
            self.true_positive_count,
            self.true_negative_count,
            self.false_positive_count,
            self.false_negative_count,
        )
        if (
            any(type(value) is not int or value < 0 for value in counts)
            or self.evaluated_count <= 0
            or self.true_positive_count
            + self.true_negative_count
            + self.false_positive_count
            + self.false_negative_count
            != self.evaluated_count
            or self.true_positive_count + self.false_negative_count
            != self.observed_positive_count
            or any(
                not math.isfinite(value) or not 0 <= value <= 1
                for value in (self.accuracy, self.precision, self.recall, self.f1)
            )
        ):
            raise ValueError("joint D1 classification metrics are invalid")

    def document(self) -> dict[str, object]:
        return {
            "evaluated_count": self.evaluated_count,
            "observed_positive_count": self.observed_positive_count,
            "true_positive_count": self.true_positive_count,
            "true_negative_count": self.true_negative_count,
            "false_positive_count": self.false_positive_count,
            "false_negative_count": self.false_negative_count,
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1CandidateResult:
    """One aggregate candidate result with no retained model parameters."""

    spec: KisDailyJointEventD1CandidateSpec
    mode: CandidateScreenMode
    backend: str
    metrics: KisDailyJointEventD1ClassificationMetrics

    def __post_init__(self) -> None:
        expected_backend = "torch_cpu" if self.mode == "cpu-smoke" else "torch_cuda"
        if (
            not isinstance(self.spec, KisDailyJointEventD1CandidateSpec)
            or self.mode not in {"cpu-smoke", "cuda-screen"}
            or self.backend not in {expected_backend, "unit"}
            or not isinstance(self.metrics, KisDailyJointEventD1ClassificationMetrics)
        ):
            raise ValueError("joint D1 candidate result is invalid")

    def document(self) -> dict[str, object]:
        document = self.spec.document(mode=self.mode)
        document["device"] = "cpu" if self.mode == "cpu-smoke" else "cuda"
        document["backend"] = self.backend
        document["metrics"] = self.metrics.document()
        return document


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1SequenceScreenRun:
    """External evidence paths plus in-memory aggregate candidate outcomes."""

    screen_input: KisDailyJointEventD1ScreenInput
    mode: CandidateScreenMode
    precommit_path: Path
    precommit_identity: str
    summary_path: Path
    result_identity: str
    candidate_results: tuple[KisDailyJointEventD1CandidateResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_results", tuple(self.candidate_results))
        if (
            not isinstance(self.screen_input, KisDailyJointEventD1ScreenInput)
            or self.mode not in {"cpu-smoke", "cuda-screen"}
            or tuple(result.spec for result in self.candidate_results)
            != KIS_DAILY_JOINT_EVENT_D1_CANDIDATE_SPECS
            or not self.precommit_identity.startswith("sha256:")
            or not self.result_identity.startswith("sha256:")
        ):
            raise ValueError("joint D1 sequence screen run is invalid")


CandidateTrainer = Callable[
    [
        KisDailyJointEventD1ScreenInput,
        KisDailyJointEventD1CandidateSpec,
        CandidateScreenMode,
    ],
    KisDailyJointEventD1CandidateResult,
]


def build_kis_daily_joint_event_d1_sequence_screen_input(
    *,
    materializer: KisDailyJointEventD1Materializer,
    target_adapter: KisDailyJointEventD1TargetCostAdapter,
) -> KisDailyJointEventD1ScreenInput:
    """Reconstruct exactly the verified sparse samples without retaining them."""

    if (
        not isinstance(materializer, KisDailyJointEventD1Materializer)
        or not isinstance(target_adapter, KisDailyJointEventD1TargetCostAdapter)
        or target_adapter.materializer.materializer_identity != materializer.materializer_identity
    ):
        raise ValueError("joint D1 sequence screen source is invalid")
    fold_spec = _screen_fold_spec(materializer.fold_input.fold_id)
    development_indices = materializer.eligible_decision_indices("development")
    validation_indices = materializer.eligible_decision_indices("validation")
    untouched_tail_start_index = (
        KIS_DAILY_JOINT_EVENT_D1_TOTAL_SESSION_COUNT
        - KIS_DAILY_JOINT_EVENT_D1_UNTOUCHED_TAIL_SESSION_COUNT
    )
    if (
        len(development_indices) != fold_spec.development_decision_count
        or len(validation_indices) != fold_spec.validation_decision_count
        or len(materializer.common_sessions) != KIS_DAILY_JOINT_EVENT_D1_TOTAL_SESSION_COUNT
        or set(development_indices).intersection(validation_indices)
        or any(
            index >= materializer.fold_input.validation_end_index
            for index in validation_indices
        )
        or any(
            index + 2 >= untouched_tail_start_index
            for index in (*development_indices, *validation_indices)
        )
    ):
        raise ValueError("joint D1 sequence screen sparse split is incompatible")
    development_samples = tuple(
        _materialize_sample(
            materializer=materializer,
            target_adapter=target_adapter,
            phase="development",
            decision_index=decision_index,
        )
        for decision_index in development_indices
    )
    standardizer = _fit_development_standardizer(development_samples)
    validation_samples = tuple(
        _materialize_sample(
            materializer=materializer,
            target_adapter=target_adapter,
            phase="validation",
            decision_index=decision_index,
        )
        for decision_index in validation_indices
    )
    return KisDailyJointEventD1ScreenInput(
        materializer=materializer,
        target_adapter=target_adapter,
        development_samples=development_samples,
        validation_samples=validation_samples,
        standardizer=standardizer,
        untouched_tail_session_count=KIS_DAILY_JOINT_EVENT_D1_UNTOUCHED_TAIL_SESSION_COUNT,
    )


def run_kis_daily_joint_event_d1_sequence_screen(
    *,
    materializer: KisDailyJointEventD1Materializer,
    target_adapter: KisDailyJointEventD1TargetCostAdapter,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    run_label: str,
    mode: CandidateScreenMode,
    repo_root: Path,
    trainer: CandidateTrainer | None = None,
) -> KisDailyJointEventD1SequenceScreenRun:
    """Run one fixed classification-only screen without replay or promotion."""

    if mode not in {"cpu-smoke", "cuda-screen"}:
        raise ValueError("joint D1 sequence screen mode is invalid")
    _validate_run_label(run_label)
    screen_input = build_kis_daily_joint_event_d1_sequence_screen_input(
        materializer=materializer,
        target_adapter=target_adapter,
    )
    output_dir = _create_external_output_dir(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        run_label=run_label,
    )
    precommit_payload = _precommit_document(screen_input=screen_input, mode=mode)
    precommit_identity = _sha256_json(precommit_payload)
    precommit_payload["precommit_identity"] = precommit_identity
    precommit_path = output_dir / "precommit.json"
    _write_source_safe_json_new(precommit_path, precommit_payload)
    try:
        selected_trainer = trainer or _train_torch_candidate
        candidate_results = tuple(
            selected_trainer(screen_input, spec, mode)
            for spec in KIS_DAILY_JOINT_EVENT_D1_CANDIDATE_SPECS
        )
        _validate_candidate_results(
            candidate_results,
            mode=mode,
            validation_decision_count=len(screen_input.validation_samples),
        )
    except Exception as error:
        _write_source_safe_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_SCHEMA_VERSION,
                "kind": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_KIND,
                "status": "incomplete",
                "screen_id": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID,
                "mode": mode,
                "precommit_identity": precommit_identity,
                "failure_class": type(error).__name__,
                "scope": _scope_document(),
            },
        )
        raise
    summary_payload = _summary_document(
        screen_input=screen_input,
        mode=mode,
        precommit_identity=precommit_identity,
        candidate_results=candidate_results,
    )
    result_identity = _sha256_json(summary_payload)
    summary_payload["result_identity"] = result_identity
    summary_path = output_dir / "summary.json"
    _write_source_safe_json_new(summary_path, summary_payload)
    return KisDailyJointEventD1SequenceScreenRun(
        screen_input=screen_input,
        mode=mode,
        precommit_path=precommit_path,
        precommit_identity=precommit_identity,
        summary_path=summary_path,
        result_identity=result_identity,
        candidate_results=candidate_results,
    )


def _materialize_sample(
    *,
    materializer: KisDailyJointEventD1Materializer,
    target_adapter: KisDailyJointEventD1TargetCostAdapter,
    phase: MaterializationPhase,
    decision_index: int,
) -> KisDailyJointEventD1SequenceSample:
    window = materializer.materialize(phase=phase, decision_index=decision_index)
    target = target_adapter.derive(phase=phase, decision_index=decision_index)
    if (
        window.phase != phase
        or window.decision_index != decision_index
        or target.decision_index != decision_index
        or target.predecessor_index != window.predecessor_index
        or target.feature_start_index != window.feature_start_index
        or target.feature_end_index != window.feature_end_index
        or target.entry_index != window.target_references.entry_index
        or target.exit_index != window.target_references.exit_index
        or window.decision_end > target.entry_start
        or target.entry_start >= target.exit_start
        or len(window.feature_rows) != KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH
    ):
        raise ValueError("joint D1 sequence sample causality is invalid")
    features = tuple(
        (
            float(row.qqq_completed_close_return),
            float(row.spy_completed_close_return),
            float(row.qqq_minus_spy_completed_close_return),
        )
        for row in window.feature_rows
    )
    return KisDailyJointEventD1SequenceSample(
        phase=phase,
        decision_index=decision_index,
        predecessor_index=window.predecessor_index,
        feature_start_index=window.feature_start_index,
        feature_end_index=window.feature_end_index,
        entry_index=target.entry_index,
        exit_index=target.exit_index,
        features=features,
        target=target.label,
    )


def _fit_development_standardizer(
    samples: Sequence[KisDailyJointEventD1SequenceSample],
) -> KisDailyJointEventD1Standardizer:
    if not samples:
        raise ValueError("joint D1 sequence development standardizer input is invalid")
    flattened = tuple(row for sample in samples for row in sample.features)
    row_count = len(flattened)
    if row_count == 0:
        raise ValueError("joint D1 sequence development standardizer is empty")
    means = tuple(
        math.fsum(row[column] for row in flattened) / row_count
        for column in range(KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT)
    )
    scales = tuple(
        max(
            math.sqrt(
                math.fsum((row[column] - means[column]) ** 2 for row in flattened) / row_count
            ),
            1e-12,
        )
        for column in range(KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT)
    )
    return KisDailyJointEventD1Standardizer(means=means, scales=scales)  # type: ignore[arg-type]


def _precommit_document(
    *,
    screen_input: KisDailyJointEventD1ScreenInput,
    mode: CandidateScreenMode,
) -> dict[str, object]:
    document = {
        "schema_version": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_SCHEMA_VERSION,
        "kind": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_KIND,
        "status": "precommitted",
        "screen_id": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID,
        "mode": mode,
        "source": _source_document(screen_input),
        "split": {
            "development_decision_count": len(screen_input.development_samples),
            "validation_decision_count": len(screen_input.validation_samples),
            "untouched_tail_session_count": screen_input.untouched_tail_session_count,
            "pre_validation_gap_consumed": False,
        },
        "shape": {
            "sequence_length": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH,
            "column_count": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT,
        },
        "normalization": {
            "fit_scope": "development_only",
            "normalization_identity": screen_input.standardizer.normalization_identity,
        },
        "classification": {
            "classification_only": True,
            "score_threshold": KIS_DAILY_JOINT_EVENT_D1_SCORE_THRESHOLD,
        },
        "candidates": [
            spec.document(mode=mode) for spec in KIS_DAILY_JOINT_EVENT_D1_CANDIDATE_SPECS
        ],
        "scope": _scope_document(),
        "artifact_policy": {
            "repo_storage_allowed": False,
            "immutable_write_only": True,
        },
    }
    _assert_source_safe(document)
    return document


def _summary_document(
    *,
    screen_input: KisDailyJointEventD1ScreenInput,
    mode: CandidateScreenMode,
    precommit_identity: str,
    candidate_results: tuple[KisDailyJointEventD1CandidateResult, ...],
) -> dict[str, object]:
    document = {
        "schema_version": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_SCHEMA_VERSION,
        "kind": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_KIND,
        "status": "complete",
        "screen_id": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID,
        "mode": mode,
        "precommit_identity": precommit_identity,
        "source": _source_document(screen_input),
        "split": {
            "development_decision_count": len(screen_input.development_samples),
            "validation_decision_count": len(screen_input.validation_samples),
            "untouched_tail_session_count": screen_input.untouched_tail_session_count,
            "pre_validation_gap_consumed": False,
        },
        "shape": {
            "sequence_length": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH,
            "column_count": KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT,
        },
        "normalization": {
            "fit_scope": "development_only",
            "normalization_identity": screen_input.standardizer.normalization_identity,
        },
        "classification": {
            "classification_only": True,
            "score_threshold": KIS_DAILY_JOINT_EVENT_D1_SCORE_THRESHOLD,
        },
        "candidates": [result.document() for result in candidate_results],
        "scope": _scope_document(),
        "artifact_policy": {
            "repo_storage_allowed": False,
            "immutable_write_only": True,
        },
    }
    _assert_source_safe(document)
    return document


def _source_document(screen_input: KisDailyJointEventD1ScreenInput) -> dict[str, object]:
    return {
        "fold_id": screen_input.materializer.fold_input.fold_id,
        "fold_input_identity": screen_input.materializer.fold_input.fold_input_identity,
        "materializer_identity": screen_input.materializer.materializer_identity,
        "target_cost_identity": screen_input.target_adapter.target_cost_identity,
        "normalization_identity": screen_input.standardizer.normalization_identity,
    }


def _scope_document() -> dict[str, bool]:
    return {
        "offline_only": True,
        "candidate_only": True,
        "model_execution_eligible": False,
        "candidate_selection_eligible": False,
        "ensemble_eligible": False,
        "replay_materialized": False,
        "paper_decision_eligible": False,
        "raw_market_data_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "per_decision_outputs_persisted": False,
        "credentials_persisted": False,
    }


def _validate_candidate_results(
    results: tuple[KisDailyJointEventD1CandidateResult, ...],
    *,
    mode: CandidateScreenMode,
    validation_decision_count: int,
) -> None:
    if (
        tuple(result.spec for result in results) != KIS_DAILY_JOINT_EVENT_D1_CANDIDATE_SPECS
        or any(result.mode != mode for result in results)
        or any(result.metrics.evaluated_count != validation_decision_count for result in results)
    ):
        raise ValueError("joint D1 sequence screen candidates changed the frozen contract")


def _train_torch_candidate(
    screen_input: KisDailyJointEventD1ScreenInput,
    spec: KisDailyJointEventD1CandidateSpec,
    mode: CandidateScreenMode,
) -> KisDailyJointEventD1CandidateResult:
    """Train one fixed candidate in memory and discard parameters after metrics."""

    import torch

    if mode == "cuda-screen" and not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is unavailable")
    device = torch.device("cuda" if mode == "cuda-screen" else "cpu")
    previous_threads = torch.get_num_threads()
    previous_deterministic = torch.are_deterministic_algorithms_enabled()
    previous_cudnn_deterministic = torch.backends.cudnn.deterministic
    previous_cudnn_benchmark = torch.backends.cudnn.benchmark
    try:
        torch.set_num_threads(1)
        torch.use_deterministic_algorithms(True)
        torch.manual_seed(spec.seed)
        if mode == "cuda-screen":
            torch.cuda.manual_seed_all(spec.seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        development_features = torch.tensor(
            _normalized_features(screen_input.development_samples, screen_input.standardizer),
            dtype=torch.float32,
            device=device,
        )
        development_targets = torch.tensor(
            tuple(sample.target for sample in screen_input.development_samples),
            dtype=torch.float32,
            device=device,
        ).unsqueeze(1)
        validation_features = torch.tensor(
            _normalized_features(screen_input.validation_samples, screen_input.standardizer),
            dtype=torch.float32,
            device=device,
        )
        validation_targets = torch.tensor(
            tuple(sample.target for sample in screen_input.validation_samples),
            dtype=torch.int64,
            device=device,
        )
        model = _build_torch_model(torch=torch, spec=spec).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate)
        loss_function = torch.nn.BCEWithLogitsLoss()
        started = time.monotonic()
        max_seconds = (
            KIS_DAILY_JOINT_EVENT_D1_CPU_MAX_SECONDS
            if mode == "cpu-smoke"
            else KIS_DAILY_JOINT_EVENT_D1_CUDA_MAX_SECONDS
        )
        for _ in range(spec.epochs_for(mode)):
            if time.monotonic() - started > max_seconds:
                raise RuntimeError("joint D1 sequence candidate wall-clock cap exceeded")
            optimizer.zero_grad(set_to_none=True)
            logits = model(development_features)
            loss = loss_function(logits, development_targets)
            if not torch.isfinite(loss).item():
                raise RuntimeError("joint D1 sequence candidate loss is nonfinite")
            loss.backward()
            optimizer.step()
        with torch.no_grad():
            validation_logits = model(validation_features).reshape(-1)
            predicted = torch.sigmoid(validation_logits).ge(
                KIS_DAILY_JOINT_EVENT_D1_SCORE_THRESHOLD
            ).to(torch.int64)
        metrics = _classification_metrics_from_tensors(
            predicted=predicted,
            observed=validation_targets,
        )
        return KisDailyJointEventD1CandidateResult(
            spec=spec,
            mode=mode,
            backend="torch_cuda" if mode == "cuda-screen" else "torch_cpu",
            metrics=metrics,
        )
    finally:
        torch.set_num_threads(previous_threads)
        torch.use_deterministic_algorithms(previous_deterministic)
        torch.backends.cudnn.deterministic = previous_cudnn_deterministic
        torch.backends.cudnn.benchmark = previous_cudnn_benchmark


def _normalized_features(
    samples: Sequence[KisDailyJointEventD1SequenceSample],
    standardizer: KisDailyJointEventD1Standardizer,
) -> tuple[SequenceFeatures, ...]:
    return tuple(standardizer.transform(sample.features) for sample in samples)


def _build_torch_model(*, torch: object, spec: KisDailyJointEventD1CandidateSpec) -> object:
    nn = torch.nn
    if spec.candidate_id == "linear":
        return nn.Sequential(
            nn.Flatten(),
            nn.Linear(
                KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_LENGTH
                * KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT,
                1,
            ),
        )

    class CompactGruModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.GRU(
                input_size=KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_COLUMN_COUNT,
                hidden_size=spec.hidden_size,
                batch_first=True,
            )
            self.head = nn.Linear(spec.hidden_size, 1)

        def forward(self, values: object) -> object:
            encoded, _ = self.encoder(values)
            return self.head(encoded[:, -1, :])

    return CompactGruModel()


def _classification_metrics_from_tensors(
    *,
    predicted: object,
    observed: object,
) -> KisDailyJointEventD1ClassificationMetrics:
    true_positive = int(((predicted == 1) & (observed == 1)).sum().item())
    true_negative = int(((predicted == 0) & (observed == 0)).sum().item())
    false_positive = int(((predicted == 1) & (observed == 0)).sum().item())
    false_negative = int(((predicted == 0) & (observed == 1)).sum().item())
    evaluated_count = true_positive + true_negative + false_positive + false_negative
    observed_positive = true_positive + false_negative
    accuracy = _ratio(true_positive + true_negative, evaluated_count)
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = _ratio(2 * precision * recall, precision + recall)
    return KisDailyJointEventD1ClassificationMetrics(
        evaluated_count=evaluated_count,
        observed_positive_count=observed_positive,
        true_positive_count=true_positive,
        true_negative_count=true_negative,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 12)


def _create_external_output_dir(*, artifact_root: Path, repo_root: Path, run_label: str) -> Path:
    resolved_repo = repo_root.resolve()
    resolved_root = artifact_root.resolve()
    if (
        artifact_root.is_symlink()
        or (resolved_root == resolved_repo or resolved_root.is_relative_to(resolved_repo))
        and not is_container_external_mount(resolved_root, resolved_repo)
    ):
        raise ValueError("joint D1 sequence artifacts must stay outside the Git workspace")
    resolved_root.mkdir(parents=True, exist_ok=True)
    screen_root = resolved_root / KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_ID
    if screen_root.is_symlink():
        raise ValueError("joint D1 sequence artifact destination is invalid")
    screen_root.mkdir(exist_ok=True)
    if not screen_root.resolve().is_relative_to(resolved_root):
        raise ValueError("joint D1 sequence artifact destination is invalid")
    output_dir = screen_root / run_label
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("joint D1 sequence artifact run label already exists")
    output_dir.mkdir()
    if not output_dir.resolve().is_relative_to(resolved_root):
        raise ValueError("joint D1 sequence artifact destination is invalid")
    return output_dir


def _write_source_safe_json_new(path: Path, payload: Mapping[str, object]) -> None:
    _assert_source_safe(payload)
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key not in _ALLOWED_ARTIFACT_KEYS:
                raise ValueError(f"joint D1 sequence artifact key is not source-safe: {key}")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("joint D1 sequence artifact value is not source-safe")
    elif not isinstance(value, (str, int, float, bool)) and value is not None:
        raise ValueError("joint D1 sequence artifact value is not source-safe")


def _validate_run_label(run_label: str) -> None:
    if (
        not isinstance(run_label, str)
        or not run_label
        or len(run_label) > 80
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
            for character in run_label
        )
    ):
        raise ValueError("joint D1 sequence run label is invalid")


def _screen_fold_spec(fold_id: str) -> KisDailyJointEventD1SequenceScreenFoldSpec:
    if not isinstance(fold_id, str):
        raise ValueError("joint D1 sequence screen fold is invalid")
    try:
        return KIS_DAILY_JOINT_EVENT_D1_SEQUENCE_SCREEN_FOLD_SPECS[fold_id]
    except KeyError as error:
        raise ValueError("joint D1 sequence screen fold is invalid") from error


def _sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

"""Bounded candidate model evaluation for the research profile."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data import SampleBarProvider
from thericher_v2.serialization import to_jsonable

from .candidate_training import (
    CandidateTrainingDataset,
    GpuReadiness,
    _candidate_lookback,
    _reject_repo_artifact_path,
    build_candidate_training_dataset,
    detect_gpu_readiness,
    load_yahoo_intraday_1m_bars,
)

CandidateEvaluationStatus = Literal["candidate_evaluated_only", "prepared_not_evaluated"]
DEFAULT_CANDIDATE_EVALUATION_RUN_ID = "bounded-candidate-evaluation"
MAX_CANDIDATE_EVALUATION_BARS = 512
OPTIONAL_CANDIDATE_EVALUATION_BACKENDS = ("torch",)


@dataclass(frozen=True)
class CandidateEvaluationConfig:
    run_id: str = DEFAULT_CANDIDATE_EVALUATION_RUN_ID
    max_bars: int = 120
    min_examples: int = 8
    probability_threshold: float = 0.5
    sample_seed: int = 31
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if self.max_bars <= 0:
            raise ValueError("max_bars must be positive")
        if self.max_bars > MAX_CANDIDATE_EVALUATION_BARS:
            raise ValueError(f"max_bars must be <= {MAX_CANDIDATE_EVALUATION_BARS}")
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        if not 0 < self.probability_threshold < 1:
            raise ValueError("probability_threshold must be between 0 and 1")


@dataclass(frozen=True)
class BoundedCandidateEvaluationResult:
    run_id: str
    status: CandidateEvaluationStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    available_backends: tuple[str, ...]
    selected_backend: str | None
    training_metrics_artifact: Path | None
    model_artifact: Path | None
    candidate_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    examples_seen: int
    metrics: dict[str, Any]
    evaluation_artifact: Path
    local_paper_conversion: str = "deferred_to_next_goal"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


CandidateEvaluationRunner = Callable[
    [CandidateTrainingDataset, Path, dict[str, Any], CandidateEvaluationConfig],
    dict[str, Any],
]


def run_bounded_candidate_evaluation(
    *,
    config: CandidateEvaluationConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    training_metrics_artifact: Path | None = None,
    model_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    gpu: GpuReadiness | None = None,
    evaluation_runner: CandidateEvaluationRunner | None = None,
) -> BoundedCandidateEvaluationResult:
    config = config or CandidateEvaluationConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-evaluation" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluation_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()
    training_payload, training_read_error = _read_training_metrics(training_metrics_artifact)
    candidate = _candidate_from_training_payload(training_payload)
    dataset = _load_evaluation_dataset(
        config=config,
        candidate=candidate,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
    )
    selected_model_artifact = model_artifact or _model_artifact_from_training_payload(
        training_payload
    )
    available_backends = _available_gpu_backends()
    selected_backend = "injected" if evaluation_runner is not None else _selected_backend()

    result = _run_candidate_evaluation_result(
        config=config,
        training_metrics_artifact=training_metrics_artifact,
        training_read_error=training_read_error,
        model_artifact=selected_model_artifact,
        candidate=candidate,
        training_payload=training_payload,
        dataset=dataset,
        gpu=gpu,
        available_backends=available_backends,
        selected_backend=selected_backend,
        evaluation_artifact=evaluation_artifact,
        evaluation_runner=evaluation_runner,
    )
    evaluation_artifact.write_text(
        json.dumps(_candidate_evaluation_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def _run_candidate_evaluation_result(
    *,
    config: CandidateEvaluationConfig,
    training_metrics_artifact: Path | None,
    training_read_error: str | None,
    model_artifact: Path | None,
    candidate: dict[str, Any],
    training_payload: dict[str, Any],
    dataset: CandidateTrainingDataset,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    evaluation_artifact: Path,
    evaluation_runner: CandidateEvaluationRunner | None,
) -> BoundedCandidateEvaluationResult:
    if training_read_error is not None:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            evaluation_artifact=evaluation_artifact,
            reason=training_read_error,
        )
    expected_feature_names = _feature_names_from_training_payload(training_payload)
    if expected_feature_names and expected_feature_names != dataset.feature_names:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            evaluation_artifact=evaluation_artifact,
            reason=(
                "training/evaluation feature names mismatch: "
                f"{expected_feature_names} != {dataset.feature_names}"
            ),
        )
    if model_artifact is None or not model_artifact.exists():
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            evaluation_artifact=evaluation_artifact,
            reason="candidate model artifact is missing",
        )
    if not gpu.available:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            evaluation_artifact=evaluation_artifact,
            reason=f"GPU readiness unavailable: {gpu.detail}",
        )
    if len(dataset.labels) < config.min_examples:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            evaluation_artifact=evaluation_artifact,
            reason=(
                "insufficient evaluation examples: "
                f"{len(dataset.labels)} < {config.min_examples}"
            ),
        )
    if evaluation_runner is None and selected_backend is None:
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=None,
            evaluation_artifact=evaluation_artifact,
            reason="no operator-approved research GPU evaluation backend installed",
        )
    runner = evaluation_runner or _run_torch_cuda_candidate_evaluation
    try:
        metrics = runner(dataset, model_artifact, training_payload, config)
    except Exception as exc:  # noqa: BLE001 - evaluation jobs record backend failures.
        return _prepared_result(
            config=config,
            training_metrics_artifact=training_metrics_artifact,
            model_artifact=model_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            evaluation_artifact=evaluation_artifact,
            reason=f"bounded candidate evaluation unavailable: {exc}",
        )
    metrics = {
        **_baseline_classification_metrics(dataset),
        **metrics,
        "local_paper_conversion": "deferred_to_next_goal",
    }
    return BoundedCandidateEvaluationResult(
        run_id=config.run_id,
        status="candidate_evaluated_only",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="bounded candidate evaluation completed",
        available_backends=available_backends,
        selected_backend=selected_backend,
        training_metrics_artifact=training_metrics_artifact,
        model_artifact=model_artifact,
        candidate_artifact=_candidate_artifact_from_training_payload(training_payload),
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=dataset.data_source,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        bars_seen=dataset.bars_seen,
        examples_seen=len(dataset.labels),
        metrics=metrics,
        evaluation_artifact=evaluation_artifact,
    )


def _prepared_result(
    *,
    config: CandidateEvaluationConfig,
    training_metrics_artifact: Path | None,
    model_artifact: Path | None,
    candidate: dict[str, Any],
    dataset: CandidateTrainingDataset,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    evaluation_artifact: Path,
    reason: str,
) -> BoundedCandidateEvaluationResult:
    return BoundedCandidateEvaluationResult(
        run_id=config.run_id,
        status="prepared_not_evaluated",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        available_backends=available_backends,
        selected_backend=selected_backend,
        training_metrics_artifact=training_metrics_artifact,
        model_artifact=model_artifact,
        candidate_artifact=None,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=dataset.data_source,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        bars_seen=dataset.bars_seen,
        examples_seen=len(dataset.labels),
        metrics={},
        evaluation_artifact=evaluation_artifact,
    )


def _load_evaluation_dataset(
    *,
    config: CandidateEvaluationConfig,
    candidate: dict[str, Any],
    yahoo_snapshot: Path | None,
    symbol: str | None,
) -> CandidateTrainingDataset:
    if yahoo_snapshot is not None:
        bars = load_yahoo_intraday_1m_bars(
            yahoo_snapshot,
            symbol=symbol,
            max_bars=config.max_bars,
        )
        data_source = str(yahoo_snapshot)
    else:
        provider = SampleBarProvider.trending_1m(
            count=config.max_bars,
            seed=config.sample_seed,
        )
        bars = list(provider.base_bars)
        data_source = f"deterministic_sample_heldout_seed{config.sample_seed}"
    lookback = _candidate_lookback(candidate)
    return build_candidate_training_dataset(
        bars,
        lookback=lookback,
        data_source=data_source,
    )


def _run_torch_cuda_candidate_evaluation(
    dataset: CandidateTrainingDataset,
    model_artifact: Path,
    training_payload: dict[str, Any],
    config: CandidateEvaluationConfig,
) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch CUDA is not available")
    device = torch.device("cuda")
    checkpoint = torch.load(model_artifact, map_location=device, weights_only=False)
    feature_names = tuple(str(name) for name in checkpoint.get("feature_names", ()))
    if feature_names != dataset.feature_names:
        raise ValueError(f"model feature names do not match evaluation dataset: {feature_names}")
    state_dict = checkpoint.get("state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("model checkpoint is missing state_dict")
    hidden_units = int(checkpoint.get("hidden_units") or _infer_hidden_units(state_dict))
    model = torch.nn.Sequential(
        torch.nn.Linear(len(dataset.feature_names), hidden_units),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_units, 1),
    ).to(device)
    model.load_state_dict(state_dict)
    model.eval()
    x = torch.tensor(dataset.features, dtype=torch.float32, device=device)
    y = torch.tensor(dataset.labels, dtype=torch.float32, device=device).view(-1, 1)
    loss_fn = torch.nn.BCEWithLogitsLoss()
    with torch.no_grad():
        logits = model(x)
        loss = loss_fn(logits, y)
        probabilities = torch.sigmoid(logits)
        predictions = (probabilities >= config.probability_threshold).float()
        accuracy = (predictions == y).float().mean()
        predicted_positive_rate = predictions.mean()
        mean_probability = probabilities.mean()
    torch.cuda.synchronize()
    return {
        "backend": "torch",
        "operation": "tiny_mlp_next_bar_direction_evaluation",
        "device": torch.cuda.get_device_name(device),
        "examples_seen": len(dataset.labels),
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "hidden_units": hidden_units,
        "loss": f"{loss.item():.6f}",
        "accuracy": f"{accuracy.item():.6f}",
        "mean_probability": f"{mean_probability.item():.6f}",
        "predicted_positive_rate": f"{predicted_positive_rate.item():.6f}",
        "probability_threshold": f"{config.probability_threshold:.6f}",
        "model_artifact": str(model_artifact),
        "candidate_experiment_id": training_payload.get("candidate_experiment_id"),
    }


def _candidate_evaluation_payload(
    result: BoundedCandidateEvaluationResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "gpu": result.gpu,
            "reason": result.reason,
            "available_backends": result.available_backends,
            "selected_backend": result.selected_backend,
            "training_metrics_artifact": (
                None
                if result.training_metrics_artifact is None
                else str(result.training_metrics_artifact)
            ),
            "model_artifact": (
                None if result.model_artifact is None else str(result.model_artifact)
            ),
            "candidate_artifact": (
                None if result.candidate_artifact is None else str(result.candidate_artifact)
            ),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "data_source": result.data_source,
            "symbol": result.symbol,
            "market": result.market,
            "timeframe": result.timeframe,
            "bars_seen": result.bars_seen,
            "examples_seen": result.examples_seen,
            "metrics": result.metrics,
            "local_paper_conversion": result.local_paper_conversion,
            "artifacts": {
                "evaluation": str(result.evaluation_artifact),
                "source_model": None
                if result.model_artifact is None
                else str(result.model_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _read_training_metrics(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "training metrics artifact is required"
    if not path.exists():
        return {}, f"training metrics artifact is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"training metrics artifact is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "training metrics artifact must contain a JSON object"
    return payload, None


def _candidate_from_training_payload(payload: dict[str, Any]) -> dict[str, Any]:
    parameters = payload.get("candidate_parameters")
    return {
        "candidate_experiment_id": payload.get("candidate_experiment_id"),
        "candidate_parameters": parameters if isinstance(parameters, dict) else {},
    }


def _model_artifact_from_training_payload(payload: dict[str, Any]) -> Path | None:
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict) and artifacts.get("model"):
        return Path(str(artifacts["model"]))
    metrics = payload.get("metrics")
    if isinstance(metrics, dict) and metrics.get("model_artifact"):
        return Path(str(metrics["model_artifact"]))
    return None


def _candidate_artifact_from_training_payload(payload: dict[str, Any]) -> Path | None:
    value = payload.get("candidate_artifact")
    if not value:
        return None
    return Path(str(value))


def _feature_names_from_training_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return ()
    names = metrics.get("feature_names")
    if not isinstance(names, list | tuple):
        return ()
    return tuple(str(name) for name in names)


def _baseline_classification_metrics(dataset: CandidateTrainingDataset) -> dict[str, Any]:
    examples = len(dataset.labels)
    if examples == 0:
        return {
            "baseline_majority_accuracy": "0.000000",
            "baseline_always_up_accuracy": "0.000000",
            "label_positive_rate": "0.000000",
        }
    positives = sum(dataset.labels)
    negatives = examples - positives
    return {
        "baseline_majority_accuracy": f"{(max(positives, negatives) / examples):.6f}",
        "baseline_always_up_accuracy": f"{(positives / examples):.6f}",
        "label_positive_rate": f"{(positives / examples):.6f}",
    }


def _available_gpu_backends() -> tuple[str, ...]:
    return tuple(
        backend
        for backend in OPTIONAL_CANDIDATE_EVALUATION_BACKENDS
        if importlib.util.find_spec(backend) is not None
    )


def _selected_backend() -> str | None:
    if importlib.util.find_spec("torch") is not None:
        return "torch"
    return None


def _infer_hidden_units(state_dict: dict[str, Any]) -> int:
    first_weight = state_dict.get("0.weight")
    shape = getattr(first_weight, "shape", None)
    if shape is None or len(shape) < 1:
        raise ValueError("cannot infer hidden_units from model checkpoint")
    return int(shape[0])

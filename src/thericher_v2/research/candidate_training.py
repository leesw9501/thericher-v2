"""Bounded GPU candidate training for the research profile."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import SampleBarProvider, assess_bar_quality
from thericher_v2.serialization import to_jsonable

CandidateTrainingStatus = Literal["candidate_trained_only", "prepared_not_trained"]
DEFAULT_CANDIDATE_TRAINING_RUN_ID = "bounded-gpu-candidate-training"
MAX_CANDIDATE_TRAINING_EPOCHS = 20
MAX_CANDIDATE_TRAINING_STEPS = 1024
MAX_CANDIDATE_TRAINING_BARS = 512
DEFAULT_CANDIDATE_TRAINING_HIDDEN_UNITS = 8
MAX_CANDIDATE_TRAINING_HIDDEN_UNITS = 64
DEFAULT_CANDIDATE_TRAINING_WEIGHT_DECAY = 0.0
MAX_CANDIDATE_TRAINING_WEIGHT_DECAY = 0.1
DEFAULT_CANDIDATE_FEATURE_PREPROCESSING = "none"
CANDIDATE_FEATURE_STANDARDIZATION = "feature_standardization"
SUPPORTED_CANDIDATE_FEATURE_PREPROCESSING = (
    DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
    CANDIDATE_FEATURE_STANDARDIZATION,
)
FEATURE_STANDARDIZATION_SCALE_FLOOR = 1e-12
MAX_CANDIDATE_DATA_SLICES = 6
OPTIONAL_CANDIDATE_TRAINING_BACKENDS = ("torch",)
CORE_FEATURE_SET_ID = "core_v1"
CORE_PLUS_BAR_POSITION_FEATURE_SET_ID = "core_plus_bar_position_v1"
CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID = "core_plus_bar_pressure_v1"
CORE_PLUS_ENTRY_ADVERSE_FEATURE_SET_ID = "core_plus_entry_adverse_v1"
SUPPORTED_CANDIDATE_FEATURE_SETS = (
    CORE_FEATURE_SET_ID,
    CORE_PLUS_BAR_POSITION_FEATURE_SET_ID,
    CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
    CORE_PLUS_ENTRY_ADVERSE_FEATURE_SET_ID,
)


@dataclass(frozen=True)
class GpuReadiness:
    available: bool
    detail: str
    checked_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


@dataclass(frozen=True)
class CandidateTrainingConfig:
    run_id: str = DEFAULT_CANDIDATE_TRAINING_RUN_ID
    max_epochs: int = 8
    max_steps: int = 256
    max_bars: int = 120
    min_examples: int = 8
    learning_rate: float = 0.01
    hidden_units: int = DEFAULT_CANDIDATE_TRAINING_HIDDEN_UNITS
    weight_decay: float = DEFAULT_CANDIDATE_TRAINING_WEIGHT_DECAY
    feature_preprocessing: str = DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        _validate_positive_cap(
            self.max_epochs,
            field_name="max_epochs",
            ceiling=MAX_CANDIDATE_TRAINING_EPOCHS,
        )
        _validate_positive_cap(
            self.max_steps,
            field_name="max_steps",
            ceiling=MAX_CANDIDATE_TRAINING_STEPS,
        )
        _validate_positive_cap(
            self.max_bars,
            field_name="max_bars",
            ceiling=MAX_CANDIDATE_TRAINING_BARS,
        )
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        _validate_positive_cap(
            self.hidden_units,
            field_name="hidden_units",
            ceiling=MAX_CANDIDATE_TRAINING_HIDDEN_UNITS,
        )
        _validate_non_negative_float_cap(
            self.weight_decay,
            field_name="weight_decay",
            ceiling=MAX_CANDIDATE_TRAINING_WEIGHT_DECAY,
        )
        if self.feature_preprocessing not in SUPPORTED_CANDIDATE_FEATURE_PREPROCESSING:
            raise ValueError(
                "feature_preprocessing must be one of "
                f"{SUPPORTED_CANDIDATE_FEATURE_PREPROCESSING}"
            )


@dataclass(frozen=True)
class CandidateDataSliceConfig:
    slice_id: str
    yahoo_snapshot: Path
    symbol: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.slice_id:
            raise ValueError("slice_id is required")
        if any(part in self.slice_id for part in ("\\", "/", ":")):
            raise ValueError("slice_id must not contain path separators")
        if not self.symbol:
            raise ValueError("symbol is required")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class CandidateTrainingDataset:
    features: tuple[tuple[float, ...], ...]
    labels: tuple[int, ...]
    feature_names: tuple[str, ...]
    symbol: str
    market: str
    timeframe: Timeframe
    data_source: str
    bars_seen: int
    lookback: int
    source_slices: tuple[dict[str, Any], ...] = ()
    feature_preprocessing: str = DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    feature_normalization: dict[str, Any] | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class BoundedCandidateTrainingResult:
    run_id: str
    status: CandidateTrainingStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    available_backends: tuple[str, ...]
    selected_backend: str | None
    candidate_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    data_source: str
    symbol: str | None
    market: str | None
    timeframe: Timeframe | None
    bars_seen: int
    examples_seen: int
    source_slices: tuple[dict[str, Any], ...]
    max_epochs: int
    max_steps: int
    hidden_units: int
    weight_decay: float
    feature_preprocessing: str
    feature_normalization: dict[str, Any] | None
    metrics: dict[str, Any]
    metrics_artifact: Path
    model_artifact: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


CandidateTrainerRunner = Callable[
    [CandidateTrainingDataset, dict[str, Any], Path, CandidateTrainingConfig],
    dict[str, Any],
]


def run_bounded_candidate_training(
    *,
    config: CandidateTrainingConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    candidate_artifact: Path | None = None,
    yahoo_snapshot: Path | None = None,
    symbol: str | None = None,
    data_slices: tuple[CandidateDataSliceConfig, ...] = (),
    gpu: GpuReadiness | None = None,
    trainer_runner: CandidateTrainerRunner | None = None,
) -> BoundedCandidateTrainingResult:
    config = config or CandidateTrainingConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-training" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_artifact = output_dir / "metrics.json"
    model_artifact = output_dir / "model.pt"
    gpu = gpu or detect_gpu_readiness()
    candidate = _read_candidate_artifact(candidate_artifact)
    available_backends = _available_gpu_backends()
    selected_backend = "injected" if trainer_runner is not None else _selected_backend()
    try:
        dataset = _load_dataset(
            config=config,
            candidate=candidate,
            yahoo_snapshot=yahoo_snapshot,
            symbol=symbol,
            data_slices=data_slices,
        )
        dataset_error = None
    except Exception as exc:  # noqa: BLE001 - training jobs record prepared data failures.
        dataset = _empty_dataset(
            data_source="candidate_training_dataset_unavailable",
            lookback=_candidate_lookback(candidate),
            feature_set=_candidate_feature_set_or_default(candidate),
            source_slices=_source_slices_from_configs(data_slices),
        )
        dataset_error = f"candidate training dataset unavailable: {exc}"

    result = _run_candidate_training_result(
        config=config,
        candidate_artifact=candidate_artifact,
        candidate=candidate,
        dataset=dataset,
        dataset_error=dataset_error,
        gpu=gpu,
        available_backends=available_backends,
        selected_backend=selected_backend,
        model_artifact=model_artifact,
        metrics_artifact=metrics_artifact,
        trainer_runner=trainer_runner,
    )
    metrics_artifact.write_text(
        json.dumps(_candidate_training_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def _run_candidate_training_result(
    *,
    config: CandidateTrainingConfig,
    candidate_artifact: Path | None,
    candidate: dict[str, Any],
    dataset: CandidateTrainingDataset,
    dataset_error: str | None,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    model_artifact: Path,
    metrics_artifact: Path,
    trainer_runner: CandidateTrainerRunner | None,
) -> BoundedCandidateTrainingResult:
    if dataset_error is not None:
        return _prepared_result(
            config=config,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            metrics_artifact=metrics_artifact,
            reason=dataset_error,
        )
    if not gpu.available:
        return _prepared_result(
            config=config,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            metrics_artifact=metrics_artifact,
            reason=f"GPU readiness unavailable: {gpu.detail}",
        )
    if len(dataset.labels) < config.min_examples:
        return _prepared_result(
            config=config,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            metrics_artifact=metrics_artifact,
            reason=f"insufficient training examples: {len(dataset.labels)} < {config.min_examples}",
        )
    if trainer_runner is None and selected_backend is None:
        return _prepared_result(
            config=config,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=None,
            metrics_artifact=metrics_artifact,
            reason="no operator-approved research GPU training backend installed",
        )
    feature_normalization = build_feature_normalization(
        dataset,
        feature_preprocessing=config.feature_preprocessing,
    )
    training_dataset = apply_feature_normalization(
        dataset,
        feature_normalization=feature_normalization,
    )
    runner = trainer_runner or _run_torch_cuda_candidate_training
    try:
        metrics = runner(training_dataset, candidate, model_artifact, config)
    except Exception as exc:  # noqa: BLE001 - candidate jobs record non-fatal backend failures.
        return _prepared_result(
            config=config,
            candidate_artifact=candidate_artifact,
            candidate=candidate,
            dataset=dataset,
            gpu=gpu,
            available_backends=available_backends,
            selected_backend=selected_backend,
            metrics_artifact=metrics_artifact,
            reason=f"bounded candidate training unavailable: {exc}",
        )
    return BoundedCandidateTrainingResult(
        run_id=config.run_id,
        status="candidate_trained_only",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="bounded candidate training completed",
        available_backends=available_backends,
        selected_backend=selected_backend,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=dataset.data_source,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        bars_seen=dataset.bars_seen,
        examples_seen=len(dataset.labels),
        source_slices=dataset.source_slices,
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
        hidden_units=config.hidden_units,
        weight_decay=config.weight_decay,
        feature_preprocessing=config.feature_preprocessing,
        feature_normalization=feature_normalization,
        metrics=metrics,
        metrics_artifact=metrics_artifact,
        model_artifact=model_artifact,
    )


def _prepared_result(
    *,
    config: CandidateTrainingConfig,
    candidate_artifact: Path | None,
    candidate: dict[str, Any],
    dataset: CandidateTrainingDataset,
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    metrics_artifact: Path,
    reason: str,
) -> BoundedCandidateTrainingResult:
    return BoundedCandidateTrainingResult(
        run_id=config.run_id,
        status="prepared_not_trained",
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=reason,
        available_backends=available_backends,
        selected_backend=selected_backend,
        candidate_artifact=candidate_artifact,
        candidate_experiment_id=candidate.get("candidate_experiment_id"),
        candidate_parameters=candidate.get("candidate_parameters") or {},
        data_source=dataset.data_source,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        bars_seen=dataset.bars_seen,
        examples_seen=len(dataset.labels),
        source_slices=dataset.source_slices,
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
        hidden_units=config.hidden_units,
        weight_decay=config.weight_decay,
        feature_preprocessing=config.feature_preprocessing,
        feature_normalization=build_feature_normalization(
            dataset,
            feature_preprocessing=config.feature_preprocessing,
        ),
        metrics={},
        metrics_artifact=metrics_artifact,
    )


def _load_dataset(
    *,
    config: CandidateTrainingConfig,
    candidate: dict[str, Any],
    yahoo_snapshot: Path | None,
    symbol: str | None,
    data_slices: tuple[CandidateDataSliceConfig, ...],
) -> CandidateTrainingDataset:
    if data_slices:
        return build_multi_slice_candidate_training_dataset(
            data_slices=data_slices,
            candidate=candidate,
            max_bars=config.max_bars,
            data_source="multi_slice_yahoo_training",
        )
    if yahoo_snapshot is not None:
        bars = load_yahoo_intraday_1m_bars(
            yahoo_snapshot,
            symbol=symbol,
            max_bars=config.max_bars,
        )
        lookback = _candidate_lookback(candidate)
        feature_set = _candidate_feature_set(candidate)
        dataset = build_candidate_training_dataset(
            bars,
            lookback=lookback,
            data_source=str(yahoo_snapshot),
            feature_set=feature_set,
        )
        return _with_source_slices(
            dataset,
            (
                _source_slice_summary(
                    slice_id=f"s01_{(symbol or bars[0].symbol).upper()}",
                    yahoo_snapshot=yahoo_snapshot,
                    symbol=dataset.symbol,
                    dataset=dataset,
                    data_quality=_compact_data_quality_summary(bars),
                ),
            ),
        )
    else:
        provider = SampleBarProvider.trending_1m(count=config.max_bars, seed=29)
        bars = list(provider.base_bars)
        data_source = "deterministic_sample"
        source_slices = ()
    lookback = _candidate_lookback(candidate)
    feature_set = _candidate_feature_set(candidate)
    return build_candidate_training_dataset(
        bars,
        lookback=lookback,
        data_source=data_source,
        feature_set=feature_set,
        source_slices=source_slices,
    )


def build_candidate_training_dataset(
    bars: list[Bar],
    *,
    lookback: int,
    data_source: str,
    feature_set: str = CORE_FEATURE_SET_ID,
    source_slices: tuple[dict[str, Any], ...] = (),
) -> CandidateTrainingDataset:
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    feature_names = _feature_names(feature_set)
    ordered = sorted(bars, key=lambda bar: bar.start_ts)
    if not ordered:
        return CandidateTrainingDataset(
            features=(),
            labels=(),
            feature_names=feature_names,
            symbol="",
            market="",
            timeframe=Timeframe.M1,
            data_source=data_source,
            bars_seen=0,
            lookback=lookback,
            source_slices=source_slices,
        )
    first = ordered[0]
    if any(
        bar.symbol != first.symbol
        or bar.market != first.market
        or bar.timeframe != first.timeframe
        or not bar.complete
        for bar in ordered
    ):
        raise ValueError(
            "candidate training bars must be complete and share symbol, market, timeframe"
        )
    features: list[tuple[float, ...]] = []
    labels: list[int] = []
    for index in range(lookback, len(ordered) - 1):
        prior = ordered[index - 1]
        anchor = ordered[index - lookback]
        current = ordered[index]
        next_bar = ordered[index + 1]
        features.append(
            _feature_vector(
                current=current,
                prior=prior,
                anchor=anchor,
                feature_set=feature_set,
            )
        )
        labels.append(1 if next_bar.close > current.close else 0)
    return CandidateTrainingDataset(
        features=tuple(features),
        labels=tuple(labels),
        feature_names=feature_names,
        symbol=first.symbol,
        market=first.market,
        timeframe=first.timeframe,
        data_source=data_source,
        bars_seen=len(ordered),
        lookback=lookback,
        source_slices=source_slices,
    )


def build_multi_slice_candidate_training_dataset(
    *,
    data_slices: tuple[CandidateDataSliceConfig, ...],
    candidate: dict[str, Any],
    max_bars: int,
    data_source: str,
) -> CandidateTrainingDataset:
    if not data_slices:
        raise ValueError("at least one data slice is required")
    if len(data_slices) > MAX_CANDIDATE_DATA_SLICES:
        raise ValueError(f"data_slices must be <= {MAX_CANDIDATE_DATA_SLICES}")
    lookback = _candidate_lookback(candidate)
    feature_set = _candidate_feature_set(candidate)
    features: list[tuple[float, ...]] = []
    labels: list[int] = []
    summaries: list[dict[str, Any]] = []
    feature_names: tuple[str, ...] | None = None
    market: str | None = None
    timeframe: Timeframe | None = None
    bars_seen = 0
    symbols: list[str] = []
    for data_slice in data_slices:
        bars = load_yahoo_intraday_1m_bars(
            data_slice.yahoo_snapshot,
            symbol=data_slice.symbol,
            max_bars=max_bars,
        )
        dataset = build_candidate_training_dataset(
            bars,
            lookback=lookback,
            data_source=str(data_slice.yahoo_snapshot),
            feature_set=feature_set,
        )
        if feature_names is None:
            feature_names = dataset.feature_names
            market = dataset.market
            timeframe = dataset.timeframe
        if dataset.feature_names != feature_names:
            raise ValueError("multi-slice feature names must match")
        if dataset.lookback != lookback:
            raise ValueError("multi-slice lookback must match")
        if dataset.market != market or dataset.timeframe != timeframe:
            raise ValueError("multi-slice market and timeframe must match")
        features.extend(dataset.features)
        labels.extend(dataset.labels)
        bars_seen += dataset.bars_seen
        symbols.append(dataset.symbol)
        summaries.append(
            _source_slice_summary(
                slice_id=data_slice.slice_id,
                yahoo_snapshot=data_slice.yahoo_snapshot,
                symbol=dataset.symbol,
                dataset=dataset,
                bars_seen=dataset.bars_seen,
                examples_seen=len(dataset.labels),
                data_quality=_compact_data_quality_summary(bars),
            )
        )
    return CandidateTrainingDataset(
        features=tuple(features),
        labels=tuple(labels),
        feature_names=feature_names or _feature_names(feature_set),
        symbol=_aggregate_symbol(symbols),
        market=market or "",
        timeframe=timeframe or Timeframe.M1,
        data_source=data_source,
        bars_seen=bars_seen,
        lookback=lookback,
        source_slices=tuple(summaries),
    )


def _with_source_slices(
    dataset: CandidateTrainingDataset,
    source_slices: tuple[dict[str, Any], ...],
) -> CandidateTrainingDataset:
    return CandidateTrainingDataset(
        features=dataset.features,
        labels=dataset.labels,
        feature_names=dataset.feature_names,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        data_source=dataset.data_source,
        bars_seen=dataset.bars_seen,
        lookback=dataset.lookback,
        source_slices=source_slices,
        feature_preprocessing=dataset.feature_preprocessing,
        feature_normalization=dataset.feature_normalization,
    )


def _empty_dataset(
    *,
    data_source: str,
    lookback: int,
    feature_set: str,
    source_slices: tuple[dict[str, Any], ...],
) -> CandidateTrainingDataset:
    return CandidateTrainingDataset(
        features=(),
        labels=(),
        feature_names=_feature_names(feature_set),
        symbol="",
        market="",
        timeframe=Timeframe.M1,
        data_source=data_source,
        bars_seen=0,
        lookback=lookback,
        source_slices=source_slices,
        feature_preprocessing=DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
        feature_normalization=None,
    )


def _source_slice_summary(
    *,
    slice_id: str,
    yahoo_snapshot: Path,
    symbol: str,
    dataset: CandidateTrainingDataset | None,
    bars_seen: int | None = None,
    examples_seen: int | None = None,
    data_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "slice_id": slice_id,
        "yahoo_snapshot": str(yahoo_snapshot),
        "symbol": symbol.upper(),
        "market": None if dataset is None else dataset.market,
        "timeframe": None if dataset is None else dataset.timeframe,
        "bars_seen": dataset.bars_seen if dataset is not None else bars_seen or 0,
        "examples_seen": (
            len(dataset.labels)
            if dataset is not None
            else examples_seen
            if examples_seen is not None
            else 0
        ),
        "feature_names": None if dataset is None else dataset.feature_names,
    }
    if data_quality is not None:
        summary["data_quality"] = data_quality
    return summary


def _compact_data_quality_summary(bars: list[Bar] | tuple[Bar, ...]) -> dict[str, Any]:
    report = assess_bar_quality(tuple(bars))
    warning_codes = Counter(warning.code for warning in report.warnings)
    return {
        "bars_seen": report.bars_seen,
        "warning_count": report.warning_count,
        "blocks_research": report.blocks_research,
        "warning_codes": dict(sorted(warning_codes.items())),
    }


def _source_slices_from_configs(
    data_slices: tuple[CandidateDataSliceConfig, ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        _source_slice_summary(
            slice_id=data_slice.slice_id,
            yahoo_snapshot=data_slice.yahoo_snapshot,
            symbol=data_slice.symbol,
            dataset=None,
        )
        for data_slice in data_slices
    )


def _aggregate_symbol(symbols: list[str]) -> str:
    unique = tuple(dict.fromkeys(symbol.upper() for symbol in symbols))
    if len(unique) == 1:
        return unique[0]
    return "MULTI"


def _run_torch_cuda_candidate_training(
    dataset: CandidateTrainingDataset,
    candidate: dict[str, Any],
    model_artifact: Path,
    config: CandidateTrainingConfig,
) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch CUDA is not available")
    torch.manual_seed(29)
    device = torch.device("cuda")
    x = torch.tensor(dataset.features, dtype=torch.float32, device=device)
    y = torch.tensor(dataset.labels, dtype=torch.float32, device=device).view(-1, 1)
    model = torch.nn.Sequential(
        torch.nn.Linear(len(dataset.feature_names), config.hidden_units),
        torch.nn.ReLU(),
        torch.nn.Linear(config.hidden_units, 1),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    with torch.no_grad():
        initial_loss = loss_fn(model(x), y)
    epochs_run = 0
    steps_run = 0
    for epoch in range(config.max_epochs):
        optimizer.zero_grad()
        logits = model(x)
        loss = loss_fn(logits, y)
        loss.backward()
        optimizer.step()
        epochs_run = epoch + 1
        steps_run += 1
        if steps_run >= config.max_steps:
            break
    torch.cuda.synchronize()
    with torch.no_grad():
        final_logits = model(x)
        final_loss = loss_fn(final_logits, y)
        predictions = (torch.sigmoid(final_logits) >= 0.5).float()
        accuracy = (predictions == y).float().mean()
    model_artifact.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "schema_version": SCHEMA_VERSION,
            "model_kind": "tiny_mlp_direction_v0",
            "candidate_experiment_id": candidate.get("candidate_experiment_id"),
            "candidate_parameters": candidate.get("candidate_parameters") or {},
            "feature_names": dataset.feature_names,
            "feature_preprocessing": dataset.feature_preprocessing,
            "feature_normalization": dataset.feature_normalization,
            "preprocessing_axis": _preprocessing_axis_payload(dataset.feature_preprocessing),
            "hidden_units": config.hidden_units,
            "weight_decay": config.weight_decay,
            "state_dict": model.state_dict(),
        },
        model_artifact,
    )
    return {
        "backend": "torch",
        "operation": "tiny_mlp_next_bar_direction",
        "device": torch.cuda.get_device_name(device),
        "epochs_run": epochs_run,
        "steps_run": steps_run,
        "examples_seen": len(dataset.labels),
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "feature_preprocessing": dataset.feature_preprocessing,
        "feature_normalization": dataset.feature_normalization,
        "preprocessing_axis": _preprocessing_axis_payload(dataset.feature_preprocessing),
        "hidden_units": config.hidden_units,
        "weight_decay": config.weight_decay,
        "initial_loss": f"{initial_loss.item():.6f}",
        "final_loss": f"{final_loss.item():.6f}",
        "accuracy": f"{accuracy.item():.6f}",
        "model_artifact": str(model_artifact),
        "candidate_experiment_id": candidate.get("candidate_experiment_id"),
    }


def _candidate_training_payload(
    result: BoundedCandidateTrainingResult,
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
            "source_slices": result.source_slices,
            "max_epochs": result.max_epochs,
            "max_steps": result.max_steps,
            "hidden_units": result.hidden_units,
            "model_axis": _model_axis_payload(result.hidden_units),
            "weight_decay": result.weight_decay,
            "regularization_axis": _regularization_axis_payload(result.weight_decay),
            "feature_preprocessing": result.feature_preprocessing,
            "preprocessing_axis": _preprocessing_axis_payload(result.feature_preprocessing),
            "feature_normalization": result.feature_normalization,
            "metrics": result.metrics,
            "artifacts": {
                "metrics": str(result.metrics_artifact),
                "model": None if result.model_artifact is None else str(result.model_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _model_axis_payload(hidden_units: int) -> dict[str, Any]:
    return {
        "axis": "hidden_units",
        "hidden_units": hidden_units,
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _regularization_axis_payload(weight_decay: float) -> dict[str, Any]:
    return {
        "axis": "weight_decay",
        "weight_decay": weight_decay,
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _preprocessing_axis_payload(feature_preprocessing: str) -> dict[str, Any]:
    return {
        "axis": "feature_preprocessing",
        "feature_preprocessing": feature_preprocessing,
        "descriptive_only": True,
        "promotion_gate": False,
    }


def build_feature_normalization(
    dataset: CandidateTrainingDataset,
    *,
    feature_preprocessing: str,
) -> dict[str, Any]:
    if feature_preprocessing not in SUPPORTED_CANDIDATE_FEATURE_PREPROCESSING:
        raise ValueError(
            "feature_preprocessing must be one of "
            f"{SUPPORTED_CANDIDATE_FEATURE_PREPROCESSING}"
        )
    feature_names = tuple(dataset.feature_names)
    if feature_preprocessing == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
        return _feature_normalization_payload(
            mode=DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
            feature_names=feature_names,
            means=(),
            scales=(),
            zero_scale_feature_names=(),
        )
    if not dataset.features:
        means = tuple(0.0 for _ in feature_names)
        scales = tuple(1.0 for _ in feature_names)
        return _feature_normalization_payload(
            mode=CANDIDATE_FEATURE_STANDARDIZATION,
            feature_names=feature_names,
            means=means,
            scales=scales,
            zero_scale_feature_names=feature_names,
        )
    width = len(feature_names)
    if any(len(row) != width for row in dataset.features):
        raise ValueError("feature rows must match feature_names length")
    columns = tuple(tuple(row[index] for row in dataset.features) for index in range(width))
    means = tuple(sum(column) / len(column) for column in columns)
    scales: list[float] = []
    zero_scale_feature_names: list[str] = []
    for name, column, mean in zip(feature_names, columns, means, strict=True):
        variance = sum((value - mean) ** 2 for value in column) / len(column)
        scale = math.sqrt(max(variance, 0.0))
        if not math.isfinite(scale) or scale <= FEATURE_STANDARDIZATION_SCALE_FLOOR:
            scale = 1.0
            zero_scale_feature_names.append(name)
        scales.append(scale)
    return _feature_normalization_payload(
        mode=CANDIDATE_FEATURE_STANDARDIZATION,
        feature_names=feature_names,
        means=means,
        scales=tuple(scales),
        zero_scale_feature_names=tuple(zero_scale_feature_names),
    )


def apply_feature_normalization(
    dataset: CandidateTrainingDataset,
    *,
    feature_normalization: dict[str, Any],
) -> CandidateTrainingDataset:
    mode = str(feature_normalization.get("mode") or DEFAULT_CANDIDATE_FEATURE_PREPROCESSING)
    if mode == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
        return _with_feature_preprocessing(
            dataset,
            feature_preprocessing=mode,
            feature_normalization=feature_normalization,
        )
    _validate_feature_normalization_payload(feature_normalization, dataset.feature_names)
    means = tuple(float(value) for value in feature_normalization["means"])
    scales = tuple(float(value) for value in feature_normalization["scales"])
    transformed = tuple(
        tuple(
            (value - mean) / scale
            for value, mean, scale in zip(row, means, scales, strict=True)
        )
        for row in dataset.features
    )
    return CandidateTrainingDataset(
        features=transformed,
        labels=dataset.labels,
        feature_names=dataset.feature_names,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        data_source=dataset.data_source,
        bars_seen=dataset.bars_seen,
        lookback=dataset.lookback,
        source_slices=dataset.source_slices,
        feature_preprocessing=mode,
        feature_normalization=feature_normalization,
    )


def apply_training_payload_feature_normalization(
    dataset: CandidateTrainingDataset,
    training_payload: dict[str, Any],
) -> CandidateTrainingDataset:
    feature_normalization = feature_normalization_from_payload(
        training_payload,
        fallback_feature_names=dataset.feature_names,
    )
    return apply_feature_normalization(
        dataset,
        feature_normalization=feature_normalization,
    )


def feature_normalization_from_payload(
    payload: dict[str, Any],
    *,
    fallback_feature_names: tuple[str, ...],
) -> dict[str, Any]:
    value = payload.get("feature_normalization")
    if value is None:
        return _feature_normalization_payload(
            mode=DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
            feature_names=fallback_feature_names,
            means=(),
            scales=(),
            zero_scale_feature_names=(),
        )
    if not isinstance(value, dict):
        raise ValueError("feature_normalization must be a JSON object")
    mode = str(value.get("mode") or DEFAULT_CANDIDATE_FEATURE_PREPROCESSING)
    if mode == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
        return _feature_normalization_payload(
            mode=DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
            feature_names=fallback_feature_names,
            means=(),
            scales=(),
            zero_scale_feature_names=(),
        )
    _validate_feature_normalization_payload(value, fallback_feature_names)
    return value


def validate_checkpoint_feature_normalization(
    *,
    checkpoint: dict[str, Any],
    training_payload: dict[str, Any],
    feature_names: tuple[str, ...],
) -> None:
    payload_normalization = feature_normalization_from_payload(
        training_payload,
        fallback_feature_names=feature_names,
    )
    checkpoint_value = checkpoint.get("feature_normalization")
    checkpoint_mode = str(
        checkpoint.get("feature_preprocessing") or DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    )
    if checkpoint_value is None:
        if payload_normalization["mode"] != DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
            raise ValueError(
                "model checkpoint is missing feature_normalization for "
                f"{payload_normalization['mode']}"
            )
        return
    if not isinstance(checkpoint_value, dict):
        raise ValueError("model checkpoint feature_normalization must be a JSON object")
    if checkpoint_mode != str(checkpoint_value.get("mode")):
        raise ValueError("model checkpoint feature preprocessing metadata is inconsistent")
    if checkpoint_mode == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
        if payload_normalization["mode"] != DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
            raise ValueError("training metrics and model checkpoint feature preprocessing differ")
        return
    _validate_feature_normalization_payload(checkpoint_value, feature_names)
    if checkpoint_value.get("signature") != payload_normalization.get("signature"):
        raise ValueError("training metrics and model checkpoint feature normalization differ")


def _with_feature_preprocessing(
    dataset: CandidateTrainingDataset,
    *,
    feature_preprocessing: str,
    feature_normalization: dict[str, Any],
) -> CandidateTrainingDataset:
    return CandidateTrainingDataset(
        features=dataset.features,
        labels=dataset.labels,
        feature_names=dataset.feature_names,
        symbol=dataset.symbol,
        market=dataset.market,
        timeframe=dataset.timeframe,
        data_source=dataset.data_source,
        bars_seen=dataset.bars_seen,
        lookback=dataset.lookback,
        source_slices=dataset.source_slices,
        feature_preprocessing=feature_preprocessing,
        feature_normalization=feature_normalization,
    )


def _feature_normalization_payload(
    *,
    mode: str,
    feature_names: tuple[str, ...],
    means: tuple[float, ...],
    scales: tuple[float, ...],
    zero_scale_feature_names: tuple[str, ...],
) -> dict[str, Any]:
    applied = mode != DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    payload = {
        "mode": mode,
        "feature_names": feature_names,
        "means": means,
        "scales": scales,
        "zero_scale_feature_names": zero_scale_feature_names,
        "scale_floor": FEATURE_STANDARDIZATION_SCALE_FLOOR,
        "applied": applied,
        "descriptive_only": True,
        "promotion_gate": False,
    }
    payload["signature"] = _feature_normalization_signature(payload)
    return payload


def _feature_normalization_signature(payload: dict[str, Any]) -> str:
    mode = str(payload.get("mode") or DEFAULT_CANDIDATE_FEATURE_PREPROCESSING)
    feature_names = tuple(str(name) for name in payload.get("feature_names", ()))
    means = tuple(f"{float(value):.12g}" for value in payload.get("means", ()))
    scales = tuple(f"{float(value):.12g}" for value in payload.get("scales", ()))
    signature_payload = {
        "mode": mode,
        "feature_names": feature_names,
        "means": means,
        "scales": scales,
    }
    encoded = json.dumps(signature_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_feature_normalization_payload(
    payload: dict[str, Any],
    feature_names: tuple[str, ...],
) -> None:
    mode = str(payload.get("mode") or DEFAULT_CANDIDATE_FEATURE_PREPROCESSING)
    if mode not in SUPPORTED_CANDIDATE_FEATURE_PREPROCESSING:
        raise ValueError(f"unsupported feature preprocessing: {mode}")
    raw_feature_names = payload.get("feature_names")
    if not isinstance(raw_feature_names, list | tuple):
        raise ValueError("feature_normalization feature_names are required")
    stored_feature_names = tuple(str(name) for name in raw_feature_names)
    if stored_feature_names != feature_names:
        raise ValueError(
            "feature_normalization feature names mismatch: "
            f"{stored_feature_names} != {feature_names}"
        )
    raw_means = payload.get("means")
    raw_scales = payload.get("scales")
    if not isinstance(raw_means, list | tuple) or not isinstance(raw_scales, list | tuple):
        raise ValueError("feature_normalization means and scales are required")
    if mode == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING:
        if raw_means or raw_scales:
            raise ValueError("none feature preprocessing must not carry statistics")
        return
    if len(raw_means) != len(feature_names) or len(raw_scales) != len(feature_names):
        raise ValueError("feature_normalization statistics must match feature count")
    means = tuple(float(value) for value in raw_means)
    scales = tuple(float(value) for value in raw_scales)
    if any(not math.isfinite(value) for value in (*means, *scales)):
        raise ValueError("feature_normalization statistics must be finite")
    if any(scale <= 0 for scale in scales):
        raise ValueError("feature_normalization scales must be positive")
    expected_signature = _feature_normalization_signature(payload)
    if payload.get("signature") != expected_signature:
        raise ValueError("feature_normalization signature mismatch")


def detect_gpu_readiness() -> GpuReadiness:
    checked_at = datetime.now(UTC)
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GpuReadiness(available=False, detail=str(exc), checked_at=checked_at)
    detail = completed.stdout.strip() or completed.stderr.strip()
    return GpuReadiness(
        available=completed.returncode == 0 and bool(completed.stdout.strip()),
        detail=detail,
        checked_at=checked_at,
    )


def load_yahoo_intraday_1m_bars(
    path: Path,
    *,
    symbol: str | None = None,
    market: str = "US",
    max_bars: int = 120,
) -> list[Bar]:
    if max_bars <= 0:
        raise ValueError("max_bars must be positive")
    selected_symbol = symbol.upper() if symbol else None
    bars: list[Bar] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_symbol = str(row["symbol"]).upper()
            if selected_symbol is None:
                selected_symbol = row_symbol
            if row_symbol != selected_symbol:
                if bars:
                    break
                continue
            bars.append(
                Bar(
                    symbol=row_symbol,
                    market=market,
                    timeframe=Timeframe.M1,
                    start_ts=_parse_utc(row["timestamp_utc"]),
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                    complete=True,
                )
            )
            if len(bars) >= max_bars:
                break
    if not bars:
        raise ValueError("no bars loaded from yahoo intraday file")
    return bars


def _read_candidate_artifact(candidate_artifact: Path | None) -> dict[str, Any]:
    if candidate_artifact is None:
        return {}
    payload = json.loads(candidate_artifact.read_text(encoding="utf-8"))
    return {
        "candidate_experiment_id": payload.get("candidate_experiment_id"),
        "candidate_parameters": payload.get("candidate_parameters"),
    }


def _available_gpu_backends() -> tuple[str, ...]:
    return tuple(
        backend
        for backend in OPTIONAL_CANDIDATE_TRAINING_BACKENDS
        if importlib.util.find_spec(backend) is not None
    )


def _selected_backend() -> str | None:
    if importlib.util.find_spec("torch") is not None:
        return "torch"
    return None


def _reject_repo_artifact_path(artifact_root: Path, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    resolved_artifact = artifact_root.resolve()
    resolved_repo = repo_root.resolve()
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if resolved_repo == docker_repo_root and (
            resolved_artifact == docker_artifact_root
            or docker_artifact_root in resolved_artifact.parents
        ):
            return
    if resolved_artifact == resolved_repo or resolved_repo in resolved_artifact.parents:
        raise ValueError("artifact_root must be outside the Git workspace")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _candidate_lookback(candidate: dict[str, Any]) -> int:
    parameters = candidate.get("candidate_parameters")
    if not isinstance(parameters, dict):
        return 3
    value = parameters.get("lookback", 3)
    try:
        lookback = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, lookback)


def _candidate_feature_set(candidate: dict[str, Any]) -> str:
    parameters = candidate.get("candidate_parameters")
    if not isinstance(parameters, dict):
        return CORE_FEATURE_SET_ID
    feature_set = str(parameters.get("feature_set") or CORE_FEATURE_SET_ID)
    if feature_set not in SUPPORTED_CANDIDATE_FEATURE_SETS:
        raise ValueError(f"unsupported candidate feature_set: {feature_set}")
    return feature_set


def _candidate_feature_set_or_default(candidate: dict[str, Any]) -> str:
    try:
        return _candidate_feature_set(candidate)
    except ValueError:
        return CORE_FEATURE_SET_ID


def _relative_change(numerator: Any, denominator: Any) -> float:
    base = float(denominator)
    if base == 0:
        return 0.0
    return (float(numerator) / base) - 1.0


def _feature_vector(
    *,
    current: Bar,
    prior: Bar,
    anchor: Bar,
    feature_set: str,
) -> tuple[float, ...]:
    base = (
        _relative_change(current.close, anchor.close),
        _relative_change(current.close, prior.close),
        _relative_change(current.high, current.low),
        _relative_change(current.volume + 1, prior.volume + 1),
    )
    if feature_set == CORE_FEATURE_SET_ID:
        return base
    if feature_set == CORE_PLUS_BAR_POSITION_FEATURE_SET_ID:
        return (*base, _close_position_in_bar(current))
    if feature_set == CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID:
        return (
            *base,
            _close_position_in_bar(current),
            _range_expansion(current=current, prior=prior),
            _bar_body_return(current),
        )
    if feature_set == CORE_PLUS_ENTRY_ADVERSE_FEATURE_SET_ID:
        return (
            *base,
            _close_position_in_bar(current),
            _range_expansion(current=current, prior=prior),
            _bar_body_return(current),
            _upper_wick_share(current),
            _low_vs_prior_low_return(current=current, prior=prior),
        )
    raise ValueError(f"unsupported candidate feature_set: {feature_set}")


def _close_position_in_bar(bar: Bar) -> float:
    span = float(bar.high - bar.low)
    if span == 0:
        return 0.5
    position = float(bar.close - bar.low) / span
    return min(max(position, 0.0), 1.0)


def _range_expansion(*, current: Bar, prior: Bar) -> float:
    return _relative_change(current.high - current.low, prior.high - prior.low)


def _bar_body_return(bar: Bar) -> float:
    return _relative_change(bar.close, bar.open)


def _upper_wick_share(bar: Bar) -> float:
    span = float(bar.high - bar.low)
    if span == 0:
        return 0.0
    upper = float(bar.high - max(bar.open, bar.close)) / span
    return min(max(upper, 0.0), 1.0)


def _low_vs_prior_low_return(*, current: Bar, prior: Bar) -> float:
    return _relative_change(current.low, prior.low)


def _feature_names(feature_set: str = CORE_FEATURE_SET_ID) -> tuple[str, ...]:
    base = (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
    )
    if feature_set == CORE_FEATURE_SET_ID:
        return base
    if feature_set == CORE_PLUS_BAR_POSITION_FEATURE_SET_ID:
        return (*base, "close_position_in_bar")
    if feature_set == CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID:
        return (
            *base,
            "close_position_in_bar",
            "range_expansion",
            "bar_body_return",
        )
    if feature_set == CORE_PLUS_ENTRY_ADVERSE_FEATURE_SET_ID:
        return (
            *base,
            "close_position_in_bar",
            "range_expansion",
            "bar_body_return",
            "upper_wick_share",
            "low_vs_prior_low_return",
        )
    raise ValueError(f"unsupported candidate feature_set: {feature_set}")


def _validate_positive_cap(value: int, *, field_name: str, ceiling: int) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    if value > ceiling:
        raise ValueError(f"{field_name} must be <= {ceiling}")


def _validate_non_negative_float_cap(
    value: float,
    *,
    field_name: str,
    ceiling: float,
) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    if value > ceiling:
        raise ValueError(f"{field_name} must be <= {ceiling}")


def parse_candidate_data_slices(
    values: list[str] | None,
) -> tuple[CandidateDataSliceConfig, ...]:
    if not values:
        return ()
    slices: list[CandidateDataSliceConfig] = []
    for ordinal, value in enumerate(values, start=1):
        slice_id: str | None = None
        raw_value = value
        prefix, separator, rest = value.partition("=")
        if separator and prefix and not any(part in prefix for part in ("\\", "/", ":")):
            slice_id = prefix
            raw_value = rest
        path_text, separator, symbol = raw_value.rpartition(":")
        if not separator or not path_text or not symbol:
            raise ValueError("data slices must use [ID=]SNAPSHOT:SYMBOL format")
        symbol = symbol.upper()
        slices.append(
            CandidateDataSliceConfig(
                slice_id=slice_id or f"s{ordinal:02d}_{symbol}",
                yahoo_snapshot=Path(path_text),
                symbol=symbol,
            )
        )
    return tuple(slices)

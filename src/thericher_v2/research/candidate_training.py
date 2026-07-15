"""Bounded GPU candidate training for the research profile."""

from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import SampleBarProvider
from thericher_v2.serialization import to_jsonable

CandidateTrainingStatus = Literal["candidate_trained_only", "prepared_not_trained"]
DEFAULT_CANDIDATE_TRAINING_RUN_ID = "bounded-gpu-candidate-training"
MAX_CANDIDATE_TRAINING_EPOCHS = 20
MAX_CANDIDATE_TRAINING_STEPS = 1024
MAX_CANDIDATE_TRAINING_BARS = 512
OPTIONAL_CANDIDATE_TRAINING_BACKENDS = ("torch",)


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
    hidden_units: int = 8
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
        if self.hidden_units <= 0:
            raise ValueError("hidden_units must be positive")


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
    max_epochs: int
    max_steps: int
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
    dataset = _load_dataset(
        config=config,
        candidate=candidate,
        yahoo_snapshot=yahoo_snapshot,
        symbol=symbol,
    )

    result = _run_candidate_training_result(
        config=config,
        candidate_artifact=candidate_artifact,
        candidate=candidate,
        dataset=dataset,
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
    gpu: GpuReadiness,
    available_backends: tuple[str, ...],
    selected_backend: str | None,
    model_artifact: Path,
    metrics_artifact: Path,
    trainer_runner: CandidateTrainerRunner | None,
) -> BoundedCandidateTrainingResult:
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
    runner = trainer_runner or _run_torch_cuda_candidate_training
    try:
        metrics = runner(dataset, candidate, model_artifact, config)
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
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
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
        max_epochs=config.max_epochs,
        max_steps=config.max_steps,
        metrics={},
        metrics_artifact=metrics_artifact,
    )


def _load_dataset(
    *,
    config: CandidateTrainingConfig,
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
        provider = SampleBarProvider.trending_1m(count=config.max_bars, seed=29)
        bars = list(provider.base_bars)
        data_source = "deterministic_sample"
    lookback = _candidate_lookback(candidate)
    return build_candidate_training_dataset(
        bars,
        lookback=lookback,
        data_source=data_source,
    )


def build_candidate_training_dataset(
    bars: list[Bar],
    *,
    lookback: int,
    data_source: str,
) -> CandidateTrainingDataset:
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    ordered = sorted(bars, key=lambda bar: bar.start_ts)
    if not ordered:
        return CandidateTrainingDataset(
            features=(),
            labels=(),
            feature_names=_feature_names(),
            symbol="",
            market="",
            timeframe=Timeframe.M1,
            data_source=data_source,
            bars_seen=0,
            lookback=lookback,
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
            (
                _relative_change(current.close, anchor.close),
                _relative_change(current.close, prior.close),
                _relative_change(current.high, current.low),
                _relative_change(current.volume + 1, prior.volume + 1),
            )
        )
        labels.append(1 if next_bar.close > current.close else 0)
    return CandidateTrainingDataset(
        features=tuple(features),
        labels=tuple(labels),
        feature_names=_feature_names(),
        symbol=first.symbol,
        market=first.market,
        timeframe=first.timeframe,
        data_source=data_source,
        bars_seen=len(ordered),
        lookback=lookback,
    )


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
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
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
            "hidden_units": config.hidden_units,
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
        "hidden_units": config.hidden_units,
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
            "max_epochs": result.max_epochs,
            "max_steps": result.max_steps,
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


def _relative_change(numerator: Any, denominator: Any) -> float:
    base = float(denominator)
    if base == 0:
        return 0.0
    return (float(numerator) / base) - 1.0


def _feature_names() -> tuple[str, ...]:
    return (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
    )


def _validate_positive_cap(value: int, *, field_name: str, ceiling: int) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    if value > ceiling:
        raise ValueError(f"{field_name} must be <= {ceiling}")

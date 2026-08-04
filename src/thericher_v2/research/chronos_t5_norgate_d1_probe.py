"""Research-only local Chronos-T5 probe over the frozen Norgate D1 panel.

The module deliberately separates a one-time public model acquisition from a
network-disabled, local-only inference probe.  It is not a trading model,
ranking surface, or Paper input.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from thericher_v2.research.norgate_broad_representation import (
    ObservedReturnDataset,
    load_frozen_observed_return_dataset,
)

CHRONOS_T5_NORGATE_D1_PROBE_ID = "chronos-t5-tiny-norgate-d1-probe-v1"
CHRONOS_T5_PACKAGE_VERSION = "2.2.2"
CHRONOS_T5_MODEL_ID = "amazon/chronos-t5-tiny"
CHRONOS_T5_MODEL_REVISION = "a4a27cf5c9a8b21a2bb935eef158344dc10ff9df"
CHRONOS_T5_MODEL_LICENSE = "Apache-2.0"
CHRONOS_T5_MODEL_SOURCE_URL = "https://huggingface.co/amazon/chronos-t5-tiny"
CHRONOS_T5_CONTEXT_LENGTH = 39
CHRONOS_T5_PREDICTION_LENGTH = 1
CHRONOS_T5_FORECAST_SAMPLE_COUNT = 20
CHRONOS_T5_CPU_CASE_COUNT = 16
CHRONOS_T5_CUDA_CASE_COUNT = 1024
CHRONOS_T5_CUDA_BATCH_SIZE = 32
DEFAULT_MODEL_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

_SAFE_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,120}", re.ASCII)
_ALLOWED_MODEL_FILES = frozenset(
    {
        ".gitattributes",
        "README.md",
        "config.json",
        "generation_config.json",
        "model.safetensors",
        "special_tokens_map.json",
        "spiece.model",
        "tokenizer.json",
        "tokenizer_config.json",
    }
)
_REQUIRED_MODEL_FILES = frozenset({"config.json", "model.safetensors"})

Phase = Literal["cpu", "cuda"]
Forecast = Callable[[Any, Phase], Any]
Downloader = Callable[..., str]


@dataclass(frozen=True, slots=True)
class ChronosT5LocalModel:
    """Verified external-only model files and their source-safe manifest."""

    directory: Path
    manifest_path: Path
    manifest_sha256: str
    file_sha256: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ChronosT5ProbeContract:
    """Immutable, non-promoting inference contract for one local source."""

    path: Path
    sha256: str
    run_directory: Path
    model_manifest_sha256: str
    dataset_hash: str
    dataset_manifest_hash: str
    development_window_sha256: str
    diagnostic_window_sha256: str


@dataclass(frozen=True, slots=True)
class ChronosT5ProbeRun:
    """A source-safe CPU/CUDA probe result without stored predictions."""

    phase: Phase
    status: Literal["completed", "cuda_unavailable"]
    summary_path: Path
    summary_sha256: str
    contract_sha256: str


def default_chronos_t5_tiny_directory(
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
) -> Path:
    return (
        Path(artifact_root)
        / "foundation-models"
        / "chronos-t5-tiny"
        / CHRONOS_T5_MODEL_REVISION
    )


def prepare_chronos_t5_tiny_local_model(
    *,
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
    repository_root: Path | str,
    downloader: Downloader | None = None,
) -> ChronosT5LocalModel:
    """Fetch only official safe model files into the external artifact root."""

    root = _external_artifact_root(artifact_root, repository_root)
    directory = default_chronos_t5_tiny_directory(root)
    manifest_path = directory / "model-manifest.json"
    if manifest_path.is_file():
        return _load_verified_local_model(
            directory,
            artifact_root=root,
            repository_root=repository_root,
        )
    if directory.exists():
        raise ValueError("Chronos model directory exists without a verified manifest")
    directory.mkdir(parents=True, exist_ok=False)
    try:
        (downloader or _snapshot_download)(
            repo_id=CHRONOS_T5_MODEL_ID,
            revision=CHRONOS_T5_MODEL_REVISION,
            local_dir=str(directory),
            allow_patterns=tuple(sorted(_ALLOWED_MODEL_FILES)),
        )
        _remove_download_metadata(directory)
        records = _verified_model_file_records(directory)
        payload = {
            "kind": "chronos_t5_tiny_local_model_manifest",
            "model_id": CHRONOS_T5_MODEL_ID,
            "model_revision": CHRONOS_T5_MODEL_REVISION,
            "runtime_package": {
                "name": "chronos-forecasting",
                "version": CHRONOS_T5_PACKAGE_VERSION,
            },
            "license": CHRONOS_T5_MODEL_LICENSE,
            "source_url": CHRONOS_T5_MODEL_SOURCE_URL,
            "safe_serialization": True,
            "files": records,
            "scope": {
                "research_only": True,
                "pretraining_scope": "not_disclosed",
                "paper_input_eligible": False,
                "promotion_eligible": False,
            },
        }
        _write_json_new(manifest_path, payload)
    except Exception:
        _remove_empty_or_partial_directory(directory)
        raise
    return _load_verified_local_model(
        directory,
        artifact_root=root,
        repository_root=repository_root,
    )


def load_verified_chronos_t5_tiny_local_model(
    *,
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
    repository_root: Path | str,
) -> ChronosT5LocalModel:
    """Reattest existing model files without any network or credential path."""

    root = _external_artifact_root(artifact_root, repository_root)
    return _load_verified_local_model(
        default_chronos_t5_tiny_directory(root),
        artifact_root=root,
        repository_root=repository_root,
    )


def freeze_chronos_t5_norgate_d1_probe(
    dataset: ObservedReturnDataset,
    model: ChronosT5LocalModel,
    *,
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
    repository_root: Path | str,
    run_id: str = CHRONOS_T5_NORGATE_D1_PROBE_ID,
    code_revision: str,
) -> ChronosT5ProbeContract:
    """Freeze a source-safe zero-shot forecast contract before evaluation."""

    _require_run_id(run_id)
    _require_sha256(code_revision, "code revision")
    _validate_dataset(dataset)
    root = _external_artifact_root(artifact_root, repository_root)
    run_directory = root / "research" / CHRONOS_T5_NORGATE_D1_PROBE_ID / run_id
    contract_path = run_directory / "contract.json"
    payload = {
        "kind": CHRONOS_T5_NORGATE_D1_PROBE_ID,
        "model": {
            "id": CHRONOS_T5_MODEL_ID,
            "revision": CHRONOS_T5_MODEL_REVISION,
            "manifest_sha256": model.manifest_sha256,
            "runtime_package": {
                "name": "chronos-forecasting",
                "version": CHRONOS_T5_PACKAGE_VERSION,
            },
            "pretraining_scope": "not_disclosed",
            "fine_tuning": False,
        },
        "dataset": {
            "id": dataset.dataset_id,
            "sha256": dataset.dataset_hash,
            "manifest_sha256": dataset.manifest_hash,
            "selected_symbol_count": dataset.selected_symbol_count,
            "development_window_sha256": dataset.development_window_sha256,
            "diagnostic_window_sha256": dataset.diagnostic_window_sha256,
        },
        "target": {
            "kind": "one_step_observed_close_to_close_return",
            "context_length": CHRONOS_T5_CONTEXT_LENGTH,
            "prediction_length": CHRONOS_T5_PREDICTION_LENGTH,
            "availability": "the final observed return in each frozen window",
        },
        "split": {
            "development": "existing target-free development return windows",
            "purge": "existing non-overlapping return-index gap",
            "validation": "existing target-free diagnostic return windows",
        },
        "baselines": ["zero_return", "last_observed_return"],
        "metrics": ["mae", "rmse", "directional_accuracy"],
        "kill_test": "reversed-target-order directional null",
        "compute": {
            "cpu_case_count": CHRONOS_T5_CPU_CASE_COUNT,
            "cuda_case_count": CHRONOS_T5_CUDA_CASE_COUNT,
            "cuda_batch_size": CHRONOS_T5_CUDA_BATCH_SIZE,
            "forecast_sample_count": CHRONOS_T5_FORECAST_SAMPLE_COUNT,
            "cuda_requires_matching_cpu_summary": True,
        },
        "code_revision": code_revision,
        "scope": _non_promoting_scope(),
        "limitations": [
            "Norgate panel is current-listing and non-PIT.",
            "Norgate adjustment, corporate-action, and availability semantics are unverified.",
            "Chronos pretraining corpus period and instrument scope are not disclosed.",
            "The result is an offline forecast diagnostic, not a KIS-reconstructible input.",
        ],
    }
    _write_json_new(contract_path, payload)
    return ChronosT5ProbeContract(
        path=contract_path,
        sha256=_sha256_json(payload),
        run_directory=run_directory,
        model_manifest_sha256=model.manifest_sha256,
        dataset_hash=dataset.dataset_hash,
        dataset_manifest_hash=dataset.manifest_hash,
        development_window_sha256=dataset.development_window_sha256,
        diagnostic_window_sha256=dataset.diagnostic_window_sha256,
    )


def run_chronos_t5_norgate_d1_probe(
    contract: ChronosT5ProbeContract,
    dataset: ObservedReturnDataset,
    model: ChronosT5LocalModel,
    *,
    phase: Phase,
    forecast: Forecast | None = None,
) -> ChronosT5ProbeRun:
    """Run one bounded local-only CPU or CUDA zero-shot diagnostic."""

    _validate_contract(contract, dataset, model)
    if phase not in {"cpu", "cuda"}:
        raise ValueError("Chronos probe phase is invalid")
    if phase == "cuda":
        _verify_matching_cpu_summary(contract)
        if not _cuda_available():
            return _write_unavailable_summary(contract)
    summary_path = contract.run_directory / f"{phase}-summary.json"
    if summary_path.exists():
        return _read_existing_run(summary_path, contract=contract, phase=phase)
    windows = dataset.development_windows if phase == "cpu" else dataset.diagnostic_windows
    case_count = CHRONOS_T5_CPU_CASE_COUNT if phase == "cpu" else CHRONOS_T5_CUDA_CASE_COUNT
    selected = _evenly_spaced_windows(windows, count=case_count)
    contexts, targets = _contexts_and_targets(selected)
    active_forecast = forecast or (
        lambda values, active_phase: _chronos_forecast(values, active_phase, model)
    )
    predicted = active_forecast(contexts, phase)
    prediction_values = _validated_prediction_values(predicted, expected_count=len(targets))
    payload = {
        "kind": CHRONOS_T5_NORGATE_D1_PROBE_ID,
        "status": "completed",
        "phase": phase,
        "contract_sha256": contract.sha256,
        "model_manifest_sha256": model.manifest_sha256,
        "case_count": len(targets),
        "metrics": {
            "chronos": _metrics(targets, prediction_values),
            "zero_return": _metrics(targets, _zeros_like(targets)),
            "last_observed_return": _metrics(targets, contexts[:, -1]),
        },
        "kill_test": {
            "kind": "reversed_target_order_directional_null",
            "chronos_directional_accuracy": _directional_accuracy(targets[::-1], prediction_values),
        },
        "scope": _non_promoting_scope(),
    }
    _write_json_new(summary_path, payload)
    return ChronosT5ProbeRun(
        phase=phase,
        status="completed",
        summary_path=summary_path,
        summary_sha256=_sha256_json(payload),
        contract_sha256=contract.sha256,
    )


def load_actual_chronos_t5_probe_inputs(
    *,
    artifact_root: Path | str = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path | str,
    repository_root: Path | str,
    run_id: str = CHRONOS_T5_NORGATE_D1_PROBE_ID,
    code_revision: str,
) -> tuple[ChronosT5ProbeContract, ObservedReturnDataset, ChronosT5LocalModel]:
    """Reattest all local inputs before a runner invokes the model runtime."""

    dataset = load_frozen_observed_return_dataset(
        market_data_root=Path(market_data_root),
        repo_root=Path(repository_root),
    )
    model = load_verified_chronos_t5_tiny_local_model(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    contract = freeze_chronos_t5_norgate_d1_probe(
        dataset,
        model,
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_id=run_id,
        code_revision=code_revision,
    )
    return contract, dataset, model


def _load_verified_local_model(
    directory: Path,
    *,
    artifact_root: Path,
    repository_root: Path | str,
) -> ChronosT5LocalModel:
    root = _external_artifact_root(artifact_root, repository_root)
    directory = directory.resolve()
    if not directory.is_relative_to(root) or directory.is_symlink() or not directory.is_dir():
        raise ValueError("Chronos model directory is invalid")
    manifest_path = directory / "model-manifest.json"
    payload = _read_json_object(manifest_path)
    if (
        payload.get("kind") != "chronos_t5_tiny_local_model_manifest"
        or payload.get("model_id") != CHRONOS_T5_MODEL_ID
        or payload.get("model_revision") != CHRONOS_T5_MODEL_REVISION
        or payload.get("license") != CHRONOS_T5_MODEL_LICENSE
        or payload.get("safe_serialization") is not True
    ):
        raise ValueError("Chronos model manifest is invalid")
    records = payload.get("files")
    observed_records = _verified_model_file_records(directory)
    if _model_file_record_mapping(records) != _model_file_record_mapping(observed_records):
        raise ValueError("Chronos model files changed")
    file_sha256 = {str(item["path"]): str(item["sha256"]) for item in records}
    return ChronosT5LocalModel(
        directory=directory,
        manifest_path=manifest_path,
        manifest_sha256=_sha256_json(payload),
        file_sha256=file_sha256,
    )


def _verified_model_file_records(directory: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    paths = sorted(path for path in directory.rglob("*") if path.is_file())
    for path in paths:
        relative = path.relative_to(directory).as_posix()
        if relative == "model-manifest.json":
            continue
        if path.is_symlink() or relative not in _ALLOWED_MODEL_FILES:
            raise ValueError("Chronos model contains an unsupported file")
        records.append({"path": relative, "sha256": _sha256_file(path)})
    names = {item["path"] for item in records}
    if not _REQUIRED_MODEL_FILES.issubset(names):
        raise ValueError("Chronos model safe files are incomplete")
    return records


def _model_file_record_mapping(records: object) -> dict[str, str]:
    """Validate manifest records while allowing legacy serialization order."""

    if not isinstance(records, list):
        raise ValueError("Chronos model file records are invalid")
    mapped: dict[str, str] = {}
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256"}:
            raise ValueError("Chronos model file records are invalid")
        path = record["path"]
        digest = record["sha256"]
        if (
            not isinstance(path, str)
            or path not in _ALLOWED_MODEL_FILES
            or not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or path in mapped
        ):
            raise ValueError("Chronos model file records are invalid")
        mapped[path] = digest
    return mapped


def _validate_dataset(dataset: ObservedReturnDataset) -> None:
    numpy = _numpy()
    for windows, field_name in (
        (dataset.development_windows, "development windows"),
        (dataset.diagnostic_windows, "diagnostic windows"),
    ):
        values = numpy.asarray(windows, dtype=numpy.float32)
        if (
            values.ndim != 2
            or values.shape[0] < CHRONOS_T5_CPU_CASE_COUNT
            or values.shape[1] != CHRONOS_T5_CONTEXT_LENGTH + CHRONOS_T5_PREDICTION_LENGTH
            or not numpy.isfinite(values).all()
        ):
            raise ValueError(f"Chronos {field_name} are invalid")


def _validate_contract(
    contract: ChronosT5ProbeContract,
    dataset: ObservedReturnDataset,
    model: ChronosT5LocalModel,
) -> None:
    payload = _read_json_object(contract.path)
    if (
        _sha256_json(payload) != contract.sha256
        or payload.get("kind") != CHRONOS_T5_NORGATE_D1_PROBE_ID
        or payload.get("model", {}).get("manifest_sha256") != model.manifest_sha256
        or payload.get("dataset", {}).get("sha256") != dataset.dataset_hash
        or payload.get("dataset", {}).get("manifest_sha256") != dataset.manifest_hash
        or payload.get("dataset", {}).get("development_window_sha256")
        != dataset.development_window_sha256
        or payload.get("dataset", {}).get("diagnostic_window_sha256")
        != dataset.diagnostic_window_sha256
    ):
        raise ValueError("Chronos probe contract changed")
    _validate_dataset(dataset)


def _verify_matching_cpu_summary(contract: ChronosT5ProbeContract) -> None:
    path = contract.run_directory / "cpu-summary.json"
    try:
        result = _read_existing_run(path, contract=contract, phase="cpu")
    except ValueError as error:
        raise ValueError("Chronos CUDA requires a completed matching CPU summary") from error
    if result.status != "completed":
        raise ValueError("Chronos CUDA requires a completed matching CPU summary")


def _write_unavailable_summary(contract: ChronosT5ProbeContract) -> ChronosT5ProbeRun:
    path = contract.run_directory / "cuda-summary.json"
    payload = {
        "kind": CHRONOS_T5_NORGATE_D1_PROBE_ID,
        "status": "cuda_unavailable",
        "phase": "cuda",
        "contract_sha256": contract.sha256,
        "scope": _non_promoting_scope(),
    }
    _write_json_new(path, payload)
    return ChronosT5ProbeRun(
        phase="cuda",
        status="cuda_unavailable",
        summary_path=path,
        summary_sha256=_sha256_json(payload),
        contract_sha256=contract.sha256,
    )


def _read_existing_run(
    path: Path,
    *,
    contract: ChronosT5ProbeContract,
    phase: Phase,
) -> ChronosT5ProbeRun:
    payload = _read_json_object(path)
    if (
        payload.get("kind") != CHRONOS_T5_NORGATE_D1_PROBE_ID
        or payload.get("phase") != phase
        or payload.get("contract_sha256") != contract.sha256
        or payload.get("status") not in {"completed", "cuda_unavailable"}
    ):
        raise ValueError("Chronos probe summary is invalid")
    return ChronosT5ProbeRun(
        phase=phase,
        status=payload["status"],
        summary_path=path,
        summary_sha256=_sha256_json(payload),
        contract_sha256=contract.sha256,
    )


def _evenly_spaced_windows(windows: Any, *, count: int) -> Any:
    numpy = _numpy()
    values = numpy.asarray(windows, dtype=numpy.float32)
    selection_count = min(count, values.shape[0])
    indexes = numpy.linspace(0, values.shape[0] - 1, num=selection_count, dtype=numpy.int64)
    return values[indexes]


def _contexts_and_targets(windows: Any) -> tuple[Any, Any]:
    numpy = _numpy()
    values = numpy.asarray(windows, dtype=numpy.float32)
    contexts = values[:, :CHRONOS_T5_CONTEXT_LENGTH]
    targets = values[:, CHRONOS_T5_CONTEXT_LENGTH]
    if contexts.shape[1] != CHRONOS_T5_CONTEXT_LENGTH or not numpy.isfinite(targets).all():
        raise ValueError("Chronos target geometry is invalid")
    return contexts, targets


def _chronos_forecast(contexts: Any, phase: Phase, model: ChronosT5LocalModel) -> Any:
    torch = _torch()
    if phase == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("Chronos CUDA is unavailable")
    from chronos import ChronosPipeline

    device = "cuda" if phase == "cuda" else "cpu"
    pipeline = ChronosPipeline.from_pretrained(
        str(model.directory),
        device_map=device,
        dtype=torch.bfloat16 if phase == "cuda" else torch.float32,
        local_files_only=True,
    )
    numpy = _numpy()
    batch_size = CHRONOS_T5_CUDA_BATCH_SIZE if phase == "cuda" else len(contexts)
    predicted_batches: list[Any] = []
    for start in range(0, len(contexts), batch_size):
        context_tensor = torch.tensor(
            contexts[start : start + batch_size],
            dtype=torch.float32,
        )
        forecast = pipeline.predict(
            inputs=context_tensor,
            prediction_length=CHRONOS_T5_PREDICTION_LENGTH,
            num_samples=CHRONOS_T5_FORECAST_SAMPLE_COUNT,
        )
        values = forecast.detach().to("cpu").numpy()
        if values.ndim != 3 or values.shape[0] != len(context_tensor) or values.shape[2] != 1:
            raise ValueError("Chronos forecast tensor is invalid")
        predicted_batches.append(numpy.median(values[:, :, 0], axis=1))
    return numpy.concatenate(predicted_batches)


def _validated_prediction_values(prediction: Any, *, expected_count: int) -> Any:
    numpy = _numpy()
    values = numpy.asarray(prediction, dtype=numpy.float64)
    if values.shape != (expected_count,) or not numpy.isfinite(values).all():
        raise ValueError("Chronos prediction values are invalid")
    return values


def _metrics(targets: Any, prediction: Any) -> dict[str, float]:
    numpy = _numpy()
    actual = numpy.asarray(targets, dtype=numpy.float64)
    estimate = numpy.asarray(prediction, dtype=numpy.float64)
    error = estimate - actual
    return {
        "mae": float(numpy.mean(numpy.abs(error))),
        "rmse": float(math.sqrt(float(numpy.mean(error * error)))),
        "directional_accuracy": _directional_accuracy(actual, estimate),
    }


def _directional_accuracy(targets: Any, prediction: Any) -> float:
    numpy = _numpy()
    actual = numpy.asarray(targets, dtype=numpy.float64) >= 0.0
    estimate = numpy.asarray(prediction, dtype=numpy.float64) >= 0.0
    return float(numpy.mean(actual == estimate))


def _zeros_like(values: Any) -> Any:
    return _numpy().zeros_like(values, dtype=_numpy().float64)


def _cuda_available() -> bool:
    try:
        return bool(_torch().cuda.is_available())
    except ModuleNotFoundError:
        return False


def _snapshot_download(**kwargs: object) -> str:
    from huggingface_hub import snapshot_download

    return str(snapshot_download(**kwargs))


def _external_artifact_root(artifact_root: Path | str, repository_root: Path | str) -> Path:
    root = Path(artifact_root).resolve()
    repository = Path(repository_root).resolve()
    mounted_root = root == repository / "model_artifacts" and root.is_mount()
    if root.is_symlink() or (root.is_relative_to(repository) and not mounted_root):
        raise ValueError("Chronos artifacts must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _remove_empty_or_partial_directory(directory: Path) -> None:
    for path in sorted(directory.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    directory.rmdir()


def _remove_download_metadata(directory: Path) -> None:
    """Discard downloader bookkeeping before attesting the allowlisted payload."""

    metadata = directory / ".cache"
    if metadata.exists():
        if metadata.is_symlink() or not metadata.is_dir():
            raise ValueError("Chronos downloader metadata is invalid")
        shutil.rmtree(metadata)


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="ascii") != rendered:
            raise ValueError("Chronos artifact identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != rendered:
                raise ValueError("Chronos artifact identity conflicts")
            return
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_json_object(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Chronos JSON artifact is unavailable")
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Chronos JSON artifact is invalid") from error
    if not isinstance(value, dict):
        raise ValueError("Chronos JSON artifact is invalid")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ValueError(f"Chronos {field_name} is invalid")


def _require_run_id(value: str) -> None:
    if _SAFE_RUN_ID.fullmatch(value) is None:
        raise ValueError("Chronos run id is invalid")


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "research_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "paper_input_eligible": False,
        "pnl_or_profitability_claim": False,
        "model_selection_eligible": False,
        "ensemble_eligible": False,
        "promotion_eligible": False,
    }


def _numpy() -> Any:
    import numpy

    return numpy


def _torch() -> Any:
    import torch

    return torch

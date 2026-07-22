"""Fixed PyTorch CUDA GRU smoke on the frozen KIS intraday development source."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import CatalogedBars

from .kis_intraday_feature_breadth import (
    KIS_INTRADAY_FEATURE_M1_BARS,
    KisIntradayFeatureContract,
    KisIntradayFeatureSample,
    build_kis_intraday_feature_contract,
    build_kis_intraday_feature_development_samples,
)

KIS_INTRADAY_CUDA_SEQUENCE_SMOKE_ID = "kis-intraday-cuda-gru-smoke-v1"
KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES = (
    "m1_close_return",
    "m1_range_ratio",
    "m1_volume_ratio",
)
KIS_INTRADAY_CUDA_SEQUENCE_HIDDEN_SIZE = 16
KIS_INTRADAY_CUDA_SEQUENCE_EPOCHS = 8
KIS_INTRADAY_CUDA_SEQUENCE_LEARNING_RATE = 0.001

SequenceTrainer = Callable[["KisIntradayCudaSequenceInput"], Mapping[str, object]]


@dataclass(frozen=True)
class KisIntradayCudaSequenceInput:
    """Development-only in-memory GRU input built from a fixed KIS source contract."""

    contract: KisIntradayFeatureContract
    sequences: tuple[tuple[tuple[float, float, float], ...], ...]
    labels: tuple[int, ...]
    development_input_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequences", tuple(tuple(row) for row in self.sequences))
        object.__setattr__(self, "labels", tuple(self.labels))
        if not self.sequences or len(self.sequences) != len(self.labels):
            raise ValueError("KIS CUDA sequence input geometry is invalid")
        if any(label not in (0, 1) for label in self.labels):
            raise ValueError("KIS CUDA sequence labels must be binary")
        if any(
            len(sequence) != KIS_INTRADAY_FEATURE_M1_BARS
            or any(len(row) != len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES) for row in sequence)
            or any(not math.isfinite(value) for row in sequence for value in row)
            for sequence in self.sequences
        ):
            raise ValueError("KIS CUDA sequence values are invalid")
        if (
            not self.development_input_hash.startswith("sha256:")
            or len(self.development_input_hash) != 71
        ):
            raise ValueError("KIS CUDA sequence input hash must be SHA-256")


@dataclass(frozen=True)
class KisIntradayCudaSequenceSmokeRun:
    """CUDA runtime evidence only; no candidate selection or model promotion occurs here."""

    sequence_input: KisIntradayCudaSequenceInput
    training: Mapping[str, object]
    summary_path: Path
    schema_version: int = SCHEMA_VERSION


def build_kis_intraday_cuda_sequence_input(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
) -> KisIntradayCudaSequenceInput:
    """Build the fixed GRU development tensor without materializing comparison labels."""

    contract = build_kis_intraday_feature_contract(catalog, session_dates=session_dates)
    samples = build_kis_intraday_feature_development_samples(contract)
    bars_by_start = {bar.start_ts: bar for bar in contract.campaign_plan.cataloged_bars.bars}
    sequences = tuple(
        _sequence_for_sample(sample, bars_by_start=bars_by_start) for sample in samples
    )
    labels = tuple(sample.target_label for sample in samples)
    development_input_hash = _sha256_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "smoke_id": KIS_INTRADAY_CUDA_SEQUENCE_SMOKE_ID,
            "feature_names": list(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
            "development_session_dates": [
                item.isoformat() for item in contract.development_session_dates
            ],
            "sequences": [
                [[format(value, ".17g") for value in row] for row in sequence]
                for sequence in sequences
            ],
            "labels": list(labels),
        }
    )
    return KisIntradayCudaSequenceInput(
        contract=contract,
        sequences=sequences,
        labels=labels,
        development_input_hash=development_input_hash,
    )


def run_kis_intraday_cuda_sequence_smoke(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    trainer: SequenceTrainer | None = None,
) -> KisIntradayCudaSequenceSmokeRun:
    """Run one fixed development-only CUDA GRU smoke and write a sanitized summary."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    output_dir = resolved_artifact_root / "kis-intraday-cuda-sequence-smoke" / run_label
    if output_dir.exists():
        raise FileExistsError(f"KIS CUDA sequence smoke artifact already exists: {output_dir}")

    sequence_input = build_kis_intraday_cuda_sequence_input(catalog, session_dates=session_dates)
    training = dict((trainer or _run_torch_cuda_gru)(sequence_input))
    _validate_training_payload(training)

    output_dir.mkdir(parents=True, exist_ok=False)
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        {
            "schema_version": SCHEMA_VERSION,
            "status": "complete",
            "mode": "offline_cuda_research",
            "smoke_id": KIS_INTRADAY_CUDA_SEQUENCE_SMOKE_ID,
            "claim": (
                "fixed CUDA GRU pipeline smoke only; not a candidate selection, "
                "profitability result, or model promotion"
            ),
            "source_contract_hash": sequence_input.contract.contract_hash,
            "development_input_hash": sequence_input.development_input_hash,
            "development_session_dates": [
                item.isoformat() for item in sequence_input.contract.development_session_dates
            ],
            "candidate_comparison_materialized": False,
            "sealed_confirmation_materialized": False,
            "sequence": {
                "sample_count": len(sequence_input.sequences),
                "length": KIS_INTRADAY_FEATURE_M1_BARS,
                "feature_names": list(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
            },
            "training": training,
            "artifact_policy": {
                "root": str(resolved_artifact_root),
                "repo_storage_allowed": False,
                "checkpoint_written": False,
            },
        },
    )
    return KisIntradayCudaSequenceSmokeRun(
        sequence_input=sequence_input,
        training=training,
        summary_path=summary_path,
    )


def _sequence_for_sample(
    sample: KisIntradayFeatureSample,
    *,
    bars_by_start: Mapping[object, Bar],
) -> tuple[tuple[float, float, float], ...]:
    bars = tuple(
        bars_by_start.get(sample.history_start + Timeframe.M1.duration * index)
        for index in range(KIS_INTRADAY_FEATURE_M1_BARS)
    )
    if any(bar is None for bar in bars):
        raise ValueError("KIS CUDA sequence input has a missing completed minute")
    history = tuple(bar for bar in bars if bar is not None)
    if history[-1].end_ts != sample.decision_end or any(
        bar.start_ts < sample.session_window.open_ts or bar.end_ts > sample.session_window.close_ts
        for bar in history
    ):
        raise ValueError("KIS CUDA sequence input cannot cross a session boundary")

    rows: list[tuple[float, float, float]] = []
    for index, bar in enumerate(history):
        previous_close = history[index - 1].close if index else bar.close
        recent = history[max(0, index - 19) : index + 1]
        volume_mean = sum(item.volume for item in recent) / len(recent)
        row = (
            float(bar.close / previous_close - 1),
            float((bar.high - bar.low) / bar.open),
            0.0 if volume_mean == 0 else float(bar.volume / volume_mean - 1),
        )
        rows.append(row)
    return tuple(rows)


def _run_torch_cuda_gru(sequence_input: KisIntradayCudaSequenceInput) -> Mapping[str, object]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is unavailable")
    torch.manual_seed(71)
    torch.cuda.manual_seed_all(71)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    device = torch.device("cuda")
    features = torch.tensor(sequence_input.sequences, dtype=torch.float32, device=device)
    labels = torch.tensor(sequence_input.labels, dtype=torch.float32, device=device).unsqueeze(1)
    encoder = torch.nn.GRU(
        input_size=len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
        hidden_size=KIS_INTRADAY_CUDA_SEQUENCE_HIDDEN_SIZE,
        batch_first=True,
    ).to(device)
    head = torch.nn.Linear(KIS_INTRADAY_CUDA_SEQUENCE_HIDDEN_SIZE, 1).to(device)
    optimizer = torch.optim.AdamW(
        list(encoder.parameters()) + list(head.parameters()),
        lr=KIS_INTRADAY_CUDA_SEQUENCE_LEARNING_RATE,
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()

    def loss_value() -> object:
        encoded, _ = encoder(features)
        return loss_fn(head(encoded[:, -1, :]), labels)

    initial_loss = loss_value()
    for _ in range(KIS_INTRADAY_CUDA_SEQUENCE_EPOCHS):
        optimizer.zero_grad(set_to_none=True)
        loss = loss_value()
        loss.backward()
        optimizer.step()
    torch.cuda.synchronize()
    final_loss = loss_value()
    return {
        "backend": "torch_cuda",
        "architecture": "gru_fixed_smoke",
        "device": torch.cuda.get_device_name(device),
        "cuda_version": torch.version.cuda,
        "sample_count": len(sequence_input.sequences),
        "sequence_length": KIS_INTRADAY_FEATURE_M1_BARS,
        "feature_count": len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
        "hidden_size": KIS_INTRADAY_CUDA_SEQUENCE_HIDDEN_SIZE,
        "epochs": KIS_INTRADAY_CUDA_SEQUENCE_EPOCHS,
        "learning_rate": KIS_INTRADAY_CUDA_SEQUENCE_LEARNING_RATE,
        "initial_loss": f"{initial_loss.item():.8f}",
        "final_loss": f"{final_loss.item():.8f}",
    }


def _validate_training_payload(training: Mapping[str, object]) -> None:
    required = {
        "backend",
        "architecture",
        "sample_count",
        "sequence_length",
        "feature_count",
        "epochs",
    }
    if required - training.keys():
        raise ValueError("KIS CUDA sequence training result is incomplete")


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_run_label(run_label: str) -> None:
    if not run_label.strip() or any(character in run_label for character in ("/", "\\", ":")):
        raise ValueError("run_label must be nonempty and contain no path separators")


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if repo_root == docker_repo_root and (
            path == docker_artifact_root or docker_artifact_root in path.parents
        ):
            return
    if path == repo_root or repo_root in path.parents:
        raise ValueError("KIS CUDA sequence artifacts must stay outside the Git workspace")

"""Fixed CUDA sequence-architecture screen for the frozen KIS intraday input."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data import CatalogedBars, SessionWindow
from thericher_v2.execution import LOCAL_PAPER_SOURCE

from .campaign import CampaignContract, CampaignFold, CampaignWindow
from .kis_intraday_campaign import KIS_INTRADAY_FIRST_SIGNAL_OFFSET, KIS_INTRADAY_LAST_SIGNAL_OFFSET
from .kis_intraday_cuda_sequence_smoke import (
    KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES,
    KisIntradayCudaSequenceInput,
    build_kis_intraday_cuda_sequence_input,
)
from .kis_intraday_feature_breadth import (
    KIS_INTRADAY_FEATURE_M1_BARS,
    KisIntradayFeatureContract,
    KisIntradayFeatureSample,
    build_kis_intraday_feature_candidate_comparison_samples,
    build_kis_intraday_feature_contract,
)
from .validation import CampaignReplayRun, run_campaign_model_replay

KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SCREEN_ID = "kis-intraday-sequence-architecture-screen-v1"
KIS_INTRADAY_SEQUENCE_ARCHITECTURES = ("lstm", "causal_tcn", "compact_attention")
KIS_INTRADAY_SEQUENCE_HIDDEN_SIZE = 16
KIS_INTRADAY_SEQUENCE_ATTENTION_HEADS = 4
KIS_INTRADAY_SEQUENCE_TCN_KERNEL_SIZE = 3
KIS_INTRADAY_SEQUENCE_EPOCHS = 8
KIS_INTRADAY_SEQUENCE_LEARNING_RATE = 0.001
KIS_INTRADAY_SEQUENCE_DECISION_THRESHOLD = 0.5

SequenceRow = tuple[float, float, float]
SequenceFeatures = tuple[SequenceRow, ...]
SequenceBatch = tuple[SequenceFeatures, ...]
ProbabilityPredictor = Callable[[SequenceBatch], tuple[float, ...]]
ComparisonSamplesBuilder = Callable[
    [KisIntradayFeatureContract], tuple[KisIntradayFeatureSample, ...]
]


@dataclass(frozen=True)
class KisIntradaySequenceArchitectureSpec:
    """One fully fixed architecture configuration recorded before comparison materializes."""

    architecture_id: Literal["lstm", "causal_tcn", "compact_attention"]
    seed: int
    hidden_size: int = KIS_INTRADAY_SEQUENCE_HIDDEN_SIZE
    attention_heads: int = KIS_INTRADAY_SEQUENCE_ATTENTION_HEADS
    tcn_kernel_size: int = KIS_INTRADAY_SEQUENCE_TCN_KERNEL_SIZE
    epochs: int = KIS_INTRADAY_SEQUENCE_EPOCHS
    learning_rate: float = KIS_INTRADAY_SEQUENCE_LEARNING_RATE
    decision_threshold: float = KIS_INTRADAY_SEQUENCE_DECISION_THRESHOLD
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.architecture_id not in KIS_INTRADAY_SEQUENCE_ARCHITECTURES:
            raise ValueError("KIS intraday sequence architecture is invalid")
        if (
            self.hidden_size != KIS_INTRADAY_SEQUENCE_HIDDEN_SIZE
            or self.attention_heads != KIS_INTRADAY_SEQUENCE_ATTENTION_HEADS
            or self.tcn_kernel_size != KIS_INTRADAY_SEQUENCE_TCN_KERNEL_SIZE
            or self.epochs != KIS_INTRADAY_SEQUENCE_EPOCHS
            or self.learning_rate != KIS_INTRADAY_SEQUENCE_LEARNING_RATE
            or self.decision_threshold != KIS_INTRADAY_SEQUENCE_DECISION_THRESHOLD
        ):
            raise ValueError("KIS intraday sequence architecture hyperparameters are frozen")
        if self.hidden_size % self.attention_heads != 0 or self.seed < 0:
            raise ValueError("KIS intraday sequence architecture geometry is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "architecture_id": self.architecture_id,
            "seed": self.seed,
            "hidden_size": self.hidden_size,
            "attention_heads": self.attention_heads,
            "tcn_kernel_size": self.tcn_kernel_size,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "decision_threshold": self.decision_threshold,
            "training_scope": "development_only",
        }


KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS = (
    KisIntradaySequenceArchitectureSpec(architecture_id="lstm", seed=101),
    KisIntradaySequenceArchitectureSpec(architecture_id="causal_tcn", seed=103),
    KisIntradaySequenceArchitectureSpec(architecture_id="compact_attention", seed=107),
)


@dataclass(frozen=True)
class KisIntradayTrainedSequenceArchitecture:
    """In-memory development-only model plus a probability adapter for fixed replay."""

    spec: KisIntradaySequenceArchitectureSpec
    training: Mapping[str, object]
    predict_probabilities: ProbabilityPredictor


SequenceArchitectureTrainer = Callable[
    [KisIntradayCudaSequenceInput, KisIntradaySequenceArchitectureSpec],
    KisIntradayTrainedSequenceArchitecture,
]


@dataclass(frozen=True)
class KisIntradaySequenceArchitectureRun:
    architecture_id: str
    training: Mapping[str, object]
    prediction_hash: str
    replay: CampaignReplayRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.architecture_id not in KIS_INTRADAY_SEQUENCE_ARCHITECTURES:
            raise ValueError("KIS intraday sequence architecture run is invalid")
        if self.replay.fill_source != LOCAL_PAPER_SOURCE:
            raise ValueError("KIS intraday sequence screen requires local-paper replay")


@dataclass(frozen=True)
class KisIntradaySequenceArchitectureScreenRun:
    """One descriptive, jointly reported comparison with no winner or promotion state."""

    contract: KisIntradayFeatureContract
    development_input: KisIntradayCudaSequenceInput
    precommit_path: Path
    precommit_hash: str
    comparison_input_hash: str
    architecture_runs: tuple[KisIntradaySequenceArchitectureRun, ...]
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "architecture_runs", tuple(self.architecture_runs))
        if tuple(item.architecture_id for item in self.architecture_runs) != (
            KIS_INTRADAY_SEQUENCE_ARCHITECTURES
        ):
            raise ValueError("KIS intraday sequence architectures must run in fixed order")


def run_kis_intraday_sequence_architecture_screen(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    artifact_root: Path,
    work_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    trainer: SequenceArchitectureTrainer | None = None,
    comparison_samples_builder: ComparisonSamplesBuilder = (
        build_kis_intraday_feature_candidate_comparison_samples
    ),
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
) -> KisIntradaySequenceArchitectureScreenRun:
    """Train fixed models on development data and jointly replay their fixed comparison outputs."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    resolved_work_root = Path(work_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    _reject_repo_path(resolved_work_root, repo_root=resolved_repo_root)
    output_dir = resolved_artifact_root / "kis-intraday-sequence-architecture-screen" / run_label
    if output_dir.exists():
        raise FileExistsError(
            f"KIS intraday sequence architecture screen artifact already exists: {output_dir}"
        )

    contract = build_kis_intraday_feature_contract(catalog, session_dates=tuple(session_dates))
    development_input = build_kis_intraday_cuda_sequence_input(
        catalog,
        session_dates=tuple(session_dates),
    )
    if development_input.contract.contract_hash != contract.contract_hash:
        raise ValueError(
            "KIS intraday sequence development input does not match the source contract"
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(contract=contract, development_input=development_input)
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, precommit_payload)

    selected_trainer = trainer or _train_torch_cuda_architecture
    trained = tuple(
        selected_trainer(development_input, spec)
        for spec in KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS
    )
    _validate_trained_architectures(trained, development_input=development_input)

    comparison_samples = tuple(comparison_samples_builder(contract))
    _validate_comparison_samples(comparison_samples, contract=contract)
    bars_by_start = {
        bar.start_ts: bar for bar in contract.campaign_plan.cataloged_bars.bars
    }
    comparison_sequences = tuple(
        _sequence_for_sample(sample, bars_by_start=bars_by_start) for sample in comparison_samples
    )
    comparison_input_hash = _comparison_input_hash(
        samples=comparison_samples,
        sequences=comparison_sequences,
    )
    samples_by_decision_end = {sample.decision_end: sample for sample in comparison_samples}
    if len(samples_by_decision_end) != len(comparison_samples):
        raise ValueError("KIS intraday sequence comparison decisions must be unique")
    campaign = _candidate_comparison_campaign(contract)

    architecture_runs: list[KisIntradaySequenceArchitectureRun] = []
    for trained_architecture in trained:
        probabilities = tuple(trained_architecture.predict_probabilities(comparison_sequences))
        _validate_probabilities(probabilities, expected_count=len(comparison_sequences))
        probabilities_by_decision_end = dict(
            zip(
                (sample.decision_end for sample in comparison_samples),
                probabilities,
                strict=True,
            )
        )
        prediction_hash = _sha256_payload(
            {
                "precommit_hash": precommit_hash,
                "architecture_id": trained_architecture.spec.architecture_id,
                "comparison_input_hash": comparison_input_hash,
                "probabilities": [format(value, ".17g") for value in probabilities],
            }
        )
        model = _KisIntradaySequenceDecisionModel(
            architecture_id=trained_architecture.spec.architecture_id,
            samples_by_decision_end=samples_by_decision_end,
            probabilities_by_decision_end=probabilities_by_decision_end,
            precommit_hash=precommit_hash,
            prediction_hash=prediction_hash,
            threshold=trained_architecture.spec.decision_threshold,
        )
        replay = run_campaign_model_replay(
            contract.campaign_plan.cataloged_bars,
            campaign=campaign,
            model=model,
            run_id=(
                f"{KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SCREEN_ID}-"
                f"{trained_architecture.spec.architecture_id}-{run_label}"
            ),
            artifact_root=resolved_artifact_root,
            work_dir=(
                resolved_work_root
                / "kis-intraday-sequence-architecture-screen"
                / run_label
                / trained_architecture.spec.architecture_id
            ),
            phase="validation",
            fold_id="fold-1",
            repo_root=resolved_repo_root,
            starting_cash=starting_cash,
            quantity=quantity,
            eligible_signal_starts=_eligible_signal_starts(
                contract.candidate_comparison_session_windows
            ),
            allowed_session_windows=contract.candidate_comparison_session_windows,
            emergency_reason="kis_intraday_sequence_architecture_screen_comparison_only",
        )
        if (
            replay.fill_source != LOCAL_PAPER_SOURCE
            or replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
        ):
            raise RuntimeError("KIS intraday sequence screen must use local-paper only")
        architecture_runs.append(
            KisIntradaySequenceArchitectureRun(
                architecture_id=trained_architecture.spec.architecture_id,
                training=dict(trained_architecture.training),
                prediction_hash=prediction_hash,
                replay=replay,
            )
        )

    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            contract=contract,
            development_input=development_input,
            precommit_path=precommit_path,
            precommit_hash=precommit_hash,
            comparison_input_hash=comparison_input_hash,
            architecture_runs=tuple(architecture_runs),
            artifact_root=resolved_artifact_root,
            campaign=campaign,
        ),
    )
    return KisIntradaySequenceArchitectureScreenRun(
        contract=contract,
        development_input=development_input,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        comparison_input_hash=comparison_input_hash,
        architecture_runs=tuple(architecture_runs),
        summary_path=summary_path,
    )


@dataclass(frozen=True)
class _KisIntradaySequenceDecisionModel:
    architecture_id: str
    samples_by_decision_end: Mapping[datetime, KisIntradayFeatureSample]
    probabilities_by_decision_end: Mapping[datetime, float]
    precommit_hash: str
    prediction_hash: str
    threshold: float
    lookback: int = KIS_INTRADAY_FEATURE_M1_BARS - 1

    def __post_init__(self) -> None:
        if (
            self.architecture_id not in KIS_INTRADAY_SEQUENCE_ARCHITECTURES
            or not 0 <= self.threshold <= 1
            or set(self.samples_by_decision_end) != set(self.probabilities_by_decision_end)
        ):
            raise ValueError("KIS intraday sequence decision model is invalid")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < KIS_INTRADAY_FEATURE_M1_BARS:
            raise ValueError("KIS intraday sequence model requires 90 completed M1 bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        probability = self.probabilities_by_decision_end.get(latest.end_ts)
        if sample is None or probability is None:
            raise ValueError("KIS intraday sequence model received a non-comparison decision")
        tail = tuple(bars[-KIS_INTRADAY_FEATURE_M1_BARS:])
        expected_starts = tuple(
            sample.history_start + Timeframe.M1.duration * index
            for index in range(KIS_INTRADAY_FEATURE_M1_BARS)
        )
        if (
            tuple(bar.start_ts for bar in tail) != expected_starts
            or tail[-1].end_ts != sample.decision_end
            or any(
                bar.start_ts < sample.session_window.open_ts
                or bar.end_ts > sample.session_window.close_ts
                for bar in tail
            )
        ):
            raise ValueError("KIS intraday sequence model cannot use cross-session history")
        confidence = Decimal(str(probability))
        action: Literal["buy", "hold"] = "buy" if probability >= self.threshold else "hold"
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=f"kis_intraday_sequence_{self.architecture_id}",
            timeframe=Timeframe.M1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=f"kis_intraday_sequence_{self.architecture_id}",
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "architecture_id": self.architecture_id,
                "decision_rule": "fixed_probability_threshold",
                "threshold": self.threshold,
                "precommit_hash": self.precommit_hash,
                "prediction_hash": self.prediction_hash,
            },
        )


def _precommit_payload(
    *,
    contract: KisIntradayFeatureContract,
    development_input: KisIntradayCudaSequenceInput,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "precommitted",
        "screen_id": KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SCREEN_ID,
        "claim": (
            "fixed multi-architecture descriptive comparison only; no winner, selection, "
            "ensemble, profitability claim, or paper-authorization decision"
        ),
        "source_contract_hash": contract.contract_hash,
        "development_input_hash": development_input.development_input_hash,
        "development_session_dates": [
            item.isoformat() for item in contract.development_session_dates
        ],
        "architectures": [
            spec.to_payload() for spec in KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS
        ],
        "replay_eligibility": {
            "phase": "validation",
            "fold_id": "fold-1",
            "candidate_comparison_session_dates": [
                item.isoformat() for item in contract.candidate_comparison_session_dates
            ],
            "candidate_comparison_session_windows": [
                _window_payload(item) for item in contract.candidate_comparison_session_windows
            ],
            "signal_offsets": {
                "first": KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
                "last": KIS_INTRADAY_LAST_SIGNAL_OFFSET,
            },
            "fill_source": LOCAL_PAPER_SOURCE,
        },
        "reporting": {
            "all_architectures_reported_jointly": True,
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
        },
        "comparison_materialized": False,
        "sealed_confirmation_materialized": False,
        "artifact_policy": {
            "raw_market_data_written": False,
            "checkpoint_written": False,
            "repo_storage_allowed": False,
        },
    }


def _validate_trained_architectures(
    trained: tuple[KisIntradayTrainedSequenceArchitecture, ...],
    *,
    development_input: KisIntradayCudaSequenceInput,
) -> None:
    if len(trained) != len(KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS):
        raise ValueError("KIS intraday sequence screen requires every fixed architecture")
    for actual, expected in zip(
        trained,
        KIS_INTRADAY_SEQUENCE_ARCHITECTURE_SPECS,
        strict=True,
    ):
        if actual.spec != expected or not callable(actual.predict_probabilities):
            raise ValueError("KIS intraday sequence trainer changed the fixed architecture plan")
        payload = actual.training
        required = {
            "backend",
            "architecture",
            "sample_count",
            "sequence_length",
            "feature_count",
            "epochs",
            "learning_rate",
            "initial_loss",
            "final_loss",
        }
        if required - payload.keys() or payload["architecture"] != expected.architecture_id:
            raise ValueError("KIS intraday sequence trainer result is incomplete")
        if (
            payload["sample_count"] != len(development_input.sequences)
            or payload["sequence_length"] != KIS_INTRADAY_FEATURE_M1_BARS
            or payload["feature_count"] != len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES)
            or payload["epochs"] != expected.epochs
            or payload["learning_rate"] != expected.learning_rate
        ):
            raise ValueError("KIS intraday sequence trainer result changed the fixed contract")


def _validate_comparison_samples(
    samples: tuple[KisIntradayFeatureSample, ...],
    *,
    contract: KisIntradayFeatureContract,
) -> None:
    expected_count = len(contract.candidate_comparison_session_dates) * (
        KIS_INTRADAY_LAST_SIGNAL_OFFSET - KIS_INTRADAY_FIRST_SIGNAL_OFFSET + 1
    )
    if (
        len(samples) != expected_count
        or {sample.session_date for sample in samples}
        != set(contract.candidate_comparison_session_dates)
        or any(
            sample.session_date in contract.development_session_dates
            or sample.session_date == contract.purge_session_date
            or sample.session_date in contract.sealed_confirmation_session_dates
            for sample in samples
        )
    ):
        raise ValueError("KIS intraday sequence comparison samples escape the fixed slice")


def _sequence_for_sample(
    sample: KisIntradayFeatureSample,
    *,
    bars_by_start: Mapping[datetime, Bar],
) -> SequenceFeatures:
    bars = tuple(
        bars_by_start.get(sample.history_start + Timeframe.M1.duration * index)
        for index in range(KIS_INTRADAY_FEATURE_M1_BARS)
    )
    if any(bar is None for bar in bars):
        raise ValueError("KIS intraday sequence input has a missing completed minute")
    history = tuple(bar for bar in bars if bar is not None)
    if history[-1].end_ts != sample.decision_end or any(
        bar.start_ts < sample.session_window.open_ts or bar.end_ts > sample.session_window.close_ts
        for bar in history
    ):
        raise ValueError("KIS intraday sequence input cannot cross a session boundary")
    rows: list[SequenceRow] = []
    for index, bar in enumerate(history):
        previous_close = history[index - 1].close if index else bar.close
        recent = history[max(0, index - 19) : index + 1]
        volume_mean = sum(item.volume for item in recent) / len(recent)
        row = (
            float(bar.close / previous_close - 1),
            float((bar.high - bar.low) / bar.open),
            0.0 if volume_mean == 0 else float(bar.volume / volume_mean - 1),
        )
        if any(not math.isfinite(value) for value in row):
            raise ValueError("KIS intraday sequence feature values are invalid")
        rows.append(row)
    return tuple(rows)


def _comparison_input_hash(
    *,
    samples: tuple[KisIntradayFeatureSample, ...],
    sequences: SequenceBatch,
) -> str:
    return _sha256_payload(
        {
            "decision_ends": [item.decision_end.isoformat() for item in samples],
            "sequences": [
                [[format(value, ".17g") for value in row] for row in sequence]
                for sequence in sequences
            ],
        }
    )


def _validate_probabilities(probabilities: tuple[float, ...], *, expected_count: int) -> None:
    if len(probabilities) != expected_count or any(
        not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities
    ):
        raise ValueError("KIS intraday sequence probabilities are invalid")


def _candidate_comparison_campaign(
    contract: KisIntradayFeatureContract,
) -> CampaignContract:
    source = contract.campaign_plan.campaign
    source_fold = source.folds[0]
    windows = contract.candidate_comparison_session_windows
    return replace(
        source,
        campaign_id=f"{source.campaign_id}-sequence-architecture-comparison",
        folds=(
            CampaignFold(
                fold_id=source_fold.fold_id,
                development=source_fold.development,
                validation=CampaignWindow(windows[0].open_ts, windows[-1].close_ts),
            ),
        ),
    )


def _eligible_signal_starts(windows: tuple[SessionWindow, ...]) -> frozenset[datetime]:
    return frozenset(
        window.open_ts + Timeframe.M1.duration * offset
        for window in windows
        for offset in range(
            KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
            KIS_INTRADAY_LAST_SIGNAL_OFFSET + 1,
        )
    )


def _train_torch_cuda_architecture(
    development_input: KisIntradayCudaSequenceInput,
    spec: KisIntradaySequenceArchitectureSpec,
) -> KisIntradayTrainedSequenceArchitecture:
    """Use PyTorch lazily so CPU-only import and test paths need no CUDA runtime."""

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is unavailable")
    torch.manual_seed(spec.seed)
    torch.cuda.manual_seed_all(spec.seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    device = torch.device("cuda")
    features = torch.tensor(development_input.sequences, dtype=torch.float32, device=device)
    labels = torch.tensor(development_input.labels, dtype=torch.float32, device=device).unsqueeze(1)
    model = _torch_model(torch=torch, spec=spec).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate)
    loss_fn = torch.nn.BCEWithLogitsLoss()

    def loss_value() -> object:
        return loss_fn(model(features), labels)

    initial_loss = float(loss_value().detach().item())
    model.train()
    for _ in range(spec.epochs):
        optimizer.zero_grad(set_to_none=True)
        loss = loss_value()
        loss.backward()
        optimizer.step()
    torch.cuda.synchronize()
    model.eval()
    final_loss = float(loss_value().detach().item())

    def predict_probabilities(batch: SequenceBatch) -> tuple[float, ...]:
        with torch.no_grad():
            tensor = torch.tensor(batch, dtype=torch.float32, device=device)
            values = torch.sigmoid(model(tensor)).flatten().detach().cpu().tolist()
        return tuple(float(value) for value in values)

    return KisIntradayTrainedSequenceArchitecture(
        spec=spec,
        training={
            "backend": "torch_cuda",
            "architecture": spec.architecture_id,
            "device": torch.cuda.get_device_name(device),
            "cuda_version": torch.version.cuda,
            "sample_count": len(development_input.sequences),
            "sequence_length": KIS_INTRADAY_FEATURE_M1_BARS,
            "feature_count": len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
            "hidden_size": spec.hidden_size,
            "attention_heads": spec.attention_heads,
            "tcn_kernel_size": spec.tcn_kernel_size,
            "epochs": spec.epochs,
            "learning_rate": spec.learning_rate,
            "initial_loss": f"{initial_loss:.8f}",
            "final_loss": f"{final_loss:.8f}",
        },
        predict_probabilities=predict_probabilities,
    )


def _torch_model(*, torch: object, spec: KisIntradaySequenceArchitectureSpec) -> object:
    nn = torch.nn

    if spec.architecture_id == "lstm":

        class LstmModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.encoder = nn.LSTM(
                    input_size=len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
                    hidden_size=spec.hidden_size,
                    batch_first=True,
                )
                self.head = nn.Linear(spec.hidden_size, 1)

            def forward(self, values: object) -> object:
                encoded, _ = self.encoder(values)
                return self.head(encoded[:, -1, :])

        return LstmModel()

    if spec.architecture_id == "causal_tcn":

        class CausalTcnModel(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.convolution = nn.Conv1d(
                    len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
                    spec.hidden_size,
                    kernel_size=spec.tcn_kernel_size,
                    padding=spec.tcn_kernel_size - 1,
                )
                self.head = nn.Linear(spec.hidden_size, 1)

            def forward(self, values: object) -> object:
                length = values.shape[1]
                encoded = self.convolution(values.transpose(1, 2))[:, :, :length]
                encoded = torch.relu(encoded)
                return self.head(encoded[:, :, -1])

        return CausalTcnModel()

    class CompactAttentionModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_projection = nn.Linear(
                len(KIS_INTRADAY_CUDA_SEQUENCE_FEATURE_NAMES),
                spec.hidden_size,
            )
            layer = nn.TransformerEncoderLayer(
                d_model=spec.hidden_size,
                nhead=spec.attention_heads,
                dim_feedforward=spec.hidden_size * 2,
                dropout=0.0,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=1)
            self.head = nn.Linear(spec.hidden_size, 1)

        def forward(self, values: object) -> object:
            length = values.shape[1]
            positions = torch.arange(length, dtype=values.dtype, device=values.device).unsqueeze(1)
            divisors = torch.exp(
                torch.arange(0, spec.hidden_size, 2, dtype=values.dtype, device=values.device)
                * (-math.log(10000.0) / spec.hidden_size)
            )
            positional = torch.zeros(
                (length, spec.hidden_size), dtype=values.dtype, device=values.device
            )
            positional[:, 0::2] = torch.sin(positions * divisors)
            positional[:, 1::2] = torch.cos(positions * divisors)
            causal_mask = torch.triu(
                torch.full(
                    (length, length), float("-inf"), dtype=values.dtype, device=values.device
                ),
                diagonal=1,
            )
            encoded = self.encoder(
                self.input_projection(values) + positional.unsqueeze(0),
                mask=causal_mask,
            )
            return self.head(encoded[:, -1, :])

    return CompactAttentionModel()


def _summary_payload(
    *,
    contract: KisIntradayFeatureContract,
    development_input: KisIntradayCudaSequenceInput,
    precommit_path: Path,
    precommit_hash: str,
    comparison_input_hash: str,
    architecture_runs: tuple[KisIntradaySequenceArchitectureRun, ...],
    artifact_root: Path,
    campaign: CampaignContract,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_cuda_local_paper",
        "claim": (
            "fixed multi-architecture descriptive comparison only; no winner, selection, "
            "ensemble, profitability claim, or paper-authorization decision"
        ),
        "source_contract_hash": contract.contract_hash,
        "development_input_hash": development_input.development_input_hash,
        "comparison_input_hash": comparison_input_hash,
        "precommit": {
            "path": str(precommit_path),
            "hash": precommit_hash,
            "written_before_comparison_materialized": True,
        },
        "candidate_comparison": {
            "session_dates": [
                item.isoformat() for item in contract.candidate_comparison_session_dates
            ],
            "materialized": True,
            "all_architectures_reported_jointly": True,
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
        },
        "sealed_confirmation": {
            "session_dates": [
                item.isoformat() for item in contract.sealed_confirmation_session_dates
            ],
            "materialized": False,
        },
        "candidate_comparison_campaign_contract_hash": campaign.contract_hash,
        "architectures": [
            {
                "architecture_id": item.architecture_id,
                "training": dict(item.training),
                "prediction_hash": item.prediction_hash,
                "fill_source": item.replay.fill_source,
                "validation_artifact_path": str(item.replay.artifact_path),
                "replay_evidence": item.replay.replay_evidence.to_payload(),
                "result": {
                    "bars_seen": item.replay.result.bars_seen,
                    "decisions_seen": item.replay.result.decisions_seen,
                    "trade_count": len(item.replay.result.trades),
                    "after_cost_pnl": str(item.replay.result.after_cost_pnl),
                    "gross_pnl": str(item.replay.result.gross_pnl),
                    "total_fees": str(item.replay.result.total_fees),
                    "total_slippage": str(item.replay.result.total_slippage),
                },
            }
            for item in architecture_runs
        ],
        "artifact_policy": {
            "root": str(artifact_root),
            "repo_storage_allowed": False,
            "checkpoint_written": False,
            "raw_market_data_written": False,
        },
    }


def _window_payload(window: SessionWindow) -> dict[str, str]:
    return {"open_utc": window.open_ts.isoformat(), "close_utc": window.close_ts.isoformat()}


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
        raise ValueError("KIS intraday sequence artifacts must stay outside the Git workspace")

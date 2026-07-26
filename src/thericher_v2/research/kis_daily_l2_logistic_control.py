"""Frozen CPU L2-logistic control for the QQQ/SPY daily sequence contract.

This is a deliberately small control, not a candidate-selection framework. It
uses the same hash-attested, completed-bar-only input geometry as the fixed
daily sequence screen, fits only development labels, then replays one frozen
chronological validation alongside the three contract-bound naive baselines.
All replays stay in the existing broker-free local-paper path.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.execution import LOCAL_PAPER_SOURCE

from .campaign import CampaignContract, NaiveBaselineId
from .kis_daily_sequence_architecture_screen import (
    KIS_DAILY_SEQUENCE_FEATURE_NAMES,
    KIS_DAILY_SEQUENCE_FOLD_ID,
    KIS_DAILY_SEQUENCE_LENGTH,
    KIS_DAILY_SEQUENCE_SYMBOLS,
    KisDailySequenceSample,
    KisDailySequenceScreenInput,
    build_kis_daily_sequence_screen_input,
)
from .validation import (
    CampaignReplayRun,
    NaiveBaselineRun,
    run_campaign_model_replay,
    run_naive_cpu_baseline,
)

KIS_DAILY_L2_LOGISTIC_CONTROL_ID = "kis-daily-l2-logistic-control-v1"
KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID = "l2_logistic"
KIS_DAILY_L2_LOGISTIC_CONTROL_STEPS = 160
KIS_DAILY_L2_LOGISTIC_CONTROL_LEARNING_RATE = 0.08
KIS_DAILY_L2_LOGISTIC_CONTROL_L2 = 0.0001
KIS_DAILY_L2_LOGISTIC_CONTROL_THRESHOLD = 0.5
KIS_DAILY_L2_LOGISTIC_CONTROL_DETERMINISTIC_SEED = 239
KIS_DAILY_L2_LOGISTIC_CONTROL_STARTING_CASH = Decimal("10000")
KIS_DAILY_L2_LOGISTIC_CONTROL_QUANTITY = Decimal("1")
KIS_DAILY_L2_LOGISTIC_CONTROL_FEATURE_WIDTH = (
    KIS_DAILY_SEQUENCE_LENGTH * len(KIS_DAILY_SEQUENCE_FEATURE_NAMES)
)
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class KisDailyL2LogisticControlSpec:
    """The one precommitted CPU control configuration.

    The model is intentionally non-configurable at this stage. Changing a
    hyperparameter is a different campaign rather than a validation retune.
    """

    steps: int = KIS_DAILY_L2_LOGISTIC_CONTROL_STEPS
    learning_rate: float = KIS_DAILY_L2_LOGISTIC_CONTROL_LEARNING_RATE
    l2_penalty: float = KIS_DAILY_L2_LOGISTIC_CONTROL_L2
    threshold: float = KIS_DAILY_L2_LOGISTIC_CONTROL_THRESHOLD
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.steps != KIS_DAILY_L2_LOGISTIC_CONTROL_STEPS
            or self.learning_rate != KIS_DAILY_L2_LOGISTIC_CONTROL_LEARNING_RATE
            or self.l2_penalty != KIS_DAILY_L2_LOGISTIC_CONTROL_L2
            or self.threshold != KIS_DAILY_L2_LOGISTIC_CONTROL_THRESHOLD
        ):
            raise ValueError("KIS daily L2 logistic control hyperparameters are frozen")

    def to_payload(self) -> dict[str, object]:
        return {
            "family": "l2_logistic_linear",
            "sequence_length": KIS_DAILY_SEQUENCE_LENGTH,
            "feature_names": list(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
            "flattened_feature_width": KIS_DAILY_L2_LOGISTIC_CONTROL_FEATURE_WIDTH,
            "optimizer": "deterministic_full_batch_gradient_descent",
            "steps": self.steps,
            "learning_rate": self.learning_rate,
            "l2_penalty": self.l2_penalty,
            "threshold": self.threshold,
            "training_scope": "pooled_qqq_spy_development_only",
        }


@dataclass(frozen=True)
class KisDailyL2LogisticControlInput:
    """The frozen QQQ/SPY input and its dedicated non-ranking campaign contract."""

    sequence_input: KisDailySequenceScreenInput
    campaign: CampaignContract
    spec: KisDailyL2LogisticControlSpec
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_campaign = replace(
            self.sequence_input.campaign,
            campaign_id=KIS_DAILY_L2_LOGISTIC_CONTROL_ID,
            deterministic_seed=KIS_DAILY_L2_LOGISTIC_CONTROL_DETERMINISTIC_SEED,
        )
        if (
            self.campaign != expected_campaign
            or any(sample.label is None for sample in self.sequence_input.development_samples)
            or any(
                sample.label is not None
                for samples in self.sequence_input.validation_samples_by_symbol.values()
                for sample in samples
            )
        ):
            raise ValueError("KIS daily L2 logistic control input is not phase-frozen")


@dataclass(frozen=True)
class KisDailyL2LogisticControlModel:
    """Development-only fitted parameters for the fixed flattened logistic control."""

    spec: KisDailyL2LogisticControlSpec
    development_input_hash: str
    standardizer_hash: str
    weights: tuple[float, ...]
    intercept: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "weights", tuple(float(value) for value in self.weights))
        if (
            len(self.weights) != KIS_DAILY_L2_LOGISTIC_CONTROL_FEATURE_WIDTH
            or not _is_sha256(self.development_input_hash)
            or not _is_sha256(self.standardizer_hash)
            or any(not math.isfinite(value) for value in (*self.weights, self.intercept))
        ):
            raise ValueError("KIS daily L2 logistic control parameters are invalid")

    @property
    def parameter_hash(self) -> str:
        return _sha256_payload(
            {
                "spec": self.spec.to_payload(),
                "development_input_hash": self.development_input_hash,
                "standardizer_hash": self.standardizer_hash,
                "weights": [format(value, ".17g") for value in self.weights],
                "intercept": format(self.intercept, ".17g"),
            }
        )

    def probability(self, features: Sequence[Sequence[float]]) -> float:
        flattened = _flatten_features(features)
        if len(flattened) != len(self.weights):
            raise ValueError("KIS daily L2 logistic control feature width is invalid")
        return _sigmoid(
            self.intercept
            + math.fsum(
                weight * value for weight, value in zip(self.weights, flattened, strict=True)
            )
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_DAILY_L2_LOGISTIC_CONTROL_ID + "_model",
            "candidate_id": KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID,
            "spec": self.spec.to_payload(),
            "development_input_hash": self.development_input_hash,
            "standardizer_hash": self.standardizer_hash,
            "weights": [float(value) for value in self.weights],
            "intercept": self.intercept,
            "parameter_hash": self.parameter_hash,
            "validation_labels_materialized_for_fit": False,
        }


@dataclass(frozen=True)
class KisDailyL2LogisticReplayCell:
    symbol: str
    prediction_hash: str
    replay: CampaignReplayRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or not _is_sha256(self.prediction_hash)
            or self.replay.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.result.campaign_phase != "validation"
        ):
            raise ValueError(
                "KIS daily L2 logistic replay requires validation local-paper evidence"
            )


@dataclass(frozen=True)
class KisDailyL2LogisticBaselineCell:
    symbol: str
    baseline_id: NaiveBaselineId
    replay: NaiveBaselineRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or self.baseline_id not in {"flat", "always_long", "previous_bar_direction"}
            or self.replay.baseline_id != self.baseline_id
            or self.replay.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.result.campaign_phase != "validation"
        ):
            raise ValueError(
                "KIS daily L2 logistic baseline requires validation local-paper evidence"
            )


@dataclass(frozen=True)
class KisDailyL2LogisticControlRun:
    """Descriptive CPU control evidence only; never a selection or order decision."""

    control_input: KisDailyL2LogisticControlInput
    precommit_path: Path
    precommit_hash: str
    model: KisDailyL2LogisticControlModel
    model_path: Path
    replay_cells: tuple[KisDailyL2LogisticReplayCell, ...]
    baseline_cells: tuple[KisDailyL2LogisticBaselineCell, ...]
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_cells", tuple(self.replay_cells))
        object.__setattr__(self, "baseline_cells", tuple(self.baseline_cells))
        expected_baselines = tuple(
            (symbol, baseline_id)
            for symbol in KIS_DAILY_SEQUENCE_SYMBOLS
            for baseline_id in self.control_input.campaign.naive_baselines
        )
        if (
            tuple(cell.symbol for cell in self.replay_cells) != KIS_DAILY_SEQUENCE_SYMBOLS
            or tuple((cell.symbol, cell.baseline_id) for cell in self.baseline_cells)
            != expected_baselines
            or not _is_sha256(self.precommit_hash)
            or not self.precommit_path.is_file()
            or not self.model_path.is_file()
            or not self.summary_path.is_file()
        ):
            raise ValueError("KIS daily L2 logistic control did not complete the frozen plan")


@dataclass(frozen=True)
class _KisDailyL2LogisticDecisionModel:
    symbol: str
    samples_by_decision_end: Mapping[datetime, KisDailySequenceSample]
    probabilities_by_decision_end: Mapping[datetime, float]
    precommit_hash: str
    model_parameter_hash: str
    lookback: int = KIS_DAILY_SEQUENCE_LENGTH

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "samples_by_decision_end",
            MappingProxyType(dict(self.samples_by_decision_end)),
        )
        object.__setattr__(
            self,
            "probabilities_by_decision_end",
            MappingProxyType(dict(self.probabilities_by_decision_end)),
        )
        if (
            self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or set(self.samples_by_decision_end) != set(self.probabilities_by_decision_end)
            or not self.samples_by_decision_end
            or any(
                not math.isfinite(value) or not 0 <= value <= 1
                for value in self.probabilities_by_decision_end.values()
            )
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.model_parameter_hash)
        ):
            raise ValueError("KIS daily L2 logistic decision model is invalid")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < self.lookback:
            raise ValueError("KIS daily L2 logistic control requires 20 completed daily bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        probability = self.probabilities_by_decision_end.get(latest.end_ts)
        if sample is None or probability is None or latest.symbol != self.symbol:
            raise ValueError("KIS daily L2 logistic control received a non-validation decision")
        tail = tuple(bars[-KIS_DAILY_SEQUENCE_LENGTH:])
        if (
            tail[0].start_ts != sample.history_start
            or tail[-1].start_ts != sample.decision_start
            or tail[-1].end_ts != sample.decision_end
            or any(not bar.complete for bar in tail)
        ):
            raise ValueError("KIS daily L2 logistic control cannot use future or cross-phase data")
        action: Literal["buy", "hold"] = (
            "buy" if probability >= KIS_DAILY_L2_LOGISTIC_CONTROL_THRESHOLD else "hold"
        )
        confidence = Decimal(str(probability))
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason="kis_daily_l2_logistic_control",
            timeframe=Timeframe.D1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID,
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "candidate_id": KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID,
                "decision_rule": "fixed_l2_logistic_threshold",
                "threshold": KIS_DAILY_L2_LOGISTIC_CONTROL_THRESHOLD,
                "precommit_hash": self.precommit_hash,
                "model_parameter_hash": self.model_parameter_hash,
                "validation_only": True,
            },
        )


def build_kis_daily_l2_logistic_control_input(
    catalog: KisPaperPrivateDailyCatalog,
) -> KisDailyL2LogisticControlInput:
    """Freeze one QQQ/SPY pair input without reading a validation label for fitting."""

    sequence_input = build_kis_daily_sequence_screen_input(catalog)
    campaign = replace(
        sequence_input.campaign,
        campaign_id=KIS_DAILY_L2_LOGISTIC_CONTROL_ID,
        deterministic_seed=KIS_DAILY_L2_LOGISTIC_CONTROL_DETERMINISTIC_SEED,
    )
    return KisDailyL2LogisticControlInput(
        sequence_input=sequence_input,
        campaign=campaign,
        spec=KisDailyL2LogisticControlSpec(),
    )


def fit_kis_daily_l2_logistic_control(
    control_input: KisDailyL2LogisticControlInput,
) -> KisDailyL2LogisticControlModel:
    """Fit the fixed full-batch logistic control from development samples only."""

    samples = control_input.sequence_input.development_samples
    if not samples or any(sample.label is None for sample in samples):
        raise ValueError("KIS daily L2 logistic control requires development labels")
    numpy = _numpy()
    features = numpy.asarray(
        [_flatten_features(sample.features) for sample in samples], dtype=numpy.float64
    )
    labels = numpy.asarray([sample.label for sample in samples], dtype=numpy.float64)
    if (
        features.shape != (len(samples), KIS_DAILY_L2_LOGISTIC_CONTROL_FEATURE_WIDTH)
        or labels.shape != (len(samples),)
        or not numpy.isfinite(features).all()
        or not numpy.isfinite(labels).all()
    ):
        raise ValueError("KIS daily L2 logistic control development matrix is invalid")

    weights = numpy.zeros(KIS_DAILY_L2_LOGISTIC_CONTROL_FEATURE_WIDTH, dtype=numpy.float64)
    intercept = 0.0
    for _ in range(control_input.spec.steps):
        logits = numpy.clip(features @ weights + intercept, -60.0, 60.0)
        probabilities = 1.0 / (1.0 + numpy.exp(-logits))
        residuals = probabilities - labels
        gradient_weights = (
            features.T @ residuals / len(samples) + control_input.spec.l2_penalty * weights
        )
        gradient_intercept = float(residuals.mean())
        weights -= control_input.spec.learning_rate * gradient_weights
        intercept -= control_input.spec.learning_rate * gradient_intercept
        if not numpy.isfinite(weights).all() or not math.isfinite(intercept):
            raise ValueError("KIS daily L2 logistic control training diverged")
    return KisDailyL2LogisticControlModel(
        spec=control_input.spec,
        development_input_hash=control_input.sequence_input.development_input_hash,
        standardizer_hash=control_input.sequence_input.standardizer.standardizer_hash,
        weights=tuple(float(value) for value in weights),
        intercept=float(intercept),
    )


def run_kis_daily_l2_logistic_control(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
) -> KisDailyL2LogisticControlRun:
    """Run one offline, CPU-only descriptive control and fixed naive comparisons."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    _reject_repo_path(resolved_artifact_root, repo_root=_MODULE_REPOSITORY_ROOT)
    control_root = (resolved_artifact_root / KIS_DAILY_L2_LOGISTIC_CONTROL_ID).resolve()
    _reject_repo_path(control_root, repo_root=resolved_repo_root)
    _reject_repo_path(control_root, repo_root=_MODULE_REPOSITORY_ROOT)
    output_dir = (control_root / run_label).resolve()
    if not output_dir.is_relative_to(control_root):
        raise ValueError("KIS daily L2 logistic control artifact path escapes its root")
    _reject_repo_path(output_dir, repo_root=resolved_repo_root)
    _reject_repo_path(output_dir, repo_root=_MODULE_REPOSITORY_ROOT)
    if output_dir.exists():
        raise FileExistsError("KIS daily L2 logistic control artifact already exists")

    control_input = build_kis_daily_l2_logistic_control_input(catalog)
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(control_input)
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, precommit_payload)

    try:
        model = fit_kis_daily_l2_logistic_control(control_input)
        model_path = output_dir / "l2-logistic-model.json"
        _write_json_new(
            model_path,
            {
                **model.to_payload(),
                "campaign_contract_hash": control_input.campaign.contract_hash,
                "precommit_hash": precommit_hash,
                "raw_market_data_written": False,
            },
        )
        replay_cells = _run_model_replays(
            control_input=control_input,
            model=model,
            precommit_hash=precommit_hash,
            artifact_root=resolved_artifact_root,
            output_dir=output_dir,
            repo_root=resolved_repo_root,
            run_label=run_label,
        )
        baseline_cells = _run_baseline_replays(
            control_input=control_input,
            artifact_root=resolved_artifact_root,
            output_dir=output_dir,
            repo_root=resolved_repo_root,
            run_label=run_label,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": "incomplete",
                "control_id": KIS_DAILY_L2_LOGISTIC_CONTROL_ID,
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "promotion_allowed": False,
                "raw_market_data_written": False,
            },
        )
        raise

    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            control_input=control_input,
            precommit_hash=precommit_hash,
            model=model,
            replay_cells=replay_cells,
            baseline_cells=baseline_cells,
        ),
    )
    return KisDailyL2LogisticControlRun(
        control_input=control_input,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        model=model,
        model_path=model_path,
        replay_cells=replay_cells,
        baseline_cells=baseline_cells,
        summary_path=summary_path,
    )


def _precommit_payload(control_input: KisDailyL2LogisticControlInput) -> dict[str, object]:
    sequence_input = control_input.sequence_input
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "precommitted",
        "control_id": KIS_DAILY_L2_LOGISTIC_CONTROL_ID,
        "claim": (
            "fixed CPU L2 logistic control and fixed naive comparators; descriptive "
            "validation only, with no winner, selection, ensemble, promotion, "
            "profitability claim, or paper-order decision"
        ),
        "source": {
            "dataset_id": sequence_input.catalog.dataset_id,
            "dataset_hash": sequence_input.catalog.dataset_hash,
            "index_hash": sequence_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "adjustment_mode": sequence_input.catalog.adjustment_mode,
            "limitations": list(sequence_input.catalog.raw_price_limitations),
            "source_mixing_allowed": False,
        },
        "campaign_contract_hash": control_input.campaign.contract_hash,
        "chronological_split": sequence_input.split.to_payload(),
        "model": control_input.spec.to_payload(),
        "training": {
            "development_input_hash": sequence_input.development_input_hash,
            "development_sample_count": len(sequence_input.development_samples),
            "fit_split": "pooled_qqq_spy_development_only",
            "row_shuffle": False,
            "gpu_used": False,
            "stop_rule": "fixed_steps_or_nonfinite_parameters_or_nonlocal_paper_replay",
        },
        "replay_sizing": _replay_sizing_payload(),
        "validation": {
            "validation_input_hash": sequence_input.validation_input_hash,
            "sample_counts": {
                symbol: len(samples)
                for symbol, samples in sequence_input.validation_samples_by_symbol.items()
            },
            "labels_materialized_for_fit": False,
            "tuning_allowed": False,
        },
        "comparators": list(control_input.campaign.naive_baselines),
        "target": {
            "decision": "completed_daily_bar_close",
            "entry": "next_observed_daily_open",
            "exit": "following_observed_daily_open",
            "replay_fill_source": LOCAL_PAPER_SOURCE,
            "non_overlapping_decision_stride_sessions": 2,
        },
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "sealed_holdout_materialized": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "model_parameters_written": True,
            "raw_market_data_written": False,
        },
    }


def _run_model_replays(
    *,
    control_input: KisDailyL2LogisticControlInput,
    model: KisDailyL2LogisticControlModel,
    precommit_hash: str,
    artifact_root: Path,
    output_dir: Path,
    repo_root: Path,
    run_label: str,
) -> tuple[KisDailyL2LogisticReplayCell, ...]:
    cells: list[KisDailyL2LogisticReplayCell] = []
    sequence_input = control_input.sequence_input
    for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
        samples = sequence_input.validation_samples_by_symbol[symbol]
        probabilities = tuple(model.probability(sample.features) for sample in samples)
        prediction_hash = _sha256_payload(
            {
                "precommit_hash": precommit_hash,
                "model_parameter_hash": model.parameter_hash,
                "symbol": symbol,
                "validation_input_hash": sequence_input.validation_input_hash,
                "probabilities": [format(value, ".17g") for value in probabilities],
            }
        )
        decision_model = _KisDailyL2LogisticDecisionModel(
            symbol=symbol,
            samples_by_decision_end={sample.decision_end: sample for sample in samples},
            probabilities_by_decision_end={
                sample.decision_end: probability
                for sample, probability in zip(samples, probabilities, strict=True)
            },
            precommit_hash=precommit_hash,
            model_parameter_hash=model.parameter_hash,
        )
        replay = run_campaign_model_replay(
            sequence_input.catalog.bars_by_symbol[symbol],
            campaign=control_input.campaign,
            model=decision_model,
            run_id=(
                f"{KIS_DAILY_L2_LOGISTIC_CONTROL_ID}-"
                f"{KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID}-{symbol.lower()}-{run_label}"
            ),
            artifact_root=artifact_root,
            work_dir=(output_dir / "work" / KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID / symbol),
            phase="validation",
            fold_id=KIS_DAILY_SEQUENCE_FOLD_ID,
            repo_root=repo_root,
            starting_cash=KIS_DAILY_L2_LOGISTIC_CONTROL_STARTING_CASH,
            quantity=KIS_DAILY_L2_LOGISTIC_CONTROL_QUANTITY,
            eligible_signal_starts=frozenset(sample.decision_start for sample in samples),
            emergency_reason="kis_daily_l2_logistic_control_validation_only",
        )
        cells.append(
            KisDailyL2LogisticReplayCell(
                symbol=symbol,
                prediction_hash=prediction_hash,
                replay=replay,
            )
        )
    return tuple(cells)


def _run_baseline_replays(
    *,
    control_input: KisDailyL2LogisticControlInput,
    artifact_root: Path,
    output_dir: Path,
    repo_root: Path,
    run_label: str,
) -> tuple[KisDailyL2LogisticBaselineCell, ...]:
    cells: list[KisDailyL2LogisticBaselineCell] = []
    sequence_input = control_input.sequence_input
    for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
        eligible_signal_starts = frozenset(
            sample.decision_start for sample in sequence_input.validation_samples_by_symbol[symbol]
        )
        for baseline_id in control_input.campaign.naive_baselines:
            replay = run_naive_cpu_baseline(
                sequence_input.catalog.bars_by_symbol[symbol],
                campaign=control_input.campaign,
                artifact_root=artifact_root,
                work_dir=output_dir / "work" / "naive" / symbol / baseline_id,
                phase="validation",
                fold_id=KIS_DAILY_SEQUENCE_FOLD_ID,
                baseline_id=baseline_id,
                repo_root=repo_root,
                starting_cash=KIS_DAILY_L2_LOGISTIC_CONTROL_STARTING_CASH,
                quantity=KIS_DAILY_L2_LOGISTIC_CONTROL_QUANTITY,
                run_label=f"{run_label}-{symbol.lower()}",
                eligible_signal_starts=eligible_signal_starts,
            )
            cells.append(
                KisDailyL2LogisticBaselineCell(
                    symbol=symbol,
                    baseline_id=baseline_id,
                    replay=replay,
                )
            )
    return tuple(cells)


def _summary_payload(
    *,
    control_input: KisDailyL2LogisticControlInput,
    precommit_hash: str,
    model: KisDailyL2LogisticControlModel,
    replay_cells: tuple[KisDailyL2LogisticReplayCell, ...],
    baseline_cells: tuple[KisDailyL2LogisticBaselineCell, ...],
) -> dict[str, object]:
    sequence_input = control_input.sequence_input
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "claim": (
            "fixed CPU L2 logistic control and fixed naive comparator evidence only; not a "
            "winner, selection, ensemble, promotion, profitability claim, or paper order"
        ),
        "source": {
            "dataset_id": sequence_input.catalog.dataset_id,
            "dataset_hash": sequence_input.catalog.dataset_hash,
            "index_hash": sequence_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "adjustment_mode": sequence_input.catalog.adjustment_mode,
            "limitations": list(sequence_input.catalog.raw_price_limitations),
        },
        "campaign_contract_hash": control_input.campaign.contract_hash,
        "chronological_split": sequence_input.split.to_payload(),
        "precommit": {
            "hash": precommit_hash,
            "written_before_fit": True,
            "written_before_validation_replay": True,
        },
        "model": {
            "candidate_id": KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID,
            "parameter_hash": model.parameter_hash,
            "development_input_hash": model.development_input_hash,
            "standardizer_hash": model.standardizer_hash,
            "spec": model.spec.to_payload(),
        },
        "validation": {
            "input_hash": sequence_input.validation_input_hash,
            "labels_materialized_for_fit": False,
            "tuning_allowed": False,
        },
        "replay_sizing": _replay_sizing_payload(),
        "replay_cells": [
            _model_replay_payload(cell)
            for cell in replay_cells
        ],
        "baseline_cells": [
            _baseline_replay_payload(cell)
            for cell in baseline_cells
        ],
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "sealed_holdout_materialized": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "model_parameters_written": True,
            "raw_market_data_written": False,
        },
    }


def _model_replay_payload(cell: KisDailyL2LogisticReplayCell) -> dict[str, object]:
    result = cell.replay.result
    return {
        "candidate_id": KIS_DAILY_L2_LOGISTIC_CONTROL_CANDIDATE_ID,
        "symbol": cell.symbol,
        "prediction_hash": cell.prediction_hash,
        "fill_source": cell.replay.fill_source,
        "decisions_seen": result.decisions_seen,
        "trade_count": len(result.trades),
        "after_cost_pnl": str(result.after_cost_pnl),
        "gross_pnl": str(result.gross_pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "event_jsonl_sha256": cell.replay.replay_evidence.event_jsonl_sha256,
        "state_sqlite_sha256": cell.replay.replay_evidence.state_sqlite_sha256,
    }


def _baseline_replay_payload(cell: KisDailyL2LogisticBaselineCell) -> dict[str, object]:
    result = cell.replay.result
    return {
        "candidate_id": cell.baseline_id,
        "symbol": cell.symbol,
        "fill_source": cell.replay.fill_source,
        "decisions_seen": result.decisions_seen,
        "trade_count": len(result.trades),
        "after_cost_pnl": str(result.after_cost_pnl),
        "gross_pnl": str(result.gross_pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "event_jsonl_sha256": cell.replay.replay_evidence.event_jsonl_sha256,
        "state_sqlite_sha256": cell.replay.replay_evidence.state_sqlite_sha256,
    }


def _flatten_features(features: Sequence[Sequence[float]]) -> tuple[float, ...]:
    flattened = tuple(float(value) for row in features for value in row)
    if (
        len(features) != KIS_DAILY_SEQUENCE_LENGTH
        or any(len(row) != len(KIS_DAILY_SEQUENCE_FEATURE_NAMES) for row in features)
        or len(flattened) != KIS_DAILY_L2_LOGISTIC_CONTROL_FEATURE_WIDTH
        or any(not math.isfinite(value) for value in flattened)
    ):
        raise ValueError("KIS daily L2 logistic control feature geometry is invalid")
    return flattened


def _replay_sizing_payload() -> dict[str, str]:
    return {
        "starting_cash": str(KIS_DAILY_L2_LOGISTIC_CONTROL_STARTING_CASH),
        "quantity": str(KIS_DAILY_L2_LOGISTIC_CONTROL_QUANTITY),
    }


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _numpy():
    import numpy

    return numpy


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_run_label(run_label: str) -> None:
    if (
        not isinstance(run_label, str)
        or not 1 <= len(run_label) <= 80
        or run_label in {".", ".."}
        or any(
            not character.isascii()
            or not (character.isalnum() or character in {".", "_", "-"})
            for character in run_label
        )
    ):
        raise ValueError("KIS daily L2 logistic control run_label is invalid")


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if path.is_relative_to(repo_root):
        raise ValueError(
            "KIS daily L2 logistic control artifacts must stay outside the Git workspace"
        )

"""Frozen source-local FirstRate 5m after-cost CPU control.

This is intentionally one narrow descriptive lineage.  It does not create a
KIS, broker, Paper-consumer, ensemble, or GPU path.  Raw bars and local-paper
events exist only in memory while a replay runs; the external evidence contains
only hashes and aggregate replay facts.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    EmergencyState,
    ModelPrediction,
    Signal,
    Timeframe,
)
from thericher_v2.data.firstrate_free_intraday_timeframe_mechanics import (
    FirstRateCanonicalSpec,
    parse_firstrate_normalization_receipt,
    validate_firstrate_canonical_bars,
)
from thericher_v2.data.local import (
    CatalogedBars,
    LocalCsvBarProvider,
    _cataloged_bars_from_verified_loader,
    bar_to_record,
)
from thericher_v2.data.provider import BarQuery
from thericher_v2.data.resample import resample_bars
from thericher_v2.execution import LOCAL_PAPER_SOURCE, EmergencyStore, replay_local_paper_account

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from .validation import InMemoryCampaignEventStore, ValidationConfig, run_local_paper_validation

FIRSTRATE_M5_AFTER_COST_CONTROL_ID = "firstrate-5m-after-cost-control-v1"
FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS = ("SPY", "QQQ")
FIRSTRATE_M5_OBSERVATION_BARS = 60
FIRSTRATE_M5_FORWARD_BARS = 1
FIRSTRATE_M5_EMBARGO_BARS = FIRSTRATE_M5_OBSERVATION_BARS + FIRSTRATE_M5_FORWARD_BARS
FIRSTRATE_M5_COST_BPS_PER_SIDE = (Decimal("1"), Decimal("3"), Decimal("5"))
FIRSTRATE_M5_DECISION_THRESHOLD = 0.5
FIRSTRATE_M5_TRAIN_FRACTION_NUMERATOR = 7
FIRSTRATE_M5_TRAIN_FRACTION_DENOMINATOR = 10
FIRSTRATE_M5_MIN_DEVELOPMENT_SAMPLES = 32
FIRSTRATE_M5_MIN_VALIDATION_SAMPLES = 16
FIRSTRATE_M5_L2_PENALTY = 0.01
FIRSTRATE_M5_LEARNING_RATE = 0.05
FIRSTRATE_M5_TRAINING_STEPS = 240
FIRSTRATE_M5_STARTING_CASH = Decimal("10000")
FIRSTRATE_M5_QUANTITY = Decimal("1")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_NORMALIZATION_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/"
    "firstrate-free-intraday-source-local-normalization-v1.json"
)
_SHA256_PREFIX = "sha256:"
_RUN_STATUSES = frozenset({"complete", "input_unavailable"})
_CLASSIFICATIONS = frozenset({"rejected", "inconclusive", "eligible_to_propose_gpu"})


class FirstRateM5InputUnavailable(ValueError):
    """The frozen source-local geometry cannot support this control."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class FirstRateM5Sample:
    """One 60-bar causal observation and next-bar directional label."""

    symbol: str
    history_start: datetime
    decision_start: datetime
    decision_end: datetime
    target_start: datetime
    exit_start: datetime
    features: tuple[float, ...]
    label: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(float(value) for value in self.features))
        if (
            self.symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or len(self.features) != FIRSTRATE_M5_OBSERVATION_BARS
            or any(not math.isfinite(value) for value in self.features)
            or self.label not in {0, 1}
            or not (
                self.history_start <= self.decision_start < self.decision_end
                <= self.target_start < self.exit_start
            )
        ):
            raise ValueError("FirstRate M5 sample geometry is invalid")


@dataclass(frozen=True)
class FirstRateM5Split:
    """Per-symbol chronological development and validation samples."""

    development_window: CampaignWindow
    validation_window: CampaignWindow
    development_samples: tuple[FirstRateM5Sample, ...]
    validation_samples: tuple[FirstRateM5Sample, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "development_samples", tuple(self.development_samples))
        object.__setattr__(self, "validation_samples", tuple(self.validation_samples))
        if (
            len(self.development_samples) < FIRSTRATE_M5_MIN_DEVELOPMENT_SAMPLES
            or len(self.validation_samples) < FIRSTRATE_M5_MIN_VALIDATION_SAMPLES
            or self.development_window.end_utc
            + timedelta(minutes=5 * FIRSTRATE_M5_EMBARGO_BARS)
            > self.validation_window.start_utc
        ):
            raise ValueError("FirstRate M5 chronological split is invalid")


@dataclass(frozen=True)
class FirstRateM5Stream:
    symbol: str
    catalog: CatalogedBars
    canonical_sha256: str
    resampled_content_sha256: str
    resampled_timestamp_set_sha256: str
    source_bar_count: int
    resampled_bar_count: int
    sample_count: int
    input_hash: str
    split: FirstRateM5Split

    def __post_init__(self) -> None:
        if (
            self.symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or self.catalog.bars[0].symbol != self.symbol
            or self.catalog.bars[0].timeframe != Timeframe.M5
            or self.source_bar_count <= 0
            or self.resampled_bar_count <= 0
            or self.sample_count <= 0
            or not all(
                _is_sha256(value)
                for value in (
                    self.catalog.dataset_hash,
                    self.canonical_sha256,
                    self.resampled_content_sha256,
                    self.resampled_timestamp_set_sha256,
                    self.input_hash,
                )
            )
        ):
            raise ValueError("FirstRate M5 stream attestation is invalid")


@dataclass(frozen=True)
class FirstRateM5ControlInput:
    normalization_receipt_sha256: str
    streams: Mapping[str, FirstRateM5Stream]
    input_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "streams", MappingProxyType(dict(self.streams)))
        if (
            tuple(self.streams) != FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or not _is_sha256(self.normalization_receipt_sha256)
            or not _is_sha256(self.input_hash)
        ):
            raise ValueError("FirstRate M5 control input is invalid")

    def source_attestation_payload(self) -> dict[str, object]:
        return {
            "normalization_receipt_sha256": self.normalization_receipt_sha256,
            "resampling": {
                "source_timeframe": Timeframe.M1.value,
                "target_timeframe": Timeframe.M5.value,
                "bucket_anchor": "utc_epoch",
                "bucket_retention": "complete_unique_contiguous_source_minutes_only",
                "reindex_or_fill": False,
            },
            "symbols": [
                {
                    "symbol": stream.symbol,
                    "canonical_sha256": stream.canonical_sha256,
                    "resampled_content_sha256": stream.resampled_content_sha256,
                    "resampled_timestamp_set_sha256": stream.resampled_timestamp_set_sha256,
                    "source_bar_count": stream.source_bar_count,
                    "resampled_bar_count": stream.resampled_bar_count,
                    "complete_contiguous_sample_count": stream.sample_count,
                    "development_sample_count": len(stream.split.development_samples),
                    "validation_sample_count": len(stream.split.validation_samples),
                    "development_input_sha256": _samples_hash(stream.split.development_samples),
                    "validation_input_sha256": _samples_hash(stream.split.validation_samples),
                }
                for stream in self.streams.values()
            ],
            "control_input_sha256": self.input_hash,
        }


@dataclass(frozen=True)
class FirstRateM5L2Model:
    symbol: str
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    intercept: float
    development_input_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "means", tuple(float(value) for value in self.means))
        object.__setattr__(self, "scales", tuple(float(value) for value in self.scales))
        object.__setattr__(self, "weights", tuple(float(value) for value in self.weights))
        if (
            self.symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or any(
                len(values) != FIRSTRATE_M5_OBSERVATION_BARS
                for values in (self.means, self.scales, self.weights)
            )
            or any(
                not math.isfinite(value)
                for value in (*self.means, *self.scales, *self.weights, self.intercept)
            )
            or any(value <= 0 for value in self.scales)
            or not _is_sha256(self.development_input_hash)
        ):
            raise ValueError("FirstRate M5 L2 logistic model is invalid")

    @property
    def standardizer_hash(self) -> str:
        return _sha256_payload(
            {
                "means": [format(value, ".17g") for value in self.means],
                "scales": [format(value, ".17g") for value in self.scales],
            }
        )

    @property
    def parameter_hash(self) -> str:
        return _sha256_payload(
            {
                "symbol": self.symbol,
                "weights": [format(value, ".17g") for value in self.weights],
                "intercept": format(self.intercept, ".17g"),
                "standardizer_hash": self.standardizer_hash,
                "development_input_hash": self.development_input_hash,
            }
        )

    def probability(self, features: tuple[float, ...]) -> float:
        if len(features) != FIRSTRATE_M5_OBSERVATION_BARS:
            raise ValueError("FirstRate M5 L2 logistic feature width is invalid")
        value = self.intercept + sum(
            weight * ((feature - mean) / scale)
            for feature, mean, scale, weight in zip(
                features,
                self.means,
                self.scales,
                self.weights,
                strict=True,
            )
        )
        return _sigmoid(value)

    def to_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "model_family": "l2_logistic",
            "parameter_hash": self.parameter_hash,
            "standardizer_hash": self.standardizer_hash,
            "development_input_sha256": self.development_input_hash,
            "weights": [format(value, ".17g") for value in self.weights],
            "intercept": format(self.intercept, ".17g"),
            "means": [format(value, ".17g") for value in self.means],
            "scales": [format(value, ".17g") for value in self.scales],
        }


@dataclass(frozen=True)
class FirstRateM5ReplayCell:
    candidate_id: Literal["l2_logistic", "always_flat", "previous_bar_direction"]
    symbol: str
    cost_bps_per_side: Decimal
    decisions_seen: int
    local_paper_fill_count: int
    all_fills_local_paper: bool
    replayable: bool
    terminal_flat: bool
    after_cost_pnl: Decimal
    gross_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "cost_bps_per_side": str(self.cost_bps_per_side),
            "decisions_seen": self.decisions_seen,
            "local_paper_fill_count": self.local_paper_fill_count,
            "fill_source": LOCAL_PAPER_SOURCE,
            "all_fills_local_paper": self.all_fills_local_paper,
            "replayable": self.replayable,
            "terminal_flat": self.terminal_flat,
            "after_cost_pnl": str(self.after_cost_pnl),
            "gross_pnl": str(self.gross_pnl),
            "total_fees": str(self.total_fees),
            "total_slippage": str(self.total_slippage),
        }


@dataclass(frozen=True)
class FirstRateM5CostControlRun:
    status: Literal["complete", "input_unavailable"]
    run_label: str
    output_dir: Path
    precommit_path: Path | None
    model_path: Path | None
    summary_path: Path | None
    input_unavailable_path: Path | None
    classification: str | None


@dataclass(frozen=True)
class FirstRateM5ValidationReceipt:
    classification: Literal["rejected", "inconclusive", "eligible_to_propose_gpu"]
    validation_path: Path
    source_reattached: bool


@dataclass(frozen=True)
class _DecisionModel:
    symbol: str
    candidate_id: Literal["l2_logistic", "always_flat", "previous_bar_direction"]
    samples_by_decision_end: Mapping[datetime, FirstRateM5Sample]
    probabilities_by_decision_end: Mapping[datetime, float] | None = None
    parameter_hash: str | None = None
    precommit_hash: str | None = None
    lookback: int = FIRSTRATE_M5_OBSERVATION_BARS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "samples_by_decision_end",
            MappingProxyType(dict(self.samples_by_decision_end)),
        )
        if self.probabilities_by_decision_end is not None:
            object.__setattr__(
                self,
                "probabilities_by_decision_end",
                MappingProxyType(dict(self.probabilities_by_decision_end)),
            )
        if (
            self.symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or self.candidate_id
            not in {"l2_logistic", "always_flat", "previous_bar_direction"}
            or not self.samples_by_decision_end
            or any(sample.symbol != self.symbol for sample in self.samples_by_decision_end.values())
        ):
            raise ValueError("FirstRate M5 decision model is invalid")
        if self.candidate_id == "l2_logistic":
            probabilities = self.probabilities_by_decision_end
            if (
                probabilities is None
                or set(probabilities) != set(self.samples_by_decision_end)
                or any(
                    not math.isfinite(value) or not 0 <= value <= 1
                    for value in probabilities.values()
                )
                or not _is_sha256(self.parameter_hash)
                or not _is_sha256(self.precommit_hash)
            ):
                raise ValueError("FirstRate M5 logistic decision model is invalid")
        elif self.probabilities_by_decision_end is not None:
            raise ValueError("FirstRate M5 baseline must not carry probabilities")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < self.lookback:
            raise ValueError("FirstRate M5 decision requires 60 completed bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        if sample is None or latest.symbol != self.symbol:
            raise ValueError("FirstRate M5 decision received an unfrozen validation bar")
        tail = tuple(bars[-self.lookback :])
        if (
            tail[0].start_ts != sample.history_start
            or tail[-1].start_ts != sample.decision_start
            or tail[-1].end_ts != sample.decision_end
            or any(not bar.complete or bar.timeframe != Timeframe.M5 for bar in tail)
            or any(
                current.start_ts - prior.start_ts != Timeframe.M5.duration
                for prior, current in zip(tail[:-1], tail[1:], strict=True)
            )
        ):
            raise ValueError("FirstRate M5 decision cannot cross a source gap or phase")
        if self.candidate_id == "l2_logistic":
            probability = self.probabilities_by_decision_end[latest.end_ts]  # type: ignore[index]
            action: Literal["buy", "hold"] = (
                "buy" if probability >= FIRSTRATE_M5_DECISION_THRESHOLD else "hold"
            )
            reason = "firstrate_m5_l2_logistic_control"
            metadata: dict[str, object] = {
                "candidate_id": self.candidate_id,
                "threshold": FIRSTRATE_M5_DECISION_THRESHOLD,
                "parameter_hash": self.parameter_hash,
                "precommit_hash": self.precommit_hash,
                "validation_only": True,
            }
        elif self.candidate_id == "always_flat":
            probability = 0.0
            action = "hold"
            reason = "firstrate_m5_always_flat_control"
            metadata = {"candidate_id": self.candidate_id, "validation_only": True}
        else:
            probability = 1.0 if latest.close > latest.open else 0.0
            action = "buy" if probability >= FIRSTRATE_M5_DECISION_THRESHOLD else "hold"
            reason = "firstrate_m5_previous_bar_direction_control"
            metadata = {"candidate_id": self.candidate_id, "validation_only": True}
        confidence = Decimal(str(probability))
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=reason,
            timeframe=Timeframe.M5,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=f"firstrate_m5_{self.candidate_id}",
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata=metadata,
        )


def build_firstrate_m5_after_cost_control_input(
    *,
    market_data_root: Path | str = _DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path | str = _DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str = _REPO_ROOT,
) -> FirstRateM5ControlInput:
    """Reattest canonical M1 input and derive the frozen M5 geometry in memory."""

    resolved_repo_root = Path(repo_root).resolve()
    resolved_market_data_root = _require_external_root(
        market_data_root,
        repo_root=resolved_repo_root,
        field_name="market_data_root",
    )
    resolved_artifact_root = _require_external_root(
        artifact_root,
        repo_root=resolved_repo_root,
        field_name="artifact_root",
    )
    normalization_path = _path_within_root(
        resolved_artifact_root,
        _NORMALIZATION_RECEIPT_RELATIVE_PATH,
        field_name="normalization_receipt_path",
    )
    normalization_bytes = normalization_path.read_bytes()
    normalization_sha256 = _sha256(normalization_bytes)
    specs = parse_firstrate_normalization_receipt(normalization_bytes)
    streams: dict[str, FirstRateM5Stream] = {}
    for spec in specs:
        stream = _load_stream(
            spec=spec,
            market_data_root=resolved_market_data_root,
            normalization_sha256=normalization_sha256,
        )
        streams[stream.symbol] = stream
    if tuple(streams) != FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS:
        raise ValueError("FirstRate M5 source must contain exactly SPY and QQQ")
    input_hash = _sha256_payload(
        {
            "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
            "normalization_receipt_sha256": normalization_sha256,
            "streams": [
                {
                    "symbol": stream.symbol,
                    "input_hash": stream.input_hash,
                    "dataset_hash": stream.catalog.dataset_hash,
                }
                for stream in streams.values()
            ],
        }
    )
    return FirstRateM5ControlInput(
        normalization_receipt_sha256=normalization_sha256,
        streams=streams,
        input_hash=input_hash,
    )


def run_firstrate_m5_after_cost_control(
    *,
    run_label: str,
    market_data_root: Path | str = _DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path | str = _DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str = _REPO_ROOT,
) -> FirstRateM5CostControlRun:
    """Run exactly the predeclared CPU control or record geometry unavailability."""

    _validate_run_label(run_label)
    resolved_repo_root = Path(repo_root).resolve()
    resolved_artifact_root = _require_external_root(
        artifact_root,
        repo_root=resolved_repo_root,
        field_name="artifact_root",
    )
    output_dir = _output_dir(resolved_artifact_root, run_label)
    if output_dir.exists():
        raise FileExistsError("FirstRate M5 control run label already has external evidence")
    try:
        control_input = build_firstrate_m5_after_cost_control_input(
            market_data_root=market_data_root,
            artifact_root=resolved_artifact_root,
            repo_root=resolved_repo_root,
        )
    except FirstRateM5InputUnavailable as error:
        output_dir.mkdir(parents=True, exist_ok=False)
        unavailable_path = output_dir / "input-unavailable.json"
        _write_json_new(
            unavailable_path,
            {
                "schema_version": SCHEMA_VERSION,
                "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
                "status": "input_unavailable",
                "reason_code": error.reason_code,
                "fit_started": False,
                "gpu_used": False,
                "network_access": False,
                "credentials_read": False,
                "kis_or_broker_called": False,
                "raw_market_data_written": False,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "promotion_allowed": False,
            },
        )
        return FirstRateM5CostControlRun(
            status="input_unavailable",
            run_label=run_label,
            output_dir=output_dir,
            precommit_path=None,
            model_path=None,
            summary_path=None,
            input_unavailable_path=unavailable_path,
            classification=None,
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(control_input)
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, precommit_payload)
    try:
        models = {
            symbol: _fit_l2_logistic(stream)
            for symbol, stream in control_input.streams.items()
        }
        model_payload = {
            "schema_version": SCHEMA_VERSION,
            "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
            "precommit_hash": precommit_hash,
            "gpu_used": False,
            "model_parameters_written": True,
            "raw_market_data_written": False,
            "models": [model.to_payload() for model in models.values()],
        }
        model_path = output_dir / "l2-logistic-model.json"
        _write_json_new(model_path, model_payload)
        model_sha256 = _sha256(model_path.read_bytes())
        replay_cells = _run_replay_matrix(
            control_input=control_input,
            models=models,
            precommit_hash=precommit_hash,
            artifact_root=resolved_artifact_root,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "fit_started": True,
                "gpu_used": False,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "promotion_allowed": False,
                "raw_market_data_written": False,
            },
        )
        raise

    classification = _classify_replay_cells(replay_cells)
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            control_input=control_input,
            precommit_hash=precommit_hash,
            models=models,
            model_sha256=model_sha256,
            replay_cells=replay_cells,
            classification=classification,
        ),
    )
    return FirstRateM5CostControlRun(
        status="complete",
        run_label=run_label,
        output_dir=output_dir,
        precommit_path=precommit_path,
        model_path=model_path,
        summary_path=summary_path,
        input_unavailable_path=None,
        classification=classification,
    )


def validate_firstrate_m5_after_cost_control(
    *,
    run_label: str,
    market_data_root: Path | str = _DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path | str = _DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str = _REPO_ROOT,
) -> FirstRateM5ValidationReceipt:
    """Independently reattach the frozen source, contract, and aggregate result."""

    _validate_run_label(run_label)
    resolved_repo_root = Path(repo_root).resolve()
    resolved_artifact_root = _require_external_root(
        artifact_root,
        repo_root=resolved_repo_root,
        field_name="artifact_root",
    )
    output_dir = _output_dir(resolved_artifact_root, run_label)
    precommit_path = output_dir / "precommit.json"
    model_path = output_dir / "l2-logistic-model.json"
    summary_path = output_dir / "summary.json"
    precommit = _read_json(precommit_path, field_name="precommit")
    model = _read_json(model_path, field_name="model")
    summary = _read_json(summary_path, field_name="summary")
    precommit_hash = _verify_precommit(precommit)
    control_input = build_firstrate_m5_after_cost_control_input(
        market_data_root=market_data_root,
        artifact_root=resolved_artifact_root,
        repo_root=resolved_repo_root,
    )
    expected_attestation = control_input.source_attestation_payload()
    if (
        precommit.get("control_id") != FIRSTRATE_M5_AFTER_COST_CONTROL_ID
        or precommit.get("input_attestation") != expected_attestation
        or summary.get("precommit_hash") != precommit_hash
        or summary.get("input_attestation") != expected_attestation
        or model.get("precommit_hash") != precommit_hash
        or summary.get("model_artifact_sha256") != _sha256(model_path.read_bytes())
    ):
        raise ValueError("FirstRate M5 control evidence binding is invalid")
    _validate_frozen_payload(precommit)
    _validate_model_payload(model, expected_precommit_hash=precommit_hash)
    replay_cells = _parse_replay_cells(summary)
    classification = _classify_replay_cells(replay_cells)
    if (
        summary.get("status") != "complete"
        or summary.get("classification") != classification
        or summary.get("selection_allowed") is not False
        or summary.get("ensemble_allowed") is not False
        or summary.get("promotion_allowed") is not False
        or summary.get("gpu_used") is not False
        or summary.get("network_access") is not False
        or summary.get("credentials_read") is not False
        or summary.get("kis_or_broker_called") is not False
        or summary.get("raw_market_data_written") is not False
    ):
        raise ValueError("FirstRate M5 control summary is invalid")
    validation_path = output_dir / "validation.json"
    validation_payload = {
        "schema_version": SCHEMA_VERSION,
        "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
        "status": "completed",
        "precommit_hash": precommit_hash,
        "model_artifact_sha256": _sha256(model_path.read_bytes()),
        "summary_sha256": _sha256(summary_path.read_bytes()),
        "source_reattached": True,
        "control_input_sha256": control_input.input_hash,
        "classification": classification,
        "validation_tuned_configuration": False,
        "gpu_used": False,
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "paper_or_execution_consumer_created": False,
        "limitations": [
            "source_local_retrospective_control_only",
            "source_timestamp_semantics_unverified",
            "session_coverage_not_assessed",
            "synthetic_cost_band_is_not_kis_execution_parity",
            "no_kis_or_paper_consumer",
        ],
    }
    _write_or_verify(validation_path, validation_payload)
    return FirstRateM5ValidationReceipt(
        classification=classification,
        validation_path=validation_path,
        source_reattached=True,
    )


def _load_stream(
    *,
    spec: FirstRateCanonicalSpec,
    market_data_root: Path,
    normalization_sha256: str,
) -> FirstRateM5Stream:
    canonical_path = _path_within_root(
        market_data_root,
        spec.canonical_market_data_relative_path,
        field_name="canonical_path",
    )
    canonical_bytes = canonical_path.read_bytes()
    if _sha256(canonical_bytes) != spec.canonical_sha256:
        raise ValueError("canonical CSV hash does not match normalization receipt")
    source_bars = LocalCsvBarProvider(canonical_path).get_bars(
        BarQuery(symbol=spec.symbol, market=spec.market, timeframe=Timeframe.M1)
    )
    validate_firstrate_canonical_bars(source_bars, spec)
    resampled = resample_bars(source_bars, Timeframe.M5)
    if not resampled:
        raise FirstRateM5InputUnavailable("no_complete_5m_bars")
    if any(bar.timeframe != Timeframe.M5 or not bar.complete for bar in resampled):
        raise ValueError("FirstRate M5 resampling produced an invalid bar")
    timestamps = tuple(bar.start_ts for bar in resampled)
    if timestamps != tuple(sorted(set(timestamps))):
        raise ValueError("FirstRate M5 resampling did not preserve unique ordering")
    samples = _build_samples(spec.symbol, resampled)
    split = _build_split(samples, resampled)
    resampled_content_sha256 = _bars_hash(resampled)
    resampled_timestamp_set_sha256 = _timestamps_hash(timestamps)
    dataset_hash = _sha256_payload(
        {
            "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
            "symbol": spec.symbol,
            "normalization_receipt_sha256": normalization_sha256,
            "canonical_sha256": spec.canonical_sha256,
            "resampled_content_sha256": resampled_content_sha256,
            "resampled_timestamp_set_sha256": resampled_timestamp_set_sha256,
        }
    )
    catalog = _cataloged_bars_from_verified_loader(
        dataset_id=(
            f"firstrate.free.intraday.{spec.symbol.lower()}.m5."
            "source-local-after-cost-control-v1"
        ),
        dataset_hash=dataset_hash,
        source_path=Path("firstrate-source-local-m5-in-memory"),
        bars=tuple(resampled),
    )
    input_hash = _sha256_payload(
        {
            "symbol": spec.symbol,
            "dataset_hash": dataset_hash,
            "sample_hash": _samples_hash(samples),
            "development_sample_hash": _samples_hash(split.development_samples),
            "validation_sample_hash": _samples_hash(split.validation_samples),
        }
    )
    return FirstRateM5Stream(
        symbol=spec.symbol,
        catalog=catalog,
        canonical_sha256=spec.canonical_sha256,
        resampled_content_sha256=resampled_content_sha256,
        resampled_timestamp_set_sha256=resampled_timestamp_set_sha256,
        source_bar_count=len(source_bars),
        resampled_bar_count=len(resampled),
        sample_count=len(samples),
        input_hash=input_hash,
        split=split,
    )


def _build_samples(symbol: str, bars: Sequence[Bar]) -> tuple[FirstRateM5Sample, ...]:
    samples: list[FirstRateM5Sample] = []
    required_tail = FIRSTRATE_M5_FORWARD_BARS + 1
    for decision_index in range(FIRSTRATE_M5_OBSERVATION_BARS - 1, len(bars) - required_tail):
        history = tuple(
            bars[
                decision_index - FIRSTRATE_M5_OBSERVATION_BARS + 1 : decision_index + 1
            ]
        )
        target = bars[decision_index + FIRSTRATE_M5_FORWARD_BARS]
        exit_bar = bars[decision_index + FIRSTRATE_M5_FORWARD_BARS + 1]
        sequence = (*history, target, exit_bar)
        if any(
            current.start_ts - previous.start_ts != Timeframe.M5.duration
            for previous, current in zip(sequence[:-1], sequence[1:], strict=True)
        ):
            continue
        base_close = history[0].close
        if base_close <= 0:
            raise ValueError("FirstRate M5 control requires positive closes")
        features = tuple(float((bar.close / base_close) - Decimal("1")) for bar in history)
        samples.append(
            FirstRateM5Sample(
                symbol=symbol,
                history_start=history[0].start_ts,
                decision_start=history[-1].start_ts,
                decision_end=history[-1].end_ts,
                target_start=target.start_ts,
                exit_start=exit_bar.start_ts,
                features=features,
                label=1 if target.close > target.open else 0,
            )
        )
    if not samples:
        raise FirstRateM5InputUnavailable("no_complete_contiguous_60bar_windows")
    return tuple(samples)


def _build_split(
    samples: tuple[FirstRateM5Sample, ...], bars: Sequence[Bar]
) -> FirstRateM5Split:
    if len(samples) < FIRSTRATE_M5_MIN_DEVELOPMENT_SAMPLES + FIRSTRATE_M5_MIN_VALIDATION_SAMPLES:
        raise FirstRateM5InputUnavailable("insufficient_complete_contiguous_5m_samples")
    split_index = (len(samples) * FIRSTRATE_M5_TRAIN_FRACTION_NUMERATOR) // (
        FIRSTRATE_M5_TRAIN_FRACTION_DENOMINATOR
    )
    split_index = max(FIRSTRATE_M5_MIN_DEVELOPMENT_SAMPLES, split_index)
    if split_index >= len(samples):
        raise FirstRateM5InputUnavailable("chronological_split_unavailable")
    development_candidates = samples[:split_index]
    split_end = development_candidates[-1].exit_start + Timeframe.M5.duration
    embargo = timedelta(minutes=5 * FIRSTRATE_M5_EMBARGO_BARS)
    validation_candidates = tuple(
        sample for sample in samples[split_index:] if sample.history_start >= split_end + embargo
    )
    if len(validation_candidates) < FIRSTRATE_M5_MIN_VALIDATION_SAMPLES:
        raise FirstRateM5InputUnavailable("embargoed_validation_geometry_unavailable")
    development = tuple(
        sample for sample in development_candidates if sample.exit_start < split_end
    )
    if len(development) < FIRSTRATE_M5_MIN_DEVELOPMENT_SAMPLES:
        raise FirstRateM5InputUnavailable("development_geometry_unavailable")
    validation_start = validation_candidates[0].history_start
    validation_end = validation_candidates[-1].exit_start + Timeframe.M5.duration
    if validation_end <= validation_start or not bars:
        raise FirstRateM5InputUnavailable("validation_window_unavailable")
    return FirstRateM5Split(
        development_window=CampaignWindow(
            start_utc=bars[0].start_ts,
            end_utc=split_end,
        ),
        validation_window=CampaignWindow(
            start_utc=validation_start,
            end_utc=validation_end,
        ),
        development_samples=development,
        validation_samples=validation_candidates,
    )


def _fit_l2_logistic(stream: FirstRateM5Stream) -> FirstRateM5L2Model:
    samples = stream.split.development_samples
    numpy = _numpy()
    features = numpy.asarray([sample.features for sample in samples], dtype=numpy.float64)
    labels = numpy.asarray([sample.label for sample in samples], dtype=numpy.float64)
    if (
        features.shape != (len(samples), FIRSTRATE_M5_OBSERVATION_BARS)
        or labels.shape != (len(samples),)
        or not numpy.isfinite(features).all()
        or not numpy.isfinite(labels).all()
    ):
        raise ValueError("FirstRate M5 development matrix is invalid")
    means = features.mean(axis=0)
    scales = features.std(axis=0)
    scales = numpy.where(scales > 0, scales, 1.0)
    normalized = (features - means) / scales
    weights = numpy.zeros(FIRSTRATE_M5_OBSERVATION_BARS, dtype=numpy.float64)
    intercept = 0.0
    for _ in range(FIRSTRATE_M5_TRAINING_STEPS):
        logits = numpy.clip(normalized @ weights + intercept, -60.0, 60.0)
        probabilities = 1.0 / (1.0 + numpy.exp(-logits))
        residuals = probabilities - labels
        gradient_weights = (
            normalized.T @ residuals / len(samples) + FIRSTRATE_M5_L2_PENALTY * weights
        )
        gradient_intercept = float(residuals.mean())
        weights -= FIRSTRATE_M5_LEARNING_RATE * gradient_weights
        intercept -= FIRSTRATE_M5_LEARNING_RATE * gradient_intercept
        if not numpy.isfinite(weights).all() or not math.isfinite(intercept):
            raise ValueError("FirstRate M5 L2 logistic training diverged")
    return FirstRateM5L2Model(
        symbol=stream.symbol,
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        weights=tuple(float(value) for value in weights),
        intercept=float(intercept),
        development_input_hash=_samples_hash(samples),
    )


def _run_replay_matrix(
    *,
    control_input: FirstRateM5ControlInput,
    models: Mapping[str, FirstRateM5L2Model],
    precommit_hash: str,
    artifact_root: Path,
) -> tuple[FirstRateM5ReplayCell, ...]:
    cells: list[FirstRateM5ReplayCell] = []
    with tempfile.TemporaryDirectory(
        dir=artifact_root,
        prefix=".firstrate-m5-after-cost-control-",
    ) as temp_dir:
        temporary_root = Path(temp_dir)
        for symbol, stream in control_input.streams.items():
            model = models[symbol]
            probabilities = {
                sample.decision_end: model.probability(sample.features)
                for sample in stream.split.validation_samples
            }
            for cost_bps in FIRSTRATE_M5_COST_BPS_PER_SIDE:
                campaign = _campaign_for(stream, cost_bps)
                model_specs = (
                    (
                        "l2_logistic",
                        _DecisionModel(
                            symbol=symbol,
                            candidate_id="l2_logistic",
                            samples_by_decision_end={
                                sample.decision_end: sample
                                for sample in stream.split.validation_samples
                            },
                            probabilities_by_decision_end=probabilities,
                            parameter_hash=model.parameter_hash,
                            precommit_hash=precommit_hash,
                        ),
                    ),
                    (
                        "always_flat",
                        _DecisionModel(
                            symbol=symbol,
                            candidate_id="always_flat",
                            samples_by_decision_end={
                                sample.decision_end: sample
                                for sample in stream.split.validation_samples
                            },
                        ),
                    ),
                    (
                        "previous_bar_direction",
                        _DecisionModel(
                            symbol=symbol,
                            candidate_id="previous_bar_direction",
                            samples_by_decision_end={
                                sample.decision_end: sample
                                for sample in stream.split.validation_samples
                            },
                        ),
                    ),
                )
                for candidate_id, decision_model in model_specs:
                    cells.append(
                        _run_one_replay(
                            stream=stream,
                            campaign=campaign,
                            decision_model=decision_model,
                            candidate_id=candidate_id,
                            cost_bps=cost_bps,
                            work_root=temporary_root,
                        )
                    )
    return tuple(cells)


def _campaign_for(stream: FirstRateM5Stream, cost_bps: Decimal) -> CampaignContract:
    split = stream.split
    return CampaignContract(
        campaign_id=(
            f"{FIRSTRATE_M5_AFTER_COST_CONTROL_ID}-{stream.symbol.lower()}-"
            f"{cost_bps.normalize()}bps"
        ),
        catalog=CatalogDatasetRef(
            catalog_id="firstrate-free-intraday-source-local-v1",
            dataset_id=stream.catalog.dataset_id,
            dataset_hash=stream.catalog.dataset_hash,
            constructed_as_of_utc=stream.catalog.bars[-1].end_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.M5,
        folds=(
            CampaignFold(
                fold_id="chronological-validation",
                development=split.development_window,
                validation=split.validation_window,
            ),
        ),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("0"),
            slippage_bps=cost_bps,
            slippage_source_id="firstrate_m5_synthetic_per_side_cost_band",
        ),
        purge=timedelta(minutes=5 * FIRSTRATE_M5_EMBARGO_BARS),
        embargo=timedelta(minutes=5 * FIRSTRATE_M5_EMBARGO_BARS),
        evidence_use="development",
        naive_baselines=("flat", "previous_bar_direction"),
        deterministic_seed=20260820,
    )


def _run_one_replay(
    *,
    stream: FirstRateM5Stream,
    campaign: CampaignContract,
    decision_model: _DecisionModel,
    candidate_id: Literal["l2_logistic", "always_flat", "previous_bar_direction"],
    cost_bps: Decimal,
    work_root: Path,
) -> FirstRateM5ReplayCell:
    work_dir = work_root / f"{stream.symbol.lower()}-{candidate_id}-{cost_bps}bps"
    work_dir.mkdir(parents=True, exist_ok=False)
    try:
        aggregate = _ReplayAggregate()
        for chunk_index, (bars, eligible_samples) in enumerate(
            _contiguous_validation_chunks(stream, campaign),
            start=1,
        ):
            event_store = InMemoryCampaignEventStore()
            chunk_dir = work_dir / f"chunk-{chunk_index:04d}"
            chunk_dir.mkdir(parents=True, exist_ok=False)
            emergency_store = EmergencyStore(chunk_dir / "emergency.json")
            emergency_store.write(
                EmergencyState(
                    stop_new_orders=False,
                    cancel_open_orders_requested=False,
                    reason="firstrate_m5_after_cost_control_validation_only",
                    updated_at=bars[0].start_ts,
                )
            )
            try:
                catalog = _cataloged_bars_from_verified_loader(
                    dataset_id=stream.catalog.dataset_id,
                    dataset_hash=stream.catalog.dataset_hash,
                    source_path=stream.catalog.source_path,
                    bars=bars,
                )
                result = run_local_paper_validation(
                    catalog,
                    event_store=event_store,
                    emergency_store=emergency_store,
                    model=decision_model,
                    config=ValidationConfig(
                        run_id=(
                            f"{FIRSTRATE_M5_AFTER_COST_CONTROL_ID}-"
                            f"{stream.symbol.lower()}-{candidate_id}-{cost_bps}bps-"
                            f"chunk-{chunk_index:04d}"
                        ),
                        starting_cash=FIRSTRATE_M5_STARTING_CASH,
                        quantity=FIRSTRATE_M5_QUANTITY,
                        fee_bps=Decimal("0"),
                        slippage_bps=cost_bps,
                    ),
                    campaign=campaign,
                    phase="validation",
                    fold_id="chronological-validation",
                    eligible_signal_starts=frozenset(
                        sample.decision_start for sample in eligible_samples
                    ),
                )
                aggregate.add(result=result, event_store=event_store)
            finally:
                for path in chunk_dir.iterdir():
                    path.unlink()
                chunk_dir.rmdir()
        if not aggregate.replayable or not aggregate.terminal_flat:
            raise RuntimeError("FirstRate M5 local-paper replay invariants failed")
        return FirstRateM5ReplayCell(
            candidate_id=candidate_id,
            symbol=stream.symbol,
            cost_bps_per_side=cost_bps,
            decisions_seen=aggregate.decisions_seen,
            local_paper_fill_count=aggregate.local_paper_fill_count,
            all_fills_local_paper=aggregate.all_fills_local_paper,
            replayable=aggregate.replayable,
            terminal_flat=aggregate.terminal_flat,
            after_cost_pnl=aggregate.after_cost_pnl,
            gross_pnl=aggregate.gross_pnl,
            total_fees=aggregate.total_fees,
            total_slippage=aggregate.total_slippage,
        )
    finally:
        for path in work_dir.iterdir():
            path.unlink()
        work_dir.rmdir()


@dataclass
class _ReplayAggregate:
    decisions_seen: int = 0
    local_paper_fill_count: int = 0
    all_fills_local_paper: bool = True
    replayable: bool = True
    terminal_flat: bool = True
    after_cost_pnl: Decimal = Decimal("0")
    gross_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")

    def add(self, *, result: object, event_store: InMemoryCampaignEventStore) -> None:
        from thericher_v2.research.validation import ValidationResult

        if not isinstance(result, ValidationResult):
            raise ValueError("FirstRate M5 local-paper replay result is invalid")
        events = event_store.iter_events()
        fills = tuple(event for event in events if event.event_type == "fill")
        all_fills_local_paper = all(
            event.payload.get("source") == LOCAL_PAPER_SOURCE for event in fills
        )
        replayed_account = replay_local_paper_account(
            event_store,  # type: ignore[arg-type]
            starting_cash=FIRSTRATE_M5_STARTING_CASH,
        )
        replayed_position = replayed_account.quantity(market=result.market, symbol=result.symbol)
        replayable = (
            all_fills_local_paper
            and len(fills) == len(result.trades)
            and replayed_account.cash == result.ending_cash
            and replayed_position == result.final_position
        )
        terminal_flat = result.final_position == 0 and replayed_position == 0
        self.decisions_seen += result.decisions_seen
        self.local_paper_fill_count += len(fills)
        self.all_fills_local_paper = self.all_fills_local_paper and all_fills_local_paper
        self.replayable = self.replayable and replayable
        self.terminal_flat = self.terminal_flat and terminal_flat
        self.after_cost_pnl += result.after_cost_pnl
        self.gross_pnl += result.gross_pnl
        self.total_fees += result.total_fees
        self.total_slippage += result.total_slippage


def _contiguous_validation_chunks(
    stream: FirstRateM5Stream,
    campaign: CampaignContract,
) -> tuple[tuple[tuple[Bar, ...], tuple[FirstRateM5Sample, ...]], ...]:
    _, window = campaign.resolve_window("validation", fold_id="chronological-validation")
    validation_bars = tuple(
        bar
        for bar in stream.catalog.bars
        if bar.start_ts >= window.start_utc and bar.end_ts <= window.end_utc
    )
    chunks: list[tuple[tuple[Bar, ...], tuple[FirstRateM5Sample, ...]]] = []
    current: list[Bar] = []
    for bar in validation_bars:
        if current and bar.start_ts - current[-1].start_ts != Timeframe.M5.duration:
            _append_validation_chunk(chunks, stream=stream, bars=tuple(current))
            current = []
        current.append(bar)
    _append_validation_chunk(chunks, stream=stream, bars=tuple(current))
    if not chunks:
        raise FirstRateM5InputUnavailable("no_contiguous_validation_chunk")
    return tuple(chunks)


def _append_validation_chunk(
    chunks: list[tuple[tuple[Bar, ...], tuple[FirstRateM5Sample, ...]]],
    *,
    stream: FirstRateM5Stream,
    bars: tuple[Bar, ...],
) -> None:
    if len(bars) < FIRSTRATE_M5_OBSERVATION_BARS + 3:
        return
    eligible = tuple(
        sample
        for sample in stream.split.validation_samples
        if sample.history_start >= bars[0].start_ts and sample.exit_start <= bars[-1].start_ts
    )
    if eligible:
        chunks.append((bars, eligible))


def _precommit_payload(control_input: FirstRateM5ControlInput) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
        "status": "precommitted",
        "claim": (
            "one fixed CPU-only source-local descriptive control; not a winner, "
            "selection, ensemble, KIS input, Paper consumer, profitability claim, "
            "or GPU appointment"
        ),
        "input_attestation": control_input.source_attestation_payload(),
        "geometry": {
            "observation_bars": FIRSTRATE_M5_OBSERVATION_BARS,
            "target": "next_5m_bar_close_greater_than_its_open",
            "target_horizon_bars": FIRSTRATE_M5_FORWARD_BARS,
            "complete_contiguous_windows_only": True,
            "cross_symbol_features": False,
            "time_of_day_features": False,
            "session_reset_features": False,
            "cross_feed_features": False,
            "chronological_train_fraction": {
                "numerator": FIRSTRATE_M5_TRAIN_FRACTION_NUMERATOR,
                "denominator": FIRSTRATE_M5_TRAIN_FRACTION_DENOMINATOR,
            },
            "embargo_bars": FIRSTRATE_M5_EMBARGO_BARS,
            "embargo_covers_observation_plus_target": True,
        },
        "model": {
            "family": "l2_logistic",
            "feature_rule": "60_completed_bar_relative_close_trajectory",
            "l2_penalty": FIRSTRATE_M5_L2_PENALTY,
            "learning_rate": FIRSTRATE_M5_LEARNING_RATE,
            "training_steps": FIRSTRATE_M5_TRAINING_STEPS,
            "decision_threshold": FIRSTRATE_M5_DECISION_THRESHOLD,
            "gpu_used": False,
            "stop_rule": "fixed_steps_or_nonfinite_parameters_or_replay_invariant_failure",
        },
        "comparators": ["always_flat", "previous_bar_direction"],
        "execution": {
            "replay_fill_source": LOCAL_PAPER_SOURCE,
            "entry": "next_5m_bar_open",
            "exit": "following_5m_bar_open",
            "terminal_flat_required": True,
            "synthetic_cost_bps_per_side": [str(value) for value in FIRSTRATE_M5_COST_BPS_PER_SIDE],
            "zero_cost_evidence_accepted": False,
            "kis_execution_parity": False,
        },
        "selection": {
            "classification_rule": "all_six_l2_vs_flat_nonzero_cost_cells",
            "kill_test": "l2_logistic_fails_to_beat_always_flat_in_all_six_cells",
            "no_post_outcome_tuning": True,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "gpu_appointment_allowed": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "model_parameters_written": True,
            "raw_market_data_written": False,
            "raw_labels_written": False,
            "raw_predictions_written": False,
            "raw_local_paper_events_written": False,
        },
        "limitations": [
            "source_local_retrospective_control_only",
            "source_timestamp_semantics_unverified",
            "session_coverage_not_assessed",
            "synthetic_cost_band_is_not_kis_execution_parity",
            "decision_time_availability_not_observed",
            "provider_finality_not_observed",
        ],
    }


def _summary_payload(
    *,
    control_input: FirstRateM5ControlInput,
    precommit_hash: str,
    models: Mapping[str, FirstRateM5L2Model],
    model_sha256: str,
    replay_cells: tuple[FirstRateM5ReplayCell, ...],
    classification: Literal["rejected", "inconclusive", "eligible_to_propose_gpu"],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "claim": (
            "fixed source-local CPU control result only; no winner, architecture selection, "
            "ensemble, KIS input, Paper consumer, or profitability claim"
        ),
        "precommit_hash": precommit_hash,
        "input_attestation": control_input.source_attestation_payload(),
        "model_artifact_sha256": model_sha256,
        "models": [
            {
                "symbol": model.symbol,
                "parameter_hash": model.parameter_hash,
                "standardizer_hash": model.standardizer_hash,
                "development_input_sha256": model.development_input_hash,
            }
            for model in models.values()
        ],
        "replay_cells": [cell.to_payload() for cell in replay_cells],
        "classification": classification,
        "classification_interpretation": {
            "rejected": "L2 logistic did not beat always-flat in any SPY/QQQ nonzero-cost cell",
            "inconclusive": "mixed nonzero-cost result; no GPU or promotion consequence",
            "eligible_to_propose_gpu": (
                "L2 logistic beat always-flat in every SPY/QQQ nonzero-cost cell; "
                "a separate frozen GPU proposal is still required"
            ),
        },
        "gpu_used": False,
        "network_access": False,
        "credentials_read": False,
        "kis_or_broker_called": False,
        "raw_market_data_written": False,
        "raw_labels_written": False,
        "raw_predictions_written": False,
        "raw_local_paper_events_written": False,
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "paper_or_execution_consumer_created": False,
        "limitations": [
            "source_local_retrospective_control_only",
            "source_timestamp_semantics_unverified",
            "session_coverage_not_assessed",
            "synthetic_cost_band_is_not_kis_execution_parity",
            "no_kis_or_paper_consumer",
        ],
    }


def _classify_replay_cells(
    cells: Sequence[FirstRateM5ReplayCell],
) -> Literal["rejected", "inconclusive", "eligible_to_propose_gpu"]:
    by_key = {(cell.candidate_id, cell.symbol, cell.cost_bps_per_side): cell for cell in cells}
    expected = {
        (candidate, symbol, cost)
        for candidate in ("l2_logistic", "always_flat", "previous_bar_direction")
        for symbol in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
        for cost in FIRSTRATE_M5_COST_BPS_PER_SIDE
    }
    if set(by_key) != expected or len(by_key) != len(cells):
        raise ValueError("FirstRate M5 replay matrix is incomplete")
    comparisons: list[bool] = []
    for symbol in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS:
        for cost in FIRSTRATE_M5_COST_BPS_PER_SIDE:
            model = by_key[("l2_logistic", symbol, cost)]
            flat = by_key[("always_flat", symbol, cost)]
            if not (
                model.all_fills_local_paper
                and model.replayable
                and model.terminal_flat
                and flat.all_fills_local_paper
                and flat.replayable
                and flat.terminal_flat
            ):
                raise ValueError("FirstRate M5 replay invariants are incomplete")
            comparisons.append(model.after_cost_pnl > flat.after_cost_pnl)
    if not any(comparisons):
        return "rejected"
    if all(comparisons):
        return "eligible_to_propose_gpu"
    return "inconclusive"


def _parse_replay_cells(summary: Mapping[str, object]) -> tuple[FirstRateM5ReplayCell, ...]:
    payload_cells = summary.get("replay_cells")
    if not isinstance(payload_cells, list):
        raise ValueError("FirstRate M5 replay cells are invalid")
    cells: list[FirstRateM5ReplayCell] = []
    for payload in payload_cells:
        if not isinstance(payload, dict):
            raise ValueError("FirstRate M5 replay cell is invalid")
        candidate_id = payload.get("candidate_id")
        if candidate_id not in {"l2_logistic", "always_flat", "previous_bar_direction"}:
            raise ValueError("FirstRate M5 replay candidate is invalid")
        symbol = payload.get("symbol")
        if symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS:
            raise ValueError("FirstRate M5 replay symbol is invalid")
        if (
            payload.get("fill_source") != LOCAL_PAPER_SOURCE
            or not isinstance(payload.get("decisions_seen"), int)
            or not isinstance(payload.get("local_paper_fill_count"), int)
            or not isinstance(payload.get("all_fills_local_paper"), bool)
            or not isinstance(payload.get("replayable"), bool)
            or not isinstance(payload.get("terminal_flat"), bool)
        ):
            raise ValueError("FirstRate M5 replay evidence is invalid")
        try:
            cell = FirstRateM5ReplayCell(
                candidate_id=candidate_id,
                symbol=symbol,
                cost_bps_per_side=Decimal(str(payload.get("cost_bps_per_side"))),
                decisions_seen=int(payload["decisions_seen"]),
                local_paper_fill_count=int(payload["local_paper_fill_count"]),
                all_fills_local_paper=bool(payload["all_fills_local_paper"]),
                replayable=bool(payload["replayable"]),
                terminal_flat=bool(payload["terminal_flat"]),
                after_cost_pnl=Decimal(str(payload.get("after_cost_pnl"))),
                gross_pnl=Decimal(str(payload.get("gross_pnl"))),
                total_fees=Decimal(str(payload.get("total_fees"))),
                total_slippage=Decimal(str(payload.get("total_slippage"))),
            )
        except Exception as error:
            raise ValueError("FirstRate M5 replay numeric payload is invalid") from error
        cells.append(cell)
    return tuple(cells)


def _verify_precommit(precommit: Mapping[str, object]) -> str:
    recorded = precommit.get("precommit_hash")
    if not _is_sha256(recorded):
        raise ValueError("FirstRate M5 precommit hash is invalid")
    payload = dict(precommit)
    payload.pop("precommit_hash", None)
    expected = _sha256_payload(payload)
    if recorded != expected:
        raise ValueError("FirstRate M5 precommit hash does not match content")
    return expected


def _validate_frozen_payload(precommit: Mapping[str, object]) -> None:
    geometry = precommit.get("geometry")
    model = precommit.get("model")
    execution = precommit.get("execution")
    selection = precommit.get("selection")
    if not all(isinstance(value, dict) for value in (geometry, model, execution, selection)):
        raise ValueError("FirstRate M5 precommit sections are invalid")
    if (
        geometry.get("observation_bars") != FIRSTRATE_M5_OBSERVATION_BARS
        or geometry.get("target") != "next_5m_bar_close_greater_than_its_open"
        or geometry.get("target_horizon_bars") != FIRSTRATE_M5_FORWARD_BARS
        or geometry.get("complete_contiguous_windows_only") is not True
        or geometry.get("cross_symbol_features") is not False
        or geometry.get("time_of_day_features") is not False
        or geometry.get("session_reset_features") is not False
        or geometry.get("cross_feed_features") is not False
        or geometry.get("embargo_bars") != FIRSTRATE_M5_EMBARGO_BARS
        or geometry.get("embargo_covers_observation_plus_target") is not True
        or model.get("family") != "l2_logistic"
        or model.get("decision_threshold") != FIRSTRATE_M5_DECISION_THRESHOLD
        or model.get("gpu_used") is not False
        or execution.get("replay_fill_source") != LOCAL_PAPER_SOURCE
        or execution.get("synthetic_cost_bps_per_side")
        != [str(value) for value in FIRSTRATE_M5_COST_BPS_PER_SIDE]
        or execution.get("zero_cost_evidence_accepted") is not False
        or execution.get("kis_execution_parity") is not False
        or selection.get("no_post_outcome_tuning") is not True
        or selection.get("selection_allowed") is not False
        or selection.get("ensemble_allowed") is not False
        or selection.get("promotion_allowed") is not False
        or selection.get("gpu_appointment_allowed") is not False
    ):
        raise ValueError("FirstRate M5 precommit is not frozen")


def _validate_model_payload(model: Mapping[str, object], *, expected_precommit_hash: str) -> None:
    entries = model.get("models")
    if (
        model.get("control_id") != FIRSTRATE_M5_AFTER_COST_CONTROL_ID
        or model.get("precommit_hash") != expected_precommit_hash
        or model.get("gpu_used") is not False
        or model.get("raw_market_data_written") is not False
        or not isinstance(entries, list)
        or len(entries) != len(FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS)
    ):
        raise ValueError("FirstRate M5 model evidence is invalid")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("FirstRate M5 model entry is invalid")
        symbol = entry.get("symbol")
        weights = entry.get("weights")
        means = entry.get("means")
        scales = entry.get("scales")
        if (
            symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or symbol in seen
            or entry.get("model_family") != "l2_logistic"
            or not _is_sha256(entry.get("parameter_hash"))
            or not _is_sha256(entry.get("standardizer_hash"))
            or not _is_sha256(entry.get("development_input_sha256"))
            or not all(
                isinstance(values, list)
                and len(values) == FIRSTRATE_M5_OBSERVATION_BARS
                for values in (weights, means, scales)
            )
            or not isinstance(entry.get("intercept"), str)
        ):
            raise ValueError("FirstRate M5 model geometry is invalid")
        seen.add(symbol)
    if seen != set(FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS):
        raise ValueError("FirstRate M5 model symbols are incomplete")


def _samples_hash(samples: Sequence[FirstRateM5Sample]) -> str:
    return _sha256_payload(
        [
            {
                "symbol": sample.symbol,
                "history_start": sample.history_start.isoformat(),
                "decision_start": sample.decision_start.isoformat(),
                "target_start": sample.target_start.isoformat(),
                "exit_start": sample.exit_start.isoformat(),
                "features": [format(value, ".17g") for value in sample.features],
                "label": sample.label,
            }
            for sample in samples
        ]
    )


def _bars_hash(bars: Sequence[Bar]) -> str:
    return _sha256_payload([bar_to_record(bar) for bar in bars])


def _timestamps_hash(timestamps: Sequence[datetime]) -> str:
    if tuple(timestamps) != tuple(sorted(set(timestamps))):
        raise ValueError("FirstRate M5 timestamps must be strictly ordered and unique")
    return _sha256("".join(f"{value.isoformat()}\n" for value in timestamps).encode("utf-8"))


def _output_dir(artifact_root: Path, run_label: str) -> Path:
    root = (artifact_root / FIRSTRATE_M5_AFTER_COST_CONTROL_ID).resolve(strict=False)
    output_dir = (root / run_label).resolve(strict=False)
    if not output_dir.is_relative_to(root):
        raise ValueError("FirstRate M5 control artifact path escapes its root")
    return output_dir


def _require_external_root(value: Path | str, *, repo_root: Path, field_name: str) -> Path:
    root = Path(value).resolve(strict=False)
    if root.is_relative_to(repo_root):
        raise ValueError(f"{field_name} must stay outside Git")
    return root


def _path_within_root(root: Path, value: Path | str, *, field_name: str) -> Path:
    candidate = Path(value)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field_name} must stay under its external root")
    return resolved


def _read_json(path: Path, *, field_name: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"FirstRate M5 {field_name} is unreadable") from error
    if not isinstance(payload, dict):
        raise ValueError(f"FirstRate M5 {field_name} must be an object")
    return payload


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")


def _write_or_verify(path: Path, payload: Mapping[str, object]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("FirstRate M5 validation receipt conflicts with existing evidence")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


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
        raise ValueError("FirstRate M5 control run_label is invalid")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(_SHA256_PREFIX)
        and len(value) == len(_SHA256_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )


def _sha256(payload: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


def _sha256_payload(payload: object) -> str:
    return _sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _numpy():
    import numpy

    return numpy

"""CPU-only signal/noise-floor check for adjustment-robust KIS D1 candles.

This leaf keeps all OHLCV-derived values, labels, probabilities, coefficients,
and numeric metrics in process. Its external evidence contains only frozen
contract identity, structural counts, categorical metric buckets, and hashes.
It has no provider, credential, execution, Paper, or GPU surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)
from .validation import _reject_repo_artifact_path

KIS_D1_CANDLE_NOISE_FLOOR_ID = "kis-d1-candle-noise-floor-v1"
KIS_D1_CANDLE_NOISE_FLOOR_DATASET_ID = "kis.paper.private.daily.nas.history.panel-v1"
KIS_D1_CANDLE_NOISE_FLOOR_DATASET_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS = (
    "AAPL",
    "AMZN",
    "GOOGL",
    "META",
    "MSFT",
    "NVDA",
)
KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS = 1510
KIS_D1_CANDLE_NOISE_FLOOR_TRAINING_SESSIONS = 1000
KIS_D1_CANDLE_NOISE_FLOOR_PURGE_SESSIONS = 33
KIS_D1_CANDLE_NOISE_FLOOR_VALIDATION_START = (
    KIS_D1_CANDLE_NOISE_FLOOR_TRAINING_SESSIONS
    + KIS_D1_CANDLE_NOISE_FLOOR_PURGE_SESSIONS
)
KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH = 32
KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES = (
    "log_high_to_open",
    "log_low_to_open",
    "log_close_to_open",
)
KIS_D1_CANDLE_NOISE_FLOOR_C = 0.1
KIS_D1_CANDLE_NOISE_FLOOR_THRESHOLD = 0.50
KIS_D1_CANDLE_NOISE_FLOOR_SEEDS = (
    20_260_802,
    20_260_803,
    20_260_804,
    20_260_805,
    20_260_806,
)
KIS_D1_CANDLE_NOISE_FLOOR_NULL_COUNT = 64
KIS_D1_CANDLE_NOISE_FLOOR_NULL_BLOCK_SIZE = 10
KIS_D1_CANDLE_NOISE_FLOOR_NULL_SEED_BASE = 60_260_802
KIS_D1_CANDLE_NOISE_FLOOR_MARGIN = 0.015
KIS_D1_CANDLE_NOISE_FLOOR_DEFAULT_ATTEMPT_ID = "cpu-noise-floor-r1"

NoiseFloorInputStatus = Literal["ready", "input_unavailable"]
NoiseFloorResultStatus = Literal[
    "noise_not_separable",
    "noise_floor_passed",
    "input_unavailable",
]

_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


@dataclass(frozen=True, slots=True)
class KisD1CandleNoiseFloorInput:
    """A source-attested, in-memory-only chronological classification dataset."""

    input_id: str
    dataset_id: str
    dataset_hash: str
    index_hash: str
    status: NoiseFloorInputStatus
    reason: str | None
    training_row_count: int
    validation_row_count: int
    validation_symbol_row_counts: tuple[int, ...]
    input_hash: str
    _training_features: Any
    _training_labels: Any
    _validation_features: Any
    _validation_labels: Any
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        numpy = _numpy()
        training_features = numpy.asarray(self._training_features, dtype=numpy.float64)
        training_labels = numpy.asarray(self._training_labels, dtype=numpy.int8)
        validation_features = numpy.asarray(self._validation_features, dtype=numpy.float64)
        validation_labels = numpy.asarray(self._validation_labels, dtype=numpy.int8)
        feature_width = (
            KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH
            * len(KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES)
        )
        if (
            self.input_id != "kis.paper.private.daily.nas.sequence.input-v1"
            or self.dataset_id != KIS_D1_CANDLE_NOISE_FLOOR_DATASET_ID
            or self.dataset_hash != KIS_D1_CANDLE_NOISE_FLOOR_DATASET_HASH
            or not _is_sha256(self.index_hash)
            or self.status not in {"ready", "input_unavailable"}
            or self.training_row_count < 0
            or self.validation_row_count < 0
            or len(self.validation_symbol_row_counts)
            != len(KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS)
            or any(count < 0 for count in self.validation_symbol_row_counts)
            or not _is_sha256(self.input_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS D1 candle noise-floor input identity is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or training_features.shape != (self.training_row_count, feature_width)
                or validation_features.shape != (self.validation_row_count, feature_width)
                or training_labels.shape != (self.training_row_count,)
                or validation_labels.shape != (self.validation_row_count,)
                or sum(self.validation_symbol_row_counts) != self.validation_row_count
                or self.training_row_count <= 0
                or self.validation_row_count <= 0
                or not numpy.isfinite(training_features).all()
                or not numpy.isfinite(validation_features).all()
                or not _are_binary_labels(training_labels, numpy=numpy)
                or not _are_binary_labels(validation_labels, numpy=numpy)
            ):
                raise ValueError("ready KIS D1 candle noise-floor input is invalid")
        elif (
            self.reason
            not in {
                "invalid_candle_ratio",
                "insufficient_development_rows",
                "source_stream_mismatch",
            }
            or training_features.shape != (0, feature_width)
            or training_labels.shape != (0,)
            or validation_features.shape != (0, feature_width)
            or validation_labels.shape != (0,)
            or self.training_row_count != 0
            or self.validation_row_count != 0
            or any(self.validation_symbol_row_counts)
        ):
            raise ValueError("unavailable KIS D1 candle noise-floor input is invalid")
        expected_input_hash = _input_hash(
            input_id=self.input_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            index_hash=self.index_hash,
            status=self.status,
            reason=self.reason,
            training_row_count=self.training_row_count,
            validation_row_count=self.validation_row_count,
            validation_symbol_row_counts=self.validation_symbol_row_counts,
        )
        if self.input_hash != expected_input_hash:
            raise ValueError("KIS D1 candle noise-floor input hash is invalid")
        for value in (
            training_features,
            training_labels,
            validation_features,
            validation_labels,
        ):
            value.setflags(write=False)
        object.__setattr__(
            self,
            "validation_symbol_row_counts",
            tuple(self.validation_symbol_row_counts),
        )
        object.__setattr__(self, "_training_features", training_features)
        object.__setattr__(self, "_training_labels", training_labels)
        object.__setattr__(self, "_validation_features", validation_features)
        object.__setattr__(self, "_validation_labels", validation_labels)

    def safe_payload(self) -> dict[str, object]:
        """Expose source identity and structure without market or label values."""

        return {
            "schema_version": self.schema_version,
            "campaign_id": KIS_D1_CANDLE_NOISE_FLOOR_ID,
            "source": {
                "input_id": self.input_id,
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "index_hash": self.index_hash,
                "phase": "development_only",
                "symbol_count": len(KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS),
            },
            "status": self.status,
            "reason": self.reason,
            "training_row_count": self.training_row_count,
            "validation_row_count": self.validation_row_count,
            "validation_symbol_row_counts": list(self.validation_symbol_row_counts),
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "predictions_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class KisD1CandleNoiseFloorMetrics:
    """Private numeric checks with a categorical external projection only."""

    actual_median_balanced_accuracy: float
    null_p95_balanced_accuracy: float
    actual_minus_null_p95: float
    seed_spread: float
    always_long_balanced_accuracy: float
    seed_count: int
    null_count: int

    def __post_init__(self) -> None:
        values = (
            self.actual_median_balanced_accuracy,
            self.null_p95_balanced_accuracy,
            self.actual_minus_null_p95,
            self.seed_spread,
            self.always_long_balanced_accuracy,
        )
        if (
            self.seed_count != len(KIS_D1_CANDLE_NOISE_FLOOR_SEEDS)
            or self.null_count != KIS_D1_CANDLE_NOISE_FLOOR_NULL_COUNT
            or any(not math.isfinite(value) for value in values)
            or self.seed_spread < 0.0
        ):
            raise ValueError("KIS D1 candle noise-floor metrics are invalid")

    @property
    def passes_noise_floor(self) -> bool:
        return (
            self.actual_minus_null_p95 >= KIS_D1_CANDLE_NOISE_FLOOR_MARGIN
            and self.seed_spread < self.actual_minus_null_p95
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "actual_median_balanced_accuracy_bucket": _accuracy_bucket(
                self.actual_median_balanced_accuracy
            ),
            "null_p95_balanced_accuracy_bucket": _accuracy_bucket(
                self.null_p95_balanced_accuracy
            ),
            "always_long_balanced_accuracy_bucket": _accuracy_bucket(
                self.always_long_balanced_accuracy
            ),
            "actual_minus_null_p95_relation": _margin_relation(
                self.actual_minus_null_p95
            ),
            "seed_spread_relation_to_excess": (
                "less_than_excess"
                if self.seed_spread < self.actual_minus_null_p95
                else "at_least_excess"
            ),
            "seed_count": self.seed_count,
            "null_count": self.null_count,
            "null_geometry": {
                "permutation": "within_symbol_contiguous_blocks",
                "block_size": KIS_D1_CANDLE_NOISE_FLOOR_NULL_BLOCK_SIZE,
            },
            "numeric_metrics_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class KisD1CandleNoiseFloorContract:
    """One immutable CPU-only campaign contract and custody record."""

    input: KisD1CandleNoiseFloorInput
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    registry_entry: FrozenCampaignRegistryEntry


@dataclass(frozen=True, slots=True)
class KisD1CandleNoiseFloorRun:
    """Source-safe terminal result for the single CPU campaign."""

    status: NoiseFloorResultStatus
    reason: str | None
    summary_path: Path
    summary_sha256: str
    registry_outcome: CampaignOutcomeRegistryEntry


def load_kis_d1_candle_noise_floor_input(
    *,
    manifest_path: Path,
    cache_root: Path,
    panel_root: Path,
    repo_root: Path | None = None,
) -> KisD1CandleNoiseFloorInput:
    """Load only through the existing attested KIS D1 sequence adapter."""

    from thericher_v2.data.kis_paper_daily_history_sequence_input import (
        load_kis_paper_daily_history_sequence_input,
    )

    source = load_kis_paper_daily_history_sequence_input(
        manifest_path=manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return build_kis_d1_candle_noise_floor_input(
        source.development,
        input_id=source.input_id,
    )


def build_kis_d1_candle_noise_floor_input(
    development_phase: object,
    *,
    input_id: str,
) -> KisD1CandleNoiseFloorInput:
    """Create fixed causal train/validation examples without later source phases."""

    numpy = _numpy()
    _require_development_phase(development_phase, input_id=input_id)
    phase = cast(Any, development_phase)
    try:
        training_features: list[Any] = []
        training_labels: list[Any] = []
        validation_features: list[Any] = []
        validation_labels: list[Any] = []
        validation_symbol_row_counts: list[int] = []
        for symbol in KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS:
            bars = _verified_symbol_bars(phase, symbol=symbol)
            feature_rows = numpy.asarray(
                [_candle_feature_row(bar) for bar in bars],
                dtype=numpy.float64,
            )
            labels = numpy.asarray(
                [1 if bar.close > bar.open else 0 for bar in bars],
                dtype=numpy.int8,
            )
            train_features, train_labels = _examples_for_anchor_range(
                feature_rows,
                labels,
                start_anchor=KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH - 1,
                stop_anchor=KIS_D1_CANDLE_NOISE_FLOOR_TRAINING_SESSIONS - 1,
            )
            validation_features_for_symbol, validation_labels_for_symbol = (
                _examples_for_anchor_range(
                    feature_rows,
                    labels,
                    start_anchor=(
                        KIS_D1_CANDLE_NOISE_FLOOR_VALIDATION_START
                        + KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH
                        - 1
                    ),
                    stop_anchor=KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS - 1,
                )
            )
            training_features.append(train_features)
            training_labels.append(train_labels)
            validation_features.append(validation_features_for_symbol)
            validation_labels.append(validation_labels_for_symbol)
            validation_symbol_row_counts.append(len(validation_labels_for_symbol))
        combined_training_features = numpy.concatenate(training_features, axis=0)
        combined_training_labels = numpy.concatenate(training_labels, axis=0)
        combined_validation_features = numpy.concatenate(validation_features, axis=0)
        combined_validation_labels = numpy.concatenate(validation_labels, axis=0)
    except ValueError as error:
        return _unavailable_input(phase, input_id=input_id, reason=str(error))
    return _ready_input(
        phase,
        input_id=input_id,
        training_features=combined_training_features,
        training_labels=combined_training_labels,
        validation_features=combined_validation_features,
        validation_labels=combined_validation_labels,
        validation_symbol_row_counts=tuple(validation_symbol_row_counts),
    )


def freeze_kis_d1_candle_noise_floor_campaign(
    input: KisD1CandleNoiseFloorInput,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision: str,
    attempt_id: str = KIS_D1_CANDLE_NOISE_FLOOR_DEFAULT_ATTEMPT_ID,
) -> KisD1CandleNoiseFloorContract:
    """Freeze the CPU-only model/null contract before target evaluation."""

    if not code_revision.strip():
        raise ValueError("code revision is required")
    _require_attempt_id(attempt_id)
    run_directory = _external_run_directory(artifact_root, repo_root, attempt_id=attempt_id)
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_D1_CANDLE_NOISE_FLOOR_ID,
            "attempt_id": attempt_id,
            "code_revision": code_revision,
            "source": input.safe_payload()["source"],
            "source_limitations": [
                "MODP=0_unadjusted",
                "corporate_action_semantics_not_qualified",
                "current_listing_registry_not_point_in_time_universe",
                "source_local_only_no_cross_source_blend",
            ],
            "input": {
                "status": input.status,
                "reason": input.reason,
                "input_hash": input.input_hash,
                "training_row_count": input.training_row_count,
                "validation_row_count": input.validation_row_count,
                "validation_symbol_row_counts": list(input.validation_symbol_row_counts),
            },
            "geometry": {
                "development_session_count": KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS,
                "training_source_sessions": [0, 999],
                "training_anchor_sessions": [31, 998],
                "purge_source_sessions": [1000, 1032],
                "validation_source_sessions": [1033, 1509],
                "validation_anchor_sessions": [1064, 1508],
                "window_length": KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH,
                "target_horizon_sessions": 1,
                "target": "next_d1_open_to_close_direction",
                "feature_names": list(KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES),
                "features_use_same_candle_ratios_only": True,
            },
            "model": {
                "family": "standardized_l2_logistic_regression",
                "c": KIS_D1_CANDLE_NOISE_FLOOR_C,
                "class_weight": None,
                "threshold": KIS_D1_CANDLE_NOISE_FLOOR_THRESHOLD,
                "seeds": list(KIS_D1_CANDLE_NOISE_FLOOR_SEEDS),
                "fit_scope": "training_only",
            },
            "null": {
                "count": KIS_D1_CANDLE_NOISE_FLOOR_NULL_COUNT,
                "permutation": "within_symbol_contiguous_blocks",
                "block_size": KIS_D1_CANDLE_NOISE_FLOOR_NULL_BLOCK_SIZE,
                "percentile": "p95_higher",
            },
            "kill_test": {
                "minimum_actual_minus_null_p95": KIS_D1_CANDLE_NOISE_FLOOR_MARGIN,
                "seed_spread_must_be_less_than_actual_minus_null_p95": True,
            },
            "scope": _non_promoting_scope(),
            "artifact_policy": {
                "repository_storage_allowed": False,
                "raw_rows_persisted": False,
                "dates_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "predictions_persisted": False,
                "numeric_metrics_persisted": False,
                "checkpoint_written": False,
            },
        },
        field_name="campaign_contract_sha256",
    )
    contract_path = run_directory / "campaign-contract.json"
    recorded = _write_or_reattach_contract(contract_path, payload)
    contract_sha256 = str(recorded["campaign_contract_sha256"])
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=input.dataset_hash,
        split_hash=_sha256_json(cast(dict[str, object], payload["geometry"])),
        cost_model_hash=_sha256_json({"cost_model": "not_applicable_noise_floor"}),
        trial_family=KIS_D1_CANDLE_NOISE_FLOOR_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return KisD1CandleNoiseFloorContract(
        input=input,
        artifact_root=Path(artifact_root).resolve(),
        repo_root=Path(repo_root).resolve(),
        attempt_id=attempt_id,
        run_directory=run_directory,
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        registry_entry=registry_entry,
    )


def run_kis_d1_candle_noise_floor(
    contract: KisD1CandleNoiseFloorContract,
) -> KisD1CandleNoiseFloorRun:
    """Run or reattach the one fixed CPU-only logistic/null evaluation."""

    existing = _load_existing_run(contract)
    if existing is not None:
        return _with_outcome(contract, existing)
    if contract.input.status != "ready":
        status: NoiseFloorResultStatus = "input_unavailable"
        reason = contract.input.reason
        metrics = None
    else:
        try:
            metrics = _evaluate_noise_floor(contract.input)
        except ValueError as error:
            status = "input_unavailable"
            reason = _safe_input_reason(error)
            metrics = None
        else:
            status = "noise_floor_passed" if metrics.passes_noise_floor else "noise_not_separable"
            reason = None if status == "noise_floor_passed" else "actual_label_signal_not_separable"
    summary = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_D1_CANDLE_NOISE_FLOOR_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "phase": "cpu_only",
            "status": status,
            "reason": reason,
            "input": {
                "input_hash": contract.input.input_hash,
                "status": contract.input.status,
                "training_row_count": contract.input.training_row_count,
                "validation_row_count": contract.input.validation_row_count,
            },
            "metrics": None if metrics is None else metrics.safe_payload(),
            "scope": _non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    summary_path = contract.run_directory / "cpu-summary.json"
    _write_or_verify_json(summary_path, summary)
    return _with_outcome(contract, _run_from_summary(contract, summary_path))


def _ready_input(
    phase: Any,
    *,
    input_id: str,
    training_features: Any,
    training_labels: Any,
    validation_features: Any,
    validation_labels: Any,
    validation_symbol_row_counts: tuple[int, ...],
) -> KisD1CandleNoiseFloorInput:
    return KisD1CandleNoiseFloorInput(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        status="ready",
        reason=None,
        training_row_count=len(training_labels),
        validation_row_count=len(validation_labels),
        validation_symbol_row_counts=validation_symbol_row_counts,
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=str(phase.parent_dataset_id),
            dataset_hash=str(phase.parent_dataset_hash),
            index_hash=str(phase.index_hash),
            status="ready",
            reason=None,
            training_row_count=len(training_labels),
            validation_row_count=len(validation_labels),
            validation_symbol_row_counts=validation_symbol_row_counts,
        ),
        _training_features=training_features,
        _training_labels=training_labels,
        _validation_features=validation_features,
        _validation_labels=validation_labels,
    )


def _unavailable_input(
    phase: Any,
    *,
    input_id: str,
    reason: str,
) -> KisD1CandleNoiseFloorInput:
    numpy = _numpy()
    safe_reason = (
        reason
        if reason in {"invalid_candle_ratio", "source_stream_mismatch"}
        else "insufficient_development_rows"
    )
    feature_width = (
        KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH
        * len(KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES)
    )
    counts = (0,) * len(KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS)
    return KisD1CandleNoiseFloorInput(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        status="input_unavailable",
        reason=safe_reason,
        training_row_count=0,
        validation_row_count=0,
        validation_symbol_row_counts=counts,
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=str(phase.parent_dataset_id),
            dataset_hash=str(phase.parent_dataset_hash),
            index_hash=str(phase.index_hash),
            status="input_unavailable",
            reason=safe_reason,
            training_row_count=0,
            validation_row_count=0,
            validation_symbol_row_counts=counts,
        ),
        _training_features=numpy.empty((0, feature_width), dtype=numpy.float64),
        _training_labels=numpy.empty((0,), dtype=numpy.int8),
        _validation_features=numpy.empty((0, feature_width), dtype=numpy.float64),
        _validation_labels=numpy.empty((0,), dtype=numpy.int8),
    )


def _verified_symbol_bars(phase: Any, *, symbol: str) -> tuple[Bar, ...]:
    stream = phase.bars_by_symbol[symbol]
    bars = tuple(stream.bars)
    sessions = tuple(phase.common_sessions)
    if (
        len(bars) != KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS
        or len(sessions) != KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS
        or tuple(sorted(sessions)) != sessions
        or len(set(sessions)) != len(sessions)
        or tuple(bar.start_ts.date() for bar in bars) != sessions
        or any(
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            for bar in bars
        )
    ):
        raise ValueError("source_stream_mismatch")
    return bars


def _candle_feature_row(bar: Bar) -> tuple[float, float, float]:
    values = (bar.open, bar.high, bar.low, bar.close)
    if any(value <= 0 for value in values):
        raise ValueError("invalid_candle_ratio")
    ratios = (
        float(bar.high / bar.open),
        float(bar.low / bar.open),
        float(bar.close / bar.open),
    )
    if any(value <= 0.0 or not math.isfinite(value) for value in ratios):
        raise ValueError("invalid_candle_ratio")
    features = tuple(math.log(value) for value in ratios)
    if any(not math.isfinite(value) for value in features):
        raise ValueError("invalid_candle_ratio")
    return cast(tuple[float, float, float], features)


def _examples_for_anchor_range(
    feature_rows: Any,
    labels: Any,
    *,
    start_anchor: int,
    stop_anchor: int,
) -> tuple[Any, Any]:
    numpy = _numpy()
    if (
        feature_rows.shape
        != (
            KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS,
            len(KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES),
        )
        or labels.shape != (KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS,)
        or start_anchor < KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH - 1
        or stop_anchor <= start_anchor
        or stop_anchor >= KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS
    ):
        raise ValueError("insufficient_development_rows")
    anchors = range(start_anchor, stop_anchor)
    rows = numpy.asarray(
        [
            feature_rows[
                anchor - KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH + 1 : anchor + 1
            ].reshape(-1)
            for anchor in anchors
        ],
        dtype=numpy.float64,
    )
    target_values = numpy.asarray(
        [labels[anchor + 1] for anchor in anchors],
        dtype=numpy.int8,
    )
    if (
        rows.shape[0] != len(target_values)
        or rows.shape[1]
        != KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH
        * len(KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES)
        or not numpy.isfinite(rows).all()
        or not _are_binary_labels(target_values, numpy=numpy)
    ):
        raise ValueError("insufficient_development_rows")
    return rows, target_values


def _evaluate_noise_floor(input: KisD1CandleNoiseFloorInput) -> KisD1CandleNoiseFloorMetrics:
    numpy = _numpy()
    training_labels = input._training_labels
    validation_labels = input._validation_labels
    if not _has_both_classes(training_labels, numpy=numpy) or not _has_both_classes(
        validation_labels,
        numpy=numpy,
    ):
        raise ValueError("single_target_class")
    mean = input._training_features.mean(axis=0)
    scale = input._training_features.std(axis=0)
    if (
        not numpy.isfinite(mean).all()
        or not numpy.isfinite(scale).all()
        or numpy.any(scale <= 0.0)
    ):
        raise ValueError("invalid_training_normalization")
    training_features = (input._training_features - mean) / scale
    validation_features = (input._validation_features - mean) / scale
    if not numpy.isfinite(training_features).all() or not numpy.isfinite(validation_features).all():
        raise ValueError("invalid_training_normalization")
    prediction_rows: list[Any] = []
    for seed in KIS_D1_CANDLE_NOISE_FLOOR_SEEDS:
        model = _fit_logistic(
            training_features,
            training_labels,
            seed=seed,
        )
        probabilities = model.predict_proba(validation_features)[:, 1]
        prediction_rows.append(
            numpy.asarray(
                probabilities >= KIS_D1_CANDLE_NOISE_FLOOR_THRESHOLD,
                dtype=numpy.int8,
            )
        )
    predictions = numpy.asarray(prediction_rows, dtype=numpy.int8)
    actual_scores = numpy.asarray(
        [_balanced_accuracy(validation_labels, row, numpy=numpy) for row in predictions],
        dtype=numpy.float64,
    )
    null_scores: list[float] = []
    for offset in range(KIS_D1_CANDLE_NOISE_FLOOR_NULL_COUNT):
        null_labels = _block_permute_validation_labels(
            validation_labels,
            symbol_row_counts=input.validation_symbol_row_counts,
            seed=KIS_D1_CANDLE_NOISE_FLOOR_NULL_SEED_BASE + offset,
        )
        null_scores.append(
            float(
                numpy.median(
                    [
                        _balanced_accuracy(null_labels, row, numpy=numpy)
                        for row in predictions
                    ]
                )
            )
        )
    actual_median = float(numpy.median(actual_scores))
    null_p95 = _percentile_higher(null_scores, percentile=0.95, numpy=numpy)
    return KisD1CandleNoiseFloorMetrics(
        actual_median_balanced_accuracy=actual_median,
        null_p95_balanced_accuracy=null_p95,
        actual_minus_null_p95=actual_median - null_p95,
        seed_spread=float(actual_scores.max() - actual_scores.min()),
        always_long_balanced_accuracy=_balanced_accuracy(
            validation_labels,
            numpy.ones_like(validation_labels, dtype=numpy.int8),
            numpy=numpy,
        ),
        seed_count=len(KIS_D1_CANDLE_NOISE_FLOOR_SEEDS),
        null_count=KIS_D1_CANDLE_NOISE_FLOOR_NULL_COUNT,
    )


def _fit_logistic(training_features: Any, training_labels: Any, *, seed: int) -> Any:
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        try:
            model = LogisticRegression(
                C=KIS_D1_CANDLE_NOISE_FLOOR_C,
                class_weight=None,
                max_iter=5000,
                random_state=seed,
                solver="saga",
                tol=1e-6,
            )
            model.fit(training_features, training_labels)
        except ConvergenceWarning as error:
            raise ValueError("logistic_nonconvergent") from error
    return model


def _block_permute_validation_labels(
    labels: Any,
    *,
    symbol_row_counts: tuple[int, ...],
    seed: int,
) -> Any:
    """Permute whole label blocks independently inside each symbol's timeline."""

    numpy = _numpy()
    values = numpy.asarray(labels, dtype=numpy.int8)
    if (
        values.ndim != 1
        or sum(symbol_row_counts) != len(values)
        or len(symbol_row_counts) != len(KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS)
        or not _are_binary_labels(values, numpy=numpy)
    ):
        raise ValueError("validation label blocks are invalid")
    generator = numpy.random.default_rng(seed)
    result = numpy.empty_like(values)
    cursor = 0
    for count in symbol_row_counts:
        segment = values[cursor : cursor + count]
        blocks = [
            segment[index : index + KIS_D1_CANDLE_NOISE_FLOOR_NULL_BLOCK_SIZE]
            for index in range(0, count, KIS_D1_CANDLE_NOISE_FLOOR_NULL_BLOCK_SIZE)
        ]
        order = generator.permutation(len(blocks))
        result[cursor : cursor + count] = numpy.concatenate([blocks[index] for index in order])
        cursor += count
    return result


def _balanced_accuracy(labels: Any, predictions: Any, *, numpy: Any) -> float:
    labels_array = numpy.asarray(labels, dtype=numpy.int8)
    prediction_array = numpy.asarray(predictions, dtype=numpy.int8)
    if (
        labels_array.shape != prediction_array.shape
        or not _has_both_classes(labels_array, numpy=numpy)
        or not _are_binary_labels(prediction_array, numpy=numpy)
    ):
        raise ValueError("balanced accuracy inputs are invalid")
    positive_recall = float((prediction_array[labels_array == 1] == 1).mean())
    negative_recall = float((prediction_array[labels_array == 0] == 0).mean())
    value = (positive_recall + negative_recall) / 2.0
    if not math.isfinite(value):
        raise ValueError("balanced accuracy is invalid")
    return value


def _percentile_higher(values: list[float], *, percentile: float, numpy: Any) -> float:
    array = numpy.asarray(values, dtype=numpy.float64)
    if array.shape != (KIS_D1_CANDLE_NOISE_FLOOR_NULL_COUNT,) or not numpy.isfinite(array).all():
        raise ValueError("null metric distribution is invalid")
    return float(numpy.quantile(array, percentile, method="higher"))


def _with_outcome(
    contract: KisD1CandleNoiseFloorContract,
    run: KisD1CandleNoiseFloorRun,
) -> KisD1CandleNoiseFloorRun:
    outcome = register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class=(
            "non_promoting_completed"
            if run.status in {"noise_not_separable", "noise_floor_passed"}
            else "non_promoting_failed"
        ),
        outcome_reference_sha256=run.summary_sha256,
        artifact_root=contract.artifact_root,
        repo_root=contract.repo_root,
    )
    return KisD1CandleNoiseFloorRun(
        status=run.status,
        reason=run.reason,
        summary_path=run.summary_path,
        summary_sha256=run.summary_sha256,
        registry_outcome=outcome,
    )


def _run_from_summary(
    contract: KisD1CandleNoiseFloorContract,
    summary_path: Path,
) -> KisD1CandleNoiseFloorRun:
    payload = _read_json_object(summary_path)
    summary_sha256 = _verify_signed_payload(payload, field_name="summary_sha256")
    status = payload.get("status")
    reason = payload.get("reason")
    if (
        payload.get("campaign_id") != KIS_D1_CANDLE_NOISE_FLOOR_ID
        or payload.get("campaign_contract_sha256") != contract.contract_sha256
        or payload.get("phase") != "cpu_only"
        or status
        not in {"noise_not_separable", "noise_floor_passed", "input_unavailable"}
        or (reason is not None and not isinstance(reason, str))
        or not isinstance(payload.get("input"), dict)
        or payload["input"].get("input_hash") != contract.input.input_hash
        or payload.get("scope") != _non_promoting_scope()
    ):
        raise ValueError("candle noise-floor summary is malformed")
    return KisD1CandleNoiseFloorRun(
        status=cast(NoiseFloorResultStatus, status),
        reason=cast(str | None, reason),
        summary_path=summary_path,
        summary_sha256=summary_sha256,
        registry_outcome=CampaignOutcomeRegistryEntry(
            contract_hash=contract.contract_sha256,
            outcome_class="non_promoting_completed",
            outcome_reference_sha256=summary_sha256,
            recorded_at=contract.registry_entry.recorded_at,
            record_path=contract.registry_entry.record_path,
            record_sha256=contract.registry_entry.record_sha256,
        ),
    )


def _load_existing_run(
    contract: KisD1CandleNoiseFloorContract,
) -> KisD1CandleNoiseFloorRun | None:
    summary_path = contract.run_directory / "cpu-summary.json"
    if not summary_path.exists():
        return None
    if not summary_path.is_file() or summary_path.is_symlink():
        raise ValueError("candle noise-floor summary path is invalid")
    return _run_from_summary(contract, summary_path)


def _require_development_phase(development_phase: object, *, input_id: str) -> None:
    phase = cast(Any, development_phase)
    if (
        input_id != "kis.paper.private.daily.nas.sequence.input-v1"
        or getattr(phase, "phase", None) != "development"
        or getattr(phase, "parent_dataset_id", None) != KIS_D1_CANDLE_NOISE_FLOOR_DATASET_ID
        or getattr(phase, "parent_dataset_hash", None)
        != KIS_D1_CANDLE_NOISE_FLOOR_DATASET_HASH
        or not _is_sha256(getattr(phase, "index_hash", None))
        or tuple(getattr(phase, "bars_by_symbol", ())) != KIS_D1_CANDLE_NOISE_FLOOR_SYMBOLS
        or len(getattr(phase, "common_sessions", ()))
        != KIS_D1_CANDLE_NOISE_FLOOR_DEVELOPMENT_SESSIONS
    ):
        raise ValueError("KIS D1 candle noise-floor requires the attested development phase")


def _external_run_directory(artifact_root: Path, repo_root: Path, *, attempt_id: str) -> Path:
    requested_root = Path(artifact_root)
    repository = Path(repo_root).resolve()
    _reject_repo_artifact_path(requested_root, repository)
    if requested_root.exists() and requested_root.is_symlink():
        raise ValueError("model artifact root must not be a symlink")
    requested_root.mkdir(parents=True, exist_ok=True)
    root = requested_root.resolve()
    run_directory = root / "research" / KIS_D1_CANDLE_NOISE_FLOOR_ID / attempt_id
    if run_directory.exists() and run_directory.is_symlink():
        raise ValueError("candle noise-floor run directory must not be a symlink")
    run_directory.mkdir(parents=True, exist_ok=True)
    return run_directory


def _write_or_reattach_contract(path: Path, payload: dict[str, object]) -> dict[str, object]:
    if not path.exists():
        _write_or_verify_json(path, payload)
        return payload
    existing = _read_json_object(path)
    _verify_signed_payload(existing, field_name="campaign_contract_sha256")
    if existing == payload:
        return existing
    if _without_code_revision(existing) != _without_code_revision(payload):
        raise ValueError("candle noise-floor contract conflicts with existing evidence")
    return existing


def _without_code_revision(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result.pop("code_revision", None)
    result.pop("campaign_contract_sha256", None)
    return result


def _write_or_verify_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        if path.is_symlink() or _read_json_object(path) != payload:
            raise ValueError("candle noise-floor artifact already exists with different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("candle noise-floor artifact is invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("candle noise-floor artifact contains invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("candle noise-floor artifact must be an object")
    return cast(dict[str, object], payload)


def _signed_payload(payload: dict[str, object], *, field_name: str) -> dict[str, object]:
    result = dict(payload)
    result[field_name] = _sha256_json(result)
    return result


def _verify_signed_payload(payload: dict[str, object], *, field_name: str) -> str:
    recorded = payload.get(field_name)
    unsigned = dict(payload)
    unsigned.pop(field_name, None)
    if not _is_sha256(recorded) or recorded != _sha256_json(unsigned):
        raise ValueError("candle noise-floor artifact checksum is invalid")
    return cast(str, recorded)


def _input_hash(
    *,
    input_id: str,
    dataset_id: str,
    dataset_hash: str,
    index_hash: str,
    status: NoiseFloorInputStatus,
    reason: str | None,
    training_row_count: int,
    validation_row_count: int,
    validation_symbol_row_counts: tuple[int, ...],
) -> str:
    return _sha256_json(
        {
            "input_id": input_id,
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "index_hash": index_hash,
            "status": status,
            "reason": reason,
            "training_row_count": training_row_count,
            "validation_row_count": validation_row_count,
            "validation_symbol_row_counts": list(validation_symbol_row_counts),
            "window_length": KIS_D1_CANDLE_NOISE_FLOOR_WINDOW_LENGTH,
            "feature_names": list(KIS_D1_CANDLE_NOISE_FLOOR_FEATURE_NAMES),
        }
    )


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "source_local_only": True,
        "point_in_time_claim_allowed": False,
        "corporate_action_claim_allowed": False,
        "survivorship_claim_allowed": False,
        "architecture_selection_allowed": False,
        "profitability_or_pnl_claim": False,
        "paper_input_allowed": False,
        "broker_access": False,
        "live_behavior": False,
        "gpu_used": False,
    }


def _accuracy_bucket(value: float) -> str:
    if value < 0.45:
        return "below_0.45"
    if value < 0.50:
        return "0.45_to_0.50"
    if value < 0.55:
        return "0.50_to_0.55"
    if value < 0.60:
        return "0.55_to_0.60"
    return "at_or_above_0.60"


def _margin_relation(value: float) -> str:
    if value <= 0.0:
        return "at_or_below_null_p95"
    if value < KIS_D1_CANDLE_NOISE_FLOOR_MARGIN:
        return "above_null_below_margin"
    return "meets_or_exceeds_margin"


def _safe_input_reason(error: ValueError) -> str:
    reason = str(error)
    if reason in {
        "single_target_class",
        "invalid_training_normalization",
        "logistic_nonconvergent",
    }:
        return reason
    return "cpu_evaluation_unavailable"


def _are_binary_labels(values: Any, *, numpy: Any) -> bool:
    return values.ndim == 1 and bool(numpy.isin(values, (0, 1)).all())


def _has_both_classes(values: Any, *, numpy: Any) -> bool:
    return _are_binary_labels(values, numpy=numpy) and len(numpy.unique(values)) == 2


def _require_attempt_id(attempt_id: str) -> None:
    if not _SAFE_ATTEMPT_ID.fullmatch(attempt_id):
        raise ValueError("attempt id is invalid")


def _sha256_json(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _numpy() -> Any:
    import numpy

    return numpy

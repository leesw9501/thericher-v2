"""Frozen source-local FirstRate 5m RSI mean-reversion control.

The control reuses the verified FirstRate source loader and its fixed
chronological geometry.  It evaluates one calibration-free, long-only RSI
rule through the deterministic in-memory local-paper simulator and writes only
aggregate evidence outside the Git workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
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
from thericher_v2.execution import LOCAL_PAPER_SOURCE, EmergencyStore, replay_local_paper_account

from .firstrate_5m_after_cost_control import (
    FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
    FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS,
    FIRSTRATE_M5_COST_BPS_PER_SIDE,
    FIRSTRATE_M5_EMBARGO_BARS,
    FIRSTRATE_M5_OBSERVATION_BARS,
    FIRSTRATE_M5_QUANTITY,
    FIRSTRATE_M5_STARTING_CASH,
    FIRSTRATE_M5_TRAIN_FRACTION_DENOMINATOR,
    FIRSTRATE_M5_TRAIN_FRACTION_NUMERATOR,
    FirstRateM5InputUnavailable,
    FirstRateM5Sample,
    FirstRateM5Stream,
    build_firstrate_m5_after_cost_control_input,
)
from .validation import (
    InMemoryCampaignEventStore,
    ValidationConfig,
    ValidationResult,
    run_local_paper_validation,
)

FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID = "firstrate-m5-mean-reversion-after-cost-control-v1"
FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE = "wilder_rsi14_30_50"
FIRSTRATE_M5_RSI_PERIOD_BARS = 14
FIRSTRATE_M5_RSI_ENTRY_THRESHOLD = Decimal("30")
FIRSTRATE_M5_RSI_EXIT_THRESHOLD = Decimal("50")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_SHA256_PREFIX = "sha256:"

_Classification = Literal["rejected", "passed_nonpromoting"]
_CandidateId = Literal["wilder_rsi14_30_50", "always_flat"]


@dataclass(frozen=True)
class FirstRateM5MeanReversionInput:
    """The reattached source-local input allowed by this one control."""

    source_loader_input_sha256: str
    normalization_receipt_sha256: str
    streams: Mapping[str, FirstRateM5Stream]
    input_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "streams", MappingProxyType(dict(self.streams)))
        if (
            tuple(self.streams) != FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or not _is_sha256(self.source_loader_input_sha256)
            or not _is_sha256(self.normalization_receipt_sha256)
            or not _is_sha256(self.input_sha256)
        ):
            raise ValueError("FirstRate M5 mean-reversion input is invalid")

    def source_attestation_payload(self) -> dict[str, object]:
        return {
            "source_loader_control_id": FIRSTRATE_M5_AFTER_COST_CONTROL_ID,
            "source_loader_input_sha256": self.source_loader_input_sha256,
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
                    "source_stream_input_sha256": stream.input_hash,
                }
                for stream in self.streams.values()
            ],
            "mean_reversion_input_sha256": self.input_sha256,
        }


@dataclass(frozen=True)
class FirstRateM5MeanReversionReplayCell:
    candidate_id: _CandidateId
    symbol: str
    cost_bps_per_side: Decimal
    decisions_seen: int
    local_paper_fill_count: int
    entry_fill_count: int
    exit_fill_count: int
    all_fills_local_paper: bool
    replayable: bool
    terminal_flat: bool
    after_cost_pnl: Decimal
    gross_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "cost_bps_per_side", Decimal(self.cost_bps_per_side))
        for field_name in (
            "after_cost_pnl",
            "gross_pnl",
            "total_fees",
            "total_slippage",
        ):
            object.__setattr__(self, field_name, Decimal(getattr(self, field_name)))
        if (
            self.candidate_id
            not in {FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE, "always_flat"}
            or self.symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or self.cost_bps_per_side not in FIRSTRATE_M5_COST_BPS_PER_SIDE
            or min(
                self.decisions_seen,
                self.local_paper_fill_count,
                self.entry_fill_count,
                self.exit_fill_count,
            )
            < 0
            or self.entry_fill_count + self.exit_fill_count != self.local_paper_fill_count
            or self.total_fees < 0
            or self.total_slippage < 0
            or any(
                not value.is_finite()
                for value in (
                    self.after_cost_pnl,
                    self.gross_pnl,
                    self.total_fees,
                    self.total_slippage,
                )
            )
        ):
            raise ValueError("FirstRate M5 mean-reversion replay cell is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "cost_bps_per_side": str(self.cost_bps_per_side),
            "decisions_seen": self.decisions_seen,
            "local_paper_fill_count": self.local_paper_fill_count,
            "entry_fill_count": self.entry_fill_count,
            "exit_fill_count": self.exit_fill_count,
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
class FirstRateM5MeanReversionRun:
    status: Literal["complete", "input_unavailable"]
    run_label: str
    output_dir: Path
    precommit_path: Path | None
    summary_path: Path | None
    input_unavailable_path: Path | None
    classification: _Classification | None


@dataclass(frozen=True)
class FirstRateM5MeanReversionValidationReceipt:
    classification: _Classification
    validation_path: Path
    source_reattached: bool


@dataclass(frozen=True)
class _RsiDecisionModel:
    """One fixed completed-bar policy, with a predeclared terminal flatten."""

    symbol: str
    candidate_id: _CandidateId
    samples_by_decision_start: Mapping[datetime, FirstRateM5Sample]
    terminal_signal_start: datetime | None
    lookback: int = FIRSTRATE_M5_OBSERVATION_BARS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "samples_by_decision_start",
            MappingProxyType(dict(self.samples_by_decision_start)),
        )
        if (
            self.symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or self.candidate_id
            not in {FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE, "always_flat"}
            or self.lookback != FIRSTRATE_M5_OBSERVATION_BARS
            or not self.samples_by_decision_start
            or any(
                sample.symbol != self.symbol
                for sample in self.samples_by_decision_start.values()
            )
            or (
                self.candidate_id == FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE
                and self.terminal_signal_start is not None
                and self.terminal_signal_start not in self.samples_by_decision_start
            )
            or (
                self.candidate_id == "always_flat"
                and self.terminal_signal_start is not None
            )
        ):
            raise ValueError("FirstRate M5 RSI decision model is invalid")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < self.lookback:
            raise ValueError("FirstRate M5 RSI rule requires 60 completed bars")
        latest = bars[-1]
        sample = self.samples_by_decision_start.get(latest.start_ts)
        if sample is None or latest.symbol != self.symbol:
            raise ValueError("FirstRate M5 RSI rule received an unfrozen validation bar")
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
            raise ValueError("FirstRate M5 RSI rule cannot cross a source gap or phase")

        if self.candidate_id == "always_flat":
            action: Literal["buy", "sell", "hold"] = "hold"
            reason = "firstrate_m5_always_flat_control"
        elif latest.start_ts == self.terminal_signal_start:
            action = "sell"
            reason = "firstrate_m5_predeclared_terminal_flatten"
        else:
            rsi = _wilder_rsi(tuple(bar.close for bar in tail))
            if rsi <= FIRSTRATE_M5_RSI_ENTRY_THRESHOLD:
                action = "buy"
                reason = "firstrate_m5_completed_wilder_rsi14_le_30_entry"
            elif rsi >= FIRSTRATE_M5_RSI_EXIT_THRESHOLD:
                action = "sell"
                reason = "firstrate_m5_completed_wilder_rsi14_ge_50_exit"
            else:
                action = "hold"
                reason = "firstrate_m5_completed_wilder_rsi14_between_thresholds_hold"
        confidence = Decimal("1") if action != "hold" else Decimal("0")
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
            metadata={
                "candidate_id": self.candidate_id,
                "observation_bars": FIRSTRATE_M5_OBSERVATION_BARS,
                "rsi_period_bars": FIRSTRATE_M5_RSI_PERIOD_BARS,
                "terminal_flat_required": True,
                "validation_only": True,
            },
        )


def build_firstrate_m5_mean_reversion_input(
    *,
    market_data_root: Path | str = _DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path | str = _DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str = _REPO_ROOT,
) -> FirstRateM5MeanReversionInput:
    """Reattach the fixed source and split without training or calibration."""

    source_input = build_firstrate_m5_after_cost_control_input(
        market_data_root=market_data_root,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    streams = dict(source_input.streams)
    if tuple(streams) != FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS:
        raise ValueError("FirstRate M5 mean-reversion source must contain exactly SPY and QQQ")
    input_sha256 = _sha256_payload(
        {
            "control_id": FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID,
            "source_loader_input_sha256": source_input.input_hash,
            "normalization_receipt_sha256": source_input.normalization_receipt_sha256,
            "streams": [
                {
                    "symbol": stream.symbol,
                    "source_stream_input_sha256": stream.input_hash,
                    "source_dataset_sha256": stream.catalog.dataset_hash,
                }
                for stream in streams.values()
            ],
        }
    )
    return FirstRateM5MeanReversionInput(
        source_loader_input_sha256=source_input.input_hash,
        normalization_receipt_sha256=source_input.normalization_receipt_sha256,
        streams=streams,
        input_sha256=input_sha256,
    )


def run_firstrate_m5_mean_reversion_after_cost_control(
    *,
    run_label: str,
    market_data_root: Path | str = _DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path | str = _DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str = _REPO_ROOT,
) -> FirstRateM5MeanReversionRun:
    """Run one immutable source-local RSI contract or record unavailable input."""

    _validate_run_label(run_label)
    resolved_repo_root = Path(repo_root).resolve()
    resolved_artifact_root = _require_external_root(
        artifact_root,
        repo_root=resolved_repo_root,
        field_name="artifact_root",
    )
    resolved_artifact_root.mkdir(parents=True, exist_ok=True)
    output_dir = _output_dir(resolved_artifact_root, run_label)
    if output_dir.exists():
        raise FileExistsError("FirstRate M5 mean-reversion run label already has external evidence")
    try:
        control_input = build_firstrate_m5_mean_reversion_input(
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
                "control_id": FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID,
                "status": "input_unavailable",
                "reason_code": error.reason_code,
                "training_started": False,
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
        return FirstRateM5MeanReversionRun(
            status="input_unavailable",
            run_label=run_label,
            output_dir=output_dir,
            precommit_path=None,
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
        replay_cells = _run_replay_matrix(
            control_input=control_input,
            precommit_hash=precommit_hash,
            artifact_root=resolved_artifact_root,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "control_id": FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "training_started": False,
                "gpu_used": False,
                "raw_market_data_written": False,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "promotion_allowed": False,
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
            replay_cells=replay_cells,
            classification=classification,
        ),
    )
    return FirstRateM5MeanReversionRun(
        status="complete",
        run_label=run_label,
        output_dir=output_dir,
        precommit_path=precommit_path,
        summary_path=summary_path,
        input_unavailable_path=None,
        classification=classification,
    )


def validate_firstrate_m5_mean_reversion_after_cost_control(
    *,
    run_label: str,
    market_data_root: Path | str = _DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path | str = _DEFAULT_ARTIFACT_ROOT,
    repo_root: Path | str = _REPO_ROOT,
) -> FirstRateM5MeanReversionValidationReceipt:
    """Independently reattach the input, frozen rule, and aggregate result."""

    _validate_run_label(run_label)
    resolved_repo_root = Path(repo_root).resolve()
    resolved_artifact_root = _require_external_root(
        artifact_root,
        repo_root=resolved_repo_root,
        field_name="artifact_root",
    )
    output_dir = _output_dir(resolved_artifact_root, run_label)
    precommit_path = output_dir / "precommit.json"
    summary_path = output_dir / "summary.json"
    precommit = _read_json(precommit_path, field_name="precommit")
    summary = _read_json(summary_path, field_name="summary")
    precommit_hash = _verify_precommit(precommit)
    control_input = build_firstrate_m5_mean_reversion_input(
        market_data_root=market_data_root,
        artifact_root=resolved_artifact_root,
        repo_root=resolved_repo_root,
    )
    expected_attestation = control_input.source_attestation_payload()
    if (
        precommit.get("control_id") != FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID
        or precommit.get("input_attestation") != expected_attestation
        or summary.get("precommit_hash") != precommit_hash
        or summary.get("input_attestation") != expected_attestation
    ):
        raise ValueError("FirstRate M5 mean-reversion evidence binding is invalid")
    _validate_frozen_payload(precommit)
    replay_cells = _parse_replay_cells(summary)
    classification = _classify_replay_cells(replay_cells)
    _validate_summary(summary, classification=classification)
    if _contains_raw_payload_key(summary):
        raise ValueError("FirstRate M5 mean-reversion summary retains raw data")
    if any(
        path.name in {"events.jsonl", "state.sqlite", "emergency.json"}
        for path in output_dir.rglob("*")
        if path.is_file()
    ):
        raise ValueError("FirstRate M5 mean-reversion output retains local-paper events")

    validation_path = output_dir / "validation.json"
    _write_or_verify(
        validation_path,
        {
            "schema_version": SCHEMA_VERSION,
            "control_id": FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID,
            "status": "completed",
            "precommit_hash": precommit_hash,
            "summary_sha256": _sha256(summary_path.read_bytes()),
            "source_reattached": True,
            "mean_reversion_input_sha256": control_input.input_sha256,
            "classification": classification,
            "validation_tuned_configuration": False,
            "training_started": False,
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
        },
    )
    return FirstRateM5MeanReversionValidationReceipt(
        classification=classification,
        validation_path=validation_path,
        source_reattached=True,
    )


def _run_replay_matrix(
    *,
    control_input: FirstRateM5MeanReversionInput,
    precommit_hash: str,
    artifact_root: Path,
) -> tuple[FirstRateM5MeanReversionReplayCell, ...]:
    cells: list[FirstRateM5MeanReversionReplayCell] = []
    with tempfile.TemporaryDirectory(
        dir=artifact_root,
        prefix=".firstrate-m5-mean-reversion-",
    ) as temporary_name:
        temporary_root = Path(temporary_name)
        for _symbol, stream in control_input.streams.items():
            chunks = _contiguous_validation_chunks(stream)
            for cost_bps in FIRSTRATE_M5_COST_BPS_PER_SIDE:
                for candidate_id in (
                    FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE,
                    "always_flat",
                ):
                    cells.append(
                        _run_one_replay(
                            stream=stream,
                            chunks=chunks,
                            candidate_id=candidate_id,
                            cost_bps=cost_bps,
                            work_root=temporary_root,
                            precommit_hash=precommit_hash,
                        )
                    )
    return tuple(cells)


def _run_one_replay(
    *,
    stream: FirstRateM5Stream,
    chunks: tuple[tuple[tuple[Bar, ...], tuple[FirstRateM5Sample, ...]], ...],
    candidate_id: _CandidateId,
    cost_bps: Decimal,
    work_root: Path,
    precommit_hash: str,
) -> FirstRateM5MeanReversionReplayCell:
    work_dir = work_root / f"{stream.symbol.lower()}-{candidate_id}-{cost_bps}bps"
    work_dir.mkdir(parents=True, exist_ok=False)
    try:
        aggregate = _ReplayAggregate()
        for chunk_index, (bars, eligible_samples) in enumerate(chunks, start=1):
            event_store = InMemoryCampaignEventStore()
            chunk_dir = work_dir / f"chunk-{chunk_index:04d}"
            chunk_dir.mkdir(parents=True, exist_ok=False)
            emergency_store = EmergencyStore(chunk_dir / "emergency.json")
            emergency_store.write(
                EmergencyState(
                    stop_new_orders=False,
                    cancel_open_orders_requested=False,
                    reason="firstrate_m5_mean_reversion_validation_only",
                    updated_at=bars[0].start_ts,
                )
            )
            try:
                samples_by_decision_start = {
                    sample.decision_start: sample for sample in eligible_samples
                }
                result = run_local_paper_validation(
                    list(bars),
                    event_store=event_store,
                    emergency_store=emergency_store,
                    model=_RsiDecisionModel(
                        symbol=stream.symbol,
                        candidate_id=candidate_id,
                        samples_by_decision_start=samples_by_decision_start,
                        terminal_signal_start=(
                            eligible_samples[-1].decision_start
                            if candidate_id == FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE
                            else None
                        ),
                    ),
                    config=ValidationConfig(
                        run_id=(
                            f"{FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID}-"
                            f"{stream.symbol.lower()}-{candidate_id}-{cost_bps}bps-"
                            f"chunk-{chunk_index:04d}"
                        ),
                        starting_cash=FIRSTRATE_M5_STARTING_CASH,
                        quantity=FIRSTRATE_M5_QUANTITY,
                        fee_bps=Decimal("0"),
                        slippage_bps=cost_bps,
                        min_bars=FIRSTRATE_M5_OBSERVATION_BARS + 3,
                    ),
                    data_source="firstrate_source_local_m5_in_memory",
                    eligible_signal_starts=frozenset(samples_by_decision_start),
                )
                aggregate.add(result=result, event_store=event_store)
            finally:
                for path in chunk_dir.iterdir():
                    path.unlink()
                chunk_dir.rmdir()
        if not aggregate.replayable or not aggregate.terminal_flat:
            raise RuntimeError("FirstRate M5 mean-reversion replay invariants failed")
        return FirstRateM5MeanReversionReplayCell(
            candidate_id=candidate_id,
            symbol=stream.symbol,
            cost_bps_per_side=cost_bps,
            decisions_seen=aggregate.decisions_seen,
            local_paper_fill_count=aggregate.local_paper_fill_count,
            entry_fill_count=aggregate.entry_fill_count,
            exit_fill_count=aggregate.exit_fill_count,
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
    entry_fill_count: int = 0
    exit_fill_count: int = 0
    all_fills_local_paper: bool = True
    replayable: bool = True
    terminal_flat: bool = True
    after_cost_pnl: Decimal = Decimal("0")
    gross_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")

    def add(
        self,
        *,
        result: ValidationResult,
        event_store: InMemoryCampaignEventStore,
    ) -> None:
        fills = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
        all_fills_local_paper = all(
            event.payload.get("source") == LOCAL_PAPER_SOURCE for event in fills
        )
        replayed_account = replay_local_paper_account(
            event_store,
            starting_cash=FIRSTRATE_M5_STARTING_CASH,
        )
        replayed_position = replayed_account.quantity(
            market=result.market,
            symbol=result.symbol,
        )
        replayable = (
            all_fills_local_paper
            and len(fills) == len(result.trades)
            and replayed_account.cash == result.ending_cash
            and replayed_position == result.final_position
        )
        terminal_flat = result.final_position == 0 and replayed_position == 0
        self.decisions_seen += result.decisions_seen
        self.local_paper_fill_count += len(fills)
        self.entry_fill_count += sum(event.payload.get("side") == "buy" for event in fills)
        self.exit_fill_count += sum(event.payload.get("side") == "sell" for event in fills)
        self.all_fills_local_paper = self.all_fills_local_paper and all_fills_local_paper
        self.replayable = self.replayable and replayable
        self.terminal_flat = self.terminal_flat and terminal_flat
        self.after_cost_pnl += result.after_cost_pnl
        self.gross_pnl += result.gross_pnl
        self.total_fees += result.total_fees
        self.total_slippage += result.total_slippage


def _contiguous_validation_chunks(
    stream: FirstRateM5Stream,
) -> tuple[tuple[tuple[Bar, ...], tuple[FirstRateM5Sample, ...]], ...]:
    window = stream.split.validation_window
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


def _precommit_payload(
    control_input: FirstRateM5MeanReversionInput,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "control_id": FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID,
        "status": "precommitted",
        "claim": (
            "one fixed CPU-only source-local mean-reversion control; not a winner, "
            "selection, ensemble, KIS input, Paper consumer, profitability claim, "
            "or GPU appointment"
        ),
        "input_attestation": control_input.source_attestation_payload(),
        "geometry": {
            "observation_bars": FIRSTRATE_M5_OBSERVATION_BARS,
            "complete_contiguous_windows_only": True,
            "cross_symbol_features": False,
            "time_of_day_features": False,
            "session_reset_features": False,
            "cross_feed_features": False,
            "chronological_train_fraction": {
                "numerator": FIRSTRATE_M5_TRAIN_FRACTION_NUMERATOR,
                "denominator": FIRSTRATE_M5_TRAIN_FRACTION_DENOMINATOR,
            },
            "development_used_for_calibration": False,
            "embargo_bars": FIRSTRATE_M5_EMBARGO_BARS,
            "embargo_covers_observation_plus_target": True,
        },
        "rule": {
            "family": "technical_mean_reversion",
            "candidate_id": FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE,
            "rsi_method": "wilder",
            "rsi_period_bars": FIRSTRATE_M5_RSI_PERIOD_BARS,
            "entry_threshold": str(FIRSTRATE_M5_RSI_ENTRY_THRESHOLD),
            "exit_threshold": str(FIRSTRATE_M5_RSI_EXIT_THRESHOLD),
            "entry_action": "buy_when_completed_wilder_rsi14_lte_30",
            "exit_action": "sell_when_completed_wilder_rsi14_gte_50",
            "terminal_action": "sell_at_next_5m_open_after_last_eligible_completed_bar",
            "calibration_free": True,
            "training_started": False,
            "gpu_used": False,
        },
        "comparators": ["always_flat"],
        "execution": {
            "replay_fill_source": LOCAL_PAPER_SOURCE,
            "entry_or_rule_exit": "next_5m_bar_open",
            "terminal_flat_required": True,
            "synthetic_cost_bps_per_side": [
                str(value) for value in FIRSTRATE_M5_COST_BPS_PER_SIDE
            ],
            "zero_cost_evidence_accepted": False,
            "kis_execution_parity": False,
        },
        "selection": {
            "classification_rule": "all_six_rsi_mean_reversion_vs_flat_nonzero_cost_cells",
            "kill_test": "rsi_mean_reversion_fails_to_beat_always_flat_in_all_six_cells",
            "no_post_outcome_tuning": True,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "gpu_appointment_allowed": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "model_parameters_written": False,
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
    control_input: FirstRateM5MeanReversionInput,
    precommit_hash: str,
    replay_cells: tuple[FirstRateM5MeanReversionReplayCell, ...],
    classification: _Classification,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "control_id": FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "claim": (
            "fixed source-local mean-reversion result only; no winner, architecture selection, "
            "ensemble, KIS input, Paper consumer, or profitability claim"
        ),
        "precommit_hash": precommit_hash,
        "input_attestation": control_input.source_attestation_payload(),
        "rule": {
            "candidate_id": FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE,
            "rsi_method": "wilder",
            "rsi_period_bars": FIRSTRATE_M5_RSI_PERIOD_BARS,
            "entry_threshold": str(FIRSTRATE_M5_RSI_ENTRY_THRESHOLD),
            "exit_threshold": str(FIRSTRATE_M5_RSI_EXIT_THRESHOLD),
            "calibration_free": True,
            "training_started": False,
        },
        "replay_cells": [cell.to_payload() for cell in replay_cells],
        "classification": classification,
        "classification_interpretation": {
            "rejected": (
                "mean-reversion rule did not beat always-flat in every "
                "SPY/QQQ nonzero-cost cell"
            ),
            "passed_nonpromoting": (
                "mean-reversion rule beat always-flat in every SPY/QQQ "
                "nonzero-cost cell; this source-local breadth control still "
                "has no GPU, ensemble, KIS, Paper, or promotion consequence"
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
    cells: Sequence[FirstRateM5MeanReversionReplayCell],
) -> _Classification:
    by_key = {(cell.candidate_id, cell.symbol, cell.cost_bps_per_side): cell for cell in cells}
    expected = {
        (candidate, symbol, cost)
        for candidate in (FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE, "always_flat")
        for symbol in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
        for cost in FIRSTRATE_M5_COST_BPS_PER_SIDE
    }
    if set(by_key) != expected or len(by_key) != len(cells):
        raise ValueError("FirstRate M5 mean-reversion replay matrix is incomplete")
    comparisons: list[bool] = []
    for symbol in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS:
        for cost in FIRSTRATE_M5_COST_BPS_PER_SIDE:
            candidate = by_key[
                (FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE, symbol, cost)
            ]
            flat = by_key[("always_flat", symbol, cost)]
            if not (
                candidate.all_fills_local_paper
                and candidate.replayable
                and candidate.terminal_flat
                and flat.all_fills_local_paper
                and flat.replayable
                and flat.terminal_flat
            ):
                raise ValueError("FirstRate M5 mean-reversion replay invariants are incomplete")
            comparisons.append(candidate.after_cost_pnl > flat.after_cost_pnl)
    return "passed_nonpromoting" if all(comparisons) else "rejected"


def _parse_replay_cells(
    summary: Mapping[str, object],
) -> tuple[FirstRateM5MeanReversionReplayCell, ...]:
    payload_cells = summary.get("replay_cells")
    if not isinstance(payload_cells, list):
        raise ValueError("FirstRate M5 mean-reversion replay cells are invalid")
    cells: list[FirstRateM5MeanReversionReplayCell] = []
    for payload in payload_cells:
        if not isinstance(payload, dict):
            raise ValueError("FirstRate M5 mean-reversion replay cell is invalid")
        candidate_id = payload.get("candidate_id")
        symbol = payload.get("symbol")
        cost = _decimal_payload_field(payload, "cost_bps_per_side")
        if (
            candidate_id
            not in {FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE, "always_flat"}
            or symbol not in FIRSTRATE_M5_AFTER_COST_CONTROL_SYMBOLS
            or cost not in FIRSTRATE_M5_COST_BPS_PER_SIDE
            or payload.get("fill_source") != LOCAL_PAPER_SOURCE
        ):
            raise ValueError("FirstRate M5 mean-reversion replay cell identity is invalid")
        cells.append(
            FirstRateM5MeanReversionReplayCell(
                candidate_id=candidate_id,
                symbol=symbol,
                cost_bps_per_side=cost,
                decisions_seen=_count_payload_field(payload, "decisions_seen"),
                local_paper_fill_count=_count_payload_field(
                    payload,
                    "local_paper_fill_count",
                ),
                entry_fill_count=_count_payload_field(payload, "entry_fill_count"),
                exit_fill_count=_count_payload_field(payload, "exit_fill_count"),
                all_fills_local_paper=_bool_payload_field(
                    payload,
                    "all_fills_local_paper",
                ),
                replayable=_bool_payload_field(payload, "replayable"),
                terminal_flat=_bool_payload_field(payload, "terminal_flat"),
                after_cost_pnl=_decimal_payload_field(payload, "after_cost_pnl"),
                gross_pnl=_decimal_payload_field(payload, "gross_pnl"),
                total_fees=_decimal_payload_field(payload, "total_fees"),
                total_slippage=_decimal_payload_field(payload, "total_slippage"),
            )
        )
    return tuple(cells)


def _validate_summary(
    summary: Mapping[str, object],
    *,
    classification: _Classification,
) -> None:
    if (
        summary.get("control_id") != FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID
        or summary.get("status") != "complete"
        or summary.get("classification") != classification
        or summary.get("rule")
        != {
            "candidate_id": FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE,
            "rsi_method": "wilder",
            "rsi_period_bars": FIRSTRATE_M5_RSI_PERIOD_BARS,
            "entry_threshold": str(FIRSTRATE_M5_RSI_ENTRY_THRESHOLD),
            "exit_threshold": str(FIRSTRATE_M5_RSI_EXIT_THRESHOLD),
            "calibration_free": True,
            "training_started": False,
        }
    ):
        raise ValueError("FirstRate M5 mean-reversion summary is invalid")
    required_false = (
        "gpu_used",
        "network_access",
        "credentials_read",
        "kis_or_broker_called",
        "raw_market_data_written",
        "raw_labels_written",
        "raw_predictions_written",
        "raw_local_paper_events_written",
        "selection_allowed",
        "ensemble_allowed",
        "promotion_allowed",
        "paper_or_execution_consumer_created",
    )
    if any(summary.get(field_name) is not False for field_name in required_false):
        raise ValueError("FirstRate M5 mean-reversion summary crossed a frozen boundary")


def _verify_precommit(precommit: Mapping[str, object]) -> str:
    stored_hash = precommit.get("precommit_hash")
    if not _is_sha256(stored_hash):
        raise ValueError("FirstRate M5 mean-reversion precommit hash is invalid")
    unsigned = dict(precommit)
    unsigned.pop("precommit_hash", None)
    if _sha256_payload(unsigned) != stored_hash:
        raise ValueError("FirstRate M5 mean-reversion precommit hash does not match")
    return stored_hash


def _validate_frozen_payload(precommit: Mapping[str, object]) -> None:
    if (
        precommit.get("status") != "precommitted"
        or precommit.get("control_id") != FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID
        or precommit.get("geometry")
        != {
            "observation_bars": FIRSTRATE_M5_OBSERVATION_BARS,
            "complete_contiguous_windows_only": True,
            "cross_symbol_features": False,
            "time_of_day_features": False,
            "session_reset_features": False,
            "cross_feed_features": False,
            "chronological_train_fraction": {
                "numerator": FIRSTRATE_M5_TRAIN_FRACTION_NUMERATOR,
                "denominator": FIRSTRATE_M5_TRAIN_FRACTION_DENOMINATOR,
            },
            "development_used_for_calibration": False,
            "embargo_bars": FIRSTRATE_M5_EMBARGO_BARS,
            "embargo_covers_observation_plus_target": True,
        }
        or precommit.get("rule")
        != {
            "family": "technical_mean_reversion",
            "candidate_id": FIRSTRATE_M5_MEAN_REVERSION_CANDIDATE,
            "rsi_method": "wilder",
            "rsi_period_bars": FIRSTRATE_M5_RSI_PERIOD_BARS,
            "entry_threshold": str(FIRSTRATE_M5_RSI_ENTRY_THRESHOLD),
            "exit_threshold": str(FIRSTRATE_M5_RSI_EXIT_THRESHOLD),
            "entry_action": "buy_when_completed_wilder_rsi14_lte_30",
            "exit_action": "sell_when_completed_wilder_rsi14_gte_50",
            "terminal_action": "sell_at_next_5m_open_after_last_eligible_completed_bar",
            "calibration_free": True,
            "training_started": False,
            "gpu_used": False,
        }
        or precommit.get("comparators") != ["always_flat"]
    ):
        raise ValueError("FirstRate M5 mean-reversion frozen contract is invalid")
    execution = precommit.get("execution")
    selection = precommit.get("selection")
    artifact_policy = precommit.get("artifact_policy")
    if (
        not isinstance(execution, dict)
        or execution.get("replay_fill_source") != LOCAL_PAPER_SOURCE
        or execution.get("entry_or_rule_exit") != "next_5m_bar_open"
        or execution.get("terminal_flat_required") is not True
        or execution.get("synthetic_cost_bps_per_side")
        != [str(value) for value in FIRSTRATE_M5_COST_BPS_PER_SIDE]
        or execution.get("zero_cost_evidence_accepted") is not False
        or execution.get("kis_execution_parity") is not False
        or not isinstance(selection, dict)
        or selection.get("classification_rule")
        != "all_six_rsi_mean_reversion_vs_flat_nonzero_cost_cells"
        or selection.get("kill_test")
        != "rsi_mean_reversion_fails_to_beat_always_flat_in_all_six_cells"
        or any(
            selection.get(field_name) is not False
            for field_name in (
                "selection_allowed",
                "ensemble_allowed",
                "promotion_allowed",
                "gpu_appointment_allowed",
            )
        )
        or not isinstance(artifact_policy, dict)
        or any(
            artifact_policy.get(field_name) is not False
            for field_name in (
                "repo_storage_allowed",
                "model_parameters_written",
                "raw_market_data_written",
                "raw_labels_written",
                "raw_predictions_written",
                "raw_local_paper_events_written",
            )
        )
    ):
        raise ValueError("FirstRate M5 mean-reversion frozen boundaries are invalid")


def _wilder_rsi(closes: Sequence[Decimal]) -> Decimal:
    """Compute one standard Wilder RSI from completed closing prices only."""

    if len(closes) < FIRSTRATE_M5_RSI_PERIOD_BARS + 1:
        raise ValueError("Wilder RSI requires 15 completed closes")
    changes = tuple(
        current - prior for prior, current in zip(closes[:-1], closes[1:], strict=True)
    )
    seed = changes[:FIRSTRATE_M5_RSI_PERIOD_BARS]
    average_gain = sum((max(change, Decimal("0")) for change in seed), Decimal("0"))
    average_loss = sum((-min(change, Decimal("0")) for change in seed), Decimal("0"))
    divisor = Decimal(FIRSTRATE_M5_RSI_PERIOD_BARS)
    average_gain /= divisor
    average_loss /= divisor
    for change in changes[FIRSTRATE_M5_RSI_PERIOD_BARS:]:
        gain = max(change, Decimal("0"))
        loss = -min(change, Decimal("0"))
        average_gain = (
            average_gain * Decimal(FIRSTRATE_M5_RSI_PERIOD_BARS - 1) + gain
        ) / divisor
        average_loss = (
            average_loss * Decimal(FIRSTRATE_M5_RSI_PERIOD_BARS - 1) + loss
        ) / divisor
    if average_loss == 0:
        return Decimal("100") if average_gain > 0 else Decimal("50")
    if average_gain == 0:
        return Decimal("0")
    relative_strength = average_gain / average_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))


def _contains_raw_payload_key(value: object) -> bool:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "features",
        "labels",
        "predictions",
        "source_path",
        "history_start",
    }
    if isinstance(value, dict):
        return bool(forbidden.intersection(value)) or any(
            _contains_raw_payload_key(nested) for nested in value.values()
        )
    if isinstance(value, list):
        return any(_contains_raw_payload_key(nested) for nested in value)
    return False


def _count_payload_field(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is invalid")
    return value


def _bool_payload_field(payload: Mapping[str, object], field_name: str) -> bool:
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is invalid")
    return value


def _decimal_payload_field(payload: Mapping[str, object], field_name: str) -> Decimal:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is invalid") from error
    if not parsed.is_finite():
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is invalid")
    return parsed


def _output_dir(artifact_root: Path, run_label: str) -> Path:
    root = (artifact_root / FIRSTRATE_M5_MEAN_REVERSION_CONTROL_ID).resolve(strict=False)
    output_dir = (root / run_label).resolve(strict=False)
    if not output_dir.is_relative_to(root):
        raise ValueError("FirstRate M5 mean-reversion run_label escapes artifact root")
    return output_dir


def _require_external_root(
    value: Path | str,
    *,
    repo_root: Path,
    field_name: str,
) -> Path:
    resolved = Path(value).resolve(strict=False)
    if resolved == repo_root or resolved.is_relative_to(repo_root):
        raise ValueError(f"{field_name} must stay outside Git workspace")
    return resolved


def _read_json(path: Path, *, field_name: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is unreadable") from error
    if not isinstance(payload, dict):
        raise ValueError(f"FirstRate M5 mean-reversion {field_name} is invalid")
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
            raise ValueError("FirstRate M5 mean-reversion validation receipt conflicts")
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
        raise ValueError("FirstRate M5 mean-reversion run_label is invalid")


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

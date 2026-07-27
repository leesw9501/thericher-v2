"""Fixed source-local ETF D1 trend-regime falsification control.

The control is deliberately a deterministic offline reference. It never ranks
symbols, fits a model, uses a GPU, or crosses the broker boundary. Replay
events remain in memory; only source-safe aggregate precommit and summary files
are written outside the repository.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    EmergencyState,
    ModelPrediction,
    Signal,
    Timeframe,
)
from thericher_v2.data.d1_liquidity_eligibility import (
    D1_LIQUIDITY_ELIGIBILITY_APPROVED_ARTIFACT_ROOT,
    D1LiquidityEligibilityInstrument,
    SourcePartitionedD1LiquidityEligibility,
    load_source_partitioned_d1_liquidity_eligibility,
    materialize_source_partitioned_d1_liquidity_eligibility,
    require_attested_source_partitioned_d1_liquidity_eligibility,
)
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS,
    load_kis_paper_private_daily_catalog,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.source_scoped_liquid_universe import (
    SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
)
from thericher_v2.research.validation import (
    InMemoryCampaignEventStore,
    ValidationConfig,
    ValidationResult,
    run_local_paper_validation,
)

ETF_D1_TREND_REGIME_ID = "etf-d1-trend-regime-v1"
ETF_D1_TREND_REGIME_RULE_ID = "completed-d1-sma20-over-sma50-long-only-v1"
ETF_D1_TREND_REGIME_SYMBOLS = ("QQQ", "SPY", "IWM")
ETF_D1_TREND_REGIME_SHORT_WINDOW = 20
ETF_D1_TREND_REGIME_LONG_WINDOW = 50
ETF_D1_TREND_REGIME_DECISION_STRIDE_SESSIONS = 2
ETF_D1_TREND_REGIME_DEVELOPMENT_FRACTION_NUMERATOR = 70
ETF_D1_TREND_REGIME_DEVELOPMENT_FRACTION_DENOMINATOR = 100
ETF_D1_TREND_REGIME_STARTING_CASH = Decimal("10000")
ETF_D1_TREND_REGIME_QUANTITY = Decimal("1")
DEFAULT_ETF_D1_TREND_REGIME_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/etf-d1-trend-regime-v1"
)

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_ETF_TARGET_KEY_BY_INSTRUMENT_ID = {
    "QQQ/NAS": "QQQ/NAS/MODP=0",
    "SPY/AMS": "SPY/AMS/MODP=0",
    "IWM/AMS": "IWM/AMS/MODP=0",
}
_ETF_INSTRUMENT_IDS = tuple(_ETF_TARGET_KEY_BY_INSTRUMENT_ID)
_IWM_SOURCE_LIMITATION = "source_limited_history_scope"
_TREND_REGIME_LIMITATIONS = (
    "fixed_source_local_etf_control_only",
    "not_cross_sectional_ranking_or_selection",
    "not_model_promotion_ensemble_gpu_or_paper_input",
    "daily_bar_proxy_does_not_establish_intraday_fillability",
)


@dataclass(frozen=True, slots=True)
class EtfD1TrendRegimeSource:
    """One verified ETF stream retained only in memory for this control."""

    instrument_id: str
    source_snapshot_sha256: str
    limitations: tuple[str, ...]
    cataloged_bars: CatalogedBars

    def __post_init__(self) -> None:
        bars = tuple(self.cataloged_bars.bars)
        if (
            self.instrument_id not in _ETF_INSTRUMENT_IDS
            or not _is_sha256(self.source_snapshot_sha256)
            or not self.limitations
            or not bars
            or bars[0].symbol != self.instrument_id.split("/", 1)[0]
        ):
            raise ValueError("ETF D1 trend-regime source is invalid")
        _validate_source_bars(bars)

    @property
    def symbol(self) -> str:
        return self.instrument_id.split("/", 1)[0]


@dataclass(frozen=True, slots=True)
class EtfD1TrendRegimeReplayMetrics:
    """Aggregate in-memory local-paper replay facts without market values."""

    decision_slot_count: int
    entry_signal_count: int
    trade_count: int
    local_paper_fill_count: int
    after_cost_pnl: Decimal
    gross_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    fill_source: str
    all_fills_local_paper: bool
    final_position: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.decision_slot_count <= 0
            or self.entry_signal_count < 0
            or self.entry_signal_count > self.decision_slot_count
            or self.trade_count != self.entry_signal_count
            or self.local_paper_fill_count != self.trade_count * 2
            or self.fill_source != "local_paper"
            or not self.all_fills_local_paper
            or self.final_position != Decimal("0")
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
            raise ValueError("ETF D1 trend-regime replay metrics are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "decision_slot_count": self.decision_slot_count,
            "entry_signal_count": self.entry_signal_count,
            "trade_count": self.trade_count,
            "local_paper_fill_count": self.local_paper_fill_count,
            "after_cost_pnl": str(self.after_cost_pnl),
            "gross_pnl": str(self.gross_pnl),
            "total_fees": str(self.total_fees),
            "total_slippage": str(self.total_slippage),
            "fill_source": self.fill_source,
            "all_fills_local_paper": self.all_fills_local_paper,
            "final_position": str(self.final_position),
        }


@dataclass(frozen=True, slots=True)
class EtfD1TrendRegimePhaseRun:
    """One source-local chronological phase and its matched comparator."""

    phase: str
    candidate: EtfD1TrendRegimeReplayMetrics
    always_long: EtfD1TrendRegimeReplayMetrics
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.phase not in {"development", "validation"}
            or self.candidate.decision_slot_count != self.always_long.decision_slot_count
        ):
            raise ValueError("ETF D1 trend-regime phase run is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "candidate": self.candidate.to_payload(),
            "time_matched_always_long": self.always_long.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class EtfD1TrendRegimeSymbolRun:
    """All fixed control facts for one ETF, never a relative score."""

    instrument_id: str
    dataset_id: str
    dataset_hash: str
    source_snapshot_sha256: str
    limitations: tuple[str, ...]
    development: EtfD1TrendRegimePhaseRun
    validation: EtfD1TrendRegimePhaseRun
    validation_does_not_beat_always_long: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.instrument_id not in _ETF_INSTRUMENT_IDS
            or not self.dataset_id
            or not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.source_snapshot_sha256)
            or not self.limitations
            or self.development.phase != "development"
            or self.validation.phase != "validation"
            or self.validation_does_not_beat_always_long
            != (
                self.validation.candidate.after_cost_pnl
                <= self.validation.always_long.after_cost_pnl
            )
        ):
            raise ValueError("ETF D1 trend-regime symbol run is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "limitations": list(self.limitations),
            "development": self.development.to_payload(),
            "validation": self.validation.to_payload(),
            "validation_does_not_beat_time_matched_always_long": (
                self.validation_does_not_beat_always_long
            ),
        }


@dataclass(frozen=True, slots=True)
class EtfD1TrendRegimeRun:
    """External precommit/summary paths plus source-safe result facts."""

    eligibility_receipt_sha256: str
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    symbol_runs: tuple[EtfD1TrendRegimeSymbolRun, ...]
    falsified: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol_runs", tuple(self.symbol_runs))
        if (
            not _is_sha256(self.eligibility_receipt_sha256)
            or not _is_sha256(self.precommit_hash)
            or tuple(run.instrument_id for run in self.symbol_runs) != _ETF_INSTRUMENT_IDS
            or self.falsified
            != all(run.validation_does_not_beat_always_long for run in self.symbol_runs)
        ):
            raise ValueError("ETF D1 trend-regime run is invalid")


@dataclass(frozen=True, slots=True)
class _TrendRegimeReplayModel:
    """Fixed timestamp actions for the generic in-memory local-paper harness."""

    model_id: str
    action_by_feature_end: Mapping[datetime, str]
    reason: str
    lookback: int = 0

    def __post_init__(self) -> None:
        actions = dict(self.action_by_feature_end)
        if (
            not self.model_id
            or not self.reason
            or self.lookback != 0
            or not actions
            or any(action not in {"buy", "sell", "hold"} for action in actions.values())
        ):
            raise ValueError("ETF D1 trend-regime replay model is invalid")
        object.__setattr__(self, "action_by_feature_end", MappingProxyType(actions))

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if not bars:
            raise ValueError("ETF D1 trend-regime replay requires a completed bar")
        latest = bars[-1]
        feature_end = latest.end_ts
        action = self.action_by_feature_end.get(feature_end)
        if action is None:
            raise ValueError("ETF D1 trend-regime replay received an unexpected bar")
        if latest.timeframe is not Timeframe.D1 or not latest.complete:
            raise ValueError("ETF D1 trend-regime decision bar is invalid")
        strength = Decimal("0") if action == "hold" else Decimal("1")
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=strength,
            reason=self.reason,
            timeframe=Timeframe.D1,
            generated_at=feature_end,
        )
        return ModelPrediction(
            model_id=self.model_id,
            model_version="1.0.0",
            symbol=signal.symbol,
            market=signal.market,
            signal=signal,
            confidence=strength,
            expected_edge_bps=Decimal("0"),
            feature_window_end=feature_end,
            metadata={"rule_id": ETF_D1_TREND_REGIME_RULE_ID},
        )


@dataclass(slots=True)
class _InMemoryEmergencyStore:
    state: EmergencyState

    def read(self) -> EmergencyState:
        return self.state

    def write(self, state: EmergencyState) -> EmergencyState:
        self.state = state
        return state


def etf_d1_trend_regime_should_enter(*, completed_bars: Sequence[Bar]) -> bool:
    """Evaluate the fixed causal 20/50 D1 condition at the latest close."""

    bars = tuple(completed_bars)
    if len(bars) < ETF_D1_TREND_REGIME_LONG_WINDOW:
        return False
    window = bars[-ETF_D1_TREND_REGIME_LONG_WINDOW :]
    if any(
        bar.timeframe is not Timeframe.D1
        or not bar.complete
        or bar.symbol != window[0].symbol
        or bar.market != window[0].market
        for bar in window
    ):
        raise ValueError("ETF D1 trend-regime rule requires complete homogeneous D1 bars")
    if any(
        later.start_ts <= earlier.start_ts
        for earlier, later in zip(window, window[1:], strict=False)
    ):
        raise ValueError("ETF D1 trend-regime rule requires chronological bars")
    sma50 = _mean(tuple(bar.close for bar in window))
    sma20 = _mean(tuple(bar.close for bar in window[-ETF_D1_TREND_REGIME_SHORT_WINDOW :]))
    return window[-1].close > sma50 and sma20 > sma50


def run_current_etf_d1_trend_regime_control(
    *,
    run_label: str,
    artifact_root: Path | str = DEFAULT_ETF_D1_TREND_REGIME_ARTIFACT_ROOT,
    repository_root: Path | str | None = None,
) -> EtfD1TrendRegimeRun:
    """Reattest current inputs and run the fixed offline ETF control once."""

    repository = _repository_root(repository_root)
    _validate_run_label(run_label)
    materialization = materialize_source_partitioned_d1_liquidity_eligibility(
        repository_root=repository
    )
    eligibility = load_source_partitioned_d1_liquidity_eligibility(
        materialization.receipt_path,
        repository_root=repository,
    )
    sources = _load_current_etf_sources(eligibility=eligibility, repository_root=repository)
    return run_etf_d1_trend_regime_control(
        eligibility_receipt_sha256=eligibility.receipt_sha256,
        sources=sources,
        run_label=run_label,
        artifact_root=artifact_root,
        repository_root=repository,
        require_approved_artifact_root=True,
    )


def _load_current_etf_sources(
    *,
    eligibility: SourcePartitionedD1LiquidityEligibility,
    repository_root: Path,
) -> tuple[EtfD1TrendRegimeSource, ...]:
    verified = require_attested_source_partitioned_d1_liquidity_eligibility(eligibility)
    etf_partition = next(
        (
            partition
            for partition in verified.partitions
            if partition.source_partition_id == SOURCE_SCOPED_LIQUID_UNIVERSE_ETF_SOURCE_ID
        ),
        None,
    )
    if (
        etf_partition is None
        or tuple(item.instrument_id for item in etf_partition.instruments) != _ETF_INSTRUMENT_IDS
        or any(not item.d1_research_eligible for item in etf_partition.instruments)
        or _IWM_SOURCE_LIMITATION not in etf_partition.instruments[-1].limitations
    ):
        raise ValueError("ETF D1 trend-regime eligibility input is incompatible")
    return tuple(
        _load_current_etf_source(
            eligibility_item=item,
            repository_root=repository_root,
        )
        for item in etf_partition.instruments
    )


def _load_current_etf_source(
    *,
    eligibility_item: D1LiquidityEligibilityInstrument,
    repository_root: Path,
) -> EtfD1TrendRegimeSource:
    target_key = _ETF_TARGET_KEY_BY_INSTRUMENT_ID.get(eligibility_item.instrument_id)
    if target_key is None or target_key not in KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS:
        raise ValueError("ETF D1 trend-regime target is unsupported")
    catalog = load_kis_paper_private_daily_catalog(
        target_keys=(target_key,),
        expected_index_hash=eligibility_item.source_snapshot_sha256,
        repo_root=repository_root,
    )
    symbol = eligibility_item.instrument_id.split("/", 1)[0]
    if (
        catalog.dataset_id != eligibility_item.dataset_id
        or catalog.index_hash != eligibility_item.source_snapshot_sha256
        or symbol not in catalog.bars_by_symbol
    ):
        raise ValueError("ETF D1 trend-regime source provenance is incompatible")
    cataloged_bars = catalog.bars_by_symbol[symbol]
    if cataloged_bars.dataset_hash != eligibility_item.dataset_hash:
        raise ValueError("ETF D1 trend-regime source dataset is incompatible")
    return EtfD1TrendRegimeSource(
        instrument_id=eligibility_item.instrument_id,
        source_snapshot_sha256=eligibility_item.source_snapshot_sha256,
        limitations=eligibility_item.limitations,
        cataloged_bars=cataloged_bars,
    )


def run_etf_d1_trend_regime_control(
    *,
    eligibility_receipt_sha256: str,
    sources: Sequence[EtfD1TrendRegimeSource],
    run_label: str,
    artifact_root: Path | str,
    repository_root: Path,
    require_approved_artifact_root: bool,
) -> EtfD1TrendRegimeRun:
    _require_sha256(eligibility_receipt_sha256, "ETF D1 trend-regime receipt hash")
    _validate_run_label(run_label)
    normalized_sources = _validate_sources(sources)
    output_dir = _create_external_output_dir(
        artifact_root=artifact_root,
        repository_root=repository_root,
        run_label=run_label,
        require_approved_artifact_root=require_approved_artifact_root,
    )
    precommit_payload = _precommit_payload(
        eligibility_receipt_sha256=eligibility_receipt_sha256,
        sources=normalized_sources,
    )
    precommit_hash = _sha256_json(precommit_payload)
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, {**precommit_payload, "precommit_hash": precommit_hash})

    try:
        symbol_runs = tuple(_run_symbol(source) for source in normalized_sources)
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "kind": ETF_D1_TREND_REGIME_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "artifact_policy": _artifact_policy_payload(),
            },
        )
        raise

    falsified = all(run.validation_does_not_beat_always_long for run in symbol_runs)
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            eligibility_receipt_sha256=eligibility_receipt_sha256,
            precommit_hash=precommit_hash,
            symbol_runs=symbol_runs,
            falsified=falsified,
        ),
    )
    return EtfD1TrendRegimeRun(
        eligibility_receipt_sha256=eligibility_receipt_sha256,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        symbol_runs=symbol_runs,
        falsified=falsified,
    )


def _run_symbol(source: EtfD1TrendRegimeSource) -> EtfD1TrendRegimeSymbolRun:
    bars = tuple(source.cataloged_bars.bars)
    decision_indices = _decision_indices(bars)
    development_indices, validation_indices = _split_decision_indices(decision_indices)
    development = _run_phase(
        source=source,
        phase="development",
        decision_indices=development_indices,
    )
    validation = _run_phase(
        source=source,
        phase="validation",
        decision_indices=validation_indices,
    )
    return EtfD1TrendRegimeSymbolRun(
        instrument_id=source.instrument_id,
        dataset_id=source.cataloged_bars.dataset_id,
        dataset_hash=source.cataloged_bars.dataset_hash,
        source_snapshot_sha256=source.source_snapshot_sha256,
        limitations=source.limitations,
        development=development,
        validation=validation,
        validation_does_not_beat_always_long=(
            validation.candidate.after_cost_pnl <= validation.always_long.after_cost_pnl
        ),
    )


def _decision_indices(bars: tuple[Bar, ...]) -> tuple[int, ...]:
    _validate_source_bars(bars)
    final_index = len(bars) - 3
    indices = tuple(
        range(
            ETF_D1_TREND_REGIME_LONG_WINDOW - 1,
            final_index + 1,
            ETF_D1_TREND_REGIME_DECISION_STRIDE_SESSIONS,
        )
    )
    if len(indices) < 4:
        raise ValueError("ETF D1 trend-regime source has insufficient decision slots")
    return indices


def _split_decision_indices(indices: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    development_count = (
        len(indices) * ETF_D1_TREND_REGIME_DEVELOPMENT_FRACTION_NUMERATOR
    ) // ETF_D1_TREND_REGIME_DEVELOPMENT_FRACTION_DENOMINATOR
    if development_count <= 0 or development_count >= len(indices):
        raise ValueError("ETF D1 trend-regime source cannot support a 70/30 split")
    development = indices[:development_count]
    validation = indices[development_count:]
    if not validation or development[-1] >= validation[0]:
        raise ValueError("ETF D1 trend-regime split is incompatible")
    return development, validation


def _run_phase(
    *,
    source: EtfD1TrendRegimeSource,
    phase: str,
    decision_indices: tuple[int, ...],
) -> EtfD1TrendRegimePhaseRun:
    candidate_actions, qualified_count = _candidate_actions(
        bars=source.cataloged_bars.bars,
        decision_indices=decision_indices,
    )
    always_long_actions = _always_long_actions(
        bars=source.cataloged_bars.bars,
        decision_indices=decision_indices,
    )
    eligible_signal_starts = _eligible_signal_starts(
        bars=source.cataloged_bars.bars,
        decision_indices=decision_indices,
    )
    candidate = _run_ephemeral_replay(
        source=source,
        phase=phase,
        decision_slot_count=len(decision_indices),
        entry_signal_count=qualified_count,
        eligible_signal_starts=eligible_signal_starts,
        model=_TrendRegimeReplayModel(
            model_id=f"{ETF_D1_TREND_REGIME_ID}-candidate-{source.symbol}-{phase}",
            action_by_feature_end=candidate_actions,
            reason="fixed_d1_trend_regime",
        ),
    )
    always_long = _run_ephemeral_replay(
        source=source,
        phase=phase,
        decision_slot_count=len(decision_indices),
        entry_signal_count=len(decision_indices),
        eligible_signal_starts=eligible_signal_starts,
        model=_TrendRegimeReplayModel(
            model_id=f"{ETF_D1_TREND_REGIME_ID}-always-long-{source.symbol}-{phase}",
            action_by_feature_end=always_long_actions,
            reason="time_matched_always_long",
        ),
    )
    return EtfD1TrendRegimePhaseRun(
        phase=phase,
        candidate=candidate,
        always_long=always_long,
    )


def _candidate_actions(
    *,
    bars: tuple[Bar, ...],
    decision_indices: tuple[int, ...],
) -> tuple[Mapping[datetime, str], int]:
    actions: dict[datetime, str] = {}
    qualified_count = 0
    for index in decision_indices:
        signal_bar = bars[index]
        entry_signal_bar = bars[index + 1]
        qualifies = etf_d1_trend_regime_should_enter(completed_bars=bars[: index + 1])
        actions[signal_bar.end_ts] = "buy" if qualifies else "hold"
        actions[entry_signal_bar.end_ts] = "sell" if qualifies else "hold"
        qualified_count += int(qualifies)
    return MappingProxyType(actions), qualified_count


def _always_long_actions(
    *,
    bars: tuple[Bar, ...],
    decision_indices: tuple[int, ...],
) -> Mapping[datetime, str]:
    actions: dict[datetime, str] = {}
    for index in decision_indices:
        actions[bars[index].end_ts] = "buy"
        actions[bars[index + 1].end_ts] = "sell"
    return MappingProxyType(actions)


def _eligible_signal_starts(
    *,
    bars: tuple[Bar, ...],
    decision_indices: tuple[int, ...],
) -> frozenset[datetime]:
    starts = frozenset(
        timestamp
        for index in decision_indices
        for timestamp in (bars[index].start_ts, bars[index + 1].start_ts)
    )
    if len(starts) != len(decision_indices) * 2:
        raise ValueError("ETF D1 trend-regime decision cadence overlaps")
    return starts


def _run_ephemeral_replay(
    *,
    source: EtfD1TrendRegimeSource,
    phase: str,
    decision_slot_count: int,
    entry_signal_count: int,
    eligible_signal_starts: frozenset[datetime],
    model: _TrendRegimeReplayModel,
) -> EtfD1TrendRegimeReplayMetrics:
    event_store = InMemoryCampaignEventStore()
    first_timestamp = source.cataloged_bars.bars[0].start_ts
    emergency_store = _InMemoryEmergencyStore(
        state=EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason=f"{ETF_D1_TREND_REGIME_ID}-{phase}-offline-replay",
            updated_at=first_timestamp,
        )
    )
    with localcontext() as context:
        context.prec = KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        result = run_local_paper_validation(
            source.cataloged_bars,
            event_store=event_store,
            emergency_store=emergency_store,  # type: ignore[arg-type]
            model=model,
            config=ValidationConfig(
                run_id=f"{ETF_D1_TREND_REGIME_ID}-{source.symbol}-{phase}-{model.model_id}",
                starting_cash=ETF_D1_TREND_REGIME_STARTING_CASH,
                quantity=ETF_D1_TREND_REGIME_QUANTITY,
                fee_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
                slippage_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
            ),
            eligible_signal_starts=eligible_signal_starts,
        )
    fill_events = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
    if (
        result.decisions_seen != len(eligible_signal_starts)
        or result.final_position != Decimal("0")
        or len(fill_events) != len(result.trades)
        or len(fill_events) != entry_signal_count * 2
        or any(event.payload.get("source") != "local_paper" for event in fill_events)
    ):
        raise RuntimeError("ETF D1 trend-regime local-paper replay invariants failed")
    return _metrics_from_validation(
        result=result,
        decision_slot_count=decision_slot_count,
        entry_signal_count=entry_signal_count,
        local_paper_fill_count=len(fill_events),
    )


def _metrics_from_validation(
    *,
    result: ValidationResult,
    decision_slot_count: int,
    entry_signal_count: int,
    local_paper_fill_count: int,
) -> EtfD1TrendRegimeReplayMetrics:
    return EtfD1TrendRegimeReplayMetrics(
        decision_slot_count=decision_slot_count,
        entry_signal_count=entry_signal_count,
        trade_count=len(result.trades) // 2,
        local_paper_fill_count=local_paper_fill_count,
        after_cost_pnl=result.after_cost_pnl,
        gross_pnl=result.gross_pnl,
        total_fees=result.total_fees,
        total_slippage=result.total_slippage,
        fill_source="local_paper",
        all_fills_local_paper=True,
        final_position=result.final_position,
    )


def _precommit_payload(
    *,
    eligibility_receipt_sha256: str,
    sources: tuple[EtfD1TrendRegimeSource, ...],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ETF_D1_TREND_REGIME_ID,
        "status": "precommitted",
        "eligibility_receipt_sha256": eligibility_receipt_sha256,
        "rule": {
            "rule_id": ETF_D1_TREND_REGIME_RULE_ID,
            "completed_d1_only": True,
            "short_sma_sessions": ETF_D1_TREND_REGIME_SHORT_WINDOW,
            "long_sma_sessions": ETF_D1_TREND_REGIME_LONG_WINDOW,
            "enter_condition": "close_gt_sma50_and_sma20_gt_sma50",
            "decision": "completed_session_t_close",
            "entry": "t_plus_1_open",
            "exit": "t_plus_2_open",
            "non_overlapping_decision_stride_sessions": (
                ETF_D1_TREND_REGIME_DECISION_STRIDE_SESSIONS
            ),
        },
        "split": {
            "development_fraction": "70/100",
            "chronological_decision_slot_boundary": True,
            "tuning_allowed": False,
        },
        "costs": {
            "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
            "slippage_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL),
            "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
            "decimal_precision": KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
            "starting_cash": str(ETF_D1_TREND_REGIME_STARTING_CASH),
            "quantity": str(ETF_D1_TREND_REGIME_QUANTITY),
        },
        "comparator": "time_matched_always_long",
        "kill_rule": {
            "validation_falsified_when_every_etf_does_not_beat_comparator": True,
            "per_symbol": True,
            "cross_symbol_aggregation_or_ranking": False,
        },
        "sources": [_source_payload(source) for source in sources],
        "scope": {
            "historical_membership_eligible": False,
            "ranking_eligible": False,
            "model_selection_eligible": False,
            "paper_trading_eligible": False,
            "executable_liquidity_eligible": False,
            "gpu_used": False,
        },
        "limitations": list(_TREND_REGIME_LIMITATIONS),
        "artifact_policy": _artifact_policy_payload(),
    }


def _summary_payload(
    *,
    eligibility_receipt_sha256: str,
    precommit_hash: str,
    symbol_runs: tuple[EtfD1TrendRegimeSymbolRun, ...],
    falsified: bool,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ETF_D1_TREND_REGIME_ID,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "eligibility_receipt_sha256": eligibility_receipt_sha256,
        "precommit_hash": precommit_hash,
        "falsified": falsified,
        "symbol_runs": [run.to_payload() for run in symbol_runs],
        "limitations": list(_TREND_REGIME_LIMITATIONS),
        "artifact_policy": _artifact_policy_payload(),
    }


def _source_payload(source: EtfD1TrendRegimeSource) -> dict[str, object]:
    return {
        "instrument_id": source.instrument_id,
        "dataset_id": source.cataloged_bars.dataset_id,
        "dataset_hash": source.cataloged_bars.dataset_hash,
        "source_snapshot_sha256": source.source_snapshot_sha256,
        "completed_d1_bar_count": len(source.cataloged_bars.bars),
        "limitations": list(source.limitations),
    }


def _artifact_policy_payload() -> dict[str, bool]:
    return {
        "external_artifacts_only": True,
        "raw_market_data_persisted": False,
        "feature_values_persisted": False,
        "prices_persisted": False,
        "weights_persisted": False,
        "checkpoints_persisted": False,
        "credentials_accessed": False,
        "account_data_persisted": False,
        "order_data_persisted": False,
        "network_accessed": False,
        "kis_accessed": False,
        "broker_network_accessed": False,
        "local_paper_only": True,
        "gpu_used": False,
    }


def _validate_sources(
    sources: Sequence[EtfD1TrendRegimeSource],
) -> tuple[EtfD1TrendRegimeSource, ...]:
    normalized = tuple(sources)
    if (
        tuple(source.instrument_id for source in normalized) != _ETF_INSTRUMENT_IDS
        or any(not isinstance(source, EtfD1TrendRegimeSource) for source in normalized)
        or _IWM_SOURCE_LIMITATION not in normalized[-1].limitations
    ):
        raise ValueError("ETF D1 trend-regime sources are incompatible")
    return normalized


def _validate_source_bars(bars: tuple[Bar, ...]) -> None:
    if len(bars) < ETF_D1_TREND_REGIME_LONG_WINDOW + 3:
        raise ValueError("ETF D1 trend-regime requires at least 53 complete D1 bars")
    first = bars[0]
    if first.timeframe is not Timeframe.D1 or not first.complete or any(
        bar.timeframe is not Timeframe.D1
        or not bar.complete
        or bar.symbol != first.symbol
        or bar.market != first.market
        for bar in bars[1:]
    ):
        raise ValueError("ETF D1 trend-regime source bars are invalid")
    if any(
        later.start_ts <= earlier.start_ts
        for earlier, later in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("ETF D1 trend-regime source bars are invalid")


def _create_external_output_dir(
    *,
    artifact_root: Path | str,
    repository_root: Path,
    run_label: str,
    require_approved_artifact_root: bool,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("ETF D1 trend-regime artifact root is invalid")
    resolved = root.resolve()
    if _path_contains(repository_root, resolved):
        raise ValueError("ETF D1 trend-regime artifacts must stay outside Git")
    if require_approved_artifact_root and not _path_contains(
        D1_LIQUIDITY_ELIGIBILITY_APPROVED_ARTIFACT_ROOT,
        resolved,
    ):
        raise ValueError("ETF D1 trend-regime artifact root is unapproved")
    output_dir = resolved / run_label
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("ETF D1 trend-regime run label already exists")
    return output_dir


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    encoded = _json_bytes(payload)
    if path.exists() or path.is_symlink():
        raise FileExistsError("ETF D1 trend-regime artifact already exists")
    staging = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _repository_root(repository_root: Path | str | None) -> Path:
    root = Path(repository_root) if repository_root is not None else Path.cwd()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("ETF D1 trend-regime repository root is invalid")
    return root.resolve()


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("ETF D1 trend-regime run label is invalid")


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("ETF D1 trend-regime average requires values")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _require_sha256(value: object, label: str) -> str:
    if not _is_sha256(value):
        raise ValueError(f"{label} is invalid")
    return str(value)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256_json(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")

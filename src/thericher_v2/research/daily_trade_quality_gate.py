"""CPU-only L2 trade-quality gate for the frozen daily three-ETF selector.

The gate is deliberately narrow: it can abstain from a selected trade, but it
cannot choose a different symbol, alter sizing, or modify the next-open entry
and following-open exit used by the reference selector.  All replayed fills
remain in the broker-free local-paper engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import numpy as np

from thericher_v2.contracts import Bar, OrderIntent, Timeframe, non_negative, positive
from thericher_v2.data.kis_paper_daily import (
    KisPaperPrivateDailyCatalog,
    slice_kis_paper_private_daily_catalog,
)
from thericher_v2.execution import (
    EmergencyStore,
    FillEventArtifact,
    LocalPaperBroker,
    collect_fill_source_evidence,
    replay_local_paper_account,
)
from thericher_v2.state import Event, EventStore

from .daily_three_etf_relative_strength import (
    DAILY_THREE_ETF_RELATIVE_STRENGTH_ID,
    DailyThreeEtfRelativeStrengthConfig,
    _decision_for_index,
    _validated_streams,
)
from .kis_daily_comparative_validation import KisDailyComparativeContract

DAILY_TRADE_QUALITY_GATE_ID = "daily-three-etf-l2-trade-quality-gate-v1"
DEFAULT_DAILY_TRADE_QUALITY_GATE_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/daily-three-etf-l2-trade-quality-gate-v1"
)
_SYMBOLS = ("QQQ", "SPY", "IWM")
_FEATURE_NAMES = (
    "selected_return_20",
    "selected_margin_over_runner_up_20",
    "selected_realized_volatility_20",
    "positive_universe_fraction_20",
)
_MIN_DEVELOPMENT_ENTRIES = 100
_MIN_DEVELOPMENT_LABEL_COUNT = 25
_MIN_VALIDATION_ACCEPTED_TRADES = 20


@dataclass(frozen=True)
class DailyTradeQualityGateConfig:
    run_id: str
    lookback_sessions: int = 20
    decision_stride_sessions: int = 2
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    stress_slippage_bps: Decimal = Decimal("2")
    l2_penalty: float = 0.1
    learning_rate: float = 0.1
    max_iterations: int = 2000
    threshold: float = 0.5
    bootstrap_block_size: int = 5
    bootstrap_samples: int = 1000
    bootstrap_seed: int = 7

    def __post_init__(self) -> None:
        if not _valid_identifier(self.run_id):
            raise ValueError("trade-quality gate run_id is invalid")
        if self.lookback_sessions != 20:
            raise ValueError("trade-quality gate lookback is frozen at 20 sessions")
        if self.decision_stride_sessions != 2:
            raise ValueError("trade-quality gate decision stride is frozen at two sessions")
        object.__setattr__(self, "starting_cash", positive(self.starting_cash, "starting_cash"))
        object.__setattr__(self, "quantity", positive(self.quantity, "quantity"))
        object.__setattr__(self, "fee_bps", non_negative(self.fee_bps, "fee_bps"))
        object.__setattr__(self, "slippage_bps", non_negative(self.slippage_bps, "slippage_bps"))
        object.__setattr__(
            self,
            "stress_slippage_bps",
            non_negative(self.stress_slippage_bps, "stress_slippage_bps"),
        )
        if (
            self.l2_penalty < 0
            or self.learning_rate <= 0
            or self.max_iterations <= 0
            or self.threshold != 0.5
            or self.bootstrap_block_size != 5
            or self.bootstrap_samples <= 0
        ):
            raise ValueError("trade-quality gate configuration is invalid")

    def to_payload(self) -> dict[str, object]:
        """Return every behavior-changing setting for the campaign contract."""

        return {
            "lookback_sessions": self.lookback_sessions,
            "decision_stride_sessions": self.decision_stride_sessions,
            "starting_cash": str(self.starting_cash),
            "quantity": str(self.quantity),
            "fee_bps": str(self.fee_bps),
            "slippage_bps": str(self.slippage_bps),
            "stress_slippage_bps": str(self.stress_slippage_bps),
            "l2_penalty": self.l2_penalty,
            "learning_rate": self.learning_rate,
            "max_iterations": self.max_iterations,
            "threshold": self.threshold,
            "bootstrap_block_size": self.bootstrap_block_size,
            "bootstrap_samples": self.bootstrap_samples,
            "bootstrap_seed": self.bootstrap_seed,
        }


@dataclass(frozen=True)
class DailyTradeQualityGateMetrics:
    scheduled_decision_count: int
    accepted_trade_count: int
    mean_normalized_after_cost_return: float
    max_drawdown: float
    bootstrap_lower_bound_vs_selector: float
    brier_score: float
    prevalence_brier_score: float

    def to_payload(self) -> dict[str, object]:
        return {
            "scheduled_decision_count": self.scheduled_decision_count,
            "accepted_trade_count": self.accepted_trade_count,
            "mean_normalized_after_cost_return": self.mean_normalized_after_cost_return,
            "max_drawdown": self.max_drawdown,
            "bootstrap_lower_bound_vs_selector": self.bootstrap_lower_bound_vs_selector,
            "brier_score": self.brier_score,
            "prevalence_brier_score": self.prevalence_brier_score,
        }


@dataclass(frozen=True)
class DailyTradeQualityGateResult:
    run_id: str
    contract_hash: str
    status: Literal["retired", "retrospective_pass"]
    stop_reasons: tuple[str, ...]
    development_entry_count: int
    development_positive_count: int
    development_negative_count: int
    validation_selector: DailyTradeQualityGateMetrics | None
    validation_candidate: DailyTradeQualityGateMetrics | None
    validation_cash_mean_return: float | None
    stress_candidate_lower_bound_vs_selector: float | None
    all_fills_local_paper: bool
    model_path: Path | None
    summary_path: Path
    summary_sha256: str


@dataclass(frozen=True)
class _Signal:
    decision_id: str
    decided_at: datetime
    symbol: str
    market: str
    signal_close: Decimal
    signal_timestamp: datetime
    entry_open: Decimal
    exit_open: Decimal
    entry_timestamp: datetime
    entry_end_timestamp: datetime
    exit_timestamp: datetime
    features: tuple[float, float, float, float]


@dataclass(frozen=True)
class _Schedule:
    decision_id: str
    decided_at: datetime
    signal: _Signal | None


@dataclass(frozen=True)
class _Replay:
    scheduled_returns: Mapping[str, Decimal]
    local_paper_fill_count: int
    all_fills_local_paper: bool
    event_path: Path
    event_sha256: str
    event_count: int


def run_daily_trade_quality_gate(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    contract: KisDailyComparativeContract,
    config: DailyTradeQualityGateConfig,
    artifact_root: Path | str = DEFAULT_DAILY_TRADE_QUALITY_GATE_ARTIFACT_ROOT,
    repo_root: Path | str | None = None,
) -> DailyTradeQualityGateResult:
    """Fit only development entries and evaluate a frozen validation gate.

    ``catalog`` must end at the post-validation embargo. The core boundary
    rejects a full catalog so the burned historical suffix is never materialized
    into this candidate's process before fitting or replay.
    """

    contract.verify_catalog_prefix(catalog, stop_index=contract.embargo.stop_index)
    work_dir = _prepare_work_dir(
        artifact_root=artifact_root,
        repo_root=repo_root,
        run_id=config.run_id,
    )
    comparative_contract_hash = contract.contract_hash
    config_payload = config.to_payload()
    config_sha256 = _json_payload_sha256(config_payload)
    code_revision = _code_revision(repo_root)
    _contract_path, contract_hash = _write_json(
        work_dir / "contract.json",
        {
            "kind": DAILY_TRADE_QUALITY_GATE_ID,
            "parent_comparative_contract_hash": comparative_contract_hash,
            "comparative_contract": contract.to_payload(),
            "raw_price_limitations": list(catalog.raw_price_limitations),
            "config": config_payload,
            "config_sha256": config_sha256,
            "frozen_model": {
                "family": "l2_logistic_regression",
                "feature_names": list(_FEATURE_NAMES),
                "threshold": config.threshold,
                "l2_penalty": config.l2_penalty,
                "optimizer": "full_batch_gradient_descent",
                "learning_rate": config.learning_rate,
                "max_iterations": config.max_iterations,
                "development_only_standardization": True,
            },
            "target": {
                "kind": "after_cost_selector_trade_sign",
                "decision_time": "completed_session_t",
                "entry": "t_plus_1_open",
                "exit": "t_plus_2_open",
                "label": "one_when_after_cost_return_is_positive",
            },
            "execution": {
                "broker": "local_paper",
                "fee_bps_per_side": str(config.fee_bps),
                "slippage_bps_per_side": str(config.slippage_bps),
            },
            "validation": {
                "primary_metric": "mean_normalized_after_cost_return_per_scheduled_decision",
                "abstention_return": 0.0,
                "bootstrap": {
                    "method": "moving_block",
                    "block_size": config.bootstrap_block_size,
                    "samples": config.bootstrap_samples,
                    "seed": config.bootstrap_seed,
                    "lower_quantile": 0.025,
                },
                "stress_slippage_bps_per_side": str(config.stress_slippage_bps),
            },
            "compute": {"runtime": "cpu_only", "gpu_used": False},
            "code_revision": code_revision,
            "historical_interpretation": contract.historical_interpretation,
        },
    )

    development_catalog = _phase_catalog(catalog, contract, "development")
    development_schedules = _schedules(development_catalog, config=config)
    development_selector = _replay_selector(
        development_schedules,
        accepted_decision_ids={signal.decision_id for signal in _signals(development_schedules)},
        phase="development_selector",
        config=config,
        work_dir=work_dir,
        slippage_bps=config.slippage_bps,
        contract_hash=contract_hash,
    )
    development_rows = _labeled_rows(development_schedules, development_selector)
    labels = np.asarray([label for _signal, label in development_rows], dtype=np.float64)
    positives = int(labels.sum())
    negatives = int(labels.size - positives)
    stop_reasons = _development_stop_reasons(labels.size, positives, negatives)
    if stop_reasons:
        return _write_retired_result(
            work_dir=work_dir,
            config=config,
            contract_hash=contract_hash,
            stop_reasons=stop_reasons,
            development_entry_count=int(labels.size),
            development_positive_count=positives,
            development_negative_count=negatives,
            all_fills_local_paper=development_selector.all_fills_local_paper,
            config_payload=config_payload,
            code_revision=code_revision,
        )

    model = _fit_model(development_rows, config=config)
    model_path, _model_sha256 = _write_json(
        work_dir / "model.json",
        model.to_payload(config=config, config_sha256=config_sha256),
    )

    validation_catalog = _phase_catalog(catalog, contract, "validation")
    validation_schedules = _schedules(validation_catalog, config=config)
    validation_signals = _signals(validation_schedules)
    validation_selector = _replay_selector(
        validation_schedules,
        accepted_decision_ids={signal.decision_id for signal in validation_signals},
        phase="validation_selector",
        config=config,
        work_dir=work_dir,
        slippage_bps=config.slippage_bps,
        contract_hash=contract_hash,
    )
    probabilities = {
        signal.decision_id: model.probability(signal.features) for signal in validation_signals
    }
    accepted_ids = {
        decision_id
        for decision_id, probability in probabilities.items()
        if probability >= config.threshold
    }
    validation_candidate = _replay_selector(
        validation_schedules,
        accepted_decision_ids=accepted_ids,
        phase="validation_candidate",
        config=config,
        work_dir=work_dir,
        slippage_bps=config.slippage_bps,
        contract_hash=contract_hash,
    )
    validation_selector_metrics, validation_candidate_metrics = _validation_metrics(
        schedules=validation_schedules,
        selector=validation_selector,
        candidate=validation_candidate,
        probabilities=probabilities,
        development_prevalence=model.prevalence,
        config=config,
    )

    stress_selector = _replay_selector(
        validation_schedules,
        accepted_decision_ids={signal.decision_id for signal in validation_signals},
        phase="validation_selector_slippage_stress",
        config=config,
        work_dir=work_dir,
        slippage_bps=config.stress_slippage_bps,
        contract_hash=contract_hash,
    )
    stress_candidate = _replay_selector(
        validation_schedules,
        accepted_decision_ids=accepted_ids,
        phase="validation_candidate_slippage_stress",
        config=config,
        work_dir=work_dir,
        slippage_bps=config.stress_slippage_bps,
        contract_hash=contract_hash,
    )
    stress_lower_bound = _bootstrap_lower_bound(
        _return_vector(validation_schedules, stress_candidate)
        - _return_vector(validation_schedules, stress_selector),
        config=config,
    )
    stop_reasons = _validation_stop_reasons(
        candidate=validation_candidate_metrics,
        selector=validation_selector_metrics,
        stress_lower_bound=stress_lower_bound,
    )
    status: Literal["retired", "retrospective_pass"] = (
        "retired" if stop_reasons else "retrospective_pass"
    )
    all_fills_local_paper = all(
        replay.all_fills_local_paper
        for replay in (
            development_selector,
            validation_selector,
            validation_candidate,
            stress_selector,
            stress_candidate,
        )
    )
    summary_path, summary_sha256 = _write_json(
        work_dir / "summary.json",
        {
            "kind": DAILY_TRADE_QUALITY_GATE_ID,
            "run_id": config.run_id,
            "code_revision": code_revision,
            "contract_hash": contract_hash,
            "parent_comparative_contract_hash": comparative_contract_hash,
            "config_sha256": config_sha256,
            "historical_interpretation": contract.historical_interpretation,
            "raw_price_limitations": list(catalog.raw_price_limitations),
            "status": status,
            "stop_reasons": list(stop_reasons),
            "development": {
                "eligible_entries": len(development_rows),
                "positive_labels": positives,
                "negative_labels": negatives,
                "prevalence": model.prevalence,
                "selector_event_sha256": development_selector.event_sha256,
            },
            "validation": {
                "selector": validation_selector_metrics.to_payload(),
                "candidate": validation_candidate_metrics.to_payload(),
                "cash_mean_normalized_after_cost_return": 0.0,
                "stress_slippage_bps_per_side": str(config.stress_slippage_bps),
                "stress_candidate_lower_bound_vs_selector": stress_lower_bound,
                "selector_event_sha256": validation_selector.event_sha256,
                "candidate_event_sha256": validation_candidate.event_sha256,
                "stress_selector_event_sha256": stress_selector.event_sha256,
                "stress_candidate_event_sha256": stress_candidate.event_sha256,
            },
            "execution": {
                "broker": "local_paper",
                "fee_bps_per_side": str(config.fee_bps),
                "slippage_bps_per_side": str(config.slippage_bps),
                "all_fills_local_paper": all_fills_local_paper,
            },
            "model_artifact": str(model_path),
        },
    )
    return DailyTradeQualityGateResult(
        run_id=config.run_id,
        contract_hash=contract_hash,
        status=status,
        stop_reasons=tuple(stop_reasons),
        development_entry_count=len(development_rows),
        development_positive_count=positives,
        development_negative_count=negatives,
        validation_selector=validation_selector_metrics,
        validation_candidate=validation_candidate_metrics,
        validation_cash_mean_return=0.0,
        stress_candidate_lower_bound_vs_selector=stress_lower_bound,
        all_fills_local_paper=all_fills_local_paper,
        model_path=model_path,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
    )


@dataclass(frozen=True)
class _L2LogisticModel:
    mean: tuple[float, float, float, float]
    scale: tuple[float, float, float, float]
    weights: tuple[float, float, float, float]
    intercept: float
    prevalence: float

    def probability(self, features: Sequence[float]) -> float:
        values = np.asarray(features, dtype=np.float64)
        normalized = (values - np.asarray(self.mean)) / np.asarray(self.scale)
        logit = float(normalized @ np.asarray(self.weights) + self.intercept)
        return _sigmoid(logit)

    def to_payload(
        self,
        *,
        config: DailyTradeQualityGateConfig,
        config_sha256: str,
    ) -> dict[str, object]:
        return {
            "kind": DAILY_TRADE_QUALITY_GATE_ID + "_model",
            "family": "l2_logistic_regression",
            "feature_names": list(_FEATURE_NAMES),
            "mean": list(self.mean),
            "scale": list(self.scale),
            "weights": list(self.weights),
            "intercept": self.intercept,
            "development_prevalence": self.prevalence,
            "threshold": 0.5,
            "optimizer": "full_batch_gradient_descent",
            "l2_penalty": config.l2_penalty,
            "learning_rate": config.learning_rate,
            "max_iterations": config.max_iterations,
            "config_sha256": config_sha256,
        }


def _fit_model(
    rows: Sequence[tuple[_Signal, int]],
    *,
    config: DailyTradeQualityGateConfig,
) -> _L2LogisticModel:
    features = np.asarray([signal.features for signal, _label in rows], dtype=np.float64)
    labels = np.asarray([label for _signal, label in rows], dtype=np.float64)
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-12] = 1.0
    normalized = (features - mean) / scale
    prevalence = float(labels.mean())
    intercept = float(np.log(prevalence / (1.0 - prevalence)))
    weights = np.zeros(normalized.shape[1], dtype=np.float64)
    for _ in range(config.max_iterations):
        probabilities = _sigmoid_array(normalized @ weights + intercept)
        residual = probabilities - labels
        gradient_weights = (normalized.T @ residual) / len(labels) + config.l2_penalty * weights
        gradient_intercept = float(residual.mean())
        weights -= config.learning_rate * gradient_weights
        intercept -= config.learning_rate * gradient_intercept
    return _L2LogisticModel(
        mean=tuple(float(value) for value in mean),
        scale=tuple(float(value) for value in scale),
        weights=tuple(float(value) for value in weights),
        intercept=float(intercept),
        prevalence=prevalence,
    )


def _phase_catalog(
    catalog: KisPaperPrivateDailyCatalog,
    contract: KisDailyComparativeContract,
    phase: Literal["development", "validation"],
) -> KisPaperPrivateDailyCatalog:
    segment = contract.segment_for(phase)
    return slice_kis_paper_private_daily_catalog(
        catalog,
        start_index=segment.start_index,
        stop_index=segment.stop_index,
    )


def _schedules(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    config: DailyTradeQualityGateConfig,
) -> tuple[_Schedule, ...]:
    streams = _validated_streams(catalog)
    strategy_config = DailyThreeEtfRelativeStrengthConfig(
        run_id=f"{config.run_id}-signals",
        lookback_sessions=config.lookback_sessions,
        decision_stride_sessions=config.decision_stride_sessions,
        starting_cash=config.starting_cash,
        quantity=config.quantity,
        fee_bps=config.fee_bps,
        slippage_bps=config.slippage_bps,
    )
    schedules: list[_Schedule] = []
    for index in range(
        config.lookback_sessions,
        len(catalog.common_sessions) - 2,
        config.decision_stride_sessions,
    ):
        decision, signal_bars = _decision_for_index(
            streams=streams,
            index=index,
            config=strategy_config,
        )
        if decision.selected_symbol is None:
            schedules.append(
                _Schedule(
                    decision_id=decision.decision_id,
                    decided_at=decision.decided_at,
                    signal=None,
                )
            )
            continue
        strengths = dict(decision.strengths)
        selected = decision.selected_symbol
        selected_strength = strengths[selected]
        runner_up = max(value for symbol, value in strengths.items() if symbol != selected)
        closes = streams[selected]
        returns = [
            float((closes[step].close / closes[step - 1].close) - Decimal("1"))
            for step in range(index - config.lookback_sessions + 1, index + 1)
        ]
        selected_bar = signal_bars[selected]
        schedules.append(
            _Schedule(
                decision_id=decision.decision_id,
                decided_at=decision.decided_at,
                signal=_Signal(
                    decision_id=decision.decision_id,
                    decided_at=decision.decided_at,
                    symbol=selected,
                    market=selected_bar.market,
                    signal_close=selected_bar.close,
                    signal_timestamp=selected_bar.start_ts,
                    entry_open=streams[selected][index + 1].open,
                    exit_open=streams[selected][index + 2].open,
                    entry_timestamp=streams[selected][index + 1].start_ts,
                    entry_end_timestamp=streams[selected][index + 1].end_ts,
                    exit_timestamp=streams[selected][index + 2].start_ts,
                    features=(
                        float(selected_strength),
                        float(selected_strength - runner_up),
                        float(np.std(np.asarray(returns, dtype=np.float64))),
                        sum(value > 0 for value in strengths.values()) / len(_SYMBOLS),
                    ),
                ),
            )
        )
    return tuple(schedules)


def _signals(schedules: Sequence[_Schedule]) -> tuple[_Signal, ...]:
    return tuple(schedule.signal for schedule in schedules if schedule.signal is not None)


def _replay_selector(
    schedules: Sequence[_Schedule],
    *,
    accepted_decision_ids: set[str],
    phase: str,
    config: DailyTradeQualityGateConfig,
    work_dir: Path,
    slippage_bps: Decimal,
    contract_hash: str,
) -> _Replay:
    replay_root = work_dir / "replays" / phase
    replay_root.mkdir(parents=True)
    events = EventStore(
        db_path=replay_root / "state.sqlite",
        jsonl_path=replay_root / "events.jsonl",
        rebuild_sqlite_on_append=False,
    )
    broker = LocalPaperBroker(
        event_store=events,
        emergency_store=EmergencyStore(replay_root / "emergency.json"),
        starting_cash=config.starting_cash,
        fee_bps=config.fee_bps,
        slippage_bps=slippage_bps,
    )
    scheduled_returns: dict[str, Decimal] = {}
    fill_count = 0
    for ordinal, schedule in enumerate(schedules, start=1):
        signal = schedule.signal
        accepted = signal is not None and signal.decision_id in accepted_decision_ids
        events.append(
            Event(
                event_type="daily_trade_quality_gate_decision",
                created_at=schedule.decided_at,
                payload={
                    "source": DAILY_TRADE_QUALITY_GATE_ID,
                    "phase": phase,
                    "decision_id": schedule.decision_id,
                    "base_strategy_id": DAILY_THREE_ETF_RELATIVE_STRENGTH_ID,
                    "action": "enter" if accepted else "abstain",
                    "selected_symbol": None if signal is None else signal.symbol,
                    "contract_hash": contract_hash,
                },
            )
        )
        if not accepted:
            scheduled_returns[schedule.decision_id] = Decimal("0")
            continue
        assert signal is not None
        entry = broker.submit_and_fill_next_bar(
            OrderIntent(
                client_order_id=f"{config.run_id}-{phase}-{ordinal:04d}-entry",
                symbol=signal.symbol,
                market=signal.market,
                side="buy",
                quantity=config.quantity,
                limit_price=None,
                decision_id=signal.decision_id,
                created_at=schedule.decided_at,
            ),
            signal_bar=_signal_bar(signal),
            execution_bar=_entry_bar(signal),
        )
        if entry.fill is None:
            raise RuntimeError("trade-quality gate entry did not produce a local-paper fill")
        exit_execution = broker.submit_and_fill_next_bar(
            OrderIntent(
                client_order_id=f"{config.run_id}-{phase}-{ordinal:04d}-exit",
                symbol=signal.symbol,
                market=signal.market,
                side="sell",
                quantity=entry.fill.quantity,
                limit_price=None,
                decision_id=f"{signal.decision_id}:flatten",
                created_at=signal.entry_end_timestamp,
            ),
            signal_bar=_entry_bar(signal),
            execution_bar=_exit_bar(signal),
        )
        if exit_execution.fill is None:
            raise RuntimeError("trade-quality gate exit did not produce a local-paper fill")
        fill_count += 2
        entry_cost = entry.fill.price * entry.fill.quantity + entry.fill.fee
        exit_value = (
            exit_execution.fill.price * exit_execution.fill.quantity - exit_execution.fill.fee
        )
        scheduled_returns[signal.decision_id] = (exit_value - entry_cost) / entry_cost

    evidence = collect_fill_source_evidence(
        (
            FillEventArtifact(
                path=events.jsonl_path,
                expected_fill_count=fill_count,
                label=phase,
            ),
        )
    )
    if not evidence.local_paper_replay_invariant_passed:
        raise RuntimeError("trade-quality gate must use replayable local-paper fills")
    account = broker.account()
    replayed_account = replay_local_paper_account(events, starting_cash=config.starting_cash)
    if account != replayed_account or account.positions:
        raise RuntimeError("trade-quality gate replay must finish flat and replayable")
    events.rebuild_sqlite()
    event_payload = events.jsonl_path.read_bytes()
    event_sha256 = _sha256(event_payload)
    event_count = len(tuple(events.iter_events()))
    _write_json(
        replay_root / "run.json",
        {
            "kind": DAILY_TRADE_QUALITY_GATE_ID + "_replay",
            "phase": phase,
            "contract_hash": contract_hash,
            "execution": {
                "broker": "local_paper",
                "fee_bps_per_side": str(config.fee_bps),
                "slippage_bps_per_side": str(slippage_bps),
                "expected_fill_count": fill_count,
            },
            "evidence": {
                "event_jsonl_sha256": event_sha256,
                "event_count": event_count,
                "all_fills_local_paper": evidence.all_fills_local_paper,
            },
        },
    )
    return _Replay(
        scheduled_returns=scheduled_returns,
        local_paper_fill_count=fill_count,
        all_fills_local_paper=evidence.all_fills_local_paper,
        event_path=events.jsonl_path,
        event_sha256=event_sha256,
        event_count=event_count,
    )


def _signal_bar(signal: _Signal) -> Bar:
    return _bar_at(signal, timestamp=signal.signal_timestamp, price=signal.signal_close)


def _entry_bar(signal: _Signal) -> Bar:
    return _bar_at(signal, timestamp=signal.entry_timestamp, price=signal.entry_open)


def _exit_bar(signal: _Signal) -> Bar:
    return _bar_at(signal, timestamp=signal.exit_timestamp, price=signal.exit_open)


def _bar_at(signal: _Signal, *, timestamp: datetime, price: Decimal) -> Bar:
    """Build only the OHLC fields LocalPaperBroker needs from frozen source bars."""

    return Bar(
        symbol=signal.symbol,
        market=signal.market,
        timeframe=Timeframe.D1,
        start_ts=timestamp,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1"),
        complete=True,
    )


def _labeled_rows(
    schedules: Sequence[_Schedule],
    replay: _Replay,
) -> tuple[tuple[_Signal, int], ...]:
    rows: list[tuple[_Signal, int]] = []
    for signal in _signals(schedules):
        realized = replay.scheduled_returns.get(signal.decision_id)
        if realized is None:
            raise RuntimeError("selector replay omitted an eligible trade-quality signal")
        rows.append((signal, int(realized > 0)))
    return tuple(rows)


def _validation_metrics(
    *,
    schedules: Sequence[_Schedule],
    selector: _Replay,
    candidate: _Replay,
    probabilities: Mapping[str, float],
    development_prevalence: float,
    config: DailyTradeQualityGateConfig,
) -> tuple[DailyTradeQualityGateMetrics, DailyTradeQualityGateMetrics]:
    selector_returns = _return_vector(schedules, selector)
    candidate_returns = _return_vector(schedules, candidate)
    labels = np.asarray(
        [int(selector.scheduled_returns[signal.decision_id] > 0) for signal in _signals(schedules)],
        dtype=np.float64,
    )
    probability_values = np.asarray(
        [probabilities[signal.decision_id] for signal in _signals(schedules)], dtype=np.float64
    )
    if labels.size == 0:
        raise RuntimeError("trade-quality validation has no eligible selector entries")
    candidate_metrics = DailyTradeQualityGateMetrics(
        scheduled_decision_count=len(schedules),
        accepted_trade_count=candidate.local_paper_fill_count // 2,
        mean_normalized_after_cost_return=float(candidate_returns.mean()),
        max_drawdown=_max_drawdown(candidate_returns),
        bootstrap_lower_bound_vs_selector=_bootstrap_lower_bound(
            candidate_returns - selector_returns,
            config=config,
        ),
        brier_score=float(np.mean((probability_values - labels) ** 2)),
        prevalence_brier_score=float(np.mean((development_prevalence - labels) ** 2)),
    )
    selector_metrics = DailyTradeQualityGateMetrics(
        scheduled_decision_count=len(schedules),
        accepted_trade_count=len(_signals(schedules)),
        mean_normalized_after_cost_return=float(selector_returns.mean()),
        max_drawdown=_max_drawdown(selector_returns),
        bootstrap_lower_bound_vs_selector=0.0,
        brier_score=float(np.mean((development_prevalence - labels) ** 2)),
        prevalence_brier_score=float(np.mean((development_prevalence - labels) ** 2)),
    )
    return selector_metrics, candidate_metrics


def _return_vector(schedules: Sequence[_Schedule], replay: _Replay) -> np.ndarray:
    return np.asarray(
        [float(replay.scheduled_returns[schedule.decision_id]) for schedule in schedules],
        dtype=np.float64,
    )


def _development_stop_reasons(entries: int, positives: int, negatives: int) -> list[str]:
    reasons: list[str] = []
    if entries < _MIN_DEVELOPMENT_ENTRIES:
        reasons.append("development_eligible_entries_below_100")
    if positives < _MIN_DEVELOPMENT_LABEL_COUNT or negatives < _MIN_DEVELOPMENT_LABEL_COUNT:
        reasons.append("development_label_class_below_25")
    return reasons


def _validation_stop_reasons(
    *,
    candidate: DailyTradeQualityGateMetrics,
    selector: DailyTradeQualityGateMetrics,
    stress_lower_bound: float,
) -> list[str]:
    reasons: list[str] = []
    if candidate.accepted_trade_count < _MIN_VALIDATION_ACCEPTED_TRADES:
        reasons.append("validation_accepted_trades_below_20")
    if candidate.bootstrap_lower_bound_vs_selector <= 0:
        reasons.append("validation_bootstrap_lower_bound_nonpositive")
    if candidate.brier_score > candidate.prevalence_brier_score:
        reasons.append("validation_brier_worse_than_prevalence")
    if candidate.max_drawdown > selector.max_drawdown:
        reasons.append("validation_drawdown_worse_than_selector")
    if stress_lower_bound <= 0:
        reasons.append("slippage_stress_bootstrap_lower_bound_nonpositive")
    return reasons


def _bootstrap_lower_bound(
    differences: np.ndarray,
    *,
    config: DailyTradeQualityGateConfig,
) -> float:
    if differences.ndim != 1 or differences.size < config.bootstrap_block_size:
        return float("-inf")
    block_count = int(np.ceil(differences.size / config.bootstrap_block_size))
    starts = np.arange(differences.size - config.bootstrap_block_size + 1)
    generator = np.random.default_rng(config.bootstrap_seed)
    samples = np.empty(config.bootstrap_samples, dtype=np.float64)
    for index in range(config.bootstrap_samples):
        selected: list[float] = []
        for start in generator.choice(starts, size=block_count, replace=True):
            selected.extend(differences[start : start + config.bootstrap_block_size])
        samples[index] = float(np.mean(selected[: differences.size]))
    return float(np.quantile(samples, 0.025))


def _max_drawdown(returns: np.ndarray) -> float:
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= 1.0 + float(value)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    return drawdown


def _sigmoid(value: float) -> float:
    return float(_sigmoid_array(np.asarray([value], dtype=np.float64))[0])


def _sigmoid_array(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _write_retired_result(
    *,
    work_dir: Path,
    config: DailyTradeQualityGateConfig,
    contract_hash: str,
    stop_reasons: Sequence[str],
    development_entry_count: int,
    development_positive_count: int,
    development_negative_count: int,
    all_fills_local_paper: bool,
    config_payload: Mapping[str, object],
    code_revision: str | None,
) -> DailyTradeQualityGateResult:
    summary_path, summary_sha256 = _write_json(
        work_dir / "summary.json",
        {
            "kind": DAILY_TRADE_QUALITY_GATE_ID,
            "run_id": config.run_id,
            "code_revision": code_revision,
            "contract_hash": contract_hash,
            "config": dict(config_payload),
            "config_sha256": _json_payload_sha256(config_payload),
            "status": "retired",
            "stop_reasons": list(stop_reasons),
            "development": {
                "eligible_entries": development_entry_count,
                "positive_labels": development_positive_count,
                "negative_labels": development_negative_count,
            },
            "execution": {"broker": "local_paper", "all_fills_local_paper": all_fills_local_paper},
        },
    )
    return DailyTradeQualityGateResult(
        run_id=config.run_id,
        contract_hash=contract_hash,
        status="retired",
        stop_reasons=tuple(stop_reasons),
        development_entry_count=development_entry_count,
        development_positive_count=development_positive_count,
        development_negative_count=development_negative_count,
        validation_selector=None,
        validation_candidate=None,
        validation_cash_mean_return=None,
        stress_candidate_lower_bound_vs_selector=None,
        all_fills_local_paper=all_fills_local_paper,
        model_path=None,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
    )


def _prepare_work_dir(
    *,
    artifact_root: Path | str,
    repo_root: Path | str | None,
    run_id: str,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("trade-quality gate artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    if repo_root is not None and resolved_root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("trade-quality gate artifacts must stay outside Git")
    work_dir = resolved_root / run_id
    if work_dir.exists() or work_dir.is_symlink():
        raise FileExistsError("trade-quality gate run directory already exists")
    work_dir.mkdir()
    return work_dir


def _write_json(path: Path, payload: Mapping[str, object]) -> tuple[Path, str]:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path, _sha256(encoded)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_payload_sha256(payload: Mapping[str, object]) -> str:
    return _sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _code_revision(repo_root: Path | str | None) -> str | None:
    if repo_root is None:
        return None
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _valid_identifier(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character in {"-", "_", "."} for character in value
    )

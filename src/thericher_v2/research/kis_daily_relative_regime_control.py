"""Frozen QQQ/SPY D1 relative-regime falsification control.

The control is intentionally a narrow, CPU-only research reference.  It
re-attests the existing private daily catalog, computes the fixed phase-local
63-session comparison in memory, and uses the existing broker-free
``local_paper`` simulator.  Only aggregate, source-safe receipts are retained
outside the repository; prices, derived feature values, event logs, and model
artifacts never leave memory.
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
from typing import Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    EmergencyState,
    ModelPrediction,
    Signal,
    Timeframe,
)
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
    load_kis_paper_private_daily_catalog,
    slice_kis_paper_private_daily_catalog,
)
from thericher_v2.execution.local_paper import replay_local_paper_account
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
)
from thericher_v2.research.historical_kis_campaign import (
    HISTORICAL_KIS_DAILY_TARGET_KEYS,
)

from .validation import (
    InMemoryCampaignEventStore,
    ValidationConfig,
    ValidationResult,
    run_local_paper_validation,
)

KIS_DAILY_RELATIVE_REGIME_CONTROL_ID = "kis-daily-relative-regime-control-v1"
KIS_DAILY_RELATIVE_REGIME_RULE_ID = "qqq-spy-d1-relative-regime-63-v1"
KIS_DAILY_RELATIVE_REGIME_SYMBOLS = ("QQQ", "SPY")
KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS = 63
KIS_DAILY_RELATIVE_REGIME_DECISION_STRIDE_SESSIONS = 2
KIS_DAILY_RELATIVE_REGIME_DEVELOPMENT_SESSIONS = 3783
KIS_DAILY_RELATIVE_REGIME_PURGE_SESSIONS = 22
KIS_DAILY_RELATIVE_REGIME_VALIDATION_SESSIONS = 951
KIS_DAILY_RELATIVE_REGIME_TOTAL_SESSIONS = (
    KIS_DAILY_RELATIVE_REGIME_DEVELOPMENT_SESSIONS
    + KIS_DAILY_RELATIVE_REGIME_PURGE_SESSIONS
    + KIS_DAILY_RELATIVE_REGIME_VALIDATION_SESSIONS
)
KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT = 2
KIS_DAILY_RELATIVE_REGIME_STARTING_CASH = Decimal("10000")
KIS_DAILY_RELATIVE_REGIME_QUANTITY = Decimal("1")
DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts"
)

_EXPECTED_CATALOG_DATASET_HASH = (
    "sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718"
)
_EXPECTED_CATALOG_INDEX_HASH = (
    "sha256:e0bb847994a97b1df1181b0013fabcb784d979c7c366f686940e563cb01ac660"
)
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

RelativeRegimeMode = Literal["cpu-smoke", "cpu-full"]
RelativeRegimeOutcome = Literal["operational_smoke", "falsified", "candidate_only"]
_ReplayRole = Literal["candidate", "always_long", "flat"]


@dataclass(frozen=True, slots=True)
class KisDailyRelativeRegimeSplit:
    """The exact chronological phase counts for the existing QQQ/SPY panel."""

    development_session_count: int = KIS_DAILY_RELATIVE_REGIME_DEVELOPMENT_SESSIONS
    purge_session_count: int = KIS_DAILY_RELATIVE_REGIME_PURGE_SESSIONS
    validation_session_count: int = KIS_DAILY_RELATIVE_REGIME_VALIDATION_SESSIONS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_session_count
            != KIS_DAILY_RELATIVE_REGIME_DEVELOPMENT_SESSIONS
            or self.purge_session_count != KIS_DAILY_RELATIVE_REGIME_PURGE_SESSIONS
            or self.validation_session_count
            != KIS_DAILY_RELATIVE_REGIME_VALIDATION_SESSIONS
        ):
            raise ValueError("KIS daily relative-regime split is frozen")

    @property
    def validation_start_index(self) -> int:
        return self.development_session_count + self.purge_session_count

    @property
    def total_session_count(self) -> int:
        return (
            self.development_session_count
            + self.purge_session_count
            + self.validation_session_count
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "phase_local_feature_window": True,
            "phase_local_warmup_session_count": KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS,
        }


@dataclass(frozen=True, slots=True)
class KisDailyRelativeRegimeInput:
    """Hash-attested, phase-local QQQ/SPY streams kept only in memory."""

    catalog: KisPaperPrivateDailyCatalog
    split: KisDailyRelativeRegimeSplit
    development_catalog: KisPaperPrivateDailyCatalog
    validation_catalog: KisPaperPrivateDailyCatalog
    development_decision_indices: tuple[int, ...]
    validation_decision_indices: tuple[int, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "development_decision_indices",
            tuple(self.development_decision_indices),
        )
        object.__setattr__(
            self,
            "validation_decision_indices",
            tuple(self.validation_decision_indices),
        )
        _validate_full_catalog(self.catalog)
        if (
            len(self.catalog.common_sessions) != self.split.total_session_count
            or len(self.development_catalog.common_sessions)
            != self.split.development_session_count
            or len(self.validation_catalog.common_sessions)
            != self.split.validation_session_count
            or self.development_catalog.common_sessions
            != self.catalog.common_sessions[: self.split.development_session_count]
            or self.validation_catalog.common_sessions
            != self.catalog.common_sessions[self.split.validation_start_index :]
        ):
            raise ValueError("KIS daily relative-regime phase slices are invalid")
        _validate_phase_catalog(
            self.development_catalog,
            expected_count=self.split.development_session_count,
        )
        _validate_phase_catalog(
            self.validation_catalog,
            expected_count=self.split.validation_session_count,
        )
        if (
            self.development_decision_indices
            != _phase_decision_indices(self.development_catalog)
            or self.validation_decision_indices
            != _phase_decision_indices(self.validation_catalog)
        ):
            raise ValueError("KIS daily relative-regime decision slots are invalid")


@dataclass(frozen=True, slots=True)
class KisDailyRelativeRegimeReplayMetrics:
    """Aggregate local-paper facts that contain no source values or decisions."""

    role: _ReplayRole
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
    replayable: bool
    final_position: Decimal
    replay_identity_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.role not in {"candidate", "always_long", "flat"}
            or self.decision_slot_count <= 0
            or self.entry_signal_count < 0
            or self.entry_signal_count > self.decision_slot_count
            or self.trade_count != self.entry_signal_count
            or self.local_paper_fill_count != self.trade_count * 2
            or self.fill_source != "local_paper"
            or not self.all_fills_local_paper
            or not self.replayable
            or self.final_position != Decimal("0")
            or not _is_sha256(self.replay_identity_hash)
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
            raise ValueError("KIS daily relative-regime replay metrics are invalid")
        if self.role == "flat" and (self.entry_signal_count or self.trade_count):
            raise ValueError("KIS daily relative-regime flat baseline must stay flat")
        if self.role == "always_long" and self.entry_signal_count != self.decision_slot_count:
            raise ValueError("KIS daily relative-regime always-long baseline is unaligned")

    def to_payload(self) -> dict[str, object]:
        return {
            "role": self.role,
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
            "replayable": self.replayable,
            "final_position": str(self.final_position),
            "replay_identity_hash": self.replay_identity_hash,
        }


@dataclass(frozen=True, slots=True)
class KisDailyRelativeRegimeControlRun:
    """One immutable, non-promoting CPU control result."""

    control_input: KisDailyRelativeRegimeInput
    mode: RelativeRegimeMode
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    candidate: KisDailyRelativeRegimeReplayMetrics
    always_long: KisDailyRelativeRegimeReplayMetrics
    flat: KisDailyRelativeRegimeReplayMetrics
    outcome: RelativeRegimeOutcome
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.mode not in {"cpu-smoke", "cpu-full"}
            or not self.precommit_path.is_file()
            or not self.summary_path.is_file()
            or not _is_sha256(self.precommit_hash)
            or self.candidate.role != "candidate"
            or self.always_long.role != "always_long"
            or self.flat.role != "flat"
            or not (
                self.candidate.decision_slot_count
                == self.always_long.decision_slot_count
                == self.flat.decision_slot_count
            )
            or self.outcome
            != classify_kis_daily_relative_regime_outcome(
                mode=self.mode,
                candidate=self.candidate,
                always_long=self.always_long,
                flat=self.flat,
            )
        ):
            raise ValueError("KIS daily relative-regime control result is invalid")


@dataclass(frozen=True, slots=True)
class _RelativeRegimeReplayModel:
    """Fixed in-memory actions for the existing local-paper validation harness."""

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
            raise ValueError("KIS daily relative-regime replay model is invalid")
        object.__setattr__(self, "action_by_feature_end", MappingProxyType(actions))

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if not bars:
            raise ValueError("KIS daily relative-regime replay requires a completed bar")
        latest = bars[-1]
        action = self.action_by_feature_end.get(latest.end_ts)
        if action is None:
            raise ValueError("KIS daily relative-regime replay received an unexpected bar")
        if (
            latest.symbol != "QQQ"
            or latest.market != "US"
            or latest.timeframe is not Timeframe.D1
            or not latest.complete
        ):
            raise ValueError("KIS daily relative-regime replay decision bar is invalid")
        strength = Decimal("1") if action != "hold" else Decimal("0")
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=strength,
            reason=self.reason,
            timeframe=Timeframe.D1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=self.model_id,
            model_version="1.0.0",
            symbol=signal.symbol,
            market=signal.market,
            signal=signal,
            confidence=strength,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={"rule_id": KIS_DAILY_RELATIVE_REGIME_RULE_ID},
        )


@dataclass(slots=True)
class _InMemoryEmergencyStore:
    state: EmergencyState

    def read(self) -> EmergencyState:
        return self.state

    def write(self, state: EmergencyState) -> EmergencyState:
        self.state = state
        return state


def load_current_kis_daily_relative_regime_input(
    *,
    cache_root: Path | str = KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    repository_root: Path | str | None = None,
) -> KisDailyRelativeRegimeInput:
    """Re-attest the exact QQQ/SPY D1 cache before exposing phase-local bars."""

    catalog = load_kis_paper_private_daily_catalog(
        cache_root=cache_root,
        target_keys=HISTORICAL_KIS_DAILY_TARGET_KEYS,
        expected_index_hash=_EXPECTED_CATALOG_INDEX_HASH,
        expected_full_dataset_hash=_EXPECTED_CATALOG_DATASET_HASH,
        repo_root=repository_root,
    )
    return build_kis_daily_relative_regime_input(catalog)


def build_kis_daily_relative_regime_input(
    catalog: KisPaperPrivateDailyCatalog,
) -> KisDailyRelativeRegimeInput:
    """Build the frozen two-asset split without exposing cross-phase features."""

    _validate_full_catalog(catalog)
    split = KisDailyRelativeRegimeSplit()
    development_catalog = slice_kis_paper_private_daily_catalog(
        catalog,
        start_index=0,
        stop_index=split.development_session_count,
    )
    validation_catalog = slice_kis_paper_private_daily_catalog(
        catalog,
        start_index=split.validation_start_index,
        stop_index=split.total_session_count,
    )
    return KisDailyRelativeRegimeInput(
        catalog=catalog,
        split=split,
        development_catalog=development_catalog,
        validation_catalog=validation_catalog,
        development_decision_indices=_phase_decision_indices(development_catalog),
        validation_decision_indices=_phase_decision_indices(validation_catalog),
    )


def qqq_spy_relative_regime_should_enter(
    *,
    qqq_completed_bars: Sequence[Bar],
    spy_completed_bars: Sequence[Bar],
) -> bool:
    """Apply the fixed causal QQQ-versus-SPY close-comparison at one close."""

    qqq_window = tuple(qqq_completed_bars)
    spy_window = tuple(spy_completed_bars)
    required_count = KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS + 1
    if len(qqq_window) != required_count or len(spy_window) != required_count:
        raise ValueError("KIS daily relative-regime requires exactly 64 completed D1 bars")
    _validate_relative_windows(qqq_window=qqq_window, spy_window=spy_window)
    qqq_change = qqq_window[-1].close / qqq_window[0].close - Decimal("1")
    spy_change = spy_window[-1].close / spy_window[0].close - Decimal("1")
    return qqq_change > spy_change


def classify_kis_daily_relative_regime_outcome(
    *,
    mode: RelativeRegimeMode,
    candidate: KisDailyRelativeRegimeReplayMetrics,
    always_long: KisDailyRelativeRegimeReplayMetrics,
    flat: KisDailyRelativeRegimeReplayMetrics,
) -> RelativeRegimeOutcome:
    """Apply the frozen strict kill rule without selecting or promoting a model."""

    if mode == "cpu-smoke":
        return "operational_smoke"
    if mode != "cpu-full":
        raise ValueError("KIS daily relative-regime mode is invalid")
    if (
        candidate.trade_count == 0
        or candidate.after_cost_pnl <= always_long.after_cost_pnl
        or candidate.after_cost_pnl <= flat.after_cost_pnl
    ):
        return "falsified"
    return "candidate_only"


def run_kis_daily_relative_regime_control(
    control_input: KisDailyRelativeRegimeInput,
    *,
    mode: RelativeRegimeMode,
    artifact_root: Path | str = DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT,
    run_label: str,
    repository_root: Path | str | None = None,
) -> KisDailyRelativeRegimeControlRun:
    """Run one deterministic, aggregate-only, local-paper CPU control."""

    if mode not in {"cpu-smoke", "cpu-full"}:
        raise ValueError("KIS daily relative-regime mode is invalid")
    _validate_run_label(run_label)
    repository = _repository_root(repository_root)
    selected_indices = _selected_validation_indices(control_input, mode=mode)
    precommit_payload = _precommit_payload(
        control_input=control_input,
        mode=mode,
        selected_indices=selected_indices,
    )
    precommit_hash = _sha256_json(precommit_payload)
    output_dir = _create_external_output_dir(
        artifact_root=artifact_root,
        repository_root=repository,
        precommit_hash=precommit_hash,
        run_label=run_label,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, {**precommit_payload, "precommit_hash": precommit_hash})

    try:
        candidate = _run_validation_replay(
            control_input=control_input,
            decision_indices=selected_indices,
            role="candidate",
            precommit_hash=precommit_hash,
        )
        always_long = _run_validation_replay(
            control_input=control_input,
            decision_indices=selected_indices,
            role="always_long",
            precommit_hash=precommit_hash,
        )
        flat = _run_validation_replay(
            control_input=control_input,
            decision_indices=selected_indices,
            role="flat",
            precommit_hash=precommit_hash,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "kind": KIS_DAILY_RELATIVE_REGIME_CONTROL_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "artifact_policy": _artifact_policy_payload(),
            },
        )
        raise

    outcome = classify_kis_daily_relative_regime_outcome(
        mode=mode,
        candidate=candidate,
        always_long=always_long,
        flat=flat,
    )
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            control_input=control_input,
            mode=mode,
            precommit_hash=precommit_hash,
            candidate=candidate,
            always_long=always_long,
            flat=flat,
            outcome=outcome,
        ),
    )
    return KisDailyRelativeRegimeControlRun(
        control_input=control_input,
        mode=mode,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        candidate=candidate,
        always_long=always_long,
        flat=flat,
        outcome=outcome,
    )


def _selected_validation_indices(
    control_input: KisDailyRelativeRegimeInput,
    *,
    mode: RelativeRegimeMode,
) -> tuple[int, ...]:
    indices = control_input.validation_decision_indices
    if mode == "cpu-full":
        return indices
    if mode == "cpu-smoke":
        smoke_indices = indices[:KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT]
        if len(smoke_indices) != KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT:
            raise ValueError("KIS daily relative-regime smoke has insufficient validation slots")
        return smoke_indices
    raise ValueError("KIS daily relative-regime mode is invalid")


def _run_validation_replay(
    *,
    control_input: KisDailyRelativeRegimeInput,
    decision_indices: tuple[int, ...],
    role: _ReplayRole,
    precommit_hash: str,
) -> KisDailyRelativeRegimeReplayMetrics:
    validation_catalog = control_input.validation_catalog
    qqq_bars = tuple(validation_catalog.bars_by_symbol["QQQ"].bars)
    spy_bars = tuple(validation_catalog.bars_by_symbol["SPY"].bars)
    actions, entry_signal_count = _replay_actions(
        qqq_bars=qqq_bars,
        spy_bars=spy_bars,
        decision_indices=decision_indices,
        role=role,
    )
    eligible_signal_starts = _eligible_signal_starts(
        bars=qqq_bars,
        decision_indices=decision_indices,
    )
    event_store = InMemoryCampaignEventStore()
    emergency_store = _InMemoryEmergencyStore(
        state=EmergencyState(
            stop_new_orders=False,
            cancel_open_orders_requested=False,
            reason=f"{KIS_DAILY_RELATIVE_REGIME_CONTROL_ID}-{role}-offline-replay",
            updated_at=qqq_bars[0].start_ts,
        )
    )
    with localcontext() as context:
        context.prec = KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        result = run_local_paper_validation(
            validation_catalog.bars_by_symbol["QQQ"],
            event_store=event_store,
            emergency_store=emergency_store,  # type: ignore[arg-type]
            model=_RelativeRegimeReplayModel(
                model_id=f"{KIS_DAILY_RELATIVE_REGIME_CONTROL_ID}-{role}",
                action_by_feature_end=actions,
                reason=f"{KIS_DAILY_RELATIVE_REGIME_RULE_ID}-{role}",
            ),
            config=ValidationConfig(
                run_id=f"{KIS_DAILY_RELATIVE_REGIME_CONTROL_ID}-{role}",
                starting_cash=KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
                quantity=KIS_DAILY_RELATIVE_REGIME_QUANTITY,
                fee_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
                slippage_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
            ),
            eligible_signal_starts=eligible_signal_starts,
        )
    return _metrics_from_in_memory_replay(
        result=result,
        event_store=event_store,
        decision_slot_count=len(decision_indices),
        entry_signal_count=entry_signal_count,
        role=role,
        precommit_hash=precommit_hash,
    )


def _replay_actions(
    *,
    qqq_bars: tuple[Bar, ...],
    spy_bars: tuple[Bar, ...],
    decision_indices: tuple[int, ...],
    role: _ReplayRole,
) -> tuple[Mapping[datetime, str], int]:
    actions: dict[datetime, str] = {}
    entry_signal_count = 0
    for index in decision_indices:
        qualifies = role == "always_long" or (
            role == "candidate"
            and qqq_spy_relative_regime_should_enter(
                qqq_completed_bars=qqq_bars[
                    index - KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS : index + 1
                ],
                spy_completed_bars=spy_bars[
                    index - KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS : index + 1
                ],
            )
        )
        actions[qqq_bars[index].end_ts] = "buy" if qualifies else "hold"
        actions[qqq_bars[index + 1].end_ts] = "sell" if qualifies else "hold"
        entry_signal_count += int(qualifies)
    return MappingProxyType(actions), entry_signal_count


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
        raise ValueError("KIS daily relative-regime decision cadence overlaps")
    return starts


def _metrics_from_in_memory_replay(
    *,
    result: ValidationResult,
    event_store: InMemoryCampaignEventStore,
    decision_slot_count: int,
    entry_signal_count: int,
    role: _ReplayRole,
    precommit_hash: str,
) -> KisDailyRelativeRegimeReplayMetrics:
    fill_events = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
    fill_sources = tuple(event.payload.get("source") for event in fill_events)
    replayed_account = replay_local_paper_account(  # type: ignore[arg-type]
        event_store,
        starting_cash=KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
    )
    replayed_position = replayed_account.quantity(market="US", symbol="QQQ")
    expected_decisions = decision_slot_count * 2
    if (
        result.decisions_seen != expected_decisions
        or result.final_position != Decimal("0")
        or len(result.trades) != entry_signal_count * 2
        or len(fill_events) != len(result.trades)
        or any(source != "local_paper" for source in fill_sources)
        or replayed_account.cash != result.ending_cash
        or replayed_position != result.final_position
    ):
        raise RuntimeError("KIS daily relative-regime local-paper replay invariants failed")
    replay_identity_hash = _sha256_json(
        {
            "precommit_hash": precommit_hash,
            "role": role,
            "decision_slot_count": decision_slot_count,
            "entry_signal_count": entry_signal_count,
            "trade_count": len(result.trades) // 2,
            "local_paper_fill_count": len(fill_events),
            "after_cost_pnl": str(result.after_cost_pnl),
            "gross_pnl": str(result.gross_pnl),
            "total_fees": str(result.total_fees),
            "total_slippage": str(result.total_slippage),
        }
    )
    return KisDailyRelativeRegimeReplayMetrics(
        role=role,
        decision_slot_count=decision_slot_count,
        entry_signal_count=entry_signal_count,
        trade_count=len(result.trades) // 2,
        local_paper_fill_count=len(fill_events),
        after_cost_pnl=result.after_cost_pnl,
        gross_pnl=result.gross_pnl,
        total_fees=result.total_fees,
        total_slippage=result.total_slippage,
        fill_source="local_paper",
        all_fills_local_paper=True,
        replayable=True,
        final_position=result.final_position,
        replay_identity_hash=replay_identity_hash,
    )


def _precommit_payload(
    *,
    control_input: KisDailyRelativeRegimeInput,
    mode: RelativeRegimeMode,
    selected_indices: tuple[int, ...],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_RELATIVE_REGIME_CONTROL_ID,
        "status": "precommitted",
        "mode": mode,
        "source": {
            "dataset_id": control_input.catalog.dataset_id,
            "dataset_hash": control_input.catalog.dataset_hash,
            "index_hash": control_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_RELATIVE_REGIME_SYMBOLS),
            "completed_d1_session_count": len(control_input.catalog.common_sessions),
            "adjustment_mode": control_input.catalog.adjustment_mode,
            "limitations": list(control_input.catalog.raw_price_limitations),
            "source_mixing_allowed": False,
        },
        "split": control_input.split.to_payload(),
        "rule": {
            "rule_id": KIS_DAILY_RELATIVE_REGIME_RULE_ID,
            "completed_d1_only": True,
            "lookback_sessions": KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS,
            "entry_condition": "qqq_change_over_lookback_strictly_gt_spy",
            "decision": "completed_session_t_close",
            "entry": "t_plus_1_open",
            "exit": "t_plus_2_open",
            "non_overlapping_decision_stride_sessions": (
                KIS_DAILY_RELATIVE_REGIME_DECISION_STRIDE_SESSIONS
            ),
        },
        "validation": {
            "phase_local_eligible_slot_count": len(
                control_input.validation_decision_indices
            ),
            "evaluated_slot_count": len(selected_indices),
            "smoke_slot_cap": (
                KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT
                if mode == "cpu-smoke"
                else None
            ),
            "tuning_allowed": False,
        },
        "execution": {
            "fill_source": "local_paper",
            "quantity": str(KIS_DAILY_RELATIVE_REGIME_QUANTITY),
            "starting_cash": str(KIS_DAILY_RELATIVE_REGIME_STARTING_CASH),
            "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
            "slippage_bps_per_fill": str(
                KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL
            ),
            "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
            "decimal_precision": KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
        },
        "comparators": ["always_long", "flat"],
        "kill_rule": {
            "full_run_falsified_when_zero_trades": True,
            "full_run_requires_strict_after_cost_win_over_each_comparator": True,
        },
        "scope": {
            "training_used": False,
            "gpu_used": False,
            "model_selection_eligible": False,
            "ensemble_eligible": False,
            "promotion_eligible": False,
            "kis_paper_eligible": False,
            "paper_order_eligible": False,
        },
        "artifact_policy": _artifact_policy_payload(),
    }


def _summary_payload(
    *,
    control_input: KisDailyRelativeRegimeInput,
    mode: RelativeRegimeMode,
    precommit_hash: str,
    candidate: KisDailyRelativeRegimeReplayMetrics,
    always_long: KisDailyRelativeRegimeReplayMetrics,
    flat: KisDailyRelativeRegimeReplayMetrics,
    outcome: RelativeRegimeOutcome,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_RELATIVE_REGIME_CONTROL_ID,
        "status": "complete",
        "mode": mode,
        "precommit_hash": precommit_hash,
        "outcome": outcome,
        "source": {
            "dataset_id": control_input.catalog.dataset_id,
            "dataset_hash": control_input.catalog.dataset_hash,
            "index_hash": control_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_RELATIVE_REGIME_SYMBOLS),
            "completed_d1_session_count": len(control_input.catalog.common_sessions),
            "adjustment_mode": control_input.catalog.adjustment_mode,
            "limitations": list(control_input.catalog.raw_price_limitations),
        },
        "split": control_input.split.to_payload(),
        "validation": {
            "phase_local_eligible_slot_count": len(
                control_input.validation_decision_indices
            ),
            "evaluated_slot_count": candidate.decision_slot_count,
            "candidate": candidate.to_payload(),
            "time_matched_always_long": always_long.to_payload(),
            "time_matched_flat": flat.to_payload(),
        },
        "scope": {
            "candidate_only": outcome == "candidate_only",
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "gpu_used": False,
            "local_paper_only": True,
        },
        "artifact_policy": _artifact_policy_payload(),
    }


def _artifact_policy_payload() -> dict[str, bool]:
    return {
        "external_artifacts_only": True,
        "raw_market_data_persisted": False,
        "feature_values_persisted": False,
        "derived_values_persisted": False,
        "per_decision_values_persisted": False,
        "prices_persisted": False,
        "event_logs_persisted": False,
        "sqlite_persisted": False,
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


def _validate_full_catalog(catalog: KisPaperPrivateDailyCatalog) -> None:
    if not isinstance(catalog, KisPaperPrivateDailyCatalog):
        raise TypeError("KIS daily relative-regime control requires the Data-owned catalog")
    if (
        catalog.dataset_id != KIS_PAPER_PRIVATE_DAILY_CATALOG_ID
        or tuple(catalog.bars_by_symbol) != KIS_DAILY_RELATIVE_REGIME_SYMBOLS
        or catalog.adjustment_mode != KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE
        or len(catalog.common_sessions) != KIS_DAILY_RELATIVE_REGIME_TOTAL_SESSIONS
        or not _is_sha256(catalog.dataset_hash)
        or not _is_sha256(catalog.index_hash)
        or not catalog.raw_price_limitations
    ):
        raise ValueError("KIS daily relative-regime source contract is invalid")
    _validate_phase_catalog(
        catalog,
        expected_count=KIS_DAILY_RELATIVE_REGIME_TOTAL_SESSIONS,
    )


def _validate_phase_catalog(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    expected_count: int,
) -> None:
    qqq_bars = tuple(catalog.bars_by_symbol["QQQ"].bars)
    spy_bars = tuple(catalog.bars_by_symbol["SPY"].bars)
    if (
        len(catalog.common_sessions) != expected_count
        or len(qqq_bars) != expected_count
        or len(spy_bars) != expected_count
        or catalog.bars_by_symbol["QQQ"].dataset_id != catalog.dataset_id
        or catalog.bars_by_symbol["SPY"].dataset_id != catalog.dataset_id
        or catalog.bars_by_symbol["QQQ"].dataset_hash != catalog.dataset_hash
        or catalog.bars_by_symbol["SPY"].dataset_hash != catalog.dataset_hash
        or catalog.bars_by_symbol["QQQ"].source_path != catalog.index_path
        or catalog.bars_by_symbol["SPY"].source_path != catalog.index_path
        or any(
            bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.close <= 0
            for symbol, bars in (("QQQ", qqq_bars), ("SPY", spy_bars))
            for bar in bars
        )
        or any(
            qqq.start_ts != spy.start_ts
            or qqq.end_ts != spy.end_ts
            or qqq.start_ts.date() != session
            or spy.start_ts.date() != session
            for qqq, spy, session in zip(
                qqq_bars,
                spy_bars,
                catalog.common_sessions,
                strict=True,
            )
        )
        or any(
            later.start_ts <= earlier.start_ts
            for bars in (qqq_bars, spy_bars)
            for earlier, later in zip(bars, bars[1:], strict=False)
        )
    ):
        raise ValueError("KIS daily relative-regime source streams are incompatible")


def _phase_decision_indices(catalog: KisPaperPrivateDailyCatalog) -> tuple[int, ...]:
    qqq_bars = tuple(catalog.bars_by_symbol["QQQ"].bars)
    last_exclusive = len(qqq_bars) - 2
    indices = tuple(
        range(
            KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS,
            last_exclusive,
            KIS_DAILY_RELATIVE_REGIME_DECISION_STRIDE_SESSIONS,
        )
    )
    if not indices or any(
        index < KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS
        or index + 2 >= len(qqq_bars)
        for index in indices
    ):
        raise ValueError("KIS daily relative-regime phase has no valid decision slots")
    if any(
        later - earlier != KIS_DAILY_RELATIVE_REGIME_DECISION_STRIDE_SESSIONS
        for earlier, later in zip(indices, indices[1:], strict=False)
    ):
        raise ValueError("KIS daily relative-regime decision cadence is invalid")
    return indices


def _validate_relative_windows(
    *,
    qqq_window: tuple[Bar, ...],
    spy_window: tuple[Bar, ...],
) -> None:
    if any(
        qqq.symbol != "QQQ"
        or spy.symbol != "SPY"
        or qqq.market != "US"
        or spy.market != "US"
        or qqq.timeframe is not Timeframe.D1
        or spy.timeframe is not Timeframe.D1
        or not qqq.complete
        or not spy.complete
        or qqq.start_ts != spy.start_ts
        or qqq.end_ts != spy.end_ts
        or qqq.close <= 0
        or spy.close <= 0
        for qqq, spy in zip(qqq_window, spy_window, strict=True)
    ) or any(
        later.start_ts <= earlier.start_ts
        for bars in (qqq_window, spy_window)
        for earlier, later in zip(bars, bars[1:], strict=False)
    ):
        raise ValueError("KIS daily relative-regime feature window is invalid")


def _create_external_output_dir(
    *,
    artifact_root: Path | str,
    repository_root: Path,
    precommit_hash: str,
    run_label: str,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("KIS daily relative-regime artifact root is invalid")
    resolved_root = root.resolve()
    if _path_contains(repository_root, resolved_root):
        raise ValueError("KIS daily relative-regime artifacts must stay outside Git")
    content_root = (
        resolved_root
        / KIS_DAILY_RELATIVE_REGIME_CONTROL_ID
        / precommit_hash.removeprefix("sha256:")[:20]
    ).resolve()
    if not _path_contains(resolved_root, content_root):
        raise ValueError("KIS daily relative-regime artifact path escapes its root")
    output_dir = (content_root / run_label).resolve()
    if not _path_contains(content_root, output_dir):
        raise ValueError("KIS daily relative-regime artifact path escapes its content root")
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("KIS daily relative-regime run label already exists")
    return output_dir


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    _reject_raw_artifact_fields(payload)
    if path.exists() or path.is_symlink():
        raise FileExistsError("KIS daily relative-regime artifact already exists")
    encoded = _json_bytes(payload)
    staging = path.with_name(f".{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _reject_raw_artifact_fields(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "eventjsonl",
        "eventlog",
        "sourcepath",
        "statesqlite",
        "workdir",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in forbidden:
                raise ValueError("KIS daily relative-regime artifact contains raw market fields")
            _reject_raw_artifact_fields(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _reject_raw_artifact_fields(nested)


def _repository_root(repository_root: Path | str | None) -> Path:
    root = Path(repository_root) if repository_root is not None else Path.cwd()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("KIS daily relative-regime repository root is invalid")
    return root.resolve()


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("KIS daily relative-regime run label is invalid")


def _path_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


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
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

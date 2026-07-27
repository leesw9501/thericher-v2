"""Frozen QQQ/SPY D1 relative-allocation falsification control.

This is a separate two-ETF opportunity-selection test.  It reuses the
hash-attested, phase-local QQQ/SPY input from the closed relative-regime
control, but tests a different economic target: hold one selected ETF for one
next-open-to-next-open slot.  All local-paper events stay in memory and only
aggregate, source-safe receipts are written outside Git.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, EmergencyState, OrderIntent
from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    LocalPaperBroker,
    replay_local_paper_account,
)
from thericher_v2.kis_daily_joint_event_d1_target_cost import (
    KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
    KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
)

from .kis_daily_relative_regime_control import (
    DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT,
    KIS_DAILY_RELATIVE_REGIME_DECISION_STRIDE_SESSIONS,
    KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS,
    KIS_DAILY_RELATIVE_REGIME_QUANTITY,
    KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT,
    KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
    KIS_DAILY_RELATIVE_REGIME_SYMBOLS,
    KisDailyRelativeRegimeInput,
    RelativeRegimeMode,
    qqq_spy_relative_regime_should_enter,
)
from .validation import InMemoryCampaignEventStore

KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID = "kis-daily-relative-allocation-control-v1"
KIS_DAILY_RELATIVE_ALLOCATION_RULE_ID = "qqq-spy-d1-relative-allocation-63-v1"

RelativeAllocationOutcome = Literal["operational_smoke", "falsified", "candidate_only"]
_AllocationRole = Literal["candidate", "always_qqq", "always_spy", "flat"]
_SelectedSymbol = Literal["QQQ", "SPY"]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)


@dataclass(frozen=True, slots=True)
class KisDailyRelativeAllocationReplayMetrics:
    """Aggregate one-account local-paper evidence without any source values."""

    role: _AllocationRole
    decision_slot_count: int
    qqq_selection_count: int
    spy_selection_count: int
    trade_count: int
    local_paper_fill_count: int
    after_cost_pnl: Decimal
    gross_pnl: Decimal
    total_fees: Decimal
    total_slippage: Decimal
    fill_source: str
    all_fills_local_paper: bool
    replayable: bool
    flat_between_slots: bool
    final_position_count: int
    replay_identity_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        selected_count = self.qqq_selection_count + self.spy_selection_count
        if (
            self.role not in {"candidate", "always_qqq", "always_spy", "flat"}
            or self.decision_slot_count <= 0
            or self.qqq_selection_count < 0
            or self.spy_selection_count < 0
            or self.trade_count != selected_count
            or self.local_paper_fill_count != self.trade_count * 2
            or self.fill_source != LOCAL_PAPER_SOURCE
            or not self.all_fills_local_paper
            or not self.replayable
            or not self.flat_between_slots
            or self.final_position_count != 0
            or not _is_sha256(self.replay_identity_hash)
            or self.schema_version != SCHEMA_VERSION
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
            raise ValueError("KIS daily relative-allocation replay metrics are invalid")
        if self.role == "candidate" and selected_count != self.decision_slot_count:
            raise ValueError("KIS daily relative-allocation candidate must select one ETF")
        if self.role == "always_qqq" and (
            self.qqq_selection_count != self.decision_slot_count or self.spy_selection_count
        ):
            raise ValueError("KIS daily relative-allocation QQQ baseline is invalid")
        if self.role == "always_spy" and (
            self.spy_selection_count != self.decision_slot_count or self.qqq_selection_count
        ):
            raise ValueError("KIS daily relative-allocation SPY baseline is invalid")
        if self.role == "flat" and selected_count:
            raise ValueError("KIS daily relative-allocation flat baseline must stay flat")

    def to_payload(self) -> dict[str, object]:
        return {
            "role": self.role,
            "decision_slot_count": self.decision_slot_count,
            "qqq_selection_count": self.qqq_selection_count,
            "spy_selection_count": self.spy_selection_count,
            "trade_count": self.trade_count,
            "local_paper_fill_count": self.local_paper_fill_count,
            "after_cost_pnl": str(self.after_cost_pnl),
            "gross_pnl": str(self.gross_pnl),
            "total_fees": str(self.total_fees),
            "total_slippage": str(self.total_slippage),
            "fill_source": self.fill_source,
            "all_fills_local_paper": self.all_fills_local_paper,
            "replayable": self.replayable,
            "flat_between_slots": self.flat_between_slots,
            "final_position_count": self.final_position_count,
            "replay_identity_hash": self.replay_identity_hash,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class KisDailyRelativeAllocationControlRun:
    """One immutable CPU-only allocation result, never a promotion decision."""

    control_input: KisDailyRelativeRegimeInput
    mode: RelativeRegimeMode
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    candidate: KisDailyRelativeAllocationReplayMetrics
    always_qqq: KisDailyRelativeAllocationReplayMetrics
    always_spy: KisDailyRelativeAllocationReplayMetrics
    flat: KisDailyRelativeAllocationReplayMetrics
    outcome: RelativeAllocationOutcome

    def __post_init__(self) -> None:
        if (
            self.mode not in {"cpu-smoke", "cpu-full"}
            or not self.precommit_path.is_file()
            or not self.summary_path.is_file()
            or not _is_sha256(self.precommit_hash)
            or self.candidate.role != "candidate"
            or self.always_qqq.role != "always_qqq"
            or self.always_spy.role != "always_spy"
            or self.flat.role != "flat"
            or len(
                {
                    self.candidate.decision_slot_count,
                    self.always_qqq.decision_slot_count,
                    self.always_spy.decision_slot_count,
                    self.flat.decision_slot_count,
                }
            )
            != 1
            or self.outcome
            != classify_kis_daily_relative_allocation_outcome(
                mode=self.mode,
                candidate=self.candidate,
                always_qqq=self.always_qqq,
                always_spy=self.always_spy,
                flat=self.flat,
            )
        ):
            raise ValueError("KIS daily relative-allocation control result is invalid")


@dataclass(slots=True)
class _InMemoryEmergencyStore:
    state: EmergencyState

    def read(self) -> EmergencyState:
        return self.state

    def write(self, state: EmergencyState) -> EmergencyState:
        self.state = state
        return state


def qqq_spy_relative_allocation_symbol(
    *,
    qqq_completed_bars: Sequence[Bar],
    spy_completed_bars: Sequence[Bar],
) -> _SelectedSymbol:
    """Select QQQ only on a strict relative win; ties deliberately select SPY."""

    return (
        "QQQ"
        if qqq_spy_relative_regime_should_enter(
            qqq_completed_bars=qqq_completed_bars,
            spy_completed_bars=spy_completed_bars,
        )
        else "SPY"
    )


def classify_kis_daily_relative_allocation_outcome(
    *,
    mode: RelativeRegimeMode,
    candidate: KisDailyRelativeAllocationReplayMetrics,
    always_qqq: KisDailyRelativeAllocationReplayMetrics,
    always_spy: KisDailyRelativeAllocationReplayMetrics,
    flat: KisDailyRelativeAllocationReplayMetrics,
) -> RelativeAllocationOutcome:
    """Use the precommitted strict three-comparator kill rule."""

    if mode == "cpu-smoke":
        return "operational_smoke"
    if mode != "cpu-full":
        raise ValueError("KIS daily relative-allocation mode is invalid")
    if any(
        candidate.after_cost_pnl <= comparator.after_cost_pnl
        for comparator in (always_qqq, always_spy, flat)
    ):
        return "falsified"
    return "candidate_only"


def run_kis_daily_relative_allocation_control(
    control_input: KisDailyRelativeRegimeInput,
    *,
    mode: RelativeRegimeMode,
    artifact_root: Path | str = DEFAULT_KIS_DAILY_RELATIVE_REGIME_ARTIFACT_ROOT,
    run_label: str,
    repository_root: Path | str | None = None,
) -> KisDailyRelativeAllocationControlRun:
    """Replay one fixed allocation rule through a single in-memory account."""

    if not isinstance(control_input, KisDailyRelativeRegimeInput):
        raise TypeError("KIS daily relative-allocation requires the phase-local input")
    if mode not in {"cpu-smoke", "cpu-full"}:
        raise ValueError("KIS daily relative-allocation mode is invalid")
    _validate_run_label(run_label)
    repository = _repository_root(repository_root)
    decision_indices = _selected_validation_indices(control_input, mode=mode)
    precommit_payload = _precommit_payload(
        control_input=control_input,
        mode=mode,
        decision_indices=decision_indices,
    )
    precommit_hash = _sha256_json(precommit_payload)
    output_dir = _create_output_dir(
        artifact_root=artifact_root,
        repository_root=repository,
        precommit_hash=precommit_hash,
        run_label=run_label,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, {**precommit_payload, "precommit_hash": precommit_hash})

    try:
        candidate = _run_allocation_replay(
            control_input=control_input,
            decision_indices=decision_indices,
            role="candidate",
            precommit_hash=precommit_hash,
        )
        always_qqq = _run_allocation_replay(
            control_input=control_input,
            decision_indices=decision_indices,
            role="always_qqq",
            precommit_hash=precommit_hash,
        )
        always_spy = _run_allocation_replay(
            control_input=control_input,
            decision_indices=decision_indices,
            role="always_spy",
            precommit_hash=precommit_hash,
        )
        flat = _run_allocation_replay(
            control_input=control_input,
            decision_indices=decision_indices,
            role="flat",
            precommit_hash=precommit_hash,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "kind": KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "artifact_policy": _artifact_policy_payload(),
            },
        )
        raise

    outcome = classify_kis_daily_relative_allocation_outcome(
        mode=mode,
        candidate=candidate,
        always_qqq=always_qqq,
        always_spy=always_spy,
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
            always_qqq=always_qqq,
            always_spy=always_spy,
            flat=flat,
            outcome=outcome,
        ),
    )
    return KisDailyRelativeAllocationControlRun(
        control_input=control_input,
        mode=mode,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        candidate=candidate,
        always_qqq=always_qqq,
        always_spy=always_spy,
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
        selected = indices[:KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT]
        if len(selected) != KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT:
            raise ValueError("KIS daily relative-allocation smoke has insufficient slots")
        return selected
    raise ValueError("KIS daily relative-allocation mode is invalid")


def _run_allocation_replay(
    *,
    control_input: KisDailyRelativeRegimeInput,
    decision_indices: tuple[int, ...],
    role: _AllocationRole,
    precommit_hash: str,
) -> KisDailyRelativeAllocationReplayMetrics:
    qqq_bars = tuple(control_input.validation_catalog.bars_by_symbol["QQQ"].bars)
    spy_bars = tuple(control_input.validation_catalog.bars_by_symbol["SPY"].bars)
    event_store = InMemoryCampaignEventStore()
    broker = LocalPaperBroker(
        event_store=event_store,  # type: ignore[arg-type]
        emergency_store=_InMemoryEmergencyStore(
            state=EmergencyState(
                stop_new_orders=False,
                cancel_open_orders_requested=False,
                reason=f"{KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID}-{role}-offline-replay",
                updated_at=qqq_bars[0].start_ts,
            )
        ),  # type: ignore[arg-type]
        starting_cash=KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
        fee_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL,
        slippage_bps=KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL,
    )
    qqq_selection_count = 0
    spy_selection_count = 0
    total_fees = Decimal("0")
    total_slippage = Decimal("0")
    flat_between_slots = True

    with localcontext() as context:
        context.prec = KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        for slot_number, index in enumerate(decision_indices, start=1):
            selected_symbol = _selected_symbol(
                role=role,
                qqq_bars=qqq_bars,
                spy_bars=spy_bars,
                index=index,
            )
            if selected_symbol is None:
                continue
            selected_bars = qqq_bars if selected_symbol == "QQQ" else spy_bars
            signal_bar = selected_bars[index]
            entry_bar = selected_bars[index + 1]
            exit_bar = selected_bars[index + 2]
            decision_id = f"{KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID}-{role}-{slot_number:04d}"
            entry_order = OrderIntent(
                client_order_id=f"{decision_id}-entry",
                symbol=selected_symbol,
                market="US",
                side="buy",
                quantity=KIS_DAILY_RELATIVE_REGIME_QUANTITY,
                limit_price=None,
                decision_id=decision_id,
                created_at=signal_bar.end_ts,
            )
            entry = broker.submit_and_fill_next_bar(
                entry_order,
                signal_bar=signal_bar,
                execution_bar=entry_bar,
            )
            if entry.fill is None:
                raise RuntimeError("KIS daily relative-allocation entry did not fill")
            total_fees += entry.fill.fee
            total_slippage += _slippage_cost(
                fill_price=entry.fill.price,
                reference_open=entry_bar.open,
                quantity=entry.fill.quantity,
                side="buy",
            )
            exit_order = OrderIntent(
                client_order_id=f"{decision_id}-exit",
                symbol=selected_symbol,
                market="US",
                side="sell",
                quantity=entry.fill.quantity,
                limit_price=None,
                decision_id=f"{decision_id}:flatten",
                created_at=entry_bar.end_ts,
            )
            exit_execution = broker.submit_and_fill_next_bar(
                exit_order,
                signal_bar=entry_bar,
                execution_bar=exit_bar,
            )
            if exit_execution.fill is None:
                raise RuntimeError("KIS daily relative-allocation exit did not fill")
            total_fees += exit_execution.fill.fee
            total_slippage += _slippage_cost(
                fill_price=exit_execution.fill.price,
                reference_open=exit_bar.open,
                quantity=exit_execution.fill.quantity,
                side="sell",
            )
            if broker.account().positions:
                flat_between_slots = False
                raise RuntimeError("KIS daily relative-allocation account did not flatten")
            if selected_symbol == "QQQ":
                qqq_selection_count += 1
            else:
                spy_selection_count += 1

    account = broker.account()
    replayed_account = replay_local_paper_account(  # type: ignore[arg-type]
        event_store,
        starting_cash=KIS_DAILY_RELATIVE_REGIME_STARTING_CASH,
    )
    fill_events = tuple(event for event in event_store.iter_events() if event.event_type == "fill")
    all_local = all(event.payload.get("source") == LOCAL_PAPER_SOURCE for event in fill_events)
    trade_count = qqq_selection_count + spy_selection_count
    if (
        account != replayed_account
        or account.positions
        or len(fill_events) != trade_count * 2
        or not all_local
    ):
        raise RuntimeError("KIS daily relative-allocation replay invariants failed")
    after_cost_pnl = account.cash - KIS_DAILY_RELATIVE_REGIME_STARTING_CASH
    replay_identity_hash = _sha256_json(
        {
            "precommit_hash": precommit_hash,
            "role": role,
            "decision_slot_count": len(decision_indices),
            "qqq_selection_count": qqq_selection_count,
            "spy_selection_count": spy_selection_count,
            "trade_count": trade_count,
            "local_paper_fill_count": len(fill_events),
            "after_cost_pnl": str(after_cost_pnl),
            "total_fees": str(total_fees),
            "total_slippage": str(total_slippage),
        }
    )
    return KisDailyRelativeAllocationReplayMetrics(
        role=role,
        decision_slot_count=len(decision_indices),
        qqq_selection_count=qqq_selection_count,
        spy_selection_count=spy_selection_count,
        trade_count=trade_count,
        local_paper_fill_count=len(fill_events),
        after_cost_pnl=after_cost_pnl,
        gross_pnl=after_cost_pnl + total_fees + total_slippage,
        total_fees=total_fees,
        total_slippage=total_slippage,
        fill_source=LOCAL_PAPER_SOURCE,
        all_fills_local_paper=all_local,
        replayable=True,
        flat_between_slots=flat_between_slots,
        final_position_count=len(account.positions),
        replay_identity_hash=replay_identity_hash,
    )


def _selected_symbol(
    *,
    role: _AllocationRole,
    qqq_bars: tuple[Bar, ...],
    spy_bars: tuple[Bar, ...],
    index: int,
) -> _SelectedSymbol | None:
    if role == "always_qqq":
        return "QQQ"
    if role == "always_spy":
        return "SPY"
    if role == "flat":
        return None
    if role != "candidate":  # pragma: no cover - Literal input is checked by callers.
        raise ValueError("KIS daily relative-allocation role is invalid")
    start_index = index - KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS
    return qqq_spy_relative_allocation_symbol(
        qqq_completed_bars=qqq_bars[start_index : index + 1],
        spy_completed_bars=spy_bars[start_index : index + 1],
    )


def _slippage_cost(
    *,
    fill_price: Decimal,
    reference_open: Decimal,
    quantity: Decimal,
    side: Literal["buy", "sell"],
) -> Decimal:
    return (
        (fill_price - reference_open) * quantity
        if side == "buy"
        else (reference_open - fill_price) * quantity
    )


def _precommit_payload(
    *,
    control_input: KisDailyRelativeRegimeInput,
    mode: RelativeRegimeMode,
    decision_indices: tuple[int, ...],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID,
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
            "rule_id": KIS_DAILY_RELATIVE_ALLOCATION_RULE_ID,
            "completed_d1_only": True,
            "lookback_sessions": KIS_DAILY_RELATIVE_REGIME_LOOKBACK_SESSIONS,
            "qqq_condition": "qqq_change_over_lookback_strictly_gt_spy",
            "tie_selection": "spy",
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
            "evaluated_slot_count": len(decision_indices),
            "smoke_slot_cap": (
                KIS_DAILY_RELATIVE_REGIME_SMOKE_SLOT_COUNT
                if mode == "cpu-smoke"
                else None
            ),
            "tuning_allowed": False,
        },
        "execution": {
            "account_scope": "single_in_memory_local_paper_account",
            "fill_source": LOCAL_PAPER_SOURCE,
            "quantity": str(KIS_DAILY_RELATIVE_REGIME_QUANTITY),
            "starting_cash": str(KIS_DAILY_RELATIVE_REGIME_STARTING_CASH),
            "fee_bps_per_fill": str(KIS_DAILY_JOINT_EVENT_D1_TARGET_FEE_BPS_PER_FILL),
            "slippage_bps_per_fill": str(
                KIS_DAILY_JOINT_EVENT_D1_TARGET_SLIPPAGE_BPS_PER_FILL
            ),
            "rounding_mode": KIS_DAILY_JOINT_EVENT_D1_TARGET_ROUNDING_MODE,
            "decimal_precision": KIS_DAILY_JOINT_EVENT_D1_TARGET_DECIMAL_PRECISION,
        },
        "comparators": ["always_qqq", "always_spy", "flat"],
        "kill_rule": {
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
    candidate: KisDailyRelativeAllocationReplayMetrics,
    always_qqq: KisDailyRelativeAllocationReplayMetrics,
    always_spy: KisDailyRelativeAllocationReplayMetrics,
    flat: KisDailyRelativeAllocationReplayMetrics,
    outcome: RelativeAllocationOutcome,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID,
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
            "time_matched_always_qqq": always_qqq.to_payload(),
            "time_matched_always_spy": always_spy.to_payload(),
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


def _create_output_dir(
    *,
    artifact_root: Path | str,
    repository_root: Path,
    precommit_hash: str,
    run_label: str,
) -> Path:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("KIS daily relative-allocation artifact root is invalid")
    resolved_root = root.resolve()
    if _path_contains(repository_root, resolved_root):
        raise ValueError("KIS daily relative-allocation artifacts must stay outside Git")
    content_root = (
        resolved_root
        / KIS_DAILY_RELATIVE_ALLOCATION_CONTROL_ID
        / precommit_hash.removeprefix("sha256:")[:20]
    ).resolve()
    if not _path_contains(resolved_root, content_root):
        raise ValueError("KIS daily relative-allocation artifact path escapes its root")
    output_dir = (content_root / run_label).resolve()
    if not _path_contains(content_root, output_dir):
        raise ValueError("KIS daily relative-allocation artifact path escapes its content root")
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("KIS daily relative-allocation run label already exists")
    return output_dir


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    _reject_raw_artifact_fields(payload)
    if path.exists() or path.is_symlink():
        raise FileExistsError("KIS daily relative-allocation artifact already exists")
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
                raise ValueError("KIS daily relative-allocation artifact contains raw fields")
            _reject_raw_artifact_fields(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_raw_artifact_fields(nested)


def _repository_root(repository_root: Path | str | None) -> Path:
    root = Path(repository_root) if repository_root is not None else Path.cwd()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("KIS daily relative-allocation repository root is invalid")
    return root.resolve()


def _validate_run_label(run_label: str) -> None:
    if not isinstance(run_label, str) or _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("KIS daily relative-allocation run label is invalid")


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

"""Hermetic replay through the existing model-to-local-paper path.

This module intentionally accepts only caller-owned completed bars and an
already constructed local-paper broker.  It has no provider, credential, or
external-runtime dependency.  It is a narrow integration check, not a model
selection or backtest result surface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from thericher_v2.backtest.simple import run_next_bar_backtest
from thericher_v2.contracts import Bar, OrderIntent, Timeframe, require_utc
from thericher_v2.execution.local_paper import (
    LOCAL_PAPER_SOURCE,
    LocalPaperBroker,
    LocalPaperExecutionResult,
)
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    prepare_local_paper_intent,
)
from thericher_v2.models.momentum import MomentumModel
from thericher_v2.models.sequence_window import (
    CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID,
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    build_causal_multitimeframe_sequence_window,
)
from thericher_v2.models.target_position_policy import (
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    propose_target_exposure,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)

ReplayStatus = Literal["filled", "no_intent"]


@dataclass(frozen=True, slots=True)
class InjectedMultitimeframeLocalPaperReplayResult:
    """Source-safe facts from one caller-injected replay."""

    status: ReplayStatus
    reason: str
    timeframe_bar_counts: Mapping[Timeframe, int]
    prediction_count: int
    all_windows_available_at_cutoff: bool
    proposal_action: str
    proposal_input_status: str
    receipt_ref: str
    decision_identity_matches: bool
    local_paper_fill_source: str | None
    local_paper_replay_matches: bool
    fill_is_next_bar: bool
    backtest_trade_count: int
    backtest_next_bar_timing_valid: bool

    def __post_init__(self) -> None:
        counts = MappingProxyType(dict(self.timeframe_bar_counts))
        if (
            self.status not in {"filled", "no_intent"}
            or not self.reason
            or tuple(counts) != SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
            or any(count < 1 for count in counts.values())
            or self.prediction_count != len(SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES)
            or not self.all_windows_available_at_cutoff
            or self.proposal_action not in {"enter", "hold", "reduce", "exit", "abstain"}
            or self.proposal_input_status
            not in {
                "ready",
                "missing",
                "stale",
                "incomplete",
                "duplicate",
                "non_contiguous",
                "misaligned",
                "future",
                "unqualified",
            }
            or not self.receipt_ref.startswith("sha256:")
            or len(self.receipt_ref) != 71
        ):
            raise ValueError("injected replay result is invalid")
        if self.status == "filled":
            if (
                self.local_paper_fill_source != LOCAL_PAPER_SOURCE
                or not self.decision_identity_matches
                or not self.local_paper_replay_matches
                or not self.fill_is_next_bar
                or self.backtest_trade_count < 1
                or not self.backtest_next_bar_timing_valid
            ):
                raise ValueError("filled replay result is invalid")
        elif (
            self.local_paper_fill_source is not None
            or self.decision_identity_matches
            or self.local_paper_replay_matches
            or self.fill_is_next_bar
            or self.backtest_trade_count != 0
            or self.backtest_next_bar_timing_valid
        ):
            raise ValueError("no-intent replay result is invalid")
        object.__setattr__(self, "timeframe_bar_counts", counts)

    def safe_payload(self) -> dict[str, object]:
        """Return replay facts without bar values, raw times, paths, or account fields."""

        return {
            "schema_id": "injected-multitimeframe-local-paper-replay-seam-v1",
            "causal_sequence_schema_id": CAUSAL_SEQUENCE_WINDOW_SCHEMA_ID,
            "status": self.status,
            "reason": self.reason,
            "timeframe_bar_counts": {
                timeframe.value: count for timeframe, count in self.timeframe_bar_counts.items()
            },
            "prediction_count": self.prediction_count,
            "all_windows_available_at_cutoff": self.all_windows_available_at_cutoff,
            "proposal": {
                "action": self.proposal_action,
                "input_status": self.proposal_input_status,
                "receipt_ref": self.receipt_ref,
                "decision_identity_matches": self.decision_identity_matches,
            },
            "local_paper": {
                "fill_source": self.local_paper_fill_source,
                "replay_matches": self.local_paper_replay_matches,
                "fill_is_next_bar": self.fill_is_next_bar,
            },
            "backtest": {
                "trade_count": self.backtest_trade_count,
                "next_bar_timing_valid": self.backtest_next_bar_timing_valid,
            },
        }


def run_injected_multitimeframe_local_paper_replay(
    bars_by_timeframe: Mapping[Timeframe, Sequence[Bar]],
    *,
    lookbacks: Mapping[Timeframe, int],
    cutoff: datetime,
    momentum_model: MomentumModel,
    opportunity: OpportunityEligibility,
    policy_config: TargetPositionPolicyConfig,
    current_exposure: Decimal,
    receipt_references: DecisionReceiptReferences,
    local_binding: LocalPaperTargetBinding,
    local_paper_broker: LocalPaperBroker,
    execution_bar: Bar,
    backtest_bars: Sequence[Bar],
) -> InjectedMultitimeframeLocalPaperReplayResult:
    """Replay existing paths from injected bars without external data access."""

    if not isinstance(momentum_model, MomentumModel):
        raise TypeError("momentum_model must be a MomentumModel")
    if not isinstance(opportunity, OpportunityEligibility):
        raise TypeError("opportunity must be an OpportunityEligibility")
    if not isinstance(policy_config, TargetPositionPolicyConfig):
        raise TypeError("policy_config must be a TargetPositionPolicyConfig")
    if not isinstance(receipt_references, DecisionReceiptReferences):
        raise TypeError("receipt_references must be DecisionReceiptReferences")
    if not isinstance(local_binding, LocalPaperTargetBinding):
        raise TypeError("local_binding must be a LocalPaperTargetBinding")
    if not isinstance(local_paper_broker, LocalPaperBroker):
        raise TypeError("local_paper_broker must be a LocalPaperBroker")

    now = require_utc(cutoff, "cutoff")
    window = build_causal_multitimeframe_sequence_window(
        bars_by_timeframe,
        lookbacks=lookbacks,
        cutoff=now,
    )
    if tuple(policy_config.required_timeframes) != SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        raise ValueError("policy config must require every injected timeframe")
    if window.symbol != opportunity.symbol or window.market != opportunity.market:
        raise ValueError("opportunity and injected windows must share identity")
    if any(len(item.bars) <= momentum_model.lookback for item in window.windows.values()):
        raise ValueError("causal windows must exceed the momentum lookback")

    predictions = tuple(
        momentum_model.predict(list(window.windows[timeframe].bars))
        for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    )
    proposal = propose_target_exposure(
        opportunity,
        predictions,
        current_exposure=current_exposure,
        config=policy_config,
        as_of=now,
    )
    receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=receipt_references,
    )
    prepared = prepare_local_paper_intent(receipt, binding=local_binding, as_of=now)
    counts = {timeframe: len(window.windows[timeframe].bars) for timeframe in window.windows}
    all_windows_available = all(item.end_ts <= now for item in window.windows.values())
    if prepared.status != "ready" or prepared.local_paper_intent is None:
        return InjectedMultitimeframeLocalPaperReplayResult(
            status="no_intent",
            reason=prepared.reason,
            timeframe_bar_counts=counts,
            prediction_count=len(predictions),
            all_windows_available_at_cutoff=all_windows_available,
            proposal_action=proposal.action,
            proposal_input_status=proposal.input_status,
            receipt_ref=prepared.receipt_ref,
            decision_identity_matches=False,
            local_paper_fill_source=None,
            local_paper_replay_matches=False,
            fill_is_next_bar=False,
            backtest_trade_count=0,
            backtest_next_bar_timing_valid=False,
        )

    m1_source = tuple(bars_by_timeframe[Timeframe.M1])
    _validate_execution_inputs(
        m1_source=m1_source,
        execution_bar=execution_bar,
        backtest_bars=backtest_bars,
        window_symbol=window.symbol,
        window_market=window.market,
        cutoff=now,
    )
    if prepared.local_paper_intent.decision_id != receipt.decision_id:
        raise ValueError("local paper intent must preserve receipt decision identity")
    backtest = run_next_bar_backtest(list(backtest_bars), model=momentum_model)
    timing_valid = all(trade.signal_bar_end == trade.execution_ts for trade in backtest.trades)
    if not backtest.trades or not timing_valid:
        raise ValueError("backtest timing must be valid before local paper execution")
    signal_bar = window.windows[Timeframe.M1].bars[-1]
    execution = _fill_or_recover_local_paper(
        local_paper_broker,
        client_order_id=prepared.local_paper_intent.client_order_id,
        intent=prepared.local_paper_intent,
        signal_bar=signal_bar,
        execution_bar=execution_bar,
    )
    if execution.fill is None:
        raise ValueError("eligible local paper intent did not fill")
    replayed = local_paper_broker.fill_next_bar(
        prepared.local_paper_intent.client_order_id,
        signal_bar=signal_bar,
        execution_bar=execution_bar,
    )
    if replayed.fill is None:
        raise ValueError("recorded local paper fill did not replay")
    return InjectedMultitimeframeLocalPaperReplayResult(
        status="filled",
        reason=prepared.reason,
        timeframe_bar_counts=counts,
        prediction_count=len(predictions),
        all_windows_available_at_cutoff=all_windows_available,
        proposal_action=proposal.action,
        proposal_input_status=proposal.input_status,
        receipt_ref=prepared.receipt_ref,
        decision_identity_matches=True,
        local_paper_fill_source=execution.fill.source,
        local_paper_replay_matches=replayed.fill == execution.fill,
        fill_is_next_bar=execution.fill.filled_at == execution_bar.start_ts,
        backtest_trade_count=len(backtest.trades),
        backtest_next_bar_timing_valid=timing_valid,
    )


def _validate_execution_inputs(
    *,
    m1_source: tuple[Bar, ...],
    execution_bar: Bar,
    backtest_bars: Sequence[Bar],
    window_symbol: str,
    window_market: str,
    cutoff: datetime,
) -> None:
    if not m1_source or any(
        bar.timeframe is not Timeframe.M1
        or bar.symbol != window_symbol
        or bar.market != window_market
        or not bar.complete
        for bar in m1_source
    ):
        raise ValueError("injected 1m source bars are invalid")
    if (
        execution_bar.timeframe is not Timeframe.M1
        or execution_bar.symbol != window_symbol
        or execution_bar.market != window_market
        or not execution_bar.complete
        or execution_bar.start_ts != cutoff
        or m1_source[-1].end_ts != cutoff
    ):
        raise ValueError("execution bar must be the next completed 1m bar")
    candidate_backtest_bars = tuple(backtest_bars)
    if candidate_backtest_bars != (*m1_source, execution_bar):
        raise ValueError("backtest must use the injected 1m sequence plus its next bar")
    full_sequence = (*m1_source, execution_bar)
    if any(
        later.start_ts != earlier.end_ts
        for earlier, later in zip(full_sequence, full_sequence[1:], strict=False)
    ):
        raise ValueError("injected 1m sequence must be contiguous through execution")


def _fill_or_recover_local_paper(
    broker: LocalPaperBroker,
    *,
    client_order_id: str,
    intent: OrderIntent,
    signal_bar: Bar,
    execution_bar: Bar,
) -> LocalPaperExecutionResult:
    try:
        return broker.fill_next_bar(
            client_order_id,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )
    except ValueError as exc:
        if str(exc) != "client_order_id has no pending accepted local paper order":
            raise
    return broker.submit_and_fill_next_bar(
        intent,
        signal_bar=signal_bar,
        execution_bar=execution_bar,
    )

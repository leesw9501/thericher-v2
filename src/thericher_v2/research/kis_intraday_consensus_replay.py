"""Frozen offline replay for a small multi-timeframe consensus policy.

The replay deliberately has one fixed decision time and one fixed outcome
horizon.  It is a descriptive local-paper baseline, not a selector or a
promotion path.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import (
    Bar,
    EmergencyState,
    OrderIntent,
    TargetInputStatus,
    Timeframe,
)
from thericher_v2.data import CatalogedBars, SessionWindow
from thericher_v2.execution import LOCAL_PAPER_SOURCE, LocalPaperBroker, replay_local_paper_account
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    PaperDecisionBridgeResult,
    prepare_local_paper_intent,
)
from thericher_v2.models import (
    CurrentSourceContract,
    CurrentSourceMetadata,
    MultiTimeframeMomentumConfig,
    MultiTimeframeMomentumSpec,
    OpportunityEligibility,
    TargetPositionPolicyConfig,
    adapt_current_source_opportunity_eligibility,
    build_causal_bar_source_contract,
    build_multitimeframe_momentum_evidence,
    propose_target_exposure,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    ResearchDecisionReceipt,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.state import Event

from .kis_intraday_campaign import (
    KIS_INTRADAY_SESSION_COUNT,
    KisIntradayCpuCampaignPlan,
    build_kis_intraday_cpu_campaign_plan,
)

KIS_INTRADAY_CONSENSUS_REPLAY_ID = "kis-intraday-multitimeframe-consensus-replay-v2"
KIS_INTRADAY_CONSENSUS_SOURCE_CONTRACT_ID = "kis-private-intraday-consensus-v2"
KIS_INTRADAY_CONSENSUS_DECISION_OFFSET = timedelta(hours=6)
KIS_INTRADAY_CONSENSUS_HORIZON = timedelta(minutes=30)
KIS_INTRADAY_CONSENSUS_STARTING_CASH = Decimal("10000")
KIS_INTRADAY_CONSENSUS_QUANTITY = Decimal("1")
KIS_INTRADAY_CONSENSUS_MAXIMUM_QUANTITY = Decimal("10")
KIS_INTRADAY_CONSENSUS_FEE_BPS = Decimal("1")
KIS_INTRADAY_CONSENSUS_SLIPPAGE_BPS = Decimal("2")
KIS_INTRADAY_CONSENSUS_TIMEFRAMES = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M10,
    Timeframe.H1,
    Timeframe.H3,
)

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_CLEAR_EMERGENCY_STATE = EmergencyState(
    stop_new_orders=False,
    cancel_open_orders_requested=False,
    reason="offline_replay_clear",
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
)


@dataclass(frozen=True)
class ConsensusReplayStrategyTotals:
    """Aggregate-only local-paper outcome for one fixed replay strategy."""

    after_cost_pnl: Decimal
    round_trip_count: int
    fill_count: int
    max_drawdown: Decimal


@dataclass(frozen=True)
class KisIntradayConsensusReplayRun:
    """Source-safe result for one immutable external replay attempt."""

    run_label: str
    status: Literal["complete"]
    precommit_path: Path
    summary_path: Path
    session_count: int
    consensus: ConsensusReplayStrategyTotals
    always_long: ConsensusReplayStrategyTotals
    abstention_count: int
    decision_action_counts: tuple[tuple[str, int], ...]
    all_fills_local_paper: bool
    all_terminal_flat: bool
    replay_digest: str


@dataclass(frozen=True)
class KisIntradayConsensusSessionReplay:
    """One in-memory session outcome; no prices, fills, or features are exposed."""

    session_date: date
    proposal_action: str
    consensus: _TradeReplay
    always_long: _TradeReplay


@dataclass(frozen=True)
class _SessionDecision:
    session_date: date
    as_of: datetime
    proposal_action: str
    proposal_reason: str
    receipt: ResearchDecisionReceipt
    bridge: PaperDecisionBridgeResult
    signal_bar: Bar | None
    entry_bar: Bar | None
    exit_signal_bar: Bar | None
    exit_bar: Bar | None


@dataclass(frozen=True)
class _TradeReplay:
    after_cost_pnl: Decimal
    fill_count: int
    terminal_flat: bool
    all_fills_local_paper: bool
    replay_digest: str


class _InMemoryReplayEventStore:
    """Keep raw local-paper fill events replayable without retaining them as artifacts."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._next_seq = 1

    def append(self, event: Event) -> Event:
        recorded = event.with_seq(self._next_seq)
        self._next_seq += 1
        self._events.append(recorded)
        return recorded

    def iter_events(self) -> tuple[Event, ...]:
        return tuple(self._events)


class _ClearEmergencyStore:
    """The offline replay cannot inherit mutable process or broker emergency state."""

    def read(self) -> EmergencyState:
        return _CLEAR_EMERGENCY_STATE


def frozen_multitimeframe_momentum_config() -> MultiTimeframeMomentumConfig:
    """Return the exact five completed-bar experts predeclared for this replay."""

    return MultiTimeframeMomentumConfig(
        feature_schema_id="multitimeframe-momentum-ohlcv-v1",
        experts=(
            MultiTimeframeMomentumSpec(Timeframe.M1, 5, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.M5, 4, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.M10, 3, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.H1, 3, Decimal("1"), Decimal("-1")),
            MultiTimeframeMomentumSpec(Timeframe.H3, 1, Decimal("1"), Decimal("-1")),
        ),
    )


def frozen_target_position_policy_config() -> TargetPositionPolicyConfig:
    """Return the fixed consensus policy geometry without any tuned weights."""

    return TargetPositionPolicyConfig(
        policy_id="multitimeframe-momentum-consensus-replay-v2",
        feature_schema_id="multitimeframe-momentum-ohlcv-v1",
        required_timeframes=KIS_INTRADAY_CONSENSUS_TIMEFRAMES,
        maximum_evidence_age={
            Timeframe.M1: timedelta(minutes=2),
            Timeframe.M5: timedelta(minutes=10),
            Timeframe.M10: timedelta(minutes=20),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.H3: timedelta(hours=3),
        },
        minimum_confidence=Decimal("0.01"),
        minimum_absolute_edge_bps=Decimal("0.01"),
        entry_target_exposure=Decimal("0.10"),
        decision_ttl=timedelta(minutes=2),
    )


def predeclared_consensus_replay_candidate(
    *,
    symbol: str,
    market: str,
    session_date: date,
    as_of: datetime,
) -> OpportunityEligibility:
    """Return the explicit fixed-scope candidate used by a structural replay.

    This is intentionally a caller-invoked fixture, not a data-derived
    opportunity selector. A production selector must supply its own candidate
    factory to the replay entry point.
    """

    return OpportunityEligibility(
        opportunity_ref=_opaque_reference(
            "predeclared-consensus-candidate-v2",
            symbol,
            market,
            session_date.isoformat(),
            as_of.isoformat(),
        ),
        symbol=symbol,
        market=market,
        eligible=True,
        input_status="ready",
        observed_at=as_of,
        valid_until=as_of + timedelta(minutes=2),
    )


def run_kis_intraday_consensus_replay(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    upstream_candidate_factory: Callable[..., OpportunityEligibility],
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
) -> KisIntradayConsensusReplayRun:
    """Run one fixed 20-session model-to-local-paper replay with no external I/O.

    The selected source is the verified local KIS cache supplied by the caller.
    This function neither reads credentials nor calls KIS, a broker, or the
    network.  It writes only aggregate external evidence and an immutable
    precommit; raw bars and fill values stay in process memory.
    """

    _validate_run_label(run_label)
    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=tuple(session_dates),
        campaign_id=KIS_INTRADAY_CONSENSUS_REPLAY_ID,
    )
    if len(plan.session_dates) != KIS_INTRADAY_SESSION_COUNT:
        raise RuntimeError("consensus replay must retain exactly twenty sessions")

    root = Path(artifact_root).resolve()
    _reject_repo_artifact_root(root, repo_root or Path.cwd())
    output_dir = root / "research" / KIS_INTRADAY_CONSENSUS_REPLAY_ID / run_label
    if output_dir.exists():
        raise FileExistsError(f"consensus replay artifact already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_path = output_dir / "precommit.json"
    _write_json(
        precommit_path,
        _precommit_payload(plan=plan, run_label=run_label, artifact_root=root),
    )

    session_outcomes = _replay_plan_sessions(
        plan,
        upstream_candidate_factory=upstream_candidate_factory,
    )
    consensus_runs = tuple(item.consensus for item in session_outcomes)
    always_long_runs = tuple(item.always_long for item in session_outcomes)
    consensus = _strategy_totals(consensus_runs)
    always_long = _strategy_totals(always_long_runs)
    all_fills_local_paper = all(
        item.all_fills_local_paper for item in (*consensus_runs, *always_long_runs)
    )
    all_terminal_flat = all(item.terminal_flat for item in (*consensus_runs, *always_long_runs))
    if not all_fills_local_paper or not all_terminal_flat:
        raise RuntimeError("consensus replay must preserve local-paper-only replayable flat fills")
    decision_action_counts = _action_counts(session_outcomes)
    replay_digest = consensus_session_replay_digest(session_outcomes)
    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            plan=plan,
            run_label=run_label,
            artifact_root=root,
            consensus=consensus,
            always_long=always_long,
            abstention_count=sum(
                1 for outcome in session_outcomes if outcome.proposal_action == "abstain"
            ),
            decision_action_counts=decision_action_counts,
            all_fills_local_paper=all_fills_local_paper,
            all_terminal_flat=all_terminal_flat,
            replay_digest=replay_digest,
        ),
    )
    return KisIntradayConsensusReplayRun(
        run_label=run_label,
        status="complete",
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=len(plan.session_dates),
        consensus=consensus,
        always_long=always_long,
        abstention_count=sum(
            1 for outcome in session_outcomes if outcome.proposal_action == "abstain"
        ),
        decision_action_counts=decision_action_counts,
        all_fills_local_paper=all_fills_local_paper,
        all_terminal_flat=all_terminal_flat,
        replay_digest=replay_digest,
    )


def replay_frozen_consensus_sessions(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    upstream_candidate_factory: Callable[..., OpportunityEligibility],
) -> tuple[KisIntradayConsensusSessionReplay, ...]:
    """Reproduce frozen in-memory session outcomes without writing an artifact."""

    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=tuple(session_dates),
        campaign_id=KIS_INTRADAY_CONSENSUS_REPLAY_ID,
    )
    if len(plan.session_dates) != KIS_INTRADAY_SESSION_COUNT:
        raise RuntimeError("consensus replay must retain exactly twenty sessions")
    return replay_frozen_consensus_plan(
        plan,
        upstream_candidate_factory=upstream_candidate_factory,
    )


def replay_frozen_consensus_plan(
    plan: KisIntradayCpuCampaignPlan,
    *,
    upstream_candidate_factory: Callable[..., OpportunityEligibility],
) -> tuple[KisIntradayConsensusSessionReplay, ...]:
    """Reproduce one already-selected plan without changing its source identity."""

    if not isinstance(plan, KisIntradayCpuCampaignPlan):
        raise TypeError("consensus replay requires a frozen KIS intraday plan")
    if len(plan.session_dates) != KIS_INTRADAY_SESSION_COUNT:
        raise ValueError("consensus replay requires exactly twenty selected sessions")
    return _replay_plan_sessions(
        plan,
        upstream_candidate_factory=upstream_candidate_factory,
    )


def consensus_session_replay_digest(
    outcomes: Sequence[KisIntradayConsensusSessionReplay],
) -> str:
    """Return the safe full replay identity used by an immutable baseline summary."""

    return _replay_digest(
        tuple(outcome.consensus for outcome in outcomes),
        tuple(outcome.always_long for outcome in outcomes),
    )


def _replay_plan_sessions(
    plan: KisIntradayCpuCampaignPlan,
    *,
    upstream_candidate_factory: Callable[..., OpportunityEligibility],
    source_metadata_factory: Callable[..., CurrentSourceMetadata] | None = None,
) -> tuple[KisIntradayConsensusSessionReplay, ...]:
    outcomes: list[KisIntradayConsensusSessionReplay] = []
    for index in range(len(plan.session_dates)):
        decision, consensus, always_long = _run_session(
            plan=plan,
            index=index,
            upstream_candidate_factory=upstream_candidate_factory,
            source_metadata_factory=source_metadata_factory,
        )
        outcomes.append(
            KisIntradayConsensusSessionReplay(
                session_date=decision.session_date,
                proposal_action=decision.proposal_action,
                consensus=consensus,
                always_long=always_long,
            )
        )
    return tuple(outcomes)


def _run_session(
    *,
    plan: KisIntradayCpuCampaignPlan,
    index: int,
    upstream_candidate_factory: Callable[..., OpportunityEligibility],
    source_metadata_factory: Callable[..., CurrentSourceMetadata] | None = None,
) -> tuple[_SessionDecision, _TradeReplay, _TradeReplay]:
    session = plan.session_windows[index]
    bars = _session_bars(plan.cataloged_bars, session=session)
    decision = _build_session_decision(
        bars,
        session=session,
        session_date=plan.session_dates[index],
        upstream_candidate_factory=upstream_candidate_factory,
        source_metadata_factory=source_metadata_factory,
    )
    consensus = _run_consensus_local_paper(decision)
    always_long = _run_always_long_local_paper(decision)
    return decision, consensus, always_long


def _build_session_decision(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    session_date: date,
    upstream_candidate_factory: Callable[..., OpportunityEligibility],
    source_metadata_factory: Callable[..., CurrentSourceMetadata] | None = None,
) -> _SessionDecision:
    as_of = session.open_ts + KIS_INTRADAY_CONSENSUS_DECISION_OFFSET
    if as_of + KIS_INTRADAY_CONSENSUS_HORIZON != session.close_ts:
        raise ValueError("consensus replay requires a thirty-minute terminal session horizon")
    source_contract = build_causal_bar_source_contract(
        bars,
        contract_id=KIS_INTRADAY_CONSENSUS_SOURCE_CONTRACT_ID,
        as_of=as_of,
    )
    source_symbol, source_market = _source_identity(bars)
    upstream_candidate = upstream_candidate_factory(
        symbol=source_symbol,
        market=source_market,
        session_date=session_date,
        as_of=as_of,
    )
    opportunity = _adapt_session_opportunity(
        upstream_candidate=upstream_candidate,
        source_contract=source_contract,
        bars=bars,
        session=session,
        as_of=as_of,
        source_metadata_factory=source_metadata_factory,
    )
    signal_bar: Bar | None = None
    entry_bar: Bar | None = None
    exit_signal_bar: Bar | None = None
    exit_bar: Bar | None = None
    predictions = ()
    if opportunity.input_status == "ready":
        by_start = {bar.start_ts: bar for bar in bars}
        signal_bar = _required_bar(by_start, as_of - Timeframe.M1.duration, "decision signal")
        entry_bar = _required_bar(by_start, as_of, "entry")
        exit_bar = _required_bar(
            by_start,
            session.close_ts - Timeframe.M1.duration,
            "terminal exit",
        )
        exit_signal_bar = _required_bar(
            by_start,
            exit_bar.start_ts - Timeframe.M1.duration,
            "terminal exit signal",
        )
        evidence = build_multitimeframe_momentum_evidence(
            bars,
            session=session,
            config=frozen_multitimeframe_momentum_config(),
            as_of=as_of,
        )
        predictions = evidence.predictions
    proposal = propose_target_exposure(
        opportunity,
        predictions,
        current_exposure=Decimal("0"),
        config=frozen_target_position_policy_config(),
        as_of=as_of,
    )
    proposal_ref = _opaque_reference("proposal", proposal.proposal_id)
    receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_opaque_reference(
                "campaign",
                KIS_INTRADAY_CONSENSUS_REPLAY_ID,
                source_contract.contract_hash,
            ),
            model_ref=_opaque_reference("model", _model_contract_digest()),
            input_manifest_ref=source_contract.contract_hash,
            proposal_ref=proposal_ref,
        ),
    )
    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=proposal_ref,
            symbol=source_symbol,
            target_exposure=proposal.target_exposure,
            current_quantity=Decimal("0"),
            maximum_quantity=KIS_INTRADAY_CONSENSUS_MAXIMUM_QUANTITY,
        ),
        as_of=as_of,
    )
    return _SessionDecision(
        session_date=session_date,
        as_of=as_of,
        proposal_action=proposal.action,
        proposal_reason=proposal.reason,
        receipt=receipt,
        bridge=bridge,
        signal_bar=signal_bar,
        entry_bar=entry_bar,
        exit_signal_bar=exit_signal_bar,
        exit_bar=exit_bar,
    )


def _adapt_session_opportunity(
    *,
    upstream_candidate: OpportunityEligibility,
    source_contract: CurrentSourceContract,
    bars: Sequence[Bar],
    session: SessionWindow,
    as_of: datetime,
    source_metadata_factory: Callable[..., CurrentSourceMetadata] | None,
) -> OpportunityEligibility:
    """Project a caller-owned candidate through causal source facts only."""

    source_metadata = (source_metadata_factory or _current_source_metadata)(
        contract=source_contract,
        bars=bars,
        session=session,
        symbol=upstream_candidate.symbol,
        market=upstream_candidate.market,
        as_of=as_of,
    )
    return adapt_current_source_opportunity_eligibility(
        upstream_candidate,
        source_metadata,
        expected_contract=source_contract,
        as_of=as_of,
    ).eligibility


def _current_source_metadata(
    *,
    contract: CurrentSourceContract,
    bars: Sequence[Bar],
    session: SessionWindow,
    symbol: str,
    market: str,
    as_of: datetime,
) -> CurrentSourceMetadata:
    input_status = _current_source_input_status(
        bars,
        session=session,
        symbol=symbol,
        market=market,
        as_of=as_of,
    )
    return CurrentSourceMetadata(
        contract=contract,
        symbol=symbol,
        market=market,
        input_status=input_status,
        complete=input_status == "ready",
        observed_at=as_of,
        valid_until=as_of + timedelta(minutes=2),
    )


def _current_source_input_status(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    symbol: str,
    market: str,
    as_of: datetime,
) -> TargetInputStatus:
    normalized_bars = tuple(bars)
    if any(not isinstance(bar, Bar) for bar in normalized_bars):
        raise TypeError("bars must contain Bar values")
    prefix = tuple(bar for bar in normalized_bars if bar.end_ts <= as_of)
    if not prefix:
        return "missing"
    if any(
        bar.symbol != symbol or bar.market != market or bar.timeframe is not Timeframe.M1
        for bar in prefix
    ):
        return "misaligned"
    starts = tuple(bar.start_ts for bar in prefix)
    if len(starts) != len(set(starts)):
        return "duplicate"
    if any(not bar.complete for bar in prefix):
        return "incomplete"
    expected_count = int((as_of - session.open_ts) / Timeframe.M1.duration)
    expected_starts = tuple(
        session.open_ts + Timeframe.M1.duration * offset for offset in range(expected_count)
    )
    if tuple(sorted(starts)) != expected_starts:
        return "non_contiguous"
    return "ready"


def _source_identity(bars: Sequence[Bar]) -> tuple[str, str]:
    normalized_bars = tuple(bars)
    if not normalized_bars:
        raise ValueError("consensus replay session has no source bars")
    if any(not isinstance(bar, Bar) for bar in normalized_bars):
        raise TypeError("bars must contain Bar values")
    first = normalized_bars[0]
    return first.symbol, first.market


def _run_consensus_local_paper(decision: _SessionDecision) -> _TradeReplay:
    if decision.bridge.route != "local_paper":
        raise RuntimeError("consensus replay must use local paper only")
    if decision.bridge.status == "no_intent":
        return _empty_trade_replay()
    if (
        decision.signal_bar is None
        or decision.entry_bar is None
        or decision.exit_signal_bar is None
        or decision.exit_bar is None
    ):
        raise RuntimeError("consensus replay intent requires complete local bars")
    entry_order = decision.bridge.local_paper_intent
    if entry_order is None or entry_order.quantity != KIS_INTRADAY_CONSENSUS_QUANTITY:
        raise RuntimeError("consensus entry must prepare exactly one local-paper share")
    return _replay_round_trip(
        entry_order=entry_order,
        decision_id=decision.receipt.decision_id,
        signal_bar=decision.signal_bar,
        entry_bar=decision.entry_bar,
        exit_signal_bar=decision.exit_signal_bar,
        exit_bar=decision.exit_bar,
    )


def _run_always_long_local_paper(decision: _SessionDecision) -> _TradeReplay:
    if (
        decision.signal_bar is None
        or decision.entry_bar is None
        or decision.exit_signal_bar is None
        or decision.exit_bar is None
    ):
        return _empty_trade_replay()
    entry_order = OrderIntent(
        client_order_id=_client_order_id(
            "always-long-entry",
            decision.session_date.isoformat(),
            decision.receipt.decision_id,
        ),
        symbol=decision.signal_bar.symbol,
        market=decision.signal_bar.market,
        side="buy",
        quantity=KIS_INTRADAY_CONSENSUS_QUANTITY,
        limit_price=None,
        decision_id=f"always-long:{decision.receipt.decision_id}",
        created_at=decision.as_of,
    )
    return _replay_round_trip(
        entry_order=entry_order,
        decision_id=entry_order.decision_id,
        signal_bar=decision.signal_bar,
        entry_bar=decision.entry_bar,
        exit_signal_bar=decision.exit_signal_bar,
        exit_bar=decision.exit_bar,
    )


def _replay_round_trip(
    *,
    entry_order: OrderIntent,
    decision_id: str,
    signal_bar: Bar,
    entry_bar: Bar,
    exit_signal_bar: Bar,
    exit_bar: Bar,
) -> _TradeReplay:
    store = _InMemoryReplayEventStore()
    broker = LocalPaperBroker(
        event_store=store,  # type: ignore[arg-type]
        emergency_store=_ClearEmergencyStore(),  # type: ignore[arg-type]
        starting_cash=KIS_INTRADAY_CONSENSUS_STARTING_CASH,
        fee_bps=KIS_INTRADAY_CONSENSUS_FEE_BPS,
        slippage_bps=KIS_INTRADAY_CONSENSUS_SLIPPAGE_BPS,
    )
    entry = broker.submit_and_fill_next_bar(
        entry_order,
        signal_bar=signal_bar,
        execution_bar=entry_bar,
    )
    if entry.fill is None:
        raise RuntimeError("fixed replay entry did not produce a local-paper fill")
    exit_order = OrderIntent(
        client_order_id=_client_order_id("terminal-exit", entry_order.client_order_id),
        symbol=entry_order.symbol,
        market=entry_order.market,
        side="sell",
        quantity=entry.fill.quantity,
        limit_price=None,
        decision_id=f"{decision_id}:terminal-horizon-exit",
        created_at=entry_bar.end_ts,
    )
    exit_execution = broker.submit_and_fill_next_bar(
        exit_order,
        signal_bar=exit_signal_bar,
        execution_bar=exit_bar,
    )
    if exit_execution.fill is None:
        raise RuntimeError("fixed replay exit did not produce a local-paper fill")
    replayed = replay_local_paper_account(
        store,  # type: ignore[arg-type]
        starting_cash=KIS_INTRADAY_CONSENSUS_STARTING_CASH,
    )
    account = broker.account()
    if account != replayed:
        raise RuntimeError("local-paper account did not match event replay")
    terminal_position = account.quantity(market=entry_order.market, symbol=entry_order.symbol)
    events = store.iter_events()
    fill_events = tuple(event for event in events if event.event_type == "fill")
    all_fills_local_paper = bool(fill_events) and all(
        event.payload.get("source") == LOCAL_PAPER_SOURCE for event in fill_events
    )
    if len(fill_events) != 2 or not all_fills_local_paper or terminal_position != 0:
        raise RuntimeError("fixed replay must end with two local-paper fills and no position")
    return _TradeReplay(
        after_cost_pnl=account.cash - KIS_INTRADAY_CONSENSUS_STARTING_CASH,
        fill_count=len(fill_events),
        terminal_flat=True,
        all_fills_local_paper=True,
        replay_digest=_event_digest(events),
    )


def _empty_trade_replay() -> _TradeReplay:
    return _TradeReplay(
        after_cost_pnl=Decimal("0"),
        fill_count=0,
        terminal_flat=True,
        all_fills_local_paper=True,
        replay_digest=_event_digest(()),
    )


def _strategy_totals(runs: Sequence[_TradeReplay]) -> ConsensusReplayStrategyTotals:
    cumulative = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for run in runs:
        cumulative += run.after_cost_pnl
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
    return ConsensusReplayStrategyTotals(
        after_cost_pnl=cumulative,
        round_trip_count=sum(1 for run in runs if run.fill_count == 2),
        fill_count=sum(run.fill_count for run in runs),
        max_drawdown=max_drawdown,
    )


def _action_counts(
    outcomes: Sequence[KisIntradayConsensusSessionReplay],
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.proposal_action] = counts.get(outcome.proposal_action, 0) + 1
    return tuple(sorted(counts.items()))


def _replay_digest(
    consensus_runs: Sequence[_TradeReplay],
    always_long_runs: Sequence[_TradeReplay],
) -> str:
    payload = {
        "consensus": [run.replay_digest for run in consensus_runs],
        "always_long": [run.replay_digest for run in always_long_runs],
    }
    return "sha256:" + _sha256_json(payload)


def _precommit_payload(
    *,
    plan: KisIntradayCpuCampaignPlan,
    run_label: str,
    artifact_root: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_intraday_consensus_replay_precommit",
        "status": "frozen_before_replay",
        "run_label": run_label,
        "source": {
            "dataset_id": plan.cataloged_bars.dataset_id,
            "dataset_hash": plan.cataloged_bars.dataset_hash,
            "session_dates": [item.isoformat() for item in plan.session_dates],
            "session_count": len(plan.session_dates),
        },
        "contract": {
            "model": _model_contract_payload(),
            "decision_as_of_offset_seconds": int(
                KIS_INTRADAY_CONSENSUS_DECISION_OFFSET.total_seconds()
            ),
            "entry": "next_completed_1m_bar_open",
            "terminal_horizon_seconds": int(KIS_INTRADAY_CONSENSUS_HORIZON.total_seconds()),
            "terminal_exit": "precommitted_open_of_terminal_1m_bar",
            "quantity": str(KIS_INTRADAY_CONSENSUS_QUANTITY),
            "starting_cash": str(KIS_INTRADAY_CONSENSUS_STARTING_CASH),
            "fee_bps": str(KIS_INTRADAY_CONSENSUS_FEE_BPS),
            "slippage_bps": str(KIS_INTRADAY_CONSENSUS_SLIPPAGE_BPS),
            "comparators": ("flat", "always_long_time_matched"),
            "post_outcome_tuning_allowed": False,
        },
        "artifact_policy": _artifact_policy(artifact_root),
    }


def _summary_payload(
    *,
    plan: KisIntradayCpuCampaignPlan,
    run_label: str,
    artifact_root: Path,
    consensus: ConsensusReplayStrategyTotals,
    always_long: ConsensusReplayStrategyTotals,
    abstention_count: int,
    decision_action_counts: tuple[tuple[str, int], ...],
    all_fills_local_paper: bool,
    all_terminal_flat: bool,
    replay_digest: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_intraday_consensus_replay_summary",
        "status": "complete",
        "mode": "offline_local_cache_local_paper_only",
        "run_label": run_label,
        "source": {
            "dataset_id": plan.cataloged_bars.dataset_id,
            "dataset_hash": plan.cataloged_bars.dataset_hash,
            "session_count": len(plan.session_dates),
        },
        "comparators": {
            "flat": {
                "after_cost_pnl": "0",
                "round_trip_count": 0,
                "fill_count": 0,
                "max_drawdown": "0",
            },
            "always_long_time_matched": _strategy_payload(always_long),
        },
        "consensus": {
            **_strategy_payload(consensus),
            "abstention_count": abstention_count,
            "decision_action_counts": dict(decision_action_counts),
        },
        "replay_proof": {
            "local_paper_source": LOCAL_PAPER_SOURCE,
            "all_fills_local_paper": all_fills_local_paper,
            "all_terminal_flat": all_terminal_flat,
            "event_replay_digest": replay_digest,
            "raw_fill_events_retained": False,
        },
        "artifact_policy": _artifact_policy(artifact_root),
        "claim": (
            "fixed descriptive local-paper baseline only; it does not select a model, "
            "form an ensemble, open a sealed evaluation, schedule KIS Paper behavior, "
            "or establish profitability"
        ),
    }


def _strategy_payload(totals: ConsensusReplayStrategyTotals) -> dict[str, object]:
    return {
        "after_cost_pnl": str(totals.after_cost_pnl),
        "round_trip_count": totals.round_trip_count,
        "fill_count": totals.fill_count,
        "max_drawdown": str(totals.max_drawdown),
    }


def _artifact_policy(artifact_root: Path) -> dict[str, object]:
    return {
        "root": str(artifact_root),
        "repo_storage_allowed": False,
        "raw_market_data_written": False,
        "raw_fill_events_retained": False,
        "checkpoint_written": False,
        "credential_read": False,
        "network_called": False,
        "broker_called": False,
    }


def _model_contract_payload() -> dict[str, object]:
    momentum = frozen_multitimeframe_momentum_config()
    policy = frozen_target_position_policy_config()
    return {
        "momentum_experts": [
            {
                "timeframe": spec.timeframe.value,
                "lookback": spec.lookback,
                "buy_threshold_bps": str(spec.buy_threshold_bps),
                "sell_threshold_bps": str(spec.sell_threshold_bps),
            }
            for spec in momentum.experts
        ],
        "policy": {
            "policy_id": policy.policy_id,
            "feature_schema_id": policy.feature_schema_id,
            "required_timeframes": [item.value for item in policy.required_timeframes],
            "maximum_evidence_age_seconds": {
                item.value: int(policy.maximum_evidence_age[item].total_seconds())
                for item in policy.required_timeframes
            },
            "minimum_confidence": str(policy.minimum_confidence),
            "minimum_absolute_edge_bps": str(policy.minimum_absolute_edge_bps),
            "entry_target_exposure": str(policy.entry_target_exposure),
            "decision_ttl_seconds": int(policy.decision_ttl.total_seconds()),
        },
    }


def _model_contract_digest() -> str:
    return "sha256:" + _sha256_json(_model_contract_payload())


def _session_bars(catalog: CatalogedBars, *, session: SessionWindow) -> tuple[Bar, ...]:
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.open_ts and bar.end_ts <= session.close_ts
    )
    if not bars:
        raise ValueError("consensus replay session has no source bars")
    return bars


def _required_bar(by_start: dict[datetime, Bar], start_ts: datetime, label: str) -> Bar:
    bar = by_start.get(start_ts)
    if bar is None or not bar.complete:
        raise ValueError(f"consensus replay is missing the required {label} bar")
    return bar


def _opaque_reference(*parts: str) -> str:
    return "ref:" + _sha256_json(list(parts))


def _client_order_id(*parts: str) -> str:
    return "replay-" + _sha256_json(list(parts))[:40]


def _event_digest(events: Sequence[Event]) -> str:
    return "sha256:" + _sha256_json([event.to_record() for event in events])


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _reject_repo_artifact_root(artifact_root: Path, repo_root: Path) -> None:
    resolved_repo = Path(repo_root).resolve()
    if artifact_root == resolved_repo or artifact_root.is_relative_to(resolved_repo):
        raise ValueError("artifact root must stay outside the Git workspace")


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

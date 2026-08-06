"""Frozen mechanics replay for the session-reset Donchian baseline.

This is deliberately a source-local conformance study, not a predictive
campaign.  It proves that a fixed causal rule can move through the existing
receipt and local-paper boundary on complete cached M1 bars without retaining
raw prices, fills, or performance metrics as artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from thericher_v2.contracts import Bar, EmergencyState, OrderIntent, TargetExposureProposal
from thericher_v2.data import (
    CatalogedBars,
    SessionWindow,
    require_complete_kis_paper_private_intraday_session,
    us_equity_2026_session,
)
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN
from thericher_v2.execution import LOCAL_PAPER_SOURCE, LocalPaperBroker, replay_local_paper_account
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    PaperDecisionBridgeResult,
    prepare_local_paper_intent,
)
from thericher_v2.models.current_source_opportunity_eligibility import (
    build_causal_bar_source_contract,
)
from thericher_v2.models.session_reset_donchian import SessionResetDonchianRule
from thericher_v2.models.session_reset_donchian_target import (
    SESSION_RESET_DONCHIAN_TARGET_FEATURE_SCHEMA_ID,
    SessionResetDonchianTargetConfig,
    propose_session_reset_donchian_target,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.state import Event

from .kis_intraday_campaign import (
    KIS_INTRADAY_SESSION_COUNT,
    KisIntradayCpuCampaignPlan,
    build_kis_intraday_cpu_campaign_plan,
)

KIS_INTRADAY_DONCHIAN_REPLAY_ID = "kis-intraday-session-reset-donchian-mechanics-v1"
KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK = 20
KIS_INTRADAY_DONCHIAN_EXIT_LOOKBACK = 10
KIS_INTRADAY_DONCHIAN_TARGET_EXPOSURE = Decimal("0.10")
KIS_INTRADAY_DONCHIAN_CONFIDENCE = Decimal("0.50")
KIS_INTRADAY_DONCHIAN_MAXIMUM_QUANTITY = Decimal("10")
KIS_INTRADAY_DONCHIAN_STARTING_CASH = Decimal("10000")
KIS_INTRADAY_DONCHIAN_FEE_BPS = Decimal("1")
KIS_INTRADAY_DONCHIAN_SLIPPAGE_BPS = Decimal("2")
KIS_INTRADAY_DONCHIAN_DECISION_TTL = timedelta(minutes=2)

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CLEAR_EMERGENCY_STATE = EmergencyState(
    stop_new_orders=False,
    cancel_open_orders_requested=False,
    reason="offline_replay_clear",
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
)


@dataclass(frozen=True)
class DonchianReplayMechanics:
    """Aggregate mechanics evidence for the fixed rule, without PnL fields."""

    decision_count: int
    eligible_enter_count: int
    eligible_exit_count: int
    forced_terminal_exit_count: int
    local_paper_fill_count: int
    all_fills_local_paper: bool
    all_terminal_flat: bool
    replay_digest: str


@dataclass(frozen=True)
class LocalPaperControlMechanics:
    """Aggregate mechanics evidence for a fixed time-matched control."""

    local_paper_fill_count: int
    all_fills_local_paper: bool
    all_terminal_flat: bool
    replay_digest: str


@dataclass(frozen=True)
class KisIntradayDonchianReplayRun:
    """Source-safe immutable result for one mechanics-only replay attempt."""

    run_label: str
    status: str
    contract_hash: str
    precommit_path: Path
    summary_path: Path
    session_count: int
    donchian: DonchianReplayMechanics
    flat_control: LocalPaperControlMechanics
    always_long_control: LocalPaperControlMechanics


@dataclass(frozen=True)
class _SessionReplay:
    donchian: DonchianReplayMechanics
    always_long: LocalPaperControlMechanics


class _InMemoryReplayEventStore:
    """Keep local-paper events replayable without storing them as artifacts."""

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
    """Offline replay must not inherit mutable process emergency state."""

    def read(self) -> EmergencyState:
        return _CLEAR_EMERGENCY_STATE


def select_first_complete_kis_intraday_regular_session_dates(
    catalog: CatalogedBars,
) -> tuple[date, ...]:
    """Choose the first twenty complete regular sessions in outcome-blind order."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("Donchian replay requires CatalogedBars")
    candidate_dates = sorted(
        {
            bar.start_ts.astimezone(US_EQUITY_EASTERN).date()
            for bar in catalog.bars
            if bar.start_ts.astimezone(US_EQUITY_EASTERN).year == 2026
        }
    )
    selected: list[date] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        try:
            require_complete_kis_paper_private_intraday_session(
                catalog,
                session=session.window,
            )
        except ValueError:
            continue
        selected.append(session_date)
        if len(selected) == KIS_INTRADAY_SESSION_COUNT:
            return tuple(selected)
    raise ValueError("Donchian replay requires twenty complete regular KIS M1 sessions")


def run_kis_intraday_session_reset_donchian_replay(
    catalog: CatalogedBars,
    *,
    artifact_root: Path,
    run_label: str,
) -> KisIntradayDonchianReplayRun:
    """Run one frozen source-local mechanics replay with no provider or broker I/O."""

    _validate_run_label(run_label)
    session_dates = select_first_complete_kis_intraday_regular_session_dates(catalog)
    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=session_dates,
        campaign_id=KIS_INTRADAY_DONCHIAN_REPLAY_ID,
    )
    root = Path(artifact_root).resolve()
    _reject_repo_artifact_root(root)
    output_dir = root / "research" / KIS_INTRADAY_DONCHIAN_REPLAY_ID / run_label
    if output_dir.exists():
        raise FileExistsError(f"Donchian replay artifact already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    contract = _contract_payload(plan)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = output_dir / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_intraday_donchian_replay_precommit",
            "status": "frozen_before_replay",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(root),
        },
    )

    replays = tuple(
        _replay_session(plan, index=index, contract_hash=contract_hash)
        for index in range(len(plan.session_dates))
    )
    donchian = _sum_donchian(item.donchian for item in replays)
    always_long = _sum_control(item.always_long for item in replays)
    flat = _flat_control()
    status = "complete" if _rule_activated(donchian) else "no_rule_activation"
    if not (
        donchian.all_fills_local_paper
        and donchian.all_terminal_flat
        and always_long.all_fills_local_paper
        and always_long.all_terminal_flat
        and flat.all_fills_local_paper
        and flat.all_terminal_flat
    ):
        raise RuntimeError("Donchian replay mechanics must remain local-paper and terminal-flat")

    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            plan=plan,
            run_label=run_label,
            status=status,
            contract_hash=contract_hash,
            artifact_root=root,
            donchian=donchian,
            flat=flat,
            always_long=always_long,
        ),
    )
    return KisIntradayDonchianReplayRun(
        run_label=run_label,
        status=status,
        contract_hash=contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=len(plan.session_dates),
        donchian=donchian,
        flat_control=flat,
        always_long_control=always_long,
    )


def _replay_session(
    plan: KisIntradayCpuCampaignPlan,
    *,
    index: int,
    contract_hash: str,
) -> _SessionReplay:
    session = plan.session_windows[index]
    bars = _session_bars(plan.cataloged_bars, session=session)
    if len(bars) < KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK + 2:
        raise ValueError("Donchian replay session is shorter than its frozen warmup and exit")
    return _SessionReplay(
        donchian=_run_donchian_local_paper(
            bars,
            session=session,
            contract_hash=contract_hash,
        ),
        always_long=_run_always_long_local_paper(
            bars,
            session=session,
            contract_hash=contract_hash,
        ),
    )


def _run_donchian_local_paper(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    contract_hash: str,
) -> DonchianReplayMechanics:
    rule = SessionResetDonchianRule(
        entry_lookback=KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK,
        exit_lookback=KIS_INTRADAY_DONCHIAN_EXIT_LOOKBACK,
    )
    config = _target_config(bars)
    store, broker = _new_local_paper_broker()
    decision_count = 0
    enter_count = 0
    exit_count = 0
    forced_terminal_exit_count = 0

    terminal_signal = bars[-2]
    terminal_execution = bars[-1]
    for signal_index in range(len(bars) - 2):
        signal_bar = bars[signal_index]
        execution_bar = bars[signal_index + 1]
        current_quantity = broker.account().quantity(market=config.market, symbol=config.symbol)
        proposal = propose_session_reset_donchian_target(
            bars[: signal_index + 1],
            session=session,
            as_of=signal_bar.end_ts,
            model_position="long" if current_quantity > 0 else "flat",
            rule=rule,
            config=config,
        )
        decision_count += 1
        if proposal.action == "enter":
            enter_count += 1
        elif proposal.action == "exit":
            exit_count += 1
        _submit_target_proposal(
            proposal,
            broker=broker,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
            contract_hash=contract_hash,
            input_manifest_ref=_causal_input_manifest_ref(
                bars[: signal_index + 1],
                as_of=signal_bar.end_ts,
            ),
        )

    current_quantity = broker.account().quantity(market=config.market, symbol=config.symbol)
    if current_quantity > 0:
        forced_terminal_exit_count = 1
        terminal = _terminal_flatten_proposal(
            config=config,
            contract_hash=contract_hash,
            signal_bar=terminal_signal,
            execution_bar=terminal_execution,
        )
        _submit_target_proposal(
            terminal,
            broker=broker,
            signal_bar=terminal_signal,
            execution_bar=terminal_execution,
            contract_hash=contract_hash,
            input_manifest_ref=_causal_input_manifest_ref(
                bars[:-1],
                as_of=terminal_signal.end_ts,
            ),
        )
    return _donchian_mechanics(
        store,
        broker,
        decision_count=decision_count,
        eligible_enter_count=enter_count,
        eligible_exit_count=exit_count,
        forced_terminal_exit_count=forced_terminal_exit_count,
    )


def _run_always_long_local_paper(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    contract_hash: str,
) -> LocalPaperControlMechanics:
    store, broker = _new_local_paper_broker()
    entry_signal = bars[KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK]
    entry_execution = bars[KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK + 1]
    entry = OrderIntent(
        client_order_id=_client_order_id(
            "always-long-entry",
            contract_hash,
            entry_signal.end_ts.isoformat(),
        ),
        symbol=entry_signal.symbol,
        market=entry_signal.market,
        side="buy",
        quantity=Decimal("1"),
        limit_price=None,
        decision_id=f"always-long:{_sha256_json([contract_hash, entry_signal.end_ts.isoformat()])}",
        created_at=entry_signal.end_ts,
        valid_until=entry_execution.end_ts,
    )
    _submit_local_intent(
        entry,
        broker=broker,
        signal_bar=entry_signal,
        execution_bar=entry_execution,
    )

    terminal_signal = bars[-2]
    terminal_execution = bars[-1]
    current_quantity = broker.account().quantity(market=entry.market, symbol=entry.symbol)
    if current_quantity <= 0:
        raise RuntimeError(
            "always-long control must hold a local-paper position before terminal exit"
        )
    terminal = OrderIntent(
        client_order_id=_client_order_id(
            "always-long-terminal-exit",
            contract_hash,
            terminal_signal.end_ts.isoformat(),
        ),
        symbol=entry.symbol,
        market=entry.market,
        side="sell",
        quantity=current_quantity,
        limit_price=None,
        decision_id=(
            "always-long-terminal:"
            + _sha256_json([contract_hash, terminal_signal.end_ts.isoformat()])
        ),
        created_at=terminal_signal.end_ts,
        valid_until=terminal_execution.end_ts,
    )
    _submit_local_intent(
        terminal,
        broker=broker,
        signal_bar=terminal_signal,
        execution_bar=terminal_execution,
    )
    return _control_mechanics(store, broker)


def _submit_target_proposal(
    proposal: TargetExposureProposal,
    *,
    broker: LocalPaperBroker,
    signal_bar: Bar,
    execution_bar: Bar,
    contract_hash: str,
    input_manifest_ref: str,
) -> PaperDecisionBridgeResult:
    proposal_ref = _opaque_reference("proposal", proposal.proposal_id)
    receipt = receipt_from_target_exposure_proposal(
        proposal,
        references=DecisionReceiptReferences(
            campaign_ref=_opaque_reference("campaign", contract_hash),
            model_ref=_opaque_reference(
                "model",
                str(KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK),
                str(KIS_INTRADAY_DONCHIAN_EXIT_LOOKBACK),
            ),
            input_manifest_ref=input_manifest_ref,
            proposal_ref=proposal_ref,
        ),
    )
    current_quantity = broker.account().quantity(market=proposal.market, symbol=proposal.symbol)
    bridge = prepare_local_paper_intent(
        receipt,
        binding=LocalPaperTargetBinding(
            proposal_ref=proposal_ref,
            symbol=proposal.symbol,
            target_exposure=proposal.target_exposure,
            current_quantity=current_quantity,
            maximum_quantity=KIS_INTRADAY_DONCHIAN_MAXIMUM_QUANTITY,
        ),
        as_of=proposal.decided_at,
    )
    if bridge.route != "local_paper":
        raise RuntimeError("Donchian mechanics replay must remain local-paper-only")
    if proposal.action in {"enter", "exit"} and bridge.status != "ready":
        raise RuntimeError("eligible Donchian proposal did not prepare a local-paper intent")
    if bridge.status == "ready":
        if bridge.local_paper_intent is None:
            raise RuntimeError("ready local-paper bridge omitted an intent")
        _submit_local_intent(
            bridge.local_paper_intent,
            broker=broker,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )
    return bridge


def _submit_local_intent(
    intent: OrderIntent,
    *,
    broker: LocalPaperBroker,
    signal_bar: Bar,
    execution_bar: Bar,
) -> None:
    execution = broker.submit_and_fill_next_bar(
        intent,
        signal_bar=signal_bar,
        execution_bar=execution_bar,
    )
    if execution.fill is None or execution.fill.source != LOCAL_PAPER_SOURCE:
        raise RuntimeError("mechanics replay intent did not create one local-paper fill")


def _terminal_flatten_proposal(
    *,
    config: SessionResetDonchianTargetConfig,
    contract_hash: str,
    signal_bar: Bar,
    execution_bar: Bar,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=(
            "session-reset-donchian-terminal-flat-v1:sha256:"
            + _sha256_json([contract_hash, signal_bar.end_ts.isoformat()])
        ),
        symbol=config.symbol,
        market=config.market,
        action="exit",
        target_exposure=Decimal("0"),
        confidence=Decimal("1"),
        feature_schema_id=SESSION_RESET_DONCHIAN_TARGET_FEATURE_SCHEMA_ID,
        input_status="ready",
        decided_at=signal_bar.end_ts,
        valid_until=execution_bar.end_ts,
        feature_window_end=signal_bar.end_ts,
        reason="predeclared_terminal_flat",
    )


def _target_config(bars: Sequence[Bar]) -> SessionResetDonchianTargetConfig:
    if not bars:
        raise ValueError("Donchian replay session has no bars")
    first = bars[0]
    return SessionResetDonchianTargetConfig(
        symbol=first.symbol,
        market=first.market,
        timeframe=first.timeframe,
        target_exposure=KIS_INTRADAY_DONCHIAN_TARGET_EXPOSURE,
        confidence=KIS_INTRADAY_DONCHIAN_CONFIDENCE,
        decision_ttl=KIS_INTRADAY_DONCHIAN_DECISION_TTL,
    )


def _causal_input_manifest_ref(bars: Sequence[Bar], *, as_of: datetime) -> str:
    return build_causal_bar_source_contract(
        bars,
        contract_id="kis-intraday-donchian-m1-causal-source-v1",
        as_of=as_of,
    ).contract_hash


def _new_local_paper_broker() -> tuple[_InMemoryReplayEventStore, LocalPaperBroker]:
    store = _InMemoryReplayEventStore()
    return (
        store,
        LocalPaperBroker(
            event_store=store,  # type: ignore[arg-type]
            emergency_store=_ClearEmergencyStore(),  # type: ignore[arg-type]
            starting_cash=KIS_INTRADAY_DONCHIAN_STARTING_CASH,
            fee_bps=KIS_INTRADAY_DONCHIAN_FEE_BPS,
            slippage_bps=KIS_INTRADAY_DONCHIAN_SLIPPAGE_BPS,
        ),
    )


def _donchian_mechanics(
    store: _InMemoryReplayEventStore,
    broker: LocalPaperBroker,
    *,
    decision_count: int,
    eligible_enter_count: int,
    eligible_exit_count: int,
    forced_terminal_exit_count: int,
) -> DonchianReplayMechanics:
    control = _control_mechanics(store, broker)
    return DonchianReplayMechanics(
        decision_count=decision_count,
        eligible_enter_count=eligible_enter_count,
        eligible_exit_count=eligible_exit_count,
        forced_terminal_exit_count=forced_terminal_exit_count,
        local_paper_fill_count=control.local_paper_fill_count,
        all_fills_local_paper=control.all_fills_local_paper,
        all_terminal_flat=control.all_terminal_flat,
        replay_digest=control.replay_digest,
    )


def _control_mechanics(
    store: _InMemoryReplayEventStore,
    broker: LocalPaperBroker,
) -> LocalPaperControlMechanics:
    account = broker.account()
    replayed = replay_local_paper_account(
        store,  # type: ignore[arg-type]
        starting_cash=KIS_INTRADAY_DONCHIAN_STARTING_CASH,
    )
    if account != replayed:
        raise RuntimeError("local-paper account did not match its replay")
    events = store.iter_events()
    fill_events = tuple(event for event in events if event.event_type == "fill")
    all_fills_local_paper = all(
        event.payload.get("source") == LOCAL_PAPER_SOURCE for event in fill_events
    )
    return LocalPaperControlMechanics(
        local_paper_fill_count=len(fill_events),
        all_fills_local_paper=all_fills_local_paper,
        all_terminal_flat=account.positions == (),
        replay_digest=_event_digest(events),
    )


def _sum_donchian(items: Sequence[DonchianReplayMechanics]) -> DonchianReplayMechanics:
    records = tuple(items)
    return DonchianReplayMechanics(
        decision_count=sum(item.decision_count for item in records),
        eligible_enter_count=sum(item.eligible_enter_count for item in records),
        eligible_exit_count=sum(item.eligible_exit_count for item in records),
        forced_terminal_exit_count=sum(item.forced_terminal_exit_count for item in records),
        local_paper_fill_count=sum(item.local_paper_fill_count for item in records),
        all_fills_local_paper=all(item.all_fills_local_paper for item in records),
        all_terminal_flat=all(item.all_terminal_flat for item in records),
        replay_digest="sha256:" + _sha256_json([item.replay_digest for item in records]),
    )


def _sum_control(items: Sequence[LocalPaperControlMechanics]) -> LocalPaperControlMechanics:
    records = tuple(items)
    return LocalPaperControlMechanics(
        local_paper_fill_count=sum(item.local_paper_fill_count for item in records),
        all_fills_local_paper=all(item.all_fills_local_paper for item in records),
        all_terminal_flat=all(item.all_terminal_flat for item in records),
        replay_digest="sha256:" + _sha256_json([item.replay_digest for item in records]),
    )


def _flat_control() -> LocalPaperControlMechanics:
    return LocalPaperControlMechanics(
        local_paper_fill_count=0,
        all_fills_local_paper=True,
        all_terminal_flat=True,
        replay_digest="sha256:" + _sha256_json([]),
    )


def _contract_payload(plan: KisIntradayCpuCampaignPlan) -> dict[str, object]:
    selection_dates = [item.isoformat() for item in plan.session_dates]
    return {
        "schema_version": 1,
        "source": {
            "dataset_id": plan.cataloged_bars.dataset_id,
            "dataset_hash": plan.cataloged_bars.dataset_hash,
            "session_count": len(plan.session_dates),
            "selection": "first_20_complete_regular_sessions_ascending",
            "selected_session_dates_sha256": "sha256:" + _sha256_json(selection_dates),
        },
        "rule": {
            "id": "session-reset-donchian-v1",
            "entry_lookback": KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK,
            "exit_lookback": KIS_INTRADAY_DONCHIAN_EXIT_LOOKBACK,
            "channel_excludes_trigger_bar": True,
            "session_local_warmup_bars": KIS_INTRADAY_DONCHIAN_ENTRY_LOOKBACK,
        },
        "execution": {
            "decision": "completed_1m_bar_end",
            "entry_exit": "next_completed_1m_bar_open",
            "terminal_exit": "predeclared_penultimate_bar_decision_final_bar_open_fill",
            "target_exposure": str(KIS_INTRADAY_DONCHIAN_TARGET_EXPOSURE),
            "maximum_quantity": str(KIS_INTRADAY_DONCHIAN_MAXIMUM_QUANTITY),
            "fee_bps": str(KIS_INTRADAY_DONCHIAN_FEE_BPS),
            "slippage_bps": str(KIS_INTRADAY_DONCHIAN_SLIPPAGE_BPS),
        },
        "controls": ("flat_time_matched", "always_long_after_warmup_time_matched"),
        "limits": {
            "decision_time_availability": "not_observed",
            "performance_metrics_retained": False,
            "post_outcome_tuning_allowed": False,
            "promotion_allowed": False,
            "paper_input_allowed": False,
            "gpu_eligible": False,
        },
    }


def _summary_payload(
    *,
    plan: KisIntradayCpuCampaignPlan,
    run_label: str,
    status: str,
    contract_hash: str,
    artifact_root: Path,
    donchian: DonchianReplayMechanics,
    flat: LocalPaperControlMechanics,
    always_long: LocalPaperControlMechanics,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "kis_intraday_donchian_replay_summary",
        "status": status,
        "mode": "offline_local_cache_local_paper_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source": {
            "dataset_id": plan.cataloged_bars.dataset_id,
            "dataset_hash": plan.cataloged_bars.dataset_hash,
            "session_count": len(plan.session_dates),
        },
        "mechanics": _donchian_payload(donchian),
        "comparators": {
            "flat_time_matched": _control_payload(flat),
            "always_long_after_warmup_time_matched": _control_payload(always_long),
        },
        "limits": {
            "decision_time_availability": "not_observed",
            "performance_metrics_retained": False,
            "promotion_allowed": False,
            "paper_input_allowed": False,
            "gpu_eligible": False,
        },
        "artifact_policy": _artifact_policy(artifact_root),
        "claim": _claim_for_status(status),
    }


def _donchian_payload(value: DonchianReplayMechanics) -> dict[str, object]:
    return {
        "decision_count": value.decision_count,
        "eligible_enter_count": value.eligible_enter_count,
        "eligible_exit_count": value.eligible_exit_count,
        "forced_terminal_exit_count": value.forced_terminal_exit_count,
        "local_paper_fill_count": value.local_paper_fill_count,
        "all_fills_local_paper": value.all_fills_local_paper,
        "all_terminal_flat": value.all_terminal_flat,
        "rule_activated": _rule_activated(value),
        "event_replay_digest": value.replay_digest,
    }


def _control_payload(value: LocalPaperControlMechanics) -> dict[str, object]:
    return {
        "local_paper_fill_count": value.local_paper_fill_count,
        "all_fills_local_paper": value.all_fills_local_paper,
        "all_terminal_flat": value.all_terminal_flat,
        "event_replay_digest": value.replay_digest,
    }


def _artifact_policy(artifact_root: Path) -> dict[str, object]:
    return {
        "root": str(artifact_root),
        "repo_storage_allowed": False,
        "raw_market_data_written": False,
        "raw_fill_events_retained": False,
        "credential_read": False,
        "network_called": False,
        "external_broker_called": False,
    }


def _claim_for_status(status: str) -> str:
    if status == "complete":
        return (
            "fixed mechanics and replay-conformance preflight only; it does not establish "
            "profitability, select a model, form an ensemble, open a sealed evaluation, "
            "or create a Paper input"
        )
    if status == "no_rule_activation":
        return (
            "the fixed rule produced no executable enter or exit; this is only a "
            "source-local no-rule-activation record and does not establish replay "
            "conformance, profitability, a model, an ensemble, or a Paper input"
        )
    raise ValueError(f"unsupported Donchian replay status: {status}")


def _session_bars(catalog: CatalogedBars, *, session: SessionWindow) -> tuple[Bar, ...]:
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.open_ts and bar.end_ts <= session.close_ts
    )
    if not bars:
        raise ValueError("Donchian replay session has no bars")
    if any(not bar.complete for bar in bars):
        raise ValueError("Donchian replay session has incomplete bars")
    return bars


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


def _rule_activated(value: DonchianReplayMechanics) -> bool:
    return value.eligible_enter_count + value.eligible_exit_count > 0


def _reject_repo_artifact_root(artifact_root: Path) -> None:
    if artifact_root == _REPOSITORY_ROOT or artifact_root.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("artifact root must stay outside the Git workspace")


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

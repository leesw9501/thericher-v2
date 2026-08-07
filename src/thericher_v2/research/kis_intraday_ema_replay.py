"""Frozen mechanics replay for the session-reset EMA baseline.

This source-local conformance study proves only that the fixed 15/30 EMA rule
can traverse the existing causal receipt and local-paper boundary on complete
cached M1 bars. It retains no raw prices, fills, or performance metrics in its
external artifacts, and it is not a predictive campaign or Paper input.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import Bar, EmergencyState, TargetExposureProposal
from thericher_v2.data import CatalogedBars, SessionWindow
from thericher_v2.execution import (
    LOCAL_PAPER_SOURCE,
    LocalPaperAccount,
    LocalPaperBroker,
    replay_local_paper_account,
)
from thericher_v2.execution.paper_decision_bridge import (
    LocalPaperTargetBinding,
    PaperDecisionBridgeResult,
    prepare_local_paper_intent,
)
from thericher_v2.models.session_reset_ema_state import SessionResetEmaStateRule
from thericher_v2.models.session_reset_ema_state_target import (
    SESSION_RESET_EMA_STATE_TARGET_FEATURE_SCHEMA_ID,
    SessionResetEmaStateTargetConfig,
    propose_session_reset_ema_state_target,
)
from thericher_v2.research.decision_receipt import (
    DecisionReceiptReferences,
    receipt_from_target_exposure_proposal,
)
from thericher_v2.state import Event

from .kis_intraday_campaign import KisIntradayCpuCampaignPlan, build_kis_intraday_cpu_campaign_plan
from .kis_intraday_donchian_replay import select_first_complete_kis_intraday_regular_session_dates

KIS_INTRADAY_EMA_REPLAY_ID = "kis-intraday-session-reset-ema-mechanics-v1"
KIS_INTRADAY_EMA_FAST_PERIOD = 15
KIS_INTRADAY_EMA_SLOW_PERIOD = 30
KIS_INTRADAY_EMA_TOLERANCE = Decimal("0.00015")
KIS_INTRADAY_EMA_TARGET_EXPOSURE = Decimal("0.10")
KIS_INTRADAY_EMA_CONFIDENCE = Decimal("0.50")
KIS_INTRADAY_EMA_MAXIMUM_QUANTITY = Decimal("10")
KIS_INTRADAY_EMA_STARTING_CASH = Decimal("10000")
KIS_INTRADAY_EMA_FEE_BPS = Decimal("1")
KIS_INTRADAY_EMA_SLIPPAGE_BPS = Decimal("2")
KIS_INTRADAY_EMA_DECISION_TTL = timedelta(minutes=2)

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SHA256_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REQUIRED_DATASET_ID_PREFIX = "kis.paper.private.intraday.qqq.nas.m1."
_SELECTION_CALENDAR_SCOPE = "2026"
_CLEAR_EMERGENCY_STATE = EmergencyState(
    stop_new_orders=False,
    cancel_open_orders_requested=False,
    reason="offline_replay_clear",
    updated_at=datetime(1970, 1, 1, tzinfo=UTC),
)
_InputUnavailableReason = Literal[
    "insufficient_complete_regular_sessions",
    "invalid_catalog",
    "invalid_completed_session_input",
]
_ReplayStatus = Literal["complete", "no_rule_activation", "input_unavailable"]


@dataclass(frozen=True)
class EmaReplayMechanics:
    """Aggregate conformance evidence for the fixed EMA rule, without PnL."""

    decision_count: int
    warmup_abstain_count: int
    ready_hold_count: int
    eligible_enter_count: int
    eligible_exit_count: int
    forced_terminal_exit_count: int
    local_paper_fill_count: int
    replay_event_count: int
    all_fills_local_paper: bool
    all_terminal_flat: bool
    replay_digest: str


@dataclass(frozen=True)
class KisIntradayEmaReplayRun:
    """Source-safe immutable result for one EMA mechanics replay attempt."""

    run_label: str
    status: _ReplayStatus
    contract_hash: str
    precommit_path: Path
    summary_path: Path
    session_count: int
    ema: EmaReplayMechanics
    input_unavailable_reason: _InputUnavailableReason | None


@dataclass(frozen=True)
class KisIntradayEmaReplayReceipt:
    """Reattached immutable parent evidence for a completed EMA mechanics replay."""

    contract_hash: str
    precommit_path: Path
    summary_path: Path
    contract: dict[str, object]
    source_dataset_id: str
    source_dataset_hash: str
    selected_session_dates_sha256: str
    calendar_scope: str
    session_count: int
    mechanics: EmaReplayMechanics


@dataclass(frozen=True)
class EmaLocalPaperSessionReplay:
    """In-memory local-paper replay evidence for one completed session only."""

    mechanics: EmaReplayMechanics
    events: tuple[Event, ...]
    terminal_account: LocalPaperAccount


@dataclass(frozen=True)
class EmaLocalPaperReplay:
    """Exact fixed-rule replay retained in memory for a bounded downstream consumer."""

    mechanics: EmaReplayMechanics
    session_replays: tuple[EmaLocalPaperSessionReplay, ...]


class _InMemoryReplayEventStore:
    """Keep local-paper events replayable without retaining them as artifacts."""

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


class _CausalPrefixManifest:
    """Incrementally commit one contiguous completed-bar prefix in memory."""

    def __init__(self) -> None:
        self._digest = _sha256_json(
            {
                "schema_id": "kis-intraday-ema-m1-causal-prefix-v1",
                "contract_id": "kis-intraday-ema-m1-causal-source-v1",
            }
        )
        self._last_end: datetime | None = None

    def append(self, bar: Bar) -> str:
        if not bar.complete:
            raise ValueError("EMA causal prefix requires complete bars")
        if self._last_end is not None and bar.start_ts != self._last_end:
            raise ValueError("EMA causal prefix requires contiguous bars")
        self._digest = _sha256_json(
            {
                "previous": self._digest,
                "as_of": bar.end_ts.isoformat(),
                "bar": _bar_payload(bar),
            }
        )
        self._last_end = bar.end_ts
        return "sha256:" + self._digest


def load_kis_intraday_ema_replay_receipt(
    *,
    precommit_path: Path,
    summary_path: Path,
    repo_root: Path = _REPOSITORY_ROOT,
) -> KisIntradayEmaReplayReceipt:
    """Reattach one completed EMA mechanics receipt from external storage only."""

    precommit_file = _resolve_external_artifact_file(precommit_path, repo_root=repo_root)
    summary_file = _resolve_external_artifact_file(summary_path, repo_root=repo_root)
    if precommit_file.parent != summary_file.parent:
        raise ValueError("EMA replay receipt paths must share one run directory")
    precommit = _read_json_mapping(precommit_file, "EMA replay precommit")
    summary = _read_json_mapping(summary_file, "EMA replay summary")
    return _ema_replay_receipt_from_payloads(
        precommit=precommit,
        summary=summary,
        precommit_path=precommit_file,
        summary_path=summary_file,
    )


def replay_kis_intraday_session_reset_ema_local_paper(
    catalog: CatalogedBars,
    *,
    expected_contract_hash: str,
) -> EmaLocalPaperReplay:
    """Replay the frozen EMA semantics in memory without writing raw events."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("EMA local-paper replay requires CatalogedBars")
    _require_sha256_reference(expected_contract_hash, "expected EMA contract hash")
    _validate_source_catalog(catalog)
    session_dates = select_first_complete_kis_intraday_regular_session_dates(catalog)
    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=session_dates,
        campaign_id=KIS_INTRADAY_EMA_REPLAY_ID,
    )
    contract_hash = "sha256:" + _sha256_json(_contract_payload(plan))
    if contract_hash != expected_contract_hash:
        raise ValueError("EMA local-paper replay contract does not match its parent receipt")
    session_replays = tuple(
        _run_ema_local_paper_evidence(
            _session_bars(plan.cataloged_bars, session=session),
            session=session,
            contract_hash=contract_hash,
        )
        for session in plan.session_windows
    )
    mechanics = _sum_ema(item.mechanics for item in session_replays)
    if not mechanics.all_fills_local_paper or not mechanics.all_terminal_flat:
        raise RuntimeError("EMA local-paper replay must remain local-paper and terminal-flat")
    return EmaLocalPaperReplay(mechanics=mechanics, session_replays=session_replays)


def run_kis_intraday_session_reset_ema_replay(
    catalog: CatalogedBars,
    *,
    artifact_root: Path,
    run_label: str,
) -> KisIntradayEmaReplayRun:
    """Run one frozen source-local EMA mechanics replay with no external I/O."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("EMA replay requires CatalogedBars")
    _validate_run_label(run_label)
    root = _external_artifact_root(artifact_root)
    output_dir = root / "research" / KIS_INTRADAY_EMA_REPLAY_ID / run_label
    if output_dir.exists():
        raise FileExistsError(f"EMA replay artifact already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)

    try:
        _validate_source_catalog(catalog)
        session_dates = select_first_complete_kis_intraday_regular_session_dates(catalog)
        plan = build_kis_intraday_cpu_campaign_plan(
            catalog,
            session_dates=session_dates,
            campaign_id=KIS_INTRADAY_EMA_REPLAY_ID,
        )
    except ValueError as error:
        return _write_input_unavailable_run(
            catalog=catalog,
            root=root,
            output_dir=output_dir,
            run_label=run_label,
            reason=_input_unavailable_reason(error),
        )

    contract = _contract_payload(plan)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = output_dir / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_intraday_ema_replay_precommit",
            "status": "frozen_before_replay",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(root),
        },
    )

    ema = _sum_ema(
        _run_ema_local_paper(
            _session_bars(plan.cataloged_bars, session=session),
            session=session,
            contract_hash=contract_hash,
        )
        for session in plan.session_windows
    )
    if not ema.all_fills_local_paper or not ema.all_terminal_flat:
        raise RuntimeError("EMA replay mechanics must remain local-paper and terminal-flat")
    status: _ReplayStatus = "complete" if _rule_activated(ema) else "no_rule_activation"
    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            plan=plan,
            run_label=run_label,
            status=status,
            contract_hash=contract_hash,
            artifact_root=root,
            ema=ema,
            input_unavailable_reason=None,
        ),
    )
    return KisIntradayEmaReplayRun(
        run_label=run_label,
        status=status,
        contract_hash=contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=len(plan.session_dates),
        ema=ema,
        input_unavailable_reason=None,
    )


def _write_input_unavailable_run(
    *,
    catalog: CatalogedBars,
    root: Path,
    output_dir: Path,
    run_label: str,
    reason: _InputUnavailableReason,
) -> KisIntradayEmaReplayRun:
    contract = _input_unavailable_contract(catalog, reason=reason)
    contract_hash = "sha256:" + _sha256_json(contract)
    precommit_path = output_dir / "precommit.json"
    _write_json(
        precommit_path,
        {
            "schema_version": 1,
            "kind": "kis_intraday_ema_replay_precommit",
            "status": "frozen_input_unavailable",
            "run_label": run_label,
            "contract_hash": contract_hash,
            "contract": contract,
            "artifact_policy": _artifact_policy(root),
        },
    )
    ema = _empty_mechanics()
    summary_path = output_dir / "summary.json"
    _write_json(
        summary_path,
        _summary_payload(
            plan=None,
            catalog=catalog,
            run_label=run_label,
            status="input_unavailable",
            contract_hash=contract_hash,
            artifact_root=root,
            ema=ema,
            input_unavailable_reason=reason,
        ),
    )
    return KisIntradayEmaReplayRun(
        run_label=run_label,
        status="input_unavailable",
        contract_hash=contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        session_count=0,
        ema=ema,
        input_unavailable_reason=reason,
    )


def _run_ema_local_paper(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    contract_hash: str,
) -> EmaReplayMechanics:
    return _run_ema_local_paper_evidence(
        bars,
        session=session,
        contract_hash=contract_hash,
    ).mechanics


def _run_ema_local_paper_evidence(
    bars: Sequence[Bar],
    *,
    session: SessionWindow,
    contract_hash: str,
) -> EmaLocalPaperSessionReplay:
    if len(bars) < KIS_INTRADAY_EMA_SLOW_PERIOD + 2:
        raise ValueError("EMA replay session is shorter than its frozen warmup and exit")
    rule = SessionResetEmaStateRule(
        fast_period=KIS_INTRADAY_EMA_FAST_PERIOD,
        slow_period=KIS_INTRADAY_EMA_SLOW_PERIOD,
        tolerance=KIS_INTRADAY_EMA_TOLERANCE,
    )
    config = _target_config(bars)
    store, broker = _new_local_paper_broker()
    decision_count = 0
    warmup_abstain_count = 0
    ready_hold_count = 0
    eligible_enter_count = 0
    eligible_exit_count = 0
    forced_terminal_exit_count = 0
    manifest = _CausalPrefixManifest()

    terminal_signal = bars[-2]
    terminal_execution = bars[-1]
    for signal_index in range(len(bars) - 2):
        signal_bar = bars[signal_index]
        execution_bar = bars[signal_index + 1]
        current_quantity = broker.account().quantity(market=config.market, symbol=config.symbol)
        proposal = propose_session_reset_ema_state_target(
            bars[: signal_index + 1],
            session=session,
            as_of=signal_bar.end_ts,
            model_position="long" if current_quantity > 0 else "flat",
            rule=rule,
            config=config,
        )
        decision_count += 1
        if proposal.action == "abstain":
            warmup_abstain_count += 1
        elif proposal.action == "hold":
            ready_hold_count += 1
        elif proposal.action == "enter":
            eligible_enter_count += 1
        elif proposal.action == "exit":
            eligible_exit_count += 1
        _submit_target_proposal(
            proposal,
            broker=broker,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
            contract_hash=contract_hash,
            input_manifest_ref=manifest.append(signal_bar),
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
            input_manifest_ref=manifest.append(terminal_signal),
        )
    mechanics = _ema_mechanics(
        store,
        broker,
        decision_count=decision_count,
        warmup_abstain_count=warmup_abstain_count,
        ready_hold_count=ready_hold_count,
        eligible_enter_count=eligible_enter_count,
        eligible_exit_count=eligible_exit_count,
        forced_terminal_exit_count=forced_terminal_exit_count,
    )
    return EmaLocalPaperSessionReplay(
        mechanics=mechanics,
        events=store.iter_events(),
        terminal_account=broker.account(),
    )


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
                str(KIS_INTRADAY_EMA_FAST_PERIOD),
                str(KIS_INTRADAY_EMA_SLOW_PERIOD),
                str(KIS_INTRADAY_EMA_TOLERANCE),
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
            maximum_quantity=KIS_INTRADAY_EMA_MAXIMUM_QUANTITY,
        ),
        as_of=proposal.decided_at,
    )
    if bridge.route != "local_paper":
        raise RuntimeError("EMA mechanics replay must remain local-paper-only")
    if proposal.action in {"enter", "exit"} and bridge.status != "ready":
        raise RuntimeError("eligible EMA proposal did not prepare a local-paper intent")
    if proposal.action not in {"enter", "exit"} and bridge.status != "no_intent":
        raise RuntimeError("non-action EMA proposal unexpectedly prepared a local-paper intent")
    if bridge.status == "ready":
        if bridge.local_paper_intent is None:
            raise RuntimeError("ready local-paper bridge omitted an intent")
        execution = broker.submit_and_fill_next_bar(
            bridge.local_paper_intent,
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )
        if execution.fill is None or execution.fill.source != LOCAL_PAPER_SOURCE:
            raise RuntimeError("EMA mechanics replay intent did not create one local-paper fill")
    return bridge


def _terminal_flatten_proposal(
    *,
    config: SessionResetEmaStateTargetConfig,
    contract_hash: str,
    signal_bar: Bar,
    execution_bar: Bar,
) -> TargetExposureProposal:
    return TargetExposureProposal(
        proposal_id=(
            "session-reset-ema-state-terminal-flat-v1:sha256:"
            + _sha256_json([contract_hash, signal_bar.end_ts.isoformat()])
        ),
        symbol=config.symbol,
        market=config.market,
        action="exit",
        target_exposure=Decimal("0"),
        confidence=Decimal("1"),
        feature_schema_id=SESSION_RESET_EMA_STATE_TARGET_FEATURE_SCHEMA_ID,
        input_status="ready",
        decided_at=signal_bar.end_ts,
        valid_until=execution_bar.end_ts,
        feature_window_end=signal_bar.end_ts,
        reason="predeclared_terminal_flat",
    )


def _target_config(bars: Sequence[Bar]) -> SessionResetEmaStateTargetConfig:
    if not bars:
        raise ValueError("EMA replay session has no bars")
    first = bars[0]
    return SessionResetEmaStateTargetConfig(
        symbol=first.symbol,
        market=first.market,
        timeframe=first.timeframe,
        target_exposure=KIS_INTRADAY_EMA_TARGET_EXPOSURE,
        confidence=KIS_INTRADAY_EMA_CONFIDENCE,
        decision_ttl=KIS_INTRADAY_EMA_DECISION_TTL,
    )


def _causal_input_manifest_ref(bars: Sequence[Bar], *, as_of: datetime) -> str:
    prefix = sorted((bar for bar in bars if bar.end_ts <= as_of), key=lambda bar: bar.start_ts)
    if not prefix:
        raise ValueError("EMA causal input manifest requires one completed bar")
    manifest = _CausalPrefixManifest()
    for bar in prefix:
        reference = manifest.append(bar)
    return reference


def _new_local_paper_broker() -> tuple[_InMemoryReplayEventStore, LocalPaperBroker]:
    store = _InMemoryReplayEventStore()
    return (
        store,
        LocalPaperBroker(
            event_store=store,  # type: ignore[arg-type]
            emergency_store=_ClearEmergencyStore(),  # type: ignore[arg-type]
            starting_cash=KIS_INTRADAY_EMA_STARTING_CASH,
            fee_bps=KIS_INTRADAY_EMA_FEE_BPS,
            slippage_bps=KIS_INTRADAY_EMA_SLIPPAGE_BPS,
        ),
    )


def _ema_mechanics(
    store: _InMemoryReplayEventStore,
    broker: LocalPaperBroker,
    *,
    decision_count: int,
    warmup_abstain_count: int,
    ready_hold_count: int,
    eligible_enter_count: int,
    eligible_exit_count: int,
    forced_terminal_exit_count: int,
) -> EmaReplayMechanics:
    account = broker.account()
    replayed = replay_local_paper_account(
        store,  # type: ignore[arg-type]
        starting_cash=KIS_INTRADAY_EMA_STARTING_CASH,
    )
    if account != replayed:
        raise RuntimeError("local-paper account did not match its replay")
    events = store.iter_events()
    fill_events = tuple(event for event in events if event.event_type == "fill")
    return EmaReplayMechanics(
        decision_count=decision_count,
        warmup_abstain_count=warmup_abstain_count,
        ready_hold_count=ready_hold_count,
        eligible_enter_count=eligible_enter_count,
        eligible_exit_count=eligible_exit_count,
        forced_terminal_exit_count=forced_terminal_exit_count,
        local_paper_fill_count=len(fill_events),
        replay_event_count=len(events),
        all_fills_local_paper=all(
            event.payload.get("source") == LOCAL_PAPER_SOURCE for event in fill_events
        ),
        all_terminal_flat=account.positions == (),
        replay_digest=_event_digest(events),
    )


def _sum_ema(items: Iterable[EmaReplayMechanics]) -> EmaReplayMechanics:
    records = tuple(items)
    return EmaReplayMechanics(
        decision_count=sum(item.decision_count for item in records),
        warmup_abstain_count=sum(item.warmup_abstain_count for item in records),
        ready_hold_count=sum(item.ready_hold_count for item in records),
        eligible_enter_count=sum(item.eligible_enter_count for item in records),
        eligible_exit_count=sum(item.eligible_exit_count for item in records),
        forced_terminal_exit_count=sum(item.forced_terminal_exit_count for item in records),
        local_paper_fill_count=sum(item.local_paper_fill_count for item in records),
        replay_event_count=sum(item.replay_event_count for item in records),
        all_fills_local_paper=all(item.all_fills_local_paper for item in records),
        all_terminal_flat=all(item.all_terminal_flat for item in records),
        replay_digest="sha256:" + _sha256_json([item.replay_digest for item in records]),
    )


def _empty_mechanics() -> EmaReplayMechanics:
    return EmaReplayMechanics(
        decision_count=0,
        warmup_abstain_count=0,
        ready_hold_count=0,
        eligible_enter_count=0,
        eligible_exit_count=0,
        forced_terminal_exit_count=0,
        local_paper_fill_count=0,
        replay_event_count=0,
        all_fills_local_paper=True,
        all_terminal_flat=True,
        replay_digest="sha256:" + _sha256_json([]),
    )


def _contract_payload(plan: KisIntradayCpuCampaignPlan) -> dict[str, object]:
    selection_dates = [item.isoformat() for item in plan.session_dates]
    return {
        "schema_version": 1,
        "replay_id": KIS_INTRADAY_EMA_REPLAY_ID,
        "source": {
            "dataset_id": plan.cataloged_bars.dataset_id,
            "dataset_hash": plan.cataloged_bars.dataset_hash,
            "session_count": len(plan.session_dates),
            "selection": "first_20_complete_regular_sessions_ascending_within_2026_scope",
            "calendar_scope": _SELECTION_CALENDAR_SCOPE,
            "complete_session_predicate": "verified_contiguous_regular_390_m1_bars",
            "selected_session_dates_sha256": "sha256:" + _sha256_json(selection_dates),
        },
        "rule": {
            "id": "session-reset-ema-state-v1",
            "fast_period": KIS_INTRADAY_EMA_FAST_PERIOD,
            "slow_period": KIS_INTRADAY_EMA_SLOW_PERIOD,
            "tolerance": str(KIS_INTRADAY_EMA_TOLERANCE),
            "seed_policy": "within_session_sma_seed_then_decimal_ema_v1",
            "session_local_warmup_bars": KIS_INTRADAY_EMA_SLOW_PERIOD,
        },
        "execution": {
            "decision": "completed_1m_bar_end",
            "entry_exit": "next_completed_1m_bar_open",
            "terminal_exit": "predeclared_penultimate_bar_decision_final_bar_open_fill",
            "target_exposure": str(KIS_INTRADAY_EMA_TARGET_EXPOSURE),
            "maximum_quantity": str(KIS_INTRADAY_EMA_MAXIMUM_QUANTITY),
            "fee_bps": str(KIS_INTRADAY_EMA_FEE_BPS),
            "slippage_bps": str(KIS_INTRADAY_EMA_SLIPPAGE_BPS),
        },
        "limits": _limits_payload(),
    }


def _input_unavailable_contract(
    catalog: CatalogedBars,
    *,
    reason: _InputUnavailableReason,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "replay_id": KIS_INTRADAY_EMA_REPLAY_ID,
        "source": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "session_count": 0,
            "selection": "first_20_complete_regular_sessions_ascending_within_2026_scope",
            "calendar_scope": _SELECTION_CALENDAR_SCOPE,
            "complete_session_predicate": "verified_contiguous_regular_390_m1_bars",
            "selected_session_dates_sha256": None,
        },
        "rule": {
            "id": "session-reset-ema-state-v1",
            "fast_period": KIS_INTRADAY_EMA_FAST_PERIOD,
            "slow_period": KIS_INTRADAY_EMA_SLOW_PERIOD,
            "tolerance": str(KIS_INTRADAY_EMA_TOLERANCE),
            "seed_policy": "within_session_sma_seed_then_decimal_ema_v1",
            "session_local_warmup_bars": KIS_INTRADAY_EMA_SLOW_PERIOD,
        },
        "input_unavailable_reason": reason,
        "limits": _limits_payload(),
    }


def _summary_payload(
    *,
    plan: KisIntradayCpuCampaignPlan | None,
    catalog: CatalogedBars | None = None,
    run_label: str,
    status: _ReplayStatus,
    contract_hash: str,
    artifact_root: Path,
    ema: EmaReplayMechanics,
    input_unavailable_reason: _InputUnavailableReason | None,
) -> dict[str, object]:
    source = plan.cataloged_bars if plan is not None else catalog
    if source is None:
        raise ValueError("EMA replay summary requires a source catalog")
    return {
        "schema_version": 1,
        "kind": "kis_intraday_ema_replay_summary",
        "status": status,
        "mode": "offline_local_cache_local_paper_only",
        "run_label": run_label,
        "contract_hash": contract_hash,
        "source": {
            "dataset_id": source.dataset_id,
            "dataset_hash": source.dataset_hash,
            "session_count": len(plan.session_dates) if plan is not None else 0,
        },
        "mechanics": _ema_payload(ema),
        "input_unavailable_reason": input_unavailable_reason,
        "limits": _limits_payload(),
        "artifact_policy": _artifact_policy(artifact_root),
        "claim": _claim_for_status(status),
    }


def _ema_payload(value: EmaReplayMechanics) -> dict[str, object]:
    return {
        "decision_count": value.decision_count,
        "warmup_abstain_count": value.warmup_abstain_count,
        "ready_hold_count": value.ready_hold_count,
        "eligible_enter_count": value.eligible_enter_count,
        "eligible_exit_count": value.eligible_exit_count,
        "forced_terminal_exit_count": value.forced_terminal_exit_count,
        "local_paper_fill_count": value.local_paper_fill_count,
        "event_replay_count": value.replay_event_count,
        "all_fills_local_paper": value.all_fills_local_paper,
        "all_terminal_flat": value.all_terminal_flat,
        "rule_activated": _rule_activated(value),
        "event_replay_digest": value.replay_digest,
    }


def _limits_payload() -> dict[str, object]:
    return {
        "decision_time_availability": "not_observed",
        "performance_metrics_retained": False,
        "post_outcome_tuning_allowed": False,
        "promotion_allowed": False,
        "paper_input_allowed": False,
        "gpu_eligible": False,
    }


def _artifact_policy(artifact_root: Path) -> dict[str, object]:
    return {
        "root": str(artifact_root),
        "repo_storage_allowed": False,
        "raw_market_data_written": False,
        "raw_price_values_retained": False,
        "raw_fill_events_retained": False,
        "credential_read": False,
        "network_called": False,
        "external_broker_called": False,
    }


def _claim_for_status(status: _ReplayStatus) -> str:
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
    if status == "input_unavailable":
        return (
            "source-local input was unavailable before replay; this record makes no "
            "mechanics, profitability, model, ensemble, evaluation, or Paper-input claim"
        )
    raise ValueError(f"unsupported EMA replay status: {status}")


def _ema_replay_receipt_from_payloads(
    *,
    precommit: Mapping[str, object],
    summary: Mapping[str, object],
    precommit_path: Path,
    summary_path: Path,
) -> KisIntradayEmaReplayReceipt:
    if set(precommit) != {
        "schema_version",
        "kind",
        "status",
        "run_label",
        "contract_hash",
        "contract",
        "artifact_policy",
    }:
        raise ValueError("EMA replay precommit shape is invalid")
    if set(summary) != {
        "schema_version",
        "kind",
        "status",
        "mode",
        "run_label",
        "contract_hash",
        "source",
        "mechanics",
        "input_unavailable_reason",
        "limits",
        "artifact_policy",
        "claim",
    }:
        raise ValueError("EMA replay summary shape is invalid")
    contract = _mapping(precommit.get("contract"), "EMA replay contract")
    contract_hash = _text(precommit.get("contract_hash"), "EMA replay contract hash")
    _require_sha256_reference(contract_hash, "EMA replay contract hash")
    if (
        precommit.get("schema_version") != 1
        or precommit.get("kind") != "kis_intraday_ema_replay_precommit"
        or precommit.get("status") != "frozen_before_replay"
        or not _text(precommit.get("run_label"), "EMA replay run label")
        or contract_hash != "sha256:" + _sha256_json(contract)
    ):
        raise ValueError("EMA replay precommit is invalid")
    _validate_parent_contract(contract)
    _validate_parent_artifact_policy(
        _mapping(precommit.get("artifact_policy"), "EMA replay precommit artifact policy")
    )
    if (
        summary.get("schema_version") != 1
        or summary.get("kind") != "kis_intraday_ema_replay_summary"
        or summary.get("status") != "complete"
        or summary.get("mode") != "offline_local_cache_local_paper_only"
        or summary.get("run_label") != precommit.get("run_label")
        or summary.get("contract_hash") != contract_hash
        or summary.get("input_unavailable_reason") is not None
        or summary.get("limits") != _limits_payload()
        or not _text(summary.get("claim"), "EMA replay summary claim")
    ):
        raise ValueError("EMA replay summary is invalid")
    _validate_parent_artifact_policy(
        _mapping(summary.get("artifact_policy"), "EMA replay summary artifact policy")
    )
    source = _mapping(contract.get("source"), "EMA replay source contract")
    summary_source = _mapping(summary.get("source"), "EMA replay summary source")
    source_dataset_id = _text(source.get("dataset_id"), "EMA replay dataset id")
    source_dataset_hash = _text(source.get("dataset_hash"), "EMA replay dataset hash")
    selected_session_dates_sha256 = _text(
        source.get("selected_session_dates_sha256"),
        "EMA replay selected session dates hash",
    )
    _require_sha256_reference(source_dataset_hash, "EMA replay dataset hash")
    _require_sha256_reference(
        selected_session_dates_sha256,
        "EMA replay selected session dates hash",
    )
    session_count = _non_negative_int(source.get("session_count"), "EMA replay session count")
    calendar_scope = _text(source.get("calendar_scope"), "EMA replay calendar scope")
    if (
        session_count != 20
        or calendar_scope != _SELECTION_CALENDAR_SCOPE
        or summary_source
        != {
            "dataset_id": source_dataset_id,
            "dataset_hash": source_dataset_hash,
            "session_count": session_count,
        }
    ):
        raise ValueError("EMA replay source binding is invalid")
    mechanics = _ema_mechanics_from_payload(_mapping(summary.get("mechanics"), "EMA mechanics"))
    if not (
        mechanics.all_fills_local_paper
        and mechanics.all_terminal_flat
        and _rule_activated(mechanics)
    ):
        raise ValueError("EMA replay parent mechanics are not complete local-paper evidence")
    return KisIntradayEmaReplayReceipt(
        contract_hash=contract_hash,
        precommit_path=precommit_path,
        summary_path=summary_path,
        contract=dict(contract),
        source_dataset_id=source_dataset_id,
        source_dataset_hash=source_dataset_hash,
        selected_session_dates_sha256=selected_session_dates_sha256,
        calendar_scope=calendar_scope,
        session_count=session_count,
        mechanics=mechanics,
    )


def _validate_parent_contract(contract: Mapping[str, object]) -> None:
    if set(contract) != {"schema_version", "replay_id", "source", "rule", "execution", "limits"}:
        raise ValueError("EMA replay contract shape is invalid")
    source = _mapping(contract.get("source"), "EMA replay source contract")
    rule = _mapping(contract.get("rule"), "EMA replay rule contract")
    execution = _mapping(contract.get("execution"), "EMA replay execution contract")
    if (
        contract.get("schema_version") != 1
        or contract.get("replay_id") != KIS_INTRADAY_EMA_REPLAY_ID
        or source.get("selection")
        != "first_20_complete_regular_sessions_ascending_within_2026_scope"
        or source.get("complete_session_predicate")
        != "verified_contiguous_regular_390_m1_bars"
        or rule
        != {
            "id": "session-reset-ema-state-v1",
            "fast_period": KIS_INTRADAY_EMA_FAST_PERIOD,
            "slow_period": KIS_INTRADAY_EMA_SLOW_PERIOD,
            "tolerance": str(KIS_INTRADAY_EMA_TOLERANCE),
            "seed_policy": "within_session_sma_seed_then_decimal_ema_v1",
            "session_local_warmup_bars": KIS_INTRADAY_EMA_SLOW_PERIOD,
        }
        or execution
        != {
            "decision": "completed_1m_bar_end",
            "entry_exit": "next_completed_1m_bar_open",
            "terminal_exit": "predeclared_penultimate_bar_decision_final_bar_open_fill",
            "target_exposure": str(KIS_INTRADAY_EMA_TARGET_EXPOSURE),
            "maximum_quantity": str(KIS_INTRADAY_EMA_MAXIMUM_QUANTITY),
            "fee_bps": str(KIS_INTRADAY_EMA_FEE_BPS),
            "slippage_bps": str(KIS_INTRADAY_EMA_SLIPPAGE_BPS),
        }
        or contract.get("limits") != _limits_payload()
    ):
        raise ValueError("EMA replay contract semantics are invalid")


def _ema_mechanics_from_payload(payload: Mapping[str, object]) -> EmaReplayMechanics:
    if set(payload) != {
        "decision_count",
        "warmup_abstain_count",
        "ready_hold_count",
        "eligible_enter_count",
        "eligible_exit_count",
        "forced_terminal_exit_count",
        "local_paper_fill_count",
        "event_replay_count",
        "all_fills_local_paper",
        "all_terminal_flat",
        "rule_activated",
        "event_replay_digest",
    }:
        raise ValueError("EMA replay mechanics shape is invalid")
    mechanics = EmaReplayMechanics(
        decision_count=_non_negative_int(payload.get("decision_count"), "EMA decision count"),
        warmup_abstain_count=_non_negative_int(
            payload.get("warmup_abstain_count"),
            "EMA warmup abstain count",
        ),
        ready_hold_count=_non_negative_int(payload.get("ready_hold_count"), "EMA ready hold count"),
        eligible_enter_count=_non_negative_int(
            payload.get("eligible_enter_count"),
            "EMA eligible enter count",
        ),
        eligible_exit_count=_non_negative_int(
            payload.get("eligible_exit_count"),
            "EMA eligible exit count",
        ),
        forced_terminal_exit_count=_non_negative_int(
            payload.get("forced_terminal_exit_count"),
            "EMA terminal exit count",
        ),
        local_paper_fill_count=_non_negative_int(
            payload.get("local_paper_fill_count"),
            "EMA local-paper fill count",
        ),
        replay_event_count=_non_negative_int(
            payload.get("event_replay_count"),
            "EMA event replay count",
        ),
        all_fills_local_paper=_bool(payload.get("all_fills_local_paper"), "EMA local-paper flag"),
        all_terminal_flat=_bool(payload.get("all_terminal_flat"), "EMA terminal-flat flag"),
        replay_digest=_text(payload.get("event_replay_digest"), "EMA replay digest"),
    )
    _require_sha256_reference(mechanics.replay_digest, "EMA replay digest")
    if payload.get("rule_activated") is not _rule_activated(mechanics):
        raise ValueError("EMA replay rule activation is inconsistent")
    return mechanics


def _validate_parent_artifact_policy(policy: Mapping[str, object]) -> None:
    if (
        set(policy)
        != {
            "root",
            "repo_storage_allowed",
            "raw_market_data_written",
            "raw_price_values_retained",
            "raw_fill_events_retained",
            "credential_read",
            "network_called",
            "external_broker_called",
        }
        or not _text(policy.get("root"), "EMA replay artifact root")
        or any(
            policy.get(field) is not False
            for field in (
                "repo_storage_allowed",
                "raw_market_data_written",
                "raw_price_values_retained",
                "raw_fill_events_retained",
                "credential_read",
                "network_called",
                "external_broker_called",
            )
        )
    ):
        raise ValueError("EMA replay artifact policy is invalid")


def _resolve_external_artifact_file(path: Path, *, repo_root: Path) -> Path:
    candidate = Path(path).absolute()
    if (
        _has_existing_symlink_component(candidate)
        or candidate.is_symlink()
        or not candidate.is_file()
    ):
        raise ValueError("EMA replay parent artifact must be a non-symlink file")
    resolved = candidate.resolve(strict=True)
    resolved_repo = Path(repo_root).resolve(strict=False)
    if resolved == resolved_repo or resolved.is_relative_to(resolved_repo):
        raise ValueError("EMA replay parent artifact must stay outside the Git workspace")
    return resolved


def _has_existing_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if not current.exists():
            return False
        if current.is_symlink():
            return True
    return False


def _read_json_mapping(path: Path, label: str) -> Mapping[str, object]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable") from error
    return _mapping(decoded, label)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a string-keyed mapping")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _require_sha256_reference(value: str, label: str) -> None:
    if _SHA256_REFERENCE.fullmatch(value) is None:
        raise ValueError(f"{label} must use sha256:<64 lowercase hex> format")


def _validate_source_catalog(catalog: CatalogedBars) -> None:
    if not catalog.dataset_id.startswith(_REQUIRED_DATASET_ID_PREFIX):
        raise ValueError("EMA replay requires the KIS private QQQ/NAS M1 catalog")
    if any(
        bar.symbol != "QQQ" or bar.market != "US" or bar.timeframe.value != "1m"
        for bar in catalog.bars
    ):
        raise ValueError("EMA replay requires the QQQ/US M1 bars loaded from NAS")


def _input_unavailable_reason(error: ValueError) -> _InputUnavailableReason:
    message = str(error)
    if "twenty complete regular KIS M1 sessions" in message:
        return "insufficient_complete_regular_sessions"
    if message in {
        "EMA replay requires the KIS private QQQ/NAS M1 catalog",
        "EMA replay requires the QQQ/US M1 bars loaded from NAS",
    }:
        return "invalid_catalog"
    return "invalid_completed_session_input"


def _session_bars(catalog: CatalogedBars, *, session: SessionWindow) -> tuple[Bar, ...]:
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.open_ts and bar.end_ts <= session.close_ts
    )
    if not bars:
        raise ValueError("EMA replay session has no bars")
    if any(not bar.complete for bar in bars):
        raise ValueError("EMA replay session has incomplete bars")
    return bars


def _opaque_reference(*parts: str) -> str:
    return "ref:" + _sha256_json(list(parts))


def _event_digest(events: Sequence[Event]) -> str:
    return "sha256:" + _sha256_json([event.to_record() for event in events])


def _bar_payload(bar: Bar) -> dict[str, str]:
    return {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": bar.start_ts.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": str(bar.complete).lower(),
    }


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rule_activated(value: EmaReplayMechanics) -> bool:
    return value.eligible_enter_count + value.eligible_exit_count > 0


def _external_artifact_root(artifact_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    if root == _REPOSITORY_ROOT or root.is_relative_to(_REPOSITORY_ROOT):
        raise ValueError("artifact root must stay outside the Git workspace")
    return root


def _validate_run_label(value: str) -> None:
    if _SAFE_RUN_LABEL.fullmatch(value) is None:
        raise ValueError("run_label must use 1-80 ASCII letters, digits, '.', '_' or '-'")

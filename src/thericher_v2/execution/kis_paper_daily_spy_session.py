"""Run one receipt-backed KIS Paper SPY daily decision session.

By default, the daily cache and model decision are evaluated offline before
this module loads Paper configuration or touches KIS. The opt-in budget trial
delegates recovery before loading a new receipt. A missing, stale, or abstaining
receipt is scoped evidence for this session, not an approval state or a hold
on another Paper action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_daily import KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT
from thericher_v2.data.kis_paper_daily_spy_input import (
    KIS_PAPER_DAILY_SPY_AVAILABILITY_ROOT,
    KisPaperDailySpyInput,
    attest_kis_paper_daily_spy_bars,
    load_kis_paper_daily_spy_input,
)
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt
from thericher_v2.research.kis_paper_daily_spy_baseline import (
    KisPaperDailySpyBaselineEvaluation,
    evaluate_kis_paper_daily_spy_baseline,
)

from .emergency import DEFAULT_PAPER_EXECUTION_CONTROL_STATE, PaperExecutionControlStore
from .kis_paper_canary import (
    DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryOutcome,
    UrllibKisPaperCanaryTransport,
)
from .kis_paper_daily_spy_head import (
    KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    load_verified_kis_paper_daily_spy_head,
)
from .kis_paper_receipt_canary import (
    prepare_kis_paper_spy_receipt_decision,
    receipt_canary_run_id,
    run_kis_paper_receipt_canary,
)
from .kis_paper_receipt_observer import (
    KisPaperReceiptObservation,
    observe_kis_paper_receipt,
)
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_paper_spy_position import (
    KisPaperSpyPositionResolution,
    resolve_kis_paper_spy_position_target,
)
from .kis_paper_terminal_field_probe import (
    KisPaperTerminalFieldProbeOutcome,
    probe_kis_paper_terminal_fields,
)
from .kis_readonly import (
    KisHttpTransport,
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)
from .paper_decision_bridge import PaperDecisionBridgeResult

if TYPE_CHECKING:
    from .kis_paper_budget_strategy import KisPaperBudgetOutcome

KIS_PAPER_DAILY_SPY_SESSION_EVIDENCE_KIND = "kis_paper_daily_spy_session_evidence"
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}", re.ASCII)
_SESSION_STATUSES = frozenset({"preview", "no_intent", "canary_completed"})
_OBSERVER_STATUSES = frozenset({"not_attempted", "completed", "unavailable"})
_OBSERVER_UNAVAILABLE_REASON = "observer_unavailable"
_TERMINAL_FIELD_PROBE_STATUSES = frozenset({"not_attempted", "completed", "unavailable"})
_TERMINAL_FIELD_PROBE_UNAVAILABLE_REASON = "terminal_field_probe_unavailable"
_SESSION_REASONS = frozenset(
    {
        "preview",
        "daily_input_unavailable",
        "daily_receipt_abstain",
        "daily_receipt_not_current",
        "session_closed",
        "pause_buys_active",
        "pause_sells_active",
        "account_unavailable",
        "account_snapshot_not_current",
        "position_out_of_scope",
        "open_order_conflict",
        "target_already_satisfied",
        "target_bridge_mismatch",
        "quote_unavailable",
        "receipt_preparation_unavailable",
    }
)


@dataclass(frozen=True)
class KisPaperDailySpySessionOutcome:
    """Safe outcome of one cache-to-receipt-to-virtual-Paper attempt."""

    session_id: str
    status: Literal["preview", "no_intent", "canary_completed"]
    reason_code: str
    observed_at: datetime
    evidence_path: Path
    receipt_ref: str | None = None
    input_manifest_ref: str | None = None
    run_id: str | None = None
    canary_phase: str | None = None
    canary_reason_code: str | None = None
    observer_status: Literal["not_attempted", "completed", "unavailable"] = "not_attempted"
    observer_reason_code: str | None = None
    observation: KisPaperReceiptObservation | None = None
    terminal_field_probe_status: Literal["not_attempted", "completed", "unavailable"] = (
        "not_attempted"
    )
    terminal_field_probe_reason_code: str | None = None
    terminal_field_probe: KisPaperTerminalFieldProbeOutcome | None = None
    terminal_field_probe_artifact_ref: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.session_id) is None:
            raise ValueError("daily SPY session id is invalid")
        if self.status not in _SESSION_STATUSES:
            raise ValueError("daily SPY session status is invalid")
        if self.status != "canary_completed" and self.reason_code not in _SESSION_REASONS:
            raise ValueError("daily SPY session reason is invalid")
        if self.status == "canary_completed" and _SAFE_REASON.fullmatch(self.reason_code) is None:
            raise ValueError("daily SPY canary reason is invalid")
        if self.receipt_ref is not None and not _is_sha256_reference(self.receipt_ref):
            raise ValueError("daily SPY receipt reference is invalid")
        if (
            self.input_manifest_ref is not None
            and not _is_sha256_reference(self.input_manifest_ref)
        ):
            raise ValueError("daily SPY input manifest reference is invalid")
        if self.run_id is not None and _SAFE_ID.fullmatch(self.run_id) is None:
            raise ValueError("daily SPY run id is invalid")
        if self.receipt_ref is not None and self.run_id is not None:
            expected_run_id = "receipt-" + self.receipt_ref.removeprefix("sha256:")
            if self.run_id != expected_run_id:
                raise ValueError("daily SPY receipt and run identity are inconsistent")
        if self.canary_phase is not None and _SAFE_REASON.fullmatch(self.canary_phase) is None:
            raise ValueError("daily SPY canary phase is invalid")
        if self.canary_reason_code is not None and _SAFE_REASON.fullmatch(
            self.canary_reason_code
        ) is None:
            raise ValueError("daily SPY canary reason is invalid")
        if self.observer_status not in _OBSERVER_STATUSES:
            raise ValueError("daily SPY observer status is invalid")
        if self.observer_reason_code is not None and _SAFE_REASON.fullmatch(
            self.observer_reason_code
        ) is None:
            raise ValueError("daily SPY observer reason is invalid")
        if self.observation is not None:
            if self.observer_status != "completed":
                raise ValueError("daily SPY observer outcome is inconsistent")
            if self.run_id is None or self.observation.run_id != self.run_id:
                raise ValueError("daily SPY observer run identity is inconsistent")
            if self.receipt_ref != self.observation.receipt_ref:
                raise ValueError("daily SPY observer receipt identity is inconsistent")
        elif self.observer_status == "completed":
            raise ValueError("daily SPY observer outcome is missing")
        if (
            self.observer_status == "unavailable"
            and self.observer_reason_code != _OBSERVER_UNAVAILABLE_REASON
        ):
            raise ValueError("daily SPY observer unavailable reason is invalid")
        if self.observer_status != "unavailable" and self.observer_reason_code is not None:
            raise ValueError("daily SPY observer reason is inconsistent")
        if self.terminal_field_probe_status not in _TERMINAL_FIELD_PROBE_STATUSES:
            raise ValueError("daily SPY terminal field probe status is invalid")
        if (
            self.terminal_field_probe_reason_code is not None
            and _SAFE_REASON.fullmatch(self.terminal_field_probe_reason_code) is None
        ):
            raise ValueError("daily SPY terminal field probe reason is invalid")
        if self.terminal_field_probe is not None:
            if self.terminal_field_probe_status != "completed":
                raise ValueError("daily SPY terminal field probe outcome is inconsistent")
            if self.run_id is None or self.terminal_field_probe.run_ref != _terminal_probe_run_ref(
                self.run_id
            ):
                raise ValueError("daily SPY terminal field probe run identity is inconsistent")
            if (
                self.terminal_field_probe_artifact_ref is None
                or not _is_sha256_reference(self.terminal_field_probe_artifact_ref)
            ):
                raise ValueError("daily SPY terminal field probe artifact reference is invalid")
        else:
            if self.terminal_field_probe_status == "completed":
                raise ValueError("daily SPY terminal field probe outcome is missing")
            if self.terminal_field_probe_artifact_ref is not None:
                raise ValueError("daily SPY terminal field probe artifact is inconsistent")
        if (
            self.terminal_field_probe_status == "unavailable"
            and self.terminal_field_probe_reason_code != _TERMINAL_FIELD_PROBE_UNAVAILABLE_REASON
        ):
            raise ValueError("daily SPY terminal field probe unavailable reason is invalid")
        if (
            self.terminal_field_probe_status != "unavailable"
            and self.terminal_field_probe_reason_code is not None
        ):
            raise ValueError("daily SPY terminal field probe reason is inconsistent")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_spy_session_outcome",
            "session_id": self.session_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": _utc_marker(self.observed_at),
            "receipt_ref": self.receipt_ref,
            "input_manifest_ref": self.input_manifest_ref,
            "run_id": self.run_id,
            "canary_phase": self.canary_phase,
            "canary_reason_code": self.canary_reason_code,
            "observer_status": self.observer_status,
            "observer_reason_code": self.observer_reason_code,
            "observation": None if self.observation is None else self.observation.safe_payload(),
            "terminal_field_probe_status": self.terminal_field_probe_status,
            "terminal_field_probe_reason_code": self.terminal_field_probe_reason_code,
            "terminal_field_probe": (
                None
                if self.terminal_field_probe is None
                else self.terminal_field_probe.safe_payload()
            ),
            "terminal_field_probe_artifact_ref": self.terminal_field_probe_artifact_ref,
            "paper_only": True,
        }


def run_kis_paper_daily_spy_session(
    *,
    environment: Mapping[str, str],
    cache_root: Path,
    head_cache_root: Path = KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    availability_root: Path,
    state_root: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    session_id: str | None = None,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    budget_trial: bool = False,
) -> KisPaperDailySpySessionOutcome | KisPaperBudgetOutcome:
    """Evaluate one SPY D1 receipt and execute only its eligible Paper intent."""

    if budget_trial and cancel_after_submit:
        raise ValueError("budget_trial and cancel_after_submit are mutually exclusive")

    observed_at = _session_now(now=now, clock=clock)
    resolved_session_id = session_id or f"daily-spy-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    if _SAFE_ID.fullmatch(resolved_session_id) is None:
        raise ValueError("daily SPY session id is invalid")

    if budget_trial:
        from .kis_paper_budget_strategy import run_kis_paper_budget_strategy

        def receipt_loader(as_of: datetime) -> ResearchDecisionReceipt:
            input = _load_preferred_daily_spy_input(
                cache_root=cache_root,
                head_cache_root=head_cache_root,
                availability_root=availability_root,
                repository_root=repository_root,
                attested_at=as_of,
            )
            return evaluate_kis_paper_daily_spy_baseline(input, as_of=as_of).receipt

        return run_kis_paper_budget_strategy(
            environment=environment,
            state_root=state_root,
            runtime_projection_path=runtime_projection_path,
            paper_account_snapshot_path=paper_account_snapshot_path,
            emergency_state_path=emergency_state_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=execute,
            transport=transport,
            client=client,
            now=now,
            clock=clock,
            execution_control_path=execution_control_path,
            receipt_loader=receipt_loader,
            session_id=resolved_session_id,
        )

    try:
        input = _load_preferred_daily_spy_input(
            cache_root=cache_root,
            head_cache_root=head_cache_root,
            availability_root=availability_root,
            repository_root=repository_root,
            attested_at=observed_at,
        )
    except (OSError, ValueError):
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent" if execute else "preview",
            reason_code="daily_input_unavailable" if execute else "preview",
            observed_at=observed_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )

    decision_at = _session_now(now=now, clock=clock)
    evaluation = evaluate_kis_paper_daily_spy_baseline(input, as_of=decision_at)
    receipt = evaluation.receipt
    if not execute:
        return _record_session(
            session_id=resolved_session_id,
            status="preview",
            reason_code="preview",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
        )
    if receipt.decision_class not in {"enter", "exit"}:
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=(
                "daily_receipt_not_current"
                if receipt.input_status in {"future", "stale"}
                else "daily_receipt_abstain"
            ),
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
        )
    if not is_us_equity_regular_session_window(decision_at):
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="session_closed",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
        )
    execution_control = PaperExecutionControlStore(execution_control_path).read()
    paused = (
        execution_control.pause_buys
        if receipt.decision_class == "enter"
        else execution_control.pause_sells
    )
    if paused:
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=(
                "pause_buys_active" if receipt.decision_class == "enter" else "pause_sells_active"
            ),
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
        )

    try:
        resolved_client = client
        if resolved_client is None:
            resolved_client = KisPaperCanaryClient(
                config=load_kis_paper_config_from_environment(environment),
                transport=transport or UrllibKisPaperCanaryTransport(),
            )
        snapshot = resolved_client.snapshot()
        position_resolution = resolve_kis_paper_spy_position_target(
            receipt,
            snapshot=snapshot,
            as_of=_session_now(now=now, clock=clock),
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError):
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="account_unavailable",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
        )
    if position_resolution.action == "none":
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=position_resolution.reason_code,
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
            position_resolution=position_resolution,
        )

    try:
        limit_input = resolved_client.fetch_spy_limit_input(observed_at=decision_at)
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError):
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="quote_unavailable",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
            position_resolution=position_resolution,
        )
    try:
        prepared = prepare_kis_paper_spy_receipt_decision(
            receipt,
            limit_input=limit_input,
            as_of=_session_now(now=now, clock=clock),
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError):
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_preparation_unavailable",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
            position_resolution=position_resolution,
        )
    if prepared.status != "ready":
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_preparation_unavailable",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
            prepared=prepared,
            position_resolution=position_resolution,
        )
    if (
        prepared.kis_paper_decision is None
        or prepared.kis_paper_decision.side != position_resolution.action
    ):
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="target_bridge_mismatch",
            observed_at=decision_at,
            artifact_root=artifact_root,
            repository_root=repository_root,
            input=input,
            evaluation=evaluation,
            prepared=prepared,
            position_resolution=position_resolution,
        )

    canary = run_kis_paper_receipt_canary(
        prepared,
        environment=environment,
        state_root=state_root,
        runtime_projection_path=runtime_projection_path,
        paper_account_snapshot_path=paper_account_snapshot_path,
        emergency_state_path=emergency_state_path,
        artifact_root=artifact_root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=cancel_after_submit,
        transport=transport,
        client=resolved_client,
        now=now,
        clock=clock,
        submit_permitted=is_us_equity_regular_session_window,
        execution_control_path=execution_control_path,
    )
    if canary.run_id != receipt_canary_run_id(prepared.receipt_ref):
        raise ValueError("daily SPY canary run identity is inconsistent")
    observation, observer_reason_code = _observe_completed_canary(
        run_id=canary.run_id,
        environment=environment,
        state_root=state_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        transport=transport,
        now=now,
        clock=clock,
    )
    (
        terminal_field_probe,
        terminal_field_probe_artifact_ref,
        terminal_field_probe_reason_code,
    ) = _probe_completed_canary_terminal_fields(
        run_id=canary.run_id,
        environment=environment,
        state_root=state_root,
        artifact_root=artifact_root,
        repository_root=repository_root,
        transport=transport,
        now=now,
        clock=clock,
    )
    return _record_session(
        session_id=resolved_session_id,
        status="canary_completed",
        reason_code=canary.reason_code,
        observed_at=decision_at,
        artifact_root=artifact_root,
        repository_root=repository_root,
        input=input,
        evaluation=evaluation,
        prepared=prepared,
        canary=canary,
        position_resolution=position_resolution,
        observation=observation,
        observer_reason_code=observer_reason_code,
        terminal_field_probe=terminal_field_probe,
        terminal_field_probe_artifact_ref=terminal_field_probe_artifact_ref,
        terminal_field_probe_reason_code=terminal_field_probe_reason_code,
    )


def _record_session(
    *,
    session_id: str,
    status: Literal["preview", "no_intent", "canary_completed"],
    reason_code: str,
    observed_at: datetime,
    artifact_root: Path,
    repository_root: Path,
    input: KisPaperDailySpyInput | None = None,
    evaluation: KisPaperDailySpyBaselineEvaluation | None = None,
    prepared: PaperDecisionBridgeResult | None = None,
    canary: KisPaperCanaryOutcome | None = None,
    position_resolution: KisPaperSpyPositionResolution | None = None,
    observation: KisPaperReceiptObservation | None = None,
    observer_reason_code: str | None = None,
    terminal_field_probe: KisPaperTerminalFieldProbeOutcome | None = None,
    terminal_field_probe_artifact_ref: str | None = None,
    terminal_field_probe_reason_code: str | None = None,
) -> KisPaperDailySpySessionOutcome:
    destination = _session_evidence_path(artifact_root=artifact_root, session_id=session_id)
    receipt = None if evaluation is None else evaluation.receipt
    outcome = KisPaperDailySpySessionOutcome(
        session_id=session_id,
        status=status,
        reason_code=reason_code,
        observed_at=observed_at,
        evidence_path=destination,
        receipt_ref=None if receipt is None else _receipt_ref(receipt),
        input_manifest_ref=None if input is None else input.input_manifest_ref,
        run_id=None if canary is None else canary.run_id,
        canary_phase=None if canary is None else canary.phase,
        canary_reason_code=None if canary is None else canary.reason_code,
        observer_status=(
            "completed"
            if observation is not None
            else "unavailable"
            if observer_reason_code is not None
            else "not_attempted"
        ),
        observer_reason_code=observer_reason_code,
        observation=observation,
        terminal_field_probe_status=(
            "completed"
            if terminal_field_probe is not None
            else "unavailable"
            if terminal_field_probe_reason_code is not None
            else "not_attempted"
        ),
        terminal_field_probe_reason_code=terminal_field_probe_reason_code,
        terminal_field_probe=terminal_field_probe,
        terminal_field_probe_artifact_ref=terminal_field_probe_artifact_ref,
    )
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_PAPER_DAILY_SPY_SESSION_EVIDENCE_KIND,
        "outcome": outcome.safe_payload(),
    }
    if input is not None:
        payload["input"] = input.safe_payload()
    if receipt is not None:
        payload["receipt"] = receipt.to_payload()
    if prepared is not None:
        payload["paper_preparation"] = prepared.safe_payload()
    if position_resolution is not None:
        payload["position_resolution"] = position_resolution.safe_payload()
    if canary is not None:
        payload["canary"] = canary.safe_payload()
    _write_or_verify(destination, payload, repository_root=repository_root)
    return outcome


def _observe_completed_canary(
    *,
    run_id: str,
    environment: Mapping[str, str],
    state_root: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> tuple[KisPaperReceiptObservation | None, str | None]:
    """Append safe same-run evidence without changing the completed order outcome."""

    try:
        outcome = observe_kis_paper_receipt(
            run_id=run_id,
            environment=environment,
            state_root=state_root,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=True,
            transport=transport,
            now=now,
            clock=clock,
        )
    # This is post-order evidence only; do not let it erase the canary outcome.
    except Exception:
        return None, _OBSERVER_UNAVAILABLE_REASON
    return outcome.observation, None


def _probe_completed_canary_terminal_fields(
    *,
    run_id: str,
    environment: Mapping[str, str],
    state_root: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> tuple[KisPaperTerminalFieldProbeOutcome | None, str | None, str | None]:
    """Append same-run field-shape evidence without changing order execution."""

    try:
        result = probe_kis_paper_terminal_fields(
            run_id=run_id,
            environment=environment,
            state_root=state_root,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=True,
            transport=transport,
            now=now,
            clock=clock,
        )
        if result.outcome.run_ref != _terminal_probe_run_ref(run_id):
            raise ValueError("terminal field probe run identity is inconsistent")
        artifact_ref = _artifact_content_ref(result.evidence_path)
    # The source probe is post-order evidence only; preserve all prior outcomes.
    except Exception:
        return None, None, _TERMINAL_FIELD_PROBE_UNAVAILABLE_REASON
    return result.outcome, artifact_ref, None


def _load_preferred_daily_spy_input(
    *,
    cache_root: Path,
    head_cache_root: Path,
    availability_root: Path,
    repository_root: Path,
    attested_at: datetime,
) -> KisPaperDailySpyInput:
    """Choose one whole source, never a per-row history/head blend."""

    head_input: KisPaperDailySpyInput | None = None
    try:
        head = load_verified_kis_paper_daily_spy_head(
            cache_root=head_cache_root,
            repository_root=repository_root,
        )
        head_input = attest_kis_paper_daily_spy_bars(
            bars=head.bars,
            catalog_dataset_id=head.dataset_id,
            catalog_dataset_hash=head.dataset_hash,
            availability_root=availability_root,
            repository_root=repository_root,
            attested_at=attested_at,
        )
    except (OSError, ValueError):
        pass

    historical_input: KisPaperDailySpyInput | None = None
    try:
        historical_input = load_kis_paper_daily_spy_input(
            cache_root=cache_root,
            availability_root=availability_root,
            repository_root=repository_root,
            attested_at=attested_at,
        )
    except (OSError, ValueError):
        pass

    if head_input is not None and (
        historical_input is None
        or head_input.last_consumed_session >= historical_input.last_consumed_session
    ):
        return head_input
    if historical_input is not None:
        return historical_input
    raise ValueError("daily SPY input is unavailable")


def _session_evidence_path(*, artifact_root: Path, session_id: str) -> Path:
    return (
        Path(artifact_root)
        / "execution"
        / "kis-paper-daily-spy-session"
        / session_id
        / "evidence.json"
    )


def _write_or_verify(
    destination: Path,
    payload: dict[str, object],
    *,
    repository_root: Path,
) -> None:
    artifact_root = Path(destination).parents[3]
    if not _is_permitted_artifact_root(artifact_root, repository_root):
        raise ValueError("daily SPY session artifact root must stay outside Git")
    encoded = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("daily SPY session evidence identity conflicts")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    resolved_artifact = Path(artifact_root).resolve()
    resolved_repository = Path(repository_root).resolve()
    if not resolved_artifact.is_relative_to(resolved_repository):
        return True
    return (
        resolved_artifact == resolved_repository / "model_artifacts"
        and resolved_artifact.is_mount()
    )


def _receipt_ref(receipt: ResearchDecisionReceipt) -> str:
    return "sha256:" + receipt.decision_id.removeprefix("decision:sha256:")


def _terminal_probe_run_ref(run_id: str) -> str:
    return "sha256:" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()


def _artifact_content_ref(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _is_sha256_reference(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _session_now(
    *, now: datetime | None, clock: Callable[[], datetime] | None
) -> datetime:
    if now is not None and clock is not None:
        raise ValueError("now and clock are mutually exclusive")
    source = now if now is not None else (clock() if clock is not None else datetime.now(UTC))
    return require_utc(source, "now")


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one KIS Paper SPY daily receipt session")
    parser.add_argument("--execute", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cancel-after-submit", action="store_true")
    mode.add_argument("--budget-trial", action="store_true")
    parser.add_argument("--budget-visits", type=int, choices=range(1, 25), default=1)
    parser.add_argument("--cache-root", type=Path, default=KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT)
    parser.add_argument("--head-cache-root", type=Path, default=KIS_PAPER_DAILY_SPY_HEAD_ROOT)
    parser.add_argument(
        "--availability-root", type=Path, default=KIS_PAPER_DAILY_SPY_AVAILABILITY_ROOT
    )
    parser.add_argument("--state-root", type=Path, default=DEFAULT_KIS_PAPER_CANARY_STATE_ROOT)
    parser.add_argument(
        "--runtime-projection", type=Path, default=DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION
    )
    parser.add_argument(
        "--paper-account-snapshot", type=Path, default=DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT
    )
    parser.add_argument(
        "--emergency-state", type=Path, default=DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE
    )
    parser.add_argument(
        "--execution-control", type=Path, default=DEFAULT_PAPER_EXECUTION_CONTROL_STATE
    )
    parser.add_argument(
        "--artifact-root", type=Path, default=DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--session-id")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    deadline = time.monotonic() + 1200 if args.budget_trial else None
    client = None
    if args.budget_trial and args.execute:
        if os.environ.get("THERICHER_MODE", "off").strip().lower() == "kis_live":
            parser.error("live_mode_unavailable")
        try:
            client = KisPaperCanaryClient(
                config=load_kis_paper_config_from_environment(os.environ),
                transport=UrllibKisPaperCanaryTransport(),
            )
        except (KisPaperReadOnlyError, KisPaperCanaryError, ValueError):
            parser.error("paper_configuration_unavailable")

    visits = args.budget_visits if args.budget_trial else 1
    for visit in range(visits):
        if deadline is not None and time.monotonic() >= deadline:
            break
        outcome = run_kis_paper_daily_spy_session(
            environment=os.environ,
            cache_root=args.cache_root,
            head_cache_root=args.head_cache_root,
            availability_root=args.availability_root,
            state_root=args.state_root,
            runtime_projection_path=args.runtime_projection,
            paper_account_snapshot_path=args.paper_account_snapshot,
            emergency_state_path=args.emergency_state,
            artifact_root=args.artifact_root,
            repository_root=args.repository_root,
            execute=args.execute,
            cancel_after_submit=args.cancel_after_submit,
            budget_trial=args.budget_trial,
            session_id=args.session_id,
            execution_control_path=args.execution_control,
            client=client,
        )
        print(json.dumps(outcome.safe_payload(), sort_keys=True), flush=True)
        if deadline is None or outcome.status != "pending" or visit + 1 == visits:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(15, remaining))


if __name__ == "__main__":
    main()

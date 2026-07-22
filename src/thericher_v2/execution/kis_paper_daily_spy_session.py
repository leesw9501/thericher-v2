"""Run one receipt-backed KIS Paper SPY daily decision session.

The daily cache and model decision are evaluated offline before this module
loads Paper configuration or touches KIS. A missing, stale, or abstaining
receipt is scoped evidence for this session, not an approval state or a hold on
another Paper action.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

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
    run_kis_paper_receipt_canary,
)
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_readonly import (
    KisHttpTransport,
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)
from .paper_decision_bridge import PaperDecisionBridgeResult

KIS_PAPER_DAILY_SPY_SESSION_EVIDENCE_KIND = "kis_paper_daily_spy_session_evidence"
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}", re.ASCII)
_SESSION_STATUSES = frozenset({"preview", "no_intent", "canary_completed"})
_SESSION_REASONS = frozenset(
    {
        "preview",
        "daily_input_unavailable",
        "daily_receipt_abstain",
        "daily_receipt_not_current",
        "session_closed",
        "pause_buys_active",
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
        if self.canary_phase is not None and _SAFE_REASON.fullmatch(self.canary_phase) is None:
            raise ValueError("daily SPY canary phase is invalid")
        if self.canary_reason_code is not None and _SAFE_REASON.fullmatch(
            self.canary_reason_code
        ) is None:
            raise ValueError("daily SPY canary reason is invalid")
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
) -> KisPaperDailySpySessionOutcome:
    """Evaluate one SPY D1 receipt and execute only its eligible Paper intent."""

    observed_at = _session_now(now=now, clock=clock)
    resolved_session_id = session_id or f"daily-spy-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    if _SAFE_ID.fullmatch(resolved_session_id) is None:
        raise ValueError("daily SPY session id is invalid")

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
    if receipt.decision_class != "enter":
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
    if PaperExecutionControlStore(execution_control_path).read().pause_buys:
        return _record_session(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="pause_buys_active",
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
        limit_input = resolved_client.fetch_spy_limit_input(observed_at=decision_at)
        prepared = prepare_kis_paper_spy_receipt_decision(
            receipt,
            limit_input=limit_input,
            as_of=_session_now(now=now, clock=clock),
        )
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
    if canary is not None:
        payload["canary"] = canary.safe_payload()
    _write_or_verify(destination, payload, repository_root=repository_root)
    return outcome


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
    parser.add_argument("--cancel-after-submit", action="store_true")
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
    args = build_parser().parse_args(argv)
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
        session_id=args.session_id,
        execution_control_path=args.execution_control,
    )
    print(json.dumps(outcome.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()

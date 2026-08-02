"""Bind one fresh prospective SPY receipt to the existing KIS Paper canary.

The frozen 15:30 multi-timeframe observation is loaded and revalidated before
this module reads Paper configuration, account facts, or a quote. It never
evaluates bars, replays local fills, changes the daily SPY route, or schedules
itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_prospective_spy_capture import (
    load_kis_paper_prospective_spy_observation_receipt,
)
from thericher_v2.models.prospective_spy_intraday_observation import (
    ProspectiveSpyIntradayObservationReceipt,
)
from thericher_v2.research.decision_receipt import ResearchDecisionReceipt
from thericher_v2.research.prospective_spy_intraday_paper_receipt import (
    research_receipt_from_prospective_spy_intraday_observation,
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
from .kis_paper_receipt_canary import (
    prepare_kis_paper_spy_receipt_decision,
    receipt_canary_run_id,
    run_kis_paper_receipt_canary,
)
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_paper_spy_position import (
    KisPaperSpyPositionResolution,
    resolve_kis_paper_spy_position_target,
)
from .kis_readonly import (
    KisHttpTransport,
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)
from .paper_decision_bridge import PaperDecisionBridgeResult

KIS_PAPER_PROSPECTIVE_SPY_SESSION_EVIDENCE_KIND = "kis_paper_prospective_spy_session"
KIS_PAPER_PROSPECTIVE_SPY_SESSION_ARTIFACT_DIRECTORY = (
    "execution/kis-paper-prospective-spy-session"
)
_EASTERN = ZoneInfo("America/New_York")
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}", re.ASCII)
_RECEIPT_REF = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_STATUSES = frozenset({"preview", "no_intent", "canary_completed"})
_DEFAULT_REPOSITORY_ROOT = Path.cwd()
_NO_INTENT_REASONS = frozenset(
    {
        "preview",
        "receipt_unavailable",
        "receipt_abstain",
        "receipt_not_current",
        "receipt_expired_before_account",
        "receipt_expired_during_preparation",
        "session_closed",
        "pause_buys_active",
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
class KisPaperProspectiveSpySessionOutcome:
    """Source-safe evidence for one receipt-bound virtual SPY session."""

    session_id: str
    status: Literal["preview", "no_intent", "canary_completed"]
    reason_code: str
    observed_at: datetime
    evidence_path: Path
    observation_receipt_ref: str | None = None
    research_receipt: ResearchDecisionReceipt | None = None
    position_resolution: KisPaperSpyPositionResolution | None = None
    prepared: PaperDecisionBridgeResult | None = None
    canary: KisPaperCanaryOutcome | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.session_id) is None:
            raise ValueError("prospective SPY session id is invalid")
        if self.status not in _STATUSES:
            raise ValueError("prospective SPY session status is invalid")
        if self.status == "canary_completed":
            if self.canary is None or _SAFE_REASON.fullmatch(self.reason_code) is None:
                raise ValueError("completed prospective SPY session is invalid")
        elif self.reason_code not in _NO_INTENT_REASONS:
            raise ValueError("prospective SPY session reason is invalid")
        if self.status != "canary_completed" and self.canary is not None:
            raise ValueError("no-intent prospective SPY session cannot carry a canary")
        if self.observation_receipt_ref is not None and _RECEIPT_REF.fullmatch(
            self.observation_receipt_ref
        ) is None:
            raise ValueError("prospective SPY observation receipt reference is invalid")
        if self.research_receipt is not None and self.observation_receipt_ref is None:
            raise ValueError("research receipt requires an observation receipt reference")
        if not isinstance(self.evidence_path, Path) or self.evidence_path.name != "evidence.json":
            raise ValueError("prospective SPY evidence path is invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))

    def safe_payload(self) -> dict[str, object]:
        """Expose categorical route evidence without bars, files, or account values."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_SPY_SESSION_EVIDENCE_KIND,
            "session_id": self.session_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": _utc_marker(self.observed_at),
            "route": "kis_paper",
            "paper_only": True,
            "observation_receipt_ref": self.observation_receipt_ref,
            "research_receipt": (
                None if self.research_receipt is None else self.research_receipt.to_payload()
            ),
            "position_resolution": (
                None
                if self.position_resolution is None
                else self.position_resolution.safe_payload()
            ),
            "prepared": None if self.prepared is None else self.prepared.safe_payload(),
            "canary": None if self.canary is None else self.canary.safe_payload(),
        }


def run_kis_paper_prospective_spy_session(
    *,
    environment: Mapping[str, str],
    artifact_root: Path = DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    state_root: Path = DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    runtime_projection_path: Path = DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    paper_account_snapshot_path: Path = DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    emergency_state_path: Path = DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    session_id: str | None = None,
) -> KisPaperProspectiveSpySessionOutcome:
    """Use one current ``enter`` receipt for at most one virtual SPY canary."""

    observed_at = _session_now(now=now, clock=clock)
    resolved_session_id = session_id or (
        f"prospective-spy-{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    if _SAFE_ID.fullmatch(resolved_session_id) is None:
        raise ValueError("prospective SPY session id is invalid")
    if resolved_session_id in {".", ".."}:
        raise ValueError("prospective SPY session id is invalid")
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)

    try:
        observation = load_kis_paper_prospective_spy_observation_receipt(
            artifact_root=root,
            repo_root=repository_root,
            session_date=observed_at.astimezone(_EASTERN).date(),
        )
        receipt = research_receipt_from_prospective_spy_intraday_observation(observation)
    except (OSError, TypeError, ValueError):
        return _record(
            session_id=resolved_session_id,
            status="no_intent" if execute else "preview",
            reason_code="receipt_unavailable" if execute else "preview",
            observed_at=observed_at,
            artifact_root=root,
        )

    receipt_ref = _observation_receipt_ref(observation)
    if not execute:
        return _record(
            session_id=resolved_session_id,
            status="preview",
            reason_code="preview",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
        )
    if receipt.decision_class != "enter":
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_abstain",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
        )
    if not _receipt_is_current(receipt, as_of=observed_at):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_not_current",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
        )
    if not is_us_equity_regular_session_window(observed_at):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="session_closed",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
        )
    if PaperExecutionControlStore(execution_control_path).read().pause_buys:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="pause_buys_active",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
        )

    before_account = _session_now(now=now, clock=clock)
    if not _receipt_is_current(receipt, as_of=before_account):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_expired_before_account",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
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
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="account_unavailable",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
        )
    if position_resolution.action == "none":
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=position_resolution.reason_code,
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
            position_resolution=position_resolution,
        )

    try:
        limit_input = resolved_client.fetch_spy_limit_input(
            observed_at=_session_now(now=now, clock=clock)
        )
        prepared = prepare_kis_paper_spy_receipt_decision(
            receipt,
            limit_input=limit_input,
            as_of=_session_now(now=now, clock=clock),
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="quote_unavailable",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
            position_resolution=position_resolution,
        )
    if prepared.status != "ready" or prepared.kis_paper_decision is None:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_preparation_unavailable",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
            position_resolution=position_resolution,
            prepared=prepared,
        )
    if prepared.kis_paper_decision.side != position_resolution.action:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="target_bridge_mismatch",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
            position_resolution=position_resolution,
            prepared=prepared,
        )

    before_submit = _session_now(now=now, clock=clock)
    if not _receipt_is_current(receipt, as_of=before_submit):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_expired_during_preparation",
            observed_at=observed_at,
            artifact_root=root,
            observation_receipt_ref=receipt_ref,
            research_receipt=receipt,
            position_resolution=position_resolution,
            prepared=prepared,
        )

    canary = run_kis_paper_receipt_canary(
        prepared,
        environment=environment,
        state_root=state_root,
        runtime_projection_path=runtime_projection_path,
        paper_account_snapshot_path=paper_account_snapshot_path,
        emergency_state_path=emergency_state_path,
        artifact_root=root,
        repository_root=repository_root,
        execute=True,
        cancel_after_submit=cancel_after_submit,
        transport=transport,
        client=resolved_client,
        now=now,
        clock=clock,
        submit_permitted=lambda submit_at: (
            is_us_equity_regular_session_window(submit_at)
            and _receipt_is_current(receipt, as_of=submit_at)
        ),
        execution_control_path=execution_control_path,
    )
    if canary.run_id != receipt_canary_run_id(prepared.receipt_ref):
        raise ValueError("prospective SPY canary run identity is inconsistent")
    return _record(
        session_id=resolved_session_id,
        status="canary_completed",
        reason_code=canary.reason_code,
        observed_at=observed_at,
        artifact_root=root,
        observation_receipt_ref=receipt_ref,
        research_receipt=receipt,
        position_resolution=position_resolution,
        prepared=prepared,
        canary=canary,
    )


def _record(
    *,
    session_id: str,
    status: Literal["preview", "no_intent", "canary_completed"],
    reason_code: str,
    observed_at: datetime,
    artifact_root: Path,
    observation_receipt_ref: str | None = None,
    research_receipt: ResearchDecisionReceipt | None = None,
    position_resolution: KisPaperSpyPositionResolution | None = None,
    prepared: PaperDecisionBridgeResult | None = None,
    canary: KisPaperCanaryOutcome | None = None,
) -> KisPaperProspectiveSpySessionOutcome:
    evidence_path = _session_evidence_path(artifact_root=artifact_root, session_id=session_id)
    outcome = KisPaperProspectiveSpySessionOutcome(
        session_id=session_id,
        status=status,
        reason_code=reason_code,
        observed_at=observed_at,
        evidence_path=evidence_path,
        observation_receipt_ref=observation_receipt_ref,
        research_receipt=research_receipt,
        position_resolution=position_resolution,
        prepared=prepared,
        canary=canary,
    )
    _write_or_verify(evidence_path, outcome.safe_payload(), artifact_root=artifact_root)
    return outcome


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve(strict=False)
    repository = Path(repository_root).resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    mounted_artifacts = repository == docker_repository and root.is_relative_to(docker_artifacts)
    if root.is_relative_to(repository) and not mounted_artifacts:
        raise ValueError("prospective SPY evidence root must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("prospective SPY evidence root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _session_evidence_path(*, artifact_root: Path, session_id: str) -> Path:
    directory = (
        artifact_root / KIS_PAPER_PROSPECTIVE_SPY_SESSION_ARTIFACT_DIRECTORY / session_id
    )
    _ensure_real_descendant(root=artifact_root, directory=directory)
    path = directory / "evidence.json"
    if path.exists() and path.is_symlink():
        raise ValueError("prospective SPY evidence path is invalid")
    if not path.resolve(strict=False).is_relative_to(artifact_root):
        raise ValueError("prospective SPY evidence path is invalid")
    return path


def _ensure_real_descendant(*, root: Path, directory: Path) -> None:
    try:
        relative_parts = directory.relative_to(root).parts
    except ValueError as error:
        raise ValueError("prospective SPY evidence path is invalid") from error
    cursor = root
    for part in relative_parts:
        cursor = cursor / part
        if cursor.exists():
            if cursor.is_symlink() or not cursor.is_dir():
                raise ValueError("prospective SPY evidence path is invalid")
        else:
            cursor.mkdir()
        if not cursor.resolve(strict=True).is_relative_to(root):
            raise ValueError("prospective SPY evidence path is invalid")


def _write_or_verify(
    path: Path,
    payload: Mapping[str, object],
    *,
    artifact_root: Path,
) -> None:
    _ensure_real_descendant(root=artifact_root, directory=path.parent)
    if path.exists() and path.is_symlink():
        raise ValueError("prospective SPY evidence path is invalid")
    if not path.resolve(strict=False).is_relative_to(artifact_root):
        raise ValueError("prospective SPY evidence path is invalid")
    encoded = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != encoded:
            raise ValueError("prospective SPY session evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(encoded)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != encoded:
                raise ValueError("prospective SPY session evidence identity conflicts")
            return
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _observation_receipt_ref(receipt: ProspectiveSpyIntradayObservationReceipt) -> str:
    return "sha256:" + hashlib.sha256(receipt.canonical_json().encode("utf-8")).hexdigest()


def _receipt_is_current(receipt: ResearchDecisionReceipt, *, as_of: datetime) -> bool:
    observed_at = require_utc(as_of, "as_of")
    return (
        receipt.input_status == "ready"
        and receipt.decision_class == "enter"
        and receipt.reason_class == "eligible_enter"
        and receipt.decided_at <= observed_at <= receipt.valid_until
    )


def _session_now(*, now: datetime | None, clock: Callable[[], datetime] | None) -> datetime:
    if now is not None and clock is not None:
        raise ValueError("provide either now or clock")
    return require_utc(now if now is not None else (clock or (lambda: datetime.now(UTC)))(), "now")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "observed_at").isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one prospective SPY KIS Paper receipt session"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cancel-after-submit", action="store_true")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--state-root", type=Path, default=DEFAULT_KIS_PAPER_CANARY_STATE_ROOT)
    parser.add_argument(
        "--runtime-projection", type=Path, default=DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION
    )
    parser.add_argument(
        "--paper-account-snapshot", type=Path, default=DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT
    )
    parser.add_argument(
        "--emergency-state",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    )
    parser.add_argument(
        "--execution-control",
        type=Path,
        default=DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    )
    parser.add_argument("--session-id")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    outcome = run_kis_paper_prospective_spy_session(
        environment=os.environ,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        state_root=args.state_root,
        runtime_projection_path=args.runtime_projection,
        paper_account_snapshot_path=args.paper_account_snapshot,
        emergency_state_path=args.emergency_state,
        execution_control_path=args.execution_control,
        execute=args.execute,
        cancel_after_submit=args.cancel_after_submit,
        session_id=args.session_id,
    )
    print(json.dumps(outcome.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()

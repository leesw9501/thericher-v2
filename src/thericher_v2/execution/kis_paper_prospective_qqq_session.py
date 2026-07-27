"""Bound one fresh QQQ runtime receipt to local replay and KIS Paper execution.

The cache and baseline are evaluated before this module creates a KIS client.
An unavailable or ineligible input therefore remains a source-safe no-intent
fact and never causes credential, account, quote, or order activity.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    select_kis_paper_intraday_runtime_window,
)
from thericher_v2.research.kis_paper_baseline import KIS_PAPER_BASELINE_MAX_AGE
from thericher_v2.research.kis_paper_prospective_loop import (
    KisPaperProspectiveLoopResult,
    run_kis_paper_prospective_loop,
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
    prepare_kis_paper_qqq_receipt_decision,
    receipt_canary_run_id,
    run_kis_paper_receipt_canary,
)
from .kis_paper_session import is_us_equity_regular_session_window
from .kis_paper_spy_position import resolve_kis_paper_qqq_position_target
from .kis_readonly import (
    KisHttpTransport,
    KisPaperReadOnlyError,
    load_kis_paper_config_from_environment,
)
from .paper_decision_bridge import PaperDecisionBridgeResult

KIS_PAPER_PROSPECTIVE_QQQ_SESSION_KIND = "kis_paper_prospective_qqq_session"
KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY = "execution/kis-paper-prospective-qqq-session"
KIS_PAPER_PROSPECTIVE_QQQ_HEAD_CACHE_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\intraday-head"
)
KIS_PAPER_PROSPECTIVE_QQQ_LOCAL_PAPER_STATE_ROOT = Path(
    r"D:\thericher-v2\model-artifacts\_control\local-paper"
)
_DEFAULT_REPOSITORY_ROOT = Path.cwd()
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}", re.ASCII)

ProspectiveQqqSessionStatus = Literal["preview", "no_intent", "canary_completed"]


@dataclass(frozen=True)
class KisPaperProspectiveQqqSessionOutcome:
    """Source-safe evidence for one current QQQ Paper session attempt."""

    session_id: str
    status: ProspectiveQqqSessionStatus
    reason_code: str
    observed_at: datetime
    evidence_path: Path
    loop: KisPaperProspectiveLoopResult | None
    position_resolution: object | None = None
    prepared: PaperDecisionBridgeResult | None = None
    canary: KisPaperCanaryOutcome | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if _SAFE_SESSION_ID.fullmatch(self.session_id) is None:
            raise ValueError("prospective QQQ session id is invalid")
        if self.status not in {"preview", "no_intent", "canary_completed"}:
            raise ValueError("prospective QQQ session status is invalid")
        if _SAFE_REASON.fullmatch(self.reason_code) is None:
            raise ValueError("prospective QQQ session reason is invalid")
        if (
            not isinstance(self.evidence_path, Path)
            or self.evidence_path.name != f"{self.session_id}.json"
        ):
            raise ValueError("prospective QQQ session evidence path is invalid")
        if self.status == "canary_completed" and self.canary is None:
            raise ValueError("completed canary session requires a canary outcome")
        if self.status != "canary_completed" and self.canary is not None:
            raise ValueError("no-intent session cannot carry a canary outcome")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))

    def safe_payload(self) -> dict[str, object]:
        """Expose categorical execution evidence without values or account facts."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_QQQ_SESSION_KIND,
            "session_id": self.session_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "observed_at": _utc_marker(self.observed_at),
            "paper_only": True,
            "loop": None if self.loop is None else self.loop.safe_payload(),
            "position_resolution": _safe_payload_or_none(self.position_resolution),
            "prepared": None if self.prepared is None else self.prepared.safe_payload(),
            "canary": None if self.canary is None else self.canary.safe_payload(),
        }


def run_kis_paper_prospective_qqq_session(
    *,
    environment: Mapping[str, str],
    cache_root: Path = KIS_PAPER_PROSPECTIVE_QQQ_HEAD_CACHE_ROOT,
    local_paper_state_root: Path = KIS_PAPER_PROSPECTIVE_QQQ_LOCAL_PAPER_STATE_ROOT,
    state_root: Path = DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    runtime_projection_path: Path = DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    paper_account_snapshot_path: Path = DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    emergency_state_path: Path = DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    execution_control_path: Path = DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    artifact_root: Path = DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    session_id: str | None = None,
) -> KisPaperProspectiveQqqSessionOutcome:
    """Run one no-secret-until-eligible QQQ runtime session.

    The same verified cached bars feed the receipt and local replay. KIS Paper
    configuration is loaded only after that receipt is current, actionable,
    inside the regular session, and not paused by the existing execution control.
    """

    observed_at = _session_now(now=now, clock=clock)
    resolved_session_id = session_id or _session_id(observed_at)
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    evidence_path = root / KIS_PAPER_PROSPECTIVE_QQQ_SESSION_ARTIFACT_DIRECTORY / (
        f"{resolved_session_id}.json"
    )

    try:
        catalog = load_verified_kis_paper_private_intraday_catalog(
            cache_root=cache_root,
            repo_root=repository_root,
            symbol="QQQ",
            exchange="NAS",
        )
        window = select_kis_paper_intraday_runtime_window(
            catalog,
            as_of=observed_at,
            max_age=KIS_PAPER_BASELINE_MAX_AGE,
        )
        loop = run_kis_paper_prospective_loop(
            window,
            local_paper_state_root=local_paper_state_root,
            repo_root=repository_root,
        )
    except (OSError, ValueError):
        return _record(
            session_id=resolved_session_id,
            status="no_intent" if execute else "preview",
            reason_code="verified_catalog_unavailable" if execute else "preview",
            observed_at=observed_at,
            evidence_path=evidence_path,
        )

    if not execute:
        return _record(
            session_id=resolved_session_id,
            status="preview",
            reason_code="preview",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
        )
    if loop.window.status != "ready":
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=f"runtime_window_{loop.window.status}",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
        )
    receipt = loop.receipt
    if receipt.decision_class not in {"enter", "exit"}:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_not_eligible",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
        )
    if not (receipt.decided_at <= observed_at <= receipt.valid_until):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_not_current",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
        )
    if not is_us_equity_regular_session_window(observed_at):
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="session_closed",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
        )
    execution_control = PaperExecutionControlStore(execution_control_path).read()
    paused = (
        execution_control.pause_buys
        if receipt.decision_class == "enter"
        else execution_control.pause_sells
    )
    if paused:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=(
                "pause_buys_active"
                if receipt.decision_class == "enter"
                else "pause_sells_active"
            ),
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
        )

    try:
        resolved_client = client
        if resolved_client is None:
            resolved_client = KisPaperCanaryClient(
                config=load_kis_paper_config_from_environment(environment),
                transport=transport or UrllibKisPaperCanaryTransport(),
            )
        snapshot = resolved_client.snapshot()
        position_resolution = resolve_kis_paper_qqq_position_target(
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
            evidence_path=evidence_path,
            loop=loop,
        )
    if position_resolution.action == "none":
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code=position_resolution.reason_code,
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
            position_resolution=position_resolution,
        )

    try:
        limit_input = resolved_client.fetch_qqq_limit_input(
            observed_at=_session_now(now=now, clock=clock)
        )
        prepared = prepare_kis_paper_qqq_receipt_decision(
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
            evidence_path=evidence_path,
            loop=loop,
            position_resolution=position_resolution,
        )
    if prepared.status != "ready" or prepared.kis_paper_decision is None:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="receipt_preparation_unavailable",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
            position_resolution=position_resolution,
            prepared=prepared,
        )
    if prepared.kis_paper_decision.side != position_resolution.action:
        return _record(
            session_id=resolved_session_id,
            status="no_intent",
            reason_code="target_bridge_mismatch",
            observed_at=observed_at,
            evidence_path=evidence_path,
            loop=loop,
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
        raise ValueError("prospective QQQ canary run identity is inconsistent")
    return _record(
        session_id=resolved_session_id,
        status="canary_completed",
        reason_code=canary.reason_code,
        observed_at=observed_at,
        evidence_path=evidence_path,
        loop=loop,
        position_resolution=position_resolution,
        prepared=prepared,
        canary=canary,
    )


def _record(
    *,
    session_id: str,
    status: ProspectiveQqqSessionStatus,
    reason_code: str,
    observed_at: datetime,
    evidence_path: Path,
    loop: KisPaperProspectiveLoopResult | None = None,
    position_resolution: object | None = None,
    prepared: PaperDecisionBridgeResult | None = None,
    canary: KisPaperCanaryOutcome | None = None,
) -> KisPaperProspectiveQqqSessionOutcome:
    outcome = KisPaperProspectiveQqqSessionOutcome(
        session_id=session_id,
        status=status,
        reason_code=reason_code,
        observed_at=observed_at,
        evidence_path=evidence_path,
        loop=loop,
        position_resolution=position_resolution,
        prepared=prepared,
        canary=canary,
    )
    _write_json_atomically(outcome.evidence_path, outcome.safe_payload())
    return outcome


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    root = Path(artifact_root).resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise ValueError("prospective QQQ evidence root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != encoded:
            raise ValueError("prospective QQQ session evidence identity conflicts")
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
                raise ValueError("prospective QQQ session evidence identity conflicts")
            return
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _safe_payload_or_none(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    safe_payload = getattr(value, "safe_payload", None)
    if not callable(safe_payload):
        raise ValueError("prospective QQQ session evidence is not source-safe")
    payload = safe_payload()
    if not isinstance(payload, dict):
        raise ValueError("prospective QQQ session evidence payload is invalid")
    return payload


def _session_id(observed_at: datetime) -> str:
    return "prospective-qqq-" + observed_at.strftime("%Y%m%dT%H%M%S%fZ")


def _session_now(*, now: datetime | None, clock: Callable[[], datetime] | None) -> datetime:
    if now is not None and clock is not None:
        raise ValueError("provide either now or clock")
    return require_utc(now if now is not None else (clock or (lambda: datetime.now(UTC)))(), "now")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "observed_at").isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one prospective QQQ KIS Paper receipt session"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cancel-after-submit", action="store_true")
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=KIS_PAPER_PROSPECTIVE_QQQ_HEAD_CACHE_ROOT,
    )
    parser.add_argument(
        "--local-paper-state-root",
        type=Path,
        default=KIS_PAPER_PROSPECTIVE_QQQ_LOCAL_PAPER_STATE_ROOT,
    )
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
        "--execution-control", type=Path, default=DEFAULT_PAPER_EXECUTION_CONTROL_STATE
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--session-id")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    outcome = run_kis_paper_prospective_qqq_session(
        environment=os.environ,
        cache_root=args.cache_root,
        local_paper_state_root=args.local_paper_state_root,
        state_root=args.state_root,
        runtime_projection_path=args.runtime_projection,
        paper_account_snapshot_path=args.paper_account_snapshot,
        emergency_state_path=args.emergency_state,
        execution_control_path=args.execution_control,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        execute=args.execute,
        cancel_after_submit=args.cancel_after_submit,
        session_id=args.session_id,
    )
    print(json.dumps(outcome.safe_payload(), sort_keys=True))


if __name__ == "__main__":
    main()

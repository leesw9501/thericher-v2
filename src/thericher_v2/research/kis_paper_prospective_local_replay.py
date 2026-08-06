"""Replay one prospective target-state proposal through broker-free local paper."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, TargetExposureProposal, require_utc
from thericher_v2.execution import LOCAL_PAPER_SOURCE, EmergencyStore, LocalPaperBroker
from thericher_v2.execution.target_position import target_proposal_to_order_intent
from thericher_v2.state import EventStore

KIS_PAPER_PROSPECTIVE_LOCAL_REPLAY_KIND = "kis_paper_prospective_local_replay"
_LOCAL_PAPER_STATE_ID = "qqq-prospective-local-paper-v1"

LocalReplayStatus = Literal["filled", "no_intent", "awaiting_replay_bar"]


@dataclass(frozen=True)
class KisPaperProspectiveLocalReplay:
    """Source-safe projection of a deterministic local-paper replay.

    The event log remains private runtime state because local fill events include
    price-derived accounting. This result carries only its digest and categorical
    lifecycle, so it is safe to place beside a research receipt artifact.
    """

    proposal_id: str
    status: LocalReplayStatus
    reason: str
    event_log_sha256: str | None
    fill_source: str | None
    filled_at: datetime | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("proposal_id is required")
        if self.status not in {"filled", "no_intent", "awaiting_replay_bar"}:
            raise ValueError("local replay status is invalid")
        if not self.reason.strip():
            raise ValueError("local replay reason is required")
        if self.status == "filled":
            if self.event_log_sha256 is None or self.fill_source != LOCAL_PAPER_SOURCE:
                raise ValueError("filled local replay requires local-paper evidence")
            if self.filled_at is None:
                raise ValueError("filled local replay requires fill time")
        elif any(
            value is not None for value in (self.event_log_sha256, self.fill_source, self.filled_at)
        ):
            raise ValueError("unfilled local replay cannot expose fill evidence")
        if self.event_log_sha256 is not None:
            _require_sha256(self.event_log_sha256, "event_log_sha256")
        if self.filled_at is not None:
            object.__setattr__(self, "filled_at", require_utc(self.filled_at, "filled_at"))

    def safe_payload(self) -> dict[str, object]:
        """Return categorical evidence that intentionally omits order prices and quantities."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_PROSPECTIVE_LOCAL_REPLAY_KIND,
            "proposal_id": _proposal_ref(self.proposal_id),
            "status": self.status,
            "reason": self.reason,
            "event_log_sha256": self.event_log_sha256,
            "fill_source": self.fill_source,
            "filled_at": None if self.filled_at is None else _utc_marker(self.filled_at),
        }


def replay_kis_paper_prospective_local_paper(
    proposal: TargetExposureProposal,
    *,
    signal_bar: Bar,
    replay_bar: Bar | None,
    state_root: Path,
    repo_root: Path,
    current_quantity: Decimal | None = None,
    maximum_quantity: Decimal = Decimal("20"),
    starting_cash: Decimal = Decimal("10000"),
) -> KisPaperProspectiveLocalReplay:
    """Map one current proposal to local paper without a broker or credential path.

    A next completed bar is intentionally optional. Its absence is a scoped
    replay fact, not a reason to fabricate a fill or defer the proposal itself.
    """

    if not isinstance(proposal, TargetExposureProposal):
        raise TypeError("proposal must be a TargetExposureProposal")
    _require_matching_signal_bar(proposal=proposal, signal_bar=signal_bar)
    if replay_bar is not None:
        _require_next_replay_bar(signal_bar=signal_bar, replay_bar=replay_bar)
        if proposal.decided_at > replay_bar.start_ts:
            return KisPaperProspectiveLocalReplay(
                proposal_id=proposal.proposal_id,
                status="no_intent",
                reason="decision_after_replay_bar",
                event_log_sha256=None,
                fill_source=None,
                filled_at=None,
            )
    root = _external_state_root(state_root=state_root, repo_root=repo_root)
    event_log_path = root / f"{_LOCAL_PAPER_STATE_ID}.jsonl"
    event_store = EventStore(
        root / f"{_LOCAL_PAPER_STATE_ID}.sqlite",
        event_log_path,
    )
    broker = LocalPaperBroker(
        event_store=event_store,
        emergency_store=EmergencyStore(root / "emergency.json"),
        starting_cash=starting_cash,
    )
    client_order_id = _client_order_id(proposal.proposal_id)
    if _has_accepted_local_order(event_store, client_order_id=client_order_id):
        if replay_bar is None:
            return KisPaperProspectiveLocalReplay(
                proposal_id=proposal.proposal_id,
                status="awaiting_replay_bar",
                reason="next_completed_bar_unavailable",
                event_log_sha256=None,
                fill_source=None,
                filled_at=None,
            )
        recovered = broker.fill_next_bar(
            client_order_id,
            signal_bar=signal_bar,
            execution_bar=replay_bar,
        )
        if recovered.fill is None:  # pragma: no cover - accepted orders either fill or reject here.
            raise ValueError("accepted local-paper order did not produce a recoverable fill")
        return KisPaperProspectiveLocalReplay(
            proposal_id=proposal.proposal_id,
            status="filled",
            reason="filled_at_next_bar_open",
            event_log_sha256=_sha256_file(event_log_path),
            fill_source=recovered.fill.source,
            filled_at=recovered.fill.filled_at,
        )
    recorded_quantity = broker.account().quantity(market=proposal.market, symbol=proposal.symbol)
    if current_quantity is not None and current_quantity != recorded_quantity:
        return KisPaperProspectiveLocalReplay(
            proposal_id=proposal.proposal_id,
            status="no_intent",
            reason="local_paper_position_mismatch",
            event_log_sha256=None,
            fill_source=None,
            filled_at=None,
        )
    intent = target_proposal_to_order_intent(
        proposal,
        client_order_id=client_order_id,
        current_quantity=recorded_quantity,
        maximum_quantity=maximum_quantity,
        as_of=proposal.decided_at,
    )
    if intent is None:
        return KisPaperProspectiveLocalReplay(
            proposal_id=proposal.proposal_id,
            status="no_intent",
            reason="target_delta_not_eligible",
            event_log_sha256=None,
            fill_source=None,
            filled_at=None,
        )
    if replay_bar is None:
        return KisPaperProspectiveLocalReplay(
            proposal_id=proposal.proposal_id,
            status="awaiting_replay_bar",
            reason="next_completed_bar_unavailable",
            event_log_sha256=None,
            fill_source=None,
            filled_at=None,
        )
    execution = broker.submit_and_fill_next_bar(
        intent,
        signal_bar=signal_bar,
        execution_bar=replay_bar,
    )
    if execution.fill is None:
        return KisPaperProspectiveLocalReplay(
            proposal_id=proposal.proposal_id,
            status="no_intent",
            reason=f"local_paper_{execution.order_result.status}",
            event_log_sha256=None,
            fill_source=None,
            filled_at=None,
        )
    return KisPaperProspectiveLocalReplay(
        proposal_id=proposal.proposal_id,
        status="filled",
        reason="filled_at_next_bar_open",
        event_log_sha256=_sha256_file(event_log_path),
        fill_source=execution.fill.source,
        filled_at=execution.fill.filled_at,
    )


def _external_state_root(*, state_root: Path, repo_root: Path) -> Path:
    root = Path(state_root).resolve()
    repository = Path(repo_root).resolve()
    mounted_artifact_root = repository / "model_artifacts"
    permitted_mount = (
        mounted_artifact_root.is_mount() and root.is_relative_to(mounted_artifact_root)
    )
    if root.is_relative_to(repository) and not permitted_mount:
        raise ValueError("local-paper runtime state must stay outside Git")
    if root.is_symlink():
        raise ValueError("local-paper runtime state root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _require_matching_signal_bar(*, proposal: TargetExposureProposal, signal_bar: Bar) -> None:
    if (
        signal_bar.symbol != proposal.symbol
        or signal_bar.market != proposal.market
        or not signal_bar.complete
        or proposal.feature_window_end != signal_bar.end_ts
    ):
        raise ValueError("local-paper signal bar does not match proposal")


def _require_next_replay_bar(*, signal_bar: Bar, replay_bar: Bar) -> None:
    if (
        replay_bar.symbol != signal_bar.symbol
        or replay_bar.market != signal_bar.market
        or replay_bar.timeframe != signal_bar.timeframe
        or not replay_bar.complete
        or replay_bar.start_ts != signal_bar.end_ts
    ):
        raise ValueError("local-paper replay bar is not the next completed bar")


def _client_order_id(proposal_id: str) -> str:
    return f"local-prospective-{_proposal_digest(proposal_id)}"


def _proposal_ref(proposal_id: str) -> str:
    return "sha256:" + _proposal_digest(proposal_id)


def _proposal_digest(proposal_id: str) -> str:
    return hashlib.sha256(proposal_id.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _has_accepted_local_order(event_store: EventStore, *, client_order_id: str) -> bool:
    return any(
        event.event_type == "local_paper_order_accepted"
        and event.payload.get("source") == LOCAL_PAPER_SOURCE
        and event.payload.get("client_order_id") == client_order_id
        for event in event_store.iter_events()
    )


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field_name} must be an exact sha256 digest")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "filled_at").isoformat().replace("+00:00", "Z")

"""One local-cache dispatch point for the existing profiled MTF forward witnesses.

This is intentionally a single-invocation selector, not a scheduler.  It
chooses at most one existing local-only observer action and leaves all source,
duplicate, mutation, conflict, and raw-snapshot semantics to that action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path
from typing import Final, Literal

from thericher_v2.contracts import require_utc
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

from .kis_mtf_profiled_prospective_observer import (
    CatalogLoader,
    KisMtfProfiledForwardOutcomeStoreResult,
    KisMtfProfiledProspectiveStoreResult,
    run_kis_mtf_profiled_forward_outcome_witness,
    run_kis_mtf_profiled_prospective_observer,
)

PROFILED_MTF_FORWARD_CAPTURE_CYCLE_ID: Final = "profiled-mtf-forward-capture-cycle-v1"
PROFILED_MTF_FORWARD_CAPTURE_CYCLE_INPUT_CUTOFF: Final = time(15, 30)
PROFILED_MTF_FORWARD_CAPTURE_CYCLE_OUTCOME_DUE: Final = time(15, 45)

CaptureCycleAction = Literal["input_observer", "outcome_witness", "outside_cycle_slot"]
SourceStoreResult = (
    KisMtfProfiledProspectiveStoreResult | KisMtfProfiledForwardOutcomeStoreResult
)


@dataclass(frozen=True, slots=True)
class ProfiledMtfForwardCaptureCycleResult:
    """One source-safe delegation result with no new persistence format."""

    action: CaptureCycleAction
    source_result: SourceStoreResult | None = field(repr=False)

    def __post_init__(self) -> None:
        if self.action == "outside_cycle_slot":
            if self.source_result is not None:
                raise ValueError("outside capture-cycle result cannot have a source result")
            return
        if self.action == "input_observer" and not isinstance(
            self.source_result, KisMtfProfiledProspectiveStoreResult
        ):
            raise ValueError("input capture-cycle result is invalid")
        if self.action == "outcome_witness" and not isinstance(
            self.source_result, KisMtfProfiledForwardOutcomeStoreResult
        ):
            raise ValueError("outcome capture-cycle result is invalid")

    @property
    def status(self) -> str:
        if self.source_result is None:
            return "outside_cycle_slot"
        return str(self.source_result.safe_payload()["status"])

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": PROFILED_MTF_FORWARD_CAPTURE_CYCLE_ID,
            "action": self.action,
            "status": self.status,
        }
        if self.source_result is not None:
            payload["source_result"] = self.source_result.safe_payload()
        return payload


def select_profiled_mtf_forward_capture_cycle_action(
    observed_at: datetime,
) -> CaptureCycleAction:
    """Choose the one current-session action without loading cache data."""

    observed = require_utc(observed_at, "observed_at")
    eastern = observed.astimezone(US_EQUITY_EASTERN)
    session = us_equity_2026_session(eastern.date())
    local_time = eastern.time().replace(tzinfo=None)
    if session is None or session.kind != "regular":
        return "outside_cycle_slot"
    if PROFILED_MTF_FORWARD_CAPTURE_CYCLE_INPUT_CUTOFF <= local_time < (
        PROFILED_MTF_FORWARD_CAPTURE_CYCLE_OUTCOME_DUE
    ):
        return "input_observer"
    if local_time >= PROFILED_MTF_FORWARD_CAPTURE_CYCLE_OUTCOME_DUE:
        return "outcome_witness"
    return "outside_cycle_slot"


def run_profiled_mtf_forward_capture_cycle(
    *,
    historical_cache_root: Path | str,
    head_cache_root: Path | str,
    market_data_root: Path | str,
    artifact_root: Path | str,
    repo_root: Path | str,
    code_revision: str,
    observed_at: datetime,
    catalog_loader: CatalogLoader,
) -> ProfiledMtfForwardCaptureCycleResult:
    """Invoke only the selected existing local-cache action for one UTC instant."""

    action = select_profiled_mtf_forward_capture_cycle_action(observed_at)
    if action == "outside_cycle_slot":
        return ProfiledMtfForwardCaptureCycleResult(action=action, source_result=None)
    common = {
        "historical_cache_root": historical_cache_root,
        "head_cache_root": head_cache_root,
        "artifact_root": artifact_root,
        "repo_root": repo_root,
        "code_revision": code_revision,
        "observed_at": observed_at,
        "catalog_loader": catalog_loader,
    }
    if action == "input_observer":
        result = run_kis_mtf_profiled_prospective_observer(**common)
        if result is None:
            raise ValueError("input observer no longer matches capture-cycle slot")
        return ProfiledMtfForwardCaptureCycleResult(action=action, source_result=result)
    result = run_kis_mtf_profiled_forward_outcome_witness(
        **common,
        market_data_root=market_data_root,
    )
    if result is None:
        raise ValueError("outcome witness no longer matches capture-cycle slot")
    return ProfiledMtfForwardCaptureCycleResult(action=action, source_result=result)

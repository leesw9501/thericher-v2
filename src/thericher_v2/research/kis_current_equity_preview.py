"""Pure fixed-component PREVIEW of the frozen October 9, 2026 entry plan.

The caller binds the official calendar, opaque-key registry, source and hashes.
Observation clocks describe when that source was actually seen, not historical
decision-time availability. Callbacks must expose only the pinned past source.
This module does not load data, read targets, fit models or create Paper inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import Bar, require_utc
from thericher_v2.research import kis_pooled_equity_components as core

ENTRY_SESSION = date(2026, 10, 9)
PAST_SESSION_COUNT = 61
COMPONENT_CONTEXT = 20


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name}_must_be_aware_UTC")
    return require_utc(value, name)


@dataclass(frozen=True, slots=True)
class CurrentEquityPreview:
    """Source-safe result; zero preview weights are not liquidation instructions."""

    plan_keys: tuple[str, ...]
    eligible_keys: tuple[str, ...]
    unavailable_keys: tuple[str, ...]
    missing_observation_keys: tuple[str, ...]
    selected_keys: tuple[str, ...]
    weights: tuple[tuple[str, Decimal], ...]
    required_sessions: tuple[date, ...]
    nominal_decision_close_at: datetime
    nominal_entry_open_at: datetime
    nominal_target_close_at: datetime
    source_observed_at: tuple[tuple[str, datetime | None], ...]
    preview_at: datetime
    past_source_call_count: int

    @property
    def status(self) -> str:
        return "top10_preview" if self.selected_keys else "flat_preview"

    @property
    def historical_decision_time_availability(self) -> str:
        return "not_observed"

    @property
    def latest_source_observed_at(self) -> datetime | None:
        return max(
            (clock for _, clock in self.source_observed_at if clock is not None), default=None
        )

    def source_safe_document(self) -> dict[str, object]:
        """Return a detached, deterministic JSON-compatible DTO without prices/scores."""
        latest = self.latest_source_observed_at
        return {
            "kind": "kis_current_equity_component_preview_v1",
            "status": self.status,
            "control": "component",
            "plan_keys": list(self.plan_keys),
            "eligible_keys": list(self.eligible_keys),
            "unavailable_keys": list(self.unavailable_keys),
            "missing_observation_keys": list(self.missing_observation_keys),
            "selected_keys": list(self.selected_keys),
            "weights": {key: str(weight) for key, weight in self.weights},
            "required_sessions": [day.isoformat() for day in self.required_sessions],
            "entry_session": ENTRY_SESSION.isoformat(),
            "nominal_decision_close_at": self.nominal_decision_close_at.isoformat(),
            "nominal_entry_open_at": self.nominal_entry_open_at.isoformat(),
            "nominal_target_close_at": self.nominal_target_close_at.isoformat(),
            "source_observed_at": {
                key: clock.isoformat() if clock is not None else None
                for key, clock in self.source_observed_at
            },
            "latest_source_observed_at": latest.isoformat() if latest is not None else None,
            "preview_at": self.preview_at.isoformat(),
            "historical_decision_time_availability": self.historical_decision_time_availability,
            "counts": {
                "plan_sessions": core.SESSION_COUNT,
                "required_past_sessions": len(self.required_sessions),
                "component_context": COMPONENT_CONTEXT,
                "top_k": core.TOP_K,
                "plan_keys": len(self.plan_keys),
                "eligible_keys": len(self.eligible_keys),
                "unavailable_keys": len(self.unavailable_keys),
                "missing_observation_keys": len(self.missing_observation_keys),
                "selected_keys": len(self.selected_keys),
                "past_source_calls": self.past_source_call_count,
            },
            "scope": {
                "preview_only": True,
                "paper_input": False,
                "liquidation_instruction": False,
                "profit_claim": False,
                "model_confidence_claim": False,
                "target_reads": False,
                "fits": False,
                "labels": False,
                "orders": False,
                "execution": False,
                "private_holdings": False,
            },
        }


def preview(
    plan: core.ComponentPlan,
    past_source: core.PastSource,
    source_observed_at: Mapping[str, datetime | None],
    *,
    preview_at: datetime,
) -> CurrentEquityPreview:
    """Reuse the last entry's causal snapshot and fixed component top-ten control.

    Absent observation clocks exclude only their keys. Invalid/future clocks
    reject this invocation before callbacks. Scheduled closes, not D1 end_ts,
    establish which past bars can have been completed by the observation time.
    """
    if not isinstance(plan, core.ComponentPlan) or plan.sessions[-1] != ENTRY_SESSION:
        raise ValueError("frozen_current_entry_plan_required")
    at = _utc(preview_at, "preview_at")
    entry_index = core.SESSION_COUNT - 1
    decision_close = plan.close_clocks[entry_index - 1]
    if at < decision_close:
        raise ValueError("preview_before_nominal_decision_close")
    if set(source_observed_at) - set(plan.keys):
        raise ValueError("observation_keys_outside_frozen_plan")
    observed = {}
    for key in plan.keys:
        clock = source_observed_at.get(key)
        if clock is not None:
            clock = _utc(clock, "source_observed_at")
            if clock > at:
                raise ValueError("source_observation_after_preview")
        observed[key] = clock
    sessions = plan.sessions[entry_index - PAST_SESSION_COUNT : entry_index]
    closes = dict(
        zip(
            sessions,
            plan.close_clocks[entry_index - PAST_SESSION_COUNT : entry_index],
            strict=True,
        )
    )
    call_count = 0

    def past(key: str, day: date) -> Bar | None:
        nonlocal call_count
        if key not in observed or day not in closes:
            raise ValueError("past_callback_outside_frozen_window")
        clock = observed[key]
        if clock is None or closes[day] > clock:
            return None
        call_count += 1
        return past_source(key, day)

    state = core.snapshot(plan, entry_index, past)
    selected = core.controls(state)["component"].selected_keys
    return CurrentEquityPreview(
        plan.keys,
        state.eligible_keys,
        state.unavailable_keys,
        tuple(key for key in plan.keys if observed[key] is None),
        selected,
        tuple((key, Decimal("0.1") if key in selected else Decimal(0)) for key in plan.keys),
        sessions,
        state.decision_at,
        state.entry_open_at,
        state.target_close_at,
        tuple(observed.items()),
        at,
        call_count,
    )

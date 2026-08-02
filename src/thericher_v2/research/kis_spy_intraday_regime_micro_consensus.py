"""Offline five-timeframe SPY regime and micro-consensus falsification.

Raw bars, decision timestamps, and target returns remain process-local. External
artifacts contain only immutable source identity, frozen contract facts, counts,
and aggregate outcomes for this non-promoting research package.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import (
    require_complete_kis_paper_private_intraday_session,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_ID = "kis-spy-intraday-regime-micro-consensus-v1"
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_SYMBOL = "SPY"
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MARKET = "US"
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_DEVELOPMENT_SESSIONS = 10
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_PURGE_SESSIONS = 1
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_VALIDATION_SESSIONS = 10
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MIN_VALIDATION_ACTIVE = 30
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_FIRST_OFFSET = timedelta(hours=3)
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_LAST_OFFSET = timedelta(hours=6)
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_DECISION_STEP = timedelta(minutes=10)
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_HOLD = timedelta(minutes=10)
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_M1_RETURN_LOOKBACK = 30
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_M1_REQUIRED_BARS = 31
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_COST_BAND = (
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_PRIMARY_COST = Decimal("10")
KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_KILL_COST = Decimal("20")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

InputStatus = Literal["ready", "input_unavailable"]
ResultStatus = Literal["input_unavailable", "falsified", "non_promoting_validation"]
PhaseName = Literal["development", "validation"]


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusConfig:
    """The fixed causal geometry for this one source-local rule."""

    development_sessions: int = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_DEVELOPMENT_SESSIONS
    purge_sessions: int = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_PURGE_SESSIONS
    validation_sessions: int = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_VALIDATION_SESSIONS
    minimum_validation_active: int = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MIN_VALIDATION_ACTIVE
    first_offset: timedelta = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_FIRST_OFFSET
    last_offset: timedelta = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_LAST_OFFSET
    decision_step: timedelta = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_DECISION_STEP
    hold: timedelta = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_HOLD
    m1_return_lookback: int = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_M1_RETURN_LOOKBACK
    cost_band: tuple[Decimal, ...] = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_COST_BAND
    primary_cost: Decimal = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_PRIMARY_COST
    kill_cost: Decimal = KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_KILL_COST
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_sessions
            != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_DEVELOPMENT_SESSIONS
            or self.purge_sessions != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_PURGE_SESSIONS
            or self.validation_sessions
            != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_VALIDATION_SESSIONS
            or self.minimum_validation_active
            != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MIN_VALIDATION_ACTIVE
            or self.first_offset != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_FIRST_OFFSET
            or self.last_offset != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_LAST_OFFSET
            or self.decision_step != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_DECISION_STEP
            or self.hold != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_HOLD
            or self.m1_return_lookback != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_M1_RETURN_LOOKBACK
            or self.cost_band != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_COST_BAND
            or self.primary_cost != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_PRIMARY_COST
            or self.kill_cost != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_KILL_COST
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("SPY regime micro-consensus config is frozen")
        if self.first_offset >= self.last_offset or self.hold != self.decision_step:
            raise ValueError("SPY regime micro-consensus timing is invalid")

    @property
    def complete_session_count(self) -> int:
        return self.development_sessions + self.purge_sessions + self.validation_sessions

    @property
    def m1_required_bars(self) -> int:
        return self.m1_return_lookback + 1

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_ID,
            "decision_time": "completed_session_bar_boundary",
            "decision_schedule": {
                "first_offset_minutes": int(self.first_offset.total_seconds() // 60),
                "last_offset_minutes": int(self.last_offset.total_seconds() // 60),
                "step_minutes": int(self.decision_step.total_seconds() // 60),
                "timezone": "America/New_York",
            },
            "feature_windows": {
                "m1_completed_bars": self.m1_required_bars,
                "m1_close_to_close_lookback_minutes": self.m1_return_lookback,
                "m5_latest_completed_bar": True,
                "m10_latest_completed_bar": True,
                "h1_latest_completed_bar": True,
                "h3_latest_completed_bar": True,
            },
            "macro_regime": "completed_h3_and_h1_close_above_own_open",
            "micro_score": {
                "components": [
                    "completed_m10_close_above_open",
                    "completed_m5_close_above_open",
                    "completed_m1_close_above_close_30_minutes_earlier",
                ],
                "minimum": 1,
            },
            "target": "decision_t_next_m1_open_to_t_plus_10m_m1_open",
            "target_non_overlapping": True,
            "split": {
                "development_sessions": self.development_sessions,
                "purge_sessions": self.purge_sessions,
                "validation_sessions": self.validation_sessions,
                "development_target_access": "prohibited",
            },
            "minimum_validation_active_decisions": self.minimum_validation_active,
            "cost": {
                "all_in_round_trip_bps": [_decimal_text(cost) for cost in self.cost_band],
                "primary_all_in_round_trip_bps": _decimal_text(self.primary_cost),
                "kill_all_in_round_trip_bps": _decimal_text(self.kill_cost),
            },
            "comparators": {
                "flat": "always_flat",
                "macro_regime": "all_macro_ready_decisions_mean_net_bps_per_active_decision",
                "schedule_wide_always_long": "descriptive_only",
            },
            "kill_rule": (
                "candidate_net_total_flat_or_worse_at_20bp_or_candidate_mean_no_better_than_"
                "macro_regime_across_cost_band"
            ),
            "gpu_eligible": False,
            "paper_input_eligible": False,
            "promotion_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusSource:
    """Source identity without a path, row, timestamp, or raw value."""

    dataset_id: str
    dataset_hash: str

    def __post_init__(self) -> None:
        if not self.dataset_id.startswith(
            "kis.paper.private.intraday.spy.ams.m1."
        ) or not _is_sha256(self.dataset_hash):
            raise ValueError("SPY regime micro-consensus source is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "symbol": KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_SYMBOL,
            "market": KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MARKET,
            "source_scope": "verified_local_private_kis_cache_offline_only",
            "point_in_time_claim_allowed": False,
            "paper_input_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusPhaseFacts:
    """Aggregate feature-only decision facts for one chronological phase."""

    phase: PhaseName
    session_count: int
    scheduled_decision_count: int
    structural_unavailable_count: int
    macro_rejected_count: int
    micro_rejected_count: int
    active_decision_count: int

    def __post_init__(self) -> None:
        values = (
            self.session_count,
            self.scheduled_decision_count,
            self.structural_unavailable_count,
            self.macro_rejected_count,
            self.micro_rejected_count,
            self.active_decision_count,
        )
        if (
            self.phase not in {"development", "validation"}
            or min(values) < 0
            or self.scheduled_decision_count
            != self.structural_unavailable_count
            + self.macro_rejected_count
            + self.micro_rejected_count
            + self.active_decision_count
        ):
            raise ValueError("SPY regime micro-consensus phase facts are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "session_count": self.session_count,
            "scheduled_decision_count": self.scheduled_decision_count,
            "structural_unavailable_count": self.structural_unavailable_count,
            "macro_rejected_count": self.macro_rejected_count,
            "micro_rejected_count": self.micro_rejected_count,
            "active_decision_count": self.active_decision_count,
        }


@dataclass(frozen=True, slots=True)
class _DecisionContext:
    """Private target locator; target price fields are never read in preparation."""

    session_index: int
    entry_index: int

    def __post_init__(self) -> None:
        if self.session_index < 0 or self.entry_index < 0:
            raise ValueError("SPY regime micro-consensus decision context is invalid")


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusInput:
    """Prepared causal contexts; validation target fields remain inaccessible until evaluation."""

    source: KisSpyIntradayRegimeMicroConsensusSource
    config: KisSpyIntradayRegimeMicroConsensusConfig
    status: InputStatus
    reason: str | None
    complete_regular_session_count: int
    development: KisSpyIntradayRegimeMicroConsensusPhaseFacts
    validation: KisSpyIntradayRegimeMicroConsensusPhaseFacts
    input_hash: str
    _validation_sessions: tuple[tuple[Bar, ...], ...] = field(repr=False)
    _schedule_contexts: tuple[_DecisionContext, ...] = field(repr=False)
    _macro_contexts: tuple[_DecisionContext, ...] = field(repr=False)
    _candidate_contexts: tuple[_DecisionContext, ...] = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        sessions = tuple(tuple(session) for session in self._validation_sessions)
        schedule = tuple(self._schedule_contexts)
        macro = tuple(self._macro_contexts)
        candidates = tuple(self._candidate_contexts)
        if (
            self.status not in {"ready", "input_unavailable"}
            or self.complete_regular_session_count < 0
            or self.schema_version != SCHEMA_VERSION
            or not _is_sha256(self.input_hash)
        ):
            raise ValueError("SPY regime micro-consensus input is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or len(sessions) != self.config.validation_sessions
                or len(schedule) > self.validation.scheduled_decision_count
                or len(macro) != self.validation.micro_rejected_count + len(candidates)
                or len(candidates) != self.validation.active_decision_count
                or len(candidates) < self.config.minimum_validation_active
            ):
                raise ValueError("ready SPY regime micro-consensus input is invalid")
            if any(
                len(session) == 0
                or any(
                    bar.symbol != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_SYMBOL
                    or bar.market != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MARKET
                    or bar.timeframe != Timeframe.M1
                    or not bar.complete
                    for bar in session
                )
                for session in sessions
            ):
                raise ValueError("SPY regime micro-consensus validation sessions are invalid")
            _validate_contexts(schedule, sessions, self.config)
            _validate_contexts(macro, sessions, self.config)
            _validate_contexts(candidates, sessions, self.config)
        elif (
            self.reason
            not in {
                "insufficient_complete_regular_sessions",
                "insufficient_validation_active_decisions",
            }
            or sessions
            or schedule
            or macro
            or candidates
        ):
            raise ValueError("unavailable SPY regime micro-consensus input is invalid")
        expected_hash = _input_hash(
            source=self.source,
            config=self.config,
            status=self.status,
            reason=self.reason,
            complete_regular_session_count=self.complete_regular_session_count,
            development=self.development,
            validation=self.validation,
        )
        if self.input_hash != expected_hash:
            raise ValueError("SPY regime micro-consensus input identity is invalid")
        object.__setattr__(self, "_validation_sessions", sessions)
        object.__setattr__(self, "_schedule_contexts", schedule)
        object.__setattr__(self, "_macro_contexts", macro)
        object.__setattr__(self, "_candidate_contexts", candidates)

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_ID,
            "source": self.source.safe_payload(),
            "contract": self.config.safe_payload(),
            "status": self.status,
            "reason": self.reason,
            "complete_regular_session_count": self.complete_regular_session_count,
            "phases": [self.development.safe_payload(), self.validation.safe_payload()],
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusValidation:
    """Aggregate post-preflight outcomes without individual timestamps or returns."""

    candidate_active_decision_count: int
    macro_regime_decision_count: int
    schedule_wide_decision_count: int
    candidate_net_total_bps_by_cost: Mapping[str, Decimal]
    candidate_net_mean_bps_by_cost: Mapping[str, Decimal]
    macro_regime_net_total_bps_by_cost: Mapping[str, Decimal]
    macro_regime_net_mean_bps_by_cost: Mapping[str, Decimal]
    schedule_wide_net_total_bps_by_cost: Mapping[str, Decimal]
    schedule_wide_net_mean_bps_by_cost: Mapping[str, Decimal]
    kill_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kill_reasons", tuple(self.kill_reasons))
        mappings = (
            self.candidate_net_total_bps_by_cost,
            self.candidate_net_mean_bps_by_cost,
            self.macro_regime_net_total_bps_by_cost,
            self.macro_regime_net_mean_bps_by_cost,
            self.schedule_wide_net_total_bps_by_cost,
            self.schedule_wide_net_mean_bps_by_cost,
        )
        expected_costs = tuple(
            _decimal_text(cost) for cost in KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_COST_BAND
        )
        valid_reasons = {
            "candidate_net_total_flat_or_worse_at_20bp",
            "candidate_mean_no_better_than_macro_regime_across_cost_band",
        }
        if (
            self.candidate_active_decision_count
            < KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MIN_VALIDATION_ACTIVE
            or self.macro_regime_decision_count < self.candidate_active_decision_count
            or self.schedule_wide_decision_count < self.macro_regime_decision_count
            or any(tuple(mapping) != expected_costs for mapping in mappings)
            or any(not value.is_finite() for mapping in mappings for value in mapping.values())
            or any(reason not in valid_reasons for reason in self.kill_reasons)
        ):
            raise ValueError("SPY regime micro-consensus validation is invalid")
        for name, mapping in (
            ("candidate_net_total_bps_by_cost", self.candidate_net_total_bps_by_cost),
            ("candidate_net_mean_bps_by_cost", self.candidate_net_mean_bps_by_cost),
            ("macro_regime_net_total_bps_by_cost", self.macro_regime_net_total_bps_by_cost),
            ("macro_regime_net_mean_bps_by_cost", self.macro_regime_net_mean_bps_by_cost),
            ("schedule_wide_net_total_bps_by_cost", self.schedule_wide_net_total_bps_by_cost),
            ("schedule_wide_net_mean_bps_by_cost", self.schedule_wide_net_mean_bps_by_cost),
        ):
            object.__setattr__(self, name, MappingProxyType(dict(mapping)))

    def safe_payload(self) -> dict[str, object]:
        return {
            "candidate_active_decision_count": self.candidate_active_decision_count,
            "macro_regime_decision_count": self.macro_regime_decision_count,
            "schedule_wide_decision_count": self.schedule_wide_decision_count,
            "candidate_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.candidate_net_total_bps_by_cost
            ),
            "candidate_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.candidate_net_mean_bps_by_cost
            ),
            "macro_regime_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.macro_regime_net_total_bps_by_cost
            ),
            "macro_regime_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.macro_regime_net_mean_bps_by_cost
            ),
            "schedule_wide_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.schedule_wide_net_total_bps_by_cost
            ),
            "schedule_wide_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.schedule_wide_net_mean_bps_by_cost
            ),
            "schedule_wide_always_long": "descriptive_only",
            "kill_reasons": list(self.kill_reasons),
        }


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusResult:
    """One non-promoting result for the frozen source-local experiment."""

    campaign_input: KisSpyIntradayRegimeMicroConsensusInput
    status: ResultStatus
    validation: KisSpyIntradayRegimeMicroConsensusValidation | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"input_unavailable", "falsified", "non_promoting_validation"}:
            raise ValueError("SPY regime micro-consensus result status is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("SPY regime micro-consensus result schema is invalid")
        if self.status == "input_unavailable":
            if self.campaign_input.status != "input_unavailable" or self.validation is not None:
                raise ValueError("unavailable SPY regime micro-consensus result is invalid")
        elif (
            self.campaign_input.status != "ready"
            or self.validation is None
            or (self.status == "falsified") != bool(self.validation.kill_reasons)
        ):
            raise ValueError("evaluated SPY regime micro-consensus result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_ID,
            "status": self.status,
            "input": self.campaign_input.safe_payload(),
            "validation": None if self.validation is None else self.validation.safe_payload(),
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "gpu_eligible": False,
            "paper_input_allowed": False,
            "promotion_allowed": False,
            "profitability_claim_allowed": False,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class KisSpyIntradayRegimeMicroConsensusRun:
    """Immutable external paths for one deterministic run label."""

    result: KisSpyIntradayRegimeMicroConsensusResult
    precommit_path: Path
    precommit_hash: str
    summary_path: Path

    def __post_init__(self) -> None:
        if not _is_sha256(self.precommit_hash):
            raise ValueError("SPY regime micro-consensus precommit hash is invalid")


def prepare_kis_spy_intraday_regime_micro_consensus(
    catalog: CatalogedBars,
    *,
    config: KisSpyIntradayRegimeMicroConsensusConfig | None = None,
) -> KisSpyIntradayRegimeMicroConsensusInput:
    """Prepare feature-only contexts before any validation target price is accessed."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("SPY regime micro-consensus requires verified cataloged bars")
    resolved_config = config or KisSpyIntradayRegimeMicroConsensusConfig()
    source = KisSpyIntradayRegimeMicroConsensusSource(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
    )
    sessions = _complete_regular_sessions(catalog)
    if len(sessions) != resolved_config.complete_session_count:
        empty_development = _empty_phase("development")
        empty_validation = _empty_phase("validation")
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_complete_regular_sessions",
            complete_regular_session_count=len(sessions),
            development=empty_development,
            validation=empty_validation,
            validation_sessions=(),
            schedule_contexts=(),
            macro_contexts=(),
            candidate_contexts=(),
        )

    development_sessions = sessions[: resolved_config.development_sessions]
    validation_start = resolved_config.development_sessions + resolved_config.purge_sessions
    validation_sessions = sessions[validation_start:]
    development, _, _, _ = _phase_contexts(
        phase="development",
        sessions=development_sessions,
        config=resolved_config,
    )
    validation, schedule_contexts, macro_contexts, candidate_contexts = _phase_contexts(
        phase="validation",
        sessions=validation_sessions,
        config=resolved_config,
    )
    if validation.active_decision_count < resolved_config.minimum_validation_active:
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_validation_active_decisions",
            complete_regular_session_count=len(sessions),
            development=development,
            validation=validation,
            validation_sessions=(),
            schedule_contexts=(),
            macro_contexts=(),
            candidate_contexts=(),
        )
    return _campaign_input(
        source=source,
        config=resolved_config,
        status="ready",
        reason=None,
        complete_regular_session_count=len(sessions),
        development=development,
        validation=validation,
        validation_sessions=tuple(item[1] for item in validation_sessions),
        schedule_contexts=schedule_contexts,
        macro_contexts=macro_contexts,
        candidate_contexts=candidate_contexts,
    )


def evaluate_kis_spy_intraday_regime_micro_consensus(
    campaign_input: KisSpyIntradayRegimeMicroConsensusInput,
) -> KisSpyIntradayRegimeMicroConsensusResult:
    """Read validation target prices only after the fixed active-count preflight."""

    if not isinstance(campaign_input, KisSpyIntradayRegimeMicroConsensusInput):
        raise TypeError("SPY regime micro-consensus requires prepared input")
    if campaign_input.status == "input_unavailable":
        return KisSpyIntradayRegimeMicroConsensusResult(
            campaign_input=campaign_input,
            status="input_unavailable",
            validation=None,
        )
    validation = _validation_outcomes(campaign_input)
    return KisSpyIntradayRegimeMicroConsensusResult(
        campaign_input=campaign_input,
        status="falsified" if validation.kill_reasons else "non_promoting_validation",
        validation=validation,
    )


def run_kis_spy_intraday_regime_micro_consensus(
    catalog: CatalogedBars,
    *,
    artifact_root: Path | str,
    run_label: str,
    repo_root: Path | str,
) -> KisSpyIntradayRegimeMicroConsensusRun:
    """Prepare, evaluate, and write idempotent source-safe evidence externally."""

    resolved_label = _validated_run_label(run_label)
    root = _external_artifact_root(Path(artifact_root), Path(repo_root))
    campaign_input = prepare_kis_spy_intraday_regime_micro_consensus(catalog)
    precommit_payload = campaign_input.safe_payload()
    precommit_hash = _sha256_json(precommit_payload)
    result = evaluate_kis_spy_intraday_regime_micro_consensus(campaign_input)
    summary_payload = {
        "precommit_hash": precommit_hash,
        "result": result.safe_payload(),
    }
    artifact_dir = root / "research" / KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_ID / resolved_label
    _ensure_artifact_directory(root, artifact_dir)
    precommit_path = artifact_dir / "precommit.json"
    summary_path = artifact_dir / "summary.json"
    _write_or_verify(precommit_path, _canonical_json(precommit_payload))
    _write_or_verify(summary_path, _canonical_json(summary_payload))
    return KisSpyIntradayRegimeMicroConsensusRun(
        result=result,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def _complete_regular_sessions(
    catalog: CatalogedBars,
) -> tuple[tuple[SessionWindow, tuple[Bar, ...]], ...]:
    if not catalog.dataset_id.startswith("kis.paper.private.intraday.spy.ams.m1.") or any(
        bar.symbol != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_SYMBOL
        or bar.market != KIS_SPY_INTRADAY_REGIME_MICRO_CONSENSUS_MARKET
        or bar.timeframe != Timeframe.M1
        for bar in catalog.bars
    ):
        raise ValueError("SPY regime micro-consensus catalog scope is invalid")
    candidate_dates = tuple(
        sorted({bar.start_ts.astimezone(US_EQUITY_EASTERN).date() for bar in catalog.bars})
    )
    complete: list[tuple[SessionWindow, tuple[Bar, ...]]] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        try:
            selected = require_complete_kis_paper_private_intraday_session(
                catalog,
                session=session.window,
            )
        except ValueError:
            continue
        complete.append((session.window, selected.bars))
    return tuple(complete)


def _phase_contexts(
    *,
    phase: PhaseName,
    sessions: tuple[tuple[SessionWindow, tuple[Bar, ...]], ...],
    config: KisSpyIntradayRegimeMicroConsensusConfig,
) -> tuple[
    KisSpyIntradayRegimeMicroConsensusPhaseFacts,
    tuple[_DecisionContext, ...],
    tuple[_DecisionContext, ...],
    tuple[_DecisionContext, ...],
]:
    scheduled = 0
    structural_unavailable = 0
    macro_rejected = 0
    micro_rejected = 0
    schedule_contexts: list[_DecisionContext] = []
    macro_contexts: list[_DecisionContext] = []
    candidate_contexts: list[_DecisionContext] = []
    for session_index, (session, session_bars) in enumerate(sessions):
        for offset in _decision_offsets(config):
            scheduled += 1
            entry_index = int(offset // Timeframe.M1.duration)
            if entry_index + int(config.hold // Timeframe.M1.duration) >= len(session_bars):
                structural_unavailable += 1
                continue
            source_bars = session_bars[:entry_index]
            state = _decision_state(source_bars=source_bars, session=session, config=config)
            if state is None:
                structural_unavailable += 1
                continue
            context = _DecisionContext(session_index=session_index, entry_index=entry_index)
            schedule_contexts.append(context)
            macro_ready, micro_score = state
            if not macro_ready:
                macro_rejected += 1
                continue
            macro_contexts.append(context)
            if micro_score < 1:
                micro_rejected += 1
                continue
            candidate_contexts.append(context)
    facts = KisSpyIntradayRegimeMicroConsensusPhaseFacts(
        phase=phase,
        session_count=len(sessions),
        scheduled_decision_count=scheduled,
        structural_unavailable_count=structural_unavailable,
        macro_rejected_count=macro_rejected,
        micro_rejected_count=micro_rejected,
        active_decision_count=len(candidate_contexts),
    )
    return facts, tuple(schedule_contexts), tuple(macro_contexts), tuple(candidate_contexts)


def _decision_state(
    *,
    source_bars: tuple[Bar, ...],
    session: SessionWindow,
    config: KisSpyIntradayRegimeMicroConsensusConfig,
) -> tuple[bool, int] | None:
    if len(source_bars) < config.m1_required_bars:
        return None
    cutoff = source_bars[-1].end_ts
    resampled = {
        timeframe: resample_session_bars(source_bars, timeframe, session=session).bars
        for timeframe in (Timeframe.M5, Timeframe.M10, Timeframe.H1, Timeframe.H3)
    }
    if any(not resampled[timeframe] for timeframe in resampled):
        return None
    latest = {timeframe: resampled[timeframe][-1] for timeframe in resampled}
    if any(bar.end_ts > cutoff for bar in latest.values()):
        return None
    macro_ready = (
        latest[Timeframe.H3].close > latest[Timeframe.H3].open
        and latest[Timeframe.H1].close > latest[Timeframe.H1].open
    )
    micro_score = sum(
        (
            int(latest[Timeframe.M10].close > latest[Timeframe.M10].open),
            int(latest[Timeframe.M5].close > latest[Timeframe.M5].open),
            int(source_bars[-1].close > source_bars[-config.m1_required_bars].close),
        )
    )
    return macro_ready, micro_score


def _decision_offsets(
    config: KisSpyIntradayRegimeMicroConsensusConfig,
) -> tuple[timedelta, ...]:
    total = int((config.last_offset - config.first_offset) // config.decision_step)
    return tuple(config.first_offset + config.decision_step * index for index in range(total + 1))


def _empty_phase(phase: PhaseName) -> KisSpyIntradayRegimeMicroConsensusPhaseFacts:
    return KisSpyIntradayRegimeMicroConsensusPhaseFacts(
        phase=phase,
        session_count=0,
        scheduled_decision_count=0,
        structural_unavailable_count=0,
        macro_rejected_count=0,
        micro_rejected_count=0,
        active_decision_count=0,
    )


def _campaign_input(
    *,
    source: KisSpyIntradayRegimeMicroConsensusSource,
    config: KisSpyIntradayRegimeMicroConsensusConfig,
    status: InputStatus,
    reason: str | None,
    complete_regular_session_count: int,
    development: KisSpyIntradayRegimeMicroConsensusPhaseFacts,
    validation: KisSpyIntradayRegimeMicroConsensusPhaseFacts,
    validation_sessions: tuple[tuple[Bar, ...], ...],
    schedule_contexts: tuple[_DecisionContext, ...],
    macro_contexts: tuple[_DecisionContext, ...],
    candidate_contexts: tuple[_DecisionContext, ...],
) -> KisSpyIntradayRegimeMicroConsensusInput:
    return KisSpyIntradayRegimeMicroConsensusInput(
        source=source,
        config=config,
        status=status,
        reason=reason,
        complete_regular_session_count=complete_regular_session_count,
        development=development,
        validation=validation,
        input_hash=_input_hash(
            source=source,
            config=config,
            status=status,
            reason=reason,
            complete_regular_session_count=complete_regular_session_count,
            development=development,
            validation=validation,
        ),
        _validation_sessions=validation_sessions,
        _schedule_contexts=schedule_contexts,
        _macro_contexts=macro_contexts,
        _candidate_contexts=candidate_contexts,
    )


def _validate_contexts(
    contexts: tuple[_DecisionContext, ...],
    sessions: tuple[tuple[Bar, ...], ...],
    config: KisSpyIntradayRegimeMicroConsensusConfig,
) -> None:
    hold_bars = int(config.hold // Timeframe.M1.duration)
    for context in contexts:
        if context.session_index >= len(sessions):
            raise ValueError("SPY regime micro-consensus context session is invalid")
        bars = sessions[context.session_index]
        if context.entry_index + hold_bars >= len(bars):
            raise ValueError("SPY regime micro-consensus context target is invalid")
        entry = bars[context.entry_index]
        exit_bar = bars[context.entry_index + hold_bars]
        if entry.start_ts + config.hold != exit_bar.start_ts or entry.end_ts > exit_bar.start_ts:
            raise ValueError("SPY regime micro-consensus context timing is invalid")


def _validation_outcomes(
    campaign_input: KisSpyIntradayRegimeMicroConsensusInput,
) -> KisSpyIntradayRegimeMicroConsensusValidation:
    candidate = _aggregate_contexts(
        contexts=campaign_input._candidate_contexts,
        sessions=campaign_input._validation_sessions,
        config=campaign_input.config,
    )
    macro = _aggregate_contexts(
        contexts=campaign_input._macro_contexts,
        sessions=campaign_input._validation_sessions,
        config=campaign_input.config,
    )
    schedule = _aggregate_contexts(
        contexts=campaign_input._schedule_contexts,
        sessions=campaign_input._validation_sessions,
        config=campaign_input.config,
    )
    kill_reasons: list[str] = []
    kill_key = _decimal_text(campaign_input.config.kill_cost)
    if candidate["total"][kill_key] <= 0:
        kill_reasons.append("candidate_net_total_flat_or_worse_at_20bp")
    costs = tuple(_decimal_text(cost) for cost in campaign_input.config.cost_band)
    if all(candidate["mean"][cost] <= macro["mean"][cost] for cost in costs):
        kill_reasons.append("candidate_mean_no_better_than_macro_regime_across_cost_band")
    return KisSpyIntradayRegimeMicroConsensusValidation(
        candidate_active_decision_count=len(campaign_input._candidate_contexts),
        macro_regime_decision_count=len(campaign_input._macro_contexts),
        schedule_wide_decision_count=len(campaign_input._schedule_contexts),
        candidate_net_total_bps_by_cost=candidate["total"],
        candidate_net_mean_bps_by_cost=candidate["mean"],
        macro_regime_net_total_bps_by_cost=macro["total"],
        macro_regime_net_mean_bps_by_cost=macro["mean"],
        schedule_wide_net_total_bps_by_cost=schedule["total"],
        schedule_wide_net_mean_bps_by_cost=schedule["mean"],
        kill_reasons=tuple(kill_reasons),
    )


def _aggregate_contexts(
    *,
    contexts: tuple[_DecisionContext, ...],
    sessions: tuple[tuple[Bar, ...], ...],
    config: KisSpyIntradayRegimeMicroConsensusConfig,
) -> dict[str, Mapping[str, Decimal]]:
    if not contexts:
        raise ValueError("SPY regime micro-consensus aggregate requires active contexts")
    gross_returns = tuple(
        _target_return_bps(
            sessions[context.session_index],
            entry_index=context.entry_index,
            config=config,
        )
        for context in contexts
    )
    totals: dict[str, Decimal] = {}
    means: dict[str, Decimal] = {}
    count = Decimal(len(gross_returns))
    for cost in config.cost_band:
        key = _decimal_text(cost)
        total = sum((gross - cost for gross in gross_returns), Decimal("0"))
        totals[key] = total
        means[key] = total / count
    return {"total": MappingProxyType(totals), "mean": MappingProxyType(means)}


def _target_return_bps(
    bars: tuple[Bar, ...],
    *,
    entry_index: int,
    config: KisSpyIntradayRegimeMicroConsensusConfig,
) -> Decimal:
    hold_bars = int(config.hold // Timeframe.M1.duration)
    entry = bars[entry_index]
    exit_bar = bars[entry_index + hold_bars]
    if entry.open <= 0 or entry.start_ts + config.hold != exit_bar.start_ts:
        raise ValueError("SPY regime micro-consensus target is invalid")
    return (exit_bar.open / entry.open - Decimal("1")) * Decimal("10000")


def _input_hash(
    *,
    source: KisSpyIntradayRegimeMicroConsensusSource,
    config: KisSpyIntradayRegimeMicroConsensusConfig,
    status: InputStatus,
    reason: str | None,
    complete_regular_session_count: int,
    development: KisSpyIntradayRegimeMicroConsensusPhaseFacts,
    validation: KisSpyIntradayRegimeMicroConsensusPhaseFacts,
) -> str:
    return _sha256_json(
        {
            "source": source.safe_payload(),
            "contract": config.safe_payload(),
            "status": status,
            "reason": reason,
            "complete_regular_session_count": complete_regular_session_count,
            "phases": [development.safe_payload(), validation.safe_payload()],
        }
    )


def _validated_run_label(run_label: str) -> str:
    if not isinstance(run_label, str) or not _SAFE_RUN_LABEL.fullmatch(run_label):
        raise ValueError("SPY regime micro-consensus run label is invalid")
    return run_label


def _external_artifact_root(artifact_root: Path, repo_root: Path) -> Path:
    root = artifact_root.resolve(strict=False)
    repository = repo_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    if root.is_relative_to(repository) and not (
        repository == docker_repository and root.is_relative_to(docker_artifacts)
    ):
        raise ValueError("SPY regime micro-consensus artifacts must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("SPY regime micro-consensus artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _ensure_artifact_directory(root: Path, artifact_dir: Path) -> None:
    if artifact_dir.exists() and (artifact_dir.is_symlink() or not artifact_dir.is_dir()):
        raise ValueError("SPY regime micro-consensus artifact directory is invalid")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not artifact_dir.resolve(strict=False).is_relative_to(root):
        raise ValueError("SPY regime micro-consensus artifact directory is invalid")


def _write_or_verify(path: Path, encoded: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise ValueError("SPY regime micro-consensus artifact conflicts with evidence")
        return
    staging = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.stage")
    try:
        staging.write_bytes(encoded)
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _safe_cost_mapping(values: Mapping[str, Decimal]) -> dict[str, str]:
    return {cost: _decimal_text(values[cost]) for cost in values}


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")

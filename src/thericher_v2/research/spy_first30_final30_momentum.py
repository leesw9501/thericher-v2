"""Offline first-30m to final-30m SPY momentum falsification.

Raw bars and per-session returns stay process-local. External evidence contains
only source identity, frozen contract facts, aggregate counts, and aggregate
outcomes. This is a small source-local replication, never a promotion claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_paper_intraday import (
    require_complete_kis_paper_private_intraday_session,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

SPY_FIRST30_FINAL30_MOMENTUM_ID = "spy-first30-final30-momentum-v1"
SPY_FIRST30_FINAL30_MOMENTUM_SYMBOL = "SPY"
SPY_FIRST30_FINAL30_MOMENTUM_MARKET = "US"
SPY_FIRST30_FINAL30_MOMENTUM_DEVELOPMENT_SESSIONS = 10
SPY_FIRST30_FINAL30_MOMENTUM_PURGE_SESSIONS = 1
SPY_FIRST30_FINAL30_MOMENTUM_VALIDATION_SESSIONS = 10
SPY_FIRST30_FINAL30_MOMENTUM_MIN_VALIDATION_ACTIVE = 8
SPY_FIRST30_FINAL30_MOMENTUM_FIRST_WINDOW_BARS = 30
SPY_FIRST30_FINAL30_MOMENTUM_ENTRY_INDEX = 360
SPY_FIRST30_FINAL30_MOMENTUM_EXIT_INDEX = 389
SPY_FIRST30_FINAL30_MOMENTUM_COST_BAND = (
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)
SPY_FIRST30_FINAL30_MOMENTUM_KILL_COST = Decimal("20")
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

InputStatus = Literal["ready", "input_unavailable"]
ResultStatus = Literal["input_unavailable", "falsified", "non_promoting_validation"]
PhaseName = Literal["development", "validation"]


@dataclass(frozen=True, slots=True)
class SpyFirst30Final30MomentumConfig:
    """The fixed causal geometry for this narrow source-local replication."""

    development_sessions: int = SPY_FIRST30_FINAL30_MOMENTUM_DEVELOPMENT_SESSIONS
    purge_sessions: int = SPY_FIRST30_FINAL30_MOMENTUM_PURGE_SESSIONS
    validation_sessions: int = SPY_FIRST30_FINAL30_MOMENTUM_VALIDATION_SESSIONS
    minimum_validation_active: int = SPY_FIRST30_FINAL30_MOMENTUM_MIN_VALIDATION_ACTIVE
    first_window_bars: int = SPY_FIRST30_FINAL30_MOMENTUM_FIRST_WINDOW_BARS
    entry_index: int = SPY_FIRST30_FINAL30_MOMENTUM_ENTRY_INDEX
    exit_index: int = SPY_FIRST30_FINAL30_MOMENTUM_EXIT_INDEX
    cost_band: tuple[Decimal, ...] = SPY_FIRST30_FINAL30_MOMENTUM_COST_BAND
    kill_cost: Decimal = SPY_FIRST30_FINAL30_MOMENTUM_KILL_COST
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_sessions != SPY_FIRST30_FINAL30_MOMENTUM_DEVELOPMENT_SESSIONS
            or self.purge_sessions != SPY_FIRST30_FINAL30_MOMENTUM_PURGE_SESSIONS
            or self.validation_sessions != SPY_FIRST30_FINAL30_MOMENTUM_VALIDATION_SESSIONS
            or self.minimum_validation_active != SPY_FIRST30_FINAL30_MOMENTUM_MIN_VALIDATION_ACTIVE
            or self.first_window_bars != SPY_FIRST30_FINAL30_MOMENTUM_FIRST_WINDOW_BARS
            or self.entry_index != SPY_FIRST30_FINAL30_MOMENTUM_ENTRY_INDEX
            or self.exit_index != SPY_FIRST30_FINAL30_MOMENTUM_EXIT_INDEX
            or self.cost_band != SPY_FIRST30_FINAL30_MOMENTUM_COST_BAND
            or self.kill_cost != SPY_FIRST30_FINAL30_MOMENTUM_KILL_COST
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("SPY first-30m/final-30m config is frozen")
        if self.first_window_bars <= 0 or not 0 <= self.entry_index < self.exit_index:
            raise ValueError("SPY first-30m/final-30m timing is invalid")
        if self.kill_cost not in self.cost_band:
            raise ValueError("SPY first-30m/final-30m kill cost is invalid")

    @property
    def complete_session_count(self) -> int:
        return self.development_sessions + self.purge_sessions + self.validation_sessions

    def safe_payload(self) -> dict[str, object]:
        return {
            "campaign_id": SPY_FIRST30_FINAL30_MOMENTUM_ID,
            "research_source": {
                "doi": "10.1016/j.jfineco.2018.05.009",
                "name": "gao_han_li_zhou_2018_market_intraday_momentum",
                "stated_spy_sample": "1993_to_2013",
            },
            "decision_time": "completed_1000_et_first_30m_boundary",
            "input": {
                "prior_session": "completed_1600_et_final_m1_close",
                "current_session": "completed_0930_to_1000_et_first_30m_close",
                "direction": "sign_current_first_30m_return_from_prior_close",
            },
            "target": {
                "entry": "1530_et_m1_open",
                "exit": "completed_1600_et_final_m1_close",
                "signed": True,
            },
            "split": {
                "development_sessions": self.development_sessions,
                "purge_sessions": self.purge_sessions,
                "validation_sessions": self.validation_sessions,
                "development_target_access": "prohibited",
            },
            "minimum_validation_active_decisions": self.minimum_validation_active,
            "cost": {
                "all_in_round_trip_bps": [_decimal_text(cost) for cost in self.cost_band],
                "kill_all_in_round_trip_bps": _decimal_text(self.kill_cost),
            },
            "comparators": {
                "flat": "always_flat",
                "direction_inverted": "same_timestamp_opposite_signed_return",
            },
            "kill_rule": "candidate_signed_net_total_flat_or_worse_at_20bp",
            "gpu_eligible": False,
            "paper_input_eligible": False,
            "promotion_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class SpyFirst30Final30MomentumSource:
    """Pinned source identity without a cache path, row, timestamp, or value."""

    dataset_id: str
    dataset_hash: str

    def __post_init__(self) -> None:
        if not self.dataset_id.startswith(
            "kis.paper.private.intraday.spy.ams.m1."
        ) or not _is_sha256(self.dataset_hash):
            raise ValueError("SPY first-30m/final-30m source is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "symbol": SPY_FIRST30_FINAL30_MOMENTUM_SYMBOL,
            "market": SPY_FIRST30_FINAL30_MOMENTUM_MARKET,
            "source_scope": "verified_local_private_kis_cache_offline_only",
            "point_in_time_claim_allowed": False,
            "paper_input_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class SpyFirst30Final30MomentumPhaseFacts:
    """Feature-only decision facts; no final-window target value is present."""

    phase: PhaseName
    session_count: int
    scheduled_decision_count: int
    structural_unavailable_count: int
    zero_direction_count: int
    active_decision_count: int

    def __post_init__(self) -> None:
        values = (
            self.session_count,
            self.scheduled_decision_count,
            self.structural_unavailable_count,
            self.zero_direction_count,
            self.active_decision_count,
        )
        if (
            self.phase not in {"development", "validation"}
            or min(values) < 0
            or self.scheduled_decision_count
            != self.structural_unavailable_count
            + self.zero_direction_count
            + self.active_decision_count
        ):
            raise ValueError("SPY first-30m/final-30m phase facts are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "session_count": self.session_count,
            "scheduled_decision_count": self.scheduled_decision_count,
            "structural_unavailable_count": self.structural_unavailable_count,
            "zero_direction_count": self.zero_direction_count,
            "active_decision_count": self.active_decision_count,
        }


@dataclass(frozen=True, slots=True)
class _DecisionContext:
    """Private locator and frozen signal; target OHLC values are absent here."""

    session_index: int
    direction: int

    def __post_init__(self) -> None:
        if self.session_index < 0 or self.direction not in {-1, 1}:
            raise ValueError("SPY first-30m/final-30m decision context is invalid")


@dataclass(frozen=True, slots=True)
class SpyFirst30Final30MomentumInput:
    """Prepared inputs where validation target values are inaccessible until evaluation."""

    source: SpyFirst30Final30MomentumSource
    config: SpyFirst30Final30MomentumConfig
    status: InputStatus
    reason: str | None
    complete_regular_session_count: int
    development: SpyFirst30Final30MomentumPhaseFacts
    validation: SpyFirst30Final30MomentumPhaseFacts
    input_hash: str
    _validation_sessions: tuple[tuple[Bar, ...], ...] = field(repr=False)
    _candidate_contexts: tuple[_DecisionContext, ...] = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        sessions = tuple(tuple(session) for session in self._validation_sessions)
        contexts = tuple(self._candidate_contexts)
        if (
            self.status not in {"ready", "input_unavailable"}
            or self.complete_regular_session_count < 0
            or self.schema_version != SCHEMA_VERSION
            or not _is_sha256(self.input_hash)
        ):
            raise ValueError("SPY first-30m/final-30m input is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or len(sessions) != self.config.validation_sessions
                or len(contexts) != self.validation.active_decision_count
                or len(contexts) < self.config.minimum_validation_active
            ):
                raise ValueError("ready SPY first-30m/final-30m input is invalid")
            if any(
                len(session) <= self.config.exit_index
                or any(
                    bar.symbol != SPY_FIRST30_FINAL30_MOMENTUM_SYMBOL
                    or bar.market != SPY_FIRST30_FINAL30_MOMENTUM_MARKET
                    or bar.timeframe != Timeframe.M1
                    or not bar.complete
                    for bar in session
                )
                for session in sessions
            ):
                raise ValueError("SPY first-30m/final-30m validation sessions are invalid")
            _validate_contexts(contexts, sessions, self.config)
        elif (
            self.reason
            not in {
                "insufficient_complete_regular_sessions",
                "insufficient_validation_active_decisions",
            }
            or sessions
            or contexts
        ):
            raise ValueError("unavailable SPY first-30m/final-30m input is invalid")
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
            raise ValueError("SPY first-30m/final-30m input identity is invalid")
        object.__setattr__(self, "_validation_sessions", sessions)
        object.__setattr__(self, "_candidate_contexts", contexts)

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": SPY_FIRST30_FINAL30_MOMENTUM_ID,
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
class SpyFirst30Final30MomentumValidation:
    """Aggregate signed and direction-inverted outcomes only."""

    candidate_active_decision_count: int
    direction_inverted_decision_count: int
    candidate_net_total_bps_by_cost: Mapping[str, Decimal]
    candidate_net_mean_bps_by_cost: Mapping[str, Decimal]
    direction_inverted_net_total_bps_by_cost: Mapping[str, Decimal]
    direction_inverted_net_mean_bps_by_cost: Mapping[str, Decimal]
    kill_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kill_reasons", tuple(self.kill_reasons))
        mappings = (
            self.candidate_net_total_bps_by_cost,
            self.candidate_net_mean_bps_by_cost,
            self.direction_inverted_net_total_bps_by_cost,
            self.direction_inverted_net_mean_bps_by_cost,
        )
        expected_keys = tuple(
            _decimal_text(cost) for cost in SPY_FIRST30_FINAL30_MOMENTUM_COST_BAND
        )
        if (
            self.candidate_active_decision_count <= 0
            or self.direction_inverted_decision_count != self.candidate_active_decision_count
            or any(tuple(mapping) != expected_keys for mapping in mappings)
            or any(
                not isinstance(value, Decimal) for mapping in mappings for value in mapping.values()
            )
            or any(
                reason != "candidate_signed_net_total_flat_or_worse_at_20bp"
                for reason in self.kill_reasons
            )
        ):
            raise ValueError("SPY first-30m/final-30m validation is invalid")
        object.__setattr__(
            self,
            "candidate_net_total_bps_by_cost",
            MappingProxyType(dict(self.candidate_net_total_bps_by_cost)),
        )
        object.__setattr__(
            self,
            "candidate_net_mean_bps_by_cost",
            MappingProxyType(dict(self.candidate_net_mean_bps_by_cost)),
        )
        object.__setattr__(
            self,
            "direction_inverted_net_total_bps_by_cost",
            MappingProxyType(dict(self.direction_inverted_net_total_bps_by_cost)),
        )
        object.__setattr__(
            self,
            "direction_inverted_net_mean_bps_by_cost",
            MappingProxyType(dict(self.direction_inverted_net_mean_bps_by_cost)),
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "candidate_active_decision_count": self.candidate_active_decision_count,
            "direction_inverted_decision_count": self.direction_inverted_decision_count,
            "candidate_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.candidate_net_total_bps_by_cost
            ),
            "candidate_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.candidate_net_mean_bps_by_cost
            ),
            "direction_inverted_net_total_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.direction_inverted_net_total_bps_by_cost
            ),
            "direction_inverted_net_mean_bps_by_all_in_round_trip_cost": _safe_cost_mapping(
                self.direction_inverted_net_mean_bps_by_cost
            ),
            "kill_reasons": list(self.kill_reasons),
        }


@dataclass(frozen=True, slots=True)
class SpyFirst30Final30MomentumResult:
    """One non-promoting evaluation result."""

    campaign_input: SpyFirst30Final30MomentumInput
    status: ResultStatus
    validation: SpyFirst30Final30MomentumValidation | None

    def __post_init__(self) -> None:
        if self.status not in {"input_unavailable", "falsified", "non_promoting_validation"}:
            raise ValueError("SPY first-30m/final-30m result status is invalid")
        if (self.status == "input_unavailable") != (self.validation is None):
            raise ValueError("SPY first-30m/final-30m result validation is invalid")
        if self.status == "falsified" and not self.validation:
            raise ValueError("SPY first-30m/final-30m kill result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": SPY_FIRST30_FINAL30_MOMENTUM_ID,
            "status": self.status,
            "input": self.campaign_input.safe_payload(),
            "validation": None if self.validation is None else self.validation.safe_payload(),
            "promotion_allowed": False,
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
            "profitability_claim_allowed": False,
            "gpu_eligible": False,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class SpyFirst30Final30MomentumRun:
    result: SpyFirst30Final30MomentumResult
    precommit_path: Path
    precommit_hash: str
    summary_path: Path


def prepare_spy_first30_final30_momentum(
    catalog: CatalogedBars,
    config: SpyFirst30Final30MomentumConfig | None = None,
) -> SpyFirst30Final30MomentumInput:
    """Prepare causal signal contexts without reading final-window target values."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("SPY first-30m/final-30m requires CatalogedBars")
    resolved_config = config or SpyFirst30Final30MomentumConfig()
    source = SpyFirst30Final30MomentumSource(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
    )
    sessions = _complete_regular_sessions(catalog)
    if len(sessions) != resolved_config.complete_session_count:
        return _campaign_input(
            source=source,
            config=resolved_config,
            status="input_unavailable",
            reason="insufficient_complete_regular_sessions",
            complete_regular_session_count=len(sessions),
            development=_empty_phase("development"),
            validation=_empty_phase("validation"),
            validation_sessions=(),
            candidate_contexts=(),
        )
    development, _ = _phase_contexts(
        phase="development",
        sessions=sessions,
        start_index=0,
        stop_index=resolved_config.development_sessions,
        context_index_offset=0,
        retain_contexts=False,
        config=resolved_config,
    )
    validation_start = resolved_config.development_sessions + resolved_config.purge_sessions
    validation_stop = validation_start + resolved_config.validation_sessions
    validation, contexts = _phase_contexts(
        phase="validation",
        sessions=sessions,
        start_index=validation_start,
        stop_index=validation_stop,
        context_index_offset=validation_start,
        retain_contexts=True,
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
        validation_sessions=tuple(
            sessions[index][1] for index in range(validation_start, validation_stop)
        ),
        candidate_contexts=contexts,
    )


def evaluate_spy_first30_final30_momentum(
    campaign_input: SpyFirst30Final30MomentumInput,
) -> SpyFirst30Final30MomentumResult:
    """Read final-window target values only after the fixed preflight passes."""

    if not isinstance(campaign_input, SpyFirst30Final30MomentumInput):
        raise TypeError("SPY first-30m/final-30m requires prepared input")
    if campaign_input.status == "input_unavailable":
        return SpyFirst30Final30MomentumResult(
            campaign_input=campaign_input,
            status="input_unavailable",
            validation=None,
        )
    validation = _validation_outcomes(campaign_input)
    return SpyFirst30Final30MomentumResult(
        campaign_input=campaign_input,
        status="falsified" if validation.kill_reasons else "non_promoting_validation",
        validation=validation,
    )


def run_spy_first30_final30_momentum(
    catalog: CatalogedBars,
    *,
    artifact_root: Path | str,
    run_label: str,
    repo_root: Path | str,
) -> SpyFirst30Final30MomentumRun:
    """Prepare, evaluate, and write idempotent source-safe external evidence."""

    resolved_label = _validated_run_label(run_label)
    root = _external_artifact_root(Path(artifact_root), Path(repo_root))
    campaign_input = prepare_spy_first30_final30_momentum(catalog)
    precommit_payload = campaign_input.safe_payload()
    precommit_hash = _sha256_json(precommit_payload)
    result = evaluate_spy_first30_final30_momentum(campaign_input)
    summary_payload = {"precommit_hash": precommit_hash, "result": result.safe_payload()}
    artifact_dir = root / "research" / SPY_FIRST30_FINAL30_MOMENTUM_ID / resolved_label
    _ensure_artifact_directory(root, artifact_dir)
    precommit_path = artifact_dir / "precommit.json"
    summary_path = artifact_dir / "summary.json"
    _write_or_verify(precommit_path, _canonical_json(precommit_payload))
    _write_or_verify(summary_path, _canonical_json(summary_payload))
    return SpyFirst30Final30MomentumRun(
        result=result,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def _complete_regular_sessions(
    catalog: CatalogedBars,
) -> tuple[tuple[SessionWindow, tuple[Bar, ...]], ...]:
    if not catalog.dataset_id.startswith("kis.paper.private.intraday.spy.ams.m1.") or any(
        bar.symbol != SPY_FIRST30_FINAL30_MOMENTUM_SYMBOL
        or bar.market != SPY_FIRST30_FINAL30_MOMENTUM_MARKET
        or bar.timeframe != Timeframe.M1
        for bar in catalog.bars
    ):
        raise ValueError("SPY first-30m/final-30m catalog scope is invalid")
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
    start_index: int,
    stop_index: int,
    context_index_offset: int,
    retain_contexts: bool,
    config: SpyFirst30Final30MomentumConfig,
) -> tuple[SpyFirst30Final30MomentumPhaseFacts, tuple[_DecisionContext, ...]]:
    structural_unavailable = 0
    zero_direction = 0
    contexts: list[_DecisionContext] = []
    for absolute_index in range(start_index, stop_index):
        prior = None if absolute_index == 0 else sessions[absolute_index - 1]
        current = sessions[absolute_index]
        direction = _causal_direction(prior=prior, current=current, config=config)
        if direction is None:
            structural_unavailable += 1
            continue
        if direction == 0:
            zero_direction += 1
            continue
        if retain_contexts:
            contexts.append(
                _DecisionContext(
                    session_index=absolute_index - context_index_offset,
                    direction=direction,
                )
            )
    facts = SpyFirst30Final30MomentumPhaseFacts(
        phase=phase,
        session_count=stop_index - start_index,
        scheduled_decision_count=stop_index - start_index,
        structural_unavailable_count=structural_unavailable,
        zero_direction_count=zero_direction,
        active_decision_count=(
            len(contexts)
            if retain_contexts
            else stop_index - start_index - structural_unavailable - zero_direction
        ),
    )
    return facts, tuple(contexts)


def _causal_direction(
    *,
    prior: tuple[SessionWindow, tuple[Bar, ...]] | None,
    current: tuple[SessionWindow, tuple[Bar, ...]],
    config: SpyFirst30Final30MomentumConfig,
) -> int | None:
    if prior is None:
        return None
    prior_window, prior_bars = prior
    current_window, current_bars = current
    if (
        len(prior_bars) <= config.exit_index
        or len(current_bars) <= config.exit_index
        or prior_bars[-1].end_ts != prior_window.close_ts
        or current_bars[config.first_window_bars - 1].end_ts
        != current_window.open_ts + Timeframe.M1.duration * config.first_window_bars
        or prior_bars[-1].end_ts > current_window.open_ts
    ):
        return None
    prior_close = prior_bars[-1].close
    first_window_close = current_bars[config.first_window_bars - 1].close
    if prior_close <= 0:
        return None
    if first_window_close > prior_close:
        return 1
    if first_window_close < prior_close:
        return -1
    return 0


def _empty_phase(phase: PhaseName) -> SpyFirst30Final30MomentumPhaseFacts:
    return SpyFirst30Final30MomentumPhaseFacts(
        phase=phase,
        session_count=0,
        scheduled_decision_count=0,
        structural_unavailable_count=0,
        zero_direction_count=0,
        active_decision_count=0,
    )


def _campaign_input(
    *,
    source: SpyFirst30Final30MomentumSource,
    config: SpyFirst30Final30MomentumConfig,
    status: InputStatus,
    reason: str | None,
    complete_regular_session_count: int,
    development: SpyFirst30Final30MomentumPhaseFacts,
    validation: SpyFirst30Final30MomentumPhaseFacts,
    validation_sessions: tuple[tuple[Bar, ...], ...],
    candidate_contexts: tuple[_DecisionContext, ...],
) -> SpyFirst30Final30MomentumInput:
    return SpyFirst30Final30MomentumInput(
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
        _candidate_contexts=candidate_contexts,
    )


def _validate_contexts(
    contexts: tuple[_DecisionContext, ...],
    sessions: tuple[tuple[Bar, ...], ...],
    config: SpyFirst30Final30MomentumConfig,
) -> None:
    for context in contexts:
        if context.session_index >= len(sessions):
            raise ValueError("SPY first-30m/final-30m context session is invalid")
        bars = sessions[context.session_index]
        if len(bars) <= config.exit_index:
            raise ValueError("SPY first-30m/final-30m context target is invalid")
        entry = bars[config.entry_index]
        exit_bar = bars[config.exit_index]
        if (
            entry.start_ts + Timeframe.M1.duration * (config.exit_index - config.entry_index)
            != exit_bar.start_ts
            or exit_bar.end_ts - entry.start_ts != Timeframe.M1.duration * 30
        ):
            raise ValueError("SPY first-30m/final-30m context timing is invalid")


def _validation_outcomes(
    campaign_input: SpyFirst30Final30MomentumInput,
) -> SpyFirst30Final30MomentumValidation:
    candidate_gross = tuple(
        _signed_target_return_bps(
            campaign_input._validation_sessions[context.session_index],
            direction=context.direction,
            config=campaign_input.config,
        )
        for context in campaign_input._candidate_contexts
    )
    inverted_gross = tuple(-value for value in candidate_gross)
    candidate = _aggregate_returns(candidate_gross, campaign_input.config)
    inverted = _aggregate_returns(inverted_gross, campaign_input.config)
    kill_key = _decimal_text(campaign_input.config.kill_cost)
    kill_reasons = (
        ("candidate_signed_net_total_flat_or_worse_at_20bp",)
        if candidate["total"][kill_key] <= 0
        else ()
    )
    return SpyFirst30Final30MomentumValidation(
        candidate_active_decision_count=len(candidate_gross),
        direction_inverted_decision_count=len(inverted_gross),
        candidate_net_total_bps_by_cost=candidate["total"],
        candidate_net_mean_bps_by_cost=candidate["mean"],
        direction_inverted_net_total_bps_by_cost=inverted["total"],
        direction_inverted_net_mean_bps_by_cost=inverted["mean"],
        kill_reasons=kill_reasons,
    )


def _signed_target_return_bps(
    bars: tuple[Bar, ...],
    *,
    direction: int,
    config: SpyFirst30Final30MomentumConfig,
) -> Decimal:
    entry = bars[config.entry_index]
    exit_bar = bars[config.exit_index]
    if (
        direction not in {-1, 1}
        or entry.open <= 0
        or entry.start_ts + Timeframe.M1.duration * (config.exit_index - config.entry_index)
        != exit_bar.start_ts
        or exit_bar.end_ts - entry.start_ts != Timeframe.M1.duration * 30
    ):
        raise ValueError("SPY first-30m/final-30m target is invalid")
    return Decimal(direction) * (exit_bar.close / entry.open - Decimal("1")) * Decimal("10000")


def _aggregate_returns(
    gross_returns: tuple[Decimal, ...],
    config: SpyFirst30Final30MomentumConfig,
) -> dict[str, Mapping[str, Decimal]]:
    if not gross_returns:
        raise ValueError("SPY first-30m/final-30m aggregate requires active contexts")
    totals: dict[str, Decimal] = {}
    means: dict[str, Decimal] = {}
    count = Decimal(len(gross_returns))
    for cost in config.cost_band:
        key = _decimal_text(cost)
        total = sum((gross - cost for gross in gross_returns), Decimal("0"))
        totals[key] = total
        means[key] = total / count
    return {"total": MappingProxyType(totals), "mean": MappingProxyType(means)}


def _input_hash(
    *,
    source: SpyFirst30Final30MomentumSource,
    config: SpyFirst30Final30MomentumConfig,
    status: InputStatus,
    reason: str | None,
    complete_regular_session_count: int,
    development: SpyFirst30Final30MomentumPhaseFacts,
    validation: SpyFirst30Final30MomentumPhaseFacts,
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
        raise ValueError("SPY first-30m/final-30m run label is invalid")
    return run_label


def _external_artifact_root(artifact_root: Path, repo_root: Path) -> Path:
    root = artifact_root.resolve(strict=False)
    repository = repo_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_artifacts = (docker_repository / "model_artifacts").resolve(strict=False)
    if root.is_relative_to(repository) and not (
        repository == docker_repository and root.is_relative_to(docker_artifacts)
    ):
        raise ValueError("SPY first-30m/final-30m artifacts must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("SPY first-30m/final-30m artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def _ensure_artifact_directory(root: Path, artifact_dir: Path) -> None:
    if artifact_dir.exists() and (artifact_dir.is_symlink() or not artifact_dir.is_dir()):
        raise ValueError("SPY first-30m/final-30m artifact directory is invalid")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not artifact_dir.resolve(strict=False).is_relative_to(root):
        raise ValueError("SPY first-30m/final-30m artifact directory is invalid")


def _write_or_verify(path: Path, encoded: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != encoded:
            raise ValueError("SPY first-30m/final-30m artifact conflicts with evidence")
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

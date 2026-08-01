"""A source-local, non-promoting CPU control for the Tiingo three-ETF D1 scope.

This module intentionally stays smaller than the project's historical campaign
machinery.  It freezes one descriptive daily contract so source-separated raw
EOD input can exercise the research loop without selecting a model, scheduling
a GPU job, or creating an execution route.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
)

TIINGO_ETF_D1_CPU_BASELINE_ID = "tiingo-etf-d1-cpu-baseline-v1"
TIINGO_ETF_D1_CPU_BASELINE_LOOKBACKS = (5, 20, 60)
TIINGO_ETF_D1_CPU_BASELINE_DEVELOPMENT_NUMERATOR = 7
TIINGO_ETF_D1_CPU_BASELINE_DEVELOPMENT_DENOMINATOR = 10
TIINGO_ETF_D1_CPU_BASELINE_TARGET_HORIZON_SESSIONS = 1
TIINGO_ETF_D1_CPU_BASELINE_PURGE_SESSIONS = 61
TIINGO_ETF_D1_CPU_BASELINE_MIN_EVALUATION_SAMPLES = 50
TIINGO_ETF_D1_CPU_BASELINE_ROUND_TRIP_COST_BPS_BAND = (
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)
TIINGO_ETF_D1_CPU_BASELINE_PRIMARY_ROUND_TRIP_COST_BPS = Decimal("10")
TIINGO_ETF_D1_CPU_BASELINE_FEATURE_DISCONTINUITY_LIMIT = Decimal("0.20")
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

BaselinePhase = Literal["development", "validation"]
BaselineStatus = Literal["evaluated", "input_unavailable"]
SampleExclusion = Literal["event", "feature_discontinuity"]


@dataclass(frozen=True, slots=True)
class TiingoEtfD1CpuBaselineConfig:
    """The fixed target, chronology, economics, and stop rule for this control."""

    lookbacks: tuple[int, ...] = TIINGO_ETF_D1_CPU_BASELINE_LOOKBACKS
    development_numerator: int = TIINGO_ETF_D1_CPU_BASELINE_DEVELOPMENT_NUMERATOR
    development_denominator: int = TIINGO_ETF_D1_CPU_BASELINE_DEVELOPMENT_DENOMINATOR
    target_horizon_sessions: int = TIINGO_ETF_D1_CPU_BASELINE_TARGET_HORIZON_SESSIONS
    purge_sessions: int = TIINGO_ETF_D1_CPU_BASELINE_PURGE_SESSIONS
    min_evaluation_samples: int = TIINGO_ETF_D1_CPU_BASELINE_MIN_EVALUATION_SAMPLES
    round_trip_cost_bps_band: tuple[Decimal, ...] = (
        TIINGO_ETF_D1_CPU_BASELINE_ROUND_TRIP_COST_BPS_BAND
    )
    primary_round_trip_cost_bps: Decimal = (
        TIINGO_ETF_D1_CPU_BASELINE_PRIMARY_ROUND_TRIP_COST_BPS
    )
    feature_discontinuity_limit: Decimal = (
        TIINGO_ETF_D1_CPU_BASELINE_FEATURE_DISCONTINUITY_LIMIT
    )
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.lookbacks != TIINGO_ETF_D1_CPU_BASELINE_LOOKBACKS
            or self.development_numerator
            != TIINGO_ETF_D1_CPU_BASELINE_DEVELOPMENT_NUMERATOR
            or self.development_denominator
            != TIINGO_ETF_D1_CPU_BASELINE_DEVELOPMENT_DENOMINATOR
            or self.target_horizon_sessions
            != TIINGO_ETF_D1_CPU_BASELINE_TARGET_HORIZON_SESSIONS
            or self.purge_sessions != TIINGO_ETF_D1_CPU_BASELINE_PURGE_SESSIONS
            or self.min_evaluation_samples
            != TIINGO_ETF_D1_CPU_BASELINE_MIN_EVALUATION_SAMPLES
            or self.round_trip_cost_bps_band
            != TIINGO_ETF_D1_CPU_BASELINE_ROUND_TRIP_COST_BPS_BAND
            or self.primary_round_trip_cost_bps
            != TIINGO_ETF_D1_CPU_BASELINE_PRIMARY_ROUND_TRIP_COST_BPS
            or self.feature_discontinuity_limit
            != TIINGO_ETF_D1_CPU_BASELINE_FEATURE_DISCONTINUITY_LIMIT
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("Tiingo ETF D1 CPU baseline config is frozen")
        if self.purge_sessions != max(self.lookbacks) + self.target_horizon_sessions:
            raise ValueError("Tiingo ETF D1 CPU baseline purge is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "lookbacks": list(self.lookbacks),
            "feature": "trailing_raw_close_return",
            "feature_available_through": "completed_session_t_close",
            "target": "next_session_open_to_close_direction",
            "trade_timing": "enter_next_session_open_exit_next_session_close",
            "development_fraction": {
                "numerator": self.development_numerator,
                "denominator": self.development_denominator,
            },
            "purge_sessions": self.purge_sessions,
            "target_horizon_sessions": self.target_horizon_sessions,
            "event_exclusion_window": "t-lookback_through_t+1",
            "feature_discontinuity_window": "t-lookback+1_through_t_only",
            "feature_discontinuity_limit": _decimal_text(self.feature_discontinuity_limit),
            "round_trip_cost_bps_band": [
                _decimal_text(cost) for cost in self.round_trip_cost_bps_band
            ],
            "primary_round_trip_cost_bps": _decimal_text(self.primary_round_trip_cost_bps),
            "minimum_evaluation_samples": self.min_evaluation_samples,
            "flat_baseline": "always_flat",
            "momentum_baseline": "long_when_trailing_raw_close_return_positive",
            "gpu_used": False,
            "training_used": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoEtfD1CpuBaselineSource:
    """Source-safe identity of the one verified raw-D1 snapshot consumed."""

    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    raw_hashes: Mapping[str, str]
    session_counts: Mapping[str, int]
    event_session_counts: Mapping[str, int]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_hashes", MappingProxyType(dict(self.raw_hashes)))
        object.__setattr__(self, "session_counts", MappingProxyType(dict(self.session_counts)))
        object.__setattr__(
            self,
            "event_session_counts",
            MappingProxyType(dict(self.event_session_counts)),
        )
        if (
            not self.dataset_id.startswith("us_equities.tiingo_etf_daily.snapshot=")
            or not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.manifest_hash)
            or tuple(self.raw_hashes) != TIINGO_ETF_D1_SYMBOLS
            or tuple(self.session_counts) != TIINGO_ETF_D1_SYMBOLS
            or tuple(self.event_session_counts) != TIINGO_ETF_D1_SYMBOLS
        ):
            raise ValueError("Tiingo ETF D1 CPU baseline source is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "manifest_hash": self.manifest_hash,
            "raw_hashes": dict(self.raw_hashes),
            "session_counts": dict(self.session_counts),
            "event_session_counts": dict(self.event_session_counts),
            "provider": "Tiingo standard EOD API",
            "price_fields": "raw_ohlcv_only",
            "adjusted_fields_used": False,
            "retrospective_research_only": True,
            "point_in_time_eligible": False,
            "paper_input_eligible": False,
            "sealed_holdout_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoEtfD1CpuBaselineSplit:
    """Counts for one symbol's chronological development, purge, and validation split."""

    symbol: str
    session_count: int
    development_session_count: int
    purge_session_count: int
    validation_session_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in TIINGO_ETF_D1_SYMBOLS
            or self.session_count < 1
            or self.development_session_count < 1
            or self.purge_session_count != TIINGO_ETF_D1_CPU_BASELINE_PURGE_SESSIONS
            or self.validation_session_count < 1
            or self.session_count
            != self.development_session_count
            + self.purge_session_count
            + self.validation_session_count
        ):
            raise ValueError("Tiingo ETF D1 CPU baseline split is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "session_count": self.session_count,
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
        }


@dataclass(frozen=True, slots=True)
class TiingoEtfD1CpuBaselineCell:
    """Aggregate-only result for one symbol, window, and chronological phase."""

    symbol: str
    lookback: int
    phase: BaselinePhase
    status: BaselineStatus
    candidate_sample_count: int
    accepted_sample_count: int
    event_excluded_count: int
    feature_discontinuity_excluded_count: int
    target_up_session_count: int | None
    momentum_long_trade_count: int | None
    momentum_net_winning_trade_count: int | None
    flat_net_total_bps: Decimal | None
    momentum_gross_total_bps: Decimal | None
    momentum_net_total_bps: Decimal | None
    momentum_net_total_bps_by_cost: Mapping[str, Decimal] | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.momentum_net_total_bps_by_cost is not None:
            object.__setattr__(
                self,
                "momentum_net_total_bps_by_cost",
                MappingProxyType(dict(self.momentum_net_total_bps_by_cost)),
            )
        if (
            self.symbol not in TIINGO_ETF_D1_SYMBOLS
            or self.lookback not in TIINGO_ETF_D1_CPU_BASELINE_LOOKBACKS
            or self.phase not in {"development", "validation"}
            or self.status not in {"evaluated", "input_unavailable"}
            or min(
                self.candidate_sample_count,
                self.accepted_sample_count,
                self.event_excluded_count,
                self.feature_discontinuity_excluded_count,
            )
            < 0
            or self.candidate_sample_count
            != self.accepted_sample_count
            + self.event_excluded_count
            + self.feature_discontinuity_excluded_count
        ):
            raise ValueError("Tiingo ETF D1 CPU baseline cell is invalid")
        unavailable_values = (
            self.target_up_session_count,
            self.momentum_long_trade_count,
            self.momentum_net_winning_trade_count,
            self.flat_net_total_bps,
            self.momentum_gross_total_bps,
            self.momentum_net_total_bps,
            self.momentum_net_total_bps_by_cost,
        )
        if self.status == "input_unavailable":
            if (
                self.accepted_sample_count >= TIINGO_ETF_D1_CPU_BASELINE_MIN_EVALUATION_SAMPLES
                or any(value is not None for value in unavailable_values)
            ):
                raise ValueError("Tiingo ETF D1 CPU baseline unavailable cell is invalid")
        elif (
            self.accepted_sample_count < TIINGO_ETF_D1_CPU_BASELINE_MIN_EVALUATION_SAMPLES
            or any(value is None for value in unavailable_values)
            or self.target_up_session_count is None
            or self.momentum_long_trade_count is None
            or self.momentum_net_winning_trade_count is None
            or self.target_up_session_count > self.accepted_sample_count
            or self.momentum_long_trade_count > self.accepted_sample_count
            or self.momentum_net_winning_trade_count > self.momentum_long_trade_count
            or self.momentum_net_total_bps_by_cost is None
            or tuple(self.momentum_net_total_bps_by_cost)
            != tuple(
                _decimal_text(cost)
                for cost in TIINGO_ETF_D1_CPU_BASELINE_ROUND_TRIP_COST_BPS_BAND
            )
            or self.momentum_net_total_bps
            != self.momentum_net_total_bps_by_cost[
                _decimal_text(TIINGO_ETF_D1_CPU_BASELINE_PRIMARY_ROUND_TRIP_COST_BPS)
            ]
        ):
            raise ValueError("Tiingo ETF D1 CPU baseline evaluated cell is invalid")

    def safe_payload(self) -> dict[str, object]:
        result: dict[str, object] = {
            "symbol": self.symbol,
            "lookback": self.lookback,
            "phase": self.phase,
            "status": self.status,
            "candidate_sample_count": self.candidate_sample_count,
            "accepted_sample_count": self.accepted_sample_count,
            "event_excluded_count": self.event_excluded_count,
            "feature_discontinuity_excluded_count": self.feature_discontinuity_excluded_count,
        }
        if self.status == "evaluated":
            result["target_up_session_count"] = self.target_up_session_count
            result["momentum_long_trade_count"] = self.momentum_long_trade_count
            result["momentum_net_winning_trade_count"] = self.momentum_net_winning_trade_count
            result["flat_net_total_bps"] = _decimal_text(self.flat_net_total_bps)
            result["momentum_gross_total_bps"] = _decimal_text(self.momentum_gross_total_bps)
            result["momentum_net_total_bps"] = _decimal_text(self.momentum_net_total_bps)
            result["momentum_net_total_bps_by_round_trip_cost"] = {
                cost: _decimal_text(total)
                for cost, total in self.momentum_net_total_bps_by_cost.items()
            }
        return result


@dataclass(frozen=True, slots=True)
class TiingoEtfD1CpuBaselineResult:
    """One source-local descriptive result that cannot select or promote a candidate."""

    source: TiingoEtfD1CpuBaselineSource
    config: TiingoEtfD1CpuBaselineConfig
    splits: tuple[TiingoEtfD1CpuBaselineSplit, ...]
    cells: tuple[TiingoEtfD1CpuBaselineCell, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            tuple(split.symbol for split in self.splits) != TIINGO_ETF_D1_SYMBOLS
            or len(self.cells) != len(TIINGO_ETF_D1_SYMBOLS) * len(self.config.lookbacks) * 2
            or tuple(
                (cell.symbol, cell.lookback, cell.phase)
                for cell in self.cells
            )
            != tuple(
                (symbol, lookback, phase)
                for symbol in TIINGO_ETF_D1_SYMBOLS
                for lookback in self.config.lookbacks
                for phase in ("development", "validation")
            )
        ):
            raise ValueError("Tiingo ETF D1 CPU baseline result is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "baseline_id": TIINGO_ETF_D1_CPU_BASELINE_ID,
            "status": "completed_descriptive_only",
            "source": self.source.safe_payload(),
            "contract": self.config.safe_payload(),
            "splits": [split.safe_payload() for split in self.splits],
            "cells": [cell.safe_payload() for cell in self.cells],
            "candidate_selection_allowed": False,
            "ensemble_allowed": False,
            "gpu_eligible": False,
            "paper_input_allowed": False,
            "promotion_allowed": False,
            "cross_symbol_replication_claim_allowed": False,
            "raw_market_data_written": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoEtfD1CpuBaselineRun:
    """External-only evidence paths for one immutable CPU baseline attempt."""

    result: TiingoEtfD1CpuBaselineResult
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _is_sha256(self.precommit_hash):
            raise ValueError("Tiingo ETF D1 CPU baseline precommit hash is invalid")


def evaluate_tiingo_etf_d1_cpu_baseline(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    config: TiingoEtfD1CpuBaselineConfig | None = None,
) -> TiingoEtfD1CpuBaselineResult:
    """Evaluate fixed flat and momentum controls without I/O, credentials, or network."""

    resolved_config = config or TiingoEtfD1CpuBaselineConfig()
    source = _source_from_snapshot(snapshot)
    _validate_rows(snapshot.rows_by_symbol)
    splits: list[TiingoEtfD1CpuBaselineSplit] = []
    cells: list[TiingoEtfD1CpuBaselineCell] = []
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = snapshot.rows_by_symbol[symbol]
        split = _build_split(symbol=symbol, session_count=len(rows), config=resolved_config)
        splits.append(split)
        for lookback in resolved_config.lookbacks:
            cells.append(
                _evaluate_phase(
                    rows=rows,
                    symbol=symbol,
                    lookback=lookback,
                    phase="development",
                    start_index=lookback,
                    end_index=split.development_session_count - 2,
                    config=resolved_config,
                )
            )
            cells.append(
                _evaluate_phase(
                    rows=rows,
                    symbol=symbol,
                    lookback=lookback,
                    phase="validation",
                    start_index=split.development_session_count + split.purge_session_count,
                    end_index=len(rows) - 2,
                    config=resolved_config,
                )
            )
    return TiingoEtfD1CpuBaselineResult(
        source=source,
        config=resolved_config,
        splits=tuple(splits),
        cells=tuple(cells),
    )


def run_tiingo_etf_d1_cpu_baseline(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    config: TiingoEtfD1CpuBaselineConfig | None = None,
) -> TiingoEtfD1CpuBaselineRun:
    """Precommit then run the offline descriptive control into the external artifact root."""

    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("Tiingo ETF D1 CPU baseline run label is invalid")
    resolved_repo_root = (repo_root or Path.cwd()).resolve(strict=True)
    resolved_artifact_root = Path(artifact_root).resolve(strict=False)
    _reject_repository_path(resolved_artifact_root, resolved_repo_root)
    _reject_repository_path(resolved_artifact_root, _MODULE_REPOSITORY_ROOT)
    output_root = (resolved_artifact_root / TIINGO_ETF_D1_CPU_BASELINE_ID).resolve(strict=False)
    output_dir = (output_root / run_label).resolve(strict=False)
    if not output_dir.is_relative_to(output_root):
        raise ValueError("Tiingo ETF D1 CPU baseline output path is invalid")
    _reject_repository_path(output_dir, resolved_repo_root)
    _reject_repository_path(output_dir, _MODULE_REPOSITORY_ROOT)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError("Tiingo ETF D1 CPU baseline artifact already exists")
    output_dir.mkdir(parents=True, exist_ok=False)

    resolved_config = config or TiingoEtfD1CpuBaselineConfig()
    source = _source_from_snapshot(snapshot)
    precommit_payload = {
        "schema_version": SCHEMA_VERSION,
        "baseline_id": TIINGO_ETF_D1_CPU_BASELINE_ID,
        "status": "precommitted",
        "attempt": {"run_label": run_label},
        "source": source.safe_payload(),
        "contract": resolved_config.safe_payload(),
        "candidate_selection_allowed": False,
        "ensemble_allowed": False,
        "gpu_eligible": False,
        "paper_input_allowed": False,
        "promotion_allowed": False,
        "raw_market_data_written": False,
    }
    precommit_hash = _sha256_json(precommit_payload)
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, {**precommit_payload, "precommit_hash": precommit_hash})
    try:
        result = evaluate_tiingo_etf_d1_cpu_baseline(snapshot, config=resolved_config)
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "baseline_id": TIINGO_ETF_D1_CPU_BASELINE_ID,
                "status": "incomplete",
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "candidate_selection_allowed": False,
                "ensemble_allowed": False,
                "gpu_eligible": False,
                "paper_input_allowed": False,
                "promotion_allowed": False,
                "raw_market_data_written": False,
            },
        )
        raise
    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        {
            **result.safe_payload(),
            "precommit_hash": precommit_hash,
        },
    )
    return TiingoEtfD1CpuBaselineRun(
        result=result,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def _source_from_snapshot(snapshot: LoadedTiingoEtfDailySnapshot) -> TiingoEtfD1CpuBaselineSource:
    facts = snapshot.snapshot
    return TiingoEtfD1CpuBaselineSource(
        dataset_id=facts.dataset_id,
        dataset_hash=facts.dataset_hash,
        manifest_hash=facts.manifest_hash,
        raw_hashes=facts.raw_hashes,
        session_counts=facts.session_counts,
        event_session_counts=facts.event_session_counts,
    )


def _validate_rows(rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]]) -> None:
    if tuple(rows_by_symbol) != TIINGO_ETF_D1_SYMBOLS:
        raise ValueError("Tiingo ETF D1 CPU baseline symbols are invalid")
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = rows_by_symbol[symbol]
        previous_date = None
        for row in rows:
            if row.symbol != symbol or (
                previous_date is not None and row.session_date <= previous_date
            ):
                raise ValueError("Tiingo ETF D1 CPU baseline row chronology is invalid")
            previous_date = row.session_date


def _build_split(
    *,
    symbol: str,
    session_count: int,
    config: TiingoEtfD1CpuBaselineConfig,
) -> TiingoEtfD1CpuBaselineSplit:
    development = (
        session_count
        * config.development_numerator
        // config.development_denominator
    )
    validation = session_count - development - config.purge_sessions
    if development <= max(config.lookbacks) + config.target_horizon_sessions or validation < 1:
        raise ValueError("Tiingo ETF D1 CPU baseline source has insufficient sessions")
    return TiingoEtfD1CpuBaselineSplit(
        symbol=symbol,
        session_count=session_count,
        development_session_count=development,
        purge_session_count=config.purge_sessions,
        validation_session_count=validation,
    )


def _evaluate_phase(
    *,
    rows: tuple[TiingoEtfDailyRow, ...],
    symbol: str,
    lookback: int,
    phase: BaselinePhase,
    start_index: int,
    end_index: int,
    config: TiingoEtfD1CpuBaselineConfig,
) -> TiingoEtfD1CpuBaselineCell:
    candidate_count = max(0, end_index - start_index + 1)
    accepted_count = 0
    event_excluded_count = 0
    discontinuity_excluded_count = 0
    target_up_count = 0
    long_count = 0
    net_winning_count = 0
    gross_total_bps = Decimal("0")
    net_total_bps_by_cost = {
        _decimal_text(cost): Decimal("0") for cost in config.round_trip_cost_bps_band
    }
    primary_cost_rate = config.primary_round_trip_cost_bps / Decimal("10000")
    for index in range(start_index, end_index + 1):
        exclusion = _sample_exclusion(
            rows,
            index=index,
            lookback=lookback,
            feature_discontinuity_limit=config.feature_discontinuity_limit,
        )
        if exclusion == "event":
            event_excluded_count += 1
            continue
        if exclusion == "feature_discontinuity":
            discontinuity_excluded_count += 1
            continue
        accepted_count += 1
        trailing_return = rows[index].close / rows[index - lookback].close - Decimal("1")
        target_return = rows[index + 1].close / rows[index + 1].open - Decimal("1")
        if target_return > 0:
            target_up_count += 1
        if trailing_return > 0:
            long_count += 1
            gross_total_bps += target_return * Decimal("10000")
            for cost in config.round_trip_cost_bps_band:
                net_total_bps_by_cost[_decimal_text(cost)] += (
                    target_return * Decimal("10000") - cost
                )
            if target_return - primary_cost_rate > 0:
                net_winning_count += 1
    if accepted_count < config.min_evaluation_samples:
        return TiingoEtfD1CpuBaselineCell(
            symbol=symbol,
            lookback=lookback,
            phase=phase,
            status="input_unavailable",
            candidate_sample_count=candidate_count,
            accepted_sample_count=accepted_count,
            event_excluded_count=event_excluded_count,
            feature_discontinuity_excluded_count=discontinuity_excluded_count,
            target_up_session_count=None,
            momentum_long_trade_count=None,
            momentum_net_winning_trade_count=None,
            flat_net_total_bps=None,
            momentum_gross_total_bps=None,
            momentum_net_total_bps=None,
            momentum_net_total_bps_by_cost=None,
        )
    return TiingoEtfD1CpuBaselineCell(
        symbol=symbol,
        lookback=lookback,
        phase=phase,
        status="evaluated",
        candidate_sample_count=candidate_count,
        accepted_sample_count=accepted_count,
        event_excluded_count=event_excluded_count,
        feature_discontinuity_excluded_count=discontinuity_excluded_count,
        target_up_session_count=target_up_count,
        momentum_long_trade_count=long_count,
        momentum_net_winning_trade_count=net_winning_count,
        flat_net_total_bps=Decimal("0"),
        momentum_gross_total_bps=gross_total_bps,
        momentum_net_total_bps=net_total_bps_by_cost[
            _decimal_text(config.primary_round_trip_cost_bps)
        ],
        momentum_net_total_bps_by_cost=net_total_bps_by_cost,
    )


def _sample_exclusion(
    rows: tuple[TiingoEtfDailyRow, ...],
    *,
    index: int,
    lookback: int,
    feature_discontinuity_limit: Decimal,
) -> SampleExclusion | None:
    """Check the known retrospective event window and causal feature-side jumps only."""

    if index - lookback < 0 or index + 1 >= len(rows):
        raise ValueError("Tiingo ETF D1 CPU baseline sample index is invalid")
    if any(
        row.div_cash != 0 or row.split_factor != 1
        for row in rows[index - lookback : index + 2]
    ):
        return "event"
    for transition_index in range(index - lookback + 1, index + 1):
        close_return = (
            rows[transition_index].close / rows[transition_index - 1].close - Decimal("1")
        )
        if abs(close_return) > feature_discontinuity_limit:
            return "feature_discontinuity"
    return None


def _reject_repository_path(path: Path, repository_root: Path) -> None:
    resolved_repository = Path(repository_root).resolve(strict=True)
    resolved_path = Path(path).resolve(strict=False)
    if resolved_path == resolved_repository or resolved_path.is_relative_to(resolved_repository):
        raise ValueError("Tiingo ETF D1 CPU baseline artifacts must stay outside the Git workspace")


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        raise RuntimeError("Tiingo ETF D1 CPU baseline artifact write failed") from exc


def _is_sha256(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        raise ValueError("Tiingo ETF D1 CPU baseline decimal is unavailable")
    return format(value, "f")

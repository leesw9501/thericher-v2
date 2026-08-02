"""Bounded CPU-only HMM regime preflight over an attested KIS NAS D1 phase.

The leaf deliberately keeps all bars, labels, parameters, and scores in memory.
External evidence contains only hashes, geometry, counts, and categorical
outcomes. It has no provider, credential, execution, Paper, or GPU surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)
from .validation import _reject_repo_artifact_path

KIS_NAS_D1_INTRADAY_REGIME_HMM_ID = "kis-nas-d1-intraday-regime-hmm-preflight-v1"
KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID = "kis.paper.private.daily.nas.history.panel-v1"
KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS = (
    "AAPL",
    "AMZN",
    "GOOGL",
    "META",
    "MSFT",
    "NVDA",
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_DEVELOPMENT_SESSIONS = 1510
KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP = 1000
KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP = 600
KIS_NAS_D1_INTRADAY_REGIME_HMM_PURGE_START = 600
KIS_NAS_D1_INTRADAY_REGIME_HMM_PURGE_STOP = 622
KIS_NAS_D1_INTRADAY_REGIME_HMM_FILTER_WARMUP_START = 602
KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START = 622
KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP = 999
KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES = (
    "close_to_open_ratio",
    "high_to_low_ratio",
    "body_to_range_ratio",
    "close_location_ratio",
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_STATE_COUNT = 2
KIS_NAS_D1_INTRADAY_REGIME_HMM_EM_STEPS = 32
KIS_NAS_D1_INTRADAY_REGIME_HMM_MAX_SECONDS = 90.0
KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS = 15
KIS_NAS_D1_INTRADAY_REGIME_HMM_COST_BPS = (10, 15, 20)
KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_COUNT = 1000
KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE = 10
KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_SEED_BASE = 20_260_803
KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS = 50
KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL = 50
KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL = 50
KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_PRIMARY_EFFECT = 0.015
KIS_NAS_D1_INTRADAY_REGIME_HMM_EXTREME_RATIO = 0.15
KIS_NAS_D1_INTRADAY_REGIME_HMM_VARIANCE_FLOOR = 1e-6
KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_STATE_WEIGHT = 20.0
KIS_NAS_D1_INTRADAY_REGIME_HMM_DEFAULT_ATTEMPT_ID = "cpu-preflight-r1"

InputStatus = Literal["ready", "input_unavailable"]
ResultStatus = Literal["input_unavailable", "noise_not_separable", "source_local_non_promoting"]
_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_INPUT_REASONS = frozenset(
    {
        "source_stream_mismatch",
        "invalid_candle_ratio",
        "insufficient_source_sessions",
    }
)
_FIT_REASONS = frozenset(
    {
        "fit_time_bound",
        "nonfinite_fit",
        "missing_state",
        "insufficient_fit_state_targets",
    }
)


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmInput:
    """Hash-bound source identity plus the in-memory development slice."""

    input_id: str
    dataset_id: str
    dataset_hash: str
    index_hash: str
    status: InputStatus
    reason: str | None
    fit_target_free_slot_count: int
    screen_target_free_slot_count: int
    input_hash: str
    _bars_by_symbol: Mapping[str, tuple[Bar, ...]]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        bars_by_symbol = {symbol: tuple(bars) for symbol, bars in self._bars_by_symbol.items()}
        expected_fit_slots = len(KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS) * (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1
        )
        expected_screen_slots = len(KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS) * (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP
            - KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START
        )
        if (
            self.input_id != "kis.paper.private.daily.nas.sequence.input-v1"
            or self.dataset_id != KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID
            or self.dataset_hash != KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH
            or not _is_sha256(self.index_hash)
            or self.status not in {"ready", "input_unavailable"}
            or self.fit_target_free_slot_count != expected_fit_slots
            or self.screen_target_free_slot_count != expected_screen_slots
            or not _is_sha256(self.input_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS NAS D1 HMM input identity is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or tuple(bars_by_symbol) != KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
            ):
                raise ValueError("ready KIS NAS D1 HMM input is invalid")
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS:
                _verify_source_bars(bars_by_symbol[symbol], symbol=symbol)
        elif self.reason not in _INPUT_REASONS or bars_by_symbol:
            raise ValueError("unavailable KIS NAS D1 HMM input is invalid")
        expected_hash = _input_hash(
            input_id=self.input_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            index_hash=self.index_hash,
            status=self.status,
            reason=self.reason,
            fit_target_free_slot_count=self.fit_target_free_slot_count,
            screen_target_free_slot_count=self.screen_target_free_slot_count,
        )
        if self.input_hash != expected_hash:
            raise ValueError("KIS NAS D1 HMM input hash is invalid")
        object.__setattr__(self, "_bars_by_symbol", MappingProxyType(bars_by_symbol))

    def safe_payload(self) -> dict[str, object]:
        """Expose lineage and geometry without bars, labels, or parameters."""

        return {
            "schema_version": self.schema_version,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_ID,
            "source": {
                "input_id": self.input_id,
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "index_hash": self.index_hash,
                "phase": "development_prefix_only",
                "symbol_count": len(KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS),
                "source_index_range": [0, KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP - 1],
            },
            "status": self.status,
            "reason": self.reason,
            "fit_target_free_slot_count": self.fit_target_free_slot_count,
            "screen_target_free_slot_count": self.screen_target_free_slot_count,
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "predictions_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class _FittedGaussianHmm:
    """In-memory diagonal Gaussian HMM parameters; never serialized directly."""

    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    initial_probabilities: tuple[float, float]
    transition_probabilities: tuple[tuple[float, float], tuple[float, float]]
    state_means: tuple[tuple[float, ...], tuple[float, ...]]
    state_variances: tuple[tuple[float, ...], tuple[float, ...]]
    parameter_sha256: str


@dataclass(frozen=True, slots=True)
class _SymbolModelSet:
    normal_model: _FittedGaussianHmm
    normal_long_state: int
    extreme_control_model: _FittedGaussianHmm
    extreme_control_long_state: int


@dataclass(frozen=True, slots=True)
class _ModelSet:
    symbols: Mapping[str, _SymbolModelSet]
    model_set_sha256: str


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmContract:
    """One frozen CPU-only HMM contract and source-safe registry entry."""

    input: KisNasD1IntradayRegimeHmmInput
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    fit_reason: str | None
    model_set: _ModelSet | None
    registry_entry: FrozenCampaignRegistryEntry


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmRun:
    """Terminal source-local result for the fixed CPU preflight."""

    status: ResultStatus
    reason: str | None
    summary_path: Path
    summary_sha256: str
    registry_outcome: CampaignOutcomeRegistryEntry


@dataclass(frozen=True, slots=True)
class _VariantMetrics:
    candidate_rate_by_cost: tuple[tuple[int, float], ...]
    all_long_rate_by_cost: tuple[tuple[int, float], ...]
    primary_null_p95: float
    candidate_count_by_symbol: tuple[int, ...]
    eligible_count_by_symbol: tuple[int, ...]
    prefix_deterministic: bool
    extreme_exclusion: bool

    @property
    def primary_candidate_rate(self) -> float:
        return dict(self.candidate_rate_by_cost)[KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS]

    @property
    def primary_all_long_rate(self) -> float:
        return dict(self.all_long_rate_by_cost)[KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS]

    @property
    def passes_primary(self) -> bool:
        return (
            self.primary_candidate_rate - self.primary_all_long_rate
            >= KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_PRIMARY_EFFECT
            and self.primary_candidate_rate - self.primary_null_p95
            >= KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_PRIMARY_EFFECT
            and self.prefix_deterministic
        )


@dataclass(frozen=True, slots=True)
class _EvaluationMetrics:
    normal: _VariantMetrics
    extreme_control: _VariantMetrics

    @property
    def survives_extreme_control(self) -> bool:
        return self.normal.passes_primary and self.extreme_control.passes_primary

    def safe_payload(self) -> dict[str, object]:
        return {
            "primary": {
                "candidate_vs_all_long": _effect_relation(
                    self.normal.primary_candidate_rate - self.normal.primary_all_long_rate
                ),
                "candidate_vs_joint_null_p95": _effect_relation(
                    self.normal.primary_candidate_rate - self.normal.primary_null_p95
                ),
                "candidate_rate_bucket": _rate_bucket(self.normal.primary_candidate_rate),
                "all_long_rate_bucket": _rate_bucket(self.normal.primary_all_long_rate),
            },
            "cost_sensitivity": {
                str(cost): _effect_relation(
                    dict(self.normal.candidate_rate_by_cost)[cost]
                    - dict(self.normal.all_long_rate_by_cost)[cost]
                )
                for cost in KIS_NAS_D1_INTRADAY_REGIME_HMM_COST_BPS
            },
            "screen": {
                "eligible_count_per_symbol": list(self.normal.eligible_count_by_symbol),
                "candidate_count_per_symbol": list(self.normal.candidate_count_by_symbol),
                "minimum_target_free_slots_per_symbol": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL
                ),
                "minimum_candidate_slots_per_symbol": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL
                ),
            },
            "causal_filter": {
                "mode": "forward_filtering_only",
                "prefix_deterministic": self.normal.prefix_deterministic,
                "warmup_source_indices": [
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_FILTER_WARMUP_START,
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_PURGE_STOP - 1,
                ],
            },
            "joint_null": {
                "count": KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_COUNT,
                "block_size_sessions": KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE,
                "permutation": "joint_contiguous_date_blocks_across_symbols",
                "percentile": "p95_higher",
            },
            "extreme_control": {
                "threshold_abs_close_to_open_return": KIS_NAS_D1_INTRADAY_REGIME_HMM_EXTREME_RATIO,
                "feature_and_target_exclusion": self.extreme_control.extreme_exclusion,
                "prefix_deterministic": self.extreme_control.prefix_deterministic,
                "primary_result": "survives"
                if self.survives_extreme_control
                else "depends_or_fails",
            },
            "numeric_metrics_persisted": False,
        }


def load_kis_nas_d1_intraday_regime_hmm_input(
    *,
    manifest_path: Path,
    cache_root: Path,
    panel_root: Path,
    repo_root: Path | None = None,
) -> KisNasD1IntradayRegimeHmmInput:
    """Reattest only the known KIS daily source before exposing its development phase."""

    from thericher_v2.data.kis_paper_daily_history_sequence_input import (
        load_kis_paper_daily_history_sequence_input,
    )

    source = load_kis_paper_daily_history_sequence_input(
        manifest_path=manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return build_kis_nas_d1_intraday_regime_hmm_input(
        source.development,
        input_id=source.input_id,
    )


def build_kis_nas_d1_intraday_regime_hmm_input(
    development_phase: object,
    *,
    input_id: str,
) -> KisNasD1IntradayRegimeHmmInput:
    """Expose only source indices 0..999 from the attested development phase."""

    phase = cast(Any, development_phase)
    try:
        _require_development_phase(phase, input_id=input_id)
        bars_by_symbol = {
            symbol: _verified_phase_prefix(phase, symbol=symbol)
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
        }
    except ValueError as error:
        return _unavailable_input(phase, input_id=input_id, reason=_safe_input_reason(error))
    return KisNasD1IntradayRegimeHmmInput(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        status="ready",
        reason=None,
        fit_target_free_slot_count=_fit_target_free_slot_count(),
        screen_target_free_slot_count=_screen_target_free_slot_count(),
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=str(phase.parent_dataset_id),
            dataset_hash=str(phase.parent_dataset_hash),
            index_hash=str(phase.index_hash),
            status="ready",
            reason=None,
            fit_target_free_slot_count=_fit_target_free_slot_count(),
            screen_target_free_slot_count=_screen_target_free_slot_count(),
        ),
        _bars_by_symbol=bars_by_symbol,
    )


def freeze_kis_nas_d1_intraday_regime_hmm_campaign(
    input: KisNasD1IntradayRegimeHmmInput,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision: str,
    attempt_id: str = KIS_NAS_D1_INTRADAY_REGIME_HMM_DEFAULT_ATTEMPT_ID,
) -> KisNasD1IntradayRegimeHmmContract:
    """Freeze model geometry and training-derived state mapping before screen labels."""

    if not isinstance(code_revision, str) or not code_revision.strip():
        raise ValueError("code revision is required")
    _require_attempt_id(attempt_id)
    run_directory = _external_run_directory(artifact_root, repo_root, attempt_id=attempt_id)
    model_set: _ModelSet | None = None
    fit_reason: str | None = input.reason if input.status == "input_unavailable" else None
    if input.status == "ready":
        try:
            model_set = _fit_model_set(input)
        except ValueError as error:
            fit_reason = _safe_fit_reason(error)
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_ID,
            "attempt_id": attempt_id,
            "code_revision": code_revision,
            "source": input.safe_payload()["source"],
            "source_limitations": [
                "MODP=0_unadjusted",
                "corporate_action_semantics_not_qualified",
                "current_listing_registry_not_point_in_time_universe",
                "source_local_only_no_cross_source_blend",
            ],
            "input": {
                "status": input.status,
                "reason": input.reason,
                "input_hash": input.input_hash,
                "fit_target_free_slot_count": input.fit_target_free_slot_count,
                "screen_target_free_slot_count": input.screen_target_free_slot_count,
            },
            "geometry": {
                "development_source_session_count": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_DEVELOPMENT_SESSIONS
                ),
                "used_source_indices": [0, KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP - 1],
                "fit_feature_indices": [0, KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1],
                "fit_mapping_decision_indices": [0, KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 2],
                "purge_indices": [
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_PURGE_START,
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_PURGE_STOP - 1,
                ],
                "filter_warmup_indices": [
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_FILTER_WARMUP_START,
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_PURGE_STOP - 1,
                ],
                "screen_source_indices": [
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START,
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP - 1,
                ],
                "screen_decision_indices": [
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START,
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP - 1,
                ],
                "target": "next_session_open_to_close_direction_after_round_trip_cost",
                "features": list(KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES),
                "features_use_same_session_ratios_only": True,
            },
            "model": {
                "family": "per_symbol_two_state_diagonal_gaussian_hmm",
                "em_steps": KIS_NAS_D1_INTRADAY_REGIME_HMM_EM_STEPS,
                "max_seconds": KIS_NAS_D1_INTRADAY_REGIME_HMM_MAX_SECONDS,
                "state_mapping": "higher_fit_period_after_cost_up_rate_long_else_other_state",
                "fit_status": "ready" if model_set is not None else "input_unavailable",
                "fit_reason": fit_reason,
                "model_set_sha256": None if model_set is None else model_set.model_set_sha256,
                "symbol_model_hashes": (
                    None
                    if model_set is None
                    else {
                        symbol: {
                            "normal": model.normal_model.parameter_sha256,
                            "normal_long_state": model.normal_long_state,
                            "extreme_control": model.extreme_control_model.parameter_sha256,
                            "extreme_control_long_state": model.extreme_control_long_state,
                        }
                        for symbol, model in model_set.symbols.items()
                    }
                ),
            },
            "cost_model": {
                "primary_round_trip_bps": KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS,
                "sensitivity_round_trip_bps": list(KIS_NAS_D1_INTRADAY_REGIME_HMM_COST_BPS),
                "selection_cost": "primary_only",
            },
            "baselines": {
                "all_long": "same_screen_slots_after_cost",
                "all_flat": "descriptive_only",
            },
            "null": {
                "count": KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_COUNT,
                "block_size_sessions": KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE,
                "permutation": "joint_contiguous_date_blocks_across_all_symbols",
                "percentile": "p95_higher",
            },
            "kill_test": {
                "minimum_effect_over_all_long_and_joint_null_p95": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_PRIMARY_EFFECT
                ),
                "minimum_fit_state_targets": KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS,
                "minimum_screen_slots_per_symbol": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL
                ),
                "minimum_candidate_slots_per_symbol": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL
                ),
                "prefix_filter_determinism": True,
                "positive_session_ohlc_multiplier_invariance": True,
                "extreme_session_abs_close_open_threshold": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_EXTREME_RATIO
                ),
                "extreme_control_must_survive": True,
            },
            "scope": _non_promoting_scope(),
            "artifact_policy": {
                "repository_storage_allowed": False,
                "raw_rows_persisted": False,
                "dates_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "probabilities_persisted": False,
                "fitted_parameters_persisted": False,
                "checkpoint_written": False,
            },
        },
        field_name="campaign_contract_sha256",
    )
    recorded = _write_or_reattach_contract(run_directory / "campaign-contract.json", payload)
    contract_sha256 = _verify_signed_payload(recorded, field_name="campaign_contract_sha256")
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=input.dataset_hash,
        split_hash=_sha256_json(cast(dict[str, object], recorded["geometry"])),
        cost_model_hash=_sha256_json(cast(dict[str, object], recorded["cost_model"])),
        trial_family=KIS_NAS_D1_INTRADAY_REGIME_HMM_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return KisNasD1IntradayRegimeHmmContract(
        input=input,
        artifact_root=Path(artifact_root).resolve(),
        repo_root=Path(repo_root).resolve(),
        attempt_id=attempt_id,
        run_directory=run_directory,
        contract_path=run_directory / "campaign-contract.json",
        contract_sha256=contract_sha256,
        fit_reason=fit_reason,
        model_set=model_set,
        registry_entry=registry_entry,
    )


def run_kis_nas_d1_intraday_regime_hmm(
    contract: KisNasD1IntradayRegimeHmmContract,
) -> KisNasD1IntradayRegimeHmmRun:
    """Run or reattach the fixed no-network CPU screen."""

    existing = _load_existing_run(contract)
    if existing is not None:
        return _with_outcome(contract, existing)
    metrics: _EvaluationMetrics | None = None
    if contract.input.status != "ready" or contract.model_set is None:
        status: ResultStatus = "input_unavailable"
        reason = contract.fit_reason or contract.input.reason or "nonfinite_fit"
    else:
        try:
            metrics = _evaluate(contract.input, contract.model_set)
        except ValueError as error:
            status = "input_unavailable"
            reason = _safe_fit_reason(error)
        else:
            status = (
                "source_local_non_promoting"
                if metrics.survives_extreme_control
                else "noise_not_separable"
            )
            reason = (
                None
                if status == "source_local_non_promoting"
                else "frozen_primary_kill_test_failed"
            )
    summary = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "phase": "cpu_only_development_preflight",
            "status": status,
            "reason": reason,
            "input": {
                "input_hash": contract.input.input_hash,
                "status": contract.input.status,
                "fit_target_free_slot_count": contract.input.fit_target_free_slot_count,
                "screen_target_free_slot_count": contract.input.screen_target_free_slot_count,
            },
            "metrics": None if metrics is None else metrics.safe_payload(),
            "scope": _non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    summary_path = contract.run_directory / "cpu-summary.json"
    _write_or_verify_json(summary_path, summary)
    return _with_outcome(contract, _run_from_summary(contract, summary_path))


def _fit_model_set(input: KisNasD1IntradayRegimeHmmInput) -> _ModelSet:
    deadline = time.perf_counter() + KIS_NAS_D1_INTRADAY_REGIME_HMM_MAX_SECONDS
    symbols: dict[str, _SymbolModelSet] = {}
    for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS:
        bars = input._bars_by_symbol[symbol]
        features = _feature_matrix(bars)
        extremes = _extreme_mask(bars)
        normal_model = _fit_two_state_hmm(
            features[:KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP], deadline=deadline
        )
        normal_states = _filter_states(
            normal_model,
            features[: KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1],
        )
        normal_labels = _fit_labels(bars, extreme_exclusion=False)
        normal_long_state = _derive_long_state(normal_states, normal_labels)

        control_features = features[:KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP][~extremes[:600]]
        if len(control_features) < KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS * 2:
            raise ValueError("insufficient_fit_state_targets")
        control_model = _fit_two_state_hmm(control_features, deadline=deadline)
        control_states = _filter_states(
            control_model,
            features[: KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1],
            valid_mask=~extremes[: KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1],
        )
        control_labels, control_label_mask = _fit_labels(
            bars,
            extreme_exclusion=True,
            extremes=extremes,
        )
        control_long_state = _derive_long_state(
            control_states[control_label_mask],
            control_labels[control_label_mask],
        )
        symbols[symbol] = _SymbolModelSet(
            normal_model=normal_model,
            normal_long_state=normal_long_state,
            extreme_control_model=control_model,
            extreme_control_long_state=control_long_state,
        )
    payload = {
        symbol: {
            "normal": values.normal_model.parameter_sha256,
            "normal_long_state": values.normal_long_state,
            "extreme_control": values.extreme_control_model.parameter_sha256,
            "extreme_control_long_state": values.extreme_control_long_state,
        }
        for symbol, values in symbols.items()
    }
    return _ModelSet(symbols=MappingProxyType(symbols), model_set_sha256=_sha256_json(payload))


def _evaluate(
    input: KisNasD1IntradayRegimeHmmInput,
    model_set: _ModelSet,
) -> _EvaluationMetrics:
    return _EvaluationMetrics(
        normal=_evaluate_variant(input, model_set, extreme_exclusion=False),
        extreme_control=_evaluate_variant(input, model_set, extreme_exclusion=True),
    )


def _evaluate_variant(
    input: KisNasD1IntradayRegimeHmmInput,
    model_set: _ModelSet,
    *,
    extreme_exclusion: bool,
) -> _VariantMetrics:
    numpy = _numpy()
    labels_by_symbol: dict[str, Any] = {}
    candidate_masks: dict[str, Any] = {}
    eligible_masks: dict[str, Any] = {}
    candidate_counts: list[int] = []
    eligible_counts: list[int] = []
    prefix_deterministic = True
    for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS:
        bars = input._bars_by_symbol[symbol]
        feature_rows = _feature_matrix(bars)
        extremes = _extreme_mask(bars)
        selected = model_set.symbols[symbol]
        model = selected.extreme_control_model if extreme_exclusion else selected.normal_model
        long_state = (
            selected.extreme_control_long_state if extreme_exclusion else selected.normal_long_state
        )
        valid_features = ~extremes if extreme_exclusion else numpy.ones(len(bars), dtype=bool)
        states, prefix_ok = _screen_states_with_prefix_proof(
            model,
            feature_rows,
            valid_features=valid_features,
        )
        prefix_deterministic = prefix_deterministic and prefix_ok
        labels = numpy.asarray(
            [
                _target_label_after_cost(
                    bars[index + 1], cost_bps=KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS
                )
                for index in range(
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START,
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP,
                )
            ],
            dtype=numpy.int8,
        )
        eligible = numpy.ones(len(labels), dtype=bool)
        if extreme_exclusion:
            eligible = numpy.asarray(
                [
                    not extremes[index] and not extremes[index + 1]
                    for index in range(
                        KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START,
                        KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP,
                    )
                ],
                dtype=bool,
            )
        candidate = (states == long_state) & eligible
        labels_by_symbol[symbol] = labels
        candidate_masks[symbol] = candidate
        eligible_masks[symbol] = eligible
        candidate_counts.append(int(candidate.sum()))
        eligible_counts.append(int(eligible.sum()))
    if any(
        count < KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL
        for count in eligible_counts
    ) or any(
        count < KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL
        for count in candidate_counts
    ):
        raise ValueError("insufficient_fit_state_targets")
    rates_by_cost: list[tuple[int, float]] = []
    long_rates_by_cost: list[tuple[int, float]] = []
    for cost in KIS_NAS_D1_INTRADAY_REGIME_HMM_COST_BPS:
        cost_labels = {
            symbol: _labels_for_screen(
                input._bars_by_symbol[symbol],
                cost_bps=cost,
            )
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
        }
        rates_by_cost.append((cost, _masked_rate(cost_labels, candidate_masks)))
        long_rates_by_cost.append((cost, _masked_rate(cost_labels, eligible_masks)))
    null_values = [
        _masked_rate(
            _joint_block_permute_labels(
                labels_by_symbol,
                seed=KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_SEED_BASE + offset,
            ),
            candidate_masks,
        )
        for offset in range(KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_COUNT)
    ]
    return _VariantMetrics(
        candidate_rate_by_cost=tuple(rates_by_cost),
        all_long_rate_by_cost=tuple(long_rates_by_cost),
        primary_null_p95=_percentile_higher(null_values),
        candidate_count_by_symbol=tuple(candidate_counts),
        eligible_count_by_symbol=tuple(eligible_counts),
        prefix_deterministic=prefix_deterministic,
        extreme_exclusion=extreme_exclusion,
    )


def _feature_matrix(bars: Sequence[Bar]) -> Any:
    numpy = _numpy()
    values = numpy.asarray([_feature_row(bar) for bar in bars], dtype=numpy.float64)
    if (
        values.shape
        != (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP,
            len(KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES),
        )
        or not numpy.isfinite(values).all()
    ):
        raise ValueError("invalid_candle_ratio")
    return values


def _feature_row(bar: Bar) -> tuple[float, float, float, float]:
    values = (bar.open, bar.high, bar.low, bar.close)
    if any(value <= 0 for value in values) or bar.high <= bar.low:
        raise ValueError("invalid_candle_ratio")
    candle_range = bar.high - bar.low
    ratios = (
        float(bar.close / bar.open),
        float(bar.high / bar.low),
        float((bar.close - bar.open) / candle_range),
        float((bar.close - bar.low) / candle_range),
    )
    if (
        ratios[0] <= 0.0
        or ratios[1] <= 0.0
        or not 0.0 <= ratios[3] <= 1.0
        or any(not math.isfinite(value) for value in ratios)
    ):
        raise ValueError("invalid_candle_ratio")
    return ratios


def _fit_two_state_hmm(features: Any, *, deadline: float) -> _FittedGaussianHmm:
    numpy = _numpy()
    values = numpy.asarray(features, dtype=numpy.float64)
    if (
        values.ndim != 2
        or values.shape[1] != len(KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES)
        or len(values) < KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS * 2
        or not numpy.isfinite(values).all()
    ):
        raise ValueError("nonfinite_fit")
    means = values.mean(axis=0)
    scales = values.std(axis=0)
    if (
        not numpy.isfinite(means).all()
        or not numpy.isfinite(scales).all()
        or numpy.any(scales <= 0.0)
    ):
        raise ValueError("nonfinite_fit")
    standardized = (values - means) / scales
    order = numpy.argsort(standardized[:, 0], kind="stable")
    midpoint = len(standardized) // 2
    lower = standardized[order[:midpoint]]
    upper = standardized[order[midpoint:]]
    if not len(lower) or not len(upper):
        raise ValueError("missing_state")
    state_means = numpy.vstack((lower.mean(axis=0), upper.mean(axis=0)))
    state_variances = numpy.vstack((lower.var(axis=0), upper.var(axis=0)))
    state_variances = numpy.maximum(
        state_variances,
        KIS_NAS_D1_INTRADAY_REGIME_HMM_VARIANCE_FLOOR,
    )
    if not numpy.isfinite(state_means).all() or not numpy.isfinite(state_variances).all():
        raise ValueError("nonfinite_fit")
    initial = numpy.asarray((0.5, 0.5), dtype=numpy.float64)
    transition = numpy.asarray(((0.9, 0.1), (0.1, 0.9)), dtype=numpy.float64)
    for _ in range(KIS_NAS_D1_INTRADAY_REGIME_HMM_EM_STEPS):
        _require_before_deadline(deadline)
        emissions = _emission_probabilities(standardized, state_means, state_variances)
        gamma, xi_sum = _forward_backward(initial, transition, emissions)
        weights = gamma.sum(axis=0)
        if numpy.any(weights < KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_STATE_WEIGHT):
            raise ValueError("missing_state")
        initial = _normalized(gamma[0])
        transition = _normalize_rows(xi_sum + 1e-8)
        state_means = (gamma.T @ standardized) / weights[:, None]
        centered = standardized[:, None, :] - state_means[None, :, :]
        state_variances = (gamma[:, :, None] * centered * centered).sum(axis=0) / weights[:, None]
        state_variances = numpy.maximum(
            state_variances,
            KIS_NAS_D1_INTRADAY_REGIME_HMM_VARIANCE_FLOOR,
        )
        if (
            not numpy.isfinite(initial).all()
            or not numpy.isfinite(transition).all()
            or not numpy.isfinite(state_means).all()
            or not numpy.isfinite(state_variances).all()
        ):
            raise ValueError("nonfinite_fit")
    payload = {
        "feature_means": [_float_text(value) for value in means],
        "feature_scales": [_float_text(value) for value in scales],
        "initial_probabilities": [_float_text(value) for value in initial],
        "transition_probabilities": [[_float_text(value) for value in row] for row in transition],
        "state_means": [[_float_text(value) for value in row] for row in state_means],
        "state_variances": [[_float_text(value) for value in row] for row in state_variances],
    }
    return _FittedGaussianHmm(
        feature_means=tuple(float(value) for value in means),
        feature_scales=tuple(float(value) for value in scales),
        initial_probabilities=(float(initial[0]), float(initial[1])),
        transition_probabilities=(
            (float(transition[0, 0]), float(transition[0, 1])),
            (float(transition[1, 0]), float(transition[1, 1])),
        ),
        state_means=(
            tuple(float(value) for value in state_means[0]),
            tuple(float(value) for value in state_means[1]),
        ),
        state_variances=(
            tuple(float(value) for value in state_variances[0]),
            tuple(float(value) for value in state_variances[1]),
        ),
        parameter_sha256=_sha256_json(payload),
    )


def _forward_backward(initial: Any, transition: Any, emissions: Any) -> tuple[Any, Any]:
    numpy = _numpy()
    count = len(emissions)
    alpha = numpy.empty((count, KIS_NAS_D1_INTRADAY_REGIME_HMM_STATE_COUNT), dtype=numpy.float64)
    scales = numpy.empty((count,), dtype=numpy.float64)
    alpha[0] = initial * emissions[0]
    scales[0] = float(alpha[0].sum())
    if not math.isfinite(scales[0]) or scales[0] <= 0.0:
        raise ValueError("nonfinite_fit")
    alpha[0] /= scales[0]
    for index in range(1, count):
        alpha[index] = (alpha[index - 1] @ transition) * emissions[index]
        scales[index] = float(alpha[index].sum())
        if not math.isfinite(scales[index]) or scales[index] <= 0.0:
            raise ValueError("nonfinite_fit")
        alpha[index] /= scales[index]
    beta = numpy.ones_like(alpha)
    for index in range(count - 2, -1, -1):
        beta[index] = transition @ (emissions[index + 1] * beta[index + 1])
        beta[index] /= scales[index + 1]
    gamma = alpha * beta
    gamma = _normalize_rows(gamma)
    xi_sum = numpy.zeros(
        (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_STATE_COUNT,
            KIS_NAS_D1_INTRADAY_REGIME_HMM_STATE_COUNT,
        ),
        dtype=numpy.float64,
    )
    for index in range(count - 1):
        xi = alpha[index, :, None] * transition * (emissions[index + 1] * beta[index + 1])[None, :]
        denominator = float(xi.sum())
        if not math.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("nonfinite_fit")
        xi_sum += xi / denominator
    return gamma, xi_sum


def _emission_probabilities(values: Any, state_means: Any, state_variances: Any) -> Any:
    numpy = _numpy()
    centered = values[:, None, :] - state_means[None, :, :]
    log_values = -0.5 * (
        numpy.log(2.0 * math.pi * state_variances)[None, :, :]
        + centered * centered / state_variances[None, :, :]
    ).sum(axis=2)
    row_max = log_values.max(axis=1, keepdims=True)
    result = numpy.maximum(
        numpy.exp(log_values - row_max),
        numpy.finfo(numpy.float64).tiny,
    )
    if not numpy.isfinite(result).all():
        raise ValueError("nonfinite_fit")
    return result


def _filter_states(
    model: _FittedGaussianHmm,
    features: Any,
    *,
    valid_mask: Any | None = None,
) -> Any:
    numpy = _numpy()
    values = numpy.asarray(features, dtype=numpy.float64)
    if values.ndim != 2 or values.shape[1] != len(KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES):
        raise ValueError("nonfinite_fit")
    if valid_mask is None:
        valid = numpy.ones(len(values), dtype=bool)
    else:
        valid = numpy.asarray(valid_mask, dtype=bool)
    if valid.shape != (len(values),):
        raise ValueError("nonfinite_fit")
    means = numpy.asarray(model.feature_means, dtype=numpy.float64)
    scales = numpy.asarray(model.feature_scales, dtype=numpy.float64)
    transformed = (values - means) / scales
    state_means = numpy.asarray(model.state_means, dtype=numpy.float64)
    state_variances = numpy.asarray(model.state_variances, dtype=numpy.float64)
    transition = numpy.asarray(model.transition_probabilities, dtype=numpy.float64)
    initial = numpy.asarray(model.initial_probabilities, dtype=numpy.float64)
    posterior = initial.copy()
    result = numpy.full((len(values),), -1, dtype=numpy.int8)
    for index, row in enumerate(transformed):
        if not valid[index]:
            posterior = initial.copy()
            continue
        emissions = _emission_probabilities(
            row.reshape(1, -1),
            state_means,
            state_variances,
        )[0]
        posterior = (posterior @ transition) * emissions
        posterior = _normalized(posterior)
        result[index] = int(numpy.argmax(posterior))
    return result


def _screen_states_with_prefix_proof(
    model: _FittedGaussianHmm,
    feature_rows: Any,
    *,
    valid_features: Any,
) -> tuple[Any, bool]:
    numpy = _numpy()
    start = KIS_NAS_D1_INTRADAY_REGIME_HMM_FILTER_WARMUP_START
    stop = KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP
    values = numpy.asarray(feature_rows, dtype=numpy.float64)
    valid = numpy.asarray(valid_features, dtype=bool)
    filtered = _filter_states(model, values[start:stop], valid_mask=valid[start:stop])
    screen_offset = KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START - start
    screen_states = filtered[screen_offset:]
    prefix_deterministic = True
    for decision_index, observed_state in zip(
        range(KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START, stop),
        screen_states,
        strict=True,
    ):
        prefix = _filter_states(
            model,
            values[start : decision_index + 1],
            valid_mask=valid[start : decision_index + 1],
        )
        if int(prefix[-1]) != int(observed_state):
            prefix_deterministic = False
            break
    return screen_states, prefix_deterministic


def _derive_long_state(states: Any, labels: Any) -> int:
    numpy = _numpy()
    state_values = numpy.asarray(states, dtype=numpy.int8)
    target_values = numpy.asarray(labels, dtype=numpy.int8)
    if (
        state_values.shape != target_values.shape
        or not _are_binary_labels(target_values)
        or numpy.any(
            (state_values < 0) | (state_values >= KIS_NAS_D1_INTRADAY_REGIME_HMM_STATE_COUNT)
        )
    ):
        raise ValueError("missing_state")
    counts = tuple(int((state_values == state).sum()) for state in range(2))
    if any(count < KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS for count in counts):
        raise ValueError("insufficient_fit_state_targets")
    rates = tuple(float(target_values[state_values == state].mean()) for state in range(2))
    if any(not math.isfinite(value) for value in rates):
        raise ValueError("nonfinite_fit")
    return 1 if rates[1] > rates[0] else 0


def _fit_labels(
    bars: Sequence[Bar],
    *,
    extreme_exclusion: bool,
    extremes: Any | None = None,
) -> tuple[Any, Any] | Any:
    numpy = _numpy()
    labels = numpy.asarray(
        [
            _target_label_after_cost(
                bars[index + 1], cost_bps=KIS_NAS_D1_INTRADAY_REGIME_HMM_PRIMARY_COST_BPS
            )
            for index in range(KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1)
        ],
        dtype=numpy.int8,
    )
    if not extreme_exclusion:
        return labels
    if extremes is None:
        raise ValueError("nonfinite_fit")
    values = numpy.asarray(extremes, dtype=bool)
    mask = numpy.asarray(
        [not values[index] and not values[index + 1] for index in range(len(labels))],
        dtype=bool,
    )
    return labels, mask


def _labels_for_screen(bars: Sequence[Bar], *, cost_bps: int) -> Any:
    numpy = _numpy()
    return numpy.asarray(
        [
            _target_label_after_cost(bars[index + 1], cost_bps=cost_bps)
            for index in range(
                KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START,
                KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP,
            )
        ],
        dtype=numpy.int8,
    )


def _target_label_after_cost(bar: Bar, *, cost_bps: int) -> int:
    if cost_bps not in KIS_NAS_D1_INTRADAY_REGIME_HMM_COST_BPS or bar.open <= 0 or bar.close <= 0:
        raise ValueError("invalid_candle_ratio")
    value = float(bar.close / bar.open - Decimal("1"))
    if not math.isfinite(value):
        raise ValueError("invalid_candle_ratio")
    return int(value > cost_bps / 10_000.0)


def _extreme_mask(bars: Sequence[Bar]) -> Any:
    numpy = _numpy()
    return numpy.asarray(
        [
            abs(float(bar.close / bar.open - Decimal("1")))
            >= KIS_NAS_D1_INTRADAY_REGIME_HMM_EXTREME_RATIO
            for bar in bars
        ],
        dtype=bool,
    )


def _joint_block_permute_labels(
    labels_by_symbol: Mapping[str, Any], *, seed: int
) -> dict[str, Any]:
    numpy = _numpy()
    values = {
        symbol: numpy.asarray(labels_by_symbol[symbol], dtype=numpy.int8)
        for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
    }
    lengths = {len(labels) for labels in values.values()}
    if len(lengths) != 1 or not all(_are_binary_labels(labels) for labels in values.values()):
        raise ValueError("nonfinite_fit")
    count = lengths.pop()
    full_stop = (
        count
        // KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE
        * KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE
    )
    blocks = list(range(0, full_stop, KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE))
    generator = numpy.random.default_rng(seed)
    order = generator.permutation(len(blocks))
    indices = [
        index
        for block_index in order
        for index in range(
            blocks[int(block_index)],
            blocks[int(block_index)] + KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_BLOCK_SIZE,
        )
    ] + list(range(full_stop, count))
    return {
        symbol: labels[numpy.asarray(indices, dtype=numpy.int64)]
        for symbol, labels in values.items()
    }


def _masked_rate(labels_by_symbol: Mapping[str, Any], masks_by_symbol: Mapping[str, Any]) -> float:
    numpy = _numpy()
    selected: list[Any] = []
    for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS:
        labels = numpy.asarray(labels_by_symbol[symbol], dtype=numpy.int8)
        mask = numpy.asarray(masks_by_symbol[symbol], dtype=bool)
        if labels.shape != mask.shape or not _are_binary_labels(labels):
            raise ValueError("nonfinite_fit")
        selected.append(labels[mask])
    joined = numpy.concatenate(selected)
    if not len(joined) or not _are_binary_labels(joined):
        raise ValueError("nonfinite_fit")
    result = float(joined.mean())
    if not math.isfinite(result):
        raise ValueError("nonfinite_fit")
    return result


def _percentile_higher(values: Sequence[float]) -> float:
    if len(values) != KIS_NAS_D1_INTRADAY_REGIME_HMM_NULL_COUNT or any(
        not math.isfinite(value) for value in values
    ):
        raise ValueError("nonfinite_fit")
    ordered = sorted(values)
    return ordered[math.ceil((len(ordered) - 1) * 0.95)]


def _unavailable_input(
    phase: Any,
    *,
    input_id: str,
    reason: str,
) -> KisNasD1IntradayRegimeHmmInput:
    safe_reason = reason if reason in _INPUT_REASONS else "source_stream_mismatch"
    dataset_id = str(getattr(phase, "parent_dataset_id", KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID))
    if dataset_id != KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID:
        dataset_id = KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID
    dataset_hash = str(
        getattr(phase, "parent_dataset_hash", KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH)
    )
    if dataset_hash != KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH:
        dataset_hash = KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH
    index_hash = str(getattr(phase, "index_hash", ""))
    if not _is_sha256(index_hash):
        index_hash = "sha256:" + "0" * 64
    return KisNasD1IntradayRegimeHmmInput(
        input_id=input_id,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        index_hash=index_hash,
        status="input_unavailable",
        reason=safe_reason,
        fit_target_free_slot_count=_fit_target_free_slot_count(),
        screen_target_free_slot_count=_screen_target_free_slot_count(),
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            index_hash=index_hash,
            status="input_unavailable",
            reason=safe_reason,
            fit_target_free_slot_count=_fit_target_free_slot_count(),
            screen_target_free_slot_count=_screen_target_free_slot_count(),
        ),
        _bars_by_symbol={},
    )


def _require_development_phase(phase: Any, *, input_id: str) -> None:
    if (
        input_id != "kis.paper.private.daily.nas.sequence.input-v1"
        or getattr(phase, "phase", None) != "development"
        or getattr(phase, "parent_dataset_id", None) != KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID
        or getattr(phase, "parent_dataset_hash", None)
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH
        or not _is_sha256(getattr(phase, "index_hash", None))
        or tuple(getattr(phase, "bars_by_symbol", ())) != KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
        or len(getattr(phase, "common_sessions", ()))
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_DEVELOPMENT_SESSIONS
    ):
        raise ValueError("source_stream_mismatch")


def _verified_phase_prefix(phase: Any, *, symbol: str) -> tuple[Bar, ...]:
    stream = phase.bars_by_symbol[symbol]
    bars = tuple(stream.bars[:KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP])
    sessions = tuple(phase.common_sessions[:KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP])
    if (
        len(bars) != KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP
        or tuple(bar.start_ts.date() for bar in bars) != sessions
    ):
        raise ValueError("insufficient_source_sessions")
    _verify_source_bars(bars, symbol=symbol)
    return bars


def _verify_source_bars(bars: Sequence[Bar], *, symbol: str) -> None:
    if len(bars) != KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP:
        raise ValueError("insufficient_source_sessions")
    previous: Bar | None = None
    for bar in bars:
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
        ):
            raise ValueError("source_stream_mismatch")
        if (
            bar.open <= 0
            or bar.close <= 0
            or bar.low <= 0
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
            or bar.high <= bar.low
        ):
            raise ValueError("invalid_candle_ratio")
        _feature_row(bar)
        if previous is not None and (
            bar.start_ts <= previous.start_ts or bar.end_ts <= previous.end_ts
        ):
            raise ValueError("source_stream_mismatch")
        previous = bar


def _screen_target_free_slot_count() -> int:
    return len(KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS) * (
        KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_DECISION_STOP
        - KIS_NAS_D1_INTRADAY_REGIME_HMM_SCREEN_START
    )


def _fit_target_free_slot_count() -> int:
    return len(KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS) * (
        KIS_NAS_D1_INTRADAY_REGIME_HMM_FIT_STOP - 1
    )


def _external_run_directory(artifact_root: Path, repo_root: Path, *, attempt_id: str) -> Path:
    requested_root = Path(artifact_root)
    repository = Path(repo_root).resolve()
    _reject_repo_artifact_path(requested_root, repository)
    if requested_root.exists() and requested_root.is_symlink():
        raise ValueError("model artifact root must not be a symlink")
    requested_root.mkdir(parents=True, exist_ok=True)
    root = requested_root.resolve()
    run_directory = root / "research" / KIS_NAS_D1_INTRADAY_REGIME_HMM_ID / attempt_id
    if run_directory.exists() and run_directory.is_symlink():
        raise ValueError("HMM run directory must not be a symlink")
    run_directory.mkdir(parents=True, exist_ok=True)
    return run_directory


def _load_existing_run(
    contract: KisNasD1IntradayRegimeHmmContract,
) -> KisNasD1IntradayRegimeHmmRun | None:
    path = contract.run_directory / "cpu-summary.json"
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError("HMM summary path is invalid")
    return _run_from_summary(contract, path)


def _run_from_summary(
    contract: KisNasD1IntradayRegimeHmmContract,
    summary_path: Path,
) -> KisNasD1IntradayRegimeHmmRun:
    payload = _read_json_object(summary_path)
    summary_sha256 = _verify_signed_payload(payload, field_name="summary_sha256")
    status = payload.get("status")
    reason = payload.get("reason")
    if (
        payload.get("campaign_id") != KIS_NAS_D1_INTRADAY_REGIME_HMM_ID
        or payload.get("campaign_contract_sha256") != contract.contract_sha256
        or payload.get("phase") != "cpu_only_development_preflight"
        or status not in {"input_unavailable", "noise_not_separable", "source_local_non_promoting"}
        or (reason is not None and not isinstance(reason, str))
        or not isinstance(payload.get("input"), dict)
        or payload["input"].get("input_hash") != contract.input.input_hash
        or payload.get("scope") != _non_promoting_scope()
    ):
        raise ValueError("HMM summary is malformed")
    return KisNasD1IntradayRegimeHmmRun(
        status=cast(ResultStatus, status),
        reason=cast(str | None, reason),
        summary_path=summary_path,
        summary_sha256=summary_sha256,
        registry_outcome=CampaignOutcomeRegistryEntry(
            contract_hash=contract.contract_sha256,
            outcome_class="non_promoting_completed",
            outcome_reference_sha256=summary_sha256,
            recorded_at=contract.registry_entry.recorded_at,
            record_path=contract.registry_entry.record_path,
            record_sha256=contract.registry_entry.record_sha256,
        ),
    )


def _with_outcome(
    contract: KisNasD1IntradayRegimeHmmContract,
    run: KisNasD1IntradayRegimeHmmRun,
) -> KisNasD1IntradayRegimeHmmRun:
    outcome = register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class=(
            "non_promoting_failed"
            if run.status == "input_unavailable"
            else "non_promoting_completed"
        ),
        outcome_reference_sha256=run.summary_sha256,
        artifact_root=contract.artifact_root,
        repo_root=contract.repo_root,
    )
    return KisNasD1IntradayRegimeHmmRun(
        status=run.status,
        reason=run.reason,
        summary_path=run.summary_path,
        summary_sha256=run.summary_sha256,
        registry_outcome=outcome,
    )


def _write_or_reattach_contract(path: Path, payload: dict[str, object]) -> dict[str, object]:
    if not path.exists():
        _write_or_verify_json(path, payload)
        return payload
    existing = _read_json_object(path)
    _verify_signed_payload(existing, field_name="campaign_contract_sha256")
    if existing == payload:
        return existing
    if _without_code_revision(existing) != _without_code_revision(payload):
        raise ValueError("HMM contract conflicts with existing evidence")
    return existing


def _write_or_verify_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        if path.is_symlink() or _read_json_object(path) != payload:
            raise ValueError("HMM artifact already exists with different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("HMM artifact is invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("HMM artifact contains invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("HMM artifact must be an object")
    return cast(dict[str, object], payload)


def _signed_payload(payload: dict[str, object], *, field_name: str) -> dict[str, object]:
    result = dict(payload)
    result[field_name] = _sha256_json(result)
    return result


def _verify_signed_payload(payload: dict[str, object], *, field_name: str) -> str:
    recorded = payload.get(field_name)
    unsigned = dict(payload)
    unsigned.pop(field_name, None)
    if not _is_sha256(recorded) or recorded != _sha256_json(unsigned):
        raise ValueError("HMM artifact checksum is invalid")
    return cast(str, recorded)


def _without_code_revision(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result.pop("code_revision", None)
    result.pop("campaign_contract_sha256", None)
    return result


def _input_hash(
    *,
    input_id: str,
    dataset_id: str,
    dataset_hash: str,
    index_hash: str,
    status: InputStatus,
    reason: str | None,
    fit_target_free_slot_count: int,
    screen_target_free_slot_count: int,
) -> str:
    return _sha256_json(
        {
            "input_id": input_id,
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "index_hash": index_hash,
            "status": status,
            "reason": reason,
            "fit_target_free_slot_count": fit_target_free_slot_count,
            "screen_target_free_slot_count": screen_target_free_slot_count,
            "features": list(KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES),
            "source_stop": KIS_NAS_D1_INTRADAY_REGIME_HMM_SOURCE_STOP,
        }
    )


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "source_local_only": True,
        "point_in_time_claim_allowed": False,
        "corporate_action_claim_allowed": False,
        "survivorship_claim_allowed": False,
        "architecture_selection_allowed": False,
        "profitability_or_pnl_claim": False,
        "paper_input_allowed": False,
        "broker_access": False,
        "live_behavior": False,
        "gpu_used": False,
    }


def _normalized(values: Any) -> Any:
    numpy = _numpy()
    result = numpy.asarray(values, dtype=numpy.float64)
    denominator = float(result.sum())
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("nonfinite_fit")
    return result / denominator


def _normalize_rows(values: Any) -> Any:
    numpy = _numpy()
    result = numpy.asarray(values, dtype=numpy.float64)
    denominators = result.sum(axis=1, keepdims=True)
    if not numpy.isfinite(denominators).all() or numpy.any(denominators <= 0.0):
        raise ValueError("nonfinite_fit")
    return result / denominators


def _are_binary_labels(values: Any) -> bool:
    numpy = _numpy()
    array = numpy.asarray(values, dtype=numpy.int8)
    return array.ndim == 1 and len(array) > 0 and bool(numpy.isin(array, (0, 1)).all())


def _require_before_deadline(deadline: float) -> None:
    if not math.isfinite(deadline) or time.perf_counter() > deadline:
        raise ValueError("fit_time_bound")


def _effect_relation(value: float) -> str:
    if value >= KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_PRIMARY_EFFECT:
        return "meets_or_exceeds_margin"
    if value > 0.0:
        return "positive_below_margin"
    return "at_or_below_comparator"


def _rate_bucket(value: float) -> str:
    if value < 0.45:
        return "below_0.45"
    if value < 0.50:
        return "0.45_to_0.50"
    if value < 0.55:
        return "0.50_to_0.55"
    if value < 0.60:
        return "0.55_to_0.60"
    return "at_or_above_0.60"


def _safe_input_reason(error: ValueError) -> str:
    reason = str(error)
    return reason if reason in _INPUT_REASONS else "source_stream_mismatch"


def _safe_fit_reason(error: ValueError) -> str:
    reason = str(error)
    return reason if reason in _FIT_REASONS else "nonfinite_fit"


def _require_attempt_id(value: str) -> None:
    if not isinstance(value, str) or not _SAFE_ATTEMPT_ID.fullmatch(value):
        raise ValueError("HMM attempt id is invalid")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("nonfinite_fit")
    return format(value, ".17g")


def _numpy() -> Any:
    import numpy

    return numpy

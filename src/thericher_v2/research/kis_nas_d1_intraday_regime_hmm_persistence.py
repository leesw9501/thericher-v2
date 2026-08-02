"""One fixed, date-disjoint persistence check for the NAS D1 HMM preflight.

This leaf deliberately exposes only fit bars ``0..599`` and later bars
``1000..1509``.  The original preflight screen ``600..999`` never appears in
its in-memory input, so no helper can use those bars or labels by accident.
All generated evidence is categorical and source-safe.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

from . import kis_nas_d1_intraday_regime_hmm as preflight
from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)
from .validation import _reject_repo_artifact_path

KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID = "kis-nas-d1-intraday-regime-hmm-persistence-v1"
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_ID = preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_ID
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256 = (
    "sha256:a98f89dba03cb6970d9a59bd33f923e31f401aa698e9992c75758e049304d1bd"
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256 = (
    "sha256:b70a2bcff4e846656309fa3ff6094a5b80db69ba48def308b626fb5049efd6f1"
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID = (
    preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_ID
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH = (
    preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_DATASET_HASH
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS = (
    preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_SYMBOLS
)
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEVELOPMENT_SESSIONS = 1510
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP = 600
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_OMITTED_START = 600
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_OMITTED_STOP = 1000
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_START = 1000
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_STOP = 1510
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FILTER_WARMUP_STOP = 20
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START = 20
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP = 509
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS = 15
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_COST_BPS = (10, 15, 20)
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_COUNT = 1000
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_BLOCK_SIZE = 10
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_SEED_BASE = 20_260_804
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_MIN_PRIMARY_EFFECT = 0.015
KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEFAULT_ATTEMPT_ID = "cpu-persistence-r1"

InputStatus = Literal["ready", "input_unavailable"]
ResultStatus = Literal["input_unavailable", "persistence_falsified", "source_local_non_promoting"]
_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_INPUT_REASONS = frozenset(
    {
        "source_stream_mismatch",
        "invalid_candle_ratio",
        "insufficient_source_sessions",
        "parent_lineage_invalid",
    }
)


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmPersistencePrecommit:
    """Immutable config receipt written before the source loader is called."""

    artifact_root: Path
    repo_root: Path
    attempt_id: str
    precommit_path: Path
    precommit_sha256: str


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmPersistenceInput:
    """Source identity plus only the fit and later-tail bar segments."""

    input_id: str
    dataset_id: str
    dataset_hash: str
    index_hash: str
    parent_contract_sha256: str
    parent_summary_sha256: str
    status: InputStatus
    reason: str | None
    fit_target_free_slot_count: int
    persistence_target_free_slot_count: int
    input_hash: str
    _fit_bars_by_symbol: Mapping[str, tuple[Bar, ...]]
    _tail_bars_by_symbol: Mapping[str, tuple[Bar, ...]]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        fit_bars = {symbol: tuple(bars) for symbol, bars in self._fit_bars_by_symbol.items()}
        tail_bars = {symbol: tuple(bars) for symbol, bars in self._tail_bars_by_symbol.items()}
        expected_fit_slots = len(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS) * (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP - 1
        )
        expected_persistence_slots = len(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS) * (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP
            - KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START
        )
        if (
            self.input_id != "kis.paper.private.daily.nas.sequence.input-v1"
            or self.dataset_id != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID
            or self.dataset_hash != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH
            or not preflight._is_sha256(self.index_hash)
            or self.parent_contract_sha256
            != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256
            or self.parent_summary_sha256
            != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256
            or self.status not in {"ready", "input_unavailable"}
            or self.fit_target_free_slot_count != expected_fit_slots
            or self.persistence_target_free_slot_count != expected_persistence_slots
            or not preflight._is_sha256(self.input_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("HMM persistence input identity is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or tuple(fit_bars) != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
                or tuple(tail_bars) != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
            ):
                raise ValueError("ready HMM persistence input is invalid")
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS:
                _verify_segment(
                    fit_bars[symbol],
                    symbol=symbol,
                    expected_count=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP,
                )
                _verify_segment(
                    tail_bars[symbol],
                    symbol=symbol,
                    expected_count=(
                        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_STOP
                        - KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_START
                    ),
                )
        elif self.reason not in _INPUT_REASONS or fit_bars or tail_bars:
            raise ValueError("unavailable HMM persistence input is invalid")
        expected_hash = _input_hash(
            input_id=self.input_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            index_hash=self.index_hash,
            parent_contract_sha256=self.parent_contract_sha256,
            parent_summary_sha256=self.parent_summary_sha256,
            status=self.status,
            reason=self.reason,
            fit_target_free_slot_count=self.fit_target_free_slot_count,
            persistence_target_free_slot_count=self.persistence_target_free_slot_count,
        )
        if self.input_hash != expected_hash:
            raise ValueError("HMM persistence input hash is invalid")
        object.__setattr__(self, "_fit_bars_by_symbol", MappingProxyType(fit_bars))
        object.__setattr__(self, "_tail_bars_by_symbol", MappingProxyType(tail_bars))

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
            "source": {
                "input_id": self.input_id,
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "index_hash": self.index_hash,
                "symbol_count": len(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS),
                "fit_source_indices": [0, 599],
                "retained_tail_source_indices": [1000, 1509],
                "omitted_original_screen_indices": [600, 999],
            },
            "parent_preflight": {
                "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_ID,
                "contract_sha256": self.parent_contract_sha256,
                "summary_sha256": self.parent_summary_sha256,
            },
            "status": self.status,
            "reason": self.reason,
            "fit_target_free_slot_count": self.fit_target_free_slot_count,
            "persistence_target_free_slot_count": self.persistence_target_free_slot_count,
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "predictions_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmPersistenceContract:
    """One frozen persistence-check contract and its in-memory model set."""

    input: KisNasD1IntradayRegimeHmmPersistenceInput
    precommit: KisNasD1IntradayRegimeHmmPersistencePrecommit
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    fit_reason: str | None
    model_set: preflight._ModelSet | None
    registry_entry: FrozenCampaignRegistryEntry


@dataclass(frozen=True, slots=True)
class KisNasD1IntradayRegimeHmmPersistenceRun:
    """Terminal source-local persistence result with source-safe evidence only."""

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
    per_symbol_primary_nonnegative: tuple[bool, ...]
    prefix_deterministic: bool
    extreme_exclusion: bool

    @property
    def primary_candidate_rate(self) -> float:
        return dict(self.candidate_rate_by_cost)[
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS
        ]

    @property
    def primary_all_long_rate(self) -> float:
        return dict(self.all_long_rate_by_cost)[
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS
        ]

    @property
    def passes_primary(self) -> bool:
        return (
            self.primary_candidate_rate - self.primary_all_long_rate
            >= KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_MIN_PRIMARY_EFFECT
            and self.primary_candidate_rate - self.primary_null_p95
            >= KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_MIN_PRIMARY_EFFECT
            and all(self.per_symbol_primary_nonnegative)
            and self.prefix_deterministic
        )


@dataclass(frozen=True, slots=True)
class _EvaluationMetrics:
    normal: _VariantMetrics
    extreme_control: _VariantMetrics

    @property
    def survives_controls(self) -> bool:
        return self.normal.passes_primary and self.extreme_control.passes_primary

    def safe_payload(self) -> dict[str, object]:
        return {
            "primary": {
                "candidate_vs_all_long": preflight._effect_relation(
                    self.normal.primary_candidate_rate - self.normal.primary_all_long_rate
                ),
                "candidate_vs_joint_null_p95": preflight._effect_relation(
                    self.normal.primary_candidate_rate - self.normal.primary_null_p95
                ),
                "candidate_rate_bucket": preflight._rate_bucket(self.normal.primary_candidate_rate),
                "all_long_rate_bucket": preflight._rate_bucket(self.normal.primary_all_long_rate),
                "every_symbol_nonnegative_vs_all_long": all(
                    self.normal.per_symbol_primary_nonnegative
                ),
            },
            "cost_sensitivity": {
                str(cost): preflight._effect_relation(
                    dict(self.normal.candidate_rate_by_cost)[cost]
                    - dict(self.normal.all_long_rate_by_cost)[cost]
                )
                for cost in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_COST_BPS
            },
            "screen": {
                "eligible_count_per_symbol": list(self.normal.eligible_count_by_symbol),
                "candidate_count_per_symbol": list(self.normal.candidate_count_by_symbol),
                "minimum_target_free_slots_per_symbol": (
                    preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL
                ),
                "minimum_candidate_slots_per_symbol": (
                    preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL
                ),
            },
            "causal_filter": {
                "mode": "forward_filtering_only",
                "prefix_deterministic": self.normal.prefix_deterministic,
                "warmup_source_indices": [1000, 1019],
                "decision_source_indices": [1020, 1508],
                "target_source_indices": [1021, 1509],
            },
            "joint_null": {
                "count": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_COUNT,
                "block_size_sessions": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_BLOCK_SIZE,
                "permutation": "joint_contiguous_date_blocks_across_symbols",
                "percentile": "p95_higher",
            },
            "extreme_control": {
                "threshold_abs_close_to_open_return": (
                    preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_EXTREME_RATIO
                ),
                "feature_and_target_exclusion": self.extreme_control.extreme_exclusion,
                "prefix_deterministic": self.extreme_control.prefix_deterministic,
                "primary_result": "survives" if self.survives_controls else "fails",
            },
            "numeric_metrics_persisted": False,
        }


def precommit_kis_nas_d1_intraday_regime_hmm_persistence(
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision: str,
    attempt_id: str = KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEFAULT_ATTEMPT_ID,
) -> KisNasD1IntradayRegimeHmmPersistencePrecommit:
    """Write the immutable config receipt before any local source is loaded."""

    if not isinstance(code_revision, str) or not code_revision.strip():
        raise ValueError("code revision is required")
    _require_attempt_id(attempt_id)
    run_directory = _external_run_directory(artifact_root, repo_root, attempt_id=attempt_id)
    payload = preflight._signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
            "attempt_id": attempt_id,
            "code_revision": code_revision,
            "claim": "one fixed later-window persistence check, not independent replication",
            "parent_preflight": {
                "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_ID,
                "contract_sha256": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256
                ),
                "summary_sha256": (
                    KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256
                ),
            },
            "geometry": _geometry_payload(),
            "cost_model": _cost_model_payload(),
            "null": {
                "count": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_COUNT,
                "block_size_sessions": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_BLOCK_SIZE,
                "permutation": "joint_contiguous_date_blocks_across_all_symbols",
                "percentile": "p95_higher",
            },
            "kill_test": _kill_test_payload(),
            "scope": _non_promoting_scope(),
            "artifact_policy": _artifact_policy(),
        },
        field_name="precommit_sha256",
    )
    path = run_directory / "persistence-precommit.json"
    preflight._write_or_verify_json(path, payload)
    return KisNasD1IntradayRegimeHmmPersistencePrecommit(
        artifact_root=Path(artifact_root).resolve(),
        repo_root=Path(repo_root).resolve(),
        attempt_id=attempt_id,
        precommit_path=path,
        precommit_sha256=preflight._verify_signed_payload(payload, field_name="precommit_sha256"),
    )


def load_kis_nas_d1_intraday_regime_hmm_persistence_input(
    *,
    manifest_path: Path,
    cache_root: Path,
    panel_root: Path,
    parent_contract_path: Path,
    parent_summary_path: Path,
    repo_root: Path | None = None,
) -> KisNasD1IntradayRegimeHmmPersistenceInput:
    """Reattest the parent receipt, then expose only train and later-tail bars."""

    _require_parent_lineage(parent_contract_path, parent_summary_path)
    from thericher_v2.data.kis_paper_daily_history_sequence_input import (
        load_kis_paper_daily_history_sequence_input,
    )

    source = load_kis_paper_daily_history_sequence_input(
        manifest_path=manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return build_kis_nas_d1_intraday_regime_hmm_persistence_input(
        source.development,
        input_id=source.input_id,
    )


def build_kis_nas_d1_intraday_regime_hmm_persistence_input(
    development_phase: object,
    *,
    input_id: str,
) -> KisNasD1IntradayRegimeHmmPersistenceInput:
    """Build a guarded input that omits all original preflight-screen bars."""

    phase = cast(Any, development_phase)
    try:
        _require_development_phase(phase, input_id=input_id)
        fit_bars = {
            symbol: _selected_segment(
                phase,
                symbol=symbol,
                start=0,
                stop=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP,
            )
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
        }
        tail_bars = {
            symbol: _selected_segment(
                phase,
                symbol=symbol,
                start=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_START,
                stop=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_STOP,
            )
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
        }
    except ValueError as error:
        return _unavailable_input(phase, input_id=input_id, reason=_safe_input_reason(error))
    return KisNasD1IntradayRegimeHmmPersistenceInput(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        parent_contract_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256,
        parent_summary_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256,
        status="ready",
        reason=None,
        fit_target_free_slot_count=_fit_target_free_slot_count(),
        persistence_target_free_slot_count=_persistence_target_free_slot_count(),
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=str(phase.parent_dataset_id),
            dataset_hash=str(phase.parent_dataset_hash),
            index_hash=str(phase.index_hash),
            parent_contract_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256,
            parent_summary_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256,
            status="ready",
            reason=None,
            fit_target_free_slot_count=_fit_target_free_slot_count(),
            persistence_target_free_slot_count=_persistence_target_free_slot_count(),
        ),
        _fit_bars_by_symbol=fit_bars,
        _tail_bars_by_symbol=tail_bars,
    )


def freeze_kis_nas_d1_intraday_regime_hmm_persistence_campaign(
    input: KisNasD1IntradayRegimeHmmPersistenceInput,
    *,
    precommit: KisNasD1IntradayRegimeHmmPersistencePrecommit,
) -> KisNasD1IntradayRegimeHmmPersistenceContract:
    """Fit only the fixed training slice after validating the earlier precommit."""

    _verify_precommit(precommit)
    model_set: preflight._ModelSet | None = None
    fit_reason: str | None = input.reason if input.status == "input_unavailable" else None
    if input.status == "ready":
        try:
            model_set = _fit_model_set(input)
        except ValueError as error:
            fit_reason = preflight._safe_fit_reason(error)
    payload = preflight._signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
            "precommit_sha256": precommit.precommit_sha256,
            "source": input.safe_payload()["source"],
            "parent_preflight": input.safe_payload()["parent_preflight"],
            "input": {
                "status": input.status,
                "reason": input.reason,
                "input_hash": input.input_hash,
                "fit_target_free_slot_count": input.fit_target_free_slot_count,
                "persistence_target_free_slot_count": input.persistence_target_free_slot_count,
            },
            "geometry": _geometry_payload(),
            "model": {
                "family": "per_symbol_two_state_diagonal_gaussian_hmm",
                "em_steps": preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_EM_STEPS,
                "max_seconds": preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MAX_SECONDS,
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
            "cost_model": _cost_model_payload(),
            "baselines": {
                "all_long": "same_later_tail_slots_after_cost",
                "all_flat": "descriptive_only",
            },
            "null": {
                "count": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_COUNT,
                "block_size_sessions": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_BLOCK_SIZE,
                "permutation": "joint_contiguous_date_blocks_across_all_symbols",
                "percentile": "p95_higher",
            },
            "kill_test": _kill_test_payload(),
            "scope": _non_promoting_scope(),
            "artifact_policy": _artifact_policy(),
        },
        field_name="campaign_contract_sha256",
    )
    recorded = preflight._write_or_reattach_contract(
        precommit.precommit_path.parent / "campaign-contract.json",
        payload,
    )
    contract_sha256 = preflight._verify_signed_payload(
        recorded,
        field_name="campaign_contract_sha256",
    )
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=input.dataset_hash,
        split_hash=preflight._sha256_json(cast(dict[str, object], recorded["geometry"])),
        cost_model_hash=preflight._sha256_json(cast(dict[str, object], recorded["cost_model"])),
        trial_family=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
        holdout_access="opened",
        artifact_root=precommit.artifact_root,
        repo_root=precommit.repo_root,
    )
    return KisNasD1IntradayRegimeHmmPersistenceContract(
        input=input,
        precommit=precommit,
        artifact_root=precommit.artifact_root,
        repo_root=precommit.repo_root,
        attempt_id=precommit.attempt_id,
        run_directory=precommit.precommit_path.parent,
        contract_path=precommit.precommit_path.parent / "campaign-contract.json",
        contract_sha256=contract_sha256,
        fit_reason=fit_reason,
        model_set=model_set,
        registry_entry=registry_entry,
    )


def run_kis_nas_d1_intraday_regime_hmm_persistence(
    contract: KisNasD1IntradayRegimeHmmPersistenceContract,
) -> KisNasD1IntradayRegimeHmmPersistenceRun:
    """Run or reattach the one fixed later-window persistence check."""

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
            reason = preflight._safe_fit_reason(error)
        else:
            status = (
                "source_local_non_promoting"
                if metrics.survives_controls
                else "persistence_falsified"
            )
            reason = (
                None
                if status == "source_local_non_promoting"
                else "frozen_persistence_kill_test_failed"
            )
    summary = preflight._signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "precommit_sha256": contract.precommit.precommit_sha256,
            "phase": "cpu_only_date_disjoint_persistence_check",
            "status": status,
            "reason": reason,
            "input": {
                "input_hash": contract.input.input_hash,
                "status": contract.input.status,
                "fit_target_free_slot_count": contract.input.fit_target_free_slot_count,
                "persistence_target_free_slot_count": (
                    contract.input.persistence_target_free_slot_count
                ),
            },
            "metrics": None if metrics is None else metrics.safe_payload(),
            "scope": _non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    summary_path = contract.run_directory / "cpu-summary.json"
    preflight._write_or_verify_json(summary_path, summary)
    return _with_outcome(contract, _run_from_summary(contract, summary_path))


def _fit_model_set(input: KisNasD1IntradayRegimeHmmPersistenceInput) -> preflight._ModelSet:
    deadline = time.perf_counter() + preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MAX_SECONDS
    symbols: dict[str, preflight._SymbolModelSet] = {}
    for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS:
        bars = input._fit_bars_by_symbol[symbol]
        features = _feature_matrix(bars)
        extremes = preflight._extreme_mask(bars)
        normal_model = preflight._fit_two_state_hmm(features, deadline=deadline)
        normal_states = preflight._filter_states(normal_model, features[:-1])
        normal_labels = _fit_labels(bars, extreme_exclusion=False)
        normal_long_state = preflight._derive_long_state(normal_states, normal_labels)

        control_features = features[~extremes]
        if (
            len(control_features)
            < preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS * 2
        ):
            raise ValueError("insufficient_fit_state_targets")
        control_model = preflight._fit_two_state_hmm(control_features, deadline=deadline)
        control_states = preflight._filter_states(
            control_model,
            features[:-1],
            valid_mask=~extremes[:-1],
        )
        control_labels, control_mask = _fit_labels(
            bars,
            extreme_exclusion=True,
            extremes=extremes,
        )
        control_long_state = preflight._derive_long_state(
            control_states[control_mask],
            control_labels[control_mask],
        )
        symbols[symbol] = preflight._SymbolModelSet(
            normal_model=normal_model,
            normal_long_state=normal_long_state,
            extreme_control_model=control_model,
            extreme_control_long_state=control_long_state,
        )
    payload = {
        symbol: {
            "normal": model.normal_model.parameter_sha256,
            "normal_long_state": model.normal_long_state,
            "extreme_control": model.extreme_control_model.parameter_sha256,
            "extreme_control_long_state": model.extreme_control_long_state,
        }
        for symbol, model in symbols.items()
    }
    return preflight._ModelSet(
        symbols=MappingProxyType(symbols),
        model_set_sha256=preflight._sha256_json(payload),
    )


def _evaluate(
    input: KisNasD1IntradayRegimeHmmPersistenceInput,
    model_set: preflight._ModelSet,
) -> _EvaluationMetrics:
    return _EvaluationMetrics(
        normal=_evaluate_variant(input, model_set, extreme_exclusion=False),
        extreme_control=_evaluate_variant(input, model_set, extreme_exclusion=True),
    )


def _evaluate_variant(
    input: KisNasD1IntradayRegimeHmmPersistenceInput,
    model_set: preflight._ModelSet,
    *,
    extreme_exclusion: bool,
) -> _VariantMetrics:
    numpy = preflight._numpy()
    labels_by_symbol: dict[str, Any] = {}
    candidate_masks: dict[str, Any] = {}
    eligible_masks: dict[str, Any] = {}
    candidate_counts: list[int] = []
    eligible_counts: list[int] = []
    per_symbol_primary_nonnegative: list[bool] = []
    prefix_deterministic = True
    for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS:
        bars = input._tail_bars_by_symbol[symbol]
        features = _feature_matrix(bars)
        extremes = preflight._extreme_mask(bars)
        selected = model_set.symbols[symbol]
        model = selected.extreme_control_model if extreme_exclusion else selected.normal_model
        long_state = (
            selected.extreme_control_long_state if extreme_exclusion else selected.normal_long_state
        )
        valid_features = ~extremes if extreme_exclusion else numpy.ones(len(bars), dtype=bool)
        states, prefix_ok = _tail_states_with_prefix_proof(
            model,
            features,
            valid_features=valid_features,
        )
        prefix_deterministic = prefix_deterministic and prefix_ok
        labels = _tail_labels(
            bars,
            cost_bps=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS,
        )
        eligible = numpy.ones(len(labels), dtype=bool)
        if extreme_exclusion:
            eligible = numpy.asarray(
                [
                    not extremes[index] and not extremes[index + 1]
                    for index in range(
                        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START,
                        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP,
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
        per_symbol_primary_nonnegative.append(
            _masked_single_rate(labels, candidate) >= _masked_single_rate(labels, eligible)
        )
    if any(
        count < preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL
        for count in eligible_counts
    ) or any(
        count < preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL
        for count in candidate_counts
    ):
        raise ValueError("insufficient_fit_state_targets")
    rates_by_cost: list[tuple[int, float]] = []
    long_rates_by_cost: list[tuple[int, float]] = []
    for cost in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_COST_BPS:
        cost_labels = {
            symbol: _tail_labels(input._tail_bars_by_symbol[symbol], cost_bps=cost)
            for symbol in KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
        }
        rates_by_cost.append((cost, preflight._masked_rate(cost_labels, candidate_masks)))
        long_rates_by_cost.append((cost, preflight._masked_rate(cost_labels, eligible_masks)))
    null_values = [
        preflight._masked_rate(
            preflight._joint_block_permute_labels(
                labels_by_symbol,
                seed=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_SEED_BASE + offset,
            ),
            candidate_masks,
        )
        for offset in range(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_NULL_COUNT)
    ]
    return _VariantMetrics(
        candidate_rate_by_cost=tuple(rates_by_cost),
        all_long_rate_by_cost=tuple(long_rates_by_cost),
        primary_null_p95=preflight._percentile_higher(null_values),
        candidate_count_by_symbol=tuple(candidate_counts),
        eligible_count_by_symbol=tuple(eligible_counts),
        per_symbol_primary_nonnegative=tuple(per_symbol_primary_nonnegative),
        prefix_deterministic=prefix_deterministic,
        extreme_exclusion=extreme_exclusion,
    )


def _feature_matrix(bars: Sequence[Bar]) -> Any:
    numpy = preflight._numpy()
    expected_count = len(bars)
    if expected_count not in {
        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP,
        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_STOP
        - KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_START,
    }:
        raise ValueError("invalid_candle_ratio")
    values = numpy.asarray([preflight._feature_row(bar) for bar in bars], dtype=numpy.float64)
    if (
        values.shape
        != (expected_count, len(preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES))
        or not numpy.isfinite(values).all()
    ):
        raise ValueError("invalid_candle_ratio")
    return values


def _fit_labels(
    bars: Sequence[Bar],
    *,
    extreme_exclusion: bool,
    extremes: Any | None = None,
) -> tuple[Any, Any] | Any:
    numpy = preflight._numpy()
    labels = numpy.asarray(
        [
            preflight._target_label_after_cost(
                bars[index + 1],
                cost_bps=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS,
            )
            for index in range(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP - 1)
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


def _tail_states_with_prefix_proof(
    model: preflight._FittedGaussianHmm,
    feature_rows: Any,
    *,
    valid_features: Any,
) -> tuple[Any, bool]:
    numpy = preflight._numpy()
    values = numpy.asarray(feature_rows, dtype=numpy.float64)
    valid = numpy.asarray(valid_features, dtype=bool)
    stop = KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP
    filtered = preflight._filter_states(model, values[:stop], valid_mask=valid[:stop])
    states = filtered[KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START:]
    prefix_deterministic = True
    for decision_index, observed_state in zip(
        range(
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START,
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP,
        ),
        states,
        strict=True,
    ):
        prefix = preflight._filter_states(
            model,
            values[: decision_index + 1],
            valid_mask=valid[: decision_index + 1],
        )
        if int(prefix[-1]) != int(observed_state):
            prefix_deterministic = False
            break
    return states, prefix_deterministic


def _tail_labels(bars: Sequence[Bar], *, cost_bps: int) -> Any:
    numpy = preflight._numpy()
    return numpy.asarray(
        [
            preflight._target_label_after_cost(bars[index + 1], cost_bps=cost_bps)
            for index in range(
                KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START,
                KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP,
            )
        ],
        dtype=numpy.int8,
    )


def _masked_single_rate(labels: Any, mask: Any) -> float:
    numpy = preflight._numpy()
    values = numpy.asarray(labels, dtype=numpy.int8)
    selected = values[numpy.asarray(mask, dtype=bool)]
    if not len(selected) or not preflight._are_binary_labels(selected):
        raise ValueError("nonfinite_fit")
    result = float(selected.mean())
    if not math.isfinite(result):
        raise ValueError("nonfinite_fit")
    return result


def _require_parent_lineage(contract_path: Path, summary_path: Path) -> None:
    contract = preflight._read_json_object(contract_path)
    summary = preflight._read_json_object(summary_path)
    if (
        preflight._verify_signed_payload(contract, field_name="campaign_contract_sha256")
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256
        or preflight._verify_signed_payload(summary, field_name="summary_sha256")
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256
        or contract.get("campaign_id") != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_ID
        or summary.get("campaign_id") != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_ID
        or summary.get("status") != "source_local_non_promoting"
        or summary.get("campaign_contract_sha256")
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256
    ):
        raise ValueError("parent_lineage_invalid")


def _require_development_phase(phase: Any, *, input_id: str) -> None:
    if (
        input_id != "kis.paper.private.daily.nas.sequence.input-v1"
        or getattr(phase, "phase", None) != "development"
        or getattr(phase, "parent_dataset_id", None)
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID
        or getattr(phase, "parent_dataset_hash", None)
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH
        or not preflight._is_sha256(getattr(phase, "index_hash", None))
        or tuple(getattr(phase, "bars_by_symbol", ()))
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS
        or len(getattr(phase, "common_sessions", ()))
        != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEVELOPMENT_SESSIONS
    ):
        raise ValueError("source_stream_mismatch")


def _selected_segment(
    phase: Any,
    *,
    symbol: str,
    start: int,
    stop: int,
) -> tuple[Bar, ...]:
    stream = phase.bars_by_symbol[symbol].bars
    bars = tuple(stream[start:stop])
    sessions = tuple(phase.common_sessions[start:stop])
    if len(bars) != stop - start or tuple(bar.start_ts.date() for bar in bars) != sessions:
        raise ValueError("insufficient_source_sessions")
    _verify_segment(bars, symbol=symbol, expected_count=stop - start)
    return bars


def _verify_segment(bars: Sequence[Bar], *, symbol: str, expected_count: int) -> None:
    if len(bars) != expected_count:
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
        preflight._feature_row(bar)
        if previous is not None and (
            bar.start_ts <= previous.start_ts or bar.end_ts <= previous.end_ts
        ):
            raise ValueError("source_stream_mismatch")
        previous = bar


def _unavailable_input(
    phase: Any,
    *,
    input_id: str,
    reason: str,
) -> KisNasD1IntradayRegimeHmmPersistenceInput:
    safe_reason = _safe_input_reason(ValueError(reason))
    dataset_id = str(
        getattr(phase, "parent_dataset_id", KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID)
    )
    if dataset_id != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID:
        dataset_id = KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_ID
    dataset_hash = str(
        getattr(
            phase, "parent_dataset_hash", KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH
        )
    )
    if dataset_hash != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH:
        dataset_hash = KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DATASET_HASH
    index_hash = str(getattr(phase, "index_hash", ""))
    if not preflight._is_sha256(index_hash):
        index_hash = "sha256:" + "0" * 64
    return KisNasD1IntradayRegimeHmmPersistenceInput(
        input_id=input_id,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        index_hash=index_hash,
        parent_contract_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256,
        parent_summary_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256,
        status="input_unavailable",
        reason=safe_reason,
        fit_target_free_slot_count=_fit_target_free_slot_count(),
        persistence_target_free_slot_count=_persistence_target_free_slot_count(),
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            index_hash=index_hash,
            parent_contract_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_CONTRACT_SHA256,
            parent_summary_sha256=KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PARENT_SUMMARY_SHA256,
            status="input_unavailable",
            reason=safe_reason,
            fit_target_free_slot_count=_fit_target_free_slot_count(),
            persistence_target_free_slot_count=_persistence_target_free_slot_count(),
        ),
        _fit_bars_by_symbol={},
        _tail_bars_by_symbol={},
    )


def _fit_target_free_slot_count() -> int:
    return len(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS) * (
        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP - 1
    )


def _persistence_target_free_slot_count() -> int:
    return len(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_SYMBOLS) * (
        KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_STOP
        - KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DECISION_START
    )


def _geometry_payload() -> dict[str, object]:
    return {
        "development_source_session_count": (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_DEVELOPMENT_SESSIONS
        ),
        "fit_source_indices": [0, 599],
        "fit_mapping_decision_indices": [0, 598],
        "omitted_original_screen_indices": [
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_OMITTED_START,
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_OMITTED_STOP - 1,
        ],
        "retained_tail_source_indices": [1000, 1509],
        "filter_warmup_source_indices": [1000, 1019],
        "decision_source_indices": [1020, 1508],
        "target_source_indices": [1021, 1509],
        "target": "next_session_open_to_close_direction_after_round_trip_cost",
        "features": list(preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES),
        "features_use_completed_decision_session_ratios_only": True,
        "original_screen_input_exposed": False,
    }


def _cost_model_payload() -> dict[str, object]:
    return {
        "primary_round_trip_bps": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_PRIMARY_COST_BPS,
        "sensitivity_round_trip_bps": list(KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_COST_BPS),
        "selection_cost": "primary_only",
    }


def _kill_test_payload() -> dict[str, object]:
    return {
        "minimum_pooled_effect_over_all_long_and_joint_null_p95": (
            KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_MIN_PRIMARY_EFFECT
        ),
        "all_symbols_nonnegative_vs_all_long_at_primary_cost": True,
        "minimum_fit_state_targets": preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_FIT_STATE_TARGETS,
        "minimum_later_tail_slots_per_symbol": (
            preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_SCREEN_SLOTS_PER_SYMBOL
        ),
        "minimum_candidate_slots_per_symbol": (
            preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_MIN_LONG_SLOTS_PER_SYMBOL
        ),
        "prefix_filter_determinism": True,
        "positive_session_ohlc_multiplier_invariance": True,
        "extreme_session_abs_close_open_threshold": (
            preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_EXTREME_RATIO
        ),
        "extreme_control_must_survive": True,
        "no_original_screen_input": True,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "repository_storage_allowed": False,
        "raw_rows_persisted": False,
        "dates_persisted": False,
        "feature_values_persisted": False,
        "target_values_persisted": False,
        "probabilities_persisted": False,
        "fitted_parameters_persisted": False,
        "checkpoint_written": False,
    }


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


def _external_run_directory(artifact_root: Path, repo_root: Path, *, attempt_id: str) -> Path:
    requested_root = Path(artifact_root)
    repository = Path(repo_root).resolve()
    _reject_repo_artifact_path(requested_root, repository)
    if requested_root.exists() and requested_root.is_symlink():
        raise ValueError("model artifact root must not be a symlink")
    requested_root.mkdir(parents=True, exist_ok=True)
    root = requested_root.resolve()
    run_directory = root / "research" / KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID / attempt_id
    if run_directory.exists() and run_directory.is_symlink():
        raise ValueError("HMM persistence run directory must not be a symlink")
    run_directory.mkdir(parents=True, exist_ok=True)
    return run_directory


def _verify_precommit(precommit: KisNasD1IntradayRegimeHmmPersistencePrecommit) -> None:
    if (
        not isinstance(precommit, KisNasD1IntradayRegimeHmmPersistencePrecommit)
        or not preflight._is_sha256(precommit.precommit_sha256)
        or not precommit.precommit_path.is_file()
        or precommit.precommit_path.is_symlink()
        or precommit.precommit_path.parent
        != _external_run_directory(
            precommit.artifact_root,
            precommit.repo_root,
            attempt_id=precommit.attempt_id,
        )
    ):
        raise ValueError("HMM persistence precommit is invalid")
    payload = preflight._read_json_object(precommit.precommit_path)
    if (
        preflight._verify_signed_payload(payload, field_name="precommit_sha256")
        != precommit.precommit_sha256
        or payload.get("campaign_id") != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID
        or payload.get("attempt_id") != precommit.attempt_id
        or payload.get("geometry") != _geometry_payload()
        or payload.get("cost_model") != _cost_model_payload()
        or payload.get("kill_test") != _kill_test_payload()
    ):
        raise ValueError("HMM persistence precommit is invalid")


def _load_existing_run(
    contract: KisNasD1IntradayRegimeHmmPersistenceContract,
) -> KisNasD1IntradayRegimeHmmPersistenceRun | None:
    path = contract.run_directory / "cpu-summary.json"
    if not path.exists():
        return None
    payload = preflight._read_json_object(path)
    if (
        preflight._verify_signed_payload(payload, field_name="summary_sha256")
        and payload.get("campaign_id") == KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID
        and payload.get("campaign_contract_sha256") == contract.contract_sha256
        and payload.get("precommit_sha256") == contract.precommit.precommit_sha256
    ):
        return _run_from_summary(contract, path)
    raise ValueError("HMM persistence summary conflicts with contract")


def _run_from_summary(
    contract: KisNasD1IntradayRegimeHmmPersistenceContract,
    path: Path,
) -> KisNasD1IntradayRegimeHmmPersistenceRun:
    payload = preflight._read_json_object(path)
    summary_sha256 = preflight._verify_signed_payload(payload, field_name="summary_sha256")
    status = payload.get("status")
    reason = payload.get("reason")
    if (
        payload.get("campaign_id") != KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_ID
        or payload.get("campaign_contract_sha256") != contract.contract_sha256
        or payload.get("precommit_sha256") != contract.precommit.precommit_sha256
        or payload.get("phase") != "cpu_only_date_disjoint_persistence_check"
        or status
        not in {"input_unavailable", "persistence_falsified", "source_local_non_promoting"}
        or (reason is not None and not isinstance(reason, str))
        or not isinstance(payload.get("input"), dict)
        or not isinstance(payload.get("scope"), dict)
    ):
        raise ValueError("HMM persistence summary is invalid")
    return KisNasD1IntradayRegimeHmmPersistenceRun(
        status=cast(ResultStatus, status),
        reason=cast(str | None, reason),
        summary_path=path,
        summary_sha256=summary_sha256,
        registry_outcome=_outcome_placeholder(contract, summary_sha256),
    )


def _with_outcome(
    contract: KisNasD1IntradayRegimeHmmPersistenceContract,
    run: KisNasD1IntradayRegimeHmmPersistenceRun,
) -> KisNasD1IntradayRegimeHmmPersistenceRun:
    outcome = register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class=(
            "non_promoting_failed"
            if run.status in {"input_unavailable", "persistence_falsified"}
            else "non_promoting_completed"
        ),
        outcome_reference_sha256=run.summary_sha256,
        artifact_root=contract.artifact_root,
        repo_root=contract.repo_root,
    )
    return KisNasD1IntradayRegimeHmmPersistenceRun(
        status=run.status,
        reason=run.reason,
        summary_path=run.summary_path,
        summary_sha256=run.summary_sha256,
        registry_outcome=outcome,
    )


def _outcome_placeholder(
    contract: KisNasD1IntradayRegimeHmmPersistenceContract,
    summary_sha256: str,
) -> CampaignOutcomeRegistryEntry:
    return CampaignOutcomeRegistryEntry(
        contract_hash=contract.contract_sha256,
        outcome_class="non_promoting_completed",
        outcome_reference_sha256=summary_sha256,
        recorded_at=contract.registry_entry.recorded_at,
        record_path=contract.registry_entry.record_path,
        record_sha256=contract.registry_entry.record_sha256,
    )


def _input_hash(
    *,
    input_id: str,
    dataset_id: str,
    dataset_hash: str,
    index_hash: str,
    parent_contract_sha256: str,
    parent_summary_sha256: str,
    status: InputStatus,
    reason: str | None,
    fit_target_free_slot_count: int,
    persistence_target_free_slot_count: int,
) -> str:
    return preflight._sha256_json(
        {
            "input_id": input_id,
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "index_hash": index_hash,
            "parent_contract_sha256": parent_contract_sha256,
            "parent_summary_sha256": parent_summary_sha256,
            "status": status,
            "reason": reason,
            "fit_target_free_slot_count": fit_target_free_slot_count,
            "persistence_target_free_slot_count": persistence_target_free_slot_count,
            "fit_stop": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_FIT_STOP,
            "tail_start": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_START,
            "tail_stop": KIS_NAS_D1_INTRADAY_REGIME_HMM_PERSISTENCE_TAIL_STOP,
            "features": list(preflight.KIS_NAS_D1_INTRADAY_REGIME_HMM_FEATURE_NAMES),
        }
    )


def _safe_input_reason(error: ValueError) -> str:
    reason = str(error)
    return reason if reason in _INPUT_REASONS else "source_stream_mismatch"


def _require_attempt_id(value: str) -> None:
    if not isinstance(value, str) or not _SAFE_ATTEMPT_ID.fullmatch(value):
        raise ValueError("HMM persistence attempt id is invalid")

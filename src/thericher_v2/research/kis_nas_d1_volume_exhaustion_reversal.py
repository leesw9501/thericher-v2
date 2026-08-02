"""CPU-only falsification of one fixed KIS NAS D1 volume-exhaustion rule.

This leaf keeps raw OHLCV values and next-session returns in memory. External
evidence contains only frozen contract identities, counts, categorical metric
relations, and hashes. It has no provider, credential, execution, Paper, GPU,
or model-training surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from types import MappingProxyType
from typing import Any, Literal, cast

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

from .artifact_paths import ensure_external_artifact_directory
from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)

KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID = "kis-nas-d1-volume-exhaustion-reversal-v1"
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_ID = (
    "kis.paper.private.daily.nas.history.panel-v1"
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS = (
    "AAPL",
    "AMZN",
    "GOOGL",
    "META",
    "MSFT",
    "NVDA",
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEVELOPMENT_SESSIONS = 1510
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_STRUCTURAL_SESSIONS = 1000
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PURGE_SESSIONS = 22
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_START = (
    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_STRUCTURAL_SESSIONS
    + KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PURGE_SESSIONS
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK = 20
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START = (
    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_START
    + KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_STOP = (
    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEVELOPMENT_SESSIONS - 2
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_RANGE_MULTIPLIER = Decimal("2.0")
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_CLOSE_LOCATION_MAX = Decimal("0.25")
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_VOLUME_MULTIPLIER = Decimal("1.5")
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DISCONTINUITY_LIMIT = Decimal("0.20")
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SIGNAL_COUNT = 50
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SYMBOL_COUNT = 4
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_COST_BPS = (
    Decimal("10"),
    Decimal("15"),
    Decimal("20"),
)
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PRIMARY_COST_BPS = Decimal("20")
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT = 64
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE = 10
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_SEED_BASE = 60_260_801
KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEFAULT_ATTEMPT_ID = "cpu-falsification-r1"

VolumeExhaustionInputStatus = Literal["ready", "input_unavailable"]
VolumeExhaustionResultStatus = Literal[
    "falsified",
    "inconclusive_non_promoting",
    "input_unavailable",
]

_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_UNAVAILABLE_REASONS = frozenset(
    {
        "insufficient_target_free_signal_coverage",
        "source_stream_mismatch",
        "no_evaluation_candidate_signals",
        "cpu_evaluation_unavailable",
    }
)


@dataclass(frozen=True, slots=True)
class KisNasD1VolumeExhaustionReversalInput:
    """A verified development-only input with a target-free signal census."""

    input_id: str
    dataset_id: str
    dataset_hash: str
    index_hash: str
    status: VolumeExhaustionInputStatus
    reason: str | None
    structural_slot_count: int
    structural_signal_count: int
    structural_signal_symbol_count: int
    evaluation_slot_count: int
    input_hash: str
    _bars_by_symbol: Mapping[str, tuple[Bar, ...]]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        bars_by_symbol = dict(self._bars_by_symbol)
        expected_evaluation_slots = len(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS) * (
            KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_STOP
            - KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START
            + 1
        )
        if (
            self.input_id != "kis.paper.private.daily.nas.sequence.input-v1"
            or self.dataset_id != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_ID
            or self.dataset_hash != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_HASH
            or not _is_sha256(self.index_hash)
            or self.status not in {"ready", "input_unavailable"}
            or self.structural_slot_count < 0
            or self.structural_signal_count < 0
            or self.structural_signal_symbol_count < 0
            or self.structural_signal_symbol_count
            > len(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS)
            or self.evaluation_slot_count != expected_evaluation_slots
            or not _is_sha256(self.input_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS NAS D1 volume-exhaustion input identity is invalid")
        if self.status == "ready":
            if (
                self.reason is not None
                or tuple(bars_by_symbol) != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS
                or self.structural_signal_count
                < KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SIGNAL_COUNT
                or self.structural_signal_symbol_count
                < KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SYMBOL_COUNT
            ):
                raise ValueError("ready KIS NAS D1 volume-exhaustion input is invalid")
            for symbol in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS:
                bars = bars_by_symbol[symbol]
                _verified_symbol_bars(
                    bars,
                    symbol=symbol,
                    sessions=tuple(bar.start_ts.date() for bar in bars),
                )
        elif self.reason not in _UNAVAILABLE_REASONS:
            raise ValueError("unavailable KIS NAS D1 volume-exhaustion input is invalid")
        expected_hash = _input_hash(
            input_id=self.input_id,
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            index_hash=self.index_hash,
            status=self.status,
            reason=self.reason,
            structural_slot_count=self.structural_slot_count,
            structural_signal_count=self.structural_signal_count,
            structural_signal_symbol_count=self.structural_signal_symbol_count,
            evaluation_slot_count=self.evaluation_slot_count,
        )
        if self.input_hash != expected_hash:
            raise ValueError("KIS NAS D1 volume-exhaustion input hash is invalid")
        object.__setattr__(
            self,
            "_bars_by_symbol",
            MappingProxyType({symbol: tuple(bars) for symbol, bars in bars_by_symbol.items()}),
        )

    def safe_payload(self) -> dict[str, object]:
        """Return only source identity and structural evidence."""

        return {
            "schema_version": self.schema_version,
            "campaign_id": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
            "source": {
                "input_id": self.input_id,
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "index_hash": self.index_hash,
                "phase": "development_only",
                "symbol_count": len(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS),
            },
            "status": self.status,
            "reason": self.reason,
            "structural_slot_count": self.structural_slot_count,
            "structural_signal_count": self.structural_signal_count,
            "structural_signal_symbol_count": self.structural_signal_symbol_count,
            "evaluation_slot_count": self.evaluation_slot_count,
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "predictions_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolumeExhaustionReversalMetrics:
    """Private numeric falsification evidence with a categorical projection."""

    candidate_trade_count: int
    candidate_symbol_count: int
    candle_only_trade_count: int
    evaluation_slot_count: int
    candidate_net_mean_bps_by_cost: tuple[tuple[str, float], ...]
    candle_only_net_mean_bps_by_cost: tuple[tuple[str, float], ...]
    null_p95_net_mean_bps_primary_cost: float
    null_count: int

    def __post_init__(self) -> None:
        costs = tuple(
            _decimal_text(cost)
            for cost in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_COST_BPS
        )
        candidate = dict(self.candidate_net_mean_bps_by_cost)
        candle_only = dict(self.candle_only_net_mean_bps_by_cost)
        if (
            self.candidate_trade_count <= 0
            or self.candidate_symbol_count <= 0
            or self.candle_only_trade_count < self.candidate_trade_count
            or self.evaluation_slot_count <= 0
            or tuple(candidate) != costs
            or tuple(candle_only) != costs
            or self.null_count != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT
            or not math.isfinite(self.null_p95_net_mean_bps_primary_cost)
            or any(not math.isfinite(value) for value in candidate.values())
            or any(not math.isfinite(value) for value in candle_only.values())
        ):
            raise ValueError("KIS NAS D1 volume-exhaustion metrics are invalid")

    @property
    def primary_net_mean_bps(self) -> float:
        return dict(self.candidate_net_mean_bps_by_cost)[
            _decimal_text(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PRIMARY_COST_BPS)
        ]

    @property
    def candidate_exceeds_candle_only_at_all_costs(self) -> bool:
        candidate = dict(self.candidate_net_mean_bps_by_cost)
        candle_only = dict(self.candle_only_net_mean_bps_by_cost)
        return all(candidate[cost] > candle_only[cost] for cost in candidate)

    @property
    def candidate_exceeds_null_p95(self) -> bool:
        return self.primary_net_mean_bps > self.null_p95_net_mean_bps_primary_cost

    @property
    def is_falsified(self) -> bool:
        return (
            self.primary_net_mean_bps <= 0.0
            or not self.candidate_exceeds_candle_only_at_all_costs
            or not self.candidate_exceeds_null_p95
        )

    def safe_payload(self) -> dict[str, object]:
        candidate = dict(self.candidate_net_mean_bps_by_cost)
        candle_only = dict(self.candle_only_net_mean_bps_by_cost)
        primary_cost = _decimal_text(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PRIMARY_COST_BPS)
        return {
            "candidate_trade_count": self.candidate_trade_count,
            "candidate_symbol_count": self.candidate_symbol_count,
            "candle_only_trade_count": self.candle_only_trade_count,
            "evaluation_slot_count": self.evaluation_slot_count,
            "primary_net_mean_relation_to_flat": (
                "positive" if self.primary_net_mean_bps > 0.0 else "nonpositive"
            ),
            "candidate_vs_candle_only_by_round_trip_cost": {
                cost: (
                    "strictly_greater"
                    if candidate[cost] > candle_only[cost]
                    else "not_strictly_greater"
                )
                for cost in candidate
            },
            "candidate_vs_null_p95_primary_cost": (
                "strictly_greater"
                if self.candidate_exceeds_null_p95
                else "not_strictly_greater"
            ),
            "primary_round_trip_cost_bps": primary_cost,
            "null_count": self.null_count,
            "null_geometry": {
                "permutation": "within_symbol_contiguous_target_return_blocks",
                "block_size": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE,
                "trailing_partial_block": "fixed_in_place",
            },
            "numeric_metrics_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolumeExhaustionReversalContract:
    """One immutable CPU-only falsification contract and custody record."""

    input: KisNasD1VolumeExhaustionReversalInput
    artifact_root: Path
    repo_root: Path
    attempt_id: str
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    registry_entry: FrozenCampaignRegistryEntry


@dataclass(frozen=True, slots=True)
class KisNasD1VolumeExhaustionReversalRun:
    """Source-safe terminal evidence for the fixed candidate."""

    status: VolumeExhaustionResultStatus
    reason: str | None
    summary_path: Path
    summary_sha256: str
    registry_outcome: CampaignOutcomeRegistryEntry


@dataclass(frozen=True, slots=True)
class _SignalFlags:
    candidate: bool
    candle_only: bool


def load_kis_nas_d1_volume_exhaustion_reversal_input(
    *,
    manifest_path: Path,
    cache_root: Path,
    panel_root: Path,
    repo_root: Path | None = None,
) -> KisNasD1VolumeExhaustionReversalInput:
    """Reattest the parent panel, then expose only its development phase."""

    from thericher_v2.data.kis_paper_daily_history_sequence_input import (
        load_kis_paper_daily_history_sequence_input,
    )

    source = load_kis_paper_daily_history_sequence_input(
        manifest_path=manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return build_kis_nas_d1_volume_exhaustion_reversal_input(
        source.development,
        input_id=source.input_id,
    )


def build_kis_nas_d1_volume_exhaustion_reversal_input(
    development_phase: object,
    *,
    input_id: str,
) -> KisNasD1VolumeExhaustionReversalInput:
    """Census a fixed rule without opening any next-session target."""

    phase = cast(Any, development_phase)
    _require_development_phase(phase, input_id=input_id)
    try:
        bars_by_symbol = {
            symbol: _verified_symbol_bars(
                tuple(phase.bars_by_symbol[symbol].bars),
                symbol=symbol,
                sessions=tuple(phase.common_sessions),
            )
            for symbol in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS
        }
    except (AttributeError, TypeError, ValueError):
        return _unavailable_input(
            phase,
            input_id=input_id,
            reason="source_stream_mismatch",
            bars_by_symbol={},
            structural_slot_count=0,
            structural_signal_count=0,
            structural_signal_symbol_count=0,
        )

    structural_slot_count, signal_count, signal_symbol_count = _structural_census(bars_by_symbol)
    if (
        signal_count < KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SIGNAL_COUNT
        or signal_symbol_count < KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SYMBOL_COUNT
    ):
        return _unavailable_input(
            phase,
            input_id=input_id,
            reason="insufficient_target_free_signal_coverage",
            bars_by_symbol=bars_by_symbol,
            structural_slot_count=structural_slot_count,
            structural_signal_count=signal_count,
            structural_signal_symbol_count=signal_symbol_count,
        )
    return _ready_input(
        phase,
        input_id=input_id,
        bars_by_symbol=bars_by_symbol,
        structural_slot_count=structural_slot_count,
        structural_signal_count=signal_count,
        structural_signal_symbol_count=signal_symbol_count,
    )


def freeze_kis_nas_d1_volume_exhaustion_reversal_campaign(
    input: KisNasD1VolumeExhaustionReversalInput,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision: str,
    attempt_id: str = KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEFAULT_ATTEMPT_ID,
) -> KisNasD1VolumeExhaustionReversalContract:
    """Persist one frozen contract before any next-session target is evaluated."""

    if not code_revision.strip():
        raise ValueError("code revision is required")
    _require_attempt_id(attempt_id)
    run_directory = _external_run_directory(artifact_root, repo_root, attempt_id=attempt_id)
    payload = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
            "attempt_id": attempt_id,
            "code_revision": code_revision,
            "source": input.safe_payload()["source"],
            "source_limitations": [
                "MODP=0_unadjusted",
                "corporate_action_semantics_not_qualified",
                "current_listing_registry_not_point_in_time_universe",
                "source_local_only_no_cross_source_blend",
                "consumed_validation_partition_excluded",
            ],
            "input": {
                "status": input.status,
                "reason": input.reason,
                "input_hash": input.input_hash,
                "structural_slot_count": input.structural_slot_count,
                "structural_signal_count": input.structural_signal_count,
                "structural_signal_symbol_count": input.structural_signal_symbol_count,
                "evaluation_slot_count": input.evaluation_slot_count,
            },
            "geometry": {
                "development_source_sessions": [0, 1509],
                "target_free_structural_source_sessions": [0, 999],
                "purge_source_sessions": [1000, 1021],
                "falsification_decision_source_sessions": [1042, 1508],
                "target_source_session_offset": 1,
                "target": "next_d1_open_to_close_return",
                "lookback_completed_sessions": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK,
                "consumed_validation_partition_access": "forbidden",
            },
            "rule": {
                "range_to_open_vs_prior_median_multiplier": _decimal_text(
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_RANGE_MULTIPLIER
                ),
                "close_location_max": _decimal_text(
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_CLOSE_LOCATION_MAX
                ),
                "signed_body": "negative",
                "volume_vs_prior_median_multiplier": _decimal_text(
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_VOLUME_MULTIPLIER
                ),
                "causal_close_to_close_discontinuity_abs_max": _decimal_text(
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DISCONTINUITY_LIMIT
                ),
                "long_only": True,
            },
            "comparators": ["flat", "candle_only_without_volume_condition"],
            "cost_model": {
                "round_trip_cost_bps_band": [
                    _decimal_text(cost)
                    for cost in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_COST_BPS
                ],
                "primary_round_trip_cost_bps": _decimal_text(
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PRIMARY_COST_BPS
                ),
            },
            "null": {
                "count": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT,
                "permutation": "within_symbol_contiguous_target_return_blocks",
                "block_size": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE,
                "trailing_partial_block": "fixed_in_place",
                "percentile": "p95_higher",
            },
            "kill_test": {
                "minimum_target_free_signal_count": (
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SIGNAL_COUNT
                ),
                "minimum_target_free_signal_symbol_count": (
                    KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_MIN_SYMBOL_COUNT
                ),
                "primary_cost_net_mean_must_be_positive": True,
                "candidate_must_strictly_exceed_candle_only_at_every_cost": True,
                "candidate_must_strictly_exceed_null_p95_at_primary_cost": True,
            },
            "scope": _non_promoting_scope(),
            "artifact_policy": {
                "repository_storage_allowed": False,
                "raw_rows_persisted": False,
                "dates_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "predictions_persisted": False,
                "checkpoint_written": False,
            },
        },
        field_name="campaign_contract_sha256",
    )
    payload = _write_or_reattach_contract(run_directory / "campaign-contract.json", payload)
    contract_sha256 = _verify_signed_payload(payload, field_name="campaign_contract_sha256")
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=input.dataset_hash,
        split_hash=_sha256_json(cast(dict[str, object], payload["geometry"])),
        cost_model_hash=_sha256_json({"cost_model": payload["cost_model"]}),
        trial_family=KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
        holdout_access="none",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return KisNasD1VolumeExhaustionReversalContract(
        input=input,
        artifact_root=Path(artifact_root).resolve(),
        repo_root=Path(repo_root).resolve(),
        attempt_id=attempt_id,
        run_directory=run_directory,
        contract_path=run_directory / "campaign-contract.json",
        contract_sha256=contract_sha256,
        registry_entry=registry_entry,
    )


def run_kis_nas_d1_volume_exhaustion_reversal(
    contract: KisNasD1VolumeExhaustionReversalContract,
) -> KisNasD1VolumeExhaustionReversalRun:
    """Run or reattach one fixed source-local CPU falsification."""

    existing = _load_existing_run(contract)
    if existing is not None:
        return _with_outcome(contract, existing)
    metrics: KisNasD1VolumeExhaustionReversalMetrics | None = None
    if contract.input.status != "ready":
        status: VolumeExhaustionResultStatus = "input_unavailable"
        reason = contract.input.reason
    else:
        try:
            metrics = _evaluate(contract.input)
        except ValueError as error:
            status = "input_unavailable"
            reason = _safe_input_reason(error)
        else:
            status = "falsified" if metrics.is_falsified else "inconclusive_non_promoting"
            reason = "frozen_kill_test_failed" if status == "falsified" else None
    summary = _signed_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
            "campaign_contract_sha256": contract.contract_sha256,
            "phase": "cpu_only_development_falsification",
            "status": status,
            "reason": reason,
            "input": {
                "input_hash": contract.input.input_hash,
                "status": contract.input.status,
                "structural_signal_count": contract.input.structural_signal_count,
                "structural_signal_symbol_count": contract.input.structural_signal_symbol_count,
            },
            "metrics": None if metrics is None else metrics.safe_payload(),
            "scope": _non_promoting_scope(),
        },
        field_name="summary_sha256",
    )
    summary_path = contract.run_directory / "cpu-summary.json"
    _write_or_verify_json(summary_path, summary)
    return _with_outcome(contract, _run_from_summary(contract, summary_path))


def _ready_input(
    phase: Any,
    *,
    input_id: str,
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
    structural_slot_count: int,
    structural_signal_count: int,
    structural_signal_symbol_count: int,
) -> KisNasD1VolumeExhaustionReversalInput:
    return KisNasD1VolumeExhaustionReversalInput(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        status="ready",
        reason=None,
        structural_slot_count=structural_slot_count,
        structural_signal_count=structural_signal_count,
        structural_signal_symbol_count=structural_signal_symbol_count,
        evaluation_slot_count=_evaluation_slot_count(),
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=str(phase.parent_dataset_id),
            dataset_hash=str(phase.parent_dataset_hash),
            index_hash=str(phase.index_hash),
            status="ready",
            reason=None,
            structural_slot_count=structural_slot_count,
            structural_signal_count=structural_signal_count,
            structural_signal_symbol_count=structural_signal_symbol_count,
            evaluation_slot_count=_evaluation_slot_count(),
        ),
        _bars_by_symbol=bars_by_symbol,
    )


def _unavailable_input(
    phase: Any,
    *,
    input_id: str,
    reason: str,
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
    structural_slot_count: int,
    structural_signal_count: int,
    structural_signal_symbol_count: int,
) -> KisNasD1VolumeExhaustionReversalInput:
    return KisNasD1VolumeExhaustionReversalInput(
        input_id=input_id,
        dataset_id=str(phase.parent_dataset_id),
        dataset_hash=str(phase.parent_dataset_hash),
        index_hash=str(phase.index_hash),
        status="input_unavailable",
        reason=reason,
        structural_slot_count=structural_slot_count,
        structural_signal_count=structural_signal_count,
        structural_signal_symbol_count=structural_signal_symbol_count,
        evaluation_slot_count=_evaluation_slot_count(),
        input_hash=_input_hash(
            input_id=input_id,
            dataset_id=str(phase.parent_dataset_id),
            dataset_hash=str(phase.parent_dataset_hash),
            index_hash=str(phase.index_hash),
            status="input_unavailable",
            reason=reason,
            structural_slot_count=structural_slot_count,
            structural_signal_count=structural_signal_count,
            structural_signal_symbol_count=structural_signal_symbol_count,
            evaluation_slot_count=_evaluation_slot_count(),
        ),
        _bars_by_symbol=bars_by_symbol,
    )


def _structural_census(
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
) -> tuple[int, int, int]:
    slots = 0
    signal_count = 0
    signal_symbol_count = 0
    for symbol in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS:
        symbol_signal_count = 0
        bars = bars_by_symbol[symbol]
        for decision_index in range(
            KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK,
            KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_STRUCTURAL_SESSIONS,
        ):
            slots += 1
            if _signal_flags(bars, decision_index=decision_index).candidate:
                signal_count += 1
                symbol_signal_count += 1
        if symbol_signal_count:
            signal_symbol_count += 1
    return slots, signal_count, signal_symbol_count


def _evaluate(
    input: KisNasD1VolumeExhaustionReversalInput,
) -> KisNasD1VolumeExhaustionReversalMetrics:
    candidate_targets_by_symbol: dict[str, tuple[float, ...]] = {}
    candidate_masks_by_symbol: dict[str, tuple[bool, ...]] = {}
    candle_only_masks_by_symbol: dict[str, tuple[bool, ...]] = {}
    candidate_trade_count = 0
    candidate_symbol_count = 0
    candle_only_trade_count = 0
    for symbol in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS:
        bars = input._bars_by_symbol[symbol]
        targets: list[float] = []
        candidate_mask: list[bool] = []
        candle_only_mask: list[bool] = []
        for decision_index in range(
            KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START,
            KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_STOP + 1,
        ):
            flags = _signal_flags(bars, decision_index=decision_index)
            targets.append(_target_return_bps(bars[decision_index + 1]))
            candidate_mask.append(flags.candidate)
            candle_only_mask.append(flags.candle_only)
        candidate_count = sum(candidate_mask)
        candidate_trade_count += candidate_count
        candidate_symbol_count += int(candidate_count > 0)
        candle_only_trade_count += sum(candle_only_mask)
        candidate_targets_by_symbol[symbol] = tuple(targets)
        candidate_masks_by_symbol[symbol] = tuple(candidate_mask)
        candle_only_masks_by_symbol[symbol] = tuple(candle_only_mask)
    if candidate_trade_count == 0:
        raise ValueError("no_evaluation_candidate_signals")

    candidate_net_by_cost: list[tuple[str, float]] = []
    candle_only_net_by_cost: list[tuple[str, float]] = []
    for cost in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_COST_BPS:
        candidate_net_by_cost.append(
            (
                _decimal_text(cost),
                _mean_net_bps(candidate_targets_by_symbol, candidate_masks_by_symbol, cost=cost),
            )
        )
        candle_only_net_by_cost.append(
            (
                _decimal_text(cost),
                _mean_net_bps(candidate_targets_by_symbol, candle_only_masks_by_symbol, cost=cost),
            )
        )
    null_values = [
        _mean_net_bps(
            {
                symbol: _block_permute_target_returns(
                    targets,
                    seed=(
                        KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_SEED_BASE
                        + offset
                        + symbol_index * 10_000
                    ),
                )
                for symbol_index, (symbol, targets) in enumerate(
                    candidate_targets_by_symbol.items()
                )
            },
            candidate_masks_by_symbol,
            cost=KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_PRIMARY_COST_BPS,
        )
        for offset in range(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT)
    ]
    return KisNasD1VolumeExhaustionReversalMetrics(
        candidate_trade_count=candidate_trade_count,
        candidate_symbol_count=candidate_symbol_count,
        candle_only_trade_count=candle_only_trade_count,
        evaluation_slot_count=input.evaluation_slot_count,
        candidate_net_mean_bps_by_cost=tuple(candidate_net_by_cost),
        candle_only_net_mean_bps_by_cost=tuple(candle_only_net_by_cost),
        null_p95_net_mean_bps_primary_cost=_percentile_higher(null_values, percentile=0.95),
        null_count=KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT,
    )


def _signal_flags(bars: Sequence[Bar], *, decision_index: int) -> _SignalFlags:
    """Evaluate only the causal completed `t-20..t` chain for one rule."""

    if (
        isinstance(decision_index, bool)
        or not isinstance(decision_index, int)
        or decision_index < KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK
        or decision_index >= len(bars)
    ):
        return _SignalFlags(candidate=False, candle_only=False)
    chain = tuple(
        bars[
            decision_index - KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK : decision_index
            + 1
        ]
    )
    if len(chain) != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK + 1:
        return _SignalFlags(candidate=False, candle_only=False)
    try:
        _validate_causal_chain(chain)
    except ValueError:
        return _SignalFlags(candidate=False, candle_only=False)
    current = chain[-1]
    candle_range = current.high - current.low
    if candle_range <= 0:
        return _SignalFlags(candidate=False, candle_only=False)
    prior_ranges = tuple((bar.high - bar.low) / bar.open for bar in chain[:-1])
    prior_volumes = tuple(bar.volume for bar in chain[:-1])
    prior_volume_median = median(prior_volumes)
    if (
        any(value <= 0 for value in prior_ranges)
        or prior_volume_median <= 0
        or _has_discontinuity(chain)
    ):
        return _SignalFlags(candidate=False, candle_only=False)
    range_to_open = candle_range / current.open
    close_location = (current.close - current.low) / candle_range
    candle_only = (
        range_to_open
        >= KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_RANGE_MULTIPLIER * median(prior_ranges)
        and close_location <= KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_CLOSE_LOCATION_MAX
        and current.close < current.open
    )
    if not candle_only:
        return _SignalFlags(candidate=False, candle_only=False)
    candidate = (
        current.volume
        >= KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_VOLUME_MULTIPLIER * prior_volume_median
    )
    return _SignalFlags(candidate=candidate, candle_only=True)


def _target_return_bps(bar: Bar) -> float:
    value = float((bar.close / bar.open - Decimal("1")) * Decimal("10000"))
    if not math.isfinite(value):
        raise ValueError("cpu_evaluation_unavailable")
    return value


def _mean_net_bps(
    targets_by_symbol: Mapping[str, tuple[float, ...]],
    masks_by_symbol: Mapping[str, tuple[bool, ...]],
    *,
    cost: Decimal,
) -> float:
    selected: list[float] = []
    for symbol in KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS:
        targets = targets_by_symbol[symbol]
        mask = masks_by_symbol[symbol]
        if len(targets) != len(mask):
            raise ValueError("cpu_evaluation_unavailable")
        selected.extend(value for value, included in zip(targets, mask, strict=True) if included)
    if not selected:
        raise ValueError("no_evaluation_candidate_signals")
    value = sum(selected) / len(selected) - float(cost)
    if not math.isfinite(value):
        raise ValueError("cpu_evaluation_unavailable")
    return value


def _block_permute_target_returns(values: tuple[float, ...], *, seed: int) -> tuple[float, ...]:
    """Permute whole target-return blocks only inside one symbol's timeline."""

    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("cpu_evaluation_unavailable")
    full_block_stop = (
        len(values)
        // KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE
        * KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE
    )
    blocks = [
        values[index : index + KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE]
        for index in range(
            0,
            full_block_stop,
            KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_BLOCK_SIZE,
        )
    ]
    order = list(range(len(blocks)))
    random.Random(seed).shuffle(order)
    return (
        tuple(value for block_index in order for value in blocks[block_index])
        + values[full_block_stop:]
    )


def _percentile_higher(values: Sequence[float], *, percentile: float) -> float:
    if (
        len(values) != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_NULL_COUNT
        or not 0.0 < percentile < 1.0
        or any(not math.isfinite(value) for value in values)
    ):
        raise ValueError("cpu_evaluation_unavailable")
    ordered = sorted(values)
    return ordered[math.ceil((len(ordered) - 1) * percentile)]


def _has_discontinuity(chain: Sequence[Bar]) -> bool:
    return any(
        abs(current.close / prior.close - Decimal("1"))
        >= KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DISCONTINUITY_LIMIT
        for prior, current in zip(chain, chain[1:], strict=False)
    )


def _validate_causal_chain(chain: Sequence[Bar]) -> None:
    previous: Bar | None = None
    for bar in chain:
        if (
            not isinstance(bar, Bar)
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.open <= 0
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
        ):
            raise ValueError("source_stream_mismatch")
        if previous is not None and (
            bar.start_ts <= previous.start_ts or bar.end_ts <= previous.end_ts
        ):
            raise ValueError("source_stream_mismatch")
        previous = bar


def _verified_symbol_bars(
    bars: tuple[Bar, ...],
    *,
    symbol: str,
    sessions: tuple[object, ...],
) -> tuple[Bar, ...]:
    if (
        len(bars) != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEVELOPMENT_SESSIONS
        or len(sessions) != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEVELOPMENT_SESSIONS
        or tuple(bar.start_ts.date() for bar in bars) != sessions
    ):
        raise ValueError("source_stream_mismatch")
    _validate_causal_chain(bars)
    if any(bar.symbol != symbol for bar in bars):
        raise ValueError("source_stream_mismatch")
    return bars


def _require_development_phase(phase: Any, *, input_id: str) -> None:
    if (
        input_id != "kis.paper.private.daily.nas.sequence.input-v1"
        or getattr(phase, "phase", None) != "development"
        or getattr(phase, "parent_dataset_id", None)
        != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_ID
        or getattr(phase, "parent_dataset_hash", None)
        != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DATASET_HASH
        or not _is_sha256(getattr(phase, "index_hash", None))
        or tuple(getattr(phase, "bars_by_symbol", ()))
        != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS
        or len(getattr(phase, "common_sessions", ()))
        != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_DEVELOPMENT_SESSIONS
    ):
        raise ValueError("KIS NAS D1 volume-exhaustion requires the attested development phase")


def _evaluation_slot_count() -> int:
    return len(KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_SYMBOLS) * (
        KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_STOP
        - KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_EVALUATION_DECISION_START
        + 1
    )


def _external_run_directory(artifact_root: Path, repo_root: Path, *, attempt_id: str) -> Path:
    return ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID,
        attempt_id,
    )


def _write_or_reattach_contract(path: Path, payload: dict[str, object]) -> dict[str, object]:
    if not path.exists():
        _write_or_verify_json(path, payload)
        return payload
    existing = _read_json_object(path)
    _verify_signed_payload(existing, field_name="campaign_contract_sha256")
    if existing == payload:
        return existing
    raise ValueError("volume-exhaustion contract conflicts with existing evidence")


def _write_or_verify_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        if path.is_symlink() or _read_json_object(path) != payload:
            raise ValueError("volume-exhaustion artifact already exists with different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("volume-exhaustion artifact is invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("volume-exhaustion artifact contains invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("volume-exhaustion artifact must be an object")
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
        raise ValueError("volume-exhaustion artifact checksum is invalid")
    return cast(str, recorded)


def _load_existing_run(
    contract: KisNasD1VolumeExhaustionReversalContract,
) -> KisNasD1VolumeExhaustionReversalRun | None:
    summary_path = contract.run_directory / "cpu-summary.json"
    if not summary_path.exists():
        return None
    if not summary_path.is_file() or summary_path.is_symlink():
        raise ValueError("volume-exhaustion summary path is invalid")
    return _run_from_summary(contract, summary_path)


def _run_from_summary(
    contract: KisNasD1VolumeExhaustionReversalContract,
    summary_path: Path,
) -> KisNasD1VolumeExhaustionReversalRun:
    payload = _read_json_object(summary_path)
    summary_sha256 = _verify_signed_payload(payload, field_name="summary_sha256")
    status = payload.get("status")
    reason = payload.get("reason")
    if (
        payload.get("campaign_id") != KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_ID
        or payload.get("campaign_contract_sha256") != contract.contract_sha256
        or payload.get("phase") != "cpu_only_development_falsification"
        or status
        not in {"falsified", "inconclusive_non_promoting", "input_unavailable"}
        or (reason is not None and not isinstance(reason, str))
        or not isinstance(payload.get("input"), dict)
        or payload["input"].get("input_hash") != contract.input.input_hash
        or payload.get("scope") != _non_promoting_scope()
    ):
        raise ValueError("volume-exhaustion summary is malformed")
    return KisNasD1VolumeExhaustionReversalRun(
        status=cast(VolumeExhaustionResultStatus, status),
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
    contract: KisNasD1VolumeExhaustionReversalContract,
    run: KisNasD1VolumeExhaustionReversalRun,
) -> KisNasD1VolumeExhaustionReversalRun:
    outcome = register_campaign_outcome(
        contract_hash=contract.contract_sha256,
        outcome_class=(
            "non_promoting_completed"
            if run.status in {"falsified", "inconclusive_non_promoting"}
            else "non_promoting_failed"
        ),
        outcome_reference_sha256=run.summary_sha256,
        artifact_root=contract.artifact_root,
        repo_root=contract.repo_root,
    )
    return KisNasD1VolumeExhaustionReversalRun(
        status=run.status,
        reason=run.reason,
        summary_path=run.summary_path,
        summary_sha256=run.summary_sha256,
        registry_outcome=outcome,
    )


def _input_hash(
    *,
    input_id: str,
    dataset_id: str,
    dataset_hash: str,
    index_hash: str,
    status: VolumeExhaustionInputStatus,
    reason: str | None,
    structural_slot_count: int,
    structural_signal_count: int,
    structural_signal_symbol_count: int,
    evaluation_slot_count: int,
) -> str:
    return _sha256_json(
        {
            "input_id": input_id,
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "index_hash": index_hash,
            "status": status,
            "reason": reason,
            "structural_slot_count": structural_slot_count,
            "structural_signal_count": structural_signal_count,
            "structural_signal_symbol_count": structural_signal_symbol_count,
            "evaluation_slot_count": evaluation_slot_count,
            "lookback": KIS_NAS_D1_VOLUME_EXHAUSTION_REVERSAL_LOOKBACK,
        }
    )


def _non_promoting_scope() -> dict[str, bool]:
    return {
        "source_local_only": True,
        "point_in_time_claim_allowed": False,
        "corporate_action_claim_allowed": False,
        "survivorship_claim_allowed": False,
        "architecture_selection_allowed": False,
        "model_selection_allowed": False,
        "ensemble_allowed": False,
        "profitability_or_pnl_claim": False,
        "paper_input_allowed": False,
        "broker_access": False,
        "live_behavior": False,
        "gpu_used": False,
    }


def _safe_input_reason(error: ValueError) -> str:
    reason = str(error)
    if reason in _UNAVAILABLE_REASONS:
        return reason
    return "cpu_evaluation_unavailable"


def _require_attempt_id(attempt_id: str) -> None:
    if not _SAFE_ATTEMPT_ID.fullmatch(attempt_id):
        raise ValueError("attempt id is invalid")


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _sha256_json(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )

"""CPU-only falsification of a fixed Tiingo D1 compression-continuation rule.

The module holds source rows and numeric returns only in memory. Its external
evidence records frozen identities, counts, categorical relations, and hashes.
It has no provider, credential, execution, Paper, GPU, or model-training path.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import median
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
)

from .artifact_paths import ensure_external_artifact_directory
from .campaign_registry import (
    CampaignOutcomeRegistryEntry,
    FrozenCampaignRegistryEntry,
    register_campaign_outcome,
    register_frozen_campaign,
)

TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID = (
    "tiingo-d1-trio-intraday-compression-continuation-falsification-v1"
)
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK = 20
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEVELOPMENT_NUMERATOR = 7
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEVELOPMENT_DENOMINATOR = 10
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PURGE_SESSIONS = 61
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_RANGE_MULTIPLIER = Decimal("0.75")
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_CLOSE_LOCATION_MIN = Decimal("0.75")
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DISCONTINUITY_LIMIT = Decimal(
    "0.20"
)
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_DEVELOPMENT_SIGNALS = 100
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_VALIDATION_ACTIVE_DAYS = 60
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_COST_BPS = (
    Decimal("10"),
    Decimal("15"),
    Decimal("20"),
)
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PRIMARY_COST_BPS = Decimal("20")
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT = 64
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_BLOCK_SIZE = 10
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_SEED_BASE = 60_260_802
TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEFAULT_ATTEMPT_ID = (
    "cpu-falsification-r1"
)

CompressionInputStatus = Literal["ready", "input_unavailable"]
CompressionResultStatus = Literal[
    "input_unavailable",
    "falsified",
    "inconclusive_non_promoting",
]

_SAFE_ATTEMPT_ID = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_INPUT_UNAVAILABLE_REASONS = frozenset(
    {
        "insufficient_common_sessions",
        "insufficient_target_free_development_signals",
        "insufficient_validation_active_days",
        "invalid_validation_target",
    }
)


@dataclass(frozen=True, slots=True)
class TiingoD1TrioIntradayCompressionInput:
    """Causal source shape and target-free decisions for one frozen campaign."""

    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    status: CompressionInputStatus
    reason: str | None
    common_session_count: int
    development_session_count: int
    purge_session_count: int
    validation_session_count: int
    development_signal_count: int
    development_signal_symbol_count: int
    validation_active_day_count: int
    validation_active_position_count: int
    input_hash: str
    _rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]]
    _validation_decisions: tuple[_CompressionDecision, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        rows = {symbol: tuple(value) for symbol, value in self._rows_by_symbol.items()}
        decisions = tuple(self._validation_decisions)
        expected_validation = self.common_session_count - (
            self.development_session_count + self.purge_session_count
        )
        if (
            set(rows) != set(TIINGO_ETF_D1_SYMBOLS)
            or not _is_sha256(self.dataset_hash)
            or not _is_sha256(self.manifest_hash)
            or self.status not in {"ready", "input_unavailable"}
            or min(
                self.common_session_count,
                self.development_session_count,
                self.purge_session_count,
                self.validation_session_count,
                self.development_signal_count,
                self.development_signal_symbol_count,
                self.validation_active_day_count,
                self.validation_active_position_count,
            )
            < 0
            or self.purge_session_count
            != TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PURGE_SESSIONS
            or self.validation_session_count != expected_validation
            or self.development_signal_symbol_count > len(TIINGO_ETF_D1_SYMBOLS)
            or self.validation_active_position_count < self.validation_active_day_count
            or not _is_sha256(self.input_hash)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("Tiingo D1 compression input identity is invalid")
        if any(len(value) != self.common_session_count for value in rows.values()):
            raise ValueError("Tiingo D1 compression rows are not aligned")
        if self.status == "ready":
            if (
                self.reason is not None
                or self.development_signal_count
                < TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_DEVELOPMENT_SIGNALS
                or self.development_signal_symbol_count != len(TIINGO_ETF_D1_SYMBOLS)
                or self.validation_active_day_count
                < TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_VALIDATION_ACTIVE_DAYS
                or len(decisions) != self.validation_active_day_count
                or sum(len(decision.symbols) for decision in decisions)
                != self.validation_active_position_count
            ):
                raise ValueError("ready Tiingo D1 compression input is invalid")
        elif self.reason not in _INPUT_UNAVAILABLE_REASONS or decisions:
            raise ValueError("unavailable Tiingo D1 compression input is invalid")
        expected_hash = _input_hash(
            dataset_id=self.dataset_id,
            dataset_hash=self.dataset_hash,
            manifest_hash=self.manifest_hash,
            status=self.status,
            reason=self.reason,
            common_session_count=self.common_session_count,
            development_session_count=self.development_session_count,
            purge_session_count=self.purge_session_count,
            validation_session_count=self.validation_session_count,
            development_signal_count=self.development_signal_count,
            development_signal_symbol_count=self.development_signal_symbol_count,
            validation_active_day_count=self.validation_active_day_count,
            validation_active_position_count=self.validation_active_position_count,
        )
        if self.input_hash != expected_hash:
            raise ValueError("Tiingo D1 compression input hash is invalid")
        object.__setattr__(self, "_rows_by_symbol", MappingProxyType(rows))
        object.__setattr__(self, "_validation_decisions", decisions)

    def safe_payload(self) -> dict[str, object]:
        """Return source-safe target-free evidence only."""

        return {
            "schema_version": self.schema_version,
            "campaign_id": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
            "source": {
                "provider": "Tiingo standard EOD API",
                "dataset_id": self.dataset_id,
                "dataset_hash": self.dataset_hash,
                "manifest_hash": self.manifest_hash,
                "symbols": list(TIINGO_ETF_D1_SYMBOLS),
                "source_reuse_grade": "repeat_source_non_promoting_falsification",
                "independent_holdout_claim_allowed": False,
                "paper_input_eligible": False,
            },
            "status": self.status,
            "reason": self.reason,
            "common_session_count": self.common_session_count,
            "split": {
                "development_session_count": self.development_session_count,
                "purge_session_count": self.purge_session_count,
                "validation_session_count": self.validation_session_count,
            },
            "target_free": {
                "development_signal_count": self.development_signal_count,
                "development_signal_symbol_count": self.development_signal_symbol_count,
                "validation_active_day_count": self.validation_active_day_count,
                "validation_active_position_count": self.validation_active_position_count,
            },
            "input_hash": self.input_hash,
            "raw_market_data_written": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "predictions_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrioIntradayCompressionMetrics:
    """Private numeric metrics with a redacted categorical projection."""

    active_day_count: int
    active_position_count: int
    active_symbol_count: int
    candidate_net_mean_bps_by_cost: tuple[tuple[str, Decimal], ...]
    equal_exposure_net_mean_bps_by_cost: tuple[tuple[str, Decimal], ...]
    null_p95_net_mean_bps_primary_cost: Decimal
    null_count: int

    def __post_init__(self) -> None:
        expected_costs = tuple(
            _decimal_text(cost)
            for cost in TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_COST_BPS
        )
        candidate = dict(self.candidate_net_mean_bps_by_cost)
        equal_exposure = dict(self.equal_exposure_net_mean_bps_by_cost)
        if (
            self.active_day_count
            < TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_VALIDATION_ACTIVE_DAYS
            or self.active_position_count < self.active_day_count
            or not 0 < self.active_symbol_count <= len(TIINGO_ETF_D1_SYMBOLS)
            or tuple(candidate) != expected_costs
            or tuple(equal_exposure) != expected_costs
            or self.null_count
            != TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT
            or not self.null_p95_net_mean_bps_primary_cost.is_finite()
            or any(not value.is_finite() for value in candidate.values())
            or any(not value.is_finite() for value in equal_exposure.values())
        ):
            raise ValueError("Tiingo D1 compression metrics are invalid")

    @property
    def primary_net_mean_bps(self) -> Decimal:
        return dict(self.candidate_net_mean_bps_by_cost)[
            _decimal_text(TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PRIMARY_COST_BPS)
        ]

    @property
    def candidate_exceeds_equal_exposure_at_all_costs(self) -> bool:
        candidate = dict(self.candidate_net_mean_bps_by_cost)
        equal_exposure = dict(self.equal_exposure_net_mean_bps_by_cost)
        return all(candidate[cost] > equal_exposure[cost] for cost in candidate)

    @property
    def candidate_exceeds_null_p95(self) -> bool:
        return self.primary_net_mean_bps > self.null_p95_net_mean_bps_primary_cost

    @property
    def is_falsified(self) -> bool:
        return (
            self.primary_net_mean_bps <= 0
            or not self.candidate_exceeds_equal_exposure_at_all_costs
            or not self.candidate_exceeds_null_p95
        )

    def safe_payload(self) -> dict[str, object]:
        candidate = dict(self.candidate_net_mean_bps_by_cost)
        equal_exposure = dict(self.equal_exposure_net_mean_bps_by_cost)
        return {
            "active_day_count": self.active_day_count,
            "active_position_count": self.active_position_count,
            "active_symbol_count": self.active_symbol_count,
            "candidate_vs_equal_exposure_by_round_trip_cost": {
                cost: _strict_relation(candidate[cost], equal_exposure[cost])
                for cost in candidate
            },
            "candidate_vs_null_p95_primary_cost": _strict_relation(
                self.primary_net_mean_bps,
                self.null_p95_net_mean_bps_primary_cost,
            ),
            "primary_net_mean_relation_to_flat": _positive_relation(
                self.primary_net_mean_bps
            ),
            "primary_round_trip_cost_bps": _decimal_text(
                TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PRIMARY_COST_BPS
            ),
            "null_count": self.null_count,
            "null_geometry": {
                "block_size": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_BLOCK_SIZE,
                "permutation": "joint_cross_sectional_validation_target_return_blocks",
                "trailing_partial_block": "fixed_in_place",
            },
            "numeric_metrics_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class TiingoD1TrioIntradayCompressionCampaign:
    """Immutable external precommit and its in-memory input."""

    campaign_input: TiingoD1TrioIntradayCompressionInput
    attempt_id: str
    code_revision: str
    artifact_root: Path
    repo_root: Path
    run_directory: Path
    contract_path: Path
    contract_sha256: str
    registry_entry: FrozenCampaignRegistryEntry

    def __post_init__(self) -> None:
        if (
            _SAFE_ATTEMPT_ID.fullmatch(self.attempt_id) is None
            or not _is_sha256(self.code_revision)
            or not _is_sha256(self.contract_sha256)
            or self.run_directory.parent.parent.parent != self.artifact_root
            or self.contract_path.parent != self.run_directory
            or self.contract_path.name != "campaign-contract.json"
        ):
            raise ValueError("Tiingo D1 compression campaign is invalid")


@dataclass(frozen=True, slots=True)
class TiingoD1TrioIntradayCompressionResult:
    """One terminal source-local outcome with external summary custody."""

    campaign: TiingoD1TrioIntradayCompressionCampaign
    status: CompressionResultStatus
    reason: str
    metrics: TiingoD1TrioIntradayCompressionMetrics | None
    summary_path: Path
    summary_sha256: str
    registry_outcome: CampaignOutcomeRegistryEntry
    _reused_summary_payload: Mapping[str, object] | None = field(
        default=None,
        repr=False,
    )

    def __post_init__(self) -> None:
        if (
            self.status not in {"input_unavailable", "falsified", "inconclusive_non_promoting"}
            or not _is_sha256(self.summary_sha256)
            or self.summary_path.parent != self.campaign.run_directory
            or self.summary_path.name != "cpu-summary.json"
        ):
            raise ValueError("Tiingo D1 compression result is invalid")
        if self.status == "input_unavailable":
            if self.metrics is not None or self.reason not in _INPUT_UNAVAILABLE_REASONS:
                raise ValueError("Tiingo D1 compression unavailable result is invalid")
        elif (
            self.metrics is None
            and self._reused_summary_payload is None
            or self.reason != "frozen_kill_test_failed"
            and self.status == "falsified"
            or self.reason != "frozen_kill_test_survived_non_promoting"
            and self.status == "inconclusive_non_promoting"
        ):
            raise ValueError("Tiingo D1 compression evaluated result is invalid")
        if self._reused_summary_payload is not None:
            object.__setattr__(
                self,
                "_reused_summary_payload",
                MappingProxyType(dict(self._reused_summary_payload)),
            )

    def safe_payload(self) -> dict[str, object]:
        if self._reused_summary_payload is not None:
            return dict(self._reused_summary_payload)
        return {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
            "campaign_contract_sha256": self.campaign.contract_sha256,
            "phase": "cpu_only_repeat_source_falsification",
            "status": self.status,
            "reason": self.reason,
            "input": self.campaign.campaign_input.safe_payload(),
            "metrics": None if self.metrics is None else self.metrics.safe_payload(),
            "scope": _scope_payload(),
            "summary_sha256": self.summary_sha256,
        }


@dataclass(frozen=True, slots=True)
class _CompressionDecision:
    index: int
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.index < 0 or not self.symbols or any(
            symbol not in TIINGO_ETF_D1_SYMBOLS for symbol in self.symbols
        ):
            raise ValueError("Tiingo D1 compression decision is invalid")


def build_tiingo_d1_trio_intraday_compression_input(
    snapshot: LoadedTiingoEtfDailySnapshot,
) -> TiingoD1TrioIntradayCompressionInput:
    """Build only causal signals and abstentions before reading any target."""

    rows_by_symbol = _aligned_rows(snapshot)
    common_session_count = len(next(iter(rows_by_symbol.values())))
    development_stop = (
        common_session_count
        * TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEVELOPMENT_NUMERATOR
        // TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEVELOPMENT_DENOMINATOR
    )
    validation_start = (
        development_stop
        + TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PURGE_SESSIONS
    )
    if validation_start + 1 >= common_session_count:
        return _unavailable_input(
            snapshot=snapshot,
            rows_by_symbol=rows_by_symbol,
            common_session_count=common_session_count,
            development_stop=development_stop,
            validation_start=validation_start,
            reason="insufficient_common_sessions",
        )
    _assert_dependency_separation(
        development_stop=development_stop,
        validation_start=validation_start,
    )
    development_signal_count = 0
    development_symbols: set[str] = set()
    for index in range(
        TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK,
        development_stop,
    ):
        for symbol in TIINGO_ETF_D1_SYMBOLS:
            if _symbol_qualifies(rows_by_symbol[symbol], index):
                development_signal_count += 1
                development_symbols.add(symbol)
    if (
        development_signal_count
        < TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_DEVELOPMENT_SIGNALS
        or len(development_symbols) != len(TIINGO_ETF_D1_SYMBOLS)
    ):
        return _unavailable_input(
            snapshot=snapshot,
            rows_by_symbol=rows_by_symbol,
            common_session_count=common_session_count,
            development_stop=development_stop,
            validation_start=validation_start,
            reason="insufficient_target_free_development_signals",
            development_signal_count=development_signal_count,
            development_signal_symbol_count=len(development_symbols),
        )
    decisions = tuple(
        _CompressionDecision(
            index=index,
            symbols=tuple(
                symbol
                for symbol in TIINGO_ETF_D1_SYMBOLS
                if _symbol_qualifies(rows_by_symbol[symbol], index)
            ),
        )
        for index in range(validation_start, common_session_count - 1)
        if any(
            _symbol_qualifies(rows_by_symbol[symbol], index)
            for symbol in TIINGO_ETF_D1_SYMBOLS
        )
    )
    active_position_count = sum(len(decision.symbols) for decision in decisions)
    if (
        len(decisions)
        < TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_MIN_VALIDATION_ACTIVE_DAYS
    ):
        return _unavailable_input(
            snapshot=snapshot,
            rows_by_symbol=rows_by_symbol,
            common_session_count=common_session_count,
            development_stop=development_stop,
            validation_start=validation_start,
            reason="insufficient_validation_active_days",
            development_signal_count=development_signal_count,
            development_signal_symbol_count=len(development_symbols),
            validation_active_day_count=len(decisions),
            validation_active_position_count=active_position_count,
        )
    return _input(
        snapshot=snapshot,
        rows_by_symbol=rows_by_symbol,
        status="ready",
        reason=None,
        common_session_count=common_session_count,
        development_stop=development_stop,
        validation_start=validation_start,
        development_signal_count=development_signal_count,
        development_signal_symbol_count=len(development_symbols),
        validation_active_day_count=len(decisions),
        validation_active_position_count=active_position_count,
        decisions=decisions,
    )


def freeze_tiingo_d1_trio_intraday_compression_campaign(
    campaign_input: TiingoD1TrioIntradayCompressionInput,
    *,
    artifact_root: Path,
    repo_root: Path,
    code_revision: str,
    attempt_id: str = TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DEFAULT_ATTEMPT_ID,
) -> TiingoD1TrioIntradayCompressionCampaign:
    """Write or reattach the exact external contract before target evaluation."""

    if not isinstance(campaign_input, TiingoD1TrioIntradayCompressionInput):
        raise TypeError("Tiingo D1 compression campaign requires its exact input")
    if _SAFE_ATTEMPT_ID.fullmatch(attempt_id) is None or not _is_sha256(code_revision):
        raise ValueError("Tiingo D1 compression campaign identity is invalid")
    run_directory = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
        attempt_id,
    )
    contract_payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
        "attempt_id": attempt_id,
        "code_revision": code_revision,
        "input": campaign_input.safe_payload(),
        "geometry": {
            "decision_time": "completed_d1_t_close",
            "lookback_completed_sessions": (
                TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK
            ),
            "development": "first_70_percent_common_sessions_target_free",
            "purge_sessions": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PURGE_SESSIONS,
            "validation": "remainder_after_purge",
            "target": "next_d1_open_to_close_return",
            "target_day_filtering": "forbidden",
        },
        "rule": {
            "range_to_open_vs_prior_median_multiplier": _decimal_text(
                TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_RANGE_MULTIPLIER
            ),
            "close_location_min": _decimal_text(
                TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_CLOSE_LOCATION_MIN
            ),
            "signed_body": "positive",
            "causal_chain": "t_minus_20_through_t_no_event_or_20pct_close_discontinuity",
            "candidate_portfolio": "equal_weight_all_qualifying_etfs_or_flat",
        },
        "comparators": ["flat", "equal_weight_spy_qqq_iwm_on_candidate_active_dates"],
        "cost_model": {
            "round_trip_cost_bps_band": [
                _decimal_text(cost)
                for cost in TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_COST_BPS
            ],
            "primary_round_trip_cost_bps": _decimal_text(
                TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PRIMARY_COST_BPS
            ),
        },
        "null": {
            "count": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT,
            "block_size": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_BLOCK_SIZE,
            "permutation": "joint_cross_sectional_validation_target_return_blocks",
            "trailing_partial_block": "fixed_in_place",
        },
        "kill_test": {
            "primary_cost_net_mean_must_be_positive": True,
            "candidate_must_strictly_exceed_equal_exposure_at_every_cost": True,
            "candidate_must_strictly_exceed_null_p95_at_primary_cost": True,
        },
        "scope": _scope_payload(),
    }
    contract_path = run_directory / "campaign-contract.json"
    contract_sha256 = _write_or_reattach_json(contract_path, contract_payload)
    registry_entry = register_frozen_campaign(
        contract_hash=contract_sha256,
        dataset_hash=campaign_input.dataset_hash,
        split_hash=_sha256_json(contract_payload["geometry"]),
        cost_model_hash=_sha256_json(contract_payload["cost_model"]),
        trial_family="tiingo-d1-compression-continuation",
        holdout_access=("opened" if campaign_input.status == "ready" else "none"),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return TiingoD1TrioIntradayCompressionCampaign(
        campaign_input=campaign_input,
        attempt_id=attempt_id,
        code_revision=code_revision,
        artifact_root=Path(artifact_root).resolve(strict=True),
        repo_root=Path(repo_root).resolve(strict=True),
        run_directory=run_directory,
        contract_path=contract_path,
        contract_sha256=contract_sha256,
        registry_entry=registry_entry,
    )


def run_tiingo_d1_trio_intraday_compression_campaign(
    campaign: TiingoD1TrioIntradayCompressionCampaign,
) -> TiingoD1TrioIntradayCompressionResult:
    """Evaluate exactly the precommitted input, then retain a redacted outcome."""

    if not isinstance(campaign, TiingoD1TrioIntradayCompressionCampaign):
        raise TypeError("Tiingo D1 compression run requires its exact campaign")
    reattached = _reattach_existing_result(campaign)
    if reattached is not None:
        return reattached
    campaign_input = campaign.campaign_input
    if campaign_input.status == "input_unavailable":
        status: CompressionResultStatus = "input_unavailable"
        reason = campaign_input.reason or "insufficient_common_sessions"
        metrics = None
        outcome_class: Literal[
            "non_promoting_completed", "non_promoting_failed", "non_promoting_abandoned"
        ] = "non_promoting_abandoned"
    else:
        try:
            metrics = _evaluate(campaign_input)
        except ValueError as exc:
            if str(exc) != "invalid_validation_target":
                raise
            status = "input_unavailable"
            reason = "invalid_validation_target"
            metrics = None
            outcome_class = "non_promoting_abandoned"
        else:
            status = "falsified" if metrics.is_falsified else "inconclusive_non_promoting"
            reason = (
                "frozen_kill_test_failed"
                if status == "falsified"
                else "frozen_kill_test_survived_non_promoting"
            )
            outcome_class = (
                "non_promoting_failed"
                if status == "falsified"
                else "non_promoting_completed"
            )
    payload = _result_payload(
        campaign=campaign,
        status=status,
        reason=reason,
        metrics=metrics,
        summary_sha256=None,
    )
    summary_path = campaign.run_directory / "cpu-summary.json"
    summary_sha256 = _write_or_reattach_json(summary_path, payload)
    registry_outcome = register_campaign_outcome(
        contract_hash=campaign.contract_sha256,
        outcome_class=outcome_class,
        outcome_reference_sha256=summary_sha256,
        artifact_root=campaign.artifact_root,
        repo_root=campaign.repo_root,
    )
    return TiingoD1TrioIntradayCompressionResult(
        campaign=campaign,
        status=status,
        reason=reason,
        metrics=metrics,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
        registry_outcome=registry_outcome,
    )


def _reattach_existing_result(
    campaign: TiingoD1TrioIntradayCompressionCampaign,
) -> TiingoD1TrioIntradayCompressionResult | None:
    summary_path = campaign.run_directory / "cpu-summary.json"
    if not summary_path.exists() and not summary_path.is_symlink():
        return None
    if summary_path.is_symlink() or not summary_path.is_file():
        raise ValueError("Tiingo D1 compression summary artifact is invalid")
    encoded = summary_path.read_bytes()
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo D1 compression summary artifact is invalid") from exc
    if not isinstance(payload, dict) or encoded != _canonical_json(payload):
        raise ValueError("Tiingo D1 compression summary artifact is invalid")
    status, reason, outcome_class = _validate_reused_summary_payload(payload, campaign)
    summary_sha256 = _sha256_bytes(encoded)
    registry_outcome = register_campaign_outcome(
        contract_hash=campaign.contract_sha256,
        outcome_class=outcome_class,
        outcome_reference_sha256=summary_sha256,
        artifact_root=campaign.artifact_root,
        repo_root=campaign.repo_root,
    )
    return TiingoD1TrioIntradayCompressionResult(
        campaign=campaign,
        status=status,
        reason=reason,
        metrics=None,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
        registry_outcome=registry_outcome,
        _reused_summary_payload=payload,
    )


def _validate_reused_summary_payload(
    payload: Mapping[str, object],
    campaign: TiingoD1TrioIntradayCompressionCampaign,
) -> tuple[
    CompressionResultStatus,
    str,
    Literal["non_promoting_completed", "non_promoting_failed", "non_promoting_abandoned"],
]:
    status = payload.get("status")
    reason = payload.get("reason")
    if (
        set(payload)
        != {
            "schema_version",
            "campaign_id",
            "campaign_contract_sha256",
            "phase",
            "status",
            "reason",
            "input",
            "metrics",
            "scope",
        }
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("campaign_id")
        != TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID
        or payload.get("campaign_contract_sha256") != campaign.contract_sha256
        or payload.get("phase") != "cpu_only_repeat_source_falsification"
        or payload.get("input") != campaign.campaign_input.safe_payload()
        or payload.get("scope") != _scope_payload()
        or status
        not in {"input_unavailable", "falsified", "inconclusive_non_promoting"}
        or not isinstance(reason, str)
    ):
        raise ValueError("Tiingo D1 compression summary artifact is invalid")
    metrics = payload.get("metrics")
    if status == "input_unavailable":
        if metrics is not None or reason not in _INPUT_UNAVAILABLE_REASONS:
            raise ValueError("Tiingo D1 compression summary artifact is invalid")
        return status, reason, "non_promoting_abandoned"
    if (
        not isinstance(metrics, dict)
        or set(metrics)
        != {
            "active_day_count",
            "active_position_count",
            "active_symbol_count",
            "candidate_vs_equal_exposure_by_round_trip_cost",
            "candidate_vs_null_p95_primary_cost",
            "null_count",
            "null_geometry",
            "numeric_metrics_persisted",
            "primary_net_mean_relation_to_flat",
            "primary_round_trip_cost_bps",
        }
        or not isinstance(metrics.get("active_day_count"), int)
        or not isinstance(metrics.get("active_position_count"), int)
        or not isinstance(metrics.get("active_symbol_count"), int)
        or metrics["active_day_count"] < 0
        or metrics["active_position_count"] < metrics["active_day_count"]
        or not 0 < metrics["active_symbol_count"] <= len(TIINGO_ETF_D1_SYMBOLS)
        or metrics.get("numeric_metrics_persisted") is not False
        or metrics.get("null_count")
        != TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT
        or metrics.get("primary_round_trip_cost_bps")
        != _decimal_text(TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PRIMARY_COST_BPS)
        or metrics.get("primary_net_mean_relation_to_flat")
        not in {"positive", "nonpositive"}
        or metrics.get("candidate_vs_null_p95_primary_cost")
        not in {"strictly_greater", "not_strictly_greater"}
        or not _valid_categorical_cost_relations(
            metrics.get("candidate_vs_equal_exposure_by_round_trip_cost")
        )
        or metrics.get("null_geometry")
        != {
            "block_size": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_BLOCK_SIZE,
            "permutation": "joint_cross_sectional_validation_target_return_blocks",
            "trailing_partial_block": "fixed_in_place",
        }
    ):
        raise ValueError("Tiingo D1 compression summary artifact is invalid")
    if status == "falsified" and reason == "frozen_kill_test_failed":
        return status, reason, "non_promoting_failed"
    if (
        status == "inconclusive_non_promoting"
        and reason == "frozen_kill_test_survived_non_promoting"
    ):
        return status, reason, "non_promoting_completed"
    raise ValueError("Tiingo D1 compression summary artifact is invalid")


def _valid_categorical_cost_relations(value: object) -> bool:
    expected_costs = {
        _decimal_text(cost)
        for cost in TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_COST_BPS
    }
    return (
        isinstance(value, dict)
        and set(value) == expected_costs
        and all(item in {"strictly_greater", "not_strictly_greater"} for item in value.values())
    )


def _aligned_rows(
    snapshot: LoadedTiingoEtfDailySnapshot,
) -> dict[str, tuple[TiingoEtfDailyRow, ...]]:
    if not isinstance(snapshot, LoadedTiingoEtfDailySnapshot):
        raise TypeError("Tiingo D1 compression requires a verified Tiingo snapshot")
    if set(snapshot.rows_by_symbol) != set(TIINGO_ETF_D1_SYMBOLS):
        raise ValueError("Tiingo D1 compression source symbols are invalid")
    rows_by_date: dict[str, dict[object, TiingoEtfDailyRow]] = {}
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = tuple(snapshot.rows_by_symbol[symbol])
        if not rows or any(row.symbol != symbol for row in rows):
            raise ValueError("Tiingo D1 compression source row identity is invalid")
        dates = tuple(row.session_date for row in rows)
        if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
            raise ValueError("Tiingo D1 compression source chronology is invalid")
        rows_by_date[symbol] = {row.session_date: row for row in rows}
    common_dates = tuple(sorted(set.intersection(*(set(rows) for rows in rows_by_date.values()))))
    if not common_dates:
        raise ValueError("Tiingo D1 compression source has no common sessions")
    return {
        symbol: tuple(rows_by_date[symbol][session] for session in common_dates)
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }


def _assert_dependency_separation(*, development_stop: int, validation_start: int) -> None:
    if (
        development_stop
        < TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK
        or validation_start - development_stop
        != TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PURGE_SESSIONS
        or validation_start
        - TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK
        <= development_stop
    ):
        raise ValueError("Tiingo D1 compression split does not separate dependencies")


def _symbol_qualifies(rows: Sequence[TiingoEtfDailyRow], index: int) -> bool:
    lookback = TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_LOOKBACK
    if index < lookback or index >= len(rows):
        return False
    causal = tuple(rows[index - lookback : index + 1])
    if len(causal) != lookback + 1 or any(not _valid_causal_row(row) for row in causal):
        return False
    if any(row.div_cash != 0 or row.split_factor != 1 for row in causal):
        return False
    if any(
        _absolute_close_return(current, previous)
        >= TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_DISCONTINUITY_LIMIT
        for previous, current in zip(causal, causal[1:], strict=False)
    ):
        return False
    prior_ranges = tuple(_range_to_open(row) for row in causal[:-1])
    current = causal[-1]
    current_range = _range_to_open(current)
    if not prior_ranges or any(value <= 0 for value in prior_ranges) or current_range <= 0:
        return False
    with localcontext() as context:
        context.prec = 34
        close_location = (current.close - current.low) / (current.high - current.low)
        return (
            current_range
            <= TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_RANGE_MULTIPLIER
            * Decimal(str(median(prior_ranges)))
            and close_location
            >= TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_CLOSE_LOCATION_MIN
            and current.close > current.open
        )


def _valid_causal_row(row: TiingoEtfDailyRow) -> bool:
    if not isinstance(row, TiingoEtfDailyRow):
        return False
    if min(row.open, row.high, row.low, row.close, row.volume) <= 0:
        return False
    return row.low <= min(row.open, row.close) and row.high >= max(row.open, row.close)


def _range_to_open(row: TiingoEtfDailyRow) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        return (row.high - row.low) / row.open


def _absolute_close_return(current: TiingoEtfDailyRow, previous: TiingoEtfDailyRow) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        return abs(current.close / previous.close - Decimal("1"))


def _evaluate(
    campaign_input: TiingoD1TrioIntradayCompressionInput,
) -> TiingoD1TrioIntradayCompressionMetrics:
    decisions = campaign_input._validation_decisions
    if not decisions:
        raise ValueError("invalid_validation_target")
    all_validation_indices = tuple(
        range(
            campaign_input.development_session_count + campaign_input.purge_session_count,
            campaign_input.common_session_count - 1,
        )
    )
    target_vectors = tuple(
        _target_vector(campaign_input._rows_by_symbol, index) for index in all_validation_indices
    )
    target_by_index = dict(zip(all_validation_indices, target_vectors, strict=True))
    candidate_returns = tuple(
        _selected_basket_return(target_by_index[decision.index], decision.symbols)
        for decision in decisions
    )
    equal_exposure_returns = tuple(
        _mean(target_by_index[decision.index]) for decision in decisions
    )
    candidate_by_cost = _net_mean_by_cost(candidate_returns)
    equal_exposure_by_cost = _net_mean_by_cost(equal_exposure_returns)
    null_values = tuple(
        _null_candidate_net_mean_primary_cost(
            decisions=decisions,
            all_indices=all_validation_indices,
            target_vectors=target_vectors,
            seed=TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_SEED_BASE + offset,
        )
        for offset in range(TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT)
    )
    return TiingoD1TrioIntradayCompressionMetrics(
        active_day_count=len(decisions),
        active_position_count=sum(len(decision.symbols) for decision in decisions),
        active_symbol_count=len({symbol for decision in decisions for symbol in decision.symbols}),
        candidate_net_mean_bps_by_cost=tuple(candidate_by_cost.items()),
        equal_exposure_net_mean_bps_by_cost=tuple(equal_exposure_by_cost.items()),
        null_p95_net_mean_bps_primary_cost=_percentile_higher(null_values, Decimal("0.95")),
        null_count=TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_COUNT,
    )


def _target_vector(
    rows_by_symbol: Mapping[str, Sequence[TiingoEtfDailyRow]],
    decision_index: int,
) -> tuple[Decimal, ...]:
    target_index = decision_index + 1
    values: list[Decimal] = []
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = rows_by_symbol[symbol]
        if target_index >= len(rows):
            raise ValueError("invalid_validation_target")
        target = rows[target_index]
        if not _valid_causal_row(target):
            raise ValueError("invalid_validation_target")
        with localcontext() as context:
            context.prec = 34
            values.append(target.close / target.open - Decimal("1"))
    return tuple(values)


def _net_mean_by_cost(returns: Sequence[Decimal]) -> dict[str, Decimal]:
    if not returns:
        raise ValueError("Tiingo D1 compression requires active validation returns")
    gross_bps = _mean(returns) * Decimal("10000")
    return {
        _decimal_text(cost): gross_bps - cost
        for cost in TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_COST_BPS
    }


def _null_candidate_net_mean_primary_cost(
    *,
    decisions: Sequence[_CompressionDecision],
    all_indices: Sequence[int],
    target_vectors: Sequence[tuple[Decimal, ...]],
    seed: int,
) -> Decimal:
    permuted = _block_permute_joint_target_vectors(target_vectors, seed=seed)
    target_by_index = dict(zip(all_indices, permuted, strict=True))
    selected = tuple(
        _selected_basket_return(target_by_index[decision.index], decision.symbols)
        for decision in decisions
    )
    return _net_mean_by_cost(selected)[
        _decimal_text(TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_PRIMARY_COST_BPS)
    ]


def _block_permute_joint_target_vectors(
    vectors: Sequence[tuple[Decimal, ...]],
    *,
    seed: int,
) -> tuple[tuple[Decimal, ...], ...]:
    block_size = TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_NULL_BLOCK_SIZE
    full_length = len(vectors) - len(vectors) % block_size
    blocks = [
        tuple(vectors[index : index + block_size])
        for index in range(0, full_length, block_size)
    ]
    random.Random(seed).shuffle(blocks)
    return tuple(value for block in blocks for value in block) + tuple(vectors[full_length:])


def _selected_basket_return(
    target_vector: Sequence[Decimal],
    symbols: Sequence[str],
) -> Decimal:
    return _mean(
        target_vector[TIINGO_ETF_D1_SYMBOLS.index(symbol)] for symbol in symbols
    )


def _percentile_higher(values: Sequence[Decimal], quantile: Decimal) -> Decimal:
    if not values or not Decimal("0") < quantile <= Decimal("1"):
        raise ValueError("Tiingo D1 compression percentile inputs are invalid")
    index = math.ceil(len(values) * float(quantile)) - 1
    return sorted(values)[index]


def _mean(values: Sequence[Decimal] | object) -> Decimal:
    collected = tuple(values)  # type: ignore[arg-type]
    if not collected or any(not isinstance(value, Decimal) for value in collected):
        raise ValueError("Tiingo D1 compression mean inputs are invalid")
    with localcontext() as context:
        context.prec = 34
        return sum(collected, Decimal("0")) / Decimal(len(collected))


def _unavailable_input(
    *,
    snapshot: LoadedTiingoEtfDailySnapshot,
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    common_session_count: int,
    development_stop: int,
    validation_start: int,
    reason: str,
    development_signal_count: int = 0,
    development_signal_symbol_count: int = 0,
    validation_active_day_count: int = 0,
    validation_active_position_count: int = 0,
) -> TiingoD1TrioIntradayCompressionInput:
    return _input(
        snapshot=snapshot,
        rows_by_symbol=rows_by_symbol,
        status="input_unavailable",
        reason=reason,
        common_session_count=common_session_count,
        development_stop=development_stop,
        validation_start=validation_start,
        development_signal_count=development_signal_count,
        development_signal_symbol_count=development_signal_symbol_count,
        validation_active_day_count=validation_active_day_count,
        validation_active_position_count=validation_active_position_count,
        decisions=(),
    )


def _input(
    *,
    snapshot: LoadedTiingoEtfDailySnapshot,
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    status: CompressionInputStatus,
    reason: str | None,
    common_session_count: int,
    development_stop: int,
    validation_start: int,
    development_signal_count: int,
    development_signal_symbol_count: int,
    validation_active_day_count: int,
    validation_active_position_count: int,
    decisions: Sequence[_CompressionDecision],
) -> TiingoD1TrioIntradayCompressionInput:
    snapshot_identity = snapshot.snapshot
    values = {
        "dataset_id": snapshot_identity.dataset_id,
        "dataset_hash": snapshot_identity.dataset_hash,
        "manifest_hash": snapshot_identity.manifest_hash,
        "status": status,
        "reason": reason,
        "common_session_count": common_session_count,
        "development_session_count": development_stop,
        "purge_session_count": validation_start - development_stop,
        "validation_session_count": common_session_count - validation_start,
        "development_signal_count": development_signal_count,
        "development_signal_symbol_count": development_signal_symbol_count,
        "validation_active_day_count": validation_active_day_count,
        "validation_active_position_count": validation_active_position_count,
    }
    return TiingoD1TrioIntradayCompressionInput(
        **values,
        input_hash=_input_hash(**values),
        _rows_by_symbol=rows_by_symbol,
        _validation_decisions=tuple(decisions),
    )


def _input_hash(**values: object) -> str:
    return _sha256_json(values)


def _result_payload(
    *,
    campaign: TiingoD1TrioIntradayCompressionCampaign,
    status: CompressionResultStatus,
    reason: str,
    metrics: TiingoD1TrioIntradayCompressionMetrics | None,
    summary_sha256: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": TIINGO_D1_TRIO_INTRADAY_COMPRESSION_CONTINUATION_ID,
        "campaign_contract_sha256": campaign.contract_sha256,
        "phase": "cpu_only_repeat_source_falsification",
        "status": status,
        "reason": reason,
        "input": campaign.campaign_input.safe_payload(),
        "metrics": None if metrics is None else metrics.safe_payload(),
        "scope": _scope_payload(),
    }
    return payload


def _scope_payload() -> dict[str, bool]:
    return {
        "source_local_only": True,
        "repeat_source_non_independent": True,
        "point_in_time_claim_allowed": False,
        "corporate_action_claim_allowed": False,
        "model_selection_allowed": False,
        "architecture_selection_allowed": False,
        "ensemble_allowed": False,
        "gpu_used": False,
        "paper_input_allowed": False,
        "broker_access": False,
        "profitability_or_pnl_claim": False,
        "live_behavior": False,
    }


def _write_or_reattach_json(path: Path, payload: Mapping[str, object]) -> str:
    encoded = _canonical_json(payload)
    digest = _sha256_bytes(encoded)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != encoded:
            raise ValueError("Tiingo D1 compression immutable artifact conflicts")
        return digest
    path.write_bytes(encoded)
    return digest


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_json(value: Mapping[str, object]) -> str:
    return _sha256_bytes(_canonical_json(value))


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _strict_relation(left: Decimal, right: Decimal) -> str:
    return "strictly_greater" if left > right else "not_strictly_greater"


def _positive_relation(value: Decimal) -> str:
    return "positive" if value > 0 else "nonpositive"

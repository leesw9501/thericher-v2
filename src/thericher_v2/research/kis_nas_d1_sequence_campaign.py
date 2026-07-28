"""Frozen per-symbol NAS D1 sequence campaign contract.

This module turns an already reattested, phase-local Data handoff into immutable
Research samples and a source-safe precommit.  It intentionally stops before
standardization, model fitting, prediction, replay, PnL, or broker behavior.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import SCHEMA_VERSION, Bar
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT,
    KisPaperDailyHistorySequenceInput,
    KisPaperDailyHistorySequencePhaseInput,
    require_attested_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.campaign import (
    SUPPORTED_NAIVE_BASELINES,
    CampaignCosts,
    ExecutableTarget,
)

KIS_NAS_D1_SEQUENCE_CAMPAIGN_VERSION = "kis-nas-d1-sequence-campaign-v1"
KIS_NAS_D1_SEQUENCE_CAMPAIGN_ID = "kis-nas-d1-sequence-campaign-v1"
KIS_NAS_D1_SEQUENCE_PRECOMMIT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research/kis-nas-d1-sequence-campaign-v1"
)
KIS_NAS_D1_SEQUENCE_LENGTH = 20
KIS_NAS_D1_SEQUENCE_FEATURE_SCHEMA_ID = "per-symbol-completed-d1-close-return-r1"
KIS_NAS_D1_SEQUENCE_FEATURE_NAMES = ("completed_daily_close_return",)
KIS_NAS_D1_SEQUENCE_DEVELOPMENT_DECISION_STRIDE = 1
KIS_NAS_D1_SEQUENCE_EVALUATION_DECISION_STRIDE = 2
KIS_NAS_D1_SEQUENCE_FEE_BPS_PER_FILL = Decimal("1")
KIS_NAS_D1_SEQUENCE_SLIPPAGE_BPS_PER_FILL = Decimal("2")
KIS_NAS_D1_SEQUENCE_COST_SOURCE_ID = "nas-d1-fixed-local-paper-cost-v1"
KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM = Decimal("0.0001")
KIS_NAS_D1_SEQUENCE_DECIMAL_PRECISION = 28
KIS_NAS_D1_SEQUENCE_ROUNDING_MODE = "ROUND_HALF_EVEN"
KIS_NAS_D1_SEQUENCE_COMPARATORS = (
    "flat",
    "always_long",
    "previous_bar_direction",
)
KIS_NAS_D1_SEQUENCE_PREVIOUS_BAR_DIRECTION_TIE_RULE = "strict_positive_long_else_flat"
KIS_NAS_D1_SEQUENCE_CPU_SMOKE_ID = "nas-d1-per-symbol-l2-logistic-smoke-v1"
KIS_NAS_D1_SEQUENCE_GPU_BREADTH_ID = "nas-d1-per-symbol-sequence-breadth-v1"
_CAMPAIGN_INPUT_ATTESTATION = object()


@dataclass(frozen=True, slots=True)
class KisNasD1SequenceSplit:
    """Exact session-count geometry owned by the frozen Data handoff."""

    development_start: date
    development_end: date
    purge_start: date
    purge_end: date
    validation_start: date
    validation_end: date
    development_session_count: int = KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT
    purge_session_count: int = KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT
    validation_session_count: int = KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.development_session_count
            != KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT
            or self.purge_session_count != KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT
            or self.validation_session_count
            != KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT
            or self.schema_version != SCHEMA_VERSION
            or not (
                self.development_start <= self.development_end
                < self.purge_start
                <= self.purge_end
                < self.validation_start
                <= self.validation_end
            )
        ):
            raise ValueError("NAS D1 sequence split is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "phase_boundaries": {
                "development": {
                    "start": self.development_start.isoformat(),
                    "end": self.development_end.isoformat(),
                },
                "purge": {
                    "start": self.purge_start.isoformat(),
                    "end": self.purge_end.isoformat(),
                },
                "validation": {
                    "start": self.validation_start.isoformat(),
                    "end": self.validation_end.isoformat(),
                },
            },
            "phase_local_features": True,
            "validation_uses_purge_sessions": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1SequenceCampaignContract:
    """Model-free target, cost, comparator, and cadence terms for one campaign."""

    campaign_id: str
    panel_dataset_id: str
    panel_dataset_hash: str
    index_hash: str
    split: KisNasD1SequenceSplit
    sequence_length: int
    feature_schema_id: str
    costs: CampaignCosts
    price_quantum: Decimal
    decimal_precision: int
    rounding_mode: str
    target: ExecutableTarget
    comparators: tuple[str, ...]
    development_decision_stride: int
    evaluation_decision_stride: int
    previous_bar_direction_tie_rule: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparators", tuple(self.comparators))
        if (
            self.campaign_id != KIS_NAS_D1_SEQUENCE_CAMPAIGN_ID
            or self.panel_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
            or self.panel_dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
            or self.sequence_length != KIS_NAS_D1_SEQUENCE_LENGTH
            or self.feature_schema_id != KIS_NAS_D1_SEQUENCE_FEATURE_SCHEMA_ID
            or self.costs.fee_bps != KIS_NAS_D1_SEQUENCE_FEE_BPS_PER_FILL
            or self.costs.slippage_bps != KIS_NAS_D1_SEQUENCE_SLIPPAGE_BPS_PER_FILL
            or self.costs.slippage_source_id != KIS_NAS_D1_SEQUENCE_COST_SOURCE_ID
            or self.price_quantum != KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM
            or self.decimal_precision != KIS_NAS_D1_SEQUENCE_DECIMAL_PRECISION
            or self.rounding_mode != KIS_NAS_D1_SEQUENCE_ROUNDING_MODE
            or self.target != ExecutableTarget()
            or self.comparators != KIS_NAS_D1_SEQUENCE_COMPARATORS
            or set(self.comparators) - SUPPORTED_NAIVE_BASELINES
            or self.development_decision_stride
            != KIS_NAS_D1_SEQUENCE_DEVELOPMENT_DECISION_STRIDE
            or self.evaluation_decision_stride != KIS_NAS_D1_SEQUENCE_EVALUATION_DECISION_STRIDE
            or self.previous_bar_direction_tie_rule
            != KIS_NAS_D1_SEQUENCE_PREVIOUS_BAR_DIRECTION_TIE_RULE
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 sequence campaign contract is invalid")

    @property
    def contract_hash(self) -> str:
        return _sha256_json(self.safe_payload())

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "panel_dataset_id": self.panel_dataset_id,
            "panel_dataset_hash": self.panel_dataset_hash,
            "index_hash": self.index_hash,
            "split": self.split.safe_payload(),
            "features": {
                "schema_id": self.feature_schema_id,
                "names": list(KIS_NAS_D1_SEQUENCE_FEATURE_NAMES),
                "sequence_length": self.sequence_length,
                "per_symbol_only": True,
                "cross_symbol_features_allowed": False,
                "return_anchor_inside_phase": True,
            },
            "target": {
                "decision_price": self.target.decision_price,
                "entry_price": self.target.entry_price,
                "exit_price": self.target.exit_price,
                "position_side": self.target.position_side,
                "entry_bar_offset": self.target.entry_bar_offset,
                "exit_bar_offset": self.target.exit_bar_offset,
                "quantity": "one_share",
                "development_target_definition": "strictly_positive_after_cost_open_to_open",
                "costs": {
                    "fee_bps_per_fill": str(self.costs.fee_bps),
                    "slippage_bps_per_fill": str(self.costs.slippage_bps),
                    "source_id": self.costs.slippage_source_id,
                    "price_quantum": str(self.price_quantum),
                    "decimal_precision": self.decimal_precision,
                    "rounding_mode": self.rounding_mode,
                },
            },
            "comparators": {
                "ids": list(self.comparators),
                "evaluation_decision_stride_sessions": self.evaluation_decision_stride,
                "previous_bar_direction_tie_rule": self.previous_bar_direction_tie_rule,
            },
            "development_decision_stride_sessions": self.development_decision_stride,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1DevelopmentSample:
    """A completed-bar-only per-symbol sequence with a development-only label."""

    symbol: str
    return_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    entry_start: datetime
    exit_start: datetime
    close_returns: tuple[float, ...]
    label: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "close_returns", tuple(self.close_returns))
        _validate_sample_geometry(
            symbol=self.symbol,
            return_anchor_start=self.return_anchor_start,
            feature_start=self.feature_start,
            decision_start=self.decision_start,
            decision_end=self.decision_end,
            entry_start=self.entry_start,
            exit_start=self.exit_start,
            close_returns=self.close_returns,
            schema_version=self.schema_version,
        )
        if self.label not in {0, 1}:
            raise ValueError("NAS D1 development label is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1ValidationSample:
    """A completed-bar-only per-symbol sequence that cannot carry a target label."""

    symbol: str
    return_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    entry_start: datetime
    exit_start: datetime
    close_returns: tuple[float, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "close_returns", tuple(self.close_returns))
        _validate_sample_geometry(
            symbol=self.symbol,
            return_anchor_start=self.return_anchor_start,
            feature_start=self.feature_start,
            decision_start=self.decision_start,
            decision_end=self.decision_end,
            entry_start=self.entry_start,
            exit_start=self.exit_start,
            close_returns=self.close_returns,
            schema_version=self.schema_version,
        )


@dataclass(frozen=True, slots=True, init=False)
class KisNasD1SequenceCampaignInput:
    """Attested development labels plus a separate target-free validation view."""

    contract: KisNasD1SequenceCampaignContract
    source_input_id: str
    source_targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    source_limitations: tuple[str, ...]
    development_sessions: tuple[date, ...]
    validation_sessions: tuple[date, ...]
    development_samples_by_symbol: Mapping[str, tuple[KisNasD1DevelopmentSample, ...]]
    validation_samples_by_symbol: Mapping[str, tuple[KisNasD1ValidationSample, ...]]
    development_input_hash: str
    validation_input_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the frozen NAS D1 sequence campaign builder")

    def development_samples(self, symbol: str) -> tuple[KisNasD1DevelopmentSample, ...]:
        require_attested_kis_nas_d1_sequence_campaign_input(self)
        return self.development_samples_by_symbol[_resolve_symbol(symbol)]

    def validation_samples(self, symbol: str) -> tuple[KisNasD1ValidationSample, ...]:
        require_attested_kis_nas_d1_sequence_campaign_input(self)
        return self.validation_samples_by_symbol[_resolve_symbol(symbol)]


@dataclass(frozen=True, slots=True)
class KisNasD1SequenceCampaignPrecommit:
    """Immutable external source-safe evidence that the campaign was frozen."""

    campaign_input: KisNasD1SequenceCampaignInput
    precommit_path: Path
    precommit_hash: str

    def __post_init__(self) -> None:
        require_attested_kis_nas_d1_sequence_campaign_input(self.campaign_input)
        if (
            self.precommit_path.is_symlink()
            or not self.precommit_path.is_file()
            or not _is_sha256(self.precommit_hash)
            or _sha256_file(self.precommit_path) != self.precommit_hash
        ):
            raise ValueError("NAS D1 sequence precommit is invalid")


def build_kis_nas_d1_sequence_campaign(
    source_input: KisPaperDailyHistorySequenceInput,
) -> KisNasD1SequenceCampaignInput:
    """Freeze causal samples from the Data-owned reattested phase handoff."""

    require_attested_kis_paper_daily_history_sequence_input(source_input)
    contract = _build_contract(source_input)
    development = _build_development_samples(
        source_input.development,
        costs=contract.costs,
    )
    validation = _build_validation_samples(source_input.validation)
    result = object.__new__(KisNasD1SequenceCampaignInput)
    object.__setattr__(result, "contract", contract)
    object.__setattr__(result, "source_input_id", source_input.input_id)
    object.__setattr__(
        result,
        "source_targets_by_key",
        MappingProxyType(dict(source_input.source_targets_by_key)),
    )
    object.__setattr__(result, "source_limitations", source_input.raw_price_limitations)
    object.__setattr__(result, "development_sessions", source_input.development.common_sessions)
    object.__setattr__(result, "validation_sessions", source_input.validation.common_sessions)
    object.__setattr__(result, "development_samples_by_symbol", MappingProxyType(development))
    object.__setattr__(result, "validation_samples_by_symbol", MappingProxyType(validation))
    object.__setattr__(
        result,
        "development_input_hash",
        _development_input_hash(development),
    )
    object.__setattr__(
        result,
        "validation_input_hash",
        _validation_input_hash(validation),
    )
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _CAMPAIGN_INPUT_ATTESTATION)
    require_attested_kis_nas_d1_sequence_campaign_input(result)
    return result


def write_kis_nas_d1_sequence_campaign_precommit(
    campaign_input: KisNasD1SequenceCampaignInput,
    *,
    artifact_root: Path | str = KIS_NAS_D1_SEQUENCE_PRECOMMIT_ROOT,
    repo_root: Path | str | None = None,
) -> KisNasD1SequenceCampaignPrecommit:
    """Write or reattest the one immutable source-safe campaign precommit."""

    require_attested_kis_nas_d1_sequence_campaign_input(campaign_input)
    repository = _repository_root(repo_root)
    root = _external_output_root(artifact_root, repository)
    label = f"campaign={campaign_input.contract.contract_hash.removeprefix('sha256:')[:20]}"
    path = root / label / "precommit.json"
    payload = _precommit_payload(campaign_input)
    _assert_source_safe(payload)
    precommit_hash = _write_or_verify_json(path, payload)
    return KisNasD1SequenceCampaignPrecommit(
        campaign_input=campaign_input,
        precommit_path=path,
        precommit_hash=precommit_hash,
    )


def calculate_kis_nas_d1_sequence_campaign_precommit_hash(
    campaign_input: KisNasD1SequenceCampaignInput,
) -> str:
    """Derive the immutable precommit identity without creating an artifact."""

    require_attested_kis_nas_d1_sequence_campaign_input(campaign_input)
    payload = _precommit_payload(campaign_input)
    _assert_source_safe(payload)
    return "sha256:" + hashlib.sha256(_json_bytes(payload)).hexdigest()


def require_attested_kis_nas_d1_sequence_campaign_input(input: object) -> None:
    """Fail closed before a later CPU/GPU worker consumes campaign samples."""

    if (
        not isinstance(input, KisNasD1SequenceCampaignInput)
        or getattr(input, "_attestation", None) is not _CAMPAIGN_INPUT_ATTESTATION
        or input.schema_version != SCHEMA_VERSION
        or not _is_sha256(input.development_input_hash)
        or not _is_sha256(input.validation_input_hash)
        or input.source_input_id != KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID
        or tuple(input.source_targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or input.source_limitations != KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS
        or len(input.development_sessions)
        != KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT
        or len(input.validation_sessions)
        != KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT
        or tuple(sorted(input.development_sessions)) != input.development_sessions
        or tuple(sorted(input.validation_sessions)) != input.validation_sessions
        or input.development_sessions[-1] >= input.validation_sessions[0]
        or tuple(input.development_samples_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(input.validation_samples_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    ):
        raise ValueError("NAS D1 sequence campaign input requires a frozen contract")
    _require_contract_matches_input(input.contract, input)
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        development = input.development_samples_by_symbol[symbol]
        validation = input.validation_samples_by_symbol[symbol]
        if (
            len(development)
            != _expected_sample_count(
                KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT,
                KIS_NAS_D1_SEQUENCE_DEVELOPMENT_DECISION_STRIDE,
            )
            or len(validation)
            != _expected_sample_count(
                KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT,
                KIS_NAS_D1_SEQUENCE_EVALUATION_DECISION_STRIDE,
            )
            or any(not isinstance(sample, KisNasD1DevelopmentSample) for sample in development)
            or any(not isinstance(sample, KisNasD1ValidationSample) for sample in validation)
            or not _samples_stay_inside_phase(
                development,
                input.development_sessions,
                expected_symbol=symbol,
                decision_stride=KIS_NAS_D1_SEQUENCE_DEVELOPMENT_DECISION_STRIDE,
            )
            or not _samples_stay_inside_phase(
                validation,
                input.validation_sessions,
                expected_symbol=symbol,
                decision_stride=KIS_NAS_D1_SEQUENCE_EVALUATION_DECISION_STRIDE,
            )
        ):
            raise ValueError("NAS D1 sequence campaign samples are invalid")
    if (
        input.development_input_hash != _development_input_hash(input.development_samples_by_symbol)
        or input.validation_input_hash != _validation_input_hash(input.validation_samples_by_symbol)
    ):
        raise ValueError("NAS D1 sequence campaign input hash is invalid")


def _build_contract(
    source_input: KisPaperDailyHistorySequenceInput,
) -> KisNasD1SequenceCampaignContract:
    development = source_input.development.common_sessions
    purge = source_input.purge.common_sessions
    validation = source_input.validation.common_sessions
    return KisNasD1SequenceCampaignContract(
        campaign_id=KIS_NAS_D1_SEQUENCE_CAMPAIGN_ID,
        panel_dataset_id=source_input.panel_dataset_id,
        panel_dataset_hash=source_input.panel_dataset_hash,
        index_hash=source_input.index_hash,
        split=KisNasD1SequenceSplit(
            development_start=development[0],
            development_end=development[-1],
            purge_start=purge[0],
            purge_end=purge[-1],
            validation_start=validation[0],
            validation_end=validation[-1],
        ),
        sequence_length=KIS_NAS_D1_SEQUENCE_LENGTH,
        feature_schema_id=KIS_NAS_D1_SEQUENCE_FEATURE_SCHEMA_ID,
        costs=CampaignCosts(
            fee_bps=KIS_NAS_D1_SEQUENCE_FEE_BPS_PER_FILL,
            slippage_bps=KIS_NAS_D1_SEQUENCE_SLIPPAGE_BPS_PER_FILL,
            slippage_source_id=KIS_NAS_D1_SEQUENCE_COST_SOURCE_ID,
        ),
        price_quantum=KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM,
        decimal_precision=KIS_NAS_D1_SEQUENCE_DECIMAL_PRECISION,
        rounding_mode=KIS_NAS_D1_SEQUENCE_ROUNDING_MODE,
        target=ExecutableTarget(),
        comparators=KIS_NAS_D1_SEQUENCE_COMPARATORS,
        development_decision_stride=KIS_NAS_D1_SEQUENCE_DEVELOPMENT_DECISION_STRIDE,
        evaluation_decision_stride=KIS_NAS_D1_SEQUENCE_EVALUATION_DECISION_STRIDE,
        previous_bar_direction_tie_rule=KIS_NAS_D1_SEQUENCE_PREVIOUS_BAR_DIRECTION_TIE_RULE,
    )


def _build_development_samples(
    phase: KisPaperDailyHistorySequencePhaseInput,
    *,
    costs: CampaignCosts,
) -> dict[str, tuple[KisNasD1DevelopmentSample, ...]]:
    samples_by_symbol: dict[str, tuple[KisNasD1DevelopmentSample, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        bars = phase.stream(symbol).bars
        samples: list[KisNasD1DevelopmentSample] = []
        for decision_index in _eligible_decision_indices(
            len(bars),
            decision_stride=KIS_NAS_D1_SEQUENCE_DEVELOPMENT_DECISION_STRIDE,
        ):
            timing, close_returns = _sample_timing_and_features(
                symbol=symbol,
                bars=bars,
                decision_index=decision_index,
            )
            samples.append(
                KisNasD1DevelopmentSample(
                    **timing,
                    close_returns=close_returns,
                    label=_after_cost_label(
                        entry_bar=bars[decision_index + 1],
                        exit_bar=bars[decision_index + 2],
                        costs=costs,
                    ),
                )
            )
        samples_by_symbol[symbol] = tuple(samples)
    return samples_by_symbol


def _build_validation_samples(
    phase: KisPaperDailyHistorySequencePhaseInput,
) -> dict[str, tuple[KisNasD1ValidationSample, ...]]:
    samples_by_symbol: dict[str, tuple[KisNasD1ValidationSample, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        bars = phase.stream(symbol).bars
        samples: list[KisNasD1ValidationSample] = []
        for decision_index in _eligible_decision_indices(
            len(bars),
            decision_stride=KIS_NAS_D1_SEQUENCE_EVALUATION_DECISION_STRIDE,
        ):
            timing, close_returns = _sample_timing_and_features(
                symbol=symbol,
                bars=bars,
                decision_index=decision_index,
            )
            samples.append(KisNasD1ValidationSample(**timing, close_returns=close_returns))
        samples_by_symbol[symbol] = tuple(samples)
    return samples_by_symbol


def _eligible_decision_indices(session_count: int, *, decision_stride: int) -> range:
    if decision_stride <= 0:
        raise ValueError("NAS D1 sequence decision stride is invalid")
    final_exclusive = session_count - ExecutableTarget().exit_bar_offset
    if final_exclusive <= KIS_NAS_D1_SEQUENCE_LENGTH:
        raise ValueError("NAS D1 sequence phase has insufficient completed bars")
    return range(KIS_NAS_D1_SEQUENCE_LENGTH, final_exclusive, decision_stride)


def _sample_timing_and_features(
    *,
    symbol: str,
    bars: Sequence[Bar],
    decision_index: int,
) -> tuple[dict[str, object], tuple[float, ...]]:
    feature_start_index = decision_index - KIS_NAS_D1_SEQUENCE_LENGTH + 1
    return_anchor_index = feature_start_index - 1
    if return_anchor_index < 0 or decision_index + ExecutableTarget().exit_bar_offset >= len(bars):
        raise ValueError("NAS D1 sequence sample geometry is invalid")
    close_returns = tuple(
        _completed_close_return(bars[index], bars[index - 1])
        for index in range(feature_start_index, decision_index + 1)
    )
    return (
        {
            "symbol": symbol,
            "return_anchor_start": bars[return_anchor_index].start_ts,
            "feature_start": bars[feature_start_index].start_ts,
            "decision_start": bars[decision_index].start_ts,
            "decision_end": bars[decision_index].end_ts,
            "entry_start": bars[decision_index + 1].start_ts,
            "exit_start": bars[decision_index + 2].start_ts,
        },
        close_returns,
    )


def _completed_close_return(current: Bar, prior: Bar) -> float:
    if (
        current.end_ts <= prior.end_ts
        or current.close <= 0
        or prior.close <= 0
        or not current.complete
        or not prior.complete
    ):
        raise ValueError("NAS D1 sequence completed close return is invalid")
    result = float(current.close / prior.close - Decimal("1"))
    if not math.isfinite(result):
        raise ValueError("NAS D1 sequence completed close return is non-finite")
    return result


def _after_cost_label(
    *,
    entry_bar: Bar,
    exit_bar: Bar,
    costs: CampaignCosts,
) -> int:
    """Mirror one-share local-paper fill arithmetic without a replay side effect."""

    if (
        entry_bar.start_ts.date() >= exit_bar.start_ts.date()
        or entry_bar.open <= 0
        or exit_bar.open <= 0
    ):
        raise ValueError("NAS D1 sequence target requires later observed opens")
    scale = Decimal("10000")
    with localcontext() as context:
        context.prec = KIS_NAS_D1_SEQUENCE_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        entry_price = (
            entry_bar.open * (Decimal("1") + costs.slippage_bps / scale)
        ).quantize(KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
        exit_price = (
            exit_bar.open * (Decimal("1") - costs.slippage_bps / scale)
        ).quantize(KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
        entry_fee = (entry_price * costs.fee_bps / scale).quantize(
            KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        exit_fee = (exit_price * costs.fee_bps / scale).quantize(
            KIS_NAS_D1_SEQUENCE_PRICE_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        return int(exit_price - exit_fee > entry_price + entry_fee)


def _validate_sample_geometry(
    *,
    symbol: str,
    return_anchor_start: datetime,
    feature_start: datetime,
    decision_start: datetime,
    decision_end: datetime,
    entry_start: datetime,
    exit_start: datetime,
    close_returns: tuple[float, ...],
    schema_version: int,
) -> None:
    if (
        _resolve_symbol(symbol) != symbol
        or len(close_returns) != KIS_NAS_D1_SEQUENCE_LENGTH
        or any(not math.isfinite(value) for value in close_returns)
        or schema_version != SCHEMA_VERSION
        or not (
            return_anchor_start < feature_start
            and feature_start <= decision_start
            and decision_start < decision_end
            and decision_end <= entry_start
            and entry_start < exit_start
        )
    ):
        raise ValueError("NAS D1 sequence sample timing or feature geometry is invalid")


def _samples_stay_inside_phase(
    samples: Sequence[KisNasD1DevelopmentSample | KisNasD1ValidationSample],
    sessions: tuple[date, ...],
    *,
    expected_symbol: str,
    decision_stride: int,
) -> bool:
    expected_indices = tuple(
        _eligible_decision_indices(
            len(sessions),
            decision_stride=decision_stride,
        )
    )
    if len(samples) != len(expected_indices):
        return False
    for sample, decision_index in zip(samples, expected_indices, strict=True):
        if (
            sample.symbol != expected_symbol
            or sample.return_anchor_start.date()
            != sessions[decision_index - KIS_NAS_D1_SEQUENCE_LENGTH]
            or sample.feature_start.date()
            != sessions[decision_index - KIS_NAS_D1_SEQUENCE_LENGTH + 1]
            or sample.decision_start.date() != sessions[decision_index]
            or sample.entry_start.date() != sessions[decision_index + 1]
            or sample.exit_start.date() != sessions[decision_index + 2]
        ):
            return False
    return True


def _expected_sample_count(session_count: int, decision_stride: int) -> int:
    return len(tuple(_eligible_decision_indices(session_count, decision_stride=decision_stride)))


def _require_contract_matches_input(
    contract: KisNasD1SequenceCampaignContract,
    input: KisNasD1SequenceCampaignInput,
) -> None:
    if (
        contract.split.development_start != input.development_sessions[0]
        or contract.split.development_end != input.development_sessions[-1]
        or contract.split.validation_start != input.validation_sessions[0]
        or contract.split.validation_end != input.validation_sessions[-1]
    ):
        raise ValueError("NAS D1 sequence campaign contract source is invalid")


def _development_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisNasD1DevelopmentSample]],
) -> str:
    return _sha256_json(
        {
            "kind": "nas_d1_development_sequence_input",
            "feature_schema_id": KIS_NAS_D1_SEQUENCE_FEATURE_SCHEMA_ID,
            "samples": {
                symbol: [
                    {
                        "return_anchor_start": sample.return_anchor_start.isoformat(),
                        "feature_start": sample.feature_start.isoformat(),
                        "decision_end": sample.decision_end.isoformat(),
                        "entry_start": sample.entry_start.isoformat(),
                        "exit_start": sample.exit_start.isoformat(),
                        "close_returns": [format(value, ".17g") for value in sample.close_returns],
                        "label": sample.label,
                    }
                    for sample in samples_by_symbol[symbol]
                ]
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
        }
    )


def _validation_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisNasD1ValidationSample]],
) -> str:
    return _sha256_json(
        {
            "kind": "nas_d1_validation_sequence_input",
            "feature_schema_id": KIS_NAS_D1_SEQUENCE_FEATURE_SCHEMA_ID,
            "samples": {
                symbol: [
                    {
                        "return_anchor_start": sample.return_anchor_start.isoformat(),
                        "feature_start": sample.feature_start.isoformat(),
                        "decision_end": sample.decision_end.isoformat(),
                        "entry_start": sample.entry_start.isoformat(),
                        "exit_start": sample.exit_start.isoformat(),
                        "close_returns": [format(value, ".17g") for value in sample.close_returns],
                    }
                    for sample in samples_by_symbol[symbol]
                ]
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
        }
    )


def _precommit_payload(campaign_input: KisNasD1SequenceCampaignInput) -> dict[str, object]:
    contract = campaign_input.contract
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_sequence_campaign_precommit",
        "status": "precommitted",
        "campaign_id": contract.campaign_id,
        "campaign_contract_hash": contract.contract_hash,
        "source": {
            "input_id": campaign_input.source_input_id,
            "dataset_id": contract.panel_dataset_id,
            "dataset_hash": contract.panel_dataset_hash,
            "index_hash": contract.index_hash,
            "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
            "adjustment_mode": KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
            "current_listing_only": True,
            "historical_point_in_time_eligible": False,
            "cross_source_blending_allowed": False,
            "target_states": [
                _target_state_payload(target)
                for target in campaign_input.source_targets_by_key.values()
            ],
            "limitations": list(campaign_input.source_limitations),
        },
        "contract": contract.safe_payload(),
        "inputs": {
            "development": {
                "input_hash": campaign_input.development_input_hash,
                "sample_counts": {
                    symbol: len(samples)
                    for symbol, samples in campaign_input.development_samples_by_symbol.items()
                },
                "labels_exposed": True,
                "standardization": "not_materialized",
            },
            "validation": {
                "input_hash": campaign_input.validation_input_hash,
                "sample_counts": {
                    symbol: len(samples)
                    for symbol, samples in campaign_input.validation_samples_by_symbol.items()
                },
                "labels_exposed": False,
                "standardization": "not_materialized",
            },
        },
        "next_eligible_packages": {
            "cpu_smoke": {
                "package_id": KIS_NAS_D1_SEQUENCE_CPU_SMOKE_ID,
                "models": ["per_symbol_l2_logistic"],
                "training_scope": "development_labels_only",
                "validation_scope": "target_free_predictions_only",
                "standardization": "per_symbol_development_only",
                "result_interpretation": "pipeline_smoke_only_no_selection_or_replay",
            },
            "gpu_breadth": {
                "package_id": KIS_NAS_D1_SEQUENCE_GPU_BREADTH_ID,
                "architectures": ["lstm", "causal_tcn", "compact_attention"],
                "training_scope": "per_symbol_development_labels_only",
                "validation_scope": "target_free_predictions_only",
                "feature_shape": [KIS_NAS_D1_SEQUENCE_LENGTH, 1],
                "result_interpretation": "candidate_breadth_only_no_selection_ensemble_or_replay",
            },
        },
        "scope": {
            "offline_only": True,
            "model_fitting_materialized": False,
            "prediction_materialized": False,
            "replay_materialized": False,
            "pnl_materialized": False,
            "ranking_eligible": False,
            "paper_decision_eligible": False,
            "live_eligible": False,
        },
        "artifact_policy": {
            "repository_storage_allowed": False,
            "immutable_write_only": True,
            "value_level_market_data_persisted": False,
            "feature_values_persisted": False,
            "target_values_persisted": False,
            "per_decision_values_persisted": False,
            "model_artifacts_persisted": False,
        },
    }


def _target_state_payload(target: KisPaperDailyHistoryPanelTarget) -> dict[str, object]:
    return {
        "target_key": target.target_key,
        "state": target.state,
        "last_reason": target.last_reason,
        "coverage_start_bucket": target.coverage_start_bucket,
        "coverage_end_bucket": target.coverage_end_bucket,
    }


def _assert_source_safe(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "returns",
        "return",
        "label",
        "labels",
        "featurevalues",
        "targetvalues",
        "persample",
        "perdecision",
        "sourcepath",
        "workdir",
        "eventjsonl",
        "eventlog",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in forbidden:
                raise ValueError("NAS D1 sequence precommit contains unsafe value-level data")
            _assert_source_safe(nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _assert_source_safe(nested)


def _external_output_root(root: Path | str, repository: Path) -> Path:
    candidate = Path(root)
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError("NAS D1 sequence precommit root is invalid") from error
    if candidate.is_symlink():
        raise ValueError("NAS D1 sequence precommit root is invalid")
    mounted_artifact_root = repository / "model_artifacts"
    permitted_mount = (
        not mounted_artifact_root.is_symlink()
        and mounted_artifact_root.is_mount()
        and resolved.is_relative_to(mounted_artifact_root.resolve())
    )
    if resolved.is_relative_to(repository) and not permitted_mount:
        raise ValueError("NAS D1 sequence precommit root must stay outside the Git workspace")
    candidate.mkdir(parents=True, exist_ok=True)
    if candidate.is_symlink() or candidate.resolve() != resolved:
        raise ValueError("NAS D1 sequence precommit root is invalid")
    return resolved


def _repository_root(repo_root: Path | str | None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if root.is_symlink() or not root.is_dir():
        raise ValueError("NAS D1 sequence repository root is invalid")
    return root.resolve()


def _write_or_verify_json(path: Path, payload: Mapping[str, object]) -> str:
    if path.is_symlink():
        raise ValueError("NAS D1 sequence precommit path is invalid")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError("NAS D1 sequence precommit directory is invalid")
    expected = _json_bytes(payload)
    try:
        with path.open("xb") as handle:
            handle.write(expected)
    except FileExistsError as error:
        if path.is_symlink() or path.read_bytes() != expected:
            raise FileExistsError("NAS D1 sequence precommit is immutable") from error
    return _sha256_file(path)


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True


def _resolve_symbol(symbol: str) -> str:
    resolved = symbol.strip().upper()
    if resolved not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 sequence symbol is unsupported")
    return resolved

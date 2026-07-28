"""Immutable candidate-only campaign for NAS D1 candle-state features.

The module freezes causal feature geometry, the local-paper-compatible target,
and simple non-tuned comparators before a model is fit.  It deliberately does
not evaluate PnL, select a candidate, create a decision, or touch a broker.
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
from thericher_v2.data.kis_paper_daily_history_candle_state_input import (
    KIS_PAPER_DAILY_HISTORY_CANDLE_STATE_INPUT_ID,
    build_kis_paper_daily_history_candle_state_input,
    require_attested_kis_paper_daily_history_candle_state_input,
)
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
)
from thericher_v2.data.kis_paper_daily_history_sequence_input import (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH,
    KisPaperDailyHistorySequenceInput,
    require_attested_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.campaign import CampaignCosts, ExecutableTarget
from thericher_v2.research.causal_bar_features import (
    KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES,
    KIS_NAS_D1_CANDLE_STATE_FEATURE_SCHEMA_ID,
    KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS,
    KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH,
)

KIS_NAS_D1_CANDLE_STATE_CAMPAIGN_VERSION = "kis-nas-d1-candle-state-campaign-v3"
KIS_NAS_D1_CANDLE_STATE_CAMPAIGN_ID = "kis-nas-d1-candle-state-campaign-v3"
KIS_NAS_D1_CANDLE_STATE_PRECOMMIT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research/kis-nas-d1-candle-state-campaign-v3"
)
KIS_NAS_D1_CANDLE_STATE_CPU_SMOKE_ID = "nas-d1-candle-state-per-symbol-l2-logistic-smoke-v3"
KIS_NAS_D1_CANDLE_STATE_GPU_BREADTH_ID = "nas-d1-candle-state-per-symbol-sequence-breadth-v3"
KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT = 5
KIS_NAS_D1_CANDLE_STATE_DEVELOPMENT_DECISION_STRIDE = 1
KIS_NAS_D1_CANDLE_STATE_EVALUATION_DECISION_STRIDE = 2
KIS_NAS_D1_CANDLE_STATE_FEE_BPS_PER_FILL = Decimal("1")
KIS_NAS_D1_CANDLE_STATE_SLIPPAGE_BPS_PER_FILL = Decimal("2")
KIS_NAS_D1_CANDLE_STATE_COST_SOURCE_ID = "nas-d1-fixed-local-paper-cost-v1"
KIS_NAS_D1_CANDLE_STATE_PRICE_QUANTUM = Decimal("0.0001")
KIS_NAS_D1_CANDLE_STATE_DECIMAL_PRECISION = 28
KIS_NAS_D1_CANDLE_STATE_COMPARATORS = (
    "flat",
    "always_long",
    "previous_candle_body_direction",
    "positive_close_location",
)
KIS_NAS_D1_CANDLE_STATE_KILL_TEST = (
    "candidate_must_not_advance_without_a_later_independent_sealed_after_cost_comparison_"
    "against_always_long"
)
KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES = frozenset(
    {"review_unavailable", "unsupported", "uncertain", "supported-with-limits"}
)

_CAMPAIGN_INPUT_ATTESTATION = object()
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateFeatureContract:
    """Data-owned completed-bar feature definitions frozen before labels."""

    schema_id: str = KIS_NAS_D1_CANDLE_STATE_FEATURE_SCHEMA_ID
    names: tuple[str, ...] = KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES
    sequence_length: int = KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH
    required_completed_bars: int = KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "names", tuple(self.names))
        if (
            self.schema_id != KIS_NAS_D1_CANDLE_STATE_FEATURE_SCHEMA_ID
            or self.names != KIS_NAS_D1_CANDLE_STATE_FEATURE_NAMES
            or self.sequence_length != KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH
            or self.required_completed_bars != KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state feature contract is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "names": list(self.names),
            "feature_shape": [self.sequence_length, len(self.names)],
            "required_completed_bars": self.required_completed_bars,
            "source": "per_symbol_completed_d1_ohlcv_only",
            "cross_symbol_features_allowed": False,
            "lookback_anchor_inside_phase": True,
            "zero_range_policy": "signed_body_and_close_location_are_zero",
            "zero_volume_policy": "log1p_volume_is_defined",
            "future_bars_read": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateCampaignContract:
    """Feature, target, comparator, and stop terms for one candidate screen."""

    campaign_id: str
    panel_dataset_id: str
    panel_dataset_hash: str
    index_hash: str
    features: KisNasD1CandleStateFeatureContract
    costs: CampaignCosts
    target: ExecutableTarget
    comparators: tuple[str, ...]
    development_decision_stride: int
    evaluation_decision_stride: int
    strongest_kill_test: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparators", tuple(self.comparators))
        if (
            self.campaign_id != KIS_NAS_D1_CANDLE_STATE_CAMPAIGN_ID
            or self.panel_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
            or not _is_sha256(self.panel_dataset_hash)
            or not _is_sha256(self.index_hash)
            or self.costs.fee_bps != KIS_NAS_D1_CANDLE_STATE_FEE_BPS_PER_FILL
            or self.costs.slippage_bps != KIS_NAS_D1_CANDLE_STATE_SLIPPAGE_BPS_PER_FILL
            or self.costs.slippage_source_id != KIS_NAS_D1_CANDLE_STATE_COST_SOURCE_ID
            or self.target != ExecutableTarget()
            or self.comparators != KIS_NAS_D1_CANDLE_STATE_COMPARATORS
            or self.development_decision_stride
            != KIS_NAS_D1_CANDLE_STATE_DEVELOPMENT_DECISION_STRIDE
            or self.evaluation_decision_stride
            != KIS_NAS_D1_CANDLE_STATE_EVALUATION_DECISION_STRIDE
            or self.strongest_kill_test != KIS_NAS_D1_CANDLE_STATE_KILL_TEST
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 candle-state campaign contract is invalid")

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
            "features": self.features.safe_payload(),
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
                    "price_quantum": str(KIS_NAS_D1_CANDLE_STATE_PRICE_QUANTUM),
                    "decimal_precision": KIS_NAS_D1_CANDLE_STATE_DECIMAL_PRECISION,
                    "rounding_mode": "ROUND_HALF_EVEN",
                },
            },
            "comparators": {
                "ids": list(self.comparators),
                "previous_candle_body_direction_rule": "strict_positive_long_else_flat",
                "positive_close_location_rule": "strict_positive_long_else_flat",
                "evaluation_decision_stride_sessions": self.evaluation_decision_stride,
            },
            "normalizer_fit_scope": "per_symbol_development_feature_rows_only",
            "strongest_kill_test": self.strongest_kill_test,
            "development_decision_stride_sessions": self.development_decision_stride,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateDevelopmentSample:
    """One causal sequence plus its development-only after-cost target."""

    symbol: str
    lookback_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    feature_sequence: tuple[tuple[float, ...], ...]
    label: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_sample(
            symbol=self.symbol,
            lookback_anchor_start=self.lookback_anchor_start,
            feature_start=self.feature_start,
            decision_start=self.decision_start,
            decision_end=self.decision_end,
            feature_sequence=self.feature_sequence,
            schema_version=self.schema_version,
        )
        if self.label not in {0, 1}:
            raise ValueError("NAS D1 candle-state development label is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateValidationSample:
    """One causal sequence deliberately kept target-free."""

    symbol: str
    lookback_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    feature_sequence: tuple[tuple[float, ...], ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_sample(
            symbol=self.symbol,
            lookback_anchor_start=self.lookback_anchor_start,
            feature_start=self.feature_start,
            decision_start=self.decision_start,
            decision_end=self.decision_end,
            feature_sequence=self.feature_sequence,
            schema_version=self.schema_version,
        )


@dataclass(frozen=True, slots=True, init=False)
class KisNasD1CandleStateCampaignInput:
    """Attested development labels and target-free validation sequences."""

    contract: KisNasD1CandleStateCampaignContract
    source_input_id: str
    source_limitations: tuple[str, ...]
    development_sessions: tuple[date, ...]
    validation_sessions: tuple[date, ...]
    development_samples_by_symbol: Mapping[str, tuple[KisNasD1CandleStateDevelopmentSample, ...]]
    validation_samples_by_symbol: Mapping[str, tuple[KisNasD1CandleStateValidationSample, ...]]
    development_input_hash: str
    validation_input_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the frozen NAS D1 candle-state campaign builder")

    def development_samples(self, symbol: str) -> tuple[KisNasD1CandleStateDevelopmentSample, ...]:
        require_attested_kis_nas_d1_candle_state_campaign_input(self)
        return self.development_samples_by_symbol[_resolve_symbol(symbol)]

    def validation_samples(self, symbol: str) -> tuple[KisNasD1CandleStateValidationSample, ...]:
        require_attested_kis_nas_d1_candle_state_campaign_input(self)
        return self.validation_samples_by_symbol[_resolve_symbol(symbol)]


@dataclass(frozen=True, slots=True)
class KisNasD1CandleStateCampaignPrecommit:
    """Immutable, source-safe campaign evidence written before fitting."""

    campaign_input: KisNasD1CandleStateCampaignInput
    review_status: str
    precommit_path: Path
    precommit_hash: str

    def __post_init__(self) -> None:
        require_attested_kis_nas_d1_candle_state_campaign_input(self.campaign_input)
        _require_review_status(self.review_status)
        if (
            _is_link_or_junction(self.precommit_path)
            or not self.precommit_path.is_file()
            or not _is_sha256(self.precommit_hash)
            or _sha256_file(self.precommit_path) != self.precommit_hash
        ):
            raise ValueError("NAS D1 candle-state precommit is invalid")


def build_kis_nas_d1_candle_state_campaign(
    source_input: KisPaperDailyHistorySequenceInput,
) -> KisNasD1CandleStateCampaignInput:
    """Freeze Data feature rows and development-only after-cost labels."""

    require_attested_kis_paper_daily_history_sequence_input(source_input)
    data_input = build_kis_paper_daily_history_candle_state_input(source_input)
    require_attested_kis_paper_daily_history_candle_state_input(data_input)
    contract = _build_contract(source_input)
    development = _build_development_samples(source_input, data_input, contract.costs)
    validation = _build_validation_samples(source_input, data_input)
    result = object.__new__(KisNasD1CandleStateCampaignInput)
    object.__setattr__(result, "contract", contract)
    object.__setattr__(result, "source_input_id", data_input.input_id)
    object.__setattr__(result, "source_limitations", tuple(data_input.raw_price_limitations))
    object.__setattr__(result, "development_sessions", source_input.development.common_sessions)
    object.__setattr__(result, "validation_sessions", source_input.validation.common_sessions)
    object.__setattr__(result, "development_samples_by_symbol", MappingProxyType(development))
    object.__setattr__(result, "validation_samples_by_symbol", MappingProxyType(validation))
    object.__setattr__(result, "development_input_hash", _development_input_hash(development))
    object.__setattr__(result, "validation_input_hash", _validation_input_hash(validation))
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _CAMPAIGN_INPUT_ATTESTATION)
    require_attested_kis_nas_d1_candle_state_campaign_input(result)
    return result


def write_kis_nas_d1_candle_state_campaign_precommit(
    campaign_input: KisNasD1CandleStateCampaignInput,
    *,
    review_status: str,
    artifact_root: Path | str = KIS_NAS_D1_CANDLE_STATE_PRECOMMIT_ROOT,
    repo_root: Path | str | None = None,
) -> KisNasD1CandleStateCampaignPrecommit:
    """Write or verify the single immutable source-safe precommit receipt."""

    require_attested_kis_nas_d1_candle_state_campaign_input(campaign_input)
    _require_review_status(review_status)
    repository = _repository_root(repo_root)
    output_root = _external_output_root(artifact_root, repository)
    payload = _precommit_payload(campaign_input, review_status=review_status)
    _assert_source_safe(payload)
    path = output_root / "campaign-precommit.json"
    precommit_hash = _write_or_verify_json(path, payload, repository)
    return KisNasD1CandleStateCampaignPrecommit(
        campaign_input=campaign_input,
        review_status=review_status,
        precommit_path=path,
        precommit_hash=precommit_hash,
    )


def calculate_kis_nas_d1_candle_state_campaign_precommit_hash(
    campaign_input: KisNasD1CandleStateCampaignInput,
    *,
    review_status: str,
) -> str:
    """Return the frozen precommit digest without writing an artifact."""

    require_attested_kis_nas_d1_candle_state_campaign_input(campaign_input)
    _require_review_status(review_status)
    return _sha256_json(_precommit_payload(campaign_input, review_status=review_status))


def require_attested_kis_nas_d1_candle_state_campaign_input(value: object) -> None:
    """Fail closed unless the campaign remains frozen and phase-local."""

    if (
        not isinstance(value, KisNasD1CandleStateCampaignInput)
        or getattr(value, "_attestation", None) is not _CAMPAIGN_INPUT_ATTESTATION
        or value.source_input_id != KIS_PAPER_DAILY_HISTORY_CANDLE_STATE_INPUT_ID
        or value.source_limitations == ()
        or value.schema_version != SCHEMA_VERSION
        or tuple(value.development_samples_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(value.validation_samples_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or not _is_sha256(value.development_input_hash)
        or not _is_sha256(value.validation_input_hash)
        or not _is_sha256(value.contract.contract_hash)
    ):
        raise ValueError("NAS D1 candle-state campaign input is invalid")
    _require_contract_matches_input(value.contract, value)
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        development = value.development_samples_by_symbol[symbol]
        validation = value.validation_samples_by_symbol[symbol]
        if (
            not _samples_stay_inside_phase(
                development,
                value.development_sessions,
                expected_symbol=symbol,
                decision_stride=KIS_NAS_D1_CANDLE_STATE_DEVELOPMENT_DECISION_STRIDE,
            )
            or not _samples_stay_inside_phase(
                validation,
                value.validation_sessions,
                expected_symbol=symbol,
                decision_stride=KIS_NAS_D1_CANDLE_STATE_EVALUATION_DECISION_STRIDE,
            )
        ):
            raise ValueError("NAS D1 candle-state campaign samples cross a phase boundary")
    if (
        value.development_input_hash != _development_input_hash(value.development_samples_by_symbol)
        or value.validation_input_hash != _validation_input_hash(value.validation_samples_by_symbol)
    ):
        raise ValueError("NAS D1 candle-state campaign input hash is invalid")


def is_kis_nas_d1_candle_state_reference_long(
    sample: KisNasD1CandleStateValidationSample,
    *,
    comparator_id: str,
) -> bool:
    """Return a fixed comparator decision without ranking or side effects."""

    if comparator_id not in KIS_NAS_D1_CANDLE_STATE_COMPARATORS:
        raise ValueError("NAS D1 candle-state comparator is unsupported")
    if comparator_id == "flat":
        return False
    if comparator_id == "always_long":
        return True
    if comparator_id == "previous_candle_body_direction":
        return sample.feature_sequence[-1][1] > 0.0
    return sample.feature_sequence[-1][2] > 0.0


def _build_contract(
    source_input: KisPaperDailyHistorySequenceInput,
) -> KisNasD1CandleStateCampaignContract:
    return KisNasD1CandleStateCampaignContract(
        campaign_id=KIS_NAS_D1_CANDLE_STATE_CAMPAIGN_ID,
        panel_dataset_id=source_input.panel_dataset_id,
        panel_dataset_hash=source_input.panel_dataset_hash,
        index_hash=source_input.index_hash,
        features=KisNasD1CandleStateFeatureContract(),
        costs=CampaignCosts(
            fee_bps=KIS_NAS_D1_CANDLE_STATE_FEE_BPS_PER_FILL,
            slippage_bps=KIS_NAS_D1_CANDLE_STATE_SLIPPAGE_BPS_PER_FILL,
            slippage_source_id=KIS_NAS_D1_CANDLE_STATE_COST_SOURCE_ID,
        ),
        target=ExecutableTarget(),
        comparators=KIS_NAS_D1_CANDLE_STATE_COMPARATORS,
        development_decision_stride=KIS_NAS_D1_CANDLE_STATE_DEVELOPMENT_DECISION_STRIDE,
        evaluation_decision_stride=KIS_NAS_D1_CANDLE_STATE_EVALUATION_DECISION_STRIDE,
        strongest_kill_test=KIS_NAS_D1_CANDLE_STATE_KILL_TEST,
    )


def _build_development_samples(
    source_input: KisPaperDailyHistorySequenceInput,
    data_input: object,
    costs: CampaignCosts,
) -> dict[str, tuple[KisNasD1CandleStateDevelopmentSample, ...]]:
    samples_by_symbol: dict[str, tuple[KisNasD1CandleStateDevelopmentSample, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        source_bars = source_input.development.stream(symbol).bars
        decision_indices = {bar.start_ts: index for index, bar in enumerate(source_bars)}
        samples: list[KisNasD1CandleStateDevelopmentSample] = []
        for data_sample in data_input.development.samples_by_symbol[symbol]:
            _require_data_sample_surface(data_sample)
            decision_index = decision_indices.get(data_sample.decision_start)
            if decision_index is None:
                raise ValueError("NAS D1 candle-state development timing is invalid")
            if decision_index + ExecutableTarget().exit_bar_offset >= len(source_bars):
                continue
            samples.append(
                KisNasD1CandleStateDevelopmentSample(
                    **_feature_sample_payload(data_sample),
                    label=_after_cost_label(
                        entry_bar=source_bars[decision_index + 1],
                        exit_bar=source_bars[decision_index + 2],
                        costs=costs,
                    ),
                )
            )
        samples_by_symbol[symbol] = tuple(samples)
    return samples_by_symbol


def _build_validation_samples(
    source_input: KisPaperDailyHistorySequenceInput,
    data_input: object,
) -> dict[str, tuple[KisNasD1CandleStateValidationSample, ...]]:
    samples_by_symbol: dict[str, tuple[KisNasD1CandleStateValidationSample, ...]] = {}
    expected_remainder = (KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1) % (
        KIS_NAS_D1_CANDLE_STATE_EVALUATION_DECISION_STRIDE
    )
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        source_bars = source_input.validation.stream(symbol).bars
        decision_indices = {bar.start_ts: index for index, bar in enumerate(source_bars)}
        samples: list[KisNasD1CandleStateValidationSample] = []
        for data_sample in data_input.validation.samples_by_symbol[symbol]:
            _require_data_sample_surface(data_sample)
            decision_index = decision_indices.get(data_sample.decision_start)
            if decision_index is None:
                raise ValueError("NAS D1 candle-state validation timing is invalid")
            if (
                decision_index + ExecutableTarget().exit_bar_offset >= len(source_bars)
                or decision_index % KIS_NAS_D1_CANDLE_STATE_EVALUATION_DECISION_STRIDE
                != expected_remainder
            ):
                continue
            samples.append(KisNasD1CandleStateValidationSample(**_feature_sample_payload(data_sample)))
        samples_by_symbol[symbol] = tuple(samples)
    return samples_by_symbol


def _feature_sample_payload(data_sample: object) -> dict[str, object]:
    sequence = tuple(
        tuple(float(value) for value in row) for row in data_sample.feature_sequence
    )
    if (
        len(sequence) != KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH
        or any(len(row) != KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT for row in sequence)
    ):
        raise ValueError("NAS D1 candle-state feature sequence shape is invalid")
    return {
        "symbol": data_sample.symbol,
        "lookback_anchor_start": data_sample.lookback_anchor_start,
        "feature_start": data_sample.feature_start,
        "decision_start": data_sample.decision_start,
        "decision_end": data_sample.decision_end,
        "feature_sequence": sequence,
    }


def _require_data_sample_surface(data_sample: object) -> None:
    required = (
        "symbol",
        "lookback_anchor_start",
        "feature_start",
        "decision_start",
        "decision_end",
        "feature_sequence",
    )
    prohibited = ("label", "entry_start", "exit_start", "entry_end", "exit_end")
    if any(not hasattr(data_sample, name) for name in required) or any(
        hasattr(data_sample, name) for name in prohibited
    ):
        raise ValueError("NAS D1 candle-state Data sample surface is invalid")


def _after_cost_label(
    *,
    entry_bar: Bar,
    exit_bar: Bar,
    costs: CampaignCosts,
) -> int:
    """Mirror the fixed one-share local-paper target without a replay side effect."""

    if (
        entry_bar.start_ts.date() >= exit_bar.start_ts.date()
        or entry_bar.open <= 0
        or exit_bar.open <= 0
    ):
        raise ValueError("NAS D1 candle-state target requires later observed opens")
    scale = Decimal("10000")
    with localcontext() as context:
        context.prec = KIS_NAS_D1_CANDLE_STATE_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        entry_price = (
            entry_bar.open * (Decimal("1") + costs.slippage_bps / scale)
        ).quantize(KIS_NAS_D1_CANDLE_STATE_PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
        exit_price = (
            exit_bar.open * (Decimal("1") - costs.slippage_bps / scale)
        ).quantize(KIS_NAS_D1_CANDLE_STATE_PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
        entry_fee = (entry_price * costs.fee_bps / scale).quantize(
            KIS_NAS_D1_CANDLE_STATE_PRICE_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        exit_fee = (exit_price * costs.fee_bps / scale).quantize(
            KIS_NAS_D1_CANDLE_STATE_PRICE_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        return int(exit_price - exit_fee > entry_price + entry_fee)


def _validate_sample(
    *,
    symbol: str,
    lookback_anchor_start: datetime,
    feature_start: datetime,
    decision_start: datetime,
    decision_end: datetime,
    feature_sequence: tuple[tuple[float, ...], ...],
    schema_version: int,
) -> None:
    if (
        _resolve_symbol(symbol) != symbol
        or len(feature_sequence) != KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH
        or any(len(row) != KIS_NAS_D1_CANDLE_STATE_FEATURE_COUNT for row in feature_sequence)
        or any(not math.isfinite(value) for row in feature_sequence for value in row)
        or schema_version != SCHEMA_VERSION
        or not (
            lookback_anchor_start < feature_start
            and feature_start <= decision_start < decision_end
        )
    ):
        raise ValueError("NAS D1 candle-state sample timing or feature geometry is invalid")


def _samples_stay_inside_phase(
    samples: Sequence[KisNasD1CandleStateDevelopmentSample | KisNasD1CandleStateValidationSample],
    sessions: tuple[date, ...],
    *,
    expected_symbol: str,
    decision_stride: int,
) -> bool:
    expected_indices = tuple(
        range(
            KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS - 1,
            len(sessions) - ExecutableTarget().exit_bar_offset,
            decision_stride,
        )
    )
    if not samples or len(samples) != len(expected_indices):
        return False
    for sample, decision_index in zip(samples, expected_indices, strict=True):
        if (
            sample.symbol != expected_symbol
            or sample.lookback_anchor_start.date()
            != sessions[decision_index - KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS + 1]
            or sample.feature_start.date()
            != sessions[decision_index - KIS_NAS_D1_CANDLE_STATE_SEQUENCE_LENGTH + 1]
            or sample.decision_start.date() != sessions[decision_index]
        ):
            return False
    return True


def _require_contract_matches_input(
    contract: KisNasD1CandleStateCampaignContract,
    value: KisNasD1CandleStateCampaignInput,
) -> None:
    if (
        contract.panel_dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
        or len(value.development_sessions) <= KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS
        or len(value.validation_sessions) <= KIS_NAS_D1_CANDLE_STATE_REQUIRED_BARS
        or value.development_sessions[-1] >= value.validation_sessions[0]
    ):
        raise ValueError("NAS D1 candle-state campaign split does not match input")


def _development_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisNasD1CandleStateDevelopmentSample]],
) -> str:
    return _sha256_json(
        {
            "kind": "kis_nas_d1_candle_state_development_input",
            "samples": {
                symbol: [
                    {
                        "decision_start": sample.decision_start.isoformat(),
                        "feature_hash": _feature_hash(sample.feature_sequence),
                        "label": sample.label,
                    }
                    for sample in samples_by_symbol[symbol]
                ]
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
        }
    )


def _validation_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisNasD1CandleStateValidationSample]],
) -> str:
    return _sha256_json(
        {
            "kind": "kis_nas_d1_candle_state_validation_input",
            "samples": {
                symbol: [
                    {
                        "decision_start": sample.decision_start.isoformat(),
                        "feature_hash": _feature_hash(sample.feature_sequence),
                    }
                    for sample in samples_by_symbol[symbol]
                ]
                for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            },
        }
    )


def _feature_hash(sequence: Sequence[Sequence[float]]) -> str:
    return _sha256_json(
        {"features": [[format(float(value), ".17g") for value in row] for row in sequence]}
    )


def _precommit_payload(
    campaign_input: KisNasD1CandleStateCampaignInput,
    *,
    review_status: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_candle_state_campaign_precommit",
        "campaign_version": KIS_NAS_D1_CANDLE_STATE_CAMPAIGN_VERSION,
        "campaign_contract": campaign_input.contract.safe_payload(),
        "campaign_contract_hash": campaign_input.contract.contract_hash,
        "review_status": review_status,
        "source": {
            "input_id": campaign_input.source_input_id,
            "development_input_hash": campaign_input.development_input_hash,
            "validation_input_hash": campaign_input.validation_input_hash,
            "source_limitations": list(campaign_input.source_limitations),
            "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
        },
        "compute_budget": {
            "cpu_package_id": KIS_NAS_D1_CANDLE_STATE_CPU_SMOKE_ID,
            "gpu_package_id": KIS_NAS_D1_CANDLE_STATE_GPU_BREADTH_ID,
            "candidate_only": True,
        },
        "reporting": _reporting_payload(),
    }


def _reporting_payload() -> dict[str, object]:
    return {
        "selection_allowed": False,
        "ensemble_allowed": False,
        "promotion_allowed": False,
        "replay_allowed": False,
        "pnl_materialized": False,
        "paper_trading_eligible": False,
    }


def _repository_root(repo_root: Path | str | None) -> Path:
    root = Path(repo_root) if repo_root is not None else _MODULE_REPOSITORY_ROOT
    if _is_link_or_junction(root) or not root.is_dir():
        raise ValueError("NAS D1 candle-state repository root is invalid")
    return root.resolve()


def _external_output_root(root: Path | str, repository: Path) -> Path:
    requested = Path(root)
    _reject_link_or_junction_components(requested)
    resolved = requested.resolve()
    _reject_repository_artifact_path(resolved, repository)
    _reject_repository_artifact_path(resolved, _MODULE_REPOSITORY_ROOT)
    requested.mkdir(parents=True, exist_ok=True)
    _reject_link_or_junction_components(requested)
    resolved = requested.resolve()
    _reject_repository_artifact_path(resolved, repository)
    _reject_repository_artifact_path(resolved, _MODULE_REPOSITORY_ROOT)
    return resolved


def _write_or_verify_json(path: Path, payload: Mapping[str, object], repository: Path) -> str:
    _reject_link_or_junction_components(path)
    resolved = path.resolve()
    _reject_repository_artifact_path(resolved, repository)
    _reject_repository_artifact_path(resolved, _MODULE_REPOSITORY_ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_or_junction_components(path)
    try:
        with path.open("xb") as handle:
            handle.write(_json_bytes(payload))
    except FileExistsError as exc:
        if _is_link_or_junction(path) or path.read_bytes() != _json_bytes(payload):
            raise FileExistsError("NAS D1 candle-state precommit is immutable") from exc
    _reject_link_or_junction_components(path)
    return _sha256_file(path)


def _reject_repository_artifact_path(path: Path, repository: Path) -> None:
    docker_repository = _DOCKER_REPOSITORY_ROOT.resolve()
    docker_artifact_root = _DOCKER_ARTIFACT_ROOT.resolve()
    if (
        repository == docker_repository
        and _DOCKER_ARTIFACT_ROOT.is_mount()
        and path.is_relative_to(docker_artifact_root)
    ):
        return
    if repository == docker_repository:
        raise ValueError("NAS D1 candle-state Docker artifacts must use /app/model_artifacts")
    if not path.is_relative_to(repository):
        return
    raise ValueError("NAS D1 candle-state artifacts must stay outside the Git workspace")


def _reject_link_or_junction_components(path: Path) -> None:
    current = Path(path)
    while True:
        if _is_link_or_junction(current):
            raise ValueError("NAS D1 candle-state artifact path cannot contain a link")
        if current == current.parent:
            return
        current = current.parent


def _is_link_or_junction(path: Path) -> bool:
    try:
        junction = getattr(path, "is_junction", None)
        return path.is_symlink() or bool(junction and junction())
    except OSError:
        return True


def _assert_source_safe(value: object) -> None:
    forbidden = {
        "account",
        "accountnumber",
        "broker",
        "closereturns",
        "credentials",
        "entry",
        "event",
        "events",
        "featuresequence",
        "featurerows",
        "label",
        "labels",
        "modelweights",
        "open",
        "order",
        "orders",
        "pnl",
        "prediction",
        "predictions",
        "probabilities",
        "rawbars",
        "secret",
        "statedict",
        "threshold",
        "thresholds",
        "volume",
        "weights",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in forbidden:
                raise ValueError("NAS D1 candle-state receipt contains unsafe value-level data")
            _assert_source_safe(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe(nested)


def _require_review_status(value: str) -> None:
    if value not in KIS_NAS_D1_CANDLE_STATE_ALLOWED_REVIEW_STATUSES:
        raise ValueError("NAS D1 candle-state review status is invalid")


def _resolve_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("NAS D1 candle-state symbol is invalid")
    resolved = symbol.strip().upper()
    if resolved not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 candle-state symbol is unsupported")
    return resolved


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value.removeprefix("sha256:")
    )


def _sha256_json(value: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(value)).hexdigest()


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()

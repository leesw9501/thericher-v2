"""Frozen NAS D1 volatility-conditioned trend campaign contract.

The package consumes an already reattested, source-local D1 sequence input and
the narrow Data-owned volatility/trend adapter.  It intentionally stops before
standardization, model fitting, predictions, replay, PnL, or broker behavior.
"""

from __future__ import annotations

import hashlib
import importlib
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
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS,
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT,
    KisPaperDailyHistorySequenceInput,
    require_attested_kis_paper_daily_history_sequence_input,
)
from thericher_v2.research.campaign import CampaignCosts, ExecutableTarget
from thericher_v2.research.causal_bar_features import (
    KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS,
)

KIS_NAS_D1_VOLATILITY_TREND_CAMPAIGN_VERSION = "kis-nas-d1-volatility-trend-campaign-v1"
KIS_NAS_D1_VOLATILITY_TREND_CAMPAIGN_ID = "kis-nas-d1-volatility-trend-campaign-v1"
KIS_NAS_D1_VOLATILITY_TREND_PRECOMMIT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/research/kis-nas-d1-volatility-trend-campaign-v1"
)
KIS_NAS_D1_VOLATILITY_TREND_CPU_SMOKE_ID = (
    "nas-d1-volatility-trend-per-symbol-l2-logistic-smoke-v1"
)
KIS_NAS_D1_VOLATILITY_TREND_GPU_BREADTH_ID = (
    "nas-d1-volatility-trend-per-symbol-sequence-breadth-v1"
)
KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT = 5
KIS_NAS_D1_VOLATILITY_TREND_QUANTILE = 0.75
KIS_NAS_D1_VOLATILITY_TREND_QUANTILE_METHOD = "linear_n_minus_1"
KIS_NAS_D1_VOLATILITY_TREND_DEVELOPMENT_DECISION_STRIDE = 1
KIS_NAS_D1_VOLATILITY_TREND_EVALUATION_DECISION_STRIDE = 2
KIS_NAS_D1_VOLATILITY_TREND_FEE_BPS_PER_FILL = Decimal("1")
KIS_NAS_D1_VOLATILITY_TREND_SLIPPAGE_BPS_PER_FILL = Decimal("2")
KIS_NAS_D1_VOLATILITY_TREND_COST_SOURCE_ID = "nas-d1-fixed-local-paper-cost-v1"
KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM = Decimal("0.0001")
KIS_NAS_D1_VOLATILITY_TREND_DECIMAL_PRECISION = 28
KIS_NAS_D1_VOLATILITY_TREND_ROUNDING_MODE = "ROUND_HALF_EVEN"
KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS = (
    "flat",
    "always_long",
    "previous_bar_direction",
    "ungated_5d_trend",
    "low_vol_only",
    "volatility_gated_5d_trend",
)
KIS_NAS_D1_VOLATILITY_TREND_PREVIOUS_BAR_DIRECTION_TIE_RULE = (
    "strict_positive_long_else_flat"
)
KIS_NAS_D1_VOLATILITY_TREND_ALLOWED_REVIEW_STATUSES = frozenset(
    {"review_unavailable", "unsupported", "uncertain", "supported-with-limits"}
)

_DATA_ADAPTER_MODULE = "thericher_v2.data.kis_paper_daily_history_volatility_trend_input"
_CAMPAIGN_INPUT_ATTESTATION = object()
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_REPOSITORY_ROOT = Path("/app")
_DOCKER_ARTIFACT_ROOT = _DOCKER_REPOSITORY_ROOT / "model_artifacts"


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendFeatureContract:
    """Data-owned feature metadata fixed before Research derives labels."""

    schema_id: str
    names: tuple[str, ...]
    sequence_length: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "names", tuple(self.names))
        if (
            not self.schema_id
            or len(self.names) != KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT
            or any(not isinstance(name, str) or not name for name in self.names)
            or len(set(self.names)) != len(self.names)
            or self.sequence_length != 20
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend feature contract is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "names": list(self.names),
            "sequence_length": self.sequence_length,
            "feature_shape": [self.sequence_length, len(self.names)],
            "source": "completed_d1_ohlc_only",
            "cross_symbol_features_allowed": False,
            "lookback_anchor_inside_phase": True,
            "terminal_realized_volatility": "completed_20_return_window_only",
            "terminal_trend": "completed_5_return_window_only",
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendSplit:
    """The fixed chronological 1,510 / 22 / 647 source geometry."""

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
            or self.purge_session_count
            != KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT
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
            raise ValueError("NAS D1 volatility trend split is invalid")

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
class KisNasD1VolatilityTrendCampaignContract:
    """Feature, target, comparator, cost, and decision terms for one campaign."""

    campaign_id: str
    panel_dataset_id: str
    panel_dataset_hash: str
    index_hash: str
    split: KisNasD1VolatilityTrendSplit
    features: KisNasD1VolatilityTrendFeatureContract
    costs: CampaignCosts
    price_quantum: Decimal
    decimal_precision: int
    rounding_mode: str
    target: ExecutableTarget
    comparators: tuple[str, ...]
    development_decision_stride: int
    evaluation_decision_stride: int
    previous_bar_direction_tie_rule: str
    volatility_quantile: float
    volatility_quantile_method: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparators", tuple(self.comparators))
        if (
            self.campaign_id != KIS_NAS_D1_VOLATILITY_TREND_CAMPAIGN_ID
            or self.panel_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
            or not _is_sha256(self.panel_dataset_hash)
            or not _is_sha256(self.index_hash)
            or self.costs.fee_bps != KIS_NAS_D1_VOLATILITY_TREND_FEE_BPS_PER_FILL
            or self.costs.slippage_bps != KIS_NAS_D1_VOLATILITY_TREND_SLIPPAGE_BPS_PER_FILL
            or self.costs.slippage_source_id != KIS_NAS_D1_VOLATILITY_TREND_COST_SOURCE_ID
            or self.price_quantum != KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM
            or self.decimal_precision != KIS_NAS_D1_VOLATILITY_TREND_DECIMAL_PRECISION
            or self.rounding_mode != KIS_NAS_D1_VOLATILITY_TREND_ROUNDING_MODE
            or self.target != ExecutableTarget()
            or self.comparators != KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS
            or self.development_decision_stride
            != KIS_NAS_D1_VOLATILITY_TREND_DEVELOPMENT_DECISION_STRIDE
            or self.evaluation_decision_stride
            != KIS_NAS_D1_VOLATILITY_TREND_EVALUATION_DECISION_STRIDE
            or self.previous_bar_direction_tie_rule
            != KIS_NAS_D1_VOLATILITY_TREND_PREVIOUS_BAR_DIRECTION_TIE_RULE
            or self.volatility_quantile != KIS_NAS_D1_VOLATILITY_TREND_QUANTILE
            or self.volatility_quantile_method
            != KIS_NAS_D1_VOLATILITY_TREND_QUANTILE_METHOD
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend campaign contract is invalid")

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
                    "price_quantum": str(self.price_quantum),
                    "decimal_precision": self.decimal_precision,
                    "rounding_mode": self.rounding_mode,
                },
            },
            "comparators": {
                "ids": list(self.comparators),
                "previous_bar_direction_tie_rule": self.previous_bar_direction_tie_rule,
                "ungated_5d_trend_rule": "terminal_trend_5_strict_positive_long_else_flat",
                "low_vol_only_rule": "terminal_rv20_lte_development_q75_long_else_flat",
                "volatility_gated_5d_trend_rule": (
                    "terminal_trend_5_strict_positive_and_terminal_rv20_lte_development_q75"
                ),
                "evaluation_decision_stride_sessions": self.evaluation_decision_stride,
            },
            "volatility_gate": {
                "quantile": self.volatility_quantile,
                "method": self.volatility_quantile_method,
                "fit_scope": "per_symbol_development_feature_rows_only",
                "receipt_value_policy": "hash_only_no_numeric_threshold",
            },
            "development_decision_stride_sessions": self.development_decision_stride,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendThreshold:
    """Development-only threshold whose numeric value never enters a receipt."""

    symbol: str
    development_input_hash: str
    quantile: float
    method: str
    value: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
            or not _is_sha256(self.development_input_hash)
            or self.quantile != KIS_NAS_D1_VOLATILITY_TREND_QUANTILE
            or self.method != KIS_NAS_D1_VOLATILITY_TREND_QUANTILE_METHOD
            or not math.isfinite(self.value)
            or self.value < 0.0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("NAS D1 volatility trend threshold is invalid")

    @property
    def threshold_hash(self) -> str:
        return _sha256_json(
            {
                "symbol": self.symbol,
                "development_input_hash": self.development_input_hash,
                "quantile": format(self.quantile, ".17g"),
                "method": self.method,
                "value": format(self.value, ".17g"),
            }
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "quantile": self.quantile,
            "method": self.method,
            "development_input_hash": self.development_input_hash,
            "threshold_hash": self.threshold_hash,
            "numeric_value_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendDevelopmentSample:
    """A causal Data feature sequence plus a development-only target label."""

    symbol: str
    lookback_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    feature_sequence: tuple[tuple[float, ...], ...]
    terminal_realized_volatility_20: float
    terminal_trend_5: float
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
            terminal_realized_volatility_20=self.terminal_realized_volatility_20,
            terminal_trend_5=self.terminal_trend_5,
            schema_version=self.schema_version,
        )
        if self.label not in {0, 1}:
            raise ValueError("NAS D1 volatility trend development label is invalid")


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendValidationSample:
    """A causal Data feature sequence that deliberately has no target label."""

    symbol: str
    lookback_anchor_start: datetime
    feature_start: datetime
    decision_start: datetime
    decision_end: datetime
    feature_sequence: tuple[tuple[float, ...], ...]
    terminal_realized_volatility_20: float
    terminal_trend_5: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_sample(
            symbol=self.symbol,
            lookback_anchor_start=self.lookback_anchor_start,
            feature_start=self.feature_start,
            decision_start=self.decision_start,
            decision_end=self.decision_end,
            feature_sequence=self.feature_sequence,
            terminal_realized_volatility_20=self.terminal_realized_volatility_20,
            terminal_trend_5=self.terminal_trend_5,
            schema_version=self.schema_version,
        )


@dataclass(frozen=True, slots=True, init=False)
class KisNasD1VolatilityTrendCampaignInput:
    """Attested development labels and target-free validation feature sequences."""

    contract: KisNasD1VolatilityTrendCampaignContract
    source_input_id: str
    source_targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    source_limitations: tuple[str, ...]
    development_sessions: tuple[date, ...]
    validation_sessions: tuple[date, ...]
    development_samples_by_symbol: Mapping[
        str, tuple[KisNasD1VolatilityTrendDevelopmentSample, ...]
    ]
    validation_samples_by_symbol: Mapping[
        str, tuple[KisNasD1VolatilityTrendValidationSample, ...]
    ]
    thresholds_by_symbol: Mapping[str, KisNasD1VolatilityTrendThreshold]
    development_input_hash: str
    validation_input_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the frozen NAS D1 volatility trend campaign builder")

    def development_samples(
        self,
        symbol: str,
    ) -> tuple[KisNasD1VolatilityTrendDevelopmentSample, ...]:
        _require_attested_campaign_input_identity(self)
        return self.development_samples_by_symbol[_resolve_symbol(symbol)]

    def validation_samples(
        self,
        symbol: str,
    ) -> tuple[KisNasD1VolatilityTrendValidationSample, ...]:
        _require_attested_campaign_input_identity(self)
        return self.validation_samples_by_symbol[_resolve_symbol(symbol)]

    def threshold(self, symbol: str) -> KisNasD1VolatilityTrendThreshold:
        _require_attested_campaign_input_identity(self)
        return self.thresholds_by_symbol[_resolve_symbol(symbol)]


@dataclass(frozen=True, slots=True)
class KisNasD1VolatilityTrendCampaignPrecommit:
    """Immutable source-safe campaign evidence written before fitting begins."""

    campaign_input: KisNasD1VolatilityTrendCampaignInput
    review_status: str
    precommit_path: Path
    precommit_hash: str

    def __post_init__(self) -> None:
        require_attested_kis_nas_d1_volatility_trend_campaign_input(self.campaign_input)
        _require_review_status(self.review_status)
        if (
            _is_link_or_junction(self.precommit_path)
            or not self.precommit_path.is_file()
            or not _is_sha256(self.precommit_hash)
            or _sha256_file(self.precommit_path) != self.precommit_hash
        ):
            raise ValueError("NAS D1 volatility trend precommit is invalid")


def build_kis_nas_d1_volatility_trend_campaign(
    source_input: KisPaperDailyHistorySequenceInput,
) -> KisNasD1VolatilityTrendCampaignInput:
    """Freeze Data-owned feature rows and development-only after-cost labels."""

    require_attested_kis_paper_daily_history_sequence_input(source_input)
    adapter = _volatility_trend_data_adapter()
    data_input = adapter.build_kis_paper_daily_history_volatility_trend_input(source_input)
    adapter.require_attested_kis_paper_daily_history_volatility_trend_input(data_input)
    feature_contract = _feature_contract_from_adapter(adapter)
    contract = _build_contract(source_input, feature_contract)
    development = _build_development_samples(source_input, data_input, feature_contract)
    validation = _build_validation_samples(source_input, data_input, feature_contract)
    development_input_hash = _development_input_hash(development)
    validation_input_hash = _validation_input_hash(validation)
    thresholds = {
        symbol: _fit_development_threshold(
            symbol=symbol,
            samples=development[symbol],
            development_input_hash=_symbol_development_input_hash(symbol, development[symbol]),
        )
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    }
    result = object.__new__(KisNasD1VolatilityTrendCampaignInput)
    object.__setattr__(result, "contract", contract)
    object.__setattr__(result, "source_input_id", source_input.input_id)
    object.__setattr__(
        result,
        "source_targets_by_key",
        MappingProxyType(dict(source_input.source_targets_by_key)),
    )
    object.__setattr__(result, "source_limitations", tuple(source_input.raw_price_limitations))
    object.__setattr__(result, "development_sessions", source_input.development.common_sessions)
    object.__setattr__(result, "validation_sessions", source_input.validation.common_sessions)
    object.__setattr__(result, "development_samples_by_symbol", MappingProxyType(development))
    object.__setattr__(result, "validation_samples_by_symbol", MappingProxyType(validation))
    object.__setattr__(result, "thresholds_by_symbol", MappingProxyType(thresholds))
    object.__setattr__(result, "development_input_hash", development_input_hash)
    object.__setattr__(result, "validation_input_hash", validation_input_hash)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _CAMPAIGN_INPUT_ATTESTATION)
    require_attested_kis_nas_d1_volatility_trend_campaign_input(result)
    return result


def write_kis_nas_d1_volatility_trend_campaign_precommit(
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
    *,
    review_status: str,
    artifact_root: Path | str = KIS_NAS_D1_VOLATILITY_TREND_PRECOMMIT_ROOT,
    repo_root: Path | str | None = None,
) -> KisNasD1VolatilityTrendCampaignPrecommit:
    """Write or reattest the immutable source-safe precommit before fitting."""

    require_attested_kis_nas_d1_volatility_trend_campaign_input(campaign_input)
    _require_review_status(review_status)
    repository = _repository_root(repo_root)
    root = _external_output_root(artifact_root, repository)
    label = (
        "campaign="
        f"{campaign_input.contract.contract_hash.removeprefix('sha256:')[:20]}"
        f"-review={review_status}"
    )
    path = root / label / "precommit.json"
    payload = _precommit_payload(campaign_input, review_status=review_status)
    _assert_source_safe(payload)
    precommit_hash = _write_or_verify_json(path, payload, repository)
    return KisNasD1VolatilityTrendCampaignPrecommit(
        campaign_input=campaign_input,
        review_status=review_status,
        precommit_path=path,
        precommit_hash=precommit_hash,
    )


def calculate_kis_nas_d1_volatility_trend_campaign_precommit_hash(
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
    *,
    review_status: str,
) -> str:
    """Derive the exact precommit identity without writing an artifact."""

    require_attested_kis_nas_d1_volatility_trend_campaign_input(campaign_input)
    _require_review_status(review_status)
    payload = _precommit_payload(campaign_input, review_status=review_status)
    _assert_source_safe(payload)
    return _sha256_json(payload)


def _require_attested_campaign_input_identity(input: object) -> None:
    """Check immutable shell metadata without rehashing every feature row."""

    if (
        not isinstance(input, KisNasD1VolatilityTrendCampaignInput)
        or getattr(input, "_attestation", None) is not _CAMPAIGN_INPUT_ATTESTATION
        or input.schema_version != SCHEMA_VERSION
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
        or tuple(input.thresholds_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or not _is_sha256(input.development_input_hash)
        or not _is_sha256(input.validation_input_hash)
    ):
        raise ValueError("NAS D1 volatility trend campaign input requires a frozen contract")


def require_attested_kis_nas_d1_volatility_trend_campaign_input(input: object) -> None:
    """Fail closed before a new durable consumer trusts the campaign boundary."""

    _require_attested_campaign_input_identity(input)
    assert isinstance(input, KisNasD1VolatilityTrendCampaignInput)
    _require_contract_matches_input(input.contract, input)
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        development = input.development_samples_by_symbol[symbol]
        validation = input.validation_samples_by_symbol[symbol]
        threshold = input.thresholds_by_symbol[symbol]
        if (
            not development
            or not validation
            or any(
                not isinstance(sample, KisNasD1VolatilityTrendDevelopmentSample)
                for sample in development
            )
            or any(
                not isinstance(sample, KisNasD1VolatilityTrendValidationSample)
                for sample in validation
            )
            or not _samples_stay_inside_phase(
                development,
                input.development_sessions,
                expected_symbol=symbol,
                decision_stride=KIS_NAS_D1_VOLATILITY_TREND_DEVELOPMENT_DECISION_STRIDE,
                sequence_length=input.contract.features.sequence_length,
            )
            or not _samples_stay_inside_phase(
                validation,
                input.validation_sessions,
                expected_symbol=symbol,
                decision_stride=KIS_NAS_D1_VOLATILITY_TREND_EVALUATION_DECISION_STRIDE,
                sequence_length=input.contract.features.sequence_length,
            )
            or not isinstance(threshold, KisNasD1VolatilityTrendThreshold)
            or threshold.symbol != symbol
            or threshold.development_input_hash
            != _symbol_development_input_hash(symbol, development)
            or threshold
            != _fit_development_threshold(
                symbol=symbol,
                samples=development,
                development_input_hash=_symbol_development_input_hash(symbol, development),
            )
        ):
            raise ValueError("NAS D1 volatility trend campaign samples are invalid")
    if (
        input.development_input_hash
        != _development_input_hash(input.development_samples_by_symbol)
        or input.validation_input_hash
        != _validation_input_hash(input.validation_samples_by_symbol)
    ):
        raise ValueError("NAS D1 volatility trend campaign input hash is invalid")


def is_kis_nas_d1_volatility_trend_reference_long(
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
    sample: KisNasD1VolatilityTrendDevelopmentSample
    | KisNasD1VolatilityTrendValidationSample,
    *,
    comparator_id: str,
) -> bool:
    """Resolve a fixed reference decision without calculating PnL or ranking."""

    require_attested_kis_nas_d1_volatility_trend_campaign_input(campaign_input)
    if comparator_id not in KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS:
        raise ValueError("NAS D1 volatility trend comparator is unsupported")
    if sample.symbol not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 volatility trend comparator symbol is unsupported")
    threshold = campaign_input.threshold(sample.symbol).value
    if comparator_id == "flat":
        return False
    if comparator_id == "always_long":
        return True
    if comparator_id == "previous_bar_direction":
        return sample.feature_sequence[-1][0] > 0.0
    if comparator_id == "ungated_5d_trend":
        return sample.terminal_trend_5 > 0.0
    if comparator_id == "low_vol_only":
        return sample.terminal_realized_volatility_20 <= threshold
    return (
        sample.terminal_trend_5 > 0.0
        and sample.terminal_realized_volatility_20 <= threshold
    )


def _build_contract(
    source_input: KisPaperDailyHistorySequenceInput,
    features: KisNasD1VolatilityTrendFeatureContract,
) -> KisNasD1VolatilityTrendCampaignContract:
    development = source_input.development.common_sessions
    purge = source_input.purge.common_sessions
    validation = source_input.validation.common_sessions
    return KisNasD1VolatilityTrendCampaignContract(
        campaign_id=KIS_NAS_D1_VOLATILITY_TREND_CAMPAIGN_ID,
        panel_dataset_id=source_input.panel_dataset_id,
        panel_dataset_hash=source_input.panel_dataset_hash,
        index_hash=source_input.index_hash,
        split=KisNasD1VolatilityTrendSplit(
            development_start=development[0],
            development_end=development[-1],
            purge_start=purge[0],
            purge_end=purge[-1],
            validation_start=validation[0],
            validation_end=validation[-1],
        ),
        features=features,
        costs=CampaignCosts(
            fee_bps=KIS_NAS_D1_VOLATILITY_TREND_FEE_BPS_PER_FILL,
            slippage_bps=KIS_NAS_D1_VOLATILITY_TREND_SLIPPAGE_BPS_PER_FILL,
            slippage_source_id=KIS_NAS_D1_VOLATILITY_TREND_COST_SOURCE_ID,
        ),
        price_quantum=KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM,
        decimal_precision=KIS_NAS_D1_VOLATILITY_TREND_DECIMAL_PRECISION,
        rounding_mode=KIS_NAS_D1_VOLATILITY_TREND_ROUNDING_MODE,
        target=ExecutableTarget(),
        comparators=KIS_NAS_D1_VOLATILITY_TREND_COMPARATORS,
        development_decision_stride=KIS_NAS_D1_VOLATILITY_TREND_DEVELOPMENT_DECISION_STRIDE,
        evaluation_decision_stride=KIS_NAS_D1_VOLATILITY_TREND_EVALUATION_DECISION_STRIDE,
        previous_bar_direction_tie_rule=(
            KIS_NAS_D1_VOLATILITY_TREND_PREVIOUS_BAR_DIRECTION_TIE_RULE
        ),
        volatility_quantile=KIS_NAS_D1_VOLATILITY_TREND_QUANTILE,
        volatility_quantile_method=KIS_NAS_D1_VOLATILITY_TREND_QUANTILE_METHOD,
    )


def _build_development_samples(
    source_input: KisPaperDailyHistorySequenceInput,
    data_input: object,
    features: KisNasD1VolatilityTrendFeatureContract,
) -> dict[str, tuple[KisNasD1VolatilityTrendDevelopmentSample, ...]]:
    samples_by_symbol: dict[str, tuple[KisNasD1VolatilityTrendDevelopmentSample, ...]] = {}
    costs = _build_contract(source_input, features).costs
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        source_bars = source_input.development.stream(symbol).bars
        decision_indices = {bar.start_ts: index for index, bar in enumerate(source_bars)}
        samples: list[KisNasD1VolatilityTrendDevelopmentSample] = []
        for data_sample in data_input.development_samples(symbol):
            _require_data_sample_surface(data_sample)
            decision_index = decision_indices.get(data_sample.decision_start)
            if decision_index is None:
                raise ValueError("NAS D1 volatility trend development timing is invalid")
            if decision_index + ExecutableTarget().exit_bar_offset >= len(source_bars):
                continue
            samples.append(
                KisNasD1VolatilityTrendDevelopmentSample(
                    **_feature_sample_payload(data_sample, features),
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
    features: KisNasD1VolatilityTrendFeatureContract,
) -> dict[str, tuple[KisNasD1VolatilityTrendValidationSample, ...]]:
    samples_by_symbol: dict[str, tuple[KisNasD1VolatilityTrendValidationSample, ...]] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        source_bars = source_input.validation.stream(symbol).bars
        decision_indices = {bar.start_ts: index for index, bar in enumerate(source_bars)}
        samples: list[KisNasD1VolatilityTrendValidationSample] = []
        for data_sample in data_input.validation_samples(symbol):
            _require_data_sample_surface(data_sample)
            decision_index = decision_indices.get(data_sample.decision_start)
            if decision_index is None:
                raise ValueError("NAS D1 volatility trend validation timing is invalid")
            if (
                decision_index + ExecutableTarget().exit_bar_offset >= len(source_bars)
                or decision_index
                % KIS_NAS_D1_VOLATILITY_TREND_EVALUATION_DECISION_STRIDE
                != (KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1)
                % KIS_NAS_D1_VOLATILITY_TREND_EVALUATION_DECISION_STRIDE
            ):
                continue
            samples.append(
                KisNasD1VolatilityTrendValidationSample(
                    **_feature_sample_payload(data_sample, features)
                )
            )
        samples_by_symbol[symbol] = tuple(samples)
    return samples_by_symbol


def _feature_sample_payload(
    data_sample: object,
    features: KisNasD1VolatilityTrendFeatureContract,
) -> dict[str, object]:
    sequence = tuple(
        tuple(float(value) for value in row) for row in data_sample.feature_sequence
    )
    if (
        len(sequence) != features.sequence_length
        or any(len(row) != len(features.names) for row in sequence)
    ):
        raise ValueError("NAS D1 volatility trend feature sequence shape is invalid")
    return {
        "symbol": data_sample.symbol,
        "lookback_anchor_start": data_sample.lookback_anchor_start,
        "feature_start": data_sample.feature_start,
        "decision_start": data_sample.decision_start,
        "decision_end": data_sample.decision_end,
        "feature_sequence": sequence,
        "terminal_realized_volatility_20": float(
            data_sample.terminal_realized_volatility_20
        ),
        "terminal_trend_5": float(data_sample.terminal_trend_5),
    }


def _require_data_sample_surface(data_sample: object) -> None:
    required = (
        "symbol",
        "lookback_anchor_start",
        "feature_start",
        "decision_start",
        "decision_end",
        "feature_sequence",
        "terminal_realized_volatility_20",
        "terminal_trend_5",
    )
    prohibited = ("label", "entry_start", "exit_start", "entry_end", "exit_end")
    if any(not hasattr(data_sample, name) for name in required) or any(
        hasattr(data_sample, name) for name in prohibited
    ):
        raise ValueError("NAS D1 volatility trend Data sample surface is invalid")


def _fit_development_threshold(
    *,
    symbol: str,
    samples: Sequence[KisNasD1VolatilityTrendDevelopmentSample],
    development_input_hash: str,
) -> KisNasD1VolatilityTrendThreshold:
    values = sorted(sample.terminal_realized_volatility_20 for sample in samples)
    if not values:
        raise ValueError("NAS D1 volatility trend threshold has no development samples")
    position = (len(values) - 1) * KIS_NAS_D1_VOLATILITY_TREND_QUANTILE
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    value = values[lower] + (values[upper] - values[lower]) * fraction
    return KisNasD1VolatilityTrendThreshold(
        symbol=symbol,
        development_input_hash=development_input_hash,
        quantile=KIS_NAS_D1_VOLATILITY_TREND_QUANTILE,
        method=KIS_NAS_D1_VOLATILITY_TREND_QUANTILE_METHOD,
        value=value,
    )


def _after_cost_label(
    *,
    entry_bar: Bar,
    exit_bar: Bar,
    costs: CampaignCosts,
) -> int:
    """Mirror the fixed one-share local-paper target with no replay side effect."""

    if (
        entry_bar.start_ts.date() >= exit_bar.start_ts.date()
        or entry_bar.open <= 0
        or exit_bar.open <= 0
    ):
        raise ValueError("NAS D1 volatility trend target requires later observed opens")
    scale = Decimal("10000")
    with localcontext() as context:
        context.prec = KIS_NAS_D1_VOLATILITY_TREND_DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        entry_price = (
            entry_bar.open * (Decimal("1") + costs.slippage_bps / scale)
        ).quantize(KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
        exit_price = (
            exit_bar.open * (Decimal("1") - costs.slippage_bps / scale)
        ).quantize(KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM, rounding=ROUND_HALF_EVEN)
        entry_fee = (entry_price * costs.fee_bps / scale).quantize(
            KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM,
            rounding=ROUND_HALF_EVEN,
        )
        exit_fee = (exit_price * costs.fee_bps / scale).quantize(
            KIS_NAS_D1_VOLATILITY_TREND_PRICE_QUANTUM,
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
    terminal_realized_volatility_20: float,
    terminal_trend_5: float,
    schema_version: int,
) -> None:
    if (
        _resolve_symbol(symbol) != symbol
        or len(feature_sequence) != 20
        or any(len(row) != KIS_NAS_D1_VOLATILITY_TREND_FEATURE_COUNT for row in feature_sequence)
        or any(not math.isfinite(value) for row in feature_sequence for value in row)
        or not math.isfinite(terminal_realized_volatility_20)
        or terminal_realized_volatility_20 < 0.0
        or not math.isfinite(terminal_trend_5)
        or schema_version != SCHEMA_VERSION
        or not (
            lookback_anchor_start < feature_start
            and feature_start <= decision_start < decision_end
        )
    ):
        raise ValueError("NAS D1 volatility trend sample timing or feature geometry is invalid")


def _samples_stay_inside_phase(
    samples: Sequence[
        KisNasD1VolatilityTrendDevelopmentSample | KisNasD1VolatilityTrendValidationSample
    ],
    sessions: tuple[date, ...],
    *,
    expected_symbol: str,
    decision_stride: int,
    sequence_length: int,
) -> bool:
    if not samples or sequence_length <= 0:
        return False
    decision_dates = tuple(sample.decision_start.date() for sample in samples)
    expected_indices = tuple(
        range(
            KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS - 1,
            len(sessions) - ExecutableTarget().exit_bar_offset,
            decision_stride,
        )
    )
    if len(samples) != len(expected_indices):
        return False
    for sample, decision_index in zip(samples, expected_indices, strict=True):
        if (
            sample.symbol != expected_symbol
            or sample.lookback_anchor_start.date()
            != sessions[
                decision_index - KIS_NAS_D1_VOLATILITY_TREND_REQUIRED_BARS + 1
            ]
            or sample.feature_start.date()
            != sessions[decision_index - sequence_length + 1]
            or sample.decision_start.date() != sessions[decision_index]
        ):
            return False
    return tuple(sorted(decision_dates)) == decision_dates


def _require_contract_matches_input(
    contract: KisNasD1VolatilityTrendCampaignContract,
    input: KisNasD1VolatilityTrendCampaignInput,
) -> None:
    if (
        contract.split.development_start != input.development_sessions[0]
        or contract.split.development_end != input.development_sessions[-1]
        or contract.split.validation_start != input.validation_sessions[0]
        or contract.split.validation_end != input.validation_sessions[-1]
    ):
        raise ValueError("NAS D1 volatility trend campaign split does not match input")


def _precommit_payload(
    campaign_input: KisNasD1VolatilityTrendCampaignInput,
    *,
    review_status: str,
) -> dict[str, object]:
    contract = campaign_input.contract
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_nas_d1_volatility_trend_campaign_precommit",
        "status": "precommitted",
        "campaign_id": contract.campaign_id,
        "campaign_contract_hash": contract.contract_hash,
        "review_status": review_status,
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
                "feature_values_persisted": False,
            },
            "validation": {
                "input_hash": campaign_input.validation_input_hash,
                "sample_counts": {
                    symbol: len(samples)
                    for symbol, samples in campaign_input.validation_samples_by_symbol.items()
                },
                "labels_exposed": False,
                "feature_values_persisted": False,
            },
        },
        "development_volatility_thresholds": [
            campaign_input.threshold(symbol).safe_payload()
            for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        ],
        "model_packages": {
            "cpu_smoke": {
                "package_id": KIS_NAS_D1_VOLATILITY_TREND_CPU_SMOKE_ID,
                "models": ["per_symbol_l2_logistic"],
                "training_scope": "development_labels_only",
                "validation_scope": "target_free_predictions_only",
                "standardization": "per_symbol_development_only_per_channel",
            },
            "gpu_breadth": {
                "package_id": KIS_NAS_D1_VOLATILITY_TREND_GPU_BREADTH_ID,
                "architectures": ["lstm", "causal_tcn", "compact_attention"],
                "training_scope": "per_symbol_development_labels_only",
                "validation_scope": "target_free_predictions_only",
                "feature_shape": [contract.features.sequence_length, len(contract.features.names)],
                "candidate_count": len(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS) * 3,
            },
        },
        "compute_caps": {
            "cpu": {
                "steps": 160,
                "learning_rate": 0.08,
                "l2_penalty": 0.0001,
            },
            "cuda": {
                "epochs": 6,
                "batch_size": 128,
                "learning_rate": 0.001,
                "hidden_size": 16,
                "attention_heads": 4,
                "tcn_kernel_size": 3,
                "max_seconds_per_candidate": 120,
                "candidate_count": 18,
                "max_candidate_seconds_total": 2160,
            },
        },
        "strongest_kill_test": {
            "evaluation": "later_one_time_sealed_local_paper",
            "reference_comparator": "ungated_5d_trend",
            "paired_after_cost_aggregate_return": "strictly_improved_required",
            "max_drawdown": "not_worsened_required",
            "failure_outcome": "reject_volatility_gated_trend_hypothesis",
        },
        "scope": {
            "offline_only": True,
            "model_fitting_materialized": False,
            "prediction_materialized": False,
            "replay_materialized": False,
            "pnl_materialized": False,
            "ranking_eligible": False,
            "selection_eligible": False,
            "ensemble_eligible": False,
            "paper_decision_eligible": False,
            "live_eligible": False,
        },
        "artifact_policy": {
            "repository_storage_allowed": False,
            "immutable_write_only": True,
            "raw_rows_persisted": False,
            "feature_values_persisted": False,
            "numeric_thresholds_persisted": False,
            "target_values_persisted": False,
            "prediction_values_persisted": False,
            "event_rows_persisted": False,
            "model_weights_persisted": False,
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


def _feature_contract_from_adapter(adapter: object) -> KisNasD1VolatilityTrendFeatureContract:
    try:
        schema_id = adapter.KIS_NAS_D1_VOLATILITY_TREND_FEATURE_SCHEMA_ID
        names = adapter.KIS_NAS_D1_VOLATILITY_TREND_FEATURE_NAMES
        sequence_length = adapter.KIS_NAS_D1_VOLATILITY_TREND_SEQUENCE_LENGTH
    except AttributeError as exc:
        raise ValueError("NAS D1 volatility trend Data adapter constants are unavailable") from exc
    return KisNasD1VolatilityTrendFeatureContract(
        schema_id=str(schema_id),
        names=tuple(str(name) for name in names),
        sequence_length=int(sequence_length),
    )


def _volatility_trend_data_adapter() -> object:
    try:
        return importlib.import_module(_DATA_ADAPTER_MODULE)
    except ImportError as exc:
        raise RuntimeError("NAS D1 volatility trend Data adapter is unavailable") from exc


def _development_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisNasD1VolatilityTrendDevelopmentSample]],
) -> str:
    return _sha256_json(
        {
            "symbols": {
                symbol: [_sample_feature_hash_payload(sample) for sample in samples]
                for symbol, samples in samples_by_symbol.items()
            }
        }
    )


def _validation_input_hash(
    samples_by_symbol: Mapping[str, Sequence[KisNasD1VolatilityTrendValidationSample]],
) -> str:
    return _sha256_json(
        {
            "symbols": {
                symbol: [_sample_feature_hash_payload(sample) for sample in samples]
                for symbol, samples in samples_by_symbol.items()
            }
        }
    )


def _symbol_development_input_hash(
    symbol: str,
    samples: Sequence[KisNasD1VolatilityTrendDevelopmentSample],
) -> str:
    return _sha256_json(
        {
            "symbol": symbol,
            "samples": [_sample_feature_hash_payload(sample) for sample in samples],
        }
    )


def _sample_feature_hash_payload(
    sample: KisNasD1VolatilityTrendDevelopmentSample
    | KisNasD1VolatilityTrendValidationSample,
) -> dict[str, object]:
    return {
        "symbol": sample.symbol,
        "lookback_anchor_start": sample.lookback_anchor_start.isoformat(),
        "feature_start": sample.feature_start.isoformat(),
        "decision_start": sample.decision_start.isoformat(),
        "decision_end": sample.decision_end.isoformat(),
        "feature_sequence": [
            [format(value, ".17g") for value in row] for row in sample.feature_sequence
        ],
        "terminal_realized_volatility_20": format(
            sample.terminal_realized_volatility_20,
            ".17g",
        ),
        "terminal_trend_5": format(sample.terminal_trend_5, ".17g"),
    }


def _repository_root(repo_root: Path | str | None) -> Path:
    root = Path(repo_root) if repo_root is not None else _MODULE_REPOSITORY_ROOT
    if _is_link_or_junction(root) or not root.is_dir():
        raise ValueError("NAS D1 volatility trend repository root is invalid")
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
            raise FileExistsError("NAS D1 volatility trend precommit is immutable") from exc
    _reject_link_or_junction_components(path)
    return _sha256_file(path)


def _reject_repository_artifact_path(path: Path, repository: Path) -> None:
    if not path.is_relative_to(repository):
        return
    docker_repository = _DOCKER_REPOSITORY_ROOT.resolve()
    docker_artifact_root = _DOCKER_ARTIFACT_ROOT.resolve()
    if (
        repository == docker_repository
        and _DOCKER_ARTIFACT_ROOT.is_mount()
        and path.is_relative_to(docker_artifact_root)
    ):
        return
    raise ValueError("NAS D1 volatility trend artifacts must stay outside the Git workspace")


def _reject_link_or_junction_components(path: Path) -> None:
    current = Path(path)
    while True:
        if _is_link_or_junction(current):
            raise ValueError("NAS D1 volatility trend artifact path cannot contain a link")
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
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = "".join(character for character in str(key).lower() if character.isalnum())
            if normalized in forbidden:
                raise ValueError("NAS D1 volatility trend receipt contains unsafe value-level data")
            _assert_source_safe(nested)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for nested in value:
            _assert_source_safe(nested)


def _require_review_status(value: str) -> None:
    if value not in KIS_NAS_D1_VOLATILITY_TREND_ALLOWED_REVIEW_STATUSES:
        raise ValueError("NAS D1 volatility trend review status is invalid")


def _resolve_symbol(symbol: str) -> str:
    resolved = symbol.strip().upper()
    if resolved not in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        raise ValueError("NAS D1 volatility trend symbol is unsupported")
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

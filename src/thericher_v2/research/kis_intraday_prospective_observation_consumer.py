"""Pure preparation for the first fixed KIS intraday prospective observation.

The external adapter owns artifact I/O and local-paper replay.  This module
only binds injected, verified streams to deterministic models and replay plans.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data import (
    CatalogedBars,
    SessionWindow,
    prepare_kis_paper_intraday_feature_input,
)
from thericher_v2.data.kis_intraday_prospective_observation import (
    KisIntradayProspectiveObservationInput,
)
from thericher_v2.execution import LOCAL_PAPER_SOURCE

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from .kis_intraday_feature_breadth import (
    KIS_INTRADAY_FEATURE_M1_BARS,
    KIS_INTRADAY_FEATURE_M5_BARS,
    KIS_INTRADAY_FEATURE_M10_BARS,
    KIS_INTRADAY_FEATURE_NAMES,
    KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION,
    KIS_INTRADAY_FEATURE_SCHEMA_ID,
    KisIntradayFeatureSample,
    KisIntradayRegularizedLinearModel,
    build_kis_intraday_feature_samples,
    fit_kis_intraday_regularized_linear_samples,
)
from .kis_intraday_prospective_head_observation import (
    KIS_INTRADAY_PROSPECTIVE_HEAD_FEATURE_WINDOWS,
    KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES,
    KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
)

KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CONSUMER_ID = (
    "kis-intraday-prospective-observation-consumer-v1"
)
KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES = (
    "flat",
    "always_long",
    "previous_bar_direction",
    "regularized_linear",
)
KIS_INTRADAY_PROSPECTIVE_OBSERVATION_FEE_BPS = Decimal("1")
KIS_INTRADAY_PROSPECTIVE_OBSERVATION_SLIPPAGE_BPS = Decimal("2")
KisIntradayProspectiveObservationCandidateId = Literal[
    "flat",
    "always_long",
    "previous_bar_direction",
    "regularized_linear",
]


@dataclass(frozen=True)
class KisIntradayProspectivePreparationIdentity:
    """Safe metadata supplied by the upstream first-five-session preparation."""

    preparation_contract_hash: str
    precommit_hash: str
    artifact_slot_id: str
    selected_rows_fingerprint_sha256: str
    head_index_metadata_sha256: str
    selected_session_dates: tuple[date, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_session_dates", tuple(self.selected_session_dates))
        for field_name, value in (
            ("preparation_contract_hash", self.preparation_contract_hash),
            ("precommit_hash", self.precommit_hash),
            ("artifact_slot_id", self.artifact_slot_id),
            ("selected_rows_fingerprint_sha256", self.selected_rows_fingerprint_sha256),
            ("head_index_metadata_sha256", self.head_index_metadata_sha256),
        ):
            _require_sha256(value, field_name)
        _require_chronological_dates(
            self.selected_session_dates,
            "preparation selected_session_dates",
            expected_count=KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "preparation_contract_hash": self.preparation_contract_hash,
            "precommit_hash": self.precommit_hash,
            "artifact_slot_id": self.artifact_slot_id,
            "selected_rows_fingerprint_sha256": self.selected_rows_fingerprint_sha256,
            "head_index_metadata_sha256": self.head_index_metadata_sha256,
            "selected_session_dates": [
                session_date.isoformat() for session_date in self.selected_session_dates
            ],
        }


@dataclass(frozen=True)
class KisIntradayProspectiveCatalogIdentity:
    """A serializable Data-owned identity without a source path or raw bars."""

    dataset_id: str
    dataset_hash: str
    input_id: str
    input_hash: str
    session_dates: tuple[date, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_dates", tuple(self.session_dates))
        if not self.dataset_id.strip() or not self.input_id.strip():
            raise ValueError("prospective observation input identity is incomplete")
        _require_sha256(self.dataset_hash, "dataset_hash")
        _require_sha256(self.input_hash, "input_hash")
        _require_chronological_dates(self.session_dates, "input identity session_dates")

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "input_id": self.input_id,
            "input_hash": self.input_hash,
            "session_dates": [session_date.isoformat() for session_date in self.session_dates],
        }


@dataclass(frozen=True)
class KisIntradayProspectiveDecisionSample:
    """One prospective decision surface with labels intentionally omitted."""

    session_date: date
    session_window: SessionWindow
    decision_start: datetime
    decision_end: datetime
    history_start: datetime
    entry_start: datetime
    exit_start: datetime
    features: tuple[float, ...]
    m1_bar_count: int
    m5_bar_count: int
    m10_bar_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(self.features))
        if (
            type(self.session_date) is not date
            or not isinstance(self.session_window, SessionWindow)
        ):
            raise ValueError("prospective decision sample session is invalid")
        if len(self.features) != len(KIS_INTRADAY_FEATURE_NAMES):
            raise ValueError("prospective decision sample feature width is invalid")
        if (
            self.m1_bar_count != KIS_INTRADAY_FEATURE_M1_BARS
            or self.m5_bar_count != KIS_INTRADAY_FEATURE_M5_BARS
            or self.m10_bar_count != KIS_INTRADAY_FEATURE_M10_BARS
        ):
            raise ValueError("prospective decision sample feature geometry is invalid")
        if any(not math.isfinite(value) for value in self.features):
            raise ValueError("prospective decision sample feature values must be finite")
        if (
            self.history_start < self.session_window.open_ts
            or self.decision_start < self.session_window.open_ts
            or self.decision_end > self.session_window.close_ts
            or self.entry_start != self.decision_end
            or self.exit_start != self.entry_start + Timeframe.M1.duration
            or self.exit_start >= self.session_window.close_ts
        ):
            raise ValueError("prospective decision sample timing is invalid")

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "session_date": self.session_date.isoformat(),
            "history_start": self.history_start.isoformat(),
            "decision_start": self.decision_start.isoformat(),
            "decision_end": self.decision_end.isoformat(),
            "entry_start": self.entry_start.isoformat(),
            "exit_start": self.exit_start.isoformat(),
            "features": [format(value, ".17g") for value in self.features],
        }


@dataclass(frozen=True)
class KisIntradayProspectiveFrozenModelReceipt:
    """Immutable model-reuse binding for a later external-artifact adapter."""

    historical_input: KisIntradayProspectiveCatalogIdentity
    prospective_input: KisIntradayProspectiveCatalogIdentity
    preparation_identity: KisIntradayProspectivePreparationIdentity
    historical_sample_hash: str
    model_parameters_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.historical_input.session_dates
            != KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
        ):
            raise ValueError("frozen receipt historical session dates are invalid")
        if self.prospective_input.session_dates != self.preparation_identity.selected_session_dates:
            raise ValueError("frozen receipt prospective preparation identity is invalid")
        _require_sha256(self.historical_sample_hash, "historical_sample_hash")
        _require_sha256(self.model_parameters_hash, "model_parameters_hash")

    @property
    def receipt_hash(self) -> str:
        return _sha256_payload(self.to_payload())

    @property
    def payload(self) -> dict[str, object]:
        return self.to_payload()

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "observation_id": KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CONSUMER_ID,
            "feature_schema": {
                "id": KIS_INTRADAY_FEATURE_SCHEMA_ID,
                "names": list(KIS_INTRADAY_FEATURE_NAMES),
                "context": dict(KIS_INTRADAY_PROSPECTIVE_HEAD_FEATURE_WINDOWS),
                "same_session_only": True,
            },
            "historical_training": {
                "session_dates": [
                    session_date.isoformat()
                    for session_date in self.historical_input.session_dates
                ],
                "input": self.historical_input.to_payload(),
                "sample_hash": self.historical_sample_hash,
                "scope": "fixed_historical_development_only",
            },
            "prospective_evaluation": {
                "input": self.prospective_input.to_payload(),
                "preparation_identity": self.preparation_identity.to_payload(),
                "required_session_count": KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
            },
            "fitted_model_parameters_sha256": self.model_parameters_hash,
            "target": {
                "direction": "long_only",
                "decision": "completed_m1_bar_close",
                "entry": "next_m1_bar_open",
                "exit": "following_m1_bar_open",
                "cross_session_allowed": False,
            },
            "costs": {
                "fee_bps_per_side": str(KIS_INTRADAY_PROSPECTIVE_OBSERVATION_FEE_BPS),
                "slippage_bps_per_side": str(KIS_INTRADAY_PROSPECTIVE_OBSERVATION_SLIPPAGE_BPS),
            },
            "limits": {
                "model_training": "historical_only",
                "local_paper_replay_persisted": False,
                "candidate_selection": False,
                "profitability_conclusion": False,
            },
        }


@dataclass(frozen=True)
class KisIntradayProspectiveObservationCandidateModel:
    """PredictionModel-compatible candidate backed by prospective feature-only samples."""

    candidate_id: KisIntradayProspectiveObservationCandidateId
    samples_by_decision_end: Mapping[datetime, KisIntradayProspectiveDecisionSample]
    prospective_sample_hash: str
    frozen_model_receipt_hash: str
    linear_model: KisIntradayRegularizedLinearModel | None
    lookback: int = KIS_INTRADAY_FEATURE_M1_BARS - 1
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.candidate_id not in KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES:
            raise ValueError("prospective observation candidate is invalid")
        if self.candidate_id == "regularized_linear" and self.linear_model is None:
            raise ValueError("regularized_linear requires the frozen historical model")
        if self.candidate_id != "regularized_linear" and self.linear_model is not None:
            raise ValueError("only regularized_linear may receive fitted parameters")
        if self.lookback != KIS_INTRADAY_FEATURE_M1_BARS - 1:
            raise ValueError("prospective observation model lookback is fixed")
        _require_sha256(self.prospective_sample_hash, "prospective_sample_hash")
        _require_sha256(self.frozen_model_receipt_hash, "frozen_model_receipt_hash")
        samples = dict(self.samples_by_decision_end)
        if not samples or any(sample.decision_end != key for key, sample in samples.items()):
            raise ValueError("prospective observation sample map is invalid")
        object.__setattr__(self, "samples_by_decision_end", MappingProxyType(samples))

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < KIS_INTRADAY_FEATURE_M1_BARS:
            raise ValueError("prospective observation candidate requires 90 completed M1 bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        if sample is None:
            raise ValueError("prospective observation candidate received an unplanned decision")
        tail = tuple(bars[-KIS_INTRADAY_FEATURE_M1_BARS:])
        expected_starts = tuple(
            sample.history_start + Timeframe.M1.duration * index
            for index in range(KIS_INTRADAY_FEATURE_M1_BARS)
        )
        if (
            tuple(bar.start_ts for bar in tail) != expected_starts
            or tail[-1].end_ts != sample.decision_end
            or any(
                not bar.complete
                or bar.timeframe != Timeframe.M1
                or bar.start_ts < sample.session_window.open_ts
                or bar.end_ts > sample.session_window.close_ts
                for bar in tail
            )
        ):
            raise ValueError("prospective observation candidate cannot use cross-session history")

        action, confidence, metadata = self._decision(sample=sample, latest=latest)
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=f"kis_intraday_prospective_{self.candidate_id}",
            timeframe=Timeframe.M1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=f"kis_intraday_prospective_{self.candidate_id}",
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "candidate_id": self.candidate_id,
                "feature_schema_id": KIS_INTRADAY_FEATURE_SCHEMA_ID,
                "prospective_sample_hash": self.prospective_sample_hash,
                "frozen_model_receipt_hash": self.frozen_model_receipt_hash,
                "replay_fill_source": LOCAL_PAPER_SOURCE,
                **metadata,
            },
        )

    def _decision(
        self,
        *,
        sample: KisIntradayProspectiveDecisionSample,
        latest: Bar,
    ) -> tuple[Literal["buy", "hold"], Decimal, dict[str, object]]:
        if self.candidate_id == "flat":
            return "hold", Decimal("0"), {"decision_rule": "fixed_flat"}
        if self.candidate_id == "always_long":
            return "buy", Decimal("1"), {"decision_rule": "fixed_always_long"}
        if self.candidate_id == "previous_bar_direction":
            buy = latest.close > latest.open
            return (
                "buy" if buy else "hold",
                Decimal("1") if buy else Decimal("0"),
                {"decision_rule": "completed_bar_direction"},
            )
        assert self.linear_model is not None
        probability = self.linear_model.probability(sample.features)
        buy = probability >= self.linear_model.threshold
        return (
            "buy" if buy else "hold",
            Decimal(str(probability)),
            {
                "decision_rule": "fixed_regularized_linear_threshold",
                "threshold": self.linear_model.threshold,
            },
        )


@dataclass(frozen=True)
class KisIntradayProspectiveCandidateReplayPlan:
    """One non-persisted local-paper replay request for the later adapter."""

    candidate_id: KisIntradayProspectiveObservationCandidateId
    replay_id: str
    model: KisIntradayProspectiveObservationCandidateModel
    eligible_signal_starts: frozenset[datetime]
    allowed_session_windows: tuple[SessionWindow, ...]
    fill_source: str = LOCAL_PAPER_SOURCE
    campaign_phase: Literal["validation"] = "validation"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "eligible_signal_starts", frozenset(self.eligible_signal_starts))
        object.__setattr__(self, "allowed_session_windows", tuple(self.allowed_session_windows))
        if self.candidate_id != self.model.candidate_id or not self.replay_id.strip():
            raise ValueError("prospective candidate replay plan is invalid")
        if self.fill_source != LOCAL_PAPER_SOURCE:
            raise ValueError("prospective candidate replay requires local_paper")
        if not self.eligible_signal_starts or not self.allowed_session_windows:
            raise ValueError("prospective candidate replay windows are incomplete")
        expected_starts = frozenset(
            sample.decision_start for sample in self.model.samples_by_decision_end.values()
        )
        if self.eligible_signal_starts != expected_starts:
            raise ValueError("prospective candidate replay signal windows are invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "replay_id": self.replay_id,
            "fill_source": self.fill_source,
            "campaign_phase": self.campaign_phase,
            "eligible_decision_count": len(self.eligible_signal_starts),
        }


@dataclass(frozen=True)
class KisIntradayProspectiveObservationSummary:
    """Safe result projection that deliberately omits PnL and selection claims."""

    frozen_model_receipt_hash: str
    historical_session_dates: tuple[date, ...]
    prospective_session_dates: tuple[date, ...]
    prospective_sample_count: int
    candidate_ids: tuple[KisIntradayProspectiveObservationCandidateId, ...]
    fill_source: str = LOCAL_PAPER_SOURCE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "historical_session_dates", tuple(self.historical_session_dates))
        object.__setattr__(self, "prospective_session_dates", tuple(self.prospective_session_dates))
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        _require_sha256(self.frozen_model_receipt_hash, "frozen_model_receipt_hash")
        if (
            self.historical_session_dates
            != KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
            or len(self.prospective_session_dates)
            != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            or self.prospective_sample_count
            != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
            or self.candidate_ids != KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES
            or self.fill_source != LOCAL_PAPER_SOURCE
        ):
            raise ValueError("prospective observation summary is invalid")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": "prepared_for_external_local_paper_replay",
            "frozen_model_receipt_hash": self.frozen_model_receipt_hash,
            "historical_session_dates": [
                session_date.isoformat() for session_date in self.historical_session_dates
            ],
            "prospective_session_dates": [
                session_date.isoformat() for session_date in self.prospective_session_dates
            ],
            "prospective_sample_count": self.prospective_sample_count,
            "candidate_ids": list(self.candidate_ids),
            "fill_source": self.fill_source,
            "selection_allowed": False,
            "profitability_conclusion": False,
        }


@dataclass(frozen=True)
class KisIntradayProspectiveObservationConsumer:
    """Injected streams, frozen model, and replay plans with no external side effects."""

    campaign: CampaignContract
    historical_cataloged_bars: CatalogedBars
    prospective_cataloged_bars: CatalogedBars
    historical_input: KisIntradayProspectiveCatalogIdentity
    prospective_input: KisIntradayProspectiveCatalogIdentity
    frozen_linear_model: KisIntradayRegularizedLinearModel
    frozen_model_receipt: KisIntradayProspectiveFrozenModelReceipt
    prospective_samples: tuple[KisIntradayProspectiveDecisionSample, ...]
    candidate_replay_plans: tuple[KisIntradayProspectiveCandidateReplayPlan, ...]
    summary: KisIntradayProspectiveObservationSummary
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "prospective_samples", tuple(self.prospective_samples))
        object.__setattr__(self, "candidate_replay_plans", tuple(self.candidate_replay_plans))
        if self.historical_cataloged_bars is self.prospective_cataloged_bars:
            raise ValueError(
                "prospective observation requires separate historical and prospective streams"
            )
        if (
            self.campaign.catalog.dataset_id != self.prospective_cataloged_bars.dataset_id
            or self.campaign.catalog.dataset_hash != self.prospective_cataloged_bars.dataset_hash
            or self.historical_input.session_dates
            != KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES
            or self.prospective_input.session_dates
            != self.frozen_model_receipt.preparation_identity.selected_session_dates
            or len(self.prospective_samples)
            != KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT
            * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
            or tuple(item.candidate_id for item in self.candidate_replay_plans)
            != KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES
            or any(item.fill_source != LOCAL_PAPER_SOURCE for item in self.candidate_replay_plans)
            or self.summary.frozen_model_receipt_hash != self.frozen_model_receipt.receipt_hash
        ):
            raise ValueError("prospective observation consumer is invalid")


def build_kis_intraday_prospective_observation_consumer(
    *,
    observation_input: KisIntradayProspectiveObservationInput,
) -> KisIntradayProspectiveObservationConsumer:
    """Freeze history-only fitting and prepare five prospective local-paper replays."""

    if not isinstance(observation_input, KisIntradayProspectiveObservationInput):
        raise TypeError("prospective observation requires a verified Data input")
    historical_catalog = observation_input.historical_catalog
    prospective_catalog = observation_input.prospective_catalog
    historical_session_dates = observation_input.historical_session_dates
    prospective_session_dates = observation_input.prospective_session_dates
    preparation_identity = KisIntradayProspectivePreparationIdentity(
        preparation_contract_hash=observation_input.contract_hash,
        precommit_hash=observation_input.precommit_hash,
        artifact_slot_id=observation_input.artifact_slot_id,
        selected_rows_fingerprint_sha256=observation_input.selected_rows_fingerprint_sha256,
        head_index_metadata_sha256=observation_input.head_index_metadata_sha256,
        selected_session_dates=observation_input.prospective_session_dates,
    )
    _require_fixed_historical_dates(historical_session_dates)
    _require_prospective_dates(prospective_session_dates)
    if preparation_identity.selected_session_dates != prospective_session_dates:
        raise ValueError(
            "prospective preparation identity must match the selected prospective dates"
        )
    if historical_catalog is prospective_catalog:
        raise ValueError(
            "prospective observation requires separate historical and prospective streams"
        )

    historical_selected, historical_input, historical_windows = _prepare_verified_input(
        historical_catalog,
        session_dates=historical_session_dates,
        label="historical",
    )
    prospective_selected, prospective_input, prospective_windows = _prepare_verified_input(
        prospective_catalog,
        session_dates=prospective_session_dates,
        label="prospective",
    )
    historical_samples = _feature_samples(
        historical_selected,
        session_dates=historical_session_dates,
        session_windows=historical_windows,
        label="historical",
    )
    prospective_feature_samples = _feature_samples(
        prospective_selected,
        session_dates=prospective_session_dates,
        session_windows=prospective_windows,
        label="prospective",
    )
    frozen_linear_model = _fit_historical_model(
        historical_samples,
        historical_session_dates=historical_session_dates,
    )
    historical_sample_hash = _sha256_payload(
        {
            "kind": "kis_intraday_prospective_historical_training_samples_v1",
            "samples": [
                _historical_feature_sample_payload(sample) for sample in historical_samples
            ],
        }
    )
    prospective_samples = tuple(
        _prospective_decision_sample(sample) for sample in prospective_feature_samples
    )
    prospective_sample_hash = _sha256_payload(
        {
            "kind": "kis_intraday_prospective_decision_samples_v1",
            "samples": [sample._fingerprint_payload() for sample in prospective_samples],
        }
    )
    receipt = KisIntradayProspectiveFrozenModelReceipt(
        historical_input=historical_input,
        prospective_input=prospective_input,
        preparation_identity=preparation_identity,
        historical_sample_hash=historical_sample_hash,
        model_parameters_hash=_sha256_payload(frozen_linear_model.to_payload()),
    )
    campaign = _prospective_campaign(
        historical_input=historical_input,
        historical_windows=historical_windows,
        prospective_input=prospective_input,
        prospective_windows=prospective_windows,
    )
    samples_by_decision_end = {
        sample.decision_end: sample for sample in prospective_samples
    }
    if len(samples_by_decision_end) != len(prospective_samples):
        raise ValueError("prospective decision sample timestamps must be unique")
    candidate_models = tuple(
        KisIntradayProspectiveObservationCandidateModel(
            candidate_id=candidate_id,
            samples_by_decision_end=samples_by_decision_end,
            prospective_sample_hash=prospective_sample_hash,
            frozen_model_receipt_hash=receipt.receipt_hash,
            linear_model=(
                frozen_linear_model if candidate_id == "regularized_linear" else None
            ),
        )
        for candidate_id in KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES
    )
    eligible_signal_starts = frozenset(sample.decision_start for sample in prospective_samples)
    replay_plans = tuple(
        KisIntradayProspectiveCandidateReplayPlan(
            candidate_id=model.candidate_id,
            replay_id=_replay_id(model.candidate_id, receipt.receipt_hash),
            model=model,
            eligible_signal_starts=eligible_signal_starts,
            allowed_session_windows=prospective_windows,
        )
        for model in candidate_models
    )
    summary = KisIntradayProspectiveObservationSummary(
        frozen_model_receipt_hash=receipt.receipt_hash,
        historical_session_dates=historical_session_dates,
        prospective_session_dates=prospective_session_dates,
        prospective_sample_count=len(prospective_samples),
        candidate_ids=KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CANDIDATES,
    )
    return KisIntradayProspectiveObservationConsumer(
        campaign=campaign,
        historical_cataloged_bars=historical_selected,
        prospective_cataloged_bars=prospective_selected,
        historical_input=historical_input,
        prospective_input=prospective_input,
        frozen_linear_model=frozen_linear_model,
        frozen_model_receipt=receipt,
        prospective_samples=prospective_samples,
        candidate_replay_plans=replay_plans,
        summary=summary,
    )


def _prepare_verified_input(
    catalog: CatalogedBars,
    *,
    session_dates: tuple[date, ...],
    label: str,
) -> tuple[CatalogedBars, KisIntradayProspectiveCatalogIdentity, tuple[SessionWindow, ...]]:
    if not isinstance(catalog, CatalogedBars):
        raise TypeError(f"{label} prospective observation input requires CatalogedBars")
    prepared = prepare_kis_paper_intraday_feature_input(catalog, session_dates=session_dates)
    selected = prepared.catalog
    windows = prepared.session_windows
    if (
        prepared.session_dates != session_dates
        or len(windows) != len(session_dates)
        or any(not isinstance(window, SessionWindow) for window in windows)
        or any(
            bar.symbol != "QQQ" or bar.market != "US" or bar.timeframe != Timeframe.M1
            for bar in selected.bars
        )
    ):
        raise ValueError(f"{label} prospective observation input is invalid")
    return (
        selected,
        KisIntradayProspectiveCatalogIdentity(
            dataset_id=selected.dataset_id,
            dataset_hash=selected.dataset_hash,
            input_id=prepared.input_id,
            input_hash=prepared.input_hash,
            session_dates=prepared.session_dates,
        ),
        windows,
    )


def _feature_samples(
    catalog: CatalogedBars,
    *,
    session_dates: tuple[date, ...],
    session_windows: tuple[SessionWindow, ...],
    label: str,
) -> tuple[KisIntradayFeatureSample, ...]:
    samples = build_kis_intraday_feature_samples(
        catalog,
        session_dates=session_dates,
        session_windows=session_windows,
    )
    expected_count = len(session_dates) * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
    if (
        len(samples) != expected_count
        or {sample.session_date for sample in samples} != set(session_dates)
    ):
        raise ValueError(f"{label} prospective observation feature samples are incomplete")
    return samples


def _fit_historical_model(
    samples: tuple[KisIntradayFeatureSample, ...],
    *,
    historical_session_dates: tuple[date, ...],
) -> KisIntradayRegularizedLinearModel:
    if any(sample.session_date not in historical_session_dates for sample in samples):
        raise ValueError("historical fitting cannot consume prospective samples")
    return fit_kis_intraday_regularized_linear_samples(
        samples,
        development_session_dates=historical_session_dates,
    )


def _prospective_campaign(
    *,
    historical_input: KisIntradayProspectiveCatalogIdentity,
    historical_windows: tuple[SessionWindow, ...],
    prospective_input: KisIntradayProspectiveCatalogIdentity,
    prospective_windows: tuple[SessionWindow, ...],
) -> CampaignContract:
    return CampaignContract(
        campaign_id=KIS_INTRADAY_PROSPECTIVE_OBSERVATION_CONSUMER_ID,
        catalog=CatalogDatasetRef(
            catalog_id=f"{prospective_input.dataset_id}:prospective-observation",
            dataset_id=prospective_input.dataset_id,
            dataset_hash=prospective_input.dataset_hash,
            constructed_as_of_utc=prospective_windows[-1].close_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.M1,
        folds=(
            CampaignFold(
                "prospective-observation",
                CampaignWindow(historical_windows[0].open_ts, historical_windows[-1].close_ts),
                CampaignWindow(prospective_windows[0].open_ts, prospective_windows[-1].close_ts),
            ),
        ),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=KIS_INTRADAY_PROSPECTIVE_OBSERVATION_FEE_BPS,
            slippage_bps=KIS_INTRADAY_PROSPECTIVE_OBSERVATION_SLIPPAGE_BPS,
            slippage_source_id="kis-intraday-prospective-observation-costs-v1",
        ),
        purge=timedelta(minutes=1),
        embargo=timedelta(minutes=1),
        naive_baselines=("flat", "always_long", "previous_bar_direction"),
        deterministic_seed=71,
    )


def _prospective_decision_sample(
    sample: KisIntradayFeatureSample,
) -> KisIntradayProspectiveDecisionSample:
    return KisIntradayProspectiveDecisionSample(
        session_date=sample.session_date,
        session_window=sample.session_window,
        decision_start=sample.decision_start,
        decision_end=sample.decision_end,
        history_start=sample.history_start,
        entry_start=sample.entry_start,
        exit_start=sample.exit_start,
        features=sample.features,
        m1_bar_count=sample.m1_bar_count,
        m5_bar_count=sample.m5_bar_count,
        m10_bar_count=sample.m10_bar_count,
    )


def _historical_feature_sample_payload(sample: KisIntradayFeatureSample) -> dict[str, object]:
    return {
        "session_date": sample.session_date.isoformat(),
        "decision_end": sample.decision_end.isoformat(),
        "history_start": sample.history_start.isoformat(),
        "entry_start": sample.entry_start.isoformat(),
        "exit_start": sample.exit_start.isoformat(),
        "features": [format(value, ".17g") for value in sample.features],
        "target_return": format(sample.target_return, ".17g"),
        "target_label": sample.target_label,
    }


def _require_fixed_historical_dates(session_dates: tuple[date, ...]) -> None:
    if not isinstance(session_dates, tuple):
        raise TypeError("historical session_dates must be a date tuple")
    if session_dates != KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES:
        raise ValueError("historical session_dates must equal the fixed ten-session prefix")


def _require_prospective_dates(session_dates: tuple[date, ...]) -> None:
    _require_chronological_dates(
        session_dates,
        "prospective session_dates",
        expected_count=KIS_INTRADAY_PROSPECTIVE_HEAD_REQUIRED_SESSION_COUNT,
    )
    if session_dates[0] <= KIS_INTRADAY_PROSPECTIVE_HEAD_HISTORICAL_DEVELOPMENT_SESSION_DATES[-1]:
        raise ValueError("prospective session_dates must follow the fixed historical prefix")


def _require_chronological_dates(
    session_dates: tuple[date, ...],
    label: str,
    *,
    expected_count: int | None = None,
) -> None:
    if not isinstance(session_dates, tuple) or any(
        type(item) is not date for item in session_dates
    ):
        raise TypeError(f"{label} must be a date tuple")
    if (
        not session_dates
        or tuple(sorted(session_dates)) != session_dates
        or len(set(session_dates)) != len(session_dates)
    ):
        raise ValueError(f"{label} must be unique and chronological")
    if expected_count is not None and len(session_dates) != expected_count:
        raise ValueError(f"{label} must contain exactly {expected_count} sessions")


def _replay_id(
    candidate_id: KisIntradayProspectiveObservationCandidateId,
    frozen_model_receipt_hash: str,
) -> str:
    receipt_prefix = frozen_model_receipt_hash.removeprefix("sha256:")[:12]
    return f"kis-prospective-{candidate_id}-{receipt_prefix}"


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")

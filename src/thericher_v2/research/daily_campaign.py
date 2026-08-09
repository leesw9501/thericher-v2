"""Frozen development-only RAW D1 campaign for SPY, QQQ, and IWM."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Bar,
    ModelPrediction,
    Signal,
    Timeframe,
    require_utc,
)
from thericher_v2.data import (
    CatalogedBars,
    CatalogedCorporateActions,
    load_fixed_etf_daily_factor_change_dates,
)
from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE
from thericher_v2.state import EventStore

from .campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from .validation import (
    CampaignReplayRun,
    NaiveBaselineRun,
    run_campaign_model_replay,
    run_naive_cpu_baseline,
)

DAILY_SYMBOLS = ("SPY", "QQQ", "IWM")
DAILY_COMMON_SESSIONS = 896
DAILY_SHARED_MAX_LOOKBACK = 20
DAILY_SIGNAL_CADENCE = 2
DAILY_PURGE_SESSIONS = 2
DAILY_EMBARGO_SESSIONS = 2
DAILY_FEE_BPS = Decimal("10")
DAILY_SLIPPAGE_BPS = Decimal("5")
DAILY_SEED = 71
DAILY_THRESHOLD = 0.5
DAILY_HIDDEN_UNITS = 8
DAILY_LEARNING_RATE = 0.005
DAILY_WEIGHT_DECAY = 0.0001
DAILY_EPOCHS = 12
DAILY_MAX_TRAINING_RUNS = 6
_LEGACY_RAW_D1_CUDA_CONTRACTS = {
    (
        "raw-d1-development-20260718-cuda-r1",
        "us_equities.fixed_etf_daily.1d.snapshot=2026-07-18-r2",
        "sha256:3deaf812461d8d2619db3657f100521c293c5d5e7b460e82959b00c6e2a9875e",
    ): "sha256:abdd71954a4b04b1baa9b40fab89688a74dc524e0fd3f52291b6ca41eba34f78",
}

DailyScenario = Literal["primary", "factor_sensitivity"]
DailyFeatureSet = Literal["core", "pressure"]
DailySensitivityVerdict = Literal["unsupported", "supported-with-limits"]


@dataclass(frozen=True)
class DailyCatalogFacts:
    catalog_id: str
    constructed_as_of_utc: datetime
    development_training_eligible: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.catalog_id.strip():
            raise ValueError("catalog_id is required")
        object.__setattr__(
            self,
            "constructed_as_of_utc",
            require_utc(self.constructed_as_of_utc, "constructed_as_of_utc"),
        )
        if not self.development_training_eligible:
            raise ValueError("Data catalog must mark daily development training eligible")


@dataclass(frozen=True)
class DailyFoldSessions:
    fold_id: str
    development: tuple[datetime, ...]
    purge: tuple[datetime, ...]
    validation: tuple[datetime, ...]


@dataclass(frozen=True)
class DailyBoundaryProof:
    fold_id: str
    purge_sessions: tuple[datetime, ...]
    last_development_label_exit: datetime
    first_validation_entry: datetime


@dataclass(frozen=True)
class DailyExecutionTimingProof:
    signal_start: datetime
    entry_start: datetime
    exit_start: datetime
    signal_common_index: int
    entry_common_index: int
    exit_common_index: int


@dataclass(frozen=True)
class DailyCampaignPlan:
    contract: CampaignContract
    cataloged_bars: tuple[CatalogedBars, ...]
    factor_change_dates: tuple[tuple[date, ...], ...]
    common_sessions: tuple[datetime, ...]
    folds: tuple[DailyFoldSessions, ...]
    embargo_sessions: tuple[datetime, ...]
    boundary_proofs: tuple[DailyBoundaryProof, ...]
    schema_version: int = SCHEMA_VERSION

    def cataloged_for(self, symbol: str) -> CatalogedBars:
        resolved = symbol.upper()
        return self.cataloged_bars[DAILY_SYMBOLS.index(resolved)]

    def factor_dates_for(self, symbol: str) -> tuple[date, ...]:
        resolved = symbol.upper()
        return self.factor_change_dates[DAILY_SYMBOLS.index(resolved)]

    def fold_for(self, fold_id: str) -> DailyFoldSessions:
        for fold in self.folds:
            if fold.fold_id == fold_id:
                return fold
        raise ValueError(f"unknown daily fold_id: {fold_id}")

    def phase_bars(
        self,
        symbol: str,
        fold_id: str,
        phase: Literal["development", "validation"],
    ) -> tuple[Bar, ...]:
        sessions = getattr(self.fold_for(fold_id), phase)
        by_start = {bar.start_ts: bar for bar in self.cataloged_for(symbol).bars}
        return tuple(by_start[session] for session in sessions)

    def eligible_signal_starts(
        self,
        symbol: str,
        fold_id: str,
        phase: Literal["development", "validation"],
        *,
        scenario: DailyScenario,
    ) -> frozenset[datetime]:
        affected_dates = (
            frozenset(self.factor_dates_for(symbol))
            if scenario == "factor_sensitivity"
            else frozenset()
        )
        return eligible_daily_signal_starts_for_dates(
            self,
            symbol,
            fold_id,
            phase,
            affected_session_dates=affected_dates,
        )

    def execution_timing_proofs(
        self,
        symbol: str,
        fold_id: str,
        phase: Literal["development", "validation"],
        *,
        scenario: DailyScenario,
    ) -> tuple[DailyExecutionTimingProof, ...]:
        bars = self.phase_bars(symbol, fold_id, phase)
        eligible = self.eligible_signal_starts(
            symbol,
            fold_id,
            phase,
            scenario=scenario,
        )
        indices = tuple(
            index for index, bar in enumerate(bars) if bar.start_ts in eligible
        )
        return self._prove_execution_timing(bars, indices)

    def _prove_execution_timing(
        self,
        bars: tuple[Bar, ...],
        signal_indices: tuple[int, ...],
    ) -> tuple[DailyExecutionTimingProof, ...]:
        common_index = {
            session: index for index, session in enumerate(self.common_sessions)
        }
        proofs: list[DailyExecutionTimingProof] = []
        for signal_index in signal_indices:
            signal = bars[signal_index]
            entry = bars[signal_index + ExecutableTarget().entry_bar_offset]
            exit_bar = bars[signal_index + ExecutableTarget().exit_bar_offset]
            global_signal = common_index[signal.start_ts]
            global_entry = common_index[entry.start_ts]
            global_exit = common_index[exit_bar.start_ts]
            if global_entry != global_signal + 1 or global_exit != global_signal + 2:
                raise ValueError(
                    "daily entry and exit must be exact adjacent observed-session indices"
                )
            proofs.append(
                DailyExecutionTimingProof(
                    signal_start=signal.start_ts,
                    entry_start=entry.start_ts,
                    exit_start=exit_bar.start_ts,
                    signal_common_index=global_signal,
                    entry_common_index=global_entry,
                    exit_common_index=global_exit,
                )
            )
        return tuple(proofs)


def eligible_daily_signal_starts_for_dates(
    plan: DailyCampaignPlan,
    symbol: str,
    fold_id: str,
    phase: Literal["development", "validation"],
    *,
    affected_session_dates: frozenset[date],
) -> frozenset[datetime]:
    """Apply the frozen observed-session [i-20, i+2] exclusion window."""

    if not isinstance(affected_session_dates, frozenset) or any(
        type(value) is not date for value in affected_session_dates
    ):
        raise TypeError("affected_session_dates must be a frozenset of dates")
    bars = plan.phase_bars(symbol, fold_id, phase)
    indices = tuple(
        index
        for index in range(
            DAILY_SHARED_MAX_LOOKBACK,
            len(bars) - ExecutableTarget().exit_bar_offset,
            DAILY_SIGNAL_CADENCE,
        )
        if not any(
            bar.start_ts.date() in affected_session_dates
            for bar in bars[
                index - DAILY_SHARED_MAX_LOOKBACK : index
                + ExecutableTarget().exit_bar_offset
                + 1
            ]
        )
    )
    plan._prove_execution_timing(bars, indices)
    return frozenset(bars[index].start_ts for index in indices)


@dataclass(frozen=True)
class DailyCandidateSpec:
    candidate_id: str
    feature_set: DailyFeatureSet
    lookback: int
    hidden_units: int = DAILY_HIDDEN_UNITS
    activation: str = "relu"
    learning_rate: float = DAILY_LEARNING_RATE
    weight_decay: float = DAILY_WEIGHT_DECAY
    threshold: float = DAILY_THRESHOLD
    epochs: int = DAILY_EPOCHS
    seed: int = DAILY_SEED
    schema_version: int = SCHEMA_VERSION


DAILY_CANDIDATES = (
    DailyCandidateSpec("d1-core-lb5", "core", 5),
    DailyCandidateSpec("d1-core-lb20", "core", 20),
    DailyCandidateSpec("d1-pressure-lb20", "pressure", 20),
)


@dataclass(frozen=True)
class DailyTrainingSample:
    symbol: str
    signal_start: datetime
    entry_start: datetime
    exit_start: datetime
    features: tuple[float, ...]
    label: int
    after_cost_pnl: Decimal


@dataclass(frozen=True)
class DailyFeatureStandardization:
    fold_id: str
    development_start: datetime
    development_end: datetime
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    schema_version: int = SCHEMA_VERSION

    def transform(self, features: tuple[float, ...]) -> tuple[float, ...]:
        if len(features) != len(self.feature_names):
            raise ValueError("feature vector does not match frozen standardization")
        return tuple(
            (value - mean) / scale
            for value, mean, scale in zip(features, self.means, self.scales, strict=True)
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "fit_phase": "development",
            "fit_fold_id": self.fold_id,
            "development_start": self.development_start.isoformat(),
            "development_end": self.development_end.isoformat(),
            "feature_names": self.feature_names,
            "means": self.means,
            "scales": self.scales,
        }


@dataclass(frozen=True)
class DailyTrainingBatch:
    fold_id: str
    candidate: DailyCandidateSpec
    samples: tuple[DailyTrainingSample, ...]
    standardized_features: tuple[tuple[float, ...], ...]
    standardization: DailyFeatureStandardization
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class DailyReplayCell:
    kind: Literal["baseline", "candidate"]
    item_id: str
    symbol: str
    fold_id: str
    scenario: DailyScenario
    replay: NaiveBaselineRun | CampaignReplayRun


@dataclass(frozen=True)
class DailySensitivityCheck:
    verdict: DailySensitivityVerdict
    sign_changes: tuple[str, ...]
    candidate_order_changed: bool
    primary_candidate_order: tuple[str, ...]
    sensitivity_candidate_order: tuple[str, ...]
    relative_order_changed: bool
    all_item_primary_order: tuple[str, ...]
    all_item_sensitivity_order: tuple[str, ...]


@dataclass(frozen=True)
class DailyBaselineResult:
    cells: tuple[DailyReplayCell, ...]
    sensitivity: DailySensitivityCheck
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class DailyCandidateTraining:
    fold_id: str
    candidate: DailyCandidateSpec
    checkpoint_path: Path
    checkpoint_sha256: str
    examples_seen: int
    standardization: DailyFeatureStandardization
    trainer_metrics: dict[str, object]
    development_sample_policy: str = "factor_safe_for_both_validation_scenarios"
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class DailyCandidateResult:
    training: tuple[DailyCandidateTraining, ...]
    cells: tuple[DailyReplayCell, ...]
    sensitivity: DailySensitivityCheck
    summary_path: Path
    summary_sha256: str
    development_only: bool = True
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class DailyExplicitEventReplayCellPlan:
    kind: Literal["baseline", "candidate"]
    item_id: str
    symbol: str
    fold_id: str
    eligible_signal_starts: tuple[datetime, ...]
    checkpoint_path: Path | None = None
    checkpoint_sha256: str | None = None
    standardization: DailyFeatureStandardization | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class DailySourceSensitivityTarget:
    campaign_id: str
    campaign_contract_hash: str
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    source_path: Path
    common_sessions_sha256: str
    calendar_lineage: Literal["r2_inherited_exact_sessions"] = (
        "r2_inherited_exact_sessions"
    )
    price_basis: Literal["raw_ohlcv_only"] = "raw_ohlcv_only"
    explicit_action_handling: Literal["signal_mask_only_no_price_adjustment"] = (
        "signal_mask_only_no_price_adjustment"
    )
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.campaign_id.strip() or not self.dataset_id.strip():
            raise ValueError("source-sensitivity target identity is required")
        for value, label in (
            (self.campaign_contract_hash, "campaign contract hash"),
            (self.dataset_hash, "dataset hash"),
            (self.manifest_hash, "manifest hash"),
            (self.common_sessions_sha256, "common sessions hash"),
        ):
            _require_sha256(value, f"source-sensitivity target {label}")
        if self.calendar_lineage != "r2_inherited_exact_sessions":
            raise ValueError("source-sensitivity target calendar lineage is invalid")


@dataclass(frozen=True)
class DailyExplicitEventReplayPlan:
    replay_id: str
    source_campaign_id: str
    artifact_root: Path
    source_summary_path: Path
    source_summary_sha256: str
    corporate_action_dataset_id: str
    corporate_action_dataset_hash: str
    corporate_action_manifest_hash: str
    r2_dataset_id: str
    r2_dataset_hash: str
    r2_manifest_hash: str
    cells: tuple[DailyExplicitEventReplayCellPlan, ...]
    source_campaign_contract_hash: str
    source_sensitivity_target: DailySourceSensitivityTarget | None = None
    parent_sensitivity_verdict: Literal["unsupported"] = "unsupported"
    training_runs: int = 0
    development_only: bool = True
    retrospective_only: bool = True
    ranking: bool = False
    promotion: bool = False
    candidate_selection: bool = False
    sealed_holdout: bool = False
    profitability_claim: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.parent_sensitivity_verdict != "unsupported"
            or self.training_runs != 0
            or len(self.cells) != 36
        ):
            raise ValueError("explicit-event plan must freeze 36 replays and zero training")
        _require_sha256(self.source_campaign_contract_hash, "source campaign contract hash")


@dataclass(frozen=True)
class DailyExplicitEventReplayCellResult:
    cell: DailyExplicitEventReplayCellPlan
    replay: NaiveBaselineRun | CampaignReplayRun
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class DailyExplicitEventReplayResult:
    replay_plan: DailyExplicitEventReplayPlan
    cells: tuple[DailyExplicitEventReplayCellResult, ...]
    summary_path: Path
    summary_sha256: str
    execution_backend: Literal["torch_cpu"] = "torch_cpu"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.replay_plan.parent_sensitivity_verdict != "unsupported"
            or self.replay_plan.training_runs != 0
            or len(self.cells) != 36
        ):
            raise ValueError("explicit-event replay must preserve the frozen no-training contract")


DailyTrainer = Callable[
    [DailyCandidateSpec, DailyTrainingBatch, Path],
    dict[str, object],
]
DailyProbabilityPredictor = Callable[[tuple[float, ...]], float]
DailyInferenceFactory = Callable[
    [DailyCandidateSpec, Path, DailyFeatureStandardization],
    DailyProbabilityPredictor,
]


class _DailyCandidateModel:
    def __init__(
        self,
        candidate: DailyCandidateSpec,
        standardization: DailyFeatureStandardization,
        predictor: DailyProbabilityPredictor,
    ) -> None:
        self.candidate = candidate
        self.standardization = standardization
        self.predictor = predictor
        self.lookback = candidate.lookback

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        latest = bars[-1]
        raw_features = daily_feature_vector(bars, self.candidate)
        probability = self.predictor(self.standardization.transform(raw_features))
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("candidate probability must be finite and between zero and one")
        confidence = Decimal(str(probability))
        action = "buy" if probability >= self.candidate.threshold else "hold"
        return ModelPrediction(
            model_id=self.candidate.candidate_id,
            model_version="development-v1",
            symbol=latest.symbol,
            market=latest.market,
            signal=Signal(
                symbol=latest.symbol,
                market=latest.market,
                action=action,
                strength=confidence,
                reason="fixed_daily_candidate_threshold",
                timeframe=Timeframe.D1,
                generated_at=latest.end_ts,
            ),
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "candidate_id": self.candidate.candidate_id,
                "lookback": self.candidate.lookback,
                "feature_set": self.candidate.feature_set,
                "threshold": self.candidate.threshold,
                "development_only": True,
            },
        )


def build_daily_campaign_plan(
    cataloged_bars: tuple[CatalogedBars, ...],
    *,
    catalog_facts: DailyCatalogFacts,
    campaign_id: str = "raw-d1-development-v1",
) -> DailyCampaignPlan:
    """Freeze the latest 896 common observed sessions before any result is read."""

    _validate_safe_path_component(campaign_id, "campaign_id")
    if len(cataloged_bars) != len(DAILY_SYMBOLS):
        raise ValueError("daily campaign requires SPY, QQQ, and IWM in fixed order")
    symbols = tuple(item.bars[0].symbol for item in cataloged_bars)
    if symbols != DAILY_SYMBOLS:
        raise ValueError("daily campaign input order must be SPY, QQQ, IWM")
    first = cataloged_bars[0]
    for item in cataloged_bars:
        if item.dataset_id != first.dataset_id or item.dataset_hash != first.dataset_hash:
            raise ValueError("daily symbols must share one attested dataset identity")
        if item.source_path.resolve() != first.source_path.resolve():
            raise ValueError("daily symbols must come from the same attested RAW file")
        if any(bar.timeframe != Timeframe.D1 or not bar.complete for bar in item.bars):
            raise ValueError("daily campaign accepts only complete attested D1 Bars")

    common = set(bar.start_ts for bar in cataloged_bars[0].bars)
    for item in cataloged_bars[1:]:
        common.intersection_update(bar.start_ts for bar in item.bars)
    ordered_common = tuple(sorted(common))
    if len(ordered_common) < DAILY_COMMON_SESSIONS:
        raise ValueError(
            f"daily campaign requires at least {DAILY_COMMON_SESSIONS} common sessions"
        )
    selected = ordered_common[-DAILY_COMMON_SESSIONS:]
    selected_set = set(selected)
    for item in cataloged_bars:
        in_range = tuple(
            bar.start_ts
            for bar in item.bars
            if selected[0] <= bar.start_ts <= selected[-1]
        )
        if in_range != selected or set(in_range) != selected_set:
            raise ValueError("each symbol must have exactly the selected common sessions")

    fold1 = DailyFoldSessions(
        fold_id="fold-1",
        development=selected[0:252],
        purge=selected[252:254],
        validation=selected[254:317],
    )
    embargo = selected[317:319]
    fold2 = DailyFoldSessions(
        fold_id="fold-2",
        development=selected[319:831],
        purge=selected[831:833],
        validation=selected[833:896],
    )
    folds = (fold1, fold2)
    for fold in folds:
        _validate_safe_path_component(fold.fold_id, "fold_id")
    contract = CampaignContract(
        campaign_id=campaign_id,
        catalog=CatalogDatasetRef(
            catalog_id=catalog_facts.catalog_id,
            dataset_id=first.dataset_id,
            dataset_hash=first.dataset_hash,
            constructed_as_of_utc=catalog_facts.constructed_as_of_utc,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.D1,
        folds=tuple(
            CampaignFold(
                fold.fold_id,
                _window(fold.development),
                _window(fold.validation),
            )
            for fold in folds
        ),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=DAILY_FEE_BPS,
            slippage_bps=DAILY_SLIPPAGE_BPS,
            slippage_source_id="frozen-daily-development-costs-v1",
        ),
        purge=timedelta(days=DAILY_PURGE_SESSIONS),
        embargo=timedelta(days=DAILY_EMBARGO_SESSIONS),
        evidence_use="development",
        sealed_holdout=None,
        deterministic_seed=DAILY_SEED,
    )
    factors = tuple(
        load_fixed_etf_daily_factor_change_dates(
            item.source_path,
            expected_dataset_hash=item.dataset_hash,
            symbol=symbol,
        )
        for symbol, item in zip(DAILY_SYMBOLS, cataloged_bars, strict=True)
    )
    plan = DailyCampaignPlan(
        contract=contract,
        cataloged_bars=cataloged_bars,
        factor_change_dates=factors,
        common_sessions=selected,
        folds=folds,
        embargo_sessions=embargo,
        boundary_proofs=(),
    )
    proofs = prove_daily_campaign_boundaries(plan)
    completed_plan = DailyCampaignPlan(
        contract=plan.contract,
        cataloged_bars=plan.cataloged_bars,
        factor_change_dates=plan.factor_change_dates,
        common_sessions=plan.common_sessions,
        folds=plan.folds,
        embargo_sessions=plan.embargo_sessions,
        boundary_proofs=proofs,
    )
    for fold in completed_plan.folds:
        for symbol in DAILY_SYMBOLS:
            for phase in ("development", "validation"):
                for scenario in ("primary", "factor_sensitivity"):
                    completed_plan.execution_timing_proofs(
                        symbol,
                        fold.fold_id,
                        phase,
                        scenario=scenario,
                    )
    return completed_plan


def build_daily_source_sensitivity_replay_plan(
    source_plan: DailyCampaignPlan,
    replay_cataloged_bars: tuple[CatalogedBars, ...],
    *,
    replay_campaign_id: str,
) -> DailyCampaignPlan:
    """Bind one attested price representation to the frozen source schedule only."""

    _validate_safe_path_component(replay_campaign_id, "replay_campaign_id")
    if replay_campaign_id == source_plan.contract.campaign_id:
        raise ValueError("replay_campaign_id must differ from the source campaign_id")
    if len(replay_cataloged_bars) != len(DAILY_SYMBOLS):
        raise ValueError("source-sensitivity replay requires SPY, QQQ, and IWM in fixed order")
    symbols = tuple(item.bars[0].symbol for item in replay_cataloged_bars)
    if symbols != DAILY_SYMBOLS:
        raise ValueError("source-sensitivity replay input order must be SPY, QQQ, IWM")
    first = replay_cataloged_bars[0]
    for item in replay_cataloged_bars:
        if item.dataset_id != first.dataset_id or item.dataset_hash != first.dataset_hash:
            raise ValueError("source-sensitivity symbols must share one attested dataset")
        if item.source_path.resolve() != first.source_path.resolve():
            raise ValueError("source-sensitivity symbols must share one attested RAW file")
        if any(bar.timeframe != Timeframe.D1 or not bar.complete for bar in item.bars):
            raise ValueError("source-sensitivity replay accepts only complete attested D1 Bars")
        if tuple(bar.start_ts for bar in item.bars) != source_plan.common_sessions:
            raise ValueError(
                "source-sensitivity replay sessions must exactly match the source plan"
            )
    if (
        first.dataset_id == source_plan.contract.catalog.dataset_id
        and first.dataset_hash == source_plan.contract.catalog.dataset_hash
    ):
        raise ValueError("source-sensitivity replay input must differ from the source dataset")

    replay_catalog = CatalogDatasetRef(
        catalog_id=(
            f"{source_plan.contract.catalog.catalog_id}:source-sensitivity:"
            f"{first.dataset_hash.removeprefix('sha256:')[:16]}"
        ),
        dataset_id=first.dataset_id,
        dataset_hash=first.dataset_hash,
        constructed_as_of_utc=source_plan.contract.catalog.constructed_as_of_utc,
        ranking_eligible=False,
        sealed_holdout_eligible=False,
    )
    replay_contract = replace(
        source_plan.contract,
        campaign_id=replay_campaign_id,
        catalog=replay_catalog,
    )
    plan = DailyCampaignPlan(
        contract=replay_contract,
        cataloged_bars=replay_cataloged_bars,
        factor_change_dates=tuple(() for _ in DAILY_SYMBOLS),
        common_sessions=source_plan.common_sessions,
        folds=source_plan.folds,
        embargo_sessions=source_plan.embargo_sessions,
        boundary_proofs=(),
    )
    completed = replace(plan, boundary_proofs=prove_daily_campaign_boundaries(plan))
    _assert_source_sensitivity_replay_compatibility(source_plan, completed)
    for fold in completed.folds:
        for symbol in DAILY_SYMBOLS:
            for phase in ("development", "validation"):
                for scenario in ("primary", "factor_sensitivity"):
                    completed.execution_timing_proofs(
                        symbol,
                        fold.fold_id,
                        phase,
                        scenario=scenario,
                    )
    return completed


def _assert_source_sensitivity_replay_compatibility(
    source_plan: DailyCampaignPlan,
    replay_plan: DailyCampaignPlan,
) -> None:
    if (
        source_plan.common_sessions != replay_plan.common_sessions
        or source_plan.folds != replay_plan.folds
        or source_plan.embargo_sessions != replay_plan.embargo_sessions
        or source_plan.boundary_proofs != replay_plan.boundary_proofs
    ):
        raise ValueError("source-sensitivity replay must retain the source session schedule")
    source_contract = source_plan.contract.to_payload()
    replay_contract = replay_plan.contract.to_payload()
    for payload in (source_contract, replay_contract):
        payload.pop("campaign_id")
        payload.pop("catalog")
    if source_contract != replay_contract:
        raise ValueError("source-sensitivity replay must retain source timing and costs")
    if any(replay_plan.factor_dates_for(symbol) for symbol in DAILY_SYMBOLS):
        raise ValueError("source-sensitivity replay cannot apply target factor diagnostics")


def _resolve_replay_input_manifest_hash(
    plan: DailyCampaignPlan,
    expected_manifest_hash: str | None,
    *,
    label: str = "explicit-event replay input",
) -> str:
    manifest_path = plan.cataloged_bars[0].source_path.resolve().parent / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError(f"{label} manifest cannot be a symlink")
    try:
        actual_manifest_hash = _sha256_file(manifest_path)
    except OSError as exc:
        raise ValueError(f"{label} manifest is not readable") from exc
    if expected_manifest_hash is None:
        return actual_manifest_hash
    _require_sha256(expected_manifest_hash, f"{label} manifest SHA-256")
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError(f"{label} manifest SHA-256 mismatch")
    return expected_manifest_hash


def _source_sensitivity_target(
    target_plan: DailyCampaignPlan,
    expected_manifest_hash: str | None,
) -> DailySourceSensitivityTarget:
    if expected_manifest_hash is None:
        raise ValueError("source-sensitivity replay requires the target manifest SHA-256")
    return DailySourceSensitivityTarget(
        campaign_id=target_plan.contract.campaign_id,
        campaign_contract_hash=target_plan.contract.contract_hash,
        dataset_id=target_plan.contract.catalog.dataset_id,
        dataset_hash=target_plan.contract.catalog.dataset_hash,
        manifest_hash=_resolve_replay_input_manifest_hash(
            target_plan,
            expected_manifest_hash,
            label="target",
        ),
        source_path=target_plan.cataloged_bars[0].source_path.resolve(),
        common_sessions_sha256=_daily_sessions_sha256(target_plan.common_sessions),
    )


def _assert_replay_target_matches_plan(
    replay_plan: DailyExplicitEventReplayPlan,
    target_plan: DailyCampaignPlan,
    target_requested: bool,
) -> None:
    target = replay_plan.source_sensitivity_target
    if not target_requested:
        if target is not None:
            raise ValueError("explicit-event plan unexpectedly declares a replay target")
        return
    if target is None or (
        target.campaign_id != target_plan.contract.campaign_id
        or target.campaign_contract_hash != target_plan.contract.contract_hash
        or target.dataset_id != target_plan.contract.catalog.dataset_id
        or target.dataset_hash != target_plan.contract.catalog.dataset_hash
        or target.source_path != target_plan.cataloged_bars[0].source_path.resolve()
        or target.common_sessions_sha256
        != _daily_sessions_sha256(target_plan.common_sessions)
    ):
        raise ValueError("explicit-event plan does not match the replay target")


def _daily_sessions_sha256(sessions: tuple[datetime, ...]) -> str:
    return _sha256_bytes("\n".join(value.isoformat() for value in sessions).encode("utf-8"))


def prove_daily_campaign_boundaries(
    plan: DailyCampaignPlan,
) -> tuple[DailyBoundaryProof, ...]:
    blocks = (
        plan.folds[0].development,
        plan.folds[0].purge,
        plan.folds[0].validation,
        plan.embargo_sessions,
        plan.folds[1].development,
        plan.folds[1].purge,
        plan.folds[1].validation,
    )
    expected_lengths = (252, 2, 63, 2, 512, 2, 63)
    if tuple(len(block) for block in blocks) != expected_lengths:
        raise ValueError("daily campaign block sizes do not match the frozen 896-session split")
    flattened = tuple(session for block in blocks for session in block)
    if flattened != plan.common_sessions or len(set(flattened)) != len(flattened):
        raise ValueError("daily campaign blocks must be disjoint, complete, and forward")
    if len(plan.embargo_sessions) != DAILY_EMBARGO_SESSIONS:
        raise ValueError("daily campaign requires exactly two observed embargo sessions")

    proofs: list[DailyBoundaryProof] = []
    for fold in plan.folds:
        if len(fold.purge) != DAILY_PURGE_SESSIONS:
            raise ValueError("daily campaign requires exactly two observed purge sessions")
        development_signal_index = tuple(
            range(
                DAILY_SHARED_MAX_LOOKBACK,
                len(fold.development) - ExecutableTarget().exit_bar_offset,
                DAILY_SIGNAL_CADENCE,
            )
        )[-1]
        validation_signal_index = DAILY_SHARED_MAX_LOOKBACK
        last_label_exit = fold.development[
            development_signal_index + ExecutableTarget().exit_bar_offset
        ]
        first_validation_entry = fold.validation[
            validation_signal_index + ExecutableTarget().entry_bar_offset
        ]
        if last_label_exit >= first_validation_entry:
            raise ValueError("development labels must finish before validation evidence starts")
        proofs.append(
            DailyBoundaryProof(
                fold_id=fold.fold_id,
                purge_sessions=fold.purge,
                last_development_label_exit=last_label_exit,
                first_validation_entry=first_validation_entry,
            )
        )
    return tuple(proofs)


def prepare_daily_explicit_event_replay(
    source_plan: DailyCampaignPlan,
    *,
    replay_target_plan: DailyCampaignPlan | None = None,
    corporate_actions: CatalogedCorporateActions,
    source_summary_path: Path,
    expected_source_summary_sha256: str,
    replay_id: str,
    artifact_root: Path,
    replay_target_manifest_hash: str | None = None,
    repo_root: Path | None = None,
) -> DailyExplicitEventReplayPlan:
    """Freeze target bars against source checkpoints without retraining either."""

    if not isinstance(corporate_actions, CatalogedCorporateActions):
        raise TypeError("corporate_actions must be CatalogedCorporateActions")
    target = replay_target_plan or source_plan
    if replay_target_plan is not None:
        _assert_source_sensitivity_replay_compatibility(source_plan, target)
    _validate_safe_path_component(replay_id, "replay_id")
    if replay_id == source_plan.contract.campaign_id:
        raise ValueError("replay_id must differ from the source campaign_id")
    resolved_root = artifact_root.resolve()
    _reject_repo_path(resolved_root, repo_root or Path.cwd())
    if Path(artifact_root).is_symlink():
        raise ValueError("artifact_root cannot be a symlink")
    source_campaign_dir = _contained_artifact_path(
        resolved_root,
        "daily-campaign",
        source_plan.contract.campaign_id,
    )
    expected_summary_path = source_campaign_dir / "summary.json"
    supplied_summary_path = Path(source_summary_path)
    if (
        not supplied_summary_path.is_absolute()
        or supplied_summary_path != expected_summary_path
        or supplied_summary_path.is_symlink()
    ):
        raise ValueError("source summary must be the exact non-symlink campaign summary")
    _assert_no_symlink_artifact_components(
        resolved_root, ("daily-campaign", source_plan.contract.campaign_id, "summary.json")
    )
    corporate_actions.assert_replay_eligible()
    _assert_corporate_action_r2_lineage(source_plan, corporate_actions)
    _assert_corporate_action_event_membership(target, corporate_actions)
    summary_path = supplied_summary_path
    _require_sha256(expected_source_summary_sha256, "source summary SHA-256")
    try:
        summary_bytes = summary_path.read_bytes()
    except OSError as exc:
        raise ValueError("source CUDA summary is not readable") from exc
    if _sha256_bytes(summary_bytes) != expected_source_summary_sha256:
        raise ValueError("source CUDA summary SHA-256 mismatch")
    try:
        summary = json.loads(summary_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("source CUDA summary must be valid UTF-8 JSON") from exc
    if not isinstance(summary, dict):
        raise ValueError("source CUDA summary must be a JSON object")
    source_campaign_contract_hash = _assert_source_summary_contract(source_plan, summary)
    checkpoints = _source_checkpoint_contracts(
        source_plan,
        summary.get("checkpoints"),
        artifact_root=resolved_root,
    )
    for fold in source_plan.folds:
        for candidate in DAILY_CANDIDATES:
            checkpoint_path, _, standardization = checkpoints[
                (fold.fold_id, candidate.candidate_id)
            ]
            _validate_daily_torch_checkpoint_cpu(
                candidate,
                checkpoint_path,
                standardization,
            )
    affected_dates = {
        symbol: corporate_actions.affected_session_dates(symbol)
        for symbol in DAILY_SYMBOLS
    }
    cells: list[DailyExplicitEventReplayCellPlan] = []
    for fold in target.folds:
        for symbol in DAILY_SYMBOLS:
            eligible = tuple(
                sorted(
                    eligible_daily_signal_starts_for_dates(
                        target,
                        symbol,
                        fold.fold_id,
                        "validation",
                        affected_session_dates=affected_dates[symbol],
                    )
                )
            )
            for baseline_id in target.contract.naive_baselines:
                cells.append(
                    DailyExplicitEventReplayCellPlan(
                        kind="baseline",
                        item_id=baseline_id,
                        symbol=symbol,
                        fold_id=fold.fold_id,
                        eligible_signal_starts=eligible,
                    )
                )
        for candidate in DAILY_CANDIDATES:
            checkpoint_path, checkpoint_hash, standardization = checkpoints[
                (fold.fold_id, candidate.candidate_id)
            ]
            for symbol in DAILY_SYMBOLS:
                eligible = tuple(
                    sorted(
                        eligible_daily_signal_starts_for_dates(
                            target,
                            symbol,
                            fold.fold_id,
                            "validation",
                            affected_session_dates=affected_dates[symbol],
                        )
                    )
                )
                cells.append(
                    DailyExplicitEventReplayCellPlan(
                        kind="candidate",
                        item_id=candidate.candidate_id,
                        symbol=symbol,
                        fold_id=fold.fold_id,
                        eligible_signal_starts=eligible,
                        checkpoint_path=checkpoint_path,
                        checkpoint_sha256=checkpoint_hash,
                        standardization=standardization,
                    )
                )
    return DailyExplicitEventReplayPlan(
        replay_id=replay_id,
        source_campaign_id=source_plan.contract.campaign_id,
        artifact_root=resolved_root,
        source_summary_path=summary_path,
        source_summary_sha256=expected_source_summary_sha256,
        corporate_action_dataset_id=corporate_actions.dataset_id,
        corporate_action_dataset_hash=corporate_actions.dataset_hash,
        corporate_action_manifest_hash=corporate_actions.manifest_hash,
        r2_dataset_id=corporate_actions.r2_dataset_id,
        r2_dataset_hash=corporate_actions.r2_dataset_hash,
        r2_manifest_hash=corporate_actions.r2_manifest_hash,
        cells=tuple(cells),
        source_campaign_contract_hash=source_campaign_contract_hash,
        source_sensitivity_target=(
            _source_sensitivity_target(target, replay_target_manifest_hash)
            if replay_target_plan is not None
            else None
        ),
    )


def run_daily_explicit_event_replay(
    source_plan: DailyCampaignPlan,
    *,
    replay_target_plan: DailyCampaignPlan | None = None,
    replay_plan: DailyExplicitEventReplayPlan,
    artifact_root: Path,
    work_root: Path,
    repo_root: Path | None = None,
) -> DailyExplicitEventReplayResult:
    """Execute the already frozen explicit-event cells through local paper only."""

    target = replay_target_plan or source_plan
    if replay_target_plan is not None:
        _assert_source_sensitivity_replay_compatibility(source_plan, target)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, resolved_repo_root)
    if Path(artifact_root).is_symlink():
        raise ValueError("explicit-event artifact_root cannot be a symlink")
    if replay_plan.artifact_root != resolved_artifact_root:
        raise ValueError("explicit-event plan artifact_root does not match execution root")
    if replay_plan.source_campaign_id != source_plan.contract.campaign_id:
        raise ValueError("explicit-event plan does not match the source campaign")
    _assert_replay_target_matches_plan(replay_plan, target, replay_target_plan is not None)
    if replay_plan.source_summary_path.is_symlink():
        raise ValueError("explicit-event source summary cannot be a symlink")
    _assert_artifact_hash(
        replay_plan.source_summary_path,
        replay_plan.source_summary_sha256,
        "explicit-event source summary",
    )
    try:
        source_summary = json.loads(replay_plan.source_summary_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("explicit-event source summary is not valid UTF-8 JSON") from exc
    if _assert_source_summary_contract(source_plan, source_summary) != (
        replay_plan.source_campaign_contract_hash
    ):
        raise ValueError("explicit-event plan source contract hash does not match")
    _assert_artifact_hash(
        target.cataloged_bars[0].source_path,
        target.contract.catalog.dataset_hash,
        "explicit-event replay input",
    )
    if replay_plan.source_sensitivity_target is not None:
        _resolve_replay_input_manifest_hash(
            target,
            replay_plan.source_sensitivity_target.manifest_hash,
            label="target",
        )
    _assert_explicit_event_replay_plan(target, replay_plan)

    expected_work_root = _contained_artifact_path(
        resolved_artifact_root,
        "daily-campaign",
        replay_plan.replay_id,
    )
    if Path(work_root).resolve() != expected_work_root:
        raise ValueError("explicit-event work_root must be the declared replay artifact directory")
    if expected_work_root.exists():
        raise FileExistsError(f"explicit-event replay target already exists: {expected_work_root}")

    run_ids = tuple(
        _explicit_event_run_id(target, replay_plan, cell) for cell in replay_plan.cells
    )
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("explicit-event replay cell run ids must be unique")
    for run_id in run_ids:
        artifact_path = resolved_artifact_root / "validation" / f"{run_id}.json"
        if artifact_path.exists():
            raise FileExistsError(
                f"explicit-event validation artifact already exists: {artifact_path}"
            )

    predictors = _explicit_event_cpu_predictors(source_plan, replay_plan)
    cells: list[DailyExplicitEventReplayCellResult] = []
    for cell in replay_plan.cells:
        run_id = _explicit_event_run_id(target, replay_plan, cell)
        work_dir = (
            expected_work_root
            / cell.fold_id
            / cell.kind
            / cell.item_id
            / cell.symbol.lower()
        )
        eligible_signal_starts = frozenset(cell.eligible_signal_starts)
        if cell.kind == "baseline":
            replay = run_naive_cpu_baseline(
                target.cataloged_for(cell.symbol),
                campaign=target.contract,
                artifact_root=resolved_artifact_root,
                work_dir=work_dir,
                phase="validation",
                fold_id=cell.fold_id,
                baseline_id=cell.item_id,
                repo_root=resolved_repo_root,
                run_label=_explicit_event_baseline_label(replay_plan.replay_id, cell.symbol),
                eligible_signal_starts=eligible_signal_starts,
            )
        else:
            candidate, standardization, predictor = predictors[(cell.fold_id, cell.item_id)]
            replay = run_campaign_model_replay(
                target.cataloged_for(cell.symbol),
                campaign=target.contract,
                model=_DailyCandidateModel(candidate, standardization, predictor),
                run_id=run_id,
                artifact_root=resolved_artifact_root,
                work_dir=work_dir,
                phase="validation",
                fold_id=cell.fold_id,
                repo_root=resolved_repo_root,
                eligible_signal_starts=eligible_signal_starts,
                emergency_reason="explicit_event_replay_initial_state",
            )
        result = DailyExplicitEventReplayCellResult(cell=cell, replay=replay)
        _assert_explicit_event_replay_evidence(result)
        cells.append(result)

    if len(cells) != 36:
        raise RuntimeError("explicit-event replay must execute exactly 36 frozen cells")
    summary_path = _write_daily_explicit_event_replay_summary(
        replay_plan,
        tuple(cells),
        path=expected_work_root / "summary.json",
    )
    return DailyExplicitEventReplayResult(
        replay_plan=replay_plan,
        cells=tuple(cells),
        summary_path=summary_path,
        summary_sha256=_sha256_file(summary_path),
    )


def _assert_explicit_event_replay_plan(
    plan: DailyCampaignPlan,
    replay_plan: DailyExplicitEventReplayPlan,
) -> None:
    if (
        replay_plan.parent_sensitivity_verdict != "unsupported"
        or replay_plan.training_runs != 0
        or replay_plan.ranking
        or replay_plan.promotion
        or replay_plan.candidate_selection
        or replay_plan.sealed_holdout
        or replay_plan.profitability_claim
    ):
        raise ValueError(
            "explicit-event replay must remain development-only with parent unsupported"
        )
    baseline_cells = tuple(cell for cell in replay_plan.cells if cell.kind == "baseline")
    candidate_cells = tuple(cell for cell in replay_plan.cells if cell.kind == "candidate")
    if len(baseline_cells) != 18 or len(candidate_cells) != 18:
        raise ValueError("explicit-event replay must contain 18 baseline and 18 candidate cells")
    for cell in replay_plan.cells:
        known_folds = {fold.fold_id for fold in plan.folds}
        if cell.symbol not in DAILY_SYMBOLS or cell.fold_id not in known_folds:
            raise ValueError("explicit-event replay cell has an unknown symbol or fold")
        if tuple(sorted(cell.eligible_signal_starts)) != cell.eligible_signal_starts:
            raise ValueError("explicit-event eligible signal starts must be sorted")
        if len(set(cell.eligible_signal_starts)) != len(cell.eligible_signal_starts):
            raise ValueError("explicit-event eligible signal starts must be unique")
        if cell.kind == "baseline":
            if (
                cell.item_id not in plan.contract.naive_baselines
                or cell.checkpoint_path is not None
                or cell.checkpoint_sha256 is not None
                or cell.standardization is not None
            ):
                raise ValueError("explicit-event baseline cell is malformed")
        elif cell.item_id not in {candidate.candidate_id for candidate in DAILY_CANDIDATES}:
            raise ValueError("explicit-event candidate cell is malformed")


def _explicit_event_cpu_predictors(
    plan: DailyCampaignPlan,
    replay_plan: DailyExplicitEventReplayPlan,
) -> dict[
    tuple[str, str],
    tuple[DailyCandidateSpec, DailyFeatureStandardization, DailyProbabilityPredictor],
]:
    predictors: dict[
        tuple[str, str],
        tuple[DailyCandidateSpec, DailyFeatureStandardization, DailyProbabilityPredictor],
    ] = {}
    checkpoint_contracts: dict[
        tuple[str, str], tuple[Path, str, DailyFeatureStandardization]
    ] = {}
    for cell in replay_plan.cells:
        if cell.kind != "candidate":
            continue
        if (
            cell.checkpoint_path is None
            or cell.checkpoint_sha256 is None
            or cell.standardization is None
        ):
            raise ValueError("explicit-event candidate checkpoint contract is incomplete")
        candidate = _daily_candidate_for_id(cell.item_id)
        _assert_artifact_hash(
            cell.checkpoint_path,
            cell.checkpoint_sha256,
            "explicit-event source checkpoint",
        )
        _assert_fold_local_standardization(plan, cell.fold_id, cell.standardization)
        key = (cell.fold_id, cell.item_id)
        contract = (cell.checkpoint_path, cell.checkpoint_sha256, cell.standardization)
        prior_contract = checkpoint_contracts.get(key)
        if prior_contract is not None:
            if prior_contract != contract:
                raise ValueError("explicit-event candidate checkpoint contract is inconsistent")
            continue
        checkpoint_contracts[key] = contract
        predictors[key] = (
            candidate,
            cell.standardization,
            load_daily_torch_cpu_predictor(
                candidate,
                cell.checkpoint_path,
                cell.standardization,
            ),
        )
    if len(predictors) != DAILY_MAX_TRAINING_RUNS:
        raise ValueError("explicit-event replay must reuse exactly six source checkpoints")
    return predictors


def _explicit_event_baseline_label(replay_id: str, symbol: str) -> str:
    return f"{replay_id}-{symbol.lower()}"


def _explicit_event_run_id(
    plan: DailyCampaignPlan,
    replay_plan: DailyExplicitEventReplayPlan,
    cell: DailyExplicitEventReplayCellPlan,
) -> str:
    if cell.kind == "baseline":
        return "-".join(
            (
                plan.contract.campaign_id,
                "validation",
                cell.fold_id,
                cell.item_id,
                _explicit_event_baseline_label(replay_plan.replay_id, cell.symbol),
            )
        )
    return "-".join(
        (
            replay_plan.replay_id,
            "validation",
            cell.fold_id,
            "candidate",
            cell.item_id,
            cell.symbol.lower(),
        )
    )


def _assert_explicit_event_replay_evidence(
    cell_result: DailyExplicitEventReplayCellResult,
) -> None:
    cell = cell_result.cell
    replay = cell_result.replay
    evidence = replay.replay_evidence
    if (
        replay.fill_source != LOCAL_PAPER_SOURCE
        or evidence.fill_source != LOCAL_PAPER_SOURCE
        or replay.result.final_position != 0
    ):
        raise RuntimeError("explicit-event replay must remain flat with local-paper fills")
    for path, expected_hash, label in (
        (evidence.event_jsonl_path, evidence.event_jsonl_sha256, "event JSONL"),
        (evidence.state_sqlite_path, evidence.state_sqlite_sha256, "state SQLite"),
        (evidence.emergency_path, evidence.emergency_sha256, "emergency state"),
    ):
        _assert_artifact_hash(path, expected_hash, f"explicit-event {label}")
    events = tuple(EventStore(evidence.state_sqlite_path, evidence.event_jsonl_path).iter_events())
    timestamps = tuple(event.created_at for event in events)
    if any(current < prior for prior, current in zip(timestamps, timestamps[1:], strict=False)):
        raise RuntimeError("explicit-event replay event timestamps must be nondecreasing")
    fills = tuple(event for event in events if event.event_type == "fill")
    if any(event.payload.get("source") != LOCAL_PAPER_SOURCE for event in fills):
        raise RuntimeError("explicit-event replay fill source must remain local_paper")
    expected_ends = {
        signal_start + Timeframe.D1.duration for signal_start in cell.eligible_signal_starts
    }
    prediction_events = tuple(
        event for event in events if event.event_type == "model_prediction"
    )
    if len(prediction_events) != len(expected_ends) or {
        event.created_at for event in prediction_events
    } != expected_ends:
        raise RuntimeError("explicit-event replay consumed a signal outside its frozen mask")


def _write_daily_explicit_event_replay_summary(
    replay_plan: DailyExplicitEventReplayPlan,
    cells: tuple[DailyExplicitEventReplayCellResult, ...],
    *,
    path: Path,
) -> Path:
    if path.exists():
        raise FileExistsError(f"explicit-event replay summary already exists: {path}")
    if len(cells) != 36:
        raise ValueError("explicit-event replay summary requires exactly 36 cells")
    local_paper_cells = sum(
        cell.replay.fill_source == LOCAL_PAPER_SOURCE for cell in cells
    )
    flat_cells = sum(cell.replay.result.final_position == 0 for cell in cells)
    if local_paper_cells != len(cells) or flat_cells != len(cells):
        raise ValueError("explicit-event summary cannot claim incomplete local-paper evidence")
    target = replay_plan.source_sensitivity_target
    labels: dict[str, object] = {
        "development_only": True,
        "retrospective_only": True,
        "ranking": False,
        "promotion": False,
        "candidate_selection": False,
        "sealed_holdout": False,
        "profitability_claim": False,
    }
    inputs: dict[str, object] = {
        "source_summary": {
            "path": str(replay_plan.source_summary_path),
            "sha256": replay_plan.source_summary_sha256,
        },
        "corporate_actions": {
            "dataset_id": replay_plan.corporate_action_dataset_id,
            "dataset_hash": replay_plan.corporate_action_dataset_hash,
            "manifest_hash": replay_plan.corporate_action_manifest_hash,
        },
        "r2": {
            "dataset_id": replay_plan.r2_dataset_id,
            "dataset_hash": replay_plan.r2_dataset_hash,
            "manifest_hash": replay_plan.r2_manifest_hash,
        },
    }
    execution: dict[str, object] = {
        "backend": "torch_cpu",
        "training_runs": 0,
        "frozen_cells": len(cells),
        "baseline_cells": sum(cell.cell.kind == "baseline" for cell in cells),
        "candidate_cells": sum(cell.cell.kind == "candidate" for cell in cells),
        "fill_source": LOCAL_PAPER_SOURCE,
        "all_final_positions_flat": flat_cells == len(cells),
    }
    if target is not None:
        labels["non_independent"] = True
        inputs["replay_input"] = {
            "campaign_id": target.campaign_id,
            "campaign_contract_hash": target.campaign_contract_hash,
            "dataset_id": target.dataset_id,
            "dataset_hash": target.dataset_hash,
            "manifest_hash": target.manifest_hash,
            "source_path": str(target.source_path),
            "price_basis": target.price_basis,
            "calendar_lineage": target.calendar_lineage,
            "common_sessions_sha256": target.common_sessions_sha256,
            "standardization_source": {
                "campaign_id": replay_plan.source_campaign_id,
                "campaign_contract_hash": replay_plan.source_campaign_contract_hash,
                "dataset_id": replay_plan.r2_dataset_id,
                "dataset_hash": replay_plan.r2_dataset_hash,
                "recomputed": False,
            },
            "explicit_action_handling": target.explicit_action_handling,
            "price_adjustments_applied": 0,
        }
        execution.update(
            {
                "local_paper_cells": local_paper_cells,
                "flat_cells": flat_cells,
                "external_broker_submissions": 0,
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "replay_id": replay_plan.replay_id,
        "source_campaign_id": replay_plan.source_campaign_id,
        "parent_sensitivity_verdict": replay_plan.parent_sensitivity_verdict,
        "labels": labels,
        "inputs": inputs,
        "execution": execution,
        "cells": [_explicit_event_replay_cell_payload(cell) for cell in cells],
    }
    if target is not None:
        payload["interpretation"] = {
            "non_independent": True,
            "reason": "target_bars_use_the_frozen_r2_observed_session_calendar",
            "not_for_selection": True,
            "not_for_profitability_claim": True,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, default=str, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _explicit_event_replay_cell_payload(
    cell_result: DailyExplicitEventReplayCellResult,
) -> dict[str, object]:
    cell = cell_result.cell
    replay = cell_result.replay
    checkpoint: dict[str, object] | None = None
    if cell.kind == "candidate":
        if (
            cell.checkpoint_path is None
            or cell.checkpoint_sha256 is None
            or cell.standardization is None
        ):
            raise ValueError("explicit-event candidate replay cell is incomplete")
        checkpoint = {
            "path": str(cell.checkpoint_path),
            "sha256": cell.checkpoint_sha256,
            "preprocessing": {
                "fit_phase": "development",
                "fit_fold_id": cell.standardization.fold_id,
            },
        }
    return {
        "kind": cell.kind,
        "item_id": cell.item_id,
        "symbol": cell.symbol,
        "fold_id": cell.fold_id,
        "eligible_signal_count": len(cell.eligible_signal_starts),
        "eligible_signal_starts_sha256": _explicit_event_starts_hash(
            cell.eligible_signal_starts
        ),
        "checkpoint": checkpoint,
        "validation_artifact": {
            "path": str(replay.artifact_path),
            "sha256": _sha256_file(replay.artifact_path),
        },
        "replay_evidence": replay.replay_evidence.to_payload(),
        "verification": {
            "fill_source": replay.fill_source,
            "final_position": replay.result.final_position,
            "decisions_seen": replay.result.decisions_seen,
            "trades": len(replay.result.trades),
            "events": replay.result.event_count,
        },
    }


def _explicit_event_starts_hash(starts: tuple[datetime, ...]) -> str:
    return _sha256_bytes("\n".join(value.isoformat() for value in starts).encode("utf-8"))


def _daily_candidate_for_id(candidate_id: str) -> DailyCandidateSpec:
    candidate = next(
        (item for item in DAILY_CANDIDATES if item.candidate_id == candidate_id),
        None,
    )
    if candidate is None:
        raise ValueError("explicit-event candidate is not in the frozen daily set")
    return candidate


def run_daily_cpu_baselines(
    plan: DailyCampaignPlan,
    *,
    artifact_root: Path,
    work_root: Path,
    repo_root: Path | None = None,
) -> DailyBaselineResult:
    cells: list[DailyReplayCell] = []
    for fold in plan.folds:
        for symbol in DAILY_SYMBOLS:
            for baseline_id in plan.contract.naive_baselines:
                for scenario in ("primary", "factor_sensitivity"):
                    run_label = f"{symbol.lower()}-{scenario}"
                    replay = run_naive_cpu_baseline(
                        plan.cataloged_for(symbol),
                        campaign=plan.contract,
                        artifact_root=artifact_root,
                        work_dir=work_root
                        / fold.fold_id
                        / symbol.lower()
                        / baseline_id
                        / scenario,
                        phase="validation",
                        fold_id=fold.fold_id,
                        baseline_id=baseline_id,
                        repo_root=repo_root,
                        run_label=run_label,
                        eligible_signal_starts=plan.eligible_signal_starts(
                            symbol,
                            fold.fold_id,
                            "validation",
                            scenario=scenario,
                        ),
                    )
                    cells.append(
                        DailyReplayCell(
                            kind="baseline",
                            item_id=baseline_id,
                            symbol=symbol,
                            fold_id=fold.fold_id,
                            scenario=scenario,
                            replay=replay,
                        )
                    )
    if len(cells) != 36:
        raise RuntimeError("daily CPU baseline matrix must contain exactly 36 replays")
    return DailyBaselineResult(
        cells=tuple(cells),
        sensitivity=check_daily_sensitivity(tuple(cells)),
    )


def build_daily_training_batch(
    plan: DailyCampaignPlan,
    *,
    fold_id: str,
    candidate: DailyCandidateSpec,
) -> DailyTrainingBatch:
    _require_frozen_candidate(candidate)
    samples: list[DailyTrainingSample] = []
    for symbol in DAILY_SYMBOLS:
        bars = plan.phase_bars(symbol, fold_id, "development")
        by_start = {bar.start_ts: index for index, bar in enumerate(bars)}
        starts = plan.eligible_signal_starts(
            symbol,
            fold_id,
            "development",
            scenario="factor_sensitivity",
        )
        for signal_start in sorted(starts):
            index = by_start[signal_start]
            features = daily_feature_vector(list(bars[: index + 1]), candidate)
            entry = bars[index + 1]
            exit_bar = bars[index + 2]
            after_cost_pnl = executable_open_to_open_pnl(entry.open, exit_bar.open)
            samples.append(
                DailyTrainingSample(
                    symbol=symbol,
                    signal_start=signal_start,
                    entry_start=entry.start_ts,
                    exit_start=exit_bar.start_ts,
                    features=features,
                    label=1 if after_cost_pnl > 0 else 0,
                    after_cost_pnl=after_cost_pnl,
                )
            )
    if not samples:
        raise ValueError("daily training batch has no factor-safe development samples")
    fold = plan.fold_for(fold_id)
    standardization = fit_daily_feature_standardization(
        tuple(samples),
        fold_id=fold_id,
        development_start=fold.development[0],
        development_end=fold.development[-1] + Timeframe.D1.duration,
        feature_names=daily_feature_names(candidate.feature_set),
    )
    _assert_fold_local_standardization(plan, fold_id, standardization)
    return DailyTrainingBatch(
        fold_id=fold_id,
        candidate=candidate,
        samples=tuple(samples),
        standardized_features=tuple(
            standardization.transform(sample.features) for sample in samples
        ),
        standardization=standardization,
    )


def run_daily_cuda_breadth(
    plan: DailyCampaignPlan,
    *,
    baselines: DailyBaselineResult,
    artifact_root: Path,
    work_root: Path,
    repo_root: Path | None = None,
    trainer: DailyTrainer | None = None,
    inference_factory: DailyInferenceFactory | None = None,
) -> DailyCandidateResult:
    """Run at most three fixed variants over two folds; defaults require CUDA."""

    if len(baselines.cells) != 36:
        raise ValueError("all fixed CPU baseline replays must finish before CUDA breadth")
    _reject_repo_path(artifact_root, repo_root or Path.cwd())
    _contained_artifact_path(
        artifact_root,
        "daily-campaign",
        plan.contract.campaign_id,
    )
    summary_path = _daily_summary_path(artifact_root, plan.contract.campaign_id)
    if summary_path.exists():
        raise FileExistsError(f"daily campaign summary already exists: {summary_path}")
    selected_trainer = trainer or train_daily_candidate_torch_cuda
    selected_factory = inference_factory or load_daily_torch_predictor
    training: list[DailyCandidateTraining] = []
    cells: list[DailyReplayCell] = []
    for fold in plan.folds:
        for candidate in DAILY_CANDIDATES:
            if len(training) >= DAILY_MAX_TRAINING_RUNS:
                raise RuntimeError("daily CUDA training cap exceeded")
            batch = build_daily_training_batch(
                plan,
                fold_id=fold.fold_id,
                candidate=candidate,
            )
            checkpoint_path = (
                _contained_artifact_path(
                    artifact_root,
                    "daily-campaign",
                    plan.contract.campaign_id,
                    fold.fold_id,
                    f"{candidate.candidate_id}.pt",
                )
            )
            if checkpoint_path.exists():
                raise FileExistsError(f"daily checkpoint already exists: {checkpoint_path}")
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            metrics = selected_trainer(candidate, batch, checkpoint_path)
            if not checkpoint_path.is_file():
                raise RuntimeError("daily trainer did not create its declared checkpoint")
            predictor = selected_factory(candidate, checkpoint_path, batch.standardization)
            training.append(
                DailyCandidateTraining(
                    fold_id=fold.fold_id,
                    candidate=candidate,
                    checkpoint_path=checkpoint_path,
                    checkpoint_sha256=_sha256_file(checkpoint_path),
                    examples_seen=len(batch.samples),
                    standardization=batch.standardization,
                    trainer_metrics=dict(metrics),
                )
            )
            for symbol in DAILY_SYMBOLS:
                model = _DailyCandidateModel(candidate, batch.standardization, predictor)
                for scenario in ("primary", "factor_sensitivity"):
                    run_id = "-".join(
                        (
                            plan.contract.campaign_id,
                            "validation",
                            fold.fold_id,
                            candidate.candidate_id,
                            symbol.lower(),
                            scenario,
                        )
                    )
                    replay = run_campaign_model_replay(
                        plan.cataloged_for(symbol),
                        campaign=plan.contract,
                        model=model,
                        run_id=run_id,
                        artifact_root=artifact_root,
                        work_dir=work_root
                        / fold.fold_id
                        / candidate.candidate_id
                        / symbol.lower()
                        / scenario,
                        phase="validation",
                        fold_id=fold.fold_id,
                        repo_root=repo_root,
                        eligible_signal_starts=plan.eligible_signal_starts(
                            symbol,
                            fold.fold_id,
                            "validation",
                            scenario=scenario,
                        ),
                    )
                    cells.append(
                        DailyReplayCell(
                            kind="candidate",
                            item_id=candidate.candidate_id,
                            symbol=symbol,
                            fold_id=fold.fold_id,
                            scenario=scenario,
                            replay=replay,
                        )
                    )
    if len(training) != DAILY_MAX_TRAINING_RUNS or len(cells) != 36:
        raise RuntimeError("daily CUDA breadth must remain fixed at 6 training and 36 replays")
    combined = (*baselines.cells, *cells)
    sensitivity = check_daily_sensitivity(tuple(combined))
    summary_path = write_daily_campaign_summary(
        plan,
        baselines,
        candidate_training=tuple(training),
        candidate_cells=tuple(cells),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return DailyCandidateResult(
        training=tuple(training),
        cells=tuple(cells),
        sensitivity=sensitivity,
        summary_path=summary_path,
        summary_sha256=_sha256_file(summary_path),
    )


def write_daily_campaign_summary(
    plan: DailyCampaignPlan,
    baselines: DailyBaselineResult,
    *,
    candidate_training: tuple[DailyCandidateTraining, ...] = (),
    candidate_cells: tuple[DailyReplayCell, ...] = (),
    artifact_root: Path,
    repo_root: Path | None = None,
) -> Path:
    """Write the single recovery manifest for this bounded development campaign."""

    _reject_repo_path(artifact_root, repo_root or Path.cwd())
    _contained_artifact_path(
        artifact_root,
        "daily-campaign",
        plan.contract.campaign_id,
    )
    path = _daily_summary_path(artifact_root, plan.contract.campaign_id)
    if path.exists():
        raise FileExistsError(f"daily campaign summary already exists: {path}")
    all_cells = (*baselines.cells, *candidate_cells)
    sensitivity = check_daily_sensitivity(tuple(all_cells))
    cuda_metrics = tuple(item.trainer_metrics for item in candidate_training)
    cuda_devices = tuple(
        sorted(
            {
                str(metrics["device"])
                for metrics in cuda_metrics
                if metrics.get("device")
            }
        )
    )
    peak_memory = tuple(
        int(metrics["cuda_peak_memory_bytes"])
        for metrics in cuda_metrics
        if metrics.get("cuda_peak_memory_bytes") is not None
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "campaign_id": plan.contract.campaign_id,
        "campaign_contract_hash": plan.contract.contract_hash,
        "labels": {
            "development_only": True,
            "ranking": False,
            "promotion": False,
            "sealed_holdout": False,
            "candidate_selection": False,
            "profitability_claim": False,
        },
        "dataset": {
            "catalog_id": plan.contract.catalog.catalog_id,
            "dataset_id": plan.contract.catalog.dataset_id,
            "dataset_hash": plan.contract.catalog.dataset_hash,
            "source_path": str(plan.cataloged_bars[0].source_path.resolve()),
            "price_basis": "raw_ohlcv_only",
            "symbols": DAILY_SYMBOLS,
        },
        "split": {
            "latest_common_sessions": len(plan.common_sessions),
            "folds": [
                {
                    "fold_id": fold.fold_id,
                    "development_start": fold.development[0].isoformat(),
                    "development_end": fold.development[-1].isoformat(),
                    "development_sessions": len(fold.development),
                    "purge_dates": [value.date().isoformat() for value in fold.purge],
                    "validation_start": fold.validation[0].isoformat(),
                    "validation_end": fold.validation[-1].isoformat(),
                    "validation_sessions": len(fold.validation),
                }
                for fold in plan.folds
            ],
            "embargo_dates": [
                value.date().isoformat() for value in plan.embargo_sessions
            ],
            "purge_observed_sessions": DAILY_PURGE_SESSIONS,
            "embargo_observed_sessions": DAILY_EMBARGO_SESSIONS,
        },
        "costs": {
            "fee_bps_per_fill": str(DAILY_FEE_BPS),
            "slippage_bps_per_fill": str(DAILY_SLIPPAGE_BPS),
        },
        "training_policy": {
            "runs": len(candidate_training),
            "maximum_runs": DAILY_MAX_TRAINING_RUNS,
            "development_samples": "factor_safe",
            "preprocessing_fit": "per_fold_development_only",
            "evaluation_asymmetry": (
                "one factor-safe development fit per fold/candidate; primary versus "
                "factor_sensitivity changes validation decision inclusion only"
            ),
            "retraining_by_validation_scenario": False,
        },
        "execution_timing": {
            "signal": "completed_observed_session_t",
            "entry_observed_session_offset": 1,
            "exit_observed_session_offset": 2,
            "calendar_contiguity_required": False,
            "common_session_adjacency_proven": True,
            "signal_cadence_observed_sessions": DAILY_SIGNAL_CADENCE,
        },
        "cuda": {
            "used": any(metrics.get("backend") == "torch_cuda" for metrics in cuda_metrics),
            "devices": cuda_devices,
            "training_runs": len(candidate_training),
            "peak_memory_bytes_max": max(peak_memory) if peak_memory else None,
            "trainer_evidence": cuda_metrics,
        },
        "aggregate_metrics": {
            "baselines": _aggregate_replay_metrics(baselines.cells),
            "candidates": _aggregate_replay_metrics(candidate_cells),
        },
        "sensitivity": {
            "verdict": sensitivity.verdict,
            "sign_changes": sensitivity.sign_changes,
            "candidate_order_changed": sensitivity.candidate_order_changed,
            "primary_candidate_order": sensitivity.primary_candidate_order,
            "sensitivity_candidate_order": sensitivity.sensitivity_candidate_order,
            "relative_order_changed": sensitivity.relative_order_changed,
            "all_item_primary_order": sensitivity.all_item_primary_order,
            "all_item_sensitivity_order": sensitivity.all_item_sensitivity_order,
            "reasons": (
                *sensitivity.sign_changes,
                *(
                    ("primary_vs_factor_sensitivity_relative_order_changed",)
                    if sensitivity.relative_order_changed
                    else ()
                ),
            ),
        },
        "checkpoints": [
            {
                "fold_id": item.fold_id,
                "candidate_id": item.candidate.candidate_id,
                "path": str(item.checkpoint_path.resolve()),
                "sha256": item.checkpoint_sha256,
                "examples_seen": item.examples_seen,
                "development_sample_policy": item.development_sample_policy,
                "standardization": item.standardization.to_payload(),
            }
            for item in candidate_training
        ],
        "replays": [_replay_evidence_payload(cell) for cell in all_cells],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def check_daily_sensitivity(
    cells: tuple[DailyReplayCell, ...],
) -> DailySensitivityCheck:
    grouped: dict[tuple[str, str, str, str], dict[str, Decimal]] = {}
    for cell in cells:
        key = (cell.kind, cell.item_id, cell.symbol, cell.fold_id)
        grouped.setdefault(key, {})[cell.scenario] = cell.replay.result.after_cost_pnl
    sign_changes: list[str] = []
    for key, scenarios in sorted(grouped.items()):
        if set(scenarios) != {"primary", "factor_sensitivity"}:
            raise ValueError("sensitivity check requires paired primary and factor replays")
        if _sign(scenarios["primary"]) != _sign(scenarios["factor_sensitivity"]):
            sign_changes.append(":".join(key))

    candidate_ids = tuple(candidate.candidate_id for candidate in DAILY_CANDIDATES)
    present_candidates = tuple(
        candidate_id
        for candidate_id in candidate_ids
        if any(cell.kind == "candidate" and cell.item_id == candidate_id for cell in cells)
    )
    primary_order = _descriptive_candidate_order(cells, present_candidates, "primary")
    sensitivity_order = _descriptive_candidate_order(
        cells,
        present_candidates,
        "factor_sensitivity",
    )
    candidate_order_changed = primary_order != sensitivity_order
    all_item_primary_order = _descriptive_all_item_order(cells, "primary")
    all_item_sensitivity_order = _descriptive_all_item_order(
        cells,
        "factor_sensitivity",
    )
    relative_order_changed = all_item_primary_order != all_item_sensitivity_order
    verdict: DailySensitivityVerdict = (
        "unsupported" if sign_changes or relative_order_changed else "supported-with-limits"
    )
    return DailySensitivityCheck(
        verdict=verdict,
        sign_changes=tuple(sign_changes),
        candidate_order_changed=candidate_order_changed,
        primary_candidate_order=primary_order,
        sensitivity_candidate_order=sensitivity_order,
        relative_order_changed=relative_order_changed,
        all_item_primary_order=all_item_primary_order,
        all_item_sensitivity_order=all_item_sensitivity_order,
    )


def daily_feature_names(feature_set: DailyFeatureSet) -> tuple[str, ...]:
    core = ("lookback_return", "last_bar_return", "bar_range", "volume_change")
    if feature_set == "core":
        return core
    if feature_set == "pressure":
        return (*core, "close_position", "range_expansion", "bar_body_return")
    raise ValueError(f"unsupported daily feature set: {feature_set}")


def daily_feature_vector(
    bars: list[Bar],
    candidate: DailyCandidateSpec,
) -> tuple[float, ...]:
    if len(bars) <= candidate.lookback:
        raise ValueError("candidate feature window is shorter than lookback")
    current = bars[-1]
    prior = bars[-2]
    anchor = bars[-candidate.lookback - 1]
    if any(bar.timeframe != Timeframe.D1 for bar in (current, prior, anchor)):
        raise ValueError("daily candidate features require RAW D1 Bars")
    core = (
        _relative_change(current.close, anchor.close),
        _relative_change(current.close, prior.close),
        _relative_change(current.high, current.low),
        _relative_change(current.volume + 1, prior.volume + 1),
    )
    if candidate.feature_set == "core":
        return core
    span = float(current.high - current.low)
    prior_span = prior.high - prior.low
    return (
        *core,
        0.5 if span == 0 else float(current.close - current.low) / span,
        _relative_change(current.high - current.low, prior_span),
        _relative_change(current.close, current.open),
    )


def executable_open_to_open_pnl(entry_open: Decimal, exit_open: Decimal) -> Decimal:
    quantum = Decimal("0.0001")
    entry_fill = (entry_open * (Decimal("1") + DAILY_SLIPPAGE_BPS / 10000)).quantize(
        quantum
    )
    exit_fill = (exit_open * (Decimal("1") - DAILY_SLIPPAGE_BPS / 10000)).quantize(
        quantum
    )
    entry_fee = (entry_fill * DAILY_FEE_BPS / 10000).quantize(quantum)
    exit_fee = (exit_fill * DAILY_FEE_BPS / 10000).quantize(quantum)
    return exit_fill - exit_fee - entry_fill - entry_fee


def fit_daily_feature_standardization(
    samples: tuple[DailyTrainingSample, ...],
    *,
    fold_id: str,
    development_start: datetime,
    development_end: datetime,
    feature_names: tuple[str, ...],
) -> DailyFeatureStandardization:
    if not samples:
        raise ValueError("standardization requires development samples")
    width = len(feature_names)
    if any(len(sample.features) != width for sample in samples):
        raise ValueError("training features do not match declared feature names")
    columns = tuple(
        tuple(sample.features[index] for sample in samples) for index in range(width)
    )
    means = tuple(sum(column) / len(column) for column in columns)
    scales: list[float] = []
    for column, mean in zip(columns, means, strict=True):
        scale = math.sqrt(sum((value - mean) ** 2 for value in column) / len(column))
        scales.append(scale if math.isfinite(scale) and scale > 1e-12 else 1.0)
    return DailyFeatureStandardization(
        fold_id=fold_id,
        development_start=require_utc(development_start, "development_start"),
        development_end=require_utc(development_end, "development_end"),
        feature_names=feature_names,
        means=means,
        scales=tuple(scales),
    )


def train_daily_candidate_torch_cuda(
    candidate: DailyCandidateSpec,
    batch: DailyTrainingBatch,
    checkpoint_path: Path,
) -> dict[str, object]:
    """Train one fixed tiny MLP; torch stays optional until this callable runs."""

    import torch

    _require_frozen_candidate(candidate)
    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is not available")
    torch.manual_seed(candidate.seed)
    torch.cuda.manual_seed_all(candidate.seed)
    device = torch.device("cuda")
    torch.cuda.reset_peak_memory_stats(device)
    x = torch.tensor(batch.standardized_features, dtype=torch.float32, device=device)
    y = torch.tensor(
        [sample.label for sample in batch.samples],
        dtype=torch.float32,
        device=device,
    ).view(-1, 1)
    model = torch.nn.Sequential(
        torch.nn.Linear(len(batch.standardization.feature_names), candidate.hidden_units),
        torch.nn.ReLU(),
        torch.nn.Linear(candidate.hidden_units, 1),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=candidate.learning_rate,
        weight_decay=candidate.weight_decay,
    )
    loss_fn = torch.nn.BCEWithLogitsLoss()
    for _ in range(candidate.epochs):
        optimizer.zero_grad()
        loss = loss_fn(model(x), y)
        loss.backward()
        optimizer.step()
    torch.cuda.synchronize()
    with torch.no_grad():
        final_loss = loss_fn(model(x), y).item()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "model_kind": "daily_tiny_mlp_v1",
        "candidate": _candidate_payload(candidate),
        "standardization": batch.standardization.to_payload(),
        "state_dict": model.state_dict(),
    }
    with checkpoint_path.open("xb") as handle:
        torch.save(payload, handle)
    return {
        "backend": "torch_cuda",
        "device": torch.cuda.get_device_name(device),
        "epochs": candidate.epochs,
        "examples": len(batch.samples),
        "final_loss": f"{final_loss:.8f}",
        "cuda_peak_memory_bytes": int(torch.cuda.max_memory_allocated(device)),
        "development_only": True,
    }


def load_daily_torch_predictor(
    candidate: DailyCandidateSpec,
    checkpoint_path: Path,
    standardization: DailyFeatureStandardization,
) -> DailyProbabilityPredictor:
    """Load only this harness's primitive/tensor checkpoint with safe torch mode."""

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("PyTorch CUDA is not available")
    device = torch.device("cuda")
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    if checkpoint.get("model_kind") != "daily_tiny_mlp_v1":
        raise ValueError("unsupported daily checkpoint model kind")
    if checkpoint.get("candidate") != _candidate_payload(candidate):
        raise ValueError("daily checkpoint candidate contract mismatch")
    if checkpoint.get("standardization") != standardization.to_payload():
        raise ValueError("daily checkpoint fold-local standardization mismatch")
    model = torch.nn.Sequential(
        torch.nn.Linear(len(standardization.feature_names), candidate.hidden_units),
        torch.nn.ReLU(),
        torch.nn.Linear(candidate.hidden_units, 1),
    ).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    def predict(standardized_features: tuple[float, ...]) -> float:
        with torch.no_grad():
            tensor = torch.tensor(
                [standardized_features],
                dtype=torch.float32,
                device=device,
            )
            return float(torch.sigmoid(model(tensor)).item())

    return predict


def load_daily_torch_cpu_predictor(
    candidate: DailyCandidateSpec,
    checkpoint_path: Path,
    standardization: DailyFeatureStandardization,
) -> DailyProbabilityPredictor:
    """Load a frozen daily checkpoint on CPU without probing or using CUDA."""

    import torch

    _require_frozen_candidate(candidate)
    device = torch.device("cpu")
    try:
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    except Exception as exc:
        raise ValueError("source checkpoint is not a safe CPU-loadable checkpoint") from exc
    if not isinstance(checkpoint, dict) or (
        checkpoint.get("schema_version") != SCHEMA_VERSION
        or checkpoint.get("model_kind") != "daily_tiny_mlp_v1"
        or checkpoint.get("candidate") != _candidate_payload(candidate)
        or checkpoint.get("standardization") != standardization.to_payload()
    ):
        raise ValueError("source checkpoint contract mismatch")
    model = torch.nn.Sequential(
        torch.nn.Linear(len(standardization.feature_names), candidate.hidden_units),
        torch.nn.ReLU(),
        torch.nn.Linear(candidate.hidden_units, 1),
    ).to(device)
    try:
        model.load_state_dict(checkpoint["state_dict"], strict=True)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("source checkpoint model state is incompatible") from exc
    model.eval()

    def predict(standardized_features: tuple[float, ...]) -> float:
        with torch.no_grad():
            tensor = torch.tensor(
                [standardized_features],
                dtype=torch.float32,
                device=device,
            )
            return float(torch.sigmoid(model(tensor)).item())

    return predict


def _assert_corporate_action_r2_lineage(
    plan: DailyCampaignPlan,
    corporate_actions: CatalogedCorporateActions,
) -> None:
    if (
        corporate_actions.r2_dataset_id != plan.contract.catalog.dataset_id
        or corporate_actions.r2_dataset_hash != plan.contract.catalog.dataset_hash
    ):
        raise ValueError("corporate-action r2 lineage does not match the daily campaign")
    r2_path = plan.cataloged_bars[0].source_path.resolve()
    r2_manifest = r2_path.parent / "manifest.json"
    try:
        current_r2_hash = _sha256_file(r2_path)
        current_manifest_hash = _sha256_file(r2_manifest)
    except OSError as exc:
        raise ValueError("daily r2 lineage files are not readable") from exc
    if current_r2_hash != corporate_actions.r2_dataset_hash:
        raise ValueError("daily r2 bytes changed after attestation")
    if current_manifest_hash != corporate_actions.r2_manifest_hash:
        raise ValueError("daily r2 manifest does not match corporate-action lineage")


def _assert_corporate_action_event_membership(
    plan: DailyCampaignPlan,
    corporate_actions: CatalogedCorporateActions,
) -> None:
    common_dates = frozenset(session.date() for session in plan.common_sessions)
    for event in corporate_actions.events:
        if event.symbol not in DAILY_SYMBOLS:
            raise ValueError("corporate-action event has unexpected symbol membership")
        if event.affected_session_date not in common_dates:
            raise ValueError("corporate-action event date is outside plan.common_sessions")


def _assert_source_summary_contract(
    plan: DailyCampaignPlan,
    summary: dict[str, Any],
) -> str:
    expected_labels = {
        "candidate_selection": False,
        "development_only": True,
        "profitability_claim": False,
        "promotion": False,
        "ranking": False,
        "sealed_holdout": False,
    }
    dataset = summary.get("dataset")
    cuda = summary.get("cuda")
    training_policy = summary.get("training_policy")
    sensitivity = summary.get("sensitivity")
    source_contract_hash = summary.get("campaign_contract_hash")
    _require_sha256(source_contract_hash, "source CUDA summary campaign contract hash")
    if (
        summary.get("campaign_id") != plan.contract.campaign_id
        or summary.get("labels") != expected_labels
    ):
        raise ValueError("source CUDA summary campaign contract or labels mismatch")
    if source_contract_hash != plan.contract.contract_hash:
        legacy_key = (
            plan.contract.campaign_id,
            plan.contract.catalog.dataset_id,
            plan.contract.catalog.dataset_hash,
        )
        if _LEGACY_RAW_D1_CUDA_CONTRACTS.get(legacy_key) != source_contract_hash:
            raise ValueError("source CUDA summary campaign contract or labels mismatch")
        # Older evidence serialized a non-UTC offset before current contract
        # normalization. Compare its frozen executable schedule by instant.
        _assert_source_summary_schedule_compatibility(plan, summary)
    if not isinstance(dataset, dict) or (
        dataset.get("catalog_id") != plan.contract.catalog.catalog_id
        or dataset.get("dataset_id") != plan.contract.catalog.dataset_id
        or dataset.get("dataset_hash") != plan.contract.catalog.dataset_hash
        or dataset.get("price_basis") != "raw_ohlcv_only"
        or tuple(dataset.get("symbols") or ()) != DAILY_SYMBOLS
    ):
        raise ValueError("source CUDA summary dataset identity mismatch")
    if not isinstance(cuda, dict) or (
        cuda.get("used") is not True
        or cuda.get("training_runs") != DAILY_MAX_TRAINING_RUNS
    ):
        raise ValueError("source summary must identify the fixed six-run CUDA campaign")
    if not isinstance(training_policy, dict) or (
        training_policy.get("runs") != DAILY_MAX_TRAINING_RUNS
        or training_policy.get("maximum_runs") != DAILY_MAX_TRAINING_RUNS
        or training_policy.get("retraining_by_validation_scenario") is not False
    ):
        raise ValueError("source summary training policy must freeze six runs")
    if not isinstance(sensitivity, dict) or sensitivity.get("verdict") != "unsupported":
        raise ValueError("source summary parent sensitivity verdict must be unsupported")
    return source_contract_hash


def _assert_source_summary_schedule_compatibility(
    plan: DailyCampaignPlan,
    summary: dict[str, Any],
) -> None:
    split = summary.get("split")
    costs = summary.get("costs")
    timing = summary.get("execution_timing")
    if not isinstance(split, dict) or not isinstance(costs, dict) or not isinstance(timing, dict):
        raise ValueError("source CUDA summary functional contract is incomplete")
    expected_timing = {
        "signal": "completed_observed_session_t",
        "entry_observed_session_offset": 1,
        "exit_observed_session_offset": 2,
        "calendar_contiguity_required": False,
        "common_session_adjacency_proven": True,
        "signal_cadence_observed_sessions": DAILY_SIGNAL_CADENCE,
    }
    if (
        split.get("latest_common_sessions") != len(plan.common_sessions)
        or split.get("purge_observed_sessions") != DAILY_PURGE_SESSIONS
        or split.get("embargo_observed_sessions") != DAILY_EMBARGO_SESSIONS
        or split.get("embargo_dates")
        != [value.date().isoformat() for value in plan.embargo_sessions]
        or timing != expected_timing
    ):
        raise ValueError("source CUDA summary functional contract mismatch")
    try:
        fee_bps = Decimal(str(costs["fee_bps_per_fill"]))
        slippage_bps = Decimal(str(costs["slippage_bps_per_fill"]))
    except (KeyError, ArithmeticError) as exc:
        raise ValueError("source CUDA summary cost contract is malformed") from exc
    if fee_bps != DAILY_FEE_BPS or slippage_bps != DAILY_SLIPPAGE_BPS:
        raise ValueError("source CUDA summary functional contract mismatch")
    observed_folds = split.get("folds")
    if not isinstance(observed_folds, list) or len(observed_folds) != len(plan.folds):
        raise ValueError("source CUDA summary functional contract mismatch")
    for observed, expected in zip(observed_folds, plan.folds, strict=True):
        if not isinstance(observed, dict) or (
            observed.get("fold_id") != expected.fold_id
            or observed.get("development_sessions") != len(expected.development)
            or observed.get("validation_sessions") != len(expected.validation)
            or observed.get("purge_dates")
            != [value.date().isoformat() for value in expected.purge]
        ):
            raise ValueError("source CUDA summary functional contract mismatch")
        for field, expected_value in (
            ("development_start", expected.development[0]),
            ("development_end", expected.development[-1]),
            ("validation_start", expected.validation[0]),
            ("validation_end", expected.validation[-1]),
        ):
            try:
                observed_value = require_utc(
                    datetime.fromisoformat(str(observed[field])),
                    f"source {field}",
                )
            except (KeyError, ValueError) as exc:
                raise ValueError("source CUDA summary functional contract is malformed") from exc
            if observed_value != expected_value:
                raise ValueError("source CUDA summary functional contract mismatch")


def _source_checkpoint_contracts(
    plan: DailyCampaignPlan,
    value: object,
    *,
    artifact_root: Path,
) -> dict[
    tuple[str, str],
    tuple[Path, str, DailyFeatureStandardization],
]:
    if not isinstance(value, list):
        raise ValueError("source summary checkpoints must be a list")
    expected = {
        (fold.fold_id, candidate.candidate_id)
        for fold in plan.folds
        for candidate in DAILY_CANDIDATES
    }
    parsed: dict[
        tuple[str, str],
        tuple[Path, str, DailyFeatureStandardization],
    ] = {}
    seen_paths: set[Path] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("source checkpoint entry must be an object")
        key = (str(item.get("fold_id")), str(item.get("candidate_id")))
        if key not in expected or key in parsed:
            raise ValueError("source checkpoint matrix is duplicated or unexpected")
        candidate = next(
            (
                candidate
                for candidate in DAILY_CANDIDATES
                if candidate.candidate_id == key[1]
            ),
            None,
        )
        expected_hash = str(item.get("sha256"))
        _require_sha256(expected_hash, "source checkpoint SHA-256")
        expected_tail = (
            "daily-campaign",
            plan.contract.campaign_id,
            key[0],
            f"{key[1]}.pt",
        )
        path = _rebase_summary_artifact_path(
            item.get("path"),
            artifact_root,
            expected_tail,
            "source checkpoint",
        )
        if path in seen_paths or candidate is None:
            raise ValueError("source checkpoint matrix is duplicated or unexpected")
        _assert_artifact_hash(path, expected_hash, "source checkpoint")
        standardization = _parse_source_standardization(
            plan,
            key[0],
            candidate,
            item.get("standardization"),
        )
        parsed[key] = (path, expected_hash, standardization)
        seen_paths.add(path)
    if set(parsed) != expected:
        raise ValueError("source checkpoint matrix does not match the fixed candidates")
    return parsed


def _parse_source_standardization(
    plan: DailyCampaignPlan,
    fold_id: str,
    candidate: DailyCandidateSpec,
    value: object,
) -> DailyFeatureStandardization:
    if not isinstance(value, dict) or (
        value.get("fit_phase") != "development"
        or value.get("fit_fold_id") != fold_id
    ):
        raise ValueError("source checkpoint standardization is malformed")
    try:
        feature_names = tuple(str(item) for item in value["feature_names"])
        means = tuple(float(item) for item in value["means"])
        scales = tuple(float(item) for item in value["scales"])
        development_start = require_utc(
            datetime.fromisoformat(str(value["development_start"])),
            "development_start",
        )
        development_end = require_utc(
            datetime.fromisoformat(str(value["development_end"])),
            "development_end",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("source checkpoint standardization is malformed") from exc
    if (
        feature_names != daily_feature_names(candidate.feature_set)
        or len(means) != len(feature_names)
        or len(scales) != len(feature_names)
        or any(not math.isfinite(item) for item in (*means, *scales))
        or any(item <= 0 for item in scales)
    ):
        raise ValueError("source checkpoint standardization is malformed")
    standardization = DailyFeatureStandardization(
        fold_id=fold_id,
        development_start=development_start,
        development_end=development_end,
        feature_names=feature_names,
        means=means,
        scales=scales,
    )
    _assert_fold_local_standardization(plan, fold_id, standardization)
    return standardization


def _validate_daily_torch_checkpoint_cpu(
    candidate: DailyCandidateSpec,
    checkpoint_path: Path,
    standardization: DailyFeatureStandardization,
) -> None:
    import torch

    _require_frozen_candidate(candidate)
    try:
        checkpoint = torch.load(
            checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
    except Exception as exc:
        raise ValueError("source checkpoint is not a safe CPU-loadable checkpoint") from exc
    if not isinstance(checkpoint, dict) or (
        checkpoint.get("schema_version") != SCHEMA_VERSION
        or checkpoint.get("model_kind") != "daily_tiny_mlp_v1"
        or checkpoint.get("candidate") != _candidate_payload(candidate)
        or checkpoint.get("standardization") != standardization.to_payload()
    ):
        raise ValueError("source checkpoint contract mismatch")
    model = torch.nn.Sequential(
        torch.nn.Linear(len(standardization.feature_names), candidate.hidden_units),
        torch.nn.ReLU(),
        torch.nn.Linear(candidate.hidden_units, 1),
    )
    try:
        model.load_state_dict(checkpoint.get("state_dict"), strict=True)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("source checkpoint model state is incompatible") from exc


def _rebase_summary_artifact_path(
    value: object,
    artifact_root: Path,
    expected_tail: tuple[str, ...],
    label: str,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} path is required")
    declared_parts = tuple(part for part in value.replace("\\", "/").split("/") if part)
    if any(part in {".", ".."} for part in declared_parts) or (
        len(declared_parts) < len(expected_tail)
        or declared_parts[-len(expected_tail) :] != expected_tail
    ):
        raise ValueError(f"{label} does not have the expected artifact-relative tail")
    resolved_root = artifact_root.resolve()
    _assert_no_symlink_artifact_components(resolved_root, expected_tail)
    candidate = resolved_root.joinpath(*expected_tail).resolve()
    if resolved_root not in candidate.parents:
        raise ValueError(f"{label} escapes artifact_root")
    return candidate


def _assert_no_symlink_artifact_components(
    artifact_root: Path,
    relative_parts: tuple[str, ...],
) -> None:
    current = artifact_root
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            raise ValueError("summary-declared artifact paths cannot contain symlinks")


def _assert_artifact_hash(path: Path, expected_hash: str, label: str) -> None:
    try:
        actual_hash = _sha256_file(path)
    except OSError as exc:
        raise ValueError(f"{label} is not readable") from exc
    if actual_hash != expected_hash:
        raise ValueError(f"{label} SHA-256 mismatch")


def _require_sha256(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must use lowercase sha256:<64 hex>")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _window(sessions: tuple[datetime, ...]) -> CampaignWindow:
    return CampaignWindow(sessions[0], sessions[-1] + Timeframe.D1.duration)


def _assert_fold_local_standardization(
    plan: DailyCampaignPlan,
    fold_id: str,
    standardization: DailyFeatureStandardization,
) -> None:
    fold = plan.fold_for(fold_id)
    expected_start = fold.development[0]
    expected_end = fold.development[-1] + Timeframe.D1.duration
    if (
        standardization.fold_id != fold_id
        or standardization.development_start != expected_start
        or standardization.development_end != expected_end
    ):
        raise RuntimeError("per-fold development-only preprocessing cannot be proven")


def _require_frozen_candidate(candidate: DailyCandidateSpec) -> None:
    _validate_safe_path_component(candidate.candidate_id, "candidate_id")
    if candidate not in DAILY_CANDIDATES:
        raise ValueError("candidate is not in the fixed daily CUDA breadth set")
    if (
        candidate.hidden_units != DAILY_HIDDEN_UNITS
        or candidate.activation != "relu"
        or candidate.learning_rate != DAILY_LEARNING_RATE
        or candidate.weight_decay != DAILY_WEIGHT_DECAY
        or candidate.threshold != DAILY_THRESHOLD
        or candidate.epochs != DAILY_EPOCHS
        or candidate.seed != DAILY_SEED
    ):
        raise ValueError("daily candidate hyperparameters are frozen")


def _candidate_payload(candidate: DailyCandidateSpec) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "feature_set": candidate.feature_set,
        "lookback": candidate.lookback,
        "hidden_units": candidate.hidden_units,
        "activation": candidate.activation,
        "learning_rate": candidate.learning_rate,
        "weight_decay": candidate.weight_decay,
        "threshold": candidate.threshold,
        "epochs": candidate.epochs,
        "seed": candidate.seed,
    }


def _descriptive_candidate_order(
    cells: tuple[DailyReplayCell, ...],
    candidate_ids: tuple[str, ...],
    scenario: DailyScenario,
) -> tuple[str, ...]:
    if not candidate_ids:
        return ()
    totals = {
        candidate_id: sum(
            (
                cell.replay.result.after_cost_pnl
                for cell in cells
                if cell.kind == "candidate"
                and cell.item_id == candidate_id
                and cell.scenario == scenario
            ),
            Decimal("0"),
        )
        for candidate_id in candidate_ids
    }
    declared_index = {candidate_id: index for index, candidate_id in enumerate(candidate_ids)}
    return tuple(
        sorted(
            candidate_ids,
            key=lambda candidate_id: (-totals[candidate_id], declared_index[candidate_id]),
        )
    )


def _descriptive_all_item_order(
    cells: tuple[DailyReplayCell, ...],
    scenario: DailyScenario,
) -> tuple[str, ...]:
    baseline_ids = ("always_long", "previous_bar_direction", "flat")
    declared = (
        *(f"baseline:{baseline_id}" for baseline_id in baseline_ids),
        *(f"candidate:{candidate.candidate_id}" for candidate in DAILY_CANDIDATES),
    )
    present = {
        f"{cell.kind}:{cell.item_id}"
        for cell in cells
        if cell.scenario == scenario
    }
    ordered_present = tuple(item for item in declared if item in present)
    unexpected = tuple(sorted(present - set(declared)))
    item_ids = (*ordered_present, *unexpected)
    totals = {
        item: sum(
            (
                cell.replay.result.after_cost_pnl
                for cell in cells
                if f"{cell.kind}:{cell.item_id}" == item and cell.scenario == scenario
            ),
            Decimal("0"),
        )
        for item in item_ids
    }
    declared_index = {item: index for index, item in enumerate(item_ids)}
    return tuple(
        sorted(
            item_ids,
            key=lambda item: (-totals[item], declared_index[item]),
        )
    )


def _aggregate_replay_metrics(
    cells: tuple[DailyReplayCell, ...],
) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[DailyReplayCell]] = {}
    for cell in cells:
        groups.setdefault((cell.item_id, cell.scenario), []).append(cell)
    return [
        {
            "item_id": item_id,
            "scenario": scenario,
            "replays": len(group),
            "after_cost_pnl": str(
                sum((cell.replay.result.after_cost_pnl for cell in group), Decimal("0"))
            ),
            "gross_pnl": str(
                sum((cell.replay.result.gross_pnl for cell in group), Decimal("0"))
            ),
            "fees": str(
                sum((cell.replay.result.total_fees for cell in group), Decimal("0"))
            ),
            "slippage": str(
                sum((cell.replay.result.total_slippage for cell in group), Decimal("0"))
            ),
            "fills": sum(len(cell.replay.result.trades) for cell in group),
        }
        for (item_id, scenario), group in sorted(groups.items())
    ]


def _replay_evidence_payload(cell: DailyReplayCell) -> dict[str, object]:
    replay = cell.replay
    evidence = replay.replay_evidence
    return {
        "kind": cell.kind,
        "item_id": cell.item_id,
        "symbol": cell.symbol,
        "fold_id": cell.fold_id,
        "scenario": cell.scenario,
        "fill_source": replay.fill_source,
        "artifact": {
            "path": str(replay.artifact_path.resolve()),
            "sha256": _sha256_file(replay.artifact_path),
        },
        "events": {
            "path": str(evidence.event_jsonl_path.resolve()),
            "sha256": evidence.event_jsonl_sha256,
        },
        "state": {
            "path": str(evidence.state_sqlite_path.resolve()),
            "sha256": evidence.state_sqlite_sha256,
        },
        "emergency": {
            "path": str(evidence.emergency_path.resolve()),
            "sha256": evidence.emergency_sha256,
        },
    }


def _daily_summary_path(artifact_root: Path, campaign_id: str) -> Path:
    return _contained_artifact_path(
        artifact_root,
        "daily-campaign",
        campaign_id,
        "summary.json",
    )


def _contained_artifact_path(artifact_root: Path, *components: str) -> Path:
    resolved_root = Path(artifact_root).resolve()
    for component in components:
        _validate_safe_path_component(component, "artifact path component")
    candidate = resolved_root.joinpath(*components).resolve()
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise ValueError("derived daily campaign path escapes artifact_root")
    return candidate


def _validate_safe_path_component(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be one nonempty safe path component")
    if value in {".", ".."} or any(character in value for character in ("/", "\\", ":")):
        raise ValueError(f"{field_name} must be one nonempty safe path component")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if (
        windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
        or posix.is_absolute()
        or len(windows.parts) != 1
        or len(posix.parts) != 1
    ):
        raise ValueError(f"{field_name} must be one nonempty safe path component")


def _relative_change(numerator: Any, denominator: Any) -> float:
    base = float(denominator)
    return 0.0 if base == 0 else float(numerator) / base - 1.0


def _sign(value: Decimal) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_repo_path(path: Path, repo_root: Path) -> None:
    resolved_path = path.resolve()
    resolved_repo = repo_root.resolve()
    if os.name != "nt" and resolved_repo == Path("/app").resolve():
        docker_artifacts = Path("/app/model_artifacts").resolve()
        if resolved_path == docker_artifacts or docker_artifacts in resolved_path.parents:
            return
    if resolved_path == resolved_repo or resolved_repo in resolved_path.parents:
        raise ValueError("daily campaign artifacts must stay outside the Git workspace")

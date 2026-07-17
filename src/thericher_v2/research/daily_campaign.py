"""Frozen development-only RAW D1 campaign for SPY, QQQ, and IWM."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
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
from thericher_v2.data import CatalogedBars, load_fixed_etf_daily_factor_change_dates

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
        bars = self.phase_bars(symbol, fold_id, phase)
        factor_dates = set(self.factor_dates_for(symbol))
        indices: list[int] = []
        for index in range(
            DAILY_SHARED_MAX_LOOKBACK,
            len(bars) - ExecutableTarget().exit_bar_offset,
            DAILY_SIGNAL_CADENCE,
        ):
            if scenario == "factor_sensitivity" and any(
                bar.start_ts.date() in factor_dates
                for bar in bars[
                    index - DAILY_SHARED_MAX_LOOKBACK : index
                    + ExecutableTarget().exit_bar_offset
                    + 1
                ]
            ):
                continue
            indices.append(index)
        self._prove_execution_timing(bars, tuple(indices))
        return frozenset(bars[index].start_ts for index in indices)

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

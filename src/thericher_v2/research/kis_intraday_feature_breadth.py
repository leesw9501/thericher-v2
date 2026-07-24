"""Bounded KIS-only intraday feature breadth for the first 20-session contract."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

import thericher_v2.data as market_data
from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data import CatalogedBars, SessionWindow, resample_session_bars
from thericher_v2.execution import LOCAL_PAPER_SOURCE

from .campaign import CampaignContract, CampaignFold, CampaignWindow
from .kis_intraday_campaign import (
    KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT,
    KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
    KIS_INTRADAY_LAST_SIGNAL_OFFSET,
    KIS_INTRADAY_SESSION_COUNT,
    KIS_INTRADAY_VALIDATION_SESSION_COUNT,
    KisIntradayCpuCampaignPlan,
    build_kis_intraday_cpu_campaign_plan,
)
from .validation import CampaignReplayRun, run_campaign_model_replay

KIS_INTRADAY_FEATURE_BREADTH_ID = "kis-intraday-feature-breadth-v1"
KIS_INTRADAY_FEATURE_SCHEMA_ID = "kis-intraday-m1-m5-m10-feature-schema-v1"
KIS_INTRADAY_FEATURE_M1_BARS = 90
KIS_INTRADAY_FEATURE_M5_BARS = 18
KIS_INTRADAY_FEATURE_M10_BARS = 9
KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION = (
    KIS_INTRADAY_LAST_SIGNAL_OFFSET - KIS_INTRADAY_FIRST_SIGNAL_OFFSET + 1
)
KIS_INTRADAY_FEATURE_CANDIDATES = (
    "flat",
    "fixed_momentum",
    "regularized_linear",
)
KIS_INTRADAY_CANDIDATE_COMPARISON_SESSION_COUNT = 5
KIS_INTRADAY_SEALED_CONFIRMATION_SESSION_COUNT = 4
if (
    KIS_INTRADAY_CANDIDATE_COMPARISON_SESSION_COUNT
    + KIS_INTRADAY_SEALED_CONFIRMATION_SESSION_COUNT
    != KIS_INTRADAY_VALIDATION_SESSION_COUNT
):
    raise RuntimeError(
        "KIS intraday comparison and confirmation sessions must partition validation"
    )
KIS_INTRADAY_LINEAR_EPOCHS = 160
KIS_INTRADAY_LINEAR_LEARNING_RATE = 0.05
KIS_INTRADAY_LINEAR_L2 = 0.01
KIS_INTRADAY_LINEAR_THRESHOLD = 0.5

KIS_INTRADAY_FEATURE_NAMES = (
    "m1_return_1",
    "m1_return_5",
    "m1_return_20",
    "m1_return_90",
    "m1_range_10",
    "m1_volume_ratio_20",
    "m5_return_3",
    "m5_return_18",
    "m10_return_3",
    "m10_return_9",
)

KisIntradayFeatureCandidateId = Literal["flat", "fixed_momentum", "regularized_linear"]


class _PreparedKisIntradayFeatureInput(Protocol):
    """The Data-owned public input boundary consumed by this module."""

    catalog: CatalogedBars
    session_dates: tuple[date, ...]
    session_windows: tuple[SessionWindow, ...]
    input_hash: str


@dataclass(frozen=True)
class KisIntradayFeatureContract:
    """Hash-bound source, schema, target, and chronology for one CPU breadth run."""

    campaign_plan: KisIntradayCpuCampaignPlan
    feature_names: tuple[str, ...]
    input_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_names", tuple(self.feature_names))
        if self.feature_names != KIS_INTRADAY_FEATURE_NAMES:
            raise ValueError("KIS intraday feature schema must remain fixed")
        if not self.input_hash.startswith("sha256:") or len(self.input_hash) != 71:
            raise ValueError("KIS intraday feature input_hash must be SHA-256")

    @property
    def contract_hash(self) -> str:
        return _sha256_payload(self.to_payload())

    @property
    def development_session_dates(self) -> tuple[date, ...]:
        return self.campaign_plan.development_session_dates

    @property
    def purge_session_date(self) -> date:
        return self.campaign_plan.purge_session_date

    @property
    def validation_session_dates(self) -> tuple[date, ...]:
        return self.campaign_plan.validation_session_dates

    @property
    def candidate_comparison_session_dates(self) -> tuple[date, ...]:
        return self.validation_session_dates[:KIS_INTRADAY_CANDIDATE_COMPARISON_SESSION_COUNT]

    @property
    def sealed_confirmation_session_dates(self) -> tuple[date, ...]:
        return self.validation_session_dates[KIS_INTRADAY_CANDIDATE_COMPARISON_SESSION_COUNT:]

    @property
    def candidate_comparison_session_windows(self) -> tuple[SessionWindow, ...]:
        return self.campaign_plan.phase_session_windows("validation")[
            :KIS_INTRADAY_CANDIDATE_COMPARISON_SESSION_COUNT
        ]

    def to_payload(self) -> dict[str, object]:
        plan = self.campaign_plan
        return {
            "schema_version": self.schema_version,
            "feature_breadth_id": KIS_INTRADAY_FEATURE_BREADTH_ID,
            "feature_schema_id": KIS_INTRADAY_FEATURE_SCHEMA_ID,
            "feature_names": list(self.feature_names),
            "feature_context": {
                "m1_completed_bars": KIS_INTRADAY_FEATURE_M1_BARS,
                "m5_completed_bars": KIS_INTRADAY_FEATURE_M5_BARS,
                "m10_completed_bars": KIS_INTRADAY_FEATURE_M10_BARS,
                "same_session_only": True,
            },
            "executable_target": {
                "direction": "long_only",
                "decision": "completed_m1_bar_close",
                "entry": "next_m1_bar_open",
                "exit": "following_m1_bar_open",
                "cross_session_allowed": False,
            },
            "catalog": {
                "dataset_id": plan.cataloged_bars.dataset_id,
                "dataset_hash": plan.cataloged_bars.dataset_hash,
                "input_hash": self.input_hash,
            },
            "campaign": {
                "contract_hash": plan.campaign.contract_hash,
                "session_dates": [item.isoformat() for item in plan.session_dates],
                "session_windows": [_window_payload(window) for window in plan.session_windows],
                "development_session_dates": [
                    item.isoformat() for item in self.development_session_dates
                ],
                "purge_session_date": self.purge_session_date.isoformat(),
                "validation_session_dates": [
                    item.isoformat() for item in self.validation_session_dates
                ],
                "candidate_comparison_session_dates": [
                    item.isoformat() for item in self.candidate_comparison_session_dates
                ],
                "sealed_confirmation_session_dates": [
                    item.isoformat() for item in self.sealed_confirmation_session_dates
                ],
                "costs": {
                    "fee_bps": str(plan.campaign.costs.fee_bps),
                    "slippage_bps": str(plan.campaign.costs.slippage_bps),
                    "slippage_source_id": plan.campaign.costs.slippage_source_id,
                },
            },
            "candidate_policy": {
                "development_only_training": True,
                "candidate_comparison_only": True,
                "selection_allowed": False,
                "sealed_confirmation_materialized": False,
                "gpu_used": False,
                "candidates": list(KIS_INTRADAY_FEATURE_CANDIDATES),
            },
        }


@dataclass(frozen=True)
class KisIntradayFeatureSample:
    """One in-session decision feature vector and its executable target label."""

    session_date: date
    session_window: SessionWindow
    decision_start: datetime
    decision_end: datetime
    history_start: datetime
    entry_start: datetime
    exit_start: datetime
    features: tuple[float, ...]
    target_return: float
    target_label: int
    m1_bar_count: int
    m5_bar_count: int
    m10_bar_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(self.features))
        if len(self.features) != len(KIS_INTRADAY_FEATURE_NAMES):
            raise ValueError("KIS intraday feature sample width is invalid")
        if self.m1_bar_count != KIS_INTRADAY_FEATURE_M1_BARS:
            raise ValueError("KIS intraday feature sample requires 90 completed M1 bars")
        if self.m5_bar_count != KIS_INTRADAY_FEATURE_M5_BARS:
            raise ValueError("KIS intraday feature sample requires 18 completed M5 bars")
        if self.m10_bar_count != KIS_INTRADAY_FEATURE_M10_BARS:
            raise ValueError("KIS intraday feature sample requires 9 completed M10 bars")
        if self.target_label not in (0, 1):
            raise ValueError("KIS intraday target label is invalid")
        if any(not math.isfinite(value) for value in (*self.features, self.target_return)):
            raise ValueError("KIS intraday feature sample values must be finite")
        if (
            self.history_start < self.session_window.open_ts
            or self.decision_start < self.session_window.open_ts
            or self.exit_start >= self.session_window.close_ts
            or self.entry_start != self.decision_end
            or self.exit_start != self.entry_start + Timeframe.M1.duration
        ):
            raise ValueError("KIS intraday feature target must remain inside one session")


@dataclass(frozen=True)
class KisIntradayFeatureDataset:
    """Development and comparison samples; purge and confirmation data stay absent."""

    contract: KisIntradayFeatureContract
    development_samples: tuple[KisIntradayFeatureSample, ...]
    validation_samples: tuple[KisIntradayFeatureSample, ...]
    sample_hash: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "development_samples", tuple(self.development_samples))
        object.__setattr__(self, "validation_samples", tuple(self.validation_samples))
        expected_development = (
            KIS_INTRADAY_DEVELOPMENT_SESSION_COUNT * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
        )
        expected_validation = (
            KIS_INTRADAY_CANDIDATE_COMPARISON_SESSION_COUNT
            * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
        )
        if len(self.development_samples) != expected_development:
            raise ValueError("KIS intraday feature development geometry is invalid")
        if len(self.validation_samples) != expected_validation:
            raise ValueError("KIS intraday feature validation geometry is invalid")
        if {
            sample.session_date for sample in self.development_samples
        } != set(self.contract.development_session_dates):
            raise ValueError("KIS intraday development samples escape the development sessions")
        if {
            sample.session_date for sample in self.validation_samples
        } != set(self.contract.candidate_comparison_session_dates):
            raise ValueError("KIS intraday comparison samples escape comparison sessions")
        if any(
            sample.session_date == self.contract.purge_session_date
            or sample.session_date in self.contract.sealed_confirmation_session_dates
            for sample in (*self.development_samples, *self.validation_samples)
        ):
            raise ValueError("KIS intraday excluded session must not produce samples")
        if not self.sample_hash.startswith("sha256:") or len(self.sample_hash) != 71:
            raise ValueError("KIS intraday sample_hash must be SHA-256")

    @property
    def purge_sample_count(self) -> int:
        return 0

    @property
    def candidate_comparison_samples(self) -> tuple[KisIntradayFeatureSample, ...]:
        return self.validation_samples


@dataclass(frozen=True)
class KisIntradayRegularizedLinearModel:
    """A fixed full-batch logistic model trained only on development samples."""

    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    intercept: float
    epochs: int = KIS_INTRADAY_LINEAR_EPOCHS
    learning_rate: float = KIS_INTRADAY_LINEAR_LEARNING_RATE
    l2: float = KIS_INTRADAY_LINEAR_L2
    threshold: float = KIS_INTRADAY_LINEAR_THRESHOLD
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_names", tuple(self.feature_names))
        object.__setattr__(self, "means", tuple(self.means))
        object.__setattr__(self, "scales", tuple(self.scales))
        object.__setattr__(self, "weights", tuple(self.weights))
        width = len(KIS_INTRADAY_FEATURE_NAMES)
        if (
            self.feature_names != KIS_INTRADAY_FEATURE_NAMES
            or len(self.means) != width
            or len(self.scales) != width
            or len(self.weights) != width
        ):
            raise ValueError("KIS intraday regularized linear model schema is invalid")
        if (
            self.epochs != KIS_INTRADAY_LINEAR_EPOCHS
            or self.learning_rate != KIS_INTRADAY_LINEAR_LEARNING_RATE
            or self.l2 != KIS_INTRADAY_LINEAR_L2
            or self.threshold != KIS_INTRADAY_LINEAR_THRESHOLD
        ):
            raise ValueError("KIS intraday regularized linear hyperparameters are frozen")
        if any(
            not math.isfinite(value) or value <= 0
            for value in self.scales
        ) or any(
            not math.isfinite(value)
            for value in (*self.means, *self.weights, self.intercept)
        ):
            raise ValueError("KIS intraday regularized linear parameters must be finite")

    def probability(self, features: tuple[float, ...]) -> float:
        if len(features) != len(self.feature_names):
            raise ValueError("KIS intraday regularized linear feature width is invalid")
        normalized = (
            (value - mean) / scale
            for value, mean, scale in zip(features, self.means, self.scales, strict=True)
        )
        return _sigmoid(self.intercept + math.fsum(
            weight * value for weight, value in zip(self.weights, normalized, strict=True)
        ))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": "regularized_linear",
            "feature_schema_id": KIS_INTRADAY_FEATURE_SCHEMA_ID,
            "feature_names": list(self.feature_names),
            "means": list(self.means),
            "scales": list(self.scales),
            "weights": list(self.weights),
            "intercept": self.intercept,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "l2": self.l2,
            "threshold": self.threshold,
            "training_scope": "development_only",
        }


@dataclass(frozen=True)
class KisIntradayFeatureCandidateRun:
    candidate_id: KisIntradayFeatureCandidateId
    replay: CampaignReplayRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.replay.fill_source != LOCAL_PAPER_SOURCE:
            raise ValueError("KIS intraday feature breadth requires local-paper replay")


@dataclass(frozen=True)
class KisIntradayFeatureBreadthRun:
    """Descriptive CPU evidence only; it makes no promotion or profitability claim."""

    contract: KisIntradayFeatureContract
    dataset: KisIntradayFeatureDataset
    linear_model: KisIntradayRegularizedLinearModel
    candidate_runs: tuple[KisIntradayFeatureCandidateRun, ...]
    contract_path: Path
    model_path: Path
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_runs", tuple(self.candidate_runs))
        if (
            tuple(item.candidate_id for item in self.candidate_runs)
            != KIS_INTRADAY_FEATURE_CANDIDATES
        ):
            raise ValueError("KIS intraday feature candidates must run in fixed order")
        if any(item.replay.result.campaign_phase != "validation" for item in self.candidate_runs):
            raise ValueError("KIS intraday feature candidates must replay validation only")


def build_kis_intraday_feature_contract(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
) -> KisIntradayFeatureContract:
    """Freeze the Data-selected KIS source before feature construction or fitting."""

    selected_dates = tuple(session_dates)
    prepared = _prepare_data_owned_input(catalog, session_dates=selected_dates)
    selected_catalog = _prepared_cataloged_bars(prepared)
    prepared_dates = _prepared_session_dates(prepared)
    prepared_windows = _prepared_session_windows(prepared)
    if prepared_dates != selected_dates:
        raise ValueError("Data feature input must preserve the requested session selection")

    plan = build_kis_intraday_cpu_campaign_plan(catalog, session_dates=prepared_dates)
    if (
        plan.cataloged_bars.dataset_id != selected_catalog.dataset_id
        or plan.cataloged_bars.dataset_hash != selected_catalog.dataset_hash
        or plan.cataloged_bars.bars != selected_catalog.bars
    ):
        raise ValueError("Data feature selection must match the frozen campaign selection")
    if plan.session_windows != prepared_windows:
        raise ValueError("Data feature session windows must match the frozen campaign windows")
    if not plan.cataloged_bars.dataset_id.startswith("kis.paper.private.intraday.qqq."):
        raise ValueError("KIS intraday feature breadth requires the KIS-only QQQ catalog")
    if any(bar.symbol != "QQQ" for bar in plan.cataloged_bars.bars):
        raise ValueError("KIS intraday feature breadth requires QQQ bars only")

    input_hash = _prepared_input_hash(
        prepared,
        catalog=selected_catalog,
        session_dates=prepared_dates,
        session_windows=prepared_windows,
    )
    return KisIntradayFeatureContract(
        campaign_plan=plan,
        feature_names=KIS_INTRADAY_FEATURE_NAMES,
        input_hash=input_hash,
    )


def build_kis_intraday_feature_dataset(
    contract: KisIntradayFeatureContract,
) -> KisIntradayFeatureDataset:
    """Build only development and comparison samples from completed same-session bars."""

    development = build_kis_intraday_feature_development_samples(contract)
    validation = build_kis_intraday_feature_candidate_comparison_samples(contract)
    sample_hash = _sha256_payload(
        {
            "contract_hash": contract.contract_hash,
            "development": [_sample_payload(item) for item in development],
            "candidate_comparison": [_sample_payload(item) for item in validation],
        }
    )
    return KisIntradayFeatureDataset(
        contract=contract,
        development_samples=development,
        validation_samples=validation,
        sample_hash=sample_hash,
    )


def build_kis_intraday_feature_development_samples(
    contract: KisIntradayFeatureContract,
) -> tuple[KisIntradayFeatureSample, ...]:
    """Materialize only the fixed development slice for a downstream trainer."""

    plan = contract.campaign_plan
    return _samples_for_windows(
        plan.cataloged_bars,
        session_dates=contract.development_session_dates,
        session_windows=plan.phase_session_windows("development"),
    )


def build_kis_intraday_feature_candidate_comparison_samples(
    contract: KisIntradayFeatureContract,
) -> tuple[KisIntradayFeatureSample, ...]:
    """Materialize only the fixed comparison slice after a screen is precommitted."""

    plan = contract.campaign_plan
    return _samples_for_windows(
        plan.cataloged_bars,
        session_dates=contract.candidate_comparison_session_dates,
        session_windows=contract.candidate_comparison_session_windows,
    )


def fit_kis_intraday_regularized_linear(
    dataset: KisIntradayFeatureDataset,
) -> KisIntradayRegularizedLinearModel:
    """Fit a deterministic small logistic candidate from development samples only."""

    return fit_kis_intraday_regularized_linear_samples(
        dataset.development_samples,
        development_session_dates=dataset.contract.development_session_dates,
    )


def fit_kis_intraday_regularized_linear_samples(
    samples: tuple[KisIntradayFeatureSample, ...],
    *,
    development_session_dates: tuple[date, ...],
) -> KisIntradayRegularizedLinearModel:
    """Fit the fixed model from an explicitly bounded development-only sample set."""

    if not isinstance(samples, tuple):
        raise TypeError("KIS intraday regularized linear samples must be a tuple")
    if not isinstance(development_session_dates, tuple):
        raise TypeError("KIS intraday development session dates must be a tuple")
    if not samples:
        raise ValueError("KIS intraday regularized linear candidate requires development samples")
    if any(
        sample.session_date not in development_session_dates
        for sample in samples
    ):
        raise ValueError("KIS intraday regularized linear candidate may train only on development")

    width = len(KIS_INTRADAY_FEATURE_NAMES)
    count = len(samples)
    means = tuple(
        math.fsum(sample.features[index] for sample in samples) / count
        for index in range(width)
    )
    scales = tuple(
        max(
            math.sqrt(
                math.fsum(
                    (sample.features[index] - means[index]) ** 2 for sample in samples
                )
                / count
            ),
            1e-12,
        )
        for index in range(width)
    )
    normalized = tuple(
        tuple(
            (value - mean) / scale
            for value, mean, scale in zip(
                sample.features,
                means,
                scales,
                strict=True,
            )
        )
        for sample in samples
    )
    weights = [0.0] * width
    intercept = 0.0
    for _ in range(KIS_INTRADAY_LINEAR_EPOCHS):
        residuals = tuple(
            _sigmoid(intercept + math.fsum(
                weight * value for weight, value in zip(weights, row, strict=True)
            ))
            - sample.target_label
            for row, sample in zip(normalized, samples, strict=True)
        )
        gradient_intercept = math.fsum(residuals) / count
        gradient_weights = [
            math.fsum(
                residual * row[index]
                for residual, row in zip(residuals, normalized, strict=True)
            )
            / count
            + KIS_INTRADAY_LINEAR_L2 * weights[index]
            for index in range(width)
        ]
        intercept -= KIS_INTRADAY_LINEAR_LEARNING_RATE * gradient_intercept
        for index, gradient in enumerate(gradient_weights):
            weights[index] -= KIS_INTRADAY_LINEAR_LEARNING_RATE * gradient

    return KisIntradayRegularizedLinearModel(
        feature_names=KIS_INTRADAY_FEATURE_NAMES,
        means=means,
        scales=scales,
        weights=tuple(weights),
        intercept=intercept,
    )


def build_kis_intraday_feature_samples(
    catalog: CatalogedBars,
    *,
    session_dates: tuple[date, ...],
    session_windows: tuple[SessionWindow, ...],
) -> tuple[KisIntradayFeatureSample, ...]:
    """Build fixed multi-timeframe samples from caller-bounded complete sessions."""

    return _samples_for_windows(
        catalog,
        session_dates=session_dates,
        session_windows=session_windows,
    )


def run_kis_intraday_feature_breadth(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    artifact_root: Path,
    work_root: Path,
    run_label: str,
    repo_root: Path | None = None,
    starting_cash: Decimal = Decimal("10000"),
    quantity: Decimal = Decimal("1"),
) -> KisIntradayFeatureBreadthRun:
    """Replay fixed candidates on comparison sessions without selection or GPU execution."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    resolved_work_root = Path(work_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    _reject_repo_path(resolved_work_root, repo_root=resolved_repo_root)
    output_dir = resolved_artifact_root / "kis-intraday-feature-breadth" / run_label
    if output_dir.exists():
        raise FileExistsError(f"KIS intraday feature breadth artifact already exists: {output_dir}")

    contract = build_kis_intraday_feature_contract(catalog, session_dates=session_dates)
    dataset = build_kis_intraday_feature_dataset(contract)
    linear_model = fit_kis_intraday_regularized_linear(dataset)
    candidate_comparison_campaign = _candidate_comparison_campaign(contract)

    output_dir.mkdir(parents=True, exist_ok=False)
    contract_path = output_dir / "contract.json"
    model_path = output_dir / "regularized-linear.json"
    _write_json_new(contract_path, {
        **contract.to_payload(),
        "contract_hash": contract.contract_hash,
        "sample_hash": dataset.sample_hash,
        "development_sample_count": len(dataset.development_samples),
        "purge_sample_count": dataset.purge_sample_count,
        "candidate_comparison_sample_count": len(dataset.candidate_comparison_samples),
        "sealed_confirmation_sample_count": 0,
    })
    _write_json_new(model_path, {
        **linear_model.to_payload(),
        "contract_hash": contract.contract_hash,
        "sample_hash": dataset.sample_hash,
    })

    validation_features = {sample.decision_end: sample for sample in dataset.validation_samples}
    candidate_runs: list[KisIntradayFeatureCandidateRun] = []
    for candidate_id in KIS_INTRADAY_FEATURE_CANDIDATES:
        candidate_model = _KisIntradayFeatureDecisionModel(
            candidate_id=candidate_id,
            samples_by_decision_end=validation_features,
            sample_hash=dataset.sample_hash,
            linear_model=linear_model if candidate_id == "regularized_linear" else None,
        )
        replay = run_campaign_model_replay(
            contract.campaign_plan.cataloged_bars,
            campaign=candidate_comparison_campaign,
            model=candidate_model,
            run_id=f"{KIS_INTRADAY_FEATURE_BREADTH_ID}-{candidate_id}-{run_label}",
            artifact_root=resolved_artifact_root,
            work_dir=resolved_work_root / "kis-intraday-feature-breadth" / run_label / candidate_id,
            phase="validation",
            fold_id="fold-1",
            repo_root=resolved_repo_root,
            starting_cash=starting_cash,
            quantity=quantity,
            eligible_signal_starts=_eligible_signal_starts(
                contract.candidate_comparison_session_windows
            ),
            allowed_session_windows=contract.candidate_comparison_session_windows,
            emergency_reason="kis_intraday_feature_breadth_candidate_comparison_only",
        )
        if (
            replay.fill_source != LOCAL_PAPER_SOURCE
            or replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
        ):
            raise RuntimeError("KIS intraday feature breadth must use local-paper only")
        candidate_runs.append(
            KisIntradayFeatureCandidateRun(candidate_id=candidate_id, replay=replay)
        )

    summary_path = output_dir / "summary.json"
    _write_json_new(summary_path, _summary_payload(
        contract=contract,
        dataset=dataset,
        linear_model=linear_model,
        candidate_runs=tuple(candidate_runs),
        contract_path=contract_path,
        model_path=model_path,
        candidate_comparison_campaign=candidate_comparison_campaign,
    ))
    return KisIntradayFeatureBreadthRun(
        contract=contract,
        dataset=dataset,
        linear_model=linear_model,
        candidate_runs=tuple(candidate_runs),
        contract_path=contract_path,
        model_path=model_path,
        summary_path=summary_path,
    )


@dataclass(frozen=True)
class _KisIntradayFeatureDecisionModel:
    candidate_id: KisIntradayFeatureCandidateId
    samples_by_decision_end: Mapping[datetime, KisIntradayFeatureSample]
    sample_hash: str
    linear_model: KisIntradayRegularizedLinearModel | None
    lookback: int = KIS_INTRADAY_FEATURE_M1_BARS - 1

    def __post_init__(self) -> None:
        if self.candidate_id not in KIS_INTRADAY_FEATURE_CANDIDATES:
            raise ValueError("KIS intraday feature candidate is invalid")
        if self.candidate_id == "regularized_linear" and self.linear_model is None:
            raise ValueError("regularized linear candidate requires fitted development parameters")
        if self.candidate_id != "regularized_linear" and self.linear_model is not None:
            raise ValueError("only regularized linear may receive fitted parameters")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < KIS_INTRADAY_FEATURE_M1_BARS:
            raise ValueError("KIS intraday feature candidate requires 90 completed M1 bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        if sample is None:
            raise ValueError("KIS intraday feature candidate received a non-validation decision")
        tail = tuple(bars[-KIS_INTRADAY_FEATURE_M1_BARS:])
        expected_starts = tuple(
            sample.history_start + Timeframe.M1.duration * index
            for index in range(KIS_INTRADAY_FEATURE_M1_BARS)
        )
        if (
            tuple(bar.start_ts for bar in tail) != expected_starts
            or tail[-1].end_ts != sample.decision_end
            or any(
                bar.start_ts < sample.session_window.open_ts
                or bar.end_ts > sample.session_window.close_ts
                for bar in tail
            )
        ):
            raise ValueError("KIS intraday feature candidate cannot use cross-session history")

        action, confidence, metadata = self._decision(sample)
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason=f"kis_intraday_feature_{self.candidate_id}",
            timeframe=Timeframe.M1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=f"kis_intraday_{self.candidate_id}",
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
                "sample_hash": self.sample_hash,
                **metadata,
            },
        )

    def _decision(
        self,
        sample: KisIntradayFeatureSample,
    ) -> tuple[Literal["buy", "hold"], Decimal, dict[str, object]]:
        if self.candidate_id == "flat":
            return "hold", Decimal("0"), {"decision_rule": "fixed_flat"}
        if self.candidate_id == "fixed_momentum":
            m1_return_20 = sample.features[2]
            m5_return_3 = sample.features[6]
            m10_return_3 = sample.features[8]
            buy = m1_return_20 > 0 and m5_return_3 > 0 and m10_return_3 > 0
            return (
                "buy" if buy else "hold",
                Decimal("1") if buy else Decimal("0"),
                {"decision_rule": "fixed_positive_momentum"},
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


def _prepare_data_owned_input(
    catalog: CatalogedBars,
    *,
    session_dates: tuple[date, ...],
) -> _PreparedKisIntradayFeatureInput:
    prepare = getattr(market_data, "prepare_kis_paper_intraday_feature_input", None)
    if not callable(prepare):
        raise RuntimeError("Data feature input API is unavailable")
    prepared = prepare(catalog, session_dates=session_dates)
    return prepared


def _prepared_cataloged_bars(prepared: _PreparedKisIntradayFeatureInput) -> CatalogedBars:
    cataloged_bars = getattr(prepared, "cataloged_bars", None)
    if isinstance(cataloged_bars, CatalogedBars):
        return cataloged_bars
    catalog = getattr(prepared, "catalog", None)
    if isinstance(catalog, CatalogedBars):
        return catalog
    raise TypeError("Data feature input must expose CatalogedBars as cataloged_bars or catalog")


def _prepared_input_hash(
    prepared: _PreparedKisIntradayFeatureInput,
    *,
    catalog: CatalogedBars,
    session_dates: tuple[date, ...],
    session_windows: tuple[SessionWindow, ...],
) -> str:
    input_hash = getattr(prepared, "input_hash", None)
    if isinstance(input_hash, str) and input_hash.startswith("sha256:") and len(input_hash) == 71:
        return input_hash
    return _sha256_payload(
        {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "session_dates": [item.isoformat() for item in session_dates],
            "session_windows": [_window_payload(item) for item in session_windows],
        }
    )


def _prepared_session_dates(prepared: _PreparedKisIntradayFeatureInput) -> tuple[date, ...]:
    session_dates = getattr(prepared, "session_dates", None)
    if not isinstance(session_dates, tuple) or any(
        type(item) is not date for item in session_dates
    ):
        raise TypeError("Data feature input session_dates must be a date tuple")
    if len(session_dates) != KIS_INTRADAY_SESSION_COUNT:
        raise ValueError("KIS intraday feature breadth requires exactly 20 sessions")
    return session_dates


def _prepared_session_windows(
    prepared: _PreparedKisIntradayFeatureInput,
) -> tuple[SessionWindow, ...]:
    session_windows = getattr(prepared, "session_windows", None)
    if not isinstance(session_windows, tuple) or any(
        not isinstance(item, SessionWindow) for item in session_windows
    ):
        raise TypeError("Data feature input session_windows must be a SessionWindow tuple")
    if len(session_windows) != KIS_INTRADAY_SESSION_COUNT:
        raise ValueError("KIS intraday feature breadth session windows are incomplete")
    return session_windows


def _samples_for_windows(
    catalog: CatalogedBars,
    *,
    session_dates: tuple[date, ...],
    session_windows: tuple[SessionWindow, ...],
) -> tuple[KisIntradayFeatureSample, ...]:
    if len(session_dates) != len(session_windows):
        raise ValueError("KIS intraday feature sessions and windows must align")
    samples: list[KisIntradayFeatureSample] = []
    for session_date, window in zip(session_dates, session_windows, strict=True):
        session_bars = tuple(
            bar
            for bar in catalog.bars
            if bar.start_ts >= window.open_ts and bar.end_ts <= window.close_ts
        )
        _validate_complete_session_bars(session_bars, window=window)
        session_m5_bars = resample_session_bars(
            session_bars,
            Timeframe.M5,
            session=window,
        ).bars
        session_m10_bars = resample_session_bars(
            session_bars,
            Timeframe.M10,
            session=window,
        ).bars
        for offset in range(
            KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
            KIS_INTRADAY_LAST_SIGNAL_OFFSET + 1,
        ):
            samples.append(
                _build_sample(
                    session_date=session_date,
                    session_window=window,
                    session_bars=session_bars,
                    session_m5_bars=session_m5_bars,
                    session_m10_bars=session_m10_bars,
                    signal_offset=offset,
                )
            )
    return tuple(samples)


def _validate_complete_session_bars(
    session_bars: tuple[Bar, ...],
    *,
    window: SessionWindow,
) -> None:
    expected_count = window.duration // Timeframe.M1.duration
    expected_starts = tuple(
        window.open_ts + Timeframe.M1.duration * index for index in range(expected_count)
    )
    if (
        len(session_bars) != expected_count
        or tuple(bar.start_ts for bar in session_bars) != expected_starts
        or any(bar.timeframe != Timeframe.M1 or not bar.complete for bar in session_bars)
    ):
        raise ValueError("KIS intraday feature input has a missing or incomplete minute")


def _build_sample(
    *,
    session_date: date,
    session_window: SessionWindow,
    session_bars: tuple[Bar, ...],
    session_m5_bars: tuple[Bar, ...],
    session_m10_bars: tuple[Bar, ...],
    signal_offset: int,
) -> KisIntradayFeatureSample:
    history_start_index = signal_offset - (KIS_INTRADAY_FEATURE_M1_BARS - 1)
    history = session_bars[history_start_index : signal_offset + 1]
    entry_bar = session_bars[signal_offset + 1]
    exit_bar = session_bars[signal_offset + 2]
    signal_bar = history[-1]
    if (
        len(history) != KIS_INTRADAY_FEATURE_M1_BARS
        or entry_bar.start_ts != signal_bar.end_ts
        or exit_bar.start_ts != entry_bar.end_ts
        or exit_bar.end_ts > session_window.close_ts
    ):
        raise ValueError("KIS intraday feature target cannot cross a session boundary")

    completed_m5_count = (signal_offset + 1) // 5
    completed_m10_count = (signal_offset + 1) // 10
    m5_bars = session_m5_bars[
        completed_m5_count - KIS_INTRADAY_FEATURE_M5_BARS : completed_m5_count
    ]
    m10_bars = session_m10_bars[
        completed_m10_count - KIS_INTRADAY_FEATURE_M10_BARS : completed_m10_count
    ]
    if (
        len(m5_bars) != KIS_INTRADAY_FEATURE_M5_BARS
        or len(m10_bars) != KIS_INTRADAY_FEATURE_M10_BARS
        or m5_bars[-1].end_ts > signal_bar.end_ts
        or m10_bars[-1].end_ts > signal_bar.end_ts
    ):
        raise ValueError("KIS intraday feature resampling must use completed same-session history")
    features = _feature_values(history, m5_bars=m5_bars, m10_bars=m10_bars)
    target_return = _relative_change(exit_bar.open, entry_bar.open)
    return KisIntradayFeatureSample(
        session_date=session_date,
        session_window=session_window,
        decision_start=signal_bar.start_ts,
        decision_end=signal_bar.end_ts,
        history_start=history[0].start_ts,
        entry_start=entry_bar.start_ts,
        exit_start=exit_bar.start_ts,
        features=features,
        target_return=target_return,
        target_label=1 if target_return > 0 else 0,
        m1_bar_count=len(history),
        m5_bar_count=len(m5_bars),
        m10_bar_count=len(m10_bars),
    )


def _feature_values(
    m1_bars: tuple[Bar, ...],
    *,
    m5_bars: tuple[Bar, ...],
    m10_bars: tuple[Bar, ...],
) -> tuple[float, ...]:
    latest = m1_bars[-1]
    latest_ten = m1_bars[-10:]
    volume_mean = math.fsum(float(bar.volume) for bar in m1_bars[-20:]) / 20
    volume_ratio = 0.0 if volume_mean == 0 else float(latest.volume) / volume_mean
    values = (
        _relative_change(latest.close, m1_bars[-2].close),
        _relative_change(latest.close, m1_bars[-6].close),
        _relative_change(latest.close, m1_bars[-21].close),
        _relative_change(latest.close, m1_bars[0].close),
        _relative_change(max(bar.high for bar in latest_ten), min(bar.low for bar in latest_ten)),
        volume_ratio,
        _relative_change(m5_bars[-1].close, m5_bars[-4].close),
        _relative_change(m5_bars[-1].close, m5_bars[0].close),
        _relative_change(m10_bars[-1].close, m10_bars[-4].close),
        _relative_change(m10_bars[-1].close, m10_bars[0].close),
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("KIS intraday feature values must be finite")
    return values


def _relative_change(current: Decimal, prior: Decimal) -> float:
    return float(current / prior - Decimal("1"))


def _sigmoid(value: float) -> float:
    bounded = max(min(value, 60.0), -60.0)
    return 1.0 / (1.0 + math.exp(-bounded))


def _sample_payload(sample: KisIntradayFeatureSample) -> dict[str, object]:
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


def _summary_payload(
    *,
    contract: KisIntradayFeatureContract,
    dataset: KisIntradayFeatureDataset,
    linear_model: KisIntradayRegularizedLinearModel,
    candidate_runs: tuple[KisIntradayFeatureCandidateRun, ...],
    contract_path: Path,
    model_path: Path,
    candidate_comparison_campaign: CampaignContract,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_local_paper",
        "claim": (
            "descriptive CPU breadth replay only; not a model promotion or profitability claim"
        ),
        "contract_hash": contract.contract_hash,
        "sample_hash": dataset.sample_hash,
        "feature_schema_id": KIS_INTRADAY_FEATURE_SCHEMA_ID,
        "sample_counts": {
            "development": len(dataset.development_samples),
            "purge": dataset.purge_sample_count,
            "candidate_comparison": len(dataset.candidate_comparison_samples),
            "sealed_confirmation": 0,
        },
        "sealed_confirmation": {
            "session_dates": [
                item.isoformat() for item in contract.sealed_confirmation_session_dates
            ],
            "materialized": False,
            "selection_allowed": False,
        },
        "candidate_comparison_campaign_contract_hash": (
            candidate_comparison_campaign.contract_hash
        ),
        "artifacts": {
            "contract_path": str(contract_path),
            "regularized_linear_path": str(model_path),
        },
        "regularized_linear": linear_model.to_payload(),
        "candidates": [
            {
                "candidate_id": item.candidate_id,
                "fill_source": item.replay.fill_source,
                "validation_artifact_path": str(item.replay.artifact_path),
                "replay_evidence": item.replay.replay_evidence.to_payload(),
                "result": {
                    "bars_seen": item.replay.result.bars_seen,
                    "decisions_seen": item.replay.result.decisions_seen,
                    "trade_count": len(item.replay.result.trades),
                    "after_cost_pnl": str(item.replay.result.after_cost_pnl),
                    "gross_pnl": str(item.replay.result.gross_pnl),
                    "total_fees": str(item.replay.result.total_fees),
                    "total_slippage": str(item.replay.result.total_slippage),
                },
            }
            for item in candidate_runs
        ],
    }


def _eligible_signal_starts(windows: tuple[SessionWindow, ...]) -> frozenset[datetime]:
    return frozenset(
        window.open_ts + Timeframe.M1.duration * offset
        for window in windows
        for offset in range(
            KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
            KIS_INTRADAY_LAST_SIGNAL_OFFSET + 1,
        )
    )


def _candidate_comparison_campaign(
    contract: KisIntradayFeatureContract,
) -> CampaignContract:
    source = contract.campaign_plan.campaign
    source_fold = source.folds[0]
    windows = contract.candidate_comparison_session_windows
    return replace(
        source,
        campaign_id=f"{source.campaign_id}-candidate-comparison",
        folds=(
            CampaignFold(
                fold_id=source_fold.fold_id,
                development=source_fold.development,
                validation=CampaignWindow(windows[0].open_ts, windows[-1].close_ts),
            ),
        ),
    )


def _window_payload(window: SessionWindow) -> dict[str, str]:
    return {
        "open_utc": window.open_ts.isoformat(),
        "close_utc": window.close_ts.isoformat(),
    }


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_run_label(run_label: str) -> None:
    if not run_label.strip() or any(character in run_label for character in ("/", "\\", ":")):
        raise ValueError("run_label must be nonempty and contain no path separators")


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if repo_root == docker_repo_root and (
            path == docker_artifact_root or docker_artifact_root in path.parents
        ):
            return
    if path == repo_root or repo_root in path.parents:
        raise ValueError("KIS intraday feature artifacts must stay outside the Git workspace")

"""Frozen nonlinear tree breadth candidate for the QQQ/SPY daily contract.

The existing daily linear and sequence screens have different inductive biases.
This campaign adds one deliberately shallow, deterministic histogram-gradient
tree candidate. It fits development labels only, persists no pickle or fitted
estimator, and sends validation decisions only through broker-free
``local_paper`` replay.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, ModelPrediction, Signal, Timeframe
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.execution import LOCAL_PAPER_SOURCE

from .campaign import CampaignContract, NaiveBaselineId
from .kis_daily_sequence_architecture_screen import (
    KIS_DAILY_SEQUENCE_FEATURE_NAMES,
    KIS_DAILY_SEQUENCE_FOLD_ID,
    KIS_DAILY_SEQUENCE_LENGTH,
    KIS_DAILY_SEQUENCE_SYMBOLS,
    KisDailySequenceSample,
    KisDailySequenceScreenInput,
    build_kis_daily_sequence_screen_input,
)
from .validation import (
    CampaignReplayRun,
    NaiveBaselineRun,
    run_campaign_model_replay,
    run_naive_cpu_baseline,
)

KIS_DAILY_REGIME_TREE_BREADTH_ID = "kis-daily-regime-tree-breadth-v1"
KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID = "hist_gradient_tree"
KIS_DAILY_REGIME_TREE_BREADTH_MAX_ITER = 96
KIS_DAILY_REGIME_TREE_BREADTH_LEARNING_RATE = 0.05
KIS_DAILY_REGIME_TREE_BREADTH_MAX_LEAF_NODES = 7
KIS_DAILY_REGIME_TREE_BREADTH_MIN_SAMPLES_LEAF = 30
KIS_DAILY_REGIME_TREE_BREADTH_L2 = 0.1
KIS_DAILY_REGIME_TREE_BREADTH_THRESHOLD = 0.5
KIS_DAILY_REGIME_TREE_BREADTH_DETERMINISTIC_SEED = 347
KIS_DAILY_REGIME_TREE_BREADTH_STARTING_CASH = Decimal("10000")
KIS_DAILY_REGIME_TREE_BREADTH_QUANTITY = Decimal("1")
KIS_DAILY_REGIME_TREE_BREADTH_FEATURE_WIDTH = (
    KIS_DAILY_SEQUENCE_LENGTH * len(KIS_DAILY_SEQUENCE_FEATURE_NAMES)
)
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class KisDailyRegimeTreeBreadthSpec:
    """One fixed shallow nonlinear candidate; parameter changes require a new campaign."""

    max_iter: int = KIS_DAILY_REGIME_TREE_BREADTH_MAX_ITER
    learning_rate: float = KIS_DAILY_REGIME_TREE_BREADTH_LEARNING_RATE
    max_leaf_nodes: int = KIS_DAILY_REGIME_TREE_BREADTH_MAX_LEAF_NODES
    min_samples_leaf: int = KIS_DAILY_REGIME_TREE_BREADTH_MIN_SAMPLES_LEAF
    l2_regularization: float = KIS_DAILY_REGIME_TREE_BREADTH_L2
    threshold: float = KIS_DAILY_REGIME_TREE_BREADTH_THRESHOLD
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.max_iter != KIS_DAILY_REGIME_TREE_BREADTH_MAX_ITER
            or self.learning_rate != KIS_DAILY_REGIME_TREE_BREADTH_LEARNING_RATE
            or self.max_leaf_nodes != KIS_DAILY_REGIME_TREE_BREADTH_MAX_LEAF_NODES
            or self.min_samples_leaf != KIS_DAILY_REGIME_TREE_BREADTH_MIN_SAMPLES_LEAF
            or self.l2_regularization != KIS_DAILY_REGIME_TREE_BREADTH_L2
            or self.threshold != KIS_DAILY_REGIME_TREE_BREADTH_THRESHOLD
        ):
            raise ValueError("KIS daily regime tree breadth hyperparameters are frozen")

    def to_payload(self) -> dict[str, object]:
        return {
            "family": "histogram_gradient_tree",
            "sequence_length": KIS_DAILY_SEQUENCE_LENGTH,
            "feature_names": list(KIS_DAILY_SEQUENCE_FEATURE_NAMES),
            "flattened_feature_width": KIS_DAILY_REGIME_TREE_BREADTH_FEATURE_WIDTH,
            "max_iter": self.max_iter,
            "learning_rate": self.learning_rate,
            "max_leaf_nodes": self.max_leaf_nodes,
            "min_samples_leaf": self.min_samples_leaf,
            "l2_regularization": self.l2_regularization,
            "early_stopping": False,
            "threshold": self.threshold,
            "training_scope": "pooled_qqq_spy_development_only",
        }


@dataclass(frozen=True)
class KisDailyRegimeTreeBreadthInput:
    """Hash-attested input that cannot fit a validation label."""

    sequence_input: KisDailySequenceScreenInput
    campaign: CampaignContract
    spec: KisDailyRegimeTreeBreadthSpec
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_campaign = replace(
            self.sequence_input.campaign,
            campaign_id=KIS_DAILY_REGIME_TREE_BREADTH_ID,
            deterministic_seed=KIS_DAILY_REGIME_TREE_BREADTH_DETERMINISTIC_SEED,
        )
        if (
            self.campaign != expected_campaign
            or any(sample.label is None for sample in self.sequence_input.development_samples)
            or any(
                sample.label is not None
                for samples in self.sequence_input.validation_samples_by_symbol.values()
                for sample in samples
            )
        ):
            raise ValueError("KIS daily regime tree breadth input is not phase-frozen")


@dataclass(frozen=True)
class KisDailyRegimeTreeBreadthModel:
    """In-memory fitted model identified without persisting unsafe serialized state."""

    spec: KisDailyRegimeTreeBreadthSpec
    development_input_hash: str
    standardizer_hash: str
    fit_prediction_hash: str
    fit_backend: Literal["hist_gradient_tree", "constant_class"]
    estimator: Any
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.development_input_hash)
            or not _is_sha256(self.standardizer_hash)
            or not _is_sha256(self.fit_prediction_hash)
            or self.fit_backend not in {"hist_gradient_tree", "constant_class"}
            or self.estimator is None
        ):
            raise ValueError("KIS daily regime tree breadth model is invalid")

    @property
    def model_identity_hash(self) -> str:
        return _sha256_payload(
            {
                "spec": self.spec.to_payload(),
                "development_input_hash": self.development_input_hash,
                "standardizer_hash": self.standardizer_hash,
                "fit_prediction_hash": self.fit_prediction_hash,
                "fit_backend": self.fit_backend,
            }
        )

    def probabilities(self, samples: Sequence[KisDailySequenceSample]) -> tuple[float, ...]:
        return _positive_class_probabilities(self.estimator, _feature_matrix(samples))


@dataclass(frozen=True)
class KisDailyRegimeTreeBreadthReplayCell:
    symbol: str
    prediction_hash: str
    replay: CampaignReplayRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or not _is_sha256(self.prediction_hash)
            or self.replay.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.result.campaign_phase != "validation"
        ):
            raise ValueError(
                "KIS daily regime tree replay requires validation local-paper evidence"
            )


@dataclass(frozen=True)
class KisDailyRegimeTreeBreadthBaselineCell:
    symbol: str
    baseline_id: NaiveBaselineId
    replay: NaiveBaselineRun
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or self.baseline_id not in {"flat", "always_long", "previous_bar_direction"}
            or self.replay.baseline_id != self.baseline_id
            or self.replay.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.replay_evidence.fill_source != LOCAL_PAPER_SOURCE
            or self.replay.result.campaign_phase != "validation"
        ):
            raise ValueError(
                "KIS daily regime tree baseline requires validation local-paper evidence"
            )


@dataclass(frozen=True)
class KisDailyRegimeTreeBreadthRun:
    """One descriptive run, intentionally ineligible for selection or promotion."""

    breadth_input: KisDailyRegimeTreeBreadthInput
    precommit_path: Path
    precommit_hash: str
    model: KisDailyRegimeTreeBreadthModel
    replay_cells: tuple[KisDailyRegimeTreeBreadthReplayCell, ...]
    baseline_cells: tuple[KisDailyRegimeTreeBreadthBaselineCell, ...]
    summary_path: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_cells", tuple(self.replay_cells))
        object.__setattr__(self, "baseline_cells", tuple(self.baseline_cells))
        expected_baselines = tuple(
            (symbol, baseline_id)
            for symbol in KIS_DAILY_SEQUENCE_SYMBOLS
            for baseline_id in self.breadth_input.campaign.naive_baselines
        )
        if (
            tuple(cell.symbol for cell in self.replay_cells) != KIS_DAILY_SEQUENCE_SYMBOLS
            or tuple((cell.symbol, cell.baseline_id) for cell in self.baseline_cells)
            != expected_baselines
            or not _is_sha256(self.precommit_hash)
            or not self.precommit_path.is_file()
            or not self.summary_path.is_file()
        ):
            raise ValueError("KIS daily regime tree breadth did not complete the frozen plan")


@dataclass(frozen=True)
class _KisDailyRegimeTreeDecisionModel:
    symbol: str
    samples_by_decision_end: Mapping[datetime, KisDailySequenceSample]
    probabilities_by_decision_end: Mapping[datetime, float]
    precommit_hash: str
    model_identity_hash: str
    lookback: int = KIS_DAILY_SEQUENCE_LENGTH

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "samples_by_decision_end",
            MappingProxyType(dict(self.samples_by_decision_end)),
        )
        object.__setattr__(
            self,
            "probabilities_by_decision_end",
            MappingProxyType(dict(self.probabilities_by_decision_end)),
        )
        if (
            self.symbol not in KIS_DAILY_SEQUENCE_SYMBOLS
            or set(self.samples_by_decision_end) != set(self.probabilities_by_decision_end)
            or not self.samples_by_decision_end
            or any(
                not math.isfinite(value) or not 0 <= value <= 1
                for value in self.probabilities_by_decision_end.values()
            )
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.model_identity_hash)
        ):
            raise ValueError("KIS daily regime tree decision model is invalid")

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        if len(bars) < self.lookback:
            raise ValueError("KIS daily regime tree requires 20 completed daily bars")
        latest = bars[-1]
        sample = self.samples_by_decision_end.get(latest.end_ts)
        probability = self.probabilities_by_decision_end.get(latest.end_ts)
        if sample is None or probability is None or latest.symbol != self.symbol:
            raise ValueError("KIS daily regime tree received a non-validation decision")
        tail = tuple(bars[-KIS_DAILY_SEQUENCE_LENGTH:])
        if (
            tail[0].start_ts != sample.history_start
            or tail[-1].start_ts != sample.decision_start
            or tail[-1].end_ts != sample.decision_end
            or any(not bar.complete for bar in tail)
        ):
            raise ValueError("KIS daily regime tree cannot use future or cross-phase data")
        action: Literal["buy", "hold"] = (
            "buy" if probability >= KIS_DAILY_REGIME_TREE_BREADTH_THRESHOLD else "hold"
        )
        confidence = Decimal(str(probability))
        signal = Signal(
            symbol=latest.symbol,
            market=latest.market,
            action=action,
            strength=confidence,
            reason="kis_daily_regime_tree_breadth",
            timeframe=Timeframe.D1,
            generated_at=latest.end_ts,
        )
        return ModelPrediction(
            model_id=KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID,
            model_version="1.0.0",
            symbol=latest.symbol,
            market=latest.market,
            signal=signal,
            confidence=confidence,
            expected_edge_bps=Decimal("0"),
            feature_window_end=latest.end_ts,
            metadata={
                "candidate_id": KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID,
                "decision_rule": "fixed_hist_gradient_tree_threshold",
                "threshold": KIS_DAILY_REGIME_TREE_BREADTH_THRESHOLD,
                "precommit_hash": self.precommit_hash,
                "model_identity_hash": self.model_identity_hash,
                "validation_only": True,
            },
        )


def build_kis_daily_regime_tree_breadth_input(
    catalog: KisPaperPrivateDailyCatalog,
) -> KisDailyRegimeTreeBreadthInput:
    """Freeze one nonlinear breadth candidate over the established QQQ/SPY geometry."""

    sequence_input = build_kis_daily_sequence_screen_input(catalog)
    campaign = replace(
        sequence_input.campaign,
        campaign_id=KIS_DAILY_REGIME_TREE_BREADTH_ID,
        deterministic_seed=KIS_DAILY_REGIME_TREE_BREADTH_DETERMINISTIC_SEED,
    )
    return KisDailyRegimeTreeBreadthInput(
        sequence_input=sequence_input,
        campaign=campaign,
        spec=KisDailyRegimeTreeBreadthSpec(),
    )


def fit_kis_daily_regime_tree_breadth(
    breadth_input: KisDailyRegimeTreeBreadthInput,
) -> KisDailyRegimeTreeBreadthModel:
    """Fit the precommitted classifier on development labels only."""

    samples = breadth_input.sequence_input.development_samples
    if not samples or any(sample.label is None for sample in samples):
        raise ValueError("KIS daily regime tree breadth requires development labels")
    numpy = _numpy()
    features = _feature_matrix(samples)
    labels = numpy.asarray([sample.label for sample in samples], dtype=numpy.int64)
    if (
        features.shape != (len(samples), KIS_DAILY_REGIME_TREE_BREADTH_FEATURE_WIDTH)
        or labels.shape != (len(samples),)
        or not numpy.isfinite(features).all()
        or not numpy.isin(labels, (0, 1)).all()
    ):
        raise ValueError("KIS daily regime tree breadth development matrix is invalid")
    observed_classes = frozenset(int(value) for value in labels)
    if len(observed_classes) == 1:
        classifier = _ConstantBinaryClassifier(next(iter(observed_classes)))
        fit_backend: Literal["hist_gradient_tree", "constant_class"] = "constant_class"
    else:
        classifier = _hist_gradient_boosting_classifier(
            max_iter=breadth_input.spec.max_iter,
            learning_rate=breadth_input.spec.learning_rate,
            max_leaf_nodes=breadth_input.spec.max_leaf_nodes,
            min_samples_leaf=breadth_input.spec.min_samples_leaf,
            l2_regularization=breadth_input.spec.l2_regularization,
            random_state=KIS_DAILY_REGIME_TREE_BREADTH_DETERMINISTIC_SEED,
            early_stopping=False,
        )
        classifier.fit(features, labels)
        fit_backend = "hist_gradient_tree"
    fit_prediction_hash = _sha256_payload(
        {
            "development_input_hash": breadth_input.sequence_input.development_input_hash,
            "probabilities": [
                format(value, ".17g")
                for value in _positive_class_probabilities(classifier, features)
            ],
        }
    )
    return KisDailyRegimeTreeBreadthModel(
        spec=breadth_input.spec,
        development_input_hash=breadth_input.sequence_input.development_input_hash,
        standardizer_hash=breadth_input.sequence_input.standardizer.standardizer_hash,
        fit_prediction_hash=fit_prediction_hash,
        fit_backend=fit_backend,
        estimator=classifier,
    )


def run_kis_daily_regime_tree_breadth(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
) -> KisDailyRegimeTreeBreadthRun:
    """Run one offline CPU tree breadth candidate and fixed local-paper baselines."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    _reject_repo_path(resolved_artifact_root, repo_root=_MODULE_REPOSITORY_ROOT)
    campaign_root = (resolved_artifact_root / KIS_DAILY_REGIME_TREE_BREADTH_ID).resolve()
    _reject_repo_path(campaign_root, repo_root=resolved_repo_root)
    _reject_repo_path(campaign_root, repo_root=_MODULE_REPOSITORY_ROOT)
    output_dir = (campaign_root / run_label).resolve()
    if not output_dir.is_relative_to(campaign_root):
        raise ValueError("KIS daily regime tree artifact path escapes its root")
    _reject_repo_path(output_dir, repo_root=resolved_repo_root)
    _reject_repo_path(output_dir, repo_root=_MODULE_REPOSITORY_ROOT)
    if output_dir.exists():
        raise FileExistsError("KIS daily regime tree breadth artifact already exists")

    breadth_input = build_kis_daily_regime_tree_breadth_input(catalog)
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(breadth_input)
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, precommit_payload)

    try:
        model = fit_kis_daily_regime_tree_breadth(breadth_input)
        replay_cells = _run_model_replays(
            breadth_input=breadth_input,
            model=model,
            precommit_hash=precommit_hash,
            artifact_root=resolved_artifact_root,
            output_dir=output_dir,
            repo_root=resolved_repo_root,
            run_label=run_label,
        )
        baseline_cells = _run_baseline_replays(
            breadth_input=breadth_input,
            artifact_root=resolved_artifact_root,
            output_dir=output_dir,
            repo_root=resolved_repo_root,
            run_label=run_label,
        )
    except Exception as error:
        _write_json_new(
            output_dir / "incomplete.json",
            {
                "schema_version": SCHEMA_VERSION,
                "status": "incomplete",
                "campaign_id": KIS_DAILY_REGIME_TREE_BREADTH_ID,
                "precommit_hash": precommit_hash,
                "failure_class": type(error).__name__,
                "selection_allowed": False,
                "ensemble_allowed": False,
                "promotion_allowed": False,
                "serialized_model_written": False,
                "raw_market_data_written": False,
            },
        )
        raise

    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            breadth_input=breadth_input,
            precommit_hash=precommit_hash,
            model=model,
            replay_cells=replay_cells,
            baseline_cells=baseline_cells,
        ),
    )
    return KisDailyRegimeTreeBreadthRun(
        breadth_input=breadth_input,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        model=model,
        replay_cells=replay_cells,
        baseline_cells=baseline_cells,
        summary_path=summary_path,
    )


def _precommit_payload(breadth_input: KisDailyRegimeTreeBreadthInput) -> dict[str, object]:
    sequence_input = breadth_input.sequence_input
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "precommitted",
        "campaign_id": KIS_DAILY_REGIME_TREE_BREADTH_ID,
        "claim": (
            "fixed shallow nonlinear histogram-gradient tree breadth candidate and fixed "
            "naive comparators; descriptive validation only, with no winner, selection, "
            "ensemble, promotion, profitability claim, or paper-order decision"
        ),
        "source": {
            "dataset_id": sequence_input.catalog.dataset_id,
            "dataset_hash": sequence_input.catalog.dataset_hash,
            "index_hash": sequence_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "adjustment_mode": sequence_input.catalog.adjustment_mode,
            "limitations": list(sequence_input.catalog.raw_price_limitations),
            "source_mixing_allowed": False,
        },
        "campaign_contract_hash": breadth_input.campaign.contract_hash,
        "chronological_split": sequence_input.split.to_payload(),
        "model": breadth_input.spec.to_payload(),
        "training": {
            "development_input_hash": sequence_input.development_input_hash,
            "development_sample_count": len(sequence_input.development_samples),
            "fit_split": "pooled_qqq_spy_development_only",
            "single_class_fallback": "constant_probability_without_tree_fit",
            "validation_labels_materialized_for_fit": False,
            "gpu_used": False,
            "stop_rule": "fit_error_or_nonfinite_probability_or_nonlocal_paper_replay",
        },
        "replay_sizing": _replay_sizing_payload(),
        "validation": {
            "validation_input_hash": sequence_input.validation_input_hash,
            "sample_counts": {
                symbol: len(samples)
                for symbol, samples in sequence_input.validation_samples_by_symbol.items()
            },
            "labels_materialized_for_fit": False,
            "tuning_allowed": False,
        },
        "comparators": list(breadth_input.campaign.naive_baselines),
        "target": {
            "decision": "completed_daily_bar_close",
            "entry": "next_observed_daily_open",
            "exit": "following_observed_daily_open",
            "replay_fill_source": LOCAL_PAPER_SOURCE,
            "non_overlapping_decision_stride_sessions": 2,
        },
        "falsification": {
            "claim": "nonlinear completed-bar regimes may add signal beyond fixed controls",
            "strongest_kill_test": (
                "after-cost local-paper replay fails to exceed previous_bar_direction "
                "for either QQQ or SPY"
            ),
            "follow_up_requires": "two-symbol after-cost improvement without retuning",
        },
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "sealed_holdout_materialized": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "serialized_model_written": False,
            "raw_market_data_written": False,
        },
    }


def _run_model_replays(
    *,
    breadth_input: KisDailyRegimeTreeBreadthInput,
    model: KisDailyRegimeTreeBreadthModel,
    precommit_hash: str,
    artifact_root: Path,
    output_dir: Path,
    repo_root: Path,
    run_label: str,
) -> tuple[KisDailyRegimeTreeBreadthReplayCell, ...]:
    cells: list[KisDailyRegimeTreeBreadthReplayCell] = []
    sequence_input = breadth_input.sequence_input
    for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
        samples = sequence_input.validation_samples_by_symbol[symbol]
        probabilities = model.probabilities(samples)
        prediction_hash = _sha256_payload(
            {
                "precommit_hash": precommit_hash,
                "model_identity_hash": model.model_identity_hash,
                "symbol": symbol,
                "validation_input_hash": sequence_input.validation_input_hash,
                "probabilities": [format(value, ".17g") for value in probabilities],
            }
        )
        decision_model = _KisDailyRegimeTreeDecisionModel(
            symbol=symbol,
            samples_by_decision_end={sample.decision_end: sample for sample in samples},
            probabilities_by_decision_end={
                sample.decision_end: probability
                for sample, probability in zip(samples, probabilities, strict=True)
            },
            precommit_hash=precommit_hash,
            model_identity_hash=model.model_identity_hash,
        )
        replay = run_campaign_model_replay(
            sequence_input.catalog.bars_by_symbol[symbol],
            campaign=breadth_input.campaign,
            model=decision_model,
            run_id=(
                f"{KIS_DAILY_REGIME_TREE_BREADTH_ID}-"
                f"{KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID}-{symbol.lower()}-{run_label}"
            ),
            artifact_root=artifact_root,
            work_dir=(
                output_dir / "work" / KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID / symbol
            ),
            phase="validation",
            fold_id=KIS_DAILY_SEQUENCE_FOLD_ID,
            repo_root=repo_root,
            starting_cash=KIS_DAILY_REGIME_TREE_BREADTH_STARTING_CASH,
            quantity=KIS_DAILY_REGIME_TREE_BREADTH_QUANTITY,
            eligible_signal_starts=frozenset(sample.decision_start for sample in samples),
            emergency_reason="kis_daily_regime_tree_breadth_validation_only",
        )
        cells.append(
            KisDailyRegimeTreeBreadthReplayCell(
                symbol=symbol,
                prediction_hash=prediction_hash,
                replay=replay,
            )
        )
    return tuple(cells)


def _run_baseline_replays(
    *,
    breadth_input: KisDailyRegimeTreeBreadthInput,
    artifact_root: Path,
    output_dir: Path,
    repo_root: Path,
    run_label: str,
) -> tuple[KisDailyRegimeTreeBreadthBaselineCell, ...]:
    cells: list[KisDailyRegimeTreeBreadthBaselineCell] = []
    sequence_input = breadth_input.sequence_input
    for symbol in KIS_DAILY_SEQUENCE_SYMBOLS:
        eligible_signal_starts = frozenset(
            sample.decision_start for sample in sequence_input.validation_samples_by_symbol[symbol]
        )
        for baseline_id in breadth_input.campaign.naive_baselines:
            replay = run_naive_cpu_baseline(
                sequence_input.catalog.bars_by_symbol[symbol],
                campaign=breadth_input.campaign,
                artifact_root=artifact_root,
                work_dir=output_dir / "work" / "naive" / symbol / baseline_id,
                phase="validation",
                fold_id=KIS_DAILY_SEQUENCE_FOLD_ID,
                baseline_id=baseline_id,
                repo_root=repo_root,
                starting_cash=KIS_DAILY_REGIME_TREE_BREADTH_STARTING_CASH,
                quantity=KIS_DAILY_REGIME_TREE_BREADTH_QUANTITY,
                run_label=f"{run_label}-{symbol.lower()}",
                eligible_signal_starts=eligible_signal_starts,
            )
            cells.append(
                KisDailyRegimeTreeBreadthBaselineCell(
                    symbol=symbol,
                    baseline_id=baseline_id,
                    replay=replay,
                )
            )
    return tuple(cells)


def _summary_payload(
    *,
    breadth_input: KisDailyRegimeTreeBreadthInput,
    precommit_hash: str,
    model: KisDailyRegimeTreeBreadthModel,
    replay_cells: tuple[KisDailyRegimeTreeBreadthReplayCell, ...],
    baseline_cells: tuple[KisDailyRegimeTreeBreadthBaselineCell, ...],
) -> dict[str, object]:
    sequence_input = breadth_input.sequence_input
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_cpu_local_paper",
        "claim": (
            "fixed shallow nonlinear histogram-gradient tree breadth candidate and naive "
            "comparators only; not a winner, selection, ensemble, promotion, profitability "
            "claim, or paper order"
        ),
        "source": {
            "dataset_id": sequence_input.catalog.dataset_id,
            "dataset_hash": sequence_input.catalog.dataset_hash,
            "index_hash": sequence_input.catalog.index_hash,
            "symbols": list(KIS_DAILY_SEQUENCE_SYMBOLS),
            "adjustment_mode": sequence_input.catalog.adjustment_mode,
            "limitations": list(sequence_input.catalog.raw_price_limitations),
        },
        "campaign_contract_hash": breadth_input.campaign.contract_hash,
        "chronological_split": sequence_input.split.to_payload(),
        "precommit": {
            "hash": precommit_hash,
            "written_before_fit": True,
            "written_before_validation_replay": True,
        },
        "model": {
            "candidate_id": KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID,
            "identity_hash": model.model_identity_hash,
            "development_input_hash": model.development_input_hash,
            "standardizer_hash": model.standardizer_hash,
            "fit_prediction_hash": model.fit_prediction_hash,
            "fit_backend": model.fit_backend,
            "spec": model.spec.to_payload(),
            "serialized_model_written": False,
        },
        "validation": {
            "input_hash": sequence_input.validation_input_hash,
            "labels_materialized_for_fit": False,
            "tuning_allowed": False,
        },
        "replay_sizing": _replay_sizing_payload(),
        "replay_cells": [_model_replay_payload(cell) for cell in replay_cells],
        "baseline_cells": [_baseline_replay_payload(cell) for cell in baseline_cells],
        "falsification": {
            "candidate_is_eligible_for_follow_up": False,
            "follow_up_requires": "two-symbol after-cost improvement without retuning",
        },
        "reporting": {
            "winner": None,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "promotion_allowed": False,
            "sealed_holdout_materialized": False,
        },
        "artifact_policy": {
            "repo_storage_allowed": False,
            "serialized_model_written": False,
            "raw_market_data_written": False,
        },
    }


def _model_replay_payload(cell: KisDailyRegimeTreeBreadthReplayCell) -> dict[str, object]:
    result = cell.replay.result
    return {
        "candidate_id": KIS_DAILY_REGIME_TREE_BREADTH_CANDIDATE_ID,
        "symbol": cell.symbol,
        "prediction_hash": cell.prediction_hash,
        "fill_source": cell.replay.fill_source,
        "decisions_seen": result.decisions_seen,
        "trade_count": len(result.trades),
        "after_cost_pnl": str(result.after_cost_pnl),
        "gross_pnl": str(result.gross_pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "event_jsonl_sha256": cell.replay.replay_evidence.event_jsonl_sha256,
        "state_sqlite_sha256": cell.replay.replay_evidence.state_sqlite_sha256,
    }


def _baseline_replay_payload(cell: KisDailyRegimeTreeBreadthBaselineCell) -> dict[str, object]:
    result = cell.replay.result
    return {
        "candidate_id": cell.baseline_id,
        "symbol": cell.symbol,
        "fill_source": cell.replay.fill_source,
        "decisions_seen": result.decisions_seen,
        "trade_count": len(result.trades),
        "after_cost_pnl": str(result.after_cost_pnl),
        "gross_pnl": str(result.gross_pnl),
        "total_fees": str(result.total_fees),
        "total_slippage": str(result.total_slippage),
        "event_jsonl_sha256": cell.replay.replay_evidence.event_jsonl_sha256,
        "state_sqlite_sha256": cell.replay.replay_evidence.state_sqlite_sha256,
    }


def _feature_matrix(samples: Sequence[KisDailySequenceSample]) -> Any:
    numpy = _numpy()
    features = numpy.asarray(
        [_flatten_features(sample.features) for sample in samples], dtype=numpy.float64
    )
    if (
        features.shape != (len(samples), KIS_DAILY_REGIME_TREE_BREADTH_FEATURE_WIDTH)
        or not numpy.isfinite(features).all()
    ):
        raise ValueError("KIS daily regime tree feature matrix is invalid")
    return features


def _positive_class_probabilities(estimator: Any, features: Any) -> tuple[float, ...]:
    numpy = _numpy()
    probabilities = numpy.asarray(estimator.predict_proba(features), dtype=numpy.float64)
    classes = tuple(int(value) for value in estimator.classes_)
    if probabilities.ndim != 2 or probabilities.shape[0] != features.shape[0] or not classes:
        raise ValueError("KIS daily regime tree probabilities are invalid")
    if 1 in classes:
        positive = probabilities[:, classes.index(1)]
    elif classes == (0,):
        positive = numpy.zeros(features.shape[0], dtype=numpy.float64)
    else:
        raise ValueError("KIS daily regime tree classifier classes are invalid")
    if positive.shape != (features.shape[0],) or not numpy.isfinite(positive).all():
        raise ValueError("KIS daily regime tree positive probabilities are invalid")
    values = tuple(float(value) for value in positive)
    if any(not 0 <= value <= 1 for value in values):
        raise ValueError("KIS daily regime tree positive probabilities are outside [0, 1]")
    return values


def _flatten_features(features: Sequence[Sequence[float]]) -> tuple[float, ...]:
    flattened = tuple(float(value) for row in features for value in row)
    if (
        len(features) != KIS_DAILY_SEQUENCE_LENGTH
        or any(len(row) != len(KIS_DAILY_SEQUENCE_FEATURE_NAMES) for row in features)
        or len(flattened) != KIS_DAILY_REGIME_TREE_BREADTH_FEATURE_WIDTH
        or any(not math.isfinite(value) for value in flattened)
    ):
        raise ValueError("KIS daily regime tree feature geometry is invalid")
    return flattened


def _replay_sizing_payload() -> dict[str, str]:
    return {
        "starting_cash": str(KIS_DAILY_REGIME_TREE_BREADTH_STARTING_CASH),
        "quantity": str(KIS_DAILY_REGIME_TREE_BREADTH_QUANTITY),
    }


def _hist_gradient_boosting_classifier(**kwargs: object) -> Any:
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(**kwargs)


@dataclass(frozen=True)
class _ConstantBinaryClassifier:
    """Keep a one-class development slice reproducible without fake tree state."""

    positive_class: int

    def __post_init__(self) -> None:
        if self.positive_class not in {0, 1}:
            raise ValueError("KIS daily regime tree constant class is invalid")

    @property
    def classes_(self) -> tuple[int, ...]:
        return (self.positive_class,)

    def predict_proba(self, features: Any) -> Any:
        numpy = _numpy()
        return numpy.full(
            (features.shape[0], 1),
            1.0,
            dtype=numpy.float64,
        )


def _numpy() -> Any:
    import numpy

    return numpy


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: str) -> bool:
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


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_run_label(run_label: str) -> None:
    if (
        not isinstance(run_label, str)
        or not 1 <= len(run_label) <= 80
        or run_label in {".", ".."}
        or any(
            not character.isascii()
            or not (character.isalnum() or character in {".", "_", "-"})
            for character in run_label
        )
    ):
        raise ValueError("KIS daily regime tree run_label is invalid")


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if repo_root == docker_repo_root and (
            path == docker_artifact_root or docker_artifact_root in path.parents
        ):
            return
    if path.is_relative_to(repo_root):
        raise ValueError("KIS daily regime tree artifacts must stay outside the Git workspace")

"""Offline, null-first window-sensitivity preflight for retained KIS intraday data."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data import CatalogedBars, SessionWindow

from .kis_intraday_campaign import (
    KIS_INTRADAY_LAST_SIGNAL_OFFSET,
    KIS_INTRADAY_REGULAR_SESSION_MINUTES,
    KisIntradayCpuCampaignPlan,
    build_kis_intraday_cpu_campaign_plan,
)

KIS_INTRADAY_WINDOW_MATRIX_ID = "kis-intraday-window-matrix-v1"
KIS_INTRADAY_WINDOW_MATRIX_WINDOWS = (30, 60, 90, 120, 180)
KIS_INTRADAY_WINDOW_MATRIX_NULL_REPLICATES = 32
KIS_INTRADAY_WINDOW_MATRIX_OPTIMIZER_STEPS = 64
KIS_INTRADAY_WINDOW_MATRIX_LEARNING_RATE = 0.05
KIS_INTRADAY_WINDOW_MATRIX_COST_MULTIPLIERS = ("1.0x", "1.5x", "2.0x")
KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_DEVELOPMENT_BLOCKS = 10
KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_COMPARISON_BLOCKS = 9
KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_OBSERVATIONS_PER_BLOCK = 32


@dataclass(frozen=True)
class KisIntradayWindowMatrixCellResult:
    """In-memory result for one frozen lookback; it is never ranked in artifacts."""

    window_bars: int
    development_observation_count: int
    comparison_observation_count: int
    development_block_count: int
    comparison_block_count: int
    brier_score: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.window_bars not in KIS_INTRADAY_WINDOW_MATRIX_WINDOWS
            or self.development_observation_count <= 0
            or self.comparison_observation_count <= 0
            or self.development_block_count < KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_DEVELOPMENT_BLOCKS
            or self.comparison_block_count < KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_COMPARISON_BLOCKS
            or not math.isfinite(self.brier_score)
            or not 0 <= self.brier_score <= 1
        ):
            raise ValueError("KIS intraday window-matrix cell result is invalid")


@dataclass(frozen=True)
class KisIntradayWindowMatrixPreflightRun:
    """External evidence for a descriptive CPU structure gate, never a model result."""

    status: Literal["complete", "input_unavailable"]
    structure_gate: Literal["structure_present", "no_structure", "input_unavailable"]
    plan: KisIntradayCpuCampaignPlan
    precommit_path: Path
    precommit_hash: str
    summary_path: Path
    cell_results: tuple[KisIntradayWindowMatrixCellResult, ...]
    null_spread_p95: float | None
    null_minimum_brier_p05: float | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "cell_results", tuple(self.cell_results))
        if self.status == "complete":
            if (
                len(self.cell_results) != len(KIS_INTRADAY_WINDOW_MATRIX_WINDOWS)
                or self.null_spread_p95 is None
                or self.null_minimum_brier_p05 is None
            ):
                raise ValueError("complete KIS intraday window preflight is incomplete")
        elif (
            self.structure_gate != "input_unavailable"
            or self.cell_results
            or self.null_spread_p95 is not None
            or self.null_minimum_brier_p05 is not None
        ):
            raise ValueError("input-unavailable KIS intraday window preflight is invalid")

    @property
    def cuda_eligible(self) -> bool:
        return self.status == "complete" and self.structure_gate == "structure_present"


@dataclass(frozen=True)
class _WindowSample:
    session_date: date
    features: tuple[float, float, float, float]
    target_label: int

    def __post_init__(self) -> None:
        if (
            type(self.session_date) is not date
            or self.target_label not in (0, 1)
            or len(self.features) != 4
            or any(not math.isfinite(value) for value in self.features)
        ):
            raise ValueError("KIS intraday window-matrix sample is invalid")


@dataclass(frozen=True)
class _LogisticModel:
    means: tuple[float, float, float, float]
    scales: tuple[float, float, float, float]
    weights: tuple[float, float, float, float]
    bias: float


class _InputUnavailable(ValueError):
    """A source-safe input category for a single frozen matrix."""


def run_kis_intraday_window_matrix_preflight(
    catalog: CatalogedBars,
    *,
    session_dates: Sequence[date],
    artifact_root: Path,
    run_label: str,
    repo_root: Path | None = None,
) -> KisIntradayWindowMatrixPreflightRun:
    """Run the fixed CPU null-first preflight without network, credentials, or broker effects."""

    _validate_run_label(run_label)
    resolved_repo_root = (repo_root or Path.cwd()).resolve()
    resolved_artifact_root = Path(artifact_root).resolve()
    _reject_repo_path(resolved_artifact_root, repo_root=resolved_repo_root)
    output_dir = resolved_artifact_root / "research" / "kis-intraday-window-matrix-v1" / run_label
    if output_dir.exists():
        raise FileExistsError(f"KIS intraday window-matrix artifact already exists: {output_dir}")

    plan = build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=tuple(session_dates),
        campaign_id=KIS_INTRADAY_WINDOW_MATRIX_ID,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    precommit_payload = _precommit_payload(plan=plan)
    precommit_hash = _sha256_payload(precommit_payload)
    precommit_payload["precommit_hash"] = precommit_hash
    precommit_path = output_dir / "precommit.json"
    _write_json_new(precommit_path, precommit_payload)

    try:
        matrix_inputs = _build_matrix_inputs(plan)
    except _InputUnavailable:
        summary_path = output_dir / "summary.json"
        _write_json_new(
            summary_path,
            _input_unavailable_summary(
                plan=plan,
                precommit_path=precommit_path,
                precommit_hash=precommit_hash,
                artifact_root=resolved_artifact_root,
            ),
        )
        return KisIntradayWindowMatrixPreflightRun(
            status="input_unavailable",
            structure_gate="input_unavailable",
            plan=plan,
            precommit_path=precommit_path,
            precommit_hash=precommit_hash,
            summary_path=summary_path,
            cell_results=(),
            null_spread_p95=None,
            null_minimum_brier_p05=None,
        )

    # The block-permuted null is deliberately evaluated before the real labels.
    null_spreads, null_minimum_briers = _evaluate_permuted_null(matrix_inputs)
    null_spread_p95 = _percentile(null_spreads, 0.95)
    null_minimum_brier_p05 = _percentile(null_minimum_briers, 0.05)
    cell_results = tuple(
        _evaluate_real_cell(window_bars, development, comparison)
        for window_bars, development, comparison in matrix_inputs
    )
    real_briers = tuple(item.brier_score for item in cell_results)
    real_spread = max(real_briers) - min(real_briers)
    structure_gate: Literal["structure_present", "no_structure"] = (
        "structure_present"
        if real_spread > null_spread_p95 and min(real_briers) < null_minimum_brier_p05
        else "no_structure"
    )

    summary_path = output_dir / "summary.json"
    _write_json_new(
        summary_path,
        _summary_payload(
            plan=plan,
            precommit_path=precommit_path,
            precommit_hash=precommit_hash,
            artifact_root=resolved_artifact_root,
            cell_results=cell_results,
            null_spread_p95=null_spread_p95,
            null_minimum_brier_p05=null_minimum_brier_p05,
            structure_gate=structure_gate,
        ),
    )
    return KisIntradayWindowMatrixPreflightRun(
        status="complete",
        structure_gate=structure_gate,
        plan=plan,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
        cell_results=cell_results,
        null_spread_p95=null_spread_p95,
        null_minimum_brier_p05=null_minimum_brier_p05,
    )


def _build_matrix_inputs(
    plan: KisIntradayCpuCampaignPlan,
) -> tuple[tuple[int, tuple[_WindowSample, ...], tuple[_WindowSample, ...]], ...]:
    outputs: list[tuple[int, tuple[_WindowSample, ...], tuple[_WindowSample, ...]]] = []
    for window_bars in KIS_INTRADAY_WINDOW_MATRIX_WINDOWS:
        development = _samples_for_phase(plan, phase="development", window_bars=window_bars)
        comparison = _samples_for_phase(plan, phase="comparison", window_bars=window_bars)
        if (
            len(_session_dates(development))
            < KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_DEVELOPMENT_BLOCKS
            or len(_session_dates(comparison))
            < KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_COMPARISON_BLOCKS
            or _minimum_block_size(development)
            < KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_OBSERVATIONS_PER_BLOCK
            or _minimum_block_size(comparison)
            < KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_OBSERVATIONS_PER_BLOCK
        ):
            raise _InputUnavailable("window matrix lacks complete causal block support")
        outputs.append((window_bars, development, comparison))
    return tuple(outputs)


def _samples_for_phase(
    plan: KisIntradayCpuCampaignPlan,
    *,
    phase: Literal["development", "comparison"],
    window_bars: int,
) -> tuple[_WindowSample, ...]:
    if window_bars not in KIS_INTRADAY_WINDOW_MATRIX_WINDOWS:
        raise _InputUnavailable("window matrix cell is not frozen")
    if phase == "development":
        session_dates = plan.development_session_dates
        session_windows = plan.phase_session_windows("development")
    else:
        session_dates = plan.validation_session_dates
        session_windows = plan.phase_session_windows("validation")
    bars_by_session = _bars_by_session(plan.cataloged_bars, session_windows)
    samples: list[_WindowSample] = []
    for session_date, session_window in zip(session_dates, session_windows, strict=True):
        session_bars = bars_by_session.get(session_window.open_ts)
        if session_bars is None:
            raise _InputUnavailable("window matrix session is unavailable")
        for signal_offset in range(window_bars - 1, KIS_INTRADAY_LAST_SIGNAL_OFFSET + 1):
            history = session_bars[signal_offset - (window_bars - 1) : signal_offset + 1]
            entry_bar = session_bars[signal_offset + 1]
            exit_bar = session_bars[signal_offset + 2]
            if (
                len(history) != window_bars
                or history[0].start_ts < session_window.open_ts
                or history[-1].end_ts != entry_bar.start_ts
                or entry_bar.end_ts != exit_bar.start_ts
                or exit_bar.end_ts > session_window.close_ts
            ):
                raise _InputUnavailable(
                    "window matrix history or target crosses a session boundary"
                )
            samples.append(
                _WindowSample(
                    session_date=session_date,
                    features=_feature_values(history),
                    target_label=1 if exit_bar.open > entry_bar.open else 0,
                )
            )
    return tuple(samples)


def _bars_by_session(
    catalog: CatalogedBars,
    session_windows: Sequence[SessionWindow],
) -> Mapping[object, tuple[Bar, ...]]:
    selected: dict[object, tuple[Bar, ...]] = {}
    for window in session_windows:
        bars = tuple(
            bar
            for bar in catalog.bars
            if window.open_ts <= bar.start_ts and bar.end_ts <= window.close_ts
        )
        expected_starts = tuple(
            window.open_ts + Timeframe.M1.duration * index
            for index in range(KIS_INTRADAY_REGULAR_SESSION_MINUTES)
        )
        if (
            len(bars) != KIS_INTRADAY_REGULAR_SESSION_MINUTES
            or tuple(item.start_ts for item in bars) != expected_starts
            or any(item.timeframe != Timeframe.M1 or not item.complete for item in bars)
        ):
            raise _InputUnavailable("window matrix session has missing or incomplete minutes")
        selected[window.open_ts] = bars
    return selected


def _feature_values(history: tuple[Bar, ...]) -> tuple[float, float, float, float]:
    first = history[0]
    latest = history[-1]
    minute_returns = tuple(
        float(item.close / previous.close - 1)
        for previous, item in zip(history[:-1], history[1:], strict=True)
    )
    ranges = tuple(float((item.high - item.low) / item.open) for item in history)
    average_volume = math.fsum(float(item.volume) for item in history) / len(history)
    volume_ratio = 0.0 if average_volume == 0 else float(latest.volume) / average_volume - 1.0
    values = (
        float(latest.close / first.close - 1),
        math.fsum(minute_returns) / len(minute_returns),
        math.fsum(ranges) / len(ranges),
        volume_ratio,
    )
    if any(not math.isfinite(value) for value in values):
        raise _InputUnavailable("window matrix feature is non-finite")
    return values


def _evaluate_permuted_null(
    matrix_inputs: Sequence[tuple[int, tuple[_WindowSample, ...], tuple[_WindowSample, ...]]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    null_spreads: list[float] = []
    null_minimum_briers: list[float] = []
    for replicate_index in range(KIS_INTRADAY_WINDOW_MATRIX_NULL_REPLICATES):
        briers: list[float] = []
        for window_bars, development, comparison in matrix_inputs:
            del window_bars
            development_labels = _permuted_block_labels(
                development,
                replicate_index,
                phase="development",
            )
            comparison_labels = _permuted_block_labels(
                comparison,
                replicate_index,
                phase="comparison",
            )
            model = _fit_logistic(development, development_labels)
            briers.append(_brier_score(model, comparison, comparison_labels))
        null_spreads.append(max(briers) - min(briers))
        null_minimum_briers.append(min(briers))
    return tuple(null_spreads), tuple(null_minimum_briers)


def _evaluate_real_cell(
    window_bars: int,
    development: tuple[_WindowSample, ...],
    comparison: tuple[_WindowSample, ...],
) -> KisIntradayWindowMatrixCellResult:
    model = _fit_logistic(development, tuple(item.target_label for item in development))
    return KisIntradayWindowMatrixCellResult(
        window_bars=window_bars,
        development_observation_count=len(development),
        comparison_observation_count=len(comparison),
        development_block_count=len(_session_dates(development)),
        comparison_block_count=len(_session_dates(comparison)),
        brier_score=_brier_score(
            model,
            comparison,
            tuple(item.target_label for item in comparison),
        ),
    )


def _permuted_block_labels(
    samples: Sequence[_WindowSample],
    replicate_index: int,
    *,
    phase: Literal["development", "comparison"],
) -> tuple[int, ...]:
    grouped: dict[date, list[int]] = defaultdict(list)
    for sample in samples:
        grouped[sample.session_date].append(sample.target_label)
    session_dates = tuple(sorted(grouped))
    if len(session_dates) < 2 or len({len(grouped[item]) for item in session_dates}) != 1:
        raise _InputUnavailable("window matrix cannot permute unequal session blocks")
    source_dates = list(session_dates)
    random.Random(71_000 + replicate_index * 2 + (0 if phase == "development" else 1)).shuffle(
        source_dates
    )
    if source_dates == list(session_dates):
        source_dates = source_dates[1:] + source_dates[:1]
    source_for_target = dict(zip(session_dates, source_dates, strict=True))
    positions: dict[date, int] = defaultdict(int)
    labels: list[int] = []
    for sample in samples:
        source = source_for_target[sample.session_date]
        position = positions[sample.session_date]
        labels.append(grouped[source][position])
        positions[sample.session_date] += 1
    return tuple(labels)


def _fit_logistic(
    samples: Sequence[_WindowSample],
    labels: Sequence[int],
) -> _LogisticModel:
    if not samples or len(samples) != len(labels) or any(label not in (0, 1) for label in labels):
        raise _InputUnavailable("window matrix logistic input is invalid")
    import numpy as np

    features = _feature_matrix(samples, np=np)
    target = np.asarray(labels, dtype=np.float64)
    means = features.mean(axis=0)
    scales = np.maximum(features.std(axis=0), 1e-12)
    normalized = (features - means) / scales
    weights = np.zeros(features.shape[1], dtype=np.float64)
    bias = 0.0
    for _ in range(KIS_INTRADAY_WINDOW_MATRIX_OPTIMIZER_STEPS):
        logits = np.clip(normalized @ weights + bias, -60.0, 60.0)
        errors = 1.0 / (1.0 + np.exp(-logits)) - target
        weights -= KIS_INTRADAY_WINDOW_MATRIX_LEARNING_RATE * (normalized.T @ errors) / len(
            normalized
        )
        bias -= KIS_INTRADAY_WINDOW_MATRIX_LEARNING_RATE * float(errors.mean())
    return _LogisticModel(
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        weights=tuple(float(value) for value in weights),
        bias=bias,
    )


def _brier_score(
    model: _LogisticModel,
    samples: Sequence[_WindowSample],
    labels: Sequence[int],
) -> float:
    if not samples or len(samples) != len(labels):
        raise _InputUnavailable("window matrix brier input is invalid")
    import numpy as np

    features = _feature_matrix(samples, np=np)
    means = np.asarray(model.means, dtype=np.float64)
    scales = np.asarray(model.scales, dtype=np.float64)
    weights = np.asarray(model.weights, dtype=np.float64)
    logits = np.clip((features - means) @ (weights / scales) + model.bias, -60.0, 60.0)
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    targets = np.asarray(labels, dtype=np.float64)
    return float(np.mean((probabilities - targets) ** 2))


def _feature_matrix(samples: Sequence[_WindowSample], *, np: object) -> object:
    return np.asarray(tuple(sample.features for sample in samples), dtype=np.float64)


def _session_dates(samples: Sequence[_WindowSample]) -> frozenset[date]:
    return frozenset(sample.session_date for sample in samples)


def _minimum_block_size(samples: Sequence[_WindowSample]) -> int:
    counts: dict[date, int] = defaultdict(int)
    for sample in samples:
        counts[sample.session_date] += 1
    return min(counts.values(), default=0)


def _precommit_payload(*, plan: KisIntradayCpuCampaignPlan) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "precommitted",
        "mode": "offline_cpu_window_sensitivity",
        "claim": (
            "null-first descriptive window-sensitivity preflight only; no winner, selection, "
            "ensemble, profitability claim, paper input, or model promotion"
        ),
        "source_contract_hash": plan.campaign.contract_hash,
        "dataset_hash": plan.cataloged_bars.dataset_hash,
        "timeframe": Timeframe.M1.value,
        "session_geometry": {
            "development_blocks": len(plan.development_session_dates),
            "purge_blocks": 1,
            "comparison_blocks": len(plan.validation_session_dates),
            "session_reset_required": True,
        },
        "matrix": {
            "windows_bars": list(KIS_INTRADAY_WINDOW_MATRIX_WINDOWS),
            "cell_count": len(KIS_INTRADAY_WINDOW_MATRIX_WINDOWS),
            "effective_sample_unit": "session_block",
            "minimum_development_blocks": KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_DEVELOPMENT_BLOCKS,
            "minimum_comparison_blocks": KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_COMPARISON_BLOCKS,
            "minimum_observations_per_block": (
                KIS_INTRADAY_WINDOW_MATRIX_MINIMUM_OBSERVATIONS_PER_BLOCK
            ),
            "development_only_normalization": True,
            "optimizer_steps_per_cell": KIS_INTRADAY_WINDOW_MATRIX_OPTIMIZER_STEPS,
            "learning_rate": KIS_INTRADAY_WINDOW_MATRIX_LEARNING_RATE,
            "comparison_materialized": False,
            "ranked_cell": None,
        },
        "null_test": {
            "label_permutation_unit": "session_block",
            "replicates": KIS_INTRADAY_WINDOW_MATRIX_NULL_REPLICATES,
            "evaluated_before_real_matrix": True,
            "structure_gate": "real_spread_gt_null_p95_and_real_min_brier_lt_null_p05",
        },
        "cost_sensitivity": {
            "multipliers": list(KIS_INTRADAY_WINDOW_MATRIX_COST_MULTIPLIERS),
            "materialized": False,
        },
        "cuda": {
            "eligible_only_if": "structure_present",
            "requested": False,
        },
        "artifact_policy": {
            "raw_market_data_written": False,
            "checkpoint_written": False,
            "repo_storage_allowed": False,
        },
    }


def _summary_payload(
    *,
    plan: KisIntradayCpuCampaignPlan,
    precommit_path: Path,
    precommit_hash: str,
    artifact_root: Path,
    cell_results: Sequence[KisIntradayWindowMatrixCellResult],
    null_spread_p95: float,
    null_minimum_brier_p05: float,
    structure_gate: Literal["structure_present", "no_structure"],
) -> dict[str, object]:
    briers = tuple(item.brier_score for item in cell_results)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "mode": "offline_cpu_window_sensitivity",
        "claim": (
            "aggregate null-first window-sensitivity evidence only; no ranked cell, winner, "
            "selection, ensemble, profitability claim, paper input, or model promotion"
        ),
        "source_contract_hash": plan.campaign.contract_hash,
        "precommit": {
            "path": str(precommit_path),
            "hash": precommit_hash,
            "written_before_real_matrix": True,
        },
        "matrix": {
            "cell_count": len(cell_results),
            "window_bars": list(KIS_INTRADAY_WINDOW_MATRIX_WINDOWS),
            "per_cell_metrics_materialized": False,
            "ranked_cell": None,
            "development_observation_count_distribution": _integer_distribution(
                tuple(item.development_observation_count for item in cell_results)
            ),
            "comparison_observation_count_distribution": _integer_distribution(
                tuple(item.comparison_observation_count for item in cell_results)
            ),
            "metric_distribution": _float_distribution(briers),
        },
        "null_test": {
            "label_permutation_unit": "session_block",
            "replicates": KIS_INTRADAY_WINDOW_MATRIX_NULL_REPLICATES,
            "evaluated_before_real_matrix": True,
            "spread_p95": _format_float(null_spread_p95),
            "minimum_brier_p05": _format_float(null_minimum_brier_p05),
        },
        "gate": {
            "status": structure_gate,
            "cuda_eligible": structure_gate == "structure_present",
            "sealed_evaluation_allowed": False,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
        },
        "cost_sensitivity": {
            "multipliers": list(KIS_INTRADAY_WINDOW_MATRIX_COST_MULTIPLIERS),
            "materialized": False,
        },
        "artifact_policy": {
            "root": str(artifact_root),
            "raw_market_data_written": False,
            "checkpoint_written": False,
            "repo_storage_allowed": False,
        },
    }


def _input_unavailable_summary(
    *,
    plan: KisIntradayCpuCampaignPlan,
    precommit_path: Path,
    precommit_hash: str,
    artifact_root: Path,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "input_unavailable",
        "mode": "offline_cpu_window_sensitivity",
        "claim": (
            "causal input is unavailable; no real matrix, CUDA, selection, or Paper action occurred"
        ),
        "source_contract_hash": plan.campaign.contract_hash,
        "precommit": {
            "path": str(precommit_path),
            "hash": precommit_hash,
            "written_before_real_matrix": True,
        },
        "matrix": {
            "windows_bars": list(KIS_INTRADAY_WINDOW_MATRIX_WINDOWS),
            "comparison_materialized": False,
            "ranked_cell": None,
        },
        "gate": {
            "status": "input_unavailable",
            "cuda_eligible": False,
            "selection_allowed": False,
            "ensemble_allowed": False,
            "paper_input_allowed": False,
        },
        "artifact_policy": {
            "root": str(artifact_root),
            "raw_market_data_written": False,
            "checkpoint_written": False,
            "repo_storage_allowed": False,
        },
    }


def _integer_distribution(values: Sequence[int]) -> dict[str, int]:
    return {"minimum": min(values), "maximum": max(values)}


def _float_distribution(values: Sequence[float]) -> dict[str, str]:
    return {
        "minimum": _format_float(min(values)),
        "maximum": _format_float(max(values)),
        "spread": _format_float(max(values) - min(values)),
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values or not 0 <= quantile <= 1:
        raise ValueError("window matrix percentile input is invalid")
    ordered = tuple(sorted(values))
    index = math.ceil((len(ordered) - 1) * quantile)
    return ordered[index]


def _sigmoid(value: float) -> float:
    bounded = max(min(value, 60.0), -60.0)
    return 1.0 / (1.0 + math.exp(-bounded))


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("window matrix float is non-finite")
    return format(value, ".12g")


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _write_json_new(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _validate_run_label(run_label: str) -> None:
    if not run_label.strip() or any(character in run_label for character in ("/", "\\", ":")):
        raise ValueError("window matrix run label is invalid")


def _reject_repo_path(path: Path, *, repo_root: Path) -> None:
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if repo_root == docker_repo_root and (
            path == docker_artifact_root or docker_artifact_root in path.parents
        ):
            return
    if path == repo_root or repo_root in path.parents:
        raise ValueError("KIS intraday window-matrix artifacts must stay outside the Git workspace")

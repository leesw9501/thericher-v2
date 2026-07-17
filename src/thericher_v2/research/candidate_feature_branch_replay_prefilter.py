"""Research-only prefilter for bounded feature-branch replay candidates."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data import assess_bar_quality
from thericher_v2.serialization import to_jsonable

from .candidate_comparison import _payload_dict, _payload_string
from .candidate_depth_comparison import _read_json_artifact
from .candidate_feature_branch_replay import derive_feature_branch_replay_threshold_pairs
from .candidate_replay import CandidateProbabilityRunner
from .candidate_threshold_sweep import (
    CandidateThresholdSweepConfig,
    run_bounded_candidate_probability_trace,
)
from .candidate_training import GpuReadiness, _reject_repo_artifact_path
from .validation import DEFAULT_MARKET_DATA_ROOT, load_yahoo_intraday_1m_bars

APP_MODEL_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")
APP_MARKET_DATA_ROOT = PurePosixPath("/app/market_data")
DEFAULT_PREFILTER_RUN_ID = "bounded-feature-branch-replay-opportunity-prefilter"
DEFAULT_PREFILTER_EXCLUDED_SYMBOLS = (
    "ADBE",
    "ADI",
    "ADP",
    "AEM",
    "AMAT",
    "AMZN",
    "BA",
    "AAPL",
    "ABBV",
    "ABT",
    "ACN",
)
MAX_PREFILTER_CANDIDATES = 12
MAX_PREFILTER_BARS = 240
MAX_PREFILTER_REPLAY_CANDIDATES = 4
PREFILTER_SUMMARY_SOURCE = "diagnostic_overlay"

FeatureBranchReplayPrefilterStatus = Literal[
    "research_prefilter_only",
    "prepared_not_prefiltered",
]


@dataclass(frozen=True)
class CandidateFeatureBranchReplayPrefilterSliceConfig:
    slice_id: str
    yahoo_snapshot: Path
    symbol: str
    probability_trace_artifact: Path | None = None
    note: str = ""
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.slice_id:
            raise ValueError("slice_id is required")
        if any(part in self.slice_id for part in ("\\", "/", ":")):
            raise ValueError("slice_id must not contain path separators")
        if not self.symbol:
            raise ValueError("symbol is required")
        object.__setattr__(self, "symbol", self.symbol.upper())


@dataclass(frozen=True)
class CandidateFeatureBranchReplayPrefilterConfig:
    run_id: str = DEFAULT_PREFILTER_RUN_ID
    max_candidates: int = MAX_PREFILTER_CANDIDATES
    max_bars: int = MAX_PREFILTER_BARS
    min_examples: int = 8
    threshold_pair_cap: int = 3
    max_replay_candidates: int = MAX_PREFILTER_REPLAY_CANDIDATES
    excluded_symbols: tuple[str, ...] = DEFAULT_PREFILTER_EXCLUDED_SYMBOLS
    candidates: tuple[CandidateFeatureBranchReplayPrefilterSliceConfig, ...] = ()
    allow_trace_compute: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if not 0 < self.max_candidates <= MAX_PREFILTER_CANDIDATES:
            raise ValueError(f"max_candidates must be <= {MAX_PREFILTER_CANDIDATES}")
        if len(self.candidates) > self.max_candidates:
            raise ValueError(f"candidates must be <= {self.max_candidates}")
        if not 0 < self.max_bars <= MAX_PREFILTER_BARS:
            raise ValueError(f"max_bars must be <= {MAX_PREFILTER_BARS}")
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        if self.threshold_pair_cap <= 0:
            raise ValueError("threshold_pair_cap must be positive")
        if not 0 < self.max_replay_candidates <= MAX_PREFILTER_REPLAY_CANDIDATES:
            raise ValueError(
                f"max_replay_candidates must be <= {MAX_PREFILTER_REPLAY_CANDIDATES}"
            )
        object.__setattr__(
            self,
            "excluded_symbols",
            tuple(dict.fromkeys(symbol.upper() for symbol in self.excluded_symbols)),
        )


@dataclass(frozen=True)
class BoundedCandidateFeatureBranchReplayPrefilterResult:
    run_id: str
    status: FeatureBranchReplayPrefilterStatus
    checked_at: datetime
    reason: str
    prefilter_artifact: Path
    source_feature_branch_artifact: Path | None
    threshold_pairs: tuple[tuple[float, float], ...]
    min_derived_buy_threshold: float | None
    candidate_summaries: tuple[dict[str, Any], ...]
    replay_candidate_slices: tuple[dict[str, Any], ...]
    excluded_symbols: tuple[str, ...]
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_feature_branch_replay_opportunity_prefilter(
    *,
    config: CandidateFeatureBranchReplayPrefilterConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    feature_branch_artifact: Path | None = None,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateFeatureBranchReplayPrefilterResult:
    config = config or CandidateFeatureBranchReplayPrefilterConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-feature-branch-replay-prefilter" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    prefilter_artifact = output_dir / "metrics.json"

    resolved_feature_branch_artifact = _resolve_model_path(
        feature_branch_artifact,
        artifact_root,
    )
    if resolved_feature_branch_artifact is not None:
        _reject_repo_artifact_path(resolved_feature_branch_artifact, repo_root)
    feature_branch_payload, feature_branch_error = _read_json_artifact(
        resolved_feature_branch_artifact,
        required_label="candidate feature branch artifact",
    )
    probability_evidence = _payload_dict(
        _payload_dict(feature_branch_payload, "metrics"),
        "probability_evidence",
    )
    threshold_pairs = derive_feature_branch_replay_threshold_pairs(
        probability_evidence,
        cap=config.threshold_pair_cap,
    )
    min_buy_threshold = (
        min(buy_threshold for buy_threshold, _sell_threshold in threshold_pairs)
        if threshold_pairs
        else None
    )
    feature_branch_status_error = _status_error(
        feature_branch_payload,
        expected="candidate_feature_branch_evaluated_only",
        label="candidate feature branch",
    )
    artifacts = _payload_dict(feature_branch_payload, "artifacts")
    training_artifact = _resolve_model_path(artifacts.get("candidate_training"), artifact_root)
    evaluation_artifact = _resolve_model_path(artifacts.get("candidate_evaluation"), artifact_root)
    model_artifact = _resolve_model_path(artifacts.get("model"), artifact_root)

    initial_errors = tuple(
        error
        for error in (
            feature_branch_error,
            feature_branch_status_error,
            None if threshold_pairs else "feature branch replay thresholds are unavailable",
            None if config.candidates else "prefilter candidates are required",
        )
        if error is not None
    )
    candidate_summaries = tuple(
        _candidate_summary(
            candidate=candidate,
            config=config,
            artifact_root=artifact_root,
            market_data_root=market_data_root,
            min_buy_threshold=min_buy_threshold,
            training_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            model_artifact=model_artifact,
            allow_trace_compute=config.allow_trace_compute,
            gpu=gpu,
            probability_runner=probability_runner,
            skip_probability=bool(initial_errors),
        )
        for candidate in config.candidates
    )
    ordered_summaries = _rank_candidate_summaries(candidate_summaries)
    replay_candidate_slices = tuple(
        _replay_slice_payload(summary)
        for summary in ordered_summaries
        if summary.get("candidate_for_one_bounded_local_replay") is True
    )[: config.max_replay_candidates]
    metrics = _prefilter_metrics(
        summaries=ordered_summaries,
        replay_candidate_slices=replay_candidate_slices,
    )
    status: FeatureBranchReplayPrefilterStatus = (
        "research_prefilter_only" if not initial_errors else "prepared_not_prefiltered"
    )
    result = BoundedCandidateFeatureBranchReplayPrefilterResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        reason=(
            "bounded research replay opportunity prefilter completed"
            if status == "research_prefilter_only"
            else "; ".join(initial_errors)
        ),
        prefilter_artifact=prefilter_artifact,
        source_feature_branch_artifact=resolved_feature_branch_artifact,
        threshold_pairs=threshold_pairs,
        min_derived_buy_threshold=min_buy_threshold,
        candidate_summaries=ordered_summaries,
        replay_candidate_slices=replay_candidate_slices,
        excluded_symbols=config.excluded_symbols,
        metrics=metrics,
    )
    prefilter_artifact.write_text(
        json.dumps(
            _prefilter_payload(
                result,
                artifact_root=artifact_root,
                config=config,
                training_artifact=training_artifact,
                evaluation_artifact=evaluation_artifact,
                model_artifact=model_artifact,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _candidate_summary(
    *,
    candidate: CandidateFeatureBranchReplayPrefilterSliceConfig,
    config: CandidateFeatureBranchReplayPrefilterConfig,
    artifact_root: Path,
    market_data_root: Path,
    min_buy_threshold: float | None,
    training_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    allow_trace_compute: bool,
    gpu: GpuReadiness | None,
    probability_runner: CandidateProbabilityRunner | None,
    skip_probability: bool,
) -> dict[str, Any]:
    resolved_snapshot = _resolve_market_path(candidate.yahoo_snapshot, market_data_root)
    data_summary = _data_summary(
        snapshot=resolved_snapshot,
        symbol=candidate.symbol,
        max_bars=config.max_bars,
    )
    if candidate.symbol in config.excluded_symbols:
        return {
            **_base_candidate_summary(candidate, resolved_snapshot),
            "status": "excluded_by_prefilter_scope",
            "reason": "symbol is excluded by current branch/no-fill replay scope",
            "data": data_summary,
            "source": PREFILTER_SUMMARY_SOURCE,
            "candidate_for_one_bounded_local_replay": False,
        }
    if skip_probability:
        return {
            **_base_candidate_summary(candidate, resolved_snapshot),
            "status": "prepared_not_scored",
            "reason": "source feature-branch artifact did not provide usable thresholds",
            "data": data_summary,
            "source": PREFILTER_SUMMARY_SOURCE,
            "candidate_for_one_bounded_local_replay": False,
        }
    trace_payload, trace_path, trace_error, trace_was_computed = _load_or_run_trace(
        candidate=candidate,
        config=config,
        artifact_root=artifact_root,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        resolved_snapshot=resolved_snapshot,
        allow_trace_compute=allow_trace_compute,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    trace_summary = _trace_summary(
        payload=trace_payload,
        trace_path=trace_path,
        expected_symbol=candidate.symbol,
        expected_snapshot=resolved_snapshot,
        expected_model_artifact=model_artifact,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        min_buy_threshold=min_buy_threshold,
    )
    errors = tuple(
        error
        for error in (
            data_summary.get("error"),
            trace_error,
            trace_summary.get("error"),
        )
        if error
    )
    candidate_for_replay = (
        not errors
        and trace_summary.get("source_model_matches_feature_branch") is True
        and trace_summary.get("data_source_matches_candidate") is True
        and trace_summary.get("examples_seen", 0) >= config.min_examples
        and trace_summary.get("probability_max") is not None
        and min_buy_threshold is not None
        and float(trace_summary["probability_max"]) >= min_buy_threshold
    )
    return {
        **_base_candidate_summary(candidate, resolved_snapshot),
        "status": "scored" if not errors else "prepared_not_scored",
        "reason": "trace probability summary scored" if not errors else "; ".join(errors),
        "data": data_summary,
        "trace": trace_summary,
        "trace_was_computed": trace_was_computed,
        "source": PREFILTER_SUMMARY_SOURCE,
        "candidate_for_one_bounded_local_replay": candidate_for_replay,
    }


def _base_candidate_summary(
    candidate: CandidateFeatureBranchReplayPrefilterSliceConfig,
    resolved_snapshot: Path,
) -> dict[str, Any]:
    return {
        "slice_id": candidate.slice_id,
        "symbol": candidate.symbol,
        "yahoo_snapshot": str(resolved_snapshot),
        "probability_trace_artifact": (
            None
            if candidate.probability_trace_artifact is None
            else str(candidate.probability_trace_artifact)
        ),
        "note": candidate.note,
    }


def _data_summary(*, snapshot: Path, symbol: str, max_bars: int) -> dict[str, Any]:
    try:
        bars = load_yahoo_intraday_1m_bars(snapshot, symbol=symbol, max_bars=max_bars)
    except Exception as exc:  # noqa: BLE001 - prefilter records unavailable data.
        return {
            "status": "unavailable",
            "error": f"candidate bars unavailable: {exc}",
            "bars_seen": 0,
            "max_bars": max_bars,
            "warning_count": 0,
            "warning_codes": {},
            "blocks_research": False,
        }
    report = assess_bar_quality(tuple(bars))
    warning_codes = Counter(warning.code for warning in report.warnings)
    return {
        "status": "loaded",
        "bars_seen": len(bars),
        "first_bar_start": bars[0].start_ts.isoformat(),
        "last_bar_start": bars[-1].start_ts.isoformat(),
        "max_bars": max_bars,
        "warning_count": report.warning_count,
        "warning_codes": dict(sorted(warning_codes.items())),
        "blocks_research": report.blocks_research,
    }


def _load_or_run_trace(
    *,
    candidate: CandidateFeatureBranchReplayPrefilterSliceConfig,
    config: CandidateFeatureBranchReplayPrefilterConfig,
    artifact_root: Path,
    training_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
    resolved_snapshot: Path,
    allow_trace_compute: bool,
    gpu: GpuReadiness | None,
    probability_runner: CandidateProbabilityRunner | None,
) -> tuple[dict[str, Any], Path | None, str | None, bool]:
    if candidate.probability_trace_artifact is not None:
        trace_path = _resolve_model_path(candidate.probability_trace_artifact, artifact_root)
        payload, error = _read_json_artifact(
            trace_path,
            required_label="candidate probability trace artifact",
        )
        return payload, trace_path, error, False
    if not allow_trace_compute:
        return (
            {},
            None,
            "probability trace artifact is not provided and trace compute is disabled",
            False,
        )
    trace = run_bounded_candidate_probability_trace(
        config=CandidateThresholdSweepConfig(
            run_id=f"{config.run_id}-{candidate.slice_id}-trace",
            max_bars=config.max_bars,
            min_examples=config.min_examples,
        ),
        artifact_root=artifact_root,
        repo_root=None,
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        yahoo_snapshot=resolved_snapshot,
        symbol=candidate.symbol,
        gpu=gpu,
        probability_runner=probability_runner,
    )
    payload = json.loads(trace.trace_artifact.read_text(encoding="utf-8"))
    error = None if trace.status == "probability_traced_only" else trace.reason
    return payload, trace.trace_artifact, error, True


def _trace_summary(
    *,
    payload: dict[str, Any],
    trace_path: Path | None,
    expected_symbol: str,
    expected_snapshot: Path,
    expected_model_artifact: Path | None,
    artifact_root: Path,
    market_data_root: Path,
    min_buy_threshold: float | None,
) -> dict[str, Any]:
    if not payload:
        return {
            "status": "unavailable",
            "artifact": None if trace_path is None else str(trace_path),
            "error": "probability trace payload is unavailable",
        }
    if payload.get("status") != "probability_traced_only":
        return {
            "status": str(payload.get("status") or "unavailable"),
            "artifact": None if trace_path is None else str(trace_path),
            "error": _payload_string(payload, "reason") or "probability trace did not complete",
        }
    trace_symbol = _payload_string(payload, "symbol")
    if trace_symbol is None or trace_symbol.upper() != expected_symbol:
        return {
            "status": "symbol_mismatch",
            "artifact": None if trace_path is None else str(trace_path),
            "error": f"trace symbol {trace_symbol!r} does not match {expected_symbol!r}",
        }
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {
            "status": "unavailable",
            "artifact": None if trace_path is None else str(trace_path),
            "error": "probability trace entries are unavailable",
        }
    probabilities = tuple(
        float(item["probability"])
        for item in entries
        if isinstance(item, dict) and item.get("probability") is not None
    )
    if not probabilities:
        return {
            "status": "unavailable",
            "artifact": None if trace_path is None else str(trace_path),
            "error": "probability trace has no probability entries",
        }
    trace_data_source = _resolve_market_path(payload.get("data_source"), market_data_root)
    trace_model_artifact = _trace_model_artifact(payload, artifact_root)
    data_source_matches = _same_path(trace_data_source, expected_snapshot)
    source_model_matches = _same_path(trace_model_artifact, expected_model_artifact)
    probability_max = max(probabilities)
    threshold_gap = (
        None if min_buy_threshold is None else probability_max - min_buy_threshold
    )
    top_entries = sorted(
        (item for item in entries if isinstance(item, dict)),
        key=lambda item: float(item.get("probability") or 0.0),
        reverse=True,
    )[:3]
    threshold_crossing_count = (
        0
        if min_buy_threshold is None
        else sum(1 for probability in probabilities if probability >= min_buy_threshold)
    )
    error = None
    if not data_source_matches:
        error = "trace data source does not match candidate snapshot"
    elif not source_model_matches:
        error = "trace source model does not match feature-branch model"
    return {
        "status": "scored" if error is None else "alignment_mismatch",
        "artifact": None if trace_path is None else str(trace_path),
        "error": error,
        "run_id": _payload_string(payload, "run_id"),
        "data_source": str(trace_data_source) if trace_data_source is not None else None,
        "data_source_matches_candidate": data_source_matches,
        "source_model_artifact": (
            None if trace_model_artifact is None else str(trace_model_artifact)
        ),
        "source_model_matches_feature_branch": source_model_matches,
        "examples_seen": _int_metric(payload.get("examples_seen")) or len(probabilities),
        "probability_count": len(probabilities),
        "probability_min": f"{min(probabilities):.6f}",
        "probability_mean": f"{sum(probabilities) / len(probabilities):.6f}",
        "probability_max": f"{probability_max:.6f}",
        "derived_buy_threshold": (
            None if min_buy_threshold is None else f"{min_buy_threshold:.6f}"
        ),
        "threshold_gap": None if threshold_gap is None else f"{threshold_gap:.6f}",
        "threshold_crossing_count": threshold_crossing_count,
        "top_probability_contexts": tuple(
            {
                "probability": f"{float(item['probability']):.6f}",
                "signal_bar_end": item.get("signal_bar_end"),
                "execution_bar_start": item.get("execution_bar_start"),
                "execution_bar_end": item.get("execution_bar_end"),
                "contiguous": item.get("contiguous"),
            }
            for item in top_entries
        ),
    }


def _rank_candidate_summaries(
    summaries: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    def rank_key(item: dict[str, Any]) -> tuple[int, float, str]:
        trace = item.get("trace") if isinstance(item.get("trace"), dict) else {}
        gap = _float_metric(trace.get("threshold_gap")) if isinstance(trace, dict) else None
        scored = 1 if gap is not None and trace.get("status") == "scored" else 0
        return (scored, gap if gap is not None else float("-inf"), str(item.get("symbol")))

    return tuple(sorted(summaries, key=rank_key, reverse=True))


def _replay_slice_payload(summary: dict[str, Any]) -> dict[str, Any]:
    trace = summary.get("trace") if isinstance(summary.get("trace"), dict) else {}
    return {
        "slice_id": summary.get("slice_id"),
        "symbol": summary.get("symbol"),
        "yahoo_snapshot": summary.get("yahoo_snapshot"),
        "probability_trace_artifact": (
            None if not isinstance(trace, dict) else trace.get("artifact")
        ),
        "source": PREFILTER_SUMMARY_SOURCE,
        "candidate_for_one_bounded_local_replay": True,
    }


def _prefilter_metrics(
    *,
    summaries: tuple[dict[str, Any], ...],
    replay_candidate_slices: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    scored = tuple(
        item
        for item in summaries
        if isinstance(item.get("trace"), dict) and item["trace"].get("status") == "scored"
    )
    gaps = tuple(
        gap
        for gap in (
            _float_metric(item["trace"].get("threshold_gap"))
            for item in scored
            if isinstance(item.get("trace"), dict)
        )
        if gap is not None
    )
    return {
        "research_prefilter_only": True,
        "candidate_count": len(summaries),
        "scored_candidate_count": len(scored),
        "excluded_candidate_count": sum(
            1 for item in summaries if item.get("status") == "excluded_by_prefilter_scope"
        ),
        "trace_missing_or_unavailable_count": sum(
            1
            for item in summaries
            if item.get("status") == "prepared_not_scored"
            and "probability trace" in str(item.get("reason", ""))
        ),
        "threshold_crossing_candidate_count": sum(
            1
            for item in summaries
            if item.get("candidate_for_one_bounded_local_replay") is True
        ),
        "candidate_for_one_bounded_local_replay_count": len(replay_candidate_slices),
        "threshold_gap_min": None if not gaps else f"{min(gaps):.6f}",
        "threshold_gap_max": None if not gaps else f"{max(gaps):.6f}",
        "replay_was_run": False,
        "order_intents_created": 0,
        "fills_created": 0,
        "no_execution_authority": True,
        "no_promotion_semantics": True,
    }


def _prefilter_payload(
    result: BoundedCandidateFeatureBranchReplayPrefilterResult,
    *,
    artifact_root: Path,
    config: CandidateFeatureBranchReplayPrefilterConfig,
    training_artifact: Path | None,
    evaluation_artifact: Path | None,
    model_artifact: Path | None,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "reason": result.reason,
            "source_feature_branch_artifact": (
                None
                if result.source_feature_branch_artifact is None
                else str(result.source_feature_branch_artifact)
            ),
            "source_training_artifact": (
                None if training_artifact is None else str(training_artifact)
            ),
            "source_evaluation_artifact": (
                None if evaluation_artifact is None else str(evaluation_artifact)
            ),
            "source_model_artifact": None if model_artifact is None else str(model_artifact),
            "prefilter_scope": {
                "mode": "research_prefilter_only",
                "summary_source": PREFILTER_SUMMARY_SOURCE,
                "descriptive_only": True,
                "no_execution_authority": True,
                "no_promotion_semantics": True,
                "max_candidates": config.max_candidates,
                "max_bars_per_symbol": config.max_bars,
                "max_replay_candidates": config.max_replay_candidates,
                "allow_trace_compute": config.allow_trace_compute,
                "default_trace_behavior": "consume_existing_trace_artifacts_only",
            },
            "threshold_derivation": {
                "mode": "feature_branch_probability_range_probe",
                "threshold_pair_cap": config.threshold_pair_cap,
                "threshold_pair_count": len(result.threshold_pairs),
                "threshold_pairs": tuple(
                    {
                        "buy_threshold": f"{buy_threshold:.6f}",
                        "sell_threshold": f"{sell_threshold:.6f}",
                    }
                    for buy_threshold, sell_threshold in result.threshold_pairs
                ),
                "min_derived_buy_threshold": (
                    None
                    if result.min_derived_buy_threshold is None
                    else f"{result.min_derived_buy_threshold:.6f}"
                ),
                "descriptive_only": True,
                "no_execution_authority": True,
                "no_promotion_semantics": True,
            },
            "excluded_symbols": result.excluded_symbols,
            "candidate_summaries": result.candidate_summaries,
            "replay_candidate_slices": result.replay_candidate_slices,
            "metrics": result.metrics,
            "boundaries": {
                "kis_api": False,
                "broker_submit": False,
                "credential_read": False,
                "env_file_read": False,
                "network_required": False,
                "market_data_acquired": False,
                "replay_run": False,
                "order_intents_created": False,
                "fills_created": False,
                "new_worker": False,
                "new_scheduler": False,
            },
            "artifacts": {
                "candidate_feature_branch_replay_prefilter": str(
                    result.prefilter_artifact
                ),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    if not payload:
        return None
    actual = payload.get("status")
    if actual == expected:
        return None
    return f"{label} status is {actual!r}, expected {expected!r}"


def _resolve_model_path(value: Any, artifact_root: Path) -> Path | None:
    if value is None or value == "":
        return None
    raw = str(value).replace("\\", "/")
    if raw == str(APP_MODEL_ARTIFACT_ROOT):
        return artifact_root
    if raw.startswith(f"{APP_MODEL_ARTIFACT_ROOT}/"):
        relative = PurePosixPath(raw).relative_to(APP_MODEL_ARTIFACT_ROOT)
        return artifact_root.joinpath(*relative.parts)
    return Path(str(value))


def _resolve_market_path(value: Any, market_data_root: Path) -> Path | None:
    if value is None or value == "":
        return None
    raw = str(value).replace("\\", "/")
    if raw == str(APP_MARKET_DATA_ROOT):
        return market_data_root
    if raw.startswith(f"{APP_MARKET_DATA_ROOT}/"):
        relative = PurePosixPath(raw).relative_to(APP_MARKET_DATA_ROOT)
        return market_data_root.joinpath(*relative.parts)
    return Path(str(value))


def _trace_model_artifact(payload: dict[str, Any], artifact_root: Path) -> Path | None:
    artifacts = _payload_dict(payload, "artifacts")
    return _resolve_model_path(
        artifacts.get("source_model") or payload.get("model_artifact"),
        artifact_root,
    )


def _same_path(left: Path | None, right: Path | None) -> bool:
    if left is None or right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left).replace("\\", "/").lower() == str(right).replace("\\", "/").lower()


def _int_metric(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_metric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

"""Comparison-informed threshold rerun for a selected depth target."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_replay import CandidateProbabilityRunner
from .candidate_threshold_holdout import (
    BoundedCandidateThresholdHoldoutResult,
    CandidateThresholdHoldoutConfig,
    run_bounded_candidate_threshold_holdout,
)
from .candidate_threshold_robustness import CandidateThresholdRobustnessSliceConfig
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
)

CandidateThresholdRerunStatus = Literal[
    "candidate_threshold_rerun_replayed_only",
    "prepared_not_threshold_reran",
]
DEFAULT_CANDIDATE_THRESHOLD_RERUN_RUN_ID = "bounded-candidate-threshold-rerun"
APP_MODEL_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")
APP_MARKET_DATA_ROOT = PurePosixPath("/app/market_data")
DEFAULT_HOST_MARKET_DATA_ROOT = Path("D:/market_data")
MAX_CANDIDATE_THRESHOLD_RERUN_PAIRS = 4
THRESHOLD_STEP = Decimal("0.001")


@dataclass(frozen=True)
class CandidateThresholdRerunConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_RERUN_RUN_ID
    max_bars: int = 120
    min_examples: int = 8
    threshold_pair_cap: int = MAX_CANDIDATE_THRESHOLD_RERUN_PAIRS
    sample_seed: int = 37
    starting_cash: Decimal = Decimal("10000")
    quantity: Decimal = Decimal("1")
    fee_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("0")
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if self.max_bars <= 0:
            raise ValueError("max_bars must be positive")
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        if not 0 < self.threshold_pair_cap <= MAX_CANDIDATE_THRESHOLD_RERUN_PAIRS:
            raise ValueError(
                "threshold_pair_cap must be between 1 and "
                f"{MAX_CANDIDATE_THRESHOLD_RERUN_PAIRS}"
            )
        if self.starting_cash <= 0:
            raise ValueError("starting_cash must be positive")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.fee_bps < 0:
            raise ValueError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")


@dataclass(frozen=True)
class BoundedCandidateThresholdRerunResult:
    run_id: str
    status: CandidateThresholdRerunStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_comparison_artifact: Path | None
    source_depth_target_artifact: Path | None
    source_calibration_artifact: Path | None
    training_metrics_artifact: Path | None
    evaluation_artifact: Path | None
    model_artifact: Path | None
    rerun_artifact: Path
    holdout_artifact: Path | None
    robustness_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    selected_variant_id: str | None
    threshold_pairs: tuple[tuple[float, float], ...]
    threshold_schedule: dict[str, Any]
    source_thresholds: dict[str, Any]
    artifact_verification: dict[str, Any]
    slice_count: int
    completed_slice_count: int
    holdout_slices: tuple[dict[str, Any], ...]
    probability_summary: dict[str, Any]
    local_paper_verification: dict[str, Any]
    comparison_metrics: dict[str, Any]
    holdout: BoundedCandidateThresholdHoldoutResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_rerun(
    *,
    config: CandidateThresholdRerunConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    comparison_artifact: Path | None = None,
    depth_target_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    probability_runner: CandidateProbabilityRunner | None = None,
) -> BoundedCandidateThresholdRerunResult:
    config = config or CandidateThresholdRerunConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-rerun" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    rerun_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    resolved_comparison_artifact = _resolve_optional_path(
        comparison_artifact,
        artifact_root,
    )
    if resolved_comparison_artifact is not None:
        _reject_repo_artifact_path(resolved_comparison_artifact, repo_root)
    comparison_payload, comparison_error = _read_json_artifact(
        resolved_comparison_artifact,
        required_label="candidate depth comparison artifact",
    )
    resolved_depth_target_artifact = _resolve_optional_path(
        depth_target_artifact or comparison_payload.get("source_depth_target_artifact"),
        artifact_root,
    )
    if resolved_depth_target_artifact is not None:
        _reject_repo_artifact_path(resolved_depth_target_artifact, repo_root)
    depth_payload, depth_error = _read_json_artifact(
        resolved_depth_target_artifact,
        required_label="candidate depth target artifact",
    )
    selected_variant_id = _payload_string(comparison_payload, "selected_variant_id")
    depth_selected_variant_id = _nested_string(
        depth_payload,
        "selection",
        "selected_variant_id",
    )
    artifacts = _source_artifacts(depth_payload, artifact_root)
    artifact_verification = _artifact_verification(
        comparison_artifact=resolved_comparison_artifact,
        depth_target_artifact=resolved_depth_target_artifact,
        source_artifacts=artifacts,
    )
    calibration_payload, calibration_error = _read_json_artifact(
        artifacts.get("calibration"),
        required_label="candidate threshold calibration artifact",
    )
    holdout_payload, holdout_error = _read_json_artifact(
        artifacts.get("holdout"),
        required_label="candidate threshold holdout artifact",
    )
    source_threshold_pairs = _threshold_pairs_from_calibration_payload(
        calibration_payload
    )
    comparison_metrics = _payload_dict(comparison_payload, "metrics")
    threshold_pairs = derive_fill_aware_threshold_pairs(
        source_threshold_pairs,
        comparison_metrics=comparison_metrics,
        cap=config.threshold_pair_cap,
    )
    holdout_slices = _holdout_slices_from_payload(holdout_payload, artifact_root)
    initial_errors = tuple(
        error
        for error in (
            comparison_error,
            _status_error(
                comparison_payload,
                expected="candidate_depth_compared_only",
                label="candidate depth comparison",
            ),
            depth_error,
            _status_error(
                depth_payload,
                expected="candidate_depth_target_ran_only",
                label="candidate depth target",
            ),
            None
            if selected_variant_id
            else "comparison selected variant is missing",
            None
            if selected_variant_id == depth_selected_variant_id
            else (
                "depth target selected variant does not match comparison: "
                f"{depth_selected_variant_id} != {selected_variant_id}"
            ),
            _artifact_error(artifact_verification),
            calibration_error,
            holdout_error,
            None
            if source_threshold_pairs
            else "source calibration contains no threshold pairs",
            None
            if threshold_pairs
            else "no comparison-informed threshold pairs derived",
            None if holdout_slices else "no holdout slices available for rerun",
        )
        if error is not None
    )
    holdout: BoundedCandidateThresholdHoldoutResult | None = None
    if not initial_errors:
        holdout = run_bounded_candidate_threshold_holdout(
            config=CandidateThresholdHoldoutConfig(
                run_id=f"{config.run_id}-holdout",
                max_bars=config.max_bars,
                min_examples=config.min_examples,
                threshold_pairs=threshold_pairs,
                slices=holdout_slices,
                sample_seed=config.sample_seed,
                starting_cash=config.starting_cash,
                quantity=config.quantity,
                fee_bps=config.fee_bps,
                slippage_bps=config.slippage_bps,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            calibration_artifact=artifacts.get("calibration"),
            training_metrics_artifact=artifacts.get("training_metrics"),
            evaluation_artifact=artifacts.get("evaluation"),
            model_artifact=artifacts.get("model"),
            gpu=gpu,
            probability_runner=probability_runner,
        )

    status: CandidateThresholdRerunStatus = (
        "candidate_threshold_rerun_replayed_only"
        if holdout is not None
        and holdout.status == "candidate_threshold_holdout_replayed_only"
        else "prepared_not_threshold_reran"
    )
    holdout_reason = None if holdout is None else holdout.reason
    result = BoundedCandidateThresholdRerunResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=(
            "bounded comparison-informed threshold rerun completed"
            if status == "candidate_threshold_rerun_replayed_only"
            else "; ".join(
                initial_errors
                or (holdout_reason or "threshold rerun did not complete",)
            )
        ),
        source_comparison_artifact=resolved_comparison_artifact,
        source_depth_target_artifact=resolved_depth_target_artifact,
        source_calibration_artifact=artifacts.get("calibration"),
        training_metrics_artifact=artifacts.get("training_metrics"),
        evaluation_artifact=artifacts.get("evaluation"),
        model_artifact=artifacts.get("model"),
        rerun_artifact=rerun_artifact,
        holdout_artifact=None if holdout is None else holdout.holdout_artifact,
        robustness_artifact=None if holdout is None else holdout.robustness_artifact,
        candidate_experiment_id=_payload_string(
            depth_payload,
            "candidate_experiment_id",
        ),
        candidate_parameters=_payload_dict(depth_payload, "candidate_parameters"),
        selected_variant_id=selected_variant_id,
        threshold_pairs=threshold_pairs,
        threshold_schedule=_threshold_schedule_payload(
            source_threshold_pairs=source_threshold_pairs,
            threshold_pairs=threshold_pairs,
            comparison_metrics=comparison_metrics,
            cap=config.threshold_pair_cap,
        ),
        source_thresholds=_source_thresholds_payload(source_threshold_pairs),
        artifact_verification=artifact_verification,
        slice_count=len(holdout_slices),
        completed_slice_count=0 if holdout is None else holdout.completed_slice_count,
        holdout_slices=() if holdout is None else holdout.holdout_slices,
        probability_summary={} if holdout is None else holdout.probability_summary,
        local_paper_verification={}
        if holdout is None
        else holdout.local_paper_verification,
        comparison_metrics=comparison_metrics,
        holdout=holdout,
        metrics=_rerun_metrics(
            status=status,
            artifact_verification=artifact_verification,
            threshold_pairs=threshold_pairs,
            holdout=holdout,
        ),
    )
    rerun_artifact.write_text(
        json.dumps(
            _candidate_threshold_rerun_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def derive_fill_aware_threshold_pairs(
    source_threshold_pairs: tuple[tuple[float, float], ...],
    *,
    comparison_metrics: dict[str, Any],
    cap: int = MAX_CANDIDATE_THRESHOLD_RERUN_PAIRS,
) -> tuple[tuple[float, float], ...]:
    valid_pairs = tuple(
        sorted(
            {
                (_rounded_threshold(buy), _rounded_threshold(sell))
                for buy, sell in source_threshold_pairs
                if 0 < sell < buy < 1
            }
        )
    )
    if not valid_pairs or cap <= 0:
        return ()
    sell_floor = min(sell for _buy, sell in valid_pairs)
    buys = tuple(sorted({buy for buy, _sell in valid_pairs}))
    high_buys = buys[max(0, len(buys) // 2) :] or buys[-1:]
    steps = _strictness_steps(comparison_metrics)
    pairs: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for buy_threshold in high_buys:
        pair = (_rounded_threshold(buy_threshold + steps * float(THRESHOLD_STEP)), sell_floor)
        if _add_threshold_pair(pair, seen, pairs, cap):
            continue
    next_buy = (
        pairs[-1][0]
        if pairs
        else _rounded_threshold(buys[-1] + steps * float(THRESHOLD_STEP))
    )
    while len(pairs) < cap:
        next_buy = _rounded_threshold(next_buy + float(THRESHOLD_STEP))
        if not _add_threshold_pair((next_buy, sell_floor), seen, pairs, cap):
            break
    return tuple(pairs)


def _candidate_threshold_rerun_payload(
    result: BoundedCandidateThresholdRerunResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "gpu": result.gpu,
            "reason": result.reason,
            "source_comparison_artifact": None
            if result.source_comparison_artifact is None
            else str(result.source_comparison_artifact),
            "source_depth_target_artifact": None
            if result.source_depth_target_artifact is None
            else str(result.source_depth_target_artifact),
            "source_calibration_artifact": None
            if result.source_calibration_artifact is None
            else str(result.source_calibration_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "selected_variant_id": result.selected_variant_id,
            "training_metrics_artifact": None
            if result.training_metrics_artifact is None
            else str(result.training_metrics_artifact),
            "evaluation_artifact": None
            if result.evaluation_artifact is None
            else str(result.evaluation_artifact),
            "model_artifact": None
            if result.model_artifact is None
            else str(result.model_artifact),
            "source_thresholds": result.source_thresholds,
            "threshold_schedule": result.threshold_schedule,
            "threshold_pairs": [
                {
                    "buy_threshold": f"{buy_threshold:.6f}",
                    "sell_threshold": f"{sell_threshold:.6f}",
                }
                for buy_threshold, sell_threshold in result.threshold_pairs
            ],
            "artifact_verification": result.artifact_verification,
            "slice_count": result.slice_count,
            "completed_slice_count": result.completed_slice_count,
            "holdout_slices": result.holdout_slices,
            "probability_summary": result.probability_summary,
            "comparison_metrics": result.comparison_metrics,
            "metrics": result.metrics,
            "local_paper_verification": result.local_paper_verification,
            "selection": {
                "mode": "research_threshold_rerun_only",
                "selected_variant_id": result.selected_variant_id,
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_threshold_rerun": str(result.rerun_artifact),
                "candidate_threshold_holdout": None
                if result.holdout_artifact is None
                else str(result.holdout_artifact),
                "candidate_threshold_robustness": None
                if result.robustness_artifact is None
                else str(result.robustness_artifact),
            },
            "artifact_policy": {
                "root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _threshold_schedule_payload(
    *,
    source_threshold_pairs: tuple[tuple[float, float], ...],
    threshold_pairs: tuple[tuple[float, float], ...],
    comparison_metrics: dict[str, Any],
    cap: int,
) -> dict[str, Any]:
    return {
        "mode": "research_threshold_rerun_only",
        "derivation": "comparison_informed_fill_aware_stricter_grid",
        "strictness_steps": _strictness_steps(comparison_metrics),
        "threshold_pair_cap": cap,
        "source_threshold_pair_count": len(source_threshold_pairs),
        "threshold_pair_count": len(threshold_pairs),
        "comparison_fill_count_delta": comparison_metrics.get(
            "local_paper_fill_count_delta"
        ),
        "comparison_pnl_floor_delta": comparison_metrics.get("pnl_min_delta"),
        "comparison_max_drawdown_delta": comparison_metrics.get("max_drawdown_delta"),
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy_threshold:.6f}",
                "sell_threshold": f"{sell_threshold:.6f}",
            }
            for buy_threshold, sell_threshold in threshold_pairs
        ],
        "winner": None,
        "recommendation": None,
        "promotion_gate": False,
    }


def _source_thresholds_payload(
    source_threshold_pairs: tuple[tuple[float, float], ...],
) -> dict[str, Any]:
    return {
        "derivation": "source_calibration_artifact",
        "threshold_pair_count": len(source_threshold_pairs),
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy_threshold:.6f}",
                "sell_threshold": f"{sell_threshold:.6f}",
            }
            for buy_threshold, sell_threshold in source_threshold_pairs
        ],
        "promotion_gate": False,
    }


def _rerun_metrics(
    *,
    status: CandidateThresholdRerunStatus,
    artifact_verification: dict[str, Any],
    threshold_pairs: tuple[tuple[float, float], ...],
    holdout: BoundedCandidateThresholdHoldoutResult | None,
) -> dict[str, Any]:
    local_paper_verification = (
        {} if holdout is None else holdout.local_paper_verification
    )
    return {
        "status": status,
        "research_threshold_rerun_only": True,
        "comparison_is_descriptive": True,
        "promotion_gate": False,
        "all_referenced_artifacts_exist": _all_artifacts_exist(artifact_verification),
        "threshold_pair_count": len(threshold_pairs),
        "completed_slice_count": 0 if holdout is None else holdout.completed_slice_count,
        "completed_variant_count": 0
        if holdout is None
        else holdout.metrics.get("completed_variant_count", 0),
        "replay_fill_count_total": 0
        if holdout is None
        else holdout.metrics.get("replay_fill_count_total", 0),
        "robustness_metrics": {}
        if holdout is None
        else holdout.metrics.get("robustness_metrics", {}),
        "local_paper_verification": local_paper_verification,
        "all_fills_local_paper": local_paper_verification.get(
            "all_fills_local_paper"
        )
        is True,
    }


def _source_artifacts(payload: dict[str, Any], artifact_root: Path) -> dict[str, Path | None]:
    artifacts = _payload_dict(payload, "artifacts")
    return {
        "training_metrics": _resolve_optional_path(
            artifacts.get("training_metrics"),
            artifact_root,
        ),
        "evaluation": _resolve_optional_path(artifacts.get("evaluation"), artifact_root),
        "model": _resolve_optional_path(artifacts.get("model"), artifact_root),
        "calibration": _resolve_optional_path(
            artifacts.get("calibration"),
            artifact_root,
        ),
        "holdout": _resolve_optional_path(artifacts.get("holdout"), artifact_root),
    }


def _artifact_verification(
    *,
    comparison_artifact: Path | None,
    depth_target_artifact: Path | None,
    source_artifacts: dict[str, Path | None],
) -> dict[str, Any]:
    paths = {
        "comparison": comparison_artifact,
        "depth_target": depth_target_artifact,
        **source_artifacts,
    }
    return {
        key: {
            "artifact": None if value is None else str(value),
            "exists": False if value is None else value.exists(),
        }
        for key, value in paths.items()
    }


def _artifact_error(artifact_verification: dict[str, Any]) -> str | None:
    missing = tuple(
        key
        for key, value in artifact_verification.items()
        if not _verification_exists(value)
    )
    if not missing:
        return None
    return "referenced threshold rerun artifacts are missing: " + ", ".join(missing)


def _holdout_slices_from_payload(
    payload: dict[str, Any],
    artifact_root: Path,
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    raw_slices = payload.get("holdout_slices")
    if not isinstance(raw_slices, list | tuple):
        return ()
    slices: list[CandidateThresholdRobustnessSliceConfig] = []
    for item in raw_slices:
        if not isinstance(item, dict):
            continue
        slice_id = _payload_string(item, "slice_id")
        yahoo_snapshot = _resolve_optional_path(
            item.get("yahoo_snapshot"),
            artifact_root,
        )
        symbol = _payload_string(item, "symbol")
        if slice_id is None or yahoo_snapshot is None or symbol is None:
            continue
        probability_trace_artifact = _resolve_optional_path(
            item.get("probability_trace_artifact"),
            artifact_root,
        )
        slices.append(
            CandidateThresholdRobustnessSliceConfig(
                slice_id=slice_id,
                yahoo_snapshot=yahoo_snapshot,
                symbol=symbol,
                probability_trace_artifact=probability_trace_artifact,
            )
        )
    return tuple(slices)


def _threshold_pairs_from_calibration_payload(
    payload: dict[str, Any],
) -> tuple[tuple[float, float], ...]:
    thresholds = _payload_dict(payload, "thresholds")
    pairs = thresholds.get("threshold_pairs")
    if not isinstance(pairs, list):
        return ()
    parsed: list[tuple[float, float]] = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        try:
            buy_threshold = float(pair["buy_threshold"])
            sell_threshold = float(pair["sell_threshold"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < sell_threshold < buy_threshold < 1:
            parsed.append((_rounded_threshold(buy_threshold), _rounded_threshold(sell_threshold)))
    return tuple(parsed)


def _read_json_artifact(
    path: Path | None,
    *,
    required_label: str,
) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, f"{required_label} is required"
    if not path.exists():
        return {}, f"{required_label} is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{required_label} is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{required_label} must contain a JSON object"
    return payload, None


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    if not payload:
        return None
    if payload.get("status") == expected:
        return None
    reason = _payload_string(payload, "reason") or f"{label} was not completed"
    return reason


def _resolve_optional_path(value: Any, artifact_root: Path) -> Path | None:
    if value is None or value == "":
        return None
    raw = str(value)
    if raw.startswith(str(APP_MODEL_ARTIFACT_ROOT)):
        relative = PurePosixPath(raw).relative_to(APP_MODEL_ARTIFACT_ROOT)
        return artifact_root.joinpath(*relative.parts)
    if raw.startswith(str(APP_MARKET_DATA_ROOT)):
        root = _host_market_data_root()
        if root is not None:
            relative = PurePosixPath(raw).relative_to(APP_MARKET_DATA_ROOT)
            return root.joinpath(*relative.parts)
    return Path(raw)


def _host_market_data_root() -> Path | None:
    configured = os.environ.get("THERICHER_HOST_MARKET_DATA_ROOT")
    if configured:
        path = Path(configured)
        if path.exists():
            return path
    if DEFAULT_HOST_MARKET_DATA_ROOT.exists():
        return DEFAULT_HOST_MARKET_DATA_ROOT
    return None


def _strictness_steps(comparison_metrics: dict[str, Any]) -> int:
    steps = 1
    fill_delta = _int_metric(comparison_metrics.get("local_paper_fill_count_delta"))
    pnl_floor_delta = _decimal_metric(comparison_metrics.get("pnl_min_delta"))
    drawdown_delta = _decimal_metric(comparison_metrics.get("max_drawdown_delta"))
    if fill_delta is not None and fill_delta > 0:
        steps += 1
    if (pnl_floor_delta is not None and pnl_floor_delta < 0) or (
        drawdown_delta is not None and drawdown_delta > 0
    ):
        steps += 1
    return min(steps, 3)


def _add_threshold_pair(
    pair: tuple[float, float],
    seen: set[tuple[float, float]],
    pairs: list[tuple[float, float]],
    cap: int,
) -> bool:
    buy_threshold, sell_threshold = pair
    if len(pairs) >= cap:
        return False
    if not 0 < sell_threshold < buy_threshold < 1:
        return False
    if pair in seen:
        return False
    seen.add(pair)
    pairs.append(pair)
    return True


def _rounded_threshold(value: float | Decimal) -> float:
    decimal = Decimal(str(value)).quantize(THRESHOLD_STEP, rounding=ROUND_HALF_UP)
    return float(decimal)


def _decimal_metric(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_metric(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _nested_string(payload: dict[str, Any], first: str, second: str) -> str | None:
    return _payload_string(_payload_dict(payload, first), second)


def _payload_dict(payload: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _all_artifacts_exist(artifact_verification: dict[str, Any]) -> bool:
    return all(_verification_exists(value) for value in artifact_verification.values())


def _verification_exists(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(value.get("exists"))

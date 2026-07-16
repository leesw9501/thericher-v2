"""Attribution-informed threshold band replay for local paper research."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .candidate_threshold_holdout import (
    BoundedCandidateThresholdHoldoutResult,
    CandidateThresholdHoldoutConfig,
    run_bounded_candidate_threshold_holdout,
)
from .candidate_threshold_rerun import (
    _payload_dict,
    _payload_string,
    _read_json_artifact,
    _resolve_optional_path,
)
from .candidate_threshold_robustness import CandidateThresholdRobustnessSliceConfig
from .candidate_training import (
    GpuReadiness,
    _reject_repo_artifact_path,
    detect_gpu_readiness,
)

CandidateThresholdBandRerunStatus = Literal[
    "candidate_threshold_band_rerun_replayed_only",
    "prepared_not_threshold_band_reran",
]
DEFAULT_CANDIDATE_THRESHOLD_BAND_RERUN_RUN_ID = (
    "bounded-candidate-threshold-band-rerun"
)
MAX_CANDIDATE_THRESHOLD_BAND_RERUN_PAIRS = 4
THRESHOLD_STEP = Decimal("0.001")


@dataclass(frozen=True)
class CandidateThresholdBandRerunConfig:
    run_id: str = DEFAULT_CANDIDATE_THRESHOLD_BAND_RERUN_RUN_ID
    max_bars: int = 120
    min_examples: int = 8
    threshold_pair_cap: int = MAX_CANDIDATE_THRESHOLD_BAND_RERUN_PAIRS
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
        if not 0 < self.threshold_pair_cap <= MAX_CANDIDATE_THRESHOLD_BAND_RERUN_PAIRS:
            raise ValueError(
                "threshold_pair_cap must be between 1 and "
                f"{MAX_CANDIDATE_THRESHOLD_BAND_RERUN_PAIRS}"
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
class BoundedCandidateThresholdBandRerunResult:
    run_id: str
    status: CandidateThresholdBandRerunStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    source_attribution_artifact: Path | None
    source_threshold_rerun_artifact: Path | None
    source_robustness_artifact: Path | None
    source_calibration_artifact: Path | None
    band_rerun_artifact: Path
    holdout_artifact: Path | None
    robustness_artifact: Path | None
    candidate_experiment_id: str | None
    candidate_parameters: dict[str, Any]
    selected_variant_id: str | None
    threshold_pairs: tuple[tuple[float, float], ...]
    threshold_derivation: dict[str, Any]
    artifact_verification: dict[str, Any]
    slice_count: int
    completed_slice_count: int
    holdout_slices: tuple[dict[str, Any], ...]
    local_paper_verification: dict[str, Any]
    holdout: BoundedCandidateThresholdHoldoutResult | None
    metrics: dict[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


def run_bounded_candidate_threshold_band_rerun(
    *,
    config: CandidateThresholdBandRerunConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    threshold_attribution_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
) -> BoundedCandidateThresholdBandRerunResult:
    config = config or CandidateThresholdBandRerunConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "candidate-threshold-band-rerun" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    band_rerun_artifact = output_dir / "metrics.json"
    gpu = gpu or detect_gpu_readiness()

    resolved_attribution_artifact = _resolve_optional_path(
        threshold_attribution_artifact,
        artifact_root,
    )
    if resolved_attribution_artifact is not None:
        _reject_repo_artifact_path(resolved_attribution_artifact, repo_root)
    attribution_payload, attribution_error = _read_json_artifact(
        resolved_attribution_artifact,
        required_label="candidate threshold attribution artifact",
    )
    resolved_rerun_artifact = _resolve_optional_path(
        attribution_payload.get("source_threshold_rerun_artifact"),
        artifact_root,
    )
    if resolved_rerun_artifact is not None:
        _reject_repo_artifact_path(resolved_rerun_artifact, repo_root)
    rerun_payload, rerun_error = _read_json_artifact(
        resolved_rerun_artifact,
        required_label="candidate threshold rerun artifact",
    )
    resolved_robustness_artifact = _resolve_optional_path(
        attribution_payload.get("source_robustness_artifact")
        or _nested_value(rerun_payload, "artifacts", "candidate_threshold_robustness"),
        artifact_root,
    )
    if resolved_robustness_artifact is not None:
        _reject_repo_artifact_path(resolved_robustness_artifact, repo_root)
    robustness_payload, robustness_error = _read_json_artifact(
        resolved_robustness_artifact,
        required_label="candidate threshold robustness artifact",
    )
    resolved_calibration_artifact = _resolve_optional_path(
        attribution_payload.get("source_calibration_artifact")
        or rerun_payload.get("source_calibration_artifact"),
        artifact_root,
    )
    if resolved_calibration_artifact is not None:
        _reject_repo_artifact_path(resolved_calibration_artifact, repo_root)
    calibration_payload, calibration_error = _read_json_artifact(
        resolved_calibration_artifact,
        required_label="candidate threshold calibration artifact",
    )
    observed_probability_max = _decimal_metric(
        _payload_dict(attribution_payload, "threshold_band_comparison").get(
            "observed_probability_max"
        )
    )
    source_threshold_pairs = _threshold_pairs_from_payload(
        _payload_dict(rerun_payload, "source_thresholds")
    ) or _threshold_pairs_from_payload(_payload_dict(calibration_payload, "thresholds"))
    threshold_pairs = derive_attribution_informed_threshold_pairs(
        source_threshold_pairs,
        observed_probability_max=observed_probability_max,
        cap=config.threshold_pair_cap,
    )
    slices = _slices_from_robustness_payload(robustness_payload, artifact_root)
    artifact_verification = _artifact_verification(
        attribution_artifact=resolved_attribution_artifact,
        rerun_artifact=resolved_rerun_artifact,
        robustness_artifact=resolved_robustness_artifact,
        calibration_artifact=resolved_calibration_artifact,
        slices=slices,
    )
    initial_errors = tuple(
        error
        for error in (
            attribution_error,
            _status_error(
                attribution_payload,
                expected="candidate_threshold_attribution_only",
                label="candidate threshold attribution",
            ),
            rerun_error,
            _status_error(
                rerun_payload,
                expected="candidate_threshold_rerun_replayed_only",
                label="candidate threshold rerun",
            ),
            robustness_error,
            _status_error(
                robustness_payload,
                expected="candidate_robustness_replayed_only",
                label="candidate threshold robustness",
            ),
            calibration_error,
            _status_error(
                calibration_payload,
                expected="candidate_thresholds_calibrated_only",
                label="candidate threshold calibration",
            ),
            None
            if observed_probability_max is not None
            else "observed probability maximum is missing",
            None
            if source_threshold_pairs
            else "source calibration threshold band is missing",
            None
            if threshold_pairs
            else "no attribution-informed threshold pairs derived",
            None if slices else "no replay slices available for threshold band rerun",
            _artifact_error(artifact_verification),
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
                slices=slices,
                sample_seed=config.sample_seed,
                starting_cash=config.starting_cash,
                quantity=config.quantity,
                fee_bps=config.fee_bps,
                slippage_bps=config.slippage_bps,
            ),
            artifact_root=artifact_root,
            repo_root=repo_root,
            calibration_artifact=resolved_calibration_artifact,
            gpu=gpu,
        )

    status: CandidateThresholdBandRerunStatus = (
        "candidate_threshold_band_rerun_replayed_only"
        if holdout is not None
        and holdout.status == "candidate_threshold_holdout_replayed_only"
        else "prepared_not_threshold_band_reran"
    )
    holdout_reason = None if holdout is None else holdout.reason
    result = BoundedCandidateThresholdBandRerunResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason=(
            "bounded attribution-informed threshold band rerun completed"
            if status == "candidate_threshold_band_rerun_replayed_only"
            else "; ".join(
                initial_errors
                or (holdout_reason or "threshold band rerun did not complete",)
            )
        ),
        source_attribution_artifact=resolved_attribution_artifact,
        source_threshold_rerun_artifact=resolved_rerun_artifact,
        source_robustness_artifact=resolved_robustness_artifact,
        source_calibration_artifact=resolved_calibration_artifact,
        band_rerun_artifact=band_rerun_artifact,
        holdout_artifact=None if holdout is None else holdout.holdout_artifact,
        robustness_artifact=None if holdout is None else holdout.robustness_artifact,
        candidate_experiment_id=_payload_string(
            attribution_payload,
            "candidate_experiment_id",
        )
        or _payload_string(rerun_payload, "candidate_experiment_id"),
        candidate_parameters=_payload_dict(attribution_payload, "candidate_parameters")
        or _payload_dict(rerun_payload, "candidate_parameters"),
        selected_variant_id=_payload_string(attribution_payload, "selected_variant_id")
        or _payload_string(rerun_payload, "selected_variant_id"),
        threshold_pairs=threshold_pairs,
        threshold_derivation=_threshold_derivation_payload(
            observed_probability_max=observed_probability_max,
            source_threshold_pairs=source_threshold_pairs,
            threshold_pairs=threshold_pairs,
            cap=config.threshold_pair_cap,
        ),
        artifact_verification=artifact_verification,
        slice_count=len(slices),
        completed_slice_count=0 if holdout is None else holdout.completed_slice_count,
        holdout_slices=() if holdout is None else holdout.holdout_slices,
        local_paper_verification={}
        if holdout is None
        else holdout.local_paper_verification,
        holdout=holdout,
        metrics=_band_rerun_metrics(
            status=status,
            artifact_verification=artifact_verification,
            threshold_pairs=threshold_pairs,
            holdout=holdout,
        ),
    )
    band_rerun_artifact.write_text(
        json.dumps(
            _candidate_threshold_band_rerun_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def derive_attribution_informed_threshold_pairs(
    source_threshold_pairs: tuple[tuple[float, float], ...],
    *,
    observed_probability_max: Decimal | float | str | None,
    cap: int = MAX_CANDIDATE_THRESHOLD_BAND_RERUN_PAIRS,
) -> tuple[tuple[float, float], ...]:
    if cap <= 0:
        return ()
    observed = _decimal_metric(observed_probability_max)
    if observed is None:
        return ()
    observed_ceiling = _floor_threshold(observed)
    valid_pairs = tuple(
        sorted(
            {
                (_rounded_threshold(buy), _rounded_threshold(sell))
                for buy, sell in source_threshold_pairs
                if 0 < sell < buy < 1
            }
        )
    )
    inside_source = tuple(
        pair for pair in valid_pairs if Decimal(str(pair[0])) <= observed_ceiling
    )
    if inside_source:
        return inside_source[-cap:]
    if not valid_pairs:
        return ()
    sell_floor = min(sell for _buy, sell in valid_pairs)
    generated: list[tuple[float, float]] = []
    buy = observed_ceiling
    while len(generated) < cap and buy > Decimal(str(sell_floor)):
        pair = (_rounded_threshold(buy), _rounded_threshold(sell_floor))
        if 0 < pair[1] < pair[0] < 1:
            generated.append(pair)
        buy -= THRESHOLD_STEP
    return tuple(reversed(generated))


def _candidate_threshold_band_rerun_payload(
    result: BoundedCandidateThresholdBandRerunResult,
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
            "source_attribution_artifact": None
            if result.source_attribution_artifact is None
            else str(result.source_attribution_artifact),
            "source_threshold_rerun_artifact": None
            if result.source_threshold_rerun_artifact is None
            else str(result.source_threshold_rerun_artifact),
            "source_robustness_artifact": None
            if result.source_robustness_artifact is None
            else str(result.source_robustness_artifact),
            "source_calibration_artifact": None
            if result.source_calibration_artifact is None
            else str(result.source_calibration_artifact),
            "candidate_experiment_id": result.candidate_experiment_id,
            "candidate_parameters": result.candidate_parameters,
            "selected_variant_id": result.selected_variant_id,
            "threshold_pairs": [
                {
                    "buy_threshold": f"{buy_threshold:.6f}",
                    "sell_threshold": f"{sell_threshold:.6f}",
                }
                for buy_threshold, sell_threshold in result.threshold_pairs
            ],
            "threshold_derivation": result.threshold_derivation,
            "artifact_verification": result.artifact_verification,
            "slice_count": result.slice_count,
            "completed_slice_count": result.completed_slice_count,
            "holdout_slices": result.holdout_slices,
            "local_paper_verification": result.local_paper_verification,
            "metrics": result.metrics,
            "result_scope": {
                "mode": "research_threshold_band_rerun_only",
                "descriptive_only": True,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_threshold_band_rerun": str(result.band_rerun_artifact),
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


def _threshold_derivation_payload(
    *,
    observed_probability_max: Decimal | None,
    source_threshold_pairs: tuple[tuple[float, float], ...],
    threshold_pairs: tuple[tuple[float, float], ...],
    cap: int,
) -> dict[str, Any]:
    return {
        "mode": "research_threshold_band_rerun_only",
        "derivation": "attribution_observed_range_source_band",
        "threshold_pair_cap": cap,
        "observed_probability_max": None
        if observed_probability_max is None
        else f"{observed_probability_max:.6f}",
        "observed_probability_ceiling": None
        if observed_probability_max is None
        else f"{_floor_threshold(observed_probability_max):.6f}",
        "source_threshold_pair_count": len(source_threshold_pairs),
        "threshold_pair_count": len(threshold_pairs),
        "threshold_pairs": [
            {
                "buy_threshold": f"{buy_threshold:.6f}",
                "sell_threshold": f"{sell_threshold:.6f}",
            }
            for buy_threshold, sell_threshold in threshold_pairs
        ],
        "descriptive_only": True,
        "promotion_gate": False,
    }


def _band_rerun_metrics(
    *,
    status: CandidateThresholdBandRerunStatus,
    artifact_verification: dict[str, Any],
    threshold_pairs: tuple[tuple[float, float], ...],
    holdout: BoundedCandidateThresholdHoldoutResult | None,
) -> dict[str, Any]:
    local_verification = {} if holdout is None else holdout.local_paper_verification
    return {
        "status": status,
        "research_threshold_band_rerun_only": True,
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
        "local_paper_verification": local_verification,
        "all_fills_local_paper": local_verification.get("all_fills_local_paper")
        is True,
    }


def _slices_from_robustness_payload(
    payload: dict[str, Any],
    artifact_root: Path,
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    raw_slices = payload.get("slices")
    if not isinstance(raw_slices, list | tuple):
        return ()
    slices: list[CandidateThresholdRobustnessSliceConfig] = []
    for item in raw_slices:
        if not isinstance(item, dict):
            continue
        slice_id = _payload_string(item, "slice_id")
        symbol = _payload_string(item, "symbol")
        yahoo_snapshot = _resolve_optional_path(item.get("yahoo_snapshot"), artifact_root)
        trace_artifact = _resolve_optional_path(
            item.get("probability_trace_artifact"),
            artifact_root,
        )
        if slice_id is None or symbol is None or yahoo_snapshot is None:
            continue
        slices.append(
            CandidateThresholdRobustnessSliceConfig(
                slice_id=slice_id,
                yahoo_snapshot=yahoo_snapshot,
                symbol=symbol,
                probability_trace_artifact=trace_artifact,
            )
        )
    return tuple(slices)


def _artifact_verification(
    *,
    attribution_artifact: Path | None,
    rerun_artifact: Path | None,
    robustness_artifact: Path | None,
    calibration_artifact: Path | None,
    slices: tuple[CandidateThresholdRobustnessSliceConfig, ...],
) -> dict[str, Any]:
    return {
        "threshold_attribution": _artifact_payload(attribution_artifact),
        "threshold_rerun": _artifact_payload(rerun_artifact),
        "source_robustness": _artifact_payload(robustness_artifact),
        "source_calibration": _artifact_payload(calibration_artifact),
        "yahoo_snapshots": {
            item.slice_id: _artifact_payload(item.yahoo_snapshot) for item in slices
        },
        "trace_artifacts": {
            item.slice_id: _artifact_payload(item.probability_trace_artifact)
            for item in slices
        },
    }


def _artifact_payload(path: Path | None) -> dict[str, Any]:
    return {
        "artifact": None if path is None else str(path),
        "exists": False if path is None else path.exists(),
    }


def _artifact_error(artifact_verification: dict[str, Any]) -> str | None:
    missing = tuple(_missing_artifact_keys(artifact_verification))
    if not missing:
        return None
    return "referenced threshold band rerun artifacts are missing: " + ", ".join(
        missing
    )


def _missing_artifact_keys(payload: dict[str, Any], prefix: str = "") -> tuple[str, ...]:
    missing: list[str] = []
    for key, value in payload.items():
        label = f"{prefix}.{key}" if prefix else str(key)
        if _is_artifact_payload(value):
            if not value.get("exists"):
                missing.append(label)
            continue
        if isinstance(value, dict):
            missing.extend(_missing_artifact_keys(value, label))
    return tuple(missing)


def _is_artifact_payload(value: Any) -> bool:
    return isinstance(value, dict) and "exists" in value and "artifact" in value


def _all_artifacts_exist(artifact_verification: dict[str, Any]) -> bool:
    return not _missing_artifact_keys(artifact_verification)


def _threshold_pairs_from_payload(
    payload: dict[str, Any],
) -> tuple[tuple[float, float], ...]:
    raw_pairs = payload.get("threshold_pairs")
    if not isinstance(raw_pairs, list):
        return ()
    pairs: list[tuple[float, float]] = []
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, dict):
            continue
        buy = _float_metric(raw_pair.get("buy_threshold"))
        sell = _float_metric(raw_pair.get("sell_threshold"))
        if buy is None or sell is None or not 0 < sell < buy < 1:
            continue
        pairs.append((_rounded_threshold(buy), _rounded_threshold(sell)))
    return tuple(pairs)


def _status_error(payload: dict[str, Any], *, expected: str, label: str) -> str | None:
    if not payload:
        return None
    if payload.get("status") == expected:
        return None
    return _payload_string(payload, "reason") or f"{label} was not completed"


def _nested_value(payload: dict[str, Any], first: str, second: str) -> Any:
    parent = payload.get(first)
    if not isinstance(parent, dict):
        return None
    return parent.get(second)


def _rounded_threshold(value: float | Decimal) -> float:
    decimal = Decimal(str(value)).quantize(THRESHOLD_STEP, rounding=ROUND_HALF_UP)
    return float(decimal)


def _floor_threshold(value: Decimal) -> Decimal:
    return value.quantize(THRESHOLD_STEP, rounding=ROUND_FLOOR)


def _decimal_metric(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float_metric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

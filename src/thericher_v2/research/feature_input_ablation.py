"""Bounded feature-input ablation over diagnostic candidate-entry rows."""

from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.serialization import to_jsonable

from .validation import GpuReadiness, _reject_repo_artifact_path, detect_gpu_readiness

FeatureInputAblationStatus = Literal[
    "feature_input_ablation_ran_only",
    "prepared_not_feature_input_ablated",
]

DEFAULT_FEATURE_INPUT_ABLATION_RUN_ID = "bounded-feature-input-ablation"
MAX_FEATURE_INPUT_ABLATION_EPOCHS = 20
MAX_FEATURE_INPUT_ABLATION_STEPS = 1024
MAX_FEATURE_INPUT_ABLATION_HIDDEN_UNITS = 64
DEFAULT_FEATURE_INPUT_ABLATION_HIDDEN_UNITS = 8
OPTIONAL_FEATURE_INPUT_ABLATION_BACKENDS = ("torch",)
DEFAULT_FEATURE_INPUT_ABLATION_ROW_MODE = "selected"
SUPPORTED_FEATURE_INPUT_ABLATION_ROW_MODES = ("selected", "all_diagnostic")
FeatureInputAblationRowMode = Literal["selected", "all_diagnostic"]

APP_MODEL_ARTIFACT_ROOT = PurePosixPath("/app/model_artifacts")
APP_MARKET_DATA_ROOT = PurePosixPath("/app/market_data")
DEFAULT_HOST_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_HOST_MARKET_DATA_ROOT = Path("D:/market_data")

ADVERSE_OR_NO_LIFT_BUCKETS = ("early_adverse_dominant", "early_no_lift")
NON_ADVERSE_BUCKETS = ("early_lift", "early_mixed")

EXISTING_THRESHOLD_META_BASELINE_GROUP = "existing_threshold_meta_baseline"
RAW_PRE_ENTRY_GROUP = "raw_pre_entry"
RAW_PRE_ENTRY_PLUS_PROBABILITY_META_GROUP = "raw_pre_entry_plus_probability_meta"
SUPPORTED_FEATURE_INPUT_GROUPS = (
    EXISTING_THRESHOLD_META_BASELINE_GROUP,
    RAW_PRE_ENTRY_GROUP,
    RAW_PRE_ENTRY_PLUS_PROBABILITY_META_GROUP,
)

PROBABILITY_DERIVED_FEATURE_NAMES = ("probability_margin", "probability_rank_pct")
RAW_PRE_ENTRY_FEATURE_NAMES = (
    "pre_close_return",
    "pre_high_low_range_pct",
    "pre_last_close_position_in_range",
    "pre_last_volume_vs_prior_avg",
)
UNIQUE_SIGNAL_KEY_FIELDS = ("slice_id", "symbol", "execution_bar_start", "offset")
PROBABILITY_BAND_IDS = (
    "tertile_1_low_probability",
    "tertile_2_mid_probability",
    "tertile_3_high_probability",
)


@dataclass(frozen=True)
class FeatureInputAblationConfig:
    run_id: str = DEFAULT_FEATURE_INPUT_ABLATION_RUN_ID
    max_epochs: int = 8
    max_steps: int = 256
    min_examples: int = 8
    hidden_units: int = DEFAULT_FEATURE_INPUT_ABLATION_HIDDEN_UNITS
    feature_groups: tuple[str, ...] = SUPPORTED_FEATURE_INPUT_GROUPS
    row_mode: FeatureInputAblationRowMode = DEFAULT_FEATURE_INPUT_ABLATION_ROW_MODE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        _validate_positive_cap(
            self.max_epochs,
            field_name="max_epochs",
            ceiling=MAX_FEATURE_INPUT_ABLATION_EPOCHS,
        )
        _validate_positive_cap(
            self.max_steps,
            field_name="max_steps",
            ceiling=MAX_FEATURE_INPUT_ABLATION_STEPS,
        )
        if self.min_examples <= 0:
            raise ValueError("min_examples must be positive")
        _validate_positive_cap(
            self.hidden_units,
            field_name="hidden_units",
            ceiling=MAX_FEATURE_INPUT_ABLATION_HIDDEN_UNITS,
        )
        if not self.feature_groups:
            raise ValueError("feature_groups are required")
        if len(self.feature_groups) > 3:
            raise ValueError("feature_groups must contain at most three groups")
        unsupported = set(self.feature_groups).difference(SUPPORTED_FEATURE_INPUT_GROUPS)
        if unsupported:
            raise ValueError(f"unsupported feature input groups: {sorted(unsupported)}")
        if self.row_mode not in SUPPORTED_FEATURE_INPUT_ABLATION_ROW_MODES:
            raise ValueError(f"unsupported feature input row_mode: {self.row_mode}")


@dataclass(frozen=True)
class _AblationBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FeatureInputGroupDataset:
    group_id: str
    feature_names: tuple[str, ...]
    feature_roles: dict[str, str]
    features: tuple[tuple[float, ...], ...]
    missing_value_counts: dict[str, int]
    missing_value_row_indexes: dict[str, tuple[int, ...]]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class FeatureInputAblationDataset:
    row_mode: FeatureInputAblationRowMode
    labels: tuple[int, ...]
    label_names: dict[int, str]
    row_metadata: tuple[dict[str, str], ...]
    rows_seen: int
    rows_used: int
    rows_dropped: int
    source_slices: tuple[str, ...]
    row_source_counts: dict[str, int]
    reconstruction: dict[str, Any]
    feature_groups: tuple[FeatureInputGroupDataset, ...]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class _UniqueSignalRecord:
    signal_key: tuple[str, str, str, str]
    label: int
    probability: float
    metadata: dict[str, str]
    row_indexes: tuple[int, ...]


@dataclass(frozen=True)
class _UniqueSignalCollapse:
    grouped: dict[tuple[str, str, str, str], list[int]]
    records: tuple[_UniqueSignalRecord, ...]
    missing_key_rows: int
    mixed_label_signal_count: int
    mixed_label_row_count: int
    score_spans: tuple[float, ...]


@dataclass(frozen=True)
class BoundedFeatureInputAblationResult:
    run_id: str
    status: FeatureInputAblationStatus
    checked_at: datetime
    gpu: GpuReadiness
    reason: str
    available_backends: tuple[str, ...]
    selected_backend: str | None
    source_stability_artifact: Path | None
    rows_seen: int
    rows_used: int
    rows_dropped: int
    label_counts: dict[str, int]
    feature_group_ids: tuple[str, ...]
    source_evidence: dict[str, Any]
    metrics: dict[str, Any]
    metrics_artifact: Path
    model_artifact: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


FeatureInputAblationRunner = Callable[
    [FeatureInputAblationDataset, Path, FeatureInputAblationConfig],
    dict[str, Any],
]


def run_bounded_feature_input_ablation(
    *,
    config: FeatureInputAblationConfig | None = None,
    artifact_root: Path,
    repo_root: Path | None = None,
    stability_artifact: Path | None = None,
    gpu: GpuReadiness | None = None,
    trainer_runner: FeatureInputAblationRunner | None = None,
) -> BoundedFeatureInputAblationResult:
    config = config or FeatureInputAblationConfig()
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "feature-input-ablation" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_artifact = output_dir / "metrics.json"
    model_artifact = output_dir / "feature_input_ablation.pt"
    gpu = gpu or detect_gpu_readiness()
    available_backends = _available_backends()
    selected_backend = "injected" if trainer_runner is not None else _selected_backend()

    payload = _read_stability_payload(stability_artifact)
    dataset = _build_dataset(payload, config=config, artifact_root=artifact_root)
    source_evidence = _source_evidence(payload)
    reason_parts: list[str] = []
    metrics: dict[str, Any] = {
        "row_mode": dataset.row_mode,
        "feature_group_count": len(dataset.feature_groups),
        "feature_groups": [_feature_group_payload(group) for group in dataset.feature_groups],
        "label_counts": _label_counts(dataset.labels),
        "descriptive_evaluation_context": _descriptive_evaluation_context(
            labels=dataset.labels,
            row_metadata=dataset.row_metadata,
        ),
        "source_slices": dataset.source_slices,
        "row_source_counts": dataset.row_source_counts,
        "row_reconstruction": dataset.reconstruction,
        "raw_market_feature_names": RAW_PRE_ENTRY_FEATURE_NAMES,
        "probability_derived_feature_names": PROBABILITY_DERIVED_FEATURE_NAMES,
    }
    status: FeatureInputAblationStatus = "prepared_not_feature_input_ablated"
    final_model_artifact: Path | None = None

    if stability_artifact is None:
        reason_parts.append("feature-input stability artifact was not provided")
    elif not stability_artifact.exists():
        reason_parts.append("feature-input stability artifact is missing")
    elif dataset.rows_used < config.min_examples:
        reason_parts.append(
            f"only {dataset.rows_used} labeled {config.row_mode} rows available; "
            f"min_examples={config.min_examples}"
        )
    elif not gpu.available and trainer_runner is None:
        reason_parts.append("GPU readiness unavailable for feature-input ablation")
    elif selected_backend is None:
        reason_parts.append("no feature-input ablation backend available")
    else:
        runner = trainer_runner or _run_torch_cuda_feature_input_ablation
        try:
            runner_metrics = runner(dataset, model_artifact, config)
        except Exception as exc:  # noqa: BLE001
            reason_parts.append(f"feature-input ablation unavailable: {exc}")
        else:
            status = "feature_input_ablation_ran_only"
            reason_parts.append("bounded feature-input ablation completed")
            final_model_artifact = model_artifact if model_artifact.exists() else None
            metrics["runner"] = runner_metrics
            metrics["group_results"] = _group_results_by_id(runner_metrics)

    result = BoundedFeatureInputAblationResult(
        run_id=config.run_id,
        status=status,
        checked_at=datetime.now(UTC),
        gpu=gpu,
        reason="; ".join(reason_parts),
        available_backends=available_backends,
        selected_backend=selected_backend,
        source_stability_artifact=stability_artifact,
        rows_seen=dataset.rows_seen,
        rows_used=dataset.rows_used,
        rows_dropped=dataset.rows_dropped,
        label_counts=_label_counts(dataset.labels),
        feature_group_ids=tuple(group.group_id for group in dataset.feature_groups),
        source_evidence=source_evidence,
        metrics=metrics,
        metrics_artifact=metrics_artifact,
        model_artifact=final_model_artifact,
    )
    metrics_artifact.write_text(
        json.dumps(
            _feature_input_ablation_payload(result, artifact_root),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result


def _run_torch_cuda_feature_input_ablation(
    dataset: FeatureInputAblationDataset,
    model_artifact: Path,
    config: FeatureInputAblationConfig,
) -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch CUDA is not available")
    torch.manual_seed(41)
    device = torch.device("cuda")
    y = torch.tensor(dataset.labels, dtype=torch.float32, device=device).view(-1, 1)
    group_metrics: list[dict[str, Any]] = []
    state_dicts: dict[str, Any] = {}

    for group in dataset.feature_groups:
        x = torch.tensor(group.features, dtype=torch.float32, device=device)
        model = torch.nn.Sequential(
            torch.nn.Linear(len(group.feature_names), config.hidden_units),
            torch.nn.ReLU(),
            torch.nn.Linear(config.hidden_units, 1),
        ).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        loss_fn = torch.nn.BCEWithLogitsLoss()
        with torch.no_grad():
            initial_loss = loss_fn(model(x), y)
        epochs_run = 0
        steps_run = 0
        for epoch in range(config.max_epochs):
            optimizer.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            epochs_run = epoch + 1
            steps_run += 1
            if steps_run >= config.max_steps:
                break
        with torch.no_grad():
            final_logits = model(x)
            final_loss = loss_fn(final_logits, y)
            probabilities = torch.sigmoid(final_logits)
            predictions = (probabilities >= 0.5).float()
            accuracy = (predictions == y).float().mean()
        probability_values = tuple(
            float(value) for value in probabilities.detach().cpu().view(-1).tolist()
        )
        state_dicts[group.group_id] = model.state_dict()
        group_metrics.append(
            {
                "group_id": group.group_id,
                "feature_names": group.feature_names,
                "feature_roles": group.feature_roles,
                "feature_count": len(group.feature_names),
                "epochs_run": epochs_run,
                "steps_run": steps_run,
                "initial_loss": f"{initial_loss.item():.6f}",
                "final_loss": f"{final_loss.item():.6f}",
                "accuracy": f"{accuracy.item():.6f}",
                "mean_probability": f"{probabilities.mean().item():.6f}",
                "descriptive_evaluation": _descriptive_evaluation_payload(
                    labels=dataset.labels,
                    probabilities=probability_values,
                    row_metadata=dataset.row_metadata,
                    feature_names=group.feature_names,
                    features=group.features,
                    missing_value_row_indexes=group.missing_value_row_indexes,
                ),
            }
        )

    torch.cuda.synchronize()
    model_artifact.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "schema_version": SCHEMA_VERSION,
            "model_kind": "tiny_mlp_feature_input_ablation_v0",
            "feature_groups": [
                {
                    "group_id": group.group_id,
                    "feature_names": group.feature_names,
                    "feature_roles": group.feature_roles,
                }
                for group in dataset.feature_groups
            ],
            "label_names": dataset.label_names,
            "state_dicts": state_dicts,
        },
        model_artifact,
    )
    return {
        "backend": "torch",
        "operation": "tiny_mlp_feature_input_ablation",
        "device": torch.cuda.get_device_name(device),
        "examples_seen": len(dataset.labels),
        "hidden_units": config.hidden_units,
        "evaluation_scope": {
            "in_sample": True,
            "descriptive_only": True,
            "held_out_split": False,
        },
        "groups": group_metrics,
        "model_artifact": str(model_artifact),
    }


def _feature_input_ablation_payload(
    result: BoundedFeatureInputAblationResult,
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
            "available_backends": result.available_backends,
            "selected_backend": result.selected_backend,
            "source_stability_artifact": (
                None
                if result.source_stability_artifact is None
                else str(result.source_stability_artifact)
            ),
            "row_mode": result.metrics.get("row_mode"),
            "rows_seen": result.rows_seen,
            "rows_used": result.rows_used,
            "rows_dropped": result.rows_dropped,
            "label_counts": result.label_counts,
            "feature_group_ids": result.feature_group_ids,
            "source_evidence": result.source_evidence,
            "metrics": result.metrics,
            "result_scope": {
                "mode": "research_feature_input_ablation_only",
                "descriptive_only": True,
                "promotion_gate": False,
                "local_paper_replay_changed": False,
                "broker_used": False,
                "kis_api_called": False,
                "credentials_read": False,
            },
            "artifacts": {
                "feature_input_ablation": str(result.metrics_artifact),
                "model": None if result.model_artifact is None else str(result.model_artifact),
            },
            "artifact_policy": {
                "artifact_root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _build_dataset(
    payload: dict[str, Any],
    *,
    config: FeatureInputAblationConfig,
    artifact_root: Path,
) -> FeatureInputAblationDataset:
    raw_rows, reconstruction = _candidate_entry_rows(
        payload,
        config=config,
        artifact_root=artifact_root,
    )
    labels: list[int] = []
    kept_rows: list[dict[str, Any]] = []
    row_metadata: list[dict[str, str]] = []
    source_slices: list[str] = []
    row_source_counts = Counter()
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        row_source_counts[str(row.get("source") or "missing")] += 1
        if row.get("source") != "diagnostic_overlay":
            continue
        label = _label_from_row(row)
        if label is None:
            continue
        labels.append(label)
        kept_rows.append(row)
        slice_id = str(row.get("slice_id") or "")
        variant_id = str(row.get("variant_id") or "")
        row_metadata.append(
            {
                "source": str(row.get("source") or "missing"),
                "slice_id": slice_id or "missing",
                "role": str(row.get("role") or "missing"),
                "symbol": str(row.get("symbol") or "missing"),
                "variant_id": variant_id or "missing",
                "offset": str(row.get("offset")) if row.get("offset") is not None else "missing",
                "execution_bar_start": str(row.get("execution_bar_start") or "missing"),
                "slice_variant_id": f"{slice_id or 'missing'}:{variant_id or 'missing'}",
            }
        )
        if slice_id and slice_id not in source_slices:
            source_slices.append(slice_id)

    groups = tuple(_build_group_dataset(group_id, kept_rows) for group_id in config.feature_groups)
    return FeatureInputAblationDataset(
        row_mode=config.row_mode,
        labels=tuple(labels),
        label_names={1: "adverse_or_no_lift", 0: "non_adverse"},
        row_metadata=tuple(row_metadata),
        rows_seen=len(raw_rows),
        rows_used=len(kept_rows),
        rows_dropped=len(raw_rows) - len(kept_rows),
        source_slices=tuple(source_slices),
        row_source_counts=dict(row_source_counts),
        reconstruction=reconstruction,
        feature_groups=groups,
    )


def _candidate_entry_rows(
    payload: dict[str, Any],
    *,
    config: FeatureInputAblationConfig,
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if config.row_mode == "selected":
        rows = payload.get("selected_candidate_entry_rows")
        raw_rows = rows if isinstance(rows, list) else []
        return list(raw_rows), {
            "mode": "selected",
            "row_source": "selected_candidate_entry_rows",
            "rows_reconstructed": 0,
            "rows_loaded": len(raw_rows),
            "descriptive_only": True,
        }
    return _reconstruct_all_diagnostic_rows(payload, artifact_root=artifact_root)


def _reconstruct_all_diagnostic_rows(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    consumed_slices = payload.get("consumed_slices")
    metrics = payload.get("metrics")
    variant_meta = metrics.get("added_source_variant_meta") if isinstance(metrics, dict) else None
    if not isinstance(consumed_slices, list) or not isinstance(variant_meta, list):
        return [], {
            "mode": "all_diagnostic",
            "row_source": "lineage_reconstruction",
            "rows_reconstructed": 0,
            "errors": ["stability artifact lacks consumed_slices or added_source_variant_meta"],
            "descriptive_only": True,
        }

    slice_by_id = {
        str(item.get("slice_id")): item
        for item in consumed_slices
        if isinstance(item, dict) and item.get("slice_id")
    }
    variants_by_slice: dict[str, list[dict[str, Any]]] = {}
    for item in variant_meta:
        if not isinstance(item, dict):
            continue
        slice_id = str(item.get("slice_id") or "")
        if not slice_id:
            continue
        variants_by_slice.setdefault(slice_id, []).append(item)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    slice_counts: dict[str, int] = {}
    variant_counts: dict[str, int] = {}

    for slice_id, variants in variants_by_slice.items():
        slice_info = slice_by_id.get(slice_id)
        if not isinstance(slice_info, dict):
            errors.append(f"{slice_id}: missing consumed slice lineage")
            continue
        symbol = str(slice_info.get("symbol") or variants[0].get("symbol") or "")
        trace_path = _resolve_lineage_path(
            slice_info.get("probability_trace_artifact"),
            artifact_root=artifact_root,
        )
        market_path = _resolve_lineage_path(
            slice_info.get("local_market_data_path"),
            artifact_root=artifact_root,
        )
        trace_payload, trace_error = _read_json_object(trace_path)
        if trace_error is not None:
            errors.append(f"{slice_id}: {trace_error}")
            continue
        trace_entries = trace_payload.get("entries")
        if not isinstance(trace_entries, list):
            errors.append(f"{slice_id}: probability trace has no entries")
            continue
        bars, bars_error = _load_symbol_bars(market_path, symbol=symbol)
        if bars_error is not None:
            errors.append(f"{slice_id}: {bars_error}")
            continue
        rank_by_offset = _probability_rank_by_offset(trace_entries)

        for variant in variants:
            buy_threshold = _as_float(variant.get("buy_threshold"))
            sell_threshold = _as_float(variant.get("sell_threshold"))
            variant_id = str(variant.get("variant_id") or "")
            if buy_threshold is None or sell_threshold is None or not variant_id:
                errors.append(f"{slice_id}: incomplete variant threshold metadata")
                continue
            variant_row_count = 0
            for entry in trace_entries:
                if not isinstance(entry, dict):
                    continue
                probability = _as_float(entry.get("probability"))
                if probability is None or probability < buy_threshold:
                    continue
                row = _diagnostic_row_from_trace_entry(
                    entry,
                    bars=bars,
                    rank_by_offset=rank_by_offset,
                    slice_info=slice_info,
                    variant=variant,
                    buy_threshold=buy_threshold,
                    sell_threshold=sell_threshold,
                    probability=probability,
                    trace_entries=trace_entries,
                )
                if row is None:
                    continue
                rows.append(row)
                variant_row_count += 1
            variant_counts[f"{slice_id}:{variant_id}"] = variant_row_count
            slice_counts[slice_id] = slice_counts.get(slice_id, 0) + variant_row_count

    return rows, {
        "mode": "all_diagnostic",
        "row_source": "lineage_reconstruction",
        "rows_reconstructed": len(rows),
        "slice_counts": slice_counts,
        "variant_counts": variant_counts,
        "error_count": len(errors),
        "errors": errors[:10],
        "descriptive_only": True,
        "local_paper_replay_changed": False,
    }


def _diagnostic_row_from_trace_entry(
    entry: dict[str, Any],
    *,
    bars: tuple[_AblationBar, ...],
    rank_by_offset: dict[int, int],
    slice_info: dict[str, Any],
    variant: dict[str, Any],
    buy_threshold: float,
    sell_threshold: float,
    probability: float,
    trace_entries: list[Any],
) -> dict[str, Any] | None:
    execution_start = _parse_utc_datetime(entry.get("execution_bar_start"))
    signal_start = _parse_utc_datetime(entry.get("signal_bar_start"))
    if execution_start is None:
        return None
    bar_index_by_timestamp = {bar.timestamp: index for index, bar in enumerate(bars)}
    bar_index = bar_index_by_timestamp.get(execution_start)
    if bar_index is None:
        return None
    offset = _as_int(entry.get("offset"))
    rank_desc = rank_by_offset.get(offset) if offset is not None else None
    rank_pct = None
    if rank_desc is not None and rank_by_offset:
        rank_pct = (len(rank_by_offset) - rank_desc + 1) / len(rank_by_offset)
    execution_open = _as_float(entry.get("execution_open"))
    if execution_open is None:
        execution_open = bars[bar_index].open
    return {
        "source": "diagnostic_overlay",
        "slice_id": str(slice_info.get("slice_id") or ""),
        "role": str(slice_info.get("role") or ""),
        "symbol": str(slice_info.get("symbol") or variant.get("symbol") or ""),
        "variant_id": str(variant.get("variant_id") or ""),
        "thresholds": {
            "buy_threshold": buy_threshold,
            "sell_threshold": sell_threshold,
        },
        "offset": offset,
        "signal_bar_start": None if signal_start is None else signal_start.isoformat(),
        "execution_bar_start": execution_start.isoformat(),
        "probability": probability,
        "probability_margin": probability - buy_threshold,
        "probability_rank_desc": rank_desc,
        "probability_rank_pct": rank_pct,
        "pre_entry_3bar": _pre_entry_summary(bars, bar_index),
        "early_3bar": _early_3bar_summary(bars, bar_index, entry_open=execution_open),
        "sell_threshold_exit_outcome": _sell_threshold_exit_outcome(
            trace_entries,
            current_offset=offset,
            sell_threshold=sell_threshold,
            entry_open=execution_open,
        ),
        "local_paper_reference": {
            "entered_local_paper": False,
            "same_timestamp_sell_fill": False,
            "source": None,
        },
    }


def _pre_entry_summary(
    bars: tuple[_AblationBar, ...],
    execution_bar_index: int,
) -> dict[str, Any]:
    window = bars[max(0, execution_bar_index - 3) : execution_bar_index]
    if len(window) < 3:
        return {"bar_count": len(window), "bucket": "pre_entry_insufficient"}
    first_close = window[0].close
    last_close = window[-1].close
    close_delta = last_close - first_close
    high = max(bar.high for bar in window)
    low = min(bar.low for bar in window)
    high_low_range = high - low
    prior_volumes = [bar.volume for bar in window[:-1]]
    prior_volume_avg = sum(prior_volumes) / len(prior_volumes) if prior_volumes else 0.0
    last_volume_vs_prior_avg = None
    if prior_volume_avg:
        last_volume_vs_prior_avg = (window[-1].volume - prior_volume_avg) / prior_volume_avg
    last_close_position = None
    if high_low_range:
        last_close_position = (last_close - low) / high_low_range
    range_pct = high_low_range / last_close if last_close else None
    return {
        "bar_count": len(window),
        "bucket": _pre_entry_bucket(close_delta),
        "close_delta": _format_float(close_delta),
        "close_return": _format_float(close_delta / first_close if first_close else None),
        "high_low_range": _format_float(high_low_range),
        "range_pct_of_last_close": _format_float(range_pct),
        "last_close_position_in_range": _format_float(last_close_position),
        "last_volume_vs_prior_avg": _format_float(last_volume_vs_prior_avg),
        "volume_sum": _format_float(sum(bar.volume for bar in window)),
    }


def _early_3bar_summary(
    bars: tuple[_AblationBar, ...],
    execution_bar_index: int,
    *,
    entry_open: float,
) -> dict[str, Any]:
    window = bars[execution_bar_index : execution_bar_index + 3]
    if len(window) < 3:
        return {"bar_count": len(window), "path_quality_bucket": "early_unavailable"}
    mae = min(bar.low for bar in window) - entry_open
    mfe = max(bar.high for bar in window) - entry_open
    return {
        "bar_count": len(window),
        "mae_from_entry": _format_float(mae),
        "mfe_from_entry": _format_float(mfe),
        "mae_pct": _format_float(mae / entry_open if entry_open else None),
        "mfe_pct": _format_float(mfe / entry_open if entry_open else None),
        "path_quality_bucket": _early_path_quality_bucket(mae=mae, mfe=mfe),
    }


def _sell_threshold_exit_outcome(
    trace_entries: list[Any],
    *,
    current_offset: int | None,
    sell_threshold: float,
    entry_open: float,
) -> dict[str, Any]:
    if current_offset is None:
        return {
            "source": "diagnostic_overlay",
            "seen_before_window_end": False,
            "outcome_bucket": "sell_threshold_offset_missing",
        }
    for item in trace_entries:
        if not isinstance(item, dict):
            continue
        offset = _as_int(item.get("offset"))
        probability = _as_float(item.get("probability"))
        if offset is None or probability is None or offset <= current_offset:
            continue
        if probability > sell_threshold:
            continue
        execution_open = _as_float(item.get("execution_open"))
        gross_delta = None if execution_open is None else execution_open - entry_open
        return {
            "source": "diagnostic_overlay",
            "seen_before_window_end": True,
            "bars_to_first_sell_threshold": offset - current_offset,
            "first_sell_threshold_offset": offset,
            "first_sell_threshold_probability": probability,
            "gross_delta_to_first_sell_threshold": _format_float(gross_delta),
            "outcome_bucket": (
                "sell_threshold_non_negative_gross"
                if gross_delta is not None and gross_delta >= 0
                else "sell_threshold_negative_gross"
            ),
        }
    return {
        "source": "diagnostic_overlay",
        "seen_before_window_end": False,
        "outcome_bucket": "sell_threshold_not_seen",
    }


def _pre_entry_bucket(close_delta: float) -> str:
    if close_delta > 0:
        return "pre_entry_up"
    if close_delta < 0:
        return "pre_entry_down"
    return "pre_entry_flat"


def _early_path_quality_bucket(*, mae: float, mfe: float) -> str:
    if mfe <= 0:
        return "early_no_lift"
    if mae >= 0:
        return "early_lift"
    if abs(mae) > mfe:
        return "early_adverse_dominant"
    return "early_mixed"


def _probability_rank_by_offset(trace_entries: list[Any]) -> dict[int, int]:
    ranked: list[tuple[int, float]] = []
    for item in trace_entries:
        if not isinstance(item, dict):
            continue
        offset = _as_int(item.get("offset"))
        probability = _as_float(item.get("probability"))
        if offset is None or probability is None:
            continue
        ranked.append((offset, probability))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return {offset: rank for rank, (offset, _probability) in enumerate(ranked, start=1)}


def _load_symbol_bars(
    path: Path | None,
    *,
    symbol: str,
) -> tuple[tuple[_AblationBar, ...], str | None]:
    if path is None:
        return (), "market data path is missing"
    if not path.exists():
        return (), f"market data path is missing: {path}"
    rows: list[_AblationBar] = []
    try:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for item in reader:
                if item.get("symbol") != symbol:
                    continue
                timestamp = _parse_utc_datetime(item.get("timestamp_utc"))
                open_price = _as_float(item.get("open"))
                high_price = _as_float(item.get("high"))
                low_price = _as_float(item.get("low"))
                close_price = _as_float(item.get("close"))
                volume = _as_float(item.get("volume"))
                if (
                    timestamp is None
                    or open_price is None
                    or high_price is None
                    or low_price is None
                    or close_price is None
                    or volume is None
                ):
                    continue
                rows.append(
                    _AblationBar(
                        timestamp=timestamp,
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=volume,
                    )
                )
    except OSError as exc:
        return (), f"market data path is unreadable: {exc}"
    rows.sort(key=lambda bar: bar.timestamp)
    if not rows:
        return (), f"market data has no rows for symbol {symbol}"
    return tuple(rows), None


def _build_group_dataset(
    group_id: str,
    rows: list[dict[str, Any]],
) -> FeatureInputGroupDataset:
    feature_names = _group_feature_names(group_id)
    feature_roles = _feature_roles(feature_names)
    missing = Counter()
    missing_row_indexes: dict[str, list[int]] = {name: [] for name in feature_names}
    features: list[tuple[float, ...]] = []
    for row_index, row in enumerate(rows):
        values: list[float] = []
        for name in feature_names:
            value = _feature_value(row, name)
            if value is None:
                missing[name] += 1
                missing_row_indexes[name].append(row_index)
                value = 0.0
            values.append(value)
        features.append(tuple(values))
    return FeatureInputGroupDataset(
        group_id=group_id,
        feature_names=feature_names,
        feature_roles=feature_roles,
        features=tuple(features),
        missing_value_counts=dict(missing),
        missing_value_row_indexes={
            name: tuple(indexes)
            for name, indexes in missing_row_indexes.items()
            if indexes
        },
    )


def _feature_group_payload(group: FeatureInputGroupDataset) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "feature_names": group.feature_names,
        "feature_roles": group.feature_roles,
        "example_count": len(group.features),
        "missing_value_counts": group.missing_value_counts,
    }


def _group_feature_names(group_id: str) -> tuple[str, ...]:
    if group_id == EXISTING_THRESHOLD_META_BASELINE_GROUP:
        return PROBABILITY_DERIVED_FEATURE_NAMES
    if group_id == RAW_PRE_ENTRY_GROUP:
        return RAW_PRE_ENTRY_FEATURE_NAMES
    if group_id == RAW_PRE_ENTRY_PLUS_PROBABILITY_META_GROUP:
        return (*RAW_PRE_ENTRY_FEATURE_NAMES, *PROBABILITY_DERIVED_FEATURE_NAMES)
    raise ValueError(f"unsupported feature input group: {group_id}")


def _feature_roles(feature_names: tuple[str, ...]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for name in feature_names:
        if name in RAW_PRE_ENTRY_FEATURE_NAMES:
            roles[name] = "raw_pre_entry_market_feature"
        elif name in PROBABILITY_DERIVED_FEATURE_NAMES:
            roles[name] = "probability_derived_meta_feature"
        else:
            roles[name] = "unknown"
    return roles


def _feature_value(row: dict[str, Any], name: str) -> float | None:
    if name == "probability_margin":
        return _as_float(row.get("probability_margin"))
    if name == "probability_rank_pct":
        return _as_float(row.get("probability_rank_pct"))
    pre_entry = row.get("pre_entry_3bar")
    if not isinstance(pre_entry, dict):
        return None
    key_by_name = {
        "pre_close_return": "close_return",
        "pre_high_low_range_pct": "range_pct_of_last_close",
        "pre_last_close_position_in_range": "last_close_position_in_range",
        "pre_last_volume_vs_prior_avg": "last_volume_vs_prior_avg",
    }
    return _as_float(pre_entry.get(key_by_name[name]))


def _label_from_row(row: dict[str, Any]) -> int | None:
    early = row.get("early_3bar")
    if not isinstance(early, dict):
        return None
    bucket = str(early.get("path_quality_bucket") or "")
    if bucket in ADVERSE_OR_NO_LIFT_BUCKETS:
        return 1
    if bucket in NON_ADVERSE_BUCKETS:
        return 0
    return None


def _label_counts(labels: tuple[int, ...]) -> dict[str, int]:
    counts = Counter(labels)
    return {
        "adverse_or_no_lift": counts[1],
        "non_adverse": counts[0],
    }


def _descriptive_evaluation_context(
    *,
    labels: Sequence[int],
    row_metadata: Sequence[dict[str, str]],
) -> dict[str, Any]:
    label_tuple = tuple(labels)
    row_count = len(label_tuple)
    source_counts = _metadata_counts(row_metadata, "source")
    slice_counts = _metadata_counts(row_metadata, "slice_id")
    variant_counts = _metadata_counts(row_metadata, "slice_variant_id")
    signal_context = _unique_signal_context(row_metadata)
    return {
        "row_count": row_count,
        "label_counts": _label_counts(label_tuple),
        "label_rates": _label_rates(label_tuple),
        "majority_label": _majority_label(label_tuple),
        "majority_accuracy": _format_metric_float(_majority_accuracy(label_tuple)),
        "adverse_or_no_lift_rate": _format_metric_float(_label_rate(label_tuple, 1)),
        "source_counts": source_counts,
        "diagnostic_overlay_rows_only": source_counts == {"diagnostic_overlay": row_count},
        "slice_counts": slice_counts,
        "variant_counts": variant_counts,
        "complete_signal_row_count": signal_context["complete_signal_row_count"],
        "missing_signal_key_row_count": signal_context["missing_signal_key_row_count"],
        "unique_signal_count": signal_context["unique_signal_count"],
        "duplicate_signal_count": signal_context["duplicate_signal_count"],
        "row_to_unique_signal_ratio": signal_context["row_to_unique_signal_ratio"],
        "max_variants_per_signal": signal_context["max_variants_per_signal"],
        "variant_count_histogram": signal_context["variant_count_histogram"],
    }


def _descriptive_evaluation_payload(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    feature_names: Sequence[str] | None = None,
    features: Sequence[Sequence[float]] | None = None,
    missing_value_row_indexes: dict[str, Sequence[int]] | None = None,
) -> dict[str, Any]:
    row_level_metrics = _binary_classification_metrics(labels, probabilities)
    unique_signal_metrics = _unique_signal_descriptive_evaluation(
        labels=labels,
        probabilities=probabilities,
        row_metadata=row_metadata,
        feature_names=feature_names,
        features=features,
        missing_value_row_indexes=missing_value_row_indexes,
        row_level_metrics=row_level_metrics,
    )
    return {
        "scope": {
            "in_sample": True,
            "descriptive_only": True,
            "held_out_split": False,
            "local_paper_replay_changed": False,
        },
        "context": _descriptive_evaluation_context(
            labels=labels,
            row_metadata=row_metadata,
        ),
        "overall": row_level_metrics,
        "unique_signal_descriptive_evaluation": unique_signal_metrics,
        "by_slice": _grouped_scored_metrics(
            labels=labels,
            probabilities=probabilities,
            row_metadata=row_metadata,
            metadata_key="slice_id",
        ),
        "by_variant": _grouped_scored_metrics(
            labels=labels,
            probabilities=probabilities,
            row_metadata=row_metadata,
            metadata_key="slice_variant_id",
        ),
    }


def _unique_signal_descriptive_evaluation(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    feature_names: Sequence[str] | None = None,
    features: Sequence[Sequence[float]] | None = None,
    missing_value_row_indexes: dict[str, Sequence[int]] | None = None,
    row_level_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(labels) != len(probabilities) or len(labels) != len(row_metadata):
        raise ValueError("labels, probabilities, and row_metadata must have the same length")

    collapse = _collapse_unique_signals(
        labels=labels,
        probabilities=probabilities,
        row_metadata=row_metadata,
    )
    unique_labels = tuple(record.label for record in collapse.records)
    unique_probabilities = tuple(record.probability for record in collapse.records)
    unique_metadata = tuple(record.metadata for record in collapse.records)
    overall = _binary_classification_metrics(unique_labels, unique_probabilities)
    payload = {
        "scope": {
            "in_sample": True,
            "descriptive_only": True,
            "held_out_split": False,
            "local_paper_replay_changed": False,
        },
        "aggregation_policy": {
            "signal_key_fields": UNIQUE_SIGNAL_KEY_FIELDS,
            "score": "mean_probability_across_threshold_variants",
            "label": "skip_mixed_label_signals",
            "missing_key": "skip_from_scored_unique_metrics",
            "variant_selection": "none",
        },
        "context": _unique_signal_scoring_context(
            labels=labels,
            row_metadata=row_metadata,
            grouped=collapse.grouped,
            missing_key_rows=collapse.missing_key_rows,
            mixed_label_signal_count=collapse.mixed_label_signal_count,
            mixed_label_row_count=collapse.mixed_label_row_count,
            scored_unique_signal_count=len(unique_labels),
            score_spans=collapse.score_spans,
        ),
        "overall": overall,
        "probability_band_diagnostics": _probability_band_diagnostics(
            labels=unique_labels,
            probabilities=unique_probabilities,
            row_metadata=unique_metadata,
        ),
        "by_slice": _grouped_scored_metrics(
            labels=unique_labels,
            probabilities=unique_probabilities,
            row_metadata=unique_metadata,
            metadata_key="slice_id",
        ),
        "delta_vs_row_level": _metric_delta_payload(
            row_level_metrics or _binary_classification_metrics(labels, probabilities),
            overall,
        ),
    }
    raw_attribution = _raw_pre_entry_band_attribution(
        records=collapse.records,
        row_metadata=row_metadata,
        feature_names=feature_names,
        features=features,
        missing_value_row_indexes=missing_value_row_indexes,
        missing_key_rows=collapse.missing_key_rows,
        mixed_label_signal_count=collapse.mixed_label_signal_count,
        mixed_label_row_count=collapse.mixed_label_row_count,
    )
    if raw_attribution is not None:
        payload["raw_pre_entry_band_attribution"] = raw_attribution
    return payload


def _collapse_unique_signals(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
) -> _UniqueSignalCollapse:
    grouped: dict[tuple[str, str, str, str], list[int]] = {}
    missing_key_rows = 0
    for index, metadata in enumerate(row_metadata):
        signal_key = _unique_signal_key(metadata)
        if signal_key is None:
            missing_key_rows += 1
            continue
        grouped.setdefault(signal_key, []).append(index)

    records: list[_UniqueSignalRecord] = []
    mixed_label_signal_count = 0
    mixed_label_row_count = 0
    score_spans: list[float] = []
    for signal_key, indexes in sorted(grouped.items()):
        signal_labels = {int(labels[index]) for index in indexes}
        signal_probabilities = [float(probabilities[index]) for index in indexes]
        score_spans.append(max(signal_probabilities) - min(signal_probabilities))
        if len(signal_labels) != 1:
            mixed_label_signal_count += 1
            mixed_label_row_count += len(indexes)
            continue
        records.append(
            _UniqueSignalRecord(
                signal_key=signal_key,
                label=next(iter(signal_labels)),
                probability=sum(signal_probabilities) / len(signal_probabilities),
                metadata={
                    "source": "diagnostic_overlay",
                    "slice_id": signal_key[0],
                    "symbol": signal_key[1],
                    "execution_bar_start": signal_key[2],
                    "offset": signal_key[3],
                },
                row_indexes=tuple(indexes),
            )
        )

    return _UniqueSignalCollapse(
        grouped=grouped,
        records=tuple(records),
        missing_key_rows=missing_key_rows,
        mixed_label_signal_count=mixed_label_signal_count,
        mixed_label_row_count=mixed_label_row_count,
        score_spans=tuple(score_spans),
    )


def _probability_band_diagnostics(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    band_count: int = 3,
) -> dict[str, Any]:
    if len(labels) != len(probabilities) or len(labels) != len(row_metadata):
        raise ValueError("labels, probabilities, and row_metadata must have the same length")
    if band_count != 3:
        raise ValueError("only rank tertile diagnostics are supported")

    label_tuple = tuple(int(label) for label in labels)
    probability_tuple = tuple(float(probability) for probability in probabilities)
    row_count = len(label_tuple)
    skip_reason, band_indexes = _probability_band_index_groups(
        probabilities=probability_tuple,
        row_metadata=row_metadata,
        band_count=band_count,
    )
    if skip_reason is not None:
        return {
            "scope": {
                "in_sample": True,
                "descriptive_only": True,
                "band_selection": "none",
            },
            "policy": _probability_band_policy(band_count),
            "context": {
                "scored_unique_signal_count": row_count,
                "band_count": band_count,
                "skip_reason": skip_reason,
            },
            "bands": {},
        }

    overall_adverse_rate = _label_rate(label_tuple, 1)
    return {
        "scope": {
            "in_sample": True,
            "descriptive_only": True,
            "band_selection": "none",
        },
        "policy": _probability_band_policy(band_count),
        "context": {
            "scored_unique_signal_count": row_count,
            "band_count": band_count,
            "skip_reason": None,
            "overall_adverse_or_no_lift_rate": _format_metric_float(overall_adverse_rate),
            **_probability_tie_context(probability_tuple),
        },
        "bands": {
            band_id: _probability_band_summary(
                labels=[label_tuple[index] for index in indexes],
                probabilities=[probability_tuple[index] for index in indexes],
                row_metadata=[row_metadata[index] for index in indexes],
                overall_adverse_rate=overall_adverse_rate,
            )
            for band_id, indexes in band_indexes.items()
        },
    }


def _probability_band_index_groups(
    *,
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    band_count: int = 3,
) -> tuple[str | None, dict[str, list[int]]]:
    if band_count != 3:
        raise ValueError("only rank tertile diagnostics are supported")
    probability_tuple = tuple(float(probability) for probability in probabilities)
    row_count = len(probability_tuple)
    if row_count == 0:
        return "no_scored_unique_signals", {}
    if row_count < band_count:
        return "insufficient_signals", {}
    if len(set(probability_tuple)) == 1:
        return "tied_probabilities", {}

    ordered_indexes = sorted(
        range(row_count),
        key=lambda index: (
            probability_tuple[index],
            _unique_signal_key(row_metadata[index]) or ("", "", "", ""),
        ),
    )
    band_indexes: dict[str, list[int]] = {band_id: [] for band_id in PROBABILITY_BAND_IDS}
    for rank, original_index in enumerate(ordered_indexes):
        band_id = PROBABILITY_BAND_IDS[min(band_count - 1, (rank * band_count) // row_count)]
        band_indexes[band_id].append(original_index)
    return None, band_indexes


def _probability_band_policy(band_count: int) -> dict[str, Any]:
    return {
        "family": "global_rank_tertile",
        "band_count": band_count,
        "assignment": "sort_by_probability_then_signal_key",
        "edges": "observed_rank_edges",
        "per_slice_edges": False,
        "threshold_search": False,
    }


def _probability_band_summary(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    overall_adverse_rate: float | None,
) -> dict[str, Any]:
    label_tuple = tuple(int(label) for label in labels)
    probability_tuple = tuple(float(probability) for probability in probabilities)
    band_adverse_rate = _label_rate(label_tuple, 1)
    return {
        "count": len(label_tuple),
        "label_counts": _label_counts(label_tuple),
        "adverse_or_no_lift_rate": _format_metric_float(band_adverse_rate),
        "lift_vs_overall_adverse_or_no_lift_rate": _format_metric_float(
            _safe_divide(band_adverse_rate, overall_adverse_rate)
            if band_adverse_rate is not None and overall_adverse_rate is not None
            else None
        ),
        "probability_min": _format_metric_float(
            min(probability_tuple) if probability_tuple else None
        ),
        "probability_max": _format_metric_float(
            max(probability_tuple) if probability_tuple else None
        ),
        "probability_mean": _format_metric_float(
            _safe_divide(sum(probability_tuple), len(probability_tuple))
        ),
        "by_slice": _probability_band_slice_summaries(
            labels=label_tuple,
            probabilities=probability_tuple,
            row_metadata=row_metadata,
            overall_adverse_rate=overall_adverse_rate,
        ),
    }


def _probability_band_slice_summaries(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    overall_adverse_rate: float | None,
) -> dict[str, Any]:
    grouped: dict[str, list[int]] = {}
    for index, metadata in enumerate(row_metadata):
        grouped.setdefault(metadata.get("slice_id") or "missing", []).append(index)
    return {
        slice_id: _probability_band_slice_summary(
            labels=[labels[index] for index in indexes],
            probabilities=[probabilities[index] for index in indexes],
            overall_adverse_rate=overall_adverse_rate,
        )
        for slice_id, indexes in sorted(grouped.items())
    }


def _probability_band_slice_summary(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    overall_adverse_rate: float | None,
) -> dict[str, Any]:
    label_tuple = tuple(int(label) for label in labels)
    probability_tuple = tuple(float(probability) for probability in probabilities)
    adverse_rate = _label_rate(label_tuple, 1)
    return {
        "count": len(label_tuple),
        "label_counts": _label_counts(label_tuple),
        "adverse_or_no_lift_rate": _format_metric_float(adverse_rate),
        "lift_vs_overall_adverse_or_no_lift_rate": _format_metric_float(
            _safe_divide(adverse_rate, overall_adverse_rate)
            if adverse_rate is not None and overall_adverse_rate is not None
            else None
        ),
        "probability_min": _format_metric_float(
            min(probability_tuple) if probability_tuple else None
        ),
        "probability_max": _format_metric_float(
            max(probability_tuple) if probability_tuple else None
        ),
    }


def _raw_pre_entry_band_attribution(
    *,
    records: Sequence[_UniqueSignalRecord],
    row_metadata: Sequence[dict[str, str]],
    feature_names: Sequence[str] | None,
    features: Sequence[Sequence[float]] | None,
    missing_value_row_indexes: dict[str, Sequence[int]] | None,
    missing_key_rows: int,
    mixed_label_signal_count: int,
    mixed_label_row_count: int,
    band_count: int = 3,
) -> dict[str, Any] | None:
    raw_feature_indexes = _raw_feature_indexes(feature_names)
    if not raw_feature_indexes:
        return None

    policy = _raw_pre_entry_band_attribution_policy(band_count)
    source_counts = _metadata_counts(row_metadata, "source")
    if features is None:
        return {
            "scope": _raw_pre_entry_band_attribution_scope(),
            "policy": policy,
            "context": {
                "raw_feature_names": tuple(raw_feature_indexes),
                "scored_unique_signal_count": len(records),
                "attributed_unique_signal_count": 0,
                "missing_signal_key_row_count": missing_key_rows,
                "skipped_mixed_label_signal_count": mixed_label_signal_count,
                "skipped_mixed_label_row_count": mixed_label_row_count,
                "duplicate_signal_count": _duplicate_record_count(records),
                "source_counts": source_counts,
                "diagnostic_overlay_rows_only": source_counts
                == {"diagnostic_overlay": len(row_metadata)},
                "band_count": band_count,
                "skip_reason": "raw_feature_values_unavailable",
                "raw_feature_duplicate_span_max": {},
            },
            "overall_raw_feature_summaries": {},
            "bands": {},
            "comparisons": {},
        }

    feature_rows = tuple(tuple(float(value) for value in row) for row in features)
    if len(feature_rows) != len(row_metadata):
        raise ValueError("features and row_metadata must have the same length")

    values_by_feature, duplicate_span_max = _raw_feature_values_by_record(
        records=records,
        raw_feature_indexes=raw_feature_indexes,
        features=feature_rows,
        missing_value_row_indexes=missing_value_row_indexes or {},
    )
    probabilities = tuple(record.probability for record in records)
    metadata = tuple(record.metadata for record in records)
    skip_reason, band_indexes = _probability_band_index_groups(
        probabilities=probabilities,
        row_metadata=metadata,
        band_count=band_count,
    )
    record_indexes = tuple(range(len(records)))
    overall_summaries = _raw_feature_summaries(
        record_indexes=record_indexes,
        values_by_feature=values_by_feature,
    )
    payload = {
        "scope": _raw_pre_entry_band_attribution_scope(),
        "policy": policy,
        "context": {
            "raw_feature_names": tuple(raw_feature_indexes),
            "scored_unique_signal_count": len(records),
            "attributed_unique_signal_count": _attributed_unique_signal_count(
                record_indexes=record_indexes,
                values_by_feature=values_by_feature,
            ),
            "missing_signal_key_row_count": missing_key_rows,
            "skipped_mixed_label_signal_count": mixed_label_signal_count,
            "skipped_mixed_label_row_count": mixed_label_row_count,
            "duplicate_signal_count": _duplicate_record_count(records),
            "source_counts": source_counts,
            "diagnostic_overlay_rows_only": source_counts
            == {"diagnostic_overlay": len(row_metadata)},
            "band_count": band_count,
            "skip_reason": skip_reason,
            "raw_feature_duplicate_span_max": duplicate_span_max,
        },
        "overall_raw_feature_summaries": overall_summaries,
        "bands": {},
        "comparisons": {},
    }
    if skip_reason is not None:
        return payload

    bands = {
        band_id: _raw_feature_band_summary(
            record_indexes=tuple(indexes),
            records=records,
            values_by_feature=values_by_feature,
        )
        for band_id, indexes in band_indexes.items()
    }
    high_band = bands["tertile_3_high_probability"]["raw_feature_summaries"]
    low_band = bands["tertile_1_low_probability"]["raw_feature_summaries"]
    payload["bands"] = bands
    payload["comparisons"] = {
        "tertile_3_high_probability_vs_overall": _raw_feature_comparison_payload(
            high_band,
            overall_summaries,
        ),
        "tertile_3_high_probability_vs_tertile_1_low_probability": (
            _raw_feature_comparison_payload(high_band, low_band)
        ),
    }
    return payload


def _raw_pre_entry_band_attribution_scope() -> dict[str, Any]:
    return {
        "in_sample": True,
        "descriptive_only": True,
        "band_selection": "none",
        "held_out_split": False,
        "local_paper_replay_changed": False,
    }


def _raw_pre_entry_band_attribution_policy(band_count: int) -> dict[str, Any]:
    return {
        "signal_key_fields": UNIQUE_SIGNAL_KEY_FIELDS,
        "score": "mean_probability_across_threshold_variants",
        "feature_value": "mean_raw_value_across_duplicate_rows",
        "label": "skip_mixed_label_signals",
        "missing_key": "skip_from_attribution",
        "band_family": "global_rank_tertile",
        "band_count": band_count,
        "assignment": "sort_by_probability_then_signal_key",
        "per_slice_edges": False,
        "threshold_search": False,
    }


def _raw_feature_indexes(feature_names: Sequence[str] | None) -> dict[str, int]:
    if feature_names is None:
        return {}
    indexes = {name: index for index, name in enumerate(feature_names)}
    return {
        name: indexes[name]
        for name in RAW_PRE_ENTRY_FEATURE_NAMES
        if name in indexes
    }


def _raw_feature_values_by_record(
    *,
    records: Sequence[_UniqueSignalRecord],
    raw_feature_indexes: dict[str, int],
    features: Sequence[Sequence[float]],
    missing_value_row_indexes: dict[str, Sequence[int]],
) -> tuple[dict[str, tuple[float | None, ...]], dict[str, str | None]]:
    values_by_feature: dict[str, tuple[float | None, ...]] = {}
    duplicate_span_max: dict[str, str | None] = {}
    missing_sets = {
        name: {int(index) for index in indexes}
        for name, indexes in missing_value_row_indexes.items()
    }
    for feature_name, feature_index in raw_feature_indexes.items():
        record_values: list[float | None] = []
        spans: list[float] = []
        missing_rows = missing_sets.get(feature_name, set())
        for record in records:
            values: list[float] = []
            for row_index in record.row_indexes:
                if row_index in missing_rows:
                    continue
                if row_index >= len(features) or feature_index >= len(features[row_index]):
                    continue
                value = float(features[row_index][feature_index])
                if math.isfinite(value):
                    values.append(value)
            if not values:
                record_values.append(None)
                continue
            spans.append(max(values) - min(values))
            record_values.append(sum(values) / len(values))
        values_by_feature[feature_name] = tuple(record_values)
        duplicate_span_max[feature_name] = _format_metric_float(max(spans) if spans else None)
    return values_by_feature, duplicate_span_max


def _raw_feature_band_summary(
    *,
    record_indexes: Sequence[int],
    records: Sequence[_UniqueSignalRecord],
    values_by_feature: dict[str, tuple[float | None, ...]],
) -> dict[str, Any]:
    index_tuple = tuple(record_indexes)
    return {
        "count": len(index_tuple),
        "raw_feature_summaries": _raw_feature_summaries(
            record_indexes=index_tuple,
            values_by_feature=values_by_feature,
        ),
        "by_slice": _raw_feature_band_slice_summaries(
            record_indexes=index_tuple,
            records=records,
            values_by_feature=values_by_feature,
        ),
    }


def _raw_feature_band_slice_summaries(
    *,
    record_indexes: Sequence[int],
    records: Sequence[_UniqueSignalRecord],
    values_by_feature: dict[str, tuple[float | None, ...]],
) -> dict[str, Any]:
    grouped: dict[str, list[int]] = {}
    for record_index in record_indexes:
        slice_id = records[record_index].metadata.get("slice_id") or "missing"
        grouped.setdefault(slice_id, []).append(record_index)
    return {
        slice_id: {
            "count": len(indexes),
            "raw_feature_summaries": _raw_feature_summaries(
                record_indexes=tuple(indexes),
                values_by_feature=values_by_feature,
            ),
        }
        for slice_id, indexes in sorted(grouped.items())
    }


def _raw_feature_summaries(
    *,
    record_indexes: Sequence[int],
    values_by_feature: dict[str, tuple[float | None, ...]],
) -> dict[str, Any]:
    return {
        feature_name: _raw_feature_summary(
            values=[values[index] for index in record_indexes],
        )
        for feature_name, values in values_by_feature.items()
    }


def _raw_feature_summary(*, values: Sequence[float | None]) -> dict[str, Any]:
    value_tuple = tuple(values)
    finite_values = sorted(
        float(value)
        for value in value_tuple
        if value is not None and math.isfinite(float(value))
    )
    return {
        "signal_count": len(value_tuple),
        "value_count": len(finite_values),
        "missing_value_count": len(value_tuple) - len(finite_values),
        "mean": _format_metric_float(_safe_divide(sum(finite_values), len(finite_values))),
        "median": _format_metric_float(_median(finite_values)),
        "min": _format_metric_float(min(finite_values) if finite_values else None),
        "max": _format_metric_float(max(finite_values) if finite_values else None),
    }


def _raw_feature_comparison_payload(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    feature_names = sorted(set(left).union(right))
    return {
        feature_name: _raw_feature_summary_delta(
            left.get(feature_name, {}),
            right.get(feature_name, {}),
        )
        for feature_name in feature_names
    }


def _raw_feature_summary_delta(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, str | None]:
    left_mean = _metric_value(left.get("mean"))
    right_mean = _metric_value(right.get("mean"))
    left_median = _metric_value(left.get("median"))
    right_median = _metric_value(right.get("median"))
    return {
        "mean_delta": _format_metric_float(
            left_mean - right_mean
            if left_mean is not None and right_mean is not None
            else None
        ),
        "median_delta": _format_metric_float(
            left_median - right_median
            if left_median is not None and right_median is not None
            else None
        ),
    }


def _attributed_unique_signal_count(
    *,
    record_indexes: Sequence[int],
    values_by_feature: dict[str, tuple[float | None, ...]],
) -> int:
    return sum(
        1
        for record_index in record_indexes
        if any(values[record_index] is not None for values in values_by_feature.values())
    )


def _duplicate_record_count(records: Sequence[_UniqueSignalRecord]) -> int:
    return sum(1 for record in records if len(record.row_indexes) > 1)


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    midpoint = len(values) // 2
    if len(values) % 2:
        return float(values[midpoint])
    return (float(values[midpoint - 1]) + float(values[midpoint])) / 2


def _binary_classification_metrics(
    labels: Sequence[int],
    probabilities: Sequence[float],
) -> dict[str, Any]:
    label_tuple = tuple(int(label) for label in labels)
    probability_tuple = tuple(float(probability) for probability in probabilities)
    if len(label_tuple) != len(probability_tuple):
        raise ValueError("labels and probabilities must have the same length")
    row_count = len(label_tuple)
    label_counts = _label_counts(label_tuple)
    predictions = tuple(1 if probability >= 0.5 else 0 for probability in probability_tuple)
    labeled_predictions = tuple(zip(label_tuple, predictions, strict=True))
    true_positive = sum(
        1 for label, prediction in labeled_predictions if label == 1 and prediction == 1
    )
    true_negative = sum(
        1 for label, prediction in labeled_predictions if label == 0 and prediction == 0
    )
    false_positive = sum(
        1 for label, prediction in labeled_predictions if label == 0 and prediction == 1
    )
    false_negative = sum(
        1 for label, prediction in labeled_predictions if label == 1 and prediction == 0
    )
    positive_count = true_positive + false_negative
    negative_count = true_negative + false_positive
    positive_recall = _safe_divide(true_positive, positive_count)
    negative_recall = _safe_divide(true_negative, negative_count)
    balanced_accuracy = None
    skip_reasons: list[str] = []
    if positive_recall is None or negative_recall is None:
        skip_reasons.append("single_class")
    else:
        balanced_accuracy = (positive_recall + negative_recall) / 2

    auc_payload = _auc_rank_average(label_tuple, probability_tuple)
    if auc_payload.get("auc") is None and auc_payload.get("skip_reason"):
        skip_reasons.append(str(auc_payload["skip_reason"]))

    return {
        "row_count": row_count,
        "label_counts": label_counts,
        "label_rates": _label_rates(label_tuple),
        "majority_label": _majority_label(label_tuple),
        "majority_accuracy": _format_metric_float(_majority_accuracy(label_tuple)),
        "accuracy": _format_metric_float(_safe_divide(true_positive + true_negative, row_count)),
        "balanced_accuracy": _format_metric_float(balanced_accuracy),
        "positive_recall": _format_metric_float(positive_recall),
        "negative_recall": _format_metric_float(negative_recall),
        "predicted_positive_rate": _format_metric_float(
            _safe_divide(sum(predictions), row_count)
        ),
        "mean_probability": _format_metric_float(
            _safe_divide(sum(probability_tuple), row_count)
        ),
        "log_loss": _format_metric_float(_binary_log_loss(label_tuple, probability_tuple)),
        "confusion": {
            "true_positive": true_positive,
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "auc": auc_payload.get("auc"),
        "auc_tie_handling": auc_payload.get("tie_handling"),
        "auc_tie_group_count": auc_payload.get("tie_group_count"),
        "auc_tied_score_count": auc_payload.get("tied_score_count"),
        "skip_reason": ",".join(dict.fromkeys(skip_reasons)) or None,
    }


def _grouped_scored_metrics(
    *,
    labels: Sequence[int],
    probabilities: Sequence[float],
    row_metadata: Sequence[dict[str, str]],
    metadata_key: str,
) -> dict[str, Any]:
    if len(labels) != len(probabilities) or len(labels) != len(row_metadata):
        raise ValueError("labels, probabilities, and row_metadata must have the same length")
    grouped: dict[str, list[int]] = {}
    for index, metadata in enumerate(row_metadata):
        group_id = metadata.get(metadata_key) or "missing"
        grouped.setdefault(group_id, []).append(index)
    return {
        group_id: _binary_classification_metrics(
            [labels[index] for index in indexes],
            [probabilities[index] for index in indexes],
        )
        for group_id, indexes in sorted(grouped.items())
    }


def _auc_rank_average(
    labels: Sequence[int],
    probabilities: Sequence[float],
) -> dict[str, Any]:
    label_tuple = tuple(int(label) for label in labels)
    probability_tuple = tuple(float(probability) for probability in probabilities)
    if len(label_tuple) != len(probability_tuple):
        raise ValueError("labels and probabilities must have the same length")
    positive_count = sum(1 for label in label_tuple if label == 1)
    negative_count = sum(1 for label in label_tuple if label == 0)
    if positive_count == 0 or negative_count == 0:
        return {
            "auc": None,
            "skip_reason": "single_class",
            "tie_handling": "average_rank",
            "tie_group_count": 0,
            "tied_score_count": 0,
        }

    ranked = sorted(enumerate(probability_tuple), key=lambda item: item[1])
    ranks = [0.0] * len(ranked)
    tie_group_count = 0
    tied_score_count = 0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][1] == ranked[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        if end - index > 1:
            tie_group_count += 1
            tied_score_count += end - index
        for rank_index in range(index, end):
            original_index = ranked[rank_index][0]
            ranks[original_index] = average_rank
        index = end

    positive_rank_sum = sum(
        rank for rank, label in zip(ranks, label_tuple, strict=True) if label == 1
    )
    auc = (
        positive_rank_sum - (positive_count * (positive_count + 1) / 2)
    ) / (positive_count * negative_count)
    return {
        "auc": _format_metric_float(auc),
        "skip_reason": None,
        "tie_handling": "average_rank",
        "tie_group_count": tie_group_count,
        "tied_score_count": tied_score_count,
    }


def _binary_log_loss(
    labels: Sequence[int],
    probabilities: Sequence[float],
) -> float | None:
    if not labels:
        return None
    epsilon = 1e-7
    total = 0.0
    for label, probability in zip(labels, probabilities, strict=True):
        clipped = min(max(float(probability), epsilon), 1.0 - epsilon)
        total += -(
            int(label) * math.log(clipped)
            + (1 - int(label)) * math.log(1.0 - clipped)
        )
    return total / len(labels)


def _label_rates(labels: tuple[int, ...]) -> dict[str, str | None]:
    return {
        "adverse_or_no_lift": _format_metric_float(_label_rate(labels, 1)),
        "non_adverse": _format_metric_float(_label_rate(labels, 0)),
    }


def _label_rate(labels: tuple[int, ...], label: int) -> float | None:
    return _safe_divide(sum(1 for value in labels if value == label), len(labels))


def _majority_label(labels: tuple[int, ...]) -> str | None:
    if not labels:
        return None
    counts = Counter(labels)
    if counts[1] == counts[0]:
        return "tie"
    return "adverse_or_no_lift" if counts[1] > counts[0] else "non_adverse"


def _majority_accuracy(labels: tuple[int, ...]) -> float | None:
    if not labels:
        return None
    counts = Counter(labels)
    return max(counts[1], counts[0]) / len(labels)


def _metadata_counts(
    row_metadata: Sequence[dict[str, str]],
    key: str,
) -> dict[str, int]:
    counts = Counter(metadata.get(key) or "missing" for metadata in row_metadata)
    return dict(sorted(counts.items()))


def _unique_signal_context(row_metadata: Sequence[dict[str, str]]) -> dict[str, Any]:
    variants_by_signal: dict[tuple[str, str, str, str], set[str]] = {}
    missing_key_rows = 0
    for metadata in row_metadata:
        signal_key = _unique_signal_key(metadata)
        if signal_key is None:
            missing_key_rows += 1
            continue
        variants_by_signal.setdefault(signal_key, set()).add(
            metadata.get("variant_id") or "missing"
        )
    unique_signal_count = len(variants_by_signal)
    max_variants = max((len(variants) for variants in variants_by_signal.values()), default=0)
    complete_signal_row_count = len(row_metadata) - missing_key_rows
    return {
        "complete_signal_row_count": complete_signal_row_count,
        "missing_signal_key_row_count": missing_key_rows,
        "unique_signal_count": unique_signal_count,
        "duplicate_signal_count": sum(
            1 for variants in variants_by_signal.values() if len(variants) > 1
        ),
        "row_to_unique_signal_ratio": _format_metric_float(
            _safe_divide(complete_signal_row_count, unique_signal_count)
        ),
        "max_variants_per_signal": max_variants,
        "variant_count_histogram": _variant_count_histogram(variants_by_signal),
    }


def _unique_signal_scoring_context(
    *,
    labels: Sequence[int],
    row_metadata: Sequence[dict[str, str]],
    grouped: dict[tuple[str, str, str, str], list[int]],
    missing_key_rows: int,
    mixed_label_signal_count: int,
    mixed_label_row_count: int,
    scored_unique_signal_count: int,
    score_spans: Sequence[float],
) -> dict[str, Any]:
    signal_context = _unique_signal_context(row_metadata)
    complete_signal_row_count = len(row_metadata) - missing_key_rows
    return {
        "row_count": len(labels),
        "complete_signal_row_count": complete_signal_row_count,
        "missing_signal_key_row_count": missing_key_rows,
        "unique_signal_count": len(grouped),
        "scored_unique_signal_count": scored_unique_signal_count,
        "skipped_mixed_label_signal_count": mixed_label_signal_count,
        "skipped_mixed_label_row_count": mixed_label_row_count,
        "duplicate_signal_count": signal_context["duplicate_signal_count"],
        "row_to_unique_signal_ratio": signal_context["row_to_unique_signal_ratio"],
        "max_variants_per_signal": signal_context["max_variants_per_signal"],
        "variant_count_histogram": signal_context["variant_count_histogram"],
        "source_counts": _metadata_counts(row_metadata, "source"),
        "diagnostic_overlay_rows_only": _metadata_counts(row_metadata, "source")
        == {"diagnostic_overlay": len(row_metadata)},
        "row_label_counts": _label_counts(tuple(int(label) for label in labels)),
        "unique_label_counts": _label_counts(tuple(int(label) for label in _labels_by_group(
            labels=labels,
            grouped=grouped,
        ))),
        "score_span_max": _format_metric_float(max(score_spans) if score_spans else None),
        "score_span_mean": _format_metric_float(
            _safe_divide(sum(score_spans), len(score_spans))
        ),
    }


def _labels_by_group(
    *,
    labels: Sequence[int],
    grouped: dict[tuple[str, str, str, str], list[int]],
) -> tuple[int, ...]:
    collapsed: list[int] = []
    for indexes in grouped.values():
        signal_labels = {int(labels[index]) for index in indexes}
        if len(signal_labels) == 1:
            collapsed.append(next(iter(signal_labels)))
    return tuple(collapsed)


def _unique_signal_key(metadata: dict[str, str]) -> tuple[str, str, str, str] | None:
    parts = tuple(str(metadata.get(field) or "") for field in UNIQUE_SIGNAL_KEY_FIELDS)
    if any(part in {"", "missing"} for part in parts):
        return None
    return parts


def _variant_count_histogram(
    variants_by_signal: dict[tuple[str, str, str, str], set[str]],
) -> dict[str, int]:
    histogram = Counter(len(variants) for variants in variants_by_signal.values())
    return {str(count): frequency for count, frequency in sorted(histogram.items())}


def _metric_delta_payload(
    row_level_metrics: dict[str, Any],
    unique_metrics: dict[str, Any],
) -> dict[str, str | None]:
    keys = ("accuracy", "balanced_accuracy", "auc", "log_loss")
    return {
        f"unique_minus_row_{key}": _format_metric_float(
            _metric_value(unique_metrics.get(key)) - _metric_value(row_level_metrics.get(key))
            if _metric_value(unique_metrics.get(key)) is not None
            and _metric_value(row_level_metrics.get(key)) is not None
            else None
        )
        for key in keys
    }


def _metric_value(value: Any) -> float | None:
    return _as_float(value)


def _probability_tie_context(probabilities: Sequence[float]) -> dict[str, int]:
    counts = Counter(probabilities)
    tied_groups = [count for count in counts.values() if count > 1]
    return {
        "tie_group_count": len(tied_groups),
        "tied_score_count": sum(tied_groups),
    }


def _safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _format_metric_float(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    return f"{value:.6f}"


def _source_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("source_evidence")
    if not isinstance(evidence, dict):
        return {
            "all_reference_fills_local_paper": None,
            "local_paper_reference_fill_count": 0,
            "diagnostic_overlay_source_counts": {},
            "diagnostic_rows_are_not_local_paper_fills": True,
        }
    return {
        "all_reference_fills_local_paper": evidence.get("all_reference_fills_local_paper"),
        "local_paper_reference_fill_count": evidence.get("local_paper_reference_fill_count", 0),
        "diagnostic_overlay_source_counts": evidence.get("diagnostic_overlay_source_counts", {}),
        "diagnostic_rows_are_not_local_paper_fills": evidence.get(
            "diagnostic_rows_are_not_local_paper_fills",
            True,
        ),
        "prior_reference_local_paper_fill_count": evidence.get(
            "prior_reference_local_paper_fill_count"
        ),
        "prior_reference_diagnostic_overlay_source_counts": evidence.get(
            "prior_reference_diagnostic_overlay_source_counts"
        ),
    }


def _read_stability_payload(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_object(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, "artifact path is missing"
    if not path.exists():
        return {}, f"artifact path is missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"artifact path is unreadable: {exc}"
    if not isinstance(payload, dict):
        return {}, "artifact must contain a JSON object"
    return payload, None


def _resolve_lineage_path(value: Any, *, artifact_root: Path) -> Path | None:
    if value is None or value == "":
        return None
    raw = str(value)
    normalized = raw.replace("\\", "/")
    if normalized == str(APP_MODEL_ARTIFACT_ROOT):
        return artifact_root
    if normalized.startswith(f"{APP_MODEL_ARTIFACT_ROOT}/"):
        relative = PurePosixPath(normalized).relative_to(APP_MODEL_ARTIFACT_ROOT)
        safe_parts = _safe_relative_parts(relative)
        return None if safe_parts is None else artifact_root.joinpath(*safe_parts)
    if normalized == str(APP_MARKET_DATA_ROOT):
        return _app_market_data_host_path(PurePosixPath("."))
    if normalized.startswith(f"{APP_MARKET_DATA_ROOT}/"):
        relative = PurePosixPath(normalized).relative_to(APP_MARKET_DATA_ROOT)
        safe_parts = _safe_relative_parts(relative)
        if safe_parts is None:
            return None
        return _app_market_data_host_path(PurePosixPath(*safe_parts))

    host_model_root = str(DEFAULT_HOST_MODEL_ARTIFACT_ROOT).replace("\\", "/")
    if _starts_with_path(normalized, host_model_root):
        relative = normalized[len(host_model_root) :].lstrip("/")
        safe_parts = _safe_relative_parts(PurePosixPath(relative)) if relative else ()
        return None if safe_parts is None else artifact_root.joinpath(*safe_parts)

    host_market_root = str(DEFAULT_HOST_MARKET_DATA_ROOT).replace("\\", "/")
    if _starts_with_path(normalized, host_market_root):
        relative = normalized[len(host_market_root) :].lstrip("/")
        safe_parts = _safe_relative_parts(PurePosixPath(relative)) if relative else ()
        if safe_parts is None:
            return None
        docker_market = Path(str(APP_MARKET_DATA_ROOT))
        if docker_market.exists():
            return docker_market.joinpath(*safe_parts)
        return DEFAULT_HOST_MARKET_DATA_ROOT.joinpath(*safe_parts)
    return None


def _safe_relative_parts(relative: PurePosixPath) -> tuple[str, ...] | None:
    parts = relative.parts
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return parts


def _app_market_data_host_path(relative: PurePosixPath) -> Path:
    docker_market = Path(str(APP_MARKET_DATA_ROOT))
    if docker_market.exists():
        return docker_market.joinpath(*relative.parts)
    return DEFAULT_HOST_MARKET_DATA_ROOT.joinpath(*relative.parts)


def _starts_with_path(value: str, root: str) -> bool:
    lower_value = value.lower()
    lower_root = root.lower()
    return lower_value == lower_root or lower_value.startswith(f"{lower_root}/")


def _available_backends() -> tuple[str, ...]:
    return tuple(
        backend
        for backend in OPTIONAL_FEATURE_INPUT_ABLATION_BACKENDS
        if importlib.util.find_spec(backend) is not None
    )


def _selected_backend() -> str | None:
    if importlib.util.find_spec("torch") is not None:
        return "torch"
    return None


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_float(value: float | None) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    return f"{value:.12f}"


def _group_results_by_id(runner_metrics: dict[str, Any]) -> dict[str, Any]:
    groups = runner_metrics.get("groups")
    if not isinstance(groups, list):
        return {}
    return {
        str(item.get("group_id")): item
        for item in groups
        if isinstance(item, dict) and item.get("group_id")
    }


def _validate_positive_cap(value: int, *, field_name: str, ceiling: int) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    if value > ceiling:
        raise ValueError(f"{field_name} must be <= {ceiling}")

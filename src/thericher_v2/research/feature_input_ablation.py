"""Bounded feature-input ablation over diagnostic candidate-entry rows."""

from __future__ import annotations

import importlib.util
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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


@dataclass(frozen=True)
class FeatureInputAblationConfig:
    run_id: str = DEFAULT_FEATURE_INPUT_ABLATION_RUN_ID
    max_epochs: int = 8
    max_steps: int = 256
    min_examples: int = 8
    hidden_units: int = DEFAULT_FEATURE_INPUT_ABLATION_HIDDEN_UNITS
    feature_groups: tuple[str, ...] = SUPPORTED_FEATURE_INPUT_GROUPS
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


@dataclass(frozen=True)
class FeatureInputGroupDataset:
    group_id: str
    feature_names: tuple[str, ...]
    feature_roles: dict[str, str]
    features: tuple[tuple[float, ...], ...]
    missing_value_counts: dict[str, int]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class FeatureInputAblationDataset:
    labels: tuple[int, ...]
    label_names: dict[int, str]
    rows_seen: int
    rows_used: int
    rows_dropped: int
    source_slices: tuple[str, ...]
    feature_groups: tuple[FeatureInputGroupDataset, ...]
    schema_version: int = SCHEMA_VERSION


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
    dataset = _build_dataset(payload, config=config)
    source_evidence = _source_evidence(payload)
    reason_parts: list[str] = []
    metrics: dict[str, Any] = {
        "feature_group_count": len(dataset.feature_groups),
        "feature_groups": [_feature_group_payload(group) for group in dataset.feature_groups],
        "label_counts": _label_counts(dataset.labels),
        "source_slices": dataset.source_slices,
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
            f"only {dataset.rows_used} labeled selected rows available; "
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
) -> FeatureInputAblationDataset:
    rows = payload.get("selected_candidate_entry_rows")
    raw_rows = rows if isinstance(rows, list) else []
    labels: list[int] = []
    kept_rows: list[dict[str, Any]] = []
    source_slices: list[str] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        if row.get("source") != "diagnostic_overlay":
            continue
        label = _label_from_row(row)
        if label is None:
            continue
        labels.append(label)
        kept_rows.append(row)
        slice_id = str(row.get("slice_id") or "")
        if slice_id and slice_id not in source_slices:
            source_slices.append(slice_id)

    groups = tuple(_build_group_dataset(group_id, kept_rows) for group_id in config.feature_groups)
    return FeatureInputAblationDataset(
        labels=tuple(labels),
        label_names={1: "adverse_or_no_lift", 0: "non_adverse"},
        rows_seen=len(raw_rows),
        rows_used=len(kept_rows),
        rows_dropped=len(raw_rows) - len(kept_rows),
        source_slices=tuple(source_slices),
        feature_groups=groups,
    )


def _build_group_dataset(
    group_id: str,
    rows: list[dict[str, Any]],
) -> FeatureInputGroupDataset:
    feature_names = _group_feature_names(group_id)
    feature_roles = _feature_roles(feature_names)
    missing = Counter()
    features: list[tuple[float, ...]] = []
    for row in rows:
        values: list[float] = []
        for name in feature_names:
            value = _feature_value(row, name)
            if value is None:
                missing[name] += 1
                value = 0.0
            values.append(value)
        features.append(tuple(values))
    return FeatureInputGroupDataset(
        group_id=group_id,
        feature_names=feature_names,
        feature_roles=feature_roles,
        features=tuple(features),
        missing_value_counts=dict(missing),
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

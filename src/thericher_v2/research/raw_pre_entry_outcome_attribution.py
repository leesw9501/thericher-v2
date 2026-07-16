"""Local-paper outcome attribution for raw pre-entry diagnostic context."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.serialization import to_jsonable

from .feature_input_ablation import (
    DEFAULT_HOST_MODEL_ARTIFACT_ROOT,
    RAW_PRE_ENTRY_FEATURE_NAMES,
    FeatureInputAblationConfig,
    _candidate_entry_rows,
    _feature_value,
    _resolve_lineage_path,
)
from .trade_path_attribution import (
    TradePathEventArtifact,
    _read_fill_events,
    attribute_trade_paths_from_local_paper_events,
)
from .validation import _reject_repo_artifact_path, load_yahoo_intraday_1m_bars

RawPreEntryOutcomeAttributionStatus = Literal[
    "raw_pre_entry_outcome_attributed_only",
    "prepared_not_raw_pre_entry_outcome_attributed",
]

DEFAULT_RAW_PRE_ENTRY_OUTCOME_ATTRIBUTION_RUN_ID = (
    "bounded-raw-pre-entry-outcome-attribution"
)
DIAGNOSTIC_OVERLAY_SOURCE = "diagnostic_overlay"
RAW_FEATURE_TERTILE_IDS = (
    "tertile_1_low_value",
    "tertile_2_mid_value",
    "tertile_3_high_value",
)
RAW_SIGNAL_KEY_FIELDS = ("slice_id", "symbol", "execution_bar_start", "offset")


@dataclass(frozen=True)
class RawPreEntryOutcomeAttributionConfig:
    run_id: str = DEFAULT_RAW_PRE_ENTRY_OUTCOME_ATTRIBUTION_RUN_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")


@dataclass(frozen=True)
class RawPreEntryOutcomeAttributionResult:
    run_id: str
    status: RawPreEntryOutcomeAttributionStatus
    checked_at: datetime
    reason: str
    source_stability_artifact: Path | None
    source_raw_band_artifact: Path | None
    rows_seen: int
    rows_used: int
    metrics: dict[str, Any]
    attribution_artifact: Path
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", self.checked_at.astimezone(UTC))


@dataclass(frozen=True)
class _DiagnosticObservation:
    index: int
    signal_key: tuple[str, str, str, str]
    observation_key: tuple[str, str, str, str]
    entry_key: tuple[str, str, str, str]
    source: str
    slice_id: str
    variant_id: str
    symbol: str
    execution_time_utc: str
    pre_entry_bucket: str
    raw_features: dict[str, float | None]
    entered_local_paper_reference: bool


def run_bounded_raw_pre_entry_outcome_attribution(
    *,
    artifact_root: Path = DEFAULT_HOST_MODEL_ARTIFACT_ROOT,
    repo_root: Path | None = None,
    stability_artifact: Path | None,
    raw_band_artifact: Path | None = None,
    config: RawPreEntryOutcomeAttributionConfig | None = None,
    checked_at: datetime | None = None,
) -> RawPreEntryOutcomeAttributionResult:
    """Write one compact external attribution artifact from existing evidence."""

    config = config or RawPreEntryOutcomeAttributionConfig()
    checked_at = (checked_at or datetime.now(UTC)).astimezone(UTC)
    _reject_repo_artifact_path(artifact_root, repo_root)
    output_dir = artifact_root / "raw-pre-entry-outcome-attribution" / config.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    attribution_artifact = output_dir / "metrics.json"

    stability_payload, stability_error = _read_json_object(stability_artifact)
    raw_band_payload, raw_band_error = _read_json_object(raw_band_artifact)
    reason_parts: list[str] = []
    if stability_error is not None:
        reason_parts.append(stability_error)
    if raw_band_error is not None:
        reason_parts.append(raw_band_error)

    diagnostic_rows: list[dict[str, Any]] = []
    reconstruction: dict[str, Any] = {}
    bars: tuple[Bar, ...] = ()
    event_artifacts: tuple[TradePathEventArtifact, ...] = ()
    fill_events: tuple[dict[str, Any], ...] = ()
    trade_payload: dict[str, Any] = {
        "local_paper_verification": {},
        "closed_segments": (),
        "open_segments": (),
    }
    inventory: dict[str, Any] = {}

    if not reason_parts:
        diagnostic_rows, reconstruction = _candidate_entry_rows(
            stability_payload,
            config=FeatureInputAblationConfig(row_mode="all_diagnostic"),
            artifact_root=artifact_root,
        )
        event_artifacts = _event_artifacts_from_stability(
            stability_payload,
            artifact_root=artifact_root,
        )
        fill_events = _fill_events_from_event_artifacts(event_artifacts)
        bars, bar_errors = _bars_from_stability(
            stability_payload,
            artifact_root=artifact_root,
        )
        inventory = {
            "event_artifact_count": len(event_artifacts),
            "fill_event_count": len(fill_events),
            "bar_count": len(bars),
            "bar_error_count": len(bar_errors),
            "bar_errors": bar_errors[:10],
        }
        if not event_artifacts:
            reason_parts.append("stability artifact has no event artifacts")
        else:
            trade_result = attribute_trade_paths_from_local_paper_events(
                event_artifacts=event_artifacts,
                bars=bars,
                checked_at=checked_at,
            )
            trade_payload = trade_result.to_payload()

    metrics = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=diagnostic_rows,
        local_paper_closed_segments=tuple(trade_payload.get("closed_segments") or ()),
        local_paper_open_segments=tuple(trade_payload.get("open_segments") or ()),
        local_paper_fill_events=fill_events,
        local_paper_verification=dict(trade_payload.get("local_paper_verification") or {}),
    )
    metrics["row_reconstruction"] = reconstruction
    metrics["evidence_inventory"] = inventory
    metrics["source_raw_band_context"] = _raw_band_context(raw_band_payload)

    status: RawPreEntryOutcomeAttributionStatus
    if reason_parts:
        status = "prepared_not_raw_pre_entry_outcome_attributed"
    else:
        status = "raw_pre_entry_outcome_attributed_only"
        reason_parts.append("bounded raw pre-entry outcome attribution completed")

    result = RawPreEntryOutcomeAttributionResult(
        run_id=config.run_id,
        status=status,
        checked_at=checked_at,
        reason="; ".join(reason_parts),
        source_stability_artifact=stability_artifact,
        source_raw_band_artifact=raw_band_artifact,
        rows_seen=len(diagnostic_rows),
        rows_used=metrics["overall"]["diagnostic_observation_count"],
        metrics=metrics,
        attribution_artifact=attribution_artifact,
        schema_version=config.schema_version,
    )
    attribution_artifact.write_text(
        json.dumps(_result_payload(result, artifact_root), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return result


def attribute_local_paper_outcomes_by_raw_pre_entry_context(
    *,
    diagnostic_rows: Sequence[Mapping[str, Any]],
    local_paper_closed_segments: Sequence[Mapping[str, Any]],
    local_paper_open_segments: Sequence[Mapping[str, Any]],
    local_paper_fill_events: Sequence[Mapping[str, Any]],
    local_paper_verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize existing local-paper outcomes by raw diagnostic context."""

    observations = _diagnostic_observations(diagnostic_rows)
    closed_by_entry = _segments_by_entry_key(local_paper_closed_segments)
    open_by_entry = _segments_by_entry_key(local_paper_open_segments)
    fill_events_by_entry, non_local_events_by_entry = _fill_events_by_entry_key(
        local_paper_fill_events
    )
    all_indexes = tuple(range(len(observations)))
    return {
        "scope": {
            "in_sample": True,
            "descriptive_only": True,
            "local_paper_replay_changed": False,
            "broker_used": False,
            "kis_api_called": False,
            "credentials_read": False,
            "threshold_search": False,
            "feature_rule": False,
        },
        "policy": {
            "diagnostic_source": DIAGNOSTIC_OVERLAY_SOURCE,
            "local_paper_source": LOCAL_PAPER_SOURCE,
            "raw_signal_key_fields": RAW_SIGNAL_KEY_FIELDS,
            "observation_key": (
                "slice_id",
                "variant_id",
                "symbol",
                "execution_bar_start_utc",
            ),
            "entry_join": "exact_slice_variant_symbol_entry_timestamp_utc",
            "raw_feature_grouping": "global_rank_tertile_by_observed_raw_value",
            "tie_breaker": "raw_value_then_observation_key",
            "missing_raw_value": "excluded_from_feature_tertile",
            "missing_outcome_evidence": "count_only",
        },
        "context": {
            "raw_feature_names": RAW_PRE_ENTRY_FEATURE_NAMES,
            "diagnostic_source_counts": _source_counts(observations),
            "local_paper_source_counts": _source_counts_from_payloads(
                local_paper_fill_events
            ),
            "local_paper_verification": dict(local_paper_verification),
            "non_local_fill_source_count": _non_local_fill_source_count(
                local_paper_verification
            ),
        },
        "overall": _outcome_summary(
            observation_indexes=all_indexes,
            observations=observations,
            closed_by_entry=closed_by_entry,
            open_by_entry=open_by_entry,
            fill_events_by_entry=fill_events_by_entry,
            non_local_events_by_entry=non_local_events_by_entry,
        ),
        "by_pre_entry_bucket": _by_pre_entry_bucket(
            observations=observations,
            closed_by_entry=closed_by_entry,
            open_by_entry=open_by_entry,
            fill_events_by_entry=fill_events_by_entry,
            non_local_events_by_entry=non_local_events_by_entry,
        ),
        "by_raw_feature_tertile": _by_raw_feature_tertile(
            observations=observations,
            closed_by_entry=closed_by_entry,
            open_by_entry=open_by_entry,
            fill_events_by_entry=fill_events_by_entry,
            non_local_events_by_entry=non_local_events_by_entry,
        ),
    }


def _result_payload(
    result: RawPreEntryOutcomeAttributionResult,
    artifact_root: Path,
) -> dict[str, Any]:
    return to_jsonable(
        {
            "schema_version": result.schema_version,
            "run_id": result.run_id,
            "status": result.status,
            "checked_at": result.checked_at,
            "reason": result.reason,
            "source_stability_artifact": (
                None
                if result.source_stability_artifact is None
                else str(result.source_stability_artifact)
            ),
            "source_raw_band_artifact": (
                None
                if result.source_raw_band_artifact is None
                else str(result.source_raw_band_artifact)
            ),
            "rows_seen": result.rows_seen,
            "rows_used": result.rows_used,
            "metrics": result.metrics,
            "result_scope": {
                "mode": "research_raw_pre_entry_outcome_attribution_only",
                "descriptive_only": True,
                "promotion_gate": False,
                "local_paper_replay_changed": False,
                "broker_used": False,
                "kis_api_called": False,
                "credentials_read": False,
            },
            "artifacts": {
                "raw_pre_entry_outcome_attribution": str(result.attribution_artifact),
            },
            "artifact_policy": {
                "artifact_root": str(artifact_root),
                "repo_storage_allowed": False,
            },
        }
    )


def _diagnostic_observations(
    diagnostic_rows: Sequence[Mapping[str, Any]],
) -> tuple[_DiagnosticObservation, ...]:
    observations: list[_DiagnosticObservation] = []
    for index, row in enumerate(diagnostic_rows):
        source = str(row.get("source") or "")
        if source != DIAGNOSTIC_OVERLAY_SOURCE:
            continue
        slice_id = str(row.get("slice_id") or "")
        variant_id = str(row.get("variant_id") or "")
        symbol = str(row.get("symbol") or "").upper()
        execution_time = _utc_timestamp(row.get("execution_bar_start"))
        offset = str(row.get("offset")) if row.get("offset") is not None else ""
        if not slice_id or not variant_id or not symbol or execution_time is None or not offset:
            continue
        pre_entry = row.get("pre_entry_3bar")
        pre_entry_bucket = (
            str(pre_entry.get("bucket") or "missing")
            if isinstance(pre_entry, Mapping)
            else "missing"
        )
        local_paper_reference = row.get("local_paper_reference")
        observations.append(
            _DiagnosticObservation(
                index=index,
                signal_key=(slice_id, symbol, execution_time, offset),
                observation_key=(slice_id, variant_id, symbol, execution_time),
                entry_key=(slice_id, variant_id, symbol, execution_time),
                source=source,
                slice_id=slice_id,
                variant_id=variant_id,
                symbol=symbol,
                execution_time_utc=execution_time,
                pre_entry_bucket=pre_entry_bucket,
                raw_features={
                    feature_name: _feature_value(dict(row), feature_name)
                    for feature_name in RAW_PRE_ENTRY_FEATURE_NAMES
                },
                entered_local_paper_reference=(
                    isinstance(local_paper_reference, Mapping)
                    and local_paper_reference.get("entered_local_paper") is True
                ),
            )
        )
    return tuple(observations)


def _segments_by_entry_key(
    segments: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str, str], tuple[Mapping[str, Any], ...]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for segment in segments:
        entry = segment.get("entry")
        if not isinstance(entry, Mapping):
            continue
        if entry.get("source") != LOCAL_PAPER_SOURCE:
            continue
        key = _entry_key(segment, entry.get("timestamp"))
        if key is None:
            continue
        grouped.setdefault(key, []).append(segment)
    return {key: tuple(value) for key, value in grouped.items()}


def _fill_events_by_entry_key(
    fill_events: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[tuple[str, str, str, str], tuple[Mapping[str, Any], ...]],
    dict[tuple[str, str, str, str], tuple[Mapping[str, Any], ...]],
]:
    local: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    non_local: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for fill in fill_events:
        if str(fill.get("side") or "") != "buy":
            continue
        key = _entry_key(fill, fill.get("created_at"))
        if key is None:
            continue
        target = local if fill.get("source") == LOCAL_PAPER_SOURCE else non_local
        target.setdefault(key, []).append(fill)
    return (
        {key: tuple(value) for key, value in local.items()},
        {key: tuple(value) for key, value in non_local.items()},
    )


def _entry_key(
    payload: Mapping[str, Any],
    timestamp_value: Any,
) -> tuple[str, str, str, str] | None:
    timestamp = _utc_timestamp(timestamp_value)
    if timestamp is None:
        return None
    slice_id = str(payload.get("slice_id") or "")
    variant_id = str(payload.get("variant_id") or "")
    symbol = str(payload.get("symbol") or "").upper()
    if not slice_id or not variant_id or not symbol:
        return None
    return (slice_id, variant_id, symbol, timestamp)


def _outcome_summary(
    *,
    observation_indexes: Sequence[int],
    observations: Sequence[_DiagnosticObservation],
    closed_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    open_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    fill_events_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    non_local_events_by_entry: Mapping[
        tuple[str, str, str, str],
        Sequence[Mapping[str, Any]],
    ],
) -> dict[str, Any]:
    selected = tuple(observations[index] for index in observation_indexes)
    closed_segments: list[Mapping[str, Any]] = []
    open_segments: list[Mapping[str, Any]] = []
    local_entry_keys = set()
    non_local_fill_count = 0
    missing_local_entry_evidence = 0
    for observation in selected:
        closed = tuple(closed_by_entry.get(observation.entry_key, ()))
        opened = tuple(open_by_entry.get(observation.entry_key, ()))
        local_fills = tuple(fill_events_by_entry.get(observation.entry_key, ()))
        non_local_fills = tuple(non_local_events_by_entry.get(observation.entry_key, ()))
        if closed or opened or local_fills:
            local_entry_keys.add(observation.entry_key)
        if observation.entered_local_paper_reference and not (closed or opened or local_fills):
            missing_local_entry_evidence += 1
        non_local_fill_count += len(non_local_fills)
        closed_segments.extend(closed)
        open_segments.extend(opened)

    closed_gross = _decimal_values(closed_segments, "gross_delta")
    closed_fee_aware = _decimal_values(closed_segments, "fee_aware_delta")
    open_window = _open_window_gross_values(open_segments)
    matched_entry_count = len(local_entry_keys)
    return {
        "diagnostic_observation_count": len(selected),
        "unique_signal_count": len({observation.signal_key for observation in selected}),
        "local_paper_entry_fill_count": matched_entry_count,
        "local_paper_fill_event_count": matched_entry_count,
        "diagnostic_without_local_paper_entry_fill_count": len(selected) - matched_entry_count,
        "closed_local_paper_path_count": len(closed_segments),
        "open_local_paper_path_count": len(open_segments),
        "closed_gross_delta_sum": _format_decimal(sum(closed_gross, Decimal("0"))),
        "closed_fee_aware_delta_sum": _format_decimal(
            sum(closed_fee_aware, Decimal("0"))
        ),
        "closed_fee_aware_delta_min": (
            None if not closed_fee_aware else _format_decimal(min(closed_fee_aware))
        ),
        "closed_fee_aware_delta_max": (
            None if not closed_fee_aware else _format_decimal(max(closed_fee_aware))
        ),
        "negative_closed_fee_aware_path_count": sum(
            1 for value in closed_fee_aware if value < 0
        ),
        "non_negative_closed_fee_aware_path_count": sum(
            1 for value in closed_fee_aware if value >= 0
        ),
        "open_window_gross_delta_sum": _format_decimal(sum(open_window, Decimal("0"))),
        "missing_local_paper_entry_evidence_count": missing_local_entry_evidence,
        "missing_trade_path_evidence_count": max(
            0,
            matched_entry_count - len({segment_key for segment_key in _segment_entry_keys(
                closed_segments,
                open_segments,
            )}),
        ),
        "non_local_fill_source_count": non_local_fill_count,
        "diagnostic_source_counts": dict(
            sorted(Counter(observation.source for observation in selected).items())
        ),
    }


def _segment_entry_keys(
    closed_segments: Sequence[Mapping[str, Any]],
    open_segments: Sequence[Mapping[str, Any]],
) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for segment in (*closed_segments, *open_segments):
        entry = segment.get("entry")
        if isinstance(entry, Mapping):
            key = _entry_key(segment, entry.get("timestamp"))
            if key is not None:
                keys.add(key)
    return keys


def _by_pre_entry_bucket(
    *,
    observations: Sequence[_DiagnosticObservation],
    closed_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    open_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    fill_events_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    non_local_events_by_entry: Mapping[
        tuple[str, str, str, str],
        Sequence[Mapping[str, Any]],
    ],
) -> dict[str, Any]:
    grouped: dict[str, list[int]] = {}
    for index, observation in enumerate(observations):
        grouped.setdefault(observation.pre_entry_bucket, []).append(index)
    return {
        bucket: _outcome_summary(
            observation_indexes=indexes,
            observations=observations,
            closed_by_entry=closed_by_entry,
            open_by_entry=open_by_entry,
            fill_events_by_entry=fill_events_by_entry,
            non_local_events_by_entry=non_local_events_by_entry,
        )
        for bucket, indexes in sorted(grouped.items())
    }


def _by_raw_feature_tertile(
    *,
    observations: Sequence[_DiagnosticObservation],
    closed_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    open_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    fill_events_by_entry: Mapping[tuple[str, str, str, str], Sequence[Mapping[str, Any]]],
    non_local_events_by_entry: Mapping[
        tuple[str, str, str, str],
        Sequence[Mapping[str, Any]],
    ],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for feature_name in RAW_PRE_ENTRY_FEATURE_NAMES:
        skipped_missing = sum(
            1 for observation in observations if observation.raw_features[feature_name] is None
        )
        skip_reason, band_indexes = _raw_feature_tertile_indexes(
            observations,
            feature_name=feature_name,
        )
        payload[feature_name] = {
            "policy": {
                "family": "global_rank_tertile_by_raw_feature_value",
                "assignment": "sort_by_raw_value_then_observation_key",
                "threshold_search": False,
                "feature_rule": False,
            },
            "context": {
                "diagnostic_observation_count": len(observations),
                "scored_observation_count": sum(len(indexes) for indexes in band_indexes.values()),
                "missing_raw_value_count": skipped_missing,
                "skip_reason": skip_reason,
            },
            "bands": {
                band_id: _outcome_summary(
                    observation_indexes=indexes,
                    observations=observations,
                    closed_by_entry=closed_by_entry,
                    open_by_entry=open_by_entry,
                    fill_events_by_entry=fill_events_by_entry,
                    non_local_events_by_entry=non_local_events_by_entry,
                )
                for band_id, indexes in band_indexes.items()
            },
        }
    return payload


def _raw_feature_tertile_indexes(
    observations: Sequence[_DiagnosticObservation],
    *,
    feature_name: str,
) -> tuple[str | None, dict[str, tuple[int, ...]]]:
    scored = [
        (index, observation.raw_features[feature_name])
        for index, observation in enumerate(observations)
        if observation.raw_features[feature_name] is not None
        and math.isfinite(float(observation.raw_features[feature_name]))
    ]
    if not scored:
        return "no_observed_raw_values", {}
    if len(scored) < len(RAW_FEATURE_TERTILE_IDS):
        return "insufficient_observed_raw_values", {}
    values = [float(value) for _index, value in scored]
    if len(set(values)) == 1:
        return "tied_raw_values", {}
    ordered = sorted(
        scored,
        key=lambda item: (
            float(item[1]),
            observations[item[0]].observation_key,
        ),
    )
    grouped: dict[str, list[int]] = {band_id: [] for band_id in RAW_FEATURE_TERTILE_IDS}
    row_count = len(ordered)
    for rank, (index, _value) in enumerate(ordered):
        band_index = min(
            len(RAW_FEATURE_TERTILE_IDS) - 1,
            (rank * len(RAW_FEATURE_TERTILE_IDS)) // row_count,
        )
        band_id = RAW_FEATURE_TERTILE_IDS[band_index]
        grouped[band_id].append(index)
    return None, {band_id: tuple(indexes) for band_id, indexes in grouped.items()}


def _event_artifacts_from_stability(
    payload: Mapping[str, Any],
    *,
    artifact_root: Path,
) -> tuple[TradePathEventArtifact, ...]:
    metrics = payload.get("metrics")
    variant_meta = (
        metrics.get("added_source_variant_meta") if isinstance(metrics, Mapping) else None
    )
    if not isinstance(variant_meta, Sequence):
        return ()
    artifacts: list[TradePathEventArtifact] = []
    for item in variant_meta:
        if not isinstance(item, Mapping):
            continue
        slice_id = str(item.get("slice_id") or "")
        variant_id = str(item.get("variant_id") or "")
        symbol = str(item.get("symbol") or "")
        if not slice_id or not variant_id or not symbol:
            continue
        artifacts.append(
            TradePathEventArtifact(
                path=_resolve_lineage_path(
                    item.get("events_artifact"),
                    artifact_root=artifact_root,
                ),
                expected_fill_count=int(item.get("local_paper_fill_count") or 0),
                slice_id=slice_id,
                variant_id=variant_id,
                symbol=symbol,
            )
        )
    return tuple(artifacts)


def _fill_events_from_event_artifacts(
    event_artifacts: Sequence[TradePathEventArtifact],
) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    for artifact in event_artifacts:
        for fill in _read_fill_events(artifact):
            enriched = dict(fill)
            enriched["slice_id"] = artifact.slice_id
            enriched["variant_id"] = artifact.variant_id
            enriched["symbol"] = artifact.symbol.upper()
            events.append(enriched)
    return tuple(events)


def _bars_from_stability(
    payload: Mapping[str, Any],
    *,
    artifact_root: Path,
) -> tuple[tuple[Bar, ...], tuple[str, ...]]:
    consumed_slices = payload.get("consumed_slices")
    if not isinstance(consumed_slices, Sequence):
        return (), ("stability artifact lacks consumed_slices",)
    bars: list[Bar] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for item in consumed_slices:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol") or "").upper()
        path = _resolve_lineage_path(
            item.get("local_market_data_path"),
            artifact_root=artifact_root,
        )
        if not symbol or path is None:
            errors.append(f"{item.get('slice_id') or 'missing'}: market data path is missing")
            continue
        key = (symbol, str(path))
        if key in seen:
            continue
        seen.add(key)
        max_bars = int(item.get("bars_loaded_for_symbol") or 5000)
        try:
            bars.extend(
                load_yahoo_intraday_1m_bars(
                    path,
                    symbol=symbol,
                    max_bars=max(max_bars, 1),
                )
            )
        except (OSError, ValueError) as exc:
            errors.append(f"{item.get('slice_id') or symbol}: {exc}")
    return tuple(bars), tuple(errors)


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


def _raw_band_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping):
        return {"available": False}
    group_results = metrics.get("group_results")
    if not isinstance(group_results, Mapping):
        return {"available": False}
    raw_group = group_results.get("raw_pre_entry")
    if not isinstance(raw_group, Mapping):
        return {"available": False}
    descriptive = raw_group.get("descriptive_evaluation")
    if not isinstance(descriptive, Mapping):
        return {"available": False}
    unique = descriptive.get("unique_signal_descriptive_evaluation")
    if not isinstance(unique, Mapping):
        return {"available": False}
    raw_attr = unique.get("raw_pre_entry_band_attribution")
    if not isinstance(raw_attr, Mapping):
        return {"available": False}
    return {
        "available": True,
        "scored_unique_signal_count": raw_attr.get("context", {}).get(
            "scored_unique_signal_count"
        )
        if isinstance(raw_attr.get("context"), Mapping)
        else None,
        "raw_feature_names": raw_attr.get("context", {}).get("raw_feature_names")
        if isinstance(raw_attr.get("context"), Mapping)
        else None,
        "overall_raw_feature_summaries": raw_attr.get("overall_raw_feature_summaries"),
        "high_vs_overall": raw_attr.get("comparisons", {}).get(
            "tertile_3_high_probability_vs_overall"
        )
        if isinstance(raw_attr.get("comparisons"), Mapping)
        else None,
        "high_vs_low": raw_attr.get("comparisons", {}).get(
            "tertile_3_high_probability_vs_tertile_1_low_probability"
        )
        if isinstance(raw_attr.get("comparisons"), Mapping)
        else None,
    }


def _source_counts(observations: Sequence[_DiagnosticObservation]) -> dict[str, int]:
    return dict(sorted(Counter(observation.source for observation in observations).items()))


def _source_counts_from_payloads(payloads: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(Counter(str(payload.get("source") or "missing") for payload in payloads).items())
    )


def _non_local_fill_source_count(local_paper_verification: Mapping[str, Any]) -> int:
    counts = local_paper_verification.get("non_local_fill_source_counts")
    if not isinstance(counts, Mapping):
        return 0
    return sum(int(value or 0) for value in counts.values())


def _decimal_values(
    payloads: Sequence[Mapping[str, Any]],
    key: str,
) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for payload in payloads:
        value = _decimal_or_none(payload.get(key))
        if value is not None:
            values.append(value)
    return tuple(values)


def _open_window_gross_values(
    open_segments: Sequence[Mapping[str, Any]],
) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for segment in open_segments:
        window_end = segment.get("window_end")
        if not isinstance(window_end, Mapping):
            continue
        value = _decimal_or_none(window_end.get("gross_delta"))
        if value is not None:
            values.append(value)
    return tuple(values)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return decimal if decimal.is_finite() else None


def _format_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _utc_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()

"""Target-free, CPU-only candle representation preflight for KIS broad D1.

The module consumes an already reattested Data-owned grid in memory.  It never
opens a provider, credential, broker, Paper, network, GPU, or model route.  Its
only write is one aggregate-only receipt beneath an external artifact root.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

from .artifact_paths import ensure_external_artifact_directory

KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ID = (
    "kis-broad-d1-invariant-candle-representation-cpu-preflight-v1"
)
KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts"
)
KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_SOURCE_DATASET_ID = (
    "kis.paper.private.daily.nas.broad.panel-v1"
)
KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_FEATURE_NAMES = (
    "high_to_open",
    "low_to_open",
    "close_to_open",
)

_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_GEOMETRY_EVENT_RATIO = 2.0
_INPUT_UNAVAILABLE_CODES = frozenset(
    {
        "data_adapter_contract_unavailable",
        "data_adapter_unavailable",
        "geometry_audit_mismatch",
        "insufficient_coverage",
        "insufficient_eligible_symbols",
        "source_drift",
        "source_geometry_failure",
    }
)
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class KisBroadD1InvariantCandleRepresentationInputUnavailable(ValueError):
    """The frozen source cannot satisfy the representation contract."""

    def __init__(self, code: str) -> None:
        if code not in _INPUT_UNAVAILABLE_CODES:
            raise ValueError("invariant candle representation unavailable code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KisBroadD1InvariantCandleRepresentationSpec:
    """The fixed target-free panel and chronological partitions."""

    cohort_target_count: int = 128
    history_session_count: int = 800
    terminal_buffer_sessions: int = 1
    development_session_count: int = 520
    purge_session_count: int = 20
    validation_session_count: int = 260
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.cohort_target_count < 2
            or self.history_session_count < 4
            or self.terminal_buffer_sessions != 1
            or self.development_session_count < 1
            or self.purge_session_count < 1
            or self.validation_session_count < 1
            or self.development_session_count
            + self.purge_session_count
            + self.validation_session_count
            != self.history_session_count
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("invariant candle representation spec is invalid")

    @property
    def validation_start_index(self) -> int:
        return self.development_session_count + self.purge_session_count

    def safe_payload(self) -> dict[str, object]:
        return {
            "cohort_target_count": self.cohort_target_count,
            "cohort_selection": "inherited_reverified_lexicographic_coverage_cohort",
            "history_session_count": self.history_session_count,
            "terminal_buffer_sessions": self.terminal_buffer_sessions,
            "development_session_count": self.development_session_count,
            "purge_session_count": self.purge_session_count,
            "validation_session_count": self.validation_session_count,
            "same_day_candle_ratio_features": list(
                KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_FEATURE_NAMES
            ),
            "cross_sectional_rank": "same_session_midrank_percentile_zero_to_one",
            "validation_use": "target_free_representation_confirmation_only",
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1InvariantCandleRepresentationInput:
    """One in-memory Data-owned grid plus its geometry-audit lineage."""

    dataset_id: str
    dataset_hash: str
    manifest_sha256: str
    materialization_receipt_sha256: str
    source_index_hash: str
    target_key_set_hash: str
    geometry_audit_receipt_sha256: str
    geometry_audit_contract_sha256: str
    geometry_audit_source_grid_sha256: str
    geometry_audit_event_mask_sha256: str
    full_target_count: int
    coverage_eligible_target_count: int
    raw_byte_attested_target_count: int
    selected_target_keys: tuple[str, ...]
    decision_session_grid: tuple[datetime, ...]
    terminal_execution_session: datetime
    grid_bars_by_target: Mapping[str, tuple[Bar, ...]]
    terminal_execution_bars_by_target: Mapping[str, Bar]
    range_event_flags_by_target: Mapping[str, tuple[bool, ...]]
    limitations: tuple[str, ...]
    spec: KisBroadD1InvariantCandleRepresentationSpec = (
        KisBroadD1InvariantCandleRepresentationSpec()
    )
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        target_keys = tuple(self.selected_target_keys)
        grid = tuple(self.decision_session_grid)
        grid_bars = MappingProxyType(
            {target_key: tuple(bars) for target_key, bars in self.grid_bars_by_target.items()}
        )
        terminal_bars = MappingProxyType(dict(self.terminal_execution_bars_by_target))
        event_flags = MappingProxyType(
            {
                target_key: tuple(flags)
                for target_key, flags in self.range_event_flags_by_target.items()
            }
        )
        if (
            self.dataset_id != KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_SOURCE_DATASET_ID
            or not isinstance(self.spec, KisBroadD1InvariantCandleRepresentationSpec)
            or any(
                not _is_sha256(value)
                for value in (
                    self.dataset_hash,
                    self.manifest_sha256,
                    self.materialization_receipt_sha256,
                    self.source_index_hash,
                    self.target_key_set_hash,
                    self.geometry_audit_receipt_sha256,
                    self.geometry_audit_contract_sha256,
                    self.geometry_audit_source_grid_sha256,
                    self.geometry_audit_event_mask_sha256,
                )
            )
            or self.full_target_count < self.coverage_eligible_target_count
            or self.coverage_eligible_target_count < len(target_keys)
            or self.raw_byte_attested_target_count < len(target_keys)
            or self.raw_byte_attested_target_count > self.coverage_eligible_target_count
            or len(target_keys) != self.spec.cohort_target_count
            or tuple(sorted(target_keys)) != target_keys
            or len(set(target_keys)) != len(target_keys)
            or any(not _target_key_is_valid(value) for value in target_keys)
            or len(grid) != self.spec.history_session_count
            or not all(isinstance(session, datetime) for session in grid)
            or tuple(sorted(grid)) != grid
            or len(set(grid)) != len(grid)
            or not isinstance(self.terminal_execution_session, datetime)
            or self.terminal_execution_session <= grid[-1]
            or set(grid_bars) != set(target_keys)
            or set(terminal_bars) != set(target_keys)
            or set(event_flags) != set(target_keys)
            or not self.limitations
            or any(not isinstance(value, str) or not value for value in self.limitations)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("invariant candle representation input is invalid")
        for target_key in target_keys:
            if (
                len(grid_bars[target_key]) != len(grid)
                or not isinstance(terminal_bars[target_key], Bar)
                or len(event_flags[target_key]) != len(grid)
                or any(type(flag) is not bool for flag in event_flags[target_key])
            ):
                raise ValueError("invariant candle representation input is invalid")
        object.__setattr__(self, "selected_target_keys", target_keys)
        object.__setattr__(self, "decision_session_grid", grid)
        object.__setattr__(self, "grid_bars_by_target", grid_bars)
        object.__setattr__(self, "terminal_execution_bars_by_target", terminal_bars)
        object.__setattr__(self, "range_event_flags_by_target", event_flags)

    @property
    def target_count(self) -> int:
        return len(self.selected_target_keys)

    @property
    def split_hash(self) -> str:
        return _sha256_payload(
            {
                "development_session_count": self.spec.development_session_count,
                "purge_session_count": self.spec.purge_session_count,
                "validation_session_count": self.spec.validation_session_count,
                "history_session_count": self.spec.history_session_count,
                "terminal_buffer_sessions": self.spec.terminal_buffer_sessions,
            }
        )

    def safe_source_payload(self) -> dict[str, object]:
        return {
            "dataset_hash": self.dataset_hash,
            "manifest_sha256": self.manifest_sha256,
            "materialization_receipt_sha256": self.materialization_receipt_sha256,
            "source_index_hash": self.source_index_hash,
            "target_key_set_hash": self.target_key_set_hash,
            "geometry_audit_receipt_sha256": self.geometry_audit_receipt_sha256,
            "geometry_audit_contract_sha256": self.geometry_audit_contract_sha256,
            "geometry_audit_source_grid_sha256": self.geometry_audit_source_grid_sha256,
            "geometry_audit_event_mask_sha256": self.geometry_audit_event_mask_sha256,
            "full_target_count": self.full_target_count,
            "coverage_eligible_target_count": self.coverage_eligible_target_count,
            "selected_target_count": self.target_count,
            "raw_byte_attested_target_count": self.raw_byte_attested_target_count,
            "common_session_count": len(self.decision_session_grid),
            "terminal_buffer_sessions": self.spec.terminal_buffer_sessions,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1InvariantCandleRepresentationDigest:
    """Opaque hashes of one completed-bar representation partition."""

    session_count: int
    ratio_feature_hash: str
    rank_feature_hash: str
    representation_hash: str

    def __post_init__(self) -> None:
        if (
            self.session_count < 1
            or not _is_sha256(self.ratio_feature_hash)
            or not _is_sha256(self.rank_feature_hash)
            or not _is_sha256(self.representation_hash)
            or self.representation_hash
            != _sha256_payload(
                {
                    "ratio_feature_hash": self.ratio_feature_hash,
                    "rank_feature_hash": self.rank_feature_hash,
                    "session_count": self.session_count,
                }
            )
        ):
            raise ValueError("invariant candle representation digest is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "session_count": self.session_count,
            "ratio_feature_hash": self.ratio_feature_hash,
            "rank_feature_hash": self.rank_feature_hash,
            "representation_hash": self.representation_hash,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1InvariantCandleRepresentationEvaluation:
    """Completed target-free digests and in-memory invariance checks."""

    full: KisBroadD1InvariantCandleRepresentationDigest
    development: KisBroadD1InvariantCandleRepresentationDigest
    validation: KisBroadD1InvariantCandleRepresentationDigest
    positive_per_symbol_scaling_invariant_passed: bool
    future_grid_bar_prefix_invariant_passed: bool
    future_grid_bar_changes_its_own_and_later_digest: bool
    terminal_buffer_invariant_passed: bool

    def __post_init__(self) -> None:
        if (
            not self.positive_per_symbol_scaling_invariant_passed
            or not self.future_grid_bar_prefix_invariant_passed
            or not self.future_grid_bar_changes_its_own_and_later_digest
            or not self.terminal_buffer_invariant_passed
        ):
            raise ValueError("invariant candle representation kill test failed")


@dataclass(frozen=True, slots=True)
class KisBroadD1InvariantCandleRepresentationRun:
    """One immutable external CPU preflight receipt."""

    status: Literal["completed", "input_unavailable"]
    run_directory: Path
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            self.status not in {"completed", "input_unavailable"}
            or not self.run_directory.is_dir()
            or not self.receipt_path.is_file()
            or not _is_sha256(self.receipt_sha256)
            or _sha256_file(self.receipt_path) != self.receipt_sha256
        ):
            raise ValueError("invariant candle representation run is invalid")


def derive_kis_broad_d1_invariant_candle_representation_digest(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
    *,
    start_index: int = 0,
    stop_index: int | None = None,
    grid_bars_by_target: Mapping[str, tuple[Bar, ...]] | None = None,
) -> KisBroadD1InvariantCandleRepresentationDigest:
    """Hash one completed-bar interval without persisting its rows or values."""

    if not isinstance(source_input, KisBroadD1InvariantCandleRepresentationInput):
        raise TypeError("invariant candle representation requires a prepared source input")
    resolved_stop = source_input.spec.history_session_count if stop_index is None else stop_index
    if not 0 <= start_index < resolved_stop <= source_input.spec.history_session_count:
        raise ValueError("invariant candle representation interval is invalid")
    bars_by_target = (
        source_input.grid_bars_by_target if grid_bars_by_target is None else grid_bars_by_target
    )
    if set(bars_by_target) != set(source_input.selected_target_keys):
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("source_drift")
    normalized = {
        target_key: tuple(bars_by_target[target_key])
        for target_key in source_input.selected_target_keys
    }
    if any(
        len(normalized[target_key]) != source_input.spec.history_session_count
        for target_key in source_input.selected_target_keys
    ):
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("source_drift")

    ratio_hasher = hashlib.sha256()
    rank_hasher = hashlib.sha256()
    with localcontext() as context:
        context.prec = 50
        for session_index in range(start_index, resolved_stop):
            ratios_by_target = {
                target_key: _candle_ratios(
                    normalized[target_key][session_index],
                    expected_symbol=_symbol_from_target_key(target_key),
                    expected_start=source_input.decision_session_grid[session_index],
                )
                for target_key in source_input.selected_target_keys
            }
            ranks_by_target = _cross_sectional_midrank_percentiles(
                ratios_by_target,
                target_keys=source_input.selected_target_keys,
            )
            for target_index, target_key in enumerate(source_input.selected_target_keys):
                ratio_hasher.update(
                    _feature_row_bytes(
                        session_index,
                        target_index,
                        ratios_by_target[target_key],
                    )
                )
                rank_hasher.update(
                    _feature_row_bytes(
                        session_index,
                        target_index,
                        ranks_by_target[target_key],
                    )
                )
    ratio_feature_hash = "sha256:" + ratio_hasher.hexdigest()
    rank_feature_hash = "sha256:" + rank_hasher.hexdigest()
    return KisBroadD1InvariantCandleRepresentationDigest(
        session_count=resolved_stop - start_index,
        ratio_feature_hash=ratio_feature_hash,
        rank_feature_hash=rank_feature_hash,
        representation_hash=_sha256_payload(
            {
                "ratio_feature_hash": ratio_feature_hash,
                "rank_feature_hash": rank_feature_hash,
                "session_count": resolved_stop - start_index,
            }
        ),
    )


def evaluate_kis_broad_d1_invariant_candle_representation(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
) -> KisBroadD1InvariantCandleRepresentationEvaluation:
    """Run the fixed source and causal invariance checks in memory only."""

    _validate_source_lineage_and_geometry(source_input)
    full = derive_kis_broad_d1_invariant_candle_representation_digest(source_input)
    development = derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        stop_index=source_input.spec.development_session_count,
    )
    validation = derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        start_index=source_input.spec.validation_start_index,
    )

    scaled = derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        grid_bars_by_target=_positive_per_symbol_scaled_grid(source_input),
    )
    future_index = source_input.spec.development_session_count
    mutated_grid = _future_grid_bar_mutated_grid(
        source_input,
        future_index=future_index,
    )
    original_prefix = derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        stop_index=future_index,
    )
    mutated_prefix = derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        stop_index=future_index,
        grid_bars_by_target=mutated_grid,
    )
    mutated_full = derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        grid_bars_by_target=mutated_grid,
    )
    terminal_mutated_input = replace(
        source_input,
        terminal_execution_bars_by_target=_terminal_buffer_mutated_bars(source_input),
    )
    terminal_mutated = derive_kis_broad_d1_invariant_candle_representation_digest(
        terminal_mutated_input
    )
    return KisBroadD1InvariantCandleRepresentationEvaluation(
        full=full,
        development=development,
        validation=validation,
        positive_per_symbol_scaling_invariant_passed=(
            scaled.ratio_feature_hash == full.ratio_feature_hash
            and scaled.rank_feature_hash == full.rank_feature_hash
        ),
        future_grid_bar_prefix_invariant_passed=(
            mutated_prefix.ratio_feature_hash == original_prefix.ratio_feature_hash
            and mutated_prefix.rank_feature_hash == original_prefix.rank_feature_hash
        ),
        future_grid_bar_changes_its_own_and_later_digest=(
            mutated_full.ratio_feature_hash != full.ratio_feature_hash
        ),
        terminal_buffer_invariant_passed=(
            terminal_mutated.ratio_feature_hash == full.ratio_feature_hash
            and terminal_mutated.rank_feature_hash == full.rank_feature_hash
        ),
    )


def run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
    *,
    source_input: KisBroadD1InvariantCandleRepresentationInput | None,
    input_unavailable_reason: str | None = None,
    artifact_root: Path
    | str = KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ARTIFACT_ROOT,
    run_label: str,
    repo_root: Path | str | None = None,
) -> KisBroadD1InvariantCandleRepresentationRun:
    """Write one source-safe completion or input-unavailable receipt."""

    if not _RUN_LABEL.fullmatch(run_label):
        raise ValueError("invariant candle representation run label is invalid")
    if (source_input is None) == (input_unavailable_reason is None):
        raise ValueError("source input and unavailable reason must be mutually exclusive")
    repository = _repository_root(repo_root)
    output_directory = _prepare_output_directory(
        artifact_root=Path(artifact_root),
        repo_root=repository,
        run_label=run_label,
    )
    if source_input is None:
        reason = _validated_input_unavailable_reason(input_unavailable_reason)
        receipt_path = output_directory / "input-unavailable.json"
        receipt_sha256 = _write_json_new(
            receipt_path,
            _input_unavailable_payload(
                reason=reason,
                spec=KisBroadD1InvariantCandleRepresentationSpec(),
            ),
        )
        return KisBroadD1InvariantCandleRepresentationRun(
            status="input_unavailable",
            run_directory=output_directory,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
        )
    try:
        evaluation = evaluate_kis_broad_d1_invariant_candle_representation(source_input)
    except KisBroadD1InvariantCandleRepresentationInputUnavailable as error:
        receipt_path = output_directory / "input-unavailable.json"
        receipt_sha256 = _write_json_new(
            receipt_path,
            _input_unavailable_payload(reason=error.code, spec=source_input.spec),
        )
        return KisBroadD1InvariantCandleRepresentationRun(
            status="input_unavailable",
            run_directory=output_directory,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
        )
    receipt_path = output_directory / "summary.json"
    receipt_sha256 = _write_json_new(
        receipt_path,
        _summary_payload(source_input, evaluation=evaluation),
    )
    return KisBroadD1InvariantCandleRepresentationRun(
        status="completed",
        run_directory=output_directory,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
    )


def _validate_source_lineage_and_geometry(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
) -> None:
    expected_grid_hash = _sha256_payload(
        {"session_starts": [session.isoformat() for session in source_input.decision_session_grid]}
    )
    if expected_grid_hash != source_input.geometry_audit_source_grid_sha256:
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("geometry_audit_mismatch")
    if source_input.target_key_set_hash != _selected_target_key_set_hash(
        source_input.selected_target_keys
    ):
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("geometry_audit_mismatch")

    event_rows: list[list[bool]] = []
    for target_key in source_input.selected_target_keys:
        expected_symbol = _symbol_from_target_key(target_key)
        events: list[bool] = []
        for session_index, bar in enumerate(source_input.grid_bars_by_target[target_key]):
            _validate_completed_d1_bar(
                bar,
                expected_symbol=expected_symbol,
                expected_start=source_input.decision_session_grid[session_index],
            )
            events.append(_geometry_event(bar))
        _validate_completed_d1_bar(
            source_input.terminal_execution_bars_by_target[target_key],
            expected_symbol=expected_symbol,
            expected_start=source_input.terminal_execution_session,
        )
        if tuple(events) != source_input.range_event_flags_by_target[target_key]:
            raise KisBroadD1InvariantCandleRepresentationInputUnavailable("geometry_audit_mismatch")
        event_rows.append(events)
    if _sha256_bool_matrix(event_rows) != source_input.geometry_audit_event_mask_sha256:
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("geometry_audit_mismatch")


def _candle_ratios(
    bar: Bar,
    *,
    expected_symbol: str,
    expected_start: datetime,
) -> tuple[Decimal, Decimal, Decimal]:
    _validate_completed_d1_bar(
        bar,
        expected_symbol=expected_symbol,
        expected_start=expected_start,
    )
    return (bar.high / bar.open, bar.low / bar.open, bar.close / bar.open)


def _cross_sectional_midrank_percentiles(
    ratios_by_target: Mapping[str, tuple[Decimal, Decimal, Decimal]],
    *,
    target_keys: tuple[str, ...],
) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    ranks: dict[str, list[Decimal]] = {target_key: [] for target_key in target_keys}
    for feature_index in range(len(KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_FEATURE_NAMES)):
        values = [ratios_by_target[target_key][feature_index] for target_key in target_keys]
        for target_key, value in zip(target_keys, values, strict=True):
            lower_count = sum(other < value for other in values)
            equal_count = sum(other == value for other in values)
            ranks[target_key].append(
                Decimal((2 * lower_count) + equal_count) / Decimal(2 * len(values))
            )
    return {target_key: tuple(values) for target_key, values in ranks.items()}  # type: ignore[return-value]


def _positive_per_symbol_scaled_grid(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
) -> dict[str, tuple[Bar, ...]]:
    return {
        target_key: tuple(
            _scale_bar(bar, Decimal(target_index + 2))
            for bar in source_input.grid_bars_by_target[target_key]
        )
        for target_index, target_key in enumerate(source_input.selected_target_keys)
    }


def _future_grid_bar_mutated_grid(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
    *,
    future_index: int,
) -> dict[str, tuple[Bar, ...]]:
    if not 0 < future_index < source_input.spec.history_session_count:
        raise ValueError("future mutation index is invalid")
    target_key = source_input.selected_target_keys[0]
    bars_by_target = {
        key: tuple(values) for key, values in source_input.grid_bars_by_target.items()
    }
    changed = list(bars_by_target[target_key])
    changed[future_index] = _shape_mutated_bar(changed[future_index])
    bars_by_target[target_key] = tuple(changed)
    return bars_by_target


def _terminal_buffer_mutated_bars(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
) -> dict[str, Bar]:
    result = dict(source_input.terminal_execution_bars_by_target)
    target_key = source_input.selected_target_keys[0]
    result[target_key] = _shape_mutated_bar(result[target_key])
    return result


def _scale_bar(bar: Bar, multiplier: Decimal) -> Bar:
    return replace(
        bar,
        open=bar.open * multiplier,
        high=bar.high * multiplier,
        low=bar.low * multiplier,
        close=bar.close * multiplier,
        volume=bar.volume * multiplier,
    )


def _shape_mutated_bar(bar: Bar) -> Bar:
    return replace(
        bar,
        high=bar.high * Decimal("1.02"),
        low=bar.low * Decimal("0.98"),
        close=bar.open,
    )


def _validate_completed_d1_bar(
    bar: object,
    *,
    expected_symbol: str,
    expected_start: datetime,
) -> None:
    if (
        not isinstance(bar, Bar)
        or bar.symbol != expected_symbol
        or bar.market != "US"
        or bar.timeframe is not Timeframe.D1
        or not bar.complete
        or bar.start_ts != expected_start
    ):
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("source_geometry_failure")
    values = (bar.open, bar.high, bar.low, bar.close)
    if (
        any(
            not isinstance(value, Decimal) or not value.is_finite() or value <= 0
            for value in values
        )
        or bar.high < max(bar.open, bar.close)
        or bar.low > min(bar.open, bar.close)
    ):
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("source_geometry_failure")


def _geometry_event(bar: Bar) -> bool:
    high_value = float(bar.high)
    low_value = float(bar.low)
    if (
        not math.isfinite(high_value)
        or not math.isfinite(low_value)
        or high_value <= 0.0
        or low_value <= 0.0
    ):
        raise KisBroadD1InvariantCandleRepresentationInputUnavailable("source_geometry_failure")
    return high_value / low_value > _GEOMETRY_EVENT_RATIO


def _feature_row_bytes(
    session_index: int,
    target_index: int,
    values: Sequence[Decimal],
) -> bytes:
    return (
        json.dumps(
            {
                "feature_index": list(range(len(values))),
                "session_index": session_index,
                "target_index": target_index,
                "values": [_decimal_text(value) for value in values],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _summary_payload(
    source_input: KisBroadD1InvariantCandleRepresentationInput,
    *,
    evaluation: KisBroadD1InvariantCandleRepresentationEvaluation,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ID,
        "status": "completed",
        "claim": (
            "one source-local target-free candle representation confirmation; no model, "
            "ranking, forecast, trade, PnL, promotion, ensemble, or live claim"
        ),
        "source": source_input.safe_source_payload(),
        "spec": source_input.spec.safe_payload(),
        "partitions": {
            "development": evaluation.development.safe_payload(),
            "purge": {
                "excluded_from_representation_confirmation": True,
                "session_count": source_input.spec.purge_session_count,
            },
            "validation": evaluation.validation.safe_payload(),
        },
        "full_representation": evaluation.full.safe_payload(),
        "invariance_kill_tests": {
            "positive_per_symbol_scaling_ratio_hash_unchanged": (
                evaluation.positive_per_symbol_scaling_invariant_passed
            ),
            "positive_per_symbol_scaling_rank_hash_unchanged": (
                evaluation.positive_per_symbol_scaling_invariant_passed
            ),
            "future_grid_bar_mutation_does_not_change_prior_prefix": (
                evaluation.future_grid_bar_prefix_invariant_passed
            ),
            "future_grid_bar_mutation_changes_own_or_later_digest": (
                evaluation.future_grid_bar_changes_its_own_and_later_digest
            ),
            "terminal_buffer_mutation_does_not_change_grid_representation": (
                evaluation.terminal_buffer_invariant_passed
            ),
        },
        "scope": {
            "target_free": True,
            "source_local_development_and_validation_confirmation_only": True,
            "current_listing_only": True,
            "point_in_time_eligible": False,
            "corporate_action_qualified": False,
            "session_finality_attested": False,
            "cross_sectional_ranking_allowed": False,
            "model_training_allowed": False,
            "paper_input_allowed": False,
            "pnl_or_profitability_claim_allowed": False,
            "live_allowed": False,
        },
        "artifact_policy": {
            "external_artifact_only": True,
            "raw_market_data_persisted": False,
            "raw_rows_persisted": False,
            "symbols_persisted": False,
            "prices_persisted": False,
            "supervised_targets_persisted": False,
            "inference_outputs_persisted": False,
            "allocation_values_persisted": False,
            "model_state_persisted": False,
            "network_access": False,
            "credentials_read": False,
            "broker_access": False,
            "paper_access": False,
            "gpu_used": False,
        },
    }


def _input_unavailable_payload(
    *,
    reason: str,
    spec: KisBroadD1InvariantCandleRepresentationSpec,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ID,
        "status": "input_unavailable",
        "reason": reason,
        "claim": "no source input was represented and no model or trading result exists",
        "spec": spec.safe_payload(),
        "artifact_policy": {
            "external_artifact_only": True,
            "raw_market_data_persisted": False,
            "raw_rows_persisted": False,
            "symbols_persisted": False,
            "prices_persisted": False,
            "supervised_targets_persisted": False,
            "inference_outputs_persisted": False,
            "allocation_values_persisted": False,
            "model_state_persisted": False,
            "network_access": False,
            "credentials_read": False,
            "broker_access": False,
            "paper_access": False,
            "gpu_used": False,
        },
    }


def _prepare_output_directory(
    *,
    artifact_root: Path,
    repo_root: Path,
    run_label: str,
) -> Path:
    root = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "research",
        KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_CPU_PREFLIGHT_ID,
    )
    destination = root / run_label
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("invariant candle representation artifact already exists")
    destination.mkdir()
    resolved = destination.resolve(strict=True)
    if resolved != destination or not resolved.is_relative_to(root):
        raise ValueError("invariant candle representation artifact path is invalid")
    return resolved


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _assert_source_safe_document(payload)
    encoded = (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
    return _sha256_bytes(encoded)


def _assert_source_safe_document(value: object) -> None:
    forbidden = {
        "account",
        "bar",
        "bars",
        "close",
        "high",
        "low",
        "open",
        "order",
        "orders",
        "price",
        "prices",
        "symbol",
        "symbols",
        "volume",
        "volumes",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in forbidden:
                raise ValueError("invariant candle representation receipt contains source values")
            _assert_source_safe_document(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe_document(nested)


def _validated_input_unavailable_reason(value: str | None) -> str:
    if value not in _INPUT_UNAVAILABLE_CODES:
        raise ValueError("invariant candle representation unavailable reason is invalid")
    return value


def _target_key_is_valid(value: object) -> bool:
    if not isinstance(value, str) or value.count("/") != 1:
        return False
    symbol, exchange = value.split("/", maxsplit=1)
    return bool(symbol and exchange)


def _symbol_from_target_key(value: str) -> str:
    return value.split("/", maxsplit=1)[0]


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized.is_zero() else format(normalized, "f")


def _repository_root(value: Path | str | None) -> Path:
    return Path(value).resolve() if value is not None else _MODULE_REPOSITORY_ROOT


def _sha256_bool_matrix(values: Sequence[Sequence[bool]]) -> str:
    return _sha256_bytes(bytes(value for row in values for value in row))


def _selected_target_key_set_hash(target_keys: tuple[str, ...]) -> str:
    return _sha256_bytes(
        (
            json.dumps(
                {"target_keys": list(target_keys)},
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True

"""Frozen, source-local KIS broad-D1 cross-sectional momentum benchmark.

The module is deliberately pure research code.  It accepts reattested completed
``Bar`` streams in memory, computes aggregate diagnostics, and writes only
source-safe external receipts.  Data loading belongs at the runner boundary;
this module has no provider, credential, network, broker, Paper, GPU, model,
or holdout route.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe

from .artifact_paths import ensure_external_artifact_directory

KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID = (
    "kis-broad-d1-cross-sectional-momentum-cpu-baseline-v1"
)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts"
)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_DATASET_ID = (
    "kis.paper.private.daily.nas.broad.panel-v1"
)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ADJUSTMENT_MODE = "MODP=0_unadjusted"
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS = (5, 20, 60)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TOP_K = 10
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_DEVELOPMENT_SESSIONS = 520
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PURGE_SESSIONS = 20
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_VALIDATION_SESSIONS = 260
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_SESSION_COUNT = 800
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_MAX_HIGH_LOW_RATIO = Decimal("2")
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ROUND_TRIP_COST_BPS = (
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PRIMARY_COST_BPS = Decimal("10")

_INPUT_UNAVAILABLE_LIMITATIONS = ("source_input_not_attached",)
_NAIVE_CONTROL_IDS = (
    "always_flat",
    "equal_weight_all_hygiene_eligible",
    "lexicographic_top_k_hygiene_eligible",
)
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SAFE_UNAVAILABLE_REASON = re.compile(r"[a-z][a-z0-9_]{2,95}", re.ASCII)
_ALLOWED_REVIEW_STATUSES = frozenset(
    {
        "not_required_before_outcome",
        "unsupported",
        "uncertain",
        "supported-with-limits",
        "review_unavailable",
    }
)
_COST_KEYS = tuple(
    str(int(value))
    for value in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ROUND_TRIP_COST_BPS
)
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class KisBroadD1CrossSectionalMomentumInputUnavailable(ValueError):
    """The named read-only input cannot support this frozen benchmark."""

    def __init__(self, code: str) -> None:
        if not _SAFE_UNAVAILABLE_REASON.fullmatch(code):
            raise ValueError("KIS broad D1 momentum unavailable code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KisBroadD1CrossSectionalMomentumSpec:
    """The fixed strategy, chronology, hygiene, cost, and falsification contract."""

    lookbacks: tuple[int, ...] = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS
    top_k: int = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TOP_K
    development_session_count: int = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_DEVELOPMENT_SESSIONS
    purge_session_count: int = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PURGE_SESSIONS
    validation_session_count: int = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_VALIDATION_SESSIONS
    maximum_high_low_ratio: Decimal = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_MAX_HIGH_LOW_RATIO
    round_trip_cost_bps: tuple[Decimal, ...] = (
        KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ROUND_TRIP_COST_BPS
    )
    primary_round_trip_cost_bps: Decimal = (
        KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PRIMARY_COST_BPS
    )
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.lookbacks != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS
            or self.top_k != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TOP_K
            or self.development_session_count
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_DEVELOPMENT_SESSIONS
            or self.purge_session_count
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PURGE_SESSIONS
            or self.validation_session_count
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_VALIDATION_SESSIONS
            or self.development_session_count
            + self.purge_session_count
            + self.validation_session_count
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_SESSION_COUNT
            or self.maximum_high_low_ratio
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_MAX_HIGH_LOW_RATIO
            or self.round_trip_cost_bps
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ROUND_TRIP_COST_BPS
            or self.primary_round_trip_cost_bps
            != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PRIMARY_COST_BPS
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS broad D1 cross-sectional momentum spec is frozen")

    def safe_payload(self) -> dict[str, object]:
        return {
            "lookback_sessions_matrix": list(self.lookbacks),
            "rank_rule": "descending_completed_close_return_then_opaque_key_tiebreak",
            "top_k": self.top_k,
            "exposure": "long_only_equal_weight_when_top_k_available_else_flat",
            "chronological_split": {
                "development_sessions": self.development_session_count,
                "purge_sessions": self.purge_session_count,
                "validation_sessions": self.validation_session_count,
                "development_and_validation_use_in_partition_completed_feature_warmup": True,
            },
            "availability": {
                "feature": "completed_close_t_over_completed_close_t_minus_lookback_plus_one",
                "decision_time": "completed_bar_t_close",
                "entry": "t_plus_1_open",
                "exit": "t_plus_1_close",
                "future_feature_access": False,
            },
            "feature_hygiene": {
                "rule": "exclude_target_when_any_completed_feature_bar_high_low_ratio_gt_2",
                "window": "t_minus_lookback_through_t_completed_bars_only",
                "future_entry_or_exit_bar_censored": False,
            },
            "cost_stress_axis": {
                "round_trip_bps": [_decimal_text(value) for value in self.round_trip_cost_bps],
                "primary_round_trip_bps": _decimal_text(self.primary_round_trip_cost_bps),
                "interpretation": "unverified_stress_axis_not_realistic_executable_cost_envelope",
                "application": "round_trip_bps_times_standard_turnover",
                "standard_turnover": "sum_absolute_weight_change_including_cash_divided_by_two",
            },
            "deterministic_naive_controls": list(_NAIVE_CONTROL_IDS),
            "validation_kill_tests": {
                "no_signal": (
                    "candidate_primary_cost_total_return_bps_not_strictly_above_"
                    "equal_weight_all_hygiene_eligible"
                ),
                "no_robustness": (
                    "candidate_total_return_bps_not_strictly_above_"
                    "equal_weight_all_hygiene_eligible_at_every_fixed_cost"
                ),
            },
            "cpu_only": True,
            "gpu_used": False,
            "model_training_used": False,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1CrossSectionalMomentumInput:
    """Pure in-memory completed-D1 input with source-safe immutable lineage."""

    dataset_hash: str
    source_index_hash: str
    panel_manifest_sha256: str
    materialization_receipt_sha256: str
    geometry_audit_receipt_sha256: str
    geometry_audit_contract_sha256: str
    geometry_audit_source_grid_sha256: str
    geometry_audit_event_mask_sha256: str
    target_key_set_hash: str
    full_target_count: int
    coverage_eligible_target_count: int
    raw_byte_attested_target_count: int
    grid_bars_by_target: Mapping[str, Sequence[Bar]]
    terminal_execution_bars_by_target: Mapping[str, Bar]
    event_availability_by_lookback: Mapping[int, Mapping[str, Sequence[bool]]]
    limitations: tuple[str, ...]
    dataset_id: str = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_DATASET_ID
    adjustment_mode: str = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ADJUSTMENT_MODE
    current_listing_only: bool = True
    non_pit: bool = True
    corporate_action_qualified: bool = False
    session_finality_attested: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        streams = {
            key: tuple(values)
            for key, values in self.grid_bars_by_target.items()
        }
        terminal_bars = dict(self.terminal_execution_bars_by_target)
        availability = {
            lookback: {
                target_key: tuple(flags)
                for target_key, flags in values.items()
            }
            for lookback, values in self.event_availability_by_lookback.items()
        }
        if not streams:
            raise KisBroadD1CrossSectionalMomentumInputUnavailable("no_target_streams")
        if (
            self.dataset_id != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_DATASET_ID
            or self.adjustment_mode != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ADJUSTMENT_MODE
            or self.current_listing_only is not True
            or self.non_pit is not True
            or self.corporate_action_qualified is not False
            or self.session_finality_attested is not False
            or self.schema_version != SCHEMA_VERSION
            or any(
                not _is_sha256(value)
                for value in (
                    self.dataset_hash,
                    self.source_index_hash,
                    self.panel_manifest_sha256,
                    self.materialization_receipt_sha256,
                    self.geometry_audit_receipt_sha256,
                    self.geometry_audit_contract_sha256,
                    self.geometry_audit_source_grid_sha256,
                    self.geometry_audit_event_mask_sha256,
                    self.target_key_set_hash,
                )
            )
            or self.full_target_count < len(streams)
            or self.coverage_eligible_target_count < len(streams)
            or self.coverage_eligible_target_count > self.full_target_count
            or self.raw_byte_attested_target_count < len(streams)
            or self.raw_byte_attested_target_count > self.full_target_count
            or len(streams) < KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TOP_K
            or any(not isinstance(key, str) or not key.strip() for key in streams)
            or self.target_key_set_hash != _target_key_set_hash(tuple(sorted(streams)))
            or set(terminal_bars) != set(streams)
            or set(availability) != set(KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS)
            or not self.limitations
            or any(
                not isinstance(value, str) or not value.strip() for value in self.limitations
            )
            or "alternate_daily_representation_semantics_unproven" not in self.limitations
        ):
            raise ValueError("KIS broad D1 cross-sectional momentum input is invalid")

        first_key = min(streams)
        first_stream = streams[first_key]
        if len(first_stream) != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_SESSION_COUNT:
            raise KisBroadD1CrossSectionalMomentumInputUnavailable(
                "common_session_count_unavailable"
            )
        common_sessions = tuple(bar.start_ts for bar in first_stream)
        if tuple(sorted(common_sessions)) != common_sessions or len(set(common_sessions)) != len(
            common_sessions
        ):
            raise ValueError("KIS broad D1 momentum session grid is invalid")
        for target_key, stream in streams.items():
            terminal_bar = terminal_bars[target_key]
            event_flags = tuple(
                (bar.high / bar.low)
                > KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_MAX_HIGH_LOW_RATIO
                for bar in stream
            )
            if (
                len(stream) != len(common_sessions)
                or tuple(bar.start_ts for bar in stream) != common_sessions
                or any(
                    not isinstance(bar, Bar)
                    or bar.timeframe != Timeframe.D1
                    or not bar.complete
                    or not _valid_geometry(bar)
                    for bar in stream
                )
                or not isinstance(terminal_bar, Bar)
                or terminal_bar.timeframe != Timeframe.D1
                or not terminal_bar.complete
                or not _valid_geometry(terminal_bar)
                or terminal_bar.start_ts <= common_sessions[-1]
            ):
                raise ValueError(
                    "KIS broad D1 cross-sectional momentum streams are incompatible"
                )
            if not target_key:
                raise ValueError("KIS broad D1 momentum target key is invalid")
            for lookback in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS:
                if (
                    set(availability[lookback]) != set(streams)
                    or availability[lookback][target_key]
                    != _event_availability(event_flags, lookback)
                ):
                    raise ValueError("KIS broad D1 momentum availability is invalid")

        object.__setattr__(self, "grid_bars_by_target", MappingProxyType(streams))
        object.__setattr__(
            self,
            "terminal_execution_bars_by_target",
            MappingProxyType(terminal_bars),
        )
        object.__setattr__(
            self,
            "event_availability_by_lookback",
            MappingProxyType(
                {
                    lookback: MappingProxyType(availability[lookback])
                    for lookback in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS
                }
            ),
        )

    @property
    def target_count(self) -> int:
        return len(self.grid_bars_by_target)

    @property
    def common_sessions(self) -> tuple[datetime, ...]:
        first_stream = next(iter(self.grid_bars_by_target.values()))
        return tuple(bar.start_ts for bar in first_stream)

    @property
    def terminal_execution_session(self) -> datetime:
        return next(iter(self.terminal_execution_bars_by_target.values())).start_ts

    @property
    def common_session_hash(self) -> str:
        return _sha256_payload(
            {"sessions": [value.isoformat() for value in self.common_sessions]}
        )

    @property
    def input_bar_hash(self) -> str:
        return _sha256_bytes(
            json.dumps(
                {
                    target_key: [
                        {
                            "start": bar.start_ts.isoformat(),
                            "open": _decimal_text(bar.open),
                            "high": _decimal_text(bar.high),
                            "low": _decimal_text(bar.low),
                            "close": _decimal_text(bar.close),
                        }
                        for bar in self.grid_bars_by_target[target_key]
                    ]
                    for target_key in sorted(self.grid_bars_by_target)
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
        )

    def safe_source_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "source_index_hash": self.source_index_hash,
            "panel_manifest_sha256": self.panel_manifest_sha256,
            "materialization_receipt_sha256": self.materialization_receipt_sha256,
            "geometry_audit_receipt_sha256": self.geometry_audit_receipt_sha256,
            "geometry_audit_contract_sha256": self.geometry_audit_contract_sha256,
            "geometry_audit_source_grid_sha256": self.geometry_audit_source_grid_sha256,
            "geometry_audit_event_mask_sha256": self.geometry_audit_event_mask_sha256,
            "input_bar_hash": self.input_bar_hash,
            "target_key_set_hash": self.target_key_set_hash,
            "full_target_count": self.full_target_count,
            "coverage_eligible_target_count": self.coverage_eligible_target_count,
            "raw_byte_attested_target_count": self.raw_byte_attested_target_count,
            "target_count": self.target_count,
            "common_session_count": len(self.common_sessions),
            "common_session_hash": self.common_session_hash,
            "terminal_execution_session_hash": _sha256_payload(
                {"terminal_execution_session": self.terminal_execution_session.isoformat()}
            ),
            "timeframe": Timeframe.D1.value,
            "adjustment_mode": self.adjustment_mode,
            "current_listing_only": self.current_listing_only,
            "non_pit": self.non_pit,
            "corporate_action_qualified": self.corporate_action_qualified,
            "session_finality_attested": self.session_finality_attested,
            "source_mixing_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1CrossSectionalMomentumAggregate:
    """Aggregate-only diagnostic for one frozen rank or naive-control rule."""

    decision_slot_count: int
    signal_slot_count: int
    no_signal_slot_count: int
    total_gross_return_bps: Decimal
    total_stress_return_bps_by_round_trip_cost: Mapping[str, Decimal]
    mean_rebalance_turnover: Decimal
    terminal_liquidation_turnover: Decimal
    mean_concentration_hhi: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        costs = MappingProxyType(dict(self.total_stress_return_bps_by_round_trip_cost))
        if (
            self.decision_slot_count < 1
            or self.signal_slot_count < 0
            or self.no_signal_slot_count < 0
            or self.signal_slot_count + self.no_signal_slot_count != self.decision_slot_count
            or tuple(costs) != _COST_KEYS
            or self.schema_version != SCHEMA_VERSION
            or any(
                not _finite_decimal(value)
                for value in (
                    self.total_gross_return_bps,
                    self.mean_rebalance_turnover,
                    self.terminal_liquidation_turnover,
                    self.mean_concentration_hhi,
                    *costs.values(),
                )
            )
            or self.mean_rebalance_turnover < 0
            or self.terminal_liquidation_turnover < 0
            or self.mean_concentration_hhi < 0
            or self.mean_concentration_hhi > 1
        ):
            raise ValueError("KIS broad D1 momentum aggregate is invalid")
        object.__setattr__(self, "total_stress_return_bps_by_round_trip_cost", costs)

    def safe_payload(self) -> dict[str, object]:
        return {
            "decision_slot_count": self.decision_slot_count,
            "signal_slot_count": self.signal_slot_count,
            "no_signal_slot_count": self.no_signal_slot_count,
            "total_gross_return_bps": _decimal_text(self.total_gross_return_bps),
            "total_stress_return_bps_by_round_trip_cost": {
                cost: _decimal_text(value)
                for cost, value in self.total_stress_return_bps_by_round_trip_cost.items()
            },
            "mean_rebalance_turnover": _decimal_text(self.mean_rebalance_turnover),
            "terminal_liquidation_turnover": _decimal_text(self.terminal_liquidation_turnover),
            "mean_concentration_hhi": _decimal_text(self.mean_concentration_hhi),
        }


@dataclass(frozen=True, slots=True)
class KisBroadD1CrossSectionalMomentumCell:
    """One predeclared lookback and chronological phase without a selection action."""

    lookback_sessions: int
    phase: Literal["development", "validation"]
    status: Literal["evaluated", "input_unavailable"]
    decision_slot_count: int
    feature_hygiene_excluded_target_count: int
    candidate: KisBroadD1CrossSectionalMomentumAggregate | None
    naive_controls: Mapping[str, KisBroadD1CrossSectionalMomentumAggregate] | None
    no_signal_after_primary_control: bool | None
    no_robustness_across_cost_stress: bool | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        controls = (
            None
            if self.naive_controls is None
            else MappingProxyType(dict(self.naive_controls))
        )
        if (
            self.lookback_sessions not in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS
            or self.phase not in {"development", "validation"}
            or self.status not in {"evaluated", "input_unavailable"}
            or self.decision_slot_count < 1
            or self.feature_hygiene_excluded_target_count < 0
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS broad D1 momentum cell is invalid")
        if self.status == "input_unavailable":
            if (
                self.candidate is not None
                or controls is not None
                or self.no_signal_after_primary_control is not None
                or self.no_robustness_across_cost_stress is not None
            ):
                raise ValueError("KIS broad D1 unavailable cell must not contain results")
        elif (
            self.candidate is None
            or controls is None
            or tuple(controls) != _NAIVE_CONTROL_IDS
            or self.candidate.decision_slot_count != self.decision_slot_count
            or any(
                value.decision_slot_count != self.decision_slot_count
                for value in controls.values()
            )
            or (self.phase == "validation")
            != (
                self.no_signal_after_primary_control is not None
                and self.no_robustness_across_cost_stress is not None
            )
        ):
            raise ValueError("KIS broad D1 evaluated cell is invalid")
        object.__setattr__(self, "naive_controls", controls)

    def safe_payload(self) -> dict[str, object]:
        result: dict[str, object] = {
            "lookback_sessions": self.lookback_sessions,
            "phase": self.phase,
            "status": self.status,
            "decision_slot_count": self.decision_slot_count,
            "feature_hygiene_excluded_target_count": self.feature_hygiene_excluded_target_count,
        }
        if self.status == "input_unavailable":
            return result
        assert self.candidate is not None
        assert self.naive_controls is not None
        result["candidate"] = self.candidate.safe_payload()
        result["naive_controls"] = {
            name: value.safe_payload() for name, value in self.naive_controls.items()
        }
        result["validation_kill_tests"] = (
            {"status": "development_not_interpreted_for_selection"}
            if self.phase == "development"
            else {
                "no_signal_after_primary_control": self.no_signal_after_primary_control,
                "no_robustness_across_cost_stress": self.no_robustness_across_cost_stress,
                "selection_action": "none",
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class KisBroadD1CrossSectionalMomentumRun:
    """One immutable external precommit/summary receipt pair or no-input summary."""

    status: Literal["completed", "input_unavailable"]
    run_directory: Path
    receipt_path: Path
    receipt_sha256: str
    precommit_path: Path | None
    precommit_sha256: str | None
    campaign_contract_hash: str | None
    cells: tuple[KisBroadD1CrossSectionalMomentumCell, ...] | None

    def __post_init__(self) -> None:
        completed = self.status == "completed"
        if (
            self.status not in {"completed", "input_unavailable"}
            or not self.run_directory.is_dir()
            or not self.receipt_path.is_file()
            or not _is_sha256(self.receipt_sha256)
            or _sha256_file(self.receipt_path) != self.receipt_sha256
            or completed != (self.precommit_path is not None)
            or completed != (self.precommit_sha256 is not None)
            or completed != (self.campaign_contract_hash is not None)
            or completed != (self.cells is not None)
            or (
                self.precommit_path is not None
                and (
                    not self.precommit_path.is_file()
                    or self.precommit_sha256 is None
                    or _sha256_file(self.precommit_path) != self.precommit_sha256
                )
            )
            or (
                self.campaign_contract_hash is not None
                and not _is_sha256(self.campaign_contract_hash)
            )
        ):
            raise ValueError("KIS broad D1 momentum run is invalid")


def validate_kis_broad_d1_cross_sectional_momentum_artifact_root(
    artifact_root: Path | str,
    *,
    repo_root: Path | str | None = None,
) -> Path:
    """Validate the external receipt parent before a runner opens source input."""

    return ensure_external_artifact_directory(
        Path(artifact_root),
        _repository_root(repo_root),
        "research",
        KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID,
    )


def run_kis_broad_d1_cross_sectional_momentum(
    *,
    source_input: KisBroadD1CrossSectionalMomentumInput | None,
    execution_parity: Mapping[str, object] | None = None,
    artifact_root: Path | str = KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ARTIFACT_ROOT,
    run_label: str,
    review_status: str = "not_required_before_outcome",
    input_unavailable_reason: str | None = None,
    repo_root: Path | str | None = None,
    spec: KisBroadD1CrossSectionalMomentumSpec | None = None,
) -> KisBroadD1CrossSectionalMomentumRun:
    """Write one frozen aggregate benchmark or a categorical no-input receipt."""

    if not _SAFE_RUN_LABEL.fullmatch(run_label):
        raise ValueError("KIS broad D1 momentum run label is invalid")
    if review_status not in _ALLOWED_REVIEW_STATUSES:
        raise ValueError("KIS broad D1 momentum review status is invalid")
    resolved_spec = spec or KisBroadD1CrossSectionalMomentumSpec()
    output_directory = _prepare_output_directory(
        artifact_root=Path(artifact_root),
        repo_root=_repository_root(repo_root),
        run_label=run_label,
    )
    if source_input is None:
        if execution_parity is not None:
            raise ValueError("KIS broad D1 momentum unavailable input has execution parity")
        reason = input_unavailable_reason or "data_input_unavailable"
        if not _SAFE_UNAVAILABLE_REASON.fullmatch(reason):
            raise ValueError("KIS broad D1 momentum unavailable reason is invalid")
        receipt_path = output_directory / "summary.json"
        receipt_sha256 = _write_json_new(
            receipt_path,
            _input_unavailable_payload(
                reason=reason,
                review_status=review_status,
                spec=resolved_spec,
            ),
        )
        return KisBroadD1CrossSectionalMomentumRun(
            status="input_unavailable",
            run_directory=output_directory,
            receipt_path=receipt_path,
            receipt_sha256=receipt_sha256,
            precommit_path=None,
            precommit_sha256=None,
            campaign_contract_hash=None,
            cells=None,
        )
    if input_unavailable_reason is not None:
        raise ValueError("KIS broad D1 momentum input and unavailable reason conflict")
    if not isinstance(source_input, KisBroadD1CrossSectionalMomentumInput):
        raise TypeError("KIS broad D1 momentum requires its exact input type")
    execution_semantics = _validated_execution_parity_payload(
        execution_parity,
        source_input=source_input,
    )

    precommit_payload = _precommit_payload(
        source_input,
        resolved_spec,
        review_status=review_status,
        execution_semantics=execution_semantics,
    )
    campaign_contract_hash = _sha256_payload(precommit_payload)
    precommit_path = output_directory / "precommit.json"
    precommit_sha256 = _write_json_new(
        precommit_path,
        {
            **precommit_payload,
            "campaign_contract_hash": campaign_contract_hash,
        },
    )
    cells = _evaluate_cells(source_input, resolved_spec)
    receipt_path = output_directory / "summary.json"
    receipt_sha256 = _write_json_new(
        receipt_path,
        _summary_payload(
            source_input,
            spec=resolved_spec,
            campaign_contract_hash=campaign_contract_hash,
            precommit_sha256=precommit_sha256,
            review_status=review_status,
            cells=cells,
            execution_semantics=execution_semantics,
        ),
    )
    return KisBroadD1CrossSectionalMomentumRun(
        status="completed",
        run_directory=output_directory,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        precommit_path=precommit_path,
        precommit_sha256=precommit_sha256,
        campaign_contract_hash=campaign_contract_hash,
        cells=cells,
    )


def _evaluate_cells(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    spec: KisBroadD1CrossSectionalMomentumSpec,
) -> tuple[KisBroadD1CrossSectionalMomentumCell, ...]:
    return tuple(
        _evaluate_cell(source_input, spec=spec, lookback=lookback, phase=phase)
        for lookback in spec.lookbacks
        for phase in ("development", "validation")
    )


def _evaluate_cell(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    *,
    spec: KisBroadD1CrossSectionalMomentumSpec,
    lookback: int,
    phase: Literal["development", "validation"],
) -> KisBroadD1CrossSectionalMomentumCell:
    decision_indices = tuple(_decision_indices(spec, lookback=lookback, phase=phase))
    accumulators = {
        "candidate": _PortfolioAccumulator(),
        **{name: _PortfolioAccumulator() for name in _NAIVE_CONTROL_IDS},
    }
    previous_weights: dict[str, Mapping[str, Decimal]] = {
        name: {} for name in accumulators
    }
    feature_hygiene_excluded_target_count = 0

    for index in decision_indices:
        eligible_scores = _eligible_scores(source_input, index=index, lookback=lookback)
        feature_hygiene_excluded_target_count += source_input.target_count - len(eligible_scores)
        can_signal = len(eligible_scores) >= spec.top_k
        weights_by_rule = _weights_by_rule(
            eligible_scores,
            top_k=spec.top_k,
            can_signal=can_signal,
        )
        returns = _future_open_returns(source_input, index=index)
        for rule_id, weights in weights_by_rule.items():
            accumulator = accumulators[rule_id]
            turnover = _turnover(previous_weights[rule_id], weights)
            accumulator.add(
                gross_return=_weighted_return(weights, returns),
                turnover=turnover,
                concentration_hhi=_concentration_hhi(weights),
                signaled=bool(weights),
            )
            previous_weights[rule_id] = weights

    for rule_id, accumulator in accumulators.items():
        accumulator.close(previous_weights[rule_id])

    candidate = _aggregate_from(accumulators["candidate"])
    if candidate is None:
        return KisBroadD1CrossSectionalMomentumCell(
            lookback_sessions=lookback,
            phase=phase,
            status="input_unavailable",
            decision_slot_count=len(decision_indices),
            feature_hygiene_excluded_target_count=feature_hygiene_excluded_target_count,
            candidate=None,
            naive_controls=None,
            no_signal_after_primary_control=None,
            no_robustness_across_cost_stress=None,
        )
    controls = {
        name: _aggregate_from(
            accumulators[name],
            allow_flat=name == "always_flat",
        )
        for name in _NAIVE_CONTROL_IDS
    }
    if any(value is None for value in controls.values()):
        raise RuntimeError("KIS broad D1 momentum control aggregate is unavailable")
    typed_controls = {
        name: value for name, value in controls.items() if value is not None
    }
    no_signal, no_robustness = _validation_kill_tests(
        candidate,
        typed_controls["equal_weight_all_hygiene_eligible"],
        phase=phase,
    )
    return KisBroadD1CrossSectionalMomentumCell(
        lookback_sessions=lookback,
        phase=phase,
        status="evaluated",
        decision_slot_count=len(decision_indices),
        feature_hygiene_excluded_target_count=feature_hygiene_excluded_target_count,
        candidate=candidate,
        naive_controls=typed_controls,
        no_signal_after_primary_control=no_signal,
        no_robustness_across_cost_stress=no_robustness,
    )


def _decision_indices(
    spec: KisBroadD1CrossSectionalMomentumSpec,
    *,
    lookback: int,
    phase: Literal["development", "validation"],
) -> range:
    phase_start, phase_end = {
        "development": (0, spec.development_session_count),
        "validation": (
            spec.development_session_count + spec.purge_session_count,
            KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_SESSION_COUNT,
        ),
    }[phase]
    start = phase_start + lookback
    stop = phase_end - 1 if phase == "development" else phase_end
    if stop <= start:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("phase_coverage_unavailable")
    return range(start, stop)


def _eligible_scores(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    *,
    index: int,
    lookback: int,
) -> dict[str, Decimal]:
    eligible: dict[str, Decimal] = {}
    availability = source_input.event_availability_by_lookback[lookback]
    for target_key in sorted(source_input.grid_bars_by_target):
        bars = source_input.grid_bars_by_target[target_key]
        if not availability[target_key][index]:
            continue
        eligible[target_key] = (
            bars[index].close / bars[index - lookback + 1].close
        ) - Decimal("1")
    return eligible


def _completed_feature_window_is_clean(
    bars: Sequence[Bar],
    *,
    decision_index: int,
    lookback: int,
) -> bool:
    return not any(
        (bars[index].high / bars[index].low)
        > KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_MAX_HIGH_LOW_RATIO
        for index in range(decision_index - lookback + 1, decision_index + 1)
    )


def _event_availability(events: Sequence[bool], lookback: int) -> tuple[bool, ...]:
    if lookback not in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS:
        raise ValueError("KIS broad D1 momentum lookback is not frozen")
    return tuple(
        index >= lookback and not any(events[index - lookback + 1 : index + 1])
        for index in range(len(events))
    )


def _future_open_returns(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    *,
    index: int,
) -> dict[str, Decimal]:
    return {
        target_key: (
            _execution_bar_for(source_input, target_key=target_key, index=index).close
            / _execution_bar_for(source_input, target_key=target_key, index=index).open
        )
        - Decimal("1")
        for target_key in source_input.grid_bars_by_target
    }


def _execution_bar_for(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    *,
    target_key: str,
    index: int,
) -> Bar:
    next_index = index + 1
    if next_index < KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_SESSION_COUNT:
        return source_input.grid_bars_by_target[target_key][next_index]
    return source_input.terminal_execution_bars_by_target[target_key]


def _weights_by_rule(
    eligible_scores: Mapping[str, Decimal],
    *,
    top_k: int,
    can_signal: bool,
) -> Mapping[str, Mapping[str, Decimal]]:
    if not can_signal:
        return {
            "candidate": {},
            "always_flat": {},
            "equal_weight_all_hygiene_eligible": {},
            "lexicographic_top_k_hygiene_eligible": {},
        }
    sorted_by_score = tuple(
        target_key
        for target_key, _score in sorted(
            eligible_scores.items(), key=lambda item: (-item[1], item[0])
        )[:top_k]
    )
    sorted_keys = tuple(sorted(eligible_scores))
    return {
        "candidate": _equal_weights(sorted_by_score),
        "always_flat": {},
        "equal_weight_all_hygiene_eligible": _equal_weights(sorted_keys),
        "lexicographic_top_k_hygiene_eligible": _equal_weights(sorted_keys[:top_k]),
    }


def _equal_weights(target_keys: Sequence[str]) -> Mapping[str, Decimal]:
    if not target_keys:
        return {}
    weight = Decimal("1") / Decimal(len(target_keys))
    return {target_key: weight for target_key in target_keys}


def _weighted_return(weights: Mapping[str, Decimal], returns: Mapping[str, Decimal]) -> Decimal:
    return sum(
        (weight * returns[target_key] for target_key, weight in weights.items()),
        Decimal("0"),
    )


def _turnover(
    previous: Mapping[str, Decimal], current: Mapping[str, Decimal]
) -> Decimal:
    asset_change = sum(
        (
            abs(current.get(target_key, Decimal("0")) - previous.get(target_key, Decimal("0")))
            for target_key in set(previous) | set(current)
        ),
        Decimal("0"),
    )
    previous_cash = Decimal("1") - sum(previous.values(), Decimal("0"))
    current_cash = Decimal("1") - sum(current.values(), Decimal("0"))
    return (asset_change + abs(current_cash - previous_cash)) / Decimal("2")


def _concentration_hhi(weights: Mapping[str, Decimal]) -> Decimal:
    return sum((value * value for value in weights.values()), Decimal("0"))


@dataclass(slots=True)
class _PortfolioAccumulator:
    decision_slot_count: int = 0
    signal_slot_count: int = 0
    gross_return: Decimal = Decimal("0")
    rebalance_turnover: Decimal = Decimal("0")
    terminal_liquidation_turnover: Decimal = Decimal("0")
    concentration_total: Decimal = Decimal("0")

    def add(
        self,
        *,
        gross_return: Decimal,
        turnover: Decimal,
        concentration_hhi: Decimal,
        signaled: bool,
    ) -> None:
        self.decision_slot_count += 1
        self.signal_slot_count += int(signaled)
        self.gross_return += gross_return
        self.rebalance_turnover += turnover
        self.concentration_total += concentration_hhi

    def close(self, weights: Mapping[str, Decimal]) -> None:
        self.terminal_liquidation_turnover = _turnover(weights, {})


def _aggregate_from(
    accumulator: _PortfolioAccumulator,
    *,
    allow_flat: bool = False,
) -> KisBroadD1CrossSectionalMomentumAggregate | None:
    if accumulator.signal_slot_count == 0 and not allow_flat:
        return None
    total_turnover = (
        accumulator.rebalance_turnover + accumulator.terminal_liquidation_turnover
    )
    gross_bps = accumulator.gross_return * Decimal("10000")
    net_by_cost = {
        cost_key: gross_bps - (cost * total_turnover)
        for cost_key, cost in zip(
            _COST_KEYS,
            KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ROUND_TRIP_COST_BPS,
            strict=True,
        )
    }
    return KisBroadD1CrossSectionalMomentumAggregate(
        decision_slot_count=accumulator.decision_slot_count,
        signal_slot_count=accumulator.signal_slot_count,
        no_signal_slot_count=(
            accumulator.decision_slot_count - accumulator.signal_slot_count
        ),
        total_gross_return_bps=gross_bps,
        total_stress_return_bps_by_round_trip_cost=net_by_cost,
        mean_rebalance_turnover=(
            accumulator.rebalance_turnover / Decimal(accumulator.decision_slot_count)
        ),
        terminal_liquidation_turnover=accumulator.terminal_liquidation_turnover,
        mean_concentration_hhi=(
            accumulator.concentration_total / Decimal(accumulator.decision_slot_count)
        ),
    )


def _validation_kill_tests(
    candidate: KisBroadD1CrossSectionalMomentumAggregate,
    equal_weight_control: KisBroadD1CrossSectionalMomentumAggregate,
    *,
    phase: Literal["development", "validation"],
) -> tuple[bool | None, bool | None]:
    if phase == "development":
        return None, None
    primary_key = _decimal_text(KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_PRIMARY_COST_BPS)
    no_signal = (
        candidate.total_stress_return_bps_by_round_trip_cost[primary_key]
        <= equal_weight_control.total_stress_return_bps_by_round_trip_cost[primary_key]
    )
    no_robustness = any(
        candidate.total_stress_return_bps_by_round_trip_cost[cost]
        <= equal_weight_control.total_stress_return_bps_by_round_trip_cost[cost]
        for cost in _COST_KEYS
    )
    return no_signal, no_robustness


def _validated_execution_parity_payload(
    value: Mapping[str, object] | None,
    *,
    source_input: KisBroadD1CrossSectionalMomentumInput,
) -> dict[str, object]:
    """Require the separately-owned replay-parity contract before evaluation."""

    if not isinstance(value, Mapping):
        raise ValueError("KIS broad D1 momentum requires an execution parity attestation")
    payload = dict(value)
    expected = {
        "input_contract_ref": source_input.input_bar_hash,
        "source_limitations": list(source_input.limitations),
        "timing": {
            "rule": "completed_d1_t_to_next_observed_d1_open",
            "next_observed_execution_bar_attested": True,
            "semantic_representability": "represented",
            "executable_or_paper_eligibility": "not_evaluated_by_semantic_attestation",
        },
        "round_trip_stress": {
            "bps": [
                _decimal_text(value)
                for value in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ROUND_TRIP_COST_BPS
            ],
            "status": "research_accounting_assumption_not_verified_fill_cost_or_liquidity_model",
        },
    }
    if payload != expected:
        raise ValueError("KIS broad D1 momentum execution parity attestation is invalid")
    return expected


def _precommit_payload(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    spec: KisBroadD1CrossSectionalMomentumSpec,
    *,
    review_status: str,
    execution_semantics: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID,
        "status": "precommitted",
        "claim": (
            "one frozen source-local CPU cross-sectional momentum benchmark; aggregate "
            "research diagnostics only, never a winner, profitability, PnL, Paper, "
            "promotion, ensemble, or live claim"
        ),
        "source": source_input.safe_source_payload(),
        "source_limitations": list(source_input.limitations),
        "spec": spec.safe_payload(),
        "execution_semantics": dict(execution_semantics),
        "review": {
            "reviewer": "claude_cli_falsification_first",
            "status": review_status,
            "required_before_result_interpretation": "unexpectedly_strong_or_depth_boundary_only",
        },
        "permissions": _permission_payload(),
        "promotion": _promotion_payload(),
        "artifact_policy": _artifact_policy(),
    }


def _summary_payload(
    source_input: KisBroadD1CrossSectionalMomentumInput,
    *,
    spec: KisBroadD1CrossSectionalMomentumSpec,
    campaign_contract_hash: str,
    precommit_sha256: str,
    review_status: str,
    cells: tuple[KisBroadD1CrossSectionalMomentumCell, ...],
    execution_semantics: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID,
        "status": "completed",
        "campaign_contract_hash": campaign_contract_hash,
        "precommit_sha256": precommit_sha256,
        "claim": (
            "source-local non-promoting aggregate benchmark evidence only; output does "
            "not select a winner or make a profitability, PnL, Paper, promotion, "
            "ensemble, or live claim"
        ),
        "source": source_input.safe_source_payload(),
        "source_limitations": list(source_input.limitations),
        "spec": spec.safe_payload(),
        "execution_semantics": dict(execution_semantics),
        "review_status": review_status,
        "cells": [cell.safe_payload() for cell in cells],
        "selection": {
            "winner_selected": False,
            "promotion_allowed": False,
            "paper_input_allowed": False,
            "sealed_holdout_accessed": False,
        },
        "permissions": _permission_payload(),
        "artifact_policy": _artifact_policy(),
    }


def _input_unavailable_payload(
    *,
    reason: str,
    review_status: str,
    spec: KisBroadD1CrossSectionalMomentumSpec,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID,
        "status": "input_unavailable",
        "reason": reason,
        "claim": "no source input was evaluated and no strategy result exists",
        "source_limitations": list(_INPUT_UNAVAILABLE_LIMITATIONS),
        "spec": spec.safe_payload(),
        "review_status": review_status,
        "selection": {
            "winner_selected": False,
            "promotion_allowed": False,
            "paper_input_allowed": False,
            "sealed_holdout_accessed": False,
        },
        "permissions": _permission_payload(),
        "artifact_policy": _artifact_policy(),
    }


def _permission_payload() -> dict[str, bool]:
    return {
        "network_access": False,
        "credentials_read": False,
        "kis_accessed": False,
        "broker_access": False,
        "order_access": False,
        "gpu_used": False,
        "sealed_holdout_accessed": False,
    }


def _promotion_payload() -> dict[str, bool]:
    return {
        "winner_selection_allowed": False,
        "profitability_claim_allowed": False,
        "pnl_claim_allowed": False,
        "paper_input_allowed": False,
        "promotion_allowed": False,
        "ensemble_allowed": False,
        "live_allowed": False,
    }


def _artifact_policy() -> dict[str, bool]:
    return {
        "external_artifact_only": True,
        "raw_bars_persisted": False,
        "raw_rows_persisted": False,
        "symbols_persisted": False,
        "prices_persisted": False,
        "weights_persisted": False,
        "predictions_persisted": False,
        "model_artifacts_persisted": False,
    }


def _prepare_output_directory(
    *,
    artifact_root: Path,
    repo_root: Path,
    run_label: str,
) -> Path:
    root = validate_kis_broad_d1_cross_sectional_momentum_artifact_root(
        artifact_root,
        repo_root=repo_root,
    )
    destination = root / run_label
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("KIS broad D1 momentum artifact already exists")
    destination.mkdir()
    resolved = destination.resolve(strict=True)
    if resolved != destination or not resolved.is_relative_to(root):
        raise ValueError("KIS broad D1 momentum artifact path is invalid")
    return resolved


def _write_json_new(path: Path, payload: Mapping[str, object]) -> str:
    _assert_source_safe_document(payload)
    encoded = (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
    try:
        descriptor = os.open(
            str(path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FileExistsError("KIS broad D1 momentum artifact is immutable") from error
    try:
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("KIS broad D1 momentum artifact write failed")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return _sha256_bytes(encoded)


def _assert_source_safe_document(value: object) -> None:
    forbidden = {
        "bar",
        "bars",
        "symbol",
        "symbols",
        "price",
        "prices",
        "open",
        "high",
        "low",
        "close",
        "weight",
        "weights",
        "prediction",
        "predictions",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in forbidden:
                raise ValueError("KIS broad D1 momentum artifact contains source values")
            _assert_source_safe_document(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            _assert_source_safe_document(nested)


def _repository_root(value: Path | str | None) -> Path:
    return Path(value).resolve() if value is not None else _MODULE_REPOSITORY_ROOT


def _valid_geometry(bar: Bar) -> bool:
    return (
        bar.open.is_finite()
        and bar.high.is_finite()
        and bar.low.is_finite()
        and bar.close.is_finite()
        and bar.open > 0
        and bar.high > 0
        and bar.low > 0
        and bar.close > 0
        and bar.high >= max(bar.open, bar.close)
        and bar.low <= min(bar.open, bar.close)
    )


def _target_key_set_hash(target_keys: Sequence[str]) -> str:
    # This identity is inherited from the materialized broad-panel contract.
    # Keep its canonical bytes stable rather than using receipt JSON formatting.
    return _sha256_bytes(
        (
            json.dumps(
                {"target_keys": list(sorted(target_keys))},
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _finite_decimal(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    )


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True

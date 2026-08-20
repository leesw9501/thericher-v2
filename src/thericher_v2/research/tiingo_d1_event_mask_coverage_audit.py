"""Aggregate-only audit of the frozen Tiingo D1 rotation exclusion masks.

The audit recomputes the exact event and discontinuity predicates used by the
completed rotation while retaining only counts, hashes, and run-length buckets.
It cannot change the frozen research contract or create a performance claim.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION
from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
)
from thericher_v2.research import tiingo_d1_trend_mean_reversion_rotation as rotation

TIINGO_D1_EVENT_MASK_COVERAGE_AUDIT_ID = "tiingo-d1-event-mask-coverage-audit-v1"
_EXPECTED_ROTATION_REASON = "insufficient_validation_active_decisions"
_RUN_BUCKETS = ("1", "2_to_5", "6_to_20", "21_to_60", "over_60")

AuditStatus = Literal["consistent", "semantic_contradiction"]


@dataclass(frozen=True, slots=True)
class TiingoD1EventMaskCoveragePhase:
    """One phase's aggregate mask coverage without decision dates or values."""

    phase: Literal["development", "validation"]
    scheduled_decision_count: int
    event_any_count: int
    discontinuity_any_count: int
    overlap_count: int
    event_priority_excluded_count: int
    discontinuity_only_excluded_count: int
    either_excluded_count: int
    unmasked_count: int
    per_symbol: Mapping[str, Mapping[str, int]]
    event_index_set_hash: str
    discontinuity_index_set_hash: str
    overlap_index_set_hash: str
    either_index_set_hash: str
    excluded_run_length_buckets: Mapping[str, int]

    def __post_init__(self) -> None:
        values = (
            self.scheduled_decision_count,
            self.event_any_count,
            self.discontinuity_any_count,
            self.overlap_count,
            self.event_priority_excluded_count,
            self.discontinuity_only_excluded_count,
            self.either_excluded_count,
            self.unmasked_count,
        )
        normalized_per_symbol = {
            symbol: dict(value) for symbol, value in self.per_symbol.items()
        }
        normalized_buckets = dict(self.excluded_run_length_buckets)
        if (
            self.phase not in {"development", "validation"}
            or min(values) < 0
            or set(normalized_per_symbol) != set(TIINGO_ETF_D1_SYMBOLS)
            or any(
                set(value) != {"event_any_count", "discontinuity_any_count", "overlap_count"}
                or any(not isinstance(count, int) or count < 0 for count in value.values())
                or value["overlap_count"] > value["event_any_count"]
                or value["overlap_count"] > value["discontinuity_any_count"]
                for value in normalized_per_symbol.values()
            )
            or self.overlap_count > self.event_any_count
            or self.overlap_count > self.discontinuity_any_count
            or self.event_priority_excluded_count != self.event_any_count
            or self.discontinuity_only_excluded_count
            != self.discontinuity_any_count - self.overlap_count
            or self.either_excluded_count
            != self.event_any_count
            + self.discontinuity_any_count
            - self.overlap_count
            or self.unmasked_count != self.scheduled_decision_count - self.either_excluded_count
            or tuple(normalized_buckets) != _RUN_BUCKETS
            or any(not isinstance(count, int) or count < 0 for count in normalized_buckets.values())
            or any(
                not _is_sha256(value)
                for value in (
                    self.event_index_set_hash,
                    self.discontinuity_index_set_hash,
                    self.overlap_index_set_hash,
                    self.either_index_set_hash,
                )
            )
        ):
            raise ValueError("Tiingo D1 event-mask coverage phase is invalid")
        object.__setattr__(self, "per_symbol", MappingProxyType(normalized_per_symbol))
        object.__setattr__(
            self,
            "excluded_run_length_buckets",
            MappingProxyType(normalized_buckets),
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "scheduled_decision_count": self.scheduled_decision_count,
            "event_any_count": self.event_any_count,
            "discontinuity_any_count": self.discontinuity_any_count,
            "overlap_count": self.overlap_count,
            "event_priority_excluded_count": self.event_priority_excluded_count,
            "discontinuity_only_excluded_count": self.discontinuity_only_excluded_count,
            "either_excluded_count": self.either_excluded_count,
            "unmasked_count": self.unmasked_count,
            "per_symbol": {
                symbol: dict(self.per_symbol[symbol]) for symbol in TIINGO_ETF_D1_SYMBOLS
            },
            "index_set_hashes": {
                "event_any": self.event_index_set_hash,
                "discontinuity_any": self.discontinuity_index_set_hash,
                "overlap": self.overlap_index_set_hash,
                "either": self.either_index_set_hash,
            },
            "excluded_run_length_buckets": dict(self.excluded_run_length_buckets),
        }


@dataclass(frozen=True, slots=True)
class TiingoD1EventMaskCoverageAudit:
    """Frozen rotation evidence plus aggregate mask coverage."""

    source_payload: Mapping[str, object]
    rotation_precommit_hash: str
    rotation_summary_sha256: str
    rotation_validation_sha256: str
    rotation_input_hash: str
    rotation_status: str
    rotation_reason: str | None
    phases: tuple[TiingoD1EventMaskCoveragePhase, ...]
    status: AuditStatus
    contradiction_codes: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "phases", tuple(self.phases))
        object.__setattr__(self, "contradiction_codes", tuple(self.contradiction_codes))
        allowed_codes = {
            "development_phase_count_binding",
            "validation_phase_count_binding",
        }
        if (
            not isinstance(self.source_payload, Mapping)
            or not _is_sha256(self.rotation_precommit_hash)
            or not _is_sha256(self.rotation_summary_sha256)
            or not _is_sha256(self.rotation_validation_sha256)
            or not _is_sha256(self.rotation_input_hash)
            or self.rotation_status != "input_unavailable"
            or self.rotation_reason != _EXPECTED_ROTATION_REASON
            or tuple(phase.phase for phase in self.phases) != ("development", "validation")
            or any(code not in allowed_codes for code in self.contradiction_codes)
            or (self.status == "consistent") != (not self.contradiction_codes)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("Tiingo D1 event-mask coverage audit is invalid")
        object.__setattr__(self, "source_payload", MappingProxyType(dict(self.source_payload)))

    def precommit_payload(self, *, rotation_run_label: str) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "audit_id": TIINGO_D1_EVENT_MASK_COVERAGE_AUDIT_ID,
            "rotation": {
                "campaign_id": rotation.TIINGO_D1_TREND_MEAN_REVERSION_ROTATION_ID,
                "run_label": rotation_run_label,
                "precommit_hash": self.rotation_precommit_hash,
                "summary_sha256": self.rotation_summary_sha256,
                "validation_sha256": self.rotation_validation_sha256,
                "input_hash": self.rotation_input_hash,
                "status": self.rotation_status,
                "reason": self.rotation_reason,
            },
            "source": dict(self.source_payload),
            "frozen_mask_contract": {
                "event": "any_fixed_universe_dividend_or_split_t_minus_60_through_t",
                "discontinuity": (
                    "any_fixed_universe_absolute_close_return_over_20pct_t_minus_60_through_t"
                ),
                "priority": "event_before_feature_discontinuity",
                "target_day_masking": "prohibited",
            },
            "output_contract": {
                "aggregate_counts_only": True,
                "deterministic_set_hashes_only": True,
                "bounded_run_length_buckets_only": True,
                "raw_market_data_written": False,
                "performance_claim_allowed": False,
                "promotion_allowed": False,
                "gpu_eligible": False,
                "paper_input_allowed": False,
            },
        }

    def summary_payload(self, *, precommit_hash: str) -> dict[str, object]:
        return {
            "precommit_hash": precommit_hash,
            "audit": {
                "schema_version": self.schema_version,
                "audit_id": TIINGO_D1_EVENT_MASK_COVERAGE_AUDIT_ID,
                "status": self.status,
                "contradiction_codes": list(self.contradiction_codes),
                "phases": [phase.safe_payload() for phase in self.phases],
                "rotation_phase_count_binding": {
                    "development": (
                        "matched"
                        if "development_phase_count_binding" not in self.contradiction_codes
                        else "mismatch"
                    ),
                    "validation": (
                        "matched"
                        if "validation_phase_count_binding" not in self.contradiction_codes
                        else "mismatch"
                    ),
                },
                "raw_market_data_written": False,
                "performance_claim_allowed": False,
                "promotion_allowed": False,
                "gpu_eligible": False,
                "paper_input_allowed": False,
            },
        }


@dataclass(frozen=True, slots=True)
class TiingoD1EventMaskCoverageAuditRun:
    """External precommit and aggregate summary locations for one audit."""

    audit: TiingoD1EventMaskCoverageAudit
    precommit_path: Path
    precommit_hash: str
    summary_path: Path

    def __post_init__(self) -> None:
        if not _is_sha256(self.precommit_hash):
            raise ValueError("Tiingo D1 event-mask coverage precommit is invalid")


@dataclass(frozen=True, slots=True)
class TiingoD1EventMaskCoverageAuditValidationReceipt:
    """Independent reattachment receipt for one aggregate-only audit."""

    status: Literal["verified"]
    validation_path: Path
    precommit_hash: str
    rotation_precommit_hash: str

    def __post_init__(self) -> None:
        if (
            self.status != "verified"
            or not _is_sha256(self.precommit_hash)
            or not _is_sha256(self.rotation_precommit_hash)
        ):
            raise ValueError("Tiingo D1 event-mask coverage validation is invalid")


def prepare_tiingo_d1_event_mask_coverage_audit(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    rotation_artifact_root: Path | str,
    rotation_run_label: str,
    repo_root: Path | str,
) -> TiingoD1EventMaskCoverageAudit:
    """Reattach the completed rotation, then recompute only aggregate masks."""

    if not isinstance(snapshot, LoadedTiingoEtfDailySnapshot):
        raise TypeError("Tiingo D1 event-mask coverage audit requires a verified snapshot")
    binding = rotation.reattach_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=rotation_artifact_root,
        run_label=rotation_run_label,
        repo_root=repo_root,
    )
    prepared = rotation.prepare_tiingo_d1_trend_mean_reversion_rotation(snapshot)
    if (
        prepared.status != "input_unavailable"
        or prepared.reason != _EXPECTED_ROTATION_REASON
    ):
        raise ValueError("Tiingo D1 event-mask coverage audit rotation status is invalid")
    rows_by_symbol = _aligned_rows(snapshot)
    phase_indices = _decision_indices(
        common_session_count=prepared.common_session_count,
        config=prepared.config,
    )
    if phase_indices is None:
        raise ValueError("Tiingo D1 event-mask coverage audit decision shape is invalid")
    development_indices, validation_indices = phase_indices
    phases = (
        _phase_coverage(
            phase="development",
            indices=development_indices,
            rows_by_symbol=rows_by_symbol,
            config=prepared.config,
        ),
        _phase_coverage(
            phase="validation",
            indices=validation_indices,
            rows_by_symbol=rows_by_symbol,
            config=prepared.config,
        ),
    )
    contradictions = tuple(
        phase.phase + "_phase_count_binding"
        for phase, facts in zip(
            phases,
            (prepared.development, prepared.validation),
            strict=True,
        )
        if not _matches_rotation_phase(phase, facts)
    )
    artifact_dir = binding.validation_path.parent
    return TiingoD1EventMaskCoverageAudit(
        source_payload=prepared.source.safe_payload(),
        rotation_precommit_hash=binding.precommit_hash,
        rotation_summary_sha256=_sha256_bytes((artifact_dir / "summary.json").read_bytes()),
        rotation_validation_sha256=_sha256_bytes(binding.validation_path.read_bytes()),
        rotation_input_hash=prepared.input_hash,
        rotation_status="input_unavailable",
        rotation_reason=prepared.reason,
        phases=phases,
        status="consistent" if not contradictions else "semantic_contradiction",
        contradiction_codes=contradictions,
    )


def run_tiingo_d1_event_mask_coverage_audit(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    artifact_root: Path | str,
    rotation_artifact_root: Path | str,
    rotation_run_label: str,
    run_label: str,
    repo_root: Path | str,
) -> TiingoD1EventMaskCoverageAuditRun:
    """Write idempotent aggregate evidence outside the repository."""

    resolved_label = _validated_run_label(run_label)
    root = _external_artifact_root(Path(artifact_root), Path(repo_root))
    audit = prepare_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        rotation_artifact_root=rotation_artifact_root,
        rotation_run_label=rotation_run_label,
        repo_root=repo_root,
    )
    precommit_payload = audit.precommit_payload(rotation_run_label=rotation_run_label)
    precommit_hash = _sha256_json(precommit_payload)
    summary_payload = audit.summary_payload(precommit_hash=precommit_hash)
    artifact_dir = root / "data" / TIINGO_D1_EVENT_MASK_COVERAGE_AUDIT_ID / resolved_label
    _ensure_artifact_directory(root, artifact_dir)
    precommit_path = artifact_dir / "precommit.json"
    summary_path = artifact_dir / "summary.json"
    _write_or_verify(precommit_path, _canonical_json(precommit_payload))
    _write_or_verify(summary_path, _canonical_json(summary_payload))
    return TiingoD1EventMaskCoverageAuditRun(
        audit=audit,
        precommit_path=precommit_path,
        precommit_hash=precommit_hash,
        summary_path=summary_path,
    )


def validate_tiingo_d1_event_mask_coverage_audit(
    snapshot: LoadedTiingoEtfDailySnapshot,
    *,
    artifact_root: Path | str,
    rotation_artifact_root: Path | str,
    rotation_run_label: str,
    run_label: str,
    repo_root: Path | str,
) -> TiingoD1EventMaskCoverageAuditValidationReceipt:
    """Recompute and bind one aggregate-only audit receipt."""

    resolved_label = _validated_run_label(run_label)
    root = _external_artifact_root(Path(artifact_root), Path(repo_root))
    audit = prepare_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        rotation_artifact_root=rotation_artifact_root,
        rotation_run_label=rotation_run_label,
        repo_root=repo_root,
    )
    precommit_payload = audit.precommit_payload(rotation_run_label=rotation_run_label)
    precommit_hash = _sha256_json(precommit_payload)
    precommit_bytes = _canonical_json(precommit_payload)
    summary_bytes = _canonical_json(audit.summary_payload(precommit_hash=precommit_hash))
    artifact_dir = root / "data" / TIINGO_D1_EVENT_MASK_COVERAGE_AUDIT_ID / resolved_label
    _ensure_artifact_directory(root, artifact_dir)
    _require_matching_evidence(artifact_dir / "precommit.json", precommit_bytes)
    _require_matching_evidence(artifact_dir / "summary.json", summary_bytes)
    validation_path = artifact_dir / "validation.json"
    validation_payload = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": TIINGO_D1_EVENT_MASK_COVERAGE_AUDIT_ID,
        "status": "verified",
        "precommit_hash": precommit_hash,
        "precommit_sha256": _sha256_bytes(precommit_bytes),
        "summary_sha256": _sha256_bytes(summary_bytes),
        "rotation_precommit_hash": audit.rotation_precommit_hash,
        "rotation_summary_sha256": audit.rotation_summary_sha256,
        "rotation_validation_sha256": audit.rotation_validation_sha256,
        "source_reattached": True,
        "raw_market_data_written": False,
        "performance_claim_allowed": False,
        "promotion_allowed": False,
        "gpu_eligible": False,
        "paper_input_allowed": False,
    }
    _write_or_verify(validation_path, _canonical_json(validation_payload))
    return TiingoD1EventMaskCoverageAuditValidationReceipt(
        status="verified",
        validation_path=validation_path,
        precommit_hash=precommit_hash,
        rotation_precommit_hash=audit.rotation_precommit_hash,
    )


def _aligned_rows(
    snapshot: LoadedTiingoEtfDailySnapshot,
) -> Mapping[str, tuple[TiingoEtfDailyRow, ...]]:
    rows_by_symbol = {
        symbol: tuple(snapshot.rows_by_symbol[symbol]) for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    date_maps = {
        symbol: {row.session_date: row for row in rows}
        for symbol, rows in rows_by_symbol.items()
    }
    if any(
        len(date_maps[symbol]) != len(rows_by_symbol[symbol])
        for symbol in TIINGO_ETF_D1_SYMBOLS
    ):
        raise ValueError("Tiingo D1 event-mask coverage source dates are invalid")
    common_dates = tuple(sorted(set.intersection(*(set(value) for value in date_maps.values()))))
    if not common_dates:
        raise ValueError("Tiingo D1 event-mask coverage source has no common sessions")
    return MappingProxyType(
        {
            symbol: tuple(date_maps[symbol][session_date] for session_date in common_dates)
            for symbol in TIINGO_ETF_D1_SYMBOLS
        }
    )


def _decision_indices(
    *,
    common_session_count: int,
    config: rotation.TiingoD1TrendMeanReversionRotationConfig,
) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    minimum_index = config.trend_lookback + 1
    all_indices = tuple(range(minimum_index, common_session_count - 1))
    development_count = (
        len(all_indices) * config.development_numerator // config.development_denominator
    )
    validation_start = development_count + config.purge_sessions
    if development_count == 0 or validation_start >= len(all_indices):
        return None
    return all_indices[:development_count], all_indices[validation_start:]


def _phase_coverage(
    *,
    phase: Literal["development", "validation"],
    indices: tuple[int, ...],
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    config: rotation.TiingoD1TrendMeanReversionRotationConfig,
) -> TiingoD1EventMaskCoveragePhase:
    event_indices: list[int] = []
    discontinuity_indices: list[int] = []
    overlap_indices: list[int] = []
    either_indices: list[int] = []
    per_symbol = {
        symbol: {
            "event_any_count": 0,
            "discontinuity_any_count": 0,
            "overlap_count": 0,
        }
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    for index in indices:
        event_flags, discontinuity_flags = _mask_flags(
            index=index,
            rows_by_symbol=rows_by_symbol,
            config=config,
        )
        event_any = any(event_flags.values())
        discontinuity_any = any(discontinuity_flags.values())
        if event_any:
            event_indices.append(index)
        if discontinuity_any:
            discontinuity_indices.append(index)
        if event_any and discontinuity_any:
            overlap_indices.append(index)
        if event_any or discontinuity_any:
            either_indices.append(index)
        for symbol in TIINGO_ETF_D1_SYMBOLS:
            if event_flags[symbol]:
                per_symbol[symbol]["event_any_count"] += 1
            if discontinuity_flags[symbol]:
                per_symbol[symbol]["discontinuity_any_count"] += 1
            if event_flags[symbol] and discontinuity_flags[symbol]:
                per_symbol[symbol]["overlap_count"] += 1
    event_count = len(event_indices)
    discontinuity_count = len(discontinuity_indices)
    overlap_count = len(overlap_indices)
    either_count = len(either_indices)
    return TiingoD1EventMaskCoveragePhase(
        phase=phase,
        scheduled_decision_count=len(indices),
        event_any_count=event_count,
        discontinuity_any_count=discontinuity_count,
        overlap_count=overlap_count,
        event_priority_excluded_count=event_count,
        discontinuity_only_excluded_count=discontinuity_count - overlap_count,
        either_excluded_count=either_count,
        unmasked_count=len(indices) - either_count,
        per_symbol=per_symbol,
        event_index_set_hash=_index_set_hash(event_indices),
        discontinuity_index_set_hash=_index_set_hash(discontinuity_indices),
        overlap_index_set_hash=_index_set_hash(overlap_indices),
        either_index_set_hash=_index_set_hash(either_indices),
        excluded_run_length_buckets=_run_length_buckets(either_indices),
    )


def _mask_flags(
    *,
    index: int,
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    config: rotation.TiingoD1TrendMeanReversionRotationConfig,
) -> tuple[Mapping[str, bool], Mapping[str, bool]]:
    start = index - config.trend_lookback
    if start <= 0:
        raise ValueError("Tiingo D1 event-mask coverage decision index is invalid")
    event_flags: dict[str, bool] = {}
    discontinuity_flags: dict[str, bool] = {}
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = rows_by_symbol[symbol]
        event_flags[symbol] = any(
            row.div_cash != 0 or row.split_factor != 1 for row in rows[start : index + 1]
        )
        discontinuity_flags[symbol] = any(
            abs(
                rows[transition_index].close / rows[transition_index - 1].close
                - Decimal("1")
            )
            > config.discontinuity_limit
            for transition_index in range(start, index + 1)
        )
    return MappingProxyType(event_flags), MappingProxyType(discontinuity_flags)


def _matches_rotation_phase(
    coverage: TiingoD1EventMaskCoveragePhase,
    facts: rotation.TiingoD1TrendMeanReversionRotationPhaseFacts,
) -> bool:
    return (
        coverage.phase == facts.phase
        and coverage.scheduled_decision_count == facts.scheduled_decision_count
        and coverage.event_priority_excluded_count == facts.event_excluded_count
        and coverage.discontinuity_only_excluded_count == facts.discontinuity_excluded_count
        and coverage.unmasked_count == facts.accepted_decision_count
    )


def _index_set_hash(indices: list[int]) -> str:
    return "sha256:" + hashlib.sha256(
        ",".join(str(index) for index in indices).encode("ascii")
    ).hexdigest()


def _run_length_buckets(indices: list[int]) -> Mapping[str, int]:
    buckets = {bucket: 0 for bucket in _RUN_BUCKETS}
    if not indices:
        return MappingProxyType(buckets)
    run_length = 1
    previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            run_length += 1
        else:
            buckets[_run_bucket(run_length)] += 1
            run_length = 1
        previous = index
    buckets[_run_bucket(run_length)] += 1
    return MappingProxyType(buckets)


def _run_bucket(length: int) -> str:
    if length == 1:
        return "1"
    if length <= 5:
        return "2_to_5"
    if length <= 20:
        return "6_to_20"
    if length <= 60:
        return "21_to_60"
    return "over_60"


def _validated_run_label(run_label: str) -> str:
    return rotation._validated_run_label(run_label)


def _external_artifact_root(artifact_root: Path, repo_root: Path) -> Path:
    return rotation._external_artifact_root(artifact_root, repo_root)


def _ensure_artifact_directory(root: Path, artifact_dir: Path) -> None:
    rotation._ensure_artifact_directory(root, artifact_dir)


def _write_or_verify(path: Path, encoded: bytes) -> None:
    rotation._write_or_verify(path, encoded)


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return rotation._canonical_json(payload)


def _sha256_json(payload: Mapping[str, object]) -> str:
    return rotation._sha256_json(payload)


def _sha256_bytes(payload: bytes) -> str:
    return rotation._sha256_bytes(payload)


def _is_sha256(value: str) -> bool:
    return rotation._is_sha256(value)


def _require_matching_evidence(path: Path, expected: bytes) -> None:
    if not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
        raise ValueError("Tiingo D1 event-mask coverage evidence binding is invalid")

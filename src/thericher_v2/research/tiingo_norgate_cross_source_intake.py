"""Read-only Engine intake for Tiingo/Norgate cross-source evidence.

This module exposes attested metadata only.  The narrow source-separation
projection exists solely to freeze an offline Norgate-only engineering slice;
it never provides Tiingo prices, features, labels, or a model execution path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

from thericher_v2.data.tiingo_norgate_cross_source_cohort import (
    TiingoNorgateCrossSourceCohort,
    load_verified_tiingo_norgate_cross_source_cohort,
)

_COHORT_KIND = "tiingo_norgate_cross_source_cohort"
_REQUIRED_SCOPE = {
    "cross_source_engineering_evidence_only": True,
    "point_in_time_eligible": False,
    "model_eligible": False,
    "training_eligible": False,
    "ranking_eligible": False,
    "ensemble_eligible": False,
    "campaign_eligible": False,
    "paper_trading_eligible": False,
    "pnl_eligible": False,
    "profitability_eligible": False,
}
_REQUIRED_ACCESS_BOUNDARY = {
    "network_access": False,
    "credential_access": False,
    "broker_access": False,
    "local_paper_access": False,
    "model_access": False,
    "raw_bar_export": False,
    "feature_or_label_export": False,
}
_FORBIDDEN_COHORT_ATTRIBUTES = ("bars", "features", "labels", "__iter__")
_DECISION_INDEX_START = 20
_DECISION_INDEX_END = 480


@dataclass(frozen=True, slots=True)
class TiingoNorgateCrossSourceIntake:
    """Metadata-only cross-source evidence for later contract review."""

    artifact_dir: Path
    manifest_hash: str
    tiingo_dataset_hash: str
    tiingo_manifest_hash: str
    norgate_dataset_hash: str
    norgate_manifest_hash: str
    rank_count: int
    overlap_session_count: int
    forward_only_session_count: int
    marker_count: int
    excluded_decision_count: int
    scope: Mapping[str, bool]
    access_boundary: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class TiingoNorgateSourceSeparationContractInput:
    """Metadata needed to freeze one Norgate-only engineering contract."""

    artifact_dir: Path
    manifest_hash: str
    tiingo_dataset_hash: str
    tiingo_manifest_hash: str
    norgate_dataset_hash: str
    norgate_manifest_hash: str
    rank_symbols: tuple[tuple[int, str], ...]
    overlap_session_dates: tuple[str, ...]
    forward_only_session_dates: tuple[str, ...]
    overlap_marker_indices_by_rank: Mapping[int, tuple[int, ...]]
    forward_only_marker_indices_by_rank: Mapping[int, tuple[int, ...]]
    excluded_decision_indices_by_rank: Mapping[int, tuple[int, ...]]
    feature_lookback: int
    entry_offset: int
    exit_offset: int


def load_verified_tiingo_norgate_cross_source_intake(
    artifact_dir: Path,
    *,
    artifact_root: Path | None = None,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
) -> TiingoNorgateCrossSourceIntake:
    """Load a fully reattested cohort without opening a research data path."""

    cohort = load_verified_tiingo_norgate_cross_source_cohort(
        artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return _intake_from_verified_cohort(cohort)


def load_verified_tiingo_norgate_source_separation_contract_input(
    artifact_dir: Path,
    *,
    artifact_root: Path | None = None,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
) -> TiingoNorgateSourceSeparationContractInput:
    """Return the narrow rank/session/mask projection for one future contract."""

    cohort = load_verified_tiingo_norgate_cross_source_cohort(
        artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _intake_from_verified_cohort(cohort)
    return _source_separation_input_from_verified_cohort(cohort)


def _intake_from_verified_cohort(
    cohort: TiingoNorgateCrossSourceCohort,
) -> TiingoNorgateCrossSourceIntake:
    if not isinstance(cohort, TiingoNorgateCrossSourceCohort):
        raise TypeError("cross-source intake requires a verified Data-owned cohort")
    if any(hasattr(cohort, name) for name in _FORBIDDEN_COHORT_ATTRIBUTES):
        raise ValueError("cross-source cohort must remain metadata-only")
    if not isinstance(cohort.artifact_dir, Path) or not cohort.artifact_dir.name:
        raise ValueError("cross-source cohort artifact path is invalid")
    for value, label in (
        (cohort.manifest_hash, "manifest hash"),
        (cohort.tiingo_dataset_hash, "Tiingo dataset hash"),
        (cohort.tiingo_manifest_hash, "Tiingo manifest hash"),
        (cohort.norgate_dataset_hash, "Norgate dataset hash"),
        (cohort.norgate_manifest_hash, "Norgate manifest hash"),
    ):
        _require_sha256(value, label)
    for value, label, allow_zero in (
        (cohort.rank_count, "rank count", False),
        (cohort.overlap_session_count, "overlap session count", False),
        (cohort.forward_only_session_count, "forward-only session count", True),
        (cohort.marker_count, "marker count", False),
        (cohort.excluded_decision_count, "excluded decision count", True),
    ):
        _require_count(value, label, allow_zero=allow_zero)

    metadata = _mapping(cohort.metadata, "cross-source cohort metadata")
    if (
        metadata.get("kind") != _COHORT_KIND
        or metadata.get("immutable") is not True
        or metadata.get("artifact_dir_name") != cohort.artifact_dir.name
    ):
        raise ValueError("cross-source cohort metadata identity is invalid")
    scope = _exact_bool_mapping(metadata.get("scope"), _REQUIRED_SCOPE, "cross-source scope")
    access_boundary = _exact_bool_mapping(
        metadata.get("access_boundary"),
        _REQUIRED_ACCESS_BOUNDARY,
        "cross-source access boundary",
    )
    _verify_parent_hashes(metadata, cohort)
    _verify_counts(metadata, cohort)

    return TiingoNorgateCrossSourceIntake(
        artifact_dir=cohort.artifact_dir,
        manifest_hash=cohort.manifest_hash,
        tiingo_dataset_hash=cohort.tiingo_dataset_hash,
        tiingo_manifest_hash=cohort.tiingo_manifest_hash,
        norgate_dataset_hash=cohort.norgate_dataset_hash,
        norgate_manifest_hash=cohort.norgate_manifest_hash,
        rank_count=cohort.rank_count,
        overlap_session_count=cohort.overlap_session_count,
        forward_only_session_count=cohort.forward_only_session_count,
        marker_count=cohort.marker_count,
        excluded_decision_count=cohort.excluded_decision_count,
        scope=scope,
        access_boundary=access_boundary,
    )


def _source_separation_input_from_verified_cohort(
    cohort: TiingoNorgateCrossSourceCohort,
) -> TiingoNorgateSourceSeparationContractInput:
    metadata = _mapping(cohort.metadata, "cross-source cohort metadata")
    rank_symbols = _rank_symbols(
        _mapping(metadata.get("rank_linkage"), "cross-source rank linkage"),
        rank_count=cohort.rank_count,
    )
    overlap_dates, forward_dates = _session_dates(
        _mapping(metadata.get("session_contract"), "cross-source session contract"),
        cohort=cohort,
    )
    overlap_markers, forward_markers, exclusions = _marker_masks(
        _mapping(metadata.get("conservative_marker_mask"), "cross-source marker mask"),
        rank_symbols=rank_symbols,
        cohort=cohort,
    )
    return TiingoNorgateSourceSeparationContractInput(
        artifact_dir=cohort.artifact_dir,
        manifest_hash=cohort.manifest_hash,
        tiingo_dataset_hash=cohort.tiingo_dataset_hash,
        tiingo_manifest_hash=cohort.tiingo_manifest_hash,
        norgate_dataset_hash=cohort.norgate_dataset_hash,
        norgate_manifest_hash=cohort.norgate_manifest_hash,
        rank_symbols=rank_symbols,
        overlap_session_dates=overlap_dates,
        forward_only_session_dates=forward_dates,
        overlap_marker_indices_by_rank=MappingProxyType(overlap_markers),
        forward_only_marker_indices_by_rank=MappingProxyType(forward_markers),
        excluded_decision_indices_by_rank=MappingProxyType(exclusions),
        feature_lookback=20,
        entry_offset=1,
        exit_offset=2,
    )


def _rank_symbols(
    linkage: Mapping[str, Any], *, rank_count: int
) -> tuple[tuple[int, str], ...]:
    if linkage.get("available_rank_count") != rank_count:
        raise ValueError("cross-source rank linkage is invalid")
    pairs = linkage.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != rank_count:
        raise ValueError("cross-source rank linkage is invalid")
    result: list[tuple[int, str]] = []
    previous_rank = 0
    for pair in pairs:
        row = _mapping(pair, "cross-source rank pair")
        rank = row.get("candidate_rank")
        symbol = row.get("symbol")
        if (
            not isinstance(rank, int)
            or isinstance(rank, bool)
            or rank <= previous_rank
            or not isinstance(symbol, str)
            or not symbol
            or symbol != symbol.strip()
            or symbol != symbol.upper()
        ):
            raise ValueError("cross-source rank linkage is invalid")
        result.append((rank, symbol))
        previous_rank = rank
    if len({symbol for _rank, symbol in result}) != len(result):
        raise ValueError("cross-source rank linkage is invalid")
    return tuple(result)


def _session_dates(
    sessions: Mapping[str, Any], *, cohort: TiingoNorgateCrossSourceCohort
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if (
        sessions.get("norgate_overlap_session_count") != cohort.overlap_session_count
        or sessions.get("forward_only_session_count") != cohort.forward_only_session_count
        or sessions.get("forward_only_price_source") != "tiingo_only"
        or sessions.get("norgate_fields_in_forward_only_slice") is not False
    ):
        raise ValueError("cross-source session contract is invalid")
    overlap = _ordered_dates(
        sessions.get("overlap_session_dates"),
        expected_count=cohort.overlap_session_count,
        label="cross-source overlap sessions",
    )
    forward = _ordered_dates(
        sessions.get("forward_only_session_dates"),
        expected_count=cohort.forward_only_session_count,
        label="cross-source forward-only sessions",
    )
    if not overlap or (forward and forward[0] <= overlap[-1]):
        raise ValueError("cross-source session boundary is invalid")
    return overlap, forward


def _marker_masks(
    marker_mask: Mapping[str, Any],
    *,
    rank_symbols: tuple[tuple[int, str], ...],
    cohort: TiingoNorgateCrossSourceCohort,
) -> tuple[dict[int, tuple[int, ...]], dict[int, tuple[int, ...]], dict[int, tuple[int, ...]]]:
    reference = _mapping(marker_mask.get("reference_window"), "cross-source marker window")
    if reference != {
        "candidate_decision_index_range": "20..480",
        "entry_index": "t+1",
        "feature_source_index_range": "t-20..t",
        "inclusive_dependency_index_range": "t-20..t+2",
        "outcome_exit_index": "t+2",
        "reference_only_not_a_training_contract": True,
    }:
        raise ValueError("cross-source marker window is invalid")
    rows = marker_mask.get("per_rank")
    if not isinstance(rows, list) or len(rows) != len(rank_symbols):
        raise ValueError("cross-source per-rank marker mask is invalid")
    expected_ranks = {rank for rank, _symbol in rank_symbols}
    overlap_by_rank: dict[int, tuple[int, ...]] = {}
    forward_by_rank: dict[int, tuple[int, ...]] = {}
    exclusions_by_rank: dict[int, tuple[int, ...]] = {}
    total_markers = 0
    total_exclusions = 0
    for item in rows:
        row = _mapping(item, "cross-source per-rank marker mask")
        rank = row.get("candidate_rank")
        if (
            not isinstance(rank, int)
            or isinstance(rank, bool)
            or rank not in expected_ranks
            or rank in exclusions_by_rank
        ):
            raise ValueError("cross-source per-rank marker mask is invalid")
        overlap = _ordered_indices(
            row.get("overlap_marker_session_indices"),
            minimum=0,
            maximum=cohort.overlap_session_count - 1,
            label="cross-source overlap marker indices",
        )
        forward = _ordered_indices(
            row.get("forward_only_marker_session_indices"),
            minimum=cohort.overlap_session_count,
            maximum=cohort.overlap_session_count + cohort.forward_only_session_count - 1,
            label="cross-source forward-only marker indices",
        )
        excluded = _ordered_indices(
            row.get("excluded_decision_indices"),
            minimum=_DECISION_INDEX_START,
            maximum=_DECISION_INDEX_END,
            label="cross-source excluded decision indices",
        )
        expected_excluded = tuple(
            sorted(
                {
                    index
                    for marker in overlap
                    for index in range(
                        max(_DECISION_INDEX_START, marker - 2),
                        min(_DECISION_INDEX_END, marker + 20) + 1,
                    )
                }
            )
        )
        if excluded != expected_excluded:
            raise ValueError("cross-source marker exclusions are inconsistent")
        overlap_by_rank[rank] = overlap
        forward_by_rank[rank] = forward
        exclusions_by_rank[rank] = excluded
        total_markers += len(overlap) + len(forward)
        total_exclusions += len(excluded)
    if (
        set(exclusions_by_rank) != expected_ranks
        or total_markers != cohort.marker_count
        or total_exclusions != cohort.excluded_decision_count
    ):
        raise ValueError("cross-source marker mask counts are invalid")
    return overlap_by_rank, forward_by_rank, exclusions_by_rank


def _verify_parent_hashes(
    metadata: Mapping[str, Any], cohort: TiingoNorgateCrossSourceCohort
) -> None:
    parents = _mapping(metadata.get("parents"), "cross-source parents")
    tiingo = _mapping(parents.get("tiingo"), "cross-source Tiingo parent")
    norgate = _mapping(parents.get("norgate"), "cross-source Norgate parent")
    if (
        tiingo.get("dataset_hash") != cohort.tiingo_dataset_hash
        or tiingo.get("manifest_hash") != cohort.tiingo_manifest_hash
        or norgate.get("dataset_hash") != cohort.norgate_dataset_hash
        or norgate.get("manifest_hash") != cohort.norgate_manifest_hash
    ):
        raise ValueError("cross-source cohort parent hashes are inconsistent")


def _verify_counts(metadata: Mapping[str, Any], cohort: TiingoNorgateCrossSourceCohort) -> None:
    linkage = _mapping(metadata.get("rank_linkage"), "cross-source rank linkage")
    sessions = _mapping(metadata.get("session_contract"), "cross-source session contract")
    marker_mask = _mapping(
        metadata.get("conservative_marker_mask"), "cross-source marker mask"
    )
    if (
        linkage.get("available_rank_count") != cohort.rank_count
        or sessions.get("norgate_overlap_session_count") != cohort.overlap_session_count
        or sessions.get("forward_only_session_count") != cohort.forward_only_session_count
        or marker_mask.get("total_marker_count") != cohort.marker_count
        or marker_mask.get("excluded_rank_decision_pair_count")
        != cohort.excluded_decision_count
    ):
        raise ValueError("cross-source cohort counts are inconsistent")


def _ordered_dates(value: object, *, expected_count: int, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != expected_count:
        raise ValueError(f"{label} are invalid")
    result: list[str] = []
    previous: date | None = None
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError(f"{label} are invalid")
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"{label} are invalid") from exc
        if raw != parsed.isoformat() or (previous is not None and parsed <= previous):
            raise ValueError(f"{label} are invalid")
        result.append(raw)
        previous = parsed
    return tuple(result)


def _ordered_indices(value: object, *, minimum: int, maximum: int, label: str) -> tuple[int, ...]:
    if (
        not isinstance(value, list)
        or any(
            not isinstance(item, int)
            or isinstance(item, bool)
            or item < minimum
            or item > maximum
            for item in value
        )
        or value != sorted(set(value))
    ):
        raise ValueError(f"{label} are invalid")
    return tuple(value)


def _exact_bool_mapping(
    value: object, expected: Mapping[str, bool], label: str
) -> Mapping[str, bool]:
    mapping = _mapping(value, label)
    if set(mapping) != set(expected) or any(
        mapping.get(key) is not required for key, required in expected.items()
    ):
        raise ValueError(f"{label} is invalid")
    return MappingProxyType(dict(expected))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} is invalid")
    return value


def _require_count(value: object, label: str, *, allow_zero: bool) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} is invalid")
    if not allow_zero and value == 0:
        raise ValueError(f"{label} must be positive")


def _require_sha256(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} is invalid")

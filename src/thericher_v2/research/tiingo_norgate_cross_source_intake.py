"""Read-only Engine intake for Tiingo/Norgate cross-source evidence.

This module intentionally exposes only attested identity, count, scope, and
access-boundary metadata.  It does not provide bars, features, labels, or a
conversion path into model, campaign, ranking, ensemble, paper, or PnL work.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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

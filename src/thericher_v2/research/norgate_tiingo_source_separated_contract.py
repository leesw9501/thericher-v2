"""One bounded, source-separated contract for a future engineering batch.

The contract selects a fixed Norgate-only feature slice. Tiingo contributes
only already-attested rank/session/action-mask metadata; this module never
reads Tiingo price rows or launches a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from thericher_v2.data.norgate_broad_development_artifact import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    NorgateBroadDevelopmentFeatureArtifact,
    load_verified_norgate_broad_development_feature_artifact,
)

from .tiingo_norgate_cross_source_intake import (
    TiingoNorgateSourceSeparationContractInput,
    load_verified_tiingo_norgate_source_separation_contract_input,
)

CONTRACT_DIRECTORY = "norgate-tii-source-separated-contract"
CONTRACT_VERSION = "norgate-tii-source-separated-contract-r4"
_CONTRACT_FILE = "contract.json"
_MAX_CONTRACT_BYTES = 512_000
_FEATURE_ARTIFACT_DIR = (
    DEFAULT_MODEL_ARTIFACT_ROOT / "norgate-broad-development-features" / "r2-3c1b21bde92e4623"
)
_COHORT_ARTIFACT_DIR = (
    DEFAULT_MODEL_ARTIFACT_ROOT
    / "tiingo-norgate-cross-source-cohort"
    / "tiingo-norgate-cross-source-cohort-r1"
)
_DEVELOPMENT = range(20, 320)
_PURGE = range(320, 322)
_VALIDATION = range(322, 481)


@dataclass(frozen=True, slots=True)
class SourceSeparatedContractExpectation:
    """Pinned geometry for the sole contract revision in this module."""

    rank_count: int
    cohort_mask_eligible_count: int
    retained_feature_row_count: int
    development_row_count: int
    purge_row_count: int
    validation_row_count: int


DEFAULT_EXPECTATION = SourceSeparatedContractExpectation(
    rank_count=29,
    cohort_mask_eligible_count=10_053,
    retained_feature_row_count=9_904,
    development_row_count=6_434,
    purge_row_count=50,
    validation_row_count=3_420,
)


@dataclass(frozen=True, slots=True)
class NorgateTiingoSourceSeparatedContract:
    """Read-only metadata for one future, predeclared engineering batch."""

    artifact_dir: Path
    contract_hash: str
    cohort_manifest_hash: str
    feature_artifact_hash: str
    feature_contract_hash: str
    rank_count: int
    retained_feature_row_count: int
    development_row_count: int
    purge_row_count: int
    validation_row_count: int
    contract: Mapping[str, Any]


def default_norgate_tiingo_source_separated_contract_dir(
    *, artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT
) -> Path:
    """Return the one immutable external destination for this preflight."""

    return Path(artifact_root) / CONTRACT_DIRECTORY / CONTRACT_VERSION


def build_norgate_tiingo_source_separated_contract(
    *,
    cohort_artifact_dir: Path = _COHORT_ARTIFACT_DIR,
    feature_artifact_dir: Path = _FEATURE_ARTIFACT_DIR,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
    expectation: SourceSeparatedContractExpectation = DEFAULT_EXPECTATION,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> NorgateTiingoSourceSeparatedContract:
    """Freeze one compact contract after offline parent re-attestation."""

    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    _validate_expectation(expectation)
    target = default_norgate_tiingo_source_separated_contract_dir(artifact_root=root)
    _validate_artifact_target(target, root=root)
    if target.exists():
        return verify_norgate_tiingo_source_separated_contract(
            target,
            cohort_artifact_dir=cohort_artifact_dir,
            feature_artifact_dir=feature_artifact_dir,
            artifact_root=root,
            market_data_root=market_data_root,
            repo_root=repo_root,
            expectation=expectation,
        )

    cohort, feature = _load_parents(
        cohort_artifact_dir=cohort_artifact_dir,
        feature_artifact_dir=feature_artifact_dir,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_parent_lineage(cohort, feature)
    contract = _contract(target, cohort=cohort, feature=feature, expectation=expectation)
    data = _json_bytes(contract)
    if len(data) > _MAX_CONTRACT_BYTES:
        raise ValueError("source-separated contract exceeds the compact artifact limit")
    _validate_storage(root, required_bytes=len(data), disk_usage=disk_usage)
    staging = _create_staging_directory(target)
    try:
        (staging / _CONTRACT_FILE).write_bytes(data)
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return verify_norgate_tiingo_source_separated_contract(
        target,
        cohort_artifact_dir=cohort_artifact_dir,
        feature_artifact_dir=feature_artifact_dir,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
        expectation=expectation,
    )


def verify_norgate_tiingo_source_separated_contract(
    artifact_dir: Path,
    *,
    cohort_artifact_dir: Path = _COHORT_ARTIFACT_DIR,
    feature_artifact_dir: Path = _FEATURE_ARTIFACT_DIR,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path | None = None,
    repo_root: Path | None = None,
    expectation: SourceSeparatedContractExpectation = DEFAULT_EXPECTATION,
) -> NorgateTiingoSourceSeparatedContract:
    """Recompute the contract from verified parents without fitting a model."""

    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    _validate_expectation(expectation)
    artifact = _validate_existing_artifact(artifact_dir, root=root)
    data = _read_regular_file(artifact, _CONTRACT_FILE, "source-separated contract")
    if len(data) > _MAX_CONTRACT_BYTES:
        raise ValueError("source-separated contract exceeds the compact artifact limit")
    contract = _json_object(data, "source-separated contract")
    cohort, feature = _load_parents(
        cohort_artifact_dir=cohort_artifact_dir,
        feature_artifact_dir=feature_artifact_dir,
        artifact_root=root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _validate_parent_lineage(cohort, feature)
    expected = _contract(artifact, cohort=cohort, feature=feature, expectation=expectation)
    if contract != expected:
        raise ValueError("source-separated contract is inconsistent")
    return _result(artifact=artifact, data=data, contract=contract)


def load_verified_norgate_tiingo_source_separated_contract(
    artifact_dir: Path,
    **kwargs: Any,
) -> NorgateTiingoSourceSeparatedContract:
    """Load the compact contract only after full parent re-attestation."""

    return verify_norgate_tiingo_source_separated_contract(artifact_dir, **kwargs)


def _load_parents(
    *,
    cohort_artifact_dir: Path,
    feature_artifact_dir: Path,
    artifact_root: Path,
    market_data_root: Path | None,
    repo_root: Path | None,
) -> tuple[TiingoNorgateSourceSeparationContractInput, NorgateBroadDevelopmentFeatureArtifact]:
    cohort = load_verified_tiingo_norgate_source_separation_contract_input(
        cohort_artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    feature = load_verified_norgate_broad_development_feature_artifact(
        feature_artifact_dir,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return cohort, feature


def _validate_parent_lineage(
    cohort: TiingoNorgateSourceSeparationContractInput,
    feature: NorgateBroadDevelopmentFeatureArtifact,
) -> None:
    if (
        feature.parent_dataset_hash != cohort.norgate_dataset_hash
        or feature.parent_manifest_hash != cohort.norgate_manifest_hash
    ):
        raise ValueError("source-separated contract parent lineage is inconsistent")
    transform = _mapping(feature.contract.get("transform"), "Norgate feature transform")
    if transform != {
        "feature_kind": "raw_close_to_close_returns",
        "feature_return_count": 20,
        "feature_return_end_index_range": "t-19..t",
        "feature_source_index_range": "t-20..t",
        "max_feature_source_index": "t",
        "entry_index": "t+1",
        "exit_index": "t+2",
        "label": "1 if open[t+2]/open[t+1]-1 > 0 else 0",
        "label_values": {"non_positive": 0, "positive": 1},
    }:
        raise ValueError("source-separated contract feature geometry is invalid")
    if (cohort.feature_lookback, cohort.entry_offset, cohort.exit_offset) != (20, 1, 2):
        raise ValueError("source-separated cohort geometry is invalid")
    if len(cohort.overlap_session_dates) != 483 or len(cohort.forward_only_session_dates) != 18:
        raise ValueError("source-separated cohort session geometry is invalid")
    if len(cohort.rank_symbols) != len(cohort.excluded_decision_indices_by_rank):
        raise ValueError("source-separated cohort rank geometry is invalid")
    selected_symbols = feature.contract.get("selected_symbols")
    if not isinstance(selected_symbols, list):
        raise ValueError("source-separated feature symbols are invalid")
    feature_symbols: dict[int, str] = {}
    for row in selected_symbols:
        item = _mapping(row, "source-separated feature symbol")
        rank = item.get("candidate_rank")
        symbol = item.get("symbol")
        if (
            not isinstance(rank, int)
            or isinstance(rank, bool)
            or rank <= 0
            or not isinstance(symbol, str)
            or not symbol
            or rank in feature_symbols
        ):
            raise ValueError("source-separated feature symbols are invalid")
        feature_symbols[rank] = symbol
    if any(feature_symbols.get(rank) != symbol for rank, symbol in cohort.rank_symbols):
        raise ValueError("source-separated rank/symbol linkage is inconsistent")
    _norgate_feature_conditioning(feature)


def _norgate_feature_conditioning(
    feature: NorgateBroadDevelopmentFeatureArtifact,
) -> dict[str, Any]:
    conditioning = _mapping(
        feature.contract.get("discontinuity_conditioning"),
        "Norgate feature conditioning",
    )
    if conditioning != {
        "checked_index_range": "t-20..t+2",
        "condition": (
            "abs(open[i]/close[i-1]-1)>=0.20 or "
            "abs(close[i]/close[i-1]-1)>=0.20"
        ),
        "does_not_assert_corporate_action": True,
        "exclusion_rule": "exclude sample when any checked raw discontinuity is true",
        "index_zero_policy": "not_computable_without_prior_panel_close",
        "purpose": "raw_data_quality_conditioning_only",
        "threshold_absolute_return": 0.2,
    }:
        raise ValueError("source-separated Norgate feature conditioning is invalid")
    return dict(conditioning)


def _contract(
    artifact: Path,
    *,
    cohort: TiingoNorgateSourceSeparationContractInput,
    feature: NorgateBroadDevelopmentFeatureArtifact,
    expectation: SourceSeparatedContractExpectation,
) -> dict[str, Any]:
    counts = _selected_counts(cohort, feature)
    _validate_counts(counts, expectation=expectation)
    conditioning = _norgate_feature_conditioning(feature)
    rank_pairs = [
        {"candidate_rank": rank, "symbol": symbol} for rank, symbol in cohort.rank_symbols
    ]
    rank_hash = _sha256(_json_bytes(rank_pairs))
    mask_hash = _sha256(
        _json_bytes(
            [
                {
                    "candidate_rank": rank,
                    "overlap_marker_indices": list(cohort.overlap_marker_indices_by_rank[rank]),
                    "forward_only_marker_indices": list(
                        cohort.forward_only_marker_indices_by_rank[rank]
                    ),
                    "excluded_decision_indices": list(
                        cohort.excluded_decision_indices_by_rank[rank]
                    ),
                }
                for rank, _symbol in cohort.rank_symbols
            ]
        )
    )
    return {
        "schema_version": 1,
        "kind": "norgate_tiingo_source_separated_contract",
        "contract_version": CONTRACT_VERSION,
        "artifact_dir_name": artifact.name,
        "immutable": True,
        "scope": {
            "engineering_only": True,
            "future_bounded_batch_prepared": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
            "ensemble_eligible": False,
            "paper_trading_eligible": False,
            "pnl_eligible": False,
            "model_promotion_eligible": False,
            "profitability_eligible": False,
        },
        "parents": {
            "cohort": {
                "manifest_hash": cohort.manifest_hash,
                "tiingo_dataset_hash": cohort.tiingo_dataset_hash,
                "tiingo_manifest_hash": cohort.tiingo_manifest_hash,
                "norgate_dataset_hash": cohort.norgate_dataset_hash,
                "norgate_manifest_hash": cohort.norgate_manifest_hash,
            },
            "norgate_feature_artifact": {
                "artifact_hash": feature.artifact_hash,
                "contract_hash": feature.contract_hash,
                "manifest_hash": feature.manifest_hash,
                "parent_dataset_hash": feature.parent_dataset_hash,
                "parent_manifest_hash": feature.parent_manifest_hash,
            },
        },
        "source_roles": {
            "norgate": "sole_price_feature_label_source",
            "tiingo": "rank_session_and_returned_marker_mask_only",
            "source_price_mixing": False,
            "forward_only_tiingo_session_use": False,
        },
        "rank_selection": {
            "rule": "exact_cohort_candidate_rank_and_symbol_pairs",
            "rank_count": len(rank_pairs),
            "pairs": rank_pairs,
            "pairs_sha256": rank_hash,
        },
        "temporal_geometry": {
            "feature_source_index_range": "t-20..t",
            "entry_index": "t+1",
            "exit_index": "t+2",
            "maximum_used_dependency_index": 482,
            "first_forward_only_tiingo_index": len(cohort.overlap_session_dates),
            "forward_only_sessions_used": False,
            "development_decision_index_range": [20, 319],
            "purge_decision_index_range": [320, 321],
            "validation_decision_index_range": [322, 480],
            "purge_observed_sessions": 2,
            "embargo_observed_sessions_for_any_later_fold_or_refit": 2,
            "post_validation_embargo_consumed": False,
        },
        "conservative_marker_mask": {
            "rule": (
                "exclude every decision whose inclusive t-20..t+2 dependency "
                "touches a returned Tiingo marker"
            ),
            "per_rank_sha256": mask_hash,
            "cohort_excluded_pair_count": sum(
                len(values) for values in cohort.excluded_decision_indices_by_rank.values()
            ),
            "forward_only_marker_pair_effect": "none",
        },
        "norgate_feature_conditioning": {
            "parent_artifact_rule": conditioning,
            "rows_removed_after_tiingo_marker_mask": (
                counts["after_tiingo_marker_mask"]
                - counts["after_existing_norgate_feature_conditioning"]
            ),
        },
        "sample_counts": counts,
        "future_batch": {
            "cpu_baselines": ["naive_always_long", "regularized_linear"],
            "cuda_candidates": [
                {
                    "id": "mlp-hidden-32-seed-71",
                    "family": "mlp",
                    "hidden_width": 32,
                    "seed": 71,
                    "epochs": 12,
                    "batch_size": 1024,
                },
                {
                    "id": "mlp-hidden-64-seed-113",
                    "family": "mlp",
                    "hidden_width": 64,
                    "seed": 113,
                    "epochs": 12,
                    "batch_size": 1024,
                },
            ],
            "cuda_max_concurrent_jobs": 1,
            "cuda_per_job_wall_clock_cap_seconds": 180,
            "cuda_per_job_vram_cap_mib": 4096,
            "no_candidate_ranking_or_promotion": True,
        },
        "stop_rules": [
            "Reject before fitting on any parent hash, rank roster, mask, or count mismatch.",
            (
                "Reject before fitting if any Tiingo price, label, or forward-only "
                "session enters the slice."
            ),
            (
                "Stop a CUDA job at its wall-clock or VRAM cap; preserve evidence "
                "and do not retry automatically."
            ),
            (
                "Do not interpret this survivor/availability-conditioned development "
                "slice as point-in-time or profitability evidence."
            ),
        ],
        "limitations": [
            (
            "Rank linkage is static survivor and availability evidence, not "
                "point-in-time membership."
            ),
            (
                "Norgate raw-discontinuity conditioning uses t+2 and is a static "
                "offline filter, not point-in-time safe."
            ),
            "Norgate raw adjustment and corporate-action semantics remain unverified.",
            (
                "Tiingo marker dates are returned-session attachments, not "
                "authoritative action timestamps."
            ),
            "The 18 Tiingo forward-only sessions are not a holdout or performance sample.",
            (
                "A future batch remains engineering evidence and cannot rank, "
                "promote, paper trade, or claim profit."
            ),
        ],
    }


def _selected_counts(
    cohort: TiingoNorgateSourceSeparationContractInput,
    feature: NorgateBroadDevelopmentFeatureArtifact,
) -> dict[str, int]:
    ranks = {rank for rank, _symbol in cohort.rank_symbols}
    potential = len(ranks) * 461
    cohort_eligible = potential - sum(
        len(cohort.excluded_decision_indices_by_rank[rank]) for rank in ranks
    )
    counts = {
        "potential_rank_decision_pairs": potential,
        "after_tiingo_marker_mask": cohort_eligible,
        "after_existing_norgate_feature_conditioning": 0,
        "development": 0,
        "purge": 0,
        "validation": 0,
    }
    seen_ranks: set[int] = set()
    feature_ranks = feature.symbol_ranks
    feature_decisions = feature.decision_indices
    if len(feature_ranks) != len(feature_decisions):
        raise ValueError("source-separated feature arrays are misaligned")
    for raw_rank, raw_decision in zip(feature_ranks, feature_decisions, strict=True):
        rank = int(raw_rank)
        decision = int(raw_decision)
        if rank not in ranks:
            continue
        if decision < 20 or decision > 480:
            raise ValueError("source-separated feature decision is outside the overlap")
        seen_ranks.add(rank)
        if decision in cohort.excluded_decision_indices_by_rank[rank]:
            continue
        counts["after_existing_norgate_feature_conditioning"] += 1
        if decision in _DEVELOPMENT:
            counts["development"] += 1
        elif decision in _PURGE:
            counts["purge"] += 1
        elif decision in _VALIDATION:
            counts["validation"] += 1
        else:  # pragma: no cover - the fixed ranges cover every valid decision.
            raise ValueError("source-separated feature split is invalid")
    if seen_ranks != ranks:
        raise ValueError("source-separated feature artifact is missing a selected rank")
    if (
        counts["after_existing_norgate_feature_conditioning"]
        != counts["development"] + counts["purge"] + counts["validation"]
    ):
        raise ValueError("source-separated feature count is inconsistent")
    return counts


def _validate_counts(
    counts: Mapping[str, int], *, expectation: SourceSeparatedContractExpectation
) -> None:
    expected = {
        "after_tiingo_marker_mask": expectation.cohort_mask_eligible_count,
        "after_existing_norgate_feature_conditioning": expectation.retained_feature_row_count,
        "development": expectation.development_row_count,
        "purge": expectation.purge_row_count,
        "validation": expectation.validation_row_count,
    }
    if any(counts.get(key) != value for key, value in expected.items()):
        raise ValueError("source-separated sample counts are invalid")
    if counts.get("potential_rank_decision_pairs") != expectation.rank_count * 461:
        raise ValueError("source-separated rank count is invalid")


def _validate_expectation(expectation: SourceSeparatedContractExpectation) -> None:
    values = (
        expectation.rank_count,
        expectation.cohort_mask_eligible_count,
        expectation.retained_feature_row_count,
        expectation.development_row_count,
        expectation.purge_row_count,
        expectation.validation_row_count,
    )
    if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values):
        raise ValueError("source-separated contract expectation is invalid")
    if (
        expectation.retained_feature_row_count
        != expectation.development_row_count
        + expectation.purge_row_count
        + expectation.validation_row_count
        or expectation.retained_feature_row_count > expectation.cohort_mask_eligible_count
    ):
        raise ValueError("source-separated contract expectation is inconsistent")


def _result(
    *, artifact: Path, data: bytes, contract: Mapping[str, Any]
) -> NorgateTiingoSourceSeparatedContract:
    sample_counts = _mapping(contract.get("sample_counts"), "source-separated sample counts")
    parents = _mapping(contract.get("parents"), "source-separated parents")
    cohort = _mapping(parents.get("cohort"), "source-separated cohort parent")
    feature = _mapping(
        parents.get("norgate_feature_artifact"), "source-separated feature parent"
    )
    return NorgateTiingoSourceSeparatedContract(
        artifact_dir=artifact,
        contract_hash=_sha256(data),
        cohort_manifest_hash=_required_sha256(
            cohort.get("manifest_hash"), "cohort manifest hash"
        ),
        feature_artifact_hash=_required_sha256(
            feature.get("artifact_hash"), "feature artifact hash"
        ),
        feature_contract_hash=_required_sha256(
            feature.get("contract_hash"), "feature contract hash"
        ),
        rank_count=_positive_int(
            _mapping(contract.get("rank_selection"), "source-separated rank selection").get(
                "rank_count"
            ),
            "source-separated rank count",
        ),
        retained_feature_row_count=_positive_int(
            sample_counts.get("after_existing_norgate_feature_conditioning"),
            "source-separated retained row count",
        ),
        development_row_count=_positive_int(
            sample_counts.get("development"), "source-separated development row count"
        ),
        purge_row_count=_positive_int(
            sample_counts.get("purge"), "source-separated purge row count"
        ),
        validation_row_count=_positive_int(
            sample_counts.get("validation"), "source-separated validation row count"
        ),
        contract=MappingProxyType(dict(contract)),
    )


def _validate_artifact_root(value: Path, *, repo_root: Path | None) -> Path:
    root = Path(value)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("source-separated artifact root must be an existing directory")
    root = root.resolve()
    repo = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repo.is_dir() or repo.is_symlink():
        raise ValueError("source-separated repository root is invalid")
    repo = repo.resolve()
    docker_mount = (
        os.name != "nt"
        and repo == Path("/app").resolve()
        and root.is_relative_to(Path("/app/model_artifacts").resolve())
    )
    if root.is_relative_to(repo) and not docker_mount:
        raise ValueError("source-separated artifacts must stay outside the Git workspace")
    return root


def _validate_artifact_target(target: Path, *, root: Path) -> None:
    if target != default_norgate_tiingo_source_separated_contract_dir(artifact_root=root):
        raise ValueError("source-separated contract destination is invalid")
    if target.parent.exists() and target.parent.is_symlink():
        raise ValueError("source-separated contract parent path is invalid")
    if target.parent.is_dir() and any(target.parent.glob(".stage-*")):
        raise FileExistsError("source-separated contract staging residue requires recovery")


def _validate_existing_artifact(value: Path, *, root: Path) -> Path:
    artifact = Path(value)
    if not artifact.is_dir() or artifact.is_symlink():
        raise ValueError("source-separated contract artifact must be a directory")
    artifact = artifact.resolve()
    if artifact != default_norgate_tiingo_source_separated_contract_dir(artifact_root=root):
        raise ValueError("source-separated contract artifact is outside its root")
    entries = tuple(artifact.iterdir())
    if {entry.name for entry in entries} != {_CONTRACT_FILE} or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ValueError("source-separated contract artifact files are invalid")
    return artifact


def _validate_storage(
    root: Path, *, required_bytes: int, disk_usage: Callable[[str | Path], Any]
) -> None:
    usage = disk_usage(root)
    total = int(usage.total)
    free_after = int(usage.free) - required_bytes
    if total <= 0 or free_after < 0:
        raise ValueError("source-separated contract storage is invalid")
    free_percent = 100 * free_after / total
    if free_percent < 15:
        raise ValueError("source-separated contract storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn("source-separated contract storage is below the warning floor", stacklevel=2)


def _create_staging_directory(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".stage-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _read_regular_file(root: Path, filename: str, label: str) -> bytes:
    path = root / filename
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(root):
        raise ValueError(f"{label} path is invalid")
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    return path.read_bytes()


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    return _mapping(value, label)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is invalid")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} is invalid")
    return value


def _required_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

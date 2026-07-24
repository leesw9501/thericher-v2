"""Sanitized development-only qualification for the static Norgate trial panel."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from thericher_v2.data.norgate_trial_development_panel import (
    DEFAULT_MARKET_DATA_ROOT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
    NorgateTrialDevelopmentPanelCatalog,
    load_verified_norgate_trial_development_panel_catalog,
)

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
NORGATE_DEVELOPMENT_QUALIFICATION_VERSION = "norgate-development-qualification-r1"
_ARTIFACT_DIRECTORY = "norgate-development-qualification"
_RECEIPT_FILE = "qualification.json"
_MINIMUM_COMMON_SESSIONS = 23
_PROHIBITED_SCOPE_FIELDS = (
    "point_in_time_eligible",
    "ranking_eligible",
    "sealed_holdout_eligible",
    "campaign_eligible",
    "model_eligible",
    "gpu_eligible",
    "paper_trading_eligible",
)
_REVERSAL_FACTS = (
    "source_identity_or_hash_changes",
    "source_scope_is_not_strictly_development_only",
    "source_loses_static_survivorship_or_adjustment_limitations",
    "source_has_fewer_than_declared_interface_sessions",
    "a sanctioned_consumer_reaches_a_prohibited_model_gpu_paper_pnl_or_live_route",
)


@dataclass(frozen=True, slots=True)
class NorgateDevelopmentQualification:
    """One hash-bound, declarative-only development-input receipt."""

    receipt_path: Path
    receipt_hash: str
    status: str
    source_dataset_hash: str
    source_manifest_hash: str
    selected_symbol_count: int
    common_session_count: int
    scope: Mapping[str, bool]
    development_interface: Mapping[str, object]
    limitations: tuple[str, ...]
    reversal_facts: tuple[str, ...]


def default_norgate_development_qualification_receipt_path(
    source_dataset_hash: str,
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
) -> Path:
    """Return the sole receipt path for one full source identity hash."""

    digest = _hash_hex(source_dataset_hash)
    return (
        Path(artifact_root)
        / _ARTIFACT_DIRECTORY
        / f"{_artifact_version_directory()}-{digest[:16]}"
        / _RECEIPT_FILE
    )


def qualify_frozen_norgate_trial_development_panel(
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateDevelopmentQualification:
    """Qualify only the repository-pinned local Norgate trial snapshot."""

    return qualify_norgate_trial_development_panel(
        FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
        expected_dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        expected_dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def qualify_norgate_trial_development_panel(
    snapshot_dir: Path,
    *,
    expected_dataset_id: str,
    expected_dataset_hash: str,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> NorgateDevelopmentQualification:
    """Re-attest a panel and write only one sanitized external receipt.

    The attested catalog stays local to this function. Its rows are never
    returned or persisted through this development-only API.
    """

    root = _validate_artifact_root(artifact_root, repo_root=repo_root)
    catalog = load_verified_norgate_trial_development_panel_catalog(
        snapshot_dir,
        expected_dataset_id=expected_dataset_id,
        expected_dataset_hash=expected_dataset_hash,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    qualified, reasons, scope, interface = _qualification_components(catalog)
    receipt = _receipt_document(catalog, qualified, reasons, scope, interface)
    receipt_bytes = _json_bytes(receipt)
    target = default_norgate_development_qualification_receipt_path(
        catalog.source.dataset_hash,
        artifact_root=root,
    )
    _validate_receipt_target(target, root=root, source_dataset_hash=catalog.source.dataset_hash)
    if target.exists():
        if _read_regular_file(target) != receipt_bytes:
            raise ValueError("Norgate development qualification receipt content is invalid")
    else:
        _write_receipt(target, receipt_bytes, root=root)
    return NorgateDevelopmentQualification(
        receipt_path=target,
        receipt_hash="sha256:" + hashlib.sha256(receipt_bytes).hexdigest(),
        status="qualified_for_development_only" if qualified else "unqualified",
        source_dataset_hash=catalog.source.dataset_hash,
        source_manifest_hash=catalog.source.manifest_hash,
        selected_symbol_count=catalog.selected_symbol_count,
        common_session_count=len(catalog.common_sessions),
        scope=MappingProxyType(scope),
        development_interface=MappingProxyType(interface),
        limitations=tuple(catalog.source_limitations),
        reversal_facts=_REVERSAL_FACTS,
    )


def _qualification_components(
    catalog: NorgateTrialDevelopmentPanelCatalog,
) -> tuple[bool, list[str], dict[str, bool], dict[str, object]]:
    prohibited_scope_is_clear = all(
        getattr(catalog.scope, name) is False for name in _PROHIBITED_SCOPE_FIELDS
    )
    reasons: list[str] = []
    if not catalog.scope.development_panel_attested:
        reasons.append("panel_not_attested")
    if not catalog.scope.development_training_eligible:
        reasons.append("development_training_not_eligible")
    if not prohibited_scope_is_clear:
        reasons.append("prohibited_source_scope_not_clear")
    if catalog.selected_symbol_count <= 0:
        reasons.append("no_selected_symbols")
    if len(catalog.common_sessions) < _MINIMUM_COMMON_SESSIONS:
        reasons.append("insufficient_common_sessions_for_declared_interface")
    qualified = not reasons
    scope = {
        "qualified_for_development_only": qualified,
        "development_training_eligible": catalog.scope.development_training_eligible,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
        "campaign_eligible": False,
        "model_eligible": False,
        "gpu_eligible": False,
        "paper_trading_eligible": False,
        "pnl_eligible": False,
        "live_eligible": False,
    }
    interface: dict[str, object]
    if qualified:
        interface = {
            "interface_id": "norgate-static-d1-development-contract-r1",
            "decision_timing": "completed_1d_close_at_t",
            "window_sessions": 21,
            "return_count": 20,
            "source_index_range": "t-20..t",
            "as_of_boundary": "inputs_end_at_t",
            "outcome_timing": "next_session_open_t_plus_1_to_following_session_open_t_plus_2",
            "materialization": "declarative_only",
            "feature_values_persisted": False,
            "outcome_values_persisted": False,
        }
    else:
        interface = {"defined": False, "materialization": "not_defined"}
    return qualified, reasons or ["development_only_scope_attested"], scope, interface


def _receipt_document(
    catalog: NorgateTrialDevelopmentPanelCatalog,
    qualified: bool,
    reasons: list[str],
    scope: Mapping[str, bool],
    interface: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "norgate_development_qualification",
        "qualification_version": NORGATE_DEVELOPMENT_QUALIFICATION_VERSION,
        "status": "qualified_for_development_only" if qualified else "unqualified",
        "source_identity": {
            "provider": catalog.source.provider,
            "interval": catalog.source.interval,
            "dataset_id": catalog.source.dataset_id,
            "dataset_hash": catalog.source.dataset_hash,
            "manifest_hash": catalog.source.manifest_hash,
            "membership_dataset_hash": catalog.source.membership_dataset_hash,
            "calendar_dataset_hash": catalog.source.calendar_dataset_hash,
        },
        "geometry": {
            "selected_symbol_count": catalog.selected_symbol_count,
            "common_session_count": len(catalog.common_sessions),
            "minimum_common_sessions_for_declared_interface": _MINIMUM_COMMON_SESSIONS,
        },
        "scope": dict(scope),
        "development_interface": dict(interface),
        "qualification_reasons": reasons,
        "limitations": list(catalog.source_limitations),
        "reversal_facts": list(_REVERSAL_FACTS),
        "receipt_constraints": {
            "raw_ohlcv_persisted": False,
            "row_level_data_persisted": False,
            "feature_vectors_persisted": False,
            "outcome_labels_persisted": False,
            "broker_or_network_used": False,
            "credential_access_used": False,
        },
    }


def _validate_artifact_root(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(artifact_root)
    if not root.is_dir() or _is_link_like(root):
        raise ValueError(
            "Norgate development qualification artifact root must be an existing directory"
        )
    root = root.resolve()
    repository = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    if not repository.is_dir() or _is_link_like(repository):
        raise ValueError("Norgate development qualification repository root is invalid")
    repository = repository.resolve()
    docker_artifact_root = Path("/app/model_artifacts").resolve()
    docker_mount = (
        os.name != "nt"
        and repository == Path("/app").resolve()
        and (root == docker_artifact_root or root.is_relative_to(docker_artifact_root))
    )
    if (root == repository or root.is_relative_to(repository)) and not docker_mount:
        raise ValueError(
            "Norgate development qualification artifact root must stay outside Git workspace"
        )
    return root


def _validate_receipt_target(target: Path, *, root: Path, source_dataset_hash: str) -> None:
    expected = default_norgate_development_qualification_receipt_path(
        source_dataset_hash,
        artifact_root=root,
    )
    if Path(target) != expected:
        raise ValueError("Norgate development qualification receipt destination is invalid")
    _validate_receipt_parent_prefix(target.parent, root=root)
    if target.exists() and (_is_link_like(target) or not target.is_file()):
        raise ValueError("Norgate development qualification receipt path is invalid")


def _validate_receipt_parent_prefix(container: Path, *, root: Path) -> None:
    artifact_parent = root / _ARTIFACT_DIRECTORY
    if container.parent != artifact_parent:
        raise ValueError("Norgate development qualification receipt directory is invalid")
    for path in (artifact_parent, container):
        if path.exists():
            _validate_safe_directory(path, root=root)


def _write_receipt(target: Path, data: bytes, *, root: Path) -> None:
    artifact_parent = root / _ARTIFACT_DIRECTORY
    if target.parent.parent != artifact_parent:
        raise ValueError("Norgate development qualification receipt directory is invalid")
    for path in (artifact_parent, target.parent):
        if path.exists():
            _validate_safe_directory(path, root=root)
        else:
            path.mkdir()
            _validate_safe_directory(path, root=root)
    temporary = target.parent / f".{_RECEIPT_FILE}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(data)
        _validate_safe_directory(target.parent, root=root)
        temporary.replace(target)
        if _is_link_like(target) or not target.is_file():
            raise ValueError("Norgate development qualification receipt path is invalid")
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_safe_directory(path: Path, *, root: Path) -> None:
    if _is_link_like(path) or not path.is_dir() or not path.resolve().is_relative_to(root):
        raise ValueError(
            "Norgate development qualification receipt directory escapes artifact root"
        )


def _read_regular_file(path: Path) -> bytes:
    if _is_link_like(path) or not path.is_file():
        raise ValueError("Norgate development qualification receipt path is invalid")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError("Norgate development qualification receipt is unreadable") from exc


def _artifact_version_directory() -> str:
    prefix, marker, revision = NORGATE_DEVELOPMENT_QUALIFICATION_VERSION.rpartition("-r")
    if not prefix or marker != "-r" or not revision.isdecimal():
        raise ValueError("Norgate development qualification version is invalid")
    return f"r{revision}"


def _hash_hex(value: object) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("Norgate development qualification source dataset hash is invalid")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(
            "Norgate development qualification source dataset hash is invalid"
        ) from exc
    return value[7:]


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

"""Execution-free helpers for external Research artifact directories."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")


def resolve_model_artifact_root() -> Path:
    """Resolve the local artifact root without importing execution behavior."""

    configured = (
        os.environ.get("THERICHER_HOST_MODEL_ARTIFACT_ROOT")
        or os.environ.get("THERICHER_MODEL_ARTIFACT_ROOT")
    )
    return Path(configured) if configured else DEFAULT_MODEL_ARTIFACT_ROOT


def ensure_external_artifact_directory(
    artifact_root: Path,
    repo_root: Path | None,
    *parts: str,
) -> Path:
    """Create a child directory only while every resolved component stays external."""

    requested_path = Path(artifact_root).absolute()
    if _has_existing_symlink_component(requested_path):
        raise ValueError("model artifact root must not traverse a symlink")
    requested_root = requested_path.resolve(strict=False)
    existing_ancestor = requested_root
    missing_parts: list[str] = []
    while not existing_ancestor.exists():
        if not existing_ancestor.name or existing_ancestor.parent == existing_ancestor:
            raise ValueError("model artifact root has no existing parent")
        missing_parts.append(existing_ancestor.name)
        existing_ancestor = existing_ancestor.parent
    if existing_ancestor.is_symlink() or not existing_ancestor.is_dir():
        raise ValueError("model artifact root must be an existing non-symlink directory")
    root = existing_ancestor.resolve(strict=True)
    planned_root = root.joinpath(*reversed(missing_parts))
    reject_repo_artifact_path(planned_root, repo_root)
    for part in reversed(missing_parts):
        candidate = root / part
        candidate.mkdir()
        if candidate.is_symlink() or not candidate.is_dir():
            raise ValueError("model artifact root must be an existing non-symlink directory")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("model artifact root escapes its external parent")
        reject_repo_artifact_path(resolved, repo_root)
        root = resolved
    current = root
    for part in parts:
        if not part or Path(part).name != part:
            raise ValueError("artifact directory part is invalid")
        candidate = current / part
        if candidate.exists():
            if candidate.is_symlink() or not candidate.is_dir():
                raise ValueError("artifact directory must not be a symlink")
        else:
            candidate.mkdir()
        resolved = candidate.resolve(strict=True)
        if resolved != candidate or not resolved.is_relative_to(root):
            raise ValueError("artifact directory escapes its external root")
        reject_repo_artifact_path(resolved, repo_root)
        current = resolved
    return current


def reject_repo_artifact_path(artifact_root: Path, repo_root: Path | None) -> None:
    """Reject Git-resident artifacts while allowing the configured Docker mount."""

    if repo_root is None:
        return
    resolved_artifact = Path(artifact_root).resolve(strict=False)
    resolved_repo = Path(repo_root).resolve(strict=False)
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_artifact_root = docker_repo_root / "model_artifacts"
        if resolved_repo == docker_repo_root and (
            resolved_artifact == docker_artifact_root
            or docker_artifact_root in resolved_artifact.parents
        ):
            return
    if resolved_artifact == resolved_repo or resolved_repo in resolved_artifact.parents:
        raise ValueError("artifact_root must be outside the Git workspace")


def _has_existing_symlink_component(path: Path) -> bool:
    """Check the lexical supplied root before resolving its existing parents."""

    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if not current.exists():
            return False
        if current.is_symlink():
            return True
    return False

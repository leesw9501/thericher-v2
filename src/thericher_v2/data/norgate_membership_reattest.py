"""Offline, source-safe reattestation receipts for Norgate membership snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thericher_v2.data.norgate_membership import (
    NorgateMembershipSnapshotResult,
    verify_norgate_sp500_membership_snapshot,
)

NORGATE_MEMBERSHIP_REATTESTATION_KIND = "norgate_membership_reattestation"
NORGATE_MEMBERSHIP_REATTESTATION_SCHEMA_VERSION = 1
_ATTEMPT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_INELIGIBLE_SCOPE_FLAGS = (
    "direct_historical_universe_list",
    "publication_time_proven",
    "campaign_eligible",
    "model_eligible",
    "ranking_eligible",
    "pit_eligible",
    "sealed_holdout_eligible",
)


class NorgateMembershipReattestationError(ValueError):
    """A source-safe failure while producing a read-only receipt."""


@dataclass(frozen=True, slots=True)
class NorgateMembershipReattestationResult:
    """Non-sensitive receipt identity for one completed reattestation."""

    receipt_path: Path | None
    receipt_sha256: str | None
    status: str
    source_identity_sha256: str | None


def reattest_norgate_sp500_membership_snapshot(
    *,
    snapshot_dir: Path,
    market_data_root: Path,
    artifact_root: Path,
    repo_root: Path,
    attempt_id: str,
    created_at_utc: datetime,
) -> NorgateMembershipReattestationResult:
    """Read an immutable snapshot twice and publish one redacted receipt.

    The existing verifier is deliberately the only snapshot reader used here.
    The receipt carries aggregate identity facts only and is created with an
    exclusive write, so reattestation never replaces an earlier receipt.
    """

    normalized_attempt_id = _attempt_id(attempt_id)
    timestamp = _utc_timestamp(created_at_utc)
    destination = _external_artifact_root(
        artifact_root,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    receipt_path = destination / f"{normalized_attempt_id}.norgate-membership-reattest.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        raise FileExistsError("Norgate membership reattestation receipt already exists")
    if not Path(snapshot_dir).is_dir():
        return _failed_result("input_unavailable")

    try:
        before = verify_norgate_sp500_membership_snapshot(
            Path(snapshot_dir),
            market_data_root=Path(market_data_root),
            repo_root=Path(repo_root),
        )
        before_scope = _read_verified_ineligible_scope(Path(snapshot_dir), before)
        before_identity = _source_identity(before, scope=before_scope)
        after = verify_norgate_sp500_membership_snapshot(
            Path(snapshot_dir),
            market_data_root=Path(market_data_root),
            repo_root=Path(repo_root),
        )
        after_scope = _read_verified_ineligible_scope(Path(snapshot_dir), after)
        after_identity = _source_identity(after, scope=after_scope)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return _failed_result("input_unavailable")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _failed_result("integrity_mismatch")
    if before_identity != after_identity:
        return _failed_result("integrity_mismatch")

    source_identity_sha256 = _sha256(_json_bytes(before_identity))
    receipt = {
        "schema_version": NORGATE_MEMBERSHIP_REATTESTATION_SCHEMA_VERSION,
        "kind": NORGATE_MEMBERSHIP_REATTESTATION_KIND,
        "attempt_id": normalized_attempt_id,
        "created_at_utc": timestamp,
        "status": "reattested",
        "source_read_only": True,
        "source_identity": {
            "pre_verification_sha256": source_identity_sha256,
            "post_verification_sha256": _sha256(_json_bytes(after_identity)),
            "unchanged": True,
        },
        "snapshot": {
            "dataset_id": before.dataset_id,
            "dataset_sha256": before.dataset_hash,
            "manifest_sha256": before.manifest_hash,
            "candidate_count": before.candidate_count,
            "membership_row_count": before.membership_row_count,
            "actual_sparse_date_window": {
                "start": before.actual_start.isoformat(),
                "end": before.actual_end.isoformat(),
            },
            "package": {"name": "norgatedata", "version": before.package_version},
        },
        "scope": before_scope,
    }
    receipt_bytes = _json_bytes(receipt)
    _write_immutable_json(receipt_path, receipt_bytes)
    return NorgateMembershipReattestationResult(
        receipt_path=receipt_path,
        receipt_sha256=_sha256(receipt_bytes),
        status="reattested",
        source_identity_sha256=source_identity_sha256,
    )


def _source_identity(
    result: NorgateMembershipSnapshotResult, *, scope: dict[str, bool]
) -> dict[str, Any]:
    return {
        "dataset_id": result.dataset_id,
        "dataset_sha256": result.dataset_hash,
        "manifest_sha256": result.manifest_hash,
        "candidate_count": result.candidate_count,
        "membership_row_count": result.membership_row_count,
        "actual_sparse_date_window": {
            "start": result.actual_start.isoformat(),
            "end": result.actual_end.isoformat(),
        },
        "package_version": result.package_version,
        "scope": scope,
    }


def _read_verified_ineligible_scope(
    snapshot_dir: Path, result: NorgateMembershipSnapshotResult
) -> dict[str, bool]:
    manifest_bytes = (Path(snapshot_dir) / "manifest.json").read_bytes()
    if _sha256(manifest_bytes) != result.manifest_hash:
        raise ValueError("Norgate membership manifest changed during reattestation")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("scope"), dict):
        raise ValueError("Norgate membership scope is invalid")
    scope = manifest["scope"]
    if any(scope.get(flag) is not False for flag in _INELIGIBLE_SCOPE_FLAGS):
        raise ValueError("Norgate membership scope is not ineligible")
    return {flag: False for flag in _INELIGIBLE_SCOPE_FLAGS}


def _external_artifact_root(
    artifact_root: Path, *, market_data_root: Path, repo_root: Path
) -> Path:
    root = _existing_directory_without_symlink(Path(artifact_root), label="artifact root")
    repository = _existing_directory_without_symlink(Path(repo_root), label="repository root")
    market_data = _existing_directory_without_symlink(
        Path(market_data_root), label="market-data root"
    )
    if root.is_relative_to(repository):
        raise NorgateMembershipReattestationError(
            "Norgate membership artifact root must stay outside Git"
        )
    if root.is_relative_to(market_data):
        raise NorgateMembershipReattestationError(
            "Norgate membership artifact root must stay outside market data"
        )
    return root


def _existing_directory_without_symlink(path: Path, *, label: str) -> Path:
    raw = Path(path)
    for ancestor in (raw, *raw.parents):
        if ancestor.exists() and ancestor.is_symlink():
            raise NorgateMembershipReattestationError(
                f"Norgate membership {label} must not traverse a symlink"
            )
    resolved = raw.resolve()
    if not resolved.is_dir():
        raise NorgateMembershipReattestationError(
            f"Norgate membership {label} must be an existing directory"
        )
    return resolved


def _write_immutable_json(path: Path, content: bytes) -> None:
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise FileExistsError("Norgate membership reattestation receipt already exists")
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        raise FileExistsError("Norgate membership reattestation receipt already exists") from None


def _attempt_id(value: str) -> str:
    candidate = str(value)
    if not _ATTEMPT_ID_PATTERN.fullmatch(candidate):
        raise ValueError("Norgate membership reattestation attempt id is invalid")
    return candidate


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Norgate membership reattestation timestamp must be UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _failed_result(status: str) -> NorgateMembershipReattestationResult:
    return NorgateMembershipReattestationResult(
        receipt_path=None,
        receipt_sha256=None,
        status=status,
        source_identity_sha256=None,
    )

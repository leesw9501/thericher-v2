"""Source-safe host readiness bridge for the locally installed Norgate client."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
DEFAULT_RECEIPT_ROOT = DEFAULT_ARTIFACT_ROOT / "data-receipts" / "norgate-host-readiness-bridge"
DEFAULT_CANDIDATE_ROOTS = (
    Path(r"C:\ProgramData\Norgate Data"),
    Path(r"D:\market_data\us_equities\norgate_us_platinum_trial"),
)
NORGATE_HOST_READINESS_BRIDGE_ID = "norgate-host-readiness-bridge-v1"
NORGATE_US_DATABASE_NAME = "US Equities"
_CORE_FILE = "core_us.ngdb"
_ROOT_TOLERANCE_SECONDS = 300
_SAFE_LABEL = re.compile(r"[A-Za-z0-9_-]{1,100}", re.ASCII)

LocalApiStatus = Literal["ready", "not_ready", "unavailable"]
CatalogStatus = Literal["configured", "not_configured", "unavailable", "not_checked"]
RootResolution = Literal["one", "none", "multiple", "not_checked"]
BridgeStatus = Literal["ready", "input_unavailable"]
HostRuntimeStatus = Literal["available", "unavailable"]


@dataclass(frozen=True)
class NorgateHostReadiness:
    """Categorical readiness result that retains no source or configuration values."""

    status: BridgeStatus
    reason: str
    host_runtime_status: HostRuntimeStatus
    local_api_status: LocalApiStatus
    us_equities_catalog_status: CatalogStatus
    source_update_metadata_status: Literal["available", "unavailable", "not_checked"]
    active_root_resolution: RootResolution

    def __post_init__(self) -> None:
        expected_states = {
            "ready": ("ready", "available", "ready", "configured", "available", "one"),
            "host_runtime_unavailable": (
                "input_unavailable",
                "unavailable",
                "unavailable",
                "not_checked",
                "not_checked",
                "not_checked",
            ),
            "local_client_unavailable": (
                "input_unavailable",
                "available",
                "unavailable",
                "not_checked",
                "not_checked",
                "not_checked",
            ),
            "local_api_not_ready": (
                "input_unavailable",
                "available",
                "not_ready",
                "not_checked",
                "not_checked",
                "not_checked",
            ),
            "database_catalog_unavailable": (
                "input_unavailable",
                "available",
                "ready",
                "unavailable",
                "not_checked",
                "not_checked",
            ),
            "us_equities_not_configured": (
                "input_unavailable",
                "available",
                "ready",
                "not_configured",
                "not_checked",
                "not_checked",
            ),
            "source_update_metadata_unavailable": (
                "input_unavailable",
                "available",
                "ready",
                "configured",
                "unavailable",
                "not_checked",
            ),
            "active_root_unresolved": (
                "input_unavailable",
                "available",
                "ready",
                "configured",
                "available",
                "none",
            ),
            "active_root_ambiguous": (
                "input_unavailable",
                "available",
                "ready",
                "configured",
                "available",
                "multiple",
            ),
        }
        expected = expected_states.get(self.reason)
        if expected is None:
            raise ValueError("Norgate host readiness reason is invalid")
        actual = (
            self.status,
            self.host_runtime_status,
            self.local_api_status,
            self.us_equities_catalog_status,
            self.source_update_metadata_status,
            self.active_root_resolution,
        )
        if actual != expected:
            raise ValueError("Norgate ready state is inconsistent")

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "host_runtime_status": self.host_runtime_status,
            "local_api_status": self.local_api_status,
            "us_equities_catalog_status": self.us_equities_catalog_status,
            "source_update_metadata_status": self.source_update_metadata_status,
            "active_root_resolution": self.active_root_resolution,
        }


@dataclass(frozen=True)
class NorgateHostReadinessReceipt:
    """External immutable bridge receipt with source-safe categories only."""

    receipt_path: Path
    receipt_sha256: str
    readiness: NorgateHostReadiness

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.readiness.status,
            "reason": self.readiness.reason,
            "host_runtime_status": self.readiness.host_runtime_status,
            "local_api_status": self.readiness.local_api_status,
            "us_equities_catalog_status": self.readiness.us_equities_catalog_status,
            "source_update_metadata_status": self.readiness.source_update_metadata_status,
            "active_root_resolution": self.readiness.active_root_resolution,
            "receipt_sha256": self.receipt_sha256,
        }


ClientLoader = Callable[[], Any]


def assess_norgate_host_readiness(
    *,
    client_loader: ClientLoader,
    candidate_roots: Sequence[Path] = DEFAULT_CANDIDATE_ROOTS,
    root_tolerance_seconds: int = _ROOT_TOLERANCE_SECONDS,
    host_runtime_available: bool = True,
) -> NorgateHostReadiness:
    """Inspect only categorical client/catalog/update/root state in memory."""

    if root_tolerance_seconds < 0:
        raise ValueError("Norgate root tolerance must be non-negative")
    if not host_runtime_available:
        return _unavailable("host_runtime_unavailable", host_runtime_status="unavailable")
    try:
        client = client_loader()
    except Exception:
        return _unavailable("local_client_unavailable")
    try:
        ready = client.status()
    except Exception:
        return _unavailable("local_client_unavailable")
    if ready is not True:
        return _unavailable("local_api_not_ready", local_api_status="not_ready")
    try:
        databases = tuple(client.databases())
    except Exception:
        return _unavailable(
            "database_catalog_unavailable",
            local_api_status="ready",
            catalog_status="unavailable",
        )
    if not all(isinstance(name, str) and name for name in databases):
        return _unavailable(
            "database_catalog_unavailable",
            local_api_status="ready",
            catalog_status="unavailable",
        )
    if NORGATE_US_DATABASE_NAME not in databases:
        return _unavailable(
            "us_equities_not_configured",
            local_api_status="ready",
            catalog_status="not_configured",
        )
    try:
        update_at = _to_utc(client.last_database_update_time(NORGATE_US_DATABASE_NAME))
    except Exception:
        return _unavailable(
            "source_update_metadata_unavailable",
            local_api_status="ready",
            catalog_status="configured",
            update_status="unavailable",
        )
    resolution = _resolve_root(
        update_at,
        candidate_roots=candidate_roots,
        tolerance_seconds=root_tolerance_seconds,
    )
    if resolution == "one":
        return NorgateHostReadiness(
            status="ready",
            reason="ready",
            host_runtime_status="available",
            local_api_status="ready",
            us_equities_catalog_status="configured",
            source_update_metadata_status="available",
            active_root_resolution="one",
        )
    return _unavailable(
        "active_root_unresolved" if resolution == "none" else "active_root_ambiguous",
        local_api_status="ready",
        catalog_status="configured",
        update_status="available",
        root_resolution=resolution,
    )


def build_norgate_host_readiness_receipt(
    *,
    destination: Path | str,
    readiness: NorgateHostReadiness,
    retrieved_at_utc: datetime,
    artifact_root: Path | str = DEFAULT_RECEIPT_ROOT,
    repo_root: Path | str | None = None,
) -> NorgateHostReadinessReceipt:
    """Write or reattach one aggregate bridge receipt outside the repository."""

    root = _require_external_root(artifact_root, repo_root=repo_root)
    target = _receipt_path(destination, root=root)
    retrieved_at = _to_utc(retrieved_at_utc)
    payload = {
        "schema_version": 1,
        "receipt_id": NORGATE_HOST_READINESS_BRIDGE_ID,
        "status": readiness.status,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "readiness": readiness.safe_payload(),
        "safety": {
            "credentials_read": False,
            "network_access": False,
            "raw_market_data_read": False,
            "price_membership_listing_or_corporate_action_calls": False,
            "database_paths_retained": False,
            "subscription_values_retained": False,
            "kis_or_broker_called": False,
            "model_or_gpu_used": False,
            "git_tracked_files_changed": False,
        },
        "limitations": [
            "local_client_state_only",
            "no_source_data_capability_proven",
            "no_subscription_or_rights_conclusion",
            "not_a_model_or_paper_input",
        ],
    }
    _write_or_verify(target, payload)
    return NorgateHostReadinessReceipt(
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
        readiness=readiness,
    )


def default_norgate_host_readiness_receipt_path(run_label: str) -> Path:
    label = _safe_run_label(run_label)
    return DEFAULT_RECEIPT_ROOT / f"bridge-{label}.json"


def read_norgate_host_readiness_receipt(
    *,
    source: Path | str,
    artifact_root: Path | str = DEFAULT_RECEIPT_ROOT,
    repo_root: Path | str | None = None,
) -> NorgateHostReadinessReceipt:
    """Reattach a bridge receipt without importing Norgate or reading source data."""

    root = _require_external_root(artifact_root, repo_root=repo_root)
    target = _receipt_path(source, root=root)
    if target.is_symlink() or not target.is_file():
        raise ValueError("Norgate bridge receipt is unavailable")
    try:
        document = json.loads(target.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate bridge receipt is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("Norgate bridge receipt is invalid")
    _validate_receipt_document(document)
    readiness_document = document["readiness"]
    assert isinstance(readiness_document, dict)
    readiness = NorgateHostReadiness(
        status=readiness_document["status"],
        reason=readiness_document["reason"],
        host_runtime_status=readiness_document["host_runtime_status"],
        local_api_status=readiness_document["local_api_status"],
        us_equities_catalog_status=readiness_document["us_equities_catalog_status"],
        source_update_metadata_status=readiness_document["source_update_metadata_status"],
        active_root_resolution=readiness_document["active_root_resolution"],
    )
    return NorgateHostReadinessReceipt(
        receipt_path=target,
        receipt_sha256=_sha256(target.read_bytes()),
        readiness=readiness,
    )


def _unavailable(
    reason: str,
    *,
    host_runtime_status: HostRuntimeStatus = "available",
    local_api_status: LocalApiStatus = "unavailable",
    catalog_status: CatalogStatus = "not_checked",
    update_status: Literal["available", "unavailable", "not_checked"] = "not_checked",
    root_resolution: RootResolution = "not_checked",
) -> NorgateHostReadiness:
    return NorgateHostReadiness(
        status="input_unavailable",
        reason=reason,
        host_runtime_status=host_runtime_status,
        local_api_status=local_api_status,
        us_equities_catalog_status=catalog_status,
        source_update_metadata_status=update_status,
        active_root_resolution=root_resolution,
    )


def _resolve_root(
    update_at: datetime,
    *,
    candidate_roots: Sequence[Path],
    tolerance_seconds: int,
) -> RootResolution:
    matches = 0
    for root in candidate_roots:
        candidate = Path(root)
        core = candidate / _CORE_FILE
        if (
            candidate.is_symlink()
            or core.is_symlink()
            or not candidate.is_dir()
            or not core.is_file()
        ):
            continue
        try:
            modified_at = datetime.fromtimestamp(core.stat().st_mtime, UTC)
        except OSError:
            continue
        if abs((modified_at - update_at).total_seconds()) <= tolerance_seconds:
            matches += 1
    if matches == 1:
        return "one"
    return "none" if matches == 0 else "multiple"


def _to_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Norgate update time must be timezone-aware")
    return value.astimezone(UTC)


def _require_external_root(value: Path | str, *, repo_root: Path | str | None) -> Path:
    root = Path(value).resolve(strict=False)
    repository = Path(repo_root).resolve(strict=False) if repo_root is not None else _REPO_ROOT
    if root.is_relative_to(repository):
        raise ValueError("Norgate bridge artifact root must stay outside Git")
    return root


def _receipt_path(destination: Path | str, *, root: Path) -> Path:
    candidate = Path(destination)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )
    if not resolved.is_relative_to(root):
        raise ValueError("Norgate bridge receipt must stay under its artifact root")
    if not resolved.name.startswith("bridge-") or resolved.suffix != ".json":
        raise ValueError("Norgate bridge receipt name is invalid")
    return resolved


def _write_or_verify(destination: Path, payload: dict[str, object]) -> None:
    encoded = _json_bytes(payload)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise ValueError("Norgate bridge receipt conflicts with existing evidence")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _safe_run_label(value: str) -> str:
    if not _SAFE_LABEL.fullmatch(value):
        raise ValueError("Norgate bridge run label is invalid")
    return value


def _validate_receipt_document(document: dict[str, object]) -> None:
    required = {
        "schema_version",
        "receipt_id",
        "status",
        "retrieved_at_utc",
        "readiness",
        "safety",
        "limitations",
    }
    if set(document) != required:
        raise ValueError("Norgate bridge receipt schema is invalid")
    if (
        document["schema_version"] != 1
        or document["receipt_id"] != NORGATE_HOST_READINESS_BRIDGE_ID
    ):
        raise ValueError("Norgate bridge receipt identity is invalid")
    if not isinstance(document["retrieved_at_utc"], str):
        raise ValueError("Norgate bridge receipt timestamp is invalid")
    try:
        parsed_timestamp = datetime.fromisoformat(document["retrieved_at_utc"])
    except ValueError as exc:
        raise ValueError("Norgate bridge receipt timestamp is invalid") from exc
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() != UTC.utcoffset(None):
        raise ValueError("Norgate bridge receipt timestamp is invalid")
    readiness = document["readiness"]
    if not isinstance(readiness, dict) or set(readiness) != {
        "status",
        "reason",
        "host_runtime_status",
        "local_api_status",
        "us_equities_catalog_status",
        "source_update_metadata_status",
        "active_root_resolution",
    }:
        raise ValueError("Norgate bridge readiness schema is invalid")
    if document["status"] != readiness["status"]:
        raise ValueError("Norgate bridge receipt status is invalid")
    safety = document["safety"]
    expected_safety = {
        "credentials_read": False,
        "network_access": False,
        "raw_market_data_read": False,
        "price_membership_listing_or_corporate_action_calls": False,
        "database_paths_retained": False,
        "subscription_values_retained": False,
        "kis_or_broker_called": False,
        "model_or_gpu_used": False,
        "git_tracked_files_changed": False,
    }
    if safety != expected_safety:
        raise ValueError("Norgate bridge receipt safety is invalid")
    if document["limitations"] != [
        "local_client_state_only",
        "no_source_data_capability_proven",
        "no_subscription_or_rights_conclusion",
        "not_a_model_or_paper_input",
    ]:
        raise ValueError("Norgate bridge receipt limitations are invalid")


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()

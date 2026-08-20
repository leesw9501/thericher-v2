"""Bounded, source-safe reconciliation for the local Norgate trial host."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from thericher_v2.data.norgate_host_readiness_bridge import (
    DEFAULT_CANDIDATE_ROOTS,
    DEFAULT_RECEIPT_ROOT,
    assess_norgate_host_readiness,
    read_norgate_host_readiness_receipt,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_RECONCILIATION_ROOT = (
    DEFAULT_MODEL_ARTIFACT_ROOT
    / "data-receipts"
    / "norgate-trial-host-readiness-reconciliation"
)
NORGATE_TRIAL_HOST_READINESS_RECONCILIATION_ID = (
    "norgate-trial-host-readiness-reconciliation-v1"
)
DEFAULT_UPDATER_EXECUTABLE_CANDIDATES = (
    Path("C:/Program Files/Norgate Data/NDU.exe"),
    Path("C:/Program Files (x86)/Norgate Data/NDU.exe"),
    Path("C:/ProgramData/Norgate Data/NDU.exe"),
)
_SAFE_LABEL = re.compile(r"[A-Za-z0-9_-]{1,100}", re.ASCII)

DiagnosticStatus = Literal["ready", "input_unavailable"]
ModuleImportStatus = Literal["available", "unavailable"]
LocalApiStatus = Literal["ready", "not_ready", "unavailable"]
UpdaterMarkerStatus = Literal["observed", "not_observed", "not_checked", "unavailable"]
MetadataStatus = Literal["ready", "not_ready", "not_checked", "unavailable"]
RootStatus = Literal["one", "none", "multiple", "not_checked"]
DiagnosisDefaults = tuple[
    DiagnosticStatus,
    str,
    ModuleImportStatus,
    LocalApiStatus,
    UpdaterMarkerStatus,
    UpdaterMarkerStatus,
    MetadataStatus,
    RootStatus,
]

_REASON_TABLE: Mapping[str, DiagnosisDefaults] = {
    "runtime_import_unavailable": (
        "input_unavailable",
        "restore_isolated_norgate_python_package",
        "unavailable",
        "unavailable",
        "not_checked",
        "not_checked",
        "not_checked",
        "not_checked",
    ),
    "local_api_not_ready_updater_not_observed": (
        "input_unavailable",
        "ensure_norgate_data_updater_is_installed_and_running",
        "available",
        "not_ready",
        "not_observed",
        "not_observed",
        "not_checked",
        "not_checked",
    ),
    "local_api_not_ready_updater_start_required": (
        "input_unavailable",
        "start_norgate_data_updater_then_retry_once",
        "available",
        "not_ready",
        "observed",
        "not_observed",
        "not_checked",
        "not_checked",
    ),
    "local_api_not_ready": (
        "input_unavailable",
        "restore_local_norgate_api_readiness",
        "available",
        "not_ready",
        "not_checked",
        "observed",
        "not_checked",
        "not_checked",
    ),
    "configured_database_not_observed": (
        "input_unavailable",
        "configure_local_norgate_us_equities_database",
        "available",
        "ready",
        "not_checked",
        "not_checked",
        "not_checked",
        "not_checked",
    ),
    "diagnosis_unavailable": (
        "input_unavailable",
        "restore_local_norgate_api_readiness",
        "available",
        "unavailable",
        "not_checked",
        "not_checked",
        "not_checked",
        "not_checked",
    ),
    "ready_for_date_indexed_probe": (
        "ready",
        "run_bounded_norgate_date_indexed_capability_probe",
        "available",
        "ready",
        "not_checked",
        "not_checked",
        "ready",
        "one",
    ),
}
_SUMMARY_SAFETY = {
    "credentials_read": False,
    "network_access": False,
    "raw_market_data_read": False,
    "paths_or_configuration_values_retained": False,
    "kis_or_broker_called": False,
    "docker_called": False,
    "model_or_gpu_used": False,
}
_SUMMARY_LIMITATIONS = (
    "local_host_state_only",
    "no_source_data_or_trial_rights_conclusion",
    "not_a_model_or_paper_input",
)
_VALIDATION_SCOPE = {
    "host_reinvoked": False,
    "network_access": False,
    "raw_market_data_read": False,
    "credentials_read": False,
    "kis_or_broker_called": False,
    "model_or_gpu_used": False,
}


@dataclass(frozen=True, slots=True)
class NorgateTrialHostReadinessDiagnosis:
    """Categorial local-host state with no source rows, paths, or secrets."""

    status: DiagnosticStatus
    reason: str
    recovery: str
    prior_receipt_sha256: str
    module_import_status: ModuleImportStatus
    local_api_status: LocalApiStatus
    updater_installation_marker_status: UpdaterMarkerStatus
    updater_process_status: UpdaterMarkerStatus
    metadata_status: MetadataStatus
    active_root_resolution: RootStatus

    def __post_init__(self) -> None:
        expected = _REASON_TABLE.get(self.reason)
        actual = (
            self.status,
            self.recovery,
            self.module_import_status,
            self.local_api_status,
            self.updater_installation_marker_status,
            self.updater_process_status,
            self.metadata_status,
            self.active_root_resolution,
        )
        if expected is None or actual != expected or not _is_sha256(self.prior_receipt_sha256):
            raise ValueError("Norgate trial host readiness diagnosis is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "recovery": self.recovery,
            "prior_receipt_sha256": self.prior_receipt_sha256,
            "module_import_status": self.module_import_status,
            "local_api_status": self.local_api_status,
            "updater_installation_marker_status": self.updater_installation_marker_status,
            "updater_process_status": self.updater_process_status,
            "metadata_status": self.metadata_status,
            "active_root_resolution": self.active_root_resolution,
        }


@dataclass(frozen=True, slots=True)
class NorgateTrialHostReadinessReconciliationReceipt:
    """One external source-safe reconciliation result."""

    summary_path: Path
    summary_sha256: str
    diagnosis: NorgateTrialHostReadinessDiagnosis

    def __post_init__(self) -> None:
        if not _is_sha256(self.summary_sha256):
            raise ValueError("Norgate trial host readiness receipt is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.diagnosis.status,
            "reason": self.diagnosis.reason,
            "recovery": self.diagnosis.recovery,
            "summary_sha256": self.summary_sha256,
        }


@dataclass(frozen=True, slots=True)
class NorgateTrialHostReadinessValidationReceipt:
    """Independent schema and identity validation of one reconciliation receipt."""

    validation_path: Path
    summary_sha256: str
    prior_receipt_sha256: str
    status: Literal["verified"]

    def __post_init__(self) -> None:
        if (
            self.status != "verified"
            or not _is_sha256(self.summary_sha256)
            or not _is_sha256(self.prior_receipt_sha256)
        ):
            raise ValueError("Norgate trial host readiness validation is invalid")


ClientLoader = Callable[[], Any]
MarkerProbe = Callable[[], UpdaterMarkerStatus]


def diagnose_norgate_trial_host_readiness(
    *,
    prior_receipt_source: Path | str,
    prior_receipt_root: Path | str = DEFAULT_RECEIPT_ROOT,
    client_loader: ClientLoader,
    updater_installation_marker_probe: MarkerProbe,
    updater_process_probe: MarkerProbe,
    candidate_roots: Sequence[Path] = DEFAULT_CANDIDATE_ROOTS,
    repo_root: Path | str | None = None,
) -> NorgateTrialHostReadinessDiagnosis:
    """Reattach the prior bridge before one safe local-host classification."""

    prior = read_norgate_host_readiness_receipt(
        source=prior_receipt_source,
        artifact_root=prior_receipt_root,
        repo_root=repo_root,
    )
    if (
        prior.readiness.status != "input_unavailable"
        or prior.readiness.reason != "local_api_not_ready"
    ):
        raise ValueError("Norgate reconciliation prior receipt is not eligible")
    try:
        client = client_loader()
    except Exception:
        return _diagnosis(
            reason="runtime_import_unavailable",
            prior_receipt_sha256=prior.receipt_sha256,
        )
    try:
        status = client.status()
    except Exception:
        return _diagnosis(
            reason="diagnosis_unavailable",
            prior_receipt_sha256=prior.receipt_sha256,
        )
    if status is not True:
        installation = _marker_status(updater_installation_marker_probe)
        process = _marker_status(updater_process_probe)
        if installation == "not_observed" and process == "not_observed":
            reason = "local_api_not_ready_updater_not_observed"
        elif installation == "observed" and process == "not_observed":
            reason = "local_api_not_ready_updater_start_required"
        elif process == "observed":
            reason = "local_api_not_ready"
        else:
            return _diagnosis(
                reason="diagnosis_unavailable",
                prior_receipt_sha256=prior.receipt_sha256,
            )
        return _diagnosis(reason=reason, prior_receipt_sha256=prior.receipt_sha256)

    readiness = assess_norgate_host_readiness(
        client_loader=lambda: _CachedStatusClient(client, status),
        candidate_roots=candidate_roots,
    )
    if readiness.status == "ready":
        return _diagnosis(
            reason="ready_for_date_indexed_probe",
            prior_receipt_sha256=prior.receipt_sha256,
        )
    if readiness.reason == "us_equities_not_configured":
        return _diagnosis(
            reason="configured_database_not_observed",
            prior_receipt_sha256=prior.receipt_sha256,
        )
    return _diagnosis(
        reason="diagnosis_unavailable",
        prior_receipt_sha256=prior.receipt_sha256,
    )


def run_norgate_trial_host_readiness_reconciliation(
    *,
    run_label: str,
    retrieved_at_utc: datetime,
    prior_receipt_source: Path | str,
    prior_receipt_root: Path | str,
    artifact_root: Path | str = DEFAULT_RECONCILIATION_ROOT,
    client_loader: ClientLoader,
    updater_installation_marker_probe: MarkerProbe,
    updater_process_probe: MarkerProbe,
    candidate_roots: Sequence[Path] = DEFAULT_CANDIDATE_ROOTS,
    repo_root: Path | str | None = None,
) -> NorgateTrialHostReadinessReconciliationReceipt:
    """Write one idempotent source-safe reconciliation receipt outside Git."""

    root = _require_external_root(artifact_root, repo_root=repo_root, create=True)
    label = _safe_label(run_label)
    diagnosis = diagnose_norgate_trial_host_readiness(
        prior_receipt_source=prior_receipt_source,
        prior_receipt_root=prior_receipt_root,
        client_loader=client_loader,
        updater_installation_marker_probe=updater_installation_marker_probe,
        updater_process_probe=updater_process_probe,
        candidate_roots=candidate_roots,
        repo_root=repo_root,
    )
    target = root / f"diagnosis-{label}.json"
    payload = _summary_payload(
        diagnosis=diagnosis,
        retrieved_at_utc=_utc_datetime(retrieved_at_utc),
    )
    _write_or_verify(target, payload)
    return NorgateTrialHostReadinessReconciliationReceipt(
        summary_path=target,
        summary_sha256=_sha256(target.read_bytes()),
        diagnosis=diagnosis,
    )


def validate_norgate_trial_host_readiness_reconciliation(
    *,
    run_label: str,
    artifact_root: Path | str = DEFAULT_RECONCILIATION_ROOT,
    repo_root: Path | str | None = None,
) -> NorgateTrialHostReadinessValidationReceipt:
    """Independently validate one persisted receipt without host or source reads."""

    root = _require_external_root(artifact_root, repo_root=repo_root, create=False)
    label = _safe_label(run_label)
    summary_path = root / f"diagnosis-{label}.json"
    receipt = _read_receipt(summary_path, root=root)
    validation_path = root / f"validation-{label}.json"
    payload = {
        "schema_version": 1,
        "receipt_id": NORGATE_TRIAL_HOST_READINESS_RECONCILIATION_ID,
        "status": "verified",
        "summary_sha256": receipt.summary_sha256,
        "prior_receipt_sha256": receipt.diagnosis.prior_receipt_sha256,
        **_VALIDATION_SCOPE,
    }
    _write_or_verify(validation_path, payload)
    return NorgateTrialHostReadinessValidationReceipt(
        validation_path=validation_path,
        summary_sha256=receipt.summary_sha256,
        prior_receipt_sha256=receipt.diagnosis.prior_receipt_sha256,
        status="verified",
    )


def default_norgate_trial_host_readiness_summary_path(run_label: str) -> Path:
    """Return the external summary location for a unique diagnostic label."""

    return DEFAULT_RECONCILIATION_ROOT / f"diagnosis-{_safe_label(run_label)}.json"


def default_updater_installation_marker_status(
    candidates: Sequence[Path] = DEFAULT_UPDATER_EXECUTABLE_CANDIDATES,
) -> UpdaterMarkerStatus:
    """Return only whether a fixed updater marker is present; never retain paths."""

    return "observed" if any(Path(path).is_file() for path in candidates) else "not_observed"


def _diagnosis(
    *,
    reason: str,
    prior_receipt_sha256: str,
) -> NorgateTrialHostReadinessDiagnosis:
    defaults = _REASON_TABLE
    try:
        (
            status,
            recovery,
            module_import_status,
            local_api_status,
            installation,
            process,
            metadata,
            root,
        ) = defaults[reason]
    except KeyError as exc:
        raise ValueError("Norgate reconciliation reason is invalid") from exc
    return NorgateTrialHostReadinessDiagnosis(
        status=status,
        reason=reason,
        recovery=recovery,
        prior_receipt_sha256=prior_receipt_sha256,
        module_import_status=module_import_status,
        local_api_status=local_api_status,
        updater_installation_marker_status=installation,
        updater_process_status=process,
        metadata_status=metadata,
        active_root_resolution=root,
    )


class _CachedStatusClient:
    """Expose a first status result without making the local API answer twice."""

    def __init__(self, client: Any, status: object) -> None:
        self._client = client
        self._status = status

    def status(self) -> object:
        return self._status

    def __getattr__(self, name: str) -> object:
        return getattr(self._client, name)


def _marker_status(probe: MarkerProbe) -> UpdaterMarkerStatus:
    try:
        value = probe()
    except Exception:
        return "unavailable"
    if value not in {"observed", "not_observed", "not_checked", "unavailable"}:
        return "unavailable"
    return value


def _summary_payload(
    *,
    diagnosis: NorgateTrialHostReadinessDiagnosis,
    retrieved_at_utc: datetime,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "receipt_id": NORGATE_TRIAL_HOST_READINESS_RECONCILIATION_ID,
        "retrieved_at_utc": retrieved_at_utc.isoformat(),
        "diagnosis": diagnosis.safe_payload(),
        "safety": dict(_SUMMARY_SAFETY),
        "limitations": list(_SUMMARY_LIMITATIONS),
    }


def _read_receipt(
    summary_path: Path,
    *,
    root: Path,
) -> NorgateTrialHostReadinessReconciliationReceipt:
    if (
        not summary_path.is_relative_to(root)
        or summary_path.is_symlink()
        or not summary_path.is_file()
    ):
        raise ValueError("Norgate reconciliation receipt is unavailable")
    try:
        document = json.loads(summary_path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Norgate reconciliation receipt is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("Norgate reconciliation receipt is invalid")
    _validate_summary_document(document)
    diagnosis_document = document["diagnosis"]
    assert isinstance(diagnosis_document, dict)
    diagnosis = NorgateTrialHostReadinessDiagnosis(
        status=diagnosis_document["status"],
        reason=diagnosis_document["reason"],
        recovery=diagnosis_document["recovery"],
        prior_receipt_sha256=diagnosis_document["prior_receipt_sha256"],
        module_import_status=diagnosis_document["module_import_status"],
        local_api_status=diagnosis_document["local_api_status"],
        updater_installation_marker_status=diagnosis_document[
            "updater_installation_marker_status"
        ],
        updater_process_status=diagnosis_document["updater_process_status"],
        metadata_status=diagnosis_document["metadata_status"],
        active_root_resolution=diagnosis_document["active_root_resolution"],
    )
    return NorgateTrialHostReadinessReconciliationReceipt(
        summary_path=summary_path,
        summary_sha256=_sha256(summary_path.read_bytes()),
        diagnosis=diagnosis,
    )


def _validate_summary_document(document: Mapping[str, object]) -> None:
    if set(document) != {
        "schema_version",
        "receipt_id",
        "retrieved_at_utc",
        "diagnosis",
        "safety",
        "limitations",
    }:
        raise ValueError("Norgate reconciliation receipt schema is invalid")
    if (
        document["schema_version"] != 1
        or document["receipt_id"] != NORGATE_TRIAL_HOST_READINESS_RECONCILIATION_ID
        or not isinstance(document["retrieved_at_utc"], str)
    ):
        raise ValueError("Norgate reconciliation receipt identity is invalid")
    try:
        timestamp = datetime.fromisoformat(document["retrieved_at_utc"])
    except ValueError as exc:
        raise ValueError("Norgate reconciliation receipt timestamp is invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(None):
        raise ValueError("Norgate reconciliation receipt timestamp is invalid")
    diagnosis = document["diagnosis"]
    required_diagnosis = {
        "status",
        "reason",
        "recovery",
        "prior_receipt_sha256",
        "module_import_status",
        "local_api_status",
        "updater_installation_marker_status",
        "updater_process_status",
        "metadata_status",
        "active_root_resolution",
    }
    if not isinstance(diagnosis, dict) or set(diagnosis) != required_diagnosis:
        raise ValueError("Norgate reconciliation diagnosis schema is invalid")
    if document["safety"] != _SUMMARY_SAFETY:
        raise ValueError("Norgate reconciliation safety is invalid")
    if document["limitations"] != list(_SUMMARY_LIMITATIONS):
        raise ValueError("Norgate reconciliation limitations are invalid")


def _require_external_root(
    value: Path | str,
    *,
    repo_root: Path | str | None,
    create: bool,
) -> Path:
    root = Path(value).resolve(strict=False)
    repository = Path(repo_root).resolve(strict=False) if repo_root is not None else _REPO_ROOT
    if root.is_relative_to(repository):
        raise ValueError("Norgate reconciliation artifacts must stay outside Git")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Norgate reconciliation artifact root is invalid")
    return root


def _write_or_verify(destination: Path, payload: Mapping[str, object]) -> None:
    encoded = _canonical_json(payload)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("Norgate reconciliation receipt conflicts with evidence")
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


def _safe_label(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_LABEL.fullmatch(value):
        raise ValueError("Norgate reconciliation run label is invalid")
    return value


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Norgate reconciliation timestamp is invalid")
    return value.astimezone(UTC)


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )

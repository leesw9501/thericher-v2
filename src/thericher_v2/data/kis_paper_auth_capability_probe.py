"""Source-safe receipt contract for one KIS Paper token capability attempt."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_PAPER_AUTH_CAPABILITY_PROBE_KIND = "kis_paper_auth_capability_probe"
KIS_PAPER_AUTH_CAPABILITY_PROBE_DIRECTORY = "kis-paper-auth-capability-probe-v1"

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_due",
        "response_invalid",
        "token_request_not_due",
        "transport_failure",
        "control_unavailable",
    }
)

ProbeStatus = Literal["authenticated", "unavailable"]


@dataclass(frozen=True, slots=True)
class KisPaperAuthCapabilityProbeOutcome:
    """One token-only outcome with no bearer token or credential data."""

    status: ProbeStatus
    observed_at: datetime
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_utc(self.observed_at, "auth capability observation")
        if (
            self.status not in {"authenticated", "unavailable"}
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS Paper auth capability outcome is invalid")
        if self.status == "authenticated":
            if self.reason is not None:
                raise ValueError("authenticated KIS Paper auth capability outcome is invalid")
            return
        if self.reason not in _SAFE_FAILURE_REASONS:
            raise ValueError("unavailable KIS Paper auth capability outcome is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "status": self.status,
            "observed_at_bucket": self.observed_at.strftime("%Y-%m-%dT%H:00Z"),
            "route_isolation": {
                "paper_only": True,
                "token_only": True,
                "market_data_requested": False,
                "account_endpoints_used": False,
                "position_endpoints_used": False,
                "open_order_endpoints_used": False,
                "quote_endpoints_used": False,
                "order_endpoints_used": False,
                "live_endpoints_used": False,
                "token_value_retained": False,
                "credentials_written": False,
                "raw_broker_body_retained": False,
            },
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True, slots=True)
class KisPaperAuthCapabilityProbeRun:
    """Immutable external receipt location for one token-only observation."""

    outcome: KisPaperAuthCapabilityProbeOutcome
    receipt_path: Path
    receipt_sha256: str

    def __post_init__(self) -> None:
        if self.receipt_path.name != "receipt.json" or not _is_sha256(self.receipt_sha256):
            raise ValueError("KIS Paper auth capability probe run is invalid")


def categorize_kis_paper_auth_capability_error(error: BaseException) -> str:
    """Map exceptions to the fixed source-safe outcome taxonomy."""

    reason = str(error)
    if isinstance(error, KisPaperMarketDataError) and reason in _SAFE_FAILURE_REASONS:
        return reason
    return "transport_failure"


def write_kis_paper_auth_capability_probe(
    outcome: KisPaperAuthCapabilityProbeOutcome,
    *,
    artifact_root: Path | str,
    repo_root: Path | str,
    run_label: str,
) -> KisPaperAuthCapabilityProbeRun:
    """Persist exactly one source-safe outcome outside the Git workspace."""

    if not isinstance(outcome, KisPaperAuthCapabilityProbeOutcome):
        raise TypeError("KIS Paper auth capability outcome is invalid")
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("KIS Paper auth capability run label is invalid")
    directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        KIS_PAPER_AUTH_CAPABILITY_PROBE_DIRECTORY,
        run_label,
    )
    receipt = {
        "kind": KIS_PAPER_AUTH_CAPABILITY_PROBE_KIND,
        "outcome": outcome.safe_payload(),
        "artifact_policy": {
            "credentials_in_receipt": False,
            "token_in_receipt": False,
            "raw_broker_body_in_receipt": False,
            "account_data_in_receipt": False,
            "repo_storage_allowed": False,
        },
    }
    receipt_path, receipt_sha256 = _write_immutable_json(directory / "receipt.json", receipt)
    return KisPaperAuthCapabilityProbeRun(
        outcome=outcome,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
    )


def _write_immutable_json(path: Path, payload: Mapping[str, object]) -> tuple[Path, str]:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("KIS Paper auth capability receipt path is invalid")
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("KIS Paper auth capability receipt conflicts")
        return path, digest
    staging = path.with_name(f".{path.name}.{uuid.uuid4().hex}.stage")
    try:
        with staging.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)
    return path, digest


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None

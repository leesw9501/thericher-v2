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
from thericher_v2.execution.kis_market_data import KisMarketDataResponse, KisPaperMarketDataError
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
_TOKEN_CODES = frozenset({"EGW00103", "EGW00105", "EGW00132", "EGW00133", "EGW00201"})
_PAGE_FAILURE_REASONS = _SAFE_FAILURE_REASONS | {
    "probe_expired",
    "probe_request_not_allowed",
    "probe_request_budget_exhausted",
    "minute_response_empty",
    "minute_response_invalid",
    "minute_response_rejected",
}


@dataclass(frozen=True, slots=True)
class KisPaperTokenProbeEnvelope:
    """Exact finite field projection, not a provider-cause interpretation."""

    http_status_class: str
    msg_cd: str | None = None
    error_code: str | None = None
    code_relation: str = "absent"

    def __post_init__(self) -> None:
        if self.http_status_class not in {"1xx", "2xx", "3xx", "4xx", "5xx"}:
            raise ValueError("token probe HTTP class is invalid")
        if any(
            code is not None and code not in _TOKEN_CODES for code in (self.msg_cd, self.error_code)
        ):
            raise ValueError("token probe code is invalid")
        if self.code_relation not in {
            "absent",
            "single",
            "agreement",
            "conflict",
            "unclassified",
            "invalid_body",
        }:
            raise ValueError("token probe code relation is invalid")
        codes = (self.msg_cd, self.error_code)
        if self.code_relation in {"absent", "invalid_body", "unclassified"} and any(codes):
            raise ValueError("token probe code relation conflicts")
        if self.code_relation == "single" and sum(code is not None for code in codes) != 1:
            raise ValueError("token probe single code is invalid")
        if self.code_relation == "agreement" and (
            self.msg_cd is None or self.msg_cd != self.error_code
        ):
            raise ValueError("token probe agreement is invalid")
        if (
            self.code_relation == "conflict"
            and self.msg_cd is not None
            and self.msg_cd == self.error_code
        ):
            raise ValueError("token probe conflict is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "http_status_class": self.http_status_class,
            "code_relation": self.code_relation,
            "http_2xx_with_allowlisted_error_code": self.http_status_class == "2xx"
            and (self.msg_cd is not None or self.error_code is not None),
        }
        for name in ("msg_cd", "error_code"):
            code = getattr(self, name)
            if code is not None:
                payload[name] = code
        if self.code_relation in {"single", "agreement"}:
            payload["agreed_code"] = self.msg_cd or self.error_code
        if "EGW00133" in (self.msg_cd, self.error_code):
            payload["semantic_support"] = {"EGW00133": "not_in_verified_catalog"}
        return payload


def project_kis_paper_token_probe_envelope(
    response: KisMarketDataResponse,
) -> KisPaperTokenProbeEnvelope:
    status = response.status_code
    if type(status) is not int or not 100 <= status <= 599:
        raise ValueError("token probe HTTP status is invalid")
    http_class = f"{status // 100}xx"
    try:
        payload = response.payload()
    except KisPaperMarketDataError:
        return KisPaperTokenProbeEnvelope(http_class, code_relation="invalid_body")
    raw = (payload.get("msg_cd"), payload.get("error_code"))
    present = tuple(value is not None for value in raw)
    codes = tuple(
        value if isinstance(value, str) and value in _TOKEN_CODES else None for value in raw
    )
    if not any(present):
        relation = "absent"
    elif all(present) and (type(raw[0]) is not type(raw[1]) or raw[0] != raw[1]):
        relation = "conflict"
    elif all(present) and all(codes):
        relation = "agreement"
    elif not all(present) and any(codes):
        relation = "single"
    else:
        relation = "unclassified"
    return KisPaperTokenProbeEnvelope(http_class, codes[0], codes[1], relation)


@dataclass(frozen=True, slots=True)
class KisPaperAuthPageProbeDetails:
    completed_at: datetime
    token_status: Literal["not_attempted", "accepted", "unavailable"] = "not_attempted"
    page_status: Literal[
        "not_attempted", "deferred", "empty", "invalid", "rejected", "nonempty"
    ] = "not_attempted"
    token_transport_calls: int = 0
    page_transport_calls: int = 0
    accepted_rows: int = 0
    token_envelope: KisPaperTokenProbeEnvelope | None = None
    next_due: datetime | None = None

    def __post_init__(self) -> None:
        require_utc(self.completed_at, "page probe completion")
        if self.next_due is not None:
            require_utc(self.next_due, "page probe next due")
        if self.token_status not in {
            "not_attempted",
            "accepted",
            "unavailable",
        } or self.page_status not in {
            "not_attempted",
            "deferred",
            "empty",
            "invalid",
            "rejected",
            "nonempty",
        }:
            raise ValueError("page probe status is invalid")
        if (
            any(
                type(count) is not int or count not in {0, 1}
                for count in (self.token_transport_calls, self.page_transport_calls)
            )
            or type(self.accepted_rows) is not int
            or not 0 <= self.accepted_rows <= 120
        ):
            raise ValueError("page probe counts are invalid")
        if (self.page_status == "nonempty") != (self.accepted_rows > 0):
            raise ValueError("page probe row count conflicts")
        if self.page_transport_calls and self.token_status != "accepted":
            raise ValueError("page probe lacks an accepted token")
        if self.token_status == "accepted" and self.token_transport_calls != 1:
            raise ValueError("page probe token count conflicts")
        if self.token_envelope is not None and (
            not isinstance(self.token_envelope, KisPaperTokenProbeEnvelope)
            or self.token_transport_calls != 1
        ):
            raise ValueError("page probe envelope is invalid")
        if (
            self.page_status in {"empty", "invalid", "rejected", "nonempty"}
            and self.page_transport_calls != 1
        ):
            raise ValueError("page probe page count conflicts")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": "token_then_qqq_head_once",
            "symbol": "QQQ",
            "exchange": "NAS",
            "completed_at": self.completed_at.isoformat(),
            "token_status": self.token_status,
            "page_status": self.page_status,
            "transport_dispatch_counts": {
                "token": self.token_transport_calls,
                "minute_page": self.page_transport_calls,
            },
            "accepted_rows": self.accepted_rows,
            "budget": {
                "token_post": 1,
                "minute_get": 1,
                "initiation_seconds": 60,
                "request_timeout_seconds": 15,
                "normal_pacing_sleep_seconds_max": 1,
            },
        }
        if self.token_envelope is not None:
            payload["token_envelope"] = self.token_envelope.safe_payload()
        if self.next_due is not None:
            payload["next_due"] = self.next_due.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class KisPaperAuthCapabilityProbeOutcome:
    """One token-only outcome with no bearer token or credential data."""

    status: ProbeStatus
    observed_at: datetime
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION
    page_probe: KisPaperAuthPageProbeDetails | None = None

    def __post_init__(self) -> None:
        require_utc(self.observed_at, "auth capability observation")
        if (
            self.status not in {"authenticated", "unavailable"}
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS Paper auth capability outcome is invalid")
        if self.page_probe is not None:
            if (
                not isinstance(self.page_probe, KisPaperAuthPageProbeDetails)
                or self.page_probe.completed_at < self.observed_at
            ):
                raise ValueError("KIS Paper page probe details are invalid")
            if self.status == "authenticated":
                if self.reason is not None or self.page_probe.page_status != "nonempty":
                    raise ValueError("KIS Paper page probe success is invalid")
            elif (
                self.reason not in _PAGE_FAILURE_REASONS
                or self.page_probe.page_status == "nonempty"
            ):
                raise ValueError("KIS Paper page probe failure is invalid")
            return
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
        if self.page_probe is not None:
            payload["observed_at"] = self.observed_at.isoformat()
            payload["page_probe"] = self.page_probe.safe_payload()
            isolation = payload["route_isolation"]
            assert isinstance(isolation, dict)
            isolation["token_only"] = False
            isolation["market_data_requested"] = self.page_probe.page_transport_calls > 0
            isolation["raw_market_rows_retained"] = False
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


def categorize_kis_paper_auth_capability_error(
    error: BaseException, *, page_probe: bool = False
) -> str:
    """Map exceptions to the fixed source-safe outcome taxonomy."""

    reason = str(error)
    allowed = _PAGE_FAILURE_REASONS if page_probe else _SAFE_FAILURE_REASONS
    if isinstance(error, KisPaperMarketDataError) and reason in allowed:
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

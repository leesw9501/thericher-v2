"""Source-safe, bounded calibration for KIS Paper token request cadence."""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import KisPaperMarketDataError
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_PAPER_TOKEN_CADENCE_PROBE_KIND = "kis_paper_token_cadence_probe"
KIS_PAPER_TOKEN_CADENCE_PROBE_DIRECTORY = "kis-paper-token-cadence-probe-v1"
KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS = 30.0

_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "response_invalid",
        "token_request_not_due",
        "transport_failure",
    }
)

ProbeStatus = Literal["accepted", "unavailable"]
FailureStage = Literal["none", "first", "second"]
SpacingCategory = Literal[
    "not_started",
    "at_or_above_requested_interval",
    "below_requested_interval",
]


@dataclass(frozen=True, slots=True)
class KisPaperTokenCadenceProbeAttempt:
    """One successful token POST and its local transport-start measurements."""

    request_started_at: datetime
    monotonic_started_seconds: float

    def __post_init__(self) -> None:
        require_utc(self.request_started_at, "token request start")
        if not _is_nonnegative_finite(self.monotonic_started_seconds):
            raise ValueError("KIS Paper token cadence attempt is invalid")


@dataclass(frozen=True, slots=True)
class KisPaperTokenCadenceProbeOutcome:
    """One two-attempt, token-only cadence result with no bearer-token value."""

    status: ProbeStatus
    requested_interval_seconds: float
    accepted_authentication_count: int
    failure_stage: FailureStage
    failure_reason: str | None
    spacing_category: SpacingCategory
    observed_monotonic_start_spacing_seconds: float | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.status not in {"accepted", "unavailable"}
            or self.requested_interval_seconds <= 0
            or self.accepted_authentication_count not in {0, 1, 2}
            or self.failure_stage not in {"none", "first", "second"}
            or self.spacing_category
            not in {
                "not_started",
                "at_or_above_requested_interval",
                "below_requested_interval",
            }
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS Paper token cadence outcome is invalid")
        if self.observed_monotonic_start_spacing_seconds is not None and (
            not math.isfinite(self.observed_monotonic_start_spacing_seconds)
            or self.observed_monotonic_start_spacing_seconds < 0
        ):
            raise ValueError("KIS Paper token cadence spacing is invalid")
        if self.status == "accepted":
            if (
                self.accepted_authentication_count != 2
                or self.failure_stage != "none"
                or self.failure_reason is not None
                or self.spacing_category != "at_or_above_requested_interval"
                or self.observed_monotonic_start_spacing_seconds is None
                or self.observed_monotonic_start_spacing_seconds
                < self.requested_interval_seconds
            ):
                raise ValueError("accepted KIS Paper token cadence outcome is invalid")
            return
        if self.failure_stage == "none" or self.failure_reason not in _SAFE_FAILURE_REASONS:
            raise ValueError("unavailable KIS Paper token cadence outcome is invalid")
        if self.failure_stage == "first" and (
            self.accepted_authentication_count != 0
            or self.spacing_category != "not_started"
            or self.observed_monotonic_start_spacing_seconds is not None
        ):
            raise ValueError("first-failure KIS Paper token cadence outcome is invalid")
        if self.failure_stage == "second" and (
            self.accepted_authentication_count != 1
            or self.spacing_category == "not_started"
            or self.observed_monotonic_start_spacing_seconds is None
        ):
            raise ValueError("second-failure KIS Paper token cadence outcome is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_TOKEN_CADENCE_PROBE_KIND,
            "status": self.status,
            "requested_interval_seconds": self.requested_interval_seconds,
            "accepted_authentication_count": self.accepted_authentication_count,
            "failure": {
                "stage": self.failure_stage,
                "reason": self.failure_reason,
            },
            "spacing_category": self.spacing_category,
            "observed_monotonic_start_spacing_seconds": (
                self.observed_monotonic_start_spacing_seconds
            ),
            "scope": {
                "paper_only": True,
                "token_only": True,
                "market_data_requested": False,
                "account_or_order_requested": False,
                "live_route": False,
                "token_value_retained": False,
                "credentials_written": False,
                "model_or_pnl_result": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisPaperTokenCadenceProbeRun:
    """External result location for one immutable capability-probe attempt."""

    outcome: KisPaperTokenCadenceProbeOutcome
    summary_path: Path
    summary_sha256: str

    def __post_init__(self) -> None:
        if not _is_sha256(self.summary_sha256) or self.summary_path.name != "summary.json":
            raise ValueError("KIS Paper token cadence probe run is invalid")


def run_kis_paper_token_cadence_probe(
    *,
    authenticate_once: Callable[[], KisPaperTokenCadenceProbeAttempt],
    requested_interval_seconds: float = KIS_PAPER_TOKEN_CADENCE_PROBE_INTERVAL_SECONDS,
    monotonic_clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> KisPaperTokenCadenceProbeOutcome:
    """Attempt exactly two fresh in-memory authentication clients at one cadence.

    The caller owns credential loading and transport construction. This helper
    neither sees nor persists the returned bearer token.
    """

    if not _is_positive_finite(requested_interval_seconds):
        raise ValueError("KIS Paper token cadence interval is invalid")
    try:
        first_attempt = authenticate_once()
    except Exception as error:
        return KisPaperTokenCadenceProbeOutcome(
            status="unavailable",
            requested_interval_seconds=float(requested_interval_seconds),
            accepted_authentication_count=0,
            failure_stage="first",
            failure_reason=_safe_failure_reason(error),
            spacing_category="not_started",
            observed_monotonic_start_spacing_seconds=None,
        )

    due = first_attempt.monotonic_started_seconds + float(requested_interval_seconds)
    remaining = due - _require_monotonic(monotonic_clock(), "token cadence clock")
    if remaining > 0:
        sleeper(remaining)
    try:
        second_attempt = authenticate_once()
    except Exception as error:
        observed_spacing = max(
            0.0,
            _require_monotonic(monotonic_clock(), "token cadence clock")
            - first_attempt.monotonic_started_seconds,
        )
        return KisPaperTokenCadenceProbeOutcome(
            status="unavailable",
            requested_interval_seconds=float(requested_interval_seconds),
            accepted_authentication_count=1,
            failure_stage="second",
            failure_reason=_safe_failure_reason(error),
            spacing_category=(
                "at_or_above_requested_interval"
                if observed_spacing >= float(requested_interval_seconds)
                else "below_requested_interval"
            ),
            observed_monotonic_start_spacing_seconds=observed_spacing,
        )
    observed_spacing = max(
        0.0,
        second_attempt.monotonic_started_seconds - first_attempt.monotonic_started_seconds,
    )
    if observed_spacing < float(requested_interval_seconds):
        return KisPaperTokenCadenceProbeOutcome(
            status="unavailable",
            requested_interval_seconds=float(requested_interval_seconds),
            accepted_authentication_count=1,
            failure_stage="second",
            failure_reason="transport_failure",
            spacing_category="below_requested_interval",
            observed_monotonic_start_spacing_seconds=observed_spacing,
        )
    return KisPaperTokenCadenceProbeOutcome(
        status="accepted",
        requested_interval_seconds=float(requested_interval_seconds),
        accepted_authentication_count=2,
        failure_stage="none",
        failure_reason=None,
        spacing_category="at_or_above_requested_interval",
        observed_monotonic_start_spacing_seconds=observed_spacing,
    )


def write_kis_paper_token_cadence_probe(
    outcome: KisPaperTokenCadenceProbeOutcome,
    *,
    artifact_root: Path | str,
    repo_root: Path | str,
    run_label: str,
    observed_at: datetime,
) -> KisPaperTokenCadenceProbeRun:
    """Persist source-safe cadence evidence outside the Git workspace."""

    if not isinstance(outcome, KisPaperTokenCadenceProbeOutcome):
        raise TypeError("KIS Paper token cadence outcome is invalid")
    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("KIS Paper token cadence run label is invalid")
    observed = require_utc(observed_at, "observed_at")
    directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "data",
        KIS_PAPER_TOKEN_CADENCE_PROBE_DIRECTORY,
        run_label,
    )
    payload = {
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "outcome": outcome.safe_payload(),
    }
    summary_path, summary_sha256 = _write_immutable_json(directory / "summary.json", payload)
    return KisPaperTokenCadenceProbeRun(
        outcome=outcome,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
    )


def _safe_failure_reason(error: BaseException) -> str:
    reason = str(error)
    if isinstance(error, KisPaperMarketDataError) and reason in _SAFE_FAILURE_REASONS:
        return reason
    return "transport_failure"


def _write_immutable_json(path: Path, payload: Mapping[str, object]) -> tuple[Path, str]:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("KIS Paper token cadence evidence path is invalid")
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    digest = "sha256:" + _sha256_bytes(encoded)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("KIS Paper token cadence evidence conflicts")
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


def _is_positive_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _is_nonnegative_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _require_monotonic(value: object, label: str) -> float:
    if not _is_nonnegative_finite(value):
        raise ValueError(f"{label} is invalid")
    return float(value)


def _sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None

"""Persist source-safe terminal evidence for one intraday-head dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.data.kis_intraday_mtf_availability import (
    KIS_INTRADAY_MTF_AVAILABILITY_ARTIFACT_DIRECTORY,
    KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID,
)
from thericher_v2.data.kis_paper_intraday_session_capture import (
    KIS_PAPER_INTRADAY_SESSION_CAPTURE_COVERAGE_CATEGORIES,
    KisPaperIntradaySessionCaptureTarget,
)
from thericher_v2.data.kis_qqq_spy_mtf_prospective_observation import (
    KisQqqSpyMtfProspectiveAttempt,
    KisQqqSpyMtfProspectiveContract,
    KisQqqSpyMtfProspectiveObservationError,
    read_kis_qqq_spy_mtf_prospective_attempt,
    read_kis_qqq_spy_mtf_prospective_contract,
)

KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND = "kis_paper_intraday_head_schedule_receipt"
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY = (
    "execution/kis-paper-intraday-head-schedule"
)
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME = "current.json"
KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_KIND = "kis_paper_intraday_head_schedule_runtime"
KIS_PAPER_INTRADAY_HEAD_COLLECTION_RECOVERY_FACT_KIND = (
    "kis_paper_intraday_head_collection_recovery_fact"
)
KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_ARTIFACT_DIRECTORY = (
    "kis-paper-intraday-causal-attestation-v1"
)
KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_KIND = (
    "kis_paper_intraday_head_causal_attestation"
)
DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT = Path(
    r"D:\thericher-v2\model-artifacts"
)
SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE = 20
_DEFAULT_REPOSITORY_ROOT = Path.cwd()

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,160}", re.ASCII)
_SCHEDULE_RECEIPT_CLAIM = (
    "scheduled dispatch observability only; not a model result, PnL claim, "
    "or broker action"
)
_SCHEDULE_RECEIPT_ARTIFACT_POLICY = {
    "credentials_in_receipt": False,
    "account_data_in_receipt": False,
    "raw_market_data_in_receipt": False,
    "broker_order_data_in_receipt": False,
    "repo_storage_allowed": False,
}
_SCHEDULE_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "run_id",
        "observed_at",
        "stages",
        "terminal",
        "artifact_policy",
        "claim",
    }
)
_SCHEDULE_RECEIPT_BINDING_KEY = "terminal_receipt_binding"
_SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY = "session_capture_binding_required"
_SCHEDULE_RECEIPT_AVAILABILITY_BINDING_KEY = "receipt_binding"
_SCHEDULE_RECEIPT_OBSERVATION_BINDING_KEY = "observation_attempt_binding"
_SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY = "causal_attestation_binding"
_TERMINAL_RECEIPT_BINDING_KEYS = frozenset(
    {
        "schedule_run_id",
        "observed_at",
        "receipt_sha256",
        "current_session_cumulative_coverage_digest",
        "current_session_cumulative_coverage_category",
    }
)
_OBSERVATION_ATTEMPT_BINDING_KEYS = frozenset(
    {
        "attempt_sha256",
        "attempt_status",
        "store_outcome",
    }
)
_AVAILABILITY_RECEIPT_BINDING_KEYS = frozenset(
    {
        "contract_sha256",
        "receipt_sha256",
        "precommit_sha256",
        "summary_sha256",
    }
)
_CAUSAL_ATTESTATION_BINDING_KEYS = frozenset({"attestation_sha256"})
_CAUSAL_ATTESTATION_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "schedule_run_id",
        "schedule_observed_at",
        "session_capture_receipt_sha256",
        "availability_summary_sha256",
        "observation_attempt_sha256",
        "attestation_origin",
        "clock_authority",
        "timezone_dst_session_rule",
        "completed_bar_geometry",
        "chronological_boundary",
        "decision_time_availability",
        "provider_finality",
        "artifact_policy",
        "claim",
    }
)
_CAUSAL_ATTESTATION_ARTIFACT_POLICY = {
    "credentials_in_receipt": False,
    "account_data_in_receipt": False,
    "raw_market_data_in_receipt": False,
    "broker_order_data_in_receipt": False,
    "repo_storage_allowed": False,
}
_CAUSAL_ATTESTATION_CLAIM = (
    "independent source-safe causal-condition attestation only; not cryptographic "
    "proof of provider origin, a model result, PnL claim, or broker action"
)
_CAUSAL_ATTESTATION_ORIGINS = frozenset({"independent_observer"})
_CAUSAL_ATTESTATION_CLOCK_AUTHORITIES = frozenset(
    {"independent_utc_clock", "not_observed"}
)
_CAUSAL_ATTESTATION_TIMEZONE_DST_SESSION_RULES = frozenset(
    {"America_New_York_IANA_DST", "not_observed"}
)
_CAUSAL_ATTESTATION_COMPLETED_BAR_GEOMETRIES = frozenset(
    {"m1_regular_session_complete_through_1530_et", "not_observed"}
)
_CAUSAL_ATTESTATION_CHRONOLOGICAL_BOUNDARIES = frozenset(
    {"non_overlapping", "not_observed"}
)
_CAUSAL_ATTESTATION_DECISION_TIME_AVAILABILITY = frozenset(
    {"observed_at_decision_time", "not_observed"}
)
_CAUSAL_ATTESTATION_PROVIDER_FINALITY = frozenset({"observed_final", "not_observed"})
_SCHEDULE_RECEIPT_TERMINAL_KEYS = frozenset(
    {"status", "recovery_class", "scheduler_exit_code"}
)
_SCHEDULE_RUNTIME_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "run_id",
        "observed_at",
        "status",
        "recovery_class",
        "scheduler_exit_code",
        "receipt_sha256",
    }
)
_LOOP_STATUSES = frozenset({"embedded", "preview", "no_intent", "unavailable", "not_applicable"})
_SESSION_STATUSES = frozenset({"no_intent", "canary_completed", "unavailable", "not_applicable"})
_VALIDATION_STATUSES = frozenset({"validated", "not_run", "unavailable", "not_applicable"})
_SPY_CYCLE_STATUSES = frozenset(
    {"preview", "no_intent", "canary_completed", "unavailable", "not_applicable"}
)
_OBSERVATION_STATUSES = frozenset(
    {
        "pending",
        "unavailable",
        "complete",
        "not_applicable",
        "observed",
        "not_observed",
        "duplicate",
        "conflict",
        "cap_reached",
        "busy",
    }
)
_CAPTURE_CYCLE_STATUSES = frozenset(
    {
        "not_applicable",
        "unavailable",
        "outside_cycle_slot",
        "observed",
        "duplicate",
        "conflict",
        "input_unavailable",
        "outcome_unavailable",
        "input_mutated",
        "appended",
        "busy",
    }
)
_AVAILABILITY_STATUSES = frozenset(
    {
        "qualified_for_prospective_input",
        "input_unavailable",
        "unavailable",
        "not_applicable",
    }
)
_OBSERVATION_ATTEMPT_STATUSES = frozenset({"observed", "not_observed"})
_OBSERVATION_ATTEMPT_OUTCOMES = frozenset({"appended", "duplicate"})
_CAPTURE_RECEIPT_KIND = "kis_paper_intraday_session_capture"
_CAPTURE_RECEIPT_DIRECTORY = ("v1", "session-capture")
_CAPTURE_TARGET_KEYS = frozenset({"QQQ/NAS/1m", "SPY/AMS/1m"})
_COLLECTION_RECOVERY_CONFLICT_ORIGINS = frozenset(
    {"candidate_batch", "retained_cache", "not_applicable", "not_recorded_legacy"}
)
_COLLECTION_RECOVERY_RETAINED_HEAD_DISPOSITIONS = frozenset(
    {"not_applicable", "preserved", "quarantined", "not_recorded_legacy"}
)
_EASTERN_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class KisPaperIntradayHeadTerminalReceiptBinding:
    """Source-safe reference to one exact same-run session-capture receipt."""

    schedule_run_id: str
    observed_at: datetime
    receipt_sha256: str
    current_session_cumulative_coverage_digest: str
    current_session_cumulative_coverage_category: str

    def __post_init__(self) -> None:
        _require_schedule_run_id(self.schedule_run_id, "binding schedule run id")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        _require_sha256(self.receipt_sha256, "binding receipt sha256")
        _require_sha256(
            self.current_session_cumulative_coverage_digest,
            "binding cumulative coverage digest",
        )
        _require_capture_coverage_category(
            self.current_session_cumulative_coverage_category,
            "binding cumulative coverage category",
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "schedule_run_id": self.schedule_run_id,
            "observed_at": _utc_marker(self.observed_at),
            "receipt_sha256": self.receipt_sha256,
            "current_session_cumulative_coverage_digest": (
                self.current_session_cumulative_coverage_digest
            ),
            "current_session_cumulative_coverage_category": (
                self.current_session_cumulative_coverage_category
            ),
        }


@dataclass(frozen=True)
class KisPaperIntradayHeadAvailabilityReceiptBinding:
    """Source-safe hashes for the exact local availability receipt used downstream."""

    contract_sha256: str
    receipt_sha256: str
    precommit_sha256: str
    summary_sha256: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.contract_sha256, "availability contract sha256"),
            (self.receipt_sha256, "availability receipt sha256"),
            (self.precommit_sha256, "availability precommit sha256"),
            (self.summary_sha256, "availability summary sha256"),
        ):
            _require_sha256(value, name)

    def safe_payload(self) -> dict[str, str]:
        return {
            "contract_sha256": self.contract_sha256,
            "receipt_sha256": self.receipt_sha256,
            "precommit_sha256": self.precommit_sha256,
            "summary_sha256": self.summary_sha256,
        }


@dataclass(frozen=True)
class KisPaperIntradayHeadObservationAttemptBinding:
    """Source-safe reference to one exact local-only pair-observation attempt."""

    attempt_sha256: str
    attempt_status: Literal["observed", "not_observed"]
    store_outcome: Literal["appended", "duplicate"]

    def __post_init__(self) -> None:
        _require_sha256(self.attempt_sha256, "observation attempt sha256")
        if self.attempt_status not in _OBSERVATION_ATTEMPT_STATUSES:
            raise ValueError("observation attempt binding is invalid")
        if self.store_outcome not in _OBSERVATION_ATTEMPT_OUTCOMES:
            raise ValueError("observation attempt binding is invalid")

    def safe_payload(self) -> dict[str, str]:
        return {
            "attempt_sha256": self.attempt_sha256,
            "attempt_status": self.attempt_status,
            "store_outcome": self.store_outcome,
        }


@dataclass(frozen=True)
class KisPaperIntradayHeadCausalAttestationBinding:
    """Hash-bind one separately produced, source-safe causal-condition receipt."""

    attestation_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.attestation_sha256, "causal attestation sha256")

    def safe_payload(self) -> dict[str, str]:
        return {"attestation_sha256": self.attestation_sha256}


@dataclass(frozen=True)
class _KisPaperIntradayHeadCausalAttestation:
    """A default-deny external condition record for one immutable terminal."""

    schedule_run_id: str
    schedule_observed_at: datetime
    session_capture_receipt_sha256: str
    availability_summary_sha256: str
    observation_attempt_sha256: str
    attestation_origin: str
    clock_authority: str
    timezone_dst_session_rule: str
    completed_bar_geometry: str
    chronological_boundary: str
    decision_time_availability: str
    provider_finality: str


@dataclass(frozen=True)
class KisPaperIntradayHeadScheduleReceipt:
    """One immutable terminal result for the existing scheduled dispatch."""

    run_id: str
    observed_at: datetime
    collection_exit_code: int
    prospective_spy_cycle_exit_code: int
    prospective_spy_cycle_status: str
    prospective_spy_cycle_id: str | None
    prospective_spy_canary_run_id: str | None
    prospective_loop_exit_code: int
    prospective_loop_status: str
    prospective_session_exit_code: int
    prospective_session_status: str
    prospective_session_id: str | None
    prospective_validation_exit_code: int
    prospective_validation_status: str
    prospective_validation_session_id: str | None
    prospective_validation_contract: str | None
    availability_exit_code: int
    availability_status: str
    availability_receipt_binding: KisPaperIntradayHeadAvailabilityReceiptBinding | None
    observation_exit_code: int
    observation_status: str
    capture_cycle_exit_code: int
    capture_cycle_status: str
    session_capture_binding_required: bool
    terminal_receipt_binding: KisPaperIntradayHeadTerminalReceiptBinding | None
    observation_attempt_binding: KisPaperIntradayHeadObservationAttemptBinding | None
    causal_attestation_binding: KisPaperIntradayHeadCausalAttestationBinding | None
    terminal_status: str
    recovery_class: str
    scheduler_exit_code: int
    evidence_path: Path

    def safe_payload(self) -> dict[str, object]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND,
            "status": self.terminal_status,
            "run_id": self.run_id,
            "observed_at": _utc_marker(self.observed_at),
            "stages": {
                "collection": {
                    "exit_code": self.collection_exit_code,
                    "status": "exit_zero" if self.collection_exit_code == 0 else "exit_nonzero",
                },
                "availability": {
                    "exit_code": self.availability_exit_code,
                    "status": self.availability_status,
                    "source_local": True,
                },
                "prospective_spy_cycle": {
                    "exit_code": self.prospective_spy_cycle_exit_code,
                    "status": self.prospective_spy_cycle_status,
                    "cycle_id": self.prospective_spy_cycle_id,
                    "canary_run_id": self.prospective_spy_canary_run_id,
                    "collector_process_separate": True,
                },
                "prospective_loop": {
                    "exit_code": self.prospective_loop_exit_code,
                    "status": self.prospective_loop_status,
                },
                "prospective_session": {
                    "exit_code": self.prospective_session_exit_code,
                    "status": self.prospective_session_status,
                    "session_id": self.prospective_session_id,
                },
                "prospective_validation": {
                    "exit_code": self.prospective_validation_exit_code,
                    "status": self.prospective_validation_status,
                    "session_id": self.prospective_validation_session_id,
                    "contract": self.prospective_validation_contract,
                },
                "observation": {
                    "exit_code": self.observation_exit_code,
                    "status": self.observation_status,
                    "required_for_qqq_cycle": False,
                    "data_only_pair_observation": True,
                },
                "profiled_mtf_forward_capture": {
                    "exit_code": self.capture_cycle_exit_code,
                    "status": self.capture_cycle_status,
                    "data_only": True,
                },
            },
            "terminal": {
                "status": self.terminal_status,
                "recovery_class": self.recovery_class,
                "scheduler_exit_code": self.scheduler_exit_code,
            },
            "artifact_policy": {
                **_SCHEDULE_RECEIPT_ARTIFACT_POLICY,
            },
            "claim": _SCHEDULE_RECEIPT_CLAIM,
        }
        if self.session_capture_binding_required:
            payload[_SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY] = True
        if self.terminal_receipt_binding is not None:
            payload[_SCHEDULE_RECEIPT_BINDING_KEY] = self.terminal_receipt_binding.safe_payload()
        if self.observation_attempt_binding is not None:
            stages = payload["stages"]
            assert isinstance(stages, dict)
            observation = stages["observation"]
            assert isinstance(observation, dict)
            observation["attempt_binding"] = self.observation_attempt_binding.safe_payload()
        if self.availability_receipt_binding is not None:
            stages = payload["stages"]
            assert isinstance(stages, dict)
            availability = stages["availability"]
            assert isinstance(availability, dict)
            availability[_SCHEDULE_RECEIPT_AVAILABILITY_BINDING_KEY] = (
                self.availability_receipt_binding.safe_payload()
            )
        if self.causal_attestation_binding is not None:
            payload[_SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY] = (
                self.causal_attestation_binding.safe_payload()
            )
        return payload


class KisPaperIntradayHeadScheduleReceiptError(ValueError):
    """A schedule receipt or its current runtime pointer is unsafe or malformed."""


@dataclass(frozen=True)
class KisPaperIntradayHeadScheduleFact:
    """One offline projection from the task-owned current terminal schedule receipt."""

    run_id: str
    observed_at: datetime
    terminal_status: Literal["complete", "recovery"]
    recovery_class: str
    scheduler_exit_code: int
    receipt_sha256: str
    coverage_binding_status: Literal["legacy_unbound", "verified"]
    current_session_cumulative_coverage_digest: str | None
    current_session_cumulative_coverage_category: str | None
    session_capture_receipt_sha256: str | None
    current_session_cumulative_coverage_gap_category: (
        Literal["current_session_missing", "current_session_short"] | None
    )
    availability_status: str
    availability_binding_status: Literal["legacy_unbound", "verified"]
    availability_contract_sha256: str | None
    availability_receipt_sha256: str | None
    availability_precommit_sha256: str | None
    availability_summary_sha256: str | None
    observation_binding_status: Literal["legacy_unbound", "verified"]
    observation_attempt_sha256: str | None
    observation_attempt_status: Literal["observed", "not_observed"] | None
    observation_store_outcome: Literal["appended", "duplicate"] | None
    causal_attestation_binding_status: Literal["not_recorded", "verified"]
    causal_attestation_sha256: str | None
    clock_authority: str | None
    timezone_dst_session_rule: str | None
    completed_bar_geometry: str | None
    chronological_boundary: str | None
    causal_input_status: Literal["input_unavailable", "qualified"]
    causal_input_reason: str
    decision_time_availability: Literal["not_observed", "attested"]
    provider_finality: Literal["not_observed", "attested"]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schedule_run_id(self.run_id, "run id")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.terminal_status not in {"complete", "recovery"}:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_terminal_status_invalid")
        _require_exit_codes(self.scheduler_exit_code)
        _require_sha256(self.receipt_sha256, "receipt sha256")
        if self.coverage_binding_status == "legacy_unbound":
            if (
                self.current_session_cumulative_coverage_digest is not None
                or self.current_session_cumulative_coverage_category is not None
                or self.session_capture_receipt_sha256 is not None
                or self.current_session_cumulative_coverage_gap_category is not None
            ):
                raise KisPaperIntradayHeadScheduleReceiptError("schedule_coverage_binding_invalid")
        elif self.coverage_binding_status == "verified":
            if (
                self.current_session_cumulative_coverage_digest is None
                or self.current_session_cumulative_coverage_category is None
                or self.session_capture_receipt_sha256 is None
            ):
                raise KisPaperIntradayHeadScheduleReceiptError("schedule_coverage_binding_invalid")
            _require_sha256(
                self.current_session_cumulative_coverage_digest,
                "coverage binding digest",
            )
            _require_sha256(
                self.session_capture_receipt_sha256,
                "coverage binding receipt sha256",
            )
            _require_capture_coverage_category(
                self.current_session_cumulative_coverage_category,
                "coverage binding category",
            )
            if self.current_session_cumulative_coverage_category == "complete":
                if self.current_session_cumulative_coverage_gap_category is not None:
                    raise KisPaperIntradayHeadScheduleReceiptError(
                        "schedule_coverage_binding_invalid"
                    )
            elif self.current_session_cumulative_coverage_gap_category not in {
                "current_session_missing",
                "current_session_short",
            }:
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_coverage_binding_invalid"
                )
        else:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_coverage_binding_invalid")
        if self.availability_status not in _AVAILABILITY_STATUSES | {"not_recorded_legacy"}:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_invalid")
        availability_values = (
            self.availability_contract_sha256,
            self.availability_receipt_sha256,
            self.availability_precommit_sha256,
            self.availability_summary_sha256,
        )
        if self.availability_binding_status == "legacy_unbound":
            if any(value is not None for value in availability_values):
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_availability_binding_invalid"
                )
        elif self.availability_binding_status == "verified":
            if any(value is None for value in availability_values):
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_availability_binding_invalid"
                )
            for value, name in zip(
                availability_values,
                (
                    "availability contract sha256",
                    "availability receipt sha256",
                    "availability precommit sha256",
                    "availability summary sha256",
                ),
                strict=True,
            ):
                assert value is not None
                _require_sha256(value, name)
        else:
            raise KisPaperIntradayHeadScheduleReceiptError(
                "schedule_availability_binding_invalid"
            )
        if self.observation_binding_status == "legacy_unbound":
            if (
                self.observation_attempt_sha256 is not None
                or self.observation_attempt_status is not None
                or self.observation_store_outcome is not None
            ):
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_observation_binding_invalid"
                )
        elif self.observation_binding_status == "verified":
            _require_sha256(self.observation_attempt_sha256, "observation attempt sha256")
            if self.observation_attempt_status not in _OBSERVATION_ATTEMPT_STATUSES:
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_observation_binding_invalid"
                )
            if self.observation_store_outcome not in _OBSERVATION_ATTEMPT_OUTCOMES:
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_observation_binding_invalid"
                )
        else:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_observation_binding_invalid")
        if self.causal_attestation_binding_status == "not_recorded":
            if (
                self.causal_attestation_sha256 is not None
                or self.clock_authority is not None
                or self.timezone_dst_session_rule is not None
                or self.completed_bar_geometry is not None
                or self.chronological_boundary is not None
            ):
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_causal_attestation_invalid"
                )
        elif self.causal_attestation_binding_status == "verified":
            if self.causal_attestation_sha256 is None:
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "schedule_causal_attestation_invalid"
                )
            _require_sha256(self.causal_attestation_sha256, "causal attestation sha256")
            for value, allowed in (
                (self.clock_authority, _CAUSAL_ATTESTATION_CLOCK_AUTHORITIES),
                (
                    self.timezone_dst_session_rule,
                    _CAUSAL_ATTESTATION_TIMEZONE_DST_SESSION_RULES,
                ),
                (
                    self.completed_bar_geometry,
                    _CAUSAL_ATTESTATION_COMPLETED_BAR_GEOMETRIES,
                ),
                (
                    self.chronological_boundary,
                    _CAUSAL_ATTESTATION_CHRONOLOGICAL_BOUNDARIES,
                ),
            ):
                if value not in allowed:
                    raise KisPaperIntradayHeadScheduleReceiptError(
                        "schedule_causal_attestation_invalid"
                    )
        else:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_attestation_invalid")
        if (
            not self.causal_input_reason
            or self.decision_time_availability not in {"not_observed", "attested"}
            or self.provider_finality not in {"not_observed", "attested"}
        ):
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_input_invalid")
        if self.causal_input_status == "qualified":
            if (
                self.causal_input_reason != "qualified"
                or self.causal_attestation_binding_status != "verified"
                or self.clock_authority != "independent_utc_clock"
                or self.timezone_dst_session_rule != "America_New_York_IANA_DST"
                or self.completed_bar_geometry != "m1_regular_session_complete_through_1530_et"
                or self.chronological_boundary != "non_overlapping"
                or self.decision_time_availability != "attested"
                or self.provider_finality != "attested"
            ):
                raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_input_invalid")
        elif self.causal_input_status != "input_unavailable":
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_input_invalid")

    def safe_payload(self) -> dict[str, object]:
        """Expose only terminal scheduling categories, never external evidence paths."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_intraday_head_schedule_fact",
            "run_id": self.run_id,
            "observed_at": _utc_marker(self.observed_at),
            "status": self.terminal_status,
            "recovery_class": self.recovery_class,
            "scheduler_exit_code": self.scheduler_exit_code,
            "receipt_sha256": self.receipt_sha256,
            "coverage_binding_status": self.coverage_binding_status,
            "current_session_cumulative_coverage_digest": (
                self.current_session_cumulative_coverage_digest
            ),
            "current_session_cumulative_coverage_category": (
                self.current_session_cumulative_coverage_category
            ),
            "session_capture_receipt_sha256": self.session_capture_receipt_sha256,
            "current_session_cumulative_coverage_gap_category": (
                self.current_session_cumulative_coverage_gap_category
            ),
            "availability_status": self.availability_status,
            "availability_binding_status": self.availability_binding_status,
            "availability_contract_sha256": self.availability_contract_sha256,
            "availability_receipt_sha256": self.availability_receipt_sha256,
            "availability_precommit_sha256": self.availability_precommit_sha256,
            "availability_summary_sha256": self.availability_summary_sha256,
            "observation_binding_status": self.observation_binding_status,
            "observation_attempt_sha256": self.observation_attempt_sha256,
            "observation_attempt_status": self.observation_attempt_status,
            "observation_store_outcome": self.observation_store_outcome,
            "causal_attestation_binding_status": self.causal_attestation_binding_status,
            "causal_attestation_sha256": self.causal_attestation_sha256,
            "clock_authority": self.clock_authority,
            "timezone_dst_session_rule": self.timezone_dst_session_rule,
            "completed_bar_geometry": self.completed_bar_geometry,
            "chronological_boundary": self.chronological_boundary,
            "causal_input_status": self.causal_input_status,
            "causal_input_reason": self.causal_input_reason,
            "decision_time_availability": self.decision_time_availability,
            "provider_finality": self.provider_finality,
        }


@dataclass(frozen=True)
class KisPaperIntradayHeadCollectionRecoveryTarget:
    """One allowlisted target outcome without counts, rows, or receipt paths."""

    target_key: str
    status: str
    reason: str | None
    conflict_origin: Literal[
        "candidate_batch", "retained_cache", "not_applicable", "not_recorded_legacy"
    ]
    retained_head_conflict_disposition: Literal[
        "not_applicable", "preserved", "quarantined", "not_recorded_legacy"
    ]

    def __post_init__(self) -> None:
        if self.target_key not in _CAPTURE_TARGET_KEYS:
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
        _require_safe_id(self.status, "collection recovery target status")
        if self.reason is not None:
            _require_safe_id(self.reason, "collection recovery target reason")
        if self.conflict_origin not in _COLLECTION_RECOVERY_CONFLICT_ORIGINS:
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
        if (
            self.retained_head_conflict_disposition
            not in _COLLECTION_RECOVERY_RETAINED_HEAD_DISPOSITIONS
        ):
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
        if self.conflict_origin == "not_recorded_legacy":
            if self.retained_head_conflict_disposition != "not_recorded_legacy":
                raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
            return
        if self.retained_head_conflict_disposition == "not_recorded_legacy":
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
        if self.conflict_origin == "not_applicable":
            if self.retained_head_conflict_disposition != "not_applicable":
                raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
            return
        if self.status != "rejected" or self.reason != "minute_duplicate_conflict":
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
        if self.conflict_origin == "candidate_batch":
            if self.retained_head_conflict_disposition != "not_applicable":
                raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
            return
        if self.retained_head_conflict_disposition not in {"preserved", "quarantined"}:
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "status": self.status,
            "reason": self.reason,
            "conflict_origin": self.conflict_origin,
            "retained_head_conflict_disposition": self.retained_head_conflict_disposition,
        }


@dataclass(frozen=True)
class KisPaperIntradayHeadCollectionRecoveryFact:
    """A read-only, binding-verified projection of capture recovery evidence."""

    category: str
    capture_binding_status: Literal["verified", "evidence_unavailable"]
    targets: tuple[KisPaperIntradayHeadCollectionRecoveryTarget, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_safe_id(self.category, "collection recovery category")
        targets = tuple(self.targets)
        object.__setattr__(self, "targets", targets)
        if self.capture_binding_status == "evidence_unavailable":
            if self.category != "evidence_unavailable" or targets:
                raise KisPaperIntradayHeadScheduleReceiptError(
                    "collection_recovery_binding_invalid"
                )
            return
        if self.capture_binding_status != "verified":
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_binding_invalid")
        if {target.target_key for target in targets} != _CAPTURE_TARGET_KEYS:
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")
        if len(targets) != len(_CAPTURE_TARGET_KEYS):
            raise KisPaperIntradayHeadScheduleReceiptError("collection_recovery_target_invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_INTRADAY_HEAD_COLLECTION_RECOVERY_FACT_KIND,
            "status": self.category,
            "capture_binding_status": self.capture_binding_status,
            "targets": [target.safe_payload() for target in self.targets],
        }


@dataclass(frozen=True)
class _ScheduleRuntimePointer:
    run_id: str
    observed_at: datetime
    terminal_status: Literal["complete", "recovery"]
    recovery_class: str
    scheduler_exit_code: int
    receipt_sha256: str


@dataclass(frozen=True)
class _ScheduleReceiptTerminal:
    run_id: str
    observed_at: datetime
    terminal_status: Literal["complete", "recovery"]
    recovery_class: str
    scheduler_exit_code: int
    session_capture_binding_required: bool
    terminal_receipt_binding: KisPaperIntradayHeadTerminalReceiptBinding | None
    availability_status: str
    availability_receipt_binding: KisPaperIntradayHeadAvailabilityReceiptBinding | None
    observation_attempt_binding: KisPaperIntradayHeadObservationAttemptBinding | None
    causal_attestation_binding: KisPaperIntradayHeadCausalAttestationBinding | None


def write_kis_paper_intraday_head_schedule_receipt(
    *,
    run_id: str,
    collection_exit_code: int,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    observation_exit_code: int,
    observation_status: str,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
    availability_exit_code: int = 0,
    availability_status: str = "not_applicable",
    availability_contract_sha256: str | None = None,
    availability_receipt_sha256: str | None = None,
    availability_precommit_sha256: str | None = None,
    availability_summary_sha256: str | None = None,
    causal_attestation_sha256: str | None = None,
    observation_attempt_sha256: str | None = None,
    observation_attempt_status: str | None = None,
    observation_store_outcome: str | None = None,
    prospective_validation_contract: str | None = None,
    session_capture_run_id: str | None = None,
    session_capture_observed_at: datetime | None = None,
    session_capture_receipt_sha256: str | None = None,
    session_capture_coverage_digest: str | None = None,
    session_capture_coverage_category: str | None = None,
    require_session_capture_binding: bool = False,
    artifact_root: Path = DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    observed_at: datetime,
) -> KisPaperIntradayHeadScheduleReceipt:
    """Write a terminal receipt without retaining provider, account, or order data.

    The collection process remains the authority for its own exit code. A
    The newer SPY cycle is a separately dispatched post-collection stage. The
    legacy QQQ branch may remain ``not_applicable`` while the data-only pair
    observation continues to publish its own credential-free fact.
    """

    _validate_schedule_receipt_inputs(
        run_id=run_id,
        collection_exit_code=collection_exit_code,
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
        prospective_validation_contract=prospective_validation_contract,
        availability_exit_code=availability_exit_code,
        availability_status=availability_status,
        observation_exit_code=observation_exit_code,
        observation_status=observation_status,
        capture_cycle_exit_code=capture_cycle_exit_code,
        capture_cycle_status=capture_cycle_status,
    )
    binding = _terminal_receipt_binding_from_inputs(
        session_capture_run_id=session_capture_run_id,
        session_capture_observed_at=session_capture_observed_at,
        session_capture_receipt_sha256=session_capture_receipt_sha256,
        session_capture_coverage_digest=session_capture_coverage_digest,
        session_capture_coverage_category=session_capture_coverage_category,
    )
    if binding is not None and binding.schedule_run_id != run_id:
        raise ValueError("terminal receipt binding run id must match schedule run id")
    availability_binding = _availability_receipt_binding_from_inputs(
        contract_sha256=availability_contract_sha256,
        receipt_sha256=availability_receipt_sha256,
        precommit_sha256=availability_precommit_sha256,
        summary_sha256=availability_summary_sha256,
    )
    if availability_binding is not None and availability_status not in {
        "qualified_for_prospective_input",
        "input_unavailable",
    }:
        raise ValueError("availability receipt binding does not match stage status")
    if availability_status == "qualified_for_prospective_input" and availability_binding is None:
        raise ValueError("qualified availability requires a receipt binding")
    causal_attestation_binding = _causal_attestation_binding_from_inputs(
        attestation_sha256=causal_attestation_sha256,
    )
    observation_binding = _observation_attempt_binding_from_inputs(
        attempt_sha256=observation_attempt_sha256,
        attempt_status=observation_attempt_status,
        store_outcome=observation_store_outcome,
    )
    if observation_binding is not None and observation_status not in {
        observation_binding.attempt_status,
        "duplicate",
    }:
        raise ValueError("observation attempt binding does not match stage status")
    if type(require_session_capture_binding) is not bool:
        raise ValueError("terminal receipt binding requirement is invalid")
    binding_required = require_session_capture_binding or binding is not None

    if binding_required and binding is None and collection_exit_code == 0:
        terminal_status, recovery_class, scheduler_exit_code = (
            "recovery",
            "session_capture_binding_unavailable",
            SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE,
        )
    else:
        terminal_status, recovery_class, scheduler_exit_code = _terminal_outcome(
            collection_exit_code=collection_exit_code,
            prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
            prospective_spy_cycle_status=prospective_spy_cycle_status,
            prospective_spy_cycle_id=prospective_spy_cycle_id,
            prospective_spy_canary_run_id=prospective_spy_canary_run_id,
            prospective_loop_exit_code=prospective_loop_exit_code,
            prospective_loop_status=prospective_loop_status,
            prospective_session_exit_code=prospective_session_exit_code,
            prospective_session_status=prospective_session_status,
            prospective_session_id=prospective_session_id,
            prospective_validation_exit_code=prospective_validation_exit_code,
            prospective_validation_status=prospective_validation_status,
            prospective_validation_session_id=prospective_validation_session_id,
            observation_exit_code=observation_exit_code,
            observation_status=observation_status,
            capture_cycle_exit_code=capture_cycle_exit_code,
            capture_cycle_status=capture_cycle_status,
        )
    root = _external_artifact_root(artifact_root=artifact_root, repository_root=repository_root)
    result = KisPaperIntradayHeadScheduleReceipt(
        run_id=run_id,
        observed_at=require_utc(observed_at, "observed_at"),
        collection_exit_code=collection_exit_code,
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
        prospective_validation_contract=prospective_validation_contract,
        availability_exit_code=availability_exit_code,
        availability_status=availability_status,
        availability_receipt_binding=availability_binding,
        observation_exit_code=observation_exit_code,
        observation_status=observation_status,
        capture_cycle_exit_code=capture_cycle_exit_code,
        capture_cycle_status=capture_cycle_status,
        session_capture_binding_required=binding_required,
        terminal_receipt_binding=binding,
        observation_attempt_binding=observation_binding,
        causal_attestation_binding=causal_attestation_binding,
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        evidence_path=(
            root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY / f"{run_id}.json"
        ),
    )
    _write_json_atomically(result.evidence_path, result.safe_payload())
    _write_schedule_runtime_pointer(
        root=root,
        receipt=result,
    )
    return result


def read_kis_paper_intraday_head_schedule_fact_from_artifact_root(
    artifact_root: Path,
    *,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    capture_cache_root: Path | None = None,
    observation_artifact_root: Path | None = None,
) -> KisPaperIntradayHeadScheduleFact:
    """Read the one task-written pointer and its exact immutable terminal receipt.

    This never searches for the newest receipt. The current pointer is written by
    the same single-owner task that wrote the referenced immutable evidence.
    """

    runtime, receipt, receipt_sha256 = _read_current_schedule_terminal(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    (
        coverage_binding_status,
        coverage_digest,
        coverage_category,
        coverage_gap_category,
    ) = _read_capture_binding(
        terminal=receipt,
        capture_cache_root=capture_cache_root,
        repository_root=repository_root,
    )
    availability_binding = receipt.availability_receipt_binding
    availability_binding_status = _read_availability_receipt_binding(
        terminal=receipt,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    (
        observation_binding_status,
        observation_attempt_sha256,
        observation_attempt_status,
        observation_store_outcome,
    ) = _read_observation_attempt_binding(
        terminal=receipt,
        observation_artifact_root=observation_artifact_root,
        repository_root=repository_root,
    )
    causal_attestation_binding_status, causal_attestation = _read_causal_attestation_binding(
        terminal=receipt,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    causal_input_status, causal_input_reason = _causal_input_terminal(
        terminal=receipt,
        coverage_binding_status=coverage_binding_status,
        coverage_category=coverage_category,
        observation_binding_status=observation_binding_status,
        observation_attempt_status=observation_attempt_status,
        observation_store_outcome=observation_store_outcome,
        causal_attestation=causal_attestation,
    )
    return KisPaperIntradayHeadScheduleFact(
        run_id=runtime.run_id,
        observed_at=runtime.observed_at,
        terminal_status=runtime.terminal_status,
        recovery_class=runtime.recovery_class,
        scheduler_exit_code=runtime.scheduler_exit_code,
        receipt_sha256=receipt_sha256,
        coverage_binding_status=coverage_binding_status,
        current_session_cumulative_coverage_digest=coverage_digest,
        current_session_cumulative_coverage_category=coverage_category,
        session_capture_receipt_sha256=(
            None
            if receipt.terminal_receipt_binding is None
            else receipt.terminal_receipt_binding.receipt_sha256
        ),
        current_session_cumulative_coverage_gap_category=coverage_gap_category,
        availability_status=receipt.availability_status,
        availability_binding_status=availability_binding_status,
        availability_contract_sha256=(
            None if availability_binding is None else availability_binding.contract_sha256
        ),
        availability_receipt_sha256=(
            None if availability_binding is None else availability_binding.receipt_sha256
        ),
        availability_precommit_sha256=(
            None if availability_binding is None else availability_binding.precommit_sha256
        ),
        availability_summary_sha256=(
            None if availability_binding is None else availability_binding.summary_sha256
        ),
        observation_binding_status=observation_binding_status,
        observation_attempt_sha256=observation_attempt_sha256,
        observation_attempt_status=observation_attempt_status,
        observation_store_outcome=observation_store_outcome,
        causal_attestation_binding_status=causal_attestation_binding_status,
        causal_attestation_sha256=(
            None
            if receipt.causal_attestation_binding is None
            else receipt.causal_attestation_binding.attestation_sha256
        ),
        clock_authority=(
            None if causal_attestation is None else causal_attestation.clock_authority
        ),
        timezone_dst_session_rule=(
            None if causal_attestation is None else causal_attestation.timezone_dst_session_rule
        ),
        completed_bar_geometry=(
            None if causal_attestation is None else causal_attestation.completed_bar_geometry
        ),
        chronological_boundary=(
            None if causal_attestation is None else causal_attestation.chronological_boundary
        ),
        causal_input_status=causal_input_status,
        causal_input_reason=causal_input_reason,
        decision_time_availability=(
            "attested"
            if (
                causal_attestation is not None
                and causal_attestation.decision_time_availability == "observed_at_decision_time"
            )
            else "not_observed"
        ),
        provider_finality=(
            "attested"
            if (
                causal_attestation is not None
                and causal_attestation.provider_finality == "observed_final"
            )
            else "not_observed"
        ),
    )


def read_kis_paper_intraday_head_collection_recovery_from_artifact_root(
    artifact_root: Path,
    *,
    repository_root: Path = _DEFAULT_REPOSITORY_ROOT,
    capture_cache_root: Path | None = None,
) -> KisPaperIntradayHeadCollectionRecoveryFact:
    """Project exact bound capture categories without exposing evidence paths or rows."""

    try:
        _, terminal, _ = _read_current_schedule_terminal(
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
        if (
            terminal.terminal_status != "recovery"
            or terminal.recovery_class != "collection_exit_nonzero"
        ):
            return _collection_recovery_evidence_unavailable()
        _, capture_payload = _read_bound_capture_receipt(
            terminal=terminal,
            capture_cache_root=capture_cache_root,
            repository_root=repository_root,
        )
        targets = _collection_recovery_targets_from_capture_payload(capture_payload)
    except (KisPaperIntradayHeadScheduleReceiptError, OSError, ValueError):
        return _collection_recovery_evidence_unavailable()
    return KisPaperIntradayHeadCollectionRecoveryFact(
        category=_collection_recovery_category(targets),
        capture_binding_status="verified",
        targets=targets,
    )


def _read_current_schedule_terminal(
    *,
    artifact_root: Path,
    repository_root: Path,
) -> tuple[_ScheduleRuntimePointer, _ScheduleReceiptTerminal, str]:
    root = _readable_external_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    runtime_path = root / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY / (
        KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    _require_direct_regular_file(
        root=root,
        path=runtime_path,
        error_code="schedule_runtime_invalid",
    )
    _, runtime_payload = _read_json_payload(runtime_path, "schedule_runtime_invalid")
    runtime = _runtime_from_payload(runtime_payload)
    evidence_path = (
        root
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
        / f"{runtime.run_id}.json"
    )
    _require_direct_regular_file(
        root=root,
        path=evidence_path,
        error_code="schedule_evidence_invalid",
    )
    receipt_bytes, receipt_payload = _read_json_payload(evidence_path, "schedule_evidence_invalid")
    receipt = _receipt_terminal_from_payload(receipt_payload)
    receipt_sha256 = _sha256(receipt_bytes)
    if (
        receipt_sha256 != runtime.receipt_sha256
        or receipt.run_id != runtime.run_id
        or receipt.observed_at != runtime.observed_at
        or receipt.terminal_status != runtime.terminal_status
        or receipt.recovery_class != runtime.recovery_class
        or receipt.scheduler_exit_code != runtime.scheduler_exit_code
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_receipt_mismatch")
    return runtime, receipt, receipt_sha256


def _validate_schedule_receipt_inputs(
    *,
    run_id: str,
    collection_exit_code: int,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    prospective_validation_contract: str | None,
    availability_exit_code: int,
    availability_status: str,
    observation_exit_code: int,
    observation_status: str,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
) -> None:
    _require_schedule_run_id(run_id, "run id")
    _require_exit_codes(
        collection_exit_code,
        prospective_spy_cycle_exit_code,
        prospective_loop_exit_code,
        prospective_session_exit_code,
        prospective_validation_exit_code,
        availability_exit_code,
        observation_exit_code,
        capture_cycle_exit_code,
    )
    _require_status(prospective_loop_status, _LOOP_STATUSES, "prospective loop")
    _require_status(prospective_session_status, _SESSION_STATUSES, "prospective session")
    _require_status(prospective_validation_status, _VALIDATION_STATUSES, "prospective validation")
    _require_status(prospective_spy_cycle_status, _SPY_CYCLE_STATUSES, "prospective SPY cycle")
    _require_status(availability_status, _AVAILABILITY_STATUSES, "availability")
    _require_status(observation_status, _OBSERVATION_STATUSES, "observation")
    _require_status(capture_cycle_status, _CAPTURE_CYCLE_STATUSES, "capture cycle")
    _require_optional_safe_id(prospective_session_id, "prospective session id")
    _require_optional_safe_id(prospective_spy_cycle_id, "prospective SPY cycle id")
    _require_optional_safe_id(prospective_spy_canary_run_id, "prospective SPY canary run id")
    _require_optional_safe_id(
        prospective_validation_session_id,
        "prospective validation session id",
    )
    _require_optional_safe_id(
        prospective_validation_contract,
        "prospective validation contract",
    )


def _write_schedule_runtime_pointer(
    *,
    root: Path,
    receipt: KisPaperIntradayHeadScheduleReceipt,
) -> None:
    """Advance the task-owned current pointer only after immutable evidence exists."""

    try:
        receipt_bytes = receipt.evidence_path.read_bytes()
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid") from error
    runtime_path = (
        root
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_DIRECTORY
        / KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME
    )
    if runtime_path.exists():
        _require_direct_regular_file(
            root=root,
            path=runtime_path,
            error_code="schedule_runtime_invalid",
        )
        _, current_payload = _read_json_payload(runtime_path, "schedule_runtime_invalid")
        current = _runtime_from_payload(current_payload)
        if current.observed_at > receipt.observed_at:
            return
        if current.observed_at == receipt.observed_at and current.run_id != receipt.run_id:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_pointer_conflict")
    _replace_json_atomically(
        runtime_path,
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_KIND,
            "run_id": receipt.run_id,
            "observed_at": _utc_marker(receipt.observed_at),
            "status": receipt.terminal_status,
            "recovery_class": receipt.recovery_class,
            "scheduler_exit_code": receipt.scheduler_exit_code,
            "receipt_sha256": _sha256(receipt_bytes),
        },
    )


def _runtime_from_payload(payload: Mapping[str, Any]) -> _ScheduleRuntimePointer:
    if (
        frozenset(payload) != _SCHEDULE_RUNTIME_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_KIND
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_invalid")
    run_id = _payload_schedule_run_id(payload.get("run_id"), "runtime run id")
    observed_at = _payload_utc(payload.get("observed_at"), "runtime observed at")
    terminal_status, recovery_class, scheduler_exit_code = _schedule_terminal_values(
        status=payload.get("status"),
        recovery_class=payload.get("recovery_class"),
        scheduler_exit_code=payload.get("scheduler_exit_code"),
        error_code="schedule_runtime_terminal_invalid",
    )
    return _ScheduleRuntimePointer(
        run_id=run_id,
        observed_at=observed_at,
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        receipt_sha256=_payload_sha256(payload.get("receipt_sha256"), "runtime receipt sha256"),
    )


def _receipt_terminal_from_payload(payload: Mapping[str, Any]) -> _ScheduleReceiptTerminal:
    if (
        frozenset(payload)
        not in {
            _SCHEDULE_RECEIPT_KEYS,
            _SCHEDULE_RECEIPT_KEYS | {_SCHEDULE_RECEIPT_BINDING_KEY},
            _SCHEDULE_RECEIPT_KEYS | {_SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY},
            _SCHEDULE_RECEIPT_KEYS
            | {_SCHEDULE_RECEIPT_BINDING_KEY, _SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY},
            _SCHEDULE_RECEIPT_KEYS | {_SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY},
            _SCHEDULE_RECEIPT_KEYS
            | {
                _SCHEDULE_RECEIPT_BINDING_KEY,
                _SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY,
            },
            _SCHEDULE_RECEIPT_KEYS
            | {
                _SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY,
                _SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY,
            },
            _SCHEDULE_RECEIPT_KEYS
            | {
                _SCHEDULE_RECEIPT_BINDING_KEY,
                _SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY,
                _SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY,
            },
        }
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_KIND
        or payload.get("artifact_policy") != _SCHEDULE_RECEIPT_ARTIFACT_POLICY
        or payload.get("claim") != _SCHEDULE_RECEIPT_CLAIM
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    terminal = payload.get("terminal")
    if not isinstance(terminal, Mapping) or frozenset(terminal) != _SCHEDULE_RECEIPT_TERMINAL_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    terminal_status, recovery_class, scheduler_exit_code = _schedule_terminal_values(
        status=terminal.get("status"),
        recovery_class=terminal.get("recovery_class"),
        scheduler_exit_code=terminal.get("scheduler_exit_code"),
        error_code="schedule_evidence_invalid",
    )
    if payload.get("status") != terminal_status:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    binding_required = _SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY in payload
    if binding_required and payload.get(_SCHEDULE_RECEIPT_BINDING_REQUIRED_KEY) is not True:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    binding_value = payload.get(_SCHEDULE_RECEIPT_BINDING_KEY)
    binding = (
        None
        if binding_value is None
        else _terminal_receipt_binding_from_payload(
            binding_value,
            error_code="schedule_evidence_invalid",
        )
    )
    binding_required = binding_required or binding is not None
    stages = payload.get("stages")
    if not isinstance(stages, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    availability_status = "not_recorded_legacy"
    availability_binding = None
    availability = stages.get("availability")
    if availability is not None:
        if not isinstance(availability, Mapping) or frozenset(availability) not in {
            frozenset({"exit_code", "status", "source_local"}),
            frozenset(
                {
                    "exit_code",
                    "status",
                    "source_local",
                    _SCHEDULE_RECEIPT_AVAILABILITY_BINDING_KEY,
                }
            ),
        }:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
        if availability.get("source_local") is not True:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
        _payload_exit_code(availability.get("exit_code"), "availability exit code")
        availability_status = _payload_safe_id(
            availability.get("status"),
            "availability status",
        )
        if availability_status not in _AVAILABILITY_STATUSES:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
        availability_value = availability.get(_SCHEDULE_RECEIPT_AVAILABILITY_BINDING_KEY)
        availability_binding = (
            None
            if availability_value is None
            else _availability_receipt_binding_from_payload(
                availability_value,
                error_code="schedule_evidence_invalid",
            )
        )
        if (
            availability_status == "qualified_for_prospective_input"
            and availability_binding is None
        ):
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    observation = stages.get("observation")
    if not isinstance(observation, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_evidence_invalid")
    observation_value = observation.get("attempt_binding")
    observation_binding = (
        None
        if observation_value is None
        else _observation_attempt_binding_from_payload(
            observation_value,
            error_code="schedule_evidence_invalid",
        )
    )
    causal_attestation_value = payload.get(_SCHEDULE_RECEIPT_CAUSAL_ATTESTATION_BINDING_KEY)
    causal_attestation_binding = (
        None
        if causal_attestation_value is None
        else _causal_attestation_binding_from_payload(
            causal_attestation_value,
            error_code="schedule_evidence_invalid",
        )
    )
    return _ScheduleReceiptTerminal(
        run_id=_payload_schedule_run_id(payload.get("run_id"), "receipt run id"),
        observed_at=_payload_utc(payload.get("observed_at"), "receipt observed at"),
        terminal_status=terminal_status,
        recovery_class=recovery_class,
        scheduler_exit_code=scheduler_exit_code,
        session_capture_binding_required=binding_required,
        terminal_receipt_binding=binding,
        availability_status=availability_status,
        availability_receipt_binding=availability_binding,
        observation_attempt_binding=observation_binding,
        causal_attestation_binding=causal_attestation_binding,
    )


def _terminal_receipt_binding_from_inputs(
    *,
    session_capture_run_id: str | None,
    session_capture_observed_at: datetime | None,
    session_capture_receipt_sha256: str | None,
    session_capture_coverage_digest: str | None,
    session_capture_coverage_category: str | None,
) -> KisPaperIntradayHeadTerminalReceiptBinding | None:
    values = (
        session_capture_run_id,
        session_capture_observed_at,
        session_capture_receipt_sha256,
        session_capture_coverage_digest,
        session_capture_coverage_category,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("terminal receipt binding is invalid")
    try:
        return KisPaperIntradayHeadTerminalReceiptBinding(
            schedule_run_id=session_capture_run_id,
            observed_at=session_capture_observed_at,
            receipt_sha256=session_capture_receipt_sha256,
            current_session_cumulative_coverage_digest=session_capture_coverage_digest,
            current_session_cumulative_coverage_category=session_capture_coverage_category,
        )
    except ValueError as error:
        raise ValueError("terminal receipt binding is invalid") from error


def _availability_receipt_binding_from_inputs(
    *,
    contract_sha256: str | None,
    receipt_sha256: str | None,
    precommit_sha256: str | None,
    summary_sha256: str | None,
) -> KisPaperIntradayHeadAvailabilityReceiptBinding | None:
    values = (contract_sha256, receipt_sha256, precommit_sha256, summary_sha256)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("availability receipt binding is invalid")
    try:
        return KisPaperIntradayHeadAvailabilityReceiptBinding(
            contract_sha256=contract_sha256,
            receipt_sha256=receipt_sha256,
            precommit_sha256=precommit_sha256,
            summary_sha256=summary_sha256,
        )
    except ValueError as error:
        raise ValueError("availability receipt binding is invalid") from error


def _causal_attestation_binding_from_inputs(
    *,
    attestation_sha256: str | None,
) -> KisPaperIntradayHeadCausalAttestationBinding | None:
    if attestation_sha256 is None:
        return None
    try:
        return KisPaperIntradayHeadCausalAttestationBinding(
            attestation_sha256=attestation_sha256,
        )
    except ValueError as error:
        raise ValueError("causal attestation binding is invalid") from error


def _observation_attempt_binding_from_inputs(
    *,
    attempt_sha256: str | None,
    attempt_status: str | None,
    store_outcome: str | None,
) -> KisPaperIntradayHeadObservationAttemptBinding | None:
    values = (attempt_sha256, attempt_status, store_outcome)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("observation attempt binding is invalid")
    try:
        return KisPaperIntradayHeadObservationAttemptBinding(
            attempt_sha256=attempt_sha256,
            attempt_status=attempt_status,  # type: ignore[arg-type]
            store_outcome=store_outcome,  # type: ignore[arg-type]
        )
    except ValueError as error:
        raise ValueError("observation attempt binding is invalid") from error


def _terminal_receipt_binding_from_payload(
    value: object,
    *,
    error_code: str,
) -> KisPaperIntradayHeadTerminalReceiptBinding:
    if not isinstance(value, Mapping) or frozenset(value) != _TERMINAL_RECEIPT_BINDING_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        return KisPaperIntradayHeadTerminalReceiptBinding(
            schedule_run_id=_payload_schedule_run_id(
                value.get("schedule_run_id"),
                "binding schedule run id",
            ),
            observed_at=_payload_utc(value.get("observed_at"), "binding observed at"),
            receipt_sha256=_payload_sha256(value.get("receipt_sha256"), "binding receipt sha256"),
            current_session_cumulative_coverage_digest=_payload_sha256(
                value.get("current_session_cumulative_coverage_digest"),
                "binding cumulative coverage digest",
            ),
            current_session_cumulative_coverage_category=_payload_capture_coverage_category(
                value.get("current_session_cumulative_coverage_category"),
                "binding cumulative coverage category",
            ),
        )
    except KisPaperIntradayHeadScheduleReceiptError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error


def _availability_receipt_binding_from_payload(
    value: object,
    *,
    error_code: str,
) -> KisPaperIntradayHeadAvailabilityReceiptBinding:
    if not isinstance(value, Mapping) or frozenset(value) != _AVAILABILITY_RECEIPT_BINDING_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        return KisPaperIntradayHeadAvailabilityReceiptBinding(
            contract_sha256=_payload_sha256(
                value.get("contract_sha256"),
                "availability contract sha256",
            ),
            receipt_sha256=_payload_sha256(
                value.get("receipt_sha256"),
                "availability receipt sha256",
            ),
            precommit_sha256=_payload_sha256(
                value.get("precommit_sha256"),
                "availability precommit sha256",
            ),
            summary_sha256=_payload_sha256(
                value.get("summary_sha256"),
                "availability summary sha256",
            ),
        )
    except KisPaperIntradayHeadScheduleReceiptError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error


def _causal_attestation_binding_from_payload(
    value: object,
    *,
    error_code: str,
) -> KisPaperIntradayHeadCausalAttestationBinding:
    if not isinstance(value, Mapping) or frozenset(value) != _CAUSAL_ATTESTATION_BINDING_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        return KisPaperIntradayHeadCausalAttestationBinding(
            attestation_sha256=_payload_sha256(
                value.get("attestation_sha256"),
                "causal attestation sha256",
            )
        )
    except (KisPaperIntradayHeadScheduleReceiptError, ValueError) as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error


def _observation_attempt_binding_from_payload(
    value: object,
    *,
    error_code: str,
) -> KisPaperIntradayHeadObservationAttemptBinding:
    if not isinstance(value, Mapping) or frozenset(value) != _OBSERVATION_ATTEMPT_BINDING_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        return KisPaperIntradayHeadObservationAttemptBinding(
            attempt_sha256=_payload_sha256(
                value.get("attempt_sha256"),
                "observation attempt sha256",
            ),
            attempt_status=_payload_safe_id(
                value.get("attempt_status"),
                "observation attempt status",
            ),  # type: ignore[arg-type]
            store_outcome=_payload_safe_id(
                value.get("store_outcome"),
                "observation store outcome",
            ),  # type: ignore[arg-type]
        )
    except (KisPaperIntradayHeadScheduleReceiptError, ValueError) as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error


def _read_capture_binding(
    *,
    terminal: _ScheduleReceiptTerminal,
    capture_cache_root: Path | None,
    repository_root: Path,
) -> tuple[
    Literal["legacy_unbound", "verified"],
    str | None,
    str | None,
    Literal["current_session_missing", "current_session_short"] | None,
]:
    binding = terminal.terminal_receipt_binding
    if binding is None:
        if terminal.session_capture_binding_required:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_required")
        return "legacy_unbound", None, None, None
    binding, capture_payload = _read_bound_capture_receipt(
        terminal=terminal,
        capture_cache_root=capture_cache_root,
        repository_root=repository_root,
    )
    current_coverage = capture_payload.get("current_session_cumulative_coverage")
    if not isinstance(current_coverage, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    return (
        "verified",
        binding.current_session_cumulative_coverage_digest,
        binding.current_session_cumulative_coverage_category,
        _coverage_gap_category(current_coverage, observed_at=binding.observed_at),
    )


def _read_availability_receipt_binding(
    *,
    terminal: _ScheduleReceiptTerminal,
    artifact_root: Path,
    repository_root: Path,
) -> Literal["legacy_unbound", "verified"]:
    binding = terminal.availability_receipt_binding
    if binding is None:
        return "legacy_unbound"
    root = _readable_external_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    summary_path = (
        root
        / "data"
        / KIS_INTRADAY_MTF_AVAILABILITY_ARTIFACT_DIRECTORY
        / f"task-owned-{terminal.run_id}"
        / "summary.json"
    )
    _require_external_artifact_regular_file(
        root=root,
        path=summary_path,
        error_code="schedule_availability_summary_invalid",
    )
    summary_bytes, summary_payload = _read_json_payload(
        summary_path,
        "schedule_availability_summary_invalid",
    )
    if _sha256(summary_bytes) != binding.summary_sha256:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_binding_mismatch")
    _verify_availability_summary_binding(
        payload=summary_payload,
        binding=binding,
        availability_status=terminal.availability_status,
    )
    return "verified"


def _verify_availability_summary_binding(
    *,
    payload: Mapping[str, Any],
    binding: KisPaperIntradayHeadAvailabilityReceiptBinding,
    availability_status: str,
) -> None:
    if (
        frozenset(payload) != {"schema_version", "receipt_id", "precommit_sha256", "receipt"}
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("receipt_id") != KIS_INTRADAY_MTF_AVAILABILITY_RECEIPT_ID
        or _payload_sha256(payload.get("precommit_sha256"), "availability precommit sha256")
        != binding.precommit_sha256
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_binding_mismatch")
    receipt = payload.get("receipt")
    if not isinstance(receipt, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_summary_invalid")
    if (
        _payload_sha256(receipt.get("contract_sha256"), "availability contract sha256")
        != binding.contract_sha256
        or _payload_sha256(receipt.get("receipt_sha256"), "availability receipt sha256")
        != binding.receipt_sha256
        or receipt.get("status") != availability_status
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_binding_mismatch")


def _read_observation_attempt_binding(
    *,
    terminal: _ScheduleReceiptTerminal,
    observation_artifact_root: Path | None,
    repository_root: Path,
) -> tuple[
    Literal["legacy_unbound", "verified"],
    str | None,
    Literal["observed", "not_observed"] | None,
    Literal["appended", "duplicate"] | None,
]:
    binding = terminal.observation_attempt_binding
    if binding is None:
        return "legacy_unbound", None, None, None
    if observation_artifact_root is None:
        raise KisPaperIntradayHeadScheduleReceiptError(
            "schedule_observation_artifact_root_required"
        )
    try:
        attempt = read_kis_qqq_spy_mtf_prospective_attempt(
            artifact_root=observation_artifact_root,
            repo_root=repository_root,
            attempt_sha256=binding.attempt_sha256,
        )
        contract = read_kis_qqq_spy_mtf_prospective_contract(
            artifact_root=observation_artifact_root,
            repo_root=repository_root,
        )
    except (KisQqqSpyMtfProspectiveObservationError, OSError, ValueError) as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            "schedule_observation_attempt_invalid"
        ) from error
    _verify_observation_attempt_binding(
        terminal=terminal,
        binding=binding,
        attempt=attempt,
        contract=contract,
    )
    return (
        "verified",
        binding.attempt_sha256,
        binding.attempt_status,
        binding.store_outcome,
    )


def _verify_observation_attempt_binding(
    *,
    terminal: _ScheduleReceiptTerminal,
    binding: KisPaperIntradayHeadObservationAttemptBinding,
    attempt: KisQqqSpyMtfProspectiveAttempt,
    contract: KisQqqSpyMtfProspectiveContract,
) -> None:
    availability_binding = terminal.availability_receipt_binding
    if (
        attempt.attempt_sha256 != binding.attempt_sha256
        or attempt.status != binding.attempt_status
        or attempt.contract_sha256 != contract.contract_sha256
        or attempt.sealed_at > terminal.observed_at
        or attempt.session_date != terminal.observed_at.astimezone(_EASTERN_TZ).date()
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_observation_binding_mismatch")
    if availability_binding is None:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_binding_required")
    if (
        contract.availability_contract_sha256 != availability_binding.contract_sha256
        or contract.availability_receipt_sha256 != availability_binding.receipt_sha256
        or contract.availability_precommit_sha256 != availability_binding.precommit_sha256
        or contract.availability_summary_sha256 != availability_binding.summary_sha256
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_availability_binding_mismatch")


def _read_causal_attestation_binding(
    *,
    terminal: _ScheduleReceiptTerminal,
    artifact_root: Path,
    repository_root: Path,
) -> tuple[
    Literal["not_recorded", "verified"],
    _KisPaperIntradayHeadCausalAttestation | None,
]:
    binding = terminal.causal_attestation_binding
    if binding is None:
        return "not_recorded", None
    root = _readable_external_artifact_root(
        artifact_root=artifact_root,
        repository_root=repository_root,
    )
    path = (
        root
        / "data"
        / KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_ARTIFACT_DIRECTORY
        / f"{terminal.run_id}.json"
    )
    _require_external_artifact_regular_file(
        root=root,
        path=path,
        error_code="schedule_causal_attestation_invalid",
    )
    encoded, payload = _read_json_payload(path, "schedule_causal_attestation_invalid")
    if _sha256(encoded) != binding.attestation_sha256:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_attestation_mismatch")
    attestation = _causal_attestation_from_payload(payload)
    _verify_causal_attestation_binding(terminal=terminal, attestation=attestation)
    return "verified", attestation


def _causal_attestation_from_payload(
    payload: Mapping[str, Any],
) -> _KisPaperIntradayHeadCausalAttestation:
    if (
        frozenset(payload) != _CAUSAL_ATTESTATION_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_PAPER_INTRADAY_HEAD_CAUSAL_ATTESTATION_KIND
        or payload.get("artifact_policy") != _CAUSAL_ATTESTATION_ARTIFACT_POLICY
        or payload.get("claim") != _CAUSAL_ATTESTATION_CLAIM
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_attestation_invalid")
    try:
        return _KisPaperIntradayHeadCausalAttestation(
            schedule_run_id=_payload_schedule_run_id(
                payload.get("schedule_run_id"),
                "causal attestation run id",
            ),
            schedule_observed_at=_payload_utc(
                payload.get("schedule_observed_at"),
                "causal attestation observed at",
            ),
            session_capture_receipt_sha256=_payload_sha256(
                payload.get("session_capture_receipt_sha256"),
                "causal attestation capture sha256",
            ),
            availability_summary_sha256=_payload_sha256(
                payload.get("availability_summary_sha256"),
                "causal attestation availability sha256",
            ),
            observation_attempt_sha256=_payload_sha256(
                payload.get("observation_attempt_sha256"),
                "causal attestation observation sha256",
            ),
            attestation_origin=_payload_causal_attestation_category(
                payload.get("attestation_origin"),
                _CAUSAL_ATTESTATION_ORIGINS,
                "causal attestation origin",
            ),
            clock_authority=_payload_causal_attestation_category(
                payload.get("clock_authority"),
                _CAUSAL_ATTESTATION_CLOCK_AUTHORITIES,
                "causal clock authority",
            ),
            timezone_dst_session_rule=_payload_causal_attestation_category(
                payload.get("timezone_dst_session_rule"),
                _CAUSAL_ATTESTATION_TIMEZONE_DST_SESSION_RULES,
                "causal timezone DST session rule",
            ),
            completed_bar_geometry=_payload_causal_attestation_category(
                payload.get("completed_bar_geometry"),
                _CAUSAL_ATTESTATION_COMPLETED_BAR_GEOMETRIES,
                "causal completed bar geometry",
            ),
            chronological_boundary=_payload_causal_attestation_category(
                payload.get("chronological_boundary"),
                _CAUSAL_ATTESTATION_CHRONOLOGICAL_BOUNDARIES,
                "causal chronological boundary",
            ),
            decision_time_availability=_payload_causal_attestation_category(
                payload.get("decision_time_availability"),
                _CAUSAL_ATTESTATION_DECISION_TIME_AVAILABILITY,
                "causal decision time availability",
            ),
            provider_finality=_payload_causal_attestation_category(
                payload.get("provider_finality"),
                _CAUSAL_ATTESTATION_PROVIDER_FINALITY,
                "causal provider finality",
            ),
        )
    except KisPaperIntradayHeadScheduleReceiptError:
        raise


def _verify_causal_attestation_binding(
    *,
    terminal: _ScheduleReceiptTerminal,
    attestation: _KisPaperIntradayHeadCausalAttestation,
) -> None:
    capture_binding = terminal.terminal_receipt_binding
    availability_binding = terminal.availability_receipt_binding
    observation_binding = terminal.observation_attempt_binding
    if (
        capture_binding is None
        or availability_binding is None
        or observation_binding is None
        or attestation.schedule_run_id != terminal.run_id
        or attestation.schedule_observed_at != terminal.observed_at
        or attestation.session_capture_receipt_sha256 != capture_binding.receipt_sha256
        or attestation.availability_summary_sha256 != availability_binding.summary_sha256
        or attestation.observation_attempt_sha256 != observation_binding.attempt_sha256
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_causal_attestation_mismatch")


def _causal_input_terminal(
    *,
    terminal: _ScheduleReceiptTerminal,
    coverage_binding_status: Literal["legacy_unbound", "verified"],
    coverage_category: str | None,
    observation_binding_status: Literal["legacy_unbound", "verified"],
    observation_attempt_status: Literal["observed", "not_observed"] | None,
    observation_store_outcome: Literal["appended", "duplicate"] | None,
    causal_attestation: _KisPaperIntradayHeadCausalAttestation | None,
) -> tuple[Literal["input_unavailable", "qualified"], str]:
    if terminal.terminal_status != "complete":
        return "input_unavailable", "terminal_recovery"
    if coverage_binding_status != "verified":
        return "input_unavailable", "session_capture_unbound"
    if coverage_category != "complete":
        return "input_unavailable", "session_coverage_incomplete"
    if terminal.availability_status == "not_recorded_legacy":
        return "input_unavailable", "historical_availability_unbound"
    if terminal.availability_receipt_binding is None:
        return "input_unavailable", "historical_availability_unbound"
    if terminal.availability_status != "qualified_for_prospective_input":
        return "input_unavailable", "historical_availability_unavailable"
    if observation_binding_status != "verified":
        return "input_unavailable", "prospective_observation_unbound"
    if observation_store_outcome != "appended":
        return "input_unavailable", "prospective_observation_duplicate"
    if observation_attempt_status != "observed":
        return "input_unavailable", "prospective_pair_not_observed"
    if causal_attestation is None:
        return "input_unavailable", "decision_time_availability_not_observed"
    if causal_attestation.clock_authority != "independent_utc_clock":
        return "input_unavailable", "clock_authority_not_observed"
    if causal_attestation.timezone_dst_session_rule != "America_New_York_IANA_DST":
        return "input_unavailable", "timezone_dst_session_rule_not_observed"
    if causal_attestation.completed_bar_geometry != "m1_regular_session_complete_through_1530_et":
        return "input_unavailable", "completed_bar_geometry_not_observed"
    if causal_attestation.chronological_boundary != "non_overlapping":
        return "input_unavailable", "chronological_boundary_not_observed"
    if causal_attestation.decision_time_availability != "observed_at_decision_time":
        return "input_unavailable", "decision_time_availability_not_observed"
    if causal_attestation.provider_finality != "observed_final":
        return "input_unavailable", "provider_finality_not_observed"
    return "qualified", "qualified"


def _read_bound_capture_receipt(
    *,
    terminal: _ScheduleReceiptTerminal,
    capture_cache_root: Path | None,
    repository_root: Path,
) -> tuple[KisPaperIntradayHeadTerminalReceiptBinding, Mapping[str, Any]]:
    binding = terminal.terminal_receipt_binding
    if binding is None:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_required")
    if capture_cache_root is None:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_cache_root_required")
    if binding.schedule_run_id != terminal.run_id:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    if binding.observed_at > terminal.observed_at:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    if (
        binding.observed_at.astimezone(_EASTERN_TZ).date()
        != terminal.observed_at.astimezone(_EASTERN_TZ).date()
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    capture_root = _readable_capture_cache_root(
        cache_root=capture_cache_root,
        repository_root=repository_root,
    )
    capture_path = capture_root / _capture_receipt_filename(binding)
    _require_capture_regular_file(
        cache_root=Path(capture_cache_root),
        capture_root=capture_root,
        path=capture_path,
        error_code="schedule_capture_receipt_invalid",
    )
    capture_bytes, capture_payload = _read_json_payload(
        capture_path,
        "schedule_capture_receipt_invalid",
    )
    if _sha256(capture_bytes) != binding.receipt_sha256:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    _verify_capture_payload_binding(capture_payload, binding)
    return binding, capture_payload


def _capture_receipt_filename(binding: KisPaperIntradayHeadTerminalReceiptBinding) -> str:
    digest_prefix = binding.receipt_sha256.removeprefix("sha256:")[:16]
    return f"{binding.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest_prefix}.json"


def _readable_capture_cache_root(*, cache_root: Path, repository_root: Path) -> Path:
    requested_root = _lexical_absolute_path(cache_root)
    _require_no_link_ancestors(requested_root, "schedule_capture_cache_root_invalid")
    root = requested_root.resolve()
    repository = Path(repository_root).resolve()
    if root.is_relative_to(repository) or root.is_symlink() or not root.is_dir():
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_cache_root_invalid")
    return root.joinpath(*_CAPTURE_RECEIPT_DIRECTORY)


def _require_capture_regular_file(
    *,
    cache_root: Path,
    capture_root: Path,
    path: Path,
    error_code: str,
) -> None:
    requested_root = _lexical_absolute_path(cache_root)
    version_root = requested_root / _CAPTURE_RECEIPT_DIRECTORY[0]
    requested_capture_root = version_root / _CAPTURE_RECEIPT_DIRECTORY[1]
    _require_no_link_ancestors(path, error_code)
    for candidate in (requested_root, version_root, requested_capture_root, path):
        _require_non_link(candidate, error_code)
    if (
        capture_root != requested_capture_root.resolve()
        or not requested_root.is_dir()
        or not version_root.is_dir()
        or not requested_capture_root.is_dir()
        or not path.is_file()
    ):
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        is_regular_file = stat.S_ISREG(path.stat().st_mode)
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    if not is_regular_file:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _verify_capture_payload_binding(
    payload: Mapping[str, Any],
    binding: KisPaperIntradayHeadTerminalReceiptBinding,
) -> None:
    if payload.get("kind") != _CAPTURE_RECEIPT_KIND:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    try:
        capture_run_id = _payload_schedule_run_id(
            payload.get("schedule_run_id"),
            "capture schedule run id",
        )
        capture_observed_at = _payload_utc(payload.get("observed_at"), "capture observed at")
        coverage_digest = _payload_sha256(
            payload.get("current_session_cumulative_coverage_digest"),
            "capture cumulative coverage digest",
        )
        coverage_category = _payload_safe_id(
            payload.get("current_session_cumulative_coverage_category"),
            "capture cumulative coverage category",
        )
    except KisPaperIntradayHeadScheduleReceiptError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            "schedule_capture_receipt_invalid"
        ) from error
    if (
        capture_run_id != binding.schedule_run_id
        or capture_observed_at != binding.observed_at
        or coverage_digest != binding.current_session_cumulative_coverage_digest
        or coverage_category != binding.current_session_cumulative_coverage_category
    ):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    current_coverage = payload.get("current_session_cumulative_coverage")
    if not isinstance(current_coverage, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    if _coverage_digest(current_coverage) != coverage_digest:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    if _coverage_category(
        current_coverage,
        observed_at=capture_observed_at,
    ) != coverage_category:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")
    coverage_gap_category = _coverage_gap_category(
        current_coverage,
        observed_at=capture_observed_at,
    )
    if (coverage_category == "complete") != (coverage_gap_category is None):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_binding_mismatch")


def _collection_recovery_targets_from_capture_payload(
    payload: Mapping[str, Any],
) -> tuple[KisPaperIntradayHeadCollectionRecoveryTarget, ...]:
    values = payload.get("targets")
    if not isinstance(values, list) or len(values) != len(_CAPTURE_TARGET_KEYS):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    provenance_fields = frozenset(
        {
            "conflict_origin",
            "retained_head_conflict_disposition",
        }
    )
    provenance_shapes: set[frozenset[str]] = set()
    for value in values:
        if not isinstance(value, Mapping):
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
        shape = frozenset(field for field in provenance_fields if field in value)
        if shape not in {frozenset(), provenance_fields}:
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
        provenance_shapes.add(shape)
    if len(provenance_shapes) != 1:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    receipt_is_legacy = not next(iter(provenance_shapes))
    targets: list[KisPaperIntradayHeadCollectionRecoveryTarget] = []
    for value in values:
        if receipt_is_legacy:
            conflict_origin = "not_recorded_legacy"
            retained_head_conflict_disposition = "not_recorded_legacy"
        else:
            conflict_origin = value["conflict_origin"]
            retained_head_conflict_disposition = value["retained_head_conflict_disposition"]
        try:
            capture_target = KisPaperIntradaySessionCaptureTarget(
                target_key=value.get("target_key"),
                status=value.get("status"),
                row_count=value.get("row_count"),
                exact_overlap_rows=value.get("exact_overlap_rows"),
                reason=value.get("reason"),
                conflict_origin=(
                    conflict_origin if conflict_origin != "not_recorded_legacy" else None
                ),
                retained_head_conflict_disposition=(
                    retained_head_conflict_disposition
                    if retained_head_conflict_disposition != "not_recorded_legacy"
                    else "not_applicable"
                ),
            )
        except (TypeError, ValueError) as error:
            raise KisPaperIntradayHeadScheduleReceiptError(
                "schedule_capture_receipt_invalid"
            ) from error
        if (
            not receipt_is_legacy
            and capture_target.reason == "minute_duplicate_conflict"
            and capture_target.conflict_origin is None
        ):
            raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
        targets.append(
            KisPaperIntradayHeadCollectionRecoveryTarget(
                target_key=capture_target.target_key,
                status=capture_target.status,
                reason=capture_target.reason,
                conflict_origin=(
                    "not_recorded_legacy"
                    if receipt_is_legacy
                    else (
                        "not_applicable"
                        if capture_target.conflict_origin is None
                        else capture_target.conflict_origin
                    )
                ),
                retained_head_conflict_disposition=(
                    capture_target.retained_head_conflict_disposition
                    if not receipt_is_legacy
                    else "not_recorded_legacy"
                ),
            )
        )
    if {target.target_key for target in targets} != _CAPTURE_TARGET_KEYS:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    return tuple(sorted(targets, key=lambda target: target.target_key))


def _collection_recovery_category(
    targets: tuple[KisPaperIntradayHeadCollectionRecoveryTarget, ...],
) -> str:
    categories = {(target.status, target.reason) for target in targets}
    if len(categories) == 1:
        status, reason = next(iter(categories))
        if status == "rejected" and reason == "minute_duplicate_conflict":
            return "rejected_duplicate_conflict"
        return status if reason is None else f"{status}_{reason}"
    return "target_outcomes_mixed"


def _collection_recovery_evidence_unavailable() -> KisPaperIntradayHeadCollectionRecoveryFact:
    return KisPaperIntradayHeadCollectionRecoveryFact(
        category="evidence_unavailable",
        capture_binding_status="evidence_unavailable",
        targets=(),
    )


def _coverage_digest(coverage: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            coverage,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, UnicodeEncodeError) as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            "schedule_capture_receipt_invalid"
        ) from error
    return _sha256(encoded)


def _coverage_category(
    coverage: Mapping[str, Any],
    *,
    observed_at: datetime,
) -> Literal["complete", "incomplete"]:
    sessions = coverage.get("regular_session_coverage")
    if not isinstance(sessions, list):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    observed_session_date = observed_at.astimezone(_EASTERN_TZ).date().isoformat()
    matching_sessions = [
        item
        for item in sessions
        if isinstance(item, Mapping) and item.get("session_date") == observed_session_date
    ]
    if len(matching_sessions) > 1:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    if not matching_sessions:
        return "incomplete"
    status = matching_sessions[0].get("status")
    if status == "complete":
        return "complete"
    if status == "short":
        return "incomplete"
    raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")


def _coverage_gap_category(
    coverage: Mapping[str, Any],
    *,
    observed_at: datetime,
) -> Literal["current_session_missing", "current_session_short"] | None:
    """Return one safe reason for an incomplete current-session coverage category."""

    sessions = coverage.get("regular_session_coverage")
    if not isinstance(sessions, list):
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    observed_session_date = observed_at.astimezone(_EASTERN_TZ).date().isoformat()
    matching_sessions = [
        item
        for item in sessions
        if isinstance(item, Mapping) and item.get("session_date") == observed_session_date
    ]
    if len(matching_sessions) > 1:
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")
    if not matching_sessions:
        return "current_session_missing"
    status = matching_sessions[0].get("status")
    if status == "complete":
        return None
    if status == "short":
        return "current_session_short"
    raise KisPaperIntradayHeadScheduleReceiptError("schedule_capture_receipt_invalid")


def _schedule_terminal_values(
    *,
    status: object,
    recovery_class: object,
    scheduler_exit_code: object,
    error_code: str,
) -> tuple[Literal["complete", "recovery"], str, int]:
    terminal_status = _payload_text(status, "terminal status")
    parsed_recovery_class = _payload_safe_id(recovery_class, "terminal recovery class")
    parsed_exit_code = _payload_exit_code(scheduler_exit_code, "terminal scheduler exit code")
    if terminal_status == "complete":
        if parsed_recovery_class != "complete" or parsed_exit_code != 0:
            raise KisPaperIntradayHeadScheduleReceiptError(error_code)
        return "complete", parsed_recovery_class, parsed_exit_code
    if terminal_status == "recovery":
        if parsed_exit_code == 0:
            raise KisPaperIntradayHeadScheduleReceiptError(error_code)
        return "recovery", parsed_recovery_class, parsed_exit_code
    raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _payload_exit_code(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise KisPaperIntradayHeadScheduleReceiptError(f"schedule_{field_name}_invalid")
    return value


def _payload_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KisPaperIntradayHeadScheduleReceiptError(f"schedule_{field_name}_invalid")
    return value


def _payload_safe_id(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_safe_id(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _payload_capture_coverage_category(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_capture_coverage_category(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _payload_schedule_run_id(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_schedule_run_id(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _payload_causal_attestation_category(
    value: object,
    allowed: frozenset[str],
    field_name: str,
) -> str:
    text = _payload_safe_id(value, field_name)
    if text not in allowed:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        )
    return text


def _payload_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise KisPaperIntradayHeadScheduleReceiptError(f"schedule_{field_name}_invalid")
    try:
        return _parse_utc(value)
    except argparse.ArgumentTypeError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error


def _payload_sha256(value: object, field_name: str) -> str:
    text = _payload_text(value, field_name)
    try:
        _require_sha256(text, field_name)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(
            f"schedule_{field_name}_invalid"
        ) from error
    return text


def _terminal_outcome(
    *,
    collection_exit_code: int,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
    observation_exit_code: int,
    observation_status: str,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
) -> tuple[str, str, int]:
    if collection_exit_code != 0:
        return "recovery", "collection_exit_nonzero", collection_exit_code

    spy_cycle_recovery = _prospective_spy_cycle_recovery_class(
        prospective_spy_cycle_exit_code=prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=prospective_spy_cycle_status,
        prospective_spy_cycle_id=prospective_spy_cycle_id,
        prospective_spy_canary_run_id=prospective_spy_canary_run_id,
    )
    if spy_cycle_recovery is not None:
        return "recovery", spy_cycle_recovery, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE

    recovery_class = _first_downstream_recovery_class(
        prospective_loop_exit_code=prospective_loop_exit_code,
        prospective_loop_status=prospective_loop_status,
        prospective_session_exit_code=prospective_session_exit_code,
        prospective_session_status=prospective_session_status,
        prospective_session_id=prospective_session_id,
        prospective_validation_exit_code=prospective_validation_exit_code,
        prospective_validation_status=prospective_validation_status,
        prospective_validation_session_id=prospective_validation_session_id,
    )
    if recovery_class is None:
        if prospective_loop_status == "not_applicable":
            observation_recovery = _data_only_observation_recovery_class(
                observation_exit_code=observation_exit_code,
                observation_status=observation_status,
            )
            if observation_recovery is not None:
                return "recovery", observation_recovery, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
            capture_recovery = _data_only_capture_cycle_recovery_class(
                capture_cycle_exit_code=capture_cycle_exit_code,
                capture_cycle_status=capture_cycle_status,
            )
            if capture_recovery is not None:
                return "recovery", capture_recovery, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE
        return "complete", "complete", 0
    return "recovery", recovery_class, SCHEDULE_DOWNSTREAM_RECOVERY_EXIT_CODE


def _prospective_spy_cycle_recovery_class(
    *,
    prospective_spy_cycle_exit_code: int,
    prospective_spy_cycle_status: str,
    prospective_spy_cycle_id: str | None,
    prospective_spy_canary_run_id: str | None,
) -> str | None:
    if prospective_spy_cycle_exit_code != 0:
        return "prospective_spy_cycle_exit_nonzero"
    if prospective_spy_cycle_status == "not_applicable":
        return None
    if prospective_spy_cycle_status not in {"preview", "no_intent", "canary_completed"}:
        return "prospective_spy_cycle_payload_unavailable"
    if prospective_spy_cycle_id is None:
        return "prospective_spy_cycle_id_unavailable"
    if (
        prospective_spy_cycle_status == "canary_completed"
        and prospective_spy_canary_run_id is None
    ):
        return "prospective_spy_canary_run_id_unavailable"
    return None


def _first_downstream_recovery_class(
    *,
    prospective_loop_exit_code: int,
    prospective_loop_status: str,
    prospective_session_exit_code: int,
    prospective_session_status: str,
    prospective_session_id: str | None,
    prospective_validation_exit_code: int,
    prospective_validation_status: str,
    prospective_validation_session_id: str | None,
) -> str | None:
    if prospective_loop_exit_code != 0:
        return "prospective_loop_exit_nonzero"
    if prospective_loop_status == "not_applicable":
        if (
            prospective_session_exit_code == 0
            and prospective_session_status == "not_applicable"
            and prospective_session_id is None
            and prospective_validation_exit_code == 0
            and prospective_validation_status == "not_applicable"
            and prospective_validation_session_id is None
        ):
            return None
        return "not_applicable_execution_branch_invalid"
    if prospective_loop_status not in {"embedded", "preview", "no_intent"}:
        return "prospective_loop_payload_unavailable"
    if prospective_session_exit_code != 0:
        return "prospective_session_exit_nonzero"
    if prospective_session_status not in {"no_intent", "canary_completed"}:
        return "prospective_session_payload_unavailable"
    if prospective_session_id is None:
        return "prospective_session_id_unavailable"
    if prospective_validation_exit_code != 0:
        return "prospective_validation_exit_nonzero"
    if prospective_validation_status != "validated":
        return "prospective_validation_payload_unavailable"
    if prospective_validation_session_id != prospective_session_id:
        return "prospective_validation_session_mismatch"
    return None


def _data_only_observation_recovery_class(
    *,
    observation_exit_code: int,
    observation_status: str,
) -> str | None:
    """Require the current data-only branch to expose its own terminal fact."""

    if observation_exit_code != 0:
        return "observation_exit_nonzero"
    if observation_status not in {
        "pending",
        "observed",
        "not_observed",
        "duplicate",
        "conflict",
        "cap_reached",
    }:
        return "observation_payload_unavailable"
    return None


def _data_only_capture_cycle_recovery_class(
    *,
    capture_cycle_exit_code: int,
    capture_cycle_status: str,
) -> str | None:
    """Require the post-collection local forward capture to expose one fact."""

    if capture_cycle_exit_code != 0:
        return "capture_cycle_exit_nonzero"
    if capture_cycle_status not in {
        "outside_cycle_slot",
        "observed",
        "duplicate",
        "conflict",
        "input_unavailable",
        "outcome_unavailable",
        "input_mutated",
        "appended",
    }:
        return "capture_cycle_payload_unavailable"
    return None


def _readable_external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    requested_root = _lexical_absolute_path(artifact_root)
    _require_no_link_ancestors(requested_root, "schedule_runtime_invalid")
    root = requested_root.resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_invalid")
    if not root.is_dir():
        raise KisPaperIntradayHeadScheduleReceiptError("schedule_runtime_invalid")
    return root


def _require_direct_regular_file(*, root: Path, path: Path, error_code: str) -> None:
    _require_no_link_ancestors(path, error_code)
    execution_root = root / "execution"
    schedule_root = execution_root / "kis-paper-intraday-head-schedule"
    for candidate in (root, execution_root, schedule_root, path):
        _require_non_link(candidate, error_code)
    if not root.is_dir() or not execution_root.is_dir() or not schedule_root.is_dir():
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    if not path.is_file():
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        is_regular_file = stat.S_ISREG(path.stat().st_mode)
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    if not is_regular_file:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _require_external_artifact_regular_file(*, root: Path, path: Path, error_code: str) -> None:
    try:
        relative_path = path.relative_to(root)
    except ValueError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    _require_no_link_ancestors(path, error_code)
    directories = [root]
    current = root
    for part in relative_path.parts[:-1]:
        current = current / part
        directories.append(current)
    for candidate in (*directories, path):
        _require_non_link(candidate, error_code)
    if not all(directory.is_dir() for directory in directories) or not path.is_file():
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    try:
        is_regular_file = stat.S_ISREG(path.stat().st_mode)
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    if not is_regular_file:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _require_non_link(path: Path, error_code: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    is_reparse_point = bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
    if stat.S_ISLNK(metadata.st_mode) or is_reparse_point:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _lexical_absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_no_link_ancestors(path: Path, error_code: str) -> None:
    lexical_path = _lexical_absolute_path(path)
    for candidate in reversed((lexical_path, *lexical_path.parents)):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
        is_reparse_point = bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
        if stat.S_ISLNK(metadata.st_mode) or is_reparse_point:
            raise KisPaperIntradayHeadScheduleReceiptError(error_code)


def _read_json_payload(path: Path, error_code: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisPaperIntradayHeadScheduleReceiptError(error_code) from error
    if not isinstance(payload, Mapping):
        raise KisPaperIntradayHeadScheduleReceiptError(error_code)
    return encoded, payload


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _external_artifact_root(*, artifact_root: Path, repository_root: Path) -> Path:
    requested_root = _lexical_absolute_path(artifact_root)
    try:
        _require_no_link_ancestors(requested_root, "schedule_receipt_root_invalid")
    except KisPaperIntradayHeadScheduleReceiptError as error:
        raise ValueError("schedule receipt root must stay outside Git") from error
    root = requested_root.resolve()
    repository = Path(repository_root).resolve()
    mounted_artifact_root = root == repository / "model_artifacts" and root.is_mount()
    if (root.is_relative_to(repository) and not mounted_artifact_root) or root.is_symlink():
        raise ValueError("schedule receipt root must stay outside Git")
    root.mkdir(parents=True, exist_ok=True)
    try:
        _require_no_link_ancestors(root, "schedule_receipt_root_invalid")
    except KisPaperIntradayHeadScheduleReceiptError as error:
        raise ValueError("schedule receipt root must stay outside Git") from error
    return root


def _write_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != rendered:
            raise ValueError("schedule receipt evidence identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        if path.exists():
            if path.read_text(encoding="ascii") != rendered:
                raise ValueError("schedule receipt evidence identity conflicts")
            return
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _replace_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically refresh the one task-owned current runtime pointer."""

    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(rendered)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _require_exit_codes(*values: int) -> None:
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("schedule stage exit codes must be non-negative integers")


def _require_safe_id(value: str, name: str) -> None:
    if value in {".", ".."} or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")


def _require_capture_coverage_category(value: str, name: str) -> None:
    if value not in KIS_PAPER_INTRADAY_SESSION_CAPTURE_COVERAGE_CATEGORIES:
        raise ValueError(f"{name} is invalid")


def _require_schedule_run_id(value: str, name: str) -> None:
    _require_safe_id(value, name)
    if value.casefold() == KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RUNTIME_ARTIFACT_NAME.removesuffix(
        ".json"
    ).casefold():
        raise ValueError(f"{name} is reserved")


def _require_optional_safe_id(value: str | None, name: str) -> None:
    if value is not None:
        _require_safe_id(value, name)


def _require_status(value: str, allowed: frozenset[str], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{name} status is invalid")


def _require_sha256(value: str, name: str) -> None:
    if (
        not value.startswith("sha256:")
        or len(value) != len("sha256:") + 64
        or any(character not in "0123456789abcdef" for character in value.removeprefix("sha256:"))
    ):
        raise ValueError(f"{name} is invalid")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "observed_at").isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("observed_at must be a UTC timestamp") from error
    if parsed.tzinfo is not UTC:
        raise argparse.ArgumentTypeError("observed_at must be a UTC timestamp")
    return require_utc(parsed, "observed_at")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write source-safe terminal evidence for one intraday-head dispatch"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--collection-exit-code", type=int, required=True)
    parser.add_argument("--prospective-spy-cycle-exit-code", type=int, required=True)
    parser.add_argument("--prospective-spy-cycle-status", required=True)
    parser.add_argument("--prospective-spy-cycle-id")
    parser.add_argument("--prospective-spy-canary-run-id")
    parser.add_argument("--prospective-loop-exit-code", type=int, required=True)
    parser.add_argument("--prospective-loop-status", required=True)
    parser.add_argument("--prospective-session-exit-code", type=int, required=True)
    parser.add_argument("--prospective-session-status", required=True)
    parser.add_argument("--prospective-session-id")
    parser.add_argument("--prospective-validation-exit-code", type=int, required=True)
    parser.add_argument("--prospective-validation-status", required=True)
    parser.add_argument("--prospective-validation-session-id")
    parser.add_argument("--prospective-validation-contract")
    parser.add_argument("--availability-exit-code", type=int, default=0)
    parser.add_argument("--availability-status", default="not_applicable")
    parser.add_argument("--availability-contract-sha256")
    parser.add_argument("--availability-receipt-sha256")
    parser.add_argument("--availability-precommit-sha256")
    parser.add_argument("--availability-summary-sha256")
    parser.add_argument("--causal-attestation-sha256")
    parser.add_argument("--observation-attempt-sha256")
    parser.add_argument("--observation-attempt-status")
    parser.add_argument("--observation-store-outcome")
    parser.add_argument("--observation-exit-code", type=int, required=True)
    parser.add_argument("--observation-status", required=True)
    parser.add_argument("--capture-cycle-exit-code", type=int, required=True)
    parser.add_argument("--capture-cycle-status", required=True)
    parser.add_argument("--session-capture-run-id")
    parser.add_argument("--session-capture-observed-at", type=_parse_utc)
    parser.add_argument("--session-capture-receipt-sha256")
    parser.add_argument("--session-capture-coverage-digest")
    parser.add_argument("--session-capture-coverage-category")
    parser.add_argument("--require-session-capture-binding", action="store_true")
    parser.add_argument("--observed-at", type=_parse_utc, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_INTRADAY_HEAD_SCHEDULE_RECEIPT_ARTIFACT_ROOT,
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    terminal_receipt_binding = _terminal_receipt_binding_from_cli_args(args)
    result = write_kis_paper_intraday_head_schedule_receipt(
        run_id=args.run_id,
        collection_exit_code=args.collection_exit_code,
        prospective_spy_cycle_exit_code=args.prospective_spy_cycle_exit_code,
        prospective_spy_cycle_status=args.prospective_spy_cycle_status,
        prospective_spy_cycle_id=args.prospective_spy_cycle_id,
        prospective_spy_canary_run_id=args.prospective_spy_canary_run_id,
        prospective_loop_exit_code=args.prospective_loop_exit_code,
        prospective_loop_status=args.prospective_loop_status,
        prospective_session_exit_code=args.prospective_session_exit_code,
        prospective_session_status=args.prospective_session_status,
        prospective_session_id=args.prospective_session_id,
        prospective_validation_exit_code=args.prospective_validation_exit_code,
        prospective_validation_status=args.prospective_validation_status,
        prospective_validation_session_id=args.prospective_validation_session_id,
        prospective_validation_contract=args.prospective_validation_contract,
        availability_exit_code=args.availability_exit_code,
        availability_status=args.availability_status,
        availability_contract_sha256=args.availability_contract_sha256,
        availability_receipt_sha256=args.availability_receipt_sha256,
        availability_precommit_sha256=args.availability_precommit_sha256,
        availability_summary_sha256=args.availability_summary_sha256,
        causal_attestation_sha256=args.causal_attestation_sha256,
        observation_attempt_sha256=args.observation_attempt_sha256,
        observation_attempt_status=args.observation_attempt_status,
        observation_store_outcome=args.observation_store_outcome,
        observation_exit_code=args.observation_exit_code,
        observation_status=args.observation_status,
        capture_cycle_exit_code=args.capture_cycle_exit_code,
        capture_cycle_status=args.capture_cycle_status,
        require_session_capture_binding=args.require_session_capture_binding,
        **terminal_receipt_binding,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        observed_at=args.observed_at,
    )
    print(json.dumps(result.safe_payload(), sort_keys=True))


def _terminal_receipt_binding_from_cli_args(args: argparse.Namespace) -> dict[str, object]:
    values = {
        "session_capture_run_id": args.session_capture_run_id,
        "session_capture_observed_at": args.session_capture_observed_at,
        "session_capture_receipt_sha256": args.session_capture_receipt_sha256,
        "session_capture_coverage_digest": args.session_capture_coverage_digest,
        "session_capture_coverage_category": args.session_capture_coverage_category,
    }
    if all(value is None for value in values.values()):
        return values
    if any(value is None for value in values.values()):
        raise ValueError("terminal receipt binding arguments must be complete")
    return values


if __name__ == "__main__":
    main()

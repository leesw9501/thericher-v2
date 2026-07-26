"""Offline joint-event windows for a future QQQ/SPY daily breadth campaign."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from thericher_v2.data.kis_daily_corporate_actions import KisDailyCorporateActionSnapshot
    from thericher_v2.data.kis_daily_event_boundary_audit import KisDailyEventBoundaryAudit
    from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog

DEFAULT_MODEL_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
KIS_DAILY_JOINT_EVENT_WINDOW_CONTRACT_SCHEMA_VERSION = 2
KIS_DAILY_JOINT_EVENT_WINDOW_CONTRACT_KIND = "kis_daily_joint_event_window_contract"
KIS_DAILY_JOINT_EVENT_FOLD_INPUT_SCHEMA_VERSION = 1
KIS_DAILY_JOINT_EVENT_FOLD_INPUT_KIND = "kis_daily_joint_event_window_fold_input"
KIS_DAILY_JOINT_EVENT_FEATURE_SESSIONS = 20
KIS_DAILY_JOINT_EVENT_LABEL_HORIZON_SESSIONS = 2
KIS_DAILY_JOINT_EVENT_PRE_VALIDATION_GAP_SESSIONS = 22
KIS_DAILY_JOINT_EVENT_VALIDATION_SESSIONS = 252
KIS_DAILY_JOINT_EVENT_FOLD_COUNT = 3
KIS_DAILY_JOINT_EVENT_INITIAL_DEVELOPMENT_SESSIONS = 3783
KIS_DAILY_JOINT_EVENT_MIN_ELIGIBLE_DECISIONS = 128
KIS_DAILY_JOINT_EVENT_TARGET_POLICY_ID = (
    "completed_bar_close_t_next_bar_open_t_plus_1_following_bar_open_t_plus_2_v1"
)
KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING = "pending_claude_falsification_review"
KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE = "review_unavailable"

_MODEL_EXECUTION_REVIEWS = frozenset(
    {
        KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING,
        KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    }
)

_JOINT_SYMBOLS = ("QQQ", "SPY")
_JOINT_EVENT_KINDS = ("cash_distribution", "split")

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "adjclose",
        "adjustedclose",
        "volume",
        "vwap",
        "price",
        "prices",
        "return",
        "returns",
        "rawresponse",
        "rawresponses",
        "credential",
        "credentials",
        "secret",
        "secrets",
        "token",
        "tokens",
        "account",
        "accounts",
        "order",
        "orders",
        "orderintent",
        "broker",
        "brokerid",
        "brokerids",
        "execution",
        "executions",
        "intent",
        "intents",
        "position",
        "positions",
        "cash",
        "pnl",
        "rawdata",
        "rawbytes",
        "providerresponse",
        "providerresponses",
    }
)


def _positive_int(value: object, field_name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class KisDailyJointEventWindowSpec:
    """Precommitted geometry for the offline daily campaign candidate."""

    feature_session_count: int = KIS_DAILY_JOINT_EVENT_FEATURE_SESSIONS
    feature_return_prior_session_count: int = 1
    label_horizon_session_count: int = KIS_DAILY_JOINT_EVENT_LABEL_HORIZON_SESSIONS
    pre_validation_gap_session_count: int = KIS_DAILY_JOINT_EVENT_PRE_VALIDATION_GAP_SESSIONS
    validation_session_count: int = KIS_DAILY_JOINT_EVENT_VALIDATION_SESSIONS
    fold_count: int = KIS_DAILY_JOINT_EVENT_FOLD_COUNT
    initial_development_session_count: int = KIS_DAILY_JOINT_EVENT_INITIAL_DEVELOPMENT_SESSIONS
    minimum_eligible_decision_count: int = KIS_DAILY_JOINT_EVENT_MIN_ELIGIBLE_DECISIONS

    def __post_init__(self) -> None:
        for field_name, value in (
            ("feature_session_count", self.feature_session_count),
            ("feature_return_prior_session_count", self.feature_return_prior_session_count),
            ("label_horizon_session_count", self.label_horizon_session_count),
            ("pre_validation_gap_session_count", self.pre_validation_gap_session_count),
            ("validation_session_count", self.validation_session_count),
            ("fold_count", self.fold_count),
            ("initial_development_session_count", self.initial_development_session_count),
            ("minimum_eligible_decision_count", self.minimum_eligible_decision_count),
        ):
            _positive_int(value, field_name)
        if (
            self.pre_validation_gap_session_count
            < self.feature_session_count + self.label_horizon_session_count
        ):
            raise ValueError("joint event-window pre-validation gap is too small")
        if self.feature_return_prior_session_count != 1:
            raise ValueError("joint event-window requires one predecessor return session")
        if self.label_horizon_session_count != KIS_DAILY_JOINT_EVENT_LABEL_HORIZON_SESSIONS:
            raise ValueError("joint event-window label horizon is incompatible with its target")
        theoretical_validation_decisions = (
            self.validation_session_count
            - self.feature_session_count
            - self.feature_return_prior_session_count
            - self.label_horizon_session_count
            + 1
        )
        if self.minimum_eligible_decision_count > theoretical_validation_decisions:
            raise ValueError("joint event-window minimum eligible decision count is impossible")

    def document(self) -> dict[str, int]:
        return {
            "feature_session_count": self.feature_session_count,
            "feature_return_prior_session_count": self.feature_return_prior_session_count,
            "label_horizon_session_count": self.label_horizon_session_count,
            "target_policy_id": KIS_DAILY_JOINT_EVENT_TARGET_POLICY_ID,
            "pre_validation_gap_session_count": self.pre_validation_gap_session_count,
            "validation_session_count": self.validation_session_count,
            "fold_count": self.fold_count,
            "initial_development_session_count": self.initial_development_session_count,
            "minimum_eligible_decision_count": self.minimum_eligible_decision_count,
        }


DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC = KisDailyJointEventWindowSpec()


@dataclass(frozen=True, slots=True)
class _ValidatedJointEventInputs:
    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    event_boundary_audit_sha256: str
    event_boundary_mask_identity: str
    event_boundary_partition_identity: str
    sessions: tuple[date, ...]
    events: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class KisDailyJointEventSession:
    """One event date from either source symbol, with no prices or values."""

    session: date
    sources: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if type(self.session) is not date:
            raise ValueError("joint event session date is invalid")
        object.__setattr__(self, "sources", tuple(self.sources))
        if not self.sources or tuple(sorted(self.sources)) != self.sources:
            raise ValueError("joint event session sources are invalid")
        for symbol, event_kind in self.sources:
            if symbol not in _JOINT_SYMBOLS or event_kind not in _JOINT_EVENT_KINDS:
                raise ValueError("joint event session source is invalid")

    def document(self) -> dict[str, object]:
        return {
            "session": self.session.isoformat(),
            "sources": [
                {"symbol": symbol, "event_kind": event_kind}
                for symbol, event_kind in self.sources
            ],
        }


@dataclass(frozen=True, slots=True)
class KisDailyJointEventWindowFold:
    """One expanding development window and its independent validation window."""

    fold_id: str
    development_start_index: int
    development_end_index: int
    pre_validation_gap_start_index: int
    pre_validation_gap_end_index: int
    validation_start_index: int
    validation_end_index: int
    development_eligible_decision_indices: tuple[int, ...]
    validation_eligible_decision_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.fold_id:
            raise ValueError("joint event-window fold id is invalid")
        indices = (
            self.development_start_index,
            self.development_end_index,
            self.pre_validation_gap_start_index,
            self.pre_validation_gap_end_index,
            self.validation_start_index,
            self.validation_end_index,
        )
        if any(type(index) is not int or index < 0 for index in indices):
            raise ValueError("joint event-window fold indices are invalid")
        if (
            self.development_start_index != 0
            or self.development_end_index != self.pre_validation_gap_start_index
            or self.pre_validation_gap_end_index != self.validation_start_index
            or self.validation_end_index <= self.validation_start_index
        ):
            raise ValueError("joint event-window fold geometry is invalid")
        object.__setattr__(
            self,
            "development_eligible_decision_indices",
            tuple(self.development_eligible_decision_indices),
        )
        object.__setattr__(
            self,
            "validation_eligible_decision_indices",
            tuple(self.validation_eligible_decision_indices),
        )


@dataclass(frozen=True, slots=True)
class KisDailyJointEventWindowContract:
    """Hash-bound, non-executable research input geometry for QQQ/SPY only."""

    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    event_boundary_audit_sha256: str
    event_boundary_mask_identity: str
    event_boundary_partition_identity: str
    created_at_utc: datetime
    sessions: tuple[date, ...]
    joint_event_sessions: tuple[KisDailyJointEventSession, ...]
    folds: tuple[KisDailyJointEventWindowFold, ...]
    final_unused_tail_start_index: int
    spec: KisDailyJointEventWindowSpec
    model_execution_review: str = KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at_utc", _require_utc(self.created_at_utc))
        object.__setattr__(self, "sessions", tuple(self.sessions))
        object.__setattr__(self, "joint_event_sessions", tuple(self.joint_event_sessions))
        object.__setattr__(self, "folds", tuple(self.folds))
        if not isinstance(self.spec, KisDailyJointEventWindowSpec):
            raise ValueError("joint event-window spec is invalid")
        if self.model_execution_review not in _MODEL_EXECUTION_REVIEWS:
            raise ValueError("joint event-window model execution review is invalid")
        _require_sha256(self.catalog_dataset_hash, "catalog dataset hash")
        _require_sha256(self.catalog_index_hash, "catalog index hash")
        _require_sha256(self.sidecar_dataset_hash, "sidecar dataset hash")
        _require_sha256(self.sidecar_manifest_hash, "sidecar manifest hash")
        _require_sha256(self.event_boundary_audit_sha256, "event-boundary audit hash")
        _require_sha256(self.event_boundary_mask_identity, "event-boundary mask identity")
        _require_sha256(self.event_boundary_partition_identity, "event-boundary partition identity")
        if (
            len(self.sessions) < 2
            or tuple(sorted(self.sessions)) != self.sessions
            or len(set(self.sessions)) != len(self.sessions)
        ):
            raise ValueError("joint event-window sessions are invalid")
        if len(self.folds) != self.spec.fold_count:
            raise ValueError("joint event-window fold count is invalid")
        if not 0 <= self.final_unused_tail_start_index < len(self.sessions):
            raise ValueError("joint event-window final tail is invalid")
        if tuple(marker.session for marker in self.joint_event_sessions) != tuple(
            sorted(marker.session for marker in self.joint_event_sessions)
        ):
            raise ValueError("joint event-window event sessions are invalid")
        if len({marker.session for marker in self.joint_event_sessions}) != len(
            self.joint_event_sessions
        ):
            raise ValueError("joint event-window event sessions are duplicated")
        if any(marker.session not in self.sessions for marker in self.joint_event_sessions):
            raise ValueError("joint event-window event session is outside the catalog")
        self._validate_folds()

    @property
    def joint_event_identity(self) -> str:
        return _sha256_json([marker.document() for marker in self.joint_event_sessions])

    @property
    def contract_identity(self) -> str:
        return _sha256_json(self._identity_document())

    def document(self) -> dict[str, object]:
        document = {
            "schema_version": KIS_DAILY_JOINT_EVENT_WINDOW_CONTRACT_SCHEMA_VERSION,
            "kind": KIS_DAILY_JOINT_EVENT_WINDOW_CONTRACT_KIND,
            "created_at_utc": self.created_at_utc.isoformat(),
            "status": "candidate",
            "lineage": {
                "catalog_dataset_hash": self.catalog_dataset_hash,
                "catalog_index_hash": self.catalog_index_hash,
                "sidecar_dataset_hash": self.sidecar_dataset_hash,
                "sidecar_manifest_hash": self.sidecar_manifest_hash,
                "session_dates_sha256": _session_dates_hash(self.sessions),
            },
            "event_boundary_audit": {
                "artifact_sha256": self.event_boundary_audit_sha256,
                "mask_identity": self.event_boundary_mask_identity,
                "partition_identity": self.event_boundary_partition_identity,
                "legacy_pair_mask_provenance_only": True,
            },
            "spec": self.spec.document(),
            "joint_event_identity": self.joint_event_identity,
            "joint_event_sessions": [marker.document() for marker in self.joint_event_sessions],
            "folds": [self._fold_document(fold) for fold in self.folds],
            "final_unused_tail": self._segment_document(
                self.final_unused_tail_start_index,
                len(self.sessions),
            ),
            "scope": {
                "offline_only": True,
                "model_execution_eligible": False,
                "model_execution_review": self.model_execution_review,
                "candidate_selection_eligible": False,
                "ensemble_eligible": False,
                "paper_decision_eligible": False,
                "generic_multi_fold_campaign_contract_eligible": False,
                "future_campaign_adapter_policy": (
                    "one_fold_per_generic_campaign_contract_with_joint_eligibility_identity"
                ),
                "raw_market_data_persisted": False,
                "provider_response_persisted": False,
                "credentials_persisted": False,
            },
        }
        document["contract_identity"] = self.contract_identity
        _assert_source_safe(document)
        return document

    def _identity_document(self) -> dict[str, object]:
        return {
            "schema_version": KIS_DAILY_JOINT_EVENT_WINDOW_CONTRACT_SCHEMA_VERSION,
            "kind": KIS_DAILY_JOINT_EVENT_WINDOW_CONTRACT_KIND,
            "lineage": {
                "catalog_dataset_hash": self.catalog_dataset_hash,
                "catalog_index_hash": self.catalog_index_hash,
                "sidecar_dataset_hash": self.sidecar_dataset_hash,
                "sidecar_manifest_hash": self.sidecar_manifest_hash,
                "session_dates_sha256": _session_dates_hash(self.sessions),
            },
            "event_boundary_audit": {
                "artifact_sha256": self.event_boundary_audit_sha256,
                "mask_identity": self.event_boundary_mask_identity,
                "partition_identity": self.event_boundary_partition_identity,
                "legacy_pair_mask_provenance_only": True,
            },
            "spec": self.spec.document(),
            "joint_event_sessions": [marker.document() for marker in self.joint_event_sessions],
            "folds": [self._fold_document(fold) for fold in self.folds],
            "final_unused_tail": self._segment_document(
                self.final_unused_tail_start_index,
                len(self.sessions),
            ),
        }

    def _fold_document(self, fold: KisDailyJointEventWindowFold) -> dict[str, object]:
        return {
            "fold_id": fold.fold_id,
            "development": self._segment_document(
                fold.development_start_index,
                fold.development_end_index,
            ),
            "pre_validation_gap": self._segment_document(
                fold.pre_validation_gap_start_index,
                fold.pre_validation_gap_end_index,
            ),
            "validation": self._segment_document(
                fold.validation_start_index,
                fold.validation_end_index,
            ),
            "development_eligible_decision_count": len(
                fold.development_eligible_decision_indices
            ),
            "development_eligible_decision_identity": self._decision_identity(
                fold.development_eligible_decision_indices
            ),
            "validation_eligible_decision_count": len(fold.validation_eligible_decision_indices),
            "validation_eligible_decision_identity": self._decision_identity(
                fold.validation_eligible_decision_indices
            ),
        }

    def _segment_document(self, start_index: int, end_index: int) -> dict[str, object]:
        return {
            "start_session": self.sessions[start_index].isoformat(),
            "end_session": self.sessions[end_index - 1].isoformat(),
            "session_count": end_index - start_index,
        }

    def _decision_identity(self, indices: tuple[int, ...]) -> str:
        return _sha256_json([self.sessions[index].isoformat() for index in indices])

    def _validate_folds(self) -> None:
        event_indices = {
            index
            for index, session in enumerate(self.sessions)
            if session in {marker.session for marker in self.joint_event_sessions}
        }
        previous_validation_end = 0
        for ordinal, fold in enumerate(self.folds, start=1):
            if fold.fold_id != f"expanding-{ordinal}":
                raise ValueError("joint event-window fold id is invalid")
            if fold.development_start_index != 0:
                raise ValueError(
                    "joint event-window development must expand from the first session"
                )
            if fold.pre_validation_gap_end_index - fold.pre_validation_gap_start_index != (
                self.spec.pre_validation_gap_session_count
            ):
                raise ValueError("joint event-window pre-validation gap is invalid")
            if fold.validation_end_index - fold.validation_start_index != (
                self.spec.validation_session_count
            ):
                raise ValueError("joint event-window validation size is invalid")
            if fold.validation_end_index > self.final_unused_tail_start_index:
                raise ValueError("joint event-window fold reaches the final unused tail")
            if ordinal == 1:
                if (
                    fold.development_end_index
                    != self.spec.initial_development_session_count
                ):
                    raise ValueError("joint event-window initial development size is invalid")
            elif fold.development_end_index != previous_validation_end:
                raise ValueError("joint event-window development is not expanding")
            self._validate_eligible_indices(
                fold.development_eligible_decision_indices,
                phase_start=fold.development_start_index,
                phase_end=fold.development_end_index,
                event_indices=event_indices,
            )
            expected_development = _eligible_decisions(
                phase_start=fold.development_start_index,
                phase_end=fold.development_end_index,
                event_indices=event_indices,
                spec=self.spec,
            )
            expected_validation = _eligible_decisions(
                phase_start=fold.validation_start_index,
                phase_end=fold.validation_end_index,
                event_indices=event_indices,
                spec=self.spec,
            )
            if fold.development_eligible_decision_indices != expected_development:
                raise ValueError("joint event-window development eligibility is not deterministic")
            if fold.validation_eligible_decision_indices != expected_validation:
                raise ValueError("joint event-window validation eligibility is not deterministic")
            self._validate_eligible_indices(
                fold.validation_eligible_decision_indices,
                phase_start=fold.validation_start_index,
                phase_end=fold.validation_end_index,
                event_indices=event_indices,
            )
            if (
                len(fold.development_eligible_decision_indices)
                < self.spec.minimum_eligible_decision_count
                or len(fold.validation_eligible_decision_indices)
                < self.spec.minimum_eligible_decision_count
            ):
                raise ValueError("joint event-window leaves too few eligible decisions")
            previous_validation_end = fold.validation_end_index
        if previous_validation_end != self.final_unused_tail_start_index:
            raise ValueError("joint event-window final tail does not follow the last fold")

    def _validate_eligible_indices(
        self,
        indices: tuple[int, ...],
        *,
        phase_start: int,
        phase_end: int,
        event_indices: set[int],
    ) -> None:
        if tuple(sorted(indices)) != indices or len(set(indices)) != len(indices):
            raise ValueError("joint event-window eligible decisions are invalid")
        for decision_index in indices:
            feature_start = (
                decision_index
                - self.spec.feature_session_count
                - self.spec.feature_return_prior_session_count
                + 1
            )
            label_end = decision_index + self.spec.label_horizon_session_count
            if feature_start < phase_start or label_end >= phase_end:
                raise ValueError("joint event-window decision crosses a phase boundary")
            if any(index in event_indices for index in range(feature_start, label_end + 1)):
                raise ValueError("joint event-window exposes an event to a decision")


@dataclass(frozen=True, slots=True)
class KisDailyJointEventWindowContractArtifact:
    path: Path
    content_hash: str
    contract: KisDailyJointEventWindowContract
    reattested_against_rebuild: bool = False


@dataclass(frozen=True, slots=True)
class KisDailyJointEventFoldInput:
    """One non-executable fold with its exact sparse joint eligibility."""

    source_artifact_sha256: str
    source_contract_identity: str
    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    event_boundary_audit_sha256: str
    event_boundary_mask_identity: str
    event_boundary_partition_identity: str
    joint_event_identity: str
    fold_id: str
    development_start_index: int
    development_end_index: int
    pre_validation_gap_start_index: int
    pre_validation_gap_end_index: int
    validation_start_index: int
    validation_end_index: int
    development_start_session: date
    development_end_session: date
    pre_validation_gap_start_session: date
    pre_validation_gap_end_session: date
    validation_start_session: date
    validation_end_session: date
    development_eligible_decision_indices: tuple[int, ...]
    validation_eligible_decision_indices: tuple[int, ...]
    development_eligible_decision_identity: str
    validation_eligible_decision_identity: str
    spec: KisDailyJointEventWindowSpec
    model_execution_review: str
    reattested_against_parent: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "source_artifact_sha256",
            "source_contract_identity",
            "catalog_dataset_hash",
            "catalog_index_hash",
            "sidecar_dataset_hash",
            "sidecar_manifest_hash",
            "event_boundary_audit_sha256",
            "event_boundary_mask_identity",
            "event_boundary_partition_identity",
            "joint_event_identity",
            "development_eligible_decision_identity",
            "validation_eligible_decision_identity",
        ):
            _require_sha256(
                getattr(self, field_name),
                f"joint event-window fold input {field_name}",
            )
        if not isinstance(self.fold_id, str) or not self.fold_id:
            raise ValueError("joint event-window fold input requires exactly one fold id")
        if not isinstance(self.spec, KisDailyJointEventWindowSpec):
            raise ValueError("joint event-window fold input spec is invalid")
        if self.model_execution_review != KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE:
            raise ValueError("joint event-window fold input must remain review_unavailable")
        if type(self.reattested_against_parent) is not bool:
            raise ValueError("joint event-window fold input reattestation is invalid")
        _validate_fold_input_geometry(self)

    @property
    def fold_input_identity(self) -> str:
        return _sha256_json(self._identity_document())

    def document(self) -> dict[str, object]:
        document = {
            "schema_version": KIS_DAILY_JOINT_EVENT_FOLD_INPUT_SCHEMA_VERSION,
            "kind": KIS_DAILY_JOINT_EVENT_FOLD_INPUT_KIND,
            "status": "candidate",
            "source_contract": {
                "artifact_sha256": self.source_artifact_sha256,
                "contract_identity": self.source_contract_identity,
            },
            "lineage": {
                "catalog_dataset_hash": self.catalog_dataset_hash,
                "catalog_index_hash": self.catalog_index_hash,
                "sidecar_dataset_hash": self.sidecar_dataset_hash,
                "sidecar_manifest_hash": self.sidecar_manifest_hash,
            },
            "event_boundary_audit": {
                "artifact_sha256": self.event_boundary_audit_sha256,
                "mask_identity": self.event_boundary_mask_identity,
                "partition_identity": self.event_boundary_partition_identity,
            },
            "joint_event_identity": self.joint_event_identity,
            "spec": self.spec.document(),
            "fold": self._fold_document(),
            "scope": {
                "offline_only": True,
                "model_execution_eligible": False,
                "model_execution_review": self.model_execution_review,
                "candidate_selection_eligible": False,
                "ensemble_eligible": False,
                "paper_decision_eligible": False,
                "generic_multi_fold_campaign_contract_eligible": False,
                "raw_market_data_persisted": False,
                "provider_response_persisted": False,
                "credentials_persisted": False,
            },
        }
        document["fold_input_identity"] = self.fold_input_identity
        _assert_source_safe(document)
        return document

    def _identity_document(self) -> dict[str, object]:
        return {
            "schema_version": KIS_DAILY_JOINT_EVENT_FOLD_INPUT_SCHEMA_VERSION,
            "kind": KIS_DAILY_JOINT_EVENT_FOLD_INPUT_KIND,
            "source_contract": {
                "artifact_sha256": self.source_artifact_sha256,
                "contract_identity": self.source_contract_identity,
            },
            "lineage": {
                "catalog_dataset_hash": self.catalog_dataset_hash,
                "catalog_index_hash": self.catalog_index_hash,
                "sidecar_dataset_hash": self.sidecar_dataset_hash,
                "sidecar_manifest_hash": self.sidecar_manifest_hash,
            },
            "event_boundary_audit": {
                "artifact_sha256": self.event_boundary_audit_sha256,
                "mask_identity": self.event_boundary_mask_identity,
                "partition_identity": self.event_boundary_partition_identity,
            },
            "joint_event_identity": self.joint_event_identity,
            "spec": self.spec.document(),
            "fold": self._fold_document(),
        }

    def _fold_document(self) -> dict[str, object]:
        return {
            "fold_id": self.fold_id,
            "development": _fold_input_segment_document(
                self.development_start_index,
                self.development_end_index,
                self.development_start_session,
                self.development_end_session,
            ),
            "pre_validation_gap": _fold_input_segment_document(
                self.pre_validation_gap_start_index,
                self.pre_validation_gap_end_index,
                self.pre_validation_gap_start_session,
                self.pre_validation_gap_end_session,
            ),
            "validation": _fold_input_segment_document(
                self.validation_start_index,
                self.validation_end_index,
                self.validation_start_session,
                self.validation_end_session,
            ),
            "development_eligible_decision_indices": list(
                self.development_eligible_decision_indices
            ),
            "development_eligible_decision_count": len(
                self.development_eligible_decision_indices
            ),
            "development_eligible_decision_identity": self.development_eligible_decision_identity,
            "validation_eligible_decision_indices": list(
                self.validation_eligible_decision_indices
            ),
            "validation_eligible_decision_count": len(
                self.validation_eligible_decision_indices
            ),
            "validation_eligible_decision_identity": self.validation_eligible_decision_identity,
        }


@dataclass(frozen=True, slots=True)
class KisDailyJointEventFoldInputArtifact:
    path: Path
    content_hash: str
    fold_input: KisDailyJointEventFoldInput
    reattested_against_parent: bool = False


def build_kis_daily_joint_event_window_contract(
    *,
    catalog: KisPaperPrivateDailyCatalog,
    sidecar: KisDailyCorporateActionSnapshot,
    event_boundary_audit: KisDailyEventBoundaryAudit,
    created_at_utc: datetime,
    repo_root: Path,
    spec: KisDailyJointEventWindowSpec = DEFAULT_KIS_DAILY_JOINT_EVENT_WINDOW_SPEC,
    model_execution_review: str = KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_PENDING,
) -> KisDailyJointEventWindowContract:
    """Build a price-free joint mask with no model or broker capability."""

    inputs = _validate_lineage(
        catalog,
        sidecar,
        event_boundary_audit,
        repo_root=repo_root,
    )
    if not isinstance(spec, KisDailyJointEventWindowSpec):
        raise ValueError("joint event-window spec is invalid")
    if model_execution_review not in _MODEL_EXECUTION_REVIEWS:
        raise ValueError("joint event-window model execution review is invalid")
    markers = _joint_event_markers(inputs.events)
    event_indices = {session: index for index, session in enumerate(inputs.sessions)}
    event_index_set = {event_indices[marker.session] for marker in markers}
    folds, final_tail_start = _build_folds(
        sessions=inputs.sessions,
        event_indices=event_index_set,
        spec=spec,
    )
    return KisDailyJointEventWindowContract(
        catalog_dataset_hash=inputs.catalog_dataset_hash,
        catalog_index_hash=inputs.catalog_index_hash,
        sidecar_dataset_hash=inputs.sidecar_dataset_hash,
        sidecar_manifest_hash=inputs.sidecar_manifest_hash,
        event_boundary_audit_sha256=inputs.event_boundary_audit_sha256,
        event_boundary_mask_identity=inputs.event_boundary_mask_identity,
        event_boundary_partition_identity=inputs.event_boundary_partition_identity,
        created_at_utc=created_at_utc,
        sessions=inputs.sessions,
        joint_event_sessions=markers,
        folds=folds,
        final_unused_tail_start_index=final_tail_start,
        spec=spec,
        model_execution_review=model_execution_review,
    )


def write_kis_daily_joint_event_window_contract(
    *,
    destination: Path,
    contract: KisDailyJointEventWindowContract,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path,
) -> KisDailyJointEventWindowContractArtifact:
    """Write one immutable source-safe contract outside Git."""

    if not isinstance(contract, KisDailyJointEventWindowContract):
        raise ValueError("joint event-window contract is invalid")
    path = _external_artifact_destination(
        destination=destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    document = json.dumps(contract.document(), sort_keys=True, separators=(",", ":")) + "\n"
    encoded = document.encode("utf-8")
    content_hash = _sha256(encoded)
    with path.open("xb") as handle:
        handle.write(encoded)
    return KisDailyJointEventWindowContractArtifact(
        path=path,
        content_hash=content_hash,
        contract=contract,
    )


def load_verified_kis_daily_joint_event_window_contract(
    *,
    path: Path,
    expected_artifact_sha256: str,
    expected_contract_identity: str,
    rebuilt_contract: KisDailyJointEventWindowContract,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path,
) -> KisDailyJointEventWindowContractArtifact:
    """Reattest a source-safe artifact against a locally rebuilt contract.

    The immutable parent artifact deliberately omits raw rows and sparse index
    lists. A caller must therefore rebuild the pinned local contract first;
    this function proves that rebuild is exactly the hash-bound parent before a
    single fold can be exposed.
    """

    _require_sha256(expected_artifact_sha256, "joint event-window expected artifact hash")
    _require_sha256(expected_contract_identity, "joint event-window expected contract identity")
    if not isinstance(rebuilt_contract, KisDailyJointEventWindowContract):
        raise ValueError("joint event-window rebuilt contract is invalid")
    if (
        rebuilt_contract.model_execution_review
        != KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE
    ):
        raise ValueError("joint event-window rebuilt contract must remain review_unavailable")
    if rebuilt_contract.contract_identity != expected_contract_identity:
        raise ValueError("joint event-window rebuilt contract identity does not match expected")

    artifact_path = _external_artifact_input_path(
        path=path,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    encoded = artifact_path.read_bytes()
    content_hash = _sha256(encoded)
    if content_hash != expected_artifact_sha256:
        raise ValueError("joint event-window artifact hash does not match expected")
    document = _load_canonical_source_safe_document(encoded)
    expected_document = rebuilt_contract.document()
    if set(document) != set(expected_document):
        raise ValueError("joint event-window artifact schema is incompatible")
    _validate_artifact_created_at(document.get("created_at_utc"))
    for key, expected_value in expected_document.items():
        if key == "created_at_utc":
            continue
        if document.get(key) != expected_value:
            raise ValueError("joint event-window artifact does not match rebuilt contract")
    return KisDailyJointEventWindowContractArtifact(
        path=artifact_path,
        content_hash=content_hash,
        contract=rebuilt_contract,
        reattested_against_rebuild=True,
    )


def select_kis_daily_joint_event_fold_input(
    artifact: KisDailyJointEventWindowContractArtifact,
    *,
    fold_id: str,
) -> KisDailyJointEventFoldInput:
    """Expose one exact expanding fold without creating a generic campaign."""

    if not isinstance(artifact, KisDailyJointEventWindowContractArtifact):
        raise ValueError("joint event-window artifact is invalid")
    if not artifact.reattested_against_rebuild:
        raise ValueError("joint event-window artifact must be reattested before fold selection")
    if not isinstance(fold_id, str) or not fold_id:
        raise ValueError("joint event-window fold input requires exactly one fold id")
    contract = artifact.contract
    if contract.model_execution_review != KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE:
        raise ValueError("joint event-window fold input must remain review_unavailable")
    try:
        fold = next(candidate for candidate in contract.folds if candidate.fold_id == fold_id)
    except StopIteration as error:
        raise ValueError("joint event-window fold id is unknown") from error
    return KisDailyJointEventFoldInput(
        source_artifact_sha256=artifact.content_hash,
        source_contract_identity=contract.contract_identity,
        catalog_dataset_hash=contract.catalog_dataset_hash,
        catalog_index_hash=contract.catalog_index_hash,
        sidecar_dataset_hash=contract.sidecar_dataset_hash,
        sidecar_manifest_hash=contract.sidecar_manifest_hash,
        event_boundary_audit_sha256=contract.event_boundary_audit_sha256,
        event_boundary_mask_identity=contract.event_boundary_mask_identity,
        event_boundary_partition_identity=contract.event_boundary_partition_identity,
        joint_event_identity=contract.joint_event_identity,
        fold_id=fold.fold_id,
        development_start_index=fold.development_start_index,
        development_end_index=fold.development_end_index,
        pre_validation_gap_start_index=fold.pre_validation_gap_start_index,
        pre_validation_gap_end_index=fold.pre_validation_gap_end_index,
        validation_start_index=fold.validation_start_index,
        validation_end_index=fold.validation_end_index,
        development_start_session=contract.sessions[fold.development_start_index],
        development_end_session=contract.sessions[fold.development_end_index - 1],
        pre_validation_gap_start_session=contract.sessions[fold.pre_validation_gap_start_index],
        pre_validation_gap_end_session=contract.sessions[fold.pre_validation_gap_end_index - 1],
        validation_start_session=contract.sessions[fold.validation_start_index],
        validation_end_session=contract.sessions[fold.validation_end_index - 1],
        development_eligible_decision_indices=fold.development_eligible_decision_indices,
        validation_eligible_decision_indices=fold.validation_eligible_decision_indices,
        development_eligible_decision_identity=contract._decision_identity(
            fold.development_eligible_decision_indices
        ),
        validation_eligible_decision_identity=contract._decision_identity(
            fold.validation_eligible_decision_indices
        ),
        spec=contract.spec,
        model_execution_review=contract.model_execution_review,
        reattested_against_parent=True,
    )


def write_kis_daily_joint_event_fold_input(
    *,
    destination: Path,
    fold_input: KisDailyJointEventFoldInput,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path,
) -> KisDailyJointEventFoldInputArtifact:
    """Write one immutable, index-only fold input outside Git."""

    if not isinstance(fold_input, KisDailyJointEventFoldInput):
        raise ValueError("joint event-window fold input is invalid")
    if not fold_input.reattested_against_parent:
        raise ValueError("joint event-window fold input must be reattested before writing")
    path = _external_artifact_destination(
        destination=destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    document = json.dumps(fold_input.document(), sort_keys=True, separators=(",", ":")) + "\n"
    encoded = document.encode("utf-8")
    content_hash = _sha256(encoded)
    with path.open("xb") as handle:
        handle.write(encoded)
    return KisDailyJointEventFoldInputArtifact(
        path=path,
        content_hash=content_hash,
        fold_input=fold_input,
    )


def load_verified_kis_daily_joint_event_fold_input(
    *,
    path: Path,
    expected_artifact_sha256: str,
    expected_fold_input_identity: str,
    expected_fold_input: KisDailyJointEventFoldInput,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path,
) -> KisDailyJointEventFoldInputArtifact:
    """Reattest an index-only fold artifact against its verified parent input."""

    _require_sha256(expected_artifact_sha256, "joint event-window expected fold artifact hash")
    _require_sha256(
        expected_fold_input_identity,
        "joint event-window expected fold input identity",
    )
    if not isinstance(expected_fold_input, KisDailyJointEventFoldInput):
        raise ValueError("joint event-window expected fold input is invalid")
    if not expected_fold_input.reattested_against_parent:
        raise ValueError("joint event-window expected fold input must be reattested")
    if expected_fold_input.fold_input_identity != expected_fold_input_identity:
        raise ValueError("joint event-window expected fold input identity does not match")

    artifact_path = _external_artifact_input_path(
        path=path,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    encoded = artifact_path.read_bytes()
    content_hash = _sha256(encoded)
    if content_hash != expected_artifact_sha256:
        raise ValueError("joint event-window fold artifact hash does not match expected")
    document = _load_canonical_source_safe_document(encoded)
    expected_document = expected_fold_input.document()
    if set(document) != set(expected_document) or document != expected_document:
        raise ValueError("joint event-window fold artifact does not match verified input")
    return KisDailyJointEventFoldInputArtifact(
        path=artifact_path,
        content_hash=content_hash,
        fold_input=expected_fold_input,
        reattested_against_parent=True,
    )


def _validate_lineage(
    catalog: object,
    sidecar: object,
    event_boundary_audit: object,
    *,
    repo_root: Path,
) -> _ValidatedJointEventInputs:
    catalog_dataset_hash = _required_sha_attribute(catalog, "dataset_hash", "catalog")
    catalog_index_hash = _required_sha_attribute(catalog, "index_hash", "catalog")
    sidecar_dataset_hash = _required_sha_attribute(sidecar, "dataset_hash", "sidecar")
    sidecar_manifest_hash = _required_sha_attribute(sidecar, "manifest_hash", "sidecar")
    audit_hash = _required_sha_attribute(event_boundary_audit, "artifact_sha256", "audit")
    audit_mask_identity = _required_sha_attribute(event_boundary_audit, "mask_identity", "audit")
    audit_partition_identity = _required_sha_attribute(
        event_boundary_audit,
        "partition_identity",
        "audit",
    )
    _require_external_input_path(
        _required_path_attribute(catalog, "index_path", "catalog"),
        repo_root=repo_root,
        label="catalog",
    )
    _require_external_input_path(
        _required_path_attribute(sidecar, "snapshot_dir", "sidecar"),
        repo_root=repo_root,
        label="sidecar",
    )
    _require_external_input_path(
        _required_path_attribute(event_boundary_audit, "path", "audit"),
        repo_root=repo_root,
        label="audit",
    )
    bars_by_symbol = _required_mapping_attribute(catalog, "bars_by_symbol", "catalog")
    if set(bars_by_symbol) != set(_JOINT_SYMBOLS):
        raise ValueError("joint event-window requires exact QQQ and SPY catalog streams")
    sidecar_catalog_dataset_hash = _required_sha_attribute(
        sidecar,
        "catalog_dataset_hash",
        "sidecar",
    )
    sidecar_catalog_index_hash = _required_sha_attribute(sidecar, "catalog_index_hash", "sidecar")
    if (
        sidecar_catalog_dataset_hash != catalog_dataset_hash
        or sidecar_catalog_index_hash != catalog_index_hash
    ):
        raise ValueError("joint event-window sidecar lineage is incompatible")
    sessions = _required_sessions_attribute(catalog, "common_sessions", "catalog")
    if (
        len(sessions) < 2
        or tuple(sorted(sessions)) != sessions
        or len(set(sessions)) != len(sessions)
    ):
        raise ValueError("joint event-window sessions are invalid")
    lineage = _required_attribute(event_boundary_audit, "lineage", "audit")
    if (
        _required_sha_attribute(lineage, "catalog_dataset_hash", "audit lineage")
        != catalog_dataset_hash
        or _required_sha_attribute(lineage, "catalog_index_hash", "audit lineage")
        != catalog_index_hash
        or _required_sha_attribute(lineage, "sidecar_dataset_hash", "audit lineage")
        != sidecar_dataset_hash
        or _required_sha_attribute(lineage, "sidecar_manifest_hash", "audit lineage")
        != sidecar_manifest_hash
        or _required_sha_attribute(lineage, "session_dates_sha256", "audit lineage")
        != _session_dates_hash(sessions)
    ):
        raise ValueError("joint event-window audit lineage is incompatible")
    events = _required_events_attribute(sidecar, sessions=sessions)
    return _ValidatedJointEventInputs(
        catalog_dataset_hash=catalog_dataset_hash,
        catalog_index_hash=catalog_index_hash,
        sidecar_dataset_hash=sidecar_dataset_hash,
        sidecar_manifest_hash=sidecar_manifest_hash,
        event_boundary_audit_sha256=audit_hash,
        event_boundary_mask_identity=audit_mask_identity,
        event_boundary_partition_identity=audit_partition_identity,
        sessions=sessions,
        events=events,
    )


def _joint_event_markers(
    events: tuple[object, ...],
) -> tuple[KisDailyJointEventSession, ...]:
    sources_by_session: dict[date, set[tuple[str, str]]] = {}
    for event in events:
        session = _required_date_attribute(event, "mapped_kis_session_date", "sidecar event")
        symbol = _required_text_attribute(event, "symbol", "sidecar event")
        event_kind = _required_text_attribute(event, "event_kind", "sidecar event")
        sources_by_session.setdefault(session, set()).add(
            (symbol, event_kind)
        )
    markers = tuple(
        KisDailyJointEventSession(session=session, sources=tuple(sorted(sources)))
        for session, sources in sorted(sources_by_session.items())
    )
    if not markers:
        raise ValueError("joint event-window sidecar has no event sessions")
    return markers


def _build_folds(
    *,
    sessions: tuple[date, ...],
    event_indices: set[int],
    spec: KisDailyJointEventWindowSpec,
) -> tuple[tuple[KisDailyJointEventWindowFold, ...], int]:
    required_sessions = spec.initial_development_session_count + spec.fold_count * (
        spec.pre_validation_gap_session_count + spec.validation_session_count
    )
    if required_sessions >= len(sessions):
        raise ValueError("joint event-window leaves no final unused tail")
    cursor = spec.initial_development_session_count
    folds: list[KisDailyJointEventWindowFold] = []
    for ordinal in range(1, spec.fold_count + 1):
        purge_start = cursor
        purge_end = purge_start + spec.pre_validation_gap_session_count
        validation_start = purge_end
        validation_end = validation_start + spec.validation_session_count
        development_eligible = _eligible_decisions(
            phase_start=0,
            phase_end=cursor,
            event_indices=event_indices,
            spec=spec,
        )
        validation_eligible = _eligible_decisions(
            phase_start=validation_start,
            phase_end=validation_end,
            event_indices=event_indices,
            spec=spec,
        )
        if (
            len(development_eligible) < spec.minimum_eligible_decision_count
            or len(validation_eligible) < spec.minimum_eligible_decision_count
        ):
            raise ValueError("joint event-window leaves too few eligible decisions")
        folds.append(
            KisDailyJointEventWindowFold(
                fold_id=f"expanding-{ordinal}",
                development_start_index=0,
                development_end_index=cursor,
                pre_validation_gap_start_index=purge_start,
                pre_validation_gap_end_index=purge_end,
                validation_start_index=validation_start,
                validation_end_index=validation_end,
                development_eligible_decision_indices=development_eligible,
                validation_eligible_decision_indices=validation_eligible,
            )
        )
        cursor = validation_end
    return tuple(folds), cursor


def _eligible_decisions(
    *,
    phase_start: int,
    phase_end: int,
    event_indices: set[int],
    spec: KisDailyJointEventWindowSpec,
) -> tuple[int, ...]:
    # The first 20-row return feature depends on one preceding completed close.
    first_decision = (
        phase_start + spec.feature_session_count + spec.feature_return_prior_session_count - 1
    )
    final_exclusive = phase_end - spec.label_horizon_session_count
    return tuple(
        decision_index
        for decision_index in range(first_decision, final_exclusive)
        if not any(
            index in event_indices
            for index in range(
                decision_index
                - spec.feature_session_count
                - spec.feature_return_prior_session_count
                + 1,
                decision_index + spec.label_horizon_session_count + 1,
            )
        )
    )


def _external_artifact_destination(
    *,
    destination: Path,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    resolved_repo = Path(repo_root).resolve()
    resolved_root = Path(artifact_root).resolve()
    if (
        resolved_root == resolved_repo or resolved_root.is_relative_to(resolved_repo)
    ) and not is_container_external_mount(resolved_root, resolved_repo):
        raise ValueError("joint event-window artifacts must stay outside the Git workspace")
    destination_path = Path(destination)
    if destination_path.is_symlink():
        raise ValueError("joint event-window artifact destination is invalid")
    resolved_destination = destination_path.resolve()
    if not resolved_destination.is_relative_to(resolved_root):
        raise ValueError("joint event-window artifact must stay under the artifact root")
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    if not resolved_destination.parent.resolve().is_relative_to(resolved_root):
        raise ValueError("joint event-window artifact destination is invalid")
    return resolved_destination


def _external_artifact_input_path(
    *,
    path: Path,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    resolved_repo = Path(repo_root).resolve()
    resolved_root = Path(artifact_root).resolve()
    if (
        resolved_root == resolved_repo or resolved_root.is_relative_to(resolved_repo)
    ) and not is_container_external_mount(resolved_root, resolved_repo):
        raise ValueError("joint event-window artifacts must stay outside the Git workspace")
    artifact_path = Path(path)
    if artifact_path.is_symlink():
        raise ValueError("joint event-window artifact input is invalid")
    try:
        resolved_path = artifact_path.resolve(strict=True)
    except OSError as error:
        raise ValueError("joint event-window artifact input is unavailable") from error
    if not resolved_path.is_file() or not resolved_path.is_relative_to(resolved_root):
        raise ValueError("joint event-window artifact input must stay under the artifact root")
    return resolved_path


def _load_canonical_source_safe_document(encoded: bytes) -> dict[str, object]:
    try:
        decoded = encoded.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("joint event-window artifact document is invalid") from error
    if not isinstance(value, dict):
        raise ValueError("joint event-window artifact document is invalid")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    if encoded != canonical.encode("utf-8"):
        raise ValueError("joint event-window artifact document is not canonical")
    _assert_source_safe(value)
    return value


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, nested in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = nested
    return value


def _validate_artifact_created_at(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("joint event-window artifact created_at_utc is invalid")
    try:
        created_at_utc = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("joint event-window artifact created_at_utc is invalid") from error
    _require_utc(created_at_utc)


def _validate_fold_input_geometry(fold_input: KisDailyJointEventFoldInput) -> None:
    indices = (
        fold_input.development_start_index,
        fold_input.development_end_index,
        fold_input.pre_validation_gap_start_index,
        fold_input.pre_validation_gap_end_index,
        fold_input.validation_start_index,
        fold_input.validation_end_index,
    )
    if any(type(index) is not int or index < 0 for index in indices):
        raise ValueError("joint event-window fold input indices are invalid")
    if (
        fold_input.development_start_index != 0
        or fold_input.development_end_index != fold_input.pre_validation_gap_start_index
        or fold_input.pre_validation_gap_end_index != fold_input.validation_start_index
        or fold_input.validation_end_index <= fold_input.validation_start_index
    ):
        raise ValueError("joint event-window fold input geometry is invalid")
    if (
        fold_input.pre_validation_gap_end_index - fold_input.pre_validation_gap_start_index
        != fold_input.spec.pre_validation_gap_session_count
    ):
        raise ValueError("joint event-window fold input gap is invalid")
    if (
        fold_input.validation_end_index - fold_input.validation_start_index
        != fold_input.spec.validation_session_count
    ):
        raise ValueError("joint event-window fold input validation size is invalid")
    sessions = (
        fold_input.development_start_session,
        fold_input.development_end_session,
        fold_input.pre_validation_gap_start_session,
        fold_input.pre_validation_gap_end_session,
        fold_input.validation_start_session,
        fold_input.validation_end_session,
    )
    if (
        any(type(session) is not date for session in sessions)
        or tuple(sorted(sessions)) != sessions
    ):
        raise ValueError("joint event-window fold input sessions are invalid")
    object.__setattr__(
        fold_input,
        "development_eligible_decision_indices",
        tuple(fold_input.development_eligible_decision_indices),
    )
    object.__setattr__(
        fold_input,
        "validation_eligible_decision_indices",
        tuple(fold_input.validation_eligible_decision_indices),
    )
    _validate_fold_input_eligible_indices(
        fold_input.development_eligible_decision_indices,
        phase_start=fold_input.development_start_index,
        phase_end=fold_input.development_end_index,
        spec=fold_input.spec,
    )
    _validate_fold_input_eligible_indices(
        fold_input.validation_eligible_decision_indices,
        phase_start=fold_input.validation_start_index,
        phase_end=fold_input.validation_end_index,
        spec=fold_input.spec,
    )


def _validate_fold_input_eligible_indices(
    indices: tuple[int, ...],
    *,
    phase_start: int,
    phase_end: int,
    spec: KisDailyJointEventWindowSpec,
) -> None:
    if tuple(sorted(indices)) != indices or len(set(indices)) != len(indices):
        raise ValueError("joint event-window fold input eligibility is invalid")
    if len(indices) < spec.minimum_eligible_decision_count:
        raise ValueError("joint event-window fold input leaves too few eligible decisions")
    first_decision = (
        phase_start + spec.feature_session_count + spec.feature_return_prior_session_count - 1
    )
    final_decision = phase_end - spec.label_horizon_session_count - 1
    if any(
        type(index) is not int or index < first_decision or index > final_decision
        for index in indices
    ):
        raise ValueError("joint event-window fold input eligibility crosses its phase")


def _fold_input_segment_document(
    start_index: int,
    end_index: int,
    start_session: date,
    end_session: date,
) -> dict[str, object]:
    return {
        "start_index": start_index,
        "end_index_exclusive": end_index,
        "start_session": start_session.isoformat(),
        "end_session": end_session.isoformat(),
        "session_count": end_index - start_index,
    }


def _require_external_input_path(path: Path, *, repo_root: Path, label: str) -> None:
    resolved_path = Path(path).resolve()
    resolved_repo = Path(repo_root).resolve()
    if (
        resolved_path == resolved_repo or resolved_path.is_relative_to(resolved_repo)
    ) and not is_container_external_mount(resolved_path, resolved_repo):
        raise ValueError(f"joint event-window {label} input must stay outside the Git workspace")


def is_container_external_mount(path: Path, repo_root: Path) -> bool:
    """Recognize the two Docker bind-mount destinations as external storage."""

    container_repo = Path("/app").resolve()
    if repo_root != container_repo:
        return False
    return any(
        path == container_repo / name or path.is_relative_to(container_repo / name)
        for name in ("market_data", "model_artifacts")
    )


def _required_attribute(source: object, attribute: str, label: str) -> object:
    try:
        return getattr(source, attribute)
    except AttributeError as error:
        raise ValueError(f"joint event-window {label} is invalid") from error


def _required_sha_attribute(source: object, attribute: str, label: str) -> str:
    value = _required_attribute(source, attribute, label)
    _require_sha256(value, f"joint event-window {label} {attribute}")
    return value


def _required_path_attribute(source: object, attribute: str, label: str) -> Path:
    value = _required_attribute(source, attribute, label)
    if not isinstance(value, Path):
        raise ValueError(f"joint event-window {label} {attribute} is invalid")
    return value


def _required_mapping_attribute(
    source: object,
    attribute: str,
    label: str,
) -> Mapping[object, object]:
    value = _required_attribute(source, attribute, label)
    if not isinstance(value, Mapping):
        raise ValueError(f"joint event-window {label} {attribute} is invalid")
    return value


def _required_sessions_attribute(source: object, attribute: str, label: str) -> tuple[date, ...]:
    value = _required_attribute(source, attribute, label)
    if not isinstance(value, tuple) or any(type(session) is not date for session in value):
        raise ValueError(f"joint event-window {label} {attribute} is invalid")
    return value


def _required_events_attribute(
    sidecar: object,
    *,
    sessions: tuple[date, ...],
) -> tuple[object, ...]:
    value = _required_attribute(sidecar, "events", "sidecar")
    if not isinstance(value, tuple) or not value:
        raise ValueError("joint event-window sidecar events are invalid")
    session_set = set(sessions)
    for event in value:
        session = _required_date_attribute(event, "mapped_kis_session_date", "sidecar event")
        symbol = _required_text_attribute(event, "symbol", "sidecar event")
        event_kind = _required_text_attribute(event, "event_kind", "sidecar event")
        if (
            symbol not in _JOINT_SYMBOLS
            or event_kind not in _JOINT_EVENT_KINDS
            or session not in session_set
        ):
            raise ValueError("joint event-window sidecar event is incompatible")
    return value


def _required_date_attribute(source: object, attribute: str, label: str) -> date:
    value = _required_attribute(source, attribute, label)
    if type(value) is not date:
        raise ValueError(f"joint event-window {label} {attribute} is invalid")
    return value


def _required_text_attribute(source: object, attribute: str, label: str) -> str:
    value = _required_attribute(source, attribute, label)
    if not isinstance(value, str) or not value:
        raise ValueError(f"joint event-window {label} {attribute} is invalid")
    return value


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if normalized in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"joint event-window artifact may not contain {key}")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)


def _require_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("joint event-window created_at_utc must be UTC-aware")
    return value.astimezone(UTC)


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use the sha256 prefix")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise ValueError(f"{field_name} must contain a SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as error:
        raise ValueError(f"{field_name} must contain a SHA-256 digest") from error


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _session_dates_hash(sessions: tuple[date, ...]) -> str:
    ordered = tuple(sorted(sessions))
    if not ordered or any(type(session) is not date for session in ordered):
        raise ValueError("joint event-window sessions are invalid")
    return _sha256("\n".join(session.isoformat() for session in ordered).encode("utf-8"))

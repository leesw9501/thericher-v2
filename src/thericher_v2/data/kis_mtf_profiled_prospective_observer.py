"""Source-safe forward witness for frozen KIS multi-timeframe profile inputs."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data.kis_intraday_mtf_availability import (
    KIS_INTRADAY_MTF_AVAILABILITY_TARGETS,
    KisIntradayMtfAvailabilityReceipt,
    freeze_kis_intraday_mtf_availability_contract,
    materialize_kis_intraday_mtf_availability,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.models.sequence_window import SequenceWindowInputError
from thericher_v2.research.artifact_paths import (
    ensure_external_artifact_directory,
    reject_repo_artifact_path,
)
from thericher_v2.research.causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from thericher_v2.research.kis_mtf_profiled_feature_input_preflight import (
    KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256,
    build_target_free_mtf_feature_pair,
    build_target_free_mtf_feature_projection,
    completed_causal_minute_prefix,
    resample_completed_causal_prefix,
)

KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID = "kis-mtf-profiled-prospective-observer-v1"
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ARTIFACT_DIRECTORY = (
    "mtf-prospective-v1"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SUMMARY_SHA256 = (
    "sha256:ad00069df6c3da2874eca7070c08c07126b56699db0c4cec91a2f30718a8168e"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_PRECOMMIT_SHA256 = (
    "sha256:25e8ac3aa820ec6c33eb70427765c36c7c05c6cd67140e5f4408415f0b510c4c"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_CONTRACT_SHA256 = (
    "sha256:25ed7202b60b2ac992e46aaca8d423875fee06f54a14e53bbf0fd8ad6280adbb"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CODE_REVISION = (
    "sha256:c85ecd2c9937f0e124d9ae39a8d40e496492b585557fd3ba8d6b1a3ce548c9f6"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CONTRACT_SHA256 = (
    "sha256:5b8cf474be34f4e4bbfb0710584bf540374daa747b7b2acf2a1ec25443aad4a1"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_RECEIPT_SHA256 = (
    "sha256:e88ded3c41960837472f5abdf195af44f35b04cbc5449e7e805a95f714143584"
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_HISTORICAL_SESSION_COUNT = 21
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_CUTOFF = time(15, 30)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_INTRADAY_MTF_AVAILABILITY_TARGETS
)
KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS = tuple(
    profile.profile_id for profile in CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profiles
)
KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID = "kis-mtf-profiled-forward-outcome-witness-v1"
KIS_MTF_PROFILED_FORWARD_OUTCOME_RAW_SNAPSHOT_ID = (
    "kis-mtf-profiled-forward-outcome-raw-snapshot-v1"
)
KIS_MTF_PROFILED_FORWARD_OUTCOME_ARTIFACT_DIRECTORY = "mtf-forward-outcomes-v1"
KIS_MTF_PROFILED_FORWARD_OUTCOME_RAW_DIRECTORY = "forward-outcome-witness-v1"
KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID = "short"
KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT = 15

ObservationStatus = Literal["observed", "input_unavailable"]
StoreOutcome = Literal["appended", "duplicate", "conflict", "busy"]
ForwardOutcomeStatus = Literal[
    "target_ready",
    "input_unavailable",
    "outcome_unavailable",
    "input_mutated",
]
ForwardOutcomeStoreOutcome = Literal[
    "appended",
    "duplicate",
    "conflict",
    "input_unavailable",
    "outcome_unavailable",
    "input_mutated",
    "busy",
]
CatalogLoader = Callable[..., Mapping[str, CatalogedBars]]
_EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class KisMtfProfiledProspectiveObserverContract:
    """Frozen historical exclusion and feature-input provenance, kept value-free."""

    historical_source_contract_sha256: str
    historical_receipt_sha256: str
    preflight_summary_sha256: str
    catalog_sha256: str
    historical_session_count: int
    historical_exclusion_sha256: str
    code_revision: str
    contract_sha256: str
    _historical_session_dates: tuple[date, ...] = field(repr=False)

    def __post_init__(self) -> None:
        dates = tuple(self._historical_session_dates)
        object.__setattr__(self, "_historical_session_dates", dates)
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.historical_source_contract_sha256,
                    self.historical_receipt_sha256,
                    self.preflight_summary_sha256,
                    self.historical_exclusion_sha256,
                    self.code_revision,
                    self.contract_sha256,
                )
            )
            or self.preflight_summary_sha256
            != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SUMMARY_SHA256
            or self.catalog_sha256 != KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256
            or self.historical_session_count
            != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_HISTORICAL_SESSION_COUNT
            or len(dates) != self.historical_session_count
            or tuple(sorted(dates)) != dates
            or len(set(dates)) != len(dates)
            or self.historical_exclusion_sha256 != _historical_exclusion_sha256(dates)
        ):
            raise ValueError("prospective observer contract is invalid")
        expected = _contract_sha256(
            historical_source_contract_sha256=self.historical_source_contract_sha256,
            historical_receipt_sha256=self.historical_receipt_sha256,
            preflight_summary_sha256=self.preflight_summary_sha256,
            catalog_sha256=self.catalog_sha256,
            historical_session_count=self.historical_session_count,
            historical_exclusion_sha256=self.historical_exclusion_sha256,
            code_revision=self.code_revision,
        )
        if self.contract_sha256 != expected:
            raise ValueError("prospective observer contract hash is invalid")

    @property
    def historical_session_dates(self) -> frozenset[date]:
        """Expose dates only to the in-memory forward-exclusion check."""

        return frozenset(self._historical_session_dates)

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID,
            "contract_sha256": self.contract_sha256,
            "historical_source_contract_sha256": self.historical_source_contract_sha256,
            "historical_receipt_sha256": self.historical_receipt_sha256,
            "preflight_summary_sha256": self.preflight_summary_sha256,
            "catalog_sha256": self.catalog_sha256,
            "historical_session_count": self.historical_session_count,
            "historical_exclusion_sha256": self.historical_exclusion_sha256,
            "code_revision": self.code_revision,
            "geometry": {
                "cutoff": "15:30:00",
                "completed_constituents_required": True,
                "historical_sessions_count_as_forward": False,
            },
            "scope": _source_safe_scope(),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledProspectiveProfileCommitment:
    """One profile's opaque pair commitment, without features or timestamps."""

    profile_id: str
    status: ObservationStatus
    pair_input_sha256: str | None

    def __post_init__(self) -> None:
        if (
            self.profile_id not in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS
            or self.status not in {"observed", "input_unavailable"}
            or (self.status == "observed") != (self.pair_input_sha256 is not None)
            or (self.pair_input_sha256 is not None and not _is_sha256(self.pair_input_sha256))
        ):
            raise ValueError("prospective profile commitment is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "status": self.status,
            "pair_input_sha256": self.pair_input_sha256,
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledProspectiveObservation:
    """One eligible forward-session result with no raw time or market values."""

    contract_sha256: str
    session_key_sha256: str
    head_source_contract_sha256: str | None
    status: ObservationStatus
    profiles: tuple[KisMtfProfiledProspectiveProfileCommitment, ...]
    content_commitment_sha256: str
    observation_sha256: str
    _session_date: date = field(repr=False)

    def __post_init__(self) -> None:
        profiles = tuple(self.profiles)
        object.__setattr__(self, "profiles", profiles)
        if (
            not _is_sha256(self.contract_sha256)
            or not _is_sha256(self.session_key_sha256)
            or not _is_sha256(self.content_commitment_sha256)
            or not _is_sha256(self.observation_sha256)
            or (
                self.head_source_contract_sha256 is not None
                and not _is_sha256(self.head_source_contract_sha256)
            )
            or tuple(profile.profile_id for profile in profiles)
            != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS
            or self.status != _status_for_profiles(profiles)
            or (
                self.status == "observed"
                and self.head_source_contract_sha256 is None
            )
            or self.session_key_sha256
            != _session_key_sha256(
                contract_sha256=self.contract_sha256,
                session_date=self._session_date,
            )
        ):
            raise ValueError("prospective observation is invalid")
        expected_content = _content_commitment_sha256(
            contract_sha256=self.contract_sha256,
            session_key_sha256=self.session_key_sha256,
            head_source_contract_sha256=self.head_source_contract_sha256,
            status=self.status,
            profiles=profiles,
        )
        if self.content_commitment_sha256 != expected_content:
            raise ValueError("prospective observation content commitment is invalid")
        expected_observation = _observation_sha256(
            contract_sha256=self.contract_sha256,
            session_key_sha256=self.session_key_sha256,
            head_source_contract_sha256=self.head_source_contract_sha256,
            status=self.status,
            profiles=profiles,
            content_commitment_sha256=self.content_commitment_sha256,
        )
        if self.observation_sha256 != expected_observation:
            raise ValueError("prospective observation hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID,
            "contract_sha256": self.contract_sha256,
            "session_key_sha256": self.session_key_sha256,
            "head_source_contract_sha256": self.head_source_contract_sha256,
            "status": self.status,
            "profile_aggregates": [profile.safe_payload() for profile in self.profiles],
            "content_commitment_sha256": self.content_commitment_sha256,
            "observation_sha256": self.observation_sha256,
            "scope": _source_safe_scope(),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledProspectiveStoreResult:
    """Outcome of an immutable forward-observation reconciliation."""

    outcome: StoreOutcome
    observation: KisMtfProfiledProspectiveObservation
    conflict_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            self.outcome not in {"appended", "duplicate", "conflict", "busy"}
            or (self.outcome == "conflict") != (self.conflict_sha256 is not None)
            or (self.conflict_sha256 is not None and not _is_sha256(self.conflict_sha256))
        ):
            raise ValueError("prospective observer store result is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID,
            "status": self.observation.status if self.outcome == "appended" else self.outcome,
            "store_outcome": self.outcome,
            "observation": self.observation.safe_payload(),
        }
        if self.conflict_sha256 is not None:
            payload["conflict_sha256"] = self.conflict_sha256
        return payload


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeContract:
    """One fixed post-cutoff window bound to the existing input observer contract."""

    observer_contract_sha256: str
    profile_id: str
    outcome_bar_count: int
    contract_sha256: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.observer_contract_sha256)
            or self.profile_id != KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID
            or self.outcome_bar_count != KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT
            or not _is_sha256(self.contract_sha256)
            or self.contract_sha256
            != _forward_outcome_contract_sha256(
                observer_contract_sha256=self.observer_contract_sha256,
                profile_id=self.profile_id,
                outcome_bar_count=self.outcome_bar_count,
            )
        ):
            raise ValueError("forward outcome contract is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
            "observer_contract_sha256": self.observer_contract_sha256,
            "profile_id": self.profile_id,
            "outcome_geometry": {
                "timeframe": Timeframe.M1.value,
                "post_cutoff_bar_count": self.outcome_bar_count,
            },
            "contract_sha256": self.contract_sha256,
            "scope": _forward_outcome_scope(raw_snapshot_retained=False),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeLegCommitment:
    """One opaque post-cutoff leg commitment in the fixed QQQ/SPY order."""

    leg_index: int
    status: Literal["available", "unavailable"]
    content_commitment_sha256: str | None

    def __post_init__(self) -> None:
        if (
            self.leg_index not in range(len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS))
            or self.status not in {"available", "unavailable"}
            or (self.status == "available") != (self.content_commitment_sha256 is not None)
            or (
                self.content_commitment_sha256 is not None
                and not _is_sha256(self.content_commitment_sha256)
            )
        ):
            raise ValueError("forward outcome leg commitment is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "leg_index": self.leg_index,
            "status": self.status,
            "content_commitment_sha256": self.content_commitment_sha256,
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeWitness:
    """A source-safe target-ready fact with no outcome values or labels."""

    contract_sha256: str
    session_key_sha256: str
    input_observation_sha256: str | None
    status: ForwardOutcomeStatus
    legs: tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...]
    raw_snapshot_sha256: str | None
    content_commitment_sha256: str
    witness_sha256: str

    def __post_init__(self) -> None:
        legs = tuple(self.legs)
        object.__setattr__(self, "legs", legs)
        target_ready = self.status == "target_ready"
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.contract_sha256,
                    self.session_key_sha256,
                    self.content_commitment_sha256,
                    self.witness_sha256,
                )
            )
            or (
                self.input_observation_sha256 is not None
                and not _is_sha256(self.input_observation_sha256)
            )
            or (self.raw_snapshot_sha256 is not None and not _is_sha256(self.raw_snapshot_sha256))
            or tuple(leg.leg_index for leg in legs)
            != tuple(range(len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS)))
            or self.status
            not in {
                "target_ready",
                "input_unavailable",
                "outcome_unavailable",
                "input_mutated",
            }
            or target_ready
            != (
                self.input_observation_sha256 is not None
                and self.raw_snapshot_sha256 is not None
                and all(leg.status == "available" for leg in legs)
            )
            or (
                self.status == "input_unavailable"
                and self.input_observation_sha256 is not None
            )
            or (
                self.status == "input_unavailable"
                and any(leg.status != "unavailable" for leg in legs)
            )
            or (
                self.status != "target_ready"
                and self.raw_snapshot_sha256 is not None
            )
        ):
            raise ValueError("forward outcome witness is invalid")
        expected_content = _forward_outcome_content_commitment_sha256(
            contract_sha256=self.contract_sha256,
            session_key_sha256=self.session_key_sha256,
            input_observation_sha256=self.input_observation_sha256,
            status=self.status,
            legs=legs,
            raw_snapshot_sha256=self.raw_snapshot_sha256,
        )
        if self.content_commitment_sha256 != expected_content:
            raise ValueError("forward outcome witness content commitment is invalid")
        if self.witness_sha256 != _forward_outcome_witness_sha256(
            contract_sha256=self.contract_sha256,
            session_key_sha256=self.session_key_sha256,
            input_observation_sha256=self.input_observation_sha256,
            status=self.status,
            legs=legs,
            raw_snapshot_sha256=self.raw_snapshot_sha256,
            content_commitment_sha256=self.content_commitment_sha256,
        ):
            raise ValueError("forward outcome witness hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
            "contract_sha256": self.contract_sha256,
            "session_key_sha256": self.session_key_sha256,
            "input_observation_sha256": self.input_observation_sha256,
            "status": self.status,
            "outcome_geometry": {
                "timeframe": Timeframe.M1.value,
                "post_cutoff_bar_count": KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT,
            },
            "legs": [leg.safe_payload() for leg in self.legs],
            "raw_snapshot_sha256": self.raw_snapshot_sha256,
            "content_commitment_sha256": self.content_commitment_sha256,
            "witness_sha256": self.witness_sha256,
            "scope": _forward_outcome_scope(
                raw_snapshot_retained=self.raw_snapshot_sha256 is not None
            ),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeMaterialization:
    """One in-memory witness and its D:-only raw snapshot candidate."""

    witness: KisMtfProfiledForwardOutcomeWitness
    raw_snapshot_payload: Mapping[str, object] | None = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.witness.status == "target_ready"
        ) != (self.raw_snapshot_payload is not None):
            raise ValueError("forward outcome raw snapshot materialization is invalid")


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeStoreResult:
    """One idempotent outcome-store result or a retryable source fact."""

    outcome: ForwardOutcomeStoreOutcome
    witness: KisMtfProfiledForwardOutcomeWitness
    conflict_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            self.outcome
            not in {
                "appended",
                "duplicate",
                "conflict",
                "input_unavailable",
                "outcome_unavailable",
                "input_mutated",
                "busy",
            }
            or (self.outcome == "conflict") != (self.conflict_sha256 is not None)
            or (self.conflict_sha256 is not None and not _is_sha256(self.conflict_sha256))
            or (
                self.outcome in {"input_unavailable", "outcome_unavailable", "input_mutated"}
                and self.witness.status != self.outcome
            )
            or (
                self.outcome in {"appended", "duplicate", "conflict"}
                and self.witness.status != "target_ready"
            )
        ):
            raise ValueError("forward outcome store result is invalid")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
            "status": self.outcome,
            "witness": self.witness.safe_payload(),
        }
        if self.conflict_sha256 is not None:
            payload["conflict_sha256"] = self.conflict_sha256
        return payload


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeInventory:
    """An Engine-safe count over replayable target-ready paired witnesses."""

    contract_sha256: str
    target_ready_pair_count: int
    target_ready_manifest_sha256: str
    status: Literal["zero_target_ready", "target_ready"]

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.contract_sha256)
            or type(self.target_ready_pair_count) is not int
            or self.target_ready_pair_count < 0
            or not _is_sha256(self.target_ready_manifest_sha256)
            or self.status not in {"zero_target_ready", "target_ready"}
            or (self.target_ready_pair_count > 0) != (self.status == "target_ready")
        ):
            raise ValueError("forward outcome inventory is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
            "contract_sha256": self.contract_sha256,
            "target_ready_pair_count": self.target_ready_pair_count,
            "target_ready_manifest_sha256": self.target_ready_manifest_sha256,
            "status": self.status,
            "scope": _forward_outcome_scope(
                raw_snapshot_retained=self.target_ready_pair_count > 0
            ),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeSnapshot:
    """One verified value-bearing raw snapshot retained only under market data."""

    contract_sha256: str
    session_key_sha256: str
    input_observation_sha256: str
    witness_sha256: str
    raw_snapshot_sha256: str
    input_prefixes: tuple[tuple[Bar, ...], ...] = field(repr=False)
    outcome_windows: tuple[tuple[Bar, ...], ...] = field(repr=False)

    def __post_init__(self) -> None:
        input_prefixes = tuple(tuple(bars) for bars in self.input_prefixes)
        outcome_windows = tuple(tuple(bars) for bars in self.outcome_windows)
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.contract_sha256,
                    self.session_key_sha256,
                    self.input_observation_sha256,
                    self.witness_sha256,
                    self.raw_snapshot_sha256,
                )
            )
            or len(input_prefixes) != len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS)
            or len(outcome_windows) != len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS)
        ):
            raise ValueError("forward outcome snapshot identity is invalid")
        for target_key, inputs, outcomes in zip(
            KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS,
            input_prefixes,
            outcome_windows,
            strict=True,
        ):
            if not inputs or len(outcomes) != KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT:
                raise ValueError("forward outcome snapshot geometry is invalid")
            _validate_forward_snapshot_sequence(inputs, target_key=target_key)
            _validate_forward_snapshot_sequence(outcomes, target_key=target_key)
            if inputs[-1].start_ts + Timeframe.M1.duration != outcomes[0].start_ts:
                raise ValueError("forward outcome snapshot target boundary is invalid")
            input_end = (inputs[-1].start_ts + Timeframe.M1.duration).astimezone(_EASTERN)
            outcome_end = (outcomes[-1].start_ts + Timeframe.M1.duration).astimezone(_EASTERN)
            if (
                input_end.date() != outcome_end.date()
                or input_end.time().replace(tzinfo=None)
                != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_CUTOFF
                or outcome_end.time().replace(tzinfo=None) != time(15, 45)
            ):
                raise ValueError("forward outcome snapshot target timing is invalid")
        outcome_ends = {
            outcomes[-1].start_ts + Timeframe.M1.duration for outcomes in outcome_windows
        }
        if len(outcome_ends) != 1:
            raise ValueError("forward outcome snapshot legs have different outcome ends")
        object.__setattr__(self, "input_prefixes", input_prefixes)
        object.__setattr__(self, "outcome_windows", outcome_windows)

    @property
    def outcome_end(self) -> datetime:
        return self.outcome_windows[0][-1].start_ts + Timeframe.M1.duration


@dataclass(frozen=True, slots=True)
class KisMtfProfiledForwardOutcomeSnapshotCatalog:
    """A read-only chronological catalog of value-bearing target-ready snapshots."""

    contract: KisMtfProfiledForwardOutcomeContract
    inventory: KisMtfProfiledForwardOutcomeInventory
    snapshots: tuple[KisMtfProfiledForwardOutcomeSnapshot, ...] = field(repr=False)

    def __post_init__(self) -> None:
        snapshots = tuple(self.snapshots)
        if (
            self.inventory.contract_sha256 != self.contract.contract_sha256
            or len(snapshots) != self.inventory.target_ready_pair_count
            or any(
                snapshot.contract_sha256 != self.contract.contract_sha256
                for snapshot in snapshots
            )
            or tuple(
                (snapshot.outcome_end, snapshot.session_key_sha256) for snapshot in snapshots
            )
            != tuple(
                sorted(
                    (snapshot.outcome_end, snapshot.session_key_sha256)
                    for snapshot in snapshots
                )
            )
            or len({snapshot.session_key_sha256 for snapshot in snapshots}) != len(snapshots)
        ):
            raise ValueError("forward outcome snapshot catalog is invalid")
        object.__setattr__(self, "snapshots", snapshots)


def freeze_kis_mtf_profiled_prospective_observer_contract(
    *,
    historical_catalogs: Mapping[str, CatalogedBars],
    code_revision: str,
    preflight_summary_sha256: str | None = None,
) -> KisMtfProfiledProspectiveObserverContract:
    """Reattest the completed historical baseline before a forward observation."""

    _require_sha256(code_revision, "code_revision")
    if preflight_summary_sha256 is None:
        preflight_summary_sha256 = KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SUMMARY_SHA256
    if preflight_summary_sha256 != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SUMMARY_SHA256:
        raise ValueError("prospective observer preflight summary is not the frozen input")
    historical_source_contract = freeze_kis_intraday_mtf_availability_contract(
        historical_catalogs,
        code_revision=KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CODE_REVISION,
    )
    historical_receipt = materialize_kis_intraday_mtf_availability(
        historical_source_contract,
        historical_catalogs,
    )
    dates = _common_eligible_session_dates(historical_receipt)
    if (
        historical_source_contract.contract_sha256
        != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_CONTRACT_SHA256
        or historical_receipt.receipt_sha256
        != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PREFLIGHT_SOURCE_RECEIPT_SHA256
        or len(dates) != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_HISTORICAL_SESSION_COUNT
    ):
        raise ValueError("prospective observer historical scope is not the frozen completed cache")
    exclusion_sha256 = _historical_exclusion_sha256(dates)
    fields = {
        "historical_source_contract_sha256": historical_source_contract.contract_sha256,
        "historical_receipt_sha256": historical_receipt.receipt_sha256,
        "preflight_summary_sha256": preflight_summary_sha256,
        "catalog_sha256": KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256,
        "historical_session_count": len(dates),
        "historical_exclusion_sha256": exclusion_sha256,
        "code_revision": code_revision,
    }
    return KisMtfProfiledProspectiveObserverContract(
        **fields,
        contract_sha256=_contract_sha256(**fields),
        _historical_session_dates=dates,
    )


def materialize_kis_mtf_profiled_prospective_observation(
    contract: KisMtfProfiledProspectiveObserverContract,
    *,
    historical_catalogs: Mapping[str, CatalogedBars],
    head_catalogs: Mapping[str, CatalogedBars | None],
    observed_at: datetime,
) -> KisMtfProfiledProspectiveObservation | None:
    """Build one all-profile forward witness entirely from verified local catalogs."""

    window = _prospective_observation_window(observed_at)
    if window is None:
        return None
    session_date, session, cutoff = window
    if session_date in contract.historical_session_dates:
        return None
    reattested = freeze_kis_mtf_profiled_prospective_observer_contract(
        historical_catalogs=historical_catalogs,
        code_revision=contract.code_revision,
        preflight_summary_sha256=contract.preflight_summary_sha256,
    )
    if reattested != contract:
        raise ValueError("prospective observer historical input changed")
    session_key_sha256 = _session_key_sha256(
        contract_sha256=contract.contract_sha256,
        session_date=session_date,
    )
    profiles, head_source_contract_sha256 = _profile_commitments(
        head_catalogs=head_catalogs,
        code_revision=contract.code_revision,
        session=session,
        cutoff=cutoff,
    )
    status = _status_for_profiles(profiles)
    content_commitment_sha256 = _content_commitment_sha256(
        contract_sha256=contract.contract_sha256,
        session_key_sha256=session_key_sha256,
        head_source_contract_sha256=head_source_contract_sha256,
        status=status,
        profiles=profiles,
    )
    return KisMtfProfiledProspectiveObservation(
        contract_sha256=contract.contract_sha256,
        session_key_sha256=session_key_sha256,
        head_source_contract_sha256=head_source_contract_sha256,
        status=status,
        profiles=profiles,
        content_commitment_sha256=content_commitment_sha256,
        observation_sha256=_observation_sha256(
            contract_sha256=contract.contract_sha256,
            session_key_sha256=session_key_sha256,
            head_source_contract_sha256=head_source_contract_sha256,
            status=status,
            profiles=profiles,
            content_commitment_sha256=content_commitment_sha256,
        ),
        _session_date=session_date,
    )


def run_kis_mtf_profiled_prospective_observer(
    *,
    historical_cache_root: Path | str,
    head_cache_root: Path | str,
    artifact_root: Path | str,
    repo_root: Path | str,
    code_revision: str,
    observed_at: datetime,
    catalog_loader: CatalogLoader,
) -> KisMtfProfiledProspectiveStoreResult | None:
    """Load local cache inputs, record one eligible result, and never call a provider."""

    if _prospective_observation_window(observed_at) is None:
        return None
    repository = Path(repo_root)
    historical_catalogs = catalog_loader(
        cache_root=Path(historical_cache_root),
        repo_root=repository,
    )
    contract = freeze_kis_mtf_profiled_prospective_observer_contract(
        historical_catalogs=historical_catalogs,
        code_revision=code_revision,
    )
    try:
        loaded_head_catalogs = catalog_loader(
            cache_root=Path(head_cache_root),
            repo_root=repository,
        )
        head_catalogs: Mapping[str, CatalogedBars | None] = loaded_head_catalogs
    except (OSError, ValueError):
        head_catalogs = {
            target_key: None for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        }
    observation = materialize_kis_mtf_profiled_prospective_observation(
        contract,
        historical_catalogs=historical_catalogs,
        head_catalogs=head_catalogs,
        observed_at=observed_at,
    )
    if observation is None:
        return None
    return append_kis_mtf_profiled_prospective_observation(
        artifact_root=artifact_root,
        repo_root=repository,
        contract=contract,
        observation=observation,
    )


def _prospective_observation_window(
    observed_at: datetime,
) -> tuple[date, SessionWindow, datetime] | None:
    """Return only a same-day regular-session causal cutoff geometry."""

    observed = require_utc(observed_at, "observed_at")
    session_date = observed.astimezone(_EASTERN).date()
    source_session = us_equity_2026_session(session_date)
    if source_session is None or source_session.kind != "regular":
        return None
    cutoff = datetime.combine(
        session_date,
        KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_CUTOFF,
        _EASTERN,
    ).astimezone(UTC)
    if observed < cutoff:
        return None
    return session_date, source_session.window, cutoff


def _forward_outcome_window(
    observed_at: datetime,
) -> tuple[date, SessionWindow, datetime, datetime] | None:
    """Return the fixed 15:30--15:45 ET completed-bar window when due."""

    base = _prospective_observation_window(observed_at)
    if base is None:
        return None
    session_date, session, cutoff = base
    outcome_end = cutoff + Timeframe.M1.duration * KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT
    if require_utc(observed_at, "observed_at") < outcome_end:
        return None
    return session_date, session, cutoff, outcome_end


def append_kis_mtf_profiled_prospective_observation(
    *,
    artifact_root: Path | str,
    repo_root: Path | str,
    contract: KisMtfProfiledProspectiveObserverContract,
    observation: KisMtfProfiledProspectiveObservation,
) -> KisMtfProfiledProspectiveStoreResult:
    """Append one immutable source-safe observation or reconcile an exact retry."""

    if observation.contract_sha256 != contract.contract_sha256:
        raise ValueError("prospective observation contract does not match the store")
    root = _observation_store_root(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        contract_sha256=contract.contract_sha256,
    )
    candidate_payload = observation.safe_payload()
    candidate_encoded = _canonical_json(candidate_payload)
    try:
        with _exclusive_store_lock(root / ".append.lock"):
            _write_immutable_json(root / "contract.json", contract.safe_payload())
            destination = (
                root / "observations" / f"{_storage_key(observation.session_key_sha256)}.json"
            )
            existing = _read_existing_observation(destination)
            if existing is None:
                _write_immutable_json(destination, candidate_payload)
                return KisMtfProfiledProspectiveStoreResult(
                    outcome="appended",
                    observation=observation,
                )
            existing_bytes, existing_payload = existing
            if existing_bytes == candidate_encoded:
                return KisMtfProfiledProspectiveStoreResult(
                    outcome="duplicate",
                    observation=observation,
                )
            conflict_sha256 = _sha256(
                {
                    "existing_content_commitment_sha256": existing_payload[
                        "content_commitment_sha256"
                    ],
                    "candidate_content_commitment_sha256": observation.content_commitment_sha256,
                }
            )
            _write_immutable_json(
                root
                / "conflicts"
                / (
                    f"{_storage_key(observation.session_key_sha256)}-"
                    f"{_storage_key(conflict_sha256)}.json"
                ),
                {
                    "kind": KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID,
                    "session_key_sha256": observation.session_key_sha256,
                    "existing_content_commitment_sha256": existing_payload[
                        "content_commitment_sha256"
                    ],
                    "candidate_content_commitment_sha256": observation.content_commitment_sha256,
                    "conflict_sha256": conflict_sha256,
                },
            )
            return KisMtfProfiledProspectiveStoreResult(
                outcome="conflict",
                observation=observation,
                conflict_sha256=conflict_sha256,
            )
    except BlockingIOError:
        return KisMtfProfiledProspectiveStoreResult(outcome="busy", observation=observation)


def freeze_kis_mtf_profiled_forward_outcome_contract(
    observer_contract: KisMtfProfiledProspectiveObserverContract,
) -> KisMtfProfiledForwardOutcomeContract:
    """Bind the one eligible short-profile outcome geometry to a frozen observer."""

    fields = {
        "observer_contract_sha256": observer_contract.contract_sha256,
        "profile_id": KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID,
        "outcome_bar_count": KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT,
    }
    return KisMtfProfiledForwardOutcomeContract(
        **fields,
        contract_sha256=_forward_outcome_contract_sha256(**fields),
    )


def materialize_kis_mtf_profiled_forward_outcome_witness(
    contract: KisMtfProfiledForwardOutcomeContract,
    *,
    observer_contract: KisMtfProfiledProspectiveObserverContract,
    historical_catalogs: Mapping[str, CatalogedBars],
    head_catalogs: Mapping[str, CatalogedBars | None],
    artifact_root: Path | str,
    repo_root: Path | str,
    observed_at: datetime,
) -> KisMtfProfiledForwardOutcomeMaterialization | None:
    """Pair one persisted causal input with a complete post-cutoff M1 window.

    The returned snapshot candidate remains in memory.  Only a target-ready
    append writes it under the caller's external market-data root.
    """

    if contract.observer_contract_sha256 != observer_contract.contract_sha256:
        raise ValueError("forward outcome contract does not match the observer contract")
    window = _forward_outcome_window(observed_at)
    if window is None:
        return None
    session_date, session, cutoff, outcome_end = window
    if session_date in observer_contract.historical_session_dates:
        return None
    session_key_sha256 = _forward_outcome_session_key_sha256(
        contract_sha256=contract.contract_sha256,
        session_date=session_date,
    )
    stored_input = _read_stored_short_input_observation(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        observer_contract=observer_contract,
        session_date=session_date,
    )
    if stored_input is None:
        return _forward_outcome_unavailable_materialization(
            contract=contract,
            session_key_sha256=session_key_sha256,
            status="input_unavailable",
        )

    current_input = materialize_kis_mtf_profiled_prospective_observation(
        observer_contract,
        historical_catalogs=historical_catalogs,
        head_catalogs=head_catalogs,
        observed_at=observed_at,
    )
    if current_input is None or not _short_profile_is_observed(current_input):
        return _forward_outcome_unavailable_materialization(
            contract=contract,
            session_key_sha256=session_key_sha256,
            status="input_unavailable",
        )
    stored_input_sha256 = stored_input["observation_sha256"]
    stored_head_source_contract_sha256 = stored_input["head_source_contract_sha256"]
    if (
        current_input.observation_sha256 != stored_input_sha256
        or current_input.head_source_contract_sha256 != stored_head_source_contract_sha256
    ):
        return _forward_outcome_unavailable_materialization(
            contract=contract,
            session_key_sha256=session_key_sha256,
            status="input_mutated",
            input_observation_sha256=stored_input_sha256,
        )

    try:
        input_prefix_by_target, input_source_contract_sha256 = _forward_input_prefixes(
            head_catalogs=head_catalogs,
            code_revision=observer_contract.code_revision,
            session=session,
            cutoff=cutoff,
        )
    except (SequenceWindowInputError, TypeError, ValueError):
        return _forward_outcome_unavailable_materialization(
            contract=contract,
            session_key_sha256=session_key_sha256,
            status="input_unavailable",
        )
    if input_source_contract_sha256 != stored_head_source_contract_sha256:
        return _forward_outcome_unavailable_materialization(
            contract=contract,
            session_key_sha256=session_key_sha256,
            status="input_mutated",
            input_observation_sha256=stored_input_sha256,
        )

    legs, outcome_bars_by_target = _forward_outcome_leg_commitments(
        head_catalogs=head_catalogs,
        session=session,
        cutoff=cutoff,
        outcome_end=outcome_end,
        observed_at=observed_at,
    )
    if any(leg.status != "available" for leg in legs):
        return _forward_outcome_unavailable_materialization(
            contract=contract,
            session_key_sha256=session_key_sha256,
            status="outcome_unavailable",
            input_observation_sha256=stored_input_sha256,
            legs=legs,
        )
    raw_snapshot_payload = _forward_outcome_raw_snapshot_payload(
        contract=contract,
        session_key_sha256=session_key_sha256,
        input_observation_sha256=stored_input_sha256,
        input_prefix_by_target=input_prefix_by_target,
        outcome_bars_by_target=outcome_bars_by_target,
    )
    raw_snapshot_sha256 = _sha256(raw_snapshot_payload)
    witness = _forward_outcome_witness(
        contract=contract,
        session_key_sha256=session_key_sha256,
        input_observation_sha256=stored_input_sha256,
        status="target_ready",
        legs=legs,
        raw_snapshot_sha256=raw_snapshot_sha256,
    )
    return KisMtfProfiledForwardOutcomeMaterialization(
        witness=witness,
        raw_snapshot_payload=raw_snapshot_payload,
    )


def append_kis_mtf_profiled_forward_outcome_witness(
    *,
    artifact_root: Path | str,
    market_data_root: Path | str,
    repo_root: Path | str,
    contract: KisMtfProfiledForwardOutcomeContract,
    materialization: KisMtfProfiledForwardOutcomeMaterialization,
) -> KisMtfProfiledForwardOutcomeStoreResult:
    """Persist a target-ready witness only after its D:-only snapshot is immutable."""

    witness = materialization.witness
    if witness.contract_sha256 != contract.contract_sha256:
        raise ValueError("forward outcome witness contract does not match the store")
    if witness.status != "target_ready":
        return KisMtfProfiledForwardOutcomeStoreResult(
            outcome=witness.status,
            witness=witness,
        )
    raw_snapshot_payload = materialization.raw_snapshot_payload
    if raw_snapshot_payload is None:
        raise ValueError("target-ready forward outcome is missing its raw snapshot")
    artifact = Path(artifact_root)
    repository = Path(repo_root)
    root = _forward_outcome_store_root(
        artifact_root=artifact,
        repo_root=repository,
        contract_sha256=contract.contract_sha256,
    )
    raw_root = _forward_outcome_raw_snapshot_root(
        market_data_root=Path(market_data_root),
        repo_root=repository,
        contract_sha256=contract.contract_sha256,
    )
    candidate_payload = witness.safe_payload()
    candidate_encoded = _canonical_json(candidate_payload)
    raw_destination = raw_root / f"{_storage_key(witness.session_key_sha256)}.json"
    destination = root / "outcomes" / f"{_storage_key(witness.session_key_sha256)}.json"
    try:
        with _exclusive_store_lock(root / ".append.lock"):
            _write_immutable_json(root / "contract.json", contract.safe_payload())
            existing = _read_existing_forward_outcome_witness(destination)
            if existing is None:
                _write_immutable_json(raw_destination, raw_snapshot_payload)
                _assert_raw_snapshot_hash(
                    destination=raw_destination,
                    expected_sha256=witness.raw_snapshot_sha256,
                )
                _write_immutable_json(destination, candidate_payload)
                return KisMtfProfiledForwardOutcomeStoreResult(
                    outcome="appended",
                    witness=witness,
                )
            existing_bytes, existing_witness = existing
            if existing_bytes == candidate_encoded:
                _write_immutable_json(raw_destination, raw_snapshot_payload)
                _assert_raw_snapshot_hash(
                    destination=raw_destination,
                    expected_sha256=witness.raw_snapshot_sha256,
                )
                return KisMtfProfiledForwardOutcomeStoreResult(
                    outcome="duplicate",
                    witness=witness,
                )
            conflict_sha256 = _sha256(
                {
                    "existing_content_commitment_sha256": (
                        existing_witness.content_commitment_sha256
                    ),
                    "candidate_content_commitment_sha256": witness.content_commitment_sha256,
                }
            )
            _write_immutable_json(
                root
                / "conflicts"
                / (
                    f"{_storage_key(witness.session_key_sha256)}-"
                    f"{_storage_key(conflict_sha256)}.json"
                ),
                {
                    "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
                    "session_key_sha256": witness.session_key_sha256,
                    "existing_content_commitment_sha256": (
                        existing_witness.content_commitment_sha256
                    ),
                    "candidate_content_commitment_sha256": witness.content_commitment_sha256,
                    "conflict_sha256": conflict_sha256,
                },
            )
            return KisMtfProfiledForwardOutcomeStoreResult(
                outcome="conflict",
                witness=witness,
                conflict_sha256=conflict_sha256,
            )
    except BlockingIOError:
        return KisMtfProfiledForwardOutcomeStoreResult(outcome="busy", witness=witness)


def inspect_kis_mtf_profiled_forward_outcome_inventory(
    *,
    artifact_root: Path | str,
    market_data_root: Path | str,
    repo_root: Path | str,
    contract: KisMtfProfiledForwardOutcomeContract,
) -> KisMtfProfiledForwardOutcomeInventory:
    """Expose only replayable target-ready count and opaque manifest identity."""

    witnesses = _stored_target_ready_forward_outcome_witnesses(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        contract=contract,
    )
    raw_root = _existing_forward_outcome_raw_snapshot_root(
        market_data_root=Path(market_data_root),
        repo_root=Path(repo_root),
        contract_sha256=contract.contract_sha256,
    )
    if witnesses and raw_root is None:
        raise ValueError("forward outcome raw snapshot store is missing")
    for witness in witnesses:
        _assert_raw_snapshot_hash(
            destination=raw_root / f"{_storage_key(witness.session_key_sha256)}.json",
            expected_sha256=witness.raw_snapshot_sha256,
        )
    return _forward_outcome_inventory_from_witnesses(contract, witnesses)


def load_kis_mtf_profiled_forward_outcome_snapshot_catalog(
    *,
    artifact_root: Path | str,
    market_data_root: Path | str,
    repo_root: Path | str,
    contract: KisMtfProfiledForwardOutcomeContract,
) -> KisMtfProfiledForwardOutcomeSnapshotCatalog:
    """Open verified retained snapshots only after a caller chooses this Data path."""

    witnesses = _stored_target_ready_forward_outcome_witnesses(
        artifact_root=Path(artifact_root),
        repo_root=Path(repo_root),
        contract=contract,
    )
    inventory = _forward_outcome_inventory_from_witnesses(contract, witnesses)
    if not witnesses:
        return KisMtfProfiledForwardOutcomeSnapshotCatalog(
            contract=contract,
            inventory=inventory,
            snapshots=(),
        )
    raw_root = _existing_forward_outcome_raw_snapshot_root(
        market_data_root=Path(market_data_root),
        repo_root=Path(repo_root),
        contract_sha256=contract.contract_sha256,
    )
    if raw_root is None:
        raise ValueError("forward outcome raw snapshot store is missing")
    snapshots = tuple(
        _read_forward_outcome_raw_snapshot(
            destination=raw_root / f"{_storage_key(witness.session_key_sha256)}.json",
            contract=contract,
            witness=witness,
        )
        for witness in witnesses
    )
    return KisMtfProfiledForwardOutcomeSnapshotCatalog(
        contract=contract,
        inventory=inventory,
        snapshots=tuple(
            sorted(
                snapshots,
                key=lambda snapshot: (snapshot.outcome_end, snapshot.session_key_sha256),
            )
        ),
    )


def _stored_target_ready_forward_outcome_witnesses(
    *,
    artifact_root: Path,
    repo_root: Path,
    contract: KisMtfProfiledForwardOutcomeContract,
) -> tuple[KisMtfProfiledForwardOutcomeWitness, ...]:
    root = _existing_forward_outcome_store_root(
        artifact_root=artifact_root,
        repo_root=repo_root,
        contract_sha256=contract.contract_sha256,
    )
    if root is None:
        return ()
    outcomes_root = root / "outcomes"
    if outcomes_root.is_symlink() or not outcomes_root.is_dir():
        raise ValueError("forward outcome inventory store is malformed")
    witnesses: list[KisMtfProfiledForwardOutcomeWitness] = []
    for path in sorted(outcomes_root.glob("*.json")):
        existing = _read_existing_forward_outcome_witness(path)
        if existing is None:
            continue
        _, witness = existing
        if witness.contract_sha256 != contract.contract_sha256:
            raise ValueError("forward outcome inventory contract changed")
        if witness.status != "target_ready" or witness.raw_snapshot_sha256 is None:
            raise ValueError("forward outcome store contains a non-target-ready witness")
        witnesses.append(witness)
    return tuple(witnesses)


def _forward_outcome_inventory_from_witnesses(
    contract: KisMtfProfiledForwardOutcomeContract,
    witnesses: tuple[KisMtfProfiledForwardOutcomeWitness, ...],
) -> KisMtfProfiledForwardOutcomeInventory:
    witness_hashes = [witness.witness_sha256 for witness in witnesses]
    manifest = _sha256(
        {
            "contract_sha256": contract.contract_sha256,
            "target_ready_witness_sha256": witness_hashes,
        }
    )
    return KisMtfProfiledForwardOutcomeInventory(
        contract_sha256=contract.contract_sha256,
        target_ready_pair_count=len(witnesses),
        target_ready_manifest_sha256=manifest,
        status="target_ready" if witnesses else "zero_target_ready",
    )


def run_kis_mtf_profiled_forward_outcome_witness(
    *,
    historical_cache_root: Path | str,
    head_cache_root: Path | str,
    artifact_root: Path | str,
    market_data_root: Path | str,
    repo_root: Path | str,
    code_revision: str,
    observed_at: datetime,
    catalog_loader: CatalogLoader,
) -> KisMtfProfiledForwardOutcomeStoreResult | None:
    """Run the local-only paired witness path without provider or credential access."""

    if _forward_outcome_window(observed_at) is None:
        return None
    repository = Path(repo_root)
    historical_catalogs = catalog_loader(
        cache_root=Path(historical_cache_root),
        repo_root=repository,
    )
    observer_contract = freeze_kis_mtf_profiled_prospective_observer_contract(
        historical_catalogs=historical_catalogs,
        code_revision=code_revision,
    )
    contract = freeze_kis_mtf_profiled_forward_outcome_contract(observer_contract)
    try:
        head_catalogs: Mapping[str, CatalogedBars | None] = catalog_loader(
            cache_root=Path(head_cache_root),
            repo_root=repository,
        )
    except (OSError, ValueError):
        head_catalogs = {
            target_key: None for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        }
    materialization = materialize_kis_mtf_profiled_forward_outcome_witness(
        contract,
        observer_contract=observer_contract,
        historical_catalogs=historical_catalogs,
        head_catalogs=head_catalogs,
        artifact_root=artifact_root,
        repo_root=repository,
        observed_at=observed_at,
    )
    if materialization is None:
        return None
    return append_kis_mtf_profiled_forward_outcome_witness(
        artifact_root=artifact_root,
        market_data_root=market_data_root,
        repo_root=repository,
        contract=contract,
        materialization=materialization,
    )


def _profile_commitments(
    *,
    head_catalogs: Mapping[str, CatalogedBars | None],
    code_revision: str,
    session: SessionWindow,
    cutoff: datetime,
) -> tuple[tuple[KisMtfProfiledProspectiveProfileCommitment, ...], str | None]:
    if set(head_catalogs) != set(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS) or any(
        catalog is None for catalog in head_catalogs.values()
    ):
        return _unavailable_profiles(), None
    present_catalogs = {
        target_key: catalog
        for target_key, catalog in head_catalogs.items()
        if isinstance(catalog, CatalogedBars)
    }
    try:
        head_contract = freeze_kis_intraday_mtf_availability_contract(
            present_catalogs,
            code_revision=code_revision,
        )
        source_by_target = {
            source.target_key: source for source in head_contract.source_identities
        }
        prefix_by_target = {
            target_key: completed_causal_minute_prefix(
                present_catalogs[target_key].bars,
                expected_symbol=source_by_target[target_key].target_key.split("/", maxsplit=1)[0],
                session=session,
                cutoff=cutoff,
            )
            for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        }
        prefix_source_hash_by_target = {
            target_key: _causal_prefix_source_sha256(
                target_key=target_key,
                prefix=prefix_by_target[target_key],
            )
            for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        }
        bars_by_timeframe = {
            target_key: resample_completed_causal_prefix(
                prefix_by_target[target_key],
                session=session,
                cutoff=cutoff,
            )
            for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        }
    except (SequenceWindowInputError, TypeError, ValueError):
        return _unavailable_profiles(), None
    head_source_contract_sha256 = _causal_head_source_contract_sha256(
        code_revision=code_revision,
        prefix_source_hash_by_target=prefix_source_hash_by_target,
    )
    profiles: list[KisMtfProfiledProspectiveProfileCommitment] = []
    for profile_id in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS:
        try:
            legs = tuple(
                build_target_free_mtf_feature_projection(
                    source_contract_sha256=head_source_contract_sha256,
                    source_dataset_hash=prefix_source_hash_by_target[target_key],
                    catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
                    profile_id=profile_id,
                    minute_bars=prefix_by_target[target_key],
                    bars_by_timeframe=bars_by_timeframe[target_key],
                    cutoff=cutoff,
                )
                for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
            )
            pair = build_target_free_mtf_feature_pair(
                profile_id,
                head_source_contract_sha256,
                legs,
            )
        except (SequenceWindowInputError, TypeError, ValueError):
            profiles.append(
                KisMtfProfiledProspectiveProfileCommitment(
                    profile_id=profile_id,
                    status="input_unavailable",
                    pair_input_sha256=None,
                )
            )
        else:
            profiles.append(
                KisMtfProfiledProspectiveProfileCommitment(
                    profile_id=profile_id,
                    status="observed",
                    pair_input_sha256=pair.pair_input_sha256,
                )
            )
    return tuple(profiles), head_source_contract_sha256


def _forward_input_prefixes(
    *,
    head_catalogs: Mapping[str, CatalogedBars | None],
    code_revision: str,
    session: SessionWindow,
    cutoff: datetime,
) -> tuple[dict[str, tuple[Bar, ...]], str]:
    """Recover the exact causal input bars used by the stored observer hash."""

    if set(head_catalogs) != set(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS) or any(
        catalog is None for catalog in head_catalogs.values()
    ):
        raise ValueError("forward outcome input catalogs are unavailable")
    present_catalogs = {
        target_key: catalog
        for target_key, catalog in head_catalogs.items()
        if isinstance(catalog, CatalogedBars)
    }
    prefix_by_target = {
        target_key: completed_causal_minute_prefix(
            present_catalogs[target_key].bars,
            expected_symbol=target_key.split("/", maxsplit=1)[0],
            session=session,
            cutoff=cutoff,
        )
        for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
    }
    source_hash = _causal_head_source_contract_sha256(
        code_revision=code_revision,
        prefix_source_hash_by_target={
            target_key: _causal_prefix_source_sha256(
                target_key=target_key,
                prefix=prefix_by_target[target_key],
            )
            for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        },
    )
    return prefix_by_target, source_hash


def _forward_outcome_leg_commitments(
    *,
    head_catalogs: Mapping[str, CatalogedBars | None],
    session: SessionWindow,
    cutoff: datetime,
    outcome_end: datetime,
    observed_at: datetime,
) -> tuple[
    tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...],
    dict[str, tuple[Bar, ...]],
]:
    """Commit exactly fifteen completed M1 bars per fixed target key."""

    bars_by_target: dict[str, tuple[Bar, ...]] = {}
    legs: list[KisMtfProfiledForwardOutcomeLegCommitment] = []
    for leg_index, target_key in enumerate(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS):
        catalog = head_catalogs.get(target_key)
        try:
            if not isinstance(catalog, CatalogedBars):
                raise ValueError("forward outcome catalog is unavailable")
            bars = _complete_forward_outcome_bars(
                catalog.bars,
                expected_symbol=target_key.split("/", maxsplit=1)[0],
                session=session,
                cutoff=cutoff,
                outcome_end=outcome_end,
                observed_at=observed_at,
            )
        except (SequenceWindowInputError, TypeError, ValueError):
            legs.append(
                KisMtfProfiledForwardOutcomeLegCommitment(
                    leg_index=leg_index,
                    status="unavailable",
                    content_commitment_sha256=None,
                )
            )
        else:
            bars_by_target[target_key] = bars
            legs.append(
                KisMtfProfiledForwardOutcomeLegCommitment(
                    leg_index=leg_index,
                    status="available",
                    content_commitment_sha256=_forward_outcome_leg_content_sha256(
                        target_key=target_key,
                        bars=bars,
                    ),
                )
            )
    return tuple(legs), bars_by_target


def _complete_forward_outcome_bars(
    bars: tuple[Bar, ...],
    *,
    expected_symbol: str,
    session: SessionWindow,
    cutoff: datetime,
    outcome_end: datetime,
    observed_at: datetime,
) -> tuple[Bar, ...]:
    selected = tuple(
        bar
        for bar in bars
        if cutoff <= bar.start_ts < outcome_end
    )
    expected_starts = tuple(
        cutoff + Timeframe.M1.duration * index
        for index in range(KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT)
    )
    ordered = tuple(sorted(selected, key=lambda bar: bar.start_ts))
    if (
        len(selected) != len(expected_starts)
        or tuple(bar.start_ts for bar in ordered) != expected_starts
        or any(
            bar.symbol != expected_symbol
            or bar.market != "US"
            or bar.timeframe != Timeframe.M1
            or not bar.complete
            or bar.end_ts > observed_at
            or bar.start_ts < session.open_ts
            or bar.end_ts > session.close_ts
            for bar in ordered
        )
    ):
        raise ValueError("forward outcome completed minute window is invalid")
    return ordered


def _forward_outcome_unavailable_materialization(
    *,
    contract: KisMtfProfiledForwardOutcomeContract,
    session_key_sha256: str,
    status: Literal["input_unavailable", "outcome_unavailable", "input_mutated"],
    input_observation_sha256: str | None = None,
    legs: tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...] | None = None,
) -> KisMtfProfiledForwardOutcomeMaterialization:
    if legs is None:
        legs = _unavailable_forward_outcome_legs()
    witness = _forward_outcome_witness(
        contract=contract,
        session_key_sha256=session_key_sha256,
        input_observation_sha256=input_observation_sha256,
        status=status,
        legs=legs,
        raw_snapshot_sha256=None,
    )
    return KisMtfProfiledForwardOutcomeMaterialization(
        witness=witness,
        raw_snapshot_payload=None,
    )


def _forward_outcome_witness(
    *,
    contract: KisMtfProfiledForwardOutcomeContract,
    session_key_sha256: str,
    input_observation_sha256: str | None,
    status: ForwardOutcomeStatus,
    legs: tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...],
    raw_snapshot_sha256: str | None,
) -> KisMtfProfiledForwardOutcomeWitness:
    content_commitment_sha256 = _forward_outcome_content_commitment_sha256(
        contract_sha256=contract.contract_sha256,
        session_key_sha256=session_key_sha256,
        input_observation_sha256=input_observation_sha256,
        status=status,
        legs=legs,
        raw_snapshot_sha256=raw_snapshot_sha256,
    )
    return KisMtfProfiledForwardOutcomeWitness(
        contract_sha256=contract.contract_sha256,
        session_key_sha256=session_key_sha256,
        input_observation_sha256=input_observation_sha256,
        status=status,
        legs=legs,
        raw_snapshot_sha256=raw_snapshot_sha256,
        content_commitment_sha256=content_commitment_sha256,
        witness_sha256=_forward_outcome_witness_sha256(
            contract_sha256=contract.contract_sha256,
            session_key_sha256=session_key_sha256,
            input_observation_sha256=input_observation_sha256,
            status=status,
            legs=legs,
            raw_snapshot_sha256=raw_snapshot_sha256,
            content_commitment_sha256=content_commitment_sha256,
        ),
    )


def _unavailable_forward_outcome_legs() -> tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...]:
    return tuple(
        KisMtfProfiledForwardOutcomeLegCommitment(
            leg_index=leg_index,
            status="unavailable",
            content_commitment_sha256=None,
        )
        for leg_index in range(len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS))
    )


def _short_profile_is_observed(observation: KisMtfProfiledProspectiveObservation) -> bool:
    return (
        observation.status == "observed"
        and any(
            profile.profile_id == KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID
            and profile.status == "observed"
            for profile in observation.profiles
        )
    )


def _forward_outcome_raw_snapshot_payload(
    *,
    contract: KisMtfProfiledForwardOutcomeContract,
    session_key_sha256: str,
    input_observation_sha256: str,
    input_prefix_by_target: Mapping[str, tuple[Bar, ...]],
    outcome_bars_by_target: Mapping[str, tuple[Bar, ...]],
) -> dict[str, object]:
    if (
        tuple(input_prefix_by_target) != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        or tuple(outcome_bars_by_target) != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
    ):
        raise ValueError("forward outcome raw snapshot targets are invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_RAW_SNAPSHOT_ID,
        "contract_sha256": contract.contract_sha256,
        "observer_contract_sha256": contract.observer_contract_sha256,
        "session_key_sha256": session_key_sha256,
        "input_observation_sha256": input_observation_sha256,
        "input_prefixes": [
            {
                "target_key": target_key,
                "bars": [
                    _forward_outcome_raw_bar_payload(bar)
                    for bar in input_prefix_by_target[target_key]
                ],
            }
            for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        ],
        "outcome_windows": [
            {
                "target_key": target_key,
                "bars": [
                    _forward_outcome_raw_bar_payload(bar)
                    for bar in outcome_bars_by_target[target_key]
                ],
            }
            for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
        ],
    }


def _forward_outcome_raw_bar_payload(bar: Bar) -> dict[str, object]:
    return {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": bar.start_ts.isoformat(),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": bar.complete,
    }


def _read_forward_outcome_raw_snapshot(
    *,
    destination: Path,
    contract: KisMtfProfiledForwardOutcomeContract,
    witness: KisMtfProfiledForwardOutcomeWitness,
) -> KisMtfProfiledForwardOutcomeSnapshot:
    """Read one immutable D:-resident target snapshot after hash reattestation."""

    if witness.status != "target_ready" or witness.raw_snapshot_sha256 is None:
        raise ValueError("forward outcome snapshot witness is not target-ready")
    if not destination.exists() or destination.is_symlink() or not destination.is_file():
        raise ValueError("forward outcome raw snapshot is unavailable")
    try:
        encoded = destination.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("forward outcome raw snapshot is malformed") from error
    if (
        "sha256:" + hashlib.sha256(encoded).hexdigest() != witness.raw_snapshot_sha256
        or not isinstance(payload, Mapping)
        or encoded != _canonical_json(payload)
    ):
        raise ValueError("forward outcome raw snapshot changed")
    return _forward_outcome_snapshot_from_raw_payload(
        payload,
        contract=contract,
        witness=witness,
    )


def _forward_outcome_snapshot_from_raw_payload(
    payload: Mapping[str, object],
    *,
    contract: KisMtfProfiledForwardOutcomeContract,
    witness: KisMtfProfiledForwardOutcomeWitness,
) -> KisMtfProfiledForwardOutcomeSnapshot:
    expected_keys = {
        "schema_version",
        "kind",
        "contract_sha256",
        "observer_contract_sha256",
        "session_key_sha256",
        "input_observation_sha256",
        "input_prefixes",
        "outcome_windows",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_MTF_PROFILED_FORWARD_OUTCOME_RAW_SNAPSHOT_ID
        or payload.get("contract_sha256") != contract.contract_sha256
        or payload.get("observer_contract_sha256") != contract.observer_contract_sha256
        or payload.get("session_key_sha256") != witness.session_key_sha256
        or payload.get("input_observation_sha256") != witness.input_observation_sha256
    ):
        raise ValueError("forward outcome raw snapshot is invalid")
    try:
        input_prefixes = _raw_snapshot_bar_groups(
            payload.get("input_prefixes"),
            field_name="input_prefixes",
        )
        outcome_windows = _raw_snapshot_bar_groups(
            payload.get("outcome_windows"),
            field_name="outcome_windows",
        )
        snapshot = KisMtfProfiledForwardOutcomeSnapshot(
            contract_sha256=contract.contract_sha256,
            session_key_sha256=witness.session_key_sha256,
            input_observation_sha256=_required_sha256_payload_field(
                payload,
                "input_observation_sha256",
            ),
            witness_sha256=witness.witness_sha256,
            raw_snapshot_sha256=witness.raw_snapshot_sha256,
            input_prefixes=input_prefixes,
            outcome_windows=outcome_windows,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("forward outcome raw snapshot is invalid") from error
    return snapshot


def _raw_snapshot_bar_groups(
    value: object,
    *,
    field_name: str,
) -> tuple[tuple[Bar, ...], ...]:
    if not isinstance(value, list) or len(value) != len(
        KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
    ):
        raise ValueError(f"forward outcome raw snapshot {field_name} is invalid")
    groups: list[tuple[Bar, ...]] = []
    for raw_group, target_key in zip(
        value,
        KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS,
        strict=True,
    ):
        group = _required_mapping(raw_group)
        bars = group.get("bars")
        if set(group) != {"target_key", "bars"} or group.get("target_key") != target_key:
            raise ValueError(f"forward outcome raw snapshot {field_name} target is invalid")
        if not isinstance(bars, list):
            raise ValueError(f"forward outcome raw snapshot {field_name} bars are invalid")
        groups.append(
            tuple(
                _raw_snapshot_bar_from_payload(raw_bar, target_key=target_key)
                for raw_bar in bars
            )
        )
    return tuple(groups)


def _raw_snapshot_bar_from_payload(
    value: object,
    *,
    target_key: str,
) -> Bar:
    payload = _required_mapping(value)
    expected_keys = {
        "symbol",
        "market",
        "timeframe",
        "start_ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "complete",
    }
    expected_symbol = target_key.split("/", maxsplit=1)[0]
    if (
        set(payload) != expected_keys
        or payload.get("symbol") != expected_symbol
        or payload.get("market") != "US"
        or payload.get("timeframe") != Timeframe.M1.value
        or type(payload.get("complete")) is not bool
        or not payload.get("complete")
    ):
        raise ValueError("forward outcome raw snapshot bar is invalid")
    start_ts_value = payload.get("start_ts")
    decimal_fields = ("open", "high", "low", "close", "volume")
    if not isinstance(start_ts_value, str) or any(
        not isinstance(payload.get(field_name), str) for field_name in decimal_fields
    ):
        raise ValueError("forward outcome raw snapshot bar is invalid")
    try:
        start_ts = require_utc(datetime.fromisoformat(start_ts_value), "start_ts")
        decimals = {
            field_name: Decimal(str(payload[field_name])) for field_name in decimal_fields
        }
        if (
            start_ts.isoformat() != start_ts_value
            or any(
                str(decimals[field_name]) != payload[field_name]
                for field_name in decimal_fields
            )
        ):
            raise ValueError("forward outcome raw snapshot bar is noncanonical")
        return Bar(
            symbol=expected_symbol,
            market="US",
            timeframe=Timeframe.M1,
            start_ts=start_ts,
            open=decimals["open"],
            high=decimals["high"],
            low=decimals["low"],
            close=decimals["close"],
            volume=decimals["volume"],
            complete=True,
        )
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("forward outcome raw snapshot bar is invalid") from error


def _validate_forward_snapshot_sequence(
    bars: tuple[Bar, ...],
    *,
    target_key: str,
) -> None:
    """Keep exact completed M1 chronology without coupling the two symbols by row."""

    expected_symbol = target_key.split("/", maxsplit=1)[0]
    if (
        not bars
        or any(
            bar.symbol != expected_symbol
            or bar.market != "US"
            or bar.timeframe != Timeframe.M1
            or not bar.complete
            for bar in bars
        )
        or tuple(bar.start_ts for bar in bars)
        != tuple(bars[0].start_ts + Timeframe.M1.duration * index for index in range(len(bars)))
    ):
        raise ValueError("forward outcome snapshot sequence is invalid")


def _unavailable_profiles() -> tuple[KisMtfProfiledProspectiveProfileCommitment, ...]:
    return tuple(
        KisMtfProfiledProspectiveProfileCommitment(
            profile_id=profile_id,
            status="input_unavailable",
            pair_input_sha256=None,
        )
        for profile_id in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS
    )


def _status_for_profiles(
    profiles: tuple[KisMtfProfiledProspectiveProfileCommitment, ...],
) -> ObservationStatus:
    if all(profile.status == "observed" for profile in profiles):
        return "observed"
    return "input_unavailable"


def _common_eligible_session_dates(
    receipt: KisIntradayMtfAvailabilityReceipt,
) -> tuple[date, ...]:
    dates = [target.eligible_session_dates for target in receipt.targets]
    common = set(dates[0]) if dates else set()
    for target_dates in dates[1:]:
        common.intersection_update(target_dates)
    return tuple(sorted(common))


def _observation_store_root(
    *,
    artifact_root: Path,
    repo_root: Path,
    contract_sha256: str,
) -> Path:
    _reject_market_data_artifact_root(artifact_root)
    parts = (
        "research",
        KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ARTIFACT_DIRECTORY,
        "c",
        _storage_key(contract_sha256),
    )
    root = ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        *parts,
    )
    for directory_name in ("observations", "conflicts"):
        ensure_external_artifact_directory(artifact_root, repo_root, *parts, directory_name)
    return root


def _read_stored_short_input_observation(
    *,
    artifact_root: Path,
    repo_root: Path,
    observer_contract: KisMtfProfiledProspectiveObserverContract,
    session_date: date,
) -> dict[str, str] | None:
    root = _observation_store_root(
        artifact_root=artifact_root,
        repo_root=repo_root,
        contract_sha256=observer_contract.contract_sha256,
    )
    session_key_sha256 = _session_key_sha256(
        contract_sha256=observer_contract.contract_sha256,
        session_date=session_date,
    )
    existing = _read_existing_observation(
        root / "observations" / f"{_storage_key(session_key_sha256)}.json"
    )
    if existing is None:
        return None
    _, payload = existing
    profiles = payload["profile_aggregates"]
    if (
        payload["contract_sha256"] != observer_contract.contract_sha256
        or payload["session_key_sha256"] != session_key_sha256
        or payload["status"] != "observed"
        or not isinstance(profiles, list)
        or not any(
            isinstance(profile, Mapping)
            and profile.get("profile_id") == KIS_MTF_PROFILED_FORWARD_OUTCOME_PROFILE_ID
            and profile.get("status") == "observed"
            and _is_sha256(profile.get("pair_input_sha256"))
            for profile in profiles
        )
        or not _is_sha256(payload["observation_sha256"])
        or not _is_sha256(payload["head_source_contract_sha256"])
    ):
        return None
    return {
        "observation_sha256": payload["observation_sha256"],
        "head_source_contract_sha256": payload["head_source_contract_sha256"],
    }


def _forward_outcome_store_root(
    *,
    artifact_root: Path,
    repo_root: Path,
    contract_sha256: str,
) -> Path:
    _reject_market_data_artifact_root(artifact_root)
    parts = (
        "research",
        KIS_MTF_PROFILED_FORWARD_OUTCOME_ARTIFACT_DIRECTORY,
        "c",
        _storage_key(contract_sha256),
    )
    root = ensure_external_artifact_directory(artifact_root, repo_root, *parts)
    for directory_name in ("outcomes", "conflicts"):
        ensure_external_artifact_directory(artifact_root, repo_root, *parts, directory_name)
    return root


def _forward_outcome_raw_snapshot_root(
    *,
    market_data_root: Path,
    repo_root: Path,
    contract_sha256: str,
) -> Path:
    return ensure_external_artifact_directory(
        market_data_root,
        repo_root,
        "us_equities",
        "kis_paper_private",
        KIS_MTF_PROFILED_FORWARD_OUTCOME_RAW_DIRECTORY,
        "c",
        _storage_key(contract_sha256),
        "snapshots",
    )


def _existing_forward_outcome_store_root(
    *,
    artifact_root: Path,
    repo_root: Path,
    contract_sha256: str,
) -> Path | None:
    _reject_market_data_artifact_root(artifact_root)
    reject_repo_artifact_path(artifact_root, repo_root)
    return _existing_external_child_directory(
        artifact_root,
        "research",
        KIS_MTF_PROFILED_FORWARD_OUTCOME_ARTIFACT_DIRECTORY,
        "c",
        _storage_key(contract_sha256),
    )


def _existing_forward_outcome_raw_snapshot_root(
    *,
    market_data_root: Path,
    repo_root: Path,
    contract_sha256: str,
) -> Path | None:
    _reject_repo_market_data_root(market_data_root, repo_root)
    return _existing_external_child_directory(
        market_data_root,
        "us_equities",
        "kis_paper_private",
        KIS_MTF_PROFILED_FORWARD_OUTCOME_RAW_DIRECTORY,
        "c",
        _storage_key(contract_sha256),
        "snapshots",
    )


def _existing_external_child_directory(root: Path, *parts: str) -> Path | None:
    current = root.absolute()
    if not current.exists():
        return None
    if current.is_symlink() or not current.is_dir():
        raise ValueError("forward outcome read-only root is invalid")
    resolved_root = current.resolve(strict=True)
    for part in parts:
        if not part or Path(part).name != part:
            raise ValueError("forward outcome read-only path is invalid")
        current = current / part
        if not current.exists():
            return None
        if current.is_symlink() or not current.is_dir():
            raise ValueError("forward outcome read-only path is invalid")
        resolved = current.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            raise ValueError("forward outcome read-only path escapes its root")
    return current.resolve(strict=True)


def _reject_repo_market_data_root(market_data_root: Path, repo_root: Path) -> None:
    candidate = market_data_root.absolute().resolve(strict=False)
    repository = repo_root.absolute().resolve(strict=False)
    if os.name != "nt":
        docker_repo_root = Path("/app").resolve()
        docker_market_data_root = docker_repo_root / "market_data"
        if repository == docker_repo_root and candidate == docker_market_data_root:
            return
    if candidate == repository or repository in candidate.parents:
        raise ValueError("market_data_root must be outside the Git workspace")


def _reject_market_data_artifact_root(artifact_root: Path) -> None:
    candidate = artifact_root.absolute().resolve(strict=False)
    market_data_root = Path("D:/market_data").absolute().resolve(strict=False)
    if candidate == market_data_root or candidate.is_relative_to(market_data_root):
        raise ValueError("prospective observer artifacts must not use the market-data root")


@contextmanager
def _exclusive_store_lock(path: Path) -> Iterator[None]:
    if path.exists() or path.is_symlink():
        raise BlockingIOError("prospective observer store is busy")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise BlockingIOError("prospective observer store is busy") from error
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def _write_immutable_json(destination: Path, payload: Mapping[str, object]) -> None:
    if (
        destination.is_symlink()
        or destination.parent.is_symlink()
        or not destination.parent.is_dir()
    ):
        raise ValueError("prospective observer artifact must not be a symlink")
    encoded = _canonical_json(payload)
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != encoded:
            raise ValueError("prospective observer immutable artifact conflicts")
        return
    staging = destination.parent / f".{destination.name}.stage"
    try:
        staging.unlink(missing_ok=True)
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def _read_existing_observation(
    destination: Path,
) -> tuple[bytes, dict[str, object]] | None:
    if not destination.exists():
        return None
    if destination.is_symlink() or not destination.is_file():
        raise ValueError("prospective observer stored observation is invalid")
    try:
        encoded = destination.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("prospective observer stored observation is invalid") from error
    if (
        not isinstance(payload, dict)
        or encoded != _canonical_json(payload)
        or not _is_safe_observation_payload(payload)
    ):
        raise ValueError("prospective observer stored observation is invalid")
    return encoded, payload


def _read_existing_forward_outcome_witness(
    destination: Path,
) -> tuple[bytes, KisMtfProfiledForwardOutcomeWitness] | None:
    if not destination.exists():
        return None
    if destination.is_symlink() or not destination.is_file():
        raise ValueError("forward outcome stored witness is invalid")
    try:
        encoded = destination.read_bytes()
        payload = json.loads(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("forward outcome stored witness is invalid") from error
    if not isinstance(payload, dict) or encoded != _canonical_json(payload):
        raise ValueError("forward outcome stored witness is invalid")
    witness = _forward_outcome_witness_from_safe_payload(payload)
    return encoded, witness


def _forward_outcome_witness_from_safe_payload(
    payload: Mapping[str, object],
) -> KisMtfProfiledForwardOutcomeWitness:
    expected_keys = {
        "schema_version",
        "kind",
        "contract_sha256",
        "session_key_sha256",
        "input_observation_sha256",
        "status",
        "outcome_geometry",
        "legs",
        "raw_snapshot_sha256",
        "content_commitment_sha256",
        "witness_sha256",
        "scope",
    }
    legs = payload.get("legs")
    geometry = payload.get("outcome_geometry")
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID
        or payload.get("outcome_geometry")
        != {
            "timeframe": Timeframe.M1.value,
            "post_cutoff_bar_count": KIS_MTF_PROFILED_FORWARD_OUTCOME_BAR_COUNT,
        }
        or not isinstance(geometry, Mapping)
        or not isinstance(legs, list)
        or payload.get("scope")
        != _forward_outcome_scope(
            raw_snapshot_retained=payload.get("raw_snapshot_sha256") is not None
        )
    ):
        raise ValueError("forward outcome stored witness is invalid")
    try:
        witness = KisMtfProfiledForwardOutcomeWitness(
            contract_sha256=_required_sha256_payload_field(payload, "contract_sha256"),
            session_key_sha256=_required_sha256_payload_field(payload, "session_key_sha256"),
            input_observation_sha256=_optional_sha256_payload_field(
                payload,
                "input_observation_sha256",
            ),
            status=_required_forward_outcome_status(payload.get("status")),
            legs=tuple(
                KisMtfProfiledForwardOutcomeLegCommitment(
                    leg_index=_required_leg_index(leg),
                    status=_required_leg_status(leg),
                    content_commitment_sha256=_optional_sha256_payload_field(
                        _required_mapping(leg),
                        "content_commitment_sha256",
                    ),
                )
                for leg in legs
            ),
            raw_snapshot_sha256=_optional_sha256_payload_field(
                payload,
                "raw_snapshot_sha256",
            ),
            content_commitment_sha256=_required_sha256_payload_field(
                payload,
                "content_commitment_sha256",
            ),
            witness_sha256=_required_sha256_payload_field(payload, "witness_sha256"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("forward outcome stored witness is invalid") from error
    if payload != witness.safe_payload():
        raise ValueError("forward outcome stored witness is invalid")
    return witness


def _assert_raw_snapshot_hash(*, destination: Path, expected_sha256: str | None) -> None:
    if expected_sha256 is None or not _is_sha256(expected_sha256):
        raise ValueError("forward outcome raw snapshot hash is invalid")
    if not destination.exists() or destination.is_symlink() or not destination.is_file():
        raise ValueError("forward outcome raw snapshot is unavailable")
    try:
        actual_sha256 = "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError("forward outcome raw snapshot is unavailable") from error
    if actual_sha256 != expected_sha256:
        raise ValueError("forward outcome raw snapshot hash changed")


def _is_safe_observation_payload(payload: Mapping[str, object]) -> bool:
    expected_keys = {
        "schema_version",
        "kind",
        "contract_sha256",
        "session_key_sha256",
        "head_source_contract_sha256",
        "status",
        "profile_aggregates",
        "content_commitment_sha256",
        "observation_sha256",
        "scope",
    }
    profiles = payload.get("profile_aggregates")
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID
        or not all(
            _is_sha256(payload.get(field_name))
            for field_name in (
                "contract_sha256",
                "session_key_sha256",
                "content_commitment_sha256",
                "observation_sha256",
            )
        )
        or payload.get("head_source_contract_sha256") is not None
        and not _is_sha256(payload.get("head_source_contract_sha256"))
        or payload.get("status") not in {"observed", "input_unavailable"}
        or not isinstance(profiles, list)
        or payload.get("scope") != _source_safe_scope()
    ):
        return False
    if len(profiles) != len(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS):
        return False
    for profile, profile_id in zip(
        profiles,
        KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_PROFILE_IDS,
        strict=True,
    ):
        if (
            not isinstance(profile, Mapping)
            or set(profile) != {"profile_id", "status", "pair_input_sha256"}
            or profile.get("profile_id") != profile_id
            or profile.get("status") not in {"observed", "input_unavailable"}
            or (profile.get("status") == "observed")
            != (profile.get("pair_input_sha256") is not None)
            or profile.get("pair_input_sha256") is not None
            and not _is_sha256(profile.get("pair_input_sha256"))
        ):
            return False
    return True


def _contract_sha256(
    *,
    historical_source_contract_sha256: str,
    historical_receipt_sha256: str,
    preflight_summary_sha256: str,
    catalog_sha256: str,
    historical_session_count: int,
    historical_exclusion_sha256: str,
    code_revision: str,
) -> str:
    return _sha256(
        {
            "kind": KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_ID,
            "historical_source_contract_sha256": historical_source_contract_sha256,
            "historical_receipt_sha256": historical_receipt_sha256,
            "preflight_summary_sha256": preflight_summary_sha256,
            "catalog_sha256": catalog_sha256,
            "historical_session_count": historical_session_count,
            "historical_exclusion_sha256": historical_exclusion_sha256,
            "code_revision": code_revision,
        }
    )


def _historical_exclusion_sha256(dates: tuple[date, ...]) -> str:
    return _sha256({"historical_session_dates": [value.isoformat() for value in dates]})


def _causal_prefix_source_sha256(*, target_key: str, prefix: tuple[Bar, ...]) -> str:
    return _sha256(
        {
            "target_key": target_key,
            "completed_minute_prefix": [
                {
                    "symbol": bar.symbol,
                    "market": bar.market,
                    "timeframe": bar.timeframe.value,
                    "start_ts": bar.start_ts.isoformat(),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                    "complete": bar.complete,
                }
                for bar in prefix
            ],
        }
    )


def _causal_head_source_contract_sha256(
    *,
    code_revision: str,
    prefix_source_hash_by_target: Mapping[str, str],
) -> str:
    if set(prefix_source_hash_by_target) != set(KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS):
        raise ValueError("prospective observer causal source identities are invalid")
    return _sha256(
        {
            "code_revision": code_revision,
            "catalog_sha256": KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256,
            "prefix_source_hashes": [
                prefix_source_hash_by_target[target_key]
                for target_key in KIS_MTF_PROFILED_PROSPECTIVE_OBSERVER_TARGET_KEYS
            ],
        }
    )


def _session_key_sha256(*, contract_sha256: str, session_date: date) -> str:
    return _sha256(
        {
            "contract_sha256": contract_sha256,
            "session_date": session_date.isoformat(),
        }
    )


def _forward_outcome_contract_sha256(
    *,
    observer_contract_sha256: str,
    profile_id: str,
    outcome_bar_count: int,
) -> str:
    return _sha256(
        {
            "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
            "observer_contract_sha256": observer_contract_sha256,
            "profile_id": profile_id,
            "outcome_geometry": {
                "timeframe": Timeframe.M1.value,
                "post_cutoff_bar_count": outcome_bar_count,
            },
        }
    )


def _forward_outcome_session_key_sha256(*, contract_sha256: str, session_date: date) -> str:
    return _sha256(
        {
            "kind": KIS_MTF_PROFILED_FORWARD_OUTCOME_WITNESS_ID,
            "contract_sha256": contract_sha256,
            "session_date": session_date.isoformat(),
        }
    )


def _forward_outcome_leg_content_sha256(*, target_key: str, bars: tuple[Bar, ...]) -> str:
    return _sha256(
        {
            "target_key": target_key,
            "completed_outcome_minute_bars": [
                _forward_outcome_raw_bar_payload(bar) for bar in bars
            ],
        }
    )


def _forward_outcome_content_commitment_sha256(
    *,
    contract_sha256: str,
    session_key_sha256: str,
    input_observation_sha256: str | None,
    status: ForwardOutcomeStatus,
    legs: tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...],
    raw_snapshot_sha256: str | None,
) -> str:
    return _sha256(
        {
            "contract_sha256": contract_sha256,
            "session_key_sha256": session_key_sha256,
            "input_observation_sha256": input_observation_sha256,
            "status": status,
            "legs": [leg.safe_payload() for leg in legs],
            "raw_snapshot_sha256": raw_snapshot_sha256,
        }
    )


def _forward_outcome_witness_sha256(
    *,
    contract_sha256: str,
    session_key_sha256: str,
    input_observation_sha256: str | None,
    status: ForwardOutcomeStatus,
    legs: tuple[KisMtfProfiledForwardOutcomeLegCommitment, ...],
    raw_snapshot_sha256: str | None,
    content_commitment_sha256: str,
) -> str:
    return _sha256(
        {
            "contract_sha256": contract_sha256,
            "session_key_sha256": session_key_sha256,
            "input_observation_sha256": input_observation_sha256,
            "status": status,
            "legs": [leg.safe_payload() for leg in legs],
            "raw_snapshot_sha256": raw_snapshot_sha256,
            "content_commitment_sha256": content_commitment_sha256,
        }
    )


def _content_commitment_sha256(
    *,
    contract_sha256: str,
    session_key_sha256: str,
    head_source_contract_sha256: str | None,
    status: ObservationStatus,
    profiles: tuple[KisMtfProfiledProspectiveProfileCommitment, ...],
) -> str:
    return _sha256(
        {
            "contract_sha256": contract_sha256,
            "session_key_sha256": session_key_sha256,
            "head_source_contract_sha256": head_source_contract_sha256,
            "status": status,
            "profiles": [profile.safe_payload() for profile in profiles],
        }
    )


def _observation_sha256(
    *,
    contract_sha256: str,
    session_key_sha256: str,
    head_source_contract_sha256: str | None,
    status: ObservationStatus,
    profiles: tuple[KisMtfProfiledProspectiveProfileCommitment, ...],
    content_commitment_sha256: str,
) -> str:
    return _sha256(
        {
            "contract_sha256": contract_sha256,
            "session_key_sha256": session_key_sha256,
            "head_source_contract_sha256": head_source_contract_sha256,
            "status": status,
            "profiles": [profile.safe_payload() for profile in profiles],
            "content_commitment_sha256": content_commitment_sha256,
        }
    )


def _source_safe_scope() -> dict[str, bool]:
    return {
        "target_or_label_opened": False,
        "return_or_cost_opened": False,
        "model_or_prediction_opened": False,
        "pnl_calculated": False,
        "gpu_used": False,
        "paper_or_broker_action": False,
        "provider_or_network_called": False,
        "credentials_or_environment_read": False,
        "raw_market_data_written": False,
        "raw_market_data_persisted": False,
    }


def _forward_outcome_scope(*, raw_snapshot_retained: bool) -> dict[str, bool]:
    return {
        "target_or_label_opened": False,
        "return_or_cost_opened": False,
        "model_or_prediction_opened": False,
        "pnl_calculated": False,
        "gpu_used": False,
        "paper_or_broker_action": False,
        "provider_or_network_called": False,
        "credentials_or_environment_read": False,
        "raw_market_data_written": raw_snapshot_retained,
        "raw_market_data_persisted": raw_snapshot_retained,
        "raw_market_data_d_only": raw_snapshot_retained,
    }


def _required_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("forward outcome payload mapping is invalid")
    return value


def _required_sha256_payload_field(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not _is_sha256(value):
        raise ValueError("forward outcome payload hash is invalid")
    return value


def _optional_sha256_payload_field(
    payload: Mapping[str, object],
    field_name: str,
) -> str | None:
    value = payload.get(field_name)
    if value is not None and not _is_sha256(value):
        raise ValueError("forward outcome payload hash is invalid")
    return value


def _required_forward_outcome_status(value: object) -> ForwardOutcomeStatus:
    if value not in {
        "target_ready",
        "input_unavailable",
        "outcome_unavailable",
        "input_mutated",
    }:
        raise ValueError("forward outcome payload status is invalid")
    return value


def _required_leg_index(value: object) -> int:
    leg_index = _required_mapping(value).get("leg_index")
    if type(leg_index) is not int:
        raise ValueError("forward outcome payload leg index is invalid")
    return leg_index


def _required_leg_status(
    value: object,
) -> Literal["available", "unavailable"]:
    status = _required_mapping(value).get("status")
    if status not in {"available", "unavailable"}:
        raise ValueError("forward outcome payload leg status is invalid")
    return status


def _storage_key(value: str) -> str:
    _require_sha256(value, "storage key")
    return value.removeprefix("sha256:")[:16]


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value.removeprefix("sha256:"))
    )

"""Forward-only, source-safe QQQ/SPY intraday observation attempts.

This module intentionally stops at immutable causal-input evidence.  It has no
provider client, credential, model, target, return, PnL, or broker behavior.
The caller supplies already verified local KIS catalogs and this leaf records
only commitments to their selected content outside the Git workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data import kis_intraday_mtf_availability as availability
from thericher_v2.data.kis_paper_intraday import load_verified_kis_paper_private_intraday_catalog
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.models.sequence_window import (
    CausalMultiTimeframeSequenceWindow,
    SequenceWindowInputError,
    build_causal_multitimeframe_sequence_window,
)
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID = "kis-qqq-spy-mtf-prospective-observation-v1"
KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ARTIFACT_DIRECTORY = (
    "kis-qqq-spy-mtf-prospective-observation-v1"
)
KIS_QQQ_SPY_MTF_PROSPECTIVE_ATTEMPT_STORE_DIRECTORY = "attempt-store-v1"
KIS_QQQ_SPY_MTF_PROSPECTIVE_ATTEMPT_CAP = 30
KIS_QQQ_SPY_MTF_PROSPECTIVE_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
KIS_QQQ_SPY_MTF_PROSPECTIVE_CUTOFF = time(15, 30)
KIS_QQQ_SPY_MTF_PROSPECTIVE_LOOKBACKS = (
    (Timeframe.M1, 30),
    (Timeframe.M5, 6),
    (Timeframe.M10, 3),
    (Timeframe.H1, 2),
    (Timeframe.H3, 2),
)
KIS_QQQ_SPY_MTF_PROSPECTIVE_PREFIX_MINUTES = 360

_EASTERN = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_SHA256_PREFIX = "sha256:"
_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_QQQ_SPY_MTF_PROSPECTIVE_TARGETS
)
_TIMEFRAMES = tuple(timeframe for timeframe, _ in KIS_QQQ_SPY_MTF_PROSPECTIVE_LOOKBACKS)
_LOOKBACKS = dict(KIS_QQQ_SPY_MTF_PROSPECTIVE_LOOKBACKS)
_STORE_SCHEMA_ID = "kis-qqq-spy-mtf-prospective-attempt-store-v1"
_SAFE_AVAILABILITY_STATUSES = frozenset({"available", "missing", "invalid"})


class KisQqqSpyMtfProspectiveObservationError(ValueError):
    """A source-safe contract or input failure for this one observation path."""


@dataclass(frozen=True, slots=True)
class KisQqqSpyMtfSourceIdentity:
    """A source identity without a source location or observed market values."""

    target_key: str
    dataset_id: str | None
    dataset_hash: str | None

    def __post_init__(self) -> None:
        if self.target_key not in _TARGET_KEYS:
            raise ValueError("prospective source target is invalid")
        if self.dataset_id is None and self.dataset_hash is not None:
            raise ValueError("prospective source identity is invalid")
        if self.dataset_id is not None and (
            not isinstance(self.dataset_id, str) or not self.dataset_id.strip()
        ):
            raise ValueError("prospective source identity is invalid")
        if self.dataset_hash is not None and not _is_sha256(self.dataset_hash):
            raise ValueError("prospective source identity is invalid")

    def safe_payload(self) -> dict[str, str | None]:
        return {
            "target_key": self.target_key,
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
        }


@dataclass(frozen=True, slots=True)
class KisQqqSpyMtfProspectiveContract:
    """Frozen geometry and historical exclusion evidence for one attempt store."""

    availability_contract_sha256: str
    availability_receipt_sha256: str
    availability_precommit_sha256: str
    availability_summary_sha256: str
    historical_source_identities: tuple[KisQqqSpyMtfSourceIdentity, ...]
    historical_exclusion_through: date
    code_revision: str
    contract_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        sources = tuple(self.historical_source_identities)
        object.__setattr__(self, "historical_source_identities", sources)
        if (
            tuple(source.target_key for source in sources) != _TARGET_KEYS
            or any(source.dataset_id is None or source.dataset_hash is None for source in sources)
            or type(self.historical_exclusion_through) is not date
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("prospective observation contract is invalid")
        for value, field_name in (
            (self.availability_contract_sha256, "availability contract"),
            (self.availability_receipt_sha256, "availability receipt"),
            (self.availability_precommit_sha256, "availability precommit"),
            (self.availability_summary_sha256, "availability summary"),
            (self.code_revision, "code revision"),
            (self.contract_sha256, "prospective contract"),
        ):
            _require_sha256(value, field_name)
        if self.contract_sha256 != _contract_sha256(
            availability_contract_sha256=self.availability_contract_sha256,
            availability_receipt_sha256=self.availability_receipt_sha256,
            availability_precommit_sha256=self.availability_precommit_sha256,
            availability_summary_sha256=self.availability_summary_sha256,
            historical_source_identities=sources,
            historical_exclusion_through=self.historical_exclusion_through,
            code_revision=self.code_revision,
        ):
            raise ValueError("prospective observation contract hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID,
            "availability": {
                "contract_sha256": self.availability_contract_sha256,
                "receipt_sha256": self.availability_receipt_sha256,
                "precommit_sha256": self.availability_precommit_sha256,
                "summary_sha256": self.availability_summary_sha256,
                "historical_sources": [
                    source.safe_payload() for source in self.historical_source_identities
                ],
                "historical_exclusion_through": self.historical_exclusion_through.isoformat(),
            },
            "geometry": _geometry_payload(),
            "code_revision": self.code_revision,
            "contract_sha256": self.contract_sha256,
            "scope": {
                "forward_attempt_only": True,
                "model_or_strategy_result": False,
                "target_or_return_opened": False,
                "pnl_calculated": False,
                "paper_or_broker_action": False,
                "gpu_used": False,
                "raw_market_data_written": False,
                "credentials_read": False,
                "network_access": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisQqqSpyMtfTargetAttempt:
    """One leg's categorical result and opaque content commitment."""

    source: KisQqqSpyMtfSourceIdentity
    availability: Literal["available", "missing", "invalid"]
    content_commitment_sha256: str
    _sequence_window: CausalMultiTimeframeSequenceWindow | None = field(
        repr=False, compare=False, default=None
    )
    _minimum_seal_at: datetime | None = field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self.availability not in _SAFE_AVAILABILITY_STATUSES:
            raise ValueError("prospective target availability is invalid")
        _require_sha256(self.content_commitment_sha256, "target content commitment")
        if self.availability == "available":
            if self.source.dataset_id is None:
                raise ValueError("available target is missing its source identity")
            if self._sequence_window is not None and self._minimum_seal_at is None:
                raise ValueError("available target is missing a source close")
        if self._sequence_window is not None and not isinstance(
            self._sequence_window, CausalMultiTimeframeSequenceWindow
        ):
            raise TypeError("target sequence window is invalid")
        if self._minimum_seal_at is not None:
            object.__setattr__(
                self,
                "_minimum_seal_at",
                require_utc(self._minimum_seal_at, "target source close"),
            )

    def safe_payload(self) -> dict[str, object]:
        return {
            "source": self.source.safe_payload(),
            "availability": self.availability,
            "content_commitment_sha256": self.content_commitment_sha256,
        }


@dataclass(frozen=True, slots=True)
class KisQqqSpyMtfProspectiveAttemptDraft:
    """A one-session attempt before the append-only store assigns its seal."""

    contract: KisQqqSpyMtfProspectiveContract
    session_date: date
    session: SessionWindow | None
    cutoff: datetime | None
    observed_at: datetime
    targets: tuple[KisQqqSpyMtfTargetAttempt, ...]
    status: Literal["observed", "not_observed"]
    reason: str
    session_key_sha256: str
    content_commitment_sha256: str
    _minimum_seal_at: datetime = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        targets = tuple(self.targets)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(
            self,
            "_minimum_seal_at",
            require_utc(self._minimum_seal_at, "attempt minimum seal"),
        )
        if (
            type(self.session_date) is not date
            or tuple(target.source.target_key for target in targets) != _TARGET_KEYS
            or self.status not in {"observed", "not_observed"}
            or not self.reason
        ):
            raise ValueError("prospective attempt draft is invalid")
        if (self.session is None) != (self.cutoff is None):
            raise ValueError("prospective attempt session geometry is invalid")
        if self.session is not None and self.cutoff is not None:
            _validate_regular_geometry(self.session, self.cutoff, self.session_date)
        for value, field_name in (
            (self.session_key_sha256, "attempt session key"),
            (self.content_commitment_sha256, "attempt content commitment"),
        ):
            _require_sha256(value, field_name)
        expected_key = _session_key_sha256(
            contract_sha256=self.contract.contract_sha256,
            session_date=self.session_date,
        )
        if self.session_key_sha256 != expected_key:
            raise ValueError("prospective attempt session key is invalid")
        expected_content = _attempt_content_commitment_sha256(
            contract_sha256=self.contract.contract_sha256,
            session_date=self.session_date,
            session=self.session,
            cutoff=self.cutoff,
            status=self.status,
            reason=self.reason,
            targets=targets,
        )
        if self.content_commitment_sha256 != expected_content:
            raise ValueError("prospective attempt content commitment is invalid")

    def seal_after(self, previous_seal: datetime | None) -> KisQqqSpyMtfProspectiveAttempt:
        """Assign a monotonic seal without changing the frozen input commitment."""

        minimum = max(self.observed_at, self._minimum_seal_at)
        if previous_seal is not None:
            prior = require_utc(previous_seal, "previous attempt seal")
            minimum = max(minimum, prior + timedelta(microseconds=1))
        return KisQqqSpyMtfProspectiveAttempt(
            contract_sha256=self.contract.contract_sha256,
            session_date=self.session_date,
            session=self.session,
            cutoff=self.cutoff,
            sealed_at=minimum,
            status=self.status,
            reason=self.reason,
            targets=self.targets,
            session_key_sha256=self.session_key_sha256,
            content_commitment_sha256=self.content_commitment_sha256,
            attempt_sha256=_attempt_sha256(
                contract_sha256=self.contract.contract_sha256,
                session_date=self.session_date,
                session=self.session,
                cutoff=self.cutoff,
                sealed_at=minimum,
                status=self.status,
                reason=self.reason,
                targets=self.targets,
                session_key_sha256=self.session_key_sha256,
                content_commitment_sha256=self.content_commitment_sha256,
            ),
        )


@dataclass(frozen=True, slots=True)
class KisQqqSpyMtfProspectiveAttempt:
    """One immutable primary attempt record; values and provider paths stay absent."""

    contract_sha256: str
    session_date: date
    session: SessionWindow | None
    cutoff: datetime | None
    sealed_at: datetime
    status: Literal["observed", "not_observed"]
    reason: str
    targets: tuple[KisQqqSpyMtfTargetAttempt, ...]
    session_key_sha256: str
    content_commitment_sha256: str
    attempt_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        targets = tuple(self.targets)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "sealed_at", require_utc(self.sealed_at, "attempt seal"))
        if (
            type(self.session_date) is not date
            or tuple(target.source.target_key for target in targets) != _TARGET_KEYS
            or self.status not in {"observed", "not_observed"}
            or not self.reason
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("prospective attempt is invalid")
        if (self.session is None) != (self.cutoff is None):
            raise ValueError("prospective attempt session geometry is invalid")
        if self.session is not None and self.cutoff is not None:
            _validate_regular_geometry(self.session, self.cutoff, self.session_date)
            if self.sealed_at < self.cutoff:
                raise ValueError("prospective attempt seal precedes the final source-bar close")
        for value, field_name in (
            (self.contract_sha256, "attempt contract"),
            (self.session_key_sha256, "attempt session key"),
            (self.content_commitment_sha256, "attempt content commitment"),
            (self.attempt_sha256, "attempt hash"),
        ):
            _require_sha256(value, field_name)
        if self.session_key_sha256 != _session_key_sha256(
            contract_sha256=self.contract_sha256,
            session_date=self.session_date,
        ):
            raise ValueError("prospective attempt session key is invalid")
        expected = _attempt_sha256(
            contract_sha256=self.contract_sha256,
            session_date=self.session_date,
            session=self.session,
            cutoff=self.cutoff,
            sealed_at=self.sealed_at,
            status=self.status,
            reason=self.reason,
            targets=targets,
            session_key_sha256=self.session_key_sha256,
            content_commitment_sha256=self.content_commitment_sha256,
        )
        if self.attempt_sha256 != expected:
            raise ValueError("prospective attempt hash is invalid")

    def safe_payload(self) -> dict[str, object]:
        session_payload: dict[str, str] | None
        if self.session is None or self.cutoff is None:
            session_payload = None
        else:
            session_payload = {
                "open_ts": _utc_marker(self.session.open_ts),
                "close_ts": _utc_marker(self.session.close_ts),
                "cutoff": _utc_marker(self.cutoff),
            }
        return {
            "schema_version": self.schema_version,
            "kind": KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID,
            "contract_sha256": self.contract_sha256,
            "session": {
                "date": self.session_date.isoformat(),
                "geometry": session_payload,
                "session_key_sha256": self.session_key_sha256,
            },
            "sealed_at": _utc_marker(self.sealed_at),
            "status": self.status,
            "reason": self.reason,
            "targets": [target.safe_payload() for target in self.targets],
            "content_commitment_sha256": self.content_commitment_sha256,
            "attempt_sha256": self.attempt_sha256,
            "scope": {
                "model_or_strategy_result": False,
                "target_or_return_opened": False,
                "pnl_calculated": False,
                "paper_or_broker_action": False,
                "gpu_used": False,
                "raw_market_data_written": False,
                "credentials_read": False,
                "network_access": False,
            },
        }


@dataclass(frozen=True, slots=True)
class KisQqqSpyMtfProspectiveStoreResult:
    """Source-safe append result; paths stay internal to the caller."""

    outcome: Literal["appended", "duplicate", "conflict", "cap_reached", "busy"]
    attempt_count: int
    attempt: KisQqqSpyMtfProspectiveAttempt | None
    conflict_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {"appended", "duplicate", "conflict", "cap_reached", "busy"}:
            raise ValueError("prospective store outcome is invalid")
        if not 0 <= self.attempt_count <= KIS_QQQ_SPY_MTF_PROSPECTIVE_ATTEMPT_CAP:
            raise ValueError("prospective store attempt count is invalid")
        if self.outcome in {"appended", "duplicate", "conflict"} and self.attempt is None:
            raise ValueError("prospective store outcome requires an attempt")
        if self.outcome == "conflict":
            _require_sha256(self.conflict_sha256, "conflict hash")
        elif self.conflict_sha256 is not None:
            raise ValueError("non-conflict store outcome has a conflict hash")

    def safe_payload(self) -> dict[str, object]:
        status = (
            self.attempt.status
            if self.outcome == "appended" and self.attempt is not None
            else self.outcome
        )
        payload: dict[str, object] = {
            "kind": KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID,
            "status": status,
            "store_outcome": self.outcome,
            "attempt_count": self.attempt_count,
        }
        if self.attempt is not None:
            payload["attempt"] = self.attempt.safe_payload()
        if self.conflict_sha256 is not None:
            payload["conflict_sha256"] = self.conflict_sha256
        return payload


def prospective_observation_window(
    observed_at: datetime,
) -> tuple[date, SessionWindow, datetime] | None:
    """Return the same-day 15:30 ET observation geometry, otherwise no-op."""

    observed = require_utc(observed_at, "observed_at")
    session_date = observed.astimezone(_EASTERN).date()
    source_session = us_equity_2026_session(session_date)
    if source_session is None or source_session.kind != "regular":
        return None
    cutoff = datetime.combine(
        session_date,
        KIS_QQQ_SPY_MTF_PROSPECTIVE_CUTOFF,
        _EASTERN,
    ).astimezone(UTC)
    if observed < cutoff:
        return None
    return session_date, source_session.window, cutoff


def freeze_kis_qqq_spy_mtf_prospective_contract(
    *,
    availability_summary_path: Path | str,
    historical_catalogs: Mapping[str, CatalogedBars],
    code_revision: str,
    repo_root: Path | str,
) -> KisQqqSpyMtfProspectiveContract:
    """Freeze the availability receipt and its exact historical exclusion scope."""

    _require_sha256(code_revision, "code revision")
    summary_path = _external_regular_file(Path(availability_summary_path), Path(repo_root))
    summary_bytes = summary_path.read_bytes()
    summary = _read_json_object(summary_bytes, "availability summary")
    binding = _availability_binding(summary)
    historical_sources = tuple(
        _source_identity_from_catalog(
            target_key,
            _catalog_for_target(historical_catalogs, target_key),
            include_dataset_hash=True,
        )
        for target_key in _TARGET_KEYS
    )
    if tuple(source.safe_payload() for source in historical_sources) != tuple(binding["sources"]):
        raise KisQqqSpyMtfProspectiveObservationError(
            "availability receipt source identity changed"
        )
    common_dates = _common_available_session_dates(historical_catalogs)
    expected_common_count = binding["common_aligned_session_count"]
    if len(common_dates) != expected_common_count or not common_dates:
        raise KisQqqSpyMtfProspectiveObservationError(
            "availability receipt historical exclusion does not match verified cache"
        )
    historical_exclusion_through = max(common_dates)
    summary_sha256 = _sha256_bytes(summary_bytes)
    contract_sha256 = _contract_sha256(
        availability_contract_sha256=binding["contract_sha256"],
        availability_receipt_sha256=binding["receipt_sha256"],
        availability_precommit_sha256=binding["precommit_sha256"],
        availability_summary_sha256=summary_sha256,
        historical_source_identities=historical_sources,
        historical_exclusion_through=historical_exclusion_through,
        code_revision=code_revision,
    )
    return KisQqqSpyMtfProspectiveContract(
        availability_contract_sha256=binding["contract_sha256"],
        availability_receipt_sha256=binding["receipt_sha256"],
        availability_precommit_sha256=binding["precommit_sha256"],
        availability_summary_sha256=summary_sha256,
        historical_source_identities=historical_sources,
        historical_exclusion_through=historical_exclusion_through,
        code_revision=code_revision,
        contract_sha256=contract_sha256,
    )


def materialize_kis_qqq_spy_mtf_prospective_attempt(
    contract: KisQqqSpyMtfProspectiveContract,
    *,
    prospective_catalogs: Mapping[str, CatalogedBars | None],
    observed_at: datetime,
) -> KisQqqSpyMtfProspectiveAttemptDraft:
    """Classify exactly the current Eastern session without creating a model input."""

    observed = require_utc(observed_at, "observed_at")
    session_date = observed.astimezone(_EASTERN).date()
    source_session = us_equity_2026_session(session_date)
    session = source_session.window if source_session is not None else None
    cutoff = (
        datetime.combine(session_date, KIS_QQQ_SPY_MTF_PROSPECTIVE_CUTOFF, _EASTERN).astimezone(UTC)
        if source_session is not None and source_session.kind == "regular"
        else None
    )
    if source_session is None:
        reason = "non_regular_session"
        targets = _unavailable_targets(prospective_catalogs, reason="missing")
    elif source_session.kind != "regular":
        reason = "non_regular_session"
        targets = _unavailable_targets(prospective_catalogs, reason="missing")
    elif session_date <= contract.historical_exclusion_through:
        reason = "historical_excluded"
        targets = _unavailable_targets(prospective_catalogs, reason="missing")
    elif cutoff is None or observed < cutoff:
        reason = "cutoff_not_reached"
        targets = _unavailable_targets(prospective_catalogs, reason="missing")
    else:
        assert session is not None
        targets = tuple(
            _evaluate_target(
                target_key=target_key,
                catalog=_catalog_or_none(prospective_catalogs, target_key),
                session=session,
                cutoff=cutoff,
            )
            for target_key in _TARGET_KEYS
        )
        availability = tuple(target.availability for target in targets)
        if availability == ("available", "available"):
            reason = "pair_available"
        elif availability == ("available", "missing") or availability == ("available", "invalid"):
            reason = "spy_unavailable"
        elif availability == ("missing", "available") or availability == ("invalid", "available"):
            reason = "qqq_unavailable"
        else:
            reason = "both_unavailable"
    status: Literal["observed", "not_observed"] = (
        "observed" if reason == "pair_available" else "not_observed"
    )
    minimum_seal = max(
        [observed]
        + [
            target._minimum_seal_at
            for target in targets
            if target._minimum_seal_at is not None
        ]
    )
    session_key_sha256 = _session_key_sha256(
        contract_sha256=contract.contract_sha256,
        session_date=session_date,
    )
    content_commitment_sha256 = _attempt_content_commitment_sha256(
        contract_sha256=contract.contract_sha256,
        session_date=session_date,
        session=session,
        cutoff=cutoff,
        status=status,
        reason=reason,
        targets=targets,
    )
    return KisQqqSpyMtfProspectiveAttemptDraft(
        contract=contract,
        session_date=session_date,
        session=session,
        cutoff=cutoff,
        observed_at=observed,
        targets=targets,
        status=status,
        reason=reason,
        session_key_sha256=session_key_sha256,
        content_commitment_sha256=content_commitment_sha256,
        _minimum_seal_at=minimum_seal,
    )


def run_kis_qqq_spy_mtf_prospective_attempt(
    *,
    availability_summary_path: Path | str,
    historical_cache_root: Path | str,
    head_cache_root: Path | str,
    artifact_root: Path | str,
    repo_root: Path | str,
    code_revision: str,
    observed_at: datetime,
) -> KisQqqSpyMtfProspectiveStoreResult | None:
    """Load verified local data only after the one same-day window is eligible."""

    if prospective_observation_window(observed_at) is None:
        return None
    repository = Path(repo_root)
    store_root = _attempt_store_root(
        artifact_root=Path(artifact_root),
        repo_root=repository,
    )
    contract = _load_store_contract(store_root)
    if contract is None:
        historical = {
            target_key: load_verified_kis_paper_private_intraday_catalog(
                cache_root=Path(historical_cache_root),
                repo_root=repository,
                symbol=symbol,
                exchange=exchange,
            )
            for target_key, (symbol, exchange) in zip(
                _TARGET_KEYS,
                KIS_QQQ_SPY_MTF_PROSPECTIVE_TARGETS,
                strict=True,
            )
        }
        contract = freeze_kis_qqq_spy_mtf_prospective_contract(
            availability_summary_path=availability_summary_path,
            historical_catalogs=historical,
            code_revision=code_revision,
            repo_root=repository,
        )
    elif contract.code_revision != code_revision:
        raise KisQqqSpyMtfProspectiveObservationError(
            "sealed prospective observation contract has a different code revision"
        )
    prospective: dict[str, CatalogedBars | None] = {}
    for target_key, (symbol, exchange) in zip(
        _TARGET_KEYS,
        KIS_QQQ_SPY_MTF_PROSPECTIVE_TARGETS,
        strict=True,
    ):
        try:
            prospective[target_key] = load_verified_kis_paper_private_intraday_catalog(
                cache_root=Path(head_cache_root),
                repo_root=repository,
                symbol=symbol,
                exchange=exchange,
            )
        except (OSError, ValueError):
            prospective[target_key] = None
    draft = materialize_kis_qqq_spy_mtf_prospective_attempt(
        contract,
        prospective_catalogs=prospective,
        observed_at=observed_at,
    )
    return append_kis_qqq_spy_mtf_prospective_attempt(
        artifact_root=artifact_root,
        repo_root=repository,
        draft=draft,
    )


def append_kis_qqq_spy_mtf_prospective_attempt(
    *,
    artifact_root: Path | str,
    repo_root: Path | str,
    draft: KisQqqSpyMtfProspectiveAttemptDraft,
) -> KisQqqSpyMtfProspectiveStoreResult:
    """Append one primary attempt or immutable conflict under a process-safe cap."""

    if not isinstance(draft, KisQqqSpyMtfProspectiveAttemptDraft):
        raise TypeError("prospective attempt draft is invalid")
    root = _attempt_store_root(artifact_root=Path(artifact_root), repo_root=Path(repo_root))
    _write_immutable_json(root / "contract.json", draft.contract.safe_payload())
    try:
        with _exclusive_store_lock(root / ".append.lock"):
            attempts = _load_primary_attempts(root, draft.contract.contract_sha256)
            previous_seal = _latest_record_seal(
                root,
                attempts.values(),
                contract_sha256=draft.contract.contract_sha256,
            )
            existing = attempts.get(draft.session_key_sha256)
            if existing is not None:
                if existing.content_commitment_sha256 == draft.content_commitment_sha256:
                    return KisQqqSpyMtfProspectiveStoreResult(
                        outcome="duplicate",
                        attempt_count=len(attempts),
                        attempt=existing,
                    )
                candidate = draft.seal_after(previous_seal)
                conflict_sha256 = _conflict_sha256(existing, candidate)
                conflict_name = (
                    f"{_storage_key_fragment(draft.session_key_sha256)}-"
                    f"{_storage_key_fragment(conflict_sha256)}.json"
                )
                _write_immutable_json(
                    root / "conflicts" / conflict_name,
                    _conflict_payload(existing, candidate, conflict_sha256),
                )
                return KisQqqSpyMtfProspectiveStoreResult(
                    outcome="conflict",
                    attempt_count=len(attempts),
                    attempt=candidate,
                    conflict_sha256=conflict_sha256,
                )
            if len(attempts) >= KIS_QQQ_SPY_MTF_PROSPECTIVE_ATTEMPT_CAP:
                return KisQqqSpyMtfProspectiveStoreResult(
                    outcome="cap_reached",
                    attempt_count=len(attempts),
                    attempt=None,
                )
            attempt = draft.seal_after(previous_seal)
            attempt_name = f"{_storage_key_fragment(attempt.session_key_sha256)}.json"
            _write_immutable_json(root / "attempts" / attempt_name, attempt.safe_payload())
            return KisQqqSpyMtfProspectiveStoreResult(
                outcome="appended",
                attempt_count=len(attempts) + 1,
                attempt=attempt,
            )
    except BlockingIOError:
        return KisQqqSpyMtfProspectiveStoreResult(
            outcome="busy",
            attempt_count=_count_primary_attempts(root),
            attempt=None,
        )


def _availability_binding(summary: Mapping[str, object]) -> dict[str, object]:
    if set(summary) != {"schema_version", "receipt_id", "precommit_sha256", "receipt"}:
        raise KisQqqSpyMtfProspectiveObservationError("availability summary shape is invalid")
    receipt = summary.get("receipt")
    if (
        summary.get("schema_version") != SCHEMA_VERSION
        or summary.get("receipt_id") != "kis-intraday-mtf-availability-receipt-v1"
        or not isinstance(receipt, Mapping)
    ):
        raise KisQqqSpyMtfProspectiveObservationError("availability summary identity is invalid")
    contract_sha256 = receipt.get("contract_sha256")
    receipt_sha256 = receipt.get("receipt_sha256")
    precommit_sha256 = summary.get("precommit_sha256")
    common_count = receipt.get("common_aligned_session_count")
    targets = receipt.get("targets")
    _require_sha256(contract_sha256, "availability contract")
    _require_sha256(receipt_sha256, "availability receipt")
    _require_sha256(precommit_sha256, "availability precommit")
    if (
        receipt.get("receipt_id") != "kis-intraday-mtf-availability-receipt-v1"
        or receipt.get("status") != "qualified_for_prospective_input"
        or receipt.get("reason") is not None
        or not isinstance(common_count, int)
        or common_count <= 0
        or not isinstance(targets, list)
        or len(targets) != len(_TARGET_KEYS)
    ):
        raise KisQqqSpyMtfProspectiveObservationError("availability receipt is not usable")
    sources: list[dict[str, str | None]] = []
    for target, target_key in zip(targets, _TARGET_KEYS, strict=True):
        if not isinstance(target, Mapping) or not isinstance(target.get("source"), Mapping):
            raise KisQqqSpyMtfProspectiveObservationError("availability receipt source is invalid")
        source = target["source"]
        raw_dataset_id = source.get("dataset_id")
        raw_dataset_hash = source.get("dataset_hash")
        identity = KisQqqSpyMtfSourceIdentity(
            target_key=str(source.get("target_key", "")),
            dataset_id=raw_dataset_id if isinstance(raw_dataset_id, str) else None,
            dataset_hash=raw_dataset_hash if isinstance(raw_dataset_hash, str) else None,
        )
        if identity.target_key != target_key or identity.dataset_id is None:
            raise KisQqqSpyMtfProspectiveObservationError("availability receipt source is invalid")
        sources.append(identity.safe_payload())
    return {
        "contract_sha256": contract_sha256,
        "receipt_sha256": receipt_sha256,
        "precommit_sha256": precommit_sha256,
        "common_aligned_session_count": common_count,
        "sources": sources,
    }


def _common_available_session_dates(catalogs: Mapping[str, CatalogedBars]) -> frozenset[date]:
    dates_by_target: list[frozenset[date]] = []
    for target_key in _TARGET_KEYS:
        catalog = _catalog_for_target(catalogs, target_key)
        materialized = availability._materialize_target(
            source=availability._source_identity(target_key=target_key, catalog=catalog),
            catalog=catalog,
        )
        dates_by_target.append(materialized.eligible_session_dates)
    common = set(dates_by_target[0])
    for dates in dates_by_target[1:]:
        common.intersection_update(dates)
    return frozenset(common)


def _unavailable_targets(
    catalogs: Mapping[str, CatalogedBars | None], *, reason: str
) -> tuple[KisQqqSpyMtfTargetAttempt, ...]:
    return tuple(
        _target_unavailable(
            target_key=target_key,
            catalog=_catalog_or_none(catalogs, target_key),
            availability=reason,
        )
        for target_key in _TARGET_KEYS
    )


def _evaluate_target(
    *,
    target_key: str,
    catalog: CatalogedBars | None,
    session: SessionWindow,
    cutoff: datetime,
) -> KisQqqSpyMtfTargetAttempt:
    if catalog is None:
        return _target_unavailable(target_key=target_key, catalog=None, availability="missing")
    source = _source_identity_from_catalog(target_key, catalog)
    selected = tuple(
        bar
        for bar in catalog.bars
        if session.open_ts <= bar.start_ts < cutoff
    )
    commitment = _target_content_commitment_sha256(
        target_key=target_key,
        source=source,
        session=session,
        cutoff=cutoff,
        bars=selected,
    )
    prefix = availability._complete_causal_prefix(
        catalog.bars,
        expected_symbol=target_key.split("/", maxsplit=1)[0],
        session=session,
        cutoff=cutoff,
    )
    if prefix is None:
        return KisQqqSpyMtfTargetAttempt(
            source=source,
            availability="invalid" if selected else "missing",
            content_commitment_sha256=commitment,
        )
    if not all(availability._available_timeframes(prefix, session=session, cutoff=cutoff).values()):
        return KisQqqSpyMtfTargetAttempt(
            source=source,
            availability="invalid",
            content_commitment_sha256=commitment,
        )
    try:
        bars_by_timeframe = {
            timeframe: resample_session_bars(prefix, timeframe, session=session).bars
            for timeframe in _TIMEFRAMES
        }
        sequence_window = build_causal_multitimeframe_sequence_window(
            bars_by_timeframe,
            lookbacks=_LOOKBACKS,
            cutoff=cutoff,
        )
        _validate_tail_containment(sequence_window, session=session, cutoff=cutoff)
    except (SequenceWindowInputError, KisQqqSpyMtfProspectiveObservationError, ValueError):
        return KisQqqSpyMtfTargetAttempt(
            source=source,
            availability="invalid" if selected else "missing",
            content_commitment_sha256=commitment,
        )
    return KisQqqSpyMtfTargetAttempt(
        source=source,
        availability="available",
        content_commitment_sha256=commitment,
        _sequence_window=sequence_window,
        _minimum_seal_at=cutoff,
    )


def _target_unavailable(
    *,
    target_key: str,
    catalog: CatalogedBars | None,
    availability: str,
) -> KisQqqSpyMtfTargetAttempt:
    if availability not in _SAFE_AVAILABILITY_STATUSES:
        raise ValueError("unavailable target category is invalid")
    source = (
        _source_identity_from_catalog(target_key, catalog)
        if catalog is not None
        else KisQqqSpyMtfSourceIdentity(target_key=target_key, dataset_id=None, dataset_hash=None)
    )
    return KisQqqSpyMtfTargetAttempt(
        source=source,
        availability=availability,  # type: ignore[arg-type]
        content_commitment_sha256=_sha256_payload(
            {
                "kind": "kis-qqq-spy-mtf-unavailable-target-v1",
                "source": source.safe_payload(),
                "availability": availability,
            }
        ),
    )


def _validate_tail_containment(
    sequence_window: CausalMultiTimeframeSequenceWindow,
    *,
    session: SessionWindow,
    cutoff: datetime,
) -> None:
    if tuple(sequence_window.windows) != _TIMEFRAMES or sequence_window.cutoff != cutoff:
        raise KisQqqSpyMtfProspectiveObservationError("timeframe geometry is invalid")
    for timeframe, lookback in KIS_QQQ_SPY_MTF_PROSPECTIVE_LOOKBACKS:
        window = sequence_window.windows[timeframe]
        if (
            len(window.bars) != lookback
            or window.start_ts < session.open_ts
            or window.end_ts > cutoff
            or window.end_ts != cutoff
            or (window.start_ts - session.open_ts) % timeframe.duration
        ):
            raise KisQqqSpyMtfProspectiveObservationError("timeframe tail escapes session prefix")


def _source_identity_from_catalog(
    target_key: str,
    catalog: CatalogedBars,
    *,
    include_dataset_hash: bool = False,
) -> KisQqqSpyMtfSourceIdentity:
    if not isinstance(catalog, CatalogedBars):
        raise TypeError("prospective catalog is invalid")
    return KisQqqSpyMtfSourceIdentity(
        target_key=target_key,
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash if include_dataset_hash else None,
    )


def _catalog_for_target(catalogs: Mapping[str, CatalogedBars], target_key: str) -> CatalogedBars:
    if set(catalogs) != set(_TARGET_KEYS):
        raise ValueError("prospective catalog targets are invalid")
    catalog = catalogs[target_key]
    if not isinstance(catalog, CatalogedBars):
        raise TypeError("prospective catalog is invalid")
    return catalog


def _catalog_or_none(
    catalogs: Mapping[str, CatalogedBars | None], target_key: str
) -> CatalogedBars | None:
    if set(catalogs) != set(_TARGET_KEYS):
        raise ValueError("prospective catalog targets are invalid")
    catalog = catalogs[target_key]
    if catalog is not None and not isinstance(catalog, CatalogedBars):
        raise TypeError("prospective catalog is invalid")
    return catalog


def _geometry_payload() -> dict[str, object]:
    return {
        "session": {
            "timezone": "America/New_York",
            "open": _REGULAR_OPEN.isoformat(),
            "close": _REGULAR_CLOSE.isoformat(),
            "cutoff": KIS_QQQ_SPY_MTF_PROSPECTIVE_CUTOFF.isoformat(),
            "same_day_weekday_regular_only": True,
        },
        "source_timeframe": Timeframe.M1.value,
        "prefix_minutes": KIS_QQQ_SPY_MTF_PROSPECTIVE_PREFIX_MINUTES,
        "tails": {
            timeframe.value: lookback
            for timeframe, lookback in KIS_QQQ_SPY_MTF_PROSPECTIVE_LOOKBACKS
        },
        "session_open_anchored": True,
        "tail_contained_in_prefix": True,
    }


def _contract_sha256(
    *,
    availability_contract_sha256: str,
    availability_receipt_sha256: str,
    availability_precommit_sha256: str,
    availability_summary_sha256: str,
    historical_source_identities: Sequence[KisQqqSpyMtfSourceIdentity],
    historical_exclusion_through: date,
    code_revision: str,
) -> str:
    return _sha256_payload(
        {
            "kind": KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID,
            "availability_contract_sha256": availability_contract_sha256,
            "availability_receipt_sha256": availability_receipt_sha256,
            "availability_precommit_sha256": availability_precommit_sha256,
            "availability_summary_sha256": availability_summary_sha256,
            "historical_source_identities": [
                source.safe_payload() for source in historical_source_identities
            ],
            "historical_exclusion_through": historical_exclusion_through.isoformat(),
            "geometry": _geometry_payload(),
            "code_revision": code_revision,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _session_key_sha256(*, contract_sha256: str, session_date: date) -> str:
    return _sha256_payload(
        {
            "kind": "kis-qqq-spy-mtf-prospective-session-key-v1",
            "contract_sha256": contract_sha256,
            "session_date": session_date.isoformat(),
        }
    )


def _attempt_content_commitment_sha256(
    *,
    contract_sha256: str,
    session_date: date,
    session: SessionWindow | None,
    cutoff: datetime | None,
    status: str,
    reason: str,
    targets: Sequence[KisQqqSpyMtfTargetAttempt],
) -> str:
    return _sha256_payload(
        {
            "kind": "kis-qqq-spy-mtf-prospective-attempt-content-v1",
            "contract_sha256": contract_sha256,
            "session_date": session_date.isoformat(),
            "session": _session_identity_payload(session, cutoff),
            "status": status,
            "reason": reason,
            "targets": [target.safe_payload() for target in targets],
        }
    )


def _attempt_sha256(
    *,
    contract_sha256: str,
    session_date: date,
    session: SessionWindow | None,
    cutoff: datetime | None,
    sealed_at: datetime,
    status: str,
    reason: str,
    targets: Sequence[KisQqqSpyMtfTargetAttempt],
    session_key_sha256: str,
    content_commitment_sha256: str,
) -> str:
    return _sha256_payload(
        {
            "kind": "kis-qqq-spy-mtf-prospective-attempt-v1",
            "contract_sha256": contract_sha256,
            "session_date": session_date.isoformat(),
            "session": _session_identity_payload(session, cutoff),
            "sealed_at": _utc_marker(sealed_at),
            "status": status,
            "reason": reason,
            "targets": [target.safe_payload() for target in targets],
            "session_key_sha256": session_key_sha256,
            "content_commitment_sha256": content_commitment_sha256,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _target_content_commitment_sha256(
    *,
    target_key: str,
    source: KisQqqSpyMtfSourceIdentity,
    session: SessionWindow,
    cutoff: datetime,
    bars: Sequence[Bar],
) -> str:
    return _sha256_payload(
        {
            "kind": "kis-qqq-spy-mtf-prospective-target-content-v1",
            "target_key": target_key,
            "source": source.safe_payload(),
            "session": _session_identity_payload(session, cutoff),
            "bars": [_canonical_bar_payload(bar) for bar in bars],
        }
    )


def _canonical_bar_payload(bar: Bar) -> dict[str, object]:
    return {
        "symbol": bar.symbol,
        "market": bar.market,
        "timeframe": bar.timeframe.value,
        "start_ts": _utc_marker(bar.start_ts),
        "open": str(bar.open),
        "high": str(bar.high),
        "low": str(bar.low),
        "close": str(bar.close),
        "volume": str(bar.volume),
        "complete": bar.complete,
    }


def _session_identity_payload(
    session: SessionWindow | None,
    cutoff: datetime | None,
) -> dict[str, str] | None:
    if session is None or cutoff is None:
        return None
    return {
        "open_ts": _utc_marker(session.open_ts),
        "close_ts": _utc_marker(session.close_ts),
        "cutoff": _utc_marker(cutoff),
    }


def _validate_regular_geometry(
    session: SessionWindow,
    cutoff: datetime,
    session_date: date,
) -> None:
    normalized_cutoff = require_utc(cutoff, "cutoff")
    local_open = session.open_ts.astimezone(_EASTERN)
    local_close = session.close_ts.astimezone(_EASTERN)
    expected_cutoff = datetime.combine(
        session_date,
        KIS_QQQ_SPY_MTF_PROSPECTIVE_CUTOFF,
        _EASTERN,
    ).astimezone(UTC)
    if (
        local_open.date() != session_date
        or local_close.date() != session_date
        or local_open.time() != _REGULAR_OPEN
        or local_close.time() != _REGULAR_CLOSE
        or session.duration != timedelta(hours=6, minutes=30)
        or normalized_cutoff != expected_cutoff
    ):
        raise ValueError("prospective attempt regular-session geometry is invalid")


def _attempt_store_root(*, artifact_root: Path, repo_root: Path) -> Path:
    return ensure_external_artifact_directory(
        artifact_root,
        repo_root,
        "data",
        KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ARTIFACT_DIRECTORY,
        KIS_QQQ_SPY_MTF_PROSPECTIVE_ATTEMPT_STORE_DIRECTORY,
    )


def _load_store_contract(root: Path) -> KisQqqSpyMtfProspectiveContract | None:
    path = root / "contract.json"
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise KisQqqSpyMtfProspectiveObservationError("prospective attempt store is invalid")
    return _contract_from_payload(_read_json_object(path.read_bytes(), "prospective contract"))


def _contract_from_payload(payload: Mapping[str, object]) -> KisQqqSpyMtfProspectiveContract:
    expected_keys = {
        "schema_version",
        "kind",
        "availability",
        "geometry",
        "code_revision",
        "contract_sha256",
        "scope",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("kind") != KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID
        or payload.get("geometry") != _geometry_payload()
    ):
        raise KisQqqSpyMtfProspectiveObservationError("prospective contract is invalid")
    availability_payload = payload.get("availability")
    if not isinstance(availability_payload, Mapping):
        raise KisQqqSpyMtfProspectiveObservationError("prospective contract is invalid")
    expected_availability_keys = {
        "contract_sha256",
        "receipt_sha256",
        "precommit_sha256",
        "summary_sha256",
        "historical_sources",
        "historical_exclusion_through",
    }
    if set(availability_payload) != expected_availability_keys:
        raise KisQqqSpyMtfProspectiveObservationError("prospective contract is invalid")
    sources_payload = availability_payload.get("historical_sources")
    if not isinstance(sources_payload, list):
        raise KisQqqSpyMtfProspectiveObservationError("prospective contract is invalid")
    try:
        sources = tuple(
            KisQqqSpyMtfSourceIdentity(
                target_key=str(source["target_key"]),
                dataset_id=source.get("dataset_id"),  # type: ignore[arg-type]
                dataset_hash=source.get("dataset_hash"),  # type: ignore[arg-type]
            )
            for source in sources_payload
            if isinstance(source, Mapping)
        )
        if len(sources) != len(sources_payload):
            raise ValueError
        return KisQqqSpyMtfProspectiveContract(
            availability_contract_sha256=str(availability_payload["contract_sha256"]),
            availability_receipt_sha256=str(availability_payload["receipt_sha256"]),
            availability_precommit_sha256=str(availability_payload["precommit_sha256"]),
            availability_summary_sha256=str(availability_payload["summary_sha256"]),
            historical_source_identities=sources,
            historical_exclusion_through=date.fromisoformat(
                str(availability_payload["historical_exclusion_through"])
            ),
            code_revision=str(payload["code_revision"]),
            contract_sha256=str(payload["contract_sha256"]),
            schema_version=int(payload["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise KisQqqSpyMtfProspectiveObservationError("prospective contract is invalid") from error


def _load_primary_attempts(
    root: Path,
    contract_sha256: str,
) -> dict[str, KisQqqSpyMtfProspectiveAttempt]:
    attempts_root = root / "attempts"
    if not attempts_root.exists():
        return {}
    if attempts_root.is_symlink() or not attempts_root.is_dir():
        raise KisQqqSpyMtfProspectiveObservationError("prospective attempt store is invalid")
    attempts: dict[str, KisQqqSpyMtfProspectiveAttempt] = {}
    for path in sorted(attempts_root.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise KisQqqSpyMtfProspectiveObservationError("prospective attempt store is invalid")
        attempt = _attempt_from_payload(_read_json_object(path.read_bytes(), "attempt record"))
        if attempt.contract_sha256 != contract_sha256:
            raise KisQqqSpyMtfProspectiveObservationError(
                "prospective attempt store contract conflicts"
            )
        expected_name = f"{_storage_key_fragment(attempt.session_key_sha256)}.json"
        if path.name != expected_name or attempt.session_key_sha256 in attempts:
            raise KisQqqSpyMtfProspectiveObservationError("prospective attempt store is invalid")
        attempts[attempt.session_key_sha256] = attempt
    if len(attempts) > KIS_QQQ_SPY_MTF_PROSPECTIVE_ATTEMPT_CAP:
        raise KisQqqSpyMtfProspectiveObservationError("prospective attempt cap is exceeded")
    return attempts


def _latest_record_seal(
    root: Path,
    primary_attempts: Sequence[KisQqqSpyMtfProspectiveAttempt],
    *,
    contract_sha256: str,
) -> datetime | None:
    seals = [attempt.sealed_at for attempt in primary_attempts]
    conflicts_root = root / "conflicts"
    if not conflicts_root.exists():
        return max(seals, default=None)
    if conflicts_root.is_symlink() or not conflicts_root.is_dir():
        raise KisQqqSpyMtfProspectiveObservationError("prospective conflict store is invalid")
    for path in conflicts_root.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise KisQqqSpyMtfProspectiveObservationError("prospective conflict store is invalid")
        payload = _read_json_object(path.read_bytes(), "conflict record")
        candidate_payload = payload.get("candidate")
        if (
            payload.get("kind") != "kis-qqq-spy-mtf-prospective-attempt-conflict-v1"
            or payload.get("status") != "conflict"
            or not isinstance(candidate_payload, Mapping)
        ):
            raise KisQqqSpyMtfProspectiveObservationError("prospective conflict store is invalid")
        candidate = _attempt_from_payload(candidate_payload)
        if candidate.contract_sha256 != contract_sha256:
            raise KisQqqSpyMtfProspectiveObservationError("prospective conflict store is invalid")
        seals.append(candidate.sealed_at)
    return max(seals, default=None)


def _attempt_from_payload(payload: Mapping[str, object]) -> KisQqqSpyMtfProspectiveAttempt:
    expected_keys = {
        "schema_version",
        "kind",
        "contract_sha256",
        "session",
        "sealed_at",
        "status",
        "reason",
        "targets",
        "content_commitment_sha256",
        "attempt_sha256",
        "scope",
    }
    if (
        set(payload) != expected_keys
        or payload.get("kind") != KIS_QQQ_SPY_MTF_PROSPECTIVE_OBSERVATION_ID
    ):
        raise KisQqqSpyMtfProspectiveObservationError("attempt record shape is invalid")
    session_payload = payload.get("session")
    targets_payload = payload.get("targets")
    if not isinstance(session_payload, Mapping) or not isinstance(targets_payload, list):
        raise KisQqqSpyMtfProspectiveObservationError("attempt record shape is invalid")
    try:
        session_date = date.fromisoformat(str(session_payload["date"]))
        geometry = session_payload["geometry"]
        if geometry is None:
            session = None
            cutoff = None
        elif isinstance(geometry, Mapping):
            session = SessionWindow(
                open_ts=_parse_utc_marker(geometry["open_ts"]),
                close_ts=_parse_utc_marker(geometry["close_ts"]),
            )
            cutoff = _parse_utc_marker(geometry["cutoff"])
        else:
            raise ValueError
        targets = tuple(_target_from_payload(item) for item in targets_payload)
        return KisQqqSpyMtfProspectiveAttempt(
            contract_sha256=str(payload["contract_sha256"]),
            session_date=session_date,
            session=session,
            cutoff=cutoff,
            sealed_at=_parse_utc_marker(payload["sealed_at"]),
            status=str(payload["status"]),  # type: ignore[arg-type]
            reason=str(payload["reason"]),
            targets=targets,
            session_key_sha256=str(session_payload["session_key_sha256"]),
            content_commitment_sha256=str(payload["content_commitment_sha256"]),
            attempt_sha256=str(payload["attempt_sha256"]),
            schema_version=int(payload["schema_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise KisQqqSpyMtfProspectiveObservationError("attempt record is invalid") from error


def _target_from_payload(payload: object) -> KisQqqSpyMtfTargetAttempt:
    if not isinstance(payload, Mapping) or set(payload) != {
        "source",
        "availability",
        "content_commitment_sha256",
    }:
        raise ValueError("target record is invalid")
    source_payload = payload["source"]
    if not isinstance(source_payload, Mapping):
        raise ValueError("target source is invalid")
    return KisQqqSpyMtfTargetAttempt(
        source=KisQqqSpyMtfSourceIdentity(
            target_key=str(source_payload["target_key"]),
            dataset_id=source_payload.get("dataset_id"),  # type: ignore[arg-type]
            dataset_hash=source_payload.get("dataset_hash"),  # type: ignore[arg-type]
        ),
        availability=str(payload["availability"]),  # type: ignore[arg-type]
        content_commitment_sha256=str(payload["content_commitment_sha256"]),
    )


def _count_primary_attempts(root: Path) -> int:
    try:
        return len(_load_primary_attempts(root, _contract_sha_from_store(root)))
    except (OSError, ValueError, KisQqqSpyMtfProspectiveObservationError):
        return 0


def _contract_sha_from_store(root: Path) -> str:
    payload = _read_json_object((root / "contract.json").read_bytes(), "prospective contract")
    value = payload.get("contract_sha256")
    _require_sha256(value, "prospective contract")
    return str(value)


def _conflict_sha256(
    existing: KisQqqSpyMtfProspectiveAttempt,
    candidate: KisQqqSpyMtfProspectiveAttempt,
) -> str:
    return _sha256_payload(
        {
            "kind": "kis-qqq-spy-mtf-prospective-attempt-conflict-v1",
            "existing_attempt_sha256": existing.attempt_sha256,
            "candidate_attempt_sha256": candidate.attempt_sha256,
            "existing_content_commitment_sha256": existing.content_commitment_sha256,
            "candidate_content_commitment_sha256": candidate.content_commitment_sha256,
        }
    )


def _conflict_payload(
    existing: KisQqqSpyMtfProspectiveAttempt,
    candidate: KisQqqSpyMtfProspectiveAttempt,
    conflict_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis-qqq-spy-mtf-prospective-attempt-conflict-v1",
        "status": "conflict",
        "session_key_sha256": existing.session_key_sha256,
        "existing_attempt_sha256": existing.attempt_sha256,
        "candidate_attempt_sha256": candidate.attempt_sha256,
        "existing_content_commitment_sha256": existing.content_commitment_sha256,
        "candidate_content_commitment_sha256": candidate.content_commitment_sha256,
        "conflict_sha256": conflict_sha256,
        "candidate": candidate.safe_payload(),
        "scope": {
            "model_or_strategy_result": False,
            "target_or_return_opened": False,
            "pnl_calculated": False,
            "paper_or_broker_action": False,
            "gpu_used": False,
            "raw_market_data_written": False,
            "credentials_read": False,
            "network_access": False,
        },
    }


@contextmanager
def _exclusive_store_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise BlockingIOError from error
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise BlockingIOError from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_immutable_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="ascii", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        if path.is_symlink() or path.read_text(encoding="ascii") != rendered:
            raise KisQqqSpyMtfProspectiveObservationError(
                "prospective immutable artifact conflicts"
            ) from error


def _external_regular_file(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    repository = repo_root.resolve(strict=False)
    if (
        path.is_symlink()
        or not resolved.is_file()
        or resolved.is_relative_to(repository)
    ):
        raise KisQqqSpyMtfProspectiveObservationError(
            "availability summary must stay outside Git"
        )
    return resolved


def _read_json_object(value: bytes, name: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisQqqSpyMtfProspectiveObservationError(f"{name} is invalid") from error
    if not isinstance(parsed, dict):
        raise KisQqqSpyMtfProspectiveObservationError(f"{name} is invalid")
    return parsed


def _parse_utc_marker(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("UTC marker is invalid")
    return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "UTC marker")


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(value).hexdigest()


def _storage_key_fragment(value: str) -> str:
    _require_sha256(value, "storage key")
    return value.removeprefix(_SHA256_PREFIX)[:24]


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len(_SHA256_PREFIX) + 64
        and value.startswith(_SHA256_PREFIX)
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )


def _require_sha256(value: object, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _utc_marker(value: datetime) -> str:
    return require_utc(value, "UTC marker").isoformat().replace("+00:00", "Z")

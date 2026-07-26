"""Pure offline D1 windows for one verified QQQ/SPY joint-event fold."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.kis_daily_joint_event_window_contract import (
    DEFAULT_MODEL_ARTIFACT_ROOT,
    KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE,
    KisDailyJointEventFoldInput,
    KisDailyJointEventFoldInputArtifact,
)

KIS_DAILY_JOINT_EVENT_D1_MATERIALIZER_SCHEMA_VERSION = 1
KIS_DAILY_JOINT_EVENT_D1_MATERIALIZER_KIND = "kis_daily_joint_event_d1_materializer_receipt"
KIS_DAILY_JOINT_EVENT_D1_SYMBOLS = ("QQQ", "SPY")
KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID = "kis.paper.private.daily.backfill-v1.common-panel"
KIS_DAILY_JOINT_EVENT_D1_ADJUSTMENT_MODE = "MODP=0_unadjusted"

MaterializationPhase = Literal["development", "validation"]

_ALLOWED_RECEIPT_KEYS = frozenset(
    {
        "artifact_sha256",
        "candidate_selection_eligible",
        "catalog_dataset_hash",
        "catalog_index_hash",
        "credentials_persisted",
        "decision_end",
        "decision_index",
        "decision_start",
        "eligible_decision_count",
        "eligible_decision_identity",
        "ensemble_eligible",
        "entry_index",
        "entry_start",
        "event_boundary_audit",
        "exit_index",
        "exit_start",
        "feature_end_index",
        "feature_row_count",
        "feature_start_index",
        "feature_values_persisted",
        "fold",
        "fold_id",
        "fold_input_identity",
        "joint_event_identity",
        "kind",
        "lineage",
        "mask_identity",
        "materialized_window",
        "materializer_identity",
        "model_execution_eligible",
        "model_execution_review",
        "offline_only",
        "paper_decision_eligible",
        "parent_artifact_sha256",
        "parent_contract_identity",
        "partition_identity",
        "phase",
        "predecessor_index",
        "raw_market_data_persisted",
        "schema_version",
        "scope",
        "sidecar_dataset_hash",
        "sidecar_manifest_hash",
        "source_fold_input",
        "status",
        "target_values_persisted",
    }
)


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1FeatureRow:
    """One completed D1 feature row held only in memory."""

    session_index: int
    session: date
    qqq_completed_close_return: Decimal
    spy_completed_close_return: Decimal
    qqq_minus_spy_completed_close_return: Decimal

    def __post_init__(self) -> None:
        if type(self.session_index) is not int or self.session_index < 1:
            raise ValueError("joint D1 feature row session index is invalid")
        if type(self.session) is not date:
            raise ValueError("joint D1 feature row session is invalid")
        for value in (
            self.qqq_completed_close_return,
            self.spy_completed_close_return,
            self.qqq_minus_spy_completed_close_return,
        ):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError("joint D1 feature row value is invalid")


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1TargetReferences:
    """Future D1 open references, deliberately not a cost-adjusted label."""

    entry_index: int
    exit_index: int
    entry_start: datetime
    exit_start: datetime
    entry_open_by_symbol: Mapping[str, Decimal]
    exit_open_by_symbol: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        if (
            type(self.entry_index) is not int
            or type(self.exit_index) is not int
            or self.exit_index != self.entry_index + 1
            or self.entry_start.tzinfo is None
            or self.exit_start.tzinfo is None
            or self.entry_start >= self.exit_start
        ):
            raise ValueError("joint D1 target references are invalid")
        entry = _validated_symbol_values(self.entry_open_by_symbol, "joint D1 entry references")
        exit_values = _validated_symbol_values(
            self.exit_open_by_symbol,
            "joint D1 exit references",
        )
        object.__setattr__(self, "entry_open_by_symbol", MappingProxyType(entry))
        object.__setattr__(self, "exit_open_by_symbol", MappingProxyType(exit_values))


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1Window:
    """One causal feature window plus future open references in memory only."""

    phase: MaterializationPhase
    decision_index: int
    predecessor_index: int
    feature_start_index: int
    feature_end_index: int
    decision_start: datetime
    decision_end: datetime
    feature_rows: tuple[KisDailyJointEventD1FeatureRow, ...]
    target_references: KisDailyJointEventD1TargetReferences

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_rows", tuple(self.feature_rows))
        if self.phase not in {"development", "validation"}:
            raise ValueError("joint D1 window phase is invalid")
        if (
            type(self.decision_index) is not int
            or type(self.predecessor_index) is not int
            or type(self.feature_start_index) is not int
            or type(self.feature_end_index) is not int
            or self.predecessor_index != self.feature_start_index - 1
            or self.feature_end_index != self.decision_index
            or len(self.feature_rows) != self.feature_end_index - self.feature_start_index + 1
            or self.target_references.entry_index != self.decision_index + 1
            or self.target_references.exit_index != self.decision_index + 2
            or self.decision_start.tzinfo is None
            or self.decision_end.tzinfo is None
            or self.decision_start >= self.decision_end
        ):
            raise ValueError("joint D1 window geometry is invalid")
        if tuple(row.session_index for row in self.feature_rows) != tuple(
            range(self.feature_start_index, self.feature_end_index + 1)
        ):
            raise ValueError("joint D1 window feature rows are invalid")


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1Materializer:
    """A non-executable catalog-to-window adapter for one verified fold."""

    fold_input: KisDailyJointEventFoldInput
    fold_artifact_sha256: str
    catalog_dataset_hash: str
    catalog_index_hash: str
    common_sessions: tuple[date, ...]
    bars_by_symbol: Mapping[str, tuple[Bar, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "common_sessions", tuple(self.common_sessions))
        normalized_bars = {
            symbol: tuple(bars)
            for symbol, bars in self.bars_by_symbol.items()
        }
        object.__setattr__(self, "bars_by_symbol", MappingProxyType(normalized_bars))
        _require_sha256(self.fold_artifact_sha256, "joint D1 fold artifact hash")
        _require_sha256(self.catalog_dataset_hash, "joint D1 catalog dataset hash")
        _require_sha256(self.catalog_index_hash, "joint D1 catalog index hash")
        if not isinstance(self.fold_input, KisDailyJointEventFoldInput):
            raise ValueError("joint D1 fold input is invalid")
        if (
            not self.fold_input.reattested_against_parent
            or self.fold_input.fold_id != "expanding-1"
            or self.fold_input.model_execution_review
            != KIS_DAILY_JOINT_EVENT_MODEL_EXECUTION_REVIEW_UNAVAILABLE
            or self.catalog_dataset_hash != self.fold_input.catalog_dataset_hash
            or self.catalog_index_hash != self.fold_input.catalog_index_hash
        ):
            raise ValueError("joint D1 materializer source contract is invalid")
        _validate_catalog_streams(
            sessions=self.common_sessions,
            bars_by_symbol=self.bars_by_symbol,
        )
        _validate_fold_sessions(self.fold_input, self.common_sessions)

    @property
    def materializer_identity(self) -> str:
        return _sha256_json(
            {
                "schema_version": KIS_DAILY_JOINT_EVENT_D1_MATERIALIZER_SCHEMA_VERSION,
                "kind": KIS_DAILY_JOINT_EVENT_D1_MATERIALIZER_KIND,
                "fold_artifact_sha256": self.fold_artifact_sha256,
                "fold_input_identity": self.fold_input.fold_input_identity,
                "catalog_dataset_hash": self.catalog_dataset_hash,
                "catalog_index_hash": self.catalog_index_hash,
                "session_dates_sha256": _session_dates_hash(self.common_sessions),
            }
        )

    def eligible_decision_indices(self, phase: MaterializationPhase) -> tuple[int, ...]:
        if phase == "development":
            return self.fold_input.development_eligible_decision_indices
        if phase == "validation":
            return self.fold_input.validation_eligible_decision_indices
        raise ValueError("joint D1 materializer phase is invalid")

    def materialize(
        self,
        *,
        phase: MaterializationPhase,
        decision_index: int,
    ) -> KisDailyJointEventD1Window:
        if type(decision_index) is not int:
            raise ValueError("joint D1 decision index is invalid")
        if decision_index not in self.eligible_decision_indices(phase):
            raise ValueError("joint D1 decision index is not sparse-eligible for this phase")
        phase_start, phase_end = _phase_bounds(self.fold_input, phase)
        predecessor_index = decision_index - self.fold_input.spec.feature_session_count
        feature_start_index = predecessor_index + 1
        feature_end_index = decision_index
        entry_index = decision_index + 1
        exit_index = decision_index + self.fold_input.spec.label_horizon_session_count
        if (
            predecessor_index < phase_start
            or exit_index >= phase_end
            or feature_end_index != decision_index
            or exit_index != entry_index + 1
        ):
            raise ValueError("joint D1 window crosses its phase boundary")

        qqq_bars = self.bars_by_symbol["QQQ"]
        spy_bars = self.bars_by_symbol["SPY"]
        feature_rows = tuple(
            _feature_row(
                session_index=index,
                session=self.common_sessions[index],
                qqq_current=qqq_bars[index],
                qqq_prior=qqq_bars[index - 1],
                spy_current=spy_bars[index],
                spy_prior=spy_bars[index - 1],
            )
            for index in range(feature_start_index, feature_end_index + 1)
        )
        decision_bar = qqq_bars[decision_index]
        entry_bars = {
            symbol: self.bars_by_symbol[symbol][entry_index]
            for symbol in KIS_DAILY_JOINT_EVENT_D1_SYMBOLS
        }
        exit_bars = {
            symbol: self.bars_by_symbol[symbol][exit_index]
            for symbol in KIS_DAILY_JOINT_EVENT_D1_SYMBOLS
        }
        return KisDailyJointEventD1Window(
            phase=phase,
            decision_index=decision_index,
            predecessor_index=predecessor_index,
            feature_start_index=feature_start_index,
            feature_end_index=feature_end_index,
            decision_start=decision_bar.start_ts,
            decision_end=decision_bar.end_ts,
            feature_rows=feature_rows,
            target_references=KisDailyJointEventD1TargetReferences(
                entry_index=entry_index,
                exit_index=exit_index,
                entry_start=entry_bars["QQQ"].start_ts,
                exit_start=exit_bars["QQQ"].start_ts,
                entry_open_by_symbol={symbol: bar.open for symbol, bar in entry_bars.items()},
                exit_open_by_symbol={symbol: bar.open for symbol, bar in exit_bars.items()},
            ),
        )

    def receipt_document(
        self,
        *,
        phase: MaterializationPhase,
        decision_index: int,
    ) -> dict[str, object]:
        window = self.materialize(phase=phase, decision_index=decision_index)
        eligible_indices = self.eligible_decision_indices(phase)
        document = {
            "schema_version": KIS_DAILY_JOINT_EVENT_D1_MATERIALIZER_SCHEMA_VERSION,
            "kind": KIS_DAILY_JOINT_EVENT_D1_MATERIALIZER_KIND,
            "status": "candidate",
            "source_fold_input": {
                "artifact_sha256": self.fold_artifact_sha256,
                "fold_input_identity": self.fold_input.fold_input_identity,
                "parent_artifact_sha256": self.fold_input.source_artifact_sha256,
                "parent_contract_identity": self.fold_input.source_contract_identity,
            },
            "lineage": {
                "catalog_dataset_hash": self.catalog_dataset_hash,
                "catalog_index_hash": self.catalog_index_hash,
                "sidecar_dataset_hash": self.fold_input.sidecar_dataset_hash,
                "sidecar_manifest_hash": self.fold_input.sidecar_manifest_hash,
            },
            "event_boundary_audit": {
                "artifact_sha256": self.fold_input.event_boundary_audit_sha256,
                "mask_identity": self.fold_input.event_boundary_mask_identity,
                "partition_identity": self.fold_input.event_boundary_partition_identity,
                "joint_event_identity": self.fold_input.joint_event_identity,
            },
            "fold": {
                "fold_id": self.fold_input.fold_id,
                "phase": phase,
                "eligible_decision_count": len(eligible_indices),
                "eligible_decision_identity": _phase_eligibility_identity(
                    self.fold_input,
                    phase,
                ),
            },
            "materialized_window": {
                "decision_index": window.decision_index,
                "predecessor_index": window.predecessor_index,
                "feature_start_index": window.feature_start_index,
                "feature_end_index": window.feature_end_index,
                "entry_index": window.target_references.entry_index,
                "exit_index": window.target_references.exit_index,
                "feature_row_count": len(window.feature_rows),
                "decision_start": window.decision_start.isoformat(),
                "decision_end": window.decision_end.isoformat(),
                "entry_start": window.target_references.entry_start.isoformat(),
                "exit_start": window.target_references.exit_start.isoformat(),
            },
            "scope": {
                "offline_only": True,
                "model_execution_eligible": False,
                "model_execution_review": self.fold_input.model_execution_review,
                "candidate_selection_eligible": False,
                "ensemble_eligible": False,
                "paper_decision_eligible": False,
                "raw_market_data_persisted": False,
                "feature_values_persisted": False,
                "target_values_persisted": False,
                "credentials_persisted": False,
            },
            "materializer_identity": self.materializer_identity,
        }
        _assert_source_safe(document)
        return document


@dataclass(frozen=True, slots=True)
class KisDailyJointEventD1MaterializerReceipt:
    path: Path
    content_hash: str
    materializer: KisDailyJointEventD1Materializer
    phase: MaterializationPhase
    decision_index: int


def build_kis_daily_joint_event_d1_materializer(
    *,
    fold_input_artifact: KisDailyJointEventFoldInputArtifact,
    catalog: object,
) -> KisDailyJointEventD1Materializer:
    """Bind one verified index-only fold to a matching local QQQ/SPY catalog."""

    if not isinstance(fold_input_artifact, KisDailyJointEventFoldInputArtifact):
        raise ValueError("joint D1 fold artifact is invalid")
    if not fold_input_artifact.reattested_against_parent:
        raise ValueError("joint D1 fold artifact must be reattested before materialization")
    input_contract = fold_input_artifact.fold_input
    if not input_contract.reattested_against_parent:
        raise ValueError("joint D1 fold input must be reattested before materialization")
    catalog_values = _validated_catalog_values(catalog)
    return KisDailyJointEventD1Materializer(
        fold_input=input_contract,
        fold_artifact_sha256=fold_input_artifact.content_hash,
        catalog_dataset_hash=catalog_values.dataset_hash,
        catalog_index_hash=catalog_values.index_hash,
        common_sessions=catalog_values.common_sessions,
        bars_by_symbol=catalog_values.bars_by_symbol,
    )


def write_kis_daily_joint_event_d1_materializer_receipt(
    *,
    destination: Path,
    materializer: KisDailyJointEventD1Materializer,
    phase: MaterializationPhase,
    decision_index: int,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path,
) -> KisDailyJointEventD1MaterializerReceipt:
    """Write a source-safe receipt after materializing one in-memory window."""

    if not isinstance(materializer, KisDailyJointEventD1Materializer):
        raise ValueError("joint D1 materializer is invalid")
    path = _external_artifact_destination(
        destination=destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    document = materializer.receipt_document(phase=phase, decision_index=decision_index)
    encoded = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    content_hash = _sha256(encoded)
    with path.open("xb") as handle:
        handle.write(encoded)
    return KisDailyJointEventD1MaterializerReceipt(
        path=path,
        content_hash=content_hash,
        materializer=materializer,
        phase=phase,
        decision_index=decision_index,
    )


@dataclass(frozen=True, slots=True)
class _CatalogValues:
    dataset_hash: str
    index_hash: str
    common_sessions: tuple[date, ...]
    bars_by_symbol: Mapping[str, tuple[Bar, ...]]


def _validated_catalog_values(catalog: object) -> _CatalogValues:
    catalog_id = getattr(catalog, "dataset_id", None)
    if (
        catalog_id != KIS_DAILY_JOINT_EVENT_D1_CATALOG_ID
        or getattr(catalog, "adjustment_mode", None) != KIS_DAILY_JOINT_EVENT_D1_ADJUSTMENT_MODE
    ):
        raise ValueError("joint D1 catalog source contract is invalid")
    dataset_hash = getattr(catalog, "dataset_hash", None)
    index_hash = getattr(catalog, "index_hash", None)
    _require_sha256(dataset_hash, "joint D1 catalog dataset hash")
    _require_sha256(index_hash, "joint D1 catalog index hash")
    sessions = getattr(catalog, "common_sessions", None)
    streams = getattr(catalog, "bars_by_symbol", None)
    if (
        not isinstance(sessions, tuple)
        or any(type(session) is not date for session in sessions)
        or tuple(sorted(sessions)) != sessions
        or len(set(sessions)) != len(sessions)
        or not isinstance(streams, Mapping)
        or tuple(streams) != KIS_DAILY_JOINT_EVENT_D1_SYMBOLS
    ):
        raise ValueError("joint D1 catalog source contract is invalid")
    bars_by_symbol: dict[str, tuple[Bar, ...]] = {}
    for symbol in KIS_DAILY_JOINT_EVENT_D1_SYMBOLS:
        stream = streams[symbol]
        bars = getattr(stream, "bars", None)
        if (
            getattr(stream, "dataset_id", None) != catalog_id
            or getattr(stream, "dataset_hash", None) != dataset_hash
            or not isinstance(bars, tuple)
        ):
            raise ValueError("joint D1 catalog stream is invalid")
        bars_by_symbol[symbol] = bars
    return _CatalogValues(
        dataset_hash=dataset_hash,
        index_hash=index_hash,
        common_sessions=sessions,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
    )


def _validate_catalog_streams(
    *,
    sessions: tuple[date, ...],
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
) -> None:
    if tuple(bars_by_symbol) != KIS_DAILY_JOINT_EVENT_D1_SYMBOLS:
        raise ValueError("joint D1 catalog symbols are invalid")
    for symbol in KIS_DAILY_JOINT_EVENT_D1_SYMBOLS:
        bars = bars_by_symbol[symbol]
        if (
            len(bars) != len(sessions)
            or any(
                not isinstance(bar, Bar)
                or bar.symbol != symbol
                or bar.market != "US"
                or bar.timeframe != Timeframe.D1
                or not bar.complete
                for bar in bars
            )
            or tuple(bar.start_ts.date() for bar in bars) != sessions
        ):
            raise ValueError("joint D1 catalog streams are incompatible")


def _validate_fold_sessions(
    fold_input: KisDailyJointEventFoldInput,
    sessions: tuple[date, ...],
) -> None:
    if fold_input.validation_end_index > len(sessions):
        raise ValueError("joint D1 catalog is shorter than its fold input")
    expected = (
        (fold_input.development_start_index, fold_input.development_start_session),
        (fold_input.development_end_index - 1, fold_input.development_end_session),
        (fold_input.pre_validation_gap_start_index, fold_input.pre_validation_gap_start_session),
        (fold_input.pre_validation_gap_end_index - 1, fold_input.pre_validation_gap_end_session),
        (fold_input.validation_start_index, fold_input.validation_start_session),
        (fold_input.validation_end_index - 1, fold_input.validation_end_session),
    )
    if any(sessions[index] != session for index, session in expected):
        raise ValueError("joint D1 catalog sessions do not match the fold input")


def _phase_bounds(
    fold_input: KisDailyJointEventFoldInput,
    phase: MaterializationPhase,
) -> tuple[int, int]:
    if phase == "development":
        return fold_input.development_start_index, fold_input.development_end_index
    if phase == "validation":
        return fold_input.validation_start_index, fold_input.validation_end_index
    raise ValueError("joint D1 materializer phase is invalid")


def _phase_eligibility_identity(
    fold_input: KisDailyJointEventFoldInput,
    phase: MaterializationPhase,
) -> str:
    if phase == "development":
        return fold_input.development_eligible_decision_identity
    if phase == "validation":
        return fold_input.validation_eligible_decision_identity
    raise ValueError("joint D1 materializer phase is invalid")


def _feature_row(
    *,
    session_index: int,
    session: date,
    qqq_current: Bar,
    qqq_prior: Bar,
    spy_current: Bar,
    spy_prior: Bar,
) -> KisDailyJointEventD1FeatureRow:
    qqq_return = _completed_close_return(qqq_current, qqq_prior)
    spy_return = _completed_close_return(spy_current, spy_prior)
    return KisDailyJointEventD1FeatureRow(
        session_index=session_index,
        session=session,
        qqq_completed_close_return=qqq_return,
        spy_completed_close_return=spy_return,
        qqq_minus_spy_completed_close_return=qqq_return - spy_return,
    )


def _completed_close_return(current: Bar, prior: Bar) -> Decimal:
    if (
        current.end_ts <= prior.end_ts
        or current.close <= 0
        or prior.close <= 0
        or not current.complete
        or not prior.complete
    ):
        raise ValueError("joint D1 completed close return is invalid")
    return current.close / prior.close - Decimal("1")


def _validated_symbol_values(values: Mapping[str, Decimal], label: str) -> dict[str, Decimal]:
    if not isinstance(values, Mapping) or tuple(values) != KIS_DAILY_JOINT_EVENT_D1_SYMBOLS:
        raise ValueError(f"{label} are invalid")
    normalized: dict[str, Decimal] = {}
    for symbol in KIS_DAILY_JOINT_EVENT_D1_SYMBOLS:
        value = values[symbol]
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError(f"{label} are invalid")
        normalized[symbol] = value
    return normalized


def _external_artifact_destination(
    *,
    destination: Path,
    artifact_root: Path,
    repo_root: Path,
) -> Path:
    resolved_repo = Path(repo_root).resolve()
    resolved_root = Path(artifact_root).resolve()
    if resolved_root == resolved_repo or resolved_root.is_relative_to(resolved_repo):
        raise ValueError("joint D1 artifacts must stay outside the Git workspace")
    destination_path = Path(destination)
    if destination_path.is_symlink():
        raise ValueError("joint D1 artifact destination is invalid")
    resolved_destination = destination_path.resolve()
    if not resolved_destination.is_relative_to(resolved_root):
        raise ValueError("joint D1 artifact must stay under the artifact root")
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    if not resolved_destination.parent.resolve().is_relative_to(resolved_root):
        raise ValueError("joint D1 artifact destination is invalid")
    return resolved_destination


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key not in _ALLOWED_RECEIPT_KEYS:
                raise ValueError(f"joint D1 receipt key is not source-safe: {key}")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{label} must use the sha256 prefix")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise ValueError(f"{label} must contain a SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as error:
        raise ValueError(f"{label} must contain a SHA-256 digest") from error
    return value


def _session_dates_hash(sessions: tuple[date, ...]) -> str:
    return _sha256("\n".join(session.isoformat() for session in sessions).encode("utf-8"))


def _sha256_json(value: object) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()

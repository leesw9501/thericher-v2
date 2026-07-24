"""Retrospective-only event masks for KIS QQQ/SPY daily return labels."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from thericher_v2.data.kis_daily_corporate_actions import (
    KIS_DAILY_CORPORATE_ACTION_SYMBOLS,
    KisDailyCorporateActionSnapshot,
    kis_daily_session_dates_hash,
)
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog

DEFAULT_MODEL_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
KIS_DAILY_EVENT_MASK_CONTRACT_SCHEMA_VERSION = 1
KIS_DAILY_EVENT_MASK_CONTRACT_KIND = "kis_daily_event_mask_contract"
KIS_DAILY_EVENT_BOUNDARY_AUDIT_SCHEMA_VERSION = 1
KIS_DAILY_EVENT_BOUNDARY_AUDIT_KIND = "kis_daily_event_boundary_audit"
KIS_DAILY_EVENT_BOUNDARY_RESIDUAL_THRESHOLD = Decimal("0.20")
_BOUNDARY_PARTITION_POLICY = "fixed_60_20_20_with_one_session_purge_and_embargo_v1"
_BOUNDARY_PARTITION_NAMES = (
    "development",
    "purge",
    "validation",
    "embargo",
    "untouched_tail",
)
_SCOPE = {
    "retrospective_price_return_label_integrity_only": True,
    "point_in_time_feature_eligible": False,
    "model_training_eligible": False,
    "paper_decision_eligible": False,
    "price_data_consumed": False,
}


@dataclass(frozen=True, slots=True)
class KisDailyEventMaskedPair:
    """One chronological t-to-t+1 pair excluded from price-return labels."""

    symbol: str
    start_session: date
    end_session: date
    event_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class KisDailyEventMaskContract:
    """A frozen source contract; it cannot score, train, or route an order."""

    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    sessions: tuple[date, ...]
    excluded_pairs: Mapping[str, tuple[KisDailyEventMaskedPair, ...]]

    def document(self) -> dict[str, object]:
        return {
            "schema_version": KIS_DAILY_EVENT_MASK_CONTRACT_SCHEMA_VERSION,
            "kind": KIS_DAILY_EVENT_MASK_CONTRACT_KIND,
            "catalog_dataset_hash": self.catalog_dataset_hash,
            "catalog_index_hash": self.catalog_index_hash,
            "sidecar_dataset_hash": self.sidecar_dataset_hash,
            "sidecar_manifest_hash": self.sidecar_manifest_hash,
            "session_dates_sha256": kis_daily_session_dates_hash(self.sessions),
            "session_count": len(self.sessions),
            "scope": dict(_SCOPE),
            "exclusion_rule": "exclude_t_to_t_plus_1_when_either_endpoint_is_an_event_date",
            "excluded_pairs": [
                {
                    "symbol": pair.symbol,
                    "start_session": pair.start_session.isoformat(),
                    "end_session": pair.end_session.isoformat(),
                    "event_dates": [event_date.isoformat() for event_date in pair.event_dates],
                }
                for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
                for pair in self.excluded_pairs[symbol]
            ],
        }


@dataclass(frozen=True, slots=True)
class KisDailyEventMaskContractArtifact:
    path: Path
    content_hash: str
    contract: KisDailyEventMaskContract


@dataclass(frozen=True, slots=True)
class KisDailyBoundaryMaskedPair:
    """One daily pair excluded without retaining either price or return."""

    symbol: str
    start_session: date
    end_session: date
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryPartition:
    """One frozen chronological source region for future common comparators."""

    name: str
    start_session: date
    end_session: date
    session_count: int


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryAudit:
    """A retrospective, price-free audit of buffered event-boundary geometry."""

    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    created_at_utc: datetime
    residual_threshold: Decimal
    status: str
    unqualified_reasons: tuple[str, ...]
    sessions: tuple[date, ...]
    partitions: tuple[KisDailyEventBoundaryPartition, ...]
    masked_pairs: Mapping[str, tuple[KisDailyBoundaryMaskedPair, ...]]
    audit_counts: Mapping[str, Mapping[str, int]]

    def mask_identity(self) -> str:
        return _sha256_json(
            [
                {
                    "symbol": pair.symbol,
                    "start_session": pair.start_session.isoformat(),
                    "end_session": pair.end_session.isoformat(),
                    "reasons": list(pair.reasons),
                }
                for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
                for pair in self.masked_pairs[symbol]
            ]
        )

    def partition_identity(self) -> str:
        return _sha256_json(
            [
                {
                    "name": partition.name,
                    "start_session": partition.start_session.isoformat(),
                    "end_session": partition.end_session.isoformat(),
                    "session_count": partition.session_count,
                }
                for partition in self.partitions
            ]
        )

    def document(self) -> dict[str, object]:
        return {
            "schema_version": KIS_DAILY_EVENT_BOUNDARY_AUDIT_SCHEMA_VERSION,
            "kind": KIS_DAILY_EVENT_BOUNDARY_AUDIT_KIND,
            "created_at_utc": _format_utc(self.created_at_utc),
            "status": self.status,
            "unqualified_reasons": list(self.unqualified_reasons),
            "catalog_dataset_hash": self.catalog_dataset_hash,
            "catalog_index_hash": self.catalog_index_hash,
            "sidecar_dataset_hash": self.sidecar_dataset_hash,
            "sidecar_manifest_hash": self.sidecar_manifest_hash,
            "session_dates_sha256": kis_daily_session_dates_hash(self.sessions),
            "residual_threshold_absolute_return": format(self.residual_threshold, "f"),
            "residual_policy": "inspect_unmasked_pairs_in_memory_only_no_return_values_persisted",
            "event_buffer_policy": (
                "exclude_pairs_when_either_endpoint_is_event_or_adjacent_session"
            ),
            "partition_policy": _BOUNDARY_PARTITION_POLICY,
            "partition_identity": self.partition_identity(),
            "mask_identity": self.mask_identity(),
            "scope": {
                "retrospective_price_return_label_integrity_only": True,
                "point_in_time_feature_eligible": False,
                "model_training_eligible": False,
                "paper_decision_eligible": False,
                "total_return_eligible": False,
                "baseline_eligible": False,
                "raw_price_data_consumed_in_memory_only": True,
                "raw_prices_or_returns_persisted": False,
            },
            "partitions": [
                {
                    "name": partition.name,
                    "start_session": partition.start_session.isoformat(),
                    "end_session": partition.end_session.isoformat(),
                    "session_count": partition.session_count,
                }
                for partition in self.partitions
            ],
            "audit_counts": {
                symbol: dict(self.audit_counts[symbol])
                for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
            },
            "masked_pairs": [
                {
                    "symbol": pair.symbol,
                    "start_session": pair.start_session.isoformat(),
                    "end_session": pair.end_session.isoformat(),
                    "reasons": list(pair.reasons),
                }
                for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
                for pair in self.masked_pairs[symbol]
            ],
            "future_comparator_requirement": (
                "use_exact_mask_identity_and_partition_identity_without_recomputing_or_tuning"
            ),
        }


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryAuditArtifact:
    path: Path
    content_hash: str
    audit: KisDailyEventBoundaryAudit


def build_kis_daily_event_mask_contract(
    *,
    catalog: KisPaperPrivateDailyCatalog,
    sidecar: KisDailyCorporateActionSnapshot,
) -> KisDailyEventMaskContract:
    """Build only the conservative label-exclusion geometry from event dates."""

    sessions = _validated_event_contract_inputs(catalog=catalog, sidecar=sidecar)
    event_dates = {
        symbol: frozenset(
            event.mapped_kis_session_date for event in sidecar.events if event.symbol == symbol
        )
        for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
    }
    excluded: dict[str, tuple[KisDailyEventMaskedPair, ...]] = {}
    for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        pairs: list[KisDailyEventMaskedPair] = []
        for start_session, end_session in zip(sessions[:-1], sessions[1:], strict=True):
            matched = tuple(sorted({start_session, end_session}.intersection(event_dates[symbol])))
            if matched:
                pairs.append(
                    KisDailyEventMaskedPair(
                        symbol=symbol,
                        start_session=start_session,
                        end_session=end_session,
                        event_dates=matched,
                    )
                )
        if not pairs:
            raise ValueError(f"KIS daily event-mask has no excluded pairs for {symbol}")
        excluded[symbol] = tuple(pairs)
    return KisDailyEventMaskContract(
        catalog_dataset_hash=catalog.dataset_hash,
        catalog_index_hash=catalog.index_hash,
        sidecar_dataset_hash=sidecar.dataset_hash,
        sidecar_manifest_hash=sidecar.manifest_hash,
        sessions=sessions,
        excluded_pairs=MappingProxyType(excluded),
    )


def build_kis_daily_event_boundary_audit(
    *,
    catalog: KisPaperPrivateDailyCatalog,
    sidecar: KisDailyCorporateActionSnapshot,
    created_at_utc: datetime,
    residual_threshold: Decimal = KIS_DAILY_EVENT_BOUNDARY_RESIDUAL_THRESHOLD,
) -> KisDailyEventBoundaryAudit:
    """Freeze a buffered event mask and inspect only categorical residual counts."""

    sessions = _validated_event_contract_inputs(
        catalog=catalog,
        sidecar=sidecar,
        minimum_sessions=16,
    )
    created_at = _require_utc(created_at_utc, "created_at_utc")
    threshold = _positive_threshold(residual_threshold)
    partitions = _frozen_partitions(sessions)
    partition_by_session = _partition_by_session(sessions=sessions, partitions=partitions)
    event_dates = {
        symbol: tuple(
            sorted(
                event.mapped_kis_session_date for event in sidecar.events if event.symbol == symbol
            )
        )
        for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
    }
    index_by_session = {session: index for index, session in enumerate(sessions)}
    masked_pairs: dict[str, tuple[KisDailyBoundaryMaskedPair, ...]] = {}
    counts: dict[str, Mapping[str, int]] = {}
    reasons: set[str] = set()
    for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        indices = tuple(index_by_session.get(event_date, -1) for event_date in event_dates[symbol])
        if any(index < 0 for index in indices):
            reasons.add(f"event_not_in_common_sessions:{symbol}")
        if not indices:
            reasons.add(f"event_missing:{symbol}")
        interior = tuple(index for index in indices if 0 < index < len(sessions) - 1)
        if len(interior) != len(indices):
            reasons.add(f"event_neighbor_missing:{symbol}")
        buffered_sessions = frozenset(
            sessions[neighbor]
            for index in interior
            for neighbor in (index - 1, index, index + 1)
        )
        pairs: list[KisDailyBoundaryMaskedPair] = []
        residual_pairs_examined = 0
        residual_exceedances = 0
        event_boundary_pairs = 0
        bars = catalog.bars_by_symbol[symbol].bars
        if len(bars) != len(sessions) or tuple(bar.start_ts.date() for bar in bars) != sessions:
            raise ValueError("KIS daily event-boundary catalog stream is incompatible")
        for index, (start_session, end_session) in enumerate(
            zip(sessions[:-1], sessions[1:], strict=True)
        ):
            pair_reasons: list[str] = []
            if start_session in buffered_sessions or end_session in buffered_sessions:
                pair_reasons.append("event_buffer")
            if (
                partition_by_session[start_session] != partition_by_session[end_session]
                or partition_by_session[start_session] in {"purge", "embargo"}
                or partition_by_session[end_session] in {"purge", "embargo"}
            ):
                pair_reasons.append("chronological_boundary")
            if start_session in event_dates[symbol] or end_session in event_dates[symbol]:
                event_boundary_pairs += 1
            if pair_reasons:
                pairs.append(
                    KisDailyBoundaryMaskedPair(
                        symbol=symbol,
                        start_session=start_session,
                        end_session=end_session,
                        reasons=tuple(pair_reasons),
                    )
                )
                continue
            residual_pairs_examined += 1
            if _absolute_return_exceeds(
                earlier=bars[index].close,
                later=bars[index + 1].close,
                threshold=threshold,
            ):
                residual_exceedances += 1
        if residual_exceedances:
            reasons.add(f"unmasked_residual_exceeds_threshold:{symbol}")
        masked_pairs[symbol] = tuple(pairs)
        counts[symbol] = MappingProxyType(
            {
                "event_count": len(event_dates[symbol]),
                "mapped_event_count": len(indices) - sum(index < 0 for index in indices),
                "interior_event_count": len(interior),
                "buffered_session_count": len(buffered_sessions),
                "event_boundary_pair_count": event_boundary_pairs,
                "masked_pair_count": len(pairs),
                "unmasked_residual_pairs_examined": residual_pairs_examined,
                "unmasked_residual_exceedance_count": residual_exceedances,
            }
        )
    return KisDailyEventBoundaryAudit(
        catalog_dataset_hash=catalog.dataset_hash,
        catalog_index_hash=catalog.index_hash,
        sidecar_dataset_hash=sidecar.dataset_hash,
        sidecar_manifest_hash=sidecar.manifest_hash,
        created_at_utc=created_at,
        residual_threshold=threshold,
        status="qualified" if not reasons else "unqualified",
        unqualified_reasons=tuple(sorted(reasons)),
        sessions=sessions,
        partitions=partitions,
        masked_pairs=MappingProxyType(masked_pairs),
        audit_counts=MappingProxyType(counts),
    )


def write_kis_daily_event_mask_contract(
    *,
    destination: Path,
    contract: KisDailyEventMaskContract,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path | None = None,
) -> KisDailyEventMaskContractArtifact:
    """Write one immutable, price-free receipt outside the repository."""

    if not isinstance(contract, KisDailyEventMaskContract):
        raise ValueError("KIS daily event-mask contract is invalid")
    path, content_hash = _write_json_artifact(
        destination=destination,
        document=contract.document(),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return KisDailyEventMaskContractArtifact(
        path=path,
        content_hash=content_hash,
        contract=contract,
    )


def write_kis_daily_event_boundary_audit(
    *,
    destination: Path,
    audit: KisDailyEventBoundaryAudit,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    repo_root: Path | None = None,
) -> KisDailyEventBoundaryAuditArtifact:
    """Write one immutable audit artifact without raw prices or returns."""

    if not isinstance(audit, KisDailyEventBoundaryAudit):
        raise ValueError("KIS daily event-boundary audit is invalid")
    path, content_hash = _write_json_artifact(
        destination=destination,
        document=audit.document(),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    return KisDailyEventBoundaryAuditArtifact(
        path=path,
        content_hash=content_hash,
        audit=audit,
    )


def _validated_event_contract_inputs(
    *,
    catalog: KisPaperPrivateDailyCatalog,
    sidecar: KisDailyCorporateActionSnapshot,
    minimum_sessions: int = 2,
) -> tuple[date, ...]:
    if not isinstance(catalog, KisPaperPrivateDailyCatalog):
        raise ValueError("KIS daily event-mask catalog is invalid")
    if not isinstance(sidecar, KisDailyCorporateActionSnapshot):
        raise ValueError("KIS daily event-mask sidecar is invalid")
    if (
        sidecar.catalog_dataset_hash != catalog.dataset_hash
        or sidecar.catalog_index_hash != catalog.index_hash
    ):
        raise ValueError("KIS daily event-mask sidecar lineage is incompatible")
    sessions = tuple(catalog.common_sessions)
    if (
        len(sessions) < minimum_sessions
        or tuple(sorted(sessions)) != sessions
        or len(set(sessions)) != len(sessions)
    ):
        raise ValueError("KIS daily event-mask sessions are invalid")
    return sessions


def _frozen_partitions(sessions: tuple[date, ...]) -> tuple[KisDailyEventBoundaryPartition, ...]:
    development_count = len(sessions) * 3 // 5
    validation_count = len(sessions) // 5
    bounds = (
        ("development", 0, development_count),
        ("purge", development_count, development_count + 1),
        ("validation", development_count + 1, development_count + 1 + validation_count),
        (
            "embargo",
            development_count + 1 + validation_count,
            development_count + 2 + validation_count,
        ),
        ("untouched_tail", development_count + 2 + validation_count, len(sessions)),
    )
    if any(stop <= start for _name, start, stop in bounds):
        raise ValueError("KIS daily event-boundary partitions are invalid")
    partitions = tuple(
        KisDailyEventBoundaryPartition(
            name=name,
            start_session=sessions[start],
            end_session=sessions[stop - 1],
            session_count=stop - start,
        )
        for name, start, stop in bounds
    )
    if tuple(partition.name for partition in partitions) != _BOUNDARY_PARTITION_NAMES:
        raise ValueError("KIS daily event-boundary partitions are invalid")
    return partitions


def _partition_by_session(
    *,
    sessions: tuple[date, ...],
    partitions: tuple[KisDailyEventBoundaryPartition, ...],
) -> Mapping[date, str]:
    assigned: dict[date, str] = {}
    cursor = 0
    for partition in partitions:
        selected = sessions[cursor : cursor + partition.session_count]
        if (
            not selected
            or selected[0] != partition.start_session
            or selected[-1] != partition.end_session
        ):
            raise ValueError("KIS daily event-boundary partitions are invalid")
        assigned.update({session: partition.name for session in selected})
        cursor += partition.session_count
    if cursor != len(sessions) or len(assigned) != len(sessions):
        raise ValueError("KIS daily event-boundary partitions are invalid")
    return MappingProxyType(assigned)


def _absolute_return_exceeds(*, earlier: Decimal, later: Decimal, threshold: Decimal) -> bool:
    if earlier <= 0 or later <= 0:
        raise ValueError("KIS daily event-boundary input close is invalid")
    return abs(later / earlier - Decimal("1")) >= threshold


def _positive_threshold(value: Decimal) -> Decimal:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or not Decimal("0") < value < Decimal("1")
    ):
        raise ValueError("KIS daily event-boundary residual threshold is invalid")
    return value


def _require_utc(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError(f"KIS daily event-boundary {label} must be UTC")
    return value


def _format_utc(value: datetime) -> str:
    return _require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json_artifact(
    *,
    destination: Path,
    document: Mapping[str, object],
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, str]:
    root = Path(artifact_root).resolve(strict=False)
    requested = Path(destination)
    resolved = requested.resolve(strict=False)
    if requested.exists() or requested.is_symlink():
        raise FileExistsError("KIS daily research artifact destination already exists")
    if resolved.suffix != ".json" or not resolved.is_relative_to(root):
        raise ValueError("KIS daily research artifact destination must be a JSON artifact")
    _assert_external_artifact(resolved, repo_root=repo_root)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    requested.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=requested.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, requested)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return requested.resolve(), "sha256:" + hashlib.sha256(payload).hexdigest()


def _assert_external_artifact(path: Path, *, repo_root: Path | None) -> None:
    if repo_root is not None:
        repository = Path(repo_root).resolve(strict=False)
        docker_artifacts = Path("/app/model_artifacts").resolve()
        if path == repository or path.is_relative_to(repository):
            if repository != Path("/app").resolve() or not path.is_relative_to(docker_artifacts):
                raise ValueError("KIS daily research artifact must stay outside Git")
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("KIS daily research artifact must stay outside Git")

"""Offline verifier for the frozen QQQ/SPY daily event-boundary audit."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType

KIS_DAILY_EVENT_BOUNDARY_AUDIT_KIND = "kis_daily_event_boundary_audit"
KIS_DAILY_EVENT_BOUNDARY_AUDIT_SCHEMA_VERSION = 1
KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS = ("QQQ", "SPY")
KIS_DAILY_EVENT_BOUNDARY_AUDIT_PARTITIONS = (
    "development",
    "purge",
    "validation",
    "embargo",
    "untouched_tail",
)

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "created_at_utc",
        "status",
        "unqualified_reasons",
        "catalog_dataset_hash",
        "catalog_index_hash",
        "sidecar_dataset_hash",
        "sidecar_manifest_hash",
        "session_dates_sha256",
        "residual_threshold_absolute_return",
        "residual_policy",
        "event_buffer_policy",
        "partition_policy",
        "partition_identity",
        "mask_identity",
        "scope",
        "partitions",
        "audit_counts",
        "masked_pairs",
        "future_comparator_requirement",
    }
)
_SCOPE = {
    "retrospective_price_return_label_integrity_only": True,
    "point_in_time_feature_eligible": False,
    "model_training_eligible": False,
    "paper_decision_eligible": False,
    "total_return_eligible": False,
    "baseline_eligible": False,
    "raw_price_data_consumed_in_memory_only": True,
    "raw_prices_or_returns_persisted": False,
}
_PARTITION_POLICY = "fixed_60_20_20_with_one_session_purge_and_embargo_v1"
_PARTITION_KEYS = frozenset({"name", "start_session", "end_session", "session_count"})
_MASKED_PAIR_KEYS = frozenset({"symbol", "start_session", "end_session", "reasons"})
_AUDIT_COUNT_KEYS = frozenset(
    {
        "event_count",
        "mapped_event_count",
        "interior_event_count",
        "buffered_session_count",
        "event_boundary_pair_count",
        "masked_pair_count",
        "unmasked_residual_pairs_examined",
        "unmasked_residual_exceedance_count",
    }
)
_ALLOWED_PAIR_REASONS = (
    ("event_buffer",),
    ("chronological_boundary",),
    ("event_buffer", "chronological_boundary"),
)
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
        "rawprice",
        "rawprices",
        "return",
        "returns",
        "barreturn",
        "barreturns",
        "perbarreturn",
        "perbarreturns",
        "dailyreturn",
        "dailyreturns",
        "residualreturn",
        "residualreturns",
    }
)
_ALLOWED_PRICE_OR_RETURN_METADATA_KEYS = frozenset(
    {
        "retrospective_price_return_label_integrity_only",
        "residual_threshold_absolute_return",
        "residual_policy",
        "raw_price_data_consumed_in_memory_only",
        "raw_prices_or_returns_persisted",
        "total_return_eligible",
    }
)


class KisDailyEventBoundaryAuditError(ValueError):
    """Fail-closed error for a frozen daily audit artifact."""


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryAuditLineage:
    """Hash-pinned KIS catalog and corporate-action sidecar lineage."""

    catalog_dataset_hash: str
    catalog_index_hash: str
    sidecar_dataset_hash: str
    sidecar_manifest_hash: str
    session_dates_sha256: str


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryPartition:
    """One named chronological region from the immutable audit."""

    name: str
    start_session: date
    end_session: date
    session_count: int


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryMaskedPair:
    """One exact daily pair that a later comparator must exclude."""

    symbol: str
    start_session: date
    end_session: date
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KisDailyEventBoundaryAudit:
    """Narrow, immutable contract consumed by later offline research only."""

    path: Path
    artifact_sha256: str
    lineage: KisDailyEventBoundaryAuditLineage
    mask_identity: str
    partition_identity: str
    partitions: tuple[KisDailyEventBoundaryPartition, ...]
    masked_pairs_by_symbol: Mapping[str, tuple[KisDailyEventBoundaryMaskedPair, ...]]

    def partition(self, name: str) -> KisDailyEventBoundaryPartition:
        """Return one named frozen partition without exposing mutable state."""

        for partition in self.partitions:
            if partition.name == name:
                return partition
        raise KeyError(name)


def load_kis_daily_event_boundary_audit(
    path: Path | str,
    *,
    expected_artifact_sha256: str,
    expected_catalog_dataset_hash: str,
    expected_catalog_index_hash: str,
    expected_sidecar_dataset_hash: str,
    expected_sidecar_manifest_hash: str,
    expected_session_dates_sha256: str,
    expected_mask_identity: str,
    expected_partition_identity: str,
) -> KisDailyEventBoundaryAudit:
    """Load one hash-pinned audit without credentials, network, or market data.

    The loader accepts only schema-v1 qualified artifacts.  It deliberately
    returns partition and exclusion geometry, not any price or return values.
    """

    expected_lineage = KisDailyEventBoundaryAuditLineage(
        catalog_dataset_hash=_require_sha256(
            expected_catalog_dataset_hash, "expected catalog dataset hash"
        ),
        catalog_index_hash=_require_sha256(
            expected_catalog_index_hash, "expected catalog index hash"
        ),
        sidecar_dataset_hash=_require_sha256(
            expected_sidecar_dataset_hash, "expected sidecar dataset hash"
        ),
        sidecar_manifest_hash=_require_sha256(
            expected_sidecar_manifest_hash, "expected sidecar manifest hash"
        ),
        session_dates_sha256=_require_sha256(
            expected_session_dates_sha256, "expected session dates hash"
        ),
    )
    expected_hash = _require_sha256(expected_artifact_sha256, "expected artifact hash")
    expected_mask = _require_sha256(expected_mask_identity, "expected mask identity")
    expected_partition = _require_sha256(
        expected_partition_identity, "expected partition identity"
    )
    artifact_path = _readable_json_path(path)
    payload = _read_bytes(artifact_path)
    actual_hash = _sha256(payload)
    if actual_hash != expected_hash:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary audit artifact hash mismatch"
        )
    document = _json_mapping(payload)
    _reject_price_or_return_fields(document)
    _require_exact_keys(document, _ROOT_KEYS, "KIS daily event-boundary audit schema")
    _validate_root(document)
    lineage = _parse_lineage(document)
    if lineage != expected_lineage:
        raise KisDailyEventBoundaryAuditError("KIS daily event-boundary audit lineage mismatch")
    partitions = _parse_partitions(document)
    parsed_partition_identity = _sha256_json(
        [
            {
                "name": partition.name,
                "start_session": partition.start_session.isoformat(),
                "end_session": partition.end_session.isoformat(),
                "session_count": partition.session_count,
            }
            for partition in partitions
        ]
    )
    _require_identity(
        document.get("partition_identity"),
        parsed_partition_identity,
        expected_partition,
        "partition",
    )
    masked_pairs = _parse_masked_pairs(document, partitions=partitions)
    parsed_mask_identity = _sha256_json(
        [
            {
                "symbol": pair.symbol,
                "start_session": pair.start_session.isoformat(),
                "end_session": pair.end_session.isoformat(),
                "reasons": list(pair.reasons),
            }
            for symbol in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS
            for pair in masked_pairs[symbol]
        ]
    )
    _require_identity(
        document.get("mask_identity"),
        parsed_mask_identity,
        expected_mask,
        "mask",
    )
    _validate_audit_counts(document, masked_pairs=masked_pairs)
    return KisDailyEventBoundaryAudit(
        path=artifact_path,
        artifact_sha256=actual_hash,
        lineage=lineage,
        mask_identity=parsed_mask_identity,
        partition_identity=parsed_partition_identity,
        partitions=partitions,
        masked_pairs_by_symbol=MappingProxyType(masked_pairs),
    )


def _readable_json_path(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.suffix != ".json" or candidate.is_symlink() or not candidate.is_file():
        raise KisDailyEventBoundaryAuditError("KIS daily event-boundary audit path is invalid")
    try:
        return candidate.resolve(strict=True)
    except OSError as error:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary audit path is invalid"
        ) from error


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary audit is unreadable"
        ) from error


def _json_mapping(payload: bytes) -> Mapping[str, object]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary audit JSON is invalid"
        ) from error
    if not isinstance(document, dict):
        raise KisDailyEventBoundaryAuditError("KIS daily event-boundary audit JSON is invalid")
    return MappingProxyType(document)


def _validate_root(document: Mapping[str, object]) -> None:
    if (
        document.get("schema_version") != KIS_DAILY_EVENT_BOUNDARY_AUDIT_SCHEMA_VERSION
        or document.get("kind") != KIS_DAILY_EVENT_BOUNDARY_AUDIT_KIND
        or document.get("status") != "qualified"
        or document.get("unqualified_reasons") != []
        or document.get("partition_policy") != _PARTITION_POLICY
        or document.get("scope") != _SCOPE
    ):
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary audit schema is incompatible"
        )
    for key in (
        "created_at_utc",
        "residual_threshold_absolute_return",
        "residual_policy",
        "event_buffer_policy",
        "future_comparator_requirement",
    ):
        if not isinstance(document.get(key), str) or not document[key]:
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary audit schema is invalid"
            )


def _parse_lineage(document: Mapping[str, object]) -> KisDailyEventBoundaryAuditLineage:
    return KisDailyEventBoundaryAuditLineage(
        catalog_dataset_hash=_require_sha256(
            document.get("catalog_dataset_hash"), "catalog dataset hash"
        ),
        catalog_index_hash=_require_sha256(
            document.get("catalog_index_hash"), "catalog index hash"
        ),
        sidecar_dataset_hash=_require_sha256(
            document.get("sidecar_dataset_hash"), "sidecar dataset hash"
        ),
        sidecar_manifest_hash=_require_sha256(
            document.get("sidecar_manifest_hash"), "sidecar manifest hash"
        ),
        session_dates_sha256=_require_sha256(
            document.get("session_dates_sha256"), "session dates hash"
        ),
    )


def _parse_partitions(document: Mapping[str, object]) -> tuple[KisDailyEventBoundaryPartition, ...]:
    raw_partitions = document.get("partitions")
    if not isinstance(raw_partitions, list) or len(raw_partitions) != len(
        KIS_DAILY_EVENT_BOUNDARY_AUDIT_PARTITIONS
    ):
        raise KisDailyEventBoundaryAuditError("KIS daily event-boundary partitions are invalid")
    partitions: list[KisDailyEventBoundaryPartition] = []
    for expected_name, raw_partition in zip(
        KIS_DAILY_EVENT_BOUNDARY_AUDIT_PARTITIONS, raw_partitions, strict=True
    ):
        if not isinstance(raw_partition, dict):
            raise KisDailyEventBoundaryAuditError("KIS daily event-boundary partitions are invalid")
        _require_exact_keys(raw_partition, _PARTITION_KEYS, "KIS daily event-boundary partition")
        name = raw_partition.get("name")
        count = raw_partition.get("session_count")
        if name != expected_name or type(count) is not int or count < 1:
            raise KisDailyEventBoundaryAuditError("KIS daily event-boundary partitions are invalid")
        start = _parse_date(raw_partition.get("start_session"), "partition start session")
        end = _parse_date(raw_partition.get("end_session"), "partition end session")
        if end < start or (count == 1 and start != end):
            raise KisDailyEventBoundaryAuditError("KIS daily event-boundary partitions are invalid")
        partitions.append(
            KisDailyEventBoundaryPartition(
                name=name,
                start_session=start,
                end_session=end,
                session_count=count,
            )
        )
    _validate_partition_geometry(tuple(partitions))
    return tuple(partitions)


def _validate_partition_geometry(partitions: tuple[KisDailyEventBoundaryPartition, ...]) -> None:
    for earlier, later in zip(partitions[:-1], partitions[1:], strict=True):
        if earlier.end_session >= later.start_session:
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary partition geometry is invalid"
            )
    if any(
        partition.session_count > (partition.end_session - partition.start_session).days + 1
        for partition in partitions
    ):
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary partition geometry is invalid"
        )
    total_sessions = sum(partition.session_count for partition in partitions)
    development, purge, validation, embargo, untouched_tail = partitions
    if (
        development.session_count != total_sessions * 3 // 5
        or purge.session_count != 1
        or validation.session_count != total_sessions // 5
        or embargo.session_count != 1
        or untouched_tail.session_count
        != total_sessions - development.session_count - validation.session_count - 2
    ):
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary partition geometry is invalid"
        )


def _parse_masked_pairs(
    document: Mapping[str, object],
    *,
    partitions: tuple[KisDailyEventBoundaryPartition, ...],
) -> dict[str, tuple[KisDailyEventBoundaryMaskedPair, ...]]:
    raw_pairs = document.get("masked_pairs")
    if not isinstance(raw_pairs, list) or not raw_pairs:
        raise KisDailyEventBoundaryAuditError("KIS daily event-boundary masked pairs are invalid")
    pairs_by_symbol: dict[str, list[KisDailyEventBoundaryMaskedPair]] = {
        symbol: [] for symbol in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS
    }
    previous_symbol_index = -1
    previous_by_symbol: dict[str, tuple[date, date] | None] = {
        symbol: None for symbol in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS
    }
    for raw_pair in raw_pairs:
        if not isinstance(raw_pair, dict):
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary masked pairs are invalid"
            )
        _require_exact_keys(raw_pair, _MASKED_PAIR_KEYS, "KIS daily event-boundary masked pair")
        symbol = raw_pair.get("symbol")
        if symbol not in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS:
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary masked pair symbol is invalid"
            )
        symbol_index = KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS.index(symbol)
        if symbol_index < previous_symbol_index:
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary masked pairs are unordered"
            )
        previous_symbol_index = symbol_index
        start = _parse_date(raw_pair.get("start_session"), "masked pair start session")
        end = _parse_date(raw_pair.get("end_session"), "masked pair end session")
        reasons = _parse_reasons(raw_pair.get("reasons"))
        if start >= end:
            raise KisDailyEventBoundaryAuditError("KIS daily event-boundary masked pair is invalid")
        previous = previous_by_symbol[symbol]
        if previous is not None and (start, end) <= previous:
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary masked pairs are unordered"
            )
        _validate_pair_partition_relation(
            start=start,
            end=end,
            reasons=reasons,
            partitions=partitions,
        )
        pair = KisDailyEventBoundaryMaskedPair(
            symbol=symbol,
            start_session=start,
            end_session=end,
            reasons=reasons,
        )
        pairs_by_symbol[symbol].append(pair)
        previous_by_symbol[symbol] = (start, end)
    if any(not pairs_by_symbol[symbol] for symbol in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS):
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary masked pairs are incomplete"
        )
    return {
        symbol: tuple(pairs_by_symbol[symbol]) for symbol in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS
    }


def _parse_reasons(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(reason, str) for reason in value):
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary masked pair reasons are invalid"
        )
    reasons = tuple(value)
    if reasons not in _ALLOWED_PAIR_REASONS:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary masked pair reasons are invalid"
        )
    return reasons


def _validate_pair_partition_relation(
    *,
    start: date,
    end: date,
    reasons: tuple[str, ...],
    partitions: tuple[KisDailyEventBoundaryPartition, ...],
) -> None:
    start_partition = _partition_name(start, partitions)
    end_partition = _partition_name(end, partitions)
    if start_partition is None or end_partition is None:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary masked pair is outside partitions"
        )
    needs_boundary = (
        start_partition != end_partition
        or start_partition in {"purge", "embargo"}
        or end_partition in {"purge", "embargo"}
    )
    if ("chronological_boundary" in reasons) != needs_boundary:
        raise KisDailyEventBoundaryAuditError(
            "KIS daily event-boundary masked pair partition relation is invalid"
        )


def _partition_name(
    session: date,
    partitions: tuple[KisDailyEventBoundaryPartition, ...],
) -> str | None:
    for partition in partitions:
        if partition.start_session <= session <= partition.end_session:
            return partition.name
    return None


def _validate_audit_counts(
    document: Mapping[str, object],
    *,
    masked_pairs: Mapping[str, tuple[KisDailyEventBoundaryMaskedPair, ...]],
) -> None:
    raw_counts = document.get("audit_counts")
    if not isinstance(raw_counts, dict) or set(raw_counts) != set(
        KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS
    ):
        raise KisDailyEventBoundaryAuditError("KIS daily event-boundary audit counts are invalid")
    for symbol in KIS_DAILY_EVENT_BOUNDARY_AUDIT_SYMBOLS:
        counts = raw_counts[symbol]
        if not isinstance(counts, dict):
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary audit counts are invalid"
            )
        _require_exact_keys(counts, _AUDIT_COUNT_KEYS, "KIS daily event-boundary audit counts")
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary audit counts are invalid"
            )
        if counts["masked_pair_count"] != len(masked_pairs[symbol]):
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary audit counts are inconsistent"
            )
        if (
            counts["mapped_event_count"] > counts["event_count"]
            or counts["interior_event_count"] > counts["mapped_event_count"]
            or counts["event_boundary_pair_count"] > counts["masked_pair_count"]
        ):
            raise KisDailyEventBoundaryAuditError(
                "KIS daily event-boundary audit counts are inconsistent"
            )


def _require_identity(
    declared: object,
    actual: str,
    expected: str,
    label: str,
) -> None:
    declared_hash = _require_sha256(declared, f"{label} identity")
    if declared_hash != actual or actual != expected:
        raise KisDailyEventBoundaryAuditError(
            f"KIS daily event-boundary audit {label} identity mismatch"
        )


def _reject_price_or_return_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise KisDailyEventBoundaryAuditError(
                    "KIS daily event-boundary audit JSON is invalid"
                )
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if key not in _ALLOWED_PRICE_OR_RETURN_METADATA_KEYS and (
                normalized in _FORBIDDEN_PAYLOAD_KEYS
                or "price" in normalized
                or "return" in normalized
            ):
                raise KisDailyEventBoundaryAuditError(
                    "KIS daily event-boundary audit contains raw price or return fields"
                )
            _reject_price_or_return_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_price_or_return_fields(nested)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise KisDailyEventBoundaryAuditError(f"{label} is invalid")


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise KisDailyEventBoundaryAuditError(f"KIS daily event-boundary {label} is invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise KisDailyEventBoundaryAuditError(
            f"KIS daily event-boundary {label} is invalid"
        ) from error
    if parsed.isoformat() != value:
        raise KisDailyEventBoundaryAuditError(f"KIS daily event-boundary {label} is invalid")
    return parsed


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise KisDailyEventBoundaryAuditError(f"KIS daily event-boundary {label} is invalid")
    return value


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _sha256(payload)

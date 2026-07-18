"""Fail-closed loading for local fixed-ETF corporate-action evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

CORPORATE_ACTION_SYMBOLS = ("SPY", "QQQ", "IWM")
CORPORATE_ACTION_EVENT_TYPES = (
    "cash_distribution",
    "split",
)
CORPORATE_ACTION_DATE_KINDS = ("ex_date", "split_trading_date")
CORPORATE_ACTION_COLUMNS = (
    "event_id",
    "symbol",
    "event_type",
    "source_date_kind",
    "source_event_date",
    "affected_session_date",
    "cash_amount",
    "currency",
    "split_numerator",
    "split_denominator",
    "source_id",
    "source_record_id",
    "mapping_rule_id",
    "mapping_status",
)
CAMPAIGN_COVERAGE_START = date(2022, 11, 22)
CAMPAIGN_COVERAGE_END = date(2026, 6, 22)

_DATASET_KIND = "fixed_etf_corporate_actions"
_EVENTS_BASENAME = "corporate_actions.csv"
_MAPPING_RULE_ID = "identity_observed_session_v1"
_SOURCE_KINDS = frozenset({"issuer_download", "licensed_api", "operator_supplied"})
_ACQUISITION_MODES = frozenset({"manual_operator", "authorized_api"})
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CATALOG_ATTESTATION_TOKEN = object()
_DUPLICATE_POLICY = {
    "event_id": "reject",
    "source_record": "reject",
    "identical_normalized_action": "preserve_records_collapse_mask_date",
    "conflict": "reject",
}
_DATE_SEMANTICS = {
    "exchange_timezone": "America/New_York",
    "session_date_semantics": "date_only_no_utc_conversion",
    "non_session_policy": "reject",
    "ambiguous_effective_date_policy": "reject",
}
_MAPPING_POLICY = {
    "id": _MAPPING_RULE_ID,
    "status": "mapped_only",
    "calendar_lineage": "verified_r2_observed_sessions",
}
_RETROSPECTIVE_SCOPE = {
    "retrospective_development_replay_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
}


@dataclass(frozen=True, slots=True)
class CorporateActionEvent:
    """One mapped event; cash means the source's total cash distribution."""

    event_id: str
    symbol: str
    event_type: str
    source_date_kind: str
    source_event_date: date
    affected_session_date: date
    cash_amount: Decimal | None
    currency: str | None
    split_numerator: Decimal | None
    split_denominator: Decimal | None
    source_id: str
    source_record_id: str
    mapping_rule_id: str
    mapping_status: str

    def __post_init__(self) -> None:
        identifiers = (self.event_id, self.source_id, self.source_record_id)
        if any(not value or value != value.strip() for value in identifiers):
            raise ValueError("corporate-action identifiers are required and must be trimmed")
        if self.symbol not in CORPORATE_ACTION_SYMBOLS:
            raise ValueError("corporate-action symbol must be SPY, QQQ, or IWM")
        if self.event_type not in CORPORATE_ACTION_EVENT_TYPES:
            raise ValueError("unsupported corporate-action event_type")
        date_kind = "ex_date" if self.event_type == "cash_distribution" else "split_trading_date"
        if self.source_date_kind != date_kind:
            raise ValueError(f"{self.event_type} requires {date_kind}")
        if (self.mapping_rule_id, self.mapping_status) != (_MAPPING_RULE_ID, "mapped"):
            raise ValueError("corporate action must use the mapped observed-session rule")
        if self.source_event_date != self.affected_session_date:
            raise ValueError("corporate-action dates cannot be rolled to another session")

        if self.event_type == "cash_distribution":
            if self.cash_amount is None or self.cash_amount <= 0:
                raise ValueError("distribution cash_amount must be positive")
            if self.currency != "USD":
                raise ValueError("distribution currency must be USD")
            if self.split_numerator is not None or self.split_denominator is not None:
                raise ValueError("distribution cannot carry a split ratio")
        elif (
            self.cash_amount is not None
            or self.currency is not None
            or self.split_numerator is None
            or self.split_denominator is None
            or self.split_numerator <= 0
            or self.split_denominator <= 0
            or self.split_numerator == self.split_denominator
        ):
            raise ValueError("split requires a positive non-unit ratio and no cash fields")


@dataclass(frozen=True, slots=True)
class _RawSource:
    source_as_of: date
    declared_pairs: frozenset[tuple[str, str]]


@dataclass(frozen=True, slots=True, init=False)
class CatalogedCorporateActions:
    """Loader-attested, retrospective-only corporate-action evidence."""

    dataset_id: str
    dataset_hash: str
    manifest_path: Path
    manifest_hash: str
    r2_dataset_id: str
    r2_dataset_hash: str
    r2_manifest_hash: str
    retrieved_at_utc: datetime
    source_as_of: date
    revision: str
    events: tuple[CorporateActionEvent, ...]
    _replay_ineligibility_reasons: tuple[str, ...]
    _identity_attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use load_cataloged_corporate_actions")

    def for_symbol(self, symbol: str) -> tuple[CorporateActionEvent, ...]:
        requested = _requested_symbol(symbol)
        return tuple(event for event in self.events if event.symbol == requested)

    def affected_session_dates(self, symbol: str) -> frozenset[date]:
        """Collapse mask dates without discarding duplicate source records."""

        requested = _requested_symbol(symbol)
        return frozenset(
            event.affected_session_date for event in self.events if event.symbol == requested
        )

    def assert_replay_eligible(self) -> None:
        """Assert complete evidence for retrospective development replay only."""

        if getattr(self, "_identity_attestation", None) is not _CATALOG_ATTESTATION_TOKEN:
            raise ValueError("corporate-action catalog is not loader-attested")
        if self._replay_ineligibility_reasons:
            reasons = "; ".join(self._replay_ineligibility_reasons)
            raise ValueError(f"corporate-action snapshot is not replay eligible: {reasons}")


def load_cataloged_corporate_actions(
    snapshot_dir: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    expected_r2_dataset_id: str,
    expected_r2_dataset_hash: str,
    expected_r2_manifest_hash: str,
    observed_session_dates: Mapping[str, Collection[date]],
    require_replay_eligible: bool = False,
    repo_root: Path | None = None,
) -> CatalogedCorporateActions:
    """Load an immutable external snapshot without network or source acquisition."""

    _required_text(dataset_id, "dataset_id")
    _required_text(expected_r2_dataset_id, "expected_r2_dataset_id")
    for value, label in (
        (expected_dataset_hash, "expected_dataset_hash"),
        (expected_manifest_hash, "expected_manifest_hash"),
        (expected_r2_dataset_hash, "expected_r2_dataset_hash"),
        (expected_r2_manifest_hash, "expected_r2_manifest_hash"),
    ):
        _validate_sha256(value, label)

    snapshot = _external_snapshot_dir(snapshot_dir, repo_root=repo_root)
    manifest_path = snapshot / "manifest.json"
    manifest_bytes = _read_snapshot_file(snapshot, manifest_path, "manifest")
    manifest_hash = _sha256_bytes(manifest_bytes)
    if manifest_hash != expected_manifest_hash:
        raise ValueError("corporate-action manifest content hash mismatch")
    manifest = _decode_manifest(manifest_bytes)

    event_path = snapshot / _EVENTS_BASENAME
    event_bytes = _read_snapshot_file(snapshot, event_path, "normalized event file")
    dataset_hash = _sha256_bytes(event_bytes)
    if dataset_hash != expected_dataset_hash:
        raise ValueError("corporate-action dataset hash mismatch")

    retrieved_at, source_as_of, revision = _validate_manifest(
        manifest,
        snapshot=snapshot,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        event_size=len(event_bytes),
        r2_id=expected_r2_dataset_id,
        r2_hash=expected_r2_dataset_hash,
        r2_manifest_hash=expected_r2_manifest_hash,
    )
    events = _parse_events(event_bytes, _validated_observed_sessions(observed_session_dates))
    sources = _validate_raw_sources(snapshot, manifest)
    reasons = _validate_coverage(
        manifest,
        events=events,
        sources=sources,
        snapshot_source_as_of=source_as_of,
    )
    catalog = _attested_catalog(
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        manifest_path=manifest_path,
        manifest_hash=manifest_hash,
        r2_dataset_id=expected_r2_dataset_id,
        r2_dataset_hash=expected_r2_dataset_hash,
        r2_manifest_hash=expected_r2_manifest_hash,
        retrieved_at_utc=retrieved_at,
        source_as_of=source_as_of,
        revision=revision,
        events=events,
        replay_ineligibility_reasons=reasons,
    )
    if require_replay_eligible:
        catalog.assert_replay_eligible()
    return catalog


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    snapshot: Path,
    dataset_id: str,
    dataset_hash: str,
    event_size: int,
    r2_id: str,
    r2_hash: str,
    r2_manifest_hash: str,
) -> tuple[datetime, date, str]:
    if (manifest.get("schema_version"), manifest.get("kind")) != (1, _DATASET_KIND):
        raise ValueError("corporate-action manifest has the wrong schema or kind")
    if manifest.get("immutable_snapshot") is not True:
        raise ValueError("corporate-action snapshot must be declared immutable")
    path_id = f"us_equities.fixed_etf_corporate_actions.{snapshot.name}"
    if dataset_id != path_id or manifest.get("dataset_id") != path_id:
        raise ValueError("corporate-action dataset_id is inconsistent with snapshot path")
    if manifest.get("dataset_hash") != dataset_hash:
        raise ValueError("corporate-action manifest does not bind normalized bytes")

    exact_values = (
        ("symbols", list(CORPORATE_ACTION_SYMBOLS), "must declare exact fixed symbols"),
        ("event_types", list(CORPORATE_ACTION_EVENT_TYPES), "event types are incomplete"),
        ("date_kinds", list(CORPORATE_ACTION_DATE_KINDS), "date kinds are invalid"),
        (
            "campaign_coverage",
            {
                "start": CAMPAIGN_COVERAGE_START.isoformat(),
                "end": CAMPAIGN_COVERAGE_END.isoformat(),
            },
            "campaign coverage must match the fixed campaign",
        ),
        ("date_semantics", _DATE_SEMANTICS, "session-date semantics are not exact"),
        ("duplicate_policy", _DUPLICATE_POLICY, "duplicate/conflict policy is invalid"),
        ("mapping_policy", _MAPPING_POLICY, "mapping policy is invalid"),
        ("scope", _RETROSPECTIVE_SCOPE, "evidence scope is invalid"),
    )
    for key, expected, message in exact_values:
        if manifest.get(key) != expected:
            raise ValueError(f"corporate-action {message}")

    normalized = _required_mapping(manifest, "normalized_events")
    if normalized.get("sha256") != dataset_hash or normalized.get("size_bytes") != event_size:
        raise ValueError("normalized event size or hash is inconsistent")
    if tuple(normalized.get("schema") or ()) != CORPORATE_ACTION_COLUMNS:
        raise ValueError("corporate-action normalized schema mismatch")
    _validate_portable_tail(
        normalized.get("path"), (snapshot.name, _EVENTS_BASENAME), "normalized event path"
    )

    lineage = _required_mapping(manifest, "r2_lineage")
    if (
        lineage.get("dataset_id"),
        lineage.get("dataset_hash"),
        lineage.get("manifest_sha256"),
    ) != (r2_id, r2_hash, r2_manifest_hash):
        raise ValueError("corporate-action r2 lineage mismatch")
    r2_snapshot = r2_id.rsplit(".", 1)[-1]
    if lineage.get("snapshot_name") != r2_snapshot:
        raise ValueError("corporate-action r2 snapshot identity is inconsistent")
    _validate_portable_tail(
        lineage.get("subset_path"), (r2_snapshot, "ohlcv_1d.csv.gz"), "r2 subset path"
    )
    _validate_portable_tail(
        lineage.get("manifest_path"), (r2_snapshot, "manifest.json"), "r2 manifest path"
    )

    metadata = _required_mapping(manifest, "snapshot_metadata")
    retrieved_at = _utc_datetime(metadata.get("retrieved_at_utc"), "retrieved_at_utc")
    source_as_of = _required_date(metadata.get("source_as_of"), "source_as_of")
    if source_as_of > retrieved_at.date():
        raise ValueError("snapshot source_as_of cannot follow retrieval UTC date")
    return retrieved_at, source_as_of, _required_text(metadata.get("revision"), "revision")


def _parse_events(
    data: bytes, sessions: Mapping[str, frozenset[date]]
) -> tuple[CorporateActionEvent, ...]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    except UnicodeDecodeError as exc:
        raise ValueError("corporate-action events must be UTF-8") from exc
    if tuple(reader.fieldnames or ()) != CORPORATE_ACTION_COLUMNS:
        raise ValueError("corporate-action event schema mismatch")

    events: list[CorporateActionEvent] = []
    ids: set[str] = set()
    records: set[tuple[str, str]] = set()
    semantics: dict[tuple[object, ...], tuple[object, ...]] = {}
    previous_order: tuple[object, ...] | None = None
    for row in reader:
        event = _event_from_row(row)
        if event.event_id in ids:
            raise ValueError(f"duplicate corporate-action event_id: {event.event_id}")
        ids.add(event.event_id)
        record = (event.source_id, event.source_record_id)
        if record in records:
            raise ValueError("duplicate corporate-action source record")
        records.add(record)
        if not CAMPAIGN_COVERAGE_START <= event.affected_session_date <= CAMPAIGN_COVERAGE_END:
            raise ValueError("corporate-action event is outside campaign coverage")
        if event.affected_session_date not in sessions[event.symbol]:
            raise ValueError("corporate action maps to a non-session date")

        semantic_key = (
            event.symbol,
            event.event_type,
            event.source_date_kind,
            event.source_event_date,
        )
        payload = (
            event.affected_session_date,
            event.cash_amount,
            event.currency,
            event.split_numerator,
            event.split_denominator,
        )
        if semantics.setdefault(semantic_key, payload) != payload:
            raise ValueError("conflicting normalized corporate-action records")
        order = (
            CORPORATE_ACTION_SYMBOLS.index(event.symbol),
            event.affected_session_date,
            CORPORATE_ACTION_EVENT_TYPES.index(event.event_type),
            event.event_id,
        )
        if previous_order is not None and order <= previous_order:
            raise ValueError("corporate-action events are not deterministically ordered")
        previous_order = order
        events.append(event)
    return tuple(events)


def _event_from_row(row: Mapping[str | None, str | None]) -> CorporateActionEvent:
    return CorporateActionEvent(
        event_id=str(row.get("event_id") or ""),
        symbol=str(row.get("symbol") or "").strip().upper(),
        event_type=str(row.get("event_type") or "").strip(),
        source_date_kind=str(row.get("source_date_kind") or "").strip(),
        source_event_date=_required_date(row.get("source_event_date"), "source_event_date"),
        affected_session_date=_required_date(
            row.get("affected_session_date"), "affected_session_date"
        ),
        cash_amount=_optional_decimal(row.get("cash_amount"), "cash_amount"),
        currency=str(row.get("currency") or "").strip() or None,
        split_numerator=_optional_decimal(row.get("split_numerator"), "split_numerator"),
        split_denominator=_optional_decimal(row.get("split_denominator"), "split_denominator"),
        source_id=str(row.get("source_id") or ""),
        source_record_id=str(row.get("source_record_id") or ""),
        mapping_rule_id=str(row.get("mapping_rule_id") or "").strip(),
        mapping_status=str(row.get("mapping_status") or "").strip(),
    )


def _validate_raw_sources(snapshot: Path, manifest: Mapping[str, Any]) -> dict[str, _RawSource]:
    entries = manifest.get("raw_sources")
    if not isinstance(entries, list) or not entries:
        raise ValueError("corporate-action manifest is missing raw sources")
    sources: dict[str, _RawSource] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid corporate-action raw source entry")
        source_id = _required_text(entry.get("source_id"), "raw source_id")
        if source_id in sources:
            raise ValueError("duplicate corporate-action raw source_id")
        prefix = f"raw source {source_id}"
        _required_text(entry.get("provider"), f"{prefix} provider")
        _https_source_url(entry.get("source_url"), f"{prefix} source_url")
        if entry.get("source_kind") not in _SOURCE_KINDS:
            raise ValueError(f"{prefix} has invalid source_kind")
        if entry.get("acquisition_mode") not in _ACQUISITION_MODES:
            raise ValueError(f"{prefix} has invalid acquisition_mode")
        if entry.get("use_scope") != "private_internal_use":
            raise ValueError(f"{prefix} use_scope must be private_internal_use")
        if entry.get("rights_status") != "confirmed":
            raise ValueError(f"{prefix} rights_status must be confirmed")

        symbols = _sorted_values(
            entry.get("symbols"), CORPORATE_ACTION_SYMBOLS, f"{prefix} symbols"
        )
        event_types = _sorted_values(
            entry.get("event_types"), CORPORATE_ACTION_EVENT_TYPES, f"{prefix} event_types"
        )
        if (
            _required_date(entry.get("coverage_start"), f"{prefix} coverage_start"),
            _required_date(entry.get("coverage_end"), f"{prefix} coverage_end"),
        ) != (CAMPAIGN_COVERAGE_START, CAMPAIGN_COVERAGE_END):
            raise ValueError(f"{prefix} must cover the exact campaign range")

        filename = _required_text(entry.get("filename"), "raw source filename")
        if Path(filename).name != filename:
            raise ValueError("raw source filename must be a basename")
        _validate_portable_tail(
            entry.get("path"), (snapshot.name, "raw", filename), f"{prefix} path"
        )
        raw_bytes = _read_snapshot_file(snapshot, snapshot / "raw" / filename, prefix)
        if entry.get("size_bytes") != len(raw_bytes):
            raise ValueError(f"raw source size mismatch: {source_id}")
        expected_hash = str(entry.get("sha256") or "")
        _validate_sha256(expected_hash, f"{prefix} hash")
        if _sha256_bytes(raw_bytes) != expected_hash:
            raise ValueError(f"raw source hash mismatch: {source_id}")

        retrieved_at = _utc_datetime(entry.get("retrieved_at_utc"), f"{prefix} retrieval")
        source_as_of = _required_date(entry.get("source_as_of"), f"{prefix} source_as_of")
        if source_as_of > retrieved_at.date():
            raise ValueError(f"{prefix} source_as_of cannot follow retrieval UTC date")
        _required_text(entry.get("revision"), f"{prefix} revision")
        sources[source_id] = _RawSource(
            source_as_of=source_as_of,
            declared_pairs=frozenset((symbol, kind) for symbol in symbols for kind in event_types),
        )
    return sources


def _validate_coverage(
    manifest: Mapping[str, Any],
    *,
    events: tuple[CorporateActionEvent, ...],
    sources: Mapping[str, _RawSource],
    snapshot_source_as_of: date,
) -> tuple[str, ...]:
    entries = manifest.get("coverage")
    expected = [
        (symbol, event_type)
        for symbol in CORPORATE_ACTION_SYMBOLS
        for event_type in CORPORATE_ACTION_EVENT_TYPES
    ]
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("corporate-action coverage is incomplete")

    reasons: list[str] = []
    used_sources: set[str] = set()
    for entry, pair in zip(entries, expected, strict=True):
        if not isinstance(entry, dict):
            raise ValueError("invalid corporate-action coverage entry")
        symbol = str(entry.get("symbol") or "").strip().upper()
        event_type = str(entry.get("event_type") or "").strip()
        if (symbol, event_type) != pair:
            raise ValueError("corporate-action coverage keys are incomplete or unordered")
        if (
            _required_date(entry.get("start"), "coverage start"),
            _required_date(entry.get("end"), "coverage end"),
        ) != (CAMPAIGN_COVERAGE_START, CAMPAIGN_COVERAGE_END):
            raise ValueError("coverage entries must span the exact campaign")
        status = str(entry.get("status") or "").strip()
        if status not in {"complete", "incomplete", "unknown"}:
            raise ValueError("invalid corporate-action coverage status")
        count = entry.get("event_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("coverage event_count must be a nonnegative integer")
        source_ids = _sorted_values(entry.get("source_ids"), tuple(sources), "coverage source_ids")
        used_sources.update(source_ids)
        if any(pair not in sources[source_id].declared_pairs for source_id in source_ids):
            raise ValueError("coverage source does not declare its symbol and event_type")

        matching = tuple(
            event for event in events if (event.symbol, event.event_type) == pair
        )
        if len(matching) != count:
            raise ValueError("coverage event_count disagrees with normalized events")
        if {event.source_id for event in matching} - set(source_ids):
            raise ValueError("event provenance is absent from its coverage evidence")
        if status != "complete":
            reasons.append(f"{symbol}/{event_type} coverage is {status}")
        stale = [
            source_id
            for source_id in source_ids
            if sources[source_id].source_as_of < CAMPAIGN_COVERAGE_END
        ]
        if stale:
            reasons.append(
                f"{symbol}/{event_type} sources predate campaign end: {', '.join(stale)}"
            )

    if used_sources != set(sources):
        raise ValueError("raw source files must be bound to coverage")
    if snapshot_source_as_of < CAMPAIGN_COVERAGE_END:
        reasons.append("snapshot source_as_of predates campaign end")
    return tuple(reasons)


def _validated_observed_sessions(
    value: Mapping[str, Collection[date]],
) -> dict[str, frozenset[date]]:
    if set(value) != set(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("observed sessions must contain exact fixed symbols")
    sessions: dict[str, frozenset[date]] = {}
    campaign_sets: set[frozenset[date]] = set()
    for symbol in CORPORATE_ACTION_SYMBOLS:
        dates = tuple(value[symbol])
        if any(type(item) is not date for item in dates):
            raise ValueError("observed sessions must be date-only values")
        sessions[symbol] = frozenset(dates)
        campaign = frozenset(
            item for item in dates if CAMPAIGN_COVERAGE_START <= item <= CAMPAIGN_COVERAGE_END
        )
        if not {CAMPAIGN_COVERAGE_START, CAMPAIGN_COVERAGE_END} <= campaign:
            raise ValueError("observed sessions do not span the fixed campaign")
        campaign_sets.add(campaign)
    if len(campaign_sets) != 1:
        raise ValueError("fixed instruments must use the same campaign sessions")
    return sessions


def _attested_catalog(**values: object) -> CatalogedCorporateActions:
    catalog = object.__new__(CatalogedCorporateActions)
    values["_identity_attestation"] = _CATALOG_ATTESTATION_TOKEN
    values["_replay_ineligibility_reasons"] = values.pop("replay_ineligibility_reasons")
    for field, value in values.items():
        object.__setattr__(catalog, field, value)
    return catalog


def _external_snapshot_dir(path: Path, *, repo_root: Path | None) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError("corporate-action snapshot cannot be a symlink")
    try:
        snapshot = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("corporate-action snapshot directory is missing") from exc
    if not snapshot.is_dir():
        raise ValueError("corporate-action snapshot path must be a directory")
    if repo_root is not None:
        root = Path(repo_root).resolve(strict=False)
        if snapshot == root or snapshot.is_relative_to(root):
            docker_mount_roots = (
                Path("/app/market_data").resolve(),
                Path("/app/model_artifacts").resolve(),
            )
            if not (
                root == Path("/app").resolve()
                and any(
                    snapshot == mount_root or snapshot.is_relative_to(mount_root)
                    for mount_root in docker_mount_roots
                )
            ):
                raise ValueError("corporate-action snapshot must be outside Git")
    if any((parent / ".git").exists() for parent in (snapshot, *snapshot.parents)):
        raise ValueError("corporate-action snapshot must be outside Git")
    return snapshot


def _read_snapshot_file(snapshot: Path, path: Path, label: str) -> bytes:
    try:
        relative = path.relative_to(snapshot)
    except ValueError as exc:
        raise ValueError(f"{label} must be inside the snapshot") from exc
    current = snapshot
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} cannot use symlinks")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"{label} must be a regular file inside the snapshot")
    return resolved.read_bytes()


def _decode_manifest(data: bytes) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("corporate-action manifest must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("corporate-action manifest must be a JSON object")
    return value


def _required_mapping(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"corporate-action manifest is missing {key}")
    return item


def _validate_portable_tail(value: object, tail: tuple[str, ...], label: str) -> None:
    parts = PurePosixPath(str(value or "").replace("\\", "/")).parts
    if len(parts) < len(tail) or tuple(parts[-len(tail) :]) != tail:
        raise ValueError(f"{label} is inconsistent with snapshot-relative identity")


def _requested_symbol(symbol: str) -> str:
    requested = symbol.strip().upper()
    if requested not in CORPORATE_ACTION_SYMBOLS:
        raise ValueError("symbol must be one of SPY, QQQ, IWM")
    return requested


def _required_text(value: object, label: str) -> str:
    text = str(value or "")
    if not text or text != text.strip():
        raise ValueError(f"{label} is required and must be trimmed")
    return text


def _required_date(value: object, label: str) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid or missing {label}: {text}") from exc


def _optional_decimal(value: object, label: str) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {label}: {text}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{label} must be finite")
    return parsed


def _utc_datetime(value: object, label: str) -> datetime:
    text = _required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return parsed.astimezone(UTC)


def _https_source_url(value: object, label: str) -> str:
    text = _required_text(value, label)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(f"{label} must be an HTTPS URL without credentials or fragment")
    return text


def _sorted_values(value: object, allowed: Collection[str], label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a nonempty sorted list")
    values = tuple(value)
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{label} must be exact, unique, and sorted")
    if set(values) - set(allowed):
        raise ValueError(f"{label} contains unsupported values")
    return values


def _validate_sha256(value: str, label: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be formatted as sha256:<64 lowercase hex>")


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"

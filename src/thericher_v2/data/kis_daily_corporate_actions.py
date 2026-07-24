"""Price-free Tiingo event sidecars for the private KIS QQQ/SPY daily cache.

This module is intentionally narrower than the older fixed-ETF corporate-action
pipeline.  It qualifies only the completed KIS Paper QQQ/SPY daily panel for
retrospective price-return labels.  Tiingo response bytes are parsed in memory
and are never written to the snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KisPaperPrivateDailyCatalog,
)
from .tiingo_eod import TIINGO_EOD_ENDPOINT, TiingoEodAcquisitionError, read_tiingo_api_token

DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
KIS_DAILY_CORPORATE_ACTION_ROOT = (
    DEFAULT_MARKET_DATA_ROOT / "us_equities" / "kis_paper_private" / "daily-corporate-actions"
)
KIS_DAILY_CORPORATE_ACTION_SYMBOLS = ("QQQ", "SPY")
KIS_DAILY_CORPORATE_ACTION_EVENT_COLUMNS = (
    "symbol",
    "source_date",
    "mapped_kis_session_date",
    "event_kind",
    "value",
)
KIS_DAILY_CORPORATE_ACTION_EVENT_KINDS = ("cash_distribution", "split")
KIS_DAILY_CORPORATE_ACTION_SCHEMA_VERSION = 1
KIS_DAILY_CORPORATE_ACTION_KIND = "kis_paper_private_daily_corporate_action_sidecar"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_SCOPE = {
    "retrospective_price_return_label_integrity_only": True,
    "point_in_time_feature_eligible": False,
    "model_training_eligible": False,
    "paper_decision_eligible": False,
    "price_policy": "no_tiingo_prices_persisted_or_used",
    "return_policy": "exclude_pairs_when_either_endpoint_has_a_dividend_or_split_event",
}
_MAPPING = {
    "rule": "identity_exact_kis_session_date_v1",
    "exchange_timezone": "America/New_York",
    "non_session_policy": "reject",
    "ambiguous_date_policy": "reject",
}


class KisDailyCorporateActionError(ValueError):
    """A neutral, fail-closed sidecar acquisition or validation error."""


@dataclass(frozen=True, slots=True)
class KisDailyCorporateActionEvent:
    """One Tiingo event mapped exactly to a retained KIS daily session."""

    symbol: str
    source_date: date
    mapped_kis_session_date: date
    event_kind: str
    value: Decimal

    def __post_init__(self) -> None:
        if self.symbol not in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
            raise ValueError("KIS daily corporate-action symbol is invalid")
        if self.event_kind not in KIS_DAILY_CORPORATE_ACTION_EVENT_KINDS:
            raise ValueError("KIS daily corporate-action event kind is invalid")
        if self.source_date != self.mapped_kis_session_date:
            raise ValueError("KIS daily corporate-action date mapping must be exact")
        if self.value <= 0:
            raise ValueError("KIS daily corporate-action value must be positive")


@dataclass(frozen=True, slots=True)
class KisDailyCorporateActionSnapshot:
    """An attested, immutable, price-free event sidecar."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    catalog_dataset_hash: str
    catalog_index_hash: str
    retrieved_at_utc: datetime
    events: tuple[KisDailyCorporateActionEvent, ...]
    event_counts: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True, slots=True)
class _NormalizedTiingoResponse:
    symbol: str
    response_hash: str
    events: tuple[KisDailyCorporateActionEvent, ...]


def default_kis_daily_corporate_action_snapshot_dir(retrieval_date: date) -> Path:
    """Return the immutable destination for one qualified QQQ/SPY sidecar."""

    if type(retrieval_date) is not date:
        raise ValueError("KIS daily corporate-action retrieval date is invalid")
    return KIS_DAILY_CORPORATE_ACTION_ROOT / (
        f"snapshot={retrieval_date.isoformat()}-qqq-spy-tiingo-events-v1"
    )


def fetch_kis_daily_tiingo_corporate_action_responses(
    *,
    env_path: Path,
    start_session: date,
    end_session: date,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = 20.0,
) -> dict[str, bytes]:
    """Fetch exactly the approved Tiingo EOD responses for the KIS date span.

    The only credential reader is ``read_tiingo_api_token``.  Responses are
    returned for immediate normalization and are never retained by this module.
    """

    _validate_session_span(start_session, end_session)
    if timeout_seconds <= 0:
        raise ValueError("Tiingo timeout_seconds must be positive")
    try:
        token = read_tiingo_api_token(Path(env_path))
    except TiingoEodAcquisitionError as error:
        raise KisDailyCorporateActionError("Tiingo token is unavailable") from error

    responses: dict[str, bytes] = {}
    query = urlencode(
        {
            "startDate": start_session.isoformat(),
            "endDate": end_session.isoformat(),
        }
    )
    for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        request = Request(
            f"{TIINGO_EOD_ENDPOINT.format(symbol=symbol)}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Token {token}"},
        )
        try:
            with opener(request, timeout=timeout_seconds) as response:
                if getattr(response, "status", 200) != 200:
                    raise KisDailyCorporateActionError(
                        f"Tiingo EOD request failed for {symbol}: unexpected status"
                    )
                payload = response.read()
        except HTTPError as error:
            raise KisDailyCorporateActionError(
                f"Tiingo EOD request failed for {symbol}: HTTP {error.code}"
            ) from error
        except (OSError, URLError) as error:
            raise KisDailyCorporateActionError(f"Tiingo EOD request failed for {symbol}") from error
        if not isinstance(payload, bytes) or not payload:
            raise KisDailyCorporateActionError(f"Tiingo EOD response is unavailable for {symbol}")
        responses[symbol] = payload
    return responses


def build_kis_daily_corporate_action_snapshot(
    *,
    destination: Path,
    raw_responses: Mapping[str, bytes],
    catalog: KisPaperPrivateDailyCatalog,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> KisDailyCorporateActionSnapshot:
    """Atomically write one price-free immutable event sidecar outside Git."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    sessions = _qualified_catalog_sessions(catalog)
    destination_path = Path(destination)
    _validate_destination(
        destination=destination_path,
        market_data_root=Path(market_data_root),
        repo_root=repo_root,
    )
    if set(raw_responses) != set(KIS_DAILY_CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo sidecar responses must contain exact QQQ and SPY symbols")

    normalized: dict[str, _NormalizedTiingoResponse] = {}
    for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        response = raw_responses[symbol]
        if not isinstance(response, bytes):
            raise ValueError(f"Tiingo response must be bytes for {symbol}")
        normalized[symbol] = _normalize_tiingo_response(
            symbol=symbol,
            raw_response=response,
            expected_sessions=sessions,
        )
        if not normalized[symbol].events:
            raise ValueError(f"Tiingo sidecar has no events for {symbol}")
    events = tuple(
        event
        for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
        for event in normalized[symbol].events
    )
    event_bytes = _event_csv_bytes(events)
    dataset_hash = _sha256(event_bytes)

    staging = _create_staging_directory(destination_path)
    try:
        (staging / "events.csv").write_bytes(event_bytes)
        manifest = _manifest(
            snapshot_dir=destination_path,
            dataset_hash=dataset_hash,
            event_size_bytes=len(event_bytes),
            normalized=normalized,
            catalog=catalog,
            sessions=sessions,
            retrieved_at_utc=retrieved_at,
        )
        manifest_bytes = _json_bytes(manifest)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        os.rename(staging, destination_path)
        staging.parent.rmdir()
    except Exception:
        if staging.parent.exists():
            shutil.rmtree(staging.parent)
        raise

    return _load_snapshot(
        destination_path,
        catalog=catalog,
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=_sha256((destination_path / "manifest.json").read_bytes()),
        repo_root=repo_root,
    )


def load_kis_daily_corporate_action_snapshot(
    snapshot_dir: Path,
    *,
    catalog: KisPaperPrivateDailyCatalog,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    repo_root: Path | None = None,
) -> KisDailyCorporateActionSnapshot:
    """Load a pinned sidecar with no network, credential, or broker dependency."""

    return _load_snapshot(
        snapshot_dir,
        catalog=catalog,
        expected_dataset_hash=expected_dataset_hash,
        expected_manifest_hash=expected_manifest_hash,
        repo_root=repo_root,
    )


def _load_snapshot(
    snapshot_dir: Path,
    *,
    catalog: KisPaperPrivateDailyCatalog,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    repo_root: Path | None,
) -> KisDailyCorporateActionSnapshot:
    _require_sha256(expected_dataset_hash, "expected dataset hash")
    _require_sha256(expected_manifest_hash, "expected manifest hash")
    sessions = _qualified_catalog_sessions(catalog)
    snapshot = _external_snapshot_dir(Path(snapshot_dir), repo_root=repo_root)
    manifest_path = snapshot / "manifest.json"
    manifest_bytes = _read_snapshot_file(snapshot, manifest_path, "sidecar manifest")
    manifest_hash = _sha256(manifest_bytes)
    if manifest_hash != expected_manifest_hash:
        raise ValueError("KIS daily corporate-action manifest hash mismatch")
    manifest = _json_object(manifest_bytes, "KIS daily corporate-action manifest")
    event_path = snapshot / "events.csv"
    event_bytes = _read_snapshot_file(snapshot, event_path, "sidecar events")
    dataset_hash = _sha256(event_bytes)
    if dataset_hash != expected_dataset_hash:
        raise ValueError("KIS daily corporate-action dataset hash mismatch")
    retrieved_at = _validate_manifest(
        manifest=manifest,
        snapshot=snapshot,
        dataset_hash=dataset_hash,
        event_size_bytes=len(event_bytes),
        catalog=catalog,
        sessions=sessions,
    )
    events = _parse_events(event_bytes=event_bytes, sessions=sessions)
    _validate_event_counts(manifest=manifest, events=events)
    counts = {
        symbol: MappingProxyType(
            {
                kind: sum(event.symbol == symbol and event.event_kind == kind for event in events)
                for kind in KIS_DAILY_CORPORATE_ACTION_EVENT_KINDS
            }
        )
        for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
    }
    return KisDailyCorporateActionSnapshot(
        snapshot_dir=snapshot,
        dataset_id=str(manifest["dataset_id"]),
        dataset_hash=dataset_hash,
        manifest_hash=manifest_hash,
        catalog_dataset_hash=catalog.dataset_hash,
        catalog_index_hash=catalog.index_hash,
        retrieved_at_utc=retrieved_at,
        events=events,
        event_counts=MappingProxyType(counts),
    )


def _qualified_catalog_sessions(catalog: KisPaperPrivateDailyCatalog) -> tuple[date, ...]:
    if not isinstance(catalog, KisPaperPrivateDailyCatalog):
        raise ValueError("KIS daily corporate-action catalog is invalid")
    if catalog.adjustment_mode != KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE:
        raise ValueError("KIS daily corporate-action catalog adjustment mode is incompatible")
    if set(catalog.bars_by_symbol) != set(KIS_DAILY_CORPORATE_ACTION_SYMBOLS):
        raise ValueError("KIS daily corporate-action catalog must contain exact QQQ and SPY")
    _require_sha256(catalog.dataset_hash, "catalog dataset hash")
    _require_sha256(catalog.index_hash, "catalog index hash")
    sessions = tuple(catalog.common_sessions)
    if (
        len(sessions) < 3
        or tuple(sorted(sessions)) != sessions
        or len(set(sessions)) != len(sessions)
    ):
        raise ValueError("KIS daily corporate-action catalog sessions are invalid")
    if any(type(session) is not date for session in sessions):
        raise ValueError("KIS daily corporate-action catalog sessions are invalid")
    for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        bars = catalog.bars_by_symbol[symbol].bars
        if len(bars) != len(sessions) or tuple(bar.start_ts.date() for bar in bars) != sessions:
            raise ValueError("KIS daily corporate-action catalog streams are incompatible")
    return sessions


def _normalize_tiingo_response(
    *,
    symbol: str,
    raw_response: bytes,
    expected_sessions: tuple[date, ...],
) -> _NormalizedTiingoResponse:
    if symbol not in KIS_DAILY_CORPORATE_ACTION_SYMBOLS:
        raise ValueError("Tiingo sidecar symbol is invalid")
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError(f"Tiingo EOD response is missing for {symbol}")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Tiingo EOD response is invalid for {symbol}") from error
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Tiingo EOD response must be a nonempty array for {symbol}")

    observed_dates: set[date] = set()
    previous_date: date | None = None
    events: list[KisDailyCorporateActionEvent] = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError(f"Tiingo EOD row must be an object for {symbol}")
        source_date = _tiingo_date(row.get("date"), symbol)
        if source_date in observed_dates:
            raise ValueError(f"Tiingo EOD response has duplicate dates for {symbol}")
        if previous_date is not None and source_date <= previous_date:
            raise ValueError(f"Tiingo EOD response dates are not ascending for {symbol}")
        observed_dates.add(source_date)
        previous_date = source_date
        cash = _tiingo_decimal(row.get("divCash"), "divCash", symbol)
        split_factor = _tiingo_decimal(row.get("splitFactor"), "splitFactor", symbol)
        if cash < 0:
            raise ValueError(f"Tiingo divCash cannot be negative for {symbol}")
        if split_factor <= 0:
            raise ValueError(f"Tiingo splitFactor must be positive for {symbol}")
        if cash > 0:
            events.append(
                KisDailyCorporateActionEvent(
                    symbol=symbol,
                    source_date=source_date,
                    mapped_kis_session_date=source_date,
                    event_kind="cash_distribution",
                    value=cash,
                )
            )
        if split_factor != 1:
            events.append(
                KisDailyCorporateActionEvent(
                    symbol=symbol,
                    source_date=source_date,
                    mapped_kis_session_date=source_date,
                    event_kind="split",
                    value=split_factor,
                )
            )

    expected = frozenset(expected_sessions)
    if observed_dates != expected:
        raise ValueError(f"Tiingo EOD session coverage is incomplete for {symbol}")
    ordered = tuple(
        sorted(
            events,
            key=lambda event: (
                event.mapped_kis_session_date,
                KIS_DAILY_CORPORATE_ACTION_EVENT_KINDS.index(event.event_kind),
            ),
        )
    )
    return _NormalizedTiingoResponse(
        symbol=symbol,
        response_hash=_sha256(raw_response),
        events=ordered,
    )


def _manifest(
    *,
    snapshot_dir: Path,
    dataset_hash: str,
    event_size_bytes: int,
    normalized: Mapping[str, _NormalizedTiingoResponse],
    catalog: KisPaperPrivateDailyCatalog,
    sessions: tuple[date, ...],
    retrieved_at_utc: datetime,
) -> dict[str, object]:
    return {
        "schema_version": KIS_DAILY_CORPORATE_ACTION_SCHEMA_VERSION,
        "kind": KIS_DAILY_CORPORATE_ACTION_KIND,
        "dataset_id": f"us_equities.kis_paper_private.daily_corporate_actions.{snapshot_dir.name}",
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "symbols": list(KIS_DAILY_CORPORATE_ACTION_SYMBOLS),
        "event_kinds": list(KIS_DAILY_CORPORATE_ACTION_EVENT_KINDS),
        "events": {
            "path": "events.csv",
            "sha256": dataset_hash,
            "size_bytes": event_size_bytes,
            "columns": list(KIS_DAILY_CORPORATE_ACTION_EVENT_COLUMNS),
        },
        "kis_daily_lineage": {
            "dataset_id": catalog.dataset_id,
            "dataset_hash": catalog.dataset_hash,
            "index_hash": catalog.index_hash,
            "adjustment_mode": catalog.adjustment_mode,
            "session_count": len(sessions),
            "first_session": sessions[0].isoformat(),
            "last_session": sessions[-1].isoformat(),
            "session_dates_sha256": kis_daily_session_dates_hash(sessions),
        },
        "source_contract": {
            "provider": "Tiingo standard EOD API",
            "endpoint_template": TIINGO_EOD_ENDPOINT,
            "normalization_fields": ["date", "divCash", "splitFactor"],
            "response_retention": "parsed_in_memory_only_no_raw_quotes_or_response_bytes",
            "date_semantics": "provider_date_must_equal_kis_observed_session_date",
        },
        "coverage": [
            {
                "symbol": symbol,
                "source_response_sha256": normalized[symbol].response_hash,
                "event_count": len(normalized[symbol].events),
            }
            for symbol in KIS_DAILY_CORPORATE_ACTION_SYMBOLS
        ],
        "mapping": dict(_MAPPING),
        "scope": dict(_SCOPE),
        "limitations": [
            "price_return_not_total_return",
            "single_source_event_omission_or_revision_not_independently_detected",
            "retrospective_non_point_in_time_event_availability",
        ],
        "snapshot_metadata": {
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
            "revision": "kis-qqq-spy-tiingo-events-v1",
        },
    }


def _validate_manifest(
    *,
    manifest: Mapping[str, object],
    snapshot: Path,
    dataset_hash: str,
    event_size_bytes: int,
    catalog: KisPaperPrivateDailyCatalog,
    sessions: tuple[date, ...],
) -> datetime:
    if (
        manifest.get("schema_version") != KIS_DAILY_CORPORATE_ACTION_SCHEMA_VERSION
        or manifest.get("kind") != KIS_DAILY_CORPORATE_ACTION_KIND
        or manifest.get("immutable_snapshot") is not True
        or manifest.get("dataset_id")
        != f"us_equities.kis_paper_private.daily_corporate_actions.{snapshot.name}"
        or manifest.get("dataset_hash") != dataset_hash
        or manifest.get("scope") != _SCOPE
    ):
        raise ValueError("KIS daily corporate-action manifest is incompatible")
    event_document = manifest.get("events")
    if not isinstance(event_document, dict) or (
        event_document.get("path"),
        event_document.get("sha256"),
        event_document.get("size_bytes"),
        event_document.get("columns"),
    ) != (
        "events.csv",
        dataset_hash,
        event_size_bytes,
        list(KIS_DAILY_CORPORATE_ACTION_EVENT_COLUMNS),
    ):
        raise ValueError("KIS daily corporate-action event document is invalid")
    lineage = manifest.get("kis_daily_lineage")
    expected_lineage = {
        "dataset_id": catalog.dataset_id,
        "dataset_hash": catalog.dataset_hash,
        "index_hash": catalog.index_hash,
        "adjustment_mode": catalog.adjustment_mode,
        "session_count": len(sessions),
        "first_session": sessions[0].isoformat(),
        "last_session": sessions[-1].isoformat(),
        "session_dates_sha256": kis_daily_session_dates_hash(sessions),
    }
    if lineage != expected_lineage:
        raise ValueError("KIS daily corporate-action lineage is incompatible")
    coverage = manifest.get("coverage")
    if not isinstance(coverage, list) or len(coverage) != len(KIS_DAILY_CORPORATE_ACTION_SYMBOLS):
        raise ValueError("KIS daily corporate-action coverage is invalid")
    for symbol, entry in zip(KIS_DAILY_CORPORATE_ACTION_SYMBOLS, coverage, strict=True):
        if not isinstance(entry, dict):
            raise ValueError("KIS daily corporate-action coverage is invalid")
        if (
            entry.get("symbol") != symbol
            or type(entry.get("event_count")) is not int
            or int(entry["event_count"]) < 1
        ):
            raise ValueError("KIS daily corporate-action coverage is invalid")
        _require_sha256(entry.get("source_response_sha256"), "source response hash")
    metadata = manifest.get("snapshot_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("KIS daily corporate-action metadata is invalid")
    return _parse_utc_datetime(metadata.get("retrieved_at_utc"), "retrieved_at_utc")


def _parse_events(
    *, event_bytes: bytes, sessions: tuple[date, ...]
) -> tuple[KisDailyCorporateActionEvent, ...]:
    try:
        reader = csv.DictReader(io.StringIO(event_bytes.decode("utf-8"), newline=""))
    except UnicodeDecodeError as error:
        raise ValueError("KIS daily corporate-action events must be UTF-8") from error
    if tuple(reader.fieldnames or ()) != KIS_DAILY_CORPORATE_ACTION_EVENT_COLUMNS:
        raise ValueError("KIS daily corporate-action event schema is invalid")
    session_set = frozenset(sessions)
    events: list[KisDailyCorporateActionEvent] = []
    previous: tuple[int, date, int] | None = None
    seen: set[tuple[str, date, str]] = set()
    for row in reader:
        event = KisDailyCorporateActionEvent(
            symbol=str(row.get("symbol") or "").strip().upper(),
            source_date=_parse_date(row.get("source_date"), "event source date"),
            mapped_kis_session_date=_parse_date(
                row.get("mapped_kis_session_date"), "mapped KIS session date"
            ),
            event_kind=str(row.get("event_kind") or "").strip(),
            value=_positive_decimal(row.get("value"), "event value"),
        )
        if event.mapped_kis_session_date not in session_set:
            raise ValueError("KIS daily corporate-action event maps to a non-session")
        duplicate_key = (event.symbol, event.source_date, event.event_kind)
        if duplicate_key in seen:
            raise ValueError("KIS daily corporate-action events contain duplicates")
        seen.add(duplicate_key)
        order = (
            KIS_DAILY_CORPORATE_ACTION_SYMBOLS.index(event.symbol),
            event.mapped_kis_session_date,
            KIS_DAILY_CORPORATE_ACTION_EVENT_KINDS.index(event.event_kind),
        )
        if previous is not None and order <= previous:
            raise ValueError("KIS daily corporate-action events are not ordered")
        previous = order
        events.append(event)
    if not events:
        raise ValueError("KIS daily corporate-action events are empty")
    return tuple(events)


def _validate_event_counts(
    *, manifest: Mapping[str, object], events: tuple[KisDailyCorporateActionEvent, ...]
) -> None:
    coverage = manifest["coverage"]
    assert isinstance(coverage, list)
    for symbol, entry in zip(KIS_DAILY_CORPORATE_ACTION_SYMBOLS, coverage, strict=True):
        assert isinstance(entry, dict)
        actual = sum(event.symbol == symbol for event in events)
        if entry["event_count"] != actual:
            raise ValueError("KIS daily corporate-action event count is inconsistent")


def _event_csv_bytes(events: tuple[KisDailyCorporateActionEvent, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=KIS_DAILY_CORPORATE_ACTION_EVENT_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for event in events:
        writer.writerow(
            {
                "symbol": event.symbol,
                "source_date": event.source_date.isoformat(),
                "mapped_kis_session_date": event.mapped_kis_session_date.isoformat(),
                "event_kind": event.event_kind,
                "value": format(event.value, "f"),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _validate_destination(
    *, destination: Path, market_data_root: Path, repo_root: Path | None
) -> None:
    try:
        root = market_data_root.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("KIS daily corporate-action market-data root is missing") from error
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("KIS daily corporate-action destination already exists")
    resolved_destination = destination.resolve(strict=False)
    if not resolved_destination.is_relative_to(root):
        raise ValueError("KIS daily corporate-action destination must stay under market_data")
    if not destination.name.startswith("snapshot="):
        raise ValueError("KIS daily corporate-action destination must use a snapshot directory")
    _assert_external_path(resolved_destination, repo_root=repo_root)
    usage = shutil.disk_usage(root)
    if usage.free / usage.total < 0.15:
        raise ValueError("KIS daily corporate-action acquisition would breach the free-space floor")


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.pending-", dir=destination.parent)
    )
    staging = pending_root / destination.name
    staging.mkdir()
    return staging


def _external_snapshot_dir(path: Path, *, repo_root: Path | None) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError("KIS daily corporate-action snapshot cannot be a symlink")
    try:
        snapshot = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("KIS daily corporate-action snapshot is missing") from error
    if not snapshot.is_dir():
        raise ValueError("KIS daily corporate-action snapshot is invalid")
    _assert_external_path(snapshot, repo_root=repo_root)
    return snapshot


def _assert_external_path(path: Path, *, repo_root: Path | None) -> None:
    candidate = Path(path).resolve(strict=False)
    if repo_root is not None:
        repository = Path(repo_root).resolve(strict=False)
        docker_market_data = Path("/app/market_data").resolve()
        if candidate == repository or candidate.is_relative_to(repository):
            if repository != Path("/app").resolve() or not candidate.is_relative_to(
                docker_market_data
            ):
                raise ValueError("KIS daily corporate-action data must stay outside Git")
    if any((parent / ".git").exists() for parent in (candidate, *candidate.parents)):
        raise ValueError("KIS daily corporate-action data must stay outside Git")


def _read_snapshot_file(snapshot: Path, path: Path, label: str) -> bytes:
    try:
        relative = path.relative_to(snapshot)
    except ValueError as error:
        raise ValueError(f"{label} must stay inside the snapshot") from error
    current = snapshot
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"{label} cannot use a symlink")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"{label} is missing") from error
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"{label} must be a regular snapshot file")
    return resolved.read_bytes()


def _tiingo_date(value: object, symbol: str) -> date:
    if not isinstance(value, str) or len(value) < 10 or not _DATE_RE.fullmatch(value[:10]):
        raise ValueError(f"Tiingo date is missing or malformed for {symbol}")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as error:
        raise ValueError(f"Tiingo date is missing or malformed for {symbol}") from error


def _tiingo_decimal(value: object, field: str, symbol: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}") from error
    if not decimal_value.is_finite():
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}")
    return decimal_value


def _positive_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"KIS daily corporate-action {label} is invalid")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"KIS daily corporate-action {label} is invalid") from error
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise ValueError(f"KIS daily corporate-action {label} is invalid")
    return decimal_value


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValueError(f"KIS daily corporate-action {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"KIS daily corporate-action {label} is invalid") from error


def _validate_session_span(start_session: date, end_session: date) -> None:
    if (
        type(start_session) is not date
        or type(end_session) is not date
        or start_session > end_session
    ):
        raise ValueError("KIS daily corporate-action session span is invalid")


def kis_daily_session_dates_hash(sessions: object) -> str:
    ordered = tuple(sorted(sessions))
    if not ordered or any(type(session) is not date for session in ordered):
        raise ValueError("KIS daily corporate-action sessions are invalid")
    return _sha256("\n".join(session.isoformat() for session in ordered).encode("utf-8"))


def _utc_datetime(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(value)
    ):
        raise ValueError(f"KIS daily corporate-action {label} must be UTC")
    return value


def _parse_utc_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"KIS daily corporate-action {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"KIS daily corporate-action {label} is invalid") from error
    return _utc_datetime(parsed, label)


def _format_utc(value: datetime) -> str:
    return _utc_datetime(value, "timestamp").isoformat().replace("+00:00", "Z")


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"KIS daily corporate-action {label} is invalid")
    return value


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _json_object(value: bytes, label: str) -> dict[str, object]:
    try:
        document = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} is invalid")
    return document


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

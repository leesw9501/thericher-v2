"""Immutable, development-only Tiingo standard-EOD full-history evidence."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .corporate_actions import CORPORATE_ACTION_SYMBOLS
from .tiingo_eod import (
    DEFAULT_MARKET_DATA_ROOT,
    MINIMUM_RETRIEVAL_LAG_DAYS,
    TIINGO_EOD_ENDPOINT,
    TiingoEodAcquisitionError,
    read_tiingo_api_token,
)

DEFAULT_TIINGO_FULL_HISTORY_SNAPSHOT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_full_history"
    / "canonical"
    / "tiingo_standard_eod"
)
FULL_HISTORY_DATASET_ID_PREFIX = "us_equities.fixed_etf_tiingo_eod_full_history"
FULL_HISTORY_REVISION = "tiingo-standard-eod-full-history-r1"
_RAW_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "div_cash",
    "split_factor",
)
_SCOPE = {
    "development_evidence_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "paper_trading_eligible": False,
}
_SOURCE_CONTRACT = {
    "provider": "Tiingo standard EOD API",
    "endpoint_template": TIINGO_EOD_ENDPOINT,
    "query_parameters": ["startDate", "endDate"],
    "raw_response_policy": "exact_per_symbol_bytes",
}
_DATA_SEMANTICS = {
    "raw_price_policy": "copy_raw_ohlcv_without_price_rescaling",
    "corporate_action_policy": "copy_divCash_and_splitFactor_without_derived_events",
    "normalization_fields": [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "divCash",
        "splitFactor",
    ],
    "adjusted_fields": "excluded_from_normalized_data",
}


class TiingoFullHistoryAcquisitionError(TiingoEodAcquisitionError):
    """A masked, fail-closed full-history Tiingo acquisition failure."""


class _RejectRedirect(HTTPRedirectHandler):
    """Prevent an Authorization header from being forwarded to another URL."""

    def redirect_request(
        self,
        _request: Request,
        _file: Any,
        _code: int,
        _message: str,
        _headers: Any,
        _new_url: str,
    ) -> Request:
        raise TiingoFullHistoryAcquisitionError("Tiingo full-history redirects are not allowed")


@dataclass(frozen=True, slots=True)
class TiingoFullHistoryRow:
    """One raw, unadjusted EOD record retained as source evidence."""

    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    div_cash: Decimal
    split_factor: Decimal


@dataclass(frozen=True, slots=True)
class TiingoFullHistoryEodSnapshot:
    """Offline-attested evidence, deliberately not a campaign or bar catalog."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    requested_start: date
    source_as_of: date
    retrieved_at_utc: datetime
    rows_by_symbol: Mapping[str, tuple[TiingoFullHistoryRow, ...]]


@dataclass(frozen=True, slots=True)
class TiingoFullHistorySnapshotResult:
    """Non-secret facts from a newly written immutable full-history snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    raw_hashes: Mapping[str, str]
    retrieved_at_utc: datetime
    requested_start: date
    source_as_of: date
    row_count: int


def default_tiingo_full_history_snapshot_dir(retrieval_date: date) -> Path:
    """Return a disjoint dated destination; write functions still prohibit overwrite."""

    return DEFAULT_TIINGO_FULL_HISTORY_SNAPSHOT_ROOT / (
        f"snapshot={retrieval_date.isoformat()}-tiingo-eod-full-history-r1"
    )


def fetch_tiingo_full_history_responses(
    *,
    env_path: Path,
    requested_start: date,
    source_as_of: date,
    timeout_seconds: float = 30.0,
) -> dict[str, bytes]:
    """Fetch exactly the approved raw responses once, without logging the token."""

    _validate_requested_window(requested_start, source_as_of)
    if timeout_seconds <= 0:
        raise ValueError("Tiingo timeout_seconds must be positive")
    token = read_tiingo_api_token(env_path)
    responses: dict[str, bytes] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        query = urlencode(
            {
                "startDate": requested_start.isoformat(),
                "endDate": source_as_of.isoformat(),
            }
        )
        request = Request(
            f"{TIINGO_EOD_ENDPOINT.format(symbol=symbol)}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Token {token}"},
        )
        try:
            with _open_without_redirect(request, timeout=timeout_seconds) as response:
                if getattr(response, "status", 200) != 200:
                    raise TiingoFullHistoryAcquisitionError(
                        f"Tiingo full-history request failed for {symbol}: unexpected status"
                    )
                payload = response.read()
        except HTTPError as exc:
            raise TiingoFullHistoryAcquisitionError(
                f"Tiingo full-history request failed for {symbol}: HTTP {exc.code}"
            ) from exc
        except (OSError, URLError) as exc:
            raise TiingoFullHistoryAcquisitionError(
                f"Tiingo full-history request failed for {symbol}"
            ) from exc
        if not isinstance(payload, bytes) or not payload:
            raise TiingoFullHistoryAcquisitionError(
                f"Tiingo full-history response is unavailable for {symbol}"
            )
        responses[symbol] = payload
    return responses


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)


def normalize_tiingo_full_history_response(
    *,
    symbol: str,
    raw_response: bytes,
    requested_start: date,
    source_as_of: date,
) -> tuple[TiingoFullHistoryRow, ...]:
    """Normalize raw fields only; adjusted provider fields never enter the evidence CSV."""

    _validate_requested_window(requested_start, source_as_of)
    requested_symbol = _requested_symbol(symbol)
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError(f"Tiingo full-history response is missing for {requested_symbol}")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Tiingo full-history response is not valid UTF-8 JSON for {requested_symbol}"
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(
            f"Tiingo full-history response must be a nonempty array for {requested_symbol}"
        )

    rows: list[TiingoFullHistoryRow] = []
    observed_dates: set[date] = set()
    previous_date: date | None = None
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Tiingo full-history row must be an object for {requested_symbol}")
        session_date = _tiingo_session_date(item.get("date"), requested_symbol)
        if session_date < requested_start or session_date > source_as_of:
            raise ValueError(
                f"Tiingo full-history row is outside the requested window for {requested_symbol}"
            )
        if session_date in observed_dates:
            raise ValueError(
                f"Tiingo full-history response has duplicate dates for {requested_symbol}"
            )
        if previous_date is not None and session_date <= previous_date:
            raise ValueError(
                "Tiingo full-history response dates are not strictly ascending for "
                f"{requested_symbol}"
            )
        prices = tuple(
            _tiingo_decimal(item.get(field), field, requested_symbol)
            for field in ("open", "high", "low", "close")
        )
        volume = _tiingo_decimal(item.get("volume"), "volume", requested_symbol)
        div_cash = _tiingo_decimal(item.get("divCash"), "divCash", requested_symbol)
        split_factor = _tiingo_decimal(item.get("splitFactor"), "splitFactor", requested_symbol)
        _validate_raw_values(
            *prices,
            volume,
            div_cash,
            split_factor,
            label=f"{requested_symbol} {session_date}",
        )
        rows.append(
            TiingoFullHistoryRow(
                symbol=requested_symbol,
                session_date=session_date,
                open=prices[0],
                high=prices[1],
                low=prices[2],
                close=prices[3],
                volume=volume,
                div_cash=div_cash,
                split_factor=split_factor,
            )
        )
        observed_dates.add(session_date)
        previous_date = session_date
    if rows[-1].session_date != source_as_of:
        raise ValueError(
            f"Tiingo full-history response does not reach source_as_of for {requested_symbol}"
        )
    return tuple(rows)


def build_tiingo_full_history_eod_snapshot(
    *,
    destination: Path,
    raw_responses: Mapping[str, bytes],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoFullHistorySnapshotResult:
    """Write one immutable external snapshot from already-fetched Tiingo bytes."""

    _validate_requested_window(requested_start, source_as_of)
    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    _assert_retrieval_lag(retrieved_at, source_as_of)
    _validate_destination(destination, market_data_root=market_data_root, repo_root=repo_root)
    if set(raw_responses) != set(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo full-history raw responses must contain exact fixed symbols")

    rows_by_symbol: dict[str, tuple[TiingoFullHistoryRow, ...]] = {}
    raw_hashes: dict[str, str] = {}
    raw_sizes: dict[str, int] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        raw = raw_responses[symbol]
        if not isinstance(raw, bytes):
            raise ValueError(f"Tiingo full-history raw response must be bytes for {symbol}")
        raw_hashes[symbol] = _sha256(raw)
        raw_sizes[symbol] = len(raw)
        rows_by_symbol[symbol] = normalize_tiingo_full_history_response(
            symbol=symbol,
            raw_response=raw,
            requested_start=requested_start,
            source_as_of=source_as_of,
        )
    _validate_common_coverage(rows_by_symbol)

    rows = tuple(row for symbol in CORPORATE_ACTION_SYMBOLS for row in rows_by_symbol[symbol])
    normalized_bytes = _gzip_bytes(_raw_csv_bytes(rows))
    dataset_hash = _sha256(normalized_bytes)
    destination_path = Path(destination)
    staging = _create_staging_directory(destination_path)
    try:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        for symbol in CORPORATE_ACTION_SYMBOLS:
            (raw_dir / f"{symbol}.json").write_bytes(raw_responses[symbol])
        (staging / "ohlcv_1d.csv.gz").write_bytes(normalized_bytes)
        manifest = _manifest(
            snapshot_dir=destination_path,
            dataset_hash=dataset_hash,
            normalized_size=len(normalized_bytes),
            raw_hashes=raw_hashes,
            raw_sizes=raw_sizes,
            rows_by_symbol=rows_by_symbol,
            requested_start=requested_start,
            source_as_of=source_as_of,
            retrieved_at_utc=retrieved_at,
        )
        manifest_bytes = _json_bytes(manifest)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        load_tiingo_full_history_eod_snapshot(
            staging,
            dataset_id=_dataset_id(destination_path),
            expected_dataset_hash=dataset_hash,
            expected_manifest_hash=_sha256(manifest_bytes),
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
        os.rename(staging, destination_path)
        staging.parent.rmdir()
    except Exception:
        if staging.parent.exists():
            shutil.rmtree(staging.parent)
        raise

    manifest_bytes = (destination_path / "manifest.json").read_bytes()
    snapshot = load_tiingo_full_history_eod_snapshot(
        destination_path,
        dataset_id=_dataset_id(destination_path),
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=_sha256(manifest_bytes),
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return TiingoFullHistorySnapshotResult(
        snapshot_dir=destination_path,
        dataset_id=snapshot.dataset_id,
        dataset_hash=snapshot.dataset_hash,
        manifest_hash=snapshot.manifest_hash,
        raw_hashes=MappingProxyType(dict(raw_hashes)),
        retrieved_at_utc=snapshot.retrieved_at_utc,
        requested_start=snapshot.requested_start,
        source_as_of=snapshot.source_as_of,
        row_count=sum(len(rows) for rows in snapshot.rows_by_symbol.values()),
    )


def acquire_tiingo_full_history_eod_snapshot(
    *,
    env_path: Path,
    destination: Path,
    requested_start: date,
    source_as_of: date,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    retrieved_at_utc: datetime | None = None,
    timeout_seconds: float = 30.0,
) -> TiingoFullHistorySnapshotResult:
    """Fetch once, then freeze an externally attested full-history evidence snapshot."""

    _validate_requested_window(requested_start, source_as_of)
    retrieved_at = _utc_datetime(retrieved_at_utc or datetime.now(UTC), "retrieved_at_utc")
    _assert_retrieval_lag(retrieved_at, source_as_of)
    _validate_destination(destination, market_data_root=market_data_root, repo_root=repo_root)
    responses = fetch_tiingo_full_history_responses(
        env_path=env_path,
        requested_start=requested_start,
        source_as_of=source_as_of,
        timeout_seconds=timeout_seconds,
    )
    return build_tiingo_full_history_eod_snapshot(
        destination=destination,
        raw_responses=responses,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def load_tiingo_full_history_eod_snapshot(
    snapshot_dir: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoFullHistoryEodSnapshot:
    """Rebuild and attest one snapshot offline without a token or network access."""

    snapshot = _snapshot_dir(snapshot_dir, market_data_root=market_data_root, repo_root=repo_root)
    if dataset_id != _dataset_id(snapshot):
        raise ValueError("Tiingo full-history dataset_id is inconsistent with its snapshot path")
    _validate_sha256(expected_dataset_hash, "expected_dataset_hash")
    _validate_sha256(expected_manifest_hash, "expected_manifest_hash")

    manifest_bytes = _read_snapshot_file(
        snapshot,
        snapshot / "manifest.json",
        "Tiingo full-history manifest",
    )
    manifest_hash = _sha256(manifest_bytes)
    if manifest_hash != expected_manifest_hash:
        raise ValueError("Tiingo full-history manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo full-history manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo full-history manifest must be an object")

    requested_start, source_as_of, retrieved_at = _validate_manifest_header(
        manifest,
        snapshot=snapshot,
        dataset_id=dataset_id,
        dataset_hash=expected_dataset_hash,
    )
    raw_entries = _validated_raw_entries(
        manifest,
        snapshot=snapshot,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
    )
    rows_by_symbol: dict[str, tuple[TiingoFullHistoryRow, ...]] = {}
    raw_hashes: dict[str, str] = {}
    raw_sizes: dict[str, int] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        entry = raw_entries[symbol]
        raw = _read_snapshot_file(snapshot, snapshot / "raw" / f"{symbol}.json", "Tiingo raw")
        if len(raw) != entry["size_bytes"] or _sha256(raw) != entry["sha256"]:
            raise ValueError(f"Tiingo full-history raw hash mismatch for {symbol}")
        rows_by_symbol[symbol] = normalize_tiingo_full_history_response(
            symbol=symbol,
            raw_response=raw,
            requested_start=requested_start,
            source_as_of=source_as_of,
        )
        raw_hashes[symbol] = entry["sha256"]
        raw_sizes[symbol] = entry["size_bytes"]
    _validate_common_coverage(rows_by_symbol)

    rows = tuple(row for symbol in CORPORATE_ACTION_SYMBOLS for row in rows_by_symbol[symbol])
    normalized_path = snapshot / "ohlcv_1d.csv.gz"
    normalized_bytes = _read_snapshot_file(snapshot, normalized_path, "Tiingo normalized data")
    actual_dataset_hash = _sha256(normalized_bytes)
    if actual_dataset_hash != expected_dataset_hash:
        raise ValueError("Tiingo full-history dataset hash mismatch")
    _validate_manifest_content(
        manifest,
        snapshot=snapshot,
        dataset_hash=actual_dataset_hash,
        normalized_size=len(normalized_bytes),
        raw_hashes=raw_hashes,
        raw_sizes=raw_sizes,
        rows_by_symbol=rows_by_symbol,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
    )
    try:
        canonical_bytes = gzip.decompress(normalized_bytes)
    except OSError as exc:
        raise ValueError("Tiingo full-history normalized data is not a valid gzip stream") from exc
    if canonical_bytes != _raw_csv_bytes(rows):
        raise ValueError("Tiingo full-history normalized data does not match attested raw bytes")

    return TiingoFullHistoryEodSnapshot(
        snapshot_dir=snapshot,
        dataset_id=dataset_id,
        dataset_hash=actual_dataset_hash,
        manifest_hash=manifest_hash,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
        rows_by_symbol=MappingProxyType(dict(rows_by_symbol)),
    )


def _validate_manifest_header(
    manifest: Mapping[str, Any],
    *,
    snapshot: Path,
    dataset_id: str,
    dataset_hash: str,
) -> tuple[date, date, datetime]:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "fixed_etf_tiingo_eod_full_history"
        or manifest.get("immutable_snapshot") is not True
        or manifest.get("symbols") != list(CORPORATE_ACTION_SYMBOLS)
        or manifest.get("symbol_order") != list(CORPORATE_ACTION_SYMBOLS)
        or manifest.get("source_contract") != _SOURCE_CONTRACT
        or manifest.get("data_semantics") != _DATA_SEMANTICS
        or manifest.get("scope") != _SCOPE
    ):
        raise ValueError("Tiingo full-history manifest contract is invalid")
    if _required_text(manifest.get("dataset_id"), "Tiingo full-history dataset_id") != dataset_id:
        raise ValueError("Tiingo full-history manifest dataset_id mismatch")
    if _required_sha256(
        manifest.get("dataset_hash"), "Tiingo full-history dataset_hash"
    ) != dataset_hash:
        raise ValueError("Tiingo full-history manifest dataset hash mismatch")
    metadata = manifest.get("snapshot_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Tiingo full-history snapshot metadata is missing")
    requested_start = _date_text(metadata.get("requested_start"), "requested_start")
    source_as_of = _date_text(metadata.get("source_as_of"), "source_as_of")
    retrieved_at = _utc_text(metadata.get("retrieved_at_utc"), "retrieved_at_utc")
    _validate_requested_window(requested_start, source_as_of)
    _assert_retrieval_lag(retrieved_at, source_as_of)
    if metadata != {
        "requested_start": requested_start.isoformat(),
        "source_as_of": source_as_of.isoformat(),
        "retrieved_at_utc": _format_utc(retrieved_at),
        "minimum_retrieval_lag_days": MINIMUM_RETRIEVAL_LAG_DAYS,
        "retrieval_lag_policy": "minimum_calendar_days_after_source_as_of_v1",
        "revision": FULL_HISTORY_REVISION,
    }:
        raise ValueError("Tiingo full-history snapshot metadata is invalid")
    _assert_manifest_path_tail(
        manifest.get("normalized_data", {}).get("path")
        if isinstance(manifest.get("normalized_data"), dict)
        else None,
        snapshot_name=snapshot.name,
        parts=("ohlcv_1d.csv.gz",),
        label="Tiingo full-history normalized data path",
    )
    return requested_start, source_as_of, retrieved_at


def _validated_raw_entries(
    manifest: Mapping[str, Any],
    *,
    snapshot: Path,
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> dict[str, Mapping[str, Any]]:
    value = manifest.get("raw_sources")
    if not isinstance(value, list) or len(value) != len(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo full-history raw evidence is invalid")
    entries: dict[str, Mapping[str, Any]] = {}
    for expected_symbol, entry in zip(CORPORATE_ACTION_SYMBOLS, value, strict=True):
        if not isinstance(entry, dict) or entry.get("symbol") != expected_symbol:
            raise ValueError("Tiingo full-history raw evidence is invalid")
        required = {
            "symbol": expected_symbol,
            "source_id": f"tiingo-standard-eod-full-history-{expected_symbol.lower()}",
            "provider": "Tiingo standard EOD API",
            "source_url": TIINGO_EOD_ENDPOINT.format(symbol=expected_symbol),
            "source_kind": "licensed_api",
            "acquisition_mode": "authorized_api",
            "use_scope": "private_internal_use",
            "rights_status": "operator_authorized_private_use",
            "requested_start": requested_start.isoformat(),
            "source_as_of": source_as_of.isoformat(),
            "filename": f"{expected_symbol}.json",
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
        }
        if any(entry.get(key) != expected for key, expected in required.items()):
            raise ValueError(f"Tiingo full-history raw evidence is invalid for {expected_symbol}")
        _assert_manifest_path_tail(
            entry.get("path"),
            snapshot_name=snapshot.name,
            parts=("raw", f"{expected_symbol}.json"),
            label=f"Tiingo full-history raw path for {expected_symbol}",
        )
        _required_sha256(entry.get("sha256"), f"Tiingo full-history raw hash for {expected_symbol}")
        size = entry.get("size_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"Tiingo full-history raw size is invalid for {expected_symbol}")
        entries[expected_symbol] = entry
    return entries


def _validate_manifest_content(
    manifest: Mapping[str, Any],
    *,
    snapshot: Path,
    dataset_hash: str,
    normalized_size: int,
    raw_hashes: Mapping[str, str],
    raw_sizes: Mapping[str, int],
    rows_by_symbol: Mapping[str, tuple[TiingoFullHistoryRow, ...]],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> None:
    normalized = manifest.get("normalized_data")
    expected_normalized = {
        "size_bytes": normalized_size,
        "sha256": dataset_hash,
        "schema": list(_RAW_COLUMNS),
        "format": "csv.gz",
        "ordering": "symbol_order_then_date_ascending",
    }
    if not isinstance(normalized, dict) or any(
        normalized.get(key) != expected for key, expected in expected_normalized.items()
    ):
        raise ValueError("Tiingo full-history normalized evidence is invalid")
    coverage = manifest.get("coverage_by_symbol")
    if coverage != _coverage_by_symbol(rows_by_symbol):
        raise ValueError("Tiingo full-history coverage evidence is invalid")
    expected_raw = _raw_sources(
        snapshot_dir=snapshot,
        raw_hashes=raw_hashes,
        raw_sizes=raw_sizes,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at_utc,
    )
    raw_sources = manifest.get("raw_sources")
    if not isinstance(raw_sources, list) or len(raw_sources) != len(expected_raw):
        raise ValueError("Tiingo full-history raw evidence is invalid")
    for actual, expected in zip(raw_sources, expected_raw, strict=True):
        if not isinstance(actual, dict):
            raise ValueError("Tiingo full-history raw evidence is invalid")
        actual_without_path = {key: value for key, value in actual.items() if key != "path"}
        expected_without_path = {key: value for key, value in expected.items() if key != "path"}
        if actual_without_path != expected_without_path:
            raise ValueError("Tiingo full-history raw evidence is invalid")


def _manifest(
    *,
    snapshot_dir: Path,
    dataset_hash: str,
    normalized_size: int,
    raw_hashes: Mapping[str, str],
    raw_sizes: Mapping[str, int],
    rows_by_symbol: Mapping[str, tuple[TiingoFullHistoryRow, ...]],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "fixed_etf_tiingo_eod_full_history",
        "dataset_id": _dataset_id(snapshot_dir),
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "symbols": list(CORPORATE_ACTION_SYMBOLS),
        "symbol_order": list(CORPORATE_ACTION_SYMBOLS),
        "normalized_data": {
            "path": str(snapshot_dir / "ohlcv_1d.csv.gz"),
            "size_bytes": normalized_size,
            "sha256": dataset_hash,
            "schema": list(_RAW_COLUMNS),
            "format": "csv.gz",
            "ordering": "symbol_order_then_date_ascending",
        },
        "raw_sources": _raw_sources(
            snapshot_dir=snapshot_dir,
            raw_hashes=raw_hashes,
            raw_sizes=raw_sizes,
            requested_start=requested_start,
            source_as_of=source_as_of,
            retrieved_at_utc=retrieved_at_utc,
        ),
        "coverage_by_symbol": _coverage_by_symbol(rows_by_symbol),
        "snapshot_metadata": {
            "requested_start": requested_start.isoformat(),
            "source_as_of": source_as_of.isoformat(),
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
            "minimum_retrieval_lag_days": MINIMUM_RETRIEVAL_LAG_DAYS,
            "retrieval_lag_policy": "minimum_calendar_days_after_source_as_of_v1",
            "revision": FULL_HISTORY_REVISION,
        },
        "source_contract": dict(_SOURCE_CONTRACT),
        "data_semantics": dict(_DATA_SEMANTICS),
        "scope": dict(_SCOPE),
    }


def _raw_sources(
    *,
    snapshot_dir: Path,
    raw_hashes: Mapping[str, str],
    raw_sizes: Mapping[str, int],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "source_id": f"tiingo-standard-eod-full-history-{symbol.lower()}",
            "provider": "Tiingo standard EOD API",
            "source_url": TIINGO_EOD_ENDPOINT.format(symbol=symbol),
            "source_kind": "licensed_api",
            "acquisition_mode": "authorized_api",
            "use_scope": "private_internal_use",
            "rights_status": "operator_authorized_private_use",
            "requested_start": requested_start.isoformat(),
            "source_as_of": source_as_of.isoformat(),
            "filename": f"{symbol}.json",
            "path": str(snapshot_dir / "raw" / f"{symbol}.json"),
            "sha256": raw_hashes[symbol],
            "size_bytes": raw_sizes[symbol],
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
        }
        for symbol in CORPORATE_ACTION_SYMBOLS
    ]


def _coverage_by_symbol(
    rows_by_symbol: Mapping[str, tuple[TiingoFullHistoryRow, ...]],
) -> dict[str, dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        rows = rows_by_symbol[symbol]
        if not rows:
            raise ValueError(f"Tiingo full-history response is empty for {symbol}")
        session_text = "".join(f"{row.session_date.isoformat()}\n" for row in rows).encode("ascii")
        coverage[symbol] = {
            "session_count": len(rows),
            "first_session": rows[0].session_date.isoformat(),
            "last_session": rows[-1].session_date.isoformat(),
            "session_dates_sha256": _sha256(session_text),
        }
    return coverage


def _validate_common_coverage(
    rows_by_symbol: Mapping[str, tuple[TiingoFullHistoryRow, ...]],
) -> None:
    common_start = max(
        rows_by_symbol[symbol][0].session_date for symbol in CORPORATE_ACTION_SYMBOLS
    )
    expected_dates = frozenset(
        row.session_date
        for row in rows_by_symbol[CORPORATE_ACTION_SYMBOLS[0]]
        if row.session_date >= common_start
    )
    for symbol in CORPORATE_ACTION_SYMBOLS[1:]:
        observed_dates = frozenset(
            row.session_date for row in rows_by_symbol[symbol] if row.session_date >= common_start
        )
        if observed_dates != expected_dates:
            raise ValueError("Tiingo full-history common session coverage is inconsistent")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> None:
    root = Path(market_data_root).resolve(strict=True)
    requested = Path(destination)
    if requested.is_symlink() or requested.exists():
        raise FileExistsError("Tiingo full-history destination already exists or is a symlink")
    resolved = requested.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("Tiingo full-history destination must be under market_data_root")
    if not requested.name.startswith("snapshot="):
        raise ValueError("Tiingo full-history destination must use a snapshot= directory")
    _assert_external_path(resolved, repo_root=repo_root)
    _check_free_space(root)


def _snapshot_dir(
    path: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> Path:
    root = Path(market_data_root).resolve(strict=True)
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError("Tiingo full-history snapshot cannot be a symlink")
    try:
        snapshot = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("Tiingo full-history snapshot directory is missing") from exc
    if not snapshot.is_dir() or not snapshot.is_relative_to(root):
        raise ValueError("Tiingo full-history snapshot must be under market_data_root")
    if not snapshot.name.startswith("snapshot="):
        raise ValueError("Tiingo full-history snapshot must use a snapshot= directory")
    _assert_external_path(snapshot, repo_root=repo_root)
    return snapshot


def _check_free_space(root: Path) -> None:
    usage = shutil.disk_usage(root)
    free_ratio = usage.free / usage.total
    if free_ratio < 0.15:
        raise ValueError(
            "Tiingo full-history acquisition would breach the market-data free-space floor"
        )
    if free_ratio < 0.20:
        warnings.warn(
            "Tiingo full-history acquisition is below the 20% market-data free-space warning level",
            RuntimeWarning,
            stacklevel=3,
        )


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.pending-", dir=destination.parent)
    )
    staging = pending_root / destination.name
    staging.mkdir()
    return staging


def _assert_external_path(path: Path, *, repo_root: Path | None) -> None:
    candidate = Path(path).resolve(strict=False)
    if repo_root is not None:
        root = Path(repo_root).resolve(strict=False)
        docker_market_data = Path("/app/market_data").resolve()
        if candidate == root or candidate.is_relative_to(root):
            if root != Path("/app").resolve() or not candidate.is_relative_to(docker_market_data):
                raise ValueError("Tiingo full-history data must be outside Git")
    if any((parent / ".git").exists() for parent in (candidate, *candidate.parents)):
        raise ValueError("Tiingo full-history data must be outside Git")


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


def _validate_requested_window(requested_start: date, source_as_of: date) -> None:
    if type(requested_start) is not date or type(source_as_of) is not date:
        raise ValueError("Tiingo full-history requested dates must be dates")
    if requested_start > source_as_of:
        raise ValueError("Tiingo full-history requested window is invalid")


def _assert_retrieval_lag(retrieved_at_utc: datetime, source_as_of: date) -> None:
    earliest = source_as_of + timedelta(days=MINIMUM_RETRIEVAL_LAG_DAYS)
    if retrieved_at_utc.date() < earliest:
        raise ValueError("Tiingo full-history retrieval is too close to source_as_of")


def _requested_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if symbol not in CORPORATE_ACTION_SYMBOLS:
        raise ValueError("Tiingo full-history symbol must be one of SPY, QQQ, IWM")
    return symbol


def _tiingo_session_date(value: object, symbol: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Tiingo date is missing or malformed for {symbol}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Tiingo date is missing or malformed for {symbol}") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != UTC.utcoffset(parsed)
        or parsed.timetz().replace(tzinfo=None) != time()
    ):
        raise ValueError(f"Tiingo date is missing or malformed for {symbol}")
    return parsed.date()


def _tiingo_decimal(value: object, field: str, symbol: str) -> Decimal:
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, str)):
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}")
    return parsed


def _validate_raw_values(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: Decimal,
    div_cash: Decimal,
    split_factor: Decimal,
    *,
    label: str,
) -> None:
    prices = (open_price, high_price, low_price, close_price)
    if any(price <= 0 for price in prices):
        raise ValueError(f"Tiingo raw price must be positive for {label}")
    if volume < 0:
        raise ValueError(f"Tiingo raw volume cannot be negative for {label}")
    if high_price < max(prices) or low_price > min(prices):
        raise ValueError(f"Tiingo raw OHLC range is invalid for {label}")
    if div_cash < 0:
        raise ValueError(f"Tiingo divCash cannot be negative for {label}")
    if split_factor <= 0:
        raise ValueError(f"Tiingo splitFactor must be positive for {label}")


def _raw_csv_bytes(rows: tuple[TiingoFullHistoryRow, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_RAW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "symbol": row.symbol,
                "date": row.session_date.isoformat(),
                "open": format(row.open, "f"),
                "high": format(row.high, "f"),
                "low": format(row.low, "f"),
                "close": format(row.close, "f"),
                "volume": format(row.volume, "f"),
                "div_cash": format(row.div_cash, "f"),
                "split_factor": format(row.split_factor, "f"),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _dataset_id(snapshot_dir: Path) -> str:
    return f"{FULL_HISTORY_DATASET_ID_PREFIX}.{Path(snapshot_dir).name}"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _required_text(value: object, label: str) -> str:
    text = str(value or "")
    if not text or text != text.strip():
        raise ValueError(f"{label} is required")
    return text


def _required_sha256(value: object, label: str) -> str:
    text = _required_text(value, label)
    if not _is_sha256(text):
        raise ValueError(f"{label} is invalid")
    return text


def _validate_sha256(value: object, label: str) -> None:
    _required_sha256(value, label)


def _is_sha256(value: str) -> bool:
    return len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value[7:]
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _date_text(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo full-history {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Tiingo full-history {label} is invalid") from exc


def _utc_text(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo full-history {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Tiingo full-history {label} is invalid") from exc
    return _utc_datetime(parsed, label)


def _assert_manifest_path_tail(
    value: object,
    *,
    snapshot_name: str,
    parts: tuple[str, ...],
    label: str,
) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    path_parts = PurePosixPath(value.replace("\\", "/")).parts
    if len(path_parts) < len(parts) + 1 or tuple(path_parts[-(len(parts) + 1) :]) != (
        snapshot_name,
        *parts,
    ):
        raise ValueError(f"{label} is invalid")

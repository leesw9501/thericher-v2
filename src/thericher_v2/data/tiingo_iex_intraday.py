"""Immutable, source-attested Tiingo IEX 5-minute evidence for fixed ETFs.

This module deliberately stops at Data ownership.  It does not register a
provider, create ``CatalogedBars``, or expose a campaign, model, or paper path.
"""

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
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from thericher_v2.contracts import Bar, Timeframe, require_utc

from .corporate_actions import CORPORATE_ACTION_SYMBOLS
from .tiingo_eod import read_tiingo_api_token

DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
DEFAULT_TIINGO_IEX_INTRADAY_SNAPSHOT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_intraday"
    / "canonical"
    / "tiingo_iex_5m"
)
TIINGO_IEX_INTRADAY_ENDPOINT = "https://api.tiingo.com/iex/{symbol}/prices"
TIINGO_IEX_INTRADAY_DATASET_ID_PREFIX = "us_equities.fixed_etf_tiingo_iex_intraday.5m"
TIINGO_IEX_INTRADAY_REVISION = "tiingo-iex-5m-r1"
TIINGO_IEX_INTRADAY_TIMEFRAME = Timeframe.M5
TIINGO_IEX_INTRADAY_COLUMNS = ("open", "high", "low", "close", "volume")
_CANONICAL_COLUMNS = (
    "symbol",
    "start_ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_MIN_COMMON_SESSIONS = 20
_SOURCE_CONTRACT = {
    "provider": "Tiingo IEX historical intraday API",
    "endpoint_template": TIINGO_IEX_INTRADAY_ENDPOINT,
    "source_kind": "licensed_api",
    "venue_scope": "IEX-only OHLCV; not consolidated market data",
    "history_basis": "provider documents intraday history from August 2017",
    "use_scope": "operator-approved private internal use",
    "request_policy": {
        "resampleFreq": "5min",
        "columns": list(TIINGO_IEX_INTRADAY_COLUMNS),
        "afterHours": False,
        "forceFill": False,
    },
}
_DATA_SEMANTICS = {
    "timeframe": "5m",
    "normalized_fields": list(_CANONICAL_COLUMNS),
    "timestamp_policy": (
        "provider date is preserved as UTC start_ts for local Bar ordering; "
        "provider documentation does not establish a bar-start or bar-end assertion"
    ),
    "session_date_policy": "US Eastern civil date using post-2007 U.S. DST rules",
    "gap_policy": "preserve returned gaps; do not impute or force-fill",
    "adjustment_policy": "OHLCV-only response; no adjusted or corporate-action lineage",
}
_SCOPE = {
    "descriptive_replay_evidence_only": True,
    "training_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
    "campaign_eligible": False,
    "paper_trading_eligible": False,
    "profitability_evidence": False,
}


class TiingoIexIntradayAcquisitionError(ValueError):
    """A masked, fail-closed Tiingo IEX intraday acquisition failure."""


class _RejectRedirect(HTTPRedirectHandler):
    """Keep the authorized request on Tiingo's expected HTTPS host."""

    def redirect_request(
        self,
        _request: Request,
        _file: Any,
        _code: int,
        _message: str,
        _headers: Any,
        _new_url: str,
    ) -> Request:
        raise TiingoIexIntradayAcquisitionError("Tiingo IEX redirects are not allowed")


@dataclass(frozen=True, slots=True)
class TiingoIexIntradaySnapshot:
    """Offline-attested Data evidence with no provider or research adapter."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    requested_start: date
    source_as_of: date
    retrieved_at_utc: datetime
    bars_by_symbol: Mapping[str, tuple[Bar, ...]]


@dataclass(frozen=True, slots=True)
class TiingoIexIntradaySnapshotResult:
    """Non-secret facts from one immutable Tiingo IEX snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    raw_hashes: Mapping[str, str]
    requested_start: date
    source_as_of: date
    retrieved_at_utc: datetime
    row_count: int
    common_session_count: int


def default_tiingo_iex_intraday_snapshot_dir(retrieval_date: date) -> Path:
    """Return the disjoint destination for one date-stamped fixed-ETF snapshot."""

    if type(retrieval_date) is not date:
        raise ValueError("retrieval_date must be a date")
    return DEFAULT_TIINGO_IEX_INTRADAY_SNAPSHOT_ROOT / (
        f"snapshot={retrieval_date.isoformat()}-{TIINGO_IEX_INTRADAY_REVISION}"
    )


def fetch_tiingo_iex_intraday_responses(
    *,
    env_path: Path,
    requested_start: date,
    source_as_of: date,
    timeout_seconds: float = 120.0,
) -> dict[str, bytes]:
    """Fetch exactly one fixed 5-minute response per approved ETF symbol."""

    _validate_requested_window(requested_start, source_as_of)
    if timeout_seconds <= 0:
        raise ValueError("Tiingo IEX timeout_seconds must be positive")
    token = read_tiingo_api_token(env_path)
    responses: dict[str, bytes] = {}
    query = _request_query(requested_start, source_as_of)
    for symbol in CORPORATE_ACTION_SYMBOLS:
        request = Request(
            f"{TIINGO_IEX_INTRADAY_ENDPOINT.format(symbol=symbol)}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Token {token}"},
        )
        try:
            with _open_without_redirect(request, timeout=timeout_seconds) as response:
                if getattr(response, "status", 200) != 200:
                    raise TiingoIexIntradayAcquisitionError(
                        f"Tiingo IEX request failed for {symbol}: unexpected status"
                    )
                payload = response.read()
        except HTTPError as exc:
            raise TiingoIexIntradayAcquisitionError(
                f"Tiingo IEX request failed for {symbol}: HTTP {exc.code}"
            ) from exc
        except (OSError, URLError) as exc:
            raise TiingoIexIntradayAcquisitionError(
                f"Tiingo IEX request failed for {symbol}"
            ) from exc
        if not isinstance(payload, bytes) or not payload:
            raise TiingoIexIntradayAcquisitionError(
                f"Tiingo IEX response is unavailable for {symbol}"
            )
        responses[symbol] = payload
    return responses


def acquire_tiingo_iex_intraday_snapshot(
    *,
    env_path: Path,
    destination: Path,
    requested_start: date,
    source_as_of: date,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    retrieved_at_utc: datetime | None = None,
    timeout_seconds: float = 120.0,
) -> TiingoIexIntradaySnapshotResult:
    """Fetch the approved responses once, then freeze one external snapshot."""

    _validate_requested_window(requested_start, source_as_of)
    retrieved_at = _utc_datetime(retrieved_at_utc or datetime.now(UTC), "retrieved_at_utc")
    _validate_destination(destination, market_data_root=market_data_root, repo_root=repo_root)
    responses = fetch_tiingo_iex_intraday_responses(
        env_path=env_path,
        requested_start=requested_start,
        source_as_of=source_as_of,
        timeout_seconds=timeout_seconds,
    )
    return build_tiingo_iex_intraday_snapshot(
        destination=destination,
        raw_responses=responses,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def build_tiingo_iex_intraday_snapshot(
    *,
    destination: Path,
    raw_responses: Mapping[str, bytes],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoIexIntradaySnapshotResult:
    """Write and attest an immutable snapshot from already-fetched raw bytes."""

    _validate_requested_window(requested_start, source_as_of)
    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    _validate_destination(destination, market_data_root=market_data_root, repo_root=repo_root)
    if set(raw_responses) != set(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo IEX raw responses must contain exact fixed symbols")

    bars_by_symbol: dict[str, tuple[Bar, ...]] = {}
    raw_hashes: dict[str, str] = {}
    raw_sizes: dict[str, int] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        raw = raw_responses[symbol]
        if not isinstance(raw, bytes):
            raise ValueError(f"Tiingo IEX raw response must be bytes for {symbol}")
        raw_hashes[symbol] = _sha256(raw)
        raw_sizes[symbol] = len(raw)
        bars_by_symbol[symbol] = normalize_tiingo_iex_intraday_response(
            symbol=symbol,
            raw_response=raw,
            requested_start=requested_start,
            source_as_of=source_as_of,
        )
    common_sessions = _validate_common_session_coverage(bars_by_symbol)

    ordered_bars = tuple(
        bar for symbol in CORPORATE_ACTION_SYMBOLS for bar in bars_by_symbol[symbol]
    )
    normalized_bytes = _gzip_bytes(_canonical_csv_bytes(ordered_bars))
    dataset_hash = _sha256(normalized_bytes)
    destination_path = Path(destination)
    staging = _create_staging_directory(destination_path)
    try:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        for symbol in CORPORATE_ACTION_SYMBOLS:
            (raw_dir / f"{symbol}.json").write_bytes(raw_responses[symbol])
        (staging / "ohlcv_5m.csv.gz").write_bytes(normalized_bytes)
        manifest = _manifest(
            snapshot_dir=destination_path,
            dataset_hash=dataset_hash,
            normalized_size=len(normalized_bytes),
            raw_hashes=raw_hashes,
            raw_sizes=raw_sizes,
            bars_by_symbol=bars_by_symbol,
            common_sessions=common_sessions,
            requested_start=requested_start,
            source_as_of=source_as_of,
            retrieved_at_utc=retrieved_at,
        )
        manifest_bytes = _json_bytes(manifest)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        load_tiingo_iex_intraday_snapshot(
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
    snapshot = load_tiingo_iex_intraday_snapshot(
        destination_path,
        dataset_id=_dataset_id(destination_path),
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=_sha256(manifest_bytes),
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    return TiingoIexIntradaySnapshotResult(
        snapshot_dir=destination_path,
        dataset_id=snapshot.dataset_id,
        dataset_hash=snapshot.dataset_hash,
        manifest_hash=snapshot.manifest_hash,
        raw_hashes=MappingProxyType(dict(raw_hashes)),
        requested_start=snapshot.requested_start,
        source_as_of=snapshot.source_as_of,
        retrieved_at_utc=snapshot.retrieved_at_utc,
        row_count=sum(len(bars) for bars in snapshot.bars_by_symbol.values()),
        common_session_count=len(common_sessions),
    )


def load_tiingo_iex_intraday_snapshot(
    snapshot_dir: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoIexIntradaySnapshot:
    """Rebuild the canonical 5-minute data from raw bytes without external access."""

    snapshot = _snapshot_dir(snapshot_dir, market_data_root=market_data_root, repo_root=repo_root)
    if dataset_id != _dataset_id(snapshot):
        raise ValueError("Tiingo IEX dataset_id is inconsistent with its snapshot path")
    _validate_sha256(expected_dataset_hash, "expected_dataset_hash")
    _validate_sha256(expected_manifest_hash, "expected_manifest_hash")

    manifest_bytes = _read_snapshot_file(
        snapshot,
        snapshot / "manifest.json",
        "Tiingo IEX manifest",
    )
    manifest_hash = _sha256(manifest_bytes)
    if manifest_hash != expected_manifest_hash:
        raise ValueError("Tiingo IEX manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo IEX manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo IEX manifest must be an object")

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
    bars_by_symbol: dict[str, tuple[Bar, ...]] = {}
    raw_hashes: dict[str, str] = {}
    raw_sizes: dict[str, int] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        entry = raw_entries[symbol]
        raw = _read_snapshot_file(snapshot, snapshot / "raw" / f"{symbol}.json", "Tiingo IEX raw")
        if len(raw) != entry["size_bytes"] or _sha256(raw) != entry["sha256"]:
            raise ValueError(f"Tiingo IEX raw hash mismatch for {symbol}")
        bars_by_symbol[symbol] = normalize_tiingo_iex_intraday_response(
            symbol=symbol,
            raw_response=raw,
            requested_start=requested_start,
            source_as_of=source_as_of,
        )
        raw_hashes[symbol] = entry["sha256"]
        raw_sizes[symbol] = entry["size_bytes"]
    common_sessions = _validate_common_session_coverage(bars_by_symbol)

    ordered_bars = tuple(
        bar for symbol in CORPORATE_ACTION_SYMBOLS for bar in bars_by_symbol[symbol]
    )
    normalized_path = snapshot / "ohlcv_5m.csv.gz"
    normalized_bytes = _read_snapshot_file(snapshot, normalized_path, "Tiingo IEX normalized data")
    actual_dataset_hash = _sha256(normalized_bytes)
    if actual_dataset_hash != expected_dataset_hash:
        raise ValueError("Tiingo IEX dataset hash mismatch")
    if normalized_bytes != _gzip_bytes(_canonical_csv_bytes(ordered_bars)):
        raise ValueError("Tiingo IEX normalized data does not match attested raw bytes")
    _validate_manifest_content(
        manifest,
        snapshot=snapshot,
        dataset_hash=actual_dataset_hash,
        normalized_size=len(normalized_bytes),
        raw_hashes=raw_hashes,
        raw_sizes=raw_sizes,
        bars_by_symbol=bars_by_symbol,
        common_sessions=common_sessions,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
    )
    return TiingoIexIntradaySnapshot(
        snapshot_dir=snapshot,
        dataset_id=dataset_id,
        dataset_hash=actual_dataset_hash,
        manifest_hash=manifest_hash,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at,
        bars_by_symbol=MappingProxyType(dict(bars_by_symbol)),
    )


def normalize_tiingo_iex_intraday_response(
    *,
    symbol: str,
    raw_response: bytes,
    requested_start: date,
    source_as_of: date,
) -> tuple[Bar, ...]:
    """Parse the selected provider fields while preserving timestamp uncertainty."""

    _validate_requested_window(requested_start, source_as_of)
    requested_symbol = _requested_symbol(symbol)
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError(f"Tiingo IEX response is missing for {requested_symbol}")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Tiingo IEX response is not valid UTF-8 JSON for {requested_symbol}"
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Tiingo IEX response must be a nonempty array for {requested_symbol}")

    bars: list[Bar] = []
    observed_timestamps: set[datetime] = set()
    previous_timestamp: datetime | None = None
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Tiingo IEX row must be an object for {requested_symbol}")
        timestamp = _tiingo_timestamp(item.get("date"), requested_symbol)
        if timestamp in observed_timestamps:
            raise ValueError(f"Tiingo IEX response has duplicate timestamps for {requested_symbol}")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError(
                f"Tiingo IEX response timestamps are not strictly ascending for {requested_symbol}"
            )
        session_date = _validate_intraday_timestamp(timestamp, requested_symbol)
        if session_date < requested_start or session_date > source_as_of:
            raise ValueError(
                f"Tiingo IEX row is outside the requested window for {requested_symbol}"
            )
        prices = tuple(
            _tiingo_decimal(item.get(field), field, requested_symbol)
            for field in ("open", "high", "low", "close")
        )
        volume = _tiingo_decimal(item.get("volume"), "volume", requested_symbol)
        try:
            bar = Bar(
                symbol=requested_symbol,
                market="US",
                timeframe=TIINGO_IEX_INTRADAY_TIMEFRAME,
                start_ts=timestamp,
                open=prices[0],
                high=prices[1],
                low=prices[2],
                close=prices[3],
                volume=volume,
                complete=True,
            )
        except ValueError as exc:
            raise ValueError(f"Tiingo IEX OHLCV is invalid for {requested_symbol}") from exc
        bars.append(bar)
        observed_timestamps.add(timestamp)
        previous_timestamp = timestamp
    if _new_york_session_date(bars[-1].start_ts) != source_as_of:
        raise ValueError(f"Tiingo IEX response does not reach source_as_of for {requested_symbol}")
    return tuple(bars)


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)


def _request_query(requested_start: date, source_as_of: date) -> str:
    return urlencode(
        {
            "startDate": requested_start.isoformat(),
            "endDate": source_as_of.isoformat(),
            "resampleFreq": "5min",
            "columns": ",".join(TIINGO_IEX_INTRADAY_COLUMNS),
            "afterHours": "false",
            "forceFill": "false",
        }
    )


def _manifest(
    *,
    snapshot_dir: Path,
    dataset_hash: str,
    normalized_size: int,
    raw_hashes: Mapping[str, str],
    raw_sizes: Mapping[str, int],
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
    common_sessions: frozenset[date],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "fixed_etf_tiingo_iex_intraday",
        "dataset_id": _dataset_id(snapshot_dir),
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "symbols": list(CORPORATE_ACTION_SYMBOLS),
        "symbol_order": list(CORPORATE_ACTION_SYMBOLS),
        "normalized_data": {
            "path": str(snapshot_dir / "ohlcv_5m.csv.gz"),
            "size_bytes": normalized_size,
            "sha256": dataset_hash,
            "schema": list(_CANONICAL_COLUMNS),
            "format": "csv.gz",
            "ordering": "symbol_order_then_start_ts_ascending",
        },
        "raw_sources": _raw_sources(
            snapshot_dir=snapshot_dir,
            raw_hashes=raw_hashes,
            raw_sizes=raw_sizes,
            requested_start=requested_start,
            source_as_of=source_as_of,
            retrieved_at_utc=retrieved_at_utc,
        ),
        "coverage_by_symbol": _coverage_by_symbol(bars_by_symbol),
        "common_session_coverage": {
            "session_count": len(common_sessions),
            "first_session": min(common_sessions).isoformat(),
            "last_session": max(common_sessions).isoformat(),
            "session_dates_sha256": _date_set_hash(common_sessions),
            "minimum_required_session_count": _MIN_COMMON_SESSIONS,
        },
        "snapshot_metadata": {
            "requested_start": requested_start.isoformat(),
            "source_as_of": source_as_of.isoformat(),
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
            "revision": TIINGO_IEX_INTRADAY_REVISION,
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
    request = _query_record(requested_start, source_as_of)
    return [
        {
            "symbol": symbol,
            "source_id": f"tiingo-iex-intraday-5m-{symbol.lower()}",
            "provider": "Tiingo IEX historical intraday API",
            "source_url": TIINGO_IEX_INTRADAY_ENDPOINT.format(symbol=symbol),
            "source_kind": "licensed_api",
            "acquisition_mode": "operator_authorized_api",
            "use_scope": "private_internal_use",
            "request": request,
            "filename": f"{symbol}.json",
            "path": str(snapshot_dir / "raw" / f"{symbol}.json"),
            "sha256": raw_hashes[symbol],
            "size_bytes": raw_sizes[symbol],
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
        }
        for symbol in CORPORATE_ACTION_SYMBOLS
    ]


def _query_record(requested_start: date, source_as_of: date) -> dict[str, Any]:
    return {
        "startDate": requested_start.isoformat(),
        "endDate": source_as_of.isoformat(),
        "resampleFreq": "5min",
        "columns": list(TIINGO_IEX_INTRADAY_COLUMNS),
        "afterHours": False,
        "forceFill": False,
    }


def _coverage_by_symbol(
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
) -> dict[str, dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        bars = bars_by_symbol[symbol]
        sessions = _session_dates(bars)
        coverage[symbol] = {
            "bar_count": len(bars),
            "session_count": len(sessions),
            "first_start_ts": _format_utc(bars[0].start_ts),
            "last_start_ts": _format_utc(bars[-1].start_ts),
            "first_session": min(sessions).isoformat(),
            "last_session": max(sessions).isoformat(),
            "session_dates_sha256": _date_set_hash(sessions),
        }
    return coverage


def _validate_common_session_coverage(
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
) -> frozenset[date]:
    common: set[date] | None = None
    for symbol in CORPORATE_ACTION_SYMBOLS:
        bars = bars_by_symbol.get(symbol)
        if not bars:
            raise ValueError(f"Tiingo IEX response is empty for {symbol}")
        sessions = set(_session_dates(bars))
        common = sessions if common is None else common & sessions
    result = frozenset(common or ())
    if len(result) < _MIN_COMMON_SESSIONS:
        raise ValueError("Tiingo IEX common session coverage is insufficient")
    return result


def _session_dates(bars: tuple[Bar, ...]) -> frozenset[date]:
    return frozenset(_new_york_session_date(bar.start_ts) for bar in bars)


def _new_york_session_date(timestamp: datetime) -> date:
    """Map UTC source timestamps to US Eastern dates without a tzdata dependency."""

    return _new_york_local_datetime(timestamp).date()


def _validate_intraday_timestamp(timestamp: datetime, symbol: str) -> date:
    """Require selected 5-minute bars without turning missing bars into a gate."""

    local = _new_york_local_datetime(timestamp)
    minute_of_day = local.hour * 60 + local.minute
    if local.weekday() >= 5 or local.second or local.microsecond or local.minute % 5:
        raise ValueError(f"Tiingo IEX timestamp is not aligned to 5-minute bars for {symbol}")
    if minute_of_day < 9 * 60 + 30 or minute_of_day > 15 * 60 + 55:
        raise ValueError(f"Tiingo IEX timestamp is outside regular-session bounds for {symbol}")
    return local.date()


def _new_york_local_datetime(timestamp: datetime) -> datetime:
    """Apply the post-2007 U.S. Eastern offset used by the documented source range."""

    value = require_utc(timestamp, "timestamp")
    if value.year < 2007:
        raise ValueError("Tiingo IEX timestamps before 2007 are unsupported")
    dst_start_day = _nth_weekday_of_month(value.year, 3, weekday=6, occurrence=2)
    dst_end_day = _nth_weekday_of_month(value.year, 11, weekday=6, occurrence=1)
    dst_start_utc = datetime(value.year, 3, dst_start_day.day, 7, tzinfo=UTC)
    dst_end_utc = datetime(value.year, 11, dst_end_day.day, 6, tzinfo=UTC)
    offset = timedelta(hours=-4 if dst_start_utc <= value < dst_end_utc else -5)
    return value + offset


def _nth_weekday_of_month(year: int, month: int, *, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _validate_manifest_header(
    manifest: Mapping[str, Any],
    *,
    snapshot: Path,
    dataset_id: str,
    dataset_hash: str,
) -> tuple[date, date, datetime]:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "fixed_etf_tiingo_iex_intraday"
        or manifest.get("immutable_snapshot") is not True
        or manifest.get("symbols") != list(CORPORATE_ACTION_SYMBOLS)
        or manifest.get("symbol_order") != list(CORPORATE_ACTION_SYMBOLS)
        or manifest.get("source_contract") != _SOURCE_CONTRACT
        or manifest.get("data_semantics") != _DATA_SEMANTICS
        or manifest.get("scope") != _SCOPE
    ):
        raise ValueError("Tiingo IEX manifest contract is invalid")
    if _required_text(manifest.get("dataset_id"), "Tiingo IEX dataset_id") != dataset_id:
        raise ValueError("Tiingo IEX manifest dataset_id mismatch")
    if _required_sha256(manifest.get("dataset_hash"), "Tiingo IEX dataset_hash") != dataset_hash:
        raise ValueError("Tiingo IEX manifest dataset hash mismatch")
    metadata = manifest.get("snapshot_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Tiingo IEX snapshot metadata is missing")
    requested_start = _date_text(metadata.get("requested_start"), "requested_start")
    source_as_of = _date_text(metadata.get("source_as_of"), "source_as_of")
    retrieved_at = _utc_text(metadata.get("retrieved_at_utc"), "retrieved_at_utc")
    _validate_requested_window(requested_start, source_as_of)
    if metadata != {
        "requested_start": requested_start.isoformat(),
        "source_as_of": source_as_of.isoformat(),
        "retrieved_at_utc": _format_utc(retrieved_at),
        "revision": TIINGO_IEX_INTRADAY_REVISION,
    }:
        raise ValueError("Tiingo IEX snapshot metadata is invalid")
    normalized = manifest.get("normalized_data")
    if not isinstance(normalized, dict) or normalized != {
        "path": normalized.get("path"),
        "size_bytes": normalized.get("size_bytes"),
        "sha256": normalized.get("sha256"),
        "schema": list(_CANONICAL_COLUMNS),
        "format": "csv.gz",
        "ordering": "symbol_order_then_start_ts_ascending",
    }:
        raise ValueError("Tiingo IEX normalized-data contract is invalid")
    _assert_manifest_path_tail(
        normalized["path"],
        snapshot_name=snapshot.name,
        parts=("ohlcv_5m.csv.gz",),
        label="normalized",
    )
    if normalized["sha256"] != dataset_hash or normalized["size_bytes"] <= 0:
        raise ValueError("Tiingo IEX normalized-data identity is invalid")
    return requested_start, source_as_of, retrieved_at


def _validated_raw_entries(
    manifest: Mapping[str, Any],
    *,
    snapshot: Path,
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> dict[str, Mapping[str, Any]]:
    entries_value = manifest.get("raw_sources")
    if not isinstance(entries_value, list) or len(entries_value) != len(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo IEX raw evidence is invalid")
    entries: dict[str, Mapping[str, Any]] = {}
    expected_request = _query_record(requested_start, source_as_of)
    for expected_symbol, entry in zip(CORPORATE_ACTION_SYMBOLS, entries_value, strict=True):
        if not isinstance(entry, dict) or entry.get("symbol") != expected_symbol:
            raise ValueError("Tiingo IEX raw evidence is invalid")
        expected_fixed = {
            "symbol": expected_symbol,
            "source_id": f"tiingo-iex-intraday-5m-{expected_symbol.lower()}",
            "provider": "Tiingo IEX historical intraday API",
            "source_url": TIINGO_IEX_INTRADAY_ENDPOINT.format(symbol=expected_symbol),
            "source_kind": "licensed_api",
            "acquisition_mode": "operator_authorized_api",
            "use_scope": "private_internal_use",
            "request": expected_request,
            "filename": f"{expected_symbol}.json",
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
        }
        if any(entry.get(key) != value for key, value in expected_fixed.items()):
            raise ValueError("Tiingo IEX raw evidence is invalid")
        _assert_manifest_path_tail(
            entry.get("path"),
            snapshot_name=snapshot.name,
            parts=("raw", f"{expected_symbol}.json"),
            label="raw",
        )
        if _required_sha256(entry.get("sha256"), "Tiingo IEX raw sha256") != entry.get("sha256"):
            raise ValueError("Tiingo IEX raw evidence is invalid")
        if not isinstance(entry.get("size_bytes"), int) or entry["size_bytes"] <= 0:
            raise ValueError("Tiingo IEX raw evidence is invalid")
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
    bars_by_symbol: Mapping[str, tuple[Bar, ...]],
    common_sessions: frozenset[date],
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
) -> None:
    expected = _manifest(
        snapshot_dir=snapshot,
        dataset_hash=dataset_hash,
        normalized_size=normalized_size,
        raw_hashes=raw_hashes,
        raw_sizes=raw_sizes,
        bars_by_symbol=bars_by_symbol,
        common_sessions=common_sessions,
        requested_start=requested_start,
        source_as_of=source_as_of,
        retrieved_at_utc=retrieved_at_utc,
    )
    actual = dict(manifest)
    expected_without_paths = dict(expected)
    actual_normalized = dict(actual["normalized_data"])
    expected_normalized = dict(expected_without_paths["normalized_data"])
    actual_normalized.pop("path", None)
    expected_normalized.pop("path", None)
    actual["normalized_data"] = actual_normalized
    expected_without_paths["normalized_data"] = expected_normalized
    actual_raw = []
    expected_raw = []
    for entry in actual["raw_sources"]:
        entry_without_path = dict(entry)
        entry_without_path.pop("path", None)
        actual_raw.append(entry_without_path)
    for entry in expected_without_paths["raw_sources"]:
        entry_without_path = dict(entry)
        entry_without_path.pop("path", None)
        expected_raw.append(entry_without_path)
    actual["raw_sources"] = actual_raw
    expected_without_paths["raw_sources"] = expected_raw
    if actual != expected_without_paths:
        raise ValueError("Tiingo IEX manifest content does not match attested data")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> None:
    root = Path(market_data_root).resolve(strict=True)
    requested = Path(destination)
    if requested.is_symlink() or requested.exists():
        raise FileExistsError("Tiingo IEX destination already exists or is a symlink")
    resolved = requested.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("Tiingo IEX destination must be under market_data_root")
    if not requested.name.startswith("snapshot="):
        raise ValueError("Tiingo IEX destination must use a snapshot= directory")
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
        raise ValueError("Tiingo IEX snapshot cannot be a symlink")
    try:
        snapshot = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("Tiingo IEX snapshot directory is missing") from exc
    if not snapshot.is_dir() or not snapshot.is_relative_to(root):
        raise ValueError("Tiingo IEX snapshot must be under market_data_root")
    if not snapshot.name.startswith("snapshot="):
        raise ValueError("Tiingo IEX snapshot must use a snapshot= directory")
    _assert_external_path(snapshot, repo_root=repo_root)
    return snapshot


def _assert_external_path(path: Path, *, repo_root: Path | None) -> None:
    candidate = Path(path).resolve(strict=False)
    if repo_root is not None:
        root = Path(repo_root).resolve(strict=False)
        docker_market_data = Path("/app/market_data").resolve()
        if candidate == root or candidate.is_relative_to(root):
            if root != Path("/app").resolve() or not candidate.is_relative_to(docker_market_data):
                raise ValueError("Tiingo IEX data must be outside Git")
    if any((parent / ".git").exists() for parent in (candidate, *candidate.parents)):
        raise ValueError("Tiingo IEX data must be outside Git")


def _check_free_space(root: Path) -> None:
    usage = shutil.disk_usage(root)
    free_ratio = usage.free / usage.total
    if free_ratio < 0.15:
        raise ValueError("Tiingo IEX acquisition would breach the market-data free-space floor")
    if free_ratio < 0.20:
        warnings.warn(
            "Tiingo IEX acquisition is below the 20% market-data free-space warning level",
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


def _read_snapshot_file(snapshot: Path, path: Path, label: str) -> bytes:
    try:
        relative = path.relative_to(snapshot)
    except ValueError as exc:
        raise ValueError(f"Tiingo IEX {label} must be inside the snapshot") from exc
    current = snapshot
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Tiingo IEX {label} cannot use symlinks")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Tiingo IEX {label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"Tiingo IEX {label} must be a regular file inside the snapshot")
    return resolved.read_bytes()


def _validate_requested_window(requested_start: date, source_as_of: date) -> None:
    if type(requested_start) is not date or type(source_as_of) is not date:
        raise ValueError("Tiingo IEX requested dates must be dates")
    if requested_start > source_as_of:
        raise ValueError("Tiingo IEX requested window is invalid")


def _requested_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if symbol not in CORPORATE_ACTION_SYMBOLS:
        raise ValueError("Tiingo IEX symbol must be one of SPY, QQQ, IWM")
    return symbol


def _tiingo_timestamp(value: object, symbol: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Tiingo IEX date is missing or malformed for {symbol}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Tiingo IEX date is missing or malformed for {symbol}") from exc
    try:
        return require_utc(parsed, "Tiingo IEX date")
    except ValueError as exc:
        raise ValueError(f"Tiingo IEX date is missing or malformed for {symbol}") from exc


def _tiingo_decimal(value: object, field: str, symbol: str) -> Decimal:
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, str)):
        raise ValueError(f"Tiingo IEX {field} is missing or malformed for {symbol}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Tiingo IEX {field} is missing or malformed for {symbol}")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Tiingo IEX {field} is missing or malformed for {symbol}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Tiingo IEX {field} is missing or malformed for {symbol}")
    return parsed


def _canonical_csv_bytes(bars: tuple[Bar, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_CANONICAL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for bar in bars:
        writer.writerow(
            {
                "symbol": bar.symbol,
                "start_ts": _format_utc(bar.start_ts),
                "open": format(bar.open, "f"),
                "high": format(bar.high, "f"),
                "low": format(bar.low, "f"),
                "close": format(bar.close, "f"),
                "volume": format(bar.volume, "f"),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _dataset_id(snapshot_dir: Path) -> str:
    return f"{TIINGO_IEX_INTRADAY_DATASET_ID_PREFIX}.{Path(snapshot_dir).name}"


def _date_set_hash(values: frozenset[date]) -> str:
    return _sha256("".join(f"{value.isoformat()}\n" for value in sorted(values)).encode("ascii"))


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


def _assert_manifest_path_tail(
    value: object,
    *,
    snapshot_name: str,
    parts: tuple[str, ...],
    label: str,
) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Tiingo IEX {label} path is invalid")
    path_parts = tuple(part for part in value.replace("\\", "/").split("/") if part)
    if path_parts[-len(parts) - 1 :] != (snapshot_name, *parts):
        raise ValueError(f"Tiingo IEX {label} path is inconsistent with the snapshot")


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_datetime(value: datetime, label: str) -> datetime:
    try:
        return require_utc(value, label)
    except ValueError as exc:
        raise ValueError(f"{label} must be an explicit UTC timestamp") from exc


def _date_text(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo IEX {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Tiingo IEX {label} is invalid") from exc


def _utc_text(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo IEX {label} is invalid")
    try:
        return _utc_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")), label)
    except ValueError as exc:
        raise ValueError(f"Tiingo IEX {label} is invalid") from exc

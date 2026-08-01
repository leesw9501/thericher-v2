"""Bounded private Tiingo raw-D1 snapshots for the fixed three-ETF research scope."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import uuid
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from thericher_v2.contracts import Bar, Timeframe

from .tiingo_eod import TIINGO_EOD_ENDPOINT, read_tiingo_api_token

DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
DEFAULT_TIINGO_ETF_D1_ROOT = (
    DEFAULT_MARKET_DATA_ROOT / "us_equities" / "tiingo_etf_daily" / "canonical"
)
TIINGO_ETF_D1_SYMBOLS = ("SPY", "QQQ", "IWM")
TIINGO_ETF_D1_VERSION = "tiingo-etf-d1-r1"
DEFAULT_TIINGO_ETF_D1_RECEIPT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_CANONICAL_FILE = "ohlcv_1d.csv.gz"
_MANIFEST_FILE = "manifest.json"
_RAW_DIRECTORY = "raw"
_MODULE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_COLUMNS = (
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


class TiingoEtfDailyError(RuntimeError):
    """A masked failure while acquiring or verifying the fixed ETF snapshot."""


class _RejectRedirect(HTTPRedirectHandler):
    """Do not forward the authorization header to a redirect destination."""

    def redirect_request(
        self,
        _request: Request,
        _file: Any,
        _code: int,
        _message: str,
        _headers: Any,
        _new_url: str,
    ) -> Request:
        raise TiingoEtfDailyError("Tiingo ETF daily redirects are not allowed")


@dataclass(frozen=True, slots=True)
class TiingoEtfDailyRow:
    """One raw-field daily record retained only inside the external snapshot."""

    symbol: str
    session_date: date
    open: Decimal = field(repr=False)
    high: Decimal = field(repr=False)
    low: Decimal = field(repr=False)
    close: Decimal = field(repr=False)
    volume: Decimal = field(repr=False)
    div_cash: Decimal = field(repr=False)
    split_factor: Decimal = field(repr=False)


@dataclass(frozen=True, slots=True)
class TiingoEtfDailySnapshot:
    """Source-safe identity and aggregate coverage facts for one snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    raw_hashes: Mapping[str, str]
    session_counts: Mapping[str, int]
    date_ranges: Mapping[str, tuple[date, date]]
    event_session_counts: Mapping[str, int]
    row_count: int
    free_percent: float

    def __post_init__(self) -> None:
        _require_sha256(self.dataset_hash, "dataset_hash")
        _require_sha256(self.manifest_hash, "manifest_hash")
        if set(self.raw_hashes) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("raw_hashes must cover the fixed ETF symbols")
        if set(self.session_counts) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("session_counts must cover the fixed ETF symbols")
        if set(self.date_ranges) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("date_ranges must cover the fixed ETF symbols")
        if set(self.event_session_counts) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("event_session_counts must cover the fixed ETF symbols")
        object.__setattr__(self, "raw_hashes", MappingProxyType(dict(self.raw_hashes)))
        object.__setattr__(self, "session_counts", MappingProxyType(dict(self.session_counts)))
        object.__setattr__(self, "date_ranges", MappingProxyType(dict(self.date_ranges)))
        object.__setattr__(
            self,
            "event_session_counts",
            MappingProxyType(dict(self.event_session_counts)),
        )


@dataclass(frozen=True, slots=True)
class LoadedTiingoEtfDailySnapshot:
    """Verified raw rows kept in-memory for source-local research only."""

    snapshot: TiingoEtfDailySnapshot
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]] = field(repr=False)

    def __post_init__(self) -> None:
        normalized = {symbol: tuple(rows) for symbol, rows in self.rows_by_symbol.items()}
        if set(normalized) != set(TIINGO_ETF_D1_SYMBOLS):
            raise ValueError("rows_by_symbol must cover the fixed ETF symbols")
        if any(
            not rows or any(row.symbol != symbol for row in rows)
            for symbol, rows in normalized.items()
        ):
            raise ValueError("rows_by_symbol is inconsistent with the fixed ETF symbols")
        object.__setattr__(self, "rows_by_symbol", MappingProxyType(normalized))

    def bars_for(self, symbol: str, *, market: str = "US") -> tuple[Bar, ...]:
        requested_symbol = _symbol(symbol)
        resolved_market = market.strip().upper()
        if requested_symbol not in self.rows_by_symbol or not resolved_market:
            raise ValueError("requested ETF bar stream is unavailable")
        return tuple(
            Bar(
                symbol=row.symbol,
                market=resolved_market,
                timeframe=Timeframe.D1,
                start_ts=datetime.combine(row.session_date, time(), tzinfo=UTC),
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                complete=True,
            )
            for row in self.rows_by_symbol[requested_symbol]
        )


def default_tiingo_etf_d1_snapshot_dir(retrieved_at_utc: datetime) -> Path:
    """Return a unique external destination for one immutable source snapshot."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    label = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_TIINGO_ETF_D1_ROOT / f"snapshot={label}-{TIINGO_ETF_D1_VERSION}"


def acquire_tiingo_etf_d1_snapshot(
    *,
    env_path: Path,
    destination: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: float = 30.0,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoEtfDailySnapshot:
    """Acquire exactly SPY, QQQ, and IWM raw daily data outside the repository."""

    _validate_window(requested_start, requested_end)
    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    if timeout_seconds <= 0:
        raise ValueError("Tiingo ETF daily timeout must be positive")
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    token = read_tiingo_api_token(Path(env_path))
    request_opener = opener or build_opener(_RejectRedirect()).open

    staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    raw_hashes: dict[str, str] = {}
    rows_by_symbol: dict[str, tuple[TiingoEtfDailyRow, ...]] = {}
    try:
        staging.mkdir(parents=True)
        raw_dir = staging / _RAW_DIRECTORY
        raw_dir.mkdir()
        for symbol in TIINGO_ETF_D1_SYMBOLS:
            raw_response = _fetch_raw_response(
                symbol=symbol,
                token=token,
                requested_start=requested_start,
                requested_end=requested_end,
                opener=request_opener,
                timeout_seconds=timeout_seconds,
            )
            rows = normalize_tiingo_etf_d1_response(symbol=symbol, raw_response=raw_response)
            raw_path = raw_dir / f"{symbol}.json"
            raw_path.write_bytes(raw_response)
            raw_hashes[symbol] = _sha256(raw_response)
            rows_by_symbol[symbol] = rows

        canonical_bytes = _gzip_bytes(_canonical_csv_bytes(rows_by_symbol))
        (staging / _CANONICAL_FILE).write_bytes(canonical_bytes)
        manifest = _manifest(
            target=target,
            requested_start=requested_start,
            requested_end=requested_end,
            retrieved_at=retrieved_at,
            canonical_hash=_sha256(canonical_bytes),
            canonical_size=len(canonical_bytes),
            raw_hashes=raw_hashes,
            rows_by_symbol=rows_by_symbol,
            raw_dir=raw_dir,
            free_percent=free_percent,
        )
        (staging / _MANIFEST_FILE).write_bytes(_json_bytes(manifest))
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    manifest_hash = _sha256((target / _MANIFEST_FILE).read_bytes())
    return _snapshot_from_manifest(
        snapshot_dir=target,
        manifest=manifest,
        manifest_hash=manifest_hash,
        free_percent=free_percent,
    )


def normalize_tiingo_etf_d1_response(
    *,
    symbol: str,
    raw_response: bytes,
) -> tuple[TiingoEtfDailyRow, ...]:
    """Parse one raw Tiingo response without accepting adjusted fields as input."""

    requested_symbol = _symbol(symbol)
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError(f"Tiingo ETF daily response is unavailable for {requested_symbol}")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Tiingo ETF daily response is invalid for {requested_symbol}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Tiingo ETF daily response is empty for {requested_symbol}")

    rows: list[TiingoEtfDailyRow] = []
    seen_dates: set[date] = set()
    previous_date: date | None = None
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Tiingo ETF daily row is invalid for {requested_symbol}")
        session_date = _date_value(item.get("date"), requested_symbol)
        if session_date in seen_dates or (
            previous_date is not None and session_date <= previous_date
        ):
            raise ValueError(f"Tiingo ETF daily dates are invalid for {requested_symbol}")
        prices = tuple(
            _decimal_value(item.get(field), field, requested_symbol)
            for field in ("open", "high", "low", "close")
        )
        volume = _decimal_value(item.get("volume"), "volume", requested_symbol)
        div_cash = _decimal_value(item.get("divCash"), "divCash", requested_symbol)
        split_factor = _decimal_value(item.get("splitFactor"), "splitFactor", requested_symbol)
        _validate_raw_values(*prices, volume, div_cash, split_factor)
        rows.append(
            TiingoEtfDailyRow(
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
        seen_dates.add(session_date)
        previous_date = session_date
    return tuple(rows)


def load_verified_tiingo_etf_d1_snapshot(
    snapshot_dir: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> LoadedTiingoEtfDailySnapshot:
    """Reattest raw and canonical external files before exposing in-memory rows."""

    _require_sha256(expected_dataset_hash, "expected_dataset_hash")
    _require_sha256(expected_manifest_hash, "expected_manifest_hash")
    snapshot, _root = _validate_existing_snapshot(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    manifest_bytes = _read_snapshot_file(snapshot, snapshot / _MANIFEST_FILE, "manifest")
    actual_manifest_hash = _sha256(manifest_bytes)
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError("Tiingo ETF daily manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo ETF daily manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo ETF daily manifest is invalid")
    snapshot_result = _snapshot_from_manifest(
        snapshot_dir=snapshot,
        manifest=manifest,
        manifest_hash=actual_manifest_hash,
        free_percent=None,
    )
    if snapshot_result.dataset_id != dataset_id:
        raise ValueError("Tiingo ETF daily dataset id mismatch")
    if snapshot_result.dataset_hash != expected_dataset_hash:
        raise ValueError("Tiingo ETF daily dataset hash mismatch")

    raw_rows = {}
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        raw_path = snapshot / _RAW_DIRECTORY / f"{symbol}.json"
        raw_rows[symbol] = normalize_tiingo_etf_d1_response(
            symbol=symbol,
            raw_response=_read_snapshot_file(snapshot, raw_path, symbol),
        )
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        raw_path = snapshot / _RAW_DIRECTORY / f"{symbol}.json"
        raw_bytes = _read_snapshot_file(snapshot, raw_path, symbol)
        if _sha256(raw_bytes) != snapshot_result.raw_hashes[symbol]:
            raise ValueError(f"Tiingo ETF daily raw hash mismatch for {symbol}")

    canonical_path = snapshot / _CANONICAL_FILE
    canonical_bytes = _read_snapshot_file(snapshot, canonical_path, "canonical dataset")
    if _sha256(canonical_bytes) != expected_dataset_hash:
        raise ValueError("Tiingo ETF daily canonical hash mismatch")
    if _parse_canonical_rows(canonical_bytes) != raw_rows:
        raise ValueError("Tiingo ETF daily canonical data does not match raw responses")
    return LoadedTiingoEtfDailySnapshot(snapshot=snapshot_result, rows_by_symbol=raw_rows)


def write_tiingo_etf_d1_receipt(
    snapshot: TiingoEtfDailySnapshot,
    *,
    artifact_root: Path = DEFAULT_TIINGO_ETF_D1_RECEIPT_ROOT,
    repo_root: Path | None = None,
) -> Path:
    """Write one aggregate-only collection receipt outside the workspace."""

    root = Path(artifact_root).resolve(strict=False)
    _validate_external_artifact_root(root, repo_root=repo_root)
    receipt_dir = (root / "data-receipts" / "tiingo-etf-d1").resolve(strict=False)
    if not receipt_dir.is_relative_to(root):
        raise ValueError("Tiingo ETF daily receipt path is invalid")
    receipt_path = receipt_dir / f"{snapshot.manifest_hash[7:]}.json"
    payload = {
        "schema_version": 1,
        "kind": "tiingo_etf_raw_d1_collection_receipt",
        "status": "collected",
        "dataset_id": snapshot.dataset_id,
        "dataset_hash": snapshot.dataset_hash,
        "manifest_hash": snapshot.manifest_hash,
        "raw_hashes": dict(snapshot.raw_hashes),
        "symbols": list(TIINGO_ETF_D1_SYMBOLS),
        "session_counts": dict(snapshot.session_counts),
        "date_ranges": {
            symbol: {
                "first_session": date_range[0].isoformat(),
                "last_session": date_range[1].isoformat(),
            }
            for symbol, date_range in snapshot.date_ranges.items()
        },
        "event_session_counts": dict(snapshot.event_session_counts),
        "row_count": snapshot.row_count,
        "source_contract": {
            "provider": "Tiingo standard EOD API",
            "raw_fields": [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "divCash",
                "splitFactor",
            ],
            "adjusted_fields_used": False,
        },
        "scope": {
            "retrospective_research_only": True,
            "point_in_time_eligible": False,
            "paper_input_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "storage": {"free_percent_before_write": snapshot.free_percent},
        "raw_market_data_written": False,
    }
    receipt_dir.mkdir(parents=True, exist_ok=True)
    try:
        with receipt_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        raise TiingoEtfDailyError("Tiingo ETF daily receipt write failed") from exc
    return receipt_path


def _fetch_raw_response(
    *,
    symbol: str,
    token: str,
    requested_start: date,
    requested_end: date,
    opener: Callable[..., Any],
    timeout_seconds: float,
) -> bytes:
    endpoint = TIINGO_EOD_ENDPOINT.format(symbol=symbol)
    query = urlencode(
        {"startDate": requested_start.isoformat(), "endDate": requested_end.isoformat()}
    )
    request = Request(
        f"{endpoint}?{query}",
        headers={"Accept": "application/json", "Authorization": f"Token {token}"},
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            if getattr(response, "status", 200) != 200:
                raise TiingoEtfDailyError(f"Tiingo ETF daily request failed for {symbol}")
            payload = response.read()
    except HTTPError as exc:
        raise TiingoEtfDailyError(
            f"Tiingo ETF daily request failed for {symbol}: HTTP {exc.code}"
        ) from exc
    except (OSError, URLError) as exc:
        raise TiingoEtfDailyError(f"Tiingo ETF daily request failed for {symbol}") from exc
    if not isinstance(payload, bytes) or not payload:
        raise TiingoEtfDailyError(f"Tiingo ETF daily response is unavailable for {symbol}")
    return payload


def _manifest(
    *,
    target: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at: datetime,
    canonical_hash: str,
    canonical_size: int,
    raw_hashes: Mapping[str, str],
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
    raw_dir: Path,
    free_percent: float,
) -> dict[str, object]:
    per_symbol = {}
    raw_sources = []
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        rows = rows_by_symbol[symbol]
        raw_path = raw_dir / f"{symbol}.json"
        event_count = sum(row.div_cash != 0 or row.split_factor != 1 for row in rows)
        per_symbol[symbol] = {
            "session_count": len(rows),
            "first_session": rows[0].session_date.isoformat(),
            "last_session": rows[-1].session_date.isoformat(),
            "event_session_count": event_count,
        }
        raw_sources.append(
            {
                "symbol": symbol,
                "filename": raw_path.name,
                "sha256": raw_hashes[symbol],
                "size_bytes": raw_path.stat().st_size,
            }
        )
    dataset_id = f"us_equities.tiingo_etf_daily.{target.name}"
    return {
        "schema_version": 1,
        "kind": "tiingo_etf_raw_d1_snapshot",
        "version": TIINGO_ETF_D1_VERSION,
        "immutable_snapshot": True,
        "dataset_id": dataset_id,
        "dataset_hash": canonical_hash,
        "symbols": list(TIINGO_ETF_D1_SYMBOLS),
        "requested_window": {
            "start": requested_start.isoformat(),
            "end": requested_end.isoformat(),
        },
        "retrieved_at_utc": _format_utc(retrieved_at),
        "source_contract": {
            "provider": "Tiingo standard EOD API",
            "endpoint_template": TIINGO_EOD_ENDPOINT,
            "raw_fields": [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "divCash",
                "splitFactor",
            ],
            "adjusted_fields_used": False,
        },
        "scope": {
            "retrospective_research_only": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "paper_input_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "per_symbol": per_symbol,
        "files": {
            "canonical": {
                "path": _CANONICAL_FILE,
                "format": "csv.gz",
                "columns": list(_CANONICAL_COLUMNS),
                "sha256": canonical_hash,
                "size_bytes": canonical_size,
            },
            "raw_sources": raw_sources,
        },
        "storage": {"free_percent_before_write": free_percent},
    }


def _snapshot_from_manifest(
    *,
    snapshot_dir: Path,
    manifest: Mapping[str, object],
    manifest_hash: str,
    free_percent: float | None,
) -> TiingoEtfDailySnapshot:
    if manifest.get("kind") != "tiingo_etf_raw_d1_snapshot":
        raise ValueError("Tiingo ETF daily manifest kind is invalid")
    if manifest.get("version") != TIINGO_ETF_D1_VERSION or not manifest.get("immutable_snapshot"):
        raise ValueError("Tiingo ETF daily manifest version is invalid")
    if tuple(manifest.get("symbols", ())) != TIINGO_ETF_D1_SYMBOLS:
        raise ValueError("Tiingo ETF daily manifest symbols are invalid")
    dataset_id = _required_text(manifest.get("dataset_id"), "dataset_id")
    expected_id = f"us_equities.tiingo_etf_daily.{snapshot_dir.name}"
    if dataset_id != expected_id:
        raise ValueError("Tiingo ETF daily dataset id is invalid")
    dataset_hash = _required_sha256(manifest.get("dataset_hash"), "dataset_hash")
    files = _required_mapping(manifest.get("files"), "files")
    canonical = _required_mapping(files.get("canonical"), "canonical")
    if tuple(canonical.get("columns", ())) != _CANONICAL_COLUMNS:
        raise ValueError("Tiingo ETF daily canonical schema is invalid")
    if canonical.get("path") != _CANONICAL_FILE or canonical.get("sha256") != dataset_hash:
        raise ValueError("Tiingo ETF daily canonical identity is invalid")
    raw_sources = files.get("raw_sources")
    if not isinstance(raw_sources, list) or len(raw_sources) != len(TIINGO_ETF_D1_SYMBOLS):
        raise ValueError("Tiingo ETF daily raw source list is invalid")
    raw_hashes: dict[str, str] = {}
    for symbol, source in zip(TIINGO_ETF_D1_SYMBOLS, raw_sources, strict=True):
        source_mapping = _required_mapping(source, "raw source")
        if (
            source_mapping.get("symbol") != symbol
            or source_mapping.get("filename") != f"{symbol}.json"
        ):
            raise ValueError("Tiingo ETF daily raw source identity is invalid")
        raw_hashes[symbol] = _required_sha256(source_mapping.get("sha256"), "raw source hash")
    per_symbol = _required_mapping(manifest.get("per_symbol"), "per_symbol")
    counts: dict[str, int] = {}
    date_ranges: dict[str, tuple[date, date]] = {}
    event_counts: dict[str, int] = {}
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        facts = _required_mapping(per_symbol.get(symbol), f"{symbol} facts")
        count = facts.get("session_count")
        event_count = facts.get("event_session_count")
        if (
            not isinstance(count, int)
            or count < 1
            or not isinstance(event_count, int)
            or event_count < 0
        ):
            raise ValueError("Tiingo ETF daily aggregate counts are invalid")
        first = _date_value(facts.get("first_session"), symbol)
        last = _date_value(facts.get("last_session"), symbol)
        if last < first:
            raise ValueError("Tiingo ETF daily date range is invalid")
        counts[symbol] = count
        date_ranges[symbol] = (first, last)
        event_counts[symbol] = event_count
    _validate_manifest_scope(manifest)
    if free_percent is None:
        storage = _required_mapping(manifest.get("storage"), "storage")
        result_free_percent = _nonnegative_float(storage.get("free_percent_before_write"))
    else:
        result_free_percent = free_percent
    return TiingoEtfDailySnapshot(
        snapshot_dir=snapshot_dir,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        manifest_hash=manifest_hash,
        raw_hashes=raw_hashes,
        session_counts=counts,
        date_ranges=date_ranges,
        event_session_counts=event_counts,
        row_count=sum(counts.values()),
        free_percent=result_free_percent,
    )


def _validate_manifest_scope(manifest: Mapping[str, object]) -> None:
    source = _required_mapping(manifest.get("source_contract"), "source_contract")
    if source.get("provider") != "Tiingo standard EOD API" or source.get("adjusted_fields_used"):
        raise ValueError("Tiingo ETF daily source contract is invalid")
    if source.get("endpoint_template") != TIINGO_EOD_ENDPOINT:
        raise ValueError("Tiingo ETF daily endpoint contract is invalid")
    scope = _required_mapping(manifest.get("scope"), "scope")
    expected_scope = {
        "retrospective_research_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "paper_input_eligible": False,
        "sealed_holdout_eligible": False,
    }
    if dict(scope) != expected_scope:
        raise ValueError("Tiingo ETF daily scope is invalid")


def _parse_canonical_rows(data: bytes) -> dict[str, tuple[TiingoEtfDailyRow, ...]]:
    try:
        raw_csv = gzip.decompress(data).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("Tiingo ETF daily canonical data is invalid") from exc
    reader = csv.DictReader(io.StringIO(raw_csv))
    if tuple(reader.fieldnames or ()) != _CANONICAL_COLUMNS:
        raise ValueError("Tiingo ETF daily canonical schema is invalid")
    rows_by_symbol: dict[str, list[TiingoEtfDailyRow]] = {
        symbol: [] for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    previous: tuple[int, date] | None = None
    for item in reader:
        symbol = _symbol(item.get("symbol"))
        if symbol not in rows_by_symbol:
            raise ValueError("Tiingo ETF daily canonical symbol is invalid")
        session_date = _date_value(item.get("date"), symbol)
        order = (TIINGO_ETF_D1_SYMBOLS.index(symbol), session_date)
        if previous is not None and order <= previous:
            raise ValueError("Tiingo ETF daily canonical ordering is invalid")
        values = tuple(
            _decimal_value(item.get(field), field, symbol)
            for field in ("open", "high", "low", "close", "volume", "div_cash", "split_factor")
        )
        _validate_raw_values(*values[:4], *values[4:])
        rows_by_symbol[symbol].append(
            TiingoEtfDailyRow(
                symbol=symbol,
                session_date=session_date,
                open=values[0],
                high=values[1],
                low=values[2],
                close=values[3],
                volume=values[4],
                div_cash=values[5],
                split_factor=values[6],
            )
        )
        previous = order
    result = {symbol: tuple(rows) for symbol, rows in rows_by_symbol.items()}
    if any(not rows for rows in result.values()):
        raise ValueError("Tiingo ETF daily canonical data is incomplete")
    return result


def _canonical_csv_bytes(
    rows_by_symbol: Mapping[str, tuple[TiingoEtfDailyRow, ...]],
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_CANONICAL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for symbol in TIINGO_ETF_D1_SYMBOLS:
        for row in rows_by_symbol[symbol]:
            writer.writerow(
                {
                    "symbol": row.symbol,
                    "date": row.session_date.isoformat(),
                    "open": _decimal_text(row.open),
                    "high": _decimal_text(row.high),
                    "low": _decimal_text(row.low),
                    "close": _decimal_text(row.close),
                    "volume": _decimal_text(row.volume),
                    "div_cash": _decimal_text(row.div_cash),
                    "split_factor": _decimal_text(row.split_factor),
                }
            )
    return buffer.getvalue().encode("utf-8")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root).resolve(strict=True)
    target = Path(destination).resolve(strict=False)
    if root not in target.parents or target.name == root.name:
        raise ValueError("Tiingo ETF daily destination must remain under market_data")
    if not target.name.startswith("snapshot=") or not target.name.endswith(TIINGO_ETF_D1_VERSION):
        raise ValueError("Tiingo ETF daily destination name is invalid")
    if repo_root is not None:
        resolved_repo = Path(repo_root).resolve(strict=True)
        if (
            target == resolved_repo or resolved_repo in target.parents
        ) and not _is_container_external_mount(
            root,
            resolved_repo,
            mount_name="market_data",
        ):
            raise ValueError("Tiingo ETF daily data must stay outside the Git workspace")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Tiingo ETF daily destination already exists")
    return target, root


def _validate_existing_snapshot(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root).resolve(strict=True)
    snapshot = Path(snapshot_dir)
    if snapshot.is_symlink():
        raise ValueError("Tiingo ETF daily snapshot cannot be a symlink")
    resolved = snapshot.resolve(strict=True)
    if root not in resolved.parents or not resolved.name.startswith("snapshot="):
        raise ValueError("Tiingo ETF daily snapshot must remain under market_data")
    if repo_root is not None:
        resolved_repo = Path(repo_root).resolve(strict=True)
        if (
            resolved == resolved_repo or resolved_repo in resolved.parents
        ) and not _is_container_external_mount(
            root,
            resolved_repo,
            mount_name="market_data",
        ):
            raise ValueError("Tiingo ETF daily snapshot must stay outside the Git workspace")
    return resolved, root


def _validate_external_artifact_root(root: Path, *, repo_root: Path | None) -> None:
    for candidate in (repo_root, _MODULE_REPOSITORY_ROOT):
        if candidate is None:
            continue
        resolved_repository = Path(candidate).resolve(strict=True)
        if (
            root == resolved_repository or root.is_relative_to(resolved_repository)
        ) and not _is_container_external_mount(
            root,
            resolved_repository,
            mount_name="model_artifacts",
        ):
            raise ValueError("Tiingo ETF daily receipt must stay outside the Git workspace")


def _is_container_external_mount(path: Path, repo_root: Path, *, mount_name: str) -> bool:
    """Allow only named Docker bind mounts beneath the container worktree."""

    container_repo = Path("/app").resolve()
    if repo_root != container_repo:
        return False
    mount_root = container_repo / mount_name
    return path == mount_root or path.is_relative_to(mount_root)


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = getattr(usage, "total", 0)
    free = getattr(usage, "free", -1)
    if not isinstance(total, int) or total <= 0 or not isinstance(free, int) or free < 0:
        raise ValueError("Tiingo ETF daily disk usage is invalid")
    free_percent = free * 100 / total
    if free_percent < 15:
        raise TiingoEtfDailyError("Tiingo ETF daily storage floor reached")
    if free_percent < 20:
        warnings.warn("Tiingo ETF daily storage is below the warning threshold", stacklevel=2)
    return free_percent


def _read_snapshot_file(snapshot: Path, path: Path, label: str) -> bytes:
    if path.is_symlink() or snapshot not in path.parents:
        raise ValueError(f"Tiingo ETF daily {label} path is invalid")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Tiingo ETF daily {label} is unavailable") from exc


def _validate_window(requested_start: date, requested_end: date) -> None:
    if type(requested_start) is not date or type(requested_end) is not date:
        raise ValueError("Tiingo ETF daily requested dates must be dates")
    if requested_end < requested_start:
        raise ValueError("Tiingo ETF daily requested dates are invalid")


def _validate_raw_values(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: Decimal,
    div_cash: Decimal,
    split_factor: Decimal,
) -> None:
    prices = (open_price, high_price, low_price, close_price)
    if any(value <= 0 for value in prices) or volume < 0 or div_cash < 0 or split_factor <= 0:
        raise ValueError("Tiingo ETF daily raw values are invalid")
    if high_price < max(prices) or low_price > min(prices):
        raise ValueError("Tiingo ETF daily raw OHLC range is invalid")


def _date_value(value: object, symbol: str) -> date:
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"Tiingo ETF daily date is invalid for {symbol}")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"Tiingo ETF daily date is invalid for {symbol}") from exc


def _decimal_value(value: object, field_name: str, symbol: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Tiingo ETF daily {field_name} is invalid for {symbol}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Tiingo ETF daily {field_name} is invalid for {symbol}") from exc
    if not result.is_finite():
        raise ValueError(f"Tiingo ETF daily {field_name} is invalid for {symbol}")
    return result


def _symbol(value: object) -> str:
    result = str(value or "").upper()
    if result not in TIINGO_ETF_D1_SYMBOLS:
        raise ValueError("Tiingo ETF daily symbol is invalid")
    return result


def _required_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Tiingo ETF daily {label} is invalid")
    return value


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tiingo ETF daily {label} is invalid")
    return value


def _required_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo ETF daily {label} is invalid")
    _require_sha256(value, label)
    return value


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 71 or not value.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in value[7:]
    ):
        raise ValueError(f"Tiingo ETF daily {label} is invalid")


def _nonnegative_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("Tiingo ETF daily storage fact is invalid")
    return float(value)


def _utc_datetime(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"Tiingo ETF daily {label} must be UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

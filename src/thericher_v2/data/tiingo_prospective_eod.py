"""Bounded, prospective-only Tiingo Standard EOD snapshot support.

This module deliberately keeps its output outside the market-data provider and
bar-catalog paths.  A snapshot is lineage evidence only until a later,
separately reviewed Data contract says otherwise.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .tiingo_eod import (
    DEFAULT_MARKET_DATA_ROOT,
    MINIMUM_RETRIEVAL_LAG_DAYS,
    TIINGO_EOD_ENDPOINT,
    read_tiingo_api_token,
)

FIXED_PROSPECTIVE_EOD_SYMBOLS = ("SPY", "QQQ", "IWM")
PROSPECTIVE_EOD_REQUESTED_START = date(2026, 7, 10)
TIINGO_PROSPECTIVE_EOD_VERSION = "tiingo-standard-eod-prospective-r1"
TIINGO_PROSPECTIVE_EOD_KIND = "fixed_etf_tiingo_standard_eod_prospective"
TIINGO_TERMS_URL = "https://app.tiingo.com/tos/"
TIINGO_INTERNAL_USE_CLAUSE = "All data via the API is for internal consumption only."
DEFAULT_TIINGO_PROSPECTIVE_EOD_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_prospective_lineage"
    / "canonical"
    / "tiingo_standard_eod"
)
MAX_TIINGO_PROSPECTIVE_EOD_REQUESTS = len(FIXED_PROSPECTIVE_EOD_SYMBOLS)
NORMALIZED_CSV_NAME = "normalized_ohlcv_1d.csv"
MANIFEST_NAME = "manifest.json"
_RAW_DIRECTORY_NAME = "raw"
_NORMALIZED_COLUMNS = (
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
_PROSPECTIVE_SCOPE = {
    "prospective_lineage_only": True,
    "model_eligible": False,
    "training_eligible": False,
    "campaign_eligible": False,
    "paper_trading_eligible": False,
    "ranking_eligible": False,
    "order_eligible": False,
    "point_in_time_eligible": False,
}
_PROSPECTIVE_RIGHTS = {
    "terms_url": TIINGO_TERMS_URL,
    "use_scope": "private_internal_use",
    "internal_use_clause": TIINGO_INTERNAL_USE_CLAUSE,
    "redistribution_eligible": False,
}


class TiingoProspectiveEodError(RuntimeError):
    """A masked, fail-closed prospective Tiingo acquisition failure."""


class _RejectRedirect(HTTPRedirectHandler):
    """Keep the approved token on the original Tiingo endpoint only."""

    def redirect_request(
        self,
        _request: Request,
        _file: Any,
        _code: int,
        _message: str,
        _headers: Any,
        _new_url: str,
    ) -> Request:
        raise TiingoProspectiveEodError("Tiingo prospective EOD redirects are not allowed")


@dataclass(frozen=True, slots=True)
class TiingoProspectiveEodRawFile:
    """Hash-bound metadata for one retained raw provider response."""

    symbol: str
    path: Path
    sha256: str
    size_bytes: int
    row_count: int


@dataclass(frozen=True, slots=True)
class TiingoProspectiveEodSnapshot:
    """Immutable lineage metadata; this type intentionally exposes no bars."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    retrieved_at_utc: datetime
    requested_start: date
    source_as_of: date
    row_count: int
    raw_files: tuple[TiingoProspectiveEodRawFile, ...]

    @property
    def prospective_lineage_only(self) -> bool:
        return True

    @property
    def model_eligible(self) -> bool:
        return False

    @property
    def training_eligible(self) -> bool:
        return False

    @property
    def campaign_eligible(self) -> bool:
        return False

    @property
    def paper_trading_eligible(self) -> bool:
        return False

    @property
    def ranking_eligible(self) -> bool:
        return False

    @property
    def order_eligible(self) -> bool:
        return False

    @property
    def point_in_time_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class _NormalizedRow:
    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    div_cash: Decimal
    split_factor: Decimal


def default_tiingo_prospective_eod_dir(
    retrieval_date: date,
    *,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
) -> Path:
    """Return the one allowed dated destination for a prospective snapshot."""

    date_value = _plain_date(retrieval_date, "Tiingo prospective retrieval date")
    return (
        Path(market_data_root)
        / "us_equities"
        / "fixed_etf_prospective_lineage"
        / "canonical"
        / "tiingo_standard_eod"
        / f"snapshot={date_value.isoformat()}-{TIINGO_PROSPECTIVE_EOD_VERSION}"
    )


def latest_source_complete_date(retrieved_at_utc: datetime) -> date:
    """Return the conservative latest source boundary for a retrieval instant."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "Tiingo prospective retrieval time")
    return retrieved_at.date() - timedelta(days=MINIMUM_RETRIEVAL_LAG_DAYS)


def clamp_source_as_of(source_as_of: date, *, retrieved_at_utc: datetime) -> date:
    """Clamp a script-provided source boundary to the conservative complete date."""

    requested = _plain_date(source_as_of, "Tiingo prospective source_as_of")
    return min(requested, latest_source_complete_date(retrieved_at_utc))


def acquire_tiingo_prospective_eod_snapshot(
    *,
    env_path: Path,
    requested_start: date,
    source_as_of: date,
    retrieved_at_utc: datetime,
    destination: Path | None = None,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: float = 20.0,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoProspectiveEodSnapshot:
    """Fetch exactly three responses and atomically retain one fixed snapshot."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "Tiingo prospective retrieval time")
    start = _plain_date(requested_start, "Tiingo prospective requested start")
    as_of = _plain_date(source_as_of, "Tiingo prospective source_as_of")
    _validate_requested_window(start, as_of, retrieved_at)
    if timeout_seconds <= 0:
        raise ValueError("Tiingo prospective timeout must be positive")

    target, snapshot_root = _validate_destination(
        destination
        or default_tiingo_prospective_eod_dir(
            retrieved_at.date(), market_data_root=market_data_root
        ),
        retrieval_date=retrieved_at.date(),
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    if target.exists():
        existing = load_tiingo_prospective_eod_snapshot(
            target,
            market_data_root=market_data_root,
            repo_root=repo_root,
        )
        if existing.requested_start != start or existing.source_as_of != as_of:
            raise FileExistsError(
                "Tiingo prospective snapshot already exists for another window"
            )
        return existing
    _assert_no_staging_residue(target)
    _validate_storage(Path(market_data_root), disk_usage=disk_usage)

    # The existing helper reads only TIINGO_API_TOKEN and is reached only after
    # every no-side-effect preflight has passed.
    token = read_tiingo_api_token(Path(env_path))
    snapshot_root.mkdir(parents=True, exist_ok=True)
    staging = snapshot_root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir(parents=True)
        raw_dir = staging / _RAW_DIRECTORY_NAME
        raw_dir.mkdir()
        request_opener = opener or _open_without_redirect
        raw_files: list[TiingoProspectiveEodRawFile] = []
        all_rows: list[_NormalizedRow] = []

        for symbol in FIXED_PROSPECTIVE_EOD_SYMBOLS:
            raw_response = _fetch_once(
                symbol=symbol,
                token=token,
                requested_start=start,
                source_as_of=as_of,
                opener=request_opener,
                timeout_seconds=timeout_seconds,
            )
            rows = _normalize_response(
                symbol=symbol,
                raw_response=raw_response,
                requested_start=start,
                source_as_of=as_of,
            )
            raw_path = raw_dir / f"{symbol}.json"
            _write_bytes(raw_path, raw_response)
            raw_files.append(
                TiingoProspectiveEodRawFile(
                    symbol=symbol,
                    path=raw_path,
                    sha256=_sha256(raw_response),
                    size_bytes=len(raw_response),
                    row_count=len(rows),
                )
            )
            all_rows.extend(rows)

        normalized_csv = _canonical_csv_bytes(all_rows)
        _write_bytes(staging / NORMALIZED_CSV_NAME, normalized_csv)
        manifest = _build_manifest(
            retrieved_at_utc=retrieved_at,
            requested_start=start,
            source_as_of=as_of,
            raw_files=raw_files,
            normalized_csv=normalized_csv,
        )
        _write_bytes(staging / MANIFEST_NAME, _canonical_json_bytes(manifest))

        _load_snapshot_metadata(staging, validate_location=False)
        try:
            staging.rename(target)
        except FileExistsError as exc:
            raise FileExistsError("Tiingo prospective snapshot already exists") from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return load_tiingo_prospective_eod_snapshot(
        target,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def load_tiingo_prospective_eod_snapshot(
    snapshot_dir: Path,
    *,
    expected_dataset_hash: str | None = None,
    expected_manifest_hash: str | None = None,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoProspectiveEodSnapshot:
    """Strictly re-attest an existing snapshot without token or network access."""

    snapshot = _validate_snapshot_location(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    metadata = _load_snapshot_metadata(snapshot, validate_location=True)
    if expected_dataset_hash is not None and metadata.dataset_hash != _sha256_text(
        expected_dataset_hash, "expected dataset hash"
    ):
        raise ValueError("Tiingo prospective dataset hash mismatch")
    if expected_manifest_hash is not None and metadata.manifest_hash != _sha256_text(
        expected_manifest_hash, "expected manifest hash"
    ):
        raise ValueError("Tiingo prospective manifest hash mismatch")
    return metadata


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)


def _fetch_once(
    *,
    symbol: str,
    token: str,
    requested_start: date,
    source_as_of: date,
    opener: Callable[..., Any],
    timeout_seconds: float,
) -> bytes:
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
        with opener(request, timeout=timeout_seconds) as response:
            if getattr(response, "status", 200) != 200:
                raise TiingoProspectiveEodError(
                    f"Tiingo prospective EOD request failed for {symbol}: unexpected status"
                )
            payload = response.read()
    except HTTPError as exc:
        raise TiingoProspectiveEodError(
            f"Tiingo prospective EOD request failed for {symbol}: HTTP {exc.code}"
        ) from exc
    except (OSError, URLError) as exc:
        raise TiingoProspectiveEodError(
            f"Tiingo prospective EOD request failed for {symbol}"
        ) from exc
    if not isinstance(payload, bytes) or not payload:
        raise TiingoProspectiveEodError(
            f"Tiingo prospective EOD response is unavailable for {symbol}"
        )
    return payload


def _normalize_response(
    *,
    symbol: str,
    raw_response: bytes,
    requested_start: date,
    source_as_of: date,
) -> tuple[_NormalizedRow, ...]:
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Tiingo prospective response is invalid for {symbol}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Tiingo prospective response must be a nonempty array for {symbol}")

    rows: list[_NormalizedRow] = []
    previous_date: date | None = None
    for raw_row in payload:
        if not isinstance(raw_row, dict):
            raise ValueError(f"Tiingo prospective row must be an object for {symbol}")
        session_date = _session_date(raw_row.get("date"), symbol)
        if session_date < requested_start or session_date > source_as_of:
            raise ValueError(
                f"Tiingo prospective response is outside its requested window for {symbol}"
            )
        if previous_date is not None and session_date <= previous_date:
            raise ValueError(
                f"Tiingo prospective response dates are not strictly ascending for {symbol}"
            )
        open_value = _decimal(raw_row.get("open"), "open", symbol)
        high = _decimal(raw_row.get("high"), "high", symbol)
        low = _decimal(raw_row.get("low"), "low", symbol)
        close = _decimal(raw_row.get("close"), "close", symbol)
        volume = _decimal(raw_row.get("volume"), "volume", symbol)
        div_cash = _decimal(raw_row.get("divCash"), "divCash", symbol)
        split_factor = _decimal(raw_row.get("splitFactor"), "splitFactor", symbol)
        if min(open_value, high, low, close) <= 0 or low > min(open_value, close) or high < max(
            open_value, close
        ):
            raise ValueError(f"Tiingo prospective OHLC range is invalid for {symbol}")
        if volume < 0:
            raise ValueError(f"Tiingo prospective volume cannot be negative for {symbol}")
        if div_cash < 0:
            raise ValueError(f"Tiingo prospective divCash cannot be negative for {symbol}")
        if split_factor <= 0:
            raise ValueError(f"Tiingo prospective splitFactor must be positive for {symbol}")
        rows.append(
            _NormalizedRow(
                symbol=symbol,
                session_date=session_date,
                open=open_value,
                high=high,
                low=low,
                close=close,
                volume=volume,
                div_cash=div_cash,
                split_factor=split_factor,
            )
        )
        previous_date = session_date
    return tuple(rows)


def _build_manifest(
    *,
    retrieved_at_utc: datetime,
    requested_start: date,
    source_as_of: date,
    raw_files: list[TiingoProspectiveEodRawFile],
    normalized_csv: bytes,
) -> dict[str, object]:
    dataset_hash = _sha256(normalized_csv)
    return {
        "schema_version": 1,
        "kind": TIINGO_PROSPECTIVE_EOD_KIND,
        "dataset_id": _dataset_id(retrieved_at_utc.date()),
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "requested_start": requested_start.isoformat(),
        "source_as_of": source_as_of.isoformat(),
        "minimum_retrieval_lag_days": MINIMUM_RETRIEVAL_LAG_DAYS,
        "symbols": list(FIXED_PROSPECTIVE_EOD_SYMBOLS),
        "source": {
            "provider": "Tiingo Standard EOD API",
            "endpoint_template": TIINGO_EOD_ENDPOINT,
            "request_count": MAX_TIINGO_PROSPECTIVE_EOD_REQUESTS,
            "retry_count": 0,
            "redirects_allowed": False,
        },
        "rights": dict(_PROSPECTIVE_RIGHTS),
        "scope": dict(_PROSPECTIVE_SCOPE),
        "files": {
            "raw": [
                {
                    "symbol": item.symbol,
                    "path": f"{_RAW_DIRECTORY_NAME}/{item.symbol}.json",
                    "sha256": item.sha256,
                    "size_bytes": item.size_bytes,
                    "row_count": item.row_count,
                }
                for item in raw_files
            ],
            "normalized_csv": {
                "path": NORMALIZED_CSV_NAME,
                "sha256": dataset_hash,
                "size_bytes": len(normalized_csv),
                "row_count": sum(item.row_count for item in raw_files),
            },
        },
    }


def _load_snapshot_metadata(
    snapshot: Path,
    *,
    validate_location: bool,
) -> TiingoProspectiveEodSnapshot:
    if validate_location:
        snapshot = snapshot.resolve(strict=True)
    manifest_bytes = _read_snapshot_file(snapshot, PurePosixPath(MANIFEST_NAME), "manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo prospective manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo prospective manifest must be an object")

    retrieved_at, requested_start, source_as_of, raw_entries, normalized_entry = _validate_manifest(
        manifest
    )
    if validate_location and snapshot.name != _snapshot_name(retrieved_at.date()):
        raise ValueError("Tiingo prospective snapshot directory is invalid")
    _validate_snapshot_layout(snapshot)

    raw_files: list[TiingoProspectiveEodRawFile] = []
    rows: list[_NormalizedRow] = []
    for symbol, raw_entry in zip(FIXED_PROSPECTIVE_EOD_SYMBOLS, raw_entries, strict=True):
        relative = PurePosixPath(f"{_RAW_DIRECTORY_NAME}/{symbol}.json")
        raw_bytes = _read_snapshot_file(snapshot, relative, f"raw response for {symbol}")
        raw_hash = _sha256(raw_bytes)
        if raw_hash != _sha256_text(raw_entry["sha256"], f"raw hash for {symbol}"):
            raise ValueError(f"Tiingo prospective raw hash mismatch for {symbol}")
        if len(raw_bytes) != _positive_int(raw_entry["size_bytes"], f"raw size for {symbol}"):
            raise ValueError(f"Tiingo prospective raw size mismatch for {symbol}")
        normalized_rows = _normalize_response(
            symbol=symbol,
            raw_response=raw_bytes,
            requested_start=requested_start,
            source_as_of=source_as_of,
        )
        expected_row_count = _positive_int(
            raw_entry["row_count"], f"raw row count for {symbol}"
        )
        if len(normalized_rows) != expected_row_count:
            raise ValueError(f"Tiingo prospective raw row count mismatch for {symbol}")
        raw_files.append(
            TiingoProspectiveEodRawFile(
                symbol=symbol,
                path=snapshot / relative,
                sha256=raw_hash,
                size_bytes=len(raw_bytes),
                row_count=len(normalized_rows),
            )
        )
        rows.extend(normalized_rows)

    normalized_csv = _read_snapshot_file(
        snapshot, PurePosixPath(NORMALIZED_CSV_NAME), "normalized CSV"
    )
    if normalized_csv != _canonical_csv_bytes(rows):
        raise ValueError("Tiingo prospective normalized CSV does not match retained raw responses")
    actual_dataset_hash = _sha256(normalized_csv)
    if actual_dataset_hash != _sha256_text(
        normalized_entry["sha256"], "normalized CSV hash"
    ):
        raise ValueError("Tiingo prospective normalized CSV hash mismatch")
    if actual_dataset_hash != _sha256_text(manifest.get("dataset_hash"), "dataset hash"):
        raise ValueError("Tiingo prospective dataset hash mismatch")
    if len(normalized_csv) != _positive_int(normalized_entry["size_bytes"], "normalized CSV size"):
        raise ValueError("Tiingo prospective normalized CSV size mismatch")
    if len(rows) != _positive_int(normalized_entry["row_count"], "normalized CSV row count"):
        raise ValueError("Tiingo prospective normalized CSV row count mismatch")

    return TiingoProspectiveEodSnapshot(
        snapshot_dir=snapshot,
        dataset_id=_dataset_id(retrieved_at.date()),
        dataset_hash=_sha256(normalized_csv),
        manifest_hash=_sha256(manifest_bytes),
        retrieved_at_utc=retrieved_at,
        requested_start=requested_start,
        source_as_of=source_as_of,
        row_count=len(rows),
        raw_files=tuple(raw_files),
    )


def _validate_manifest(
    manifest: dict[str, object],
) -> tuple[datetime, date, date, list[dict[str, object]], dict[str, object]]:
    expected_keys = {
        "schema_version",
        "kind",
        "dataset_id",
        "dataset_hash",
        "immutable_snapshot",
        "retrieved_at_utc",
        "requested_start",
        "source_as_of",
        "minimum_retrieval_lag_days",
        "symbols",
        "source",
        "rights",
        "scope",
        "files",
    }
    if (
        set(manifest) != expected_keys
        or manifest.get("schema_version") != 1
        or manifest.get("kind") != TIINGO_PROSPECTIVE_EOD_KIND
        or manifest.get("immutable_snapshot") is not True
    ):
        raise ValueError("Tiingo prospective manifest schema is invalid")
    retrieved_at = _parse_utc(manifest.get("retrieved_at_utc"), "retrieved_at_utc")
    requested_start = _parse_date(manifest.get("requested_start"), "requested_start")
    source_as_of = _parse_date(manifest.get("source_as_of"), "source_as_of")
    _validate_requested_window(requested_start, source_as_of, retrieved_at)
    if manifest.get("dataset_id") != _dataset_id(retrieved_at.date()):
        raise ValueError("Tiingo prospective dataset id is invalid")
    _sha256_text(manifest.get("dataset_hash"), "dataset hash")
    if manifest.get("minimum_retrieval_lag_days") != MINIMUM_RETRIEVAL_LAG_DAYS:
        raise ValueError("Tiingo prospective retrieval lag is invalid")
    if manifest.get("symbols") != list(FIXED_PROSPECTIVE_EOD_SYMBOLS):
        raise ValueError("Tiingo prospective symbols are invalid")
    if manifest.get("scope") != _PROSPECTIVE_SCOPE:
        raise ValueError("Tiingo prospective scope is invalid")
    if manifest.get("rights") != _PROSPECTIVE_RIGHTS:
        raise ValueError("Tiingo prospective rights contract is invalid")
    source = manifest.get("source")
    if not isinstance(source, dict) or source != {
        "provider": "Tiingo Standard EOD API",
        "endpoint_template": TIINGO_EOD_ENDPOINT,
        "request_count": MAX_TIINGO_PROSPECTIVE_EOD_REQUESTS,
        "retry_count": 0,
        "redirects_allowed": False,
    }:
        raise ValueError("Tiingo prospective source contract is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"raw", "normalized_csv"}:
        raise ValueError("Tiingo prospective file manifest is invalid")
    raw_entries = files["raw"]
    if not isinstance(raw_entries, list) or len(raw_entries) != MAX_TIINGO_PROSPECTIVE_EOD_REQUESTS:
        raise ValueError("Tiingo prospective raw file manifest is invalid")
    normalized_entry = files["normalized_csv"]
    if not isinstance(normalized_entry, dict):
        raise ValueError("Tiingo prospective normalized file manifest is invalid")

    validated_raw: list[dict[str, object]] = []
    for symbol, entry in zip(FIXED_PROSPECTIVE_EOD_SYMBOLS, raw_entries, strict=True):
        if not isinstance(entry, dict) or set(entry) != {
            "symbol",
            "path",
            "sha256",
            "size_bytes",
            "row_count",
        }:
            raise ValueError("Tiingo prospective raw file manifest is invalid")
        if entry.get("symbol") != symbol or entry.get("path") != f"raw/{symbol}.json":
            raise ValueError("Tiingo prospective raw file path is invalid")
        _sha256_text(entry.get("sha256"), f"raw hash for {symbol}")
        _positive_int(entry.get("size_bytes"), f"raw size for {symbol}")
        _positive_int(entry.get("row_count"), f"raw row count for {symbol}")
        validated_raw.append(entry)
    if set(normalized_entry) != {"path", "sha256", "size_bytes", "row_count"}:
        raise ValueError("Tiingo prospective normalized file manifest is invalid")
    if normalized_entry.get("path") != NORMALIZED_CSV_NAME:
        raise ValueError("Tiingo prospective normalized file path is invalid")
    _sha256_text(normalized_entry.get("sha256"), "normalized CSV hash")
    _positive_int(normalized_entry.get("size_bytes"), "normalized CSV size")
    _positive_int(normalized_entry.get("row_count"), "normalized CSV row count")
    return retrieved_at, requested_start, source_as_of, validated_raw, normalized_entry


def _validate_requested_window(
    requested_start: date,
    source_as_of: date,
    retrieved_at: datetime,
) -> None:
    if requested_start < PROSPECTIVE_EOD_REQUESTED_START:
        raise ValueError("Tiingo prospective requested start predates the approved boundary")
    if source_as_of < requested_start:
        raise ValueError("Tiingo prospective source_as_of predates requested start")
    if source_as_of > latest_source_complete_date(retrieved_at):
        raise ValueError(
            "Tiingo prospective source_as_of is newer than the complete source boundary"
        )


def _validate_destination(
    destination: Path,
    *,
    retrieval_date: date,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    market_root = Path(market_data_root)
    try:
        resolved_market_root = market_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("Tiingo prospective market-data root is missing") from exc
    if not resolved_market_root.is_dir() or resolved_market_root.is_symlink():
        raise ValueError("Tiingo prospective market-data root is invalid")
    snapshot_root = (
        resolved_market_root
        / "us_equities"
        / "fixed_etf_prospective_lineage"
        / "canonical"
        / "tiingo_standard_eod"
    )
    target = Path(destination)
    if target.is_symlink() or (
        target.resolve(strict=False).parent != snapshot_root.resolve(strict=False)
    ):
        raise ValueError("Tiingo prospective destination is outside its fixed canonical root")
    if target.name != _snapshot_name(retrieval_date):
        raise ValueError("Tiingo prospective destination name is invalid")
    _assert_outside_repo(target, repo_root=repo_root)
    if target.exists() and not target.is_dir():
        raise FileExistsError("Tiingo prospective snapshot already exists")
    return target.resolve(strict=False), snapshot_root.resolve(strict=False)


def _validate_snapshot_location(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> Path:
    market_root = Path(market_data_root)
    try:
        resolved_market_root = market_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("Tiingo prospective market-data root is missing") from exc
    snapshot = Path(snapshot_dir)
    if snapshot.is_symlink():
        raise ValueError("Tiingo prospective snapshot cannot be a symlink")
    try:
        resolved = snapshot.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("Tiingo prospective snapshot is missing") from exc
    expected_parent = (
        resolved_market_root
        / "us_equities"
        / "fixed_etf_prospective_lineage"
        / "canonical"
        / "tiingo_standard_eod"
    ).resolve(strict=False)
    if not resolved.is_dir() or resolved.parent != expected_parent:
        raise ValueError("Tiingo prospective snapshot is outside its fixed canonical root")
    _assert_outside_repo(resolved, repo_root=repo_root)
    return resolved


def _assert_outside_repo(path: Path, *, repo_root: Path | None) -> None:
    if repo_root is None:
        return
    repo = Path(repo_root).resolve(strict=False)
    if path.resolve(strict=False).is_relative_to(repo):
        raise ValueError("Tiingo prospective data must remain outside Git")


def _assert_no_staging_residue(target: Path) -> None:
    parent = target.parent
    if not parent.exists():
        return
    if any(parent.glob(".stage-*")):
        raise FileExistsError("Tiingo prospective snapshot has staging residue")


def _validate_storage(
    market_data_root: Path,
    *,
    disk_usage: Callable[[str | Path], Any],
) -> None:
    usage = disk_usage(market_data_root)
    total = getattr(usage, "total", 0)
    free = getattr(usage, "free", -1)
    if not isinstance(total, int) or not isinstance(free, int) or total <= 0 or free < 0:
        raise ValueError("Tiingo prospective free-space check is unavailable")
    ratio = free / total
    if ratio < 0.15:
        raise ValueError("Tiingo prospective acquisition would breach the hard free-space floor")
    if ratio < 0.20:
        warnings.warn(
            "Tiingo prospective acquisition is below the 20% market-data free-space warning level",
            RuntimeWarning,
            stacklevel=2,
        )


def _validate_snapshot_layout(snapshot: Path) -> None:
    expected = {MANIFEST_NAME, NORMALIZED_CSV_NAME, _RAW_DIRECTORY_NAME}
    entries = {entry.name for entry in snapshot.iterdir()}
    if entries != expected:
        raise ValueError("Tiingo prospective snapshot layout is invalid")
    raw_directory = snapshot / _RAW_DIRECTORY_NAME
    if raw_directory.is_symlink() or not raw_directory.is_dir():
        raise ValueError("Tiingo prospective raw directory is invalid")
    if {entry.name for entry in raw_directory.iterdir()} != {
        f"{symbol}.json" for symbol in FIXED_PROSPECTIVE_EOD_SYMBOLS
    }:
        raise ValueError("Tiingo prospective raw directory is invalid")


def _read_snapshot_file(snapshot: Path, relative: PurePosixPath, label: str) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Tiingo prospective {label} path is invalid")
    path = snapshot.joinpath(*relative.parts)
    current = snapshot
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Tiingo prospective {label} cannot use symlinks")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Tiingo prospective {label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"Tiingo prospective {label} must be a regular file inside the snapshot")
    return resolved.read_bytes()


def _canonical_csv_bytes(rows: list[_NormalizedRow]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_NORMALIZED_COLUMNS)
    for row in rows:
        writer.writerow(
            (
                row.symbol,
                row.session_date.isoformat(),
                _decimal_text(row.open),
                _decimal_text(row.high),
                _decimal_text(row.low),
                _decimal_text(row.close),
                _decimal_text(row.volume),
                _decimal_text(row.div_cash),
                _decimal_text(row.split_factor),
            )
        )
    return output.getvalue().encode("utf-8")


def _session_date(value: object, symbol: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Tiingo prospective date is invalid for {symbol}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Tiingo prospective date is invalid for {symbol}") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != UTC.utcoffset(parsed)
        or parsed.timetz().replace(tzinfo=None) != time()
    ):
        raise ValueError(f"Tiingo prospective date is invalid for {symbol}")
    return parsed.date()


def _decimal(value: object, field: str, symbol: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"Tiingo prospective {field} is invalid for {symbol}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Tiingo prospective {field} is invalid for {symbol}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Tiingo prospective {field} is invalid for {symbol}")
    return parsed


def _write_bytes(path: Path, value: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _canonical_json_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _dataset_id(retrieval_date: date) -> str:
    return f"{TIINGO_PROSPECTIVE_EOD_VERSION}:{retrieval_date.isoformat()}"


def _snapshot_name(retrieval_date: date) -> str:
    return f"snapshot={retrieval_date.isoformat()}-{TIINGO_PROSPECTIVE_EOD_VERSION}"


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"Tiingo prospective {label} is invalid")
    digest = value.removeprefix("sha256:")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"Tiingo prospective {label} is invalid")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Tiingo prospective {label} is invalid")
    return value


def _plain_date(value: date, label: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{label} must be a date")
    return value


def _utc_datetime(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(UTC)


def _parse_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo prospective {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Tiingo prospective {label} is invalid") from exc


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Tiingo prospective {label} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Tiingo prospective {label} is invalid") from exc
    return _utc_datetime(parsed, f"Tiingo prospective {label}")


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")

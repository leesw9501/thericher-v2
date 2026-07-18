"""Fail-closed Tiingo standard-EOD corporate-action acquisition for fixed ETFs."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from math import gcd
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from thericher_v2.contracts import Bar, Timeframe

from .corporate_actions import (
    CAMPAIGN_COVERAGE_END,
    CAMPAIGN_COVERAGE_START,
    CORPORATE_ACTION_COLUMNS,
    CORPORATE_ACTION_EVENT_TYPES,
    CORPORATE_ACTION_SYMBOLS,
    CatalogedCorporateActions,
    CorporateActionEvent,
    load_cataloged_corporate_actions,
)
from .daily import load_cataloged_yahoo_daily_1d_bars
from .local import CatalogedBars, _cataloged_bars_from_verified_loader, _validate_sha256

DEFAULT_MARKET_DATA_ROOT = Path(r"D:\market_data")
DEFAULT_R2_SNAPSHOT_DIR = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_daily"
    / "canonical"
    / "ohlcv_1d"
    / "snapshot=2026-07-18-r2"
)
DEFAULT_TIINGO_SNAPSHOT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_corporate_actions"
    / "canonical"
    / "tiingo_standard_eod"
)
DEFAULT_TIINGO_RAW_D1_SNAPSHOT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "fixed_etf_daily"
    / "canonical"
    / "tiingo_raw_d1"
)
TIINGO_EOD_ENDPOINT = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
TIINGO_SOURCE_ID_PREFIX = "tiingo-standard-eod"
MINIMUM_RETRIEVAL_LAG_DAYS = 7
FIXED_R2_CAMPAIGN_SESSION_COUNT = 896
_ENV_TOKEN_RE = re.compile(r"TIINGO_API_TOKEN=(.*)\Z")
_TIINGO_RAW_D1_COLUMNS = (
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
_TIINGO_RAW_D1_SCOPE = {
    "retrospective_development_replay_only": True,
    "point_in_time_eligible": False,
    "ranking_eligible": False,
    "sealed_holdout_eligible": False,
}


class TiingoEodAcquisitionError(ValueError):
    """A masked, fail-closed Tiingo EOD acquisition failure."""


@dataclass(frozen=True, slots=True)
class R2CorporateActionLineage:
    """The verified r2 identity and exact observed sessions used for coverage."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    observed_session_dates: Mapping[str, frozenset[date]]


@dataclass(frozen=True, slots=True)
class TiingoEodSnapshotResult:
    """Non-secret facts from one loader-attested immutable snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    raw_hashes: Mapping[str, str]
    retrieved_at_utc: datetime
    coverage_session_count: int
    event_counts: Mapping[str, Mapping[str, int]]
    catalog: CatalogedCorporateActions


@dataclass(frozen=True, slots=True)
class TiingoRawD1SnapshotResult:
    """Non-secret facts from one immutable raw-D1 comparison snapshot."""

    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    source_raw_hashes: Mapping[str, str]
    row_count: int


@dataclass(frozen=True, slots=True)
class _TiingoRawD1Row:
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
class _TiingoRawD1Source:
    snapshot_dir: Path
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    raw_responses: Mapping[str, bytes]
    raw_hashes: Mapping[str, str]
    raw_sizes: Mapping[str, int]


def default_tiingo_snapshot_dir(retrieval_date: date) -> Path:
    """Return a dated, disjoint path; callers still get overwrite protection."""

    return DEFAULT_TIINGO_SNAPSHOT_ROOT / (
        f"snapshot={retrieval_date.isoformat()}-tiingo-eod-corporate-actions-r1"
    )


def default_tiingo_raw_d1_snapshot_dir(derivation_date: date) -> Path:
    """Return a dated disjoint destination for one raw-D1 comparison snapshot."""

    return DEFAULT_TIINGO_RAW_D1_SNAPSHOT_ROOT / (
        f"snapshot={derivation_date.isoformat()}-tiingo-raw-d1-r1"
    )


def read_tiingo_api_token(env_path: Path) -> str:
    """Return only the approved key from an env file without parsing other keys."""

    found: str | None = None
    try:
        with Path(env_path).open("r", encoding="utf-8", newline="") as handle:
            for line in handle:
                match = _ENV_TOKEN_RE.fullmatch(line.rstrip("\r\n"))
                if match is None:
                    continue
                if found is not None:
                    raise TiingoEodAcquisitionError("Tiingo token is unavailable")
                candidate = match.group(1).strip()
                if not candidate:
                    raise TiingoEodAcquisitionError("Tiingo token is unavailable")
                found = candidate
    except OSError as exc:
        raise TiingoEodAcquisitionError("Tiingo token is unavailable") from exc
    if found is None:
        raise TiingoEodAcquisitionError("Tiingo token is unavailable")
    return found


def load_fixed_r2_corporate_action_lineage(r2_snapshot_dir: Path) -> R2CorporateActionLineage:
    """Load the fixed r2 bytes through its existing strict local loader."""

    snapshot = Path(r2_snapshot_dir)
    if snapshot.is_symlink():
        raise ValueError("r2 snapshot cannot be a symlink")
    try:
        resolved = snapshot.resolve(strict=True)
        manifest_bytes = (resolved / "manifest.json").read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("r2 snapshot manifest is missing") from exc
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("r2 snapshot manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("r2 snapshot manifest must be an object")

    dataset_id = _required_text(manifest.get("dataset_id"), "r2 dataset_id")
    dataset_hash = _required_sha256(manifest.get("dataset_hash"), "r2 dataset_hash")
    subset_path = resolved / "ohlcv_1d.csv.gz"
    sessions: dict[str, frozenset[date]] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        bars = load_cataloged_yahoo_daily_1d_bars(
            subset_path,
            dataset_id=dataset_id,
            expected_dataset_hash=dataset_hash,
            symbol=symbol,
        )
        sessions[symbol] = frozenset(
            bar.start_ts.date()
            for bar in bars.bars
            if CAMPAIGN_COVERAGE_START <= bar.start_ts.date() <= CAMPAIGN_COVERAGE_END
        )
    _validate_observed_session_dates(sessions, require_fixed_r2_count=True)
    return R2CorporateActionLineage(
        snapshot_dir=resolved,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        manifest_hash=_sha256(manifest_bytes),
        observed_session_dates=sessions,
    )


def fetch_tiingo_standard_eod_responses(
    *,
    env_path: Path,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = 20.0,
) -> dict[str, bytes]:
    """Fetch exactly three raw EOD responses using only the approved token."""

    if timeout_seconds <= 0:
        raise ValueError("Tiingo timeout_seconds must be positive")
    token = read_tiingo_api_token(env_path)
    responses: dict[str, bytes] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        endpoint = TIINGO_EOD_ENDPOINT.format(symbol=symbol)
        query = urlencode(
            {
                "startDate": CAMPAIGN_COVERAGE_START.isoformat(),
                "endDate": CAMPAIGN_COVERAGE_END.isoformat(),
            }
        )
        request = Request(
            f"{endpoint}?{query}",
            headers={"Accept": "application/json", "Authorization": f"Token {token}"},
        )
        try:
            with opener(request, timeout=timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise TiingoEodAcquisitionError(
                        f"Tiingo EOD request failed for {symbol}: unexpected status"
                    )
                payload = response.read()
        except HTTPError as exc:
            raise TiingoEodAcquisitionError(
                f"Tiingo EOD request failed for {symbol}: HTTP {exc.code}"
            ) from exc
        except (OSError, URLError) as exc:
            raise TiingoEodAcquisitionError(
                f"Tiingo EOD request failed for {symbol}"
            ) from exc
        if not isinstance(payload, bytes) or not payload:
            raise TiingoEodAcquisitionError(f"Tiingo EOD response is unavailable for {symbol}")
        responses[symbol] = payload
    return responses


def normalize_tiingo_standard_eod_response(
    *,
    symbol: str,
    raw_response: bytes,
    expected_session_dates: frozenset[date],
) -> tuple[CorporateActionEvent, ...]:
    """Map only Tiingo date, divCash, and splitFactor into strict local events."""

    requested_symbol = _requested_symbol(symbol)
    expected = _validated_single_symbol_sessions(expected_session_dates, requested_symbol)
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError(f"Tiingo EOD response is missing for {requested_symbol}")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Tiingo EOD response is not valid UTF-8 JSON for {requested_symbol}"
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Tiingo EOD response must be a nonempty array for {requested_symbol}")

    source_id = f"{TIINGO_SOURCE_ID_PREFIX}-{requested_symbol.lower()}"
    source_hash = _sha256(raw_response).removeprefix("sha256:")[:16]
    events: list[CorporateActionEvent] = []
    observed_dates: set[date] = set()
    previous_date: date | None = None
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError(f"Tiingo EOD row must be an object for {requested_symbol}")
        session_date = _tiingo_session_date(row.get("date"), requested_symbol)
        if session_date in observed_dates:
            raise ValueError(f"Tiingo EOD response has duplicate dates for {requested_symbol}")
        if previous_date is not None and session_date <= previous_date:
            raise ValueError(
                f"Tiingo EOD response dates are not strictly ascending for {requested_symbol}"
            )
        observed_dates.add(session_date)
        previous_date = session_date
        cash = _tiingo_decimal(row.get("divCash"), "divCash", requested_symbol)
        split_factor = _tiingo_decimal(row.get("splitFactor"), "splitFactor", requested_symbol)
        if cash < 0:
            raise ValueError(f"Tiingo divCash cannot be negative for {requested_symbol}")
        if split_factor <= 0:
            raise ValueError(f"Tiingo splitFactor must be positive for {requested_symbol}")

        if cash > 0:
            events.append(
                CorporateActionEvent(
                    event_id=(
                        f"tiingo-{requested_symbol.lower()}-cash-{session_date:%Y%m%d}-{source_hash}"
                    ),
                    symbol=requested_symbol,
                    event_type="cash_distribution",
                    source_date_kind="ex_date",
                    source_event_date=session_date,
                    affected_session_date=session_date,
                    cash_amount=cash,
                    currency="USD",
                    split_numerator=None,
                    split_denominator=None,
                    source_id=source_id,
                    source_record_id=f"{requested_symbol}-{session_date.isoformat()}-cash_distribution",
                    mapping_rule_id="identity_observed_session_v1",
                    mapping_status="mapped",
                )
            )
        if split_factor != 1:
            numerator, denominator = _decimal_ratio(split_factor)
            events.append(
                CorporateActionEvent(
                    event_id=(
                        f"tiingo-{requested_symbol.lower()}-split-{session_date:%Y%m%d}-{source_hash}"
                    ),
                    symbol=requested_symbol,
                    event_type="split",
                    source_date_kind="split_trading_date",
                    source_event_date=session_date,
                    affected_session_date=session_date,
                    cash_amount=None,
                    currency=None,
                    split_numerator=numerator,
                    split_denominator=denominator,
                    source_id=source_id,
                    source_record_id=f"{requested_symbol}-{session_date.isoformat()}-split",
                    mapping_rule_id="identity_observed_session_v1",
                    mapping_status="mapped",
                )
            )
    if observed_dates != expected:
        raise ValueError(f"Tiingo EOD session coverage is incomplete for {requested_symbol}")
    return tuple(
        sorted(
            events,
            key=lambda event: (
                CORPORATE_ACTION_SYMBOLS.index(event.symbol),
                event.affected_session_date,
                CORPORATE_ACTION_EVENT_TYPES.index(event.event_type),
                event.event_id,
            ),
        )
    )


def normalize_tiingo_raw_d1_response(
    *,
    symbol: str,
    raw_response: bytes,
    expected_session_dates: frozenset[date],
) -> tuple[_TiingoRawD1Row, ...]:
    """Normalize only raw D1 fields; provider adjusted fields never enter output."""

    return _normalize_tiingo_raw_d1_response(
        symbol=symbol,
        raw_response=raw_response,
        expected_session_dates=expected_session_dates,
        require_campaign_span=True,
    )


def _normalize_tiingo_raw_d1_response(
    *,
    symbol: str,
    raw_response: bytes,
    expected_session_dates: frozenset[date],
    require_campaign_span: bool,
) -> tuple[_TiingoRawD1Row, ...]:
    requested_symbol = _requested_symbol(symbol)
    expected = _validated_single_symbol_sessions(
        expected_session_dates,
        requested_symbol,
        require_campaign_span=require_campaign_span,
    )
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError(f"Tiingo EOD response is missing for {requested_symbol}")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Tiingo EOD response is not valid UTF-8 JSON for {requested_symbol}"
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Tiingo EOD response must be a nonempty array for {requested_symbol}")

    rows: list[_TiingoRawD1Row] = []
    observed_dates: set[date] = set()
    previous_date: date | None = None
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError(f"Tiingo EOD row must be an object for {requested_symbol}")
        session_date = _tiingo_session_date(row.get("date"), requested_symbol)
        if session_date in observed_dates:
            raise ValueError(f"Tiingo EOD response has duplicate dates for {requested_symbol}")
        if previous_date is not None and session_date <= previous_date:
            raise ValueError(
                f"Tiingo EOD response dates are not strictly ascending for {requested_symbol}"
            )
        observed_dates.add(session_date)
        previous_date = session_date
        prices = tuple(
            _tiingo_decimal(row.get(field), field, requested_symbol)
            for field in ("open", "high", "low", "close")
        )
        volume = _tiingo_decimal(row.get("volume"), "volume", requested_symbol)
        div_cash = _tiingo_decimal(row.get("divCash"), "divCash", requested_symbol)
        split_factor = _tiingo_decimal(
            row.get("splitFactor"), "splitFactor", requested_symbol
        )
        _validate_raw_d1_values(
            *prices,
            volume,
            div_cash,
            split_factor,
            label=f"{requested_symbol} {session_date}",
        )
        rows.append(
            _TiingoRawD1Row(
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
    if observed_dates != expected:
        raise ValueError(f"Tiingo EOD session coverage is incomplete for {requested_symbol}")
    return tuple(rows)


def build_tiingo_eod_corporate_action_snapshot(
    *,
    destination: Path,
    raw_responses: Mapping[str, bytes],
    r2_lineage: R2CorporateActionLineage,
    retrieved_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoEodSnapshotResult:
    """Write and attest one disjoint immutable Tiingo EOD snapshot outside Git."""

    retrieved_at = _utc_datetime(retrieved_at_utc, "retrieved_at_utc")
    _assert_retrieval_lag(retrieved_at)
    _validate_observed_session_dates(r2_lineage.observed_session_dates)
    _validate_destination(destination, r2_lineage.snapshot_dir, market_data_root)
    if set(raw_responses) != set(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo EOD raw responses must contain exact fixed symbols")

    normalized: dict[str, tuple[CorporateActionEvent, ...]] = {}
    raw_hashes: dict[str, str] = {}
    raw_sizes: dict[str, int] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        raw = raw_responses[symbol]
        if not isinstance(raw, bytes):
            raise ValueError(f"Tiingo EOD raw response must be bytes for {symbol}")
        raw_hashes[symbol] = _sha256(raw)
        raw_sizes[symbol] = len(raw)
        normalized[symbol] = normalize_tiingo_standard_eod_response(
            symbol=symbol,
            raw_response=raw,
            expected_session_dates=r2_lineage.observed_session_dates[symbol],
        )
    events = tuple(event for symbol in CORPORATE_ACTION_SYMBOLS for event in normalized[symbol])
    event_bytes = _event_csv_bytes(events)
    dataset_hash = _sha256(event_bytes)
    destination_path = Path(destination)
    staging = _create_staging_directory(destination_path)
    try:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        for symbol in CORPORATE_ACTION_SYMBOLS:
            (raw_dir / f"{symbol}.json").write_bytes(raw_responses[symbol])
        (staging / "corporate_actions.csv").write_bytes(event_bytes)
        manifest = _tiingo_manifest(
            snapshot_dir=destination_path,
            dataset_hash=dataset_hash,
            event_size=len(event_bytes),
            raw_hashes=raw_hashes,
            raw_sizes=raw_sizes,
            normalized=normalized,
            r2_lineage=r2_lineage,
            retrieved_at_utc=retrieved_at,
        )
        manifest_bytes = _json_bytes(manifest)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        _load_attested_snapshot(
            staging,
            dataset_hash=dataset_hash,
            manifest_hash=_sha256(manifest_bytes),
            r2_lineage=r2_lineage,
            repo_root=repo_root,
        )
        os.rename(staging, destination_path)
        staging.parent.rmdir()
    except Exception:
        if staging.parent.exists():
            shutil.rmtree(staging.parent)
        raise

    manifest_path = destination_path / "manifest.json"
    catalog = _load_attested_snapshot(
        destination_path,
        dataset_hash=dataset_hash,
        manifest_hash=_sha256(manifest_path.read_bytes()),
        r2_lineage=r2_lineage,
        repo_root=repo_root,
    )
    return TiingoEodSnapshotResult(
        snapshot_dir=destination_path,
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        manifest_hash=catalog.manifest_hash,
        raw_hashes=dict(raw_hashes),
        retrieved_at_utc=retrieved_at,
        coverage_session_count=len(r2_lineage.observed_session_dates["SPY"]),
        event_counts={
            symbol: {
                event_type: sum(
                    event.symbol == symbol and event.event_type == event_type
                    for event in catalog.events
                )
                for event_type in CORPORATE_ACTION_EVENT_TYPES
            }
            for symbol in CORPORATE_ACTION_SYMBOLS
        },
        catalog=catalog,
    )


def acquire_fixed_tiingo_eod_corporate_action_snapshot(
    *,
    env_path: Path,
    destination: Path,
    r2_snapshot_dir: Path = DEFAULT_R2_SNAPSHOT_DIR,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    retrieved_at_utc: datetime | None = None,
    opener: Callable[..., Any] = urlopen,
    timeout_seconds: float = 20.0,
) -> TiingoEodSnapshotResult:
    """Acquire the approved source, then build one fail-closed immutable snapshot."""

    lineage = load_fixed_r2_corporate_action_lineage(r2_snapshot_dir)
    retrieved_at = _utc_datetime(retrieved_at_utc or datetime.now(UTC), "retrieved_at_utc")
    _assert_retrieval_lag(retrieved_at)
    _validate_destination(destination, lineage.snapshot_dir, market_data_root)
    responses = fetch_tiingo_standard_eod_responses(
        env_path=env_path,
        opener=opener,
        timeout_seconds=timeout_seconds,
    )
    return build_tiingo_eod_corporate_action_snapshot(
        destination=destination,
        raw_responses=responses,
        r2_lineage=lineage,
        retrieved_at_utc=retrieved_at,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )


def build_tiingo_raw_d1_comparison_snapshot(
    *,
    destination: Path,
    source_snapshot_dir: Path,
    r2_lineage: R2CorporateActionLineage,
    derived_at_utc: datetime,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoRawD1SnapshotResult:
    """Derive one immutable raw-D1 input from existing attested Tiingo bytes."""

    derived_at = _utc_datetime(derived_at_utc, "derived_at_utc")
    _validate_observed_session_dates(r2_lineage.observed_session_dates)
    source = _load_tiingo_raw_d1_source(
        source_snapshot_dir=source_snapshot_dir,
        r2_lineage=r2_lineage,
        repo_root=repo_root,
    )
    _validate_raw_d1_destination(
        destination=destination,
        source_snapshot_dir=source.snapshot_dir,
        r2_snapshot_dir=r2_lineage.snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    rows_by_symbol = {
        symbol: normalize_tiingo_raw_d1_response(
            symbol=symbol,
            raw_response=source.raw_responses[symbol],
            expected_session_dates=r2_lineage.observed_session_dates[symbol],
        )
        for symbol in CORPORATE_ACTION_SYMBOLS
    }
    rows = tuple(row for symbol in CORPORATE_ACTION_SYMBOLS for row in rows_by_symbol[symbol])
    subset_bytes = _gzip_bytes(_raw_d1_csv_bytes(rows))
    dataset_hash = _sha256(subset_bytes)
    destination_path = Path(destination)
    staging = _create_staging_directory(destination_path)
    try:
        (staging / "ohlcv_1d.csv.gz").write_bytes(subset_bytes)
        manifest = _tiingo_raw_d1_manifest(
            snapshot_dir=destination_path,
            dataset_hash=dataset_hash,
            subset_size=len(subset_bytes),
            source=source,
            r2_lineage=r2_lineage,
            rows_by_symbol=rows_by_symbol,
            derived_at_utc=derived_at,
        )
        manifest_bytes = _json_bytes(manifest)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        os.rename(staging, destination_path)
        staging.parent.rmdir()
    except Exception:
        if staging.parent.exists():
            shutil.rmtree(staging.parent)
        raise
    manifest_hash = _sha256((destination_path / "manifest.json").read_bytes())
    return TiingoRawD1SnapshotResult(
        snapshot_dir=destination_path,
        dataset_id=f"us_equities.fixed_etf_tiingo_raw_d1.{destination_path.name}",
        dataset_hash=dataset_hash,
        manifest_hash=manifest_hash,
        source_raw_hashes=dict(source.raw_hashes),
        row_count=len(rows),
    )


def load_cataloged_tiingo_raw_d1_bars(
    snapshot_dir: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    source_snapshot_dir: Path,
    r2_lineage: R2CorporateActionLineage,
    symbol: str,
    market: str = "US",
    repo_root: Path | None = None,
) -> CatalogedBars:
    """Load one raw-D1 stream only after re-attesting every local dependency.

    The comparison snapshot is development-only and uses r2's observed calendar.
    It does not expose Tiingo adjusted fields or infer corporate-action behavior.
    """

    resolved_dataset_id = _required_text(dataset_id, "dataset_id")
    _validate_sha256(expected_dataset_hash, "expected_dataset_hash")
    _validate_sha256(expected_manifest_hash, "expected_manifest_hash")
    requested_symbol = _requested_symbol(symbol)
    resolved_market = market.strip().upper()
    if not resolved_market:
        raise ValueError("market is required")

    verified_r2 = _reattest_r2_lineage(r2_lineage, repo_root=repo_root)
    snapshot = _external_snapshot_dir(snapshot_dir, repo_root=repo_root)
    if not snapshot.name.startswith("snapshot="):
        raise ValueError("Tiingo raw-D1 snapshot must use a snapshot= directory")
    expected_dataset_id = f"us_equities.fixed_etf_tiingo_raw_d1.{snapshot.name}"
    if resolved_dataset_id != expected_dataset_id:
        raise ValueError("Tiingo raw-D1 dataset_id is inconsistent with its snapshot path")

    manifest_path = snapshot / "manifest.json"
    manifest_bytes = _read_external_snapshot_file(
        snapshot, manifest_path, "Tiingo raw-D1 manifest"
    )
    actual_manifest_hash = _sha256(manifest_bytes)
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError("Tiingo raw-D1 manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo raw-D1 manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo raw-D1 manifest must be an object")

    source = _load_tiingo_raw_d1_source(
        source_snapshot_dir=source_snapshot_dir,
        r2_lineage=verified_r2,
        repo_root=repo_root,
    )
    rows_by_symbol = {
        fixed_symbol: normalize_tiingo_raw_d1_response(
            symbol=fixed_symbol,
            raw_response=source.raw_responses[fixed_symbol],
            expected_session_dates=verified_r2.observed_session_dates[fixed_symbol],
        )
        for fixed_symbol in CORPORATE_ACTION_SYMBOLS
    }
    rows = tuple(
        row for fixed_symbol in CORPORATE_ACTION_SYMBOLS for row in rows_by_symbol[fixed_symbol]
    )
    subset_path = snapshot / "ohlcv_1d.csv.gz"
    subset_bytes = _read_external_snapshot_file(
        snapshot, subset_path, "Tiingo raw-D1 subset"
    )
    actual_dataset_hash = _sha256(subset_bytes)
    if actual_dataset_hash != expected_dataset_hash:
        raise ValueError("Tiingo raw-D1 dataset hash mismatch")
    _validate_tiingo_raw_d1_manifest(
        manifest,
        snapshot_dir=snapshot,
        dataset_id=resolved_dataset_id,
        dataset_hash=actual_dataset_hash,
        source=source,
        r2_lineage=verified_r2,
    )
    try:
        canonical_subset_bytes = gzip.decompress(subset_bytes)
    except OSError as exc:
        raise ValueError("Tiingo raw-D1 subset is not a valid gzip stream") from exc
    if canonical_subset_bytes != _raw_d1_csv_bytes(rows):
        raise ValueError("Tiingo raw-D1 subset does not match attested raw source bytes")

    bars = tuple(
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
        for row in rows_by_symbol[requested_symbol]
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id=resolved_dataset_id,
        dataset_hash=actual_dataset_hash,
        source_path=subset_path,
        bars=bars,
    )


def _load_attested_snapshot(
    snapshot_dir: Path,
    *,
    dataset_hash: str,
    manifest_hash: str,
    r2_lineage: R2CorporateActionLineage,
    repo_root: Path | None,
) -> CatalogedCorporateActions:
    catalog = load_cataloged_corporate_actions(
        snapshot_dir,
        dataset_id=f"us_equities.fixed_etf_corporate_actions.{snapshot_dir.name}",
        expected_dataset_hash=dataset_hash,
        expected_manifest_hash=manifest_hash,
        expected_r2_dataset_id=r2_lineage.dataset_id,
        expected_r2_dataset_hash=r2_lineage.dataset_hash,
        expected_r2_manifest_hash=r2_lineage.manifest_hash,
        observed_session_dates=r2_lineage.observed_session_dates,
        require_replay_eligible=True,
        repo_root=repo_root,
    )
    _validate_tiingo_finalization_metadata(snapshot_dir / "manifest.json", catalog)
    return catalog


def _validate_tiingo_finalization_metadata(
    manifest_path: Path,
    catalog: CatalogedCorporateActions,
) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo snapshot manifest is not readable JSON") from exc
    source_contract = manifest.get("tiingo_source_contract")
    if source_contract != {
        "endpoint_template": TIINGO_EOD_ENDPOINT,
        "normalization_fields": ["date", "divCash", "splitFactor"],
        "raw_response_policy": "exact_per_symbol_bytes",
        "source": "Tiingo standard EOD API",
    }:
        raise ValueError("Tiingo snapshot source contract is invalid")
    finalization = manifest.get("event_finalization")
    expected = {
        "campaign_end": CAMPAIGN_COVERAGE_END.isoformat(),
        "minimum_retrieval_lag_days": MINIMUM_RETRIEVAL_LAG_DAYS,
        "policy": "minimum_calendar_days_after_campaign_end_v1",
        "retrieved_at_utc": _format_utc(catalog.retrieved_at_utc),
    }
    if finalization != expected:
        raise ValueError("Tiingo snapshot finalization metadata is invalid")
    _assert_retrieval_lag(catalog.retrieved_at_utc)


def _tiingo_manifest(
    *,
    snapshot_dir: Path,
    dataset_hash: str,
    event_size: int,
    raw_hashes: Mapping[str, str],
    raw_sizes: Mapping[str, int],
    normalized: Mapping[str, tuple[CorporateActionEvent, ...]],
    r2_lineage: R2CorporateActionLineage,
    retrieved_at_utc: datetime,
) -> dict[str, Any]:
    snapshot_name = snapshot_dir.name
    coverage = []
    for symbol in CORPORATE_ACTION_SYMBOLS:
        source_id = f"{TIINGO_SOURCE_ID_PREFIX}-{symbol.lower()}"
        for event_type in CORPORATE_ACTION_EVENT_TYPES:
            coverage.append(
                {
                    "symbol": symbol,
                    "event_type": event_type,
                    "start": CAMPAIGN_COVERAGE_START.isoformat(),
                    "end": CAMPAIGN_COVERAGE_END.isoformat(),
                    "status": "complete",
                    "event_count": sum(
                        event.event_type == event_type for event in normalized[symbol]
                    ),
                    "source_ids": [source_id],
                }
            )
    raw_sources = []
    for symbol in CORPORATE_ACTION_SYMBOLS:
        filename = f"{symbol}.json"
        raw_sources.append(
            {
                "source_id": f"{TIINGO_SOURCE_ID_PREFIX}-{symbol.lower()}",
                "provider": "Tiingo standard EOD API",
                "source_url": TIINGO_EOD_ENDPOINT.format(symbol=symbol),
                "source_kind": "licensed_api",
                "acquisition_mode": "authorized_api",
                "use_scope": "private_internal_use",
                "rights_status": "confirmed",
                "symbols": [symbol],
                "event_types": list(CORPORATE_ACTION_EVENT_TYPES),
                "coverage_start": CAMPAIGN_COVERAGE_START.isoformat(),
                "coverage_end": CAMPAIGN_COVERAGE_END.isoformat(),
                "filename": filename,
                "path": str(snapshot_dir / "raw" / filename),
                "sha256": raw_hashes[symbol],
                "size_bytes": raw_sizes[symbol],
                "retrieved_at_utc": _format_utc(retrieved_at_utc),
                "source_as_of": CAMPAIGN_COVERAGE_END.isoformat(),
                "revision": "tiingo-standard-eod-v1",
            }
        )
    return {
        "schema_version": 1,
        "kind": "fixed_etf_corporate_actions",
        "dataset_id": f"us_equities.fixed_etf_corporate_actions.{snapshot_name}",
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "symbols": list(CORPORATE_ACTION_SYMBOLS),
        "event_types": list(CORPORATE_ACTION_EVENT_TYPES),
        "date_kinds": ["ex_date", "split_trading_date"],
        "normalized_events": {
            "path": str(snapshot_dir / "corporate_actions.csv"),
            "sha256": dataset_hash,
            "size_bytes": event_size,
            "schema": list(CORPORATE_ACTION_COLUMNS),
        },
        "raw_sources": raw_sources,
        "snapshot_metadata": {
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
            "source_as_of": CAMPAIGN_COVERAGE_END.isoformat(),
            "revision": "tiingo-standard-eod-corporate-actions-r1",
        },
        "campaign_coverage": {
            "start": CAMPAIGN_COVERAGE_START.isoformat(),
            "end": CAMPAIGN_COVERAGE_END.isoformat(),
        },
        "coverage": coverage,
        "date_semantics": {
            "exchange_timezone": "America/New_York",
            "session_date_semantics": "date_only_no_utc_conversion",
            "non_session_policy": "reject",
            "ambiguous_effective_date_policy": "reject",
        },
        "mapping_policy": {
            "id": "identity_observed_session_v1",
            "status": "mapped_only",
            "calendar_lineage": "verified_r2_observed_sessions",
        },
        "duplicate_policy": {
            "event_id": "reject",
            "source_record": "reject",
            "identical_normalized_action": "preserve_records_collapse_mask_date",
            "conflict": "reject",
        },
        "scope": {
            "retrospective_development_replay_only": True,
            "point_in_time_eligible": False,
            "ranking_eligible": False,
            "sealed_holdout_eligible": False,
        },
        "r2_lineage": {
            "dataset_id": r2_lineage.dataset_id,
            "dataset_hash": r2_lineage.dataset_hash,
            "manifest_sha256": r2_lineage.manifest_hash,
            "snapshot_name": r2_lineage.snapshot_dir.name,
            "subset_path": str(r2_lineage.snapshot_dir / "ohlcv_1d.csv.gz"),
            "manifest_path": str(r2_lineage.snapshot_dir / "manifest.json"),
        },
        "event_finalization": {
            "campaign_end": CAMPAIGN_COVERAGE_END.isoformat(),
            "minimum_retrieval_lag_days": MINIMUM_RETRIEVAL_LAG_DAYS,
            "policy": "minimum_calendar_days_after_campaign_end_v1",
            "retrieved_at_utc": _format_utc(retrieved_at_utc),
        },
        "tiingo_source_contract": {
            "endpoint_template": TIINGO_EOD_ENDPOINT,
            "normalization_fields": ["date", "divCash", "splitFactor"],
            "raw_response_policy": "exact_per_symbol_bytes",
            "source": "Tiingo standard EOD API",
        },
    }


def _event_csv_bytes(events: tuple[CorporateActionEvent, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CORPORATE_ACTION_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for event in events:
        writer.writerow(
            {
                "event_id": event.event_id,
                "symbol": event.symbol,
                "event_type": event.event_type,
                "source_date_kind": event.source_date_kind,
                "source_event_date": event.source_event_date.isoformat(),
                "affected_session_date": event.affected_session_date.isoformat(),
                "cash_amount": "" if event.cash_amount is None else format(event.cash_amount, "f"),
                "currency": event.currency or "",
                "split_numerator": (
                    "" if event.split_numerator is None else format(event.split_numerator, "f")
                ),
                "split_denominator": (
                    "" if event.split_denominator is None else format(event.split_denominator, "f")
                ),
                "source_id": event.source_id,
                "source_record_id": event.source_record_id,
                "mapping_rule_id": event.mapping_rule_id,
                "mapping_status": event.mapping_status,
            }
        )
    return buffer.getvalue().encode("utf-8")


def _validate_destination(destination: Path, r2_snapshot_dir: Path, market_data_root: Path) -> None:
    root = Path(market_data_root).resolve(strict=True)
    requested = Path(destination)
    if requested.is_symlink() or requested.exists():
        raise FileExistsError("Tiingo snapshot destination already exists or is a symlink")
    resolved_destination = requested.resolve(strict=False)
    if not resolved_destination.is_relative_to(root):
        raise ValueError("Tiingo snapshot destination must be under market_data_root")
    if not requested.name.startswith("snapshot="):
        raise ValueError("Tiingo snapshot destination must use a snapshot= directory")
    r2 = Path(r2_snapshot_dir).resolve(strict=True)
    if resolved_destination.is_relative_to(r2) or r2.is_relative_to(resolved_destination):
        raise ValueError("Tiingo snapshot cannot overlap the r2 data snapshot")
    usage = shutil.disk_usage(root)
    if usage.free / usage.total < 0.15:
        raise ValueError("Tiingo acquisition would breach the market-data free-space floor")


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.pending-", dir=destination.parent)
    )
    staging = pending_root / destination.name
    staging.mkdir()
    return staging


def _validate_observed_session_dates(
    value: Mapping[str, frozenset[date]],
    *,
    require_fixed_r2_count: bool = False,
) -> None:
    if set(value) != set(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("r2 observed sessions must contain exact fixed symbols")
    campaign_sets: set[frozenset[date]] = set()
    for symbol in CORPORATE_ACTION_SYMBOLS:
        campaign = _validated_single_symbol_sessions(value[symbol], symbol)
        campaign_sets.add(campaign)
    if len(campaign_sets) != 1:
        raise ValueError("r2 fixed-instrument sessions must be identical")
    if require_fixed_r2_count and len(next(iter(campaign_sets))) != FIXED_R2_CAMPAIGN_SESSION_COUNT:
        raise ValueError("r2 fixed campaign session coverage is incomplete")


def _validated_single_symbol_sessions(
    value: frozenset[date],
    symbol: str,
    *,
    require_campaign_span: bool = True,
) -> frozenset[date]:
    if (
        not isinstance(value, frozenset)
        or not value
        or any(type(item) is not date for item in value)
    ):
        raise ValueError(f"r2 observed sessions are invalid for {symbol}")
    campaign = frozenset(
        item for item in value if CAMPAIGN_COVERAGE_START <= item <= CAMPAIGN_COVERAGE_END
    )
    if campaign != value or (
        require_campaign_span
        and not {CAMPAIGN_COVERAGE_START, CAMPAIGN_COVERAGE_END} <= campaign
    ):
        raise ValueError(f"r2 observed sessions do not span the fixed campaign for {symbol}")
    return campaign


def _requested_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if symbol not in CORPORATE_ACTION_SYMBOLS:
        raise ValueError("Tiingo symbol must be one of SPY, QQQ, IWM")
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
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Tiingo {field} is missing or malformed for {symbol}")
    if not isinstance(value, (int, float, str)):
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


def _decimal_ratio(value: Decimal) -> tuple[Decimal, Decimal]:
    sign, digits, exponent = value.as_tuple()
    coefficient = int("".join(str(digit) for digit in digits))
    if sign or coefficient <= 0:
        raise ValueError("Tiingo splitFactor must be positive")
    numerator = coefficient * (10**exponent) if exponent >= 0 else coefficient
    denominator = 1 if exponent >= 0 else 10 ** (-exponent)
    divisor = gcd(numerator, denominator)
    return Decimal(numerator // divisor), Decimal(denominator // divisor)


def _assert_retrieval_lag(retrieved_at_utc: datetime) -> None:
    earliest = CAMPAIGN_COVERAGE_END + timedelta(days=MINIMUM_RETRIEVAL_LAG_DAYS)
    if retrieved_at_utc.date() < earliest:
        raise ValueError("Tiingo retrieval is too close to campaign end to freeze events")


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _required_text(value: object, label: str) -> str:
    text = str(value or "")
    if not text or text != text.strip():
        raise ValueError(f"{label} is required")
    return text


def _required_sha256(value: object, label: str) -> str:
    text = _required_text(value, label)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", text):
        raise ValueError(f"{label} is invalid")
    return text


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _reattest_r2_lineage(
    r2_lineage: R2CorporateActionLineage,
    *,
    repo_root: Path | None,
) -> R2CorporateActionLineage:
    if not isinstance(r2_lineage, R2CorporateActionLineage):
        raise ValueError("Tiingo raw-D1 requires an r2 lineage")
    verified = load_fixed_r2_corporate_action_lineage(r2_lineage.snapshot_dir)
    _assert_external_path(verified.snapshot_dir, repo_root=repo_root)
    if (
        verified.dataset_id != r2_lineage.dataset_id
        or verified.dataset_hash != r2_lineage.dataset_hash
        or verified.manifest_hash != r2_lineage.manifest_hash
        or verified.observed_session_dates != r2_lineage.observed_session_dates
    ):
        raise ValueError("Tiingo raw-D1 r2 lineage re-attestation mismatch")
    _validate_observed_session_dates(
        verified.observed_session_dates,
        require_fixed_r2_count=True,
    )
    return verified


def _load_tiingo_raw_d1_source(
    *,
    source_snapshot_dir: Path,
    r2_lineage: R2CorporateActionLineage,
    repo_root: Path | None,
) -> _TiingoRawD1Source:
    source = _external_snapshot_dir(source_snapshot_dir, repo_root=repo_root)
    manifest_path = source / "manifest.json"
    manifest_bytes = _read_external_snapshot_file(source, manifest_path, "Tiingo source manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo source manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo source manifest must be an object")
    dataset_id = _required_text(manifest.get("dataset_id"), "Tiingo source dataset_id")
    dataset_hash = _required_sha256(manifest.get("dataset_hash"), "Tiingo source dataset_hash")
    manifest_hash = _sha256(manifest_bytes)
    _load_attested_snapshot(
        source,
        dataset_hash=dataset_hash,
        manifest_hash=manifest_hash,
        r2_lineage=r2_lineage,
        repo_root=repo_root,
    )

    raw_entries = manifest.get("raw_sources")
    if not isinstance(raw_entries, list):
        raise ValueError("Tiingo source raw evidence is missing")
    entries = {
        entry.get("source_id"): entry
        for entry in raw_entries
        if isinstance(entry, dict)
    }
    raw_responses: dict[str, bytes] = {}
    raw_hashes: dict[str, str] = {}
    raw_sizes: dict[str, int] = {}
    for symbol in CORPORATE_ACTION_SYMBOLS:
        source_id = f"{TIINGO_SOURCE_ID_PREFIX}-{symbol.lower()}"
        entry = entries.get(source_id)
        if not isinstance(entry, dict) or entry.get("filename") != f"{symbol}.json":
            raise ValueError(f"Tiingo source raw evidence is invalid for {symbol}")
        expected_hash = _required_sha256(entry.get("sha256"), f"Tiingo source {symbol} hash")
        expected_size = entry.get("size_bytes")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size <= 0
        ):
            raise ValueError(f"Tiingo source {symbol} size is invalid")
        raw = _read_external_snapshot_file(source, source / "raw" / f"{symbol}.json", "Tiingo raw")
        if len(raw) != expected_size or _sha256(raw) != expected_hash:
            raise ValueError(f"Tiingo source raw hash mismatch for {symbol}")
        raw_responses[symbol] = raw
        raw_hashes[symbol] = expected_hash
        raw_sizes[symbol] = expected_size
    return _TiingoRawD1Source(
        snapshot_dir=source,
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        manifest_hash=manifest_hash,
        raw_responses=raw_responses,
        raw_hashes=raw_hashes,
        raw_sizes=raw_sizes,
    )


def _validate_tiingo_raw_d1_manifest(
    manifest: Mapping[str, Any],
    *,
    snapshot_dir: Path,
    dataset_id: str,
    dataset_hash: str,
    source: _TiingoRawD1Source,
    r2_lineage: R2CorporateActionLineage,
) -> None:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "fixed_etf_tiingo_raw_d1_comparison"
        or manifest.get("immutable_snapshot") is not True
    ):
        raise ValueError("Tiingo raw-D1 manifest contract is invalid")
    if _required_text(manifest.get("dataset_id"), "Tiingo raw-D1 dataset_id") != dataset_id:
        raise ValueError("Tiingo raw-D1 manifest dataset_id mismatch")
    if _required_sha256(
        manifest.get("dataset_hash"), "Tiingo raw-D1 dataset_hash"
    ) != dataset_hash:
        raise ValueError("Tiingo raw-D1 manifest dataset hash mismatch")
    if manifest.get("symbols") != list(CORPORATE_ACTION_SYMBOLS) or manifest.get(
        "symbol_order"
    ) != list(CORPORATE_ACTION_SYMBOLS):
        raise ValueError("Tiingo raw-D1 manifest symbol contract is invalid")

    subset = manifest.get("subset")
    if not isinstance(subset, dict):
        raise ValueError("Tiingo raw-D1 manifest subset evidence is missing")
    if (
        _required_sha256(subset.get("sha256"), "Tiingo raw-D1 subset sha256")
        != dataset_hash
        or subset.get("schema") != list(_TIINGO_RAW_D1_COLUMNS)
        or subset.get("format") != "csv.gz"
        or subset.get("ordering") != "symbol_order_then_date_ascending"
    ):
        raise ValueError("Tiingo raw-D1 manifest subset evidence is invalid")
    _assert_manifest_path_tail(
        subset.get("path"),
        snapshot_name=snapshot_dir.name,
        basename="ohlcv_1d.csv.gz",
        label="Tiingo raw-D1 subset path",
    )

    source_lineage = manifest.get("source_lineage")
    if not isinstance(source_lineage, dict):
        raise ValueError("Tiingo raw-D1 manifest source lineage is missing")
    tiingo_lineage = source_lineage.get("tiingo_corporate_actions")
    if not isinstance(tiingo_lineage, dict) or any(
        tiingo_lineage.get(key) != expected
        for key, expected in {
            "dataset_id": source.dataset_id,
            "dataset_hash": source.dataset_hash,
            "manifest_sha256": source.manifest_hash,
            "snapshot_name": source.snapshot_dir.name,
        }.items()
    ):
        raise ValueError("Tiingo raw-D1 source snapshot lineage is invalid")
    _assert_manifest_path_tail(
        tiingo_lineage.get("manifest_path"),
        snapshot_name=source.snapshot_dir.name,
        basename="manifest.json",
        label="Tiingo raw-D1 source manifest path",
    )

    r2_manifest_lineage = source_lineage.get("r2_calendar")
    if not isinstance(r2_manifest_lineage, dict) or any(
        r2_manifest_lineage.get(key) != expected
        for key, expected in {
            "dataset_id": r2_lineage.dataset_id,
            "dataset_hash": r2_lineage.dataset_hash,
            "manifest_sha256": r2_lineage.manifest_hash,
            "snapshot_name": r2_lineage.snapshot_dir.name,
        }.items()
    ):
        raise ValueError("Tiingo raw-D1 r2 calendar lineage is invalid")
    _assert_manifest_path_tail(
        r2_manifest_lineage.get("subset_path"),
        snapshot_name=r2_lineage.snapshot_dir.name,
        basename="ohlcv_1d.csv.gz",
        label="Tiingo raw-D1 r2 subset path",
    )
    _assert_manifest_path_tail(
        r2_manifest_lineage.get("manifest_path"),
        snapshot_name=r2_lineage.snapshot_dir.name,
        basename="manifest.json",
        label="Tiingo raw-D1 r2 manifest path",
    )

    if (
        manifest.get("raw_price_policy") != "copy_raw_ohlcv_without_price_rescaling"
        or manifest.get("corporate_action_policy")
        != "copy_divCash_and_splitFactor_without_derived_events"
        or manifest.get("normalization_fields")
        != [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "divCash",
            "splitFactor",
        ]
        or manifest.get("scope") != _TIINGO_RAW_D1_SCOPE
    ):
        raise ValueError("Tiingo raw-D1 data semantics are invalid")


def _assert_manifest_path_tail(
    value: object,
    *,
    snapshot_name: str,
    basename: str,
    label: str,
) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    parts = PurePosixPath(value.replace("\\", "/")).parts
    if len(parts) < 2 or tuple(parts[-2:]) != (snapshot_name, basename):
        raise ValueError(f"{label} is invalid")


def _validate_raw_d1_destination(
    *,
    destination: Path,
    source_snapshot_dir: Path,
    r2_snapshot_dir: Path,
    market_data_root: Path,
    repo_root: Path | None,
) -> None:
    _validate_destination(destination, r2_snapshot_dir, market_data_root)
    resolved_destination = Path(destination).resolve(strict=False)
    source = Path(source_snapshot_dir).resolve(strict=True)
    if (
        resolved_destination.is_relative_to(source)
        or source.is_relative_to(resolved_destination)
    ):
        raise ValueError("Tiingo raw-D1 snapshot cannot overlap the source snapshot")
    _assert_external_path(resolved_destination, repo_root=repo_root)
    usage = shutil.disk_usage(Path(market_data_root).resolve(strict=True))
    if usage.free / usage.total < 0.20:
        warnings.warn(
            "Tiingo raw-D1 derivation is below the 20% market-data free-space warning level",
            RuntimeWarning,
            stacklevel=2,
        )


def _tiingo_raw_d1_manifest(
    *,
    snapshot_dir: Path,
    dataset_hash: str,
    subset_size: int,
    source: _TiingoRawD1Source,
    r2_lineage: R2CorporateActionLineage,
    rows_by_symbol: Mapping[str, tuple[_TiingoRawD1Row, ...]],
    derived_at_utc: datetime,
) -> dict[str, Any]:
    rows = tuple(row for symbol in CORPORATE_ACTION_SYMBOLS for row in rows_by_symbol[symbol])
    return {
        "schema_version": 1,
        "kind": "fixed_etf_tiingo_raw_d1_comparison",
        "dataset_id": f"us_equities.fixed_etf_tiingo_raw_d1.{snapshot_dir.name}",
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "symbols": list(CORPORATE_ACTION_SYMBOLS),
        "symbol_order": list(CORPORATE_ACTION_SYMBOLS),
        "row_count": len(rows),
        "per_symbol_counts": {
            symbol: len(rows_by_symbol[symbol]) for symbol in CORPORATE_ACTION_SYMBOLS
        },
        "date_ranges": {
            symbol: {
                "min": rows_by_symbol[symbol][0].session_date.isoformat(),
                "max": rows_by_symbol[symbol][-1].session_date.isoformat(),
                "sessions": len(rows_by_symbol[symbol]),
            }
            for symbol in CORPORATE_ACTION_SYMBOLS
        },
        "subset": {
            "path": str(snapshot_dir / "ohlcv_1d.csv.gz"),
            "size_bytes": subset_size,
            "sha256": dataset_hash,
            "schema": list(_TIINGO_RAW_D1_COLUMNS),
            "format": "csv.gz",
            "ordering": "symbol_order_then_date_ascending",
        },
        "source_lineage": {
            "tiingo_corporate_actions": {
                "dataset_id": source.dataset_id,
                "dataset_hash": source.dataset_hash,
                "manifest_sha256": source.manifest_hash,
                "snapshot_name": source.snapshot_dir.name,
                "manifest_path": str(source.snapshot_dir / "manifest.json"),
            },
            "r2_calendar": {
                "dataset_id": r2_lineage.dataset_id,
                "dataset_hash": r2_lineage.dataset_hash,
                "manifest_sha256": r2_lineage.manifest_hash,
                "snapshot_name": r2_lineage.snapshot_dir.name,
                "subset_path": str(r2_lineage.snapshot_dir / "ohlcv_1d.csv.gz"),
                "manifest_path": str(r2_lineage.snapshot_dir / "manifest.json"),
            },
        },
        "source_raw_responses": [
            {
                "symbol": symbol,
                "filename": f"{symbol}.json",
                "sha256": source.raw_hashes[symbol],
                "size_bytes": source.raw_sizes[symbol],
            }
            for symbol in CORPORATE_ACTION_SYMBOLS
        ],
        "campaign_coverage": {
            "start": CAMPAIGN_COVERAGE_START.isoformat(),
            "end": CAMPAIGN_COVERAGE_END.isoformat(),
            "calendar_lineage": "verified_r2_observed_sessions",
        },
        "snapshot_metadata": {
            "derived_at_utc": _format_utc(derived_at_utc),
            "source_as_of": CAMPAIGN_COVERAGE_END.isoformat(),
            "revision": "tiingo-standard-eod-raw-d1-r1",
        },
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
        "scope": dict(_TIINGO_RAW_D1_SCOPE),
    }


def _external_snapshot_dir(path: Path, *, repo_root: Path | None) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError("Tiingo source snapshot cannot be a symlink")
    try:
        snapshot = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("Tiingo source snapshot directory is missing") from exc
    if not snapshot.is_dir():
        raise ValueError("Tiingo source snapshot must be a directory")
    _assert_external_path(snapshot, repo_root=repo_root)
    return snapshot


def _assert_external_path(path: Path, *, repo_root: Path | None) -> None:
    candidate = Path(path).resolve(strict=False)
    if repo_root is not None:
        root = Path(repo_root).resolve(strict=False)
        docker_market_data = Path("/app/market_data").resolve()
        if candidate == root or candidate.is_relative_to(root):
            if root != Path("/app").resolve() or not candidate.is_relative_to(docker_market_data):
                raise ValueError("Tiingo raw-D1 data must be outside Git")
    if any((parent / ".git").exists() for parent in (candidate, *candidate.parents)):
        raise ValueError("Tiingo raw-D1 data must be outside Git")


def _read_external_snapshot_file(snapshot: Path, path: Path, label: str) -> bytes:
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


def _validate_raw_d1_values(
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


def _raw_d1_csv_bytes(rows: tuple[_TiingoRawD1Row, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_TIINGO_RAW_D1_COLUMNS, lineterminator="\n")
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

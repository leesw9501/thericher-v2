"""Fixed-instrument daily data preparation and local hash-bound loading."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import (
    CatalogedBars,
    _cataloged_bars_from_verified_loader,
    _validate_sha256,
)

FIXED_ETF_DAILY_SYMBOLS = ("SPY", "QQQ", "IWM")
DEVELOPMENT_MIN_SESSIONS = 756
ADJUSTMENT_POLICY_ID = "yahoo_adj_close_price_factor_raw_volume_v1"
RAW_EXECUTION_POLICY_ID = "raw_ohlcv_campaign_v1"
FACTOR_CHANGE_RELATIVE_THRESHOLD = Decimal("0.0001")
_R2_DATASET_KIND = "fixed_instrument_raw_daily_campaign_subset"
_ADJUSTED_CONTAINMENT_TOLERANCE = Decimal("1e-24")
SOURCE_REQUIRED_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    "asset_type",
    "yahoo_symbol",
    "source",
)
R1_SUBSET_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjustment_factor",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "raw_adj_close",
    "asset_type",
    "yahoo_symbol",
    "source",
)
R2_SUBSET_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "diagnostic_adjusted_open",
    "diagnostic_adjusted_high",
    "diagnostic_adjusted_low",
    "diagnostic_adj_close",
    "diagnostic_adjustment_factor",
    "factor_change",
    "asset_type",
    "yahoo_symbol",
    "source",
)


@dataclass(frozen=True)
class DevelopmentDailyUniverseRef:
    """One immutable, retrospective-only reference to a Yahoo daily snapshot."""

    dataset_id: str
    snapshot: str
    snapshot_path: Path
    manifest_path: Path
    dataset_hash: str
    manifest_hash: str
    snapshot_created_at_utc: str
    common_session_start: date
    symbols: tuple[str, ...]
    source_name: str
    retrospective_development_replay_only: bool
    development_ref_universe_is_inception_truncated_and_survivor_selected: bool
    point_in_time_eligible: bool
    survivorship_bias_risk: str
    delisting_coverage: str
    corporate_action_policy: str


@dataclass(frozen=True)
class DevelopmentDailyStream:
    """A non-campaign summary of one development-only daily stream."""

    symbol: str
    dataset_id: str
    dataset_hash: str
    source_path: Path
    session_count: int
    first_start_ts: datetime
    last_start_ts: datetime


@dataclass(frozen=True)
class DevelopmentDailyUniverse:
    """Hash-bound descriptive streams retained behind a development boundary."""

    reference: DevelopmentDailyUniverseRef
    streams: tuple[DevelopmentDailyStream, ...]


BROAD_DAILY_DEVELOPMENT_UNIVERSE = DevelopmentDailyUniverseRef(
    dataset_id="us_equities.yahoo_daily_universe.1d.snapshot=2026-06-23",
    snapshot="2026-06-23",
    snapshot_path=Path(
        "D:/market_data/us_equities/yahoo_daily_universe/canonical/ohlcv_daily/"
        "snapshot=2026-06-23/ohlcv_daily.csv.gz"
    ),
    manifest_path=Path(
        "D:/market_data/us_equities/yahoo_daily_universe/manifests/"
        "yahoo_daily_universe_snapshot=2026-06-23.json"
    ),
    dataset_hash="sha256:1690a766a820b3e6385c76605c7e02548ab0e428148c93f85388c7a6a8b065b4",
    manifest_hash="sha256:642eff01919da260b388a66303db1954c68d7cd6ceb9685cac3c923d348b9a03",
    snapshot_created_at_utc="2026-06-23T06:14:33Z",
    common_session_start=date(2000, 5, 26),
    symbols=FIXED_ETF_DAILY_SYMBOLS,
    source_name="yahoo_chart_unofficial",
    retrospective_development_replay_only=True,
    development_ref_universe_is_inception_truncated_and_survivor_selected=True,
    point_in_time_eligible=False,
    survivorship_bias_risk="present",
    delisting_coverage="unproven",
    corporate_action_policy="raw_ohlcv_unadjusted_unverified",
)


def build_fixed_etf_daily_subset(
    source_path: Path,
    output_dir: Path,
    *,
    constructed_at_utc: datetime | None = None,
) -> Path:
    """Create the legacy immutable r1 adjusted-price subset and manifest."""

    source = Path(source_path)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"immutable output snapshot already exists: {destination}")
    constructed_at = constructed_at_utc or datetime.now(UTC)
    if constructed_at.tzinfo is None:
        raise ValueError("constructed_at_utc must be timezone-aware")
    constructed_at = constructed_at.astimezone(UTC)

    rows_by_symbol, scan = _scan_source_once(source)
    ordered_rows = [
        row
        for symbol in FIXED_ETF_DAILY_SYMBOLS
        for row in sorted(rows_by_symbol[symbol], key=lambda item: item["date"])
    ]
    counts = {symbol: len(rows_by_symbol[symbol]) for symbol in FIXED_ETF_DAILY_SYMBOLS}
    missing_symbols = [symbol for symbol, count in counts.items() if count == 0]
    if missing_symbols:
        raise ValueError(f"source has no rows for fixed symbols: {', '.join(missing_symbols)}")

    date_ranges = {
        symbol: {
            "min": min(row["date"] for row in rows),
            "max": max(row["date"] for row in rows),
            "sessions": len(rows),
        }
        for symbol, rows in rows_by_symbol.items()
    }
    below_floor = [
        symbol for symbol, count in counts.items() if count < DEVELOPMENT_MIN_SESSIONS
    ]
    development_eligible = not below_floor

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    subset_path = destination / "ohlcv_1d.csv.gz"
    _write_deterministic_gzip(subset_path, ordered_rows)
    subset_hash = _sha256_path(subset_path)
    subset_size = subset_path.stat().st_size
    dataset_id = f"us_equities.fixed_etf_daily.1d.{destination.name}"
    manifest = {
        "schema_version": 1,
        "kind": "fixed_instrument_adjusted_daily_subset",
        "dataset_id": dataset_id,
        "dataset_hash": subset_hash,
        "constructed_at_utc": constructed_at.isoformat(),
        "immutable_snapshot": True,
        "symbols": list(FIXED_ETF_DAILY_SYMBOLS),
        "symbol_order": list(FIXED_ETF_DAILY_SYMBOLS),
        "row_count": len(ordered_rows),
        "per_symbol_counts": counts,
        "date_ranges": date_ranges,
        "source": {
            "path": str(source),
            "size_bytes": source.stat().st_size,
            "sha256": scan["source_hash"],
            "schema": scan["source_schema"],
            "rows_scanned": scan["source_rows_scanned"],
        },
        "subset": {
            "path": str(subset_path),
            "size_bytes": subset_size,
            "sha256": subset_hash,
            "schema": list(R1_SUBSET_COLUMNS),
            "format": "csv.gz",
            "ordering": "symbol_order_then_date_ascending",
        },
        "quality_counts": {
            "selected_rows_seen": scan["selected_rows_seen"],
            "rows_written": len(ordered_rows),
            "duplicate_symbol_date": 0,
            "critical_null_rows": 0,
            "invalid_date_rows": 0,
            "invalid_ohlcv_rows": 0,
            "non_monotonic_output": 0,
        },
        "adjustment_policy": {
            "id": ADJUSTMENT_POLICY_ID,
            "factor_formula": "adjustment_factor = raw_adj_close / raw_close",
            "price_formula": "adjusted_OHLC = raw_OHLC * adjustment_factor",
            "close_formula": "adjusted_close = raw_adj_close",
            "volume_formula": "output_volume = raw_volume (unchanged)",
            "decimal_policy": (
                "28 significant digits, ROUND_HALF_EVEN; high/low containment "
                "residue up to 1e-24 is normalized outward"
            ),
            "limitations": [
                "Yahoo adj_close may combine split and dividend effects.",
                (
                    "The available fields do not identify a split-only factor, "
                    "so volume is not split-adjusted."
                ),
                "Adjusted prices are for development research, not executable historical fills.",
            ],
        },
        "known_gaps": [
            "The source is an unofficial Yahoo acquisition snapshot.",
            "The fixed universe was constructed after the historical observation period.",
            (
                "Historical point-in-time membership, delistings, and "
                "corporate-action lineage are not proven."
            ),
            "No independent sealed holdout was created by this subset operation.",
        ],
        "eligibility": {
            "parser": {
                "eligible": True,
                "reasons": ["schema, hash, ordering, duplicate, null, and OHLCV checks passed"],
            },
            "development_training": {
                "eligible": development_eligible,
                "minimum_sessions_per_instrument": DEVELOPMENT_MIN_SESSIONS,
                "reasons": (
                    ["all fixed instruments meet the ordered-session development floor"]
                    if development_eligible
                    else [f"below {DEVELOPMENT_MIN_SESSIONS} sessions: {', '.join(below_floor)}"]
                ),
            },
            "ranking": {
                "eligible": False,
                "reasons": [
                    "construction postdates the observation period",
                    "historical PIT membership and independent evidence are not proven",
                ],
            },
            "sealed_holdout": {
                "eligible": False,
                "reasons": [
                    "construction postdates the observation period",
                    "no independent sealed evidence exists",
                ],
            },
        },
    }
    manifest_path = destination / "manifest.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest_path


def build_fixed_etf_daily_raw_subset(
    parent_snapshot_dir: Path,
    output_dir: Path,
    *,
    constructed_at_utc: datetime | None = None,
) -> Path:
    """Derive an immutable raw-price campaign subset from verified r1 bytes."""

    parent = Path(parent_snapshot_dir)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"immutable output snapshot already exists: {destination}")
    constructed_at = constructed_at_utc or datetime.now(UTC)
    if constructed_at.tzinfo is None:
        raise ValueError("constructed_at_utc must be timezone-aware")
    constructed_at = constructed_at.astimezone(UTC)

    parent_manifest_path = parent / "manifest.json"
    parent_subset_path = parent / "ohlcv_1d.csv.gz"
    parent_manifest_bytes = parent_manifest_path.read_bytes()
    try:
        parent_manifest = json.loads(parent_manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("parent r1 manifest is not valid UTF-8 JSON") from exc
    if not isinstance(parent_manifest, dict):
        raise ValueError("parent r1 manifest must be a JSON object")

    parent_expected_hash = str(parent_manifest.get("dataset_hash") or "")
    _validate_sha256(parent_expected_hash, "parent r1 dataset_hash")
    parent_subset_manifest = parent_manifest.get("subset")
    if not isinstance(parent_subset_manifest, dict):
        raise ValueError("parent r1 manifest is missing subset evidence")
    if parent_subset_manifest.get("sha256") != parent_expected_hash:
        raise ValueError("parent r1 manifest contains inconsistent subset hashes")
    source_manifest = parent_manifest.get("source")
    if not isinstance(source_manifest, dict):
        raise ValueError("parent r1 manifest is missing original source evidence")
    original_source_hash = str(source_manifest.get("sha256") or "")
    _validate_sha256(original_source_hash, "original source sha256")

    parent_subset_bytes = parent_subset_path.read_bytes()
    parent_actual_hash = _sha256_bytes(parent_subset_bytes)
    if parent_actual_hash != parent_expected_hash:
        raise ValueError(
            "parent r1 hash mismatch: "
            f"expected {parent_expected_hash}, observed {parent_actual_hash}"
        )
    ordered_rows, evidence = _derive_raw_r2_rows(parent_subset_bytes)
    counts = evidence["per_symbol_counts"]
    below_floor = [
        symbol
        for symbol in FIXED_ETF_DAILY_SYMBOLS
        if counts[symbol] < DEVELOPMENT_MIN_SESSIONS
    ]
    development_eligible = not below_floor

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=False)
    subset_path = destination / "ohlcv_1d.csv.gz"
    _write_deterministic_gzip(subset_path, ordered_rows, columns=R2_SUBSET_COLUMNS)
    subset_hash = _sha256_path(subset_path)
    dataset_id = f"us_equities.fixed_etf_daily.1d.{destination.name}"
    diagnostic_columns = [
        "diagnostic_adjusted_open",
        "diagnostic_adjusted_high",
        "diagnostic_adjusted_low",
        "diagnostic_adj_close",
        "diagnostic_adjustment_factor",
        "factor_change",
    ]
    manifest = {
        "schema_version": 2,
        "kind": _R2_DATASET_KIND,
        "dataset_id": dataset_id,
        "dataset_hash": subset_hash,
        "constructed_at_utc": constructed_at.isoformat(),
        "immutable_snapshot": True,
        "symbols": list(FIXED_ETF_DAILY_SYMBOLS),
        "symbol_order": list(FIXED_ETF_DAILY_SYMBOLS),
        "row_count": len(ordered_rows),
        "per_symbol_counts": counts,
        "date_ranges": evidence["date_ranges"],
        "lineage": {
            "parent_r1": {
                "dataset_id": parent_manifest.get("dataset_id"),
                "dataset_hash": parent_actual_hash,
                "manifest_sha256": _sha256_bytes(parent_manifest_bytes),
                "manifest_path": str(parent_manifest_path),
                "subset_path": str(parent_subset_path),
            },
            "original_source": {
                "path": source_manifest.get("path"),
                "sha256": original_source_hash,
            },
        },
        "subset": {
            "path": str(subset_path),
            "size_bytes": subset_path.stat().st_size,
            "sha256": subset_hash,
            "schema": list(R2_SUBSET_COLUMNS),
            "format": "csv.gz",
            "ordering": "symbol_order_then_date_ascending",
        },
        "supersedes": {
            "dataset_id": parent_manifest.get("dataset_id"),
            "for_campaign_use": True,
            "reason": "r1 canonical prices were adjusted and are not executable",
        },
        "raw_execution_policy": {
            "id": RAW_EXECUTION_POLICY_ID,
            "canonical_price_fields": (
                "open/high/low/close are copied from r1 raw_open/raw_high/"
                "raw_low/raw_close"
            ),
            "volume": "volume is raw and unchanged",
            "diagnostic_columns": diagnostic_columns,
            "diagnostics_are_non_executable": True,
            "excluded_from_campaign": [
                "features",
                "labels",
                "fills",
                "thresholds",
                "metrics",
            ],
        },
        "factor_change_diagnostic": {
            "formula": "abs(current_factor / previous_factor - 1)",
            "threshold_relative": str(FACTOR_CHANGE_RELATIVE_THRESHOLD),
            "threshold_basis_points": 1,
            "comparison": ">=",
            "adjacency": "adjacent observed sessions within each symbol",
            "flagged_date": "current session date",
            "first_observed_session_flagged": False,
            "csv_encoding": "1 means material factor change; 0 means no change",
            "per_symbol": {
                symbol: {
                    "count": len(evidence["factor_change_dates"][symbol]),
                    "dates": evidence["factor_change_dates"][symbol],
                }
                for symbol in FIXED_ETF_DAILY_SYMBOLS
            },
            "research_exclusion": (
                "exclude every lookback, signal, entry, exit, feature, label, "
                "fill, threshold, and metric sample touching a flagged date"
            ),
        },
        "quality_counts": {
            "parent_rows_read": len(ordered_rows),
            "rows_written": len(ordered_rows),
            "duplicate_symbol_date": 0,
            "critical_null_rows": 0,
            "invalid_date_rows": 0,
            "invalid_raw_ohlcv_rows": 0,
            "non_monotonic_output": 0,
        },
        "claude_limitation": [
            (
                "Adjusted diagnostics are non-executable and must not enter "
                "campaign features, labels, fills, thresholds, or metrics."
            ),
            (
                "Factor-change flags are exclusion diagnostics, not authoritative "
                "corporate-action or dividend lineage."
            ),
        ],
        "known_gaps": [
            "The original source is an unofficial Yahoo acquisition snapshot.",
            "The fixed universe was constructed after the historical observation period.",
            (
                "Historical point-in-time membership, delistings, and "
                "corporate-action lineage are not proven."
            ),
            "No independent sealed holdout was created by this subset operation.",
        ],
        "eligibility": {
            "parser": {
                "eligible": True,
                "reasons": [
                    "parent hash, schema, ordering, duplicate, null, and raw OHLCV checks passed"
                ],
            },
            "development_training": {
                "eligible": development_eligible,
                "minimum_sessions_per_instrument": DEVELOPMENT_MIN_SESSIONS,
                "reasons": (
                    ["all fixed instruments meet the ordered-session development floor"]
                    if development_eligible
                    else [
                        f"below {DEVELOPMENT_MIN_SESSIONS} sessions: "
                        f"{', '.join(below_floor)}"
                    ]
                ),
            },
            "ranking": {
                "eligible": False,
                "reasons": [
                    "construction postdates the observation period",
                    "historical PIT membership and independent evidence are not proven",
                ],
            },
            "sealed_holdout": {
                "eligible": False,
                "reasons": [
                    "construction postdates the observation period",
                    "no independent sealed evidence exists",
                ],
            },
        },
    }
    manifest_path = destination / "manifest.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest_path


def load_cataloged_yahoo_daily_1d_bars(
    path: Path,
    *,
    dataset_id: str,
    expected_dataset_hash: str,
    symbol: str,
    market: str = "US",
    max_bars: int | None = None,
) -> CatalogedBars:
    """Load one fixed ETF's hash-bound daily bars strictly from local bytes."""

    if not dataset_id.strip():
        raise ValueError("dataset_id is required")
    _validate_sha256(expected_dataset_hash, "expected_dataset_hash")
    requested_symbol = symbol.strip().upper()
    if requested_symbol not in FIXED_ETF_DAILY_SYMBOLS:
        raise ValueError("symbol must be one of SPY, QQQ, IWM")
    resolved_market = market.strip().upper()
    if not resolved_market:
        raise ValueError("market is required")
    if max_bars is not None and max_bars <= 0:
        raise ValueError("max_bars must be positive when supplied")

    source_path, actual_hash, rows = _load_verified_r2_rows(
        path,
        expected_dataset_hash=expected_dataset_hash,
        expected_dataset_id=dataset_id,
    )
    bars: list[Bar] = []
    for row in rows:
        row_symbol = str(row["symbol"]).strip().upper()
        if row_symbol != requested_symbol:
            if bars:
                break
            continue
        start_ts = datetime.combine(date.fromisoformat(row["date"]), time(), tzinfo=UTC)
        open_price = _finite_decimal(row["open"], f"{row_symbol} open")
        high_price = _finite_decimal(row["high"], f"{row_symbol} high")
        low_price = _finite_decimal(row["low"], f"{row_symbol} low")
        close_price = _finite_decimal(row["close"], f"{row_symbol} close")
        volume = _finite_decimal(row["volume"], f"{row_symbol} volume")
        _validate_raw_ohlcv(
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            label=f"{row_symbol} {row['date']}",
        )
        bar = Bar(
            symbol=row_symbol,
            market=resolved_market,
            timeframe=Timeframe.D1,
            start_ts=start_ts,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
            complete=True,
        )
        if bars and bar.start_ts <= bars[-1].start_ts:
            raise ValueError("daily subset bars must be strictly chronological")
        bars.append(bar)
        if max_bars is not None and len(bars) >= max_bars:
            break
    if not bars:
        raise ValueError(f"no bars loaded for fixed symbol {requested_symbol}")
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
        dataset_hash=actual_hash,
        source_path=source_path,
        bars=tuple(bars),
    )


_DEVELOPMENT_FEATURE_ACCESSOR_CALLER = (
    "thericher_v2.research.development_daily_features"
)


def load_broad_daily_development_universe() -> DevelopmentDailyUniverse:
    """Load the one predeclared Yahoo snapshot for retrospective development only.

    The ref deliberately cannot be configured by callers. It exposes only
    stream summaries, not campaign-ready bars, and is not a historical universe
    claim.
    """

    universe, _ = _load_broad_daily_development_universe_data()
    return universe


def _reverify_broad_daily_development_feature_input(
    universe: DevelopmentDailyUniverse,
) -> tuple[tuple[Bar, ...], ...]:
    """Return re-attested bars only to the bounded feature materializer."""

    caller_module = sys._getframe(1).f_globals.get("__name__")
    if caller_module != _DEVELOPMENT_FEATURE_ACCESSOR_CALLER:
        raise PermissionError("development feature input is restricted to its materializer")
    if not isinstance(universe, DevelopmentDailyUniverse):
        raise TypeError("development feature input requires DevelopmentDailyUniverse")
    reattested_universe, streams = _load_broad_daily_development_universe_data()
    if reattested_universe != universe:
        raise ValueError("development feature input does not match re-attested source")
    if any(not bar.complete for stream in streams for bar in stream):
        raise ValueError("development feature input requires completed bars")
    return streams


def _load_broad_daily_development_universe_data(
) -> tuple[DevelopmentDailyUniverse, tuple[tuple[Bar, ...], ...]]:
    """Re-attest and parse the fixed source without exposing its raw bars publicly."""

    caller_module = sys._getframe(1).f_globals.get("__name__")
    if caller_module != __name__:
        raise PermissionError(
            "broad daily raw input is restricted to Data-owned loaders"
        )
    reference = BROAD_DAILY_DEVELOPMENT_UNIVERSE
    _validate_broad_daily_development_reference(reference)
    source_path = reference.snapshot_path
    try:
        snapshot_bytes = source_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("broad daily development snapshot is missing") from exc
    actual_dataset_hash = _sha256_bytes(snapshot_bytes)
    if actual_dataset_hash != reference.dataset_hash:
        raise ValueError(
            "broad daily development snapshot hash mismatch: "
            f"expected {reference.dataset_hash}, observed {actual_dataset_hash}"
        )

    try:
        manifest_bytes = reference.manifest_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("broad daily development manifest is missing") from exc
    actual_manifest_hash = _sha256_bytes(manifest_bytes)
    if actual_manifest_hash != reference.manifest_hash:
        raise ValueError("broad daily development manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("broad daily development manifest must be valid UTF-8 JSON") from exc
    _validate_broad_daily_development_manifest(
        manifest,
        reference=reference,
        snapshot_size=len(snapshot_bytes),
    )

    bars_by_symbol: dict[str, list[Bar]] = {
        symbol: [] for symbol in reference.symbols
    }
    first_observed_sessions: dict[str, date] = {}
    seen_symbol_dates: set[tuple[str, date]] = set()
    try:
        with gzip.open(
            io.BytesIO(snapshot_bytes),
            "rt",
            encoding="utf-8",
            newline="",
        ) as handle:
            reader = csv.DictReader(handle)
            schema = tuple(reader.fieldnames or ())
            missing_columns = [
                column for column in SOURCE_REQUIRED_COLUMNS if column not in schema
            ]
            if missing_columns:
                raise ValueError(
                    "broad daily development source schema missing columns: "
                    f"{', '.join(missing_columns)}"
                )
            for row in reader:
                symbol = str(row.get("symbol") or "").strip().upper()
                if symbol not in bars_by_symbol:
                    continue
                if str(row.get("source") or "").strip() != reference.source_name:
                    raise ValueError(
                        "broad daily development source provenance is inconsistent "
                        f"for {symbol}"
                    )
                date_text = str(row.get("date") or "").strip()
                try:
                    session = date.fromisoformat(date_text)
                except ValueError as exc:
                    raise ValueError(
                        f"invalid broad daily development date for {symbol}: {date_text}"
                    ) from exc
                first_observed = first_observed_sessions.get(symbol)
                if first_observed is None or session < first_observed:
                    first_observed_sessions[symbol] = session
                if session < reference.common_session_start:
                    continue
                key = (symbol, session)
                if key in seen_symbol_dates:
                    raise ValueError(
                        "duplicate broad daily development row: "
                        f"{symbol} {session.isoformat()}"
                    )
                seen_symbol_dates.add(key)
                open_price = _finite_decimal(
                    str(row.get("open") or ""), f"{symbol} {session} open"
                )
                high_price = _finite_decimal(
                    str(row.get("high") or ""), f"{symbol} {session} high"
                )
                low_price = _finite_decimal(
                    str(row.get("low") or ""), f"{symbol} {session} low"
                )
                close_price = _finite_decimal(
                    str(row.get("close") or ""), f"{symbol} {session} close"
                )
                volume = _finite_decimal(
                    str(row.get("volume") or ""), f"{symbol} {session} volume"
                )
                _validate_raw_ohlcv(
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                    label=f"{symbol} {session}",
                )
                bar = Bar(
                    symbol=symbol,
                    market="US",
                    timeframe=Timeframe.D1,
                    start_ts=datetime.combine(session, time(), tzinfo=UTC),
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    complete=True,
                )
                stream = bars_by_symbol[symbol]
                if stream and bar.start_ts <= stream[-1].start_ts:
                    raise ValueError(
                        "broad daily development rows must be strictly chronological "
                        f"for {symbol}"
                    )
                stream.append(bar)
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("broad daily development snapshot is not valid gzip CSV") from exc

    missing_symbols = [symbol for symbol, bars in bars_by_symbol.items() if not bars]
    if missing_symbols:
        raise ValueError(
            "broad daily development snapshot is missing fixed symbols: "
            f"{', '.join(missing_symbols)}"
        )
    observed_inception_bound = max(first_observed_sessions.values())
    if observed_inception_bound != reference.common_session_start:
        raise ValueError(
            "broad daily development common_session_start must equal the latest "
            "fixed-symbol inception"
        )
    if any(
        bars_by_symbol[symbol][0].start_ts.date() != reference.common_session_start
        for symbol in reference.symbols
    ):
        raise ValueError(
            "broad daily development symbols must begin at common_session_start"
        )
    expected_sessions = tuple(
        bar.start_ts for bar in bars_by_symbol[reference.symbols[0]]
    )
    for symbol in reference.symbols[1:]:
        observed_sessions = tuple(bar.start_ts for bar in bars_by_symbol[symbol])
        if observed_sessions != expected_sessions:
            raise ValueError(
                "broad daily development symbols must share identical sessions"
            )
    universe = DevelopmentDailyUniverse(
        reference=reference,
        streams=tuple(
            DevelopmentDailyStream(
                symbol=symbol,
                dataset_id=reference.dataset_id,
                dataset_hash=actual_dataset_hash,
                source_path=source_path,
                session_count=len(bars_by_symbol[symbol]),
                first_start_ts=bars_by_symbol[symbol][0].start_ts,
                last_start_ts=bars_by_symbol[symbol][-1].start_ts,
            )
            for symbol in reference.symbols
        ),
    )
    return universe, tuple(tuple(bars_by_symbol[symbol]) for symbol in reference.symbols)


def load_fixed_etf_daily_factor_change_dates(
    path: Path,
    *,
    expected_dataset_hash: str,
    symbol: str,
) -> tuple[date, ...]:
    """Return verified r2 factor-change dates without loading adjusted prices."""

    requested_symbol = symbol.strip().upper()
    if requested_symbol not in FIXED_ETF_DAILY_SYMBOLS:
        raise ValueError("symbol must be one of SPY, QQQ, IWM")
    _, _, rows = _load_verified_r2_rows(
        path,
        expected_dataset_hash=expected_dataset_hash,
    )
    flagged_dates: list[date] = []
    for row in rows:
        row_symbol = str(row["symbol"]).strip().upper()
        if row_symbol != requested_symbol:
            if flagged_dates:
                break
            continue
        flag = row["factor_change"]
        if flag not in {"0", "1"}:
            raise ValueError(f"invalid factor_change flag for {row_symbol} {row['date']}")
        if flag == "1":
            flagged_dates.append(date.fromisoformat(row["date"]))
    return tuple(flagged_dates)


def _validate_broad_daily_development_reference(
    reference: DevelopmentDailyUniverseRef,
) -> None:
    _validate_sha256(reference.dataset_hash, "development dataset_hash")
    _validate_sha256(reference.manifest_hash, "development manifest_hash")
    if not reference.snapshot:
        raise ValueError("development snapshot is required")
    expected_snapshot_dir = f"snapshot={reference.snapshot}"
    expected_dataset_id = (
        "us_equities.yahoo_daily_universe.1d." + expected_snapshot_dir
    )
    if reference.dataset_id != expected_dataset_id:
        raise ValueError("development dataset_id is inconsistent with its snapshot")
    if reference.symbols != FIXED_ETF_DAILY_SYMBOLS:
        raise ValueError("development universe symbols must be exactly SPY, QQQ, IWM")
    if not reference.snapshot_created_at_utc:
        raise ValueError("development snapshot_created_at_utc is required")
    if not isinstance(reference.common_session_start, date):
        raise ValueError("development common_session_start must be a date")
    if reference.source_name != "yahoo_chart_unofficial":
        raise ValueError("development source must remain yahoo_chart_unofficial")
    snapshot_tail = (
        "canonical",
        "ohlcv_daily",
        expected_snapshot_dir,
        "ohlcv_daily.csv.gz",
    )
    if _path_tail(reference.snapshot_path, len(snapshot_tail)) != snapshot_tail:
        raise ValueError("development snapshot path is inconsistent with its snapshot")
    manifest_tail = (
        "manifests",
        f"yahoo_daily_universe_snapshot={reference.snapshot}.json",
    )
    if _path_tail(reference.manifest_path, len(manifest_tail)) != manifest_tail:
        raise ValueError("development manifest path is inconsistent with its snapshot")
    if not reference.retrospective_development_replay_only:
        raise ValueError("development reference must remain retrospective-only")
    if not (
        reference.development_ref_universe_is_inception_truncated_and_survivor_selected
    ):
        raise ValueError(
            "development reference must retain inception and survivor limitations"
        )
    if reference.point_in_time_eligible:
        raise ValueError("development reference must remain point-in-time ineligible")
    if reference.survivorship_bias_risk != "present":
        raise ValueError("development reference must retain survivorship risk")
    if reference.delisting_coverage != "unproven":
        raise ValueError("development reference must retain unproven delisting coverage")
    if reference.corporate_action_policy != "raw_ohlcv_unadjusted_unverified":
        raise ValueError("development reference must retain raw corporate-action limits")


def _validate_broad_daily_development_manifest(
    manifest: Any,
    *,
    reference: DevelopmentDailyUniverseRef,
    snapshot_size: int,
) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("broad daily development manifest must be an object")
    if manifest.get("dataset") != "yahoo_daily_universe":
        raise ValueError("broad daily development manifest dataset is inconsistent")
    if manifest.get("schema_version") != 1:
        raise ValueError("broad daily development manifest schema is unsupported")
    if manifest.get("snapshot") != reference.snapshot:
        raise ValueError("broad daily development manifest snapshot is inconsistent")
    if manifest.get("created_at_utc") != reference.snapshot_created_at_utc:
        raise ValueError("broad daily development manifest vintage is inconsistent")
    if manifest.get("publish_status") != "published":
        raise ValueError("broad daily development manifest is not published")
    if manifest.get("partial_status") != "complete":
        raise ValueError("broad daily development manifest is not complete")
    request = manifest.get("request")
    if not isinstance(request, dict) or request.get("interval") != "1d":
        raise ValueError("broad daily development manifest interval is inconsistent")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("broad daily development manifest files are required")
    expected_tail = (
        "canonical",
        "ohlcv_daily",
        f"snapshot={reference.snapshot}",
        "ohlcv_daily.csv.gz",
    )
    matching_files = [
        entry
        for entry in files
        if isinstance(entry, dict)
        and _path_tail(str(entry.get("path") or ""), len(expected_tail))
        == expected_tail
    ]
    if len(matching_files) != 1:
        raise ValueError("broad daily development manifest has no unique snapshot file")
    file_entry = matching_files[0]
    manifest_dataset_hash = "sha256:" + str(file_entry.get("sha256") or "")
    _validate_sha256(manifest_dataset_hash, "development manifest dataset sha256")
    if manifest_dataset_hash != reference.dataset_hash:
        raise ValueError("broad daily development manifest dataset hash is inconsistent")
    manifest_size = file_entry.get("bytes")
    if not isinstance(manifest_size, int) or manifest_size != snapshot_size:
        raise ValueError("broad daily development manifest size is inconsistent")


def _path_tail(path: Path | str, count: int) -> tuple[str, ...]:
    parts = PurePosixPath(str(path).replace("\\", "/")).parts
    return tuple(parts[-count:])


def _validate_sibling_r2_manifest(
    subset_path: Path,
    *,
    expected_dataset_hash: str,
    expected_dataset_id: str | None,
) -> None:
    manifest_path = subset_path.parent / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("daily r2 sibling manifest is required") from exc
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("daily r2 sibling manifest must be valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("daily r2 sibling manifest must be a JSON object")
    if manifest.get("schema_version") != 2 or manifest.get("kind") != _R2_DATASET_KIND:
        raise ValueError("daily sibling manifest is not the required r2 dataset kind")

    manifest_dataset_id = str(manifest.get("dataset_id") or "")
    path_dataset_id = f"us_equities.fixed_etf_daily.1d.{subset_path.parent.name}"
    if manifest_dataset_id != path_dataset_id:
        raise ValueError("daily r2 manifest dataset_id is inconsistent with its snapshot path")
    if expected_dataset_id is not None and manifest_dataset_id != expected_dataset_id:
        raise ValueError(
            "dataset_id mismatch: "
            f"expected {manifest_dataset_id}, observed caller value {expected_dataset_id}"
        )

    manifest_dataset_hash = str(manifest.get("dataset_hash") or "")
    _validate_sha256(manifest_dataset_hash, "manifest dataset_hash")
    subset = manifest.get("subset")
    if not isinstance(subset, dict):
        raise ValueError("daily r2 manifest is missing subset evidence")
    subset_hash = str(subset.get("sha256") or "")
    _validate_sha256(subset_hash, "manifest subset sha256")
    if manifest_dataset_hash != expected_dataset_hash or subset_hash != expected_dataset_hash:
        raise ValueError("daily r2 manifest hashes do not match the actual subset bytes")
    manifest_subset_path = str(subset.get("path") or "")
    if subset_path.name != "ohlcv_1d.csv.gz":
        raise ValueError("daily r2 subset must use the expected file basename")
    provenance_parts = PurePosixPath(manifest_subset_path.replace("\\", "/")).parts
    expected_tail = (subset_path.parent.name, subset_path.name)
    if len(provenance_parts) < 2 or tuple(provenance_parts[-2:]) != expected_tail:
        raise ValueError("daily r2 manifest subset path tail is inconsistent")

    lineage = manifest.get("lineage")
    if not isinstance(lineage, dict):
        raise ValueError("daily r2 manifest is missing hash lineage")
    parent_r1 = lineage.get("parent_r1")
    original_source = lineage.get("original_source")
    if not isinstance(parent_r1, dict) or not isinstance(original_source, dict):
        raise ValueError("daily r2 manifest has incomplete hash lineage")
    parent_dataset_id = str(parent_r1.get("dataset_id") or "")
    if not parent_dataset_id:
        raise ValueError("daily r2 parent dataset_id is required")
    _validate_sha256(str(parent_r1.get("dataset_hash") or ""), "parent r1 dataset_hash")
    _validate_sha256(
        str(parent_r1.get("manifest_sha256") or ""),
        "parent r1 manifest_sha256",
    )
    _validate_sha256(
        str(original_source.get("sha256") or ""),
        "original source sha256",
    )
    supersedes = manifest.get("supersedes")
    if (
        not isinstance(supersedes, dict)
        or supersedes.get("dataset_id") != parent_dataset_id
        or supersedes.get("for_campaign_use") is not True
    ):
        raise ValueError("daily r2 supersession lineage is inconsistent")


def _load_verified_r2_rows(
    path: Path,
    *,
    expected_dataset_hash: str,
    expected_dataset_id: str | None = None,
) -> tuple[Path, str, list[dict[str, str]]]:
    _validate_sha256(expected_dataset_hash, "expected_dataset_hash")
    source_path = Path(path)
    compressed_bytes = source_path.read_bytes()
    actual_hash = _sha256_bytes(compressed_bytes)
    if actual_hash != expected_dataset_hash:
        raise ValueError(
            f"dataset hash mismatch: expected {expected_dataset_hash}, observed {actual_hash}"
        )
    _validate_sibling_r2_manifest(
        source_path,
        expected_dataset_hash=actual_hash,
        expected_dataset_id=expected_dataset_id,
    )
    with gzip.open(
        io.BytesIO(compressed_bytes),
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != R2_SUBSET_COLUMNS:
            raise ValueError("daily r2 subset schema mismatch")
        rows = list(reader)
    return source_path, actual_hash, rows


def _derive_raw_r2_rows(
    parent_subset_bytes: bytes,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    ordered_rows: list[dict[str, str]] = []
    counts = {symbol: 0 for symbol in FIXED_ETF_DAILY_SYMBOLS}
    factor_change_dates: dict[str, list[str]] = {
        symbol: [] for symbol in FIXED_ETF_DAILY_SYMBOLS
    }
    first_dates: dict[str, date] = {}
    last_dates: dict[str, date] = {}
    previous_factor: dict[str, Decimal] = {}
    seen: set[tuple[str, date]] = set()
    last_symbol_index = 0

    with gzip.open(
        io.BytesIO(parent_subset_bytes),
        "rt",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != R1_SUBSET_COLUMNS:
            raise ValueError("parent r1 subset schema mismatch")
        for row in reader:
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol not in FIXED_ETF_DAILY_SYMBOLS:
                raise ValueError(f"unexpected symbol in parent r1 subset: {symbol}")
            symbol_index = FIXED_ETF_DAILY_SYMBOLS.index(symbol)
            if symbol_index < last_symbol_index:
                raise ValueError("parent r1 symbols are not in fixed deterministic order")
            last_symbol_index = symbol_index

            raw_date = str(row.get("date") or "").strip()
            try:
                session = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(f"invalid parent r1 date for {symbol}: {raw_date}") from exc
            key = (symbol, session)
            if key in seen:
                raise ValueError(f"duplicate parent r1 row: {symbol} {session}")
            seen.add(key)
            if symbol in last_dates and session <= last_dates[symbol]:
                raise ValueError(f"parent r1 dates are not increasing for {symbol}")

            open_price = _finite_decimal(row["raw_open"], f"{symbol} raw_open")
            high_price = _finite_decimal(row["raw_high"], f"{symbol} raw_high")
            low_price = _finite_decimal(row["raw_low"], f"{symbol} raw_low")
            close_price = _finite_decimal(row["raw_close"], f"{symbol} raw_close")
            volume = _finite_decimal(row["volume"], f"{symbol} volume")
            _validate_raw_ohlcv(
                open_price,
                high_price,
                low_price,
                close_price,
                volume,
                label=f"{symbol} {session}",
            )
            adjusted_open = _finite_decimal(row["open"], f"{symbol} adjusted open")
            adjusted_high = _finite_decimal(row["high"], f"{symbol} adjusted high")
            adjusted_low = _finite_decimal(row["low"], f"{symbol} adjusted low")
            adjusted_close = _finite_decimal(row["raw_adj_close"], f"{symbol} adj_close")
            factor = _finite_decimal(
                row["adjustment_factor"],
                f"{symbol} adjustment_factor",
            )
            if min(adjusted_open, adjusted_high, adjusted_low, adjusted_close, factor) <= 0:
                raise ValueError(f"invalid non-positive diagnostic for {symbol} {session}")

            material_factor_change = False
            if symbol in previous_factor:
                with localcontext() as context:
                    context.prec = 28
                    context.rounding = ROUND_HALF_EVEN
                    relative_change = abs(factor / previous_factor[symbol] - Decimal("1"))
                material_factor_change = (
                    relative_change >= FACTOR_CHANGE_RELATIVE_THRESHOLD
                )
            if material_factor_change:
                factor_change_dates[symbol].append(session.isoformat())
            previous_factor[symbol] = factor
            first_dates.setdefault(symbol, session)
            last_dates[symbol] = session
            counts[symbol] += 1
            ordered_rows.append(
                {
                    "symbol": symbol,
                    "date": session.isoformat(),
                    "open": _decimal_text(open_price),
                    "high": _decimal_text(high_price),
                    "low": _decimal_text(low_price),
                    "close": _decimal_text(close_price),
                    "volume": _decimal_text(volume),
                    "diagnostic_adjusted_open": _decimal_text(adjusted_open),
                    "diagnostic_adjusted_high": _decimal_text(adjusted_high),
                    "diagnostic_adjusted_low": _decimal_text(adjusted_low),
                    "diagnostic_adj_close": _decimal_text(adjusted_close),
                    "diagnostic_adjustment_factor": _decimal_text(factor),
                    "factor_change": "1" if material_factor_change else "0",
                    "asset_type": str(row.get("asset_type") or "").strip(),
                    "yahoo_symbol": str(row.get("yahoo_symbol") or "").strip(),
                    "source": str(row.get("source") or "").strip(),
                }
            )

    missing_symbols = [symbol for symbol, count in counts.items() if count == 0]
    if missing_symbols:
        raise ValueError(f"parent r1 has no rows for: {', '.join(missing_symbols)}")
    date_ranges = {
        symbol: {
            "min": first_dates[symbol].isoformat(),
            "max": last_dates[symbol].isoformat(),
            "sessions": counts[symbol],
        }
        for symbol in FIXED_ETF_DAILY_SYMBOLS
    }
    return ordered_rows, {
        "per_symbol_counts": counts,
        "date_ranges": date_ranges,
        "factor_change_dates": factor_change_dates,
    }


def _scan_source_once(source: Path) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    rows_by_symbol: dict[str, list[dict[str, str]]] = {
        symbol: [] for symbol in FIXED_ETF_DAILY_SYMBOLS
    }
    seen: set[tuple[str, str]] = set()
    source_rows_scanned = 0
    selected_rows_seen = 0
    digest = hashlib.sha256()
    with source.open("rb") as raw:
        digesting_reader = _DigestingReader(raw, digest)
        with gzip.GzipFile(fileobj=digesting_reader, mode="rb") as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                source_schema = tuple(reader.fieldnames or ())
                missing = [
                    column for column in SOURCE_REQUIRED_COLUMNS if column not in source_schema
                ]
                if missing:
                    raise ValueError(f"source schema missing columns: {', '.join(missing)}")
                for row in reader:
                    source_rows_scanned += 1
                    symbol = str(row.get("symbol") or "").strip().upper()
                    if symbol not in rows_by_symbol:
                        continue
                    selected_rows_seen += 1
                    transformed = _adjust_row(row, symbol=symbol)
                    key = (symbol, transformed["date"])
                    if key in seen:
                        raise ValueError(f"duplicate fixed-instrument row: {symbol} {key[1]}")
                    seen.add(key)
                    rows_by_symbol[symbol].append(transformed)
    return rows_by_symbol, {
        "source_hash": "sha256:" + digest.hexdigest(),
        "source_schema": list(source_schema),
        "source_rows_scanned": source_rows_scanned,
        "selected_rows_seen": selected_rows_seen,
    }


def _adjust_row(row: dict[str | None, str | None], *, symbol: str) -> dict[str, str]:
    critical = ("date", "open", "high", "low", "close", "volume", "adj_close")
    values = {column: str(row.get(column) or "").strip() for column in critical}
    missing = [column for column, value in values.items() if not value]
    if missing:
        raise ValueError(f"critical null for {symbol}: {', '.join(missing)}")
    try:
        parsed_date = date.fromisoformat(values["date"])
    except ValueError as exc:
        raise ValueError(f"invalid date for {symbol}: {values['date']}") from exc
    numbers = {
        column: _finite_decimal(values[column], f"{symbol} {parsed_date} {column}")
        for column in ("open", "high", "low", "close", "volume", "adj_close")
    }
    prices = [numbers[column] for column in ("open", "high", "low", "close")]
    if any(price <= 0 for price in prices) or numbers["adj_close"] <= 0:
        raise ValueError(f"invalid non-positive price for {symbol} {parsed_date}")
    if numbers["volume"] < 0:
        raise ValueError(f"invalid negative volume for {symbol} {parsed_date}")
    if numbers["high"] < max(prices) or numbers["low"] > min(prices):
        raise ValueError(f"invalid OHLC range for {symbol} {parsed_date}")
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        factor = numbers["adj_close"] / numbers["close"]
        adjusted = {
            column: numbers[column] * factor for column in ("open", "high", "low")
        }
        adjusted["close"] = numbers["adj_close"]
    adjusted["high"], adjusted["low"] = _normalize_adjusted_containment(
        adjusted["open"],
        adjusted["high"],
        adjusted["low"],
        adjusted["close"],
        label=f"{symbol} {parsed_date}",
    )
    return {
        "symbol": symbol,
        "date": parsed_date.isoformat(),
        "open": _decimal_text(adjusted["open"]),
        "high": _decimal_text(adjusted["high"]),
        "low": _decimal_text(adjusted["low"]),
        "close": _decimal_text(adjusted["close"]),
        "volume": _decimal_text(numbers["volume"]),
        "adjustment_factor": _decimal_text(factor),
        "raw_open": _decimal_text(numbers["open"]),
        "raw_high": _decimal_text(numbers["high"]),
        "raw_low": _decimal_text(numbers["low"]),
        "raw_close": _decimal_text(numbers["close"]),
        "raw_adj_close": _decimal_text(numbers["adj_close"]),
        "asset_type": str(row.get("asset_type") or "").strip(),
        "yahoo_symbol": str(row.get("yahoo_symbol") or "").strip(),
        "source": str(row.get("source") or "").strip(),
    }


def _write_deterministic_gzip(
    path: Path,
    rows: list[dict[str, str]],
    *,
    columns: tuple[str, ...] = R1_SUBSET_COLUMNS,
) -> None:
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def _finite_decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value for {label}") from exc
    if not parsed.is_finite():
        raise ValueError(f"invalid non-finite value for {label}")
    return parsed


def _validate_raw_ohlcv(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: Decimal,
    *,
    label: str,
) -> None:
    prices = (open_price, high_price, low_price, close_price)
    if any(price <= 0 for price in prices):
        raise ValueError(f"invalid non-positive raw price for {label}")
    if volume < 0:
        raise ValueError(f"invalid negative raw volume for {label}")
    if high_price < max(prices) or low_price > min(prices):
        raise ValueError(f"invalid raw OHLC range for {label}")


def _normalize_adjusted_containment(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    *,
    label: str,
) -> tuple[Decimal, Decimal]:
    high_floor = max(open_price, close_price)
    low_ceiling = min(open_price, close_price)
    high_deficit = max(high_floor - high_price, Decimal("0"))
    low_excess = max(low_price - low_ceiling, Decimal("0"))
    if high_deficit > _ADJUSTED_CONTAINMENT_TOLERANCE:
        raise ValueError(f"invalid adjusted high containment for {label}")
    if low_excess > _ADJUSTED_CONTAINMENT_TOLERANCE:
        raise ValueError(f"invalid adjusted low containment for {label}")
    return max(high_price, high_floor), min(low_price, low_ceiling)


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class _DigestingReader:
    def __init__(self, source: BinaryIO, digest: Any) -> None:
        self._source = source
        self._digest = digest
        self.name = getattr(source, "name", "")

    def read(self, size: int = -1) -> bytes:
        data = self._source.read(size)
        self._digest.update(data)
        return data

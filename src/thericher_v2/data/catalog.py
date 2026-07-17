"""Bounded, machine-readable training-readiness catalog for local OHLCV files."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO

CATALOG_SCHEMA_VERSION = 1
DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_MODEL_ARTIFACT_ROOT = Path("D:/thericher-v2/model-artifacts")
DEFAULT_DAILY_ROOT = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "yahoo_daily_universe"
    / "canonical"
    / "ohlcv_daily"
)
DEFAULT_INTRADAY_PATHS = (
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "yahoo_intraday_starter"
    / "canonical"
    / "ohlcv_1m"
    / "snapshot=2026-06-18"
    / "ohlcv_1m.csv.gz",
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "yahoo_intraday_starter"
    / "canonical"
    / "ohlcv_1m"
    / "snapshot=2026-07-09-shadow-t0"
    / "ohlcv_1m.csv.gz",
    DEFAULT_MARKET_DATA_ROOT
    / "us_equities"
    / "yahoo_intraday_starter"
    / "canonical"
    / "ohlcv_1m"
    / "snapshot=2026-07-09-shadow-t0-8d-probe"
    / "ohlcv_1m.csv.gz",
)

_CRITICAL_BASE_COLUMNS = ("symbol", "open", "high", "low", "close", "volume")
_PRICE_COLUMNS = ("open", "high", "low", "close")
_TIMEFRAME_SECONDS = {"1m": 60, "5m": 300, "10m": 600, "1h": 3600, "3h": 10800, "1d": 86400}
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SNAPSHOT_DATE_PATTERN = re.compile(r"snapshot=(\d{4}-\d{2}-\d{2})")
_MAX_GAP_EXAMPLES = 10
_SCHEMA_INFERENCE_ROW_LIMIT = 10_000


def inspect_ohlcv_file(
    path: Path,
    *,
    timeframe: str,
    proposed_holdout_start: date | None,
    provenance_proves_point_in_time: bool,
    minimum_training_sessions: int,
    known_gaps: Sequence[str] = (),
    sha256: str | None = None,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    """Fully inspect one CSV or CSV.GZ file with bounded summary output."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if timeframe not in _TIMEFRAME_SECONDS:
        raise ValueError(f"unsupported catalog timeframe: {timeframe}")
    if minimum_training_sessions <= 0:
        raise ValueError("minimum_training_sessions must be positive")

    stat = source.stat()
    as_of, as_of_derivation = _derive_as_of_construction_date(source, stat.st_mtime)
    file_sha256 = sha256 or _sha256_file(source)
    resolved_dataset_id = dataset_id or _default_dataset_id(source, timeframe)
    constructed_as_of_utc = datetime.combine(
        as_of,
        datetime.min.time(),
        tzinfo=UTC,
    ).isoformat()
    timestamp_column: str | None = None
    session_column: str | None = None
    columns: tuple[str, ...]
    row_count = 0
    malformed_row_count = 0
    invalid_timestamp_count = 0
    invalid_session_count = 0
    non_monotonic_count = 0
    duplicate_count = 0
    symbol_block_reentry_count = 0
    critical_nulls: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    session_counts: Counter[str] = Counter()
    timestamps: set[str] = set()
    observed_types: dict[str, set[str]] = defaultdict(set)
    last_timestamp_by_symbol: dict[str, datetime] = {}
    last_gap_timestamp: dict[tuple[str, str], datetime] = {}
    delta_seconds_counts: Counter[int] = Counter()
    gap_transition_count = 0
    missing_interval_count = 0
    max_gap_seconds = 0
    gap_examples: list[dict[str, Any]] = []
    ohlcv_failures: Counter[str] = Counter()
    rows_with_ohlcv_failure = 0
    current_symbol: str | None = None
    seen_timestamps_in_block: set[str] = set()
    completed_symbol_blocks: set[str] = set()
    min_timestamp: tuple[datetime, str] | None = None
    max_timestamp: tuple[datetime, str] | None = None
    rows_before_holdout = 0
    rows_on_or_after_holdout = 0

    with _open_csv_text(source) as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        timestamp_column = _choose_column(columns, ("timestamp_utc", "timestamp", "date"))
        session_column = _choose_column(columns, ("session_date", "date"))
        critical_columns = (*_CRITICAL_BASE_COLUMNS, timestamp_column or "timestamp")

        for row in reader:
            row_count += 1
            if None in row:
                malformed_row_count += 1
            if row_count <= _SCHEMA_INFERENCE_ROW_LIMIT:
                for column in columns:
                    value = (row.get(column) or "").strip()
                    if value:
                        observed_types[column].add(_infer_value_type(value))

            for column in critical_columns:
                if not (row.get(column) or "").strip():
                    critical_nulls[column] += 1

            symbol = (row.get("symbol") or "").strip().upper()
            raw_timestamp = (row.get(timestamp_column) or "").strip() if timestamp_column else ""
            if symbol:
                symbol_counts[symbol] += 1
            if symbol and symbol != current_symbol:
                if current_symbol is not None:
                    completed_symbol_blocks.add(current_symbol)
                if symbol in completed_symbol_blocks:
                    symbol_block_reentry_count += 1
                current_symbol = symbol
                seen_timestamps_in_block = set()
            if symbol and raw_timestamp:
                if raw_timestamp in seen_timestamps_in_block:
                    duplicate_count += 1
                else:
                    seen_timestamps_in_block.add(raw_timestamp)

            parsed_timestamp = _parse_timestamp(raw_timestamp)
            if raw_timestamp and parsed_timestamp is None:
                invalid_timestamp_count += 1
            if parsed_timestamp is not None:
                timestamps.add(raw_timestamp)
                point = (parsed_timestamp, raw_timestamp)
                if min_timestamp is None or point[0] < min_timestamp[0]:
                    min_timestamp = point
                if max_timestamp is None or point[0] > max_timestamp[0]:
                    max_timestamp = point
                if proposed_holdout_start is not None:
                    if parsed_timestamp.date() < proposed_holdout_start:
                        rows_before_holdout += 1
                    else:
                        rows_on_or_after_holdout += 1

            raw_session = (row.get(session_column) or "").strip() if session_column else ""
            if not raw_session and parsed_timestamp is not None:
                raw_session = parsed_timestamp.date().isoformat()
            if raw_session:
                try:
                    date.fromisoformat(raw_session)
                except ValueError:
                    invalid_session_count += 1
                else:
                    session_counts[raw_session] += 1

            if symbol and parsed_timestamp is not None:
                prior = last_timestamp_by_symbol.get(symbol)
                if prior is not None and parsed_timestamp < prior:
                    non_monotonic_count += 1
                if prior is None or parsed_timestamp > prior:
                    last_timestamp_by_symbol[symbol] = parsed_timestamp

                stream_session = raw_session if timeframe != "1d" else "all"
                gap_key = (symbol, stream_session)
                prior_gap = last_gap_timestamp.get(gap_key)
                if prior_gap is not None and parsed_timestamp > prior_gap:
                    delta_seconds = int((parsed_timestamp - prior_gap).total_seconds())
                    delta_seconds_counts[delta_seconds] += 1
                    expected_seconds = _TIMEFRAME_SECONDS[timeframe]
                    if delta_seconds > expected_seconds:
                        gap_transition_count += 1
                        max_gap_seconds = max(max_gap_seconds, delta_seconds)
                        missing = max(delta_seconds // expected_seconds - 1, 1)
                        missing_interval_count += missing
                        if len(gap_examples) < _MAX_GAP_EXAMPLES:
                            gap_examples.append(
                                {
                                    "symbol": symbol,
                                    "session": stream_session,
                                    "previous": prior_gap.isoformat(),
                                    "current": parsed_timestamp.isoformat(),
                                    "delta_seconds": delta_seconds,
                                    "missing_intervals": missing,
                                }
                            )
                if prior_gap is None or parsed_timestamp > prior_gap:
                    last_gap_timestamp[gap_key] = parsed_timestamp

            failures = _ohlcv_failures(row)
            if failures:
                rows_with_ohlcv_failure += 1
                ohlcv_failures.update(failures)

    missing_columns = sorted(
        column
        for column in (*_CRITICAL_BASE_COLUMNS, timestamp_column or "timestamp")
        if column not in columns
    )
    duplicate_count_is_exact = symbol_block_reentry_count == 0
    integrity_reasons: list[str] = []
    if missing_columns:
        integrity_reasons.append(f"missing critical columns: {', '.join(missing_columns)}")
    if sum(critical_nulls.values()):
        integrity_reasons.append("critical columns contain null values")
    if invalid_timestamp_count or invalid_session_count:
        integrity_reasons.append("timestamp or session values are invalid")
    if malformed_row_count:
        integrity_reasons.append("malformed CSV rows are present")
    if duplicate_count:
        integrity_reasons.append("duplicate (symbol, timestamp) rows are present")
    if not duplicate_count_is_exact:
        integrity_reasons.append("symbol blocks re-enter, so duplicate count is only a lower bound")
    if non_monotonic_count:
        integrity_reasons.append("per-symbol timestamps are non-monotonic in file order")
    if rows_with_ohlcv_failure:
        integrity_reasons.append("OHLCV invariants fail")
    if len(session_counts) < minimum_training_sessions:
        integrity_reasons.append(
            f"only {len(session_counts)} sessions; "
            f"{minimum_training_sessions} required by this catalog"
        )
    if not provenance_proves_point_in_time:
        integrity_reasons.append("point-in-time universe construction is not proven")

    training_eligible = not integrity_reasons
    holdout_reasons = list(integrity_reasons)
    if proposed_holdout_start is None:
        holdout_reasons.append("no proposed sealed-holdout start was supplied")
    else:
        if as_of > proposed_holdout_start:
            holdout_reasons.append(
                "dataset construction date postdates the proposed sealed-holdout start"
            )
        if rows_before_holdout == 0:
            holdout_reasons.append("no pre-holdout rows are available for training")
        if rows_on_or_after_holdout == 0:
            holdout_reasons.append("no rows fall inside the proposed sealed holdout")
    if not provenance_proves_point_in_time and (
        "point-in-time provenance cannot support a sealed holdout" not in holdout_reasons
    ):
        holdout_reasons.append("point-in-time provenance cannot support a sealed holdout")

    min_session = min(session_counts) if session_counts else None
    max_session = max(session_counts) if session_counts else None
    result_known_gaps = list(dict.fromkeys(known_gaps))
    if timeframe == "1d":
        result_known_gaps.append(
            "daily interval gaps are calendar-day deltas; exchange holidays are not classified"
        )
    return {
        "dataset_id": resolved_dataset_id,
        "dataset_hash": f"sha256:{file_sha256}",
        "constructed_as_of_utc": constructed_as_of_utc,
        "path": str(source),
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        "sha256": file_sha256,
        "format": "csv.gz" if source.suffix.lower() == ".gz" else "csv",
        "timeframe": timeframe,
        "as_of_construction_date": as_of.isoformat(),
        "as_of_construction_date_derivation": as_of_derivation,
        "point_in_time_construction_proven": provenance_proves_point_in_time,
        "schema": {
            "columns": list(columns),
            "inferred_types": {
                column: _merge_inferred_types(observed_types.get(column, set()))
                for column in columns
            },
            "inference_rows": min(row_count, _SCHEMA_INFERENCE_ROW_LIMIT),
        },
        "row_count": row_count,
        "timestamp": {
            "column": timestamp_column,
            "min": min_timestamp[1] if min_timestamp else None,
            "max": max_timestamp[1] if max_timestamp else None,
            "distinct_count": len(timestamps),
            "invalid_count": invalid_timestamp_count,
        },
        "session": {
            "column": session_column,
            "min": min_session,
            "max": max_session,
            "count": len(session_counts),
            "row_counts": dict(sorted(session_counts.items())),
            "invalid_count": invalid_session_count,
        },
        "symbols": sorted(symbol_counts),
        "symbol_count": len(symbol_counts),
        "per_symbol_counts": dict(sorted(symbol_counts.items())),
        "duplicate_symbol_timestamp_count": duplicate_count,
        "duplicate_count_is_exact": duplicate_count_is_exact,
        "symbol_block_reentry_count": symbol_block_reentry_count,
        "non_monotonic_count": non_monotonic_count,
        "critical_nulls": {
            column: critical_nulls[column] for column in critical_columns
        },
        "malformed_row_count": malformed_row_count,
        "ohlcv_invariant_failures": {
            "row_count": rows_with_ohlcv_failure,
            "counts": dict(sorted(ohlcv_failures.items())),
        },
        "interval_gaps": {
            "expected_interval_seconds": _TIMEFRAME_SECONDS[timeframe],
            "gap_transition_count": gap_transition_count,
            "missing_interval_count": missing_interval_count,
            "max_gap_seconds": max_gap_seconds or None,
            "delta_seconds_counts": {
                str(delta): count
                for delta, count in delta_seconds_counts.most_common(12)
            },
            "examples": gap_examples,
            "summary_is_bounded": True,
        },
        "split": {
            "proposed_holdout_start": (
                proposed_holdout_start.isoformat() if proposed_holdout_start else None
            ),
            "rows_before_holdout": rows_before_holdout,
            "rows_on_or_after_holdout": rows_on_or_after_holdout,
            "row_level_split_materialized": False,
        },
        "known_gaps": result_known_gaps,
        "eligibility_scope": "honest_model_selection_campaign",
        "development_smoke_allowed": row_count > 0 and not missing_columns,
        "training_eligible": training_eligible,
        "ranking_eligible": training_eligible,
        "training_eligibility_reasons": (
            ["integrity, coverage, and point-in-time checks passed"]
            if training_eligible
            else integrity_reasons
        ),
        "sealed_holdout_eligible": not holdout_reasons,
        "sealed_holdout_eligibility_reasons": (
            ["construction predates holdout and point-in-time provenance is proven"]
            if not holdout_reasons
            else list(dict.fromkeys(holdout_reasons))
        ),
    }


def build_training_readiness_catalog(
    *,
    intraday_paths: Sequence[Path] = DEFAULT_INTRADAY_PATHS,
    daily_root: Path = DEFAULT_DAILY_ROOT,
    proposed_holdout_start: date | None = date(2026, 7, 1),
    generated_at: datetime | None = None,
    daily_inventory_limit: int = 8,
    daily_sample_limit: int = 1,
) -> dict[str, Any]:
    """Catalog exactly three intraday files plus a bounded daily inventory/sample."""

    if len(intraday_paths) != 3:
        raise ValueError("exactly three intraday files are required")
    if daily_inventory_limit <= 0:
        raise ValueError("daily_inventory_limit must be positive")
    if daily_sample_limit < 0 or daily_sample_limit > daily_inventory_limit:
        raise ValueError("daily_sample_limit must be between zero and inventory limit")

    checked_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
    intraday_gaps = (
        "Yahoo Chart is an unofficial acquisition-time source",
        "snapshot provenance does not prove point-in-time universe membership",
        "coverage is suitable for development smoke, not independent model ranking",
    )
    intraday = [
        inspect_ohlcv_file(
            Path(path),
            timeframe="1m",
            proposed_holdout_start=proposed_holdout_start,
            provenance_proves_point_in_time=False,
            minimum_training_sessions=20,
            known_gaps=intraday_gaps,
            dataset_id=_dataset_id_for_family(
                Path(path),
                family="us_equities.yahoo_intraday_starter",
                timeframe="1m",
            ),
        )
        for path in intraday_paths
    ]

    daily_path = Path(daily_root)
    discovered = sorted(daily_path.glob("snapshot=*/ohlcv_daily.csv.gz"))
    selected_inventory = discovered[-daily_inventory_limit:]
    daily_inventory = [_file_inventory(path) for path in selected_inventory]
    sample_paths = selected_inventory[-daily_sample_limit:] if daily_sample_limit else []
    inventory_by_path = {entry["path"]: entry for entry in daily_inventory}
    daily_gaps = (
        "Yahoo Chart is an unofficial acquisition-time source",
        "universe membership and delistings are not point-in-time proven",
        "OHLC is unadjusted while adj_close alone cannot define a full adjustment policy",
        "corporate actions and exchange-calendar completeness are not independently verified",
    )
    daily_samples = [
        inspect_ohlcv_file(
            path,
            timeframe="1d",
            proposed_holdout_start=proposed_holdout_start,
            provenance_proves_point_in_time=False,
            minimum_training_sessions=252,
            known_gaps=daily_gaps,
            sha256=inventory_by_path[str(path)]["sha256"],
            dataset_id=inventory_by_path[str(path)]["dataset_id"],
        )
        for path in sample_paths
    ]
    sampled_paths = {item["path"] for item in daily_samples}
    for entry in daily_inventory:
        entry["content_inspected"] = entry["path"] in sampled_paths
    inspected = [*intraday, *daily_samples]
    usage = shutil.disk_usage(daily_path.anchor or daily_path)
    catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "kind": "training_readiness_catalog",
        "generated_at": checked_at.isoformat(),
        "boundaries": {
            "network_used": False,
            "credentials_read": False,
            "data_acquired": False,
            "broad_recursive_scan": False,
            "repo_artifacts_allowed": False,
        },
        "storage": {
            "drive": daily_path.anchor,
            "total_bytes": usage.total,
            "free_bytes": usage.free,
            "free_percent": round(100 * usage.free / usage.total, 2),
            "warning_floor_percent": 20,
            "hard_floor_percent": 15,
        },
        "eligibility_scope": "honest_model_selection_campaign_not_parser_smoke",
        "proposed_holdout_start": (
            proposed_holdout_start.isoformat() if proposed_holdout_start else None
        ),
        "intraday_files": intraday,
        "daily_universe": {
            "root": str(daily_path),
            "discovered_file_count": len(discovered),
            "inventory_limit": daily_inventory_limit,
            "inventory_truncated": len(discovered) > len(selected_inventory),
            "inventory": daily_inventory,
            "sample_policy": "newest snapshots by path name; full content scan",
            "sample_limit": daily_sample_limit,
            "samples": daily_samples,
        },
        "overlap_notes": _build_overlap_notes(inspected),
        "split_notes": [
            "No row-level split was written; the catalog only counts proposed split sides.",
            "Acquisition snapshot dates do not prove historical point-in-time universe membership.",
            "Any construction date after the proposed holdout start rejects sealed-holdout use.",
        ],
        "training_eligible_file_count": sum(
            bool(item["training_eligible"]) for item in inspected
        ),
        "sealed_holdout_eligible_file_count": sum(
            bool(item["sealed_holdout_eligible"]) for item in inspected
        ),
    }
    catalog["catalog_id"] = derive_catalog_id(catalog)
    return catalog


def derive_catalog_id(catalog: dict[str, Any]) -> str:
    """Derive a stable catalog identity without runtime or storage volatility."""

    datasets = [
        {
            "dataset_id": entry["dataset_id"],
            "dataset_hash": entry["dataset_hash"],
            "constructed_as_of_utc": entry["constructed_as_of_utc"],
            "timeframe": entry["timeframe"],
            "row_count": entry["row_count"],
            "schema_columns": entry["schema"]["columns"],
            "timestamp": entry["timestamp"],
            "session": entry["session"],
            "split": entry["split"],
            "ranking_eligible": entry["ranking_eligible"],
            "sealed_holdout_eligible": entry["sealed_holdout_eligible"],
            "training_eligibility_reasons": entry["training_eligibility_reasons"],
            "sealed_holdout_eligibility_reasons": entry[
                "sealed_holdout_eligibility_reasons"
            ],
        }
        for entry in _inspected_datasets(catalog)
    ]
    daily_inventory = [
        {
            "dataset_id": entry["dataset_id"],
            "dataset_hash": entry["dataset_hash"],
            "constructed_as_of_utc": entry["constructed_as_of_utc"],
            "size_bytes": entry["size_bytes"],
        }
        for entry in catalog["daily_universe"]["inventory"]
    ]
    stable_inputs = {
        "schema_version": catalog["schema_version"],
        "kind": catalog["kind"],
        "eligibility_scope": catalog["eligibility_scope"],
        "proposed_holdout_start": catalog["proposed_holdout_start"],
        "daily_inventory_limit": catalog["daily_universe"]["inventory_limit"],
        "daily_inventory_truncated": catalog["daily_universe"]["inventory_truncated"],
        "daily_sample_limit": catalog["daily_universe"]["sample_limit"],
        "datasets": sorted(datasets, key=lambda entry: entry["dataset_id"]),
        "daily_inventory": sorted(
            daily_inventory,
            key=lambda entry: entry["dataset_id"],
        ),
    }
    encoded = json.dumps(stable_inputs, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def select_catalog_dataset(catalog: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    """Return one inspected dataset using the Data-owned stable dataset ID."""

    matches = [
        entry for entry in _inspected_datasets(catalog) if entry["dataset_id"] == dataset_id
    ]
    if not matches:
        raise KeyError(f"dataset_id not found in inspected catalog entries: {dataset_id}")
    if len(matches) > 1:
        raise ValueError(f"dataset_id is not unique: {dataset_id}")
    return matches[0]


def write_training_readiness_catalog(
    catalog: dict[str, Any],
    *,
    artifact_root: Path = DEFAULT_MODEL_ARTIFACT_ROOT,
    run_id: str,
    repo_root: Path | None = None,
) -> Path:
    """Write one immutable JSON catalog beneath the external Data artifact root."""

    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id must be non-empty and path-safe")
    run_dir = (
        Path(artifact_root) / "data-agent" / "training-readiness-catalog" / run_id
    ).resolve()
    if repo_root is not None and run_dir.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("training-readiness artifacts must stay outside Git")
    run_dir.mkdir(parents=True, exist_ok=False)
    output = run_dir / "catalog.json"
    output.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _file_inventory(path: Path) -> dict[str, Any]:
    stat = path.stat()
    as_of, derivation = _derive_as_of_construction_date(path, stat.st_mtime)
    file_sha256 = _sha256_file(path)
    return {
        "dataset_id": _dataset_id_for_family(
            path,
            family="us_equities.yahoo_daily_universe",
            timeframe="1d",
        ),
        "dataset_hash": f"sha256:{file_sha256}",
        "constructed_as_of_utc": datetime.combine(
            as_of,
            datetime.min.time(),
            tzinfo=UTC,
        ).isoformat(),
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        "sha256": file_sha256,
        "as_of_construction_date": as_of.isoformat(),
        "as_of_construction_date_derivation": derivation,
        "content_inspected": False,
    }


def _inspected_datasets(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *catalog.get("intraday_files", []),
        *catalog.get("daily_universe", {}).get("samples", []),
    ]


def _default_dataset_id(path: Path, timeframe: str) -> str:
    name = path.name
    for suffix in (".csv.gz", ".csv"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return f"local.{name}.{timeframe}.{path.parent.name}"


def _dataset_id_for_family(path: Path, *, family: str, timeframe: str) -> str:
    return f"{family}.{timeframe}.{path.parent.name}"


def _build_overlap_notes(files: Sequence[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for index, left in enumerate(files):
        for right in files[index + 1 :]:
            if left["timeframe"] != right["timeframe"]:
                continue
            common_symbols = set(left["symbols"]) & set(right["symbols"])
            left_min = left["timestamp"]["min"]
            left_max = left["timestamp"]["max"]
            right_min = right["timestamp"]["min"]
            right_max = right["timestamp"]["max"]
            temporal_overlap = bool(
                left_min
                and left_max
                and right_min
                and right_max
                and max(left_min, right_min) <= min(left_max, right_max)
            )
            if common_symbols and temporal_overlap:
                notes.append(
                    f"{Path(left['path']).parent.name} and {Path(right['path']).parent.name} "
                    f"overlap in {len(common_symbols)} symbol(s) and time; key-level deduplication "
                    "is required before combining them"
                )
    if not notes:
        notes.append("no same-timeframe symbol/time overlap found in inspected files")
    notes.append("daily and intraday files were not treated as interchangeable")
    return notes


def _ohlcv_failures(row: dict[str | None, str | None]) -> tuple[str, ...]:
    values: dict[str, Decimal] = {}
    failures: list[str] = []
    for column in _PRICE_COLUMNS:
        raw = (row.get(column) or "").strip()
        if not raw:
            continue
        try:
            values[column] = Decimal(raw)
        except InvalidOperation:
            failures.append(f"non_numeric_{column}")
    if len(values) == len(_PRICE_COLUMNS):
        if any(value <= 0 for value in values.values()):
            failures.append("non_positive_price")
        if values["high"] < max(values["open"], values["low"], values["close"]):
            failures.append("high_below_ohlc")
        if values["low"] > min(values["open"], values["high"], values["close"]):
            failures.append("low_above_ohlc")
    raw_volume = (row.get("volume") or "").strip()
    if raw_volume:
        try:
            if Decimal(raw_volume) < 0:
                failures.append("negative_volume")
        except InvalidOperation:
            failures.append("non_numeric_volume")
    return tuple(failures)


def _derive_as_of_construction_date(path: Path, mtime: float) -> tuple[date, str]:
    for part in reversed(path.parts):
        match = _SNAPSHOT_DATE_PATTERN.search(part)
        if match:
            return date.fromisoformat(match.group(1)), f"snapshot_partition:{part}"
    return (
        datetime.fromtimestamp(mtime, UTC).date(),
        "file_mtime_utc_fallback_unverified",
    )


def _choose_column(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            parsed_date = date.fromisoformat(value)
            return datetime.combine(parsed_date, datetime.min.time(), tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _infer_value_type(value: str) -> str:
    try:
        int(value)
    except ValueError:
        pass
    else:
        return "integer"
    try:
        Decimal(value)
    except InvalidOperation:
        pass
    else:
        return "number"
    if _parse_timestamp(value) is not None:
        return "date" if len(value) == 10 else "datetime"
    return "string"


def _merge_inferred_types(types: set[str]) -> str:
    if not types:
        return "null"
    if types <= {"integer", "number"}:
        return "number" if "number" in types else "integer"
    if len(types) == 1:
        return next(iter(types))
    return "mixed[" + ",".join(sorted(types)) + "]"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _open_csv_text(path: Path) -> Iterator[TextIO]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            yield handle
        return
    with path.open("r", encoding="utf-8", newline="") as handle:
        yield handle

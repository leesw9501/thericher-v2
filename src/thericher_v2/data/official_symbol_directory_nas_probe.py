"""Offline contract for one small NASDAQ current-listing capability probe.

The official NASDAQ listing is current-listing evidence only.  This module
does not infer historical membership, point-in-time eligibility, price
coverage, or a trading decision.  It reads a supplied immutable snapshot and
returns source-safe metadata for one fixed six-symbol probe registry.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OFFICIAL_SYMBOL_DIRECTORY_SNAPSHOT_KIND = "official_symbol_directory_prospective_snapshot"
OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_VERSION = "official-symbol-directory-nas-probe-r1"
OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256 = (
    "sha256:129e6aa02a27e8760139a901f13e2ee4e3fc9b5d4a3e615f9dcd431154aecea4"
)
NASDAQ_LISTING_FILE_NAME = "nasdaqlisted.txt"
NAS_EXCHANGE = "NAS"
NAS_COMMON_STOCK_PROBE_SYMBOLS = (
    "AAPL",
    "AMZN",
    "GOOGL",
    "META",
    "MSFT",
    "NVDA",
)
NAS_COMMON_STOCK_PROBE_TARGET_COUNT = len(NAS_COMMON_STOCK_PROBE_SYMBOLS)

_REQUIRED_LISTING_COLUMNS = (
    "Symbol",
    "Security Name",
    "Market Category",
    "Test Issue",
    "Financial Status",
    "Round Lot Size",
    "ETF",
    "NextShares",
)
_ALLOWED_MARKET_CATEGORIES = frozenset({"G", "Q", "S"})
_EXCLUDED_SECURITY_NAME_TERMS = (
    "depositary",
    "etf",
    "fund",
    "note",
    "preferred",
    "right",
    "trust",
    "unit",
    "warrant",
)
_SYMBOL_PATTERN = re.compile(r"[A-Z]{1,5}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class OfficialSymbolDirectoryNasProbeError(ValueError):
    """A fail-closed current-listing source-contract error."""


@dataclass(frozen=True, slots=True)
class NasProbeTarget:
    """One target in the immutable NAS-only capability registry."""

    symbol: str
    exchange: str


@dataclass(frozen=True, slots=True)
class OfficialSymbolDirectoryNasProbeRegistry:
    """Source-safe, immutable metadata for the fixed prospective-only registry."""

    version: str
    source_manifest_sha256: str
    source_file_sha256: str
    source_file_size_bytes: int
    targets: tuple[NasProbeTarget, ...]
    registry_payload: bytes
    registry_sha256: str

    @property
    def prospective_only(self) -> bool:
        """Current-listing evidence cannot establish historical membership."""

        return True

    @property
    def historical_point_in_time_eligible(self) -> bool:
        """The registry is deliberately not a point-in-time universe."""

        return False

    @property
    def target_keys(self) -> tuple[str, ...]:
        """Return canonical probe keys without exposing original listing rows."""

        return tuple(f"{target.symbol}/{target.exchange}" for target in self.targets)


def build_official_symbol_directory_nas_probe_registry(
    *,
    manifest_path: Path | str,
    nasdaq_listing_path: Path | str,
) -> OfficialSymbolDirectoryNasProbeRegistry:
    """Verify a supplied snapshot and derive the fixed NAS-only probe registry.

    The manifest must declare an immutable, prospective-only
    ``official_symbol_directory_prospective_snapshot`` and bind
    ``nasdaqlisted.txt`` in its ``files`` document with a SHA-256 digest.  No provider,
    network, environment, credential, KIS, or artifact operation is involved.
    """

    return _build_official_symbol_directory_nas_probe_registry(
        manifest_path=manifest_path,
        nasdaq_listing_path=nasdaq_listing_path,
        expected_manifest_sha256=OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_SOURCE_MANIFEST_SHA256,
    )


def _build_official_symbol_directory_nas_probe_registry(
    *,
    manifest_path: Path | str,
    nasdaq_listing_path: Path | str,
    expected_manifest_sha256: str,
) -> OfficialSymbolDirectoryNasProbeRegistry:
    """Build the same registry against an explicitly injected source identity.

    The public builder above always uses the one approved snapshot hash. This
    narrow helper exists so offline tests can exercise parser failures without
    copying the private source snapshot into the repository.
    """

    expected_manifest_sha256 = _required_sha256(
        expected_manifest_sha256,
        "official symbol-directory manifest sha256",
    )
    manifest_bytes = _read_file(manifest_path, "official symbol-directory manifest")
    source_manifest_sha256 = _sha256(manifest_bytes)
    if source_manifest_sha256 != expected_manifest_sha256:
        raise OfficialSymbolDirectoryNasProbeError(
            "official symbol-directory manifest hash mismatch"
        )
    manifest = _parse_manifest(manifest_bytes)
    source_entry = _validate_manifest(manifest)

    listing = Path(nasdaq_listing_path)
    if listing.name != NASDAQ_LISTING_FILE_NAME:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing filename is invalid")
    listing_bytes = _read_file(listing, "NASDAQ listing file")
    source_file_sha256 = _sha256(listing_bytes)
    expected_source_sha256 = _required_sha256(source_entry.get("sha256"), "source file sha256")
    if source_file_sha256 != expected_source_sha256:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing source file hash mismatch")
    _validate_optional_size(source_entry.get("size_bytes"), len(listing_bytes))

    rows_by_symbol = _parse_nasdaq_listing(listing_bytes)
    targets = _fixed_eligible_targets(rows_by_symbol)
    payload = _registry_payload(
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256=source_file_sha256,
        source_file_size_bytes=len(listing_bytes),
        targets=targets,
    )
    return OfficialSymbolDirectoryNasProbeRegistry(
        version=OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_VERSION,
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256=source_file_sha256,
        source_file_size_bytes=len(listing_bytes),
        targets=targets,
        registry_payload=payload,
        registry_sha256=_sha256(payload),
    )


def _read_file(path_value: Path | str, label: str) -> bytes:
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise OfficialSymbolDirectoryNasProbeError(f"{label} is unreadable")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise OfficialSymbolDirectoryNasProbeError(f"{label} is unreadable") from exc


def _parse_manifest(data: bytes) -> Mapping[str, Any]:
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfficialSymbolDirectoryNasProbeError(
            "official symbol-directory manifest is invalid"
        ) from exc
    if not isinstance(manifest, dict):
        raise OfficialSymbolDirectoryNasProbeError("official symbol-directory manifest is invalid")
    return manifest


def _validate_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    if manifest.get("kind") != OFFICIAL_SYMBOL_DIRECTORY_SNAPSHOT_KIND:
        raise OfficialSymbolDirectoryNasProbeError(
            "official symbol-directory manifest kind is invalid"
        )
    if manifest.get("immutable_snapshot") is not True:
        raise OfficialSymbolDirectoryNasProbeError(
            "official symbol-directory snapshot must be immutable"
        )
    if not _manifest_is_prospective_only(manifest):
        raise OfficialSymbolDirectoryNasProbeError(
            "official symbol-directory snapshot must be prospective-only"
        )
    source_entry = _source_file_entry(manifest)
    _validate_source_entry(source_entry)
    return source_entry


def _manifest_is_prospective_only(manifest: Mapping[str, Any]) -> bool:
    top_level = manifest.get("prospective_only")
    scope_value = manifest.get("scope")
    scope = scope_value if isinstance(scope_value, Mapping) else None
    scoped = scope.get("prospective_only") if scope is not None else None
    declared = tuple(value for value in (top_level, scoped) if value is not None)
    return bool(declared) and all(value is True for value in declared)


def _source_file_entry(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    document = manifest.get("files")
    if not isinstance(document, list):
        raise OfficialSymbolDirectoryNasProbeError("official source file document is invalid")
    entries = [
        entry
        for entry in document
        if isinstance(entry, Mapping) and entry.get("name") == NASDAQ_LISTING_FILE_NAME
    ]
    if not entries:
        raise OfficialSymbolDirectoryNasProbeError("official source file entry is missing")
    if len(entries) != 1:
        raise OfficialSymbolDirectoryNasProbeError("official source file entry is ambiguous")
    return entries[0]


def _validate_source_entry(entry: Mapping[str, Any]) -> None:
    if entry.get("name") != NASDAQ_LISTING_FILE_NAME:
        raise OfficialSymbolDirectoryNasProbeError("official source file name is invalid")
    if entry.get("bytes_unaltered") is not True:
        raise OfficialSymbolDirectoryNasProbeError("official source file must be unaltered")
    _required_sha256(entry.get("sha256"), "source file sha256")
    size_bytes = entry.get("size_bytes")
    if size_bytes is not None and (
        not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 1
    ):
        raise OfficialSymbolDirectoryNasProbeError("official source file size is invalid")


def _validate_optional_size(value: object, actual_size: int) -> None:
    if value is not None and value != actual_size:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing source file size mismatch")


def _parse_nasdaq_listing(data: bytes) -> dict[str, Mapping[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), delimiter="|")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing file is invalid") from exc
    fieldnames = tuple(reader.fieldnames or ())
    if len(fieldnames) != len(set(fieldnames)) or not set(_REQUIRED_LISTING_COLUMNS).issubset(
        fieldnames
    ):
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing schema is invalid")

    rows_by_symbol: dict[str, Mapping[str, str]] = {}
    footer_seen = False
    try:
        for row in reader:
            symbol_value = row.get("Symbol")
            symbol = symbol_value.strip().upper() if isinstance(symbol_value, str) else ""
            if symbol.startswith("FILE CREATION TIME:"):
                footer_seen = True
                continue
            if footer_seen:
                raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing footer is not terminal")
            if any(row.get(column) is None for column in _REQUIRED_LISTING_COLUMNS):
                raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing row is incomplete")
            if not symbol:
                raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing row has no symbol")
            if symbol in rows_by_symbol:
                raise OfficialSymbolDirectoryNasProbeError(
                    "NASDAQ listing contains duplicate symbols"
                )
            rows_by_symbol[symbol] = {
                column: str(row[column]).strip() for column in _REQUIRED_LISTING_COLUMNS
            }
    except csv.Error as exc:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing file is invalid") from exc
    if not rows_by_symbol:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ listing has no symbols")
    return rows_by_symbol


def _fixed_eligible_targets(
    rows_by_symbol: Mapping[str, Mapping[str, str]],
) -> tuple[NasProbeTarget, ...]:
    targets: list[NasProbeTarget] = []
    for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS:
        row = rows_by_symbol.get(symbol)
        if row is None:
            raise OfficialSymbolDirectoryNasProbeError(
                "NASDAQ listing is missing a fixed probe symbol"
            )
        if not _is_eligible_common_stock(symbol, row):
            raise OfficialSymbolDirectoryNasProbeError(
                "NASDAQ listing fixed probe symbol is not an eligible common stock"
            )
        targets.append(NasProbeTarget(symbol=symbol, exchange=NAS_EXCHANGE))
    if len(targets) != NAS_COMMON_STOCK_PROBE_TARGET_COUNT:
        raise OfficialSymbolDirectoryNasProbeError("NASDAQ probe target count is invalid")
    return tuple(targets)


def _is_eligible_common_stock(symbol: str, row: Mapping[str, str]) -> bool:
    if _SYMBOL_PATTERN.fullmatch(symbol) is None:
        return False
    if row["Market Category"].upper() not in _ALLOWED_MARKET_CATEGORIES:
        return False
    if row["Test Issue"].upper() != "N":
        return False
    if row["Financial Status"].upper() != "N":
        return False
    if row["ETF"].upper() != "N" or row["NextShares"].upper() != "N":
        return False
    security_name = row["Security Name"].casefold()
    return security_name.endswith(" common stock") and not any(
        term in security_name for term in _EXCLUDED_SECURITY_NAME_TERMS
    )


def _registry_payload(
    *,
    source_manifest_sha256: str,
    source_file_sha256: str,
    source_file_size_bytes: int,
    targets: tuple[NasProbeTarget, ...],
) -> bytes:
    payload = {
        "exchange": NAS_EXCHANGE,
        "kind": "official_symbol_directory_nas_probe_registry",
        "limitations": [
            "current_listing_only",
            "not_historical_point_in_time_universe",
            "not_price_coverage_or_corporate_action_qualification",
            "not_training_or_trading_input",
        ],
        "prospective_only": True,
        "selection_rules": {
            "common_stock_name_suffix": " common stock",
            "excluded_security_name_terms": list(_EXCLUDED_SECURITY_NAME_TERMS),
            "fixed_symbols": list(NAS_COMMON_STOCK_PROBE_SYMBOLS),
            "market_categories": sorted(_ALLOWED_MARKET_CATEGORIES),
            "nextshares": "N",
            "symbol_pattern": _SYMBOL_PATTERN.pattern,
            "test_issue": "N",
            "etf": "N",
            "financial_status": "N",
        },
        "source": {
            "listing_file": NASDAQ_LISTING_FILE_NAME,
            "listing_file_sha256": source_file_sha256,
            "listing_file_size_bytes": source_file_size_bytes,
            "manifest_sha256": source_manifest_sha256,
        },
        "targets": [
            {"exchange": target.exchange, "symbol": target.symbol} for target in targets
        ],
        "version": OFFICIAL_SYMBOL_DIRECTORY_NAS_PROBE_VERSION,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _required_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise OfficialSymbolDirectoryNasProbeError(f"{label} is invalid")
    normalized = value.removeprefix("sha256:").lower()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise OfficialSymbolDirectoryNasProbeError(f"{label} is invalid")
    return f"sha256:{normalized}"


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"

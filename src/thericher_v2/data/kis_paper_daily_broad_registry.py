"""Offline registry for a broad NAS current-listing daily-data bootstrap.

This module reattests one immutable official NASDAQ current-listing snapshot
and emits only canonical ``symbol``/``exchange`` targets plus source-safe
provenance.  It is not provider price data, a point-in-time universe, or a
ranking input.  It never reads configuration, credentials, or the network.
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
KIS_PAPER_DAILY_BROAD_REGISTRY_KIND = "kis_paper_daily_broad_current_listing_registry"
KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION = "kis-paper-daily-broad-registry-r1"
KIS_PAPER_DAILY_BROAD_REGISTRY_SOURCE_MANIFEST_SHA256 = (
    "sha256:129e6aa02a27e8760139a901f13e2ee4e3fc9b5d4a3e615f9dcd431154aecea4"
)
KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME = "kis-paper-daily-broad-registry.json"
NASDAQ_LISTING_FILE_NAME = "nasdaqlisted.txt"
NAS_EXCHANGE = "NAS"
BOOTSTRAP_TARGET_COUNT = 8

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


class KisPaperDailyBroadRegistryError(ValueError):
    """A fail-closed current-listing registry contract error."""


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadRegistryScope:
    """Typed limits that prevent this registry becoming price or PIT evidence."""

    current_listing_only: bool = True
    non_pit: bool = True
    non_ranking: bool = True
    provider_price_data: bool = False


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadRegistryTarget:
    """One canonical KIS daily target derived from the NAS current listing."""

    symbol: str
    exchange: str

    @property
    def key(self) -> str:
        """Return the canonical source-safe target key."""

        return f"{self.symbol}/{self.exchange}"


@dataclass(frozen=True, slots=True)
class KisPaperDailyBroadRegistry:
    """Immutable, source-safe broad registry and its deterministic bootstrap."""

    version: str
    scope: KisPaperDailyBroadRegistryScope
    source_manifest_sha256: str
    source_file_sha256: str
    source_file_size_bytes: int
    targets: tuple[KisPaperDailyBroadRegistryTarget, ...]
    bootstrap_targets: tuple[KisPaperDailyBroadRegistryTarget, ...]
    registry_identity_sha256: str
    registry_payload: bytes
    registry_sha256: str

    @property
    def target_keys(self) -> tuple[str, ...]:
        """Return every eligible canonical target key in sorted canonical order."""

        return tuple(target.key for target in self.targets)

    @property
    def bootstrap_target_keys(self) -> tuple[str, ...]:
        """Return the fixed-size bootstrap selection in identity-hash order."""

        return tuple(target.key for target in self.bootstrap_targets)


def build_kis_paper_daily_broad_registry(
    *,
    manifest_path: Path | str,
    nasdaq_listing_path: Path | str,
) -> KisPaperDailyBroadRegistry:
    """Build the broad registry against the one pinned official source manifest.

    The public entrypoint intentionally accepts only the approved source
    manifest identity.  The source snapshot is current-listing evidence only;
    no historical membership or provider price-data claim is inferred.
    """

    return _build_kis_paper_daily_broad_registry(
        manifest_path=manifest_path,
        nasdaq_listing_path=nasdaq_listing_path,
        expected_manifest_sha256=KIS_PAPER_DAILY_BROAD_REGISTRY_SOURCE_MANIFEST_SHA256,
    )


def _build_kis_paper_daily_broad_registry(
    *,
    manifest_path: Path | str,
    nasdaq_listing_path: Path | str,
    expected_manifest_sha256: str,
) -> KisPaperDailyBroadRegistry:
    """Build against an injected source identity for offline contract tests."""

    expected_manifest_sha256 = _required_sha256(
        expected_manifest_sha256,
        "official symbol-directory manifest sha256",
    )
    manifest_bytes = _read_file(manifest_path, "official symbol-directory manifest")
    source_manifest_sha256 = _sha256(manifest_bytes)
    if source_manifest_sha256 != expected_manifest_sha256:
        raise KisPaperDailyBroadRegistryError("official symbol-directory manifest hash mismatch")

    manifest = _parse_manifest(manifest_bytes)
    source_entry = _validate_manifest(manifest)
    listing = Path(nasdaq_listing_path)
    if listing.name != NASDAQ_LISTING_FILE_NAME:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing filename is invalid")
    listing_bytes = _read_file(listing, "NASDAQ listing file")
    source_file_sha256 = _sha256(listing_bytes)
    expected_source_sha256 = _required_sha256(source_entry.get("sha256"), "source file sha256")
    if source_file_sha256 != expected_source_sha256:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing source file hash mismatch")
    source_file_size_bytes = _required_size(source_entry.get("size_bytes"), "source file size")
    if len(listing_bytes) != source_file_size_bytes:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing source file size mismatch")

    targets = _eligible_targets(_parse_nasdaq_listing(listing_bytes))
    if len(targets) < BOOTSTRAP_TARGET_COUNT:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing has too few eligible targets")
    scope = KisPaperDailyBroadRegistryScope()
    registry_identity_sha256 = _sha256(_registry_identity_payload(scope=scope, targets=targets))
    bootstrap_targets = _bootstrap_targets(
        registry_identity_sha256=registry_identity_sha256,
        targets=targets,
    )
    payload = _registry_payload(
        scope=scope,
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256=source_file_sha256,
        source_file_size_bytes=source_file_size_bytes,
        targets=targets,
        bootstrap_targets=bootstrap_targets,
        registry_identity_sha256=registry_identity_sha256,
    )
    return KisPaperDailyBroadRegistry(
        version=KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
        scope=scope,
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256=source_file_sha256,
        source_file_size_bytes=source_file_size_bytes,
        targets=targets,
        bootstrap_targets=bootstrap_targets,
        registry_identity_sha256=registry_identity_sha256,
        registry_payload=payload,
        registry_sha256=_sha256(payload),
    )


def write_kis_paper_daily_broad_registry(
    *,
    registry: KisPaperDailyBroadRegistry,
    output_root: Path | str,
    repo_root: Path | str,
) -> Path:
    """Atomically write a registry only to an external, non-symlink root."""

    root = _external_root(output_root=output_root, repo_root=repo_root, create=True)
    output_path = root / KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME
    _reject_symlink_ancestors(output_path, "registry output path")
    if output_path.is_symlink():
        raise KisPaperDailyBroadRegistryError("registry output path must not be a symlink")
    if output_path.exists():
        if not output_path.is_file():
            raise KisPaperDailyBroadRegistryError("registry output path is invalid")
        if _read_file(output_path, "registry output") != registry.registry_payload:
            raise KisPaperDailyBroadRegistryError("registry output already has different content")
        return output_path

    temporary_path = root / (
        f".{KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME}."
        f"{registry.registry_sha256.removeprefix('sha256:')}.tmp"
    )
    _reject_symlink_ancestors(temporary_path, "registry temporary output path")
    try:
        with temporary_path.open("xb") as handle:
            handle.write(registry.registry_payload)
            handle.flush()
    except FileExistsError:
        if temporary_path.is_symlink() or _read_file(
            temporary_path, "registry temporary output"
        ) != registry.registry_payload:
            raise KisPaperDailyBroadRegistryError("registry temporary output is invalid") from None
    try:
        temporary_path.replace(output_path)
    except OSError as exc:
        raise KisPaperDailyBroadRegistryError("registry output could not be finalized") from exc
    return output_path


def load_kis_paper_daily_broad_registry(
    *,
    output_root: Path | str,
    repo_root: Path | str,
) -> KisPaperDailyBroadRegistry:
    """Reload and reattest an externally written canonical registry payload."""

    root = _external_root(output_root=output_root, repo_root=repo_root, create=False)
    payload = _read_file(
        root / KIS_PAPER_DAILY_BROAD_REGISTRY_FILENAME,
        "registry output",
    )
    return _registry_from_payload(payload)


def _external_root(*, output_root: Path | str, repo_root: Path | str, create: bool) -> Path:
    root = Path(output_root).absolute()
    repository = Path(repo_root).absolute()
    _reject_symlink_ancestors(root, "registry output root")
    _reject_symlink_ancestors(repository, "repository root")
    if not repository.is_dir():
        raise KisPaperDailyBroadRegistryError("repository root is invalid")
    if root.exists() and not root.is_dir():
        raise KisPaperDailyBroadRegistryError("registry output root is invalid")

    resolved_root = root.resolve(strict=False)
    resolved_repository = repository.resolve(strict=True)
    mounted_market_data = resolved_repository / "market_data"
    mounted_market_data_root = mounted_market_data.resolve(strict=False)
    external_mount = (
        mounted_market_data.is_mount()
        and _is_relative_to(resolved_root, mounted_market_data_root)
    )
    if _is_relative_to(resolved_root, resolved_repository) and not external_mount:
        raise KisPaperDailyBroadRegistryError("registry output root must be outside the repository")
    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise KisPaperDailyBroadRegistryError("registry output root is unavailable") from exc
        _reject_symlink_ancestors(root, "registry output root")
    elif not root.is_dir():
        raise KisPaperDailyBroadRegistryError("registry output root is unavailable")
    return root


def _registry_from_payload(payload: bytes) -> KisPaperDailyBroadRegistry:
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KisPaperDailyBroadRegistryError("registry output is invalid") from exc
    if not isinstance(document, Mapping):
        raise KisPaperDailyBroadRegistryError("registry output is invalid")
    expected_keys = {
        "bootstrap_targets",
        "kind",
        "registry_identity_sha256",
        "scope",
        "source",
        "targets",
        "version",
    }
    if set(document) != expected_keys:
        raise KisPaperDailyBroadRegistryError("registry output schema is invalid")
    if document.get("kind") != KIS_PAPER_DAILY_BROAD_REGISTRY_KIND:
        raise KisPaperDailyBroadRegistryError("registry output kind is invalid")
    if document.get("version") != KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION:
        raise KisPaperDailyBroadRegistryError("registry output version is invalid")

    scope = _scope_from_payload(document.get("scope"))
    source = document.get("source")
    if not isinstance(source, Mapping) or set(source) != {
        "listing_file",
        "listing_file_sha256",
        "listing_file_size_bytes",
        "manifest_sha256",
    }:
        raise KisPaperDailyBroadRegistryError("registry output source is invalid")
    if source.get("listing_file") != NASDAQ_LISTING_FILE_NAME:
        raise KisPaperDailyBroadRegistryError("registry output listing file is invalid")
    source_manifest_sha256 = _required_sha256(
        source.get("manifest_sha256"),
        "registry output manifest sha256",
    )
    source_file_sha256 = _required_sha256(
        source.get("listing_file_sha256"),
        "registry output source file sha256",
    )
    source_file_size_bytes = _required_size(
        source.get("listing_file_size_bytes"),
        "registry output source file size",
    )
    targets = _targets_from_payload(document.get("targets"), "registry output targets")
    if len(targets) < BOOTSTRAP_TARGET_COUNT:
        raise KisPaperDailyBroadRegistryError("registry output has too few targets")
    if targets != tuple(sorted(targets, key=lambda target: target.key)):
        raise KisPaperDailyBroadRegistryError("registry output targets are not canonical")

    registry_identity_sha256 = _required_sha256(
        document.get("registry_identity_sha256"),
        "registry output identity sha256",
    )
    expected_identity_sha256 = _sha256(_registry_identity_payload(scope=scope, targets=targets))
    if registry_identity_sha256 != expected_identity_sha256:
        raise KisPaperDailyBroadRegistryError("registry output identity hash mismatch")
    bootstrap_targets = _targets_from_payload(
        document.get("bootstrap_targets"),
        "registry output bootstrap targets",
    )
    expected_bootstrap_targets = _bootstrap_targets(
        registry_identity_sha256=registry_identity_sha256,
        targets=targets,
    )
    if bootstrap_targets != expected_bootstrap_targets:
        raise KisPaperDailyBroadRegistryError("registry output bootstrap selection is invalid")

    canonical_payload = _registry_payload(
        scope=scope,
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256=source_file_sha256,
        source_file_size_bytes=source_file_size_bytes,
        targets=targets,
        bootstrap_targets=bootstrap_targets,
        registry_identity_sha256=registry_identity_sha256,
    )
    if payload != canonical_payload:
        raise KisPaperDailyBroadRegistryError("registry output is not canonical")
    return KisPaperDailyBroadRegistry(
        version=KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
        scope=scope,
        source_manifest_sha256=source_manifest_sha256,
        source_file_sha256=source_file_sha256,
        source_file_size_bytes=source_file_size_bytes,
        targets=targets,
        bootstrap_targets=bootstrap_targets,
        registry_identity_sha256=registry_identity_sha256,
        registry_payload=canonical_payload,
        registry_sha256=_sha256(canonical_payload),
    )


def _read_file(path_value: Path | str, label: str) -> bytes:
    path = Path(path_value)
    _reject_symlink_ancestors(path, label)
    if path.is_symlink() or not path.is_file():
        raise KisPaperDailyBroadRegistryError(f"{label} is unreadable")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise KisPaperDailyBroadRegistryError(f"{label} is unreadable") from exc


def _reject_symlink_ancestors(path: Path, label: str) -> None:
    current = path.absolute()
    while True:
        try:
            if current.is_symlink():
                raise KisPaperDailyBroadRegistryError(f"{label} must not use a symlink")
        except OSError as exc:
            raise KisPaperDailyBroadRegistryError(f"{label} is unreadable") from exc
        parent = current.parent
        if parent == current:
            return
        current = parent


def _parse_manifest(data: bytes) -> Mapping[str, Any]:
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KisPaperDailyBroadRegistryError(
            "official symbol-directory manifest is invalid"
        ) from exc
    if not isinstance(manifest, Mapping):
        raise KisPaperDailyBroadRegistryError("official symbol-directory manifest is invalid")
    return manifest


def _validate_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    if manifest.get("kind") != OFFICIAL_SYMBOL_DIRECTORY_SNAPSHOT_KIND:
        raise KisPaperDailyBroadRegistryError("official symbol-directory manifest kind is invalid")
    if manifest.get("immutable_snapshot") is not True:
        raise KisPaperDailyBroadRegistryError(
            "official symbol-directory snapshot must be immutable"
        )
    if not _manifest_is_prospective_only(manifest):
        raise KisPaperDailyBroadRegistryError(
            "official symbol-directory snapshot must be prospective-only"
        )
    source_entry = _source_file_entry(manifest)
    if source_entry.get("bytes_unaltered") is not True:
        raise KisPaperDailyBroadRegistryError("official source file must be unaltered")
    _required_sha256(source_entry.get("sha256"), "source file sha256")
    _required_size(source_entry.get("size_bytes"), "source file size")
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
        raise KisPaperDailyBroadRegistryError("official source file document is invalid")
    entries = [
        entry
        for entry in document
        if isinstance(entry, Mapping) and entry.get("name") == NASDAQ_LISTING_FILE_NAME
    ]
    if len(entries) != 1:
        raise KisPaperDailyBroadRegistryError("official source file entry is invalid")
    return entries[0]


def _parse_nasdaq_listing(data: bytes) -> dict[str, Mapping[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), delimiter="|")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing file is invalid") from exc
    fieldnames = tuple(reader.fieldnames or ())
    if len(fieldnames) != len(set(fieldnames)) or not set(_REQUIRED_LISTING_COLUMNS).issubset(
        fieldnames
    ):
        raise KisPaperDailyBroadRegistryError("NASDAQ listing schema is invalid")

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
                raise KisPaperDailyBroadRegistryError("NASDAQ listing footer is not terminal")
            if any(row.get(column) is None for column in _REQUIRED_LISTING_COLUMNS):
                raise KisPaperDailyBroadRegistryError("NASDAQ listing row is incomplete")
            if not symbol:
                raise KisPaperDailyBroadRegistryError("NASDAQ listing row has no symbol")
            if symbol in rows_by_symbol:
                raise KisPaperDailyBroadRegistryError("NASDAQ listing contains duplicate symbols")
            rows_by_symbol[symbol] = {
                column: str(row[column]).strip() for column in _REQUIRED_LISTING_COLUMNS
            }
    except csv.Error as exc:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing file is invalid") from exc
    if not rows_by_symbol:
        raise KisPaperDailyBroadRegistryError("NASDAQ listing has no symbols")
    return rows_by_symbol


def _eligible_targets(
    rows_by_symbol: Mapping[str, Mapping[str, str]],
) -> tuple[KisPaperDailyBroadRegistryTarget, ...]:
    targets = tuple(
        KisPaperDailyBroadRegistryTarget(symbol=symbol, exchange=NAS_EXCHANGE)
        for symbol, row in sorted(rows_by_symbol.items())
        if _is_eligible_common_stock(symbol, row)
    )
    if len({target.key for target in targets}) != len(targets):
        raise KisPaperDailyBroadRegistryError("NASDAQ registry targets are ambiguous")
    return targets


def _is_eligible_common_stock(symbol: str, row: Mapping[str, str]) -> bool:
    if _SYMBOL_PATTERN.fullmatch(symbol) is None:
        return False
    if row["Market Category"].upper() not in _ALLOWED_MARKET_CATEGORIES:
        return False
    if row["Test Issue"].upper() != "N" or row["Financial Status"].upper() != "N":
        return False
    if row["ETF"].upper() != "N" or row["NextShares"].upper() != "N":
        return False
    security_name = row["Security Name"].casefold()
    return security_name.endswith(" common stock") and not any(
        term in security_name for term in _EXCLUDED_SECURITY_NAME_TERMS
    )


def _bootstrap_targets(
    *,
    registry_identity_sha256: str,
    targets: tuple[KisPaperDailyBroadRegistryTarget, ...],
) -> tuple[KisPaperDailyBroadRegistryTarget, ...]:
    return tuple(
        sorted(
            targets,
            key=lambda target: (
                hashlib.sha256(
                    f"{registry_identity_sha256}:{target.key}".encode("ascii")
                ).hexdigest(),
                target.key,
            ),
        )[:BOOTSTRAP_TARGET_COUNT]
    )


def _registry_identity_payload(
    *,
    scope: KisPaperDailyBroadRegistryScope,
    targets: tuple[KisPaperDailyBroadRegistryTarget, ...],
) -> bytes:
    return _canonical_json(
        {
            "exchange": NAS_EXCHANGE,
            "kind": KIS_PAPER_DAILY_BROAD_REGISTRY_KIND,
            "scope": _scope_payload(scope),
            "targets": _target_payload(targets),
            "version": KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
        }
    )


def _registry_payload(
    *,
    scope: KisPaperDailyBroadRegistryScope,
    source_manifest_sha256: str,
    source_file_sha256: str,
    source_file_size_bytes: int,
    targets: tuple[KisPaperDailyBroadRegistryTarget, ...],
    bootstrap_targets: tuple[KisPaperDailyBroadRegistryTarget, ...],
    registry_identity_sha256: str,
) -> bytes:
    return _canonical_json(
        {
            "bootstrap_targets": _target_payload(bootstrap_targets),
            "kind": KIS_PAPER_DAILY_BROAD_REGISTRY_KIND,
            "registry_identity_sha256": registry_identity_sha256,
            "scope": _scope_payload(scope),
            "source": {
                "listing_file": NASDAQ_LISTING_FILE_NAME,
                "listing_file_sha256": source_file_sha256,
                "listing_file_size_bytes": source_file_size_bytes,
                "manifest_sha256": source_manifest_sha256,
            },
            "targets": _target_payload(targets),
            "version": KIS_PAPER_DAILY_BROAD_REGISTRY_VERSION,
        }
    )


def _scope_payload(scope: KisPaperDailyBroadRegistryScope) -> dict[str, bool]:
    return {
        "current_listing_only": scope.current_listing_only,
        "non_pit": scope.non_pit,
        "non_ranking": scope.non_ranking,
        "provider_price_data": scope.provider_price_data,
    }


def _target_payload(
    targets: tuple[KisPaperDailyBroadRegistryTarget, ...],
) -> list[dict[str, str]]:
    return [{"exchange": target.exchange, "symbol": target.symbol} for target in targets]


def _scope_from_payload(value: object) -> KisPaperDailyBroadRegistryScope:
    expected = _scope_payload(KisPaperDailyBroadRegistryScope())
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise KisPaperDailyBroadRegistryError("registry output scope is invalid")
    return KisPaperDailyBroadRegistryScope()


def _targets_from_payload(
    value: object,
    label: str,
) -> tuple[KisPaperDailyBroadRegistryTarget, ...]:
    if not isinstance(value, list):
        raise KisPaperDailyBroadRegistryError(f"{label} is invalid")
    targets: list[KisPaperDailyBroadRegistryTarget] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"exchange", "symbol"}:
            raise KisPaperDailyBroadRegistryError(f"{label} is invalid")
        symbol = item.get("symbol")
        exchange = item.get("exchange")
        if not isinstance(symbol, str) or _SYMBOL_PATTERN.fullmatch(symbol) is None:
            raise KisPaperDailyBroadRegistryError(f"{label} has an invalid symbol")
        if exchange != NAS_EXCHANGE:
            raise KisPaperDailyBroadRegistryError(f"{label} has an invalid exchange")
        targets.append(KisPaperDailyBroadRegistryTarget(symbol=symbol, exchange=exchange))
    result = tuple(targets)
    if len({target.key for target in result}) != len(result):
        raise KisPaperDailyBroadRegistryError(f"{label} has duplicate targets")
    return result


def _required_size(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise KisPaperDailyBroadRegistryError(f"{label} is invalid")
    return value


def _required_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise KisPaperDailyBroadRegistryError(f"{label} is invalid")
    normalized = value.removeprefix("sha256:").lower()
    if _SHA256_PATTERN.fullmatch(normalized) is None:
        raise KisPaperDailyBroadRegistryError(f"{label} is invalid")
    return f"sha256:{normalized}"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"

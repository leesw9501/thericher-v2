"""Offline loading for the private KIS Paper daily-cache panel.

The loader deliberately has no KIS client, environment lookup, or network
dependency. It re-attests the immutable D: cache before exposing daily bars to
research or local-paper validation.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import (
    CatalogedBars,
    _cataloged_bars_from_verified_loader,
    _validate_sha256,
)

KIS_PAPER_PRIVATE_DAILY_CATALOG_VERSION = "kis-paper-private-daily-catalog-v1"
KIS_PAPER_PRIVATE_DAILY_CATALOG_ID = "kis.paper.private.daily.backfill-v1.common-panel"
KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT = Path("D:/market_data/us_equities/kis_paper_private/daily")
KIS_PAPER_PRIVATE_DAILY_INDEX_RELATIVE_PATH = Path("backfill-v1/index.json")
KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS = (
    "QQQ/NAS/MODP=0",
    "SPY/AMS/MODP=0",
    "IWM/AMS/MODP=0",
)
KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE = "MODP=0_unadjusted"

_RAW_COLUMNS = (
    "symbol",
    "exchange",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
_USABLE_CHUNK_OUTCOMES = frozenset({"committed", "partial", "complete"})


@dataclass(frozen=True)
class KisPaperPrivateDailyCatalog:
    """A hash-attested, same-source daily panel restricted to common sessions."""

    dataset_id: str
    dataset_hash: str
    index_hash: str
    index_path: Path
    source_root: Path
    adjustment_mode: str
    bars_by_symbol: Mapping[str, CatalogedBars]
    common_sessions: tuple[date, ...]
    raw_price_limitations: tuple[str, ...]


@dataclass(frozen=True)
class _VerifiedDailyRow:
    bar: Bar
    record: tuple[str, ...]


def load_kis_paper_private_daily_catalog(
    cache_root: Path | str = KIS_PAPER_PRIVATE_DAILY_CACHE_ROOT,
    *,
    target_keys: Sequence[str] = KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS,
    market: str = "US",
    expected_index_hash: str | None = None,
    end_session: date | None = None,
    repo_root: Path | str | None = None,
) -> KisPaperPrivateDailyCatalog:
    """Load verified KIS Paper daily bars without credentials, broker calls, or network.

    Only completed chunks that actually contain a retained raw snapshot become
    research input. A false retention field is a fact about an empty/rejected
    collection result, not a permission or a reason to mutate the cache. When
    ``end_session`` is supplied, every raw file remains fully hash-attested but
    later rows do not become ``Bar`` objects in the returned catalog.
    """

    root = _verified_cache_root(cache_root=cache_root, repo_root=repo_root)
    resolved_market = market.strip().upper()
    if resolved_market != "US":
        raise ValueError("KIS paper daily catalog market must be US")
    requested_targets = _requested_target_keys(target_keys)
    if expected_index_hash is not None:
        _require_sha256(expected_index_hash, "expected_index_hash")
    if end_session is not None and type(end_session) is not date:
        raise ValueError("KIS paper daily catalog end_session must be a date")

    index_path = _safe_external_path(root / KIS_PAPER_PRIVATE_DAILY_INDEX_RELATIVE_PATH, root)
    try:
        index_bytes = index_path.read_bytes()
    except OSError as error:
        raise ValueError("KIS paper daily catalog index is unreadable") from error
    index_hash = _sha256(index_bytes)
    if expected_index_hash is not None and index_hash != expected_index_hash:
        raise ValueError("KIS paper daily catalog index hash mismatch")
    index = _json_document(index_bytes, "KIS paper daily catalog index")
    targets = _selected_index_targets(index=index, requested_targets=requested_targets)

    rows_by_target: dict[str, dict[date, _VerifiedDailyRow]] = {}
    for target_key in requested_targets:
        rows_by_target[target_key] = _load_target_rows(
            target=targets[target_key],
            target_key=target_key,
            root=root,
            market=resolved_market,
            end_session=end_session,
        )

    common_sessions = tuple(
        sorted(set.intersection(*(set(rows) for rows in rows_by_target.values())))
    )
    if not common_sessions:
        raise ValueError("KIS paper daily catalog has no common completed sessions")

    dataset_hash = _dataset_hash(
        target_keys=requested_targets,
        rows_by_target=rows_by_target,
        common_sessions=common_sessions,
        market=resolved_market,
    )
    bars_by_symbol: dict[str, CatalogedBars] = {}
    for target_key in requested_targets:
        symbol, _exchange, _adjustment = target_key.split("/", maxsplit=2)
        bars = tuple(rows_by_target[target_key][session].bar for session in common_sessions)
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )

    return KisPaperPrivateDailyCatalog(
        dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
        dataset_hash=dataset_hash,
        index_hash=index_hash,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        common_sessions=common_sessions,
        raw_price_limitations=(
            "MODP=0_unadjusted",
            "corporate_action_semantics_not_qualified",
        ),
    )


def slice_kis_paper_private_daily_catalog(
    catalog: KisPaperPrivateDailyCatalog,
    *,
    start_index: int,
    stop_index: int,
) -> KisPaperPrivateDailyCatalog:
    """Return a hash-bound chronological slice without reopening the source cache.

    Research uses this boundary to give a phase only the sessions it is allowed
    to consume. The derived identity includes the parent hash and exact session
    range, while the source bytes remain in the existing Data-owned cache.
    """

    if not isinstance(start_index, int) or isinstance(start_index, bool):
        raise ValueError("KIS paper daily slice start_index must be an integer")
    if not isinstance(stop_index, int) or isinstance(stop_index, bool):
        raise ValueError("KIS paper daily slice stop_index must be an integer")
    session_count = len(catalog.common_sessions)
    if not 0 <= start_index < stop_index <= session_count:
        raise ValueError("KIS paper daily slice range is invalid")

    sessions = catalog.common_sessions[start_index:stop_index]
    derived_hash = _slice_dataset_hash(
        parent_dataset_id=catalog.dataset_id,
        parent_dataset_hash=catalog.dataset_hash,
        start_index=start_index,
        stop_index=stop_index,
        sessions=sessions,
    )
    derived_id = f"{catalog.dataset_id}:slice-{start_index}-{stop_index}"
    bars_by_symbol: dict[str, CatalogedBars] = {}
    for symbol, stream in catalog.bars_by_symbol.items():
        bars = stream.bars[start_index:stop_index]
        if len(bars) != len(sessions) or tuple(bar.start_ts.date() for bar in bars) != sessions:
            raise ValueError("KIS paper daily catalog slice streams are incompatible")
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=derived_id,
            dataset_hash=derived_hash,
            source_path=catalog.index_path,
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id=derived_id,
        dataset_hash=derived_hash,
        index_hash=catalog.index_hash,
        index_path=catalog.index_path,
        source_root=catalog.source_root,
        adjustment_mode=catalog.adjustment_mode,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        common_sessions=sessions,
        raw_price_limitations=(
            *catalog.raw_price_limitations,
            f"derived_session_slice_of:{catalog.dataset_hash}",
        ),
    )


def _verified_cache_root(
    *,
    cache_root: Path | str,
    repo_root: Path | str | None,
) -> Path:
    candidate = Path(cache_root)
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("KIS paper daily catalog cache root is invalid")
    try:
        root = candidate.resolve()
    except OSError as error:
        raise ValueError("KIS paper daily catalog cache root is invalid") from error
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("KIS paper daily catalog cache root must stay outside Git")
    return root


def _requested_target_keys(target_keys: Sequence[str]) -> tuple[str, ...]:
    if isinstance(target_keys, str):
        raise ValueError("KIS paper daily catalog target keys are invalid")
    resolved = tuple(str(target_key).strip().upper() for target_key in target_keys)
    if not resolved or len(set(resolved)) != len(resolved):
        raise ValueError("KIS paper daily catalog target keys are invalid")
    if any(target_key not in KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS for target_key in resolved):
        raise ValueError("KIS paper daily catalog target keys are unsupported")
    requested = set(resolved)
    return tuple(
        target_key
        for target_key in KIS_PAPER_PRIVATE_DAILY_TARGET_KEYS
        if target_key in requested
    )


def _selected_index_targets(
    *,
    index: Mapping[str, object],
    requested_targets: tuple[str, ...],
) -> Mapping[str, Mapping[str, object]]:
    if (
        index.get("kind") != "kis_paper_private_daily_backfill_index"
        or index.get("backfill_version") != "kis-paper-private-daily-backfill-v1"
        or not isinstance(index.get("targets"), list)
    ):
        raise ValueError("KIS paper daily catalog index is invalid")
    selected: dict[str, Mapping[str, object]] = {}
    for target in index["targets"]:
        if not isinstance(target, dict):
            raise ValueError("KIS paper daily catalog index is invalid")
        target_key = target.get("target_key")
        if target_key not in requested_targets:
            continue
        if target_key in selected or not isinstance(target_key, str):
            raise ValueError("KIS paper daily catalog index is invalid")
        symbol, exchange, _adjustment = target_key.split("/", maxsplit=2)
        if target.get("symbol") != symbol or target.get("exchange") != exchange:
            raise ValueError("KIS paper daily catalog index is invalid")
        selected[target_key] = target
    if set(selected) != set(requested_targets):
        raise ValueError("KIS paper daily catalog target is missing")
    return MappingProxyType(selected)


def _load_target_rows(
    *,
    target: Mapping[str, object],
    target_key: str,
    root: Path,
    market: str,
    end_session: date | None,
) -> dict[date, _VerifiedDailyRow]:
    chunks = target.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("KIS paper daily catalog target is invalid")
    symbol, exchange, _adjustment = target_key.split("/", maxsplit=2)
    merged: dict[date, _VerifiedDailyRow] = {}
    usable_chunks = [
        chunk
        for chunk in chunks
        if (
            isinstance(chunk, dict)
            and chunk.get("raw_market_data_retained") is True
            and chunk.get("outcome") in _USABLE_CHUNK_OUTCOMES
        )
    ]
    _verify_chunk_cursor_seams(usable_chunks)
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("KIS paper daily catalog target is invalid")
        if chunk.get("raw_market_data_retained") is not True:
            continue
        if chunk.get("outcome") not in _USABLE_CHUNK_OUTCOMES:
            continue
        if not isinstance(chunk.get("row_count"), int) or int(chunk["row_count"]) <= 0:
            raise ValueError("KIS paper daily catalog committed chunk is invalid")
        chunk_rows = _load_chunk_rows(
            chunk=chunk,
            target_key=target_key,
            symbol=symbol,
            exchange=exchange,
            root=root,
            market=market,
            end_session=end_session,
        )
        for session, row in chunk_rows.items():
            prior = merged.get(session)
            if prior is not None and prior.record != row.record:
                raise ValueError("KIS paper daily catalog has conflicting overlap rows")
            merged.setdefault(session, row)
    if not usable_chunks or not merged:
        raise ValueError("KIS paper daily catalog has no retained completed data")
    return merged


def _verify_chunk_cursor_seams(chunks: list[dict[str, object]]) -> None:
    """Require each usable backward page to begin at its newer page's boundary."""

    if any(not isinstance(chunk.get("input_cursor_date"), str) for chunk in chunks):
        raise ValueError("KIS paper daily catalog chunk cursor seam is invalid")
    ordered = sorted(chunks, key=lambda chunk: str(chunk["input_cursor_date"]), reverse=True)
    for newer, older in zip(ordered, ordered[1:], strict=False):
        newer_output = newer.get("output_cursor_date")
        older_input = older.get("input_cursor_date")
        if (
            not isinstance(newer_output, str)
            or not isinstance(older_input, str)
            or newer_output != older_input
        ):
            raise ValueError("KIS paper daily catalog chunk cursor seam is invalid")


def _load_chunk_rows(
    *,
    chunk: Mapping[str, object],
    target_key: str,
    symbol: str,
    exchange: str,
    root: Path,
    market: str,
    end_session: date | None,
) -> dict[date, _VerifiedDailyRow]:
    manifest_path_value = chunk.get("manifest_path")
    manifest_hash = chunk.get("manifest_hash")
    raw_hash = chunk.get("raw_sha256")
    if not isinstance(manifest_path_value, str):
        raise ValueError("KIS paper daily catalog committed chunk is invalid")
    _require_sha256(manifest_hash, "manifest_hash")
    _require_sha256(raw_hash, "raw_sha256")
    manifest_path = _safe_external_path(Path(manifest_path_value), root)
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise ValueError("KIS paper daily catalog manifest is unreadable") from error
    if _sha256(manifest_bytes) != manifest_hash:
        raise ValueError("KIS paper daily catalog manifest hash mismatch")
    manifest = _json_document(manifest_bytes, "KIS paper daily catalog manifest")
    _validate_manifest_identity(
        manifest=manifest,
        target_key=target_key,
        symbol=symbol,
        exchange=exchange,
    )
    raw_document = _raw_document(manifest)
    if raw_document["sha256"] != raw_hash:
        raise ValueError("KIS paper daily catalog raw hash mismatch")
    raw_path = _raw_path(
        raw_document=raw_document,
        manifest_path=manifest_path,
        root=root,
    )
    try:
        raw_bytes = raw_path.read_bytes()
    except OSError as error:
        raise ValueError("KIS paper daily catalog raw file is unreadable") from error
    if len(raw_bytes) != raw_document["size_bytes"] or _sha256(raw_bytes) != raw_hash:
        raise ValueError("KIS paper daily catalog raw hash mismatch")
    rows, actual_fingerprints = _parse_raw_rows(
        raw_bytes=raw_bytes,
        symbol=symbol,
        exchange=exchange,
        market=market,
        end_session=end_session,
    )
    expected_fingerprints = chunk.get("row_fingerprints")
    if not isinstance(expected_fingerprints, dict):
        raise ValueError("KIS paper daily catalog committed chunk is invalid")
    if (
        len(actual_fingerprints) != chunk["row_count"]
        or actual_fingerprints != expected_fingerprints
    ):
        raise ValueError("KIS paper daily catalog committed chunk drift")
    return rows


def _validate_manifest_identity(
    *,
    manifest: Mapping[str, object],
    target_key: str,
    symbol: str,
    exchange: str,
) -> None:
    source = manifest.get("source")
    backfill = manifest.get("backfill")
    if (
        manifest.get("kind") != "kis_paper_private_daily_cache"
        or manifest.get("status") not in {"completed", "partial"}
        or (
            manifest.get("status") == "completed"
            and manifest.get("completed") is not True
        )
        or (
            manifest.get("status") == "partial"
            and (
                manifest.get("completed") is not False
                or not isinstance(manifest.get("stop_outcome"), str)
                or not str(manifest["stop_outcome"]).startswith("partial_")
            )
        )
        or not isinstance(source, dict)
        or source.get("provider") != "KIS Open API virtual paper"
        or source.get("endpoint") != "dailyprice"
        or source.get("symbol") != symbol
        or source.get("exchange") != exchange
        or source.get("adjustment_mode") != KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE
        or not isinstance(backfill, dict)
        or backfill.get("target_key") != target_key
        or backfill.get("contract_version") != "kis-paper-private-daily-backfill-v1"
    ):
        raise ValueError("KIS paper daily catalog manifest is incompatible")


def _raw_document(manifest: Mapping[str, object]) -> Mapping[str, object]:
    files = manifest.get("files")
    document = files.get("raw_daily_rows") if isinstance(files, dict) else None
    if not isinstance(document, dict):
        raise ValueError("KIS paper daily catalog raw document is invalid")
    if (
        document.get("format") != "csv.gz"
        or document.get("ordering") != "session_date_ascending"
        or document.get("columns") != list(_RAW_COLUMNS)
        or not isinstance(document.get("path"), str)
        or type(document.get("size_bytes")) is not int
    ):
        raise ValueError("KIS paper daily catalog raw document is invalid")
    _require_sha256(document.get("sha256"), "raw_sha256")
    return document


def _raw_path(
    *,
    raw_document: Mapping[str, object],
    manifest_path: Path,
    root: Path,
) -> Path:
    raw_relative = Path(str(raw_document["path"]))
    if raw_relative.is_absolute() or ".." in raw_relative.parts:
        raise ValueError("KIS paper daily catalog raw path is invalid")
    raw_path = _safe_external_path(manifest_path.parent / raw_relative, root)
    if not raw_path.is_relative_to(manifest_path.parent.resolve()):
        raise ValueError("KIS paper daily catalog raw path is invalid")
    return raw_path


def _parse_raw_rows(
    *,
    raw_bytes: bytes,
    symbol: str,
    exchange: str,
    market: str,
    end_session: date | None,
) -> tuple[dict[date, _VerifiedDailyRow], dict[str, str]]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes), mode="rb") as handle:
            with io.TextIOWrapper(handle, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                    raise ValueError("KIS paper daily catalog raw schema is invalid")
                rows: dict[date, _VerifiedDailyRow] = {}
                fingerprints: dict[str, str] = {}
                prior_session: date | None = None
                for document in reader:
                    if set(document) != set(_RAW_COLUMNS) or any(
                        document.get(field) is None for field in _RAW_COLUMNS
                    ):
                        raise ValueError("KIS paper daily catalog raw contents are invalid")
                    if document["symbol"] != symbol or document["exchange"] != exchange:
                        raise ValueError("KIS paper daily catalog raw contents are invalid")
                    session = _session_date(document["session_date"])
                    if prior_session is not None and session <= prior_session:
                        raise ValueError("KIS paper daily catalog raw contents are invalid")
                    prior_session = session
                    record = tuple(document[field] for field in _RAW_COLUMNS)
                    fingerprints[session.isoformat()] = _row_fingerprint(record)
                    if end_session is not None and session > end_session:
                        continue
                    try:
                        bar = Bar(
                            symbol=symbol,
                            market=market,
                            timeframe=Timeframe.D1,
                            start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                            open=Decimal(document["open"]),
                            high=Decimal(document["high"]),
                            low=Decimal(document["low"]),
                            close=Decimal(document["close"]),
                            volume=Decimal(document["volume"]),
                            complete=True,
                        )
                    except (InvalidOperation, ValueError) as error:
                        raise ValueError(
                            "KIS paper daily catalog raw contents are invalid"
                        ) from error
                    rows[session] = _VerifiedDailyRow(bar=bar, record=record)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        if (
            isinstance(error, ValueError)
            and str(error) == "KIS paper daily catalog raw schema is invalid"
        ):
            raise
        raise ValueError("KIS paper daily catalog raw contents are invalid") from error

    if not fingerprints or (end_session is None and not rows):
        raise ValueError("KIS paper daily catalog raw contents are invalid")
    return rows, fingerprints


def _dataset_hash(
    *,
    target_keys: tuple[str, ...],
    rows_by_target: Mapping[str, Mapping[date, _VerifiedDailyRow]],
    common_sessions: tuple[date, ...],
    market: str,
) -> str:
    document = {
        "catalog_version": KIS_PAPER_PRIVATE_DAILY_CATALOG_VERSION,
        "market": market,
        "adjustment_mode": KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        "common_sessions": [session.isoformat() for session in common_sessions],
        "streams": [
            {
                "target_key": target_key,
                "rows": [
                    list(rows_by_target[target_key][session].record)
                    for session in common_sessions
                ],
            }
            for target_key in target_keys
        ],
    }
    payload = json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _sha256(payload)


def _slice_dataset_hash(
    *,
    parent_dataset_id: str,
    parent_dataset_hash: str,
    start_index: int,
    stop_index: int,
    sessions: tuple[date, ...],
) -> str:
    payload = json.dumps(
        {
            "kind": "kis_paper_private_daily_catalog_slice_v1",
            "parent_dataset_id": parent_dataset_id,
            "parent_dataset_hash": parent_dataset_hash,
            "start_index": start_index,
            "stop_index": stop_index,
            "sessions": [session.isoformat() for session in sessions],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256(payload)


def _safe_external_path(path: Path, root: Path) -> Path:
    """Reject path escapes and symlinked cache components before reading bytes."""

    resolved_root = root.resolve()
    candidate = Path(os.path.abspath(path))
    current = candidate
    while current != resolved_root:
        if not current.is_relative_to(resolved_root) or current.is_symlink():
            raise ValueError("KIS paper daily catalog path is invalid")
        parent = current.parent
        if parent == current:
            raise ValueError("KIS paper daily catalog path is invalid")
        current = parent
    if candidate.is_symlink():
        raise ValueError("KIS paper daily catalog path is invalid")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError("KIS paper daily catalog path is invalid") from error
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("KIS paper daily catalog path is invalid")
    return resolved


def _json_document(payload: bytes, label: str) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} is invalid")
    return document


def _session_date(value: str) -> date:
    if (
        len(value) != 10
        or value[4] != "-"
        or value[7] != "-"
        or not value.replace("-", "").isdigit()
    ):
        raise ValueError("KIS paper daily catalog raw contents are invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("KIS paper daily catalog raw contents are invalid") from error


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"KIS paper daily catalog {label} is invalid")
    try:
        _validate_sha256(value, label)
    except ValueError as error:
        raise ValueError(f"KIS paper daily catalog {label} is invalid") from error
    return value


def _row_fingerprint(record: tuple[str, ...]) -> str:
    return _sha256("\x1f".join(record).encode("utf-8"))


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()

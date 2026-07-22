"""Pure schema contract for private KIS intraday v1 index metadata.

The contract validates decoded index metadata only. It neither opens snapshot
files nor attests raw market-bar contents.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

_BACKFILL_VERSION = "v1"
_INDEX_KIND = "kis_paper_private_intraday_backfill"
_INVALID_INDEX_MESSAGE = "KIS private intraday v1 index metadata is invalid"

__all__ = [
    "KisPaperPrivateIntradayV1IndexMetadata",
    "KisPaperPrivateIntradayV1RetainedChunkMetadata",
    "KisPaperPrivateIntradayV1TargetMetadata",
    "validate_kis_paper_private_intraday_v1_index_metadata",
]


@dataclass(frozen=True, slots=True)
class KisPaperPrivateIntradayV1RetainedChunkMetadata:
    """Validated retained-chunk metadata in original index row order."""

    chunk_key: str
    input_cursor: Mapping[str, str] | None
    output_cursor: Mapping[str, str] | None
    rows: tuple[tuple[str, str], ...]
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class KisPaperPrivateIntradayV1TargetMetadata:
    """Validated target state without provider rows or file paths."""

    target_key: str
    symbol: str
    exchange: str
    next_cursor: Mapping[str, str] | None
    retained_chunks: tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...]


@dataclass(frozen=True, slots=True)
class KisPaperPrivateIntradayV1IndexMetadata:
    """Immutable projection of a validated private intraday v1 index."""

    generation: int
    targets: tuple[KisPaperPrivateIntradayV1TargetMetadata, ...]


def validate_kis_paper_private_intraday_v1_index_metadata(
    index: Mapping[str, object],
    *,
    expected_targets: Iterable[tuple[str, str]],
) -> KisPaperPrivateIntradayV1IndexMetadata:
    """Validate a decoded v1 index and return its normalized metadata projection.

    ``expected_targets`` is the caller-owned symbol/exchange scope. Target and
    retained-chunk order are preserved from the index; unretained historical
    markers are intentionally excluded from cache semantics.
    """

    if not isinstance(index, Mapping):
        _invalid()
    expected_target_keys = _expected_target_keys(expected_targets)
    if (
        index.get("schema_version") != SCHEMA_VERSION
        or index.get("kind") != _INDEX_KIND
        or index.get("backfill_version") != _BACKFILL_VERSION
        or type(index.get("generation")) is not int
        or int(index["generation"]) < 0
        or not isinstance(index.get("targets"), list)
    ):
        _invalid()

    targets_document = index["targets"]
    assert isinstance(targets_document, list)
    observed_target_keys: set[str] = set()
    targets: list[KisPaperPrivateIntradayV1TargetMetadata] = []
    for target_document in targets_document:
        target = _parse_target(target_document)
        if target.target_key in observed_target_keys:
            _invalid()
        observed_target_keys.add(target.target_key)
        targets.append(target)
    if observed_target_keys != expected_target_keys:
        _invalid()

    return KisPaperPrivateIntradayV1IndexMetadata(
        generation=int(index["generation"]),
        targets=tuple(targets),
    )


def _expected_target_keys(expected_targets: Iterable[tuple[str, str]]) -> frozenset[str]:
    keys: set[str] = set()
    for target in expected_targets:
        if not isinstance(target, tuple) or len(target) != 2:
            _invalid()
        symbol, exchange = target
        target_key = _target_key(symbol=symbol, exchange=exchange)
        if target_key in keys:
            _invalid()
        keys.add(target_key)
    if not keys:
        _invalid()
    return frozenset(keys)


def _parse_target(document: object) -> KisPaperPrivateIntradayV1TargetMetadata:
    if not isinstance(document, Mapping):
        _invalid()
    symbol = _normalize_target_component(document.get("symbol"))
    exchange = _normalize_target_component(document.get("exchange"))
    target_key = _target_key(symbol=symbol, exchange=exchange)
    if document.get("target_key") != target_key:
        _invalid()

    next_cursor = _cursor_document(document.get("next_cursor"))
    last_reason = document.get("last_reason")
    if last_reason is not None and not isinstance(last_reason, str):
        _invalid()
    last_observed_document = document.get("last_observed_at_utc")
    if last_observed_document is not None:
        _parse_utc_timestamp(last_observed_document)
    chunks_document = document.get("chunks")
    if not isinstance(chunks_document, list):
        _invalid()

    chunk_keys: set[str] = set()
    retained_chunks: list[KisPaperPrivateIntradayV1RetainedChunkMetadata] = []
    for chunk_document in chunks_document:
        if _is_unretained_marker(chunk_document):
            continue
        chunk = _parse_retained_chunk(chunk_document, target_key=target_key)
        if chunk.chunk_key in chunk_keys:
            _invalid()
        chunk_keys.add(chunk.chunk_key)
        retained_chunks.append(chunk)

    return KisPaperPrivateIntradayV1TargetMetadata(
        target_key=target_key,
        symbol=symbol,
        exchange=exchange,
        next_cursor=next_cursor,
        retained_chunks=tuple(retained_chunks),
    )


def _parse_retained_chunk(
    document: object,
    *,
    target_key: str,
) -> KisPaperPrivateIntradayV1RetainedChunkMetadata:
    if not isinstance(document, Mapping):
        _invalid()
    input_cursor = _cursor_document(document.get("input_cursor"))
    output_cursor = _cursor_document(document.get("output_cursor"))
    fingerprints_document = document.get("row_fingerprints")
    collected_at_document = document.get("collected_at_utc")
    if (
        document.get("outcome") not in {"committed", "partial"}
        or not isinstance(document.get("manifest_path"), str)
        or not _is_sha256(document.get("manifest_hash"))
        or not _is_sha256(document.get("raw_sha256"))
        or document.get("raw_market_data_retained") is not True
        or not isinstance(document.get("row_count"), int)
        or int(document["row_count"]) <= 0
        or not isinstance(fingerprints_document, Mapping)
        or not isinstance(document.get("exact_overlap_rows"), int)
        or not isinstance(document.get("conflicting_overlap_rows"), int)
        or int(document["conflicting_overlap_rows"]) != 0
        or not isinstance(collected_at_document, str)
    ):
        _invalid()

    rows = tuple(fingerprints_document.items())
    if len(rows) != document["row_count"]:
        _invalid()
    for timestamp, fingerprint in rows:
        if not _is_timestamp_key(timestamp) or not _is_sha256(fingerprint):
            _invalid()
    collected_at = _parse_utc_timestamp(collected_at_document)
    expected_chunk_key = _chunk_key(
        target_key=target_key,
        input_cursor=input_cursor,
        rows=rows,
    )
    legacy_chunk_key = _legacy_chunk_key(target_key=target_key, input_cursor=input_cursor)
    chunk_key = document.get("chunk_key")
    if not isinstance(chunk_key, str) or chunk_key not in {expected_chunk_key, legacy_chunk_key}:
        _invalid()
    if output_cursor == input_cursor and output_cursor is not None:
        _invalid()

    return KisPaperPrivateIntradayV1RetainedChunkMetadata(
        chunk_key=chunk_key,
        input_cursor=input_cursor,
        output_cursor=output_cursor,
        rows=rows,
        collected_at=collected_at,
    )


def _target_key(*, symbol: object, exchange: object) -> str:
    return f"{_normalize_target_component(symbol)}/{_normalize_target_component(exchange)}/1m"


def _normalize_target_component(value: object) -> str:
    if not isinstance(value, str):
        _invalid()
    normalized = value.strip().upper()
    if not normalized:
        _invalid()
    return normalized


def _cursor_document(value: object) -> Mapping[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        _invalid()
    next_value = value.get("next")
    keyb = value.get("keyb")
    if not isinstance(next_value, str) or not isinstance(keyb, str):
        _invalid()
    normalized = {"keyb": keyb.strip(), "next": next_value.strip()}
    if (
        normalized["next"] != "1"
        or len(normalized["keyb"]) != 14
        or not normalized["keyb"].isdigit()
    ):
        _invalid()
    return MappingProxyType(normalized)


def _is_unretained_marker(document: object) -> bool:
    return (
        isinstance(document, Mapping)
        and document.get("raw_market_data_retained") is False
        and not isinstance(document.get("manifest_path"), str)
    )


def _chunk_key(
    *,
    target_key: str,
    input_cursor: Mapping[str, str] | None,
    rows: tuple[tuple[str, str], ...],
) -> str:
    return _sha256_payload(
        {
            "backfill_version": _BACKFILL_VERSION,
            "input_cursor": dict(input_cursor) if input_cursor is not None else None,
            "row_fingerprints": dict(sorted(rows)),
            "target_key": target_key,
        }
    )


def _legacy_chunk_key(
    *,
    target_key: str,
    input_cursor: Mapping[str, str] | None,
) -> str:
    return _sha256_payload(
        {
            "backfill_version": _BACKFILL_VERSION,
            "input_cursor": dict(input_cursor) if input_cursor is not None else None,
            "target_key": target_key,
        }
    )


def _parse_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        _invalid()
    try:
        return require_utc(
            datetime.fromisoformat(value.replace("Z", "+00:00")),
            "KIS private intraday index timestamp",
        )
    except ValueError:
        _invalid()


def _is_timestamp_key(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 15
        and value[8:9] == "T"
        and value[:8].isdigit()
        and value[9:].isdigit()
    )


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    prefix, separator, digest = value.partition(":")
    return (
        prefix == "sha256"
        and separator == ":"
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _invalid() -> None:
    raise ValueError(_INVALID_INDEX_MESSAGE)

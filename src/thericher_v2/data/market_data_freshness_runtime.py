"""Credential-free runtime projection for sanitized market-data freshness."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

MARKET_DATA_FRESHNESS_RUNTIME_KIND = "market_data_freshness_runtime"
MARKET_DATA_FRESHNESS_RUNTIME_TTL = timedelta(hours=36)
_STREAM_PATTERN = re.compile(r"[A-Z0-9]{1,12}/[A-Z]{2,5}/(?:1m|1d)", re.ASCII)
_DETAIL_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}", re.ASCII)

MarketDataFreshnessStatus = Literal["present", "not_created", "invalid"]
MarketDataFreshnessOutcome = Literal["committed", "partial", "unknown"]


class MarketDataFreshnessRuntimeError(ValueError):
    """The sanitized runtime projection is malformed or unsafe to render."""


@dataclass(frozen=True)
class MarketDataFreshnessStream:
    """A small metadata-only view of one stored bar stream."""

    collection_mode: Literal["backfill", "head"]
    stream: str
    cache_status: MarketDataFreshnessStatus
    last_observed_at_utc: datetime | None
    latest_collection_outcome: MarketDataFreshnessOutcome
    retained_chunk_count: int
    partial_chunk_count: int
    detail_code: str | None = None

    def __post_init__(self) -> None:
        if self.collection_mode not in {"backfill", "head"}:
            raise MarketDataFreshnessRuntimeError("freshness_collection_mode_invalid")
        if _STREAM_PATTERN.fullmatch(self.stream) is None:
            raise MarketDataFreshnessRuntimeError("freshness_stream_invalid")
        if self.cache_status not in {"present", "not_created", "invalid"}:
            raise MarketDataFreshnessRuntimeError("freshness_cache_status_invalid")
        if self.latest_collection_outcome not in {"committed", "partial", "unknown"}:
            raise MarketDataFreshnessRuntimeError("freshness_outcome_invalid")
        if (
            type(self.retained_chunk_count) is not int
            or self.retained_chunk_count < 0
            or type(self.partial_chunk_count) is not int
            or self.partial_chunk_count < 0
            or self.partial_chunk_count > self.retained_chunk_count
        ):
            raise MarketDataFreshnessRuntimeError("freshness_count_invalid")
        if self.last_observed_at_utc is not None:
            object.__setattr__(
                self,
                "last_observed_at_utc",
                require_utc(self.last_observed_at_utc, "last_observed_at_utc"),
            )
        if (
            self.detail_code is not None
            and _DETAIL_CODE_PATTERN.fullmatch(self.detail_code) is None
        ):
            raise MarketDataFreshnessRuntimeError("freshness_detail_code_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "collection_mode": self.collection_mode,
            "stream": self.stream,
            "cache_status": self.cache_status,
            "last_observed_at_utc": (
                None if self.last_observed_at_utc is None else self.last_observed_at_utc.isoformat()
            ),
            "latest_collection_outcome": self.latest_collection_outcome,
            "retained_chunk_count": self.retained_chunk_count,
            "partial_chunk_count": self.partial_chunk_count,
            "detail_code": self.detail_code,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MarketDataFreshnessStream:
        expected = {
            "collection_mode",
            "stream",
            "cache_status",
            "last_observed_at_utc",
            "latest_collection_outcome",
            "retained_chunk_count",
            "partial_chunk_count",
            "detail_code",
        }
        if not isinstance(payload, Mapping) or frozenset(payload) != expected:
            raise MarketDataFreshnessRuntimeError("freshness_stream_keys_invalid")
        observed_at = payload["last_observed_at_utc"]
        return cls(
            collection_mode=_text(payload["collection_mode"], "collection_mode"),  # type: ignore[arg-type]
            stream=_text(payload["stream"], "stream"),
            cache_status=_text(payload["cache_status"], "cache_status"),  # type: ignore[arg-type]
            last_observed_at_utc=(
                None
                if observed_at is None
                else _utc_datetime(observed_at, "last_observed_at_utc")
            ),
            latest_collection_outcome=_text(  # type: ignore[arg-type]
                payload["latest_collection_outcome"], "latest_collection_outcome"
            ),
            retained_chunk_count=_count(payload["retained_chunk_count"], "retained_chunk_count"),
            partial_chunk_count=_count(payload["partial_chunk_count"], "partial_chunk_count"),
            detail_code=(
                None
                if payload["detail_code"] is None
                else _text(payload["detail_code"], "detail_code")
            ),
        )


@dataclass(frozen=True)
class MarketDataFreshnessRuntimeSnapshot:
    """A dashboard-readable projection with no paths, hashes, rows, or prices."""

    observed_at: datetime
    expires_at: datetime
    streams: tuple[MarketDataFreshnessStream, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise MarketDataFreshnessRuntimeError("freshness_schema_version_invalid")
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "expires_at", require_utc(self.expires_at, "expires_at"))
        if self.expires_at <= self.observed_at:
            raise MarketDataFreshnessRuntimeError("freshness_expiry_invalid")
        identities = {(stream.collection_mode, stream.stream) for stream in self.streams}
        if not self.streams or len(identities) != len(self.streams):
            raise MarketDataFreshnessRuntimeError("freshness_streams_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": MARKET_DATA_FRESHNESS_RUNTIME_KIND,
            "observed_at": self.observed_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "streams": [stream.to_dict() for stream in self.streams],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MarketDataFreshnessRuntimeSnapshot:
        expected = {"schema_version", "kind", "observed_at", "expires_at", "streams"}
        if (
            not isinstance(payload, Mapping)
            or frozenset(payload) != expected
            or payload["schema_version"] != SCHEMA_VERSION
            or payload["kind"] != MARKET_DATA_FRESHNESS_RUNTIME_KIND
            or not isinstance(payload["streams"], list)
        ):
            raise MarketDataFreshnessRuntimeError("freshness_envelope_invalid")
        return cls(
            observed_at=_utc_datetime(payload["observed_at"], "observed_at"),
            expires_at=_utc_datetime(payload["expires_at"], "expires_at"),
            streams=tuple(MarketDataFreshnessStream.from_dict(item) for item in payload["streams"]),
            schema_version=SCHEMA_VERSION,
        )


@dataclass(frozen=True)
class MarketDataFreshnessRuntimeRead:
    status: Literal["unknown", "available", "unavailable"]
    snapshot: MarketDataFreshnessRuntimeSnapshot | None = None

    def __post_init__(self) -> None:
        if (self.status == "available") != (self.snapshot is not None):
            raise MarketDataFreshnessRuntimeError("freshness_read_invalid")


def write_market_data_freshness_runtime(
    snapshot: MarketDataFreshnessRuntimeSnapshot,
    path: Path,
) -> None:
    """Atomically write the only market-data representation the console reads."""

    payload = json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with staging.open("wb") as handle:
            handle.write(payload)
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)


def read_market_data_freshness_runtime(
    path: Path | None,
    *,
    now: datetime | None = None,
) -> MarketDataFreshnessRuntimeRead:
    """Read only a current, fully validated market-data metadata projection."""

    if path is None or not path.exists():
        return MarketDataFreshnessRuntimeRead(status="unknown")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = MarketDataFreshnessRuntimeSnapshot.from_dict(payload)
        current = require_utc(now or datetime.now(UTC), "now")
        if current < snapshot.observed_at or current >= snapshot.expires_at:
            return MarketDataFreshnessRuntimeRead(status="unavailable")
        return MarketDataFreshnessRuntimeRead(status="available", snapshot=snapshot)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return MarketDataFreshnessRuntimeRead(status="unavailable")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise MarketDataFreshnessRuntimeError(f"freshness_{field_name}_invalid")
    return value


def _count(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise MarketDataFreshnessRuntimeError(f"freshness_{field_name}_invalid")
    return value


def _utc_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise MarketDataFreshnessRuntimeError(f"freshness_{field_name}_invalid")
    try:
        return require_utc(datetime.fromisoformat(value), field_name)
    except ValueError as error:
        raise MarketDataFreshnessRuntimeError(f"freshness_{field_name}_invalid") from error

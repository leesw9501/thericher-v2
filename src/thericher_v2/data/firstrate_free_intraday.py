"""Offline normalization for a hash-bound FirstRate free intraday archive.

The archive contract is intentionally small and explicit: it must contain one
UTF-8 CSV named ``<SYMBOL>.csv`` with the fixed FirstRate OHLCV header.  This
leaf never downloads data, reads environment state, or contacts a provider.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import stat
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CSV_FIELDS, bar_to_record

_EASTERN = ZoneInfo("America/New_York")
_SOURCE_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")
_SOURCE_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
_MAX_DECLARED_CSV_BYTES = 128 * 1024 * 1024
_MAX_DECLARED_EXPANSION_RATIO = 100


@dataclass(frozen=True)
class FirstRateFreeIntradayNormalization:
    """Source-safe aggregates for one deterministic archive normalization."""

    symbol: str
    market: str
    source_entry_name: str
    input_sha256: str
    output_sha256: str
    bar_count: int
    decoded_timestamp_set_sha256: str
    emitted_timestamp_set_sha256: str

    def __post_init__(self) -> None:
        if not _SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("symbol is invalid")
        if not self.market:
            raise ValueError("market is required")
        if self.source_entry_name != f"{self.symbol}.csv":
            raise ValueError("source_entry_name does not match symbol")
        for field_name in ("input_sha256", "output_sha256"):
            _require_sha256(getattr(self, field_name), field_name)
        for field_name in (
            "decoded_timestamp_set_sha256",
            "emitted_timestamp_set_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.bar_count <= 0:
            raise ValueError("bar_count must be positive")
        if self.decoded_timestamp_set_sha256 != self.emitted_timestamp_set_sha256:
            raise ValueError("decoded and emitted timestamp sets must match")


def normalize_firstrate_free_intraday_zip(
    archive_path: Path | str,
    *,
    expected_archive_sha256: str,
    symbol: str,
    output_csv_path: Path | str,
    market: str = "US",
) -> FirstRateFreeIntradayNormalization:
    """Normalize one locally staged FirstRate ZIP into canonical 1m CSV rows.

    The supplied archive is read only after its exact SHA-256 is checked.  CSV
    rows are decoded before any output is published, so invalid input cannot
    produce a partial canonical file.
    """

    requested_symbol = _normalize_symbol(symbol)
    resolved_market = _normalize_market(market)
    expected_hash = _require_sha256(expected_archive_sha256, "expected_archive_sha256")
    source_path = Path(archive_path)
    destination = Path(output_csv_path)
    if source_path.resolve() == destination.resolve():
        raise ValueError("output_csv_path must differ from archive_path")

    archive_bytes = source_path.read_bytes()
    input_sha256 = _sha256(archive_bytes)
    if input_sha256 != expected_hash:
        raise ValueError(
            "archive hash mismatch: "
            f"expected {expected_hash}, observed {input_sha256}"
        )

    source_entry_name = f"{requested_symbol}.csv"
    bars = _decode_archive(
        archive_bytes=archive_bytes,
        symbol=requested_symbol,
        market=resolved_market,
        source_entry_name=source_entry_name,
    )
    decoded_digest = _timestamp_set_sha256(bar.start_ts for bar in bars)
    canonical_csv = _canonical_csv_bytes(bars)
    emitted_timestamps = _emitted_timestamps(canonical_csv)
    emitted_digest = _timestamp_set_sha256(emitted_timestamps)
    if len(emitted_timestamps) != len(bars):
        raise RuntimeError("canonical CSV emitted an unexpected row count")
    if emitted_digest != decoded_digest:
        raise RuntimeError("canonical CSV timestamp set does not match decoded rows")

    _write_bytes_atomically(destination, canonical_csv)
    return FirstRateFreeIntradayNormalization(
        symbol=requested_symbol,
        market=resolved_market,
        source_entry_name=source_entry_name,
        input_sha256=input_sha256,
        output_sha256=_sha256(canonical_csv),
        bar_count=len(bars),
        decoded_timestamp_set_sha256=decoded_digest,
        emitted_timestamp_set_sha256=emitted_digest,
    )


def _decode_archive(
    *,
    archive_bytes: bytes,
    symbol: str,
    market: str,
    source_entry_name: str,
) -> tuple[Bar, ...]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise ValueError("archive must contain exactly one CSV entry")
            member = members[0]
            _validate_archive_member(member, source_entry_name)
            try:
                payload = archive.read(member)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise ValueError("archive CSV entry cannot be read safely") from error
    except zipfile.BadZipFile as error:
        raise ValueError("archive is not a valid ZIP file") from error

    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("archive CSV entry must be UTF-8") from error
    return _decode_source_rows(decoded, symbol=symbol, market=market)


def _validate_archive_member(member: zipfile.ZipInfo, expected_name: str) -> None:
    name = member.filename
    path = PurePosixPath(name)
    mode = member.external_attr >> 16
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or path.name != name
        or any(part in {"", ".", ".."} for part in path.parts)
        or member.is_dir()
        or stat.S_ISLNK(mode)
        or member.flag_bits & 0x1
    ):
        raise ValueError("archive contains an unsafe entry")
    if name != expected_name:
        raise ValueError("archive CSV entry does not match requested symbol")
    compressed_size = max(member.compress_size, 1)
    if (
        member.file_size > _MAX_DECLARED_CSV_BYTES
        or member.file_size > compressed_size * _MAX_DECLARED_EXPANSION_RATIO
    ):
        raise ValueError("archive CSV entry exceeds declared expansion limit")


def _decode_source_rows(
    source_csv: str,
    *,
    symbol: str,
    market: str,
) -> tuple[Bar, ...]:
    reader = csv.DictReader(io.StringIO(source_csv, newline=""))
    if tuple(reader.fieldnames or ()) != _SOURCE_FIELDS:
        raise ValueError("archive CSV header must exactly match FirstRate OHLCV fields")

    bars: list[Bar] = []
    source_timestamps: set[datetime] = set()
    utc_timestamps: set[datetime] = set()
    previous_source_timestamp: datetime | None = None
    previous_utc_timestamp: datetime | None = None
    for row_number, row in enumerate(reader, start=2):
        if row is None or None in row:
            raise ValueError(f"archive CSV row {row_number} has an invalid field count")
        source_timestamp = _parse_source_timestamp(
            _required_source_value(row, "timestamp", row_number), row_number
        )
        if source_timestamp in source_timestamps:
            raise ValueError(f"archive CSV has duplicate timestamps at row {row_number}")
        if (
            previous_source_timestamp is not None
            and source_timestamp <= previous_source_timestamp
        ):
            raise ValueError(
                f"archive CSV timestamps are not strictly increasing at row {row_number}"
            )
        utc_timestamp = _local_timestamp_to_utc(source_timestamp, row_number)
        if utc_timestamp in utc_timestamps:
            raise ValueError(f"archive CSV has duplicate UTC timestamps at row {row_number}")
        if previous_utc_timestamp is not None and utc_timestamp <= previous_utc_timestamp:
            raise ValueError(
                f"archive CSV UTC timestamps are not strictly increasing at row {row_number}"
            )
        try:
            bar = Bar(
                symbol=symbol,
                market=market,
                timeframe=Timeframe.M1,
                start_ts=utc_timestamp,
                open=_decimal_source_value(row, "open", row_number),
                high=_decimal_source_value(row, "high", row_number),
                low=_decimal_source_value(row, "low", row_number),
                close=_decimal_source_value(row, "close", row_number),
                volume=_decimal_source_value(row, "volume", row_number),
                complete=True,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"archive CSV has invalid OHLCV at row {row_number}") from error
        bars.append(bar)
        source_timestamps.add(source_timestamp)
        utc_timestamps.add(utc_timestamp)
        previous_source_timestamp = source_timestamp
        previous_utc_timestamp = utc_timestamp
    if not bars:
        raise ValueError("archive CSV must contain at least one data row")
    return tuple(bars)


def _parse_source_timestamp(value: str, row_number: int) -> datetime:
    try:
        parsed = datetime.strptime(value, _SOURCE_TIMESTAMP_FORMAT)
    except ValueError as error:
        raise ValueError(
            f"archive CSV timestamp is invalid at row {row_number}; "
            f"expected {_SOURCE_TIMESTAMP_FORMAT}"
        ) from error
    if parsed.strftime(_SOURCE_TIMESTAMP_FORMAT) != value:
        raise ValueError(
            f"archive CSV timestamp is invalid at row {row_number}; "
            f"expected {_SOURCE_TIMESTAMP_FORMAT}"
        )
    return parsed


def _local_timestamp_to_utc(local_timestamp: datetime, row_number: int) -> datetime:
    candidates = {
        candidate
        for fold in (0, 1)
        if (candidate := _utc_candidate_for_local_timestamp(local_timestamp, fold))
        is not None
    }
    if len(candidates) != 1:
        raise ValueError(
            "archive CSV timestamp is ambiguous or nonexistent in America/New_York "
            f"at row {row_number}"
        )
    return candidates.pop()


def _utc_candidate_for_local_timestamp(
    local_timestamp: datetime, fold: int
) -> datetime | None:
    localized = local_timestamp.replace(tzinfo=_EASTERN, fold=fold)
    candidate = localized.astimezone(UTC)
    if candidate.astimezone(_EASTERN).replace(tzinfo=None) != local_timestamp:
        return None
    return candidate


def _required_source_value(
    row: dict[str | None, str | list[str] | None], field_name: str, row_number: int
) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"archive CSV {field_name} is required at row {row_number}")
    return value.strip()


def _decimal_source_value(
    row: dict[str | None, str | list[str] | None], field_name: str, row_number: int
) -> Decimal:
    value = _required_source_value(row, field_name, row_number)
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(
            f"archive CSV {field_name} is not decimal at row {row_number}"
        ) from error
    if not result.is_finite():
        raise ValueError(f"archive CSV {field_name} is not finite at row {row_number}")
    return result


def _canonical_csv_bytes(bars: tuple[Bar, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(bar_to_record(bar) for bar in bars)
    return buffer.getvalue().encode("utf-8")


def _emitted_timestamps(canonical_csv: bytes) -> tuple[datetime, ...]:
    reader = csv.DictReader(io.StringIO(canonical_csv.decode("utf-8"), newline=""))
    if tuple(reader.fieldnames or ()) != CSV_FIELDS:
        raise RuntimeError("canonical CSV header is invalid")
    timestamps: list[datetime] = []
    for row_number, row in enumerate(reader, start=2):
        value = row.get("start_ts")
        if not isinstance(value, str):
            raise RuntimeError(f"canonical CSV timestamp is missing at row {row_number}")
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError as error:
            raise RuntimeError(
                f"canonical CSV timestamp is invalid at row {row_number}"
            ) from error
        if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise RuntimeError(f"canonical CSV timestamp is not UTC at row {row_number}")
        timestamps.append(timestamp.astimezone(UTC))
    if len(timestamps) != len(set(timestamps)):
        raise RuntimeError("canonical CSV has duplicate timestamps")
    return tuple(timestamps)


def _timestamp_set_sha256(timestamps: Iterable[datetime]) -> str:
    resolved = tuple(timestamps)
    if len(resolved) != len(set(resolved)):
        raise ValueError("timestamp set contains duplicates")
    payload = "".join(
        f"{timestamp.astimezone(UTC).isoformat()}\n" for timestamp in sorted(resolved)
    ).encode("utf-8")
    return _sha256(payload)


def _write_bytes_atomically(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _normalize_symbol(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("symbol must be str")
    result = value.strip().upper()
    if not _SYMBOL_PATTERN.fullmatch(result):
        raise ValueError("symbol is invalid")
    return result


def _normalize_market(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("market must be str")
    result = value.strip().upper()
    if not result:
        raise ValueError("market is required")
    return result


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")
    return value


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()

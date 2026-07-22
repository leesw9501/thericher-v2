"""Private forward daily-head cache for the KIS Paper SPY receipt lane.

The historical daily cache moves backward. This separate small cache collects a
fresh KIS Paper daily page, drops the current US exchange date before any bytes
are retained, and publishes one hash-attested single-source SPY/AMS snapshot.
It is data-loop infrastructure only: an unavailable head is not a Paper
permission state and callers may use another ready source.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import threading
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

from .kis_market_data import (
    KisPaperDailyQuery,
    KisPaperDailyRawRow,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
)

KIS_PAPER_DAILY_SPY_HEAD_VERSION = "kis-paper-daily-spy-head-v1"
KIS_PAPER_DAILY_SPY_HEAD_ROOT = Path(
    r"D:\market_data\us_equities\kis_paper_private\daily-head\v1"
)
KIS_PAPER_DAILY_SPY_HEAD_INDEX_FILENAME = "index.json"
KIS_PAPER_DAILY_SPY_HEAD_SYMBOL = "SPY"
KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE = "AMS"
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
_HEAD_LOCKS: dict[Path, threading.RLock] = {}
_HEAD_LOCKS_GUARD = threading.Lock()


class KisPaperDailySpyHeadError(RuntimeError):
    """A safe structural failure from the private forward daily-head cache."""


@dataclass(frozen=True)
class KisPaperDailySpyHeadSnapshot:
    """One verified single-source SPY D1 head snapshot without raw row exposure."""

    dataset_id: str
    dataset_hash: str
    index_path: Path
    manifest_path: Path
    collected_at: datetime
    last_session: date
    bars: tuple[Bar, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "collected_at", require_utc(self.collected_at, "collected_at"))
        if not self.dataset_id or not _is_sha256_reference(self.dataset_hash):
            raise ValueError("daily SPY head dataset identity is invalid")
        if len(self.bars) < 2 or self.bars[-1].start_ts.date() != self.last_session:
            raise ValueError("daily SPY head bars are invalid")
        if any(
            bar.symbol != KIS_PAPER_DAILY_SPY_HEAD_SYMBOL
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            for bar in self.bars
        ):
            raise ValueError("daily SPY head bars are invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_spy_head_snapshot",
            "dataset_id": self.dataset_id,
            "dataset_hash": self.dataset_hash,
            "symbol": KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
            "exchange": KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
            "last_session": self.last_session.isoformat(),
            "row_count": len(self.bars),
            "collected_at": _utc_marker(self.collected_at),
            "current_exchange_session_excluded": True,
        }


@dataclass(frozen=True)
class KisPaperDailySpyHeadCollection:
    """Safe summary of one bounded forward collection attempt."""

    status: Literal["collected", "unchanged", "unavailable"]
    observed_at: datetime
    eligible_through_session: date | None
    row_count: int
    snapshot: KisPaperDailySpyHeadSnapshot | None
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.status not in {"collected", "unchanged", "unavailable"}:
            raise ValueError("daily SPY head collection status is invalid")
        if self.row_count < 0:
            raise ValueError("daily SPY head row count is invalid")
        if self.status in {"collected", "unchanged"} and self.snapshot is None:
            raise ValueError("daily SPY head snapshot is required")
        if self.status == "unavailable" and self.reason != "insufficient_completed_rows":
            raise ValueError("daily SPY head unavailable reason is invalid")

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_spy_head_collection",
            "status": self.status,
            "observed_at": _utc_marker(self.observed_at),
            "eligible_through_session": (
                None
                if self.eligible_through_session is None
                else self.eligible_through_session.isoformat()
            ),
            "row_count": self.row_count,
            "reason": self.reason,
            "snapshot": None if self.snapshot is None else self.snapshot.safe_payload(),
            "paper_only": True,
        }


def collect_kis_paper_daily_spy_head_once(
    client: KisPaperMarketDataClient,
    *,
    cache_root: Path = KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    repository_root: Path,
    observed_at: datetime | None = None,
) -> KisPaperDailySpyHeadCollection:
    """Collect and atomically publish one non-current-session SPY/AMS daily head."""

    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    eligible_through = _latest_prior_us_equity_session(observed)
    if eligible_through is None:
        return KisPaperDailySpyHeadCollection(
            status="unavailable",
            observed_at=observed,
            eligible_through_session=None,
            row_count=0,
            snapshot=None,
            reason="insufficient_completed_rows",
        )
    anchor_date = observed.astimezone(US_EQUITY_EASTERN).strftime("%Y%m%d")
    page = client.fetch_daily_raw_page(
        KisPaperDailyQuery(
            symbol=KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
            exchange=KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
            by_date=anchor_date,
        )
    )
    rows = _filter_prior_session_rows(page.rows, eligible_through=eligible_through)
    if (
        not _has_two_consecutive_tail_sessions(rows)
        or not rows
        or _row_date(rows[-1]) != eligible_through
    ):
        return KisPaperDailySpyHeadCollection(
            status="unavailable",
            observed_at=observed,
            eligible_through_session=eligible_through,
            row_count=len(rows),
            snapshot=None,
            reason="insufficient_completed_rows",
        )
    root = _head_root(cache_root=cache_root, repository_root=repository_root)
    raw_payload = _compressed_rows(rows)
    raw_sha256 = _sha256(raw_payload)
    rows_sha256 = _rows_sha256(rows)
    last_session = _row_date(rows[-1])
    with _exclusive_head_lock(root / ".daily_spy_head"):
        index = _read_or_initial_index(root)
        latest = index.get("latest")
        if isinstance(latest, Mapping) and latest.get("raw_sha256") == raw_sha256:
            snapshot = load_verified_kis_paper_daily_spy_head(
                cache_root=root,
                repository_root=repository_root,
            )
            return KisPaperDailySpyHeadCollection(
                status="unchanged",
                observed_at=observed,
                eligible_through_session=eligible_through,
                row_count=len(rows),
                snapshot=snapshot,
            )
        manifest_path, manifest_hash = _write_snapshot(
            root=root,
            observed_at=observed,
            anchor_date=anchor_date,
            eligible_through=eligible_through,
            rows=rows,
            raw_payload=raw_payload,
            raw_sha256=raw_sha256,
            rows_sha256=rows_sha256,
        )
        index = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_daily_spy_head_index",
            "version": KIS_PAPER_DAILY_SPY_HEAD_VERSION,
            "generation": int(index["generation"]) + 1,
            "latest": {
                "manifest_path": manifest_path.relative_to(root).as_posix(),
                "manifest_sha256": manifest_hash,
                "raw_sha256": raw_sha256,
                "rows_sha256": rows_sha256,
                "last_session": last_session.isoformat(),
                "collected_at": _utc_marker(observed),
            },
        }
        _write_index(root=root, index=index)
    snapshot = load_verified_kis_paper_daily_spy_head(
        cache_root=root,
        repository_root=repository_root,
    )
    return KisPaperDailySpyHeadCollection(
        status="collected",
        observed_at=observed,
        eligible_through_session=eligible_through,
        row_count=len(rows),
        snapshot=snapshot,
    )


def load_verified_kis_paper_daily_spy_head(
    *,
    cache_root: Path = KIS_PAPER_DAILY_SPY_HEAD_ROOT,
    repository_root: Path | None = None,
) -> KisPaperDailySpyHeadSnapshot:
    """Load and fully attest the newest private SPY/AMS daily-head snapshot."""

    root = _head_root(cache_root=cache_root, repository_root=repository_root)
    index_path = root / KIS_PAPER_DAILY_SPY_HEAD_INDEX_FILENAME
    try:
        index_payload = index_path.read_bytes()
    except OSError as error:
        raise ValueError("daily SPY head index is unavailable") from error
    index = _json_mapping(index_payload, "daily SPY head index")
    latest = _validated_index(index)
    manifest_path = _safe_child(root, str(latest["manifest_path"]))
    try:
        manifest_payload = manifest_path.read_bytes()
    except OSError as error:
        raise ValueError("daily SPY head manifest is unavailable") from error
    if _sha256(manifest_payload) != latest["manifest_sha256"]:
        raise ValueError("daily SPY head manifest hash is invalid")
    manifest = _json_mapping(manifest_payload, "daily SPY head manifest")
    raw_payload, rows, collected_at, dataset_id, dataset_hash = _validate_manifest_and_rows(
        manifest=manifest,
        manifest_path=manifest_path,
        expected_raw_sha256=str(latest["raw_sha256"]),
        expected_rows_sha256=str(latest["rows_sha256"]),
    )
    if _sha256(raw_payload) != latest["raw_sha256"]:
        raise ValueError("daily SPY head raw hash is invalid")
    last_session = _row_date(rows[-1])
    if latest["last_session"] != last_session.isoformat():
        raise ValueError("daily SPY head last session is invalid")
    bars = tuple(_bar_from_row(row) for row in rows)
    if not _has_two_consecutive_tail_sessions(rows):
        raise ValueError("daily SPY head lacks consecutive sessions")
    return KisPaperDailySpyHeadSnapshot(
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        index_path=index_path,
        manifest_path=manifest_path,
        collected_at=collected_at,
        last_session=last_session,
        bars=bars,
    )


def _latest_prior_us_equity_session(observed_at: datetime) -> date | None:
    current_eastern_date = require_utc(observed_at, "observed_at").astimezone(
        US_EQUITY_EASTERN
    ).date()
    for offset in range(1, 8):
        candidate = current_eastern_date - timedelta(days=offset)
        try:
            session = us_equity_2026_session(candidate)
        except ValueError:
            return None
        if session is not None:
            return session.session_date
    return None


def _filter_prior_session_rows(
    rows: tuple[KisPaperDailyRawRow, ...],
    *,
    eligible_through: date,
) -> tuple[KisPaperDailyRawRow, ...]:
    by_date: dict[date, KisPaperDailyRawRow] = {}
    for row in rows:
        session = _row_date(row)
        if session > eligible_through:
            continue
        prior = by_date.get(session)
        if prior is not None and prior != row:
            raise KisPaperDailySpyHeadError("daily_head_duplicate_conflict")
        by_date[session] = row
    return tuple(by_date[session] for session in sorted(by_date))


def _has_two_consecutive_tail_sessions(rows: tuple[KisPaperDailyRawRow, ...]) -> bool:
    if len(rows) < 2:
        return False
    previous = _row_date(rows[-2])
    current = _row_date(rows[-1])
    try:
        session = us_equity_2026_session(previous + timedelta(days=1))
    except ValueError:
        return False
    if session is not None and session.session_date == current:
        return True
    for offset in range(2, 8):
        try:
            candidate = us_equity_2026_session(previous + timedelta(days=offset))
        except ValueError:
            return False
        if candidate is not None:
            return candidate.session_date == current
    return False


def _write_snapshot(
    *,
    root: Path,
    observed_at: datetime,
    anchor_date: str,
    eligible_through: date,
    rows: tuple[KisPaperDailyRawRow, ...],
    raw_payload: bytes,
    raw_sha256: str,
    rows_sha256: str,
) -> tuple[Path, str]:
    snapshot_name = (
        f"snapshot={observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:12]}-spy-ams-v1"
    )
    target = root / snapshot_name
    staging = root / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        raw_path = staging / "raw" / "ohlcv_daily.csv.gz"
        raw_path.parent.mkdir()
        _write_bytes_and_sync(raw_path, raw_payload)
        dataset_id = f"kis.paper.private.daily.head-v1.{snapshot_name}"
        dataset_hash = _dataset_hash(
            raw_sha256=raw_sha256,
            rows_sha256=rows_sha256,
            first_session=_row_date(rows[0]),
            last_session=_row_date(rows[-1]),
            row_count=len(rows),
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_daily_spy_head_snapshot",
            "version": KIS_PAPER_DAILY_SPY_HEAD_VERSION,
            "dataset_id": dataset_id,
            "dataset_hash": dataset_hash,
            "immutable_snapshot": True,
            "collected_at": _utc_marker(observed_at),
            "source": {
                "provider": "KIS Open API virtual paper",
                "endpoint": "dailyprice",
                "market": "US",
                "symbol": KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
                "exchange": KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
                "adjustment_mode": "MODP=0_unadjusted",
            },
            "collection": {
                "requested_anchor_bymd": anchor_date,
                "current_exchange_session_excluded": True,
                "eligible_through_session": eligible_through.isoformat(),
                "first_retained_session": _row_date(rows[0]).isoformat(),
                "last_retained_session": _row_date(rows[-1]).isoformat(),
                "row_count": len(rows),
                "rows_sha256": rows_sha256,
            },
            "files": {
                "raw_daily_rows": {
                    "path": "raw/ohlcv_daily.csv.gz",
                    "sha256": raw_sha256,
                    "size_bytes": len(raw_payload),
                    "format": "csv.gz",
                    "ordering": "session_date_ascending",
                    "columns": list(_RAW_COLUMNS),
                }
            },
            "storage": {"private_local_only": True, "served": False, "redistributed": False},
            "redaction": {
                "credentials_persisted": False,
                "account_facts_persisted": False,
                "request_headers_persisted": False,
                "response_bodies_persisted": False,
            },
        }
        manifest_payload = (
            json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _write_bytes_and_sync(staging / "manifest.json", manifest_payload)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target / "manifest.json", _sha256(manifest_payload)


def _validate_manifest_and_rows(
    *,
    manifest: Mapping[str, object],
    manifest_path: Path,
    expected_raw_sha256: str,
    expected_rows_sha256: str,
) -> tuple[bytes, tuple[KisPaperDailyRawRow, ...], datetime, str, str]:
    source = manifest.get("source")
    collection = manifest.get("collection")
    files = manifest.get("files")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != "kis_paper_daily_spy_head_snapshot"
        or manifest.get("version") != KIS_PAPER_DAILY_SPY_HEAD_VERSION
        or manifest.get("immutable_snapshot") is not True
        or not isinstance(source, Mapping)
        or not isinstance(collection, Mapping)
        or not isinstance(files, Mapping)
    ):
        raise ValueError("daily SPY head manifest is invalid")
    if source != {
        "provider": "KIS Open API virtual paper",
        "endpoint": "dailyprice",
        "market": "US",
        "symbol": KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
        "exchange": KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
        "adjustment_mode": "MODP=0_unadjusted",
    }:
        raise ValueError("daily SPY head source is invalid")
    if collection.get("current_exchange_session_excluded") is not True:
        raise ValueError("daily SPY head current-session policy is invalid")
    raw = files.get("raw_daily_rows")
    if not isinstance(raw, Mapping):
        raise ValueError("daily SPY head raw document is invalid")
    if (
        raw.get("path") != "raw/ohlcv_daily.csv.gz"
        or raw.get("sha256") != expected_raw_sha256
        or raw.get("format") != "csv.gz"
        or raw.get("ordering") != "session_date_ascending"
        or raw.get("columns") != list(_RAW_COLUMNS)
        or not isinstance(raw.get("size_bytes"), int)
    ):
        raise ValueError("daily SPY head raw document is invalid")
    raw_path = _safe_child(manifest_path.parent, str(raw["path"]))
    try:
        raw_payload = raw_path.read_bytes()
    except OSError as error:
        raise ValueError("daily SPY head raw bytes are unavailable") from error
    if len(raw_payload) != raw["size_bytes"] or _sha256(raw_payload) != expected_raw_sha256:
        raise ValueError("daily SPY head raw bytes are invalid")
    rows = _parse_compressed_rows(raw_payload)
    if not _has_two_consecutive_tail_sessions(rows):
        raise ValueError("daily SPY head rows are invalid")
    first_session = _row_date(rows[0]).isoformat()
    last_session = _row_date(rows[-1]).isoformat()
    if (
        collection.get("first_retained_session") != first_session
        or collection.get("last_retained_session") != last_session
        or collection.get("row_count") != len(rows)
        or collection.get("rows_sha256") != expected_rows_sha256
        or collection.get("eligible_through_session") != last_session
        or _rows_sha256(rows) != expected_rows_sha256
    ):
        raise ValueError("daily SPY head collection identity is invalid")
    collected_at = _parse_utc(manifest.get("collected_at"))
    dataset_id = manifest.get("dataset_id")
    dataset_hash = manifest.get("dataset_hash")
    if not isinstance(dataset_id, str) or not _is_sha256_reference(dataset_hash):
        raise ValueError("daily SPY head dataset identity is invalid")
    expected_dataset_hash = _dataset_hash(
        raw_sha256=expected_raw_sha256,
        rows_sha256=expected_rows_sha256,
        first_session=_row_date(rows[0]),
        last_session=_row_date(rows[-1]),
        row_count=len(rows),
    )
    if dataset_hash != expected_dataset_hash:
        raise ValueError("daily SPY head dataset hash is invalid")
    return raw_payload, rows, collected_at, dataset_id, dataset_hash


def _read_or_initial_index(root: Path) -> dict[str, object]:
    path = root / KIS_PAPER_DAILY_SPY_HEAD_INDEX_FILENAME
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "kis_paper_daily_spy_head_index",
            "version": KIS_PAPER_DAILY_SPY_HEAD_VERSION,
            "generation": 0,
            "latest": None,
        }
    index = _json_mapping(path.read_bytes(), "daily SPY head index")
    _validated_index(index)
    return index


def _validated_index(index: Mapping[str, object]) -> Mapping[str, object]:
    if (
        index.get("schema_version") != SCHEMA_VERSION
        or index.get("kind") != "kis_paper_daily_spy_head_index"
        or index.get("version") != KIS_PAPER_DAILY_SPY_HEAD_VERSION
        or not isinstance(index.get("generation"), int)
        or int(index["generation"]) < 1
        or not isinstance(index.get("latest"), Mapping)
    ):
        raise ValueError("daily SPY head index is invalid")
    latest = index["latest"]
    if (
        not isinstance(latest.get("manifest_path"), str)
        or not _is_sha256_reference(latest.get("manifest_sha256"))
        or not _is_sha256_reference(latest.get("raw_sha256"))
        or not _is_sha256_reference(latest.get("rows_sha256"))
        or not _is_iso_date(latest.get("last_session"))
    ):
        raise ValueError("daily SPY head index is invalid")
    _parse_utc(latest.get("collected_at"))
    return latest


def _write_index(*, root: Path, index: Mapping[str, object]) -> None:
    _validated_index(index)
    payload = (json.dumps(index, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    target = root / KIS_PAPER_DAILY_SPY_HEAD_INDEX_FILENAME
    staging = root / f".{target.name}.{uuid.uuid4().hex}.stage"
    try:
        _write_bytes_and_sync(staging, payload)
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)


def _head_root(*, cache_root: Path, repository_root: Path | None) -> Path:
    root = Path(cache_root)
    if root.is_symlink():
        raise ValueError("daily SPY head cache root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    resolved = root.resolve()
    if repository_root is not None:
        repository = Path(repository_root).resolve()
        mounted_root = repository / "market_data"
        mounted_market_data = mounted_root.is_mount() and resolved.is_relative_to(mounted_root)
        if resolved.is_relative_to(repository) and not mounted_market_data:
            raise ValueError("daily SPY head cache root must stay outside Git")
    return resolved


@contextmanager
def _exclusive_head_lock(path: Path) -> Iterator[None]:
    resolved = path.resolve()
    with _HEAD_LOCKS_GUARD:
        lock = _HEAD_LOCKS.setdefault(resolved, threading.RLock())
    with lock:
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _compressed_rows(rows: tuple[KisPaperDailyRawRow, ...]) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=_RAW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "symbol": KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
                "exchange": KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
                "session_date": _row_date(row).isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.clos,
                "volume": row.tvol,
            }
        )
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as handle:
        handle.write(text.getvalue().encode("utf-8"))
    return buffer.getvalue()


def _parse_compressed_rows(payload: bytes) -> tuple[KisPaperDailyRawRow, ...]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
            reader = csv.DictReader(io.StringIO(handle.read().decode("utf-8"), newline=""))
            if tuple(reader.fieldnames or ()) != _RAW_COLUMNS:
                raise ValueError("daily SPY head raw columns are invalid")
            raw_rows = list(reader)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("daily SPY head raw contents are invalid") from error
    rows: list[KisPaperDailyRawRow] = []
    for raw in raw_rows:
        if raw.get("symbol") != KIS_PAPER_DAILY_SPY_HEAD_SYMBOL or raw.get(
            "exchange"
        ) != KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE:
            raise ValueError("daily SPY head raw scope is invalid")
        try:
            rows.append(
                KisPaperDailyRawRow(
                    xymd=_compact_date(raw.get("session_date")),
                    open=_text(raw.get("open")),
                    high=_text(raw.get("high")),
                    low=_text(raw.get("low")),
                    clos=_text(raw.get("close")),
                    tvol=_text(raw.get("volume")),
                )
            )
        except (KisPaperMarketDataError, TypeError, ValueError) as error:
            raise ValueError("daily SPY head raw contents are invalid") from error
    if not rows or tuple(_row_date(row) for row in rows) != tuple(
        sorted(_row_date(row) for row in rows)
    ):
        raise ValueError("daily SPY head raw ordering is invalid")
    if len({_row_date(row) for row in rows}) != len(rows):
        raise ValueError("daily SPY head raw rows are duplicated")
    return tuple(rows)


def _bar_from_row(row: KisPaperDailyRawRow) -> Bar:
    session = _row_date(row)
    return Bar(
        symbol=KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=Decimal(row.open),
        high=Decimal(row.high),
        low=Decimal(row.low),
        close=Decimal(row.clos),
        volume=Decimal(row.tvol),
        complete=True,
    )


def _rows_sha256(rows: tuple[KisPaperDailyRawRow, ...]) -> str:
    payload = [row.as_document() for row in rows]
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return _sha256(encoded)


def _dataset_hash(
    *,
    raw_sha256: str,
    rows_sha256: str,
    first_session: date,
    last_session: date,
    row_count: int,
) -> str:
    return _sha256(
        json.dumps(
            {
                "kind": KIS_PAPER_DAILY_SPY_HEAD_VERSION,
                "source": {
                    "symbol": KIS_PAPER_DAILY_SPY_HEAD_SYMBOL,
                    "exchange": KIS_PAPER_DAILY_SPY_HEAD_EXCHANGE,
                    "adjustment_mode": "MODP=0_unadjusted",
                },
                "raw_sha256": raw_sha256,
                "rows_sha256": rows_sha256,
                "first_session": first_session.isoformat(),
                "last_session": last_session.isoformat(),
                "row_count": row_count,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _row_date(row: KisPaperDailyRawRow) -> date:
    return datetime.strptime(row.xymd, "%Y%m%d").date()


def _compact_date(value: object) -> str:
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError("daily SPY head date is invalid")
    compact = value.replace("-", "")
    datetime.strptime(compact, "%Y%m%d")
    return compact


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("daily SPY head value is invalid")
    return value.strip()


def _safe_child(root: Path, relative: str) -> Path:
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError("daily SPY head path is invalid")
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise ValueError("daily SPY head path is invalid") from error
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("daily SPY head path is invalid")
    return resolved


def _json_mapping(payload: bytes, label: str) -> dict[str, object]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} is invalid")
    return decoded


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("daily SPY head timestamp is invalid")
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "collected_at")
    except (TypeError, ValueError) as error:
        raise ValueError("daily SPY head timestamp is invalid") from error


def _is_sha256_reference(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _utc_marker(value: datetime) -> str:
    return require_utc(value).isoformat().replace("+00:00", "Z")


def _write_bytes_and_sync(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())

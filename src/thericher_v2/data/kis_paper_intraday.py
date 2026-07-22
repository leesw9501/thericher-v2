"""Offline loader for the private KIS Paper 1m cache."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from thericher_v2.contracts import Bar, Timeframe, require_utc
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.resample import SessionResampleResult, SessionWindow, resample_session_bars
from thericher_v2.execution.kis_market_data import KisPaperMinuteRawBar
from thericher_v2.execution.kis_private_intraday_backfill import (
    KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION,
    KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME,
    KisPaperPrivateIntradayTarget,
)

_KOREA_TZ = ZoneInfo("Asia/Seoul")
_RAW_MINUTE_COLUMNS = frozenset(
    {"xymd", "xhms", "kymd", "khms", "open", "high", "low", "last", "evol"}
)


def load_verified_kis_paper_private_intraday_catalog(
    *,
    cache_root: Path,
    repo_root: Path,
    symbol: str,
    exchange: str,
) -> CatalogedBars:
    """Load one KIS-native stream without credentials, network, or source mixing."""

    target = KisPaperPrivateIntradayTarget(symbol=symbol, exchange=exchange)
    root = _external_backfill_root(cache_root=cache_root, repo_root=repo_root)
    index_path = root / KIS_PAPER_PRIVATE_INTRADAY_INDEX_FILENAME
    index_bytes = _read_bytes(index_path, "private intraday index is invalid")
    index = _decode_json(index_bytes, "private intraday index is invalid")
    target_state = _target_state(index=index, target=target)
    chunks = target_state.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("private intraday index is invalid")

    bars_by_start: dict[datetime, tuple[Bar, str]] = {}
    lineage: list[dict[str, str]] = []
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("private intraday index is invalid")
        # A false value means this particular chunk has no usable file. It is
        # not a collection permission switch and cannot block later work.
        if chunk.get("raw_market_data_retained") is not True:
            continue
        if chunk.get("outcome") not in {"committed", "partial"}:
            raise ValueError("private intraday index is invalid")
        manifest_path, manifest_hash, raw_hash = _chunk_paths(root=root, chunk=chunk)
        manifest_bytes = _read_bytes(manifest_path, "private intraday manifest is invalid")
        if _sha256(manifest_bytes) != manifest_hash:
            raise ValueError("private intraday manifest hash mismatch")
        manifest = _decode_json(manifest_bytes, "private intraday manifest is invalid")
        raw_relative, manifest_raw_hash = _validate_manifest(
            manifest=manifest,
            target=target,
            chunk=chunk,
        )
        if manifest_raw_hash != raw_hash:
            raise ValueError("private intraday raw hash mismatch")
        raw_path = _resolve_child(root=manifest_path.parent, relative=raw_relative)
        raw_bytes = _read_bytes(raw_path, "private intraday raw file is invalid")
        if _sha256(raw_bytes) != raw_hash:
            raise ValueError("private intraday raw hash mismatch")
        collected_at = _manifest_collected_at(manifest)
        raw_bars = tuple(_raw_bar_from_record(record) for record in _decode_raw_rows(raw_bytes))
        _attest_chunk_rows(chunk=chunk, raw_bars=raw_bars)
        for raw_bar in raw_bars:
            start_ts = _korea_timestamp_to_utc(raw_bar)
            bar = Bar(
                symbol=target.symbol,
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start_ts,
                open=raw_bar.open,
                high=raw_bar.high,
                low=raw_bar.low,
                close=raw_bar.last,
                volume=raw_bar.volume,
                complete=raw_bar_end_is_complete(
                    start_ts=start_ts,
                    collected_at=collected_at,
                ),
            )
            fingerprint = _raw_row_fingerprint(raw_bar)
            prior = bars_by_start.get(start_ts)
            if prior is None:
                bars_by_start[start_ts] = (bar, fingerprint)
            elif prior[1] != fingerprint:
                raise ValueError("private intraday cache has conflicting overlap rows")
        lineage.append({"manifest_hash": manifest_hash, "raw_sha256": raw_hash})

    if not bars_by_start:
        raise ValueError("private intraday cache has no retained bars")
    bars = tuple(bar for _, (bar, _) in sorted(bars_by_start.items()))
    return _cataloged_bars_from_verified_loader(
        dataset_id=(
            "kis.paper.private.intraday."
            f"{target.symbol.lower()}.{target.exchange.lower()}.m1.{KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION}"
        ),
        dataset_hash=_dataset_hash(index_bytes=index_bytes, lineage=lineage),
        source_path=index_path,
        bars=bars,
    )


def slice_verified_kis_paper_private_intraday_catalog(
    catalog: CatalogedBars,
    *,
    session: SessionWindow,
) -> CatalogedBars:
    """Derive one hash-bound session slice without reopening the KIS cache."""

    if not isinstance(catalog, CatalogedBars):
        raise TypeError("private intraday session requires CatalogedBars")
    if any(bar.timeframe != Timeframe.M1 for bar in catalog.bars):
        raise ValueError("private intraday cache must contain 1m bars")
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.open_ts and bar.end_ts <= session.close_ts
    )
    if not bars:
        raise ValueError("private intraday session has no source bars")
    return _cataloged_bars_from_verified_loader(
        dataset_id=(
            f"{catalog.dataset_id}:session-"
            f"{session.open_ts.strftime('%Y%m%dT%H%MZ')}-"
            f"{session.close_ts.strftime('%Y%m%dT%H%MZ')}"
        ),
        dataset_hash=_session_dataset_hash(catalog=catalog, session=session),
        source_path=catalog.source_path,
        bars=bars,
    )


def require_complete_kis_paper_private_intraday_session(
    catalog: CatalogedBars,
    *,
    session: SessionWindow,
) -> CatalogedBars:
    """Return a session slice only when every expected 1m source bar is present."""

    sliced = slice_verified_kis_paper_private_intraday_catalog(catalog, session=session)
    if session.duration % Timeframe.M1.duration:
        raise ValueError("private intraday session must align to one-minute bars")
    expected_starts = tuple(
        session.open_ts + Timeframe.M1.duration * index
        for index in range(session.duration // Timeframe.M1.duration)
    )
    if (
        len(sliced.bars) != len(expected_starts)
        or not all(bar.complete for bar in sliced.bars)
        or tuple(bar.start_ts for bar in sliced.bars) != expected_starts
    ):
        raise ValueError("private intraday session is incomplete")
    return sliced


def resample_verified_kis_paper_private_intraday_catalog(
    catalog: CatalogedBars,
    *,
    timeframe: Timeframe,
    session: SessionWindow,
) -> SessionResampleResult:
    """Resample a verified 1m stream within a caller-declared session."""

    sliced = slice_verified_kis_paper_private_intraday_catalog(catalog, session=session)
    return resample_session_bars(sliced.bars, timeframe, session=session)


def raw_bar_end_is_complete(*, start_ts: datetime, collected_at: datetime) -> bool:
    """Fail closed for a minute that could still have been forming at collection."""

    start = require_utc(start_ts, "start_ts")
    collection_minute = require_utc(collected_at, "collected_at").replace(second=0, microsecond=0)
    return start + Timeframe.M1.duration <= collection_minute


def _external_backfill_root(*, cache_root: Path, repo_root: Path) -> Path:
    root = Path(cache_root).resolve()
    if root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("private intraday cache root must stay outside Git")
    backfill = root / KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    if backfill.is_symlink():
        raise ValueError("private intraday cache root is invalid")
    return backfill.resolve()


def _target_state(
    *, index: Mapping[str, object], target: KisPaperPrivateIntradayTarget
) -> Mapping[str, object]:
    if (
        index.get("kind") != "kis_paper_private_intraday_backfill"
        or index.get("backfill_version") != KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    ):
        raise ValueError("private intraday index is invalid")
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise ValueError("private intraday index is invalid")
    matches = [
        state
        for state in targets
        if isinstance(state, Mapping) and state.get("target_key") == target.target_key
    ]
    if len(matches) != 1:
        raise ValueError("private intraday index target is missing")
    state = matches[0]
    if state.get("symbol") != target.symbol or state.get("exchange") != target.exchange:
        raise ValueError("private intraday index is invalid")
    return state


def _chunk_paths(*, root: Path, chunk: Mapping[str, object]) -> tuple[Path, str, str]:
    manifest_relative = chunk.get("manifest_path")
    manifest_hash = chunk.get("manifest_hash")
    raw_hash = chunk.get("raw_sha256")
    if (
        not isinstance(manifest_relative, str)
        or not _is_sha256(manifest_hash)
        or not _is_sha256(raw_hash)
    ):
        raise ValueError("private intraday index is invalid")
    return _resolve_child(root=root, relative=manifest_relative), manifest_hash, raw_hash


def _validate_manifest(
    *,
    manifest: Mapping[str, object],
    target: KisPaperPrivateIntradayTarget,
    chunk: Mapping[str, object],
) -> tuple[str, str]:
    if (
        manifest.get("kind") != "kis_paper_private_intraday_cache"
        or manifest.get("backfill_version") != KIS_PAPER_PRIVATE_INTRADAY_BACKFILL_VERSION
    ):
        raise ValueError("private intraday manifest is invalid")
    source = manifest.get("source")
    timestamp_contract = manifest.get("timestamp_contract")
    if (
        not isinstance(source, Mapping)
        or source.get("provider") != "KIS Open API virtual paper"
        or source.get("endpoint") != "inquire-time-itemchartprice"
        or source.get("symbol") != target.symbol
        or source.get("exchange") != target.exchange
        or source.get("bar_interval") != "1m"
        or not isinstance(timestamp_contract, Mapping)
        or timestamp_contract.get("canonical_basis") != "korea_timestamp"
        or timestamp_contract.get("timezone") != "Asia/Seoul"
        or timestamp_contract.get("exchange_timestamp_semantics") != "observed_unqualified"
    ):
        raise ValueError("private intraday manifest is invalid")
    start_policy = timestamp_contract.get("canonical_start_policy")
    completion_rule = timestamp_contract.get("completed_bar_rule")
    if (
        start_policy == "korea_timestamp_projected_to_utc"
        and completion_rule == "source_timestamp_plus_1m_at_or_before_collection_minute"
    ):
        pass
    elif start_policy is None and completion_rule == "bar_end_at_or_before_collection_minute":
        # The first retained v1 snapshots used this equivalent, less explicit
        # spelling before the canonical-start policy was added to the manifest.
        pass
    else:
        raise ValueError("private intraday manifest is invalid")
    files = manifest.get("files")
    raw = files.get("raw_minute_rows") if isinstance(files, Mapping) else None
    if (
        not isinstance(raw, Mapping)
        or not isinstance(raw.get("path"), str)
        or not _is_sha256(raw.get("sha256"))
        or raw.get("format") != "csv.gz"
        or set(raw.get("columns", ())) != _RAW_MINUTE_COLUMNS
    ):
        raise ValueError("private intraday manifest is invalid")
    backfill = manifest.get("backfill")
    index_chunk = backfill.get("index_chunk") if isinstance(backfill, Mapping) else None
    if (
        not isinstance(index_chunk, Mapping)
        or index_chunk.get("chunk_key") != chunk.get("chunk_key")
    ):
        raise ValueError("private intraday manifest is invalid")
    for field in (
        "outcome",
        "input_cursor",
        "output_cursor",
        "raw_sha256",
        "raw_market_data_retained",
        "row_count",
        "row_fingerprints",
        "exact_overlap_rows",
        "conflicting_overlap_rows",
        "collected_at_utc",
        "reason",
    ):
        if index_chunk.get(field) != chunk.get(field):
            raise ValueError("private intraday manifest is invalid")
    return str(raw["path"]), str(raw["sha256"])


def _manifest_collected_at(manifest: Mapping[str, object]) -> datetime:
    value = manifest.get("collected_at_utc")
    if not isinstance(value, str):
        raise ValueError("private intraday manifest is invalid")
    try:
        return require_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "collected_at")
    except ValueError as error:
        raise ValueError("private intraday manifest is invalid") from error


def _decode_raw_rows(raw_bytes: bytes) -> tuple[dict[str, str], ...]:
    try:
        with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if set(reader.fieldnames or ()) != _RAW_MINUTE_COLUMNS:
                raise ValueError("private intraday raw columns are invalid")
            rows = tuple(dict(row) for row in reader)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("private intraday raw file is invalid") from error
    if not rows:
        raise ValueError("private intraday raw file is invalid")
    return rows


def _raw_bar_from_record(record: Mapping[str, str]) -> KisPaperMinuteRawBar:
    if set(record) != _RAW_MINUTE_COLUMNS:
        raise ValueError("private intraday raw row is invalid")
    try:
        return KisPaperMinuteRawBar(
            exchange_date=record["xymd"],
            exchange_time=record["xhms"],
            korea_date=record["kymd"],
            korea_time=record["khms"],
            open=Decimal(record["open"]),
            high=Decimal(record["high"]),
            low=Decimal(record["low"]),
            last=Decimal(record["last"]),
            volume=Decimal(record["evol"]),
        )
    except (KeyError, ValueError, ArithmeticError) as error:
        raise ValueError("private intraday raw row is invalid") from error


def _korea_timestamp_to_utc(row: KisPaperMinuteRawBar) -> datetime:
    try:
        local = datetime.strptime(
            f"{row.korea_date}{row.korea_time}", "%Y%m%d%H%M%S"
        ).replace(tzinfo=_KOREA_TZ)
    except ValueError as error:
        raise ValueError("private intraday Korea timestamp is invalid") from error
    return local.astimezone(UTC)


def _raw_row_fingerprint(row: KisPaperMinuteRawBar) -> str:
    payload = json.dumps(row.as_document(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(payload)


def _attest_chunk_rows(
    *,
    chunk: Mapping[str, object],
    raw_bars: tuple[KisPaperMinuteRawBar, ...],
) -> None:
    expected_row_count = chunk.get("row_count")
    expected_fingerprints = chunk.get("row_fingerprints")
    if (
        type(expected_row_count) is not int
        or expected_row_count <= 0
        or not isinstance(expected_fingerprints, Mapping)
    ):
        raise ValueError("private intraday index is invalid")
    observed_fingerprints = {
        f"{row.korea_date}T{row.korea_time}": _raw_row_fingerprint(row)
        for row in raw_bars
    }
    if (
        len(raw_bars) != expected_row_count
        or len(observed_fingerprints) != len(raw_bars)
        or dict(expected_fingerprints) != observed_fingerprints
    ):
        raise ValueError("private intraday committed chunk drift")


def _dataset_hash(*, index_bytes: bytes, lineage: list[dict[str, str]]) -> str:
    payload = json.dumps(
        {
            "index_sha256": _sha256(index_bytes),
            "lineage": sorted(
                lineage,
                key=lambda item: (item["manifest_hash"], item["raw_sha256"]),
            ),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256(payload)


def _session_dataset_hash(*, catalog: CatalogedBars, session: SessionWindow) -> str:
    payload = json.dumps(
        {
            "kind": "kis_paper_private_intraday_session_slice_v1",
            "parent_dataset_id": catalog.dataset_id,
            "parent_dataset_hash": catalog.dataset_hash,
            "session_open_utc": session.open_ts.isoformat(),
            "session_close_utc": session.close_ts.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256(payload)


def _read_bytes(path: Path, reason: str) -> bytes:
    if path.is_symlink():
        raise ValueError(reason)
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError(reason) from error


def _decode_json(value: bytes, reason: str) -> dict[str, object]:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(reason) from error
    if not isinstance(decoded, dict):
        raise ValueError(reason)
    return decoded


def _resolve_child(*, root: Path, relative: str) -> Path:
    if not relative:
        raise ValueError("private intraday cache path is invalid")
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError("private intraday cache path is invalid")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("private intraday cache path is invalid")
    return resolved


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


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

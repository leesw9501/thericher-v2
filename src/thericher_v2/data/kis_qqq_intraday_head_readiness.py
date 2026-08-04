"""Metadata-only readiness receipts for fresh QQQ intraday research windows.

The observer reads only the retained index and its row fingerprints.  It never
opens raw bars, calls a provider, loads credentials, fits a model, or creates
an execution input.  Its one job is to make a newly collected, time-disjoint
90-observation plus 10-future-minute window auditable before a later campaign
chooses whether to consume it.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.research.artifact_paths import ensure_external_artifact_directory

from .kis_paper_intraday_index_metadata import (
    KisPaperPrivateIntradayV1RetainedChunkMetadata,
    sha256_kis_paper_private_intraday_v1_index_bytes,
    validate_kis_paper_private_intraday_v1_index_metadata,
)
from .us_equity_session import us_equity_2026_session

KIS_QQQ_INTRADAY_HEAD_READINESS_KIND = "kis_qqq_intraday_head_readiness"
KIS_QQQ_INTRADAY_HEAD_READINESS_ARTIFACT_DIRECTORY = "runs"
KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET = "QQQ/NAS/1m"
KIS_QQQ_INTRADAY_HEAD_READINESS_CACHE_VERSION = "v1"
KIS_QQQ_INTRADAY_HEAD_READINESS_INDEX_FILENAME = "index.json"
KIS_QQQ_INTRADAY_HEAD_READINESS_CUTOFF = date(2026, 7, 21)
KIS_QQQ_INTRADAY_HEAD_READINESS_FEATURE_BAR_COUNT = 90
KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET_BAR_COUNT = 10
KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_START_OFFSET = 260
KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_END_OFFSET = 359

_EXPECTED_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
_QQQ_TARGET_KEY = KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_EASTERN_TZ = ZoneInfo("America/New_York")

ReadinessStatus = Literal["observed", "duplicate", "input_unavailable", "contaminated"]


@dataclass(frozen=True, slots=True)
class KisQqqIntradayHeadReadiness:
    """One source-safe outcome for an exact collector interval."""

    status: ReadinessStatus
    reason: str | None
    index_metadata_sha256: str | None
    selected_chunk_count: int
    session_date: date | None = None
    session_key_sha256: str | None = None
    source_commitment_sha256: str | None = None
    evidence_path: Path | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"observed", "duplicate", "input_unavailable", "contaminated"}:
            raise ValueError("QQQ readiness status is invalid")
        if self.reason is not None and (
            not self.reason
            or not self.reason.isascii()
            or not self.reason.replace("_", "").isalnum()
        ):
            raise ValueError("QQQ readiness reason is invalid")
        if self.selected_chunk_count < 0:
            raise ValueError("QQQ readiness selected chunk count is invalid")
        if self.session_date is not None and type(self.session_date) is not date:
            raise ValueError("QQQ readiness session date is invalid")
        for value in (
            self.index_metadata_sha256,
            self.session_key_sha256,
            self.source_commitment_sha256,
        ):
            if value is not None and not _is_sha256(value):
                raise ValueError("QQQ readiness hash is invalid")
        if self.status in {"observed", "duplicate"} and (
            self.session_date is None
            or self.session_key_sha256 is None
            or self.source_commitment_sha256 is None
        ):
            raise ValueError("QQQ readiness qualified outcome is incomplete")
        if self.evidence_path is not None and self.evidence_path.suffix != ".json":
            raise ValueError("QQQ readiness evidence path is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return only data-lineage categories and hashes, never rows or paths."""

        return {
            "schema_version": self.schema_version,
            "kind": KIS_QQQ_INTRADAY_HEAD_READINESS_KIND,
            "status": self.status,
            "reason": self.reason,
            "source": {
                "provider_route": "kis_paper_market_data",
                "target": KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET,
                "collection_scope": "head",
                "index_metadata_sha256": self.index_metadata_sha256,
                "selected_chunk_count": self.selected_chunk_count,
            },
            "prospective_window": {
                "historical_cutoff": KIS_QQQ_INTRADAY_HEAD_READINESS_CUTOFF.isoformat(),
                "session_date": (
                    None if self.session_date is None else self.session_date.isoformat()
                ),
                "session_key_sha256": self.session_key_sha256,
                "source_commitment_sha256": self.source_commitment_sha256,
                "completed_m1_feature_bar_count": (
                    KIS_QQQ_INTRADAY_HEAD_READINESS_FEATURE_BAR_COUNT
                ),
                "future_m1_target_bar_count": KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET_BAR_COUNT,
                "window_start_offset": KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_START_OFFSET,
                "window_end_offset": KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_END_OFFSET,
            },
            "limits": {
                "raw_market_data_opened": False,
                "network_access": False,
                "credentials_read": False,
                "model_fit": False,
                "gpu_used": False,
                "paper_execution": False,
                "target_or_return_opened": False,
            },
        }


@dataclass(frozen=True, slots=True)
class _RowMetadata:
    fingerprint: str
    complete: bool


@dataclass(frozen=True, slots=True)
class _QualifiedWindow:
    session_date: date
    session_key_sha256: str
    source_commitment_sha256: str


def observe_kis_paper_qqq_intraday_head_readiness(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    repository_root: Path | str,
    collection_started_at: datetime,
    collector_returned_at: datetime,
) -> KisQqqIntradayHeadReadiness:
    """Observe one collection interval without exposing a raw market-data row.

    An interval may be retried safely.  A qualified window becomes immutable
    under the external artifact root; a changed commitment for the same session
    is contamination, never an overwrite.
    """

    started = require_utc(collection_started_at, "collection_started_at")
    returned = require_utc(collector_returned_at, "collector_returned_at")
    if returned < started:
        raise ValueError("QQQ readiness collector interval is invalid")
    index_bytes, chunks = _load_interval_chunks(
        cache_root=Path(cache_root),
        repository_root=Path(repository_root),
        collection_started_at=started,
        collector_returned_at=returned,
    )
    if index_bytes is None:
        return _result(status="input_unavailable", reason="index_not_created")
    index_hash = sha256_kis_paper_private_intraday_v1_index_bytes(index_bytes)
    if not chunks:
        return _result(
            status="input_unavailable",
            reason="current_head_chunks_unavailable",
            index_metadata_sha256=index_hash,
        )
    rows, conflict = _rows_from_chunks(chunks)
    if conflict:
        return _persist_contamination(
            reason="fingerprint_metadata_conflict",
            artifact_root=Path(artifact_root),
            repository_root=Path(repository_root),
            index_metadata_sha256=index_hash,
            selected_chunk_count=len(chunks),
        )
    windows, calendar_unavailable = _qualified_windows(rows)
    if calendar_unavailable:
        return _result(
            status="input_unavailable",
            reason="session_calendar_unavailable",
            index_metadata_sha256=index_hash,
            selected_chunk_count=len(chunks),
        )
    historical = [
        window
        for window in windows
        if window.session_date <= KIS_QQQ_INTRADAY_HEAD_READINESS_CUTOFF
    ]
    if historical:
        return _persist_contamination(
            reason="historical_overlap",
            artifact_root=Path(artifact_root),
            repository_root=Path(repository_root),
            index_metadata_sha256=index_hash,
            selected_chunk_count=len(chunks),
            window=historical[0],
        )
    prospective = [
        window
        for window in windows
        if window.session_date > KIS_QQQ_INTRADAY_HEAD_READINESS_CUTOFF
    ]
    if not prospective:
        return _result(
            status="input_unavailable",
            reason="complete_window_unavailable",
            index_metadata_sha256=index_hash,
            selected_chunk_count=len(chunks),
        )
    if len(prospective) != 1:
        return _result(
            status="input_unavailable",
            reason="multiple_complete_windows",
            index_metadata_sha256=index_hash,
            selected_chunk_count=len(chunks),
        )
    return _persist_qualified_window(
        window=prospective[0],
        artifact_root=Path(artifact_root),
        repository_root=Path(repository_root),
        index_metadata_sha256=index_hash,
        selected_chunk_count=len(chunks),
    )


def _load_interval_chunks(
    *,
    cache_root: Path,
    repository_root: Path,
    collection_started_at: datetime,
    collector_returned_at: datetime,
) -> tuple[bytes | None, tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...]]:
    root = _external_cache_root(cache_root=cache_root, repository_root=repository_root)
    version_root = root / KIS_QQQ_INTRADAY_HEAD_READINESS_CACHE_VERSION
    if version_root.is_symlink():
        raise ValueError("QQQ readiness cache root is invalid")
    index_path = version_root / KIS_QQQ_INTRADAY_HEAD_READINESS_INDEX_FILENAME
    if not index_path.exists():
        return None, ()
    if index_path.is_symlink():
        raise ValueError("QQQ readiness index is invalid")
    try:
        index_bytes = index_path.read_bytes()
        decoded = json.loads(index_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("QQQ readiness index is invalid") from error
    if not isinstance(decoded, Mapping):
        raise ValueError("QQQ readiness index is invalid")
    try:
        metadata = validate_kis_paper_private_intraday_v1_index_metadata(
            decoded,
            expected_targets=_EXPECTED_TARGETS,
        )
    except ValueError as error:
        raise ValueError("QQQ readiness index is invalid") from error
    target = [target for target in metadata.targets if target.target_key == _QQQ_TARGET_KEY]
    if len(target) != 1:
        raise ValueError("QQQ readiness target is invalid")
    chunks = tuple(
        chunk
        for chunk in target[0].retained_chunks
        if chunk.collection_scope == "head"
        and collection_started_at <= chunk.collected_at <= collector_returned_at
    )
    return index_bytes, chunks


def _external_cache_root(*, cache_root: Path, repository_root: Path) -> Path:
    requested = cache_root.absolute()
    if _has_existing_symlink_component(requested):
        raise ValueError("QQQ readiness cache root is invalid")
    root = requested.resolve(strict=False)
    repository = repository_root.resolve(strict=False)
    docker_repository = Path("/app").resolve(strict=False)
    docker_market_data = docker_repository / "market_data"
    mounted_market_data = (
        repository == docker_repository and root.is_relative_to(docker_market_data)
    )
    if root.is_relative_to(repository) and not mounted_market_data:
        raise ValueError("QQQ readiness cache root must stay outside Git")
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError("QQQ readiness cache root is invalid")
    return root


def _rows_from_chunks(
    chunks: Sequence[KisPaperPrivateIntradayV1RetainedChunkMetadata],
) -> tuple[dict[str, _RowMetadata], bool]:
    rows: dict[str, _RowMetadata] = {}
    conflict = False
    for chunk in sorted(chunks, key=lambda item: (item.collected_at, item.chunk_key)):
        if chunk.candidate_batch_conflicted:
            continue
        for row_key, fingerprint in chunk.rows:
            complete = _minute_is_complete(row_key=row_key, collected_at=chunk.collected_at)
            previous = rows.get(row_key)
            if previous is None:
                rows[row_key] = _RowMetadata(fingerprint=fingerprint, complete=complete)
            elif previous.fingerprint != fingerprint:
                conflict = True
            elif complete and not previous.complete:
                rows[row_key] = _RowMetadata(fingerprint=fingerprint, complete=True)
    return rows, conflict


def _qualified_windows(
    rows: Mapping[str, _RowMetadata],
) -> tuple[tuple[_QualifiedWindow, ...], bool]:
    session_dates: set[date] = set()
    calendar_unavailable = False
    for row_key in rows:
        session_date = _korea_timestamp_to_utc(row_key).astimezone(_EASTERN_TZ).date()
        try:
            session = us_equity_2026_session(session_date)
        except ValueError:
            calendar_unavailable = True
            continue
        if session is not None and session.kind == "regular":
            session_dates.add(session_date)
    qualified: list[_QualifiedWindow] = []
    for session_date in sorted(session_dates):
        session = us_equity_2026_session(session_date)
        assert session is not None and session.kind == "regular"
        expected = tuple(
            _korea_timestamp_key(session.window.open_ts + timedelta(minutes=offset))
            for offset in range(
                KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_START_OFFSET,
                KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_END_OFFSET + 1,
            )
        )
        if not all(row_key in rows and rows[row_key].complete for row_key in expected):
            continue
        fingerprints = {row_key: rows[row_key].fingerprint for row_key in expected}
        qualified.append(
            _QualifiedWindow(
                session_date=session_date,
                session_key_sha256=_sha256_text(
                    f"{KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET}:{session_date.isoformat()}"
                ),
                source_commitment_sha256=_sha256_payload(
                    {
                        "target": KIS_QQQ_INTRADAY_HEAD_READINESS_TARGET,
                        "session_date": session_date.isoformat(),
                        "window_start_offset": KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_START_OFFSET,
                        "window_end_offset": KIS_QQQ_INTRADAY_HEAD_READINESS_WINDOW_END_OFFSET,
                        "row_fingerprints": fingerprints,
                    }
                ),
            )
        )
    return tuple(qualified), calendar_unavailable


def _minute_is_complete(*, row_key: str, collected_at: datetime) -> bool:
    start = _korea_timestamp_to_utc(row_key)
    collection_minute = require_utc(collected_at, "collected_at").replace(second=0, microsecond=0)
    return start + timedelta(minutes=1) <= collection_minute


def _persist_qualified_window(
    *,
    window: _QualifiedWindow,
    artifact_root: Path,
    repository_root: Path,
    index_metadata_sha256: str,
    selected_chunk_count: int,
) -> KisQqqIntradayHeadReadiness:
    directory = ensure_external_artifact_directory(
        artifact_root,
        repository_root,
        KIS_QQQ_INTRADAY_HEAD_READINESS_ARTIFACT_DIRECTORY,
    )
    existing = _existing_session_commitment(
        directory=directory,
        session_key_sha256=window.session_key_sha256,
    )
    if existing is not None:
        if existing != window.source_commitment_sha256:
            return _persist_contamination(
                reason="artifact_identity_conflict",
                artifact_root=artifact_root,
                repository_root=repository_root,
                index_metadata_sha256=index_metadata_sha256,
                selected_chunk_count=selected_chunk_count,
                window=window,
            )
        return _result(
            status="duplicate",
            index_metadata_sha256=index_metadata_sha256,
            selected_chunk_count=selected_chunk_count,
            window=window,
        )
    result = _result(
        status="observed",
        index_metadata_sha256=index_metadata_sha256,
        selected_chunk_count=selected_chunk_count,
        window=window,
    )
    destination = directory / _receipt_filename(status="observed", window=window)
    _write_immutable_json(path=destination, payload=result.safe_payload(), root=directory)
    return _with_evidence_path(result=result, evidence_path=destination)


def _persist_contamination(
    *,
    reason: str,
    artifact_root: Path,
    repository_root: Path,
    index_metadata_sha256: str,
    selected_chunk_count: int,
    window: _QualifiedWindow | None = None,
) -> KisQqqIntradayHeadReadiness:
    result = _result(
        status="contaminated",
        reason=reason,
        index_metadata_sha256=index_metadata_sha256,
        selected_chunk_count=selected_chunk_count,
        window=window,
    )
    directory = ensure_external_artifact_directory(
        artifact_root,
        repository_root,
        KIS_QQQ_INTRADAY_HEAD_READINESS_ARTIFACT_DIRECTORY,
    )
    destination = directory / _receipt_filename(
        status="contaminated",
        window=window,
        index_hash=index_metadata_sha256,
    )
    _write_immutable_json(path=destination, payload=result.safe_payload(), root=directory)
    return _with_evidence_path(result=result, evidence_path=destination)


def _result(
    *,
    status: ReadinessStatus,
    reason: str | None = None,
    index_metadata_sha256: str | None = None,
    selected_chunk_count: int = 0,
    window: _QualifiedWindow | None = None,
) -> KisQqqIntradayHeadReadiness:
    return KisQqqIntradayHeadReadiness(
        status=status,
        reason=reason,
        index_metadata_sha256=index_metadata_sha256,
        selected_chunk_count=selected_chunk_count,
        session_date=None if window is None else window.session_date,
        session_key_sha256=None if window is None else window.session_key_sha256,
        source_commitment_sha256=None if window is None else window.source_commitment_sha256,
    )


def _existing_session_commitment(*, directory: Path, session_key_sha256: str) -> str | None:
    found: str | None = None
    for path in directory.glob("*.json"):
        if path.is_symlink():
            raise ValueError("QQQ readiness artifact ledger is invalid")
        try:
            payload = json.loads(path.read_text(encoding="ascii"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("QQQ readiness artifact ledger is invalid") from error
        if not isinstance(payload, Mapping):
            raise ValueError("QQQ readiness artifact ledger is invalid")
        if (
            payload.get("kind") != KIS_QQQ_INTRADAY_HEAD_READINESS_KIND
            or payload.get("status") != "observed"
        ):
            continue
        window = payload.get("prospective_window")
        if (
            not isinstance(window, Mapping)
            or window.get("session_key_sha256") != session_key_sha256
        ):
            continue
        commitment = window.get("source_commitment_sha256")
        if not _is_sha256(commitment):
            raise ValueError("QQQ readiness artifact ledger is invalid")
        if found is not None and found != commitment:
            raise ValueError("QQQ readiness artifact ledger is invalid")
        found = commitment
    return found


def _receipt_filename(
    *,
    status: Literal["observed", "contaminated"],
    window: _QualifiedWindow | None,
    index_hash: str | None = None,
) -> str:
    session_token = "metadata" if window is None else _digest_suffix(window.session_key_sha256)
    identity = (
        _digest_suffix(index_hash)
        if window is None
        else _digest_suffix(window.source_commitment_sha256)
    )
    return f"{status}-{session_token}-{identity}.json"


def _write_immutable_json(*, path: Path, payload: Mapping[str, object], root: Path) -> None:
    if (
        path.parent != root
        or path.is_symlink()
        or not path.resolve(strict=False).is_relative_to(root)
    ):
        raise ValueError("QQQ readiness artifact path is invalid")
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="ascii") != rendered:
            raise ValueError("QQQ readiness artifact identity conflicts")
        return
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="ascii",
        dir=root,
        prefix=f".{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    try:
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            if path.is_symlink() or path.read_text(encoding="ascii") != rendered:
                raise ValueError("QQQ readiness artifact identity conflicts") from error
    finally:
        temporary.unlink(missing_ok=True)


def _with_evidence_path(
    *, result: KisQqqIntradayHeadReadiness, evidence_path: Path
) -> KisQqqIntradayHeadReadiness:
    return KisQqqIntradayHeadReadiness(
        status=result.status,
        reason=result.reason,
        index_metadata_sha256=result.index_metadata_sha256,
        selected_chunk_count=result.selected_chunk_count,
        session_date=result.session_date,
        session_key_sha256=result.session_key_sha256,
        source_commitment_sha256=result.source_commitment_sha256,
        evidence_path=evidence_path,
        schema_version=result.schema_version,
    )


def _korea_timestamp_to_utc(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError as error:
        raise ValueError("QQQ readiness timestamp metadata is invalid") from error
    return parsed.replace(tzinfo=_KOREA_TZ).astimezone(UTC)


def _korea_timestamp_key(value: datetime) -> str:
    return require_utc(value, "session timestamp").astimezone(_KOREA_TZ).strftime("%Y%m%dT%H%M%S")


def _sha256_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


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


def _digest_suffix(value: str | None) -> str:
    if not _is_sha256(value):
        raise ValueError("QQQ readiness hash is invalid")
    return value.removeprefix("sha256:")[:20]


def _has_existing_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if not current.exists():
            return False
        if current.is_symlink():
            return True
    return False

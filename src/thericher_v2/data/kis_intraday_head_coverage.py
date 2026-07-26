"""Metadata-only coverage inspection for the prospective KIS intraday head."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from .kis_paper_intraday import raw_bar_end_is_complete
from .kis_paper_intraday_index_metadata import (
    KisPaperPrivateIntradayV1RetainedChunkMetadata,
    KisPaperPrivateIntradayV1TargetMetadata,
    sha256_kis_paper_private_intraday_v1_index_bytes,
    validate_kis_paper_private_intraday_v1_index_metadata,
)
from .us_equity_session import us_equity_2026_session

KIS_INTRADAY_HEAD_COVERAGE_KIND = "kis_paper_intraday_head_coverage"
KIS_INTRADAY_HEAD_CACHE_VERSION = "v1"
KIS_INTRADAY_HEAD_INDEX_FILENAME = "index.json"
KIS_INTRADAY_HEAD_EXPECTED_TARGETS = (("QQQ", "NAS"), ("SPY", "AMS"))
KIS_INTRADAY_HEAD_QQQ_TARGET_KEY = "QQQ/NAS/1m"

_KOREA_TZ = ZoneInfo("Asia/Seoul")
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,80}", re.ASCII)


@dataclass(frozen=True, slots=True)
class KisIntradayHeadSessionCoverage:
    """One regular session's safe, offset-based QQQ coverage facts."""

    session_date: date
    expected_minute_count: int
    complete_minute_count: int
    missing_minute_ranges: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if type(self.session_date) is not date:
            raise ValueError("head coverage session date is invalid")
        if (
            type(self.expected_minute_count) is not int
            or type(self.complete_minute_count) is not int
            or self.expected_minute_count <= 0
            or not 0 <= self.complete_minute_count <= self.expected_minute_count
        ):
            raise ValueError("head coverage minute counts are invalid")
        ranges = tuple(self.missing_minute_ranges)
        object.__setattr__(self, "missing_minute_ranges", ranges)
        missing_count = 0
        previous_end = -1
        for start, end in ranges:
            if (
                type(start) is not int
                or type(end) is not int
                or start < 0
                or end < start
                or end >= self.expected_minute_count
                or start <= previous_end
            ):
                raise ValueError("head coverage missing minute ranges are invalid")
            previous_end = end
            missing_count += end - start + 1
        if missing_count != self.expected_minute_count - self.complete_minute_count:
            raise ValueError("head coverage missing minute ranges disagree with counts")

    @property
    def status(self) -> Literal["complete", "short"]:
        return "complete" if self.complete_minute_count == self.expected_minute_count else "short"

    def to_payload(self) -> dict[str, object]:
        return {
            "session_date": self.session_date.isoformat(),
            "status": self.status,
            "expected_minute_count": self.expected_minute_count,
            "complete_minute_count": self.complete_minute_count,
            "missing_minute_count": self.expected_minute_count - self.complete_minute_count,
            "missing_minute_ranges": [
                {
                    "start_offset": start,
                    "end_offset": end,
                    "minute_count": end - start + 1,
                }
                for start, end in self.missing_minute_ranges
            ],
        }


@dataclass(frozen=True, slots=True)
class KisIntradayHeadCoverage:
    """Safe coverage summary derived only from the head index and manifests."""

    status: Literal["not_created", "available"]
    target_key: str
    required_complete_session_count: int
    index_generation: int | None
    index_metadata_sha256: str | None
    retained_chunk_count: int
    last_reason_category: str
    last_conflict_origin: Literal[
        "none", "not_recorded", "candidate_batch", "retained_cache"
    ]
    continuation_category: Literal["not_observed", "available", "terminal", "mixed"]
    exact_overlap_row_count: int
    exact_overlap_category: Literal["none", "exact_overlap"]
    conflicting_overlap_category: Literal["none", "retained_fingerprint_conflict"]
    session_coverage: tuple[KisIntradayHeadSessionCoverage, ...]

    def __post_init__(self) -> None:
        if self.status not in {"not_created", "available"}:
            raise ValueError("head coverage status is invalid")
        if not self.target_key or type(self.required_complete_session_count) is not int:
            raise ValueError("head coverage scope is invalid")
        if (
            self.required_complete_session_count <= 0
            or type(self.retained_chunk_count) is not int
            or self.retained_chunk_count < 0
            or self.continuation_category not in {"not_observed", "available", "terminal", "mixed"}
            or self.exact_overlap_category not in {"none", "exact_overlap"}
            or self.conflicting_overlap_category not in {"none", "retained_fingerprint_conflict"}
            or self.last_conflict_origin
            not in {"none", "not_recorded", "candidate_batch", "retained_cache"}
            or type(self.exact_overlap_row_count) is not int
            or self.exact_overlap_row_count < 0
            or not _SAFE_REASON.fullmatch(self.last_reason_category)
        ):
            raise ValueError("head coverage counts are invalid")
        if self.last_reason_category == "minute_duplicate_conflict":
            if self.last_conflict_origin == "none":
                raise ValueError("head coverage conflict origin is invalid")
        elif self.last_conflict_origin != "none":
            raise ValueError("head coverage conflict origin is invalid")
        if self.status == "not_created":
            if (
                self.index_generation is not None
                or self.index_metadata_sha256 is not None
                or self.retained_chunk_count != 0
                or self.session_coverage
                or self.last_conflict_origin != "none"
            ):
                raise ValueError("missing head coverage is invalid")
        elif (
            self.index_generation is None
            or self.index_generation < 0
            or not _is_sha256(self.index_metadata_sha256)
        ):
            raise ValueError("available head coverage is invalid")
        coverage = tuple(self.session_coverage)
        object.__setattr__(self, "session_coverage", coverage)
        if tuple(item.session_date for item in coverage) != tuple(
            sorted(item.session_date for item in coverage)
        ):
            raise ValueError("head coverage sessions must be chronological")

    @property
    def complete_sessions(self) -> tuple[KisIntradayHeadSessionCoverage, ...]:
        return tuple(item for item in self.session_coverage if item.status == "complete")

    @property
    def preparation_input_status(self) -> Literal[
        "pending_complete_sessions", "metadata_conflict", "sufficient_complete_sessions"
    ]:
        if self.conflicting_overlap_category != "none":
            return "metadata_conflict"
        if len(self.complete_sessions) < self.required_complete_session_count:
            return "pending_complete_sessions"
        return "sufficient_complete_sessions"

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": KIS_INTRADAY_HEAD_COVERAGE_KIND,
            "status": self.status,
            "target_key": self.target_key,
            "index": {
                "generation": self.index_generation,
                "metadata_sha256": self.index_metadata_sha256,
            },
            "retained_chunk_count": self.retained_chunk_count,
            "last_reason_category": self.last_reason_category,
            "last_conflict_origin": self.last_conflict_origin,
            "continuation_category": self.continuation_category,
            "exact_overlap": {
                "category": self.exact_overlap_category,
                "row_count": self.exact_overlap_row_count,
            },
            "conflicting_overlap_category": self.conflicting_overlap_category,
            "regular_session_coverage": [item.to_payload() for item in self.session_coverage],
            "complete_regular_session_dates": [
                item.session_date.isoformat() for item in self.complete_sessions
            ],
            "complete_regular_session_count": len(self.complete_sessions),
            "preparation_input": {
                "required_complete_session_count": self.required_complete_session_count,
                "status": self.preparation_input_status,
            },
        }


def inspect_kis_paper_private_intraday_head_coverage(
    *,
    cache_root: Path | str,
    repo_root: Path | str,
    after_session_date: date,
    required_complete_session_count: int,
    manifest_hashes: frozenset[str] | None = None,
) -> KisIntradayHeadCoverage:
    """Inspect QQQ head coverage without opening raw minute files or network access.

    ``manifest_hashes`` narrows the result to one bounded capture attempt. An
    empty set deliberately selects no retained rows, so a legacy head chunk
    cannot satisfy a fresh capture receipt by accident.
    """

    if (
        type(after_session_date) is not date
        or type(required_complete_session_count) is not int
        or required_complete_session_count <= 0
    ):
        raise ValueError("head coverage inspection scope is invalid")
    if manifest_hashes is not None and (
        not isinstance(manifest_hashes, frozenset)
        or any(not _is_sha256(value) for value in manifest_hashes)
    ):
        raise ValueError("head coverage manifest scope is invalid")
    version_root, index_path = _head_index_paths(cache_root=cache_root, repo_root=repo_root)
    if not index_path.exists():
        return KisIntradayHeadCoverage(
            status="not_created",
            target_key=KIS_INTRADAY_HEAD_QQQ_TARGET_KEY,
            required_complete_session_count=required_complete_session_count,
            index_generation=None,
            index_metadata_sha256=None,
            retained_chunk_count=0,
            last_reason_category="none",
            last_conflict_origin="none",
            continuation_category="not_observed",
            exact_overlap_row_count=0,
            exact_overlap_category="none",
            conflicting_overlap_category="none",
            session_coverage=(),
        )
    if index_path.is_symlink():
        raise ValueError("head coverage index is invalid")
    try:
        index_bytes = index_path.read_bytes()
        index = json.loads(index_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("head coverage index is invalid") from error
    if not isinstance(index, Mapping):
        raise ValueError("head coverage index is invalid")
    try:
        metadata = validate_kis_paper_private_intraday_v1_index_metadata(
            index,
            expected_targets=KIS_INTRADAY_HEAD_EXPECTED_TARGETS,
        )
    except ValueError as error:
        raise ValueError("head coverage index is invalid") from error
    target = _target_metadata(metadata.targets)
    target_document = _target_document(index)
    all_retained_documents = _retained_chunk_documents(target_document)
    if len(all_retained_documents) != len(target.retained_chunks):
        raise ValueError("head coverage index is invalid")
    retained_documents, retained_chunks = _select_retained_chunks(
        documents=all_retained_documents,
        chunks=target.retained_chunks,
        manifest_hashes=manifest_hashes,
    )

    first_seen_complete, retained_fingerprint_conflict = _first_seen_completion(
        chunks=retained_chunks
    )
    session_coverage = _session_coverage(
        completed_row_keys=frozenset(
            row_key for row_key, complete in first_seen_complete.items() if complete
        ),
        after_session_date=after_session_date,
    )
    exact_overlap_row_count = sum(
        _required_nonnegative_int(document.get("exact_overlap_rows"))
        for document in retained_documents
    )
    continuation_category = _continuation_category(
        version_root=version_root,
        target=target,
        chunks=retained_documents,
    )
    last_reason = (
        target_document.get("last_reason")
        if manifest_hashes is None
        else (retained_documents[-1].get("reason") if retained_documents else None)
    )
    last_reason_category = _last_reason_category(last_reason)
    return KisIntradayHeadCoverage(
        status="available",
        target_key=target.target_key,
        required_complete_session_count=required_complete_session_count,
        index_generation=metadata.generation,
        index_metadata_sha256=sha256_kis_paper_private_intraday_v1_index_bytes(index_bytes),
        retained_chunk_count=len(retained_chunks),
        last_reason_category=last_reason_category,
        last_conflict_origin=(
            _last_conflict_origin(
                target_document=target_document,
                last_reason=last_reason,
            )
            if manifest_hashes is None
            else "none"
        ),
        continuation_category=continuation_category,
        exact_overlap_row_count=exact_overlap_row_count,
        exact_overlap_category=("exact_overlap" if exact_overlap_row_count else "none"),
        conflicting_overlap_category=(
            "retained_fingerprint_conflict" if retained_fingerprint_conflict else "none"
        ),
        session_coverage=session_coverage,
    )


def _head_index_paths(*, cache_root: Path | str, repo_root: Path | str) -> tuple[Path, Path]:
    root = Path(cache_root)
    if root.is_symlink():
        raise ValueError("head coverage cache root is invalid")
    resolved_root = root.resolve()
    if resolved_root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("head coverage cache root must stay outside the Git workspace")
    version_root = resolved_root / KIS_INTRADAY_HEAD_CACHE_VERSION
    if version_root.is_symlink():
        raise ValueError("head coverage cache root is invalid")
    return version_root, version_root / KIS_INTRADAY_HEAD_INDEX_FILENAME


def _target_metadata(
    targets: Sequence[KisPaperPrivateIntradayV1TargetMetadata],
) -> KisPaperPrivateIntradayV1TargetMetadata:
    matches = [
        target for target in targets if target.target_key == KIS_INTRADAY_HEAD_QQQ_TARGET_KEY
    ]
    if len(matches) != 1:
        raise ValueError("head coverage target is invalid")
    return matches[0]


def _target_document(index: Mapping[str, object]) -> Mapping[str, object]:
    targets = index.get("targets")
    if not isinstance(targets, list):
        raise ValueError("head coverage index is invalid")
    matches = [
        target
        for target in targets
        if isinstance(target, Mapping)
        and target.get("target_key") == KIS_INTRADAY_HEAD_QQQ_TARGET_KEY
    ]
    if len(matches) != 1:
        raise ValueError("head coverage target is invalid")
    return matches[0]


def _retained_chunk_documents(target: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    chunks = target.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("head coverage target is invalid")
    retained: list[Mapping[str, object]] = []
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("head coverage target is invalid")
        if chunk.get("raw_market_data_retained") is True:
            retained.append(chunk)
    return tuple(retained)


def _select_retained_chunks(
    *,
    documents: Sequence[Mapping[str, object]],
    chunks: Sequence[KisPaperPrivateIntradayV1RetainedChunkMetadata],
    manifest_hashes: frozenset[str] | None,
) -> tuple[
    tuple[Mapping[str, object], ...], tuple[KisPaperPrivateIntradayV1RetainedChunkMetadata, ...]
]:
    if len(documents) != len(chunks):
        raise ValueError("head coverage index is invalid")
    pairs = tuple(zip(documents, chunks, strict=True))
    if manifest_hashes is not None:
        pairs = tuple(
            (document, chunk)
            for document, chunk in pairs
            if document.get("manifest_hash") in manifest_hashes
        )
    return tuple(document for document, _ in pairs), tuple(chunk for _, chunk in pairs)


def _first_seen_completion(
    *,
    chunks: Sequence[KisPaperPrivateIntradayV1RetainedChunkMetadata],
) -> tuple[dict[str, bool], bool]:
    completion: dict[str, bool] = {}
    fingerprints: dict[str, str] = {}
    retained_fingerprint_conflict = False
    for chunk in chunks:
        if chunk.candidate_batch_conflicted:
            continue
        for row_key, fingerprint in chunk.rows:
            prior = fingerprints.get(row_key)
            if prior is not None:
                retained_fingerprint_conflict = (
                    retained_fingerprint_conflict or prior != fingerprint
                )
                continue
            fingerprints[row_key] = fingerprint
            completion[row_key] = raw_bar_end_is_complete(
                start_ts=_korea_timestamp_to_utc(row_key),
                collected_at=chunk.collected_at,
            )
    return completion, retained_fingerprint_conflict


def _session_coverage(
    *,
    completed_row_keys: frozenset[str],
    after_session_date: date,
) -> tuple[KisIntradayHeadSessionCoverage, ...]:
    candidate_dates = sorted(
        {
            _korea_timestamp_to_utc(row_key).date()
            for row_key in completed_row_keys
            if _korea_timestamp_to_utc(row_key).date() > after_session_date
        }
    )
    coverage: list[KisIntradayHeadSessionCoverage] = []
    for session_date in candidate_dates:
        session = us_equity_2026_session(session_date)
        if session is None or session.kind != "regular":
            continue
        expected_keys = tuple(
            _korea_timestamp_key(session.window.open_ts + timedelta(minutes=offset))
            for offset in range(
                int((session.window.close_ts - session.window.open_ts) / timedelta(minutes=1))
            )
        )
        missing_offsets = tuple(
            offset
            for offset, row_key in enumerate(expected_keys)
            if row_key not in completed_row_keys
        )
        coverage.append(
            KisIntradayHeadSessionCoverage(
                session_date=session_date,
                expected_minute_count=len(expected_keys),
                complete_minute_count=len(expected_keys) - len(missing_offsets),
                missing_minute_ranges=_contiguous_ranges(missing_offsets),
            )
        )
    return tuple(coverage)


def _continuation_category(
    *,
    version_root: Path,
    target: KisPaperPrivateIntradayV1TargetMetadata,
    chunks: Sequence[Mapping[str, object]],
) -> Literal["not_observed", "available", "terminal", "mixed"]:
    if not chunks:
        return "not_observed"
    continuation_flags = tuple(
        _manifest_has_continuation(version_root=version_root, target=target, chunk=chunk)
        for chunk in chunks
    )
    if all(continuation_flags):
        return "available"
    if not any(continuation_flags):
        return "terminal"
    return "mixed"


def _manifest_has_continuation(
    *,
    version_root: Path,
    target: KisPaperPrivateIntradayV1TargetMetadata,
    chunk: Mapping[str, object],
) -> bool:
    relative = chunk.get("manifest_path")
    expected_hash = chunk.get("manifest_hash")
    if not isinstance(relative, str) or not _is_sha256(expected_hash):
        raise ValueError("head coverage manifest metadata is invalid")
    relative_path = Path(relative)
    candidate = version_root / relative_path
    if not relative or relative_path.is_absolute() or candidate.is_symlink():
        raise ValueError("head coverage manifest metadata is invalid")
    resolved_root = version_root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("head coverage manifest metadata is invalid")
    try:
        payload = resolved.read_bytes()
        manifest = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("head coverage manifest metadata is invalid") from error
    if _sha256(payload) != expected_hash or not isinstance(manifest, Mapping):
        raise ValueError("head coverage manifest metadata is invalid")
    source = manifest.get("source")
    pages = manifest.get("pages")
    if (
        not isinstance(source, Mapping)
        or source.get("symbol") != target.symbol
        or source.get("exchange") != target.exchange
        or not isinstance(pages, list)
        or not pages
        or not isinstance(pages[-1], Mapping)
        or type(pages[-1].get("continuation_available")) is not bool
    ):
        raise ValueError("head coverage manifest metadata is invalid")
    return bool(pages[-1]["continuation_available"])


def _last_reason_category(value: object) -> str:
    if value is None:
        return "none"
    if not isinstance(value, str):
        raise ValueError("head coverage target reason is invalid")
    return value if _SAFE_REASON.fullmatch(value) else "unclassified"


def _last_conflict_origin(
    *,
    target_document: Mapping[str, object],
    last_reason: object,
) -> Literal["none", "not_recorded", "candidate_batch", "retained_cache"]:
    if last_reason != "minute_duplicate_conflict":
        return "none"
    if "last_conflict_origin" not in target_document:
        return "not_recorded"
    value = target_document.get("last_conflict_origin")
    if value in {"candidate_batch", "retained_cache"}:
        return value
    raise ValueError("head coverage target conflict origin is invalid")


def _required_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("head coverage overlap metadata is invalid")
    return value


def _contiguous_ranges(offsets: Sequence[int]) -> tuple[tuple[int, int], ...]:
    if not offsets:
        return ()
    ranges: list[tuple[int, int]] = []
    start = offsets[0]
    previous = start
    for offset in offsets[1:]:
        if offset == previous + 1:
            previous = offset
            continue
        ranges.append((start, previous))
        start = offset
        previous = offset
    ranges.append((start, previous))
    return tuple(ranges)


def _korea_timestamp_to_utc(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError as error:
        raise ValueError("head coverage timestamp metadata is invalid") from error
    return parsed.replace(tzinfo=_KOREA_TZ).astimezone(UTC)


def _korea_timestamp_key(value: datetime) -> str:
    return value.astimezone(_KOREA_TZ).strftime("%Y%m%dT%H%M%S")


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

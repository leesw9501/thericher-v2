"""Isolated one-page IWM/AMS KIS Paper minute-head cache.

This route deliberately stays outside the QQQ/SPY intraday collector.  It
retains one current-day IWM page as an immutable content-addressed snapshot,
never follows a continuation cursor, and emits only source-safe receipts.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataError,
    KisPaperMinutePage,
    KisPaperMinuteQuery,
    KisPaperMinuteRawBar,
)

KIS_PAPER_MARKET_DATA_ROOT = Path(r"D:\market_data")
KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT = (
    KIS_PAPER_MARKET_DATA_ROOT / "us_equities" / "kis_paper_private" / "intraday"
)
KIS_PAPER_IWM_M1_CURRENT_HEAD_CACHE_ROOT = (
    KIS_PAPER_MARKET_DATA_ROOT
    / "us_equities"
    / "kis_paper_private"
    / "iwm_m1_current_head"
)
KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET = ("IWM", "AMS")
KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY = "IWM/AMS/1m"
KIS_PAPER_IWM_M1_CURRENT_HEAD_VERSION = "v1"
KIS_PAPER_IWM_M1_CURRENT_HEAD_SNAPSHOT_DIRECTORY = "snapshots"
KIS_PAPER_IWM_M1_CURRENT_HEAD_ARTIFACT_DIRECTORY = "data/kis-paper-iwm-m1-current-head"

_RAW_MINUTE_COLUMNS = (
    "xymd",
    "xhms",
    "kymd",
    "khms",
    "open",
    "high",
    "low",
    "last",
    "evol",
)
_SAFE_FAILURE_REASONS = frozenset(
    {
        "auth_rejected",
        "auth_response_invalid",
        "config_missing",
        "minute_duplicate_conflict",
        "minute_response_empty",
        "minute_response_invalid",
        "minute_response_rejected",
        "paper_host_required",
        "rate_limited",
        "redirect_rejected",
        "request_not_allowlisted",
        "response_invalid",
        "token_request_not_due",
        "transport_failure",
    }
)


class KisPaperIwmM1CurrentHeadClient(Protocol):
    """The data-only operation used by the isolated IWM cache."""

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage: ...


@dataclass(frozen=True)
class KisPaperIwmM1CurrentHeadOutcome:
    """Source-safe result of one IWM current-head observation."""

    status: Literal["collected", "unavailable", "rejected"]
    observed_at: datetime
    row_count: int
    exact_duplicate_rows: int
    continuation_category: Literal["not_observed", "observed_not_followed"]
    cache_disposition: Literal["retained", "already_retained", "not_written"]
    response_class: str
    raw_market_data_retained: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.row_count < 0 or self.exact_duplicate_rows < 0 or not self.response_class:
            raise ValueError("IWM current-head outcome is invalid")
        if self.status == "collected":
            if (
                self.row_count <= 0
                or self.cache_disposition not in {"retained", "already_retained"}
                or not self.raw_market_data_retained
                or self.response_class != "accepted"
            ):
                raise ValueError("IWM current-head outcome is invalid")
            return
        if (
            self.row_count
            or self.exact_duplicate_rows
            or self.cache_disposition != "not_written"
            or self.raw_market_data_retained
        ):
            raise ValueError("IWM current-head outcome is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return a receipt body without raw rows, paths, or credentials."""

        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_iwm_m1_current_head",
            "status": self.status,
            "paper_only": True,
            "route_class": "kis_paper_market_data",
            "target_key": KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY,
            "collection_scope": "one_current_day_head_page_no_continuation",
            "observed_at": self.observed_at.isoformat(),
            "accepted_page_count": int(self.status == "collected"),
            "accepted_row_category": "nonempty" if self.row_count else "none",
            "continuation_category": self.continuation_category,
            "cache_disposition": self.cache_disposition,
            "response_class": self.response_class,
            "raw_market_data_retained": self.raw_market_data_retained,
            "storage": "external_market_data_only",
            "next_recovery": (
                "new_isolated_current_head_observation"
                if self.status == "collected"
                else "retry_isolated_one_page_observation"
            ),
        }


@dataclass(frozen=True)
class KisPaperIwmM1CurrentHeadResult:
    outcome: KisPaperIwmM1CurrentHeadOutcome
    snapshot_path: Path | None


@dataclass(frozen=True)
class KisPaperIwmM1CurrentHeadReceipt:
    result: KisPaperIwmM1CurrentHeadResult
    evidence_path: Path


class _CandidatePageDuplicateConflict(KisPaperMarketDataError):
    """Marks a conflicting timestamp inside the single candidate page."""


def collect_kis_paper_iwm_m1_current_head(
    *,
    client: KisPaperIwmM1CurrentHeadClient,
    cache_root: Path,
    repository_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
    protected_cache_roots: tuple[Path, ...] = (KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,),
    observed_at: datetime | None = None,
) -> KisPaperIwmM1CurrentHeadResult:
    """Collect at most one current-day IWM/AMS page into its own cache."""

    root = validate_kis_paper_iwm_m1_current_head_cache_root(
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=market_data_root,
        protected_cache_roots=protected_cache_roots,
    )
    observed = require_utc(observed_at or datetime.now(UTC), "observed_at")
    query = KisPaperMinuteQuery(
        exchange=KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET[1],
        symbol=KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET[0],
    )
    try:
        page = client.fetch_minute_page(query)
        rows, exact_duplicate_rows = _validated_page_rows(page=page, query=query)
    except KisPaperMarketDataError as error:
        return KisPaperIwmM1CurrentHeadResult(
            outcome=_failed_outcome(error=error, observed_at=observed),
            snapshot_path=None,
        )

    raw_bytes = _compressed_raw_minute_csv(rows)
    content_document = [row.as_document() for row in rows]
    content_digest = hashlib.sha256(_canonical_json_bytes(content_document)).hexdigest()
    raw_digest = hashlib.sha256(raw_bytes).hexdigest()
    manifest = _snapshot_manifest(
        content_digest=content_digest,
        raw_digest=raw_digest,
        row_count=len(rows),
        exact_duplicate_rows=exact_duplicate_rows,
        continuation_observed=page.next_cursor is not None,
    )
    snapshot_path, cache_disposition = _write_immutable_snapshot(
        root=root,
        content_digest=content_digest,
        raw_bytes=raw_bytes,
        manifest=manifest,
    )
    return KisPaperIwmM1CurrentHeadResult(
        outcome=KisPaperIwmM1CurrentHeadOutcome(
            status="collected",
            observed_at=observed,
            row_count=len(rows),
            exact_duplicate_rows=exact_duplicate_rows,
            continuation_category=(
                "observed_not_followed" if page.next_cursor is not None else "not_observed"
            ),
            cache_disposition=cache_disposition,
            response_class="accepted",
            raw_market_data_retained=True,
        ),
        snapshot_path=snapshot_path,
    )


def collect_and_write_kis_paper_iwm_m1_current_head(
    *,
    client: KisPaperIwmM1CurrentHeadClient,
    cache_root: Path,
    artifact_root: Path,
    repository_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
    protected_cache_roots: tuple[Path, ...] = (KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,),
    observed_at: datetime | None = None,
) -> KisPaperIwmM1CurrentHeadReceipt:
    """Collect the isolated page and retain a source-safe external receipt."""

    result = collect_kis_paper_iwm_m1_current_head(
        client=client,
        cache_root=cache_root,
        repository_root=repository_root,
        market_data_root=market_data_root,
        protected_cache_roots=protected_cache_roots,
        observed_at=observed_at,
    )
    return KisPaperIwmM1CurrentHeadReceipt(
        result=result,
        evidence_path=write_kis_paper_iwm_m1_current_head_evidence(
            outcome=result.outcome,
            artifact_root=artifact_root,
            repository_root=repository_root,
        ),
    )


def write_kis_paper_iwm_m1_current_head_evidence(
    *,
    outcome: KisPaperIwmM1CurrentHeadOutcome,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Atomically write a receipt that cannot contain provider rows."""

    root = _external_root(
        root=artifact_root,
        repository_root=repository_root,
        label="IWM current-head artifact root",
    )
    payload = _canonical_json_bytes(outcome.safe_payload()) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()[:16]
    destination = (
        root
        / KIS_PAPER_IWM_M1_CURRENT_HEAD_ARTIFACT_DIRECTORY
        / f"{outcome.observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{digest}.json"
    )
    _ensure_directory(destination.parent)
    _validate_descendant(root=root, path=destination, label="IWM current-head evidence")
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ValueError("IWM current-head evidence conflicts")
        return destination
    staging = destination.with_name(f".{digest}.{uuid.uuid4().hex[:8]}.stage")
    try:
        staging.write_bytes(payload)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def validate_kis_paper_iwm_m1_current_head_cache_root(
    *,
    cache_root: Path,
    repository_root: Path,
    market_data_root: Path = KIS_PAPER_MARKET_DATA_ROOT,
    protected_cache_roots: tuple[Path, ...] = (KIS_PAPER_PRIVATE_INTRADAY_CACHE_ROOT,),
) -> Path:
    """Reject in-repository or linked destinations before any provider request."""

    resolved_cache = _external_root(
        root=cache_root,
        repository_root=repository_root,
        label="IWM current-head cache root",
    )
    resolved_market_data_root = _external_root(
        root=market_data_root,
        repository_root=repository_root,
        label="market-data root",
    )
    if (
        resolved_cache == resolved_market_data_root
        or not resolved_cache.is_relative_to(resolved_market_data_root)
    ):
        raise ValueError("IWM current-head cache root must stay below market-data root")
    for protected_root in protected_cache_roots:
        resolved_protected_root = Path(protected_root).resolve()
        if (
            resolved_cache == resolved_protected_root
            or resolved_cache.is_relative_to(resolved_protected_root)
            or resolved_protected_root.is_relative_to(resolved_cache)
        ):
            raise ValueError("IWM current-head cache root overlaps active private cache")
    return resolved_cache


def _validated_page_rows(
    *,
    page: KisPaperMinutePage,
    query: KisPaperMinuteQuery,
) -> tuple[tuple[KisPaperMinuteRawBar, ...], int]:
    if page.query != query or not page.bars:
        reason = "minute_response_invalid" if page.bars else "minute_response_empty"
        raise KisPaperMarketDataError(reason)
    rows_by_key: dict[str, KisPaperMinuteRawBar] = {}
    exact_duplicate_rows = 0
    for row in page.bars:
        key = f"{row.exchange_date}{row.exchange_time}"
        prior = rows_by_key.get(key)
        if prior is None:
            rows_by_key[key] = row
            continue
        if _row_fingerprint(prior) != _row_fingerprint(row):
            raise _CandidatePageDuplicateConflict("minute_duplicate_conflict")
        exact_duplicate_rows += 1
    return tuple(rows_by_key[key] for key in sorted(rows_by_key)), exact_duplicate_rows


def _failed_outcome(
    *,
    error: KisPaperMarketDataError,
    observed_at: datetime,
) -> KisPaperIwmM1CurrentHeadOutcome:
    reason = _safe_failure_reason(error)
    return KisPaperIwmM1CurrentHeadOutcome(
        status="rejected" if reason == "minute_duplicate_conflict" else "unavailable",
        observed_at=observed_at,
        row_count=0,
        exact_duplicate_rows=0,
        continuation_category="not_observed",
        cache_disposition="not_written",
        response_class=reason,
        raw_market_data_retained=False,
    )


def _write_immutable_snapshot(
    *,
    root: Path,
    content_digest: str,
    raw_bytes: bytes,
    manifest: dict[str, object],
) -> tuple[Path, Literal["retained", "already_retained"]]:
    version_root = root / KIS_PAPER_IWM_M1_CURRENT_HEAD_VERSION
    snapshot_root = version_root / KIS_PAPER_IWM_M1_CURRENT_HEAD_SNAPSHOT_DIRECTORY
    _ensure_directory(snapshot_root)
    destination = snapshot_root / content_digest
    _validate_descendant(root=root, path=destination, label="IWM current-head snapshot")
    if destination.exists():
        _attest_snapshot(destination=destination, raw_bytes=raw_bytes, manifest=manifest)
        return destination, "already_retained"

    staging = snapshot_root / f".{content_digest}.{uuid.uuid4().hex[:8]}.stage"
    try:
        staging.mkdir()
        (staging / "rows.csv.gz").write_bytes(raw_bytes)
        (staging / "manifest.json").write_bytes(_canonical_json_bytes(manifest) + b"\n")
        os.replace(staging, destination)
    except FileExistsError:
        _attest_snapshot(destination=destination, raw_bytes=raw_bytes, manifest=manifest)
        return destination, "already_retained"
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination, "retained"


def _attest_snapshot(
    *,
    destination: Path,
    raw_bytes: bytes,
    manifest: dict[str, object],
) -> None:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("IWM current-head snapshot is invalid")
    raw_path = destination / "rows.csv.gz"
    manifest_path = destination / "manifest.json"
    if (
        raw_path.is_symlink()
        or manifest_path.is_symlink()
        or raw_path.read_bytes() != raw_bytes
        or manifest_path.read_bytes() != _canonical_json_bytes(manifest) + b"\n"
    ):
        raise ValueError("IWM current-head snapshot conflicts")


def _snapshot_manifest(
    *,
    content_digest: str,
    raw_digest: str,
    row_count: int,
    exact_duplicate_rows: int,
    continuation_observed: bool,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_iwm_m1_current_head_snapshot",
        "collection_version": KIS_PAPER_IWM_M1_CURRENT_HEAD_VERSION,
        "target_key": KIS_PAPER_IWM_M1_CURRENT_HEAD_TARGET_KEY,
        "collection_scope": "one_current_day_head_page_no_continuation",
        "content_sha256": content_digest,
        "raw_sha256": raw_digest,
        "raw_filename": "rows.csv.gz",
        "row_count": row_count,
        "exact_duplicate_rows": exact_duplicate_rows,
        "continuation_observed": continuation_observed,
    }


def _compressed_raw_minute_csv(rows: tuple[KisPaperMinuteRawBar, ...]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as gzip_handle:
        with io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="") as text_handle:
            writer = csv.DictWriter(
                text_handle,
                fieldnames=_RAW_MINUTE_COLUMNS,
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row.as_document())
    return buffer.getvalue()


def _row_fingerprint(row: KisPaperMinuteRawBar) -> bytes:
    return _canonical_json_bytes(row.as_document())


def _external_root(*, root: Path, repository_root: Path, label: str) -> Path:
    supplied_root = Path(root)
    if supplied_root.is_symlink():
        raise ValueError(f"{label} is invalid")
    resolved_root = supplied_root.resolve()
    resolved_repository = Path(repository_root).resolve()
    if resolved_root.is_relative_to(resolved_repository):
        raise ValueError(f"{label} must stay outside Git")
    return resolved_root


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("IWM current-head destination is invalid")


def _validate_descendant(*, root: Path, path: Path, label: str) -> None:
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(root):
        raise ValueError(f"{label} is invalid")


def _safe_failure_reason(error: KisPaperMarketDataError) -> str:
    reason = str(error)
    return reason if reason in _SAFE_FAILURE_REASONS else "iwm_current_head_error"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

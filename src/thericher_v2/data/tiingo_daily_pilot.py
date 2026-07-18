"""One capped, private-use Tiingo standard-EOD raw-daily acquisition pilot."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import uuid
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .norgate_candidate_union import (
    DEFAULT_MARKET_DATA_ROOT,
    NorgateCandidateSelection,
    load_norgate_candidate_union,
    rank_quantile_ranks,
    select_rank_quantile_candidates,
)
from .tiingo_eod import TIINGO_EOD_ENDPOINT, read_tiingo_api_token

DEFAULT_TIINGO_DAILY_PILOT_ROOT = (
    DEFAULT_MARKET_DATA_ROOT / "us_equities" / "tiingo_standard_eod_pilot" / "canonical"
)
MAX_TIINGO_DAILY_PILOT_REQUESTS = 30
DEFAULT_TIINGO_DAILY_PILOT_SAMPLE_SIZE = 30
TIINGO_DAILY_PILOT_VERSION = "tiingo-standard-eod-pilot-r1"
TIINGO_TERMS_URL = "https://app.tiingo.com/tos/"
TIINGO_TERMS_RETRIEVED_DATE = date(2026, 7, 19)
TIINGO_INTERNAL_USE_CLAUSE = "All data via the API is for internal consumption only."
_CANONICAL_FILE = "ohlcv_1d.csv.gz"
_MANIFEST_FILE = "manifest.json"
_RETENTION_FILE = "TIINGO_PRIVATE_INTERNAL_DATA_MARKER.txt"
_SNAPSHOT_SUFFIX = "-tiingo-standard-eod-pilot-r1"
_RAW_COLUMNS = (
    "candidate_rank",
    "candidate_symbol",
    "request_identifier",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "div_cash",
    "split_factor",
)


class TiingoDailyPilotError(RuntimeError):
    """A masked, fail-closed error from the bounded Tiingo daily pilot."""


class _RejectRedirect(HTTPRedirectHandler):
    """Prevent an approved token from crossing a redirect boundary."""

    def redirect_request(
        self,
        _request: Request,
        _file: Any,
        _code: int,
        _message: str,
        _headers: Any,
        _new_url: str,
    ) -> Request:
        raise TiingoDailyPilotError("Tiingo daily pilot redirects are not allowed")


@dataclass(frozen=True, slots=True)
class TiingoDailyPilotRow:
    """One canonical raw-field row, intentionally outside any bar catalog."""

    candidate_rank: int
    candidate_symbol: str
    request_identifier: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    div_cash: Decimal
    split_factor: Decimal


@dataclass(frozen=True, slots=True)
class _PilotResponse:
    candidate_rank: int
    candidate_symbol: str
    request_identifier: str
    http_status: int | None
    classification: str
    row_count: int | None
    first_session: date | None
    last_session: date | None
    error_class: str | None
    raw_filename: str | None
    raw_hash: str | None
    raw_size: int | None


@dataclass(frozen=True, slots=True)
class TiingoDailyPilotResult:
    """Non-secret facts from one immutable external pilot snapshot."""

    snapshot_dir: Path
    dataset_hash: str
    manifest_hash: str
    completed: bool
    stop_reason: str | None
    request_count: int
    available_count: int
    empty_count: int
    unavailable_count: int
    row_count: int
    free_percent: float


def default_tiingo_daily_pilot_dir(retrieval_date: date) -> Path:
    """Return the external snapshot destination for this pilot revision."""

    if isinstance(retrieval_date, datetime):
        raise ValueError("Tiingo daily pilot retrieval date must not include a time")
    return DEFAULT_TIINGO_DAILY_PILOT_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def acquire_tiingo_daily_pilot(
    *,
    candidate_union_path: Path,
    candidate_union_manifest_path: Path,
    expected_candidate_union_hash: str,
    env_path: Path,
    destination: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    sample_size: int = DEFAULT_TIINGO_DAILY_PILOT_SAMPLE_SIZE,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: float = 20.0,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoDailyPilotResult:
    """Acquire exactly one capped pass and atomically retain its external evidence."""

    _validate_window(requested_start, requested_end)
    if not 1 <= sample_size <= MAX_TIINGO_DAILY_PILOT_REQUESTS:
        raise ValueError("Tiingo daily pilot sample size is outside the request budget")
    retrieved_at = _utc_datetime(retrieved_at_utc, "Tiingo daily pilot retrieval time")
    if timeout_seconds <= 0:
        raise ValueError("Tiingo daily pilot timeout must be positive")
    union = load_norgate_candidate_union(
        candidate_union_path=candidate_union_path,
        candidate_union_manifest_path=candidate_union_manifest_path,
        expected_candidate_union_hash=expected_candidate_union_hash,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    selection = select_rank_quantile_candidates(union, sample_size=sample_size)
    target, root = _validate_destination(
        destination,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    _assert_no_staging_residue(target)
    free_percent = _validate_storage(root, disk_usage=disk_usage)
    token = read_tiingo_api_token(env_path)
    request_opener = opener or _open_without_redirect

    staging = _create_staging_directory(target)
    try:
        raw_dir = staging / "raw"
        raw_dir.mkdir()
        rows: list[TiingoDailyPilotRow] = []
        responses: list[_PilotResponse] = []
        stop_reason: str | None = None
        for candidate_rank, candidate_symbol in zip(
            selection.selected_ranks, selection.selected_symbols, strict=True
        ):
            response, payload, should_stop = _request_response(
                candidate_rank=candidate_rank,
                candidate_symbol=candidate_symbol,
                token=token,
                requested_start=requested_start,
                requested_end=requested_end,
                opener=request_opener,
                timeout_seconds=timeout_seconds,
            )
            if payload is not None:
                response = _write_raw_response(response, payload=payload, raw_dir=raw_dir)
                try:
                    normalized = _normalize_response(
                        candidate_rank=candidate_rank,
                        candidate_symbol=candidate_symbol,
                        request_identifier=candidate_symbol,
                        payload=payload,
                        requested_start=requested_start,
                        requested_end=requested_end,
                    )
                except ValueError:
                    response = _replace_response(
                        response,
                        classification="error",
                        row_count=None,
                        first_session=None,
                        last_session=None,
                        error_class="malformed_response",
                    )
                    should_stop = True
                else:
                    if normalized:
                        rows.extend(normalized)
                        response = _replace_response(
                            response,
                            classification="available",
                            row_count=len(normalized),
                            first_session=normalized[0].session_date,
                            last_session=normalized[-1].session_date,
                            error_class=None,
                        )
                    else:
                        response = _replace_response(
                            response,
                            classification="empty",
                            row_count=0,
                            first_session=None,
                            last_session=None,
                            error_class=None,
                        )
            responses.append(response)
            if should_stop:
                stop_reason = response.error_class or "request_error"
                break

        canonical_bytes = _gzip_bytes(_canonical_csv_bytes(tuple(rows)))
        marker_bytes = _retention_marker_bytes()
        (staging / _CANONICAL_FILE).write_bytes(canonical_bytes)
        (staging / _RETENTION_FILE).write_bytes(marker_bytes)
        manifest = _manifest(
            snapshot_dir=target,
            selection=selection,
            candidate_union_path=candidate_union_path,
            responses=tuple(responses),
            dataset_hash=_sha256(canonical_bytes),
            dataset_size=len(canonical_bytes),
            row_count=len(rows),
            marker_hash=_sha256(marker_bytes),
            marker_size=len(marker_bytes),
            requested_start=requested_start,
            requested_end=requested_end,
            retrieved_at_utc=retrieved_at,
            stop_reason=stop_reason,
            free_percent=free_percent,
            market_data_root=root,
        )
        manifest_bytes = _json_bytes(manifest)
        (staging / _MANIFEST_FILE).write_bytes(manifest_bytes)
        os.rename(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    try:
        result = _verify_snapshot(
            target,
            expected_dataset_hash=_sha256(canonical_bytes),
            expected_manifest_hash=_sha256(manifest_bytes),
            market_data_root=market_data_root,
            repo_root=repo_root,
            require_destination_name=True,
        )
    except Exception as exc:
        _quarantine_failed_snapshot(target)
        raise TiingoDailyPilotError(
            "Tiingo daily pilot verification failed; external evidence was retained for recovery"
        ) from exc
    return TiingoDailyPilotResult(
        snapshot_dir=result.snapshot_dir,
        dataset_hash=result.dataset_hash,
        manifest_hash=result.manifest_hash,
        completed=result.completed,
        stop_reason=result.stop_reason,
        request_count=result.request_count,
        available_count=result.available_count,
        empty_count=result.empty_count,
        unavailable_count=result.unavailable_count,
        row_count=result.row_count,
        free_percent=result.free_percent,
    )


def verify_tiingo_daily_pilot_snapshot(
    snapshot_dir: Path,
    *,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoDailyPilotResult:
    """Re-attest a completed pilot offline without token or network access."""

    return _verify_snapshot(
        snapshot_dir,
        expected_dataset_hash=expected_dataset_hash,
        expected_manifest_hash=expected_manifest_hash,
        market_data_root=market_data_root,
        repo_root=repo_root,
        require_destination_name=True,
    )


def _request_response(
    *,
    candidate_rank: int,
    candidate_symbol: str,
    token: str,
    requested_start: date,
    requested_end: date,
    opener: Callable[..., Any],
    timeout_seconds: float,
) -> tuple[_PilotResponse, bytes | None, bool]:
    query = urlencode(
        {"startDate": requested_start.isoformat(), "endDate": requested_end.isoformat()}
    )
    request = Request(
        f"{TIINGO_EOD_ENDPOINT.format(symbol=candidate_symbol)}?{query}",
        headers={"Accept": "application/json", "Authorization": f"Token {token}"},
    )
    response = _base_response(candidate_rank, candidate_symbol)
    try:
        with opener(request, timeout=timeout_seconds) as raw_response:
            status = getattr(raw_response, "status", 200)
            if status == 404:
                return _replace_response(
                    response,
                    http_status=404,
                    classification="unavailable",
                    error_class="http_404",
                ), None, False
            if status != 200:
                return _replace_response(
                    response,
                    http_status=status if isinstance(status, int) else None,
                    classification="error",
                    error_class=_http_error_class(status),
                ), None, True
            payload = raw_response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return _replace_response(
                response,
                http_status=404,
                classification="unavailable",
                error_class="http_404",
            ), None, False
        return _replace_response(
            response,
            http_status=exc.code,
            classification="error",
            error_class=_http_error_class(exc.code),
        ), None, True
    except TiingoDailyPilotError:
        return _replace_response(
            response, classification="error", error_class="redirect_blocked"
        ), None, True
    except (OSError, URLError):
        return _replace_response(
            response, classification="error", error_class="network_error"
        ), None, True
    if not isinstance(payload, bytes) or not payload:
        return _replace_response(
            response, http_status=200, classification="error", error_class="malformed_response"
        ), None, True
    return _replace_response(response, http_status=200), payload, False


def _normalize_response(
    *,
    candidate_rank: int,
    candidate_symbol: str,
    request_identifier: str,
    payload: bytes,
    requested_start: date,
    requested_end: date,
) -> tuple[TiingoDailyPilotRow, ...]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo daily pilot payload is malformed") from exc
    if not isinstance(decoded, list):
        raise ValueError("Tiingo daily pilot payload must be an array")
    rows: list[TiingoDailyPilotRow] = []
    previous: date | None = None
    for item in decoded:
        if not isinstance(item, dict):
            raise ValueError("Tiingo daily pilot row must be an object")
        session = _session_date(item.get("date"))
        if session < requested_start or session > requested_end:
            raise ValueError("Tiingo daily pilot row is outside the requested window")
        if previous is not None and session <= previous:
            raise ValueError("Tiingo daily pilot dates must be strictly ascending")
        prices = tuple(
            _decimal(item.get(field), field) for field in ("open", "high", "low", "close")
        )
        volume = _decimal(item.get("volume"), "volume")
        div_cash = _decimal(item.get("divCash"), "divCash")
        split_factor = _decimal(item.get("splitFactor"), "splitFactor")
        _validate_raw_values(*prices, volume, div_cash, split_factor)
        rows.append(
            TiingoDailyPilotRow(
                candidate_rank=candidate_rank,
                candidate_symbol=candidate_symbol,
                request_identifier=request_identifier,
                session_date=session,
                open=prices[0],
                high=prices[1],
                low=prices[2],
                close=prices[3],
                volume=volume,
                div_cash=div_cash,
                split_factor=split_factor,
            )
        )
        previous = session
    return tuple(rows)


def _write_raw_response(
    response: _PilotResponse, *, payload: bytes, raw_dir: Path
) -> _PilotResponse:
    filename = f"{response.candidate_rank:04d}.json"
    (raw_dir / filename).write_bytes(payload)
    return _replace_response(
        response,
        raw_filename=filename,
        raw_hash=_sha256(payload),
        raw_size=len(payload),
    )


def _verify_snapshot(
    snapshot_dir: Path,
    *,
    expected_dataset_hash: str,
    expected_manifest_hash: str,
    market_data_root: Path,
    repo_root: Path | None,
    require_destination_name: bool,
) -> TiingoDailyPilotResult:
    snapshot = _validated_snapshot_dir(
        snapshot_dir,
        market_data_root=market_data_root,
        repo_root=repo_root,
        require_destination_name=require_destination_name,
    )
    manifest_bytes = _read_snapshot_file(snapshot, _MANIFEST_FILE, "Tiingo daily pilot manifest")
    if _sha256(manifest_bytes) != _required_sha256(expected_manifest_hash, "manifest hash"):
        raise ValueError("Tiingo daily pilot manifest hash mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo daily pilot manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Tiingo daily pilot manifest must be an object")
    _validate_manifest_header(manifest, snapshot=snapshot, dataset_hash=expected_dataset_hash)
    responses = _validated_responses(manifest, snapshot=snapshot)
    _validate_response_sequence(manifest, responses)
    canonical_bytes = _read_snapshot_file(
        snapshot, _CANONICAL_FILE, "Tiingo daily pilot canonical data"
    )
    if _sha256(canonical_bytes) != _required_sha256(expected_dataset_hash, "dataset hash"):
        raise ValueError("Tiingo daily pilot dataset hash mismatch")
    marker_bytes = _read_snapshot_file(
        snapshot, _RETENTION_FILE, "Tiingo daily pilot retention marker"
    )
    if marker_bytes != _retention_marker_bytes():
        raise ValueError("Tiingo daily pilot retention marker is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Tiingo daily pilot file evidence is invalid")
    marker_file = files.get("retention_marker")
    if not isinstance(marker_file, dict) or marker_file != {
        "path": _RETENTION_FILE,
        "sha256": _sha256(marker_bytes),
        "size_bytes": len(marker_bytes),
    }:
        raise ValueError("Tiingo daily pilot retention evidence is invalid")
    canonical_file = files.get("canonical_raw_fields")
    if not isinstance(canonical_file, dict) or canonical_file != {
        "path": _CANONICAL_FILE,
        "sha256": _sha256(canonical_bytes),
        "size_bytes": len(canonical_bytes),
        "format": "csv.gz",
        "columns": list(_RAW_COLUMNS),
        "ordering": "candidate_rank_then_date_ascending",
    }:
        raise ValueError("Tiingo daily pilot canonical evidence is invalid")
    reconstructed_rows = _rows_from_responses(
        snapshot=snapshot,
        responses=responses,
        requested_start=_date_value(manifest.get("requested_window", {}).get("start")),
        requested_end=_date_value(manifest.get("requested_window", {}).get("end")),
    )
    expected_canonical = _gzip_bytes(_canonical_csv_bytes(reconstructed_rows))
    if canonical_bytes != expected_canonical:
        raise ValueError("Tiingo daily pilot canonical data does not match raw evidence")
    aggregate = _aggregate(responses)
    if manifest.get("aggregate") != aggregate:
        raise ValueError("Tiingo daily pilot aggregate is invalid")
    _validate_storage_manifest(manifest, market_data_root=market_data_root)
    return TiingoDailyPilotResult(
        snapshot_dir=snapshot,
        dataset_hash=_sha256(canonical_bytes),
        manifest_hash=_sha256(manifest_bytes),
        completed=manifest.get("completed") is True,
        stop_reason=_optional_text(manifest.get("stop_reason")),
        request_count=len(responses),
        available_count=aggregate["available"],
        empty_count=aggregate["empty"],
        unavailable_count=aggregate["unavailable"],
        row_count=len(reconstructed_rows),
        free_percent=_nonnegative_float(
            manifest.get("storage", {}).get("free_percent")
            if isinstance(manifest.get("storage"), dict)
            else None,
            "storage free percent",
        ),
    )


def _validate_manifest_header(
    manifest: dict[str, object], *, snapshot: Path, dataset_hash: str
) -> None:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "tiingo_standard_eod_daily_pilot"
        or manifest.get("pilot_version") != TIINGO_DAILY_PILOT_VERSION
        or manifest.get("dataset_id") != _dataset_id(snapshot)
        or manifest.get("dataset_hash") != _required_sha256(dataset_hash, "dataset hash")
        or manifest.get("immutable_snapshot") is not True
    ):
        raise ValueError("Tiingo daily pilot manifest header is invalid")
    if manifest.get("scope") != _scope():
        raise ValueError("Tiingo daily pilot scope is invalid")
    if manifest.get("source_contract") != _source_contract():
        raise ValueError("Tiingo daily pilot source contract is invalid")
    if manifest.get("rights") != _rights_contract():
        raise ValueError("Tiingo daily pilot rights contract is invalid")
    requested_window = manifest.get("requested_window")
    if not isinstance(requested_window, dict):
        raise ValueError("Tiingo daily pilot requested window is invalid")
    _validate_window(
        _date_value(requested_window.get("start")), _date_value(requested_window.get("end"))
    )
    candidate_union = manifest.get("candidate_union")
    if not isinstance(candidate_union, dict):
        raise ValueError("Tiingo daily pilot candidate union is invalid")
    candidate_count = _positive_int(candidate_union.get("candidate_count"), "candidate count")
    _required_sha256(candidate_union.get("sha256"), "candidate union hash")
    if (
        not isinstance(candidate_union.get("path"), str)
        or not candidate_union["path"].strip()
        or candidate_union.get("selection_algorithm") != "rank_quantile_inclusive_v1"
    ):
        raise ValueError("Tiingo daily pilot candidate union is invalid")
    ranks = candidate_union.get("selected_ranks")
    if not isinstance(ranks, list) or not 1 <= len(ranks) <= MAX_TIINGO_DAILY_PILOT_REQUESTS:
        raise ValueError("Tiingo daily pilot selected ranks are invalid")
    expected_ranks = rank_quantile_ranks(candidate_count, sample_size=len(ranks))
    if ranks != list(expected_ranks):
        raise ValueError("Tiingo daily pilot selected ranks are invalid")
    if candidate_union.get("symbols_persisted_external_only") is not True:
        raise ValueError("Tiingo daily pilot candidate privacy scope is invalid")


def _validate_response_sequence(
    manifest: dict[str, object], responses: Sequence[_PilotResponse]
) -> None:
    candidate_union = manifest.get("candidate_union")
    if not isinstance(candidate_union, dict):
        raise ValueError("Tiingo daily pilot candidate union is invalid")
    selected_ranks = candidate_union.get("selected_ranks")
    if not isinstance(selected_ranks, list):
        raise ValueError("Tiingo daily pilot selected ranks are invalid")
    response_ranks = [response.candidate_rank for response in responses]
    if response_ranks != selected_ranks[: len(response_ranks)]:
        raise ValueError("Tiingo daily pilot response order does not match the fixed selection")
    completed = manifest.get("completed")
    stop_reason = _optional_text(manifest.get("stop_reason"))
    if completed is True:
        if len(responses) != len(selected_ranks) or stop_reason is not None:
            raise ValueError("Tiingo daily pilot completed state is invalid")
        if any(response.classification == "error" for response in responses):
            raise ValueError("Tiingo daily pilot completed state has an error")
        return
    if completed is not False or not responses:
        raise ValueError("Tiingo daily pilot stopped state is invalid")
    last = responses[-1]
    if last.classification != "error" or stop_reason != last.error_class:
        raise ValueError("Tiingo daily pilot stop reason is invalid")


def _validate_response_contract(response: _PilotResponse) -> None:
    if response.classification in {"available", "empty"}:
        if (
            response.http_status != 200
            or response.error_class is not None
            or response.raw_filename is None
        ):
            raise ValueError("Tiingo daily pilot successful response is invalid")
        if response.classification == "available":
            if (
                response.row_count is None
                or response.row_count <= 0
                or response.first_session is None
                or response.last_session is None
            ):
                raise ValueError("Tiingo daily pilot available response is invalid")
        elif (
            response.row_count != 0
            or response.first_session is not None
            or response.last_session is not None
        ):
            raise ValueError("Tiingo daily pilot empty response is invalid")
        return
    if response.classification == "unavailable":
        if (
            response.http_status != 404
            or response.error_class != "http_404"
            or response.raw_filename is not None
            or response.row_count is not None
            or response.first_session is not None
            or response.last_session is not None
        ):
            raise ValueError("Tiingo daily pilot unavailable response is invalid")
        return
    if response.classification != "error" or response.error_class is None:
        raise ValueError("Tiingo daily pilot error response is invalid")
    if (
        response.row_count is not None
        or response.first_session is not None
        or response.last_session is not None
    ):
        raise ValueError("Tiingo daily pilot error response is invalid")


def _validate_storage_manifest(manifest: dict[str, object], *, market_data_root: Path) -> None:
    storage = manifest.get("storage")
    if not isinstance(storage, dict):
        raise ValueError("Tiingo daily pilot storage evidence is invalid")
    if storage.get("root") != str(Path(market_data_root).resolve()):
        raise ValueError("Tiingo daily pilot storage root is invalid")
    if (
        _nonnegative_float(storage.get("free_percent"), "storage free percent") < 15
        or storage.get("warning_floor_percent") != 20
        or storage.get("hard_floor_percent") != 15
    ):
        raise ValueError("Tiingo daily pilot storage evidence is invalid")


def _validated_responses(
    manifest: dict[str, object], *, snapshot: Path
) -> tuple[_PilotResponse, ...]:
    raw_sources = manifest.get("raw_sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Tiingo daily pilot raw evidence is invalid")
    if len(raw_sources) > MAX_TIINGO_DAILY_PILOT_REQUESTS:
        raise ValueError("Tiingo daily pilot raw evidence exceeds the request cap")
    responses: list[_PilotResponse] = []
    ranks: set[int] = set()
    for entry in raw_sources:
        if not isinstance(entry, dict):
            raise ValueError("Tiingo daily pilot raw evidence is invalid")
        rank = _positive_int(entry.get("candidate_rank"), "candidate rank")
        candidate_symbol = _symbol(entry.get("candidate_symbol"))
        request_identifier = _symbol(entry.get("request_identifier"))
        if request_identifier != candidate_symbol or rank in ranks:
            raise ValueError("Tiingo daily pilot symbol mapping is invalid")
        ranks.add(rank)
        classification = entry.get("classification")
        if classification not in {"available", "empty", "unavailable", "error"}:
            raise ValueError("Tiingo daily pilot response classification is invalid")
        status = entry.get("http_status")
        if status is not None and (not isinstance(status, int) or isinstance(status, bool)):
            raise ValueError("Tiingo daily pilot HTTP status is invalid")
        row_count = entry.get("row_count")
        if row_count is not None and (
            not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0
        ):
            raise ValueError("Tiingo daily pilot row count is invalid")
        first = _optional_date(entry.get("first_session"))
        last = _optional_date(entry.get("last_session"))
        error_class = _optional_text(entry.get("error_class"))
        filename = _optional_text(entry.get("raw_filename"))
        raw_hash = _optional_text(entry.get("raw_sha256"))
        raw_size = entry.get("raw_size_bytes")
        if filename is None:
            if raw_hash is not None or raw_size is not None:
                raise ValueError("Tiingo daily pilot raw evidence is invalid")
        else:
            if filename != f"{rank:04d}.json" or raw_hash is None or raw_size is None:
                raise ValueError("Tiingo daily pilot raw evidence is invalid")
            raw = _read_snapshot_file(
                snapshot, f"raw/{filename}", "Tiingo daily pilot raw response"
            )
            if _sha256(raw) != _required_sha256(raw_hash, "raw response hash"):
                raise ValueError("Tiingo daily pilot raw hash mismatch")
            if raw_size != len(raw):
                raise ValueError("Tiingo daily pilot raw size is inconsistent")
        response = _PilotResponse(
            candidate_rank=rank,
            candidate_symbol=candidate_symbol,
            request_identifier=request_identifier,
            http_status=status,
            classification=classification,
            row_count=row_count,
            first_session=first,
            last_session=last,
            error_class=error_class,
            raw_filename=filename,
            raw_hash=raw_hash,
            raw_size=raw_size if isinstance(raw_size, int) else None,
        )
        _validate_response_contract(response)
        responses.append(response)
    if tuple(response.candidate_rank for response in responses) != tuple(sorted(ranks)):
        raise ValueError("Tiingo daily pilot raw response order is invalid")
    return tuple(responses)


def _rows_from_responses(
    *,
    snapshot: Path,
    responses: Sequence[_PilotResponse],
    requested_start: date,
    requested_end: date,
) -> tuple[TiingoDailyPilotRow, ...]:
    rows: list[TiingoDailyPilotRow] = []
    for response in responses:
        if response.raw_filename is None:
            if response.classification not in {"unavailable", "error"}:
                raise ValueError("Tiingo daily pilot response is missing raw evidence")
            continue
        if response.classification == "error":
            continue
        raw = _read_snapshot_file(
            snapshot, f"raw/{response.raw_filename}", "Tiingo daily pilot raw"
        )
        normalized = _normalize_response(
            candidate_rank=response.candidate_rank,
            candidate_symbol=response.candidate_symbol,
            request_identifier=response.request_identifier,
            payload=raw,
            requested_start=requested_start,
            requested_end=requested_end,
        )
        if response.classification == "available" and not normalized:
            raise ValueError("Tiingo daily pilot available response is empty")
        if response.classification == "empty" and normalized:
            raise ValueError("Tiingo daily pilot empty response has rows")
        if response.row_count != len(normalized):
            raise ValueError("Tiingo daily pilot response row count is inconsistent")
        if normalized:
            if (
                response.first_session != normalized[0].session_date
                or response.last_session != normalized[-1].session_date
            ):
                raise ValueError("Tiingo daily pilot response coverage is inconsistent")
        rows.extend(normalized)
    return tuple(rows)


def _manifest(
    *,
    snapshot_dir: Path,
    selection: NorgateCandidateSelection,
    candidate_union_path: Path,
    responses: tuple[_PilotResponse, ...],
    dataset_hash: str,
    dataset_size: int,
    row_count: int,
    marker_hash: str,
    marker_size: int,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    stop_reason: str | None,
    free_percent: float,
    market_data_root: Path,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "tiingo_standard_eod_daily_pilot",
        "pilot_version": TIINGO_DAILY_PILOT_VERSION,
        "dataset_id": _dataset_id(snapshot_dir),
        "dataset_hash": dataset_hash,
        "immutable_snapshot": True,
        "completed": stop_reason is None,
        "stop_reason": stop_reason,
        "candidate_union": {
            "path": str(Path(candidate_union_path).resolve()),
            "sha256": selection.candidate_union_hash,
            "candidate_count": selection.candidate_count,
            "selection_algorithm": "rank_quantile_inclusive_v1",
            "selected_ranks": list(selection.selected_ranks),
            "symbols_persisted_external_only": True,
        },
        "requested_window": {
            "start": requested_start.isoformat(),
            "end": requested_end.isoformat(),
        },
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "source_contract": _source_contract(),
        "rights": _rights_contract(),
        "raw_sources": [_response_document(response) for response in responses],
        "aggregate": _aggregate(responses),
        "files": {
            "canonical_raw_fields": {
                "path": _CANONICAL_FILE,
                "sha256": dataset_hash,
                "size_bytes": dataset_size,
                "format": "csv.gz",
                "columns": list(_RAW_COLUMNS),
                "ordering": "candidate_rank_then_date_ascending",
            },
            "retention_marker": {
                "path": _RETENTION_FILE,
                "sha256": marker_hash,
                "size_bytes": marker_size,
            },
        },
        "storage": {
            "root": str(Path(market_data_root).resolve()),
            "free_percent": free_percent,
            "warning_floor_percent": 20,
            "hard_floor_percent": 15,
        },
        "scope": _scope(),
        "limitations": [
            "The candidate union has no as-of date and is not a historical tradable universe.",
            "A missing or empty response is a recorded gap, not a replacement opportunity.",
            "Raw payloads and candidate identifiers are private external evidence only.",
        ],
    }


def _response_document(response: _PilotResponse) -> dict[str, object]:
    return {
        "candidate_rank": response.candidate_rank,
        "candidate_symbol": response.candidate_symbol,
        "request_identifier": response.request_identifier,
        "http_status": response.http_status,
        "classification": response.classification,
        "row_count": response.row_count,
        "first_session": response.first_session.isoformat() if response.first_session else None,
        "last_session": response.last_session.isoformat() if response.last_session else None,
        "error_class": response.error_class,
        "raw_filename": response.raw_filename,
        "raw_sha256": response.raw_hash,
        "raw_size_bytes": response.raw_size,
    }


def _aggregate(responses: Sequence[_PilotResponse]) -> dict[str, int]:
    classifications = [response.classification for response in responses]
    return {
        "request_count": len(responses),
        "available": classifications.count("available"),
        "empty": classifications.count("empty"),
        "unavailable": classifications.count("unavailable"),
        "errors": classifications.count("error"),
    }


def _source_contract() -> dict[str, object]:
    return {
        "provider": "Tiingo standard EOD API",
        "endpoint_template": TIINGO_EOD_ENDPOINT,
        "authentication": "approved_Tiingo_token_only",
        "request_budget": MAX_TIINGO_DAILY_PILOT_REQUESTS,
        "observed_hourly_request_limit": 50,
        "retry_count": 0,
        "symbol_transform": "none",
        "raw_response_policy": "exact_rank_named_bytes",
    }


def _rights_contract() -> dict[str, object]:
    return {
        "terms_url": TIINGO_TERMS_URL,
        "terms_retrieved_date": TIINGO_TERMS_RETRIEVED_DATE.isoformat(),
        "internal_use_clause": TIINGO_INTERNAL_USE_CLAUSE,
        "redistribution": "not_permitted",
        "retention_marker": _RETENTION_FILE,
    }


def _scope() -> dict[str, bool]:
    return {
        "private_internal_use_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
        "campaign_eligible": False,
        "model_eligible": False,
        "gpu_eligible": False,
        "paper_trading_eligible": False,
    }


def _retention_marker_bytes() -> bytes:
    return (
        "This directory contains Tiingo API data for private internal use only.\n"
        f"Terms source: {TIINGO_TERMS_URL}\n"
        f"Terms retrieved: {TIINGO_TERMS_RETRIEVED_DATE.isoformat()}\n"
        f"Internal-use clause: {TIINGO_INTERNAL_USE_CLAUSE}\n"
        "Do not redistribute this data.\n"
        "If account entitlement or applicable terms require deletion, the operator must delete\n"
        "this snapshot directory and its derived copies. This marker records scope only.\n"
    ).encode("ascii")


def _canonical_csv_bytes(rows: Sequence[TiingoDailyPilotRow]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_RAW_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "candidate_rank": row.candidate_rank,
                "candidate_symbol": row.candidate_symbol,
                "request_identifier": row.request_identifier,
                "date": row.session_date.isoformat(),
                "open": format(row.open, "f"),
                "high": format(row.high, "f"),
                "low": format(row.low, "f"),
                "close": format(row.close, "f"),
                "volume": format(row.volume, "f"),
                "div_cash": format(row.div_cash, "f"),
                "split_factor": format(row.split_factor, "f"),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _validate_destination(
    destination: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Tiingo daily pilot market-data root must exist")
    root = root.resolve()
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo daily pilot market-data root must stay outside Git")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Tiingo daily pilot destination already exists")
    target = target.resolve()
    if repo_root is not None and target.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo daily pilot destination must stay outside Git")
    if not target.is_relative_to(root):
        raise ValueError("Tiingo daily pilot destination must stay under market data")
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Tiingo daily pilot destination must use the required snapshot name")
    return target, root


def _assert_no_staging_residue(destination: Path) -> None:
    if destination.parent.is_dir() and any(
        list(destination.parent.glob(".stage-*"))
        + list(destination.parent.glob(".rejected-*"))
    ):
        raise FileExistsError("Tiingo daily pilot staging residue requires recovery")


def _quarantine_failed_snapshot(destination: Path) -> Path:
    """Keep a published but unverified external snapshot for manual recovery."""

    quarantined = destination.parent / f".rejected-{destination.name}-{uuid.uuid4().hex}"
    try:
        os.rename(destination, quarantined)
    except OSError:
        return destination
    return quarantined


def _validated_snapshot_dir(
    snapshot_dir: Path,
    *,
    market_data_root: Path,
    repo_root: Path | None,
    require_destination_name: bool,
) -> Path:
    root = Path(market_data_root).resolve()
    snapshot = Path(snapshot_dir)
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise ValueError("Tiingo daily pilot snapshot must be a directory")
    snapshot = snapshot.resolve()
    if not snapshot.is_relative_to(root):
        raise ValueError("Tiingo daily pilot snapshot must stay under market data")
    if repo_root is not None and snapshot.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo daily pilot snapshot must stay outside Git")
    if require_destination_name and (
        not snapshot.name.startswith("snapshot=") or not snapshot.name.endswith(_SNAPSHOT_SUFFIX)
    ):
        raise ValueError("Tiingo daily pilot snapshot name is invalid")
    return snapshot


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Tiingo daily pilot storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Tiingo daily pilot storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn(
            "Tiingo daily pilot storage is below the warning free-space floor",
            stacklevel=2,
        )
    return free_percent


def _create_staging_directory(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".stage-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _read_snapshot_file(snapshot: Path, relative_path: str, label: str) -> bytes:
    path = snapshot / relative_path
    if path.is_symlink() or not path.resolve(strict=False).is_relative_to(snapshot):
        raise ValueError(f"{label} path is invalid")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing") from exc
    if not resolved.is_file() or not resolved.is_relative_to(snapshot):
        raise ValueError(f"{label} must be a regular file inside the snapshot")
    return resolved.read_bytes()


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)


def _base_response(candidate_rank: int, candidate_symbol: str) -> _PilotResponse:
    return _PilotResponse(
        candidate_rank=candidate_rank,
        candidate_symbol=candidate_symbol,
        request_identifier=candidate_symbol,
        http_status=None,
        classification="pending",
        row_count=None,
        first_session=None,
        last_session=None,
        error_class=None,
        raw_filename=None,
        raw_hash=None,
        raw_size=None,
    )


def _replace_response(response: _PilotResponse, **changes: object) -> _PilotResponse:
    values = {
        "candidate_rank": response.candidate_rank,
        "candidate_symbol": response.candidate_symbol,
        "request_identifier": response.request_identifier,
        "http_status": response.http_status,
        "classification": response.classification,
        "row_count": response.row_count,
        "first_session": response.first_session,
        "last_session": response.last_session,
        "error_class": response.error_class,
        "raw_filename": response.raw_filename,
        "raw_hash": response.raw_hash,
        "raw_size": response.raw_size,
    }
    values.update(changes)
    return _PilotResponse(**values)


def _session_date(value: object) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError("Tiingo daily pilot date is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Tiingo daily pilot date is invalid") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != UTC.utcoffset(parsed)
        or parsed.timetz().replace(tzinfo=None) != time()
    ):
        raise ValueError("Tiingo daily pilot date is invalid")
    return parsed.date()


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or value is None or not isinstance(value, (int, float, str)):
        raise ValueError(f"Tiingo daily pilot {field} is invalid")
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"Tiingo daily pilot {field} is invalid") from exc
    if not parsed.is_finite():
        raise ValueError(f"Tiingo daily pilot {field} is invalid")
    return parsed


def _validate_raw_values(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    volume: Decimal,
    div_cash: Decimal,
    split_factor: Decimal,
) -> None:
    prices = (open_price, high_price, low_price, close_price)
    if any(value <= 0 for value in prices) or volume < 0 or div_cash < 0 or split_factor <= 0:
        raise ValueError("Tiingo daily pilot raw values are invalid")
    if high_price < max(prices) or low_price > min(prices):
        raise ValueError("Tiingo daily pilot raw OHLC range is invalid")


def _validate_window(requested_start: date, requested_end: date) -> None:
    if type(requested_start) is not date or type(requested_end) is not date:
        raise ValueError("Tiingo daily pilot dates must be dates")
    if requested_end < requested_start:
        raise ValueError("Tiingo daily pilot requested window is invalid")


def _date_value(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Tiingo daily pilot date value is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Tiingo daily pilot date value is invalid") from exc


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    return _date_value(value)


def _symbol(value: object) -> str:
    symbol = str(value or "")
    if not symbol or symbol != symbol.strip() or symbol != symbol.upper() or "\n" in symbol:
        raise ValueError("Tiingo daily pilot symbol is invalid")
    return symbol


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text or text != text.strip():
        raise ValueError("Tiingo daily pilot text is invalid")
    return text


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Tiingo daily pilot {label} is invalid")
    return value


def _nonnegative_float(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Tiingo daily pilot {label} is invalid")
    return float(value)


def _required_sha256(value: object, label: str) -> str:
    text = str(value or "")
    if len(text) != 71 or not text.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in text[7:]
    ):
        raise ValueError(f"Tiingo daily pilot {label} is invalid")
    return text


def _http_error_class(status: object) -> str:
    return f"http_{status}" if isinstance(status, int) else "unexpected_http_status"


def _dataset_id(snapshot_dir: Path) -> str:
    return f"us_equities.tiingo_standard_eod_daily_pilot.{Path(snapshot_dir).name}"


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

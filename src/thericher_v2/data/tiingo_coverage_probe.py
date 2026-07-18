"""Bounded, symbol-private Tiingo standard-EOD coverage probe."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import shutil
import uuid
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .tiingo_eod import TIINGO_EOD_ENDPOINT, read_tiingo_api_token

DEFAULT_MARKET_DATA_ROOT = Path("D:/market_data")
DEFAULT_PROBE_ARTIFACT_ROOT = (
    Path("D:/thericher-v2/model-artifacts/data-agent/tiingo-eod-coverage-probe")
)
MAX_TIINGO_COVERAGE_REQUESTS = 12
DEFAULT_TIINGO_COVERAGE_SAMPLE_SIZE = 12
TIINGO_COVERAGE_PROBE_VERSION = "tiingo-eod-coverage-probe-r1"
_CANDIDATE_COLUMNS = ("candidate_rank", "symbol")
_SUMMARY_FILE = "summary.json"
_SNAPSHOT_SUFFIX = "-tiingo-eod-coverage-probe-r1"
_SELECTION_ALGORITHM = "rank_quantile_inclusive_v1"


class TiingoCoverageProbeError(RuntimeError):
    """A masked failure for the bounded Tiingo coverage probe."""


class _RejectRedirect(HTTPRedirectHandler):
    """Keep the approved token from being forwarded to another URL."""

    def redirect_request(
        self,
        _request: Request,
        _file: Any,
        _code: int,
        _message: str,
        _headers: Any,
        _new_url: str,
    ) -> Request:
        raise TiingoCoverageProbeError("Tiingo coverage redirects are not allowed")


@dataclass(frozen=True, slots=True)
class TiingoCoverageSelection:
    """In-memory candidate selection; symbols must never be serialized."""

    candidate_count: int
    candidate_union_hash: str
    selected_ranks: tuple[int, ...]
    selected_symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TiingoCoverageResponse:
    """Non-raw metadata for one requested sample position."""

    candidate_rank: int
    http_status: int | None
    classification: str
    row_count: int | None
    first_session: date | None
    last_session: date | None
    error_class: str | None


@dataclass(frozen=True, slots=True)
class TiingoCoverageProbeResult:
    """Safe facts from one immutable external coverage summary."""

    summary_path: Path
    summary_hash: str
    completed: bool
    stop_reason: str | None
    request_count: int
    available_count: int
    empty_count: int
    unavailable_count: int
    free_percent: float


def default_tiingo_coverage_probe_dir(retrieval_date: date) -> Path:
    """Return the one-date external artifact destination for this probe revision."""

    if isinstance(retrieval_date, datetime):
        raise ValueError("Tiingo coverage retrieval date must not include a time")
    return DEFAULT_PROBE_ARTIFACT_ROOT / (
        f"snapshot={retrieval_date.isoformat()}{_SNAPSHOT_SUFFIX}"
    )


def load_tiingo_coverage_selection(
    *,
    candidate_union_path: Path,
    candidate_union_manifest_path: Path,
    expected_candidate_union_hash: str,
    sample_size: int = DEFAULT_TIINGO_COVERAGE_SAMPLE_SIZE,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    repo_root: Path | None = None,
) -> TiingoCoverageSelection:
    """Load one validated external union and choose deterministic quantile ranks."""

    if not 1 <= sample_size <= MAX_TIINGO_COVERAGE_REQUESTS:
        raise ValueError("Tiingo coverage sample size is outside the request budget")
    root = _validated_external_root(market_data_root, repo_root=repo_root)
    candidate_path = _validated_external_file(
        candidate_union_path, root=root, repo_root=repo_root, label="candidate union"
    )
    manifest_path = _validated_external_file(
        candidate_union_manifest_path, root=root, repo_root=repo_root, label="candidate manifest"
    )
    expected_hash = _required_sha256(expected_candidate_union_hash, "candidate union hash")
    candidate_bytes = candidate_path.read_bytes()
    candidate_hash = _sha256(candidate_bytes)
    if candidate_hash != expected_hash:
        raise ValueError("Tiingo coverage candidate union hash mismatch")
    manifest = _load_candidate_manifest(manifest_path)
    _validate_candidate_manifest(
        manifest,
        candidate_path=candidate_path,
        candidate_hash=candidate_hash,
    )
    candidates = _parse_ranked_candidates(candidate_bytes)
    candidate_count = _positive_int(manifest.get("candidate_count"), "candidate count")
    if len(candidates) != candidate_count:
        raise ValueError("Tiingo coverage candidate count is inconsistent")
    if candidate_count < sample_size:
        raise ValueError("Tiingo coverage candidate union is smaller than the sample")
    selected_ranks = _quantile_ranks(candidate_count, sample_size)
    return TiingoCoverageSelection(
        candidate_count=candidate_count,
        candidate_union_hash=candidate_hash,
        selected_ranks=selected_ranks,
        selected_symbols=tuple(candidates[rank - 1] for rank in selected_ranks),
    )


def run_tiingo_eod_coverage_probe(
    *,
    candidate_union_path: Path,
    candidate_union_manifest_path: Path,
    expected_candidate_union_hash: str,
    env_path: Path,
    destination: Path,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    sample_size: int = DEFAULT_TIINGO_COVERAGE_SAMPLE_SIZE,
    market_data_root: Path = DEFAULT_MARKET_DATA_ROOT,
    artifact_root: Path = DEFAULT_PROBE_ARTIFACT_ROOT,
    repo_root: Path | None = None,
    opener: Callable[..., Any] | None = None,
    timeout_seconds: float = 20.0,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
) -> TiingoCoverageProbeResult:
    """Make at most twelve approved-token requests and retain only safe metadata."""

    _validate_window(requested_start, requested_end)
    retrieved_at = _utc_datetime(retrieved_at_utc, "Tiingo coverage retrieval time")
    if timeout_seconds <= 0:
        raise ValueError("Tiingo coverage timeout must be positive")
    selection = load_tiingo_coverage_selection(
        candidate_union_path=candidate_union_path,
        candidate_union_manifest_path=candidate_union_manifest_path,
        expected_candidate_union_hash=expected_candidate_union_hash,
        sample_size=sample_size,
        market_data_root=market_data_root,
        repo_root=repo_root,
    )
    target, resolved_artifact_root = _validate_destination(
        destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    free_percent = _validate_storage(resolved_artifact_root, disk_usage=disk_usage)
    request_opener = opener or _open_without_redirect
    token = read_tiingo_api_token(env_path)

    responses: list[TiingoCoverageResponse] = []
    stop_reason: str | None = None
    for candidate_rank, symbol in zip(
        selection.selected_ranks, selection.selected_symbols, strict=True
    ):
        response, should_stop = _request_coverage(
            symbol=symbol,
            candidate_rank=candidate_rank,
            token=token,
            requested_start=requested_start,
            requested_end=requested_end,
            opener=request_opener,
            timeout_seconds=timeout_seconds,
        )
        responses.append(response)
        if should_stop:
            stop_reason = response.error_class or "request_error"
            break

    summary = _summary_document(
        selection=selection,
        responses=tuple(responses),
        stop_reason=stop_reason,
        requested_start=requested_start,
        requested_end=requested_end,
        retrieved_at_utc=retrieved_at,
        candidate_union_path=candidate_union_path,
        free_percent=free_percent,
    )
    summary_bytes = _json_bytes(summary)
    summary_path = _publish_summary(target, summary_bytes)
    classifications = [response.classification for response in responses]
    return TiingoCoverageProbeResult(
        summary_path=summary_path,
        summary_hash=_sha256(summary_bytes),
        completed=stop_reason is None,
        stop_reason=stop_reason,
        request_count=len(responses),
        available_count=classifications.count("available"),
        empty_count=classifications.count("empty"),
        unavailable_count=classifications.count("unavailable"),
        free_percent=free_percent,
    )


def _request_coverage(
    *,
    symbol: str,
    candidate_rank: int,
    token: str,
    requested_start: date,
    requested_end: date,
    opener: Callable[..., Any],
    timeout_seconds: float,
) -> tuple[TiingoCoverageResponse, bool]:
    query = urlencode(
        {"startDate": requested_start.isoformat(), "endDate": requested_end.isoformat()}
    )
    request = Request(
        f"{TIINGO_EOD_ENDPOINT.format(symbol=symbol)}?{query}",
        headers={"Accept": "application/json", "Authorization": f"Token {token}"},
    )
    try:
        with opener(request, timeout=timeout_seconds) as raw_response:
            status = getattr(raw_response, "status", 200)
            if status == 404:
                return _error_response(candidate_rank, 404, "unavailable", "http_404"), False
            if status != 200:
                return _error_response(
                    candidate_rank,
                    status if isinstance(status, int) else None,
                    "error",
                    _http_error_class(status),
                ), True
            payload = raw_response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return _error_response(candidate_rank, 404, "unavailable", "http_404"), False
        return _error_response(candidate_rank, exc.code, "error", _http_error_class(exc.code)), True
    except TiingoCoverageProbeError:
        return _error_response(candidate_rank, None, "error", "redirect_blocked"), True
    except (OSError, URLError):
        return _error_response(candidate_rank, None, "error", "network_error"), True

    try:
        row_count, first_session, last_session = _coverage_dates(
            payload,
            requested_start=requested_start,
            requested_end=requested_end,
        )
    except ValueError:
        return _error_response(candidate_rank, 200, "error", "malformed_response"), True
    if row_count == 0:
        return (
            TiingoCoverageResponse(
                candidate_rank=candidate_rank,
                http_status=200,
                classification="empty",
                row_count=0,
                first_session=None,
                last_session=None,
                error_class=None,
            ),
            False,
        )
    return (
        TiingoCoverageResponse(
            candidate_rank=candidate_rank,
            http_status=200,
            classification="available",
            row_count=row_count,
            first_session=first_session,
            last_session=last_session,
            error_class=None,
        ),
        False,
    )


def _coverage_dates(
    payload: object,
    *,
    requested_start: date,
    requested_end: date,
) -> tuple[int, date | None, date | None]:
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("Tiingo coverage payload is unavailable")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo coverage payload is malformed") from exc
    if not isinstance(decoded, list):
        raise ValueError("Tiingo coverage payload must be an array")
    previous: date | None = None
    for item in decoded:
        if not isinstance(item, dict):
            raise ValueError("Tiingo coverage row must be an object")
        session = _session_date(item.get("date"))
        if session < requested_start or session > requested_end:
            raise ValueError("Tiingo coverage row is outside the requested window")
        if previous is not None and session <= previous:
            raise ValueError("Tiingo coverage dates must be strictly ascending")
        previous = session
    return len(decoded), _session_date(decoded[0]["date"]) if decoded else None, previous


def _summary_document(
    *,
    selection: TiingoCoverageSelection,
    responses: tuple[TiingoCoverageResponse, ...],
    stop_reason: str | None,
    requested_start: date,
    requested_end: date,
    retrieved_at_utc: datetime,
    candidate_union_path: Path,
    free_percent: float,
) -> dict[str, object]:
    classifications = [response.classification for response in responses]
    return {
        "schema_version": 1,
        "kind": "tiingo_standard_eod_coverage_probe",
        "probe_version": TIINGO_COVERAGE_PROBE_VERSION,
        "retrieved_at_utc": _format_utc(retrieved_at_utc),
        "completed": stop_reason is None,
        "stop_reason": stop_reason,
        "candidate_union": {
            "path": str(Path(candidate_union_path).resolve()),
            "sha256": selection.candidate_union_hash,
            "candidate_count": selection.candidate_count,
            "selection_algorithm": _SELECTION_ALGORITHM,
            "sample_size": len(selection.selected_ranks),
            "selected_ranks": list(selection.selected_ranks),
            "selected_symbols_persisted": False,
        },
        "source_contract": {
            "provider": "Tiingo standard EOD API",
            "endpoint_template": TIINGO_EOD_ENDPOINT,
            "authentication": "approved_Tiingo_token_only",
            "client": "stdlib_urllib_no_redirect",
            "python_version": platform.python_version(),
        },
        "requested_window": {
            "start": requested_start.isoformat(),
            "end": requested_end.isoformat(),
        },
        "request_budget": {
            "maximum": MAX_TIINGO_COVERAGE_REQUESTS,
            "issued": len(responses),
            "retries": 0,
        },
        "aggregate": {
            "available": classifications.count("available"),
            "empty": classifications.count("empty"),
            "unavailable": classifications.count("unavailable"),
            "errors": classifications.count("error"),
        },
        "responses": [_response_document(response) for response in responses],
        "storage": {
            "free_percent": free_percent,
            "warning_floor_percent": 20,
            "hard_floor_percent": 15,
        },
        "scope": {
            "coverage_probe_only": True,
            "market_data_snapshot_created": False,
            "universe_claim_eligible": False,
            "point_in_time_eligible": False,
            "campaign_eligible": False,
            "model_eligible": False,
            "gpu_eligible": False,
            "paper_trading_eligible": False,
        },
        "limitations": [
            "No selected symbols, raw API responses, prices, or volumes are persisted.",
            "A successful response proves only bounded endpoint reachability and returned rows.",
            "This probe does not establish point-in-time membership, data rights, or model "
            "eligibility.",
        ],
    }


def _response_document(response: TiingoCoverageResponse) -> dict[str, object]:
    return {
        "candidate_rank": response.candidate_rank,
        "http_status": response.http_status,
        "classification": response.classification,
        "row_count": response.row_count,
        "first_session": response.first_session.isoformat() if response.first_session else None,
        "last_session": response.last_session.isoformat() if response.last_session else None,
        "error_class": response.error_class,
    }


def _load_candidate_manifest(path: Path) -> dict[str, object]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Tiingo coverage candidate manifest is invalid") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Tiingo coverage candidate manifest must be an object")
    return parsed


def _validate_candidate_manifest(
    manifest: dict[str, object],
    *,
    candidate_path: Path,
    candidate_hash: str,
) -> None:
    if (manifest.get("schema_version"), manifest.get("kind")) != (
        1,
        "norgate_sp500_current_past_membership_matrix",
    ):
        raise ValueError("Tiingo coverage candidate manifest schema is invalid")
    scope = manifest.get("scope")
    if not isinstance(scope, dict) or any(
        scope.get(key) is not False
        for key in (
            "direct_historical_universe_list",
            "publication_time_proven",
            "pit_eligible",
            "campaign_eligible",
            "model_eligible",
        )
    ):
        raise ValueError("Tiingo coverage candidate manifest scope is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Tiingo coverage candidate manifest files are invalid")
    candidate_file = files.get("candidate_union")
    if not isinstance(candidate_file, dict):
        raise ValueError("Tiingo coverage candidate manifest lineage is invalid")
    if candidate_file.get("path") != candidate_path.name:
        raise ValueError("Tiingo coverage candidate manifest path is invalid")
    if _required_sha256(candidate_file.get("sha256"), "manifest candidate hash") != candidate_hash:
        raise ValueError("Tiingo coverage candidate manifest hash mismatch")
    if candidate_file.get("size_bytes") != candidate_path.stat().st_size:
        raise ValueError("Tiingo coverage candidate manifest size is inconsistent")
    if tuple(candidate_file.get("columns", ())) != _CANDIDATE_COLUMNS:
        raise ValueError("Tiingo coverage candidate manifest columns are invalid")


def _parse_ranked_candidates(candidate_bytes: bytes) -> tuple[str, ...]:
    try:
        reader = csv.DictReader(io.StringIO(candidate_bytes.decode("utf-8"), newline=""))
    except UnicodeDecodeError as exc:
        raise ValueError("Tiingo coverage candidate union is not UTF-8") from exc
    if tuple(reader.fieldnames or ()) != _CANDIDATE_COLUMNS:
        raise ValueError("Tiingo coverage candidate union columns are invalid")
    candidates: list[str] = []
    for expected_rank, row in enumerate(reader, start=1):
        if set(row) != set(_CANDIDATE_COLUMNS):
            raise ValueError("Tiingo coverage candidate union row is invalid")
        rank = row.get("candidate_rank")
        symbol = row.get("symbol")
        if rank != str(expected_rank) or not isinstance(symbol, str) or not _valid_symbol(symbol):
            raise ValueError("Tiingo coverage candidate union row is invalid")
        candidates.append(symbol)
    if not candidates or len(set(candidates)) != len(candidates):
        raise ValueError("Tiingo coverage candidate union is invalid")
    return tuple(candidates)


def _quantile_ranks(candidate_count: int, sample_size: int) -> tuple[int, ...]:
    if sample_size == 1:
        return (1,)
    ranks = tuple(
        1 + index * (candidate_count - 1) // (sample_size - 1)
        for index in range(sample_size)
    )
    if len(set(ranks)) != sample_size:
        raise ValueError("Tiingo coverage sample ranks are invalid")
    return ranks


def _validated_external_root(market_data_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(market_data_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Tiingo coverage market-data root must exist")
    resolved = root.resolve()
    if repo_root is not None and resolved.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo coverage market-data root must stay outside Git")
    return resolved


def _validated_external_file(
    path: Path,
    *,
    root: Path,
    repo_root: Path | None,
    label: str,
) -> Path:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"Tiingo coverage {label} must be a regular file")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Tiingo coverage {label} must stay under market data")
    if repo_root is not None and resolved.is_relative_to(Path(repo_root).resolve()):
        raise ValueError(f"Tiingo coverage {label} must stay outside Git")
    return resolved


def _validate_destination(
    destination: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = Path(artifact_root)
    if root.is_symlink():
        raise ValueError("Tiingo coverage artifact root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo coverage artifact root must stay outside Git")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Tiingo coverage destination already exists")
    target = target.resolve()
    if repo_root is not None and target.is_relative_to(Path(repo_root).resolve()):
        raise ValueError("Tiingo coverage destination must stay outside Git")
    if not target.is_relative_to(root):
        raise ValueError("Tiingo coverage destination must stay under the artifact root")
    if not target.name.startswith("snapshot=") or not target.name.endswith(_SNAPSHOT_SUFFIX):
        raise ValueError("Tiingo coverage destination must use the required snapshot name")
    return target, root


def _validate_storage(root: Path, *, disk_usage: Callable[[str | Path], Any]) -> float:
    usage = disk_usage(root)
    total = int(getattr(usage, "total", 0))
    free = int(getattr(usage, "free", 0))
    if total <= 0 or free < 0:
        raise ValueError("Tiingo coverage storage usage is invalid")
    free_percent = round(100 * free / total, 2)
    if free_percent < 15:
        raise ValueError("Tiingo coverage storage is below the hard free-space floor")
    if free_percent < 20:
        warnings.warn(
            "Tiingo coverage storage is below the warning free-space floor",
            stacklevel=2,
        )
    return free_percent


def _publish_summary(destination: Path, summary_bytes: bytes) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".stage-{uuid.uuid4().hex}"
    try:
        staging.mkdir()
        (staging / _SUMMARY_FILE).write_bytes(summary_bytes)
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination / _SUMMARY_FILE


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_RejectRedirect()).open(request, timeout=timeout)


def _error_response(
    candidate_rank: int,
    status: int | None,
    classification: str,
    error_class: str,
) -> TiingoCoverageResponse:
    return TiingoCoverageResponse(
        candidate_rank=candidate_rank,
        http_status=status,
        classification=classification,
        row_count=None,
        first_session=None,
        last_session=None,
        error_class=error_class,
    )


def _http_error_class(status: object) -> str:
    return f"http_{status}" if isinstance(status, int) else "unexpected_http_status"


def _session_date(value: object) -> date:
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("Tiingo coverage date is invalid")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError("Tiingo coverage date is invalid") from exc


def _validate_window(requested_start: date, requested_end: date) -> None:
    if isinstance(requested_start, datetime) or isinstance(requested_end, datetime):
        raise ValueError("Tiingo coverage dates must not include a time")
    if requested_end < requested_start:
        raise ValueError("Tiingo coverage end date must not precede start date")


def _utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC timestamp")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _valid_symbol(value: str) -> bool:
    return bool(value) and value == value.strip() and value == value.upper() and "\n" not in value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Tiingo coverage {label} is invalid")
    return value


def _required_sha256(value: object, label: str) -> str:
    text = str(value or "")
    if len(text) != 71 or not text.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in text[7:]
    ):
        raise ValueError(f"Tiingo coverage {label} is invalid")
    return text


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

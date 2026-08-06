"""Source-safe, injected-input observations for Cboe D1 volatility CSVs.

This module is deliberately only an observation primitive.  It never fetches
data, reads configuration, or exposes parsed market-data values to a caller or
receipt.  A future collector is responsible for supplying the response body
and its own session boundaries.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

CBOE_D1_VOLATILITY_AVAILABILITY_OBSERVATION_KIND: Final = (
    "cboe_d1_volatility_availability_observation"
)
CBOE_D1_VOLATILITY_AVAILABILITY_OBSERVATION_SCHEMA_VERSION: Final = 1
CBOE_D1_VOLATILITY_CSV_HEADER: Final = ("DATE", "OPEN", "HIGH", "LOW", "CLOSE")
_RECEIPT_DIRECTORY: Final = "cboe-d1-volatility-availability-observations"
_CANONICALIZATION: Final = "cboe_d1_ohlc_matching_row_v1"
_BRACKET: Final = "at_or_after_session_close_before_next_market_open"
_QUALIFICATION: Final = "observation_only_not_eligible_for_feature_campaign_paper_model_or_pnl"
_SHA256_RE: Final = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CBOE_DAILY_PRICE_URLS: Final = {
    "VIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "VXN": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv",
    "RVX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/RVX_History.csv",
}
_ROOT_KEYS: Final = frozenset(
    {
        "schema_version",
        "kind",
        "observation_sha256",
        "session_label",
        "observed_at_utc",
        "session_close_utc",
        "next_market_open_utc",
        "close_relative_bracket",
        "source_url_sha256",
        "series_symbol",
        "parsed_status",
        "canonicalization",
        "normalized_row_sha256",
        "cache_metadata",
        "decision_time_availability",
        "provider_finality",
        "qualification",
    }
)
_CACHE_KEYS: Final = frozenset(
    {"age_seconds", "cache_control_sha256", "etag_sha256"}
)


class CboeD1VolatilityAvailabilityError(ValueError):
    """Fail-closed error for an unsafe Cboe D1 availability observation."""


@dataclass(frozen=True, slots=True)
class CboeD1VolatilityAvailabilityReceipt:
    """A validated source-safe receipt outside the repository."""

    receipt_path: Path
    observation_sha256: str


def write_cboe_d1_volatility_availability_observation(
    *,
    artifact_root: Path | str,
    repository_root: Path | str,
    csv_payload: str,
    session_label: date,
    observed_at: datetime,
    session_close: datetime,
    next_market_open: datetime,
    source_url: str,
    series_symbol: str,
    cache_age_seconds: int | None = None,
    cache_control: str | None = None,
    etag: str | None = None,
) -> CboeD1VolatilityAvailabilityReceipt:
    """Write one immutable, source-safe observation from injected CSV content.

    The response body is parsed and discarded in this call.  The resulting
    receipt intentionally does not establish decision-time availability,
    provider finality, or eligibility for any trading or research use.
    """

    root = _external_artifact_root(Path(artifact_root), Path(repository_root))
    normalized_session = _require_session_label(session_label)
    observed_at_utc, session_close_utc, next_market_open_utc = _observation_bracket(
        observed_at=observed_at,
        session_close=session_close,
        next_market_open=next_market_open,
    )
    normalized_symbol = _require_series_symbol(series_symbol)
    normalized_url = _normalize_source_url(source_url, series_symbol=normalized_symbol)
    normalized_row_sha256 = _matching_row_sha256(
        csv_payload=csv_payload,
        session_label=normalized_session,
    )
    cache_metadata = _cache_metadata(
        age_seconds=cache_age_seconds,
        cache_control=cache_control,
        etag=etag,
    )
    body = {
        "schema_version": CBOE_D1_VOLATILITY_AVAILABILITY_OBSERVATION_SCHEMA_VERSION,
        "kind": CBOE_D1_VOLATILITY_AVAILABILITY_OBSERVATION_KIND,
        "session_label": normalized_session,
        "observed_at_utc": observed_at_utc,
        "session_close_utc": session_close_utc,
        "next_market_open_utc": next_market_open_utc,
        "close_relative_bracket": _BRACKET,
        "source_url_sha256": _sha256_text(normalized_url),
        "series_symbol": normalized_symbol,
        "parsed_status": "matching_row_found",
        "canonicalization": _CANONICALIZATION,
        "normalized_row_sha256": normalized_row_sha256,
        "cache_metadata": cache_metadata,
        "decision_time_availability": "not_observed",
        "provider_finality": "not_observed",
        "qualification": _QUALIFICATION,
    }
    observation_sha256 = _sha256_json(body)
    payload = {"observation_sha256": observation_sha256, **body}
    target = _direct_receipt_target(root, observation_sha256)
    _write_immutable_json(target, payload)
    return validate_cboe_d1_volatility_availability_receipt(
        receipt_path=target,
        artifact_root=root,
        repository_root=repository_root,
    )


def validate_cboe_d1_volatility_availability_receipt(
    *,
    receipt_path: Path | str,
    artifact_root: Path | str,
    repository_root: Path | str,
) -> CboeD1VolatilityAvailabilityReceipt:
    """Validate one direct, source-safe receipt without network or credentials."""

    root = _external_artifact_root(Path(artifact_root), Path(repository_root))
    path = _direct_receipt_path(Path(receipt_path), root)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CboeD1VolatilityAvailabilityError("receipt is unreadable") from error
    if not isinstance(document, dict) or set(document) != _ROOT_KEYS:
        raise CboeD1VolatilityAvailabilityError("receipt schema is invalid")
    _validate_receipt_document(document)
    observation_body = {
        key: value for key, value in document.items() if key != "observation_sha256"
    }
    observation_sha256 = document["observation_sha256"]
    if _sha256_json(observation_body) != observation_sha256:
        raise CboeD1VolatilityAvailabilityError("receipt identity is invalid")
    if path.parent.name != observation_sha256[7:]:
        raise CboeD1VolatilityAvailabilityError("receipt path does not match its identity")
    return CboeD1VolatilityAvailabilityReceipt(
        receipt_path=path,
        observation_sha256=observation_sha256,
    )


def _matching_row_sha256(*, csv_payload: str, session_label: str) -> str:
    if not isinstance(csv_payload, str) or not csv_payload:
        raise CboeD1VolatilityAvailabilityError("CSV payload is missing")
    try:
        reader = csv.DictReader(io.StringIO(csv_payload, newline=""))
        if tuple(reader.fieldnames or ()) != CBOE_D1_VOLATILITY_CSV_HEADER:
            raise CboeD1VolatilityAvailabilityError("CSV header is invalid")
        matches = []
        for row in reader:
            if set(row) != set(CBOE_D1_VOLATILITY_CSV_HEADER):
                raise CboeD1VolatilityAvailabilityError("CSV row scope is invalid")
            normalized = _normalize_csv_row(row)
            if normalized["DATE"] == session_label:
                matches.append(normalized)
    except (csv.Error, TypeError) as error:
        raise CboeD1VolatilityAvailabilityError("CSV payload is malformed") from error
    if len(matches) != 1:
        raise CboeD1VolatilityAvailabilityError("matching CSV row is missing or ambiguous")
    return _sha256_json(matches[0])


def _normalize_csv_row(row: dict[str | None, str | None]) -> dict[str, str]:
    if set(row) != set(CBOE_D1_VOLATILITY_CSV_HEADER):
        raise CboeD1VolatilityAvailabilityError("CSV row scope is invalid")
    normalized_date = _require_cell(row["DATE"])
    try:
        normalized_date = date.fromisoformat(normalized_date).isoformat()
    except ValueError as error:
        raise CboeD1VolatilityAvailabilityError("CSV row date is invalid") from error
    normalized = {"DATE": normalized_date}
    for column in CBOE_D1_VOLATILITY_CSV_HEADER[1:]:
        normalized[column] = _canonical_decimal(_require_cell(row[column]))
    return normalized


def _require_cell(value: object) -> str:
    if not isinstance(value, str):
        raise CboeD1VolatilityAvailabilityError("CSV row scope is invalid")
    normalized = value.strip()
    if not normalized:
        raise CboeD1VolatilityAvailabilityError("CSV row scope is invalid")
    return normalized


def _canonical_decimal(value: str) -> str:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise CboeD1VolatilityAvailabilityError("CSV OHLC value is invalid") from error
    if not parsed.is_finite():
        raise CboeD1VolatilityAvailabilityError("CSV OHLC value is invalid")
    if parsed.is_zero():
        return "0"
    return format(parsed.normalize(), "f")


def _require_session_label(value: date) -> str:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise CboeD1VolatilityAvailabilityError("session label is invalid")
    return value.isoformat()


def _observation_bracket(
    *,
    observed_at: datetime,
    session_close: datetime,
    next_market_open: datetime,
) -> tuple[str, str, str]:
    values = (observed_at, session_close, next_market_open)
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise CboeD1VolatilityAvailabilityError("observation boundaries must be timezone-aware")
    if session_close >= next_market_open:
        raise CboeD1VolatilityAvailabilityError("observation boundaries are invalid")
    if observed_at < session_close or observed_at >= next_market_open:
        raise CboeD1VolatilityAvailabilityError("observation is outside the close-relative bracket")
    return (
        _utc_marker(observed_at),
        _utc_marker(session_close),
        _utc_marker(next_market_open),
    )


def _normalize_source_url(value: str, *, series_symbol: str) -> str:
    if not isinstance(value, str):
        raise CboeD1VolatilityAvailabilityError("source URL is invalid")
    parsed = urlsplit(value)
    expected = _CBOE_DAILY_PRICE_URLS[series_symbol]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "cdn.cboe.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or value != expected
    ):
        raise CboeD1VolatilityAvailabilityError("source URL is invalid")
    return expected


def _require_series_symbol(value: str) -> str:
    if not isinstance(value, str) or value not in _CBOE_DAILY_PRICE_URLS:
        raise CboeD1VolatilityAvailabilityError("series symbol is invalid")
    return value


def _cache_metadata(
    *,
    age_seconds: int | None,
    cache_control: str | None,
    etag: str | None,
) -> dict[str, int | str]:
    if age_seconds is None:
        recorded_age: int | str = "not_observed"
    elif isinstance(age_seconds, bool) or not isinstance(age_seconds, int) or age_seconds < 0:
        raise CboeD1VolatilityAvailabilityError("cache age is invalid")
    else:
        recorded_age = age_seconds
    return {
        "age_seconds": recorded_age,
        "cache_control_sha256": _optional_header_hash(cache_control),
        "etag_sha256": _optional_header_hash(etag),
    }


def _optional_header_hash(value: str | None) -> str:
    if value is None:
        return "absent"
    if not isinstance(value, str) or not value:
        raise CboeD1VolatilityAvailabilityError("cache metadata is invalid")
    return _sha256_text(value)


def _external_artifact_root(root: Path, repository_root: Path) -> Path:
    candidate = root.resolve(strict=False)
    repository = repository_root.resolve(strict=False)
    if candidate == repository or candidate.is_relative_to(repository):
        raise CboeD1VolatilityAvailabilityError("artifact root must be outside the repository")
    if root.exists() and (not root.is_dir() or root.is_symlink()):
        raise CboeD1VolatilityAvailabilityError("artifact root is invalid")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise CboeD1VolatilityAvailabilityError("artifact root is invalid")
    return root.resolve()


def _direct_receipt_target(artifact_root: Path, observation_sha256: str) -> Path:
    if not _is_sha256(observation_sha256):
        raise CboeD1VolatilityAvailabilityError("receipt identity is invalid")
    directory = artifact_root
    for part in (_RECEIPT_DIRECTORY, observation_sha256[7:]):
        candidate = directory / part
        try:
            candidate.mkdir()
        except FileExistsError:
            pass
        if candidate.is_symlink() or not candidate.is_dir():
            raise CboeD1VolatilityAvailabilityError("receipt path is not direct")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(artifact_root):
            raise CboeD1VolatilityAvailabilityError("receipt path is not direct")
        directory = candidate
    return directory / "receipt.json"


def _direct_receipt_path(path: Path, artifact_root: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise CboeD1VolatilityAvailabilityError("receipt path is invalid")
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(artifact_root)
    except ValueError as error:
        raise CboeD1VolatilityAvailabilityError("receipt is outside its artifact root") from error
    if (
        len(relative.parts) != 3
        or relative.parts[0] != _RECEIPT_DIRECTORY
        or relative.parts[2] != "receipt.json"
        or not re.fullmatch(r"[0-9a-f]{64}", relative.parts[1])
    ):
        raise CboeD1VolatilityAvailabilityError("receipt path is not direct")
    current = artifact_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise CboeD1VolatilityAvailabilityError("receipt path is not direct")
    return resolved


def _write_immutable_json(path: Path, payload: dict[str, object]) -> None:
    encoded = _json_bytes(payload)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise CboeD1VolatilityAvailabilityError("receipt path is not direct")
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise CboeD1VolatilityAvailabilityError("receipt is not immutable") from None


def _validate_receipt_document(document: dict[str, object]) -> None:
    if (
        document["schema_version"] != CBOE_D1_VOLATILITY_AVAILABILITY_OBSERVATION_SCHEMA_VERSION
        or document["kind"] != CBOE_D1_VOLATILITY_AVAILABILITY_OBSERVATION_KIND
        or document["close_relative_bracket"] != _BRACKET
        or document["parsed_status"] != "matching_row_found"
        or document["canonicalization"] != _CANONICALIZATION
        or document["decision_time_availability"] != "not_observed"
        or document["provider_finality"] != "not_observed"
        or document["qualification"] != _QUALIFICATION
    ):
        raise CboeD1VolatilityAvailabilityError("receipt categories are invalid")
    for key in ("observation_sha256", "source_url_sha256", "normalized_row_sha256"):
        if not _is_sha256(document[key]):
            raise CboeD1VolatilityAvailabilityError("receipt hash is invalid")
    try:
        date.fromisoformat(_require_string(document["session_label"]))
        observed_at = _parse_utc_marker(document["observed_at_utc"])
        session_close = _parse_utc_marker(document["session_close_utc"])
        next_market_open = _parse_utc_marker(document["next_market_open_utc"])
    except (TypeError, ValueError) as error:
        raise CboeD1VolatilityAvailabilityError("receipt time is invalid") from error
    if (
        session_close >= next_market_open
        or observed_at < session_close
        or observed_at >= next_market_open
    ):
        raise CboeD1VolatilityAvailabilityError("receipt time is invalid")
    _require_series_symbol(_require_string(document["series_symbol"]))
    cache_metadata = document["cache_metadata"]
    if not isinstance(cache_metadata, dict) or set(cache_metadata) != _CACHE_KEYS:
        raise CboeD1VolatilityAvailabilityError("receipt cache metadata is invalid")
    age = cache_metadata["age_seconds"]
    if age != "not_observed" and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
        raise CboeD1VolatilityAvailabilityError("receipt cache metadata is invalid")
    for key in ("cache_control_sha256", "etag_sha256"):
        value = cache_metadata[key]
        if value != "absent" and not _is_sha256(value):
            raise CboeD1VolatilityAvailabilityError("receipt cache metadata is invalid")


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise CboeD1VolatilityAvailabilityError("receipt value is invalid")
    return value


def _utc_marker(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc_marker(value: object) -> datetime:
    marker = _require_string(value)
    if not marker.endswith("Z"):
        raise ValueError("UTC marker is invalid")
    parsed = datetime.fromisoformat(marker.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None or _utc_marker(parsed) != marker:
        raise ValueError("UTC marker is invalid")
    return parsed


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_json(payload: object) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None

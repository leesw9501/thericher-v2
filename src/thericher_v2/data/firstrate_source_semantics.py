"""Source-safe FirstRate documentation retrieval for a bounded data contract."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/firstrate-source-semantics-retrieval-v1.json"
)
_INTERPRETATION_RECEIPT_RELATIVE_PATH = Path(
    "data-receipts/firstrate-free-intraday/"
    "firstrate-source-semantics-interpretation-v1.json"
)
_SCHEMA_VERSION = "firstrate-source-semantics-retrieval-v1"
_INTERPRETATION_SCHEMA_VERSION = "firstrate-source-semantics-interpretation-v1"
_SHA256_PREFIX = "sha256:"
_OFFICIAL_HOST = "firstratedata.com"
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class OfficialSource:
    """An exact no-auth FirstRate page and its required primary statements."""

    source_id: str
    url: str
    statements: tuple[tuple[str, str], ...]


_OFFICIAL_SOURCES = (
    OfficialSource(
        source_id="free_intraday_data",
        url="https://firstratedata.com/free-intraday-data",
        statements=(
            (
                "free_popular_dataset_coverage",
                "For backtesting and analysis purposes we offer 1 year of free intraday "
                "data for our most popular datasets.",
            ),
            (
                "free_bar_schema",
                "All data are 1-minute intraday bars "
                "(format : timestamp,open,high,low,close,volume)",
            ),
            (
                "zero_volume_omission",
                "Note : Zero volume bars are not included therefore gaps in the sequence "
                "are periods with no trading.",
            ),
            ("us_eastern_timezone", "All datasets are in US Eastern Time (ie New York time)"),
            ("spy_listing", "SPY (SPDR S&P 500)"),
            ("qqq_listing", "QQQ (Invesco QQQ Trust)"),
        ),
    ),
    OfficialSource(
        source_id="license_agreement",
        url="https://firstratedata.com/about/license",
        statements=(
            ("private_use", "the Data is for the private use of the Subscriber only."),
            (
                "derivative_works",
                "create derivative works, including, but not limited to, incorporating the "
                "Data into its internal models, published market research, or published "
                "academic research papers.",
            ),
            (
                "no_resale_redistribution",
                "not to resell or otherwise redistribute the Data as part of a commercial "
                "agreement with other third-parties.",
            ),
        ),
    ),
)


def retrieve_firstrate_source_semantics(
    *,
    artifact_root: Path | str,
    receipt_path: Path | str | None = None,
    fetch: Callable[[str], bytes] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Re-retrieve official pages and retain only source-safe interpretation facts."""

    root = _require_external_root(artifact_root, field_name="artifact_root")
    destination = _path_within_root(
        root,
        receipt_path or root / _RECEIPT_RELATIVE_PATH,
        field_name="receipt_path",
    )
    fetch_page = fetch or _fetch_official_page
    retrieved_at = (now or datetime.now(UTC)).astimezone(UTC)
    sources: list[dict[str, object]] = []
    evidence_by_source: dict[str, dict[str, str]] = {}
    source_unverified = False
    for source in _OFFICIAL_SOURCES:
        observation = _retrieve_source(source, fetch=fetch_page, retrieved_at=retrieved_at)
        sources.append(observation)
        if observation["status"] != "confirmed":
            source_unverified = True
            continue
        statements = observation["statements"]
        if not isinstance(statements, dict):
            raise RuntimeError("confirmed source retrieval has invalid statement payload")
        evidence_by_source[source.source_id] = statements

    if source_unverified:
        facts = [
            {
                "fact": "official_source_retrieval",
                "status": "source_unverified",
                "interpretation": "no FirstRate data-contract limit changed",
            }
        ]
        status = "source_unverified"
    else:
        facts = _facts(evidence_by_source)
        status = "completed"
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "receipt_id": "firstrate-source-semantics-retrieval-v1",
        "status": status,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "sources": sources,
        "facts": facts,
        "safety": {
            "credentials_read": False,
            "official_no_auth_network_access_only": True,
            "market_data_acquired": False,
            "raw_market_rows_retained_in_receipt": False,
            "raw_page_body_retained_in_receipt": False,
            "kis_or_broker_called": False,
            "model_or_gpu_used": False,
            "git_tracked_files_changed": False,
        },
        "permitted_interpretation": "firstrate_source_semantics_only",
        "non_promotion": [
            "no_session_completeness_claim",
            "no_kis_parity",
            "decision_time_availability_not_observed",
            "provider_finality_not_observed",
            "not_a_predictive_model_or_paper_input",
        ],
    }
    _write_or_verify(destination, payload)
    return {
        "status": status,
        "receipt_path_relative_to_artifact_root": _relative_posix(root, destination),
        "source_count": len(sources),
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--receipt-path", type=Path)
    args = parser.parse_args(argv)
    result = retrieve_firstrate_source_semantics(
        artifact_root=args.artifact_root,
        receipt_path=args.receipt_path,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


def resolve_firstrate_source_semantics(
    *,
    artifact_root: Path | str,
    source_receipt_path: Path | str | None = None,
    interpretation_receipt_path: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Attach the reviewed narrow interpretation without rewriting source evidence."""

    root = _require_external_root(artifact_root, field_name="artifact_root")
    source_path = _path_within_root(
        root,
        source_receipt_path or root / _RECEIPT_RELATIVE_PATH,
        field_name="source_receipt_path",
    )
    destination = _path_within_root(
        root,
        interpretation_receipt_path or root / _INTERPRETATION_RECEIPT_RELATIVE_PATH,
        field_name="interpretation_receipt_path",
    )
    source_bytes = source_path.read_bytes()
    source = _decode_json(source_bytes)
    _validate_source_receipt_for_resolution(source)
    resolved_at = (now or datetime.now(UTC)).astimezone(UTC)
    payload: dict[str, object] = {
        "schema_version": _INTERPRETATION_SCHEMA_VERSION,
        "receipt_id": "firstrate-source-semantics-interpretation-v1",
        "status": "completed",
        "resolved_at_utc": resolved_at.isoformat(),
        "source_receipt": {
            "relative_to_artifact_root": True,
            "path": _relative_posix(root, source_path),
            "sha256": _sha256(source_bytes),
        },
        "claude_challenge": {
            "verdict": "supported-with-limits",
            "scope": "FirstRate timestamp, omission, coverage, and license interpretation",
            "reversal_fact": (
                "official or file-level evidence that timestamps use fixed UTC-5 rather than "
                "a DST-observing New York rule"
            ),
        },
        "facts": [
            {
                "fact": "timestamp_timezone_label",
                "status": "confirmed_vendor_declared",
                "interpretation": "FirstRate labels the data US Eastern/New York time.",
            },
            {
                "fact": "timezone_offset_convention",
                "status": "not_disclosed",
                "interpretation": (
                    "No official evidence establishes DST-observing versus fixed-offset "
                    "conversion for the archived timestamps."
                ),
            },
            {
                "fact": "bar_timestamp_boundary",
                "status": "not_disclosed",
                "interpretation": (
                    "No official evidence establishes source bar start versus end stamping."
                ),
            },
            {
                "fact": "zero_volume_omission",
                "status": "confirmed_vendor_declared",
                "interpretation": (
                    "The vendor declares zero-volume bars omitted; this does not establish "
                    "market-session completeness or a cross-feed alignment."
                ),
            },
            {
                "fact": "free_offer_scope",
                "status": "confirmed_catalog_offer_only",
                "interpretation": (
                    "The public page offers one year for popular datasets and lists SPY/QQQ; "
                    "it does not prove local archive coverage."
                ),
            },
            {
                "fact": "project_license_policy",
                "status": "conservative_project_policy",
                "interpretation": (
                    "Keep this project private/internal with no redistribution; source-license "
                    "applicability and version for pre-existing files remain unobserved."
                ),
            },
        ],
        "prohibited_inferences": [
            "no_cross_feed_minute_alignment",
            "no_session_completeness_claim",
            "no_kis_parity",
            "decision_time_availability_not_observed",
            "provider_finality_not_observed",
            "not_a_predictive_model_or_paper_input",
        ],
        "safety": {
            "credentials_read": False,
            "network_access": False,
            "market_data_acquired": False,
            "raw_market_rows_retained_in_receipt": False,
            "raw_page_body_retained_in_receipt": False,
            "kis_or_broker_called": False,
            "model_or_gpu_used": False,
            "git_tracked_files_changed": False,
        },
    }
    _write_or_verify(destination, payload)
    return {
        "status": "completed",
        "receipt_path_relative_to_artifact_root": _relative_posix(root, destination),
    }


def resolution_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=_DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--interpretation-receipt", type=Path)
    args = parser.parse_args(argv)
    result = resolve_firstrate_source_semantics(
        artifact_root=args.artifact_root,
        source_receipt_path=args.source_receipt,
        interpretation_receipt_path=args.interpretation_receipt,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


def _retrieve_source(
    source: OfficialSource,
    *,
    fetch: Callable[[str], bytes],
    retrieved_at: datetime,
) -> dict[str, object]:
    try:
        first = fetch(source.url)
        second = fetch(source.url)
    except (HTTPError, OSError, URLError, ValueError):
        return {
            "source_id": source.source_id,
            "url": source.url,
            "status": "source_unverified",
            "retrieved_at_utc": retrieved_at.isoformat(),
        }
    if not isinstance(first, bytes) or not isinstance(second, bytes):
        return {
            "source_id": source.source_id,
            "url": source.url,
            "status": "source_unverified",
            "retrieved_at_utc": retrieved_at.isoformat(),
        }
    first_hash = _sha256(first)
    if first_hash != _sha256(second):
        return {
            "source_id": source.source_id,
            "url": source.url,
            "status": "source_unverified",
            "retrieved_at_utc": retrieved_at.isoformat(),
        }
    normalized = _normalized_page_text(first)
    statements: dict[str, str] = {}
    for statement_id, statement in source.statements:
        if statement not in normalized:
            return {
                "source_id": source.source_id,
                "url": source.url,
                "status": "source_unverified",
                "retrieved_at_utc": retrieved_at.isoformat(),
                "content_sha256": first_hash,
            }
        statements[statement_id] = statement
    return {
        "source_id": source.source_id,
        "url": source.url,
        "status": "confirmed",
        "retrieved_at_utc": retrieved_at.isoformat(),
        "content_sha256": first_hash,
        "reread_content_sha256": first_hash,
        "reread_hash_matches": True,
        "statements": statements,
    }


def _facts(evidence: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    free = evidence["free_intraday_data"]
    license_terms = evidence["license_agreement"]
    return [
        {
            "fact": "timestamp_timezone",
            "status": "confirmed",
            "source_id": "free_intraday_data",
            "statement": free["us_eastern_timezone"],
            "interpretation": (
                "FirstRate labels the data US Eastern/New York time; its exact UTC offset "
                "rule remains unverified."
            ),
        },
        {
            "fact": "timezone_offset_convention",
            "status": "not_disclosed",
            "source_id": "free_intraday_data",
            "statement": "not_disclosed",
            "interpretation": (
                "The page does not establish DST-observing versus fixed-offset timestamp "
                "conversion."
            ),
        },
        {
            "fact": "bar_timestamp_boundary",
            "status": "not_disclosed",
            "source_id": "free_intraday_data",
            "statement": "not_disclosed",
            "interpretation": (
                "The page names a timestamp column but does not state whether source bars are "
                "start- or end-stamped."
            ),
        },
        {
            "fact": "zero_volume_omission",
            "status": "confirmed",
            "source_id": "free_intraday_data",
            "statement": free["zero_volume_omission"],
            "interpretation": (
                "This is vendor-declared no-trade omission evidence only; do not fill, bridge, "
                "or call it session coverage."
            ),
        },
        {
            "fact": "free_sample_scope",
            "status": "confirmed",
            "source_id": "free_intraday_data",
            "statement": free["free_popular_dataset_coverage"],
            "interpretation": (
                "The public offer describes one year for popular datasets and lists SPY/QQQ; "
                "exact local archive coverage remains hash-bound input evidence only."
            ),
        },
        {
            "fact": "private_use_and_derivatives",
            "status": "confirmed",
            "source_id": "license_agreement",
            "statements": [
                license_terms["private_use"],
                license_terms["derivative_works"],
                license_terms["no_resale_redistribution"],
            ],
            "interpretation": (
                "The quoted terms describe private use, derivatives, and no resale; their "
                "applicability/version for existing files remains unobserved."
            ),
        },
    ]


def _fetch_official_page(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != _OFFICIAL_HOST or parsed.port is not None:
        raise ValueError("official FirstRate URL is invalid")
    request = Request(url, headers={"User-Agent": "TheRicher-v2-source-retrieval/1.0"})
    opener = build_opener(_RejectRedirects())
    with opener.open(request, timeout=20) as response:
        if response.geturl() != url:
            raise ValueError("official FirstRate URL redirected")
        payload = response.read()
    if not payload:
        raise ValueError("official FirstRate response is empty")
    return payload


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        _request: Request,
        _fp: object,
        _code: int,
        _message: str,
        _headers: object,
        _newurl: str,
    ) -> Request | None:
        return None


def _normalized_page_text(payload: bytes) -> str:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("official FirstRate page is not UTF-8") from error
    return _WHITESPACE.sub(" ", html.unescape(_HTML_TAG.sub(" ", decoded))).strip()


def _validate_source_receipt_for_resolution(payload: dict[str, object]) -> None:
    if (
        payload.get("schema_version") != _SCHEMA_VERSION
        or payload.get("receipt_id") != "firstrate-source-semantics-retrieval-v1"
        or payload.get("status") != "completed"
    ):
        raise ValueError("FirstRate source receipt is not a completed retrieval")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("FirstRate source receipt sources are invalid")
    expected_sources = {source.source_id for source in _OFFICIAL_SOURCES}
    observed_sources = {
        item.get("source_id")
        for item in sources
        if isinstance(item, dict) and item.get("status") == "confirmed"
    }
    if observed_sources != expected_sources:
        raise ValueError("FirstRate source receipt does not confirm all official sources")
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise ValueError("FirstRate source receipt facts are invalid")
    observed_facts = {
        item.get("fact") for item in facts if isinstance(item, dict) and "status" in item
    }
    required_facts = {
        "timestamp_timezone",
        "bar_timestamp_boundary",
        "zero_volume_omission",
        "free_sample_scope",
        "private_use_and_derivatives",
    }
    if not required_facts.issubset(observed_facts):
        raise ValueError("FirstRate source receipt facts are incomplete")


def _require_external_root(value: Path | str, *, field_name: str) -> Path:
    root = Path(value).resolve(strict=False)
    if root.is_relative_to(_REPO_ROOT):
        raise ValueError(f"{field_name} must stay outside Git")
    return root


def _path_within_root(root: Path, value: Path | str, *, field_name: str) -> Path:
    candidate = Path(value)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (root / candidate).resolve(strict=False)
    )
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field_name} must stay under its external root")
    return resolved


def _relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_or_verify(destination: Path, payload: dict[str, object]) -> None:
    encoded = _encode(payload)
    if destination.exists():
        existing = _decode_json(destination.read_bytes())
        if _semantic_payload(existing) != _semantic_payload(payload):
            raise ValueError("FirstRate source semantics receipt conflicts with existing evidence")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _semantic_payload(payload: dict[str, object]) -> dict[str, object]:
    result = json.loads(json.dumps(payload, ensure_ascii=True))
    result.pop("retrieved_at_utc", None)
    result.pop("resolved_at_utc", None)
    sources = result.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                source.pop("retrieved_at_utc", None)
    return result


def _decode_json(payload: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("FirstRate source semantics receipt is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("FirstRate source semantics receipt is invalid")
    return decoded


def _encode(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    main()

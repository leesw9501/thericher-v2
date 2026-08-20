"""Observe one Cboe D1 volatility CSV without retaining market-data content."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from thericher_v2.data.cboe_d1_volatility_availability import (
    _CBOE_DAILY_PRICE_URLS,
    CboeD1VolatilityAvailabilityError,
    validate_cboe_d1_volatility_availability_request,
    write_cboe_d1_volatility_availability_observation,
)

_NO_CACHE_HEADERS = {"Cache-Control": "no-cache", "Pragma": "no-cache"}


@dataclass(frozen=True, slots=True)
class CboeHttpResponse:
    """One in-memory HTTPS response, supplied by the real or test transport."""

    status_code: int
    body: str | None
    headers: Mapping[str, str]


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


Fetcher = Callable[[str, Mapping[str, str]], CboeHttpResponse]


def fetch_cboe_daily_csv(url: str, headers: Mapping[str, str]) -> CboeHttpResponse:
    """Fetch exactly one fixed Cboe CSV, rejecting redirects and retaining it only in memory."""

    request = Request(url, headers=dict(headers), method="GET")
    opener = build_opener(_RejectRedirectHandler())
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                return CboeHttpResponse(status_code=response.status, body=None, headers={})
            return CboeHttpResponse(
                status_code=200,
                body=response.read().decode("utf-8"),
                headers={key: value for key, value in response.headers.items()},
            )
    except HTTPError as error:
        return CboeHttpResponse(status_code=error.code, body=None, headers={})
    except (OSError, URLError, UnicodeDecodeError):
        return CboeHttpResponse(status_code=0, body=None, headers={})


def observe_once(
    *,
    series: str,
    session_label: date,
    observed_at: datetime,
    session_close: datetime,
    next_market_open: datetime,
    artifact_root: Path,
    repository_root: Path,
    fetcher: Fetcher = fetch_cboe_daily_csv,
) -> dict[str, str | None]:
    """Observe one explicitly scoped series and expose only a source-safe result."""

    try:
        request_scope = validate_cboe_d1_volatility_availability_request(
            series_symbol=series,
            session_label=session_label,
            observed_at=observed_at,
            session_close=session_close,
            next_market_open=next_market_open,
            artifact_root=artifact_root,
            repository_root=repository_root,
        )
        normalized_series, validated_artifact_root = request_scope
    except (CboeD1VolatilityAvailabilityError, TypeError, ValueError):
        return _unavailable(None)
    url = _CBOE_DAILY_PRICE_URLS[normalized_series]
    try:
        response = fetcher(url, _NO_CACHE_HEADERS)
    except Exception:
        return _unavailable(normalized_series)
    try:
        if response.status_code != 200 or not isinstance(response.body, str):
            return _unavailable(normalized_series)
        receipt = write_cboe_d1_volatility_availability_observation(
            artifact_root=validated_artifact_root,
            repository_root=repository_root,
            csv_payload=response.body,
            session_label=session_label,
            observed_at=observed_at,
            session_close=session_close,
            next_market_open=next_market_open,
            source_url=url,
            series_symbol=normalized_series,
            cache_age_seconds=_age_header(response.headers),
            cache_control=_header(response.headers, "Cache-Control"),
            etag=_header(response.headers, "ETag"),
            response_date=_header(response.headers, "Date"),
            last_modified=_header(response.headers, "Last-Modified"),
        )
    except (AttributeError, CboeD1VolatilityAvailabilityError, TypeError, ValueError):
        return _unavailable(normalized_series)
    return {
        "receipt_sha256": receipt.observation_sha256,
        "series": normalized_series,
        "status": "observed",
    }


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == name.lower() and isinstance(value, str):
            return value
    return None


def _age_header(headers: Mapping[str, str]) -> int | None:
    value = _header(headers, "Age")
    if value is None:
        return None
    if not value.isascii() or not value.isdecimal():
        raise ValueError("invalid Age header")
    return int(value)


def _unavailable(series: str | None) -> dict[str, str | None]:
    return {"receipt_sha256": None, "series": series, "status": "unavailable"}


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from error


def _utc_datetime_argument(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a UTC ISO-8601 timestamp") from error
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise argparse.ArgumentTypeError("expected a UTC ISO-8601 timestamp")
    return parsed


def _utc_now() -> datetime:
    """Return the instant a scheduled observer actually begins its request."""

    return datetime.now(tz=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Observe one Cboe D1 volatility series")
    parser.add_argument(
        "--series",
        required=True,
        action="append",
        choices=sorted(_CBOE_DAILY_PRICE_URLS),
    )
    parser.add_argument("--session-label", required=True, type=_date_argument)
    observed_at = parser.add_mutually_exclusive_group(required=True)
    observed_at.add_argument("--observed-at", type=_utc_datetime_argument)
    observed_at.add_argument(
        "--observed-now",
        action="store_true",
        help="Capture the actual UTC instant immediately before the one-shot request.",
    )
    parser.add_argument("--session-close", required=True, type=_utc_datetime_argument)
    parser.add_argument("--next-market-open", required=True, type=_utc_datetime_argument)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    return parser


def main(*, fetcher: Fetcher = fetch_cboe_daily_csv) -> None:
    parser = build_parser()
    args = parser.parse_args()
    if len(args.series) != 1:
        parser.error("--series must be supplied exactly once")
    observed_at = args.observed_at if args.observed_at is not None else _utc_now()
    result = observe_once(
        series=args.series[0],
        session_label=args.session_label,
        observed_at=observed_at,
        session_close=args.session_close,
        next_market_open=args.next_market_open,
        artifact_root=args.artifact_root,
        repository_root=args.repository_root,
        fetcher=fetcher,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

"""Source-specific MODP0 OPEN/CLOSE eligibility, never strict OHLCV/Bar grade."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from thericher_v2.execution.kis_market_data import (
    KIS_PAPER_DAILY_MAX_ROWS,
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_DAILY_TR_ID,
    KIS_PAPER_MARKET_DATA_BASE_URL,
    KIS_PAPER_TOKEN_PATH,
    KisMarketDataRequest,
    KisMarketDataResponse,
    KisPaperDailyQuery,
    KisPaperMarketDataClient,
    KisPaperMarketDataError,
    UrllibKisPaperMarketDataTransport,
    _successful_payload,
)

VERSION = "kis-modp0-price-endpoints-v1"
FAULT_CODES = frozenset(
    {
        "unused_high_invalid",
        "unused_low_invalid",
        "unused_tvol_invalid",
        "high_below_open_close",
        "low_above_open_close",
    }
)
SCOPE = MappingProxyType(
    {
        "SPY": frozenset({"AMS"}),
        "TLT": frozenset({"NAS", "AMS", "NYS"}),
        "GLD": frozenset({"AMS"}),
    }
)


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise KisPaperMarketDataError(code)


def _day(text: object) -> str:
    _require(
        type(text) is str and len(text) == 8 and text.isascii() and text.isdigit(),
        "endpoint_date_invalid",
    )
    try:
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    except ValueError:
        raise KisPaperMarketDataError("endpoint_date_invalid") from None


def _number(raw: object, *, positive: bool) -> tuple[str, Decimal]:
    _require(type(raw) is str and bool(raw.strip()), "endpoint_numeric_invalid")
    text = raw.strip()
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise KisPaperMarketDataError("endpoint_numeric_invalid") from None
    _require(
        number.is_finite() and (number > 0 if positive else number >= 0), "endpoint_numeric_invalid"
    )
    return text, number


def _digest(value: object) -> None:
    _require(
        type(value) is str
        and value.startswith("sha256:")
        and len(value) == 71
        and all(c in "0123456789abcdef" for c in value[7:]),
        "endpoint_hash_invalid",
    )


def _unused_faults(row: Mapping, opening: Decimal, close: Decimal) -> tuple[str, ...]:
    faults = []
    for key, positive in (("high", True), ("low", True), ("tvol", False)):
        try:
            _, number = _number(row.get(key), positive=positive)
        except KisPaperMarketDataError:
            faults.append(f"unused_{key}_invalid")
            continue
        if key == "high" and number < max(opening, close):
            faults.append("high_below_open_close")
        if key == "low" and number > min(opening, close):
            faults.append("low_above_open_close")
    return tuple(faults)


def _reject_echo(body: bytes, payload: Mapping, values: tuple[str, ...]) -> None:
    _require(not any(v.encode("utf-8") in body for v in values if v), "credential_echo_rejected")
    pending = [payload]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            _require(not any(v in item for v in values if v), "credential_echo_rejected")
        elif isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


@dataclass(frozen=True, slots=True)
class KisDailyEndpointRow:
    session_date: str
    open: str = field(repr=False)
    close: str = field(repr=False)
    provider_row_sha256: str = field(repr=False)
    unused_ohlcv_faults: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require(
            type(self.session_date) is str
            and _day(self.session_date.replace("-", "")) == self.session_date,
            "endpoint_date_invalid",
        )
        _number(self.open, positive=True)
        _number(self.close, positive=True)
        _digest(self.provider_row_sha256)
        _require(
            type(self.unused_ohlcv_faults) is tuple
            and len(set(self.unused_ohlcv_faults)) == len(self.unused_ohlcv_faults)
            and all(f in FAULT_CODES for f in self.unused_ohlcv_faults),
            "endpoint_fault_invalid",
        )

    def as_document(self) -> dict:
        """Private market-root serialization only; do not log this document."""
        return dict(
            session_date=self.session_date,
            open=self.open,
            close=self.close,
            provider_row_sha256=self.provider_row_sha256,
            unused_ohlcv_faults=list(self.unused_ohlcv_faults),
        )


@dataclass(frozen=True, slots=True)
class KisDailyEndpointPage:
    query: KisPaperDailyQuery
    rows: tuple[KisDailyEndpointRow, ...] = field(repr=False)
    source_row_count: int
    duplicate_row_count: int
    source_body_sha256: str
    continuation: str | None
    source_row_fingerprints: tuple[tuple[str, str], ...] = field(repr=False)

    def __post_init__(self) -> None:
        _require(
            type(self.query) is KisPaperDailyQuery
            and self.query.adjustment_mode == "0"
            and self.query.exchange in SCOPE.get(self.query.symbol, ()),
            "endpoint_query_invalid",
        )
        anchor = _day(self.query.by_date)
        _require(
            type(self.rows) is tuple
            and all(type(r) is KisDailyEndpointRow for r in self.rows)
            and tuple(r.session_date for r in self.rows)
            == tuple(sorted({r.session_date for r in self.rows})),
            "endpoint_page_invalid",
        )
        for row in self.rows:
            row.__post_init__()
            _require(row.session_date <= anchor, "endpoint_date_after_anchor")
        _require(
            type(self.source_row_count) is int
            and type(self.duplicate_row_count) is int
            and 0 <= self.source_row_count <= KIS_PAPER_DAILY_MAX_ROWS
            and self.duplicate_row_count == self.source_row_count - len(self.rows)
            and self.duplicate_row_count >= 0,
            "endpoint_page_invalid",
        )
        _digest(self.source_body_sha256)
        _require(
            self.continuation in (None, "F")
            and type(self.source_row_fingerprints) is tuple
            and len(self.source_row_fingerprints) == self.source_row_count,
            "endpoint_page_invalid",
        )
        for pair in self.source_row_fingerprints:
            _require(
                type(pair) is tuple
                and len(pair) == 2
                and type(pair[0]) is str
                and _day(pair[0].replace("-", "")) == pair[0],
                "endpoint_page_invalid",
            )
            _digest(pair[1])
        first_fingerprints = {}
        for day, fingerprint in self.source_row_fingerprints:
            first_fingerprints.setdefault(day, fingerprint)
        _require(
            set(d for d, _ in self.source_row_fingerprints)
            == set(r.session_date for r in self.rows)
            and all(r.provider_row_sha256 == first_fingerprints[r.session_date] for r in self.rows),
            "endpoint_page_invalid",
        )

    def safe_facts(self) -> dict:
        faults = Counter(f for row in self.rows for f in row.unused_ohlcv_faults)
        return dict(
            kind=VERSION,
            symbol=self.query.symbol,
            exchange=self.query.exchange,
            BYMD=self.query.by_date,
            MODP="0",
            source_row_count=self.source_row_count,
            unique_date_count=len(self.rows),
            duplicate_row_count=self.duplicate_row_count,
            oldest_date=self.rows[0].session_date if self.rows else None,
            newest_date=self.rows[-1].session_date if self.rows else None,
            source_body_sha256=self.source_body_sha256,
            continuation=self.continuation,
            unused_ohlcv_fault_counts=dict(sorted(faults.items())),
            strict_ohlcv_grade=False,
            qualification="not_claimed",
        )


def parse_kis_daily_price_endpoints(
    response: KisMarketDataResponse,
    *,
    query: KisPaperDailyQuery,
    credential_values: tuple[str, ...] = (),
) -> KisDailyEndpointPage:
    """Required OC conflicts reject; unused field defects stay visible, not repaired."""
    _require(
        type(query) is KisPaperDailyQuery
        and query.adjustment_mode == "0"
        and query.exchange in SCOPE.get(query.symbol, ()),
        "endpoint_query_invalid",
    )
    anchor = _day(query.by_date)
    payload = _successful_payload(response, "daily_response_rejected")
    _reject_echo(response.body, payload, credential_values)
    raw_rows = payload.get("output2")
    _require(
        isinstance(payload.get("output1"), Mapping)
        and type(raw_rows) is list
        and len(raw_rows) <= KIS_PAPER_DAILY_MAX_ROWS,
        "endpoint_schema_invalid",
    )
    unique = {}
    fingerprints = []
    for row in raw_rows:
        _require(isinstance(row, Mapping), "endpoint_schema_invalid")
        day = _day(row.get("xymd"))
        _require(day <= anchor, "endpoint_date_after_anchor")
        opening, opening_value = _number(row.get("open"), positive=True)
        close, close_value = _number(row.get("clos"), positive=True)
        digest = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        fingerprints.append((day, digest))
        faults = _unused_faults(row, opening_value, close_value)
        if day in unique:
            previous = unique[day]
            _require(
                (previous.open, previous.close) == (opening, close), "endpoint_duplicate_conflict"
            )
            # Required values agree; retain every original fingerprint and warning.
            faults = tuple(sorted(set(previous.unused_ohlcv_faults) | set(faults)))
            digest = previous.provider_row_sha256
        unique[day] = KisDailyEndpointRow(day, opening, close, digest, faults)
    continuation = next((v for k, v in response.headers.items() if k.lower() == "tr_cont"), None)
    return KisDailyEndpointPage(
        query,
        tuple(unique[d] for d in sorted(unique)),
        len(raw_rows),
        len(raw_rows) - len(unique),
        "sha256:" + hashlib.sha256(response.body).hexdigest(),
        "F" if continuation == "F" else None,
        tuple(fingerprints),
    )


class KisPaperDailyEndpointTransport(UrllibKisPaperMarketDataTransport):
    """Same shared gates and virtual host, fixed daily/token scope, MODP0 only."""

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        path = urllib.parse.urlsplit(request.url).path
        _require(
            (request.method == "POST" and path == KIS_PAPER_TOKEN_PATH)
            or (request.method == "GET" and path == KIS_PAPER_DAILY_PATH),
            "request_not_allowlisted",
        )
        return self._request_with_daily_symbol_exchanges(
            request, daily_symbol_exchanges=SCOPE, daily_adjustment_modes=frozenset({"0"})
        )


class KisPaperDailyEndpointClient(KisPaperMarketDataClient):
    """Reuse one in-memory token; ordinary strict daily parsing remains unchanged."""

    def fetch_daily_endpoint_page(self, query: KisPaperDailyQuery) -> KisDailyEndpointPage:
        _require(self._minute_route == "standard", "minute_route_disallows_daily_page")
        _require(self._config.base_url == KIS_PAPER_MARKET_DATA_BASE_URL, "paper_host_required")
        _require(
            type(query) is KisPaperDailyQuery
            and query.adjustment_mode == "0"
            and query.exchange in SCOPE.get(query.symbol, ()),
            "endpoint_query_invalid",
        )
        _day(query.by_date)
        _require(
            self._daily_page_attempts < self._max_daily_page_attempts, "daily_page_limit_exceeded"
        )
        token = self._issue_access_token()
        self._daily_page_attempts += 1
        response = self._transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{self._config.base_url}{KIS_PAPER_DAILY_PATH}",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": self._config.app_key,
                    "appsecret": self._config.app_secret,
                    "tr_id": KIS_PAPER_DAILY_TR_ID,
                    "tr_cont": query.continuation or "",
                    "accept": "application/json",
                },
                query={
                    "AUTH": "",
                    "EXCD": query.exchange,
                    "SYMB": query.symbol,
                    "GUBN": "0",
                    "BYMD": query.by_date,
                    "MODP": "0",
                },
                daily_symbol_exchanges=SCOPE,
            )
        )
        return parse_kis_daily_price_endpoints(
            response,
            query=query,
            credential_values=(self._config.app_key, self._config.app_secret, token),
        )

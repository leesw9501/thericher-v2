"""KIS virtual-paper market-data boundary with an enforced paper-only route."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION

from .kis_market_data_rate_gate import KisPaperMarketDataRateGate

KIS_PAPER_MARKET_DATA_BASE_URL = "https://openapivts.koreainvestment.com:29443"
KIS_PAPER_TOKEN_PATH = "/oauth2/tokenP"
KIS_PAPER_MINUTE_PATH = "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
KIS_PAPER_MINUTE_TR_ID = "HHDFS76950200"
KIS_PAPER_MINUTE_MAX_ROWS = 120
KIS_PAPER_DAILY_PATH = "/uapi/overseas-price/v1/quotations/dailyprice"
KIS_PAPER_DAILY_TR_ID = "HHDFS76240000"
KIS_PAPER_DAILY_MAX_ROWS = 100
KIS_PAPER_MARKET_DATA_MAX_MINUTE_PAGE_ATTEMPTS = 3
KIS_PAPER_MARKET_DATA_MAX_DAILY_PAGE_ATTEMPTS = 3
KIS_PAPER_MINUTE_QUERY_KEYS = frozenset(
    {"AUTH", "EXCD", "SYMB", "NMIN", "PINC", "NREC", "FILL", "KEYB", "NEXT"}
)
KIS_PAPER_DAILY_QUERY_KEYS = frozenset({"AUTH", "EXCD", "SYMB", "GUBN", "BYMD", "MODP"})
KIS_PAPER_MINUTE_SYMBOL_EXCHANGES = {
    "QQQ": frozenset({"NAS"}),
    # The active daily cache observes SPY through NYSE Arca (AMS). Keep NAS
    # available as an observed empty capability rather than forcing one venue.
    "SPY": frozenset({"NAS", "AMS"}),
}
# Daily history has a deliberately separate contract from the minute probe.
# QQQ/NAS was observed by the v1 private cache. NYS and AMS remain available
# for empirical ETF venue checks; the active backfill mapping records only a
# data-bearing response as verified.
KIS_PAPER_DAILY_SYMBOL_EXCHANGES = {
    "QQQ": frozenset({"NAS"}),
    # NAS remains supported for the existing historical capability probe;
    # NYS is the backfill candidate for the primary NYSE Arca listing.
    "SPY": frozenset({"AMS", "NAS", "NYS"}),
    "IWM": frozenset({"AMS", "NYS"}),
}
_KIS_PAPER_FORBIDDEN_MODE_NAMES = frozenset({"live", "kis_live"})
_KIS_PAPER_CONFIG_NON_SECRET_KEYS = frozenset(
    {
        "THERICHER_MODE",
        "THERICHER_HOST_MODEL_ARTIFACT_ROOT",
        "THERICHER_MODEL_ARTIFACT_ROOT",
    }
)
_KIS_PAPER_CONFIG_BLANK_KEYS = frozenset({"THERICHER_DASHBOARD_TOKEN"})
_KIS_PAPER_CONFIG_READABLE_ENV_KEYS = _KIS_PAPER_CONFIG_NON_SECRET_KEYS | frozenset(
    {
        "KIS_PAPER_APP_KEY",
        "KIS_PAPER_APP_SECRET",
        *_KIS_PAPER_CONFIG_BLANK_KEYS,
    }
)


class KisPaperMarketDataError(RuntimeError):
    """A non-secret failure reason for the narrow read-only market-data boundary."""


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep credential-bearing requests pinned to the initial allowlisted host."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        raise KisPaperMarketDataError("redirect_rejected")


@dataclass(frozen=True)
class KisPaperMinuteCallCounts:
    """Non-secret counts for one bounded raw-minute client instance."""

    token_attempts: int
    minute_page_attempts: int


@dataclass(frozen=True)
class KisPaperMarketDataCallCounts:
    """Non-secret request counts for a bounded read-only market-data session."""

    token_attempts: int
    minute_page_attempts: int
    daily_page_attempts: int


@dataclass(frozen=True, repr=False)
class KisPaperMarketDataConfig:
    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    base_url: str = KIS_PAPER_MARKET_DATA_BASE_URL

    def __post_init__(self) -> None:
        if self.base_url != KIS_PAPER_MARKET_DATA_BASE_URL:
            raise KisPaperMarketDataError("paper_host_required")
        if not self.app_key.strip() or not self.app_secret.strip():
            raise KisPaperMarketDataError("config_missing")


@dataclass(frozen=True, repr=False)
class KisMarketDataRequest:
    method: Literal["GET", "POST"]
    url: str
    headers: Mapping[str, str] = field(repr=False)
    query: Mapping[str, str] = field(default_factory=dict, repr=False)
    json_body: Mapping[str, str] | None = field(default=None, repr=False)


@dataclass(frozen=True, repr=False)
class KisMarketDataResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes = field(repr=False)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> KisMarketDataResponse:
        return cls(
            status_code=status_code,
            headers=dict(headers or {}),
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )

    def payload(self) -> Mapping[str, Any]:
        try:
            decoded = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KisPaperMarketDataError("response_invalid") from error
        if not isinstance(decoded, Mapping):
            raise KisPaperMarketDataError("response_invalid")
        return decoded


class KisMarketDataTransport(Protocol):
    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse: ...


class UrllibKisPaperMarketDataTransport:
    """Direct-only transport for the bounded paper market-data allowlist."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        request_gate: KisPaperMarketDataRateGate | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._request_gate = request_gate
        # Never inherit HTTPS_PROXY for credential-bearing paper requests.
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RejectRedirectHandler(),
        )

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        _validate_request(request)
        if self._request_gate is not None:
            self._request_gate.wait_for_request_slot()
        data = (
            json.dumps(request.json_body, separators=(",", ":")).encode("utf-8")
            if request.json_body is not None
            else None
        )
        url = _request_url(request)
        http_request = urllib.request.Request(
            url,
            data=data,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with self._opener.open(http_request, timeout=self._timeout_seconds) as response:
                result = KisMarketDataResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            result = KisMarketDataResponse(
                status_code=error.code,
                headers=dict(error.headers.items()) if error.headers is not None else {},
                body=error.read(),
            )
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise KisPaperMarketDataError("transport_failure") from error
        if self._request_gate is not None and _response_is_rate_limited(result):
            self._request_gate.record_rate_limit()
        return result


@dataclass(frozen=True)
class KisPaperMinuteQuery:
    exchange: str
    symbol: str
    continuation_next: str | None = None
    continuation_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.exchange not in KIS_PAPER_MINUTE_SYMBOL_EXCHANGES.get(
            self.symbol, frozenset()
        ):
            raise ValueError("minute market-data symbol/exchange pair is not supported")
        if (self.continuation_next is None) != (self.continuation_key is None):
            raise ValueError("continuation next and key must be supplied together")
        if self.continuation_next is not None and (
            not self.continuation_next or not self.continuation_key
        ):
            raise ValueError("continuation values must be nonempty")


@dataclass(frozen=True)
class KisPaperDailyQuery:
    """Typed raw daily-query shape for the private historical cache lane."""

    symbol: str
    by_date: str
    continuation: str | None = None
    exchange: str = "NAS"

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "by_date", self.by_date.strip())
        if self.exchange not in KIS_PAPER_DAILY_SYMBOL_EXCHANGES.get(self.symbol, frozenset()):
            raise ValueError("daily historical symbol/exchange pair is not approved")
        if len(self.by_date) != 8 or not self.by_date.isdigit():
            raise ValueError("daily historical probe date must be YYYYMMDD")
        if self.continuation not in {None, "F"}:
            raise ValueError("daily historical probe continuation is not approved")


@dataclass(frozen=True)
class KisPaperDailyPage:
    """Metadata-only daily page facts shared by observation and cache callers."""

    query: KisPaperDailyQuery
    row_count: int
    newest_date: str | None
    oldest_date: str | None
    required_ohlcv_fields_present: bool
    continuation_available: bool
    continuation_value: str | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.row_count < 0 or self.row_count > KIS_PAPER_DAILY_MAX_ROWS:
            raise KisPaperMarketDataError("daily_response_invalid")
        if (self.newest_date is None) != (self.oldest_date is None):
            raise KisPaperMarketDataError("daily_response_invalid")
        for value in (self.newest_date, self.oldest_date):
            if value is not None and (len(value) != 8 or not value.isdigit()):
                raise KisPaperMarketDataError("daily_response_invalid")
        if self.continuation_available != (self.continuation_value == "F"):
            raise KisPaperMarketDataError("daily_response_invalid")


@dataclass(frozen=True)
class KisPaperDailyRawRow:
    """One unadjusted daily OHLCV row for a narrowly authorized local cache."""

    xymd: str
    open: str
    high: str
    low: str
    clos: str
    tvol: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if len(self.xymd) != 8 or not self.xymd.isdigit():
            raise KisPaperMarketDataError("daily_response_invalid")
        for name in ("open", "high", "low", "clos", "tvol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise KisPaperMarketDataError("daily_response_invalid")
            object.__setattr__(self, name, value.strip())
        open_value = _decimal(self.open, "daily_response_invalid")
        high_value = _decimal(self.high, "daily_response_invalid")
        low_value = _decimal(self.low, "daily_response_invalid")
        close_value = _decimal(self.clos, "daily_response_invalid")
        volume_value = _decimal(self.tvol, "daily_response_invalid")
        if (
            open_value <= 0
            or high_value <= 0
            or low_value <= 0
            or close_value <= 0
            or volume_value < 0
            or high_value < max(open_value, close_value)
            or low_value > min(open_value, close_value)
        ):
            raise KisPaperMarketDataError("daily_response_invalid")

    def as_document(self) -> dict[str, str]:
        """Preserve the provider's raw daily field names without response metadata."""

        return {
            "clos": self.clos,
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "tvol": self.tvol,
            "xymd": self.xymd,
        }


@dataclass(frozen=True)
class KisPaperDailyRawPage:
    """Typed daily page plus cache-eligible rows, never a full response body."""

    page: KisPaperDailyPage
    rows: tuple[KisPaperDailyRawRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        if not isinstance(self.page, KisPaperDailyPage) or not all(
            isinstance(row, KisPaperDailyRawRow) for row in self.rows
        ):
            raise KisPaperMarketDataError("daily_response_invalid")
        if len(self.rows) != self.page.row_count:
            raise KisPaperMarketDataError("daily_response_invalid")




@dataclass(frozen=True)
class KisPaperMinuteRawBar:
    exchange_date: str
    exchange_time: str
    korea_date: str
    korea_time: str
    open: Decimal
    high: Decimal
    low: Decimal
    last: Decimal
    volume: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name, length in (
            (self.exchange_date, "exchange_date", 8),
            (self.korea_date, "korea_date", 8),
            (self.exchange_time, "exchange_time", 6),
            (self.korea_time, "korea_time", 6),
        ):
            if len(value) != length or not value.isdigit():
                raise KisPaperMarketDataError(f"minute_{name}_invalid")
        for date, time, name in (
            (self.exchange_date, self.exchange_time, "exchange"),
            (self.korea_date, self.korea_time, "korea"),
        ):
            try:
                datetime.strptime(f"{date}{time}", "%Y%m%d%H%M%S")
            except ValueError as error:
                raise KisPaperMarketDataError(f"minute_{name}_timestamp_invalid") from error
        for value, name in (
            (self.open, "open"),
            (self.high, "high"),
            (self.low, "low"),
            (self.last, "last"),
            (self.volume, "volume"),
        ):
            decimal = _decimal(value, f"minute_{name}_invalid")
            if decimal < 0 or (name != "volume" and decimal == 0):
                raise KisPaperMarketDataError(f"minute_{name}_invalid")
            object.__setattr__(self, name, decimal)
        if self.high < max(self.open, self.last) or self.low > min(self.open, self.last):
            raise KisPaperMarketDataError("minute_ohlc_invalid")

    def as_document(self) -> dict[str, str]:
        """Keep the provider's minute-field names for private cache persistence."""

        return {
            "evol": str(self.volume),
            "high": str(self.high),
            "kymd": self.korea_date,
            "khms": self.korea_time,
            "last": str(self.last),
            "low": str(self.low),
            "open": str(self.open),
            "xhms": self.exchange_time,
            "xymd": self.exchange_date,
        }


@dataclass(frozen=True)
class KisPaperMinutePage:
    query: KisPaperMinuteQuery
    bars: tuple[KisPaperMinuteRawBar, ...]
    next_cursor: str | None
    more: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        if not self.bars:
            raise KisPaperMarketDataError("minute_response_empty")
        if len(self.bars) > KIS_PAPER_MINUTE_MAX_ROWS:
            raise KisPaperMarketDataError("minute_response_invalid")


class KisPaperMarketDataClient:
    """Read-only KIS Paper minute and daily pages within fixed allowlists."""

    def __init__(
        self,
        *,
        config: KisPaperMarketDataConfig,
        transport: KisMarketDataTransport,
        max_minute_page_attempts: int = KIS_PAPER_MARKET_DATA_MAX_MINUTE_PAGE_ATTEMPTS,
        max_daily_page_attempts: int = KIS_PAPER_MARKET_DATA_MAX_DAILY_PAGE_ATTEMPTS,
    ) -> None:
        if type(max_minute_page_attempts) is not int or max_minute_page_attempts < 1:
            raise ValueError("max_minute_page_attempts must be a positive integer")
        if type(max_daily_page_attempts) is not int or max_daily_page_attempts < 1:
            raise ValueError("max_daily_page_attempts must be a positive integer")
        self._config = config
        self._transport = transport
        self._max_minute_page_attempts = max_minute_page_attempts
        self._max_daily_page_attempts = max_daily_page_attempts
        self._access_token: str | None = None
        self._token_attempts = 0
        self._minute_page_attempts = 0
        self._daily_page_attempts = 0

    @property
    def call_counts(self) -> KisPaperMarketDataCallCounts:
        return KisPaperMarketDataCallCounts(
            token_attempts=self._token_attempts,
            minute_page_attempts=self._minute_page_attempts,
            daily_page_attempts=self._daily_page_attempts,
        )

    @property
    def minute_call_counts(self) -> KisPaperMinuteCallCounts:
        return KisPaperMinuteCallCounts(
            token_attempts=self._token_attempts,
            minute_page_attempts=self._minute_page_attempts,
        )

    def fetch_minute_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage:
        if self._minute_page_attempts >= self._max_minute_page_attempts:
            raise KisPaperMarketDataError("minute_page_limit_exceeded")
        access_token = self._issue_access_token()
        request = KisMarketDataRequest(
            method="GET",
            url=f"{self._config.base_url}{KIS_PAPER_MINUTE_PATH}",
            headers={
                "authorization": f"Bearer {access_token}",
                "appkey": self._config.app_key,
                "appsecret": self._config.app_secret,
                "tr_id": KIS_PAPER_MINUTE_TR_ID,
                "tr_cont": "N" if query.continuation_next is not None else "",
                "custtype": "P",
                "accept": "application/json",
            },
            query={
                "AUTH": "",
                "EXCD": query.exchange,
                "SYMB": query.symbol,
                "NMIN": "1",
                "PINC": "1" if query.continuation_next is not None else "0",
                "NREC": "120",
                "FILL": "",
                "KEYB": query.continuation_key or "",
                "NEXT": query.continuation_next or "",
            },
        )
        if before_request is not None:
            before_request()
        self._minute_page_attempts += 1
        response = self._transport.request(request)
        payload = _successful_payload(response, "minute_response_rejected")
        output1 = payload.get("output1")
        output2 = payload.get("output2")
        if not isinstance(output1, Mapping) or not isinstance(output2, Sequence):
            raise KisPaperMarketDataError("minute_response_invalid")
        rows = tuple(_parse_minute_bar(row) for row in output2)
        # KIS documents minute pagination through the response ``tr_cont``
        # header. ``output1.next`` is provider metadata, not a stable cursor.
        continuation = (_response_header(response.headers, "tr_cont") or "").upper()
        next_cursor = "1" if continuation in {"M", "F"} else None
        return KisPaperMinutePage(
            query=query,
            bars=rows,
            next_cursor=next_cursor,
            more=str(output1.get("more", "")).strip(),
        )

    def fetch_daily_page(self, query: KisPaperDailyQuery) -> KisPaperDailyPage:
        """Return metadata-only daily facts for existing observation callers."""

        return self.fetch_daily_raw_page(query).page

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        """Return typed OHLCV rows only for a bounded private-cache collector."""

        if self._daily_page_attempts >= self._max_daily_page_attempts:
            raise KisPaperMarketDataError("daily_page_limit_exceeded")
        access_token = self._issue_access_token()
        self._daily_page_attempts += 1
        response = self._transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{self._config.base_url}{KIS_PAPER_DAILY_PATH}",
                headers={
                    "authorization": f"Bearer {access_token}",
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
            )
        )
        payload = _successful_payload(response, "daily_response_rejected")
        output1 = payload.get("output1")
        output2 = payload.get("output2")
        if not isinstance(output1, Mapping) or not isinstance(output2, Sequence):
            raise KisPaperMarketDataError("daily_response_invalid")
        rows = tuple(_parse_daily_raw_row(row) for row in output2)
        dates = tuple(row.xymd for row in rows)
        continuation_value = _response_header(response.headers, "tr_cont")
        continuation = "F" if continuation_value == "F" else None
        page = KisPaperDailyPage(
            query=query,
            row_count=len(rows),
            newest_date=max(dates) if dates else None,
            oldest_date=min(dates) if dates else None,
            required_ohlcv_fields_present=bool(rows),
            continuation_available=continuation is not None,
            continuation_value=continuation,
        )
        return KisPaperDailyRawPage(page=page, rows=rows)

    def ensure_authenticated(self) -> None:
        """Issue the single permitted token before a caller's final GET gate."""

        self._issue_access_token()

    def _issue_access_token(self) -> str:
        if self._access_token is not None:
            return self._access_token
        self._token_attempts += 1
        response = self._transport.request(
            KisMarketDataRequest(
                method="POST",
                url=f"{self._config.base_url}{KIS_PAPER_TOKEN_PATH}",
                headers={"content-type": "application/json", "accept": "application/json"},
                json_body={
                    "grant_type": "client_credentials",
                    "appkey": self._config.app_key,
                    "appsecret": self._config.app_secret,
                },
            )
        )
        if _response_is_rate_limited(response):
            raise KisPaperMarketDataError("rate_limited")
        if response.status_code != 200:
            raise KisPaperMarketDataError("auth_rejected")
        payload = response.payload()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise KisPaperMarketDataError("auth_response_invalid")
        self._access_token = token
        return self._access_token


class KisPaperMinuteClient:
    """Compatibility wrapper for the raw-minute-only qualification boundary."""

    def __init__(
        self,
        *,
        config: KisPaperMarketDataConfig,
        transport: KisMarketDataTransport,
    ) -> None:
        self._client = KisPaperMarketDataClient(config=config, transport=transport)

    @property
    def call_counts(self) -> KisPaperMinuteCallCounts:
        return self._client.minute_call_counts

    def fetch_page(
        self,
        query: KisPaperMinuteQuery,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> KisPaperMinutePage:
        return self._client.fetch_minute_page(query, before_request=before_request)

    def ensure_authenticated(self) -> None:
        """Obtain and retain a paper token inside the paper-only client."""

        self._client.ensure_authenticated()


def load_kis_paper_market_data_config(
    dotenv_path: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> KisPaperMarketDataConfig:
    """Read complete Paper app credentials from named env vars or a strict dotenv file."""

    configured = _load_kis_paper_market_data_environment_config(
        os.environ if environment is None else environment
    )
    if configured is not None:
        return configured
    return _load_kis_paper_market_data_dotenv_config(dotenv_path)


def _load_kis_paper_market_data_environment_config(
    environment: Mapping[str, str],
) -> KisPaperMarketDataConfig | None:
    """Use only a complete named Paper pair; never combine environment and dotenv values."""

    mode = environment.get("THERICHER_MODE", "off")
    if not isinstance(mode, str) or mode.strip().lower() in _KIS_PAPER_FORBIDDEN_MODE_NAMES:
        raise KisPaperMarketDataError("config_missing")
    required = ("KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET")
    supplied = {key: environment.get(key) for key in required}
    if not any(value is not None for value in supplied.values()):
        return None
    if any(not isinstance(value, str) or not value.strip() for value in supplied.values()):
        raise KisPaperMarketDataError("config_missing")
    return KisPaperMarketDataConfig(
        app_key=str(supplied["KIS_PAPER_APP_KEY"]).strip(),
        app_secret=str(supplied["KIS_PAPER_APP_SECRET"]).strip(),
    )


def _load_kis_paper_market_data_dotenv_config(dotenv_path: Path) -> KisPaperMarketDataConfig:
    """Read only Paper credentials from the local approved dotenv layout."""

    required = {"KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET"}
    values: dict[str, str] = {}
    mode: str | None = None
    try:
        with Path(dotenv_path).open("rb", buffering=0) as handle:
            while assignment := _read_approved_dotenv_assignment(handle):
                key, value = assignment
                if key == "THERICHER_MODE":
                    if mode is not None:
                        raise KisPaperMarketDataError("config_missing")
                    mode = value
                    continue
                if key in required:
                    if key in values:
                        raise KisPaperMarketDataError("config_missing")
                    values[key] = value
                    if set(values) == required:
                        break
                    continue
                if key not in (
                    _KIS_PAPER_CONFIG_NON_SECRET_KEYS | _KIS_PAPER_CONFIG_BLANK_KEYS
                ):
                    raise KisPaperMarketDataError("config_missing")
    except OSError as error:
        raise KisPaperMarketDataError("config_missing") from error
    if (
        mode is None
        or mode.strip().lower() in _KIS_PAPER_FORBIDDEN_MODE_NAMES
        or set(values) != required
        or any(not value for value in values.values())
    ):
        raise KisPaperMarketDataError("config_missing")
    return KisPaperMarketDataConfig(
        app_key=values["KIS_PAPER_APP_KEY"],
        app_secret=values["KIS_PAPER_APP_SECRET"],
    )


def _read_approved_dotenv_assignment(handle: BinaryIO) -> tuple[str, str] | None:
    """Read one allowed assignment without consuming an unapproved value.

    The loader has permission for its two paper app values only. A blank
    dashboard placeholder may precede them so a normal local ``.env`` layout
    remains usable, but a nonempty dashboard value is rejected before it is
    retained. Reading keys byte-by-byte lets the loader reject reordered
    account/live entries before their values enter Python memory.
    """

    while True:
        first = handle.read(1)
        if not first:
            return None
        while first in {b" ", b"\t"}:
            first = handle.read(1)
            if not first:
                return None
        if first in {b"\r", b"\n"}:
            continue
        if first == b"#":
            _consume_dotenv_line(handle)
            continue

        key_bytes = bytearray()
        current = first
        while current not in {b"=", b"\r", b"\n", b""}:
            if len(key_bytes) >= 128:
                raise KisPaperMarketDataError("config_missing")
            key_bytes.extend(current)
            current = handle.read(1)
        if current != b"=":
            raise KisPaperMarketDataError("config_missing")
        try:
            key = key_bytes.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise KisPaperMarketDataError("config_missing") from error
        if not key or key not in _KIS_PAPER_CONFIG_READABLE_ENV_KEYS:
            raise KisPaperMarketDataError("config_missing")
        if key in _KIS_PAPER_CONFIG_BLANK_KEYS:
            if not _read_empty_dotenv_value(handle):
                raise KisPaperMarketDataError("config_missing")
            return key, ""
        return key, _read_dotenv_value(handle)


def _consume_dotenv_line(handle: BinaryIO) -> None:
    while handle.read(1) not in {b"", b"\r", b"\n"}:
        pass


def _read_dotenv_value(handle: BinaryIO) -> str:
    value_bytes = bytearray()
    while (current := handle.read(1)) not in {b"", b"\r", b"\n"}:
        if len(value_bytes) >= 8_192:
            raise KisPaperMarketDataError("config_missing")
        value_bytes.extend(current)
    try:
        return value_bytes.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise KisPaperMarketDataError("config_missing") from error


def _read_empty_dotenv_value(handle: BinaryIO) -> bool:
    """Accept only an immediately empty optional value without retaining bytes."""

    current = handle.read(1)
    if current in {b"", b"\n"}:
        return True
    if current != b"\r":
        return False
    return handle.read(1) in {b"", b"\n"}


def _daily_row(raw: object) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise KisPaperMarketDataError("daily_response_invalid")
    return raw


def _required_daily_date(raw: Mapping[str, object]) -> str:
    value = raw.get("xymd")
    if not isinstance(value, str) or len(value) != 8 or not value.isdigit():
        raise KisPaperMarketDataError("daily_response_invalid")
    return value


def _daily_row_has_required_ohlcv_fields(raw: Mapping[str, object]) -> bool:
    return {"xymd", "open", "high", "low", "clos", "tvol"}.issubset(raw)


def _parse_daily_raw_row(raw: object) -> KisPaperDailyRawRow:
    row = _daily_row(raw)
    if not _daily_row_has_required_ohlcv_fields(row):
        raise KisPaperMarketDataError("daily_response_invalid")
    try:
        return KisPaperDailyRawRow(
            xymd=_required_daily_date(row),
            open=_required_daily_text(row, "open"),
            high=_required_daily_text(row, "high"),
            low=_required_daily_text(row, "low"),
            clos=_required_daily_text(row, "clos"),
            tvol=_required_daily_text(row, "tvol"),
        )
    except KisPaperMarketDataError:
        raise
    except (TypeError, ValueError) as error:
        raise KisPaperMarketDataError("daily_response_invalid") from error


def _required_daily_text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KisPaperMarketDataError("daily_response_invalid")
    return value.strip()


def _response_header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value.strip()
    return None


def _parse_minute_bar(raw: object) -> KisPaperMinuteRawBar:
    if not isinstance(raw, Mapping):
        raise KisPaperMarketDataError("minute_response_invalid")
    try:
        return KisPaperMinuteRawBar(
            exchange_date=_required_text(raw, "xymd"),
            exchange_time=_required_text(raw, "xhms"),
            korea_date=_required_text(raw, "kymd"),
            korea_time=_required_text(raw, "khms"),
            open=_decimal(_required_text(raw, "open"), "minute_open_invalid"),
            high=_decimal(_required_text(raw, "high"), "minute_high_invalid"),
            low=_decimal(_required_text(raw, "low"), "minute_low_invalid"),
            last=_decimal(_required_text(raw, "last"), "minute_last_invalid"),
            volume=_decimal(_required_text(raw, "evol"), "minute_volume_invalid"),
        )
    except KisPaperMarketDataError:
        raise
    except (TypeError, ValueError) as error:
        raise KisPaperMarketDataError("minute_response_invalid") from error


def _required_text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KisPaperMarketDataError("minute_response_invalid")
    return value.strip()


def _decimal(value: object, code: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise KisPaperMarketDataError(code) from error
    if not parsed.is_finite():
        raise KisPaperMarketDataError(code)
    return parsed


def _successful_payload(
    response: KisMarketDataResponse,
    code: str,
) -> Mapping[str, Any]:
    if _response_is_rate_limited(response):
        raise KisPaperMarketDataError("rate_limited")
    if response.status_code != 200:
        raise KisPaperMarketDataError(code)
    payload = response.payload()
    if str(payload.get("rt_cd", "")) != "0":
        raise KisPaperMarketDataError(code)
    return payload


def _response_is_rate_limited(response: KisMarketDataResponse) -> bool:
    if response.status_code == 429:
        return True
    try:
        payload = response.payload()
    except KisPaperMarketDataError:
        return False
    return str(payload.get("msg_cd", "")).strip().upper() == "EGW00201"


def _validate_request(request: KisMarketDataRequest) -> None:
    parsed = urllib.parse.urlparse(request.url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "openapivts.koreainvestment.com:29443"
        or parsed.query
        or parsed.fragment
    ):
        raise KisPaperMarketDataError("request_not_allowlisted")
    if request.method == "POST":
        if (
            parsed.path != KIS_PAPER_TOKEN_PATH
            or request.query
            or request.json_body is None
            or set(request.json_body) != {"grant_type", "appkey", "appsecret"}
        ):
            raise KisPaperMarketDataError("request_not_allowlisted")
        return
    if request.method != "GET" or request.json_body is not None:
        raise KisPaperMarketDataError("request_not_allowlisted")
    if parsed.path == KIS_PAPER_MINUTE_PATH and _is_approved_minute_request(request):
        return
    if parsed.path == KIS_PAPER_DAILY_PATH and _is_approved_daily_request(request):
        return
    raise KisPaperMarketDataError("request_not_allowlisted")


def _is_approved_minute_request(request: KisMarketDataRequest) -> bool:
    query = request.query
    if (
        set(query) != KIS_PAPER_MINUTE_QUERY_KEYS
        or request.headers.get("tr_id") != KIS_PAPER_MINUTE_TR_ID
        or request.headers.get("custtype") != "P"
        or query.get("AUTH") != ""
        or query.get("EXCD")
        not in KIS_PAPER_MINUTE_SYMBOL_EXCHANGES.get(
            str(query.get("SYMB")), frozenset()
        )
        or query.get("NMIN") != "1"
        or query.get("NREC") != str(KIS_PAPER_MINUTE_MAX_ROWS)
        or query.get("FILL") != ""
    ):
        return False
    if query.get("PINC") == "0":
        return (
            request.headers.get("tr_cont") == ""
            and query.get("KEYB") == ""
            and query.get("NEXT") == ""
        )
    return (
        query.get("PINC") == "1"
        and request.headers.get("tr_cont") == "N"
        and query.get("NEXT") == "1"
        and isinstance(query.get("KEYB"), str)
        and len(query["KEYB"]) == 14
        and query["KEYB"].isdigit()
    )


def _is_approved_daily_request(request: KisMarketDataRequest) -> bool:
    query = request.query
    by_date = query.get("BYMD")
    return (
        set(query) == KIS_PAPER_DAILY_QUERY_KEYS
        and request.headers.get("tr_id") == KIS_PAPER_DAILY_TR_ID
        and request.headers.get("tr_cont", "") in {"", "F"}
        and query.get("AUTH") == ""
        and query.get("EXCD")
        in KIS_PAPER_DAILY_SYMBOL_EXCHANGES.get(str(query.get("SYMB")), frozenset())
        and query.get("GUBN") == "0"
        and isinstance(by_date, str)
        and len(by_date) == 8
        and by_date.isdigit()
        and query.get("MODP") == "0"
    )


def _request_url(request: KisMarketDataRequest) -> str:
    if not request.query:
        return request.url
    return f"{request.url}?{urllib.parse.urlencode(dict(request.query))}"

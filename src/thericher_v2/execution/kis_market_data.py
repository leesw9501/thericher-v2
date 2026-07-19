"""Narrow KIS virtual-paper market-data boundary for observed raw 1-minute pages."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION

KIS_PAPER_MARKET_DATA_BASE_URL = "https://openapivts.koreainvestment.com:29443"
KIS_PAPER_TOKEN_PATH = "/oauth2/tokenP"
KIS_PAPER_MINUTE_PATH = "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
KIS_PAPER_MINUTE_TR_ID = "HHDFS76950200"
KIS_PAPER_MINUTE_QUERY_KEYS = frozenset(
    {"AUTH", "EXCD", "SYMB", "NMIN", "PINC", "NREC", "FILL", "KEYB", "NEXT", "FILL_GUBN"}
)


class KisPaperMarketDataError(RuntimeError):
    """A non-secret failure reason for the narrow read-only market-data boundary."""


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
    """Standard-library transport that accepts only token and raw 1-minute reads."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds

    def request(self, request: KisMarketDataRequest) -> KisMarketDataResponse:
        _validate_request(request)
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
            with urllib.request.urlopen(http_request, timeout=self._timeout_seconds) as response:
                return KisMarketDataResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            return KisMarketDataResponse(
                status_code=error.code,
                headers=dict(error.headers.items()) if error.headers is not None else {},
                body=error.read(),
            )
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise KisPaperMarketDataError("transport_failure") from error


@dataclass(frozen=True)
class KisPaperMinuteQuery:
    exchange: str
    symbol: str
    continuation_next: str | None = None
    continuation_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", self.exchange.strip().upper())
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.exchange not in {"NAS", "NYS", "AMS"}:
            raise ValueError("exchange must be NAS, NYS, or AMS")
        is_valid_symbol = (
            self.symbol
            and self.symbol.isascii()
            and self.symbol.replace(".", "").isalnum()
        )
        if not is_valid_symbol:
            raise ValueError("symbol must be a nonempty ASCII market symbol")
        if (self.continuation_next is None) != (self.continuation_key is None):
            raise ValueError("continuation next and key must be supplied together")
        if self.continuation_next is not None and (
            not self.continuation_next or not self.continuation_key
        ):
            raise ValueError("continuation values must be nonempty")


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


class KisPaperMinuteClient:
    """Fetch a caller-bounded raw 1-minute page without creating KIS Bar objects."""

    def __init__(
        self,
        *,
        config: KisPaperMarketDataConfig,
        transport: KisMarketDataTransport,
    ) -> None:
        self._config = config
        self._transport = transport
        self._access_token: str | None = None

    def fetch_page(self, query: KisPaperMinuteQuery) -> KisPaperMinutePage:
        access_token = self._issue_access_token()
        response = self._transport.request(
            KisMarketDataRequest(
                method="GET",
                url=f"{self._config.base_url}{KIS_PAPER_MINUTE_PATH}",
                headers={
                    "authorization": f"Bearer {access_token}",
                    "appkey": self._config.app_key,
                    "appsecret": self._config.app_secret,
                    "tr_id": KIS_PAPER_MINUTE_TR_ID,
                    "accept": "application/json",
                },
                query={
                    "AUTH": "",
                    "EXCD": query.exchange,
                    "SYMB": query.symbol,
                    "NMIN": "1",
                    "PINC": "0",
                    "NREC": "120",
                    "FILL": "",
                    "KEYB": query.continuation_key or "",
                    "NEXT": query.continuation_next or "",
                    "FILL_GUBN": "0",
                },
            )
        )
        payload = _successful_payload(response, "minute_response_rejected")
        output1 = payload.get("output1")
        output2 = payload.get("output2")
        if not isinstance(output1, Mapping) or not isinstance(output2, Sequence):
            raise KisPaperMarketDataError("minute_response_invalid")
        rows = tuple(_parse_minute_bar(row) for row in output2)
        next_value = output1.get("next")
        next_cursor = str(next_value).strip() if next_value is not None else ""
        return KisPaperMinutePage(
            query=query,
            bars=rows,
            next_cursor=next_cursor or None,
            more=str(output1.get("more", "")).strip(),
        )

    def _issue_access_token(self) -> str:
        if self._access_token is not None:
            return self._access_token
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
        if response.status_code != 200:
            raise KisPaperMarketDataError("auth_rejected")
        payload = response.payload()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise KisPaperMarketDataError("auth_response_invalid")
        self._access_token = token
        return self._access_token


def load_kis_paper_market_data_config(dotenv_path: Path) -> KisPaperMarketDataConfig:
    """Read only the two paper app credentials needed for an explicit data probe."""

    required = {"KIS_PAPER_APP_KEY", "KIS_PAPER_APP_SECRET"}
    values: dict[str, str] = {}
    with Path(dotenv_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            key, separator, value = line.partition("=")
            if separator and key.strip() in required:
                values[key.strip()] = value.strip()
    if set(values) != required or any(not value for value in values.values()):
        raise KisPaperMarketDataError("config_missing")
    return KisPaperMarketDataConfig(
        app_key=values["KIS_PAPER_APP_KEY"],
        app_secret=values["KIS_PAPER_APP_SECRET"],
    )


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
    if response.status_code != 200:
        raise KisPaperMarketDataError(code)
    payload = response.payload()
    if str(payload.get("rt_cd", "")) != "0":
        raise KisPaperMarketDataError(code)
    return payload


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
    if (
        request.method != "GET"
        or parsed.path != KIS_PAPER_MINUTE_PATH
        or request.json_body is not None
        or set(request.query) != KIS_PAPER_MINUTE_QUERY_KEYS
        or request.headers.get("tr_id") != KIS_PAPER_MINUTE_TR_ID
    ):
        raise KisPaperMarketDataError("request_not_allowlisted")


def _request_url(request: KisMarketDataRequest) -> str:
    if not request.query:
        return request.url
    return f"{request.url}?{urllib.parse.urlencode(dict(request.query))}"

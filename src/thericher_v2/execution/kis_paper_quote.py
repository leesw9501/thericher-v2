"""Transient, virtual-paper-only SPY quote support for the KIS canary.

The quote is deliberately an in-memory input. This module has no artifact,
logging, environment, or filesystem behavior, so the raw price cannot become
part of a public runtime projection or a Git artifact through this boundary.
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo

from .kis_readonly import (
    KIS_PAPER_BASE_URL,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperConfig,
    KisPaperReadOnlyError,
)

KIS_PAPER_US_SPY_QUOTE_PATH: Final = "/uapi/overseas-price/v1/quotations/price"
KIS_PAPER_US_SPY_QUOTE_TR_ID: Final = "HHDFS00000300"
KIS_PAPER_US_SPY_PRICE_DETAIL_PATH: Final = "/uapi/overseas-price/v1/quotations/price-detail"
KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID: Final = "HHDFS76200200"
KIS_PAPER_US_SPY_ASKING_PRICE_PATH: Final = (
    "/uapi/overseas-price/v1/quotations/inquire-asking-price"
)
KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID: Final = "HHDFS76200100"
KIS_PAPER_US_SPY_QUOTE_EXCHANGE: Final = "NAS"
KIS_PAPER_US_SPY_PRICE_DETAIL_EXCHANGE: Final = "AMS"
KIS_PAPER_US_SPY_ASKING_PRICE_EXCHANGE: Final = "AMS"
KIS_PAPER_US_SPY_QUOTE_SYMBOL: Final = "SPY"
# KIS's official sample labels both quote ``AMS`` and order ``AMEX`` as AMEX.
KIS_PAPER_US_SPY_ORDER_EXCHANGE: Final = "AMEX"
KIS_PAPER_US_QQQ_QUOTE_PATH: Final = KIS_PAPER_US_SPY_QUOTE_PATH
KIS_PAPER_US_QQQ_QUOTE_TR_ID: Final = KIS_PAPER_US_SPY_QUOTE_TR_ID
KIS_PAPER_US_QQQ_PRICE_DETAIL_PATH: Final = KIS_PAPER_US_SPY_PRICE_DETAIL_PATH
KIS_PAPER_US_QQQ_PRICE_DETAIL_TR_ID: Final = KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID
KIS_PAPER_US_QQQ_ASKING_PRICE_PATH: Final = KIS_PAPER_US_SPY_ASKING_PRICE_PATH
KIS_PAPER_US_QQQ_ASKING_PRICE_TR_ID: Final = KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID
KIS_PAPER_US_QQQ_QUOTE_EXCHANGE: Final = "NAS"
KIS_PAPER_US_QQQ_PRICE_DETAIL_EXCHANGE: Final = "NAS"
KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE: Final = "NAS"
KIS_PAPER_US_QQQ_QUOTE_SYMBOL: Final = "QQQ"
KIS_PAPER_US_QQQ_ORDER_EXCHANGE: Final = "NASD"
DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS: Final = Decimal("25")
KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE: Final = timedelta(seconds=120)
KIS_PAPER_QQQ_ASKING_PRICE_MAX_AGE: Final = KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
_KOREA_TZ = ZoneInfo("Asia/Seoul")
_QUOTE_HEADERS: Final = frozenset(
    {"authorization", "appkey", "appsecret", "tr_id", "custtype", "tr_cont"}
)
_DECIMAL_PLACES = re.compile(r"[0-6]", re.ASCII)


class KisPaperQuoteError(RuntimeError):
    """A closed, non-secret reason why the transient quote is unusable."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class KisPaperSpyQuote:
    """The only parsed quote fields needed to derive a nonmarket limit."""

    last: Decimal
    decimal_places: int

    def __post_init__(self) -> None:
        if not self.last.is_finite() or self.last <= 0:
            raise ValueError("quote last must be positive")
        if not isinstance(self.decimal_places, int) or isinstance(self.decimal_places, bool):
            raise ValueError("quote decimal_places is invalid")
        if not 0 <= self.decimal_places <= 6:
            raise ValueError("quote decimal_places is invalid")


@dataclass(frozen=True, repr=False)
class KisPaperSpyLimitInput:
    """Transient fresh-price and tick input for one explicit Paper limit."""

    last: Decimal
    decimal_places: int
    tick_size: Decimal
    quoted_at: datetime

    def __post_init__(self) -> None:
        quote = KisPaperSpyQuote(last=self.last, decimal_places=self.decimal_places)
        if (
            not isinstance(self.tick_size, Decimal)
            or not self.tick_size.is_finite()
            or self.tick_size <= 0
        ):
            raise ValueError("quote tick_size is invalid")
        scale_tick = Decimal(1).scaleb(-quote.decimal_places)
        if not _is_tick_multiple(self.tick_size, scale_tick):
            raise ValueError("quote tick_size is invalid")
        if self.quoted_at.tzinfo is None or self.quoted_at.utcoffset() is None:
            raise ValueError("quote timestamp is invalid")
        object.__setattr__(self, "quoted_at", self.quoted_at.astimezone(UTC))

    def as_quote(self) -> KisPaperSpyQuote:
        return KisPaperSpyQuote(last=self.last, decimal_places=self.decimal_places)


@dataclass(frozen=True, repr=False)
class KisPaperSpyPriceDetailProbe:
    """Sanitized shape-only result of the exact Paper price-detail route."""

    http_status_class: Literal["1xx", "2xx", "3xx", "4xx", "5xx", "other"]
    payload_mapping: Literal["not_checked", "invalid", "mapping"]
    result: Literal["not_checked", "success", "not_success"]
    last_state: str
    decimal_scale_state: str
    tick_state: str

    def safe_payload(self) -> dict[str, str | bool]:
        return {
            "http_status_class": self.http_status_class,
            "payload_mapping": self.payload_mapping,
            "result": self.result,
            "last_state": self.last_state,
            "decimal_scale_state": self.decimal_scale_state,
            "tick_state": self.tick_state,
            "paper_only": True,
        }


@dataclass(frozen=True, repr=False)
class KisPaperSpyAskingPriceProbe:
    """Sanitized shape-only result of the exact Paper SPY best-price route."""

    http_status_class: Literal["1xx", "2xx", "3xx", "4xx", "5xx", "other"]
    payload_mapping: Literal["not_checked", "invalid", "mapping"]
    result: Literal["not_checked", "success", "not_success"]
    last_state: str
    decimal_scale_state: str
    best_bid_state: str
    best_ask_state: str
    bid_ask_state: str
    quote_timestamp_state: str
    quote_timestamp_age_state: str

    def safe_payload(self) -> dict[str, str | bool]:
        return {
            "http_status_class": self.http_status_class,
            "payload_mapping": self.payload_mapping,
            "result": self.result,
            "last_state": self.last_state,
            "decimal_scale_state": self.decimal_scale_state,
            "best_bid_state": self.best_bid_state,
            "best_ask_state": self.best_ask_state,
            "bid_ask_state": self.bid_ask_state,
            "quote_timestamp_state": self.quote_timestamp_state,
            "quote_timestamp_age_state": self.quote_timestamp_age_state,
            "paper_only": True,
        }


# QQQ uses the same transient shape as SPY. The fixed request builders below
# are the only route difference; no caller can supply a symbol or exchange.
KisPaperQqqQuote = KisPaperSpyQuote
KisPaperQqqLimitInput = KisPaperSpyLimitInput
KisPaperQqqPriceDetailProbe = KisPaperSpyPriceDetailProbe
KisPaperQqqAskingPriceProbe = KisPaperSpyAskingPriceProbe


def build_kis_paper_spy_quote_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the one documented virtual-paper quote request without dispatching it."""

    return _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=KIS_PAPER_US_SPY_QUOTE_PATH,
        tr_id=KIS_PAPER_US_SPY_QUOTE_TR_ID,
        exchange=KIS_PAPER_US_SPY_QUOTE_EXCHANGE,
        symbol=KIS_PAPER_US_SPY_QUOTE_SYMBOL,
    )


def build_kis_paper_spy_price_detail_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the exact Paper-host-pinned SPY price-detail probe request."""

    return _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
        tr_id=KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
        exchange=KIS_PAPER_US_SPY_PRICE_DETAIL_EXCHANGE,
        symbol=KIS_PAPER_US_SPY_QUOTE_SYMBOL,
    )


def build_kis_paper_spy_asking_price_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the exact Paper-host-pinned AMEX SPY best-price probe request."""

    return _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
        tr_id=KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
        exchange=KIS_PAPER_US_SPY_ASKING_PRICE_EXCHANGE,
        symbol=KIS_PAPER_US_SPY_QUOTE_SYMBOL,
    )


def build_kis_paper_qqq_quote_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the fixed virtual-paper NAS/QQQ quote request without dispatching it."""

    return _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=KIS_PAPER_US_QQQ_QUOTE_PATH,
        tr_id=KIS_PAPER_US_QQQ_QUOTE_TR_ID,
        exchange=KIS_PAPER_US_QQQ_QUOTE_EXCHANGE,
        symbol=KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    )


def build_kis_paper_qqq_price_detail_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the fixed virtual-paper NAS/QQQ price-detail probe request."""

    return _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=KIS_PAPER_US_QQQ_PRICE_DETAIL_PATH,
        tr_id=KIS_PAPER_US_QQQ_PRICE_DETAIL_TR_ID,
        exchange=KIS_PAPER_US_QQQ_PRICE_DETAIL_EXCHANGE,
        symbol=KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    )


def build_kis_paper_qqq_asking_price_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the fixed virtual-paper NAS/QQQ asking-price probe request."""

    return _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=KIS_PAPER_US_QQQ_ASKING_PRICE_PATH,
        tr_id=KIS_PAPER_US_QQQ_ASKING_PRICE_TR_ID,
        exchange=KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE,
        symbol=KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    )


def _build_kis_paper_price_request(
    *,
    config: KisPaperConfig,
    access_token: str,
    path: str,
    tr_id: str,
    exchange: str,
    symbol: str,
) -> KisHttpRequest:
    if not isinstance(access_token, str) or not access_token:
        raise KisPaperQuoteError("quote_access_token_invalid")
    return KisHttpRequest(
        method="GET",
        url=f"{config.base_url}{path}",
        headers={
            "authorization": f"Bearer {access_token}",
            "appkey": config.app_key,
            "appsecret": config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "tr_cont": "",
        },
        query={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
    )


def validate_kis_paper_spy_quote_request(request: KisHttpRequest) -> None:
    """Reject every quote request except the documented virtual SPY quote shape."""

    if not _is_exact_kis_paper_spy_price_request(
        request,
        path=KIS_PAPER_US_SPY_QUOTE_PATH,
        tr_id=KIS_PAPER_US_SPY_QUOTE_TR_ID,
        exchange=KIS_PAPER_US_SPY_QUOTE_EXCHANGE,
    ):
        raise KisPaperQuoteError("quote_request_not_allowlisted")


def validate_kis_paper_spy_price_detail_request(request: KisHttpRequest) -> None:
    """Reject every price-detail request except the exact Paper SPY probe tuple."""

    if not _is_exact_kis_paper_spy_price_request(
        request,
        path=KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
        tr_id=KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
        exchange=KIS_PAPER_US_SPY_PRICE_DETAIL_EXCHANGE,
    ):
        raise KisPaperQuoteError("price_detail_request_not_allowlisted")


def validate_kis_paper_spy_asking_price_request(request: KisHttpRequest) -> None:
    """Reject every asking-price request except the exact Paper SPY probe tuple."""

    if not _is_exact_kis_paper_spy_price_request(
        request,
        path=KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
        tr_id=KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
        exchange=KIS_PAPER_US_SPY_ASKING_PRICE_EXCHANGE,
    ):
        raise KisPaperQuoteError("asking_price_request_not_allowlisted")


def validate_kis_paper_qqq_quote_request(request: KisHttpRequest) -> None:
    """Reject every quote request except the documented virtual NAS/QQQ shape."""

    if not _is_exact_kis_paper_price_request(
        request,
        path=KIS_PAPER_US_QQQ_QUOTE_PATH,
        tr_id=KIS_PAPER_US_QQQ_QUOTE_TR_ID,
        exchange=KIS_PAPER_US_QQQ_QUOTE_EXCHANGE,
        symbol=KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    ):
        raise KisPaperQuoteError("quote_request_not_allowlisted")


def validate_kis_paper_qqq_price_detail_request(request: KisHttpRequest) -> None:
    """Reject every price-detail request except the exact Paper NAS/QQQ tuple."""

    if not _is_exact_kis_paper_price_request(
        request,
        path=KIS_PAPER_US_QQQ_PRICE_DETAIL_PATH,
        tr_id=KIS_PAPER_US_QQQ_PRICE_DETAIL_TR_ID,
        exchange=KIS_PAPER_US_QQQ_PRICE_DETAIL_EXCHANGE,
        symbol=KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    ):
        raise KisPaperQuoteError("price_detail_request_not_allowlisted")


def validate_kis_paper_qqq_asking_price_request(request: KisHttpRequest) -> None:
    """Reject every asking-price request except the exact Paper NAS/QQQ tuple."""

    if not _is_exact_kis_paper_price_request(
        request,
        path=KIS_PAPER_US_QQQ_ASKING_PRICE_PATH,
        tr_id=KIS_PAPER_US_QQQ_ASKING_PRICE_TR_ID,
        exchange=KIS_PAPER_US_QQQ_ASKING_PRICE_EXCHANGE,
        symbol=KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    ):
        raise KisPaperQuoteError("asking_price_request_not_allowlisted")


def parse_kis_paper_spy_quote(payload: Mapping[str, Any]) -> KisPaperSpyQuote:
    """Parse only ``last`` and ``zdiv`` from a successful KIS quote payload."""

    return _parse_kis_paper_spy_quote_fields(_successful_output(payload, output_key="output"))


def parse_kis_paper_qqq_quote(payload: Mapping[str, Any]) -> KisPaperQqqQuote:
    """Parse only ``last`` and ``zdiv`` from a successful fixed NAS/QQQ payload."""

    return _parse_kis_paper_spy_quote_fields(_successful_output(payload, output_key="output"))


def parse_kis_paper_spy_limit_input(
    *,
    asking_price_payload: Mapping[str, Any],
    price_detail_payload: Mapping[str, Any],
    observed_at: datetime,
) -> KisPaperSpyLimitInput:
    """Combine exact AMS/SPY KIS fields without exposing a provider value."""

    return _parse_kis_paper_limit_input(
        asking_price_payload=asking_price_payload,
        price_detail_payload=price_detail_payload,
        observed_at=observed_at,
    )


def parse_kis_paper_qqq_limit_input(
    *,
    asking_price_payload: Mapping[str, Any],
    price_detail_payload: Mapping[str, Any],
    observed_at: datetime,
) -> KisPaperQqqLimitInput:
    """Combine fixed NAS/QQQ fields without exposing a provider value."""

    return _parse_kis_paper_limit_input(
        asking_price_payload=asking_price_payload,
        price_detail_payload=price_detail_payload,
        observed_at=observed_at,
    )


def _parse_kis_paper_limit_input(
    *,
    asking_price_payload: Mapping[str, Any],
    price_detail_payload: Mapping[str, Any],
    observed_at: datetime,
) -> KisPaperSpyLimitInput:
    asking_output = _successful_output(asking_price_payload, output_key="output1")
    quote = _parse_kis_paper_spy_quote_fields(asking_output)
    timestamp_state, quoted_at = _quote_timestamp_details(asking_output)
    timestamp_age_state = _quote_timestamp_age_state(quoted_at, observed_at=observed_at)
    if timestamp_state != "valid_date_and_time" or quoted_at is None:
        raise KisPaperQuoteError("quote_timestamp_invalid")
    if timestamp_age_state != "age_within_120s_under_korea_interpretation":
        raise KisPaperQuoteError("quote_timestamp_stale")

    detail_output = _successful_output(price_detail_payload, output_key="output")
    try:
        detail_scale = _decimal_places(detail_output.get("zdiv"))
        tick_size = _positive_decimal(detail_output.get("e_hogau"))
    except KisPaperQuoteError as error:
        raise KisPaperQuoteError("quote_tick_invalid") from error
    if detail_scale != quote.decimal_places:
        raise KisPaperQuoteError("quote_scale_mismatch")
    try:
        return KisPaperSpyLimitInput(
            last=quote.last,
            decimal_places=quote.decimal_places,
            tick_size=tick_size,
            quoted_at=quoted_at,
        )
    except ValueError as error:
        raise KisPaperQuoteError("quote_tick_invalid") from error


def inspect_kis_paper_spy_price_detail_response(
    response: KisHttpResponse,
) -> KisPaperSpyPriceDetailProbe:
    """Classify only fixed field shapes; raw provider values stay in memory."""

    http_status_class = _http_status_class(response.status_code)
    if response.status_code != 200:
        return KisPaperSpyPriceDetailProbe(
            http_status_class=http_status_class,
            payload_mapping="not_checked",
            result="not_checked",
            last_state="not_checked",
            decimal_scale_state="not_checked",
            tick_state="not_checked",
        )
    try:
        payload = response.payload()
    except KisPaperReadOnlyError:
        return KisPaperSpyPriceDetailProbe(
            http_status_class=http_status_class,
            payload_mapping="invalid",
            result="not_checked",
            last_state="not_checked",
            decimal_scale_state="not_checked",
            tick_state="not_checked",
        )
    if payload.get("rt_cd") != "0":
        return KisPaperSpyPriceDetailProbe(
            http_status_class=http_status_class,
            payload_mapping="mapping",
            result="not_success",
            last_state="not_checked",
            decimal_scale_state="not_checked",
            tick_state="not_checked",
        )
    output = payload.get("output")
    if not isinstance(output, Mapping):
        return KisPaperSpyPriceDetailProbe(
            http_status_class=http_status_class,
            payload_mapping="mapping",
            result="success",
            last_state="missing_or_invalid_output",
            decimal_scale_state="missing_or_invalid_output",
            tick_state="missing_or_invalid_output",
        )
    return KisPaperSpyPriceDetailProbe(
        http_status_class=http_status_class,
        payload_mapping="mapping",
        result="success",
        last_state=_positive_decimal_state(output, "last"),
        decimal_scale_state=_decimal_scale_state(output, "zdiv"),
        tick_state=_positive_decimal_state(output, "e_hogau"),
    )


def inspect_kis_paper_spy_asking_price_response(
    response: KisHttpResponse,
    *,
    observed_at: datetime | None = None,
) -> KisPaperSpyAskingPriceProbe:
    """Classify fixed best-price field shapes without exposing provider values."""

    http_status_class = _http_status_class(response.status_code)
    if response.status_code != 200:
        return _asking_price_probe_unchecked(http_status_class=http_status_class)
    try:
        payload = response.payload()
    except KisPaperReadOnlyError:
        return _asking_price_probe_unchecked(
            http_status_class=http_status_class,
            payload_mapping="invalid",
        )
    if payload.get("rt_cd") != "0":
        return _asking_price_probe_unchecked(
            http_status_class=http_status_class,
            payload_mapping="mapping",
            result="not_success",
        )
    output = payload.get("output1")
    if not isinstance(output, Mapping):
        return KisPaperSpyAskingPriceProbe(
            http_status_class=http_status_class,
            payload_mapping="mapping",
            result="success",
            last_state="missing_or_invalid_output",
            decimal_scale_state="missing_or_invalid_output",
            best_bid_state="missing_or_invalid_output",
            best_ask_state="missing_or_invalid_output",
            bid_ask_state="not_checked",
            quote_timestamp_state="missing_or_invalid_output",
            quote_timestamp_age_state="not_checked",
        )
    timestamp_state, quote_at = _quote_timestamp_details(output)
    best_bid_state = _positive_decimal_state(output, "pbid1")
    best_ask_state = _positive_decimal_state(output, "pask1")
    return KisPaperSpyAskingPriceProbe(
        http_status_class=http_status_class,
        payload_mapping="mapping",
        result="success",
        last_state=_positive_decimal_state(output, "last"),
        decimal_scale_state=_decimal_scale_state(output, "zdiv"),
        best_bid_state=best_bid_state,
        best_ask_state=best_ask_state,
        bid_ask_state=_bid_ask_state(
            output,
            best_bid_state=best_bid_state,
            best_ask_state=best_ask_state,
        ),
        quote_timestamp_state=timestamp_state,
        quote_timestamp_age_state=_quote_timestamp_age_state(
            quote_at,
            observed_at=observed_at,
        ),
    )


def inspect_kis_paper_qqq_price_detail_response(
    response: KisHttpResponse,
) -> KisPaperQqqPriceDetailProbe:
    """Classify fixed NAS/QQQ detail shapes without retaining provider values."""

    return inspect_kis_paper_spy_price_detail_response(response)


def inspect_kis_paper_qqq_asking_price_response(
    response: KisHttpResponse,
    *,
    observed_at: datetime | None = None,
) -> KisPaperQqqAskingPriceProbe:
    """Classify fixed NAS/QQQ asking-price shapes without retaining values."""

    return inspect_kis_paper_spy_asking_price_response(response, observed_at=observed_at)


def derive_kis_paper_nonmarket_limit(
    quote: KisPaperSpyQuote,
    *,
    discount_bps: Decimal = DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
    tick_size: Decimal | None = None,
) -> Decimal:
    """Round a small below-last discount down to the KIS-reported price scale."""

    if not isinstance(quote, KisPaperSpyQuote):
        raise TypeError("quote must be a KisPaperSpyQuote")
    if not isinstance(discount_bps, Decimal) or not discount_bps.is_finite():
        raise ValueError("discount_bps must be finite")
    if discount_bps <= 0 or discount_bps >= Decimal("10000"):
        raise ValueError("discount_bps must be between zero and 10000")
    scale_tick = Decimal(1).scaleb(-quote.decimal_places)
    tick = scale_tick if tick_size is None else tick_size
    if not isinstance(tick, Decimal) or not tick.is_finite() or tick <= 0:
        raise KisPaperQuoteError("quote_tick_invalid")
    if not _is_tick_multiple(tick, scale_tick):
        raise KisPaperQuoteError("quote_tick_invalid")
    try:
        raw_limit = quote.last * (Decimal("1") - (discount_bps / Decimal("10000")))
        limit = (raw_limit / tick).to_integral_value(rounding=ROUND_DOWN) * tick
        limit = limit.quantize(scale_tick, rounding=ROUND_DOWN)
    except InvalidOperation as error:
        raise KisPaperQuoteError("quote_limit_invalid") from error
    if limit <= 0 or not _is_tick_multiple(limit, tick):
        raise KisPaperQuoteError("quote_limit_invalid")
    return limit


def _positive_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KisPaperQuoteError("quote_response_incomplete")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise KisPaperQuoteError("quote_response_incomplete") from error
    if not decimal.is_finite() or decimal <= 0:
        raise KisPaperQuoteError("quote_response_incomplete")
    return decimal


def _successful_output(payload: Mapping[str, Any], *, output_key: str) -> Mapping[str, object]:
    if payload.get("rt_cd") != "0":
        raise KisPaperQuoteError("quote_rejected")
    output = payload.get(output_key)
    if not isinstance(output, Mapping):
        raise KisPaperQuoteError("quote_response_incomplete")
    return output


def _parse_kis_paper_spy_quote_fields(output: Mapping[str, object]) -> KisPaperSpyQuote:
    if _blank_text(output.get("last")) and _blank_text(output.get("zdiv")):
        raise KisPaperQuoteError("quote_response_blank")
    return KisPaperSpyQuote(
        last=_positive_decimal(output.get("last")),
        decimal_places=_decimal_places(output.get("zdiv")),
    )


def _decimal_places(value: object) -> int:
    if isinstance(value, bool):
        raise KisPaperQuoteError("quote_response_incomplete")
    text = str(value)
    if _DECIMAL_PLACES.fullmatch(text) is None:
        raise KisPaperQuoteError("quote_response_incomplete")
    return int(text)


def _blank_text(value: object) -> bool:
    return isinstance(value, str) and not value.strip()


def _is_exact_kis_paper_spy_price_request(
    request: KisHttpRequest,
    *,
    path: str,
    tr_id: str,
    exchange: str,
) -> bool:
    return _is_exact_kis_paper_price_request(
        request,
        path=path,
        tr_id=tr_id,
        exchange=exchange,
        symbol=KIS_PAPER_US_SPY_QUOTE_SYMBOL,
    )


def _is_exact_kis_paper_price_request(
    request: KisHttpRequest,
    *,
    path: str,
    tr_id: str,
    exchange: str,
    symbol: str,
) -> bool:
    parsed = urllib.parse.urlparse(request.url)
    return not (
        parsed.scheme != "https"
        or parsed.netloc != urllib.parse.urlparse(KIS_PAPER_BASE_URL).netloc
        or parsed.path != path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or request.method != "GET"
        or request.json_body is not None
        or set(request.query) != {"AUTH", "EXCD", "SYMB"}
        or request.query.get("AUTH") != ""
        or request.query.get("EXCD") != exchange
        or request.query.get("SYMB") != symbol
        or set(request.headers) != _QUOTE_HEADERS
        or request.headers.get("tr_id") != tr_id
        or not request.headers.get("authorization", "").startswith("Bearer ")
        or not request.headers.get("authorization", "").removeprefix("Bearer ")
        or not request.headers.get("appkey")
        or not request.headers.get("appsecret")
        or request.headers.get("custtype") != "P"
        or request.headers.get("tr_cont") != ""
    )


def _http_status_class(status_code: int) -> Literal["1xx", "2xx", "3xx", "4xx", "5xx", "other"]:
    if 100 <= status_code <= 199:
        return "1xx"
    if 200 <= status_code <= 299:
        return "2xx"
    if 300 <= status_code <= 399:
        return "3xx"
    if 400 <= status_code <= 499:
        return "4xx"
    if 500 <= status_code <= 599:
        return "5xx"
    return "other"


def _positive_decimal_state(output: Mapping[str, object], key: str) -> str:
    if key not in output:
        return "missing"
    value = output[key]
    if _blank_text(value):
        return "blank"
    if value is None or isinstance(value, bool):
        return "invalid"
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "invalid"
    if not decimal.is_finite() or decimal <= 0:
        return "invalid"
    return "positive_decimal"


def _decimal_scale_state(output: Mapping[str, object], key: str) -> str:
    if key not in output:
        return "missing"
    value = output[key]
    if _blank_text(value):
        return "blank"
    if isinstance(value, bool) or _DECIMAL_PLACES.fullmatch(str(value)) is None:
        return "invalid"
    return "valid_scale"


def _asking_price_probe_unchecked(
    *,
    http_status_class: Literal["1xx", "2xx", "3xx", "4xx", "5xx", "other"],
    payload_mapping: Literal["not_checked", "invalid", "mapping"] = "not_checked",
    result: Literal["not_checked", "success", "not_success"] = "not_checked",
) -> KisPaperSpyAskingPriceProbe:
    return KisPaperSpyAskingPriceProbe(
        http_status_class=http_status_class,
        payload_mapping=payload_mapping,
        result=result,
        last_state="not_checked",
        decimal_scale_state="not_checked",
        best_bid_state="not_checked",
        best_ask_state="not_checked",
        bid_ask_state="not_checked",
        quote_timestamp_state="not_checked",
        quote_timestamp_age_state="not_checked",
    )


def _bid_ask_state(
    output: Mapping[str, object],
    *,
    best_bid_state: str,
    best_ask_state: str,
) -> str:
    if best_bid_state != "positive_decimal" or best_ask_state != "positive_decimal":
        return "not_checked"
    try:
        best_bid = Decimal(str(output["pbid1"]))
        best_ask = Decimal(str(output["pask1"]))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return "invalid"
    return "non_crossed" if best_bid <= best_ask else "crossed"


def _quote_timestamp_details(output: Mapping[str, object]) -> tuple[str, datetime | None]:
    date_value = output.get("dymd")
    time_value = output.get("dhms")
    if date_value is None or time_value is None:
        return "missing", None
    if _blank_text(date_value) or _blank_text(time_value):
        return "blank", None
    if isinstance(date_value, bool) or isinstance(time_value, bool):
        return "invalid", None
    try:
        local_time = datetime.strptime(f"{date_value}{time_value}", "%Y%m%d%H%M%S")
    except (TypeError, ValueError):
        return "invalid", None
    return "valid_date_and_time", local_time.replace(tzinfo=_KOREA_TZ).astimezone(UTC)


def _quote_timestamp_age_state(
    quote_at: datetime | None,
    *,
    observed_at: datetime | None,
) -> str:
    if quote_at is None:
        return "not_checked"
    observed = observed_at or datetime.now(UTC)
    if observed.tzinfo is None or observed.utcoffset() is None:
        return "invalid_observed_at"
    age = observed.astimezone(UTC) - quote_at
    if age < timedelta(seconds=-5):
        return "future_under_korea_interpretation"
    if age <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE:
        return "age_within_120s_under_korea_interpretation"
    return "stale_under_korea_interpretation"


def _is_tick_multiple(value: Decimal, tick: Decimal) -> bool:
    if not value.is_finite() or not tick.is_finite() or value <= 0 or tick <= 0:
        return False
    try:
        quotient = value / tick
    except InvalidOperation:
        return False
    return quotient == quotient.to_integral_value()

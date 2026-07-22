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
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Final

from .kis_readonly import KIS_PAPER_BASE_URL, KisHttpRequest, KisPaperConfig

KIS_PAPER_US_SPY_QUOTE_PATH: Final = "/uapi/overseas-price/v1/quotations/price"
KIS_PAPER_US_SPY_QUOTE_TR_ID: Final = "HHDFS00000300"
KIS_PAPER_US_SPY_QUOTE_EXCHANGE: Final = "NAS"
KIS_PAPER_US_SPY_QUOTE_SYMBOL: Final = "SPY"
DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS: Final = Decimal("25")
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


def build_kis_paper_spy_quote_request(
    *,
    config: KisPaperConfig,
    access_token: str,
) -> KisHttpRequest:
    """Build the one documented virtual-paper quote request without dispatching it."""

    if not isinstance(access_token, str) or not access_token:
        raise KisPaperQuoteError("quote_access_token_invalid")
    return KisHttpRequest(
        method="GET",
        url=f"{config.base_url}{KIS_PAPER_US_SPY_QUOTE_PATH}",
        headers={
            "authorization": f"Bearer {access_token}",
            "appkey": config.app_key,
            "appsecret": config.app_secret,
            "tr_id": KIS_PAPER_US_SPY_QUOTE_TR_ID,
            "custtype": "P",
            "tr_cont": "",
        },
        query={
            "AUTH": "",
            "EXCD": KIS_PAPER_US_SPY_QUOTE_EXCHANGE,
            "SYMB": KIS_PAPER_US_SPY_QUOTE_SYMBOL,
        },
    )


def validate_kis_paper_spy_quote_request(request: KisHttpRequest) -> None:
    """Reject every quote request except the documented virtual SPY quote shape."""

    parsed = urllib.parse.urlparse(request.url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != urllib.parse.urlparse(KIS_PAPER_BASE_URL).netloc
        or parsed.path != KIS_PAPER_US_SPY_QUOTE_PATH
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or request.method != "GET"
        or request.json_body is not None
        or set(request.query) != {"AUTH", "EXCD", "SYMB"}
        or request.query.get("AUTH") != ""
        or request.query.get("EXCD") != KIS_PAPER_US_SPY_QUOTE_EXCHANGE
        or request.query.get("SYMB") != KIS_PAPER_US_SPY_QUOTE_SYMBOL
        or set(request.headers) != _QUOTE_HEADERS
        or request.headers.get("tr_id") != KIS_PAPER_US_SPY_QUOTE_TR_ID
        or not request.headers.get("authorization", "").startswith("Bearer ")
        or not request.headers.get("authorization", "").removeprefix("Bearer ")
        or not request.headers.get("appkey")
        or not request.headers.get("appsecret")
        or request.headers.get("custtype") != "P"
        or request.headers.get("tr_cont") != ""
    ):
        raise KisPaperQuoteError("quote_request_not_allowlisted")


def parse_kis_paper_spy_quote(payload: Mapping[str, Any]) -> KisPaperSpyQuote:
    """Parse only ``last`` and ``zdiv`` from a successful KIS quote payload."""

    if payload.get("rt_cd") != "0":
        raise KisPaperQuoteError("quote_rejected")
    output = payload.get("output")
    if not isinstance(output, Mapping):
        raise KisPaperQuoteError("quote_response_incomplete")
    return KisPaperSpyQuote(
        last=_positive_decimal(output.get("last")),
        decimal_places=_decimal_places(output.get("zdiv")),
    )


def derive_kis_paper_nonmarket_limit(
    quote: KisPaperSpyQuote,
    *,
    discount_bps: Decimal = DEFAULT_KIS_PAPER_CANARY_DISCOUNT_BPS,
) -> Decimal:
    """Round a small below-last discount down to the KIS-reported price scale."""

    if not isinstance(quote, KisPaperSpyQuote):
        raise TypeError("quote must be a KisPaperSpyQuote")
    if not isinstance(discount_bps, Decimal) or not discount_bps.is_finite():
        raise ValueError("discount_bps must be finite")
    if discount_bps <= 0 or discount_bps >= Decimal("10000"):
        raise ValueError("discount_bps must be between zero and 10000")
    tick = Decimal(1).scaleb(-quote.decimal_places)
    try:
        limit = (quote.last * (Decimal("1") - (discount_bps / Decimal("10000")))).quantize(
            tick,
            rounding=ROUND_DOWN,
        )
    except InvalidOperation as error:
        raise KisPaperQuoteError("quote_limit_invalid") from error
    if limit <= 0:
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


def _decimal_places(value: object) -> int:
    if isinstance(value, bool):
        raise KisPaperQuoteError("quote_response_incomplete")
    text = str(value)
    if _DECIMAL_PLACES.fullmatch(text) is None:
        raise KisPaperQuoteError("quote_response_incomplete")
    return int(text)

"""Pure KIS virtual-paper US limit-order body-field mappings.

This module intentionally maps a body-field fragment only. It has no endpoint,
header, account, credential, environment, or transport dependency. A future
separately authorized adapter must supply account context and perform its own
request and reconciliation work.
"""

from __future__ import annotations

import re
from typing import Final

from .broker import BrokerOrderRequest

KIS_PAPER_US_BUY_LIMIT_SOURCE_REVISION: Final = "885dd4e2f5c37e4f7e23dd63c15555a9967bc7bc"
KIS_PAPER_US_BUY_LIMIT_SOURCE_URL: Final = (
    "https://github.com/koreainvestment/open-trading-api/blob/"
    f"{KIS_PAPER_US_BUY_LIMIT_SOURCE_REVISION}/examples_llm/overseas_stock/order/order.py"
)
KIS_PAPER_US_SELL_LIMIT_SOURCE_REVISION: Final = KIS_PAPER_US_BUY_LIMIT_SOURCE_REVISION
KIS_PAPER_US_SELL_LIMIT_SOURCE_URL: Final = KIS_PAPER_US_BUY_LIMIT_SOURCE_URL
KIS_PAPER_US_EXCHANGES: Final = frozenset({"NASD", "NYSE", "AMEX"})

_US_SYMBOL = re.compile(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*")


def map_kis_paper_us_buy_limit_order_fields(
    request: BrokerOrderRequest,
    *,
    exchange: str,
) -> dict[str, str]:
    """Map a long-only US limit request without implying it can be transmitted.

    ``BrokerOrderRequest.market`` deliberately remains the generic ``US``
    market. KIS requires a concrete exchange code, so callers must supply one
    explicitly; the mapper never derives a venue from the symbol.
    """

    return _map_kis_paper_us_limit_order_fields(
        request,
        exchange=exchange,
        expected_side="buy",
        sell_type="",
    )


def map_kis_paper_us_sell_limit_order_fields(
    request: BrokerOrderRequest,
    *,
    exchange: str,
) -> dict[str, str]:
    """Map a US sell limit body fragment without proving a position exists.

    The existing deterministic risk boundary must establish that a sell is a
    long-only reduction before this pure mapper can ever be considered by a
    separately authorized transport.
    """

    return _map_kis_paper_us_limit_order_fields(
        request,
        exchange=exchange,
        expected_side="sell",
        sell_type="00",
    )


def _map_kis_paper_us_limit_order_fields(
    request: BrokerOrderRequest,
    *,
    exchange: str,
    expected_side: str,
    sell_type: str,
) -> dict[str, str]:
    if not isinstance(request, BrokerOrderRequest):
        raise TypeError("request must be BrokerOrderRequest")
    if request.market != "US":
        raise ValueError("KIS paper US mapper requires market US")
    if request.side != expected_side:
        raise ValueError(f"KIS paper US mapper supports {expected_side} orders only")
    if request.limit_price is None or (
        not request.limit_price.is_finite() or request.limit_price <= 0
    ):
        raise ValueError("KIS paper US mapper requires a positive limit price")
    if not request.quantity.is_finite() or request.quantity <= 0:
        raise ValueError("KIS paper US mapper requires a positive quantity")
    if request.quantity != request.quantity.to_integral_value():
        raise ValueError("KIS paper US mapper requires a whole-share quantity")
    if _US_SYMBOL.fullmatch(request.symbol) is None:
        raise ValueError("KIS paper US mapper requires a simple US ticker symbol")

    return {
        "OVRS_EXCG_CD": _kis_paper_us_exchange(exchange),
        "PDNO": request.symbol,
        "ORD_QTY": str(int(request.quantity)),
        "OVRS_ORD_UNPR": format(request.limit_price, "f"),
        "SLL_TYPE": sell_type,
        "ORD_SVR_DVSN_CD": "0",
        "ORD_DVSN": "00",
    }


def _kis_paper_us_exchange(value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("KIS paper US exchange must be explicit")
    exchange = value.upper()
    if exchange not in KIS_PAPER_US_EXCHANGES:
        raise ValueError("KIS paper US exchange is unsupported")
    return exchange

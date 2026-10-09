"""Pure, explicitly bound NASDAQ stock quote requests for virtual Paper reads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .kis_paper_quote import (
    KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
    KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID,
    KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
    KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID,
    KisPaperQuoteError,
    _build_kis_paper_price_request,
    _is_exact_kis_paper_price_request,
)
from .kis_readonly import KIS_PAPER_BASE_URL, KisHttpRequest, KisPaperConfig

_SYMBOL = re.compile(r"[A-Z]{1,10}", re.ASCII)
_BINDING = re.compile(r"ref:[0-9a-f]{64}", re.ASCII)
_ROUTES = (
    ("asking_price", KIS_PAPER_US_SPY_ASKING_PRICE_PATH, KIS_PAPER_US_SPY_ASKING_PRICE_TR_ID),
    ("price_detail", KIS_PAPER_US_SPY_PRICE_DETAIL_PATH, KIS_PAPER_US_SPY_PRICE_DETAIL_TR_ID),
)


@dataclass(frozen=True, slots=True, repr=False)
class KisPaperStockInstrument:
    """Caller-attested instrument identity, not a listing or provider-support proof."""

    symbol: str
    binding_ref: str

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or _SYMBOL.fullmatch(self.symbol) is None:
            raise KisPaperQuoteError("stock_symbol_invalid")
        if type(self.binding_ref) is not str or _BINDING.fullmatch(self.binding_ref) is None:
            raise KisPaperQuoteError("stock_binding_ref_invalid")

    @property
    def market(self) -> Literal["US"]:
        return "US"

    @property
    def quote_exchange(self) -> Literal["NAS"]:
        return "NAS"

    @property
    def order_exchange(self) -> Literal["NASD"]:
        return "NASD"


def _validate_instrument(instrument: KisPaperStockInstrument) -> None:
    if type(instrument) is not KisPaperStockInstrument:
        raise KisPaperQuoteError("stock_instrument_invalid")
    instrument.__post_init__()


def build_kis_paper_stock_quote_request(
    *,
    config: KisPaperConfig,
    access_token: str,
    instrument: KisPaperStockInstrument,
    kind: Literal["asking_price", "price_detail"],
) -> KisHttpRequest:
    """Build one of two fixed GETs; this function never loads credentials or calls KIS."""
    _validate_instrument(instrument)
    if not isinstance(config, KisPaperConfig):
        raise KisPaperQuoteError("stock_quote_config_invalid")
    if type(kind) is not str or kind not in {route[0] for route in _ROUTES}:
        raise KisPaperQuoteError("stock_quote_kind_invalid")
    if type(access_token) is not str or not access_token.strip():
        raise KisPaperQuoteError("quote_access_token_invalid")
    _, path, tr_id = next(route for route in _ROUTES if route[0] == kind)
    request = _build_kis_paper_price_request(
        config=config,
        access_token=access_token,
        path=path,
        tr_id=tr_id,
        exchange=instrument.quote_exchange,
        symbol=instrument.symbol,
    )
    validate_kis_paper_stock_quote_request(request, instrument=instrument)
    return request


def validate_kis_paper_stock_quote_request(
    request: KisHttpRequest, *, instrument: KisPaperStockInstrument
) -> None:
    """Match exact route/header/query grammar against the supplied bound instrument."""
    _validate_instrument(instrument)
    try:
        if type(request) is not KisHttpRequest:
            raise KisPaperQuoteError("stock_quote_request_invalid")
        for values in (request.headers, request.query):
            if not isinstance(values, Mapping) or any(
                type(key) is not str or type(value) is not str for key, value in values.items()
            ):
                raise KisPaperQuoteError("stock_quote_request_invalid")
        if any("\r" in value or "\n" in value for value in request.headers.values()):
            raise KisPaperQuoteError("stock_quote_request_invalid")
        for _, path, tr_id in _ROUTES:
            if request.url == KIS_PAPER_BASE_URL + path and _is_exact_kis_paper_price_request(
                request,
                path=path,
                tr_id=tr_id,
                exchange=instrument.quote_exchange,
                symbol=instrument.symbol,
            ):
                return
    except KisPaperQuoteError:
        raise
    except Exception:
        raise KisPaperQuoteError("stock_quote_request_invalid") from None
    raise KisPaperQuoteError("stock_quote_request_invalid")

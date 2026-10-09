"""Explicit NASDAQ stock read-only observations; never an intent or order path."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import require_utc

from .kis_paper_quote import (
    KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
    KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
    KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
    KisPaperQuoteError,
    KisPaperSpyLimitInput,
    derive_kis_paper_marketable_limit,
    parse_kis_paper_qqq_limit_input,
)
from .kis_paper_stock_quote import (
    KisPaperStockInstrument,
    build_kis_paper_stock_quote_request,
    validate_kis_paper_stock_quote_request,
)
from .kis_readonly import (
    KisHttpRequest,
    KisHttpResponse,
    KisPaperCashSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    UrllibKisHttpTransport,
    _request_url_with_query,
    _require_http_success,
)


def _instrument(value: object) -> KisPaperStockInstrument:
    if type(value) is not KisPaperStockInstrument:
        raise KisPaperReadOnlyError("stock_instrument_invalid")
    try:
        replace(value)
    except (ValueError, TypeError, AttributeError, KisPaperQuoteError):
        raise KisPaperReadOnlyError("stock_instrument_invalid") from None
    return value


def _validate_quote(request: KisHttpRequest, instrument: KisPaperStockInstrument) -> None:
    try:
        validate_kis_paper_stock_quote_request(request, instrument=_instrument(instrument))
    except KisPaperQuoteError:
        raise KisPaperReadOnlyError("request_not_allowlisted") from None


class UrllibKisPaperStockHttpTransport(UrllibKisHttpTransport):
    """Exact target on both quote paths; non-quote legacy requests are unchanged."""

    def __init__(self, *, instrument: KisPaperStockInstrument, **arguments) -> None:
        self._stock_instrument = _instrument(instrument)
        super().__init__(**arguments)

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        if urllib.parse.urlsplit(request.url).path not in {
            KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
            KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
        }:
            return super().request(request)
        _validate_quote(request, self._stock_instrument)
        # The exact stock validator has rejected every POST, foreign host and route.
        self._pacer.wait_for_request_slot()
        http_request = urllib.request.Request(
            _request_url_with_query(request),
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with self._opener.open(http_request, timeout=self._timeout_seconds) as response:
                return KisHttpResponse(
                    response.status, dict(response.headers.items()), response.read()
                )
        except urllib.error.HTTPError as error:
            return KisHttpResponse(
                error.code,
                dict(error.headers.items()) if error.headers is not None else {},
                error.read(),
            )
        except (OSError, TimeoutError, urllib.error.URLError):
            raise KisPaperReadOnlyError("transport_failure") from None


@dataclass(frozen=True, repr=False)
class KisPaperStockPreviewReads:
    account_ref: str
    instrument: KisPaperStockInstrument
    snapshot: KisPaperReadOnlySnapshot
    quote: KisPaperSpyLimitInput
    buy_limit: Decimal
    cash: KisPaperCashSnapshot
    orderable: KisPaperOrderableFundsSnapshot
    started_at: datetime
    completed_at: datetime
    elapsed_seconds: float


class KisPaperStockReadOnlyClient(KisPaperReadOnlyClient):
    """One reused transient client for account, bound quotes and exact funds."""

    def _dispatch_stock_quote(
        self, request: KisHttpRequest, *, instrument: KisPaperStockInstrument
    ) -> KisHttpResponse:
        _validate_quote(request, instrument)
        return self._transport.request(request)

    def stock_orderable_funds_at_limit(
        self,
        *,
        instrument: KisPaperStockInstrument,
        limit_price: Decimal,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> tuple[KisPaperCashSnapshot, KisPaperOrderableFundsSnapshot]:
        """One exact target/limit GET; observations are not settled cash or fills."""
        bound = _instrument(instrument)
        if (
            type(limit_price) is not Decimal
            or not limit_price.is_finite()
            or limit_price <= 0
            or limit_price.as_tuple().exponent < -8
            or limit_price.adjusted() >= 23
        ):
            raise KisPaperReadOnlyError("orderability_price_invalid")
        captured_at = require_utc(clock())
        return self._cash_and_orderable_funds(
            self._access_token or self._issue_access_token(),
            captured_at,
            symbol=bound.symbol,
            exchange=bound.order_exchange,
            limit_price=limit_price,
            exact=True,
        )

    def stock_preview_snapshot(
        self,
        *,
        instrument: KisPaperStockInstrument,
        expected_account_ref: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> KisPaperStockPreviewReads:
        """Account first, then two quotes and bound funds, entirely in memory.

        The caller owns source identity, session/lifetime and private readback.
        Sequential observations are not atomic or submission permission.
        """
        from .kis_paper_spy_fill_cycle import _digest

        bound = _instrument(instrument)
        config = self._config
        account_ref = _digest([config.base_url, config.account_number, config.account_product_code])
        if type(expected_account_ref) is not str or expected_account_ref != account_ref:
            raise KisPaperReadOnlyError("stock_account_binding_mismatch")
        started_at = require_utc(clock())
        started = time.monotonic()
        snapshot = self.snapshot()
        responses = {}
        for kind in ("asking_price", "price_detail"):
            response = self._dispatch_stock_quote(
                build_kis_paper_stock_quote_request(
                    config=config, access_token=self._access_token, instrument=bound, kind=kind
                ),
                instrument=bound,
            )
            _require_http_success(response, "stock_quote_rejected")
            if response.header("tr_cont").strip().upper() not in {"", "D", "E"}:
                raise KisPaperReadOnlyError("stock_quote_incomplete")
            responses[kind] = response.payload(reject_duplicate_keys=True)
        try:
            quote = parse_kis_paper_qqq_limit_input(
                asking_price_payload=responses["asking_price"],
                price_detail_payload=responses["price_detail"],
                observed_at=require_utc(clock()),
            )
            limit = derive_kis_paper_marketable_limit(quote, side="buy", observed_at=clock())
        except KisPaperQuoteError as error:
            raise KisPaperReadOnlyError(error.code) from None
        cash, funds = self.stock_orderable_funds_at_limit(
            instrument=bound, limit_price=limit, clock=clock
        )
        completed_at = require_utc(clock())
        times = [
            snapshot.captured_at,
            snapshot.identity.captured_at,
            snapshot.open_orders.captured_at,
            snapshot.cash.captured_at,
            snapshot.orderable_funds.captured_at,
            *(row.captured_at for row in (*snapshot.positions, *snapshot.open_orders.orders)),
            quote.quoted_at,
            cash.captured_at,
            funds.captured_at,
        ]
        if completed_at < started_at or any(
            not timedelta(seconds=-5) <= completed_at - at <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
            for at in times
        ):
            raise KisPaperReadOnlyError("stock_snapshot_stale")
        return KisPaperStockPreviewReads(
            account_ref,
            bound,
            snapshot,
            quote,
            limit,
            cash,
            funds,
            started_at,
            completed_at,
            time.monotonic() - started,
        )

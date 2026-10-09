"""Explicit stock-bound adapter to existing virtual Paper canary semantics.

No credential loading, intent construction, persistence, or recovery policy is
introduced here. The caller owns source/account/intent custody and the complete
shared budget. Sequential preview reads are not fills or submission permission.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from .kis_paper_canary import (
    KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
    KIS_PAPER_US_CANCEL_PATH,
    KisPaperCanaryClient,
    KisPaperCanaryError,
    KisPaperCanaryIntent,
    KisPaperCanaryReconciliation,
    KisPaperCanaryState,
    UrllibKisPaperCanaryTransport,
)
from .kis_paper_quote import (
    KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
    KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
    KisPaperQuoteError,
)
from .kis_paper_stock_quote import KisPaperStockInstrument, validate_kis_paper_stock_quote_request
from .kis_paper_stock_readonly import (
    KisPaperStockPreviewReads,
    KisPaperStockReadOnlyClient,
    _instrument,
)
from .kis_readonly import (
    KisHttpRequest,
    KisHttpResponse,
    KisHttpTransport,
    KisPaperCashSnapshot,
    KisPaperConfig,
    KisPaperOrderableFundsSnapshot,
    KisPaperReadOnlyError,
    KisPaperRequestPacer,
    _request_url_with_query,
)

_QUOTE_PATHS = frozenset({KIS_PAPER_US_SPY_ASKING_PRICE_PATH, KIS_PAPER_US_SPY_PRICE_DETAIL_PATH})


def _bound_instrument(value: object) -> KisPaperStockInstrument:
    try:
        return _instrument(value)
    except KisPaperReadOnlyError:
        raise KisPaperCanaryError("stock_instrument_invalid") from None


class UrllibKisPaperStockCanaryTransport(UrllibKisPaperCanaryTransport):
    """Generic canary transport plus only the two exact bound stock quote GETs.

    Inherited deadline dispatch calls this same _request method. Generic token,
    account, funds, submit and cancel requests retain the unchanged validator,
    shared pacer, direct-only opener and post-pacing pre-wire deadline check.
    """

    def __init__(
        self,
        *,
        instrument: KisPaperStockInstrument,
        timeout_seconds: float = 15.0,
        pacer: KisPaperRequestPacer | None = None,
    ) -> None:
        self._stock_instrument = _bound_instrument(instrument)
        super().__init__(timeout_seconds=timeout_seconds, pacer=pacer)

    @property
    def instrument(self) -> KisPaperStockInstrument:
        return _bound_instrument(self._stock_instrument)

    def _request(
        self,
        request: KisHttpRequest,
        *,
        before_wire: Callable[[], None] | None = None,
    ) -> KisHttpResponse:
        if type(request) is not KisHttpRequest or type(request.url) is not str:
            raise KisPaperCanaryError("request_not_allowlisted")
        request = replace(
            request,
            headers=dict(request.headers),
            query=dict(request.query),
            json_body=None if request.json_body is None else dict(request.json_body),
        )
        try:
            path = urllib.parse.urlsplit(request.url).path
        except ValueError:
            raise KisPaperCanaryError("request_not_allowlisted") from None
        if request.method == "POST" and path in {
            KIS_PAPER_US_BUY_LIMIT_ORDER_PATH,
            KIS_PAPER_US_CANCEL_PATH,
        }:
            body, bound = request.json_body, self.instrument
            if (
                not isinstance(body, Mapping)
                or type(body.get("PDNO")) is not str
                or body["PDNO"] != bound.symbol
                or type(body.get("OVRS_EXCG_CD")) is not str
                or body["OVRS_EXCG_CD"] != bound.order_exchange
            ):
                raise KisPaperCanaryError("stock_instrument_mismatch")
        if path not in _QUOTE_PATHS:
            try:
                return super()._request(request, before_wire=before_wire)
            except KisPaperCanaryError as error:
                raise KisPaperCanaryError(error.code) from None
        try:
            validate_kis_paper_stock_quote_request(request, instrument=self.instrument)
        except KisPaperQuoteError:
            raise KisPaperCanaryError("request_not_allowlisted") from None
        self._pacer.wait_for_request_slot()
        http_request = urllib.request.Request(
            _request_url_with_query(request),
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            if before_wire is not None:
                before_wire()
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
            raise KisPaperCanaryError("transport_failure") from None


class KisPaperStockCanaryClient(KisPaperCanaryClient):
    """One instrument and one in-memory token, using existing canary recovery."""

    def __init__(
        self,
        *,
        config: KisPaperConfig,
        transport: KisHttpTransport,
        instrument: KisPaperStockInstrument,
    ) -> None:
        self._stock_instrument = _bound_instrument(instrument)
        if isinstance(transport, UrllibKisPaperStockCanaryTransport):
            if transport.instrument != self.instrument:
                raise KisPaperCanaryError("stock_transport_binding_mismatch")
        super().__init__(config=config, transport=transport)

    @property
    def instrument(self) -> KisPaperStockInstrument:
        return _bound_instrument(self._stock_instrument)

    def _require_target(self, symbol: str, exchange: str) -> None:
        bound = self.instrument
        if (
            type(symbol) is not str
            or symbol != bound.symbol
            or type(exchange) is not str
            or exchange != bound.order_exchange
        ):
            raise KisPaperCanaryError("stock_instrument_mismatch")

    def _require_intent(self, intent: KisPaperCanaryIntent) -> None:
        if type(intent) is not KisPaperCanaryIntent:
            raise KisPaperCanaryError("stock_intent_invalid")
        self._require_target(intent.symbol, intent.exchange)

    def orderable_funds_at_limit(
        self,
        *,
        symbol: str,
        exchange: str,
        limit_price: Decimal,
    ) -> tuple[KisPaperCashSnapshot, KisPaperOrderableFundsSnapshot]:
        self._require_target(symbol, exchange)
        reader = KisPaperStockReadOnlyClient(
            config=self._config,
            transport=self._transport,
            access_token=self._access_token,
        )
        try:
            return reader.stock_orderable_funds_at_limit(
                instrument=self.instrument,
                limit_price=limit_price,
            )
        except KisPaperReadOnlyError as error:
            raise KisPaperReadOnlyError(error.code) from None
        finally:
            self._access_token = reader._access_token

    def stock_preview_snapshot(
        self,
        *,
        expected_account_ref: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> KisPaperStockPreviewReads:
        reader = KisPaperStockReadOnlyClient(
            config=self._config,
            transport=self._transport,
            access_token=self._access_token,
        )
        try:
            return reader.stock_preview_snapshot(
                instrument=self.instrument,
                expected_account_ref=expected_account_ref,
                clock=clock,
            )
        except KisPaperReadOnlyError as error:
            raise KisPaperReadOnlyError(error.code) from None
        finally:
            self._access_token = reader._access_token

    def reconcile(
        self,
        state: KisPaperCanaryState,
        *,
        now: datetime,
    ) -> KisPaperCanaryReconciliation:
        if type(state) is not KisPaperCanaryState:
            raise KisPaperCanaryError("stock_state_invalid")
        self._require_intent(state.intent)
        return super().reconcile(state, now=now)

    def submit_limit(
        self,
        intent: KisPaperCanaryIntent,
        *,
        now: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> tuple[bool, str | None]:
        self._require_intent(intent)
        return super().submit_limit(intent, now=now, clock=clock)

    def _cancel_limit_order(self, intent: KisPaperCanaryIntent, *, broker_order_id: str) -> bool:
        self._require_intent(intent)
        return super()._cancel_limit_order(intent, broker_order_id=broker_order_id)

"""Explicit NASDAQ stock read-only observations; never an intent or order path."""

from __future__ import annotations

import math
import re
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
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_US_EXCHANGES,
    KisHttpRequest,
    KisHttpResponse,
    KisPaperAccountIdentity,
    KisPaperCashSnapshot,
    KisPaperOpenOrder,
    KisPaperOpenOrdersSnapshot,
    KisPaperOrderableFundsSnapshot,
    KisPaperPosition,
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


def _exit_typed(value, expected):
    try:
        if type(value) is not expected or replace(value) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError, ArithmeticError):
        raise KisPaperReadOnlyError("stock_exit_snapshot_invalid") from None


@dataclass(frozen=True, repr=False)
class KisPaperStockExitAccountSnapshot:
    """Completed sequential positions/orders only; no cash or settlement claim."""

    identity: KisPaperAccountIdentity
    positions: tuple[KisPaperPosition, ...]
    open_orders: KisPaperOpenOrdersSnapshot
    captured_at: datetime

    def __post_init__(self):
        _exit_typed(self.identity, KisPaperAccountIdentity)
        _exit_typed(self.open_orders, KisPaperOpenOrdersSnapshot)
        if type(self.positions) is not tuple or self.open_orders.complete is not True:
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid")
        for position in self.positions:
            _exit_typed(position, KisPaperPosition)
        for order in self.open_orders.orders:
            _exit_typed(order, KisPaperOpenOrder)
        if len({(p.exchange, p.symbol) for p in self.positions}) != len(self.positions):
            raise KisPaperReadOnlyError("balance_response_duplicate")
        try:
            require_utc(self.captured_at)
        except (ValueError, TypeError, AttributeError):
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid") from None
        times = [
            self.identity.captured_at,
            self.open_orders.captured_at,
            *(p.captured_at for p in self.positions),
            *(o.captured_at for o in self.open_orders.orders),
        ]
        if any(at != self.captured_at for at in times):
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid")


@dataclass(frozen=True, repr=False)
class KisPaperStockExitReads:
    account_ref: str
    instrument: KisPaperStockInstrument
    snapshot: KisPaperStockExitAccountSnapshot
    quote: KisPaperSpyLimitInput
    started_at: datetime
    completed_at: datetime
    elapsed_seconds: float

    def __post_init__(self):
        if (
            type(self.account_ref) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.account_ref) is None
        ):
            raise KisPaperReadOnlyError("stock_account_binding_mismatch")
        _instrument(self.instrument)
        _exit_typed(self.snapshot, KisPaperStockExitAccountSnapshot)
        _exit_typed(self.quote, KisPaperSpyLimitInput)
        try:
            require_utc(self.started_at)
            require_utc(self.completed_at)
        except (ValueError, TypeError, AttributeError):
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid") from None
        if (
            type(self.elapsed_seconds) is not float
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid")
        if (
            not self.started_at <= self.snapshot.captured_at <= self.completed_at
            or self.completed_at - self.snapshot.captured_at > KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
        ):
            raise KisPaperReadOnlyError("stock_snapshot_stale")
        try:
            derive_kis_paper_marketable_limit(
                self.quote, side="sell", observed_at=self.completed_at
            )
        except KisPaperQuoteError as error:
            raise KisPaperReadOnlyError(error.code) from None

    @property
    def positions(self) -> tuple[KisPaperPosition, ...]:
        return self.snapshot.positions

    @property
    def open_orders(self) -> tuple[KisPaperOpenOrder, ...]:
        return self.snapshot.open_orders.orders


class _StockExitAccountClient(KisPaperReadOnlyClient):
    """Reuse native page/row parsers, rejecting ambiguous page metadata first."""

    def _read_only_get(self, endpoint, **arguments):
        response = super()._read_only_get(endpoint, **arguments)
        if endpoint in {KIS_PAPER_BALANCE_ENDPOINT, KIS_PAPER_OPEN_ORDERS_ENDPOINT}:
            response.payload(reject_duplicate_keys=True)
            if response.header("tr_cont").strip().upper() not in {"", "D", "E", "M", "F"}:
                raise KisPaperReadOnlyError("stock_exit_pagination_invalid")
        return response


class KisPaperStockReadOnlyClient(KisPaperReadOnlyClient):
    """One reused transient client for account, bound quotes and exact funds."""

    def _dispatch_stock_quote(
        self, request: KisHttpRequest, *, instrument: KisPaperStockInstrument
    ) -> KisHttpResponse:
        _validate_quote(request, instrument)
        return self._transport.request(request)

    def stock_exit_account_snapshot(
        self,
        *,
        instrument: KisPaperStockInstrument,
        expected_account_ref: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> KisPaperStockExitAccountSnapshot:
        """Complete all existing account venue groups without querying funds."""
        from .kis_paper_spy_fill_cycle import _digest

        _instrument(instrument)
        config = self._config
        account_ref = _digest([config.base_url, config.account_number, config.account_product_code])
        if type(expected_account_ref) is not str or expected_account_ref != account_ref:
            raise KisPaperReadOnlyError("stock_account_binding_mismatch")
        started_at = require_utc(clock())
        reader = _StockExitAccountClient(
            config=config, transport=self._transport, access_token=self._access_token
        )
        try:
            token = reader._access_token or reader._issue_access_token()
            captured_at = require_utc(clock())
            orders = reader._open_orders(token, captured_at)
            positions = {}
            for exchange in KIS_PAPER_US_EXCHANGES:
                for row in reader._balance_positions(token, exchange, captured_at):
                    key = (row.exchange, row.symbol)
                    prior = positions.get(key)
                    if prior is not None and (
                        prior.currency,
                        prior.quantity,
                        prior.average_price,
                    ) != (row.currency, row.quantity, row.average_price):
                        raise KisPaperReadOnlyError("balance_response_duplicate")
                    positions.setdefault(key, row)
            completed_at = require_utc(clock())
            if (
                not started_at <= captured_at <= completed_at
                or completed_at - captured_at > KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
            ):
                raise KisPaperReadOnlyError("stock_snapshot_stale")
            return KisPaperStockExitAccountSnapshot(
                KisPaperAccountIdentity(config.masked_account_identity, captured_at),
                tuple(positions[key] for key in sorted(positions)),
                orders,
                captured_at,
            )
        except KisPaperReadOnlyError as error:
            raise KisPaperReadOnlyError(error.code) from None
        except (ValueError, TypeError, AttributeError):
            raise KisPaperReadOnlyError("stock_exit_snapshot_invalid") from None
        except (OSError, TimeoutError):
            raise KisPaperReadOnlyError("transport_failure") from None
        finally:
            self._access_token = reader._access_token
            self._latest_open_order_records = reader._latest_open_order_records

    def stock_exit_snapshot(
        self,
        *,
        instrument: KisPaperStockInstrument,
        expected_account_ref: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> KisPaperStockExitReads:
        """Account/positions/orders then fresh bid/tick, never cash/buying power."""
        bound = _instrument(instrument)
        started_at, started = require_utc(clock()), time.monotonic()
        snapshot = self.stock_exit_account_snapshot(
            instrument=bound, expected_account_ref=expected_account_ref, clock=clock
        )
        responses = {}
        try:
            for kind in ("asking_price", "price_detail"):
                response = self._dispatch_stock_quote(
                    build_kis_paper_stock_quote_request(
                        config=self._config,
                        access_token=self._access_token,
                        instrument=bound,
                        kind=kind,
                    ),
                    instrument=bound,
                )
                _require_http_success(response, "stock_quote_rejected")
                if response.header("tr_cont").strip().upper() not in {"", "D", "E"}:
                    raise KisPaperReadOnlyError("stock_quote_incomplete")
                responses[kind] = response.payload(reject_duplicate_keys=True)
            quote = parse_kis_paper_qqq_limit_input(
                asking_price_payload=responses["asking_price"],
                price_detail_payload=responses["price_detail"],
                observed_at=require_utc(clock()),
            )
            return KisPaperStockExitReads(
                expected_account_ref,
                bound,
                snapshot,
                quote,
                started_at,
                require_utc(clock()),
                time.monotonic() - started,
            )
        except (KisPaperReadOnlyError, KisPaperQuoteError) as error:
            raise KisPaperReadOnlyError(error.code) from None
        except (OSError, TimeoutError):
            raise KisPaperReadOnlyError("transport_failure") from None

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

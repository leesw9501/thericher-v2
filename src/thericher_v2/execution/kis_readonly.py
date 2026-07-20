"""Bounded KIS virtual-paper account discovery with no order actions.

This module is intentionally separate from the disabled broker lifecycle
boundary. It can collect a single, typed virtual-paper account view, including
open-order evidence, but it cannot create, change, or cancel an order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Protocol

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

KIS_PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
KIS_PAPER_TOKEN_PATH = "/oauth2/tokenP"
DEFAULT_KIS_PAPER_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")

KIS_PAPER_ENV_KEYS = (
    "KIS_PAPER_APP_KEY",
    "KIS_PAPER_APP_SECRET",
    "KIS_PAPER_ACCOUNT_NO",
    "KIS_PAPER_ACCOUNT_PRODUCT_CODE",
)
KIS_PAPER_US_EXCHANGES = ("NASD", "NYSE", "AMEX")
# KIS documents `inquire-nccs` NASD as the single US-wide query value.
KIS_PAPER_OPEN_ORDER_QUERY_EXCHANGES = ("NASD",)
KIS_PAPER_ORDERABLE_REFERENCE_EXCHANGE = "NASD"
KIS_PAPER_ORDERABLE_REFERENCE_SYMBOL = "SPY"
KIS_PAPER_ORDERABLE_REFERENCE_PRICE = Decimal("1")
MAX_KIS_PAPER_BALANCE_PAGES = 10


class KisPaperReadOnlyError(RuntimeError):
    """A non-secret reason why a read-only discovery must fail closed."""

    def __init__(self, code: str, *, diagnostic: Mapping[str, str] | None = None) -> None:
        self.code = code
        self.diagnostic = dict(diagnostic or {})
        super().__init__(code)


@dataclass(frozen=True)
class KisPaperReadOnlyEndpoint:
    """One documented virtual-paper GET endpoint and its fixed query shape."""

    name: Literal["balance", "orderable_funds", "open_orders"]
    path: str
    tr_id: str
    query_keys: frozenset[str]

    def __post_init__(self) -> None:
        if not self.path.startswith("/") or not self.tr_id:
            raise ValueError("read-only endpoint must have a path and tr_id")


KIS_PAPER_BALANCE_ENDPOINT = KisPaperReadOnlyEndpoint(
    name="balance",
    path="/uapi/overseas-stock/v1/trading/inquire-balance",
    tr_id="VTTS3012R",
    query_keys=frozenset(
        {
            "CANO",
            "ACNT_PRDT_CD",
            "OVRS_EXCG_CD",
            "TR_CRCY_CD",
            "CTX_AREA_FK200",
            "CTX_AREA_NK200",
        }
    ),
)
KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT = KisPaperReadOnlyEndpoint(
    name="orderable_funds",
    path="/uapi/overseas-stock/v1/trading/inquire-psamount",
    tr_id="VTTS3007R",
    query_keys=frozenset(
        {
            "CANO",
            "ACNT_PRDT_CD",
            "OVRS_EXCG_CD",
            "OVRS_ORD_UNPR",
            "ITEM_CD",
        }
    ),
)
KIS_PAPER_OPEN_ORDERS_ENDPOINT = KisPaperReadOnlyEndpoint(
    name="open_orders",
    path="/uapi/overseas-stock/v1/trading/inquire-nccs",
    tr_id="VTTS3018R",
    query_keys=frozenset(
        {
            "CANO",
            "ACNT_PRDT_CD",
            "OVRS_EXCG_CD",
            "SORT_SQN",
            "CTX_AREA_FK200",
            "CTX_AREA_NK200",
        }
    ),
)
KIS_PAPER_READ_ONLY_ENDPOINTS = (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
)


@dataclass(frozen=True)
class KisPaperConfig:
    """Credentials and account routing for the fixed virtual-paper host."""

    app_key: str = field(repr=False)
    app_secret: str = field(repr=False)
    account_number: str = field(repr=False)
    account_product_code: str = field(repr=False)
    base_url: str = KIS_PAPER_BASE_URL

    def __post_init__(self) -> None:
        _require_exact_paper_base_url(self.base_url)
        object.__setattr__(self, "base_url", KIS_PAPER_BASE_URL)
        for value in (self.app_key, self.app_secret):
            if not isinstance(value, str) or not value.strip():
                raise KisPaperReadOnlyError("config_missing")
        if not self.account_number.isdigit() or len(self.account_number) != 8:
            raise KisPaperReadOnlyError("config_account_invalid")
        if not self.account_product_code.isdigit() or len(self.account_product_code) != 2:
            raise KisPaperReadOnlyError("config_product_invalid")

    @property
    def masked_account_identity(self) -> str:
        return f"****{self.account_number[-4:]}-**"


@dataclass(frozen=True, repr=False)
class KisHttpRequest:
    """Internal request shape whose repr never exposes credential values."""

    method: Literal["GET", "POST"]
    url: str
    headers: Mapping[str, str] = field(repr=False)
    query: Mapping[str, str] = field(default_factory=dict, repr=False)
    json_body: Mapping[str, str] | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        endpoint = urllib.parse.urlparse(self.url).path
        return (
            "KisHttpRequest("
            f"method={self.method!r}, endpoint={endpoint!r}, "
            f"query_keys={tuple(sorted(self.query))!r})"
        )


@dataclass(frozen=True, repr=False)
class KisHttpResponse:
    """Internal response bytes that are parsed in memory and never persisted raw."""

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
    ) -> KisHttpResponse:
        return cls(
            status_code=status_code,
            headers=dict(headers or {}),
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )

    def payload(self) -> Mapping[str, Any]:
        try:
            decoded = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise KisPaperReadOnlyError("response_invalid") from error
        if not isinstance(decoded, Mapping):
            raise KisPaperReadOnlyError("response_invalid")
        return decoded

    def header(self, name: str) -> str:
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return ""


class KisHttpTransport(Protocol):
    """Injectable transport for the only allowed KIS discovery requests."""

    def request(self, request: KisHttpRequest) -> KisHttpResponse: ...


class UrllibKisHttpTransport:
    """Small standard-library transport guarded by the same request allowlist."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        _validate_allowlisted_request(request)
        url = _request_url_with_query(request)
        data = (
            json.dumps(request.json_body, separators=(",", ":")).encode("utf-8")
            if request.json_body is not None
            else None
        )
        http_request = urllib.request.Request(
            url,
            data=data,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout_seconds) as response:
                return KisHttpResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            return KisHttpResponse(
                status_code=error.code,
                headers=dict(error.headers.items()) if error.headers is not None else {},
                body=error.read(),
            )
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise KisPaperReadOnlyError("transport_failure") from error


@dataclass(frozen=True)
class KisPaperAccountIdentity:
    masked_account: str
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.masked_account.startswith("****") or "-**" not in self.masked_account:
            raise ValueError("account identity must remain masked")
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperCashSnapshot:
    """Exact `ord_psbl_frcr_amt` mapping; not settled cash or account equity."""

    currency: str
    available_cash: Decimal
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "available_cash", _non_negative_decimal(self.available_cash))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperOrderableFundsSnapshot:
    currency: str
    orderable_funds: Decimal
    reference_exchange: str
    reference_symbol: str
    reference_price: Decimal
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "orderable_funds", _non_negative_decimal(self.orderable_funds))
        object.__setattr__(self, "reference_exchange", _required_text(self.reference_exchange))
        object.__setattr__(self, "reference_symbol", _required_text(self.reference_symbol))
        object.__setattr__(self, "reference_price", _positive_decimal(self.reference_price))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperPosition:
    symbol: str
    exchange: str
    currency: str
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _required_text(self.symbol).upper())
        object.__setattr__(self, "exchange", _required_text(self.exchange).upper())
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "quantity", _positive_decimal(self.quantity))
        object.__setattr__(self, "average_price", _positive_decimal(self.average_price))
        object.__setattr__(self, "market_price", _positive_decimal(self.market_price))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperOpenOrder:
    """One active order represented without its raw KIS order identifier."""

    order_reference: str
    symbol: str
    exchange: str
    currency: str
    side: Literal["buy", "sell"]
    requested_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    limit_price: Decimal | None
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.order_reference.startswith("open-"):
            raise ValueError("open order reference must be redacted")
        object.__setattr__(self, "symbol", _required_text(self.symbol).upper())
        object.__setattr__(self, "exchange", _required_text(self.exchange).upper())
        object.__setattr__(self, "currency", _currency(self.currency))
        if self.side not in {"buy", "sell"}:
            raise ValueError("open order side must be buy or sell")
        object.__setattr__(self, "requested_quantity", _positive_decimal(self.requested_quantity))
        object.__setattr__(self, "filled_quantity", _non_negative_decimal(self.filled_quantity))
        object.__setattr__(self, "remaining_quantity", _positive_decimal(self.remaining_quantity))
        if self.filled_quantity + self.remaining_quantity != self.requested_quantity:
            raise ValueError("open order quantities must reconcile")
        if self.limit_price is not None:
            object.__setattr__(self, "limit_price", _positive_decimal(self.limit_price))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperOpenOrdersSnapshot:
    """Complete virtual-paper open-order evidence from the fixed read-only query."""

    orders: tuple[KisPaperOpenOrder, ...]
    captured_at: datetime
    complete: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "orders", tuple(self.orders))
        if not self.complete:
            raise ValueError("collected open-order evidence must be complete")
        references = [order.order_reference for order in self.orders]
        if len(set(references)) != len(references):
            raise ValueError("open-order evidence must not contain duplicate references")
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperReadOnlySnapshot:
    identity: KisPaperAccountIdentity
    cash: KisPaperCashSnapshot
    orderable_funds: KisPaperOrderableFundsSnapshot
    positions: tuple[KisPaperPosition, ...]
    open_orders: KisPaperOpenOrdersSnapshot
    captured_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "positions", tuple(self.positions))
        if not self.open_orders.complete:
            raise ValueError("read-only snapshot requires complete open-order evidence")
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True)
class KisPaperReadOnlyReconciliation:
    """A discovery result is intentionally never authorization to submit."""

    reconciled_at: datetime
    safe_to_submit: Literal[False]
    reasons: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.safe_to_submit is not False or not self.reasons:
            raise ValueError("read-only reconciliation must fail closed")
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))
        object.__setattr__(self, "reconciled_at", require_utc(self.reconciled_at, "reconciled_at"))


@dataclass(frozen=True)
class KisPaperDiscoveryOutcome:
    status: Literal["collected", "failed_closed"]
    reason_code: str
    captured_at: datetime
    snapshot: KisPaperReadOnlySnapshot | None = None
    reconciliation: KisPaperReadOnlyReconciliation | None = None
    diagnostic: Mapping[str, str] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status == "collected" and (self.snapshot is None or self.reconciliation is None):
            raise ValueError("collected discovery requires typed evidence")
        if self.status == "failed_closed" and (
            self.snapshot is not None or self.reconciliation is not None
        ):
            raise ValueError("failed discovery must not retain partial account evidence")
        if self.status == "collected" and self.diagnostic:
            raise ValueError("collected discovery must not retain failure diagnostics")
        if set(self.diagnostic) - {
            "endpoint",
            "tr_id",
            "http_status",
        }:
            raise ValueError("read-only diagnostics must be an allowlisted string mapping")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in self.diagnostic.items()
        ):
            raise ValueError("read-only diagnostics must be an allowlisted string mapping")
        if self.diagnostic:
            _validate_read_only_diagnostic(self.diagnostic)
        object.__setattr__(self, "diagnostic", dict(self.diagnostic))
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))

    def evidence_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "kind": "kis_paper_read_only_discovery",
            "status": self.status,
            "reason_code": self.reason_code,
            "captured_at": self.captured_at.isoformat(),
            "paper_only": True,
            "submit_capability": False,
        }
        if self.snapshot is None or self.reconciliation is None:
            if self.diagnostic:
                payload["diagnostic"] = dict(self.diagnostic)
            return payload
        payload["snapshot"] = {
            "identity": {
                "masked_account": self.snapshot.identity.masked_account,
                "captured_at": self.snapshot.identity.captured_at.isoformat(),
            },
            "cash": {
                "currency": self.snapshot.cash.currency,
                "available_cash": str(self.snapshot.cash.available_cash),
                "captured_at": self.snapshot.cash.captured_at.isoformat(),
            },
            "orderable_funds": {
                "currency": self.snapshot.orderable_funds.currency,
                "orderable_funds": str(self.snapshot.orderable_funds.orderable_funds),
                "reference_exchange": self.snapshot.orderable_funds.reference_exchange,
                "reference_symbol": self.snapshot.orderable_funds.reference_symbol,
                "reference_price": str(self.snapshot.orderable_funds.reference_price),
                "captured_at": self.snapshot.orderable_funds.captured_at.isoformat(),
            },
            "positions": [
                {
                    "symbol": position.symbol,
                    "exchange": position.exchange,
                    "currency": position.currency,
                    "quantity": str(position.quantity),
                    "average_price": str(position.average_price),
                    "market_price": str(position.market_price),
                    "captured_at": position.captured_at.isoformat(),
                }
                for position in self.snapshot.positions
            ],
            "open_orders": {
                "complete": self.snapshot.open_orders.complete,
                "orders": [
                    {
                        "order_reference": order.order_reference,
                        "symbol": order.symbol,
                        "exchange": order.exchange,
                        "currency": order.currency,
                        "side": order.side,
                        "requested_quantity": str(order.requested_quantity),
                        "filled_quantity": str(order.filled_quantity),
                        "remaining_quantity": str(order.remaining_quantity),
                        "limit_price": (
                            str(order.limit_price) if order.limit_price is not None else None
                        ),
                        "captured_at": order.captured_at.isoformat(),
                    }
                    for order in self.snapshot.open_orders.orders
                ],
                "captured_at": self.snapshot.open_orders.captured_at.isoformat(),
            },
        }
        payload["reconciliation"] = {
            "safe_to_submit": self.reconciliation.safe_to_submit,
            "reasons": list(self.reconciliation.reasons),
            "reconciled_at": self.reconciliation.reconciled_at.isoformat(),
        }
        return payload


class KisPaperReadOnlyClient:
    """Fetch one fixed virtual-paper discovery snapshot through an injected transport."""

    def __init__(self, *, config: KisPaperConfig, transport: KisHttpTransport) -> None:
        self._config = config
        self._transport = transport

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        access_token = self._issue_access_token()
        captured_at = datetime.now(UTC)
        open_orders = self._open_orders(access_token, captured_at)
        positions: list[KisPaperPosition] = []
        for exchange in KIS_PAPER_US_EXCHANGES:
            positions.extend(self._balance_positions(access_token, exchange, captured_at))
        _ensure_unique_positions(positions)
        cash, orderable_funds = self._cash_and_orderable_funds(access_token, captured_at)
        return KisPaperReadOnlySnapshot(
            identity=KisPaperAccountIdentity(self._config.masked_account_identity, captured_at),
            cash=cash,
            orderable_funds=orderable_funds,
            positions=tuple(sorted(positions, key=lambda item: (item.exchange, item.symbol))),
            open_orders=open_orders,
            captured_at=captured_at,
        )

    def _issue_access_token(self) -> str:
        response = self._transport.request(
            KisHttpRequest(
                method="POST",
                url=f"{self._config.base_url}{KIS_PAPER_TOKEN_PATH}",
                headers={
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                json_body={
                    "grant_type": "client_credentials",
                    "appkey": self._config.app_key,
                    "appsecret": self._config.app_secret,
                },
            )
        )
        _require_http_success(response, "auth_rejected")
        payload = response.payload()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise KisPaperReadOnlyError("auth_response_invalid")
        return token

    def _balance_positions(
        self,
        access_token: str,
        exchange: str,
        captured_at: datetime,
    ) -> list[KisPaperPosition]:
        query = {
            "CANO": self._config.account_number,
            "ACNT_PRDT_CD": self._config.account_product_code,
            "OVRS_EXCG_CD": exchange,
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        positions: list[KisPaperPosition] = []
        continuation_header = ""
        for _page in range(MAX_KIS_PAPER_BALANCE_PAGES):
            response = self._read_only_get(
                KIS_PAPER_BALANCE_ENDPOINT,
                access_token=access_token,
                query=query,
                continuation_header=continuation_header,
            )
            payload = _successful_payload(
                response,
                "balance_rejected",
                endpoint=KIS_PAPER_BALANCE_ENDPOINT,
            )
            positions.extend(_parse_balance_positions(payload, exchange, captured_at))
            continuation = response.header("tr_cont").strip().upper()
            if continuation not in {"M", "F"}:
                return positions
            query = {
                **query,
                "CTX_AREA_FK200": _response_text(
                    payload, "ctx_area_fk200", "balance_response_incomplete"
                ),
                "CTX_AREA_NK200": _response_text(
                    payload, "ctx_area_nk200", "balance_response_incomplete"
                ),
            }
            if not query["CTX_AREA_FK200"] or not query["CTX_AREA_NK200"]:
                raise KisPaperReadOnlyError("balance_response_incomplete")
            continuation_header = "N"
        raise KisPaperReadOnlyError("balance_pagination_incomplete")

    def _cash_and_orderable_funds(
        self,
        access_token: str,
        captured_at: datetime,
    ) -> tuple[KisPaperCashSnapshot, KisPaperOrderableFundsSnapshot]:
        response = self._read_only_get(
            KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
            access_token=access_token,
            query={
                "CANO": self._config.account_number,
                "ACNT_PRDT_CD": self._config.account_product_code,
                "OVRS_EXCG_CD": KIS_PAPER_ORDERABLE_REFERENCE_EXCHANGE,
                "OVRS_ORD_UNPR": str(KIS_PAPER_ORDERABLE_REFERENCE_PRICE),
                "ITEM_CD": KIS_PAPER_ORDERABLE_REFERENCE_SYMBOL,
            },
        )
        payload = _successful_payload(
            response,
            "orderable_funds_rejected",
            endpoint=KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
        )
        output = payload.get("output")
        if not isinstance(output, Mapping):
            raise KisPaperReadOnlyError("orderable_funds_response_incomplete")
        currency = _response_text(output, "tr_crcy_cd", "orderable_funds_response_incomplete")
        available_cash = _response_decimal(
            output,
            "ord_psbl_frcr_amt",
            "orderable_funds_response_incomplete",
        )
        orderable_funds = _response_decimal(
            output,
            "ovrs_ord_psbl_amt",
            "orderable_funds_response_incomplete",
        )
        return (
            KisPaperCashSnapshot(currency, available_cash, captured_at),
            KisPaperOrderableFundsSnapshot(
                currency=currency,
                orderable_funds=orderable_funds,
                reference_exchange=KIS_PAPER_ORDERABLE_REFERENCE_EXCHANGE,
                reference_symbol=KIS_PAPER_ORDERABLE_REFERENCE_SYMBOL,
                reference_price=KIS_PAPER_ORDERABLE_REFERENCE_PRICE,
                captured_at=captured_at,
            ),
        )

    def _open_orders(
        self,
        access_token: str,
        captured_at: datetime,
    ) -> KisPaperOpenOrdersSnapshot:
        orders: list[KisPaperOpenOrder] = []
        for exchange in KIS_PAPER_OPEN_ORDER_QUERY_EXCHANGES:
            query = {
                "CANO": self._config.account_number,
                "ACNT_PRDT_CD": self._config.account_product_code,
                "OVRS_EXCG_CD": exchange,
                "SORT_SQN": "DS",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            }
            continuation_header = ""
            for _page in range(MAX_KIS_PAPER_BALANCE_PAGES):
                response = self._read_only_get(
                    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
                    access_token=access_token,
                    query=query,
                    continuation_header=continuation_header,
                )
                payload = _successful_payload(
                    response,
                    "open_orders_rejected",
                    endpoint=KIS_PAPER_OPEN_ORDERS_ENDPOINT,
                )
                orders.extend(_parse_open_orders(payload, captured_at))
                continuation = response.header("tr_cont").strip().upper()
                if continuation not in {"M", "F"}:
                    break
                query = {
                    **query,
                    "CTX_AREA_FK200": _response_text(
                        payload, "ctx_area_fk200", "open_orders_response_incomplete"
                    ),
                    "CTX_AREA_NK200": _response_text(
                        payload, "ctx_area_nk200", "open_orders_response_incomplete"
                    ),
                }
                if not query["CTX_AREA_FK200"] or not query["CTX_AREA_NK200"]:
                    raise KisPaperReadOnlyError("open_orders_response_incomplete")
                continuation_header = "N"
            else:
                raise KisPaperReadOnlyError("open_orders_pagination_incomplete")
        _ensure_unique_open_orders(orders)
        return KisPaperOpenOrdersSnapshot(
            orders=tuple(sorted(orders, key=lambda item: item.order_reference)),
            captured_at=captured_at,
        )

    def _read_only_get(
        self,
        endpoint: KisPaperReadOnlyEndpoint,
        *,
        access_token: str,
        query: Mapping[str, str],
        continuation_header: str = "",
    ) -> KisHttpResponse:
        if set(query) != endpoint.query_keys:
            raise KisPaperReadOnlyError("query_not_allowlisted")
        headers = {
            "authorization": f"Bearer {access_token}",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
            "tr_id": endpoint.tr_id,
            "custtype": "P",
            "tr_cont": continuation_header,
        }
        return self._transport.request(
            KisHttpRequest(
                method="GET",
                url=f"{self._config.base_url}{endpoint.path}",
                headers=headers,
                query=dict(query),
            )
        )


def load_kis_paper_config(dotenv_path: Path) -> KisPaperConfig:
    """Read only the four explicitly authorized values from a root ``.env`` file."""

    values: dict[str, str] = {}
    try:
        with dotenv_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                parsed = _authorized_dotenv_value(raw_line)
                if parsed is None:
                    continue
                key, value = parsed
                if key in values:
                    raise KisPaperReadOnlyError("config_duplicate")
                values[key] = value
    except FileNotFoundError as error:
        raise KisPaperReadOnlyError("config_missing") from error
    if any(not values.get(key, "").strip() for key in KIS_PAPER_ENV_KEYS):
        raise KisPaperReadOnlyError("config_missing")
    return KisPaperConfig(
        app_key=values["KIS_PAPER_APP_KEY"].strip(),
        app_secret=values["KIS_PAPER_APP_SECRET"].strip(),
        account_number=values["KIS_PAPER_ACCOUNT_NO"].strip(),
        account_product_code=values["KIS_PAPER_ACCOUNT_PRODUCT_CODE"].strip(),
    )


def load_kis_paper_config_from_environment(
    environment: Mapping[str, str] | None = None,
) -> KisPaperConfig:
    """Read exactly the four approved paper values from an injected mapping."""

    source = os.environ if environment is None else environment
    values: dict[str, str] = {}
    for key in KIS_PAPER_ENV_KEYS:
        value = source.get(key, "")
        values[key] = value.strip() if isinstance(value, str) else ""
    if any(not values[key] for key in KIS_PAPER_ENV_KEYS):
        raise KisPaperReadOnlyError("config_missing")
    return KisPaperConfig(
        app_key=values["KIS_PAPER_APP_KEY"],
        app_secret=values["KIS_PAPER_APP_SECRET"],
        account_number=values["KIS_PAPER_ACCOUNT_NO"],
        account_product_code=values["KIS_PAPER_ACCOUNT_PRODUCT_CODE"],
    )


def reconcile_kis_paper_readonly(
    snapshot: KisPaperReadOnlySnapshot,
    *,
    reconciled_at: datetime | None = None,
) -> KisPaperReadOnlyReconciliation:
    """Return a typed fail-closed result; this discovery cannot enable submission."""

    reasons = ["read_only_boundary"]
    if snapshot.cash.currency != snapshot.orderable_funds.currency:
        reasons.append("cash_orderable_currency_mismatch")
    if len({(position.exchange, position.symbol) for position in snapshot.positions}) != len(
        snapshot.positions
    ):
        reasons.append("position_duplicate")
    if len({order.order_reference for order in snapshot.open_orders.orders}) != len(
        snapshot.open_orders.orders
    ):
        reasons.append("open_order_duplicate")
    return KisPaperReadOnlyReconciliation(
        reconciled_at=reconciled_at or datetime.now(UTC),
        safe_to_submit=False,
        reasons=tuple(reasons),
    )


def run_kis_paper_readonly_discovery(
    *,
    dotenv_path: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None = None,
) -> tuple[KisPaperDiscoveryOutcome, Path]:
    """Collect or fail closed once, then write only redacted evidence outside Git."""

    captured_at = datetime.now(UTC)
    try:
        config = load_kis_paper_config(dotenv_path)
        client = KisPaperReadOnlyClient(
            config=config,
            transport=transport or UrllibKisHttpTransport(),
        )
        snapshot = client.snapshot()
        reconciliation = reconcile_kis_paper_readonly(snapshot)
        outcome = KisPaperDiscoveryOutcome(
            status="collected",
            reason_code="read_only_snapshot_collected",
            captured_at=snapshot.captured_at,
            snapshot=snapshot,
            reconciliation=reconciliation,
        )
    except KisPaperReadOnlyError as error:
        outcome = KisPaperDiscoveryOutcome(
            status="failed_closed",
            reason_code=error.code,
            captured_at=captured_at,
            diagnostic=error.diagnostic,
        )
    except Exception:
        outcome = KisPaperDiscoveryOutcome(
            status="failed_closed",
            reason_code="unexpected_failure",
            captured_at=captured_at,
        )
    return outcome, write_kis_paper_readonly_evidence(
        outcome,
        artifact_root=artifact_root,
        repository_root=repository_root,
    )


def write_kis_paper_readonly_evidence(
    outcome: KisPaperDiscoveryOutcome,
    *,
    artifact_root: Path,
    repository_root: Path,
) -> Path:
    """Atomically persist redacted discovery evidence only under an external root."""

    resolved_root = artifact_root.resolve()
    resolved_repo = repository_root.resolve()
    if _is_within(resolved_root, resolved_repo):
        raise KisPaperReadOnlyError("artifact_root_inside_repository")
    destination = (
        resolved_root
        / "execution"
        / "kis-paper-readonly"
        / f"{outcome.captured_at.strftime('%Y%m%dT%H%M%S%fZ')}-{outcome.status}.json"
    )
    if destination.exists():
        raise KisPaperReadOnlyError("evidence_already_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(outcome.evidence_payload(), handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one KIS virtual-paper read-only discovery")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_KIS_PAPER_ARTIFACT_ROOT)
    arguments = parser.parse_args(argv)
    repository_root = arguments.repository_root.resolve()
    outcome, evidence_path = run_kis_paper_readonly_discovery(
        dotenv_path=repository_root / ".env",
        artifact_root=arguments.artifact_root,
        repository_root=repository_root,
    )
    print(
        json.dumps(
            {
                "status": outcome.status,
                "reason_code": outcome.reason_code,
                "evidence_path": str(evidence_path),
                "safe_to_submit": False,
            },
            sort_keys=True,
        )
    )
    return 0 if outcome.status == "collected" else 2


def _authorized_dotenv_value(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    key, separator, value = line.partition("=")
    key = key.strip()
    if key not in KIS_PAPER_ENV_KEYS:
        return None
    if not separator:
        return key, ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _require_exact_paper_base_url(base_url: str) -> None:
    try:
        parsed = urllib.parse.urlparse(base_url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname == "openapivts.koreainvestment.com"
            and parsed.port == 29443
            and parsed.path in {"", "/"}
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        valid = False
    if not valid:
        raise KisPaperReadOnlyError("paper_host_required")


def _validate_allowlisted_request(request: KisHttpRequest) -> None:
    _require_exact_paper_base_url(_base_url_from_endpoint(request.url))
    parsed = urllib.parse.urlparse(request.url)
    if parsed.query or parsed.fragment:
        raise KisPaperReadOnlyError("request_not_allowlisted")
    if request.method == "POST":
        if (
            parsed.path != KIS_PAPER_TOKEN_PATH
            or request.query
            or request.json_body is None
            or set(request.json_body) != {"grant_type", "appkey", "appsecret"}
            or request.json_body.get("grant_type") != "client_credentials"
        ):
            raise KisPaperReadOnlyError("request_not_allowlisted")
        return
    if request.method != "GET":
        raise KisPaperReadOnlyError("request_not_allowlisted")
    endpoint = next(
        (candidate for candidate in KIS_PAPER_READ_ONLY_ENDPOINTS if candidate.path == parsed.path),
        None,
    )
    if (
        endpoint is None
        or request.json_body is not None
        or set(request.query) != endpoint.query_keys
        or request.headers.get("tr_id") != endpoint.tr_id
        or not request.headers.get("authorization", "").startswith("Bearer ")
    ):
        raise KisPaperReadOnlyError("request_not_allowlisted")


def _base_url_from_endpoint(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _request_url_with_query(request: KisHttpRequest) -> str:
    if not request.query:
        return request.url
    return f"{request.url}?{urllib.parse.urlencode(sorted(request.query.items()))}"


def _require_http_success(response: KisHttpResponse, code: str) -> None:
    if response.status_code != 200:
        raise KisPaperReadOnlyError(code)


def _successful_payload(
    response: KisHttpResponse,
    code: str,
    *,
    endpoint: KisPaperReadOnlyEndpoint,
) -> Mapping[str, Any]:
    try:
        payload = response.payload()
    except KisPaperReadOnlyError as error:
        if response.status_code != 200:
            raise KisPaperReadOnlyError(
                code,
                diagnostic=_failure_diagnostic(response, endpoint),
            ) from error
        raise
    if response.status_code != 200 or payload.get("rt_cd") != "0":
        raise KisPaperReadOnlyError(
            code,
            diagnostic=_failure_diagnostic(response, endpoint),
        )
    return payload


def _failure_diagnostic(
    response: KisHttpResponse,
    endpoint: KisPaperReadOnlyEndpoint,
) -> dict[str, str]:
    """Persist only fixed request identity and safe response codes, never free text."""

    diagnostic = {
        "endpoint": endpoint.name,
        "tr_id": endpoint.tr_id,
        "http_status": str(response.status_code),
    }
    return diagnostic


def _validate_read_only_diagnostic(diagnostic: Mapping[str, str]) -> None:
    required = {"endpoint", "tr_id", "http_status"}
    if not required <= set(diagnostic):
        raise ValueError("read-only diagnostics must identify the failed request")
    endpoint_by_name = {endpoint.name: endpoint.tr_id for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS}
    endpoint_name = diagnostic["endpoint"]
    if endpoint_by_name.get(endpoint_name) != diagnostic["tr_id"]:
        raise ValueError("read-only diagnostics must use an allowlisted endpoint")
    status = diagnostic["http_status"]
    if not status.isdecimal() or not 100 <= int(status) <= 599:
        raise ValueError("read-only diagnostic status must be an HTTP status")
def _parse_balance_positions(
    payload: Mapping[str, Any],
    expected_exchange: str,
    captured_at: datetime,
) -> list[KisPaperPosition]:
    raw_rows = payload.get("output1")
    if isinstance(raw_rows, Mapping):
        rows = [raw_rows] if raw_rows else []
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        raise KisPaperReadOnlyError("balance_response_incomplete")
    positions: list[KisPaperPosition] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise KisPaperReadOnlyError("balance_response_incomplete")
        quantity = _response_decimal(row, "ovrs_cblc_qty", "balance_response_incomplete")
        if quantity == 0:
            continue
        if quantity < 0:
            raise KisPaperReadOnlyError("balance_response_incomplete")
        exchange = _response_text(row, "ovrs_excg_cd", "balance_response_incomplete").upper()
        if exchange != expected_exchange:
            raise KisPaperReadOnlyError("balance_response_incomplete")
        average_price = _response_decimal(row, "pchs_avg_pric", "balance_response_incomplete")
        market_price = _response_decimal(row, "now_pric2", "balance_response_incomplete")
        if average_price <= 0 or market_price <= 0:
            raise KisPaperReadOnlyError("balance_response_incomplete")
        positions.append(
            KisPaperPosition(
                symbol=_response_text(row, "ovrs_pdno", "balance_response_incomplete"),
                exchange=exchange,
                currency=_response_text(row, "tr_crcy_cd", "balance_response_incomplete"),
                quantity=quantity,
                average_price=average_price,
                market_price=market_price,
                captured_at=captured_at,
            )
        )
    return positions


def _ensure_unique_positions(positions: list[KisPaperPosition]) -> None:
    keys = [(position.exchange, position.symbol) for position in positions]
    if len(set(keys)) != len(keys):
        raise KisPaperReadOnlyError("balance_response_duplicate")


def _parse_open_orders(
    payload: Mapping[str, Any],
    captured_at: datetime,
) -> list[KisPaperOpenOrder]:
    raw_rows = payload.get("output")
    if isinstance(raw_rows, Mapping):
        rows = [raw_rows] if raw_rows else []
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        raise KisPaperReadOnlyError("open_orders_response_incomplete")
    orders: list[KisPaperOpenOrder] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        exchange = _response_text(row, "ovrs_excg_cd", "open_orders_response_incomplete").upper()
        if exchange not in KIS_PAPER_US_EXCHANGES:
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        requested_quantity = _response_decimal(
            row, "ft_ord_qty", "open_orders_response_incomplete"
        )
        filled_quantity = _response_decimal(
            row, "ft_ccld_qty", "open_orders_response_incomplete"
        )
        remaining_quantity = _response_decimal(
            row, "nccs_qty", "open_orders_response_incomplete"
        )
        if (
            requested_quantity <= 0
            or remaining_quantity <= 0
            or filled_quantity + remaining_quantity != requested_quantity
        ):
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        orders.append(
            KisPaperOpenOrder(
                order_reference=_redacted_order_reference(
                    _response_text(row, "odno", "open_orders_response_incomplete")
                ),
                symbol=_response_text(row, "pdno", "open_orders_response_incomplete"),
                exchange=exchange,
                currency=_response_text(row, "tr_crcy_cd", "open_orders_response_incomplete"),
                side=_open_order_side(row),
                requested_quantity=requested_quantity,
                filled_quantity=filled_quantity,
                remaining_quantity=remaining_quantity,
                limit_price=_optional_order_price(row),
                captured_at=captured_at,
            )
        )
    return orders


def _ensure_unique_open_orders(orders: list[KisPaperOpenOrder]) -> None:
    references = [order.order_reference for order in orders]
    if len(set(references)) != len(references):
        raise KisPaperReadOnlyError("open_orders_response_duplicate")


def _redacted_order_reference(raw_order_number: str) -> str:
    digest = hashlib.sha256(raw_order_number.encode("utf-8")).hexdigest()[:16]
    return f"open-{digest}"


def _open_order_side(payload: Mapping[str, Any]) -> Literal["buy", "sell"]:
    code = _response_text(payload, "sll_buy_dvsn_cd", "open_orders_response_incomplete")
    side_by_code: dict[str, Literal["buy", "sell"]] = {"01": "sell", "02": "buy"}
    try:
        return side_by_code[code]
    except KeyError as error:
        raise KisPaperReadOnlyError("open_orders_response_incomplete") from error


def _optional_order_price(payload: Mapping[str, Any]) -> Decimal | None:
    value = payload.get("ft_ord_unpr3")
    if not isinstance(value, str) or not value.strip():
        raise KisPaperReadOnlyError("open_orders_response_incomplete")
    try:
        price = Decimal(value.strip())
    except InvalidOperation as error:
        raise KisPaperReadOnlyError("open_orders_response_incomplete") from error
    if not price.is_finite() or price < 0:
        raise KisPaperReadOnlyError("open_orders_response_incomplete")
    return price if price > 0 else None


def _response_text(payload: Mapping[str, Any], field_name: str, code: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise KisPaperReadOnlyError(code)
    return value.strip()


def _response_decimal(payload: Mapping[str, Any], field_name: str, code: str) -> Decimal:
    value = payload.get(field_name)
    try:
        decimal = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError) as error:
        raise KisPaperReadOnlyError(code) from error
    if not decimal.is_finite() or decimal < 0:
        raise KisPaperReadOnlyError(code)
    return decimal


def _required_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("text value is required")
    return value.strip()


def _currency(value: str) -> str:
    currency = _required_text(value).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a three-letter code")
    return currency


def _non_negative_decimal(value: Decimal) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("decimal value is invalid") from error
    if not decimal.is_finite() or decimal < 0:
        raise ValueError("decimal value must be non-negative")
    return decimal


def _positive_decimal(value: Decimal) -> Decimal:
    decimal = _non_negative_decimal(value)
    if decimal <= 0:
        raise ValueError("decimal value must be positive")
    return decimal


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())

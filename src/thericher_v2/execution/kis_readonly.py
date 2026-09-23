"""Bounded KIS virtual-paper account discovery with no order actions.

This module is intentionally separate from the disabled broker lifecycle
boundary. It can collect a single, typed virtual-paper account view, including
open-order evidence, but it cannot create, change, or cancel an order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc

from .kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)

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
KIS_PAPER_SAME_DAY_ORDER_ID_MAX_PAGES = 2
DEFAULT_KIS_PAPER_REQUEST_INTERVAL_SECONDS = 1.0
_SAFE_KIS_PAPER_UPSTREAM_CODE = re.compile(r"[A-Z][A-Z0-9]{1,15}", re.ASCII)
_RAW_KIS_PAPER_ORDER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}", re.ASCII)
_KIS_PAPER_TERMINAL_FIELD_NAMES = frozenset(
    {
        "order_quantity",
        "filled_quantity",
        "remaining_quantity",
        "filled_price",
        "filled_amount",
        "processing_status",
        "revision_cancel_indicator",
        "order_time",
    }
)


class KisPaperReadOnlyError(RuntimeError):
    """A non-secret reason why a read-only discovery must fail closed."""

    def __init__(self, code: str, *, diagnostic: Mapping[str, str] | None = None) -> None:
        self.code = code
        self.diagnostic = dict(diagnostic or {})
        super().__init__(code)


@dataclass(frozen=True)
class KisPaperReadOnlyEndpoint:
    """One documented virtual-paper GET endpoint and its fixed query shape."""

    name: Literal["balance", "orderable_funds", "open_orders", "same_day_order_id"]
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
KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT = KisPaperReadOnlyEndpoint(
    name="same_day_order_id",
    path="/uapi/overseas-stock/v1/trading/inquire-ccnl",
    tr_id="VTTS3035R",
    query_keys=frozenset(
        {
            "CANO",
            "ACNT_PRDT_CD",
            "PDNO",
            "ORD_STRT_DT",
            "ORD_END_DT",
            "SLL_BUY_DVSN",
            "CCLD_NCCS_DVSN",
            "OVRS_EXCG_CD",
            "SORT_SQN",
            "ORD_DT",
            "ORD_GNO_BRNO",
            "ODNO",
            "CTX_AREA_NK200",
            "CTX_AREA_FK200",
        }
    ),
)
KIS_PAPER_READ_ONLY_ENDPOINTS = (
    KIS_PAPER_BALANCE_ENDPOINT,
    KIS_PAPER_ORDERABLE_FUNDS_ENDPOINT,
    KIS_PAPER_OPEN_ORDERS_ENDPOINT,
    KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
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


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep credential-bearing requests pinned to the virtual-paper host."""

    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        raise KisPaperReadOnlyError("redirect_rejected")


class KisPaperRequestPacer:
    """Space real KIS Paper requests without changing injected offline transports."""

    def __init__(
        self,
        *,
        minimum_request_interval_seconds: float = DEFAULT_KIS_PAPER_REQUEST_INTERVAL_SECONDS,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            isinstance(minimum_request_interval_seconds, bool)
            or not isinstance(minimum_request_interval_seconds, (int, float))
            or not math.isfinite(minimum_request_interval_seconds)
            or minimum_request_interval_seconds <= 0
        ):
            raise ValueError("minimum_request_interval_seconds must be positive")
        self._minimum_request_interval_seconds = float(minimum_request_interval_seconds)
        self._monotonic_clock = monotonic_clock
        self._sleeper = sleeper
        self._last_dispatch_at: float | None = None

    def wait_for_request_slot(self) -> None:
        if self._last_dispatch_at is None:
            self._last_dispatch_at = self._monotonic_clock()
            return
        next_dispatch_at = self._last_dispatch_at + self._minimum_request_interval_seconds
        current = self._monotonic_clock()
        while current < next_dispatch_at:
            self._sleeper(next_dispatch_at - current)
            current = self._monotonic_clock()
        self._last_dispatch_at = current


class UrllibKisHttpTransport:
    """Small standard-library transport guarded by the same request allowlist."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        minimum_request_interval_seconds: float = DEFAULT_KIS_PAPER_REQUEST_INTERVAL_SECONDS,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._pacer = KisPaperRequestPacer(
            minimum_request_interval_seconds=minimum_request_interval_seconds,
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
        )
        # Credential-bearing paper requests must not inherit host proxy settings.
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RejectRedirectHandler(),
        )

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        validate_kis_paper_readonly_request(request)
        self._pacer.wait_for_request_slot()
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
            with self._opener.open(http_request, timeout=self._timeout_seconds) as response:
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


@dataclass(frozen=True, repr=False)
class _KisPaperOpenOrderRecord:
    """One parsed open order with its raw ID kept inside the client process only."""

    raw_order_id: str
    order: KisPaperOpenOrder


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
class KisPaperSameDayOrderIdObservation:
    """One exact order-ID sighting in KIS's current-day history query.

    This is deliberately not a fill, cancellation, position, or PnL fact. The
    endpoint response is parsed only in memory and the raw order ID never
    becomes part of this typed result.
    """

    observed_at: datetime
    same_day_order_id_seen: bool
    row_count: int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if type(self.same_day_order_id_seen) is not bool:
            raise ValueError("same-day order observation flag is invalid")
        if type(self.row_count) is not int or self.row_count < 0:
            raise ValueError("same-day order observation count is invalid")


@dataclass(frozen=True)
class KisPaperTerminalFieldObservation:
    """Safe structural evidence from one completed Paper order-history query.

    This deliberately reports only whether the documented response fields were
    present and structurally usable for one in-memory order identity. The
    currently qualified KIS source does not define sufficient terminal enum,
    amendment, or PnL semantics, so this type cannot claim a fill, cancellation,
    or realized amount.
    """

    identity_match: Literal["exact_order", "original_order_lineage", "absent", "ambiguous"]
    field_states: Mapping[str, Literal["not_observed", "present", "missing_or_invalid"]]
    pagination_status: Literal["complete"] = "complete"
    terminal_state_support: Literal["unqualified"] = "unqualified"
    pnl_status: Literal["not_observed"] = "not_observed"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.identity_match not in {
            "exact_order",
            "original_order_lineage",
            "absent",
            "ambiguous",
        }:
            raise ValueError("terminal field identity match is invalid")
        if self.pagination_status != "complete":
            raise ValueError("terminal field pagination must be complete")
        if self.terminal_state_support != "unqualified" or self.pnl_status != "not_observed":
            raise ValueError("terminal field observation cannot promote lifecycle or pnl")
        normalized_states = dict(self.field_states)
        if set(normalized_states) != _KIS_PAPER_TERMINAL_FIELD_NAMES:
            raise ValueError("terminal field states must have the documented keys")
        if any(
            state not in {"not_observed", "present", "missing_or_invalid"}
            for state in normalized_states.values()
        ):
            raise ValueError("terminal field state is invalid")
        if self.identity_match in {"absent", "ambiguous"} and any(
            state != "not_observed" for state in normalized_states.values()
        ):
            raise ValueError("unmatched terminal rows cannot expose field support")
        object.__setattr__(self, "field_states", normalized_states)

    def safe_payload(self) -> dict[str, object]:
        return {
            "identity_match": self.identity_match,
            "pagination_status": self.pagination_status,
            "field_support": dict(self.field_states),
            "terminal_state_support": self.terminal_state_support,
            "pnl_status": self.pnl_status,
        }


@dataclass(frozen=True, repr=False)
class _KisPaperOrderHistoryRows:
    """Raw response rows held only while deriving safe history observations."""

    row_count: int
    direct_matches: tuple[Mapping[str, Any], ...]
    lineage_matches: tuple[Mapping[str, Any], ...]


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
    """Completeness facts for an account view collected by a read-only client."""

    reconciled_at: datetime
    account_snapshot_complete: Literal[True]
    scope: Literal["read_only"] = "read_only"
    reasons: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.account_snapshot_complete is not True or self.scope != "read_only":
            raise ValueError("read-only reconciliation scope is invalid")
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
            "upstream_code",
        }:
            raise ValueError("read-only diagnostics must be an allowlisted string mapping")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in self.diagnostic.items()
        ):
            raise ValueError("read-only diagnostics must be an allowlisted string mapping")
        if self.diagnostic:
            validate_kis_paper_readonly_diagnostic(self.diagnostic)
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
        payload["facts"] = {
            "cash_currency": self.snapshot.cash.currency,
            "orderable_funds_currency": self.snapshot.orderable_funds.currency,
            "position_count": len(self.snapshot.positions),
            "open_order_count": len(self.snapshot.open_orders.orders),
        }
        payload["reconciliation"] = {
            "account_snapshot_complete": self.reconciliation.account_snapshot_complete,
            "scope": self.reconciliation.scope,
            "reasons": list(self.reconciliation.reasons),
            "reconciled_at": self.reconciliation.reconciled_at.isoformat(),
        }
        return payload


class KisPaperReadOnlyClient:
    """Fetch one fixed virtual-paper discovery snapshot through an injected transport."""

    def __init__(
        self,
        *,
        config: KisPaperConfig,
        transport: KisHttpTransport,
        access_token: str | None = None,
    ) -> None:
        if access_token is not None and (not isinstance(access_token, str) or not access_token):
            raise KisPaperReadOnlyError("access_token_invalid")
        self._config = config
        self._transport = transport
        self._access_token = access_token
        self._latest_open_order_records: tuple[_KisPaperOpenOrderRecord, ...] | None = None

    def _dispatch(self, request: KisHttpRequest) -> KisHttpResponse:
        """Validate before every transport, including injected test transports."""

        validate_kis_paper_readonly_request(request)
        return self._transport.request(request)

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        access_token = self._access_token or self._issue_access_token()
        captured_at = datetime.now(UTC)
        open_orders = self._open_orders(access_token, captured_at)
        positions: dict[tuple[str, str], KisPaperPosition] = {}
        for exchange in KIS_PAPER_US_EXCHANGES:
            # A query may return other US venues; merge only completed query groups.
            for position in self._balance_positions(access_token, exchange, captured_at):
                key = (position.exchange, position.symbol)
                prior = positions.get(key)
                if prior is None:
                    positions[key] = position
                elif (prior.currency, prior.quantity, prior.average_price) != (
                    position.currency, position.quantity, position.average_price
                ):
                    raise KisPaperReadOnlyError("balance_response_duplicate")
                # Retain the first indicative mark; sequential queries are not atomic.
        cash, orderable_funds = self._cash_and_orderable_funds(access_token, captured_at)
        return KisPaperReadOnlySnapshot(
            identity=KisPaperAccountIdentity(self._config.masked_account_identity, captured_at),
            cash=cash,
            orderable_funds=orderable_funds,
            positions=tuple(positions[key] for key in sorted(positions)),
            open_orders=open_orders,
            captured_at=captured_at,
        )

    def observe_same_day_order_id(
        self,
        raw_order_id: str,
        *,
        as_of: datetime,
        order_at: datetime | None = None,
    ) -> KisPaperSameDayOrderIdObservation:
        """Check one raw ID on its recorded ET order day, or today by default.

        KIS's ``inquire-ccnl`` response may establish only that the exact order
        ID appeared in that query. It must not be treated as a fill, cancel, or
        realized-PnL claim by callers.
        """

        observed_at = require_utc(as_of, "as_of")
        history = self._read_same_day_order_history(
            raw_order_id,
            order_at=observed_at if order_at is None else require_utc(order_at, "order_at"),
        )
        return KisPaperSameDayOrderIdObservation(
            observed_at=observed_at,
            same_day_order_id_seen=bool(history.direct_matches),
            row_count=history.row_count,
        )

    def _find_unique_exact_open_order_id(
        self,
        *,
        symbol: str,
        exchange: str,
        side: Literal["buy", "sell"],
        quantity: Decimal,
        limit_price: Decimal,
    ) -> str | None:
        """Return one raw ID only when an exact open-order match is unique."""

        records = self._latest_open_order_records
        if records is None:
            access_token = self._access_token or self._issue_access_token()
            records = self._open_order_records(access_token, datetime.now(UTC))
        matches = [
            record.raw_order_id
            for record in records
            if (
                record.order.symbol == symbol
                and record.order.exchange == exchange
                and record.order.side == side
                and record.order.remaining_quantity == quantity
                and record.order.limit_price == limit_price
            )
        ]
        return matches[0] if len(matches) == 1 else None

    def observe_order_execution(
        self,
        raw_order_id: str,
        *,
        order_at: datetime,
        observed_at: datetime,
        symbol: str,
        exchange: str,
        side: Literal["buy", "sell"],
        quantity: Decimal,
    ) -> KisPaperExecutionObservation:
        """Bind one documented cumulative fill row; never sum amendment lineage.

        KIS's official overseas inquire_ccnl example names ft_ccld_qty and
        ft_ccld_amt3 as executed quantity/amount. No status-name inference or
        assumption that an absent open order was filled is made here.
        """
        history = self._read_same_day_order_history(raw_order_id, order_at=order_at)
        base = dict(
            row_count=history.row_count,
            same_day_order_id_seen=bool(history.direct_matches),
            observed_at=require_utc(observed_at),
        )
        if not history.direct_matches:
            return KisPaperExecutionObservation(**base, status="absent")
        if len(history.direct_matches) != 1:
            return KisPaperExecutionObservation(**base, status="ambiguous")
        row = history.direct_matches[0]
        order_date = (
            require_utc(order_at).astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
        )
        if (
            row.get("ord_dt") != order_date
            or row.get("pdno") != symbol
            or row.get("ovrs_excg_cd") != exchange
            or row.get("sll_buy_dvsn_cd") != {"buy": "02", "sell": "01"}.get(side)
            or row.get("tr_crcy_cd") != "USD"
        ):
            return KisPaperExecutionObservation(**base, status="identity_mismatch")
        try:
            requested = _response_decimal(row, "ft_ord_qty", "ccnl_response_incomplete")
            filled = _response_decimal(row, "ft_ccld_qty", "ccnl_response_incomplete")
            amount = _response_decimal(row, "ft_ccld_amt3", "ccnl_response_incomplete")
            price = _response_decimal(row, "ft_ccld_unpr3", "ccnl_response_incomplete")
            remaining = _response_decimal(row, "nccs_qty", "ccnl_response_incomplete")
            if (
                requested != quantity
                or remaining < 0
                or filled + remaining > requested
                or price < 0
                or (filled > 0 and price <= 0)
                or abs(amount - filled * price) > Decimal("0.01")
            ):
                raise ValueError("fill quantity mismatch")
            fill = KisPaperCumulativeFill(
                identity_ref=fill_identity_ref(
                    raw_order_id=raw_order_id,
                    order_at=order_at,
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    quantity=quantity,
                ),
                requested_quantity=requested,
                quantity=filled,
                gross_amount=amount,
                observed_at=observed_at,
                remaining_quantity=remaining,
            )
        except (KisPaperReadOnlyError, ValueError, InvalidOperation):
            return KisPaperExecutionObservation(**base, status="fields_invalid")
        return KisPaperExecutionObservation(**base, status="available", fill=fill)

    def inspect_order_history_terminal_fields(
        self,
        raw_order_id: str,
        *,
        order_at: datetime,
    ) -> KisPaperTerminalFieldObservation:
        """Inspect documented history-field presence without inferring a terminal state.

        ``inquire-ccnl`` cannot filter a virtual Paper request by order number.
        The returned pages are therefore completed before one raw order identity
        is compared in memory. The result never preserves an order identifier,
        values, status code, or broker timestamp.
        """

        history = self._read_same_day_order_history(raw_order_id, order_at=order_at)
        direct_matches = history.direct_matches
        direct_row_ids = {id(row) for row in direct_matches}
        lineage_matches = tuple(
            row for row in history.lineage_matches if id(row) not in direct_row_ids
        )
        matches: tuple[
            tuple[Literal["exact_order", "original_order_lineage"], Mapping[str, Any]], ...
        ] = tuple(("exact_order", row) for row in direct_matches) + tuple(
            ("original_order_lineage", row) for row in lineage_matches
        )
        if not matches:
            return KisPaperTerminalFieldObservation(
                identity_match="absent",
                field_states=_unobserved_terminal_field_states(),
            )
        if len(matches) != 1:
            return KisPaperTerminalFieldObservation(
                identity_match="ambiguous",
                field_states=_unobserved_terminal_field_states(),
            )
        identity_match, row = matches[0]
        return KisPaperTerminalFieldObservation(
            identity_match=identity_match,
            field_states=_terminal_field_states(row),
        )

    def _read_same_day_order_history(
        self,
        raw_order_id: str,
        *,
        order_at: datetime,
    ) -> _KisPaperOrderHistoryRows:
        """Read the fixed Paper history query and retain matched rows in memory only."""

        if (
            not isinstance(raw_order_id, str)
            or _RAW_KIS_PAPER_ORDER_ID.fullmatch(raw_order_id) is None
        ):
            raise KisPaperReadOnlyError("order_id_invalid")
        normalized_order_at = require_utc(order_at, "order_at")
        access_token = self._access_token or self._issue_access_token()
        eastern_date = normalized_order_at.astimezone(ZoneInfo("America/New_York")).strftime(
            "%Y%m%d"
        )
        query = {
            "CANO": self._config.account_number,
            "ACNT_PRDT_CD": self._config.account_product_code,
            "PDNO": "",
            "ORD_STRT_DT": eastern_date,
            "ORD_END_DT": eastern_date,
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "00",
            "OVRS_EXCG_CD": "",
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_NK200": "",
            "CTX_AREA_FK200": "",
        }
        continuation_header = ""
        row_count = 0
        direct_matches: list[Mapping[str, Any]] = []
        lineage_matches: list[Mapping[str, Any]] = []
        for _page in range(KIS_PAPER_SAME_DAY_ORDER_ID_MAX_PAGES):
            response = self._read_only_get(
                KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
                access_token=access_token,
                query=query,
                continuation_header=continuation_header,
            )
            payload = _successful_payload(
                response,
                "ccnl_rejected",
                endpoint=KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
            )
            output = payload.get("output")
            if not isinstance(output, Sequence) or isinstance(output, (str, bytes, bytearray)):
                raise KisPaperReadOnlyError("ccnl_response_incomplete")
            for row in output:
                if not isinstance(row, Mapping):
                    raise KisPaperReadOnlyError("ccnl_response_incomplete")
                candidate = row.get("odno")
                if (
                    not isinstance(candidate, str)
                    or _RAW_KIS_PAPER_ORDER_ID.fullmatch(candidate) is None
                ):
                    raise KisPaperReadOnlyError("ccnl_response_incomplete")
                row_count += 1
                if _history_order_id_matches(candidate, raw_order_id):
                    direct_matches.append(row)
                original_order_id = row.get("orgn_odno")
                if _history_order_id_matches(original_order_id, raw_order_id):
                    lineage_matches.append(row)
            continuation = response.header("tr_cont").strip().upper()
            if continuation not in {"M", "F"}:
                return _KisPaperOrderHistoryRows(
                    row_count=row_count,
                    direct_matches=tuple(direct_matches),
                    lineage_matches=tuple(lineage_matches),
                )
            query = {
                **query,
                "CTX_AREA_FK200": _response_text(
                    payload, "ctx_area_fk200", "ccnl_response_incomplete"
                ),
                "CTX_AREA_NK200": _response_text(
                    payload, "ctx_area_nk200", "ccnl_response_incomplete"
                ),
            }
            if not query["CTX_AREA_FK200"] or not query["CTX_AREA_NK200"]:
                raise KisPaperReadOnlyError("ccnl_response_incomplete")
            continuation_header = "N"
        raise KisPaperReadOnlyError("ccnl_pagination_incomplete")

    def _issue_access_token(self) -> str:
        response = self._dispatch(
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
        self._access_token = token
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
            positions.extend(_parse_balance_positions(payload, captured_at))
            continuation = response.header("tr_cont").strip().upper()
            if continuation not in {"M", "F"}:
                _ensure_unique_positions(positions)
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
        records = self._open_order_records(access_token, captured_at)
        self._latest_open_order_records = records
        return KisPaperOpenOrdersSnapshot(
            orders=tuple(
                sorted((record.order for record in records), key=lambda item: item.order_reference)
            ),
            captured_at=captured_at,
        )

    def _open_order_records(
        self,
        access_token: str,
        captured_at: datetime,
    ) -> tuple[_KisPaperOpenOrderRecord, ...]:
        records: list[_KisPaperOpenOrderRecord] = []
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
                records.extend(_parse_open_order_records(payload, captured_at))
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
        _ensure_unique_open_orders([record.order for record in records])
        return tuple(sorted(records, key=lambda item: item.order.order_reference))

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
        return self._dispatch(
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
    """Return typed account-completeness facts without deciding order readiness."""

    reasons: list[str] = []
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
        account_snapshot_complete=True,
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
                "scope": "read_only",
                "account_snapshot_complete": outcome.status == "collected",
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


def validate_kis_paper_readonly_request(request: KisHttpRequest) -> None:
    """Validate one fixed read-only virtual-paper request before transport."""

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
            or set(request.headers) != {"content-type", "accept"}
            or request.headers.get("content-type") != "application/json"
            or request.headers.get("accept") != "application/json"
            or not request.json_body.get("appkey")
            or not request.json_body.get("appsecret")
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
        or set(request.headers)
        != {"authorization", "appkey", "appsecret", "tr_id", "custtype", "tr_cont"}
        or request.headers.get("tr_id") != endpoint.tr_id
        or not request.headers.get("authorization", "").startswith("Bearer ")
        or not request.headers.get("authorization", "").removeprefix("Bearer ")
        or not request.headers.get("appkey")
        or not request.headers.get("appsecret")
        or request.headers.get("custtype") != "P"
        or request.headers.get("tr_cont") not in {"", "N"}
        or (
            endpoint is KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT
            and not _valid_same_day_order_id_query(request.query)
        )
    ):
        raise KisPaperReadOnlyError("request_not_allowlisted")


# Keep the private compatibility name while new clients import the public contract.
_validate_allowlisted_request = validate_kis_paper_readonly_request


def _history_order_id_matches(candidate: object, raw_order_id: str) -> bool:
    """Compare history IDs only; never normalize persisted or submitted identity."""

    if not isinstance(candidate, str) or _RAW_KIS_PAPER_ORDER_ID.fullmatch(candidate) is None:
        return False
    if candidate == raw_order_id:
        return True
    # The caller validates raw_order_id with the same bounded ASCII pattern.
    if not candidate.isdecimal() or not raw_order_id.isdecimal():
        return False
    positive_id = raw_order_id.lstrip("0")
    return bool(positive_id) and candidate.lstrip("0") == positive_id


def _valid_same_day_order_id_query(query: Mapping[str, str]) -> bool:
    """Keep the history lookup broad but fixed to one ET calendar day."""

    account_number = query.get("CANO")
    product_code = query.get("ACNT_PRDT_CD")
    start_date = query.get("ORD_STRT_DT")
    end_date = query.get("ORD_END_DT")
    return (
        isinstance(account_number, str)
        and len(account_number) == 8
        and account_number.isdigit()
        and isinstance(product_code, str)
        and len(product_code) == 2
        and product_code.isdigit()
        and isinstance(start_date, str)
        and len(start_date) == 8
        and start_date.isdigit()
        and end_date == start_date
        and query.get("PDNO") == ""
        and query.get("SLL_BUY_DVSN") == "00"
        and query.get("CCLD_NCCS_DVSN") == "00"
        and query.get("OVRS_EXCG_CD") == ""
        and query.get("SORT_SQN") == "DS"
        and all(query.get(key) == "" for key in ("ORD_DT", "ORD_GNO_BRNO", "ODNO"))
        and all(
            isinstance(query.get(key), str) and len(query[key]) <= 256
            for key in ("CTX_AREA_NK200", "CTX_AREA_FK200")
        )
    )


def _unobserved_terminal_field_states() -> dict[str, Literal["not_observed"]]:
    return {field_name: "not_observed" for field_name in _KIS_PAPER_TERMINAL_FIELD_NAMES}


def _terminal_field_states(
    row: Mapping[str, Any],
) -> dict[str, Literal["present", "missing_or_invalid"]]:
    """Classify field shape only; raw history values never leave this function."""

    return {
        "order_quantity": _terminal_decimal_field_state(row.get("ft_ord_qty"), positive=True),
        "filled_quantity": _terminal_decimal_field_state(row.get("ft_ccld_qty")),
        "remaining_quantity": _terminal_decimal_field_state(row.get("nccs_qty")),
        "filled_price": _terminal_decimal_field_state(row.get("ft_ccld_unpr3")),
        "filled_amount": _terminal_decimal_field_state(row.get("ft_ccld_amt3")),
        "processing_status": _terminal_text_field_state(row.get("prcs_stat_name")),
        "revision_cancel_indicator": _terminal_text_field_state(row.get("rvse_cncl_dvsn")),
        "order_time": _terminal_text_field_state(row.get("ord_tmd")),
    }


def _terminal_decimal_field_state(
    value: object,
    *,
    positive: bool = False,
) -> Literal["present", "missing_or_invalid"]:
    if not isinstance(value, str) or not value.strip():
        return "missing_or_invalid"
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError):
        return "missing_or_invalid"
    if not decimal_value.is_finite() or (decimal_value <= 0 if positive else decimal_value < 0):
        return "missing_or_invalid"
    return "present"


def _terminal_text_field_state(value: object) -> Literal["present", "missing_or_invalid"]:
    return "present" if isinstance(value, str) and value.strip() else "missing_or_invalid"


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
            diagnostic=_failure_diagnostic(response, endpoint, payload=payload),
        )
    return payload


def _failure_diagnostic(
    response: KisHttpResponse,
    endpoint: KisPaperReadOnlyEndpoint,
    *,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Persist only fixed request identity and safe response codes, never free text."""

    diagnostic = {
        "endpoint": endpoint.name,
        "tr_id": endpoint.tr_id,
        "http_status": str(response.status_code),
    }
    if payload is not None:
        upstream_code = safe_kis_paper_upstream_code(payload.get("msg_cd"))
        if upstream_code is not None:
            diagnostic["upstream_code"] = upstream_code
    return diagnostic


def validate_kis_paper_readonly_diagnostic(diagnostic: Mapping[str, str]) -> None:
    """Validate the minimal KIS Paper failure projection shared with the bridge."""

    required = {"endpoint", "tr_id", "http_status"}
    allowed = required | {"upstream_code"}
    if (
        not required <= set(diagnostic)
        or set(diagnostic) - allowed
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in diagnostic.items()
        )
    ):
        raise ValueError("read-only diagnostics must identify the failed request")
    endpoint_by_name = {endpoint.name: endpoint.tr_id for endpoint in KIS_PAPER_READ_ONLY_ENDPOINTS}
    endpoint_name = diagnostic["endpoint"]
    if endpoint_by_name.get(endpoint_name) != diagnostic["tr_id"]:
        raise ValueError("read-only diagnostics must use an allowlisted endpoint")
    status = diagnostic["http_status"]
    if not status.isdecimal() or not 100 <= int(status) <= 599:
        raise ValueError("read-only diagnostic status must be an HTTP status")
    if "upstream_code" in diagnostic and (
        safe_kis_paper_upstream_code(diagnostic["upstream_code"]) != diagnostic["upstream_code"]
    ):
        raise ValueError("read-only diagnostic upstream code is not allowlisted")


def safe_kis_paper_upstream_code(value: object) -> str | None:
    """Keep only a short KIS-style code; never normalize arbitrary response text."""

    if (
        not isinstance(value, str)
        or _SAFE_KIS_PAPER_UPSTREAM_CODE.fullmatch(value) is None
        or not any("0" <= character <= "9" for character in value)
    ):
        return None
    return value


def _parse_balance_positions(
    payload: Mapping[str, Any],
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
        if exchange not in KIS_PAPER_US_EXCHANGES:
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
    return [record.order for record in _parse_open_order_records(payload, captured_at)]


def _parse_open_order_records(
    payload: Mapping[str, Any],
    captured_at: datetime,
) -> list[_KisPaperOpenOrderRecord]:
    raw_rows = payload.get("output")
    if isinstance(raw_rows, Mapping):
        rows = [raw_rows] if raw_rows else []
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        raise KisPaperReadOnlyError("open_orders_response_incomplete")
    records: list[_KisPaperOpenOrderRecord] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        exchange = _response_text(row, "ovrs_excg_cd", "open_orders_response_incomplete").upper()
        if exchange not in KIS_PAPER_US_EXCHANGES:
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        requested_quantity = _response_decimal(row, "ft_ord_qty", "open_orders_response_incomplete")
        filled_quantity = _response_decimal(row, "ft_ccld_qty", "open_orders_response_incomplete")
        remaining_quantity = _response_decimal(row, "nccs_qty", "open_orders_response_incomplete")
        if (
            requested_quantity <= 0
            or remaining_quantity <= 0
            or filled_quantity + remaining_quantity != requested_quantity
        ):
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        raw_order_id = _response_text(row, "odno", "open_orders_response_incomplete")
        if _RAW_KIS_PAPER_ORDER_ID.fullmatch(raw_order_id) is None:
            raise KisPaperReadOnlyError("open_orders_response_incomplete")
        records.append(
            _KisPaperOpenOrderRecord(
                raw_order_id=raw_order_id,
                order=KisPaperOpenOrder(
                    order_reference=_redacted_order_reference(raw_order_id),
                    symbol=_response_text(row, "pdno", "open_orders_response_incomplete"),
                    exchange=exchange,
                    currency=_response_text(row, "tr_crcy_cd", "open_orders_response_incomplete"),
                    side=_open_order_side(row),
                    requested_quantity=requested_quantity,
                    filled_quantity=filled_quantity,
                    remaining_quantity=remaining_quantity,
                    limit_price=_optional_order_price(row),
                    captured_at=captured_at,
                ),
            )
        )
    return records


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

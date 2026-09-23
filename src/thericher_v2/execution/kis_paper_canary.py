"""Narrow, virtual-paper-only US buy-limit canary with durable recovery state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.research.kis_paper_canary_intent import (
    KisPaperCanaryBuyDecision,
    KisPaperCanaryOrderDecision,
    KisPaperCanarySellDecision,
)

from .broker import BrokerOrderRequest
from .emergency import (
    DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    EmergencyStore,
    PaperExecutionControlStore,
)
from .kis_paper_console_bridge import paper_account_snapshot_from_kis_readonly
from .kis_paper_fill_accounting import (
    KisPaperCumulativeFill,
    KisPaperExecutionObservation,
    fill_identity_ref,
)
from .kis_paper_order_fields import (
    map_kis_paper_us_buy_limit_order_fields,
    map_kis_paper_us_sell_limit_order_fields,
)
from .kis_paper_quote import (
    KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE,
    KIS_PAPER_US_QQQ_QUOTE_SYMBOL,
    KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
    KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
    KIS_PAPER_US_SPY_QUOTE_PATH,
    KisPaperQqqAskingPriceProbe,
    KisPaperQqqLimitInput,
    KisPaperQqqPriceDetailProbe,
    KisPaperQqqQuote,
    KisPaperQuoteError,
    KisPaperSpyAskingPriceProbe,
    KisPaperSpyLimitInput,
    KisPaperSpyPriceDetailProbe,
    KisPaperSpyQuote,
    build_kis_paper_qqq_asking_price_request,
    build_kis_paper_qqq_price_detail_request,
    build_kis_paper_qqq_quote_request,
    build_kis_paper_spy_asking_price_request,
    build_kis_paper_spy_price_detail_request,
    build_kis_paper_spy_quote_request,
    inspect_kis_paper_qqq_asking_price_response,
    inspect_kis_paper_qqq_price_detail_response,
    inspect_kis_paper_spy_asking_price_response,
    inspect_kis_paper_spy_price_detail_response,
    parse_kis_paper_qqq_limit_input,
    parse_kis_paper_qqq_quote,
    parse_kis_paper_spy_limit_input,
    parse_kis_paper_spy_quote,
    validate_kis_paper_qqq_asking_price_request,
    validate_kis_paper_qqq_price_detail_request,
    validate_kis_paper_qqq_quote_request,
    validate_kis_paper_spy_asking_price_request,
    validate_kis_paper_spy_price_detail_request,
    validate_kis_paper_spy_quote_request,
)
from .kis_readonly import (
    KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT,
    KIS_PAPER_SAME_DAY_ORDER_ID_MAX_PAGES,
    KIS_PAPER_TOKEN_PATH,
    KisHttpRequest,
    KisHttpResponse,
    KisHttpTransport,
    KisPaperConfig,
    KisPaperReadOnlyClient,
    KisPaperReadOnlyError,
    KisPaperReadOnlySnapshot,
    KisPaperRequestPacer,
    load_kis_paper_config_from_environment,
    safe_kis_paper_upstream_code,
    validate_kis_paper_readonly_request,
)
from .paper_account_snapshot import write_paper_account_snapshot
from .paper_canary_runtime import (
    PAPER_CANARY_RUNTIME_TTL,
    PAPER_CANARY_SAFE_RECONCILIATION_REASON_CODES,
    PaperCanaryRuntimeSnapshot,
    redact_paper_canary_order_reference,
    write_paper_canary_runtime,
)

DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT = Path(r"D:\thericher-v2\model-artifacts")
DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION = Path("runtime/state/kis_paper_canary.json")
DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT = Path("runtime/state/paper_account_snapshot.json")
DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE = Path("runtime/emergency_state.json")
DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL = DEFAULT_PAPER_EXECUTION_CONTROL_STATE
DEFAULT_KIS_PAPER_CANARY_STATE_ROOT = Path("runtime/private/kis_paper_canary")

KIS_PAPER_US_BUY_LIMIT_ORDER_PATH = "/uapi/overseas-stock/v1/trading/order"
KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID = "VTTT1002U"
KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID = "VTTT1001U"
KIS_PAPER_US_CANCEL_PATH = "/uapi/overseas-stock/v1/trading/order-rvsecncl"
KIS_PAPER_US_CANCEL_TR_ID = "VTTT1004U"
# Backward-compatible names for the now shared read-only history endpoint.
KIS_PAPER_US_CCNCL_PATH = KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.path
KIS_PAPER_US_CCNCL_TR_ID = KIS_PAPER_SAME_DAY_ORDER_ID_ENDPOINT.tr_id
KIS_PAPER_US_CCNCL_MAX_PAGES = KIS_PAPER_SAME_DAY_ORDER_ID_MAX_PAGES
KIS_PAPER_RATE_LIMIT_CODE = "EGW00201"

_RECEIPT_DECISION_ID = re.compile(r"receipt-([0-9a-f]{64})")
_SHA256_REFERENCE = re.compile(r"sha256:[0-9a-f]{64}")

_PAPER_POST_HEADERS = frozenset(
    {"authorization", "appkey", "appsecret", "tr_id", "custtype", "content-type", "accept"}
)
_PAPER_GET_HEADERS = frozenset(
    {"authorization", "appkey", "appsecret", "tr_id", "custtype", "tr_cont"}
)
_BUY_LIMIT_BODY_KEYS = frozenset(
    {
        "CANO",
        "ACNT_PRDT_CD",
        "OVRS_EXCG_CD",
        "PDNO",
        "ORD_QTY",
        "OVRS_ORD_UNPR",
        "CTAC_TLNO",
        "MGCO_APTM_ODNO",
        "SLL_TYPE",
        "ORD_SVR_DVSN_CD",
        "ORD_DVSN",
    }
)
_CANCEL_BODY_KEYS = frozenset(
    {
        "CANO",
        "ACNT_PRDT_CD",
        "OVRS_EXCG_CD",
        "PDNO",
        "ORGN_ODNO",
        "RVSE_CNCL_DVSN_CD",
        "ORD_QTY",
        "OVRS_ORD_UNPR",
        "MGCO_APTM_ODNO",
        "ORD_SVR_DVSN_CD",
    }
)
_STATE_PHASES = frozenset(
    {
        "intent_recorded",
        "submission_started",
        "submitted",
        "rejected",
        "outcome_unknown",
        "cancel_started",
        "cancelled",
    }
)
_READ_ONLY_RECOVERY_PHASES = frozenset({"submission_started", "outcome_unknown", "cancel_started"})
_PENDING_RECOVERY_PHASES = frozenset(
    {"submission_started", "submitted", "outcome_unknown", "cancel_started"}
)
_SAFE_SUBMIT_RESPONSE_CATEGORIES = frozenset(
    {
        "acknowledged_order_reference",
        "http_non_200",
        "legacy_response_incomplete",
        "not_observed",
        "payload_invalid",
        "provider_rejected",
        "success_order_reference_missing",
        "success_output_missing",
        "transport_unavailable",
    }
)
_IDLESS_RECOVERABLE_SUBMIT_CATEGORIES = frozenset(
    {"success_order_reference_missing", "success_output_missing"}
)
_SAFE_REASON_CODES = frozenset(
    {
        "preview",
        "intent_expired",
        "emergency_stop_new_orders",
        "pause_buys_active",
        "pause_sells_active",
        "matching_open_order",
        "owned_intent_conflict",
        "submit_rejected",
        "submit_http_4xx",
        "submit_http_5xx",
        "submit_kis_rejected",
        "submit_rate_limited",
        "submit_transport_unknown",
        "submit_response_incomplete",
        "quote_rejected",
        "quote_response_blank",
        "quote_response_incomplete",
        "session_closed",
        "cancel_rejected",
        "cancel_transport_unknown",
        "cancel_response_incomplete",
        "reconciliation_unavailable",
        "reconciliation_unresolved",
        "reconciliation_clean",
    }
)


class KisPaperCanaryError(RuntimeError):
    """A non-secret failure reason for the bounded virtual-paper canary."""

    def __init__(
        self,
        code: str,
        *,
        upstream_code: str | None = None,
        submit_response_category: str | None = None,
    ) -> None:
        self.code = code
        self.upstream_code = upstream_code
        self.submit_response_category = submit_response_category
        if (
            upstream_code is not None
            and safe_kis_paper_upstream_code(upstream_code) != upstream_code
        ):
            raise ValueError("canary upstream code is invalid")
        if (
            submit_response_category is not None
            and submit_response_category not in _SAFE_SUBMIT_RESPONSE_CATEGORIES
        ):
            raise ValueError("canary submit response category is invalid")
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class KisPaperSubmitResponseProbe:
    """Category-only view of one virtual buy-limit response."""

    http_status_class: Literal["1xx", "2xx", "3xx", "4xx", "5xx", "other"]
    category: str
    upstream_code_state: Literal["not_checked", "valid", "absent_or_invalid"]

    def __post_init__(self) -> None:
        if self.category not in _SAFE_SUBMIT_RESPONSE_CATEGORIES:
            raise ValueError("submit response category is invalid")

    def safe_payload(self) -> dict[str, str | bool]:
        return {
            "http_status_class": self.http_status_class,
            "category": self.category,
            "upstream_code_state": self.upstream_code_state,
            "paper_only": True,
        }


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        raise KisPaperCanaryError("redirect_rejected")


class UrllibKisPaperCanaryTransport:
    """Direct-only virtual-paper transport for the canary request allowlist."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        pacer: KisPaperRequestPacer | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._pacer = pacer or KisPaperRequestPacer()
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RejectRedirectHandler(),
        )

    def request(self, request: KisHttpRequest) -> KisHttpResponse:
        return self._request(request)

    def request_before_deadline(
        self,
        request: KisHttpRequest,
        *,
        deadline: datetime,
        clock: Callable[[], datetime],
    ) -> KisHttpResponse:
        """Pace and build the request, then recheck immediately before ``open``.

        This prevents an already expired intent from beginning I/O; it does not
        bound scheduling, TLS, socket, or remote-processing latency after ``open``.
        """

        valid_until = require_utc(deadline, "deadline")

        def ensure_current() -> None:
            if require_utc(clock(), "clock") >= valid_until:
                raise KisPaperCanaryError("intent_expired")

        return self._request(request, before_wire=ensure_current)

    def _request(
        self,
        request: KisHttpRequest,
        *,
        before_wire: Callable[[], None] | None = None,
    ) -> KisHttpResponse:
        validate_kis_paper_canary_request(request)
        self._pacer.wait_for_request_slot()
        data = (
            json.dumps(request.json_body, separators=(",", ":")).encode("utf-8")
            if request.json_body is not None
            else None
        )
        url = _request_url_with_query(request)
        http_request = urllib.request.Request(
            url,
            data=data,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            if before_wire is not None:
                before_wire()
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
            raise KisPaperCanaryError("transport_failure") from error


@dataclass(frozen=True)
class KisPaperCanaryIntent:
    """The durable execution-owned projection of a research-side canary decision."""

    run_id: str
    client_order_id: str
    decision_id: str
    symbol: str
    exchange: str
    quantity: Decimal
    limit_price: Decimal
    created_at: datetime
    valid_until: datetime
    side: Literal["buy", "sell"] = "buy"
    price_contract_ref: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        identifiers = (
            (self.run_id, "run_id"),
            (self.client_order_id, "client_order_id"),
            (self.decision_id, "decision_id"),
        )
        for value, label in identifiers:
            _safe_identifier(value, label)
        if self.exchange not in {"NASD", "NYSE", "AMEX"}:
            raise ValueError("canary exchange is invalid")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("canary symbol is invalid")
        if self.side not in {"buy", "sell"}:
            raise ValueError("canary side is invalid")
        if self.quantity <= 0 or self.quantity != self.quantity.to_integral_value():
            raise ValueError("canary quantity must be whole shares")
        if self.limit_price <= 0:
            raise ValueError("canary limit price must be positive")
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until <= self.created_at:
            raise ValueError("canary validity is invalid")
        if (
            self.price_contract_ref is not None
            and _SHA256_REFERENCE.fullmatch(self.price_contract_ref) is None
        ):
            raise ValueError("canary price contract reference is invalid")

    @property
    def fingerprint(self) -> str:
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )

    def to_dict(self) -> dict[str, str]:
        payload = {
            "run_id": self.run_id,
            "client_order_id": self.client_order_id,
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "quantity": str(self.quantity),
            "limit_price": str(self.limit_price),
            "created_at": self.created_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
        }
        if self.price_contract_ref is not None:
            payload["price_contract_ref"] = self.price_contract_ref
        # Keep pre-existing buy-only private state fingerprints replayable.
        if self.side == "sell":
            payload["side"] = self.side
        return payload

    @classmethod
    def from_decision(
        cls,
        decision: KisPaperCanaryOrderDecision,
        *,
        run_id: str,
        price_contract_ref: str | None = None,
    ) -> KisPaperCanaryIntent:
        _safe_identifier(run_id, "run_id")
        return cls(
            run_id=run_id,
            client_order_id=f"canary-{run_id}",
            decision_id=decision.decision_id,
            symbol=decision.symbol,
            exchange=decision.exchange,
            quantity=decision.quantity,
            limit_price=decision.limit_price,
            created_at=decision.decision_as_of,
            valid_until=decision.valid_until,
            side=decision.side,
            price_contract_ref=price_contract_ref,
        )

    def broker_request(self) -> BrokerOrderRequest:
        return BrokerOrderRequest(
            client_order_id=self.client_order_id,
            symbol=self.symbol,
            market="US",
            side=self.side,
            quantity=self.quantity,
            limit_price=self.limit_price,
            decision_id=self.decision_id,
            created_at=self.created_at,
        )


@dataclass(frozen=True, repr=False)
class KisPaperCanaryState:
    intent: KisPaperCanaryIntent
    phase: str
    updated_at: datetime
    reason_code: str
    broker_order_id: str | None = None
    submitted_at: datetime | None = None
    submission_started_at: datetime | None = None
    cancel_after_submit: bool = False
    submit_upstream_code: str | None = None
    submit_response_category: str | None = None
    schema_version: int = SCHEMA_VERSION
    cumulative_fill: KisPaperCumulativeFill | None = None
    fill_observation_status: str = "not_observed"
    fill_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.phase not in _STATE_PHASES:
            raise ValueError("canary state phase is invalid")
        if self.reason_code not in _SAFE_REASON_CODES:
            raise ValueError("canary state reason is invalid")
        if self.broker_order_id is not None and not _raw_order_id(self.broker_order_id):
            raise ValueError("canary broker order id is invalid")
        if self.submission_started_at is not None:
            started_at = require_utc(self.submission_started_at, "submission_started_at")
            if (
                not self.intent.created_at
                <= started_at
                <= require_utc(self.updated_at, "updated_at")
            ):
                raise ValueError("canary submission start is outside state lifetime")
            object.__setattr__(self, "submission_started_at", started_at)
        if self.submitted_at is not None:
            if self.broker_order_id is None:
                raise ValueError("canary submitted time requires broker order id")
            submitted_at = require_utc(self.submitted_at, "submitted_at")
            if submitted_at < self.intent.created_at:
                raise ValueError("canary submitted time precedes intent")
            if (
                self.submission_started_at is not None
                and submitted_at != self.submission_started_at
            ):
                raise ValueError("canary submitted time differs from recorded attempt")
            object.__setattr__(self, "submitted_at", submitted_at)
        if not isinstance(self.cancel_after_submit, bool):
            raise ValueError("canary cancellation policy is invalid")
        if (
            self.submit_upstream_code is not None
            and safe_kis_paper_upstream_code(self.submit_upstream_code) != self.submit_upstream_code
        ):
            raise ValueError("canary submit upstream code is invalid")
        if (
            self.submit_response_category is not None
            and self.submit_response_category not in _SAFE_SUBMIT_RESPONSE_CATEGORIES
        ):
            raise ValueError("canary submit response category is invalid")
        object.__setattr__(self, "updated_at", require_utc(self.updated_at, "updated_at"))
        if self.fill_observation_status not in {
            "not_observed",
            "available",
            "absent",
            "ambiguous",
            "identity_mismatch",
            "fields_invalid",
            "conflict",
            "unavailable",
        }:
            raise ValueError("fill observation status invalid")
        if (self.fill_observation_status == "not_observed") != (self.fill_observed_at is None):
            raise ValueError("fill observation time missing")
        if self.fill_observed_at is not None:
            require_utc(self.fill_observed_at)
            if self.fill_observed_at > self.updated_at:
                raise ValueError("fill observation time invalid")
        if self.cumulative_fill is not None:
            order_at = self.submission_started_at or self.submitted_at
            if (
                self.broker_order_id is None
                or order_at is None
                or (
                    self.cumulative_fill.identity_ref
                    != fill_identity_ref(
                        raw_order_id=self.broker_order_id,
                        order_at=order_at,
                        symbol=self.intent.symbol,
                        exchange=self.intent.exchange,
                        side=self.intent.side,
                        quantity=self.intent.quantity,
                    )
                    or self.cumulative_fill.requested_quantity != self.intent.quantity
                    or self.fill_observed_at is None
                    or not order_at <= self.cumulative_fill.observed_at <= self.fill_observed_at
                )
            ):
                raise ValueError("fill observation binding invalid")
        if self.fill_observation_status == "available" and (
            self.cumulative_fill is None
            or self.cumulative_fill.observed_at != self.fill_observed_at
        ):
            raise ValueError("current fill missing")

    @property
    def current_fill(self) -> KisPaperCumulativeFill | None:
        return self.cumulative_fill if self.fill_observation_status == "available" else None

    @property
    def gross_cashflow_contribution(self) -> Decimal | None:
        """Own order's gross flow only, never account cash, settlement, or net PnL."""
        fill = self.current_fill
        if fill is None:
            return None
        return fill.gross_amount * (1 if self.intent.side == "sell" else -1)

    @property
    def position_contribution(self) -> Decimal | None:
        fill = self.current_fill
        if fill is None:
            return None
        return fill.quantity * (1 if self.intent.side == "buy" else -1)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_canary_state",
            "intent": self.intent.to_dict(),
            "intent_fingerprint": self.intent.fingerprint,
            "phase": self.phase,
            "updated_at": self.updated_at.isoformat(),
            "reason_code": self.reason_code,
            "broker_order_id": self.broker_order_id,
            "submitted_at": (None if self.submitted_at is None else self.submitted_at.isoformat()),
            "submission_started_at": (
                None
                if self.submission_started_at is None
                else self.submission_started_at.isoformat()
            ),
            "cancel_after_submit": self.cancel_after_submit,
            "submit_upstream_code": self.submit_upstream_code,
            "submit_response_category": self.submit_response_category,
            "cumulative_fill": None
            if self.cumulative_fill is None
            else self.cumulative_fill.to_dict(),
            "fill_observation_status": self.fill_observation_status,
            "fill_observed_at": None
            if self.fill_observed_at is None
            else self.fill_observed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> KisPaperCanaryState:
        expected = {
            "schema_version",
            "kind",
            "intent",
            "intent_fingerprint",
            "phase",
            "updated_at",
            "reason_code",
            "broker_order_id",
        }
        optional = {
            "submitted_at",
            "submission_started_at",
            "cancel_after_submit",
            "submit_upstream_code",
            "submit_response_category",
            "cumulative_fill",
            "fill_observation_status",
            "fill_observed_at",
        }
        if not isinstance(payload, Mapping) or not expected <= set(payload) <= expected | optional:
            raise KisPaperCanaryError("state_invalid")
        if (
            payload["schema_version"] != SCHEMA_VERSION
            or payload["kind"] != "kis_paper_canary_state"
        ):
            raise KisPaperCanaryError("state_invalid")
        raw_intent = payload["intent"]
        if not isinstance(raw_intent, Mapping):
            raise KisPaperCanaryError("state_invalid")
        try:
            intent = KisPaperCanaryIntent(
                run_id=_required_text(raw_intent.get("run_id")),
                client_order_id=_required_text(raw_intent.get("client_order_id")),
                decision_id=_required_text(raw_intent.get("decision_id")),
                symbol=_required_text(raw_intent.get("symbol")),
                exchange=_required_text(raw_intent.get("exchange")),
                quantity=_positive_decimal(raw_intent.get("quantity")),
                limit_price=_positive_decimal(raw_intent.get("limit_price")),
                created_at=_utc_datetime(raw_intent.get("created_at")),
                valid_until=_utc_datetime(raw_intent.get("valid_until")),
                side=("buy" if "side" not in raw_intent else _required_text(raw_intent["side"])),
                price_contract_ref=(
                    None
                    if "price_contract_ref" not in raw_intent
                    or raw_intent["price_contract_ref"] is None
                    else _required_sha256_reference(raw_intent["price_contract_ref"])
                ),
            )
            if payload["intent_fingerprint"] != intent.fingerprint:
                raise ValueError("fingerprint")
            return cls(
                intent=intent,
                cumulative_fill=(
                    None
                    if payload.get("cumulative_fill") is None
                    else KisPaperCumulativeFill.from_dict(payload["cumulative_fill"])
                ),
                fill_observation_status=payload.get("fill_observation_status", "not_observed"),
                fill_observed_at=(
                    None
                    if payload.get("fill_observed_at") is None
                    else _utc_datetime(payload["fill_observed_at"])
                ),
                phase=_required_text(payload["phase"]),
                updated_at=_utc_datetime(payload["updated_at"]),
                reason_code=_required_text(payload["reason_code"]),
                broker_order_id=(
                    None
                    if payload["broker_order_id"] is None
                    else _required_text(payload["broker_order_id"])
                ),
                submitted_at=(
                    None
                    if "submitted_at" not in payload or payload["submitted_at"] is None
                    else _utc_datetime(payload["submitted_at"])
                ),
                submission_started_at=(
                    None
                    if payload.get("submission_started_at") is None
                    else _utc_datetime(payload["submission_started_at"])
                ),
                cancel_after_submit=(
                    False
                    if "cancel_after_submit" not in payload
                    else _required_bool(payload["cancel_after_submit"])
                ),
                submit_upstream_code=(
                    None
                    if "submit_upstream_code" not in payload
                    or payload["submit_upstream_code"] is None
                    else _required_text(payload["submit_upstream_code"])
                ),
                submit_response_category=(
                    None
                    if "submit_response_category" not in payload
                    or payload["submit_response_category"] is None
                    else _required_text(payload["submit_response_category"])
                ),
            )
        except (InvalidOperation, TypeError, ValueError) as error:
            raise KisPaperCanaryError("state_invalid") from error


@dataclass(frozen=True, repr=False)
class KisPaperCanaryReconciliation:
    snapshot: KisPaperReadOnlySnapshot | None
    account_status: Literal["available", "unavailable"]
    ccnl_row_count: int
    matching_open_order: bool
    matching_ccnl: bool
    status: Literal["clean", "unresolved"]
    reason_code: str | None = None
    recovered_broker_order_id: str | None = field(default=None, repr=False)
    execution: KisPaperExecutionObservation | None = field(default=None, repr=False)

    @property
    def position_count(self) -> int:
        return 0 if self.snapshot is None else len(self.snapshot.positions)

    @property
    def open_order_count(self) -> int:
        return 0 if self.snapshot is None else len(self.snapshot.open_orders.orders)


@dataclass(frozen=True)
class KisPaperCanaryOutcome:
    run_id: str
    phase: str
    reason_code: str
    evidence_path: Path
    runtime_path: Path
    paper_account_snapshot_path: Path
    reconciliation: KisPaperCanaryReconciliation
    submit_upstream_code: str | None = None
    submit_response_category: str | None = None
    schema_version: int = SCHEMA_VERSION

    def safe_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "reason_code": self.reason_code,
            "submit_upstream_code": self.submit_upstream_code,
            "submit_response_category": self.submit_response_category,
            "paper_only": True,
            "reconciliation_status": self.reconciliation.status,
            "reconciliation_reason_code": self.reconciliation.reason_code,
            "account_status": self.reconciliation.account_status,
            "position_count": self.reconciliation.position_count,
            "open_order_count": self.reconciliation.open_order_count,
        }


class KisPaperCanaryStateStore:
    """One atomic state file per canary run; it is never a Git artifact."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> KisPaperCanaryState | None:
        with exclusive_kis_paper_canary_state_lock(self.path):
            return self._read_unlocked()

    def record_intent(
        self,
        intent: KisPaperCanaryIntent,
        *,
        cancel_after_submit: bool,
        now: datetime,
    ) -> KisPaperCanaryState:
        with exclusive_kis_paper_canary_state_lock(self.path):
            current = self._read_unlocked()
            if current is not None:
                if current.intent != intent:
                    raise KisPaperCanaryError("state_intent_mismatch")
                return current
            state = KisPaperCanaryState(
                intent=intent,
                phase="intent_recorded",
                updated_at=now,
                reason_code="preview",
                cancel_after_submit=cancel_after_submit,
            )
            self._write_unlocked(state)
            return state

    def record_fill_observation(
        self,
        intent: KisPaperCanaryIntent,
        observation: KisPaperExecutionObservation,
        *,
        now: datetime,
    ) -> KisPaperCanaryState:
        with exclusive_kis_paper_canary_state_lock(self.path):
            current = self._read_unlocked()
            if current is None or current.intent != intent:
                raise KisPaperCanaryError("state_intent_mismatch")
            cumulative = current.cumulative_fill
            status = observation.status
            try:
                if observation.fill is not None:
                    cumulative = observation.fill.advance(cumulative)
                state = replace(
                    current,
                    cumulative_fill=cumulative,
                    fill_observation_status=status,
                    fill_observed_at=now,
                    updated_at=max(current.updated_at, now),
                )
            except ValueError:
                # Preserve accepted totals but make stale/conflicting reads explicit.
                state = replace(
                    current,
                    fill_observation_status="conflict",
                    fill_observed_at=max(current.fill_observed_at or now, now),
                    updated_at=max(current.updated_at, now),
                )
            self._write_unlocked(state)
            return state

    def transition(
        self,
        intent: KisPaperCanaryIntent,
        *,
        expected: frozenset[str],
        phase: str,
        reason_code: str,
        now: datetime,
        broker_order_id: str | None = None,
        submitted_at: datetime | None = None,
        submission_started_at: datetime | None = None,
        submit_upstream_code: str | None = None,
        submit_response_category: str | None = None,
    ) -> KisPaperCanaryState:
        with exclusive_kis_paper_canary_state_lock(self.path):
            current = self._read_unlocked()
            if current is None or current.intent != intent or current.phase not in expected:
                raise KisPaperCanaryError("state_transition_invalid")
            if (
                current.submitted_at is not None
                and submitted_at is not None
                and submitted_at != current.submitted_at
            ):
                raise KisPaperCanaryError("state_submission_time_invalid")
            if submission_started_at is not None and (
                (
                    current.submission_started_at is not None
                    and submission_started_at != current.submission_started_at
                )
                or (
                    current.submission_started_at is None
                    and (current.phase != "intent_recorded" or phase != "submission_started")
                )
            ):
                raise KisPaperCanaryError("state_submission_time_invalid")
            state = KisPaperCanaryState(
                intent=intent,
                phase=phase,
                updated_at=now,
                reason_code=reason_code,
                cumulative_fill=current.cumulative_fill,
                fill_observation_status=current.fill_observation_status,
                fill_observed_at=current.fill_observed_at,
                broker_order_id=(
                    current.broker_order_id if broker_order_id is None else broker_order_id
                ),
                submitted_at=(current.submitted_at if submitted_at is None else submitted_at),
                submission_started_at=(
                    current.submission_started_at
                    if submission_started_at is None
                    else submission_started_at
                ),
                cancel_after_submit=current.cancel_after_submit,
                submit_upstream_code=(
                    current.submit_upstream_code
                    if submit_upstream_code is None
                    else submit_upstream_code
                ),
                submit_response_category=(
                    current.submit_response_category
                    if submit_response_category is None
                    else submit_response_category
                ),
            )
            self._write_unlocked(state)
            return state

    def _read_unlocked(self) -> KisPaperCanaryState | None:
        try:
            return KisPaperCanaryState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise KisPaperCanaryError("state_invalid") from error

    def _write_unlocked(self, state: KisPaperCanaryState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(json.dumps(state.to_dict(), sort_keys=True, separators=(",", ":")))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class KisPaperCanaryClient:
    """The only module that can build a virtual-paper submit/cancel request."""

    def __init__(self, *, config: KisPaperConfig, transport: KisHttpTransport) -> None:
        self._config = config
        self._transport = transport
        self._access_token: str | None = None

    def snapshot(self) -> KisPaperReadOnlySnapshot:
        """Read one complete virtual-paper account fact using this client's token."""

        return KisPaperReadOnlyClient(
            config=self._config,
            transport=self._transport,
            access_token=self._issue_access_token(),
        ).snapshot()

    def reconcile(
        self,
        state: KisPaperCanaryState,
        *,
        now: datetime,
    ) -> KisPaperCanaryReconciliation:
        try:
            access_token = self._issue_access_token()
            read_only_client = KisPaperReadOnlyClient(
                config=self._config,
                transport=self._transport,
                access_token=access_token,
            )
            snapshot = read_only_client.snapshot()
            # Recovery time is not order time. Legacy unknown dates stay unknown.
            order_at = state.submission_started_at or state.submitted_at
            same_day_order = (
                None
                if state.broker_order_id is None or order_at is None
                else read_only_client.observe_order_execution(
                    state.broker_order_id,
                    order_at=order_at,
                    observed_at=now,
                    symbol=state.intent.symbol,
                    exchange=state.intent.exchange,
                    side=state.intent.side,
                    quantity=state.intent.quantity,
                )
            )
            recovered_broker_order_id = (
                None
                if state.phase != "outcome_unknown" or state.broker_order_id is not None
                else read_only_client._find_unique_exact_open_order_id(
                    symbol=state.intent.symbol,
                    exchange=state.intent.exchange,
                    side=state.intent.side,
                    quantity=state.intent.quantity,
                    limit_price=state.intent.limit_price,
                )
            )
        except (KisPaperCanaryError, KisPaperReadOnlyError) as error:
            return _unavailable_reconciliation(reason_code=_safe_reconciliation_reason_code(error))
        order_reference = (
            None
            if state.broker_order_id is None
            else _redacted_open_order_reference(state.broker_order_id)
        )
        matching_open = bool(
            order_reference
            and any(
                order.order_reference == order_reference for order in snapshot.open_orders.orders
            )
        )
        matching_ccnl = bool(same_day_order and same_day_order.same_day_order_id_seen)
        known = matching_open or matching_ccnl
        status: Literal["clean", "unresolved"] = "unresolved"
        if state.phase in {"intent_recorded", "rejected"}:
            status = "clean"
        elif (
            state.phase == "cancelled"
            and same_day_order is not None
            and not matching_open
            and not matching_ccnl
        ):
            status = "clean"
        elif known:
            status = "clean"
        return KisPaperCanaryReconciliation(
            snapshot=snapshot,
            account_status="available",
            ccnl_row_count=0 if same_day_order is None else same_day_order.row_count,
            matching_open_order=matching_open,
            matching_ccnl=matching_ccnl,
            status=status,
            recovered_broker_order_id=recovered_broker_order_id,
            execution=same_day_order,
        )

    def fetch_spy_quote(self) -> KisPaperSpyQuote:
        """Fetch the one transient quote that may seed a new virtual canary intent."""

        response = self._dispatch(
            build_kis_paper_spy_quote_request(
                config=self._config,
                access_token=self._issue_access_token(),
            )
        )
        if response.status_code != 200:
            raise KisPaperCanaryError("quote_rejected")
        try:
            payload = response.payload()
            return parse_kis_paper_spy_quote(payload)
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        except KisPaperReadOnlyError as error:
            raise KisPaperCanaryError("quote_response_incomplete") from error

    def probe_spy_price_detail(self) -> KisPaperSpyPriceDetailProbe:
        """Read one exact price-detail route without creating an intent or order."""

        response = self._dispatch(
            build_kis_paper_spy_price_detail_request(
                config=self._config,
                access_token=self._issue_access_token(),
            )
        )
        return inspect_kis_paper_spy_price_detail_response(response)

    def probe_spy_asking_price(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> KisPaperSpyAskingPriceProbe:
        """Read one exact best-price route without creating an intent or order."""

        response = self._dispatch(
            build_kis_paper_spy_asking_price_request(
                config=self._config,
                access_token=self._issue_access_token(),
            )
        )
        return inspect_kis_paper_spy_asking_price_response(response, observed_at=observed_at)

    def fetch_spy_limit_input(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> KisPaperSpyLimitInput:
        """Read the exact fresh AMS/SPY fields used by the Paper limit contract."""

        access_token = self._issue_access_token()
        asking_response = self._dispatch(
            build_kis_paper_spy_asking_price_request(
                config=self._config,
                access_token=access_token,
            )
        )
        price_detail_response = self._dispatch(
            build_kis_paper_spy_price_detail_request(
                config=self._config,
                access_token=access_token,
            )
        )
        if asking_response.status_code != 200 or price_detail_response.status_code != 200:
            raise KisPaperCanaryError("quote_rejected")
        try:
            return parse_kis_paper_spy_limit_input(
                asking_price_payload=asking_response.payload(),
                price_detail_payload=price_detail_response.payload(),
                observed_at=observed_at or datetime.now(UTC),
            )
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        except KisPaperReadOnlyError as error:
            raise KisPaperCanaryError("quote_response_incomplete") from error

    def fetch_qqq_quote(self) -> KisPaperQqqQuote:
        """Fetch the one transient NAS/QQQ quote that may seed a QQQ canary."""

        response = self._dispatch(
            build_kis_paper_qqq_quote_request(
                config=self._config,
                access_token=self._issue_access_token(),
            )
        )
        if response.status_code != 200:
            raise KisPaperCanaryError("quote_rejected")
        try:
            payload = response.payload()
            return parse_kis_paper_qqq_quote(payload)
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        except KisPaperReadOnlyError as error:
            raise KisPaperCanaryError("quote_response_incomplete") from error

    def probe_qqq_price_detail(self) -> KisPaperQqqPriceDetailProbe:
        """Read the fixed NAS/QQQ detail route without creating an intent or order."""

        response = self._dispatch(
            build_kis_paper_qqq_price_detail_request(
                config=self._config,
                access_token=self._issue_access_token(),
            )
        )
        return inspect_kis_paper_qqq_price_detail_response(response)

    def probe_qqq_asking_price(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> KisPaperQqqAskingPriceProbe:
        """Read the fixed NAS/QQQ asking route without creating an intent or order."""

        response = self._dispatch(
            build_kis_paper_qqq_asking_price_request(
                config=self._config,
                access_token=self._issue_access_token(),
            )
        )
        return inspect_kis_paper_qqq_asking_price_response(response, observed_at=observed_at)

    def fetch_qqq_limit_input(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> KisPaperQqqLimitInput:
        """Read the exact fresh NAS/QQQ fields used by the Paper limit contract."""

        access_token = self._issue_access_token()
        asking_response = self._dispatch(
            build_kis_paper_qqq_asking_price_request(
                config=self._config,
                access_token=access_token,
            )
        )
        price_detail_response = self._dispatch(
            build_kis_paper_qqq_price_detail_request(
                config=self._config,
                access_token=access_token,
            )
        )
        if asking_response.status_code != 200 or price_detail_response.status_code != 200:
            raise KisPaperCanaryError("quote_rejected")
        try:
            return parse_kis_paper_qqq_limit_input(
                asking_price_payload=asking_response.payload(),
                price_detail_payload=price_detail_response.payload(),
                observed_at=observed_at or datetime.now(UTC),
            )
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        except KisPaperReadOnlyError as error:
            raise KisPaperCanaryError("quote_response_incomplete") from error

    def submit_limit(
        self,
        intent: KisPaperCanaryIntent,
        *,
        now: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> tuple[bool, str | None]:
        """Submit the intent's explicit virtual-paper limit-order side only."""

        if intent.side == "buy":
            fields = map_kis_paper_us_buy_limit_order_fields(
                intent.broker_request(), exchange=intent.exchange
            )
            tr_id = KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID
        else:
            fields = map_kis_paper_us_sell_limit_order_fields(
                intent.broker_request(), exchange=intent.exchange
            )
            tr_id = KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID
        body = {
            "CANO": self._config.account_number,
            "ACNT_PRDT_CD": self._config.account_product_code,
            **fields,
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
        }
        response = self._dispatch(
            KisHttpRequest(
                method="POST",
                url=f"{self._config.base_url}{KIS_PAPER_US_BUY_LIMIT_ORDER_PATH}",
                headers=self._post_headers(tr_id),
                json_body=body,
            ),
            deadline=intent.valid_until,
            now=now,
            clock=clock,
        )
        probe = inspect_kis_paper_buy_limit_response(response)
        if probe.category == "http_non_200":
            raise KisPaperCanaryError(
                _submit_http_failure_reason(response),
                upstream_code=_submit_response_upstream_code(response),
                submit_response_category=probe.category,
            )
        if probe.category == "payload_invalid":
            raise KisPaperCanaryError(
                "submit_response_incomplete",
                submit_response_category=probe.category,
            )
        if probe.category == "provider_rejected":
            payload = response.payload()
            raise KisPaperCanaryError(
                "submit_kis_rejected",
                upstream_code=safe_kis_paper_upstream_code(payload.get("msg_cd")),
                submit_response_category=probe.category,
            )
        if probe.category == "success_output_missing":
            raise KisPaperCanaryError(
                "submit_response_incomplete",
                submit_response_category=probe.category,
            )
        if probe.category == "success_order_reference_missing":
            raise KisPaperCanaryError(
                "submit_response_incomplete",
                submit_response_category=probe.category,
            )
        if probe.category != "acknowledged_order_reference":
            raise KisPaperCanaryError(
                "submit_transport_unknown",
                submit_response_category="transport_unavailable",
            )
        payload = response.payload()
        output = payload.get("output")
        if not isinstance(output, Mapping):  # Defensive: probe already checked this shape.
            raise KisPaperCanaryError(
                "submit_response_incomplete",
                submit_response_category="success_output_missing",
            )
        order_id = output.get("ODNO")
        if not isinstance(order_id, str) or not _raw_order_id(order_id):  # Defensive shape check.
            raise KisPaperCanaryError(
                "submit_response_incomplete",
                submit_response_category="success_order_reference_missing",
            )
        return True, order_id

    def submit_buy_limit(
        self,
        intent: KisPaperCanaryIntent,
        *,
        now: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> tuple[bool, str | None]:
        """Compatibility wrapper for the original buy-only canary entry point."""

        if intent.side != "buy":
            raise KisPaperCanaryError("request_not_allowlisted")
        return self.submit_limit(intent, now=now, clock=clock)

    def cancel_order(self, intent: KisPaperCanaryIntent, *, broker_order_id: str) -> bool:
        """Cancel an acknowledged virtual-paper order without changing its side."""

        return self._cancel_limit_order(intent, broker_order_id=broker_order_id)

    def cancel_buy_order(self, intent: KisPaperCanaryIntent, *, broker_order_id: str) -> bool:
        """Compatibility wrapper for the original buy-only cancellation entry point."""

        if intent.side != "buy":
            raise KisPaperCanaryError("request_not_allowlisted")
        return self._cancel_limit_order(intent, broker_order_id=broker_order_id)

    def _cancel_limit_order(self, intent: KisPaperCanaryIntent, *, broker_order_id: str) -> bool:
        if not _raw_order_id(broker_order_id):
            raise KisPaperCanaryError("cancel_response_incomplete")
        body = {
            "CANO": self._config.account_number,
            "ACNT_PRDT_CD": self._config.account_product_code,
            "OVRS_EXCG_CD": intent.exchange,
            "PDNO": intent.symbol,
            "ORGN_ODNO": broker_order_id,
            "RVSE_CNCL_DVSN_CD": "02",
            "ORD_QTY": str(int(intent.quantity)),
            "OVRS_ORD_UNPR": "0",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0",
        }
        response = self._dispatch(
            KisHttpRequest(
                method="POST",
                url=f"{self._config.base_url}{KIS_PAPER_US_CANCEL_PATH}",
                headers=self._post_headers(KIS_PAPER_US_CANCEL_TR_ID),
                json_body=body,
            )
        )
        return response.status_code == 200 and response.payload().get("rt_cd") == "0"

    def _issue_access_token(self) -> str:
        if self._access_token is not None:
            return self._access_token
        response = self._dispatch(
            KisHttpRequest(
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
            raise KisPaperCanaryError("auth_rejected")
        payload = response.payload()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise KisPaperCanaryError("auth_response_invalid")
        self._access_token = token
        return token

    def _post_headers(self, tr_id: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._issue_access_token()}",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "content-type": "application/json",
            "accept": "application/json",
        }

    def _get_headers(self, access_token: str, tr_id: str, continuation: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {access_token}",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "tr_cont": continuation,
        }

    def _dispatch(
        self,
        request: KisHttpRequest,
        *,
        deadline: datetime | None = None,
        now: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> KisHttpResponse:
        validate_kis_paper_canary_request(request)
        if deadline is not None:
            if isinstance(self._transport, UrllibKisPaperCanaryTransport):
                pre_io_clock = clock or (lambda: datetime.now(UTC))
                return self._transport.request_before_deadline(
                    request,
                    deadline=deadline,
                    clock=pre_io_clock,
                )
            if _canary_now(now=now, clock=clock) >= deadline:
                raise KisPaperCanaryError("intent_expired")
        return self._transport.request(request)


def _run_kis_paper_canary(
    *,
    decision: KisPaperCanaryOrderDecision,
    run_id: str,
    environment: Mapping[str, str],
    state_path: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    submit_permitted: Callable[[datetime], bool] | None = None,
    execution_control_path: Path = DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
    require_existing_state: bool = False,
    price_contract_ref: str | None = None,
    reuse_existing_intent_if_same_decision: bool = False,
    read_only_recovery: bool = False,
    recovery_only: bool = False,
) -> KisPaperCanaryOutcome:
    """Run or recover one bounded virtual-paper canary without a retry submit path."""

    observed_at = _canary_now(now=now, clock=clock)
    state_store = KisPaperCanaryStateStore(state_path)
    requested_intent = KisPaperCanaryIntent.from_decision(
        decision,
        run_id=run_id,
        price_contract_ref=price_contract_ref,
    )
    existing_state = state_store.read()
    if existing_state is not None:
        if reuse_existing_intent_if_same_decision:
            _ensure_reusable_receipt_intent_matches(existing_state.intent, requested_intent)
        else:
            _ensure_recovery_intent_matches(existing_state.intent, requested_intent)
        intent = existing_state.intent
    elif require_existing_state:
        raise KisPaperCanaryError("recovery_state_missing")
    else:
        intent = requested_intent
    state = state_store.record_intent(
        intent,
        cancel_after_submit=cancel_after_submit,
        now=observed_at,
    )
    if recovery_only and state.phase not in _PENDING_RECOVERY_PHASES:
        raise KisPaperCanaryError("recovery_phase_not_reconcilable")
    prior_recovery_state = state if read_only_recovery else None
    emergency = EmergencyStore(emergency_state_path).read()
    execution_control = PaperExecutionControlStore(execution_control_path).read()
    reconciliation = _unavailable_reconciliation()

    if read_only_recovery:
        # This entry point is intentionally unable to reach submit or cancel branches.
        if (
            not execute
            or not require_existing_state
            or state.phase not in _READ_ONLY_RECOVERY_PHASES
        ):
            raise KisPaperCanaryError("recovery_phase_not_reconcilable")
        state, reconciliation = _recover_existing_canary(
            state=state,
            state_store=state_store,
            environment=environment,
            transport=transport,
            client=client,
            observed_at=observed_at,
            allow_order_side_effects=False,
            clock=lambda: _canary_now(now=now, clock=clock),
        )
    elif not execute:
        # Preview persists the intent but never reads credentials or calls KIS.
        pass
    elif state.phase != "intent_recorded":
        state, reconciliation = _recover_existing_canary(
            state=state,
            state_store=state_store,
            environment=environment,
            transport=transport,
            client=client,
            observed_at=observed_at,
            allow_order_side_effects=True,
            clock=lambda: _canary_now(now=now, clock=clock),
        )
    elif observed_at >= intent.valid_until:
        state = state_store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="intent_recorded",
            reason_code="intent_expired",
            now=observed_at,
        )
    elif emergency.blocks_new_orders:
        state = state_store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="intent_recorded",
            reason_code="emergency_stop_new_orders",
            now=observed_at,
        )
    elif execution_control.pause_buys if intent.side == "buy" else execution_control.pause_sells:
        state = state_store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="intent_recorded",
            reason_code=("pause_buys_active" if intent.side == "buy" else "pause_sells_active"),
            now=observed_at,
        )
    elif _conflicts_with_owned_spy_cycle(state_path.parent, intent):
        state = state_store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="intent_recorded",
            reason_code="owned_intent_conflict",
            now=observed_at,
        )
    else:
        if client is None:
            config = load_kis_paper_config_from_environment(environment)
            client = KisPaperCanaryClient(
                config=config,
                transport=transport or UrllibKisPaperCanaryTransport(),
            )
        reconciliation = client.reconcile(state, now=observed_at)
        if _conflicts_with_intent_open_order(reconciliation.snapshot, intent):
            state = state_store.transition(
                intent,
                expected=frozenset({"intent_recorded"}),
                phase="intent_recorded",
                reason_code="matching_open_order",
                now=observed_at,
            )
        elif reconciliation.account_status != "available":
            state = state_store.transition(
                intent,
                expected=frozenset({"intent_recorded"}),
                phase="intent_recorded",
                reason_code="reconciliation_unavailable",
                now=observed_at,
            )
        else:
            submit_at = _canary_now(now=now, clock=clock)
            if submit_at >= intent.valid_until:
                state = state_store.transition(
                    intent,
                    expected=frozenset({"intent_recorded"}),
                    phase="intent_recorded",
                    reason_code="intent_expired",
                    now=submit_at,
                )
            elif submit_permitted is not None and not submit_permitted(submit_at):
                state = state_store.transition(
                    intent,
                    expected=frozenset({"intent_recorded"}),
                    phase="intent_recorded",
                    reason_code="session_closed",
                    now=submit_at,
                )
            else:
                state = state_store.transition(
                    intent,
                    expected=frozenset({"intent_recorded"}),
                    phase="submission_started",
                    reason_code="preview",
                    now=submit_at,
                    submission_started_at=submit_at,
                )
                try:
                    accepted, broker_order_id = client.submit_limit(
                        intent,
                        now=now,
                        clock=clock,
                    )
                except (KisPaperCanaryError, KisPaperReadOnlyError) as error:
                    state = state_store.transition(
                        intent,
                        expected=frozenset({"submission_started"}),
                        phase="outcome_unknown",
                        reason_code=_safe_submit_failure_reason(error),
                        now=submit_at,
                        submit_upstream_code=_safe_submit_upstream_code(error),
                        submit_response_category=_safe_submit_response_category(error),
                    )
                else:
                    if not accepted:
                        state = state_store.transition(
                            intent,
                            expected=frozenset({"submission_started"}),
                            phase="rejected",
                            reason_code="submit_rejected",
                            now=submit_at,
                            submit_response_category="provider_rejected",
                        )
                    elif broker_order_id is None:
                        state = state_store.transition(
                            intent,
                            expected=frozenset({"submission_started"}),
                            phase="outcome_unknown",
                            reason_code="submit_response_incomplete",
                            now=submit_at,
                            submit_response_category="success_order_reference_missing",
                        )
                    else:
                        state = state_store.transition(
                            intent,
                            expected=frozenset({"submission_started"}),
                            phase="submitted",
                            reason_code="reconciliation_unresolved",
                            now=submit_at,
                            broker_order_id=broker_order_id,
                            submitted_at=submit_at,
                            submit_response_category="acknowledged_order_reference",
                        )
                        reconciliation = client.reconcile(state, now=submit_at)
                        if state.cancel_after_submit:
                            state, reconciliation = _cancel_submitted_canary(
                                client=client,
                                state_store=state_store,
                                state=state,
                                reconciliation=reconciliation,
                                observed_at=submit_at,
                            )

    if execute:
        state = _record_reconciliation_fill(
            state_store,
            state,
            reconciliation,
            observed_at=observed_at,
        )
    if reconciliation.snapshot is not None:
        write_paper_account_snapshot(
            paper_account_snapshot_from_kis_readonly(
                reconciliation.snapshot,
                observed_at=observed_at,
            ),
            paper_account_snapshot_path,
        )
    runtime_digest = _write_runtime_projection(
        state=state,
        reconciliation=reconciliation,
        emergency=emergency,
        runtime_projection_path=runtime_projection_path,
        observed_at=observed_at,
    )
    evidence_path = _write_evidence(
        state=state,
        reconciliation=reconciliation,
        emergency=emergency,
        runtime_digest=runtime_digest,
        artifact_root=artifact_root,
        repository_root=repository_root,
        observed_at=observed_at,
        prior_recovery_state=prior_recovery_state,
    )
    return KisPaperCanaryOutcome(
        run_id=run_id,
        phase=state.phase,
        reason_code=state.reason_code,
        evidence_path=evidence_path,
        runtime_path=runtime_projection_path,
        paper_account_snapshot_path=paper_account_snapshot_path,
        reconciliation=reconciliation,
        submit_upstream_code=state.submit_upstream_code,
        submit_response_category=state.submit_response_category,
    )


def _conflicts_with_owned_spy_cycle(state_root: Path, intent: KisPaperCanaryIntent) -> bool:
    if intent.symbol != "SPY":
        return False
    from .kis_paper_budget_strategy import conflicts_with_budget_strategy
    from .kis_paper_spy_fill_cycle import conflicts_with_active_spy_fill_cycle

    return conflicts_with_active_spy_fill_cycle(
        state_root, intent.run_id, intent.symbol
    ) or conflicts_with_budget_strategy(state_root, intent.run_id, intent.symbol)


def run_kis_paper_canary(
    *,
    decision: KisPaperCanaryOrderDecision,
    run_id: str,
    environment: Mapping[str, str],
    state_path: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    execute: bool,
    cancel_after_submit: bool,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    submit_permitted: Callable[[datetime], bool] | None = None,
    execution_control_path: Path = DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
    price_contract_ref: str | None = None,
    reuse_existing_intent_if_same_decision: bool = False,
) -> KisPaperCanaryOutcome:
    """Serialize one canary root from reconciliation through terminal state."""

    # Different run IDs share this lock, so they cannot both observe an empty
    # book and submit before either durable state transition is complete.
    with exclusive_kis_paper_canary_state_lock(state_path.parent / ".canary_execution"):
        return _run_kis_paper_canary(
            decision=decision,
            run_id=run_id,
            environment=environment,
            state_path=state_path,
            runtime_projection_path=runtime_projection_path,
            paper_account_snapshot_path=paper_account_snapshot_path,
            emergency_state_path=emergency_state_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=execute,
            cancel_after_submit=cancel_after_submit,
            transport=transport,
            client=client,
            now=now,
            clock=clock,
            submit_permitted=submit_permitted,
            execution_control_path=execution_control_path,
            price_contract_ref=price_contract_ref,
            reuse_existing_intent_if_same_decision=reuse_existing_intent_if_same_decision,
        )


def reconcile_kis_paper_canary_unknown_run(
    *,
    run_id: str,
    environment: Mapping[str, str],
    state_path: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    execution_control_path: Path = DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
) -> KisPaperCanaryOutcome:
    """Reconcile one ambiguous persisted run without creating or cancelling an order.

    The decision is reconstructed only from the private durable intent. Restricting
    this entry point to nonterminal ambiguity phases guarantees that it can enter
    the existing recovery branch but never the submit or cancellation branches.
    """

    _safe_identifier(run_id, "run_id")
    with exclusive_kis_paper_canary_state_lock(state_path.parent / ".canary_execution"):
        state = KisPaperCanaryStateStore(state_path).read()
        if state is None:
            raise KisPaperCanaryError("recovery_state_missing")
        if state.intent.run_id != run_id:
            raise KisPaperCanaryError("recovery_run_id_mismatch")
        if state.phase not in _READ_ONLY_RECOVERY_PHASES:
            raise KisPaperCanaryError("recovery_phase_not_reconcilable")
        intent = state.intent
        decision: KisPaperCanaryOrderDecision
        decision_type = (
            KisPaperCanaryBuyDecision if intent.side == "buy" else KisPaperCanarySellDecision
        )
        decision = decision_type(
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            exchange=intent.exchange,
            quantity=intent.quantity,
            limit_price=intent.limit_price,
            decision_as_of=intent.created_at,
            valid_until=intent.valid_until,
        )
        return _run_kis_paper_canary(
            decision=decision,
            run_id=run_id,
            environment=environment,
            state_path=state_path,
            runtime_projection_path=runtime_projection_path,
            paper_account_snapshot_path=paper_account_snapshot_path,
            emergency_state_path=emergency_state_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=True,
            cancel_after_submit=state.cancel_after_submit,
            transport=transport,
            now=now,
            clock=clock,
            execution_control_path=execution_control_path,
            require_existing_state=True,
            read_only_recovery=True,
        )


def recover_kis_paper_canary_pending_run(
    *,
    run_id: str,
    environment: Mapping[str, str],
    state_path: Path,
    runtime_projection_path: Path,
    paper_account_snapshot_path: Path,
    emergency_state_path: Path,
    artifact_root: Path,
    repository_root: Path,
    transport: KisHttpTransport | None = None,
    client: KisPaperCanaryClient | None = None,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
    execution_control_path: Path = DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
) -> KisPaperCanaryOutcome:
    """Resume one persisted pending run without creating a fresh order intent.

    This entry point may only reconcile or continue the cancellation path of the
    exact durable state. It cannot reach the new-submit branch, including if a
    concurrent state mutation changes the phase after the initial inventory.
    """

    _safe_identifier(run_id, "run_id")
    with exclusive_kis_paper_canary_state_lock(state_path.parent / ".canary_execution"):
        state = KisPaperCanaryStateStore(state_path).read()
        if state is None:
            raise KisPaperCanaryError("recovery_state_missing")
        if state.intent.run_id != run_id:
            raise KisPaperCanaryError("recovery_run_id_mismatch")
        if state.phase not in _PENDING_RECOVERY_PHASES:
            raise KisPaperCanaryError("recovery_phase_not_reconcilable")
        intent = state.intent
        decision_type = (
            KisPaperCanaryBuyDecision if intent.side == "buy" else KisPaperCanarySellDecision
        )
        decision: KisPaperCanaryOrderDecision = decision_type(
            decision_id=intent.decision_id,
            symbol=intent.symbol,
            exchange=intent.exchange,
            quantity=intent.quantity,
            limit_price=intent.limit_price,
            decision_as_of=intent.created_at,
            valid_until=intent.valid_until,
        )
        return _run_kis_paper_canary(
            decision=decision,
            run_id=run_id,
            environment=environment,
            state_path=state_path,
            runtime_projection_path=runtime_projection_path,
            paper_account_snapshot_path=paper_account_snapshot_path,
            emergency_state_path=emergency_state_path,
            artifact_root=artifact_root,
            repository_root=repository_root,
            execute=True,
            cancel_after_submit=state.cancel_after_submit,
            transport=transport,
            client=client,
            now=now,
            clock=clock,
            execution_control_path=execution_control_path,
            require_existing_state=True,
            recovery_only=True,
        )


def _canary_now(
    *,
    now: datetime | None,
    clock: Callable[[], datetime] | None,
) -> datetime:
    if now is not None and clock is not None:
        raise ValueError("now and clock are mutually exclusive")
    source = now if now is not None else (clock() if clock is not None else datetime.now(UTC))
    return require_utc(source, "now")


def validate_kis_paper_canary_request(request: KisHttpRequest) -> None:
    """Reject every request outside the small virtual-paper canary surface."""

    try:
        validate_kis_paper_readonly_request(request)
        return
    except KisPaperReadOnlyError as read_only_error:
        if read_only_error.code == "paper_host_required":
            raise KisPaperCanaryError(read_only_error.code) from read_only_error
    parsed = urllib.parse.urlparse(request.url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "openapivts.koreainvestment.com"
        or parsed.port != 29443
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise KisPaperCanaryError("request_not_allowlisted")
    if request.method == "GET" and parsed.path == KIS_PAPER_US_SPY_QUOTE_PATH:
        _validate_allowlisted_price_request(
            request,
            spy_validator=validate_kis_paper_spy_quote_request,
            qqq_validator=validate_kis_paper_qqq_quote_request,
        )
        return
    if request.method == "GET" and parsed.path == KIS_PAPER_US_SPY_PRICE_DETAIL_PATH:
        _validate_allowlisted_price_request(
            request,
            spy_validator=validate_kis_paper_spy_price_detail_request,
            qqq_validator=validate_kis_paper_qqq_price_detail_request,
        )
        return
    if request.method == "GET" and parsed.path == KIS_PAPER_US_SPY_ASKING_PRICE_PATH:
        _validate_allowlisted_price_request(
            request,
            spy_validator=validate_kis_paper_spy_asking_price_request,
            qqq_validator=validate_kis_paper_qqq_asking_price_request,
        )
        return
    if request.method == "POST" and parsed.path == KIS_PAPER_US_BUY_LIMIT_ORDER_PATH:
        if request.headers.get("tr_id") == KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID:
            _validate_post_headers(request, tr_id=KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID)
            _validate_order_body(request.json_body, _BUY_LIMIT_BODY_KEYS)
            _validate_buy_limit_body(request.json_body)
            return
        if request.headers.get("tr_id") == KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID:
            _validate_post_headers(request, tr_id=KIS_PAPER_US_SELL_LIMIT_ORDER_TR_ID)
            _validate_order_body(request.json_body, _BUY_LIMIT_BODY_KEYS)
            _validate_sell_limit_body(request.json_body)
            return
        raise KisPaperCanaryError("request_not_allowlisted")
    if request.method == "POST" and parsed.path == KIS_PAPER_US_CANCEL_PATH:
        _validate_post_headers(request, tr_id=KIS_PAPER_US_CANCEL_TR_ID)
        _validate_order_body(request.json_body, _CANCEL_BODY_KEYS)
        _validate_cancel_body(request.json_body)
        return
    raise KisPaperCanaryError("request_not_allowlisted")


def _validate_allowlisted_price_request(
    request: KisHttpRequest,
    *,
    spy_validator: Callable[[KisHttpRequest], None],
    qqq_validator: Callable[[KisHttpRequest], None],
) -> None:
    validator = (
        qqq_validator
        if request.query.get("SYMB") == KIS_PAPER_US_QQQ_QUOTE_SYMBOL
        else spy_validator
    )
    try:
        validator(request)
    except KisPaperQuoteError as error:
        raise KisPaperCanaryError(error.code) from error


def _record_reconciliation_fill(
    store: KisPaperCanaryStateStore,
    state: KisPaperCanaryState,
    reconciliation: KisPaperCanaryReconciliation,
    *,
    observed_at: datetime,
) -> KisPaperCanaryState:
    observation = reconciliation.execution
    if observation is None:
        if state.cumulative_fill is None:
            return state
        observation = KisPaperExecutionObservation(0, False, "unavailable")
    return store.record_fill_observation(
        state.intent,
        observation,
        now=(
            observation.observed_at
            or (
                observation.fill.observed_at
                if observation.fill is not None
                else max(observed_at, state.updated_at)
            )
        ),
    )


def _cancel_submitted_canary(
    *,
    client: KisPaperCanaryClient,
    state_store: KisPaperCanaryStateStore,
    state: KisPaperCanaryState,
    reconciliation: KisPaperCanaryReconciliation,
    observed_at: datetime,
) -> tuple[KisPaperCanaryState, KisPaperCanaryReconciliation]:
    # A cancellation may remove the history row. Retain any prior exact fill
    # before the side effect; a later absent row changes freshness, not totals.
    state = _record_reconciliation_fill(
        state_store,
        state,
        reconciliation,
        observed_at=observed_at,
    )
    if state.broker_order_id is None:
        return state, reconciliation
    state = state_store.transition(
        state.intent,
        expected=frozenset({"submitted"}),
        phase="cancel_started",
        reason_code="reconciliation_unresolved",
        now=observed_at,
    )
    try:
        cancelled = client.cancel_order(state.intent, broker_order_id=state.broker_order_id)
    except (KisPaperCanaryError, KisPaperReadOnlyError):
        state = state_store.transition(
            state.intent,
            expected=frozenset({"cancel_started"}),
            phase="outcome_unknown",
            reason_code="cancel_transport_unknown",
            now=observed_at,
        )
        return state, client.reconcile(state, now=observed_at)
    if not cancelled:
        state = state_store.transition(
            state.intent,
            expected=frozenset({"cancel_started"}),
            phase="submitted",
            reason_code="cancel_rejected",
            now=observed_at,
        )
        return state, client.reconcile(state, now=observed_at)
    reconciliation = client.reconcile(state, now=observed_at)
    if (
        reconciliation.account_status != "available"
        or (state.submission_started_at is None and state.submitted_at is None)
        or reconciliation.matching_open_order
        or reconciliation.matching_ccnl
    ):
        state = state_store.transition(
            state.intent,
            expected=frozenset({"cancel_started"}),
            phase="outcome_unknown",
            reason_code="reconciliation_unresolved",
            now=observed_at,
        )
        return state, reconciliation
    state = state_store.transition(
        state.intent,
        expected=frozenset({"cancel_started"}),
        phase="cancelled",
        reason_code="reconciliation_clean",
        now=observed_at,
    )
    return state, client.reconcile(state, now=observed_at)


def _recover_existing_canary(
    *,
    state: KisPaperCanaryState,
    state_store: KisPaperCanaryStateStore,
    environment: Mapping[str, str],
    transport: KisHttpTransport | None,
    client: KisPaperCanaryClient | None,
    observed_at: datetime,
    allow_order_side_effects: bool,
    clock: Callable[[], datetime],
) -> tuple[KisPaperCanaryState, KisPaperCanaryReconciliation]:
    try:
        if client is None:
            client = KisPaperCanaryClient(
                config=load_kis_paper_config_from_environment(environment),
                transport=transport or UrllibKisPaperCanaryTransport(),
            )
        reconciliation = client.reconcile(state, now=observed_at)
        state = _record_reconciliation_fill(
            state_store,
            state,
            reconciliation,
            observed_at=observed_at,
        )
        if (
            state.phase in {"submitted", "cancel_started", "outcome_unknown"}
            and reconciliation.execution is not None
            and reconciliation.execution.cancellation_confirmed
        ):
            reconciled_at = clock()
            if _confirmed_zero_fill_cancel(
                state, reconciliation, environment=environment, now=reconciled_at
            ):
                return state_store.transition(
                    state.intent,
                    expected=frozenset({state.phase}),
                    phase="cancelled",
                    reason_code="reconciliation_clean",
                    now=reconciled_at,
                ), reconciliation
        if (
            allow_order_side_effects
            and state.phase == "outcome_unknown"
            and state.broker_order_id is None
            and state.submit_response_category in _IDLESS_RECOVERABLE_SUBMIT_CATEGORIES
            and reconciliation.recovered_broker_order_id is not None
        ):
            state = state_store.transition(
                state.intent,
                expected=frozenset({"outcome_unknown"}),
                phase="submitted",
                reason_code="reconciliation_clean",
                now=observed_at,
                broker_order_id=reconciliation.recovered_broker_order_id,
                submitted_at=state.submission_started_at,
            )
            reconciliation = client.reconcile(state, now=observed_at)
            state = _record_reconciliation_fill(
                state_store,
                state,
                reconciliation,
                observed_at=observed_at,
            )
        if (
            allow_order_side_effects
            and state.phase == "outcome_unknown"
            and state.broker_order_id is not None
            and state.cancel_after_submit
            and reconciliation.matching_open_order
        ):
            # Reconciliation proves this exact durable order is still open after
            # a cancel transport failure. Resume only its cancellation path.
            state = state_store.transition(
                state.intent,
                expected=frozenset({"outcome_unknown"}),
                phase="submitted",
                reason_code="reconciliation_unresolved",
                now=observed_at,
            )
            reconciliation = client.reconcile(state, now=observed_at)
            state = _record_reconciliation_fill(
                state_store,
                state,
                reconciliation,
                observed_at=observed_at,
            )
    except (KisPaperCanaryError, KisPaperReadOnlyError) as error:
        return state, _unavailable_reconciliation(
            reason_code=_safe_reconciliation_reason_code(error)
        )
    if (
        allow_order_side_effects
        and state.phase == "submitted"
        and state.cancel_after_submit
        and state.broker_order_id is not None
        and reconciliation.matching_open_order
    ):
        return _cancel_submitted_canary(
            client=client,
            state_store=state_store,
            state=state,
            reconciliation=reconciliation,
            observed_at=observed_at,
        )
    if state.phase in {"submission_started", "cancel_started", "outcome_unknown"}:
        state = state_store.transition(
            state.intent,
            expected=frozenset({state.phase}),
            phase="outcome_unknown",
            reason_code=(
                "reconciliation_clean"
                if reconciliation.status == "clean"
                else "reconciliation_unresolved"
            ),
            now=max(observed_at, state.updated_at),
        )
    return state, reconciliation


def _confirmed_zero_fill_cancel(state, reconciliation, *, environment, now) -> bool:
    observation, snapshot = reconciliation.execution, reconciliation.snapshot
    if (
        observation is None or not observation.cancellation_confirmed
        or state.current_fill is None or state.current_fill != observation.fill
        or not timedelta(0) <= now - observation.fill.observed_at
        <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
        or snapshot is None or reconciliation.account_status != "available"
        or not reconciliation.matching_ccnl or reconciliation.matching_open_order
        or not snapshot.open_orders.complete
        or state.broker_order_id is None
        or (state.submission_started_at or state.submitted_at) is None
        or any(
            (order.symbol, order.exchange) == (state.intent.symbol, state.intent.exchange)
            for order in snapshot.open_orders.orders
        )
    ):
        return False
    config = load_kis_paper_config_from_environment(environment)
    times = [
        observation.fill.observed_at, snapshot.captured_at, snapshot.identity.captured_at,
        snapshot.open_orders.captured_at, snapshot.cash.captured_at,
        snapshot.orderable_funds.captured_at,
        *(item.captured_at for item in snapshot.positions),
    ]
    return snapshot.identity.masked_account == config.masked_account_identity and all(
        timedelta(seconds=-5) <= now - timestamp <= KIS_PAPER_SPY_ASKING_PRICE_MAX_AGE
        for timestamp in times
    )


def _conflicts_with_intent_open_order(
    snapshot: KisPaperReadOnlySnapshot | None,
    intent: KisPaperCanaryIntent,
) -> bool:
    if snapshot is None:
        return False
    return any(
        order.symbol == intent.symbol
        and order.exchange == intent.exchange
        and order.side == intent.side
        and (
            order.requested_quantity == intent.quantity
            or order.remaining_quantity == intent.quantity
        )
        for order in snapshot.open_orders.orders
    )


def _ensure_recovery_intent_matches(
    recorded: KisPaperCanaryIntent,
    requested: KisPaperCanaryIntent,
) -> None:
    recorded_identity = (
        recorded.run_id,
        recorded.client_order_id,
        recorded.decision_id,
        recorded.symbol,
        recorded.exchange,
        recorded.side,
        recorded.quantity,
        recorded.limit_price,
    )
    requested_identity = (
        requested.run_id,
        requested.client_order_id,
        requested.decision_id,
        requested.symbol,
        requested.exchange,
        requested.side,
        requested.quantity,
        requested.limit_price,
    )
    if recorded_identity != requested_identity:
        raise KisPaperCanaryError("state_intent_mismatch")


def _ensure_reusable_receipt_intent_matches(
    recorded: KisPaperCanaryIntent,
    requested: KisPaperCanaryIntent,
) -> None:
    """Permit a receipt retry to recover its first persisted price, never replace it."""

    recorded_identity = (
        recorded.run_id,
        recorded.client_order_id,
        recorded.decision_id,
        recorded.symbol,
        recorded.exchange,
        recorded.side,
        recorded.quantity,
    )
    requested_identity = (
        requested.run_id,
        requested.client_order_id,
        requested.decision_id,
        requested.symbol,
        requested.exchange,
        requested.side,
        requested.quantity,
    )
    if recorded_identity != requested_identity or recorded.price_contract_ref is None:
        raise KisPaperCanaryError("state_intent_mismatch")


def inspect_kis_paper_buy_limit_response(
    response: KisHttpResponse,
) -> KisPaperSubmitResponseProbe:
    """Classify a virtual buy-limit acknowledgement without exposing its body."""

    http_status_class = _http_status_class(response.status_code)
    if response.status_code != 200:
        return KisPaperSubmitResponseProbe(
            http_status_class=http_status_class,
            category="http_non_200",
            upstream_code_state=_submit_upstream_code_state(response),
        )
    try:
        payload = response.payload()
    except KisPaperReadOnlyError:
        return KisPaperSubmitResponseProbe(
            http_status_class=http_status_class,
            category="payload_invalid",
            upstream_code_state="not_checked",
        )
    upstream_code_state = _payload_upstream_code_state(payload)
    if payload.get("rt_cd") != "0":
        return KisPaperSubmitResponseProbe(
            http_status_class=http_status_class,
            category="provider_rejected",
            upstream_code_state=upstream_code_state,
        )
    output = payload.get("output")
    if not isinstance(output, Mapping):
        return KisPaperSubmitResponseProbe(
            http_status_class=http_status_class,
            category="success_output_missing",
            upstream_code_state=upstream_code_state,
        )
    order_id = output.get("ODNO")
    if not isinstance(order_id, str) or not _raw_order_id(order_id):
        return KisPaperSubmitResponseProbe(
            http_status_class=http_status_class,
            category="success_order_reference_missing",
            upstream_code_state=upstream_code_state,
        )
    return KisPaperSubmitResponseProbe(
        http_status_class=http_status_class,
        category="acknowledged_order_reference",
        upstream_code_state=upstream_code_state,
    )


def _submit_http_failure_reason(response: KisHttpResponse) -> str:
    if _submit_response_has_rate_limit_code(response):
        return "submit_rate_limited"
    status_code = response.status_code
    if 400 <= status_code < 500:
        return "submit_http_4xx"
    if 500 <= status_code < 600:
        return "submit_http_5xx"
    return "submit_transport_unknown"


def _safe_submit_failure_reason(error: Exception) -> str:
    if isinstance(error, KisPaperCanaryError) and error.code in {
        "submit_http_4xx",
        "submit_http_5xx",
        "submit_kis_rejected",
        "submit_rate_limited",
        "submit_response_incomplete",
    }:
        return error.code
    return "submit_transport_unknown"


def _safe_submit_upstream_code(error: Exception) -> str | None:
    if isinstance(error, KisPaperCanaryError):
        return error.upstream_code
    return None


def _safe_submit_response_category(error: Exception) -> str:
    if isinstance(error, KisPaperCanaryError) and error.submit_response_category is not None:
        return error.submit_response_category
    return "transport_unavailable"


def _submit_response_has_rate_limit_code(response: KisHttpResponse) -> bool:
    return _submit_response_upstream_code(response) == KIS_PAPER_RATE_LIMIT_CODE


def _submit_response_upstream_code(response: KisHttpResponse) -> str | None:
    try:
        payload = response.payload()
    except KisPaperReadOnlyError:
        return None
    return safe_kis_paper_upstream_code(payload.get("msg_cd"))


def _submit_upstream_code_state(
    response: KisHttpResponse,
) -> Literal["not_checked", "valid", "absent_or_invalid"]:
    try:
        payload = response.payload()
    except KisPaperReadOnlyError:
        return "not_checked"
    return _payload_upstream_code_state(payload)


def _payload_upstream_code_state(
    payload: Mapping[str, object],
) -> Literal["not_checked", "valid", "absent_or_invalid"]:
    return (
        "valid"
        if safe_kis_paper_upstream_code(payload.get("msg_cd")) is not None
        else "absent_or_invalid"
    )


def _http_status_class(status_code: int) -> Literal["1xx", "2xx", "3xx", "4xx", "5xx", "other"]:
    if 100 <= status_code < 200:
        return "1xx"
    if 200 <= status_code < 300:
        return "2xx"
    if 300 <= status_code < 400:
        return "3xx"
    if 400 <= status_code < 500:
        return "4xx"
    if 500 <= status_code < 600:
        return "5xx"
    return "other"


def _unavailable_reconciliation(*, reason_code: str | None = None) -> KisPaperCanaryReconciliation:
    return KisPaperCanaryReconciliation(
        snapshot=None,
        account_status="unavailable",
        ccnl_row_count=0,
        matching_open_order=False,
        matching_ccnl=False,
        status="unresolved",
        reason_code=reason_code,
    )


def _safe_reconciliation_reason_code(
    error: KisPaperCanaryError | KisPaperReadOnlyError,
) -> str | None:
    code = error.code
    if code in PAPER_CANARY_SAFE_RECONCILIATION_REASON_CODES:
        return code
    return None


def _write_runtime_projection(
    *,
    state: KisPaperCanaryState,
    reconciliation: KisPaperCanaryReconciliation,
    emergency: object,
    runtime_projection_path: Path,
    observed_at: datetime,
) -> str:
    stop_new_orders = bool(getattr(emergency, "stop_new_orders", True))
    cancel_requested = bool(getattr(emergency, "cancel_open_orders_requested", False))
    status = "unavailable" if state.reason_code == "emergency_stop_new_orders" else state.phase
    if status == "cancel_started":
        status = "submission_started"
    return write_paper_canary_runtime(
        PaperCanaryRuntimeSnapshot(
            run_id=state.intent.run_id,
            status=status,  # type: ignore[arg-type]
            reconciliation_status=reconciliation.status,
            reconciliation_reason_code=reconciliation.reason_code,
            submit_upstream_code=state.submit_upstream_code,
            account_status=reconciliation.account_status,
            position_count=reconciliation.position_count,
            open_order_count=reconciliation.open_order_count,
            stop_new_orders=stop_new_orders,
            cancel_open_orders_requested=cancel_requested,
            observed_at=observed_at,
            expires_at=observed_at + PAPER_CANARY_RUNTIME_TTL,
            order_reference=(
                None
                if state.broker_order_id is None
                else redact_paper_canary_order_reference(state.broker_order_id)
            ),
        ),
        runtime_projection_path,
    )


def _write_evidence(
    *,
    state: KisPaperCanaryState,
    reconciliation: KisPaperCanaryReconciliation,
    emergency: object,
    runtime_digest: str,
    artifact_root: Path,
    repository_root: Path,
    observed_at: datetime,
    prior_recovery_state: KisPaperCanaryState | None = None,
) -> Path:
    root = artifact_root.resolve()
    repo = repository_root.resolve()
    if not _is_permitted_artifact_root(root, repo):
        raise KisPaperCanaryError("artifact_root_inside_repository")
    run_root = root / "execution" / "kis-paper-canary" / state.intent.run_id
    primary_destination = run_root / "evidence.json"
    destination = primary_destination
    prior_evidence_sha256: str | None = None
    if prior_recovery_state is not None:
        if primary_destination.is_file():
            prior_evidence_sha256 = (
                "sha256:" + hashlib.sha256(primary_destination.read_bytes()).hexdigest()
            )
        identity = "|".join(
            (
                prior_recovery_state.intent.fingerprint,
                prior_recovery_state.updated_at.isoformat(),
                observed_at.isoformat(),
            )
        )
        suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        timestamp = observed_at.strftime("%Y%m%dT%H%M%S%fZ")
        destination = run_root / "reconciliations" / f"{timestamp}-{suffix}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": (
            "kis_paper_canary_evidence"
            if prior_recovery_state is None
            else "kis_paper_canary_reconciliation_evidence"
        ),
        "paper_only": True,
        "run_id": state.intent.run_id,
        "order_side": state.intent.side,
        "intent_fingerprint": state.intent.fingerprint,
        "decision_ref": _redacted_decision_reference(state.intent.decision_id),
        "attribution_ref": _receipt_attribution_reference(state.intent.decision_id),
        "price_contract_ref": state.intent.price_contract_ref,
        "phase": state.phase,
        "reason_code": state.reason_code,
        "submit_upstream_code": state.submit_upstream_code,
        "submit_response_category": state.submit_response_category,
        "observed_at": observed_at.isoformat(),
        "order_reference": (
            None
            if state.broker_order_id is None
            else redact_paper_canary_order_reference(state.broker_order_id)
        ),
        "reconciliation": {
            "status": reconciliation.status,
            "reason_code": reconciliation.reason_code,
            "account_status": reconciliation.account_status,
            "position_count": reconciliation.position_count,
            "open_order_count": reconciliation.open_order_count,
            "ccnl_row_count": reconciliation.ccnl_row_count,
            "matching_open_order": reconciliation.matching_open_order,
            "matching_ccnl": reconciliation.matching_ccnl,
        },
        "emergency": {
            "stop_new_orders": bool(getattr(emergency, "stop_new_orders", True)),
            "cancel_open_orders_requested": bool(
                getattr(emergency, "cancel_open_orders_requested", False)
            ),
        },
        "runtime_projection_sha256": runtime_digest,
    }
    if state.fill_observation_status != "not_observed":
        payload["fill_accounting"] = {
            "source": "kis_paper",
            "observation_status": state.fill_observation_status,
            "observed_at": state.fill_observed_at.isoformat(),
            "quantity_state": (
                "not_observed" if state.current_fill is None else state.current_fill.status
            ),
            "fees": "not_observed",
            "settled_cash": "not_observed",
            "net_pnl": "not_observed",
        }
    if prior_recovery_state is not None:
        payload.update(
            {
                "prior_phase": prior_recovery_state.phase,
                "prior_reason_code": prior_recovery_state.reason_code,
                "prior_evidence_sha256": prior_evidence_sha256,
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    immutable = prior_recovery_state is not None
    if immutable and destination.exists():
        try:
            if destination.read_bytes() == encoded + b"\n":
                return destination
        except OSError as error:
            raise KisPaperCanaryError("recovery_evidence_collision") from error
        raise KisPaperCanaryError("recovery_evidence_collision")
    staging = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with staging.open("wb") as handle:
            handle.write(encoded)
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination


def _validate_get_headers(request: KisHttpRequest, *, tr_id: str) -> None:
    if (
        set(request.headers) != _PAPER_GET_HEADERS
        or request.headers.get("tr_id") != tr_id
        or not request.headers.get("authorization", "").startswith("Bearer ")
        or not request.headers.get("authorization", "").removeprefix("Bearer ")
        or not request.headers.get("appkey")
        or not request.headers.get("appsecret")
        or request.headers.get("custtype") != "P"
        or request.headers.get("tr_cont") not in {"", "N"}
    ):
        raise KisPaperCanaryError("request_not_allowlisted")


def _validate_post_headers(request: KisHttpRequest, *, tr_id: str) -> None:
    if (
        request.query
        or set(request.headers) != _PAPER_POST_HEADERS
        or request.headers.get("tr_id") != tr_id
        or not request.headers.get("authorization", "").startswith("Bearer ")
        or not request.headers.get("authorization", "").removeprefix("Bearer ")
        or not request.headers.get("appkey")
        or not request.headers.get("appsecret")
        or request.headers.get("custtype") != "P"
        or request.headers.get("content-type") != "application/json"
        or request.headers.get("accept") != "application/json"
    ):
        raise KisPaperCanaryError("request_not_allowlisted")


def _validate_order_body(body: Mapping[str, str] | None, expected: frozenset[str]) -> None:
    if (
        body is None
        or set(body) != expected
        or any(not isinstance(value, str) for value in body.values())
    ):
        raise KisPaperCanaryError("request_not_allowlisted")


def _validate_buy_limit_body(body: Mapping[str, str] | None) -> None:
    assert body is not None
    if (
        not _account_number(body["CANO"])
        or not _account_product_code(body["ACNT_PRDT_CD"])
        or body["OVRS_EXCG_CD"] not in {"NASD", "NYSE", "AMEX"}
        or not _symbol(body["PDNO"])
        or not _whole_positive(body["ORD_QTY"])
        or not _positive_price(body["OVRS_ORD_UNPR"])
        or body["CTAC_TLNO"] != ""
        or body["MGCO_APTM_ODNO"] != ""
        or body["SLL_TYPE"] != ""
        or body["ORD_SVR_DVSN_CD"] != "0"
        or body["ORD_DVSN"] != "00"
    ):
        raise KisPaperCanaryError("request_not_allowlisted")


def _validate_sell_limit_body(body: Mapping[str, str] | None) -> None:
    assert body is not None
    if (
        not _account_number(body["CANO"])
        or not _account_product_code(body["ACNT_PRDT_CD"])
        or body["OVRS_EXCG_CD"] not in {"NASD", "NYSE", "AMEX"}
        or not _symbol(body["PDNO"])
        or not _whole_positive(body["ORD_QTY"])
        or not _positive_price(body["OVRS_ORD_UNPR"])
        or body["CTAC_TLNO"] != ""
        or body["MGCO_APTM_ODNO"] != ""
        or body["SLL_TYPE"] != "00"
        or body["ORD_SVR_DVSN_CD"] != "0"
        or body["ORD_DVSN"] != "00"
    ):
        raise KisPaperCanaryError("request_not_allowlisted")


def _validate_cancel_body(body: Mapping[str, str] | None) -> None:
    assert body is not None
    if (
        not _account_number(body["CANO"])
        or not _account_product_code(body["ACNT_PRDT_CD"])
        or body["OVRS_EXCG_CD"] not in {"NASD", "NYSE", "AMEX"}
        or not _symbol(body["PDNO"])
        or not _raw_order_id(body["ORGN_ODNO"])
        or body["RVSE_CNCL_DVSN_CD"] != "02"
        or not _whole_positive(body["ORD_QTY"])
        or body["OVRS_ORD_UNPR"] != "0"
        or body["MGCO_APTM_ODNO"] != ""
        or body["ORD_SVR_DVSN_CD"] != "0"
    ):
        raise KisPaperCanaryError("request_not_allowlisted")


def _account_number(value: str) -> bool:
    return len(value) == 8 and value.isdigit()


def _account_product_code(value: str) -> bool:
    return len(value) == 2 and value.isdigit()


def _symbol(value: str) -> bool:
    if not value or len(value) > 24 or value != value.upper():
        return False
    return all(character.isalnum() or character in ".-" for character in value)


def _whole_positive(value: str) -> bool:
    return value.isdigit() and int(value) > 0


def _positive_price(value: str) -> bool:
    if not value or value.count(".") > 1:
        return False
    whole, _, fraction = value.partition(".")
    if not whole.isdigit() or (fraction and not fraction.isdigit()):
        return False
    try:
        return Decimal(value).is_finite() and Decimal(value) > 0
    except InvalidOperation:
        return False


def _request_url_with_query(request: KisHttpRequest) -> str:
    if not request.query:
        return request.url
    return f"{request.url}?{urllib.parse.urlencode(sorted(request.query.items()))}"


def _raw_order_id(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 64
        and all(character.isalnum() or character in "-_" for character in value)
    )


def _redacted_open_order_reference(raw_order_id: str) -> str:
    digest = hashlib.sha256(raw_order_id.encode("utf-8")).hexdigest()[:16]
    return f"open-{digest}"


def _redacted_decision_reference(raw_decision_id: str) -> str:
    _safe_identifier(raw_decision_id, "decision_id")
    digest = hashlib.sha256(raw_decision_id.encode("utf-8")).hexdigest()[:16]
    return f"decision-{digest}"


def _receipt_attribution_reference(raw_decision_id: str) -> str | None:
    """Expose the exact opaque receipt digest only for the dedicated bridge form."""

    match = _RECEIPT_DECISION_ID.fullmatch(raw_decision_id)
    return None if match is None else f"sha256:{match.group(1)}"


def _safe_identifier(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 80
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise ValueError(f"canary {label} is invalid")


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("text")
    return value


def _required_sha256_reference(value: object) -> str:
    if not isinstance(value, str) or _SHA256_REFERENCE.fullmatch(value) is None:
        raise ValueError("sha256 reference")
    return value


def _required_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("bool")
    return value


def _positive_decimal(value: object) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("decimal") from error
    if not decimal.is_finite() or decimal <= 0:
        raise ValueError("decimal")
    return decimal


def _utc_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime")
    return require_utc(datetime.fromisoformat(value), "datetime")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_permitted_artifact_root(artifact_root: Path, repository_root: Path) -> bool:
    if not _is_within(artifact_root, repository_root):
        return True
    return artifact_root == repository_root / "model_artifacts" and artifact_root.is_mount()


_STATE_LOCKS: dict[Path, threading.RLock] = {}
_STATE_LOCKS_GUARD = threading.Lock()


@contextmanager
def exclusive_kis_paper_canary_state_lock(path: Path) -> Iterator[None]:
    resolved = path.resolve()
    with _STATE_LOCKS_GUARD:
        lock = _STATE_LOCKS.setdefault(resolved, threading.RLock())
    with lock:
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one KIS virtual-paper buy-limit canary")
    parser.add_argument("--run-id")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--exchange", default="NASD")
    parser.add_argument("--quantity", default="1")
    parser.add_argument("--limit-price", default="1")
    parser.add_argument("--valid-seconds", type=int, default=300)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cancel-after-submit", action="store_true")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_STATE_ROOT,
    )
    parser.add_argument(
        "--runtime-projection",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_RUNTIME_PROJECTION,
    )
    parser.add_argument(
        "--paper-account-snapshot",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_ACCOUNT_SNAPSHOT,
    )
    parser.add_argument(
        "--emergency-state",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_EMERGENCY_STATE,
    )
    parser.add_argument(
        "--execution-control",
        type=Path,
        default=DEFAULT_KIS_PAPER_CANARY_EXECUTION_CONTROL,
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(
            os.environ.get(
                "THERICHER_MODEL_ARTIFACT_ROOT",
                DEFAULT_KIS_PAPER_CANARY_ARTIFACT_ROOT,
            )
        ),
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    observed_at = datetime.now(UTC)
    run_id = arguments.run_id or f"canary-{observed_at.strftime('%Y%m%dT%H%M%SZ')}"
    try:
        quantity = _positive_decimal(arguments.quantity)
        limit_price = _positive_decimal(arguments.limit_price)
        decision = KisPaperCanaryBuyDecision(
            decision_id=f"decision-{run_id}",
            symbol=arguments.symbol,
            exchange=arguments.exchange,
            quantity=quantity,
            limit_price=limit_price,
            decision_as_of=observed_at,
            valid_until=observed_at + timedelta(seconds=arguments.valid_seconds),
        )
        outcome = run_kis_paper_canary(
            decision=decision,
            run_id=run_id,
            environment=os.environ,
            state_path=arguments.state_root / f"{run_id}.json",
            runtime_projection_path=arguments.runtime_projection,
            paper_account_snapshot_path=arguments.paper_account_snapshot,
            emergency_state_path=arguments.emergency_state,
            artifact_root=arguments.artifact_root,
            repository_root=arguments.repository_root,
            execute=arguments.execute,
            cancel_after_submit=arguments.cancel_after_submit,
            execution_control_path=arguments.execution_control,
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError) as error:
        print(json.dumps({"status": "failed", "reason_code": str(error), "paper_only": True}))
        return 2
    print(json.dumps(outcome.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

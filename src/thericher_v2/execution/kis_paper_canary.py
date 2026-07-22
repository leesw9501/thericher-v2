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
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, require_utc
from thericher_v2.research.kis_paper_canary_intent import KisPaperCanaryBuyDecision

from .broker import BrokerOrderRequest
from .emergency import (
    DEFAULT_PAPER_EXECUTION_CONTROL_STATE,
    EmergencyStore,
    PaperExecutionControlStore,
)
from .kis_paper_console_bridge import paper_account_snapshot_from_kis_readonly
from .kis_paper_order_fields import map_kis_paper_us_buy_limit_order_fields
from .kis_paper_quote import (
    KIS_PAPER_US_SPY_ASKING_PRICE_PATH,
    KIS_PAPER_US_SPY_PRICE_DETAIL_PATH,
    KIS_PAPER_US_SPY_QUOTE_PATH,
    KisPaperQuoteError,
    KisPaperSpyAskingPriceProbe,
    KisPaperSpyLimitInput,
    KisPaperSpyPriceDetailProbe,
    KisPaperSpyQuote,
    build_kis_paper_spy_asking_price_request,
    build_kis_paper_spy_price_detail_request,
    build_kis_paper_spy_quote_request,
    inspect_kis_paper_spy_asking_price_response,
    inspect_kis_paper_spy_price_detail_response,
    parse_kis_paper_spy_limit_input,
    parse_kis_paper_spy_quote,
    validate_kis_paper_spy_asking_price_request,
    validate_kis_paper_spy_price_detail_request,
    validate_kis_paper_spy_quote_request,
)
from .kis_readonly import (
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
KIS_PAPER_US_CANCEL_PATH = "/uapi/overseas-stock/v1/trading/order-rvsecncl"
KIS_PAPER_US_CANCEL_TR_ID = "VTTT1004U"
KIS_PAPER_US_CCNCL_PATH = "/uapi/overseas-stock/v1/trading/inquire-ccnl"
KIS_PAPER_US_CCNCL_TR_ID = "VTTS3035R"
KIS_PAPER_US_CCNCL_MAX_PAGES = 2
KIS_PAPER_RATE_LIMIT_CODE = "EGW00201"

_RECEIPT_DECISION_ID = re.compile(r"receipt-([0-9a-f]{64})")

_PAPER_POST_HEADERS = frozenset(
    {"authorization", "appkey", "appsecret", "tr_id", "custtype", "content-type", "accept"}
)
_PAPER_GET_HEADERS = frozenset(
    {"authorization", "appkey", "appsecret", "tr_id", "custtype", "tr_cont"}
)
_CCNL_QUERY_KEYS = frozenset(
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
_READ_ONLY_RECOVERY_PHASES = frozenset(
    {"submission_started", "outcome_unknown", "cancel_started"}
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
_SAFE_REASON_CODES = frozenset(
    {
        "preview",
        "intent_expired",
        "emergency_stop_new_orders",
        "pause_buys_active",
        "matching_open_order",
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
        if self.quantity <= 0 or self.quantity != self.quantity.to_integral_value():
            raise ValueError("canary quantity must be whole shares")
        if self.limit_price <= 0:
            raise ValueError("canary limit price must be positive")
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        object.__setattr__(self, "valid_until", require_utc(self.valid_until, "valid_until"))
        if self.valid_until <= self.created_at:
            raise ValueError("canary validity is invalid")

    @property
    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, str]:
        return {
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

    @classmethod
    def from_decision(
        cls,
        decision: KisPaperCanaryBuyDecision,
        *,
        run_id: str,
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
        )

    def broker_request(self) -> BrokerOrderRequest:
        return BrokerOrderRequest(
            client_order_id=self.client_order_id,
            symbol=self.symbol,
            market="US",
            side="buy",
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
    cancel_after_submit: bool = False
    submit_upstream_code: str | None = None
    submit_response_category: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.phase not in _STATE_PHASES:
            raise ValueError("canary state phase is invalid")
        if self.reason_code not in _SAFE_REASON_CODES:
            raise ValueError("canary state reason is invalid")
        if self.broker_order_id is not None and not _raw_order_id(self.broker_order_id):
            raise ValueError("canary broker order id is invalid")
        if not isinstance(self.cancel_after_submit, bool):
            raise ValueError("canary cancellation policy is invalid")
        if (
            self.submit_upstream_code is not None
            and safe_kis_paper_upstream_code(self.submit_upstream_code)
            != self.submit_upstream_code
        ):
            raise ValueError("canary submit upstream code is invalid")
        if (
            self.submit_response_category is not None
            and self.submit_response_category not in _SAFE_SUBMIT_RESPONSE_CATEGORIES
        ):
            raise ValueError("canary submit response category is invalid")
        object.__setattr__(self, "updated_at", require_utc(self.updated_at, "updated_at"))

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
            "cancel_after_submit": self.cancel_after_submit,
            "submit_upstream_code": self.submit_upstream_code,
            "submit_response_category": self.submit_response_category,
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
            "cancel_after_submit",
            "submit_upstream_code",
            "submit_response_category",
        }
        if (
            not isinstance(payload, Mapping)
            or not expected <= set(payload) <= expected | optional
        ):
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
            )
            if payload["intent_fingerprint"] != intent.fingerprint:
                raise ValueError("fingerprint")
            return cls(
                intent=intent,
                phase=_required_text(payload["phase"]),
                updated_at=_utc_datetime(payload["updated_at"]),
                reason_code=_required_text(payload["reason_code"]),
                broker_order_id=(
                    None
                    if payload["broker_order_id"] is None
                    else _required_text(payload["broker_order_id"])
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

    def transition(
        self,
        intent: KisPaperCanaryIntent,
        *,
        expected: frozenset[str],
        phase: str,
        reason_code: str,
        now: datetime,
        broker_order_id: str | None = None,
        submit_upstream_code: str | None = None,
        submit_response_category: str | None = None,
    ) -> KisPaperCanaryState:
        with exclusive_kis_paper_canary_state_lock(self.path):
            current = self._read_unlocked()
            if current is None or current.intent != intent or current.phase not in expected:
                raise KisPaperCanaryError("state_transition_invalid")
            state = KisPaperCanaryState(
                intent=intent,
                phase=phase,
                updated_at=now,
                reason_code=reason_code,
                broker_order_id=(
                    current.broker_order_id
                    if broker_order_id is None
                    else broker_order_id
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

    def reconcile(
        self,
        state: KisPaperCanaryState,
        *,
        now: datetime,
    ) -> KisPaperCanaryReconciliation:
        try:
            access_token = self._issue_access_token()
            snapshot = KisPaperReadOnlyClient(
                config=self._config,
                transport=self._transport,
                access_token=access_token,
            ).snapshot()
            raw_order_ids = self._inquire_ccnl(access_token, now=now)
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
                order.order_reference == order_reference
                for order in snapshot.open_orders.orders
            )
        )
        matching_ccnl = bool(state.broker_order_id and state.broker_order_id in raw_order_ids)
        known = matching_open or matching_ccnl
        status: Literal["clean", "unresolved"] = "unresolved"
        if state.phase in {"intent_recorded", "rejected"}:
            status = "clean"
        elif state.phase == "cancelled" and not matching_open and not matching_ccnl:
            status = "clean"
        elif known:
            status = "clean"
        return KisPaperCanaryReconciliation(
            snapshot=snapshot,
            account_status="available",
            ccnl_row_count=len(raw_order_ids),
            matching_open_order=matching_open,
            matching_ccnl=matching_ccnl,
            status=status,
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

    def submit_buy_limit(self, intent: KisPaperCanaryIntent) -> tuple[bool, str | None]:
        body = {
            "CANO": self._config.account_number,
            "ACNT_PRDT_CD": self._config.account_product_code,
            **map_kis_paper_us_buy_limit_order_fields(
                intent.broker_request(), exchange=intent.exchange
            ),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
        }
        response = self._dispatch(
            KisHttpRequest(
                method="POST",
                url=f"{self._config.base_url}{KIS_PAPER_US_BUY_LIMIT_ORDER_PATH}",
                headers=self._post_headers(KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID),
                json_body=body,
            )
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

    def cancel_buy_order(self, intent: KisPaperCanaryIntent, *, broker_order_id: str) -> bool:
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

    def _inquire_ccnl(self, access_token: str, *, now: datetime) -> tuple[str, ...]:
        eastern_date = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
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
        order_ids: list[str] = []
        continuation = ""
        for _page in range(KIS_PAPER_US_CCNCL_MAX_PAGES):
            response = self._dispatch(
                KisHttpRequest(
                    method="GET",
                    url=f"{self._config.base_url}{KIS_PAPER_US_CCNCL_PATH}",
                    headers=self._get_headers(
                        access_token,
                        KIS_PAPER_US_CCNCL_TR_ID,
                        continuation,
                    ),
                    query=query,
                )
            )
            if response.status_code != 200:
                raise KisPaperCanaryError("ccnl_rejected")
            payload = response.payload()
            if payload.get("rt_cd") != "0":
                raise KisPaperCanaryError("ccnl_rejected")
            output = payload.get("output")
            if not isinstance(output, Sequence) or isinstance(output, (str, bytes, bytearray)):
                raise KisPaperCanaryError("ccnl_response_incomplete")
            for row in output:
                if isinstance(row, Mapping):
                    candidate = row.get("odno")
                    if isinstance(candidate, str) and _raw_order_id(candidate):
                        order_ids.append(candidate)
            next_header = _header(response.headers, "tr_cont").upper()
            if next_header not in {"M", "F"}:
                return tuple(sorted(set(order_ids)))
            next_nk = _mapping_text(payload, "ctx_area_nk200")
            next_fk = _mapping_text(payload, "ctx_area_fk200")
            if not next_nk or not next_fk:
                raise KisPaperCanaryError("ccnl_response_incomplete")
            query = {**query, "CTX_AREA_NK200": next_nk, "CTX_AREA_FK200": next_fk}
            continuation = "N"
        raise KisPaperCanaryError("ccnl_pagination_incomplete")

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

    def _dispatch(self, request: KisHttpRequest) -> KisHttpResponse:
        validate_kis_paper_canary_request(request)
        return self._transport.request(request)


def _run_kis_paper_canary(
    *,
    decision: KisPaperCanaryBuyDecision,
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
) -> KisPaperCanaryOutcome:
    """Run or recover one bounded virtual-paper canary without a retry submit path."""

    observed_at = _canary_now(now=now, clock=clock)
    state_store = KisPaperCanaryStateStore(state_path)
    requested_intent = KisPaperCanaryIntent.from_decision(decision, run_id=run_id)
    existing_state = state_store.read()
    if existing_state is not None:
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
    emergency = EmergencyStore(emergency_state_path).read()
    execution_control = PaperExecutionControlStore(execution_control_path).read()
    reconciliation = _unavailable_reconciliation()

    if not execute:
        # Preview persists the intent but never reads credentials or calls KIS.
        pass
    elif state.phase != "intent_recorded":
        state, reconciliation = _recover_existing_canary(
            state=state,
            state_store=state_store,
            environment=environment,
            transport=transport,
            observed_at=observed_at,
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
    elif execution_control.pause_buys:
        state = state_store.transition(
            intent,
            expected=frozenset({"intent_recorded"}),
            phase="intent_recorded",
            reason_code="pause_buys_active",
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
        if _matches_intent_open_order(reconciliation.snapshot, intent):
            state = state_store.transition(
                intent,
                expected=frozenset({"intent_recorded"}),
                phase="outcome_unknown",
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
                )
                try:
                    accepted, broker_order_id = client.submit_buy_limit(intent)
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


def run_kis_paper_canary(
    *,
    decision: KisPaperCanaryBuyDecision,
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
        decision = KisPaperCanaryBuyDecision(
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
        try:
            validate_kis_paper_spy_quote_request(request)
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        return
    if request.method == "GET" and parsed.path == KIS_PAPER_US_SPY_PRICE_DETAIL_PATH:
        try:
            validate_kis_paper_spy_price_detail_request(request)
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        return
    if request.method == "GET" and parsed.path == KIS_PAPER_US_SPY_ASKING_PRICE_PATH:
        try:
            validate_kis_paper_spy_asking_price_request(request)
        except KisPaperQuoteError as error:
            raise KisPaperCanaryError(error.code) from error
        return
    if request.method == "GET" and parsed.path == KIS_PAPER_US_CCNCL_PATH:
        _validate_get_headers(request, tr_id=KIS_PAPER_US_CCNCL_TR_ID)
        if request.json_body is not None or set(request.query) != _CCNL_QUERY_KEYS:
            raise KisPaperCanaryError("request_not_allowlisted")
        _validate_ccnl_query(request.query)
        return
    if request.method == "POST" and parsed.path == KIS_PAPER_US_BUY_LIMIT_ORDER_PATH:
        _validate_post_headers(request, tr_id=KIS_PAPER_US_BUY_LIMIT_ORDER_TR_ID)
        _validate_order_body(request.json_body, _BUY_LIMIT_BODY_KEYS)
        _validate_buy_limit_body(request.json_body)
        return
    if request.method == "POST" and parsed.path == KIS_PAPER_US_CANCEL_PATH:
        _validate_post_headers(request, tr_id=KIS_PAPER_US_CANCEL_TR_ID)
        _validate_order_body(request.json_body, _CANCEL_BODY_KEYS)
        _validate_cancel_body(request.json_body)
        return
    raise KisPaperCanaryError("request_not_allowlisted")


def _cancel_submitted_canary(
    *,
    client: KisPaperCanaryClient,
    state_store: KisPaperCanaryStateStore,
    state: KisPaperCanaryState,
    reconciliation: KisPaperCanaryReconciliation,
    observed_at: datetime,
) -> tuple[KisPaperCanaryState, KisPaperCanaryReconciliation]:
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
        cancelled = client.cancel_buy_order(state.intent, broker_order_id=state.broker_order_id)
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
    observed_at: datetime,
) -> tuple[KisPaperCanaryState, KisPaperCanaryReconciliation]:
    try:
        client = KisPaperCanaryClient(
            config=load_kis_paper_config_from_environment(environment),
            transport=transport or UrllibKisPaperCanaryTransport(),
        )
        reconciliation = client.reconcile(state, now=observed_at)
    except (KisPaperCanaryError, KisPaperReadOnlyError) as error:
        return state, _unavailable_reconciliation(
            reason_code=_safe_reconciliation_reason_code(error)
        )
    if (
        state.phase == "submitted"
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
            now=observed_at,
        )
    return state, reconciliation


def _matches_intent_open_order(
    snapshot: KisPaperReadOnlySnapshot | None,
    intent: KisPaperCanaryIntent,
) -> bool:
    if snapshot is None:
        return False
    return any(
        order.symbol == intent.symbol
        and order.exchange == intent.exchange
        and order.side == "buy"
        and order.remaining_quantity == intent.quantity
        and order.limit_price == intent.limit_price
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
        recorded.quantity,
        recorded.limit_price,
    )
    requested_identity = (
        requested.run_id,
        requested.client_order_id,
        requested.decision_id,
        requested.symbol,
        requested.exchange,
        requested.quantity,
        requested.limit_price,
    )
    if recorded_identity != requested_identity:
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
) -> Path:
    root = artifact_root.resolve()
    repo = repository_root.resolve()
    if not _is_permitted_artifact_root(root, repo):
        raise KisPaperCanaryError("artifact_root_inside_repository")
    destination = root / "execution" / "kis-paper-canary" / state.intent.run_id / "evidence.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kis_paper_canary_evidence",
        "paper_only": True,
        "run_id": state.intent.run_id,
        "intent_fingerprint": state.intent.fingerprint,
        "decision_ref": _redacted_decision_reference(state.intent.decision_id),
        "attribution_ref": _receipt_attribution_reference(state.intent.decision_id),
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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
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


def _validate_ccnl_query(query: Mapping[str, str]) -> None:
    if (
        not _account_number(query["CANO"])
        or not _account_product_code(query["ACNT_PRDT_CD"])
        or query["PDNO"] != ""
        or not _yyyymmdd(query["ORD_STRT_DT"])
        or query["ORD_END_DT"] != query["ORD_STRT_DT"]
        or query["SLL_BUY_DVSN"] != "00"
        or query["CCLD_NCCS_DVSN"] != "00"
        or query["OVRS_EXCG_CD"] != ""
        or query["SORT_SQN"] != "DS"
        or any(query[key] != "" for key in ("ORD_DT", "ORD_GNO_BRNO", "ODNO"))
        or not _continuation_value(query["CTX_AREA_NK200"])
        or not _continuation_value(query["CTX_AREA_FK200"])
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


def _yyyymmdd(value: str) -> bool:
    return len(value) == 8 and value.isdigit()


def _continuation_value(value: str) -> bool:
    return isinstance(value, str) and len(value) <= 256


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


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return ""


def _mapping_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise KisPaperCanaryError("ccnl_response_incomplete")
    return value


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
            now=observed_at,
            execution_control_path=arguments.execution_control,
        )
    except (KisPaperCanaryError, KisPaperReadOnlyError, ValueError) as error:
        print(json.dumps({"status": "failed", "reason_code": str(error), "paper_only": True}))
        return 2
    print(json.dumps(outcome.safe_payload(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

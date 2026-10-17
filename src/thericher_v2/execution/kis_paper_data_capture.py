"""Finite private capture sessions for current20 refresh and XLK daily context.

Data supplies exact typed queries and date bounds, then calls ``capture`` in a
context manager. One lazy native client authenticates once for both endpoints.
Results contain cache references, never prices; existing workers are unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import stat
import time
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from . import kis_market_data as market
from .kis_market_data_rate_gate import (
    KisPaperMarketDataRateGate,
    KisPaperMarketDataTokenStartGate,
    KisPaperTokenStartGateBusy,
)
from .kis_stock_intraday_foundation import FoundationOwner, atomic_json, file_ref

_MARKET_BASE = Path("D:/market_data/us_equities/kis_paper_private")
_ARTIFACT_BASE = Path("D:/thericher-v2/model-artifacts")
_REPO = Path(__file__).resolve().parents[3]
_VERSION = "kis-paper-data-capture-v1"
_MAX_BODY = 262144
_KNOWN_FAILURES = frozenset(
    {
        "transport_failure",
        "response_invalid",
        "minute_response_invalid",
        "minute_response_rejected",
        "daily_response_invalid",
        "daily_response_rejected",
        "auth_response_invalid",
        "auth_rejected",
        "rate_limited",
        "capture_response_date_scope",
        "capture_duplicate_rows",
    }
)
_PRE_WIRE_FAILURES = frozenset(
    {
        "historical_minute_past_timestamp_required",
        "historical_minute_scope_mismatch",
        "request_not_allowlisted",
        "minute_page_limit_exceeded",
        "daily_page_limit_exceeded",
        "paper_host_required",
    }
)


class KisPaperCaptureError(ValueError):
    """Categorical capture failure; never carries a provider body or credentials."""


@dataclass(frozen=True)
class CaptureQuery:
    query: (
        market.KisPaperHistoricalMinuteQuery
        | market.KisPaperDailyQuery
        | market.KisPaperDailyAdjustmentProbeQuery
    )
    first_date: str
    last_date: str

    def __post_init__(self) -> None:
        if type(self.query) not in (
            market.KisPaperHistoricalMinuteQuery,
            market.KisPaperDailyQuery,
            market.KisPaperDailyAdjustmentProbeQuery,
        ):
            raise KisPaperCaptureError("capture_typed_query_required")
        for value in (self.first_date, self.last_date):
            try:
                if not isinstance(value, str) or len(value) != 8 or not value.isascii():
                    raise ValueError
                if datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d") != value:
                    raise ValueError
            except ValueError:
                raise KisPaperCaptureError("capture_date_scope_invalid") from None
        if self.first_date > self.last_date:
            raise KisPaperCaptureError("capture_date_scope_invalid")
        key = (
            (self.query.continuation_key[:8] if self.query.continuation_key else None)
            if type(self.query) is market.KisPaperHistoricalMinuteQuery
            else self.query.by_date
        )
        if key is not None and not self.first_date <= key <= self.last_date:
            raise KisPaperCaptureError("capture_query_date_outside_scope")

    def document(self) -> dict[str, Any]:
        q = self.query
        minute = type(q) is market.KisPaperHistoricalMinuteQuery
        return dict(
            kind="minute" if minute else "daily",
            symbol=q.symbol,
            exchange=q.exchange,
            first_date=self.first_date,
            last_date=self.last_date,
            approved={k: sorted(v) for k, v in q.approved_symbol_exchanges.items()},
            parameters=(
                dict(
                    KEYB=q.continuation_key or "",
                    NEXT=q.continuation_next or "",
                    PINC="1" if q.include_previous_day else "0",
                    NMIN="1",
                )
                if minute
                else dict(BYMD=q.by_date, MODP=q.adjustment_mode, continuation=q.continuation)
            ),
        )

    @property
    def key(self) -> str:
        return hashlib.sha256(_json(self.document())).hexdigest()


@dataclass(frozen=True)
class CaptureLimits:
    max_get: int
    max_retries: int
    wall_seconds: float
    max_auth: int = 1
    request_timeout_seconds: float = 5
    request_interval_seconds: float = 2

    def __post_init__(self) -> None:
        if any(
            type(v) is not int or v < 0 for v in (self.max_get, self.max_retries, self.max_auth)
        ):
            raise KisPaperCaptureError("capture_caps_invalid")
        if self.max_get < 1 or self.max_retries > self.max_get:
            raise KisPaperCaptureError("capture_caps_invalid")
        for value in (
            self.wall_seconds,
            self.request_timeout_seconds,
            self.request_interval_seconds,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise KisPaperCaptureError("capture_caps_invalid")
        if self.request_interval_seconds < 2:
            raise KisPaperCaptureError("capture_pacing_floor")


@dataclass(frozen=True)
class CaptureReadiness:
    ready: bool
    next_due: datetime | None = None

    def __post_init__(self) -> None:
        if type(self.ready) is not bool:
            raise KisPaperCaptureError("capture_readiness_invalid")
        if self.next_due is not None:
            _utc(self.next_due)


@dataclass(frozen=True)
class CaptureResult:
    query_key: str
    status: str
    row_count: int | None = None
    raw: dict[str, str] | None = None
    native: dict[str, str] | None = None
    outcome: dict[str, str] | None = None
    reason: str | None = None
    next_due: str | None = None
    cache_hit: bool = False


class _NotReady(KisPaperCaptureError):
    pass


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("ascii")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise KisPaperCaptureError("capture_UTC_clock_required")
    return value


def _safe_path(path: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise KisPaperCaptureError("capture_reparse_path_refused")
        if not (stat.S_ISDIR(info.st_mode) or (part == path and stat.S_ISREG(info.st_mode))):
            raise KisPaperCaptureError("capture_path_invalid")
        if part == path and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise KisPaperCaptureError("capture_hardlink_refused")
    return path.resolve()


class KisPaperDataCaptureSession:
    """One finite, exclusive data-only Paper session with durable query custody.

    ``owner_ready`` is a due-aware, caller-owned probe, not a scheduler. A false
    result defers without a request; unknown next-due remains ``None``. Default
    token spacing is300. An explicitly authorized caller may name60 through
    ``token_minimum_interval_seconds``; the value is frozen in this session.
    """

    def __init__(
        self,
        *,
        queries: Sequence[CaptureQuery],
        market_root: Path,
        artifact_root: Path,
        limits: CaptureLimits,
        owner_ready: Callable[[], CaptureReadiness],
        token_minimum_interval_seconds: float = 300,
        config_loader: Callable[[], market.KisPaperMarketDataConfig] = (
            market.load_kis_paper_market_data_environment_config
        ),
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.queries = tuple(queries)
        if not self.queries or any(type(q) is not CaptureQuery for q in self.queries):
            raise KisPaperCaptureError("capture_frozen_queries_required")
        if len({q.key for q in self.queries}) != len(self.queries):
            raise KisPaperCaptureError("capture_duplicate_query")
        if type(limits) is not CaptureLimits or token_minimum_interval_seconds not in (60, 300):
            raise KisPaperCaptureError("capture_caps_invalid")
        self.market_root, self.artifact_root = _safe_path(market_root), _safe_path(artifact_root)
        for root, base in ((self.market_root, _MARKET_BASE), (self.artifact_root, _ARTIFACT_BASE)):
            if (
                not root.is_relative_to(_safe_path(base))
                or root == _safe_path(base)
                or root.is_relative_to(_REPO)
            ):
                raise KisPaperCaptureError("capture_storage_scope")
            if root.exists() and not root.is_dir():
                raise KisPaperCaptureError("capture_storage_directory_required")
        self.control_root = _safe_path(_MARKET_BASE / "collection-control-v1")
        if self.market_root.is_relative_to(self.control_root) or self.control_root.is_relative_to(
            self.market_root
        ):
            raise KisPaperCaptureError("capture_control_root_overlap")
        self.limits, self._owner_ready = limits, owner_ready
        self._token_interval = float(token_minimum_interval_seconds)
        self._loader, self._clock, self._monotonic, self._sleep = (
            config_loader,
            clock,
            monotonic,
            sleeper,
        )
        minute = [
            q.query.approved_symbol_exchanges
            for q in self.queries
            if type(q.query) is market.KisPaperHistoricalMinuteQuery
        ]
        if minute and any(q != minute[0] for q in minute):
            raise KisPaperCaptureError("capture_minute_scope_mismatch")
        self._minute_scope = minute[0] if minute else None
        daily = [
            q.query.approved_symbol_exchanges
            for q in self.queries
            if type(q.query) is not market.KisPaperHistoricalMinuteQuery
        ]
        if daily and any(q != daily[0] for q in daily):
            raise KisPaperCaptureError("capture_daily_scope_mismatch")
        self._daily_scope = daily[0] if daily else None
        self._daily_modes = frozenset(
            q.query.adjustment_mode
            for q in self.queries
            if type(q.query) is not market.KisPaperHistoricalMinuteQuery
        ) or frozenset({"0"})
        self._contract = dict(
            queries=[q.document() for q in self.queries],
            limits=asdict(limits),
            token_interval=self._token_interval,
            market_root=str(self.market_root),
            artifact_root=str(self.artifact_root),
        )
        self._stack: ExitStack | None = None
        self._owners: list[FoundationOwner] = []
        self._state: dict[str, Any] | None = None
        self._client: market.KisPaperMarketDataClient | None = None
        self._authenticated = False
        self._active: CaptureQuery | None = None
        self._retry = False
        self._raw: dict[str, str] | None = None
        self._busy = False
        self._started = 0.0
        self._carried_wall = 0.0

    def __enter__(self) -> KisPaperDataCaptureSession:
        if self._stack is not None or self._owners:
            raise KisPaperCaptureError("capture_already_entered")
        stack = ExitStack()
        self._stack = stack
        try:
            for root in (self.market_root, self.artifact_root):
                _safe_path(root)
                owner = stack.enter_context(FoundationOwner(root))
                self._owners.append(owner)
            self._started = self._monotonic()
            path = self.artifact_root / "capture-state.json"
            _safe_path(path)
            if path.exists():
                state = json.loads(path.read_bytes())
                if state["version"] != _VERSION or state["contract"] != self._contract:
                    raise KisPaperCaptureError("capture_resume_contract_mismatch")
                if state["pending"] is not None:
                    raise KisPaperCaptureError("capture_pending_unknown")
                for key, cap in (
                    ("GET", self.limits.max_get),
                    ("POST", self.limits.max_auth),
                    ("retry", self.limits.max_retries),
                ):
                    if type(state[key]) is not int or not 0 <= state[key] <= cap:
                        raise KisPaperCaptureError("capture_resume_debits_invalid")
                if (
                    not math.isfinite(state["owned_wall_seconds"])
                    or state["owned_wall_seconds"] < 0
                ):
                    raise KisPaperCaptureError("capture_resume_debits_invalid")
                _utc(datetime.fromisoformat(state["started_utc"]))
                self._carried_wall = state["owned_wall_seconds"]
                self._state = state
                self._check()
            else:
                self._state = dict(
                    version=_VERSION,
                    contract=self._contract,
                    started_utc=_utc(self._clock()).isoformat(),
                    owned_wall_seconds=0,
                    GET=0,
                    POST=0,
                    retry=0,
                    pending=None,
                    completed={},
                    failed_attempts=[],
                    next_due=None,
                    wait_reason=None,
                )
                self._commit(self._state)
        except BaseException:
            self._stack = None
            stack.close()
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        stack, self._stack = self._stack, None
        self._client = None
        if stack is not None:
            # ExitStack attempts both exact-identity releases even if one was lost.
            stack.close()

    @property
    def progress(self) -> dict[str, Any]:
        self._held()
        return copy.deepcopy(self._state)

    def _held(self) -> None:
        if len(self._owners) != 2:
            raise KisPaperCaptureError("capture_owner_required")
        for owner in self._owners:
            try:
                owner.require_held()
            except (OSError, ValueError):
                raise KisPaperCaptureError("capture_owner_lost") from None
        for root in (self.market_root, self.artifact_root, self.control_root):
            _safe_path(root)

    def _check(self, reserve: float = 0) -> float:
        self._held()
        now = _utc(self._clock())
        elapsed = max(
            self._carried_wall + self._monotonic() - self._started,
            (now - datetime.fromisoformat(self._state["started_utc"])).total_seconds(),
        )
        if elapsed + reserve >= self.limits.wall_seconds:
            raise KisPaperCaptureError("capture_wall_cap")
        return elapsed

    def _commit(self, value: dict[str, Any]) -> None:
        self._held()
        value = copy.deepcopy(value)
        value["owned_wall_seconds"] = max(
            value["owned_wall_seconds"], self._carried_wall + self._monotonic() - self._started
        )
        path = self.artifact_root / "capture-state.json"
        _safe_path(path)
        _safe_path(path.with_suffix(".json.pending"))
        if path.exists() and json.loads(path.read_bytes()) != self._state:
            raise KisPaperCaptureError("capture_persisted_state_changed")
        try:
            atomic_json(path, value)
        except OSError:
            raise KisPaperCaptureError("capture_state_storage_failure") from None
        self._state = value

    def _ready(self) -> None:
        self._check()
        fact = self._owner_ready()
        if type(fact) is not CaptureReadiness:
            raise KisPaperCaptureError("capture_readiness_invalid")
        self._held()
        if not fact.ready:
            state = copy.deepcopy(self._state)
            state.update(
                next_due=fact.next_due.isoformat() if fact.next_due else None,
                wait_reason="owner_not_ready",
            )
            self._commit(state)
            raise _NotReady("owner_not_ready")

    def _pause(self, seconds: float) -> None:
        self._check(seconds)
        state = copy.deepcopy(self._state)
        state.update(
            next_due=(_utc(self._clock()) + timedelta(seconds=seconds)).isoformat(),
            wait_reason="request_pacing",
        )
        self._commit(state)
        self._sleep(seconds)
        self._check()

    def _immutable(self, name: str, body: bytes) -> dict[str, str]:
        self._held()
        disk = shutil.disk_usage(self.market_root)
        if disk.free - len(body) < disk.total * 0.15:
            raise KisPaperCaptureError("capture_disk_floor")
        path = self.market_root / name
        _safe_path(path)
        try:
            with path.open("xb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            return file_ref(path)
        except OSError:
            raise KisPaperCaptureError("capture_immutable_storage_failure") from None

    def _begin(self, method: str) -> None:
        # The only full caller probe: after all pacing, immediately before wire.
        self._ready()
        self._check()
        persisted = json.loads((self.artifact_root / "capture-state.json").read_bytes())
        if persisted != self._state or self._state["pending"] is not None:
            raise KisPaperCaptureError("capture_pending_or_state_changed")
        state = copy.deepcopy(self._state)
        if method == "POST":
            if self._token.snapshot().last_token_request_started_at_utc != self._token.claimed_mark:
                raise KisPaperCaptureError("capture_token_start_identity_changed")
            if state["POST"] >= self.limits.max_auth:
                raise KisPaperCaptureError("capture_auth_cap")
        else:
            self._admit_GET(state)
            failures = [v for v in state["failed_attempts"] if v["query_key"] == self._active.key]
            if self._retry:
                failed = failures[-1]
                state["retry"] += 1
                failed["retried_by"] = state["GET"] + 1
        state[method] += 1
        state["pending"] = dict(
            method=method,
            ordinal=state[method],
            query_key=self._active.key if method == "GET" else None,
            started_utc=_utc(self._clock()).isoformat(),
        )
        state.update(next_due=None, wait_reason=None)
        self._commit(state)

    def _admit_GET(self, state: dict[str, Any]) -> None:
        if self._active is None or state["GET"] >= self.limits.max_get:
            raise KisPaperCaptureError("capture_GET_cap")
        failures = [v for v in state["failed_attempts"] if v["query_key"] == self._active.key]
        if self._retry:
            failed = failures[-1] if failures else None
            if (
                failed is None
                or failed["reason"] != "transport_failure"
                or failed.get("retried_by") is not None
                or failed["ordinal"] != state["GET"]
            ):
                raise KisPaperCaptureError("capture_exact_failed_attempt_required")
            if state["retry"] >= self.limits.max_retries:
                raise KisPaperCaptureError("capture_retry_cap")
            self._verify_ref(failed["outcome"])
        elif failures:
            raise KisPaperCaptureError("capture_explicit_exact_retry_required")

    def _client_once(self) -> market.KisPaperMarketDataClient:
        if self._client is not None:
            return self._client
        self._check()
        if self._state["POST"] >= self.limits.max_auth:
            raise KisPaperCaptureError("capture_auth_cap")
        config = self._loader()
        if type(config) is not market.KisPaperMarketDataConfig:
            raise KisPaperCaptureError("capture_paper_config_required")
        session = self

        class Token(KisPaperMarketDataTokenStartGate):
            claimed_mark = None

            def claim_token_request_start(self) -> bool:
                session._check()
                claimed = super().claim_token_request_start()
                if claimed:
                    self.claimed_mark = self.snapshot().last_token_request_started_at_utc
                return claimed

        token = Token(
            control_root=self.control_root,
            clock=self._clock,
            minimum_request_interval_seconds=self._token_interval,
        )
        rate = KisPaperMarketDataRateGate(
            control_root=self.control_root,
            clock=self._clock,
            sleeper=self._pause,
            minimum_request_interval_seconds=self.limits.request_interval_seconds,
        )

        class Transport(market.UrllibKisPaperMixedDataTransport):
            def request(self, request: market.KisMarketDataRequest) -> market.KisMarketDataResponse:
                session._check()
                response = super().request(request)
                session._check()
                if request.method == "GET":
                    secrets = (
                        config.app_key,
                        config.app_secret,
                        request.headers["authorization"].removeprefix("Bearer "),
                    )
                    if len(response.body) > _MAX_BODY:
                        raise KisPaperCaptureError("capture_response_size")
                    try:
                        decoded = json.dumps(json.loads(response.body), ensure_ascii=False).encode(
                            "utf-8"
                        )
                    except (UnicodeError, ValueError):
                        raise KisPaperCaptureError("capture_response_inspection_failed") from None
                    if any(
                        secret.encode() in response.body or secret.encode() in decoded
                        for secret in secrets
                    ):
                        raise KisPaperCaptureError("capture_secret_echo_refused")
                    session._raw = session._immutable(
                        f"GET-{session._state['GET']:06d}.body", response.body
                    )
                return response

        transport = Transport(
            minute_symbol_exchanges=self._minute_scope,
            daily_symbol_exchanges=self._daily_scope,
            daily_adjustment_modes=self._daily_modes,
            timeout_seconds=self.limits.request_timeout_seconds,
            request_gate=rate,
            token_start_gate=token,
        )
        delegate = transport._opener

        class Response:
            def __init__(self, response: Any) -> None:
                self.response = response
                self.status = response.code if isinstance(response, HTTPError) else response.status
                self.headers = response.headers

            def __enter__(self) -> Response:
                return self

            def __exit__(self, *_exc: object) -> None:
                self.response.close()

            def read(self) -> bytes:
                session._check()
                body = self.response.read(_MAX_BODY + 1)
                session._check()
                if len(body) > _MAX_BODY:
                    raise KisPaperCaptureError("capture_response_size")
                return body

        class Wire:
            def open(self, request: Any, timeout: float) -> Any:
                session._validate_wire(request)
                session._begin(request.get_method())
                remaining = session.limits.wall_seconds - session._check()
                try:
                    response = delegate.open(request, timeout=min(timeout, remaining))
                except HTTPError as error:
                    response = error
                return Response(response)

        transport._opener = Wire()
        self._token = token
        self._client = market.KisPaperMarketDataClient(
            config=config,
            transport=transport,
            minute_route="historical_timestamp" if self._minute_scope else "standard",
            minute_symbol_exchanges=self._minute_scope,
            allow_mixed_data=self._minute_scope is not None and self._daily_scope is not None,
            mixed_daily_symbol_exchanges=self._daily_scope
            if self._minute_scope is not None
            else None,
            max_minute_page_attempts=self.limits.max_get,
            max_daily_page_attempts=self.limits.max_get,
        )
        return self._client

    def _validate_wire(self, request: Any) -> None:
        parts = urlsplit(request.full_url)
        if (
            parts.scheme != "https"
            or parts.netloc != "openapivts.koreainvestment.com:29443"
            or parts.fragment
        ):
            raise KisPaperCaptureError("capture_paper_route_required")
        method = request.get_method()
        if method == "POST":
            if parts.path != market.KIS_PAPER_TOKEN_PATH or parts.query:
                raise KisPaperCaptureError("capture_data_route_required")
            return
        if method != "GET" or self._active is None:
            raise KisPaperCaptureError("capture_data_route_required")
        q = self._active.query
        if type(q) is market.KisPaperHistoricalMinuteQuery:
            path = market.KIS_PAPER_MINUTE_PATH
            expected = dict(
                AUTH=[""],
                SYMB=[q.symbol],
                EXCD=[q.exchange],
                NMIN=["1"],
                PINC=["1" if q.include_previous_day else "0"],
                NREC=["120"],
                FILL=[""],
                KEYB=[q.continuation_key or ""],
                NEXT=[q.continuation_next or ""],
            )
        else:
            path = market.KIS_PAPER_DAILY_PATH
            expected = dict(
                AUTH=[""],
                SYMB=[q.symbol],
                EXCD=[q.exchange],
                GUBN=["0"],
                BYMD=[q.by_date],
                MODP=[q.adjustment_mode],
            )
        if parts.path != path or parse_qs(parts.query, keep_blank_values=True) != expected:
            raise KisPaperCaptureError("capture_exact_query_required")

    def _resolve(
        self,
        status: str,
        *,
        reason: str | None = None,
        native: dict[str, str] | None = None,
        rows: int | None = None,
    ) -> CaptureResult | None:
        self._held()
        pending = self._state["pending"]
        if pending is None:
            raise KisPaperCaptureError("capture_pending_required")
        method, ordinal = pending["method"], pending["ordinal"]
        result = CaptureResult(
            query_key=self._active.key if method == "GET" else "auth",
            status=status,
            raw=self._raw if method == "GET" else None,
            native=native,
            reason=reason,
            row_count=rows,
        )
        outcome = self._immutable(f"{method}-{ordinal:06d}.outcome.json", _json(asdict(result)))
        state = copy.deepcopy(self._state)
        if method == "GET":
            result = CaptureResult(**(asdict(result) | dict(outcome=outcome)))
            if reason == "transport_failure":
                state["failed_attempts"].append(
                    dict(
                        query_key=self._active.key,
                        ordinal=ordinal,
                        reason=reason,
                        retried_by=None,
                        outcome=outcome,
                    )
                )
            else:
                state["completed"][self._active.key] = asdict(result)
        state["pending"] = None
        self._commit(state)
        return result if method == "GET" else None

    def _cached(self, query: CaptureQuery) -> CaptureResult | None:
        item = self._state["completed"].get(query.key)
        if item is None:
            return None
        for key in ("raw", "native", "outcome"):
            if item[key] is not None:
                self._verify_ref(item[key])
        return CaptureResult(**(item | dict(cache_hit=True)))

    def _verify_ref(self, ref: dict[str, str]) -> None:
        path = _safe_path(Path(ref["path"]))
        if not path.is_relative_to(self.market_root) or file_ref(path) != ref:
            raise KisPaperCaptureError("capture_cache_ref_mismatch")

    def capture(self, query: CaptureQuery, *, retry: bool = False) -> CaptureResult:
        self._held()
        if self._busy:
            raise KisPaperCaptureError("capture_reentrancy_refused")
        if type(query) is not CaptureQuery or query.document() not in self._contract["queries"]:
            raise KisPaperCaptureError("capture_query_outside_frozen_scope")
        if type(retry) is not bool:
            raise KisPaperCaptureError("capture_retry_flag_invalid")
        if self._state["pending"] is not None:
            raise KisPaperCaptureError("capture_pending_unknown")
        self._check()
        cached = self._cached(query)
        if cached is not None:
            return cached
        self._active, self._retry, self._raw, self._busy = query, retry, None, True
        try:
            self._admit_GET(self._state)
            self._check()
            client = self._client_once()
            if not self._authenticated and self._state["POST"] >= self.limits.max_auth:
                raise KisPaperCaptureError("capture_auth_cap")
            client.ensure_authenticated()
            if self._state["pending"] is not None:
                self._resolve("AUTHENTICATED")
            self._authenticated = True
            self._check()
            if type(query.query) is market.KisPaperHistoricalMinuteQuery:
                page = client.fetch_minute_page(query.query)
                documents = [v.as_document() for v in page.bars]
            else:
                page = client.fetch_daily_raw_page(query.query)
                documents = [v.as_document() for v in page.rows]
            self._check()
            dates = [v["xymd"] for v in documents]
            if any(not query.first_date <= day <= query.last_date for day in dates):
                raise market.KisPaperMarketDataError("capture_response_date_scope")
            if len(set((v["xymd"], v.get("xhms")) for v in documents)) != len(documents):
                raise market.KisPaperMarketDataError("capture_duplicate_rows")
            native = self._immutable(f"GET-{self._state['GET']:06d}.native.json", _json(documents))
            return self._resolve("ACCEPTED", native=native, rows=len(documents))
        except _NotReady:
            return CaptureResult(
                query.key, "DEFERRED", reason="owner_not_ready", next_due=self._state["next_due"]
            )
        except market.KisPaperMarketDataError as error:
            if str(error) == "token_request_not_due" and self._state["pending"] is None:
                try:
                    due = self._token.snapshot().next_token_request_not_before_utc
                except KisPaperTokenStartGateBusy:
                    due = None
                state = copy.deepcopy(self._state)
                state.update(
                    next_due=due.isoformat() if due else None, wait_reason="token_request_not_due"
                )
                self._commit(state)
                return CaptureResult(
                    query.key,
                    "DEFERRED",
                    reason="token_request_not_due",
                    next_due=state["next_due"],
                )
            if self._state["pending"] is None:
                reason = (
                    str(error)
                    if str(error) in _PRE_WIRE_FAILURES
                    else "capture_native_pre_wire_refusal"
                )
                raise KisPaperCaptureError(reason) from None
            reason = str(error) if str(error) in _KNOWN_FAILURES else "response_invalid"
            result = self._resolve("REJECTED", reason=reason)
            if result is None:
                raise KisPaperCaptureError("capture_authentication_rejected") from None
            return result
        finally:
            self._active, self._busy = None, False

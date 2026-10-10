"""Pure, injected one-page endpoint preparation; no client, IO or persistence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
)
from thericher_v2.research.cross_asset_etf_input import CrossAssetSession

MAX_PEERS = 42
_YIELDS = frozenset(
    {"auth_rejected", "auth_response_invalid", "rate_limited", "token_request_not_due"}
)
_PAGE_ERRORS = frozenset(
    {
        "page_identity_invalid",
        "page_schema_invalid",
        "future_date",
        "duplicate_date",
        "page_bounds_invalid",
        "clock_invalid",
    }
)


class EndpointInputError(ValueError):
    """Only fixed categorical messages may cross the helper boundary."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EndpointInputError(code)


def _sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pin(value: str) -> None:
    _require(
        type(value) is str and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None,
        "binding_invalid",
    )


def _utc(value: datetime) -> datetime:
    _require(
        type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None,
        "clock_invalid",
    )
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True, repr=False)
class EndpointPeer:
    key: str
    symbol: str
    exchange: str

    def __post_init__(self) -> None:
        _require(
            type(self.key) is str and 0 < len(self.key) <= 256 and self.key.isprintable(),
            "peer_identity_invalid",
        )
        _require(self.exchange == "NAS", "peer_route_invalid")
        # Use the native query grammar, not an opaque-key-to-symbol parser.
        try:
            query = KisPaperDailyQuery(
                self.symbol,
                "20261012",
                exchange=self.exchange,
                approved_symbol_exchanges={self.symbol: frozenset({"NAS"})},
            )
        except (ValueError, TypeError):
            raise EndpointInputError("peer_identity_invalid") from None
        _require(query.symbol == self.symbol, "peer_identity_invalid")


def peer_sha256(peers: tuple[EndpointPeer, ...]) -> str:
    _require(
        type(peers) is tuple and all(type(p) is EndpointPeer for p in peers),
        "peer_identity_invalid",
    )
    return _sha([{"key": p.key, "symbol": p.symbol, "exchange": p.exchange} for p in peers])


@dataclass(frozen=True, slots=True, repr=False)
class EndpointScope:
    peers: tuple[EndpointPeer, ...]
    expected_peer_sha256: str
    parent_seal_sha256: str
    session: CrossAssetSession
    past_cutoff: datetime

    def __post_init__(self) -> None:
        _pin(self.expected_peer_sha256)
        _pin(self.parent_seal_sha256)
        _require(
            type(self.peers) is tuple and 0 < len(self.peers) <= MAX_PEERS, "peer_count_invalid"
        )
        _require(peer_sha256(self.peers) == self.expected_peer_sha256, "peer_binding_invalid")
        _require(
            len({p.key for p in self.peers}) == len(self.peers)
            and len({(p.symbol, p.exchange) for p in self.peers}) == len(self.peers),
            "peer_identity_conflict",
        )
        _require(type(self.session) is CrossAssetSession, "session_invalid")
        try:
            official = us_equity_2026_session(self.session.session_date)
        except ValueError:
            raise EndpointInputError("session_invalid") from None
        _require(
            official is not None
            and official.window.open_ts == self.session.open_at
            and official.window.close_ts == self.session.close_at,
            "session_invalid",
        )
        object.__setattr__(self, "past_cutoff", _utc(self.past_cutoff))
        _require(self.past_cutoff < self.session.open_at, "past_cutoff_invalid")

    @property
    def binding_sha256(self) -> str:
        return _sha(
            {
                "peers": self.expected_peer_sha256,
                "parent": self.parent_seal_sha256,
                "session": self.session.session_date.isoformat(),
                "open": _utc(self.session.open_at).isoformat(),
                "close": _utc(self.session.close_at).isoformat(),
                "past_cutoff": self.past_cutoff.isoformat(),
            }
        )

    def query(self, position: int) -> KisPaperDailyQuery:
        peer = self.peers[position]
        return KisPaperDailyQuery(
            peer.symbol,
            self.session.session_date.strftime("%Y%m%d"),
            exchange=peer.exchange,
            approved_symbol_exchanges={p.symbol: frozenset({p.exchange}) for p in self.peers},
        )


@dataclass(frozen=True, slots=True)
class EndpointObservation:
    key: str = field(repr=False)
    status: str
    reason: str | None
    request_entered_at: datetime | None
    observed_at: datetime | None
    rows: tuple[KisPaperDailyRawRow, ...] = field(default=(), repr=False)
    endpoint_open: str | None = field(default=None, repr=False)
    canonical_rows_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class EndpointBatch:
    scope: EndpointScope = field(repr=False)
    observations: tuple[EndpointObservation, ...] = field(repr=False)
    callback_attempts: int
    next_index: int
    stop_reason: str | None

    def safe_facts(self) -> dict:
        return {
            "scope_sha256": self.scope.binding_sha256,
            "session_date": self.scope.session.session_date.isoformat(),
            "peer_count": len(self.observations),
            "available_count": sum(o.status == "available" for o in self.observations),
            "unavailable_count": sum(o.status == "input_unavailable" for o in self.observations),
            "not_attempted_count": sum(o.status == "not_attempted" for o in self.observations),
            "callback_attempts": self.callback_attempts,
            "count_semantics": "injected callback entries; not independently measured wire starts",
            "next_index": self.next_index,
            "stop_reason": self.stop_reason,
            "price_only": True,
            "pit_or_finality_claimed": False,
        }


def _validate_page(page: KisPaperDailyRawPage, query: KisPaperDailyQuery) -> tuple:
    _require(
        type(page) is KisPaperDailyRawPage and type(page.page.query) is KisPaperDailyQuery,
        "page_identity_invalid",
    )
    actual = page.page.query
    _require(
        actual == query
        and actual.approved_symbol_exchanges == query.approved_symbol_exchanges
        and actual.adjustment_mode == "0",
        "page_identity_invalid",
    )
    _require(
        type(page.rows) is tuple
        and type(page.page.row_count) is int
        and len(page.rows) == page.page.row_count <= 100,
        "page_schema_invalid",
    )
    days = []
    documents = []
    for row in page.rows:
        _require(type(row) is KisPaperDailyRawRow, "page_schema_invalid")
        try:
            checked = KisPaperDailyRawRow(**row.as_document())
            day = datetime.strptime(checked.xymd, "%Y%m%d").date()
        except (ValueError, TypeError, KisPaperMarketDataError):
            raise EndpointInputError("page_schema_invalid") from None
        _require(day <= datetime.strptime(query.by_date, "%Y%m%d").date(), "future_date")
        _require(day not in days, "duplicate_date")
        days.append(day)
        documents.append(checked.as_document())
    newest = max(days).strftime("%Y%m%d") if days else None
    oldest = min(days).strftime("%Y%m%d") if days else None
    _require(
        page.page.newest_date == newest and page.page.oldest_date == oldest, "page_bounds_invalid"
    )
    _require(not days or page.page.required_ohlcv_fields_present is True, "page_schema_invalid")
    selected = next((r for r in page.rows if r.xymd == query.by_date), None)
    return selected, _sha(documents)


def collect_endpoints(
    scope: EndpointScope,
    *,
    fetch_daily_raw_page: Callable,
    clock: Callable[[], datetime],
    start_index: int = 0,
    max_attempts: int | None = None,
) -> EndpointBatch:
    """One callback per peer; the caller persists evidence and owns restart state."""
    _require(type(scope) is EndpointScope, "scope_invalid")
    _require(type(start_index) is int and 0 <= start_index <= len(scope.peers), "cursor_invalid")
    limit = len(scope.peers) - start_index if max_attempts is None else max_attempts
    _require(type(limit) is int and 0 <= limit <= MAX_PEERS, "attempt_budget_invalid")
    _require(callable(fetch_daily_raw_page) and callable(clock), "callback_invalid")
    observations = [
        EndpointObservation(p.key, "not_attempted", None, None, None) for p in scope.peers
    ]
    attempts, position, stop = 0, start_index, None
    while position < len(scope.peers) and attempts < limit:
        entered = _utc(clock())
        if entered < scope.session.close_at:
            stop = "endpoint_not_completed"
            break
        query = scope.query(position)
        attempts += 1
        peer = scope.peers[position]
        try:
            page = fetch_daily_raw_page(query)
            observed = _utc(clock())
            _require(observed >= entered and observed >= scope.session.close_at, "clock_invalid")
            selected, digest = _validate_page(page, query)
            reason = None if selected is not None else "endpoint_missing"
            observations[position] = EndpointObservation(
                peer.key,
                "available" if selected is not None else "input_unavailable",
                reason,
                entered,
                observed,
                page.rows,
                selected.open if selected is not None else None,
                digest,
            )
        except Exception as error:
            if type(error) is EndpointInputError and str(error) in _PAGE_ERRORS:
                reason = str(error)
            elif type(error) is KisPaperMarketDataError and str(error) in _YIELDS:
                reason = str(error)
            else:
                reason = "provider_unavailable"
            observations[position] = EndpointObservation(
                peer.key,
                "input_unavailable",
                reason,
                entered,
                None,
            )
            if reason in _YIELDS or reason in {"provider_unavailable", "clock_invalid"}:
                stop = reason
                break
        position += 1
    return EndpointBatch(scope, tuple(observations), attempts, position, stop)


@dataclass(frozen=True, slots=True)
class PairEndpointMask:
    keys: tuple[str, ...] = field(repr=False)
    complete_by_peer: tuple[bool, ...] = field(repr=False)

    @property
    def target_complete(self) -> bool:
        return all(self.complete_by_peer)

    def safe_facts(self) -> dict:
        return {
            "peer_count": len(self.keys),
            "complete_peer_count": sum(self.complete_by_peer),
            "target_complete": self.target_complete,
            "returns_calculated": False,
        }


def pair_endpoint_mask(entry: EndpointBatch, exit: EndpointBatch) -> PairEndpointMask:
    _require(type(entry) is EndpointBatch and type(exit) is EndpointBatch, "pair_binding_invalid")
    _require(
        entry.scope.peers == exit.scope.peers
        and entry.scope.parent_seal_sha256 == exit.scope.parent_seal_sha256
        and entry.scope.past_cutoff == exit.scope.past_cutoff
        and entry.scope.session.session_date < exit.scope.session.session_date,
        "pair_binding_invalid",
    )
    keys = tuple(p.key for p in entry.scope.peers)
    _require(
        tuple(o.key for o in entry.observations) == keys
        and tuple(o.key for o in exit.observations) == keys,
        "pair_binding_invalid",
    )
    return PairEndpointMask(
        keys,
        tuple(
            a.status == b.status == "available"
            for a, b in zip(entry.observations, exit.observations, strict=True)
        ),
    )

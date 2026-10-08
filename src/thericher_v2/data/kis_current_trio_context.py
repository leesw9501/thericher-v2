"""Pure current Paper OC selection; caller owns actual collection and byte custody.

The active calendar is the existing source-backed 2026 session calendar. Local
request/receipt times are caller attestations, not provider publication times.
No historical cohort, IO, price adjustment, return calculation or client is used.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from thericher_v2.data.kis_daily_price_endpoints import (
    VERSION as ENDPOINT_VERSION,
)
from thericher_v2.data.kis_daily_price_endpoints import (
    KisDailyEndpointPage,
)
from thericher_v2.data.us_equity_session import UsEquity2026Session, us_equity_2026_session
from thericher_v2.execution.kis_market_data import KisPaperDailyQuery, KisPaperMarketDataError

VERSION = "kis-current-trio-context-v1"
INSTRUMENT_ORDER = ("SPY", "TLT", "GLD")
_VENUES = ("AMS", "NAS", "AMS")
_REASONS = frozenset(
    {
        "calendar_invalid",
        "decision_not_in_entry_session",
        "collection_binding_invalid",
        "collection_time_invalid",
        "source_symbols_invalid",
        "page_invalid",
        "page_identity_mismatch",
        "page_hash_mismatch",
        "required_session_missing",
        "required_close_invalid",
    }
)


class KisCurrentTrioInputUnavailable(ValueError):
    """A categorical failure of this consumer's input, never a global hold."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = (
            reason_code if type(reason_code) is str and reason_code in _REASONS else "page_invalid"
        )
        super().__init__(self.reason_code)

    def safe_facts(self) -> dict[str, str]:
        return {"status": "input_unavailable", "reason_code": self.reason_code}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise KisCurrentTrioInputUnavailable(reason)


def _utc(value: object) -> bool:
    return type(value) is datetime and value.utcoffset() == timedelta(0)


def _hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(c in "0123456789abcdef" for c in value[7:])
    )


def _digest(document: object) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _query_document(query: KisPaperDailyQuery) -> dict[str, object]:
    return dict(
        symbol=query.symbol,
        exchange=query.exchange,
        BYMD=query.by_date,
        GUBN="0",
        MODP=query.adjustment_mode,
        continuation=query.continuation,
    )


def current_trio_page_sha256(page: KisDailyEndpointPage) -> str:
    """Bind all typed OC values, warnings and duplicate fingerprints, not raw bytes.

    The caller separately verifies the raw body hash and immutable receipt. This
    pure helper cannot prove a response was actually read at an attested time.
    """
    _require(type(page) is KisDailyEndpointPage, "page_invalid")
    try:
        page.__post_init__()
    except (KisPaperMarketDataError, ValueError, TypeError, AttributeError):
        raise KisCurrentTrioInputUnavailable("page_invalid") from None
    return _digest(
        dict(
            kind=ENDPOINT_VERSION,
            query=_query_document(page.query),
            rows=[row.as_document() for row in page.rows],
            source_row_count=page.source_row_count,
            duplicate_row_count=page.duplicate_row_count,
            source_body_sha256=page.source_body_sha256,
            continuation=page.continuation,
            source_row_fingerprints=page.source_row_fingerprints,
        )
    )


@dataclass(frozen=True, slots=True)
class KisCurrentTrioPageBinding:
    collection_ref: str
    query: KisPaperDailyQuery
    source_body_sha256: str
    typed_page_sha256: str
    request_started_at: datetime
    observed_at: datetime
    source_kind: str = ENDPOINT_VERSION
    gubn: str = "0"
    modp: str = "0"

    def __post_init__(self) -> None:
        _require(
            all(
                _hash(v)
                for v in (self.collection_ref, self.source_body_sha256, self.typed_page_sha256)
            )
            and type(self.query) is KisPaperDailyQuery
            and self.source_kind == ENDPOINT_VERSION
            and self.gubn == self.modp == "0",
            "collection_binding_invalid",
        )
        _require(
            _utc(self.request_started_at)
            and _utc(self.observed_at)
            and self.request_started_at <= self.observed_at,
            "collection_time_invalid",
        )


@dataclass(frozen=True, slots=True)
class KisCurrentTrioCollectionBinding:
    collection_ref: str
    started_at: datetime
    completed_at: datetime
    pages: tuple[KisCurrentTrioPageBinding, ...]

    def __post_init__(self) -> None:
        _require(
            _hash(self.collection_ref)
            and type(self.pages) is tuple
            and len(self.pages) == 3
            and all(type(p) is KisCurrentTrioPageBinding for p in self.pages),
            "collection_binding_invalid",
        )
        _require(
            _utc(self.started_at)
            and _utc(self.completed_at)
            and self.started_at <= self.completed_at,
            "collection_time_invalid",
        )
        for page, symbol, venue in zip(self.pages, INSTRUMENT_ORDER, _VENUES, strict=True):
            page.__post_init__()
            _require(
                page.collection_ref == self.collection_ref
                and page.query.symbol == symbol
                and page.query.exchange == venue
                and page.query.continuation is None,
                "collection_binding_invalid",
            )
            _require(
                self.started_at <= page.request_started_at <= page.observed_at <= self.completed_at,
                "collection_time_invalid",
            )
        _require(
            all(
                a.observed_at <= b.request_started_at
                for a, b in zip(self.pages, self.pages[1:], strict=False)
            ),
            "collection_time_invalid",
        )


@dataclass(frozen=True, slots=True)
class KisCurrentTrioContext:
    session_dates: tuple[date, ...]
    closes: tuple[tuple[Decimal, ...], ...] = field(repr=False)
    decision_at: datetime
    entry_at: datetime
    feature_cutoff: datetime
    collection_ref: str
    observed_at_by_symbol: tuple[datetime, ...]
    collection_completed_at: datetime
    context_sha256: str
    source_body_sha256_by_symbol: tuple[str, ...]
    typed_page_sha256_by_symbol: tuple[str, ...]
    source_row_counts: tuple[int, ...]
    duplicate_row_counts: tuple[int, ...]

    def safe_facts(self) -> dict[str, object]:
        return dict(
            kind=VERSION,
            status="ready",
            instrument_order=INSTRUMENT_ORDER,
            collection_ref=self.collection_ref,
            context_sha256=self.context_sha256,
            required_closes_per_symbol=64,
            return_intervals_per_symbol=63,
            source_row_counts=self.source_row_counts,
            duplicate_row_counts=self.duplicate_row_counts,
            source_body_sha256_by_symbol=self.source_body_sha256_by_symbol,
            typed_page_sha256_by_symbol=self.typed_page_sha256_by_symbol,
            source_grade="price_only",
            MODP="0_opaque",
            corporate_actions="not_applied_or_qualified",
            point_in_time="not_claimed",
            provider_publication_at="not_observed",
            finality="not_observed",
            source_datetime="scheduled_session_close_not_provider_publication",
            availability="caller_attested_local_receipt_before_decision_only",
            raw_byte_custody="caller_owned_not_verified_by_pure_selector",
        )


def _history(
    scheduled_history: tuple[UsEquity2026Session, ...],
    entry_session: UsEquity2026Session,
) -> tuple[date, ...]:
    _require(
        type(scheduled_history) is tuple
        and len(scheduled_history) == 64
        and type(entry_session) is UsEquity2026Session
        and all(type(s) is UsEquity2026Session for s in scheduled_history),
        "calendar_invalid",
    )
    try:
        _require(
            type(entry_session.session_date) is date
            and entry_session == us_equity_2026_session(entry_session.session_date),
            "calendar_invalid",
        )
        expected = []
        day = entry_session.session_date
        while len(expected) < 64:
            day -= timedelta(days=1)
            session = us_equity_2026_session(day)
            if session is not None:
                expected.append(session)
        _require(scheduled_history == tuple(reversed(expected)), "calendar_invalid")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise KisCurrentTrioInputUnavailable("calendar_invalid") from None
    return tuple(s.session_date for s in scheduled_history)


def prepare_current_trio_context(
    pages_by_symbol: Mapping[str, KisDailyEndpointPage],
    *,
    scheduled_history: tuple[UsEquity2026Session, ...],
    entry_session: UsEquity2026Session,
    decision_at: datetime,
    collection_binding: KisCurrentTrioCollectionBinding,
) -> KisCurrentTrioContext:
    """Select exactly64 prior CLOSEs for a current, intraday three-symbol cycle.

    Binding refs name the caller's exact fresh receipt, never the frozen research
    cohort. Every symbol uses one entire validated page; no row grafting occurs.
    """
    dates = _history(scheduled_history, entry_session)
    cutoff = scheduled_history[-1].window.close_ts
    _require(
        _utc(decision_at)
        and entry_session.window.open_ts <= decision_at < entry_session.window.close_ts,
        "decision_not_in_entry_session",
    )
    _require(
        type(collection_binding) is KisCurrentTrioCollectionBinding, "collection_binding_invalid"
    )
    collection_binding.__post_init__()
    _require(
        cutoff <= collection_binding.started_at and collection_binding.completed_at <= decision_at,
        "collection_time_invalid",
    )
    _require(
        isinstance(pages_by_symbol, Mapping) and set(pages_by_symbol) == set(INSTRUMENT_ORDER),
        "source_symbols_invalid",
    )
    anchor = dates[-1].strftime("%Y%m%d")
    closes, hashes, counts, duplicates = [], [], [], []
    for symbol, venue, binding in zip(
        INSTRUMENT_ORDER, _VENUES, collection_binding.pages, strict=True
    ):
        page = pages_by_symbol[symbol]
        digest = current_trio_page_sha256(page)
        _require(
            page.query == binding.query
            and page.query.symbol == symbol
            and page.query.exchange == venue
            and page.query.by_date == anchor
            and page.query.continuation is None
            and page.query.adjustment_mode == "0",
            "page_identity_mismatch",
        )
        _require(
            page.source_body_sha256 == binding.source_body_sha256
            and digest == binding.typed_page_sha256,
            "page_hash_mismatch",
        )
        by_date = {row.session_date: row for row in page.rows}
        _require(all(day.isoformat() in by_date for day in dates), "required_session_missing")
        selected = tuple(Decimal(by_date[day.isoformat()].close) for day in dates)
        _require(all(c.is_finite() and c > 0 for c in selected), "required_close_invalid")
        _require(digest == current_trio_page_sha256(page), "page_hash_mismatch")
        closes.append(selected)
        hashes.append(digest)
        counts.append(page.source_row_count)
        duplicates.append(page.duplicate_row_count)
    observed = tuple(p.observed_at for p in collection_binding.pages)
    identity = _digest(
        dict(
            kind=VERSION,
            collection_ref=collection_binding.collection_ref,
            source_body_sha256=[p.source_body_sha256 for p in collection_binding.pages],
            typed_page_sha256=hashes,
            dates=[day.isoformat() for day in dates],
            closes=[[str(c) for c in channel] for channel in closes],
            feature_cutoff=cutoff.isoformat(),
            decision_at=decision_at.isoformat(),
            entry_at=entry_session.window.open_ts.isoformat(),
            collection_started_at=collection_binding.started_at.isoformat(),
            collection_completed_at=collection_binding.completed_at.isoformat(),
            requests=[p.request_started_at.isoformat() for p in collection_binding.pages],
            observed=[t.isoformat() for t in observed],
        )
    )
    return KisCurrentTrioContext(
        dates,
        tuple(closes),
        decision_at,
        entry_session.window.open_ts,
        cutoff,
        collection_binding.collection_ref,
        observed,
        collection_binding.completed_at,
        identity,
        tuple(p.source_body_sha256 for p in collection_binding.pages),
        tuple(hashes),
        tuple(counts),
        tuple(duplicates),
    )

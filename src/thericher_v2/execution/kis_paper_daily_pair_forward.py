"""Bounded KIS Paper current-D1 collection for the QQQ/SPY forward cache."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
    KisPaperDailyPairForwardCacheError,
    KisPaperDailyPairForwardRow,
    KisPaperDailyPairForwardRun,
    commit_kis_paper_daily_pair_forward_observation,
    retain_kis_paper_daily_pair_forward_page,
    sanitize_kis_paper_daily_pair_forward_failure_reason,
)

from . import kis_market_data
from .kis_market_data import (
    KIS_PAPER_DAILY_PATH,
    KIS_PAPER_DAILY_TR_ID,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperMarketDataError,
)
from .kis_paper_daily_history import UrllibKisPaperDailyHistoryTransport
from .kis_paper_daily_nas_forward import latest_completed_us_equity_d1_session


class KisPaperDailyPairForwardError(RuntimeError):
    """A structural current-D1 pair forward collection failure."""


class KisPaperDailyPairForwardClient(Protocol):
    """The sole credentialed capability required by this collector."""

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage: ...


class UrllibKisPaperDailyPairForwardTransport(UrllibKisPaperDailyHistoryTransport):
    """Allow only virtual Paper daily requests for QQQ/NAS and SPY/AMS."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._daily_symbol_exchanges = _SYMBOL_EXCHANGES


_SYMBOL_EXCHANGES: Mapping[str, frozenset[str]] = {
    symbol: frozenset({exchange})
    for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
}


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardObservation:
    """One uncommitted, source-scoped QQQ/SPY D1 collection result."""

    rows_by_target: Mapping[str, tuple[KisPaperDailyPairForwardRow, ...]]
    failure_reasons_by_target: Mapping[str, str]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class KisPaperDailyPairForwardRetainedObservation(KisPaperDailyPairForwardObservation):
    """Opt-in metadata only; the legacy observation's fields/serialization stay unchanged."""

    retained_pages: Mapping[str, Mapping[str, str]]


def collect_kis_paper_daily_pair_forward_once(
    client: KisPaperDailyPairForwardClient,
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    repository_root: Path | str,
    frozen_boundary: date = KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    observed_at: datetime | None = None,
    retain_observations: bool = False,
) -> KisPaperDailyPairForwardRun:
    """Fetch one page per fixed pair target and retain completed later sessions only."""

    retention = {}
    if type(retain_observations) is not bool:
        raise ValueError("pair observation opt-in is invalid")
    if retain_observations:
        retention = {
            "observation_root": Path(cache_root) / "observations-v1",
            "repository_root": repository_root,
        }
    observation = collect_kis_paper_daily_pair_forward_observation(
        client,
        frozen_boundary=frozen_boundary,
        observed_at=observed_at,
        **retention,
    )
    return commit_kis_paper_daily_pair_forward_observation(
        rows_by_target=observation.rows_by_target,
        failure_reasons_by_target=observation.failure_reasons_by_target,
        cache_root=cache_root,
        repo_root=repository_root,
        frozen_boundary=frozen_boundary,
        observed_at=observation.observed_at,
    )


def collect_kis_paper_daily_pair_forward_observation(
    client: KisPaperDailyPairForwardClient,
    *,
    frozen_boundary: date = KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    observed_at: datetime | None = None,
    observation_root: Path | str | None = None,
    repository_root: Path | str | None = None,
    capture_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> KisPaperDailyPairForwardObservation:
    """Fetch one fixed-target observation without touching the durable cache."""

    if type(frozen_boundary) is not date:
        raise ValueError("pair forward boundary is invalid")
    observed = _require_utc(observed_at or datetime.now(UTC))
    eligible_through = latest_completed_us_equity_d1_session(observed)
    target_keys = tuple(
        _target_key(symbol, exchange)
        for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS
    )
    if eligible_through is None:
        if observation_root is not None:
            return KisPaperDailyPairForwardRetainedObservation(
                rows_by_target={key: () for key in target_keys},
                failure_reasons_by_target={}, observed_at=observed, retained_pages={},
            )
        return KisPaperDailyPairForwardObservation(
            rows_by_target={key: () for key in target_keys},
            failure_reasons_by_target={},
            observed_at=observed,
        )

    anchor = eligible_through.strftime("%Y%m%d")
    rows_by_target: dict[str, tuple[KisPaperDailyPairForwardRow, ...]] = {}
    failures: dict[str, str] = {}
    retained_pages: dict[str, Mapping[str, str]] = {}
    for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS:
        target_key = _target_key(symbol, exchange)
        try:
            query = KisPaperDailyQuery(
                symbol=symbol,
                exchange=exchange,
                by_date=anchor,
                approved_symbol_exchanges=_SYMBOL_EXCHANGES,
            )
            page = client.fetch_daily_raw_page(query)
            if observation_root is not None:
                # Retention is opt-in and precedes all canonical merge/publication.
                # A failed retention aborts the invocation, not just this target's merge.
                retained_pages[target_key] = _retain_whole_page(
                    page, query=query, observation_root=observation_root,
                    repository_root=repository_root, captured_at=capture_clock(),
                )
            rows_by_target[target_key] = _completed_forward_rows(
                page,
                symbol=symbol,
                exchange=exchange,
                eligible_through=eligible_through,
                frozen_boundary=frozen_boundary,
            )
        except (KisPaperDailyPairForwardError, KisPaperMarketDataError, ValueError) as error:
            failures[target_key] = sanitize_kis_paper_daily_pair_forward_failure_reason(error)
    if observation_root is not None:
        return KisPaperDailyPairForwardRetainedObservation(
            rows_by_target=rows_by_target, failure_reasons_by_target=failures,
            observed_at=observed, retained_pages=retained_pages,
        )
    return KisPaperDailyPairForwardObservation(
        rows_by_target=rows_by_target,
        failure_reasons_by_target=failures,
        observed_at=observed,
    )


def _retain_whole_page(
    page: KisPaperDailyRawPage, *, query: KisPaperDailyQuery,
    observation_root: Path | str, repository_root: Path | str | None,
    captured_at: datetime,
) -> Mapping[str, str]:
    try:
        if (
            type(page.page.query) is not KisPaperDailyQuery or page.page.query != query
            or not page.page.required_ohlcv_fields_present
        ):
            raise ValueError
        rows = tuple(
            KisPaperDailyPairForwardRow(
                symbol=query.symbol, exchange=query.exchange, session_date=_compact_date(raw.xymd),
                open=Decimal(raw.open), high=Decimal(raw.high), low=Decimal(raw.low),
                close=Decimal(raw.clos), volume=Decimal(raw.tvol),
            )
            for raw in page.rows
        )
        if rows and (
            page.page.newest_date != max(raw.xymd for raw in page.rows)
            or page.page.oldest_date != min(raw.xymd for raw in page.rows)
        ):
            raise ValueError
        return retain_kis_paper_daily_pair_forward_page(
            rows=rows, query=_public_query_envelope(query), captured_at=captured_at,
            observation_root=observation_root, repo_root=repository_root,
        )
    except (KisPaperDailyPairForwardCacheError, OSError, ValueError) as error:
        raise KisPaperDailyPairForwardCacheError("pair whole-page retention failed") from error


def _public_query_envelope(query: KisPaperDailyQuery) -> dict[str, str]:
    """Copy only actual non-auth request fields; never inspect a request's headers."""

    return {
        "endpoint": KIS_PAPER_DAILY_PATH,
        "tr_id": KIS_PAPER_DAILY_TR_ID,
        "SYMB": query.symbol,
        "EXCD": query.exchange,
        "GUBN": "0",
        "BYMD": query.by_date,
        "MODP": query.adjustment_mode,
        "continuation": query.continuation or "",
        "collector_source_sha256": "sha256:" + hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "request_source_sha256": "sha256:" + hashlib.sha256(
            Path(kis_market_data.__file__).read_bytes()
        ).hexdigest(),
    }


def _completed_forward_rows(
    page: KisPaperDailyRawPage,
    *,
    symbol: str,
    exchange: str,
    eligible_through: date,
    frozen_boundary: date,
) -> tuple[KisPaperDailyPairForwardRow, ...]:
    by_session: dict[date, KisPaperDailyPairForwardRow] = {}
    for raw in page.rows:
        session = _compact_date(raw.xymd)
        if session > eligible_through or session <= frozen_boundary:
            continue
        row = KisPaperDailyPairForwardRow(
            symbol=symbol,
            exchange=exchange,
            session_date=session,
            open=Decimal(raw.open),
            high=Decimal(raw.high),
            low=Decimal(raw.low),
            close=Decimal(raw.clos),
            volume=Decimal(raw.tvol),
        )
        prior = by_session.get(session)
        if prior is not None and prior != row:
            raise KisPaperDailyPairForwardError("daily_duplicate_conflict")
        by_session[session] = row
    return tuple(by_session[session] for session in sorted(by_session))


def _compact_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise KisPaperDailyPairForwardError("daily_response_invalid") from error


def _target_key(symbol: str, exchange: str) -> str:
    return f"{symbol}/{exchange}"


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("pair forward clock must return UTC")
    return value.astimezone(UTC)

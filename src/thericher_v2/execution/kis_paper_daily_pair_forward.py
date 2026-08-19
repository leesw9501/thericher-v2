"""Bounded KIS Paper current-D1 collection for the QQQ/SPY forward cache."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from thericher_v2.data.kis_paper_daily_pair_forward_cache import (
    KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS,
    KisPaperDailyPairForwardRow,
    KisPaperDailyPairForwardRun,
    commit_kis_paper_daily_pair_forward_observation,
    sanitize_kis_paper_daily_pair_forward_failure_reason,
)

from .kis_market_data import KisPaperDailyQuery, KisPaperDailyRawPage, KisPaperMarketDataError
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


def collect_kis_paper_daily_pair_forward_once(
    client: KisPaperDailyPairForwardClient,
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_PAIR_FORWARD_CACHE_ROOT,
    repository_root: Path | str,
    frozen_boundary: date = KIS_PAPER_DAILY_PAIR_FORWARD_FROZEN_BOUNDARY,
    observed_at: datetime | None = None,
) -> KisPaperDailyPairForwardRun:
    """Fetch one page per fixed pair target and retain completed later sessions only."""

    observation = collect_kis_paper_daily_pair_forward_observation(
        client,
        frozen_boundary=frozen_boundary,
        observed_at=observed_at,
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
        return KisPaperDailyPairForwardObservation(
            rows_by_target={key: () for key in target_keys},
            failure_reasons_by_target={},
            observed_at=observed,
        )

    anchor = eligible_through.strftime("%Y%m%d")
    rows_by_target: dict[str, tuple[KisPaperDailyPairForwardRow, ...]] = {}
    failures: dict[str, str] = {}
    for symbol, exchange in KIS_PAPER_DAILY_PAIR_FORWARD_TARGETS:
        target_key = _target_key(symbol, exchange)
        try:
            page = client.fetch_daily_raw_page(
                KisPaperDailyQuery(
                    symbol=symbol,
                    exchange=exchange,
                    by_date=anchor,
                    approved_symbol_exchanges=_SYMBOL_EXCHANGES,
                )
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
    return KisPaperDailyPairForwardObservation(
        rows_by_target=rows_by_target,
        failure_reasons_by_target=failures,
        observed_at=observed,
    )


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

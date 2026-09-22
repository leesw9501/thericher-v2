"""Bounded KIS Paper current-D1 collection for the separate NAS forward cache."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ROOT,
    KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY,
    KisPaperDailyNasForwardRow,
    KisPaperDailyNasForwardRun,
    commit_kis_paper_daily_nas_forward_observation,
    kis_paper_daily_nas_forward_failure_context,
    sanitize_kis_paper_daily_nas_forward_failure_reason,
)
from thericher_v2.data.official_symbol_directory_nas_probe import NAS_EXCHANGE
from thericher_v2.data.us_equity_session import US_EQUITY_EASTERN, us_equity_2026_session

from .kis_market_data import (
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperMarketDataError,
)
from .kis_paper_daily_history import UrllibKisPaperDailyHistoryTransport


class KisPaperDailyNasForwardError(RuntimeError):
    """A structural current-D1 forward-collection failure."""


class KisPaperDailyNasForwardClient(Protocol):
    """The sole credentialed capability required by this collector."""

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage: ...


class UrllibKisPaperDailyNasForwardTransport(UrllibKisPaperDailyHistoryTransport):
    """Keep the forward cache on the existing fixed six-symbol daily allowlist."""


_SYMBOL_EXCHANGES: Mapping[str, frozenset[str]] = {
    symbol: frozenset({NAS_EXCHANGE}) for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
}


def collect_kis_paper_daily_nas_forward_once(
    client: KisPaperDailyNasForwardClient,
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_NAS_FORWARD_CACHE_ROOT,
    repository_root: Path | str,
    frozen_boundary: date = KIS_PAPER_DAILY_NAS_FORWARD_FROZEN_BOUNDARY,
    observed_at: datetime | None = None,
) -> KisPaperDailyNasForwardRun:
    """Fetch one page per fixed NAS symbol and retain only completed later D1 rows."""

    if type(frozen_boundary) is not date:
        raise ValueError("NAS forward boundary is invalid")
    observed = _require_utc(observed_at or datetime.now(UTC))
    eligible_through = latest_completed_us_equity_d1_session(observed)
    if eligible_through is None:
        return commit_kis_paper_daily_nas_forward_observation(
            rows_by_symbol={symbol: () for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS},
            failure_reasons_by_symbol={},
            cache_root=cache_root,
            repo_root=repository_root,
            frozen_boundary=frozen_boundary,
            observed_at=observed,
        )

    anchor = eligible_through.strftime("%Y%m%d")
    rows_by_symbol: dict[str, tuple[KisPaperDailyNasForwardRow, ...]] = {}
    failures: dict[str, str] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        try:
            with kis_paper_daily_nas_forward_failure_context("target_fetch", symbol=symbol):
                page = client.fetch_daily_raw_page(
                    KisPaperDailyQuery(
                        symbol=symbol,
                        exchange=NAS_EXCHANGE,
                        by_date=anchor,
                        approved_symbol_exchanges=_SYMBOL_EXCHANGES,
                    )
                )
                rows_by_symbol[symbol] = _completed_forward_rows(
                    page,
                    symbol=symbol,
                    eligible_through=eligible_through,
                    frozen_boundary=frozen_boundary,
                )
        except (KisPaperMarketDataError, KisPaperDailyNasForwardError, ValueError) as error:
            failures[symbol] = sanitize_kis_paper_daily_nas_forward_failure_reason(error)
    return commit_kis_paper_daily_nas_forward_observation(
        rows_by_symbol=rows_by_symbol,
        failure_reasons_by_symbol=failures,
        cache_root=cache_root,
        repo_root=repository_root,
        frozen_boundary=frozen_boundary,
        observed_at=observed,
    )


def _completed_forward_rows(
    page: KisPaperDailyRawPage,
    *,
    symbol: str,
    eligible_through: date,
    frozen_boundary: date,
) -> tuple[KisPaperDailyNasForwardRow, ...]:
    by_session: dict[date, KisPaperDailyNasForwardRow] = {}
    for raw in page.rows:
        session = _compact_date(raw.xymd)
        if session > eligible_through or session <= frozen_boundary:
            continue
        row = KisPaperDailyNasForwardRow(
            symbol=symbol,
            session_date=session,
            open=Decimal(raw.open),
            high=Decimal(raw.high),
            low=Decimal(raw.low),
            close=Decimal(raw.clos),
            volume=Decimal(raw.tvol),
        )
        prior = by_session.get(session)
        if prior is not None and prior != row:
            raise KisPaperDailyNasForwardError("daily_duplicate_conflict")
        by_session[session] = row
    return tuple(by_session[session] for session in sorted(by_session))


def latest_completed_us_equity_d1_session(observed_at: datetime) -> date | None:
    """Return the latest 2026 US equity session whose actual close has passed."""

    observed = _require_utc(observed_at)
    current_eastern_date = observed.astimezone(US_EQUITY_EASTERN).date()
    for offset in range(0, 8):
        try:
            session = us_equity_2026_session(current_eastern_date - timedelta(days=offset))
        except ValueError:
            return None
        if session is not None and session.window.close_ts <= observed:
            return session.session_date
    return None


def _compact_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as error:
        raise KisPaperDailyNasForwardError("daily_response_invalid") from error


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("NAS forward clock must return UTC")
    return value.astimezone(UTC)

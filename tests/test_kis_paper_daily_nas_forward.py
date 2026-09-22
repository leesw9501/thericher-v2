from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from thericher_v2.data.kis_paper_daily_history_panel import KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
from thericher_v2.data.kis_paper_daily_nas_forward_cache import (
    get_kis_paper_daily_nas_forward_failure_details,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperDailyPage,
    KisPaperDailyQuery,
    KisPaperDailyRawPage,
    KisPaperDailyRawRow,
    KisPaperMarketDataError,
)
from thericher_v2.execution.kis_paper_daily_nas_forward import (
    collect_kis_paper_daily_nas_forward_once,
    latest_completed_us_equity_d1_session,
)


def test_collects_only_prior_completed_rows_for_exact_fixed_nas_scope(tmp_path: Path) -> None:
    client = _Client()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    run = collect_kis_paper_daily_nas_forward_once(
        client,
        cache_root=tmp_path / "external" / "forward",
        repository_root=repo_root,
        observed_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    assert run.status == "ready"
    assert tuple(query.symbol for query in client.queries) == KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    assert all(query.exchange == "NAS" for query in client.queries)
    assert all(query.continuation is None for query in client.queries)
    assert all(
        tuple(row.session_date for row in run.cache.rows_by_symbol[symbol])
        == (date(2026, 7, 27), date(2026, 7, 28))
        for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
    )
    assert {query.by_date for query in client.queries} == {"20260728"}
    payload = run.safe_payload()
    assert "target_failures" not in payload
    assert payload["route_isolation"] == {
        "daily_market_data_only": True,
        "account_endpoints_used": False,
        "order_endpoints_used": False,
        "live_endpoints_used": False,
    }


def test_one_symbol_failure_is_scoped_and_does_not_read_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(failures={"MSFT": "transport_failure"})
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("core collector must not read the environment")

    monkeypatch.setattr(os, "getenv", unexpected)
    run = collect_kis_paper_daily_nas_forward_once(
        client,
        cache_root=tmp_path / "external" / "forward",
        repository_root=repo_root,
        observed_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    assert run.status == "partial"
    assert run.cache.targets_by_key["MSFT/NAS"].status == "deferred"
    assert not run.cache.rows_by_symbol["MSFT"]
    assert run.cache.rows_by_symbol["AAPL"]
    assert run.safe_payload()["target_failures"] == [
        {
            "failure_stage": "target_fetch",
            "failure_category": "transport_failure",
            "failure_symbol": "MSFT",
        }
    ]
    assert "target_failures" not in run.cache.safe_payload()


def test_unknown_fetch_failure_is_sanitized_to_safe_reason(tmp_path: Path) -> None:
    client = _Client(failures={"AAPL": "unexpected sensitive provider detail"})
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    run = collect_kis_paper_daily_nas_forward_once(
        client,
        cache_root=tmp_path / "external" / "forward",
        repository_root=repo_root,
        observed_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
    )

    assert run.status == "partial"
    assert (
        run.cache.targets_by_key["AAPL/NAS"].last_reason
        == "unexpected_private_daily_collector_error"
    )
    assert run.safe_payload()["target_failures"] == [
        {
            "failure_stage": "target_fetch",
            "failure_category": "unexpected_private_daily_collector_error",
            "failure_symbol": "AAPL",
        }
    ]
    assert "sensitive provider detail" not in json.dumps(run.safe_payload())


def test_fatal_fetch_error_keeps_type_and_safe_symbol_without_committing(tmp_path: Path) -> None:
    error = OSError("synthetic-private-transport-detail")

    class FailingClient(_Client):
        def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
            if query.symbol == "MSFT":
                raise error
            return super().fetch_daily_raw_page(query)

    cache_root = tmp_path / "external"
    with pytest.raises(OSError) as caught:
        collect_kis_paper_daily_nas_forward_once(
            FailingClient(),
            cache_root=cache_root,
            repository_root=tmp_path / "repo",
            observed_at=datetime(2026, 7, 29, 1, tzinfo=UTC),
        )

    assert caught.value is error
    assert not cache_root.exists()
    assert get_kis_paper_daily_nas_forward_failure_details(error) == {
        "failure_stage": "target_fetch",
        "failure_category": "io_error",
        "failure_symbol": "MSFT",
    }


def test_latest_completed_session_uses_actual_regular_and_early_close_times() -> None:
    korea = ZoneInfo("Asia/Seoul")

    assert latest_completed_us_equity_d1_session(
        datetime(2026, 7, 27, 19, 59, tzinfo=UTC)
    ) == date(2026, 7, 24)
    assert latest_completed_us_equity_d1_session(
        datetime(2026, 7, 27, 20, 0, tzinfo=UTC)
    ) == date(2026, 7, 27)
    assert latest_completed_us_equity_d1_session(
        datetime(2026, 11, 27, 17, 59, tzinfo=UTC)
    ) == date(2026, 11, 25)
    assert latest_completed_us_equity_d1_session(
        datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    ) == date(2026, 11, 27)
    assert latest_completed_us_equity_d1_session(
        datetime(2026, 7, 28, 6, 40, tzinfo=korea).astimezone(UTC)
    ) == date(2026, 7, 27)
    assert latest_completed_us_equity_d1_session(
        datetime(2026, 1, 6, 6, 40, tzinfo=korea).astimezone(UTC)
    ) == date(2026, 1, 5)


class _Client:
    def __init__(self, *, failures: dict[str, str] | None = None) -> None:
        self.queries: list[KisPaperDailyQuery] = []
        self._failures = failures or {}

    def fetch_daily_raw_page(self, query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
        self.queries.append(query)
        if reason := self._failures.get(query.symbol):
            raise KisPaperMarketDataError(reason)
        return _page(query)


def _page(query: KisPaperDailyQuery) -> KisPaperDailyRawPage:
    rows = (
        KisPaperDailyRawRow(
            xymd="20260728",
            open="101",
            high="102",
            low="100",
            clos="101",
            tvol="1000",
        ),
        KisPaperDailyRawRow(
            xymd="20260727",
            open="100",
            high="101",
            low="99",
            clos="100",
            tvol="900",
        ),
    )
    return KisPaperDailyRawPage(
        page=KisPaperDailyPage(
            query=query,
            row_count=len(rows),
            newest_date="20260728",
            oldest_date="20260727",
            required_ohlcv_fields_present=True,
            continuation_available=False,
            continuation_value=None,
        ),
        rows=rows,
    )

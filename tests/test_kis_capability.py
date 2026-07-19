from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_capability import (
    CompletedBarCache,
    KisCapabilityState,
    KisMarketDataCapability,
    KisStorageRightsStatus,
    observed_kis_paper_capabilities,
)


def test_observed_kis_capabilities_remain_non_deployable_until_qualified() -> None:
    raw_minute, adjusted_daily = observed_kis_paper_capabilities()

    assert raw_minute.state == KisCapabilityState.OBSERVED
    assert raw_minute.timeframe == Timeframe.M1
    assert raw_minute.raw_fields == (
        "xymd",
        "xhms",
        "kymd",
        "khms",
        "open",
        "high",
        "low",
        "last",
        "evol",
    )
    assert raw_minute.storage_rights == KisStorageRightsStatus.UNVERIFIED
    assert raw_minute.paper_model_eligible is False
    assert raw_minute.persistent_cache_allowed is False

    assert adjusted_daily.state == KisCapabilityState.UNAVAILABLE
    assert adjusted_daily.raw_fields == ()
    assert adjusted_daily.paper_model_eligible is False


def test_qualified_memory_capability_does_not_imply_persistent_storage_rights() -> None:
    capability = KisMarketDataCapability(
        capability_id="unit.kis.raw-1m",
        state=KisCapabilityState.QUALIFIED,
        endpoint_category="overseas_stock_intraday",
        exchange_scope=("NAS",),
        symbol_scope=("QQQ",),
        raw_fields=("open", "high", "low", "last", "evol"),
        timeframe=Timeframe.M1,
        time_semantics="unit UTC conversion",
        completed_bar_rule="unit completed-bar rule",
        freshness_budget=timedelta(minutes=2),
        paging_facts="unit bounded page",
        storage_rights=KisStorageRightsStatus.UNVERIFIED,
        evidence_reference="unit-evidence",
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert capability.paper_model_eligible
    assert capability.persistent_cache_allowed is False


def test_completed_bar_cache_reports_input_problems_without_filling_them() -> None:
    bars = _bars(4)
    as_of = bars[-1].end_ts

    assert CompletedBarCache(tuple(bars[:3])).latest_window(
        count=4,
        as_of=as_of,
        max_age=timedelta(minutes=2),
    ).status == "missing"

    duplicate = CompletedBarCache(tuple(bars + [bars[1]])).latest_window(
        count=4,
        as_of=as_of,
        max_age=timedelta(minutes=2),
    )
    assert duplicate.status == "duplicate"

    gap = CompletedBarCache((bars[0], bars[1], bars[3], _bar(4))).latest_window(
        count=4,
        as_of=_bar(4).end_ts,
        max_age=timedelta(minutes=2),
    )
    assert gap.status == "non_contiguous"

    stale = CompletedBarCache(tuple(bars)).latest_window(
        count=4,
        as_of=as_of + timedelta(minutes=3),
        max_age=timedelta(minutes=2),
    )
    assert stale.status == "stale"


def _bars(count: int) -> list[Bar]:
    return [_bar(index) for index in range(count)]


def _bar(index: int) -> Bar:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC) + timedelta(minutes=index)
    open_price = Decimal("100") + Decimal(index) / Decimal("100")
    close = open_price + Decimal("0.01")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start,
        open=open_price,
        high=close + Decimal("0.01"),
        low=open_price - Decimal("0.01"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )

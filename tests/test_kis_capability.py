from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_capability import (
    CompletedBarCache,
    KisCapabilityQualification,
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
    capability = _qualified_capability()

    assert capability.paper_model_eligible
    assert capability.persistent_cache_allowed is False

    qualification = KisCapabilityQualification(
        qualification_id="unit.qualification.raw-1m",
        capability_id=capability.capability_id,
        capability_contract_sha256=capability.contract_sha256,
        evidence_reference="unit-evidence-review",
        reviewed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert qualification.binds(capability)
    assert qualification.binds(replace(capability, paging_facts="changed")) is False


def test_capability_contract_sha256_covers_every_capability_field() -> None:
    capability = _qualified_capability()
    changes = {
        "capability_id": "unit.kis.raw-1m.changed",
        "state": KisCapabilityState.OBSERVED,
        "endpoint_category": "overseas_stock_daily",
        "exchange_scope": ("NYSE",),
        "symbol_scope": ("SPY",),
        "raw_fields": ("open", "high", "low", "last", "evol", "vwap"),
        "timeframe": Timeframe.M5,
        "time_semantics": "changed time semantics",
        "completed_bar_rule": "changed completed-bar rule",
        "freshness_budget": timedelta(minutes=3),
        "paging_facts": "changed paging facts",
        "storage_rights": KisStorageRightsStatus.CONFIRMED,
        "evidence_reference": "changed-evidence",
        "observed_at": datetime(2026, 1, 2, 0, 1, tzinfo=UTC),
        "schema_version": 2,
    }

    assert set(changes) == {field.name for field in fields(KisMarketDataCapability)}
    for field_name, replacement in changes.items():
        assert replace(capability, **{field_name: replacement}).contract_sha256 != (
            capability.contract_sha256
        )


def test_capability_contract_sha256_normalizes_membership_scope_order() -> None:
    capability = replace(
        _qualified_capability(),
        exchange_scope=("NAS", "NYSE"),
        symbol_scope=("QQQ", "SPY"),
    )
    reordered = replace(
        capability,
        exchange_scope=("NYSE", "NAS"),
        symbol_scope=("SPY", "QQQ"),
    )
    qualification = KisCapabilityQualification(
        qualification_id="unit.qualification.scope-order",
        capability_id=capability.capability_id,
        capability_contract_sha256=capability.contract_sha256,
        evidence_reference="unit-evidence-review",
        reviewed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert capability.exchange_scope == ("NAS", "NYSE")
    assert capability.symbol_scope == ("QQQ", "SPY")
    assert reordered.contract_sha256 == capability.contract_sha256
    assert qualification.binds(reordered)


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


def _qualified_capability() -> KisMarketDataCapability:
    return KisMarketDataCapability(
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

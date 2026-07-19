"""Non-secret KIS market-data capability records and completed-bar cache."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc


class KisCapabilityState(StrEnum):
    DECLARED = "declared"
    OBSERVED = "observed"
    QUALIFIED = "qualified"
    UNAVAILABLE = "unavailable"


class KisStorageRightsStatus(StrEnum):
    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    PROHIBITED = "prohibited"


BarWindowStatus = Literal[
    "ready",
    "missing",
    "stale",
    "incomplete",
    "duplicate",
    "non_contiguous",
    "future",
]


@dataclass(frozen=True)
class KisMarketDataCapability:
    """A small, versioned data contract rather than a second data catalog."""

    capability_id: str
    state: KisCapabilityState
    endpoint_category: str
    exchange_scope: tuple[str, ...]
    symbol_scope: tuple[str, ...]
    raw_fields: tuple[str, ...]
    timeframe: Timeframe
    time_semantics: str
    completed_bar_rule: str
    freshness_budget: timedelta | None
    paging_facts: str
    storage_rights: KisStorageRightsStatus
    evidence_reference: str
    observed_at: datetime | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.capability_id, "capability_id"),
            (self.endpoint_category, "endpoint_category"),
            (self.time_semantics, "time_semantics"),
            (self.completed_bar_rule, "completed_bar_rule"),
            (self.paging_facts, "paging_facts"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be nonempty")
        object.__setattr__(self, "exchange_scope", _required_scope(self.exchange_scope))
        object.__setattr__(self, "symbol_scope", _required_scope(self.symbol_scope))
        object.__setattr__(self, "raw_fields", tuple(field.strip() for field in self.raw_fields))
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        if self.freshness_budget is not None and self.freshness_budget <= timedelta(0):
            raise ValueError("freshness_budget must be positive when known")
        if self.state == KisCapabilityState.DECLARED:
            if self.observed_at is not None or self.evidence_reference:
                raise ValueError("declared capability cannot claim observed evidence")
        else:
            if self.observed_at is None or not self.evidence_reference.strip():
                raise ValueError("observed capability state requires dated evidence")
            object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.state == KisCapabilityState.QUALIFIED:
            if self.storage_rights == KisStorageRightsStatus.PROHIBITED:
                raise ValueError("qualified capability cannot use prohibited storage rights")
            if self.freshness_budget is None:
                raise ValueError("qualified capability requires a freshness budget")

    @property
    def paper_model_eligible(self) -> bool:
        return self.state == KisCapabilityState.QUALIFIED

    @property
    def persistent_cache_allowed(self) -> bool:
        return self.storage_rights == KisStorageRightsStatus.CONFIRMED


@dataclass(frozen=True)
class CompletedBarWindow:
    status: BarWindowStatus
    bars: tuple[Bar, ...]
    observed_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))
        if self.status == "ready" and not self.bars:
            raise ValueError("ready window requires bars")
        if self.status != "ready" and self.bars:
            raise ValueError("unready window must not expose candidate bars")


@dataclass(frozen=True)
class CompletedBarCache:
    """In-memory completed bars only; persistence awaits storage-rights evidence."""

    bars: tuple[Bar, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "bars", tuple(self.bars))

    def latest_window(
        self,
        *,
        count: int,
        as_of: datetime,
        max_age: timedelta,
    ) -> CompletedBarWindow:
        if count <= 0:
            raise ValueError("count must be positive")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        observed_at = require_utc(as_of, "as_of")
        if len(self.bars) < count:
            return CompletedBarWindow("missing", (), observed_at)

        ordered = tuple(sorted(self.bars, key=lambda item: item.start_ts))
        first = ordered[0]
        if any(
            item.timeframe != first.timeframe
            or item.symbol != first.symbol
            or item.market != first.market
            or not item.complete
            for item in ordered
        ):
            return CompletedBarWindow("incomplete", (), observed_at)
        if len({item.start_ts for item in ordered}) != len(ordered):
            return CompletedBarWindow("duplicate", (), observed_at)

        selected = ordered[-count:]
        if any(
            current.start_ts != prior.end_ts
            for prior, current in zip(selected, selected[1:], strict=False)
        ):
            return CompletedBarWindow("non_contiguous", (), observed_at)
        latest = selected[-1]
        if latest.end_ts > observed_at:
            return CompletedBarWindow("future", (), observed_at)
        if observed_at - latest.end_ts > max_age:
            return CompletedBarWindow("stale", (), observed_at)
        return CompletedBarWindow("ready", selected, observed_at)


def observed_kis_paper_capabilities() -> tuple[KisMarketDataCapability, ...]:
    """The dated 2026-07-19 observations, deliberately short of qualification."""

    observed_at = datetime(2026, 7, 19, 5, 42, 16, tzinfo=UTC)
    evidence = (
        r"D:\thericher-v2\model-artifacts\execution\kis-paper-market-data-probe"
        r"\20260719T054216611479Z\summary.json"
    )
    return (
        KisMarketDataCapability(
            capability_id="kis.paper.us.raw-1m.2026-07-19",
            state=KisCapabilityState.OBSERVED,
            endpoint_category="overseas_stock_intraday",
            exchange_scope=("NAS",),
            symbol_scope=("QQQ",),
            raw_fields=(
                "xymd",
                "xhms",
                "kymd",
                "khms",
                "open",
                "high",
                "low",
                "last",
                "evol",
            ),
            timeframe=Timeframe.M1,
            time_semantics=(
                "exchange and Korea timestamp fields observed; UTC conversion unqualified"
            ),
            completed_bar_rule="completion semantics require a later bounded runtime observation",
            freshness_budget=None,
            paging_facts="two 120-row pages observed with one boundary overlap",
            storage_rights=KisStorageRightsStatus.UNVERIFIED,
            evidence_reference=evidence,
            observed_at=observed_at,
        ),
        KisMarketDataCapability(
            capability_id="kis.paper.us.adjusted-daily.2026-07-19",
            state=KisCapabilityState.UNAVAILABLE,
            endpoint_category="overseas_stock_daily_adjusted",
            exchange_scope=("NAS",),
            symbol_scope=("QQQ",),
            raw_fields=(),
            timeframe=Timeframe.D1,
            time_semantics="unavailable for the initial baseline",
            completed_bar_rule="unavailable for the initial baseline",
            freshness_budget=None,
            paging_facts="adjusted request returned EGW00201",
            storage_rights=KisStorageRightsStatus.UNVERIFIED,
            evidence_reference=evidence,
            observed_at=observed_at,
        ),
    )


def _required_scope(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(value.strip().upper() for value in values)
    if not normalized or any(not value for value in normalized):
        raise ValueError("capability scope must be nonempty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("capability scope must not contain duplicates")
    return normalized

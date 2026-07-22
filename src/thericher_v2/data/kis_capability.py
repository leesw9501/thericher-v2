"""Non-secret KIS market-data capability records and completed-bar cache."""

from __future__ import annotations

import hashlib
import json
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

    @property
    def contract_sha256(self) -> str:
        """Return a canonical fingerprint for a qualification binding."""

        payload = {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "state": self.state.value,
            "endpoint_category": self.endpoint_category,
            "exchange_scope": list(self.exchange_scope),
            "symbol_scope": list(self.symbol_scope),
            "raw_fields": list(self.raw_fields),
            "timeframe": self.timeframe.value,
            "time_semantics": self.time_semantics,
            "completed_bar_rule": self.completed_bar_rule,
            "freshness_budget_microseconds": _timedelta_microseconds(self.freshness_budget),
            "paging_facts": self.paging_facts,
            "storage_rights": self.storage_rights.value,
            "evidence_reference": self.evidence_reference,
            "observed_at": None if self.observed_at is None else self.observed_at.isoformat(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True)
class KisCapabilityQualification:
    """A reviewed binding for one exact capability contract.

    This is structural provenance only. A later Data-owned reader must validate
    evidence before an external record can enter a production trusted registry.
    """

    qualification_id: str
    capability_id: str
    capability_contract_sha256: str
    evidence_reference: str
    reviewed_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.qualification_id, "qualification_id"),
            (self.capability_id, "capability_id"),
            (self.capability_contract_sha256, "capability_contract_sha256"),
            (self.evidence_reference, "evidence_reference"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be nonempty")
        _require_sha256(self.capability_contract_sha256, "capability_contract_sha256")
        object.__setattr__(self, "reviewed_at", require_utc(self.reviewed_at, "reviewed_at"))

    def binds(self, capability: KisMarketDataCapability) -> bool:
        return (
            self.capability_id == capability.capability_id
            and self.capability_contract_sha256 == capability.contract_sha256
        )


def trusted_kis_paper_baseline_qualifications() -> tuple[KisCapabilityQualification, ...]:
    """Return Data-owned production bindings; none exist until a later review."""

    return ()


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
    """Dated Paper observations, deliberately short of research qualification."""

    observed_at = datetime(2026, 7, 19, 5, 42, 16, tzinfo=UTC)
    evidence = (
        r"D:\thericher-v2\model-artifacts\execution\kis-paper-market-data-probe"
        r"\20260719T054216611479Z\summary.json"
    )
    return (
        KisMarketDataCapability(
            capability_id="kis.paper.us.raw-1m.cache-v1.2026-07-22",
            state=KisCapabilityState.OBSERVED,
            endpoint_category="overseas_stock_intraday",
            exchange_scope=("NAS", "AMS"),
            symbol_scope=("QQQ", "SPY"),
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
                "Korea timestamp fields map to UTC; exchange/session/open-close semantics "
                "observed_unqualified"
            ),
            completed_bar_rule=(
                "bar end at or before the rounded collection minute; source completion "
                "semantics unqualified"
            ),
            freshness_budget=None,
            paging_facts=(
                "two 120-row pages per target with one exact boundary overlap; "
                "NEXT/KEYB cursor persisted"
            ),
            storage_rights=KisStorageRightsStatus.UNVERIFIED,
            evidence_reference=(
                r"D:\market_data\us_equities\kis_paper_private\intraday\v1\index.json"
            ),
            observed_at=datetime(2026, 7, 22, 1, 10, 4, 69369, tzinfo=UTC),
        ),
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
    normalized = tuple(sorted(value.strip().upper() for value in values))
    if not normalized or any(not value for value in normalized):
        raise ValueError("capability scope must be nonempty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("capability scope must not contain duplicates")
    return normalized


def _timedelta_microseconds(value: timedelta | None) -> int | None:
    if value is None:
        return None
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _require_sha256(value: str, name: str) -> None:
    prefix = "sha256:"
    digest = value.removeprefix(prefix)
    if not value.startswith(prefix) or len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest.lower()
    ):
        raise ValueError(f"{name} must be a sha256 digest")

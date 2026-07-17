"""Immutable contract for one catalog-backed research campaign."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from thericher_v2.contracts import (
    SCHEMA_VERSION,
    Timeframe,
    non_negative,
    require_utc,
)

CampaignPhase = Literal["development", "validation", "holdout"]
CampaignEvidenceUse = Literal["development", "ranking"]
NaiveBaselineId = Literal["always_long", "previous_bar_direction", "flat"]

SUPPORTED_NAIVE_BASELINES: frozenset[str] = frozenset(
    {"always_long", "previous_bar_direction", "flat"}
)


@dataclass(frozen=True)
class CatalogDatasetRef:
    """Data-owned identity and eligibility facts consumed by Research."""

    catalog_id: str
    dataset_id: str
    dataset_hash: str
    constructed_as_of_utc: datetime
    ranking_eligible: bool
    sealed_holdout_eligible: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.catalog_id, "catalog_id")
        _require_text(self.dataset_id, "dataset_id")
        _require_sha256(self.dataset_hash, "dataset_hash")
        object.__setattr__(
            self,
            "constructed_as_of_utc",
            require_utc(self.constructed_as_of_utc, "constructed_as_of_utc"),
        )


@dataclass(frozen=True)
class CampaignWindow:
    """Half-open UTC interval: ``start_utc <= bar < end_utc``."""

    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        start = require_utc(self.start_utc, "start_utc")
        end = require_utc(self.end_utc, "end_utc")
        if end <= start:
            raise ValueError("campaign window end_utc must be after start_utc")
        object.__setattr__(self, "start_utc", start)
        object.__setattr__(self, "end_utc", end)


@dataclass(frozen=True)
class CampaignFold:
    fold_id: str
    development: CampaignWindow
    validation: CampaignWindow

    def __post_init__(self) -> None:
        _require_text(self.fold_id, "fold_id")
        if self.development.end_utc > self.validation.start_utc:
            raise ValueError("development and validation windows must not overlap")


@dataclass(frozen=True)
class ExecutableTarget:
    """Target supported by the local-paper next-bar-open fill contract."""

    decision_price: Literal["completed_bar_close"] = "completed_bar_close"
    entry_price: Literal["next_bar_open"] = "next_bar_open"
    exit_price: Literal["following_bar_open"] = "following_bar_open"
    position_side: Literal["long_only"] = "long_only"
    entry_bar_offset: int = 1
    exit_bar_offset: int = 2

    def __post_init__(self) -> None:
        if self.entry_bar_offset != 1:
            raise ValueError("local-paper campaign entry must use the next bar open")
        if self.exit_bar_offset != self.entry_bar_offset + 1:
            raise ValueError("campaign exit must use the open following the entry bar")


@dataclass(frozen=True)
class CampaignCosts:
    fee_bps: Decimal
    slippage_bps: Decimal
    slippage_source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fee_bps", non_negative(self.fee_bps, "fee_bps"))
        object.__setattr__(
            self,
            "slippage_bps",
            non_negative(self.slippage_bps, "slippage_bps"),
        )
        _require_text(self.slippage_source_id, "slippage_source_id")


@dataclass(frozen=True)
class CampaignContract:
    """Single generic contract shared by campaign preparation and validation."""

    campaign_id: str
    catalog: CatalogDatasetRef
    timeframe: Timeframe
    folds: tuple[CampaignFold, ...]
    target: ExecutableTarget
    costs: CampaignCosts
    purge: timedelta
    embargo: timedelta
    evidence_use: CampaignEvidenceUse = "development"
    sealed_holdout: CampaignWindow | None = None
    naive_baselines: tuple[NaiveBaselineId, ...] = (
        "always_long",
        "previous_bar_direction",
        "flat",
    )
    metrics: tuple[str, ...] = (
        "after_cost_pnl",
        "gross_pnl",
        "fee_cost",
        "slippage_cost",
        "trade_count",
    )
    deterministic_seed: int = 23
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.campaign_id, "campaign_id")
        object.__setattr__(self, "timeframe", Timeframe(self.timeframe))
        object.__setattr__(self, "folds", tuple(self.folds))
        object.__setattr__(self, "naive_baselines", tuple(self.naive_baselines))
        object.__setattr__(self, "metrics", tuple(self.metrics))
        if not self.folds:
            raise ValueError("campaign requires at least one forward fold")
        if self.purge < timedelta(0) or self.embargo < timedelta(0):
            raise ValueError("purge and embargo must be non-negative")
        label_horizon = self.timeframe.duration * (
            self.target.exit_bar_offset - self.target.entry_bar_offset
        )
        if self.purge < label_horizon or self.embargo < label_horizon:
            raise ValueError("purge and embargo must cover the executable label horizon")
        if not isinstance(self.deterministic_seed, int) or isinstance(
            self.deterministic_seed, bool
        ):
            raise ValueError("deterministic_seed must be an integer")
        if self.deterministic_seed < 0:
            raise ValueError("deterministic_seed must be non-negative")
        if self.evidence_use not in {"development", "ranking"}:
            raise ValueError("unsupported evidence_use")
        if self.evidence_use == "ranking":
            if not self.catalog.ranking_eligible:
                raise ValueError("ranking contract requires catalog ranking eligibility")
            if self.costs.slippage_bps <= 0:
                raise ValueError("ranking contract requires strictly positive slippage")

        _validate_unique_text(self.naive_baselines, "naive_baselines")
        unsupported = set(self.naive_baselines) - SUPPORTED_NAIVE_BASELINES
        if unsupported:
            raise ValueError(f"unsupported naive baseline: {sorted(unsupported)[0]}")
        _validate_unique_text(self.metrics, "metrics")
        if "after_cost_pnl" not in self.metrics:
            raise ValueError("campaign metrics must include after_cost_pnl")

        prior_validation: CampaignWindow | None = None
        seen_fold_ids: set[str] = set()
        for fold in self.folds:
            if fold.fold_id in seen_fold_ids:
                raise ValueError("fold_id values must be unique")
            seen_fold_ids.add(fold.fold_id)
            if fold.development.end_utc + self.purge > fold.validation.start_utc:
                raise ValueError("purge must separate development and validation windows")
            if (
                prior_validation is not None
                and prior_validation.end_utc + self.embargo > fold.development.start_utc
            ):
                raise ValueError("folds must be forward, non-overlapping, and embargoed")
            prior_validation = fold.validation

        if self.sealed_holdout is not None:
            if not self.catalog.sealed_holdout_eligible:
                raise ValueError("catalog marks the sealed holdout ineligible")
            if self.catalog.constructed_as_of_utc > self.sealed_holdout.start_utc:
                raise ValueError("catalog as-of construction is after sealed holdout start")
            if (
                prior_validation is not None
                and prior_validation.end_utc + self.embargo > self.sealed_holdout.start_utc
            ):
                raise ValueError("sealed holdout must follow validation and embargo")

    @property
    def contract_hash(self) -> str:
        encoded = json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def verify_cataloged_dataset(self, *, dataset_id: str, dataset_hash: str) -> None:
        if dataset_id != self.catalog.dataset_id:
            raise ValueError("CatalogedBars dataset_id does not match the campaign contract")
        if dataset_hash != self.catalog.dataset_hash:
            raise ValueError("CatalogedBars dataset_hash does not match the campaign contract")

    def resolve_window(
        self,
        phase: CampaignPhase,
        *,
        fold_id: str | None = None,
        tuning: bool = False,
    ) -> tuple[str | None, CampaignWindow]:
        if phase == "holdout":
            if tuning:
                raise ValueError("sealed holdout cannot be used for tuning")
            if fold_id is not None:
                raise ValueError("sealed holdout is not associated with a fold_id")
            if self.sealed_holdout is None:
                raise ValueError("campaign has no sealed holdout")
            return None, self.sealed_holdout
        if phase not in {"development", "validation"}:
            raise ValueError("unsupported campaign phase")
        resolved_fold = self._resolve_fold(fold_id)
        window = (
            resolved_fold.development if phase == "development" else resolved_fold.validation
        )
        return resolved_fold.fold_id, window

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "catalog": {
                "schema_version": self.catalog.schema_version,
                "catalog_id": self.catalog.catalog_id,
                "dataset_id": self.catalog.dataset_id,
                "dataset_hash": self.catalog.dataset_hash,
                "constructed_as_of_utc": self.catalog.constructed_as_of_utc.isoformat(),
                "ranking_eligible": self.catalog.ranking_eligible,
                "sealed_holdout_eligible": self.catalog.sealed_holdout_eligible,
            },
            "timeframe": self.timeframe.value,
            "folds": [
                {
                    "fold_id": fold.fold_id,
                    "development": _window_payload(fold.development),
                    "validation": _window_payload(fold.validation),
                }
                for fold in self.folds
            ],
            "target": {
                "decision_price": self.target.decision_price,
                "entry_price": self.target.entry_price,
                "exit_price": self.target.exit_price,
                "position_side": self.target.position_side,
                "entry_bar_offset": self.target.entry_bar_offset,
                "exit_bar_offset": self.target.exit_bar_offset,
            },
            "costs": {
                "fee_bps": str(self.costs.fee_bps),
                "slippage_bps": str(self.costs.slippage_bps),
                "slippage_source_id": self.costs.slippage_source_id,
            },
            "purge_seconds": self.purge.total_seconds(),
            "embargo_seconds": self.embargo.total_seconds(),
            "evidence_use": self.evidence_use,
            "sealed_holdout": (
                None if self.sealed_holdout is None else _window_payload(self.sealed_holdout)
            ),
            "naive_baselines": list(self.naive_baselines),
            "metrics": list(self.metrics),
            "deterministic_seed": self.deterministic_seed,
        }

    def _resolve_fold(self, fold_id: str | None) -> CampaignFold:
        if fold_id is None:
            if len(self.folds) != 1:
                raise ValueError("fold_id is required when a campaign has multiple folds")
            return self.folds[0]
        for fold in self.folds:
            if fold.fold_id == fold_id:
                return fold
        raise ValueError(f"unknown campaign fold_id: {fold_id}")


def _window_payload(window: CampaignWindow) -> dict[str, str]:
    return {
        "start_utc": window.start_utc.isoformat(),
        "end_utc": window.end_utc.isoformat(),
    }


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use the sha256: prefix")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise ValueError(f"{field_name} must contain a 64-character SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain a hexadecimal SHA-256 digest") from exc


def _validate_unique_text(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    for value in values:
        _require_text(value, field_name)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must be unique")

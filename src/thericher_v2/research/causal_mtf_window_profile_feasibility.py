"""Outcome-free causal multi-timeframe window profile contracts.

This module fixes a small, canonical set of observation windows before any
dataset, label, return, model, or campaign is selected.  It is deliberately
offline: callers provide ``Bar`` objects and an explicit external artifact
root when they want to persist a source-safe catalog-registration receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.models.sequence_window import (
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    CausalMultiTimeframeSequenceWindow,
    build_causal_multitimeframe_sequence_window,
)

from .artifact_paths import ensure_external_artifact_directory

CAUSAL_MTF_WINDOW_PROFILE_CATALOG_SCHEMA_ID = "causal-mtf-window-profile-catalog-v1"
CAUSAL_MTF_WINDOW_PROFILE_RECEIPT_SCHEMA_ID = "causal-mtf-window-profile-receipt-v1"
CANONICAL_PROFILE_TIMEFRAMES = SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
CANONICAL_PROFILE_SPECS = (
    ("short", (15, 3, 3, 2, 2)),
    ("kis_baseline", (30, 6, 3, 2, 2)),
    ("one_hour", (60, 12, 6, 2, 2)),
    ("medium", (90, 18, 12, 2, 2)),
    ("long", (120, 36, 12, 2, 2)),
    ("extended", (180, 36, 18, 2, 2)),
)
WindowProfileFeasibilityStatus = Literal["feasible"]


@dataclass(frozen=True, slots=True)
class CausalMtfWindowProfile:
    """One named five-timeframe observation-window choice."""

    profile_id: str
    lookback_vector: tuple[int, int, int, int, int]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("profile schema_version must match the current contract")
        if not self.profile_id or any(part in self.profile_id for part in ("/", "\\", ":")):
            raise ValueError("profile_id must be a nonempty identifier")
        values = tuple(self.lookback_vector)
        if len(values) != len(CANONICAL_PROFILE_TIMEFRAMES):
            raise ValueError("lookback_vector must cover exactly 1m, 5m, 10m, 1h, and 3h")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in values
        ):
            raise ValueError("profile lookbacks must be positive integers")
        object.__setattr__(self, "lookback_vector", values)

    @property
    def lookbacks(self) -> Mapping[Timeframe, int]:
        """Return the five lookbacks in the sequence-window canonical order."""

        return MappingProxyType(
            dict(zip(CANONICAL_PROFILE_TIMEFRAMES, self.lookback_vector, strict=True))
        )

    @property
    def identity_sha256(self) -> str:
        return _sha256_json(_profile_payload(self))


@dataclass(frozen=True, slots=True)
class CausalMtfWindowProfileCatalog:
    """The only allowed ordered profile catalog for this preparatory contract."""

    profiles: tuple[CausalMtfWindowProfile, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("catalog schema_version must match the current contract")
        profiles = tuple(self.profiles)
        expected = tuple(
            CausalMtfWindowProfile(profile_id=profile_id, lookback_vector=lookbacks)
            for profile_id, lookbacks in CANONICAL_PROFILE_SPECS
        )
        if profiles != expected:
            raise ValueError("profiles must equal the immutable canonical ordered catalog")
        object.__setattr__(self, "profiles", profiles)

    @property
    def identity_sha256(self) -> str:
        return _sha256_json(_catalog_payload(self))

    def profile(self, profile_id: str) -> CausalMtfWindowProfile:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        raise ValueError("profile_id is not in the canonical catalog")


CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG = CausalMtfWindowProfileCatalog(
    profiles=tuple(
        CausalMtfWindowProfile(profile_id=profile_id, lookback_vector=lookbacks)
        for profile_id, lookbacks in CANONICAL_PROFILE_SPECS
    )
)


@dataclass(frozen=True, slots=True)
class CausalMtfWindowProfileFeasibility:
    """Structural output only; it intentionally contains no OHLCV values."""

    profile_id: str
    catalog_sha256: str
    status: WindowProfileFeasibilityStatus
    window: CausalMultiTimeframeSequenceWindow = field(repr=False)
    schema_version: int = SCHEMA_VERSION

    def source_safe_summary(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "catalog_sha256": self.catalog_sha256,
            "status": self.status,
            "timeframe_bar_counts": {
                timeframe.value: len(window.bars)
                for timeframe, window in self.window.windows.items()
            },
            "window_end": {
                timeframe.value: window.end_ts.isoformat()
                for timeframe, window in self.window.windows.items()
            },
        }


@dataclass(frozen=True, slots=True)
class CausalMtfWindowProfileReceipt:
    """Immutable, redacted catalog-registration receipt stored outside Git."""

    receipt_path: Path
    receipt_sha256: str
    catalog_sha256: str
    issued_at: datetime
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("receipt schema_version must match the current contract")
        _require_sha256(self.receipt_sha256, "receipt_sha256")
        _require_sha256(self.catalog_sha256, "catalog_sha256")
        object.__setattr__(self, "issued_at", require_utc(self.issued_at, "issued_at"))


def assess_profile_feasibility(
    *,
    catalog: CausalMtfWindowProfileCatalog,
    profile_id: str,
    bars_by_timeframe: Mapping[Timeframe, Sequence[Bar]],
    cutoff: datetime,
) -> CausalMtfWindowProfileFeasibility:
    """Use the existing causal validator without reading any external input."""

    profile = catalog.profile(profile_id)
    window = build_causal_multitimeframe_sequence_window(
        bars_by_timeframe,
        lookbacks=profile.lookbacks,
        cutoff=cutoff,
    )
    return CausalMtfWindowProfileFeasibility(
        profile_id=profile.profile_id,
        catalog_sha256=catalog.identity_sha256,
        status="feasible",
        window=window,
    )


def assess_profile_with_deterministic_synthetic_bars(
    *,
    catalog: CausalMtfWindowProfileCatalog,
    profile_id: str,
    cutoff: datetime,
) -> CausalMtfWindowProfileFeasibility:
    """Run the pure structural check with deterministic, in-memory test bars."""

    profile = catalog.profile(profile_id)
    return assess_profile_feasibility(
        catalog=catalog,
        profile_id=profile.profile_id,
        bars_by_timeframe=deterministic_synthetic_bars(profile=profile, cutoff=cutoff),
        cutoff=cutoff,
    )


def deterministic_synthetic_bars(
    *,
    profile: CausalMtfWindowProfile,
    cutoff: datetime,
    symbol: str = "WINDOW",
    market: str = "SYNTHETIC",
) -> dict[Timeframe, tuple[Bar, ...]]:
    """Make complete contiguous bars solely for contract feasibility tests."""

    normalized_cutoff = require_utc(cutoff, "cutoff")
    output: dict[Timeframe, tuple[Bar, ...]] = {}
    for timeframe, lookback in profile.lookbacks.items():
        start = normalized_cutoff - timeframe.duration * lookback
        output[timeframe] = tuple(
            Bar(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                start_ts=start + timeframe.duration * index,
                open=Decimal("100.00"),
                high=Decimal("100.01"),
                low=Decimal("99.99"),
                close=Decimal("100.00"),
                volume=Decimal("1"),
                complete=True,
            )
            for index in range(lookback)
        )
    return output


def write_catalog_registration_receipt(
    *,
    catalog: CausalMtfWindowProfileCatalog,
    artifact_root: Path,
    issued_at: datetime,
) -> CausalMtfWindowProfileReceipt:
    """Persist one immutable source-safe catalog receipt below an external root."""

    normalized_issued_at = require_utc(issued_at, "issued_at")
    output_dir = ensure_external_artifact_directory(
        artifact_root,
        _repo_root(),
        "research",
        "causal-mtf-window-profile-catalog",
    )
    unsigned_payload = {
        "schema_id": CAUSAL_MTF_WINDOW_PROFILE_RECEIPT_SCHEMA_ID,
        "catalog_sha256": catalog.identity_sha256,
        "issued_at": normalized_issued_at.isoformat(),
        "receipt_kind": "source_safe_catalog_registration",
        "contains": ["catalog_identity", "timestamp"],
        "excludes": [
            "artifact_root",
            "bar_values",
            "credentials",
            "environment",
            "labels",
            "model_weights",
            "prices",
            "returns",
            "targets",
        ],
    }
    receipt_sha256 = _sha256_json(unsigned_payload)
    payload = {**unsigned_payload, "receipt_sha256": receipt_sha256}
    stamp = normalized_issued_at.strftime("%Y%m%dT%H%M%SZ")
    receipt_path = output_dir / f"{stamp}-{receipt_sha256[7:19]}.json"
    try:
        with receipt_path.open("x", encoding="utf-8") as receipt_file:
            json.dump(payload, receipt_file, indent=2, sort_keys=True)
            receipt_file.write("\n")
    except FileExistsError as error:
        raise ValueError(
            "catalog registration receipt is immutable and already exists"
        ) from error
    return CausalMtfWindowProfileReceipt(
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        catalog_sha256=catalog.identity_sha256,
        issued_at=normalized_issued_at,
    )


def _catalog_payload(catalog: CausalMtfWindowProfileCatalog) -> dict[str, object]:
    return {
        "schema_id": CAUSAL_MTF_WINDOW_PROFILE_CATALOG_SCHEMA_ID,
        "profiles": [_profile_payload(profile) for profile in catalog.profiles],
    }


def _profile_payload(profile: CausalMtfWindowProfile) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "lookbacks": {
            timeframe.value: lookback
            for timeframe, lookback in zip(
                CANONICAL_PROFILE_TIMEFRAMES, profile.lookback_vector, strict=True
            )
        },
    }


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use the sha256: prefix")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must contain a lowercase SHA-256 digest")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

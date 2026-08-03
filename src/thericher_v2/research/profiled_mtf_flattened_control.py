"""A deterministic flattened control view over one causal MTF projection.

The source projection remains the owner of normalized feature provenance and
per-timeframe sequences. This module only publishes one MLP-style flattened
layout for a caller that explicitly chooses that control. It reuses the
existing causal-window validator for structural checks, but it does not
independently derive normalized values from bars.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Final

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe, require_utc
from thericher_v2.models.sequence_window import (
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    CausalMultiTimeframeSequenceWindow,
    build_causal_multitimeframe_sequence_window,
)

from .causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
)
from .kis_mtf_profiled_feature_input_preflight import NormalizedCompletedBarProjection

PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID: Final = "profiled-mtf-flattened-control-v1"
PROFILED_MTF_FLATTENED_CONTROL_FEATURE_NAMES: Final = (
    "close_relative_to_first_completed_bar",
    "volume_relative_to_first_completed_bar_or_one",
)
PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY: Final = (
    "per_timeframe_first_completed_close_and_volume_or_one"
)


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlattenedBlock:
    """One canonical contiguous segment in the flattened control vector."""

    timeframe: Timeframe
    feature_offset: int
    bar_count: int
    window_end: datetime
    anchor_policy: str = PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY

    def __post_init__(self) -> None:
        if self.timeframe not in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
            raise ValueError("flattened control timeframe is invalid")
        if self.feature_offset < 0 or self.bar_count <= 0:
            raise ValueError("flattened control block geometry is invalid")
        if self.anchor_policy != PROFILED_MTF_FLATTENED_CONTROL_ANCHOR_POLICY:
            raise ValueError("flattened control anchor policy is invalid")
        object.__setattr__(self, "window_end", require_utc(self.window_end, "window_end"))

    @property
    def feature_width(self) -> int:
        return self.bar_count * len(PROFILED_MTF_FLATTENED_CONTROL_FEATURE_NAMES)


@dataclass(frozen=True, slots=True)
class ProfiledMtfFlattenedControl:
    """One immutable flattened MLP control derived from one source projection."""

    projection: NormalizedCompletedBarProjection = field(repr=False)
    blocks: tuple[ProfiledMtfFlattenedBlock, ...]
    flattened_values: tuple[Decimal, ...] = field(repr=False)
    control_sha256: str
    schema_id: str = PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_id != PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID:
            raise ValueError("flattened control schema_id is invalid")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("flattened control schema_version is invalid")
        projection = _require_projection(self.projection)
        expected_blocks, expected_values = _expected_layout(projection)
        blocks = tuple(self.blocks)
        values = tuple(self.flattened_values)
        if blocks != expected_blocks or values != expected_values:
            raise ValueError("flattened control layout does not match its projection")
        expected_hash = _control_sha256(
            projection=projection,
            blocks=blocks,
            flattened_values=values,
        )
        if self.control_sha256 != expected_hash:
            raise ValueError("flattened control identity is invalid")
        object.__setattr__(self, "blocks", blocks)
        object.__setattr__(self, "flattened_values", values)

    @property
    def source_contract_sha256(self) -> str:
        return self.projection.source_contract_sha256

    @property
    def source_dataset_hash(self) -> str:
        return self.projection.source_dataset_hash

    @property
    def catalog_sha256(self) -> str:
        return self.projection.catalog_sha256

    @property
    def profile_id(self) -> str:
        return self.projection.profile_id

    @property
    def symbol(self) -> str:
        return self.projection.window.symbol

    @property
    def market(self) -> str:
        return self.projection.window.market

    @property
    def cutoff(self) -> datetime:
        return self.projection.cutoff

    @property
    def feature_timestamp(self) -> datetime:
        return self.projection.feature_timestamp

    @property
    def projection_sha256(self) -> str:
        return self.projection.projection_sha256

    @property
    def window_ends(self) -> tuple[tuple[Timeframe, datetime], ...]:
        return self.projection.window_ends

    @property
    def feature_width(self) -> int:
        return len(self.flattened_values)


def build_profiled_mtf_flattened_control(
    projection: NormalizedCompletedBarProjection,
) -> ProfiledMtfFlattenedControl:
    """Flatten one structurally revalidated projection in canonical block order."""

    projection = _require_projection(projection)
    blocks, values = _expected_layout(projection)
    return ProfiledMtfFlattenedControl(
        projection=projection,
        blocks=blocks,
        flattened_values=values,
        control_sha256=_control_sha256(
            projection=projection,
            blocks=blocks,
            flattened_values=values,
        ),
    )


def _require_projection(value: object) -> NormalizedCompletedBarProjection:
    if not isinstance(value, NormalizedCompletedBarProjection):
        raise TypeError("flattened control requires a NormalizedCompletedBarProjection")
    return value


def _expected_layout(
    projection: NormalizedCompletedBarProjection,
) -> tuple[tuple[ProfiledMtfFlattenedBlock, ...], tuple[Decimal, ...]]:
    window = _revalidate_projection_window(projection)
    profile = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.profile(projection.profile_id)
    actual_bar_counts = tuple(
        len(window.windows[timeframe].bars)
        for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    )
    expected_bar_counts = tuple(
        profile.lookbacks[timeframe]
        for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    )
    if actual_bar_counts != expected_bar_counts:
        raise ValueError("flattened control profile geometry is invalid")

    blocks: list[ProfiledMtfFlattenedBlock] = []
    values: list[Decimal] = []
    feature_offset = 0
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        rows = projection.feature_values[timeframe]
        sequence = window.windows[timeframe]
        if len(rows) != len(sequence.bars):
            raise ValueError("flattened control feature geometry is invalid")
        blocks.append(
            ProfiledMtfFlattenedBlock(
                timeframe=timeframe,
                feature_offset=feature_offset,
                bar_count=len(rows),
                window_end=sequence.end_ts,
            )
        )
        for close_value, volume_value in rows:
            if not isinstance(close_value, Decimal) or not isinstance(volume_value, Decimal):
                raise ValueError("flattened control feature values are invalid")
            if not close_value.is_finite() or not volume_value.is_finite():
                raise ValueError("flattened control feature values are invalid")
            values.extend((close_value, volume_value))
        feature_offset += len(rows) * len(PROFILED_MTF_FLATTENED_CONTROL_FEATURE_NAMES)
    return tuple(blocks), tuple(values)


def _revalidate_projection_window(
    projection: NormalizedCompletedBarProjection,
) -> CausalMultiTimeframeSequenceWindow:
    supplied = {
        timeframe: projection.window.windows[timeframe].bars
        for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    }
    lookbacks = {
        timeframe: len(projection.window.windows[timeframe].bars)
        for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
    }
    window = build_causal_multitimeframe_sequence_window(
        supplied,
        lookbacks=lookbacks,
        cutoff=projection.cutoff,
    )
    if (
        window.symbol != projection.window.symbol
        or window.market != projection.window.market
        or window.cutoff != projection.cutoff
        or tuple(
            window.windows[timeframe].bars
            for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
        )
        != tuple(
            projection.window.windows[timeframe].bars
            for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
        )
    ):
        raise ValueError("flattened control causal window is inconsistent")
    if projection.feature_timestamp > projection.cutoff:
        raise ValueError("flattened control feature timestamp is invalid")
    return window


def _control_sha256(
    *,
    projection: NormalizedCompletedBarProjection,
    blocks: tuple[ProfiledMtfFlattenedBlock, ...],
    flattened_values: tuple[Decimal, ...],
) -> str:
    payload = {
        "schema_id": PROFILED_MTF_FLATTENED_CONTROL_SCHEMA_ID,
        "projection_sha256": projection.projection_sha256,
        "feature_names": list(PROFILED_MTF_FLATTENED_CONTROL_FEATURE_NAMES),
        "blocks": [
            {
                "timeframe": block.timeframe.value,
                "feature_offset": block.feature_offset,
                "bar_count": block.bar_count,
                "window_end": block.window_end.isoformat(),
                "anchor_policy": block.anchor_policy,
            }
            for block in blocks
        ],
        "flattened_values": [str(value) for value in flattened_values],
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

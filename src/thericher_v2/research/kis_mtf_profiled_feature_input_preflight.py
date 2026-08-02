"""Target-free causal MTF input preflight for verified local KIS minute bars."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe, require_utc
from thericher_v2.data.kis_intraday_mtf_availability import (
    KIS_INTRADAY_MTF_AVAILABILITY_PREFIX_MINUTES,
    KIS_INTRADAY_MTF_AVAILABILITY_TARGETS,
    KisIntradayMtfAvailabilityContract,
    KisIntradayMtfAvailabilityReceipt,
    KisIntradayMtfSourceIdentity,
    freeze_kis_intraday_mtf_availability_contract,
    load_kis_intraday_mtf_availability_catalogs,
    materialize_kis_intraday_mtf_availability,
)
from thericher_v2.data.local import CatalogedBars
from thericher_v2.data.resample import SessionWindow, resample_session_bars
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.models.sequence_window import (
    SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES,
    CausalMultiTimeframeSequenceWindow,
    SequenceWindowInputError,
)

from .artifact_paths import ensure_external_artifact_directory
from .causal_mtf_window_profile_feasibility import (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
    CausalMtfWindowProfileCatalog,
    assess_profile_feasibility,
)

KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_RECEIPT_ID = "kis-mtf-profiled-feature-input-preflight-v1"
KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_ARTIFACT_DIRECTORY = (
    "kis-mtf-profiled-feature-input-preflight-v1"
)
KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256 = (
    CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG.identity_sha256
)
KIS_MTF_PROFILED_FEATURE_INPUT_CUTOFF = time(15, 30)
KIS_MTF_PROFILED_FEATURE_INPUT_TARGET_KEYS = tuple(
    f"{symbol}/{exchange}/1m" for symbol, exchange in KIS_INTRADAY_MTF_AVAILABILITY_TARGETS
)

PreflightStatus = Literal["feature_inputs_ready", "input_unavailable"]
_EASTERN = ZoneInfo("America/New_York")
_SHA256_PREFIX = "sha256:"
_SAFE_RUN_LABEL = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)
_SLOW_TIMEFRAMES = frozenset({Timeframe.H1, Timeframe.H3})


@dataclass(frozen=True, slots=True)
class NormalizedCompletedBarProjection:
    """One typed, in-memory, target-free projection of an existing causal window."""

    source_contract_sha256: str
    source_dataset_hash: str
    catalog_sha256: str
    profile_id: str
    cutoff: datetime
    window: CausalMultiTimeframeSequenceWindow = field(repr=False)
    feature_values: Mapping[Timeframe, tuple[tuple[Decimal, Decimal], ...]] = field(repr=False)
    projection_sha256: str

    def __post_init__(self) -> None:
        cutoff = require_utc(self.cutoff, "cutoff")
        values = {
            Timeframe(timeframe): tuple((Decimal(close), Decimal(volume)) for close, volume in rows)
            for timeframe, rows in self.feature_values.items()
        }
        if (
            not _is_sha256(self.source_contract_sha256)
            or not _is_sha256(self.source_dataset_hash)
            or self.catalog_sha256 != KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256
            or not self.profile_id
            or self.window.cutoff != cutoff
            or tuple(values) != SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
            or any(
                len(values[timeframe]) != len(sequence.bars)
                or any(
                    not close.is_finite() or not volume.is_finite()
                    for close, volume in values[timeframe]
                )
                for timeframe, sequence in self.window.windows.items()
            )
        ):
            raise ValueError("normalized completed-bar projection is invalid")
        expected = _projection_sha256(
            source_contract_sha256=self.source_contract_sha256,
            source_dataset_hash=self.source_dataset_hash,
            catalog_sha256=self.catalog_sha256,
            profile_id=self.profile_id,
            cutoff=cutoff,
            window_ends=self.window_ends,
            feature_values=values,
        )
        if self.projection_sha256 != expected:
            raise ValueError("normalized completed-bar projection hash is invalid")
        object.__setattr__(self, "cutoff", cutoff)
        object.__setattr__(self, "feature_values", MappingProxyType(values))

    @property
    def window_ends(self) -> tuple[tuple[Timeframe, datetime], ...]:
        return tuple(
            (timeframe, sequence.end_ts) for timeframe, sequence in self.window.windows.items()
        )

    @property
    def feature_timestamp(self) -> datetime:
        return max(end_ts for _, end_ts in self.window_ends)

    @property
    def completed_bar_status(self) -> bool:
        return all(
            bar.complete for sequence in self.window.windows.values() for bar in sequence.bars
        )


@dataclass(frozen=True, slots=True)
class KisMtfProfiledFeatureInputPair:
    """One aligned QQQ/SPY profile input held in memory only."""

    profile_id: str
    source_contract_sha256: str
    catalog_sha256: str
    cutoff: datetime
    legs: tuple[NormalizedCompletedBarProjection, NormalizedCompletedBarProjection] = field(
        repr=False
    )
    pair_input_sha256: str

    def __post_init__(self) -> None:
        cutoff = require_utc(self.cutoff, "cutoff")
        legs = tuple(self.legs)
        if (
            not self.profile_id
            or not _is_sha256(self.source_contract_sha256)
            or self.catalog_sha256 != KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256
            or len(legs) != 2
            or len({leg.source_dataset_hash for leg in legs}) != 2
            or any(
                leg.profile_id != self.profile_id
                or leg.source_contract_sha256 != self.source_contract_sha256
                or leg.catalog_sha256 != self.catalog_sha256
                or leg.cutoff != cutoff
                or leg.feature_timestamp != self.feature_timestamp
                or not leg.completed_bar_status
                for leg in legs
            )
            or self.feature_timestamp > cutoff
        ):
            raise ValueError("profiled feature-input pair is invalid")
        expected = _pair_input_sha256(
            profile_id=self.profile_id,
            source_contract_sha256=self.source_contract_sha256,
            catalog_sha256=self.catalog_sha256,
            cutoff=cutoff,
            feature_timestamp=self.feature_timestamp,
            legs=legs,
        )
        if self.pair_input_sha256 != expected:
            raise ValueError("profiled feature-input pair hash is invalid")
        object.__setattr__(self, "cutoff", cutoff)
        object.__setattr__(self, "legs", legs)

    @property
    def feature_timestamp(self) -> datetime:
        return self.legs[0].feature_timestamp


@dataclass(frozen=True, slots=True)
class KisMtfProfileAggregate:
    """Source-safe per-profile counts and an opaque aggregate input identity."""

    profile_id: str
    feature_ready_pair_count: int
    input_unavailable_pair_count: int
    aggregate_input_sha256: str | None

    def safe_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "feature_ready_pair_count": self.feature_ready_pair_count,
            "input_unavailable_pair_count": self.input_unavailable_pair_count,
            "aggregate_input_sha256": self.aggregate_input_sha256,
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledFeatureInputContract:
    source_contract_sha256: str
    source_receipt_sha256: str
    catalog_sha256: str
    code_revision: str
    contract_sha256: str

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_RECEIPT_ID,
            "contract_sha256": self.contract_sha256,
            "source_contract_sha256": self.source_contract_sha256,
            "source_receipt_sha256": self.source_receipt_sha256,
            "catalog_sha256": self.catalog_sha256,
            "code_revision": self.code_revision,
            "geometry": {
                "source_timeframe": Timeframe.M1.value,
                "timeframes": [
                    timeframe.value for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES
                ],
                "session_cutoff": "15:30 America/New_York",
                "slow_constituents": {Timeframe.H1.value: 60, Timeframe.H3.value: 180},
            },
            "scope": _source_safe_scope(),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledFeatureInputReceipt:
    contract_sha256: str
    status: PreflightStatus
    eligible_session_count: int
    profile_aggregates: tuple[KisMtfProfileAggregate, ...]
    receipt_sha256: str

    @property
    def reason(self) -> str | None:
        return None if self.status == "feature_inputs_ready" else "causal_input_unavailable"

    def safe_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_RECEIPT_ID,
            "contract_sha256": self.contract_sha256,
            "status": self.status,
            "reason": self.reason,
            "eligible_session_count": self.eligible_session_count,
            "profile_aggregates": [
                aggregate.safe_payload() for aggregate in self.profile_aggregates
            ],
            "receipt_sha256": self.receipt_sha256,
            "scope": _source_safe_scope(),
        }


@dataclass(frozen=True, slots=True)
class KisMtfProfiledFeatureInputMaterialization:
    receipt: KisMtfProfiledFeatureInputReceipt
    pairs: tuple[KisMtfProfiledFeatureInputPair, ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class KisMtfProfiledFeatureInputRun:
    contract: KisMtfProfiledFeatureInputContract
    receipt: KisMtfProfiledFeatureInputReceipt
    run_directory: Path
    precommit_path: Path
    precommit_sha256: str
    summary_path: Path
    summary_sha256: str


def freeze_kis_mtf_profiled_feature_input_contract(
    *,
    source_contract: KisIntradayMtfAvailabilityContract,
    source_receipt: KisIntradayMtfAvailabilityReceipt,
    catalog: CausalMtfWindowProfileCatalog,
    code_revision: str,
) -> KisMtfProfiledFeatureInputContract:
    """Freeze exact source and catalog identities before profile materialization."""

    if (
        not isinstance(source_contract, KisIntradayMtfAvailabilityContract)
        or not isinstance(source_receipt, KisIntradayMtfAvailabilityReceipt)
        or source_receipt.contract_sha256 != source_contract.contract_sha256
        or catalog.identity_sha256 != KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256
    ):
        raise ValueError("profiled feature-input source bindings are invalid")
    _require_sha256(code_revision, "code_revision")
    fields = {
        "source_contract_sha256": source_contract.contract_sha256,
        "source_receipt_sha256": source_receipt.receipt_sha256,
        "catalog_sha256": catalog.identity_sha256,
        "code_revision": code_revision,
    }
    return KisMtfProfiledFeatureInputContract(
        **fields,
        contract_sha256=_sha256(
            {"receipt_id": KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_RECEIPT_ID, **fields}
        ),
    )


def materialize_kis_mtf_profiled_feature_inputs(
    *,
    contract: KisMtfProfiledFeatureInputContract,
    source_contract: KisIntradayMtfAvailabilityContract,
    source_receipt: KisIntradayMtfAvailabilityReceipt,
    catalogs: Mapping[str, CatalogedBars],
    catalog: CausalMtfWindowProfileCatalog = CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
) -> KisMtfProfiledFeatureInputMaterialization:
    """Build all fixed-profile pair inputs from verified completed minute prefixes."""

    _require_bindings(contract, source_contract, source_receipt, catalogs, catalog)
    session_dates = _common_eligible_session_dates(source_receipt)
    sources = {source.target_key: source for source in source_contract.source_identities}
    pairs: list[KisMtfProfiledFeatureInputPair] = []
    aggregates: list[KisMtfProfileAggregate] = []
    for profile in catalog.profiles:
        ready: list[KisMtfProfiledFeatureInputPair] = []
        unavailable = 0
        for session_date in session_dates:
            try:
                legs = tuple(
                    _materialize_leg(
                        source_contract_sha256=contract.source_contract_sha256,
                        source=sources[target_key],
                        source_catalog=catalogs[target_key],
                        profile_id=profile.profile_id,
                        catalog=catalog,
                        session_date=session_date,
                    )
                    for target_key in KIS_MTF_PROFILED_FEATURE_INPUT_TARGET_KEYS
                )
                pair = build_target_free_mtf_feature_pair(
                    profile.profile_id, contract.source_contract_sha256, legs
                )
            except (SequenceWindowInputError, TypeError, ValueError):
                unavailable += 1
                continue
            ready.append(pair)
            pairs.append(pair)
        aggregates.append(
            KisMtfProfileAggregate(
                profile_id=profile.profile_id,
                feature_ready_pair_count=len(ready),
                input_unavailable_pair_count=unavailable,
                aggregate_input_sha256=_aggregate_input_sha256(profile.profile_id, ready)
                if ready
                else None,
            )
        )
    aggregate_tuple = tuple(aggregates)
    all_ready = bool(session_dates) and all(
        aggregate.feature_ready_pair_count == len(session_dates) for aggregate in aggregate_tuple
    )
    status: PreflightStatus = "feature_inputs_ready" if all_ready else "input_unavailable"
    receipt_fields = {
        "contract_sha256": contract.contract_sha256,
        "status": status,
        "reason": None if all_ready else "causal_input_unavailable",
        "eligible_session_count": len(session_dates),
        "profile_aggregates": [aggregate.safe_payload() for aggregate in aggregate_tuple],
    }
    receipt = KisMtfProfiledFeatureInputReceipt(
        contract_sha256=contract.contract_sha256,
        status=status,
        eligible_session_count=len(session_dates),
        profile_aggregates=aggregate_tuple,
        receipt_sha256=_sha256(
            {"receipt_id": KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_RECEIPT_ID, **receipt_fields}
        ),
    )
    return KisMtfProfiledFeatureInputMaterialization(receipt=receipt, pairs=tuple(pairs))


def run_kis_mtf_profiled_feature_input_preflight(
    *,
    cache_root: Path | str,
    artifact_root: Path | str,
    repo_root: Path | str,
    run_label: str,
    code_revision: str,
    expected_dataset_hashes: Mapping[str, str] | None = None,
) -> KisMtfProfiledFeatureInputRun:
    """Reattest local inputs and persist one immutable aggregate-only receipt."""

    if _SAFE_RUN_LABEL.fullmatch(run_label) is None:
        raise ValueError("profiled feature-input run label is invalid")
    catalogs = load_kis_intraday_mtf_availability_catalogs(
        cache_root=Path(cache_root), repo_root=Path(repo_root)
    )
    _require_expected_dataset_hashes(catalogs, expected_dataset_hashes)
    source_contract = freeze_kis_intraday_mtf_availability_contract(
        catalogs, code_revision=code_revision
    )
    source_receipt = materialize_kis_intraday_mtf_availability(source_contract, catalogs)
    contract = freeze_kis_mtf_profiled_feature_input_contract(
        source_contract=source_contract,
        source_receipt=source_receipt,
        catalog=CANONICAL_CAUSAL_MTF_WINDOW_PROFILE_CATALOG,
        code_revision=code_revision,
    )
    run_directory = ensure_external_artifact_directory(
        Path(artifact_root),
        Path(repo_root),
        "research",
        KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_ARTIFACT_DIRECTORY,
        run_label,
    )
    precommit_path, precommit_sha256 = _write_immutable_json(
        run_directory, "precommit.json", contract.safe_payload()
    )
    receipt = materialize_kis_mtf_profiled_feature_inputs(
        contract=contract,
        source_contract=source_contract,
        source_receipt=source_receipt,
        catalogs=catalogs,
    ).receipt
    summary_path, summary_sha256 = _write_immutable_json(
        run_directory,
        "summary.json",
        {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": KIS_MTF_PROFILED_FEATURE_INPUT_PREFLIGHT_RECEIPT_ID,
            "precommit_sha256": precommit_sha256,
            "receipt": receipt.safe_payload(),
        },
    )
    return KisMtfProfiledFeatureInputRun(
        contract=contract,
        receipt=receipt,
        run_directory=run_directory,
        precommit_path=precommit_path,
        precommit_sha256=precommit_sha256,
        summary_path=summary_path,
        summary_sha256=summary_sha256,
    )


def build_target_free_mtf_feature_projection(
    *,
    source_contract_sha256: str,
    source_dataset_hash: str,
    catalog: CausalMtfWindowProfileCatalog,
    profile_id: str,
    minute_bars: Sequence[Bar],
    bars_by_timeframe: Mapping[Timeframe, Sequence[Bar]],
    cutoff: datetime,
) -> NormalizedCompletedBarProjection:
    """Create one pure normalized projection after exact slow-bar revalidation."""

    _require_sha256(source_contract_sha256, "source_contract_sha256")
    _require_sha256(source_dataset_hash, "source_dataset_hash")
    cutoff = require_utc(cutoff, "cutoff")
    if catalog.identity_sha256 != KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256:
        raise ValueError("profiled feature-input catalog identity is invalid")
    window = assess_profile_feasibility(
        catalog=catalog,
        profile_id=profile_id,
        bars_by_timeframe=bars_by_timeframe,
        cutoff=cutoff,
    ).window
    for timeframe in _SLOW_TIMEFRAMES:
        for slow_bar in window.windows[timeframe].bars:
            verify_slow_bar_constituent_containment(
                slow_bar=slow_bar, minute_bars=minute_bars, cutoff=cutoff
            )
    values = _normalized_feature_values(window)
    ends = tuple((timeframe, sequence.end_ts) for timeframe, sequence in window.windows.items())
    return NormalizedCompletedBarProjection(
        source_contract_sha256=source_contract_sha256,
        source_dataset_hash=source_dataset_hash,
        catalog_sha256=catalog.identity_sha256,
        profile_id=profile_id,
        cutoff=cutoff,
        window=window,
        feature_values=values,
        projection_sha256=_projection_sha256(
            source_contract_sha256=source_contract_sha256,
            source_dataset_hash=source_dataset_hash,
            catalog_sha256=catalog.identity_sha256,
            profile_id=profile_id,
            cutoff=cutoff,
            window_ends=ends,
            feature_values=values,
        ),
    )


def verify_slow_bar_constituent_containment(
    *,
    slow_bar: Bar,
    minute_bars: Sequence[Bar],
    cutoff: datetime,
) -> None:
    """Require exact 1m reconstruction of each selected completed 1h/3h bar."""

    cutoff = require_utc(cutoff, "cutoff")
    if (
        slow_bar.timeframe not in _SLOW_TIMEFRAMES
        or not slow_bar.complete
        or slow_bar.end_ts > cutoff
    ):
        raise ValueError("slow bar is not completed causal input")
    expected_count = int(slow_bar.timeframe.duration // Timeframe.M1.duration)
    minutes = tuple(
        sorted(
            (bar for bar in minute_bars if slow_bar.start_ts <= bar.start_ts < slow_bar.end_ts),
            key=lambda bar: bar.start_ts,
        )
    )
    expected_starts = tuple(
        slow_bar.start_ts + Timeframe.M1.duration * index for index in range(expected_count)
    )
    if (
        len(minutes) != expected_count
        or tuple(bar.start_ts for bar in minutes) != expected_starts
        or any(
            bar.timeframe != Timeframe.M1
            or not bar.complete
            or bar.end_ts > cutoff
            or bar.symbol != slow_bar.symbol
            or bar.market != slow_bar.market
            for bar in minutes
        )
    ):
        raise ValueError("slow bar minute constituents are not exact causal input")
    reconstructed = Bar(
        symbol=slow_bar.symbol,
        market=slow_bar.market,
        timeframe=slow_bar.timeframe,
        start_ts=slow_bar.start_ts,
        open=minutes[0].open,
        high=max(bar.high for bar in minutes),
        low=min(bar.low for bar in minutes),
        close=minutes[-1].close,
        volume=sum((bar.volume for bar in minutes), Decimal("0")),
        complete=True,
    )
    if reconstructed != slow_bar:
        raise ValueError("slow bar does not match its exact minute reconstruction")


def _materialize_leg(
    *,
    source_contract_sha256: str,
    source: KisIntradayMtfSourceIdentity,
    source_catalog: CatalogedBars,
    profile_id: str,
    catalog: CausalMtfWindowProfileCatalog,
    session_date: date,
) -> NormalizedCompletedBarProjection:
    session = us_equity_2026_session(session_date)
    if session is None or session.kind != "regular":
        raise ValueError("profiled feature-input session is not regular")
    cutoff = _session_cutoff(session.window)
    prefix = completed_causal_minute_prefix(
        source_catalog.bars,
        expected_symbol=source.target_key.split("/", maxsplit=1)[0],
        session=session.window,
        cutoff=cutoff,
    )
    return build_target_free_mtf_feature_projection(
        source_contract_sha256=source_contract_sha256,
        source_dataset_hash=source.dataset_hash,
        catalog=catalog,
        profile_id=profile_id,
        minute_bars=prefix,
        bars_by_timeframe=resample_completed_causal_prefix(
            prefix, session=session.window, cutoff=cutoff
        ),
        cutoff=cutoff,
    )


def build_target_free_mtf_feature_pair(
    profile_id: str,
    source_contract_sha256: str,
    legs: Sequence[NormalizedCompletedBarProjection],
) -> KisMtfProfiledFeatureInputPair:
    """Bind two normalized projections without exposing their feature values."""

    legs = tuple(legs)
    if len(legs) != 2:
        raise ValueError("profiled feature-input pair requires exactly two legs")
    cutoff = legs[0].cutoff
    return KisMtfProfiledFeatureInputPair(
        profile_id=profile_id,
        source_contract_sha256=source_contract_sha256,
        catalog_sha256=KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256,
        cutoff=cutoff,
        legs=(legs[0], legs[1]),
        pair_input_sha256=_pair_input_sha256(
            profile_id=profile_id,
            source_contract_sha256=source_contract_sha256,
            catalog_sha256=KIS_MTF_PROFILED_FEATURE_INPUT_CATALOG_SHA256,
            cutoff=cutoff,
            feature_timestamp=legs[0].feature_timestamp,
            legs=legs,
        ),
    )


def completed_causal_minute_prefix(
    bars: Sequence[Bar],
    *,
    expected_symbol: str,
    session: SessionWindow,
    cutoff: datetime,
) -> tuple[Bar, ...]:
    source = tuple(bar for bar in bars if session.open_ts <= bar.start_ts and bar.end_ts <= cutoff)
    expected_starts = tuple(
        session.open_ts + Timeframe.M1.duration * index
        for index in range(KIS_INTRADAY_MTF_AVAILABILITY_PREFIX_MINUTES)
    )
    if (
        len(source) != len(expected_starts)
        or tuple(sorted(bar.start_ts for bar in source)) != expected_starts
        or any(
            bar.timeframe != Timeframe.M1
            or not bar.complete
            or bar.end_ts > cutoff
            or bar.symbol != expected_symbol
            or bar.market != "US"
            for bar in source
        )
    ):
        raise ValueError("completed minute prefix is invalid")
    return tuple(sorted(source, key=lambda bar: bar.start_ts))


def resample_completed_causal_prefix(
    prefix: Sequence[Bar],
    *,
    session: SessionWindow,
    cutoff: datetime,
) -> dict[Timeframe, tuple[Bar, ...]]:
    result: dict[Timeframe, tuple[Bar, ...]] = {}
    for timeframe in SUPPORTED_SEQUENCE_WINDOW_TIMEFRAMES:
        resampled = resample_session_bars(prefix, timeframe, session=session)
        if any(start < cutoff for start in resampled.skipped_bucket_starts):
            raise ValueError("completed minute prefix has a skipped causal bucket")
        completed = tuple(bar for bar in resampled.bars if bar.end_ts <= cutoff)
        if not completed:
            raise ValueError("resampled causal bars are unavailable")
        result[timeframe] = completed
    return result


def _normalized_feature_values(
    window: CausalMultiTimeframeSequenceWindow,
) -> dict[Timeframe, tuple[tuple[Decimal, Decimal], ...]]:
    result: dict[Timeframe, tuple[tuple[Decimal, Decimal], ...]] = {}
    for timeframe, sequence in window.windows.items():
        anchor_close = sequence.bars[0].close
        anchor_volume = sequence.bars[0].volume or Decimal("1")
        result[timeframe] = tuple(
            (bar.close / anchor_close - Decimal("1"), bar.volume / anchor_volume - Decimal("1"))
            for bar in sequence.bars
        )
    return result


def _common_eligible_session_dates(
    source_receipt: KisIntradayMtfAvailabilityReceipt,
) -> tuple[date, ...]:
    dates = [target.eligible_session_dates for target in source_receipt.targets]
    common = set(dates[0]) if dates else set()
    for target_dates in dates[1:]:
        common.intersection_update(target_dates)
    return tuple(sorted(common))


def _require_bindings(
    contract: KisMtfProfiledFeatureInputContract,
    source_contract: KisIntradayMtfAvailabilityContract,
    source_receipt: KisIntradayMtfAvailabilityReceipt,
    catalogs: Mapping[str, CatalogedBars],
    catalog: CausalMtfWindowProfileCatalog,
) -> None:
    if (
        source_receipt.contract_sha256 != source_contract.contract_sha256
        or contract.source_contract_sha256 != source_contract.contract_sha256
        or contract.source_receipt_sha256 != source_receipt.receipt_sha256
        or contract.catalog_sha256 != catalog.identity_sha256
        or set(catalogs) != set(KIS_MTF_PROFILED_FEATURE_INPUT_TARGET_KEYS)
    ):
        raise ValueError("profiled feature-input source bindings changed")
    for source in source_contract.source_identities:
        observed = catalogs[source.target_key]
        if observed.dataset_id != source.dataset_id or observed.dataset_hash != source.dataset_hash:
            raise ValueError("profiled feature-input source identity changed")


def _require_expected_dataset_hashes(
    catalogs: Mapping[str, CatalogedBars], expected_dataset_hashes: Mapping[str, str] | None
) -> None:
    if expected_dataset_hashes is None:
        return
    if set(expected_dataset_hashes) != set(KIS_MTF_PROFILED_FEATURE_INPUT_TARGET_KEYS):
        raise ValueError("profiled feature-input expected source identities are invalid")
    for target_key, expected_hash in expected_dataset_hashes.items():
        _require_sha256(expected_hash, "expected_dataset_hash")
        if catalogs[target_key].dataset_hash != expected_hash:
            raise ValueError("profiled feature-input expected source identity changed")


def _session_cutoff(session: SessionWindow) -> datetime:
    local_open = session.open_ts.astimezone(_EASTERN)
    return local_open.replace(
        hour=KIS_MTF_PROFILED_FEATURE_INPUT_CUTOFF.hour,
        minute=KIS_MTF_PROFILED_FEATURE_INPUT_CUTOFF.minute,
        second=0,
        microsecond=0,
    ).astimezone(session.open_ts.tzinfo)


def _projection_sha256(
    *,
    source_contract_sha256: str,
    source_dataset_hash: str,
    catalog_sha256: str,
    profile_id: str,
    cutoff: datetime,
    window_ends: Sequence[tuple[Timeframe, datetime]],
    feature_values: Mapping[Timeframe, Sequence[tuple[Decimal, Decimal]]],
) -> str:
    return _sha256(
        {
            "source_contract_sha256": source_contract_sha256,
            "source_dataset_hash": source_dataset_hash,
            "catalog_sha256": catalog_sha256,
            "profile_id": profile_id,
            "cutoff": cutoff.isoformat(),
            "window_ends": [
                {"timeframe": timeframe.value, "end_ts": end_ts.isoformat()}
                for timeframe, end_ts in window_ends
            ],
            "feature_values": {
                timeframe.value: [[str(close), str(volume)] for close, volume in rows]
                for timeframe, rows in feature_values.items()
            },
        }
    )


def _pair_input_sha256(
    *,
    profile_id: str,
    source_contract_sha256: str,
    catalog_sha256: str,
    cutoff: datetime,
    feature_timestamp: datetime,
    legs: Sequence[NormalizedCompletedBarProjection],
) -> str:
    return _sha256(
        {
            "profile_id": profile_id,
            "source_contract_sha256": source_contract_sha256,
            "catalog_sha256": catalog_sha256,
            "cutoff": cutoff.isoformat(),
            "feature_timestamp": feature_timestamp.isoformat(),
            "leg_projection_sha256": [leg.projection_sha256 for leg in legs],
        }
    )


def _aggregate_input_sha256(
    profile_id: str, pairs: Sequence[KisMtfProfiledFeatureInputPair]
) -> str:
    return _sha256(
        {"profile_id": profile_id, "pair_input_sha256": [pair.pair_input_sha256 for pair in pairs]}
    )


def _source_safe_scope() -> dict[str, bool]:
    return {
        "target_or_label_opened": False,
        "return_or_cost_opened": False,
        "model_or_prediction_opened": False,
        "pnl_calculated": False,
        "gpu_used": False,
        "paper_or_broker_action": False,
        "provider_or_network_called": False,
        "credentials_or_environment_read": False,
        "raw_market_data_written": False,
        "raw_market_data_persisted": False,
    }


def _write_immutable_json(
    directory: Path,
    filename: Literal["precommit.json", "summary.json"],
    payload: Mapping[str, object],
) -> tuple[Path, str]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("profiled feature-input artifact directory is invalid")
    destination = directory / filename
    encoded = _canonical_json(payload)
    digest = _sha256_bytes(encoded)
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != encoded:
            raise ValueError("profiled feature-input immutable artifact conflicts")
        return destination, digest
    staging = directory / f".{filename}.{uuid.uuid4().hex}.stage"
    try:
        staging.write_bytes(encoded)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return destination, digest


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(_canonical_json(payload))


def _sha256_bytes(payload: bytes) -> str:
    return _SHA256_PREFIX + hashlib.sha256(payload).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if not _is_sha256(value):
        raise ValueError(f"{field_name} must use sha256:<64 lowercase hex> format")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(_SHA256_PREFIX)
        and len(value) == len(_SHA256_PREFIX) + 64
        and all(character in "0123456789abcdef" for character in value[len(_SHA256_PREFIX) :])
    )

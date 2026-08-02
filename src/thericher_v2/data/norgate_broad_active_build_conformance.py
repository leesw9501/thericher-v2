"""Taxonomize a bounded active-build comparison for the static Norgate broad panel.

This probe deliberately distinguishes a value revision on a session shared by
both series from an absent symbol or a changed session sequence.  The latter
categories are source availability facts, not evidence that a stored OHLCV
value was revised.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.norgate_daily import (
    NorgateClientUnavailableError,
    NorgateLocalUpdaterUnavailableError,
    NorgateMalformedResponseError,
    NorgateRawDailyBarProvider,
    NorgateUnavailableError,
)
from thericher_v2.data.norgate_trial_development_panel import (
    DEFAULT_MARKET_DATA_ROOT,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
    FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
    NorgateTrialDevelopmentPanelCatalog,
    load_verified_norgate_trial_development_panel_catalog,
)
from thericher_v2.data.provider import BarQuery

NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ID = "norgate-broad-d1-active-build-conformance-taxonomy-v1"
DEFAULT_NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ARTIFACT_ROOT = Path(
    "D:/thericher-v2/model-artifacts/data/norgate-broad-d1-active-build-conformance-v1"
)
FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_MANIFEST_HASH = (
    "sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e"
)

_RECEIPT_FILE = "receipt.json"
_SAFE_RUN_LABEL = re.compile(r"[a-z0-9][a-z0-9-]{0,79}", re.ASCII)
_STATUSES = {"matching", "revision_detected", "input_unavailable"}
_SOURCE_UNAVAILABLE_REASONS = {
    "active_client_unavailable",
    "active_local_source_unavailable",
    "active_source_unavailable",
}

ReaderCategory = Literal[
    "repeatable",
    "nonrepeatable",
    "response_malformed",
    "source_unavailable",
]
SeriesCategory = Literal[
    "exact_match",
    "value_mismatch",
    "symbol_absent",
    "session_coverage_mismatch",
    "reader_nonrepeatable",
    "response_malformed",
    "source_unavailable",
]


class NorgateBroadActiveBuildConformanceError(RuntimeError):
    """Raised when a broad active-build conformance receipt is invalid."""


class _ActiveResponseMalformed(NorgateBroadActiveBuildConformanceError):
    """Raised for one syntactically valid provider call with invalid bars."""


class _DailyBarProvider(Protocol):
    def get_bars(self, query: BarQuery) -> list[Bar]:
        """Return one bounded local D1 response."""


CatalogLoader = Callable[..., NorgateTrialDevelopmentPanelCatalog]


@dataclass(frozen=True, slots=True)
class NorgateBroadActiveBuildConformanceEvidence:
    """Source-safe taxonomy for one immutable panel symbol."""

    symbol: str
    reader_category: ReaderCategory
    series_category: SeriesCategory
    reference_bar_count: int
    active_bar_count: int | None
    shared_session_count: int | None
    missing_session_count: int | None
    surplus_session_count: int | None
    value_mismatch_count: int | None

    def __post_init__(self) -> None:
        if (
            not _safe_symbol(self.symbol)
            or self.reader_category
            not in {
                "repeatable",
                "nonrepeatable",
                "response_malformed",
                "source_unavailable",
            }
            or self.series_category
            not in {
                "exact_match",
                "value_mismatch",
                "symbol_absent",
                "session_coverage_mismatch",
                "reader_nonrepeatable",
                "response_malformed",
                "source_unavailable",
            }
            or not _nonnegative_int(self.reference_bar_count)
        ):
            raise ValueError("Norgate broad active-build evidence is invalid")

        values = (
            self.active_bar_count,
            self.shared_session_count,
            self.missing_session_count,
            self.surplus_session_count,
            self.value_mismatch_count,
        )
        if self.reader_category == "repeatable":
            if self.series_category not in {
                "exact_match",
                "value_mismatch",
                "symbol_absent",
                "session_coverage_mismatch",
            } or any(not _nonnegative_int(value) for value in values):
                raise ValueError("Norgate broad active-build evidence is invalid")
            assert self.active_bar_count is not None
            assert self.shared_session_count is not None
            assert self.missing_session_count is not None
            assert self.surplus_session_count is not None
            assert self.value_mismatch_count is not None
            if (
                self.reference_bar_count != self.shared_session_count + self.missing_session_count
                or self.active_bar_count != self.shared_session_count + self.surplus_session_count
            ):
                raise ValueError("Norgate broad active-build evidence geometry is invalid")
            if self.series_category == "exact_match" and any(
                value != 0
                for value in (
                    self.missing_session_count,
                    self.surplus_session_count,
                    self.value_mismatch_count,
                )
            ):
                raise ValueError("Norgate broad active-build exact evidence is invalid")
            if self.series_category == "value_mismatch" and (
                self.missing_session_count != 0
                or self.surplus_session_count != 0
                or self.value_mismatch_count <= 0
            ):
                raise ValueError("Norgate broad active-build mismatch evidence is invalid")
            if self.series_category == "symbol_absent" and (
                self.active_bar_count != 0
                or self.shared_session_count != 0
                or self.missing_session_count != self.reference_bar_count
                or self.surplus_session_count != 0
                or self.value_mismatch_count != 0
            ):
                raise ValueError("Norgate broad active-build absence evidence is invalid")
            if self.series_category == "session_coverage_mismatch" and (
                self.missing_session_count + self.surplus_session_count <= 0
            ):
                raise ValueError("Norgate broad active-build coverage evidence is invalid")
        elif (
            any(value is not None for value in values)
            or (
                self.reader_category == "nonrepeatable"
                and self.series_category != "reader_nonrepeatable"
            )
            or (
                self.reader_category == "response_malformed"
                and self.series_category != "response_malformed"
            )
            or (
                self.reader_category == "source_unavailable"
                and self.series_category != "source_unavailable"
            )
        ):
            raise ValueError("Norgate broad active-build reader evidence is invalid")

    def safe_payload(self) -> dict[str, object]:
        """Return categories and counts without raw sessions or values."""

        return {
            "symbol": self.symbol,
            "reader_category": self.reader_category,
            "series_category": self.series_category,
            "reference_bar_count": self.reference_bar_count,
            "active_bar_count": self.active_bar_count,
            "shared_session_count": self.shared_session_count,
            "missing_session_count": self.missing_session_count,
            "surplus_session_count": self.surplus_session_count,
            "value_mismatch_count": self.value_mismatch_count,
        }


@dataclass(frozen=True, slots=True)
class NorgateBroadActiveBuildConformanceResult:
    """Provider-free handle for one immutable source-safe receipt."""

    receipt_dir: Path
    receipt_sha256: str
    status: str
    reason: str
    reference_dataset_id: str
    reference_dataset_hash: str
    reference_manifest_hash: str
    selected_symbol_count: int
    common_session_count: int
    reference_bar_count: int
    observed_active_bar_count: int
    active_response_hash: str | None
    evidence: tuple[NorgateBroadActiveBuildConformanceEvidence, ...]

    def __post_init__(self) -> None:
        if (
            self.status not in _STATUSES
            or not _is_sha256(self.receipt_sha256)
            or self.reference_dataset_id != FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID
            or self.reference_dataset_hash != FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH
            or self.reference_manifest_hash != FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_MANIFEST_HASH
            or not _positive_int(self.selected_symbol_count)
            or not _positive_int(self.common_session_count)
            or self.reference_bar_count != self.selected_symbol_count * self.common_session_count
            or not _nonnegative_int(self.observed_active_bar_count)
            or (self.active_response_hash is not None and not _is_sha256(self.active_response_hash))
            or len(self.evidence) > self.selected_symbol_count
            or len({item.symbol for item in self.evidence}) != len(self.evidence)
            or self.observed_active_bar_count
            != sum(item.active_bar_count or 0 for item in self.evidence)
        ):
            raise ValueError("Norgate broad active-build result is invalid")
        _validate_result_outcome(self)

    def safe_payload(self) -> dict[str, object]:
        """Return the complete aggregate-only receipt payload."""

        counts = _evidence_counts(self.evidence)
        return {
            "status": self.status,
            "reason": self.reason,
            "selected_symbol_count": self.selected_symbol_count,
            "common_session_count": self.common_session_count,
            "reference_bar_count": self.reference_bar_count,
            "observed_active_bar_count": self.observed_active_bar_count,
            "compared_symbol_count": len(self.evidence),
            "exact_match_symbol_count": counts["exact_match"],
            "value_mismatch_symbol_count": counts["value_mismatch"],
            "symbol_absent_count": counts["symbol_absent"],
            "session_coverage_mismatch_count": counts["session_coverage_mismatch"],
            "nonrepeatable_symbol_count": counts["reader_nonrepeatable"],
            "malformed_symbol_count": counts["response_malformed"],
            "source_unavailable_symbol_count": counts["source_unavailable"],
            "active_response_sha256": self.active_response_hash,
            "per_symbol": [item.safe_payload() for item in self.evidence],
        }


def build_norgate_broad_active_build_conformance_receipt(
    *,
    destination: Path,
    artifact_root: Path = DEFAULT_NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ARTIFACT_ROOT,
    repo_root: Path | None = None,
    active_provider: _DailyBarProvider | None = None,
    catalog_loader: CatalogLoader = load_verified_norgate_trial_development_panel_catalog,
) -> NorgateBroadActiveBuildConformanceResult:
    """Run one serial local comparison or reattach an existing immutable receipt."""

    root, target, exists = _validate_destination(
        destination,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    if exists:
        return verify_norgate_broad_active_build_conformance_receipt(
            target,
            artifact_root=root,
            repo_root=repo_root,
        )

    catalog = catalog_loader(
        FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_SNAPSHOT_DIR,
        expected_dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        expected_dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
        market_data_root=DEFAULT_MARKET_DATA_ROOT,
        repo_root=repo_root,
    )
    symbols, reference, manifest_hash, common_session_count = _validated_reference_catalog(catalog)
    provider = active_provider or NorgateRawDailyBarProvider()
    evidence, active_response_hash, source_failure_reason = _compare_active_build(
        symbols,
        reference,
        provider,
    )
    if source_failure_reason is None:
        status, reason = _outcome(evidence, selected_symbol_count=len(symbols))
    else:
        status, reason = "input_unavailable", source_failure_reason

    result = NorgateBroadActiveBuildConformanceResult(
        receipt_dir=target,
        receipt_sha256="sha256:" + "0" * 64,
        status=status,
        reason=reason,
        reference_dataset_id=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID,
        reference_dataset_hash=FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH,
        reference_manifest_hash=manifest_hash,
        selected_symbol_count=len(symbols),
        common_session_count=common_session_count,
        reference_bar_count=sum(len(reference[symbol]) for symbol in symbols),
        observed_active_bar_count=sum(item.active_bar_count or 0 for item in evidence),
        active_response_hash=active_response_hash,
        evidence=evidence,
    )
    receipt = _receipt_document(result)
    _write_new_receipt(target, _json_bytes(receipt), root=root)
    return verify_norgate_broad_active_build_conformance_receipt(
        target,
        artifact_root=root,
        repo_root=repo_root,
    )


def verify_norgate_broad_active_build_conformance_receipt(
    receipt_dir: Path,
    *,
    artifact_root: Path = DEFAULT_NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ARTIFACT_ROOT,
    repo_root: Path | None = None,
    expected_receipt_sha256: str | None = None,
) -> NorgateBroadActiveBuildConformanceResult:
    """Reattach one receipt without a provider, raw panel, or credential access."""

    root, directory = _validate_existing_receipt_dir(
        receipt_dir,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    if {entry.name for entry in directory.iterdir()} != {_RECEIPT_FILE}:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt files are invalid"
        )
    contents = _read_regular_file(directory / _RECEIPT_FILE)
    actual_receipt_sha256 = _sha256(contents)
    if (
        expected_receipt_sha256 is not None
        and _sha256_text(expected_receipt_sha256, "expected receipt hash")
        != actual_receipt_sha256
    ):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt hash is not the expected value"
        )
    return _result_from_document(
        directory,
        _json_object(contents),
        receipt_sha256=actual_receipt_sha256,
        artifact_root=root,
    )


def _validated_reference_catalog(
    catalog: NorgateTrialDevelopmentPanelCatalog,
) -> tuple[tuple[str, ...], dict[str, tuple[Bar, ...]], str, int]:
    if not isinstance(catalog, NorgateTrialDevelopmentPanelCatalog):
        raise NorgateBroadActiveBuildConformanceError("Norgate broad reference catalog is invalid")
    source = catalog.source
    if (
        source.dataset_id != FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_ID
        or source.dataset_hash != FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_DATASET_HASH
        or source.manifest_hash != FROZEN_NORGATE_TRIAL_DEVELOPMENT_PANEL_MANIFEST_HASH
        or catalog.selected_symbol_count <= 0
        or len(catalog.common_sessions) <= 0
        or len(catalog.bars_by_symbol) != catalog.selected_symbol_count
        or len(catalog.candidate_ranks_by_symbol) != catalog.selected_symbol_count
        or catalog.scope.model_eligible
        or catalog.scope.gpu_eligible
        or catalog.scope.paper_trading_eligible
    ):
        raise NorgateBroadActiveBuildConformanceError("Norgate broad reference identity is invalid")
    symbols = tuple(
        sorted(
            catalog.candidate_ranks_by_symbol,
            key=lambda symbol: catalog.candidate_ranks_by_symbol[symbol],
        )
    )
    if len(symbols) != catalog.selected_symbol_count or not all(
        _safe_symbol(symbol) for symbol in symbols
    ):
        raise NorgateBroadActiveBuildConformanceError("Norgate broad reference symbols are invalid")
    reference: dict[str, tuple[Bar, ...]] = {}
    for symbol in symbols:
        series = catalog.bars_by_symbol.get(symbol)
        bars = tuple(getattr(series, "bars", ()))
        _validate_reference_series(
            bars, symbol=symbol, common_session_count=len(catalog.common_sessions)
        )
        if tuple(bar.start_ts.date() for bar in bars) != catalog.common_sessions:
            raise NorgateBroadActiveBuildConformanceError(
                "Norgate broad reference sessions are invalid"
            )
        reference[symbol] = bars
    return symbols, reference, source.manifest_hash, len(catalog.common_sessions)


def _compare_active_build(
    symbols: Sequence[str],
    reference: Mapping[str, tuple[Bar, ...]],
    provider: _DailyBarProvider,
) -> tuple[
    tuple[NorgateBroadActiveBuildConformanceEvidence, ...],
    str | None,
    str | None,
]:
    evidence: list[NorgateBroadActiveBuildConformanceEvidence] = []
    active_by_symbol: dict[str, tuple[Bar, ...]] = {}
    for symbol in symbols:
        reference_bars = reference[symbol]
        query = BarQuery(
            symbol=symbol,
            market="US",
            timeframe=Timeframe.D1,
            start_ts=reference_bars[0].start_ts,
            end_ts=reference_bars[-1].start_ts + Timeframe.D1.duration,
        )
        try:
            first = tuple(provider.get_bars(query))
            _validate_active_series(first, symbol=symbol, query=query)
            second = tuple(provider.get_bars(query))
            _validate_active_series(second, symbol=symbol, query=query)
        except NorgateMalformedResponseError:
            evidence.append(
                _reader_failure_evidence(symbol, len(reference_bars), "response_malformed")
            )
            continue
        except _ActiveResponseMalformed:
            evidence.append(
                _reader_failure_evidence(symbol, len(reference_bars), "response_malformed")
            )
            continue
        except NorgateClientUnavailableError:
            evidence.append(
                _reader_failure_evidence(symbol, len(reference_bars), "source_unavailable")
            )
            return tuple(evidence), None, "active_client_unavailable"
        except NorgateLocalUpdaterUnavailableError:
            evidence.append(
                _reader_failure_evidence(symbol, len(reference_bars), "source_unavailable")
            )
            return tuple(evidence), None, "active_local_source_unavailable"
        except NorgateUnavailableError:
            evidence.append(
                _reader_failure_evidence(symbol, len(reference_bars), "source_unavailable")
            )
            return tuple(evidence), None, "active_source_unavailable"
        if first != second:
            evidence.append(
                _reader_failure_evidence(symbol, len(reference_bars), "reader_nonrepeatable")
            )
            continue
        active_by_symbol[symbol] = first
        evidence.append(_compare_symbol(reference_bars, first, symbol=symbol))
    active_response_hash = (
        _active_response_hash(symbols, active_by_symbol)
        if len(active_by_symbol) == len(symbols)
        else None
    )
    return tuple(evidence), active_response_hash, None


def _validate_reference_series(
    bars: Sequence[Bar],
    *,
    symbol: str,
    common_session_count: int,
) -> None:
    if len(bars) != common_session_count:
        raise NorgateBroadActiveBuildConformanceError("Norgate broad reference series is invalid")
    _validate_series(bars, symbol=symbol, start=None, end=None, allow_empty=False)


def _validate_active_series(bars: Sequence[Bar], *, symbol: str, query: BarQuery) -> None:
    _validate_series(
        bars,
        symbol=symbol,
        start=query.start_ts,
        end=query.end_ts,
        allow_empty=True,
    )


def _validate_series(
    bars: Sequence[Bar],
    *,
    symbol: str,
    start: datetime | None,
    end: datetime | None,
    allow_empty: bool,
) -> None:
    if not bars and not allow_empty:
        raise _ActiveResponseMalformed("Norgate broad active response is malformed")
    previous: datetime | None = None
    for bar in bars:
        if (
            not isinstance(bar, Bar)
            or bar.symbol != symbol
            or bar.market != "US"
            or bar.timeframe is not Timeframe.D1
            or not bar.complete
            or bar.start_ts.tzinfo is not UTC
            or bar.start_ts.time() != datetime.min.time()
            or bar.open <= 0
            or bar.high < max(bar.open, bar.close)
            or bar.low > min(bar.open, bar.close)
            or (start is not None and bar.start_ts < start)
            or (end is not None and bar.start_ts >= end)
            or (previous is not None and bar.start_ts <= previous)
        ):
            raise _ActiveResponseMalformed("Norgate broad active response is malformed")
        previous = bar.start_ts


def _reader_failure_evidence(
    symbol: str,
    reference_bar_count: int,
    category: SeriesCategory,
) -> NorgateBroadActiveBuildConformanceEvidence:
    reader_category: ReaderCategory = {
        "reader_nonrepeatable": "nonrepeatable",
        "response_malformed": "response_malformed",
        "source_unavailable": "source_unavailable",
    }[category]
    return NorgateBroadActiveBuildConformanceEvidence(
        symbol=symbol,
        reader_category=reader_category,
        series_category=category,
        reference_bar_count=reference_bar_count,
        active_bar_count=None,
        shared_session_count=None,
        missing_session_count=None,
        surplus_session_count=None,
        value_mismatch_count=None,
    )


def _compare_symbol(
    reference: Sequence[Bar],
    active: Sequence[Bar],
    *,
    symbol: str,
) -> NorgateBroadActiveBuildConformanceEvidence:
    reference_by_start = {bar.start_ts: bar for bar in reference}
    active_by_start = {bar.start_ts: bar for bar in active}
    shared = reference_by_start.keys() & active_by_start.keys()
    missing = reference_by_start.keys() - active_by_start.keys()
    surplus = active_by_start.keys() - reference_by_start.keys()
    value_mismatch_count = sum(
        not _same_ohlcv(reference_by_start[start_ts], active_by_start[start_ts])
        for start_ts in shared
    )
    if not active:
        category: SeriesCategory = "symbol_absent"
    elif missing or surplus:
        category = "session_coverage_mismatch"
    elif value_mismatch_count:
        category = "value_mismatch"
    else:
        category = "exact_match"
    return NorgateBroadActiveBuildConformanceEvidence(
        symbol=symbol,
        reader_category="repeatable",
        series_category=category,
        reference_bar_count=len(reference),
        active_bar_count=len(active),
        shared_session_count=len(shared),
        missing_session_count=len(missing),
        surplus_session_count=len(surplus),
        value_mismatch_count=value_mismatch_count,
    )


def _same_ohlcv(reference: Bar, active: Bar) -> bool:
    return (
        reference.open == active.open
        and reference.high == active.high
        and reference.low == active.low
        and reference.close == active.close
        and reference.volume == active.volume
    )


def _outcome(
    evidence: Sequence[NorgateBroadActiveBuildConformanceEvidence],
    *,
    selected_symbol_count: int,
) -> tuple[str, str]:
    counts = _evidence_counts(evidence)
    if len(evidence) != selected_symbol_count or counts["response_malformed"]:
        return "input_unavailable", "active_response_malformed"
    if counts["reader_nonrepeatable"]:
        return "input_unavailable", "active_reader_nonrepeatable"
    if counts["symbol_absent"] or counts["session_coverage_mismatch"]:
        return "input_unavailable", "active_symbol_or_session_coverage_unavailable"
    if counts["value_mismatch"]:
        return "revision_detected", "shared_session_value_mismatch_detected"
    if counts["exact_match"] == selected_symbol_count:
        return "matching", "active_build_matches_broad_frozen_contract"
    raise NorgateBroadActiveBuildConformanceError("Norgate broad active-build outcome is invalid")


def _evidence_counts(
    evidence: Sequence[NorgateBroadActiveBuildConformanceEvidence],
) -> dict[str, int]:
    return {
        category: sum(item.series_category == category for item in evidence)
        for category in (
            "exact_match",
            "value_mismatch",
            "symbol_absent",
            "session_coverage_mismatch",
            "reader_nonrepeatable",
            "response_malformed",
            "source_unavailable",
        )
    }


def _validate_result_outcome(result: NorgateBroadActiveBuildConformanceResult) -> None:
    counts = _evidence_counts(result.evidence)
    complete_repeatable = (
        len(result.evidence) == result.selected_symbol_count
        and counts["reader_nonrepeatable"] == 0
        and counts["response_malformed"] == 0
        and counts["source_unavailable"] == 0
    )
    if (result.active_response_hash is not None) != complete_repeatable:
        raise ValueError("Norgate broad active-build response hash is invalid")
    if result.status == "matching":
        if (
            result.reason != "active_build_matches_broad_frozen_contract"
            or not complete_repeatable
            or counts["exact_match"] != result.selected_symbol_count
        ):
            raise ValueError("Norgate broad active-build matching result is invalid")
        return
    if result.status == "revision_detected":
        if (
            result.reason != "shared_session_value_mismatch_detected"
            or not complete_repeatable
            or counts["value_mismatch"] <= 0
            or counts["symbol_absent"]
            or counts["session_coverage_mismatch"]
        ):
            raise ValueError("Norgate broad active-build revision result is invalid")
        return
    if result.reason in _SOURCE_UNAVAILABLE_REASONS:
        if not counts["source_unavailable"] or result.active_response_hash is not None:
            raise ValueError("Norgate broad active-build unavailable result is invalid")
        return
    expected_reason = (
        "active_response_malformed"
        if counts["response_malformed"] or len(result.evidence) != result.selected_symbol_count
        else (
            "active_reader_nonrepeatable"
            if counts["reader_nonrepeatable"]
            else "active_symbol_or_session_coverage_unavailable"
        )
    )
    if result.reason != expected_reason or not (
        counts["response_malformed"]
        or counts["reader_nonrepeatable"]
        or counts["source_unavailable"]
        or counts["symbol_absent"]
        or counts["session_coverage_mismatch"]
    ):
        raise ValueError("Norgate broad active-build input result is invalid")


def _active_response_hash(
    symbols: Sequence[str], active_by_symbol: Mapping[str, Sequence[Bar]]
) -> str:
    payload = {
        "symbols": [
            {
                "symbol": symbol,
                "bars": [
                    [
                        bar.symbol,
                        bar.market,
                        bar.timeframe.value,
                        bar.start_ts.isoformat(),
                        _canonical_decimal(bar.open),
                        _canonical_decimal(bar.high),
                        _canonical_decimal(bar.low),
                        _canonical_decimal(bar.close),
                        _canonical_decimal(bar.volume),
                        bar.complete,
                    ]
                    for bar in active_by_symbol[symbol]
                ],
            }
            for symbol in symbols
        ]
    }
    return _sha256(_json_bytes(payload))


def _canonical_decimal(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _receipt_document(result: NorgateBroadActiveBuildConformanceResult) -> dict[str, object]:
    return {
        "schema_version": 2,
        "kind": "norgate_broad_d1_active_build_conformance_taxonomy_receipt",
        "probe_id": NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ID,
        "reference": {
            "dataset_id": result.reference_dataset_id,
            "dataset_hash": result.reference_dataset_hash,
            "manifest_hash": result.reference_manifest_hash,
        },
        "active_reader": {
            "two_reads_per_symbol": True,
            "serial_single_provider": True,
            "active_response_sha256": result.active_response_hash,
        },
        "outcome": result.safe_payload(),
        "source_limitations": [
            "static_current_listing_selection_not_point_in_time",
            "adjustment_semantics_unverified",
            "corporate_action_semantics_unverified",
            "availability_time_semantics_unverified",
            "matching_is_current_build_reproducibility_only",
        ],
        "target_free_integrity": {
            "raw_ohlcv_persisted": False,
            "session_dates_persisted": False,
            "source_paths_persisted": False,
            "credential_access": False,
            "network_access": False,
            "broker_access": False,
            "model_or_pnl_evaluated": False,
            "gpu_used": False,
        },
    }


def _result_from_document(
    receipt_dir: Path,
    document: dict[str, object],
    *,
    receipt_sha256: str,
    artifact_root: Path,
) -> NorgateBroadActiveBuildConformanceResult:
    if (
        set(document)
        != {
            "schema_version",
            "kind",
            "probe_id",
            "reference",
            "active_reader",
            "outcome",
            "source_limitations",
            "target_free_integrity",
        }
        or document.get("schema_version") != 2
        or document.get("kind") != "norgate_broad_d1_active_build_conformance_taxonomy_receipt"
        or document.get("probe_id") != NORGATE_BROAD_ACTIVE_BUILD_CONFORMANCE_ID
    ):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt is invalid"
        )
    reference = _mapping(document.get("reference"), "reference")
    if set(reference) != {"dataset_id", "dataset_hash", "manifest_hash"}:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build reference is invalid"
        )
    active_reader = _mapping(document.get("active_reader"), "active reader")
    if (
        set(active_reader)
        != {
            "two_reads_per_symbol",
            "serial_single_provider",
            "active_response_sha256",
        }
        or active_reader.get("two_reads_per_symbol") is not True
        or active_reader.get("serial_single_provider") is not True
    ):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build reader is invalid"
        )
    if document.get("source_limitations") != [
        "static_current_listing_selection_not_point_in_time",
        "adjustment_semantics_unverified",
        "corporate_action_semantics_unverified",
        "availability_time_semantics_unverified",
        "matching_is_current_build_reproducibility_only",
    ] or document.get("target_free_integrity") != {
        "raw_ohlcv_persisted": False,
        "session_dates_persisted": False,
        "source_paths_persisted": False,
        "credential_access": False,
        "network_access": False,
        "broker_access": False,
        "model_or_pnl_evaluated": False,
        "gpu_used": False,
    }:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt scope is invalid"
        )
    outcome = _mapping(document.get("outcome"), "outcome")
    required_outcome = {
        "status",
        "reason",
        "selected_symbol_count",
        "common_session_count",
        "reference_bar_count",
        "observed_active_bar_count",
        "compared_symbol_count",
        "exact_match_symbol_count",
        "value_mismatch_symbol_count",
        "symbol_absent_count",
        "session_coverage_mismatch_count",
        "nonrepeatable_symbol_count",
        "malformed_symbol_count",
        "source_unavailable_symbol_count",
        "active_response_sha256",
        "per_symbol",
    }
    if set(outcome) != required_outcome:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build outcome is invalid"
        )
    evidence_values = outcome.get("per_symbol")
    if not isinstance(evidence_values, list):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build evidence is invalid"
        )
    evidence = tuple(_evidence_from_document(value) for value in evidence_values)
    result = NorgateBroadActiveBuildConformanceResult(
        receipt_dir=receipt_dir,
        receipt_sha256=receipt_sha256,
        status=_text(outcome.get("status"), "status"),
        reason=_text(outcome.get("reason"), "reason"),
        reference_dataset_id=_text(reference.get("dataset_id"), "dataset id"),
        reference_dataset_hash=_sha256_text(reference.get("dataset_hash"), "dataset hash"),
        reference_manifest_hash=_sha256_text(reference.get("manifest_hash"), "manifest hash"),
        selected_symbol_count=_positive_integer(
            outcome.get("selected_symbol_count"), "selected count"
        ),
        common_session_count=_positive_integer(
            outcome.get("common_session_count"), "session count"
        ),
        reference_bar_count=_nonnegative_integer(
            outcome.get("reference_bar_count"), "reference bars"
        ),
        observed_active_bar_count=_nonnegative_integer(
            outcome.get("observed_active_bar_count"), "active bars"
        ),
        active_response_hash=_optional_sha256(outcome.get("active_response_sha256")),
        evidence=evidence,
    )
    if (
        active_reader.get("active_response_sha256") != result.active_response_hash
        or result.safe_payload() != outcome
    ):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt is inconsistent"
        )
    if not receipt_dir.is_relative_to(artifact_root):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt root is invalid"
        )
    return result


def _evidence_from_document(value: object) -> NorgateBroadActiveBuildConformanceEvidence:
    document = _mapping(value, "per-symbol evidence")
    expected = {
        "symbol",
        "reader_category",
        "series_category",
        "reference_bar_count",
        "active_bar_count",
        "shared_session_count",
        "missing_session_count",
        "surplus_session_count",
        "value_mismatch_count",
    }
    if set(document) != expected:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build evidence is invalid"
        )
    return NorgateBroadActiveBuildConformanceEvidence(
        symbol=_text(document.get("symbol"), "symbol"),
        reader_category=_text(document.get("reader_category"), "reader category"),
        series_category=_text(document.get("series_category"), "series category"),
        reference_bar_count=_nonnegative_integer(
            document.get("reference_bar_count"), "reference bar count"
        ),
        active_bar_count=_optional_nonnegative_integer(document.get("active_bar_count")),
        shared_session_count=_optional_nonnegative_integer(document.get("shared_session_count")),
        missing_session_count=_optional_nonnegative_integer(document.get("missing_session_count")),
        surplus_session_count=_optional_nonnegative_integer(document.get("surplus_session_count")),
        value_mismatch_count=_optional_nonnegative_integer(document.get("value_mismatch_count")),
    )


def _validate_destination(
    destination: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path, bool]:
    root = _validated_artifact_root(artifact_root, repo_root=repo_root)
    target = Path(destination)
    if target.is_symlink():
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt destination is invalid"
        )
    resolved_target = target.resolve(strict=False)
    if not resolved_target.is_relative_to(root) or not _SAFE_RUN_LABEL.fullmatch(
        resolved_target.name
    ):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt destination must stay under artifact root"
        )
    if target.exists():
        if not target.is_dir():
            raise NorgateBroadActiveBuildConformanceError(
                "Norgate broad active-build receipt destination is invalid"
            )
        return root, resolved_target, True
    return root, resolved_target, False


def _validate_existing_receipt_dir(
    receipt_dir: Path,
    *,
    artifact_root: Path,
    repo_root: Path | None,
) -> tuple[Path, Path]:
    root = _validated_artifact_root(artifact_root, repo_root=repo_root)
    directory = Path(receipt_dir)
    if not directory.is_dir() or directory.is_symlink():
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt is invalid"
        )
    directory = directory.resolve()
    if not directory.is_relative_to(root) or not _SAFE_RUN_LABEL.fullmatch(directory.name):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt root is invalid"
        )
    return root, directory


def _validated_artifact_root(artifact_root: Path, *, repo_root: Path | None) -> Path:
    root = Path(artifact_root)
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build artifact root is invalid"
        )
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    if repo_root is not None and root.is_relative_to(Path(repo_root).resolve()):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build artifacts must stay outside the Git workspace"
        )
    usage = shutil.disk_usage(root)
    if usage.total <= 0 or usage.free / usage.total < 0.15:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build artifact storage is below the floor"
        )
    return root


def _write_new_receipt(target: Path, content: bytes, *, root: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    resolved_target = target.resolve()
    if target.is_symlink() or not resolved_target.is_relative_to(root):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt destination is invalid"
        )
    path = resolved_target / _RECEIPT_FILE
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
    except Exception:
        shutil.rmtree(resolved_target, ignore_errors=True)
        raise


def _read_regular_file(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt is invalid"
        )
    return path.read_bytes()


def _json_object(contents: bytes) -> dict[str, object]:
    try:
        value = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt is invalid"
        ) from exc
    if not isinstance(value, dict):
        raise NorgateBroadActiveBuildConformanceError(
            "Norgate broad active-build receipt is invalid"
        )
    return value


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise NorgateBroadActiveBuildConformanceError(
            f"Norgate broad active-build {label} is invalid"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NorgateBroadActiveBuildConformanceError(
            f"Norgate broad active-build {label} is invalid"
        )
    return value


def _sha256_text(value: object, label: str) -> str:
    text = _text(value, label)
    if not _is_sha256(text):
        raise NorgateBroadActiveBuildConformanceError(
            f"Norgate broad active-build {label} is invalid"
        )
    return text


def _optional_sha256(value: object) -> str | None:
    if value is None:
        return None
    return _sha256_text(value, "response hash")


def _positive_integer(value: object, label: str) -> int:
    if not _positive_int(value):
        raise NorgateBroadActiveBuildConformanceError(
            f"Norgate broad active-build {label} is invalid"
        )
    assert isinstance(value, int)
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if not _nonnegative_int(value):
        raise NorgateBroadActiveBuildConformanceError(
            f"Norgate broad active-build {label} is invalid"
        )
    assert isinstance(value, int)
    return value


def _optional_nonnegative_integer(value: object) -> int | None:
    if value is None:
        return None
    return _nonnegative_integer(value, "optional count")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def _positive_int(value: object) -> bool:
    return _nonnegative_int(value) and value > 0


def _nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _safe_symbol(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 32
        and value.isascii()
        and not any(character.isspace() for character in value)
    )

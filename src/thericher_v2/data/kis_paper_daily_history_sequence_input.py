"""Phase-local Research inputs from the reattested NAS daily-history panel.

The historical panel owns source reattestation.  This adapter binds its one
known-good common-session intersection to the frozen chronological campaign
geometry before Research can derive a feature or a target.  It stays offline:
no provider, environment, broker, model, or artifact dependency appears here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from thericher_v2.contracts import SCHEMA_VERSION, Timeframe
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_ROOT,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
    load_materialized_kis_paper_daily_history_panel,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader

KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_VERSION = "kis-paper-daily-nas-sequence-input-v1"
KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID = "kis.paper.private.daily.nas.sequence.input-v1"
KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH = (
    "sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e"
)
KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH = (
    KIS_PAPER_DAILY_HISTORY_PANEL_ROOT
    / "panel=7e8d6fe54dd5252fc4b9"
    / "manifest.json"
)
KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT = 1510
KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT = 22
KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT = 647
KIS_PAPER_DAILY_HISTORY_SEQUENCE_TOTAL_SESSION_COUNT = (
    KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT
    + KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT
    + KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT
)
KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS = (
    "MODP=0_unadjusted",
    "corporate_action_semantics_not_qualified",
    "current_listing_registry_not_point_in_time_universe",
    "source_local_only_no_cross_source_blend",
)

KisPaperDailyHistorySequencePhase = Literal["development", "purge", "validation"]
_PHASES: tuple[KisPaperDailyHistorySequencePhase, ...] = (
    "development",
    "purge",
    "validation",
)
_INPUT_ATTESTATION = object()


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyHistorySequencePhaseInput:
    """One immutable chronological phase with source-local D1 streams only."""

    phase: KisPaperDailyHistorySequencePhase
    parent_dataset_id: str
    parent_dataset_hash: str
    index_hash: str
    source_index_path: Path
    common_sessions: tuple[date, ...]
    bars_by_symbol: Mapping[str, CatalogedBars]
    targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    raw_price_limitations: tuple[str, ...]
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified NAS daily-history sequence input adapter")

    def stream(self, symbol: str) -> CatalogedBars:
        """Return an immutable stream only after validating the adapter boundary."""

        require_attested_kis_paper_daily_history_sequence_phase_input(self)
        resolved = symbol.strip().upper()
        if resolved not in self.bars_by_symbol:
            raise ValueError("NAS daily-history sequence symbol is unsupported")
        return self.bars_by_symbol[resolved]

    def safe_payload(self) -> dict[str, object]:
        """Return provenance and timing facts without rows, prices, or values."""

        require_attested_kis_paper_daily_history_sequence_phase_input(self)
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_history_sequence_phase_input",
            "phase": self.phase,
            "parent_dataset_id": self.parent_dataset_id,
            "parent_dataset_hash": self.parent_dataset_hash,
            "index_hash": self.index_hash,
            "session_count": len(self.common_sessions),
            "session_start": self.common_sessions[0].isoformat(),
            "session_end": self.common_sessions[-1].isoformat(),
            "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
            "source_target_states": [
                {
                    "target_key": target.target_key,
                    "state": target.state,
                    "last_reason": target.last_reason,
                    "coverage_start_bucket": target.coverage_start_bucket,
                    "coverage_end_bucket": target.coverage_end_bucket,
                }
                for target in self.targets_by_key.values()
            ],
            "source_local_only": True,
            "raw_rows_persisted": False,
        }


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyHistorySequenceInput:
    """The one fixed 1,510 / 22 / 647 session handoff into Research."""

    input_id: str
    panel_dataset_id: str
    panel_dataset_hash: str
    index_hash: str
    adjustment_mode: str
    source_index_path: Path
    source_targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    raw_price_limitations: tuple[str, ...]
    development: KisPaperDailyHistorySequencePhaseInput
    purge: KisPaperDailyHistorySequencePhaseInput
    validation: KisPaperDailyHistorySequencePhaseInput
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified NAS daily-history sequence input loader")

    def phase(
        self,
        name: KisPaperDailyHistorySequencePhase,
    ) -> KisPaperDailyHistorySequencePhaseInput:
        require_attested_kis_paper_daily_history_sequence_input(self)
        return getattr(self, name)

    def safe_payload(self) -> dict[str, object]:
        """Return a source-safe handoff identity for a Research precommit."""

        require_attested_kis_paper_daily_history_sequence_input(self)
        return {
            "schema_version": self.schema_version,
            "kind": "kis_paper_daily_history_sequence_input",
            "input_id": self.input_id,
            "panel_dataset_id": self.panel_dataset_id,
            "panel_dataset_hash": self.panel_dataset_hash,
            "index_hash": self.index_hash,
            "adjustment_mode": self.adjustment_mode,
            "symbols": list(KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS),
            "phases": {
                phase: getattr(self, phase).safe_payload()
                for phase in _PHASES
            },
            "raw_price_limitations": list(self.raw_price_limitations),
            "source_local_only": True,
            "ranking_eligible": False,
            "paper_trading_eligible": False,
        }


def load_kis_paper_daily_history_sequence_input(
    manifest_path: Path | str = KIS_PAPER_DAILY_HISTORY_SEQUENCE_PANEL_MANIFEST_PATH,
    *,
    cache_root: Path | str = KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    panel_root: Path | str = KIS_PAPER_DAILY_HISTORY_PANEL_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyHistorySequenceInput:
    """Reattest the panel/cache before exposing any phase to Research."""

    panel = load_materialized_kis_paper_daily_history_panel(
        manifest_path,
        cache_root=cache_root,
        panel_root=panel_root,
        repo_root=repo_root,
    )
    return _prepare_kis_paper_daily_history_sequence_input(panel)


def _prepare_kis_paper_daily_history_sequence_input(
    panel: KisPaperDailyHistoryPanel,
) -> KisPaperDailyHistorySequenceInput:
    """Freeze the exact source-local phases from an already reattested panel."""

    _validate_panel(panel)
    development_stop = KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT
    purge_stop = development_stop + KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT
    development = _phase_from_verified_panel(
        panel=panel,
        phase="development",
        start_index=0,
        stop_index=development_stop,
    )
    purge = _phase_from_verified_panel(
        panel=panel,
        phase="purge",
        start_index=development_stop,
        stop_index=purge_stop,
    )
    validation = _phase_from_verified_panel(
        panel=panel,
        phase="validation",
        start_index=purge_stop,
        stop_index=KIS_PAPER_DAILY_HISTORY_SEQUENCE_TOTAL_SESSION_COUNT,
    )
    result = object.__new__(KisPaperDailyHistorySequenceInput)
    object.__setattr__(result, "input_id", KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID)
    object.__setattr__(result, "panel_dataset_id", panel.dataset_id)
    object.__setattr__(result, "panel_dataset_hash", panel.dataset_hash)
    object.__setattr__(result, "index_hash", panel.index_hash)
    object.__setattr__(result, "adjustment_mode", panel.adjustment_mode)
    object.__setattr__(result, "source_index_path", panel.index_path)
    object.__setattr__(
        result,
        "source_targets_by_key",
        MappingProxyType(dict(panel.targets_by_key)),
    )
    object.__setattr__(result, "raw_price_limitations", panel.raw_price_limitations)
    object.__setattr__(result, "development", development)
    object.__setattr__(result, "purge", purge)
    object.__setattr__(result, "validation", validation)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _INPUT_ATTESTATION)
    require_attested_kis_paper_daily_history_sequence_input(result)
    return result


def require_attested_kis_paper_daily_history_sequence_input(
    input: object,
) -> None:
    """Fail closed unless the exact frozen panel and phase geometry still agree."""

    if (
        not isinstance(input, KisPaperDailyHistorySequenceInput)
        or getattr(input, "_attestation", None) is not _INPUT_ATTESTATION
        or input.input_id != KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_ID
        or input.panel_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or input.panel_dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
        or input.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        or input.raw_price_limitations != KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS
        or input.schema_version != SCHEMA_VERSION
        or tuple(input.source_targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or input.source_index_path.is_symlink()
        or not input.source_index_path.is_file()
    ):
        raise ValueError("NAS daily-history sequence input requires a verified panel")
    phases = (input.development, input.purge, input.validation)
    if tuple(phase.phase for phase in phases) != _PHASES:
        raise ValueError("NAS daily-history sequence phase order is invalid")
    expected_counts = (
        KIS_PAPER_DAILY_HISTORY_SEQUENCE_DEVELOPMENT_SESSION_COUNT,
        KIS_PAPER_DAILY_HISTORY_SEQUENCE_PURGE_SESSION_COUNT,
        KIS_PAPER_DAILY_HISTORY_SEQUENCE_VALIDATION_SESSION_COUNT,
    )
    for phase, expected_count in zip(phases, expected_counts, strict=True):
        require_attested_kis_paper_daily_history_sequence_phase_input(phase)
        if (
            phase.parent_dataset_id != input.panel_dataset_id
            or phase.parent_dataset_hash != input.panel_dataset_hash
            or phase.index_hash != input.index_hash
            or phase.source_index_path != input.source_index_path
            or phase.targets_by_key != input.source_targets_by_key
            or phase.raw_price_limitations != input.raw_price_limitations
            or len(phase.common_sessions) != expected_count
        ):
            raise ValueError("NAS daily-history sequence phase provenance is invalid")
    combined_sessions = (
        input.development.common_sessions
        + input.purge.common_sessions
        + input.validation.common_sessions
    )
    if (
        len(combined_sessions) != KIS_PAPER_DAILY_HISTORY_SEQUENCE_TOTAL_SESSION_COUNT
        or tuple(sorted(combined_sessions)) != combined_sessions
        or len(set(combined_sessions)) != len(combined_sessions)
    ):
        raise ValueError("NAS daily-history sequence phases are not contiguous")


def require_attested_kis_paper_daily_history_sequence_phase_input(
    input: object,
) -> None:
    """Fail closed before a phase stream can be used as a feature source."""

    if (
        not isinstance(input, KisPaperDailyHistorySequencePhaseInput)
        or getattr(input, "_attestation", None) is not _INPUT_ATTESTATION
        or input.phase not in _PHASES
        or input.parent_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or input.parent_dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
        or input.raw_price_limitations != KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS
        or input.schema_version != SCHEMA_VERSION
        or tuple(input.bars_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(input.targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or not input.common_sessions
        or tuple(sorted(input.common_sessions)) != input.common_sessions
        or len(set(input.common_sessions)) != len(input.common_sessions)
        or input.source_index_path.is_symlink()
        or not input.source_index_path.is_file()
    ):
        raise ValueError("NAS daily-history sequence phase requires a verified input")
    for symbol, stream in input.bars_by_symbol.items():
        if (
            not isinstance(stream, CatalogedBars)
            or stream.source_path != input.source_index_path
            or stream.dataset_id != _phase_dataset_id(
                parent_dataset_id=input.parent_dataset_id,
                phase=input.phase,
                sessions=input.common_sessions,
            )
            or stream.dataset_hash
            != _phase_dataset_hash(
                parent_dataset_hash=input.parent_dataset_hash,
                index_hash=input.index_hash,
                phase=input.phase,
                sessions=input.common_sessions,
            )
            or len(stream.bars) != len(input.common_sessions)
            or tuple(bar.start_ts.date() for bar in stream.bars) != input.common_sessions
            or any(
                bar.symbol != symbol
                or bar.market != "US"
                or bar.timeframe is not Timeframe.D1
                or not bar.complete
                for bar in stream.bars
            )
        ):
            raise ValueError("NAS daily-history sequence phase stream is invalid")


def _validate_panel(panel: object) -> None:
    if (
        not isinstance(panel, KisPaperDailyHistoryPanel)
        or panel.dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or panel.dataset_hash != KIS_PAPER_DAILY_HISTORY_SEQUENCE_EXPECTED_DATASET_HASH
        or panel.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        or tuple(panel.bars_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(panel.targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or len(panel.common_sessions) != KIS_PAPER_DAILY_HISTORY_SEQUENCE_TOTAL_SESSION_COUNT
        or tuple(sorted(panel.common_sessions)) != panel.common_sessions
        or len(set(panel.common_sessions)) != len(panel.common_sessions)
        or panel.raw_price_limitations != KIS_PAPER_DAILY_HISTORY_SEQUENCE_SOURCE_LIMITATIONS
        or panel.index_path.is_symlink()
        or panel.source_root.is_symlink()
        or not panel.index_path.is_file()
        or not panel.source_root.is_dir()
        or panel.index_path.parent != panel.source_root
    ):
        raise ValueError("NAS daily-history panel does not satisfy the sequence contract")
    for symbol, stream in panel.bars_by_symbol.items():
        target = panel.targets_by_key.get(f"{symbol}/NAS")
        if (
            target is None
            or stream.source_path != panel.index_path
            or stream.dataset_id != panel.dataset_id
            or stream.dataset_hash != panel.dataset_hash
            or len(stream.bars) < KIS_PAPER_DAILY_HISTORY_SEQUENCE_TOTAL_SESSION_COUNT
            or not set(panel.common_sessions).issubset(
                {bar.start_ts.date() for bar in stream.bars}
            )
            or any(
                bar.symbol != symbol
                or bar.market != "US"
                or bar.timeframe is not Timeframe.D1
                or not bar.complete
                for bar in stream.bars
            )
        ):
            raise ValueError("NAS daily-history panel stream is incompatible")


def _phase_from_verified_panel(
    *,
    panel: KisPaperDailyHistoryPanel,
    phase: KisPaperDailyHistorySequencePhase,
    start_index: int,
    stop_index: int,
) -> KisPaperDailyHistorySequencePhaseInput:
    sessions = panel.common_sessions[start_index:stop_index]
    if not sessions or len(sessions) != stop_index - start_index:
        raise ValueError("NAS daily-history sequence phase slice is invalid")
    dataset_id = _phase_dataset_id(
        parent_dataset_id=panel.dataset_id,
        phase=phase,
        sessions=sessions,
    )
    dataset_hash = _phase_dataset_hash(
        parent_dataset_hash=panel.dataset_hash,
        index_hash=panel.index_hash,
        phase=phase,
        sessions=sessions,
    )
    bars_by_symbol: dict[str, CatalogedBars] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        stream = panel.bars_by_symbol[symbol]
        bars_by_session = {bar.start_ts.date(): bar for bar in stream.bars}
        bars = tuple(bars_by_session[session] for session in sessions)
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            source_path=panel.index_path,
            bars=bars,
        )
    result = object.__new__(KisPaperDailyHistorySequencePhaseInput)
    object.__setattr__(result, "phase", phase)
    object.__setattr__(result, "parent_dataset_id", panel.dataset_id)
    object.__setattr__(result, "parent_dataset_hash", panel.dataset_hash)
    object.__setattr__(result, "index_hash", panel.index_hash)
    object.__setattr__(result, "source_index_path", panel.index_path)
    object.__setattr__(result, "common_sessions", sessions)
    object.__setattr__(result, "bars_by_symbol", MappingProxyType(bars_by_symbol))
    object.__setattr__(result, "targets_by_key", MappingProxyType(dict(panel.targets_by_key)))
    object.__setattr__(result, "raw_price_limitations", panel.raw_price_limitations)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _INPUT_ATTESTATION)
    require_attested_kis_paper_daily_history_sequence_phase_input(result)
    return result


def _phase_dataset_id(
    *,
    parent_dataset_id: str,
    phase: KisPaperDailyHistorySequencePhase,
    sessions: tuple[date, ...],
) -> str:
    return (
        f"{parent_dataset_id}:{KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_VERSION}:"
        f"{phase}:{len(sessions)}"
    )


def _phase_dataset_hash(
    *,
    parent_dataset_hash: str,
    index_hash: str,
    phase: KisPaperDailyHistorySequencePhase,
    sessions: tuple[date, ...],
) -> str:
    payload = {
        "parent_dataset_hash": parent_dataset_hash,
        "index_hash": index_hash,
        "input_version": KIS_PAPER_DAILY_HISTORY_SEQUENCE_INPUT_VERSION,
        "phase": phase,
        "sessions": [session.isoformat() for session in sessions],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()

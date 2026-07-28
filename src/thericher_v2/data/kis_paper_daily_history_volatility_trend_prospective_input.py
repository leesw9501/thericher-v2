"""Offline prospective-session metadata for the NAS D1 trend package.

The daily-history panel remains the only owner of raw local rows.  This
adapter reattests that panel, then exposes only a caller-pinned freshness
boundary and the exact six-symbol common sessions after it.  It neither fetches
nor writes data and deliberately retains no bars or price values.
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
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
    build_kis_paper_daily_history_panel,
)
from thericher_v2.data.local import CatalogedBars

KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_VERSION = (
    "kis-paper-daily-nas-volatility-trend-prospective-input-v1"
)
KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_ID = (
    "kis.paper.private.daily.nas.volatility-trend.prospective-input-v1"
)

KisPaperDailyHistoryVolatilityTrendProspectiveStatus = Literal[
    "ready", "input_unavailable"
]

KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_TARGET_SLOT_SESSION_COUNT = 3

_INPUT_ATTESTATION = object()
_SOURCE_SAFE_FORBIDDEN_FIELDS = frozenset(
    {
        "bars",
        "close",
        "entry",
        "exit",
        "feature_sequence",
        "high",
        "low",
        "open",
        "prediction",
        "predictions",
        "price",
        "prices",
        "target",
        "targets",
        "volume",
    }
)


@dataclass(frozen=True, slots=True, init=False)
class KisPaperDailyHistoryVolatilityTrendProspectiveInput:
    """Source-safe, all-symbol post-boundary D1 session availability."""

    input_id: str
    panel_dataset_id: str
    panel_dataset_hash: str
    index_hash: str
    adjustment_mode: str
    source_index_path: Path
    source_targets_by_key: Mapping[str, KisPaperDailyHistoryPanelTarget]
    raw_price_limitations: tuple[str, ...]
    frozen_boundary: date
    post_boundary_common_sessions: tuple[date, ...]
    eligible_target_slot_count: int
    status: KisPaperDailyHistoryVolatilityTrendProspectiveStatus
    prospective_input_hash: str
    schema_version: int
    _attestation: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("use the verified NAS D1 prospective input loader")

    @property
    def input_available(self) -> bool:
        """Whether one non-overlapping decision/entry/exit slot is available."""

        require_attested_kis_paper_daily_history_volatility_trend_prospective_input(
            self
        )
        return self.status == "ready"

    def safe_payload(self) -> dict[str, object]:
        """Return provenance and session geometry without raw market values."""

        require_attested_kis_paper_daily_history_volatility_trend_prospective_input(
            self
        )
        common_sessions = {
            "all_symbols_exact": True,
            "count": len(self.post_boundary_common_sessions),
            "dates_sha256": _session_dates_hash(self.post_boundary_common_sessions),
        }
        if self.post_boundary_common_sessions:
            common_sessions["start"] = self.post_boundary_common_sessions[0].isoformat()
            common_sessions["end"] = self.post_boundary_common_sessions[-1].isoformat()
        payload = {
            "schema_version": self.schema_version,
            "kind": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_ID,
            "version": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_VERSION,
            "status": self.status,
            "source": {
                "panel_dataset_id": self.panel_dataset_id,
                "panel_dataset_hash": self.panel_dataset_hash,
                "index_hash": self.index_hash,
                "adjustment_mode": self.adjustment_mode,
                "target_states": [
                    _target_state_payload(target)
                    for target in self.source_targets_by_key.values()
                ],
            },
            "freshness": {
                "frozen_boundary": self.frozen_boundary.isoformat(),
                "strictly_after_boundary": True,
                "post_boundary_common_sessions": common_sessions,
                "target_slot_contract": {
                    "decision_then_following_complete_sessions": 2,
                    "complete_common_sessions_per_slot": (
                        KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_TARGET_SLOT_SESSION_COUNT
                    ),
                    "non_overlapping": True,
                    "eligible_target_slot_count": self.eligible_target_slot_count,
                },
            },
            "limitations": list(self.raw_price_limitations),
            "prospective_input_hash": self.prospective_input_hash,
            "source_local_only": True,
            "raw_rows_persisted": False,
        }
        _assert_source_safe(payload)
        return payload


def load_kis_paper_daily_history_volatility_trend_prospective_input(
    *,
    frozen_boundary: date,
    cache_root: Path | str = KIS_PAPER_DAILY_HISTORY_CACHE_ROOT,
    repo_root: Path | str | None = None,
) -> KisPaperDailyHistoryVolatilityTrendProspectiveInput:
    """Reattest the current local panel before exposing prospective metadata."""

    panel = build_kis_paper_daily_history_panel(cache_root, repo_root=repo_root)
    return build_kis_paper_daily_history_volatility_trend_prospective_input(
        panel,
        frozen_boundary=frozen_boundary,
    )


def build_kis_paper_daily_history_volatility_trend_prospective_input(
    panel: KisPaperDailyHistoryPanel,
    *,
    frozen_boundary: date,
) -> KisPaperDailyHistoryVolatilityTrendProspectiveInput:
    """Project one already reattested panel to exact post-boundary availability."""

    _require_date(frozen_boundary, "frozen boundary")
    _validate_panel(panel)
    post_boundary_common_sessions = tuple(
        session for session in panel.common_sessions if session > frozen_boundary
    )
    eligible_target_slot_count = (
        len(post_boundary_common_sessions)
        // KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_TARGET_SLOT_SESSION_COUNT
    )
    status: KisPaperDailyHistoryVolatilityTrendProspectiveStatus = (
        "ready" if eligible_target_slot_count else "input_unavailable"
    )
    result = object.__new__(KisPaperDailyHistoryVolatilityTrendProspectiveInput)
    object.__setattr__(
        result,
        "input_id",
        KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_ID,
    )
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
    object.__setattr__(result, "frozen_boundary", frozen_boundary)
    object.__setattr__(
        result,
        "post_boundary_common_sessions",
        post_boundary_common_sessions,
    )
    object.__setattr__(result, "eligible_target_slot_count", eligible_target_slot_count)
    object.__setattr__(result, "status", status)
    object.__setattr__(result, "schema_version", SCHEMA_VERSION)
    object.__setattr__(result, "_attestation", _INPUT_ATTESTATION)
    object.__setattr__(result, "prospective_input_hash", _input_hash(result))
    require_attested_kis_paper_daily_history_volatility_trend_prospective_input(
        result
    )
    return result


def require_attested_kis_paper_daily_history_volatility_trend_prospective_input(
    value: object,
) -> None:
    """Fail closed before a prospective observer trusts freshness metadata."""

    if (
        not isinstance(value, KisPaperDailyHistoryVolatilityTrendProspectiveInput)
        or getattr(value, "_attestation", None) is not _INPUT_ATTESTATION
        or value.input_id
        != KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_ID
        or value.panel_dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or value.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        or value.schema_version != SCHEMA_VERSION
        or tuple(value.source_targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or value.source_index_path.is_symlink()
        or not value.source_index_path.is_file()
        or not _is_sha256(value.panel_dataset_hash)
        or not _is_sha256(value.index_hash)
        or not _is_sha256(value.prospective_input_hash)
        or value.status not in {"ready", "input_unavailable"}
    ):
        raise ValueError("NAS D1 prospective input requires an attested panel")
    _require_date(value.frozen_boundary, "frozen boundary")
    _validate_targets(value.source_targets_by_key)
    if (
        tuple(sorted(value.post_boundary_common_sessions))
        != value.post_boundary_common_sessions
        or len(set(value.post_boundary_common_sessions))
        != len(value.post_boundary_common_sessions)
        or any(
            session <= value.frozen_boundary
            for session in value.post_boundary_common_sessions
        )
        or value.eligible_target_slot_count
        != len(value.post_boundary_common_sessions)
        // KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_TARGET_SLOT_SESSION_COUNT
        or (value.status == "ready") != bool(value.eligible_target_slot_count)
        or value.prospective_input_hash != _input_hash(value)
    ):
        raise ValueError("NAS D1 prospective input provenance is invalid")


def _validate_panel(panel: object) -> None:
    if (
        not isinstance(panel, KisPaperDailyHistoryPanel)
        or panel.dataset_id != KIS_PAPER_DAILY_HISTORY_PANEL_ID
        or panel.adjustment_mode != KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE
        or tuple(panel.bars_by_symbol) != KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS
        or tuple(panel.targets_by_key) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS
        or tuple(sorted(panel.common_sessions)) != panel.common_sessions
        or len(set(panel.common_sessions)) != len(panel.common_sessions)
        or panel.index_path.is_symlink()
        or panel.source_root.is_symlink()
        or not panel.index_path.is_file()
        or not panel.source_root.is_dir()
        or panel.index_path.parent != panel.source_root
        or not _is_sha256(panel.dataset_hash)
        or not _is_sha256(panel.index_hash)
    ):
        raise ValueError("NAS D1 prospective panel is invalid")
    _validate_targets(panel.targets_by_key)
    sessions_by_symbol: list[set[date]] = []
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        stream = panel.bars_by_symbol[symbol]
        target = panel.targets_by_key[f"{symbol}/NAS"]
        if (
            not isinstance(stream, CatalogedBars)
            or stream.dataset_id != panel.dataset_id
            or stream.dataset_hash != panel.dataset_hash
            or stream.source_path != panel.index_path
            or len(stream.bars) != target.bar_count
        ):
            raise ValueError("NAS D1 prospective panel stream is invalid")
        sessions = set()
        for bar in stream.bars:
            if (
                bar.symbol != symbol
                or bar.market != "US"
                or bar.timeframe is not Timeframe.D1
                or not bar.complete
            ):
                raise ValueError("NAS D1 prospective panel stream is invalid")
            sessions.add(bar.start_ts.date())
        if not sessions:
            raise ValueError("NAS D1 prospective panel stream is empty")
        sessions_by_symbol.append(sessions)
    if tuple(sorted(set.intersection(*sessions_by_symbol))) != panel.common_sessions:
        raise ValueError("NAS D1 prospective panel common sessions are invalid")


def _validate_targets(
    targets: Mapping[str, KisPaperDailyHistoryPanelTarget],
) -> None:
    if tuple(targets) != KIS_PAPER_DAILY_HISTORY_PANEL_TARGET_KEYS:
        raise ValueError("NAS D1 prospective panel targets are invalid")
    for target_key, target in targets.items():
        if (
            not isinstance(target, KisPaperDailyHistoryPanelTarget)
            or target.target_key != target_key
        ):
            raise ValueError("NAS D1 prospective panel target is invalid")


def _input_hash(value: KisPaperDailyHistoryVolatilityTrendProspectiveInput) -> str:
    return _sha256_json(
        {
            "kind": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_ID,
            "version": KIS_PAPER_DAILY_HISTORY_VOLATILITY_TREND_PROSPECTIVE_INPUT_VERSION,
            "schema_version": value.schema_version,
            "panel_dataset_id": value.panel_dataset_id,
            "panel_dataset_hash": value.panel_dataset_hash,
            "index_hash": value.index_hash,
            "adjustment_mode": value.adjustment_mode,
            "target_states": [
                _target_state_payload(target)
                for target in value.source_targets_by_key.values()
            ],
            "raw_price_limitations": list(value.raw_price_limitations),
            "frozen_boundary": value.frozen_boundary.isoformat(),
            "post_boundary_common_sessions": [
                session.isoformat() for session in value.post_boundary_common_sessions
            ],
            "eligible_target_slot_count": value.eligible_target_slot_count,
            "status": value.status,
        }
    )


def _target_state_payload(target: KisPaperDailyHistoryPanelTarget) -> dict[str, object]:
    return {
        "target_key": target.target_key,
        "state": target.state,
        "last_reason": target.last_reason,
        "coverage_start_bucket": target.coverage_start_bucket,
        "coverage_end_bucket": target.coverage_end_bucket,
    }


def _session_dates_hash(sessions: tuple[date, ...]) -> str:
    return _sha256_json({"sessions": [session.isoformat() for session in sessions]})


def _assert_source_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _SOURCE_SAFE_FORBIDDEN_FIELDS:
                raise ValueError("NAS D1 prospective payload contains source values")
            _assert_source_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_source_safe(nested)


def _require_date(value: object, name: str) -> None:
    if type(value) is not date:
        raise ValueError(f"NAS D1 prospective {name} is invalid")


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        return False
    return True


def _sha256_json(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()

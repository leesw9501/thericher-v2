"""Read-only input boundary for the fixed KIS broad-D1 momentum benchmark.

This consumer reattests one immutable selected broad panel entirely in memory.
It does not repair cache rows, persist an artifact, or reach any provider.  The
result intentionally retains the source-local limitations of the selected
panel; it is a narrow causal bar input, not a ranking or promotion decision.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from thericher_v2.contracts import SCHEMA_VERSION, Bar, Timeframe
from thericher_v2.data.kis_broad_d1_geometry_audit import (
    KisBroadD1GeometryAudit,
    KisBroadD1GeometryAuditSpec,
    KisBroadD1GeometryAuditUnavailable,
    build_kis_broad_d1_geometry_audit_from_selection,
)
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanelSelection,
    load_materialized_kis_paper_daily_broad_panel_selection,
)

KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_INPUT_ID = (
    "kis-broad-d1-cross-sectional-momentum-input-v1"
)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS = (5, 20, 60)
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TARGET_COUNT = 128
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT = 800
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TERMINAL_BUFFER_SESSIONS = 1
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_RAW_BYTE_ATTESTATION_LIMIT = 512
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_RANGE_RATIO = 2.0
KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ADDITIONAL_LIMITATION = (
    "alternate_daily_representation_semantics_unproven"
)

_UNAVAILABLE_CODES = frozenset(
    {
        "insufficient_coverage",
        "insufficient_eligible_symbols",
        "geometry_audit_mismatch",
        "malformed_or_changed_source",
    }
)


class KisBroadD1CrossSectionalMomentumInputUnavailable(ValueError):
    """The immutable source cannot satisfy this frozen input contract."""

    def __init__(self, code: str) -> None:
        if code not in _UNAVAILABLE_CODES:
            raise ValueError("KIS broad D1 momentum input unavailable code is invalid")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class KisBroadD1CrossSectionalMomentumInput:
    """One immutable completed-bar grid with deterministic event availability.

    Every target has exactly the 800 decision-session bars and one completed
    terminal execution bar.  The terminal bar is never part of a feature
    window, so a decision at the last grid session cannot see beyond its own
    completed D1 bar.
    """

    dataset_id: str
    dataset_hash: str
    manifest_sha256: str
    materialization_receipt_sha256: str
    source_index_hash: str
    target_key_set_hash: str
    geometry_audit_receipt_sha256: str
    geometry_audit_contract_sha256: str
    geometry_audit_source_grid_sha256: str
    geometry_audit_event_mask_sha256: str
    full_target_count: int
    coverage_eligible_target_count: int
    raw_byte_attested_target_count: int
    selected_target_keys: tuple[str, ...]
    decision_session_grid: tuple[datetime, ...]
    terminal_execution_session: datetime
    grid_bars_by_target: Mapping[str, tuple[Bar, ...]]
    terminal_execution_bars_by_target: Mapping[str, Bar]
    range_event_flags_by_target: Mapping[str, tuple[bool, ...]]
    event_availability_by_lookback: Mapping[int, Mapping[str, tuple[bool, ...]]]
    limitations: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        grid_bars = MappingProxyType(
            {target_key: tuple(bars) for target_key, bars in self.grid_bars_by_target.items()}
        )
        terminal_bars = MappingProxyType(dict(self.terminal_execution_bars_by_target))
        event_flags = MappingProxyType(
            {
                target_key: tuple(flags)
                for target_key, flags in self.range_event_flags_by_target.items()
            }
        )
        availability = MappingProxyType(
            {
                lookback: MappingProxyType(
                    {target_key: tuple(flags) for target_key, flags in values.items()}
                )
                for lookback, values in self.event_availability_by_lookback.items()
            }
        )
        grid = tuple(self.decision_session_grid)
        target_keys = tuple(self.selected_target_keys)
        if (
            self.dataset_id != KIS_PAPER_DAILY_BROAD_PANEL_ID
            or any(
                not _is_sha256(value)
                for value in (
                    self.dataset_hash,
                    self.manifest_sha256,
                    self.materialization_receipt_sha256,
                    self.source_index_hash,
                    self.target_key_set_hash,
                    self.geometry_audit_receipt_sha256,
                    self.geometry_audit_contract_sha256,
                    self.geometry_audit_source_grid_sha256,
                    self.geometry_audit_event_mask_sha256,
                )
            )
            or self.full_target_count < self.coverage_eligible_target_count
            or self.coverage_eligible_target_count < len(target_keys)
            or len(target_keys) != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TARGET_COUNT
            or self.raw_byte_attested_target_count < len(target_keys)
            or self.raw_byte_attested_target_count > self.coverage_eligible_target_count
            or tuple(sorted(target_keys)) != target_keys
            or len(set(target_keys)) != len(target_keys)
            or len(grid) != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
            or tuple(sorted(grid)) != grid
            or len(set(grid)) != len(grid)
            or self.terminal_execution_session <= grid[-1]
            or set(grid_bars) != set(target_keys)
            or set(terminal_bars) != set(target_keys)
            or set(event_flags) != set(target_keys)
            or set(availability) != set(KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS)
            or not self.limitations
            or any(not isinstance(value, str) or not value for value in self.limitations)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError("KIS broad D1 momentum input is invalid")

        event_rows: list[list[bool]] = []
        for target_key in target_keys:
            expected_symbol = target_key.split("/", maxsplit=1)[0]
            bars = grid_bars[target_key]
            terminal_bar = terminal_bars[target_key]
            flags = event_flags[target_key]
            if (
                len(bars) != len(grid)
                or len(flags) != len(grid)
                or any(
                    not _is_valid_completed_d1_bar(
                        bar,
                        expected_symbol=expected_symbol,
                        expected_start=grid[index],
                    )
                    for index, bar in enumerate(bars)
                )
                or not _is_valid_completed_d1_bar(
                    terminal_bar,
                    expected_symbol=expected_symbol,
                    expected_start=self.terminal_execution_session,
                )
                or any(type(flag) is not bool for flag in flags)
                or tuple(_range_event(bar) for bar in bars) != flags
            ):
                raise ValueError("KIS broad D1 momentum input is invalid")
            event_rows.append(list(flags))

        if (
            self.target_key_set_hash
            != _selected_target_key_set_hash(target_keys)
            or self.geometry_audit_source_grid_sha256
            != _sha256_payload({"session_starts": [item.isoformat() for item in grid]})
            or self.geometry_audit_event_mask_sha256 != _sha256_bool_matrix(event_rows)
        ):
            raise ValueError("KIS broad D1 momentum input is invalid")

        for lookback in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS:
            values = availability[lookback]
            if set(values) != set(target_keys):
                raise ValueError("KIS broad D1 momentum input is invalid")
            for target_key in target_keys:
                expected = _event_availability(event_flags[target_key], lookback)
                if values[target_key] != expected:
                    raise ValueError("KIS broad D1 momentum input is invalid")

        object.__setattr__(self, "selected_target_keys", target_keys)
        object.__setattr__(self, "decision_session_grid", grid)
        object.__setattr__(self, "grid_bars_by_target", grid_bars)
        object.__setattr__(self, "terminal_execution_bars_by_target", terminal_bars)
        object.__setattr__(self, "range_event_flags_by_target", event_flags)
        object.__setattr__(self, "event_availability_by_lookback", availability)

    @property
    def target_count(self) -> int:
        """The fixed cross-sectional cohort size."""

        return len(self.selected_target_keys)

    def availability_for(self, lookback: int) -> Mapping[str, tuple[bool, ...]]:
        """Return the fixed completed-bar event mask for one frozen lookback."""

        try:
            return self.event_availability_by_lookback[lookback]
        except KeyError as error:
            raise ValueError("KIS broad D1 momentum lookback is not frozen") from error


def build_kis_broad_d1_cross_sectional_momentum_input(
    *,
    manifest_path: Path | str,
    materialization_receipt_path: Path | str,
    geometry_audit_receipt_path: Path | str,
    cache_root: Path | str,
    panel_root: Path | str,
    repo_root: Path | str | None = None,
) -> KisBroadD1CrossSectionalMomentumInput:
    """Reattach and bind the exact selected panel and preceding audit receipt."""

    try:
        selection = load_materialized_kis_paper_daily_broad_panel_selection(
            manifest_path,
            materialization_receipt_path=materialization_receipt_path,
            cohort_target_count=KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TARGET_COUNT,
            minimum_bar_count=(
                KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
                + KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TERMINAL_BUFFER_SESSIONS
            ),
            common_session_count=KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT,
            terminal_buffer_sessions=(
                KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TERMINAL_BUFFER_SESSIONS
            ),
            raw_byte_attestation_limit=(
                KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_RAW_BYTE_ATTESTATION_LIMIT
            ),
            cache_root=cache_root,
            panel_root=panel_root,
            repo_root=repo_root,
        )
    except (OSError, ValueError) as error:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable(
            _selection_unavailable_code(error)
        ) from error

    try:
        geometry_audit = build_kis_broad_d1_geometry_audit_from_selection(
            selection,
            spec=KisBroadD1GeometryAuditSpec(),
        )
    except KisBroadD1GeometryAuditUnavailable as error:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable(
            "malformed_or_changed_source"
        ) from error
    except ValueError as error:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable(
            "malformed_or_changed_source"
        ) from error

    receipt_sha256 = _reattest_geometry_audit_receipt(
        geometry_audit_receipt_path,
        expected=geometry_audit,
    )
    return build_kis_broad_d1_cross_sectional_momentum_input_from_selection(
        selection,
        geometry_audit=geometry_audit,
        geometry_audit_receipt_sha256=receipt_sha256,
    )


def build_kis_broad_d1_cross_sectional_momentum_input_from_selection(
    selection: KisPaperDailyBroadPanelSelection,
    *,
    geometry_audit: KisBroadD1GeometryAudit,
    geometry_audit_receipt_sha256: str,
) -> KisBroadD1CrossSectionalMomentumInput:
    """Build the same fixed input from an already reattested selected panel."""

    if not isinstance(selection, KisPaperDailyBroadPanelSelection):
        raise TypeError("KIS broad D1 momentum input requires a selected broad panel")
    if (
        selection.dataset_id != KIS_PAPER_DAILY_BROAD_PANEL_ID
        or len(selection.selected_target_keys)
        != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TARGET_COUNT
        or selection.coverage_eligible_target_count
        < KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TARGET_COUNT
        or selection.raw_byte_attested_target_count
        < KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TARGET_COUNT
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("insufficient_eligible_symbols")
    if (
        selection.minimum_bar_count
        != (
            KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
            + KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TERMINAL_BUFFER_SESSIONS
        )
        or selection.common_session_count
        != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
        or selection.terminal_buffer_sessions
        != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TERMINAL_BUFFER_SESSIONS
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("insufficient_coverage")
    if (
        not isinstance(geometry_audit, KisBroadD1GeometryAudit)
        or not _is_sha256(geometry_audit_receipt_sha256)
        or geometry_audit.spec != KisBroadD1GeometryAuditSpec()
        or geometry_audit.source.dataset_hash != selection.dataset_hash
        or geometry_audit.source.manifest_sha256 != selection.manifest_sha256
        or geometry_audit.source.materialization_receipt_sha256
        != selection.materialization_receipt_sha256
        or geometry_audit.source.source_index_hash != selection.index_sha256
        or geometry_audit.source.selected_target_key_set_hash
        != selection.selected_target_key_set_hash
        or geometry_audit.source.full_target_count != selection.full_target_count
        or geometry_audit.source.coverage_eligible_target_count
        != selection.coverage_eligible_target_count
        or geometry_audit.source.selected_target_count != len(selection.selected_target_keys)
        or geometry_audit.source.raw_byte_attested_target_count
        != selection.raw_byte_attested_target_count
        or geometry_audit.source.common_session_count
        != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
        or not geometry_audit.event_censored_candidate_input_eligible
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("geometry_audit_mismatch")

    grid, terminal_execution_session = _grid_and_terminal_session(selection)
    grid_bars_by_target: dict[str, tuple[Bar, ...]] = {}
    terminal_bars_by_target: dict[str, Bar] = {}
    event_flags_by_target: dict[str, tuple[bool, ...]] = {}
    event_rows: list[list[bool]] = []
    for target_key in selection.selected_target_keys:
        records, terminal_bar = _target_grid_and_terminal(
            selection.bars_by_target[target_key].bars,
            target_key=target_key,
            grid=grid,
            terminal_execution_session=terminal_execution_session,
        )
        flags = tuple(_range_event(record) for record in records)
        grid_bars_by_target[target_key] = records
        terminal_bars_by_target[target_key] = terminal_bar
        event_flags_by_target[target_key] = flags
        event_rows.append(list(flags))

    event_mask_sha256 = _sha256_bool_matrix(event_rows)
    grid_sha256 = _sha256_payload(
        {"session_starts": [session.isoformat() for session in grid]}
    )
    if (
        geometry_audit.source.common_session_grid_sha256 != grid_sha256
        or geometry_audit.feature_event_mask_sha256 != event_mask_sha256
        or geometry_audit.feature_event_count != sum(sum(row) for row in event_rows)
        or geometry_audit.feature_event_target_count != sum(any(row) for row in event_rows)
        or geometry_audit.feature_event_session_count
        != sum(any(row[index] for row in event_rows) for index in range(len(grid)))
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("geometry_audit_mismatch")

    availability_by_lookback = {
        lookback: {
            target_key: _event_availability(event_flags_by_target[target_key], lookback)
            for target_key in selection.selected_target_keys
        }
        for lookback in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS
    }
    if not _audit_availability_matches(
        availability_by_lookback[20],
        geometry_audit,
        selection.selected_target_keys,
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("geometry_audit_mismatch")

    return KisBroadD1CrossSectionalMomentumInput(
        dataset_id=selection.dataset_id,
        dataset_hash=selection.dataset_hash,
        manifest_sha256=selection.manifest_sha256,
        materialization_receipt_sha256=selection.materialization_receipt_sha256,
        source_index_hash=selection.index_sha256,
        target_key_set_hash=selection.selected_target_key_set_hash,
        geometry_audit_receipt_sha256=geometry_audit_receipt_sha256,
        geometry_audit_contract_sha256=geometry_audit.contract_sha256,
        geometry_audit_source_grid_sha256=grid_sha256,
        geometry_audit_event_mask_sha256=event_mask_sha256,
        full_target_count=selection.full_target_count,
        coverage_eligible_target_count=selection.coverage_eligible_target_count,
        raw_byte_attested_target_count=selection.raw_byte_attested_target_count,
        selected_target_keys=selection.selected_target_keys,
        decision_session_grid=grid,
        terminal_execution_session=terminal_execution_session,
        grid_bars_by_target=grid_bars_by_target,
        terminal_execution_bars_by_target=terminal_bars_by_target,
        range_event_flags_by_target=event_flags_by_target,
        event_availability_by_lookback=availability_by_lookback,
        limitations=_preserved_limitations(selection.limitations),
    )


def _selection_unavailable_code(error: BaseException) -> str:
    message = str(error)
    if message == "broad daily panel selection coverage is insufficient":
        return "insufficient_eligible_symbols"
    if message == "broad daily panel selection exact coverage is insufficient":
        return "insufficient_coverage"
    return "malformed_or_changed_source"


def _preserved_limitations(limitations: tuple[str, ...]) -> tuple[str, ...]:
    if KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ADDITIONAL_LIMITATION in limitations:
        return limitations
    return (*limitations, KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ADDITIONAL_LIMITATION)


def _reattest_geometry_audit_receipt(
    path: Path | str,
    *,
    expected: KisBroadD1GeometryAudit,
) -> str:
    receipt_path = Path(path)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("geometry_audit_mismatch")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable(
            "geometry_audit_mismatch"
        ) from error
    if not isinstance(payload, dict) or payload != expected.payload():
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("geometry_audit_mismatch")
    return _sha256_bytes(receipt_path.read_bytes())


def _grid_and_terminal_session(
    selection: KisPaperDailyBroadPanelSelection,
) -> tuple[tuple[datetime, ...], datetime]:
    reference = selection.bars_by_target[selection.selected_target_keys[0]].bars
    required_count = (
        KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
        + KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_TERMINAL_BUFFER_SESSIONS
    )
    if len(reference) < required_count:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("insufficient_coverage")
    grid = tuple(reference[-required_count:-1])
    terminal = reference[-1]
    if (
        len(grid) != KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_GRID_SESSION_COUNT
        or tuple(bar.start_ts for bar in grid) != tuple(sorted(bar.start_ts for bar in grid))
        or len({bar.start_ts for bar in grid}) != len(grid)
        or terminal.start_ts <= grid[-1].start_ts
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("malformed_or_changed_source")
    return tuple(bar.start_ts for bar in grid), terminal.start_ts


def _target_grid_and_terminal(
    records: tuple[Bar, ...],
    *,
    target_key: str,
    grid: tuple[datetime, ...],
    terminal_execution_session: datetime,
) -> tuple[tuple[Bar, ...], Bar]:
    by_session = {bar.start_ts: bar for bar in records}
    if len(by_session) != len(records):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("malformed_or_changed_source")
    try:
        grid_records = tuple(by_session[session] for session in grid)
        terminal = by_session[terminal_execution_session]
    except KeyError as error:
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("insufficient_coverage") from error
    expected_symbol = target_key.split("/", maxsplit=1)[0]
    if any(
        not _is_valid_completed_d1_bar(
            bar,
            expected_symbol=expected_symbol,
            expected_start=grid[index],
        )
        for index, bar in enumerate(grid_records)
    ) or not _is_valid_completed_d1_bar(
        terminal,
        expected_symbol=expected_symbol,
        expected_start=terminal_execution_session,
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable("malformed_or_changed_source")
    return grid_records, terminal


def _is_valid_completed_d1_bar(
    bar: object,
    *,
    expected_symbol: str,
    expected_start: datetime,
) -> bool:
    if (
        not isinstance(bar, Bar)
        or bar.symbol != expected_symbol
        or bar.market != "US"
        or bar.timeframe is not Timeframe.D1
        or not bar.complete
        or bar.start_ts != expected_start
    ):
        return False
    values = tuple(float(value) for value in (bar.open, bar.high, bar.low, bar.close))
    return (
        all(math.isfinite(value) and value > 0.0 for value in values)
        and values[2] <= min(values[0], values[3])
        and values[1] >= max(values[0], values[3])
    )


def _range_event(bar: Bar) -> bool:
    high_value = float(bar.high)
    low_value = float(bar.low)
    if (
        not math.isfinite(high_value)
        or not math.isfinite(low_value)
        or high_value <= 0.0
        or low_value <= 0.0
    ):
        raise KisBroadD1CrossSectionalMomentumInputUnavailable(
            "malformed_or_changed_source"
        )
    return high_value / low_value > KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_RANGE_RATIO


def _event_availability(events: tuple[bool, ...], lookback: int) -> tuple[bool, ...]:
    if lookback not in KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS:
        raise ValueError("KIS broad D1 momentum lookback is not frozen")
    availability = [False] * len(events)
    for index in range(lookback, len(events)):
        availability[index] = not any(events[index - lookback + 1 : index + 1])
    return tuple(availability)


def _audit_availability_matches(
    availability: Mapping[str, tuple[bool, ...]],
    audit: KisBroadD1GeometryAudit,
    target_keys: tuple[str, ...],
) -> bool:
    spec = audit.spec
    development_indices = range(
        spec.feature_lookback_sessions,
        spec.development_session_count - 1,
    )
    validation_start = spec.development_session_count + spec.purge_session_count
    validation_indices = range(
        validation_start + spec.feature_lookback_sessions,
        spec.history_session_count - 1,
    )
    development_counts = [
        sum(availability[target_key][index] for index in development_indices)
        for target_key in target_keys
    ]
    validation_counts = [
        sum(availability[target_key][index] for index in validation_indices)
        for target_key in target_keys
    ]
    validation_session_counts = [
        sum(availability[target_key][index] for target_key in target_keys)
        for index in validation_indices
    ]
    return (
        sum(development_counts) == audit.development_available_pair_count
        and min(development_counts) == audit.development_available_per_target_min
        and max(development_counts) == audit.development_available_per_target_max
        and sum(validation_counts) == audit.validation_available_pair_count
        and min(validation_counts) == audit.validation_available_per_target_min
        and max(validation_counts) == audit.validation_available_per_target_max
        and min(validation_session_counts) == audit.validation_available_per_session_min
        and max(validation_session_counts) == audit.validation_available_per_session_max
        and sum(
            count < spec.minimum_validation_available_target_count
            for count in validation_session_counts
        )
        == audit.validation_sessions_below_minimum_count
    )


def _sha256_bool_matrix(values: list[list[bool]]) -> str:
    return _sha256_bytes(bytes(value for row in values for value in row))


def _sha256_payload(payload: Mapping[str, object]) -> str:
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _selected_target_key_set_hash(target_keys: tuple[str, ...]) -> str:
    payload = {"target_keys": list(target_keys)}
    encoded = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return _sha256_bytes(encoded)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        return False
    try:
        int(digest, 16)
    except ValueError:
        return False
    return True

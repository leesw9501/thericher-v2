"""Named SPY/TLT/GLD inputs bound to the existing positional shared-NAV math.

Caller-supplied calendars and adjusted vintages are bindings, not evidence of
historical publication, reinvestment or broker fills. This module performs no
I/O, source relabeling, policy selection, fitting or availability inference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from thericher_v2.contracts import require_utc
from thericher_v2.research import three_asset_nav as nav

INSTRUMENT_ORDER = ("SPY", "TLT", "GLD")


class CrossAssetInputUnavailable(ValueError):
    """A categorical fault scoped to the requested dates, never a global hold."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def safe_facts(self) -> dict[str, str]:
        return {"status": "input_unavailable", "reason_code": self.reason_code}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise CrossAssetInputUnavailable(reason)


def _utc(value: datetime) -> datetime:
    _require(type(value) is datetime and value.utcoffset() == timedelta(0), "calendar_not_utc")
    return require_utc(value)


def _vintage(value: str) -> None:
    _require(type(value) is str and bool(value) and value == value.strip(), "vintage_invalid")


@dataclass(frozen=True, slots=True)
class CrossAssetSession:
    session_date: date
    open_at: datetime
    close_at: datetime

    def __post_init__(self) -> None:
        _require(type(self.session_date) is date, "calendar_date_invalid")
        opening, closing = _utc(self.open_at), _utc(self.close_at)
        _require(
            opening.date() == closing.date() == self.session_date and opening < closing,
            "calendar_session_invalid",
        )


@dataclass(frozen=True, slots=True)
class CrossAssetAdjustedRow:
    symbol: str
    session_date: date
    vintage_ref: str = field(repr=False)
    adj_open: Decimal = field(repr=False)
    adj_high: Decimal = field(repr=False)
    adj_low: Decimal = field(repr=False)
    adj_close: Decimal = field(repr=False)

    def __post_init__(self) -> None:
        _require(type(self.symbol) is str and self.symbol in INSTRUMENT_ORDER, "row_symbol_invalid")
        _require(type(self.session_date) is date, "row_date_invalid")
        _vintage(self.vintage_ref)
        prices = (self.adj_open, self.adj_high, self.adj_low, self.adj_close)
        _require(
            all(type(value) is Decimal and value.is_finite() and value > 0 for value in prices),
            "adjusted_values_invalid",
        )
        _require(
            self.adj_low <= min(self.adj_open, self.adj_close)
            <= max(self.adj_open, self.adj_close) <= self.adj_high,
            "adjusted_geometry_invalid",
        )


def _sessions(value: tuple[CrossAssetSession, ...]) -> None:
    _require(type(value) is tuple and bool(value), "calendar_required")
    for session in value:
        _require(type(session) is CrossAssetSession, "calendar_type_invalid")
        session.__post_init__()
    _require(
        all(
            left.session_date < right.session_date and left.close_at < right.open_at
            for left, right in zip(value, value[1:], strict=False)
        ),
        "calendar_order_invalid",
    )


@dataclass(frozen=True, slots=True)
class CrossAssetInputs:
    sessions: tuple[CrossAssetSession, ...]
    vintage_ref: str = field(repr=False)
    rows_by_instrument: tuple[tuple[CrossAssetAdjustedRow, ...], ...] = field(repr=False)
    instrument_order: tuple[str, ...] = INSTRUMENT_ORDER

    def __post_init__(self) -> None:
        _require(
            type(self.instrument_order) is tuple and self.instrument_order == INSTRUMENT_ORDER,
            "instrument_order_invalid",
        )
        _sessions(self.sessions)
        _vintage(self.vintage_ref)
        _require(
            type(self.rows_by_instrument) is tuple and len(self.rows_by_instrument) == 3,
            "input_columns_invalid",
        )
        for symbol, rows in zip(INSTRUMENT_ORDER, self.rows_by_instrument, strict=True):
            _require(type(rows) is tuple and len(rows) == len(self.sessions), "input_rows_invalid")
            for row, session in zip(rows, self.sessions, strict=True):
                _require(type(row) is CrossAssetAdjustedRow, "required_row_type_invalid")
                row.__post_init__()
                _require(row.symbol == symbol, "required_row_symbol_mismatch")
                _require(row.session_date == session.session_date, "required_row_date_mismatch")
                _require(row.vintage_ref == self.vintage_ref, "required_vintage_mismatch")

    def safe_facts(self) -> dict[str, object]:
        return {
            "status": "ready",
            "instrument_order": self.instrument_order,
            "session_count": len(self.sessions),
            "row_count_per_instrument": len(self.sessions),
            "first_session": self.sessions[0].session_date.isoformat(),
            "last_session": self.sessions[-1].session_date.isoformat(),
        }


def prepare_cross_asset_marks(
    rows_by_symbol: Mapping[str, Sequence[CrossAssetAdjustedRow]],
    *,
    scheduled_sessions: tuple[CrossAssetSession, ...],
    vintage_ref: str,
) -> CrossAssetInputs:
    """Require every supplied scheduled mark, including cash-only/loss dates.

    Select required date keys before validating values/vintages. Extraneous old,
    current or future rows never confer or remove eligibility. No date is filled,
    dropped, intersected across symbols or inferred from source support.
    """
    _sessions(scheduled_sessions)
    _vintage(vintage_ref)
    _require(
        isinstance(rows_by_symbol, Mapping) and set(rows_by_symbol) == set(INSTRUMENT_ORDER),
        "source_symbols_invalid",
    )
    required = {session.session_date for session in scheduled_sessions}
    selected = []
    for symbol in INSTRUMENT_ORDER:
        source = rows_by_symbol[symbol]
        _require(
            isinstance(source, Sequence) and not isinstance(source, (str, bytes)),
            "source_sequence_invalid",
        )
        by_date = {}
        for row in source:
            day = getattr(row, "session_date", None)
            if type(day) is date and day in required:
                _require(day not in by_date, "required_session_duplicate")
                by_date[day] = row
        _require(set(by_date) == required, "required_session_missing")
        selected.append(tuple(by_date[session.session_date] for session in scheduled_sessions))
    return CrossAssetInputs(scheduled_sessions, vintage_ref, tuple(selected))


@dataclass(frozen=True, slots=True)
class CrossAssetHistory:
    inputs: CrossAssetInputs = field(repr=False)
    decision_at: datetime
    entry_session_date: date

    def __post_init__(self) -> None:
        _require(type(self.inputs) is CrossAssetInputs, "history_inputs_invalid")
        self.inputs.__post_init__()
        _require(type(self.entry_session_date) is date, "entry_date_invalid")
        _require(
            _utc(self.decision_at) == self.inputs.sessions[-1].close_at
            and self.inputs.sessions[-1].session_date < self.entry_session_date,
            "history_cutoff_invalid",
        )

    def safe_facts(self) -> dict[str, object]:
        return {
            **self.inputs.safe_facts(),
            "decision_at": self.decision_at.isoformat(),
            "entry_session": self.entry_session_date.isoformat(),
        }


def build_cross_asset_history(
    rows_by_symbol: Mapping[str, Sequence[CrossAssetAdjustedRow]],
    *,
    scheduled_sessions: tuple[CrossAssetSession, ...],
    entry_session_date: date,
    history_session_count: int,
    decision_at: datetime,
    vintage_ref: str,
) -> CrossAssetHistory:
    """Select exact preceding calendar sessions at the previous scheduled CLOSE.

    The caller supplies the complete frozen calendar, not a source-date union.
    History availability does not inspect entry/payoff marks. A D1 session label
    denotes an adjusted daily row; its UTC midnight is not the decision clock.
    Calendar CLOSE is an assumed cutoff, not measured publication availability.
    """
    _sessions(scheduled_sessions)
    _require(type(entry_session_date) is date, "entry_date_invalid")
    _require(
        type(history_session_count) is int and history_session_count > 0, "history_count_invalid"
    )
    dates = tuple(session.session_date for session in scheduled_sessions)
    _require(entry_session_date in dates, "entry_session_missing")
    entry_index = dates.index(entry_session_date)
    _require(entry_index >= history_session_count, "scheduled_history_missing")
    previous = scheduled_sessions[entry_index - 1]
    _require(_utc(decision_at) == previous.close_at, "decision_not_previous_close")
    selected = scheduled_sessions[entry_index - history_session_count : entry_index]
    inputs = prepare_cross_asset_marks(
        rows_by_symbol, scheduled_sessions=selected, vintage_ref=vintage_ref
    )
    return CrossAssetHistory(inputs, decision_at, entry_session_date)


@dataclass(frozen=True, slots=True)
class CrossAssetTarget:
    weights_by_symbol: Mapping[str, Decimal] = field(repr=False)
    cash_weight: Decimal = field(repr=False)
    instrument_order: tuple[str, ...] = INSTRUMENT_ORDER

    def __post_init__(self) -> None:
        _require(
            type(self.instrument_order) is tuple and self.instrument_order == INSTRUMENT_ORDER,
            "instrument_order_invalid",
        )
        _require(
            isinstance(self.weights_by_symbol, Mapping)
            and set(self.weights_by_symbol) == set(INSTRUMENT_ORDER),
            "target_symbols_invalid",
        )
        copied = {symbol: self.weights_by_symbol[symbol] for symbol in INSTRUMENT_ORDER}
        nav.ThreeAssetTarget(tuple(copied.values()), self.cash_weight)
        object.__setattr__(self, "weights_by_symbol", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class CrossAssetReplay:
    ledger: nav.ThreeAssetReplay = field(repr=False)
    vintage_ref: str = field(repr=False)
    instrument_order: tuple[str, ...] = INSTRUMENT_ORDER

    def __post_init__(self) -> None:
        _require(
            type(self.instrument_order) is tuple and self.instrument_order == INSTRUMENT_ORDER,
            "instrument_order_invalid",
        )
        _require(type(self.ledger) is nav.ThreeAssetReplay, "ledger_type_invalid")
        _vintage(self.vintage_ref)

    def safe_facts(self) -> dict[str, object]:
        return {
            "status": "replayed",
            "instrument_order": self.instrument_order,
            "session_count": len(self.ledger.daily),
            "first_session": self.ledger.daily[0].date.isoformat(),
            "last_session": self.ledger.daily[-1].date.isoformat(),
        }


def replay_cross_asset(
    inputs: CrossAssetInputs,
    targets_by_date: Mapping[date, CrossAssetTarget],
    cost_bps: Decimal,
) -> CrossAssetReplay:
    """Bind named instruments once; call only the ledger's positional replay.

    One shared NAV1/cash account, overnight carry, post-fee OPEN targets and final
    CLOSE liquidation use unchanged Decimal50 arithmetic/actual-notional fees.
    No legacy from_mapping helper or legacy source row is accepted or relabeled.
    """
    _require(type(inputs) is CrossAssetInputs, "replay_inputs_invalid")
    inputs.__post_init__()
    _require(isinstance(targets_by_date, Mapping), "target_dates_invalid")
    days = tuple(
        nav.ThreeAssetDay(
            session.session_date,
            tuple(rows[index].adj_open for rows in inputs.rows_by_instrument),
            tuple(rows[index].adj_close for rows in inputs.rows_by_instrument),
        )
        for index, session in enumerate(inputs.sessions)
    )
    actions = {}
    for day, target in targets_by_date.items():
        _require(type(target) is CrossAssetTarget, "target_type_invalid")
        # Revalidate without mutating the frozen caller-owned target.
        _require(target.instrument_order == INSTRUMENT_ORDER, "instrument_order_invalid")
        _require(
            isinstance(target.weights_by_symbol, Mapping)
            and set(target.weights_by_symbol) == set(INSTRUMENT_ORDER),
            "target_symbols_invalid",
        )
        actions[day] = nav.ThreeAssetTarget(
            tuple(target.weights_by_symbol[symbol] for symbol in INSTRUMENT_ORDER),
            target.cash_weight,
        )
    return CrossAssetReplay(nav.replay(days, actions, cost_bps), inputs.vintage_ref)

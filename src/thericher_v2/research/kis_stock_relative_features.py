"""Pure stock-specific features and sealed five-session relative targets.

The 800-session TRAIN and 113-session current calendars stay separate. Clocks
are nominal; callers bind source/registry/hashes and actual observation times.
No fitting, policy selection, loading, persistence or execution lives here.
Known entry features need prior61 only; target calendar coverage is separate.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction

from thericher_v2.contracts import require_utc
from thericher_v2.research import kis_pooled_equity_components as core

WARMUP = 61
HORIZON = 5
KEY_COUNT = 128
MAX_FUTURE_FITS = 9
FEATURE_NAMES = ("meanID5", "meanID20", "meanON20", "close_return_vol20")


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ValueError(category)


def _finite(value: object) -> float:
    try:
        return core._number(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("finite_feature_required") from exc


@dataclass(frozen=True, slots=True)
class FeaturePlan:
    sessions: tuple[date, ...]
    keys: tuple[str, ...]
    open_clocks: tuple[datetime, ...]
    close_clocks: tuple[datetime, ...]

    def __post_init__(self) -> None:
        for name in ("sessions", "keys"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in ("open_clocks", "close_clocks"):
            _require(
                all(isinstance(v, datetime) for v in getattr(self, name)), "clock_type_invalid"
            )
            object.__setattr__(self, name, tuple(require_utc(v, name) for v in getattr(self, name)))
        _require(
            len(self.sessions) in (113, 800)
            and all(type(day) is date for day in self.sessions)
            and all(a < b for a, b in zip(self.sessions, self.sessions[1:], strict=False)),
            "separate_exact_113_or_800_calendar_required",
        )
        _require(
            len(self.keys) == KEY_COUNT
            and all(isinstance(key, str) and key for key in self.keys)
            and self.keys == tuple(sorted(set(self.keys))),
            "exact_128_sorted_opaque_keys_required",
        )
        _require(
            len(self.open_clocks) == len(self.close_clocks) == len(self.sessions)
            and all(
                opening.date() == day == closing.date() and opening < closing
                for day, opening, closing in zip(
                    self.sessions, self.open_clocks, self.close_clocks, strict=True
                )
            )
            and all(
                closing < opening
                for closing, opening in zip(
                    self.close_clocks[:-1], self.open_clocks[1:], strict=True
                )
            ),
            "explicit_ordered_UTC_calendar_clocks_required",
        )

    @property
    def feature_entries(self) -> range:
        return range(WARMUP, len(self.sessions))

    @property
    def complete_target_entries(self) -> range:
        return range(WARMUP, len(self.sessions) - HORIZON)

    @property
    def complete_entries(self) -> range:
        """Compatibility alias for TRAIN targets, not inference availability."""
        return self.complete_target_entries


def purged_prefix_entries(plan: FeaturePlan, target_open_cutoff: int) -> range:
    """Include TRAIN entries only when entry+5 OPEN <= the fixed prefix cutoff.

    E.g. cutoff427 includes entry61..422, not entries423..427 whose exits lie
    beyond that prefix. No outcome-dependent selection or fold fitting occurs.
    """
    _require(
        isinstance(plan, FeaturePlan)
        and type(target_open_cutoff) is int
        and 0 <= target_open_cutoff < len(plan.sessions),
        "prefix_cutoff_invalid",
    )
    return range(WARMUP, max(WARMUP, target_open_cutoff - HORIZON + 1))


@dataclass(frozen=True, slots=True)
class StockRow:
    key: str
    symbol: str
    market: str
    values: tuple[float, ...]
    sequence: tuple[tuple[float, float], ...] | None = None

    def __post_init__(self) -> None:
        _require(
            all(isinstance(v, str) and v for v in (self.key, self.symbol, self.market)),
            "stock_identity_required",
        )
        values = tuple(_finite(v) for v in self.values)
        _require(len(values) == 4 and values[-1] >= 0, "fixed_four_feature_geometry")
        object.__setattr__(self, "values", values)
        if self.sequence is not None:
            sequence = tuple(tuple(_finite(v) for v in step) for step in self.sequence)
            _require(
                len(sequence) == 20 and all(len(step) == 2 for step in sequence),
                "fixed_20x2_sequence_geometry",
            )
            object.__setattr__(self, "sequence", sequence)


@dataclass(frozen=True, slots=True)
class FeatureSeal:
    plan: FeaturePlan
    entry_index: int
    rows: tuple[StockRow, ...]
    unavailable_keys: tuple[str, ...]
    include_sequence: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "unavailable_keys", tuple(self.unavailable_keys))
        _require(
            isinstance(self.plan, FeaturePlan)
            and type(self.entry_index) is int
            and self.entry_index in self.plan.feature_entries,
            "known_entry_with_prior61_required",
        )
        _require(
            type(self.include_sequence) is bool
            and all(isinstance(row, StockRow) for row in self.rows),
            "stock_rows_required",
        )
        eligible = self.eligible_keys
        _require(
            eligible == tuple(sorted(set(eligible)))
            and set(eligible) <= set(self.plan.keys)
            and self.unavailable_keys == tuple(key for key in self.plan.keys if key not in eligible)
            and all((row.sequence is not None) == self.include_sequence for row in self.rows),
            "frozen_eligible_identity_binding",
        )

    @property
    def eligible_keys(self) -> tuple[str, ...]:
        return tuple(row.key for row in self.rows)

    @property
    def features(self) -> tuple[tuple[float, ...], ...]:
        return tuple(row.values for row in self.rows)

    @property
    def sequences(self) -> tuple | None:
        return tuple(row.sequence for row in self.rows) if self.include_sequence else None

    @property
    def entry_session(self) -> date:
        return self.plan.sessions[self.entry_index]

    @property
    def exit_index(self) -> int:
        return self.entry_index + HORIZON

    @property
    def exit_session(self) -> date | None:
        return (
            self.plan.sessions[self.exit_index]
            if self.exit_index < len(self.plan.sessions)
            else None
        )

    @property
    def decision_at(self) -> datetime:
        return self.plan.close_clocks[self.entry_index - 1]

    @property
    def entry_open_at(self) -> datetime:
        return self.plan.open_clocks[self.entry_index]

    @property
    def exit_open_at(self) -> datetime | None:
        return (
            self.plan.open_clocks[self.exit_index]
            if self.exit_index < len(self.plan.sessions)
            else None
        )


def features(
    plan: FeaturePlan,
    entry_index: int,
    past_source: core.PastSource,
    *,
    include_sequence: bool = False,
) -> FeatureSeal:
    """One prior61 read/key using core eligibility, never entry/future bars.

    Log ID/ON means follow core components. Volatility is population std of
    20 simple CLOSE returns from the last21 prior CLOSEs, not cross-centered.
    Numeric feature failure rejects construction, never silently drops a peer.
    """
    _require(
        isinstance(plan, FeaturePlan)
        and type(entry_index) is int
        and entry_index in plan.feature_entries,
        "known_entry_with_prior61_required",
    )
    _require(type(include_sequence) is bool, "sequence_choice_invalid")
    captured = {}

    def capture(key, day):
        value = past_source(key, day)
        captured[key, day] = value
        return value

    # core.snapshot uses these same calendar attributes, including on the
    # separately validated 113 view; no artificial 800-calendar extension.
    try:
        snapshot = core.snapshot(plan, entry_index, capture)
        raw = []
        for row in snapshot.rows:
            bars = tuple(
                captured[row.key, day] for day in plan.sessions[entry_index - 21 : entry_index]
            )
            returns = tuple(
                _finite(float(Fraction(b.close) / Fraction(a.close) - 1))
                for a, b in zip(bars, bars[1:], strict=False)
            )
            mean = math.fsum(v / 20 for v in returns)
            volatility = math.hypot(*(v / math.sqrt(20) - mean / math.sqrt(20) for v in returns))
            on, intraday = row.components
            vector = (
                math.fsum(intraday[-5:]) / 5,
                math.fsum(intraday) / 20,
                math.fsum(on) / 20,
                _finite(volatility),
            )
            sequence = tuple(zip(on, intraday, strict=True)) if include_sequence else None
            raw.append((row.key, bars[-1].symbol, bars[-1].market, vector, sequence))
        means = tuple(math.fsum(row[3][j] / len(raw) for row in raw) for j in range(3))
        rows = tuple(
            StockRow(
                key,
                symbol,
                market,
                tuple(vector[j] - means[j] for j in range(3)) + (vector[3],),
                sequence,
            )
            for key, symbol, market, vector, sequence in raw
        )
    except (OverflowError, ArithmeticError) as exc:
        raise ValueError("finite_feature_required") from exc
    return FeatureSeal(plan, entry_index, rows, snapshot.unavailable_keys, include_sequence)


@dataclass(frozen=True, slots=True)
class OpenQuote:
    """Only target OPEN plus identity/nominal-clock binding; assessed after seal."""

    symbol: str
    market: str
    session: date
    open_at: datetime
    price: Decimal | float


TargetSource = Callable[[str, date], OpenQuote | None]


def _target_open(value: OpenQuote | None, row: StockRow, day: date, at: datetime) -> Fraction:
    _require(isinstance(value, OpenQuote), "target_open_quote_required")
    _require(isinstance(value.open_at, datetime), "target_clock_type_invalid")
    _require(
        (value.symbol, value.market, value.session) == (row.symbol, row.market, day)
        and require_utc(value.open_at, "target_open_at") == at,
        "target_identity_clock_invalid",
    )
    _require(
        isinstance(value.price, (Decimal, float)) and not isinstance(value.price, bool),
        "target_price_invalid",
    )
    result = Fraction(core._score(value.price))
    _require(result > 0, "target_price_invalid")
    return result


@dataclass(frozen=True, slots=True)
class RelativeTargets:
    seal: FeatureSeal
    observed_returns: tuple[tuple[str, Fraction], ...]
    missing_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(isinstance(self.seal, FeatureSeal), "feature_identity_seal_required")
        object.__setattr__(
            self, "observed_returns", tuple(tuple(row) for row in self.observed_returns)
        )
        object.__setattr__(self, "missing_keys", tuple(self.missing_keys))
        if self.seal.exit_session is None:
            _require(
                not self.observed_returns and not self.missing_keys,
                "unknown_horizon_cannot_contain_quote_observations",
            )
            return
        eligible = self.seal.eligible_keys
        _require(
            self.missing_keys == tuple(key for key in eligible if key in self.missing_keys)
            and tuple(key for key, _ in self.observed_returns)
            == tuple(key for key in eligible if key not in self.missing_keys)
            and all(isinstance(value, Fraction) for _, value in self.observed_returns),
            "exact_frozen_target_peer_binding",
        )
        if not self.missing_keys and eligible:
            for value in self.values:
                _finite(value)

    @property
    def unavailable_reason(self) -> str | None:
        if self.seal.exit_session is None:
            return "target_horizon_not_in_calendar"
        if not self.seal.rows:
            return "empty_eligible_cohort"
        if self.missing_keys:
            return "target_peer_unavailable"
        return None

    @property
    def values(self) -> tuple[float, ...] | None:
        if self.unavailable_reason is not None:
            return None
        mean = sum((value for _, value in self.observed_returns), Fraction(0)) / len(self.seal.rows)
        return tuple(float(value - mean) for _, value in self.observed_returns)

    @property
    def available_at(self) -> datetime | None:
        return self.seal.exit_open_at

    @property
    def historical_decision_time_availability(self) -> str:
        return "not_observed"


def target_labels(seal: FeatureSeal, target_source: TargetSource) -> RelativeTargets:
    """All frozen eligible peers, two scheduled OPENs each, after feature seal.

    Any missing/invalid peer invalidates the full date. No selected-name filter,
    alternate horizon, peer graft, cost label, cent projection or log target.
    An exit outside this calendar yields a date-level unavailable result with
    zero quote callbacks, without changing feature eligibility or peer identity.
    """
    _require(isinstance(seal, FeatureSeal), "feature_identity_seal_required")
    if seal.exit_session is None:
        return RelativeTargets(seal, (), ())
    observed, missing = [], []
    for row in seal.rows:
        first = target_source(row.key, seal.entry_session)
        last = target_source(row.key, seal.exit_session)
        try:
            opening = _target_open(first, row, seal.entry_session, seal.entry_open_at)
            exit_open = _target_open(last, row, seal.exit_session, seal.exit_open_at)
            result = exit_open / opening - 1
            _finite(float(result))
            observed.append((row.key, result))
        except (ValueError, TypeError, ArithmeticError, OverflowError):
            missing.append(row.key)
    return RelativeTargets(seal, tuple(observed), tuple(missing))

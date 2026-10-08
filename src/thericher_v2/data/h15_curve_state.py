"""Pure three-tenor Board package parsing and assumed, non-PIT curve context.

Only the selected maturity values become features. Dates are selected before
finiteness is checked; revised observations are not historical release proof.
"""

from __future__ import annotations

import csv
import io
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from typing import Literal
from zoneinfo import ZoneInfo

from thericher_v2.contracts import require_utc
from thericher_v2.data.federal_reserve_h15 import FederalReserveH15Error, H15Observation

THREE_MONTH_SERIES = "RIFLGFCM03_N.B"
TWO_YEAR_SERIES = "RIFLGFCY02_N.B"
TEN_YEAR_SERIES = "RIFLGFCY10_N.B"
_SELECTED = (THREE_MONTH_SERIES, TWO_YEAR_SERIES, TEN_YEAR_SERIES)
_TENORS = {
    "RIFLGFCM01_N.B": "1-month",
    THREE_MONTH_SERIES: "3-month",
    "RIFLGFCM06_N.B": "6-month",
    "RIFLGFCY01_N.B": "1-year",
    TWO_YEAR_SERIES: "2-year",
    "RIFLGFCY03_N.B": "3-year",
    "RIFLGFCY05_N.B": "5-year",
    "RIFLGFCY07_N.B": "7-year",
    TEN_YEAR_SERIES: "10-year",
    "RIFLGFCY20_N.B": "20-year",
    "RIFLGFCY30_N.B": "30-year",
}
_METADATA = ("Series Description", "Unit:", "Multiplier:", "Currency:", "Unique Identifier:")
_MISSING = frozenset({"", "NA", "N/A", "ND"})
_ET = ZoneInfo("America/New_York")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FederalReserveH15Error(code)


def _anchor(decision_at: datetime) -> tuple[datetime, date]:
    try:
        _require(
            type(decision_at) is datetime and decision_at.utcoffset() == timedelta(0),
            "decision_invalid",
        )
        decision_at = require_utc(decision_at, "H15 curve decision")
        return decision_at, decision_at.astimezone(_ET).date() - timedelta(days=30)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise FederalReserveH15Error("decision_invalid") from None


@dataclass(frozen=True, slots=True)
class H15CurveSnapshot:
    three_month: tuple[H15Observation, ...] = field(repr=False)
    two_year: tuple[H15Observation, ...] = field(repr=False)
    ten_year: tuple[H15Observation, ...] = field(repr=False)
    _shared_dates: tuple[date, ...] = field(init=False, repr=False)
    _shared_rows: tuple[tuple[H15Observation, ...], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        indexes = []
        for rows in (self.three_month, self.two_year, self.ten_year):
            _require(type(rows) is tuple, "csv_invalid")
            previous = None
            available = {}
            for row in rows:
                _require(type(row) is H15Observation, "csv_invalid")
                row.__post_init__()
                day = row.observation_date
                if previous is not None:
                    _require(day != previous, "duplicate_observation_date")
                    _require(day > previous, "observation_date_order_invalid")
                previous = day
                if row.source_missing_code is None:
                    _require(type(row.yield_percent) is Decimal, "value_invalid")
                    available[day] = row
            indexes.append(available)
        shared = tuple(sorted(indexes[0].keys() & indexes[1].keys() & indexes[2].keys()))
        object.__setattr__(self, "_shared_dates", shared)
        object.__setattr__(
            self, "_shared_rows", tuple(tuple(index[day] for index in indexes) for day in shared)
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "kind": "h15_curve_snapshot",
            "units": "percent",
            "three_month_rows": len(self.three_month),
            "two_year_rows": len(self.two_year),
            "ten_year_rows": len(self.ten_year),
            "shared_nonmissing_date_count": len(self._shared_dates),
            "missing_observation_count": sum(
                row.source_missing_code is not None
                for rows in (self.three_month, self.two_year, self.ten_year)
                for row in rows
            ),
            "historical_release_vintage_proven": False,
        }


@dataclass(frozen=True, slots=True)
class H15CurveState:
    status: Literal["available", "input_unavailable"]
    decision_at: datetime
    anchor_date: date
    observation_date: date | None = None
    reason: (
        Literal["shared_observation_missing", "shared_observation_stale", "selected_value_invalid"]
        | None
    ) = None
    three_month_percent: Fraction | None = field(default=None, repr=False)
    two_year_percent: Fraction | None = field(default=None, repr=False)
    ten_year_percent: Fraction | None = field(default=None, repr=False)
    level_percent: Fraction | None = field(default=None, repr=False)
    slope_percent: Fraction | None = field(default=None, repr=False)
    curvature_percent: Fraction | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _, anchor = _anchor(self.decision_at)
        _require(type(self.anchor_date) is date and self.anchor_date == anchor, "decision_invalid")
        _require(
            self.observation_date is None
            or type(self.observation_date) is date
            and self.observation_date <= anchor,
            "date_invalid",
        )
        values = (
            self.three_month_percent,
            self.two_year_percent,
            self.ten_year_percent,
            self.level_percent,
            self.slope_percent,
            self.curvature_percent,
        )
        if self.status == "available":
            _require(
                self.reason is None
                and self.observation_date is not None
                and (anchor - self.observation_date).days <= 7
                and all(type(value) is Fraction for value in values),
                "value_invalid",
            )
            three, two, ten, level, slope, curvature = values
            _require(
                level == (three + two + ten) / 3
                and slope == ten - three
                and curvature == 2 * two - three - ten,
                "value_invalid",
            )
        else:
            _require(
                self.status == "input_unavailable"
                and self.reason
                in {
                    "shared_observation_missing",
                    "shared_observation_stale",
                    "selected_value_invalid",
                }
                and all(value is None for value in values),
                "value_invalid",
            )
            _require(
                self.observation_date is None
                if self.reason == "shared_observation_missing"
                else self.observation_date is not None
                and ((anchor - self.observation_date).days > 7)
                == (self.reason == "shared_observation_stale"),
                "date_invalid",
            )

    @property
    def factors_percent(self) -> tuple[Fraction, Fraction, Fraction] | None:
        if self.status != "available":
            return None
        return self.level_percent, self.slope_percent, self.curvature_percent

    def safe_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "decision_at": self.decision_at.isoformat(),
            "anchor_date": self.anchor_date.isoformat(),
            "observation_date": self.observation_date.isoformat()
            if self.observation_date
            else None,
            "lag_calendar_days": 30,
            "max_age_calendar_days": 7,
            "units": "percent",
            "factor_count": 3 if self.status == "available" else 0,
            "availability_assumption": "revised_non_PIT_development_lag",
            "historical_release_vintage_proven": False,
        }


def _observation(day: date, text: str) -> H15Observation:
    if text in _MISSING:
        return H15Observation(day, None, text)
    _require(text.isascii() and text == text.strip() and "_" not in text, "value_invalid")
    try:
        with localcontext() as context:
            context.traps[InvalidOperation] = True
            value = Decimal(text)
    except InvalidOperation:
        raise FederalReserveH15Error("value_invalid") from None
    return H15Observation(day, value)


def parse_h15_curve_package(raw: bytes) -> H15CurveSnapshot:
    """Parse the fixed 11-series Treasury package; never infer a publication clock."""
    _require(type(raw) is bytes, "csv_invalid")
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        metadata = tuple(next(reader, ()) for _ in _METADATA)
        header = next(reader, ())
        _require(
            len(header) == 12
            and header[0] == "Time Period"
            and len(set(header[1:])) == 11
            and set(header[1:]) == _TENORS.keys(),
            "csv_invalid",
        )
        for label, row in zip(_METADATA, metadata, strict=True):
            _require(len(row) == 12 and row[0] == label, "csv_invalid")
            for column, series in enumerate(header[1:], 1):
                expected = {
                    "Series Description": (
                        f"Market yield on U.S. Treasury securities at {_TENORS[series]}"
                        "  constant maturity, quoted on investment basis"
                    ),
                    "Unit:": "Percent:_Per_Year",
                    "Multiplier:": "1",
                    "Currency:": "NA",
                    "Unique Identifier:": "H15/H15/" + series,
                }[label]
                _require(row[column] == expected, "csv_invalid")
        columns = tuple(header.index(series) for series in _SELECTED)
        observations = ([], [], [])
        previous = None
        for row in reader:
            _require(len(row) == 12, "csv_invalid")
            try:
                day = date.fromisoformat(row[0])
                _require(day.isoformat() == row[0], "date_invalid")
            except ValueError:
                raise FederalReserveH15Error("date_invalid") from None
            if previous is not None:
                _require(day != previous, "duplicate_observation_date")
                _require(day > previous, "observation_date_order_invalid")
            previous = day
            for rows, column in zip(observations, columns, strict=True):
                rows.append(_observation(day, row[column]))
        return H15CurveSnapshot(*(tuple(rows) for rows in observations))
    except (UnicodeError, csv.Error):
        raise FederalReserveH15Error("csv_invalid") from None


def select_h15_curve_state(snapshot: H15CurveSnapshot, *, decision_at: datetime) -> H15CurveState:
    """Latest complete date at ET-date-minus-30, then finite-value and seven-day checks."""
    _require(type(snapshot) is H15CurveSnapshot, "csv_invalid")
    decision_at, anchor = _anchor(decision_at)
    index = bisect_right(snapshot._shared_dates, anchor) - 1
    if index < 0:
        return H15CurveState(
            "input_unavailable", decision_at, anchor, reason="shared_observation_missing"
        )
    selected = snapshot._shared_dates[index]
    reason = None
    if (anchor - selected).days > 7:
        reason = "shared_observation_stale"
    else:
        rows = snapshot._shared_rows[index]
        if any(not row.yield_percent.is_finite() for row in rows):
            reason = "selected_value_invalid"
        else:
            three, two, ten = tuple(Fraction(row.yield_percent) for row in rows)
            return H15CurveState(
                "available",
                decision_at,
                anchor,
                selected,
                three_month_percent=three,
                two_year_percent=two,
                ten_year_percent=ten,
                level_percent=(three + two + ten) / 3,
                slope_percent=ten - three,
                curvature_percent=2 * two - three - ten,
            )
    return H15CurveState("input_unavailable", decision_at, anchor, selected, reason)

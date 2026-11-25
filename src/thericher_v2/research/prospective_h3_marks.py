"""Project target-only marks for the frozen five-cohort 50:50 H3 evaluation."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanel,
    H3DailyPanelPlan,
)
from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.research.prospective_h3_calendar import (
    H3Interval,
    select_prospective_h3_intervals,
)

_FROZEN_INTERVALS = (
    H3Interval(date(2026, 11, 30), date(2026, 12, 3)),
    H3Interval(date(2026, 12, 4), date(2026, 12, 9)),
    H3Interval(date(2026, 12, 10), date(2026, 12, 15)),
    H3Interval(date(2026, 12, 16), date(2026, 12, 21)),
    H3Interval(date(2026, 12, 22), date(2026, 12, 28)),
)
_DECISION_SYMBOLS = tuple(symbol for symbol, _ in NET25_H3_AXIS[:17])


@dataclass(frozen=True)
class ProspectiveH3Marks:
    """Date-major OPEN4/CLOSE3 on the ordered 17-name decision axis."""

    sessions: tuple[date, ...]
    symbols: tuple[str, ...]
    opens: tuple[tuple[Decimal, ...], ...] = field(repr=False)
    closes: tuple[tuple[Decimal, ...], ...] = field(repr=False)


def project_prospective_h3_marks(panel: H3DailyPanel, interval: H3Interval) -> ProspectiveH3Marks:
    """Supply marks to the frozen 50:50 and equal-weight comparison, without scoring.

    Before calling, prove the exact independently owned target capture was
    acquired after the expiry session's official close in its authorized window,
    using the frozen same-basis MODP1 edition. Bind the qualified panel to the
    source, response identities, ordered columns, capture clock and untouched
    target custody. Rows carry dates, not symbol identities or acquisition times;
    a matching axis and as-of cannot prove provenance, freshness or finality.
    The caller keeps these outcomes sealed until the authorized block-end read.
    """
    if type(interval) is not H3Interval or interval not in _FROZEN_INTERVALS:
        raise ValueError("h3_marks_interval_invalid")
    if (
        type(panel) is not H3DailyPanel
        or type(panel.plan) is not H3DailyPanelPlan
        or panel.plan.axis != NET25_H3_AXIS
    ):
        raise ValueError("h3_marks_axis_invalid")
    if panel.plan.as_of != interval.expiry:
        raise ValueError("h3_marks_as_of_mismatch")

    sessions = panel.plan.sessions
    if len(sessions) != 60 or len(panel.rows) != len(sessions) or sessions[-1] != interval.expiry:
        raise ValueError("h3_marks_session_grid_invalid")
    try:
        (tracked,) = select_prospective_h3_intervals(
            sessions, earliest_entry=interval.entry, count=1
        )
    except ValueError:
        raise ValueError("h3_marks_session_grid_invalid") from None
    if tracked != interval:
        raise ValueError("h3_marks_session_grid_invalid")

    target_sessions = sessions[-4:]
    rows = panel.rows[-4:]
    for day, row in zip(target_sessions, rows, strict=True):
        key = day.strftime("%Y%m%d")
        if (
            type(row) is not tuple
            or len(row) != len(NET25_H3_AXIS)
            or any(getattr(bar, "xymd", None) != key for bar in row)
        ):
            raise ValueError("h3_marks_session_grid_invalid")

    return ProspectiveH3Marks(
        target_sessions,
        _DECISION_SYMBOLS,
        tuple(_project_row(row, "open") for row in rows),
        tuple(_project_row(row, "clos") for row in rows[:3]),
    )


def _project_row(row: tuple[KisPaperDailyRawRow, ...], field_name: str) -> tuple[Decimal, ...]:
    marks = []
    for bar in row[: len(_DECISION_SYMBOLS)]:
        text = getattr(bar, field_name, None)
        if type(text) is not str:
            raise ValueError("h3_marks_required_value_invalid")
        try:
            mark = Decimal(text)
        except InvalidOperation:
            raise ValueError("h3_marks_required_value_invalid") from None
        if not mark.is_finite() or mark <= 0:
            raise ValueError("h3_marks_required_value_invalid")
        marks.append(mark)
    return tuple(marks)

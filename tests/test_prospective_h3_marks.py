import hashlib
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanelPlan,
    qualify_h3_daily_panel,
)
from thericher_v2.execution.kis_paper_data_capture import CaptureResult
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import project_prospective_h3_marks

WINDOWS = (
    ("2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03"),
    ("2026-12-04", "2026-12-07", "2026-12-08", "2026-12-09"),
    ("2026-12-10", "2026-12-11", "2026-12-14", "2026-12-15"),
    ("2026-12-16", "2026-12-17", "2026-12-18", "2026-12-21"),
    ("2026-12-22", "2026-12-23", "2026-12-24", "2026-12-28"),
)


def _panel(as_of):
    plan = H3DailyPanelPlan(NET25_H3_AXIS, as_of)
    captures = []
    for col, query in enumerate(plan.queries):
        wire = json.dumps(
            [
                dict(
                    xymd=day.strftime("%Y%m%d"),
                    open=f"{100 + r}.{col:02}",
                    high="1000",
                    low="1",
                    clos=f"{200 + r}.{col:02}",
                    tvol="1",
                )
                for r, day in reversed(tuple(enumerate(plan.sessions)))
            ]
        ).encode("ascii")
        captures.append(
            (
                CaptureResult(
                    query.key, "ACCEPTED", 60, native={"sha256": hashlib.sha256(wire).hexdigest()}
                ),
                wire,
            )
        )
    return qualify_h3_daily_panel(plan, reversed(captures))


@pytest.fixture
def cohort():
    entry, _, _, expiry = map(date.fromisoformat, WINDOWS[0])
    return _panel(expiry), H3Interval(entry, expiry)


@pytest.mark.parametrize("window", WINDOWS)
def test_qualified_panel_projects_only_frozen_marks_in_order(window):
    sessions = tuple(map(date.fromisoformat, window))
    marks = project_prospective_h3_marks(
        _panel(sessions[-1]), H3Interval(sessions[0], sessions[-1])
    )
    assert marks.sessions == sessions
    assert marks.symbols == tuple(symbol for symbol, _ in NET25_H3_AXIS[:17])
    assert marks.opens == tuple(
        tuple(Decimal(f"{day}.{col:02}") for col in range(17)) for day in range(156, 160)
    )
    assert marks.closes == tuple(
        tuple(Decimal(f"{day}.{col:02}") for col in range(17)) for day in range(256, 259)
    )
    assert "opens=" not in repr(marks) and "closes=" not in repr(marks)


@pytest.mark.parametrize("offset", [-1, 1])
def test_refuses_stale_or_later_dated_panel(cohort, offset):
    _, interval = cohort
    as_of = date(2026, 12, interval.expiry.day + offset)
    with pytest.raises(ValueError, match="h3_marks_as_of_mismatch"):
        project_prospective_h3_marks(_panel(as_of), interval)


def test_refuses_other_h3_window_even_with_matching_expiry():
    interval = H3Interval(date(2026, 12, 1), date(2026, 12, 4))
    with pytest.raises(ValueError, match="h3_marks_interval_invalid"):
        project_prospective_h3_marks(_panel(interval.expiry), interval)


@pytest.mark.parametrize("axis", [NET25_H3_AXIS[::-1], (("AAPL", "NYS"), *NET25_H3_AXIS[1:])])
def test_refuses_reordered_or_wrong_fixed19_axis(cohort, axis):
    panel, interval = cohort
    with pytest.raises(ValueError, match="h3_marks_axis_invalid"):
        project_prospective_h3_marks(replace(panel, plan=replace(panel.plan, axis=axis)), interval)


@pytest.mark.parametrize("defect", ["row_order", "missing_row", "missing_column", "session_order"])
def test_refuses_wrong_session_grid(cohort, defect):
    panel, interval = cohort
    rows = panel.rows
    if defect == "row_order":
        panel = replace(panel, rows=(*rows[:-2], rows[-1], rows[-2]))
    elif defect == "missing_row":
        panel = replace(panel, rows=rows[:-1])
    elif defect == "missing_column":
        panel = replace(panel, rows=(*rows[:-1], rows[-1][:-1]))
    else:
        sessions = panel.plan.sessions
        object.__setattr__(
            panel.plan, "sessions", (*sessions[:-3], sessions[-2], sessions[-3], sessions[-1])
        )
    with pytest.raises(ValueError, match="h3_marks_session_grid_invalid"):
        project_prospective_h3_marks(panel, interval)


@pytest.mark.parametrize(("row", "field"), [(-1, "open"), (-2, "clos")])
@pytest.mark.parametrize("value", [None, "", "0", "-1", "NaN", "Infinity", "not-a-price"])
def test_refuses_any_invalid_required_mark_even_for_last_decision_name(cohort, row, field, value):
    panel, interval = cohort
    object.__setattr__(panel.rows[row][16], field, value)
    with pytest.raises(ValueError, match="^h3_marks_required_value_invalid$"):
        project_prospective_h3_marks(panel, interval)


def test_unused_values_are_not_needed_or_emitted(cohort):
    panel, interval = cohort
    expected = project_prospective_h3_marks(panel, interval)
    object.__delattr__(panel.rows[-1][0], "clos")
    object.__delattr__(panel.rows[-4][17], "open")
    object.__delattr__(panel.rows[-4][18], "clos")
    object.__delattr__(panel.rows[-4][0], "high")
    object.__delattr__(panel.rows[-5][0], "open")
    assert project_prospective_h3_marks(panel, interval) == expected

"""Join admitted Dec4 fixed-half inputs for the prospective H3 block reducer."""

from datetime import date

from thericher_v2.ops.h3_dec4_fixed_half_reader import INTERVAL, Dec4FixedHalfForecast
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import ProspectiveH3Marks
from thericher_v2.research.prospective_h3_replay import (
    ProspectiveH3Replay,
    replay_prospective_h3_cohort,
)


def evaluate_dec4_fixed_half_slot(
    forecast: Dec4FixedHalfForecast, marks: ProspectiveH3Marks
) -> ProspectiveH3Replay:
    """Evaluate one Dec4-Dec9 slot with native costs and no overrides.

    The caller independently admits the forecast and target custody at block
    end. This join checks identity, not provenance; rejected slots raise and
    must not be converted to no-signal records.
    """
    if type(forecast) is not Dec4FixedHalfForecast or type(marks) is not ProspectiveH3Marks:
        raise ValueError("h3_fixed_half_slot_input_type")
    if (
        type(forecast.interval) is not H3Interval
        or any(type(day) is not date for day in forecast.interval)
        or forecast.interval != INTERVAL
        or type(marks.sessions) is not tuple
        or any(type(day) is not date for day in marks.sessions)
    ):
        raise ValueError("h3_fixed_half_slot_interval")
    for symbols in (forecast.forecast_symbols, marks.symbols):
        if type(symbols) is not tuple or any(type(symbol) is not str for symbol in symbols):
            raise ValueError("h3_fixed_half_slot_axis")
    return replay_prospective_h3_cohort(
        forecast.interval,
        marks,
        forecast_symbols=forecast.forecast_symbols,
        blend_scores=forecast.blend_scores,
    )

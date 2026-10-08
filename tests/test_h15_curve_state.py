from __future__ import annotations

import builtins
import copy
import csv
import io
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_UP, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from thericher_v2.data.federal_reserve_h15 import FederalReserveH15Error, H15Observation
from thericher_v2.data.h15_curve_state import (
    H15CurveSnapshot,
    H15CurveState,
    parse_h15_curve_package,
    select_h15_curve_state,
)

SERIES = (
    "RIFLGFCM01_N.B",
    "RIFLGFCM03_N.B",
    "RIFLGFCM06_N.B",
    "RIFLGFCY01_N.B",
    "RIFLGFCY02_N.B",
    "RIFLGFCY03_N.B",
    "RIFLGFCY05_N.B",
    "RIFLGFCY07_N.B",
    "RIFLGFCY10_N.B",
    "RIFLGFCY20_N.B",
    "RIFLGFCY30_N.B",
)
TENORS = (
    "1-month",
    "3-month",
    "6-month",
    "1-year",
    "2-year",
    "3-year",
    "5-year",
    "7-year",
    "10-year",
    "20-year",
    "30-year",
)
SELECTED = ("RIFLGFCM03_N.B", "RIFLGFCY02_N.B", "RIFLGFCY10_N.B")
DECISION = datetime(2024, 2, 1, 21, tzinfo=UTC)
ANCHOR = date(2024, 1, 2)


def table(entries=(), *, columns=SERIES):
    descriptions = dict(zip(SERIES, TENORS, strict=True))
    rows = [
        [
            "Series Description",
            *(
                f"Market yield on U.S. Treasury securities at {descriptions[s]}"
                "  constant maturity, quoted on investment basis"
                for s in columns
            ),
        ],
        ["Unit:", *["Percent:_Per_Year"] * len(columns)],
        ["Multiplier:", *["1"] * len(columns)],
        ["Currency:", *["NA"] * len(columns)],
        ["Unique Identifier:", *("H15/H15/" + s for s in columns)],
        ["Time Period", *columns],
    ]
    for day, values in entries:
        selected = dict(zip(SELECTED, values, strict=True))
        rows.append([day, *(selected.get(s, "0.75") for s in columns)])
    return rows


def encode(rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def snapshot(entries=(("2024-01-02", ("1", "2", "4")),)):
    return parse_h15_curve_package(encode(table(entries)))


def state(value=None, *, decision_at=DECISION):
    return select_h15_curve_state(snapshot() if value is None else value, decision_at=decision_at)


def test_exact_named_yields_and_three_factors():
    selected = state()
    assert selected.status == "available" and selected.reason is None
    assert selected.anchor_date == selected.observation_date == ANCHOR
    assert (selected.three_month_percent, selected.two_year_percent, selected.ten_year_percent) == (
        Fraction(1),
        Fraction(2),
        Fraction(4),
    )
    assert selected.factors_percent == (Fraction(7, 3), Fraction(3), Fraction(-1))


@pytest.mark.parametrize("precision,rounding", [(2, ROUND_UP), (3, ROUND_DOWN), (50, ROUND_UP)])
def test_exact_arithmetic_is_independent_of_decimal_context(precision, rounding):
    entries = (("2024-01-02", ("1.23456789", "2.98765432", "4.00000001")),)
    expected = state(snapshot(entries))
    with localcontext() as context:
        context.prec, context.rounding = precision, rounding
        context.traps[InvalidOperation] = False
        assert state(snapshot(entries)) == expected
        with pytest.raises(FederalReserveH15Error, match="^value_invalid$"):
            snapshot((("2024-01-02", ("junk", "2", "4")),))


@pytest.mark.parametrize(
    "values", [("0", "0", "0"), ("-1", "-.25", ".5"), ("1e-8", "+2E-8", "3.00e-8")]
)
def test_zero_negative_and_exponent_yields_are_not_clipped(values):
    selected = state(snapshot((("2024-01-02", values),)))
    a, b, c = (Fraction(Decimal(v)) for v in values)
    assert selected.factors_percent == ((a + b + c) / 3, c - a, 2 * b - a - c)


def test_columns_are_mapped_by_exact_identifier_not_position():
    entries = (("2024-01-02", ("1", "2", "4")),)
    original = state(snapshot(entries))
    reversed_columns = parse_h15_curve_package(encode(table(entries, columns=SERIES[::-1])))
    assert state(reversed_columns) == original


def test_unselected_maturity_is_not_a_feature_or_value_quality_gate():
    rows = table((("2024-01-02", ("1", "2", "4")),))
    rows[-1][1] = "unused-source-field"
    assert state(parse_h15_curve_package(encode(rows))) == state()


@pytest.mark.parametrize("missing", ["ND", "NA", "N/A", ""])
def test_missing_marker_is_retained_without_imputation(missing):
    value = snapshot((("2024-01-02", (missing, "2", "4")),))
    assert value.three_month[0].yield_percent is None
    assert value.three_month[0].source_missing_code == missing
    selected = state(value)
    assert selected.reason == "shared_observation_missing"
    assert selected.factors_percent is None and selected.observation_date is None
    assert value.safe_payload()["missing_observation_count"] == 1


def test_latest_incomplete_date_selects_one_earlier_complete_vector():
    value = snapshot(
        (
            ("2023-12-29", ("1", "2", "4")),
            ("2024-01-02", ("ND", "99", "100")),
        )
    )
    selected = state(value)
    assert selected.observation_date == date(2023, 12, 29)
    assert selected.factors_percent == (Fraction(7, 3), Fraction(3), Fraction(-1))


def test_individually_available_tenors_cannot_be_carried_into_a_vector():
    value = snapshot(
        (
            ("2023-12-29", ("1", "ND", "ND")),
            ("2024-01-01", ("ND", "2", "ND")),
            ("2024-01-02", ("ND", "ND", "4")),
        )
    )
    assert state(value).reason == "shared_observation_missing"


@pytest.mark.parametrize("position", [0, 1, 2])
@pytest.mark.parametrize("invalid", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_selected_nonfinite_never_falls_back_to_an_older_finite_vector(position, invalid):
    values = ["1", "2", "4"]
    values[position] = invalid
    value = snapshot(
        (
            ("2023-12-29", ("1", "2", "4")),
            ("2024-01-02", values),
        )
    )
    selected = state(value)
    assert selected.status == "input_unavailable"
    assert selected.reason == "selected_value_invalid"
    assert selected.observation_date == ANCHOR and selected.factors_percent is None
    assert all(
        getattr(selected, name) is None
        for name in (
            "three_month_percent",
            "two_year_percent",
            "ten_year_percent",
            "level_percent",
            "slope_percent",
            "curvature_percent",
        )
    )


@pytest.mark.parametrize(
    "future", [("9000", "-9000", "123"), ("NaN", "sNaN", "Infinity"), ("ND", "NA", "")]
)
def test_future_value_and_support_perturbations_do_not_change_past_state(future):
    past = (("2024-01-02", ("1", "2", "4")),)
    expected = state(snapshot(past))
    assert state(snapshot((*past, ("2024-01-03", future)))) == expected
    assert state(snapshot((*past, ("2026-10-07", future)))) == expected


@pytest.mark.parametrize(
    "day,status,reason",
    [
        ("2023-12-26", "available", None),
        ("2023-12-25", "input_unavailable", "shared_observation_stale"),
        ("2024-01-03", "input_unavailable", "shared_observation_missing"),
    ],
)
def test_seven_day_boundary_and_future_only_history(day, status, reason):
    selected = state(snapshot(((day, ("1", "2", "4")),)))
    assert (selected.status, selected.reason) == (status, reason)


@pytest.mark.parametrize(
    "clock,anchor",
    [
        (datetime(2024, 2, 1, 4, 59, 59, tzinfo=UTC), date(2024, 1, 1)),
        (datetime(2024, 2, 1, 5, tzinfo=UTC), date(2024, 1, 2)),
        (datetime(2024, 3, 11, 3, 59, 59, tzinfo=UTC), date(2024, 2, 9)),
        (datetime(2024, 3, 11, 4, tzinfo=UTC), date(2024, 2, 10)),
    ],
)
def test_et_calendar_date_not_utc_date_or_thirty_times_24_hours(clock, anchor):
    selected = state(snapshot(()), decision_at=clock)
    assert selected.anchor_date == anchor


@pytest.mark.parametrize(
    "clock",
    [
        None,
        "2024-02-01",
        date(2024, 2, 1),
        datetime(2024, 2, 1),
        datetime(2024, 2, 1, tzinfo=timezone(timedelta(hours=1))),
        datetime(1, 1, 1, tzinfo=UTC),
    ],
)
def test_invalid_decision_types_zones_and_date_underflow_are_categorical(clock):
    with pytest.raises(FederalReserveH15Error, match="^decision_invalid$"):
        state(snapshot(()), decision_at=clock)


@pytest.mark.parametrize(
    "raw",
    [None, "not-bytes", bytearray(b"bad"), memoryview(b"bad"), b"", b"\xff", b'"unterminated'],
)
def test_raw_type_encoding_and_csv_syntax_reject_without_values(raw):
    with pytest.raises(FederalReserveH15Error, match="^csv_invalid$"):
        parse_h15_curve_package(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_header",
        "unknown_series",
        "unit",
        "multiplier",
        "currency",
        "identifier",
        "description",
        "metadata_order",
        "extra_column",
        "short_row",
        "blank_row",
    ],
)
def test_strict_raw_package_schema(mutation):
    rows = table((("2024-01-02", ("1", "2", "4")),))
    if mutation == "duplicate_header":
        rows[5][2] = rows[5][1]
    elif mutation == "unknown_series":
        rows[5][2] = "RIFSGFS_3M_DISCOUNT"
    elif mutation in {"unit", "multiplier", "currency", "identifier", "description"}:
        row_index = {"unit": 1, "multiplier": 2, "currency": 3, "identifier": 4, "description": 0}[
            mutation
        ]
        rows[row_index][2] = "unapproved-schema"
    elif mutation == "metadata_order":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "extra_column":
        rows[-1].append("extra")
    elif mutation == "short_row":
        rows[-1].pop()
    else:
        rows.append([])
    with pytest.raises(FederalReserveH15Error, match="^csv_invalid$"):
        parse_h15_curve_package(encode(rows))


@pytest.mark.parametrize(
    "day",
    [
        "2024-1-2",
        "2024-02-30",
        "\uff12\uff10\uff12\uff14-01-02",
        "2024-W01-2",
        "20240102",
        " 2024-01-02",
    ],
)
def test_date_grammar_and_calendar_are_exact(day):
    with pytest.raises(FederalReserveH15Error, match="^date_invalid$"):
        snapshot(((day, ("1", "2", "4")),))


@pytest.mark.parametrize(
    "entries,reason",
    [
        (
            (("2024-01-02", ("1", "2", "4")), ("2024-01-02", ("1", "2", "4"))),
            "duplicate_observation_date",
        ),
        (
            (("2024-01-02", ("1", "2", "4")), ("2024-01-01", ("1", "2", "4"))),
            "observation_date_order_invalid",
        ),
    ],
)
def test_duplicate_or_reversed_dates_are_not_sorted_or_repaired(entries, reason):
    with pytest.raises(FederalReserveH15Error, match="^" + reason + "$"):
        snapshot(entries)


@pytest.mark.parametrize("text", ["junk", "1_000", "\uff11.\uff12", " 1", "1 "])
def test_selected_value_grammar_is_strict(text):
    with pytest.raises(FederalReserveH15Error, match="^value_invalid$"):
        snapshot((("2024-01-02", (text, "2", "4")),))


def test_bom_and_crlf_preserve_the_same_snapshot():
    raw = encode(table((("2024-01-02", ("1", "2", "4")),)))
    assert parse_h15_curve_package(b"\xef\xbb\xbf" + raw.replace(b"\n", b"\r\n")) == snapshot()


def test_snapshot_state_and_observations_are_immutable():
    value = snapshot()
    selected = state(value)
    before = copy.deepcopy(value)
    for obj, field_name, field_value in (
        (value, "three_month", ()),
        (value.three_month[0], "yield_percent", Decimal(0)),
        (selected, "level_percent", Fraction(0)),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field_name, field_value)
    assert value == before and state(value) == selected


def test_financial_repr_and_safe_payload_are_hidden():
    value = snapshot((("2024-01-02", ("7654321.1234567", "2", "4")),))
    selected = state(value)
    safe = json.dumps([value.safe_payload(), selected.safe_payload()])
    assert "7654321" not in repr(value) + repr(selected) + safe
    assert "7654321" not in repr(value.three_month[0])
    assert selected.safe_payload()["historical_release_vintage_proven"] is False
    assert selected.safe_payload()["factor_count"] == 3
    assert not any(
        name in selected.safe_payload()
        for name in (
            "three_month_percent",
            "two_year_percent",
            "ten_year_percent",
            "level_percent",
            "slope_percent",
            "curvature_percent",
            "factors_percent",
        )
    )


def test_direct_snapshot_rejects_mutable_shape_wrong_rows_and_invalid_missing_shape():
    obs = H15Observation(ANCHOR, Decimal(1))
    with pytest.raises(FederalReserveH15Error, match="^csv_invalid$"):
        H15CurveSnapshot([obs], (obs,), (obs,))
    with pytest.raises(FederalReserveH15Error, match="^csv_invalid$"):
        H15CurveSnapshot((object(),), (obs,), (obs,))
    with pytest.raises(FederalReserveH15Error, match="^value_invalid$"):
        H15CurveSnapshot((H15Observation(ANCHOR, None),), (obs,), (obs,))
    with pytest.raises(FederalReserveH15Error, match="^csv_invalid$"):
        select_h15_curve_state({}, decision_at=DECISION)


def test_direct_state_rejects_false_financial_or_availability_metadata():
    selected = state()
    with pytest.raises(FederalReserveH15Error):
        replace(selected, level_percent=Fraction(0))
    with pytest.raises(FederalReserveH15Error):
        replace(selected, anchor_date=ANCHOR + timedelta(days=1))
    with pytest.raises(FederalReserveH15Error):
        H15CurveState("input_unavailable", DECISION, ANCHOR, reason="selected_value_invalid")


def test_pure_functions_do_not_open_files_or_access_network(monkeypatch):
    raw = encode(table((("2024-01-02", ("1", "2", "4")),)))

    def forbidden(*args, **kwargs):
        raise AssertionError("pure curve API performed I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert state(parse_h15_curve_package(raw)).status == "available"

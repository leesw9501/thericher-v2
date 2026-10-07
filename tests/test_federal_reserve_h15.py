from __future__ import annotations

import csv
import hashlib
import inspect
import io
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.data import federal_reserve_h15 as h15


def _row(day: date, value: str | None, missing: str | None = None) -> h15.H15Observation:
    return h15.H15Observation(day, Decimal(value) if value is not None else None, missing)


def _decision(anchor: date) -> datetime:
    day = anchor + timedelta(days=30)
    return datetime(day.year, day.month, day.day, 17, tzinfo=UTC)


def _csv(rows: tuple[h15.H15Observation, ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("observation_date", "yield_percent", "source_missing_code"))
    for row in rows:
        writer.writerow(
            (
                row.observation_date.isoformat(),
                str(row.yield_percent) if row.yield_percent is not None else "",
                row.source_missing_code or "",
            )
        )
    return buffer.getvalue().encode()


def _hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _snapshot_files(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Synthetic bytes only; real snapshot constants are never read by tests."""
    day = date(2026, 1, 2)
    sources = {
        h15.TWO_YEAR_SERIES + ".csv": _csv((_row(day, "1.25"),)),
        h15.TEN_YEAR_SERIES + ".csv": _csv((_row(day, "2.50"),)),
    }
    raw = b"synthetic-board-response\n"
    raw_hash = _hash(raw)
    raw_path = "raw/" + raw_hash.removeprefix("sha256:") + ".csv"
    sources[raw_path] = raw
    series = {
        name: {
            "board_series_id": "H15/H15/" + name,
            "units": "percent",
            "canonical_sha256": _hash(sources[name + ".csv"]),
        }
        for name in (h15.TWO_YEAR_SERIES, h15.TEN_YEAR_SERIES)
    }
    manifest = {
        "source_url": h15.SOURCE_URL,
        "response_sha256": raw_hash,
        "raw_response_retained": False,
        "series": series,
    }
    sources["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    attestation = {
        "source_url": h15.SOURCE_URL,
        "original_manifest_sha256": _hash(sources["manifest.json"]),
        "original_response_sha256": raw_hash,
        "re_retrieved_response_sha256": raw_hash,
        "raw_response_retained": True,
        "raw_path_relative": raw_path,
        "parser_counts_and_canonical_hashes": series,
    }
    sources["source-attestation.json"] = json.dumps(attestation, sort_keys=True).encode()
    monkeypatch.setattr(h15, "RAW_SHA256", raw_hash)
    monkeypatch.setattr(h15, "RAW_RELATIVE_PATH", raw_path)
    monkeypatch.setattr(
        h15,
        "SNAPSHOT_SHA256",
        MappingProxyType({name: _hash(payload) for name, payload in sources.items()}),
    )
    for name, payload in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def test_reader_pins_all_five_files_and_preserves_original_retention_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _snapshot_files(monkeypatch, tmp_path)
    snapshot = h15.read_federal_reserve_h15_snapshot(tmp_path)
    assert snapshot.two_year[0].yield_percent == Decimal("1.25")
    assert snapshot.ten_year[0].yield_percent == Decimal("2.50")
    assert snapshot.safe_summary()["units"] == "percent"
    assert len(h15.SNAPSHOT_SHA256) == 5
    assert json.loads((tmp_path / "manifest.json").read_bytes())["raw_response_retained"] is False


@pytest.mark.parametrize(
    "source", ["manifest.json", "source-attestation.json", "raw", "two", "ten"]
)
def test_each_changed_source_byte_invalidates_the_pin_not_an_asof_coverage_rule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str
) -> None:
    _snapshot_files(monkeypatch, tmp_path)
    name = {
        "raw": h15.RAW_RELATIVE_PATH,
        "two": h15.TWO_YEAR_SERIES + ".csv",
        "ten": h15.TEN_YEAR_SERIES + ".csv",
    }.get(source, source)
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(h15.FederalReserveH15Error, match="^source_hash_mismatch$"):
        h15.read_federal_reserve_h15_snapshot(tmp_path)


def test_missing_file_is_categorical_and_does_not_acquire(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _snapshot_files(monkeypatch, tmp_path)
    (tmp_path / h15.RAW_RELATIVE_PATH).unlink()
    with pytest.raises(h15.FederalReserveH15Error, match="^source_unavailable$"):
        h15.read_federal_reserve_h15_snapshot(tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw_response_retained", False),
        ("raw_path_relative", "../private-canary"),
        ("original_manifest_sha256", "sha256:wrong"),
        ("source_url", "https://unrelated.invalid"),
    ],
)
def test_hash_consistent_attestation_must_still_bind_exact_source_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, field: str, value: object
) -> None:
    _snapshot_files(monkeypatch, tmp_path)
    path = tmp_path / "source-attestation.json"
    payload = json.loads(path.read_bytes())
    payload[field] = value
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(
        h15,
        "SNAPSHOT_SHA256",
        MappingProxyType(
            {
                **h15.SNAPSHOT_SHA256,
                "source-attestation.json": _hash(raw),
            }
        ),
    )
    with pytest.raises(h15.FederalReserveH15Error, match="^source_contract_invalid$"):
        h15.read_federal_reserve_h15_snapshot(tmp_path)


@pytest.mark.parametrize(
    "two,ten", [("0", "0"), ("-1.25", "0"), ("0", "-2.50"), ("-3.75", "-2.50")]
)
def test_zero_and_negative_yields_are_valid_exact_percent_units(two: str, ten: str) -> None:
    day = date(2026, 1, 2)
    snapshot = h15.H15Snapshot((_row(day, two),), (_row(day, ten),))
    result = h15.select_h15_asof_pair(snapshot, decision_at=_decision(day))
    assert result.status == "available"
    assert result.two_year_percent == Decimal(two)
    assert result.ten_year_percent == Decimal(ten)
    assert result.spread_percent == Decimal(ten) - Decimal(two)


def test_exact_subtraction_does_not_inherit_low_ambient_precision() -> None:
    day = date(2026, 1, 2)
    snapshot = h15.H15Snapshot((_row(day, "1.234567"),), (_row(day, "2.345678"),))
    with localcontext() as context:
        context.prec = 2
        result = h15.select_h15_asof_pair(snapshot, decision_at=_decision(day))
    assert result.spread_percent == Decimal("1.111111")


@pytest.mark.parametrize(
    "decision,anchor",
    [
        (datetime(2026, 2, 2, 0, 30, tzinfo=UTC), date(2026, 1, 2)),
        (datetime(2026, 8, 2, 0, 30, tzinfo=UTC), date(2026, 7, 2)),
    ],
)
def test_anchor_uses_et_decision_date_in_winter_and_summer(
    decision: datetime, anchor: date
) -> None:
    snapshot = h15.H15Snapshot((_row(anchor, "1"),), (_row(anchor, "2"),))
    assert h15.select_h15_asof_pair(snapshot, decision_at=decision).anchor_date == anchor


@pytest.mark.parametrize(
    "age,status", [(0, "available"), (7, "available"), (8, "input_unavailable")]
)
def test_age_is_inclusive_seven_calendar_days(age: int, status: str) -> None:
    anchor = date(2026, 1, 12)
    observed = anchor - timedelta(days=age)
    snapshot = h15.H15Snapshot((_row(observed, "1"),), (_row(observed, "2"),))
    result = h15.select_h15_asof_pair(snapshot, decision_at=_decision(anchor))
    assert result.status == status
    assert result.observation_date == observed
    if age == 8:
        assert result.reason == "shared_observation_stale"
        assert result.spread_percent is None


@pytest.mark.parametrize("marker", ["", "NA", "N/A", "ND"])
def test_known_missing_rows_are_not_observations_and_never_carry_one_maturity(marker: str) -> None:
    day = date(2026, 1, 2)
    earlier = day - timedelta(days=1)
    two = h15._canonical_rows(_csv((_row(earlier, "1"), _row(day, None, marker))))
    ten = (_row(earlier, "2"), _row(day, "3"))
    result = h15.select_h15_asof_pair(h15.H15Snapshot(two, ten), decision_at=_decision(day))
    assert result.status == "available"
    assert result.observation_date == earlier
    assert result.ten_year_percent == Decimal("2")


def test_individually_recent_maturities_do_not_form_a_pair() -> None:
    anchor = date(2026, 1, 12)
    snapshot = h15.H15Snapshot((_row(anchor, "1"),), (_row(anchor - timedelta(days=1), "2"),))
    result = h15.select_h15_asof_pair(snapshot, decision_at=_decision(anchor))
    assert result.reason == "shared_observation_missing"
    assert result.status == "input_unavailable"


@pytest.mark.parametrize("bad", ["NaN", "sNaN", "Infinity", "-Infinity", None])
@pytest.mark.parametrize("maturity", ["two_year", "ten_year"])
def test_selected_invalid_pair_is_unavailable_without_older_fallback(
    bad: str | None, maturity: str
) -> None:
    day = date(2026, 1, 2)
    earlier = day - timedelta(days=1)
    snapshot = h15.H15Snapshot(
        (_row(earlier, "1"), _row(day, "1.5")),
        (_row(earlier, "2"), _row(day, "2.5")),
    )
    snapshot = replace(snapshot, **{maturity: (getattr(snapshot, maturity)[0], _row(day, bad))})
    result = h15.select_h15_asof_pair(snapshot, decision_at=_decision(day))
    assert result.status == "input_unavailable"
    assert result.reason == "selected_value_invalid"
    assert result.observation_date == day
    assert result.spread_percent is None


@pytest.mark.parametrize("future", ["changed", "removed", "added", "missing", "nonfinite"])
def test_future_value_presence_and_missing_mutations_cannot_change_past_selection(
    future: str,
) -> None:
    day = date(2026, 1, 2)
    after = day + timedelta(days=1)
    snapshot = h15.H15Snapshot(
        (_row(day, "1"), _row(after, "3")),
        (_row(day, "2"), _row(after, "4")),
    )
    expected = h15.select_h15_asof_pair(snapshot, decision_at=_decision(day))
    if future == "removed":
        mutated = h15.H15Snapshot(snapshot.two_year[:1], snapshot.ten_year[:1])
    elif future == "added":
        mutated = h15.H15Snapshot(
            snapshot.two_year + (_row(after + timedelta(days=1), "-100"),),
            snapshot.ten_year + (_row(after + timedelta(days=1), "100"),),
        )
    else:
        row = (
            _row(after, None, "ND")
            if future == "missing"
            else _row(after, "NaN" if future == "nonfinite" else "-100")
        )
        mutated = replace(snapshot, two_year=(snapshot.two_year[0], row))
    assert h15.select_h15_asof_pair(mutated, decision_at=_decision(day)) == expected


@pytest.mark.parametrize(
    "days,code",
    [
        ([date(2026, 1, 2), date(2026, 1, 2)], "duplicate_observation_date"),
        ([date(2026, 1, 3), date(2026, 1, 2)], "observation_date_order_invalid"),
    ],
)
def test_duplicate_and_nonmonotone_dates_fail_categorically(days: list[date], code: str) -> None:
    rows = h15._canonical_rows(_csv(tuple(_row(day, "1") for day in days)))
    with pytest.raises(h15.FederalReserveH15Error, match="^" + code + "$"):
        h15.H15Snapshot(rows, ())


@pytest.mark.parametrize(
    "body,code",
    [
        ("wrong,header\n", "csv_invalid"),
        ("2026-01-02,1\n", "csv_invalid"),
        ("20260102,1,\n", "date_invalid"),
        ("2026-01-02,,private-marker-canary\n", "missing_code_invalid"),
        ("2026-01-02,1,ND\n", "missing_code_invalid"),
        ("2026-01-02,private-value-canary,\n", "value_invalid"),
    ],
)
def test_csv_geometry_unknown_markers_and_values_never_escape_error_text(
    body: str, code: str
) -> None:
    prefix = (
        "observation_date,yield_percent,source_missing_code\n"
        if code != "csv_invalid" or body.startswith("2026")
        else ""
    )
    with pytest.raises(h15.FederalReserveH15Error) as error:
        h15._canonical_rows((prefix + body).encode())
    assert str(error.value) == code
    assert "canary" not in str(error.value)


def test_values_are_hidden_immutable_and_current_etf_prices_are_not_an_api_input() -> None:
    day = date(2026, 1, 2)
    row = _row(day, "98765.4321")
    snapshot = h15.H15Snapshot([row], [row])
    result = h15.select_h15_asof_pair(snapshot, decision_at=_decision(day))
    for representation in (
        repr(row),
        repr(snapshot),
        repr(result),
        json.dumps(result.safe_summary()),
    ):
        assert "98765" not in representation
    assert tuple(inspect.signature(h15.select_h15_asof_pair).parameters) == (
        "snapshot",
        "decision_at",
    )
    with pytest.raises(FrozenInstanceError):
        row.yield_percent = Decimal("0")
    with pytest.raises(FrozenInstanceError):
        result.spread_percent = Decimal("0")
    assert isinstance(snapshot.two_year, tuple)


@pytest.mark.parametrize(
    "decision",
    [
        datetime(2026, 2, 2),
        datetime(2026, 2, 2, tzinfo=timezone(timedelta(hours=9))),
        "private-canary",
    ],
)
def test_decision_requires_utc_without_echoing_input(decision: object) -> None:
    with pytest.raises(h15.FederalReserveH15Error, match="^decision_invalid$"):
        h15.select_h15_asof_pair(h15.H15Snapshot((), ()), decision_at=decision)


def test_fixed_production_pins_are_complete_and_not_caller_supplied() -> None:
    assert (
        h15.SNAPSHOT_SHA256["manifest.json"]
        == "sha256:6b2c62423470f12c17d22a634d4d5018ed7f6682d5a5875bc08c6ffd9e49e393"
    )
    assert (
        h15.SNAPSHOT_SHA256["source-attestation.json"]
        == "sha256:d7f6ea428eb2d9a834cd39d2969dd435a678d3e45c4838f21268d1eb68697fd3"
    )
    assert h15.SNAPSHOT_SHA256[h15.RAW_RELATIVE_PATH] == h15.RAW_SHA256
    assert tuple(inspect.signature(h15.read_federal_reserve_h15_snapshot).parameters) == ("root",)

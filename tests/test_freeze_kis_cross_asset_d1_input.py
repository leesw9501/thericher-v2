from __future__ import annotations

import csv
import gzip
import importlib.util
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution.kis_market_data import KisMarketDataResponse, KisPaperMarketDataConfig

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "freezer_test", ROOT / "scripts/freeze_kis_cross_asset_d1_input.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)
SECRET = "fake_secret_error_body"


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    base = tmp_path.parent / uuid.uuid4().hex[:8]
    market, artifacts = base / "m", base / "a"
    seconds = 0
    empty_symbol = None

    def clock():
        return datetime(2026, 10, 8, tzinfo=UTC) + timedelta(seconds=seconds)

    class Transport:
        def request(self, request):
            nonlocal seconds
            seconds += 1
            if request.method == "POST":
                return KisMarketDataResponse.from_payload({"access_token": "fake-token"})
            rows = (
                []
                if request.query["SYMB"] == empty_symbol
                else [
                    {
                        "xymd": d,
                        "open": "13.125",
                        "high": "20",
                        "low": "1",
                        "clos": "10",
                        "tvol": "100",
                    }
                    for d in ("20261007", "20261006")
                ]
            )
            return KisMarketDataResponse.from_payload(
                {"rt_cd": "0", "output1": {}, "output2": rows}
            )

    result = script.history.run_history(
        market_root=market,
        artifact_root=artifacts,
        repository_root=ROOT,
        run_label="synthetic-history",
        dotenv_path=base / "never-read.env",
        maximum_get_pages=3,
        clock=clock,
        monotonic=lambda: seconds,
        transport_factory=lambda **kwargs: Transport(),
        config_loader=lambda path: KisPaperMarketDataConfig("fake-key", "fake-secret"),
        space_check=lambda count: False,
    )
    assert result["accepted_page_count"] == 3
    calendar = artifacts / "calendar.json"
    calendar.write_text(
        json.dumps(
            {
                "kind": "caller_nyse_session_dates_v1",
                "calendar_attestation": "caller_predeclared_full_scope_nyse_sessions",
                "start": "2007-08-21",
                "end": "2026-10-07",
                "session_dates": ["2007-08-21", "2026-10-06", "2026-10-07"],
            }
        )
    )
    monkeypatch.setattr(
        script.history, "private_daily_cache_would_cross_free_space_floor", lambda **kwargs: False
    )
    kwargs = dict(
        history_receipt=Path(result["receipt_path"]),
        history_sha256=result["receipt_sha256"],
        calendar_path=calendar,
        calendar_sha256=script.probe._sha(calendar.read_bytes()),
        market_root=market,
        artifact_root=artifacts,
        repository_root=ROOT,
        run_label="freeze",
    )
    return SimpleNamespace(kwargs=kwargs, original=result, market=market, artifacts=artifacts)


def commitment(result):
    return json.loads(Path(result["commitment_path"]).read_bytes())


def live_index(fixture):
    receipt = json.loads(fixture.kwargs["history_receipt"].read_bytes())
    path = fixture.market / receipt["catalog"]["market_relative_path"]
    return path, json.loads(path.read_bytes())


def test_partial_history_freezes_only_existing_prices_with_gaps_and_vintages(fixture):
    result = script.freeze_input(**fixture.kwargs)
    assert result["status"] == "available"
    c = commitment(result)
    assert c["qualification"] == "not_claimed" and c["adjustment_mode"] == "MODP0_opaque"
    assert c["shared_observed_session_count"] == 2
    assert len(c["chunks"]) == 3
    assert c["history_receipt_sha256"] == fixture.kwargs["history_sha256"]
    for symbol, coverage in c["coverage"].items():
        assert coverage["price_row_count"] == 2 and coverage["expected_session_count"] == 3
        assert coverage["missing_session_dates"] == ["2007-08-21"]
        file = c["price_only_files"][symbol]
        path = fixture.market / file["market_relative_path"]
        assert script.probe._sha(path.read_bytes()) == file["sha256"]
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))
        assert tuple(rows[0]) == script.COLUMNS and "volume" not in rows[0]
        assert [r["session_date"] for r in rows] == ["2026-10-06", "2026-10-07"]
        assert rows[0]["open"] == "13.125"
        assert "13.125" not in json.dumps(c)
        chunk = next(x for x in c["chunks"] if x["symbol"] == symbol)
        assert (
            chunk["observed_at_utc"]
            == json.loads(
                (
                    live_index(fixture)[0].parent
                    / live_index(fixture)[1]["targets"][symbol]["chunks"][0]["manifest_path"]
                ).read_bytes()
            )["collected_at_utc"]
        )
    manifest = fixture.market / next(iter(c["price_only_files"].values()))["market_relative_path"]
    assert json.loads((manifest.parent / "manifest.json").read_bytes()) == c


def test_calendar_and_terminal_frozen_before_price_parser(fixture, monkeypatch):
    original = script.history._verify_index

    def check(*args):
        path = fixture.artifacts / f"research/{script.history.GOAL}/input/freeze/contract.json"
        assert path.exists()
        return original(*args)

    monkeypatch.setattr(script.history, "_verify_index", check)
    assert script.freeze_input(**fixture.kwargs)["status"] == "available"


@pytest.mark.parametrize("which", ["raw", "manifest", "intent"])
def test_changed_source_bytes_reject_without_price_publication(fixture, which):
    index_path, index = live_index(fixture)
    chunk = index["targets"]["SPY"]["chunks"][0]
    manifest_path = index_path.parent / chunk["manifest_path"]
    if which == "manifest":
        path = manifest_path
    elif which == "intent":
        path = index_path.parent / chunk["intent_path"]
    else:
        manifest = json.loads(manifest_path.read_bytes())
        path = manifest_path.parent / manifest["files"]["raw_daily_rows"]["path"]
    path.write_bytes(path.read_bytes() + b" ")
    result = script.freeze_input(**fixture.kwargs)
    assert result["status"] == "input_unavailable"
    assert not list(fixture.market.rglob("*-price-only.csv.gz"))
    assert not list(fixture.artifacts.rglob("input-commitment.json"))


def test_live_catalog_changed_rejects_exact_terminal_not_latest_scan(fixture):
    path, _ = live_index(fixture)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(script.FreezeError, match="source_hash_mismatch"):
        script.freeze_input(**fixture.kwargs)


@pytest.mark.parametrize(
    "dates",
    [
        ["2007-08-21", "2026-10-07", "2026-10-06"],
        ["2007-08-21", "2026-10-06", "2026-10-06", "2026-10-07"],
        ["2026-10-06", "2026-10-07"],
    ],
)
def test_invalid_caller_calendar_not_repaired_or_inferred(fixture, dates):
    path = fixture.kwargs["calendar_path"]
    doc = json.loads(path.read_bytes())
    doc["session_dates"] = dates
    path.write_text(json.dumps(doc))
    fixture.kwargs["calendar_sha256"] = script.probe._sha(path.read_bytes())
    with pytest.raises(script.FreezeError, match="calendar_invalid"):
        script.freeze_input(**fixture.kwargs)


def test_off_calendar_source_day_not_silently_dropped(fixture):
    path = fixture.kwargs["calendar_path"]
    doc = json.loads(path.read_bytes())
    doc["session_dates"] = ["2007-08-21", "2026-10-07"]
    path.write_text(json.dumps(doc))
    fixture.kwargs["calendar_sha256"] = script.probe._sha(path.read_bytes())
    result = script.freeze_input(**fixture.kwargs)
    assert result["reason"] == "off_calendar_source_date"
    assert not list(fixture.market.rglob("*-price-only.csv.gz"))


def test_final_source_change_rejects_without_commitment(fixture, monkeypatch):
    initial = script._pins(ROOT)
    reads = 0

    def pins(repo):
        nonlocal reads
        reads += 1
        return initial if reads == 1 else {**initial, "changed": "sha256:" + "0" * 64}

    monkeypatch.setattr(script, "_pins", pins)
    result = script.freeze_input(**fixture.kwargs)
    assert result["reason"] == "source_code_changed"
    assert not list(fixture.artifacts.rglob("input-commitment.json"))


def test_existing_frozen_output_never_overwritten(fixture):
    first = script.freeze_input(**fixture.kwargs)
    saved = Path(first["commitment_path"]).read_bytes()
    with pytest.raises(script.FreezeError, match="immutable_destination_exists"):
        script.freeze_input(**fixture.kwargs)
    assert Path(first["commitment_path"]).read_bytes() == saved


def test_redacted_cli_failure_no_environment_or_network(monkeypatch, capsys):
    def fail(**kwargs):
        raise OSError(SECRET)

    monkeypatch.setattr(script, "freeze_input", fail)
    assert (
        script.main(
            [
                "--history-receipt",
                "missing",
                "--history-sha256",
                "missing",
                "--calendar",
                "missing",
                "--calendar-sha256",
                "missing",
                "--run-label",
                "synthetic",
            ]
        )
        == 20
    )
    assert SECRET not in capsys.readouterr().out


def test_cli_compact_coverage_preserves_full_commitment_and_calendar(fixture, capsys):
    calendar_path = fixture.kwargs["calendar_path"]
    calendar = json.loads(calendar_path.read_bytes())
    calendar["sessions_utc"] = [{"date": "2026-10-07", "open": "2026-10-07T13:30:00Z"}]
    calendar_path.write_text(json.dumps(calendar))
    calendar_bytes = calendar_path.read_bytes()
    fixture.kwargs["calendar_sha256"] = script.probe._sha(calendar_bytes)
    source_pins = script._pins(ROOT)
    args = []
    for key, flag in (
        ("history_receipt", "--history-receipt"),
        ("history_sha256", "--history-sha256"),
        ("calendar_path", "--calendar"),
        ("calendar_sha256", "--calendar-sha256"),
        ("market_root", "--market-root"),
        ("artifact_root", "--artifact-root"),
        ("run_label", "--run-label"),
    ):
        args.extend((flag, str(fixture.kwargs[key])))
    assert script.main(args) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert len(output) < 2000
    assert "missing_session_dates" not in output and "13.125" not in output
    for coverage in result["coverage"].values():
        assert coverage == {
            "expected_session_count": 3,
            "price_row_count": 2,
            "oldest_date": "2026-10-06",
            "newest_date": "2026-10-07",
            "missing_session_count": 1,
        }
    assert commitment(result)["coverage"]["SPY"]["missing_session_dates"] == ["2007-08-21"]
    assert calendar_path.read_bytes() == calendar_bytes
    assert script._pins(ROOT) == source_pins

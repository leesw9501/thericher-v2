from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

import thericher_v2.data.daily as daily_module
from thericher_v2.data import (
    BROAD_DAILY_DEVELOPMENT_UNIVERSE,
    FIXED_ETF_DAILY_SYMBOLS,
    DevelopmentDailyStream,
    DevelopmentDailyUniverse,
    DevelopmentDailyUniverseRef,
    load_broad_daily_development_universe,
)
from thericher_v2.research.validation import run_local_paper_validation

SOURCE_COLUMNS = (
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adj_close",
    "asset_type",
    "yahoo_symbol",
    "source",
)


def test_loads_only_the_fixed_offline_development_universe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert BROAD_DAILY_DEVELOPMENT_UNIVERSE.common_session_start == date(2000, 5, 26)
    assert (
        BROAD_DAILY_DEVELOPMENT_UNIVERSE
        .development_ref_universe_is_inception_truncated_and_survivor_selected
        is True
    )
    reference = _install_fixture(tmp_path, monkeypatch)
    before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    universe = load_broad_daily_development_universe()
    loaded = universe.streams

    assert isinstance(universe, DevelopmentDailyUniverse)
    assert universe.reference == reference
    assert all(isinstance(stream, DevelopmentDailyStream) for stream in loaded)
    assert [stream.symbol for stream in loaded] == list(FIXED_ETF_DAILY_SYMBOLS)
    assert all(stream.dataset_id == reference.dataset_id for stream in loaded)
    assert all(stream.dataset_hash == reference.dataset_hash for stream in loaded)
    assert all(
        not hasattr(stream, "bars") and not hasattr(stream, "_bars")
        for stream in loaded
    )
    assert [stream.session_count for stream in loaded] == [2, 2, 2]
    assert all(
        stream.first_start_ts == loaded[0].first_start_ts
        and stream.last_start_ts == loaded[0].last_start_ts
        for stream in loaded[1:]
    )
    for value in (universe, *loaded):
        with pytest.raises(
            ValueError,
            match="campaign validation requires Data-owned CatalogedBars",
        ):
            run_local_paper_validation(
                value,
                event_store=None,
                emergency_store=None,
                campaign=object(),
            )
        with pytest.raises(TypeError):
            run_local_paper_validation(
                value,
                event_store=None,
                emergency_store=None,
            )
    assert reference.retrospective_development_replay_only is True
    assert (
        reference.development_ref_universe_is_inception_truncated_and_survivor_selected
        is True
    )
    assert reference.common_session_start == date(2026, 6, 18)
    assert all(
        stream.first_start_ts.date() == reference.common_session_start
        for stream in loaded
    )
    assert reference.point_in_time_eligible is False
    assert reference.survivorship_bias_risk == "present"
    assert reference.delisting_coverage == "unproven"
    assert reference.corporate_action_policy == "raw_ohlcv_unadjusted_unverified"
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == before


def test_rejects_snapshot_or_manifest_tampering_before_gzip_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _install_fixture(tmp_path, monkeypatch)

    def fail_decompression(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gzip parsing must not begin after hash failure")

    reference.snapshot_path.write_bytes(b"tampered snapshot")
    with monkeypatch.context() as parse_guard:
        parse_guard.setattr(daily_module.gzip, "open", fail_decompression)
        with pytest.raises(ValueError, match="snapshot hash mismatch"):
            load_broad_daily_development_universe()

    reference = _install_fixture(tmp_path / "manifest", monkeypatch)
    reference.manifest_path.write_text("{}\n", encoding="utf-8")
    with monkeypatch.context() as parse_guard:
        parse_guard.setattr(daily_module.gzip, "open", fail_decompression)
        with pytest.raises(ValueError, match="manifest hash mismatch"):
            load_broad_daily_development_universe()


def test_rejects_inconsistent_manifest_and_shifted_inception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _install_fixture(tmp_path, monkeypatch)
    manifest = json.loads(reference.manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot"] = "wrong-snapshot"
    reference.manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verified_manifest = replace(
        reference,
        manifest_hash=_sha256(reference.manifest_path.read_bytes()),
    )
    monkeypatch.setattr(
        daily_module,
        "BROAD_DAILY_DEVELOPMENT_UNIVERSE",
        verified_manifest,
    )
    with pytest.raises(ValueError, match="manifest snapshot is inconsistent"):
        load_broad_daily_development_universe()

    reference = _install_fixture(tmp_path / "inception", monkeypatch)
    shifted_inception = replace(reference, common_session_start=date(2026, 6, 22))
    monkeypatch.setattr(
        daily_module,
        "BROAD_DAILY_DEVELOPMENT_UNIVERSE",
        shifted_inception,
    )
    with pytest.raises(ValueError, match="latest fixed-symbol inception"):
        load_broad_daily_development_universe()


@pytest.mark.parametrize(
    "fault",
    ["missing", "duplicate", "non_monotonic", "ohlc"],
)
def test_rejects_missing_or_invalid_fixed_symbol_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    rows = _source_rows()
    if fault == "missing":
        rows = [row for row in rows if row["symbol"] != "IWM"]
    elif fault == "duplicate":
        rows.append(dict(rows[0]))
    elif fault == "non_monotonic":
        spy_rows = [row for row in rows if row["symbol"] == "SPY"]
        other_rows = [row for row in rows if row["symbol"] != "SPY"]
        rows = list(reversed(spy_rows)) + other_rows
    else:
        rows[0]["high"] = "99"
    _install_fixture(tmp_path, monkeypatch, rows=rows)

    with pytest.raises(ValueError):
        load_broad_daily_development_universe()


def _install_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: list[dict[str, str]] | None = None,
) -> DevelopmentDailyUniverseRef:
    snapshot_path = (
        tmp_path
        / "market_data"
        / "us_equities"
        / "yahoo_daily_universe"
        / "canonical"
        / "ohlcv_daily"
        / "snapshot=2026-06-23"
        / "ohlcv_daily.csv.gz"
    )
    manifest_path = (
        tmp_path
        / "market_data"
        / "us_equities"
        / "yahoo_daily_universe"
        / "manifests"
        / "yahoo_daily_universe_snapshot=2026-06-23.json"
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(snapshot_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows or _source_rows())
    dataset_hash = _sha256(snapshot_path.read_bytes())
    manifest = {
        "dataset": "yahoo_daily_universe",
        "schema_version": 1,
        "snapshot": "2026-06-23",
        "created_at_utc": "2026-06-23T06:14:33Z",
        "publish_status": "published",
        "partial_status": "complete",
        "request": {"interval": "1d"},
        "files": [
            {
                "path": str(snapshot_path),
                "bytes": snapshot_path.stat().st_size,
                "sha256": dataset_hash.removeprefix("sha256:"),
            }
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reference = replace(
        BROAD_DAILY_DEVELOPMENT_UNIVERSE,
        snapshot_path=snapshot_path,
        manifest_path=manifest_path,
        dataset_hash=dataset_hash,
        manifest_hash=_sha256(manifest_path.read_bytes()),
        common_session_start=date(2026, 6, 18),
    )
    monkeypatch.setattr(
        daily_module,
        "BROAD_DAILY_DEVELOPMENT_UNIVERSE",
        reference,
    )
    return reference


def _source_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for symbol in FIXED_ETF_DAILY_SYMBOLS:
        for session in (date(2026, 6, 18), date(2026, 6, 22)):
            rows.append(
                {
                    "symbol": symbol,
                    "date": session.isoformat(),
                    "open": "100",
                    "high": "110",
                    "low": "90",
                    "close": "105",
                    "volume": "1000",
                    "adj_close": "105",
                    "asset_type": "etf",
                    "yahoo_symbol": symbol,
                    "source": "yahoo_chart_unofficial",
                }
            )
    return rows


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

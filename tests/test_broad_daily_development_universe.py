from __future__ import annotations

import csv
import gzip
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data.daily as daily_module
import thericher_v2.research.development_daily_features as feature_module
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    BROAD_DAILY_DEVELOPMENT_UNIVERSE,
    FIXED_ETF_DAILY_SYMBOLS,
    DevelopmentDailyStream,
    DevelopmentDailyUniverse,
    DevelopmentDailyUniverseRef,
    load_broad_daily_development_universe,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.development_daily_features import (
    FEATURE_AVAILABILITY,
    FEATURE_NAMES,
    OUTCOME_AVAILABILITY,
    RAW_CLOSE_LIMITATION,
    RAW_NEXT_OBSERVED_CLOSE_OUTCOME_LIMITATION,
    materialize_development_daily_feature_outcomes,
    materialize_development_daily_features,
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
_SOURCE_SESSIONS = (
    date(2026, 6, 18),
    date(2026, 6, 22),
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
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
    assert [stream.session_count for stream in loaded] == [6, 6, 6]
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
    ["missing", "duplicate", "misaligned", "non_monotonic", "ohlc"],
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
    elif fault == "misaligned":
        rows = [
            row
            for row in rows
            if not (
                row["symbol"] == "QQQ"
                and row["date"] == _SOURCE_SESSIONS[5].isoformat()
            )
        ]
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
        writer.writerows(rows if rows is not None else _source_rows())
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


def test_materializes_immutable_descriptive_features_in_deterministic_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fixture(tmp_path, monkeypatch, rows=_source_rows(session_count=7))
    universe = load_broad_daily_development_universe()

    result = materialize_development_daily_features(universe)

    assert result.source is universe
    assert result.source_hash == universe.reference.dataset_hash
    assert result.feature_names == FEATURE_NAMES
    assert result.availability == FEATURE_AVAILABILITY
    assert result.raw_close_limitation == RAW_CLOSE_LIMITATION
    assert result.source.reference.corporate_action_policy == "raw_ohlcv_unadjusted_unverified"
    assert result.source.reference.survivorship_bias_risk == "present"
    assert result.source.reference.delisting_coverage == "unproven"
    assert [row.symbol for row in result.rows] == ["SPY", "QQQ", "IWM"] * 2
    assert [row.session for row in result.rows] == [
        _SOURCE_SESSIONS[5],
        _SOURCE_SESSIONS[5],
        _SOURCE_SESSIONS[5],
        _SOURCE_SESSIONS[6],
        _SOURCE_SESSIONS[6],
        _SOURCE_SESSIONS[6],
    ]

    first_spy = result.rows[0]
    assert first_spy.close_return_5_sessions == Decimal("107") / Decimal("102") - 1
    assert first_spy.close_return_1_session == Decimal("107") / Decimal("106") - 1
    assert first_spy.high_low_range == Decimal("110") / Decimal("100") - 1
    assert first_spy.volume_change_1_session == Decimal("1051") / Decimal("1041") - 1
    with pytest.raises(FrozenInstanceError):
        first_spy.symbol = "AAPL"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.source.streams[0].symbol = "AAPL"  # type: ignore[misc]


def test_feature_materializer_requires_six_completed_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fixture(tmp_path, monkeypatch, rows=_source_rows(session_count=5))

    with pytest.raises(ValueError, match="needs at least 6 sessions"):
        materialize_development_daily_features(load_broad_daily_development_universe())


def test_materializes_future_outcomes_in_next_observed_session_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fixture(tmp_path, monkeypatch, rows=_source_rows(session_count=7))
    features = materialize_development_daily_features(
        load_broad_daily_development_universe()
    )

    outcomes = materialize_development_daily_feature_outcomes(features)

    assert outcomes.feature_result is features
    assert outcomes.source_hash == features.source_hash
    assert outcomes.outcome_availability == OUTCOME_AVAILABILITY
    assert (
        outcomes.raw_next_observed_close_outcome_limitation
        == RAW_NEXT_OBSERVED_CLOSE_OUTCOME_LIMITATION
    )
    assert [row.feature.symbol for row in outcomes.rows] == ["SPY", "QQQ", "IWM"]
    assert [row.feature.session for row in outcomes.rows] == [_SOURCE_SESSIONS[5]] * 3
    assert [row.outcome_session for row in outcomes.rows] == [_SOURCE_SESSIONS[6]] * 3
    assert [row.calendar_days_to_outcome for row in outcomes.rows] == [3, 3, 3]
    assert outcomes.rows[0].raw_next_observed_close_return == (
        Decimal("108") / Decimal("107") - 1
    )
    with pytest.raises(FrozenInstanceError):
        outcomes.rows[0].outcome_session = date(2026, 7, 1)  # type: ignore[misc]


def test_outcome_materializer_uses_only_the_next_raw_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_rows = _source_rows(session_count=8)
    _install_fixture(tmp_path / "initial", monkeypatch, rows=initial_rows)
    initial = materialize_development_daily_feature_outcomes(
        materialize_development_daily_features(load_broad_daily_development_universe())
    )

    tail_changed_rows = [dict(row) for row in initial_rows]
    for row in tail_changed_rows:
        if row["date"] == _SOURCE_SESSIONS[7].isoformat():
            row.update(
                {
                    "open": "500",
                    "high": "510",
                    "low": "490",
                    "close": "505",
                    "volume": "999999",
                }
            )
    _install_fixture(tmp_path / "tail", monkeypatch, rows=tail_changed_rows)
    tail_changed = materialize_development_daily_feature_outcomes(
        materialize_development_daily_features(load_broad_daily_development_universe())
    )
    assert [
        row for row in initial.rows if row.outcome_session < _SOURCE_SESSIONS[7]
    ] == [
        row for row in tail_changed.rows if row.outcome_session < _SOURCE_SESSIONS[7]
    ]

    next_non_close_changed_rows = [dict(row) for row in initial_rows]
    for row in next_non_close_changed_rows:
        if row["date"] == _SOURCE_SESSIONS[6].isoformat():
            close = int(row["close"])
            row.update(
                {
                    "open": str(close - 1),
                    "high": str(close + 5),
                    "low": str(close - 5),
                    "volume": "999999",
                }
            )
    _install_fixture(tmp_path / "next-non-close", monkeypatch, rows=next_non_close_changed_rows)
    next_non_close_changed = materialize_development_daily_feature_outcomes(
        materialize_development_daily_features(load_broad_daily_development_universe())
    )
    assert [
        row for row in initial.rows if row.outcome_session == _SOURCE_SESSIONS[6]
    ] == [
        row
        for row in next_non_close_changed.rows
        if row.outcome_session == _SOURCE_SESSIONS[6]
    ]

    next_close_changed_rows = [dict(row) for row in initial_rows]
    for row in next_close_changed_rows:
        if row["date"] == _SOURCE_SESSIONS[6].isoformat():
            close = int(row["close"]) + 20
            row.update(
                {
                    "open": str(close - 1),
                    "high": str(close + 5),
                    "low": str(close - 5),
                    "close": str(close),
                }
            )
    _install_fixture(tmp_path / "next-close", monkeypatch, rows=next_close_changed_rows)
    next_close_changed = materialize_development_daily_feature_outcomes(
        materialize_development_daily_features(load_broad_daily_development_universe())
    )
    initial_next_rows = [
        row for row in initial.rows if row.outcome_session == _SOURCE_SESSIONS[6]
    ]
    changed_next_rows = [
        row
        for row in next_close_changed.rows
        if row.outcome_session == _SOURCE_SESSIONS[6]
    ]
    assert [row.feature for row in initial_next_rows] == [
        row.feature for row in changed_next_rows
    ]
    assert all(
        before.raw_next_observed_close_return
        != after.raw_next_observed_close_return
        for before, after in zip(initial_next_rows, changed_next_rows, strict=True)
    )


@pytest.mark.parametrize("artifact", ["snapshot", "manifest"])
def test_outcome_materializer_rejects_forged_or_tampered_feature_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact: str,
) -> None:
    _install_fixture(tmp_path / artifact, monkeypatch, rows=_source_rows(session_count=7))
    features = materialize_development_daily_features(
        load_broad_daily_development_universe()
    )

    with pytest.raises(ValueError, match="does not match re-attested source"):
        materialize_development_daily_feature_outcomes(replace(features, rows=()))
    with pytest.raises(ValueError, match="source hash is inconsistent"):
        materialize_development_daily_feature_outcomes(
            replace(features, source_hash="sha256:" + "0" * 64)
        )

    target = (
        features.source.reference.snapshot_path
        if artifact == "snapshot"
        else features.source.reference.manifest_path
    )
    target.write_bytes(b"tampered source")
    with pytest.raises(ValueError, match=f"{artifact} hash mismatch"):
        materialize_development_daily_feature_outcomes(features)


def test_feature_materializer_does_not_use_future_or_adjusted_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_rows = _source_rows(session_count=7)
    _install_fixture(tmp_path / "initial", monkeypatch, rows=initial_rows)
    initial = materialize_development_daily_features(load_broad_daily_development_universe())

    future_changed_rows = [dict(row) for row in initial_rows]
    future_changed_rows[-1].update(
        {
            "open": "500",
            "high": "510",
            "low": "490",
            "close": "505",
            "volume": "999999",
        }
    )
    _install_fixture(tmp_path / "future", monkeypatch, rows=future_changed_rows)
    future_changed = materialize_development_daily_features(
        load_broad_daily_development_universe()
    )
    assert [
        row for row in initial.rows if row.session < _SOURCE_SESSIONS[6]
    ] == [row for row in future_changed.rows if row.session < _SOURCE_SESSIONS[6]]

    adjusted_only_rows = [dict(row) for row in initial_rows]
    for row in adjusted_only_rows:
        row["adj_close"] = "999999"
    _install_fixture(tmp_path / "adjusted-only", monkeypatch, rows=adjusted_only_rows)
    adjusted_only = materialize_development_daily_features(
        load_broad_daily_development_universe()
    )
    assert adjusted_only.rows == initial.rows


def test_feature_materializer_rejects_stale_or_plain_cataloged_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fixture(tmp_path / "development", monkeypatch)
    universe = load_broad_daily_development_universe()
    stale_universe = replace(universe, streams=())

    with pytest.raises(ValueError, match="does not match re-attested source"):
        materialize_development_daily_features(stale_universe)
    universe.reference.snapshot_path.write_bytes(b"tampered snapshot")
    with pytest.raises(ValueError, match="snapshot hash mismatch"):
        materialize_development_daily_features(universe)

    _install_fixture(tmp_path / "guard", monkeypatch)
    with pytest.raises(PermissionError, match="restricted to Data-owned loaders"):
        daily_module._load_broad_daily_development_universe_data()

    universe = load_broad_daily_development_universe()
    with pytest.raises(PermissionError, match="restricted to its materializer"):
        daily_module._reverify_broad_daily_development_feature_input(universe)
    with pytest.raises(PermissionError, match="restricted to its materializer module"):
        feature_module._materialize_development_daily_features_from_streams(
            universe,
            (),
        )

    cataloged = _cataloged_bars_from_verified_loader(
        dataset_id="unit.cataloged.1d",
        dataset_hash="sha256:" + "0" * 64,
        source_path=tmp_path / "plain-cataloged.csv.gz",
        bars=(
            Bar(
                symbol="SPY",
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime(2026, 6, 18, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("1000"),
            ),
        ),
    )
    with pytest.raises(TypeError, match="require DevelopmentDailyUniverse"):
        materialize_development_daily_features((cataloged,))  # type: ignore[arg-type]

    outcome = materialize_development_daily_feature_outcomes(
        materialize_development_daily_features(universe)
    )
    with pytest.raises(TypeError, match="require DevelopmentDailyFeatureResult"):
        materialize_development_daily_feature_outcomes((cataloged,))  # type: ignore[arg-type]
    with pytest.raises(
        ValueError,
        match="campaign validation requires Data-owned CatalogedBars",
    ):
        run_local_paper_validation(
            outcome,
            event_store=None,
            emergency_store=None,
            campaign=object(),
        )


def _source_rows(*, session_count: int = 6) -> list[dict[str, str]]:
    if not 1 <= session_count <= len(_SOURCE_SESSIONS):
        raise ValueError("session_count is outside the deterministic fixture range")
    rows: list[dict[str, str]] = []
    for symbol_index, symbol in enumerate(FIXED_ETF_DAILY_SYMBOLS):
        for offset, session in enumerate(_SOURCE_SESSIONS[:session_count]):
            price = 100 + symbol_index * 100 + offset
            volume = 1000 + symbol_index * 100 + offset * 10
            rows.append(
                {
                    "symbol": symbol,
                    "date": session.isoformat(),
                    "open": str(price),
                    "high": str(price + 5),
                    "low": str(price - 5),
                    "close": str(price + 2),
                    "volume": str(volume),
                    "adj_close": str(price + 2),
                    "asset_type": "etf",
                    "yahoo_symbol": symbol,
                    "source": "yahoo_chart_unofficial",
                }
            )
    return rows


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

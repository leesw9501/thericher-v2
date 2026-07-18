from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import thericher_v2.data.tiingo_iex_intraday as intraday

_RETRIEVED_AT = datetime(2026, 7, 19, 3, 4, 5, tzinfo=UTC)
_ARCHIVE_BATCH_ONE_START = datetime(2026, 7, 19, 4, 0, tzinfo=UTC)


def test_archive_is_external_attested_offline_and_binds_r1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _archive_fixture(tmp_path)

    def unexpected_access(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("archive replay must not read credentials or network")

    monkeypatch.setattr(intraday, "read_tiingo_api_token", unexpected_access)
    monkeypatch.setattr(intraday, "_open_without_redirect", unexpected_access)
    loaded = intraday.load_tiingo_iex_pre_r1_archive_snapshot(
        fixture["archive_destination"],
        dataset_id=fixture["archive_result"].dataset_id,
        expected_dataset_hash=fixture["archive_result"].dataset_hash,
        expected_manifest_hash=fixture["archive_result"].manifest_hash,
        r1_snapshot_dir=fixture["r1_destination"],
        market_data_root=fixture["market_root"],
        repo_root=fixture["repo_root"],
    )

    manifest = json.loads(
        (fixture["archive_destination"] / "manifest.json").read_text(encoding="utf-8")
    )
    assert fixture["archive_result"].row_count == 63
    assert fixture["archive_result"].common_session_count == 21
    assert len(fixture["archive_result"].raw_chunk_hashes) == 63
    assert len(manifest["raw_sources"]) == 63
    assert manifest["archive_contract"]["request_count"] == 63
    assert manifest["archive_contract"]["coverage_policy"] == (
        "returned coverage is recorded; source-window completeness is not asserted"
    )
    assert manifest["raw_sources"][0]["returned_coverage"] == {
        "row_count": 1,
        "first_start_ts": "2017-12-29T14:30:00Z",
        "last_start_ts": "2017-12-29T14:30:00Z",
        "first_session": "2017-12-29",
        "last_session": "2017-12-29",
    }
    assert manifest["archive_contract"]["cross_chunk_overlap"] == {
        "detected": False,
        "policy": "strictly increasing start_ts per symbol across fixed window order",
    }
    assert manifest["r1_snapshot_reference"]["dataset_id"] == fixture["r1_result"].dataset_id
    assert (
        loaded.bars_by_symbol["SPY"][-1].start_ts
        < loaded.r1_snapshot.bars_by_symbol["SPY"][0].start_ts
    )
    assert not hasattr(loaded, "get_bars")
    assert not hasattr(loaded, "paper_trading")


def test_archive_reattests_attested_chunk_coverage(tmp_path: Path) -> None:
    fixture = _archive_fixture(tmp_path)
    manifest_path = fixture["archive_destination"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw_sources"][0]["returned_coverage"]["row_count"] = 2
    manifest_bytes = intraday._json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)

    with pytest.raises(ValueError, match="manifest content does not match"):
        intraday.load_tiingo_iex_pre_r1_archive_snapshot(
            fixture["archive_destination"],
            dataset_id=fixture["archive_result"].dataset_id,
            expected_dataset_hash=fixture["archive_result"].dataset_hash,
            expected_manifest_hash=intraday._sha256(manifest_bytes),
            r1_snapshot_dir=fixture["r1_destination"],
            market_data_root=fixture["market_root"],
            repo_root=fixture["repo_root"],
        )


def test_archive_rejects_capped_chunk_without_publishing_snapshot(tmp_path: Path) -> None:
    fixture = _r1_fixture(tmp_path)
    raw_chunks = _archive_raw_chunks()
    raw_chunks[("SPY", 1)] = json.dumps([{"date": "2017-08-01T14:30:00Z"}] * 10_000).encode()
    destination = fixture["market_root"] / "archive" / "snapshot=capped"
    raw_times, batch_timings, archive_retrieved_at = _archive_acquisition_timing()

    with pytest.raises(ValueError, match="reaches the 10000 row cap"):
        intraday.build_tiingo_iex_pre_r1_archive_snapshot(
            destination=destination,
            raw_chunks=raw_chunks,
            raw_chunk_retrieved_at_utc=raw_times,
            batch_timings=batch_timings,
            r1_snapshot_dir=fixture["r1_destination"],
            r1_dataset_id=fixture["r1_result"].dataset_id,
            r1_expected_dataset_hash=fixture["r1_result"].dataset_hash,
            r1_expected_manifest_hash=fixture["r1_result"].manifest_hash,
            retrieved_at_utc=archive_retrieved_at,
            market_data_root=fixture["market_root"],
            repo_root=fixture["repo_root"],
        )
    assert not destination.exists()


def test_archive_rejects_cross_chunk_overlap_and_preserves_r1_loader(tmp_path: Path) -> None:
    fixture = _archive_fixture(tmp_path)
    bar = fixture["r1_loaded"].bars_by_symbol["SPY"][0]
    repeated = {window.index: (bar,) for window in intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS}
    with pytest.raises(ValueError, match="chunks overlap"):
        intraday._merge_archive_bars("SPY", repeated)

    r1 = intraday.load_tiingo_iex_intraday_snapshot(
        fixture["r1_destination"],
        dataset_id=fixture["r1_result"].dataset_id,
        expected_dataset_hash=fixture["r1_result"].dataset_hash,
        expected_manifest_hash=fixture["r1_result"].manifest_hash,
        market_data_root=fixture["market_root"],
        repo_root=fixture["repo_root"],
    )
    assert r1.dataset_id == fixture["r1_result"].dataset_id


def test_archive_requires_external_destination_and_rejects_r1_overlap(tmp_path: Path) -> None:
    fixture = _r1_fixture(tmp_path)
    raw_times, batch_timings, archive_retrieved_at = _archive_acquisition_timing()
    repo_root = fixture["market_root"] / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    repo_destination = repo_root / "snapshot=unsafe"
    with pytest.raises(ValueError, match="outside Git"):
        intraday.build_tiingo_iex_pre_r1_archive_snapshot(
            destination=repo_destination,
            raw_chunks=_archive_raw_chunks(),
            raw_chunk_retrieved_at_utc=raw_times,
            batch_timings=batch_timings,
            r1_snapshot_dir=fixture["r1_destination"],
            r1_dataset_id=fixture["r1_result"].dataset_id,
            r1_expected_dataset_hash=fixture["r1_result"].dataset_hash,
            r1_expected_manifest_hash=fixture["r1_result"].manifest_hash,
            retrieved_at_utc=archive_retrieved_at,
            market_data_root=fixture["market_root"],
            repo_root=repo_root,
        )

    overlapping = _r1_fixture(tmp_path / "overlap", first_session=date(2026, 1, 8))
    raw_times, batch_timings, archive_retrieved_at = _archive_acquisition_timing()
    with pytest.raises(ValueError, match="not disjoint before r1"):
        intraday.build_tiingo_iex_pre_r1_archive_snapshot(
            destination=overlapping["market_root"] / "archive" / "snapshot=overlap",
            raw_chunks=_archive_raw_chunks(),
            raw_chunk_retrieved_at_utc=raw_times,
            batch_timings=batch_timings,
            r1_snapshot_dir=overlapping["r1_destination"],
            r1_dataset_id=overlapping["r1_result"].dataset_id,
            r1_expected_dataset_hash=overlapping["r1_result"].dataset_hash,
            r1_expected_manifest_hash=overlapping["r1_result"].manifest_hash,
            retrieved_at_utc=archive_retrieved_at,
            market_data_root=overlapping["market_root"],
            repo_root=overlapping["repo_root"],
        )


def test_archive_acquisition_uses_fixed_three_batch_schedule_without_partial_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _r1_fixture(tmp_path)
    raw_chunks = _archive_raw_chunks()
    calls: list[tuple[date, date]] = []
    clock = {"seconds": 0.0}

    def fetch(*, requested_start: date, source_as_of: date, **_kwargs: object) -> dict[str, bytes]:
        calls.append((requested_start, source_as_of))
        window = next(
            item
            for item in intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS
            if item.requested_start == requested_start and item.source_as_of == source_as_of
        )
        callback = _kwargs["on_response"]
        assert callable(callback)
        responses = {
            symbol: raw_chunks[(symbol, window.index)] for symbol in ("SPY", "QQQ", "IWM")
        }
        for symbol in responses:
            callback(symbol, intraday._utc_now())
        return responses

    monkeypatch.setattr(intraday, "fetch_tiingo_iex_intraday_responses", fetch)
    monkeypatch.setattr(intraday.time, "monotonic", lambda: clock["seconds"])
    monkeypatch.setattr(
        intraday,
        "_utc_now",
        lambda: _ARCHIVE_BATCH_ONE_START + timedelta(seconds=clock["seconds"]),
    )
    monkeypatch.setattr(
        intraday.time,
        "sleep",
        lambda seconds: clock.__setitem__("seconds", clock["seconds"] + seconds),
    )
    destination = fixture["market_root"] / "archive" / "snapshot=acquired"
    result = intraday.acquire_tiingo_iex_pre_r1_archive_snapshot(
        env_path=tmp_path / ".env",
        destination=destination,
        r1_snapshot_dir=fixture["r1_destination"],
        r1_dataset_id=fixture["r1_result"].dataset_id,
        r1_expected_dataset_hash=fixture["r1_result"].dataset_hash,
        r1_expected_manifest_hash=fixture["r1_result"].manifest_hash,
        retrieved_at_utc=_ARCHIVE_BATCH_ONE_START + timedelta(seconds=2 * 61 * 60),
        market_data_root=fixture["market_root"],
        repo_root=fixture["repo_root"],
    )
    assert calls == [
        (window.requested_start, window.source_as_of)
        for window in intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS
    ]
    assert clock["seconds"] == 2 * 61 * 60
    assert result.row_count == 63
    assert destination.is_dir()


def test_archive_acquisition_does_not_publish_partial_snapshot_on_fetch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _r1_fixture(tmp_path)
    destination = fixture["market_root"] / "archive" / "snapshot=failed"

    def fail_fetch(**_kwargs: object) -> dict[str, bytes]:
        raise intraday.TiingoIexIntradayAcquisitionError("Tiingo IEX request failed for SPY")

    monkeypatch.setattr(intraday, "fetch_tiingo_iex_intraday_responses", fail_fetch)
    with pytest.raises(intraday.TiingoIexIntradayAcquisitionError):
        intraday.acquire_tiingo_iex_pre_r1_archive_snapshot(
            env_path=tmp_path / ".env",
            destination=destination,
            r1_snapshot_dir=fixture["r1_destination"],
            r1_dataset_id=fixture["r1_result"].dataset_id,
            r1_expected_dataset_hash=fixture["r1_result"].dataset_hash,
            r1_expected_manifest_hash=fixture["r1_result"].manifest_hash,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=fixture["market_root"],
            repo_root=fixture["repo_root"],
        )
    assert not destination.exists()


def test_archive_acquisition_stops_on_first_invalid_chunk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _r1_fixture(tmp_path)
    raw_chunks = _archive_raw_chunks()
    calls: list[tuple[date, date]] = []
    destination = fixture["market_root"] / "archive" / "snapshot=invalid"

    def fetch(*, requested_start: date, source_as_of: date, **_kwargs: object) -> dict[str, bytes]:
        calls.append((requested_start, source_as_of))
        window = next(
            item
            for item in intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS
            if item.requested_start == requested_start and item.source_as_of == source_as_of
        )
        responses = {
            symbol: raw_chunks[(symbol, window.index)] for symbol in ("SPY", "QQQ", "IWM")
        }
        callback = _kwargs["on_response"]
        assert callable(callback)
        for symbol in responses:
            callback(symbol, _ARCHIVE_BATCH_ONE_START)
        responses["SPY"] = b"[]"
        return responses

    monkeypatch.setattr(intraday, "fetch_tiingo_iex_intraday_responses", fetch)
    with pytest.raises(ValueError, match="must be a nonempty array"):
        intraday.acquire_tiingo_iex_pre_r1_archive_snapshot(
            env_path=tmp_path / ".env",
            destination=destination,
            r1_snapshot_dir=fixture["r1_destination"],
            r1_dataset_id=fixture["r1_result"].dataset_id,
            r1_expected_dataset_hash=fixture["r1_result"].dataset_hash,
            r1_expected_manifest_hash=fixture["r1_result"].manifest_hash,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=fixture["market_root"],
            repo_root=fixture["repo_root"],
        )
    assert calls == [
        (
            intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS[0].requested_start,
            intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS[0].source_as_of,
        )
    ]
    assert not destination.exists()


def _archive_fixture(tmp_path: Path) -> dict[str, object]:
    fixture = _r1_fixture(tmp_path)
    destination = fixture["market_root"] / "archive" / "snapshot=pre-r1"
    raw_times, batch_timings, archive_retrieved_at = _archive_acquisition_timing()
    result = intraday.build_tiingo_iex_pre_r1_archive_snapshot(
        destination=destination,
        raw_chunks=_archive_raw_chunks(),
        raw_chunk_retrieved_at_utc=raw_times,
        batch_timings=batch_timings,
        r1_snapshot_dir=fixture["r1_destination"],
        r1_dataset_id=fixture["r1_result"].dataset_id,
        r1_expected_dataset_hash=fixture["r1_result"].dataset_hash,
        r1_expected_manifest_hash=fixture["r1_result"].manifest_hash,
        retrieved_at_utc=archive_retrieved_at,
        market_data_root=fixture["market_root"],
        repo_root=fixture["repo_root"],
    )
    fixture["archive_destination"] = destination
    fixture["archive_result"] = result
    fixture["r1_loaded"] = intraday.load_tiingo_iex_intraday_snapshot(
        fixture["r1_destination"],
        dataset_id=fixture["r1_result"].dataset_id,
        expected_dataset_hash=fixture["r1_result"].dataset_hash,
        expected_manifest_hash=fixture["r1_result"].manifest_hash,
        market_data_root=fixture["market_root"],
        repo_root=fixture["repo_root"],
    )
    return fixture


def _r1_fixture(tmp_path: Path, *, first_session: date = date(2026, 1, 13)) -> dict[str, object]:
    market_root = tmp_path / "market"
    market_root.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sessions = _weekdays(first_session, 20)
    destination = market_root / "r1" / "snapshot=r1-fixture"
    result = intraday.build_tiingo_iex_intraday_snapshot(
        destination=destination,
        raw_responses={symbol: _payload(sessions) for symbol in ("SPY", "QQQ", "IWM")},
        requested_start=sessions[0],
        source_as_of=sessions[-1],
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=market_root,
        repo_root=repo_root,
    )
    return {
        "market_root": market_root,
        "repo_root": repo_root,
        "r1_destination": destination,
        "r1_result": result,
    }


def _archive_raw_chunks() -> dict[tuple[str, int], bytes]:
    return {
        (symbol, window.index): _payload(
            [_last_weekday(window.requested_start, window.source_as_of)]
        )
        for symbol in ("SPY", "QQQ", "IWM")
        for window in intraday.TIINGO_IEX_PRE_R1_ARCHIVE_WINDOWS
    }


def _archive_acquisition_timing() -> tuple[
    dict[tuple[str, int], datetime],
    dict[int, tuple[datetime, datetime]],
    datetime,
]:
    raw_times: dict[tuple[str, int], datetime] = {}
    batch_timings: dict[int, tuple[datetime, datetime]] = {}
    for batch_index in range(1, 4):
        started_at = _ARCHIVE_BATCH_ONE_START + timedelta(seconds=(batch_index - 1) * 61 * 60)
        completed_at = started_at + timedelta(seconds=60)
        batch_timings[batch_index] = (started_at, completed_at)
        first_window_index = (batch_index - 1) * 7 + 1
        for window_index in range(first_window_index, first_window_index + 7):
            for offset, symbol in enumerate(("SPY", "QQQ", "IWM")):
                raw_times[(symbol, window_index)] = started_at + timedelta(seconds=offset)
    return raw_times, batch_timings, batch_timings[3][1]


def _weekdays(first: date, count: int) -> list[date]:
    result: list[date] = []
    value = first
    while len(result) < count:
        if value.weekday() < 5:
            result.append(value)
        value += timedelta(days=1)
    return result


def _last_weekday(start: date, end: date) -> date:
    value = end
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    assert value >= start
    return value


def _payload(sessions: list[date]) -> bytes:
    return json.dumps(
        [
            {
                "date": datetime.combine(session, datetime.min.time(), tzinfo=UTC)
                .replace(hour=14, minute=30)
                .isoformat()
                .replace("+00:00", "Z"),
                "open": "99",
                "high": "102",
                "low": "98",
                "close": "100",
                "volume": "1000",
            }
            for session in sessions
        ]
    ).encode()

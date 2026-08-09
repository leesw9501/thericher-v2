from __future__ import annotations

import gzip
import io
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

import thericher_v2.data.tiingo_iex_intraday as intraday

_REQUESTED_START = date(2026, 6, 1)
_SOURCE_AS_OF = date(2026, 6, 26)
_RETRIEVED_AT = datetime(2026, 7, 19, 2, 3, 4, tzinfo=UTC)


class _Response:
    status = 200

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_snapshot_is_external_attested_and_offline_reattested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    repo_root = market_root / "repo"
    repo_root.mkdir()
    destination = market_root / "intraday" / "snapshot=2026-07-19-tiingo-iex-5m-r1"
    result = intraday.build_tiingo_iex_intraday_snapshot(
        destination=destination,
        raw_responses=_responses(),
        requested_start=_REQUESTED_START,
        source_as_of=_SOURCE_AS_OF,
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=market_root,
        repo_root=repo_root,
    )

    def unexpected_access(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline loader must not read credentials or network")

    monkeypatch.setattr(intraday, "read_tiingo_api_token", unexpected_access)
    monkeypatch.setattr(intraday, "_open_without_redirect", unexpected_access)
    loaded = intraday.load_tiingo_iex_intraday_snapshot(
        destination,
        dataset_id=result.dataset_id,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )

    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert result.row_count == 60
    assert result.common_session_count == 20
    assert loaded.bars_by_symbol["SPY"][0].timeframe.value == "5m"
    assert manifest["scope"] == {
        "descriptive_replay_evidence_only": True,
        "training_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
        "campaign_eligible": False,
        "paper_trading_eligible": False,
        "profitability_evidence": False,
    }
    assert manifest["source_contract"]["venue_scope"] == (
        "IEX-only OHLCV; not consolidated market data"
    )
    assert not hasattr(loaded, "get_bars")
    with pytest.raises(FileExistsError, match="already exists"):
        intraday.build_tiingo_iex_intraday_snapshot(
            destination=destination,
            raw_responses=_responses(),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=market_root,
            repo_root=repo_root,
        )


def test_fetch_uses_only_approved_token_and_exact_fixed_iex_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TIINGO_API_TOKEN=test-token\n", encoding="utf-8")
    requests = []

    def opener(request, *, timeout: float):
        requests.append((request, timeout))
        symbol = urlparse(request.full_url).path.split("/")[-2]
        return _Response(_responses()[symbol])

    monkeypatch.setattr(intraday, "_open_without_redirect", opener)
    responses = intraday.fetch_tiingo_iex_intraday_responses(
        env_path=env_path,
        requested_start=_REQUESTED_START,
        source_as_of=_SOURCE_AS_OF,
    )

    assert set(responses) == {"SPY", "QQQ", "IWM"}
    assert len(requests) == 3
    for request, timeout in requests:
        parsed = urlparse(request.full_url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "api.tiingo.com"
        assert parsed.path in {
            "/iex/SPY/prices",
            "/iex/QQQ/prices",
            "/iex/IWM/prices",
        }
        assert parse_qs(parsed.query) == {
            "startDate": ["2026-06-01"],
            "endDate": ["2026-06-26"],
            "resampleFreq": ["5min"],
            "columns": ["open,high,low,close,volume"],
            "afterHours": ["false"],
            "forceFill": ["false"],
        }
        assert request.get_header("Authorization") == "Token test-token"
        assert timeout == 120.0

    monkeypatch.setattr(intraday, "read_tiingo_api_token", lambda _path: "test-token")
    monkeypatch.setattr(
        intraday,
        "_open_without_redirect",
        lambda *_args, **_kwargs: _raise_http_error(),
    )
    with pytest.raises(intraday.TiingoIexIntradayAcquisitionError, match="HTTP 403"):
        intraday.fetch_tiingo_iex_intraday_responses(
            env_path=env_path,
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )


def test_loader_rejects_tampered_raw_or_normalized_bytes(tmp_path: Path) -> None:
    market_root, repo_root, destination, result = _snapshot_fixture(tmp_path)
    raw_path = destination / "raw" / "SPY.json"
    raw = raw_path.read_bytes()
    raw_path.write_bytes(b"x" + raw[1:])
    with pytest.raises(ValueError, match="raw hash mismatch"):
        _load(destination, result, market_root, repo_root)

    market_root, repo_root, destination, result = _snapshot_fixture(tmp_path / "second")
    normalized_path = destination / "ohlcv_5m.csv.gz"
    normalized = normalized_path.read_bytes()
    normalized_path.write_bytes(b"x" + normalized[1:])
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        _load(destination, result, market_root, repo_root)


def test_loader_accepts_equivalent_gzip_encoding_but_rejects_changed_canonical_content(
    tmp_path: Path,
) -> None:
    market_root, repo_root, destination, result = _snapshot_fixture(tmp_path)
    normalized_path = destination / "ohlcv_5m.csv.gz"
    canonical = gzip.decompress(normalized_path.read_bytes())

    equivalent = _gzip_with_level(canonical, level=1)
    assert equivalent != normalized_path.read_bytes()
    equivalent_hash, equivalent_manifest_hash = _rewrite_normalized_manifest(
        destination,
        equivalent,
    )
    loaded = intraday.load_tiingo_iex_intraday_snapshot(
        destination,
        dataset_id=result.dataset_id,
        expected_dataset_hash=equivalent_hash,
        expected_manifest_hash=equivalent_manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )
    assert loaded.dataset_hash == equivalent_hash

    changed = _gzip_with_level(canonical + b"x", level=1)
    changed_hash, changed_manifest_hash = _rewrite_normalized_manifest(destination, changed)
    with pytest.raises(ValueError, match="does not match attested raw bytes"):
        intraday.load_tiingo_iex_intraday_snapshot(
            destination,
            dataset_id=result.dataset_id,
            expected_dataset_hash=changed_hash,
            expected_manifest_hash=changed_manifest_hash,
            market_data_root=market_root,
            repo_root=repo_root,
        )


def test_normalizer_preserves_gapped_sessions_but_rejects_invalid_timestamps() -> None:
    rows = _rows("SPY")
    normalized = intraday.normalize_tiingo_iex_intraday_response(
        symbol="SPY",
        raw_response=_payload(rows),
        requested_start=_REQUESTED_START,
        source_as_of=_SOURCE_AS_OF,
    )
    assert len(normalized) == 20

    unaligned_rows = _rows("SPY")
    unaligned_rows[0]["date"] = "2026-06-01T13:31:00Z"
    with pytest.raises(ValueError, match="not aligned to 5-minute bars"):
        intraday.normalize_tiingo_iex_intraday_response(
            symbol="SPY",
            raw_response=_payload(unaligned_rows),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )

    after_hours_rows = _rows("SPY")
    after_hours_rows[0]["date"] = "2026-06-01T12:00:00Z"
    with pytest.raises(ValueError, match="outside regular-session bounds"):
        intraday.normalize_tiingo_iex_intraday_response(
            symbol="SPY",
            raw_response=_payload(after_hours_rows),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )

    rows[1]["date"] = rows[0]["date"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        intraday.normalize_tiingo_iex_intraday_response(
            symbol="SPY",
            raw_response=_payload(rows),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )


def test_normalizer_identifies_the_timestamp_of_invalid_ohlcv() -> None:
    rows = _rows("SPY")
    rows[0]["high"] = "99"
    with pytest.raises(ValueError, match="SPY at 2026-06-01T13:30:00Z"):
        intraday.normalize_tiingo_iex_intraday_response(
            symbol="SPY",
            raw_response=_payload(rows),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )


def test_build_rejects_repo_destination_and_insufficient_common_sessions(tmp_path: Path) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    repo_root = market_root / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        intraday.build_tiingo_iex_intraday_snapshot(
            destination=repo_root / "snapshot=unsafe",
            raw_responses=_responses(),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=market_root,
            repo_root=repo_root,
        )

    short_rows = _rows("SPY")[:19]
    with pytest.raises(ValueError, match="does not reach source_as_of"):
        intraday.normalize_tiingo_iex_intraday_response(
            symbol="SPY",
            raw_response=_payload(short_rows),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )


def _snapshot_fixture(tmp_path: Path):
    market_root = tmp_path / "market"
    market_root.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    destination = market_root / "intraday" / "snapshot=fixture"
    result = intraday.build_tiingo_iex_intraday_snapshot(
        destination=destination,
        raw_responses=_responses(),
        requested_start=_REQUESTED_START,
        source_as_of=_SOURCE_AS_OF,
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=market_root,
        repo_root=repo_root,
    )
    return market_root, repo_root, destination, result


def _load(destination: Path, result, market_root: Path, repo_root: Path):
    return intraday.load_tiingo_iex_intraday_snapshot(
        destination,
        dataset_id=result.dataset_id,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )


def _gzip_with_level(data: bytes, *, level: int) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        fileobj=buffer,
        mode="wb",
        mtime=0,
        compresslevel=level,
    ) as stream:
        stream.write(data)
    return buffer.getvalue()


def _rewrite_normalized_manifest(destination: Path, normalized: bytes) -> tuple[str, str]:
    normalized_path = destination / "ohlcv_5m.csv.gz"
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_hash = intraday._sha256(normalized)
    manifest["dataset_hash"] = dataset_hash
    manifest["normalized_data"]["sha256"] = dataset_hash
    manifest["normalized_data"]["size_bytes"] = len(normalized)
    manifest_bytes = intraday._json_bytes(manifest)
    normalized_path.write_bytes(normalized)
    manifest_path.write_bytes(manifest_bytes)
    return dataset_hash, intraday._sha256(manifest_bytes)


def _responses() -> dict[str, bytes]:
    return {symbol: _payload(_rows(symbol)) for symbol in ("SPY", "QQQ", "IWM")}


def _rows(symbol: str) -> list[dict[str, str]]:
    del symbol
    rows: list[dict[str, str]] = []
    session = _REQUESTED_START
    while len(rows) < 20:
        if session.weekday() < 5:
            rows.append(_row(session, close=str(100 + len(rows))))
        session += timedelta(days=1)
    assert session - timedelta(days=1) == _SOURCE_AS_OF
    return rows


def _row(session: date, *, close: str) -> dict[str, str]:
    timestamp = datetime.combine(session, time(13, 30), tzinfo=UTC)
    close_value = int(close)
    return {
        "date": timestamp.isoformat().replace("+00:00", "Z"),
        "open": str(close_value - 1),
        "high": str(close_value + 2),
        "low": str(close_value - 2),
        "close": close,
        "volume": "1000",
    }


def _payload(rows: list[dict[str, str]]) -> bytes:
    return json.dumps(rows).encode("utf-8")


def _raise_http_error() -> _Response:
    raise HTTPError("https://api.tiingo.com", 403, "forbidden", {}, None)

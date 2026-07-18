from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

import thericher_v2.data.tiingo_full_history as full_history

_REQUESTED_START = date(1900, 1, 1)
_SOURCE_AS_OF = date(2026, 7, 10)
_RETRIEVED_AT = datetime(2026, 7, 18, 2, 3, 4, tzinfo=UTC)


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


def test_snapshot_is_external_immutable_and_offline_reattested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    repo_root = market_root / "repo"
    repo_root.mkdir()
    destination = market_root / "full-history" / "snapshot=2026-07-18-tiingo-eod-full-history-r1"
    result = full_history.build_tiingo_full_history_eod_snapshot(
        destination=destination,
        raw_responses=_responses(),
        requested_start=_REQUESTED_START,
        source_as_of=_SOURCE_AS_OF,
        retrieved_at_utc=_RETRIEVED_AT,
        market_data_root=market_root,
        repo_root=repo_root,
    )

    def unexpected_access(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline loader must not access a token or the network")

    monkeypatch.setattr(full_history, "read_tiingo_api_token", unexpected_access)
    monkeypatch.setattr(full_history, "_open_without_redirect", unexpected_access)
    loaded = full_history.load_tiingo_full_history_eod_snapshot(
        destination,
        dataset_id=result.dataset_id,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )

    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    normalized = gzip.decompress((destination / "ohlcv_1d.csv.gz").read_bytes())
    assert result.row_count == 8
    assert loaded.rows_by_symbol["SPY"][0].session_date == date(1993, 1, 29)
    assert loaded.rows_by_symbol["IWM"][-1].session_date == _SOURCE_AS_OF
    assert manifest["scope"] == {
        "development_evidence_only": True,
        "point_in_time_eligible": False,
        "ranking_eligible": False,
        "sealed_holdout_eligible": False,
        "campaign_eligible": False,
        "paper_trading_eligible": False,
    }
    assert b"adjClose" not in normalized
    assert not hasattr(loaded, "bars")
    with pytest.raises(FileExistsError, match="already exists"):
        full_history.build_tiingo_full_history_eod_snapshot(
            destination=destination,
            raw_responses=_responses(),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=market_root,
            repo_root=repo_root,
        )


def test_loader_rejects_tampered_raw_or_normalized_evidence(tmp_path: Path) -> None:
    market_root, repo_root, destination, result = _snapshot_fixture(tmp_path)
    raw_path = destination / "raw" / "SPY.json"
    raw = raw_path.read_bytes()
    raw_path.write_bytes(b"x" + raw[1:])
    with pytest.raises(ValueError, match="raw hash mismatch"):
        _load(destination, result, market_root, repo_root)

    market_root, repo_root, destination, result = _snapshot_fixture(tmp_path / "second")
    normalized_path = destination / "ohlcv_1d.csv.gz"
    normalized = normalized_path.read_bytes()
    normalized_path.write_bytes(b"x" + normalized[1:])
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        _load(destination, result, market_root, repo_root)


def test_normalizer_rejects_out_of_window_and_adjusted_data_is_not_consumed() -> None:
    rows = _payload_rows("SPY")
    rows.append(_row(date(2026, 7, 11)))
    with pytest.raises(ValueError, match="outside the requested window"):
        full_history.normalize_tiingo_full_history_response(
            symbol="SPY",
            raw_response=_payload(rows),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )
    with pytest.raises(ValueError, match="does not reach source_as_of"):
        full_history.normalize_tiingo_full_history_response(
            symbol="SPY",
            raw_response=_payload([_row(date(1993, 1, 29))]),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )

    normalized = full_history.normalize_tiingo_full_history_response(
        symbol="SPY",
        raw_response=_payload(_payload_rows("SPY")),
        requested_start=_REQUESTED_START,
        source_as_of=_SOURCE_AS_OF,
    )
    assert normalized[0].close == 100
    assert not hasattr(normalized[0], "adj_close")


def test_fetch_uses_only_approved_token_and_exact_three_standard_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TIINGO_API_TOKEN=test-token\n", encoding="utf-8")
    requests = []

    def opener(request, *, timeout: float):
        requests.append((request, timeout))
        symbol = urlparse(request.full_url).path.split("/")[-2]
        return _Response(_payload(_payload_rows(symbol)))

    monkeypatch.setattr(full_history, "_open_without_redirect", opener)
    responses = full_history.fetch_tiingo_full_history_responses(
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
            "/tiingo/daily/SPY/prices",
            "/tiingo/daily/QQQ/prices",
            "/tiingo/daily/IWM/prices",
        }
        assert parse_qs(parsed.query) == {
            "startDate": ["1900-01-01"],
            "endDate": ["2026-07-10"],
        }
        assert request.get_header("Authorization") == "Token test-token"
        assert timeout == 30.0

    monkeypatch.setattr(full_history, "read_tiingo_api_token", lambda _path: "test-token")
    monkeypatch.setattr(
        full_history,
        "_open_without_redirect",
        lambda *_args, **_kwargs: _raise_http_error(),
    )
    with pytest.raises(full_history.TiingoFullHistoryAcquisitionError, match="HTTP 403"):
        full_history.fetch_tiingo_full_history_responses(
            env_path=env_path,
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )


def test_fetch_rejects_redirect_before_authorization_can_be_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("TIINGO_API_TOKEN=test-token\n", encoding="utf-8")

    class _RedirectingOpener:
        def __init__(self, handler: full_history._RejectRedirect) -> None:
            self._handler = handler

        def open(self, request, *, timeout: float):
            return self._handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://untrusted.example/redirect",
            )

    monkeypatch.setattr(
        full_history,
        "build_opener",
        lambda handler: _RedirectingOpener(handler),
    )
    with pytest.raises(full_history.TiingoFullHistoryAcquisitionError, match="redirects"):
        full_history.fetch_tiingo_full_history_responses(
            env_path=env_path,
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
        )


def test_build_rejects_inconsistent_common_sessions(tmp_path: Path) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    responses = _responses()
    spy_rows = _payload_rows("SPY")
    spy_rows.insert(len(spy_rows) - 1, _row(date(2026, 7, 9)))
    responses["SPY"] = _payload(spy_rows)
    with pytest.raises(ValueError, match="common session coverage"):
        full_history.build_tiingo_full_history_eod_snapshot(
            destination=market_root / "snapshot=inconsistent",
            raw_responses=responses,
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=market_root,
        )


def test_build_rejects_repo_destination_and_insufficient_retrieval_lag(tmp_path: Path) -> None:
    market_root = tmp_path / "market"
    market_root.mkdir()
    repo_root = market_root / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        full_history.build_tiingo_full_history_eod_snapshot(
            destination=repo_root / "snapshot=unsafe",
            raw_responses=_responses(),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
            retrieved_at_utc=_RETRIEVED_AT,
            market_data_root=market_root,
            repo_root=repo_root,
        )
    with pytest.raises(ValueError, match="too close"):
        full_history.build_tiingo_full_history_eod_snapshot(
            destination=market_root / "snapshot=too-soon",
            raw_responses=_responses(),
            requested_start=_REQUESTED_START,
            source_as_of=_SOURCE_AS_OF,
            retrieved_at_utc=datetime(2026, 7, 16, tzinfo=UTC),
            market_data_root=market_root,
            repo_root=repo_root,
        )


def _snapshot_fixture(tmp_path: Path):
    market_root = tmp_path / "market"
    market_root.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    destination = market_root / "full-history" / "snapshot=fixture"
    result = full_history.build_tiingo_full_history_eod_snapshot(
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
    return full_history.load_tiingo_full_history_eod_snapshot(
        destination,
        dataset_id=result.dataset_id,
        expected_dataset_hash=result.dataset_hash,
        expected_manifest_hash=result.manifest_hash,
        market_data_root=market_root,
        repo_root=repo_root,
    )


def _responses() -> dict[str, bytes]:
    return {symbol: _payload(_payload_rows(symbol)) for symbol in ("SPY", "QQQ", "IWM")}


def _payload_rows(symbol: str) -> list[dict[str, str]]:
    starts = {"SPY": date(1993, 1, 29), "QQQ": date(1999, 3, 10), "IWM": date(2000, 5, 26)}
    rows = [_row(starts[symbol])]
    common_start = starts["IWM"]
    if starts[symbol] < common_start:
        rows.append(_row(common_start))
    rows.append(_row(_SOURCE_AS_OF, close="101"))
    return rows


def _row(session: date, *, close: str = "100") -> dict[str, str]:
    return {
        "date": f"{session.isoformat()}T00:00:00.000Z",
        "open": "99",
        "high": "102",
        "low": "98",
        "close": close,
        "volume": "1000",
        "divCash": "0",
        "splitFactor": "1",
        "adjClose": "7",
    }


def _payload(rows: list[dict[str, str]]) -> bytes:
    return json.dumps(rows).encode("utf-8")


def _raise_http_error() -> _Response:
    raise HTTPError("https://api.tiingo.com", 403, "forbidden", {}, None)

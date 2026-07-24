from __future__ import annotations

import json
import os
import socket
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

import thericher_v2.data.kis_daily_corporate_actions as sidecar_module
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_daily_corporate_actions import (
    KisDailyCorporateActionError,
    build_kis_daily_corporate_action_snapshot,
    fetch_kis_daily_tiingo_corporate_action_responses,
    load_kis_daily_corporate_action_snapshot,
)
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.local import _cataloged_bars_from_verified_loader

_SESSIONS = (
    date(2024, 3, 14),
    date(2024, 3, 15),
    date(2024, 3, 18),
    date(2024, 3, 19),
)
_HASH = "sha256:" + "a" * 64
_INDEX_HASH = "sha256:" + "b" * 64


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


def test_price_free_sidecar_is_hash_bound_and_offline_reload_needs_no_credentials_or_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _catalog(tmp_path)
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    destination = market_root / "sidecars" / "snapshot=unit"
    snapshot = build_kis_daily_corporate_action_snapshot(
        destination=destination,
        raw_responses=_responses(),
        catalog=catalog,
        retrieved_at_utc=datetime(2026, 7, 25, 1, 2, 3, tzinfo=UTC),
        market_data_root=market_root,
        repo_root=tmp_path / "repo",
    )

    persisted = b"".join(path.read_bytes() for path in destination.iterdir())
    assert b"QUOTE_SENTINEL" not in persisted
    assert b"adjClose" not in persisted
    assert b"close" not in persisted
    assert not (destination / "raw").exists()
    assert snapshot.event_counts["QQQ"]["cash_distribution"] == 1
    assert snapshot.event_counts["SPY"]["cash_distribution"] == 1

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline sidecar loader must not open a network connection")

    def no_credential_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline sidecar loader must not read a credential")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(os, "getenv", no_credential_read)
    monkeypatch.setattr(sidecar_module, "urlopen", no_network)
    monkeypatch.setattr(sidecar_module, "read_tiingo_api_token", no_credential_read)

    reloaded = load_kis_daily_corporate_action_snapshot(
        destination,
        catalog=catalog,
        expected_dataset_hash=snapshot.dataset_hash,
        expected_manifest_hash=snapshot.manifest_hash,
        repo_root=tmp_path / "repo",
    )

    assert reloaded.events == snapshot.events


def test_fetch_uses_only_tiingo_eod_for_qqq_and_spy(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "KIS_PAPER_APP_KEY=must-not-be-used\nTIINGO_API_TOKEN=unit-token\n",
        encoding="utf-8",
    )
    requests = []

    def opener(request: object, **_kwargs: object) -> _Response:
        requests.append(request)
        assert hasattr(request, "full_url")
        symbol = "QQQ" if "/QQQ/" in request.full_url else "SPY"
        return _Response(_responses()[symbol])

    responses = fetch_kis_daily_tiingo_corporate_action_responses(
        env_path=env_path,
        start_session=_SESSIONS[0],
        end_session=_SESSIONS[-1],
        opener=opener,
    )

    assert tuple(responses) == ("QQQ", "SPY")
    assert len(requests) == 2
    assert all(
        request.full_url.startswith("https://api.tiingo.com/tiingo/daily/") for request in requests
    )
    assert all("startDate=2024-03-14" in request.full_url for request in requests)
    assert all("endDate=2024-03-19" in request.full_url for request in requests)
    assert all(request.get_header("Authorization") == "Token unit-token" for request in requests)


def test_sidecar_fails_closed_for_coverage_gap_and_does_not_create_a_snapshot(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    destination = market_root / "snapshot=missing-session"
    responses = _responses()
    rows = json.loads(responses["SPY"].decode("utf-8"))
    responses["SPY"] = json.dumps(rows[:-1]).encode("utf-8")

    with pytest.raises(ValueError, match="session coverage is incomplete"):
        build_kis_daily_corporate_action_snapshot(
            destination=destination,
            raw_responses=responses,
            catalog=catalog,
            retrieved_at_utc=datetime(2026, 7, 25, 1, 2, 3, tzinfo=UTC),
            market_data_root=market_root,
            repo_root=tmp_path / "repo",
        )

    assert not destination.exists()


def test_sidecar_requires_at_least_one_event_per_symbol(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    market_root = tmp_path / "market-data"
    market_root.mkdir()
    responses = _responses()
    rows = json.loads(responses["QQQ"].decode("utf-8"))
    for row in rows:
        row["divCash"] = 0
    responses["QQQ"] = json.dumps(rows).encode("utf-8")

    with pytest.raises(ValueError, match="has no events for QQQ"):
        build_kis_daily_corporate_action_snapshot(
            destination=market_root / "snapshot=missing-anchor",
            raw_responses=responses,
            catalog=catalog,
            retrieved_at_utc=datetime(2026, 7, 25, 1, 2, 3, tzinfo=UTC),
            market_data_root=market_root,
            repo_root=tmp_path / "repo",
        )


def test_sidecar_rejects_a_git_destination_before_writing(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        build_kis_daily_corporate_action_snapshot(
            destination=repo_root / "snapshot=wrong-place",
            raw_responses=_responses(),
            catalog=catalog,
            retrieved_at_utc=datetime(2026, 7, 25, 1, 2, 3, tzinfo=UTC),
            market_data_root=tmp_path,
            repo_root=repo_root,
        )


def test_fetch_hides_a_missing_token_error(tmp_path: Path) -> None:
    with pytest.raises(KisDailyCorporateActionError, match="Tiingo token is unavailable"):
        fetch_kis_daily_tiingo_corporate_action_responses(
            env_path=tmp_path / ".env",
            start_session=_SESSIONS[0],
            end_session=_SESSIONS[-1],
        )


def _catalog(tmp_path: Path) -> KisPaperPrivateDailyCatalog:
    source_path = tmp_path / "catalog-index.json"
    source_path.write_text("{}\n", encoding="utf-8")
    bars_by_symbol = {}
    for position, symbol in enumerate(("QQQ", "SPY"), start=1):
        bars = tuple(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                open=Decimal("100") + position,
                high=Decimal("102") + position,
                low=Decimal("99") + position,
                close=Decimal("101") + position,
                volume=Decimal("1000"),
                complete=True,
            )
            for session in _SESSIONS
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id="unit-kis-daily",
            dataset_hash=_HASH,
            source_path=source_path,
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id="unit-kis-daily",
        dataset_hash=_HASH,
        index_hash=_INDEX_HASH,
        index_path=source_path,
        source_root=tmp_path,
        adjustment_mode="MODP=0_unadjusted",
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        common_sessions=_SESSIONS,
        raw_price_limitations=("MODP=0_unadjusted", "corporate_action_semantics_not_qualified"),
    )


def _responses() -> dict[str, bytes]:
    return {
        "QQQ": _payload(event_date=date(2024, 3, 15), amount="0.57"),
        "SPY": _payload(event_date=date(2024, 3, 18), amount="1.23"),
    }


def _payload(*, event_date: date, amount: str) -> bytes:
    return json.dumps(
        [
            {
                "date": f"{session.isoformat()}T00:00:00.000Z",
                "divCash": amount if session == event_date else "0",
                "splitFactor": "1",
                "close": "QUOTE_SENTINEL",
                "adjClose": "QUOTE_SENTINEL",
            }
            for session in _SESSIONS
        ]
    ).encode("utf-8")

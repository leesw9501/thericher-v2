from __future__ import annotations

import json
import os
import socket
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.daily_three_etf_relative_strength import (
    DailyThreeEtfRelativeStrengthConfig,
    run_daily_three_etf_relative_strength,
)

_SYMBOLS = ("QQQ", "SPY", "IWM")
_DATASET_HASH = "sha256:" + "a" * 64


def test_runs_causal_relative_strength_through_replayable_local_paper_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _catalog(
        tmp_path,
        steps={"QQQ": Decimal("3"), "SPY": Decimal("1"), "IWM": Decimal("-1")},
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local-paper baseline must not open a network connection")

    def no_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local-paper baseline must not read credentials")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(os, "getenv", no_environment)
    result = run_daily_three_etf_relative_strength(
        catalog,
        config=DailyThreeEtfRelativeStrengthConfig(run_id="unit-uptrend"),
        artifact_root=tmp_path / "artifacts",
        repo_root=repo_root,
    )

    assert result.dataset_id == "kis.paper.private.daily.backfill-v1.common-panel"
    assert len(result.decisions) == 3
    assert all(decision.selected_symbol == "QQQ" for decision in result.decisions)
    assert len(result.trades) == 6
    assert result.local_paper_fill_count == 6
    assert result.all_fills_local_paper is True
    assert {trade.source for trade in result.trades} == {"local_paper"}
    assert result.final_position_count == 0
    assert result.replayed_final_position_count == 0
    assert result.event_jsonl_path.is_file()
    assert result.event_jsonl_path.is_relative_to(tmp_path / "artifacts")
    assert not result.event_jsonl_path.is_relative_to(repo_root)
    assert result.run_manifest_path.is_relative_to(tmp_path / "artifacts")
    manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
    assert manifest["dataset"]["dataset_hash"] == result.dataset_hash
    assert manifest["strategy"]["lookback_sessions"] == 20
    assert manifest["execution"]["broker"] == "local_paper"
    assert manifest["evidence"]["event_jsonl_sha256"] == result.event_jsonl_sha256
    with sqlite3.connect(result.event_jsonl_path.parent / "state.sqlite") as connection:
        latest = connection.execute(
            "select market, symbol, action from latest_decisions"
        ).fetchall()
    assert latest == [("US", "QQQ-SPY-IWM", "enter")]


def test_abstains_when_no_etf_has_positive_lookback_return(tmp_path: Path) -> None:
    catalog = _catalog(
        tmp_path,
        steps={"QQQ": Decimal("-1"), "SPY": Decimal("-2"), "IWM": Decimal("-3")},
    )
    result = run_daily_three_etf_relative_strength(
        catalog,
        config=DailyThreeEtfRelativeStrengthConfig(run_id="unit-downtrend"),
        artifact_root=tmp_path / "artifacts",
    )

    assert result.abstain_count == 3
    assert not result.trades
    assert result.local_paper_fill_count == 0
    assert result.all_fills_local_paper is True
    assert result.ending_cash == result.starting_cash


def test_rejects_artifact_root_inside_git(tmp_path: Path) -> None:
    catalog = _catalog(
        tmp_path,
        steps={"QQQ": Decimal("3"), "SPY": Decimal("1"), "IWM": Decimal("-1")},
    )
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        run_daily_three_etf_relative_strength(
            catalog,
            config=DailyThreeEtfRelativeStrengthConfig(run_id="inside-git"),
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
        )


def _catalog(
    tmp_path: Path,
    *,
    steps: dict[str, Decimal],
) -> KisPaperPrivateDailyCatalog:
    sessions = tuple(date(2026, 1, 2) + timedelta(days=index) for index in range(27))
    streams = {}
    starting_prices = {"QQQ": Decimal("100"), "SPY": Decimal("200"), "IWM": Decimal("300")}
    for symbol in _SYMBOLS:
        bars = tuple(
            _bar(
                symbol=symbol,
                session=session,
                close=starting_prices[symbol] + steps[symbol] * index,
            )
            for index, session in enumerate(sessions)
        )
        streams[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
            dataset_hash=_DATASET_HASH,
            source_path=tmp_path / "index.json",
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id="kis.paper.private.daily.backfill-v1.common-panel",
        dataset_hash=_DATASET_HASH,
        index_hash="sha256:" + "b" * 64,
        index_path=tmp_path / "index.json",
        source_root=tmp_path,
        adjustment_mode="MODP=0_unadjusted",
        bars_by_symbol=MappingProxyType(streams),
        common_sessions=sessions,
        raw_price_limitations=("MODP=0_unadjusted",),
    )


def _bar(*, symbol: str, session: date, close: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )

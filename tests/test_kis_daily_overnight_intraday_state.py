from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import (
    KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
    KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    KisPaperPrivateDailyCatalog,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_daily_overnight_intraday_state as state
from thericher_v2.research import kis_daily_overnight_intraday_state_validation as validator
from thericher_v2.research import kis_daily_relative_regime_control as relative


@pytest.fixture(scope="module")
def source_input(tmp_path_factory: pytest.TempPathFactory) -> relative.KisDailyRelativeRegimeInput:
    return relative.build_kis_daily_relative_regime_input(
        _catalog(tmp_path_factory.mktemp("overnight-intraday-source"))
    )


def test_directional_count_rule_is_causal_and_not_a_cumulative_product(
    source_input: relative.KisDailyRelativeRegimeInput,
) -> None:
    intraday_dominant = _window(intraday_positive_count=11)
    overnight_dominant = _window(intraday_positive_count=9)

    assert intraday_dominant[0].close == intraday_dominant[-1].close
    assert overnight_dominant[0].close == overnight_dominant[-1].close
    assert state.overnight_intraday_positive_count_should_enter(
        completed_bars=intraday_dominant
    ) is True
    assert state.overnight_intraday_positive_count_should_enter(
        completed_bars=overnight_dominant
    ) is False

    bars = source_input.validation_catalog.bars_by_symbol["QQQ"].bars
    index = 20
    baseline = state.overnight_intraday_positive_count_should_enter(
        completed_bars=bars[index - 20 : index + 1]
    )
    future = list(bars)
    future[index + 1] = _bar(
        symbol="QQQ",
        start=bars[index + 1].start_ts,
        open_value=Decimal("999"),
        close_value=Decimal("1000"),
    )
    assert state.overnight_intraday_positive_count_should_enter(
        completed_bars=tuple(future[index - 20 : index + 1])
    ) is baseline
    with pytest.raises(ValueError, match="exactly 21"):
        state.overnight_intraday_positive_count_should_enter(completed_bars=intraday_dominant[1:])


def test_cpu_smoke_and_independent_validator_stay_offline_and_external(
    source_input: relative.KisDailyRelativeRegimeInput,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    _deny_external_access(monkeypatch)

    smoke = state.run_kis_daily_overnight_intraday_state_cpu_smoke(
        source_input,
        artifact_root=artifact_root,
        run_label="cpu-smoke",
        repository_root=repository_root,
    )
    summary = json.loads(smoke.summary_path.read_text(encoding="utf-8"))
    assert summary["outcome"] == "operational_smoke"
    assert summary["review"]["claude_verdict"] == "unsupported"
    assert summary["scope"]["gpu_used"] is False
    assert summary["scope"]["full_validation_eligible"] is False
    for metrics in summary["validation"]["metrics_by_symbol"].values():
        for metric in metrics.values():
            assert metric["local_paper_fill_count"] == metric["trade_count"] * 2
            assert metric["fill_source"] == "local_paper"
            assert metric["final_position"] == "0"

    monkeypatch.setattr(
        validator,
        "load_current_kis_daily_relative_regime_input",
        lambda **_kwargs: source_input,
    )
    _precommit_hash, _summary_hash, receipt_path = (
        validator.validate_current_kis_daily_overnight_intraday_state_cpu_smoke(
            cache_root=tmp_path / "cache",
            artifact_root=artifact_root,
            precommit_path=smoke.precommit_path,
            summary_path=smoke.summary_path,
            run_label="validation",
            repository_root=repository_root,
        )
    )
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "attested"
    assert not list(artifact_root.rglob("*.jsonl"))
    assert not list(artifact_root.rglob("*.sqlite"))
    assert not list(artifact_root.rglob("*.pt"))
    for document in artifact_root.rglob("*.json"):
        _assert_no_raw_fields(json.loads(document.read_text(encoding="utf-8")))

    with pytest.raises(ValueError, match="outside Git"):
        state.run_kis_daily_overnight_intraday_state_cpu_smoke(
            source_input,
            artifact_root=repository_root / "artifacts",
            run_label="inside-git",
            repository_root=repository_root,
        )


def _window(*, intraday_positive_count: int) -> tuple[Bar, ...]:
    start = datetime(2000, 1, 1, tzinfo=UTC)
    bars = [_bar(symbol="QQQ", start=start, open_value=Decimal("99"), close_value=Decimal("100"))]
    prior_close = Decimal("100")
    for index in range(1, 21):
        positive = index <= intraday_positive_count
        open_value = prior_close - Decimal("1") if positive else prior_close + Decimal("1")
        bars.append(
            _bar(
                symbol="QQQ",
                start=start + timedelta(days=index),
                open_value=open_value,
                close_value=prior_close,
            )
        )
    return tuple(bars)


def _catalog(root: Path) -> KisPaperPrivateDailyCatalog:
    sessions = tuple(
        (datetime(2000, 1, 1, tzinfo=UTC) + timedelta(days=index)).date()
        for index in range(relative.KIS_DAILY_RELATIVE_REGIME_TOTAL_SESSIONS)
    )
    index_path = root / "private-source-index.json"
    streams = {}
    for symbol, base in (("QQQ", Decimal("100")), ("SPY", Decimal("200"))):
        bars = tuple(
            _bar(
                symbol=symbol,
                start=datetime(session.year, session.month, session.day, tzinfo=UTC),
                open_value=base + Decimal(index) / Decimal("10"),
                close_value=(
                    base
                    + Decimal(index) / Decimal("10")
                    + (Decimal("0.07") if index % 3 else Decimal("-0.04"))
                ),
            )
            for index, session in enumerate(sessions)
        )
        streams[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
            dataset_hash=_sha256("fixture-dataset"),
            source_path=index_path,
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id=KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
        dataset_hash=_sha256("fixture-dataset"),
        index_hash=_sha256("fixture-index"),
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_PRIVATE_DAILY_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(streams),
        common_sessions=sessions,
        raw_price_limitations=("MODP=0_unadjusted", "corporate_action_semantics_not_qualified"),
    )


def _bar(*, symbol: str, start: datetime, open_value: Decimal, close_value: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start,
        open=open_value,
        high=max(open_value, close_value) + Decimal("1"),
        low=min(open_value, close_value) - Decimal("1"),
        close=close_value,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("overnight/intraday smoke must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_raw_fields(value: object) -> None:
    forbidden = {"open", "high", "low", "close", "volume", "price", "return"}
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_fields(nested)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()

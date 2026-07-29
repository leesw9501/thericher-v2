from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_d1_adjustment_audit as audit
from thericher_v2.data.kis_paper_daily_history_panel import (
    KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_HISTORY_PANEL_ID,
    KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS,
    KisPaperDailyHistoryPanel,
    KisPaperDailyHistoryPanelTarget,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader

_EXTRA_PAIR = (date(2019, 1, 2), date(2019, 1, 3))


def test_writes_an_external_categorical_census_without_external_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repository.mkdir()
    artifact_root.mkdir()
    _deny_external_access(monkeypatch)
    panel = _panel(tmp_path / "panel")

    result = audit.build_kis_d1_discontinuity_census_receipt(
        artifact_root=artifact_root,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        panel_loader=lambda _root, _repo: panel,
    )
    repeated = audit.build_kis_d1_discontinuity_census_receipt(
        artifact_root=artifact_root,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        panel_loader=lambda _root, _repo: panel,
    )

    assert result.census.status == "no_unexplained_large_discontinuity"
    assert result.census.model_eligible is False
    assert result.census.paper_trading_eligible is False
    assert result.receipt_path.is_relative_to(artifact_root)
    assert not result.receipt_path.is_relative_to(repository)
    assert repeated.receipt_path == result.receipt_path
    assert repeated.receipt_sha256 == result.receipt_sha256

    text = result.receipt_path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["artifact_policy"]["network_accessed"] is False
    assert payload["artifact_policy"]["credentials_accessed"] is False
    assert payload["artifact_policy"]["per_pair_records_persisted"] is False
    assert payload["census"]["scope"]["label_eligible"] is False
    assert "2020-08-31" not in text
    assert "2019-01-03" not in text
    assert str(tmp_path) not in text
    _assert_no_raw_keys(payload)


def test_excludes_known_fixed_splits_and_reports_an_unexplained_signature(tmp_path: Path) -> None:
    zero = audit.assess_kis_d1_discontinuity_census(_panel(tmp_path / "zero"))
    observed = audit.assess_kis_d1_discontinuity_census(
        _panel(tmp_path / "observed", unexplained_symbols={"META"})
    )

    assert zero.status == "no_unexplained_large_discontinuity"
    assert zero.results_by_symbol["AAPL"].known_fixed_split_signature_count == 1
    assert zero.results_by_symbol["NVDA"].known_fixed_split_signature_count == 2
    assert all(
        result.unexplained_large_discontinuity_count == 0
        for result in zero.results_by_symbol.values()
    )
    assert observed.status == "unexplained_large_discontinuity_observed"
    assert observed.results_by_symbol["META"].status == "unexplained_large_discontinuity_observed"
    assert observed.results_by_symbol["META"].unexplained_large_discontinuity_count == 1


def test_an_incomplete_pair_is_fail_closed_to_inconclusive(tmp_path: Path) -> None:
    panel = _panel(tmp_path / "panel")
    streams = dict(panel.bars_by_symbol)
    meta_bars = list(panel.bars_by_symbol["META"].bars)
    meta_bars[0] = replace(meta_bars[0], complete=False)
    streams["META"] = SimpleNamespace(bars=tuple(meta_bars))
    incomplete_panel = SimpleNamespace(
        dataset_id=panel.dataset_id,
        dataset_hash=panel.dataset_hash,
        index_hash=panel.index_hash,
        adjustment_mode=panel.adjustment_mode,
        bars_by_symbol=MappingProxyType(streams),
    )

    result = audit.assess_kis_d1_discontinuity_census(incomplete_panel)

    assert result.status == "inconclusive"
    assert result.results_by_symbol["META"].status == "inconclusive_pair"


def test_rejects_git_local_artifacts_before_reading_sources(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        audit.build_kis_d1_discontinuity_census_receipt(
            artifact_root=repository,
            market_data_root=tmp_path / "market-data",
            repo_root=repository,
            panel_loader=lambda _root, _repo: (_ for _ in ()).throw(
                AssertionError("must not load")
            ),
        )


def test_census_contract_reuses_the_five_fixed_pairs() -> None:
    assert audit.SPLIT_SIGNATURE_THRESHOLD_MULTIPLIER == Decimal("3")
    assert audit._census_contract_sha256().startswith("sha256:")  # noqa: SLF001
    assert len(audit._known_fixed_split_pairs()) == 5  # noqa: SLF001
    assert audit._is_known_fixed_split(  # noqa: SLF001
        "AAPL", date(2020, 8, 28), date(2020, 8, 31)
    )
    assert not audit._is_known_fixed_split(  # noqa: SLF001
        "META", date(2020, 8, 28), date(2020, 8, 31)
    )


def _panel(
    root: Path,
    *,
    unexplained_symbols: set[str] | None = None,
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    unexplained = unexplained_symbols or set()
    sessions = tuple(
        sorted(
            {
                _EXTRA_PAIR[0],
                _EXTRA_PAIR[1],
                *(
                    session
                    for pairs in audit._SPLIT_SESSION_PAIRS.values()  # noqa: SLF001
                    for pair in pairs
                    for session in pair
                ),
            }
        )
    )
    dataset_hash = "sha256:" + "a" * 64
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        split_after_sessions = {
            after
            for _before, after in audit._SPLIT_SESSION_PAIRS.get(symbol, ())  # noqa: SLF001
        }
        if symbol in unexplained:
            split_after_sessions.add(_EXTRA_PAIR[1])
        values: dict[date, Decimal] = {}
        level = Decimal("100")
        for session in sessions:
            if session in split_after_sessions:
                level /= Decimal("4")
            values[session] = level
        bars = tuple(
            _bar(symbol=symbol, session=session, close=values[session])
            for session in sessions
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=index_path,
            bars=bars,
        )
        targets_by_key[f"{symbol}/NAS"] = KisPaperDailyHistoryPanelTarget(
            target_key=f"{symbol}/NAS",
            state="complete",
            last_reason=None,
            chunk_count=1,
            bar_count=len(bars),
            coverage_start_bucket=_quarter(bars[0].start_ts.date()),
            coverage_end_bucket=_quarter(bars[-1].start_ts.date()),
        )
    return KisPaperDailyHistoryPanel(
        dataset_id=KIS_PAPER_DAILY_HISTORY_PANEL_ID,
        dataset_hash=dataset_hash,
        index_hash="sha256:" + "b" * 64,
        index_path=index_path,
        source_root=root,
        adjustment_mode=KIS_PAPER_DAILY_HISTORY_PANEL_ADJUSTMENT_MODE,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        targets_by_key=MappingProxyType(targets_by_key),
        common_sessions=sessions,
    )


def _bar(*, symbol: str, session: date, close: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _quarter(value: date) -> str:
    return f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("KIS D1 discontinuity census must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_raw_keys(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "timestamp",
        "timestamps",
        "date",
        "dates",
        "eventdate",
        "eventdates",
        "sourcepath",
        "workdir",
        "statesqlite",
        "eventjsonl",
        "eventlog",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_keys(nested)

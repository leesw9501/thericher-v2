from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

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


def test_writes_an_external_categorical_receipt_without_external_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repository.mkdir()
    artifact_root.mkdir()
    _deny_external_access(monkeypatch)
    panel = _panel(tmp_path / "panel")

    result = audit.build_kis_d1_adjustment_audit_receipt(
        artifact_root=artifact_root,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        panel_loader=lambda _root, _repo: panel,
    )
    repeated = audit.build_kis_d1_adjustment_audit_receipt(
        artifact_root=artifact_root,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        panel_loader=lambda _root, _repo: panel,
    )

    assert result.audit.status == "consistent_with_declared_unadjusted"
    assert result.audit.model_eligible is False
    assert result.audit.paper_trading_eligible is False
    assert result.receipt_path.is_relative_to(artifact_root)
    assert not result.receipt_path.is_relative_to(repository)
    assert repeated.receipt_path == result.receipt_path
    assert repeated.receipt_sha256 == result.receipt_sha256

    text = result.receipt_path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["artifact_policy"]["network_accessed"] is False
    assert payload["artifact_policy"]["credentials_accessed"] is False
    assert payload["audit"]["scope"]["model_eligible"] is False
    assert payload["audit"]["scope"]["paper_trading_eligible"] is False
    assert "2020-08-31" not in text
    assert "2024-06-10" not in text
    assert str(tmp_path) not in text
    _assert_no_raw_keys(payload)


def test_classifies_a_complete_missing_signature_as_falsified(tmp_path: Path) -> None:
    panel = _panel(tmp_path / "panel", absent_signatures={"AMZN"})

    result = audit.assess_kis_d1_adjustment_audit(panel)

    assert result.status == "declared_unadjusted_falsified"
    assert result.results_by_symbol["AMZN"].status == "signature_absent"
    assert result.results_by_symbol["AMZN"].complete_event_count == 1
    assert result.results_by_symbol["AMZN"].signature_event_count == 0


def test_classifies_a_missing_required_pair_as_inconclusive(tmp_path: Path) -> None:
    panel = _panel(tmp_path / "panel", omitted_pairs={("NVDA", 1)})

    result = audit.assess_kis_d1_adjustment_audit(panel)

    assert result.status == "inconclusive"
    assert result.results_by_symbol["NVDA"].status == "inconclusive_pair"
    assert result.results_by_symbol["NVDA"].complete_event_count == 1
    assert result.results_by_symbol["NVDA"].signature_event_count == 1


def test_rejects_git_local_artifacts_before_reading_sources(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        audit.build_kis_d1_adjustment_audit_receipt(
            artifact_root=repository,
            market_data_root=tmp_path / "market-data",
            repo_root=repository,
            panel_loader=lambda _root, _repo: (_ for _ in ()).throw(
                AssertionError("must not load")
            ),
        )


def test_fixed_contract_requires_all_five_public_pairs() -> None:
    assert audit.SPLIT_SIGNATURE_THRESHOLD_MULTIPLIER == Decimal("3")
    assert audit._contract_sha256().startswith("sha256:")  # noqa: SLF001
    assert sum(len(pairs) for pairs in audit._SPLIT_SESSION_PAIRS.values()) == 5  # noqa: SLF001


def _panel(
    root: Path,
    *,
    absent_signatures: set[str] | None = None,
    omitted_pairs: set[tuple[str, int]] | None = None,
) -> KisPaperDailyHistoryPanel:
    root.mkdir(parents=True)
    index_path = root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    absent = absent_signatures or set()
    omitted = omitted_pairs or set()
    sessions = tuple(
        sorted(
            {
                session
                for pairs in audit._SPLIT_SESSION_PAIRS.values()  # noqa: SLF001
                for pair in pairs
                for session in pair
            }
        )
    )
    dataset_hash = "sha256:" + "a" * 64
    bars_by_symbol: dict[str, object] = {}
    targets_by_key: dict[str, KisPaperDailyHistoryPanelTarget] = {}
    for symbol in KIS_PAPER_DAILY_HISTORY_PANEL_SYMBOLS:
        values = {session: Decimal("100") for session in sessions}
        omitted_sessions: set[date] = set()
        for index, (before, after) in enumerate(audit._SPLIT_SESSION_PAIRS.get(symbol, ())):  # noqa: SLF001
            values[before] = Decimal("100")
            values[after] = Decimal("100") if symbol in absent else Decimal("25")
            if (symbol, index) in omitted:
                omitted_sessions.add(after)
        bars = tuple(
            _bar(symbol=symbol, session=session, close=values[session])
            for session in sessions
            if session not in omitted_sessions
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
    common_sessions = tuple(
        sorted(
            set.intersection(
                *(
                    set(bar.start_ts.date() for bar in stream.bars)
                    for stream in bars_by_symbol.values()
                )
            )
        )
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
        common_sessions=common_sessions,
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
        raise AssertionError("KIS D1 adjustment audit must stay offline and credential-free")

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

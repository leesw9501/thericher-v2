from __future__ import annotations

import json
import socket
import urllib.request
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_intraday_runtime_window import (
    KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE,
    select_kis_paper_intraday_runtime_window,
)
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research.kis_paper_prospective_loop import run_kis_paper_prospective_loop


def test_ready_window_keeps_a_retrospective_replay_as_a_scoped_no_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog(91)
    window = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=catalog.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )

    result = run_kis_paper_prospective_loop(
        window,
        local_paper_state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
    )

    assert result.window.status == "ready"
    assert result.capability_authorization == "provisional"
    assert result.proposal.action == "enter"
    assert result.receipt.decision_class == "enter"
    assert result.local_paper_replay is not None
    assert result.proposal.decided_at == window.as_of
    assert window.replay_bar is not None
    assert result.proposal.decided_at > window.replay_bar.start_ts
    assert result.local_paper_replay.status == "no_intent"
    assert result.local_paper_replay.reason == "decision_after_replay_bar"
    assert result.local_paper_replay.fill_source is None
    payload = result.safe_payload()
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["mode"] == "offline_local_paper"
    assert payload["baseline"]["capability_authorization"] == "provisional"
    assert payload["window"]["freshness"]["lag_category"] == "within_budget"
    assert "101.00" not in rendered
    assert "price" not in rendered
    assert "credential" not in rendered


def test_missing_window_creates_a_replayable_unavailable_receipt_without_local_order(
    tmp_path: Path,
) -> None:
    catalog = _catalog(45)
    window = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=catalog.bars[-1].end_ts,
        max_age=timedelta(minutes=2),
    )

    result = run_kis_paper_prospective_loop(
        window,
        local_paper_state_root=tmp_path / "runtime",
        repo_root=tmp_path / "repo",
    )

    assert result.window.status == "missing"
    assert result.capability_authorization == "not_evaluated"
    assert result.proposal.action == "abstain"
    assert result.receipt.decision_class == "abstain"
    assert result.receipt.reason_class == "input_unavailable"
    assert result.local_paper_replay is None
    assert not (tmp_path / "runtime" / "qqq-prospective-local-paper-v1.jsonl").exists()


def test_runtime_loop_rejects_a_ready_window_with_a_wider_than_runtime_budget(
    tmp_path: Path,
) -> None:
    catalog = _catalog(91)
    window = select_kis_paper_intraday_runtime_window(
        catalog,
        as_of=catalog.bars[-1].end_ts,
        max_age=KIS_PAPER_INTRADAY_RUNTIME_MAX_AGE + timedelta(microseconds=1),
    )

    assert window.status == "ready"
    with pytest.raises(ValueError, match="exceeds the fixed baseline freshness budget"):
        run_kis_paper_prospective_loop(
            window,
            local_paper_state_root=tmp_path / "runtime",
            repo_root=tmp_path / "repo",
        )
    assert not (tmp_path / "runtime" / "qqq-prospective-local-paper-v1.jsonl").exists()


def _catalog(count: int) -> CatalogedBars:
    session = us_equity_2026_session(date(2026, 7, 20))
    assert session is not None
    bars = tuple(
        _bar(index=index, start_ts=session.window.open_ts + timedelta(minutes=index))
        for index in range(count)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("unit-index.json"),
        bars=bars,
    )


def _bar(*, index: int, start_ts) -> Bar:
    open_price = Decimal("100") + Decimal(index) / Decimal("100")
    close = open_price + Decimal("0.005")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=open_price,
        high=close + Decimal("0.01"),
        low=open_price - Decimal("0.01"),
        close=close,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prospective loop must stay offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

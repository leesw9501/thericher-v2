from __future__ import annotations

import json
import socket
import urllib.request
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import kis_intraday_consensus_replay as consensus_replay

_SESSION_DATES = (
    date(2026, 6, 23),
    date(2026, 6, 24),
    date(2026, 6, 25),
    date(2026, 6, 26),
    date(2026, 6, 29),
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
    date(2026, 7, 8),
    date(2026, 7, 9),
    date(2026, 7, 10),
    date(2026, 7, 13),
    date(2026, 7, 14),
    date(2026, 7, 15),
    date(2026, 7, 16),
    date(2026, 7, 17),
    date(2026, 7, 20),
    date(2026, 7, 21),
)


def test_consensus_replay_is_external_aggregate_only_and_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_network(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"

    run = consensus_replay.run_kis_intraday_consensus_replay(
        _catalog(),
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=Path.cwd(),
    )

    assert run.status == "complete"
    assert run.session_count == 20
    assert run.consensus.round_trip_count == 10
    assert run.consensus.fill_count == 20
    assert run.always_long.round_trip_count == 20
    assert run.always_long.fill_count == 40
    assert run.abstention_count == 0
    assert dict(run.decision_action_counts) == {"enter": 10, "hold": 10}
    assert run.all_fills_local_paper is True
    assert run.all_terminal_flat is True
    assert run.precommit_path.is_relative_to(artifact_root)
    assert run.summary_path.is_relative_to(artifact_root)

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_replay"
    assert precommit["contract"]["post_outcome_tuning_allowed"] is False
    assert summary["mode"] == "offline_local_cache_local_paper_only"
    assert summary["replay_proof"] == {
        "all_fills_local_paper": True,
        "all_terminal_flat": True,
        "event_replay_digest": run.replay_digest,
        "local_paper_source": "local_paper",
        "raw_fill_events_retained": False,
    }
    assert summary["artifact_policy"] == {
        "broker_called": False,
        "checkpoint_written": False,
        "credential_read": False,
        "network_called": False,
        "raw_fill_events_retained": False,
        "raw_market_data_written": False,
        "repo_storage_allowed": False,
        "root": str(artifact_root.resolve()),
    }
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert "KIS_PAPER_" not in serialized
    assert '"open"' not in serialized
    assert '"close"' not in serialized
    assert '"price"' not in serialized


def test_decision_ignores_post_as_of_bars_even_when_terminal_outcome_changes() -> None:
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts and bar.end_ts <= session.window.close_ts
    )
    as_of = session.window.open_ts + consensus_replay.KIS_INTRADAY_CONSENSUS_DECISION_OFFSET
    changed = tuple(
        _shift_bar(bar, Decimal("50")) if bar.start_ts >= as_of else bar for bar in bars
    )

    original = consensus_replay._build_session_decision(
        bars,
        session=session.window,
        source_dataset_hash=catalog.dataset_hash,
        session_date=_SESSION_DATES[0],
    )
    shifted = consensus_replay._build_session_decision(
        changed,
        session=session.window,
        source_dataset_hash=catalog.dataset_hash,
        session_date=_SESSION_DATES[0],
    )

    assert original.proposal_action == "enter"
    assert shifted.proposal_action == original.proposal_action
    assert shifted.proposal_reason == original.proposal_reason
    assert shifted.receipt == original.receipt
    assert shifted.bridge == original.bridge


def test_consensus_replay_rejects_an_artifact_root_inside_the_workspace() -> None:
    with pytest.raises(ValueError, match="outside the Git workspace"):
        consensus_replay.run_kis_intraday_consensus_replay(
            _catalog(),
            session_dates=_SESSION_DATES,
            artifact_root=Path.cwd(),
            run_label="inside-repo-r1",
            repo_root=Path.cwd(),
        )


def _catalog() -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        direction = Decimal("1") if session_index % 2 == 0 else Decimal("-1")
        for minute in range(390):
            opened = (
                Decimal("100")
                + Decimal(session_index)
                + direction * Decimal(minute) / Decimal("100")
            )
            closed = opened + direction * Decimal("0.02")
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=max(opened, closed) + Decimal("0.01"),
                    low=min(opened, closed) - Decimal("0.01"),
                    close=closed,
                    volume=Decimal("1000") + Decimal(minute) + Decimal(session_index),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.consensus-replay-unit-v1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("D:/market_data/unit-kis-consensus-replay-index.json"),
        bars=tuple(bars),
    )


def _shift_bar(bar: Bar, shift: Decimal) -> Bar:
    return replace(
        bar,
        open=bar.open + shift,
        high=bar.high + shift,
        low=bar.low + shift,
        close=bar.close + shift,
    )


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("consensus replay must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.execution.paper_decision_bridge import PaperDecisionBridgeResult
from thericher_v2.research import kis_intraday_donchian_replay as donchian_replay

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


def test_donchian_replay_is_external_aggregate_only_and_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"

    run = donchian_replay.run_kis_intraday_session_reset_donchian_replay(
        _catalog(),
        artifact_root=artifact_root,
        run_label="unit-r1",
        repo_root=Path.cwd(),
    )

    assert run.status == "complete"
    assert run.session_count == 20
    assert run.donchian.decision_count == 20 * 388
    assert run.donchian.eligible_enter_count == 20
    assert run.donchian.eligible_exit_count == 0
    assert run.donchian.forced_terminal_exit_count == 20
    assert run.donchian.local_paper_fill_count == 40
    assert run.donchian.all_fills_local_paper is True
    assert run.donchian.all_terminal_flat is True
    assert run.always_long_control.local_paper_fill_count == 40
    assert run.always_long_control.all_fills_local_paper is True
    assert run.always_long_control.all_terminal_flat is True
    assert run.flat_control.local_paper_fill_count == 0

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_replay"
    assert precommit["contract_hash"].startswith("sha256:")
    assert precommit["contract"]["source"]["selection"] == (
        "first_20_complete_regular_sessions_ascending"
    )
    assert precommit["contract"]["execution"]["terminal_exit"] == (
        "predeclared_penultimate_bar_decision_final_bar_open_fill"
    )
    assert precommit["contract"]["limits"] == {
        "decision_time_availability": "not_observed",
        "gpu_eligible": False,
        "paper_input_allowed": False,
        "performance_metrics_retained": False,
        "post_outcome_tuning_allowed": False,
        "promotion_allowed": False,
    }
    assert summary["mechanics"]["all_fills_local_paper"] is True
    assert summary["mechanics"]["all_terminal_flat"] is True
    assert summary["artifact_policy"]["credential_read"] is False
    assert summary["artifact_policy"]["network_called"] is False
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert "after_cost_pnl" not in serialized
    assert '"price"' not in serialized
    assert '"open"' not in serialized
    assert "KIS_PAPER_" not in serialized


def test_selector_uses_first_twenty_complete_regular_sessions_in_catalog_order() -> None:
    extra_date = date(2026, 7, 22)
    catalog = _catalog((*_SESSION_DATES, extra_date))

    selected = donchian_replay.select_first_complete_kis_intraday_regular_session_dates(catalog)

    assert selected == _SESSION_DATES


def test_causal_input_manifest_ignores_later_and_other_session_bars() -> None:
    session = _session_bars(_SESSION_DATES[0])
    later_session = _session_bars(_SESSION_DATES[1])
    as_of = session[20].end_ts

    original = donchian_replay._causal_input_manifest_ref(session, as_of=as_of)
    changed = donchian_replay._causal_input_manifest_ref(
        (
            *session[:21],
            replace(session[21], high=Decimal("250"), close=Decimal("250")),
            *session[22:],
            *later_session,
        ),
        as_of=as_of,
    )

    assert changed == original


def test_eligible_donchian_proposal_cannot_silently_lose_its_local_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_bars(_SESSION_DATES[0])

    def no_intent(*_args: object, **_kwargs: object) -> PaperDecisionBridgeResult:
        return PaperDecisionBridgeResult(
            route="local_paper",
            receipt_ref="sha256:" + "b" * 64,
            status="no_intent",
            reason="target_binding_mismatch",
        )

    monkeypatch.setattr(donchian_replay, "prepare_local_paper_intent", no_intent)

    with pytest.raises(RuntimeError, match="eligible Donchian proposal"):
        donchian_replay._run_donchian_local_paper(
            session,
            session=_session_window(_SESSION_DATES[0]),
            contract_hash="sha256:" + "c" * 64,
        )


def test_replay_rejects_a_repo_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)

    with pytest.raises(ValueError, match="artifact root must stay outside"):
        donchian_replay.run_kis_intraday_session_reset_donchian_replay(
            _catalog(),
            artifact_root=Path.cwd() / "generated-donchian-artifacts",
            run_label="unit-reject-root",
            repo_root=Path.cwd(),
        )


def _catalog(session_dates: tuple[date, ...] = _SESSION_DATES) -> CatalogedBars:
    bars = tuple(
        bar
        for session_date in session_dates
        for bar in _session_bars(session_date)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.test",
        dataset_hash="sha256:" + "a" * 64,
        source_path=Path("C:/external/kis-index.json"),
        bars=bars,
    )


def _session_bars(session_date: date) -> tuple[Bar, ...]:
    open_ts = datetime(session_date.year, session_date.month, session_date.day, 13, 30, tzinfo=UTC)
    return tuple(_bar(open_ts, minute) for minute in range(390))


def _session_window(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None
    return session.window


def _bar(open_ts: datetime, minute: int) -> Bar:
    close = Decimal("100")
    high = Decimal("101")
    low = Decimal("99")
    if minute == 20:
        close = Decimal("102")
        high = Decimal("102")
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=open_ts + timedelta(minutes=minute),
        open=Decimal("100"),
        high=high,
        low=low,
        close=close,
        volume=Decimal("1"),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)
    monkeypatch.setattr(os, "environ", {})

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
from thericher_v2.research import kis_intraday_ema_replay as ema_replay

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


def test_ema_replay_is_external_aggregate_only_and_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    calls: list[tuple[object, Bar, Bar, object]] = []
    original_submit_and_fill = ema_replay.LocalPaperBroker.submit_and_fill_next_bar

    def record_submit_and_fill(
        self: ema_replay.LocalPaperBroker,
        intent: object,
        *,
        signal_bar: Bar,
        execution_bar: Bar,
    ) -> object:
        result = original_submit_and_fill(
            self,
            intent,  # type: ignore[arg-type]
            signal_bar=signal_bar,
            execution_bar=execution_bar,
        )
        calls.append((intent, signal_bar, execution_bar, result.fill))
        return result

    monkeypatch.setattr(
        ema_replay.LocalPaperBroker,
        "submit_and_fill_next_bar",
        record_submit_and_fill,
    )
    artifact_root = tmp_path / "model-artifacts"

    run = ema_replay.run_kis_intraday_session_reset_ema_replay(
        _catalog("entry"),
        artifact_root=artifact_root,
        run_label="unit-r1",
    )

    assert run.status == "complete"
    assert run.session_count == 20
    assert run.ema.decision_count == 20 * 388
    assert run.ema.warmup_abstain_count == 20 * 29
    assert run.ema.ready_hold_count == 20 * 358
    assert run.ema.eligible_enter_count == 20
    assert run.ema.eligible_exit_count == 0
    assert run.ema.forced_terminal_exit_count == 20
    assert run.ema.local_paper_fill_count == 40
    assert run.ema.replay_event_count >= run.ema.local_paper_fill_count
    assert run.ema.all_fills_local_paper is True
    assert run.ema.all_terminal_flat is True
    assert calls
    assert all(execution.start_ts == signal.end_ts for _, signal, execution, _ in calls)
    assert any(execution.open != signal.close for _, signal, execution, _ in calls)
    for intent, _, execution, fill in calls:
        assert fill is not None
        adjustment = Decimal("1.0002") if intent.side == "buy" else Decimal("0.9998")
        assert fill.filled_at == execution.start_ts
        assert fill.price == (execution.open * adjustment).quantize(Decimal("0.0001"))

    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_replay"
    assert precommit["contract_hash"].startswith("sha256:")
    assert precommit["contract"]["source"]["selection"] == (
        "first_20_complete_regular_sessions_ascending_within_2026_scope"
    )
    assert precommit["contract"]["source"]["calendar_scope"] == "2026"
    assert precommit["contract"]["source"]["complete_session_predicate"] == (
        "verified_contiguous_regular_390_m1_bars"
    )
    assert precommit["contract"]["rule"] == {
        "fast_period": 15,
        "id": "session-reset-ema-state-v1",
        "seed_policy": "within_session_sma_seed_then_decimal_ema_v1",
        "session_local_warmup_bars": 30,
        "slow_period": 30,
        "tolerance": "0.00015",
    }
    assert precommit["contract"]["execution"]["entry_exit"] == "next_completed_1m_bar_open"
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
    assert summary["mechanics"]["rule_activated"] is True
    assert summary["artifact_policy"]["credential_read"] is False
    assert summary["artifact_policy"]["network_called"] is False
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert "after_cost_pnl" not in serialized
    assert '"price"' not in serialized
    assert '"close"' not in serialized
    assert "KIS_PAPER_" not in serialized


def test_ema_replay_records_rule_exit_without_terminal_flatten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)

    mechanics = ema_replay._run_ema_local_paper(
        _session_bars(_SESSION_DATES[0], "entry_exit"),
        session=_session_window(_SESSION_DATES[0]),
        contract_hash="sha256:" + "d" * 64,
    )

    assert mechanics.eligible_enter_count == 1
    assert mechanics.eligible_exit_count == 1
    assert mechanics.forced_terminal_exit_count == 0
    assert mechanics.local_paper_fill_count == 2
    assert mechanics.all_terminal_flat is True


def test_ema_replay_marks_no_activation_without_carrying_warmup_between_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)

    run = ema_replay.run_kis_intraday_session_reset_ema_replay(
        _catalog("flat"),
        artifact_root=tmp_path / "model-artifacts",
        run_label="unit-no-activation",
    )

    assert run.status == "no_rule_activation"
    assert run.ema.decision_count == 20 * 388
    assert run.ema.warmup_abstain_count == 20 * 29
    assert run.ema.ready_hold_count == 20 * 359
    assert run.ema.eligible_enter_count == 0
    assert run.ema.eligible_exit_count == 0
    assert run.ema.local_paper_fill_count == 0
    assert run.ema.all_terminal_flat is True
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "no_rule_activation"
    assert summary["mechanics"]["rule_activated"] is False
    assert "does not establish replay conformance" in summary["claim"]


def test_ema_replay_writes_an_input_unavailable_record_for_incomplete_coverage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)

    run = ema_replay.run_kis_intraday_session_reset_ema_replay(
        _catalog_with_missing_minute(),
        artifact_root=tmp_path / "model-artifacts",
        run_label="unit-insufficient",
    )

    assert run.status == "input_unavailable"
    assert run.session_count == 0
    assert run.input_unavailable_reason == "insufficient_complete_regular_sessions"
    assert run.ema.decision_count == 0
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert summary["input_unavailable_reason"] == "insufficient_complete_regular_sessions"
    assert summary["mechanics"]["local_paper_fill_count"] == 0
    assert summary["artifact_policy"]["network_called"] is False


def test_ema_replay_rejects_a_non_kis_nas_catalog_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)

    run = ema_replay.run_kis_intraday_session_reset_ema_replay(
        _catalog("entry", dataset_id="sample.qqq.us.m1.v1"),
        artifact_root=tmp_path / "model-artifacts",
        run_label="unit-wrong-source",
    )

    assert run.status == "input_unavailable"
    assert run.input_unavailable_reason == "invalid_catalog"


def test_ema_replay_contract_hash_pins_the_catalog_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    first = _contract_hash(_catalog("entry", dataset_hash="sha256:" + "a" * 64))
    second = _contract_hash(_catalog("entry", dataset_hash="sha256:" + "b" * 64))

    assert first != second


def test_ema_causal_input_manifest_ignores_later_and_other_session_bars() -> None:
    session = _session_bars(_SESSION_DATES[0], "entry")
    later_session = _session_bars(_SESSION_DATES[1], "entry")
    as_of = session[30].end_ts

    original = ema_replay._causal_input_manifest_ref(session, as_of=as_of)
    changed = ema_replay._causal_input_manifest_ref(
        (
            *session[:31],
            replace(session[31], high=Decimal("250"), close=Decimal("250")),
            *session[32:],
            *later_session,
        ),
        as_of=as_of,
    )

    assert changed == original


def test_ema_replay_keeps_earlier_receipts_and_intents_stable_when_future_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    session = _session_bars(_SESSION_DATES[0], "entry")
    changed = (
        *session[:31],
        replace(
            session[31],
            open=Decimal("250"),
            high=Decimal("250"),
            low=Decimal("102"),
            close=Decimal("250"),
        ),
        *session[32:],
    )
    cutoff = session[30].end_ts
    original_prepare = ema_replay.prepare_local_paper_intent

    def capture_prefix(bars: tuple[Bar, ...]) -> list[tuple[str, str, str, str | None]]:
        captured: list[tuple[str, str, str, str | None]] = []

        def prepare(receipt: object, **kwargs: object) -> object:
            result = original_prepare(receipt, **kwargs)  # type: ignore[arg-type]
            if receipt.decided_at <= cutoff:
                client_order_id = (
                    result.local_paper_intent.client_order_id
                    if result.local_paper_intent is not None
                    else None
                )
                captured.append(
                    (receipt.decision_id, receipt.proposal_ref, result.status, client_order_id)
                )
            return result

        monkeypatch.setattr(ema_replay, "prepare_local_paper_intent", prepare)
        ema_replay._run_ema_local_paper(
            bars,
            session=_session_window(_SESSION_DATES[0]),
            contract_hash="sha256:" + "e" * 64,
        )
        return captured

    assert capture_prefix(session) == capture_prefix(changed)


def test_eligible_ema_proposal_cannot_silently_lose_its_local_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_bars(_SESSION_DATES[0], "entry")

    def no_intent(*_args: object, **_kwargs: object) -> PaperDecisionBridgeResult:
        return PaperDecisionBridgeResult(
            route="local_paper",
            receipt_ref="sha256:" + "b" * 64,
            status="no_intent",
            reason="target_binding_mismatch",
        )

    monkeypatch.setattr(ema_replay, "prepare_local_paper_intent", no_intent)

    with pytest.raises(RuntimeError, match="eligible EMA proposal"):
        ema_replay._run_ema_local_paper(
            session,
            session=_session_window(_SESSION_DATES[0]),
            contract_hash="sha256:" + "c" * 64,
        )


def test_ema_replay_rejects_the_actual_repo_artifact_root_when_cwd_is_external(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="artifact root must stay outside"):
        ema_replay.run_kis_intraday_session_reset_ema_replay(
            _catalog("entry"),
            artifact_root=ema_replay._REPOSITORY_ROOT / "generated-ema-artifacts",
            run_label="unit-reject-root",
        )


def _catalog(
    mode: str,
    *,
    session_dates: tuple[date, ...] = _SESSION_DATES,
    dataset_hash: str = "sha256:" + "a" * 64,
    dataset_id: str = "kis.paper.private.intraday.qqq.nas.m1.test",
) -> CatalogedBars:
    bars = tuple(
        bar
        for session_date in session_dates
        for bar in _session_bars(session_date, mode)
    )
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        source_path=Path("C:/external/kis-index.json"),
        bars=bars,
    )


def _catalog_with_missing_minute() -> CatalogedBars:
    catalog = _catalog("entry")
    missing_start = _session_window(_SESSION_DATES[4]).open_ts + timedelta(minutes=100)
    bars = tuple(bar for bar in catalog.bars if bar.start_ts != missing_start)
    return _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        source_path=catalog.source_path,
        bars=bars,
    )


def _session_bars(session_date: date, mode: str) -> tuple[Bar, ...]:
    open_ts = datetime(session_date.year, session_date.month, session_date.day, 13, 30, tzinfo=UTC)
    return tuple(_bar(open_ts, minute, mode) for minute in range(390))


def _session_window(session_date: date):
    session = us_equity_2026_session(session_date)
    assert session is not None
    return session.window


def _contract_hash(catalog: CatalogedBars) -> str:
    session_dates = ema_replay.select_first_complete_kis_intraday_regular_session_dates(catalog)
    plan = ema_replay.build_kis_intraday_cpu_campaign_plan(
        catalog,
        session_dates=session_dates,
        campaign_id=ema_replay.KIS_INTRADAY_EMA_REPLAY_ID,
    )
    return "sha256:" + ema_replay._sha256_json(ema_replay._contract_payload(plan))


def _bar(open_ts: datetime, minute: int, mode: str) -> Bar:
    if mode not in {"entry", "entry_exit", "flat"}:
        raise ValueError("unsupported fixture mode")
    close = Decimal("100")
    if mode == "entry" and minute >= 30:
        close = Decimal("102")
    elif mode == "entry_exit":
        if minute == 30:
            close = Decimal("102")
        elif minute >= 31:
            close = Decimal("90")
    opening = Decimal("101") if mode == "entry" and minute == 31 else close
    return Bar(
        symbol="QQQ",
        market="US",
        timeframe=Timeframe.M1,
        start_ts=open_ts + timedelta(minutes=minute),
        open=opening,
        high=max(opening, close),
        low=min(opening, close),
        close=close,
        volume=Decimal("1"),
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr(os, "getenv", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(urllib.request, "urlopen", deny)

from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.models.current_source_opportunity_eligibility import CurrentSourceMetadata
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
_V2_REPLAY_DIGEST = "sha256:8855ec22147b9218fc83ac60eaf3cb17dd2a70b38bc46b7568aec5033ad383d1"


def test_consensus_replay_is_external_aggregate_only_and_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_network(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"

    run = consensus_replay.run_kis_intraday_consensus_replay(
        _catalog(),
        session_dates=_SESSION_DATES,
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
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
    assert run.replay_digest == _V2_REPLAY_DIGEST
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
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )
    shifted = consensus_replay._build_session_decision(
        changed,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )

    assert original.proposal_action == "enter"
    assert shifted.proposal_action == original.proposal_action
    assert shifted.proposal_reason == original.proposal_reason
    assert shifted.receipt == original.receipt
    assert shifted.bridge == original.bridge


def test_ready_decision_uses_one_causal_window_for_adapter_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts and bar.end_ts <= session.window.close_ts
    )
    adapter_windows: list[object] = []
    policy_windows: list[object | None] = []
    original_adapter = consensus_replay.build_multitimeframe_momentum_evidence_from_causal_window
    original_policy = consensus_replay.propose_target_exposure

    def capture_adapter(*args: object, **kwargs: object) -> object:
        adapter_windows.append(args[0])
        return original_adapter(*args, **kwargs)

    def capture_policy(*args: object, **kwargs: object) -> object:
        policy_windows.append(kwargs.get("causal_window"))
        return original_policy(*args, **kwargs)

    monkeypatch.setattr(
        consensus_replay,
        "build_multitimeframe_momentum_evidence_from_causal_window",
        capture_adapter,
    )
    monkeypatch.setattr(consensus_replay, "propose_target_exposure", capture_policy)

    decision = consensus_replay._build_session_decision(
        bars,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )

    assert decision.proposal_action == "enter"
    assert len(adapter_windows) == len(policy_windows) == 1
    assert policy_windows[0] is adapter_windows[0]


def test_bound_decision_ignores_post_as_of_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    adapter_windows: list[object] = []
    policy_windows: list[object | None] = []
    original_adapter = consensus_replay.build_multitimeframe_momentum_evidence_from_causal_window
    original_policy = consensus_replay.propose_target_exposure

    def capture_adapter(*args: object, **kwargs: object) -> object:
        adapter_windows.append(args[0])
        return original_adapter(*args, **kwargs)

    def capture_policy(*args: object, **kwargs: object) -> object:
        policy_windows.append(kwargs.get("causal_window"))
        return original_policy(*args, **kwargs)

    monkeypatch.setattr(
        consensus_replay,
        "build_multitimeframe_momentum_evidence_from_causal_window",
        capture_adapter,
    )
    monkeypatch.setattr(consensus_replay, "propose_target_exposure", capture_policy)

    original = consensus_replay._build_session_decision(
        bars,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )
    shifted = consensus_replay._build_session_decision(
        changed,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )

    assert shifted.proposal_action == original.proposal_action
    assert shifted.proposal_reason == original.proposal_reason
    assert shifted.receipt == original.receipt
    assert shifted.bridge == original.bridge
    assert len(adapter_windows) == len(policy_windows) == 2
    assert policy_windows[0] is adapter_windows[0]
    assert policy_windows[1] is adapter_windows[1]
    assert adapter_windows[0] == adapter_windows[1]


def test_malformed_source_never_calls_adapter_or_binds_a_policy_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts
        and bar.end_ts <= session.window.close_ts
        and bar.start_ts != session.window.open_ts
    )
    adapter_calls: list[object] = []
    policy_windows: list[object | None] = []
    original_policy = consensus_replay.propose_target_exposure

    def fail_if_adapter_called(*args: object, **kwargs: object) -> object:
        adapter_calls.append(args)
        raise AssertionError("malformed source must not construct direct causal evidence")

    def capture_policy(*args: object, **kwargs: object) -> object:
        policy_windows.append(kwargs.get("causal_window"))
        return original_policy(*args, **kwargs)

    monkeypatch.setattr(
        consensus_replay,
        "build_multitimeframe_momentum_evidence_from_causal_window",
        fail_if_adapter_called,
    )
    monkeypatch.setattr(consensus_replay, "propose_target_exposure", capture_policy)

    decision = consensus_replay._build_session_decision(
        bars,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )

    assert decision.proposal_reason == "opportunity_non_contiguous"
    assert decision.bridge.status == "no_intent"
    assert adapter_calls == []
    assert policy_windows == [None]


def test_ready_direct_evidence_disagreement_fails_before_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts and bar.end_ts <= session.window.close_ts
    )
    original_adapter = consensus_replay.build_multitimeframe_momentum_evidence_from_causal_window

    def mismatched_adapter(*args: object, **kwargs: object) -> object:
        evidence = original_adapter(*args, **kwargs)
        return replace(evidence, reason="forced_direct_evidence_mismatch")

    def fail_if_policy_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unbound evidence must not reach the target policy")

    monkeypatch.setattr(
        consensus_replay,
        "build_multitimeframe_momentum_evidence_from_causal_window",
        mismatched_adapter,
    )
    monkeypatch.setattr(consensus_replay, "propose_target_exposure", fail_if_policy_called)

    with pytest.raises(RuntimeError, match="must match its causal-window input"):
        consensus_replay._build_session_decision(
            bars,
            session=session.window,
            session_date=_SESSION_DATES[0],
            upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
        )


def test_incomplete_current_source_abstains_even_when_as_of_model_evidence_is_ready() -> None:
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    as_of = session.window.open_ts + consensus_replay.KIS_INTRADAY_CONSENSUS_DECISION_OFFSET
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts and bar.end_ts <= session.window.close_ts
    )
    evidence = consensus_replay.build_multitimeframe_momentum_evidence(
        bars,
        session=session.window,
        config=consensus_replay.frozen_multitimeframe_momentum_config(),
        as_of=as_of,
    )

    def incomplete_source_metadata(*args: object, **kwargs: object) -> CurrentSourceMetadata:
        source = consensus_replay._current_source_metadata(*args, **kwargs)
        return replace(source, complete=False)

    decision = consensus_replay._build_session_decision(
        bars,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
        source_metadata_factory=incomplete_source_metadata,
    )

    assert evidence.input_status == "ready"
    assert decision.proposal_action == "abstain"
    assert decision.proposal_reason == "opportunity_incomplete"
    assert decision.bridge.status == "no_intent"


def test_ineligible_upstream_candidate_abstains_without_a_local_paper_intent() -> None:
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts and bar.end_ts <= session.window.close_ts
    )

    def ineligible_candidate(**kwargs: object) -> object:
        candidate = consensus_replay.predeclared_consensus_replay_candidate(**kwargs)
        return replace(candidate, eligible=False)

    decision = consensus_replay._build_session_decision(
        bars,
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=ineligible_candidate,
    )

    assert decision.proposal_action == "abstain"
    assert decision.proposal_reason == "opportunity_ineligible"
    assert decision.bridge.status == "no_intent"
    assert decision.bridge.local_paper_intent is None


@pytest.mark.parametrize(
    ("mutate", "reason"),
    (
        (
            lambda bars, session: tuple(
                bar for bar in bars if bar.start_ts != session.open_ts
            ),
            "opportunity_non_contiguous",
        ),
        (
            lambda bars, _session: (*bars, bars[0]),
            "opportunity_duplicate",
        ),
        (
            lambda bars, session: tuple(
                bar
                for bar in bars
                if bar.start_ts
                != session.open_ts
                + consensus_replay.KIS_INTRADAY_CONSENSUS_DECISION_OFFSET
                - Timeframe.M1.duration
            ),
            "opportunity_non_contiguous",
        ),
    ),
)
def test_current_source_gaps_or_duplicates_abstain_without_a_local_paper_intent(
    mutate: object,
    reason: str,
) -> None:
    assert callable(mutate)
    catalog = _catalog()
    session = us_equity_2026_session(_SESSION_DATES[0])
    assert session is not None
    bars = tuple(
        bar
        for bar in catalog.bars
        if bar.start_ts >= session.window.open_ts and bar.end_ts <= session.window.close_ts
    )
    decision = consensus_replay._build_session_decision(
        mutate(bars, session.window),
        session=session.window,
        session_date=_SESSION_DATES[0],
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )

    assert decision.proposal_action == "abstain"
    assert decision.proposal_reason == reason
    assert decision.bridge.status == "no_intent"
    assert decision.bridge.local_paper_intent is None


def test_stale_current_source_can_only_add_abstentions_to_the_frozen_replay() -> None:
    plan = consensus_replay.build_kis_intraday_cpu_campaign_plan(
        _catalog(),
        session_dates=_SESSION_DATES,
        campaign_id=consensus_replay.KIS_INTRADAY_CONSENSUS_REPLAY_ID,
    )
    baseline = consensus_replay._replay_plan_sessions(
        plan,
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
    )

    def stale_source_metadata(*args: object, **kwargs: object) -> CurrentSourceMetadata:
        source = consensus_replay._current_source_metadata(*args, **kwargs)
        return replace(
            source,
            observed_at=source.observed_at - timedelta(minutes=1),
            valid_until=source.observed_at - timedelta(microseconds=1),
        )

    downgraded = consensus_replay._replay_plan_sessions(
        plan,
        upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
        source_metadata_factory=stale_source_metadata,
    )

    assert consensus_replay.consensus_session_replay_digest(baseline) == _V2_REPLAY_DIGEST
    assert tuple(item.proposal_action for item in downgraded) == ("abstain",) * 20
    assert sum(item.consensus.fill_count for item in downgraded) == 0
    assert sum(item.consensus.fill_count for item in downgraded) <= sum(
        item.consensus.fill_count for item in baseline
    )
    assert all(item.consensus.all_fills_local_paper for item in downgraded)
    assert all(item.consensus.terminal_flat for item in downgraded)


def test_consensus_replay_rejects_an_artifact_root_inside_the_workspace() -> None:
    with pytest.raises(ValueError, match="outside the Git workspace"):
        consensus_replay.run_kis_intraday_consensus_replay(
            _catalog(),
            session_dates=_SESSION_DATES,
            upstream_candidate_factory=consensus_replay.predeclared_consensus_replay_candidate,
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


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("consensus decision must not access external state")

    monkeypatch.setattr(os, "getenv", fail_external)
    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "read_text", fail_external)

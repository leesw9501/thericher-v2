from __future__ import annotations

import json
import socket
import urllib.request
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.data.us_equity_session import us_equity_2026_session
from thericher_v2.research import kis_intraday_consensus_replay as consensus_replay
from thericher_v2.research import kis_intraday_consensus_selection_null as selection_null

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


def test_selection_null_reproduces_the_baseline_before_exact_equal_count_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_network(monkeypatch)
    catalog = _catalog()
    artifact_root = tmp_path / "model-artifacts"
    baseline = consensus_replay.run_kis_intraday_consensus_replay(
        catalog,
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        run_label="baseline-r1",
        repo_root=Path.cwd(),
    )

    run = selection_null.run_kis_intraday_consensus_selection_null(
        catalog,
        session_dates=_SESSION_DATES,
        baseline_summary_path=baseline.summary_path,
        artifact_root=artifact_root,
        run_label="null-r1",
        repo_root=Path.cwd(),
    )

    assert run.status == "complete"
    assert run.classification == "selection_unqualified"
    assert run.selected_session_count == 2
    assert run.null_method == "exact_combinations"
    assert run.null_subset_count == 190
    assert Decimal("0") <= run.one_sided_p_value <= Decimal("1")
    precommit = json.loads(run.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert precommit["status"] == "frozen_before_diagnostic"
    assert precommit["null_contract"]["selected_session_count"] == 2
    assert summary["baseline"]["replay_digest_match"] is True
    assert summary["equal_count_null"]["subset_count"] == 190
    assert summary["selection"]["selected_session_count"] == 2
    assert summary["replay_proof"] == {
        "all_fills_local_paper": True,
        "all_terminal_flat": True,
        "local_paper_source": "local_paper",
        "raw_fill_events_retained": False,
    }
    assert summary["artifact_policy"] == {
        "broker_called": False,
        "checkpoint_written": False,
        "credential_read": False,
        "gpu_used": False,
        "network_called": False,
        "raw_fill_events_retained": False,
        "raw_market_data_written": False,
        "repo_storage_allowed": False,
        "root": str(artifact_root.resolve()),
    }
    serialized = run.summary_path.read_text(encoding="utf-8")
    assert '"open"' not in serialized
    assert '"close"' not in serialized
    assert '"price"' not in serialized
    assert "client_order_id" not in serialized
    assert "KIS_PAPER_" not in serialized


def test_selection_null_rejects_a_baseline_replay_digest_mismatch(tmp_path: Path) -> None:
    catalog = _catalog()
    artifact_root = tmp_path / "model-artifacts"
    baseline = consensus_replay.run_kis_intraday_consensus_replay(
        catalog,
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        run_label="baseline-r2",
        repo_root=Path.cwd(),
    )
    payload = json.loads(baseline.summary_path.read_text(encoding="utf-8"))
    payload["replay_proof"]["event_replay_digest"] = "sha256:" + "f" * 64
    mismatch_root = tmp_path / "mismatch"
    mismatch_root.mkdir()
    mismatch_summary = mismatch_root / "summary.json"
    mismatch_precommit = mismatch_root / "precommit.json"
    mismatch_summary.write_text(json.dumps(payload), encoding="utf-8")
    mismatch_precommit.write_text(
        baseline.precommit_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="immutable baseline replay digest"):
        selection_null.run_kis_intraday_consensus_selection_null(
            catalog,
            session_dates=_SESSION_DATES,
            baseline_summary_path=mismatch_summary,
            artifact_root=artifact_root,
            run_label="null-mismatch-r1",
            repo_root=Path.cwd(),
        )


def test_session_replay_projection_is_source_safe_and_matches_baseline_digest(
    tmp_path: Path,
) -> None:
    catalog = _catalog()
    baseline = consensus_replay.run_kis_intraday_consensus_replay(
        catalog,
        session_dates=_SESSION_DATES,
        artifact_root=tmp_path / "model-artifacts",
        run_label="baseline-r3",
        repo_root=Path.cwd(),
    )

    outcomes = consensus_replay.replay_frozen_consensus_sessions(
        catalog,
        session_dates=_SESSION_DATES,
    )

    assert len(outcomes) == 20
    assert all(outcome.consensus.terminal_flat for outcome in outcomes)
    assert all(outcome.always_long.all_fills_local_paper for outcome in outcomes)
    assert consensus_replay.consensus_session_replay_digest(outcomes) == baseline.replay_digest


def _catalog() -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        direction = Decimal("1") if session_index < 2 else Decimal("-1")
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
                    volume=Decimal("1000") + Decimal(session_index) + Decimal(minute),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.selection-null-unit-v1",
        dataset_hash="sha256:" + "b" * 64,
        source_path=Path("D:/market_data/unit-kis-consensus-selection-null-index.json"),
        bars=tuple(bars),
    )


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("selection null must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

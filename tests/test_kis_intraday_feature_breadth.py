from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.data as market_data
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    CatalogedBars,
    SessionWindow,
    prepare_kis_paper_intraday_feature_input,
    us_equity_2026_session,
)
from thericher_v2.data.kis_paper_intraday import (
    select_complete_kis_paper_private_intraday_sessions,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.kis_intraday_feature_breadth import (
    KIS_INTRADAY_FEATURE_CANDIDATES,
    KIS_INTRADAY_FEATURE_M1_BARS,
    KIS_INTRADAY_FEATURE_M5_BARS,
    KIS_INTRADAY_FEATURE_M10_BARS,
    KIS_INTRADAY_FEATURE_NAMES,
    KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION,
    build_kis_intraday_feature_contract,
    build_kis_intraday_feature_dataset,
    fit_kis_intraday_regularized_linear,
    run_kis_intraday_feature_breadth,
)
from thericher_v2.state import EventStore


@dataclass(frozen=True)
class _ExpectedFeatureInput:
    cataloged_bars: CatalogedBars
    session_dates: tuple[date, ...]
    session_windows: tuple[SessionWindow, ...]


def test_feature_contract_uses_public_data_input_and_exact_10_1_9_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _deny_external_access(monkeypatch)
    catalog = _catalog()
    prepared = prepare_kis_paper_intraday_feature_input(
        catalog,
        session_dates=_SESSION_DATES,
    )

    contract = build_kis_intraday_feature_contract(catalog, session_dates=_SESSION_DATES)
    dataset = build_kis_intraday_feature_dataset(contract)

    assert contract.input_hash == prepared.input_hash
    assert contract.feature_names == KIS_INTRADAY_FEATURE_NAMES
    assert contract.campaign_plan.development_session_dates == _SESSION_DATES[:10]
    assert contract.purge_session_date == _SESSION_DATES[10]
    assert contract.validation_session_dates == _SESSION_DATES[11:]
    assert len(dataset.development_samples) == 10 * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
    assert contract.candidate_comparison_session_dates == _SESSION_DATES[11:16]
    assert contract.sealed_confirmation_session_dates == _SESSION_DATES[16:]
    assert len(dataset.candidate_comparison_samples) == 5 * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
    assert dataset.purge_sample_count == 0

    for sample in (*dataset.development_samples, *dataset.candidate_comparison_samples):
        assert sample.m1_bar_count == KIS_INTRADAY_FEATURE_M1_BARS
        assert sample.m5_bar_count == KIS_INTRADAY_FEATURE_M5_BARS
        assert sample.m10_bar_count == KIS_INTRADAY_FEATURE_M10_BARS
        assert sample.history_start >= sample.session_window.open_ts
        assert sample.entry_start == sample.decision_end
        assert sample.exit_start == sample.entry_start + Timeframe.M1.duration
        assert sample.exit_start + Timeframe.M1.duration <= sample.session_window.close_ts


def test_contract_accepts_the_data_agent_public_input_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _catalog()

    def prepare(
        source: CatalogedBars,
        *,
        session_dates: tuple[date, ...],
    ) -> _ExpectedFeatureInput:
        selected = select_complete_kis_paper_private_intraday_sessions(
            source,
            session_dates=session_dates,
        )
        return _ExpectedFeatureInput(
            cataloged_bars=selected,
            session_dates=session_dates,
            session_windows=tuple(_session_window(item) for item in session_dates),
        )

    monkeypatch.setattr(
        market_data,
        "prepare_kis_paper_intraday_feature_input",
        prepare,
    )
    contract = build_kis_intraday_feature_contract(catalog, session_dates=_SESSION_DATES)

    assert contract.campaign_plan.cataloged_bars.dataset_hash.startswith("sha256:")
    assert contract.input_hash.startswith("sha256:")


def test_regularized_linear_training_does_not_materialize_confirmation_data() -> None:
    baseline_catalog = _catalog()
    mutated_catalog = _catalog(sealed_confirmation_price_shift=Decimal("30"))

    baseline_dataset = build_kis_intraday_feature_dataset(
        build_kis_intraday_feature_contract(baseline_catalog, session_dates=_SESSION_DATES)
    )
    mutated_dataset = build_kis_intraday_feature_dataset(
        build_kis_intraday_feature_contract(mutated_catalog, session_dates=_SESSION_DATES)
    )

    assert baseline_dataset.development_samples == mutated_dataset.development_samples
    assert (
        baseline_dataset.candidate_comparison_samples
        == mutated_dataset.candidate_comparison_samples
    )
    assert fit_kis_intraday_regularized_linear(baseline_dataset) == (
        fit_kis_intraday_regularized_linear(mutated_dataset)
    )


def test_feature_breadth_is_offline_comparison_only_and_replayable_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    artifact_root = tmp_path / "model-artifacts"
    run = run_kis_intraday_feature_breadth(
        _catalog(),
        session_dates=_SESSION_DATES,
        artifact_root=artifact_root,
        work_root=tmp_path / "work",
        run_label="unit-r1",
        repo_root=Path.cwd(),
    )

    assert (
        tuple(item.candidate_id for item in run.candidate_runs)
        == KIS_INTRADAY_FEATURE_CANDIDATES
    )
    assert all(item.replay.fill_source == LOCAL_PAPER_SOURCE for item in run.candidate_runs)
    assert all(
        item.replay.replay_evidence.fill_source == LOCAL_PAPER_SOURCE
        for item in run.candidate_runs
    )
    assert all(item.replay.result.campaign_phase == "validation" for item in run.candidate_runs)
    assert all(
        item.replay.result.decisions_seen == 5 * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION
        for item in run.candidate_runs
    )
    assert run.candidate_runs[0].replay.result.trades == ()
    assert run.candidate_runs[1].replay.result.trades
    assert run.summary_path.is_relative_to(artifact_root)
    assert run.contract_path.is_relative_to(artifact_root)
    assert run.model_path.is_relative_to(artifact_root)

    momentum_store = EventStore(
        run.candidate_runs[1].replay.replay_evidence.state_sqlite_path,
        run.candidate_runs[1].replay.replay_evidence.event_jsonl_path,
    )
    fills = [event for event in momentum_store.iter_events() if event.event_type == "fill"]
    assert fills
    assert all(event.payload["source"] == LOCAL_PAPER_SOURCE for event in fills)

    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    assert summary["mode"] == "offline_local_paper"
    assert summary["sample_counts"] == {
        "development": 10 * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION,
        "purge": 0,
        "candidate_comparison": 5 * KIS_INTRADAY_FEATURE_SAMPLES_PER_SESSION,
        "sealed_confirmation": 0,
    }
    assert summary["sealed_confirmation"]["materialized"] is False
    assert summary["sealed_confirmation"]["selection_allowed"] is False
    assert all(item["fill_source"] == LOCAL_PAPER_SOURCE for item in summary["candidates"])
    assert "KIS_PAPER_" not in run.summary_path.read_text(encoding="utf-8")


def test_feature_contract_rejects_a_missing_completed_minute() -> None:
    source = _catalog(missing_session_date=_SESSION_DATES[0], missing_minute=100)

    with pytest.raises(ValueError, match="incomplete"):
        build_kis_intraday_feature_contract(source, session_dates=_SESSION_DATES)


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS intraday feature breadth must not open the network")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS intraday feature breadth must not read credentials")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_environment)


def _catalog(
    *,
    missing_session_date: date | None = None,
    missing_minute: int | None = None,
    sealed_confirmation_price_shift: Decimal = Decimal("0"),
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(_SESSION_DATES):
        session = us_equity_2026_session(session_date)
        assert session is not None
        shift = sealed_confirmation_price_shift if session_index >= 16 else Decimal("0")
        for minute in range(390):
            if session_date == missing_session_date and minute == missing_minute:
                continue
            opened = (
                Decimal("100")
                + Decimal(session_index)
                + Decimal(minute) / Decimal("100")
                + shift
            )
            closed = opened + Decimal("0.02")
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * minute,
                    open=opened,
                    high=closed + Decimal("0.01"),
                    low=opened - Decimal("0.01"),
                    close=closed,
                    volume=Decimal("1000") + Decimal(minute),
                    complete=True,
                )
            )
    hash_character = "b" if sealed_confirmation_price_shift else "a"
    return _cataloged_bars_from_verified_loader(
        dataset_id="kis.paper.private.intraday.qqq.nas.m1.unit-v1",
        dataset_hash="sha256:" + hash_character * 64,
        source_path=Path(f"D:/market_data/unit-kis-index-{hash_character}.json"),
        bars=tuple(bars),
    )


def _session_window(session_date: date) -> SessionWindow:
    session = us_equity_2026_session(session_date)
    assert session is not None
    return session.window


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

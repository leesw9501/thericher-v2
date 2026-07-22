from __future__ import annotations

import json
import socket
import sqlite3
import urllib.request
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import thericher_v2.research.kis_intraday_campaign as kis_intraday_campaign
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import CatalogedBars, us_equity_2026_session
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.execution import EmergencyStore
from thericher_v2.research.campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from thericher_v2.research.kis_intraday_campaign import (
    KIS_INTRADAY_FIRST_SIGNAL_OFFSET,
    KIS_INTRADAY_LAST_SIGNAL_OFFSET,
    build_kis_intraday_cpu_campaign_plan,
    run_kis_intraday_cpu_naive_baselines,
)
from thericher_v2.research.validation import (
    ValidationConfig,
    _NaiveBaselineModel,
    run_local_paper_validation,
    run_naive_cpu_baseline,
)
from thericher_v2.state import EventStore


def test_plan_freezes_exact_10_1_9_geometry_and_signal_offsets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_dates = _regular_session_dates()
    catalog = _catalog(tmp_path, session_dates)
    calls = _install_selector(monkeypatch, selected=catalog)

    plan = build_kis_intraday_cpu_campaign_plan(catalog, session_dates=session_dates)

    assert calls == [session_dates]
    assert plan.development_session_dates == session_dates[:10]
    assert plan.purge_session_date == session_dates[10]
    assert plan.validation_session_dates == session_dates[11:]
    assert plan.campaign.catalog.ranking_eligible is False
    assert plan.campaign.sealed_holdout is None
    assert plan.campaign.evidence_use == "development"
    assert plan.campaign.naive_baselines == (
        "flat",
        "always_long",
        "previous_bar_direction",
    )

    development_starts = plan.eligible_signal_starts("development")
    validation_starts = plan.eligible_signal_starts("validation")
    assert len(development_starts) == 10 * 299
    assert len(validation_starts) == 9 * 299
    first_window = plan.phase_session_windows("development")[0]
    first_allowed = first_window.open_ts + Timeframe.M1.duration * KIS_INTRADAY_FIRST_SIGNAL_OFFSET
    last_allowed = first_window.open_ts + Timeframe.M1.duration * KIS_INTRADAY_LAST_SIGNAL_OFFSET
    first_disallowed = first_window.open_ts + Timeframe.M1.duration * (
        KIS_INTRADAY_LAST_SIGNAL_OFFSET + 1
    )
    assert first_allowed in development_starts
    assert last_allowed in development_starts
    assert first_disallowed not in development_starts
    assert plan.phase_session_windows("development") == plan.session_windows[:10]
    assert plan.phase_session_windows("validation") == plan.session_windows[11:]

    with pytest.raises(ValueError, match="exactly 20"):
        build_kis_intraday_cpu_campaign_plan(catalog, session_dates=session_dates[:-1])


def test_plan_rejects_missing_intraday_minute_even_when_session_start_is_declared(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_dates = _regular_session_dates()
    complete_catalog = _catalog(tmp_path, session_dates)
    missing_catalog = _catalog(
        tmp_path,
        session_dates,
        excluded={(session_dates[4], 141)},
    )
    _install_selector(monkeypatch, selected=missing_catalog)

    with pytest.raises(ValueError, match="complete contiguous minutes"):
        build_kis_intraday_cpu_campaign_plan(complete_catalog, session_dates=session_dates)


def test_campaign_rejects_a_target_that_would_cross_a_declared_session_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_dates = _regular_session_dates()
    catalog = _catalog(tmp_path, session_dates)
    _install_selector(monkeypatch, selected=catalog)
    plan = build_kis_intraday_cpu_campaign_plan(catalog, session_dates=session_dates)
    first_session = plan.phase_session_windows("development")[0]

    with pytest.raises(ValueError, match="cannot cross a declared session boundary"):
        run_naive_cpu_baseline(
            plan.cataloged_bars,
            campaign=plan.campaign,
            artifact_root=tmp_path / "artifacts",
            work_dir=tmp_path / "work",
            repo_root=Path.cwd(),
            phase="development",
            fold_id="fold-1",
            baseline_id="always_long",
            eligible_signal_starts=frozenset(
                {first_session.open_ts + Timeframe.M1.duration * 388}
            ),
            allowed_session_windows=plan.phase_session_windows("development"),
        )


def test_campaign_baseline_is_offline_credential_free_and_replayable_local_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("KIS intraday CPU campaign must stay offline")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.lower().startswith(".env"):
            raise AssertionError("KIS intraday CPU campaign must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    session_dates = _regular_session_dates()
    catalog = _catalog(tmp_path, session_dates)
    _install_selector(monkeypatch, selected=catalog)
    plan = build_kis_intraday_cpu_campaign_plan(catalog, session_dates=session_dates)

    run = run_naive_cpu_baseline(
        plan.cataloged_bars,
        campaign=plan.campaign,
        artifact_root=tmp_path / "artifacts",
        work_dir=tmp_path / "work",
        repo_root=Path.cwd(),
        phase="validation",
        fold_id="fold-1",
        baseline_id="always_long",
        eligible_signal_starts=plan.eligible_signal_starts("validation"),
        allowed_session_windows=plan.phase_session_windows("validation"),
    )

    assert run.fill_source == "local_paper"
    assert run.replay_evidence.fill_source == "local_paper"
    assert run.result.final_position == 0
    assert run.artifact_path.is_relative_to(tmp_path / "artifacts")
    fills = [
        event
        for event in EventStore(
            run.replay_evidence.state_sqlite_path,
            run.replay_evidence.event_jsonl_path,
        ).iter_events()
        if event.event_type == "fill"
    ]
    assert fills
    assert all(event.payload["source"] == "local_paper" for event in fills)


def test_runner_dispatches_all_naive_paths_in_fixed_phase_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session_dates = _regular_session_dates()
    catalog = _catalog(tmp_path, session_dates, rising=False)
    _install_selector(monkeypatch, selected=catalog)
    plan = build_kis_intraday_cpu_campaign_plan(catalog, session_dates=session_dates)
    result = run_kis_intraday_cpu_naive_baselines(
        plan,
        artifact_root=tmp_path / "artifacts",
        work_root=tmp_path / "work",
        repo_root=Path.cwd(),
        run_label="attempt-a",
    )

    assert [
        (item.phase, item.baseline.baseline_id) for item in result.baseline_runs
    ] == [
        ("development", "flat"),
        ("development", "always_long"),
        ("development", "previous_bar_direction"),
        ("validation", "flat"),
        ("validation", "always_long"),
        ("validation", "previous_bar_direction"),
    ]
    assert len(result.baseline_runs) == 6
    assert all(item.baseline.fill_source == "local_paper" for item in result.baseline_runs)
    assert all(item.baseline.result.final_position == 0 for item in result.baseline_runs)
    assert all(item.baseline.result.run_id.endswith("-attempt-a") for item in result.baseline_runs)
    assert [
        item.baseline.result.decisions_seen for item in result.baseline_runs
    ] == [
        10 * 299,
        10 * 299,
        10 * 299,
        9 * 299,
        9 * 299,
        9 * 299,
    ]
    always_long_runs = [
        item.baseline for item in result.baseline_runs if item.baseline.baseline_id == "always_long"
    ]
    assert all(run.result.trades for run in always_long_runs)
    assert all(
        run.replay_evidence.event_jsonl_path.is_relative_to(tmp_path / "work")
        for run in always_long_runs
    )


def test_declared_session_windows_do_not_hide_an_intrasession_gap(tmp_path: Path) -> None:
    catalog = _contiguous_catalog(tmp_path)
    broken = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        source_path=catalog.source_path,
        bars=tuple(bar for index, bar in enumerate(catalog.bars) if index != 8),
    )
    session = us_equity_2026_session(date(2026, 1, 2))
    assert session is not None

    with pytest.raises(ValueError, match="contiguous"):
        run_local_paper_validation(
            broken,
            event_store=EventStore(tmp_path / "gap.sqlite", tmp_path / "gap.jsonl"),
            emergency_store=EmergencyStore(tmp_path / "gap-emergency.json"),
            model=_NaiveBaselineModel(baseline_id="always_long", deterministic_seed=71),
            config=ValidationConfig(run_id="unit-intrasession-gap"),
            allowed_session_windows=(session.window,),
        )


def test_attempt_labels_create_distinct_immutable_campaign_artifacts(tmp_path: Path) -> None:
    catalog = _contiguous_catalog(tmp_path)
    campaign = _small_campaign(catalog)
    eligible = frozenset({catalog.bars[1].start_ts, catalog.bars[4].start_ts})
    artifact_root = tmp_path / "artifacts"

    first = run_naive_cpu_baseline(
        catalog,
        campaign=campaign,
        artifact_root=artifact_root,
        work_dir=tmp_path / "attempt-a-work",
        repo_root=Path.cwd(),
        phase="development",
        fold_id="fold-1",
        baseline_id="always_long",
        run_label="attempt-a",
        eligible_signal_starts=eligible,
    )
    second = run_naive_cpu_baseline(
        catalog,
        campaign=campaign,
        artifact_root=artifact_root,
        work_dir=tmp_path / "attempt-b-work",
        repo_root=Path.cwd(),
        phase="development",
        fold_id="fold-1",
        baseline_id="always_long",
        run_label="attempt-b",
        eligible_signal_starts=eligible,
    )

    assert first.result.run_id.endswith("-attempt-a")
    assert second.result.run_id.endswith("-attempt-b")
    assert first.artifact_path != second.artifact_path
    assert first.artifact_path.exists()
    assert second.artifact_path.exists()


def test_fast_campaign_replay_matches_ordinary_local_paper_and_rebuilds_sqlite(
    tmp_path: Path,
) -> None:
    catalog = _contiguous_catalog(tmp_path)
    campaign = _small_campaign(catalog)
    eligible = frozenset({catalog.bars[1].start_ts, catalog.bars[4].start_ts})
    run_id = "unit-campaign-development-fold-1-always_long"

    ordinary_store = EventStore(tmp_path / "ordinary.sqlite", tmp_path / "ordinary.jsonl")
    ordinary = run_local_paper_validation(
        catalog,
        event_store=ordinary_store,
        emergency_store=EmergencyStore(tmp_path / "ordinary-emergency.json"),
        model=_NaiveBaselineModel(baseline_id="always_long", deterministic_seed=71),
        config=ValidationConfig(
            run_id=run_id,
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("2"),
        ),
        campaign=campaign,
        phase="development",
        fold_id="fold-1",
        baseline_id="always_long",
        eligible_signal_starts=eligible,
    )
    fast = run_naive_cpu_baseline(
        catalog,
        campaign=campaign,
        artifact_root=tmp_path / "artifacts",
        work_dir=tmp_path / "fast-work",
        repo_root=Path.cwd(),
        phase="development",
        fold_id="fold-1",
        baseline_id="always_long",
        eligible_signal_starts=eligible,
    )

    ordinary_records = [event.to_record() for event in ordinary_store.iter_events()]
    fast_store = EventStore(
        fast.replay_evidence.state_sqlite_path,
        fast.replay_evidence.event_jsonl_path,
    )
    fast_records = [event.to_record() for event in fast_store.iter_events()]
    assert fast.result == ordinary
    assert fast_records == ordinary_records
    assert fast_store.replay() == ordinary_store.replay()

    with sqlite3.connect(fast.replay_evidence.state_sqlite_path) as connection:
        sqlite_events = connection.execute(
            "select seq, event_type, created_at, payload_json from events order by seq"
        ).fetchall()
        sqlite_positions = connection.execute(
            "select market, symbol, quantity from positions order by market, symbol"
        ).fetchall()
    assert sqlite_events == [
        (
            event["seq"],
            event["event_type"],
            event["created_at"],
            json.dumps(event["payload"], sort_keys=True),
        )
        for event in fast_records
    ]
    expected_positions = [
        (market, symbol, str(quantity))
        for (market, symbol), quantity in sorted(fast_store.replay().positions.items())
    ]
    assert sqlite_positions == expected_positions


def _install_selector(
    monkeypatch: pytest.MonkeyPatch,
    *,
    selected: CatalogedBars,
) -> list[tuple[date, ...]]:
    calls: list[tuple[date, ...]] = []

    def select_complete(
        catalog: CatalogedBars,
        *,
        session_dates: tuple[date, ...],
    ) -> CatalogedBars:
        assert isinstance(catalog, CatalogedBars)
        calls.append(session_dates)
        return selected

    monkeypatch.setattr(
        kis_intraday_campaign,
        "select_complete_kis_paper_private_intraday_sessions",
        select_complete,
    )
    return calls


def _regular_session_dates() -> tuple[date, ...]:
    selected: list[date] = []
    candidate = date(2026, 1, 2)
    while len(selected) < 20:
        session = us_equity_2026_session(candidate)
        if session is not None and session.kind == "regular":
            selected.append(candidate)
        candidate += timedelta(days=1)
    return tuple(selected)


def _catalog(
    tmp_path: Path,
    session_dates: tuple[date, ...],
    *,
    excluded: set[tuple[date, int]] | None = None,
    rising: bool = True,
) -> CatalogedBars:
    bars: list[Bar] = []
    for session_index, session_date in enumerate(session_dates):
        session = us_equity_2026_session(session_date)
        assert session is not None
        for offset in range(390):
            if excluded is not None and (session_date, offset) in excluded:
                continue
            opened = Decimal("100") + Decimal(session_index) + Decimal(offset) / Decimal("100")
            closed = opened + (Decimal("0.01") if rising else Decimal("-0.01"))
            bars.append(
                Bar(
                    symbol="QQQ",
                    market="US",
                    timeframe=Timeframe.M1,
                    start_ts=session.window.open_ts + Timeframe.M1.duration * offset,
                    open=opened,
                    high=closed + Decimal("0.01"),
                    low=opened - Decimal("0.01"),
                    close=closed,
                    volume=Decimal("1000"),
                    complete=True,
                )
            )
    return _cataloged_bars_from_verified_loader(
        dataset_id="unit.kis.paper.intraday.qqq.m1",
        dataset_hash="sha256:" + "a" * 64,
        source_path=tmp_path / "selected-index.json",
        bars=tuple(bars),
    )


def _contiguous_catalog(tmp_path: Path) -> CatalogedBars:
    start = us_equity_2026_session(date(2026, 1, 2))
    assert start is not None
    bars = []
    for offset in range(24):
        opened = Decimal("100") + Decimal(offset) / Decimal("10")
        closed = opened + Decimal("0.01")
        bars.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.M1,
                start_ts=start.window.open_ts + Timeframe.M1.duration * offset,
                open=opened,
                high=closed + Decimal("0.01"),
                low=opened - Decimal("0.01"),
                close=closed,
                volume=Decimal("1000"),
                complete=True,
            )
        )
    return _cataloged_bars_from_verified_loader(
        dataset_id="unit.kis.paper.intraday.qqq.parity.m1",
        dataset_hash="sha256:" + "b" * 64,
        source_path=tmp_path / "parity-index.json",
        bars=tuple(bars),
    )


def _small_campaign(catalog: CatalogedBars) -> CampaignContract:
    bars = catalog.bars
    return CampaignContract(
        campaign_id="unit-campaign",
        catalog=CatalogDatasetRef(
            catalog_id="unit-catalog",
            dataset_id=catalog.dataset_id,
            dataset_hash=catalog.dataset_hash,
            constructed_as_of_utc=bars[-1].end_ts,
            ranking_eligible=False,
            sealed_holdout_eligible=False,
        ),
        timeframe=Timeframe.M1,
        folds=(
            CampaignFold(
                "fold-1",
                CampaignWindow(bars[0].start_ts, bars[11].end_ts),
                CampaignWindow(bars[13].start_ts, bars[-1].end_ts),
            ),
        ),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("2"),
            slippage_source_id="unit-costs",
        ),
        purge=Timeframe.M1.duration,
        embargo=Timeframe.M1.duration,
        evidence_use="development",
        naive_baselines=("always_long",),
        deterministic_seed=71,
    )

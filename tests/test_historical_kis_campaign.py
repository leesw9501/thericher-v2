from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily import KIS_PAPER_PRIVATE_DAILY_CATALOG_ID
from thericher_v2.data.local import CatalogedBars, _cataloged_bars_from_verified_loader
from thericher_v2.research.historical_kis_campaign import (
    HISTORICAL_KIS_DAILY_NAIVE_BASELINES,
    build_historical_kis_daily_campaign,
    build_sanitized_historical_kis_summary,
    run_historical_kis_daily_cpu_baselines,
    write_frozen_historical_kis_campaign_contract,
    write_sanitized_historical_kis_summary,
)
from thericher_v2.state import EventStore


def test_frozen_contract_records_the_required_historical_research_terms(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    campaign = build_historical_kis_daily_campaign(
        _daily_catalog(tmp_path),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=repo_root,
    )

    payload = campaign.to_payload()

    assert payload["input"] == {
        "dataset_hash": "sha256:" + "a" * 64,
        "dataset_id": KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
        "loader": "load_kis_paper_private_daily_catalog",
        "source_separation": "KIS private daily source only; no source mixing",
    }
    assert payload["campaign"]["target"] == {
        "decision_price": "completed_bar_close",
        "entry_price": "next_bar_open",
        "exit_price": "following_bar_open",
        "position_side": "long_only",
        "entry_bar_offset": 1,
        "exit_bar_offset": 2,
    }
    assert payload["feature_availability"] == {
        "schema_version": 1,
        "feature_names": ["completed_daily_bar_direction"],
        "available_at": "completed_bar_end",
        "decision_rule": "decision_at_completed_bar_end",
        "execution_rule": "next_daily_bar_open_then_following_daily_bar_open",
    }
    assert payload["decision_schedule"] == {
        "schema_version": 1,
        "signal_stride_bars": 2,
        "first_signal_offset": 0,
        "rule": "next_signal_after_prior_target_exit_bar_opens",
    }
    assert payload["chronological_split"]["development_session_count"] == 63
    assert payload["chronological_split"]["purge_session_count"] == 1
    assert payload["chronological_split"]["holdout_session_count"] == 16
    assert payload["chronological_split"]["holdout_status"] == (
        "chronological_unsealed_descriptive_only"
    )
    assert payload["campaign"]["naive_baselines"] == list(HISTORICAL_KIS_DAILY_NAIVE_BASELINES)
    assert payload["campaign"]["costs"] == {
        "fee_bps": "1",
        "slippage_bps": "2",
        "slippage_source_id": "historical-kis-daily-fixed-cost-assumption-v1",
    }
    assert "after_cost_pnl" in payload["campaign"]["metrics"]
    assert payload["candidate_scope"]["prior_sequence_screens"] == ("descriptive_only_not_selected")
    assert payload["artifact_root"] == str((tmp_path / "model-artifacts").resolve())
    assert "source_path" not in json.dumps(payload)


def test_cpu_baseline_runs_only_the_fixed_naive_comparison_and_writes_sanitized_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    campaign = build_historical_kis_daily_campaign(
        _daily_catalog(tmp_path),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    contract_path = write_frozen_historical_kis_campaign_contract(
        campaign,
        path=(
            artifact_root
            / "historical-kis-daily-cpu-baseline"
            / "daily-gap-r2"
            / "campaign-contract.json"
        ),
        repo_root=repo_root,
    )

    result = run_historical_kis_daily_cpu_baselines(
        campaign,
        contract_path=contract_path,
        work_root=(artifact_root / "historical-kis-daily-cpu-baseline" / "daily-gap-r2" / "work"),
        repo_root=repo_root,
        run_label="daily-gap-r2",
    )
    summary = build_sanitized_historical_kis_summary(result, run_label="daily-gap-r2")
    summary_path = write_sanitized_historical_kis_summary(
        summary,
        path=(
            artifact_root / "historical-kis-daily-cpu-baseline" / "daily-gap-r2" / "summary.json"
        ),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    assert tuple((item.phase, item.baseline.baseline_id) for item in result.baseline_runs) == (
        ("development", "always_long"),
        ("development", "previous_bar_direction"),
        ("chronological_holdout", "always_long"),
        ("chronological_holdout", "previous_bar_direction"),
    )
    assert all(item.baseline.fill_source == "local_paper" for item in result.baseline_runs)
    assert all(
        item.baseline.replay_evidence.fill_source == "local_paper" for item in result.baseline_runs
    )
    assert result.baseline_runs[0].baseline.result.decisions_seen == 31
    assert result.baseline_runs[2].baseline.result.decisions_seen == 7
    assert summary["all_fills_local_paper"] is True
    assert summary["contract"]["artifact_name"] == "campaign-contract.json"
    assert all("path" not in item for item in summary["baseline_runs"])
    assert "source_path" not in json.dumps(summary)
    assert str(_daily_catalog(tmp_path).source_path) not in json.dumps(summary)
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary


def test_daily_holiday_gap_freezes_a_two_bar_non_overlapping_signal_schedule(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    campaign = build_historical_kis_daily_campaign(
        _daily_catalog(tmp_path, holiday_gap=True),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    starts = campaign.eligible_signal_starts("development")
    friday, monday, wednesday = campaign.cataloged_bars.bars[:3]
    assert friday.start_ts in starts
    assert monday.start_ts not in starts
    assert wednesday.start_ts in starts
    assert monday.end_ts < wednesday.start_ts

    contract_path = write_frozen_historical_kis_campaign_contract(
        campaign,
        path=(
            artifact_root
            / "historical-kis-daily-cpu-baseline"
            / "daily-holiday-gap-r3"
            / "campaign-contract.json"
        ),
        repo_root=repo_root,
    )
    result = run_historical_kis_daily_cpu_baselines(
        campaign,
        contract_path=contract_path,
        work_root=(
            artifact_root / "historical-kis-daily-cpu-baseline" / "daily-holiday-gap-r3" / "work"
        ),
        repo_root=repo_root,
        run_label="daily-holiday-gap-r3",
    )
    events = tuple(
        EventStore(
            result.baseline_runs[0].baseline.replay_evidence.state_sqlite_path,
            result.baseline_runs[0].baseline.replay_evidence.event_jsonl_path,
        ).iter_events()
    )
    assert all(
        current.created_at >= prior.created_at
        for prior, current in zip(events, events[1:], strict=False)
    )


def test_contract_rejects_a_non_kis_or_git_local_source(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = _daily_catalog(tmp_path, dataset_id="external.daily.unit-v1")

    with pytest.raises(ValueError, match="verified KIS private daily loader"):
        build_historical_kis_daily_campaign(
            source,
            artifact_root=tmp_path / "model-artifacts",
            repo_root=repo_root,
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        build_historical_kis_daily_campaign(
            _daily_catalog(tmp_path),
            artifact_root=repo_root / "model-artifacts",
            repo_root=repo_root,
        )


def test_cpu_runner_rejects_a_tampered_frozen_contract(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    campaign = build_historical_kis_daily_campaign(
        _daily_catalog(tmp_path),
        artifact_root=artifact_root,
        repo_root=repo_root,
    )
    contract_path = write_frozen_historical_kis_campaign_contract(
        campaign,
        path=artifact_root / "attempt" / "campaign-contract.json",
        repo_root=repo_root,
    )
    contract_path.write_text(
        json.dumps({"frozen_contract_hash": "sha256:" + "b" * 64}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the frozen input"):
        run_historical_kis_daily_cpu_baselines(
            campaign,
            contract_path=contract_path,
            work_root=artifact_root / "attempt" / "work",
            repo_root=repo_root,
            run_label="tamper-r2",
        )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("historical KIS CPU baseline must remain offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)
    monkeypatch.setattr(os, "getenv", fail_external)


def _daily_catalog(
    tmp_path: Path,
    *,
    dataset_id: str = KIS_PAPER_PRIVATE_DAILY_CATALOG_ID,
    holiday_gap: bool = False,
) -> CatalogedBars:
    current = datetime(2025, 1, 3 if holiday_gap else 2, tzinfo=UTC)
    bars: list[Bar] = []
    while len(bars) < 80:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        if holiday_gap and current.date() == date(2025, 1, 7):
            current += timedelta(days=1)
            continue
        index = len(bars)
        opened = Decimal("100") + Decimal(index)
        closed = opened + (Decimal("0.5") if index % 2 else Decimal("-0.25"))
        bars.append(
            Bar(
                symbol="QQQ",
                market="US",
                timeframe=Timeframe.D1,
                start_ts=current,
                open=opened,
                high=max(opened, closed) + Decimal("1"),
                low=min(opened, closed) - Decimal("1"),
                close=closed,
                volume=Decimal("1000") + Decimal(index),
                complete=True,
            )
        )
        current += timedelta(days=1)
    return _cataloged_bars_from_verified_loader(
        dataset_id=dataset_id,
        dataset_hash="sha256:" + "a" * 64,
        source_path=tmp_path / "market-data" / "daily-index.json",
        bars=tuple(bars),
    )

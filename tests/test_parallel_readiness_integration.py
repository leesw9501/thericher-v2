from __future__ import annotations

import csv
import gzip
import hashlib
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import (
    generate_trending_bars,
    load_cataloged_yahoo_intraday_1m_bars,
)
from thericher_v2.data.catalog import (
    build_training_readiness_catalog,
    select_catalog_dataset,
)
from thericher_v2.execution import EmergencyStore
from thericher_v2.research.campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from thericher_v2.research.validation import (
    run_local_paper_validation,
    run_naive_cpu_baseline,
)
from thericher_v2.state import EventStore

CATALOG_REF_FIELDS = (
    "dataset_id",
    "dataset_hash",
    "constructed_as_of_utc",
    "ranking_eligible",
    "sealed_holdout_eligible",
)


def test_catalog_to_development_baseline_is_offline_local_and_replayable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("catalog-backed validation must remain offline")

    original_open = Path.open
    original_read_text = Path.read_text

    def guard_open(path: Path, *args: object, **kwargs: object):
        lowered = path.name.lower()
        if lowered.startswith(".env") or any(
            marker in lowered for marker in ("credential", "secret", "token")
        ):
            raise AssertionError("catalog-backed validation must not read credentials")
        return original_open(path, *args, **kwargs)

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("catalog-backed validation must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(Path, "open", guard_open)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    bars = generate_trending_bars(
        timeframe=Timeframe.M1,
        count=48,
        seed=71,
    )
    intraday_paths = tuple(
        tmp_path / "market-data" / "intraday" / f"snapshot=2026-01-0{index}" / "ohlcv_1m.csv.gz"
        for index in range(5, 8)
    )
    for path in intraday_paths:
        _write_bars(path, bars)
    daily_root = tmp_path / "market-data" / "daily"
    _write_bars(
        daily_root / "snapshot=2026-01-08" / "ohlcv_daily.csv.gz",
        bars[:1],
    )

    catalog = build_training_readiness_catalog(
        intraday_paths=intraday_paths,
        daily_root=daily_root,
        proposed_holdout_start=date(2026, 1, 3),
        generated_at=datetime(2026, 7, 18, tzinfo=UTC),
    )
    selected = select_catalog_dataset(
        catalog,
        catalog["intraday_files"][0]["dataset_id"],
    )
    ref_values = {field: selected[field] for field in CATALOG_REF_FIELDS}
    ref_values["constructed_as_of_utc"] = datetime.fromisoformat(
        ref_values["constructed_as_of_utc"]
    )
    catalog_ref = CatalogDatasetRef(catalog_id=catalog["catalog_id"], **ref_values)
    selected_path = Path(selected["path"])
    cataloged = load_cataloged_yahoo_intraday_1m_bars(
        selected_path,
        dataset_id=selected["dataset_id"],
        expected_dataset_hash=selected["dataset_hash"],
        symbol="AAPL",
        max_bars=48,
    )
    loaded_bars = cataloged.bars

    assert catalog["boundaries"]["network_used"] is False
    assert catalog["boundaries"]["credentials_read"] is False
    assert catalog["training_eligible_file_count"] == 0
    assert catalog["sealed_holdout_eligible_file_count"] == 0
    assert catalog_ref.dataset_hash == selected["dataset_hash"]
    assert cataloged.dataset_id == catalog_ref.dataset_id
    assert cataloged.dataset_hash == _file_sha256(selected_path)
    assert cataloged.source_path == selected_path

    fold = CampaignFold(
        "fold-1",
        CampaignWindow(loaded_bars[0].start_ts, loaded_bars[9].end_ts),
        CampaignWindow(loaded_bars[15].start_ts, loaded_bars[25].end_ts),
    )
    campaign = CampaignContract(
        campaign_id="catalog-development-smoke",
        catalog=catalog_ref,
        timeframe=Timeframe.M1,
        folds=(fold,),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("2"),
            slippage_source_id="integration-assumption",
        ),
        purge=timedelta(minutes=1),
        embargo=timedelta(minutes=1),
        evidence_use="development",
    )
    with pytest.raises(ValueError, match="ranking eligibility"):
        replace(campaign, evidence_use="ranking")
    with pytest.raises(ValueError, match="sealed holdout ineligible"):
        replace(
            campaign,
            sealed_holdout=CampaignWindow(
                loaded_bars[31].start_ts,
                loaded_bars[43].end_ts,
            ),
        )

    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    external_root = tmp_path / "external"
    with pytest.raises(ValueError, match="requires Data-owned CatalogedBars"):
        run_local_paper_validation(
            list(cataloged.bars),
            event_store=EventStore(
                external_root / "raw-list.sqlite",
                external_root / "raw-list.jsonl",
            ),
            emergency_store=EmergencyStore(external_root / "raw-list-emergency.json"),
            campaign=campaign,
        )

    wrong_timeframe_campaign = replace(
        campaign,
        timeframe=Timeframe.M5,
        purge=timedelta(minutes=5),
        embargo=timedelta(minutes=5),
    )
    with pytest.raises(ValueError, match="timeframe does not match"):
        run_local_paper_validation(
            cataloged,
            event_store=EventStore(
                external_root / "timeframe.sqlite",
                external_root / "timeframe.jsonl",
            ),
            emergency_store=EmergencyStore(external_root / "timeframe-emergency.json"),
            campaign=wrong_timeframe_campaign,
        )

    first = run_naive_cpu_baseline(
        cataloged,
        campaign=campaign,
        artifact_root=external_root / "artifacts-a",
        work_dir=external_root / "run-a",
        repo_root=fake_repo,
    )
    second = run_naive_cpu_baseline(
        cataloged,
        campaign=campaign,
        artifact_root=external_root / "artifacts-b",
        work_dir=external_root / "run-b",
        repo_root=fake_repo,
    )

    first_store = EventStore(
        external_root / "run-a" / "state.sqlite",
        external_root / "run-a" / "events.jsonl",
    )
    second_store = EventStore(
        external_root / "run-b" / "state.sqlite",
        external_root / "run-b" / "events.jsonl",
    )
    first_events = list(first_store.iter_events())
    second_events = list(second_store.iter_events())
    fill_events = [event for event in first_events if event.event_type == "fill"]

    replay = first.replay_evidence
    assert first.artifact_path.exists()
    evidence_paths = (
        first.artifact_path,
        replay.event_jsonl_path,
        replay.state_sqlite_path,
        replay.emergency_path,
    )
    assert all(path.exists() for path in evidence_paths)
    assert all(not path.is_relative_to(fake_repo) for path in evidence_paths)
    assert replay.event_jsonl_sha256 == _file_sha256(replay.event_jsonl_path)
    assert replay.state_sqlite_sha256 == _file_sha256(replay.state_sqlite_path)
    assert replay.emergency_sha256 == _file_sha256(replay.emergency_path)
    assert first.fill_source == replay.fill_source == "local_paper"
    assert fill_events
    assert all(event.payload["source"] == "local_paper" for event in fill_events)
    assert first.result.final_position == 0
    assert first.result.dataset_id == cataloged.dataset_id
    assert first.result.dataset_hash == cataloged.dataset_hash
    assert first.result.dataset_source_path == selected_path.resolve()
    assert first_store.replay() == second_store.replay()
    assert [event.to_record() for event in first_events] == [
        event.to_record() for event in second_events
    ]
    first_payload = json.loads(first.artifact_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second.artifact_path.read_text(encoding="utf-8"))
    assert first_payload["cataloged_data"]["dataset_hash"] == cataloged.dataset_hash
    assert first_payload["replay_evidence"]["fill_source"] == "local_paper"
    assert _without_replay_paths(first_payload) == _without_replay_paths(second_payload)

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_naive_cpu_baseline(
            cataloged,
            campaign=campaign,
            artifact_root=fake_repo / "artifacts",
            work_dir=external_root / "repo-artifact-attempt",
            repo_root=fake_repo,
        )
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_naive_cpu_baseline(
            cataloged,
            campaign=campaign,
            artifact_root=external_root / "work-dir-check-artifacts",
            work_dir=fake_repo / "work",
            repo_root=fake_repo,
        )
    assert not any(fake_repo.rglob("*"))

    selected_path.write_bytes(selected_path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_cataloged_yahoo_intraday_1m_bars(
            selected_path,
            dataset_id=cataloged.dataset_id,
            expected_dataset_hash=cataloged.dataset_hash,
            symbol="AAPL",
            max_bars=48,
        )


def _without_replay_paths(payload: dict[str, object]) -> dict[str, object]:
    normalized = json.loads(json.dumps(payload))
    replay = normalized["replay_evidence"]
    replay["work_dir"] = "<external-work-dir>"
    for key in ("event_jsonl", "state_sqlite", "emergency"):
        replay[key]["path"] = f"<{key}-path>"
    return normalized


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bars(path: Path, bars: list[Bar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "symbol",
                "timestamp_utc",
                "session_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ),
        )
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "symbol": bar.symbol,
                    "timestamp_utc": bar.start_ts.isoformat(),
                    "session_date": bar.start_ts.date().isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )

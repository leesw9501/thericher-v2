from __future__ import annotations

import csv
import gzip
import hashlib
import json
import socket
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, ModelPrediction, Timeframe
from thericher_v2.data import CatalogedBars, load_cataloged_yahoo_intraday_1m_bars
from thericher_v2.execution import EmergencyStore
from thericher_v2.models import MomentumModel
from thericher_v2.research.campaign import (
    CampaignContract,
    CampaignCosts,
    CampaignFold,
    CampaignWindow,
    CatalogDatasetRef,
    ExecutableTarget,
)
from thericher_v2.research.validation import (
    discard_partial_campaign_replay,
    run_campaign_model_replay,
    run_local_paper_validation,
    run_naive_cpu_baseline,
)
from thericher_v2.state import EventStore

DATASET_ID = "unit-yahoo-1m"


def _write_snapshot(path: Path, *, count: int = 48) -> str:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("symbol", "timestamp_utc", "open", "high", "low", "close", "volume"),
        )
        writer.writeheader()
        price = Decimal("100")
        for index in range(count):
            opened = price
            price = (opened * Decimal("1.001")).quantize(Decimal("0.0001"))
            writer.writerow(
                {
                    "symbol": "AAPL",
                    "timestamp_utc": (start + timedelta(minutes=index)).isoformat(),
                    "open": opened,
                    "high": max(opened, price) + Decimal("0.01"),
                    "low": min(opened, price) - Decimal("0.01"),
                    "close": price,
                    "volume": 1000 + index,
                }
            )
    return _file_sha256(path)


def _load_cataloged(tmp_path: Path) -> CatalogedBars:
    snapshot = tmp_path / "ohlcv_1m.csv.gz"
    dataset_hash = _write_snapshot(snapshot)
    return load_cataloged_yahoo_intraday_1m_bars(
        snapshot,
        dataset_id=DATASET_ID,
        expected_dataset_hash=dataset_hash,
        symbol="AAPL",
        max_bars=48,
    )


def _contract(
    cataloged: CatalogedBars,
    *,
    slippage_bps: Decimal = Decimal("2"),
    holdout_eligible: bool = True,
    as_of_after_holdout: bool = False,
    timeframe: Timeframe = Timeframe.M1,
) -> CampaignContract:
    bars = cataloged.bars
    development = CampaignWindow(bars[0].start_ts, bars[9].end_ts)
    validation = CampaignWindow(bars[15].start_ts, bars[25].end_ts)
    holdout = CampaignWindow(bars[31].start_ts, bars[43].end_ts)
    as_of = holdout.start_utc + timedelta(minutes=1) if as_of_after_holdout else bars[0].start_ts
    return CampaignContract(
        campaign_id="unit-campaign",
        catalog=CatalogDatasetRef(
            catalog_id="unit-catalog",
            dataset_id=cataloged.dataset_id,
            dataset_hash=cataloged.dataset_hash,
            constructed_as_of_utc=as_of,
            ranking_eligible=True,
            sealed_holdout_eligible=holdout_eligible,
        ),
        timeframe=timeframe,
        folds=(CampaignFold("fold-1", development, validation),),
        target=ExecutableTarget(),
        costs=CampaignCosts(
            fee_bps=Decimal("1"),
            slippage_bps=slippage_bps,
            slippage_source_id="unit-independent-assumption",
        ),
        purge=timeframe.duration,
        embargo=timeframe.duration,
        evidence_use="ranking",
        sealed_holdout=holdout,
        deterministic_seed=71,
    )


def test_campaign_rejects_overlap_zero_slippage_and_bad_holdout(tmp_path: Path) -> None:
    cataloged = _load_cataloged(tmp_path)
    bars = cataloged.bars
    with pytest.raises(ValueError, match="must not overlap"):
        CampaignFold(
            "overlap",
            CampaignWindow(bars[0].start_ts, bars[10].end_ts),
            CampaignWindow(bars[9].start_ts, bars[20].end_ts),
        )
    with pytest.raises(ValueError, match="strictly positive slippage"):
        _contract(cataloged, slippage_bps=Decimal("0"))
    with pytest.raises(ValueError, match="marks the sealed holdout ineligible"):
        _contract(cataloged, holdout_eligible=False)
    with pytest.raises(ValueError, match="after sealed holdout start"):
        _contract(cataloged, as_of_after_holdout=True)


def test_loader_rejects_byte_tamper_before_parsing(tmp_path: Path) -> None:
    snapshot = tmp_path / "ohlcv_1m.csv.gz"
    expected_hash = _write_snapshot(snapshot)
    original = load_cataloged_yahoo_intraday_1m_bars(
        snapshot,
        dataset_id=DATASET_ID,
        expected_dataset_hash=expected_hash,
    )
    assert original.dataset_hash == expected_hash

    snapshot.write_bytes(snapshot.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_cataloged_yahoo_intraday_1m_bars(
            snapshot,
            dataset_id=DATASET_ID,
            expected_dataset_hash=expected_hash,
        )


def test_campaign_harness_requires_cataloged_bars_and_matching_timeframe(
    tmp_path: Path,
) -> None:
    cataloged = _load_cataloged(tmp_path)
    campaign = _contract(cataloged)
    with pytest.raises(ValueError, match="requires Data-owned CatalogedBars"):
        run_local_paper_validation(
            list(cataloged.bars),
            event_store=EventStore(tmp_path / "raw.sqlite", tmp_path / "raw.jsonl"),
            emergency_store=EmergencyStore(tmp_path / "raw-emergency.json"),
            campaign=campaign,
        )

    wrong_hash_campaign = replace(
        campaign,
        catalog=replace(campaign.catalog, dataset_hash="sha256:" + "b" * 64),
    )
    with pytest.raises(ValueError, match="dataset_hash does not match"):
        run_local_paper_validation(
            cataloged,
            event_store=EventStore(tmp_path / "hash.sqlite", tmp_path / "hash.jsonl"),
            emergency_store=EmergencyStore(tmp_path / "hash-emergency.json"),
            campaign=wrong_hash_campaign,
        )

    wrong_timeframe_campaign = _contract(cataloged, timeframe=Timeframe.M5)
    with pytest.raises(ValueError, match="timeframe does not match"):
        run_local_paper_validation(
            cataloged,
            event_store=EventStore(tmp_path / "timeframe.sqlite", tmp_path / "timeframe.jsonl"),
            emergency_store=EmergencyStore(tmp_path / "timeframe-emergency.json"),
            campaign=wrong_timeframe_campaign,
        )

    with pytest.raises(ValueError, match="cannot be used for tuning"):
        run_local_paper_validation(
            cataloged,
            event_store=EventStore(tmp_path / "holdout.sqlite", tmp_path / "holdout.jsonl"),
            emergency_store=EmergencyStore(tmp_path / "holdout-emergency.json"),
            campaign=campaign,
            phase="holdout",
            tuning=True,
        )


def test_naive_baseline_keeps_durable_offline_replay_and_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("campaign baseline must not use a network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("campaign baseline must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    cataloged = _load_cataloged(tmp_path)
    campaign = _contract(cataloged)

    first = run_naive_cpu_baseline(
        cataloged,
        campaign=campaign,
        artifact_root=tmp_path / "artifacts-a",
        work_dir=tmp_path / "run-a",
        repo_root=Path.cwd(),
    )
    second = run_naive_cpu_baseline(
        cataloged,
        campaign=campaign,
        artifact_root=tmp_path / "artifacts-b",
        work_dir=tmp_path / "run-b",
        repo_root=Path.cwd(),
    )

    result = first.result
    assert result.bars_seen == 10
    assert result.final_position == 0
    assert result.trades
    assert result.dataset_id == cataloged.dataset_id
    assert result.dataset_hash == cataloged.dataset_hash
    assert result.total_fees > 0
    assert result.total_slippage > 0
    assert result.after_cost_pnl == result.gross_pnl - result.total_fees - result.total_slippage
    for entry, exit_fill in zip(result.trades[::2], result.trades[1::2], strict=True):
        assert entry.side == "buy"
        assert exit_fill.side == "sell"
        assert entry.filled_at == entry.signal_bar_end
        assert exit_fill.filled_at == exit_fill.signal_bar_end
        assert exit_fill.filled_at - entry.filled_at == result.timeframe.duration

    replay = first.replay_evidence
    assert first.fill_source == "local_paper"
    assert replay.fill_source == "local_paper"
    assert replay.event_jsonl_path.exists()
    assert replay.state_sqlite_path.exists()
    assert replay.emergency_path.exists()
    assert replay.event_jsonl_sha256 == _file_sha256(replay.event_jsonl_path)
    assert replay.state_sqlite_sha256 == _file_sha256(replay.state_sqlite_path)
    assert replay.emergency_sha256 == _file_sha256(replay.emergency_path)

    events = EventStore(replay.state_sqlite_path, replay.event_jsonl_path)
    fill_events = [event for event in events.iter_events() if event.event_type == "fill"]
    assert fill_events
    assert all(event.payload["source"] == "local_paper" for event in fill_events)

    first_payload = json.loads(first.artifact_path.read_text())
    second_payload = json.loads(second.artifact_path.read_text())
    assert first_payload["replay_evidence"]["fill_source"] == "local_paper"
    assert first_payload["cataloged_data"]["dataset_hash"] == cataloged.dataset_hash
    assert _without_replay_paths(first_payload) == _without_replay_paths(second_payload)

    with pytest.raises(FileExistsError, match="validation artifact already exists"):
        run_naive_cpu_baseline(
            cataloged,
            campaign=campaign,
            artifact_root=tmp_path / "artifacts-a",
            work_dir=tmp_path / "duplicate-run",
            repo_root=Path.cwd(),
        )
    assert not (tmp_path / "duplicate-run").exists()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_naive_cpu_baseline(
            cataloged,
            campaign=campaign,
            artifact_root=Path.cwd() / "model-artifacts",
            work_dir=tmp_path / "repo-artifact-run",
            repo_root=Path.cwd(),
        )


def test_explicit_partial_campaign_replay_discard_allows_retry(tmp_path: Path) -> None:
    cataloged = _load_cataloged(tmp_path)
    campaign = _contract(cataloged)
    artifact_root = tmp_path / "artifacts"
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    sentinel = work_dir / "leave-me-alone.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    run_id = "unit-recovery-replay"

    with pytest.raises(RuntimeError, match="injected prediction failure"):
        run_campaign_model_replay(
            cataloged,
            campaign=campaign,
            model=_FailAfterFirstPrediction(),
            run_id=run_id,
            artifact_root=artifact_root,
            work_dir=work_dir,
            repo_root=Path.cwd(),
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert (work_dir / "events.jsonl").is_file()
    assert (work_dir / "emergency.json").is_file()
    artifact_path = artifact_root / "validation" / f"{run_id}.json"
    assert not artifact_path.exists()
    with pytest.raises(FileExistsError, match="event JSONL already exists"):
        run_campaign_model_replay(
            cataloged,
            campaign=campaign,
            model=MomentumModel(),
            run_id=run_id,
            artifact_root=artifact_root,
            work_dir=work_dir,
            repo_root=Path.cwd(),
        )

    sidecars = ("state.sqlite", "state.sqlite-journal", "state.sqlite-shm", "state.sqlite-wal")
    for name in sidecars:
        (work_dir / name).write_text("partial", encoding="utf-8")
    discarded = discard_partial_campaign_replay(
        artifact_root=artifact_root,
        work_dir=work_dir,
        run_id=run_id,
        repo_root=Path.cwd(),
    )

    assert {path.name for path in discarded} == {
        "emergency.json",
        "events.jsonl",
        *sidecars,
    }
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    partial_names = (*sidecars, "events.jsonl", "emergency.json")
    assert all(not (work_dir / name).exists() for name in partial_names)

    stale_wal = work_dir / "state.sqlite-wal"
    stale_wal.write_text("partial", encoding="utf-8")
    with pytest.raises(FileExistsError, match="state SQLite write-ahead log already exists"):
        run_campaign_model_replay(
            cataloged,
            campaign=campaign,
            model=MomentumModel(),
            run_id=run_id,
            artifact_root=artifact_root,
            work_dir=work_dir,
            repo_root=Path.cwd(),
        )
    assert discard_partial_campaign_replay(
        artifact_root=artifact_root,
        work_dir=work_dir,
        run_id=run_id,
        repo_root=Path.cwd(),
    ) == (stale_wal,)

    recovered = run_campaign_model_replay(
        cataloged,
        campaign=campaign,
        model=MomentumModel(),
        run_id=run_id,
        artifact_root=artifact_root,
        work_dir=work_dir,
        repo_root=Path.cwd(),
    )

    assert recovered.fill_source == "local_paper"
    assert recovered.artifact_path.is_file()
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    with pytest.raises(FileExistsError, match="completed validation artifact"):
        discard_partial_campaign_replay(
            artifact_root=artifact_root,
            work_dir=work_dir,
            run_id=run_id,
            repo_root=Path.cwd(),
        )


class _FailAfterFirstPrediction:
    lookback = 3

    def __init__(self) -> None:
        self._calls = 0
        self._delegate = MomentumModel()

    def predict(self, bars: list[Bar]) -> ModelPrediction:
        self._calls += 1
        if self._calls > 1:
            raise RuntimeError("injected prediction failure")
        return self._delegate.predict(bars)


def _without_replay_paths(payload: dict[str, object]) -> dict[str, object]:
    normalized = json.loads(json.dumps(payload))
    replay = normalized["replay_evidence"]
    replay["work_dir"] = "<external-work-dir>"
    for key in ("event_jsonl", "state_sqlite", "emergency"):
        replay[key]["path"] = f"<{key}-path>"
    return normalized


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

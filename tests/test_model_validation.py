from __future__ import annotations

import csv
import gzip
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data import generate_trending_bars
from thericher_v2.execution import EmergencyStore
from thericher_v2.research.validation import (
    GpuReadiness,
    ValidationConfig,
    discover_market_data_inventory,
    load_yahoo_intraday_1m_bars,
    run_local_paper_validation,
    run_sample_cpu_smoke,
    write_gpu_experiment_plan,
    write_validation_artifact,
)
from thericher_v2.state import EventStore


def test_validation_loop_uses_local_paper_and_replayable_fills(tmp_path) -> None:
    bars = generate_trending_bars(count=20, seed=31)
    store = EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl")

    result = run_local_paper_validation(
        bars,
        event_store=store,
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        config=ValidationConfig(run_id="unit-validation"),
        data_source="unit_sample",
    )

    events = list(store.iter_events())
    fill_events = [event for event in events if event.event_type == "fill"]

    assert result.data_source == "unit_sample"
    assert result.trades
    assert result.event_count == len(events)
    assert any(event.event_type == "model_prediction" for event in events)
    assert any(event.event_type == "ensemble_decision" for event in events)
    assert fill_events
    assert all(event.payload["source"] == "local_paper" for event in fill_events)
    assert store.replay().positions[("US", "AAPL")] == result.final_position


def test_validation_loop_is_offline_and_does_not_read_credentials(monkeypatch, tmp_path) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validation must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("validation must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_local_paper_validation(
        generate_trending_bars(count=20, seed=32),
        event_store=EventStore(tmp_path / "state.sqlite", tmp_path / "events.jsonl"),
        emergency_store=EmergencyStore(tmp_path / "emergency.json"),
        config=ValidationConfig(run_id="offline-validation"),
    )

    assert result.trades


def test_yahoo_intraday_loader_reads_explicit_gzip_snapshot(tmp_path) -> None:
    snapshot = tmp_path / "ohlcv_1m.csv.gz"
    with gzip.open(snapshot, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "timestamp_utc",
                "timestamp_et",
                "session_date",
                "bar_time_et",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "source",
            ],
        )
        writer.writeheader()
        for index in range(3):
            writer.writerow(
                {
                    "symbol": "MSFT",
                    "timestamp_utc": f"2026-06-30T13:3{index}:00Z",
                    "timestamp_et": "",
                    "session_date": "2026-06-30",
                    "bar_time_et": "",
                    "open": str(100 + index),
                    "high": str(101 + index),
                    "low": str(99 + index),
                    "close": str(100.5 + index),
                    "volume": str(1000 + index),
                    "source": "unit",
                }
            )

    bars = load_yahoo_intraday_1m_bars(snapshot, symbol="MSFT", max_bars=2)

    assert len(bars) == 2
    assert bars[0].symbol == "MSFT"
    assert bars[0].market == "US"
    assert bars[0].start_ts == datetime(2026, 6, 30, 13, 30, tzinfo=UTC)


def test_validation_artifacts_are_written_outside_repo(tmp_path) -> None:
    result = run_sample_cpu_smoke(tmp_path / "smoke")
    artifact_root = tmp_path / "model-artifacts"

    artifact = write_validation_artifact(
        result,
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )

    assert artifact.exists()
    assert artifact_root in artifact.parents
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_validation_artifact(
            result,
            artifact_root=Path.cwd() / "model_artifacts",
            repo_root=Path.cwd(),
        )


def test_gpu_plan_artifact_is_mocked_outside_repo(tmp_path) -> None:
    result = run_sample_cpu_smoke(tmp_path / "smoke")
    gpu = GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    artifact = write_gpu_experiment_plan(
        result=result,
        gpu=gpu,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    assert artifact.exists()
    assert artifact.name.endswith("-gpu-plan.json")


def test_market_data_inventory_is_shallow_and_tolerates_missing_root(tmp_path) -> None:
    missing = discover_market_data_inventory(tmp_path / "missing")

    assert not missing.root_exists
    assert missing.useful_paths == ()

from __future__ import annotations

import csv
import gzip
import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.research.experiments import (
    MAX_SHORT_EXPERIMENTS,
    ExperimentSpec,
    default_short_experiment_specs,
    load_experiment_source,
    run_short_experiment_queue,
    write_experiment_metrics_artifact,
    write_gpu_candidate_smoke_artifact,
)
from thericher_v2.research.validation import GpuReadiness


def test_short_experiment_queue_replays_local_paper_metrics(tmp_path) -> None:
    source = load_experiment_source(max_bars=60)
    specs = (
        ExperimentSpec("unit_m1", timeframe=Timeframe.M1, lookback=3),
        ExperimentSpec("unit_m5", timeframe=Timeframe.M5, lookback=3),
    )

    first = run_short_experiment_queue(
        source,
        queue_id="unit-short-queue",
        specs=specs,
        work_root=tmp_path / "first",
    )
    second = run_short_experiment_queue(
        source,
        queue_id="unit-short-queue",
        specs=specs,
        work_root=tmp_path / "second",
    )

    assert first.experiments == second.experiments
    assert len(first.experiments) == 2
    for metrics in first.experiments:
        assert metrics.data_source == "deterministic_sample"
        assert metrics.local_paper_trades == metrics.replay_fill_count
        assert metrics.final_position == metrics.replay_final_position
        assert metrics.event_count >= metrics.decisions_seen


def test_experiment_queue_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("experiment queue must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("experiment queue must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_short_experiment_queue(
        load_experiment_source(max_bars=50),
        queue_id="offline-experiment-queue",
        specs=(ExperimentSpec("offline_m1"),),
        work_root=tmp_path / "queue",
    )

    assert result.experiments[0].local_paper_trades >= 0


def test_experiment_artifact_is_written_outside_repo(tmp_path) -> None:
    result = run_short_experiment_queue(
        load_experiment_source(max_bars=50),
        queue_id="artifact-queue",
        specs=(ExperimentSpec("artifact_m1"),),
        work_root=tmp_path / "queue",
    )

    artifact = write_experiment_metrics_artifact(
        result,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["queue_id"] == "artifact-queue"
    assert payload["experiment_count"] == 1
    assert payload["experiments"][0]["local_paper_trades"] == payload["experiments"][0][
        "replay_fill_count"
    ]
    with pytest.raises(ValueError, match="outside the Git workspace"):
        write_experiment_metrics_artifact(
            result,
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
        )


def test_external_market_data_use_is_explicit(tmp_path) -> None:
    snapshot = tmp_path / "ohlcv_1m.csv.gz"
    _write_yahoo_snapshot(snapshot, symbol="MSFT", count=30)

    sample_source = load_experiment_source(max_bars=30)
    external_source = load_experiment_source(
        yahoo_snapshot=snapshot,
        symbol="MSFT",
        max_bars=30,
    )
    result = run_short_experiment_queue(
        external_source,
        queue_id="external-data-queue",
        specs=(ExperimentSpec("external_m1", timeframe=Timeframe.M1, lookback=3),),
        work_root=tmp_path / "queue",
    )

    assert sample_source.external_path is None
    assert sample_source.data_source == "deterministic_sample"
    assert external_source.external_path == snapshot
    assert result.experiments[0].symbol == "MSFT"
    assert result.experiments[0].data_source == str(snapshot)


def test_default_short_queue_is_bounded() -> None:
    assert len(default_short_experiment_specs()) <= MAX_SHORT_EXPERIMENTS
    too_many = tuple(ExperimentSpec(f"too_many_{index}") for index in range(9))

    with pytest.raises(ValueError, match="capped"):
        run_short_experiment_queue(
            load_experiment_source(max_bars=40),
            specs=too_many,
        )


def test_gpu_candidate_smoke_artifact_is_prepared_outside_repo(tmp_path) -> None:
    result = run_short_experiment_queue(
        load_experiment_source(max_bars=50),
        queue_id="gpu-candidate-queue",
        specs=(ExperimentSpec("candidate_m1"),),
        work_root=tmp_path / "queue",
    )
    gpu = GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    artifact = write_gpu_candidate_smoke_artifact(
        result,
        gpu=gpu,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
    )

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["status"] == "prepared_not_trained"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["candidate_experiment_id"] == "candidate_m1"


def _write_yahoo_snapshot(path: Path, *, symbol: str, count: int) -> None:
    start = datetime(2026, 6, 30, 13, 30, tzinfo=UTC)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
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
        for index in range(count):
            timestamp = start + timedelta(minutes=index)
            open_price = Decimal("100") + Decimal(index) / Decimal("10")
            close_price = open_price + Decimal("0.03")
            writer.writerow(
                {
                    "symbol": symbol,
                    "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                    "timestamp_et": "",
                    "session_date": "2026-06-30",
                    "bar_time_et": "",
                    "open": str(open_price),
                    "high": str(close_price + Decimal("0.05")),
                    "low": str(open_price - Decimal("0.05")),
                    "close": str(close_price),
                    "volume": str(1000 + index),
                    "source": "unit",
                }
            )

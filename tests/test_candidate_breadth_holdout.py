from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.research.candidate_breadth_holdout import (
    CandidateBreadthHoldoutConfig,
    run_bounded_candidate_breadth_holdout,
)
from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessSliceConfig,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_breadth_holdout_consumes_queue_and_reuses_primitives(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_breadth_holdout as breadth_holdout

    calibration_calls: list[str] = []
    holdout_calls: list[str] = []
    original_calibration = breadth_holdout.run_bounded_candidate_threshold_calibration
    original_holdout = breadth_holdout.run_bounded_candidate_threshold_holdout

    def spy_calibration(**kwargs):  # noqa: ANN001
        calibration_calls.append(kwargs["config"].run_id)
        return original_calibration(**kwargs)

    def spy_holdout(**kwargs):  # noqa: ANN001
        holdout_calls.append(kwargs["config"].run_id)
        return original_holdout(**kwargs)

    monkeypatch.setattr(
        breadth_holdout,
        "run_bounded_candidate_threshold_calibration",
        spy_calibration,
    )
    monkeypatch.setattr(
        breadth_holdout,
        "run_bounded_candidate_threshold_holdout",
        spy_holdout,
    )

    artifact_root = tmp_path / "model-artifacts"
    queue_artifact = _breadth_queue_artifact(
        artifact_root,
        variant_ids=("unit-lb3", "unit-lb5"),
    )
    source_snapshot = _yahoo_snapshot(tmp_path / "source", symbols=("AAA", "BBB"))
    holdout_snapshot = _yahoo_snapshot(tmp_path / "holdout", symbols=("AAA", "BBB"))

    result = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-breadth-holdout",
            max_bars=40,
            source_slices=_slices(source_snapshot, ("AAA", "BBB")),
            holdout_slices=_slices(holdout_snapshot, ("AAA", "BBB")),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=_unit_gpu(),
        probability_runner=_probability_runner,
    )

    payload = json.loads(result.holdout_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_breadth_holdout_replayed_only"
    assert result.input_variant_count == 2
    assert result.processed_variant_count == 2
    assert result.completed_variant_count == 2
    assert calibration_calls == [
        "unit-breadth-holdout-unit-lb3-cal",
        "unit-breadth-holdout-unit-lb5-cal",
    ]
    assert holdout_calls == [
        "unit-breadth-holdout-unit-lb3-hold",
        "unit-breadth-holdout-unit-lb5-hold",
    ]
    assert payload["selection"]["winner"] is None
    assert payload["selection"]["recommendation"] is None
    assert payload["selection"]["promotion_gate"] is False
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["metrics"]["local_paper_fill_count_total"] > 0
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.holdout_artifact.resolve().parents
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_breadth_holdout(
            config=CandidateBreadthHoldoutConfig(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
            breadth_queue_artifact=Path.cwd() / "queue.json",
            gpu=_unit_gpu(),
        )


def test_candidate_breadth_holdout_processes_at_most_three_variants(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    queue_artifact = _breadth_queue_artifact(
        artifact_root,
        variant_ids=("v1", "v2", "v3", "v4"),
    )
    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))

    result = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-breadth-holdout-cap",
            max_bars=40,
            source_slices=_slices(snapshot, ("AAA",)),
            holdout_slices=_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=_unit_gpu(),
        probability_runner=_probability_runner,
    )

    assert result.input_variant_count == 4
    assert result.processed_variant_count == 3
    assert [item.variant_id for item in result.variants] == ["v1", "v2", "v3"]


def test_candidate_breadth_holdout_missing_queue_and_model_are_prepared(
    tmp_path,
) -> None:
    missing_queue = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(run_id="unit-missing-queue"),
        artifact_root=tmp_path / "model-artifacts-missing-queue",
        repo_root=Path.cwd(),
        breadth_queue_artifact=tmp_path / "missing-queue.json",
        gpu=_unit_gpu(),
        probability_runner=_probability_runner,
    )

    assert missing_queue.status == "prepared_not_breadth_holdout_replayed"
    assert "artifact is missing" in missing_queue.reason

    artifact_root = tmp_path / "model-artifacts-missing-model"
    queue_artifact = _breadth_queue_artifact(
        artifact_root,
        variant_ids=("unit-lb3",),
        write_model=False,
    )
    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))
    missing_model = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-missing-model",
            max_bars=40,
            source_slices=_slices(snapshot, ("AAA",)),
            holdout_slices=_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=_unit_gpu(),
        probability_runner=_probability_runner,
    )

    assert missing_model.status == "prepared_not_breadth_holdout_replayed"
    assert missing_model.variants[0].status == "prepared_not_holdout_replayed"
    assert missing_model.variants[0].calibration is not None
    assert missing_model.variants[0].calibration.status == "prepared_not_calibrated"


def test_candidate_breadth_holdout_missing_data_gpu_and_backend_are_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    queue_artifact = _breadth_queue_artifact(artifact_root, variant_ids=("unit-lb3",))
    missing_snapshot = tmp_path / "missing.csv.gz"

    missing_data = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-missing-data",
            source_slices=_slices(missing_snapshot, ("AAA",)),
            holdout_slices=_slices(missing_snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=_unit_gpu(),
        probability_runner=_probability_runner,
    )
    assert missing_data.status == "prepared_not_breadth_holdout_replayed"
    assert missing_data.variants[0].status == "prepared_not_holdout_replayed"

    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))
    missing_gpu = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-missing-gpu",
            max_bars=40,
            source_slices=_slices(snapshot, ("AAA",)),
            holdout_slices=_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )
    assert missing_gpu.status == "prepared_not_breadth_holdout_replayed"

    import thericher_v2.research.candidate_replay as candidate_replay

    monkeypatch.setattr(
        candidate_replay.importlib.util,
        "find_spec",
        lambda _name: None,
    )
    missing_backend = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-missing-backend",
            max_bars=40,
            source_slices=_slices(snapshot, ("AAA",)),
            holdout_slices=_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=_unit_gpu(),
    )
    assert missing_backend.status == "prepared_not_breadth_holdout_replayed"


def test_candidate_breadth_holdout_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate breadth holdout must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate breadth holdout must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root = tmp_path / "model-artifacts"
    queue_artifact = _breadth_queue_artifact(artifact_root, variant_ids=("unit-lb3",))
    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))
    result = run_bounded_candidate_breadth_holdout(
        config=CandidateBreadthHoldoutConfig(
            run_id="unit-offline-breadth-holdout",
            max_bars=40,
            source_slices=_slices(snapshot, ("AAA",)),
            holdout_slices=_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_queue_artifact=queue_artifact,
        gpu=_unit_gpu(),
        probability_runner=_probability_runner,
    )

    assert result.holdout_artifact.exists()


def test_candidate_breadth_holdout_import_keeps_torch_lazy_and_no_kis_paths(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    import thericher_v2.research.candidate_breadth_holdout as breadth_holdout

    source = Path(breadth_holdout.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source
    assert "live" not in source


def _breadth_queue_artifact(
    artifact_root: Path,
    *,
    variant_ids: tuple[str, ...],
    write_model: bool = True,
) -> Path:
    queue_dir = artifact_root / "candidate-breadth-queue" / "unit-queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    variants = []
    for index, variant_id in enumerate(variant_ids, start=1):
        training_artifact, evaluation_artifact, model_artifact = _variant_artifacts(
            artifact_root,
            variant_id=variant_id,
            lookback=index + 2,
            write_model=write_model,
        )
        variants.append(
            {
                "variant_id": variant_id,
                "status": "variant_evaluated_only",
                "candidate_experiment_id": variant_id,
                "candidate_parameters": {
                    "model_id": "momentum_close_v1",
                    "timeframe": "1m",
                    "lookback": index + 2,
                    "buy_threshold_bps": 10,
                    "sell_threshold_bps": -10,
                },
                "training": {
                    "status": "candidate_trained_only",
                    "metrics_artifact": str(training_artifact),
                    "model_artifact": str(model_artifact),
                },
                "evaluation": {
                    "status": "candidate_evaluated_only",
                    "evaluation_artifact": str(evaluation_artifact),
                },
            }
        )
    path = queue_dir / "metrics.json"
    path.write_text(
        json.dumps(
            {
                "status": "candidate_breadth_queued_only",
                "reason": "unit breadth queue completed",
                "variant_count": len(variants),
                "variants": variants,
                "artifact_policy": {
                    "root": str(artifact_root),
                    "repo_storage_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _variant_artifacts(
    artifact_root: Path,
    *,
    variant_id: str,
    lookback: int,
    write_model: bool,
) -> tuple[Path, Path, Path]:
    model_artifact = artifact_root / "models" / f"{variant_id}.pt"
    model_artifact.parent.mkdir(parents=True, exist_ok=True)
    if write_model:
        model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = artifact_root / "candidate-training" / variant_id / "metrics.json"
    evaluation_artifact = artifact_root / "candidate-evaluation" / variant_id / "metrics.json"
    training_artifact.parent.mkdir(parents=True, exist_ok=True)
    evaluation_artifact.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "candidate_experiment_id": variant_id,
        "candidate_parameters": {
            "lookback": lookback,
            "timeframe": "1m",
            "model_id": "momentum_close_v1",
        },
        "source_slices": [],
        "artifacts": {
            "model": str(model_artifact),
        },
        "metrics": {
            "feature_names": [
                "lookback_return",
                "last_bar_return",
                "bar_range",
                "volume_change",
            ],
            "model_artifact": str(model_artifact),
        },
    }
    training_artifact.write_text(json.dumps(payload), encoding="utf-8")
    evaluation_artifact.write_text(
        json.dumps(
            {
                **payload,
                "training_metrics_artifact": str(training_artifact),
                "model_artifact": str(model_artifact),
                "artifacts": {
                    "source_model": str(model_artifact),
                },
            }
        ),
        encoding="utf-8",
    )
    return training_artifact, evaluation_artifact, model_artifact


def _probability_runner(dataset, model, training_payload):  # noqa: ANN001
    values = (0.18, 0.32, 0.49, 0.67, 0.84)
    probabilities = tuple(values[index % len(values)] for index in range(len(dataset.labels)))
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": probabilities,
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "model_artifact": str(model),
        "candidate_experiment_id": training_payload.get("candidate_experiment_id"),
    }


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _slices(
    yahoo_snapshot: Path,
    symbols: tuple[str, ...],
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    return tuple(
        CandidateThresholdRobustnessSliceConfig(
            slice_id=symbol.lower(),
            yahoo_snapshot=yahoo_snapshot,
            symbol=symbol,
        )
        for symbol in symbols
    )


def _yahoo_snapshot(
    directory: Path,
    *,
    symbols: tuple[str, ...],
    bar_count: int = 50,
) -> Path:
    import csv
    import gzip

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ohlcv_1m.csv.gz"
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    fields = [
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
    ]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for symbol_index, symbol in enumerate(symbols):
            base_price = 100 + symbol_index
            for index in range(bar_count):
                timestamp = start + timedelta(minutes=index)
                price = base_price + index * 0.02
                close = price + (0.05 if index % 2 == 0 else -0.03)
                writer.writerow(
                    {
                        "symbol": symbol,
                        "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                        "timestamp_et": "",
                        "session_date": "2026-01-02",
                        "bar_time_et": "",
                        "open": f"{price:.4f}",
                        "high": f"{price + 0.10:.4f}",
                        "low": f"{price - 0.10:.4f}",
                        "close": f"{close:.4f}",
                        "volume": str(1000 + index),
                        "source": "unit",
                    }
                )
    return path

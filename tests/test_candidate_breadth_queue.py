from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.research.candidate_breadth_queue import (
    CandidateBreadthQueueConfig,
    CandidateBreadthVariantConfig,
    default_candidate_breadth_variants,
    run_bounded_candidate_breadth_queue,
)
from thericher_v2.research.candidate_training import (
    CandidateDataSliceConfig,
    GpuReadiness,
)


def test_candidate_breadth_queue_reuses_training_and_evaluation_primitives(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_breadth_queue as breadth_queue

    training_calls: list[str] = []
    evaluation_calls: list[str] = []
    original_training = breadth_queue.run_bounded_candidate_training
    original_evaluation = breadth_queue.run_bounded_candidate_evaluation

    def spy_training(**kwargs):  # noqa: ANN001
        training_calls.append(kwargs["config"].run_id)
        return original_training(**kwargs)

    def spy_evaluation(**kwargs):  # noqa: ANN001
        evaluation_calls.append(kwargs["config"].run_id)
        return original_evaluation(**kwargs)

    monkeypatch.setattr(breadth_queue, "run_bounded_candidate_training", spy_training)
    monkeypatch.setattr(
        breadth_queue,
        "run_bounded_candidate_evaluation",
        spy_evaluation,
    )

    artifact_root = tmp_path / "model-artifacts"
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    result = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-breadth-queue",
            max_bars=40,
            max_epochs=2,
            max_steps=5,
            variants=(
                _variant("unit-lb3", lookback=3),
                _variant("unit-lb5", lookback=5),
            ),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        data_slices=(
            CandidateDataSliceConfig(
                slice_id="aaa",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
            CandidateDataSliceConfig(
                slice_id="bbb",
                yahoo_snapshot=yahoo_snapshot,
                symbol="BBB",
            ),
        ),
        gpu=_unit_gpu(),
        trainer_runner=_training_runner,
        evaluation_runner=_evaluation_runner,
    )

    payload = json.loads(result.queue_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_breadth_queued_only"
    assert result.variant_count == 2
    assert result.trained_variant_count == 2
    assert result.completed_variant_count == 2
    assert training_calls == [
        "unit-breadth-queue-unit-lb3-training",
        "unit-breadth-queue-unit-lb5-training",
    ]
    assert evaluation_calls == [
        "unit-breadth-queue-unit-lb3-evaluation",
        "unit-breadth-queue-unit-lb5-evaluation",
    ]
    assert payload["selection"]["winner"] is None
    assert payload["selection"]["recommendation"] is None
    assert payload["selection"]["promotion_gate"] is False
    assert payload["max_bars"] == 40
    assert payload["max_epochs"] == 2
    assert payload["max_steps"] == 5
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    for candidate_artifact in payload["artifacts"]["candidates"]:
        path = Path(candidate_artifact)
        assert path.exists()
        assert artifact_root.resolve() in path.resolve().parents
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_breadth_queue(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=GpuReadiness(
                available=False,
                detail="unit",
                checked_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        )


def test_candidate_breadth_queue_defaults_are_capped_to_three() -> None:
    defaults = default_candidate_breadth_variants()

    assert len(defaults) == 3
    assert [item.candidate_experiment_id for item in defaults] == [
        "m1_lb3_b10_s10",
        "m1_lb5_b10_s10",
        "m1_lb8_b10_s10",
    ]
    with pytest.raises(ValueError, match="variants must be <= 3"):
        CandidateBreadthQueueConfig(
            variants=(
                _variant("v1", lookback=1),
                _variant("v2", lookback=2),
                _variant("v3", lookback=3),
                _variant("v4", lookback=4),
            )
        )


def test_candidate_breadth_queue_missing_candidates_are_prepared(tmp_path) -> None:
    result = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-empty-breadth-queue",
            variants=(),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        trainer_runner=_training_runner,
        evaluation_runner=_evaluation_runner,
    )

    payload = json.loads(result.queue_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_breadth_queued"
    assert result.variant_count == 0
    assert payload["reason"] == "no candidate variants evaluated"


def test_candidate_breadth_queue_missing_data_model_gpu_and_backend_are_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    missing_data = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-missing-data-breadth-queue",
            variants=(_variant("unit-lb3", lookback=3),),
        ),
        artifact_root=tmp_path / "model-artifacts-data",
        repo_root=Path.cwd(),
        data_slices=(
            CandidateDataSliceConfig(
                slice_id="missing",
                yahoo_snapshot=tmp_path / "missing.csv.gz",
                symbol="AAA",
            ),
        ),
        gpu=_unit_gpu(),
        trainer_runner=_training_runner,
        evaluation_runner=_evaluation_runner,
    )
    assert missing_data.status == "prepared_not_breadth_queued"
    assert "dataset unavailable" in missing_data.variants[0].training.reason

    missing_model = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-missing-model-breadth-queue",
            variants=(_variant("unit-lb3", lookback=3),),
        ),
        artifact_root=tmp_path / "model-artifacts-model",
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        trainer_runner=lambda dataset, candidate, model_artifact, config: {
            "backend": "unit",
            "examples_seen": len(dataset.labels),
            "candidate_experiment_id": candidate["candidate_experiment_id"],
            "model_artifact": str(model_artifact),
            "max_epochs": config.max_epochs,
        },
        evaluation_runner=_evaluation_runner,
    )
    assert missing_model.status == "prepared_not_breadth_queued"
    assert missing_model.variants[0].training.status == "candidate_trained_only"
    assert missing_model.variants[0].evaluation.reason == "candidate model artifact is missing"

    missing_gpu = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-missing-gpu-breadth-queue",
            variants=(_variant("unit-lb3", lookback=3),),
        ),
        artifact_root=tmp_path / "model-artifacts-gpu",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )
    assert missing_gpu.status == "prepared_not_breadth_queued"
    assert "GPU readiness unavailable" in missing_gpu.variants[0].training.reason

    import thericher_v2.research.candidate_training as candidate_training

    monkeypatch.setattr(
        candidate_training.importlib.util,
        "find_spec",
        lambda _name: None,
    )
    missing_backend = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-missing-backend-breadth-queue",
            variants=(_variant("unit-lb3", lookback=3),),
        ),
        artifact_root=tmp_path / "model-artifacts-backend",
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
    )
    assert missing_backend.status == "prepared_not_breadth_queued"
    assert (
        "no compatible research GPU training backend"
        in missing_backend.variants[0].training.reason
    )


def test_candidate_breadth_queue_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate breadth queue must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate breadth queue must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_breadth_queue(
        config=CandidateBreadthQueueConfig(
            run_id="unit-offline-breadth-queue",
            variants=(_variant("unit-lb3", lookback=3),),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        trainer_runner=_training_runner,
        evaluation_runner=_evaluation_runner,
    )

    assert result.queue_artifact.exists()


def test_candidate_breadth_queue_import_keeps_torch_lazy_and_no_broker_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_breadth_queue as breadth_queue

    source = Path(breadth_queue.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source
    assert "localpaperbroker" not in source
    assert "thericher_v2.execution" not in source


def _variant(variant_id: str, *, lookback: int) -> CandidateBreadthVariantConfig:
    return CandidateBreadthVariantConfig(
        variant_id=variant_id,
        candidate_experiment_id=variant_id,
        candidate_parameters={
            "model_id": "momentum_close_v1",
            "timeframe": "1m",
            "lookback": lookback,
            "buy_threshold_bps": 10,
            "sell_threshold_bps": -10,
        },
    )


def _training_runner(dataset, candidate, model_artifact, config):  # noqa: ANN001
    model_artifact.write_text("unit-model", encoding="utf-8")
    return {
        "backend": "unit",
        "operation": "unit_candidate_training",
        "examples_seen": len(dataset.labels),
        "feature_names": dataset.feature_names,
        "epochs_run": config.max_epochs,
        "steps_run": min(config.max_steps, 1),
        "candidate_experiment_id": candidate["candidate_experiment_id"],
        "model_artifact": str(model_artifact),
    }


def _evaluation_runner(dataset, model, training_payload, _config):  # noqa: ANN001
    return {
        "backend": "unit",
        "operation": "unit_candidate_evaluation",
        "examples_seen": len(dataset.labels),
        "loss": "0.500000",
        "accuracy": "0.500000",
        "mean_probability": "0.500000",
        "predicted_positive_rate": "1.000000",
        "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
        == dataset.feature_names,
        "model_artifact": str(model),
    }


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _yahoo_snapshot(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...],
    bar_count: int = 50,
) -> Path:
    import csv
    import gzip

    path = tmp_path / "ohlcv_1m.csv.gz"
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

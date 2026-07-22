from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_threshold_sweep import (
    CandidateThresholdSweepConfig,
    run_bounded_candidate_threshold_sweep,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_threshold_sweep_writes_trace_and_local_paper_artifacts(
    tmp_path,
) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    comparison_artifact = _comparison_artifact(tmp_path)

    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(
            run_id="unit-threshold-sweep",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    sweep_payload = json.loads(result.sweep_artifact.read_text(encoding="utf-8"))
    trace_payload = json.loads(result.probability_trace_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_swept_only"
    assert sweep_payload["artifact_policy"]["repo_storage_allowed"] is False
    assert trace_payload["artifact_policy"]["repo_storage_allowed"] is False
    assert trace_payload["entries"]
    assert {
        "probability",
        "signal_bar_end",
        "execution_bar_start",
        "execution_open",
    }.issubset(trace_payload["entries"][0])
    assert len(result.variants) == 2
    assert all(variant.replay_fill_count > 0 for variant in result.variants)
    assert all(variant.deltas["comparison_is_descriptive"] for variant in result.variants)
    assert all(variant.deltas["promotion_gate"] is False for variant in result.variants)
    for variant in result.variants:
        assert _fill_sources(Path(variant.events_artifact)) == {LOCAL_PAPER_SOURCE}
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_sweep(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            comparison_artifact=comparison_artifact,
            gpu=_unit_gpu(),
        )


def test_candidate_threshold_sweep_is_deterministic_from_one_trace(tmp_path) -> None:
    seed_root = tmp_path / "seed"
    seed_root.mkdir()
    model_artifact = _model_artifact(seed_root)
    training_artifact = _training_metrics_artifact(seed_root, model_artifact)
    evaluation_artifact = _evaluation_artifact(seed_root, training_artifact, model_artifact)
    comparison_artifact = _comparison_artifact(seed_root)
    seed = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(
            run_id="trace-seed",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
        ),
        artifact_root=seed_root / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    first = _run_from_trace(
        tmp_path / "first",
        seed.probability_trace_artifact,
        comparison_artifact,
    )
    second = _run_from_trace(
        tmp_path / "second",
        seed.probability_trace_artifact,
        comparison_artifact,
    )

    assert first.status == second.status == "candidate_swept_only"
    assert [(v.pnl, v.max_drawdown, v.replay_fill_count) for v in first.variants] == [
        (v.pnl, v.max_drawdown, v.replay_fill_count) for v in second.variants
    ]
    assert [variant.deltas for variant in first.variants] == [
        variant.deltas for variant in second.variants
    ]


def test_candidate_threshold_sweep_records_invalid_threshold_without_failing(
    tmp_path,
) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    comparison_artifact = _comparison_artifact(tmp_path)

    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(
            run_id="invalid-threshold-sweep",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.30, 0.70)),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.status == "candidate_swept_only"
    assert [variant.status for variant in result.variants] == [
        "candidate_replayed_only",
        "prepared_not_replayed",
    ]
    assert "0 < sell < buy < 1" in result.variants[1].reason


def test_candidate_threshold_sweep_missing_trace_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(run_id="missing-trace-sweep"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        probability_trace_artifact=tmp_path / "missing-trace.json",
        comparison_artifact=_comparison_artifact(tmp_path),
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.sweep_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_swept"
    assert "probability trace artifact is missing" in payload["reason"]


def test_candidate_threshold_sweep_missing_model_is_prepared(tmp_path) -> None:
    missing_model = tmp_path / "missing-model.pt"
    training_artifact = _training_metrics_artifact(tmp_path, missing_model)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, missing_model)

    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(run_id="missing-model-threshold-sweep"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=_comparison_artifact(tmp_path),
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.sweep_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_swept"
    assert "model artifact is missing" in payload["reason"]


def test_candidate_threshold_sweep_missing_gpu_is_prepared(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(run_id="missing-gpu-threshold-sweep"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=_comparison_artifact(tmp_path),
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(result.sweep_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_swept"
    assert "GPU readiness unavailable" in payload["reason"]


def test_candidate_threshold_sweep_missing_backend_is_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_threshold_sweep as threshold_sweep

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(threshold_sweep, "_selected_backend", lambda: None)
    monkeypatch.setattr(threshold_sweep, "_available_gpu_backends", lambda: ())

    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(run_id="missing-backend-threshold-sweep"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=_comparison_artifact(tmp_path),
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.sweep_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_swept"
    assert "no compatible research GPU probability backend" in payload["reason"]


def test_candidate_threshold_sweep_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("threshold sweep must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("threshold sweep must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(
            run_id="offline-threshold-sweep",
            max_bars=40,
            threshold_pairs=((0.70, 0.30),),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        comparison_artifact=_comparison_artifact(tmp_path),
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.sweep_artifact.exists()


def test_candidate_threshold_sweep_import_keeps_torch_lazy_and_no_kis_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_threshold_sweep as threshold_sweep

    source = Path(threshold_sweep.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source


def _run_from_trace(root: Path, trace_artifact: Path, comparison_artifact: Path):
    root.mkdir(parents=True, exist_ok=True)
    return run_bounded_candidate_threshold_sweep(
        config=CandidateThresholdSweepConfig(
            run_id="from-trace-threshold-sweep",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
        ),
        artifact_root=root / "model-artifacts",
        repo_root=Path.cwd(),
        probability_trace_artifact=trace_artifact,
        comparison_artifact=comparison_artifact,
        gpu=GpuReadiness(
            available=False,
            detail="not needed when consuming probability trace",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )


def _alternating_probability_runner(dataset, model_artifact, training_payload):  # noqa: ANN001
    assert model_artifact.exists()
    assert tuple(training_payload["metrics"]["feature_names"]) == dataset.feature_names
    probabilities = tuple(
        0.80 if index % 4 in {0, 1} else 0.20
        for index in range(len(dataset.labels))
    )
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": probabilities,
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "candidate_experiment_id": training_payload["candidate_experiment_id"],
    }


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _model_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "external-model.pt"
    path.write_text("unit-model", encoding="utf-8")
    return path


def _training_metrics_artifact(tmp_path: Path, model_artifact: Path) -> Path:
    path = tmp_path / "training-metrics.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
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
        ),
        encoding="utf-8",
    )
    return path


def _evaluation_artifact(
    tmp_path: Path,
    training_artifact: Path,
    model_artifact: Path,
) -> Path:
    path = tmp_path / "evaluation-metrics.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "training_metrics_artifact": str(training_artifact),
                "model_artifact": str(model_artifact),
                "artifacts": {
                    "source_model": str(model_artifact),
                },
                "metrics": {
                    "feature_names": [
                        "lookback_return",
                        "last_bar_return",
                        "bar_range",
                        "volume_change",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _comparison_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "comparison.json"
    path.write_text(
        json.dumps(
            {
                "status": "candidate_compared_only",
                "baseline_metrics": {
                    "pnl": "-1",
                    "max_drawdown": "2",
                    "equity": "9999",
                    "final_position": "1",
                    "trade_count": 2,
                    "replay_fill_count": 2,
                    "event_count": 6,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _fill_sources(path: Path) -> set[str]:
    return {
        json.loads(line)["payload"]["source"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "fill"
    }

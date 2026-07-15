from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data import SampleBarProvider
from thericher_v2.research.candidate_training import (
    CandidateTrainingConfig,
    GpuReadiness,
    build_candidate_training_dataset,
    run_bounded_candidate_training,
)


def test_candidate_training_builds_dataset_from_sample_bars() -> None:
    bars = list(SampleBarProvider.trending_1m(count=20, seed=31).base_bars)

    dataset = build_candidate_training_dataset(
        bars,
        lookback=3,
        data_source="deterministic_sample",
    )

    assert dataset.symbol == "AAPL"
    assert dataset.market == "US"
    assert dataset.bars_seen == 20
    assert len(dataset.features) == len(dataset.labels) == 16
    assert dataset.feature_names == (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
    )


def test_candidate_training_records_injected_success_and_model_artifact_outside_repo(
    tmp_path,
) -> None:
    def runner(dataset, candidate, model_artifact, config):  # noqa: ANN001
        model_artifact.write_text("unit-model", encoding="utf-8")
        return {
            "backend": "unit",
            "operation": "unit_candidate_training",
            "examples_seen": len(dataset.labels),
            "epochs_run": config.max_epochs,
            "steps_run": 1,
            "candidate_experiment_id": candidate["candidate_experiment_id"],
            "model_artifact": str(model_artifact),
        }

    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(run_id="unit-candidate-training"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_trained_only"
    assert result.model_artifact is not None
    assert result.model_artifact.exists()
    assert payload["status"] == "candidate_trained_only"
    assert payload["candidate_experiment_id"] == "unit_candidate"
    assert payload["metrics"]["backend"] == "unit"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_training(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=GpuReadiness(
                available=False,
                detail="unit",
                checked_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        )


def test_candidate_training_missing_gpu_is_prepared_not_trained(tmp_path) -> None:
    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(run_id="missing-gpu-candidate-training"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_trained"
    assert result.model_artifact is None
    assert payload["artifacts"]["model"] is None
    assert "GPU readiness unavailable" in payload["reason"]


def test_candidate_training_config_rejects_unbounded_caps() -> None:
    with pytest.raises(ValueError, match="max_epochs"):
        CandidateTrainingConfig(max_epochs=21)
    with pytest.raises(ValueError, match="max_steps"):
        CandidateTrainingConfig(max_steps=1025)
    with pytest.raises(ValueError, match="max_bars"):
        CandidateTrainingConfig(max_bars=513)


def test_candidate_training_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate training must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate training must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(run_id="offline-candidate-training"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=_offline_runner,
    )

    assert result.metrics_artifact.exists()


def test_candidate_training_import_keeps_torch_lazy() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_training as candidate_training

    source = Path(candidate_training.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "thericher_v2.execution" not in source
    assert "localpaperbroker" not in source
    assert "kis" not in source


def _candidate_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _offline_runner(dataset, candidate, model_artifact, _config):  # noqa: ANN001
    model_artifact.write_text("unit-model", encoding="utf-8")
    return {
        "backend": "unit",
        "examples_seen": len(dataset.labels),
        "candidate_experiment_id": candidate["candidate_experiment_id"],
        "model_artifact": str(model_artifact),
    }

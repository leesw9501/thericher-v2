from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.jobs import (
    ResearchJobSpec,
    run_and_write_research_job,
)
from thericher_v2.research.validation import GpuReadiness


def test_research_job_runs_injected_training_and_writes_artifacts_outside_repo(
    tmp_path,
) -> None:
    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-research-job",
            candidate_artifact=_candidate_artifact(tmp_path),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=lambda candidate: {
            "backend": "unit",
            "operation": "tiny_training_step",
            "initial_loss": "2.000000",
            "final_loss": "1.000000",
            "candidate_experiment_id": candidate["candidate_experiment_id"],
        },
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["status"] == "completed"
    assert payload["candidate_experiment_id"] == "unit_candidate"
    assert payload["training"]["status"] == "training_ran_only"
    assert Path(payload["artifacts"]["training_smoke"]).exists()
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_and_write_research_job(
            ResearchJobSpec(job_id="bad-repo-job"),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=GpuReadiness(
                available=False,
                detail="unit",
                checked_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        )


def test_research_job_missing_gpu_is_prepared_not_trained(tmp_path) -> None:
    run = run_and_write_research_job(
        ResearchJobSpec(job_id="missing-gpu-job"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "prepared_not_trained"
    assert payload["status"] == "prepared_not_trained"
    assert payload["training"]["status"] == "prepared_not_trained"
    assert "GPU readiness unavailable" in payload["reason"]


def test_research_job_runs_candidate_training_kind_with_injected_runner(tmp_path) -> None:
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

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-training-job",
            kind="candidate_training",
            candidate_artifact=_candidate_artifact(tmp_path),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_trainer_runner=runner,
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["status"] == "completed"
    assert payload["kind"] == "candidate_training"
    assert payload["candidate_training"]["status"] == "candidate_trained_only"
    assert payload["candidate_training"]["metrics"]["backend"] == "unit"
    assert Path(payload["artifacts"]["candidate_metrics"]).exists()
    assert Path(payload["artifacts"]["model"]).exists()


def test_research_job_runs_candidate_evaluation_kind_with_injected_runner(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-evaluation-job",
            kind="candidate_evaluation",
            training_metrics_artifact=_training_metrics_artifact(tmp_path, model_artifact),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_evaluation_runner=lambda dataset, model, training_payload, _config: {
            "backend": "unit",
            "operation": "unit_candidate_evaluation",
            "examples_seen": len(dataset.labels),
            "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
            == dataset.feature_names,
            "model_artifact": str(model),
        },
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["status"] == "completed"
    assert payload["kind"] == "candidate_evaluation"
    assert payload["candidate_evaluation"]["status"] == "candidate_evaluated_only"
    assert payload["candidate_evaluation"]["metrics"]["backend"] == "unit"
    assert payload["candidate_evaluation"]["local_paper_conversion"] == "deferred_to_next_goal"
    assert Path(payload["artifacts"]["candidate_evaluation"]).exists()
    assert Path(payload["artifacts"]["source_model"]).exists()


def test_research_job_runs_candidate_replay_kind_with_injected_runner(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-replay-job",
            kind="candidate_replay",
            training_metrics_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            buy_threshold=0.70,
            sell_threshold=0.30,
            max_bars=40,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_probability_runner=lambda dataset, model, training_payload: {
            "backend": "unit",
            "operation": "unit_candidate_probabilities",
            "probabilities": tuple(
                0.80 if index % 4 in {0, 1} else 0.20
                for index in range(len(dataset.labels))
            ),
            "feature_names": dataset.feature_names,
            "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
            == dataset.feature_names,
            "model_artifact": str(model),
        },
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["status"] == "completed"
    assert payload["kind"] == "candidate_replay"
    assert payload["candidate_replay"]["status"] == "candidate_replayed_only"
    assert payload["candidate_replay"]["replay_fill_count"] > 0
    assert Path(payload["artifacts"]["candidate_replay"]).exists()
    assert Path(payload["artifacts"]["source_model"]).exists()


def test_research_job_runs_candidate_replay_comparison_kind_with_injected_runner(
    tmp_path,
) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-comparison-job",
            kind="candidate_replay_comparison",
            training_metrics_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            buy_threshold=0.70,
            sell_threshold=0.30,
            max_bars=40,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_probability_runner=lambda dataset, model, training_payload: {
            "backend": "unit",
            "operation": "unit_candidate_probabilities",
            "probabilities": tuple(
                0.80 if index % 4 in {0, 1} else 0.20
                for index in range(len(dataset.labels))
            ),
            "feature_names": dataset.feature_names,
            "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
            == dataset.feature_names,
            "model_artifact": str(model),
        },
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["status"] == "completed"
    assert payload["kind"] == "candidate_replay_comparison"
    comparison = payload["candidate_replay_comparison"]
    assert comparison["status"] == "candidate_compared_only"
    assert comparison["candidate_metrics"]["replay_fill_count"] > 0
    assert comparison["baseline_metrics"]["replay_fill_count"] > 0
    assert comparison["deltas"]["comparison_is_descriptive"] is True
    assert comparison["deltas"]["promotion_gate"] is False
    assert Path(payload["artifacts"]["candidate_replay_comparison"]).exists()
    assert Path(payload["artifacts"]["candidate_replay"]).exists()
    assert Path(payload["artifacts"]["baseline_events"]).exists()


def test_research_job_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unsupported research job kind"):
        ResearchJobSpec(kind="not-a-real-job")  # type: ignore[arg-type]


def test_research_job_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("research job runner must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("research job runner must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="offline-research-job",
            candidate_artifact=_candidate_artifact(tmp_path),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=lambda candidate: {
            "backend": "unit",
            "candidate_experiment_id": candidate["candidate_experiment_id"],
        },
    )

    assert run.job_artifact.exists()


def test_research_job_does_not_import_broker_or_torch_on_base_path() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.jobs as jobs

    source = Path(jobs.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source
    assert "localpaperbroker" not in source
    assert "thericher_v2.execution" not in source


def test_research_job_keeps_torch_research_container_only() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    stages = _dockerfile_stages(dockerfile)
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    base_dependencies = pyproject.split("[project.optional-dependencies]", maxsplit=1)[0]

    assert "torch" not in base_dependencies
    assert "torch==" not in stages["base"].lower()
    assert "torch==" in stages["research"].lower()
    assert "torch==" not in stages["runtime"].lower()


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


def _dockerfile_stages(dockerfile: str) -> dict[str, str]:
    stages: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    for line in dockerfile.splitlines():
        lower = line.lower()
        if lower.startswith("from "):
            if current_name is not None:
                stages[current_name] = "\n".join(current_lines)
            current_lines = [line]
            current_name = lower.rsplit(" as ", maxsplit=1)[-1].strip()
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        stages[current_name] = "\n".join(current_lines)
    return stages

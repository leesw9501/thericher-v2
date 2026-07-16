from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessSliceConfig,
)
from thericher_v2.research.candidate_training import CandidateDataSliceConfig
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
            "feature_names": dataset.feature_names,
            "epochs_run": config.max_epochs,
            "steps_run": 1,
            "hidden_units": config.hidden_units,
            "candidate_experiment_id": candidate["candidate_experiment_id"],
            "model_artifact": str(model_artifact),
        }

    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-training-job",
            kind="candidate_training",
            candidate_artifact=_candidate_artifact(tmp_path),
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
            max_bars=40,
            candidate_hidden_units=12,
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
    assert payload["candidate_training"]["hidden_units"] == 12
    assert payload["candidate_training"]["model_axis"]["hidden_units"] == 12
    assert payload["candidate_training"]["metrics"]["backend"] == "unit"
    assert payload["candidate_training"]["metrics"]["hidden_units"] == 12
    assert payload["candidate_training"]["source_slices"][0]["slice_id"] == "aaa"
    assert Path(payload["artifacts"]["candidate_metrics"]).exists()
    assert Path(payload["artifacts"]["model"]).exists()


def test_research_job_rejects_hidden_units_outside_training_axis() -> None:
    with pytest.raises(ValueError, match="candidate_hidden_units"):
        ResearchJobSpec(
            job_id="bad-hidden-units-eval",
            kind="candidate_evaluation",
            candidate_hidden_units=12,
        )

    with pytest.raises(ValueError, match="candidate_hidden_units"):
        ResearchJobSpec(
            job_id="bad-hidden-units-cap",
            kind="candidate_training",
            candidate_hidden_units=0,
        )


def test_research_job_runs_candidate_evaluation_kind_with_injected_runner(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-evaluation-job",
            kind="candidate_evaluation",
            training_metrics_artifact=_training_metrics_artifact(
                tmp_path,
                model_artifact,
                source_slices=(
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
            ),
            max_bars=40,
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
    assert payload["candidate_evaluation"]["source_slices"][1]["slice_id"] == "bbb"
    assert payload["candidate_evaluation"]["local_paper_conversion"] == "deferred_to_next_goal"
    assert Path(payload["artifacts"]["candidate_evaluation"]).exists()
    assert Path(payload["artifacts"]["source_model"]).exists()


def test_research_job_runs_candidate_breadth_queue_kind_with_injected_runners(
    tmp_path,
) -> None:
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))

    def trainer(dataset, candidate, model_artifact, config):  # noqa: ANN001
        model_artifact.write_text("unit-model", encoding="utf-8")
        return {
            "backend": "unit",
            "operation": "unit_candidate_training",
            "examples_seen": len(dataset.labels),
            "feature_names": dataset.feature_names,
            "epochs_run": config.max_epochs,
            "steps_run": 1,
            "candidate_experiment_id": candidate["candidate_experiment_id"],
            "model_artifact": str(model_artifact),
        }

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-breadth-queue-job",
            kind="candidate_breadth_queue",
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
            max_bars=40,
            max_epochs=2,
            max_steps=5,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_trainer_runner=trainer,
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
    assert payload["kind"] == "candidate_breadth_queue"
    queue = payload["candidate_breadth_queue"]
    assert queue["status"] == "candidate_breadth_queued_only"
    assert queue["variant_count"] == 3
    assert queue["trained_variant_count"] == 3
    assert queue["completed_variant_count"] == 3
    assert queue["selection"]["winner"] is None
    assert queue["selection"]["promotion_gate"] is False
    assert Path(payload["artifacts"]["candidate_breadth_queue"]).exists()


def test_research_job_runs_candidate_breadth_holdout_kind_with_injected_runner(
    tmp_path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    queue_artifact = _breadth_queue_artifact(artifact_root, variant_id="unit-lb3")
    source_dir = tmp_path / "source"
    holdout_dir = tmp_path / "holdout"
    source_dir.mkdir()
    holdout_dir.mkdir()
    source_snapshot = _yahoo_snapshot(source_dir, symbols=("AAA",))
    holdout_snapshot = _yahoo_snapshot(holdout_dir, symbols=("AAA",))

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="ubh-job",
            kind="candidate_breadth_holdout",
            breadth_queue_artifact=queue_artifact,
            data_slices=(
                CandidateDataSliceConfig(
                    slice_id="src",
                    yahoo_snapshot=source_snapshot,
                    symbol="AAA",
                ),
            ),
            robustness_slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="hold",
                    yahoo_snapshot=holdout_snapshot,
                    symbol="AAA",
                ),
            ),
            max_bars=40,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_probability_runner=_probability_runner,
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_breadth_holdout"
    holdout = payload["candidate_breadth_holdout"]
    assert holdout["status"] == "candidate_breadth_holdout_replayed_only"
    assert holdout["processed_variant_count"] == 1
    assert holdout["completed_variant_count"] == 1
    assert holdout["selection"]["winner"] is None
    assert holdout["metrics"]["all_fills_local_paper"] is True
    assert Path(payload["artifacts"]["candidate_breadth_holdout"]).exists()


def test_research_job_runs_candidate_depth_target_kind_with_injected_runners(
    tmp_path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    queue_artifact = _breadth_queue_artifact(artifact_root, variant_id="unit-lb3")
    source_dir = tmp_path / "source"
    holdout_dir = tmp_path / "holdout"
    source_dir.mkdir()
    holdout_dir.mkdir()
    source_snapshot = _yahoo_snapshot(source_dir, symbols=("AAA",))
    holdout_snapshot = _yahoo_snapshot(holdout_dir, symbols=("AAA",))
    breadth_run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="ubh-source",
            kind="candidate_breadth_holdout",
            breadth_queue_artifact=queue_artifact,
            data_slices=(
                CandidateDataSliceConfig(
                    slice_id="src",
                    yahoo_snapshot=source_snapshot,
                    symbol="AAA",
                ),
            ),
            robustness_slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="hold",
                    yahoo_snapshot=holdout_snapshot,
                    symbol="AAA",
                ),
            ),
            max_bars=40,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_probability_runner=_probability_runner,
    )

    def trainer(dataset, candidate, model_artifact, config):  # noqa: ANN001
        model_artifact.write_text("unit-depth-model", encoding="utf-8")
        return {
            "backend": "unit",
            "operation": "unit_candidate_depth_training",
            "examples_seen": len(dataset.labels),
            "feature_names": dataset.feature_names,
            "epochs_run": config.max_epochs,
            "steps_run": 1,
            "candidate_experiment_id": candidate["candidate_experiment_id"],
            "model_artifact": str(model_artifact),
        }

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="udt-job",
            kind="candidate_depth_target",
            breadth_holdout_artifact=breadth_run.result.training_artifact,
            data_slices=(
                CandidateDataSliceConfig(
                    slice_id="src",
                    yahoo_snapshot=source_snapshot,
                    symbol="AAA",
                ),
            ),
            robustness_slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="hold",
                    yahoo_snapshot=holdout_snapshot,
                    symbol="AAA",
                ),
            ),
            max_bars=45,
            max_epochs=5,
            max_steps=160,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        candidate_trainer_runner=trainer,
        candidate_evaluation_runner=lambda dataset, model, training_payload, _config: {
            "backend": "unit",
            "operation": "unit_candidate_depth_evaluation",
            "examples_seen": len(dataset.labels),
            "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
            == dataset.feature_names,
            "model_artifact": str(model),
        },
        candidate_probability_runner=_probability_runner,
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_depth_target"
    depth = payload["candidate_depth_target"]
    assert depth["status"] == "candidate_depth_target_ran_only"
    assert depth["selected_variant_count"] == 1
    assert depth["selection"]["mode"] == "research_scheduling_only"
    assert depth["selection"]["winner"] is None
    assert depth["selection"]["recommendation"] is None
    assert depth["metrics"]["all_fills_local_paper"] is True
    assert Path(payload["artifacts"]["candidate_depth_target"]).exists()
    assert Path(payload["artifacts"]["candidate_training"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_holdout"]).exists()
    assert Path(payload["artifacts"]["model"]).exists()


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


def test_research_job_runs_candidate_threshold_sweep_kind_with_injected_runner(
    tmp_path,
) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    comparison_artifact = tmp_path / "comparison.json"
    comparison_artifact.write_text(
        json.dumps(
            {
                "baseline_metrics": {
                    "pnl": "-1",
                    "max_drawdown": "2",
                    "equity": "9999",
                    "final_position": "1",
                    "trade_count": 2,
                    "replay_fill_count": 2,
                    "event_count": 6,
                }
            }
        ),
        encoding="utf-8",
    )

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-threshold-sweep-job",
            kind="candidate_threshold_sweep",
            training_metrics_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            comparison_artifact=comparison_artifact,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
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
    assert payload["kind"] == "candidate_threshold_sweep"
    sweep = payload["candidate_threshold_sweep"]
    assert sweep["status"] == "candidate_swept_only"
    assert sweep["completed_variant_count"] == 2
    assert sweep["variants"][0]["replay_fill_count"] > 0
    assert Path(payload["artifacts"]["candidate_threshold_sweep"]).exists()
    assert Path(payload["artifacts"]["candidate_probability_trace"]).exists()
    assert Path(payload["artifacts"]["candidate_replay_comparison"]).exists()


def test_research_job_runs_candidate_threshold_robustness_kind_with_injected_runner(
    tmp_path,
) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    yahoo_snapshot = _yahoo_snapshot(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-candidate-threshold-robustness-job",
            kind="candidate_threshold_robustness",
            training_metrics_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
            robustness_slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="aaa_slice",
                    yahoo_snapshot=yahoo_snapshot,
                    symbol="AAA",
                ),
            ),
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
    assert payload["kind"] == "candidate_threshold_robustness"
    robustness = payload["candidate_threshold_robustness"]
    assert robustness["status"] == "candidate_robustness_replayed_only"
    assert robustness["completed_slice_count"] == 1
    assert robustness["slices"][0]["metrics"]["completed_variant_count"] == 2
    assert Path(payload["artifacts"]["candidate_threshold_robustness"]).exists()
    assert Path(payload["artifacts"]["source_model"]).exists()


def test_research_job_runs_candidate_threshold_calibration_kind_with_injected_runner(
    tmp_path,
) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    yahoo_snapshot = _yahoo_snapshot(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-calib-job",
            kind="candidate_threshold_calibration",
            training_metrics_artifact=training_artifact,
            evaluation_artifact=evaluation_artifact,
            robustness_slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="aaa_slice",
                    yahoo_snapshot=yahoo_snapshot,
                    symbol="AAA",
                ),
            ),
            max_bars=40,
            threshold_pair_cap=2,
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
                0.20 + (0.60 * ((index + 1) / (len(dataset.labels) + 1)))
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
    assert payload["kind"] == "candidate_threshold_calibration"
    calibration = payload["candidate_threshold_calibration"]
    assert calibration["status"] == "candidate_thresholds_calibrated_only"
    assert calibration["ready_trace_count"] == 1
    assert calibration["thresholds"]["derivation"] == "observed_probability_quantiles"
    assert calibration["thresholds"]["threshold_pair_cap"] == 2
    assert len(calibration["thresholds"]["threshold_pairs"]) == 2
    assert calibration["thresholds"]["promotion_gate"] is False
    assert Path(payload["artifacts"]["candidate_threshold_calibration"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_robustness"]).exists()
    assert Path(payload["artifacts"]["source_model"]).exists()


def test_research_job_runs_candidate_threshold_holdout_kind_with_injected_runner(
    tmp_path,
) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    calibration_artifact = _threshold_calibration_artifact(
        tmp_path,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
    )
    yahoo_snapshot = _yahoo_snapshot(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-holdout-job",
            kind="candidate_threshold_holdout",
            calibration_artifact=calibration_artifact,
            robustness_slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="aaa_holdout",
                    yahoo_snapshot=yahoo_snapshot,
                    symbol="AAA",
                ),
            ),
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
    assert payload["kind"] == "candidate_threshold_holdout"
    holdout = payload["candidate_threshold_holdout"]
    assert holdout["status"] == "candidate_threshold_holdout_replayed_only"
    assert holdout["thresholds"]["derivation"] == "source_calibration_artifact_unchanged"
    assert holdout["thresholds"]["promotion_gate"] is False
    assert holdout["local_paper_verification"]["all_fills_local_paper"] is True
    assert Path(payload["artifacts"]["candidate_threshold_holdout"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_robustness"]).exists()
    assert Path(payload["artifacts"]["source_calibration"]).exists()
    assert Path(payload["artifacts"]["source_model"]).exists()


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


def _training_metrics_artifact(
    tmp_path: Path,
    model_artifact: Path,
    *,
    source_slices: tuple[CandidateDataSliceConfig, ...] = (),
) -> Path:
    return _training_metrics_artifact_with_sources(
        tmp_path,
        model_artifact,
        source_slices=source_slices,
    )


def _training_metrics_artifact_with_sources(
    tmp_path: Path,
    model_artifact: Path,
    *,
    source_slices: tuple[CandidateDataSliceConfig, ...] = (),
) -> Path:
    source_slice_payload = [
        {
            "slice_id": data_slice.slice_id,
            "yahoo_snapshot": str(data_slice.yahoo_snapshot),
            "symbol": data_slice.symbol,
            "bars_seen": 40,
            "examples_seen": 36,
        }
        for data_slice in source_slices
    ]
    path = tmp_path / "training-metrics.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "source_slices": source_slice_payload,
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


def _threshold_calibration_artifact(
    tmp_path: Path,
    *,
    training_artifact: Path,
    evaluation_artifact: Path,
    model_artifact: Path,
) -> Path:
    path = tmp_path / "threshold-calibration.json"
    path.write_text(
        json.dumps(
            {
                "status": "candidate_thresholds_calibrated_only",
                "reason": "unit calibration completed",
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "training_metrics_artifact": str(training_artifact),
                "evaluation_artifact": str(evaluation_artifact),
                "model_artifact": str(model_artifact),
                "thresholds": {
                    "derivation": "observed_probability_quantiles",
                    "threshold_pairs": [
                        {
                            "buy_threshold": "0.700000",
                            "sell_threshold": "0.300000",
                        },
                        {
                            "buy_threshold": "0.500000",
                            "sell_threshold": "0.300000",
                        },
                    ],
                    "promotion_gate": False,
                },
                "artifact_policy": {
                    "repo_storage_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _breadth_queue_artifact(artifact_root: Path, *, variant_id: str) -> Path:
    fixture_dir = artifact_root / "breadth-fixtures" / variant_id
    fixture_dir.mkdir(parents=True, exist_ok=True)
    model_artifact = fixture_dir / "model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact = fixture_dir / "training.json"
    evaluation_artifact = fixture_dir / "evaluation.json"
    candidate_parameters = {
        "lookback": 3,
        "timeframe": "1m",
        "model_id": "momentum_close_v1",
    }
    training_artifact.write_text(
        json.dumps(
            {
                "candidate_experiment_id": variant_id,
                "candidate_parameters": candidate_parameters,
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
        ),
        encoding="utf-8",
    )
    evaluation_artifact.write_text(
        json.dumps(
            {
                "candidate_experiment_id": variant_id,
                "candidate_parameters": candidate_parameters,
                "training_metrics_artifact": str(training_artifact),
                "model_artifact": str(model_artifact),
                "artifacts": {
                    "source_model": str(model_artifact),
                },
            }
        ),
        encoding="utf-8",
    )
    queue_artifact = artifact_root / "candidate-breadth-queue" / "unit-queue" / "metrics.json"
    queue_artifact.parent.mkdir(parents=True, exist_ok=True)
    queue_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_breadth_queued_only",
                "reason": "unit queue completed",
                "variant_count": 1,
                "variants": [
                    {
                        "variant_id": variant_id,
                        "status": "variant_evaluated_only",
                        "candidate_experiment_id": variant_id,
                        "candidate_parameters": candidate_parameters,
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
                ],
            }
        ),
        encoding="utf-8",
    )
    return queue_artifact


def _probability_runner(dataset, model, training_payload):  # noqa: ANN001
    values = (0.18, 0.32, 0.49, 0.67, 0.84)
    probabilities = tuple(values[index % len(values)] for index in range(len(dataset.labels)))
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": probabilities,
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "model_artifact": str(model),
        "candidate_experiment_id": training_payload.get("candidate_experiment_id"),
    }


def _yahoo_snapshot(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = ("AAA",),
) -> Path:
    import csv
    import gzip
    from datetime import timedelta

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
            for index in range(50):
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

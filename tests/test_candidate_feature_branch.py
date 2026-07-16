import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.candidate_feature_branch import (
    CandidateFeatureBranchConfig,
    run_bounded_candidate_feature_branch,
)
from thericher_v2.research.candidate_training import (
    CANDIDATE_FEATURE_STANDARDIZATION,
    CORE_PLUS_BAR_POSITION_FEATURE_SET_ID,
    CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
    GpuReadiness,
)
from thericher_v2.research.jobs import ResearchJobSpec, run_and_write_research_job


def test_candidate_feature_branch_trains_and_evaluates_feature_axis(
    tmp_path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    band_artifact = _threshold_band_artifact(artifact_root)

    result = run_bounded_candidate_feature_branch(
        config=CandidateFeatureBranchConfig(
            run_id="unit-feature-branch",
            max_bars=40,
            max_epochs=2,
            max_steps=8,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_band_rerun_artifact=band_artifact,
        gpu=_unit_gpu(),
        trainer_runner=_unit_training_runner,
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.feature_branch_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_feature_branch_evaluated_only"
    assert payload["result_scope"]["mode"] == "research_feature_branch_only"
    assert payload["result_scope"]["descriptive_only"] is True
    assert payload["result_scope"]["promotion_gate"] is False
    assert payload["candidate_parameters"]["feature_set"] == (
        CORE_PLUS_BAR_POSITION_FEATURE_SET_ID
    )
    assert payload["metrics"]["research_feature_branch_only"] is True
    assert payload["metrics"]["threshold_loop_closure_recorded"] is True
    assert payload["metrics"]["feature_names"][-1] == "close_position_in_bar"
    assert payload["metrics"]["probability_evidence"]["min_probability"] == "0.430000"
    assert payload["metrics"]["probability_evidence"]["max_probability"] == "0.470000"
    assert (
        payload["metrics"]["local_paper_context"][
            "source_context_all_fills_local_paper"
        ]
        is True
    )
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.feature_branch_artifact.resolve().parents
    assert result.model_artifact is not None
    assert result.model_artifact.exists()
    rendered = json.dumps(payload).lower()
    assert "winner" not in rendered
    assert "recommendation" not in rendered
    assert "production ready" not in rendered

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_feature_branch(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            threshold_band_rerun_artifact=band_artifact,
            gpu=_unit_gpu(),
        )


def test_candidate_feature_branch_can_target_bar_pressure_axis(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    band_artifact = _threshold_band_artifact(artifact_root)

    result = run_bounded_candidate_feature_branch(
        config=CandidateFeatureBranchConfig(
            run_id="unit-bar-pressure-feature-branch",
            feature_set_id=CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
            max_bars=40,
            max_epochs=2,
            max_steps=8,
            hidden_units=12,
            weight_decay=0.02,
            feature_preprocessing=CANDIDATE_FEATURE_STANDARDIZATION,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_band_rerun_artifact=band_artifact,
        gpu=_unit_gpu(),
        trainer_runner=_unit_training_runner,
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.feature_branch_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_feature_branch_evaluated_only"
    assert payload["feature_set_id"] == CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID
    assert payload["candidate_parameters"]["feature_set"] == (
        CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID
    )
    assert payload["candidate_parameters"]["feature_branch_axis"] == "bar_pressure"
    assert payload["model_axis"]["hidden_units"] == 12
    assert payload["metrics"]["model_axis"]["hidden_units"] == 12
    assert payload["regularization_axis"] == {
        "axis": "weight_decay",
        "weight_decay": 0.02,
        "descriptive_only": True,
        "promotion_gate": False,
    }
    assert payload["feature_preprocessing"] == CANDIDATE_FEATURE_STANDARDIZATION
    assert payload["preprocessing_axis"]["feature_preprocessing"] == (
        CANDIDATE_FEATURE_STANDARDIZATION
    )
    assert payload["feature_normalization"]["mode"] == CANDIDATE_FEATURE_STANDARDIZATION
    assert payload["metrics"]["regularization_axis"]["weight_decay"] == 0.02
    assert payload["metrics"]["preprocessing_axis"]["feature_preprocessing"] == (
        CANDIDATE_FEATURE_STANDARDIZATION
    )
    assert payload["metrics"]["feature_names"][-3:] == [
        "close_position_in_bar",
        "range_expansion",
        "bar_body_return",
    ]


def test_candidate_feature_branch_research_job_dispatch(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    band_artifact = _threshold_band_artifact(artifact_root)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-feature-branch-job",
            kind="candidate_feature_branch",
            threshold_band_rerun_artifact=band_artifact,
            candidate_feature_set=CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
            candidate_hidden_units=12,
            candidate_weight_decay=0.02,
            candidate_feature_preprocessing=CANDIDATE_FEATURE_STANDARDIZATION,
            max_bars=40,
            max_epochs=2,
            max_steps=8,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        candidate_trainer_runner=_unit_training_runner,
        candidate_evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_feature_branch"
    assert payload["status"] == "completed"
    branch = payload["candidate_feature_branch"]
    assert branch["status"] == "candidate_feature_branch_evaluated_only"
    assert branch["feature_set_id"] == CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID
    assert branch["metrics"]["model_axis"]["hidden_units"] == 12
    assert branch["regularization_axis"]["weight_decay"] == 0.02
    assert branch["metrics"]["regularization_axis"]["weight_decay"] == 0.02
    assert branch["preprocessing_axis"]["feature_preprocessing"] == (
        CANDIDATE_FEATURE_STANDARDIZATION
    )
    assert branch["feature_normalization"]["mode"] == CANDIDATE_FEATURE_STANDARDIZATION
    assert branch["metrics"]["preprocessing_axis"]["feature_preprocessing"] == (
        CANDIDATE_FEATURE_STANDARDIZATION
    )
    assert branch["result_scope"]["mode"] == "research_feature_branch_only"
    assert branch["metrics"]["probability_evidence"]["probability_range"] == "0.040000"
    assert Path(payload["artifacts"]["candidate_feature_branch"]).exists()
    assert Path(payload["artifacts"]["candidate_training"]).exists()
    assert Path(payload["artifacts"]["candidate_evaluation"]).exists()
    assert Path(payload["artifacts"]["model"]).exists()
    assert Path(payload["artifacts"]["source_threshold_band_rerun"]).exists()


def test_candidate_feature_branch_missing_context_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_feature_branch(
        config=CandidateFeatureBranchConfig(run_id="missing-context-feature-branch"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        threshold_band_rerun_artifact=tmp_path / "missing-band.json",
        gpu=_unit_gpu(),
        trainer_runner=_unit_training_runner,
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.feature_branch_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_feature_branched"
    assert "candidate threshold band rerun artifact is missing" in result.reason
    assert payload["training_status"] is None
    assert payload["evaluation_status"] is None
    assert payload["metrics"]["training_examples_seen"] == 0


def test_candidate_feature_branch_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("feature branch must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("feature branch must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root = tmp_path / "model-artifacts"
    result = run_bounded_candidate_feature_branch(
        config=CandidateFeatureBranchConfig(
            run_id="offline-feature-branch",
            max_bars=40,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_band_rerun_artifact=_threshold_band_artifact(artifact_root),
        gpu=_unit_gpu(),
        trainer_runner=_unit_training_runner,
        evaluation_runner=_unit_evaluation_runner,
    )

    assert result.status == "candidate_feature_branch_evaluated_only"


def test_candidate_feature_branch_import_keeps_torch_lazy_and_no_broker_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_feature_branch as feature_branch

    source = Path(feature_branch.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source
    assert "broker" not in source
    assert "live" not in source


def _threshold_band_artifact(artifact_root: Path) -> Path:
    path = (
        artifact_root
        / "candidate-threshold-band-rerun"
        / "unit-band"
        / "metrics.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "unit-band",
                "status": "candidate_threshold_band_rerun_replayed_only",
                "candidate_experiment_id": "m1_lb3_b10_s10",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "metrics": {
                    "completed_variant_count": 12,
                    "replay_fill_count_total": 247,
                },
                "local_paper_verification": {
                    "all_fills_local_paper": True,
                    "fill_sources": ["local_paper"],
                },
                "result_scope": {
                    "mode": "research_threshold_band_rerun_only",
                    "descriptive_only": True,
                    "promotion_gate": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _unit_training_runner(dataset, candidate, model_artifact, config):  # noqa: ANN001
    model_artifact.write_text("unit-model", encoding="utf-8")
    return {
        "backend": "unit",
        "operation": "unit_feature_branch_training",
        "examples_seen": len(dataset.labels),
        "epochs_run": config.max_epochs,
        "steps_run": min(config.max_steps, 1),
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "hidden_units": config.hidden_units,
        "weight_decay": config.weight_decay,
        "feature_preprocessing": dataset.feature_preprocessing,
        "feature_normalization": dataset.feature_normalization,
        "candidate_experiment_id": candidate["candidate_experiment_id"],
        "model_artifact": str(model_artifact),
    }


def _unit_evaluation_runner(dataset, model_artifact, training_payload, _config):  # noqa: ANN001
    return {
        "backend": "unit",
        "operation": "unit_feature_branch_evaluation",
        "examples_seen": len(dataset.labels),
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
        == dataset.feature_names,
        "min_probability": "0.430000",
        "max_probability": "0.470000",
        "mean_probability": "0.451000",
        "probability_range": "0.040000",
        "predicted_positive_rate": "0.500000",
        "accuracy": "0.500000",
        "loss": "0.690000",
        "model_artifact": str(model_artifact),
    }

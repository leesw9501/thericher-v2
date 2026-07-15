from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.candidate_evaluation import (
    CandidateEvaluationConfig,
    run_bounded_candidate_evaluation,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_evaluation_records_injected_success_outside_repo(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="unit-candidate-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(tmp_path, model_artifact),
        gpu=_unit_gpu(),
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_evaluated_only"
    assert payload["status"] == "candidate_evaluated_only"
    assert payload["candidate_experiment_id"] == "unit_candidate"
    assert payload["metrics"]["backend"] == "unit"
    assert payload["metrics"]["feature_names_match"] is True
    assert payload["local_paper_conversion"] == "deferred_to_next_goal"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_evaluation(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=_unit_gpu(),
        )


def test_candidate_evaluation_missing_model_is_prepared_not_evaluated(tmp_path) -> None:
    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="missing-model-candidate-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(
            tmp_path,
            tmp_path / "missing-model.pt",
        ),
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_evaluated"
    assert payload["status"] == "prepared_not_evaluated"
    assert "model artifact is missing" in payload["reason"]
    assert payload["artifacts"]["source_model"].endswith("missing-model.pt")


def test_candidate_evaluation_feature_name_mismatch_is_prepared(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="mismatch-candidate-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(
            tmp_path,
            model_artifact,
            feature_names=["wrong_feature"],
        ),
        gpu=_unit_gpu(),
        evaluation_runner=_raising_evaluation_runner,
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_evaluated"
    assert "feature names mismatch" in payload["reason"]


def test_candidate_evaluation_config_rejects_unbounded_caps() -> None:
    with pytest.raises(ValueError, match="max_bars"):
        CandidateEvaluationConfig(max_bars=513)
    with pytest.raises(ValueError, match="probability_threshold"):
        CandidateEvaluationConfig(probability_threshold=1)


def test_candidate_evaluation_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate evaluation must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate evaluation must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="offline-candidate-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(tmp_path, model_artifact),
        gpu=_unit_gpu(),
        evaluation_runner=_unit_evaluation_runner,
    )

    assert result.evaluation_artifact.exists()


def test_candidate_evaluation_import_keeps_torch_lazy_and_no_broker_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_evaluation as candidate_evaluation

    source = Path(candidate_evaluation.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "thericher_v2.execution" not in source
    assert "localpaperbroker" not in source
    assert "kis" not in source


def _training_metrics_artifact(
    tmp_path: Path,
    model_artifact: Path,
    *,
    feature_names: list[str] | None = None,
) -> Path:
    path = tmp_path / f"training-metrics-{len(list(tmp_path.glob('training-metrics-*')))}.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "candidate_artifact": str(tmp_path / "candidate.json"),
                "artifacts": {
                    "model": str(model_artifact),
                },
                "metrics": {
                    "feature_names": feature_names
                    or [
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


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _unit_evaluation_runner(dataset, model_artifact, training_payload, _config):  # noqa: ANN001
    assert model_artifact.exists()
    assert tuple(training_payload["metrics"]["feature_names"]) == dataset.feature_names
    return {
        "backend": "unit",
        "operation": "unit_candidate_evaluation",
        "examples_seen": len(dataset.labels),
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "accuracy": "0.500000",
    }


def _raising_evaluation_runner(*_args: object, **_kwargs: object) -> dict[str, object]:
    raise AssertionError("feature mismatch should stop before evaluation")

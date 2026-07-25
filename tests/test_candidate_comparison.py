from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_comparison import (
    CandidateReplayComparisonConfig,
    run_bounded_candidate_replay_comparison,
)
from thericher_v2.research.candidate_replay import (
    CandidateReplayConfig,
    run_bounded_candidate_replay,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_replay_comparison_records_both_sides_local_paper_only(
    tmp_path,
) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(
            run_id="unit-candidate-comparison",
            max_bars=40,
            buy_threshold=0.70,
            sell_threshold=0.30,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(result.comparison_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_compared_only"
    assert result.candidate_metrics["replay_fill_count"] > 0
    assert result.baseline_metrics["replay_fill_count"] > 0
    assert result.source_alignment["same_bar_evidence"] is True
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["thresholds"]["promotion_gate"] == "false"
    assert payload["deltas"]["comparison_is_descriptive"] is True
    assert payload["deltas"]["promotion_gate"] is False
    assert _fill_sources(result.candidate_replay_artifact.parent / "events.jsonl") == {
        LOCAL_PAPER_SOURCE
    }
    assert _fill_sources(result.baseline_events) == {LOCAL_PAPER_SOURCE}
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_replay_comparison(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=_unit_gpu(),
        )


def test_candidate_replay_comparison_consumes_existing_replay_artifact_deterministically(
    tmp_path,
) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    replay = run_bounded_candidate_replay(
        config=CandidateReplayConfig(
            run_id="unit-existing-replay",
            max_bars=40,
            buy_threshold=0.70,
            sell_threshold=0.30,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    first = _run_consumed_replay_comparison(
        tmp_path / "first",
        replay.replay_artifact,
        training_artifact,
    )
    second = _run_consumed_replay_comparison(
        tmp_path / "second",
        replay.replay_artifact,
        training_artifact,
    )

    assert first.status == second.status == "candidate_compared_only"
    assert first.baseline_metrics["pnl"] == second.baseline_metrics["pnl"]
    assert first.baseline_metrics["max_drawdown"] == second.baseline_metrics["max_drawdown"]
    assert first.deltas == second.deltas


def test_candidate_replay_comparison_missing_replay_artifact_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(run_id="missing-replay-comparison"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_replay_artifact=tmp_path / "missing-replay.json",
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.comparison_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_compared"
    assert "candidate replay artifact is missing" in payload["reason"]


def test_candidate_replay_comparison_missing_model_is_prepared(tmp_path) -> None:
    missing_model = tmp_path / "missing-model.pt"
    training_artifact = _training_metrics_artifact(tmp_path, missing_model)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, missing_model)

    result = run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(run_id="missing-model-comparison"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.comparison_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_compared"
    assert "model artifact is missing" in payload["reason"]


def test_candidate_replay_comparison_missing_gpu_is_prepared(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(run_id="missing-gpu-comparison"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(result.comparison_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_compared"
    assert "GPU readiness unavailable" in payload["reason"]


def test_candidate_replay_comparison_missing_backend_is_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_replay as candidate_replay

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(candidate_replay, "_selected_backend", lambda: None)
    monkeypatch.setattr(candidate_replay, "_available_gpu_backends", lambda: ())

    result = run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(run_id="missing-backend-comparison"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.comparison_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_compared"
    assert "no compatible research GPU replay backend" in payload["reason"]


def test_candidate_replay_comparison_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate comparison must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate comparison must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(
            run_id="offline-candidate-comparison",
            max_bars=40,
            buy_threshold=0.70,
            sell_threshold=0.30,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.comparison_artifact.exists()


def test_candidate_replay_comparison_import_keeps_torch_lazy_and_no_kis_paths(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    import thericher_v2.research.candidate_comparison as candidate_comparison

    source = Path(candidate_comparison.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source


def _run_consumed_replay_comparison(
    root: Path,
    replay_artifact: Path,
    training_artifact: Path,
):
    root.mkdir(parents=True, exist_ok=True)
    return run_bounded_candidate_replay_comparison(
        config=CandidateReplayComparisonConfig(
            run_id="consumed-replay-comparison",
            max_bars=40,
            buy_threshold=0.70,
            sell_threshold=0.30,
        ),
        artifact_root=root / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_replay_artifact=replay_artifact,
        training_metrics_artifact=training_artifact,
        gpu=GpuReadiness(
            available=False,
            detail="not needed when consuming replay artifact",
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


def _fill_sources(path: Path) -> set[str]:
    return {
        json.loads(line)["payload"]["source"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "fill"
    }

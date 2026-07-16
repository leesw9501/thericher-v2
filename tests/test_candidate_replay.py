from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.data import SampleBarProvider
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_replay import (
    CandidateReplayConfig,
    run_bounded_candidate_replay,
)
from thericher_v2.research.candidate_training import (
    CANDIDATE_FEATURE_STANDARDIZATION,
    GpuReadiness,
    apply_feature_normalization,
    build_candidate_training_dataset,
    build_feature_normalization,
)


def test_candidate_replay_records_local_paper_fills_and_artifact_outside_repo(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_replay(
        config=CandidateReplayConfig(
            run_id="unit-candidate-replay",
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

    payload = json.loads(result.replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_replayed_only"
    assert result.replay_fill_count > 0
    assert result.replay_fill_count == len(result.trades)
    assert {trade.source for trade in result.trades} == {LOCAL_PAPER_SOURCE}
    assert payload["status"] == "candidate_replayed_only"
    assert payload["replay_fill_count"] == len(result.trades)
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["thresholds"]["promotion_gate"] == "false"
    events_path = result.replay_artifact.parent / "events.jsonl"
    fill_payloads = [
        json.loads(line)["payload"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "fill"
    ]
    assert fill_payloads
    assert {payload["source"] for payload in fill_payloads} == {LOCAL_PAPER_SOURCE}
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_replay(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=_unit_gpu(),
        )


def test_candidate_replay_is_deterministic_with_injected_runner(tmp_path) -> None:
    first = _run_deterministic_replay(tmp_path / "first")
    second = _run_deterministic_replay(tmp_path / "second")

    assert first.status == second.status == "candidate_replayed_only"
    assert first.pnl == second.pnl
    assert first.max_drawdown == second.max_drawdown
    assert first.replay_fill_count == second.replay_fill_count
    assert [(trade.side, trade.price, trade.fee) for trade in first.trades] == [
        (trade.side, trade.price, trade.fee) for trade in second.trades
    ]
    assert first.replay_final_position == second.replay_final_position


def test_candidate_replay_missing_model_is_prepared_not_replayed(tmp_path) -> None:
    missing_model = tmp_path / "missing-model.pt"
    training_artifact = _training_metrics_artifact(tmp_path, missing_model)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, missing_model)

    result = run_bounded_candidate_replay(
        config=CandidateReplayConfig(run_id="missing-model-candidate-replay"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_replayed"
    assert "model artifact is missing" in payload["reason"]


def test_candidate_replay_missing_gpu_is_prepared_not_replayed(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_replay(
        config=CandidateReplayConfig(run_id="missing-gpu-candidate-replay"),
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

    payload = json.loads(result.replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_replayed"
    assert "GPU readiness unavailable" in payload["reason"]


def test_candidate_replay_missing_backend_is_prepared_not_replayed(monkeypatch, tmp_path) -> None:
    import thericher_v2.research.candidate_replay as candidate_replay

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(candidate_replay, "_selected_backend", lambda: None)
    monkeypatch.setattr(candidate_replay, "_available_gpu_backends", lambda: ())

    result = run_bounded_candidate_replay(
        config=CandidateReplayConfig(run_id="missing-backend-candidate-replay"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_replayed"
    assert "no operator-approved research GPU replay backend" in payload["reason"]


def test_candidate_replay_probability_path_uses_artifact_feature_normalization(
    tmp_path,
) -> None:
    model_artifact = _model_artifact(tmp_path)
    raw_dataset = build_candidate_training_dataset(
        list(SampleBarProvider.trending_1m(count=40, seed=37).base_bars),
        lookback=3,
        data_source="deterministic_sample_replay_seed37",
    )
    feature_normalization = build_feature_normalization(
        raw_dataset,
        feature_preprocessing=CANDIDATE_FEATURE_STANDARDIZATION,
    )
    expected_dataset = apply_feature_normalization(
        raw_dataset,
        feature_normalization=feature_normalization,
    )
    training_artifact = _training_metrics_artifact(
        tmp_path,
        model_artifact,
        feature_normalization=feature_normalization,
    )
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    def runner(dataset, model, training_payload):  # noqa: ANN001
        assert model.exists()
        assert dataset.feature_preprocessing == CANDIDATE_FEATURE_STANDARDIZATION
        assert dataset.features == expected_dataset.features
        assert training_payload["feature_normalization"]["signature"] == (
            feature_normalization["signature"]
        )
        return {
            "backend": "unit",
            "operation": "unit_candidate_probabilities",
            "probabilities": tuple(0.80 for _ in dataset.labels),
            "feature_names": dataset.feature_names,
            "feature_names_match": True,
            "feature_preprocessing": dataset.feature_preprocessing,
            "feature_normalization": dataset.feature_normalization,
            "model_artifact": str(model),
        }

    result = run_bounded_candidate_replay(
        config=CandidateReplayConfig(
            run_id="standardized-candidate-replay",
            max_bars=40,
            buy_threshold=0.70,
            sell_threshold=0.30,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=runner,
    )

    payload = json.loads(result.replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_replayed_only"
    assert payload["probability_metrics"]["feature_preprocessing"] == (
        CANDIDATE_FEATURE_STANDARDIZATION
    )


def test_candidate_replay_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate replay must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate replay must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_replay(
        config=CandidateReplayConfig(run_id="offline-candidate-replay", max_bars=40),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.replay_artifact.exists()


def test_candidate_replay_import_keeps_torch_lazy_and_no_kis_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_replay as candidate_replay

    source = Path(candidate_replay.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source


def _run_deterministic_replay(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    model_artifact = _model_artifact(root)
    training_artifact = _training_metrics_artifact(root, model_artifact)
    evaluation_artifact = _evaluation_artifact(root, training_artifact, model_artifact)
    return run_bounded_candidate_replay(
        config=CandidateReplayConfig(
            run_id="deterministic-candidate-replay",
            max_bars=40,
            buy_threshold=0.70,
            sell_threshold=0.30,
        ),
        artifact_root=root / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
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


def _model_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "external-model.pt"
    path.write_text("unit-model", encoding="utf-8")
    return path


def _training_metrics_artifact(
    tmp_path: Path,
    model_artifact: Path,
    *,
    feature_normalization: dict[str, object] | None = None,
) -> Path:
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
                "feature_preprocessing": "none"
                if feature_normalization is None
                else feature_normalization["mode"],
                "feature_normalization": feature_normalization,
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


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

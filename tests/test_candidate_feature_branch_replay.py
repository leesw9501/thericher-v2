from __future__ import annotations

import csv
import gzip
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_feature_branch_replay import (
    CandidateFeatureBranchReplayConfig,
    derive_feature_branch_replay_threshold_pairs,
    run_bounded_candidate_feature_branch_replay,
)
from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessSliceConfig,
)
from thericher_v2.research.candidate_training import GpuReadiness
from thericher_v2.research.jobs import ResearchJobSpec, run_and_write_research_job


def test_candidate_feature_branch_replay_uses_local_paper_only(tmp_path) -> None:
    artifact_root, feature_branch_artifact, yahoo_snapshot = _feature_branch_artifacts(
        tmp_path
    )

    result = run_bounded_candidate_feature_branch_replay(
        config=CandidateFeatureBranchReplayConfig(
            run_id="unit-feature-branch-replay",
            max_bars=40,
            slices=_slices(yahoo_snapshot),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_artifact=feature_branch_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(result.feature_branch_replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_feature_branch_replayed_only"
    assert result.robustness is not None
    assert payload["result_scope"]["mode"] == "research_feature_branch_replay_only"
    assert payload["result_scope"]["descriptive_only"] is True
    assert payload["result_scope"]["promotion_gate"] is False
    assert payload["threshold_derivation"]["mode"] == "feature_branch_probability_range_probe"
    assert payload["metrics"]["research_feature_branch_replay_only"] is True
    assert payload["metrics"]["replay_fill_count_total"] > 0
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["local_paper_verification"]["all_fills_local_paper"] is True
    assert _fill_sources(result) == {LOCAL_PAPER_SOURCE}
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.feature_branch_replay_artifact.resolve().parents
    rendered = json.dumps(payload).lower()
    assert "winner" not in rendered
    assert "recommendation" not in rendered
    assert "production ready" not in rendered

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_feature_branch_replay(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            feature_branch_artifact=feature_branch_artifact,
            gpu=_unit_gpu(),
        )


def test_candidate_feature_branch_replay_research_job_dispatch(tmp_path) -> None:
    artifact_root, feature_branch_artifact, yahoo_snapshot = _feature_branch_artifacts(
        tmp_path
    )

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-feature-branch-replay-job",
            kind="candidate_feature_branch_replay",
            feature_branch_artifact=feature_branch_artifact,
            max_bars=40,
            threshold_pair_cap=2,
            robustness_slices=_slices(yahoo_snapshot),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        candidate_probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_feature_branch_replay"
    replay = payload["candidate_feature_branch_replay"]
    assert replay["status"] == "candidate_feature_branch_replayed_only"
    assert replay["threshold_derivation"]["threshold_pair_cap"] == 2
    assert replay["metrics"]["threshold_pair_count"] == 2
    assert replay["metrics"]["all_fills_local_paper"] is True
    assert Path(payload["artifacts"]["candidate_feature_branch_replay"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_robustness"]).exists()
    assert Path(payload["artifacts"]["source_feature_branch"]).exists()
    assert Path(payload["artifacts"]["model"]).exists()


def test_candidate_feature_branch_replay_missing_context_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_feature_branch_replay(
        config=CandidateFeatureBranchReplayConfig(run_id="missing-feature-branch-replay"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        feature_branch_artifact=tmp_path / "missing-feature-branch.json",
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(result.feature_branch_replay_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_feature_branch_replayed"
    assert "candidate feature branch artifact is missing" in result.reason
    assert payload["completed_slice_count"] == 0
    assert payload["metrics"]["replay_fill_count_total"] == 0


def test_candidate_feature_branch_replay_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("feature branch replay must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("feature branch replay must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    artifact_root, feature_branch_artifact, yahoo_snapshot = _feature_branch_artifacts(
        tmp_path
    )

    result = run_bounded_candidate_feature_branch_replay(
        config=CandidateFeatureBranchReplayConfig(
            run_id="offline-feature-branch-replay",
            max_bars=40,
            slices=_slices(yahoo_snapshot),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_artifact=feature_branch_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.status == "candidate_feature_branch_replayed_only"


def test_candidate_feature_branch_replay_import_keeps_torch_lazy_and_no_kis_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_feature_branch_replay as replay

    source = Path(replay.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source


def test_derive_feature_branch_replay_threshold_pairs_uses_probability_range() -> None:
    pairs = derive_feature_branch_replay_threshold_pairs(
        {
            "min_probability": "0.171124",
            "mean_probability": "0.457413",
            "max_probability": "0.484606",
        }
    )

    assert pairs == (
        (0.482, 0.457),
        (0.483, 0.457),
        (0.484, 0.457),
    )


def _feature_branch_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
    market_root = tmp_path / "market-data"
    yahoo_snapshot = _yahoo_snapshot(market_root, symbols=("AAA", "BBB"))
    model_artifact = artifact_root / "candidate-training" / "unit-feature" / "model.pt"
    training_artifact = (
        artifact_root / "candidate-training" / "unit-feature" / "metrics.json"
    )
    evaluation_artifact = (
        artifact_root / "candidate-evaluation" / "unit-feature" / "metrics.json"
    )
    feature_branch_artifact = (
        artifact_root / "candidate-feature-branch" / "unit-feature" / "metrics.json"
    )
    feature_names = [
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
        "close_position_in_bar",
    ]
    model_artifact.parent.mkdir(parents=True, exist_ok=True)
    model_artifact.write_text("unit-model", encoding="utf-8")
    _write_json(
        training_artifact,
        {
            "status": "candidate_trained_only",
            "candidate_experiment_id": "m1_lb3_b10_s10__core_plus_bar_position_v1",
            "candidate_parameters": {
                "lookback": 3,
                "timeframe": "1m",
                "feature_set": "core_plus_bar_position_v1",
            },
            "source_slices": [
                {
                    "slice_id": "aaa",
                    "yahoo_snapshot": str(yahoo_snapshot),
                    "symbol": "AAA",
                },
                {
                    "slice_id": "bbb",
                    "yahoo_snapshot": str(yahoo_snapshot),
                    "symbol": "BBB",
                },
            ],
            "artifacts": {"model": str(model_artifact)},
            "metrics": {
                "feature_names": feature_names,
                "model_artifact": str(model_artifact),
            },
        },
    )
    _write_json(
        evaluation_artifact,
        {
            "status": "candidate_evaluated_only",
            "candidate_experiment_id": "m1_lb3_b10_s10__core_plus_bar_position_v1",
            "candidate_parameters": {
                "lookback": 3,
                "timeframe": "1m",
                "feature_set": "core_plus_bar_position_v1",
            },
            "training_metrics_artifact": str(training_artifact),
            "model_artifact": str(model_artifact),
            "metrics": {
                "feature_names": feature_names,
                "min_probability": "0.200000",
                "mean_probability": "0.460000",
                "max_probability": "0.720000",
                "probability_range": "0.520000",
            },
        },
    )
    _write_json(
        feature_branch_artifact,
        {
            "status": "candidate_feature_branch_evaluated_only",
            "candidate_experiment_id": "m1_lb3_b10_s10__core_plus_bar_position_v1",
            "candidate_parameters": {
                "lookback": 3,
                "timeframe": "1m",
                "feature_set": "core_plus_bar_position_v1",
            },
            "metrics": {
                "research_feature_branch_only": True,
                "probability_evidence": {
                    "min_probability": "0.200000",
                    "mean_probability": "0.460000",
                    "max_probability": "0.720000",
                    "probability_range": "0.520000",
                },
            },
            "artifacts": {
                "candidate_training": _app_path(training_artifact, artifact_root),
                "candidate_evaluation": _app_path(evaluation_artifact, artifact_root),
                "model": _app_path(model_artifact, artifact_root),
            },
            "artifact_policy": {
                "root": "/app/model_artifacts",
                "repo_storage_allowed": False,
            },
        },
    )
    return artifact_root, feature_branch_artifact, yahoo_snapshot


def _slices(yahoo_snapshot: Path) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    return (
        CandidateThresholdRobustnessSliceConfig(
            slice_id="aaa",
            yahoo_snapshot=yahoo_snapshot,
            symbol="AAA",
        ),
        CandidateThresholdRobustnessSliceConfig(
            slice_id="bbb",
            yahoo_snapshot=yahoo_snapshot,
            symbol="BBB",
        ),
    )


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _alternating_probability_runner(dataset, model_artifact, training_payload):  # noqa: ANN001
    probabilities = tuple(0.72 if index % 2 == 0 else 0.31 for index in range(len(dataset.labels)))
    return {
        "backend": "unit",
        "operation": "unit_feature_branch_replay_probabilities",
        "probabilities": probabilities,
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "feature_names_match": tuple(training_payload["metrics"]["feature_names"])
        == dataset.feature_names,
        "model_artifact": str(model_artifact),
    }


def _fill_sources(result) -> set[str]:  # noqa: ANN001
    assert result.robustness is not None
    sources: set[str] = set()
    for slice_result in result.robustness.slices:
        for variant in slice_result.variants:
            if variant.events_artifact is None:
                continue
            events = Path(variant.events_artifact).read_text(encoding="utf-8").splitlines()
            for line in events:
                event = json.loads(line)
                if event["event_type"] == "fill":
                    sources.add(event["payload"]["source"])
    return sources


def _yahoo_snapshot(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...],
    bar_count: int = 50,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
        for symbol in symbols:
            for index in range(bar_count):
                timestamp = start + timedelta(minutes=index)
                price = 100 + index * 0.03 + (0.20 if symbol == "BBB" else 0)
                close = price + (0.06 if index % 2 == 0 else -0.04)
                writer.writerow(
                    {
                        "symbol": symbol,
                        "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                        "timestamp_et": "",
                        "session_date": "2026-01-02",
                        "bar_time_et": "",
                        "open": f"{price:.4f}",
                        "high": f"{price + 0.12:.4f}",
                        "low": f"{price - 0.12:.4f}",
                        "close": f"{close:.4f}",
                        "volume": str(1000 + index),
                        "source": "unit",
                    }
                )
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _app_path(path: Path, artifact_root: Path) -> str:
    relative = path.relative_to(artifact_root)
    return "/app/model_artifacts/" + "/".join(relative.parts)

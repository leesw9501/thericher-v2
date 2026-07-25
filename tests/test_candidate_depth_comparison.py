import json
import socket
import sys
from pathlib import Path

import pytest

from thericher_v2.research.candidate_depth_comparison import (
    CandidateDepthComparisonConfig,
    run_bounded_candidate_depth_comparison,
)
from thericher_v2.research.jobs import ResearchJobSpec, run_and_write_research_job


def test_candidate_depth_comparison_reads_external_artifacts_and_selected_only(
    tmp_path,
) -> None:
    artifact_root, depth_artifact, breadth_artifact = _comparison_artifacts(tmp_path)

    result = run_bounded_candidate_depth_comparison(
        config=CandidateDepthComparisonConfig(run_id="unit-depth-compare"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        depth_target_artifact=depth_artifact,
    )

    payload = json.loads(result.comparison_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_depth_compared_only"
    assert result.source_breadth_holdout_artifact == breadth_artifact
    assert result.selected_variant_id == "m1_lb3_b10_s10"
    assert result.selected_variant_count == 1
    assert result.input_variant_count == 2
    assert result.breadth_evidence["variant_id"] == "m1_lb3_b10_s10"
    assert result.depth_evidence["variant_id"] == "m1_lb3_b10_s10"
    assert result.deltas["local_paper_fill_count"] == 15
    assert result.deltas["max_epochs"] == 3
    assert result.deltas["max_steps"] == 128
    assert result.deltas["max_bars"] == 60
    assert payload["selection"]["mode"] == "research_comparison_only"
    assert payload["selection"]["winner"] is None
    assert payload["selection"]["recommendation"] is None
    assert payload["selection"]["promotion_gate"] is False
    assert payload["metrics"]["all_referenced_artifacts_exist"] is True
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.comparison_artifact.resolve().parents

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_depth_comparison(
            config=CandidateDepthComparisonConfig(),
            artifact_root=artifact_root,
            repo_root=Path.cwd(),
            depth_target_artifact=Path.cwd() / "depth.json",
        )


def test_candidate_depth_comparison_research_job_dispatch(tmp_path) -> None:
    artifact_root, depth_artifact, _breadth_artifact = _comparison_artifacts(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="unit-depth-comparison-job",
            kind="candidate_depth_comparison",
            depth_target_artifact=depth_artifact,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_depth_comparison"
    comparison = payload["candidate_depth_comparison"]
    assert comparison["status"] == "candidate_depth_compared_only"
    assert comparison["selected_variant_id"] == "m1_lb3_b10_s10"
    assert comparison["metrics"]["research_comparison_only"] is True
    assert comparison["selection"]["winner"] is None
    assert Path(payload["artifacts"]["candidate_depth_comparison"]).exists()


def test_candidate_depth_comparison_missing_artifacts_are_prepared(tmp_path) -> None:
    missing_depth = run_bounded_candidate_depth_comparison(
        config=CandidateDepthComparisonConfig(run_id="missing-depth"),
        artifact_root=tmp_path / "model-artifacts-missing-depth",
        repo_root=Path.cwd(),
        depth_target_artifact=tmp_path / "missing-depth.json",
    )
    assert missing_depth.status == "prepared_not_depth_compared"
    assert "depth target artifact is missing" in missing_depth.reason

    artifact_root, depth_artifact, breadth_artifact = _comparison_artifacts(tmp_path)
    breadth_artifact.unlink()
    missing_breadth = run_bounded_candidate_depth_comparison(
        config=CandidateDepthComparisonConfig(run_id="missing-breadth"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        depth_target_artifact=depth_artifact,
    )
    assert missing_breadth.status == "prepared_not_depth_compared"
    assert "breadth holdout artifact is missing" in missing_breadth.reason

    artifact_root, depth_artifact, _breadth_artifact = _comparison_artifacts(
        tmp_path / "missing-source"
    )
    source_model = artifact_root / "candidate-training" / "breadth-lb3" / "model.pt"
    source_model.unlink()
    missing_source = run_bounded_candidate_depth_comparison(
        config=CandidateDepthComparisonConfig(run_id="missing-source"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        depth_target_artifact=depth_artifact,
    )
    assert missing_source.status == "prepared_not_depth_compared"
    assert "referenced comparison artifacts are missing" in missing_source.reason
    assert missing_source.artifact_verification["breadth_model"]["exists"] is False


def test_candidate_depth_comparison_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("depth comparison must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("depth comparison must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root, depth_artifact, _breadth_artifact = _comparison_artifacts(tmp_path)
    result = run_bounded_candidate_depth_comparison(
        config=CandidateDepthComparisonConfig(run_id="offline-depth-compare"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        depth_target_artifact=depth_artifact,
    )

    assert result.status == "candidate_depth_compared_only"


def test_candidate_depth_comparison_import_keeps_torch_lazy_and_no_broker_paths(
    monkeypatch,
) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    import thericher_v2.research.candidate_depth_comparison as depth_comparison

    source = Path(depth_comparison.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source
    assert "broker" not in source
    assert "live" not in source


def _comparison_artifacts(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
    breadth_paths = _source_artifacts(artifact_root, family="breadth-lb3")
    depth_paths = _source_artifacts(artifact_root, family="depth-lb3")
    breadth_artifact = (
        artifact_root
        / "candidate-breadth-holdout"
        / "unit-breadth"
        / "metrics.json"
    )
    depth_artifact = artifact_root / "candidate-depth-target" / "unit-depth" / "metrics.json"
    breadth_artifact.parent.mkdir(parents=True, exist_ok=True)
    depth_artifact.parent.mkdir(parents=True, exist_ok=True)
    breadth_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_breadth_holdout_replayed_only",
                "max_bars": 60,
                "variants": [
                    _breadth_variant("m1_lb3_b10_s10", breadth_paths, fills=5),
                    _breadth_variant("m1_lb5_b10_s10", breadth_paths, fills=99),
                ],
            }
        ),
        encoding="utf-8",
    )
    depth_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_depth_target_ran_only",
                "source_breadth_holdout_artifact": _app_path(
                    breadth_artifact,
                    artifact_root,
                ),
                "candidate_experiment_id": "m1_lb3_b10_s10",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "max_bars": 120,
                "max_epochs": 6,
                "max_steps": 192,
                "selection": {
                    "mode": "research_scheduling_only",
                    "selected_variant_id": "m1_lb3_b10_s10",
                    "winner": None,
                    "recommendation": None,
                    "promotion_gate": False,
                },
                "artifacts": {
                    "training_metrics": _app_path(depth_paths["training"], artifact_root),
                    "evaluation": _app_path(depth_paths["evaluation"], artifact_root),
                    "model": _app_path(depth_paths["model"], artifact_root),
                    "calibration": _app_path(depth_paths["calibration"], artifact_root),
                    "holdout": _app_path(depth_paths["holdout"], artifact_root),
                    "robustness": _app_path(depth_paths["robustness"], artifact_root),
                },
                "metrics": {
                    "training_status": "candidate_trained_only",
                    "holdout_status": "candidate_threshold_holdout_replayed_only",
                    "selected_backend": "torch",
                    "bars_seen": 120,
                    "examples_seen": 116,
                    "local_paper_fill_count": 20,
                    "local_paper_verification": {
                        "local_paper_fill_count": 20,
                        "all_fills_local_paper": True,
                    },
                    "pnl_min": "-2.0",
                    "pnl_max": "2.0",
                    "max_drawdown_max": "1.5",
                    "probability_summary": {
                        "source": _probability_summary(count=116, mean="0.52"),
                        "holdout": _probability_summary(count=116, mean="0.51"),
                    },
                    "source_verification": {
                        "source_training_metrics_artifact": _app_path(
                            breadth_paths["training"],
                            artifact_root,
                        ),
                        "source_evaluation_artifact": _app_path(
                            breadth_paths["evaluation"],
                            artifact_root,
                        ),
                        "source_model_artifact": _app_path(
                            breadth_paths["model"],
                            artifact_root,
                        ),
                        "source_calibration_artifact": _app_path(
                            breadth_paths["calibration"],
                            artifact_root,
                        ),
                        "source_holdout_artifact": _app_path(
                            breadth_paths["holdout"],
                            artifact_root,
                        ),
                        "source_robustness_artifact": _app_path(
                            breadth_paths["robustness"],
                            artifact_root,
                        ),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return artifact_root, depth_artifact, breadth_artifact


def _source_artifacts(artifact_root: Path, *, family: str) -> dict[str, Path]:
    directory = artifact_root / "candidate-training" / family
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "training": directory / "metrics.json",
        "evaluation": artifact_root / "candidate-evaluation" / family / "metrics.json",
        "model": directory / "model.pt",
        "calibration": artifact_root
        / "candidate-threshold-calibration"
        / family
        / "metrics.json",
        "holdout": artifact_root / "candidate-threshold-holdout" / family / "metrics.json",
        "robustness": artifact_root
        / "candidate-threshold-robustness"
        / family
        / "metrics.json",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    paths["training"].write_text(
        json.dumps(
            {
                "status": "candidate_trained_only",
                "selected_backend": "torch",
                "max_epochs": 3 if family.startswith("breadth") else 6,
                "max_steps": 64 if family.startswith("breadth") else 192,
                "bars_seen": 60 if family.startswith("breadth") else 120,
                "examples_seen": 56 if family.startswith("breadth") else 116,
                "source_slices": [
                    {
                        "slice_id": family,
                        "symbol": "AAA",
                        "bars_seen": 60 if family.startswith("breadth") else 120,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    paths["calibration"].write_text(
        json.dumps(
            {
                "status": "candidate_thresholds_calibrated_only",
                "probability_summary": _probability_summary(
                    count=56 if family.startswith("breadth") else 116,
                    mean="0.50" if family.startswith("breadth") else "0.52",
                ),
            }
        ),
        encoding="utf-8",
    )
    paths["evaluation"].write_text("{}", encoding="utf-8")
    paths["holdout"].write_text("{}", encoding="utf-8")
    paths["robustness"].write_text("{}", encoding="utf-8")
    paths["model"].write_text("unit-model", encoding="utf-8")
    return paths


def _breadth_variant(
    variant_id: str,
    paths: dict[str, Path],
    *,
    fills: int,
) -> dict[str, object]:
    return {
        "variant_id": variant_id,
        "status": "variant_holdout_replayed_only",
        "candidate_experiment_id": variant_id,
        "candidate_parameters": {
            "lookback": 3,
            "timeframe": "1m",
        },
        "training_metrics_artifact": str(paths["training"]),
        "evaluation_artifact": str(paths["evaluation"]),
        "model_artifact": str(paths["model"]),
        "calibration": {"artifact": str(paths["calibration"])},
        "holdout": {
            "artifact": str(paths["holdout"]),
            "robustness_artifact": str(paths["robustness"]),
        },
        "metrics": {
            "holdout_status": "candidate_threshold_holdout_replayed_only",
            "replay_fill_count_total": fills,
            "local_paper_verification": {
                "local_paper_fill_count": fills,
                "all_fills_local_paper": True,
            },
            "pnl_min": "-1.0",
            "pnl_max": "1.0",
            "max_drawdown_max": "0.5",
            "probability_summary": _probability_summary(count=56, mean="0.49"),
        },
    }


def _probability_summary(*, count: int, mean: str) -> dict[str, str | int]:
    return {
        "count": count,
        "min": "0.10",
        "mean": mean,
        "max": "0.90",
    }


def _app_path(path: Path, artifact_root: Path) -> str:
    relative = path.relative_to(artifact_root)
    return "/app/model_artifacts/" + "/".join(relative.parts)

import csv
import gzip
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_threshold_rerun import (
    CandidateThresholdRerunConfig,
    derive_fill_aware_threshold_pairs,
    run_bounded_candidate_threshold_rerun,
)
from thericher_v2.research.candidate_training import GpuReadiness
from thericher_v2.research.jobs import ResearchJobSpec, run_and_write_research_job


def test_candidate_threshold_rerun_derives_capped_grid_and_reuses_local_paper(
    tmp_path,
) -> None:
    artifact_root, comparison_artifact = _rerun_artifacts(tmp_path)

    result = run_bounded_candidate_threshold_rerun(
        config=CandidateThresholdRerunConfig(run_id="unit-threshold-rerun"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    expected_pairs = derive_fill_aware_threshold_pairs(
        ((0.50, 0.30), (0.70, 0.30)),
        comparison_metrics={
            "local_paper_fill_count_delta": 10,
            "pnl_min_delta": "-1.00",
            "max_drawdown_delta": "0.50",
        },
        cap=4,
    )
    payload = json.loads(result.rerun_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_threshold_rerun_replayed_only"
    assert result.selected_variant_id == "m1_lb3_b10_s10"
    assert result.threshold_pairs == expected_pairs
    assert len(result.threshold_pairs) == 4
    assert result.threshold_schedule["mode"] == "research_threshold_rerun_only"
    assert result.threshold_schedule["winner"] is None
    assert result.threshold_schedule["recommendation"] is None
    assert result.threshold_schedule["promotion_gate"] is False
    assert result.holdout is not None
    assert result.holdout.thresholds["derivation"] == (
        "comparison_informed_threshold_override"
    )
    assert payload["selection"]["mode"] == "research_threshold_rerun_only"
    assert payload["selection"]["winner"] is None
    assert payload["selection"]["recommendation"] is None
    assert payload["selection"]["promotion_gate"] is False
    assert payload["metrics"]["research_threshold_rerun_only"] is True
    assert payload["metrics"]["all_referenced_artifacts_exist"] is True
    assert payload["local_paper_verification"]["all_fills_local_paper"] is True
    assert payload["local_paper_verification"]["local_paper_fill_count"] > 0
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.rerun_artifact.resolve().parents
    assert artifact_root.resolve() in result.holdout_artifact.resolve().parents
    assert _rerun_fill_sources(result) == {LOCAL_PAPER_SOURCE}

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_rerun(
            config=CandidateThresholdRerunConfig(),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            comparison_artifact=comparison_artifact,
            gpu=_unit_gpu(),
        )


def test_candidate_threshold_rerun_research_job_dispatch(tmp_path) -> None:
    artifact_root, comparison_artifact = _rerun_artifacts(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="utrj",
            kind="candidate_threshold_rerun",
            comparison_artifact=comparison_artifact,
            max_bars=40,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        candidate_probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_threshold_rerun"
    assert payload["status"] == "completed"
    rerun = payload["candidate_threshold_rerun"]
    assert rerun["status"] == "candidate_threshold_rerun_replayed_only"
    assert rerun["threshold_schedule"]["mode"] == "research_threshold_rerun_only"
    assert rerun["selection"]["winner"] is None
    assert rerun["metrics"]["all_fills_local_paper"] is True
    assert Path(payload["artifacts"]["candidate_threshold_rerun"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_holdout"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_robustness"]).exists()


def test_candidate_threshold_rerun_missing_artifacts_are_prepared(tmp_path) -> None:
    missing_comparison = run_bounded_candidate_threshold_rerun(
        config=CandidateThresholdRerunConfig(run_id="missing-comparison"),
        artifact_root=tmp_path / "missing-artifacts",
        repo_root=Path.cwd(),
        comparison_artifact=tmp_path / "missing-comparison.json",
        gpu=_unit_gpu(),
    )
    assert missing_comparison.status == "prepared_not_threshold_reran"
    assert "comparison artifact is missing" in missing_comparison.reason

    artifact_root, comparison_artifact = _rerun_artifacts(tmp_path / "missing-model")
    depth_artifact = artifact_root / "candidate-depth-target" / "unit-depth" / "metrics.json"
    depth_payload = json.loads(depth_artifact.read_text(encoding="utf-8"))
    model_artifact = Path(depth_payload["artifacts"]["model"])
    model_artifact.unlink()
    missing_source = run_bounded_candidate_threshold_rerun(
        config=CandidateThresholdRerunConfig(run_id="missing-source"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
    )
    assert missing_source.status == "prepared_not_threshold_reran"
    assert "referenced threshold rerun artifacts are missing" in missing_source.reason
    assert missing_source.artifact_verification["model"]["exists"] is False

    artifact_root, comparison_artifact = _rerun_artifacts(tmp_path / "missing-threshold")
    calibration_artifact = (
        artifact_root
        / "candidate-threshold-calibration"
        / "unit-depth-calibration"
        / "metrics.json"
    )
    calibration_payload = json.loads(calibration_artifact.read_text(encoding="utf-8"))
    calibration_payload["thresholds"]["threshold_pairs"] = []
    calibration_artifact.write_text(json.dumps(calibration_payload), encoding="utf-8")
    missing_thresholds = run_bounded_candidate_threshold_rerun(
        config=CandidateThresholdRerunConfig(run_id="missing-thresholds"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
    )
    assert missing_thresholds.status == "prepared_not_threshold_reran"
    assert "source calibration contains no threshold pairs" in missing_thresholds.reason


def test_candidate_threshold_rerun_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("threshold rerun must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("threshold rerun must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root, comparison_artifact = _rerun_artifacts(tmp_path)
    result = run_bounded_candidate_threshold_rerun(
        config=CandidateThresholdRerunConfig(run_id="offline-rerun"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        comparison_artifact=comparison_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.status == "candidate_threshold_rerun_replayed_only"


def test_candidate_threshold_rerun_import_keeps_torch_lazy_and_no_broker_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_threshold_rerun as rerun

    source = Path(rerun.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source
    assert "broker" not in source
    assert "live" not in source


def _rerun_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
    yahoo_snapshot = _yahoo_snapshot(tmp_path / "market-data")
    model_artifact = artifact_root / "candidate-training" / "unit-depth" / "model.pt"
    training_artifact = (
        artifact_root / "candidate-training" / "unit-depth" / "metrics.json"
    )
    evaluation_artifact = (
        artifact_root / "candidate-evaluation" / "unit-depth" / "metrics.json"
    )
    calibration_artifact = (
        artifact_root
        / "candidate-threshold-calibration"
        / "unit-depth-calibration"
        / "metrics.json"
    )
    holdout_artifact = (
        artifact_root
        / "candidate-threshold-holdout"
        / "unit-depth-holdout"
        / "metrics.json"
    )
    depth_artifact = artifact_root / "candidate-depth-target" / "unit-depth" / "metrics.json"
    comparison_artifact = (
        artifact_root / "candidate-depth-comparison" / "unit-comparison" / "metrics.json"
    )
    for path in (
        model_artifact,
        training_artifact,
        evaluation_artifact,
        calibration_artifact,
        holdout_artifact,
        depth_artifact,
        comparison_artifact,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    model_artifact.write_text("unit-model", encoding="utf-8")
    training_artifact.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "m1_lb3_b10_s10",
                "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
                "artifacts": {"model": str(model_artifact)},
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
                "candidate_experiment_id": "m1_lb3_b10_s10",
                "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
                "training_metrics_artifact": str(training_artifact),
                "model_artifact": str(model_artifact),
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
    calibration_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_thresholds_calibrated_only",
                "candidate_experiment_id": "m1_lb3_b10_s10",
                "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
                "training_metrics_artifact": str(training_artifact),
                "evaluation_artifact": str(evaluation_artifact),
                "model_artifact": str(model_artifact),
                "thresholds": {
                    "derivation": "observed_probability_quantiles",
                    "threshold_pairs": [
                        {"buy_threshold": "0.500000", "sell_threshold": "0.300000"},
                        {"buy_threshold": "0.700000", "sell_threshold": "0.300000"},
                    ],
                    "promotion_gate": False,
                },
            }
        ),
        encoding="utf-8",
    )
    holdout_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_threshold_holdout_replayed_only",
                "holdout_slices": [
                    {
                        "slice_id": "aaa_holdout",
                        "symbol": "AAA",
                        "yahoo_snapshot": str(yahoo_snapshot),
                    }
                ],
                "local_paper_verification": {
                    "all_fills_local_paper": True,
                    "local_paper_fill_count": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    depth_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_depth_target_ran_only",
                "candidate_experiment_id": "m1_lb3_b10_s10",
                "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
                "selection": {
                    "selected_variant_id": "m1_lb3_b10_s10",
                    "mode": "research_scheduling_only",
                    "promotion_gate": False,
                },
                "artifacts": {
                    "training_metrics": str(training_artifact),
                    "evaluation": str(evaluation_artifact),
                    "model": str(model_artifact),
                    "calibration": str(calibration_artifact),
                    "holdout": str(holdout_artifact),
                },
            }
        ),
        encoding="utf-8",
    )
    comparison_artifact.write_text(
        json.dumps(
            {
                "status": "candidate_depth_compared_only",
                "source_depth_target_artifact": _app_path(depth_artifact, artifact_root),
                "selected_variant_id": "m1_lb3_b10_s10",
                "metrics": {
                    "research_comparison_only": True,
                    "local_paper_fill_count_delta": 10,
                    "pnl_min_delta": "-1.00",
                    "max_drawdown_delta": "0.50",
                    "all_fills_local_paper": True,
                    "promotion_gate": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return artifact_root, comparison_artifact


def _alternating_probability_runner(dataset, model_artifact, training_payload):  # noqa: ANN001
    assert model_artifact.exists()
    assert tuple(training_payload["metrics"]["feature_names"]) == dataset.feature_names
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": tuple(
            0.80 if index % 4 in {0, 1} else 0.20
            for index in range(len(dataset.labels))
        ),
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


def _yahoo_snapshot(tmp_path: Path, *, bar_count: int = 50) -> Path:
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
        for index in range(bar_count):
            timestamp = start + timedelta(minutes=index)
            price = 100 + index * 0.02
            close = price + (0.05 if index % 2 == 0 else -0.03)
            writer.writerow(
                {
                    "symbol": "AAA",
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


def _rerun_fill_sources(result) -> set[str]:  # noqa: ANN001
    assert result.holdout is not None
    assert result.holdout.robustness is not None
    sources: set[str] = set()
    for slice_result in result.holdout.robustness.slices:
        for variant in slice_result.variants:
            if variant.events_artifact is None:
                continue
            events = Path(variant.events_artifact).read_text(encoding="utf-8").splitlines()
            for line in events:
                event = json.loads(line)
                if event["event_type"] == "fill":
                    sources.add(event["payload"]["source"])
    return sources


def _app_path(path: Path, artifact_root: Path) -> str:
    relative = path.relative_to(artifact_root)
    return "/app/model_artifacts/" + "/".join(relative.parts)

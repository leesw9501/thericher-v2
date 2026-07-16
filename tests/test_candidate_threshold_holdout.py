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
from thericher_v2.research.candidate_threshold_holdout import (
    CandidateThresholdHoldoutConfig,
    run_bounded_candidate_threshold_holdout,
)
from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessSliceConfig,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_threshold_holdout_consumes_calibration_grid_unchanged(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_threshold_holdout as holdout

    calls: list[tuple[tuple[float, float], ...]] = []
    original_run_robustness = holdout.run_bounded_candidate_threshold_robustness

    def spy_run_robustness(**kwargs):  # noqa: ANN001
        calls.append(kwargs["config"].threshold_pairs)
        return original_run_robustness(**kwargs)

    monkeypatch.setattr(
        holdout,
        "run_bounded_candidate_threshold_robustness",
        spy_run_robustness,
    )
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    calibration_artifact = _calibration_artifact(
        tmp_path,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
    )
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))

    result = run_bounded_candidate_threshold_holdout(
        config=CandidateThresholdHoldoutConfig(
            run_id="unit-holdout",
            max_bars=40,
            slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="aaa_holdout",
                    yahoo_snapshot=yahoo_snapshot,
                    symbol="AAA",
                ),
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="bbb_holdout",
                    yahoo_snapshot=yahoo_snapshot,
                    symbol="BBB",
                ),
            ),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=calibration_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(result.holdout_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_threshold_holdout_replayed_only"
    assert result.threshold_pairs == ((0.70, 0.30), (0.50, 0.30))
    assert calls == [((0.70, 0.30), (0.50, 0.30))]
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["thresholds"]["derivation"] == "source_calibration_artifact_unchanged"
    assert payload["thresholds"]["promotion_gate"] is False
    assert payload["metrics"]["comparison_is_descriptive"] is True
    assert payload["local_paper_verification"]["all_fills_local_paper"] is True
    assert payload["local_paper_verification"]["local_paper_fill_count"] > 0
    assert result.robustness is not None
    for slice_result in result.robustness.slices:
        for variant in slice_result.variants:
            assert _fill_sources(Path(str(variant.events_artifact))) == {
                LOCAL_PAPER_SOURCE
            }

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_holdout(
            config=CandidateThresholdHoldoutConfig(
                slices=(
                    CandidateThresholdRobustnessSliceConfig(
                        slice_id="bad",
                        yahoo_snapshot=yahoo_snapshot,
                        symbol="AAA",
                    ),
                )
            ),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            calibration_artifact=calibration_artifact,
            gpu=_unit_gpu(),
        )


def test_candidate_threshold_holdout_missing_calibration_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_threshold_holdout(
        config=CandidateThresholdHoldoutConfig(
            run_id="missing-calibration-holdout",
            slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="aaa_holdout",
                    yahoo_snapshot=_yahoo_snapshot(tmp_path),
                    symbol="AAA",
                ),
            ),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=tmp_path / "missing-calibration.json",
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.holdout_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_holdout_replayed"
    assert "calibration artifact is missing" in result.reason
    assert result.robustness is None
    assert payload["artifacts"]["candidate_threshold_robustness"] is None


def test_candidate_threshold_holdout_allows_missing_events_for_zero_fill_variants(
    tmp_path,
) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    calibration_artifact = _calibration_artifact(
        tmp_path,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        threshold_pairs=((0.99, 0.01),),
    )

    result = run_bounded_candidate_threshold_holdout(
        config=_single_slice_config(
            _yahoo_snapshot(tmp_path),
            run_id="zero-fill-holdout",
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=calibration_artifact,
        gpu=_unit_gpu(),
        probability_runner=_middle_probability_runner,
    )

    assert result.status == "candidate_threshold_holdout_replayed_only"
    assert result.local_paper_verification["local_paper_fill_count"] == 0
    assert result.local_paper_verification["unreadable_event_artifacts"] == []
    assert result.local_paper_verification["all_fills_local_paper"] is True
    assert result.robustness is not None
    assert result.robustness.slices[0].variants[0].replay_fill_count == 0


def test_candidate_threshold_holdout_missing_data_records_request(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    calibration_artifact = _calibration_artifact(
        tmp_path,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        threshold_pairs=((0.70, 0.30),),
    )

    result = run_bounded_candidate_threshold_holdout(
        config=CandidateThresholdHoldoutConfig(
            run_id="missing-data-holdout",
            slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="missing_holdout",
                    yahoo_snapshot=tmp_path / "missing.csv.gz",
                    symbol="AAA",
                ),
            ),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=calibration_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(result.holdout_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_holdout_replayed"
    assert result.data_requests
    assert result.data_requests[0]["symbol"] == "AAA"
    assert result.data_requests[0]["timeframe"] == "1m"
    assert "missing" in payload["data_requests"][0]["reason"]


def test_candidate_threshold_holdout_missing_model_gpu_and_backend_are_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    yahoo_snapshot = _yahoo_snapshot(tmp_path)
    missing_model = tmp_path / "missing-model.pt"
    missing_training = _training_metrics_artifact(tmp_path, missing_model)
    missing_evaluation = _evaluation_artifact(tmp_path, missing_training, missing_model)
    missing_model_calibration = _calibration_artifact(
        tmp_path,
        training_artifact=missing_training,
        evaluation_artifact=missing_evaluation,
        model_artifact=missing_model,
        threshold_pairs=((0.70, 0.30),),
    )
    missing_model_result = run_bounded_candidate_threshold_holdout(
        config=_single_slice_config(yahoo_snapshot, run_id="missing-model-holdout"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=missing_model_calibration,
        gpu=_unit_gpu(),
    )
    assert missing_model_result.status == "prepared_not_holdout_replayed"
    assert "model artifact is missing" in missing_model_result.robustness.slices[0].reason

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    calibration_artifact = _calibration_artifact(
        tmp_path,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        threshold_pairs=((0.70, 0.30),),
    )
    missing_gpu_result = run_bounded_candidate_threshold_holdout(
        config=_single_slice_config(yahoo_snapshot, run_id="missing-gpu-holdout"),
        artifact_root=tmp_path / "gpu-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=calibration_artifact,
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )
    assert missing_gpu_result.status == "prepared_not_holdout_replayed"
    assert "GPU readiness unavailable" in missing_gpu_result.robustness.slices[0].reason

    import thericher_v2.research.candidate_threshold_sweep as threshold_sweep

    monkeypatch.setattr(threshold_sweep, "_selected_backend", lambda: None)
    monkeypatch.setattr(threshold_sweep, "_available_gpu_backends", lambda: ())
    missing_backend_result = run_bounded_candidate_threshold_holdout(
        config=_single_slice_config(yahoo_snapshot, run_id="missing-backend-holdout"),
        artifact_root=tmp_path / "backend-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=calibration_artifact,
        gpu=_unit_gpu(),
    )
    assert missing_backend_result.status == "prepared_not_holdout_replayed"
    assert "no operator-approved research GPU probability backend" in (
        missing_backend_result.robustness.slices[0].reason
    )


def test_candidate_threshold_holdout_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("holdout replay must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("holdout replay must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    calibration_artifact = _calibration_artifact(
        tmp_path,
        training_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        model_artifact=model_artifact,
        threshold_pairs=((0.70, 0.30),),
    )
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_threshold_holdout(
        config=_single_slice_config(_yahoo_snapshot(tmp_path), run_id="offline-holdout"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        calibration_artifact=calibration_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.holdout_artifact.exists()


def test_candidate_threshold_holdout_import_keeps_torch_lazy_and_no_kis_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_threshold_holdout as holdout

    source = Path(holdout.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source


def _single_slice_config(
    yahoo_snapshot: Path,
    *,
    run_id: str,
) -> CandidateThresholdHoldoutConfig:
    return CandidateThresholdHoldoutConfig(
        run_id=run_id,
        max_bars=40,
        slices=(
            CandidateThresholdRobustnessSliceConfig(
                slice_id="aaa_holdout",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
        ),
    )


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


def _middle_probability_runner(dataset, model_artifact, training_payload):  # noqa: ANN001
    assert model_artifact.exists()
    assert tuple(training_payload["metrics"]["feature_names"]) == dataset.feature_names
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": tuple(0.50 for _ in range(len(dataset.labels))),
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


def _calibration_artifact(
    tmp_path: Path,
    *,
    training_artifact: Path,
    evaluation_artifact: Path,
    model_artifact: Path,
    threshold_pairs: tuple[tuple[float, float], ...],
) -> Path:
    path = tmp_path / f"calibration-{len(list(tmp_path.glob('calibration-*.json')))}.json"
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
                            "buy_threshold": f"{buy_threshold:.6f}",
                            "sell_threshold": f"{sell_threshold:.6f}",
                        }
                        for buy_threshold, sell_threshold in threshold_pairs
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


def _yahoo_snapshot(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = ("AAA",),
    bar_count: int = 50,
) -> Path:
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
            for index in range(bar_count):
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


def _fill_sources(path: Path) -> set[str]:
    return {
        json.loads(line)["payload"]["source"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "fill"
    }

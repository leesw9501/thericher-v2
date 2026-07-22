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
from thericher_v2.research.candidate_threshold_calibration import (
    CandidateThresholdCalibrationConfig,
    derive_calibration_threshold_pairs,
    run_bounded_candidate_threshold_calibration,
)
from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessSliceConfig,
)
from thericher_v2.research.candidate_threshold_sweep import (
    _probabilities_from_trace_payload,
    _read_trace_artifact,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_threshold_calibration_derives_capped_grid_and_replays_local_paper(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_threshold_calibration as calibration

    calls: list[tuple[tuple[float, float], ...]] = []
    original_run_robustness = calibration.run_bounded_candidate_threshold_robustness

    def spy_run_robustness(**kwargs):  # noqa: ANN001
        calls.append(kwargs["config"].threshold_pairs)
        return original_run_robustness(**kwargs)

    monkeypatch.setattr(
        calibration,
        "run_bounded_candidate_threshold_robustness",
        spy_run_robustness,
    )
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    config = CandidateThresholdCalibrationConfig(
        run_id="unit-threshold-calibration",
        max_bars=40,
        threshold_pair_cap=3,
        slices=(
            CandidateThresholdRobustnessSliceConfig(
                slice_id="aaa_slice",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
            CandidateThresholdRobustnessSliceConfig(
                slice_id="bbb_slice",
                yahoo_snapshot=yahoo_snapshot,
                symbol="BBB",
            ),
        ),
    )

    result = run_bounded_candidate_threshold_calibration(
        config=config,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_calibration_probability_runner,
    )

    trace_probabilities = _trace_probabilities(result.trace_summaries)
    expected_pairs = derive_calibration_threshold_pairs(
        tuple(trace_probabilities),
        cap=config.threshold_pair_cap,
        quantile_pairs=config.quantile_pairs,
    )
    payload = json.loads(result.calibration_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_thresholds_calibrated_only"
    assert result.threshold_pairs == expected_pairs
    assert calls == [expected_pairs]
    assert len(result.threshold_pairs) <= 3
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["thresholds"]["derivation"] == "observed_probability_quantiles"
    assert payload["thresholds"]["promotion_gate"] is False
    assert payload["metrics"]["comparison_is_descriptive"] is True
    assert result.robustness is not None
    assert result.robustness.status == "candidate_robustness_replayed_only"

    fill_sources: set[str] = set()
    fill_count = 0
    for slice_result in result.robustness.slices:
        for variant in slice_result.variants:
            fill_count += variant.replay_fill_count
            fill_sources.update(_fill_sources(Path(str(variant.events_artifact))))
    assert fill_count > 0
    assert fill_sources == {LOCAL_PAPER_SOURCE}

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_calibration(
            config=config,
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=_unit_gpu(),
        )


def test_candidate_threshold_calibration_is_deterministic_from_traces(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    seed_config = CandidateThresholdCalibrationConfig(
        run_id="seed-calib",
        max_bars=40,
        threshold_pair_cap=4,
        slices=(
            CandidateThresholdRobustnessSliceConfig(
                slice_id="aaa_slice",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
            CandidateThresholdRobustnessSliceConfig(
                slice_id="bbb_slice",
                yahoo_snapshot=yahoo_snapshot,
                symbol="BBB",
            ),
        ),
    )
    seed = run_bounded_candidate_threshold_calibration(
        config=seed_config,
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_calibration_probability_runner,
    )

    from_trace = run_bounded_candidate_threshold_calibration(
        config=CandidateThresholdCalibrationConfig(
            run_id="trace-calib",
            max_bars=40,
            threshold_pair_cap=4,
            quantile_pairs=seed_config.quantile_pairs,
            slices=tuple(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id=summary.slice_id,
                    yahoo_snapshot=yahoo_snapshot,
                    symbol=summary.symbol,
                    probability_trace_artifact=summary.probability_trace_artifact,
                )
                for summary in seed.trace_summaries
            ),
        ),
        artifact_root=tmp_path / "trace-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="not needed when consuming traces",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    assert from_trace.status == "candidate_thresholds_calibrated_only"
    assert from_trace.threshold_pairs == seed.threshold_pairs
    assert from_trace.metrics["replay_fill_count_total"] == seed.metrics[
        "replay_fill_count_total"
    ]


def test_candidate_threshold_calibration_missing_trace_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_threshold_calibration(
        config=CandidateThresholdCalibrationConfig(
            run_id="missing-trace-calibration",
            slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="missing",
                    yahoo_snapshot=_yahoo_snapshot(tmp_path),
                    symbol="AAA",
                    probability_trace_artifact=tmp_path / "missing-trace.json",
                ),
            ),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="trace load only",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(result.calibration_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_calibrated"
    assert "no probability trace was ready" in result.reason
    assert "missing" in result.trace_summaries[0].reason
    assert result.robustness is None
    assert payload["artifacts"]["candidate_threshold_robustness"] is None


def test_candidate_threshold_calibration_missing_model_is_prepared(tmp_path) -> None:
    yahoo_snapshot = _yahoo_snapshot(tmp_path)
    missing_model = tmp_path / "missing-model.pt"
    training_artifact = _training_metrics_artifact(tmp_path, missing_model)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, missing_model)

    result = run_bounded_candidate_threshold_calibration(
        config=_single_slice_config(yahoo_snapshot, run_id="missing-model-calibration"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    assert result.status == "prepared_not_calibrated"
    assert "model artifact is missing" in result.trace_summaries[0].reason


def test_candidate_threshold_calibration_missing_gpu_is_prepared(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_threshold_calibration(
        config=_single_slice_config(_yahoo_snapshot(tmp_path), run_id="missing-gpu-calibration"),
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

    assert result.status == "prepared_not_calibrated"
    assert "GPU readiness unavailable" in result.trace_summaries[0].reason


def test_candidate_threshold_calibration_missing_backend_is_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_threshold_sweep as threshold_sweep

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(threshold_sweep, "_selected_backend", lambda: None)
    monkeypatch.setattr(threshold_sweep, "_available_gpu_backends", lambda: ())

    result = run_bounded_candidate_threshold_calibration(
        config=_single_slice_config(
            _yahoo_snapshot(tmp_path),
            run_id="missing-backend-calibration",
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    assert result.status == "prepared_not_calibrated"
    assert "no compatible research GPU probability backend" in result.trace_summaries[
        0
    ].reason


def test_candidate_threshold_calibration_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("calibration must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("calibration must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_threshold_calibration(
        config=_single_slice_config(_yahoo_snapshot(tmp_path), run_id="offline-calibration"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_calibration_probability_runner,
    )

    assert result.calibration_artifact.exists()


def test_candidate_threshold_calibration_import_keeps_torch_lazy_and_no_kis_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_threshold_calibration as calibration

    source = Path(calibration.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source


def test_derive_calibration_threshold_pairs_handles_degenerate_probabilities() -> None:
    assert derive_calibration_threshold_pairs((0.42, 0.42, 0.42)) == ()
    assert derive_calibration_threshold_pairs((0.20, 0.50, 0.80, 0.90), cap=2) == (
        (0.5, 0.2),
        (0.8, 0.2),
    )


def _single_slice_config(
    yahoo_snapshot: Path,
    *,
    run_id: str,
) -> CandidateThresholdCalibrationConfig:
    return CandidateThresholdCalibrationConfig(
        run_id=run_id,
        max_bars=40,
        slices=(
            CandidateThresholdRobustnessSliceConfig(
                slice_id="aaa_slice",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
        ),
    )


def _calibration_probability_runner(dataset, model_artifact, training_payload):  # noqa: ANN001
    assert model_artifact.exists()
    assert tuple(training_payload["metrics"]["feature_names"]) == dataset.feature_names
    pattern = (0.459, 0.462, 0.466, 0.464, 0.461, 0.458)
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": tuple(
            pattern[index % len(pattern)] for index in range(len(dataset.labels))
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


def _trace_probabilities(summaries) -> list[float]:  # noqa: ANN001
    probabilities: list[float] = []
    for summary in summaries:
        payload, error = _read_trace_artifact(Path(str(summary.probability_trace_artifact)))
        assert error is None
        probabilities.extend(_probabilities_from_trace_payload(payload))
    return probabilities


def _fill_sources(path: Path) -> set[str]:
    return {
        json.loads(line)["payload"]["source"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "fill"
    }

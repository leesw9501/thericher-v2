from __future__ import annotations

import csv
import gzip
import hashlib
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessConfig,
    CandidateThresholdRobustnessSliceConfig,
    parse_robustness_slices,
    run_bounded_candidate_threshold_robustness,
)
from thericher_v2.research.candidate_training import GpuReadiness


def test_candidate_threshold_robustness_replays_slices_through_sweep_primitive(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_threshold_robustness as robustness

    calls: list[str] = []
    original_run_threshold_variants = robustness._run_threshold_variants

    def spy_run_threshold_variants(**kwargs):  # noqa: ANN001
        calls.append(str(kwargs["output_dir"]))
        return original_run_threshold_variants(**kwargs)

    monkeypatch.setattr(robustness, "_run_threshold_variants", spy_run_threshold_variants)
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))

    result = run_bounded_candidate_threshold_robustness(
        config=CandidateThresholdRobustnessConfig(
            run_id="unit-threshold-robustness",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
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
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    payload = json.loads(result.robustness_artifact.read_text(encoding="utf-8"))
    assert calls == [
        str(result.robustness_artifact.parent / "slices" / "aaa_slice"),
        str(result.robustness_artifact.parent / "slices" / "bbb_slice"),
    ]
    assert result.status == "candidate_robustness_replayed_only"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert payload["thresholds"]["promotion_gate"] is False
    assert payload["completed_slice_count"] == 2
    assert payload["metrics"]["comparison_is_descriptive"] is True
    for slice_result in result.slices:
        assert slice_result.status == "slice_replayed_only"
        assert slice_result.metrics["completed_variant_count"] == 2
        for variant in slice_result.variants:
            assert variant.replay_fill_count > 0
            assert _fill_sources(Path(variant.events_artifact)) == {LOCAL_PAPER_SOURCE}
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_robustness(
            config=CandidateThresholdRobustnessConfig(
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
            gpu=_unit_gpu(),
        )


def test_candidate_threshold_robustness_is_deterministic_from_traces(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    seed = run_bounded_candidate_threshold_robustness(
        config=CandidateThresholdRobustnessConfig(
            run_id="seed-threshold-robustness",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
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
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    from_trace = run_bounded_candidate_threshold_robustness(
        config=CandidateThresholdRobustnessConfig(
            run_id="from-trace-threshold-robustness",
            max_bars=40,
            threshold_pairs=((0.70, 0.30), (0.50, 0.30)),
            slices=tuple(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id=item.slice_id,
                    yahoo_snapshot=yahoo_snapshot,
                    symbol=str(item.symbol),
                    probability_trace_artifact=item.probability_trace_artifact,
                )
                for item in seed.slices
            ),
        ),
        artifact_root=tmp_path / "trace-model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="not needed when consuming traces",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    assert from_trace.status == "candidate_robustness_replayed_only"
    assert [
        [
            (variant.pnl, variant.max_drawdown, variant.replay_fill_count)
            for variant in item.variants
        ]
        for item in from_trace.slices
    ] == [
        [
            (variant.pnl, variant.max_drawdown, variant.replay_fill_count)
            for variant in item.variants
        ]
        for item in seed.slices
    ]


def test_candidate_threshold_robustness_missing_data_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_threshold_robustness(
        config=CandidateThresholdRobustnessConfig(
            run_id="missing-data-threshold-robustness",
            slices=(
                CandidateThresholdRobustnessSliceConfig(
                    slice_id="missing",
                    yahoo_snapshot=tmp_path / "missing.csv.gz",
                    symbol="AAA",
                ),
            ),
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.status == "prepared_not_robustness_replayed"
    assert result.slices[0].status == "prepared_not_replayed"
    assert "probability trace unavailable" in result.slices[0].reason


def test_candidate_threshold_robustness_without_slices_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_threshold_robustness(
        config=CandidateThresholdRobustnessConfig(run_id="no-slice-robustness"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
    )

    payload = json.loads(result.robustness_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_robustness_replayed"
    assert payload["slice_count"] == 0
    assert payload["reason"] == "no robustness slice replayed"


def test_candidate_threshold_robustness_missing_model_is_prepared(tmp_path) -> None:
    yahoo_snapshot = _yahoo_snapshot(tmp_path)
    missing_model = tmp_path / "missing-model.pt"
    training_artifact = _training_metrics_artifact(tmp_path, missing_model)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, missing_model)

    result = run_bounded_candidate_threshold_robustness(
        config=_single_slice_config(yahoo_snapshot, run_id="missing-model-robustness"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    assert result.status == "prepared_not_robustness_replayed"
    assert "model artifact is missing" in result.slices[0].reason


def test_candidate_threshold_robustness_missing_gpu_is_prepared(tmp_path) -> None:
    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)

    result = run_bounded_candidate_threshold_robustness(
        config=_single_slice_config(
            _yahoo_snapshot(tmp_path),
            run_id="missing-gpu-robustness",
        ),
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

    assert result.status == "prepared_not_robustness_replayed"
    assert "GPU readiness unavailable" in result.slices[0].reason


def test_candidate_threshold_robustness_missing_backend_is_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_threshold_sweep as threshold_sweep

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(threshold_sweep, "_selected_backend", lambda: None)
    monkeypatch.setattr(threshold_sweep, "_available_gpu_backends", lambda: ())

    result = run_bounded_candidate_threshold_robustness(
        config=_single_slice_config(
            _yahoo_snapshot(tmp_path),
            run_id="missing-backend-robustness",
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
    )

    assert result.status == "prepared_not_robustness_replayed"
    assert "no compatible research GPU probability backend" in result.slices[0].reason


def test_candidate_threshold_robustness_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("robustness replay must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("robustness replay must not read credential files")
        return original_read_text(path, *args, **kwargs)

    model_artifact = _model_artifact(tmp_path)
    training_artifact = _training_metrics_artifact(tmp_path, model_artifact)
    evaluation_artifact = _evaluation_artifact(tmp_path, training_artifact, model_artifact)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = run_bounded_candidate_threshold_robustness(
        config=_single_slice_config(_yahoo_snapshot(tmp_path), run_id="offline-robustness"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        evaluation_artifact=evaluation_artifact,
        gpu=_unit_gpu(),
        probability_runner=_alternating_probability_runner,
    )

    assert result.robustness_artifact.exists()


def test_candidate_threshold_robustness_import_keeps_torch_lazy_and_no_kis_paths(
    monkeypatch,
) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    import thericher_v2.research.candidate_threshold_robustness as robustness

    source = Path(robustness.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "kis" not in source


def test_parse_robustness_slices_uses_last_colon_for_windows_paths() -> None:
    slices = parse_robustness_slices(
        [r"cvs=D:\market_data\snapshot\ohlcv_1m.csv.gz:CVS"]
    )

    assert len(slices) == 1
    assert slices[0].slice_id == "cvs"
    assert slices[0].symbol == "CVS"
    assert str(slices[0].yahoo_snapshot).endswith("ohlcv_1m.csv.gz")


def _single_slice_config(
    yahoo_snapshot: Path,
    *,
    run_id: str,
) -> CandidateThresholdRobustnessConfig:
    return CandidateThresholdRobustnessConfig(
        run_id=run_id,
        max_bars=40,
        threshold_pairs=((0.70, 0.30),),
        slices=(
            CandidateThresholdRobustnessSliceConfig(
                slice_id="aaa_slice",
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
    digest = (
        hashlib.sha256(model_artifact.read_bytes()).hexdigest()
        if model_artifact.exists()
        else "0" * 64
    )
    path = tmp_path / "evaluation-metrics.json"
    path.write_text(
        json.dumps(
            {
                "status": "candidate_evaluated_only",
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
                "training_metrics_artifact": str(training_artifact),
                "model_artifact": str(model_artifact),
                "model_artifact_sha256": f"sha256:{digest}",
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


def _fill_sources(path: Path) -> set[str]:
    return {
        json.loads(line)["payload"]["source"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "fill"
    }

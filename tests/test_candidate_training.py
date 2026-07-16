from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import SampleBarProvider
from thericher_v2.research.candidate_training import (
    CANDIDATE_FEATURE_STANDARDIZATION,
    CORE_PLUS_BAR_POSITION_FEATURE_SET_ID,
    CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
    CORE_PLUS_ENTRY_ADVERSE_FEATURE_SET_ID,
    DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
    DEFAULT_CANDIDATE_TRAINING_WEIGHT_DECAY,
    MAX_CANDIDATE_TRAINING_HIDDEN_UNITS,
    MAX_CANDIDATE_TRAINING_WEIGHT_DECAY,
    CandidateDataSliceConfig,
    CandidateTrainingConfig,
    GpuReadiness,
    build_candidate_training_dataset,
    build_multi_slice_candidate_training_dataset,
    parse_candidate_data_slices,
    run_bounded_candidate_training,
)


def test_candidate_training_builds_dataset_from_sample_bars() -> None:
    bars = list(SampleBarProvider.trending_1m(count=20, seed=31).base_bars)

    dataset = build_candidate_training_dataset(
        bars,
        lookback=3,
        data_source="deterministic_sample",
    )

    assert dataset.symbol == "AAPL"
    assert dataset.market == "US"
    assert dataset.bars_seen == 20
    assert len(dataset.features) == len(dataset.labels) == 16
    assert dataset.feature_names == (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
    )
    assert dataset.source_slices == ()
    assert dataset.feature_preprocessing == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    assert dataset.feature_normalization is None


def test_candidate_training_builds_bar_position_feature_branch() -> None:
    bars = list(SampleBarProvider.trending_1m(count=20, seed=31).base_bars)

    dataset = build_candidate_training_dataset(
        bars,
        lookback=3,
        data_source="deterministic_sample",
        feature_set=CORE_PLUS_BAR_POSITION_FEATURE_SET_ID,
    )

    assert dataset.feature_names == (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
        "close_position_in_bar",
    )
    assert len(dataset.features[0]) == 5
    assert all(0 <= row[-1] <= 1 for row in dataset.features)


def test_candidate_training_builds_bar_pressure_feature_branch() -> None:
    bars = list(SampleBarProvider.trending_1m(count=20, seed=31).base_bars)

    dataset = build_candidate_training_dataset(
        bars,
        lookback=3,
        data_source="deterministic_sample",
        feature_set=CORE_PLUS_BAR_PRESSURE_FEATURE_SET_ID,
    )

    assert dataset.feature_names == (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
        "close_position_in_bar",
        "range_expansion",
        "bar_body_return",
    )
    assert len(dataset.features[0]) == 7
    assert all(0 <= row[4] <= 1 for row in dataset.features)
    assert all(isinstance(row[5], float) for row in dataset.features)
    assert all(isinstance(row[6], float) for row in dataset.features)


def test_candidate_training_builds_entry_adverse_feature_branch() -> None:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    bars = [
        _unit_bar("AAA", start, open_="100", high="100.5", low="99.5", close="100.2"),
        _unit_bar(
            "AAA",
            start + timedelta(minutes=1),
            open_="100.2",
            high="100.6",
            low="99.8",
            close="100.1",
        ),
        _unit_bar(
            "AAA",
            start + timedelta(minutes=2),
            open_="100.1",
            high="100.4",
            low="99.0",
            close="99.7",
        ),
        _unit_bar(
            "AAA",
            start + timedelta(minutes=3),
            open_="100",
            high="100",
            low="100",
            close="100",
        ),
        _unit_bar(
            "AAA",
            start + timedelta(minutes=4),
            open_="100",
            high="100.2",
            low="99.7",
            close="99.9",
        ),
    ]

    dataset = build_candidate_training_dataset(
        bars,
        lookback=3,
        data_source="unit",
        feature_set=CORE_PLUS_ENTRY_ADVERSE_FEATURE_SET_ID,
    )

    assert dataset.feature_names == (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
        "close_position_in_bar",
        "range_expansion",
        "bar_body_return",
        "upper_wick_share",
        "low_vs_prior_low_return",
    )
    assert len(dataset.features[0]) == 9
    assert dataset.features[0][7] == 0.0
    assert dataset.features[0][8] == pytest.approx((100 / 99) - 1)


def test_candidate_training_builds_multi_slice_dataset_without_feature_shape_drift(
    tmp_path,
) -> None:
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))

    dataset = build_multi_slice_candidate_training_dataset(
        data_slices=(
            CandidateDataSliceConfig(
                slice_id="aaa",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
            CandidateDataSliceConfig(
                slice_id="bbb",
                yahoo_snapshot=yahoo_snapshot,
                symbol="BBB",
            ),
        ),
        candidate={
            "candidate_experiment_id": "unit_candidate",
            "candidate_parameters": {"lookback": 3},
        },
        max_bars=40,
        data_source="unit_multi_slice",
    )

    assert dataset.symbol == "MULTI"
    assert dataset.market == "US"
    assert dataset.feature_names == (
        "lookback_return",
        "last_bar_return",
        "bar_range",
        "volume_change",
    )
    assert dataset.bars_seen == 80
    assert len(dataset.labels) == 72
    assert [item["slice_id"] for item in dataset.source_slices] == ["aaa", "bbb"]
    assert [item["examples_seen"] for item in dataset.source_slices] == [36, 36]
    assert [item["data_quality"]["bars_seen"] for item in dataset.source_slices] == [40, 40]
    assert all(
        item["data_quality"]["blocks_research"] is False for item in dataset.source_slices
    )
    assert all(
        "incomplete_resample_bucket" in item["data_quality"]["warning_codes"]
        for item in dataset.source_slices
    )


def test_candidate_training_records_injected_success_and_model_artifact_outside_repo(
    tmp_path,
) -> None:
    raw_dataset = build_candidate_training_dataset(
        list(SampleBarProvider.trending_1m(count=120, seed=29).base_bars),
        lookback=3,
        data_source="deterministic_sample",
    )

    def runner(dataset, candidate, model_artifact, config):  # noqa: ANN001
        model_artifact.write_text("unit-model", encoding="utf-8")
        assert dataset.features == raw_dataset.features
        assert dataset.feature_preprocessing == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
        return {
            "backend": "unit",
            "operation": "unit_candidate_training",
            "examples_seen": len(dataset.labels),
            "epochs_run": config.max_epochs,
            "steps_run": 1,
            "hidden_units": config.hidden_units,
            "weight_decay": config.weight_decay,
            "feature_preprocessing": dataset.feature_preprocessing,
            "feature_normalization": dataset.feature_normalization,
            "candidate_experiment_id": candidate["candidate_experiment_id"],
            "model_artifact": str(model_artifact),
        }

    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(
            run_id="unit-candidate-training",
            hidden_units=12,
            weight_decay=0.02,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_trained_only"
    assert result.model_artifact is not None
    assert result.model_artifact.exists()
    assert payload["status"] == "candidate_trained_only"
    assert payload["candidate_experiment_id"] == "unit_candidate"
    assert payload["hidden_units"] == 12
    assert payload["model_axis"] == {
        "axis": "hidden_units",
        "hidden_units": 12,
        "descriptive_only": True,
        "promotion_gate": False,
    }
    assert payload["metrics"]["backend"] == "unit"
    assert payload["metrics"]["hidden_units"] == 12
    assert result.weight_decay == 0.02
    assert payload["weight_decay"] == 0.02
    assert payload["regularization_axis"] == {
        "axis": "weight_decay",
        "weight_decay": 0.02,
        "descriptive_only": True,
        "promotion_gate": False,
    }
    assert payload["feature_preprocessing"] == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    assert payload["preprocessing_axis"] == {
        "axis": "feature_preprocessing",
        "feature_preprocessing": DEFAULT_CANDIDATE_FEATURE_PREPROCESSING,
        "descriptive_only": True,
        "promotion_gate": False,
    }
    assert payload["feature_normalization"]["mode"] == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    assert payload["metrics"]["feature_preprocessing"] == DEFAULT_CANDIDATE_FEATURE_PREPROCESSING
    assert payload["metrics"]["weight_decay"] == 0.02
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_training(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=GpuReadiness(
                available=False,
                detail="unit",
                checked_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        )


def test_candidate_training_standardizes_features_and_records_metadata(tmp_path) -> None:
    def runner(dataset, _candidate, model_artifact, config):  # noqa: ANN001
        model_artifact.write_text("unit-model", encoding="utf-8")
        assert config.feature_preprocessing == CANDIDATE_FEATURE_STANDARDIZATION
        assert dataset.feature_preprocessing == CANDIDATE_FEATURE_STANDARDIZATION
        assert dataset.feature_normalization is not None
        columns = list(zip(*dataset.features, strict=True))
        assert all(abs(sum(column) / len(column)) < 1e-10 for column in columns)
        return {
            "backend": "unit",
            "feature_preprocessing": dataset.feature_preprocessing,
            "feature_normalization": dataset.feature_normalization,
            "feature_names": dataset.feature_names,
            "model_artifact": str(model_artifact),
        }

    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(
            run_id="unit-standardized-candidate-training",
            feature_preprocessing=CANDIDATE_FEATURE_STANDARDIZATION,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_trained_only"
    assert payload["feature_preprocessing"] == CANDIDATE_FEATURE_STANDARDIZATION
    assert payload["preprocessing_axis"]["feature_preprocessing"] == (
        CANDIDATE_FEATURE_STANDARDIZATION
    )
    assert payload["feature_normalization"]["mode"] == CANDIDATE_FEATURE_STANDARDIZATION
    assert payload["feature_normalization"]["signature"]
    assert payload["metrics"]["feature_normalization"]["signature"] == (
        payload["feature_normalization"]["signature"]
    )


def test_candidate_training_records_multi_slice_source_rows(tmp_path) -> None:
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(
            run_id="unit-multi-slice-candidate-training",
            max_bars=40,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        data_slices=(
            CandidateDataSliceConfig(
                slice_id="aaa",
                yahoo_snapshot=yahoo_snapshot,
                symbol="AAA",
            ),
            CandidateDataSliceConfig(
                slice_id="bbb",
                yahoo_snapshot=yahoo_snapshot,
                symbol="BBB",
            ),
        ),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=_offline_runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_trained_only"
    assert payload["symbol"] == "MULTI"
    assert payload["bars_seen"] == 80
    assert payload["examples_seen"] == 72
    assert [item["slice_id"] for item in payload["source_slices"]] == ["aaa", "bbb"]
    assert [item["data_quality"]["bars_seen"] for item in payload["source_slices"]] == [
        40,
        40,
    ]
    assert all(
        item["data_quality"]["blocks_research"] is False
        for item in payload["source_slices"]
    )
    assert payload["artifact_policy"]["repo_storage_allowed"] is False


def test_candidate_training_missing_multi_slice_data_is_prepared(tmp_path) -> None:
    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(run_id="missing-multi-slice-candidate-training"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        data_slices=(
            CandidateDataSliceConfig(
                slice_id="missing",
                yahoo_snapshot=tmp_path / "missing.csv.gz",
                symbol="AAA",
            ),
        ),
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=_offline_runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_trained"
    assert "dataset unavailable" in payload["reason"]
    assert payload["source_slices"][0]["examples_seen"] == 0


def test_candidate_training_missing_gpu_is_prepared_not_trained(tmp_path) -> None:
    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(run_id="missing-gpu-candidate-training"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_trained"
    assert result.model_artifact is None
    assert payload["artifacts"]["model"] is None
    assert "GPU readiness unavailable" in payload["reason"]
    assert payload["weight_decay"] == DEFAULT_CANDIDATE_TRAINING_WEIGHT_DECAY
    assert payload["regularization_axis"]["weight_decay"] == 0.0


def test_candidate_training_config_rejects_unbounded_caps() -> None:
    with pytest.raises(ValueError, match="max_epochs"):
        CandidateTrainingConfig(max_epochs=21)
    with pytest.raises(ValueError, match="max_steps"):
        CandidateTrainingConfig(max_steps=1025)
    with pytest.raises(ValueError, match="max_bars"):
        CandidateTrainingConfig(max_bars=513)
    with pytest.raises(ValueError, match="hidden_units"):
        CandidateTrainingConfig(hidden_units=0)
    with pytest.raises(ValueError, match="hidden_units"):
        CandidateTrainingConfig(hidden_units=MAX_CANDIDATE_TRAINING_HIDDEN_UNITS + 1)
    with pytest.raises(ValueError, match="weight_decay"):
        CandidateTrainingConfig(weight_decay=-0.001)
    with pytest.raises(ValueError, match="weight_decay"):
        CandidateTrainingConfig(weight_decay=MAX_CANDIDATE_TRAINING_WEIGHT_DECAY + 0.001)
    with pytest.raises(ValueError, match="weight_decay"):
        CandidateTrainingConfig(weight_decay=float("nan"))
    with pytest.raises(ValueError, match="weight_decay"):
        CandidateTrainingConfig(weight_decay=float("inf"))
    with pytest.raises(ValueError, match="feature_preprocessing"):
        CandidateTrainingConfig(feature_preprocessing="broad_preprocessing_search")


def test_candidate_training_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate training must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate training must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA",))

    result = run_bounded_candidate_training(
        config=CandidateTrainingConfig(run_id="offline-candidate-training"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        candidate_artifact=_candidate_artifact(tmp_path),
        yahoo_snapshot=yahoo_snapshot,
        symbol="AAA",
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=_offline_runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.metrics_artifact.exists()
    assert payload["source_slices"][0]["data_quality"]["bars_seen"] == 50
    assert payload["source_slices"][0]["data_quality"]["blocks_research"] is False


def test_candidate_training_import_keeps_torch_lazy() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_training as candidate_training

    source = Path(candidate_training.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "thericher_v2.execution" not in source
    assert "localpaperbroker" not in source
    assert "kis" not in source


def test_parse_candidate_data_slices_uses_last_colon_for_windows_paths() -> None:
    slices = parse_candidate_data_slices(
        [r"cvs=D:\market_data\snapshot\ohlcv_1m.csv.gz:CVS"]
    )

    assert len(slices) == 1
    assert slices[0].slice_id == "cvs"
    assert slices[0].symbol == "CVS"
    assert str(slices[0].yahoo_snapshot).endswith("ohlcv_1m.csv.gz")


def _candidate_artifact(tmp_path: Path) -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(
        json.dumps(
            {
                "candidate_experiment_id": "unit_candidate",
                "candidate_parameters": {
                    "lookback": 3,
                    "timeframe": "1m",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _offline_runner(dataset, candidate, model_artifact, _config):  # noqa: ANN001
    model_artifact.write_text("unit-model", encoding="utf-8")
    return {
        "backend": "unit",
        "examples_seen": len(dataset.labels),
        "weight_decay": _config.weight_decay,
        "feature_preprocessing": dataset.feature_preprocessing,
        "candidate_experiment_id": candidate["candidate_experiment_id"],
        "model_artifact": str(model_artifact),
    }


def _yahoo_snapshot(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...],
    bar_count: int = 50,
) -> Path:
    import csv
    import gzip

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


def _unit_bar(
    symbol: str,
    start_ts: datetime,
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.M1,
        start_ts=start_ts,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
    )

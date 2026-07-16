from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data import SampleBarProvider
from thericher_v2.research.candidate_evaluation import (
    CandidateEvaluationConfig,
    run_bounded_candidate_evaluation,
)
from thericher_v2.research.candidate_training import (
    CANDIDATE_FEATURE_STANDARDIZATION,
    CandidateDataSliceConfig,
    GpuReadiness,
    apply_feature_normalization,
    build_candidate_training_dataset,
    build_feature_normalization,
)


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
    assert payload["source_slices"] == []
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_evaluation(
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            gpu=_unit_gpu(),
        )


def test_candidate_evaluation_reuses_training_source_slices(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    training_artifact = _training_metrics_artifact(
        tmp_path,
        model_artifact,
        source_slices=(
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
    )

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(
            run_id="multi-slice-candidate-evaluation",
            max_bars=40,
        ),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=training_artifact,
        gpu=_unit_gpu(),
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_evaluated_only"
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


def test_candidate_evaluation_uses_artifact_feature_normalization(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")
    raw_dataset = build_candidate_training_dataset(
        list(SampleBarProvider.trending_1m(count=120, seed=31).base_bars),
        lookback=3,
        data_source="deterministic_sample_heldout_seed31",
    )
    feature_normalization = build_feature_normalization(
        raw_dataset,
        feature_preprocessing=CANDIDATE_FEATURE_STANDARDIZATION,
    )
    expected_dataset = apply_feature_normalization(
        raw_dataset,
        feature_normalization=feature_normalization,
    )

    def runner(dataset, model, training_payload, _config):  # noqa: ANN001
        assert model.exists()
        assert dataset.feature_preprocessing == CANDIDATE_FEATURE_STANDARDIZATION
        assert dataset.feature_normalization["signature"] == feature_normalization["signature"]
        assert dataset.features == expected_dataset.features
        assert training_payload["feature_normalization"]["signature"] == (
            feature_normalization["signature"]
        )
        return {
            "backend": "unit",
            "feature_names": dataset.feature_names,
            "feature_names_match": True,
            "feature_preprocessing": dataset.feature_preprocessing,
            "feature_normalization": dataset.feature_normalization,
            "model_artifact": str(model),
        }

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="standardized-candidate-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(
            tmp_path,
            model_artifact,
            feature_normalization=feature_normalization,
        ),
        gpu=_unit_gpu(),
        evaluation_runner=runner,
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_evaluated_only"
    assert payload["metrics"]["feature_preprocessing"] == CANDIDATE_FEATURE_STANDARDIZATION
    assert payload["metrics"]["feature_normalization"]["signature"] == (
        feature_normalization["signature"]
    )


def test_candidate_evaluation_missing_multi_slice_data_is_prepared(tmp_path) -> None:
    model_artifact = tmp_path / "external-model.pt"
    model_artifact.write_text("unit-model", encoding="utf-8")

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="missing-multi-slice-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(
            tmp_path,
            model_artifact,
            source_slices=(
                CandidateDataSliceConfig(
                    slice_id="missing",
                    yahoo_snapshot=tmp_path / "missing.csv.gz",
                    symbol="AAA",
                ),
            ),
        ),
        gpu=_unit_gpu(),
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_evaluated"
    assert "dataset unavailable" in payload["reason"]
    assert payload["source_slices"][0]["examples_seen"] == 0


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
    yahoo_snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA",))

    result = run_bounded_candidate_evaluation(
        config=CandidateEvaluationConfig(run_id="offline-candidate-evaluation"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        training_metrics_artifact=_training_metrics_artifact(tmp_path, model_artifact),
        yahoo_snapshot=yahoo_snapshot,
        symbol="AAA",
        gpu=_unit_gpu(),
        evaluation_runner=_unit_evaluation_runner,
    )

    payload = json.loads(result.evaluation_artifact.read_text(encoding="utf-8"))
    assert result.evaluation_artifact.exists()
    assert payload["source_slices"][0]["data_quality"]["bars_seen"] == 50
    assert payload["source_slices"][0]["data_quality"]["blocks_research"] is False


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
    source_slices: tuple[CandidateDataSliceConfig, ...] = (),
    feature_normalization: dict[str, object] | None = None,
) -> Path:
    source_slice_payload = [
        {
            "slice_id": data_slice.slice_id,
            "yahoo_snapshot": str(data_slice.yahoo_snapshot),
            "symbol": data_slice.symbol,
            "bars_seen": 40,
            "examples_seen": 36,
        }
        for data_slice in source_slices
    ]
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
                "source_slices": source_slice_payload,
                "feature_preprocessing": "none"
                if feature_normalization is None
                else feature_normalization["mode"],
                "feature_normalization": feature_normalization,
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

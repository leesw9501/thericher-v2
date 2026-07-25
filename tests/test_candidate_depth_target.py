import csv
import gzip
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.research.candidate_depth_target import (
    CandidateDepthTargetConfig,
    run_bounded_candidate_depth_target,
)
from thericher_v2.research.candidate_threshold_robustness import (
    CandidateThresholdRobustnessSliceConfig,
)
from thericher_v2.research.candidate_training import (
    CandidateDataSliceConfig,
    GpuReadiness,
)


def test_candidate_depth_target_selects_one_and_reuses_primitives(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.candidate_depth_target as depth_target

    calls: dict[str, list[str]] = {
        "training": [],
        "evaluation": [],
        "calibration": [],
        "holdout": [],
    }
    original_training = depth_target.run_bounded_candidate_training
    original_evaluation = depth_target.run_bounded_candidate_evaluation
    original_calibration = depth_target.run_bounded_candidate_threshold_calibration
    original_holdout = depth_target.run_bounded_candidate_threshold_holdout

    def spy_training(**kwargs):  # noqa: ANN001
        calls["training"].append(kwargs["config"].run_id)
        return original_training(**kwargs)

    def spy_evaluation(**kwargs):  # noqa: ANN001
        calls["evaluation"].append(kwargs["config"].run_id)
        return original_evaluation(**kwargs)

    def spy_calibration(**kwargs):  # noqa: ANN001
        calls["calibration"].append(kwargs["config"].run_id)
        return original_calibration(**kwargs)

    def spy_holdout(**kwargs):  # noqa: ANN001
        calls["holdout"].append(kwargs["config"].run_id)
        return original_holdout(**kwargs)

    monkeypatch.setattr(depth_target, "run_bounded_candidate_training", spy_training)
    monkeypatch.setattr(depth_target, "run_bounded_candidate_evaluation", spy_evaluation)
    monkeypatch.setattr(
        depth_target,
        "run_bounded_candidate_threshold_calibration",
        spy_calibration,
    )
    monkeypatch.setattr(
        depth_target,
        "run_bounded_candidate_threshold_holdout",
        spy_holdout,
    )

    artifact_root = tmp_path / "model-artifacts"
    breadth_holdout = _breadth_holdout_artifact(artifact_root)
    source_snapshot = _yahoo_snapshot(tmp_path / "source", symbols=("AAA", "BBB"))
    holdout_snapshot = _yahoo_snapshot(tmp_path / "holdout", symbols=("AAA", "BBB"))

    result = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt",
            max_bars=60,
            max_epochs=5,
            max_steps=160,
            source_slices=_data_slices(source_snapshot, ("AAA", "BBB")),
            holdout_slices=_robustness_slices(holdout_snapshot, ("AAA", "BBB")),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=breadth_holdout,
        gpu=_unit_gpu(),
        trainer_runner=_trainer_runner,
        evaluation_runner=_evaluation_runner,
        probability_runner=_probability_runner,
    )

    payload = json.loads(result.target_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_depth_target_ran_only"
    assert result.selected_variant_count == 1
    assert result.selection is not None
    assert result.selection.variant_id == "m1_lb3_b10_s10"
    assert calls == {
        "training": ["dt-m1_lb3_b10_s10-train"],
        "evaluation": ["dt-m1_lb3_b10_s10-eval"],
        "calibration": ["dt-m1_lb3_b10_s10-cal"],
        "holdout": ["dt-m1_lb3_b10_s10-hold"],
    }
    assert payload["selection"]["mode"] == "research_scheduling_only"
    assert payload["selection"]["winner"] is None
    assert payload["selection"]["recommendation"] is None
    assert payload["selection"]["promotion_gate"] is False
    assert payload["selection"]["selected_variant_count"] == 1
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["metrics"]["local_paper_fill_count"] > 0
    assert payload["metrics"]["research_scheduling_only"] is True
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.target_artifact.resolve().parents
    assert artifact_root.resolve() in result.model_artifact.resolve().parents
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_depth_target(
            config=CandidateDepthTargetConfig(),
            artifact_root=Path.cwd(),
            repo_root=Path.cwd(),
            breadth_holdout_artifact=breadth_holdout,
            gpu=_unit_gpu(),
        )


def test_candidate_depth_target_heuristic_is_deterministic_with_missing_metrics(
    tmp_path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"
    breadth_holdout = _breadth_holdout_artifact(
        artifact_root,
        variants=(
            _variant_spec("z-missing", fill_count=None, drawdown=None, pnl_min=None),
            _variant_spec("a-ready", fill_count=5, drawdown="0.5", pnl_min="-0.1"),
            _variant_spec("b-ready", fill_count=5, drawdown="0.5", pnl_min="-0.2"),
        ),
    )
    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))

    result = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt-missing-metrics",
            max_bars=50,
            source_slices=_data_slices(snapshot, ("AAA",)),
            holdout_slices=_robustness_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=breadth_holdout,
        gpu=_unit_gpu(),
        trainer_runner=_trainer_runner,
        evaluation_runner=_evaluation_runner,
        probability_runner=_probability_runner,
    )

    assert result.selection is not None
    assert result.selection.variant_id == "a-ready"
    assert result.selected_variant_count == 1


def test_candidate_depth_target_missing_states_are_prepared(
    monkeypatch,
    tmp_path,
) -> None:
    missing_breadth = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(run_id="dt-missing-breadth"),
        artifact_root=tmp_path / "artifacts-missing-breadth",
        repo_root=Path.cwd(),
        breadth_holdout_artifact=tmp_path / "missing.json",
        gpu=_unit_gpu(),
    )
    assert missing_breadth.status == "prepared_not_depth_targeted"
    assert "artifact is missing" in missing_breadth.reason

    artifact_root = tmp_path / "model-artifacts"
    missing_model_artifact = _breadth_holdout_artifact(
        artifact_root,
        variants=(_variant_spec("missing-model", write_model=False),),
    )
    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))
    missing_model = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt-missing-model",
            max_bars=50,
            source_slices=_data_slices(snapshot, ("AAA",)),
            holdout_slices=_robustness_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=missing_model_artifact,
        gpu=_unit_gpu(),
        trainer_runner=_trainer_runner,
        evaluation_runner=_evaluation_runner,
        probability_runner=_probability_runner,
    )
    assert missing_model.status == "prepared_not_depth_targeted"
    assert "source model artifact is missing" in missing_model.reason

    missing_data = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt-missing-data",
            source_slices=_data_slices(tmp_path / "missing.csv.gz", ("AAA",)),
            holdout_slices=_robustness_slices(tmp_path / "missing.csv.gz", ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=_breadth_holdout_artifact(
            artifact_root,
            variants=(_variant_spec("missing-data"),),
            run_id="source-missing-data",
        ),
        gpu=_unit_gpu(),
        trainer_runner=_trainer_runner,
        evaluation_runner=_evaluation_runner,
        probability_runner=_probability_runner,
    )
    assert missing_data.status == "prepared_not_depth_targeted"
    assert "dataset unavailable" in missing_data.reason

    missing_gpu = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt-missing-gpu",
            max_bars=50,
            source_slices=_data_slices(snapshot, ("AAA",)),
            holdout_slices=_robustness_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=_breadth_holdout_artifact(
            artifact_root,
            variants=(_variant_spec("missing-gpu"),),
            run_id="source-missing-gpu",
        ),
        gpu=GpuReadiness(
            available=False,
            detail="nvidia-smi unavailable",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=_trainer_runner,
        evaluation_runner=_evaluation_runner,
        probability_runner=_probability_runner,
    )
    assert missing_gpu.status == "prepared_not_depth_targeted"
    assert "GPU readiness unavailable" in missing_gpu.reason

    import thericher_v2.research.candidate_training as candidate_training

    monkeypatch.setattr(
        candidate_training.importlib.util,
        "find_spec",
        lambda _name: None,
    )
    missing_backend = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt-missing-backend",
            max_bars=50,
            source_slices=_data_slices(snapshot, ("AAA",)),
            holdout_slices=_robustness_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=_breadth_holdout_artifact(
            artifact_root,
            variants=(_variant_spec("missing-backend"),),
            run_id="source-missing-backend",
        ),
        gpu=_unit_gpu(),
    )
    assert missing_backend.status == "prepared_not_depth_targeted"
    assert "research GPU training backend" in missing_backend.reason


def test_candidate_depth_target_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("candidate depth target must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("candidate depth target must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root = tmp_path / "model-artifacts"
    breadth_holdout = _breadth_holdout_artifact(artifact_root)
    snapshot = _yahoo_snapshot(tmp_path / "snapshots", symbols=("AAA",))
    result = run_bounded_candidate_depth_target(
        config=CandidateDepthTargetConfig(
            run_id="dt-offline",
            max_bars=50,
            source_slices=_data_slices(snapshot, ("AAA",)),
            holdout_slices=_robustness_slices(snapshot, ("AAA",)),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        breadth_holdout_artifact=breadth_holdout,
        gpu=_unit_gpu(),
        trainer_runner=_trainer_runner,
        evaluation_runner=_evaluation_runner,
        probability_runner=_probability_runner,
    )

    assert result.status == "candidate_depth_target_ran_only"


def test_candidate_depth_target_import_keeps_torch_lazy_and_no_broker_paths(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    import thericher_v2.research.candidate_depth_target as depth_target

    source = Path(depth_target.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source
    assert "broker" not in source
    assert "live" not in source


def _breadth_holdout_artifact(
    artifact_root: Path,
    *,
    variants: tuple[dict[str, object], ...] | None = None,
    run_id: str = "unit-breadth-holdout",
) -> Path:
    output_dir = artifact_root / "candidate-breadth-holdout" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_variants = variants or (
        _variant_spec(
            "m1_lb5_b10_s10",
            fill_count=149,
            drawdown="1.35309542236328",
            pnl_min="-0.62640000000000",
        ),
        _variant_spec(
            "m1_lb3_b10_s10",
            fill_count=109,
            drawdown="0.93319572753906",
            pnl_min="-0.21330000000000",
        ),
        _variant_spec(
            "m1_lb8_b10_s10",
            fill_count=142,
            drawdown="0.75319542236328",
            pnl_min="-0.02650000000000",
        ),
    )
    payload_variants = [
        _materialize_variant(artifact_root, variant) for variant in selected_variants
    ]
    path = output_dir / "metrics.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "status": "candidate_breadth_holdout_replayed_only",
                "reason": "unit breadth holdout completed",
                "variants": payload_variants,
                "metrics": {
                    "comparison_is_descriptive": True,
                    "promotion_gate": False,
                },
                "selection": {
                    "winner": None,
                    "recommendation": None,
                    "promotion_gate": False,
                    "mode": "descriptive_breadth_holdout_only",
                },
                "artifact_policy": {
                    "root": str(artifact_root),
                    "repo_storage_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _variant_spec(
    variant_id: str,
    *,
    fill_count: int | None = 7,
    drawdown: str | None = "0.4",
    pnl_min: str | None = "-0.1",
    status: str = "variant_holdout_replayed_only",
    write_model: bool = True,
) -> dict[str, object]:
    return {
        "variant_id": variant_id,
        "fill_count": fill_count,
        "drawdown": drawdown,
        "pnl_min": pnl_min,
        "status": status,
        "write_model": write_model,
    }


def _materialize_variant(
    artifact_root: Path,
    spec: dict[str, object],
) -> dict[str, object]:
    variant_id = str(spec["variant_id"])
    source_dir = artifact_root / "source-lineage" / variant_id
    source_dir.mkdir(parents=True, exist_ok=True)
    training = source_dir / "training.json"
    evaluation = source_dir / "evaluation.json"
    model = source_dir / "model.pt"
    calibration = source_dir / "calibration.json"
    holdout = source_dir / "holdout.json"
    robustness = source_dir / "robustness.json"
    for path in (training, evaluation, calibration, holdout, robustness):
        path.write_text("{}", encoding="utf-8")
    if bool(spec.get("write_model", True)):
        model.write_text("unit-model", encoding="utf-8")
    fill_count = spec.get("fill_count")
    metrics = {
        "holdout_status": "candidate_threshold_holdout_replayed_only",
        "replay_fill_count_total": fill_count,
        "pnl_min": spec.get("pnl_min"),
        "pnl_max": "0.7",
        "max_drawdown_max": spec.get("drawdown"),
        "local_paper_verification": {
            "local_paper_fill_count": fill_count,
            "all_fills_local_paper": True,
        },
        "promotion_gate": False,
    }
    return {
        "variant_id": variant_id,
        "status": spec.get("status"),
        "candidate_experiment_id": variant_id,
        "candidate_parameters": {
            "model_id": "momentum_close_v1",
            "timeframe": "1m",
            "lookback": 3,
            "buy_threshold_bps": 10,
            "sell_threshold_bps": -10,
        },
        "training_metrics_artifact": str(training),
        "evaluation_artifact": str(evaluation),
        "model_artifact": str(model),
        "calibration": {"artifact": str(calibration)},
        "holdout": {
            "artifact": str(holdout),
            "robustness_artifact": str(robustness),
        },
        "metrics": metrics,
    }


def _trainer_runner(dataset, candidate, model, config):  # noqa: ANN001
    model.write_text("unit-depth-model", encoding="utf-8")
    return {
        "backend": "unit",
        "operation": "unit_candidate_training",
        "final_loss": "0.123",
        "accuracy": "0.750000",
        "feature_names": dataset.feature_names,
        "model_artifact": str(model),
        "candidate_experiment_id": candidate.get("candidate_experiment_id"),
        "epoch_count": config.max_epochs,
    }


def _evaluation_runner(dataset, model, training_payload, _config):  # noqa: ANN001
    return {
        "backend": "unit",
        "operation": "unit_candidate_evaluation",
        "accuracy": "0.700000",
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "model_artifact": str(model),
        "candidate_experiment_id": training_payload.get("candidate_experiment_id"),
    }


def _probability_runner(dataset, model, training_payload):  # noqa: ANN001
    values = (0.18, 0.32, 0.49, 0.67, 0.84)
    probabilities = tuple(values[index % len(values)] for index in range(len(dataset.labels)))
    return {
        "backend": "unit",
        "operation": "unit_candidate_probabilities",
        "probabilities": probabilities,
        "feature_count": len(dataset.feature_names),
        "feature_names": dataset.feature_names,
        "feature_names_match": True,
        "model_artifact": str(model),
        "candidate_experiment_id": training_payload.get("candidate_experiment_id"),
    }


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _data_slices(
    yahoo_snapshot: Path,
    symbols: tuple[str, ...],
) -> tuple[CandidateDataSliceConfig, ...]:
    return tuple(
        CandidateDataSliceConfig(
            slice_id=symbol.lower(),
            yahoo_snapshot=yahoo_snapshot,
            symbol=symbol,
        )
        for symbol in symbols
    )


def _robustness_slices(
    yahoo_snapshot: Path,
    symbols: tuple[str, ...],
) -> tuple[CandidateThresholdRobustnessSliceConfig, ...]:
    return tuple(
        CandidateThresholdRobustnessSliceConfig(
            slice_id=f"h{symbol.lower()}",
            yahoo_snapshot=yahoo_snapshot,
            symbol=symbol,
        )
        for symbol in symbols
    )


def _yahoo_snapshot(
    directory: Path,
    *,
    symbols: tuple[str, ...],
    bar_count: int = 70,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ohlcv_1m.csv.gz"
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

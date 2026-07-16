import csv
import gzip
import json
import socket
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_threshold_band_rerun import (
    CandidateThresholdBandRerunConfig,
    derive_attribution_informed_threshold_pairs,
    run_bounded_candidate_threshold_band_rerun,
)
from thericher_v2.research.candidate_training import GpuReadiness
from thericher_v2.research.jobs import ResearchJobSpec, run_and_write_research_job


def test_candidate_threshold_band_rerun_replays_inside_observed_probability_range(
    tmp_path,
) -> None:
    artifact_root, attribution_artifact = _band_artifacts(tmp_path)

    result = run_bounded_candidate_threshold_band_rerun(
        config=CandidateThresholdBandRerunConfig(
            run_id="unit-threshold-band",
            max_bars=50,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_attribution_artifact=attribution_artifact,
        gpu=_unit_gpu(),
    )

    expected_pairs = (
        (0.452, 0.449),
        (0.453, 0.449),
        (0.454, 0.448),
        (0.455, 0.448),
    )
    payload = json.loads(result.band_rerun_artifact.read_text(encoding="utf-8"))
    assert result.status == "candidate_threshold_band_rerun_replayed_only"
    assert result.threshold_pairs == expected_pairs
    assert payload["result_scope"]["mode"] == "research_threshold_band_rerun_only"
    assert payload["result_scope"]["descriptive_only"] is True
    assert payload["result_scope"]["promotion_gate"] is False
    assert "recommendation" not in json.dumps(payload).lower()
    assert "winner" not in json.dumps(payload).lower()
    assert payload["threshold_derivation"]["observed_probability_ceiling"] == "0.455000"
    assert payload["threshold_derivation"]["threshold_pair_count"] == 4
    assert payload["metrics"]["research_threshold_band_rerun_only"] is True
    assert payload["metrics"]["replay_fill_count_total"] > 0
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.band_rerun_artifact.resolve().parents
    assert result.holdout is not None
    assert result.holdout.local_paper_verification["all_fills_local_paper"] is True
    assert _fill_sources(result) == {LOCAL_PAPER_SOURCE}

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_band_rerun(
            config=CandidateThresholdBandRerunConfig(),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            threshold_attribution_artifact=attribution_artifact,
            gpu=_unit_gpu(),
        )


def test_candidate_threshold_band_rerun_research_job_dispatch(tmp_path) -> None:
    artifact_root, attribution_artifact = _band_artifacts(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="utbrj",
            kind="candidate_threshold_band_rerun",
            threshold_attribution_artifact=attribution_artifact,
            max_bars=50,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        gpu=_unit_gpu(),
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_threshold_band_rerun"
    assert payload["status"] == "completed"
    band = payload["candidate_threshold_band_rerun"]
    assert band["status"] == "candidate_threshold_band_rerun_replayed_only"
    assert band["result_scope"]["mode"] == "research_threshold_band_rerun_only"
    assert band["metrics"]["all_fills_local_paper"] is True
    assert Path(payload["artifacts"]["candidate_threshold_band_rerun"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_holdout"]).exists()
    assert Path(payload["artifacts"]["candidate_threshold_robustness"]).exists()
    assert Path(payload["artifacts"]["source_threshold_attribution"]).exists()


def test_candidate_threshold_band_rerun_missing_artifacts_are_prepared(tmp_path) -> None:
    missing_result = run_bounded_candidate_threshold_band_rerun(
        config=CandidateThresholdBandRerunConfig(run_id="missing-attribution"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        threshold_attribution_artifact=tmp_path / "missing-attribution.json",
        gpu=_unit_gpu(),
    )
    assert missing_result.status == "prepared_not_threshold_band_reran"
    assert "candidate threshold attribution artifact is missing" in missing_result.reason

    artifact_root, attribution_artifact = _band_artifacts(tmp_path / "missing-trace")
    trace_artifact = artifact_root / "candidate-probability-trace" / "unit-trace" / "trace.json"
    trace_artifact.unlink()
    missing_trace = run_bounded_candidate_threshold_band_rerun(
        config=CandidateThresholdBandRerunConfig(run_id="missing-trace", max_bars=50),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_attribution_artifact=attribution_artifact,
        gpu=_unit_gpu(),
    )
    assert missing_trace.status == "prepared_not_threshold_band_reran"
    assert "trace_artifacts.hold_aaa" in missing_trace.reason


def test_candidate_threshold_band_rerun_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("threshold band rerun must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("threshold band rerun must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root, attribution_artifact = _band_artifacts(tmp_path)
    result = run_bounded_candidate_threshold_band_rerun(
        config=CandidateThresholdBandRerunConfig(
            run_id="offline-band",
            max_bars=50,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_attribution_artifact=attribution_artifact,
        gpu=_unit_gpu(),
    )

    assert result.status == "candidate_threshold_band_rerun_replayed_only"


def test_candidate_threshold_band_rerun_import_keeps_torch_lazy_and_no_broker_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_threshold_band_rerun as band_rerun

    source = Path(band_rerun.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source
    assert "broker" not in source
    assert "live" not in source


def test_derive_attribution_informed_threshold_pairs_uses_observed_ceiling() -> None:
    pairs = derive_attribution_informed_threshold_pairs(
        (
            (0.451, 0.449),
            (0.452, 0.449),
            (0.453, 0.449),
            (0.454, 0.448),
            (0.455, 0.448),
            (0.456, 0.448),
        ),
        observed_probability_max=Decimal("0.455766"),
        cap=4,
    )

    assert pairs == (
        (0.452, 0.449),
        (0.453, 0.449),
        (0.454, 0.448),
        (0.455, 0.448),
    )


def _band_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
    market_root = tmp_path / "market-data"
    yahoo_snapshot = _yahoo_snapshot(market_root)
    model_artifact = artifact_root / "candidate-training" / "unit-depth" / "model.pt"
    training_artifact = (
        artifact_root / "candidate-training" / "unit-depth" / "metrics.json"
    )
    evaluation_artifact = (
        artifact_root / "candidate-evaluation" / "unit-depth" / "metrics.json"
    )
    trace_artifact = artifact_root / "candidate-probability-trace" / "unit-trace" / "trace.json"
    calibration_artifact = (
        artifact_root
        / "candidate-threshold-calibration"
        / "unit-calibration"
        / "metrics.json"
    )
    robustness_artifact = (
        artifact_root
        / "candidate-threshold-robustness"
        / "unit-robustness"
        / "metrics.json"
    )
    rerun_artifact = (
        artifact_root
        / "candidate-threshold-rerun"
        / "unit-rerun"
        / "metrics.json"
    )
    attribution_artifact = (
        artifact_root
        / "candidate-threshold-attribution"
        / "unit-attribution"
        / "metrics.json"
    )
    model_artifact.parent.mkdir(parents=True, exist_ok=True)
    model_artifact.write_text("unit-model", encoding="utf-8")
    _write_json(
        training_artifact,
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
        },
    )
    _write_json(
        evaluation_artifact,
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
        },
    )
    _write_json(
        trace_artifact,
        {
            "status": "probability_traced_only",
            "available_backends": ["unit"],
            "selected_backend": "trace",
            "training_metrics_artifact": str(training_artifact),
            "evaluation_artifact": str(evaluation_artifact),
            "model_artifact": str(model_artifact),
            "candidate_experiment_id": "m1_lb3_b10_s10",
            "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
            "data_source": str(yahoo_snapshot),
            "symbol": "AAA",
            "market": "US",
            "timeframe": "1m",
            "bars_seen": 50,
            "examples_seen": 46,
            "lookback": 3,
            "probability_metrics": {"operation": "unit_trace"},
            "entries": [
                {
                    "offset": index,
                    "probability": 0.4555 if index % 2 == 0 else 0.4470,
                }
                for index in range(46)
            ],
        },
    )
    threshold_pairs = [
        {"buy_threshold": "0.451000", "sell_threshold": "0.449000"},
        {"buy_threshold": "0.452000", "sell_threshold": "0.449000"},
        {"buy_threshold": "0.453000", "sell_threshold": "0.449000"},
        {"buy_threshold": "0.454000", "sell_threshold": "0.448000"},
        {"buy_threshold": "0.455000", "sell_threshold": "0.448000"},
        {"buy_threshold": "0.456000", "sell_threshold": "0.448000"},
    ]
    _write_json(
        calibration_artifact,
        {
            "status": "candidate_thresholds_calibrated_only",
            "candidate_experiment_id": "m1_lb3_b10_s10",
            "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
            "training_metrics_artifact": str(training_artifact),
            "evaluation_artifact": str(evaluation_artifact),
            "model_artifact": str(model_artifact),
            "thresholds": {
                "derivation": "observed_probability_quantiles",
                "threshold_pairs": threshold_pairs,
                "promotion_gate": False,
            },
        },
    )
    _write_json(
        robustness_artifact,
        {
            "status": "candidate_robustness_replayed_only",
            "slices": [
                {
                    "slice_id": "hold_aaa",
                    "status": "slice_replayed_only",
                    "reason": "slice threshold variants replayed from probability trace",
                    "symbol": "AAA",
                    "market": "US",
                    "timeframe": "1m",
                    "bars_seen": 50,
                    "examples_seen": 46,
                    "yahoo_snapshot": str(yahoo_snapshot),
                    "probability_trace_artifact": _app_path(trace_artifact, artifact_root),
                    "source_alignment": {"same_trace_evidence": True},
                    "variants": [],
                    "metrics": {},
                }
            ],
        },
    )
    _write_json(
        rerun_artifact,
        {
            "status": "candidate_threshold_rerun_replayed_only",
            "candidate_experiment_id": "m1_lb3_b10_s10",
            "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
            "selected_variant_id": "m1_lb3_b10_s10",
            "source_calibration_artifact": _app_path(calibration_artifact, artifact_root),
            "source_thresholds": {
                "threshold_pair_count": 6,
                "threshold_pairs": threshold_pairs,
            },
            "artifacts": {
                "candidate_threshold_robustness": _app_path(
                    robustness_artifact,
                    artifact_root,
                ),
            },
            "metrics": {
                "research_threshold_rerun_only": True,
                "local_paper_verification": {
                    "all_fills_local_paper": True,
                    "local_paper_fill_count": 0,
                },
            },
            "local_paper_verification": {
                "all_fills_local_paper": True,
                "local_paper_fill_count": 0,
            },
        },
    )
    _write_json(
        attribution_artifact,
        {
            "status": "candidate_threshold_attribution_only",
            "candidate_experiment_id": "m1_lb3_b10_s10",
            "candidate_parameters": {"lookback": 3, "timeframe": "1m"},
            "selected_variant_id": "m1_lb3_b10_s10",
            "source_threshold_rerun_artifact": _app_path(rerun_artifact, artifact_root),
            "source_robustness_artifact": _app_path(robustness_artifact, artifact_root),
            "source_calibration_artifact": _app_path(calibration_artifact, artifact_root),
            "threshold_band_comparison": {
                "mode": "research_threshold_attribution_only",
                "observed_probability_max": "0.455766",
                "source_buy_min": 0.451,
                "source_buy_max": 0.456,
                "strict_buy_min": 0.457,
                "strict_buy_min_above_observed_probability_max": True,
                "promotion_gate": False,
            },
            "metrics": {
                "research_threshold_attribution_only": True,
                "buy_opportunity_count_total": 0,
                "replay_fill_count_total": 0,
                "all_fills_local_paper": True,
            },
        },
    )
    return artifact_root, attribution_artifact


def _unit_gpu() -> GpuReadiness:
    return GpuReadiness(
        available=True,
        detail="Unit GPU, 24576 MiB",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _fill_sources(result) -> set[str]:  # noqa: ANN001
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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _app_path(path: Path, artifact_root: Path) -> str:
    relative = path.relative_to(artifact_root)
    return "/app/model_artifacts/" + "/".join(relative.parts)

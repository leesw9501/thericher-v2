import json
import socket
import sys
from pathlib import Path

import pytest

from thericher_v2.research.candidate_threshold_attribution import (
    CandidateThresholdAttributionConfig,
    run_bounded_candidate_threshold_attribution,
)
from thericher_v2.research.jobs import ResearchJobSpec, run_and_write_research_job


def test_candidate_threshold_attribution_describes_zero_fill_threshold_opportunities(
    tmp_path,
) -> None:
    artifact_root, rerun_artifact = _attribution_artifacts(tmp_path)

    result = run_bounded_candidate_threshold_attribution(
        config=CandidateThresholdAttributionConfig(run_id="unit-threshold-attribution"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_rerun_artifact=rerun_artifact,
    )

    payload = json.loads(result.attribution_artifact.read_text(encoding="utf-8"))
    first_variant = payload["slices"][0]["variants"][0]
    second_variant = payload["slices"][0]["variants"][1]
    assert result.status == "candidate_threshold_attribution_only"
    assert payload["selection"]["mode"] == "research_threshold_attribution_only"
    assert payload["selection"]["winner"] is None
    assert payload["selection"]["recommendation"] is None
    assert payload["selection"]["promotion_gate"] is False
    assert payload["metrics"]["research_threshold_attribution_only"] is True
    assert payload["metrics"]["comparison_is_descriptive"] is True
    assert payload["metrics"]["buy_opportunity_count_total"] == 2
    assert payload["metrics"]["sell_opportunity_count_total"] == 2
    assert payload["metrics"]["replay_fill_count_total"] == 2
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.attribution_artifact.resolve().parents
    assert first_variant["buy_opportunity_count"] == 2
    assert first_variant["sell_opportunity_count"] == 1
    assert first_variant["neutral_probability_count"] == 1
    assert first_variant["replay_fill_count"] == 2
    assert first_variant["promotion_gate"] is False
    assert second_variant["buy_opportunity_count"] == 0
    assert second_variant["attribution"] == "buy threshold exceeded observed probability range"
    assert payload["threshold_band_comparison"]["source_buy_max"] == 0.7
    assert payload["threshold_band_comparison"]["strict_buy_min"] == 0.7
    assert payload["threshold_band_comparison"]["observed_probability_max"] == 0.8
    assert payload["threshold_band_comparison"]["winner"] is None

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_threshold_attribution(
            config=CandidateThresholdAttributionConfig(),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            threshold_rerun_artifact=rerun_artifact,
        )


def test_candidate_threshold_attribution_research_job_dispatch(tmp_path) -> None:
    artifact_root, rerun_artifact = _attribution_artifacts(tmp_path)

    run = run_and_write_research_job(
        ResearchJobSpec(
            job_id="utaj",
            kind="candidate_threshold_attribution",
            threshold_rerun_artifact=rerun_artifact,
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
    )

    payload = json.loads(run.job_artifact.read_text(encoding="utf-8"))
    assert run.result.status == "completed"
    assert payload["kind"] == "candidate_threshold_attribution"
    assert payload["status"] == "completed"
    attribution = payload["candidate_threshold_attribution"]
    assert attribution["status"] == "candidate_threshold_attribution_only"
    assert attribution["selection"]["mode"] == "research_threshold_attribution_only"
    assert attribution["selection"]["winner"] is None
    assert attribution["metrics"]["all_referenced_artifacts_exist"] is True
    assert Path(payload["artifacts"]["candidate_threshold_attribution"]).exists()
    assert Path(payload["artifacts"]["source_threshold_rerun"]).exists()
    assert Path(payload["artifacts"]["source_robustness"]).exists()
    assert Path(payload["artifacts"]["source_calibration"]).exists()


def test_candidate_threshold_attribution_missing_artifacts_are_prepared(
    tmp_path,
) -> None:
    missing_result = run_bounded_candidate_threshold_attribution(
        config=CandidateThresholdAttributionConfig(run_id="missing-rerun"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        threshold_rerun_artifact=tmp_path / "missing-rerun.json",
    )
    assert missing_result.status == "prepared_not_threshold_attributed"
    assert "candidate threshold rerun artifact is missing" in missing_result.reason

    artifact_root, rerun_artifact = _attribution_artifacts(tmp_path / "missing-trace")
    trace_artifact = artifact_root / "candidate-probability-trace" / "unit-trace" / "trace.json"
    trace_artifact.unlink()
    missing_trace = run_bounded_candidate_threshold_attribution(
        config=CandidateThresholdAttributionConfig(run_id="missing-trace"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_rerun_artifact=rerun_artifact,
    )
    assert missing_trace.status == "prepared_not_threshold_attributed"
    assert "trace_artifacts.hold_aaa" in missing_trace.reason
    assert "threshold attribution slices are incomplete: hold_aaa" in missing_trace.reason


def test_candidate_threshold_attribution_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("threshold attribution must not open network connections")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("threshold attribution must not read credential files")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root, rerun_artifact = _attribution_artifacts(tmp_path)
    result = run_bounded_candidate_threshold_attribution(
        config=CandidateThresholdAttributionConfig(run_id="offline-attribution"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        threshold_rerun_artifact=rerun_artifact,
    )

    assert result.status == "candidate_threshold_attribution_only"


def test_candidate_threshold_attribution_import_keeps_torch_lazy_and_no_broker_paths() -> None:
    sys.modules.pop("torch", None)
    import thericher_v2.research.candidate_threshold_attribution as attribution

    source = Path(attribution.__file__).read_text(encoding="utf-8").lower()
    assert "torch" not in sys.modules
    assert "torch" not in source
    assert "kis" not in source
    assert "broker" not in source
    assert "live" not in source


def _attribution_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
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
    events_artifact = (
        artifact_root
        / "candidate-threshold-robustness"
        / "unit-robustness"
        / "hold_aaa-t01-events.jsonl"
    )
    _write_json(
        trace_artifact,
        {
            "status": "probability_traced_only",
            "entries": [
                {"offset": 0, "probability": 0.80},
                {"offset": 1, "probability": 0.72},
                {"offset": 2, "probability": 0.50},
                {"offset": 3, "probability": 0.20},
            ],
        },
    )
    _write_json(
        calibration_artifact,
        {
            "status": "candidate_thresholds_calibrated_only",
            "thresholds": {
                "threshold_pairs": [
                    {"buy_threshold": "0.500000", "sell_threshold": "0.300000"},
                    {"buy_threshold": "0.700000", "sell_threshold": "0.300000"},
                ],
            },
        },
    )
    events_artifact.parent.mkdir(parents=True, exist_ok=True)
    events_artifact.write_text(
        json.dumps({"event_type": "fill", "payload": {"source": "local_paper"}}) + "\n",
        encoding="utf-8",
    )
    _write_json(
        robustness_artifact,
        {
            "status": "candidate_robustness_replayed_only",
            "slices": [
                {
                    "slice_id": "hold_aaa",
                    "symbol": "AAA",
                    "probability_trace_artifact": _app_path(trace_artifact, artifact_root),
                    "variants": [
                        {
                            "variant_id": "hold_aaa-t01",
                            "status": "candidate_replayed_only",
                            "buy_threshold": "0.700000",
                            "sell_threshold": "0.300000",
                            "replay_fill_count": 2,
                            "trade_count": 2,
                            "final_position": "0",
                            "pnl": "1.25",
                            "max_drawdown": "0.10",
                            "events_artifact": str(events_artifact),
                        },
                        {
                            "variant_id": "hold_aaa-t02",
                            "status": "candidate_replayed_only",
                            "buy_threshold": "0.900000",
                            "sell_threshold": "0.300000",
                            "replay_fill_count": 0,
                            "trade_count": 0,
                            "final_position": "0",
                            "pnl": "0",
                            "max_drawdown": "0",
                            "events_artifact": None,
                        },
                    ],
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
                "threshold_pair_count": 2,
                "threshold_pairs": [
                    {"buy_threshold": "0.500000", "sell_threshold": "0.300000"},
                    {"buy_threshold": "0.700000", "sell_threshold": "0.300000"},
                ],
            },
            "threshold_schedule": {
                "mode": "research_threshold_rerun_only",
                "threshold_pair_count": 2,
                "threshold_pairs": [
                    {"buy_threshold": "0.700000", "sell_threshold": "0.300000"},
                    {"buy_threshold": "0.900000", "sell_threshold": "0.300000"},
                ],
                "winner": None,
                "recommendation": None,
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_threshold_rerun": str(rerun_artifact),
                "candidate_threshold_robustness": _app_path(
                    robustness_artifact,
                    artifact_root,
                ),
            },
            "metrics": {
                "research_threshold_rerun_only": True,
                "local_paper_verification": {
                    "all_fills_local_paper": True,
                    "local_paper_fill_count": 2,
                },
            },
            "local_paper_verification": {
                "all_fills_local_paper": True,
                "local_paper_fill_count": 2,
            },
        },
    )
    return artifact_root, rerun_artifact


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _app_path(path: Path, artifact_root: Path) -> str:
    relative = path.relative_to(artifact_root)
    return "/app/model_artifacts/" + "/".join(relative.parts)

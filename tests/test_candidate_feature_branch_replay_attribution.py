import json
import socket
from pathlib import Path

import pytest

import thericher_v2.research.candidate_feature_branch_replay as feature_branch_replay
from thericher_v2.execution import BROKER_DISABLED_SOURCE, LOCAL_PAPER_SOURCE
from thericher_v2.research.candidate_feature_branch_replay import (
    CandidateFeatureBranchReplayAttributionConfig,
    run_bounded_candidate_feature_branch_replay_opportunity_attribution,
)


def test_feature_branch_replay_attribution_describes_zero_fill_opportunities(
    tmp_path,
) -> None:
    artifact_root, replay_artifact = _feature_branch_replay_attribution_artifacts(
        tmp_path
    )

    result = run_bounded_candidate_feature_branch_replay_opportunity_attribution(
        config=CandidateFeatureBranchReplayAttributionConfig(
            run_id="unit-feature-replay-attribution",
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_replay_artifact=replay_artifact,
    )

    payload = json.loads(result.attribution_artifact.read_text(encoding="utf-8"))
    first_variant = payload["slices"][0]["variants"][0]
    alignment = payload["source_vs_holdout_probability_alignment"]
    assert result.status == "candidate_feature_branch_replay_attribution_only"
    assert (
        payload["result_scope"]["mode"]
        == "research_feature_branch_replay_opportunity_attribution_only"
    )
    assert alignment["mode"] == "source_vs_holdout_probability_alignment_attribution"
    assert alignment["source_probability_summary"] == {
        "min": "0.100000",
        "max": "0.800000",
        "mean": "0.450000",
        "range": "0.700000",
        "label_positive_rate": "0.460000",
        "predicted_positive_rate": "0.030000",
    }
    assert alignment["holdout_probability_summary"] == {
        "slice_count": 1,
        "count": 3,
        "min": "0.200000",
        "max": "0.997000",
        "mean": "0.532333",
        "range": "0.797000",
    }
    assert alignment["source_to_holdout_delta"] == {
        "holdout_min_minus_source_min": "0.100000",
        "holdout_max_minus_source_max": "0.197000",
        "holdout_mean_minus_source_mean": "0.082333",
        "holdout_range_minus_source_range": "0.097000",
    }
    assert alignment["threshold_gap"] == {
        "buy_threshold_min": "0.998000",
        "buy_threshold_max": "0.999000",
        "sell_threshold_min": "0.447000",
        "sell_threshold_max": "0.447000",
        "buy_threshold_min_minus_holdout_max": "0.001000",
        "sell_threshold_max_minus_holdout_min": "0.247000",
        "buy_threshold_min_above_holdout_max": True,
    }
    assert alignment["opportunities"] == {
        "buy_opportunity_count_total": 0,
        "sell_opportunity_count_total": 4,
        "replay_fill_count_total": 0,
    }
    assert (
        payload["metrics"]["source_vs_holdout_probability_alignment"][
            "threshold_gap"
        ]["buy_threshold_min_above_holdout_max"]
        is True
    )
    assert payload["metrics"]["buy_opportunity_count_total"] == 0
    assert payload["metrics"]["sell_opportunity_count_total"] == 4
    assert payload["metrics"]["replay_fill_count_total"] == 0
    assert payload["metrics"]["zero_fill_variant_count"] == 2
    assert payload["metrics"]["all_fills_local_paper"] is True
    assert payload["local_paper_verification"]["local_paper_fill_count"] == 0
    assert len(payload["local_paper_verification"]["missing_zero_fill_event_artifacts"]) == 2
    assert first_variant["attribution"] == "buy threshold exceeded observed probability range"
    assert first_variant["pnl"] == "0"
    assert first_variant["max_drawdown"] == "0"
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.attribution_artifact.resolve().parents
    rendered = json.dumps(payload).lower()
    assert "winner" not in rendered
    assert "recommendation" not in rendered
    assert "production ready" not in rendered

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_feature_branch_replay_opportunity_attribution(
            config=CandidateFeatureBranchReplayAttributionConfig(),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            feature_branch_replay_artifact=replay_artifact,
        )


def test_feature_branch_replay_attribution_is_offline_and_does_not_read_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("feature branch attribution must not open network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("feature branch attribution must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    artifact_root, replay_artifact = _feature_branch_replay_attribution_artifacts(
        tmp_path
    )
    result = run_bounded_candidate_feature_branch_replay_opportunity_attribution(
        config=CandidateFeatureBranchReplayAttributionConfig(run_id="offline-fbra"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_replay_artifact=replay_artifact,
    )

    assert result.status == "candidate_feature_branch_replay_attribution_only"


def test_feature_branch_replay_attribution_import_keeps_torch_lazy() -> None:
    source = Path(feature_branch_replay.__file__).read_text(encoding="utf-8").lower()

    assert "import torch" not in source
    assert "from torch" not in source


def test_feature_branch_replay_attribution_keeps_broker_disabled_source_separate(
    tmp_path,
) -> None:
    artifact_root, replay_artifact = _feature_branch_replay_attribution_artifacts(
        tmp_path,
        event_source=BROKER_DISABLED_SOURCE,
    )

    result = run_bounded_candidate_feature_branch_replay_opportunity_attribution(
        config=CandidateFeatureBranchReplayAttributionConfig(run_id="broker-source-fbra"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_replay_artifact=replay_artifact,
    )

    payload = json.loads(result.attribution_artifact.read_text(encoding="utf-8"))
    verification = payload["local_paper_verification"]
    assert result.status == "candidate_feature_branch_replay_attribution_only"
    assert BROKER_DISABLED_SOURCE != LOCAL_PAPER_SOURCE
    assert verification["fill_source_counts"] == {BROKER_DISABLED_SOURCE: 1}
    assert verification["non_local_fill_source_counts"] == {BROKER_DISABLED_SOURCE: 1}
    assert verification["local_paper_fill_count"] == 0
    assert verification["all_fills_local_paper"] is False
    assert payload["metrics"]["all_fills_local_paper"] is False
    assert payload["metrics"]["replay_fill_count_total"] == 1


def test_feature_branch_replay_attribution_requires_completed_robustness(
    tmp_path,
) -> None:
    artifact_root, replay_artifact = _feature_branch_replay_attribution_artifacts(
        tmp_path,
        robustness_status="prepared_not_robustness_replayed",
    )

    result = run_bounded_candidate_feature_branch_replay_opportunity_attribution(
        config=CandidateFeatureBranchReplayAttributionConfig(run_id="prepared-fbra"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_replay_artifact=replay_artifact,
    )

    assert result.status == "prepared_not_feature_branch_replay_attributed"
    assert "candidate threshold robustness" in result.reason


def _feature_branch_replay_attribution_artifacts(
    tmp_path: Path,
    *,
    event_source: str | None = None,
    robustness_status: str = "candidate_robustness_replayed_only",
) -> tuple[Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
    trace_artifact = (
        artifact_root
        / "candidate-probability-trace"
        / "unit-feature-replay-attribution"
        / "trace.json"
    )
    robustness_artifact = (
        artifact_root
        / "candidate-threshold-robustness"
        / "unit-feature-replay-attribution"
        / "metrics.json"
    )
    replay_artifact = (
        artifact_root
        / "candidate-feature-branch-replay"
        / "unit-feature-replay"
        / "metrics.json"
    )
    first_events_artifact = (
        artifact_root
        / "candidate-threshold-robustness"
        / "unit-feature-replay-attribution"
        / "slices"
        / "hold_aaa"
        / "variants"
        / "t01_b0p998_s0p447"
        / "events.jsonl"
    )
    second_events_artifact = first_events_artifact.parent.parent / "t02" / "events.jsonl"
    probabilities = (
        (1.0, 0.20)
        if event_source is not None
        else (0.997, 0.40, 0.20)
    )
    _write_json(
        trace_artifact,
        {
            "status": "probability_traced_only",
            "entries": [
                {"offset": index, "probability": probability}
                for index, probability in enumerate(probabilities)
            ],
        },
    )
    if event_source is not None:
        first_events_artifact.parent.mkdir(parents=True, exist_ok=True)
        first_events_artifact.write_text(
            json.dumps({"event_type": "fill", "payload": {"source": event_source}})
            + "\n",
            encoding="utf-8",
        )
    replay_fill_count = 1 if event_source is not None else 0
    _write_json(
        robustness_artifact,
        {
            "status": robustness_status,
            "slices": [
                {
                    "slice_id": "hold_aaa",
                    "symbol": "AAA",
                    "probability_trace_artifact": _app_path(trace_artifact, artifact_root),
                    "variants": [
                        {
                            "variant_id": "t01_b0p998_s0p447",
                            "status": "candidate_replayed_only",
                            "buy_threshold": "0.998000",
                            "sell_threshold": "0.447000",
                            "replay_fill_count": replay_fill_count,
                            "trade_count": replay_fill_count,
                            "final_position": "0",
                            "pnl": "0",
                            "max_drawdown": "0",
                            "events_artifact": str(first_events_artifact),
                        },
                        {
                            "variant_id": "t02_b0p999_s0p447",
                            "status": "candidate_replayed_only",
                            "buy_threshold": "0.999000",
                            "sell_threshold": "0.447000",
                            "replay_fill_count": 0,
                            "trade_count": 0,
                            "final_position": "0",
                            "pnl": "0",
                            "max_drawdown": "0",
                            "events_artifact": _app_path(
                                second_events_artifact,
                                artifact_root,
                            ),
                        },
                    ],
                }
            ],
        },
    )
    _write_json(
        replay_artifact,
        {
            "status": "candidate_feature_branch_replayed_only",
            "candidate_experiment_id": "m1_lb3_b10_s10__core_plus_bar_pressure_v1",
            "candidate_parameters": {
                "feature_set": "core_plus_bar_pressure_v1",
                "lookback": 3,
                "timeframe": "1m",
            },
            "threshold_pairs": [
                {"buy_threshold": "0.998000", "sell_threshold": "0.447000"},
                {"buy_threshold": "0.999000", "sell_threshold": "0.447000"},
            ],
            "threshold_derivation": {
                "mode": "feature_branch_probability_range_probe",
                "source_probability_evidence": {
                    "min_probability": "0.100000",
                    "max_probability": "0.800000",
                    "mean_probability": "0.450000",
                    "probability_range": "0.700000",
                    "label_positive_rate": "0.460000",
                    "predicted_positive_rate": "0.030000",
                },
                "threshold_pair_cap": 2,
                "threshold_pair_count": 2,
                "threshold_pairs": [
                    {"buy_threshold": "0.998000", "sell_threshold": "0.447000"},
                    {"buy_threshold": "0.999000", "sell_threshold": "0.447000"},
                ],
                "saturation_guard": {
                    "mode": "max_buy_ceiling_clamped_below_one",
                    "promotion_gate": False,
                },
                "promotion_gate": False,
            },
            "artifacts": {
                "candidate_feature_branch_replay": str(replay_artifact),
                "candidate_threshold_robustness": _app_path(
                    robustness_artifact,
                    artifact_root,
                ),
            },
            "local_paper_verification": {
                "all_fills_local_paper": True,
                "local_paper_fill_count": 0,
                "non_local_fill_source_counts": {},
            },
            "metrics": {
                "research_feature_branch_replay_only": True,
                "replay_fill_count_total": replay_fill_count,
                "promotion_gate": False,
            },
        },
    )
    return artifact_root, replay_artifact


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _app_path(path: Path, artifact_root: Path) -> str:
    relative = path.relative_to(artifact_root)
    return "/app/model_artifacts/" + "/".join(relative.parts)

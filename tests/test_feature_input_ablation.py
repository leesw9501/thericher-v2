from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.research.feature_input_ablation import (
    EXISTING_THRESHOLD_META_BASELINE_GROUP,
    RAW_PRE_ENTRY_GROUP,
    RAW_PRE_ENTRY_PLUS_PROBABILITY_META_GROUP,
    FeatureInputAblationConfig,
    run_bounded_feature_input_ablation,
)
from thericher_v2.research.validation import GpuReadiness


def test_feature_input_ablation_runs_injected_and_separates_feature_groups(
    tmp_path,
) -> None:
    stability_artifact = _stability_artifact(tmp_path)

    def runner(dataset, model_artifact, config):  # noqa: ANN001
        assert config.max_epochs == 3
        assert dataset.rows_used == 8
        assert [group.group_id for group in dataset.feature_groups] == [
            EXISTING_THRESHOLD_META_BASELINE_GROUP,
            RAW_PRE_ENTRY_GROUP,
            RAW_PRE_ENTRY_PLUS_PROBABILITY_META_GROUP,
        ]
        raw_group = dataset.feature_groups[1]
        assert set(raw_group.feature_roles.values()) == {"raw_pre_entry_market_feature"}
        combined_group = dataset.feature_groups[2]
        assert {
            "raw_pre_entry_market_feature",
            "probability_derived_meta_feature",
        } == set(combined_group.feature_roles.values())
        model_artifact.write_text("unit-feature-input-model", encoding="utf-8")
        return {
            "backend": "unit",
            "operation": "unit_feature_input_ablation",
            "examples_seen": len(dataset.labels),
            "groups": [
                {
                    "group_id": group.group_id,
                    "feature_count": len(group.feature_names),
                    "accuracy": "0.500000",
                }
                for group in dataset.feature_groups
            ],
            "model_artifact": str(model_artifact),
        }

    result = run_bounded_feature_input_ablation(
        config=FeatureInputAblationConfig(run_id="unit-feature-input", max_epochs=3),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        stability_artifact=stability_artifact,
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=runner,
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "feature_input_ablation_ran_only"
    assert payload["status"] == "feature_input_ablation_ran_only"
    assert payload["rows_used"] == 8
    assert payload["label_counts"] == {
        "adverse_or_no_lift": 4,
        "non_adverse": 4,
    }
    assert payload["source_evidence"]["all_reference_fills_local_paper"] is True
    assert payload["source_evidence"]["local_paper_reference_fill_count"] == 12
    assert payload["source_evidence"]["diagnostic_overlay_source_counts"] == {
        "diagnostic_overlay": 8,
    }
    assert payload["result_scope"]["broker_used"] is False
    assert payload["result_scope"]["kis_api_called"] is False
    assert payload["result_scope"]["credentials_read"] is False
    assert payload["result_scope"]["local_paper_replay_changed"] is False
    assert payload["metrics"]["raw_market_feature_names"] == [
        "pre_close_return",
        "pre_high_low_range_pct",
        "pre_last_close_position_in_range",
        "pre_last_volume_vs_prior_avg",
    ]
    assert payload["metrics"]["probability_derived_feature_names"] == [
        "probability_margin",
        "probability_rank_pct",
    ]
    assert Path(payload["artifacts"]["model"]).exists()


def test_feature_input_ablation_missing_artifact_is_prepared(tmp_path) -> None:
    result = run_bounded_feature_input_ablation(
        config=FeatureInputAblationConfig(run_id="missing-feature-input"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        stability_artifact=tmp_path / "missing.json",
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert result.status == "prepared_not_feature_input_ablated"
    assert payload["status"] == "prepared_not_feature_input_ablated"
    assert "missing" in payload["reason"]
    assert payload["artifacts"]["model"] is None


def test_feature_input_ablation_uses_diagnostic_overlay_rows_only(tmp_path) -> None:
    stability_artifact = _stability_artifact(tmp_path)
    payload = json.loads(stability_artifact.read_text(encoding="utf-8"))
    local_paper_row = dict(payload["selected_candidate_entry_rows"][0])
    local_paper_row["source"] = "local_paper"
    payload["selected_candidate_entry_rows"].append(local_paper_row)
    stability_artifact.write_text(json.dumps(payload), encoding="utf-8")

    result = run_bounded_feature_input_ablation(
        config=FeatureInputAblationConfig(run_id="source-filtered-feature-input"),
        artifact_root=tmp_path / "model-artifacts",
        repo_root=Path.cwd(),
        stability_artifact=stability_artifact,
        gpu=GpuReadiness(
            available=True,
            detail="Unit GPU, 24576 MiB",
            checked_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        trainer_runner=lambda dataset, model_artifact, _config: {
            "backend": "unit",
            "operation": "unit_feature_input_ablation",
            "examples_seen": len(dataset.labels),
            "groups": [],
            "model_artifact": str(model_artifact),
        },
    )

    payload = json.loads(result.metrics_artifact.read_text(encoding="utf-8"))
    assert payload["rows_seen"] == 9
    assert payload["rows_used"] == 8
    assert payload["rows_dropped"] == 1


def test_feature_input_ablation_rejects_repo_artifact_root(tmp_path) -> None:
    stability_artifact = _stability_artifact(tmp_path)

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_feature_input_ablation(
            config=FeatureInputAblationConfig(run_id="bad-repo-root"),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            stability_artifact=stability_artifact,
        )


def test_feature_input_ablation_import_keeps_torch_lazy_and_no_kis_paths() -> None:
    import thericher_v2.research.feature_input_ablation as ablation

    source = Path(ablation.__file__).read_text(encoding="utf-8").lower()
    assert "kis_api_called" in source
    assert "requests" not in source
    assert "os.environ" not in source
    assert "broker_used" in source
    assert source.count("import torch") == 1


def _stability_artifact(tmp_path: Path) -> Path:
    rows = []
    buckets = [
        "early_adverse_dominant",
        "early_no_lift",
        "early_lift",
        "early_mixed",
    ]
    for index in range(8):
        rows.append(
            {
                "source": "diagnostic_overlay",
                "slice_id": "unit_slice",
                "symbol": "AAA",
                "variant_id": "v1",
                "probability_margin": 0.01 * (index + 1),
                "probability_rank_pct": 0.2 + (index * 0.05),
                "pre_entry_3bar": {
                    "close_return": str(0.001 * index),
                    "range_pct_of_last_close": str(0.002 * (index + 1)),
                    "last_close_position_in_range": str(0.1 * (index % 5)),
                    "last_volume_vs_prior_avg": str(-0.05 * index),
                },
                "early_3bar": {
                    "path_quality_bucket": buckets[index % len(buckets)],
                },
            }
        )
    artifact = tmp_path / "stability.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "cross_slice_feature_input_stability_diagnostic_only",
                "source_evidence": {
                    "all_reference_fills_local_paper": True,
                    "local_paper_reference_fill_count": 12,
                    "diagnostic_overlay_source_counts": {"diagnostic_overlay": 8},
                    "diagnostic_rows_are_not_local_paper_fills": True,
                },
                "selected_candidate_entry_rows": rows,
            }
        ),
        encoding="utf-8",
    )
    return artifact

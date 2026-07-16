from __future__ import annotations

import csv
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.research.feature_input_ablation import (
    EXISTING_THRESHOLD_META_BASELINE_GROUP,
    RAW_PRE_ENTRY_FEATURE_NAMES,
    RAW_PRE_ENTRY_GROUP,
    RAW_PRE_ENTRY_PLUS_PROBABILITY_META_GROUP,
    FeatureInputAblationConfig,
    _binary_classification_metrics,
    _descriptive_evaluation_payload,
    _probability_band_diagnostics,
    _resolve_lineage_path,
    _unique_signal_descriptive_evaluation,
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
        assert len(dataset.row_metadata) == len(dataset.labels)
        assert {metadata["source"] for metadata in dataset.row_metadata} == {
            "diagnostic_overlay"
        }
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
    assert payload["metrics"]["descriptive_evaluation_context"]["row_count"] == 8
    assert payload["metrics"]["descriptive_evaluation_context"]["source_counts"] == {
        "diagnostic_overlay": 8,
    }
    assert payload["metrics"]["descriptive_evaluation_context"][
        "diagnostic_overlay_rows_only"
    ] is True
    assert payload["metrics"]["descriptive_evaluation_context"][
        "missing_signal_key_row_count"
    ] == 8
    assert payload["metrics"]["descriptive_evaluation_context"]["unique_signal_count"] == 0
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


def test_feature_input_ablation_all_diagnostic_mode_reconstructs_lineage_rows(
    monkeypatch,
    tmp_path,
) -> None:
    import thericher_v2.research.feature_input_ablation as ablation

    artifact_root = tmp_path / "model-artifacts"
    market_data_root = tmp_path / "market_data"
    monkeypatch.setattr(ablation, "DEFAULT_HOST_MARKET_DATA_ROOT", market_data_root)
    stability_artifact = _lineage_stability_artifact(
        tmp_path,
        artifact_root,
        market_data_root=market_data_root,
    )

    def runner(dataset, model_artifact, config):  # noqa: ANN001
        assert config.row_mode == "all_diagnostic"
        assert dataset.row_mode == "all_diagnostic"
        assert dataset.rows_seen == 5
        assert dataset.rows_used == 5
        assert dataset.row_source_counts == {"diagnostic_overlay": 5}
        assert dataset.source_slices == ("unit_full",)
        assert {metadata["source"] for metadata in dataset.row_metadata} == {
            "diagnostic_overlay"
        }
        assert {metadata["slice_variant_id"] for metadata in dataset.row_metadata} == {
            "unit_full:t01",
            "unit_full:t02",
        }
        model_artifact.write_text("unit-full-row-model", encoding="utf-8")
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
        config=FeatureInputAblationConfig(
            run_id="unit-full-row-feature-input",
            row_mode="all_diagnostic",
            min_examples=2,
        ),
        artifact_root=artifact_root,
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
    assert payload["row_mode"] == "all_diagnostic"
    assert payload["rows_seen"] == 5
    assert payload["rows_used"] == 5
    assert payload["rows_dropped"] == 0
    assert payload["metrics"]["row_mode"] == "all_diagnostic"
    assert payload["metrics"]["row_source_counts"] == {"diagnostic_overlay": 5}
    assert payload["metrics"]["row_reconstruction"]["rows_reconstructed"] == 5
    assert payload["metrics"]["row_reconstruction"]["slice_counts"] == {
        "unit_full": 5,
    }
    assert payload["metrics"]["descriptive_evaluation_context"]["source_counts"] == {
        "diagnostic_overlay": 5,
    }
    assert payload["metrics"]["descriptive_evaluation_context"]["variant_counts"] == {
        "unit_full:t01": 4,
        "unit_full:t02": 1,
    }
    assert payload["metrics"]["descriptive_evaluation_context"][
        "unique_signal_count"
    ] < payload["rows_used"]
    assert payload["metrics"]["row_reconstruction"]["local_paper_replay_changed"] is False
    assert payload["source_evidence"]["all_reference_fills_local_paper"] is True
    assert payload["source_evidence"]["local_paper_reference_fill_count"] == 2
    assert payload["result_scope"]["local_paper_replay_changed"] is False
    assert Path(payload["artifacts"]["model"]).exists()


def test_feature_input_ablation_resolves_model_artifact_lineage_paths(tmp_path) -> None:
    artifact_root = tmp_path / "model-artifacts"

    host_style = _resolve_lineage_path(
        "D:\\thericher-v2\\model-artifacts\\candidate-probability-trace\\unit\\trace.json",
        artifact_root=artifact_root,
    )
    docker_style = _resolve_lineage_path(
        "/app/model_artifacts/candidate-probability-trace/unit/trace.json",
        artifact_root=artifact_root,
    )

    expected = artifact_root / "candidate-probability-trace" / "unit" / "trace.json"
    assert host_style == expected
    assert docker_style == expected
    assert _resolve_lineage_path("C:\\Users\\operator\\.env", artifact_root=artifact_root) is None
    assert (
        _resolve_lineage_path(
            "/app/model_artifacts/../secrets/.env",
            artifact_root=artifact_root,
        )
        is None
    )
    assert (
        _resolve_lineage_path(
            "D:\\thericher-v2\\model-artifacts\\..\\secrets\\.env",
            artifact_root=artifact_root,
        )
        is None
    )
    assert (
        _resolve_lineage_path(
            "/app/market_data/../secrets/.env",
            artifact_root=artifact_root,
        )
        is None
    )


def test_feature_input_ablation_descriptive_metrics_expose_majority_trap() -> None:
    metrics = _binary_classification_metrics(
        labels=(1, 1, 1, 0),
        probabilities=(0.95, 0.80, 0.70, 0.60),
    )

    assert metrics["majority_label"] == "adverse_or_no_lift"
    assert metrics["majority_accuracy"] == "0.750000"
    assert metrics["accuracy"] == "0.750000"
    assert metrics["balanced_accuracy"] == "0.500000"
    assert metrics["negative_recall"] == "0.000000"
    assert metrics["log_loss"] is not None


def test_feature_input_ablation_auc_ties_and_single_class_groups() -> None:
    tied = _binary_classification_metrics(
        labels=(1, 0, 1, 0),
        probabilities=(0.50, 0.50, 0.50, 0.50),
    )
    assert tied["auc"] == "0.500000"
    assert tied["auc_tie_handling"] == "average_rank"
    assert tied["auc_tie_group_count"] == 1
    assert tied["auc_tied_score_count"] == 4

    payload = _descriptive_evaluation_payload(
        labels=(1, 1, 0),
        probabilities=(0.90, 0.55, 0.45),
        row_metadata=(
            {
                "source": "diagnostic_overlay",
                "slice_id": "single_positive",
                "variant_id": "v1",
                "slice_variant_id": "single_positive:v1",
            },
            {
                "source": "diagnostic_overlay",
                "slice_id": "single_positive",
                "variant_id": "v1",
                "slice_variant_id": "single_positive:v1",
            },
            {
                "source": "diagnostic_overlay",
                "slice_id": "single_negative",
                "variant_id": "v2",
                "slice_variant_id": "single_negative:v2",
            },
        ),
    )

    assert payload["scope"]["in_sample"] is True
    assert payload["by_slice"]["single_positive"]["auc"] is None
    assert payload["by_slice"]["single_positive"]["skip_reason"] == "single_class"
    assert payload["by_slice"]["single_negative"]["balanced_accuracy"] is None
    assert payload["context"]["diagnostic_overlay_rows_only"] is True
    assert payload["unique_signal_descriptive_evaluation"]["context"][
        "missing_signal_key_row_count"
    ] == 3
    assert payload["unique_signal_descriptive_evaluation"]["context"][
        "scored_unique_signal_count"
    ] == 0
    bands = payload["unique_signal_descriptive_evaluation"]["probability_band_diagnostics"]
    assert bands["context"]["skip_reason"] == "no_scored_unique_signals"
    assert bands["bands"] == {}


def test_feature_input_ablation_unique_signal_mean_collapse_is_deterministic() -> None:
    labels = (1, 1, 0, 0)
    probabilities = (0.10, 0.90, 0.60, 0.70)
    metadata = (
        _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t01"),
        _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t02"),
        _unique_signal_metadata("unit", "AAA", "2026-01-02T14:31:00+00:00", "2", "t01"),
        _unique_signal_metadata("unit", "AAA", "2026-01-02T14:31:00+00:00", "2", "t02"),
    )

    payload = _unique_signal_descriptive_evaluation(
        labels=labels,
        probabilities=probabilities,
        row_metadata=metadata,
    )
    reversed_payload = _unique_signal_descriptive_evaluation(
        labels=tuple(reversed(labels)),
        probabilities=tuple(reversed(probabilities)),
        row_metadata=tuple(reversed(metadata)),
    )

    assert payload == reversed_payload
    assert payload["aggregation_policy"]["score"] == "mean_probability_across_threshold_variants"
    assert payload["aggregation_policy"]["variant_selection"] == "none"
    assert payload["context"]["unique_signal_count"] == 2
    assert payload["context"]["scored_unique_signal_count"] == 2
    assert payload["context"]["variant_count_histogram"] == {"2": 2}
    assert payload["context"]["score_span_max"] == "0.800000"
    assert payload["overall"]["auc"] == "0.000000"
    assert payload["delta_vs_row_level"]["unique_minus_row_auc"] == "-0.500000"


def test_feature_input_ablation_unique_signal_mixed_labels_are_reported() -> None:
    payload = _unique_signal_descriptive_evaluation(
        labels=(1, 0, 0),
        probabilities=(0.80, 0.20, 0.30),
        row_metadata=(
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t01"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t02"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:31:00+00:00", "2", "t01"),
        ),
    )

    assert payload["context"]["unique_signal_count"] == 2
    assert payload["context"]["skipped_mixed_label_signal_count"] == 1
    assert payload["context"]["skipped_mixed_label_row_count"] == 2
    assert payload["context"]["scored_unique_signal_count"] == 1
    assert payload["overall"]["balanced_accuracy"] is None
    assert payload["overall"]["auc"] is None
    assert payload["overall"]["skip_reason"] == "single_class"
    assert payload["probability_band_diagnostics"]["context"][
        "skip_reason"
    ] == "insufficient_signals"


def test_feature_input_ablation_probability_bands_are_deterministic() -> None:
    labels = (0, 0, 1, 0, 1, 1)
    probabilities = (0.10, 0.20, 0.30, 0.70, 0.80, 0.90)
    metadata = (
        _unique_signal_metadata("slice_a", "AAA", "2026-01-02T14:30:00+00:00", "1", "t01"),
        _unique_signal_metadata("slice_a", "AAA", "2026-01-02T14:31:00+00:00", "2", "t01"),
        _unique_signal_metadata("slice_a", "AAA", "2026-01-02T14:32:00+00:00", "3", "t01"),
        _unique_signal_metadata("slice_b", "BBB", "2026-01-02T14:30:00+00:00", "1", "t01"),
        _unique_signal_metadata("slice_b", "BBB", "2026-01-02T14:31:00+00:00", "2", "t01"),
        _unique_signal_metadata("slice_b", "BBB", "2026-01-02T14:32:00+00:00", "3", "t01"),
    )

    bands = _probability_band_diagnostics(
        labels=labels,
        probabilities=probabilities,
        row_metadata=metadata,
    )
    reversed_bands = _probability_band_diagnostics(
        labels=tuple(reversed(labels)),
        probabilities=tuple(reversed(probabilities)),
        row_metadata=tuple(reversed(metadata)),
    )

    assert bands == reversed_bands
    assert bands["policy"]["family"] == "global_rank_tertile"
    assert bands["policy"]["per_slice_edges"] is False
    assert bands["policy"]["threshold_search"] is False
    assert bands["scope"]["band_selection"] == "none"
    assert bands["context"]["overall_adverse_or_no_lift_rate"] == "0.500000"
    assert bands["bands"]["tertile_1_low_probability"]["adverse_or_no_lift_rate"] == "0.000000"
    assert bands["bands"]["tertile_1_low_probability"][
        "lift_vs_overall_adverse_or_no_lift_rate"
    ] == "0.000000"
    assert bands["bands"]["tertile_2_mid_probability"]["adverse_or_no_lift_rate"] == "0.500000"
    assert bands["bands"]["tertile_3_high_probability"]["adverse_or_no_lift_rate"] == "1.000000"
    assert bands["bands"]["tertile_3_high_probability"][
        "lift_vs_overall_adverse_or_no_lift_rate"
    ] == "2.000000"
    assert bands["bands"]["tertile_3_high_probability"]["by_slice"]["slice_b"]["count"] == 2


def test_feature_input_ablation_probability_bands_skip_degenerate_scores() -> None:
    bands = _probability_band_diagnostics(
        labels=(1, 0, 1),
        probabilities=(0.50, 0.50, 0.50),
        row_metadata=(
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t01"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:31:00+00:00", "2", "t01"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:32:00+00:00", "3", "t01"),
        ),
    )

    assert bands["context"]["skip_reason"] == "tied_probabilities"
    assert bands["context"]["scored_unique_signal_count"] == 3
    assert bands["bands"] == {}


def test_feature_input_ablation_raw_band_attribution_is_deterministic() -> None:
    labels = (0, 0, 1, 0, 1, 1)
    probabilities = (0.10, 0.20, 0.30, 0.70, 0.80, 0.90)
    metadata = (
        _unique_signal_metadata("slice_a", "AAA", "2026-01-02T14:30:00+00:00", "1", "t01"),
        _unique_signal_metadata("slice_a", "AAA", "2026-01-02T14:31:00+00:00", "2", "t01"),
        _unique_signal_metadata("slice_a", "AAA", "2026-01-02T14:32:00+00:00", "3", "t01"),
        _unique_signal_metadata("slice_b", "BBB", "2026-01-02T14:30:00+00:00", "1", "t01"),
        _unique_signal_metadata("slice_b", "BBB", "2026-01-02T14:31:00+00:00", "2", "t01"),
        _unique_signal_metadata("slice_b", "BBB", "2026-01-02T14:32:00+00:00", "3", "t01"),
    )
    features = (
        (1.0, 0.10, 0.10, 10.0),
        (2.0, 0.20, 0.20, 20.0),
        (3.0, 0.30, 0.30, 30.0),
        (4.0, 0.40, 0.40, 40.0),
        (5.0, 0.50, 0.50, 50.0),
        (6.0, 0.60, 0.60, 0.0),
    )

    payload = _unique_signal_descriptive_evaluation(
        labels=labels,
        probabilities=probabilities,
        row_metadata=metadata,
        feature_names=RAW_PRE_ENTRY_FEATURE_NAMES,
        features=features,
        missing_value_row_indexes={"pre_last_volume_vs_prior_avg": (5,)},
    )
    reversed_payload = _unique_signal_descriptive_evaluation(
        labels=tuple(reversed(labels)),
        probabilities=tuple(reversed(probabilities)),
        row_metadata=tuple(reversed(metadata)),
        feature_names=RAW_PRE_ENTRY_FEATURE_NAMES,
        features=tuple(reversed(features)),
        missing_value_row_indexes={"pre_last_volume_vs_prior_avg": (0,)},
    )

    assert payload == reversed_payload
    attribution = payload["raw_pre_entry_band_attribution"]
    assert set(attribution["scope"]) == {
        "in_sample",
        "descriptive_only",
        "band_selection",
        "held_out_split",
        "local_paper_replay_changed",
    }
    assert attribution["scope"]["descriptive_only"] is True
    assert attribution["scope"]["band_selection"] == "none"
    assert attribution["scope"]["local_paper_replay_changed"] is False
    assert attribution["policy"]["threshold_search"] is False
    assert attribution["policy"]["feature_rule"] is False
    assert attribution["context"]["source_counts"] == {"diagnostic_overlay": 6}
    assert attribution["context"]["diagnostic_overlay_rows_only"] is True
    assert attribution["context"]["skip_reason"] is None
    high = attribution["bands"]["tertile_3_high_probability"]
    assert high["count"] == 2
    assert high["by_slice"]["slice_b"]["count"] == 2
    close_summary = high["raw_feature_summaries"]["pre_close_return"]
    assert close_summary["signal_count"] == 2
    assert close_summary["mean"] == "5.500000"
    assert close_summary["median"] == "5.500000"
    assert close_summary["min"] == "5.000000"
    assert close_summary["max"] == "6.000000"
    volume_summary = high["raw_feature_summaries"]["pre_last_volume_vs_prior_avg"]
    assert volume_summary["value_count"] == 1
    assert volume_summary["missing_value_count"] == 1
    assert volume_summary["mean"] == "50.000000"
    comparisons = attribution["comparisons"]
    assert comparisons["tertile_3_high_probability_vs_overall"]["pre_close_return"][
        "mean_delta"
    ] == "2.000000"
    assert comparisons["tertile_3_high_probability_vs_tertile_1_low_probability"][
        "pre_close_return"
    ]["median_delta"] == "4.000000"


def test_feature_input_ablation_raw_band_attribution_skips_incomplete_keys() -> None:
    payload = _unique_signal_descriptive_evaluation(
        labels=(1, 0, 1),
        probabilities=(0.10, 0.40, 0.90),
        row_metadata=(
            {"source": "diagnostic_overlay", "slice_id": "unit"},
            {"source": "diagnostic_overlay", "symbol": "AAA"},
            {"source": "diagnostic_overlay", "offset": "3"},
        ),
        feature_names=RAW_PRE_ENTRY_FEATURE_NAMES,
        features=(
            (1.0, 0.10, 0.10, 10.0),
            (2.0, 0.20, 0.20, 20.0),
            (3.0, 0.30, 0.30, 30.0),
        ),
    )

    attribution = payload["raw_pre_entry_band_attribution"]
    assert attribution["context"]["missing_signal_key_row_count"] == 3
    assert attribution["context"]["scored_unique_signal_count"] == 0
    assert attribution["context"]["skip_reason"] == "no_scored_unique_signals"
    assert attribution["bands"] == {}
    assert attribution["overall_raw_feature_summaries"]["pre_close_return"][
        "signal_count"
    ] == 0


def test_feature_input_ablation_raw_band_attribution_skips_mixed_labels() -> None:
    payload = _unique_signal_descriptive_evaluation(
        labels=(1, 0, 0, 1, 1),
        probabilities=(0.95, 0.05, 0.20, 0.60, 0.90),
        row_metadata=(
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t01"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:30:00+00:00", "1", "t02"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:31:00+00:00", "2", "t01"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:32:00+00:00", "3", "t01"),
            _unique_signal_metadata("unit", "AAA", "2026-01-02T14:33:00+00:00", "4", "t01"),
        ),
        feature_names=RAW_PRE_ENTRY_FEATURE_NAMES,
        features=(
            (999.0, 0.10, 0.10, 10.0),
            (-999.0, 0.20, 0.20, 20.0),
            (1.0, 0.30, 0.30, 30.0),
            (2.0, 0.40, 0.40, 40.0),
            (3.0, 0.50, 0.50, 50.0),
        ),
    )

    attribution = payload["raw_pre_entry_band_attribution"]
    assert attribution["context"]["skipped_mixed_label_signal_count"] == 1
    assert attribution["context"]["skipped_mixed_label_row_count"] == 2
    assert attribution["context"]["scored_unique_signal_count"] == 3
    assert attribution["overall_raw_feature_summaries"]["pre_close_return"]["mean"] == "2.000000"
    assert attribution["bands"]["tertile_3_high_probability"]["raw_feature_summaries"][
        "pre_close_return"
    ]["mean"] == "3.000000"


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
    assert "thericher_v2.execution" not in source
    assert "localpaperbroker" not in source
    assert "orderintent" not in source
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


def _unique_signal_metadata(
    slice_id: str,
    symbol: str,
    execution_bar_start: str,
    offset: str,
    variant_id: str,
) -> dict[str, str]:
    return {
        "source": "diagnostic_overlay",
        "slice_id": slice_id,
        "symbol": symbol,
        "execution_bar_start": execution_bar_start,
        "offset": offset,
        "variant_id": variant_id,
        "slice_variant_id": f"{slice_id}:{variant_id}",
    }


def _lineage_stability_artifact(
    tmp_path: Path,
    artifact_root: Path,
    *,
    market_data_root: Path,
) -> Path:
    market_data = _lineage_yahoo_snapshot(market_data_root)
    trace_path = artifact_root / "candidate-probability-trace" / "unit" / "trace.json"
    trace_path.parent.mkdir(parents=True)
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    probabilities = (0.40, 0.48, 0.51, 0.56, 0.62, 0.53, 0.45, 0.49)
    trace_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "schema_version": 1,
                        "offset": index,
                        "probability": probability,
                        "signal_bar_start": (
                            start + timedelta(minutes=max(index - 1, 0))
                        ).isoformat(),
                        "execution_bar_start": (
                            start + timedelta(minutes=index)
                        ).isoformat(),
                        "execution_open": f"{100 + index * 0.20:.4f}",
                    }
                    for index, probability in enumerate(probabilities)
                ],
            }
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "lineage-stability.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "cross_slice_feature_input_stability_diagnostic_only",
                "consumed_slices": [
                    {
                        "slice_id": "unit_full",
                        "role": "holdout",
                        "symbol": "AAA",
                        "probability_trace_artifact": (
                            "D:\\thericher-v2\\model-artifacts"
                            "\\candidate-probability-trace\\unit\\trace.json"
                        ),
                        "local_market_data_path": str(market_data),
                    }
                ],
                "metrics": {
                    "added_source_variant_meta": [
                        {
                            "slice_id": "unit_full",
                            "symbol": "AAA",
                            "variant_id": "t01",
                            "buy_threshold": 0.50,
                            "sell_threshold": 0.46,
                            "candidate_entry_rows": 4,
                            "local_paper_fill_count": 2,
                        },
                        {
                            "slice_id": "unit_full",
                            "symbol": "AAA",
                            "variant_id": "t02",
                            "buy_threshold": 0.60,
                            "sell_threshold": 0.46,
                            "candidate_entry_rows": 1,
                            "local_paper_fill_count": 0,
                        },
                    ]
                },
                "source_evidence": {
                    "all_reference_fills_local_paper": True,
                    "local_paper_reference_fill_count": 2,
                    "diagnostic_overlay_source_counts": {"diagnostic_overlay": 5},
                    "diagnostic_rows_are_not_local_paper_fills": True,
                },
                "selected_candidate_entry_rows": [
                    {
                        "source": "local_paper",
                        "slice_id": "unit_full",
                        "early_3bar": {"path_quality_bucket": "early_lift"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return artifact


def _lineage_yahoo_snapshot(tmp_path: Path) -> Path:
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
        for index in range(12):
            timestamp = start + timedelta(minutes=index)
            open_price = 100 + index * 0.20
            writer.writerow(
                {
                    "symbol": "AAA",
                    "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                    "timestamp_et": "",
                    "session_date": "2026-01-02",
                    "bar_time_et": "",
                    "open": f"{open_price:.4f}",
                    "high": f"{open_price + (0.15 if index % 2 else 0.45):.4f}",
                    "low": f"{open_price - (0.35 if index % 3 == 0 else 0.05):.4f}",
                    "close": f"{open_price + (0.08 if index % 2 else -0.02):.4f}",
                    "volume": str(1000 + index * 10),
                    "source": "unit",
                }
            )
    return path

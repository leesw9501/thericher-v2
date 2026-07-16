from __future__ import annotations

import importlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from thericher_v2.execution.local_paper import LOCAL_PAPER_SOURCE
from thericher_v2.research.feature_input_ablation import (
    RAW_PRE_ENTRY_FEATURE_NAMES,
    UNIQUE_SIGNAL_KEY_FIELDS,
)
from thericher_v2.research.raw_pre_entry_outcome_attribution import (
    RAW_SIGNAL_KEY_FIELDS,
    RawPreEntryOutcomeAttributionConfig,
    attribute_local_paper_outcomes_by_raw_pre_entry_context,
    run_bounded_raw_pre_entry_outcome_attribution,
)

BROKER_DISABLED_SOURCE = "broker_disabled"


def test_raw_pre_entry_outcome_attribution_summarizes_local_paper_evidence() -> None:
    diagnostic_rows = (
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v1",
            timestamp="2026-01-02T23:30:00+09:00",
            offset=1,
            close_position="0.10",
            bucket="pre_entry_down",
        ),
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v1",
            timestamp="2026-01-02T23:31:00+09:00",
            offset=2,
            close_position="0.20",
            bucket="pre_entry_down",
        ),
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v2",
            timestamp="2026-01-02T23:32:00+09:00",
            offset=3,
            close_position="0.80",
            bucket="pre_entry_up",
        ),
        _diagnostic_row(
            slice_id="slice_b",
            variant_id="v1",
            timestamp="2026-01-02T23:33:00+09:00",
            offset=4,
            close_position="0.90",
            bucket="pre_entry_up",
            entered_local_paper=True,
        ),
    )
    closed_segments = (
        _closed_segment(
            slice_id="slice_a",
            variant_id="v1",
            timestamp="2026-01-02T14:30:00+00:00",
            gross_delta="1.25",
            fee_aware_delta="1.20",
        ),
    )
    open_segments = (
        _open_segment(
            slice_id="slice_a",
            variant_id="v1",
            timestamp="2026-01-02T14:31:00+00:00",
            window_gross_delta="-0.35",
        ),
    )
    fill_events = (
        _fill_event("slice_a", "v1", "2026-01-02T14:30:00+00:00", LOCAL_PAPER_SOURCE),
        _fill_event("slice_a", "v1", "2026-01-02T14:30:00+00:00", LOCAL_PAPER_SOURCE),
        _fill_event("slice_a", "v1", "2026-01-02T14:31:00+00:00", LOCAL_PAPER_SOURCE),
        _fill_event(
            "slice_a",
            "wrong_variant",
            "2026-01-02T14:32:00+00:00",
            LOCAL_PAPER_SOURCE,
        ),
        _fill_event(
            "slice_a",
            "v2",
            "2026-01-02T14:32:00+00:00",
            BROKER_DISABLED_SOURCE,
        ),
    )

    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=diagnostic_rows,
        local_paper_closed_segments=closed_segments,
        local_paper_open_segments=open_segments,
        local_paper_fill_events=fill_events,
        local_paper_verification={
            "all_fills_local_paper": False,
            "local_paper_fill_count": 2,
            "non_local_fill_source_counts": {BROKER_DISABLED_SOURCE: 1},
        },
    )

    overall = payload["overall"]
    assert payload["scope"]["local_paper_replay_changed"] is False
    assert payload["scope"]["broker_used"] is False
    assert payload["scope"]["credentials_read"] is False
    assert payload["context"]["diagnostic_source_counts"] == {"diagnostic_overlay": 4}
    assert payload["context"]["local_paper_source_counts"] == {
        BROKER_DISABLED_SOURCE: 1,
        LOCAL_PAPER_SOURCE: 4,
    }
    assert payload["context"]["non_local_fill_source_count"] == 1
    assert overall["diagnostic_observation_count"] == 4
    assert overall["unique_signal_count"] == 4
    assert overall["local_paper_entry_fill_count"] == 2
    assert overall["local_paper_fill_event_count"] == 3
    assert overall["diagnostic_without_local_paper_entry_fill_count"] == 2
    assert overall["closed_local_paper_path_count"] == 1
    assert overall["open_local_paper_path_count"] == 1
    assert overall["closed_gross_delta_sum"] == "1.25"
    assert overall["closed_fee_aware_delta_sum"] == "1.2"
    assert overall["open_window_gross_delta_sum"] == "-0.35"
    assert overall["missing_local_paper_entry_evidence_count"] == 1
    assert overall["non_local_fill_source_count"] == 1

    down_bucket = payload["by_pre_entry_bucket"]["pre_entry_down"]
    assert down_bucket["diagnostic_observation_count"] == 2
    assert down_bucket["local_paper_entry_fill_count"] == 2
    assert down_bucket["closed_local_paper_path_count"] == 1
    assert down_bucket["open_local_paper_path_count"] == 1


def test_raw_pre_entry_outcome_attribution_raw_feature_tertiles_are_deterministic() -> None:
    diagnostic_rows = tuple(
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v1",
            timestamp=f"2026-01-02T14:3{index}:00+00:00",
            offset=index,
            close_position=str(value),
            bucket="pre_entry_up",
        )
        for index, value in enumerate(("0.10", "0.20", "0.80", "0.90"))
    )
    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=diagnostic_rows,
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(),
        local_paper_verification={"all_fills_local_paper": True},
    )
    reversed_payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=tuple(reversed(diagnostic_rows)),
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(),
        local_paper_verification={"all_fills_local_paper": True},
    )

    bands = payload["by_raw_feature_tertile"]["pre_last_close_position_in_range"]
    reversed_bands = reversed_payload["by_raw_feature_tertile"][
        "pre_last_close_position_in_range"
    ]

    assert bands == reversed_bands
    assert bands["policy"]["threshold_search"] is False
    assert bands["policy"]["feature_rule"] is False
    assert bands["context"]["skip_reason"] is None
    assert bands["bands"]["tertile_1_low_value"]["diagnostic_observation_count"] == 2
    assert bands["bands"]["tertile_2_mid_value"]["diagnostic_observation_count"] == 1
    assert bands["bands"]["tertile_3_high_value"]["diagnostic_observation_count"] == 1


def test_raw_pre_entry_outcome_attribution_uses_exact_variant_entry_join() -> None:
    diagnostic_rows = (
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v1",
            timestamp="2026-01-02T23:30:00+09:00",
            offset=1,
            close_position="0.10",
            bucket="pre_entry_down",
        ),
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v2",
            timestamp="2026-01-02T23:30:00+09:00",
            offset=1,
            close_position="0.20",
            bucket="pre_entry_down",
        ),
    )

    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=diagnostic_rows,
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(
            _fill_event(
                "slice_a",
                "v1",
                "2026-01-02T14:30:00+00:00",
                LOCAL_PAPER_SOURCE,
                symbol="aaa",
            ),
            _fill_event(
                "slice_a",
                "v2",
                "2026-01-02T14:30:00+00:00",
                LOCAL_PAPER_SOURCE,
                symbol="BBB",
            ),
        ),
        local_paper_verification={"all_fills_local_paper": True},
    )

    overall = payload["overall"]
    assert overall["diagnostic_observation_count"] == 2
    assert overall["unique_signal_count"] == 1
    assert overall["local_paper_entry_fill_count"] == 1
    assert overall["local_paper_fill_event_count"] == 1
    assert overall["diagnostic_without_local_paper_entry_fill_count"] == 1


def test_raw_pre_entry_outcome_attribution_reports_missing_trade_paths() -> None:
    diagnostic_rows = (
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v1",
            timestamp="2026-01-02T14:30:00+00:00",
            offset=1,
            close_position="0.10",
            bucket="pre_entry_down",
            entered_local_paper=True,
        ),
    )

    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=diagnostic_rows,
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(
            _fill_event("slice_a", "v1", "2026-01-02T14:30:00+00:00", LOCAL_PAPER_SOURCE),
        ),
        local_paper_verification={
            "all_fills_local_paper": True,
            "local_paper_fill_count": 1,
            "non_local_fill_source_counts": {},
        },
    )

    overall = payload["overall"]
    assert overall["local_paper_entry_fill_count"] == 1
    assert overall["missing_local_paper_entry_evidence_count"] == 0
    assert overall["missing_trade_path_evidence_count"] == 1


def test_raw_pre_entry_outcome_attribution_excludes_missing_raw_values() -> None:
    rows = [
        _diagnostic_row(
            slice_id="slice_a",
            variant_id="v1",
            timestamp=f"2026-01-02T14:3{index}:00+00:00",
            offset=index,
            close_position=str(value),
            bucket="pre_entry_up",
        )
        for index, value in enumerate(("0.10", "0.20", "0.80", "0.90"))
    ]
    for index, value in enumerate(("10.0", "20.0", "30.0")):
        pre_entry = rows[index]["pre_entry_3bar"]
        assert isinstance(pre_entry, dict)
        pre_entry["last_volume_vs_prior_avg"] = value
    rows[-1]["pre_entry_3bar"].pop("last_volume_vs_prior_avg")  # type: ignore[union-attr]

    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=tuple(rows),
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(),
        local_paper_verification={"all_fills_local_paper": True},
    )

    volume = payload["by_raw_feature_tertile"]["pre_last_volume_vs_prior_avg"]
    assert volume["context"]["diagnostic_observation_count"] == 4
    assert volume["context"]["scored_observation_count"] == 3
    assert volume["context"]["missing_raw_value_count"] == 1
    assert volume["context"]["skip_reason"] is None
    assert all(
        band["diagnostic_observation_count"] == 1 for band in volume["bands"].values()
    )


def test_raw_pre_entry_outcome_attribution_excludes_non_diagnostic_rows() -> None:
    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=(
            _diagnostic_row(
                slice_id="slice_a",
                variant_id="v1",
                timestamp="2026-01-02T14:30:00+00:00",
                offset=1,
                close_position="0.10",
                bucket="pre_entry_down",
            ),
            {
                **_diagnostic_row(
                    slice_id="slice_a",
                    variant_id="v1",
                    timestamp="2026-01-02T14:31:00+00:00",
                    offset=2,
                    close_position="0.20",
                    bucket="pre_entry_down",
                ),
                "source": LOCAL_PAPER_SOURCE,
            },
        ),
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(),
        local_paper_verification={"all_fills_local_paper": True},
    )

    assert payload["overall"]["diagnostic_observation_count"] == 1
    assert payload["context"]["diagnostic_source_counts"] == {"diagnostic_overlay": 1}


def test_raw_pre_entry_outcome_attribution_rejects_repo_artifact_root(tmp_path) -> None:
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_raw_pre_entry_outcome_attribution(
            config=RawPreEntryOutcomeAttributionConfig(run_id="bad-root"),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            stability_artifact=tmp_path / "missing-stability.json",
            raw_band_artifact=tmp_path / "missing-band.json",
        )


def test_raw_pre_entry_outcome_attribution_reports_missing_artifacts(
    tmp_path,
) -> None:
    artifact_root = tmp_path / "model-artifacts"

    result = run_bounded_raw_pre_entry_outcome_attribution(
        config=RawPreEntryOutcomeAttributionConfig(run_id="missing-contract"),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        stability_artifact=tmp_path / "missing-stability.json",
        raw_band_artifact=tmp_path / "missing-band.json",
        checked_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    payload = json.loads(result.attribution_artifact.read_text(encoding="utf-8"))
    artifact_path = Path(payload["artifacts"]["raw_pre_entry_outcome_attribution"])
    assert result.status == "prepared_not_raw_pre_entry_outcome_attributed"
    assert "artifact path is missing" in result.reason
    assert result.rows_seen == 0
    assert result.rows_used == 0
    assert payload["status"] == "prepared_not_raw_pre_entry_outcome_attributed"
    assert payload["metrics"]["overall"]["diagnostic_observation_count"] == 0
    assert payload["metrics"]["overall"]["missing_local_paper_entry_evidence_count"] == 0
    assert payload["metrics"]["source_raw_band_context"] == {"available": False}
    assert set(payload["metrics"]["scope"]) == {
        "in_sample",
        "descriptive_only",
        "local_paper_replay_changed",
        "broker_used",
        "kis_api_called",
        "credentials_read",
        "threshold_search",
        "feature_rule",
    }
    assert payload["result_scope"]["descriptive_only"] is True
    assert payload["result_scope"]["promotion_gate"] is False
    assert payload["result_scope"]["local_paper_replay_changed"] is False
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_path.resolve().is_relative_to(artifact_root.resolve())
    rendered = json.dumps(payload).lower()
    for forbidden in ("winner", "recommendation", "production ready", "live ready"):
        assert forbidden not in rendered


def test_raw_pre_entry_outcome_attribution_is_not_a_research_job_kind() -> None:
    from thericher_v2.research import jobs

    assert "raw_pre_entry_outcome_attribution" not in jobs.SUPPORTED_RESEARCH_JOB_KINDS
    assert "raw_pre_entry_outcome" not in jobs.SUPPORTED_RESEARCH_JOB_KINDS
    with pytest.raises(SystemExit):
        jobs.build_parser().parse_args(["--kind", "raw_pre_entry_outcome_attribution"])


def test_raw_pre_entry_outcome_attribution_reuses_feature_signal_key_contract() -> None:
    assert RAW_SIGNAL_KEY_FIELDS == UNIQUE_SIGNAL_KEY_FIELDS
    payload = attribute_local_paper_outcomes_by_raw_pre_entry_context(
        diagnostic_rows=(),
        local_paper_closed_segments=(),
        local_paper_open_segments=(),
        local_paper_fill_events=(),
        local_paper_verification={"all_fills_local_paper": True},
    )
    assert tuple(payload["context"]["raw_feature_names"]) == RAW_PRE_ENTRY_FEATURE_NAMES
    assert tuple(payload["by_raw_feature_tertile"]) == RAW_PRE_ENTRY_FEATURE_NAMES


def test_raw_pre_entry_outcome_attribution_import_does_not_load_broker_module() -> None:
    sys.modules.pop("thericher_v2.research.raw_pre_entry_outcome_attribution", None)
    sys.modules.pop("thericher_v2.research.trade_path_attribution", None)
    sys.modules.pop("thericher_v2.execution.broker", None)

    importlib.import_module("thericher_v2.research.raw_pre_entry_outcome_attribution")

    assert "thericher_v2.execution.broker" not in sys.modules


def test_raw_pre_entry_outcome_attribution_import_has_no_broker_submit_paths() -> None:
    import thericher_v2.research.raw_pre_entry_outcome_attribution as attribution

    source = Path(attribution.__file__).read_text(encoding="utf-8").lower()
    assert "requests" not in source
    assert "os.environ" not in source
    assert "localpaperbroker" not in source
    assert "orderintent" not in source
    assert "submit_order" not in source
    assert "submit_and_fill" not in source
    assert "kis_api_called" in source


def _diagnostic_row(
    *,
    slice_id: str,
    variant_id: str,
    timestamp: str,
    offset: int,
    close_position: str,
    bucket: str,
    entered_local_paper: bool = False,
    symbol: str = "AAA",
) -> dict[str, object]:
    return {
        "source": "diagnostic_overlay",
        "slice_id": slice_id,
        "variant_id": variant_id,
        "symbol": symbol,
        "execution_bar_start": timestamp,
        "offset": offset,
        "pre_entry_3bar": {
            "bucket": bucket,
            "close_return": "0.001",
            "range_pct_of_last_close": "0.002",
            "last_close_position_in_range": close_position,
            "last_volume_vs_prior_avg": "0.003",
        },
        "local_paper_reference": {
            "entered_local_paper": entered_local_paper,
            "source": LOCAL_PAPER_SOURCE if entered_local_paper else None,
        },
    }


def _fill_event(
    slice_id: str,
    variant_id: str,
    timestamp: str,
    source: str,
    *,
    symbol: str = "AAA",
) -> dict[str, object]:
    return {
        "slice_id": slice_id,
        "variant_id": variant_id,
        "symbol": symbol,
        "created_at": timestamp,
        "side": "buy",
        "source": source,
    }


def _closed_segment(
    *,
    slice_id: str,
    variant_id: str,
    timestamp: str,
    gross_delta: str,
    fee_aware_delta: str,
) -> dict[str, object]:
    return {
        "slice_id": slice_id,
        "variant_id": variant_id,
        "symbol": "AAA",
        "entry": {
            "timestamp": timestamp,
            "source": LOCAL_PAPER_SOURCE,
        },
        "gross_delta": gross_delta,
        "fee_aware_delta": fee_aware_delta,
    }


def _open_segment(
    *,
    slice_id: str,
    variant_id: str,
    timestamp: str,
    window_gross_delta: str,
) -> dict[str, object]:
    return {
        "slice_id": slice_id,
        "variant_id": variant_id,
        "symbol": "AAA",
        "entry": {
            "timestamp": timestamp,
            "source": LOCAL_PAPER_SOURCE,
        },
        "window_end": {
            "gross_delta": window_gross_delta,
        },
    }

import csv
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.research.candidate_feature_branch_replay_prefilter import (
    CandidateFeatureBranchReplayPrefilterConfig,
    CandidateFeatureBranchReplayPrefilterSliceConfig,
    run_bounded_candidate_feature_branch_replay_opportunity_prefilter,
)


def test_feature_branch_replay_prefilter_ranks_trace_candidates(tmp_path) -> None:
    artifact_root, feature_branch_artifact, model_artifact = _feature_branch_artifact(
        tmp_path
    )
    snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA", "BBB"))
    aaa_trace = _trace_artifact(
        artifact_root,
        run_id="trace-aaa",
        snapshot=snapshot,
        symbol="AAA",
        model_artifact=model_artifact,
        probabilities=(0.500, 0.542, 0.498),
    )
    bbb_trace = _trace_artifact(
        artifact_root,
        run_id="trace-bbb",
        snapshot=snapshot,
        symbol="BBB",
        model_artifact=model_artifact,
        probabilities=(0.501, 0.530, 0.499),
    )

    result = run_bounded_candidate_feature_branch_replay_opportunity_prefilter(
        config=CandidateFeatureBranchReplayPrefilterConfig(
            run_id="unit-prefilter",
            min_examples=2,
            candidates=(
                CandidateFeatureBranchReplayPrefilterSliceConfig(
                    slice_id="bbb",
                    yahoo_snapshot=snapshot,
                    symbol="BBB",
                    probability_trace_artifact=bbb_trace,
                ),
                CandidateFeatureBranchReplayPrefilterSliceConfig(
                    slice_id="aaa",
                    yahoo_snapshot=snapshot,
                    symbol="AAA",
                    probability_trace_artifact=aaa_trace,
                ),
            ),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_artifact=feature_branch_artifact,
    )

    payload = json.loads(result.prefilter_artifact.read_text(encoding="utf-8"))
    assert result.status == "research_prefilter_only"
    assert result.min_derived_buy_threshold == pytest.approx(0.541)
    assert [item["symbol"] for item in result.candidate_summaries] == ["AAA", "BBB"]
    assert result.candidate_summaries[0]["trace"]["threshold_gap"] == "0.001000"
    assert result.candidate_summaries[0]["candidate_for_one_bounded_local_replay"] is True
    assert result.candidate_summaries[1]["candidate_for_one_bounded_local_replay"] is False
    assert [item["symbol"] for item in result.replay_candidate_slices] == ["AAA"]
    assert payload["metrics"]["scored_candidate_count"] == 2
    assert payload["metrics"]["threshold_crossing_candidate_count"] == 1
    assert payload["metrics"]["candidate_for_one_bounded_local_replay_count"] == 1
    assert payload["metrics"]["order_intents_created"] == 0
    assert payload["metrics"]["fills_created"] == 0
    assert payload["prefilter_scope"]["mode"] == "research_prefilter_only"
    assert payload["prefilter_scope"]["no_execution_authority"] is True
    assert payload["prefilter_scope"]["no_promotion_semantics"] is True
    assert payload["boundaries"]["broker_submit"] is False
    assert payload["boundaries"]["kis_api"] is False
    assert payload["boundaries"]["credential_read"] is False
    assert payload["artifact_policy"]["repo_storage_allowed"] is False
    assert artifact_root.resolve() in result.prefilter_artifact.resolve().parents
    rendered = json.dumps(payload).lower()
    assert "should_replay" not in rendered
    assert "winner" not in rendered
    assert "approved" not in rendered
    assert "execution_threshold" not in rendered


def test_feature_branch_replay_prefilter_excludes_and_does_not_compute_by_default(
    tmp_path,
) -> None:
    artifact_root, feature_branch_artifact, model_artifact = _feature_branch_artifact(
        tmp_path
    )
    snapshot = _yahoo_snapshot(tmp_path, symbols=("AAPL", "CCC"))
    aapl_trace = _trace_artifact(
        artifact_root,
        run_id="trace-aapl",
        snapshot=snapshot,
        symbol="AAPL",
        model_artifact=model_artifact,
        probabilities=(0.700, 0.710),
    )

    result = run_bounded_candidate_feature_branch_replay_opportunity_prefilter(
        config=CandidateFeatureBranchReplayPrefilterConfig(
            run_id="unit-prefilter-excluded",
            candidates=(
                CandidateFeatureBranchReplayPrefilterSliceConfig(
                    slice_id="aapl",
                    yahoo_snapshot=snapshot,
                    symbol="AAPL",
                    probability_trace_artifact=aapl_trace,
                ),
                CandidateFeatureBranchReplayPrefilterSliceConfig(
                    slice_id="ccc",
                    yahoo_snapshot=snapshot,
                    symbol="CCC",
                ),
            ),
        ),
        artifact_root=artifact_root,
        repo_root=Path.cwd(),
        feature_branch_artifact=feature_branch_artifact,
    )

    payload = json.loads(result.prefilter_artifact.read_text(encoding="utf-8"))
    by_symbol = {item["symbol"]: item for item in payload["candidate_summaries"]}
    assert by_symbol["AAPL"]["status"] == "excluded_by_prefilter_scope"
    assert by_symbol["AAPL"]["candidate_for_one_bounded_local_replay"] is False
    assert by_symbol["CCC"]["status"] == "prepared_not_scored"
    assert "trace compute is disabled" in by_symbol["CCC"]["reason"]
    assert payload["prefilter_scope"]["allow_trace_compute"] is False
    assert payload["metrics"]["trace_missing_or_unavailable_count"] == 1
    assert payload["metrics"]["threshold_crossing_candidate_count"] == 0
    assert payload["replay_candidate_slices"] == []
    assert payload["boundaries"]["replay_run"] is False
    assert payload["boundaries"]["order_intents_created"] is False
    assert payload["boundaries"]["fills_created"] is False


def test_feature_branch_replay_prefilter_rejects_repo_artifact_root(tmp_path) -> None:
    artifact_root, feature_branch_artifact, model_artifact = _feature_branch_artifact(
        tmp_path
    )
    snapshot = _yahoo_snapshot(tmp_path, symbols=("AAA",))
    trace = _trace_artifact(
        artifact_root,
        run_id="trace-aaa",
        snapshot=snapshot,
        symbol="AAA",
        model_artifact=model_artifact,
        probabilities=(0.542,),
    )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_bounded_candidate_feature_branch_replay_opportunity_prefilter(
            config=CandidateFeatureBranchReplayPrefilterConfig(
                run_id="repo-prefilter",
                candidates=(
                    CandidateFeatureBranchReplayPrefilterSliceConfig(
                        slice_id="aaa",
                        yahoo_snapshot=snapshot,
                        symbol="AAA",
                        probability_trace_artifact=trace,
                    ),
                ),
            ),
            artifact_root=Path.cwd() / "model-artifacts",
            repo_root=Path.cwd(),
            feature_branch_artifact=feature_branch_artifact,
        )


def _feature_branch_artifact(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifact_root = tmp_path / "model-artifacts"
    training = artifact_root / "candidate-training" / "unit" / "metrics.json"
    evaluation = artifact_root / "candidate-evaluation" / "unit" / "metrics.json"
    model = artifact_root / "candidate-training" / "unit" / "model.pt"
    feature_branch = artifact_root / "candidate-feature-branch" / "unit" / "metrics.json"
    for path in (training, evaluation, model, feature_branch):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    feature_branch.write_text(
        json.dumps(
            {
                "status": "candidate_feature_branch_evaluated_only",
                "metrics": {
                    "probability_evidence": {
                        "max_probability": "0.543403",
                        "mean_probability": "0.497777",
                    },
                },
                "artifacts": {
                    "candidate_training": str(training),
                    "candidate_evaluation": str(evaluation),
                    "model": str(model),
                },
            }
        ),
        encoding="utf-8",
    )
    return artifact_root, feature_branch, model


def _trace_artifact(
    artifact_root: Path,
    *,
    run_id: str,
    snapshot: Path,
    symbol: str,
    model_artifact: Path,
    probabilities: tuple[float, ...],
) -> Path:
    path = artifact_root / "candidate-probability-trace" / run_id / "trace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    entries = [
        {
            "offset": index,
            "probability": probability,
            "signal_bar_start": (start + timedelta(minutes=index)).isoformat(),
            "signal_bar_end": (start + timedelta(minutes=index + 1)).isoformat(),
            "execution_bar_start": (start + timedelta(minutes=index + 1)).isoformat(),
            "execution_bar_end": (start + timedelta(minutes=index + 2)).isoformat(),
            "signal_close": "100",
            "execution_open": "100",
            "execution_close": "100",
            "contiguous": True,
        }
        for index, probability in enumerate(probabilities)
    ]
    path.write_text(
        json.dumps(
            {
                "status": "probability_traced_only",
                "run_id": run_id,
                "reason": "unit trace",
                "data_source": str(snapshot),
                "symbol": symbol,
                "examples_seen": len(entries),
                "entries": entries,
                "artifacts": {"source_model": str(model_artifact)},
            }
        ),
        encoding="utf-8",
    )
    return path


def _yahoo_snapshot(tmp_path: Path, *, symbols: tuple[str, ...]) -> Path:
    path = tmp_path / "market-data" / "ohlcv_1m.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        for symbol in symbols:
            for index in range(12):
                timestamp = start + timedelta(minutes=index)
                writer.writerow(
                    {
                        "symbol": symbol,
                        "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
                        "timestamp_et": "",
                        "session_date": "2026-01-02",
                        "bar_time_et": "",
                        "open": "100",
                        "high": "101",
                        "low": "99",
                        "close": "100",
                        "volume": "1000",
                        "source": "unit",
                    }
                )
    return path

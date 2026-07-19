from __future__ import annotations

import json
import socket
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy
import pytest

from thericher_v2.research.norgate_broad_development_validation import (
    CUDA_JOB_SPECS,
    DEVELOPMENT_END_INDEX,
    DEVELOPMENT_START_INDEX,
    FEATURE_WIDTH,
    FIXED_PARENT_DATASET_HASH,
    FIXED_PARENT_MANIFEST_HASH,
    PURGE_END_INDEX,
    VALIDATION_END_INDEX,
    NorgateBroadDevelopmentDataset,
    _dataset_from_verified_feature_artifact,
    run_norgate_broad_development_cpu_baseline,
    run_norgate_broad_development_cuda_job,
)


def test_cpu_baseline_is_offline_date_clustered_and_external(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("broad development validation must not use a network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("broad development validation must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()

    result = run_norgate_broad_development_cpu_baseline(
        _dataset(tmp_path),
        artifact_root=artifact_root,
        repo_root=repo,
        code_revision="unit-test",
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert result.summary_path.is_file()
    assert result.summary_path.is_relative_to(artifact_root)
    assert payload["scope"]["engineering_only"] is True
    assert payload["scope"]["ensemble_eligible"] is False
    assert payload["attestations"] == {
        "offline": True,
        "network_access": False,
        "credential_access": False,
        "broker_access": False,
        "local_paper_execution": False,
    }
    assert payload["temporal_split"]["development_date_groups"] == 300
    assert payload["temporal_split"]["validation_date_groups"] == 159
    validation = payload["cpu_baselines"]["regularized_linear"]["validation"]
    assert validation["date_group_count"] == 159
    assert validation["iid_claim"] is False
    assert len(validation["contiguous_date_blocks"]) == 5
    assert "after_cost_pnl" not in json.dumps(payload)


def test_rejects_lookahead_or_noncanonical_rows(tmp_path: Path) -> None:
    artifact_root = tmp_path / "model-artifacts"
    artifact_root.mkdir()
    dataset = _dataset(tmp_path)
    broken_start = replace(
        dataset,
        source_start_indices=numpy.asarray(dataset.source_start_indices) + 1,
    )
    with pytest.raises(ValueError, match="source and label index"):
        run_norgate_broad_development_cpu_baseline(
            broken_start,
            artifact_root=artifact_root,
            repo_root=tmp_path / "repo",
        )

    broken_order = replace(
        dataset,
        symbol_ranks=numpy.asarray(dataset.symbol_ranks)[::-1],
    )
    with pytest.raises(ValueError, match="canonical date/rank order"):
        run_norgate_broad_development_cpu_baseline(
            broken_order,
            artifact_root=artifact_root,
            run_id="broken-order",
            repo_root=tmp_path / "repo",
        )


def test_rejects_artifacts_inside_git_and_cuda_before_cpu(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact_root = repo / "model-artifacts"
    artifact_root.mkdir()
    dataset = _dataset(tmp_path)
    with pytest.raises(ValueError, match="outside the Git workspace"):
        run_norgate_broad_development_cpu_baseline(
            dataset,
            artifact_root=artifact_root,
            repo_root=repo,
        )

    external = tmp_path / "external-artifacts"
    external.mkdir()
    with pytest.raises(ValueError, match="CPU baseline is required"):
        run_norgate_broad_development_cuda_job(
            dataset,
            artifact_root=external,
            repo_root=repo,
            job_id="mlp-seed-71",
        )


def test_cuda_requires_checkpoint_reload_evidence_and_pins_fixed_parent_rows(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact_root = tmp_path / "external-artifacts"
    artifact_root.mkdir()
    dataset = _dataset(tmp_path)
    run_norgate_broad_development_cpu_baseline(
        dataset,
        artifact_root=artifact_root,
        run_id="unsafe-trainer",
        repo_root=repo,
    )

    def unsafe_trainer(*args: object) -> tuple[numpy.ndarray, dict[str, object]]:
        checkpoint_path = args[-1]
        assert isinstance(checkpoint_path, Path)
        checkpoint_path.write_bytes(b"not-a-safe-checkpoint")
        return numpy.full(318, 0.5, dtype=numpy.float32), {}

    with pytest.raises(ValueError, match="safe weights-only checkpoint reload"):
        run_norgate_broad_development_cuda_job(
            dataset,
            artifact_root=artifact_root,
            run_id="unsafe-trainer",
            repo_root=repo,
            job_id="mlp-seed-71",
            trainer=unsafe_trainer,
        )

    source = _dataset(tmp_path)
    fake = SimpleNamespace(
        contract={
            "scope": {
                "engineering_cuda_exploration_eligible": True,
                "point_in_time_eligible": False,
                "ranking_eligible": False,
                "sealed_holdout_eligible": False,
                "campaign_eligible": False,
                "model_eligible": False,
                "model_promotion_eligible": False,
                "gpu_eligible": False,
                "paper_trading_eligible": False,
                "pnl_eligible": False,
                "profitability_eligible": False,
            },
            "parent_panel": {
                "raw_scope": {"model_eligible": False, "gpu_eligible": False},
                "dataset_hash": FIXED_PARENT_DATASET_HASH,
                "manifest_hash": FIXED_PARENT_MANIFEST_HASH,
                "selected_symbol_count": 2,
            },
            "transform": {
                "feature_return_count": FEATURE_WIDTH,
                "feature_source_index_range": "t-20..t",
                "max_feature_source_index": "t",
                "entry_index": "t+1",
                "exit_index": "t+2",
            },
            "discontinuity_conditioning": {"checked_index_range": "t-20..t+2"},
            "row_counts": {"development": 600, "purge": 4, "validation": 318},
            "limitations": ["unit limitation"],
        },
        artifact_dir=source.artifact_dir,
        artifact_hash=source.artifact_hash,
        contract_hash=source.contract_hash,
        parent_dataset_hash=FIXED_PARENT_DATASET_HASH,
        parent_manifest_hash=FIXED_PARENT_MANIFEST_HASH,
        feature_array=source.features,
        label_array=source.labels,
        decision_indices=source.decision_indices,
        decision_dates=source.decision_dates,
        source_start_indices=source.source_start_indices,
        source_end_indices=source.source_end_indices,
        entry_indices=source.entry_indices,
        exit_indices=source.exit_indices,
        symbol_ranks=source.symbol_ranks,
        split_ids=numpy.asarray(
            [
                0 if value == "development" else 1 if value == "purge" else 2
                for value in source.split_ids
            ],
            dtype=numpy.int8,
        ),
    )
    with pytest.raises(ValueError, match="fixed Norgate parent row counts"):
        _dataset_from_verified_feature_artifact(fake)


def test_cuda_batch_is_fixed_and_diverse_without_ensemble_selection() -> None:
    assert [(item.model_family, item.seed) for item in CUDA_JOB_SPECS] == [
        ("mlp", 71),
        ("mlp", 113),
        ("temporal_conv", 71),
        ("temporal_conv", 113),
    ]
    assert all(item.epochs == 24 and item.batch_size == 4096 for item in CUDA_JOB_SPECS)
    source = Path(
        "src/thericher_v2/research/norgate_broad_development_validation.py"
    ).read_text(encoding="utf-8").lower()
    assert "thericher_v2.execution" not in source
    assert "localpaperbroker" not in source
    assert "kis" not in source
    assert "requests" not in source


def _dataset(tmp_path: Path) -> NorgateBroadDevelopmentDataset:
    rows: list[tuple[int, int]] = []
    for decision_index in range(DEVELOPMENT_START_INDEX, VALIDATION_END_INDEX + 1):
        for symbol_rank in (1, 2):
            rows.append((decision_index, symbol_rank))
    count = len(rows)
    decision_indices = numpy.asarray([item[0] for item in rows], dtype=numpy.int64)
    symbol_ranks = numpy.asarray([item[1] for item in rows], dtype=numpy.int64)
    offsets = numpy.arange(FEATURE_WIDTH, dtype=numpy.float64)
    features = numpy.asarray(
        [
            ((decision_index + symbol_rank + offsets) % 11 - 5) / 100
            for decision_index, symbol_rank in rows
        ],
        dtype=numpy.float64,
    )
    labels = ((decision_indices + symbol_ranks) % 2).astype(numpy.int8)
    split_ids = numpy.asarray(
        [
            "development"
            if value <= DEVELOPMENT_END_INDEX
            else "purge"
            if value <= PURGE_END_INDEX
            else "validation"
            for value in decision_indices
        ]
    )
    dates = numpy.datetime64("2024-01-01") + decision_indices.astype("timedelta64[D]")
    assert count == 2 * (VALIDATION_END_INDEX - DEVELOPMENT_START_INDEX + 1)
    assert split_ids.tolist().count("development") == 2 * 300
    assert split_ids.tolist().count("purge") == 2 * 2
    assert split_ids.tolist().count("validation") == 2 * 159
    return NorgateBroadDevelopmentDataset(
        artifact_dir=tmp_path / "derived-feature-artifact",
        artifact_hash="sha256:" + "a" * 64,
        contract_hash="sha256:" + "b" * 64,
        parent_dataset_hash="sha256:" + "c" * 64,
        parent_manifest_hash="sha256:" + "d" * 64,
        features=features,
        labels=labels,
        decision_indices=decision_indices,
        decision_dates=dates,
        source_start_indices=decision_indices - FEATURE_WIDTH,
        source_end_indices=decision_indices,
        entry_indices=decision_indices + 1,
        exit_indices=decision_indices + 2,
        symbol_ranks=symbol_ranks,
        split_ids=split_ids,
        discontinuity_excluded_count=0,
        limitations=("unit limitation",),
    )

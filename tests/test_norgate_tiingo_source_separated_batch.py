from __future__ import annotations

import ast
import json
import socket
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

import numpy
import pytest

import thericher_v2.research.norgate_tiingo_source_separated_batch as batch
from thericher_v2.research.norgate_tiingo_source_separated_contract import (
    NorgateTiingoSourceSeparatedContract,
)
from thericher_v2.research.tiingo_norgate_cross_source_intake import (
    TiingoNorgateSourceSeparationContractInput,
)


def test_cpu_batch_is_offline_external_and_development_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("source-separated batch must not use a network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("source-separated batch must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    repo, root = _roots(tmp_path, "baseline")
    dataset = _dataset(tmp_path)
    result = batch.run_norgate_tiingo_source_separated_cpu_baseline(
        dataset,
        artifact_root=root,
        repo_root=repo,
        code_revision="unit-test",
    )

    payload = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert result.summary_path.is_relative_to(root)
    assert payload["scope"] == batch._RESULT_SCOPE
    assert payload["attestations"] == {
        "offline": True,
        "network_access": False,
        "credential_access": False,
        "broker_access": False,
        "local_paper_execution": False,
        "artifact_outside_git": True,
    }
    assert payload["temporal_split"] == {
        "fit_decision_indices": [20, 319],
        "purge_decision_indices": [320, 321],
        "purge_used_for_fit": False,
        "purge_used_for_evaluation": False,
        "validation_decision_indices": [322, 480],
        "validation_used_for_fixed_engineering_evaluation_only": True,
        "development_label_exit_max_index": 321,
        "validation_decision_start_index": 322,
    }
    assert payload["evaluation_policy"]["candidate_selection_eligible"] is False
    assert payload["scope"]["pnl_eligible"] is False
    assert "after_cost" not in json.dumps(payload).lower()

    poison = _poison_non_development_rows(dataset)
    poison_repo, poison_root = _roots(tmp_path, "poison")
    poisoned = batch.run_norgate_tiingo_source_separated_cpu_baseline(
        poison,
        artifact_root=poison_root,
        repo_root=poison_repo,
        code_revision="unit-test",
    )
    poison_payload = json.loads(poisoned.summary_path.read_text(encoding="utf-8"))
    assert (
        payload["cpu_baselines"]["development_preprocessing"]
        == poison_payload["cpu_baselines"]["development_preprocessing"]
    )
    assert (
        payload["cpu_baselines"]["regularized_linear"]["weights_sha256"]
        == poison_payload["cpu_baselines"]["regularized_linear"]["weights_sha256"]
    )
    assert (
        payload["cpu_baselines"]["regularized_linear"]["bias"]
        == poison_payload["cpu_baselines"]["regularized_linear"]["bias"]
    )


def test_loader_reattests_contract_parents_without_tiingo_prices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo, root = _roots(tmp_path, "loader")
    dataset = _dataset(tmp_path)
    contract, cohort, feature = _parents_for_loader(tmp_path)
    calls: list[str] = []

    def load_contract(*_args: object, **_kwargs: object) -> NorgateTiingoSourceSeparatedContract:
        calls.append("contract")
        return contract

    def load_cohort(
        *_args: object, **_kwargs: object
    ) -> TiingoNorgateSourceSeparationContractInput:
        calls.append("cohort")
        return cohort

    def load_feature(*_args: object, **_kwargs: object) -> Any:
        calls.append("feature")
        return feature

    monkeypatch.setattr(
        batch, "load_verified_norgate_tiingo_source_separated_contract", load_contract
    )
    monkeypatch.setattr(
        batch, "load_verified_tiingo_norgate_source_separation_contract_input", load_cohort
    )
    monkeypatch.setattr(
        batch, "load_verified_norgate_broad_development_feature_artifact", load_feature
    )
    monkeypatch.setattr(batch, "_dataset_from_verified_parents", lambda *_args: dataset)

    loaded = batch.load_verified_norgate_tiingo_source_separated_batch_dataset(
        contract_artifact_dir=tmp_path / "contract",
        cohort_artifact_dir=tmp_path / "cohort",
        feature_artifact_dir=tmp_path / "feature",
        artifact_root=root,
        market_data_root=tmp_path / "market-data",
        repo_root=repo,
    )

    assert loaded is dataset
    assert calls == ["contract", "cohort", "feature"]


def test_cuda_uses_only_fixed_rows_and_replayable_external_artifacts(tmp_path: Path) -> None:
    repo, root = _roots(tmp_path, "cuda")
    dataset = _dataset(tmp_path)
    batch.run_norgate_tiingo_source_separated_cpu_baseline(
        dataset,
        artifact_root=root,
        repo_root=repo,
        code_revision="unit-test",
    )
    observed: dict[str, object] = {}

    def trainer(
        spec: batch.SourceSeparatedCudaJobSpec,
        development_features: numpy.ndarray,
        development_labels: numpy.ndarray,
        validation_features: numpy.ndarray,
        checkpoint_path: Path,
        _monotonic: object,
    ) -> tuple[numpy.ndarray, dict[str, object]]:
        observed["job_id"] = spec.job_id
        observed["development_shape"] = development_features.shape
        observed["development_labels"] = development_labels.copy()
        observed["validation_shape"] = validation_features.shape
        checkpoint_path.write_bytes(b"test-safe-checkpoint")
        return numpy.full(len(validation_features), 0.5, dtype=numpy.float32), _trainer_evidence()

    result = batch.run_norgate_tiingo_source_separated_cuda_job(
        dataset,
        artifact_root=root,
        repo_root=repo,
        code_revision="unit-test",
        job_id="mlp-hidden-32-seed-71",
        trainer=trainer,
    )

    assert observed["job_id"] == "mlp-hidden-32-seed-71"
    assert observed["development_shape"] == (6_434, batch.FEATURE_WIDTH)
    assert observed["validation_shape"] == (3_420, batch.FEATURE_WIDTH)
    development = numpy.asarray(dataset.split_ids) == "development"
    expected_development_labels = numpy.asarray(dataset.labels)[development]
    assert numpy.array_equal(observed["development_labels"], expected_development_labels)
    assert result.summary_path.is_relative_to(root)
    assert result.checkpoint_path.is_relative_to(root)
    assert result.prediction_path.is_relative_to(root)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["cuda_job"]["selection_eligible"] is False
    assert summary["cuda_job"]["ensemble_eligible"] is False
    assert summary["cuda_job"]["validation_predictions"]["sha256"] == result.prediction_sha256
    with numpy.load(result.prediction_path, allow_pickle=False) as predictions:
        assert predictions["decision_indices"].min() == 322
        assert predictions["decision_indices"].max() == 480
        assert len(predictions["probabilities"]) == 3_420


def test_cuda_lock_failure_and_stopped_job_are_not_retried(tmp_path: Path) -> None:
    repo, root = _roots(tmp_path, "cuda-failure")
    dataset = _dataset(tmp_path)
    batch.run_norgate_tiingo_source_separated_cpu_baseline(
        dataset,
        artifact_root=root,
        repo_root=repo,
        code_revision="unit-test",
    )
    lock_path = batch._source_separated_cuda_lock_path(root)
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("occupied", encoding="utf-8")
    with pytest.raises(batch.SourceSeparatedGpuLockHeldError):
        batch.run_norgate_tiingo_source_separated_cuda_job(
            dataset,
            artifact_root=root,
            repo_root=repo,
            code_revision="unit-test",
            job_id="mlp-hidden-32-seed-71",
            trainer=_fake_trainer,
        )
    lock_path.unlink()

    calls: list[str] = []

    def stopped_trainer(
        *_args: object, **_kwargs: object
    ) -> tuple[numpy.ndarray, dict[str, object]]:
        calls.append("called")
        raise batch.SourceSeparatedCudaJobStopped(
            "wall_clock_cap_exceeded", elapsed_seconds=180.0, peak_memory_bytes=1
        )

    with pytest.raises(batch.SourceSeparatedCudaJobStopped, match="wall_clock_cap_exceeded"):
        batch.run_norgate_tiingo_source_separated_cuda_job(
            dataset,
            artifact_root=root,
            repo_root=repo,
            code_revision="unit-test",
            job_id="mlp-hidden-32-seed-71",
            trainer=stopped_trainer,
        )
    job_dir = batch.default_norgate_tiingo_source_separated_batch_dir(
        artifact_root=root
    ) / "cuda" / "mlp-hidden-32-seed-71"
    failure = json.loads((job_dir / "failure.json").read_text(encoding="utf-8"))
    assert failure["cuda_failure"]["automatic_retry_permitted"] is False
    assert not (job_dir / "checkpoint.pt").exists()
    assert not (job_dir / "validation-predictions.npz").exists()
    with pytest.raises(FileExistsError, match="already has evidence"):
        batch.run_norgate_tiingo_source_separated_cuda_job(
            dataset,
            artifact_root=root,
            repo_root=repo,
            code_revision="unit-test",
            job_id="mlp-hidden-32-seed-71",
            trainer=stopped_trainer,
        )
    assert calls == ["called"]


def test_rejects_git_artifacts_forward_rows_and_runtime_imports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    inside_repo = repo / "model-artifacts"
    inside_repo.mkdir()
    with pytest.raises(ValueError, match="outside the Git workspace"):
        batch.run_norgate_tiingo_source_separated_cpu_baseline(
            _dataset(tmp_path),
            artifact_root=inside_repo,
            repo_root=repo,
            code_revision="unit-test",
        )

    dataset = _dataset(tmp_path)
    exit_indices = numpy.asarray(dataset.exit_indices).copy()
    decision_indices = numpy.asarray(dataset.decision_indices).copy()
    source_start = numpy.asarray(dataset.source_start_indices).copy()
    source_end = numpy.asarray(dataset.source_end_indices).copy()
    entry_indices = numpy.asarray(dataset.entry_indices).copy()
    decision_indices[-1] = 481
    source_start[-1] = 461
    source_end[-1] = 481
    entry_indices[-1] = 482
    exit_indices[-1] = 483
    invalid = replace(
        dataset,
        decision_indices=decision_indices,
        source_start_indices=source_start,
        source_end_indices=source_end,
        entry_indices=entry_indices,
        exit_indices=exit_indices,
    )
    external = tmp_path / "external-artifacts"
    external.mkdir()
    with pytest.raises(ValueError, match="split timing|forward-only"):
        batch.run_norgate_tiingo_source_separated_cpu_baseline(
            invalid,
            artifact_root=external,
            repo_root=repo,
            code_revision="unit-test",
        )

    source = Path("src/thericher_v2/research/norgate_tiingo_source_separated_batch.py")
    module = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for statement in module.body
        if isinstance(statement, (ast.Import, ast.ImportFrom))
        for alias in statement.names
    }
    text = source.read_text(encoding="utf-8").lower()
    assert "torch" not in imports
    for forbidden in ("thericher_v2.execution", "localpaperbroker", "requests", "socket"):
        assert forbidden not in text


def _roots(tmp_path: Path, name: str) -> tuple[Path, Path]:
    repo = tmp_path / f"repo-{name}"
    root = tmp_path / f"artifacts-{name}"
    repo.mkdir()
    root.mkdir()
    return repo, root


def _dataset(tmp_path: Path) -> batch.NorgateTiingoSourceSeparatedBatchDataset:
    ranks = tuple((rank, f"S{rank:03d}") for rank in range(1, 30))
    targets = {"development": 6_434, "purge": 50, "validation": 3_420}
    candidates = {key: [] for key in targets}
    for decision_index in range(20, 481):
        split = _split_for_index(decision_index)
        for rank, _symbol in ranks:
            candidates[split].append((decision_index, rank, split))
    rows = [
        row
        for split, target in targets.items()
        for row in (*candidates[split][: target - 1], candidates[split][-1])
    ]
    rows.sort()
    assert {split: sum(row[2] == split for row in rows) for split in targets} == targets
    decision_indices = numpy.asarray([row[0] for row in rows], dtype=numpy.int64)
    symbol_ranks = numpy.asarray([row[1] for row in rows], dtype=numpy.int64)
    split_ids = numpy.asarray([row[2] for row in rows], dtype="U16")
    offsets = numpy.arange(batch.FEATURE_WIDTH, dtype=numpy.float64)
    features = numpy.asarray(
        [((decision + rank + offsets) % 17 - 8) / 100 for decision, rank, _split in rows],
        dtype=numpy.float64,
    )
    labels = ((decision_indices + symbol_ranks) % 2).astype(numpy.int8)
    dates = numpy.asarray(
        [(date(2024, 1, 1) + timedelta(days=int(value))).isoformat() for value in decision_indices]
    )
    contract = _contract(ranks, excluded_by_rank={rank: () for rank, _symbol in ranks})
    return batch.NorgateTiingoSourceSeparatedBatchDataset(
        contract_dir=tmp_path / "contract",
        contract_hash="sha256:" + "a" * 64,
        cohort_manifest_hash="sha256:" + "b" * 64,
        feature_artifact_hash="sha256:" + "c" * 64,
        feature_contract_hash="sha256:" + "d" * 64,
        selected_slice_sha256="sha256:" + "e" * 64,
        features=features,
        labels=labels,
        decision_indices=decision_indices,
        decision_dates=dates,
        source_start_indices=decision_indices - batch.FEATURE_WIDTH,
        source_end_indices=decision_indices,
        entry_indices=decision_indices + 1,
        exit_indices=decision_indices + 2,
        symbol_ranks=symbol_ranks,
        split_ids=split_ids,
        rank_symbols=ranks,
        sample_counts=MappingProxyType(_expected_counts()),
        norgate_retention=MappingProxyType(
            {
                "norgate_origin_data": True,
                "parent_deletion_requires_derived_deletion": True,
                "automated_deletion": False,
                "marker_file": "DELETE_ON_PARENT_EXPIRY.txt",
            }
        ),
        contract=MappingProxyType(contract),
    )


def _poison_non_development_rows(
    dataset: batch.NorgateTiingoSourceSeparatedBatchDataset,
) -> batch.NorgateTiingoSourceSeparatedBatchDataset:
    features = numpy.asarray(dataset.features).copy()
    labels = numpy.asarray(dataset.labels).copy()
    not_development = numpy.asarray(dataset.split_ids) != "development"
    features[not_development] = 9_999.0
    labels[not_development] = 1 - labels[not_development]
    return replace(dataset, features=features, labels=labels)


def _parents_for_loader(
    tmp_path: Path,
) -> tuple[
    NorgateTiingoSourceSeparatedContract,
    TiingoNorgateSourceSeparationContractInput,
    SimpleNamespace,
]:
    ranks = tuple((rank, f"S{rank:03d}") for rank in range(1, 30))
    excluded_by_rank = {rank: [] for rank, _symbol in ranks}
    candidate_pairs = [
        (decision, rank)
        for decision in range(20, 481)
        for rank, _symbol in ranks
    ]
    for decision, rank in candidate_pairs[:3_316]:
        excluded_by_rank[rank].append(decision)
    excluded = {rank: tuple(values) for rank, values in excluded_by_rank.items()}
    overlap_dates = tuple(
        (date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(483)
    )
    cohort = TiingoNorgateSourceSeparationContractInput(
        artifact_dir=tmp_path / "cohort",
        manifest_hash="sha256:" + "b" * 64,
        tiingo_dataset_hash="sha256:" + "f" * 64,
        tiingo_manifest_hash="sha256:" + "0" * 64,
        norgate_dataset_hash="sha256:" + "1" * 64,
        norgate_manifest_hash="sha256:" + "2" * 64,
        rank_symbols=ranks,
        overlap_session_dates=overlap_dates,
        forward_only_session_dates=tuple("forward" for _ in range(18)),
        overlap_marker_indices_by_rank=MappingProxyType({rank: () for rank, _ in ranks}),
        forward_only_marker_indices_by_rank=MappingProxyType({rank: () for rank, _ in ranks}),
        excluded_decision_indices_by_rank=MappingProxyType(excluded),
        feature_lookback=20,
        entry_offset=1,
        exit_offset=2,
    )
    feature = SimpleNamespace(
        artifact_hash="sha256:" + "c" * 64,
        contract_hash="sha256:" + "d" * 64,
        manifest_hash="sha256:" + "3" * 64,
        parent_dataset_hash=cohort.norgate_dataset_hash,
        parent_manifest_hash=cohort.norgate_manifest_hash,
        contract={
            "retention": {
                "norgate_origin_data": True,
                "parent_deletion_requires_derived_deletion": True,
                "automated_deletion": False,
                "marker_file": "DELETE_ON_PARENT_EXPIRY.txt",
            }
        },
    )
    contract_payload = _contract(
        ranks,
        excluded_by_rank=excluded,
        cohort=cohort,
        feature=feature,
    )
    contract = NorgateTiingoSourceSeparatedContract(
        artifact_dir=tmp_path / "contract",
        contract_hash="sha256:" + "a" * 64,
        cohort_manifest_hash=cohort.manifest_hash,
        feature_artifact_hash=feature.artifact_hash,
        feature_contract_hash=feature.contract_hash,
        rank_count=29,
        retained_feature_row_count=9_904,
        development_row_count=6_434,
        purge_row_count=50,
        validation_row_count=3_420,
        contract=MappingProxyType(contract_payload),
    )
    return contract, cohort, feature


def _contract(
    rank_symbols: tuple[tuple[int, str], ...],
    *,
    excluded_by_rank: dict[int, tuple[int, ...]] | dict[int, list[int]],
    cohort: TiingoNorgateSourceSeparationContractInput | None = None,
    feature: SimpleNamespace | None = None,
) -> dict[str, object]:
    pairs = [{"candidate_rank": rank, "symbol": symbol} for rank, symbol in rank_symbols]
    mask_rows = [
        {
            "candidate_rank": rank,
            "overlap_marker_indices": [],
            "forward_only_marker_indices": [],
            "excluded_decision_indices": list(excluded_by_rank[rank]),
        }
        for rank, _symbol in rank_symbols
    ]
    payload: dict[str, object] = {
        "scope": dict(batch._CONTRACT_SCOPE),
        "source_roles": {
            "norgate": "sole_price_feature_label_source",
            "tiingo": "rank_session_and_returned_marker_mask_only",
            "source_price_mixing": False,
            "forward_only_tiingo_session_use": False,
        },
        "rank_selection": {
            "rule": "exact_cohort_candidate_rank_and_symbol_pairs",
            "rank_count": 29,
            "pairs": pairs,
            "pairs_sha256": batch._sha256_json(pairs),
        },
        "temporal_geometry": {
            "feature_source_index_range": "t-20..t",
            "entry_index": "t+1",
            "exit_index": "t+2",
            "maximum_used_dependency_index": 482,
            "first_forward_only_tiingo_index": 483,
            "forward_only_sessions_used": False,
            "development_decision_index_range": [20, 319],
            "purge_decision_index_range": [320, 321],
            "validation_decision_index_range": [322, 480],
            "purge_observed_sessions": 2,
            "embargo_observed_sessions_for_any_later_fold_or_refit": 2,
            "post_validation_embargo_consumed": False,
        },
        "sample_counts": _expected_counts(),
        "future_batch": {
            "cpu_baselines": ["naive_always_long", "regularized_linear"],
            "cuda_candidates": [
                {
                    "id": spec.job_id,
                    "family": "mlp",
                    "hidden_width": spec.hidden_width,
                    "seed": spec.seed,
                    "epochs": spec.epochs,
                    "batch_size": spec.batch_size,
                }
                for spec in batch.CUDA_JOB_SPECS
            ],
            "cuda_max_concurrent_jobs": 1,
            "cuda_per_job_wall_clock_cap_seconds": batch.CUDA_WALL_CLOCK_CAP_SECONDS,
            "cuda_per_job_vram_cap_mib": batch.CUDA_VRAM_CAP_MIB,
            "no_candidate_ranking_or_promotion": True,
        },
        "conservative_marker_mask": {
            "per_rank_sha256": batch._sha256_json(mask_rows),
            "cohort_excluded_pair_count": sum(len(value) for value in excluded_by_rank.values()),
            "forward_only_marker_pair_effect": "none",
        },
        "norgate_feature_conditioning": {"rows_removed_after_tiingo_marker_mask": 149},
    }
    if cohort is not None and feature is not None:
        payload["parents"] = {
            "cohort": {
                "manifest_hash": cohort.manifest_hash,
                "norgate_dataset_hash": cohort.norgate_dataset_hash,
                "norgate_manifest_hash": cohort.norgate_manifest_hash,
            },
            "norgate_feature_artifact": {
                "artifact_hash": feature.artifact_hash,
                "contract_hash": feature.contract_hash,
            },
        }
    return payload


def _trainer_evidence() -> dict[str, object]:
    return {
        "backend": "torch_cuda",
        "safe_weights_only_reload": True,
        "elapsed_seconds": 1.0,
        "peak_memory_bytes": 1024,
        "vram_cap_bytes": batch.CUDA_VRAM_CAP_MIB * 1024 * 1024,
        "vram_cap_enforcement": "torch_allocator_fraction_and_peak_accounting",
        "vram_cap_is_physical_partition": False,
        "wall_clock_cap_seconds": batch.CUDA_WALL_CLOCK_CAP_SECONDS,
        "wall_clock_hard_timer_enforced": True,
        "wall_clock_enforcement": "unix_itimer_plus_monotonic_batch_checks",
    }


def _fake_trainer(
    _spec: batch.SourceSeparatedCudaJobSpec,
    _development_features: numpy.ndarray,
    _development_labels: numpy.ndarray,
    validation_features: numpy.ndarray,
    checkpoint_path: Path,
    _monotonic: object,
) -> tuple[numpy.ndarray, dict[str, object]]:
    checkpoint_path.write_bytes(b"test-safe-checkpoint")
    return numpy.full(len(validation_features), 0.5, dtype=numpy.float32), _trainer_evidence()


def _expected_counts() -> dict[str, int]:
    return {
        "potential_rank_decision_pairs": 13_369,
        "after_tiingo_marker_mask": 10_053,
        "after_existing_norgate_feature_conditioning": 9_904,
        "development": 6_434,
        "purge": 50,
        "validation": 3_420,
    }


def _split_for_index(decision_index: int) -> str:
    if decision_index <= 319:
        return "development"
    if decision_index <= 321:
        return "purge"
    return "validation"

from __future__ import annotations

import json
import socket
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

import thericher_v2.research.norgate_tiingo_source_separated_contract as contract_module
from thericher_v2.research.tiingo_norgate_cross_source_intake import (
    TiingoNorgateSourceSeparationContractInput,
)


def test_builds_compact_offline_contract_with_conservative_mask(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, repo = _roots(tmp_path)
    cohort, feature = _parents(tmp_path)
    _stub_parents(monkeypatch, cohort, feature)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("source-separated contract must not use a network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("source-separated contract must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)
    result = contract_module.build_norgate_tiingo_source_separated_contract(
        artifact_root=root,
        repo_root=repo,
        expectation=_expectation(),
    )

    assert result.artifact_dir.is_relative_to(root)
    assert {entry.name for entry in result.artifact_dir.iterdir()} == {"contract.json"}
    assert (
        result.rank_count,
        result.retained_feature_row_count,
        result.development_row_count,
        result.purge_row_count,
        result.validation_row_count,
    ) == (29, 89, 31, 29, 29)
    assert result.contract["source_roles"] == {
        "norgate": "sole_price_feature_label_source",
        "tiingo": "rank_session_and_returned_marker_mask_only",
        "source_price_mixing": False,
        "forward_only_tiingo_session_use": False,
    }
    assert result.contract["sample_counts"] == {
        "potential_rank_decision_pairs": 13_369,
        "after_tiingo_marker_mask": 13_346,
        "after_existing_norgate_feature_conditioning": 89,
        "development": 31,
        "purge": 29,
        "validation": 29,
    }
    assert result.contract["norgate_feature_conditioning"][
        "rows_removed_after_tiingo_marker_mask"
    ] == 13_257
    assert any("not point-in-time safe" in item for item in result.contract["limitations"])
    assert result.contract["scope"]["future_bounded_batch_prepared"] is True
    assert all(
        value is False
        for key, value in result.contract["scope"].items()
        if key not in {"engineering_only", "future_bounded_batch_prepared"}
    )

    loaded = contract_module.load_verified_norgate_tiingo_source_separated_contract(
        result.artifact_dir,
        artifact_root=root,
        repo_root=repo,
        expectation=_expectation(),
    )
    assert loaded.contract_hash == result.contract_hash


def test_contract_rejects_tampering_parent_mismatch_and_repo_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, repo = _roots(tmp_path)
    cohort, feature = _parents(tmp_path)
    _stub_parents(monkeypatch, cohort, feature)
    result = contract_module.build_norgate_tiingo_source_separated_contract(
        artifact_root=root,
        repo_root=repo,
        expectation=_expectation(),
    )
    contract_path = result.artifact_dir / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source_roles"]["forward_only_tiingo_session_use"] = True
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ValueError, match="inconsistent"):
        contract_module.verify_norgate_tiingo_source_separated_contract(
            result.artifact_dir,
            artifact_root=root,
            repo_root=repo,
            expectation=_expectation(),
        )

    repo_artifacts = repo / "model-artifacts"
    repo_artifacts.mkdir()
    with pytest.raises(ValueError, match="outside the Git workspace"):
        contract_module.build_norgate_tiingo_source_separated_contract(
            artifact_root=repo_artifacts,
            repo_root=repo,
            expectation=_expectation(),
        )

    bad_feature = _feature(parent_dataset_hash="sha256:" + "9" * 64)
    _stub_parents(monkeypatch, cohort, bad_feature)
    alternate_root = tmp_path / "alternate-artifacts"
    alternate_root.mkdir()
    with pytest.raises(ValueError, match="parent lineage"):
        contract_module.build_norgate_tiingo_source_separated_contract(
            artifact_root=alternate_root,
            repo_root=repo,
            expectation=_expectation(),
        )


def test_contract_rejects_wrong_rank_symbol_linkage_and_has_no_runtime_imports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root, repo = _roots(tmp_path)
    cohort, feature = _parents(tmp_path)
    feature.contract["selected_symbols"][0]["symbol"] = "WRONG"
    _stub_parents(monkeypatch, cohort, feature)

    with pytest.raises(ValueError, match="rank/symbol linkage"):
        contract_module.build_norgate_tiingo_source_separated_contract(
            artifact_root=root,
            repo_root=repo,
            expectation=_expectation(),
        )

    source = Path(
        "src/thericher_v2/research/norgate_tiingo_source_separated_contract.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "thericher_v2.execution",
        "localpaperbroker",
        "torch",
        "requests",
        "socket",
    ):
        assert forbidden not in source


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "model-artifacts"
    repo = tmp_path / "repo"
    root.mkdir()
    repo.mkdir()
    return root, repo


def _stub_parents(
    monkeypatch: pytest.MonkeyPatch,
    cohort: TiingoNorgateSourceSeparationContractInput,
    feature: Any,
) -> None:
    monkeypatch.setattr(
        contract_module,
        "_load_parents",
        lambda **_kwargs: (cohort, feature),
    )


def _parents(tmp_path: Path) -> tuple[TiingoNorgateSourceSeparationContractInput, Any]:
    ranks = tuple((rank, f"S{rank:03d}") for rank in range(1, 30))
    overlap_dates = tuple(
        (date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(483)
    )
    forward_dates = tuple(
        (date(2025, 4, 28) + timedelta(days=index)).isoformat() for index in range(18)
    )
    excluded = {rank: () for rank, _symbol in ranks}
    excluded[1] = tuple(range(98, 121))
    overlap_markers = {rank: () for rank, _symbol in ranks}
    overlap_markers[1] = (100,)
    forward_markers = {rank: () for rank, _symbol in ranks}
    forward_markers[1] = (483,)
    cohort = TiingoNorgateSourceSeparationContractInput(
        artifact_dir=tmp_path / "cohort",
        manifest_hash="sha256:" + "a" * 64,
        tiingo_dataset_hash="sha256:" + "b" * 64,
        tiingo_manifest_hash="sha256:" + "c" * 64,
        norgate_dataset_hash="sha256:" + "d" * 64,
        norgate_manifest_hash="sha256:" + "e" * 64,
        rank_symbols=ranks,
        overlap_session_dates=overlap_dates,
        forward_only_session_dates=forward_dates,
        overlap_marker_indices_by_rank=MappingProxyType(overlap_markers),
        forward_only_marker_indices_by_rank=MappingProxyType(forward_markers),
        excluded_decision_indices_by_rank=MappingProxyType(excluded),
        feature_lookback=20,
        entry_offset=1,
        exit_offset=2,
    )
    return cohort, _feature()


def _feature(*, parent_dataset_hash: str = "sha256:" + "d" * 64) -> Any:
    ranks = list(range(1, 30))
    symbol_ranks = [rank for rank in ranks for _decision in (20, 320, 322)]
    decision_indices = [decision for _rank in ranks for decision in (20, 320, 322)]
    symbol_ranks.extend([1, 1, 1])
    decision_indices.extend([97, 100, 121])
    return SimpleNamespace(
        artifact_hash="sha256:" + "f" * 64,
        contract_hash="sha256:" + "1" * 64,
        manifest_hash="sha256:" + "2" * 64,
        parent_dataset_hash=parent_dataset_hash,
        parent_manifest_hash="sha256:" + "e" * 64,
        symbol_ranks=symbol_ranks,
        decision_indices=decision_indices,
        contract={
            "transform": {
                "feature_kind": "raw_close_to_close_returns",
                "feature_return_count": 20,
                "feature_return_end_index_range": "t-19..t",
                "feature_source_index_range": "t-20..t",
                "max_feature_source_index": "t",
                "entry_index": "t+1",
                "exit_index": "t+2",
                "label": "1 if open[t+2]/open[t+1]-1 > 0 else 0",
                "label_values": {"non_positive": 0, "positive": 1},
            },
            "selected_symbols": [
                {"candidate_rank": rank, "symbol": f"S{rank:03d}"}
                for rank in ranks
            ],
            "discontinuity_conditioning": {
                "checked_index_range": "t-20..t+2",
                "condition": (
                    "abs(open[i]/close[i-1]-1)>=0.20 or "
                    "abs(close[i]/close[i-1]-1)>=0.20"
                ),
                "does_not_assert_corporate_action": True,
                "exclusion_rule": "exclude sample when any checked raw discontinuity is true",
                "index_zero_policy": "not_computable_without_prior_panel_close",
                "purpose": "raw_data_quality_conditioning_only",
                "threshold_absolute_return": 0.2,
            },
        },
    )


def _expectation() -> contract_module.SourceSeparatedContractExpectation:
    return contract_module.SourceSeparatedContractExpectation(
        rank_count=29,
        cohort_mask_eligible_count=13_346,
        retained_feature_row_count=89,
        development_row_count=31,
        purge_row_count=29,
        validation_row_count=29,
    )

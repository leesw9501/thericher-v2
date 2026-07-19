from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

import thericher_v2.research.tiingo_norgate_cross_source_intake as intake_module
from thericher_v2.data.tiingo_norgate_cross_source_cohort import (
    TiingoNorgateCrossSourceCohort,
)


def test_verified_intake_is_metadata_only_and_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cohort = _cohort(tmp_path)
    calls: list[dict[str, Any]] = []

    def load_verified(artifact_dir: Path, **kwargs: Any) -> TiingoNorgateCrossSourceCohort:
        calls.append({"artifact_dir": artifact_dir, **kwargs})
        return cohort

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("cross-source intake must not use a network")

    original_read_text = Path.read_text

    def guard_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith(".env"):
            raise AssertionError("cross-source intake must not read credentials")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(
        intake_module,
        "load_verified_tiingo_norgate_cross_source_cohort",
        load_verified,
    )
    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(Path, "read_text", guard_read_text)

    result = intake_module.load_verified_tiingo_norgate_cross_source_intake(
        cohort.artifact_dir,
        artifact_root=tmp_path / "artifact-root",
        market_data_root=tmp_path / "market-data",
        repo_root=tmp_path / "repo",
    )

    assert calls == [
        {
            "artifact_dir": cohort.artifact_dir,
            "artifact_root": tmp_path / "artifact-root",
            "market_data_root": tmp_path / "market-data",
            "repo_root": tmp_path / "repo",
        }
    ]
    assert result.artifact_dir == cohort.artifact_dir
    assert result.manifest_hash == cohort.manifest_hash
    assert result.rank_count == 29
    assert result.overlap_session_count == 483
    assert result.forward_only_session_count == 18
    assert result.scope["cross_source_engineering_evidence_only"] is True
    assert all(
        value is False
        for key, value in result.scope.items()
        if key != "cross_source_engineering_evidence_only"
    )
    assert all(value is False for value in result.access_boundary.values())
    for attribute in ("bars", "features", "labels", "metadata", "__iter__"):
        assert not hasattr(result, attribute)
    with pytest.raises(TypeError):
        iter(result)


@pytest.mark.parametrize(
    ("section", "key", "value", "error"),
    [
        ("scope", "model_eligible", True, "cross-source scope"),
        ("scope", "training_eligible", True, "cross-source scope"),
        ("access_boundary", "broker_access", True, "cross-source access boundary"),
        ("access_boundary", "raw_bar_export", True, "cross-source access boundary"),
    ],
)
def test_rejects_forbidden_scope_or_access_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    section: str,
    key: str,
    value: bool,
    error: str,
) -> None:
    metadata = _metadata()
    metadata[section][key] = value
    cohort = _cohort(tmp_path, metadata=metadata)
    _stub_loader(monkeypatch, cohort)

    with pytest.raises(ValueError, match=error):
        intake_module.load_verified_tiingo_norgate_cross_source_intake(cohort.artifact_dir)


def test_rejects_tampered_parent_hash_or_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = _metadata()
    metadata["parents"]["norgate"]["dataset_hash"] = "sha256:" + "9" * 64
    cohort = _cohort(tmp_path, metadata=metadata)
    _stub_loader(monkeypatch, cohort)

    with pytest.raises(ValueError, match="parent hashes"):
        intake_module.load_verified_tiingo_norgate_cross_source_intake(cohort.artifact_dir)

    metadata = _metadata()
    metadata["rank_linkage"]["available_rank_count"] = 30
    cohort = _cohort(tmp_path, metadata=metadata)
    _stub_loader(monkeypatch, cohort)

    with pytest.raises(ValueError, match="counts"):
        intake_module.load_verified_tiingo_norgate_cross_source_intake(cohort.artifact_dir)


def test_intake_has_no_execution_broker_or_model_imports() -> None:
    source = Path(
        "src/thericher_v2/research/tiingo_norgate_cross_source_intake.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "thericher_v2.execution",
        "thericher_v2.research.validation",
        "localpaperbroker",
        "torch",
        "requests",
        "socket",
    ):
        assert forbidden not in source


def _stub_loader(
    monkeypatch: pytest.MonkeyPatch, cohort: TiingoNorgateCrossSourceCohort
) -> None:
    monkeypatch.setattr(
        intake_module,
        "load_verified_tiingo_norgate_cross_source_cohort",
        lambda *_args, **_kwargs: cohort,
    )


def _cohort(
    tmp_path: Path, *, metadata: dict[str, Any] | None = None
) -> TiingoNorgateCrossSourceCohort:
    return TiingoNorgateCrossSourceCohort(
        artifact_dir=tmp_path / "cohort-r1",
        manifest_hash="sha256:" + "a" * 64,
        tiingo_dataset_hash="sha256:" + "b" * 64,
        tiingo_manifest_hash="sha256:" + "c" * 64,
        norgate_dataset_hash="sha256:" + "d" * 64,
        norgate_manifest_hash="sha256:" + "e" * 64,
        rank_count=29,
        overlap_session_count=483,
        forward_only_session_count=18,
        marker_count=153,
        excluded_decision_count=302,
        metadata=_metadata() if metadata is None else metadata,
    )


def _metadata() -> dict[str, Any]:
    return {
        "kind": "tiingo_norgate_cross_source_cohort",
        "immutable": True,
        "artifact_dir_name": "cohort-r1",
        "scope": {
            "cross_source_engineering_evidence_only": True,
            "point_in_time_eligible": False,
            "model_eligible": False,
            "training_eligible": False,
            "ranking_eligible": False,
            "ensemble_eligible": False,
            "campaign_eligible": False,
            "paper_trading_eligible": False,
            "pnl_eligible": False,
            "profitability_eligible": False,
        },
        "access_boundary": {
            "network_access": False,
            "credential_access": False,
            "broker_access": False,
            "local_paper_access": False,
            "model_access": False,
            "raw_bar_export": False,
            "feature_or_label_export": False,
        },
        "parents": {
            "tiingo": {
                "dataset_hash": "sha256:" + "b" * 64,
                "manifest_hash": "sha256:" + "c" * 64,
            },
            "norgate": {
                "dataset_hash": "sha256:" + "d" * 64,
                "manifest_hash": "sha256:" + "e" * 64,
            },
        },
        "rank_linkage": {"available_rank_count": 29},
        "session_contract": {
            "norgate_overlap_session_count": 483,
            "forward_only_session_count": 18,
        },
        "conservative_marker_mask": {
            "total_marker_count": 153,
            "excluded_rank_decision_pair_count": 302,
        },
    }

from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from thericher_v2.data import d1_source_conformance as conformance


def test_writes_an_external_metadata_only_receipt_without_external_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repo"
    artifact_root = tmp_path / "artifacts"
    repository.mkdir()
    artifact_root.mkdir()
    _deny_external_access(monkeypatch)

    result = conformance.build_d1_source_conformance_receipt(
        artifact_root=artifact_root,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        norgate_loader=lambda _root, _repo: _metadata("norgate"),
        kis_loader=lambda _root, _repo: _metadata("kis_paper"),
    )
    repeated = conformance.build_d1_source_conformance_receipt(
        artifact_root=artifact_root,
        market_data_root=tmp_path / "market-data",
        repo_root=repository,
        norgate_loader=lambda _root, _repo: _metadata("norgate"),
        kis_loader=lambda _root, _repo: _metadata("kis_paper"),
    )

    assert result.conformance.status == "metadata_conforming_with_limits"
    assert result.conformance.source_parameterized_only is True
    assert result.conformance.price_transfer_eligible is False
    assert result.conformance.model_eligible is False
    assert result.receipt_path.is_relative_to(artifact_root)
    assert not result.receipt_path.is_relative_to(repository)
    assert repeated.receipt_path == result.receipt_path
    assert repeated.receipt_sha256 == result.receipt_sha256

    payload = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert payload["artifact_policy"]["network_accessed"] is False
    assert payload["artifact_policy"]["credentials_accessed"] is False
    assert payload["conformance"]["interface_scope"]["paper_trading_eligible"] is False
    _assert_no_raw_keys(payload)
    assert str(tmp_path) not in result.receipt_path.read_text(encoding="utf-8")


def test_preserves_an_unqualified_semantic_conflict_without_value_comparison() -> None:
    norgate = _metadata("norgate")
    kis = replace(
        _metadata("kis_paper"),
        adjustment_semantics="declared_unadjusted",
        symbol_identity_semantics="current_listing_registry_non_pit",
    )

    result = conformance.assess_d1_metadata_conformance(norgate=norgate, kis_paper=kis)

    assert result.status == "semantics_conflict"
    assert result.semantics["adjustment"] == "semantics_conflict"
    assert result.semantics["symbol_identity"] == "semantics_conflict"
    assert result.shared_field_names == conformance.D1_OHLCV_FIELDS
    assert result.norgate_only_field_names == ()
    assert result.kis_paper_only_field_names == ()


def test_rejects_git_local_artifacts_before_reading_sources(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        conformance.build_d1_source_conformance_receipt(
            artifact_root=repository,
            market_data_root=tmp_path / "market-data",
            repo_root=repository,
            norgate_loader=lambda _root, _repo: _metadata("norgate"),
            kis_loader=lambda _root, _repo: _metadata("kis_paper"),
        )


def _metadata(source_name: str) -> conformance.D1SourceMetadata:
    return conformance.D1SourceMetadata(
        source_name=source_name,  # type: ignore[arg-type]
        dataset_id=f"test.{source_name}.d1",
        dataset_sha256="sha256:" + ("a" if source_name == "norgate" else "b") * 64,
        lineage_sha256="sha256:" + ("c" if source_name == "norgate" else "d") * 64,
        field_names=conformance.D1_OHLCV_FIELDS,
        timeframe="1d",
        completed_bar_semantics="completed_bar_attested",
        adjustment_semantics="unqualified",
        corporate_action_semantics="unqualified",
        symbol_identity_semantics="source_parameterized",
        session_timezone_semantics="unknown",
        gap_halt_semantics="unknown",
        stream_count=2,
        common_session_count=5,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("D1 source conformance must stay offline and credential-free")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)


def _assert_no_raw_keys(value: object) -> None:
    forbidden = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price",
        "prices",
        "return",
        "returns",
        "timestamp",
        "timestamps",
        "sourcepath",
        "workdir",
        "statesqlite",
        "eventjsonl",
        "eventlog",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_keys(nested)

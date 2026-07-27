from __future__ import annotations

import hashlib
import inspect
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path

import pytest

from thericher_v2.contracts import Timeframe
from thericher_v2.data import source_scoped_liquid_universe as universe_module
from thericher_v2.data.source_scoped_liquid_universe import (
    SOURCE_SCOPED_LIQUID_UNIVERSE_ID,
    SourceScopedLiquidUniverse,
    _ApprovedSourceIdentity,
    _load_source_scoped_liquid_universe_manifest,
    _materialize_source_scoped_liquid_universe_manifest,
    _SourceScopedLiquidUniverseSourcePaths,
    load_source_scoped_liquid_universe_manifest,
    materialize_source_scoped_liquid_universe_manifest,
)
from thericher_v2.research import unranked_opportunity_selection as opportunity_module
from thericher_v2.research.unranked_opportunity_selection import (
    UnrankedOpportunitySelectionInput,
    build_unranked_opportunity_selection_input,
    require_attested_unranked_opportunity_selection_input,
)

_ETF_TARGETS = (
    ("QQQ", "NAS", "QQQ/NAS/MODP=0", "complete"),
    ("SPY", "AMS", "SPY/AMS/MODP=0", "complete"),
    ("IWM", "AMS", "IWM/AMS/MODP=0", "source_limited"),
)
_NAS_TARGETS = ("AAPL/NAS", "AMZN/NAS", "GOOGL/NAS", "META/NAS", "MSFT/NAS", "NVDA/NAS")
_DEFAULT_APPROVAL = object()


@dataclass(frozen=True)
class _Fixture:
    repository_root: Path
    source_paths: _SourceScopedLiquidUniverseSourcePaths
    private_index_path: Path
    panel_manifest_path: Path
    panel_evidence_path: Path
    approved_source_identity: _ApprovedSourceIdentity


def test_materializes_and_reattests_a_deterministic_unranked_universe(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)

    first = _materialize(fixture, tmp_path / "external-output")
    second = _materialize(fixture, tmp_path / "external-output")
    universe = _load(fixture, first.manifest_path)

    assert first == second
    assert first.manifest_path.is_file()
    assert first.manifest_sha256 == _sha256(first.manifest_path.read_bytes())
    assert universe.manifest_id == SOURCE_SCOPED_LIQUID_UNIVERSE_ID
    assert [instrument.instrument_id for instrument in universe.instruments] == [
        "QQQ/NAS",
        "SPY/AMS",
        "IWM/AMS",
        *_NAS_TARGETS,
    ]
    assert all(
        instrument.supported_timeframes == (Timeframe.D1,) for instrument in universe.instruments
    )
    assert universe.instruments[2].availability_scope.endswith("source_limited")
    assert universe.historical_membership_eligible is False
    assert universe.ranking_eligible is False
    assert universe.paper_trading_eligible is False
    assert universe.model_selection_eligible is False
    assert universe.liquidity_qualified is False
    assert universe.cross_partition_alignment_eligible is False
    manifest_text = first.manifest_path.read_text(encoding="ascii")
    assert "100.123" not in manifest_text
    assert '"raw_rows_persisted":false' in manifest_text


def test_loader_rejects_changed_source_provenance_and_historical_scope(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    materialization = _materialize(fixture, tmp_path / "external-output")
    index = _read_json(fixture.private_index_path)
    index["targets"][0]["state"] = "source_limited"
    _write_json(fixture.private_index_path, index)

    with pytest.raises(ValueError, match="unapproved"):
        _load(fixture, materialization.manifest_path)
    with pytest.raises(ValueError, match="historical membership"):
        _load_source_scoped_liquid_universe_manifest(
            manifest_path=materialization.manifest_path,
            source_paths=fixture.source_paths,
            repository_root=fixture.repository_root,
            requested_membership_scope="historical_point_in_time",
            approved_source_identity=fixture.approved_source_identity,
            require_approved_manifest_root=False,
        )


def test_rejects_duplicate_identity_and_missing_d1_source_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    panel = _read_json(fixture.panel_manifest_path)
    panel["scope"]["target_keys"] = ["QQQ/NAS"]
    _write_json(fixture.panel_manifest_path, panel)
    evidence = _read_json(fixture.panel_evidence_path)
    evidence["panel_manifest"]["sha256"] = _sha256(fixture.panel_manifest_path.read_bytes())
    evidence["source"]["target_keys"] = ["QQQ/NAS"]
    _write_json(fixture.panel_evidence_path, evidence)
    with monkeypatch.context() as scoped_monkeypatch:
        scoped_monkeypatch.setattr(universe_module, "_NAS_TARGETS", (("QQQ", "NAS"),))
        with pytest.raises(ValueError, match="duplicate identity"):
            _materialize(
                fixture,
                tmp_path / "external-output",
                approved_source_identity=None,
            )

    fixture = _fixture(tmp_path / "missing-d1")
    panel = _read_json(fixture.panel_manifest_path)
    panel["scope"]["timeframe"] = "1m"
    _write_json(fixture.panel_manifest_path, panel)
    evidence = _read_json(fixture.panel_evidence_path)
    evidence["panel_manifest"]["sha256"] = _sha256(fixture.panel_manifest_path.read_bytes())
    _write_json(fixture.panel_evidence_path, evidence)

    with pytest.raises(ValueError, match="scope is incompatible"):
        _materialize(
            fixture,
            tmp_path / "external-output-2",
            approved_source_identity=None,
        )


def test_rejects_manifest_scope_tampering_and_git_output(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    materialization = _materialize(fixture, tmp_path / "external-output")
    manifest = _read_json(materialization.manifest_path)
    manifest["scope"]["ranking_eligible"] = True
    _write_json(materialization.manifest_path, manifest)

    with pytest.raises(ValueError, match="source provenance"):
        _load(fixture, materialization.manifest_path)
    with pytest.raises(ValueError, match="outside Git"):
        _materialize(fixture, fixture.repository_root / "forbidden-output")
    assert not (fixture.repository_root / "forbidden-output").exists()


def test_data_builder_is_offline_metadata_only_and_never_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("liquid-universe contract must not use this capability")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    materialization = _materialize(fixture, tmp_path / "external-output")
    loaded = _load(fixture, materialization.manifest_path)

    assert loaded.instruments
    source = inspect.getsource(universe_module).lower()
    for forbidden_name in ("urllib", "requests", "socket", "getenv", ".env", "orderintent"):
        assert forbidden_name not in source
    assert "source_paths" not in inspect.signature(
        materialize_source_scoped_liquid_universe_manifest
    ).parameters
    assert "source_paths" not in inspect.signature(
        load_source_scoped_liquid_universe_manifest
    ).parameters


def test_public_api_requires_approved_sources_and_market_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    unapproved = _ApprovedSourceIdentity(
        private_daily_index_sha256="sha256:" + "0" * 64,
        nas_panel_evidence_sha256=fixture.approved_source_identity.nas_panel_evidence_sha256,
        nas_panel_manifest_sha256=fixture.approved_source_identity.nas_panel_manifest_sha256,
    )
    with pytest.raises(ValueError, match="unapproved"):
        _materialize(
            fixture,
            tmp_path / "external-output",
            approved_source_identity=unapproved,
        )

    approved_market_root = tmp_path / "approved-market-data"
    approved_output_root = approved_market_root / "source-scoped-liquid-universe" / "v1"
    monkeypatch.setattr(
        universe_module,
        "DEFAULT_SOURCE_SCOPED_LIQUID_UNIVERSE_PRIVATE_DAILY_INDEX_PATH",
        fixture.private_index_path,
    )
    monkeypatch.setattr(
        universe_module,
        "DEFAULT_SOURCE_SCOPED_LIQUID_UNIVERSE_NAS_PANEL_EVIDENCE_PATH",
        fixture.panel_evidence_path,
    )
    monkeypatch.setattr(
        universe_module,
        "SOURCE_SCOPED_LIQUID_UNIVERSE_OUTPUT_ROOT",
        approved_output_root,
    )
    monkeypatch.setattr(
        universe_module,
        "SOURCE_SCOPED_LIQUID_UNIVERSE_APPROVED_MARKET_DATA_ROOT",
        approved_market_root,
    )
    monkeypatch.setattr(
        universe_module,
        "_APPROVED_SOURCE_IDENTITY",
        fixture.approved_source_identity,
    )

    with pytest.raises(ValueError, match="approved external root"):
        materialize_source_scoped_liquid_universe_manifest(
            output_root=tmp_path / "not-approved",
            repository_root=fixture.repository_root,
        )
    materialization = materialize_source_scoped_liquid_universe_manifest(
        output_root=approved_output_root,
        repository_root=fixture.repository_root,
    )
    loaded = load_source_scoped_liquid_universe_manifest(
        materialization.manifest_path,
        repository_root=fixture.repository_root,
    )

    assert loaded.manifest_sha256 == materialization.manifest_sha256


def test_unranked_research_consumer_preserves_metadata_without_selection(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    materialization = _materialize(fixture, tmp_path / "external-output")
    universe = _load(fixture, materialization.manifest_path)
    input = build_unranked_opportunity_selection_input(universe)

    assert input.manifest_sha256 == universe.manifest_sha256
    assert [instrument.instrument_id for instrument in input.instruments] == [
        instrument.instrument_id for instrument in universe.instruments
    ]
    assert {instrument.source_id for instrument in input.instruments} == {
        "kis-paper-private-daily-etf-catalog-v1",
        "kis-paper-current-nas-daily-panel-v1",
    }
    assert input.offline_only is True
    assert input.historical_membership_eligible is False
    assert input.ranking_eligible is False
    assert input.paper_trading_eligible is False
    assert input.model_selection_eligible is False
    assert input.liquidity_qualified is False
    assert input.cross_partition_alignment_eligible is False
    assert not hasattr(input.instruments[0], "price")
    assert not hasattr(input.instruments[0], "score")
    with pytest.raises(ValueError, match="ranking or Paper"):
        build_unranked_opportunity_selection_input(universe, requested_use="rank_symbols")
    with pytest.raises(ValueError, match="ranking or Paper"):
        build_unranked_opportunity_selection_input(universe, requested_use="paper_trading")
    forged_universe = object.__new__(SourceScopedLiquidUniverse)
    with pytest.raises(ValueError, match="loader attestation"):
        build_unranked_opportunity_selection_input(forged_universe)
    forged_input = object.__new__(UnrankedOpportunitySelectionInput)
    with pytest.raises(ValueError, match="builder attestation"):
        require_attested_unranked_opportunity_selection_input(forged_input)
    assert tuple(inspect.signature(build_unranked_opportunity_selection_input).parameters) == (
        "universe",
        "requested_use",
    )
    source = inspect.getsource(opportunity_module).lower()
    for forbidden_name in (
        "urllib",
        "requests",
        "socket",
        "getenv",
        ".env",
        "orderintent",
        "torch",
        "cuda",
    ):
        assert forbidden_name not in source


def _fixture(root: Path) -> _Fixture:
    repository_root = root / "repo"
    repository_root.mkdir(parents=True)
    source_root = root / "sources"
    private_index_path = source_root / "private-daily" / "index.json"
    _write_json(
        private_index_path,
        {
            "kind": "kis_paper_private_daily_backfill_index",
            "backfill_version": "kis-paper-private-daily-backfill-v1",
            "redaction": {
                "account_facts_persisted": False,
                "credentials_persisted": False,
            },
            "storage": {
                "private_local_only": True,
                "redistributed": False,
                "served": False,
            },
            "targets": [
                {
                    "target_key": target_key,
                    "symbol": symbol,
                    "exchange": venue,
                    "venue_status": "verified_by_kis_response",
                    "state": state,
                }
                for symbol, venue, target_key, state in _ETF_TARGETS
            ],
        },
    )
    panel_manifest_path = source_root / "nas-panel" / "manifest.json"
    _write_json(
        panel_manifest_path,
        {
            "kind": "kis_paper_daily_universe_panel",
            "dataset_id": "fixture.kis.paper.current.nas.panel",
            "dataset_hash": "sha256:" + "a" * 64,
            "scope": {
                "market": "US",
                "timeframe": "1d",
                "historical_point_in_time_eligible": False,
                "paper_trading_eligible": False,
                "ranking_eligible": False,
                "target_keys": list(_NAS_TARGETS),
            },
            "limitations": [
                "current_listing_registry_is_not_a_historical_point_in_time_universe",
                "corporate_action_semantics_not_qualified",
                "offline_local_paper_validation_only",
            ],
        },
    )
    panel_evidence_path = source_root / "nas-panel-evidence" / "evidence.json"
    _write_json(
        panel_evidence_path,
        {
            "kind": "kis_paper_daily_universe_panel_evidence",
            "panel_manifest": {
                "path": str(panel_manifest_path),
                "sha256": _sha256(panel_manifest_path.read_bytes()),
            },
            "redaction": {
                "credentials_persisted": False,
                "raw_rows_persisted": False,
            },
            "scope": {
                "offline_local_paper_validation_only": True,
                "paper_trading_eligible": False,
                "ranking_eligible": False,
            },
            "source": {"target_keys": list(_NAS_TARGETS)},
        },
    )
    return _Fixture(
        repository_root=repository_root,
        source_paths=_SourceScopedLiquidUniverseSourcePaths(
            private_daily_index_path=private_index_path,
            nas_panel_evidence_path=panel_evidence_path,
        ),
        private_index_path=private_index_path,
        panel_manifest_path=panel_manifest_path,
        panel_evidence_path=panel_evidence_path,
        approved_source_identity=_ApprovedSourceIdentity(
            private_daily_index_sha256=_sha256(private_index_path.read_bytes()),
            nas_panel_evidence_sha256=_sha256(panel_evidence_path.read_bytes()),
            nas_panel_manifest_sha256=_sha256(panel_manifest_path.read_bytes()),
        ),
    )


def _materialize(
    fixture: _Fixture,
    output_root: Path,
    *,
    approved_source_identity: object = _DEFAULT_APPROVAL,
):
    approved = (
        fixture.approved_source_identity
        if approved_source_identity is _DEFAULT_APPROVAL
        else approved_source_identity
    )
    return _materialize_source_scoped_liquid_universe_manifest(
        source_paths=fixture.source_paths,
        output_root=output_root,
        repository_root=fixture.repository_root,
        approved_source_identity=approved,
        require_approved_output_root=False,
    )


def _load(fixture: _Fixture, manifest_path: Path):
    return _load_source_scoped_liquid_universe_manifest(
        manifest_path=manifest_path,
        source_paths=fixture.source_paths,
        repository_root=fixture.repository_root,
        requested_membership_scope="current_source_scoped_only",
        approved_source_identity=fixture.approved_source_identity,
        require_approved_manifest_root=False,
    )


def _read_json(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()

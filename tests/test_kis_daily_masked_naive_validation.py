from __future__ import annotations

import json
import os
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

import thericher_v2.research.kis_daily_masked_naive_validation as masked_validation
from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_daily_event_boundary_audit import (
    KisDailyEventBoundaryAudit,
    KisDailyEventBoundaryAuditLineage,
    KisDailyEventBoundaryMaskedPair,
    KisDailyEventBoundaryPartition,
)
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.kis_daily_masked_naive_validation import (
    KIS_DAILY_MASKED_NAIVE_VALIDATION_ID,
    run_kis_daily_masked_naive_validation,
    run_pinned_kis_daily_masked_naive_validation,
)

_SOURCE_HASH = "sha256:" + "a" * 64
_INDEX_HASH = "sha256:" + "b" * 64
_SIDECAR_HASH = "sha256:" + "c" * 64
_SIDECAR_MANIFEST_HASH = "sha256:" + "d" * 64
_SESSION_HASH = "sha256:" + "e" * 64
_AUDIT_HASH = "sha256:" + "f" * 64
_MASK_HASH = "sha256:" + "1" * 64
_PARTITION_HASH = "sha256:" + "2" * 64


def test_runs_fixed_controls_offline_with_replayable_local_paper_fills(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, audit = _catalog_and_audit(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("masked naive validation must stay offline and credential-free")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

    result = run_kis_daily_masked_naive_validation(
        catalog,
        audit=audit,
        source_dataset_hash=_SOURCE_HASH,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    assert result.artifact_path.parent == artifact_root.resolve()
    assert len(result.control_results) == 12
    assert all(item.all_fills_local_paper for item in result.control_results)
    assert all(item.replay_invariant_passed for item in result.control_results)
    assert all(
        item.fill_count == item.entry_count * 2 for item in result.control_results
    )
    assert {
        item.control for item in result.control_results
    } == {"flat", "always_long", "previous_session_direction"}
    assert all(
        item.entry_count == 0 and item.fill_count == 0
        for item in result.control_results
        if item.control == "flat"
    )
    _assert_no_raw_market_fields(json.loads(result.artifact_path.read_text(encoding="utf-8")))
    persisted = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert persisted["execution"]["source"] == "local_paper"
    assert persisted["eligibility"]["control_eligibility_identical"] is True
    assert persisted["eligibility"]["untouched_tail_materialized"] is False
    assert persisted["scope"]["claude_verdict"] == "supported-with-limits"
    assert not list(artifact_root.glob(f".{KIS_DAILY_MASKED_NAIVE_VALIDATION_ID}-*"))


def test_rejects_catalog_drift_or_tail_before_writing_an_artifact(tmp_path: Path) -> None:
    catalog, audit = _catalog_and_audit(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    with pytest.raises(ValueError, match="index hash"):
        run_kis_daily_masked_naive_validation(
            replace(catalog, index_hash="sha256:" + "9" * 64),
            audit=audit,
            source_dataset_hash=_SOURCE_HASH,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
    assert not artifact_root.exists()

    tail_catalog = _catalog_from_sessions(
        tmp_path,
        sessions=tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(20)),
    )
    with pytest.raises(ValueError, match="prefix session count|untouched tail"):
        run_kis_daily_masked_naive_validation(
            tail_catalog,
            audit=audit,
            source_dataset_hash=_SOURCE_HASH,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
    assert not artifact_root.exists()


def test_pinned_runner_rechecks_audit_before_loading_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, audit = _catalog_and_audit(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    calls: list[str] = []

    def fake_audit_loader(*_args: object, **kwargs: object) -> KisDailyEventBoundaryAudit:
        calls.append("audit")
        assert kwargs["expected_catalog_dataset_hash"] == _SOURCE_HASH
        assert kwargs["expected_catalog_index_hash"] == _INDEX_HASH
        return audit

    def fake_catalog_loader(*_args: object, **kwargs: object) -> KisPaperPrivateDailyCatalog:
        calls.append("catalog")
        assert calls == ["audit", "catalog"]
        assert kwargs["expected_index_hash"] == _INDEX_HASH
        assert kwargs["expected_full_dataset_hash"] == _SOURCE_HASH
        assert kwargs["end_session"] == audit.partition("embargo").end_session
        return catalog

    monkeypatch.setattr(masked_validation, "load_kis_daily_event_boundary_audit", fake_audit_loader)
    monkeypatch.setattr(
        masked_validation,
        "load_kis_paper_private_daily_catalog",
        fake_catalog_loader,
    )
    monkeypatch.setattr(masked_validation, "_EXPECTED_CATALOG_DATASET_HASH", _SOURCE_HASH)
    monkeypatch.setattr(masked_validation, "_EXPECTED_CATALOG_INDEX_HASH", _INDEX_HASH)

    result = run_pinned_kis_daily_masked_naive_validation(
        audit_path=tmp_path / "audit.json",
        cache_root=tmp_path / "cache",
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    assert calls == ["audit", "catalog"]
    assert result.artifact_path.is_file()


def test_rejects_artifact_root_inside_git(tmp_path: Path) -> None:
    catalog, audit = _catalog_and_audit(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(ValueError, match="outside Git"):
        run_kis_daily_masked_naive_validation(
            catalog,
            audit=audit,
            source_dataset_hash=_SOURCE_HASH,
            artifact_root=repo_root / "artifacts",
            repo_root=repo_root,
        )


def test_removes_only_abandoned_tool_owned_temporary_replay_logs(tmp_path: Path) -> None:
    catalog, audit = _catalog_and_audit(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    artifact_root = tmp_path / "artifacts"
    stale = artifact_root / f".{KIS_DAILY_MASKED_NAIVE_VALIDATION_ID}-interrupted"
    stale.mkdir(parents=True)
    (stale / "events.jsonl").write_text("raw-temporary-event\n", encoding="utf-8")
    unrelated = artifact_root / "unrelated-evidence"
    unrelated.mkdir()

    run_kis_daily_masked_naive_validation(
        catalog,
        audit=audit,
        source_dataset_hash=_SOURCE_HASH,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    assert not stale.exists()
    assert unrelated.is_dir()


def _catalog_and_audit(
    tmp_path: Path,
) -> tuple[KisPaperPrivateDailyCatalog, KisDailyEventBoundaryAudit]:
    sessions = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(20))
    catalog = _catalog_from_sessions(tmp_path, sessions=sessions[:18])
    partitions = (
        KisDailyEventBoundaryPartition("development", sessions[0], sessions[11], 12),
        KisDailyEventBoundaryPartition("purge", sessions[12], sessions[12], 1),
        KisDailyEventBoundaryPartition("validation", sessions[13], sessions[16], 4),
        KisDailyEventBoundaryPartition("embargo", sessions[17], sessions[17], 1),
        KisDailyEventBoundaryPartition("untouched_tail", sessions[18], sessions[19], 2),
    )
    masked = MappingProxyType(
        {
            "QQQ": (
                KisDailyEventBoundaryMaskedPair(
                    "QQQ", sessions[4], sessions[5], ("event_buffer",)
                ),
                KisDailyEventBoundaryMaskedPair(
                    "QQQ", sessions[11], sessions[12], ("chronological_boundary",)
                ),
            ),
            "SPY": (
                KisDailyEventBoundaryMaskedPair(
                    "SPY", sessions[6], sessions[7], ("event_buffer",)
                ),
                KisDailyEventBoundaryMaskedPair(
                    "SPY", sessions[11], sessions[12], ("chronological_boundary",)
                ),
            ),
        }
    )
    audit = KisDailyEventBoundaryAudit(
        path=tmp_path / "audit.json",
        artifact_sha256=_AUDIT_HASH,
        lineage=KisDailyEventBoundaryAuditLineage(
            catalog_dataset_hash=_SOURCE_HASH,
            catalog_index_hash=_INDEX_HASH,
            sidecar_dataset_hash=_SIDECAR_HASH,
            sidecar_manifest_hash=_SIDECAR_MANIFEST_HASH,
            session_dates_sha256=_SESSION_HASH,
        ),
        mask_identity=_MASK_HASH,
        partition_identity=_PARTITION_HASH,
        partitions=partitions,
        masked_pairs_by_symbol=masked,
    )
    return catalog, audit


def _catalog_from_sessions(
    tmp_path: Path,
    *,
    sessions: tuple[date, ...],
) -> KisPaperPrivateDailyCatalog:
    streams = {}
    for symbol, base in (("QQQ", Decimal("100")), ("SPY", Decimal("200"))):
        bars = tuple(
            _bar(symbol=symbol, session=session, index=index, base=base)
            for index, session in enumerate(sessions)
        )
        streams[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id="test-kis-daily",
            dataset_hash=_SOURCE_HASH,
            source_path=tmp_path / f"{symbol}.csv.gz",
            bars=bars,
        )
    return KisPaperPrivateDailyCatalog(
        dataset_id="test-kis-daily",
        dataset_hash="sha256:" + "3" * 64,
        index_hash=_INDEX_HASH,
        index_path=tmp_path / "index.json",
        source_root=tmp_path / "source",
        adjustment_mode="MODP=0_unadjusted",
        bars_by_symbol=MappingProxyType(streams),
        common_sessions=sessions,
        raw_price_limitations=("MODP=0_unadjusted",),
    )


def _bar(*, symbol: str, session: date, index: int, base: Decimal) -> Bar:
    open_value = base + Decimal(index)
    close_offset = Decimal("1") if symbol == "QQQ" or index % 2 == 0 else Decimal("-1")
    close_value = open_value + close_offset
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
        open=open_value,
        high=max(open_value, close_value) + Decimal("1"),
        low=min(open_value, close_value) - Decimal("1"),
        close=close_value,
        volume=Decimal("1000"),
        complete=True,
    )


def _assert_no_raw_market_fields(value: object) -> None:
    forbidden = {"open", "high", "low", "close", "volume", "price", "return"}
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            assert normalized not in forbidden
            _assert_no_raw_market_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_market_fields(nested)

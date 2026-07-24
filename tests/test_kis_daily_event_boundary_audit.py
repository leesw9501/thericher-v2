from __future__ import annotations

import os
import socket
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_daily_corporate_actions import (
    KisDailyCorporateActionEvent,
    KisDailyCorporateActionSnapshot,
)
from thericher_v2.data.kis_paper_daily import KisPaperPrivateDailyCatalog
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research.kis_daily_event_mask_contract import (
    build_kis_daily_event_boundary_audit,
    write_kis_daily_event_boundary_audit,
)

_HASH = "sha256:" + "a" * 64
_INDEX_HASH = "sha256:" + "b" * 64
_SIDECAR_HASH = "sha256:" + "c" * 64
_SIDECAR_MANIFEST_HASH = "sha256:" + "d" * 64


def test_audit_uses_a_buffered_mask_and_frozen_partition_identity(tmp_path: Path) -> None:
    catalog, sessions = _catalog(tmp_path)
    audit = build_kis_daily_event_boundary_audit(
        catalog=catalog,
        sidecar=_sidecar(sessions),
        created_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
    )

    assert audit.status == "qualified"
    assert audit.unqualified_reasons == ()
    assert tuple(partition.name for partition in audit.partitions) == (
        "development",
        "purge",
        "validation",
        "embargo",
        "untouched_tail",
    )
    qqq_pairs = audit.masked_pairs["QQQ"]
    assert [
        (pair.start_session, pair.end_session, pair.reasons)
        for pair in qqq_pairs
        if pair.reasons == ("event_buffer",)
    ] == [
        (sessions[6], sessions[7], ("event_buffer",)),
        (sessions[7], sessions[8], ("event_buffer",)),
        (sessions[8], sessions[9], ("event_buffer",)),
        (sessions[9], sessions[10], ("event_buffer",)),
    ]
    assert audit.audit_counts["QQQ"] == {
        "event_count": 1,
        "mapped_event_count": 1,
        "interior_event_count": 1,
        "buffered_session_count": 3,
        "event_boundary_pair_count": 2,
        "masked_pair_count": 8,
        "unmasked_residual_pairs_examined": 11,
        "unmasked_residual_exceedance_count": 0,
    }
    document = audit.document()
    assert document["scope"] == {
        "retrospective_price_return_label_integrity_only": True,
        "point_in_time_feature_eligible": False,
        "model_training_eligible": False,
        "paper_decision_eligible": False,
        "total_return_eligible": False,
        "baseline_eligible": False,
        "raw_price_data_consumed_in_memory_only": True,
        "raw_prices_or_returns_persisted": False,
    }
    assert document["mask_identity"] == audit.mask_identity()
    assert document["partition_identity"] == audit.partition_identity()


def test_audit_rejects_an_unmasked_large_residual_without_persisting_it(tmp_path: Path) -> None:
    catalog, sessions = _catalog(tmp_path, qqq_jump_at=4)
    audit = build_kis_daily_event_boundary_audit(
        catalog=catalog,
        sidecar=_sidecar(sessions),
        created_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
    )

    assert audit.status == "unqualified"
    assert audit.unqualified_reasons == ("unmasked_residual_exceeds_threshold:QQQ",)
    assert audit.audit_counts["QQQ"]["unmasked_residual_exceedance_count"] == 1
    document = str(audit.document())
    assert "150" not in document
    assert "close" not in document


def test_audit_records_missing_event_neighbors_as_a_scoped_rejection(tmp_path: Path) -> None:
    catalog, sessions = _catalog(tmp_path)
    audit = build_kis_daily_event_boundary_audit(
        catalog=catalog,
        sidecar=_sidecar(sessions, qqq_event_index=0),
        created_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
    )

    assert audit.status == "unqualified"
    assert audit.unqualified_reasons == ("event_neighbor_missing:QQQ",)
    assert audit.audit_counts["QQQ"]["buffered_session_count"] == 0


def test_audit_artifact_stays_external_and_needs_no_network_or_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, sessions = _catalog(tmp_path)
    audit = build_kis_daily_event_boundary_audit(
        catalog=catalog,
        sidecar=_sidecar(sessions),
        created_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
    )
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("event-boundary audit must not use network")

    def no_credentials(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("event-boundary audit must not read credentials")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(os, "getenv", no_credentials)
    artifact = write_kis_daily_event_boundary_audit(
        destination=artifact_root / "audit.json",
        audit=audit,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    content = artifact.path.read_text(encoding="utf-8")
    assert artifact.content_hash.startswith("sha256:")
    assert '"close"' not in content
    assert "150" not in content
    assert '"paper_decision_eligible": false' in content
    with pytest.raises(ValueError, match="outside Git"):
        write_kis_daily_event_boundary_audit(
            destination=repo_root / "audit.json",
            audit=audit,
            artifact_root=repo_root,
            repo_root=repo_root,
        )


def test_audit_rejects_a_sidecar_from_a_different_catalog(tmp_path: Path) -> None:
    catalog, sessions = _catalog(tmp_path)
    foreign_catalog, _ = _catalog(tmp_path / "foreign")
    foreign_catalog = KisPaperPrivateDailyCatalog(
        dataset_id=foreign_catalog.dataset_id,
        dataset_hash="sha256:" + "e" * 64,
        index_hash=foreign_catalog.index_hash,
        index_path=foreign_catalog.index_path,
        source_root=foreign_catalog.source_root,
        adjustment_mode=foreign_catalog.adjustment_mode,
        bars_by_symbol=foreign_catalog.bars_by_symbol,
        common_sessions=foreign_catalog.common_sessions,
        raw_price_limitations=foreign_catalog.raw_price_limitations,
    )

    with pytest.raises(ValueError, match="lineage is incompatible"):
        build_kis_daily_event_boundary_audit(
            catalog=foreign_catalog,
            sidecar=_sidecar(sessions),
            created_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
        )


def _catalog(
    tmp_path: Path,
    *,
    qqq_jump_at: int | None = None,
) -> tuple[KisPaperPrivateDailyCatalog, tuple[date, ...]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_path = tmp_path / "catalog-index.json"
    source_path.write_text("{}\n", encoding="utf-8")
    sessions = tuple(date(2024, 1, 1) + timedelta(days=index) for index in range(20))
    bars_by_symbol = {}
    for symbol in ("QQQ", "SPY"):
        closes = [Decimal("100") for _session in sessions]
        if symbol == "QQQ" and qqq_jump_at is not None:
            closes[qqq_jump_at:] = [Decimal("150")] * (len(closes) - qqq_jump_at)
        bars = tuple(
            Bar(
                symbol=symbol,
                market="US",
                timeframe=Timeframe.D1,
                start_ts=datetime(session.year, session.month, session.day, tzinfo=UTC),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=Decimal("1000"),
                complete=True,
            )
            for session, close in zip(sessions, closes, strict=True)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id="unit-kis-daily-boundary",
            dataset_hash=_HASH,
            source_path=source_path,
            bars=bars,
        )
    return (
        KisPaperPrivateDailyCatalog(
            dataset_id="unit-kis-daily-boundary",
            dataset_hash=_HASH,
            index_hash=_INDEX_HASH,
            index_path=source_path,
            source_root=tmp_path,
            adjustment_mode="MODP=0_unadjusted",
            bars_by_symbol=MappingProxyType(bars_by_symbol),
            common_sessions=sessions,
            raw_price_limitations=("MODP=0_unadjusted",),
        ),
        sessions,
    )


def _sidecar(
    sessions: tuple[date, ...],
    *,
    qqq_event_index: int = 8,
) -> KisDailyCorporateActionSnapshot:
    return KisDailyCorporateActionSnapshot(
        snapshot_dir=Path("D:/market_data/snapshot=unit"),
        dataset_id="unit-sidecar",
        dataset_hash=_SIDECAR_HASH,
        manifest_hash=_SIDECAR_MANIFEST_HASH,
        catalog_dataset_hash=_HASH,
        catalog_index_hash=_INDEX_HASH,
        retrieved_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
        events=(
            KisDailyCorporateActionEvent(
                symbol="QQQ",
                source_date=sessions[qqq_event_index],
                mapped_kis_session_date=sessions[qqq_event_index],
                event_kind="cash_distribution",
                value=Decimal("1"),
            ),
            KisDailyCorporateActionEvent(
                symbol="SPY",
                source_date=sessions[10],
                mapped_kis_session_date=sessions[10],
                event_kind="cash_distribution",
                value=Decimal("1"),
            ),
        ),
        event_counts={
            "QQQ": {"cash_distribution": 1, "split": 0},
            "SPY": {"cash_distribution": 1, "split": 0},
        },
    )

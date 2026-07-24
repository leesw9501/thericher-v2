from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from test_kis_daily_corporate_actions import _HASH, _INDEX_HASH, _catalog
from thericher_v2.data.kis_daily_corporate_actions import (
    KisDailyCorporateActionEvent,
    KisDailyCorporateActionSnapshot,
)
from thericher_v2.research.kis_daily_event_mask_contract import (
    build_kis_daily_event_mask_contract,
    write_kis_daily_event_mask_contract,
)


def test_event_mask_excludes_both_pairs_touching_an_event_without_using_prices(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)
    sidecar = _sidecar(catalog)

    contract = build_kis_daily_event_mask_contract(catalog=catalog, sidecar=sidecar)

    assert [
        (pair.start_session, pair.end_session, pair.event_dates)
        for pair in contract.excluded_pairs["QQQ"]
    ] == [
        (date(2024, 3, 14), date(2024, 3, 15), (date(2024, 3, 15),)),
        (date(2024, 3, 15), date(2024, 3, 18), (date(2024, 3, 15),)),
    ]
    assert [
        (pair.start_session, pair.end_session, pair.event_dates)
        for pair in contract.excluded_pairs["SPY"]
    ] == [
        (date(2024, 3, 15), date(2024, 3, 18), (date(2024, 3, 18),)),
        (date(2024, 3, 18), date(2024, 3, 19), (date(2024, 3, 18),)),
    ]
    assert contract.document()["scope"] == {
        "retrospective_price_return_label_integrity_only": True,
        "point_in_time_feature_eligible": False,
        "model_training_eligible": False,
        "paper_decision_eligible": False,
        "price_data_consumed": False,
    }


def test_event_mask_receipt_stays_outside_git_and_has_no_price_fields(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    contract = build_kis_daily_event_mask_contract(catalog=catalog, sidecar=_sidecar(catalog))
    artifact_root = tmp_path / "artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    destination = artifact_root / "contracts" / "mask.json"

    artifact = write_kis_daily_event_mask_contract(
        destination=destination,
        contract=contract,
        artifact_root=artifact_root,
        repo_root=repo_root,
    )

    content = destination.read_text(encoding="utf-8")
    assert artifact.path == destination.resolve()
    assert artifact.content_hash.startswith("sha256:")
    assert "close" not in content
    assert "volume" not in content
    assert 'paper_decision_eligible": false' in content
    with pytest.raises(FileExistsError, match="already exists"):
        write_kis_daily_event_mask_contract(
            destination=destination,
            contract=contract,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
    with pytest.raises(ValueError, match="outside Git"):
        write_kis_daily_event_mask_contract(
            destination=repo_root / "mask.json",
            contract=contract,
            artifact_root=repo_root,
            repo_root=repo_root,
        )


def test_event_mask_rejects_sidecar_from_another_catalog(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    sidecar = _sidecar(catalog)
    foreign_root = tmp_path / "foreign"
    foreign_root.mkdir()
    foreign_catalog = replace(_catalog(foreign_root), dataset_hash="sha256:" + "e" * 64)

    with pytest.raises(ValueError, match="lineage is incompatible"):
        build_kis_daily_event_mask_contract(catalog=foreign_catalog, sidecar=sidecar)


def _sidecar(catalog: object) -> KisDailyCorporateActionSnapshot:
    return KisDailyCorporateActionSnapshot(
        snapshot_dir=Path("D:/market_data/snapshot=unit"),
        dataset_id="unit-sidecar",
        dataset_hash="sha256:" + "c" * 64,
        manifest_hash="sha256:" + "d" * 64,
        catalog_dataset_hash=_HASH,
        catalog_index_hash=_INDEX_HASH,
        retrieved_at_utc=datetime(2026, 7, 25, tzinfo=UTC),
        events=(
            KisDailyCorporateActionEvent(
                symbol="QQQ",
                source_date=date(2024, 3, 15),
                mapped_kis_session_date=date(2024, 3, 15),
                event_kind="cash_distribution",
                value=Decimal("0.57"),
            ),
            KisDailyCorporateActionEvent(
                symbol="SPY",
                source_date=date(2024, 3, 18),
                mapped_kis_session_date=date(2024, 3, 18),
                event_kind="cash_distribution",
                value=Decimal("1.23"),
            ),
        ),
        event_counts={
            "QQQ": {"cash_distribution": 1, "split": 0},
            "SPY": {"cash_distribution": 1, "split": 0},
        },
    )

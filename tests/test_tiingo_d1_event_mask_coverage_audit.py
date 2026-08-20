from __future__ import annotations

import json
import os
import socket
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.data.tiingo_etf_daily import (
    TIINGO_ETF_D1_SYMBOLS,
    LoadedTiingoEtfDailySnapshot,
    TiingoEtfDailyRow,
    TiingoEtfDailySnapshot,
)
from thericher_v2.research import tiingo_d1_event_mask_coverage_audit as audit
from thericher_v2.research import tiingo_d1_trend_mean_reversion_rotation as rotation


def test_audit_binds_the_completed_rotation_and_retains_aggregate_masks_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("event-mask audit must not access the network")

    def fail_environment(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("event-mask audit must not access environment credentials")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(os, "getenv", fail_environment)
    artifact_root = tmp_path / "external-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot()
    rotation.run_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="rotation-r1",
        repo_root=repo_root,
    )
    rotation.validate_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="rotation-r1",
        repo_root=repo_root,
    )

    run = audit.run_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        artifact_root=artifact_root,
        rotation_artifact_root=artifact_root,
        rotation_run_label="rotation-r1",
        run_label="audit-r1",
        repo_root=repo_root,
    )
    receipt = audit.validate_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        artifact_root=artifact_root,
        rotation_artifact_root=artifact_root,
        rotation_run_label="rotation-r1",
        run_label="audit-r1",
        repo_root=repo_root,
    )
    rerun = audit.run_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        artifact_root=artifact_root,
        rotation_artifact_root=artifact_root,
        rotation_run_label="rotation-r1",
        run_label="audit-r1",
        repo_root=repo_root,
    )

    summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
    validation = json.loads(receipt.validation_path.read_text(encoding="utf-8"))
    prepared = rotation.prepare_tiingo_d1_trend_mean_reversion_rotation(snapshot)
    validation_phase = run.audit.phases[1]

    assert run.audit.status == "consistent"
    assert rerun.precommit_hash == run.precommit_hash
    assert receipt.status == "verified"
    assert receipt.rotation_precommit_hash == run.audit.rotation_precommit_hash
    assert validation_phase.event_any_count > 0
    assert validation_phase.discontinuity_any_count > 0
    assert validation_phase.overlap_count > 0
    assert validation_phase.discontinuity_only_excluded_count > 0
    assert validation_phase.event_priority_excluded_count == (
        prepared.validation.event_excluded_count
    )
    assert validation_phase.discontinuity_only_excluded_count == (
        prepared.validation.discontinuity_excluded_count
    )
    assert validation_phase.unmasked_count == prepared.validation.accepted_decision_count
    assert summary["audit"]["raw_market_data_written"] is False
    assert summary["audit"]["performance_claim_allowed"] is False
    assert summary["audit"]["paper_input_allowed"] is False
    assert validation["source_reattached"] is True
    assert validation["rotation_precommit_hash"] == run.audit.rotation_precommit_hash
    assert _raw_field_names(summary).isdisjoint(
        {"open", "high", "low", "close", "volume", "div_cash", "split_factor", "session_date"}
    )

    with pytest.raises(ValueError, match="outside Git"):
        audit.run_tiingo_d1_event_mask_coverage_audit(
            snapshot,
            artifact_root=repo_root / "model-artifacts",
            rotation_artifact_root=artifact_root,
            rotation_run_label="rotation-r1",
            run_label="repo-root-r1",
            repo_root=repo_root,
        )


def test_audit_rejects_tampered_summary_binding(tmp_path: Path) -> None:
    artifact_root = tmp_path / "external-artifacts"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    snapshot = _snapshot()
    rotation.run_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="rotation-r1",
        repo_root=repo_root,
    )
    rotation.validate_tiingo_d1_trend_mean_reversion_rotation(
        snapshot,
        artifact_root=artifact_root,
        run_label="rotation-r1",
        repo_root=repo_root,
    )
    run = audit.run_tiingo_d1_event_mask_coverage_audit(
        snapshot,
        artifact_root=artifact_root,
        rotation_artifact_root=artifact_root,
        rotation_run_label="rotation-r1",
        run_label="audit-r1",
        repo_root=repo_root,
    )

    run.summary_path.write_text("{}\n", encoding="ascii")
    with pytest.raises(ValueError, match="evidence binding"):
        audit.validate_tiingo_d1_event_mask_coverage_audit(
            snapshot,
            artifact_root=artifact_root,
            rotation_artifact_root=artifact_root,
            rotation_run_label="rotation-r1",
            run_label="audit-r1",
            repo_root=repo_root,
        )


def test_audit_module_has_no_credential_network_or_execution_surface() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "thericher_v2"
        / "research"
        / "tiingo_d1_event_mask_coverage_audit.py"
    ).read_text(encoding="ascii").lower()

    assert ".env" not in source
    assert "socket" not in source
    assert "requests" not in source
    assert "thericher_v2.execution" not in source


def _raw_field_names(value: object) -> set[str]:
    keys: set[str] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            keys.update(current)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return keys


def _snapshot() -> LoadedTiingoEtfDailySnapshot:
    count = 1_000
    rows_by_symbol = {
        symbol: tuple(
            _row(symbol=symbol, index=index)
            for index in range(count)
        )
        for symbol in TIINGO_ETF_D1_SYMBOLS
    }
    snapshot = TiingoEtfDailySnapshot(
        snapshot_dir=Path(
            "D:/market_data/us_equities/tiingo_etf_daily/canonical/"
            "snapshot=fixture-event-mask-audit-r1"
        ),
        dataset_id="us_equities.tiingo_etf_daily.snapshot=fixture-event-mask-audit-r1",
        dataset_hash="sha256:" + "a" * 64,
        manifest_hash="sha256:" + "b" * 64,
        raw_hashes={
            symbol: "sha256:" + character * 64
            for symbol, character in zip(TIINGO_ETF_D1_SYMBOLS, "cde", strict=True)
        },
        session_counts={symbol: count for symbol in TIINGO_ETF_D1_SYMBOLS},
        date_ranges={
            symbol: (rows[0].session_date, rows[-1].session_date)
            for symbol, rows in rows_by_symbol.items()
        },
        event_session_counts={
            symbol: sum(row.div_cash != 0 or row.split_factor != 1 for row in rows)
            for symbol, rows in rows_by_symbol.items()
        },
        row_count=count * len(TIINGO_ETF_D1_SYMBOLS),
        free_percent=40.0,
    )
    return LoadedTiingoEtfDailySnapshot(snapshot=snapshot, rows_by_symbol=rows_by_symbol)


def _row(*, symbol: str, index: int) -> TiingoEtfDailyRow:
    close = Decimal("125") if symbol == "IWM" and index == 795 else Decimal("100")
    return TiingoEtfDailyRow(
        symbol=symbol,
        session_date=date(2020, 1, 1) + timedelta(days=index),
        open=close - Decimal("0.01"),
        high=close + Decimal("0.02"),
        low=close - Decimal("0.03"),
        close=close,
        volume=Decimal("1000"),
        div_cash=Decimal("1") if symbol == "QQQ" and index == 790 else Decimal("0"),
        split_factor=Decimal("1"),
    )

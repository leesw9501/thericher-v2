from __future__ import annotations

import inspect
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_broad_d1_geometry_audit as audit
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanelSelection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader


def test_writes_an_aggregate_only_external_geometry_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection(tmp_path)
    monkeypatch.setattr(
        audit,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        lambda *_args, **_kwargs: selection,
    )
    _deny_external_access(monkeypatch)
    repository = tmp_path / "repo"
    repository.mkdir()

    result = audit.run_kis_broad_d1_geometry_audit(
        manifest_path=tmp_path / "panel" / "manifest.json",
        materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=tmp_path / "artifacts",
        run_label="unit-a",
        repo_root=repository,
        spec=_spec(),
    )

    payload = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert result.audit is not None
    assert payload["ratio_bins"] == [
        {
            "affected_bar_count": 1,
            "affected_session_count": 1,
            "affected_target_count": 1,
            "threshold": 2.0,
        },
        {
            "affected_bar_count": 1,
            "affected_session_count": 1,
            "affected_target_count": 1,
            "threshold": 3.0,
        },
        {
            "affected_bar_count": 0,
            "affected_session_count": 0,
            "affected_target_count": 0,
            "threshold": 5.0,
        },
        {
            "affected_bar_count": 0,
            "affected_session_count": 0,
            "affected_target_count": 0,
            "threshold": 10.0,
        },
    ]
    assert payload["feature_event_censoring"] == {
        "development_available_pair_count": 85,
        "development_available_per_target_max": 35,
        "development_available_per_target_min": 15,
        "event_censored_candidate_input_eligible": True,
        "event_definition": "high_low_ratio_gt_fixed_2",
        "feature_event_count": 1,
        "feature_event_mask_sha256": result.audit.feature_event_mask_sha256,
        "feature_event_session_count": 1,
        "feature_event_target_count": 1,
        "feature_window": "t_minus_19_through_t_completed_bars_only",
        "target_event_censoring": False,
        "validation_available_pair_count": 57,
        "validation_available_per_session_max": 3,
        "validation_available_per_session_min": 3,
        "validation_available_per_target_max": 19,
        "validation_available_per_target_min": 19,
        "validation_sessions_below_minimum_count": 0,
    }
    assert payload["artifact_policy"]["network_access"] is False
    assert payload["artifact_policy"]["credentials_read"] is False
    assert payload["scope"]["model_training_eligible"] is False
    assert result.receipt_path.is_relative_to(tmp_path / "artifacts")
    text = result.receipt_path.read_text(encoding="utf-8")
    assert "AAA/NAS" not in text
    assert "100.00" not in text
    assert "\"open\"" not in text
    assert "\"close\"" not in text


def test_writes_a_scoped_input_unavailable_receipt_without_opening_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        audit,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("broad daily panel selection exact coverage is insufficient")
        ),
    )
    repository = tmp_path / "repo"
    repository.mkdir()

    result = audit.run_kis_broad_d1_geometry_audit(
        manifest_path=tmp_path / "panel" / "manifest.json",
        materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=tmp_path / "artifacts",
        run_label="coverage-short",
        repo_root=repository,
        spec=_spec(),
    )

    assert result.status == "input_unavailable"
    assert result.audit is None
    assert json.loads(result.receipt_path.read_text(encoding="utf-8"))["reason"] == (
        "insufficient_exact_common_session_coverage"
    )


def test_rejects_a_repository_artifact_root_before_loading_the_panel(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        audit.run_kis_broad_d1_geometry_audit(
            manifest_path=tmp_path / "panel" / "manifest.json",
            materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
            cache_root=tmp_path / "cache",
            panel_root=tmp_path / "panel",
            artifact_root=repository / "artifacts",
            run_label="repo-artifact",
            repo_root=repository,
            spec=_spec(),
        )


def test_module_has_no_network_credential_or_broker_route() -> None:
    source = inspect.getsource(audit)

    assert "KisPaperMarketDataClient" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert ".env" not in source


def test_feature_event_censoring_does_not_remove_an_unseen_next_bar_label() -> None:
    spec = _spec()
    events = [False] * 100
    events[25] = True

    availability = audit._feature_availability(events, spec)

    assert availability[24] is True
    assert availability[25:45] == [False] * 20
    assert availability[45] is True


def _spec() -> audit.KisBroadD1GeometryAuditSpec:
    return audit.KisBroadD1GeometryAuditSpec(
        cohort_target_count=3,
        history_session_count=100,
        development_session_count=56,
        purge_session_count=4,
        validation_session_count=40,
        minimum_validation_available_target_count=2,
        raw_byte_attestation_limit=6,
    )


def _selection(tmp_path: Path) -> KisPaperDailyBroadPanelSelection:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "index.json").write_text("{}\n", encoding="utf-8")
    selected_target_keys = ("AAA/NAS", "BBB/NAS", "CCC/NAS")
    bars_by_target = {}
    for target_index, target_key in enumerate(selected_target_keys):
        symbol = target_key.split("/", maxsplit=1)[0]
        bars = tuple(_bar(symbol, target_index, session) for session in range(102))
        bars_by_target[target_key] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
            dataset_hash="sha256:" + "d" * 64,
            source_path=source_root / "index.json",
            bars=bars,
        )
    return KisPaperDailyBroadPanelSelection(
        dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
        dataset_hash="sha256:" + "d" * 64,
        manifest_sha256="sha256:" + "e" * 64,
        materialization_receipt_sha256="sha256:" + "f" * 64,
        index_sha256="sha256:" + "a" * 64,
        source_root=source_root,
        full_target_count=8,
        coverage_eligible_target_count=4,
        minimum_bar_count=101,
        common_session_count=100,
        terminal_buffer_sessions=1,
        raw_byte_attested_target_count=3,
        selected_target_keys=selected_target_keys,
        bars_by_target=bars_by_target,
    )


def _bar(symbol: str, target_index: int, session: int) -> Bar:
    open_value = Decimal("100.00") + Decimal(target_index) + Decimal(session) / Decimal("10")
    close_value = open_value * (Decimal("1.01") if session % 2 else Decimal("0.99"))
    high_value = max(open_value, close_value) * Decimal("1.01")
    low_value = min(open_value, close_value) * Decimal("0.99")
    if target_index == 0 and session == 25:
        high_value = low_value * Decimal("4")
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=session),
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("geometry audit must not use network or credentials")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(os, "getenv", fail)

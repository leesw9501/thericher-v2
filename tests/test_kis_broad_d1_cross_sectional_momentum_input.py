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
from thericher_v2.data import kis_broad_d1_cross_sectional_momentum_input as momentum_input
from thericher_v2.data import kis_broad_d1_geometry_audit as geometry_audit
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanelSelection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader


def test_reattaches_one_read_only_causal_grid_and_terminal_buffer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection(tmp_path)
    receipt_path = _write_audit_receipt(tmp_path, selection)
    source_index = selection.source_root / "index.json"
    index_before = source_index.read_bytes()
    seen: dict[str, object] = {}

    def load_selection(
        manifest_path: Path | str,
        **kwargs: object,
    ) -> KisPaperDailyBroadPanelSelection:
        seen["manifest_path"] = manifest_path
        seen["kwargs"] = kwargs
        return selection

    monkeypatch.setattr(
        momentum_input,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        load_selection,
    )
    _deny_external_access(monkeypatch)

    result = momentum_input.build_kis_broad_d1_cross_sectional_momentum_input(
        manifest_path=tmp_path / "panel" / "manifest.json",
        materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
        geometry_audit_receipt_path=receipt_path,
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        repo_root=tmp_path / "repo",
    )

    assert seen["manifest_path"] == tmp_path / "panel" / "manifest.json"
    assert seen["kwargs"] == {
        "materialization_receipt_path": tmp_path / "materialization" / "receipt.json",
        "cohort_target_count": 128,
        "minimum_bar_count": 801,
        "common_session_count": 800,
        "terminal_buffer_sessions": 1,
        "raw_byte_attestation_limit": 512,
        "cache_root": tmp_path / "cache",
        "panel_root": tmp_path / "panel",
        "repo_root": tmp_path / "repo",
    }
    assert result.dataset_hash == selection.dataset_hash
    assert result.manifest_sha256 == selection.manifest_sha256
    assert result.materialization_receipt_sha256 == selection.materialization_receipt_sha256
    assert result.source_index_hash == selection.index_sha256
    assert result.target_key_set_hash == selection.selected_target_key_set_hash
    assert result.limitations == (
        *selection.limitations,
        "alternate_daily_representation_semantics_unproven",
    )
    assert len(result.decision_session_grid) == 800
    assert result.terminal_execution_session > result.decision_session_grid[-1]
    assert result.target_count == 128
    assert tuple(result.event_availability_by_lookback) == (5, 20, 60)
    assert source_index.read_bytes() == index_before

    target_key = selection.selected_target_keys[0]
    grid_bars = result.grid_bars_by_target[target_key]
    assert len(grid_bars) == 800
    assert all(bar.timeframe is Timeframe.D1 and bar.complete for bar in grid_bars)
    assert tuple(bar.start_ts for bar in grid_bars) == result.decision_session_grid
    assert (
        result.terminal_execution_bars_by_target[target_key].start_ts
        == result.terminal_execution_session
    )
    assert result.range_event_flags_by_target[target_key][120] is True
    assert result.availability_for(5)[target_key][120:125] == (False,) * 5
    assert result.availability_for(5)[target_key][125] is True
    assert result.availability_for(20)[target_key][120:140] == (False,) * 20
    assert result.availability_for(20)[target_key][140] is True
    assert result.availability_for(60)[target_key][120:180] == (False,) * 60
    assert result.availability_for(60)[target_key][180] is True
    assert result.availability_for(5)[target_key][799] is True


def test_rejects_a_changed_panel_identity_against_the_prior_audit(tmp_path: Path) -> None:
    audited_selection = _selection(tmp_path / "audited")
    changed_selection = _selection(tmp_path / "changed", manifest_character="9")
    audit = geometry_audit.build_kis_broad_d1_geometry_audit_from_selection(audited_selection)

    with pytest.raises(
        momentum_input.KisBroadD1CrossSectionalMomentumInputUnavailable,
        match="geometry_audit_mismatch",
    ) as error:
        momentum_input.build_kis_broad_d1_cross_sectional_momentum_input_from_selection(
            changed_selection,
            geometry_audit=audit,
            geometry_audit_receipt_sha256="sha256:" + "1" * 64,
        )

    assert error.value.code == "geometry_audit_mismatch"


def test_rejects_a_mismatched_geometry_audit_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection(tmp_path)
    receipt_path = _write_audit_receipt(tmp_path, selection)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["contract_sha256"] = "sha256:" + "9" * 64
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        momentum_input,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        lambda *_args, **_kwargs: selection,
    )

    with pytest.raises(
        momentum_input.KisBroadD1CrossSectionalMomentumInputUnavailable,
        match="geometry_audit_mismatch",
    ) as error:
        momentum_input.build_kis_broad_d1_cross_sectional_momentum_input(
            manifest_path=tmp_path / "panel" / "manifest.json",
            materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
            geometry_audit_receipt_path=receipt_path,
            cache_root=tmp_path / "cache",
            panel_root=tmp_path / "panel",
        )

    assert error.value.code == "geometry_audit_mismatch"


@pytest.mark.parametrize(
    ("loader_error", "expected_code"),
    (
        ("broad daily panel selection coverage is insufficient", "insufficient_eligible_symbols"),
        (
            "broad daily panel selection exact coverage is insufficient",
            "insufficient_coverage",
        ),
        (
            "broad daily panel selected target does not reattest",
            "malformed_or_changed_source",
        ),
    ),
)
def test_categorizes_unavailable_selected_panel_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loader_error: str,
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        momentum_input,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError(loader_error)),
    )

    with pytest.raises(
        momentum_input.KisBroadD1CrossSectionalMomentumInputUnavailable,
        match=expected_code,
    ) as error:
        momentum_input.build_kis_broad_d1_cross_sectional_momentum_input(
            manifest_path=tmp_path / "panel" / "manifest.json",
            materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
            geometry_audit_receipt_path=tmp_path / "audit" / "summary.json",
            cache_root=tmp_path / "cache",
            panel_root=tmp_path / "panel",
        )

    assert error.value.code == expected_code


def test_categorizes_an_undersized_selected_cohort(tmp_path: Path) -> None:
    selection = _selection(tmp_path, target_count=3)

    with pytest.raises(
        momentum_input.KisBroadD1CrossSectionalMomentumInputUnavailable,
        match="insufficient_eligible_symbols",
    ) as error:
        momentum_input.build_kis_broad_d1_cross_sectional_momentum_input_from_selection(
            selection,
            geometry_audit=None,  # type: ignore[arg-type]
            geometry_audit_receipt_sha256="sha256:" + "1" * 64,
        )

    assert error.value.code == "insufficient_eligible_symbols"


def test_module_has_no_network_credential_broker_or_write_route() -> None:
    source = inspect.getsource(momentum_input)

    assert "KisPaperMarketDataClient" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert ".env" not in source
    assert "urllib" not in source
    assert "open(" not in source
    assert ".write_" not in source


def _selection(
    tmp_path: Path,
    *,
    target_count: int = 128,
    manifest_character: str = "e",
) -> KisPaperDailyBroadPanelSelection:
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True, exist_ok=True)
    index_path = source_root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    target_keys = tuple(f"S{index:03d}/NAS" for index in range(target_count))
    bars_by_target = {}
    for target_index, target_key in enumerate(target_keys):
        symbol = target_key.split("/", maxsplit=1)[0]
        bars_by_target[target_key] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
            dataset_hash="sha256:" + "d" * 64,
            source_path=index_path,
            bars=tuple(_bar(symbol, target_index, session) for session in range(801)),
        )
    return KisPaperDailyBroadPanelSelection(
        dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
        dataset_hash="sha256:" + "d" * 64,
        manifest_sha256="sha256:" + manifest_character * 64,
        materialization_receipt_sha256="sha256:" + "f" * 64,
        index_sha256="sha256:" + "a" * 64,
        source_root=source_root,
        full_target_count=target_count + 2,
        coverage_eligible_target_count=target_count,
        minimum_bar_count=801,
        common_session_count=800,
        terminal_buffer_sessions=1,
        raw_byte_attested_target_count=target_count,
        selected_target_keys=target_keys,
        bars_by_target=bars_by_target,
    )


def _write_audit_receipt(tmp_path: Path, selection: KisPaperDailyBroadPanelSelection) -> Path:
    audit = geometry_audit.build_kis_broad_d1_geometry_audit_from_selection(selection)
    path = tmp_path / "audit" / "summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit.payload(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def _bar(symbol: str, target_index: int, session: int) -> Bar:
    open_value = Decimal("100.00") + Decimal(target_index) + Decimal(session) / Decimal("10")
    close_value = open_value * (Decimal("1.01") if session % 2 else Decimal("0.99"))
    high_value = max(open_value, close_value) * Decimal("1.01")
    low_value = min(open_value, close_value) * Decimal("0.99")
    if target_index == 0 and session == 120:
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
        raise AssertionError("input adapter must not use network or credentials")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(os, "getenv", fail)

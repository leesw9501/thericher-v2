from __future__ import annotations

import inspect
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanel,
    KisPaperDailyBroadPanelSelection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_broad_d1_causal_cpu_preflight as preflight


def test_runs_source_safe_offline_cpu_preflight_without_network_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    panel = _panel(tmp_path)
    _use_panel(monkeypatch, panel)
    _deny_network(monkeypatch)
    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    artifact_root = tmp_path / "artifacts"

    first = preflight.run_kis_broad_d1_causal_cpu_preflight(
        manifest_path=tmp_path / "panel" / "manifest.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=artifact_root,
        run_label="cpu-a",
        review_status="uncertain",
        repo_root=repository_root,
        spec=_spec(),
    )
    second = preflight.run_kis_broad_d1_causal_cpu_preflight(
        manifest_path=tmp_path / "panel" / "manifest.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=artifact_root,
        run_label="cpu-b",
        review_status="uncertain",
        repo_root=repository_root,
        spec=_spec(),
    )

    first_precommit = _read(first.run_directory / "precommit.json")
    first_summary = _read(first.receipt_path)
    second_summary = _read(second.receipt_path)
    assert first.status == "completed"
    assert second.status == "completed"
    assert first.contract_hash == second.contract_hash
    assert first_precommit["availability"] == {
        "features_use_completed_bar_t_or_earlier": True,
        "target_uses_next_completed_bar": True,
        "terminal_panel_session_excluded": True,
        "target_tie_rule": "zero_direction",
        "zero_range_feature_rule": "neutral_close_location",
        "within_bar_mixed_adjustment_screen": "reject_if_high_low_ratio_exceeds_fixed_limit",
    }
    assert first_summary["artifact_policy"] == {
        "broker_access": False,
        "credentials_read": False,
        "external_artifact_only": True,
        "gpu_used": False,
        "model_weights_persisted": False,
        "network_access": False,
        "prediction_rows_persisted": False,
        "prices_persisted": False,
        "raw_market_data_persisted": False,
        "volumes_persisted": False,
    }
    assert first_summary["result"]["profitability_claim_allowed"] is False
    assert first_summary["result"]["paper_input_allowed"] is False
    assert first_summary["source"]["current_listing_only"] is True
    assert first_summary["source"]["corporate_action_qualified"] is False
    assert first_summary["metrics"] == second_summary["metrics"]
    assert first_summary["sample_counts"]["development"] > 0
    assert first_summary["sample_counts"]["validation"] > 0
    assert first.frozen_campaign is not None
    assert first.outcome is not None
    assert {path.name for path in first.run_directory.iterdir()} == {
        "precommit.json",
        "summary.json",
    }
    summary_text = first.receipt_path.read_text(encoding="utf-8")
    assert "100.00" not in summary_text
    assert "101.00" not in summary_text
    assert "AAA/NAS" not in summary_text
    assert "KIS_PAPER_APP_KEY" not in inspect.getsource(preflight)
    assert "KIS_LIVE_" not in inspect.getsource(preflight)
    assert "environ" not in inspect.getsource(preflight)


def test_uses_next_bar_target_and_keeps_validation_feature_windows_inside_partition(
    tmp_path: Path,
) -> None:
    panel = _panel(tmp_path)
    spec = _spec()
    prepared = preflight.build_kis_broad_d1_causal_cpu_preflight_input_from_panel(
        panel,
        spec=spec,
    )
    first_target = panel.target_keys[0]
    bars = panel.bars_by_target[first_target].bars
    grid = bars[-(spec.history_session_count + spec.terminal_buffer_sessions) : -1]
    first_development_target_index = spec.feature_lookback_sessions + 1
    expected_first_label = int(
        grid[first_development_target_index].close
        > grid[first_development_target_index].open
    )

    assert prepared.development_labels[0] == expected_first_label
    assert prepared.validation_labels.shape == (
        spec.cohort_target_count,
        spec.validation_sample_count_per_target,
    )
    assert prepared.common_session_start == grid[0].start_ts
    assert prepared.common_session_end == grid[-1].start_ts


def test_reattaches_a_frozen_selected_subset_without_opening_the_full_panel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    panel = _panel(tmp_path)
    selection = _selection(panel, _spec())
    calls: list[str] = []

    def selected_loader(*_args: object, **_kwargs: object) -> KisPaperDailyBroadPanelSelection:
        calls.append("selection")
        return selection

    def full_loader(*_args: object, **_kwargs: object) -> KisPaperDailyBroadPanel:
        raise AssertionError("full broad panel loader must not run")

    monkeypatch.setattr(
        preflight,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        selected_loader,
    )
    monkeypatch.setattr(preflight, "load_materialized_kis_paper_daily_broad_panel", full_loader)

    prepared = preflight.build_kis_broad_d1_causal_cpu_preflight_input(
        manifest_path=tmp_path / "panel" / "manifest.json",
        materialization_receipt_path=tmp_path / "artifacts" / "receipt.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        repo_root=tmp_path / "repo",
        spec=_spec(),
    )

    assert calls == ["selection"]
    assert prepared.materialization_receipt_sha256 == selection.materialization_receipt_sha256
    assert prepared.full_target_count == len(panel.target_keys)
    assert prepared.raw_byte_attested_target_count == prepared.target_count
    assert prepared.target_key_set_hash == selection.selected_target_key_set_hash


def test_records_scoped_input_unavailable_without_fitting_when_coverage_is_short(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_panel(monkeypatch, _panel(tmp_path, target_count=2))
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    result = preflight.run_kis_broad_d1_causal_cpu_preflight(
        manifest_path=tmp_path / "panel" / "manifest.json",
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=tmp_path / "artifacts",
        run_label="coverage-short",
        review_status="uncertain",
        repo_root=repository_root,
        spec=_spec(),
    )

    assert result.status == "input_unavailable"
    assert _read(result.receipt_path)["reason"] == "insufficient_coverage_eligible_targets"
    assert not (result.run_directory / "precommit.json").exists()
    assert not list((tmp_path / "artifacts" / "_control").glob("**/*"))


def test_rejects_mixed_within_bar_adjustment_geometry_before_model_fit(tmp_path: Path) -> None:
    panel = _panel(tmp_path)
    target_key = panel.target_keys[0]
    catalog = panel.bars_by_target[target_key]
    changed = replace(catalog.bars[20], high=catalog.bars[20].low * Decimal("3"))
    changed_catalog = _cataloged_bars_from_verified_loader(
        dataset_id=catalog.dataset_id,
        dataset_hash=catalog.dataset_hash,
        source_path=catalog.source_path,
        bars=(*catalog.bars[:20], changed, *catalog.bars[21:]),
    )
    object.__setattr__(
        panel,
        "bars_by_target",
        MappingProxyType({**panel.bars_by_target, target_key: changed_catalog}),
    )

    with pytest.raises(
        preflight.KisBroadD1CausalCpuInputUnavailable,
        match="within_bar_geometry_integrity_failure",
    ):
        preflight.build_kis_broad_d1_causal_cpu_preflight_input_from_panel(
            panel,
            spec=_spec(),
        )


def test_rejects_repository_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_panel(monkeypatch, _panel(tmp_path))
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        preflight.run_kis_broad_d1_causal_cpu_preflight(
            manifest_path=tmp_path / "panel" / "manifest.json",
            cache_root=tmp_path / "cache",
            panel_root=tmp_path / "panel",
            artifact_root=repository_root / "artifacts",
            run_label="repo-artifact",
            review_status="uncertain",
            repo_root=repository_root,
            spec=_spec(),
        )


def test_docker_cpu_preflight_is_network_isolated_and_has_no_kis_environment() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    start = compose.index("  kis-broad-d1-causal-cpu-preflight:")
    end = compose.index("\n  chronos-t5-tiny-acquisition:", start)
    service = compose[start:end]

    assert 'profiles: ["kis-broad-d1-causal-cpu"]' in service
    assert "network_mode: none" in service
    assert "read_only: true" in service
    assert "gpus:" not in service
    assert "KIS_PAPER_" not in service
    assert "KIS_LIVE_" not in service
    assert "/app/market_data:ro" in service
    assert "/app/model_artifacts" in service
    assert "--materialization-receipt-path" in service
    assert "daily-nas-broad-panel-v1/panel=6f83952b101050f22103/receipt.json" in service


def _spec() -> preflight.KisBroadD1CausalCpuPreflightSpec:
    return preflight.KisBroadD1CausalCpuPreflightSpec(
        cohort_target_count=3,
        history_session_count=100,
        development_session_count=56,
        purge_session_count=4,
        validation_session_count=40,
        feature_lookback_sessions=20,
    )


def _panel(tmp_path: Path, *, target_count: int = 4) -> KisPaperDailyBroadPanel:
    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    keys = tuple(f"{chr(65 + index)}AA/NAS" for index in range(target_count))
    bars_by_target = {}
    for target_index, target_key in enumerate(keys):
        symbol = target_key.split("/", maxsplit=1)[0]
        bars = tuple(_bar(symbol, target_index, session) for session in range(102))
        bars_by_target[target_key] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
            dataset_hash="sha256:" + "d" * 64,
            source_path=source_root / "index.json",
            bars=bars,
        )
    result = object.__new__(KisPaperDailyBroadPanel)
    object.__setattr__(result, "dataset_id", KIS_PAPER_DAILY_BROAD_PANEL_ID)
    object.__setattr__(result, "dataset_hash", "sha256:" + "d" * 64)
    object.__setattr__(result, "index_sha256", "sha256:" + "e" * 64)
    object.__setattr__(result, "target_keys", keys)
    object.__setattr__(result, "bars_by_target", MappingProxyType(bars_by_target))
    return result


def _selection(
    panel: KisPaperDailyBroadPanel,
    spec: preflight.KisBroadD1CausalCpuPreflightSpec,
) -> KisPaperDailyBroadPanelSelection:
    selected_target_keys = panel.target_keys[: spec.cohort_target_count]
    return KisPaperDailyBroadPanelSelection(
        dataset_id=panel.dataset_id,
        dataset_hash=panel.dataset_hash,
        manifest_sha256="sha256:" + "f" * 64,
        materialization_receipt_sha256="sha256:" + "a" * 64,
        index_sha256=panel.index_sha256,
        source_root=panel.bars_by_target[selected_target_keys[0]].source_path.parent,
        full_target_count=len(panel.target_keys),
        coverage_eligible_target_count=len(panel.target_keys),
        minimum_bar_count=spec.history_session_count + spec.terminal_buffer_sessions,
        common_session_count=spec.history_session_count,
        terminal_buffer_sessions=spec.terminal_buffer_sessions,
        raw_byte_attested_target_count=len(selected_target_keys),
        selected_target_keys=selected_target_keys,
        bars_by_target={key: panel.bars_by_target[key] for key in selected_target_keys},
    )


def _bar(symbol: str, target_index: int, session: int) -> Bar:
    direction_up = (session + target_index * 2) % 5 in {0, 1, 4}
    open_value = Decimal("100.00") + Decimal(target_index) + Decimal(session) / Decimal("10")
    close_value = open_value * (Decimal("1.01") if direction_up else Decimal("0.99"))
    if session == 0:
        close_value = open_value
    high_value = max(open_value, close_value) * Decimal("1.01")
    low_value = min(open_value, close_value) * Decimal("0.99")
    if session == 1:
        high_value = open_value
        low_value = open_value
        close_value = open_value
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


def _use_panel(monkeypatch: pytest.MonkeyPatch, panel: KisPaperDailyBroadPanel) -> None:
    monkeypatch.setattr(
        preflight,
        "load_materialized_kis_paper_daily_broad_panel",
        lambda *_args, **_kwargs: panel,
    )


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))

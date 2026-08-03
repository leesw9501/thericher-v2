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
from thericher_v2.data import kis_broad_d1_geometry_audit as geometry_audit
from thericher_v2.data.kis_paper_daily_broad_panel import (
    KIS_PAPER_DAILY_BROAD_PANEL_ID,
    KisPaperDailyBroadPanelSelection,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.research import kis_broad_d1_event_censored_cpu_preflight as preflight


def test_runs_one_aggregate_only_event_censored_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection(tmp_path)
    spec = _spec()
    audit_receipt = _geometry_audit_receipt(tmp_path, selection, spec)
    monkeypatch.setattr(
        preflight,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        lambda *_args, **_kwargs: selection,
    )
    _deny_external_access(monkeypatch)
    repository = tmp_path / "repo"
    repository.mkdir()

    result = preflight.run_kis_broad_d1_event_censored_cpu_preflight(
        manifest_path=tmp_path / "panel" / "manifest.json",
        materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
        geometry_audit_receipt_path=audit_receipt,
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=tmp_path / "artifacts",
        run_label="event-a",
        review_status="supported-with-limits",
        repo_root=repository,
        spec=spec,
    )

    precommit = _read(result.run_directory / "precommit.json")
    summary = _read(result.receipt_path)
    assert result.status == "completed"
    assert result.frozen_campaign is not None
    assert result.outcome is not None
    assert precommit["availability"] == {
        "all_baselines_bootstraps_and_nulls_use_same_availability_mask": True,
        "event_definition": "high_low_ratio_gt_fixed_2",
        "feature_window_censoring": "t_minus_19_through_t_completed_bars_only",
        "features_use_completed_bar_t_or_earlier": True,
        "target_event_censoring": False,
        "target_tie_rule": "zero_direction",
        "target_uses_next_completed_bar": True,
        "terminal_panel_session_excluded": True,
    }
    assert precommit["sample_counts"] == {
        "development_available_pairs": 85,
        "validation_available_pairs": 57,
        "validation_available_per_session_max": 3,
        "validation_available_per_session_min": 3,
    }
    assert summary["artifact_policy"] == {
        "broker_access": False,
        "credentials_read": False,
        "external_artifact_only": True,
        "gpu_used": False,
        "model_weights_persisted": False,
        "network_access": False,
        "prediction_rows_persisted": False,
        "prices_persisted": False,
        "raw_market_data_persisted": False,
        "targets_persisted": False,
        "volumes_persisted": False,
    }
    assert summary["result"]["profitability_claim_allowed"] is False
    assert summary["result"]["paper_input_allowed"] is False
    assert set(summary["metrics"]) == {
        "balanced_accuracy_advantage_lower_5th_percentile",
        "baseline_balanced_accuracy",
        "causal_falsifiers_passed",
        "cross_sectional_residual_advantage_lower_5th_percentile",
        "development_constant_feature_count",
        "model_balanced_accuracy",
        "model_weights_persisted",
        "per_target_temporal_permutation_null_95th_percentile",
        "prediction_rows_persisted",
        "session_block_permutation_null_95th_percentile",
    }
    assert {path.name for path in result.run_directory.iterdir()} == {
        "precommit.json",
        "summary.json",
    }
    text = result.receipt_path.read_text(encoding="utf-8")
    assert "AAA/NAS" not in text
    assert "100.00" not in text
    assert "\"open\"" not in text
    assert "\"close\"" not in text


def test_censoring_uses_only_completed_feature_window_not_next_bar_label() -> None:
    events = [False] * 100
    events[25] = True

    available = preflight._feature_availability(events, _spec())

    assert available[24] is True
    assert available[25:45] == [False] * 20
    assert available[45] is True


def test_masked_metrics_ignore_unavailable_pairs() -> None:
    numpy = preflight._numpy()
    labels = numpy.asarray([[1, 0], [0, 1]], dtype=numpy.int8)
    predictions = numpy.asarray([[1, 0], [1, 0]], dtype=numpy.int8)
    availability = numpy.asarray([[True, True], [False, False]], dtype=numpy.bool_)

    assert preflight._masked_balanced_accuracy(labels, predictions, availability, numpy) == 1.0


def test_writes_scoped_input_unavailable_when_audit_does_not_reattest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = _selection(tmp_path)
    monkeypatch.setattr(
        preflight,
        "load_materialized_kis_paper_daily_broad_panel_selection",
        lambda *_args, **_kwargs: selection,
    )
    repository = tmp_path / "repo"
    repository.mkdir()
    broken_receipt = tmp_path / "audit" / "summary.json"
    broken_receipt.parent.mkdir()
    broken_receipt.write_text("{}\n", encoding="utf-8")

    result = preflight.run_kis_broad_d1_event_censored_cpu_preflight(
        manifest_path=tmp_path / "panel" / "manifest.json",
        materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
        geometry_audit_receipt_path=broken_receipt,
        cache_root=tmp_path / "cache",
        panel_root=tmp_path / "panel",
        artifact_root=tmp_path / "artifacts",
        run_label="bad-audit",
        review_status="supported-with-limits",
        repo_root=repository,
        spec=_spec(),
    )

    assert result.status == "input_unavailable"
    assert _read(result.receipt_path)["reason"] == "geometry_audit_receipt_mismatch"
    assert not (result.run_directory / "precommit.json").exists()
    assert not list((tmp_path / "artifacts" / "_control").glob("**/*"))


def test_rejects_a_repository_artifact_root_before_loading_input(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ValueError, match="outside the Git workspace"):
        preflight.run_kis_broad_d1_event_censored_cpu_preflight(
            manifest_path=tmp_path / "panel" / "manifest.json",
            materialization_receipt_path=tmp_path / "materialization" / "receipt.json",
            geometry_audit_receipt_path=tmp_path / "audit" / "summary.json",
            cache_root=tmp_path / "cache",
            panel_root=tmp_path / "panel",
            artifact_root=repository / "artifacts",
            run_label="repo-artifact",
            review_status="supported-with-limits",
            repo_root=repository,
            spec=_spec(),
        )


def test_module_has_no_network_credential_or_broker_route() -> None:
    source = inspect.getsource(preflight)

    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert ".env" not in source
    assert "urllib" not in source
    assert "requests" not in source


def test_docker_candidate_is_network_isolated_without_kis_environment() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    start = compose.index("  kis-broad-d1-event-censored-cpu-preflight:")
    end = compose.index("\n  chronos-t5-tiny-acquisition:", start)
    service = compose[start:end]

    assert 'profiles: ["kis-broad-d1-event-censored-cpu"]' in service
    assert "network_mode: none" in service
    assert "read_only: true" in service
    assert "gpus:" not in service
    assert "KIS_PAPER_" not in service
    assert "KIS_LIVE_" not in service
    assert "/app/market_data:ro" in service
    assert "/app/model_artifacts" in service
    assert "--geometry-audit-receipt-path" in service


def _spec() -> preflight.KisBroadD1EventCensoredCpuPreflightSpec:
    return preflight.KisBroadD1EventCensoredCpuPreflightSpec(
        cohort_target_count=3,
        history_session_count=100,
        development_session_count=56,
        purge_session_count=4,
        validation_session_count=40,
        minimum_validation_available_target_count=2,
    )


def _selection(tmp_path: Path) -> KisPaperDailyBroadPanelSelection:
    source_root = tmp_path / "source"
    source_root.mkdir(exist_ok=True)
    index_path = source_root / "index.json"
    index_path.write_text("{}\n", encoding="utf-8")
    selected_target_keys = ("AAA/NAS", "BBB/NAS", "CCC/NAS")
    bars_by_target = {}
    for target_index, target_key in enumerate(selected_target_keys):
        symbol = target_key.split("/", maxsplit=1)[0]
        bars_by_target[target_key] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_BROAD_PANEL_ID,
            dataset_hash="sha256:" + "d" * 64,
            source_path=index_path,
            bars=tuple(_bar(symbol, target_index, session) for session in range(102)),
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


def _geometry_audit_receipt(
    tmp_path: Path,
    selection: KisPaperDailyBroadPanelSelection,
    spec: preflight.KisBroadD1EventCensoredCpuPreflightSpec,
) -> Path:
    audit = geometry_audit.build_kis_broad_d1_geometry_audit_from_selection(
        selection,
        spec=spec.geometry_audit_spec(),
    )
    path = tmp_path / "audit" / "summary.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(audit.payload(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def _bar(symbol: str, target_index: int, session: int) -> Bar:
    direction_up = (session + target_index * 2) % 5 in {0, 1, 4}
    open_value = Decimal("100.00") + Decimal(target_index) + Decimal(session) / Decimal("10")
    close_value = open_value * (Decimal("1.01") if direction_up else Decimal("0.99"))
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
        raise AssertionError("candidate must not use network or credentials")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(os, "getenv", fail)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))

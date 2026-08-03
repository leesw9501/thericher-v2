from __future__ import annotations

import inspect
import json
import socket
import urllib.request
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import (
    kis_broad_d1_invariant_candle_representation_cpu_preflight as preflight,
)


def test_runs_source_safe_target_free_preflight_without_external_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_input = _source_input()
    _deny_external_access(monkeypatch)
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"

    host = preflight.run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
        source_input=source_input,
        artifact_root=artifact_root,
        run_label="host-a",
        repo_root=repository,
    )
    docker_equivalent = preflight.run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
        source_input=source_input,
        artifact_root=artifact_root,
        run_label="docker-a",
        repo_root=repository,
    )

    summary = _read(host.receipt_path)
    receipt_text = host.receipt_path.read_text(encoding="utf-8")
    assert host.status == "completed"
    assert docker_equivalent.status == "completed"
    assert host.receipt_sha256 == docker_equivalent.receipt_sha256
    assert host.receipt_path.read_bytes() == docker_equivalent.receipt_path.read_bytes()
    assert summary["spec"] == {
        "cohort_target_count": 3,
        "cohort_selection": "inherited_reverified_lexicographic_coverage_cohort",
        "cross_sectional_rank": "same_session_midrank_percentile_zero_to_one",
        "development_session_count": 56,
        "history_session_count": 100,
        "purge_session_count": 4,
        "same_day_candle_ratio_features": ["high_to_open", "low_to_open", "close_to_open"],
        "terminal_buffer_sessions": 1,
        "validation_session_count": 40,
        "validation_use": "target_free_representation_confirmation_only",
    }
    assert summary["partitions"]["development"]["session_count"] == 56
    assert summary["partitions"]["purge"] == {
        "excluded_from_representation_confirmation": True,
        "session_count": 4,
    }
    assert summary["partitions"]["validation"]["session_count"] == 40
    assert all(summary["invariance_kill_tests"].values())
    assert summary["artifact_policy"] == {
        "allocation_values_persisted": False,
        "broker_access": False,
        "credentials_read": False,
        "external_artifact_only": True,
        "gpu_used": False,
        "inference_outputs_persisted": False,
        "model_state_persisted": False,
        "network_access": False,
        "paper_access": False,
        "prices_persisted": False,
        "raw_market_data_persisted": False,
        "raw_rows_persisted": False,
        "supervised_targets_persisted": False,
        "symbols_persisted": False,
    }
    assert "AAA/NAS" not in receipt_text
    assert "100.00" not in receipt_text
    assert '"open"' not in receipt_text
    assert '"close"' not in receipt_text
    assert {path.name for path in host.run_directory.iterdir()} == {"summary.json"}


def test_positive_scaling_and_future_or_terminal_mutation_obey_the_causal_contract() -> None:
    source_input = _source_input()
    original = preflight.derive_kis_broad_d1_invariant_candle_representation_digest(source_input)
    scaled = preflight.derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        grid_bars_by_target=preflight._positive_per_symbol_scaled_grid(source_input),
    )
    future_index = source_input.spec.development_session_count
    future_mutated = preflight._future_grid_bar_mutated_grid(
        source_input,
        future_index=future_index,
    )
    prefix = preflight.derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        stop_index=future_index,
    )
    future_prefix = preflight.derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        stop_index=future_index,
        grid_bars_by_target=future_mutated,
    )
    future_full = preflight.derive_kis_broad_d1_invariant_candle_representation_digest(
        source_input,
        grid_bars_by_target=future_mutated,
    )
    terminal_mutated = replace(
        source_input,
        terminal_execution_bars_by_target=preflight._terminal_buffer_mutated_bars(source_input),
    )

    assert scaled.ratio_feature_hash == original.ratio_feature_hash
    assert scaled.rank_feature_hash == original.rank_feature_hash
    assert future_prefix == prefix
    assert future_full.ratio_feature_hash != original.ratio_feature_hash
    assert (
        preflight.derive_kis_broad_d1_invariant_candle_representation_digest(terminal_mutated)
        == original
    )


def test_categorizes_geometry_audit_and_source_geometry_failures(tmp_path: Path) -> None:
    source_input = _source_input()
    repository = tmp_path / "repo"
    repository.mkdir()
    artifact_root = tmp_path / "artifacts"
    audit_mismatch = replace(
        source_input,
        geometry_audit_source_grid_sha256="sha256:" + "9" * 64,
    )
    target_key = source_input.selected_target_keys[0]
    changed_grid = dict(source_input.grid_bars_by_target)
    changed_bars = list(changed_grid[target_key])
    changed_bars[0] = replace(changed_bars[0], complete=False)
    changed_grid[target_key] = tuple(changed_bars)
    geometry_failure = replace(source_input, grid_bars_by_target=changed_grid)

    audit_result = preflight.run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
        source_input=audit_mismatch,
        artifact_root=artifact_root,
        run_label="audit-mismatch",
        repo_root=repository,
    )
    geometry_result = preflight.run_kis_broad_d1_invariant_candle_representation_cpu_preflight(
        source_input=geometry_failure,
        artifact_root=artifact_root,
        run_label="geometry-failure",
        repo_root=repository,
    )

    assert audit_result.status == "input_unavailable"
    assert _read(audit_result.receipt_path)["reason"] == "geometry_audit_mismatch"
    assert geometry_result.status == "input_unavailable"
    assert _read(geometry_result.receipt_path)["reason"] == "source_geometry_failure"


def test_module_and_runner_have_no_network_credential_or_broker_route() -> None:
    module_source = inspect.getsource(preflight)
    runner_source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_broad_d1_invariant_candle_representation_cpu_preflight.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "KIS_PAPER_APP_",
        "KIS_LIVE_",
        ".env",
        "socket",
        "urllib",
        "requests",
        "OrderIntent",
        "LocalPaperBroker",
        "torch",
    ):
        assert forbidden not in module_source
        assert forbidden not in runner_source
    assert "importlib.import_module" in runner_source
    assert "kis_broad_d1_cross_sectional_momentum_input" in runner_source


def test_network_isolated_cpu_compose_service_has_only_read_only_mounts() -> None:
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    start = compose.index("  kis-broad-d1-invariant-candle-representation-cpu-preflight:")
    end = compose.index("\n  chronos-t5-tiny-acquisition:", start)
    service = compose[start:end]

    assert 'profiles: ["kis-broad-d1-invariant-candle-representation-cpu"]' in service
    assert "target: base" in service
    assert "network_mode: none" in service
    assert "read_only: true" in service
    assert "gpus:" not in service
    assert "KIS_PAPER_" not in service
    assert "KIS_LIVE_" not in service
    assert "THERICHER_MODE: off" in service
    assert "run_kis_broad_d1_invariant_candle_representation_cpu_preflight.py" in service
    assert "--geometry-audit-receipt-path" in service
    assert "/app/market_data:ro" in service
    assert "/app/model_artifacts" in service


def _source_input() -> preflight.KisBroadD1InvariantCandleRepresentationInput:
    spec = preflight.KisBroadD1InvariantCandleRepresentationSpec(
        cohort_target_count=3,
        history_session_count=100,
        development_session_count=56,
        purge_session_count=4,
        validation_session_count=40,
    )
    target_keys = ("AAA/NAS", "BBB/NAS", "CCC/NAS")
    grid = tuple(datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(100))
    terminal = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=100)
    grid_bars_by_target = {
        target_key: tuple(
            _bar(target_key.split("/", maxsplit=1)[0], target_index, session)
            for session in range(100)
        )
        for target_index, target_key in enumerate(target_keys)
    }
    terminal_bars_by_target = {
        target_key: _bar(target_key.split("/", maxsplit=1)[0], target_index, 100)
        for target_index, target_key in enumerate(target_keys)
    }
    event_flags_by_target = {
        target_key: tuple(preflight._geometry_event(bar) for bar in bars)
        for target_key, bars in grid_bars_by_target.items()
    }
    return preflight.KisBroadD1InvariantCandleRepresentationInput(
        dataset_id=preflight.KIS_BROAD_D1_INVARIANT_CANDLE_REPRESENTATION_SOURCE_DATASET_ID,
        dataset_hash="sha256:" + "a" * 64,
        manifest_sha256="sha256:" + "b" * 64,
        materialization_receipt_sha256="sha256:" + "c" * 64,
        source_index_hash="sha256:" + "d" * 64,
        target_key_set_hash=preflight._selected_target_key_set_hash(target_keys),
        geometry_audit_receipt_sha256="sha256:" + "f" * 64,
        geometry_audit_contract_sha256="sha256:" + "1" * 64,
        geometry_audit_source_grid_sha256=preflight._sha256_payload(
            {"session_starts": [session.isoformat() for session in grid]}
        ),
        geometry_audit_event_mask_sha256=preflight._sha256_bool_matrix(
            [event_flags_by_target[target_key] for target_key in target_keys]
        ),
        full_target_count=5,
        coverage_eligible_target_count=3,
        raw_byte_attested_target_count=3,
        selected_target_keys=target_keys,
        decision_session_grid=grid,
        terminal_execution_session=terminal,
        grid_bars_by_target=grid_bars_by_target,
        terminal_execution_bars_by_target=terminal_bars_by_target,
        range_event_flags_by_target=event_flags_by_target,
        limitations=(
            "current_listing_only",
            "non_pit",
            "corporate_action_qualified_false",
            "session_finality_unattested",
        ),
        spec=spec,
    )


def _bar(symbol: str, target_index: int, session: int) -> Bar:
    start = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=session)
    open_value = Decimal("100") + Decimal(target_index * 5) + Decimal(session) / Decimal("10")
    direction = (session + target_index) % 3
    close_multiplier = (Decimal("0.99"), Decimal("1.00"), Decimal("1.01"))[direction]
    close_value = open_value * close_multiplier
    high_value = max(open_value, close_value) * (
        Decimal("1.01") + Decimal(target_index) / Decimal("1000")
    )
    low_value = min(open_value, close_value) * (
        Decimal("0.99") - Decimal(target_index) / Decimal("1000")
    )
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start,
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        volume=Decimal("1000"),
        complete=True,
    )


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("preflight must not access the network or credentials")

    original_open = Path.open

    def guard_open(path: Path, *args: object, **kwargs: object):
        if path.name.lower() == ".env":
            fail()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(Path, "open", guard_open)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))

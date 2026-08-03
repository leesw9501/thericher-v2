from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import socket
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.research import kis_broad_d1_cross_sectional_momentum as momentum


def test_writes_a_frozen_source_safe_aggregate_benchmark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_input = _input()
    repository = tmp_path / "repo"
    repository.mkdir()
    _deny_external_access(monkeypatch)

    result = momentum.run_kis_broad_d1_cross_sectional_momentum(
        source_input=source_input,
        execution_parity=_execution_parity(source_input),
        artifact_root=tmp_path / "artifacts",
        run_label="fixture-a",
        review_status="not_required_before_outcome",
        repo_root=repository,
    )

    precommit = json.loads(result.precommit_path.read_text(encoding="utf-8"))
    summary = json.loads(result.receipt_path.read_text(encoding="utf-8"))

    assert result.status == "completed"
    assert result.precommit_path is not None
    assert precommit["spec"]["lookback_sessions_matrix"] == [5, 20, 60]
    assert precommit["spec"]["top_k"] == 10
    assert precommit["spec"]["availability"] == {
        "decision_time": "completed_bar_t_close",
        "entry": "t_plus_1_open",
        "exit": "t_plus_1_close",
        "feature": "completed_close_t_over_completed_close_t_minus_lookback_plus_one",
        "future_feature_access": False,
    }
    assert precommit["spec"]["cost_stress_axis"]["round_trip_bps"] == ["5", "10", "20"]
    assert precommit["spec"]["cost_stress_axis"]["interpretation"] == (
        "unverified_stress_axis_not_realistic_executable_cost_envelope"
    )
    assert precommit["spec"]["cost_stress_axis"]["application"] == (
        "round_trip_bps_times_standard_turnover"
    )
    assert summary["selection"] == {
        "paper_input_allowed": False,
        "promotion_allowed": False,
        "sealed_holdout_accessed": False,
        "winner_selected": False,
    }
    assert [(cell["lookback_sessions"], cell["phase"]) for cell in summary["cells"]] == [
        (5, "development"),
        (5, "validation"),
        (20, "development"),
        (20, "validation"),
        (60, "development"),
        (60, "validation"),
    ]
    assert all(
        cell["status"] == "evaluated" and "candidate" in cell
        for cell in summary["cells"]
    )
    validation_cells = [cell for cell in summary["cells"] if cell["phase"] == "validation"]
    assert all(
        set(cell["validation_kill_tests"])
        == {
            "no_robustness_across_cost_stress",
            "no_signal_after_primary_control",
            "selection_action",
        }
        and cell["validation_kill_tests"]["selection_action"] == "none"
        for cell in validation_cells
    )
    assert summary["source"]["current_listing_only"] is True
    assert summary["source"]["non_pit"] is True
    assert summary["source"]["corporate_action_qualified"] is False
    assert summary["source"]["session_finality_attested"] is False
    assert summary["execution_semantics"]["timing"]["semantic_representability"] == "represented"
    assert (
        summary["execution_semantics"]["timing"]["executable_or_paper_eligibility"]
        == "not_evaluated_by_semantic_attestation"
    )
    assert result.receipt_path.is_relative_to(tmp_path / "artifacts")

    for payload in (precommit, summary):
        _assert_no_raw_fields(payload)
    receipt_text = result.receipt_path.read_text(encoding="utf-8")
    assert "T00/NAS" not in receipt_text
    assert "100.00" not in receipt_text


def test_completed_feature_hygiene_ignores_a_future_entry_bar_event() -> None:
    bars = _bars(target_index=0, event_sessions={101})

    assert momentum._completed_feature_window_is_clean(
        bars,
        decision_index=100,
        lookback=5,
    )


def test_completed_feature_hygiene_rejects_an_event_inside_its_lookback() -> None:
    bars = _bars(target_index=0, event_sessions={100})

    assert not momentum._completed_feature_window_is_clean(
        bars,
        decision_index=100,
        lookback=5,
    )


def test_target_key_set_hash_matches_the_materialized_panel_identity() -> None:
    target_keys = ("T02/NAS", "T01/NAS")
    payload = {"target_keys": ["T01/NAS", "T02/NAS"]}
    canonical_bytes = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    expected = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()

    assert momentum._target_key_set_hash(target_keys) == expected


def test_round_trip_cost_charges_standard_turnover_at_the_declared_bps() -> None:
    accumulator = momentum._PortfolioAccumulator(
        decision_slot_count=1,
        signal_slot_count=1,
        gross_return=Decimal("1"),
        rebalance_turnover=Decimal("1"),
        concentration_total=Decimal("1"),
    )

    aggregate = momentum._aggregate_from(accumulator)

    assert aggregate is not None
    assert aggregate.total_stress_return_bps_by_round_trip_cost["20"] == Decimal("9980")


def test_review_status_accepts_the_full_claude_verdict_set() -> None:
    assert "unsupported" in momentum._ALLOWED_REVIEW_STATUSES
    assert "uncertain" in momentum._ALLOWED_REVIEW_STATUSES
    assert "supported-with-limits" in momentum._ALLOWED_REVIEW_STATUSES


def test_input_unavailable_writes_only_a_categorical_summary(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    result = momentum.run_kis_broad_d1_cross_sectional_momentum(
        source_input=None,
        input_unavailable_reason="data_adapter_unavailable",
        artifact_root=tmp_path / "artifacts",
        run_label="no-input",
        review_status="review_unavailable",
        repo_root=repository,
    )

    payload = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.status == "input_unavailable"
    assert result.precommit_path is None
    assert payload["reason"] == "data_adapter_unavailable"
    assert payload["review_status"] == "review_unavailable"
    assert payload["selection"]["winner_selected"] is False
    _assert_no_raw_fields(payload)


def test_rejects_a_repository_artifact_root_before_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    monkeypatch.setattr(
        momentum,
        "_evaluate_cells",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not evaluate")),
    )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        momentum.run_kis_broad_d1_cross_sectional_momentum(
            source_input=_input(),
            execution_parity=_execution_parity(_input()),
            artifact_root=repository / "artifacts",
            run_label="repo-artifact",
            repo_root=repository,
        )


def test_core_has_no_data_execution_network_or_credential_route() -> None:
    source = inspect.getsource(momentum)

    assert "thericher_v2.data" not in source
    assert "thericher_v2.execution" not in source
    assert "KIS_PAPER_APP_" not in source
    assert "KIS_LIVE_" not in source
    assert ".env" not in source
    assert "import socket" not in source
    assert "import urllib" not in source


def test_runner_rejects_a_repository_artifact_root_before_loading_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_load_data_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not load")),
    )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        runner.main(
            [
                "--manifest-path",
                "ignored.json",
                "--materialization-receipt-path",
                "ignored-receipt.json",
                "--geometry-audit-receipt-path",
                "ignored-audit.json",
                "--cache-root",
                "ignored-cache",
                "--panel-root",
                "ignored-panel",
                "--artifact-root",
                str(Path(__file__).resolve().parents[1] / "artifacts"),
                "--run-label",
                "reject-root",
            ]
        )


def test_runner_turns_a_data_input_unavailable_code_into_a_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = _runner_module()
    monkeypatch.setattr(
        runner,
        "_load_data_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            momentum.KisBroadD1CrossSectionalMomentumInputUnavailable(
                "insufficient_exact_common_session_coverage"
            )
        ),
    )

    runner.main(
        [
            "--manifest-path",
            "ignored.json",
            "--materialization-receipt-path",
            "ignored-receipt.json",
            "--geometry-audit-receipt-path",
            "ignored-audit.json",
            "--cache-root",
            "ignored-cache",
            "--panel-root",
            "ignored-panel",
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--run-label",
            "adapter-unavailable",
            "--review-status",
            "review_unavailable",
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    receipt_path = (
        tmp_path
        / "artifacts"
        / "research"
        / momentum.KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_ID
        / "adapter-unavailable"
        / "summary.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert printed["status"] == "input_unavailable"
    assert receipt["reason"] == "insufficient_exact_common_session_coverage"
    assert receipt["review_status"] == "review_unavailable"


def _input() -> momentum.KisBroadD1CrossSectionalMomentumInput:
    target_keys = tuple(f"T{index:02d}/NAS" for index in range(12))
    all_bars_by_target = {
        target_key: _bars(target_index=index, event_sessions={615} if index == 0 else set())
        for index, target_key in enumerate(target_keys)
    }
    grid_bars_by_target = {
        target_key: bars[:-1] for target_key, bars in all_bars_by_target.items()
    }
    return momentum.KisBroadD1CrossSectionalMomentumInput(
        dataset_hash=_hash("a"),
        source_index_hash=_hash("b"),
        panel_manifest_sha256=_hash("c"),
        materialization_receipt_sha256=_hash("d"),
        geometry_audit_receipt_sha256=_hash("e"),
        geometry_audit_contract_sha256=_hash("f"),
        geometry_audit_source_grid_sha256=_hash("1"),
        geometry_audit_event_mask_sha256=_hash("2"),
        target_key_set_hash=momentum._target_key_set_hash(target_keys),
        full_target_count=20,
        coverage_eligible_target_count=12,
        raw_byte_attested_target_count=12,
        grid_bars_by_target=grid_bars_by_target,
        terminal_execution_bars_by_target={
            target_key: bars[-1] for target_key, bars in all_bars_by_target.items()
        },
        event_availability_by_lookback={
            lookback: {
                target_key: _event_availability(bars[:-1], lookback)
                for target_key, bars in all_bars_by_target.items()
            }
            for lookback in momentum.KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_LOOKBACKS
        },
        limitations=(
            "current_listing_only_not_point_in_time_universe",
            "non_pit_registry_scope",
            "MODP_0_unadjusted",
            "corporate_action_semantics_not_qualified",
            "session_finality_unattested",
            "alternate_daily_representation_semantics_unproven",
        ),
    )


def _bars(*, target_index: int, event_sessions: set[int]) -> tuple[Bar, ...]:
    bars: list[Bar] = []
    base = Decimal("100") + Decimal(target_index)
    slope = Decimal("0.03") + Decimal(target_index) / Decimal("1000")
    for session in range(
        momentum.KIS_BROAD_D1_CROSS_SECTIONAL_MOMENTUM_SESSION_COUNT + 1
    ):
        open_value = base + Decimal(session) * slope
        close_value = open_value * (
            Decimal("1.001") if (session + target_index) % 3 else Decimal("0.999")
        )
        high_value = max(open_value, close_value) * Decimal("1.01")
        low_value = min(open_value, close_value) * Decimal("0.99")
        if session in event_sessions:
            high_value = low_value * Decimal("3")
        bars.append(
            Bar(
                symbol=f"T{target_index:02d}",
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
        )
    return tuple(bars)


def _event_availability(bars: tuple[Bar, ...], lookback: int) -> tuple[bool, ...]:
    availability = [False] * len(bars)
    for index in range(lookback, len(bars)):
        availability[index] = momentum._completed_feature_window_is_clean(
            bars,
            decision_index=index,
            lookback=lookback,
        )
    return tuple(availability)


def _execution_parity(
    source_input: momentum.KisBroadD1CrossSectionalMomentumInput,
) -> dict[str, object]:
    return {
        "input_contract_ref": source_input.input_bar_hash,
        "source_limitations": list(source_input.limitations),
        "timing": {
            "rule": "completed_d1_t_to_next_observed_d1_open",
            "next_observed_execution_bar_attested": True,
            "semantic_representability": "represented",
            "executable_or_paper_eligibility": "not_evaluated_by_semantic_attestation",
        },
        "round_trip_stress": {
            "bps": ["5", "10", "20"],
            "status": "research_accounting_assumption_not_verified_fill_cost_or_liquidity_model",
        },
    }


def _runner_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_broad_d1_cross_sectional_momentum.py"
    )
    spec = importlib.util.spec_from_file_location("run_kis_broad_d1_cross_sectional_momentum", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("KIS broad D1 momentum runner is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("momentum benchmark must not use external access")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(os, "getenv", fail)


def _assert_no_raw_fields(value: object) -> None:
    forbidden = {
        "bar",
        "bars",
        "symbol",
        "symbols",
        "price",
        "prices",
        "open",
        "high",
        "low",
        "close",
        "weight",
        "weights",
        "prediction",
        "predictions",
    }
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key.lower() not in forbidden
            _assert_no_raw_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_raw_fields(nested)

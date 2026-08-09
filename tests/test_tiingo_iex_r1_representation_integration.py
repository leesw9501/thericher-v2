from __future__ import annotations

import json
import socket
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.data.corporate_actions import CORPORATE_ACTION_SYMBOLS
from thericher_v2.data.tiingo_iex_intraday import build_tiingo_iex_intraday_snapshot
from thericher_v2.research import tiingo_iex_r1_representation_integration as integration


def test_freeze_reattests_the_pinned_snapshot_without_external_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    fixture = _snapshot_fixture(tmp_path)
    _pin_fixture_identity(monkeypatch, fixture)

    contract = integration.freeze_tiingo_iex_r1_representation_contract(
        snapshot_dir=fixture["snapshot_dir"],
        dataset_id=fixture["dataset_id"],
        dataset_hash=fixture["dataset_hash"],
        manifest_hash=fixture["manifest_hash"],
        market_data_root=fixture["market_data_root"],
        repo_root=tmp_path / "repo",
    )

    assert contract.window_count > 0
    assert contract.gap_window_count == 0
    assert dict(contract.symbol_window_counts) == {"SPY": 40, "QQQ": 40, "IWM": 40}
    payload = contract.safe_payload()
    assert payload["source"]["source_training_eligible"] is False
    assert payload["source"]["paper_input_eligible"] is False
    assert payload["task"]["return_labels_materialized"] is False
    assert payload["task"]["holdout_materialized"] is False


def test_freeze_rejects_any_identity_other_than_the_pinned_r1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _snapshot_fixture(tmp_path)
    _pin_fixture_identity(monkeypatch, fixture)

    with pytest.raises(ValueError, match="pinned r1 identity"):
        integration.freeze_tiingo_iex_r1_representation_contract(
            snapshot_dir=fixture["snapshot_dir"],
            dataset_id="other",
            dataset_hash=fixture["dataset_hash"],
            manifest_hash=fixture["manifest_hash"],
            market_data_root=fixture["market_data_root"],
            repo_root=tmp_path / "repo",
        )


def test_run_writes_only_source_safe_external_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_external_access(monkeypatch)
    fixture = _snapshot_fixture(tmp_path)
    _pin_fixture_identity(monkeypatch, fixture)
    contract = integration.freeze_tiingo_iex_r1_representation_contract(
        snapshot_dir=fixture["snapshot_dir"],
        dataset_id=fixture["dataset_id"],
        dataset_hash=fixture["dataset_hash"],
        manifest_hash=fixture["manifest_hash"],
        market_data_root=fixture["market_data_root"],
        repo_root=tmp_path / "repo",
    )
    artifact_root = tmp_path / "model-artifacts"

    run = integration.run_tiingo_iex_r1_representation_integration(
        contract,
        phase="cpu",
        artifact_root=artifact_root,
        run_label="unit-cpu-r1",
        repo_root=tmp_path / "repo",
        matrix_runner=_completed_matrix,
    )

    assert run.summary_path.is_relative_to(artifact_root)
    payload = json.loads(run.summary_path.read_text(encoding="ascii"))
    assert payload["architecture_order"] == list(integration.TIINGO_IEX_R1_ARCHITECTURES)
    assert payload["research_steward_custody"] == {
        "allocation_kind": "source_isolated_target_free_representation",
        "family_lineage": integration.TIINGO_IEX_R1_REPRESENTATION_INTEGRATION_ID,
        "gpu_appointment": "not_requested",
        "sealed_evaluation_spent": False,
        "promotion_eligible": False,
        "completion_category": "non_promoting_runtime_evidence",
    }
    assert payload["scope"] == {
        "holdout_accessed": False,
        "kis_input_eligible": False,
        "model_selection": False,
        "normalized_arrays_persisted": False,
        "numeric_losses_persisted": False,
        "paper_input_eligible": False,
        "raw_market_data_persisted": False,
        "return_metrics_persisted": False,
        "trading_prediction": False,
        "weights_persisted": False,
    }
    rendered = run.summary_path.read_text(encoding="ascii").lower()
    assert "weight_path" not in rendered
    assert "initial_loss" not in rendered
    assert "final_loss" not in rendered
    assert "kis_paper" not in rendered


def test_run_rejects_a_git_resident_artifact_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _snapshot_fixture(tmp_path)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _pin_fixture_identity(monkeypatch, fixture)
    contract = integration.freeze_tiingo_iex_r1_representation_contract(
        snapshot_dir=fixture["snapshot_dir"],
        dataset_id=fixture["dataset_id"],
        dataset_hash=fixture["dataset_hash"],
        manifest_hash=fixture["manifest_hash"],
        market_data_root=fixture["market_data_root"],
        repo_root=repo_root,
    )

    with pytest.raises(ValueError, match="outside the Git workspace"):
        integration.run_tiingo_iex_r1_representation_integration(
            contract,
            phase="cpu",
            artifact_root=repo_root / "model-artifacts",
            run_label="invalid-root",
            repo_root=repo_root,
            matrix_runner=_completed_matrix,
        )


def _completed_matrix(
    *_args: object,
) -> tuple[integration.TiingoIexR1RepresentationArchitectureRun, ...]:
    return tuple(
        integration.TiingoIexR1RepresentationArchitectureRun(
            architecture_id=architecture_id,
            status="completed",
            training_loss_finite=True,
            memory_released=True,
        )
        for architecture_id in integration.TIINGO_IEX_R1_ARCHITECTURES
    )


def _snapshot_fixture(tmp_path: Path) -> dict[str, Path | str]:
    market_data_root = tmp_path / "market-data"
    market_data_root.mkdir()
    snapshot_dir = market_data_root / "snapshot=r1"
    result = build_tiingo_iex_intraday_snapshot(
        destination=snapshot_dir,
        raw_responses={symbol: _response(symbol) for symbol in CORPORATE_ACTION_SYMBOLS},
        requested_start=date(2017, 8, 1),
        source_as_of=date(2026, 7, 10),
        retrieved_at_utc=datetime(2026, 7, 19, tzinfo=UTC),
        market_data_root=market_data_root,
        repo_root=tmp_path / "repo",
    )
    return {
        "market_data_root": market_data_root,
        "snapshot_dir": snapshot_dir,
        "dataset_id": result.dataset_id,
        "dataset_hash": result.dataset_hash,
        "manifest_hash": result.manifest_hash,
    }


def _pin_fixture_identity(monkeypatch: pytest.MonkeyPatch, fixture: dict[str, Path | str]) -> None:
    monkeypatch.setattr(integration, "TIINGO_IEX_R1_DATASET_ID", fixture["dataset_id"])
    monkeypatch.setattr(integration, "TIINGO_IEX_R1_DATASET_HASH", fixture["dataset_hash"])
    monkeypatch.setattr(integration, "TIINGO_IEX_R1_MANIFEST_HASH", fixture["manifest_hash"])


def _response(symbol: str) -> bytes:
    sessions = _business_sessions_ending(date(2026, 7, 10), count=20)
    rows: list[dict[str, object]] = []
    symbol_offset = {"SPY": 0, "QQQ": 10, "IWM": 20}[symbol]
    for session_index, session in enumerate(sessions):
        start = datetime(session.year, session.month, session.day, 13, 30, tzinfo=UTC)
        for bar_index in range(30):
            price = 100.0 + symbol_offset + session_index + bar_index / 100.0
            rows.append(
                {
                    "date": (start + timedelta(minutes=5 * bar_index)).isoformat(),
                    "open": price,
                    "high": price + 0.2,
                    "low": price - 0.2,
                    "close": price + 0.1,
                    "volume": 1_000 + bar_index,
                }
            )
    return json.dumps(rows).encode("utf-8")


def _business_sessions_ending(last_session: date, *, count: int) -> list[date]:
    sessions: list[date] = []
    cursor = last_session
    while len(sessions) < count:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(sessions))


def _deny_external_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_external(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tiingo IEX representation integration must stay offline")

    monkeypatch.setattr(socket, "create_connection", fail_external)
    monkeypatch.setattr(urllib.request, "urlopen", fail_external)

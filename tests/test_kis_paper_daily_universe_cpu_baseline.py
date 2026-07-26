from __future__ import annotations

import inspect
import json
import os
import socket
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from thericher_v2.contracts import Bar, Timeframe
from thericher_v2.data import kis_paper_daily_universe_panel as panel_module
from thericher_v2.data.kis_paper_daily_universe_panel import (
    KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
    KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
)
from thericher_v2.data.local import _cataloged_bars_from_verified_loader
from thericher_v2.data.official_symbol_directory_nas_probe import NAS_COMMON_STOCK_PROBE_SYMBOLS
from thericher_v2.execution import LOCAL_PAPER_SOURCE
from thericher_v2.research import kis_paper_daily_universe_cpu_baseline as baseline


def test_baseline_is_offline_deterministic_local_paper_and_source_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _deny_network(monkeypatch)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    panel = _panel(tmp_path)
    _use_panel(monkeypatch, panel)
    artifact_root = tmp_path / "model-artifacts"

    first = baseline.run_kis_paper_daily_universe_cpu_baseline(
        artifact_root=artifact_root,
        run_label="cpu-a",
        repo_root=repo_root,
    )
    second = baseline.run_kis_paper_daily_universe_cpu_baseline(
        artifact_root=artifact_root,
        run_label="cpu-b",
        repo_root=repo_root,
    )

    summary = _read(first.summary_path)
    second_summary = _read(second.summary_path)
    assert (
        first.baseline_input.campaign.contract_hash == second.baseline_input.campaign.contract_hash
    )
    assert first.precommit_hash == second.precommit_hash
    assert (
        "panel"
        not in inspect.signature(baseline.run_kis_paper_daily_universe_cpu_baseline).parameters
    )
    assert _normalized_outcomes(summary) == _normalized_outcomes(second_summary)
    assert tuple(cell.symbol for cell in first.momentum_cells) == NAS_COMMON_STOCK_PROBE_SYMBOLS
    assert tuple(cell.symbol for cell in first.naive_cells) == NAS_COMMON_STOCK_PROBE_SYMBOLS
    assert all(cell.verification.fill_source == LOCAL_PAPER_SOURCE for cell in first.momentum_cells)
    assert all(cell.verification.fill_source == LOCAL_PAPER_SOURCE for cell in first.naive_cells)
    assert all(
        cell.verification.local_paper_replay_invariant_passed for cell in first.momentum_cells
    )
    assert all(cell.verification.local_paper_replay_invariant_passed for cell in first.naive_cells)
    assert all(
        cell.result.final_position == 0 for cell in (*first.momentum_cells, *first.naive_cells)
    )
    assert all(cell.result.trades for cell in (*first.momentum_cells, *first.naive_cells))
    for cell in (*first.momentum_cells, *first.naive_cells):
        bars = panel.validation_series(cell.symbol).bars
        bar_index_by_end = {bar.end_ts: index for index, bar in enumerate(bars)}
        for entry, exit_fill in zip(cell.result.trades[::2], cell.result.trades[1::2], strict=True):
            entry_signal_index = bar_index_by_end[entry.signal_bar_end]
            exit_signal_index = bar_index_by_end[exit_fill.signal_bar_end]
            assert entry.side == "buy"
            assert exit_fill.side == "sell"
            assert entry.quantity == exit_fill.quantity
            assert exit_signal_index == entry_signal_index + 1
            assert entry.filled_at == bars[entry_signal_index + 1].start_ts
            assert exit_fill.filled_at == bars[exit_signal_index + 1].start_ts
            assert exit_fill.filled_at >= entry.filled_at
    first_symbol_bars = panel.validation_series(NAS_COMMON_STOCK_PROBE_SYMBOLS[0]).bars
    assert any(
        current.start_ts.date() - prior.start_ts.date() > timedelta(days=1)
        for prior, current in zip(first_symbol_bars, first_symbol_bars[1:], strict=False)
    )

    assert summary["mode"] == "offline_cpu_local_paper"
    assert summary["source"] == {
        "adjustment_mode": KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
        "cache_manifest_sha256": "sha256:" + "a" * 64,
        "completion_rule": "observed_session_label_complete_for_offline_replay_only",
        "dataset_hash": "sha256:" + "d" * 64,
        "dataset_id": KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
        "limitations": [
            "current_listing_registry_is_not_a_historical_point_in_time_universe",
            "corporate_action_semantics_not_qualified",
            "session_labels_do_not_prove_provider_close_availability",
            "offline_local_paper_validation_only",
        ],
        "market": "US",
        "panel_evidence_sha256": "sha256:" + "b" * 64,
        "registry_sha256": "sha256:" + "c" * 64,
        "source_mixing_allowed": False,
        "symbols": list(NAS_COMMON_STOCK_PROBE_SYMBOLS),
        "timeframe": "1d",
    }
    assert summary["validation"] == {
        "all_cells_local_paper": True,
        "all_cells_replayed_flat": True,
        "tuning_allowed": False,
    }
    assert summary["reporting"]["winner"] is None
    assert summary["reporting"]["selection_allowed"] is False
    assert summary["reporting"]["ensemble_allowed"] is False
    assert summary["reporting"]["promotion_allowed"] is False
    assert summary["falsification"]["selection_allowed"] is False
    assert summary["falsification"]["promotion_allowed"] is False
    assert isinstance(summary["falsification"]["falsification_note"], str)
    assert summary["artifact_policy"] == {
        "broker_access": False,
        "credentials_read": False,
        "gpu_used": False,
        "network_access": False,
        "raw_market_data_written": False,
        "replay_event_logs_retained": False,
        "repo_storage_allowed": False,
        "source_safe_summary": True,
    }
    assert {path.name for path in first.summary_path.parent.rglob("*") if path.is_file()} == {
        "precommit.json",
        "summary.json",
    }
    summary_text = first.summary_path.read_text(encoding="utf-8")
    assert str(panel.cache_manifest_path) not in summary_text
    assert "451.123" not in summary_text
    for forbidden in ("events.jsonl", "state.sqlite", "last_price", "dataset_source_path"):
        assert forbidden not in summary_text


def test_baseline_requires_the_exact_frozen_panel_geometry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_panel(monkeypatch, _panel(tmp_path, count=198))
    with pytest.raises(ValueError, match="frozen 199-session panel"):
        baseline.build_kis_paper_daily_universe_cpu_baseline_input()


def test_baseline_reasserts_panel_attestation_for_direct_input_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_panel(monkeypatch, _panel(tmp_path))
    prepared = baseline.build_kis_paper_daily_universe_cpu_baseline_input()
    forged_panel = object.__new__(type(prepared.panel))
    for field_name in prepared.panel.__dataclass_fields__:
        object.__setattr__(forged_panel, field_name, getattr(prepared.panel, field_name))
    object.__setattr__(forged_panel, "_attestation", object())

    with pytest.raises(ValueError, match="loader attestation"):
        baseline.KisPaperDailyUniverseCpuBaselineInput(
            panel=forged_panel,
            inputs_by_symbol=prepared.inputs_by_symbol,
            split=prepared.split,
            campaign=prepared.campaign,
            spec=prepared.spec,
        )


def test_baseline_rejects_artifacts_inside_either_repository_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _use_panel(monkeypatch, _panel(tmp_path))

    with pytest.raises(ValueError, match="outside the Git workspace"):
        baseline.run_kis_paper_daily_universe_cpu_baseline(
            artifact_root=repo_root / "model-artifacts",
            run_label="bad-root",
            repo_root=repo_root,
        )

    module_repo_root = Path(baseline.__file__).resolve().parents[3]
    with pytest.raises(ValueError, match="outside the Git workspace"):
        baseline.run_kis_paper_daily_universe_cpu_baseline(
            artifact_root=module_repo_root / "unit-artifacts",
            run_label="spoofed-root",
            repo_root=tmp_path / "other-repo",
        )


@pytest.mark.parametrize("run_label", (".", "..", "../escape", "bad label", "x" * 81))
def test_baseline_rejects_unsafe_run_labels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    run_label: str,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _use_panel(monkeypatch, _panel(tmp_path))
    artifact_root = tmp_path / "model-artifacts"

    with pytest.raises(ValueError, match="run_label is invalid"):
        baseline.run_kis_paper_daily_universe_cpu_baseline(
            artifact_root=artifact_root,
            run_label=run_label,
            repo_root=repo_root,
        )

    assert not artifact_root.exists()


def test_baseline_module_has_no_credential_network_or_broker_import_path() -> None:
    source = inspect.getsource(baseline).lower()

    for forbidden in (".env", "kis_paper_app_key", "requests", "urllib", "socket", "orderintent"):
        assert forbidden not in source


def test_baseline_recovers_only_its_marked_stale_transient_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _use_panel(monkeypatch, _panel(tmp_path))
    artifact_root = tmp_path / "model-artifacts"
    transient_root = (
        artifact_root / "_transient" / baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID
    )
    stale = transient_root / f".{baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID}-stale"
    stale.mkdir(parents=True)
    (stale / "owner.json").write_text(
        json.dumps(
            {
                "baseline_id": baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
                "kind": "transient_local_paper_replay",
            }
        ),
        encoding="utf-8",
    )
    (stale / "events.jsonl").write_text("raw-replay-log", encoding="utf-8")
    active = transient_root / f".{baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID}-active"
    active.mkdir()
    (active / "owner.json").write_text(
        json.dumps(
            {
                "baseline_id": baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
                "kind": "transient_local_paper_replay",
                "process_id": os.getpid(),
            }
        ),
        encoding="utf-8",
    )

    baseline.run_kis_paper_daily_universe_cpu_baseline(
        artifact_root=artifact_root,
        run_label="stale-cleanup",
        repo_root=repo_root,
    )

    assert not stale.exists()
    assert {path.name for path in transient_root.iterdir()} == {active.name}


def test_baseline_ignores_a_symlinked_transient_owner_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _use_panel(monkeypatch, _panel(tmp_path))
    artifact_root = tmp_path / "model-artifacts"
    transient_root = (
        artifact_root / "_transient" / baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID
    )
    candidate = transient_root / f".{baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID}-symlink"
    candidate.mkdir(parents=True)
    external_marker = tmp_path / "external-owner.json"
    external_marker.write_text(
        json.dumps(
            {
                "baseline_id": baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID,
                "kind": "transient_local_paper_replay",
            }
        ),
        encoding="utf-8",
    )
    marker = candidate / "owner.json"
    try:
        marker.symlink_to(external_marker)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")

    baseline.run_kis_paper_daily_universe_cpu_baseline(
        artifact_root=artifact_root,
        run_label="symlink-owner",
        repo_root=repo_root,
    )

    assert marker.is_symlink()
    assert candidate.exists()
    assert external_marker.read_text(encoding="utf-8").startswith("{")


def test_baseline_exception_keeps_only_source_safe_incomplete_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _use_panel(monkeypatch, _panel(tmp_path))
    artifact_root = tmp_path / "model-artifacts"

    def fail_validation(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("forced validation failure")

    monkeypatch.setattr(baseline, "run_local_paper_validation", fail_validation)
    with pytest.raises(RuntimeError, match="forced validation failure"):
        baseline.run_kis_paper_daily_universe_cpu_baseline(
            artifact_root=artifact_root,
            run_label="incomplete",
            repo_root=repo_root,
        )

    output_dir = artifact_root / baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID / "incomplete"
    assert {path.name for path in output_dir.iterdir()} == {"precommit.json", "incomplete.json"}
    assert not tuple(
        (artifact_root / "_transient" / baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_ID).iterdir()
    )


def _panel(
    root: Path, *, count: int = baseline.KIS_PAPER_DAILY_UNIVERSE_CPU_BASELINE_SESSION_COUNT
):
    source_root = root / "market-data"
    start = datetime(2025, 1, 1, tzinfo=UTC)
    session_starts = _weekday_session_starts(start=start, count=count)
    sessions = tuple(timestamp.date() for timestamp in session_starts)
    dataset_hash = "sha256:" + "d" * 64
    bars_by_symbol = {}
    for symbol_index, symbol in enumerate(NAS_COMMON_STOCK_PROBE_SYMBOLS):
        bars = tuple(
            _bar(
                symbol=symbol,
                start_ts=session_starts[index],
                opened=Decimal("450") + Decimal(symbol_index) + Decimal(index),
            )
            for index in range(count)
        )
        bars_by_symbol[symbol] = _cataloged_bars_from_verified_loader(
            dataset_id=KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
            dataset_hash=dataset_hash,
            source_path=source_root / f"{symbol.lower()}.csv",
            bars=bars,
        )
    return panel_module._panel_from_verified_load(
        dataset_id=KIS_PAPER_DAILY_UNIVERSE_PANEL_ID,
        dataset_hash=dataset_hash,
        cache_manifest_path=source_root / "manifest.json",
        cache_manifest_sha256="sha256:" + "a" * 64,
        evidence_path=source_root / "evidence.json",
        evidence_sha256="sha256:" + "b" * 64,
        registry_sha256="sha256:" + "c" * 64,
        source_manifest_sha256="sha256:" + "e" * 64,
        source_file_sha256="sha256:" + "f" * 64,
        adjustment_mode=KIS_PAPER_DAILY_UNIVERSE_PANEL_ADJUSTMENT_MODE,
        common_sessions=sessions,
        bars_by_symbol=MappingProxyType(bars_by_symbol),
        alignment_excluded_rows=MappingProxyType(
            {symbol: 0 for symbol in NAS_COMMON_STOCK_PROBE_SYMBOLS}
        ),
    )


def _bar(*, symbol: str, start_ts: datetime, opened: Decimal) -> Bar:
    return Bar(
        symbol=symbol,
        market="US",
        timeframe=Timeframe.D1,
        start_ts=start_ts,
        open=opened,
        high=opened + Decimal("2"),
        low=opened - Decimal("1"),
        close=opened + Decimal("0.123"),
        volume=Decimal("1000"),
        complete=True,
    )


def _weekday_session_starts(*, start: datetime, count: int) -> tuple[datetime, ...]:
    sessions: list[datetime] = []
    current = start
    while len(sessions) < count:
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    return tuple(sessions)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_outcomes(summary: dict[str, object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for outcome in summary["outcomes"]:
        assert isinstance(outcome, dict)
        cells: dict[str, object] = {}
        for name in ("momentum", "naive_comparator"):
            cell = outcome[name]
            assert isinstance(cell, dict)
            verification = cell["replay_verification"]
            assert isinstance(verification, dict)
            cells[name] = {
                **{key: value for key, value in cell.items() if key != "replay_verification"},
                "replay_verification": {
                    key: value
                    for key, value in verification.items()
                    if key not in {"event_jsonl_sha256", "emergency_sha256"}
                },
            }
        normalized.append(
            {
                "symbol": outcome["symbol"],
                "descriptive_after_cost_pnl_delta_momentum_minus_naive": outcome[
                    "descriptive_after_cost_pnl_delta_momentum_minus_naive"
                ],
                "ranking_allowed": outcome["ranking_allowed"],
                "winner": outcome["winner"],
                **cells,
            }
        )
    return normalized


def _use_panel(monkeypatch: pytest.MonkeyPatch, panel: object) -> None:
    monkeypatch.setattr(
        baseline,
        "load_frozen_kis_paper_daily_universe_panel",
        lambda: panel,
    )


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("baseline must remain offline")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)

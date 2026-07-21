from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_market_data import KisPaperMarketDataCallCounts
from thericher_v2.execution.kis_private_daily_collector import (
    KisPaperPrivateDailyCollectionResult,
)

_OBSERVED_AT = datetime(2026, 7, 21, 18, 30, tzinfo=UTC)


def test_execute_flag_precedes_configuration_loading(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    collector = _load_script()

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("execute flag must precede configuration loading")

    monkeypatch.setattr(collector, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    collector.main([])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_terminal_control_blocks_before_configuration_loading(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    collector = _load_script()

    monkeypatch.setattr(collector, "private_daily_collector_recovery_state", lambda **_: "complete")

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("terminal collector must block before configuration loading")

    monkeypatch.setattr(collector, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    collector.main(["--execute"])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "private_daily_attempt_already_reserved",
        "recovery": "complete",
    }


def test_success_prints_only_safe_manifest_facts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    collector = _load_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    manifest_path = tmp_path / "market-data" / "manifest.json"
    result = _result()
    calls: list[str] = []

    monkeypatch.setattr(collector, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(
        collector,
        "private_daily_collector_recovery_state",
        lambda **_: "restart",
    )
    monkeypatch.setattr(
        collector,
        "private_daily_cache_would_cross_free_space_floor",
        lambda **_: False,
    )
    monkeypatch.setattr(collector, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(collector, "_client", lambda _: object())
    monkeypatch.setattr(
        collector,
        "reserve_private_daily_collector_attempt",
        lambda **_: calls.append("reserved"),
    )
    monkeypatch.setattr(
        collector,
        "mark_private_daily_collector_network_started",
        lambda **_: calls.append("network_started"),
    )
    monkeypatch.setattr(
        collector,
        "run_bounded_kis_paper_private_daily_collection",
        lambda *_args, **_: result,
    )
    monkeypatch.setattr(
        collector,
        "write_kis_paper_private_daily_cache",
        lambda **_: (manifest_path, "sha256:manifest"),
    )
    monkeypatch.setattr(
        collector,
        "mark_private_daily_collector_completed",
        lambda **_: calls.append("completed"),
    )

    collector.main(
        ["--execute"],
        clock=lambda: _OBSERVED_AT,
        code_revision=lambda _: "git:test",
    )

    output = capsys.readouterr().out
    assert json.loads(output) == {
        "manifest_hash": "sha256:manifest",
        "manifest_path": str(manifest_path),
        "row_count": 0,
        "status": "rejected",
    }
    assert calls == ["reserved", "network_started", "completed"]
    assert "cache-token" not in output
    assert "paper-key" not in output


def _result() -> KisPaperPrivateDailyCollectionResult:
    return KisPaperPrivateDailyCollectionResult(
        observed_at=_OBSERVED_AT,
        requested_anchor_date="20260717",
        code_revision="git:test",
        call_counts=KisPaperMarketDataCallCounts(1, 0, 0),
        pages=(),
        rows=(),
        dedupe_count=0,
        conflicting_duplicate_rows=0,
        inter_page_delay_seconds=(),
        status="rejected",
        reason="daily_response_rejected",
    )


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "collect_kis_paper_private_daily.py"
    spec = importlib.util.spec_from_file_location(
        "collect_kis_paper_private_daily_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

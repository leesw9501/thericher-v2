from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_historical_capacity_map import (
    KisPaperDailyCapacityMapResult,
    KisPaperMinuteCapacityMapResult,
)
from thericher_v2.execution.kis_market_data import KisPaperMarketDataCallCounts

_OBSERVED_AT = datetime(2026, 7, 21, 17, 30, tzinfo=UTC)


def test_execute_flag_precedes_configuration_loading(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capacity_map = _load_script()

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("execute flag must precede configuration loading")

    monkeypatch.setattr(capacity_map, "load_kis_paper_market_data_config", fail_if_config_is_loaded)

    capacity_map.main(["--track", "daily"])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


@pytest.mark.parametrize("track", ["daily", "minute"])
def test_track_writes_a_terminal_marker_without_printing_raw_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    track: str,
) -> None:
    capacity_map = _load_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    artifact_root = tmp_path / "artifacts"
    summary_path = artifact_root / "summary.json"
    result = _result(track)
    monkeypatch.setattr(capacity_map, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(
        capacity_map,
        "KIS_PAPER_HISTORICAL_CAPACITY_MAP_CONTROL_ROOT",
        control_root,
    )
    monkeypatch.setattr(capacity_map, "KIS_PAPER_DAILY_CAPACITY_MAP_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(capacity_map, "KIS_PAPER_MINUTE_CAPACITY_MAP_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(capacity_map, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(capacity_map, "_client_for_track", lambda *_args: object())
    monkeypatch.setattr(capacity_map, "_run_track", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        capacity_map,
        "_write_track_summary",
        lambda *_args, **_kwargs: (summary_path, "sha256:unit"),
    )

    capacity_map.main(["--track", track, "--execute"], clock=lambda: _OBSERVED_AT)

    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "observed"
    assert json.loads(output)["track"] == track
    assert "777.777" not in output
    assert "capacity-token" not in output
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "summary_written"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("terminal map must block before configuration loading")

    monkeypatch.setattr(capacity_map, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    capacity_map.main(["--track", track, "--execute"], clock=lambda: _OBSERVED_AT)
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "capacity_map_attempt_already_reserved",
        "track": track,
    }


def _result(track: str) -> KisPaperDailyCapacityMapResult | KisPaperMinuteCapacityMapResult:
    if track == "daily":
        return KisPaperDailyCapacityMapResult(
            observed_at=_OBSERVED_AT,
            call_counts=KisPaperMarketDataCallCounts(1, 0, 0),
            pages=(),
            status="observed",
        )
    return KisPaperMinuteCapacityMapResult(
        observed_at=_OBSERVED_AT,
        call_counts=KisPaperMarketDataCallCounts(1, 0, 0),
        pages=(),
        status="observed",
    )


def _load_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "map_kis_paper_historical_capacity.py"
    spec = importlib.util.spec_from_file_location(
        "map_kis_paper_historical_capacity_for_test",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

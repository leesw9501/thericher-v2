from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_historical_probe import (
    KisPaperHistoricalDailyObservation,
    KisPaperHistoricalMinuteObservation,
    KisPaperHistoricalProbeEvidence,
)
from thericher_v2.execution.kis_market_data import (
    KisPaperMarketDataCallCounts,
    KisPaperMarketDataError,
)

_OBSERVED_AT = datetime(2026, 7, 19, 9, 30, tzinfo=UTC)


def test_execute_flag_is_required_before_configuration_loading(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("execute flag must precede configuration loading")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)

    probe.main([])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_reserved_historical_objective_stops_before_configuration_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    probe.reserve_external_one_shot_attempt(
        control_root=control_root,
        repo_root=repo_root,
        objective_id=probe.KIS_PAPER_HISTORICAL_PROBE_OBJECTIVE_ID,
        observed_at=_OBSERVED_AT,
    )
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT", control_root)

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("reserved historical objective must not load configuration")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)

    probe.main(
        ["--execute"],
        clock=lambda: _OBSERVED_AT,
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "historical_attempt_already_reserved",
    }


def test_configuration_failure_does_not_reserve_or_start_a_network_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT", control_root)

    def fail_config(_: Path) -> object:
        raise KisPaperMarketDataError("config_missing")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_config)

    probe.main(["--execute"], clock=lambda: _OBSERVED_AT, dotenv_path=tmp_path / ".env")

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "config_missing",
    }
    assert not list((control_root / "reservations").glob("*.json"))
    assert not list((control_root / "ledger").glob("*.jsonl"))


def test_successful_runner_marks_external_summary_and_never_prints_raw_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    summary_path = tmp_path / "artifacts" / "summary.json"
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT", control_root)
    monkeypatch.setattr(probe, "KIS_PAPER_HISTORICAL_PROBE_ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(probe, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(probe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        probe,
        "run_bounded_kis_paper_historical_probe",
        lambda *_args, **_kwargs: _evidence(),
    )
    monkeypatch.setattr(
        probe,
        "write_kis_paper_historical_probe_summary",
        lambda **_kwargs: (summary_path, "sha256:unit"),
    )

    probe.main(["--execute"], clock=lambda: _OBSERVED_AT, dotenv_path=tmp_path / ".env")

    output = capsys.readouterr().out
    document = json.loads(output)
    assert document["status"] == "observed"
    assert "777.777" not in output
    assert "issued-token" not in output
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "summary_written"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("completed one-shot must block before configuration loading")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    probe.main(["--execute"], clock=lambda: _OBSERVED_AT, dotenv_path=tmp_path / ".env")
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "historical_attempt_already_reserved",
    }


@pytest.mark.parametrize(
    ("failure_point", "expected_reason"),
    [
        ("summary_write", "summary_write_failed"),
        ("summary_transition", "attempt_state_unresolved"),
    ],
)
def test_indeterminate_historical_lifecycle_blocks_a_following_configuration_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure_point: str,
    expected_reason: str,
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    summary_path = tmp_path / "artifacts" / "summary.json"
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_HISTORICAL_PROBE_CONTROL_ROOT", control_root)
    monkeypatch.setattr(probe, "KIS_PAPER_HISTORICAL_PROBE_ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(probe, "KisPaperMarketDataClient", lambda **_kwargs: object())
    monkeypatch.setattr(probe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        probe,
        "run_bounded_kis_paper_historical_probe",
        lambda *_args, **_kwargs: _evidence(),
    )
    if failure_point == "summary_write":
        monkeypatch.setattr(
            probe,
            "write_kis_paper_historical_probe_summary",
            lambda **_kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
        )
    else:
        monkeypatch.setattr(
            probe,
            "write_kis_paper_historical_probe_summary",
            lambda **_kwargs: (summary_path, "sha256:unit"),
        )
        monkeypatch.setattr(
            probe,
            "mark_external_one_shot_summary_written",
            lambda **_kwargs: (_ for _ in ()).throw(ValueError("transition unavailable")),
        )

    probe.main(["--execute"], clock=lambda: _OBSERVED_AT, dotenv_path=tmp_path / ".env")

    assert json.loads(capsys.readouterr().out) == {
        "status": "indeterminate",
        "reason": expected_reason,
    }

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("an indeterminate one-shot must block before configuration loading")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    probe.main(["--execute"], clock=lambda: _OBSERVED_AT, dotenv_path=tmp_path / ".env")

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "historical_attempt_already_reserved",
    }


def _evidence() -> KisPaperHistoricalProbeEvidence:
    continuation_newest = _OBSERVED_AT - timedelta(minutes=2)
    return KisPaperHistoricalProbeEvidence(
        observed_at=_OBSERVED_AT,
        requested_by_date="20260719",
        call_counts=KisPaperMarketDataCallCounts(1, 3, 3),
        daily=(
            KisPaperHistoricalDailyObservation(
                symbol="QQQ",
                first_row_count=2,
                first_newest_date="20260717",
                first_oldest_date="20260716",
                required_ohlcv_fields_present=True,
                continuation_available=True,
                continuation_requested=True,
                continuation_row_count=2,
                continuation_newest_date="20260715",
                continuation_oldest_date="20260714",
                continuation_has_older_date=True,
            ),
            KisPaperHistoricalDailyObservation(
                symbol="SPY",
                first_row_count=2,
                first_newest_date="20260717",
                first_oldest_date="20260716",
                required_ohlcv_fields_present=True,
                continuation_available=False,
                continuation_requested=False,
                continuation_row_count=None,
                continuation_newest_date=None,
                continuation_oldest_date=None,
                continuation_has_older_date=False,
            ),
        ),
        minute=(
            KisPaperHistoricalMinuteObservation(
                symbol="QQQ",
                first_row_count=2,
                first_newest_utc=_OBSERVED_AT,
                first_oldest_utc=_OBSERVED_AT - timedelta(minutes=1),
                continuation_available=True,
                continuation_requested=True,
                continuation_row_count=2,
                continuation_newest_utc=continuation_newest,
                continuation_oldest_utc=continuation_newest - timedelta(minutes=1),
                exact_overlap_count=0,
                continuation_boundary_contiguous=True,
            ),
            KisPaperHistoricalMinuteObservation(
                symbol="SPY",
                first_row_count=2,
                first_newest_utc=_OBSERVED_AT,
                first_oldest_utc=_OBSERVED_AT - timedelta(minutes=1),
                continuation_available=False,
                continuation_requested=False,
                continuation_row_count=None,
                continuation_newest_utc=None,
                continuation_oldest_utc=None,
                exact_overlap_count=0,
                continuation_boundary_contiguous=False,
            ),
        ),
    )


def _load_probe_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_historical_data.py"
    spec = importlib.util.spec_from_file_location("probe_kis_historical_for_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

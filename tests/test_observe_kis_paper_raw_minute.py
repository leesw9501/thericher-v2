from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_market_data import KisPaperMarketDataError, KisPaperMinuteCallCounts
from thericher_v2.execution.kis_raw_minute_observation import KisPaperRawMinuteObservation

_SESSION_DATE = date(2026, 7, 21)
_START = datetime(2026, 7, 21, 17, 30, 20, tzinfo=UTC)


def test_dry_run_never_loads_config_or_touches_control_or_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observe = _load_observe_script()
    artifact_root = tmp_path / "artifact"
    control_root = tmp_path / "control"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("dry-run must not read KIS configuration")

    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)

    observe.main(["--session-date", _SESSION_DATE.isoformat()])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }
    assert not artifact_root.exists()
    assert not control_root.exists()


def test_execute_requires_session_confirmation_before_config_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observe = _load_observe_script()
    control_root = tmp_path / "control"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("session confirmation must precede credential loading")

    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)

    observe.main(
        ["--execute", "--session-date", _SESSION_DATE.isoformat()],
        clock=lambda: _START,
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "regular_nasdaq_session_confirmation_required",
    }
    assert not control_root.exists()


def test_malformed_session_date_stops_before_config_or_control_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observe = _load_observe_script()
    control_root = tmp_path / "control"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("invalid session dates must not read KIS configuration")

    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)

    with pytest.raises(SystemExit):
        observe.main(
            ["--execute", "--session-date", "not-a-date"],
            dotenv_path=tmp_path / "must-not-be-read.env",
        )

    assert not control_root.exists()


def test_out_of_window_execute_does_not_load_config_or_reserve_an_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observe = _load_observe_script()
    control_root = tmp_path / "control"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("closed-session execution must not read KIS configuration")

    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)

    observe.main(
        [
            "--execute",
            "--confirm-regular-nasdaq-session",
            "--session-date",
            _SESSION_DATE.isoformat(),
        ],
        clock=lambda: _START - timedelta(hours=5),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "not_executed"
    assert document["reason"] == "regular_session_window_closed"
    assert not control_root.exists()


def test_config_preflight_failure_does_not_reserve_or_write_an_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observe = _load_observe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    artifact_root = tmp_path / "artifact"
    monkeypatch.setattr(observe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_ARTIFACT_ROOT", artifact_root)

    def fail_config(_: Path) -> object:
        raise KisPaperMarketDataError("config_missing")

    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", fail_config)
    observe.main(
        [
            "--execute",
            "--confirm-regular-nasdaq-session",
            "--session-date",
            _SESSION_DATE.isoformat(),
        ],
        clock=lambda: _START,
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "configuration_preflight_failed",
    }
    assert not list((control_root / "reservations").glob("*.json"))
    assert not artifact_root.exists()


def test_successful_fake_lifecycle_writes_sanitized_summary_and_blocks_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observe = _load_observe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    artifact_root = tmp_path / "artifact"
    monkeypatch.setattr(observe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(observe, "KisPaperMinuteClient", lambda **_kwargs: object())
    monkeypatch.setattr(observe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        observe,
        "run_bounded_kis_paper_raw_minute_observation",
        lambda *_args, **_kwargs: _evidence(),
    )

    args = [
        "--execute",
        "--confirm-regular-nasdaq-session",
        "--session-date",
        _SESSION_DATE.isoformat(),
    ]
    clock_values = iter((_START, _START + timedelta(seconds=1), _START + timedelta(seconds=2)))
    observe.main(
        args,
        clock=lambda: next(clock_values),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "observed"
    summary = Path(document["summary_path"])
    assert summary.is_relative_to(artifact_root)
    assert "raw-price-sentinel" not in summary.read_text(encoding="utf-8")
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "summary_written"
    ledger = next((control_root / "ledger").glob("*.jsonl")).read_text(encoding="utf-8")
    for forbidden in ("cursor", "token", "account", "response"):
        assert forbidden not in ledger

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("a completed one-shot must block before configuration loading")

    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    observe.main(args, clock=lambda: _START, dotenv_path=tmp_path / "must-not-be-read.env")
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "observation_attempt_already_reserved",
    }


def test_summary_write_failure_preserves_network_started_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observe = _load_observe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    monkeypatch.setattr(observe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(observe, "KIS_PAPER_RAW_MINUTE_OBSERVATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(observe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(observe, "KisPaperMinuteClient", lambda **_kwargs: object())
    monkeypatch.setattr(observe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        observe,
        "run_bounded_kis_paper_raw_minute_observation",
        lambda *_args, **_kwargs: _evidence(),
    )

    def fail_summary(**_kwargs: object) -> object:
        raise OSError("simulated artifact failure")

    monkeypatch.setattr(observe, "write_kis_paper_raw_minute_observation_summary", fail_summary)
    clock_values = iter((_START, _START + timedelta(seconds=1), _START + timedelta(seconds=2)))
    observe.main(
        [
            "--execute",
            "--confirm-regular-nasdaq-session",
            "--session-date",
            _SESSION_DATE.isoformat(),
        ],
        clock=lambda: next(clock_values),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "indeterminate",
        "reason": "summary_write_failed",
    }
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "network_started"


def _evidence() -> KisPaperRawMinuteObservation:
    return KisPaperRawMinuteObservation(
        observed_at_start=_START,
        observed_at_end=_START + timedelta(seconds=3),
        session_date=_SESSION_DATE,
        call_counts=KisPaperMinuteCallCounts(1, 2),
        first_page_row_count=120,
        continuation_page_row_count=120,
        continuation_available=True,
        continuation_requested=True,
        first_page_required_ohlcv_fields_present=True,
        continuation_page_required_ohlcv_fields_present=True,
        first_exchange_newest=_START.replace(second=0),
        first_exchange_oldest=_START.replace(second=0) - timedelta(minutes=119),
        first_korea_newest=_START.replace(second=0),
        first_korea_oldest=_START.replace(second=0) - timedelta(minutes=119),
        continuation_exchange_newest=_START.replace(second=0) - timedelta(minutes=120),
        continuation_exchange_oldest=_START.replace(second=0) - timedelta(minutes=239),
        continuation_korea_newest=_START.replace(second=0) - timedelta(minutes=120),
        continuation_korea_oldest=_START.replace(second=0) - timedelta(minutes=239),
    )


def _load_observe_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "observe_kis_paper_raw_minute.py"
    spec = importlib.util.spec_from_file_location(
        "observe_kis_paper_raw_minute_for_test", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

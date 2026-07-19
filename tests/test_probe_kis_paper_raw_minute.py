from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from thericher_v2.execution.kis_market_data import KisPaperMinuteCallCounts
from thericher_v2.execution.kis_minute_qualification import (
    KisPaperMinuteQualificationEvidence,
    KisPaperMinuteQualificationFacts,
)


def test_out_of_window_execute_does_not_load_credentials_or_create_an_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    dotenv = tmp_path / "must-not-be-read.env"
    artifact_root = tmp_path / "artifacts"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("out-of-window execution must not load credentials")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", tmp_path / "control")

    probe.main(
        ["--execute"],
        clock=lambda: datetime(2026, 7, 19, 17, 30, 20, tzinfo=UTC),
        dotenv_path=dotenv,
    )

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "not_executed"
    assert document["reason"] == "regular_session_qualification_window_closed"
    assert not artifact_root.exists()


def test_wrong_weekday_date_does_not_load_credentials_or_reserve_an_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    control_root = tmp_path / "control"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("an unverified session date must not load credentials")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)

    probe.main(
        ["--execute"],
        clock=lambda: datetime(2026, 7, 21, 17, 30, 20, tzinfo=UTC),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    document = json.loads(capsys.readouterr().out)
    assert document["reason"] == "regular_session_qualification_window_closed"
    assert not control_root.exists()


def test_execute_flag_is_required_before_any_credential_load(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("execute flag is required before credential loading")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)

    probe.main([])

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "execute_flag_required",
    }


def test_reserved_objective_stops_before_any_credential_load(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    probe.reserve_kis_paper_minute_qualification_attempt(
        control_root=control_root,
        repo_root=repo_root,
        observed_at=datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
    )
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("reserved objective must not load credentials")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)

    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=lambda: datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "qualification_attempt_already_reserved",
    }


def test_valid_window_requires_explicit_session_exception_confirmation_before_config_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", tmp_path / "control")

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("session confirmation must precede credential loading")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)

    probe.main(
        ["--execute"],
        clock=lambda: datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "session_exception_confirmation_required",
    }


def test_summary_write_failure_preserves_the_network_started_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"

    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(
        probe,
        "KIS_PAPER_MINUTE_QUALIFICATION_ARTIFACT_ROOT",
        tmp_path / "artifacts",
    )
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(probe, "KisPaperMinuteClient", lambda **_kwargs: object())
    monkeypatch.setattr(probe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        probe,
        "run_bounded_kis_paper_minute_qualification",
        lambda *_args, **_kwargs: object(),
    )

    def fail_summary_write(**_kwargs: object) -> object:
        raise OSError("simulated external artifact failure")

    monkeypatch.setattr(probe, "write_kis_paper_minute_qualification_summary", fail_summary_write)

    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=lambda: datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
        dotenv_path=tmp_path / "must-not-be-read.env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "indeterminate",
        "reason": "summary_write_failed",
    }
    markers = list((control_root / "reservations").glob("*.json"))
    assert len(markers) == 1
    assert json.loads(markers[0].read_text(encoding="utf-8"))["phase"] == "network_started"


def test_successful_runner_lifecycle_marks_summary_written_and_blocks_a_second_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    summary_path = tmp_path / "artifact" / "summary.json"
    result = _observed_result()

    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(probe, "KisPaperMinuteClient", lambda **_kwargs: object())
    monkeypatch.setattr(probe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        probe,
        "run_bounded_kis_paper_minute_qualification",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(
        probe,
        "write_kis_paper_minute_qualification_summary",
        lambda **_kwargs: (summary_path, "sha256:unit"),
    )

    def safe_clock() -> datetime:
        return datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC)

    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=safe_clock,
        dotenv_path=tmp_path / ".env",
    )

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "observed"
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "summary_written"

    def fail_if_config_is_loaded(_: Path) -> object:
        raise AssertionError("a completed one-shot must block before credential loading")

    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", fail_if_config_is_loaded)
    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=safe_clock,
        dotenv_path=tmp_path / ".env",
    )
    assert json.loads(capsys.readouterr().out) == {
        "status": "not_executed",
        "reason": "qualification_attempt_already_reserved",
    }


def test_summary_state_transition_failure_is_indeterminate_not_completion_like(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())
    monkeypatch.setattr(probe, "KisPaperMinuteClient", lambda **_kwargs: object())
    monkeypatch.setattr(probe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        probe,
        "run_bounded_kis_paper_minute_qualification",
        lambda *_args, **_kwargs: _observed_result(),
    )
    monkeypatch.setattr(
        probe,
        "write_kis_paper_minute_qualification_summary",
        lambda **_kwargs: (tmp_path / "summary.json", "sha256:unit"),
    )

    def fail_transition(**_kwargs: object) -> object:
        raise ValueError("simulated marker write failure")

    monkeypatch.setattr(
        probe,
        "mark_kis_paper_minute_qualification_summary_written",
        fail_transition,
    )

    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=lambda: datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
        dotenv_path=tmp_path / ".env",
    )

    assert json.loads(capsys.readouterr().out) == {
        "status": "indeterminate",
        "reason": "attempt_state_unresolved",
    }
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "network_started"


def test_runner_rechecks_the_window_after_reservation_before_any_client_is_created(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"
    client_created = False

    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())

    def fail_if_client_is_created(**_kwargs: object) -> object:
        nonlocal client_created
        client_created = True
        raise AssertionError("a stale window must stop before client construction")

    monkeypatch.setattr(probe, "KisPaperMinuteClient", fail_if_client_is_created)
    monkeypatch.setattr(probe, "UrllibKisPaperMarketDataTransport", lambda: object())
    monkeypatch.setattr(
        probe,
        "write_kis_paper_minute_qualification_summary",
        lambda **_kwargs: (tmp_path / "summary.json", "sha256:unit"),
    )
    clock_values = iter(
        (
            datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
            datetime(2026, 7, 20, 17, 30, 21, tzinfo=UTC),
            datetime(2026, 7, 20, 17, 31, 20, tzinfo=UTC),
        )
    )

    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=lambda: next(clock_values),
        dotenv_path=tmp_path / ".env",
    )

    assert json.loads(capsys.readouterr().out)["status"] == "rejected"
    assert client_created is False
    marker = next((control_root / "reservations").glob("*.json"))
    assert json.loads(marker.read_text(encoding="utf-8"))["phase"] == "summary_written"


def test_runner_rechecks_the_window_after_config_before_reserving_an_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = _load_probe_script()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    control_root = tmp_path / "control"

    monkeypatch.setattr(probe, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(probe, "KIS_PAPER_MINUTE_QUALIFICATION_CONTROL_ROOT", control_root)
    monkeypatch.setattr(probe, "load_kis_paper_market_data_config", lambda _: object())
    clock_values = iter(
        (
            datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC),
            datetime(2026, 7, 20, 17, 31, 20, tzinfo=UTC),
        )
    )

    probe.main(
        ["--execute", "--confirm-no-exception"],
        clock=lambda: next(clock_values),
        dotenv_path=tmp_path / ".env",
    )

    document = json.loads(capsys.readouterr().out)
    assert document["status"] == "not_executed"
    assert not list((control_root / "reservations").glob("*.json"))


def _observed_result() -> KisPaperMinuteQualificationEvidence:
    observed_at = datetime(2026, 7, 20, 17, 30, 20, tzinfo=UTC)
    return KisPaperMinuteQualificationEvidence(
        observed_at_start=observed_at,
        observed_at_end=observed_at + timedelta(seconds=1),
        exchange="NAS",
        symbol="QQQ",
        call_counts=KisPaperMinuteCallCounts(1, 2),
        first_page_row_count=120,
        continuation_page_row_count=120,
        continuation_available=True,
        continuation_requested=True,
        first_exchange_newest=observed_at,
        first_exchange_oldest=observed_at - timedelta(minutes=119),
        first_korea_newest=observed_at,
        first_korea_oldest=observed_at - timedelta(minutes=119),
        continuation_exchange_newest=observed_at - timedelta(minutes=120),
        continuation_exchange_oldest=observed_at - timedelta(minutes=239),
        continuation_korea_newest=observed_at - timedelta(minutes=120),
        continuation_korea_oldest=observed_at - timedelta(minutes=239),
        exact_overlap_count=0,
        excluded_current_or_future_row_count=1,
        newest_completed_end=observed_at,
        facts=KisPaperMinuteQualificationFacts(
            probe_window_valid=True,
            first_page_descends_one_minute=True,
            continuation_page_descends_one_minute=True,
            exchange_and_korea_map_to_same_utc=True,
            continuation_has_no_overlap=True,
            continuation_boundary_is_contiguous=True,
            conflicting_overlap_count=0,
            current_minute_row_observed=True,
            current_minute_row_excluded=True,
            completed_bars_available=True,
            completed_window_fresh=True,
            baseline_boundary_aligned=True,
        ),
    )


def _load_probe_script() -> ModuleType:
    script_path = Path(__file__).parents[1] / "scripts" / "probe_kis_paper_raw_minute.py"
    spec = importlib.util.spec_from_file_location(
        "probe_kis_paper_raw_minute_for_test", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

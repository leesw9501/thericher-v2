"""Explicit fill mode must not change the existing immediate-cancel entry point."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_paper_session as session

WRITE_OUTCOME = session._write_fill_cycle_outcome


@pytest.fixture(autouse=True)
def isolate_worker_artifacts(monkeypatch):
    monkeypatch.setattr(session, "_write_fill_cycle_outcome", lambda *args: None)


def _arguments(*extra):
    return session.build_parser().parse_args(["--fill-cycle-id", "synthetic-cycle", *extra])


@pytest.mark.parametrize(
    "arguments",
    [
        ["--fill-cycle-id", "x", "--cancel-after-submit"],
        ["--fill-cycle-visits", "2"],
        ["--fill-cycle-id", "x", "--fill-cycle-visits", "21"],
        ["--fill-cycle-id", "x", "--fill-cycle-visits", "0"],
        ["--fill-cycle-id", "x", "--session-id", "y"],
        ["--fill-cycle-id", "x", "--valid-seconds", "600"],
    ],
)
def test_invalid_mode_does_not_dispatch(monkeypatch, arguments):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid mode reached dispatch")

    monkeypatch.setattr(session, "run_kis_paper_quote_session", forbidden)
    monkeypatch.setattr(session, "_run_fill_cycle_visits", forbidden)
    with pytest.raises(SystemExit) as error:
        session.main(arguments)
    assert error.value.code == 2


def test_legacy_cli_keeps_cancel_semantics(monkeypatch, capsys):
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(safe_payload=lambda: {"status": "preview"})

    monkeypatch.setattr(session, "run_kis_paper_quote_session", run)
    assert session.main(["--execute", "--cancel-after-submit"]) == 0
    assert calls[0]["execute"] and calls[0]["cancel_after_submit"]
    assert "preview" in capsys.readouterr().out


@pytest.mark.parametrize("execute,regular", [(False, True), (True, False)])
def test_preview_and_closed_worker_never_load_config(monkeypatch, execute, regular):
    from thericher_v2.execution import kis_paper_spy_fill_cycle as cycle

    monkeypatch.setattr(session, "is_us_equity_regular_session_window", lambda now: regular)

    def forbidden(*args, **kwargs):
        pytest.fail("preview/closed worker reached credentials or sleep")

    monkeypatch.setattr(session, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(session.time, "sleep", forbidden)
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(safe_payload=lambda: {"status": "not_due"})

    monkeypatch.setattr(cycle, "run_kis_paper_spy_fill_cycle", run)
    arguments = _arguments("--fill-cycle-visits", "20", *(["--execute"] if execute else []))
    assert session._run_fill_cycle_visits(arguments)["worker_visits"] == 1
    assert calls[0]["client"] is None


@pytest.mark.parametrize("last_status", ["complete", "pending", "recovery_required"])
def test_bounded_worker_reuses_one_client(monkeypatch, last_status):
    from thericher_v2.execution import kis_paper_spy_fill_cycle as cycle

    clients = []
    calls = []
    sleeps = []
    monkeypatch.setattr(session, "is_us_equity_regular_session_window", lambda now: True)
    monkeypatch.setattr(session, "load_kis_paper_config_from_environment", lambda env: object())
    monkeypatch.setattr(session.time, "sleep", sleeps.append)
    monkeypatch.setattr(session.time, "monotonic", lambda: 0)

    def new_client(**kwargs):
        client = object()
        clients.append(client)
        return client

    def run(**kwargs):
        calls.append(kwargs)
        status = "pending" if len(calls) == 1 else last_status
        return SimpleNamespace(safe_payload=lambda: {"status": status})

    monkeypatch.setattr(session, "KisPaperCanaryClient", new_client)
    monkeypatch.setattr(cycle, "run_kis_paper_spy_fill_cycle", run)
    payload = session._run_fill_cycle_visits(_arguments("--execute", "--fill-cycle-visits", "2"))
    assert len(clients) == 1
    assert len(calls) == 2
    assert all(call["client"] is clients[0] for call in calls)
    assert sleeps == [15]
    assert payload["worker_visits"] == 2
    assert payload["worker_stop"] == ("visit_budget" if last_status == "pending" else "outcome")


def test_fill_cli_has_no_legacy_dispatch(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("fill CLI dispatched legacy quote session")

    monkeypatch.setattr(session, "run_kis_paper_quote_session", forbidden)
    monkeypatch.setattr(session, "_run_fill_cycle_visits", lambda args: {"status": "preview"})
    assert session.main(["--fill-cycle-id", "synthetic-cycle"]) == 0
    assert "preview" in capsys.readouterr().out


def test_repo_artifacts_rejected_before_credentials(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid artifact root reached credentials")

    monkeypatch.setattr(session, "load_kis_paper_config_from_environment", forbidden)
    arguments = _arguments("--execute")
    arguments.repository_root = tmp_path
    arguments.artifact_root = tmp_path / "artifacts"
    with pytest.raises(ValueError, match="outside the Git workspace"):
        session._run_fill_cycle_visits(arguments)


def test_selected_live_mode_rejected_before_paper_credentials(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("live-selected invocation read Paper credentials")

    monkeypatch.setenv("THERICHER_MODE", "kis_live")
    monkeypatch.setattr(session, "load_kis_paper_config_from_environment", forbidden)
    with pytest.raises(ValueError, match="live mode is unavailable"):
        session._run_fill_cycle_visits(_arguments("--execute"))


def test_safe_worker_status_is_persisted_without_raw_cycle_identity(tmp_path):
    arguments = _arguments()
    arguments.artifact_root = tmp_path / "artifacts"
    payload = {"status": "pending", "worker_visits": 1, "worker_stop": "observing"}
    WRITE_OUTCOME(arguments, payload)
    paths = list(
        arguments.artifact_root.glob("execution/kis-paper-spy-fill-cycle/*/worker-outcome.json")
    )
    assert len(paths) == 1
    assert json.loads(paths[0].read_text()) == payload
    assert len(payload["cycle_ref"]) == 64
    assert arguments.fill_cycle_id not in paths[0].read_text()


def test_additive_diagnostics_roundtrip_without_changing_worker_stop_or_exit(
    tmp_path, monkeypatch, capsys
):
    from thericher_v2.execution import kis_paper_spy_fill_cycle as cycle

    outcome = cycle.KisPaperSpyFillCycleOutcome(
        "recovery_required", "evidence_unavailable", datetime(2026, 9, 22, 14, 30, tzinfo=UTC),
        failure_stage=cycle._FailureStage.ACCOUNT_SNAPSHOT,
        failure_category=cycle._FailureCategory.READONLY,
    )
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return outcome

    def forbidden(*args, **kwargs):
        pytest.fail("diagnostic serialization must not load credentials or retry")

    monkeypatch.setattr(cycle, "run_kis_paper_spy_fill_cycle", run)
    monkeypatch.setattr(session, "load_kis_paper_config_from_environment", forbidden)
    monkeypatch.setattr(session.time, "sleep", forbidden)
    monkeypatch.setattr(session, "_write_fill_cycle_outcome", WRITE_OUTCOME)
    artifact_root = tmp_path / "artifacts"
    assert session.main([
        "--fill-cycle-id", "spy-fill-20260922-v1", "--fill-cycle-visits", "20",
        "--artifact-root", str(artifact_root), "--repository-root", str(tmp_path / "repo"),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert payload["worker_visits"] == 1 and payload["worker_stop"] == "outcome"
    assert payload["failure_stage"] == "account_snapshot"
    assert payload["failure_category"] == "readonly_error"
    assert payload["status"] == "recovery_required"
    assert payload["reason_code"] == "evidence_unavailable"
    expected_ref = "e6ad99be327e7ece5fb77ca234f75d9c2fbf266277cabbf0221a7d44b5204866"
    assert payload["cycle_ref"] == cycle._digest("spy-fill-20260922-v1") == expected_ref
    receipt = artifact_root / "execution" / "kis-paper-spy-fill-cycle" / expected_ref
    assert json.loads((receipt / "worker-outcome.json").read_text()) == payload

"""Budget worker exit status is operational evidence, never a fill assertion."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from thericher_v2.execution import kis_paper_daily_spy_session as session


@pytest.fixture
def offline(monkeypatch):
    state = SimpleNamespace(now=0.0, calls=[], sleeps=[])

    def sleep(seconds):
        state.sleeps.append(seconds)
        state.now += seconds

    monkeypatch.setattr(session, "time", SimpleNamespace(
        monotonic=lambda: state.now, sleep=sleep,
    ))
    monkeypatch.setattr(session, "os", SimpleNamespace(environ={"THERICHER_MODE": "off"}))
    monkeypatch.setattr(session, "load_kis_paper_config_from_environment", lambda _: object())
    monkeypatch.setattr(session, "UrllibKisPaperCanaryTransport", lambda: object())
    monkeypatch.setattr(session, "KisPaperCanaryClient", lambda **_: object())
    return state


def install_outcomes(monkeypatch, state, statuses):
    remaining = iter(statuses)

    def run(**kwargs):
        state.calls.append(kwargs)
        status = next(remaining)
        return SimpleNamespace(
            status=status,
            safe_payload=lambda: {"status": status, "paper_only": True},
        )

    monkeypatch.setattr(session, "run_kis_paper_daily_spy_session", run)


@pytest.mark.parametrize(("status", "code"), [
    ("preview", 0), ("not_due", 0), ("no_intent", 0), ("order_complete", 0),
    ("recovery_required", 20), ("pending", 21), ("unexpected", 20),
])
def test_budget_exit_distinguishes_unknown_and_unfinished(
    monkeypatch, offline, capsys, status, code,
):
    install_outcomes(monkeypatch, offline, [status])
    assert session.main(["--budget-trial", "--execute", "--budget-visits", "1"]) == code
    assert json.loads(capsys.readouterr().out)["status"] == status
    assert len(offline.calls) == 1 and offline.sleeps == []


@pytest.mark.parametrize(("statuses", "code"), [
    (["pending", "order_complete"], 0),
    (["pending", "recovery_required"], 20),
    (["pending", "pending"], 21),
])
def test_budget_last_result_controls_exit_without_extra_visit(
    monkeypatch, offline, statuses, code,
):
    install_outcomes(monkeypatch, offline, statuses)
    assert session.main(["--budget-trial", "--execute", "--budget-visits", "2"]) == code
    assert len(offline.calls) == 2 and offline.sleeps == [15]
    assert offline.calls[0]["client"] is offline.calls[1]["client"]


def test_deadline_before_any_visit_is_not_success(monkeypatch, offline):
    ticks = iter([0.0, 1200.0])
    monkeypatch.setattr(session.time, "monotonic", lambda: next(ticks))
    install_outcomes(monkeypatch, offline, [])
    assert session.main(["--budget-trial"]) == 21
    assert offline.calls == [] and offline.sleeps == []


def test_pending_visit_crossing_deadline_is_not_success(monkeypatch, offline):
    install_outcomes(monkeypatch, offline, ["pending"])
    original = session.run_kis_paper_daily_spy_session

    def run(**kwargs):
        outcome = original(**kwargs)
        offline.now = 1201.0
        return outcome

    monkeypatch.setattr(session, "run_kis_paper_daily_spy_session", run)
    assert session.main(["--budget-trial", "--budget-visits", "2"]) == 21
    assert len(offline.calls) == 1 and offline.sleeps == []


@pytest.mark.parametrize("status", ["preview", "no_intent", "canary_completed"])
def test_legacy_cli_keeps_zero_exit_and_single_visit(monkeypatch, offline, status):
    install_outcomes(monkeypatch, offline, [status])
    assert session.main(["--budget-visits", "24"]) == 0
    assert len(offline.calls) == 1 and offline.sleeps == []


def test_module_entry_propagates_main_return():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(session.__file__).read_text())
    final = tree.body[-1]
    assert isinstance(final, ast.If)
    statement = final.body[0]
    assert isinstance(statement, ast.Raise)
    assert isinstance(statement.exc, ast.Call) and statement.exc.func.id == "SystemExit"
    assert isinstance(statement.exc.args[0], ast.Call)
    assert statement.exc.args[0].func.id == "main"

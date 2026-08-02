from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def test_script_noops_before_the_same_day_cutoff_without_opening_inputs(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "run_kis_qqq_spy_mtf_prospective_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("inputs must stay unopened")),
    )

    assert script.main(["--observed-at", "2026-07-21T19:29:00Z"]) == 0

    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_qqq_spy_mtf_prospective_observation",
        "reason": "outside_eligible_observation_window",
        "status": "pending",
    }


def test_script_has_no_credential_network_account_or_order_surface() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_qqq_spy_mtf_prospective_attempt.py"
    ).read_text(encoding="utf-8").lower()

    assert ".env" not in source
    assert "kis_paper_app" not in source
    assert "kis_live" not in source
    assert "account" not in source
    assert "order" not in source
    assert "socket" not in source
    assert "urllib" not in source


def test_script_marks_an_eligible_input_failure_for_schedule_recovery(
    monkeypatch,
    capsys,
) -> None:
    script = _load_script()
    monkeypatch.setattr(
        script,
        "run_kis_qqq_spy_mtf_prospective_attempt",
        lambda **_kwargs: (_ for _ in ()).throw(script.KisQqqSpyMtfProspectiveObservationError()),
    )

    assert script.main(["--observed-at", "2026-07-21T19:30:00Z"]) == 20

    assert json.loads(capsys.readouterr().out) == {
        "kind": "kis_qqq_spy_mtf_prospective_observation",
        "reason": "verified_input_unavailable",
        "status": "unavailable",
    }


def _load_script() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_kis_qqq_spy_mtf_prospective_attempt.py"
    )
    spec = importlib.util.spec_from_file_location("run_kis_qqq_spy_mtf_prospective_attempt", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

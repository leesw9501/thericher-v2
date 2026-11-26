import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import (
    kis_paper_budget_strategy as budget,
)
from thericher_v2.execution import (
    kis_paper_canary as canary,
)
from thericher_v2.execution import (
    kis_paper_fill_accounting as accounting,
)
from thericher_v2.execution import (
    kis_paper_single_etf_leg as leg,
)
from thericher_v2.ops import h20_exact_phase_outcomes as readout


def _state(side, quantity, filled, attempted):
    return SimpleNamespace(
        intent=SimpleNamespace(side=side, quantity=quantity, symbol="SPY", exchange="INVENTED"),
        submission_started_at=object() if attempted else None,
        submit_response_category="acknowledged_order_reference" if attempted else None,
        broker_order_id="invented" if attempted else None,
        cumulative_fill=None
        if filled is None
        else SimpleNamespace(quantity=filled, identity_ref="x"),
        current_fill=None if not filled else SimpleNamespace(quantity=filled),
    )


@pytest.mark.parametrize(
    "exit_filled, terminal, expected_fill, expected_inventory",
    [
        (None, False, "NOT_RECORDED", "POSITIVE"),
        (2, False, "PARTIAL", "POSITIVE"),
        (5, True, "FULL", "FLAT"),
    ],
)
def test_exact_exit_is_separate_from_full_entry(
    exit_filled, terminal, expected_fill, expected_inventory
):
    source = [
        (_state("buy", 5, 5, True), True, "entry"),
        (_state("sell", 5, exit_filled, True), terminal, "exit"),
    ]
    result = readout._phases(source, lambda _, proof: proof)
    assert result["entry"]["fill"] == "FULL"
    assert result["exit"]["fill"] == expected_fill
    assert result["exit"]["acceptance"] == "ACKNOWLEDGED"
    assert result["exit"]["terminal"] == ("YES" if terminal else "UNKNOWN")
    assert result["current_owned_inventory"] == expected_inventory
    assert result["broker_holdings"] == "NOT_READ" and result["net_PnL"] == "UNKNOWN"
    assert result["reservation_released"] is False


@pytest.fixture
def execution(tmp_path, monkeypatch):
    if not readout._READER.is_file():
        pytest.skip("exact external H20 reader not available")
    old_load = readout._load
    flags = SimpleNamespace(admit=True, stable=True, has_exit=False)
    contract = SimpleNamespace(account_ref="invented", request_id="entry")
    entry = _state("buy", 5, 5, True)
    exit_state = _state("sell", 5, None, True)
    plans = {
        "entry": {"states": {"entry": entry}},
        "exit": {"states": {"exit": exit_state}},
    }
    (tmp_path / "entry").touch()
    reads = []

    def compiled(raw):
        code = old_load(raw)
        code["states_unlocked"] = lambda *_: {}
        return code

    def _control(path):
        reads.append(path.name)
        return path.name

    def find(_binding, phase):
        return plans[phase] if phase == "entry" or flags.has_exit else None

    monkeypatch.setattr(readout, "_load", compiled)
    monkeypatch.setattr(leg, "_control_path", lambda _root, _contract, phase: tmp_path / phase)
    monkeypatch.setattr(budget, "_read_json", _control)
    monkeypatch.setattr(budget, "_load_binding", lambda *_: {})
    monkeypatch.setattr(leg, "_find", find)
    monkeypatch.setattr(leg, "_checked_control", lambda _doc, _contract, phase: plans[phase])
    monkeypatch.setattr(leg, "_history", lambda *_: None)
    monkeypatch.setattr(
        leg,
        "_scope",
        lambda *_: (dict(entry=entry, exit=exit_state), dict(entry=True, exit=False), None),
    )
    monkeypatch.setattr(leg, "_exit_request", lambda _: "exit")
    monkeypatch.setattr(leg, "_lot_interference", lambda *_: None)
    monkeypatch.setattr(budget, "_owners", lambda _: ())
    monkeypatch.setattr(budget, "_terminal", lambda _, proof: proof)
    monkeypatch.setattr(accounting, "fill_identity_ref", lambda **_: "x")
    monkeypatch.setattr(
        canary, "KisPaperCanaryState", SimpleNamespace(from_dict=lambda state: state)
    )

    def projection():
        return readout.read_h20_phase_outcomes(
            tmp_path,
            contract,
            datetime.now(UTC),
            source_check=lambda: "frozen",
            inventory=lambda _: (),
            unchanged=lambda *_: flags.stable,
            admit=lambda: flags.admit,
        )

    return SimpleNamespace(root=tmp_path, flags=flags, reads=reads, run=projection)


def test_pinned_reader_cannot_turn_an_entry_fill_into_an_exit(execution):
    result = execution.run()
    assert result["entry"]["fill"] == "FULL"
    assert result["exit"] == readout._unknown_phase("NO_LINKED_PLAN")
    assert execution.reads == ["entry"]
    assert result["current_owned_inventory"] == "POSITIVE"


def test_exact_exit_child_can_be_acknowledged_without_fill_or_terminal(execution):
    execution.flags.has_exit = True
    (execution.root / "exit").touch()
    result = execution.run()
    assert execution.reads == ["entry", "exit"]
    assert result["exit"] == dict(
        plan="LINKED",
        attempt="RECORDED",
        acceptance="ACKNOWLEDGED",
        fill="NOT_RECORDED",
        terminal="UNKNOWN",
    )


@pytest.mark.parametrize(
    "fault, reason",
    [
        ("admit", "ADMISSION_REQUIRED"),
        ("stable", "PRIVATE_UNSTABLE"),
        ("orphan", "CONTROL_BINDING_INVALID"),
    ],
)
def test_unqualified_readout_exposes_neither_phase(execution, fault, reason):
    if fault == "orphan":
        (execution.root / "exit").touch()
    else:
        setattr(execution.flags, fault, False)
    result = execution.run()
    assert result["reason"] == reason
    assert result["exit"] == result["entry"] == readout._unknown_phase()
    if fault == "admit":
        assert not execution.reads


def test_guest_default_is_inert_and_unqualified_read_refuses():
    script = Path(__file__).resolve().parents[1] / "scripts/run_h20_phase_reader_guest.py"
    argv = [sys.executable, "-I", "-S", "-B", str(script)]
    result = subprocess.run(argv, capture_output=True, timeout=5, check=True)
    assert json.loads(result.stdout) == {"status": "INERT_SOURCE_ONLY", "actual_private_reads": 0}
    refused = subprocess.run(argv + ["--read"], capture_output=True, timeout=5, check=False)
    assert refused.returncode == 20
    assert json.loads(refused.stdout) == {"status": "UNKNOWN_PHASE_READER_NOT_ADMITTED"}


def test_guest_rejects_unlisted_import_shadows(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/run_h20_phase_reader_guest.py"
    spec = importlib.util.spec_from_file_location("fixture_h20_guest", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pkg = tmp_path / "package"
    pkg.mkdir()
    good = pkg / "pinned.py"
    good.touch()
    module._code_members([tmp_path], {str(good)})
    (pkg / "read.py").touch()
    with pytest.raises(ValueError, match="H20_PHASE_GUEST_NOT_ADMITTED"):
        module._code_members([tmp_path], {str(good)})

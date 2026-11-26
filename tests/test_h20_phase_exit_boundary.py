import json
import os
from hashlib import sha256

import pytest

from thericher_v2.execution.paper_peer_visit import bank_key, encode
from thericher_v2.ops import h20_phase_exit_boundary as exit_boundary


def test_retained_install_and_control_pins():
    if not exit_boundary._HOST.is_dir():
        pytest.skip("original H20 host source not retained on this host")
    exit_boundary._verify_static(lambda path: exit_boundary._read(path)[0])


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(exit_boundary, "_EXIT", tmp_path)
    observer = tmp_path / "observer"
    observer.mkdir()
    monkeypatch.setattr(exit_boundary, "_OBSERVER", observer)
    bank = dict(engine="npipe:////./pipe/invented", volume="invented")
    control = dict(bank=bank, gate_root=str(tmp_path / "gate"))
    monkeypatch.setattr(exit_boundary, "_verify_static", lambda _: control)
    monkeypatch.setattr(exit_boundary, "_utc_now", lambda: exit_boundary.OPENS)
    common = dict(source=exit_boundary._SOURCE, release=exit_boundary._RELEASE)
    start = dict(
        **common,
        round_id=exit_boundary._ROUND,
        phase="exit",
        pid=123,
        no_financial_claim=True,
    )
    closure = dict(
        **common,
        schema="paired-native-closure-v1",
        round_id=exit_boundary._ROUND,
        phase="exit",
        root_controller_exited=False,
        financial_outcome="UNKNOWN",
        reservation_or_budget_release=False,
        status="EXACT_NATIVE_VISITS_CLOSED",
        native_visits=0,
        native_children=0,
    )
    closed = dict(
        **common,
        schema="paired-owner-native-visits-closed-v1",
        round_id=exit_boundary._ROUND,
        native_visits_only=True,
        root_controller_exited=False,
        reservations_released=False,
        financial_outcome="UNKNOWN",
        receipts=[closure],
    )
    result = dict(
        **common,
        phase="exit",
        reservations_released=False,
        restore_obligation=False,
        status="H20_FINITE_OPERATIONAL_RETURN_NOT_FILL_PROOF",
    )
    return (start, closed, result), control


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "no_native",
        "stale",
        "phase",
        "restoration",
        "alias",
        "active",
        "unstable",
        "missing",
        "wrong_restore_pin",
        "wrong_native_owner",
        "wrong_native_path",
    ],
)
def test_boundary_requires_original_joint_receipts_and_positive_owner_closure(
    tmp_path, evidence, fault
):
    records, control = evidence
    start, closed, result = records
    visit = closed["receipts"][0]
    if fault == "no_native":
        visit.update(
            status="SOURCE_PROVEN_NO_NATIVE_STARTED",
            run=None,
            control_ref=None,
            native_visits=0,
            native_children=0,
        )
    if fault == "phase":
        visit["phase"] = "entry"
    if fault == "restoration":
        result["restore_obligation"] = True
    if fault == "alias":
        start["release"] = "a" * 64
    if fault != "no_native":
        key = bank_key(control["bank"])
        run = "b" * 32
        gate = tmp_path / "gate" / ("bank-" + key)
        gate.mkdir(parents=True)
        path = gate / ("CLOSED-" + run + ".json")
        raw = encode(
            dict(
                status="CLOSED_OPERATIONAL_ONLY",
                same_native_intent_reconciliation_required=True,
                reservation_or_budget_release=False,
                record=dict(
                    schema="paper-bank-leg-v1",
                    identity=dict(
                        source=exit_boundary._SOURCE,
                        release=exit_boundary._RELEASE,
                        group=exit_boundary._SOURCE,
                        member="stock-ingress",
                        run=run,
                        argv_sha256="c" * 64,
                        bank=key,
                    ),
                    owner=dict(
                        pid=124 if fault == "wrong_native_owner" else 123,
                        native_start="win-filetime:123",
                    ),
                    sequence=0,
                    visits=[],
                    reservation_release=False,
                ),
            )
        )
        path.write_bytes(raw)
        visit.update(
            run=run,
            control_ref=dict(
                path=str(path.with_name("foreign.json") if fault == "wrong_native_path" else path),
                sha256=sha256(raw).hexdigest(),
            ),
        )
    times = [
        exit_boundary._TRIGGER,
        exit_boundary._RESTORE,
        exit_boundary._RESTORE if fault != "stale" else exit_boundary._TRIGGER,
    ]
    for name, row, stamp in zip(exit_boundary._FILES, records, times, strict=True):
        if name == "RESULT.json" and fault == "missing":
            continue
        path = tmp_path / name
        path.write_text(json.dumps(row), encoding="ascii")
        os.utime(path, (stamp.timestamp(), stamp.timestamp()))
    closure = tmp_path / "OWN-NATIVE-CLOSURE.json"
    pin = sha256(closure.read_bytes()).hexdigest()
    restore_started = dict(
        task="thericher-kis-paper-snapshot-observer",
        closure_path=str(closure),
        closure_sha256=pin,
        Parent_attests_exact_runtime_owner_closure=True,
        independently_proven_by_helper=False,
    )
    restore_done = dict(
        status="ORIGINAL_ENABLED_RESTORED_EXACT",
        closure_ref_sha256="b" * 64 if fault == "wrong_restore_pin" else pin,
        restore_obligation=False,
        history_not_reset=True,
        financial_outcome="UNKNOWN",
        TaskRun_Kill_newTask=0,
        before=dict(enabled=False, instances=0),
        after=dict(enabled=True),
    )
    for name, row in (
        ("RESTORE-STARTED.json", restore_started),
        ("RESTORE-RESULT.json", restore_done),
    ):
        path = tmp_path / "observer" / name
        path.write_text(json.dumps(row), encoding="ascii")
        stamp = exit_boundary._RESTORE.timestamp()
        os.utime(path, (stamp, stamp))

    def owner(task, pid):
        assert (task, pid) == (exit_boundary.TASK, 123)
        if fault == "unstable":
            (tmp_path / "RESULT.json").write_text("{}", encoding="ascii")
        return fault != "active"

    kwargs = dict(owner_closed=owner)
    if fault in {None, "no_native"}:
        assert exit_boundary.prove_h20_exit_read_boundary(**kwargs) is True
    else:
        with pytest.raises((FileNotFoundError, ValueError)):
            exit_boundary.prove_h20_exit_read_boundary(**kwargs)

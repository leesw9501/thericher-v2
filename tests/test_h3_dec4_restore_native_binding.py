import os
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops import h3_dec4_restore_native_binding as native
from thericher_v2.ops import h3_dec4_restore_writer_guard as guard_api
from thericher_v2.ops.h3_dec4_observer_plan import Dec4ObserverPlan
from thericher_v2.ops.h3_dec4_pair_release import Dec4PairSource
from thericher_v2.ops.h3_dec4_restore_daemon import Dec4RestoreDaemon
from thericher_v2.ops.h3_dec4_writer_census import Dec4CensusProfile, Dec4WriterCensus

_PIN = "a" * 64
_OTHER = "b" * 64
_BANK = pv.canonical_bank("npipe:////./pipe/dockerDesktopLinuxEngine", "invented-bank")


def _write(path, row):
    raw = pv.encode(row)
    path.write_bytes(raw)
    return sha256(raw).hexdigest()


def _guard(root):
    gate = root / "gate"
    census = Dec4WriterCensus(
        Dec4CensusProfile(
            root / "claims.json",
            _PIN,
            _PIN,
            _OTHER,
            root / "docker",
            (str(root / "private"),),
            (str(gate), _BANK["volume"]),
            (_PIN,),
        )
    )
    return guard_api.Dec4RestoreWriterGuard(
        census,
        root / "read_h3_restore_retired_writers.ps1",
        _PIN,
        root / "retired.json",
        _PIN,
        gate,
        pv.bank_key(_BANK),
        _BANK["volume"],
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows phase binding")
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "root",
        "gate",
        "release",
        "launcher",
        "phase_pin",
        "legacy",
        "swapped_grant",
        "changed_bytes",
        "entry_not_ready",
    ],
)
def test_actual_factory_requires_matching_frozen_release(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(native, "_ROOT", tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    guard = _guard(tmp_path)
    obs = Dec4ObserverPlan("entry", str(tmp_path / "observer"), _PIN, _OTHER)
    daemon = Dec4RestoreDaemon(_OTHER, _PIN, tmp_path / "docker")
    row = dict(
        launcher=str(source / "scripts" / "bank.py"),
        evidence_root=str(tmp_path / "owner"),
        observer=dict(
            package_root=obs.package_root,
            bridge_sha256=_PIN,
            core_sha256=_OTHER,
            pwsh=str(native._PWSH),
            pwsh_sha256=_PIN,
        ),
        daemon=dict(
            docker_sha256=_OTHER,
            daemon_id_sha256=_PIN,
            empty_docker_config=str(daemon.empty_docker_config),
        ),
        writers=dict(
            claims_path=str(guard.census.profile.claims_path),
            claims_sha256=_PIN,
            sensitive=list(guard.census.profile.sensitive),
            protected=list(guard.census.profile.protected),
            financial_entries=[_PIN],
            monitor_image=None,
            retirement_helper=str(guard.helper),
            retirement_helper_sha256=_PIN,
            retirement_roster=str(guard.roster),
            retirement_roster_sha256=_PIN,
        ),
    )
    row["pins"] = dict(
        observer_plan_sha256=obs.sha256,
        observer_restore_daemon_sha256=daemon.sha256,
        observer_restore_writer_guard_sha256=guard.sha256,
    )
    exit_obs = Dec4ObserverPlan("exit", obs.package_root, _PIN, _OTHER)
    exit_row = deepcopy(row)
    exit_row["pins"]["observer_plan_sha256"] = exit_obs.sha256
    exit_row["evidence_root"] = str(tmp_path / "exit-owner")
    document = dict(
        files={"scripts/bank.py": _PIN},
        restore_bootstrap={"executable": "C:\\Python\\pythonw.exe"},
        restore_native={"entry": row, "exit": exit_row},
        original_owner={"bank": _BANK},
        original_gate_root=str(guard.gate_root),
        single_bank_writer_gate=dict(gate_root=str(guard.gate_root), bank_key=guard.bank_key),
    )
    if fault == "root":
        row["evidence_root"] = str(tmp_path / "source" / ".." / "owner")
    if fault == "gate":
        document["single_bank_writer_gate"]["bank_key"] = _PIN
    if fault == "launcher":
        row["launcher"] = str(source / "scripts" / "not_pinned.py")
    if fault == "phase_pin":
        exit_row["pins"]["observer_plan_sha256"] = obs.sha256
    if fault == "entry_not_ready":
        row["pins"]["observer_plan_sha256"] = exit_obs.sha256
    pin = _write(source / "SOURCE.json", document)
    grants = {
        phase: dict(phase=phase, allow_execute=True, actual_financial_admission=False)
        for phase in ("entry", "exit")
    }
    if fault == "release":
        grants["entry"]["actual_financial_admission"] = True
    if fault == "swapped_grant":
        grants["exit"]["phase"] = "entry"
    release = _write(
        tmp_path / ("RELEASE-entry.json" if fault == "legacy" else "RELEASE.json"),
        dict(
            schema="h3-dec4-protected-pair-release-v1",
            source=pin,
            phases=grants,
        ),
    )
    if fault == "changed_bytes":
        with (tmp_path / "RELEASE.json").open("ab") as stream:
            stream.write(b" ")
    if fault is not None:
        phase = "exit" if fault == "phase_pin" else "entry"
        with pytest.raises(pv.Denied, match="h3_restore_native_binding"):
            native.build_dec4_restore_binding(source, phase, pin, release)
        if fault == "entry_not_ready":
            assert native.build_dec4_restore_binding(source, "exit", pin, release).lease.plan == (
                exit_obs
            )
        return
    binding = native.build_dec4_restore_binding(source, "entry", pin, release)
    assert binding.plan.source_sha256 == pin and binding.plan.release_sha256 == release
    assert binding.lease.transport.bounded_normal_restore
    assert binding.daemon.sha256 == daemon.sha256
    closed = native.build_dec4_restore_binding(source, "exit", pin, release)
    assert closed.plan.source_sha256 == pin and closed.plan.release_sha256 == release
    assert closed.lease.plan == exit_obs and closed.plan.task_name != binding.plan.task_name
    original = SimpleNamespace(
        ROOT=source,
        check=lambda supplied: binding.source.check(supplied),
        release=lambda *_: pytest.fail("legacy launcher release reader called"),
    )
    for phase in ("entry", "exit"):
        adapter = Dec4PairSource(original, phase)
        assert adapter.release(adapter.check(pin), pin, release) == {"source": pin, **grants[phase]}


@pytest.mark.parametrize("fault", [None, "missing_legacy", "open_roster", "changed_self"])
def test_retirement_and_current_census_are_both_required(tmp_path, monkeypatch, fault):
    guard = _guard(tmp_path)
    tasks = sorted(guard_api._RETIRED)
    if fault == "missing_legacy":
        tasks.pop()
    monkeypatch.setattr(guard_api, "_windows_root", lambda: Path(tmp_path))
    monkeypatch.setattr(
        guard_api,
        "_full_member",
        lambda *_: ((1,), pv.encode({"tasks": [{"path": n} for n in tasks]})),
    )
    monkeypatch.setattr(guard_api, "_path_stamp", lambda _: (1,))
    monkeypatch.setattr(
        guard_api,
        "_run",
        lambda *_, **__: pv.encode(
            dict(
                schema="h3-restore-retired-writers-proof-v1",
                profile_sha256=_PIN,
                retired=fault != "open_roster",
            )
        ),
    )
    actor = SimpleNamespace(
        pid=os.getpid(),
        image=sys.executable,
        raw_command_sha256=_PIN,
        parsed_argv_sha256=pv.digest(list(sys.orig_argv)),
        filetime="123",
    )
    monkeypatch.setattr(guard_api, "read_windows_actor", lambda _: actor)

    def census(_self, *, own, bind_owned, **_kwargs):
        assert own is None
        return bool(
            bind_owned(
                {
                    "actors": [
                        dict(
                            pid=actor.pid,
                            argv_sha256=_OTHER if fault == "changed_self" else _PIN,
                            start_ticks=str(guard_api._EPOCH + 123),
                        )
                    ]
                }
            )
        )

    monkeypatch.setattr(Dec4WriterCensus, "evaluate", census)
    record = dict(
        schema="paper-bank-leg-v1",
        identity=dict(
            source=_PIN,
            release=_PIN,
            group=_PIN,
            member="stock-ingress",
            run="1" * 32,
            argv_sha256=_PIN,
            bank=guard.bank_key,
        ),
        owner={"pid": 1, "native_start": "win-filetime:1"},
        sequence=0,
        visits=[],
        reservation_release=False,
    )
    deadline = datetime.now(UTC) + timedelta(seconds=30)
    if fault == "missing_legacy":
        with pytest.raises(pv.Denied, match="roster_incomplete"):
            guard.retirement_ready()
        return
    assert guard.retirement_ready() is (fault != "open_roster")
    with guard.hold(record, deadline=deadline) as check:
        if fault == "changed_self":
            with pytest.raises(pv.Denied, match="self_unbound"):
                check()
        else:
            assert check() is (fault != "open_roster")

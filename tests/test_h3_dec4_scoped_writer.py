import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from thericher_v2.execution.paper_peer_visit import bank_key
from thericher_v2.ops import h3_dec4_scoped_writer as writer
from thericher_v2.ops.h3_dec4_docker_inventory import Dec4DockerInventory
from thericher_v2.ops.h3_dec4_guest_identity import CapsuleProcess, linux_argv_sha256
from thericher_v2.ops.h3_dec4_writer_census import Dec4CensusProfile, Dec4WriterCensus

_BANK = {"engine": "npipe:////./pipe/dockerdesktoplinuxengine", "volume": "invented-bank"}
_CID = "3" * 64
_ARGV = ["python", "invented-worker.py"]


@pytest.fixture
def setup(tmp_path):
    protected = (_BANK["volume"], str(tmp_path), str(tmp_path / "original-writable"))
    census = Dec4WriterCensus(
        Dec4CensusProfile(
            tmp_path / "claims",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            tmp_path / "docker-config",
            (str(tmp_path / "secret"),),
            protected,
            ("d" * 64,),
        )
    )
    guard = writer.Dec4ScopedWriterGuard(census)
    root = tmp_path / "bank"
    leg = SimpleNamespace(check=lambda: None, key=bank_key(_BANK), root=root, record={})
    ready = SimpleNamespace(
        source=dict(
            original_owner=dict(bank=_BANK),
            original_gate_root=str(tmp_path),
            retained_input_path=str(tmp_path / "retained"),
            writer_census_sha256=guard.sha256,
            capsule=dict(mounts=[dict(rw=True, source=protected[-1])]),
        ),
        plan=SimpleNamespace(
            starts_at=datetime.now(UTC) - timedelta(seconds=1),
            ends_at=datetime.now(UTC) + timedelta(seconds=30),
        ),
        owner=SimpleNamespace(prove=lambda: "exact-scheduled-proof"),
    )
    return guard, leg, ready


def test_first_class_rejects_changed_scope_before_observer(setup, monkeypatch):
    guard, leg, ready = setup
    ready.source["capsule"]["mounts"].append(dict(rw=True, source="unknown-alias"))
    monkeypatch.setattr(Dec4WriterCensus, "evaluate", lambda *a, **kw: pytest.fail("unknown scope"))
    with pytest.raises(ValueError, match="^h3_writer_guard_scope$"):
        guard.before_observer(leg, ready, "invented-watchdog")


def test_rejects_unprotected_entry_reference_parent(setup):
    guard, leg, ready = setup
    ready.source["retained_input_path"] = str(leg.root / "unprotected" / "retained")
    with pytest.raises(ValueError, match="^h3_writer_guard_scope$"):
        guard.source_ready(leg, ready)


def test_guest_scope_runs_one_fresh_decision_with_exact_own_cid_and_live_attach(setup, monkeypatch):
    guard, leg, ready = setup
    exact = []
    decisions = []
    guest = CapsuleProcess(1, 12441, linux_argv_sha256(_ARGV))
    visit = SimpleNamespace(
        cid=_CID,
        spec={"entrypoint": _ARGV[:1], "args": _ARGV[1:]},
        exact=lambda row: exact.append(row),
        inspect=lambda cid: (cid,),
    )
    ctx = SimpleNamespace(
        leg=leg,
        readiness=ready,
        watchdog_actor=lambda: "proof",
        restore_actor=lambda: "restore-proof",
        exchange_deadline=time.monotonic() + 5,
        guest_process=guest,
        daemon_inventory=Dec4DockerInventory(_CID, 20, "epoch", 1),
    )
    facts = {"actors": object()}

    def join(observed, **kwargs):
        assert observed is facts and kwargs == dict(
            owner="exact-scheduled-proof",
            bank_record={},
            watchdog="proof",
            restore="restore-proof",
            attached_visit=visit,
        )
        return frozenset({(9, "1", "exact")})

    def evaluate(_self, *, own, deadline, bind_owned, exact_scope):
        decisions.append((own, deadline))
        assert own == _CID and deadline <= ctx.exchange_deadline
        assert bind_owned(facts) == frozenset({(9, "1", "exact")})
        assert not exact_scope({"Id": "wrong"})
        assert exact_scope({"Id": own}) and exact_scope({"Id": own})
        return True

    monkeypatch.setattr(writer, "join_dec4_writer_actors", join)
    monkeypatch.setattr(Dec4WriterCensus, "evaluate", evaluate)
    assert guard.check(ctx, stage="GUEST_ADMISSION", visit=visit)
    assert exact == [(_CID,)] and len(decisions) == 1
    ctx.guest_process = CapsuleProcess(1, 12441, "0" * 64)
    with pytest.raises(ValueError, match="h3_writer_guest_unbound"):
        guard.check(ctx, stage="GUEST_ADMISSION", visit=visit)
    assert len(decisions) == 1

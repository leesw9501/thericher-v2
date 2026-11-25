import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from thericher_v2.execution import paper_peer_visit as peer
from thericher_v2.ops.h3_dec4_watchdog import supervise_host

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows Jobs")


def _run(tmp_path, script, *, seconds=5, args=()):
    return supervise_host(
        [sys._base_executable, "-I", "-c", script, *map(str, args)],
        deadline=time.monotonic() + seconds,
        cwd=tmp_path,
        env={"SystemRoot": os.environ["SystemRoot"]},
    )


def test_exact_root_exit_is_not_a_capsule_closure(tmp_path):
    result = _run(tmp_path, "raise SystemExit(17)")
    assert result.disposition == "EXITED"
    assert result.exit_code == 17
    assert result.pid != os.getpid()
    assert int(result.native_start.removeprefix("win-filetime:")) > 0


def test_expired_deadline_never_runs_payload(tmp_path):
    marker = tmp_path / "started"
    with pytest.raises(TimeoutError, match="h3_host_deadline_before_launch"):
        _run(
            tmp_path,
            "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
            seconds=-1,
            args=(marker,),
        )
    assert not marker.exists()


@pytest.mark.parametrize("root_blocks", [True, False])
def test_joins_native_descendant_even_with_blocked_or_exited_root(tmp_path, root_blocks):
    marker = tmp_path / "descendant"
    script = """
import pathlib, subprocess, sys, time
marker = pathlib.Path(sys.argv[1])
child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"])
marker.write_text(str(child.pid), encoding="ascii")
if sys.argv[2] == "True":
    time.sleep(30)
"""
    result = _run(tmp_path, script, seconds=2, args=(marker, root_blocks))
    assert int(marker.read_text(encoding="ascii")) != result.pid
    assert result.disposition == ("DEADLINE" if root_blocks else "EXITED_WITH_MEMBERS")
    assert result.exit_code == (20 if root_blocks else 0)


def test_rejects_unscoped_launch(tmp_path):
    with pytest.raises(ValueError, match="h3_host_invalid_launch"):
        supervise_host(["python.exe"], env={}, cwd=tmp_path, deadline=time.monotonic() + 5)


def test_native_abort_leaves_exact_pending_create_claim_held(tmp_path):
    bank = peer.canonical_bank("unix:///synthetic-fixture.sock", "synthetic")
    identity = dict(
        source="1" * 64,
        release="2" * 64,
        group="3" * 64,
        member="fixture",
        run=uuid4().hex,
        argv_sha256="4" * 64,
        bank=peer.bank_key(bank),
    )
    candidate = peer.BankLeg(tmp_path, bank=bank, identity=identity)
    script = """
import json, sys, time
sys.path.insert(0, sys.argv[1])
from thericher_v2.execution.paper_peer_visit import BankLeg
with BankLeg(sys.argv[2], bank=json.loads(sys.argv[3]), identity=json.loads(sys.argv[4])) as leg:
    with leg.visit("a" * 32, kind="effect") as visit:
        visit.create_attempt("5" * 64)
        time.sleep(30)
"""
    source = Path(__file__).resolve().parents[1] / "src"
    result = _run(
        tmp_path, script, seconds=2, args=(source, tmp_path, json.dumps(bank), json.dumps(identity))
    )
    assert result.disposition == "DEADLINE"
    before = candidate.active.read_bytes()
    record = json.loads(before)
    assert record["owner"] == dict(pid=result.pid, native_start=result.native_start)
    assert record["visits"][0]["create"]["resolution"] == "ATTEMPTED_UNRESOLVED"
    with pytest.raises(peer.Held, match="durable_bank_leg_held"):
        with candidate:
            pytest.fail("native Job proof reopened a durable claim")
    assert candidate.active.read_bytes() == before
    assert not list(candidate.root.glob("CLOSED-*.json"))

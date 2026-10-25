"""Operational-only synthetic receipts and real local-process/OS-lock tests.

No Docker, Scheduler, credentials, financial custody, market/model payloads or
native order APIs. Invented closure receipts are NOT actual Docker validation.
"""

import copy
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from thericher_v2.execution import paper_peer_visit as peer

BANK = peer.canonical_bank("npipe:////./pipe/dockerDesktopLinuxEngine", "synthetic-paper")
SOURCE_ROOT = str(Path(__file__).resolve().parents[1] / "src")


def identity(**changes):
    value = dict(
        source="1" * 64,
        release="2" * 64,
        group="3" * 64,
        member="GRU_EXIT",
        run=uuid4().hex,
        argv_sha256="4" * 64,
        bank=peer.bank_key(BANK),
    )
    return value | changes


def receipt(record, **changes):
    visit = record["visits"][-1]
    create = visit["create"]
    return (
        dict(
            schema="paper-bank-visit-closure-v1",
            identity=record["identity"],
            owner=record["owner"],
            visit=visit["run"],
            record_sha256=peer.digest(record),
            children=[
                {k: c[k] for k in ("token", "argv_sha256", "pid", "native_start")}
                | {"closure": "EXACT_PROCESS_AND_JOB_JOINED"}
                for c in visit["children"]
            ],
            create_resolution=create["resolution"],
            container=create["cid"],
            container_status="EXACT_CONTAINER_ABSENT_AFTER_JOIN",
            evidence_sha256="5" * 64,
        )
        | changes
    )


def leg(root, **kwargs):
    return peer.BankLeg(root, bank=BANK, identity=identity(), **kwargs)


def _popen(args, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(args, **kwargs)


def _stop(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def _wait_file(path, process):
    end = time.monotonic() + 8
    while not path.exists() and time.monotonic() < end:
        assert process.poll() is None, process.stderr.read(8192).decode()
        time.sleep(0.01)
    assert path.exists(), "bounded_synthetic_worker_timeout"


PROBE = """
def proof(record):
    v=record['visits'][-1]
    return dict(schema='paper-bank-visit-closure-v1',identity=record['identity'],
        owner=record['owner'],visit=v['run'],record_sha256=p.digest(record),children=[],
        create_resolution='NOT_ATTEMPTED',container=None,
        container_status='EXACT_CONTAINER_ABSENT_AFTER_JOIN',evidence_sha256='5'*64)
"""

WORKER = (
    """
import sys,json,time
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,sys.argv[1])
from thericher_v2.execution import paper_peer_visit as p
root=Path(sys.argv[2]);bank=json.loads(sys.argv[3]);ident=json.loads(sys.argv[4]);mode=sys.argv[5]
"""
    + PROBE
    + """
if mode=='owner':
    with p.BankLeg(root,bank=bank,identity=ident) as leg:
        for kind in ('seed','effect','postseed'):
            with leg.visit(uuid4().hex,kind=kind) as visit:
                (root/(kind+'.ready')).write_text('ready')
                end=time.monotonic()+8
                while not (root/(kind+'.go')).exists():
                    if time.monotonic()>end:raise RuntimeError('bounded_test_timeout')
                    time.sleep(.01)
                visit.close(proof)
        leg.close()
elif mode=='contender':
    debits=0
    for kind in ('seed','effect','postseed'):
        end=time.monotonic()+8
        while not (root/(kind+'.ready')).exists():
            if time.monotonic()>end:raise RuntimeError('bounded_test_timeout')
            time.sleep(.01)
        try:
            with p.BankLeg(root,bank=bank,identity=ident):debits+=1
        except p.Held:pass
        (root/(kind+'.contended')).write_text(str(debits))
    if debits:raise RuntimeError('overlapping_bank_leg')
elif mode=='die':
    with p.BankLeg(root,bank=bank,identity=ident) as leg:
        with leg.visit(uuid4().hex,kind='effect') as visit:
            visit.create_attempt('6'*64)
            (root/'owner.ready').write_text('ready')
            sys.stdin.buffer.read(1)
"""
)


def worker(root, mode, ident=None):
    return _popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            WORKER,
            SOURCE_ROOT,
            str(root),
            json.dumps(BANK),
            json.dumps(ident or identity()),
            mode,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def test_two_real_processes_exclude_whole_seed_effect_postseed_without_debit(tmp_path):
    owner = worker(tmp_path, "owner")
    contender = None
    try:
        _wait_file(tmp_path / "seed.ready", owner)
        contender = worker(tmp_path, "contender", identity(group="7" * 64, member="TimesFM_EXIT"))
        for kind in ("seed", "effect", "postseed"):
            path = tmp_path / (kind + ".contended")
            _wait_file(path, contender)
            assert path.read_text() == "0"
            (tmp_path / (kind + ".go")).touch()
        assert owner.wait(timeout=8) == 0, owner.stderr.read().decode()
        assert contender.wait(timeout=8) == 0, contender.stderr.read().decode()
        with leg(tmp_path) as next_leg:
            next_leg.close()
    finally:
        _stop(owner)
        if contender is not None:
            _stop(contender)


@pytest.mark.skipif(os.name != "nt", reason="genuine Windows termination/byte-lock test")
def test_windows_owner_termination_releases_os_lock_but_not_durable_claim(tmp_path):
    owner = worker(tmp_path, "die")
    try:
        _wait_file(tmp_path / "owner.ready", owner)
        root = tmp_path / ("bank-" + peer.bank_key(BANK))
        active = root / "ACTIVE-LEG.json"
        before = active.read_bytes()
        _stop(owner)
        with peer.Gate(root):
            pass  # Real OS lock acquired after genuine owner termination.
        with pytest.raises(peer.Held, match="durable_bank_leg_held"), leg(tmp_path):
            pytest.fail("orphan_admitted")
        assert active.read_bytes() == before
    finally:
        _stop(owner)


def test_canonical_bank_key_ignores_policy_group_and_casefolds_windows_endpoint(tmp_path):
    assert (
        peer.canonical_bank("NPIPE:////./PIPE/DOCKERDESKTOPLINUXENGINE", "synthetic-paper") == BANK
    )
    assert peer.bank_key(peer.canonical_bank("unix:///var/run/docker.sock", "bank"))
    with leg(tmp_path) as first:
        other = peer.BankLeg(
            tmp_path, bank=BANK, identity=identity(group="9" * 64, member="newHGB")
        )
        assert first.root == other.root
        with pytest.raises(peer.Held):
            with other:
                pytest.fail("same_bank_different_group_admitted")
        first.close()


def test_context_exit_and_exception_never_clear_durable_claim(tmp_path):
    with pytest.raises(ValueError), leg(tmp_path) as active:
        with active.visit(uuid4().hex, kind="seed"):
            raise ValueError("synthetic_failure")
    assert active.active.exists()
    with pytest.raises(peer.Held), leg(tmp_path):
        pytest.fail("failure_reclaimed")


def test_positive_operational_close_preserves_financial_unknown(tmp_path):
    with leg(tmp_path) as active:
        for kind in ("seed", "effect", "postseed"):
            with active.visit(uuid4().hex, kind=kind) as visit:
                if kind == "effect":
                    visit.create_attempt("6" * 64)
                    visit.create_ack("7" * 64)
                visit.close(receipt)
        active.close()
    closed = json.loads(next(active.root.glob("CLOSED-*.json")).read_bytes())
    assert closed["status"] == "CLOSED_OPERATIONAL_ONLY"
    assert closed["same_native_intent_reconciliation_required"] is True
    assert closed["reservation_or_budget_release"] is False
    assert closed["record"]["reservation_release"] is False
    assert not active.active.exists()


def test_live_child_denies_before_adapter_container_probe(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:
        child = visit.spawn([sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"])
        try:
            with pytest.raises(peer.Denied, match="child_still_live"):
                visit.close(lambda _: pytest.fail("container_probe_before_child_join"))
            assert active.active.exists()
        finally:
            _stop(child)


def test_positive_child_termination_plus_bound_job_receipt_can_close(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:
        child = visit.spawn([sys.executable, "-I", "-B", "-c", "import time; time.sleep(.2)"])
        try:
            child.wait(timeout=5)
            visit.create_attempt("6" * 64)
            visit.create_ack("7" * 64)
            visit.close(receipt)
            active.close()
        finally:
            _stop(child)


@pytest.mark.parametrize("result", [None, "raise"])
def test_post_popen_identity_probe_failure_retains_handle_and_pid(tmp_path, result):
    def probe(pid):
        if pid == os.getpid():
            return peer.process_start(pid)
        if result == "raise":
            raise peer.Denied("synthetic_probe_failure")
        return None

    with leg(tmp_path, process_probe=probe) as active:
        with active.visit(uuid4().hex, kind="effect") as visit:
            try:
                args = [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"]
                if result == "raise":
                    with pytest.raises(peer.Denied, match="synthetic_probe_failure"):
                        visit.spawn(args)
                else:
                    with pytest.raises(peer.Denied, match="child_start_unknown"):
                        visit.spawn(args)
                assert len(active.handles) == 1
                saved = json.loads(active.active.read_bytes())["visits"][-1]["children"][0]
                assert saved["pid"] == active.handles[0].pid
                assert saved["native_start"] is None
                _stop(active.handles[0])
                with pytest.raises(peer.Denied, match="spawn_gap_requires_recovery"):
                    visit.close(receipt)
            finally:
                for handle in active.handles:
                    _stop(handle)


def test_post_popen_pid_accessor_failure_still_retains_owned_handle(tmp_path):
    def failed_pid(_):
        raise peer.Denied("synthetic_pid_failure")

    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:
        try:
            with pytest.raises(peer.Denied, match="synthetic_pid_failure"):
                visit.spawn(
                    [sys.executable, "-I", "-B", "-c", "import time;time.sleep(30)"],
                    pid_of=failed_pid,
                )
            assert len(active.handles) == 1
            saved = json.loads(active.active.read_bytes())["visits"][-1]["children"][0]
            assert saved["status"] == "SPAWNING_PID_UNKNOWN"
            assert saved["pid"] is None
        finally:
            for handle in active.handles:
                _stop(handle)


def test_factory_failure_leaves_spawn_attempt_unresolved(tmp_path):
    def failed_factory(*_, **__):
        raise FileNotFoundError

    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:
        with pytest.raises(FileNotFoundError):
            visit.spawn(["invented-not-created"], factory=failed_factory)
        with pytest.raises(peer.Denied, match="spawn_gap_requires_recovery"):
            visit.close(receipt)


@pytest.mark.parametrize(
    "resolution,cid",
    [
        ("ATTEMPTED_UNRESOLVED", None),
        ("NO_CREATE_PROVEN", None),
        ("NOT_ATTEMPTED", None),
        ("DISCOVERED_EXACT_SCOPE", None),
    ],
)
def test_pending_daemon_create_no_cid_or_empty_listing_is_not_closure(tmp_path, resolution, cid):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:
        visit.create_attempt("6" * 64)
        with pytest.raises(peer.Denied, match="daemon_create_unresolved"):
            visit.close(lambda r: receipt(r, create_resolution=resolution, container=cid))
        with pytest.raises(peer.Denied, match="closure_schema"):
            visit.close(lambda r: receipt(r, listing=[]))
        assert active.active.exists()


def test_exact_source_bound_discovered_cid_can_settle_unknown_create(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:
        visit.create_attempt("6" * 64)
        visit.close(
            lambda r: receipt(r, create_resolution="DISCOVERED_EXACT_SCOPE", container="7" * 64)
        )
        active.close()


@pytest.mark.parametrize(
    "field", ["source", "release", "group", "member", "run", "argv_sha256", "bank"]
)
def test_forged_identity_receipt_refused(tmp_path, field):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:

        def forged(record):
            value = receipt(record)
            value["identity"] = dict(value["identity"], **{field: "forged"})
            return value

        with pytest.raises(peer.Denied, match="closure_identity"):
            visit.close(forged)
        assert active.active.exists()


@pytest.mark.parametrize("field", ["pid", "native_start"])
def test_forged_owner_pid_or_start_refused(tmp_path, field):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:

        def forged(record):
            value = receipt(record)
            value["owner"] = dict(value["owner"], **{field: "forged"})
            return value

        with pytest.raises(peer.Denied, match="closure_identity"):
            visit.close(forged)


@pytest.mark.parametrize("value", [True, False, {}, {"status": "CLOSED"}])
def test_model_bool_or_unbound_receipt_never_releases(tmp_path, value):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:
        with pytest.raises(peer.Denied, match="closure_schema"):
            visit.close(lambda _: value)
        with pytest.raises(peer.Denied, match="visit_not_closed"):
            active.close()


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b"{}", b"{", b"{}\n", b"[]"]
)
def test_malformed_or_noncanonical_existing_claim_refused(tmp_path, raw):
    with leg(tmp_path) as active:
        pass
    active.active.write_bytes(raw)
    with pytest.raises(peer.Denied), leg(tmp_path):
        pytest.fail("malformed_claim_admitted")


@pytest.mark.parametrize("change", ["bytes", "mtime", "identity", "memory"])
def test_claim_bytes_mtime_identity_and_memory_guards(tmp_path, change):
    with leg(tmp_path) as active:
        before = active.active.read_bytes()
        if change == "bytes":
            active.active.write_bytes(before.replace(b"GRU_EXIT", b"NEW_EXIT"))
        elif change == "mtime":
            s = active.active.stat()
            os.utime(active.active, ns=(s.st_atime_ns, s.st_mtime_ns + 10_000_000))
        elif change == "identity":
            active.active.rename(active.root / "original.json")
            active.active.write_bytes(before)
        else:
            active.record["owner"]["pid"] += 1
        with pytest.raises(peer.Denied, match="claim_changed|claim_memory_changed"):
            active.check()


@pytest.mark.parametrize("target", ["ACTIVE-LEG.json", "HOST-VISIT.lock"])
def test_hardlinked_claim_or_gate_refused(tmp_path, target):
    with leg(tmp_path) as active:
        pass
    original = active.root / target
    alias = tmp_path / "additional-hardlink"
    before = original.lstat()
    before_bytes = original.read_bytes()
    assert before.st_nlink == 1
    os.link(original, alias)
    try:
        with pytest.raises(peer.Denied, match="path_type_or_hardlink"), leg(tmp_path):
            pytest.fail("hardlink_admitted")
    finally:
        for path in (original, alias):
            path.relative_to(tmp_path)
            peer.ordinary(path.parent)
            current = path.lstat()
            assert stat.S_ISREG(current.st_mode)
            assert not getattr(current, "st_file_attributes", 0) & 1024
            assert (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino)
            assert current.st_nlink == 2
        alias.unlink()
        assert not os.path.lexists(alias)
        after = original.lstat()
        assert (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size) == (
            before.st_dev,
            before.st_ino,
            before.st_mtime_ns,
            before.st_size,
        )
        assert after.st_nlink == 1 and original.read_bytes() == before_bytes


def test_real_symlink_root_refused_when_os_allows_creation(tmp_path):
    actual = tmp_path / "real"
    actual.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not authorize symlink creation")
    try:
        with pytest.raises(peer.Denied, match="path_reparse"), leg(link):
            pytest.fail("symlink_admitted")
    finally:
        assert link.is_symlink() and link.resolve(strict=True) == actual.resolve(strict=True)
        link.unlink()
        assert not os.path.lexists(link) and actual.is_dir()


@pytest.mark.skipif(os.name != "nt", reason="real Windows directory junction")
def test_real_windows_junction_root_refused(tmp_path, monkeypatch):
    actual = tmp_path / "real"
    actual.mkdir()
    target_identity = (actual.stat().st_dev, actual.stat().st_ino)
    junction = tmp_path / "junction"
    monkeypatch.delenv("COMSPEC", raising=False)
    # cmd parses a forward-slash argv[0] incorrectly when COMSPEC is absent.
    command = str(Path("C:/Windows/System32/cmd.exe"))
    try:
        result = subprocess.run(
            [
                command,
                "/d",
                "/c",
                "mklink",
                "/J",
                str(junction),
                str(actual),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )
        assert result.returncode == 0
        assert junction.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
        with pytest.raises(peer.Denied, match="path_reparse"), leg(junction):
            pytest.fail("junction_admitted")
    finally:
        if os.path.lexists(junction):
            peer.ordinary(junction.parent)
            assert junction.lstat().st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
            assert junction.resolve(strict=True) == actual.resolve(strict=True)
            assert (actual.stat().st_dev, actual.stat().st_ino) == target_identity
            junction.rmdir()  # Remove the verified link only, never recurse into its target.
        assert not os.path.lexists(junction)
        assert (actual.stat().st_dev, actual.stat().st_ino) == target_identity


def test_reparse_attribute_rejected_without_following(monkeypatch, tmp_path):
    original = Path.lstat

    class Reparse:
        st_mode = stat_mode = 0o040755
        st_file_attributes = 1024

    monkeypatch.setattr(Path, "lstat", lambda p: Reparse() if p == tmp_path else original(p))
    with pytest.raises(peer.Denied, match="path_reparse"):
        peer.ordinary(tmp_path)


def test_stale_or_changed_claim_during_probe_cannot_close(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:

        def changed(record):
            value = receipt(record)
            active.active.write_bytes(active.active.read_bytes() + b" ")
            return value

        with pytest.raises(peer.Denied, match="claim_changed"):
            visit.close(changed)


def test_constructor_rejects_mismatched_bank_and_extra_identity_fields(tmp_path):
    with pytest.raises(peer.Denied, match="leg_identity"):
        peer.BankLeg(tmp_path, bank=BANK, identity=identity(bank="9" * 64))
    with pytest.raises(peer.Denied, match="leg_identity"):
        peer.BankLeg(tmp_path, bank=BANK, identity=identity(arbitrary_allow=True))


def test_changed_child_argv_start_or_pid_in_closure_receipt_refused(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:
        child = visit.spawn([sys.executable, "-I", "-B", "-c", "import time;time.sleep(.2)"])
        try:
            child.wait(timeout=5)
            for field in ("argv_sha256", "native_start", "pid"):

                def forged(record, field=field):
                    value = receipt(record)
                    value["children"] = copy.deepcopy(value["children"])
                    value["children"][0][field] = "forged"
                    return value

                with pytest.raises(peer.Denied, match="child_closure_unbound"):
                    visit.close(forged)
            with pytest.raises(peer.Denied, match="child_closure_unbound"):

                def float_pid(record):
                    value = receipt(record)
                    value["children"][0]["pid"] = float(value["children"][0]["pid"])
                    return value

                visit.close(float_pid)
        finally:
            _stop(child)


def test_numerically_equal_but_wrong_owner_type_refused(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="seed") as visit:

        def float_owner(record):
            value = receipt(record)
            value["owner"] = dict(value["owner"], pid=float(value["owner"]["pid"]))
            return value

        with pytest.raises(peer.Denied, match="closure_identity"):
            visit.close(float_owner)


def test_reentering_owned_gate_does_not_lose_original_handle(tmp_path):
    with peer.Gate(tmp_path / "control") as gate:
        handle = gate.file
        with pytest.raises(peer.Denied, match="gate_already_owned"):
            gate.__enter__()
        assert gate.file is handle
        gate.check()


def test_reentrant_adapter_probe_cannot_erase_new_lifecycle_state(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:

        def changed(record):
            visit.create_attempt("6" * 64)
            return receipt(record)

        with pytest.raises(peer.Denied, match="claim_changed_during_probe"):
            visit.close(changed)
        saved = json.loads(active.active.read_bytes())
        assert saved["visits"][-1]["create"]["resolution"] == "ATTEMPTED_UNRESOLVED"


def test_stale_transition_cannot_overwrite_later_marker(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:
        stale = copy.deepcopy(active.record)
        visit.create_attempt("6" * 64)
        with pytest.raises(peer.Denied, match="claim_stale_transition"):
            active._save(stale)


def test_closed_leg_run_cannot_be_reused_for_another_effect(tmp_path):
    ident = identity()
    with peer.BankLeg(tmp_path, bank=BANK, identity=ident) as active:
        active.close()
    with pytest.raises(peer.Denied, match="leg_run_already_closed"):
        with peer.BankLeg(tmp_path, bank=BANK, identity=ident):
            pytest.fail("closed_run_reused")


def test_semantically_malformed_closed_pending_create_record_refused(tmp_path):
    with leg(tmp_path) as active, active.visit(uuid4().hex, kind="effect") as visit:
        visit.create_attempt("6" * 64)
    value = json.loads(active.active.read_bytes())
    value["visits"][-1].update(status="CLOSED", closure="8" * 64)
    active.active.write_bytes(peer.encode(value))
    with pytest.raises(peer.Denied, match="record_closure"), leg(tmp_path):
        pytest.fail("closed_pending_create_admitted")

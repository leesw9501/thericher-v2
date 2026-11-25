"""The pinned class and tracked exchange share one synthetic durable visit."""

import io
import json
import os
import subprocess
import time
from threading import Event
from types import SimpleNamespace

import pytest

from test_h3_dec4_capsule import _outcome, _parse
from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops import h3_dec4_host_exchange
from thericher_v2.ops.h3_dec4_capsule_adapter import (
    _CONTROLLER,
    _compile_visit,
    _load_visit,
    _run_visit,
)
from thericher_v2.ops.h3_dec4_guest_identity import ANSWER, CHALLENGE, REQUEST, linux_argv_sha256
from thericher_v2.ops.h3_dec4_job_closure import read_dec4_normal_job_close

_BANK = dict(engine="npipe:////./pipe/dockerdesktoplinuxengine", volume="synthetic")
_CID = "c" * 64
_SPEC = dict(
    kind="effect",
    phase="entry",
    image="fixture",
    network="none",
    mounts=[],
    entrypoint=["python"],
    args=["fixture.py", "--execute"],
)
_NONCE = "8" * 64
_ARGV = linux_argv_sha256([*_SPEC["entrypoint"], *_SPEC["args"]])


def _request(sequence):
    return (
        json.dumps(
            dict(
                kind=REQUEST,
                sequence=sequence,
                challenge=_NONCE,
                process=dict(namespace_pid=1, start_ticks=101, argv_sha256=_ARGV),
            )
        ).encode()
        + b"\n"
    )


@pytest.fixture(scope="module")
def frozen_daemon():
    path = _CONTROLLER / "daemon.py"
    if not path.is_file():
        pytest.skip("external R8 daemon source not available")
    return path.read_bytes()


def test_loads_pinned_code_without_legacy_transport(frozen_daemon, tmp_path):
    visit = _load_visit()
    assert visit.__name__ == "CapsuleVisit"
    assert "transport" not in visit.execute.__globals__
    assert "transport" not in visit.execute.__code__.co_names
    assert "telemetry" not in visit.__init__.__code__.co_names
    with pytest.raises(ValueError, match="^h3_capsule_r8_source_mismatch$"):
        _compile_visit(frozen_daemon + b"\n", tmp_path, None, None)


@pytest.mark.parametrize(
    "case",
    [
        "ok",
        "retained",
        "unknown_create",
        "timeout",
        "remove",
        "owner_denied",
        "guard",
        "guest_guard_denied",
        "guest_guard_identity_changed",
        "guest_guard_deadline",
    ],
)
def test_exact_exchange_and_r8_closure(frozen_daemon, tmp_path, monkeypatch, case):
    monkeypatch.setattr(h3_dec4_host_exchange, "token_hex", lambda _: _NONCE)
    _, guest = _parse()
    terminal = _outcome(guest)
    source = guest.cohort.source_ref.removeprefix("sha256:")
    key = pv.bank_key(_BANK)
    identity = dict(
        source=source,
        release="e" * 64,
        group=source,
        member="synthetic",
        run="1" * 32,
        argv_sha256="d" * 64,
        bank=key,
    )
    log, jobs = [], []
    present = running = False
    release_read = Event()

    def live_probe(pid):
        # Fast CLI roots are not visible by the time Visit.spawn probes them.
        return "win-filetime:1" if pid == os.getpid() else None

    class Job:
        def __init__(self, argv, *, created, **opts):
            nonlocal present, running
            self.command, *self.args = argv[3:]
            self.pid = os.getpid() + len(jobs) + 1
            self.native_start = f"win-filetime:{self.pid}"
            self.joined, self.job, self.returncode = False, object(), 0
            jobs.append(self)
            log.append(self.command)
            created(self)
            if self.command == "create":
                present = True
                self.labels = dict(a.split("=", 1) for a in self.args if a.startswith("thericher."))
                self.name = self.args[self.args.index("--name") + 1]
            elif self.command == "start":
                assert self.args == ["--attach", "--interactive", _CID]
                assert opts["stderr"] == subprocess.DEVNULL
                assert opts["creationflags"] == getattr(subprocess, "DETACHED_PROCESS", 0)
                assert leg.record["visits"][0]["create"]["cid"] == _CID
                assert leg.record["visits"][0]["create"]["resolution"] == "ACK_EXACT_CID"
                running = True
                self.stdin = io.BytesIO()
                self.stdout = io.BytesIO(_request(1) + _request(2) + terminal)
                if case == "timeout":
                    self.stdout = SimpleNamespace(readline=self.blocked_read)

        def blocked_read(self, _limit):
            release_read.wait(4)  # Fixture fails boundedly even if abort regresses.
            return b""

        def communicate(self, *, timeout):
            nonlocal present, running
            assert timeout > 0
            if self.command == "create":
                if case == "unknown_create":
                    self.returncode = 1
                    return b"", b""
                return _CID.encode(), b""
            if self.command == "ps":
                if len(self.args) > 4:
                    assert case == "unknown_create"
                    assert all("label=thericher.single_owner." in a for a in self.args[3::2])
                return (_CID.encode() if present else b""), b""
            if self.command == "inspect":
                assert self.args == [_CID]
                created_job = jobs[0]
                return json.dumps(
                    [
                        dict(
                            Image="fixture",
                            Name="/" + created_job.name,
                            Mounts=[],
                            Config=dict(
                                Labels=created_job.labels, Entrypoint=["python"], Cmd=_SPEC["args"]
                            ),
                            HostConfig=dict(
                                NetworkMode="none",
                                ReadonlyRootfs=True,
                                Privileged=False,
                                CapDrop=["ALL"],
                                Memory=1073741824,
                                NanoCpus=1000000000,
                                PidsLimit=64,
                                SecurityOpt=["no-new-privileges"],
                                LogConfig={"Type": "none"},
                            ),
                            State=dict(Running=running),
                        )
                    ]
                ).encode(), b""
            assert self.command in {"stop", "rm"} and self.args[-1] == _CID
            assert all(job.joined for job in jobs if job.command == "start")
            running = False
            if self.command == "rm":
                if case == "remove":
                    self.returncode = 1
                else:
                    present = False
            return b"", b""

        def poll(self):
            return self.returncode

        def wait(self, *, timeout):
            assert timeout > 0
            if self.command == "start" and "kill_job" not in log:
                assert self.stdin.closed  # Exact exchange consumed the terminal and EOF.
            return self.returncode

        def active(self):
            return int(self.command == "start" and case == "timeout" and not release_read.is_set())

        def kill(self):
            assert self.command == "start"
            log.append("kill_job")
            release_read.set()

        def join_job(self, timeout=5):
            assert timeout > 0 and self.active() == 0
            self.joined = True

        def close_job(self):
            assert self.joined
            self.job = None

    def admit():
        log.append("admit")
        return not (case == "owner_denied" and "start" in log)

    def read_retained():
        log.append("retained")
        return terminal + (b"different" if case == "retained" else b"")

    def writer_check(ctx, *, stage, visit):
        assert visit.context is ctx
        log.append(stage)
        if stage == "GUEST_ADMISSION":
            assert ctx.guest_process.start_ticks == 101 and ctx.guest_process.argv_sha256 == _ARGV
            attach = next(job for job in visit.jobs if job.command == "start")
            assert attach.command == "start" and visit.cid == _CID
            assert leg.record["visits"][0]["children"][-1]["pid"] == attach.pid
            if case == "ok":
                visit.exact(visit.inspect(_CID))
                assert visit.jobs[-1].command == "inspect" and visit.jobs[-1].joined
            if log.count(stage) == 2:
                if case == "guest_guard_denied":
                    return False
                if case == "guest_guard_identity_changed":
                    attach.native_start = "win-filetime:1"
                if case == "guest_guard_deadline":
                    deadlines[0] = 0
        return not (case == "guard" and stage == "AFTER_CREATE")

    clock = time.monotonic
    deadlines = [1]
    errors = {
        "retained": (ValueError, "h3_capsule_outcome_unconfirmed"),
        "unknown_create": (pv.Held, "daemon_create_ack_unknown"),
        "timeout": (ValueError, "h3_host_exchange_deadline"),
        "remove": (pv.Held, "daemon_remove_unknown"),
        "owner_denied": (ValueError, "h3_host_exchange_owner_denied"),
        "guard": (pv.Held, "h3_capsule_visit_writer_denied"),
        "guest_guard_denied": (ValueError, "h3_host_exchange_owner_denied"),
        "guest_guard_identity_changed": (ValueError, "h3_host_exchange_owner_denied"),
        "guest_guard_deadline": (ValueError, "h3_host_exchange_owner_denied"),
    }
    visit_type = _compile_visit(frozen_daemon, tmp_path, Job, None)
    with pv.BankLeg(tmp_path, bank=_BANK, identity=identity, process_probe=live_probe) as leg:
        ctx = SimpleNamespace(
            leg=leg,
            bank=_BANK,
            source_pin=source,
            created_starts={},
            admission=admit,
            writer_guard=SimpleNamespace(check=writer_check),
        )

        def invoke():
            deadline = clock() + (1.5 if case == "timeout" else 5)

            def load():
                log.append("packet")
                assert log.count("GUEST_ADMISSION") == 1
                return b'{"invented":true}'

            return _run_visit(
                visit_type,
                ctx,
                _SPEC,
                guest,
                load,
                read_retained,
                deadline,
                _clock=lambda: clock() if deadlines[0] else deadline,
            )

        if case == "ok":
            assert invoke() == dict(
                pending=False,
                native_status="no_intent",
                financial_claim="UNKNOWN",
                reservation_release=False,
            )
        else:
            error, reason = errors[case]
            with pytest.raises(error, match=f"^{reason}$"):
                invoke()

        assert leg.process_probe is live_probe and ctx.created_starts == {}
        (visit,) = leg.record["visits"]
        receipt = leg.root / ("JOB-CLOSED-" + identity["run"] + ".json")
        assert receipt.is_file() is (case == "ok")
        if case == "ok":
            snapshot = read_dec4_normal_job_close(leg.root, leg.record)
            assert pv._read(receipt) == snapshot
            changed = pv._decode(snapshot[0])
            changed["receipt"]["children"][0]["native_start"] = "win-filetime:1"
            receipt.write_bytes(pv.encode(changed))
            with pytest.raises(pv.Denied, match="^h3_normal_job_receipt_unbound$"):
                read_dec4_normal_job_close(leg.root, leg.record)
        assert visit["create"]["resolution"] == (
            "DISCOVERED_EXACT_SCOPE" if case == "unknown_create" else "ACK_EXACT_CID"
        )
        assert log.count("create") == 1
        assert log.count("start") == (0 if case in {"unknown_create", "guard"} else 1)
        assert log.index("BEFORE_CREDENTIALS") < log.index("BEFORE_CREATE") < log.index("create")
        assert all(job.joined and job.job is None for job in jobs)
        if case == "remove":
            assert present and visit["status"] == "ACTIVE"
            with pytest.raises(pv.Denied, match="^visit_not_closed$"):
                leg.close()
        else:
            assert not present and visit["status"] == "CLOSED"
            assert all(child["status"] == "JOINED" for child in visit["children"])
            if case in {"timeout", "owner_denied"}:
                assert log.index("start") < log.index("kill_job") < log.index("stop")
                assert "retained" not in log
                attach = next(job for job in jobs if job.command == "start")
                assert json.loads(attach.stdin.getvalue()) == dict(kind=CHALLENGE, challenge=_NONCE)
                assert "packet" not in log
            elif case.startswith("guest_guard_"):
                attach = next(job for job in jobs if job.command == "start")
                rows = [json.loads(row) for row in attach.stdin.getvalue().splitlines()]
                assert rows == [
                    dict(kind=CHALLENGE, challenge=_NONCE),
                    dict(kind=ANSWER, challenge=_NONCE, sequence=1, ready=True),
                    {"invented": True},
                ]
                assert log.count("GUEST_ADMISSION") == 2
                assert log.count("packet") == 1
                assert log.index("start") < log.index("kill_job") < log.index("stop")
                assert "retained" not in log
            elif case not in {"unknown_create", "guard"}:
                assert log.index("start") < log.index("retained") < log.index("stop")
                assert "admit" in log[log.index("start") : log.index("retained")]
                assert log.count("GUEST_ADMISSION") == 2
            with pytest.raises(ValueError, match="^h3_capsule_visit_already_started$"):
                invoke()
            leg.close()

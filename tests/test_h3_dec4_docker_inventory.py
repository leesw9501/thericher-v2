import json
import subprocess
import sys
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest

from thericher_v2.execution.paper_peer_visit import digest
from thericher_v2.ops import h3_dec4_docker_inventory as inventory

CID = "b" * 64
RUN = "a" * 32
IMAGE = "sha256:" + "1" * 64
SOURCE = "2" * 64
EPOCH = "2026-12-04T14:31:31.012345679Z"
PID = 32768
TOP = b"PID\n32768\n"


@pytest.fixture
def visit():
    spec = {"kind": "effect", "image": IMAGE, "args": ["invented"]}
    ack = {"resolution": "ACK_EXACT_CID", "cid": CID, "spec_sha256": digest(spec)}
    leg = SimpleNamespace(
        record={
            "schema": "paper-bank-leg-v1",
            "identity": {"source": SOURCE},
            "visits": [{"run": RUN, "kind": "effect", "status": "ACTIVE", "create": ack}],
        },
        check=lambda: None,
    )
    return SimpleNamespace(cid=CID, run=RUN, spec=spec, context=SimpleNamespace(leg=leg))


@pytest.fixture
def inspected():
    return {
        "id": CID,
        "name": "/thericher-single-owner-" + RUN,
        "image": IMAGE,
        "visit": RUN,
        "source": SOURCE,
        "pid_mode": "",
        "init": None,
        "restart_policy": {"Name": "no", "MaximumRetryCount": 0},
        "restart_count": 0,
        "tty": False,
        "open_stdin": True,
        "stdin_once": True,
        "log_driver": "none",
        "state": {
            "Status": "running",
            "Running": True,
            "Paused": False,
            "Restarting": False,
            "OOMKilled": False,
            "Dead": False,
            "Pid": PID,
            "ExitCode": 0,
            "Error": "",
            "StartedAt": EPOCH,
            "FinishedAt": "0001-01-01T00:00:00Z",
        },
    }


def _reply(obj):
    return json.dumps(obj, separators=(",", ":")).encode("ascii") + b"\n"


def _commands(monkeypatch, *replies):
    replies = iter(replies)
    calls = []

    def docker(argv, deadline):
        calls.append((argv, deadline))
        reply = next(replies)
        return reply() if callable(reply) else reply

    monkeypatch.setattr(inventory, "_docker", docker)
    return calls


def _sample(visit):
    return inventory.sample_dec4_docker_inventory(visit, deadline=time.monotonic() + 2)


def test_one_process_matches_acknowledged_daemon_pid_and_epoch(visit, inspected, monkeypatch):
    calls = _commands(monkeypatch, _reply(inspected), TOP, _reply(inspected))
    checks = []
    visit.context.leg.check = lambda: checks.append(len(calls))
    facts = _sample(visit)
    assert facts == inventory.Dec4DockerInventory(CID, PID, EPOCH, 1)
    assert not hasattr(facts, "start_ticks")
    assert checks == [0, 3]
    assert [argv for argv, _ in calls] == [
        ("container", "inspect", "--format", inventory._FORMAT, CID),
        ("container", "top", CID, "-o", "pid"),
        ("container", "inspect", "--format", inventory._FORMAT, CID),
    ]
    assert len({deadline for _, deadline in calls}) == 1


@pytest.mark.parametrize(
    "update",
    [
        {"resolution": "DISCOVERED_EXACT_SCOPE"},
        {"cid": "c" * 64},
        {"spec_sha256": "0" * 64},
    ],
)
def test_unacknowledged_visit_does_not_query(visit, monkeypatch, update):
    visit.context.leg.record["visits"][0]["create"].update(update)
    calls = _commands(monkeypatch)
    with pytest.raises(ValueError, match="^h3_docker_inventory_ack$"):
        _sample(visit)
    assert calls == []


def test_ack_change_during_observation_denies(visit, inspected, monkeypatch):
    def finish():
        visit.context.leg.record["visits"][0]["status"] = "CLOSED"
        return _reply(inspected)

    _commands(monkeypatch, _reply(inspected), TOP, finish)
    with pytest.raises(ValueError, match="^h3_docker_inventory_ack$"):
        _sample(visit)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"id": "c" * 64}, "inspect_identity"),
        ({"name": "/other"}, "inspect_identity"),
        ({"image": "sha256:" + "8" * 64}, "inspect_identity"),
        ({"source": "8" * 64}, "inspect_identity"),
        ({"visit": "8" * 32}, "inspect_identity"),
        ({"pid_mode": None}, "pid_namespace"),
        ({"pid_mode": "host"}, "pid_namespace"),
        ({"pid_mode": "container:" + "8" * 64}, "pid_namespace"),
        ({"init": True}, "pid_namespace"),
        ({"tty": True}, "private_stream"),
        ({"open_stdin": False}, "private_stream"),
        ({"stdin_once": False}, "private_stream"),
        ({"log_driver": "json-file"}, "private_stream"),
        ({"restart_count": 1}, "restart"),
        ({"restart_count": False}, "restart"),
        ({"restart_policy": {"Name": "always", "MaximumRetryCount": 0}}, "restart"),
    ],
)
def test_wrong_pinned_inspect_metadata_denies(visit, inspected, monkeypatch, changes, reason):
    calls = _commands(monkeypatch, _reply(inspected | changes))
    with pytest.raises(ValueError, match=f"^h3_docker_inventory_{reason}$"):
        _sample(visit)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "state",
    [
        {"Dead": True},
        {"Paused": True},
        {"Running": 1},
        {"Error": "secret stderr or state text"},
        {"Status": "created"},
        {"Restarting": True},
        {"OOMKilled": True},
        {"ExitCode": False},
        {"Pid": True},
        {"Pid": 1},
        {"Pid": 2**31},
        {"FinishedAt": "2026-12-04T14:31:30Z"},
        {"StartedAt": "0001-01-01T00:00:00Z"},
        {"StartedAt": "2026-02-31T14:31:31Z"},
        {"StartedAt": "2026-12-04T14:31:31.1234567890Z"},
        {"StartedAt": "Fri Dec 4 14:31:31 2026"},
        {"Health": {}},
    ],
)
def test_incomplete_or_unusable_full_state_denies(visit, inspected, monkeypatch, state):
    inspected["state"].update(state)
    _commands(monkeypatch, _reply(inspected))
    with pytest.raises(ValueError, match="^h3_docker_inventory_inspect_state$"):
        _sample(visit)


@pytest.mark.parametrize("field", ["Running", "FinishedAt", "Pid", "StartedAt"])
def test_missing_state_is_not_inferred(visit, inspected, monkeypatch, field):
    del inspected["state"][field]
    _commands(monkeypatch, _reply(inspected))
    with pytest.raises(ValueError, match="^h3_docker_inventory_inspect_state$"):
        _sample(visit)


@pytest.mark.parametrize("mutation", [lambda raw: raw[:-1], lambda raw: b'{"id":1,' + raw[1:]])
def test_bad_json_frames_are_rejected(visit, inspected, monkeypatch, mutation):
    _commands(monkeypatch, mutation(_reply(inspected)))
    with pytest.raises(ValueError, match="^h3_docker_inventory_inspect_frame$"):
        _sample(visit)


@pytest.mark.parametrize("changed", [{"Pid": PID + 1}, {"StartedAt": EPOCH.replace("679", "678")}])
def test_bracket_requires_exact_epoch_and_pid(visit, inspected, monkeypatch, changed):
    after = deepcopy(inspected)
    after["state"].update(changed)
    _commands(monkeypatch, _reply(inspected), TOP, _reply(after))
    with pytest.raises(ValueError, match="^h3_docker_inventory_changed$"):
        _sample(visit)


@pytest.mark.parametrize(
    ("top", "reason"),
    [
        (b"PID\n32768\n32769\n", "extra_process"),
        (b"PID\n32769\n32768\n", "extra_process"),
        (b"PID\n32769\n", "top_pid_mismatch"),
        (b"PID\n", "top_shape"),
        (b"PID\n32768", "top_frame"),
        (b"PID\n32768\n32768\n", "top_shape"),
        (b"PID\n32768\n\n", "top_shape"),
        (b"PID\n2147483648\n", "top_shape"),
        (b"PID\n00032768\n", "top_shape"),
        (b"PID\n32768 \n", "top_shape"),
        (b"PID LSTART\n32768 secret\n", "top_shape"),
    ],
)
def test_top_rejects_extra_wrong_or_unknown_rows(visit, inspected, monkeypatch, top, reason):
    calls = _commands(monkeypatch, _reply(inspected), top, _reply(inspected))
    with pytest.raises(ValueError, match=f"^h3_docker_inventory_{reason}$"):
        _sample(visit)
    assert len(calls) == 3


def test_expired_deadline_prevents_owner_and_docker_queries(visit, monkeypatch):
    calls = _commands(monkeypatch)
    visit.context.leg.check = lambda: pytest.fail("expired sampler touched BankLeg")
    with pytest.raises(ValueError, match="^h3_docker_inventory_timeout$"):
        inventory.sample_dec4_docker_inventory(visit, deadline=time.monotonic() - 1)
    assert calls == []


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        ("import sys; sys.stdout.buffer.write(b'PID\\n32768\\n')", TOP),
        ("import sys; sys.stderr.write('secret')", "reply"),
        ("import sys; print('secret'); sys.exit(1)", "reply"),
        ("print('x' * 8192)", "reply"),
        ("import time; time.sleep(20)", "timeout"),
    ],
)
def test_native_runner_bounds_pipe_and_time_without_leaking_output(monkeypatch, script, expected):
    popen = subprocess.Popen
    launched = []
    args = ("container", "top", CID, "-o", "pid")

    def launch(argv, **kwargs):
        assert argv == (*inventory._DOCKER, *args)
        assert kwargs["env"] == inventory._ENV
        assert kwargs["stdin"] == subprocess.DEVNULL
        # Run only a local invented Python producer, never Docker, in pytest.
        child = popen(
            (sys.executable, "-I", "-c", script), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        launched.append(child)
        return child

    monkeypatch.setattr(inventory.subprocess, "Popen", launch)
    deadline = time.monotonic() + (0.25 if expected == "timeout" else 5)
    if type(expected) is bytes:
        assert inventory._docker(args, deadline) == expected
    else:
        with pytest.raises(ValueError, match=f"^h3_docker_inventory_{expected}$"):
            inventory._docker(args, deadline)
    assert len(launched) == 1 and launched[0].poll() is not None
